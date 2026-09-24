# 設計メモ — 遅い call 段テスト 20 件の作り替え (R-105)

## 0. 版数・位置づけ

- **v0.2 (2026-09-24)。** v0.1 からの変更: 設計レビュー 1 回 (§4) の 9 件を反映 (D-1 の値の根拠、両 plug の一致の固定、r2db の無裏打ちと C-09 の余裕、D-5 のガードの選び方と cache の型)。
- **v0.1 (2026-09-24)。** 基点 local main `63bb9bf`。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-105 (規模 M、Class C)。作業指示書 `docs/work-orders/WORK_ORDER_R105_SLOW_CALL_TESTS_V1.md`。
- 運用条件 §1.6 の 44 (時間を食う vector は構成値に比例しない形へ) と 44a (対象は `slowest 25 durations` に繰り返し現れる vector) の適用。R-34 (負荷依存 timing テストの Event 同期化、2026-09-08 閉止) の後継。
- 出所: 依頼者指示 2026-09-24「新しいチャットで、提案通りに進めて」(`docs/work-orders/HANDOVER_20260924_FABLE5.md` §3 の 1)。

## 1. 時間の源 (監督再読で確定。file:line は基点 main)

対象 = 完了ゲート (label r86、2026-09-24) の上位 25 のうち 20 件 = 5 関数 × 4 PostgreSQL adapter (r2db-api-http / -socket、MitateDB-api-http / -socket。socket plug は http adapter の subclass で同 process、同じ宣言値)。

| 関数 | ゲート (4 adapter 合計) | 単独 (同、`pt.py … --durations=0`、log `pt 20260924-123120`) | 時間の源 | 出所 |
|---|---|---|---|---|
| `test_c25_result_request_id` | 55.5 s | 50.2 s | `_find_audit_event_by_request_id` が **宣言 lag (11,000 ms) が経過するまで** 指数 backoff で poll。audit_query は `recorded_at < now − visibility_lag_ms` の行しか返さないので、lag 未満で見つかることはない | `conformance-tests/test_c25_result_request_id.py:203-208`、`:355` (deadline = lag + 2000)。reader 側の閾値: `r2db-api/src/r2db_api/audit_query.py:306`、`MitateDB-api/src/mitatedb_api/audit_query.py:284` |
| `test_c27_same_digest_executes_once` | 47.9 s | 46.6 s | `_count_execution_audit_events` の `poll_interval_s = max(0.3, lag_s)` = **11 s を 1 回 sleep** | `conformance-tests/test_c27_concurrent_same_key.py:266-268`、`:291` |
| `test_c09_v1_fail_closed_events_are_observable_through_audit_query` | 45.5 s | 44.8 s | `time.sleep(audit_visibility_lag_ms()/1000)` = **11 s** | `conformance-tests/test_c09_audit_evidence.py:392` |
| `test_c09_v2_no_forbidden_field_key_or_reusable_secret_value_appears` | 44.7 s | 44.3 s | 同上 | `conformance-tests/test_c09_audit_evidence.py:473` |
| `test_c05_v2_declaration_and_position_agree` | 49.4 s | 22.0 s | 9 driver がそれぞれ isolated surface を provision (5 往復) し、`_drive_requests_per_minute` だけが isolated profile の `requests_per_minute=50` に比例して ~50 往復。**sleep・poll は無い**。1 adapter あたり実 HTTP/socket 往復 ≈ 130〜160 回で、ゲート負荷下で 2〜3 倍に伸びる | `conformance-tests/test_c05_limit_declaration_agreement.py:395-483`、`:755-765`; `r2db-api/conformance/conformance_adapter_r2db.py:162`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py:1116` |

in-process adapter (lag 0) では同じ 4 関数が 0.3〜0.9 s である (同 log)。**16 件 (C-25/C-27/C-09 v1・v2 × 4) の時間はすべて 4 PostgreSQL plug の宣言値 `audit_query.visibility_lag_ms = 11,000 ms` に比例する**。

宣言値の出所 (2 peer で異なる):

- r2db http plug: adapter が **定数で宣言** — `DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS + DEFAULT_AUDIT_IDLE_TIMEOUT_MS + VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` = 5000+5000+1000 (`r2db-api/conformance/conformance_adapter_r2db_http.py:1483`)。writer role に role-level timeout は **無い** (migration `0008` を流さない。Q4 設計 §3.11 の 4「r2db HTTP plug は宣言表の読み出し経路を通らない」。`r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py::test_http_conformance_adapter_audit_writer_connection_has_no_explicit_session_override` がこれを固定)。
- MitateDB http plug: peer の composition root が **`pg_db_role_setting` から導出** (`MitateDB-api/src/mitatedb_api/control_composition.py:241`、`platform_declarations.derive_visibility_lag_ms` = max(statement+idle)+1000)。adapter の bootstrap が流す `0007_platform_declarations.sql:98` が api / controlplane role に 5000/5000 を置く。`MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py:118-119` が 5000/5000 を固定。

両 peer の `tests/test_audit_query.py` (ゲート上位 25 のうち 2 件):

- MitateDB `test_in_memory_and_postgres_audit_query_semantics_have_parity` 11.35 s: `pg` fixture が `_postgres_harness(control_platform)` を既定 (5000/5000 → 11,000) で呼び `time.sleep(11.3)` (`MitateDB-api/tests/test_audit_query.py:161-162`、`:461`)。r2db の同名テストは既定 200/200 (lag 1,400) で 1.7 s (`r2db-api/tests/test_audit_query.py:339-340`)。
- r2db `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` 10.0 s: `_isomorphic_symbol_source` が 156 行 × 2 側で毎回 `read_text` + `ast.parse` (`r2db-api/tests/test_audit_query.py:3337-3338`; MitateDB `:3110-3111`)。構成値比例ではなく再解析の非効率。

## 2. 決定

### D-1 4 PostgreSQL plug の宣言 lag を conformance 配備の値 4,000 ms にする (11,000 → 4,000)

- conformance 配備の writer timeout を **statement 1,000 ms / idle_in_transaction 2,000 ms** とし、両 http adapter に同名の module 定数 `CONFORMANCE_AUDIT_STATEMENT_TIMEOUT_MS = 1000` / `CONFORMANCE_AUDIT_IDLE_TIMEOUT_MS = 2000` を置く (同型性表には載せない。§1.5 の 40b、集合の増減は Class D)。宣言 lag = 1000 + 2000 + `VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` = 4,000。両 peer の新規テストは定数の和との一致に加えて **リテラル 4000** との一致を assert する。MitateDB 側の第 3 の assert (catalog 導出 = 宣言) は、adapter の宣言も test の再計算も同じ catalog 行を同じ関数で読むので adapter 編集では単独で赤にできない (両辺同源。コードレビュー指摘 2)。完了条件 2 の裏づけは、role の値を動かす変異 (M2 / M3) が第 1 assert (定数和) で赤になることと、導出そのものが peer の composition root の既存経路であること (両辺同源の穴を塞ぎ、片 peer の定数だけが動いて 2 plug の宣言が割れる事態を赤にする。同型性表への登録 = Class D は避ける)。
- **r2db http adapter**: `:1483` の定数を conformance 定数の和に替える。role-level timeout は今までどおり置かない (Q4 §3.11 の 4 を変えない。上記固定テストはそのまま緑)。宣言値の性格は現状と同じ「adapter 自身の配備値」であり、r2db の peer テスト harness (`_postgres_harness` の 200+200+1000) と同じ形。
- **MitateDB http adapter**: bootstrap で `0007` の後に api / controlplane role へ `ALTER ROLE … SET statement_timeout = '1000ms'` / `idle_in_transaction_session_timeout = '2000ms'` を adapter 自身の admin 接続で発行する (`ops set-platform-timeouts` / `tests/control_plane_harness.set_role_timeouts` と同じ SQL 形。tests からは import しない)。peer の composition root が catalog から 4,000 を導出する — 導出経路は現状のまま。
- 値が効く先 (MitateDB のみ): api role (`PostgresCredentialRegistry` の credential 照合と `PostgresApplicationAuditSink` の `application_audit` 書込み、`conformance_adapter_mitatedb_http.py:1022-1028`) と controlplane role (control-plane の台帳更新と `append_audit`、`control_plane.py:1674-1740` の `unit_of_work`) が **platform DB** で流す文と tx。現行は `0007` の 5,000/5,000 で、statement は 5 倍の締め付けになる。C-27 の A の保持は application DB の runtime role 上の advisory lock (`backend.py:479-519`) で、runtime / developer role は `0013` の statement 5,000 のまま、idle は cluster 既定のまま — **本値の対象外**。application の provisioning (CREATE DATABASE) は adapter が provision role の psql で tx の外で行う (`conformance_adapter_mitatedb_http.py:1297`、`:451`)。
- 値の根拠: platform DB の tx は文の間に subprocess や外部待ちを挟まない ms 単位の unit_of_work だけなので idle 2,000 は十分。statement 1,000 は単行〜数十行の INSERT / SELECT に十分だが、ゲート負荷 (-n 5、同一ローカル cluster) 下の checkpoint 停止は静的に排除できない。**計測 (WP-1 完了条件 4 の conformance 全体 1 回 + C-09 v1/v2 の 2 回) で timeout 起因の赤、または監査 event が期限内に現れない赤が 1 件でも出たら、statement を 2,000 (lag 5,000) に上げて本節に実測とともに記す (裁定は監督)。**
- r2db http plug の宣言は現状 (11,000) も 4,000 後も role / session の裏打ちを持たない (性格は不変、後から古い `recorded_at` の行が割り込める余裕が 7 秒縮む)。C-09 v1 / v2 は `sleep(宣言 lag)` ちょうどで読む唯一の vector (C-25 は +2,000 ms、C-27 は +15 s の余裕)。v1 の fail-closed event と v2 の credential 発行 event はどちらも要求の tx 内で commit されるので lag 内に見えるはずだが、静的には排除できないので完了条件 4 で 2 回回す。
- 見込み: C-25 ≈ 5.8 s (backoff の刻みで lag を 1〜2 s 超える)、C-27 ≈ 4.6 s、C-09 ≈ 4.2 s → 16 件 ≈ 75 s (単独)。C-05 と合わせ 20 件 ≈ 97 s (前 207.9 s)。**目標値は置かず実測を §5 に書く**。

### D-2 テストの待ち方は変えない

C-25 / C-27 / C-09 は既に「宣言 lag に従って待つ」形であり、audit_query が lag 未満の行を返さない以上、Event / 条件変数や短い間隔の poll に置き換えても lag より早く終われない。テスト本体は触らず、C-25 の註釈 (`test_c25_result_request_id.py:339-348`「BOTH http plugs declare 11000 on this deployment」) だけを事実に合わせて書き換える。

### D-3 C-05 v2 は作り替えない (観察として残す)

rpm driver の ~50 往復だけが構成値比例で、残り ~100 往復は 9 driver の provisioning と各 driver の本質的な N/N+1 境界駆動。`requests_per_minute` を下げると isolated surface を共有する他の消費者 (schema_objects driver は 1 分内に 20+ 往復) を壊しうるし、driver ごとの limits 上書きは port (`isolated_application_surface()`) の版上げを要する。利得 (単独 22 s のうち数 s) が費用に見合わない。

### D-4 MitateDB `tests/test_audit_query.py` の `pg` fixture を r2db と同じ「小さい timeout 対」にする (Class B)

`pg` fixture が `_postgres_harness(control_platform, audit_statement_timeout_ms=1000, audit_idle_timeout_ms=1000)` を渡す (同ファイルに既にある呼び方)。lag 導出は catalog から実測される (harness の設計どおり)。`pg` の唯一の lag 依存の消費者 (parity テスト) は `pg.visibility_lag_ms` を読み戻して待つので、seed を下げても観測は変わらず待ちだけ縮む (受け入れ監査 2026-09-24 が「消費者は明示値を持つ」という v0.2 の理由付けを訂正)。実装担当が同ファイル全体を回して確認する。

### D-5 `_isomorphic_symbol_source` の解析結果を path ごとに cache する (両 peer 同一本体、Class C)

module-level の cache を置き、`read_text` + `parse` を path ごとに 1 回にする。**鍵は絶対 path** (`peer_root / relative_path`) — relative path だけを鍵にすると自 peer の tree を sibling 側にも返し、同型性テストが自分自身との比較になって恒久に緑になる (最大の危険)。この危険を赤にするガードテストを両 peer に置く: **両 peer で relative path が文字列として同一の行** (例: `tests/test_audit_query.py` の `_postgres_harness` — 両 peer に同名の module-level 関数として存在し、本体は peer ごとに異なる。`_ISOMORPHIC_TARGETS` は `AnnAssign` で `_isomorphic_symbol_source` の matcher (`Assign` のみ) が拾わず `None` を返すので使えない — 実装で判明、コードレビュー観察 (c)) の symbol について、自 peer と sibling の `_isomorphic_symbol_source` の返り値が異なることを assert する。path が両側で異なる行 (src 系) を選ぶと鍵の誤りが衝突を起こさず、ガードが空振りする。cache は `dict[Path, tuple[str, _ast.Module]]` (末尾の `get_source_segment` が `source` を要するので、文字列も一緒に持つ)。同 helper は同型性表の行 (`r2db-api/tests/test_audit_query.py:2415`) なので、両 peer に同一本体で入れ、既存の同型性テストが一致を固定する。

### 却下した代替案

- **宣言 lag を 0 にする** (in-process plug と同じ): 4 PostgreSQL plug の keyset paging の安定性を語る宣言が空になる。C-25 の註釈が「http plug の lag は network + buffering の性質」と記す現状の意味を捨てる。
- **r2db http adapter にも ALTER ROLE を置く**: Q4 §3.11 の 4 とその固定テストに反する。r2db の宣言値は今も定数であり、定数を下げるだけで目的を達する。
- **C-25 / C-27 / C-09 の poll を Event / 条件変数へ**: audit_query の lag 閾値により lag より早く終われない (D-2)。
- **`requests_per_minute` の isolated 値を下げる**: D-3。
- **conformance-tests 側で lag の閾値を回避する読み方**: 契約の `completeness_note` (lag 未満の行は返らない) を検査対象から外すことになり、C-25 (3) の検査を弱める。

## 3. 保つ検査 (Condition 文は `conformance-tests/CONDITIONS.md` から逐語)

| 条件 | Condition (逐語) | 作り替え | 保たれる検査 |
|---|---|---|---|
| C-25 | Every successful result a peer declaring contract 1.7.0 returns carries `request_id`; distinct executions carry distinct values (a request answered from an idempotency record is not a new execution and carries the original execution's own value); and where `audit_query` is available, the value a mutation returned is the value that mutation's own audit events carry. | D-1 (宣言値の変更のみ)、D-2 (註釈) | (3) の相関は同じ helper が同じ宣言 lag + 2000 ms を待って同じ event を探す。lag の値が変わるだけで、宣言 lag に従うという検査の形は不変 |
| C-27 | A peer declaring `idempotency` serializes concurrent requests that carry the SAME key: at most one of them executes, the other is answered only after the first commits -- as a replay carrying the first execution's own `request_id` when the two requests' digests agree, and as `CONFLICT` naming `idempotency_key` when they differ (a first attempt that fails leaves no record, so the second is a new request and executes); and two concurrent requests carrying DIFFERENT keys against a deployment already one row below its `idempotency_entries` bound leave that bound intact, one of them refused with `LIMIT_EXCEEDED` naming that class. | D-1 | 「1 回だけ実行」の audit 側の証拠は同じ helper が宣言 lag 後に数える。idle 2,000 ms は A の保持時間を十分に超える (超えなければ A の tx が切られて赤になる = 検査は弱まらず、値を上げる) |
| C-09 | Security events are attributable and immutable to application callers; secrets, SQL, and row values are absent. Audit query requires control/audit authority. | D-1 | v1 / v2 は同じ `sleep(宣言 lag)` の後に同じ集合を読む。宣言 lag に従う形は不変 |
| C-05 | All applicable resource classes have finite, discoverable bounds and over-bound requests terminate deterministically. | 変更なし (D-3) | — |

D-4 / D-5 は peer テストであり conformance の Condition に載らない。D-5 は既存の同型性テストが両 peer の本体一致を固定し、ガードテストが鍵の誤りを固定する。

## 4. 設計レビュー (1 回、Class C、2026-09-24)

指摘 9 件、すべて同じ変更セットで文書に反映 (v0.2): (1) 変異 M4 が同源で赤にならない → ALTER の idle 値をリテラルにする変異へ; (2) D-5 のガードは path 同一の行から選ぶ; (3) statement 1,000 は api role の全 SQL に効く → 根拠と上げ条件を広げた; (4) idle の根拠が効かない role の話 → platform DB の tx で書き直した; (5) 両 plug の一致をリテラル 4000 で固定; (6) r2db 無裏打ちと C-09 の余裕 0 → 明記し 2 回回す; (7) 検証集合が狭い → conformance 全体 1 回; (8) C-25 の註釈は L-1 を逐語で残し追記、行数固定を外す; (9) cache の型を `tuple[str, Module]` に。報告: scratchpad `review-r105-design.md` (引き継ぎ書の裁定節に全件)。クラス引き上げなし。

## 5. 実施記録 (2026-09-24、監督)

- 実装: WP-1 / WP-2 / WP-3 すべて (作業指示書 §7.2)。コードレビュー 4 件はすべて同じ変更セットで直した (§7.1 の訂正註)。
- **20 件の call 時間 (単独、`pt … --durations=0`)**: 前 **207.9 s** (log `pt 20260924-123120`) → 後 **99.7 s** (log `pt 20260924-130733`)、**−52%**。内訳 (4 adapter 合計): C-25 50.2 → 25.8 s、C-27 46.6 → 18.6 s、C-09 v1 44.8 → 16.8 s、C-09 v2 44.3 → 16.3 s、C-05 v2 22.0 → 22.1 s (不変、D-3)。
- **完了ゲート**: 前 `4018 passed, 2 subtests passed in 521.02s (0:08:41)` (label r86) → 後 **`4022 passed, 2 subtests passed in 499.13s (0:08:19)`** (label r105、judge=PASS、残骸差分 0)。壁時計 **−21.9 s (−4.2%)**。監査後に MitateDB `pg` fixture の註釈だけを直して再実行 (label r105b): **`4022 passed, 2 subtests passed in 486.51s (0:08:06)`**、judge=PASS、残骸差分 0 (commit の正本)。テスト +4 (新規: 両 peer の宣言 lag テスト 2、両 peer のガードテスト 2)。
- **`slowest 25 durations` の前後 (ゲート負荷下)**: 前は 25 件すべてが本件の 20 件 + audit_query 2 件 + C-14 / C-03 (5.9〜16.0 s)。後の上位は C-05 v2 × 4 (9.1〜17.2 s、不変) が占め、C-25 × 4 は 4.8〜8.0 s (前 13.1〜14.6)、C-27 × 4 は 4.7〜5.0 s (前 11.8〜12.1)、C-09 v1 は 4.4〜4.7 s (前 11.1〜11.6)、C-09 v2 は 4.3 s 以下 (4 件中 3 件は上位 25 の外)、r2db isomorphism 5.6 s (前 10.0)、MitateDB parity は上位 25 の外 (前 11.4)。ゲート負荷下の 20 件合計は前 243.1 s → 後 ≈ 130 s (上位 25 の外の 4 件を 4.3 s と置いた上限)、**≈ −47%** — 単独では半分以下、ゲートでは C-05 v2 が負荷で 2〜3 倍に伸びるため半分に僅かに届かない (C-05 は D-3 で作り替えない)。
- 値の上げ条件 (D-1) は発動しなかった: conformance 全体 1 回 (1104 passed in 606 s)、C-09 v1/v2 2 回、完了ゲート -n 5 のいずれにも timeout 起因の赤・監査 event 不在の赤は 0。
- 変異: M1〜M4' (5 件、監督再実行 `mutate 20260924-134610`、M1 は値 assert `5000 == 4000` で赤) — `mutate: 5 mutations, 5 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged`; M5 / M6 / M5b (3 件、`mutate 20260924-134638`) — `mutate: 3 mutations, 3 as expected, restores verified 2/2 files (sha256 x2)`。
- WP-3 の前後はゲート同士では 10.03 → 5.62 s (−44%)、単独では 2.60 s。WP-2 はゲートで上位 25 の外 (≤ 4.32 s)、単独 3.34 s。
- 受け入れ監査 (2026-09-24): 完了条件はすべて充足 (WP-1/2 は変異の裏づけが間接 = 上記の限界)。未充足 2 件 (本節と作業指示書 §7.2 の空欄 → 埋めた; MitateDB `pg` fixture 註釈の理由付け → 直した)、証拠不足 2 件 (ゲート基準の「半分」= 上記のとおり閾値 121.5 s を挟む; mutate の集計行 → 本節に転記)。観察 3 件は引き継ぎ書の裁定節。
- 記録: 台帳 R-105 行、作業指示書 §7、引き継ぎ書 `docs/work-orders/HANDOVER_20260924_FABLE6.md`。
