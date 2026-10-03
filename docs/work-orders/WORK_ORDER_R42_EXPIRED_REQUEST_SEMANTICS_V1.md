# 作業指示書 — R-42 期限切れ要求の意味論 (Change Set Manifest)

## 0. 版数・位置づけ

- **v1.1 (2026-10-03)。** 実施の記録 (§5) と訂正註 (§6) を足した。本文は書き換えていない。
- **v1.0 (2026-10-03)。** 起草。未発注・未 commit。
- 設計の正本は `docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md` **v0.10** (以下「設計」)。本書は設計の問題設定 (§1)・制約 (§2)・決定 (§3 の D-1〜D-9)・却下案 (§4)・裁定 (§5・§10) を写さず節番号で指す (`RM` §9 の 9)。逐語は付録の確定文ファイル (設計 §9 から機械的に抜き出したもの) と §1.2 の変異案の写しだけ。
- 台帳 `RM` §8.1 の **R-42** (`RM`:461)。**規模 L** (`OC` §1.13 の 74)。**変更クラス D** (`security/`、契約、conformance)。WP ごとのクラスは各 WP に書く。
- 着手条件: R-118 の merge の後に、統合 branch `r42` (worktree `.claude/worktrees/r42`) へ local main を取り込む。本書の `file:line` は `r42` の `925760f` (R-118 の merge 前) の現物である。R-118 の merge で `SJ`・`CT/test_contract.py`・`spec/*.md`・版の literal の行と値が動くので、WP-1 は着手時に記号名で引き直す (完了条件 1)。両 peer の製品コード (`R/postgres.py`・`R/structured.py`・`R/limits.py`・`M/backend_postgres.py`・`M/backend_sqlite.py`・`M/pool.py`・`M/cell.py`) は、設計が引く行が `925760f` でも同じ行である (起草時に照合)。
- **番号の割当** (枠。監督確定): 契約版 = **1.16.0**、直前の版 = 1.15.0 (R-118)、従属判断 = **21**、port 版 = **v1.22** (`CA` に新しい節)、新条件 = **C-35 の次** (採番は WP-2 で監督。本書は番号を書かない)、`CM` = 3.17 を見込む (現物で確かめる)。
- 番号: 完了条件は全 WP の通し番号 (1〜85)。変異は **V<完了条件番号>** (複数は a・b…、各 1 entry)。expect は `red` (収集時の assert で落ちる変異は `error`)。変異の無い完了条件は「監査照合」と書き、照合対象の逐語 (コマンドと集計行、`file:line`、`git diff`) を報告と §5 に残すこと自体を完了条件とする (`OC` §1.5 の 40)。
- 読む順: §1 → 設計 §1・§3・§6・§9 → 担当 WP。

**略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`ROLES` = `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`、`DEVTOOLS` = `tools/dev/README.md`、`CM` = `security/CONTROL_MAPPING.md`、`CA` = `docs/design/CONFORMANCE_ADAPTER_V1.md`、`CT` = `conformance-tests`、`COND` = `conformance-tests/CONDITIONS.md`、`CH` = `conformance-tests/CONDITIONS_HISTORY.md`、`SJ` = `spec/data-service-api.v1.json`、`SC` = `spec/OPERATION_CATALOG.json`、`R` = `r2db-api/src/r2db_api`、`M` = `MitateDB-api/src/mitatedb_api`、`RT` = `r2db-api/tests`、`MT` = `MitateDB-api/tests`、`RC` = `r2db-api/conformance`、`MC` = `MitateDB-api/conformance`、`$SP` = 監督が発注時に渡す scratchpad (`{scratchpad}`)、`<NN>` = 新条件の番号 (C-35 の次)。

### 0.1 枠 (問題設定・守る条件・決定・却下案・未確定)

- 問題設定と守るべき条件: 設計 §1・§2。決定軸は「期限の検査のために DB 往復を足さない」「製品コードに test 用 hook を足さない」(設計 §2、X-1・X-7)。
- 決定と根拠: 設計 §3 の D-1〜D-9、§6、§9 (契約文。依頼者確定 2026-10-03)。依頼者裁定 U-1〜U-9・V-1〜V-3・契約文の確定は設計 §10 (再審議しない。`OC` §1.7 の 51)。
- 却下した代替案: 設計 §4 の X-1〜X-8。蒸し返さない。
- 未確定で依頼者判断待ちの選択肢: 無し。設計が「作業指示書で確定する」とした点は §1.1 に監督の確定事項として置く。

## 1. 設計からの転記と監督の確定事項

### 1.1 確定事項

| # | 事項 | 内容 | 出所 |
|---|---|---|---|
| 1 | 契約の版と確定文 | minor 1.16.0・従属判断 21。確定文 (設計 §9) は付録の script の出力。置き換えは「1.15.0」→「1.16.0」、「subordinate ruling 20」→「21」、「1.14.0」→「1.15.0」だけ (script が適用する)。他は逐語 | 設計 v0.10 の版数行、§10 末尾 |
| 2 | 置き場 | §9.1 → `limits.execution_ms` (新 key)。§9.2 → `versioning.version_binding` の 1.15.0 の文の後・version-flip の文 (「A peer's version-flip」) の前。§9.3 → `versioning.obligations[]` の末尾。§9.4 → `structured_operations.dry_run.decision` の末尾 | 設計 D-6、U-9 |
| 3 | 版の切り替え (設計 D-6 (B)) | `spec/` の 1.16.0、生成 `OPERATION_CATALOG.json` 3 部、両 peer の契約の同梱コピー、両 peer の版の flip、新条件と version gate の guard を統合 branch `r42` 上の**最後の 1 commit** (WP-5) に入れる。振る舞いの WP (WP-2〜WP-4) はそれより前の commit で版を動かさない。中間 commit で C-29 と guard を赤にしない | 設計 D-6、§11.6 N-6、§11.7 F-12 |
| 4 | WP の順 | WP-1 は内容を先に作り、commit は WP-5。WP-2 (port の部) → WP-3 → WP-4 は `r42` に順に commit。WP-2 の新条件の部は WP-5 の commit に入る (3) | 枠 |
| 5 | 検査の置き方 | 検査は文を発行する helper に置く: r2db は `_run` (`R/postgres.py`:234) と `transaction()` の前 (入れ子を含む)、MitateDB は `_execute` (`M/backend_postgres.py`:295)。規則は「検査は次に文を発行する点にだけ置き、次が pre_commit / COMMIT である点には置かない」 | 設計 D-9、§11.5 RW-9 |
| 6 | 観測 | 新 primitive と既存 2 primitive の handle は「放した後に要求のために発行された文の数」を返す。値 = 要求が使う pool の `execute_count` の差 + transaction / savepoint を開いた回数 (enter 側だけ) − checkout の維持の文。enter 側の計数を足す場所 (両 peer の `psycopg_counting.py` か plug 側) は実装担当が決めて報告する。in-process の 2 plug は None | 設計 D-7、§6.4 |
| 7 | B | 完了ゲートの中で受理点から stall 点までの到達時間を測って決める。初期値 500 ms、保持は合図から B + B/5 | 設計 D-7、M-8 |
| 8 | `reference_wall_clock` の定義文 | 1.16.0 の段落か `limit_enforcement` の説明に 1 文を足すかを WP-1 の実装担当が現物で確かめ監督に上げる。裁定は監督 | 設計 §11.7 の範囲外の観察 |
| 9 | 共通条件で駆動しない点 | lock 待ちの後の検査、pool 待ち超過と接続確立の写像、閾値、義務 (a)、義務 (c) の文の bound は peer の単体テストで固定 (r2db は clock の注入、MitateDB は test 側の `time.monotonic` の差し替え) | 設計 D-9 の最後の項 |

10. **起草の疑義への監督の確定 (2026-10-03)**: (a) `obligations` の index と R-118 の 1.15.0 の文の pin (`len(versions) == 12`、`"1.15.0" not in versions`) は着手時に実測して改める (WP-1 の完了条件 1・5・6)。(b) §9.3 の json の `"subordinate_ruling": 20` も 21 に置き換える (版の番号の読み替えの一部。設計 v0.10 の版数行)。(c) §9.1 の 2 段落は半角空白 1 つで繋いで 1 つの文字列の値にする (R-108 の先例)。(d) WP-1 の worktree は `.claude/worktrees/r42-wp1` (branch `r42-wp1`。統合 branch `r42` から切る)。変更は WIP commit としてその branch に置き、WP-5 の最後の 1 commit で統合する (`r42` には WP-5 まで入れない)。WP-2 の新条件の部 (test file と CONDITIONS の行) も同じ扱いで `r42-wp1` に置く。(e) version gate の殺し手として test module が「1.15.0 の宣言は束縛しない」と自己 assert する形 (完了条件 32) は test 側の guard であり、製品コードに触れないので認める。(f) 性能差分の基準 (§3) は、WP-5 で flip の直前の統合 branch の commit と flip の後の merge 候補を同じ日に同じ引数で測って並べる。設計 §12.5 は参考値であり基準ではない (別の日・別の commit の値)。(g) 変異を持たない完了条件 23・25 は監査照合 (設計 §6.4 の記述と現物の file:line を監査担当が突き合わせる)。

### 1.2 変異案の写し (設計 §6.6 の材料。設計レビュー 2 回目 1 巡目の担当観点 B の提案、2026-10-02。逐語)

設計段階の案で、`mutate.py` の spec ではない (対象のコードは実装前)。本書の各 WP の対応表はこれと設計 §6.6 から確定した。

| id | completion_condition | mutation | expected_red |
|---|---|---|---|
| B-M1 | U-8 (a) / obligation (b) second half: no clock check after the last statement | re-add the post-SELECT check_deadline in r2db query (r2db-api/src/r2db_api/postgres.py:1554 today) and an equivalent post-last-statement check in MitateDB read | a peer unit test that moves the injected clock (r2db) / patched monotonic (MitateDB) past the deadline after the last statement and expects success; no conformance vector covers it |
| B-M2 | D-2 (c) at every between-statement point, not only the stall successor | remove the check before _load_catalog / before the 2nd statement of a single _apply / before _idempotency_store (one entry per point, per OC mutate -x pitfall) | peer unit test per point, or a single check inside the statement-issuing helper (r2db _run) so one mutation covers all |
| B-M3 | SQLite backend between-statement and DDL-before checks (D-9 'same semantics') | remove the new checks in MitateDB-api/src/mitatedb_api/backend_sqlite.py | MitateDB peer unit test (in-process plug observes code only) |
| B-M4 | MitateDB record_idempotency psycopg exception translation; SET LOCAL / _retime QueryCanceled -> execution_ms | revert each translation to the current 503 path | MitateDB peer unit test with synthetic QueryCanceled injection (precedent: tests/test_r71_catalog_read_cancel_mapping.py) |
| B-M5 | statement-count handle is wired (non-vacuity) | make the PG plugs' handle return a constant 0 | positive control asserting statements-after-release >= 1 on the 4 PG plugs |
| B-M6 | per-statement bound exists and never exceeds the remaining budget (section 9.1 sentence) | MitateDB/r2db _timeout_ms returns the full execution_ms instead of the remaining one | existing MitateDB tests/test_r102_request_scope.py::test_the_scope_sets_its_timeouts_from_the_deadline_not_the_constructed_value; r2db needs an equivalent |

対応: B-M5 → V21。B-M2 → V43・V57。B-M1 → V48・V69。B-M6 → V50・V60。B-M4 → V61〜V63。B-M3 → V66。

## 2. Change Set Manifest (WP-1〜WP-5)

### 2.0 共通 (全 WP)

**順序**: WP-1 の内容 (別 worktree、commit しない) → WP-2 (port の部を `r42` に commit。新条件の部は作って保持) → WP-3 (`r42` に commit) → WP-4 (`r42` に commit) → WP-2 の新条件の部の実測 (WP-1 と新条件の部を `r42` の worktree に載せた状態) → WP-5 (最後の 1 commit、記録、完了ゲート、監査、main への merge 1 回)。WP-3 と WP-4 は並行しない (`CM` を両方が触る)。

**worktree**: WP-1 = 監督が発注時に指定する別 worktree (変更は WP-5 まで `r42` に入れない。保持の形は監督)。WP-2〜WP-4 = `.claude/worktrees/r42`。

**役割**:

- 実装担当 (`ROLES` の 2、`implementer`): WP-1〜WP-4 に 1 起動ずつ (差し戻しは別起動)。WP-2 の新条件の部の実測は WP-4 の後に別起動。
- コードレビュー (`ROLES` の 5、`reviewer`): WP ごとに 1 巡目は担当観点 A / B の 2 起動の並列。並列の 2 起動は `mutate.py` を実行せず spec を `$SP/review-r42-wp<N>-<A|B>-mutations.json` に書き、監督が実行する。再確認は観点を指定しない 1 起動 (`OC` §1.7 の 50a・50b)。
- 受け入れ監査 (`ROLES` の 6、`evidence-auditor`): 全 WP のレビューの後に 1 回。
- 監督: 確定文ファイル (付録)、新条件の採番、各 commit、WP-5、完了ゲート、`COLLECTION_FLOOR`、指摘の 1 件ごとの裁定 (`OC` §1.15 の 77)、local main への merge。

**実装担当への注意** (発注の「注意」の行に置く。規律の本文は `OC`): `OC` §1.1 の 2 (commit しない。新規 file の `git add -N` だけ)、§1.3 の 26 (skip / xfail を置かない)、§1.5 の 32〜40 (空振り禁止、変異先行、主張は実測の後、確定文言はファイル経由、設計外の拡張は実装前に上げる、同型性テスト、実行規律、対応表)、§1.6 の 42 (suite 全体・`gate.py`・`finalize.py` を実行しない)、§1.7 の 47 (下請けの Agent を起動しない)、§1.9 の 60〜63、§1.10 の 65・66。変異は 1 変異 1 entry、`-x` を使わず、test id はその完了条件の test (`-k` は `--collect-only -q` で確かめる)。新しいコメント・docstring は現在形で、フェーズ / WP / 台帳 ID / 日付を入れない (`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 (5))。`CT/` の docstring の `file:line` は `CT/test_conformance_docstring_position_refs.py` が検査する。報告は `$SP/r42-wp<N>-report.md` (道具の出力行をそのまま貼る)。port 8000 / 8001 の uvicorn は別 repo の常設 service なので止めない。

**道具の引数** (main checkout を cwd に、`-C` で worktree を指す。渡し忘れると main を測る):

```bash
tools/dev/pt.py -C .claude/worktrees/<name> -- <各 WP の「テスト」のパス> -q
tools/dev/mutate.py "$SP/r42-wp<N>-mutations.json" -C .claude/worktrees/<name>
```

worktree を cwd にして: `python3 tools/check_comment_provenance.py --base <WP の基点> <触った src>`、`python3 tools/check_comment_provenance.py --register`、`python3 tools/change_class.py <触った全パス>`、`python3 tools/check_doc_refs.py`、`python3 tools/public_value_scan.py <触った全パス>`。peer の tests は peer ごとに別の `pt.py` 呼び出しで回す。

### 2.1 WP-1 — 契約 1.16.0 (実装担当。commit は WP-5)

**目的**: 設計 §9 の確定文で契約を 1.16.0 にし、設計 D-6 の列挙する pin・記録・版の literal・同梱コピー・派生 catalog を追随させる。peer の挙動は変えない。
**読むべき正本**: 設計 D-6・§9・§10 末尾・§11.7 の範囲外の観察、§1.1 の 1・2・3・8、付録。先例: R-118 の契約の commit (取り込み後の `git log -- spec/data-service-api.v1.json` の最新)、`docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` §2.1。**クラス**: C (契約と宣言値)。**テンプレート**: `ROLES` の 2。

**確定文の置き方** (ファイルは付録の script の出力 `$SP/r42-fixed-text/`):

| JSON path | 値 |
|---|---|
| `limits.execution_ms` (新) | `9.1-1.txt` + 半角空白 1 つ + `9.1-2.txt` |
| `versioning.version_binding` | 1.15.0 の文の末尾と「A peer's version-flip」の間に `9.2.txt` (前後は空白 1 つ) |
| `versioning.obligations` | 末尾に `9.3-entry.json` |
| `structured_operations.dry_run.decision` | 現行の値 + 空白 + `9.4.txt` |

`SJ` と両 peer の同梱コピー (`R/contract/data-service-api.v1.json`、`M/contract/data-service-api.v1.json`) を byte 一致にする。

**触ってよいパス**:

- `SJ`、`R/contract/data-service-api.v1.json`、`M/contract/data-service-api.v1.json`
- `SC`、`R/contract/OPERATION_CATALOG.json`、`M/contract/OPERATION_CATALOG.json` (`python3 tools/contract_catalog.py` で再生成。`--check` は照合)
- `spec/CONTRACT_HISTORY.md` (`## versioning.version_binding` の引用を 1.16.0 の全文に。Revision note を Revision note 10 (1.14.0、`spec/CONTRACT_HISTORY.md`:428) と R-118 の 1.15.0 の note の形で足し、既存の義務 1.7.0 (3) を execution_ms について狭めることも書く)、`spec/CCR_DISPOSITION.md` (従属判断 21。19 の段 :343 と R-118 の 20 の段の形)、`spec/README.md` (1.16.0 の段落。1.14.0 の段落 :35 の形)
- 宣言 4 か所 (`R/capabilities_document.py`:88、`R/control_plane.py`:656、`M/capabilities_document.py`:145、`M/control_plane.py`:1617) と直前のコメント、CH-ID の訂正の追記先 `docs/code-history/r2db-api/service.md`・`docs/code-history/r2db-api/control_plane.md`・`docs/code-history/MitateDB-api/capabilities_document.md`・`docs/code-history/MitateDB-api/control_plane.md`
- 版の literal: `RT/test_foundation.py` (:252・:2496・:2511・:2559・:2594)、`RT/test_audit_query.py` (:1991・:4047・:4081)、`RT/test_control_plane_service.py`:1808、`RT/test_denial_details_and_request_id.py`:514、`MT/test_audit_query.py` (:1727・:1757・:1769・:3849)、`MT/test_control_plane_service.py`:574、`MT/test_denial_details_and_request_id.py` (:552・:566)、`MT/test_http.py`:393 (行と値は R-118 の後の現物で引き直す)
- `CT/test_contract.py`、`CT/test_contract_history_register.py` (register が要求するときだけ)
- これ以外は 0 件。触らない: 両 peer の振る舞いのコード、`COND`、`CH`、`CM`、`RM`。

**完了条件 (1〜18) → 変異** (2〜8 の変異は確定文の 1 語を `SJ` と同梱コピー 2 つの 3 か所で同じに変える形。test id はその文のピン)

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | 着手時に `SJ` の `version_binding` の末尾 (1.15.0 の文と version-flip の文)、`obligations` の件数と末尾の版、R-118 が置いた 1.15.0 の文のピンの形 (右端と obligations の件数・末尾の版の assert) を実測し報告した | 監査照合 (`python3 -c` の出力と `file:line`) |
| 2 | `limits.execution_ms` の値が確定文と byte 一致し、新しい逐語ピンがそれを等号で assert する | V2a: `wall-clock budget` → `wall-clock limit`。V2b: `shorter than one millisecond` → `shorter than one microsecond` |
| 3 | `_PRE_1_8_0_LIMITS_KEYS` (`CT/test_contract.py`:138-146、照合 :180-184) の切り直し: `limits` の key 集合が基点の集合 + `execution_ms` に等しい。docstring に U-9 の裁定 (設計 §10) を書く | V3: `limits` に別の sibling key を 1 つ足す (3 か所) |
| 4 | 1.15.0 の文の末尾と version-flip の文の間がちょうど空白 + `9.2.txt` + 空白 (等号のピン) | V4: `in either direction` → `in one direction` |
| 5 | R-118 の 1.15.0 の文のピンの右端が 1.16.0 の段落の始まりに追随し、同じピンの obligations の件数・末尾の版の assert が 1.16.0 の entry を含む形に移る (1.15.0 の文は 1 字も変えない) | V5: 1.16.0 の段落の直前に 1 語足す (3 か所) |
| 6 | `obligations` の末尾 (1 の実測の index) が `9.3-entry.json` と dict 一致する index 固定のピン (`CT/test_contract.py`:1582 の 1.14.0 の entry のピンの形) | V6: `subordinate_ruling` を 20 に (3 か所) |
| 7 | 散文の無条件義務の個数 (`four`) と entry の `unconditional` の要素数の一致のピン (`_UNCONDITIONAL_COUNT_RE` `CT/test_operation_catalog_register.py`:314 は「Those obligations are unconditional」に当たらない。設計 D-6) | V7: entry の `unconditional` から 1 つ消す (3 か所) |
| 8 | `dry_run.decision` の末尾が空白 + `9.4.txt` のピン。`PIN_1_7_0_DRY_RUN_DECISION` (`CT/test_contract.py`:2279 の包含照合) は緑 | V8: `is the exception` → `is an exception` |
| 9 | 3 つの契約の `contract_version` が 1.16.0 で、版の宣言のテスト (`CT/test_contract.py`:78 の位置) が 1.16.0 を assert する | V9: `SJ` の `contract_version` を 1.15.0 に |
| 10 | 3 つの契約が byte 一致 | V10: r2db の同梱コピーの `9.4.txt` の文に 1 文字足す |
| 11 | 派生 catalog 3 部が再生成済みで `tools/contract_catalog.py --check` が up to date | V11: `M/contract/OPERATION_CATALOG.json` の `contract_version` を 1.15.0 に |
| 12 | 両 peer が data・control の両面で 1.16.0 を宣言し、版の literal が 1.16.0 | V12: `M/control_plane.py` の宣言を 1.15.0 に (`MT/test_control_plane_service.py`:574 の test) |
| 13 | `spec/CONTRACT_HISTORY.md` の引用と Revision note が register を通る | V13: 引用の 1 文字を変える (`test_contract_history_companion_quote_matches_the_contract_value_verbatim`) |
| 14 | `spec/CCR_DISPOSITION.md` に従属判断 21 の段 | V14: 段の頭の `21. **` → `21 **` (`test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition`) |
| 15 | `spec/README.md` の 1.16.0 の段落、CH-ID の訂正の追記、`check_comment_provenance.py --register` が OK | 監査照合 (`git diff` と出力の逐語) |
| 16 | §1.1 の 8 (`reference_wall_clock`) の現物の確かめを、`SJ` の `limit_enforcement` の `file:line` と 1.16.0 の段落の該当句を添えて監督へ上げた | 監査照合 (報告の逐語) |
| 17 | 基点で `1.15.0` を含む追跡ファイルを `git grep -l '1\.15\.0' -- ':!docs/archive' ':!docs/code-history'` で実測し、版の宣言・版の literal と 1.15.0 の文を名指す記述を分けて報告した (後者は変えない)。下の「テスト」の全呼び出しが failed 0・skipped 0 | 監査照合 (集計行の逐語) |
| 18 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト = `tools/dev/pt.py -C .claude/worktrees/<WP-1 の worktree> -- conformance-tests/test_contract.py conformance-tests/test_contract_history_register.py conformance-tests/test_operation_catalog_register.py conformance-tests/test_c29_operation_catalog_url.py conformance-tests/test_c19_client_self_sufficiency.py -q`、`-- r2db-api/tests/test_foundation.py r2db-api/tests/test_control_plane_service.py r2db-api/tests/test_audit_query.py r2db-api/tests/test_denial_details_and_request_id.py -q`、`-- MitateDB-api/tests/test_http.py MitateDB-api/tests/test_control_plane_service.py MitateDB-api/tests/test_audit_query.py MitateDB-api/tests/test_denial_details_and_request_id.py -q`。変異 = `tools/dev/mutate.py "$SP/r42-wp1-mutations.json" -C .claude/worktrees/<WP-1 の worktree>`。

**レビューの観点**: 確定文の言い換えが無いこと (付録の script を再実行して値と照合)。置き場 (§1.1 の 2) と obligations の index。版の追随の漏れと、1.15.0 の文を名指す記述を誤って変えていないこと。

### 2.2 WP-2 — port v1.22 と新条件 (実装担当)

**目的**: 設計 D-7・§6 を実現する。(port の部) 新 primitive と handle の文の数、(ii) の stall 点の統一、docstring の改訂。(新条件の部) 3 vector と positive control、version gate と guard、既存の記述の書き換え。
**読むべき正本**: 設計 D-2・D-7・§6.1〜§6.6・M-8・§12.4、§1.1 の 3・6・7。現物: `CT/adapter.py`:563 (`contract_version_at_least`)・:997-1049 (`IdempotencyHold`・`PlanVerificationHold`、`wait_until_held` は :1021・:1048)・:1810・:1901-1902・:1965-1966、`RC/conformance_adapter_r2db.py`:339-344、`RC/conformance_adapter_r2db_http.py`:893-898、`MC/conformance_adapter_mitatedb.py`:534-545、`MC/conformance_adapter_mitatedb_http.py`:867-873、`R/psycopg_counting.py`・`M/psycopg_counting.py` (`execute_count`)、`CA` §25 の導入 (:3461-3472) と §31 (port 改訂の節の形)、`COND` の C-35 の行 (行の形)。**クラス**: D (`CM`)。**テンプレート**: `ROLES` の 2。

**port の部** (WP-2 の commit):

- 新 primitive (仮称 `hold_after_admission`): 契約の点「rate・concurrency・budget の bound が確定した後、最初の接続取得の前」で止める。`ConformanceAdapter` の `@abstractmethod` + 6 plug (socket の 2 本は http plug の subclass。設計 §6.1)。製品コードに test 用 hook を足さない (X-7)。
- handle: §1.1 の 6。既存 2 primitive の handle にも同じ値。
- (ii) の r2db の 2 実装の stall 点を「`_idempotency_reserve` が戻った後」へ (設計 §6.4 の【追記】)。(iii) は変えない。
- docstring: `hold_after_idempotency_lookup` の 1 文 (`CT/adapter.py`:1902) を改訂し、写し `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md`:374 と `CA`:3491 に【追記】を足す。`hold_after_plan_verification` に「先着が `LIMIT_EXCEEDED` で拒否される」場合を足すかは実装担当が現物で確かめて報告する (裁定は監督)。改訂文は監督が確定文ファイルにしてから複製する (`OC` §1.5 の 35・36)。
- 新条件の test は「held」か「要求の完了」のどちらかを待ち、完了が先なら即座に赤 (`wait_until_held` の 30 s を待たない)。

**新条件の部** (作って保持し、WP-5 の commit に入れる):

- `COND` に行 (Condition は設計 §6.2 を C-35 の行の 5 列の形で英文にし、全文を報告に載せる。確定は監督。Invariants は SI-08・SI-11)、`CH` に節、test `CT/test_c<NN>_<名>.py` (名は実装担当、`@pytest.mark.condition`)。
- 3 vector と positive control は設計 §6.3 の表。(iii) の plan を得る dry run は実要求と同じ budget で、hold を仕掛ける前に済ませる (設計 D-7)。(ii) の再送は budget を外す。
- version gate: 1.16.0 以上を宣言する plug に束縛 (`contract_version_at_least`)。guard: 登録された全 plug が束縛されることを assert (非空振り)。
- 書き換え: `COND`:34 (C-05 の Disclosed scope limits の `execution_ms`)、`COND`:53 (C-24) と `CT/test_c24_request_budget.py`:40-41、旧文は `CH` の該当節へ逐語 (`COND` 冒頭の Update convention)。`CM`:659・:852 (引用の範囲を `_set_timeouts` の def と `SET LOCAL` の組み立て・実行に。実装後の行で取り直す)・:870・:905 (現物と照合してから直す。設計 §11.5 RW-16)・:1023 (V-3 の開示)・:1141、両 peer の「文発行前の拒否」「rollback」の claim。`CM` の断言は WP-3・WP-4 の実測の後に書く (`OC` §1.5 の 34)。
- 実測の時期: 新条件の vector と変異 (28〜35) は WP-4 の commit の後に、WP-1 と新条件の部を `r42` の worktree に載せた状態で行う (変異の対象の検査は WP-3・WP-4 で入る)。

**触ってよいパス**: `CT/adapter.py`、`RC/conformance_adapter_r2db.py`、`RC/conformance_adapter_r2db_http.py`、`RC/conformance_adapter_r2db_socket.py`、`MC/conformance_adapter_mitatedb.py`、`MC/conformance_adapter_mitatedb_http.py`、`MC/conformance_adapter_mitatedb_socket.py`、`R/psycopg_counting.py`・`M/psycopg_counting.py` (計数を peer 側に足すときだけ。足したら同型性の行 `RT/test_audit_query.py`:2425・`MT/test_audit_query.py`:2217 も)、`CA` (版数行と新しい節)、`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (:374 への【追記】だけ)、`CT/test_c<NN>_<名>.py` (新規)、`COND`、`CH`、`CT/test_c24_request_budget.py` (:40-41 だけ)、`CM` (上の行と claim だけ)。触らない: 両 peer の振る舞いのコード、`spec/`、`CT/test_contract.py`、`CT/COLLECTION_FLOOR`。

**完了条件 (19〜39) → 変異** (28〜31 の変異の注入先は WP-3・WP-4 で入る peer の検査。1 つの peer の変異はその peer の PostgreSQL 2 plug の item を test id にする)

| # | 完了条件 | 変異 |
|---|---|---|
| 19 | 実装前に `CT/test_c27_concurrent_same_key.py`・`CT/test_c34_concurrent_plan_precondition.py` の集計行を取った | 監査照合 (集計行の逐語) |
| 20 | 新 primitive が `@abstractmethod` で 6 plug にあり、docstring が契約の点を述べ `port v1.22` の段落を持つ | 監査照合 (`git diff`) |
| 21 | handle が PostgreSQL の 4 plug で放した後の文の数を返し、in-process の 2 plug で None を返す。positive control が 4 plug で「文の数 >= 1」を assert する (B-M5) | V21: PostgreSQL の plug の新 primitive の handle が定数 0 を返す |
| 22 | 既存 2 primitive の handle も同じ値を返す | V22: r2db http の `IdempotencyHold` の値を定数 0 に ((ii) の positive control) |
| 23 | (ii) の r2db の 2 実装の stall 点が `_idempotency_reserve` の後で、C-27・C-34 の集計が 19 と同じ | 監査照合 (`file:line` と集計行) |
| 24 | `hold_after_idempotency_lookup` の docstring の改訂が確定文ファイルと逐語一致、2 文書に【追記】、`hold_after_plan_verification` の扱いを報告した | 監査照合 (`diff` の逐語) |
| 25 | 新条件の test の待ちが「held か完了」で、stall 点の前で拒否される要求 (例 (ii) を `budget.execution_ms = 1` で) で即座に赤になることを 1 回実測した | 監査照合 (実測の出力と所要時間) |
| 26 | `CA` の版数行が 1.22 で、新しい節 (追加の理由、signature、意味、plug ごとの実現の実測、enter 側の計数を足した場所) がある | 監査照合 (`git diff`) |
| 27 | `COND` の新条件の行と `CH` の節があり、`CT/test_conditions_register.py` が緑 | 監査照合 (集計行) |
| 28 | (i): `budget.execution_ms = 1`、保持 100 ms → `LIMIT_EXCEEDED` / `execution_ms`、PostgreSQL の 4 plug で放した後の文の数 0 | V28a: r2db の `_run` と `transaction()` の前の検査を外す。V28b: MitateDB の `_execute` の検査を外す |
| 29 | (i) の positive control: 十分な予算で同じ保持 → 完了し効果が残る | V29: r2db の期限の検査が常に拒否する (r2db の 2 plug の positive control) |
| 30 | (ii): 「stall 点に入った」こと、`LIMIT_EXCEEDED`、行が残らない、budget を外した同 key の再送が新規実行、文の数 0 | V30a: V28a と同じ注入、(ii) の item。V30b: V28b と同じ注入、(ii) の item |
| 31 | (iii): plan は同じ budget の dry run で hold の前に取る。「stall 点に入った」こと、`LIMIT_EXCEEDED`、revision が動かない、文の数 0 | V31a: V28a と同じ注入、(iii) の item。V31b: V28b と同じ注入、(iii) の item |
| 32 | version gate が 1.16.0 以上を宣言する plug だけを束縛し、test module が 1.15.0 の宣言を束縛しないことを自己 assert する (先例 `CT/test_c06_destructive_confirmation.py`:1593-1597) | V32: gate の述語を常に真にする |
| 33 | guard: 登録された全 plug (6) が束縛される | V33: guard が見る束縛の集合を空にする |
| 34 | B を完了ゲートの中の到達時間から決め、値と保持 (B + B/5) と測定値を報告した | 監査照合 (測定値の逐語) |
| 35 | 設計 M-8 の残り: 6 plug で (i)〜(iii) の拒否と stall 点の到達が 100/100、positive control も 100/100 | 監査照合 (集計の逐語) |
| 36 | C-05・C-24 の行と `CT/test_c24_request_budget.py`:40-41 が新条件を指し、旧文が `CH` に逐語で移った | 監査照合 (`git diff`) |
| 37 | `CM` の書き換え (上の行と claim) があり `CT/test_control_mapping_register.py` が緑。変更したファイルごとに `grep -c '<path>:' security/CONTROL_MAPPING.md` の前後の件数を報告した | 監査照合 (`git diff`・件数・集計行) |
| 38 | 新しい試験に skip / xfail が無く、下の「テスト」の全呼び出しが failed 0・skipped 0 | 監査照合 (`git grep` と集計行) |
| 39 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト (port の部) = `tools/dev/pt.py -C .claude/worktrees/r42 -- conformance-tests/test_c27_concurrent_same_key.py conformance-tests/test_c34_concurrent_plan_precondition.py conformance-tests/test_c29_operation_catalog_url.py conformance-tests/test_conformance_docstring_position_refs.py -q`。テスト (新条件の部) = `-- conformance-tests/test_c<NN>_<名>.py conformance-tests/test_c05_limit_declaration_agreement.py conformance-tests/test_c24_request_budget.py conformance-tests/test_conditions_register.py conformance-tests/test_control_mapping_register.py conformance-tests/test_conformance_docstring_position_refs.py -q --durations=0`。変異 = `tools/dev/mutate.py "$SP/r42-wp2-mutations.json" -C .claude/worktrees/r42`。

**レビューの観点**: 文の数の観測が pool の維持と COMMIT / ROLLBACK を数えないこと (設計 §6.4)。空振り (handle が実際に計数を読むか、positive control の assert)。stall 点の位置と C-27・C-34 への影響。製品コードに test 用 hook が入っていないこと (X-7)。

### 2.3 WP-3 — r2db (実装担当)

**目的**: 設計 D-9 の r2db の項を全部実現し、peer の単体テスト (clock の注入。`R/service.py`:176) で固定する。
**読むべき正本**: 設計 D-2・D-5・D-9 (r2db・両 peer の項)・§1.3・§6.6、§1.1 の 5・9、§1.2。現物: `R/postgres.py`:230-231・:234 (`_run`)・:436 (`_acquire`)・:621 (checkout の `SELECT 1`)・:655・:660 (差し替え)・:1117・:1261・:1317・:1419・:1435 (`transaction()`)・:1430 (`_idempotency_reserve`)・:1498・:1554・:1613・:1691・:1701・:1725・:1733・:2202・:2416・:2426・:2649 (`_timeout_ms`)・:2656 (`_set_timeouts`)、`R/limits.py`:99-100、`R/structured.py`:937-938・:1161-1162。**クラス**: D (`CM`)。**テンプレート**: `ROLES` の 2。

**触ってよいパス**: `R/postgres.py`、`R/limits.py`、`R/structured.py`、`RT/` の新規 test 1 ファイル (名は実装担当) と、既存の期限・timeout のテスト (`RT/test_postgres.py`・`RT/test_pg_timeouts.py`) の追随、`CM` (r2db の claim だけ。版は上げない)。触らない: MitateDB、`CT/`、`spec/`。

**完了条件 (40〜55) → 変異** (test id は r2db の単体テスト。検査点が複数あるときは点ごとに 1 entry)

| # | 完了条件 (設計) | 変異 |
|---|---|---|
| 40 | 入口検査 (:1498・:1613) が pool 取得の後・最初の文 (BEGIN) の前へ移り、apply_schema にも同じ位置にある。期限切れの要求は BEGIN を含め文 0 件で拒否 (D-2 (a)、D-9) | V40: 外側の `transaction()` の前の検査を外す |
| 41 | pool の取得に残りを渡し、待ちの超過が `LIMIT_EXCEEDED` / `execution_ms` (U-6 (a)) | V41: 写像を外す (503 に戻る) |
| 42 | 新規接続 (`_acquire` :436、差し替え :655・:660) に残りを渡し、接続の取得の失敗は時計の判定 1 本 (残り < 1 ms なら 413、それ以外は 503。即時の拒否は 503。V-3) | V42a: `_acquire` の判定を外す (常に 503)。V42b: 差し替えの判定を外す |
| 43 | `_run` の前の検査: 2 文目以降の前で期限切れなら次の文を発行しない (D-2 (c)、B-M2) | V43: `_run` の検査を外す |
| 44 | 入れ子の `transaction()` (:1261・:1317・:1419・:1435) の前の検査 (savepoint を開く文。設計 §11.6 N-8) | V44: 検査点ごとに外す (1 点 1 entry) |
| 45 | lock 待ちの後は時計の再検査だけ (再設定しない)。lock 待ちで尽きた要求は次の文の前で拒否 (D-2 (b)、§11.5 RW-10) | V45: 再検査を担う検査を外す (lock 待ちの test) |
| 46 | `_timeout_ms` は残り < 1 ms で `LIMIT_EXCEEDED` を上げ、0 を返さない (D-2) | V46: `max(1, …)` に戻す |
| 47 | 閾値が残り < 1 ms (`R/limits.py`:100 の `clock() > deadline` を改める。U-7) | V47: `clock() > deadline` に戻す |
| 48 | query の SELECT 後の検査 (:1554) が無く、最後の文の後に時計が期限を過ぎても成功 (U-8 (a)、B-M1) | V48: SELECT 後の検査を戻す |
| 49 | 次が pre_commit / COMMIT の点に検査が無い (transact の loop 後 :1701 は store が続く要求だけに残る) | V49: idempotency_key の無い transact の loop 後に検査を戻す |
| 50 | 文の bound (`SET LOCAL` の値) が算出時の残り以下 (義務 (c)、B-M6) | V50: `_timeout_ms` が満額の execution_ms を返す |
| 51 | in-memory backend: 各 operation の前で検査 (1 operation = 1 文)、最後の operation の後の検査 (`R/structured.py`:937-938・:1161-1162) を外し、閾値 < 1 ms (§11.6 N-7) | V51a: 最後の operation の後の検査を戻す。V51b: 閾値を `>` に戻す |
| 52 | 義務 (a): pool・lock の待ちを予算に数える (受理点より遅く始めない) | V52: 期限を pool 取得の後に計算する |
| 53 | `CM` の r2db の claim (義務 (a)・(c)、pool と接続の写像、閾値) が実測と単体テスト名を引く | 監査照合 (`git diff`) |
| 54 | 新しい試験に skip / xfail が無く、下の「テスト」が failed 0・skipped 0。C-29 が緑 | 監査照合 (集計行) |
| 55 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト = `tools/dev/pt.py -C .claude/worktrees/r42 -- r2db-api/tests -q`、`-- conformance-tests/test_c29_operation_catalog_url.py conformance-tests/test_c27_concurrent_same_key.py conformance-tests/test_c24_request_budget.py conformance-tests/test_c05_limit_declaration_agreement.py -q`。変異 = `tools/dev/mutate.py "$SP/r42-wp3-mutations.json" -C .claude/worktrees/r42`。

**レビューの観点**: 検査点が「次に文を発行する点」だけにあり、pre_commit の後に時計の検査が無いこと (設計 D-2)。DB 往復を足していないこと (X-1)。`_timeout_ms` が 0 を返す経路が無いこと。

### 2.4 WP-4 — MitateDB (実装担当)

**目的**: 設計 D-9 の MitateDB の項を全部実現し、peer の単体テスト (test 側の `time.monotonic` の差し替え) で固定する。
**読むべき正本**: 設計 D-2・D-5・D-9 (MitateDB・両 peer の項)・§1.4・§6.6、§1.1 の 5・9、§1.2。現物: `M/backend_postgres.py`:295 (`_execute`)・:452 (`_borrow`)・:467-506 (`request_scope`)・:532-552 (`_retime`)・:555-606 (`_acquire_advisory`)・:1058→1069→1070・:1204→1229→1230・:1372→1382→1383 (schema 3 経路)・:1681-1685 (`_timeout_ms`)・:1687-1698 (`_set_timeouts`)・:1817-1825 (`record_idempotency`)、`M/pool.py`:443-508 (`acquire`)、`M/cell.py`:686-692、`M/backend_sqlite.py`:22-27・:181・:646・:711、`MT/test_r102_request_scope.py`:576、`MT/test_r71_catalog_read_cancel_mapping.py` (合成の `QueryCanceled` の注入の先例)。**クラス**: D (`CM`)。**テンプレート**: `ROLES` の 2。

**触ってよいパス**: `M/backend_postgres.py`、`M/pool.py`、`M/backend_sqlite.py`、`M/cell.py` (期限の経路だけ)、`MT/` の新規 test 1 ファイル (名は実装担当) と既存の期限のテスト (`MT/test_r102_request_scope.py`・`MT/test_pg_timeouts.py`・`MT/test_application_plane_limits.py`) の追随、両 peer に同名のヘルパを置くときは `RT/test_audit_query.py`・`MT/test_audit_query.py` の `_ISOMORPHIC_TARGETS` (Class D)、`CM` (MitateDB の claim だけ。版は上げない)。触らない: r2db の製品コード、`CT/`、`spec/`。

**完了条件 (56〜74) → 変異**

| # | 完了条件 (設計) | 変異 |
|---|---|---|
| 56 | `request_scope` の入口 (pool 取得の後・最初の `SET LOCAL` の前) の検査。期限切れなら idle 接続があっても文 0 件で拒否 | V56: 入口の検査を外す |
| 57 | `_execute` の前の検査 (operation loop・create_collection の複数文の間を含む。D-2 (c)、B-M2) | V57: `_execute` の検査を外す |
| 58 | lock 待ちの後の `_retime` の検査と閾値 (残り < 1 ms。D-2 (b)、U-7) | V58a: `_retime` の検査を外す。V58b: `<= 0` に戻す |
| 59 | `_timeout_ms` は残り < 1 ms で `LIMIT_EXCEEDED` を上げ、0 を返さない | V59: `max(1, …)` に戻す |
| 60 | 文の bound が算出時の残り以下 (義務 (c)、B-M6) | V60: `_timeout_ms` が満額を返す (`test_the_scope_sets_its_timeouts_from_the_deadline_not_the_constructed_value`) |
| 61 | `request_scope` の `SET LOCAL` の `QueryCanceled` / `LockNotAvailable` を `execution_ms` に写す (B-M4) | V61: 503 の経路に戻す |
| 62 | `_retime` の再 `SET LOCAL` の同じ写像 (B-M4) | V62: 503 の経路に戻す |
| 63 | `record_idempotency` の psycopg 例外の翻訳 (B-M4) | V63: 翻訳を外す |
| 64 | pool 待ちの超過は `LIMIT_EXCEEDED`、接続の確立の失敗は時計の判定 1 本 (V-3) | V64: 時計の判定を外す (`PoolConnectFailed` は常に 503) |
| 65 | schema 3 経路の `_write_idempotency_row` が `pre_commit` の前 (store → pre_commit → COMMIT) | V65a・b・c: 経路ごとに順序を戻す |
| 66 | SQLite backend の文の間と DDL の前の検査、閾値 < 1 ms (B-M3) | V66a: 新しい検査を外す。V66b: `_check_deadline` を strict `>` に戻す |
| 67 | SQLite backend の文の bound (例: progress handler。遅い文を期限で打ち切る。V-1) | V67: bound を外す |
| 68 | bound は文の実行中だけ有効で、commit・rollback の前に外す (期限を過ぎた直後の commit が成功。§11.6 N-4) | V68: commit の間も有効にする |
| 69 | read の最後の文の後に時計の検査が無い (U-8 (a)、B-M1) | V69: read の最後の文の後に検査を足す |
| 70 | 義務 (a): pool・lock の待ちを予算に数える | V70: 期限を `_borrow` の後に計算し直す |
| 71 | 両 peer に同名のヘルパを置いたときは `_ISOMORPHIC_TARGETS` の行と同型性テスト。置かないときはその旨を報告 | V71: r2db 側のヘルパに正規化で消えない 1 行差 (置かないときは監査照合) |
| 72 | `CM` の MitateDB の claim (義務 (a)・(c)、SQLite の bound、写像) が実測と単体テスト名を引く | 監査照合 (`git diff`) |
| 73 | 新しい試験に skip / xfail が無く、下の「テスト」が failed 0・skipped 0。C-29 が緑 | 監査照合 (集計行) |
| 74 | 本表に対応の無い行が無い | 監査照合 |

**道具の引数**: テスト = `tools/dev/pt.py -C .claude/worktrees/r42 -- MitateDB-api/tests -q`、`-- conformance-tests/test_c29_operation_catalog_url.py conformance-tests/test_c27_concurrent_same_key.py conformance-tests/test_c34_concurrent_plan_precondition.py conformance-tests/test_c24_request_budget.py conformance-tests/test_c05_limit_declaration_agreement.py -q`、同型性の行を足したときは `-- r2db-api/tests/test_audit_query.py -k isomorphic -q`。変異 = `tools/dev/mutate.py "$SP/r42-wp4-mutations.json" -C .claude/worktrees/r42`。

**レビューの観点**: 予算を過ぎた要求が commit しないこと (設計 §1.5・§12.4 の欠陥)。schema 3 経路で pre_commit の後に文が無いこと。SQLite の bound が commit・rollback に掛からないこと。

### 2.5 WP-5 — 版の flip、完了ゲート、記録と閉止 (監督)

**目的**: 設計 D-6 (B) の最後の 1 commit を作り、完了ゲート・計測・受け入れ監査・閉止を行う。
**読むべき正本**: 設計 D-6・M-8・§12.5、§1.1 の 3、`OC` §1.8 の 55・56、§1.13 の 75、§1.15 の 77、§1.16 の 78・79。**クラス**: D。**テンプレート**: `ROLES` の 6・7。

| 対象 | 書くこと |
|---|---|
| 最後の commit | WP-1 の全変更 + WP-2 の新条件の部 (gate と guard を含む) + 派生 catalog 3 部 + 同梱コピー + 両 peer の版の flip |
| `CM` | 版 3.17 (現物で確かめる)。新条件の Evidence と WP-2〜WP-4 の claim |
| 設計 | v0.11 の註: M-8 の【実測】(B、100/100)、本書の番号の割当。行を消さない |
| `RM` | R-42 の閉止 (行を記録ファイルへ逐語で移し §8.2 に索引行。`OC` §1.16 の 79)、§1 の現状、:39 の契約の版、版数行と回転 |
| 引き継ぎ書 | `docs/work-orders/HANDOVER_<日付>_R42_FABLE.md` (「裁定」節を最終節に)、最新 2 通から外れる引き継ぎ書の移動 |
| 本書 | §5 の記録 |

**完了条件 (75〜85) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 75 | 最後の commit が上表の内容だけを持ち、WP-2〜WP-4 の commit は版を動かしていない | 監査照合 (`git show --stat` の逐語) |
| 76 | WP-2〜WP-4 の各 commit で C-29 が緑 (各 WP の「テスト」の集計行) | 監査照合 |
| 77 | 完了ゲート PASS (§4)、`COLLECTION_FLOOR` の更新 | 監査照合 (集計行) |
| 78 | 性能差分 (§3) | 監査照合 (PERF 行の逐語) |
| 79 | 受け入れ監査 | 監査照合 (判定の集計) |
| 80 | `CM` の版上げと `CT/test_control_mapping_register.py` が緑 | 監査照合 |
| 81 | 台帳の閉止・§1・:39・版数と回転、`python3 tools/dev/ledger.py --check` が緑 | 監査照合 (出力の逐語) |
| 82 | 設計 v0.11 の註 | 監査照合 (`git diff`) |
| 83 | 引き継ぎ書と移動 | 監査照合 (`git status --short`) |
| 84 | `tools/check_doc_refs.py`・`tools/public_value_scan.py <触った全パス>` が緑、`tools/change_class.py <全変更セットのパス>` が D | 監査照合 (出力の逐語) |
| 85 | 本表に対応の無い行が無い | 監査照合 |

## 3. 計測 (性能差分。監督)

1. 引数: `tools/perf_baseline.py --n 100 --warmup 10 --concurrency 1` と `tools/perf_baseline.py --n 15 --warmup 3 --concurrency 32` (設計 §12.5 と同じ。K=32 は D-16 の標本数)。
2. 基準: 設計 §12.5 の表 (M-3 の K=1 の `DBTIME` 行と要求の p50、M-5 の K=32 の `POOL` 行)。実装後を merge 候補で取り、同じ行を並べる。K=1 の閾値は `RM` §0.1.4 の 1。超えたら依頼者へ上げる。
3. 実施条件: 各 run の開始時の 1 分 load average を記録する。他の pytest が無いことを確かめる。出力は `$SP/perf-r42-*.txt`。

## 4. 完了ゲートと受け入れ (監督)

- 完了ゲート: merge 候補の上で `tools/dev/gate.py -C <候補の worktree> --label r42` を単独実行し、集計行だけを正本にする (`OC` §1.6 の 41)。契約ファイルを触るので root suite の完走を完了条件にする (`OC` §1.1 の 10)。B と M-8 の 100/100 (完了条件 34・35) はこの実行の中で測る。
- `CT/COLLECTION_FLOOR` をゲートの実測に更新する。
- pre-commit が緑。commit は `tools/dev/finalize.py`。
- 受け入れ監査 (`evidence-auditor`): 全 WP のコードレビューの後に 1 回。監査対象は本書 §2 の全完了条件。

## 5. 記録 (統合時に監督が埋める)

### 5.1 commit

| WP | worktree (branch) | commit |
|---|---|---|
| WP-1 | session worktree、branch `r42-wp1` (記号名 `r42-wp1`) | WIP 7f23864・2809400・29976a2 (内容として WP-5 の commit に含む。main の履歴に入れない) |
| WP-2 | `r42` (port の部) / `r42-wp1` (新条件の部 WIP 2187190) | a0b5d1d、c14faea、e332c34 |
| WP-3 | `r42` | 5ef1fe1、7b6aced、62136cd (in-memory apply_schema の operation 前の検査は flip の commit) |
| WP-4 | `r42` | d510122、b2658e6、2910a5c |
| WP-5 | `r42` | flip 9d68964、閉止は `finalize.py` の commit (本書 §5 と台帳 v1.161) |

### 5.2 完了ゲート

候補 9d68964 (branch `r42`)、`tools/dev/gate.py -C <session worktree> --label r42`、2026-10-03: **gate: 5231 passed, 2 subtests passed in 509.14s (0:08:29), judge=PASS, label r42, pg_database/pg_roles diff 0**。`COLLECTION_FLOOR` 5029 → 5231。

### 5.3 計測 (§3)

基準 = local main 662d58a (detached worktree `r42-perfbase`)、実装後 = 2910a5c + flip の内容 (`PERFRUN commit=2910a5c-dirty`。9d68964 との差は flip 候補の再確認 1〜5 のコメント・文書だけで、コードは同一)、同日・同引数 (`--n 100 --warmup 10 --concurrency 1`、`--n 15 --warmup 3 --concurrency 32`)。K=1 の p50 の最大 +11.7%・p95 の最大 +8.4%、K=32 の p50 の最大 +4.1%・p95 の最大 +3.2% (閾値 p50 +40% / p95 +50%)、backend_calls 不変。開始時の load average は基準 2.95 / 候補 2.6 台 (1 分)。各 run の開始時に `ps` で他の pytest が 0 件、harness は排他の suite lock を取る。K=1 の p50 の最大 +11.7% は in-process MitateDB query 0.128 → 0.143 ms、backend_calls は全 plug・全 op で不変。訂正註 8。全表 (`PERF` 行の p50 / p95、K=1 は `--n 100`、K=32 は `--n 15`):

| plug | op | K | p50 ms 基準 → 実装後 (差) | p95 ms 基準 → 実装後 (差) | backend_calls |
|---|---|---|---|---|---|
| MitateDB-api | batch | 1 | 0.166 → 0.177 (+6.6%) | 0.179 → 0.194 (+8.4%) | 39.00 → 39.00 |
| MitateDB-api | cross_entity | 1 | 0.124 → 0.133 (+7.3%) | 0.142 → 0.143 (+0.7%) | 18.00 → 18.00 |
| MitateDB-api | mutate | 1 | 0.100 → 0.104 (+4.0%) | 0.125 → 0.115 (-8.0%) | 11.00 → 11.00 |
| MitateDB-api | query | 1 | 0.128 → 0.143 (+11.7%) | 0.158 → 0.153 (-3.2%) | 12.00 → 12.00 |
| MitateDB-api-http | batch | 1 | 2.281 → 2.120 (-7.1%) | 2.396 → 2.303 (-3.9%) | 34.00 → 34.00 |
| MitateDB-api-http | cross_entity | 1 | 1.612 → 1.391 (-13.7%) | 1.720 → 1.554 (-9.7%) | 19.00 → 19.00 |
| MitateDB-api-http | mutate | 1 | 1.254 → 1.177 (-6.1%) | 1.463 → 1.290 (-11.8%) | 14.00 → 14.00 |
| MitateDB-api-http | query | 1 | 1.528 → 1.392 (-8.9%) | 1.659 → 1.495 (-9.9%) | 17.00 → 17.00 |
| MitateDB-api-socket | batch | 1 | 5.993 → 5.498 (-8.3%) | 7.008 → 6.420 (-8.4%) | 34.00 → 34.00 |
| MitateDB-api-socket | cross_entity | 1 | 5.294 → 4.878 (-7.9%) | 6.428 → 5.751 (-10.5%) | 19.00 → 19.00 |
| MitateDB-api-socket | mutate | 1 | 5.349 → 4.628 (-13.5%) | 6.683 → 5.455 (-18.4%) | 14.00 → 14.00 |
| MitateDB-api-socket | query | 1 | 5.412 → 4.893 (-9.6%) | 7.354 → 6.318 (-14.1%) | 17.00 → 17.00 |
| r2db-api | batch | 1 | 0.518 → 0.518 (+0.0%) | 0.709 → 0.701 (-1.1%) | 1.00 → 1.00 |
| r2db-api | mutate | 1 | 0.166 → 0.166 (+0.0%) | 0.209 → 0.209 (+0.0%) | 1.00 → 1.00 |
| r2db-api | query | 1 | 0.113 → 0.116 (+2.7%) | 0.133 → 0.123 (-7.5%) | 1.00 → 1.00 |
| r2db-api-http | batch | 1 | 2.117 → 1.993 (-5.9%) | 2.226 → 2.412 (+8.4%) | 24.00 → 24.00 |
| r2db-api-http | mutate | 1 | 1.931 → 1.826 (-5.4%) | 2.178 → 2.046 (-6.1%) | 20.00 → 20.00 |
| r2db-api-http | query | 1 | 1.856 → 1.700 (-8.4%) | 2.067 → 1.838 (-11.1%) | 18.00 → 18.00 |
| r2db-api-socket | batch | 1 | 5.890 → 5.470 (-7.1%) | 6.141 → 5.596 (-8.9%) | 24.00 → 24.00 |
| r2db-api-socket | mutate | 1 | 5.689 → 5.302 (-6.8%) | 5.922 → 5.464 (-7.7%) | 20.00 → 20.00 |
| r2db-api-socket | query | 1 | 5.738 → 5.158 (-10.1%) | 5.994 → 5.316 (-11.3%) | 18.00 → 18.00 |
| MitateDB-api | batch | 32 | 3.444 → 3.407 (-1.1%) | 3.550 → 3.583 (+0.9%) | 39.00 → 39.00 |
| MitateDB-api | cross_entity | 32 | 1.938 → 2.018 (+4.1%) | 2.491 → 2.164 (-13.1%) | 18.00 → 18.00 |
| MitateDB-api | mutate | 32 | 1.251 → 1.213 (-3.0%) | 1.382 → 1.331 (-3.7%) | 11.00 → 11.00 |
| MitateDB-api | query | 32 | 2.146 → 2.047 (-4.6%) | 2.312 → 2.182 (-5.6%) | 12.00 → 12.00 |
| MitateDB-api-http | batch | 32 | 53.091 → 49.176 (-7.4%) | 57.420 → 51.700 (-10.0%) | 34.00 → 34.00 |
| MitateDB-api-http | cross_entity | 32 | 39.645 → 35.524 (-10.4%) | 45.956 → 38.361 (-16.5%) | 19.00 → 19.00 |
| MitateDB-api-http | mutate | 32 | 34.767 → 31.720 (-8.8%) | 38.102 → 34.121 (-10.4%) | 14.00 → 14.00 |
| MitateDB-api-http | query | 32 | 36.133 → 34.518 (-4.5%) | 40.546 → 41.848 (+3.2%) | 17.00 → 17.00 |
| MitateDB-api-socket | batch | 32 | 174.719 → 161.099 (-7.8%) | 188.941 → 164.021 (-13.2%) | 34.00 → 34.00 |
| MitateDB-api-socket | cross_entity | 32 | 156.344 → 143.109 (-8.5%) | 167.762 → 151.375 (-9.8%) | 19.00 → 19.00 |
| MitateDB-api-socket | mutate | 32 | 149.189 → 137.472 (-7.9%) | 153.747 → 144.701 (-5.9%) | 14.00 → 14.00 |
| MitateDB-api-socket | query | 32 | 154.661 → 142.038 (-8.2%) | 164.524 → 146.156 (-11.2%) | 17.00 → 17.00 |
| r2db-api | batch | 32 | 68.054 → 62.992 (-7.4%) | 97.652 → 89.724 (-8.1%) | 1.00 → 1.00 |
| r2db-api | mutate | 32 | 11.363 → 10.734 (-5.5%) | 17.332 → 16.102 (-7.1%) | 1.00 → 1.00 |
| r2db-api | query | 32 | 1.554 → 1.541 (-0.8%) | 1.714 → 1.763 (+2.9%) | 1.00 → 1.00 |
| r2db-api-http | batch | 32 | 48.641 → 44.765 (-8.0%) | 52.453 → 47.507 (-9.4%) | 24.00 → 24.00 |
| r2db-api-http | mutate | 32 | 43.621 → 39.322 (-9.9%) | 47.024 → 41.381 (-12.0%) | 20.00 → 20.00 |
| r2db-api-http | query | 32 | 41.323 → 37.725 (-8.7%) | 51.162 → 40.538 (-20.8%) | 18.00 → 18.00 |
| r2db-api-socket | batch | 32 | 166.255 → 154.746 (-6.9%) | 174.473 → 158.078 (-9.4%) | 24.00 → 24.00 |
| r2db-api-socket | mutate | 32 | 159.431 → 148.367 (-6.9%) | 167.419 → 155.397 (-7.2%) | 20.00 → 20.00 |
| r2db-api-socket | query | 32 | 155.715 → 146.377 (-6.0%) | 165.176 → 156.195 (-5.4%) | 18.00 → 18.00 |

### 5.4 受け入れ監査と閉止

受け入れ監査 (`evidence-auditor`、2026-10-03、対象 9d68964 + 閉止の記録): 完了条件 85 件中 充足 82・未充足 1 (75: flip の commit に WP-3 の訂正 (in-memory apply_schema の operation 前の検査) が入る — 訂正註 10 で読み替え)・証拠不足 2 (81・84 — 下の逐語で充足)。主張と実測の差 4 件 (A1〜A4) と観察 1 件は引き継ぎ書 `docs/work-orders/HANDOVER_20261003_R42_CLOSE_FABLE.md` の「裁定」節。

- 81: `tools/dev/ledger.py --check` → `ledger --check: GREEN rows(8.1)=24 rows(8.2)=98 archive_sections=98`
- 84 (変更セット 71 パス = `git diff --name-only 662d58a` + 作業ツリー): `check_doc_refs OK: 0 dangling references` / `# mode=tree files_scanned=71 total_flagged=0` / `class=D conformance_required=true`
- 閉止の commit は `tools/dev/finalize.py` (`--tools-tests`) で行い、main へ `--no-ff` で merge した (SHA は `git log` が正)。

## 6. 訂正註 (本文は書き換えない。`OC` §1.8 の 57)

1. **【訂正註 2026-10-03 (WP-1〜WP-5 の実施)】worktree の名。** §1.1 の 10 (d) と §2.0 の `.claude/worktrees/r42-wp1` / `.claude/worktrees/r42` は記号名として扱った。実体は作業チャットの session worktree (`.claude/worktrees/` 配下) で branch `r42-wp1` と `r42` を切り替えた (subagent の他 worktree への書き込みが harness に拒否されるため。`.claude/worktrees/r42` は 662d58a で畳み、branch は残した)。
2. **【訂正註 2026-10-03】番号と版。** 新条件 = **C-36**、`CA` の新節 = **§32 (v1.22)**、`CM` の版 = **3.19** (§0 の見込み 3.17 は R-30・R-120 が先に使った)。WP-2 の port の部の commit (`a0b5d1d`) では `CA` が C-36 を名指すと `tools/check_doc_refs.py` が CONDITIONS の行の無い中間 commit で赤になるため「C-35 の次。番号は版の flip の commit で付く」と書き、flip の commit で C-36 に戻した (設計 D-7 が番号を書かないのと同じ理由)。
3. **【訂正註 2026-10-03】WP-1 の取り込み方。** §1.1 の 10 (d) の「WIP commit を WP-5 の最後の 1 commit で統合する」は、merge commit ではなく内容として取り込む (`git diff 2fdc894 r42-wp1 | git apply`)。merge で取り込むと、挙動の無い状態で版を flip した commit が main から到達可能になり §1.1 の 3 と完了条件 75 が字義どおり成り立たない (WP-1 レビュー A-1)。`r42-wp1` の 4 commit (7f23864・2809400・29976a2・2187190) は main の履歴に入らない。
4. **【訂正註 2026-10-03】触ってよいパスの拡張 (監督裁定)。** WP-2: 両 peer の `tests/test_r79_prepared_stats.py` (`txn_open_count` を単独で殺す単体テスト。§1.5 の 33)。WP-3: `docs/code-history/r2db-api/` (companion。`structured.md` 新設 CH-0552〜CH-0564)、`RT/test_foundation.py`・`RT/test_l1_details_vocabulary_ast_scan.py` (追随。§1.5 の 40b)。WP-4: `MT/test_application_audit.py`・`MT/test_l1_details_vocabulary_ast_scan.py`・`MT/test_limit_class_vocabulary.py` (追随)、`M/audit_hook.py` (docstring のみ。CH-0567)、`docs/code-history/MitateDB-api/` (CH-0565〜0567、CH-0337 の訂正)。
5. **【訂正註 2026-10-03】完了条件 51 の列挙漏れ。** in-memory backend の「最後の operation の後の検査」は `R/structured.py` の query・transact の 2 点に加え apply_schema にもあり (基点 :1788)、3 点とも外した。apply_schema は入口 (idempotency の照会の前) と operation の直前 (plan 照合の後) の 2 点で検査する (D-2 (c)。変異 V51g〜V51j)。
6. **【訂正註 2026-10-03】V28 / V31 の注入。** 「検査を外す」は「その経路で最初の文の前にある検査すべて」と読む: r2db は `_timeout_ms` の拒否 + 外側 `_transaction` 3 点 + `_run` の検査、MitateDB は `_execute` の `_check_budget` + `_timeout_ms` の拒否 (V28b)。V30 / V31 は helper の検査だけで足りる (WP-2 レビュー A F2)。V28a2 / V28b2 (bound を残して文の数で赤) を足した。
7. **【訂正註 2026-10-03】完了条件 27・38 の「緑」。** `CT/test_conditions_register.py::test_every_executable_condition_has_a_marked_test` は一部の file だけを集める呼び出しでは構造上赤になる (基点 main でも同じ)。27・38 の「緑」は完了ゲート (root suite) で示す。
8. **【訂正註 2026-10-03】§3 の基準。** 性能差分の基準は flip 直前の統合 branch の commit (2910a5c) ではなく local main (662d58a。R-42 の挙動が入る前) を同じ日・同じ引数で測った値とした。2910a5c は WP-3・WP-4 の挙動を既に含み、flip の commit は契約文・宣言・conformance だけなので、2910a5c との差分は挙動の差を測らない。
9. **【訂正註 2026-10-03】M-8 の 100/100 の取り方。** 完了ゲートの中では 1 回しか走らないので、完了条件 34・35 は実測の起動が scratchpad の loop (6 plug × 100 回、burner で負荷を掛ける) で測った (`CA` §32.2)。(i)(ii) は in-memory apply_schema の operation 前の検査を足す前の測定、(iii) は足した後の再測。
10. **【訂正註 2026-10-03】flip の commit の中身 (完了条件 75、§1.1 の 3)。** flip の commit (9d68964) には §2.5 の表の内容に加え、WP-3 の訂正 (in-memory `apply_schema` の operation 直前の期限検査: `r2db-api/src/r2db_api/structured.py`、`r2db-api/tests/test_expired_request_checks.py`、`docs/code-history/r2db-api/structured.md`) が入る。この訂正は flip の内容 (C-36 の (iii) が in-process plug に束縛される状態) を載せて初めて測れた実測 (M-8 の (iii) r2db-api 0/100) で見つかり、同じ commit で直した。D-6 (B) の目的 (挙動の無い 1.16.0 の宣言が main から到達できない) は保たれる (662d58a〜2910a5c の 10 commit は 3 部とも 1.15.0 で C-36 の file も無い)。版に依らない挙動なので別 commit にもできたが、分けなかった (受け入れ監査 75、監督裁定)。

## 付録 — 確定文の抜き出し script

確定文は、設計 §9.1 の 2 段落・§9.2・§9.4 の引用 (`> ` の行) と §9.3 の json の塊を、`1.15.0` → `1.16.0`、`1.14.0` → `1.15.0`、`subordinate ruling 20` → `subordinate ruling 21` (json の `"subordinate_ruling": 20` → `21` を含む) の置換だけで写したものである。手で打ち直さない。scratchpad は次のチャットから読めないので全文を載せる。再生成: script を `$SP/r42-fixed-text/extract.py` に保存し、worktree を cwd にして `python3 "$SP/r42-fixed-text/extract.py" . "$SP/r42-fixed-text"`。

```python
#!/usr/bin/env python3
"""Extract the confirmed R-42 contract text from
docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md section 9 (requester-confirmed
2026-10-03), substituting only 1.15.0 -> 1.16.0, 1.14.0 -> 1.15.0 and
subordinate ruling 20 -> 21 (design v0.10 version line).

usage: python3 extract.py <repo root> <output dir>
writes 9.1-1.txt, 9.1-2.txt, 9.2.txt, 9.4.txt (each = the quoted paragraph,
no trailing newline) and 9.3-entry.json (the entry text, no trailing newline).
"""
import json
import sys
from pathlib import Path

DESIGN = "docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md"
SUBSTITUTIONS = (
    ("1.15.0", "1.16.0"),
    ("1.14.0", "1.15.0"),
    ("subordinate ruling 20", "subordinate ruling 21"),
    ('"subordinate_ruling": 20', '"subordinate_ruling": 21'),
)
HEADINGS = ("### 9.1 ", "### 9.2 ", "### 9.3 ", "### 9.4 ", "## 10. ")


def substitute(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    assert "ruling 20" not in text and "1.14.0" not in text, text[:80]
    return text


def sections(lines: list[str]) -> dict[str, list[str]]:
    starts = [next(i for i, line in enumerate(lines) if line.startswith(h)) for h in HEADINGS]
    assert starts == sorted(starts), starts
    return {h: lines[a + 1:b] for h, a, b in zip(HEADINGS[:4], starts, starts[1:])}


def quotes(body: list[str]) -> list[str]:
    return [line[2:] for line in body if line.startswith("> ")]


def main() -> None:
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    sec = sections((root / DESIGN).read_text(encoding="utf-8").splitlines())
    s91 = quotes(sec["### 9.1 "])
    s92 = quotes(sec["### 9.2 "])
    s94 = quotes(sec["### 9.4 "])
    assert (len(s91), len(s92), len(s94)) == (2, 1, 1), (len(s91), len(s92), len(s94))
    body93 = sec["### 9.3 "]
    begin = body93.index("```json") + 1
    end = body93.index("```", begin)
    entry = substitute("\n".join(body93[begin:end]))
    parsed = json.loads(entry)
    assert parsed["version"] == "1.16.0" and parsed["subordinate_ruling"] == 21, parsed
    assert len(parsed["unconditional"]) == 4 and parsed["conditional"] == [], parsed
    out.mkdir(parents=True, exist_ok=True)
    files = {"9.1-1.txt": s91[0], "9.1-2.txt": s91[1], "9.2.txt": s92[0], "9.4.txt": s94[0]}
    for name, text in files.items():
        (out / name).write_text(substitute(text), encoding="utf-8")
    (out / "9.3-entry.json").write_text(entry, encoding="utf-8")
    print(f"wrote 4 paragraphs and the obligations entry to {out}")


if __name__ == "__main__":
    main()
```

起草時の出力の sha256 (設計 v0.10、`925760f` から生成。再生成の照合に使う):

```text
f79063db2a4aa353e3bd4de1241bf224cb0c3829711c4e450a81d6e0d50d49b0  9.1-1.txt
4084f59fd2f83953ef7bfae8292c0161bf7c28395093803430cfa4d043dad3ad  9.1-2.txt
ec2e7a8d78d7cfa4bd8e0209f7090a5e5085fc00e5e8435d44b8e94fe74c1335  9.2.txt
7eba8cbe7bcc06259e9dbff9daa815de9c85a3169ddb7624891b51e9378f3281  9.3-entry.json
345c7e9eb54dcd207d463dbba833552f2cdbc6a40cb628c4b6c59461455798db  9.4.txt
```

4 つの引用は、設計 v0.9 の §9 として依頼者が確定した文 (設計 §10 末尾) と置換の前の段階で逐語一致する (起草時に照合)。
