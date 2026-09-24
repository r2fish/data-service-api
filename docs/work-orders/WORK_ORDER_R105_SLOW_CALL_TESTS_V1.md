# 作業指示書 — R-105 遅い call 段テスト 20 件の作り替え

## 0. 版数・位置づけ

- **v1.1 (2026-09-24)。** v1.0 からの変更: 設計レビュー (設計 §4) の 9 件を反映 (§1 の 4、§2.1 の 4〜6、§2.3 の 4、§2.4 の M4、§4.1 の 1〜2)。
- **v1.0 (2026-09-24)。** 基点 local main `63bb9bf`。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-105 (規模 M)。設計 `docs/design/SLOW_CALL_PHASE_TESTS_V0_1.md` (決定 D-1〜D-5)。変更クラス **Class C** (`conformance-tests/test_c25_result_request_id.py` の註釈と、同型性表に登録された helper `_isomorphic_symbol_source` の本体)。`tools/change_class.py` の下限は C。
- 役割: 実装担当 1 (WP-1 → WP-2 → WP-3 を直列)、レビュー担当 (コードレビュー 1 回)、監査担当 (Class C)。完了ゲートと commit は監督。
- WP-2 / WP-3 は任意: 位置参照の再固定や既存テストの書き換えが 10 行を超えるなら実装せず、報告に理由を書く (残った分は台帳に明記する)。

## 1. 監督確定事項 (設計 §2 の写しではなく、実装に効く事実だけ)

1. 4 PostgreSQL plug の宣言 `audit_query.visibility_lag_ms` を 11,000 → **4,000** にする。値は両 http adapter の module 定数 `CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS = 1000` / `CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS = 2000` + `VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` (既存 1000)。
2. r2db は定数で宣言する (role-level timeout は置かない。`r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py` は変更せず緑のまま)。MitateDB は adapter の bootstrap で `ALTER ROLE` を発行し、peer が catalog から導出する (導出コードは触らない)。
3. conformance テスト本体 (C-25 / C-27 / C-09 / C-05) の待ち方・assert は変えない。触るのは C-25 の註釈だけ。
4. 計測で timeout 起因の赤 (`statement timeout` / `idle-in-transaction` を含む失敗)、**または監査 event が期限内に現れない赤** (C-09 / C-23 / C-25 などの「event が見つからない」形) が 1 件でも出たら、直さずに監督へ上げる (値の変更は監督裁定。候補は statement 2,000 → lag 5,000)。MitateDB の statement 1,000 は api role の全 SQL (credential 照合・`application_audit` 書込み・control-plane 台帳) に効く (設計 D-1)。

## 2. WP-1 — 4 PostgreSQL plug の宣言 lag を 4,000 ms にする

### 2.1 タスク

1. `r2db-api/conformance/conformance_adapter_r2db_http.py`: module 定数 2 つを足し、`:1483` の `audit_visibility_lag_ms=` を `CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS + CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` に替える。`:1473-1482` の註釈を事実に合わせる (「pre-Q4 と同じ固定値 5000+5000+margin」→「conformance 配備の値。role-level timeout は置かない (Q4 §3.11 の 4)」)。`DEFAULT_AUDIT_*` の import が不要になれば外す。
2. `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`: module 定数 2 つを足し、bootstrap で `0007_platform_declarations.sql` を流した直後に、api role と controlplane role へ `ALTER ROLE … SET statement_timeout = '1000ms'` / `SET idle_in_transaction_session_timeout = '2000ms'` を adapter 自身の admin 接続 (`_Platform.admin_dsn`、autocommit) で発行する。SQL の形は `MitateDB-api/tests/control_plane_harness.py:247` と同じ (`sql.Identifier` / `sql.Literal`)。tests からは import しない。`:1096-1101` の註釈 (「shipped 5000ms/5000ms」) を事実に合わせる。
3. `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`: `:118-119` の `DEFAULT_AUDIT_*` との一致を、adapter の `CONFORMANCE_AUDIT_*` との一致に替える (`!= cluster default` の 2 assert は残す)。docstring の「role-level 5000ms/5000ms」の記述を事実に合わせる。
4. 新規テスト (両 peer、既存の `test_conformance_adapter_*_http_audit_writer_timeouts.py` に足す): その peer の http adapter を build し、`audit_visibility_lag_ms()` が `CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS + CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` に等しいこと **と、リテラル `4000` に等しいこと** の両方を assert する (両辺同源の穴を塞ぐ。両 peer の plug が同じ値を宣言することの固定)。MitateDB 側はさらに、api / controlplane role の `pg_db_role_setting` を `platform_declarations.read_declared_role_timeouts` で読み `derive_visibility_lag_ms` が同じ値を返すことを assert する (宣言 = catalog 導出)。
5. `conformance-tests/test_c25_result_request_id.py:335-348` の註釈: Phase 10 WP-5a review L-1 の文 (「Measured (…) BOTH in-process peers declare `visibility_lag_ms` 0, and BOTH http plugs declare 11000 on this deployment -- the lag is a property of the http adapter (network + buffering), not of either peer」) は **逐語で残し**、その直後に R-105 の訂正を足す: 両 http plug は conformance 配備の値 4000 を宣言する (r2db は adapter 自身の定数 `CONFORMANCE_AUDIT_*` の和、MitateDB は adapter が置く role timeout からの peer の catalog 導出)。L-1 の「どちらの peer の性質でもない」は MitateDB については成り立たなくなった。行数固定は不要 (`security/CONTROL_MAPPING.md` の C-25 参照は `::test` 形式)。conformance-tests の他のファイルに「11000」「11 s」の記述が無いことを grep で確認する (基点では C-25 の註釈のみ)。
6. 計測: 実装後に §2.5 の pt コマンド (20 件 + in-process 10 件) を `--durations=0` で回し、20 件の call 時間を報告に表で貼る (前 = 単独 207.9 s、`pt 20260924-123120`)。C-09 v1 / v2 は全 adapter で **2 回** 回す (r2db の宣言は裏打ちが無く、C-09 は `sleep(lag)` ちょうどで読むため、1 回の緑では flakiness を判定できない)。

### 2.2 触ってよいパス

- `r2db-api/conformance/conformance_adapter_r2db_http.py`
- `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`
- `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py` (新規テストの追加のみ。既存 3 テストは変えない)
- `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`
- `conformance-tests/test_c25_result_request_id.py` (註釈のみ)

触らない: 両 peer の `src/`、`migrations/`、`spec/`、`security/`、`conformance-tests/CONDITIONS.md`、C-27 / C-09 / C-05 のテスト本体、port (`conformance-tests/adapter.py`)。

### 2.3 完了条件

1. 4 PostgreSQL plug の `audit_visibility_lag_ms()` が 4,000 (新規テスト 2 件が緑)。
2. MitateDB の宣言値が catalog 導出と一致 (新規テストの導出 assert が緑)。
3. `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py` が conformance 定数を固定して緑、`r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py` は変更なしで緑。
4. `conformance-tests` 全体を 1 回前景で回して緑 (約 9 分、Bash の timeout 600000 で 1 呼び出しに収まる。MitateDB の api / controlplane role の timeout 変更は MitateDB-api-http / -socket へ向かう全 conformance に効くので、代表 7 ファイルではなく全体)。timeout 起因の赤と「監査 event が現れない」赤が 0。C-09 v1 / v2 は別に 2 回 (§2.1 の 6)。網羅は監督の完了ゲートが与える。
5. 20 件の call 時間の前後 (監査照合: 報告の表と pt の log)。
6. C-25 の註釈が事実と一致 (監査照合: 差分)。

### 2.4 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1 (r2db) | M1: r2db http adapter の `audit_visibility_lag_ms=` を `DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS + DEFAULT_AUDIT_IDLE_TIMEOUT_MS + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` に戻す | 新規テスト (r2db) 赤 |
| 1・2 (MitateDB) | M2: MitateDB http adapter の `ALTER ROLE` 発行を落とす | 新規テスト (MitateDB) 赤、`…_has_statement_and_idle_timeouts_set` 赤 |
| 2 | M3: MitateDB の `ALTER ROLE` を statement だけにする (idle を落とす) | 新規テストの導出 assert 赤 |
| 3 | M4: MitateDB adapter の `ALTER ROLE … idle_in_transaction_session_timeout` の値だけを定数参照からリテラル `'5000ms'` にする | `…_has_statement_and_idle_timeouts_set` の idle 一致 assert 赤、新規テストの導出 assert 赤 |
| 1 (両 plug の一致) | M4': r2db の `CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS` を 3000 にする | 新規テスト (r2db) のリテラル 4000 assert 赤 |
| 4・5・6 | 監査照合 (pt の集計行と `--durations=0` の表、差分) | — |

定数そのものを動かす変異は、宣言・発行・期待が同一の源なので原理的に赤にならない (設計レビュー指摘 1)。M4 / M4' はそれぞれ発行側・宣言側の片方だけを動かす。

### 2.5 道具の引数

```
tools/dev/pt.py -C .claude/worktrees/mystifying-villani-03bfde -- r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py -q
tools/dev/pt.py -C .claude/worktrees/mystifying-villani-03bfde -- 'conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_v2_declaration_and_position_agree' 'conformance-tests/test_c25_result_request_id.py::test_c25_result_request_id' 'conformance-tests/test_c27_concurrent_same_key.py::test_c27_same_digest_executes_once' 'conformance-tests/test_c09_audit_evidence.py::test_c09_v1_fail_closed_events_are_observable_through_audit_query' 'conformance-tests/test_c09_audit_evidence.py::test_c09_v2_no_forbidden_field_key_or_reusable_secret_value_appears' -q --durations=0 -p no:randomly
tools/dev/pt.py -C .claude/worktrees/mystifying-villani-03bfde -- conformance-tests -q
tools/dev/pt.py -C .claude/worktrees/mystifying-villani-03bfde -- 'conformance-tests/test_c09_audit_evidence.py::test_c09_v1_fail_closed_events_are_observable_through_audit_query' 'conformance-tests/test_c09_audit_evidence.py::test_c09_v2_no_forbidden_field_key_or_reusable_secret_value_appears' -q   # 2 回
tools/dev/mutate.py "$SP/r105-wp1-mutations.json" -C .claude/worktrees/mystifying-villani-03bfde
```

## 3. WP-2 (任意、Class B) — MitateDB `tests/test_audit_query.py` の `pg` fixture

### 3.1 タスク

`MitateDB-api/tests/test_audit_query.py:229-234` の `pg` fixture が `_postgres_harness(control_platform, audit_statement_timeout_ms=1000, audit_idle_timeout_ms=1000)` を渡す (lag 3,000)。同ファイル全体を回し、lag に依存する vector (明示値を持つもの) が緑のままであることを確認する。

### 3.2 触ってよいパス

`MitateDB-api/tests/test_audit_query.py` (fixture の 1 呼び出しと、必要なら fixture の docstring)。

### 3.3 完了条件 → 変異

| 完了条件 | 変異 / 照合 |
|---|---|
| 1. `test_in_memory_and_postgres_audit_query_semantics_have_parity` の call 時間が前 (11.35 s、ゲート) の半分以下 | 監査照合 (pt `--durations=0`) |
| 2. 同ファイル全テスト緑 | 監査照合 (pt の集計行) |

## 4. WP-3 (任意、Class C、両 peer 同一本体) — `_isomorphic_symbol_source` の解析 cache

### 4.1 タスク

1. 両 peer の `tests/test_audit_query.py` の `_isomorphic_symbol_source` (r2db `:3289`、MitateDB `:3062`) に、module-level `_ISOMORPHIC_PARSE_CACHE: dict[Path, tuple[str, _ast.Module]]` (末尾の `get_source_segment` が `source` を要するので文字列も持つ) を鍵 = `peer_root / relative_path` (絶対 path) で使う `read_text` + `_ast.parse` の cache を入れる。本体は両 peer で同一にする (既存の同型性テストが固定する)。docstring は既存を逐語で残し、cache の 1 段落を末尾に足す (§1.5 の 40c)。
2. ガードテスト (両 peer に同名で): **両 peer で relative path が文字列として同一の行** (例: `("tests/test_audit_query.py", "tests/test_audit_query.py", "_ISOMORPHIC_TARGETS")` — 両 peer に同名で存在し、行の並びが peer 方向で逆なので生ソースは必ず異なる) の symbol について、`_isomorphic_symbol_source(self_root, …)` と `_isomorphic_symbol_source(sibling_root, …)` の返り値が **異なる** ことを assert する。path が両側で異なる行 (src 系) を選ぶと M5 が赤にならない (鍵の衝突が起きない)。
3. 位置参照: `tools/tests -q` (`git add -N` してから) と `conformance-tests/test_conditions_register.py` を回し、`security/CONTROL_MAPPING.md` の `file:line` 参照が両ファイルの行ずれで赤になるなら、再固定が 10 行以内のときだけ直す。超えるなら WP-3 を実装せず報告する。

### 4.2 触ってよいパス

`r2db-api/tests/test_audit_query.py`、`MitateDB-api/tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` の行は増減しない)。

### 4.3 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1. cache の鍵が絶対 path | M5: 鍵を `relative_path` だけにする (両 peer) | ガードテスト赤 (両 peer) |
| 2. 両 peer の本体が同一 | M6: 片 peer だけ cache 行を落とす | `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` 赤 |
| 3. `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` の call 時間が前 (10.0 s、r2db、ゲート) の半分以下 | 監査照合 (pt `--durations=0`) |

### 4.4 道具の引数

```
tools/dev/pt.py -C .claude/worktrees/mystifying-villani-03bfde -- r2db-api/tests/test_audit_query.py MitateDB-api/tests/test_audit_query.py -q --durations=5
tools/dev/mutate.py "$SP/r105-wp3-mutations.json" -C .claude/worktrees/mystifying-villani-03bfde
```

## 5. 範囲外 (起票せず観察として引き継ぎ書に残す)

- C-05 v2 の往復数 (設計 D-3)。
- C-25 の backoff の刻み (lag を 1〜2 s 超える) — 値が小さくなった後の実測で判断する。

## 6. レビューと受け入れ

- コードレビュー 1 回 (Class C)。準拠: 設計 §2〜§3、本書 §1。
- 受け入れ監査 1 回 (Class C)。材料: 実装報告、pt / mutate の log、コードレビュー結果、完了ゲートの集計行と `slowest 25 durations` の前後 (前 = label r86)。
- 完了ゲート: `tools/dev/gate.py -C <worktree> --label r105`。壁時計の前 = 521.02 s (r86)。

## 7. 記録 (統合時に監督が埋める)

### 7.1 訂正註と監督裁定

- **【訂正註 2026-09-24 (コードレビュー指摘 3)】** §2.1 の 5 の「L-1 の『どちらの peer の性質でもない』は MitateDB については成り立たなくなった」は誤り — MitateDB plug の catalog 導出は Q4 から既存で、R-105 が変えたのは seed 値だけ。註釈は「変わったのは数値であって機構ではない」に直した (監督裁定)。
- **【訂正註 2026-09-24 (コードレビュー指摘 2)】** §2.4 の M1 (`DEFAULT_AUDIT_*` に戻す) は import を外したため `NameError` で赤になり値の assert を通らない。M1 を call site に `+ 1000` を足す形に差し替えて再実行した。M2 / M3 の赤は導出 assert ではなく第 1 assert (定数和) で出る。完了条件 2 を単独で赤にする変異は adapter 編集では作れない (設計 D-1 の限界の記述)。
- **【訂正註 2026-09-24 (コードレビュー指摘 4)】** §4.3 の M5 は両 peer を編集して r2db 側のガード 1 本で観測していた。MitateDB 側だけを編集して MitateDB 側のガードで観測する M5b を足した。
- **【訂正註 2026-09-24 (コードレビュー指摘 1)】** 文書中の pt log 名 `pt-YYYYMMDD-HHMMSS` は公開値スキャンが project id として拾うので `pt YYYYMMDD-HHMMSS` と書く。

### 7.2 実施と受け入れ

- **WP-1** (2026-09-24): 両 http adapter の `CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS = 1000` / `CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS = 2000`; r2db は `_build_control_stack` の宣言を定数の和に、MitateDB は `_bootstrap_platform` で `0007` 直後に api / controlplane role へ `ALTER ROLE` (admin 接続、autocommit、直後に close)。新規テスト `test_http_conformance_adapter_declares_the_conformance_deployment_visibility_lag` (両 peer: 定数和・リテラル 4000; MitateDB はさらに catalog 導出)。`…_has_statement_and_idle_timeouts_set` は conformance 定数を固定。C-25 の註釈は L-1 逐語 + R-105 訂正 (§7.1)。pt: `6 passed`、`30 passed in 110.53s` (20 件 + in-process 10 件)、`1104 passed in 606.05s` (conformance 全体)、C-09 v1/v2 2 回とも `12 passed`。変異 M1〜M4' 5 件すべて赤 (監督再実行 `mutate 20260924-134610`)。
- **WP-2**: `pg` fixture に 1000/1000 を渡す。`62 passed in 20.94s`。parity 11.35 s (ゲート) → 3.34 s (単独)。
- **WP-3**: 両 peer 同一の `_ISOMORPHIC_PARSE_CACHE` (鍵 = 絶対 path、`(source, tree)`)、既存 docstring 逐語 + 追記、ガードテスト `test_isomorphic_symbol_source_cache_key_is_the_resolved_absolute_path` (symbol `_postgres_harness`)。`139 passed in 52.27s`。isomorphism 10.0 s → 2.6 s (単独) / 5.6 s (ゲート)。変異 M5 / M6 / M5b 赤 (`mutate 20260924-134638`)。位置参照の再固定 0 行。
- **完了ゲート** (監督単独、label r105): `4022 passed, 2 subtests passed in 499.13s (0:08:19)`、judge=PASS、残骸差分 0。前 `4018 passed … 521.02s`。監査後の註釈修正を含む再実行 (label r105b、commit の正本): `4022 passed, 2 subtests passed in 486.51s (0:08:06)`、judge=PASS、残骸差分 0。20 件の call 時間: 単独 207.9 → 99.7 s (−52%)、ゲート負荷下 243.1 → ≈130 s (≈ −47%、C-05 v2 不変)。詳細は設計 §5。
- mutate の集計行: `mutate: 5 mutations, 5 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged` (`mutate 20260924-134610`)、`mutate: 3 mutations, 3 as expected, restores verified 2/2 files (sha256 x2)` (`mutate 20260924-134638`)。
- **コードレビュー** 4 件 → すべて同じ変更セットで直した (§7.1)。**受け入れ監査** (2026-09-24): 完了条件は全件充足 (WP-1/2 は間接)、未充足 2 件と証拠不足 2 件は同じ変更セットで直した / 記録した (設計 §5)。観察 3 件は引き継ぎ書 `docs/work-orders/HANDOVER_20260924_FABLE6.md` の裁定節。
