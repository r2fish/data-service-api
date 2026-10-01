# 作業指示書 — R-102 MitateDB のデータ面の application 単位の直列化 (Change Set Manifest)

## 0. 版数・位置づけ

- **v1.0 (2026-10-01)。** 起草。未発注・未 commit。
- 設計の正本は `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` **v0.5** (以下「設計」。依頼者裁定済み = 設計 §11.1、確定)。本書は設計の決定 (D-1〜D-8)・却下案 (設計 §4 の (乙)〜(戊)、D-3 の却下 (b)(c))・背景を写さず節番号で指す (`RM` §9 の 9)。逐語は §1 の監督裁定、§2.5 の lock の順序表 (設計 D-3)、§3 の判定規則 (設計 §8) だけ。
- 台帳 `RM` §8.1 の **R-102** (`RM`:462)。G-4 の終了条件の 1 つ (`RM`:40)。
- 基点: local main の R-119 merge 後の先頭 (起草時点 `ddf9c73`。契約 1.13.0、`CM` 3.13)。worktree `.claude/worktrees/r102` (branch `r102`)、本書では `$WT` (main checkout からの相対)。全 WP が同じファイル群に触るので並行 worktree にしない (`OC` §1.2 の 16)。WP は直列で、WP ごとに監督が branch へ WIP commit する。完了ゲートは最後の merge 候補 (main に branch を `--no-ff` で merge した候補) の上で 1 回 (必要なら再実行)。main への merge は全 WP の後に 1 回。
- **規模 L** (`OC` §1.13 の 74)。**変更クラス D** (設計 §9: `CM` の Control 主張の書き換え = D、`COND`・port・conformance の test の変更 = C、両 peer の src = B)。D の証拠: C の全部 + 依頼者裁定の逐語 (設計 §11.1) + 版付きの security-contract 決定 (`CM` 3.13 → 3.14)。**契約は 1.13.0 のまま、`spec/` は触らない** (M-1)。
- レビューの形: コードレビューは **4 群** (WP-1+2、WP-3+4、WP-5+6、WP-7)。各群の **1 巡目は担当観点 A / B の `reviewer` 2 起動を並列** (`OC` §1.7 の 50a。並列の 2 起動は `mutate.py` を実行せず、足したい変異は spec を `$SP` のファイルに書く。実行は 2 起動の完了後に監督)、修正後の再確認は観点を指定しない 1 起動。受け入れ監査 (`evidence-auditor`) は全群のレビューの後に 1 回。担当は報告に「確認した観点 / 確認していない観点」を書く (同 50b)。
- 依頼者確認の扱い: §1 の監督裁定 M-1〜M-16 は**依頼者確認待ちのまま監督裁定で進め、閉止前に一覧でまとめて確認を求める** (依頼者指示 2026-10-01「裁定は監督の推奨で進めてあとで確認」)。WP-1 で再現が成立したときの依頼者への報告 (設計 Q-4 の (i-a)) は監督が引き継ぎ書に書く (M-16)。
- 番号: 完了条件は全 WP の通し番号 (1〜98)。変異は **V<完了条件番号>** (`expect=red`。記号 M は §1 の監督裁定と重なるので変異には使わない)。変異の無い完了条件は「監査照合」とし、照合対象の逐語 (実行したコマンドと集計行、`file:line`、`git diff`) を報告と §5 に残すこと自体を完了条件とする (`OC` §1.5 の 40)。
- 本書の `file:line` は起草時点の main (`ddf9c73`) の現物である。設計の出所 (基点 `173371d`) との差は §0.2。実装担当は着手時に記号名で引き直す (行は WP ごとに動く)。

**略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`ROLES` = `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`、`CM` = `security/CONTROL_MAPPING.md`、`COND` = `conformance-tests/CONDITIONS.md`、`CT` = `conformance-tests`、`CR` = `MitateDB-api/docs/cloud-run-cloud-sql.md`、`M` = `MitateDB-api/src/mitatedb_api`、`R` = `r2db-api/src/r2db_api`、`MT` = `MitateDB-api/tests`、`RT` = `r2db-api/tests`、`MC` = `MitateDB-api/conformance`、`RC` = `r2db-api/conformance`、`$SP` = 監督が発注時に渡す scratchpad、`$WT` = `.claude/worktrees/r102`。

### 0.1 枠 (問題設定・守る条件・決定・却下案・未確定)

- 問題設定と守るべき条件: 設計 §1・§3 (cell lock の廃止、application × role の pool、1 要求 = 主接続の 1 transaction、advisory lock 2 段 3a / 3b、transaction scope の idempotency lock、共通条件 C-34、r2db の 3 窓を同じ変更セットで閉じる)。事実は設計 §2 (行番号は §0.2 で引き直す)。
- 決定と根拠: 設計 §5 の D-1〜D-8 (設計 §11.1 で依頼者裁定済み。再審議しない、`OC` §1.7 の 51) と §1 の M-1〜M-16 (監督裁定、依頼者確認待ち)。
- 却下した代替案: 設計 §4 (候補 (乙)(丙)(丁)(戊)) と設計 D-3 の却下 (b)(c)。蒸し返さない。
- 未確定で依頼者判断待ちの選択肢: 無し (M-1〜M-16 は監督裁定で進め、最後に依頼者が確認する)。

### 0.2 設計の出所の行番号と現行 main の対応 (註。設計文書は書き換えない)

設計の `file:line` は `173371d` の木。R-115 の merge (`M/cell.py`・`M/backend_postgres.py`・`M/pool.py`・`M/main.py`・契約 1.13.0) と R-119 の merge で次の行が動いた。表に無い出所は現行でも同じ行である。

| 設計の出所 (`173371d`) | 現行 (`ddf9c73`) | 備考 |
|---|---|---|
| `RM`:459 (R-102) | `RM`:462 | G-4 は :40 のまま、§0.1.3 の G-4 行は :58、§0.1.4 の 3・4 は :66・:67 のまま |
| `spec/data-service-api.v1.json`:826 / :829 | :834 / :837 | 契約 1.13.0 で動いた。:37 は同じ |
| `M/cell.py`:1266 (`schema_count` の上限検査) | :1321 | :645 (`_lock`)・:508-603 (`_CountingRLock`)・:646-685 (経緯コメント)・:623 は同じ |
| `M/cell.py`:1268-1360 (field の検証と `enum_members`) | :1323-1473 | |
| `M/cell.py`:1419-1431 (idempotency の受付)、:1423-1430 (受付の註) | :1474-1486、:1479・:1502 | |
| `M/cell.py`:1466-1484 (開1 の plan の照合) | :1515-1539 | |
| `M/cell.py`:1885-1886 / :1887-1891 (`alter_field`) | :1940-1941 / :1942-1946 | |
| `M/cell.py`:2125-2152 (`_schema_revision_uncounted`)、:2151 (内側の lock) | :2180-2207、:2206 | |
| `M/cell.py`:2309-2310 / :2354 / :2357 (`read_page` の外側 lock / 内側 lock / decode) | :2363-2364 / :2408 / :2411 | :2411 は R-119 で内側の lock の中へ移った |
| `M/cell.py`:2325 (select を pass 1 で決める) | :2379 | |
| `M/cell.py`:2374 (buffer の push、lock の外) | :2427 (`_write_data_operation_event`) | R-115 で buffer は無くなり同期書き込みになった |
| `M/cell.py`:2935-2936 / :3130 (`transact` の外側 / 内側 lock) | :2990-2991 / :3187 | |
| `M/cell.py`:3337・:3346 (`transact` の監査) | :3284 (`pre_commit`)・:3408 (`__record`) | R-115 で形が変わった |
| `M/cell.py`:3407 (`_decode_rows`)、:3638 (`check_declared_value`) | :3460、:3701 | |
| `M/cell.py`:1155-1165 (守3 の註) | :1210-1220 | |
| `M/backend_postgres.py`:1388-1392 (DML の `except psycopg.Error`) | :1316-1321・:1349-1353・:1378-1379 | R-115 で単発の `insert()` / `update()` が消え、以後 −66〜−67 |
| `M/backend_postgres.py`:1591-1602 (`SET LOCAL`) / :1605-1624・:1609 (`begin`) | :1524-1535 (`_set_timeouts`) / :1538-1557・:1542 | :294-295・:330-366・:420・:440・:518-555・:668・:740-918・:818・:921-936・:938-940・:1152・:212-241 は同じ |
| `M/backend_postgres.py`:1722-1763 (session scope の理由) | :1655-1696 | |
| `M/backend_postgres.py`:1772-1774 / :1784-1795・:1794 (per-key lock) | :1706-1708 / :1717-1728・:1728 | |
| `M/backend_postgres.py`:1828-1839 / :1846-1858 / :1884 (件数 lock) / :1939-1943 (unlock) | :1762-1773 / :1780-1792 / :1818 / :1873-1877 | |
| `M/pool.py`:115 / :307 / :311-321 / :334-340 | :126 (`acquire_timeout`) / :350-354 (接続失敗) / :362-368 (枯渇) / :381-388 (`release`) | R-115 の idle ping で動いた |
| `M/credential_store_postgres.py`:401-418 | :402-418 | |
| `M/main.py`:390・:533 (platform pool) | :351 (platform pool)・:358 (audit pool、R-115) | |
| `M/main.py`:573-613 / :589-603 / :733 | :536-576 / :553-567 / :649 | |
| `M/http.py`:1310-1315 | :1303-1315 | |
| `M/platform_declarations.py`:1102-1103 / :1254 / :1362-1375 | :1108-1109 / :1260 / :1381 | |
| `MT/test_application_audit.py`:2163 / :2330 | :1705 / :1866 | test 名は同じ |
| `MT/test_postgres.py`:1013 | :1021 (`test_transact_pass_boundary_schema_change_window_yields_not_found_and_sibling_entity_unchanged`) | |
| `MT/test_audit_query.py`:2188 (`_ISOMORPHIC_TARGETS`)、件数 pin 199、:2812 | :2217、件数 pin 205 (`test_isomorphic_target_table_is_pinned_to_its_current_205_rows`)、:2851 | r2db 側は `RT/test_audit_query.py`:2425・:3071 |
| `CM`:716 / :979 / :998-1000 / :1029 / :1500・:1505 | :717 / :980 / :999-1001 / :1030 / :1501・:1506 | `CM`:854 は同じ (段は :850-857)。版の行は :5 |
| `MC/conformance_adapter_mitatedb_http.py`:3378-3389 (`pool_stats`) | :3379-3390 | |
| `CR`:526 (接続の式) | :509-531 | 同じ式の表が §6.5 の :1717-1731 にもある |
| `R/postgres.py`:2078 / :2089-2092 / :2094 / :2113 / :2138 | :2090 / :2101-2104 / :2106 / :2125 / :2150 | `apply_schema` の中 |
| `R/postgres.py`:2151-2172 / :2172 / :2193 / :2206 / :2242・:2307 / :2351 / :2387 / :2583-2598 | :2163-2184 / :2184 / :2205 / :2218 / :2254・:2319 / :2363 / :2399 / :2606-2621 | :904・:1007-1008・:1126・:1381・:1401・:1407・:1623・:679・:809・:815-829 は同じ |

## 1. 監督裁定 M-1〜M-16 (依頼者確認待ち。逐語)

出所: 監督の枠 (`$SP/r102-wo-frame.md`、2026-10-01) の「監督裁定 M-1〜M-16 (設計 §12 の起草時確定事項と、起草に要る形の確定)」節から逐語で複製した (`OC` §1.5 の 35・36)。**依頼者確認待ち**である。確認で覆ったときは本書に訂正註を足し、行を消さない (`OC` §1.8 の 56・57)。

M-1 (設計 §12 の 7、40P01 の写像): MitateDB は `psycopg.errors.DeadlockDetected` (40P01) と `psycopg.errors.SerializationFailure` (40001) を新しい例外 `StorageTransientError(FoundationError)` (errors.py) に写し、http.py の `_CLASSIFY_ORDER` で `SERVICE_UNAVAILABLE` (503) に写す。r2db は既に未分類の psycopg.Error を `SERVICE_UNAVAILABLE` に写す (r2db-api/src/r2db_api/postgres.py:1741-1750、:2438-2443) ので契約の語彙は増えず、契約は触らない。DML・idempotency 経路の残りの `except psycopg.Error → ValidationError("storage backend rejected the request")` は本件では変えない (観察として引き継ぎ書に残す)。

M-2 (設計 §12 の 10、D-2 (ii)、データ面の接続失敗の写像): pool.py は中立の例外 `PoolExhausted` / `PoolConnectFailed` (共通の基底 `PoolError(Exception)`) を投げる。platform 側の利用者 (credential_store_postgres.py、application_audit.py、main.py の借用点) は現行と同じ文面の `AuthorizationStateUnavailable` / 監査側の既存例外へ写す (観測可能な振る舞いは不変。既存テストの文字列 pin を壊さない)。データ面: `PoolExhausted` (deadline の残りを超えた) → `ResourceLimitError(limit_class="execution_ms")`、`PoolConnectFailed` → `StorageTransientError` → `SERVICE_UNAVAILABLE`。F-12 の refusing cell の意味論は不変。

M-3 (設計 §12 の 8、audit pool との待ちの連鎖): audit pool の保持者 (pre-commit hook の書き込み、denial の route、同期 event の書き込み) は platform DB にしか触れず application database の lock を待たない。application の transaction と lock を持ったまま audit pool を待つ側は既存の acquire_timeout (5.0 s) で打ち切られ `AuditSinkUnavailable` (503) になり、範囲の出口で接続を返す (rollback で lock も放す)。完了条件として固定する: audit pool の max_size=1 で 1 本を借りたまま schema 操作を出すと有界の時間で 503 になり、借りた 1 本を返した後の次の schema 操作は成功する (lock が残らない)。変異: 範囲の出口の release / rollback を消す → 次の schema 操作が lock 待ちで赤。

M-4 (設計 §12 の 9、DDL の timeout): 範囲の入口で主接続 (と DML / query の pass 1 用 developer 接続) に `SET LOCAL statement_timeout` / `lock_timeout` を deadline から 1 回打つ。catalog 読み群 (schema_count / field_domains / field_types / all_field_types / field_constraints / field_types_and_constraints / all_field_constraints / schema_revision) は自分で timeout を打たず自己 commit もしない。schema 操作の本体 (create_collection / add_field / alter_field_constraints) の既存の `_set_timeouts` 呼び出しは同じ transaction 内の打ち直し (後勝ち、同じ値) として残してよいが、値は deadline 由来に統一する (R-87 の「constructed max_execution_ms で無条件」は消える。`CM`:854 付近の主張 (8 reads が各自 transaction を開く) を書き換える)。

M-5 (設計 §12 の 11、D-6 の形): `StorageBackend.request_scope(kind, *, deadline)` (kind ∈ {"schema", "dml", "query"}) を context manager として足し、`RequestScope` (dataclass 相当) を yield する。PostgresBackend の scope は `main` (schema = developer、dml / query = runtime) と `developer` (dml / query の pass 1 用。schema では main と同一) の接続を持ち、入口で developer → runtime の順に借り、transaction を開き timeout を打ち、出口で rollback (未 commit なら) → release する。SQLiteBackend の scope は backend 自身の RLock を保持し、接続欄は None。backend のデータ / catalog メソッドは `scope` を keyword 引数で受け取り (`scope=`)、`self._developer` / `self._runtime` を参照しない (静的テストで固定: backend_postgres.py に `self._developer` / `self._runtime` の参照 0 件、cell.py に `self._lock`・`_CountingRLock`・`SQLiteBackend`・`PostgresBackend` の名前 0 件)。cell.py は現行の外側 `with self._lock:` の位置を `with self._backend.request_scope(kind, deadline=deadline) as scope:` に置き換え、内側の再入 `with self._lock:` は削除する。backend の種類で分岐しない。

M-6 (設計 §12 の 12、schema 操作の transaction が長くなる件): 受け入れる。上限は範囲の入口の deadline 由来の timeout (execution_ms) であり、追加の機構は置かない。対象実体の DML の共有 lock 待ちも同じ timeout で打ち切られ `LIMIT_EXCEEDED(execution_ms)` になる (設計 D-3 の timeout の項)。

M-7 (設計 §12 の 13、3b の取得数と往復): DML は触る実体の重複を除いて昇順に並べ、1 文で取る: `SELECT bool_and(pg_try_advisory_xact_lock_shared(%s, hashtext(e))) FROM unnest(%s::text[]) AS e` → false なら waits を 1 数えて `SELECT pg_advisory_xact_lock_shared(%s, hashtext(e)) FROM unnest(%s::text[]) AS e` で取り直す (既に取れた分は同 transaction 内の再取得で無害 [PostgreSQL 一般、repo では未確認])。schema 操作の 3a・3b も同じ try → block の形 (各 1 文)。往復は競合が無ければ DML +1 (3b)、schema 操作 +2 (3a・3b)、競合時に各 +1。`backend_calls` の差分の理由は作業指示書 §計測 と `RM` §0.1.4 の 4 の形で記録する。

M-8 (pool の寸法と持ち主): application × role の pool は `PostgresBackend` が自分で持つ (2 個)。上限は `role_pool_size(thread_limit)`。`build_app` は thread limit を `PostgresBackend(..., pool_size=)` に渡す。conformance の http / socket adapter (MitateDB-api/conformance/conformance_adapter_mitatedb_http.py) は composition root と同じ寸法 (`role_pool_size(DEFAULT_THREAD_LIMIT)`) を渡す (R-115 の教訓: plug の構成は composition root と揃える)。`DSA_PERF_POOL_SIZE` の類の新設定は足さない。

M-9 (idle の切り詰めの形、設計 D-2 / L-1): pool.py に process に 1 つの弱参照の一覧 (`weakref.WeakSet`) を置き、`BoundedConnectionPool` の全 instance が生成時に登録する。どの pool の `acquire` でも、一覧の全 pool について `_pool_returned_at` が `IDLE_CLOSE_THRESHOLD_S = 300.0` s より古い idle 接続を閉じる (in-use には触れない)。掃除の走査は 1 process で高々 1 秒に 1 回 (monotonic の記録で抑える。同じ結果を保ったまま acquire ごとの全 pool の lock 取得を避けるための実装詳細。設計外の拡張ではなく実装の細部として扱うが、依頼者確認の対象に含める)。専用 thread・timer は無し。要求が 1 件も来ない process は掃かない (開示)。

M-10 (advisory lock の key): 3a = `_SCHEMA_SERIALIZATION_LOCK_KEY = 761761763` (1 引数形、排他のみ、`pg_advisory_xact_lock`)。3b = `_ENTITY_LOCK_NAMESPACE = 76176101` (2 引数形、`hashtext(実体名)`)。既存の 76176100 / 761761761 / 761761762 と別値。migration は不要 (advisory lock は表も権限も要らない)。

M-11 (拒否の優先順位、設計 K-2 / Q-9): `create_collection` の `schema_count` の上限検査は idempotency の受付の後・3a の後へ移す。dry-run も同じ点で数える。`enum_members` と `schema_objects` の順が r2db と逆になる点は本件で揃えない (観察)。

M-12 (起動時の F-12 検査): `PostgresBackend.__init__` は接続を張らない (pool を作るだけ)。`build_app` は served application ごとに runtime の pool から 1 本借りて F-12 の検査を行い、現行どおり 1 行記録して返す。検出時の refusing cell の意味論は不変。

M-13 (C-34 と port v1.20): 共通条件 C-34 (plan の前提条件が並行する schema 操作の下でも成り立つ) を `conformance-tests/CONDITIONS.md` に足し、port の hook `hold_after_plan_verification(session)` を足す (port v1.20): 「`session` 上で次に到着する schema 操作を 1 件だけ、その要求自身が plan token を現在の revision と照合し終え (plan を提示しない要求では、自分が進める revision を読み終え)、その照合が取った lock をすべて保持したまま、DDL をまだ 1 文も実行していない地点で停止させたまま保持する。保持中に同じ Application への 2 件目の schema 操作を出すと、2 件目は先着が解放されて commit した後にはじめて答えを返すか、または先着が `PRECONDITION_FAILED` で拒否され何も実行しない。`with` を抜けると先着は解放される。」実現は両 peer とも adapter 内部の stalled cell method (product code に test 専用 hook を置かない。`hold_after_idempotency_lookup` と同じ規律)。試験の形は C-27 と同じ (`wait_until_held`、B の有界の未完了確認、release 後の両者の結果)。in-process の MitateDB plug (SQLite) では B は backend の RLock で待つ (空振りではない: hold は実際に到達し、B は実際に出され、B の未完了と A の結果を assert する)。C-34 の登録は 6 adapter。`schema_objects` の上限と drop の確認句の窓は peer テストで固定 (K-7)。

M-14 (R-119 のテストの扱い): D-5 の後 `_decode_rows` は pass 1 で読んだ field types を使い catalog を読まない。`MitateDB-api/tests/test_r119_read_page_decode_under_lock.py` は「decode が範囲の外で catalog を読まない」を固定する形へ作り替える (backend.field_types が範囲の外で 1 度も呼ばれないこと、応答の decode が正しいこと)。変異: decode を範囲の外の catalog 読みに戻す。

M-15 (WP の分割と順): WP-1 再現テスト (赤で置く) → WP-2 C-34 + port v1.20 + 6 adapter (r2db は WP-6 まで赤のまま) → WP-3 pool.py (D-2) → WP-4 MitateDB 本体 (D-1・D-3・D-4・D-5・D-6、M-1〜M-7・M-10〜M-12・M-14) → WP-5 計測器 (D-7、adapter の pool_stats、perf_baseline の POOL 行、tools/tests、PERF README、test_r78 / test_r79) → WP-6 r2db (D-8: lock を `_load_catalog` の前に、WP-1 の r2db の 3 窓を緑に) → WP-7 記録 (CM、COND の C-05 note・C-27 の変異指定・adapter.py:1802 の (ii)、C-27 テストの語、runbook の式、config.py の docstring、R-113 設計への註、startup_checks の指紋、台帳 R-102 行、`RM` §0.1.3 の G-4 行)。コードレビューは WP-1+2、WP-3+4、WP-5+6、WP-7 の 4 群 (各群 1 巡目 A / B 並列)。計測 D-R102 は監督が WP-3 の前 (基準値、基点 main) と WP-7 の後 (実装後) に行い、結果は作業指示書 §計測 に記録する。

M-16 (WP-1 の再現テストの置き方): MitateDB は `MitateDB-api/tests/test_idempotency_concurrency.py` の `_pg_pair` (独立 2 cell = 別接続組) と同じ土台で `MitateDB-api/tests/test_r102_cross_cell_windows.py` に 開1〜開4 の 4 本。r2db は `r2db-api/tests/test_r102_schema_windows.py` に plan / 確認句 / schema_objects の 3 本 (2 つの service / cell instance、同じ application)。hold は test 内部の stalled method (backend / cell の該当メソッドを wrap して Event で止める)。WP-1 の時点で赤 (再現成立) か緑 (不成立) かを実測し報告に書く。赤なら成立を作業指示書に記録し、依頼者への報告 (設計 Q-4 (i-a)) は監督が引き継ぎ書 §4 に書く。WP-4 / WP-6 で緑にし、以後は常設のテストとして残す (変異: 3a を消す / 3b を消す / 排他を共有にする / r2db の lock を消す)。

## 2. Change Set Manifest (WP-1〜WP-7)

### 2.0 共通 (全 WP)

**順序**: WP-1 (再現テスト、赤で置く) → WP-2 (C-34 + port v1.20 + 6 adapter。r2db の 2 plug と socket 1 plug は WP-6 まで赤) → [計測 D-R102 の基準値、§3] → WP-3 (`M/pool.py`) → WP-4 (MitateDB 本体) → WP-5 (計測器) → WP-6 (r2db) → WP-7 (記録) → [計測 D-R102 の実装後、§3] → 完了ゲート・受け入れ監査・merge (§4) (M-15)。WP-1・WP-2 の赤のテストは赤のまま branch に commit してよい (main には入らない)。

**役割**:

- 実装担当 (`ROLES` の 2、`implementer`): WP-1〜WP-6 に 1 起動ずつ (差し戻しは別起動)。雛形の穴は各 WP の「発注の穴」に置く。
- コードレビュー (`ROLES` の 5、`reviewer`、Class D): 4 群 (§0)。レビューの範囲は群の WP の差分。観点は各 WP の「レビューの観点」と、空振り (`OC` §1.5 の 32)・代理指標 (`OC` §1.7 の 52)・主張 vs 実測 (`OC` §1.5 の 34)。
- 受け入れ監査 (`ROLES` の 6、`evidence-auditor`): 全群のレビューの後に 1 回。
- 監督: WP ごとの branch への commit、WP-7 (実装担当を起動しない。起草担当に渡してよい)、確定文ファイルの作成 (§2.2)、計測 D-R102 (§3)、完了ゲート、`COLLECTION_FLOOR` の更新、指摘の 1 件ごとの裁定 (`OC` §1.15 の 77)、local main への merge 1 回。push は停止中。

**実装担当への注意 (全 WP。発注の「注意」の行に置く)**:

1. suite 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` を実行しない (`OC` §1.6 の 42、§1.11 の 70)。テストは各 WP の「道具の引数」の `pt.py` だけを前景・直列・timeout 600000 で回す (conformance の担当ファイルは 1 回の前景呼び出しに収まる)。
2. commit・merge・push・branch 操作・`git stash` をしない。例外は新規 file の `git add -N` だけ (`OC` §1.1 の 2)。
3. 下請けの Agent を起動しない (`OC` §1.7 の 47)。
4. 設計に無い検査・機構は実装前に報告し、監督裁定を得てから実装する (`OC` §1.5 の 37)。触ってよいパスの外の赤は直さず報告する。
5. docstring と経緯コメントを移すときは逐語で移し、移動で指す先が変わる位置参照だけを括弧書きで補う (`OC` §1.5 の 40c)。新しいコメント・docstring は現在形で書き、フェーズ / WP / 台帳 ID / 日付の語を入れない (`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 (5))。`# history: CH-NNNN` を持つ塊を言い換える・消すときは同じ変更セットで `docs/code-history/MitateDB-api/` (r2db は `docs/code-history/r2db-api/`) に訂正を追記する (同設計 §9.3。CH-ID を持つ塊がコードごと消える場合の扱いは R-115 作業指示書 訂正註 9 の (2) の先例)。`python3 tools/check_comment_provenance.py --base main <触った src>` の赤は、直したもの・直さなかったものを問わず報告に列挙する。
6. 変異は 1 変異 1 entry、`-x` を使わない。各 entry の test id はその完了条件のテスト 1 件だけ (`mutate.py` は最初の失敗で止まる)。`-k` の id は `--collect-only -q` で確かめる。`old` / `new` は実装担当が書き、報告に表で残す。REFUSED (終了コード 75) は迂回しない (`OC` §1.10 の 66)。
7. 新しいテストは観測対象が 1 件以上あることを assert する (`OC` §1.5 の 32)。skip / xfail を置かない。
8. 一時ファイルは `$SP` 配下、複数手順は `$SP` の bash 3.2 互換スクリプト。報告は `$SP/r102-wp<N>-report.md` (道具の出力行をそのまま貼る。`OC` §1.10 の 65)。本番には何も適用しない。port 8000 / 8001 の uvicorn は別 repo の常設 service なので止めない。

**道具の引数** (`$SP` を export し、main checkout を cwd にして `-C` で worktree を指す。渡し忘れると main を測る):

```bash
tools/dev/pt.py -C .claude/worktrees/r102 -- <各 WP の「テスト」のパス> -q
tools/dev/mutate.py "$SP/r102-wp<N>-mutations.json" -C .claude/worktrees/r102
```

worktree を cwd にして: `python3 tools/check_comment_provenance.py --base main <触った src>`、`python3 tools/check_comment_provenance.py --register`、`python3 tools/change_class.py <触った全パス>`、`python3 tools/check_doc_refs.py`、`python3 tools/public_value_scan.py <触った全パス>`。`tools/tests` に触れた WP は、新規 file を `git add -N` した後に `tools/dev/pt.py -C .claude/worktrees/r102 -- tools/tests -q` を別に回す (根の gate は `tools/tests` を含まない)。

**後の WP で走らせる変異**: WP-1・WP-2 の試験に掛かる変異のうち、試験が緑になる前には赤 / 緑を区別できないもの (V1〜V9、V17〜V19) は、その試験を緑にする WP (WP-4・WP-6) の実装担当が走らせ、その WP の報告に表で残す (R-115 作業指示書 §4.2 の先例)。spec は WP-1・WP-2 の担当が `$SP/r102-wp1-mutations-deferred.json`・`$SP/r102-wp2-mutations-deferred.json` に書いておく (`old` は後の WP の実装に合わせて書き直してよい。書き直しは報告に書く)。

### 2.1 WP-1 — 再現テスト (実装担当。赤で置く)

**目的**: 設計 §2.5 の開1〜開4 (MitateDB、process 間) と設計 §2.6 の r2db の 3 窓 (plan・確認句・`schema_objects`) を、2 組の接続 (2 cell / 2 service instance) で決定的に再現するテストを先に置き、**現行実装に対する赤 / 緑を実測する** (M-16、設計 Q-4 の (i))。以後は常設のテストとして残す。
**読むべき正本**: 設計 §2.5・§2.6・§6 の「開1〜開4」行・§11.1 の Q-4・Q-5。`MT/test_idempotency_concurrency.py`:228-250 (`_pg_pair`、独立 2 cell = 別接続組)、:253・:298・:347 (2 cell の並行の書き方)。**クラス**: B。**群**: レビュー群 1 (WP-1+2)。

**触ってよいパス**: `MT/test_r102_cross_cell_windows.py` (新規)、`RT/test_r102_schema_windows.py` (新規)。これ以外は 0 件 (両 peer の src・adapter・既存テストを触らない)。

**試験の筋書き** (共通: 先着 A を test 内部の stalled method で止め、後着 B を別 thread で出す。止め方は「対象の backend / cell のメソッドを wrap し、wrap の中で `threading.Event` を待つ」形で、product code に hook を置かない (M-16)。A の停止は上限付きの待ちで確かめ、上限内に到達しなければ wrap 点を message に含む `AssertionError` で落ちる。B の未完了は有界の窓 (`MT/test_idempotency_concurrency.py` の `_BLOCKED_PROOF_WINDOW_S` と同じ形) で確かめる。**assert の形は 7 本とも**「B が A の保持中に完了したなら、A は正しく拒否されて何も実行しない。B が保持中に完了しなかったなら、解放後に A・B の順に commit し、両方の結果が矛盾しない」とする。固定の sleep は B の未完了の窓だけ。wrap 点は実装担当が現物で選び、報告に `file:line` で書く):

| # | テスト (置き場) | A (保持する要求) と停止点 | B (割り込ませる要求) | assert |
|---|---|---|---|---|
| 開1 | plan の check-then-act (`MT/test_r102_cross_cell_windows.py`、`_pg_pair` の cell_a / cell_b) | cell_a で実体 E1 への schema 操作 (例 `add_field`) を、dry-run で得た plan を付けて出す。停止点 = plan を現在の revision と照合し終えた後・DDL の前 (現行は cell_a の `_backend` の該当 DDL メソッドの入口) | cell_b で**別の実体 E2** への schema 操作 (plan なし) | B が保持中に完了したなら、A は `PRECONDITION_FAILED` (`violated_declaration: plan`) で E1 に何も足さない。完了しなかったなら、解放後に A・B とも成功し、revision は 2 進む。B を別の実体にするのは、3b ではなく 3a だけがこの窓を閉じることを固定するため |
| 開2 | alter 同士の lost update (同上) | cell_a で `alter_field(E, f, enum=...)`。停止点 = registry 行を読んだ後・UPDATE の前 (現行は `alter_field_constraints` の中の `LOCK TABLE` の前) | cell_b で同じ `f` に `alter_field(E, f, nullable=False)` | 両方の完了後、registry の `f` が A の enum と B の nullable の両方を持つ (どちらの更新も失われない) |
| 開3 | 検証と DML の間の alter (同上) | cell_a で E への DML (enum の値 v を書く insert)。停止点 = pass 1 の検証 (`check_declared_value`) を通った後・DML の実行の前 (現行は pass 2 の入口) | cell_b で `alter_field(E, f, enum=...)` (v を除く) | B が保持中に完了したなら、A は拒否され v を持つ行は無い。完了しなかったなら、A の行が入った後に B が走り、B の走査の判定どおりになる |
| 開4 | `schema_objects` の上限 (同上。`FoundationConfig` の `max_schema_objects` を現数 + 1 にする) | cell_a で `create_collection(E1)`。停止点 = `schema_count` の上限検査を通った後・DDL の前 | cell_b で `create_collection(E2)` | 両方の完了後、schema object の数が上限以下で、2 件のうち 1 件が `LIMIT_EXCEEDED` (`limit_class` `schema_objects`) |
| r2db plan | `RT/test_r102_schema_windows.py` (同じ application に 2 つの `PostgresCell` instance) | cell_a で E1 への `apply_schema` を plan 付きで。停止点 = revision を読んだ後・DDL の前 | cell_b で別の実体 E2 への `apply_schema` (plan なし) | 開1 と同じ |
| r2db 確認句 | 同上 | cell_a で `drop_entity` (E1) を、その時点の revision の確認句付きで。停止点 = 確認句の revision を読んだ後・DROP の前 (`R/postgres.py`:2218) | cell_b で別の実体への `apply_schema` (revision を進める) | B が保持中に完了したなら、A は `DESTRUCTIVE_CONFIRMATION_REQUIRED` で E1 は残る。完了しなかったなら、解放後に A・B とも成功 |
| r2db `schema_objects` | 同上 (上限を現数 + 1) | cell_a で `create_entity` (E1)。停止点 = `schema_objects` の検査 (`R/postgres.py`:2184) の後・DDL の前 | cell_b で `create_entity` (E2) | 開4 と同じ |

**完了条件 (1〜12) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | 開1 のテストが上の筋書きで在り、A の停止の到達と B の送出を assert する | V1 (WP-4 の後): 3a の取得を消す |
| 2 | 開2 のテストが在り、同上 | V2 (WP-4 の後): 3a の取得を消す (設計 §6) |
| 3 | 開3 のテストが在り、同上 | V3 (WP-4 の後): DML の 3b の取得を消す |
| 4 | 開3 のテストが排他と共有の区別に依存する (DML の共有と schema 操作の排他が競合することを通って緑になる) | V4 (WP-4 の後): schema 操作の 3b を排他の代わりに共有で取る |
| 5 | 開4 のテストが在り、同上 | V5 (WP-4 の後): 3a の取得を消す |
| 6 | r2db plan のテストが在り、同上 | V6 (WP-6 の後): r2db の lock を消す |
| 7 | r2db 確認句のテストが在り、同上 | V7 (WP-6 の後): r2db の lock を消す |
| 8 | r2db `schema_objects` のテストが在り、同上 | V8 (WP-6 の後): r2db の lock を消す |
| 9 | 7 本とも A の停止の待ちに上限があり、未到達なら wrap 点を含む message で落ちる | V9 (WP-4 の後): 開1 の wrap 対象を到達しないメソッド名に替える (`AssertionError` の message 行を照合) |
| 10 | WP-1 の時点 (基点の実装) で 7 本それぞれが赤か緑かを実測した。赤は再現の成立 (M-16)、緑は不成立として、失敗の assert 行と集計行を報告に逐語で貼る | 監査照合 (`pt.py` の集計行と各 test の結果行、赤の assert message の行) |
| 11 | skip / xfail が無く、固定の sleep は B の未完了の窓だけ | 監査照合 (`git grep -n 'skip\|xfail\|sleep' <2 file>` の逐語) |
| 12 | 本表に対応の無い行が無い | 監査照合 |

**発注の穴** (`ROLES` の 2): 作業指示書 = 本節。正本設計 = 設計 §2.5・§2.6・§6。テスト = `tools/dev/pt.py -C .claude/worktrees/r102 -- MitateDB-api/tests/test_r102_cross_cell_windows.py -q` と `-- r2db-api/tests/test_r102_schema_windows.py -q`。変異 = V1〜V9 は後の WP で実行するので、spec を `$SP/r102-wp1-mutations-deferred.json` に書くだけ。報告 = `$SP/r102-wp1-report.md`。

**レビューの観点**: 空振り (停止点に本当に到達しているか、B が本当に出ているか、B の完了 / 未完了の両方の枝の assert が意味を持つか)。開1・開4 の B が別の実体であること (3a の変異が赤になる前提)。2 cell が本当に別の接続組であること (`_pg_pair` の形)。

### 2.2 WP-2 — C-34 + port v1.20 + 6 adapter (実装担当)

**目的**: 設計 Q-5 (共通条件を足す) と M-13。plan の前提条件が並行する schema 操作の下でも成り立つことを共通条件 C-34 として両 peer の 6 plug で駆動する。port に hook `hold_after_plan_verification(session)` を足し (port v1.20)、6 adapter が adapter 内部の stalled cell method で実現する。**r2db-http と r2db-socket の 2 plug は WP-6 まで赤のまま** (M-15)。
**読むべき正本**: 設計 §9 の `conformance-tests/` の段・§11.1 の Q-5、M-13。雛形: `CT/test_c27_concurrent_same_key.py` (試験の形: `wait_until_held`、`_BLOCKED_PROOF_WINDOW_S` の有界の未完了確認、release 後の両者の結果、`test_c27_drives_on_every_registered_plug` の非空振りの guard、`test_c27_hold_timeout_fails_loudly`)、`CT/adapter.py`:997 (`IdempotencyHold`)・:1830 (`hold_after_idempotency_lookup` の docstring の形)、`RC/conformance_adapter_r2db.py`:299-357 と `RC/conformance_adapter_r2db_http.py`:878 (r2db の stalled cell method)、`MC/conformance_adapter_mitatedb.py`:527 と `MC/conformance_adapter_mitatedb_http.py`:859 (MitateDB の同じ形)。**クラス**: C。**群**: レビュー群 1。

**確定文ファイル** (監督が発注前に作る。`OC` §1.5 の 35): `$SP/confirmed-r102-hook.txt` (M-13 の hook の文。M-13 の「」の中を逐語) と `$SP/confirmed-r102-condition.txt` (下の条件文の起草案を監督が確定したもの)。実装担当はこの 2 ファイルから複製し、言い換えない。

**条件文の起草案** (本書の文は起草案であり確定文言ではない。監督が確定文ファイルに写し、`COND` の行はそのファイルから複製する。書式は `COND` の既存行 (`COND`:27 の表頭 `| ID | Condition | Invariants | Evidence | Status |`、1 cell 3000 字以内 = `CT/test_conditions_register.py`:96) に倣う):

```text
| C-34 | A peer declaring `dry_run` keeps a `plan`'s precondition true under a concurrent schema operation against the same Application: while one schema operation is held after it has checked its `plan` against the Application's current revision (or, carrying no `plan`, has read the revision it will advance), still holding every lock that check took and before it has executed any DDL, a second schema operation against the same Application either answers only after the first has been released and has committed, or the first is refused with `PRECONDITION_FAILED` naming `plan` and executes nothing -- a `plan` is never honored against a revision other than the one it was checked against. | SI-11 | concurrent schema-operation observation driven by a deterministic adapter hook, `hold_after_plan_verification(session)` (port v1.20), that holds the next schema operation arriving on `session` at that point -- `conformance-tests/test_c34_<name>.py` | executable (six adapters) -- `conformance-tests/test_c34_<name>.py`, `@pytest.mark.condition("C-34")`; the hook is realized inside each adapter by a stalled cell method, never by a test-only hook on product code (the same discipline as `hold_after_idempotency_lookup`, C-27). 〈観測の範囲と plug ごとの赤になる変異は、WP-4・WP-6 の実測の後に WP-7 で記入する (`OC` §1.5 の 34)〉 [history](CONDITIONS_HISTORY.md#c-34) |
```

**触ってよいパス**: `COND` (C-34 の行だけ)、`CT/adapter.py` (hook `hold_after_plan_verification` と port v1.20 の記述だけ)、`CT/test_c34_<name>.py` (新規。`<name>` は実装担当が付け報告に書く)、`CT/registry.json` (C-34 を 6 adapter で駆動するのに変更が要るときだけ。現行は adapter の一覧、`CT/registry.json`:1-14)、`CT/README.md` (port の版の記述が在るときだけ)、`RC/conformance_adapter_r2db.py`、`RC/conformance_adapter_r2db_http.py`、`MC/conformance_adapter_mitatedb.py`、`MC/conformance_adapter_mitatedb_http.py` (socket の 2 adapter は http の adapter を継承する = `RC/conformance_adapter_r2db_socket.py`:477、`MC/conformance_adapter_mitatedb_socket.py`:338。継承で足りなければ報告)。両 peer の `src/` を触らない。

**hook と試験の形**:

- port: `hold_after_plan_verification(session)` を `@abstractmethod` で足す。docstring の最初の段落は `$SP/confirmed-r102-hook.txt` の逐語、続けて `port v1.20` の段落 (C-34 の駆動、`hold_after_idempotency_lookup` との構造の違い = 自分では要求を出さない)。yield する handle は `IdempotencyHold` と同じ形 (`wait_until_held(timeout_s)`)。新しい型を足すか `IdempotencyHold` を使い回すかは実装担当が選び、報告に書く。
- adapter の停止点 (M-13 の hook の文の地点): MitateDB は cell (または backend) の schema 操作の DDL を担うメソッドの入口を wrap する (plan の照合と schema lock の取得の後、DDL の前)。r2db の in-process plug は `structured.ApplicationCell` の同じ地点、http plug は `PostgresCell.apply_schema` の中の revision の読みの後・DDL の前。選んだ wrap 点が hook の文の地点であることを、報告に `file:line` で示す。hook は次の 1 件の schema 操作だけを止め、他は素通しする。
- `CT/test_c34_<name>.py`: C-27 と同じ形。(a) `test_c34_drives_on_every_registered_plug` (6 plug が駆動されることの guard)、(b) `test_c34_hold_timeout_fails_loudly`、(c) 本体 = A (実体 E1 への plan 付きの schema 操作) を hook で保持 → `wait_until_held` → B (**別の実体 E2** への schema 操作) を別 thread で出す → 有界の窓で B の未完了を確かめる → release → 「B が保持中に完了しなかった: A・B とも成功し revision が 2 進む」または「A が `PRECONDITION_FAILED` (`plan`) で E1 に何も足さない」を assert。B を別の実体にするのは、MitateDB-http の赤が 3a だけに依存することを固定するため。in-process の MitateDB plug (SQLite) では B は lock で待つ (空振りではない: hold は実際に到達し、B は実際に出され、B の未完了と A の結果を assert する。M-13)。
- `schema_objects` の上限と drop の確認句の窓は C-34 に含めず、peer テストで固定する (M-13、K-7。WP-1 の r2db の 2 本と開4)。

**完了条件 (13〜25) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 13 | port に `hold_after_plan_verification(session)` が在り、docstring の最初の段落が `$SP/confirmed-r102-hook.txt` と逐語一致し、`port v1.20` の段落を持つ | 監査照合 (docstring の段落と確定文ファイルの `diff` の逐語) |
| 14 | r2db の 2 adapter (in-process・http) が hook を adapter 内部の stalled method で実現する | V14: r2db-http の stall を素通しにする (`test_c34` 本体の `wait_until_held` が赤) |
| 15 | MitateDB の 2 adapter (in-process・http) が同上 | V15: MitateDB-http の stall を素通しにする |
| 16 | `test_c34_drives_on_every_registered_plug` が 6 plug の駆動を assert する | V16: 1 adapter の hook を `NotImplementedError` にする (guard が赤) |
| 17 | C-34 本体が MitateDB-http で 3a に依存して緑になる | V17 (WP-4 の後): 3a の取得を消す |
| 18 | C-34 本体が MitateDB の in-process plug で SQLite backend の lock に依存して緑になる | V18 (WP-4 の後): SQLite の範囲の RLock を外す |
| 19 | C-34 本体が r2db-http で r2db の lock に依存して緑になる | V19 (WP-6 の後): r2db の lock を消す |
| 20 | `test_c34_hold_timeout_fails_loudly` が、要求を出さないときの `wait_until_held` の失敗を assert する | V20: MitateDB-http の `wait_until_held` を待たずに返す形にする |
| 21 | WP-2 の時点の plug ごとの結果を実測した (見込み: MitateDB の 4 plug と r2db の in-process は緑、r2db-http / r2db-socket は赤。違えば報告) | 監査照合 (`pt.py` の集計行と plug ごとの結果行) |
| 22 | `COND` の C-34 の行が `$SP/confirmed-r102-condition.txt` から複製され、`CT/test_conditions_register.py` が緑 | 監査照合 (集計行の逐語) |
| 23 | C-34 の test が 6 plug で collect される | 監査照合 (`--collect-only -q` の逐語) |
| 24 | 新しい試験に skip / xfail が無い | 監査照合 (`git grep` の逐語) |
| 25 | 本表に対応の無い行が無い | 監査照合 |

**発注の穴**: テスト = `tools/dev/pt.py -C .claude/worktrees/r102 -- conformance-tests/test_c34_<name>.py conformance-tests/test_c27_concurrent_same_key.py conformance-tests/test_conditions_register.py -q`。変異 = `tools/dev/mutate.py "$SP/r102-wp2-mutations.json" -C .claude/worktrees/r102` (V14〜V16・V20)。V17〜V19 は `$SP/r102-wp2-mutations-deferred.json`。報告 = `$SP/r102-wp2-report.md`。

**レビューの観点**: hook の文と停止点の一致 (照合の後・lock を保持・DDL の前)。空振り (保持が本当に到達し、B が本当に出され、B の未完了の窓が意味を持つか)。確定文の言い換えが無いこと。C-27 の hook と干渉しないこと (同じ adapter が両方を持つ)。

### 2.3 WP-3 — `M/pool.py` (設計 D-2。実装担当)

**目的**: 設計 D-2 の pool の class の直し (J-3 の (i)〜(iii)) と idle の切り詰め (M-9)、pool の中立の例外と利用者の写像 (M-2 の platform 側)。データ面の利用はまだ無い (WP-4)。
**読むべき正本**: 設計 D-2 (表と (i)〜(iii))・§2.8・§12 の 3・4・10、M-2・M-9。現物: `M/pool.py`:107-415 (`BoundedConnectionPool`。`acquire` :317-379、`release` :381-388、`discard` :390-398、R-115 の idle ping `IDLE_PING_THRESHOLD_S` :64 と `_pool_returned_at` :387)、利用者 `M/credential_store_postgres.py`:402-418、`M/application_audit.py`:505-533。r2db の同じ形: `R/postgres.py`:806-829 (`SharedPoolManager`、idle 300 s)、:679 (返却前の rollback)。**クラス**: B (`_ISOMORPHIC_TARGETS` に登録された helper に触れたら C。`change_class.py` の実測を報告)。**群**: レビュー群 2 (WP-3+4)。

**触ってよいパス**: `M/pool.py`、`M/credential_store_postgres.py`、`M/application_audit.py`、`M/main.py` (M-2 が挙げる借用点の写像だけ)、`MC/conformance_adapter_mitatedb_http.py` (`_audit_pool`・`_read_pool` の利用者の写像が要るときだけ)、`MT/` のうち pool と利用者のテスト (新規 `MT/test_r102_pool.py` と、既存の pool / credential store / audit sink のテスト)。

**実装の要点**:

- (i) `acquire(timeout=None)`: 呼び出しごとの待ち上限。`None` は構築時の `acquire_timeout` (既定 5.0 s、`M/pool.py`:126)。
- (ii) 中立の例外 `PoolError(Exception)` と、その下の `PoolExhausted` (待ち上限の超過) / `PoolConnectFailed` (接続の失敗) を `M/pool.py` に置き、`M/pool.py` は `AuthorizationStateUnavailable` を投げない。platform 側の利用者は現行と同じ文面の `AuthorizationStateUnavailable` (`"platform registry connection pool exhausted (max_size reached)"` / `"authorization state unavailable"`) と監査側の既存の例外へ写す (観測可能な振る舞いは不変、既存テストの文字列 pin を壊さない。M-2)。データ面の写像は WP-4。
- (iii) `release` は idle へ戻す前に必ず rollback し、rollback が失敗した接続は捨てる (`discard`)。
- idle の切り詰め (M-9): `weakref.WeakSet` の一覧に全 instance が生成時に登録し、どの pool の `acquire` でも、一覧の全 pool について `_pool_returned_at` が `IDLE_CLOSE_THRESHOLD_S = 300.0` s より古い idle 接続を閉じる。in-use には触れない。走査は 1 process で高々 1 秒に 1 回 (monotonic の記録)。専用 thread・timer は無し。閉じた接続の統計は既存の畳み込み (`_fold_closed_connection_stats`) を通す。

**完了条件 (26〜36) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 26 | `acquire(timeout=t)` は枯渇時に約 t で打ち切り、`timeout` 省略時は構築時の値を使う | V26: 呼び出しの `timeout` を無視して構築時の値を使う |
| 27 | 枯渇は `PoolExhausted`、接続失敗は `PoolConnectFailed` を投げ、どちらも `PoolError` の下にあり `FoundationError` ではない | V27: 枯渇で `AuthorizationStateUnavailable` を投げる形に戻す |
| 28 | credential store の借用点が `PoolError` を現行と同じ文面の `AuthorizationStateUnavailable` に写し、既存の文字列 pin のテストが緑 | V28: credential store の写像を外す (`PoolExhausted` が素通りする) |
| 29 | audit sink の借用点が `PoolError` を監査側の既存の例外に写し、既存テストが緑 | V29: `M/application_audit.py` の写像を外す |
| 30 | 開いた transaction と `SET` を残して返した接続が、次の借用で clean (`transaction_status` が IDLE、`SET` の値が既定) | V30: `release` の rollback を消す |
| 31 | rollback が失敗する接続は idle へ戻らず捨てられる | V31: rollback の失敗時も idle へ戻す |
| 32 | 別の pool の `acquire` で、止まった pool の閾値超えの idle 接続が閉じられ、in-use の接続は閉じられない | V32: 掃除を自分の pool だけにする |
| 33 | 掃除の走査は 1 process で高々 1 秒に 1 回 | V33: 抑制を外す (acquire ごとに走査する) |
| 34 | 参照の無くなった pool は一覧から消える (弱参照) | V34: `WeakSet` を強参照の集合にする |
| 35 | `MT` の pool・credential store・audit sink の既存テストと `MT/test_r78_pool_wait_stats.py` の pool の部が緑 | 監査照合 (集計行の逐語) |
| 36 | 本表に対応の無い行が無い | 監査照合 |

**発注の穴**: テスト = `tools/dev/pt.py -C .claude/worktrees/r102 -- MitateDB-api/tests -q`。変異 = `tools/dev/mutate.py "$SP/r102-wp3-mutations.json" -C .claude/worktrees/r102`。報告 = `$SP/r102-wp3-report.md`。

**レビューの観点**: 設計 §12 の 3・4 (session 状態が返却後に残らない。rollback の失敗で捨てる経路)。掃除が lookup の経路にならないこと (弱参照の一覧を掃除以外に使わない。SI-01、設計 K-10)。platform 側の観測可能な振る舞いの不変 (文面・code)。

### 2.4 WP-4 — MitateDB 本体 (実装担当)

**目的**: 設計 D-1・D-3・D-4・D-5・D-6 と M-1〜M-7・M-10〜M-12・M-14。`ApplicationCell._lock` による直列化を廃止し、要求の範囲 (`request_scope`) で接続を借り、1 要求 = 主接続の 1 transaction、advisory lock 2 段 (3a・3b)、transaction scope の idempotency lock にする。WP-1 の MitateDB 4 本と WP-2 の C-34 (MitateDB の 4 plug) をこの構造で緑にする。
**読むべき正本**: 設計 §2.1〜§2.5・§2.8・D-1〜D-6 (特に D-3 の段と帰結・拒否の優先順位・40P01・件数 lock・reap・順序・timeout)・§6・§9 の `CM` と migration の段・§12 の 1〜4・7〜13、M-1〜M-7・M-10〜M-12・M-14。**クラス**: B + C (conformance の adapter) + D (`_ISOMORPHIC_TARGETS` の集合が増減すれば)。`change_class.py` の実測を報告。**群**: レビュー群 2。

**触ってよいパス**: `M/cell.py`、`M/backend.py`、`M/backend_postgres.py`、`M/backend_sqlite.py`、`M/errors.py`、`M/http.py`、`M/main.py`、`M/pool.py` (WP-3 の上の写像に要るときだけ)、`MC/` (in-process adapter の SQLite の範囲、http adapter の `PostgresBackend(..., pool_size=)`・C-27 / C-34 の stalled method の追随、`MC/conformance_adapter_mitatedb.py`:118 の `_CLASSIFY_ORDER` が `M/http.py` の表を写すなら同じ行)、`MT/`、`docs/code-history/MitateDB-api/`。`M/config.py` の docstring と `M/startup_checks.py` の指紋は WP-7 で扱う (`M/main.py` を変えると `MT/test_ops_startup_checks.py` の `test_every_first_parent_fingerprint_is_in_the_table` が branch 上で赤になりうる。WP-7 で追随、R-115 作業指示書 訂正註 13 の (6) の先例)。

**実装の要点**:

1. **要求の範囲 (M-5、設計 D-6)**: `StorageBackend.request_scope(kind, *, deadline)` (kind ∈ {"schema", "dml", "query"}) を context manager として `M/backend.py` に足し、`RequestScope` を yield する。
   - `PostgresBackend`: `main` (schema = developer、dml / query = runtime) と `developer` (dml / query の pass 1 用。schema では main と同一) の接続を持つ。入口で developer → runtime の順に借り (pool の待ち上限 = deadline の残り、WP-3 の (i))、transaction を開き、`SET LOCAL statement_timeout` / `lock_timeout` を deadline から 1 回打つ (M-4)。出口で未 commit なら rollback → release。lock は範囲の中の決まった点で D-3 の順に取る (範囲自身は lock を取らない)。
   - `SQLiteBackend`: backend 自身の RLock を範囲全体 (idempotency の lookup → 実行 → store、`M/backend_sqlite.py`:745-749 の註) で保持し、接続欄は `None`。
   - backend のデータ / catalog メソッドは `scope=` を keyword 引数で受け取り、`self._developer` / `self._runtime` を参照しない。
   - `M/cell.py` は現行の外側 `with self._lock:` の位置 (20 箇所、下表) を `with self._backend.request_scope(kind, deadline=deadline) as scope:` に置き換え、内側の再入 `with self._lock:` を削除する。backend の種類で分岐しない。`_CountingRLock` (`M/cell.py`:508-603) と `self._lock` (:645) を消す。経緯コメント (:646-685) は逐語で扱う (§2.0 の注意 5)。

   | 現行の `with self._lock:` (`M/cell.py`) | メソッド |
   |---|---|
   | :744 | `prepared_stats` (作り替えは WP-5。WP-4 の時点の形は報告に書く) |
   | :1276・:1561 | `create_collection` |
   | :1687・:1857 | `add_field` |
   | :1941・:2120 | `alter_field` |
   | :2177・:2206 | `schema_revision`・`_schema_revision_uncounted` |
   | :2230 | `catalog` |
   | :2259・:2293 | `insert` |
   | :2364・:2408 | `read_page` |
   | :2547・:2555 | `update` |
   | :2701・:2719 | `delete` |
   | :2991・:3187 | `transact` |

2. **1 要求 = 主接続の 1 transaction と lock の順 (設計 D-3)**: 設計 D-3 の schema 操作と DML の段のとおり。catalog 読み群 (`schema_count` / `field_domains` / `field_types` / `all_field_types` / `field_constraints` / `field_types_and_constraints` / `all_field_constraints` / `schema_revision`、`M/backend_postgres.py`:420・:440・:518・:556・:613・:668・:710・:921) は渡された範囲の transaction の中で読み、自分で timeout を打たず自己 commit もしない (M-4)。schema 操作の本体 (`create_collection` :946、`add_field` :1092、`alter_field_constraints` :740) の既存の `_set_timeouts` 呼び出しは同じ transaction 内の打ち直しとして残してよいが、値は deadline 由来にする (M-4)。DML の pass 1 の catalog 読みは developer 接続で、3b の共有を取った後に行う (runtime role は registry を読めない、設計 §2.8)。
3. **lock の順序表 (設計 D-3、逐語。行番号は設計の基点 `173371d` の `M/backend_postgres.py`。現行は §0.2。表中の「本書」は設計を指す)**:

- 順序 (全要求がこの昇順で取り、上位を取った後に下位を取らない):

| 順 | lock | 取る要求 | scope・接続 | 出所 |
|---|---|---|---|---|
| 1 | per-key advisory lock `(76176100, hashtext(key))` | keyed・非 dry-run | transaction・主接続 (transact は runtime、schema 3 種は developer) | 現行は session 形、`M/backend_postgres.py`:1794 |
| 2 | 件数 advisory lock `(761761762)` | keyed・非 replay | transaction・主接続 | 現行は session 形、:1884 |
| 3a | schema 操作の直列化 lock (新、排他のみ) | schema 操作 | transaction・developer | 本書 |
| 3b | 実体単位の lock (新): schema 操作は対象実体を排他、DML は触る実体を共有 (key の昇順) | schema 操作・DML | transaction・主接続 (schema は developer、DML は runtime) | 本書 |
| 4 | 表 lock: `LOCK TABLE ... SHARE ROW EXCLUSIVE`、DDL の暗黙の表 lock、DML の行・表 lock | 各要求 | transaction | :818、:1152 |
| 5 | revision 行の行 lock | schema 操作 | transaction・developer | :939 |

4. **3a・3b の key と取り方 (M-10、M-7)**: 3a = `_SCHEMA_SERIALIZATION_LOCK_KEY = 761761763` (1 引数形、排他のみ、`pg_advisory_xact_lock`)。3b = `_ENTITY_LOCK_NAMESPACE = 76176101` (2 引数形、`hashtext(実体名)`)。既存の 76176100 (`M/backend_postgres.py`:233) / 761761761 / 761761762 (:241) と別値。migration は不要。DML は触る実体の重複を除いて昇順に並べ、M-7 の 1 文 (try 形) → false なら waits を 1 数えて block 形で取り直す。schema 操作の 3a・3b も同じ try → block の形 (各 1 文)。waits の数え方の器は WP-5 で公開する (WP-4 では数えるだけでよい)。
5. **idempotency の lock を transaction scope へ (設計 D-3 の帰結)**: per-key (`M/backend_postgres.py`:1728) と件数 (:1818) を `pg_advisory_xact_lock` にし、主接続の transaction の中で取る。`idempotency_begin` / `idempotency_reserve` の途中 commit と `idempotency_unlock` (:1845) は不要になる。session scope の理由を述べる docstring (:1655-1696、:1780-1792 ほか) の書き換えは §2.0 の注意 5 の規律。`M/cell.py` の `_idempotency_pg_scope` (:1169-1228) の役割 (接続の解決と `finally` の unlock) は同じ帰結で無くなる。扱いは報告に書く。
6. **拒否の優先順位 (M-11、設計 D-3 の K-2)**: `create_collection` の `schema_count` の上限検査 (`M/cell.py`:1321) を idempotency の受付 (:1474-1486) の後・3a の後へ移す。dry-run も同じ点で数える (設計 D-3 の dry-run の項)。field の検証と `enum_members` (:1323-1473) は受付の前に残す。
7. **例外の写像 (M-1、M-2)**: `M/errors.py` に `StorageTransientError(FoundationError)` を足し、`M/http.py` の `_CLASSIFY_ORDER` (:91-106) で `SERVICE_UNAVAILABLE` (503) に写す。`psycopg.errors.DeadlockDetected` (40P01) と `psycopg.errors.SerializationFailure` (40001) を `StorageTransientError` に写す (DML・idempotency の経路の残りの `except psycopg.Error → ValidationError` は変えない。M-1)。データ面の `PoolExhausted` → `ResourceLimitError(limit_class="execution_ms")`、`PoolConnectFailed` → `StorageTransientError`。lock 待ちの `LockNotAvailable` / `QueryCanceled` → `ResourceLimitError(execution_ms)` は現行どおり (:1762-1770)。F-12 の refusing cell の意味論は不変 (M-2)。
8. **pool の寸法と F-12 (M-8、M-12)**: application × role の pool 2 個を `PostgresBackend` が持つ。上限は `role_pool_size(thread_limit)`。`build_app` は `PostgresBackend(..., pool_size=)` に thread limit 由来の値を渡す (`M/main.py`:553)。`PostgresBackend.__init__` は接続を張らない。`build_app` は served application ごとに runtime の pool から 1 本借りて F-12 の検査 (現行は `M/backend_postgres.py`:330-366 の `__init__` の中) を行い、現行どおり 1 行記録して返す (`M/main.py`:556-567)。`MC/conformance_adapter_mitatedb_http.py`:1492 の構築は `role_pool_size(DEFAULT_THREAD_LIMIT)` を渡す。`DSA_PERF_POOL_SIZE` の類の新設定は足さない。
9. **`read_page` の decode (M-14、設計 D-5)**: `_decode_rows` (`M/cell.py`:3460) は pass 1 で読んだ field types を使い、catalog を読まない。`MT/test_r119_read_page_decode_under_lock.py` を「decode が範囲の外で catalog を読まない」を固定する形へ作り替える (backend の `field_types` が範囲の外で 1 度も呼ばれないこと、応答の decode が正しいこと)。
10. **作り替える既存テスト**: `MT/test_threadpool_offload.py`:561 (`test_pass1_and_pass2_serialize_through_cell_lock_no_developer_connection_race` → 「同一 application への並行要求が互いの transaction に触れない」)、`MT/test_postgres.py`:1021 (`begin()` を差し替えて窓を作る試験。差し替え点を範囲の中の同じ意味の地点へ移す)、`MT/test_r87_catalog_read_execution_ms.py` と `MT/test_r71_catalog_read_cancel_mapping.py` (catalog 読みの timeout の形が M-4 で変わる)、WP-1 の 4 本の wrap 点 (名前が変われば同じ意味の地点へ移す。assert は変えない)、`MC/` の C-27 の stalled method (`MC/conformance_adapter_mitatedb.py`:527、`MC/conformance_adapter_mitatedb_http.py`:859)。作り替えは報告に旧 → 新の test 名で残す。

**完了条件 (37〜71) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 37 | 静的テスト: `M/backend_postgres.py` に `self._developer` / `self._runtime` の参照が 0 件 (数え方は pool の属性名と衝突しない形を選び、報告に書く) | V37: `self._developer` の参照を 1 つ足す |
| 38 | 静的テスト: `M/cell.py` に `self._lock`・`_CountingRLock`・`SQLiteBackend`・`PostgresBackend` の名前が 0 件 (M-5) | V38: `M/cell.py` に `self._lock` の参照を 1 つ足す |
| 39 | 原子性 (SI-11、設計 §6): `MT/test_foundation.py`:111・`MT/test_postgres.py`:697 ほかの既存の証拠が範囲の形で緑 | V39: `transact` の 2 つの operation の間に commit を入れる |
| 40 | C-27 が MitateDB の in-process plug で SQLite の範囲の lock に依存して緑 (設計 §6 の C-27 行、K-5) | V40: SQLite の範囲の RLock を外す |
| 41 | C-27 の (i)(ii) が MitateDB-http で per-key lock (xact) に依存して緑 | V41: per-key lock を外す |
| 42 | C-27 の (iii) が MitateDB-http で件数 lock (xact) に依存して緑 | V42: 件数 lock を外す |
| 43 | 要求の後に pool へ返った接続が advisory lock を 1 つも持たない (`pg_locks`) | V43: per-key lock を session 形 (`pg_advisory_lock`) に戻す |
| 44 | 接続の非共有: 同一 application への並行要求が互いの transaction に触れない (作り替えた `MT/test_threadpool_offload.py` の試験) | V44: 2 要求に同じ接続を渡す |
| 45 | WP-1 の MitateDB の 4 本 (開1〜開4) が緑。V1〜V5・V9 をここで実行し、表に残す | 監査照合 (集計行の逐語。変異は V1〜V5・V9) |
| 46 | 並行性: 同一 application の 2 要求が同時に pass 2 にいることを観測する | V46: pool の上限を 1 にする |
| 47 | 監査の順序: `MT/test_application_audit.py`:1705・:1866 ほかの既存テストが緑 (設計 §6 の「既存」) | 監査照合 (集計行の逐語) |
| 48 | audit pool (M-3): audit pool の `max_size=1` で 1 本を借りたまま schema 操作を出すと有界の時間で 503 になり、借りた 1 本を返した後の次の schema 操作は成功する | V48: 範囲の出口の release / rollback を消す |
| 49 | lock 順序 (設計 §6、L-2): keyed `create_collection` × keyed `add_field` を交差させて 40P01 が出ない | V49: `create_collection` だけ 3a を受付の前に取る |
| 50 | 実体単位の粒度 (K-1): 実体 A の schema 操作が待っている間に実体 B の DML が通る | V50: 3b の key を固定値にする |
| 51 | D-4: schema 操作が lock を持つ間も別実体の query が通る | V51: query に 3b を取らせる |
| 52 | lock 待ちの timeout の写像: deadline の超過で `LIMIT_EXCEEDED(execution_ms)` (M-6 の共有 lock 待ちを含む) | V52: 範囲の入口の timeout の設定を消す |
| 53 | pool の取得待ちの超過が `LIMIT_EXCEEDED(execution_ms)` (M-2) | V53: `PoolExhausted` の写像を外す |
| 54 | データ面の接続失敗が `SERVICE_UNAVAILABLE` (M-2) | V54: `PoolConnectFailed` の写像を外す |
| 55 | 40P01 の写像 (M-1): 逆順に行を更新する 2 batch で、client 起因の code にならず `SERVICE_UNAVAILABLE` | V55: 40P01 の写像を消す |
| 56 | 40001 も `SERVICE_UNAVAILABLE` (M-1) | V56: 40001 を写像から外す |
| 57 | catalog 読み群は範囲の transaction の中で読み、自己 commit せず、自分で timeout を打たない (M-4) | V57: `schema_revision` に commit を戻す |
| 58 | schema 操作の本体の timeout の値は deadline 由来 (M-4。構築時の `max_execution_ms` の無条件の値ではない) | V58: 構築時の `max_execution_ms` を使う形に戻す |
| 59 | DML の 3b は触る実体の重複を除いた昇順の配列を 1 文で取る (M-7) | V59: 並べ替えを外す |
| 60 | 3a / 3b の key が M-10 の値で、既存の 3 値と別 | V60: 3a の key を 761761762 にする |
| 61 | 拒否の優先順位 (M-11): 上限に達した状態での同一 key・同一 digest の再送が replay | V61: `schema_count` の検査を受付の前に戻す |
| 62 | dry-run が実行と同じ点 (3a・3b の後、同じ transaction) で `schema_count` と revision を読む (M-11、設計 D-3) | 監査照合 (`file:line` と該当の diff) |
| 63 | 起動時の F-12 (M-12): 台帳未適用の application が refusing cell になり 1 行記録され、他の application は serve する | V63: 起動時の検査を消す |
| 64 | `PostgresBackend.__init__` は接続を張らない (M-12) | V64: `__init__` で runtime の pool から 1 本借りる |
| 65 | `build_app` が `role_pool_size(thread_limit)` を、http adapter が `role_pool_size(DEFAULT_THREAD_LIMIT)` を pool の上限として渡す (M-8) | V65: `build_app` で `pool_size` を渡さない |
| 66 | 借用順 (K-3、L-7): pool 上限 1・同じ実体の DML と schema 操作の並行 2 要求で輪にならず deadline で打ち切られる | V66: lock を取ってから developer を借りる |
| 67 | `read_page` の decode が範囲の外で catalog を読まない (M-14。作り替えた `MT/test_r119_read_page_decode_under_lock.py`) | V67: decode を範囲の外の catalog 読みに戻す |
| 68 | WP-2 の C-34 が MitateDB の 4 plug で緑。V17・V18 をここで実行する | 監査照合 (集計行の逐語。変異は V17・V18) |
| 69 | `MT` の suite と §「発注の穴」の conformance が failed 0・skipped 0 (branch 上の指紋の test の赤は WP-7 の対象として除いて報告) | 監査照合 (集計行の逐語) |
| 70 | `check_comment_provenance.py --base main` と `--register` の結果、`docs/code-history/MitateDB-api/` の訂正 | 監査照合 (出力の逐語) |
| 71 | 本表に対応の無い行が無い | 監査照合 |

**発注の穴**: テスト = `tools/dev/pt.py -C .claude/worktrees/r102 -- MitateDB-api/tests -q` と `-- conformance-tests/test_c05_limit_declaration_agreement.py conformance-tests/test_c06_destructive_confirmation.py conformance-tests/test_c07_atomicity_and_retry.py conformance-tests/test_c09_audit_evidence.py conformance-tests/test_c16_cross_entity_atomicity.py conformance-tests/test_c22_dry_run_and_plan.py conformance-tests/test_c23_idempotency_semantics.py conformance-tests/test_c27_concurrent_same_key.py conformance-tests/test_c34_<name>.py -q`。変異 = `tools/dev/mutate.py "$SP/r102-wp4-mutations.json" -C .claude/worktrees/r102` (V37〜V67 と、WP-1・WP-2 の後送り分 V1〜V5・V9・V17・V18)。報告 = `$SP/r102-wp4-report.md`。

**レビューの観点**: 設計 §12 の 1 (1 → 2 → 3a → 3b の網羅、共有を持つ DML と `LOCK TABLE` を待つ schema 操作の経路)・2 (D-4)・3・4 (返却後の状態)・8 (audit pool との待ちの連鎖、M-3)・9 (DDL の timeout、M-4)・11 (cell に backend の種類の分岐が残らない)・12 (長い schema 操作の transaction、M-6)・13 (3b の取得数、M-7)。F-12 の意味論の不変。拒否の優先順位の変化が M-11 の範囲に留まること。

### 2.5 WP-5 — 計測器 (設計 D-7。実装担当)

**目的**: `_CountingRLock` の統計 (`POOL lock=` 行) の代わりに、pool の acquire / waits (r2db の `POOL role=` 行と同じ形) と schema lock の行 (`schema_lock=<application>`、3a と 3b の合算) を出す (設計 D-7、M-15)。
**読むべき正本**: 設計 D-7・§8。現物: `tools/perf_baseline.py`:944-969 (`_format_pool_row`。形は keys で選び、peer 名で選ばない = 同 docstring)、:972 (`_emit_pool_rows`)、`MC/conformance_adapter_mitatedb_http.py`:3379-3390 (`pool_stats` = `cell._lock.stats()`)・:3392 (`prepared_stats`)、r2db の key の形 `"<application_id>/<role>"` (`RC/conformance_adapter_r2db_http.py`:4200-4207)、`tools/PERF_BASELINE_README.md`:265-307、`tools/tests/test_perf_baseline.py`:239-246、`MT/test_r78_pool_wait_stats.py`:138、`MT/test_r79_prepared_stats.py`:120、`docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md`:993 (O-3)。**クラス**: B。**群**: レビュー群 3 (WP-5+6)。

**触ってよいパス**: `tools/perf_baseline.py`、`tools/PERF_BASELINE_README.md`、`tools/tests/test_perf_baseline.py`、`MC/conformance_adapter_mitatedb_http.py` (`pool_stats` / `prepared_stats`)、`M/backend_postgres.py` (schema lock の統計の器と、pool の統計の公開だけ)、`M/cell.py` (`prepared_stats` だけ)、`MT/test_r78_pool_wait_stats.py`、`MT/test_r79_prepared_stats.py`。

**実装の要点**: `pool_stats()` は application ごとに runtime / developer の pool の `stats()` (6 keys、`M/pool.py`:190-200) を r2db と同じ key の形で返し、加えて schema lock の統計 (acquire / waits / wait_total_ms / wait_max_ms、3a と 3b の合算) を application の key で返す。「待ち」は try 形で取れなかった取得 (設計 D-7)。`_format_pool_row` は keys で 3 つ目の形 `schema_lock=<key>` を選ぶ。

**完了条件 (72〜80) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 72 | `pool_stats()` が application ごとの runtime・developer の role 行を返す | V72: developer の行を返さない |
| 73 | `pool_stats()` が application ごとの schema lock の行 (3a と 3b の合算) を返す | V73: 3b の取得を数えない |
| 74 | schema lock の waits は try 形で取れなかった取得の数で、競合の無い取得では増えない | V74: try の失敗を数えない |
| 75 | `_format_pool_row` が keys で `POOL ... schema_lock=<key> acquire=<n> waits=<n> wait_total_ms=<x.xxx> wait_max_ms=<x.xxx>` を印字する (`tools/tests`) | V75: schema lock の形を role の形で印字する |
| 76 | `MT/test_r78_pool_wait_stats.py`:138 の cell lock の試験を pool / schema lock の統計の試験に作り替えた | V76: pool の `_record_wait` を呼ばない |
| 77 | `MT/test_r79_prepared_stats.py`:120 と `prepared_stats` の docstring (R-101 作業指示書 :993 の O-3) を lock 無しの形に作り替えた | V77: `prepared_stats` が backend の probe を呼ばず `[]` を返す |
| 78 | `tools/PERF_BASELINE_README.md`:265-307 の lock 行の説明を新しい 2 つの行に合わせた | 監査照合 (`git diff`) |
| 79 | `tools/dev/pt.py -C .claude/worktrees/r102 -- tools/tests -q` と `MT` の 2 file が failed 0 | 監査照合 (集計行の逐語) |
| 80 | 本表に対応の無い行が無い | 監査照合 |

**発注の穴**: テスト = `tools/dev/pt.py -C .claude/worktrees/r102 -- MitateDB-api/tests/test_r78_pool_wait_stats.py MitateDB-api/tests/test_r79_prepared_stats.py -q` と `-- tools/tests -q`。変異 = `tools/dev/mutate.py "$SP/r102-wp5-mutations.json" -C .claude/worktrees/r102`。報告 = `$SP/r102-wp5-report.md`。

**レビューの観点**: D-R102 の判定値 (§3) がこの行から式どおりに読めること (分母・分子の出所)。keys で形を選ぶ規律。harness 由来の借用の扱い (`tools/PERF_BASELINE_README.md`:265-274)。

### 2.6 WP-6 — r2db (設計 D-8。実装担当)

**目的**: 設計 D-8 (Q-5 で「足す」)。r2db の `apply_schema` の lock を `_load_catalog` より前に置き、plan・確認句・`schema_objects` の 3 窓を閉じる。WP-1 の r2db の 3 本と WP-2 の C-34 の r2db-http / r2db-socket を緑にする。
**読むべき正本**: 設計 §2.6・D-8・§6。現物: `R/postgres.py`:2067-2446 (`apply_schema`。接続 :2101、`_load_catalog` :2106、per-key lock と lookup :2125-2126、件数 lock :2146-2147、revision の読み :2150、`schema_objects` :2163-2184、`enum_members` :2205、`drop_entity` の確認句 :2218、`drop_index` の確認句 :2363、revision の加算 :2399)、:1381・:1401 (idempotency の xact lock の書き方)、:188-207 (advisory lock の namespace の註)。**クラス**: B (+ D: `_ISOMORPHIC_TARGETS` の集合が増減すれば)。**群**: レビュー群 3。

**触ってよいパス**: `R/postgres.py`、`RT/` (WP-1 のテストの assert は変えない)、`RC/` (C-34 の stalled method の追随が要るときだけ)、`RT/test_audit_query.py` と `MT/test_audit_query.py` (`_ISOMORPHIC_TARGETS` の表と件数 pin だけ)、`docs/code-history/r2db-api/`。

**完了条件 (81〜87) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 81 | WP-1 の r2db の 3 本が緑。V6〜V8 をここで実行する | 監査照合 (集計行の逐語。変異は V6〜V8) |
| 82 | WP-2 の C-34 が r2db-http・r2db-socket で緑。V19 をここで実行する | 監査照合 (集計行の逐語。変異は V19) |
| 83 | r2db の lock を取る点が `_load_catalog` (`R/postgres.py`:2106) より前 | V83: lock を `schema_objects` の検査の後へ移す (`schema_objects` の試験が赤) |
| 84 | `RT` の suite と r2db の conformance (C-22・C-23・C-27・C-34) が failed 0・skipped 0 | 監査照合 (集計行の逐語) |
| 85 | 全 WP の後の `_ISOMORPHIC_TARGETS` の集合と件数 pin を実測で合わせた (`OC` §1.5 の 40b。集合が変わらなければその実測) | V85: 表に 1 行足す (pin が赤)。集合が変わらないときは監査照合 (`git diff` と pin の集計行) |
| 86 | `check_comment_provenance.py --base main` と `--register` の結果 | 監査照合 (出力の逐語) |
| 87 | 本表に対応の無い行が無い | 監査照合 |

**発注の穴**: テスト = `tools/dev/pt.py -C .claude/worktrees/r102 -- r2db-api/tests -q` と `-- conformance-tests/test_c22_dry_run_and_plan.py conformance-tests/test_c23_idempotency_semantics.py conformance-tests/test_c27_concurrent_same_key.py conformance-tests/test_c34_<name>.py -q`。変異 = `tools/dev/mutate.py "$SP/r102-wp6-mutations.json" -C .claude/worktrees/r102` (V83・V85 と後送り分 V6〜V8・V19)。報告 = `$SP/r102-wp6-report.md`。

**レビューの観点**: 新しい lock と既存の per-key / 件数 lock の順 (DML の `transact` と交差して輪にならないか)。replay の答え方の変化の有無 (lock を lookup の前に取る。設計 Q-9 の対案の費用の記述)。r2db の in-process plug (`R/structured.py` の `_idempotency_lock`) との挙動の差。

### 2.7 WP-7 — 記録 (監督。起草担当に渡してよい)

**読むべき正本**: 設計 §9・§10、M-15 の WP-7 の列挙、`OC` §1.8 の 56、§1.16 の 78・79。R-115 作業指示書 §8 (記録の WP の形)。**クラス**: D。**群**: レビュー群 4。

**触ってよいパスと記録の対象** (行番号は起草時点。WP-1〜WP-6 の後に引き直す):

| 対象 | 行 | 書くこと |
|---|---|---|
| `CM` | :5 | 版 3.13 → **3.14** (変更セットごとに 1 版、`OC` §1.13 の 75) |
| `CM` | :850-857 | catalog 読み 8 本が各自 transaction を開き無条件に `SET LOCAL` を打つという主張 (:854) と、要求単位ではなく文単位という主張 (:856) を M-4 の実挙動に書き換える |
| `CM` | :980 | 「per-application `PostgresBackend` pools nothing」を application × role の pool の実挙動に書き換える |
| `CM` | :999-1001 | cell lock の 3 主張 (`M/cell.py:645`) を範囲・3a / 3b・xact の idempotency lock の主張に書き換える |
| `CM` | :1030 | 証拠の旧 test 名 (`test_pass1_and_pass2_serialize_through_cell_lock_no_developer_connection_race`) を WP-4 の作り替え後の名に |
| `CM` | :1501・:1506 | SI-11 の証拠 (`begin()` の差し替え) と Status の窓の記述を WP-4 の実挙動に |
| `CM` | :868 | `_ISOMORPHIC_TARGETS` の件数 pin の名が WP-6 で変わったときだけ追随 |
| `COND` | :34 (C-05) | Concurrency note の「`MitateDB-api` allows one in-flight op per cell (`ApplicationCell._lock`)」を、SQLite plug は backend の lock の下で真、http plug について改める形に (設計 §9) |
| `COND` | :56 (C-27) | 変異指定を plug ごとに分ける (設計 §6 の C-27 行)、開示済みの限界 (「SESSION advisory locks」の語) を xact へ |
| `COND` | C-34 の行 | Status の〈〉の部分を WP-4・WP-6 の実測 (plug ごとの赤になる変異、観測の範囲) で埋める |
| `CT/adapter.py` | :1802-1810 | `hold_in_flight` の docstring の (ii) (「at most one in-flight operation PER CELL」) |
| `CT/test_c27_concurrent_same_key.py` | :57-74 (:59 の「session advisory lock」の語を含む) | 開示の段を実挙動に |
| `CR` | :509-531、:1717-1731 (§6.5) | 接続の式 (「persistent connections」) を pool の実挙動に |
| `M/config.py` | :362-366 | `role_pool_size` の docstring の「This peer's per-application data path is NOT pooled at all」の段 |
| `docs/design/MULTI_PROCESS_WORKER_V0_1.md` | :26 | 行を消さず、R-102 で覆った根拠と日付の註を足す (`OC` §1.8 の 56。版は上げない = 設計 L-9) |
| `M/startup_checks.py` | :1013 (`KNOWN_FINGERPRINTS`) | 現行世代の行の指紋を最終の `M/main.py`・`M/config.py`・`M/platform_declarations.py` に合わせる (世代は足さない。手順の出所は R-115 作業指示書 訂正註 3 と 13 の (6)) |
| `RM` | :462 (R-102) | 閉止: 行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の末尾へ逐語で移し §8.2 に索引行 (`OC` §1.16 の 79) |
| `RM` | :58 (§0.1.3 の G-4 行) | 【再実測】(§3 の D-R102 の結果、R-102 の閉止) |
| `RM` | 版数行 | 版上げと版数ログの回転 (`OC` §1.16 の 78) |
| 本書 | §5 | 記録 |

**完了条件 (88〜98) → 変異**:

| # | 完了条件 | 変異 |
|---|---|---|
| 88 | `CM` の上の行が WP-4・WP-6 の実挙動と実測した test 名を引いて書き換えられ (`OC` §1.5 の 34)、版が 3.14 | 監査照合 (`git diff`) |
| 89 | `pt.py -- conformance-tests/test_control_mapping_register.py -q` が緑 (主張は 300 字以内、参照が解決する) | 監査照合 (集計行の逐語) |
| 90 | 変更した各ファイルについて `grep -c '<path>:' security/CONTROL_MAPPING.md` の件数を前後で記録し、行参照が現物に追随している | 監査照合 (コマンドと出力の逐語) |
| 91 | `COND` の C-05・C-27・C-34 の行、`CT/adapter.py`:1802-1810、`CT/test_c27_concurrent_same_key.py`:57-74 が実挙動に合い、`pt.py -- conformance-tests/test_conditions_register.py -q` が緑 | 監査照合 (`git diff` と集計行の逐語) |
| 92 | `CR` の 2 箇所が pool の実挙動に合い、`CR` の §10 (受理済み) の sha256 が変更の前後で一致 (R-115 作業指示書 §8.3 の確かめ方) | 監査照合 (前後の出力の逐語) |
| 93 | `M/config.py` の docstring と `docs/design/MULTI_PROCESS_WORKER_V0_1.md`:26 の註 | 監査照合 (`git diff`) |
| 94 | `KNOWN_FINGERPRINTS` が更新され、merge 候補の上で `MT/test_ops_startup_checks.py` が緑 | 監査照合 (集計行の逐語) |
| 95 | 台帳: R-102 の閉止 (移動と索引行)、G-4 行の【再実測】、版数行と回転。`python3 tools/dev/ledger.py --check` が緑 | 監査照合 (出力の逐語) |
| 96 | `tools/check_doc_refs.py`・`tools/public_value_scan.py <触った全パス>` が緑、`tools/change_class.py <全変更セットのパス>` が D | 監査照合 (出力の逐語) |
| 97 | §5 に commit・ゲート・計測・監査の記録がある | 監査照合 |
| 98 | 本表に対応の無い行が無い | 監査照合 |

## 3. 計測 D-R102 (監督)

**判定規則** (設計 §8 の逐語。計測の前に固定し、計測の後に動かさない):

```text
D-R102 判定規則 (計測前に固定。計測後に動かさない):
  plug: MitateDB-api-http と MitateDB-api-socket (in-process の 2 plug。POOL 行が出る)。
  条件: K=4、--warmup 10 --n 100、thread limit 既定 (4)、2 run。
        DSA_PERF_POOL_SIZE は設定しない (既定)。--roundtrip は付けない。
  読む行: 各 run・各 plug の perf 用 application (perfbase_<id>) の op=cross_entity の POOL 行
          (その run の最後の POOL 行で、query / mutate / batch / cross_entity の累積。
          RM §0.1.4 の 3 の出所 985/3530 と同じ行、PERF_CONCURRENCY_MEASUREMENT_V0_1.md:179)。
          cap_probe_* の行は読まない。
  判定値: その op の role 行 (runtime・developer) と schema_lock 行 (3a・3b の合算) の
          waits の和 / acquire の和。分母は読む行が印字する acquire をそのまま使う
          (harness 由来の借用を引かない。tools/PERF_BASELINE_README.md:265-274)。
  「待ち」: pool は既存の定義、schema lock は D-7 の try 形で取れなかった取得。
  判定: 2 run とも 10% 以下 = RM §0.1.4 の 3 (Q-2 の読み替え後) を満たす。
  基準値: 実装前に同じ条件で取る (同じ行の lock= 行。thread limit 4 での値は未計測)。
          基準値を取る木は R-102 の実装 branch の分岐点の main (R-115 merge 後)。
          前後は同じ日に交互 (interleave) に取る。
  開示: 分母の数え方が前後で違う (前 = RLock の再入を数える / 後 = pool の借用を数える)。
  併せて記録する (判定に使わない): K=1 の非退行 (RM §0.1.4 の 1、完了ゲートで判定)、
          backend_calls の差分と理由 (RM §0.1.4 の 4)、real-server plug の N=1 / N=4 の K=1・K=32
          (R-101 作業指示書 D-16 と同じ手順)、K=4 の query / mutate の p50 の前後。
  実施条件: 各 run の開始時の 1 分 load average が 3.0 以下。超えた run は捨てて取り直す
          (先例: 採用 run は 2.12 と 1.63、12〜15 の run は破棄。MULTI_PROCESS_WORKER_V0_1.md:575、:577、:611)。
          他の pytest と nginx 無し。
```

**併せて取るもの** (枠の計測の節): K=1 `--warmup 20 --n 200` (`RM` §0.1.4 の 1 の退行閾値 = p50 +40% / p95 +50%。完了ゲートの性能差分)、real-server plug の N=1 / N=4 の K=1・K=32 (R-101 作業指示書 §10.1 の D-16 と同じ手順)、`backend_calls` の差分と理由 (`RM` §0.1.4 の 4、M-7 の往復の増分)、K=4 の `query` / `mutate` の p50 の前後。

**実施手順**:

1. 時機 (M-15): 基準値 = WP-3 の前 (木 = r102 の分岐点の main)。実装後 = WP-7 の後 (木 = branch の最終の tree)。前後は同じ日に交互 (interleave) に取る (設計 §8)。
2. 各 run の開始時に 1 分 load average を記録し、3.0 を超えた run は捨てて取り直す。他の pytest と nginx が無いことを確かめる (設計 §8 の実施条件)。
3. 読む行: 各 run・各 plug の `perfbase_<id>` の `op=cross_entity` の POOL 行 (その run の最後の POOL 行)。基準値は `lock=` 行、実装後は role 行 (runtime・developer) と `schema_lock=` 行。`cap_probe_*` の行は読まない。
4. 出力は `$SP/perf-r102-*.txt` に保存し、表には行の逐語から転記する。無効とした run は理由とともに §5.3 に書く。

**記録表の雛形** (§5.3 に置く。R-115 作業指示書 §10.3、R-101 作業指示書 D-16 の形):

表 A — D-R102 の判定 (K=4、`--warmup 10 --n 100`、thread limit 4、2 run):

| run | 木 | 開始時の load average | plug | 基準値: `lock=` waits / acquire | 実装後: runtime 行 waits / acquire | 実装後: developer 行 waits / acquire | 実装後: `schema_lock=` 行 waits / acquire | 判定値 (waits の和 / acquire の和) | 10% 以下 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | | MitateDB-api-http | | | | | | |
| 1 | | | MitateDB-api-socket | | | | | | |
| 2 | | | MitateDB-api-http | | | | | | |
| 2 | | | MitateDB-api-socket | | | | | | |

表 B — 併記 (判定に使わない):

| 計測 | 形 | r2db-api p50 / p95 | MitateDB-api p50 / p95 |
|---|---|---|---|
| K=1 全 plug・全 op | `tools/perf_baseline.py --warmup 20 --n 200` | | |
| K=4 `query` / `mutate` の p50 の前後 | D-R102 の run の PERF 行 | | |
| real-server N=1 K=1 / K=32 (比) | `tools/perf_baseline.py --real-server <peer> --workers 1` | | |
| real-server N=4 K=1 / K=32 (比) | `tools/perf_baseline.py --real-server <peer> --workers 4` | | |

表 C — `backend_calls` の差分 (`RM` §0.1.4 の 4):

| plug | op | 基準値 | 実装後 | 差分 | 理由 (3a・3b の文、M-7 の try → block、catalog 読みの同一 transaction 化 など) |
|---|---|---|---|---|---|

## 4. 完了ゲートと受け入れ (監督)

- 完了ゲート: merge 候補 (local main に branch `r102` を `--no-ff` で merge した候補) の上で `tools/dev/gate.py -C <候補の worktree> --label r102` を単独実行する (レビュー担当・監査担当が pytest を走らせていないことを確かめてから)。集計行だけを正本にする (`OC` §1.6 の 41)。`-C` を渡し忘れると main を測る。
- `CT/COLLECTION_FLOOR` をゲートの実測に更新する (候補の上の commit)。
- `tools/tests` は `tools/dev/pt.py -C <候補の worktree> -- tools/tests -q` を別に回す (WP-5 が触る)。
- pre-commit (公開値スキャン・doc 参照・台帳の固定欄) が緑。commit は `tools/dev/finalize.py`。
- 性能: §3 の表 A の判定と、表 B の K=1 を `RM` §0.1.4 の 1 と突き合わせる。超えたら依頼者へ上げる。
- 受け入れ監査 (`evidence-auditor`、`ROLES` の 6): 全群のコードレビューの後に 1 回。監査対象は本書 §2 の全完了条件。パケットの「裁定」節は見出しと空表だけ。
- 閉止の前に、§1 の M-1〜M-16 と閉止までに出た監督裁定の一覧を依頼者に示して確認を求める (§0)。

## 5. 記録 (統合時に監督が埋める)

### 5.1 commit

branch `r102` (基点 main `ddf9c73`、WP ごとの WIP commit 24 + 並行 worktree の merge 14。並行 worktree: r102-wp1b / r102-wp2 / r102-wp3 / r102-wp6 / r102-wp7)。main へは merge 候補 `r102-merge` (main に `r102` を `--no-ff` で merge) を経て 1 回。

| WP | commit (本体 → レビュー後 → 再確認後) |
|---|---|
| WP-1 | `1d24454` → `fd0479d` → `b01ec6e` |
| WP-2 | `9cb6787` → `e205819` → `9957afd` |
| WP-3 | `361f3bd` → `a3c6078` → `610d641` |
| WP-4 | `ff408fa` → `c29eb61` → `eb97a06` (WP-4/5 再確認) → `0d8ffd0` (差し戻し 2、訂正註 6) |
| WP-5 | `32eefb0` → `4a37988` → `5e0cb08` |
| WP-6 | `a2f9735` → `3d2656e` → `10f7833` |
| WP-7 | `400f527` → `6116807` (訂正註 5、ops の式) → `0cd6fa0` → `d4bb075` (最終一括、訂正註 7、引き継ぎ書) → `3a03608` (指紋の行) |

### 5.2 完了ゲート

監督、候補 `4d7181a` (main `ddf9c73` + branch `r102` `22fc73a`、`--no-ff`) の上で単独実行: `gate: 4927 passed, 2 subtests passed in 464.40s (0:07:44)`、judge=PASS、pg_database/pg_roles diff 0 (label r102、2026-10-01 16:27、merge 候補 `4d7181a` = main `ddf9c73` + branch `r102` `22fc73a`)。`COLLECTION_FLOOR` 4855 → 4927。`tools/tests` は候補の上で別に実行 (§5.4)。branch の先頭では `MitateDB-api/tests/test_ops_startup_checks.py::test_every_first_parent_fingerprint_is_in_the_table` だけが赤 (first-parent の履歴に branch の途中の commit が入るため。訂正註 4 / R-115 の先例)。

### 5.3 計測 D-R102

監督、2026-10-01。木: 基準値 = 分岐点の main `ddf9c73` (worktree `r102-base`)、実装後 = `r102` の `3a03608` (製品コードは `0d8ffd0` で確定。`3a03608` は指紋の行のみ)。前後を同じ日に交互に取った (round 2)。各 run の開始時の 1 分 load average は 1.69〜2.50 (すべて 3.0 以下)。開示: 実装後の木は K=4 run 1 以外 `commit=3a03608-dirty` (本書 §5 の未 commit の記録が作業ツリーにあった。製品コードは同じ)。他の pytest と nginx は無し。出力は scratchpad の `perf-r102-<before|after>-<k4|k1|rs-…>-run<N>.txt` (K=4 と K=1 は 2 run、real-server は 1 run)。**round 1** (12:38〜12:48、実装後 = `eb97a06`) は K=1 で MitateDB-http の p50 が +176〜226% の退行を示し (訂正註 6: ROLLBACK による prepared statement の破棄)、M-19 の直しの後に全段を取り直した (round 1 の K=4 の判定値も 0/4856 = 0.0% で同じ)。

表 A — D-R102 の判定 (K=4、`--warmup 10 --n 100`、thread limit 4、2 run。読む行 = `perfbase_<id>` の op=cross_entity の POOL 行):

| run | 木 | load | plug | 基準値: `lock=` waits / acquire | 実装後: runtime | developer | `schema_lock=` | 判定値 | 10% 以下 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | before / after | 1.69 / 2.00 | MitateDB-api-http | 1319 / 3537 (37.3%) | 0 / 1762 | 0 / 1765 | 0 / 1329 | 0 / 4856 = 0.0% | 満たす |
| 1 | before / after | 1.69 / 2.00 | MitateDB-api-socket | 1319 / 3537 (37.3%) | 0 / 1762 | 0 / 1765 | 0 / 1329 | 0 / 4856 = 0.0% | 満たす |
| 2 | before / after | 2.38 / 2.25 | MitateDB-api-http | 1319 / 3537 (37.3%) | 0 / 1762 | 0 / 1765 | 0 / 1329 | 0 / 4856 = 0.0% | 満たす |
| 2 | before / after | 2.38 / 2.25 | MitateDB-api-socket | 1319 / 3537 (37.3%) | 0 / 1762 | 0 / 1765 | 0 / 1329 | 0 / 4856 = 0.0% | 満たす |

判定: 2 run とも 10% 以下 → `RM` §0.1.4 の 3 (設計 Q-2 の読み替え後) を満たす。開示: 分母の数え方が前後で違う (前 = RLock の再入を数える / 後 = pool の借用 + schema lock の取得を数える)。

表 B — 併記 (判定に使わない。query p50 / p95、2 run の平均、`$SP/perf-r102-k1-summary-round2.txt`・`perf-r102-rs-summary-round2.txt`):

| 計測 | 形 | r2db-api | MitateDB-api |
|---|---|---|---|
| K=1 全 plug・全 op | `tools/perf_baseline.py --warmup 20 --n 200` (6 plug) | p50 −1.8〜+1.4%、p95 −5.5〜+15.6% (http batch の p95 +15.6% が最大) | in-process p50 −2.8〜+4.2% / p95 −0.7〜+6.2%; http p50 −16.8〜−0.8% / p95 −16.9〜+1.0% (query 1.527 → 1.377 ms); socket p50 −9.2〜−2.3% / p95 −13.4〜−4.3% |
| K=4 query / mutate の p50 (http plug、round 2 の 2 run) | D-R102 の run の PERF 行 | — | query 5.21 / 5.33 → 4.16 / 4.15 ms、mutate 4.11 / 4.07 → 4.02 / 3.94 ms (基準値は cell lock の待ちを含む) |
| real-server N=1 K=1 / K=32 (比) | `--real-server <peer> --workers 1` (K=1: `--warmup 20 --n 200`、K=32: `--warmup 3 --n 15`) | 2.573 → 2.556 ms / 42.836 → 43.272 ms (16.65 → 16.93 倍) | 2.307 → 2.345 / 39.353 → 39.991 (17.06 → 17.05 倍) |
| real-server N=4 K=1 / K=32 (比) | 同 `--workers 4` | 2.571 → 2.546 / 27.640 → 26.757 (10.75 → 10.51 倍) | 2.354 → 2.268 / 24.779 → 24.978 (10.53 → 11.01 倍) |

`RM` §0.1.4 の 1 (K=1: p50 +40% / p95 +50%) はすべて内側。§0.1.4 の 2 (K=32 / K=1 ≤ 8) は本件の対象外 (R-101、設計 §10) で、前後とも変わらない。K=32 の real-server を `--warmup 20 --n 200` で取ると credential の rate (600/min) を超えて 429 になる (記録 `perf-r102-round2-rs32-n200/`)。

表 C — `backend_calls` (K=1):

| plug | op | 基準値 | 実装後 | 理由 |
|---|---|---|---|---|
| MitateDB-api-http / -socket | query / mutate / batch / cross_entity | 23 / 15 / 51 / 24 | 17 / 14 / 34 / 19 | catalog 読み 8 本の自己 commit と各自の `SET LOCAL` が無くなり、範囲の入口の `SET LOCAL` 2 文 × 2 接続に集約。per-key / 件数 / 3a / 3b の lock 文 (try 形) が加わる。読み取り transaction の COMMIT (M-19) は `cursor.execute` ではなく数に入らない |
| MitateDB-api (SQLite) | query / mutate / batch / cross_entity | 11 / 9 / 37 / 16 | 12 / 11 / 39 / 18 | `request_scope` / `lock_schema` / `lock_entities` (no-op) が public method として数えられる |
| r2db-api (3 plug) | query / mutate / batch | 1 / 1 / 1、18 / 19 / 23 | 不変 | schema lock は `apply_schema` だけ (計測の op に無い) |

### 5.4 受け入れ監査と閉止

- 受け入れ監査 (`evidence-auditor`、候補 `4d7181a`、パケット = scratchpad の `acceptance-packet-r102.md`): 充足が主。未充足 / 証拠不足 = 完了条件 90 (grep の前後値が最終の木に無い → 下に記録)、97 (§5.2 / §5.4 が空 → 本節)、98a の 1 件 (`CM`:1469 の `backend_postgres.py:480` → :481-482、直した)、§3 の K=4 の p50 の前後 (round 2 の値を §5.3 表 B に記録)、§4 の `tools/tests` (候補 `4d7181a` で `1 failed, 783 passed` = `test_0f_both_peers_all_src_rev_vs_itself_is_green` の CH-0547 → `c3e5ca7` で直し、最終候補で再実行)。主張 vs 実測: CM の R-102 の行 175 行のうち test 名 56 件・file:line 88 件がすべて解決、内容は 26 件を読み不一致 1 件 (上の 98a)。逐語 (M-1〜M-16、D-R102、lock の順序表、hook 文、C-34) は一致。観察 5 件 (cell.py の参照 8 件の 1 行ずれ → `c3e5ca7` の削除分を全 17 件で引き直した; 引き継ぎ書の語と欠落 → 直した; 計測の木の dirty → §5.3 に開示; 変異 id の衝突 (V15 × 2、56a が V70) → 観察; 固定 sleep で待ちの到達を代用 (test_r102_request_scope.py:380・:422・:701) → 観察)。
- `grep -c '<path>:' security/CONTROL_MAPPING.md` (完了条件 90、main `ddf9c73` → 最終の木): backend_postgres.py 7 → 18 (+ `` `path`: `` 1)、cell.py 17 → 18 (+3)、pool.py 0 → 3、main.py 8 → 9、ops.py 94 → 94 (+1)、platform_declarations.py 13 → 13、r2db postgres.py 10 → 15 (+9)、cloud-run-cloud-sql.md 15 → 15、test_r102_request_scope.py 0 → 8、test_r102_cross_cell_windows.py 0 → 3、test_r102_pool.py 0 → 2、test_r102_schema_windows.py 0 → 3、test_schema_serialization_lock.py 0 → 2、test_c34 0 → 1。
- 最終候補 `5da56d1` (main `ddf9c73` + `r102` `c3e5ca7`): 完了ゲート `gate: 4927 passed, 2 subtests passed in 910.29s (0:15:10)`、judge=PASS、pg_database/pg_roles diff 0 (label r102-final、2026-10-01 16:42)、`tools/tests` `pt: 784 passed in 88.08s (0:01:28)` (tools/tests、候補 `5da56d1`)。本節と CM の行参照の直しは最終ゲートの後の記録の commit (docs のみ) で入れ、`conformance-tests/test_control_mapping_register.py` と `tools/check_doc_refs.py` で確かめた。
- 閉止: 台帳 v1.146 (R-102 を §8.2 の索引と記録ファイルへ)、`CM` 3.14、設計 v0.6、R-120 起票。依頼者確認は引き継ぎ書 §4。

## 6. 訂正註 (本文は書き換えない。`OC` §1.8 の 57)

**訂正註 1 (2026-10-01、監督。起草担当の疑義 (a)〜(k) への裁定。本文は書き換えない)**

1. (a) 本書は `COND` に C-34 の行が入る WP-2 の WIP commit と同じ変更セットで branch に commit する (`tools/check_doc_refs.py` の C-34 の宙づり参照を避ける)。
2. (b) `conformance-tests/CONDITIONS_HISTORY.md` を WP-2 (新しい `## C-34` の節、`CT/test_conditions_register.py`:352・:378) と WP-7 (C-05 / C-27 の旧文を履歴へ移す、`COND`:6-12 の規約) の「触ってよいパス」に加える。
3. (c) `CT/registry.json` に条件ごとの登録欄は無い (adapter の一覧だけ)。WP-2 の「`CT/registry.json` (… 変更が要るときだけ)」は削除して読む。C-34 の 6 plug での駆動は test の parametrize と `test_c34_drives_on_every_registered_plug` の guard で担う。
4. (d) 設計 §6 の証拠表は 16 行である (枠の「17 行」は誤記)。
5. (e) 開2 (同じ実体への alter 同士) は 3b の排他でも直列になるので、V2 は「3a と 3b の両方の取得を消す」(1 entry に 2 edits) とする。開1・開4・C-34 の B は別の実体 (本文どおり) で、V1・V5・V17 は 3a だけを消す。
6. (f) 完了条件 38 の静的テストは次の形で読む: `M/cell.py` のコード (コメント・docstring を除く) に `self._lock`・`_CountingRLock`・`PostgresBackend`・`isinstance(self._backend` が 0 件、`SQLiteBackend` は import 行と既定 backend の構築 (`backend or SQLiteBackend(...)` 相当) の 2 箇所だけ。
7. (g) M-2 の「main.py の借用点」は M-12 の F-12 の借用 (`build_app` が runtime の pool から 1 本借りる点) を指す。その接続失敗は、現行の eager 接続の失敗が起動時に招く帰結と同じにする (現行の帰結は WP-4 の実装担当が現物で確かめ報告に書く)。
8. (h) 受理済みの runbook §10.10 (`CR`:3330-3336 付近) の「application ごとに永続接続を持つ」は R-102 の後は偽になる。WP-7 は §10.10 を新しい版 (12) として書き、§10.8 に 12 / not accepted を記す (R-115 の先例)。再受理は閉止時の依頼者確認 (§0) に含める。§6.5 の式は本文どおり WP-7。
9. (i) r2db の lock (設計 D-8) の形: `apply_schema` が `_load_catalog` の前に、application の接続の transaction で `pg_advisory_xact_lock(761761763)` (1 引数形、排他のみ) を取る。application ごとに database が分かれている (`r2db-api/migrations/0003_provision_application.sql`:109) ので key は application 単位に働く。定数は r2db 側に独立に置く (peer 間でコードを共有しない)。schema 操作だけが取り、DML・query は取らない。
10. (j) 計測の時機は設計 §8 に従う: 基準値 (木 = 分岐点の main `ddf9c73`、別 worktree で checkout) と実装後 (木 = branch の最終 tree) を WP-7 の後に同じ日に交互に取る。§2.0 の順序と §3 の手順 1 の「基準値 = WP-3 の前」は削除して読む。
11. (k) 観察: delete の確認句も revision を読む (`R/postgres.py`:1847、`M/cell.py`:2676)。DML の確認句の窓は設計の 3 窓にも D-3 にも入っていないので本件の範囲外とし、引き継ぎ書の「裁定」節に観察として残す。
12. WP-2 の test file 名は `conformance-tests/test_c34_concurrent_plan_precondition.py` とする (本文の `<name>` = `concurrent_plan_precondition`)。
13. WP-1 と WP-2 は触るファイルが重ならない (WP-1 = 新規 test 2 本、WP-2 = `CT/`・`RC/`・`MC/` の adapter と新規 test) ので、WP-2 は branch `r102` から分けた worktree `.claude/worktrees/r102-wp2` (branch `r102-wp2`) で並行に行い、監督が `r102` へ merge する (`OC` §1.2 の 16)。

**訂正註 2 (2026-10-01、監督。WP-1〜WP-3 のコードレビュー 1 巡目の裁定。本文は書き換えない)**

1. (WP-2 レビュー B-1) WP-7 の表に `docs/design/CONFORMANCE_ADAPTER_V1.md` (版数 1.19 → **1.20**、§30 = `hold_after_plan_verification` の節を新設。§25 の v1.15 の形) を足す。触ってよいパスにも足す。
2. (WP-2 レビュー A-2 / B-2) 確定文を改めた: port の hook の文と C-34 の Condition cell は「`plan` または `dry_run` を提示する schema 操作」だけを対象にし、停止点を「plan の照合に使う現在の revision を読み終え、その読みが取った lock をすべて保持したまま、DDL をまだ 1 文も実行していない地点」とする (plan を提示しない操作は素通し)。M-13 の「」の文と §2.2 の起草案のうち plan 無しの節は削除して読む。新しい確定文は `$SP/confirmed-r102-hook.txt` / `$SP/confirmed-r102-condition.txt` (旧版は `*.v1.txt`)。理由: どの plug にも plan 無しの操作を「自分が進める revision を読み終えた地点」で止める点が無く (r2db は DDL の後に加算、MitateDB は読む前)、条件文のその節に観測も変異も無かった。
3. (WP-2 レビュー B-7) 訂正註 1 の 10 は M-15 の「計測 D-R102 は監督が WP-3 の前 (基準値、基点 main) と WP-7 の後 (実装後) に行い」の句にも掛かる: 基準値と実装後は WP-7 の後に同じ日に交互に取る。
4. (WP-3 レビュー B-2) 設計 D-2 (iii) の「必ず rollback」は、実装では `transaction_status != IDLE` のときだけ rollback する形とした (IDLE の rollback は psycopg が往復なしで返し、`CountingConnection.txn_count` だけが進むため)。観測可能な結果 (開いた transaction と `SET LOCAL` が戻る、INERROR も戻る) は設計と同じ。設計文書には WP-7 で註を足す。
5. (WP-2 レビュー B-3) 完了条件 14 の V14a は r2db-http が変異なしでも赤の間は「監査照合 (理由行の逐語)」とし、WP-6 の後に監督が再実行して赤 (理由の変化ではなく失敗) を示す。完了条件 15 は V15 + V15b。
6. (WP-1 レビュー) 完了条件 9 は V9 (MitateDB) + V9r (r2db、WP-6 の後)。WP-1 の停止点は開1・開3・開4 とも `_execute` の文そのもの (`ALTER TABLE … ADD COLUMN` / `INSERT INTO` / `CREATE TABLE`、thread A のみ)、未完了の枝は `pg_stat_activity` の lock 待ちの観測で裏付ける。後送りの spec は `$SP/r102-wp1-mutations-deferred-wp4.json` / `-wp6.json`。
7. 手順の記録: レビュー群 1 (WP-1+2) と群 2 (WP-3+4) は、並行 worktree で WP が別々に終わったため、WP ごとに A / B の 2 起動並列で行った (各 WP を 1 回と数える。群の回数より起動は増えたが、§1.7 の 50 の回数は変えていない)。

**訂正註 3 (2026-10-01、監督。WP-6 のコードレビュー 1 巡目の裁定。本文は書き換えない)**

1. **M-17 (監督裁定、依頼者確認待ち)**: r2db の schema lock (訂正註 1 の 9) の取得順は per-key → lookup (replay は記録から答える) → **schema lock (3a) → 件数 lock** → `_load_catalog` → revision の読みとする。設計 D-3 の順序表 (MitateDB: 1 per-key → 2 件数 → 3a) と逆になる (peer 非対称)。理由: r2db では WP-6 前に無かった連鎖 — keyed の schema 操作が件数 lock を持ったまま無関係な遅い schema 操作の 3a を待ち、その間に別 key の keyed DML が件数 lock で止まる — が退行になるため (レビュー A-1)。輪は無い (3a の保持者が後で待つ件数 lock の保持者 (DML の `transact`) は 3a を取らない)。MitateDB は設計 D-3 の順のまま (依頼者裁定済み。同じ連鎖は設計 L-6 が開示済み)。両 peer を揃えるかは依頼者確認に含める。
2. 完了条件 83 の「lock を取る点が `_load_catalog` (:2106) より前」は、実装 (lookup の後に lock を取り、`_load_catalog` をその後へ動かした) が趣旨 (plan・確認句・`schema_objects` の読みが lock の下) を満たすので、そのとおり読む。
3. **起票 R-120** (監督): r2db の DML にも 開3 相当 (pass 1 の enum / nullable の検証と書き込みの間に `alter_field` が commit しうる。物理制約が無く registry を Python で検証する) が構造上開いている (WP-6 より前から。レビュー A-2)。設計 K-7 (依頼者裁定 Q-5) が r2db の窓を plan・確認句・`schema_objects` の 3 つに限ったので、本変更セットでは閉じず台帳に起票する (WP-7 で `RM` §8.1 に行を足す)。
4. WP-6 の完了条件に次を足す: 87a = add_field の `LOCK TABLE … SHARE ROW EXCLUSIVE` の SQL 文字列 pin (変異 RB1)、87b = 3 つの advisory lock 定数の区別の pin (RB2)、87c = dry-run が schema lock の下で catalog と revision を読む (RA1)。製品コメント CH-0069 / CH-0071 の言い換えは `docs/code-history/r2db-api/postgres.md` に §9.3 の形で訂正を追記する。

**訂正註 4 (2026-10-01、監督。WP-4 / WP-5 のコードレビュー 1 巡目の裁定。本文は書き換えない)**

1. (WP-4 レビュー A-1) M-4 の「範囲の入口で 1 回」は、競合した lock の取得 (try 形で取れず block 形で取り直した 3a / 3b、per-key / 件数 lock の待ち) の後・pass 2 / DDL の前に、残り deadline から `SET LOCAL` を 1 回打ち直す形に改める (残りが 0 以下なら `LIMIT_EXCEEDED(execution_ms)`)。競合の無い要求では往復は増えない。M-6 の「上限は execution_ms」はこの打ち直しで成り立つ。完了条件 **52a** (lock を待たされた要求の statement_timeout が残り時間に縮む、変異 V52a = 打ち直しを消す) を WP-4 に足す。
2. (WP-4 レビュー B-3) 完了条件 65 の後半に **65b** (http adapter の cell の backend の pool の size が `role_pool_size(DEFAULT_THREAD_LIMIT)` = 6、変異 V65b = `pool_size=` を外す) を足す。
3. (WP-4 レビュー B-5) 新設の `_acquire_advisory` の `except psycopg.Error` は `StorageTransientError` (503) に写す (M-1 の凍結は既存の DML / idempotency の箇所に限る)。完了条件 **56a** (lock 取得中の接続断が 503、変異 = `ValidationError` に戻す)。
4. (WP-4 レビュー B-8 (a)) 完了条件 68 と §2.4 の「MitateDB の 4 plug」は **3 plug** (in-process / http / socket) と読む。C-34 は 6 adapter (両 peer 3 plug ずつ) で、`RealServerMitateDB` は composition root (C-33 用) であり C-34 の plug ではない。
5. (WP-4 レビュー B-8 (c)) R-120 の台帳行は WP-4 の WIP commit (ff408fa) で入った (訂正註 3 の 3 の「WP-7 で」を改める)。版数 (v1.146) と版数ログの回転は WP-7 で 1 回。
6. (WP-4 レビュー A-3、観察) F-12 の refusing cell は範囲の入口で拒否するので、不正な形の要求も (旧の VALIDATION_FAILED ではなく) SERVICE_UNAVAILABLE になる。どちらも拒否であり、F-12 状態の application に限る。M-12 の「意味論は不変」の註として WP-7 の記録に書く。
7. (WP-4 レビュー A-2) `tools/perf_baseline.py` の `_resolve_app_db_and_matcher` (MitateDB の `backend._runtime` を読む) を WP-5 の対象に足す (pool の形に作り直し、偽物の test と README :495 を合わせる。変異 V78a)。SQLite plug で `request_scope` / `lock_schema` / `lock_entities` が backend call に数えられる点は §3 の表 C の説明に使う。
8. (WP-4 レビュー A-4) `MitateDB-api/src/mitatedb_api/capabilities_document.py`:432-442 の docstring (session-level lock / `idempotency_unlock`) を WP-4 の触ってよいパスに足し、xact 化に合わせる。
9. (WP-5 レビュー前の監督裁定) WP-3 の `test_r102_pool.py` の admin DSN reader は raise 形、`tools/tests/test_no_shared_cluster_defaults.py` の pin は 33 → 34 (WP-5 の commit 32eefb0)。`prepared_stats` の旧 docstring は CH-0548 として登録。

**訂正註 5 (2026-10-01、監督。WP-7 の起草とレビュー再確認の裁定。本文は書き換えない)**

1. (WP-7 起草の疑義) `ops inventory` item (8) (`MitateDB-api/src/mitatedb_api/ops.py`) の application 項を `2 x K x (O + N)` から `2 x K x (O + N x role_pool_size(thread_limit))` に改める (新 basis の data process は role ごとに最大 `role_pool_size(thread_limit)` 本、旧 basis は 1 本)。runbook §10.10 版 12 の式と一致させる。完了条件 **92a** (item (8) の値を pin する test の実測更新、変異 V-ops-1 = 旧形に戻す、V-ops-2 = O を落とす)。commit 6116807 (branch r102-wp7)。
2. (WP-4/5 再確認) `BoundedConnectionPool.map_idle` の例外時の put-back を pin する test (変異 RR-MI1) を完了条件 **77c** として足す。`prepared_stats` が probe 中に死んだ idle 接続で raise する点は観察 (製品の経路に無く、r2db も同形)。
3. (WP-7 起草) 作業指示書 §2.7 の「`CR`:509-531」は 0012 の表 (記録) を指しており、接続の式は現行 :540。表はそのまま、式を直した。
4. 計測 D-R102 の「実装後」の木は r102 の eb97a06 (製品コードはここで確定。以後の変更は記録 (WP-7) と指紋の更新のみ)。

**訂正註 6 (2026-10-01、監督。計測 D-R102 の K=1 で見つけた退行の裁定。本文は書き換えない)**

1. 事実: 実装後 (eb97a06) の K=1 `--warmup 20 --n 200` で MitateDB-api-http の p50 が query 2.144 → 6.476 ms (+202%)、mutate +176%、batch +226%、socket plug で +20〜50% (閾値 `RM` §0.1.4 の 1 を超える)。DBTIME の db_calls は減っている (3800 → 2600) のに 1 文あたりの時間が 10 倍。PREPARED 行は before `prepared=5 share=0.989` → after `prepared=0`。
2. 原因: psycopg の `Connection.rollback()` は ROLLBACK の後に prepared statement のキャッシュを捨てる (`_connection_base.py` の `_rollback_gen`: `self._prepared.clear()` + `DEALLOCATE ALL`)。範囲の出口で query の runtime transaction と pass 1 の developer の読み取り transaction を rollback して pool に返す形 (M-5) では、接続上の文が毎回捨てられ、二度と prepare されない。R-102 前は catalog 読みと `read()` が自己 commit していた。
3. 裁定 (**M-19**、依頼者確認待ち): 例外なしで抜ける範囲は、INTRANS の主接続 (query) と developer 接続 (DML / query の pass 1 の読み) を **COMMIT** して返す (例外で抜けるときは rollback、`release` の rollback は安全網のまま)。読み取りだけの transaction の COMMIT は意味論を変えない。完了条件 **57b** (threshold 回の同じ query の後に `pg_prepared_statements` に文が残る、変異 V57b = 出口を rollback に戻す) を WP-4 に足す。`backend_calls` は commit の分だけ増える (query +1、DML +1 (developer))。
4. 計測 D-R102 は訂正註 5 の 4 を改め、「実装後」の木を差し戻し 2 の後の r102 head とし、k4 / k1 / real-server の全段を取り直す (round 1 の結果は `$SP/perf-r102-round1/` に記録として残し、K=4 の判定値 (0/4856 = 0.0%、2 run) は参考値とする)。

**訂正註 7 (2026-10-01、監督。依頼者確認の一覧の補い。本文は書き換えない)**

1. **M-18 (問い、依頼者判断待ち)**: `plan` を持つ DML (transact の dry-run / plan) は 3a を取らない (設計 D-3・D-4) ので、別 entity への schema 操作が revision を進めても plan 付き DML は通る (WP-4 の実装担当の疑義 1)。(a) 設計どおり (DML の plan の照合は対象 entity の 3b の範囲で守られ、別 entity の schema 変更は DML の対象に触れない) / (b) plan 付き DML も 3a を共有で取る (schema 操作中は DML が止まる)。監督の推奨 = (a)、観察として記録。
2. 裁定の語彙: 引き継ぎ書「裁定」節の語は `OC` §1.15 の 77 の 4 語 (起票 / 既知の穴 / 観察 / 直した) に限る。レビュー WP-5 B-3 (触ってよいパスの外の file) の「追認」は「観察 (監督の発注で許していた)」と読む。
3. 最終一括 (`$SP/r102-final-batch.md` の 1〜7) を完了条件 **98a** とし、WP-7 に含める (34b の test の入力と V-ops-3、SI-01 Evidence、main.py / pool.py の旧コメント、r87 の test 名、C-34 Status の RB-wp7-1、差し戻し 2 後の CM の行と主張、README の 1 文)。


**訂正註 8 (2026-10-01、監督。受け入れ監査と最終候補の裁定。本文は書き換えない)**

1. (WP-4 レビュー B-1 の裁定の変更) 消えた cell lock の経緯コメント (main の `cell.py`:646-685) の受け皿 CH-0547 は、(ii) 「元の塊全体を fence に、参照行を残す塊の末尾に」の形では `tools/tests/test_comment_provenance.py::test_0f_both_peers_all_src_rev_vs_itself_is_green` (常設) が赤になる (検査器は「保護参照 (test 名) を含む文の削除」を companion から導出できない: 設計 §4.1 (3))。`c3e5ca7` で (i) に戻した: `_CountingRLock` の docstring と同じく git に任せ、CH-0547 の節と参照行を外す (R-115 作業指示書 訂正註 9 (2) の先例)。§2.0 の注意 5 の「逐語の受け皿」はコードごと消える塊には掛からない、と読む。覆した日付 2026-10-01、根拠 = 本註。
2. (監査) 完了条件 90 の grep の前後値は §5.4 に記録した。完了条件 98a の `CM`:1469 の参照を :481-482 に直し、`c3e5ca7` の 1 行削除で動いた `cell.py` の参照 17 件を引き直した。
3. (監査の観察) 変異 id の衝突 (`r102-wp4-mutations-d.json` の V15 が 2 つ、56a の変異が V70) と、固定 sleep による待ちの到達の代用 (`test_r102_request_scope.py`:380・:422・:701) は観察。製品コードの最終 (`0d8ffd0`) の後に再実行した変異は V39 / V43 / V44 / V57b で、spec の 101 edit のうち 94 は最終の木に old が在る (V73 の old は無い = WP-4 差し戻し後の文字列と異なる。観察)。
