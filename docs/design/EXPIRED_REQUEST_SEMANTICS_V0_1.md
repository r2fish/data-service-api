# 設計メモ — 期限切れ要求の意味論 (R-42)

## 0. 版数・位置づけ

- **v0.10 (2026-10-03、作業機)。** 契約文 (§9) を依頼者が確定した (逐語は §10 の末尾)。版の番号の読み替えを記録した: 台帳 R-118 が契約 1.15.0 (従属判断 20) を先に使う (台帳 v1.154 の R-118 行の【追記】) ので、R-42 の契約は merge 順の帰結として **minor 1.16.0・従属判断 21** になり、§9 の「1.15.0」「subordinate ruling 20」「1.14.0」は契約 WP で「1.16.0」「21」「1.15.0」に置き換える (U-4 の裁定の要点は minor であること。番号は merge 順で振る)。§9.2 の段落の置き場は 1.15.0 の文の後・version-flip の文の前。設計の本文の「1.15.0」「ruling 20」は読み替えとし、書き換えない。
- **v0.9 (2026-10-03、作業機)。** §9 の最終確認 (FC-1〜FC-6、全件直す) を反映: 文の定義にデータを読む文を入れ (閉じた列挙にしない)、義務 (c) を接続ごとの形にし (MitateDB は 2 接続)、in-memory の storage の操作は義務 (b) にだけ数える (FC-3 は (A'))、「budget」の語を要求のフィールドと区別した。一覧は §11.8。この版の §9 を依頼者に提示する。
- **v0.8 (2026-10-03、作業機)。** 再々確認 (§9 と N-1〜N-12 の閉じ方に限る。F-1〜F-14、全件直す) を反映。義務 (c) の bound に上限 (算出時の残りを超えない) と設定の義務を入れ、義務の前文に範囲を入れ、文の定義を storage の操作にも及ぶ形にした (in-memory も縛る)。一覧は §11.7。契約文 (§9) はこの版を依頼者に提示する。
- **v0.7 (2026-10-03、作業機)。** 設計レビュー 2 回目の再確認 (N-1〜N-12、全件直す) を反映。義務 (c) を「設定後の各文は設定直前の残りから算出した bound の下で走り、bound に届いた文は打ち切る」に改め (入口で 1 回設定する U-2 (a) と字義で合う形)、文の定義に transaction / savepoint を開く文を含め、観測値の定義を enter 側の計数に改め、版の切り替えを統合 branch 上の 1 commit に定めた。一覧は §11.6。
- **v0.6 (2026-10-03、作業機)。** 設計レビュー 2 回目の 1 巡目 (A 9 件 + 観察 1、B 14 件 → 19 件に統合) と依頼者裁定 V-1〜V-3 (§10) を反映。義務を 4 件にし (実行中の文の打ち切り)、範囲を query・mutation・schema 操作に定め、接続確立の判定を時計 1 本にした。§9 を組み直した。一覧は §11.5。
- **v0.5 (2026-10-02、作業機)。** 依頼者裁定 U-1〜U-9 (全件 (a)。逐語は §10) を反映。§5 の各項に裁定を記し、D-2 の (d) を置かない形に確定、D-6・D-7・D-9 を裁定に合わせ、§9 を裁定どおりの 1 本の候補文に組んだ。契約文 (§9) の確定は設計レビュー 2 回目の後に依頼者へ求める。反映の一覧は §11.4。
- **v0.4 (2026-10-02、作業機)。** 作業機の照合 (設計が引く file:line と「基点で未照合」の 12 行) と実測 (M-1〜M-8) を反映。主な変更: (1) `statement_timeout` は COMMIT を打ち切らない (M-4) ので、「COMMIT は文の bound で打ち切られる」を取り下げ、commit 段の【保留】文と U-6 の commit 段の選択肢を削った。(2) v0.2 の起票候補 (MitateDB schema 操作の `commit_failed` の欠け) は現物に無く、取り下げた (台帳 v1.151 の R-42 行)。(3) 修正前の挙動を conformance の水準で記録した (MitateDB の PostgreSQL 2 plug は予算を過ぎた要求を commit する)。(4) §12 に実測の記録を足した。一覧は §11.3。基点は local main `3ce48d2` (製品コードは `4241b55` から変わっていない。`r2db-api/src`・`MitateDB-api/src` の差分 0)。
- **v0.3 (2026-10-02)。** 再確認 (担当観点: 指定なし) の 12 件と観察 1 件を反映。U-8 の (d) の扱い、U-9 の pin の向きの訂正。反映の一覧は §11.2。同日、レビュー項目の記号を R-N から RV-N に改めた (台帳の R 族との衝突を避ける)。
- **v0.2 (2026-10-02)。** 設計レビュー 1 回目 (A 9 件・B 15 件 → 19 件に統合) を反映。新しい U-8・U-9。起票候補 1 件 (MitateDB schema 操作の cancel 分岐の `commit_failed` 欠落)。反映の一覧は §11。
- **v0.1 (2026-10-02)。** 基点 local main `4241b55`。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-42 (規模 L、変更クラス D (`RM` §9 の 8))。契約 1.14.0 (subordinate ruling 19)、port v1.21。
- 着手の根拠: 台帳 R-42 行の依頼者裁定 (`RM`:462) 「**【追記 2026-09-15 依頼者裁定】** 「R-42はフェーズ11で」 — **フェーズ11 で扱う**。」
- ファイル名は依頼者指示 2026-10-02 による。台帳項目の設計であり計画文書のフェーズ節ではないので、運用条件 §1.8 の 53 の転記は行わない。
- 範囲: 共通の意味論と契約文言の候補まで (`CLAUDE.md` の開発順序)。契約・conformance・実装は変えない。
- 本 session は cloud で PostgreSQL が無く、新しい実測はしない。PostgreSQL の挙動に依る主張には次のどれかを添える: **【既存実測: 出所】** / **【PG 文書 (未実測)】** / **【未確認 → M-N】** (§8)。
- v0.4 から: 作業機で測った主張には **【実測 2026-10-02: §12 の節】** を添える。
- 表記: file:line は基点 main のもの。r2db の製品コードは `r2db-api/src/r2db_api/`、MitateDB は `MitateDB-api/src/mitatedb_api/` からの相対で書く。v0.3 まで報告由来の事実に添えていた「基点で未照合」の印は、v0.4 で照合を済ませ、印を外した (結果は §11.3)。出所の記法は運用条件 §0。

## 1. 問題設定

### 1.1 起票 (台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 R-42、`RM`:462 の逐語)

> **期限を使い切った要求が 1 ms の timeout で文を実行し、成否が負荷で揺れる (両 peer)。** 両 peer は、要求が limit gate を通るときに実行期限を計算し、その後の待ちもその期限に数える。MitateDB は `ApplicationCell._lock` の前で計算し (`MitateDB-api/src/mitatedb_api/cell.py:771`、lock は例えば `cell.py:2171-2172`)、r2db は `service.py` の `_slot` 経路である。期限を過ぎても両 peer とも拒否せず、1 ms に丸めて文を発行する (MitateDB `MitateDB-api/src/mitatedb_api/backend_postgres.py:1477-1481` の `_timeout_ms`、r2db `r2db-api/src/r2db_api/postgres.py:2467-2471` の `_timeout_ms`)。このため、予算を使い切った同じ要求が機械の負荷しだいで 200 にも 413 `LIMIT_EXCEEDED`/`execution_ms` にもなり、結果が決定的でない。契約の limits の記述は、execution_ms の計測がいつ始まるかも、lock や slot の待ちを数えるかも述べていない。`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 の事故で、MitateDB のテストが赤になった原因として見つかった (テスト側は同節の【追記】のとおり本変更で修正済み)。**候補 (未決定)**: 残り予算が 0 以下なら文を発行する前に `LIMIT_EXCEEDED`/`execution_ms` で決定的に拒否し、conformance で固定する。lock や slot の待ちを数えるか、契約の文言に註が要るか (契約を変えるなら版を上げる) は設計で決める。

### 1.2 起票と現物の差

- 起票の `ApplicationCell._lock` と行番号は陳腐化している。MitateDB の cell lock は台帳 R-102 の設計 `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` の D-1 で廃止され (同 :144)、PostgreSQL の advisory lock と `request_scope` に置き換わった (同 :163-164、:200)。
- r2db は入口の期限検査を query・transact の 2 経路に持つが、pool 取得と apply_schema に穴がある (§1.3)。
- MitateDB は pool 取得と lock 待ちの後に検査を持つが、`request_scope` の入口と文の間に穴がある (§1.4)。

### 1.3 r2db の時系列 (`r2db-api/src/r2db_api/` 相対)

| # | 段 | 場所 | 期限を既に過ぎていたら |
|---|---|---|---|
| 1 | rate・concurrency slot (`_slot`) | `service.py:552-584` | slot は待たず即 429。期限は未計算 |
| 2 | 期限の計算 `self._clock() + effective_limits.execution_ms / 1000` (budget で狭めた値) | `service.py:313` (query) / `:374` (transact) / `:455` (apply_schema)。clock は注入可 (`service.py:176`) | — |
| 3 | 入口の `limits.check_deadline` (`clock() > deadline` で 413) | `postgres.py:1498` (query) / `:1613` (transact)。**apply_schema には無い** (`:2108-2120`) | query・transact は DB の前で拒否。apply_schema は進む |
| 4 | pool 取得 (`self._runtime.connection()` / `self._developer.connection()`) | 期限を渡さない。固定の `_DEFAULT_CONNECT_TIMEOUT_S = 5`、`_DEFAULT_ACQUIRE_TIMEOUT_S = 10.0` (`postgres.py:230-231`) | 待ちの超過は `psycopg.OperationalError` (`postgres.py:458`) が backend の `try` の外 (`:1502` 対 `:1504`) → http 層で汎用 503 (`http.py:360-368`) |
| 5 | `_timeout_ms` → `_set_timeouts` | `postgres.py:2649-2654` / `:2656-2672` | `max(1, int(remaining))` で残り 0 以下でも 1 ms。transaction ごとに 1 回、再計算なし。`statement_timeout` と `lock_timeout` を同値で `SET LOCAL` |
| 6 | advisory lock (`_idempotency_key_lock` / `_idempotency_reserve_lock` / `_schema_serialization_lock`) | `postgres.py:1352-1412` | `pg_advisory_xact_lock` の待ちは `lock_timeout` に掛かる **【実測 2026-10-02: §12.1 (M-6)】**。待った後の再検査・再設定は無い |
| 7 | 以降の `check_deadline` | query `:1554` (SELECT 後)、transact `:1691` (各 operation 前)・`:1701` (loop 後)、apply_schema `:2202` (DDL 前の 1 回) | `_idempotency_store`・`pre_commit`・COMMIT の前には無い |
| 8 | エラー写像 | `limits.py:101` と `postgres.py` の各 except (`:1120-1123` / `:1544-1547` / `:1735-1744` / `:2428-2437`) | `QueryCanceled` / `LockNotAvailable` → 413 `LIMIT_EXCEEDED`、details `{resource: "execution_ms", limit_class: "execution_ms", limit: <実効の execution_ms>}` |
| 9 | 残るもの | 1 transaction | rollback で部分適用・idempotency 記録は残らない。transact (`postgres.py:1735-1764`) と apply_schema (`:2428-2454`) の except の 5 分岐 (QueryCanceled / LockNotAvailable / UniqueViolation / DataError / psycopg.Error) はすべて、hook が fired なら `commit_failed()` で error 行を best-effort で追記する (`service.py:112-117`)。`pre_commit` は try 内の最後の文 (`:1733`・`:2426`) なので、hook の後に起き得るのは COMMIT の psycopg 例外だけで、そのとき data は rollback、allow 行と error 行が残る。COMMIT は予算では打ち切られない (D-3)。transact も apply_schema も同じ (apply_schema は idempotency を pre_commit より前に書く。store は `postgres.py:2416-2420` (`if` は `:2415`)、pre_commit は `:2426`)。`LIMIT_EXCEEDED` は `_DURABLE_DENIAL_CODES` (`service.py:49-56`) に無く、deny event は in-memory sink のみ |
| 10 | dry_run | 2〜5・catalog・各 operation 前の検査は同じ | idempotency の lock・lookup・reserve を飛ばす。終端は `psycopg.Rollback` |

### 1.4 MitateDB の時系列 (`MitateDB-api/src/mitatedb_api/` 相対)

| # | 段 | 場所 | 期限を既に過ぎていたら |
|---|---|---|---|
| 1 | `_limit_gate`: rate → concurrency slot (待たない) → bytes・depth → budget で狭める → `deadline = time.monotonic() + max_execution_ms/1000` | `cell.py:686-692`。clock の注入は無い | — |
| 2 | `_borrow`: `pool.acquire(timeout = max(0, deadline - now))` | `backend_postgres.py:452-463`、`pool.py:444-508` | 3 経路: (1) idle 接続あり → 残り 0 でも即返る (`pool.py:467-477`)。(2) 上限未満・idle なし → 新規接続。`connect_timeout = min(設定値, max(1, ceil(残り)))` で、psycopg の下限 2 s が掛かる (`pool.py:444-492`)。失敗は `PoolConnectFailed` (`pool.py:496`) → `StorageTransientError` 503 (`backend_postgres.py:463-464`)。(3) 上限到達・idle なし → `PoolExhausted` (`pool.py:508`) → `ResourceLimitError(limit_class="execution_ms")` 413 (`backend_postgres.py:461-462`) |
| 3 | `request_scope`: `_timeout_ms(deadline)` → `SET LOCAL` | `backend_postgres.py:484-500`、`_timeout_ms` は `:1681-1685` | **入口の残り検査は無い**。`max(1, int(remaining))` で残り 0 以下でも 1 ms。`SET LOCAL` の cancel は `psycopg.Error` → `StorageTransientError` 503 (`:493-500`。経路は存在するが作業機では再現しなかった、§1.5) |
| 4 | advisory lock (`_acquire_advisory`) | `backend_postgres.py:555-606` | try 形で取れれば 1 文で `_retime` 無し。取れなければ block 形で待ち、`lock_timeout` に掛かる (`QueryCanceled` / `LockNotAvailable` → `ResourceLimitError` execution_ms、`:577-578`)。待った後だけ `_retime` (`:604`)。idempotency の key lock・件数 lock も同じ経路 (`:1766`、`:1803-1804`) |
| 5 | `_retime` | `backend_postgres.py:532-552` | `scope.deadline - now <= 0` なら拒否。それ以外は `_timeout_ms` で再 `SET LOCAL`。0 < 残り < 1 ms は `max(1, int(0)) = 1` → 1 ms。再 `SET LOCAL` の cancel は `psycopg.Error` → `StorageTransientError` 503 (`:544-552`。経路は存在するが作業機では再現しなかった、§1.5) |
| 6 | 文の間 | operation loop (`cell.py:2838-2848`) と create_collection の複数文 (`backend_postgres.py:1176-1218`) の間に検査なし。`begin` は no-op (`backend_postgres.py:1700-1703`) | 検査されない |
| 7 | 残るもの | 1 transaction、release 時に rollback | 部分適用・idempotency 記録は残らない。`LIMIT_EXCEEDED` は耐久 denial の対象外 (`audit_dispatch.py:32-60` のコメント、集合 `DURABLE_DENIAL_CODES` は `:61-68`)。順序は経路で違う: transact は idempotency 記録 → pre_commit → commit (`cell.py:2908-2919`) で、pre_commit の前の打ち切りなら audit 行なし。単一行の insert / update (`_write_row_before_commit` `cell.py:791`、呼び出し `:1994`・`:2265`) は write → pre_commit → commit。schema 3 経路 (`alter_field_constraints` `backend_postgres.py:1058`、`create_collection` `:1204`、`add_field` `:1372`) は pre_commit を idempotency の書き込み (`:1069`・`:1229`・`:1382`) と commit (`:1070`・`:1230`・`:1383`) より先に行う。行の `delete` (`:1632`) は idempotency の書き込みが無く pre_commit (`:1648`) → commit。backend 単体の cancel 分岐 (`:1071`・`:1231`・`:1384`・`:1651`) は `commit_failed` を呼ばないが、呼び出し側の `_error_row_once_fired` (`cell.py:770-789`、R-115 WP-4b) がこの 4 経路の呼び出し (`cell.py:1303`・`:1582`・`:1829`・`:2396`) を包み、pre_commit の後に commit せず抜けるあらゆる失敗で error 行を書く (`MitateDB-api/tests/test_application_audit.py` の `test_a_cancelled_schema_record_write_after_the_pre_commit_row_writes_an_error_row_and_keeps_the_response` と `test_a_cancelled_delete_commit_after_the_pre_commit_row_writes_an_error_row_and_keeps_the_response` が `["allow", "error"]` を固定)。【訂正 2026-10-02 (v0.4)】 v0.2〜v0.3 の「allow 行だけが残り error 行は追記されない」は backend 単体だけを読んだ誤り。schema 3 経路の順序 (pre_commit の後に idempotency の書き込み = 文) は D-2 (pre_commit の後に文を発行しない) と両立しないので、D-9 で並べ替える |
| 8 | 応答の経路差 | `cell.py:2919`・`:2920`・`:3010`、`backend_postgres.py:1817-1825`・`:528-530`、`http.py:568` | schema 操作は commit も同じ try 内で 413 execution_ms (error 行は #7 の `_error_row_once_fired`)。transact の `backend.commit` (`backend_postgres.py:1705`、呼び出し `cell.py:2919`) の例外は `:2920` の except で rollback し、hook が fired なら `commit_failed` の後 `AuditSinkUnavailable` (`:3010`) → 503。`record_idempotency` の cancel は翻訳されず (`backend_postgres.py:1817-1825`)、`http.py:568` の `except Exception` で汎用 503。read の `_end_reads` の commit 失敗は `backend_postgres.py:528-530` で `StorageTransientError` → 503。COMMIT は予算では打ち切られない (D-3) |
| 9 | HTTP | `http.py:84`、`errors.py:80-91` | `LIMIT_EXCEEDED` は 413、details は `{"limit_class": "execution_ms"}` のみ |
| 10 | SQLite plug | `backend_sqlite.py:22-27`、`:181`、`:646`、`:711` | 入口と begin で `_check_deadline` (strict `>`) を持つ |
| 11 | dry_run | 期限・pool・lock・`SET LOCAL` は同じ | idempotency 検査なし、audit hook 不構築、rollback。create_collection の dry_run は CREATE TABLE を実走し bump と INSERT を飛ばす (`backend_postgres.py:1180-1200`) |

### 1.5 1 ms の文が走る経路 (両 peer に残る) と修正前の挙動

経路:
- r2db: `check_deadline` を通った後の pool 待ち → `_timeout_ms` = 1 ms (pool に期限が渡らない)。apply_schema は入口検査が無いので期限切れでも pool → 1 ms。advisory lock を待った後に再設定が無いので、待ちの後の文は「scope 入口の残り」の満額で走る (超過の方向)。0 < 残り < 1 ms は `check_deadline` を通り `_timeout_ms` = 1 ms。
- MitateDB: `request_scope` の入口 (残り 0 以下でも 1 ms。pool に idle があれば `_borrow` は即返る)、`_retime` の 0 < 残り < 1 ms、その下で走る全文。文の間に検査は無い (§1.4 #6)。

実測で確かめられたこと **【実測 2026-10-02: §12.1・§12.2・§12.4】**:
- r2db: `timeout_ms == 1` は駆動 A・C・D の全経路で 50/50 記録された (B の query・transact は入口の `check_deadline` `postgres.py:1498` / `:1613` が先に拒否し、文は 0 本)。apply_schema は入口検査が無く、期限を 1 s 過ぎた B でも `SET LOCAL` を 1 ms で発行し、catalog 読みが cancel されて 413 (50/50。期限切れで CREATE TABLE が走った回は 0)。
- r2db の結果は揺れる: 残り 0.6 ms (C) の軽い query は 200 21/50・413 29/50。`budget.execution_ms = 1` (D) の軽い query は無負荷で 200 50/50、CPU 負荷の下で 413 50/50。重い query は C・D とも 413 50/50。同じ条件でも run の間で内訳が変わる。413 の相当数は文の cancel ではなく、全文が完了した後の `check_deadline` (`postgres.py:1554` / `:1691` / `:2202`) による — U-8 の現物の姿で、仕事は終わっているのに 413 になり、境界が負荷で動く。応答は 200 か 413 だけ (503 は 0)。r2db の `_set_timeouts` は try の内側なので `SET LOCAL` の cancel は 413 になり、MitateDB (503、§1.4 #3) と peer で応答が違う。
- MitateDB: 期限を過ぎた要求が成功して commit する。軽い read と transact (軽い / 約 312 行を更新する重い) は、R1 (期限を 30〜40 ms 過ぎている)・R1b・D・R2 のすべてで 200 50/50 (各文が 1 ms 未満で終わり、文の間に検査が無い)。conformance の水準でも、PostgreSQL の 2 plug は予算 50 ms を 60 ms 以上過ぎた要求を最後まで実行して commit する (20/20、負荷に依らない。§12.4)。これは「1 ms の文」より手前の欠陥である。
- MitateDB の重い文は負荷で揺れる: 重い read は R1 で 200 5/50・413 45/50、create_collection は R1 で 200 7/50・413 43/50 (CREATE TABLE の cancel)。CPU 負荷の下では R1b・D・R2 でも 2〜4/50 が 413、`budget.execution_ms = 1` の 312 行の更新は 12〜13/50 が 413。`_retime` は blocking の advisory lock 待ちの後にだけ到達する。
- 機構: 1 ms の bound の下の文の成否は、その文が 1 ms を超えるかで決まる。PostgreSQL 単体では軽い文 (`SET LOCAL`、`SELECT 1`、主キー 1 行、5000 行の整列) は 1 回も cancel されず、1 ms を超える文は 200/200 が 1.04〜1.37 ms で cancel される。peer 経由でも軽い文から少し重い文へ移ると 200 が r2db C で 21/50 → 0/50、D で 50/50 → 0/50、MitateDB R1 で 50/50 → 5/50 に落ちる。MitateDB の既存実測は §1.6 の `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5。

再現しなかったこと (起き得ないことの証明ではない):
- MitateDB の 503: 経路は存在するが (`backend_postgres.py:493-500`、`:544-552`)、作業機では再現しなかった (0 / 1695)。
- `SET LOCAL` 自体の cancel: 最後の `_timeout_ms` が 1 だった要求 (MitateDB 1695 件・r2db 1400 件、CPU 負荷の下を含む) で 0 回。PostgreSQL 単体でも 0/2000。

未実測: r2db の pool 待ち超過 (§1.3 #4 の 503)、MitateDB の §1.4 #2 の (2)(3) (新規接続、`PoolExhausted`)、idempotency 経路と dry run の 1 ms 経路、実 HTTP スタック (uvicorn / TLS / proxy)。

利用者 (AI エージェント) は結果から再送の可否を決められない。契約は期限切れの要求が「何も残していない」ことを明文化していない。

### 1.6 既存の記録にある実測 (再測しない)

- `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 【追記 2026-09-15、v0.17】: MitateDB の要求 B が lock の後ろで約 10 s 待ち、`statement_timeout = 1ms` で走っていた。`timeout_ms == 1` のときに 10 ms の文を強制すると、ゲートの赤が再現した (`a_status: 200`、`b_status: 413`)。
- 台帳 R-78 (`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md`): r2db の pool size 32 の待ちは 0、size 2 の最大待ちは K=4 で 2.5 ms、K=32 で 35.0 ms。MitateDB の cell lock の最大待ちは 28〜67 ms (K=32 で 67.1 ms) — **台帳 R-102 で cell lock が廃止される前の値**。query p50 は K=32 で r2db 63〜67 ms、MitateDB 211〜220 ms。R-102 の後の値は §8 M-5。
- 台帳 R-80 (`docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md`): 往復の成分を測る道具 (`tools/perf_baseline.py --roundtrip`)。1 文の追加の費用はこの道具で測る。
- CI は `postgres:16` (`CI`:196)。PostgreSQL 17 の `transaction_timeout` は使えない。作業機は PostgreSQL 16.14 で `transaction_timeout` は無い **【実測 2026-10-02: §12.1】**。配備の版は未確認 (M-2)。
- `statement_timeout = 0` は timeout の無効を意味する (だから `max(1, …)` が置かれている) **【PG 文書 (未実測)】**。`statement_timeout` は文ごとに計測され、transaction 全体の上限ではない **【PG 文書 (未実測)】**。

### 1.7 契約の沈黙

述べていること (`spec/data-service-api.v1.json`):
- `limits.classes` に `execution_ms`、例 5000 (`limits.example_profile`)。
- `limits.request_budget`: budget で狭めた bound の超過は配備 bound の超過と同じく `LIMIT_EXCEEDED` + `details.limit_class`。execution_ms は query・mutation (単一・cross-entity)・schema 操作に適用。budget の検査は request shape の検査の位置。
- `errors.details_vocabulary`: `LIMIT_EXCEEDED.limit_class` は必須。`common_optional.futility` は任意。`open` (閉じた語彙ではない)。
- `errors.http_status_note`: 409 以外の HTTP status は契約で未定義。
- `structured_operations.idempotency.record`: 失敗した要求は記録を残さず、再送は新規の試行。digest に budget を含む。
- `transactions.atomic` / `transactions.retry`。`structured_operations.dry_run.external_effects`: dry run は行・catalog・schema revision・idempotency 記録・audit event を残さない (audit event も「externally visible な状態変化」に数える)。dry run も rate・concurrency を消費する。
- 両 peer は execution_ms の enforcement を `reference_wall_clock` と宣言 (`security/CONTROL_MAPPING.md:729`、`:851`)。

述べていないこと (`spec/` 全体で `deadline`・`timeout`・`wall-clock`・`statement_timeout`・`lock_timeout` は 0 件): 計測の始点、lock・slot・pool の待ちを数えるか、文ごとか要求全体か、超過時の HTTP status、超過で終わった要求が何も残さないこと。execution_ms の超過が `LIMIT_EXCEEDED` になること自体も `request_budget` と `details_vocabulary` からの読みであり、明文は無い。

## 2. 制約

- `CLAUDE.md` の開発順序 (共通の意味論 → 契約 → conformance → 実装)。本書は共通の意味論と契約文言の候補まで。
- Security Invariants は feature gate にしない。新しい不変条件は足さない。SI-08 の Verification 句「deterministic rejection or termination beyond supported limits」が本件の性質そのものであり、SI-11 が「部分状態を残さない」を既に述べている。
- 決定軸 (依頼者指示 2026-10-02、本 session の起動指示): 堅牢で安全が第一、次に最大限の自由。高性能が前提なので、**期限の検査のために DB の往復を足さない**。
- peer は同じ安全の結果を別の制御で出してよい (`CLAUDE.md`)。
- 公開 API は構造化のまま。契約を変えるなら版を上げ、`versioning.version_binding` の散文と `versioning.obligations[]` の両方に書く (1.14.0 の形)。
- 確定文言はファイル経由 (運用条件 §1.5 の 35)。§9 の契約文は候補であり、依頼者が確定するまで逐語 pin を置かない。

## 3. 決定と根拠

**D-1 execution_ms は 1 要求の wall-clock 予算である。** 始点は遅くとも「受理点」— 要求がその配備の rate・concurrency の gate を通り、budget で狭めた要求固有の bound が確定した時点 (両 peer が今期限を計算している点、§1.3 の 2・§1.4 の 1)。予算に数えるのは、受理点から**要求が commit を始めるまで** (pool の取得待ち、lock の待ち、文の実行)。**commit を始めた要求は、execution_ms では拒否も打ち切りもされない** (M-4: `statement_timeout` は COMMIT に掛からない。両 peer の COMMIT の仕事は WAL の書き出しだけで、deferred の制約・trigger は無い **【実測 2026-10-02: §12.1】**)。commit の後に時計で拒否することはできない (commit 済みの要求を失敗として返せない)。実装はもっと早く (受信時から) 数え始めてよいが、遅く始めてはならない。1 page = 1 要求で、page ごとに新しい予算。dry_run も同じ予算の下で走る (dry run は文を発行する)。ただし dry run と real の要求は発行する文が違うので、どちらの成功も execution_ms の拒否も他方を予言しない (両方向。§11.5 RW-3)。契約は dry run が limit の拒否も決めると読める文を持つ (1.7.0 (3)) ので、execution_ms がその例外であることを §9.1・§9.2・§9.4 で明記する。
- 範囲 (依頼者裁定 V-2。§11.5 RW-2): query・単一 / cross-entity の mutation・schema 操作と、その dry run (契約 `limits.request_budget` が execution_ms の適用先に挙げる 3 種)。catalog 読みなど他の要求を実装がどう bound するかはこの版では定めない。r2db の catalog 経路 (`r2db-api/src/r2db_api/service.py:489-501`。期限を計算しない) は変えない。
- 根拠: SI-08 は要求 1 件が資源を無限に持てないことを求め、利用者に見える所要時間を bound するのは待ちを含めてこそである。MitateDB の `_borrow` の docstring は既に「期限を超える待ちは要求が execution_ms を超えたこと」と読んでいる。待ちを別 class に分けると `limits.classes` の語彙 (1.2.0 の規則) に新語が要り、利用者が 2 つの予算を推論する負担が増え、安全の結果は増えない (U-1 の裁定 (a))。
- 受理点の後の待ち (pool・lock) は、台帳 R-102 の後の 32 並列で最大 3.4 ms で、既定 5000 ms に対して 3 桁の余裕がある (M-5、§12.5)。
- 受理点の前 (認証・body の解析・worker の順番待ち) は逐次で r2db 約 0.5 ms・MitateDB 約 5 ms、32 並列で p50 53〜78 ms (M-7、§12.3)。

**D-2 予算を使い切った要求は、次の文を発行する前に拒否する。**
- 「文」の定義 (§9.1 と同じ範囲): 実装が要求のために保持するすべての接続 (MitateDB の developer 接続の catalog 読みを含む。要求自身の各 transaction) で、要求の内容から発行する文。transaction / savepoint を開く文を含み (transaction を開く文は、r2db は `transaction()` の入口の BEGIN、MitateDB は最初の文と同時の暗黙の BEGIN)、終える文は含まない。`SET LOCAL`、catalog 読み、lock の文、idempotency の読み書き、DML / DDL を含む。含めない: pool の維持 (r2db の checkout ごとの `SELECT 1` `postgres.py:621`、新規接続の `SET search_path` `postgres.py:388`、MitateDB の idle ping `pool.py:369` (閾値の条件は `:384`、呼び出しは `:386`))、transaction / savepoint を終える文 (COMMIT / ROLLBACK / RELEASE。D-1・D-3 のとおり予算の外)、別接続の audit sink への書き込み。v0.6 の「psycopg の暗黙の BEGIN はその transaction の一部」を改めた (§11.6 N-8)。
- 実装は、文を発行しようとする各点で残り予算を process 内の時計で比べ、残りが 1 ms 未満 (整数 ms で 0) なら文を発行せず `LIMIT_EXCEEDED` + `details.limit_class: execution_ms` で終える。`_timeout_ms` 自身も残り 1 ms 未満で `LIMIT_EXCEEDED` を上げ、決して 0 を返さない (`statement_timeout = 0` は timeout の無効 **【PG 文書 (未実測)】** なので、0 を返すと fail-open になる)。v0.1 の「`max(1, …)` の丸めを廃止する」はこの形に改めた (§11 RV-3)。
- 検査点は実装の自由だが、少なくとも (a) pool 取得の後・最初の文 (r2db は `transaction()` の BEGIN、MitateDB は `SET LOCAL`) の前 (`_timeout_ms` の拒否と transaction を開く前の検査が兼ねる)、(b) lock 待ちの後、(c) 複数文の要求の文と文の間、に置く。(d) は置かない (U-8 の裁定 (a))。最後の文が完了した後は時計で検査せず、pre_commit → COMMIT と進む。**検査点はすべて pre_commit より前に置く。pre_commit の後は時計で検査せず COMMIT を発行する。COMMIT は文の bound の外にあり、予算では打ち切られない (M-4)。**
- 検査は時計の比較だけで DB 往復を足さない (X-1)。
- 閾値を「1 ms 未満」とする理由: `statement_timeout` の分解能は 1 ms で、0 は「無効」を意味するので、1 ms 未満の残りで文を発行する手段が無い **【PG 文書 (未実測)】**。(U-7 の裁定 (a))。
- 範囲: D-2 が決定的にするのは予算を使い切った要求だけである。残りが 1 ms 以上で文の所要時間より短い帯 (例 1.5 ms) では 200 / 413 が負荷に依り、D-3 により再送は安全である。修正前の揺れの実測: r2db で残り 0.6 ms の軽い query が 200 21/50・413 29/50 (M-1、§12.2)。

**D-3 期限で終わった要求は、行・catalog・schema revision・idempotency 記録を残さない。** 1 要求 = 1 transaction の rollback による。idempotency は契約 `structured_operations.idempotency.record` の「失敗した要求は記録を残さない」の帰結であり、execution_ms の失敗もこれに含まれる。同じ key の再送は新規の試行として実行される。同じ key の以前の要求が残したものは `structured_operations.idempotency.record` が律する (digest に budget を含む。§11.6 N-11)。
- 語の分け方: 契約 `structured_operations.dry_run.external_effects` は「externally visible な状態変化」に audit event を含めるので、本書と §9 はこの語を使わず、残さないものを列挙する。この列挙は audit の証跡を律しない (どの audit event が残るかは列挙の外で、`transactions.atomic` と `structured_operations.dry_run.external_effects` は変えない)。
- audit: `LIMIT_EXCEEDED` は耐久 denial ではない (両 peer の現物。SI-14 の security-relevant な denial ではない) ので変えない。
- **execution_ms で拒否または打ち切られた要求は commit していない。** 予算の強制 (時計の検査と文の bound) はどちらも commit の前にしか働かない **【実測 2026-10-02: §12.1 (M-4)】**。従って `LIMIT_EXCEEDED` + `limit_class: execution_ms` を受け取った利用者は、要求が何も残していないと決められる。COMMIT が予算の外の原因 (運用者の cancel、接続断) で失敗した場合の audit の扱い (allow 行の後の error 行) は現行のままで、本書の範囲外。r2db は backend の except の 5 分岐 (§1.3 #9)、MitateDB は `cell.py` の `_error_row_once_fired` と transact・単一行の経路がそれぞれ error 行を書く (§1.4 #7・#8)。【訂正 2026-10-02 (v0.4)】 v0.2〜v0.3 の「MitateDB の schema 操作は `commit_failed` を呼ばない」は誤りで、削った (§11.3)。
- 範囲 (§11.5 RW-11): 「何も残さない」は要求が実行していた atomic unit について述べる (§9.1、§9.2 の (d))。`transactions.interactive` のとおり v1 では atomic unit = 1 要求である。
- COMMIT に外部からの cancel (運用者の操作) が当たったときの code は peer と経路で違う (r2db は 413、MitateDB の transact・単一行は 503、schema 3 経路と delete は 413) が、どの経路でも commit はしておらず状態は残らない (§11.5 RW-19。観察で、起票しない)。

**D-4 エラーの形は既存のまま**: code `LIMIT_EXCEEDED`、`details.limit_class: execution_ms`。HTTP status は契約で未定義のまま (両 peer の 413 は conformance の cross-peer 証拠で固定済み)。新しい code (X-5)・新しい class (X-4)・新しい details key (X-8) は足さない。再送の可否は D-3 の保証 (何も残っていない) で足りる。`details.futility` は付けない (U-3 の裁定 (a))。

**D-5 文の bound は入口の残りで 1 回設定し (lock 待ちの後の `_retime` は MitateDB のみ)、bound に届いた文は打ち切る。予算が尽きた時点で実行中の文は bound に届く前に完了し得て、その後は次の文の前で拒否されるか、次の文が無ければ commit に進む (U-8 (a))。** 打ち切りの結果は D-3 と同じ。両 peer の形 (2 つの timeout を同値で設定) では、lock の待ちの超過は 57014 `query_canceled` になる (文の開始が lock 待ちの開始より先なので `statement_timeout` が先に満了する。`lock_timeout` 単独なら 55P03。両 peer は両方を捕まえている。M-6 **【実測 2026-10-02: §12.1】**)。文の bound は契約の義務である (依頼者裁定 V-1、§9.2 の (c))。MitateDB の SQLite backend には文の bound が無いので入れる (D-9)。v0.6 の 1 行目「文の途中で期限が来た要求は、実装の文の bound (`statement_timeout` / `lock_timeout`) で打ち切る (現行どおり)」は、入口で 1 回設定する U-2 (a) と字義で衝突したので改めた (§11.6 N-1)。
- 要求は予算より遅く終わり得る: 実行中の文は完了するか自身の bound に届くまで走り、接続の確立は残りを超え得、pool の維持・commit 前の audit の書き込み・commit は予算で bound されない (§9.1 の末尾で開示する。§11.5 RW-4、§11.6 N-1・N-5)。
- 上限の主張は**文の実行区間に限る**: 文の bound を「scope 入口の残り」で 1 回設定し (MitateDB は実際に lock を待った後だけ `_retime` で再設定する。r2db は再設定せず、lock 待ちの後は時計の再検査だけ。D-9、§11.5 RW-10)、文の間は D-2 の時計検査で補う現行の形では、文の実行区間の合計は「残りの 2 倍未満」である (文 n は残りが尽きる前にしか始まらず、その文自身は入口の残りまで走れる) **【PG 文書 (未実測): 文ごとの計測】**。文ごとに bound を再設定すれば「残り + 1 文の分解能」になるが、文ごとに 1 往復が増える。U-2 の裁定 (a): 現行の形 + 文の間の時計検査。
- 文の実行区間の外は、次の別の上限で bound される:
  - 接続の確立: 上限は `connect_timeout`。MitateDB は `min(connect_timeout, max(1, ceil(残り)))` で psycopg の下限 2 s が掛かる (`pool.py:444-492`)。r2db は固定 5 s (`postgres.py:230`)。接続の確立の後に期限が切れていれば、D-2 (a) の検査 (pool 取得の後) が文の前で捕まえる。**判定 (依頼者裁定 V-3。時計の判定 1 本)**: 原因を問わず、接続の取得が失敗した時点で予算が尽きていれば (残り < 1 ms) `LIMIT_EXCEEDED` execution_ms、尽きていなければ `SERVICE_UNAVAILABLE`。即時の拒否 (接続拒否) は 503 のまま。開示: 応答しない宛先 (blackhole) は connect の時間切れとして現れ、その時点で予算はほぼ尽きているので 413 になり得る (§6.5 の `security/CONTROL_MAPPING.md:1023` に開示を足す)。どちらの code でも何も残らず再送は安全。v0.5 の判定 (時間切れで失敗し予算が尽きていれば 413、尽きていなければ (拒否・到達不能・予算内の時間切れ) 503。判定は process 内の時計) は、応答しない宛先で U-6 の裁定の説明文 (到達不能は 503) と食い違うので、2026-10-03 に V-3 で置き換えた (§11.5 RW-5)。
  - pool の維持の文 (r2db の checkout ごとの `SELECT 1` `postgres.py:621`、MitateDB の idle ping `pool.py:369`)。予算の外。MitateDB の ping には timeout が無い (§11.5 RW-13)。
  - audit sink への書き込み (別接続)。
  - COMMIT: 予算でも文の bound でも bound されない (M-4)。両 peer とも deferred の仕事を持たないので、所要時間は WAL の書き出し。

**D-6 契約の文言を足し、minor 版 1.15.0 (subordinate ruling 20) とする (U-4 の裁定 (a))。** 足す場所と記録:
- execution_ms の節 (範囲、始点、待ちの算入、commit の開始まで、1 page = 1 要求、dry_run、文の定義、「使い切った要求は次の文の前で拒否」、文ごとの bound、「拒否・打ち切られた要求は commit していない」、遅く終わり得ることの開示。§9.1 が正)。置き場は `limits` の新 key `execution_ms` (U-9 の裁定 (a))。`conformance-tests/test_contract.py:138-146`・`:180-184` の `_PRE_1_8_0_LIMITS_KEYS` の pin は切り直す (依頼者確認は U-9 の裁定が兼ねる。§10)。v0.1 では `limits.execution_ms` の新 key に置くと定めていたが、v0.2 (2026-10-02) で `conformance-tests/test_contract.py` の `_PRE_1_8_0_LIMITS_KEYS` の pin (`:138-146`、`:180-184`) が新しい sibling key を 1.8.0 の裁定として禁じていることがわかったので、U-9 に移した (§11 RV-14)。`errors.details_vocabulary.LIMIT_EXCEEDED` は変えない。
- `structured_operations.idempotency.record` には挿入しない。§9.1 の「no idempotency record」と義務 (d) (v0.5 の (c)) で足りる。v0.1 の挿入案は、文中への挿入が `PIN_1_7_0_IDEMPOTENCY_RECORD` (`conformance-tests/test_contract.py:2165-2166`、包含で照合 `:2286`) を、末尾への追記が `PIN_1_8_0` の endswith (`:525-532`、`:578`) を壊すので削った (§11 RV-14)。
- `versioning.version_binding` の散文に 1.15.0 の段落 (無条件義務 four の列挙、「1.14.0 のままの実装は遡って縛られない」)、`versioning.obligations[]` に entry (識別子 4 つ。§9.3)。v0.5 の 3 件に義務 (c) (文ごとの bound。v0.6 の「実行中の文の打ち切り」を §11.6 N-1 で改め、識別子は `statements_run_under_per_statement_bound`) を足した (依頼者裁定 V-1。§11.5 RW-1)。段落の置き場は 1.14.0 の前例どおり「1.14.0 の段落の直後・version-flip 文の前」。
- `structured_operations.dry_run.decision` に、execution_ms の拒否は dry run と real で同じとは限らない旨の相互参照の 1 文を追記する (§9.4。`PIN_1_7_0_DRY_RUN_DECISION` は `conformance-tests/test_contract.py:2279` の包含照合で、`dry_run["decision"]` を見る pin はこの 1 件だけなので、追記で壊れない)。
- 1.14.0 の前例どおりの記録: `spec/CONTRACT_HISTORY.md` の revision note (`:428` の Revision note 10 の形。既存の義務 1.7.0 (3) を狭めることも記録する)、`spec/CCR_DISPOSITION.md` の ruling 20 (`:343` の ruling 19 の形)。
- 文言は候補として §9 に置き、依頼者が確定する。変える節に掛かる pin (下の列挙。`_PRE_1_8_0_LIMITS_KEYS` は U-9 の裁定 (a)) を確定後に更新する (本 session では触らない)。
- 版の切り替え (§11.5 RW-7、§11.6 N-6。監督裁定 (B)): `spec/` の 1.15.0、生成される `OPERATION_CATALOG.json` の 3 部、両 peer の契約の同梱コピー、両 peer の版の flip、新条件と version gate の guard を、統合 branch 上の同じ 1 commit に入れる (C-29 が catalog と capability document の版の一致を assert するため)。振る舞いの WP (両 peer の検査・写像・port v1.22) はそれより前の commit で、版を動かさない (1.10.0 の `3af11b3` → `5d988c6` の形を踏襲し、flip の commit に spec も入れる)。中間 commit は統合 branch 上にだけあり main には 1 つの merge で入るので、契約の version-flip 文 (配備が宣言より先に振る舞いを出すことを非適合とする) には当たらない (§11.7 F-12)。中間 commit で C-29・guard が赤にならない。v0.6 の「1 commit で main に入れる (1.11.0 の `e21922a` と同じ形)」は「WP は統合 branch の上で分けて作る」と字義で衝突したので改めた。
- 壊れる pin (§11.5 RW-8): `test_contract_declares_1_14_0` (`conformance-tests/test_contract.py:78-91`)、`_PRE_1_8_0_LIMITS_KEYS` (`:138-146`、照合 `:180-184`)、`test_contract_pins_the_1_14_0_version_binding_paragraph_verbatim` (`:1555-1568`。等値照合の右端を 1.15.0 の段落の開始へ)、`:1572` の docstring。
- 更新対象 (§11.5 RW-8): `spec/CONTRACT_HISTORY.md` の version_binding の引用 (`conformance-tests/test_contract_history_register.py:343` が全文一致を照合)、`spec/README.md` の版の段落、両 peer の "1.14.0" の pin (`r2db-api/tests/test_foundation.py:252` ほか、`r2db-api/tests/test_audit_query.py:1991`・`:4047`・`:4081`、`r2db-api/tests/test_control_plane_service.py:1808`、`r2db-api/tests/test_denial_details_and_request_id.py:514`、`MitateDB-api/tests/test_http.py:393`、`MitateDB-api/tests/test_control_plane_service.py:574`、`MitateDB-api/tests/test_audit_query.py:1727`・`:1757`・`:1769`・`:3849`、`MitateDB-api/tests/test_denial_details_and_request_id.py:552`・`:566`。§11.6 N-12)。散文の義務の個数 (four) と `obligations[]` の entry の一致は `_UNCONDITIONAL_COUNT_RE` (`conformance-tests/test_operation_catalog_register.py:314`) では機械照合されないので、`obligations[12]` の index 固定の pin (`conformance-tests/test_contract.py:1582` の形) を置く。

**D-7 conformance で決定的に固定する: 新しい共通条件を 1 件足す** (番号は conformance の WP で採番し、C-35 の次を見込む。`tools/check_doc_refs.py` が未定義の C 族番号を参照切れとして止めるので本書では番号を書かない。先例 `docs/design/MULTI_PROCESS_WORKER_V0_1.md:766`。以下「新条件」)。性質は §6.2 の (i)〜(iii)。
- version gate (§11.5 RW-7): 新条件は 1.15.0 以上を宣言する plug に束縛し、登録された全 plug が束縛されることを assert する非空振りの guard を置く。
- 駆動 (i): 新 primitive は、契約の点で「rate・concurrency・budget の bound が確定した後、最初の接続取得の前」で止めると定義する。従って期限の検査と文のどちらよりも前である。受理点から stall 点までに検査が無いので `budget.execution_ms = 1` でよく、十分長く (例 100 ms) 保持して放すと、放した後の最初の検査で拒否される。
- 駆動 (ii)(iii): stall 点に届くまでに文と検査がある (r2db は入口検査・`SET LOCAL`・key lock・lookup、plan 検証)。予算 B は「stall 点に届く」のに足りる値にし、保持は test が受け取る「stall 点に入った」合図 (`hold_after_idempotency_lookup` / `hold_after_plan_verification` の handle の既存の合図) の時点から B + 余裕 (例 B/5) を単調時計で測って放す。受理点は stall 点より前なので、放した時点で受理点からの経過は必ず B + 余裕以上である。test は「stall 点に入った」ことを assert し、届かずに先に拒否されたら赤にする (運用条件 §1.5 の 32 の空振り禁止)。test は「held」か「要求の完了」のどちらかを待ち、完了が先なら即座に赤にする (`wait_until_held` の timeout 30 s を待たない。§6.4、§11.5 RW-17)。
- B は作業指示書の conformance の WP で、完了ゲートの中での到達時間を測って決める。初期値の候補は 500 ms (無負荷の到達時間の最大 17.2 ms の約 30 倍。保持は B + B/5 = 600 ms。§12.4)。余裕を B/5 とするのは `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 の教訓 (窓は `max_execution_ms / 5` の形 — ここで効いている予算は B) による。
- (iii) の plan を得る dry run は実要求と同じ budget を付ける: budget の無い dry run で得た plan を budget 付きの実要求に出すと、6 plug すべてで `PRECONDITION_FAILED` (`violated_declaration` は `plan`) になる (plan は budget を含む要求に束縛される。§12.4)。positive control も自分の予算で plan を取り直し、dry run は hold を仕掛ける前に済ませる (§6.4、§11.5 RW-14)。
- (ii) の再送は budget を外して送る (digest が変わる)。従って「記録があれば `CONFLICT`、無ければ新規実行」で観測し、B の下での成功に依らない。
- 各 vector に positive control (十分な予算で同じ保持 → 完了し効果が残る) を組にする (`docs/design/CONFORMANCE_ADAPTER_V1.md:40` の規則)。
- **決定性の論法**: 拒否の方向は負荷に対して単調である — 放した時点で受理点からの経過が予算より長ければ、負荷はそれを更に長くするだけで短くしない。従って「放した後の拒否」は負荷で揺れない。**単調性が保証するのは放した後の拒否だけである。** stall 点への到達、(iii) の plan を得る dry run、(ii) の再送の成功は B の余裕に依る (成功の方向)。
- (ii) は既存の `hold_after_idempotency_lookup` (lock 保持・効果 0 件で止める)、(iii) は既存の `hold_after_plan_verification` で駆動できる (修正前の計測で 6 plug とも stall 点に 20/20 到達。§12.4)。ただし (ii) の stall 点は port v1.22 で r2db の 2 実装を「予約の後」(`_idempotency_reserve` が戻った後。§11.6 N-3) へ移して揃える。(iii) は docstring の点を 4 実装が既に満たすので変えない (v0.5 の「stall 点の定義と 4 実装を揃える」を (ii) だけに改めた。§6.4、§11.5 RW-14)。(i) の点で止める primitive は port v1.21 に無く、port v1.22 の新 primitive (仮称 `hold_after_admission`。ABC + 6 plug) が要る。
- 観測: 応答だけでは「文を発行しなかった」と「1 ms で cancel された」を区別できない。primitive の handle が「放した後に要求のために発行された文の数」(D-2 の定義の文。要求が保持するすべての接続) を返す (台帳 R-79 の `execute_count` が接続ごとの文の数を既に数えている)。観測値は、要求が使う pool の `execute_count` の差 + transaction / savepoint を**開いた**回数 (enter 側だけ) − checkout の維持の文の回数 (§6.4、§11.6 N-3)。enter 側だけを数える計数は現物に無いので、足す場所 (両 peer の `psycopg_counting.py` か plug 側) は port v1.22 の設計で決める。v0.6 の「`execute_count` と `txn_count` の差」は、`txn_count` が transaction を終える COMMIT / ROLLBACK / RELEASE と `commit()`・`rollback()` も数え (`r2db-api/src/r2db_api/psycopg_counting.py:115-182`、`MitateDB-api/src/mitatedb_api/psycopg_counting.py:115-182`)、正しい実装で偽の赤になるので改めた。positive control で PostgreSQL の 4 plug について「放した後の文の数 >= 1」を assert する。in-process 2 plug は 0 ではなく None (観測不能) を返し、test は None のとき code だけを見る。既存 handle は文の数を持たない (§6.4)。U-5 の裁定: (i)〜(iii) を全部、観測は文の数。
- `limit_enforcement.execution_ms` による分岐は置かない (§6.2 の註)。
- C-05 の開示「execution_ms never driven」は新条件を指す形に書き換える (§6.5)。`security/CONTROL_MAPPING.md` に両 peer の「文発行前の拒否」「rollback」の claim を足す (実装 WP の仕事)。

**D-8 Security Invariants**: 新しい不変条件は足さない。適用は §7。

**D-9 実装の義務 (本書は列挙だけ。作業指示書は裁定後)**:
- r2db — 入口検査 (`postgres.py:1498`、`:1613`) を pool 取得の後へ**移す** (足すのではなく置き換える。入口の検査点は無くなる)。apply_schema も同じ位置に 1 つ置く。pool 取得に期限の残りを渡し超過を `LIMIT_EXCEEDED` execution_ms に写す (U-6 の裁定 (a))。advisory lock 待ちの後は時計の再検査だけ (helper の検査が兼ねる)。bound の再設定はしない (往復を足さない。文の実行区間の「残りの 2 倍未満」は再設定が無くても成り立つ: 次の文は残りが尽きる前にしか始まらず、その文は入口の残りまでしか走れない。v0.5 の「再検査と再設定」から再設定を外した。§11.5 RW-10)。operation loop・DDL・store の前 (pre_commit より前) の検査。新規接続の箇所は 2 つ (`_acquire` の `postgres.py:436` と、`:655`・`:660` の差し替え)。両方に残りを渡す (§11.5 RW-13、§11.6 N-12)。`_timeout_ms` は残り 1 ms 未満で `LIMIT_EXCEEDED` を上げ、0 を返さない。`query` の SELECT 後の検査 (`postgres.py:1554`) は外す (U-8 の裁定 (a))。規則は 1 つ: **検査は次に文を発行する点にだけ置き、次が pre_commit / COMMIT である点には置かない。** transact の loop 後の検査 (`postgres.py:1701`) は、次に idempotency の store (文) が続く要求では「次の文の前」の検査として残り、続かない要求では外れる (行ごとの確定は作業指示書)。r2db の in-memory backend は契約の意味での文を発行しないので、義務 (c) は空 (bound を設定する文も打ち切る文も無い)。検査点の置き方 (義務 (b)) に限って、r2db の in-memory backend (`structured.py`) は 1 operation を 1 文とみなし、各 operation の前で検査し、最後の operation の後の検査 (`structured.py:937-938`・`:1161-1162`) は外す (§11.6 N-7)。
- MitateDB — 最優先の欠陥は、文の間の検査が無く、予算を過ぎた要求が commit することである (§1.5、§12.2、§12.4)。`request_scope` 入口 (pool 取得後) の検査、文の間の検査、`_retime` の閾値を D-2 に揃える、`_timeout_ms` を D-2 の形にする、`record_idempotency` (`backend_postgres.py:1817-1825`) の psycopg 例外の翻訳 (文なので範囲内)。`SET LOCAL` (`backend_postgres.py:493-500`) と `_retime` (`:544-552`) の `QueryCanceled` / `LockNotAvailable` を execution_ms に写す。schema 3 経路 (`backend_postgres.py:1058→1069→1070`、`:1204→1229→1230`、`:1372→1382→1383`) の `_write_idempotency_row` を `pre_commit` の前へ移し、r2db (`postgres.py:1725→1733`、`:2416→2426`) と transact の順序 (store → pre_commit → COMMIT) に揃える (`_error_row_once_fired` があっても、pre_commit の後の文が予算で cancel されると allow + error の 2 行が残る経路が開いたままになるため)。SQLite backend に文の bound を入れる (例: `sqlite3` の progress handler で期限を見て打ち切る。手段は実装の自由、DB 往復は無い。依頼者裁定 V-1。§11.5 RW-2)。handler は文の実行中だけ有効にし、commit・rollback の前に外す (§11.6 N-4)。
- 【訂正 2026-10-02 (v0.4)】 v0.2〜v0.3 の「schema 4 経路の cancel 分岐に `commit_failed` を足す」「この欠けを台帳に起票する」「transact の commit の psycopg 例外の翻訳」を削った。前 2 つは呼び出し側の `_error_row_once_fired` が既に error 行を書くため (§1.4 #7。台帳 v1.151 の R-42 行)、3 つ目は commit が予算の外にあるため (M-4)。
- 両 peer — 接続の確立の時間切れの写像 (D-5。U-6 の裁定)。
- 両 peer — 閾値を D-2 (残り < 1 ms) に揃える: `check_deadline` (r2db `limits.py:100` は `clock() > deadline`)、SQLite の `_check_deadline` (strict `>`)、r2db の in-memory backend。
- 両 peer — 変異: 各検査点を外すと新条件の対応 vector が赤になること (観測は D-7 の文の数。見込みは §6.6)。
- 両 peer — 検査は文を発行する helper 1 か所に置く形を推奨する (r2db の `_run` `postgres.py:234`、MitateDB は文を発行する共通の関数 (PostgreSQL backend の `_execute` `backend_postgres.py:295`)。1 つの変異で全点を覆える。pool の維持・COMMIT / ROLLBACK は helper を通らないので D-2 の定義と合う)。transaction を開く点は helper を通らず BEGIN を発行する (r2db の `with conn.transaction():`、例 `postgres.py:1117`。psycopg の `transaction()` は入口で BEGIN を送る) ので、その直前にも同じ検査を 1 つ置く (D-2 (a) の点。MitateDB の暗黙の BEGIN は最初の文と同時なので helper の検査が兼ねる)。r2db の入れ子の `transaction()` (`postgres.py:1261`・`:1317`・`:1419`・`:1435`。savepoint を開く) の前にも同じ検査を置く (§11.6 N-8)。採否は作業指示書 (§11.5 RW-9)。
- 共通条件で駆動しない検査点 — D-2 (b) lock 待ちの後、U-6 の裁定の pool 待ち超過と接続確立の時間切れの写像、閾値、義務 (c) の文の bound — は peer の単体テストで固定する (r2db は clock の注入、MitateDB は test 側での `time.monotonic` の差し替え。製品コードに hook は足さない)。義務 (a) (待ちを数え、受理点より遅く始めない) の証拠もこの単体テストと `security/CONTROL_MAPPING.md` の claim で取る (§6.4)。完了条件 → 変異の対応は作業指示書で確定する (運用条件 §1.5 の 40)。SQLite / in-memory backend は同じ意味論。

## 4. 却下した代替案

| ID | 代替案 | 却下の理由 |
|---|---|---|
| X-1 | 期限検査のための DB 往復 (`SELECT clock_timestamp()`、`SELECT now()`) | 決定軸に反する。process 内の単調時計で足りる (両 peer とも既にそうしている) |
| X-2 | 現行 (`max(1, …)` で 1 ms の文を発行) を維持し「境界では未定義」と文書化 | 予算を使い切った要求の結果が負荷で変わるのは SI-08 の Verification 句 (deterministic) に反し、利用者が再送の可否を決められない (残りが 1 ms 以上の帯は D-2 の範囲の外) |
| X-3 | 計測の始点を「最初の文」にして待ちを数えない | 利用者に見える所要時間が予算と無関係になり、pool・lock の保持が予算で bound されない。MitateDB の現行の読み (待ち超過 = 予算超過) とも逆行。U-1 の裁定 (a) で不採用 |
| X-4 | 待ちを別の limit class (例 `queue_ms`) にする | `limits.classes` の語彙に新語が要り (1.2.0 の規則)、利用者が 2 つの予算を推論する。安全の結果は増えない。U-1 の裁定 (a) で不採用 |
| X-5 | 文の途中の期限切れを `ATOMICITY_FAILED` で返す | 契約はこの code の意味を定義していない。両 peer の現物は `LIMIT_EXCEEDED` で、limit_class が原因を伝える |
| X-6 | PostgreSQL 17 の `transaction_timeout` を使う (transaction 全体の上限を 1 回で設定) | CI は `postgres:16`。作業機も 16.14 (M-2、§12.1)。将来の選択肢として M-2 に残す |
| X-7 | conformance のために製品コードに test 用 hook や clock 注入を足す (MitateDB には clock 注入が無い) | `docs/design/CONFORMANCE_ADAPTER_V1.md` の規律 (adapter の primitive で駆動し、製品コードに test 用 hook を足さない) に反する。stall primitive で実時間を経過させれば決定的に拒否側へ倒せる (D-7 の単調性) |
| X-8 | 新しい details key (`stage` / `executed` など) で「どこで予算が尽きたか」を返す | 既存の `futility` で足り、`details` の語彙を増やさない |

## 5. 選択肢と依頼者裁定 (2026-10-02 に全件裁定済み。逐語は §10)

**U-1 計測の始点と待ちの算入**
- **【依頼者裁定 2026-10-02】(a)。**
- (a) 受理点から、待ちをすべて数える (**推奨**。D-1)。
  - 利点: 実装が制御する所要時間を 1 つの予算で bound する。両 peer の現行の計算点のままで、新しい class が要らない。
  - 欠点: 受理点の前は数えない: 逐次で r2db 約 0.5 ms・MitateDB 約 5 ms (うち認証 p50 0.23〜0.25 ms / 2.4〜2.6 ms)、32 並列では受理点の前の待ち (worker thread の順番待ち) が p50 53〜78 ms・max 101〜113 ms (M-7、§12.3。in-process の ASGI で、uvicorn・TLS・reverse proxy を含まない)。pool・lock の待ちは他要求の負荷で伸びるので、同じ要求が負荷で拒否され得る (再送は D-3 で安全)。
  - 推奨の理由: 契約は「遅くとも受理点」と定め、実装がより早く数え始めることを許す。受理点の前の待ちは配備の資源保護 = 台帳 R-31 の範囲で、execution_ms の意味論に入れると実装が HTTP 層の待ちを観測する義務を負う。
- (b) 受信時から (認証・body の解析も数える)。
  - 利点: より厳しく、利用者に見える所要時間に最も近い。
  - 欠点: HTTP 層の実装に依る。(a) との差は逐次で約 0.5 ms (r2db)・約 5 ms (MitateDB)、既定 5000 ms の 0.01〜0.1%。32 並列で p50 53〜78 ms (§12.3)。
- (c) 最初の文から (待ちを数えない。X-3)。
  - 利点: 予算が文の実行だけを指し、待ちの長さで拒否されない。
  - 欠点: 利用者に見える所要時間が予算と無関係になり、pool・lock の保持が予算で bound されない。MitateDB の現行の読みと逆行する。
- (d) 待ちを別 class に分ける (X-4)。
  - 利点: 待ちと実行を別々に bound できる。
  - 欠点: `limits.classes` に新語が要る (1.2.0 の規則)。利用者が 2 つの予算を推論し、安全の結果は増えない。

**U-2 文の途中の期限切れの上限 (文の実行区間。区間外は D-5)**
- **【依頼者裁定 2026-10-02】(a)。**
- (a) 現行の形 + 文の間の時計検査 (上限 < 残りの 2 倍。往復を足さない。**推奨**)。
- (b) 文ごとに `SET LOCAL` を再設定 (上限 ≒ 残り。文ごとに 1 往復)。要求あたり 3〜15 往復を足す。見積もりの下限は 1 往復 11 µs × 文の数 = +0.03〜0.17 ms、上限の目安は現在の DB 時間の倍 = +0.36〜0.95 ms (http plug の p50 1.2〜1.9 ms の 2〜50%)。実装して測った値ではない (M-3、§12.1・§12.5)。決定軸 (往復を足さない) に反する点は変わらない。
- (c) PostgreSQL 17 の `transaction_timeout` (X-6)。作業機の 16.14 に `transaction_timeout` は無い (M-2、§12.1)。
- 契約文言は (a) でも成り立つ弱さにする (v0.8: 「設定後の各文は、算出時の残りを超えない文の bound の下で走り、bound に届いた文は打ち切られる。尽きた時点で実行中の文は完了し得る」。§9.1)。

**U-3 再送可否の伝達** (v0.1 の推奨は (b)。v0.2 (2026-10-02) で (a) に移した — §11 RV-16)
- **【依頼者裁定 2026-10-02】(a)。**
- (a) D-3 の保証だけ (何も残らない → 再送は常に安全) (**推奨**)。
- (b) 加えて、文の実行で使い切ったときは `details.futility` を MAY で付ける (任意なので conformance は「付くなら SI-10 に適う内容」だけを見る)。欠点: 実装は「再送しても同じ」を知り得ない (文の所要時間は負荷と行 lock の待ちで変わる) ので、`futility` の文を真に書けない。
- (c) 必須の新 key (X-8、却下)。

**U-4 契約の版**
- **【依頼者裁定 2026-10-02】(a)。**
- (a) minor 1.15.0 + subordinate ruling 20 + obligations entry (**推奨**)。先例: 1.11.0 (拒否 code を変える義務)・1.12.0 が minor。本件は未定義の意味を埋めるものであり、文発行前の拒否の型は `structured_operations.idempotency.record` の「before it executes」に既にある。
- (b) major。既存の義務 1.7.0 (3) (dry run の拒否は real と同じ code と details) を execution_ms について狭めるので、この読みを強める。1.14.0 の自制「requires no implementation to refuse a request it accepted under 1.13.0」に照らすと、今 200 になり得る要求を拒否に変える。ただしその 200 は保証されていない偶然の結果である。
- (c) 版を上げず subordinate ruling の註だけ (義務を機械可読にできない)。

**U-5 conformance の範囲**
- **【依頼者裁定 2026-10-02】範囲 (a)、観測 = 文の数を返す。**
- (a) 新条件の (i)〜(iii) を全部、port v1.22 の新 primitive を含めて (**推奨**。(i) が台帳 R-42 の候補そのもの)。
- (b) 既存 primitive で駆動できる (ii)(iii) だけを先に、(i) は後続。
- (c) 観測の形: handle が「放した後に発行された文の数」を返す (**推奨**) / 応答 code だけ (r2db の 3 plug と MitateDB の SQLite plug は修正前から期待どおりの code を返すので、D-2 の検査点を外す変異がこの 4 plug で常に生き残る。M-8)。in-process の MitateDB SQLite plug には、SQLite の trace callback で文を数える代替がある (r2db の in-memory plug には文が無い)。

**U-6 pool 待ち超過・接続確立の code**
- **【依頼者裁定 2026-10-02】pool 待ち (a)、接続確立 (a)。**
- pool 待ち: (a) 予算を超えたら両 peer とも `LIMIT_EXCEEDED` execution_ms (**推奨**。MitateDB の現行は上限到達の `PoolExhausted` だけ。r2db は 503 から変える)。(b) r2db の現行 (503 `SERVICE_UNAVAILABLE`) を許す (peer で分かれる)。
- 接続確立の時間切れ・失敗: (a) 予算由来の connect timeout の超過は 413 execution_ms。(b) 503 のまま (MitateDB の現行 `PoolConnectFailed`、§1.4 #2)。材料: `security/CONTROL_MAPPING.md:1023` (pool・lock の待ちの超過は `LIMIT_EXCEEDED`、到達不能は `SERVICE_UNAVAILABLE`) は現物と合うが、新規接続の確立が予算を超えた場合がどちらの句に入るかを述べていない。
- **【依頼者裁定 2026-10-03 (V-3)】時計の判定 1 本 + 開示。**
- 【v0.4 で削除: 予算による commit 段の cancel は存在しない (M-4)】

**U-7 閾値**
- **【依頼者裁定 2026-10-02】(a)。**
- (a) 残り < 1 ms (整数 ms で 0) で拒否 (**推奨**。D-2)。
- (b) 残り ≤ 0 で拒否し、0 < 残り < 1 ms は 1 ms で発行 (現行の `_retime`)。
- (c) 残り < 安全余裕 (例 5 ms) で拒否。利点: D-2 の範囲の外に残る「残り 1 ms 以上・文の所要時間未満」の帯 (負荷で 200 / 413) を狭める (M-1: 1 ms を超える文は 1.04〜1.37 ms で cancel される。§12.1)。欠点: 契約で数を決めることになる。

**U-8 最後の文が完了した後の時計検査**
- **【依頼者裁定 2026-10-02】(a)。**
- (a) 検査しない — 結果は要求自身の最後の文の完了で決まり、その後は時計で拒否しない。(a) では D-2 (d) を置かない: 最後の文の後は pre_commit → COMMIT と進む (r2db は `postgres.py:1554` の検査を外す) (**推奨**: 文の実行は文の bound で既に bound されており、完了した仕事を捨てて利用者に何も返さないのは自由の損失。現物の r2db は (b) の形で、仕事が終わっているのに 413 になる回が負荷で変わる (M-1: 残り 0.6 ms の軽い query が 200 21/50・413 29/50。§12.2))。
- (b) 検査する — (d) を置き、read は SELECT の後にも検査する。予算を wall-clock の上限として厳密に読む (r2db の現行。MitateDB は read の SELECT 後に検査を足す)。
- どちらも決定的 (境界の位置が違うだけ)。どちらを選んでも commit は bound されない (M-4)。§9.1 の差し替えは [U-8 (a)] の印。

**U-9 `limits.execution_ms` の置き場**
- **【依頼者裁定 2026-10-02】(a)。**
- (a) `limits` の新 key `execution_ms` (per-class の key の先例 `enum_members`)。ただし `conformance-tests/test_contract.py:138-146`・`:180-184` の `_PRE_1_8_0_LIMITS_KEYS` は「新しい sibling key を置かない」を 1.8.0 の裁定として pin しており、pin の切り直しに依頼者確認が要る (**推奨**)。
- (b) `limits.profile` の文字列の中 (1.8.0 (2) の先例)。`limits.profile` は endswith の pin (`conformance-tests/test_contract.py:111-115`、`:177`) を持つ。1.8.0 の文より前に挿入すれば pin はそのまま、末尾なら切り直す。
- (c) `limits.request_budget` の末尾。`request_budget` の `PIN_1_7_0` は包含照合 (`:2267-2268`) なので、末尾追記なら pin はそのまま。

## 6. conformance への影響

### 6.1 現状 (基点 main)

- C-05 は「2 classes never driven -- `execution_ms`, `idempotency_retention_ms` (no deterministic construction / not enabled)」と開示する (`conformance-tests/CONDITIONS.md:34`、フェーズ7 設計の D-6.2/§7.3)。
- C-24 は execution_ms を駆動せず、宣言 unavailable の budget=1 → `CAPABILITY_UNSUPPORTED` と、配備値 + 1 → `VALIDATION_FAILED` だけを使う (`conformance-tests/test_c24_request_budget.py:40-41`)。
- port v1.21 の stall primitive (`conformance-tests/adapter.py`): `hold_in_flight` (`:1810`。plug 自身の catalog 読みを止める。budget も operation も指定できない)、`hold_after_idempotency_lookup` (`:1901`。caller が出す budget 付き mutation を idempotency 受理区間の末尾 = lock 保持・効果 0 件で止める。C-27 の primitive)、`hold_after_plan_verification` (`:1965`。schema 操作を DDL 前で止める)。clock の注入・期限を操る手段は port に無い。
- 6 adapter: in-process と http の各 plug は個別実装。socket 2 本は http plug の subclass で `hold_*` を自前で定義せず (`r2db-api/conformance/conformance_adapter_r2db_socket.py:477`、`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py:338`)、同一 process 内の cell を差し替えるので、stall は socket 越しでも効く (両 socket plug で確認済み。§12.4)。
- port の設計原則は `docs/design/CONFORMANCE_ADAPTER_V1.md` の §2 (negative test に positive control を組にする規則は `:40`)。port 拡張の規則: 同書 §25 の導入 (`:3461-3472`) が明文で定めるのは「test 用 hook を製品コードに足さない」「追加のみ」で、ABC の `@abstractmethod` と全 plug の実装は既存 primitive の実際の形である (同書の導入の明文ではない)。
- `security/CONTROL_MAPPING.md`: r2db `_set_timeouts` が execution_ms を `statement_timeout`/`lock_timeout` に写す second enforcement layer (`:659`)。MitateDB は期限を `SET LOCAL` に写し、pool・lock 待ちが期限を超えれば `LIMIT_EXCEEDED` execution_ms (`:852`、`:869-870`、`:1023`)。`:1023` は現物と合う (pool 上限到達の待ち超過は 413、到達不能は 503、§1.4 #2)。新規接続の確立が予算を超えた場合は述べていない (U-6)。「文発行前の拒否」「1 ms」「rollback の保証」は claim されていない。

### 6.2 新条件の候補文 (候補。文言は契約の確定後に CONDITIONS.md の形で書く)

execution_ms を使い切った要求は決定的に終わる: (i) 受理点の後・最初の接続取得の前で予算を使い切った要求は、文を発行せず `LIMIT_EXCEEDED` + `details.limit_class: execution_ms` で終わる。(ii) 複数文の要求が文の間で予算を使い切ったら、次の文を発行せず同じ形で終わり、行も idempotency 記録も残らない (同じ idempotency_key で budget を外した再送は `CONFLICT` でなく新規として実行される)。(iii) schema 操作が DDL の前で予算を使い切ったら、DDL を発行せず同じ形で終わり、revision は動かない。各 vector は十分な予算の positive control と組にする。適用: SI-08、SI-11。

**註 (`limit_enforcement.execution_ms` による分岐)**: 新条件は `limit_enforcement.execution_ms` が `unavailable` の配備を `CAPABILITY_UNSUPPORTED` 側に分岐させない。ただし根拠は契約の `limits.finite_required` ではない — `limits.finite_required` (`spec/data-service-api.v1.json:927`) は真偽値 `true` だけで class ごとの必須を述べず、capability document の `limit_enforcement` の schema (`:1351-1360`) はどの class にも `unavailable` を許す。execution_ms を `unavailable` にしないことは C-05 V3 (固定 9 class。`conformance-tests/test_c05_limit_declaration_agreement.py:78-82` の `_FIXED_NINE`、検査は `:1258`。出所はフェーズ7 設計 D-6.1 の裁定 S-2) が conformance で固定している。従って新条件は C-05 V3 を前提とし、`unavailable` の配備は C-05 V3 で赤になる。C-24 の unavailable 分岐は `request_budget` capability のもので、1.9.0 以上を宣言する実装は `request_budget` を unavailable にしない (`versioning.version_binding` の 1.9.0 の段落) ので、新条件には現れない。

義務 (c) (文ごとの bound) は共通条件では駆動せず、peer の単体テストで固定する (§6.6、D-9)。

### 6.3 3 vector

| vector | 止める primitive | 止める要求と保持 | 観測 | positive control |
|---|---|---|---|---|
| (i) 受理点の後・最初の接続取得の前 | port v1.22 の新 primitive (仮称 `hold_after_admission`) | `budget.execution_ms = 1` の要求。保持は例 100 ms | code・limit_class、放した後の文の数 = 0 (U-5 (c)。in-process 2 plug は None で code だけ) | 十分な予算で同じ保持 → 完了し効果が残る。PostgreSQL の 4 plug で放した後の文の数 >= 1 |
| (ii) 文の間 | `hold_after_idempotency_lookup` (既存) | `budget.execution_ms = B` の idempotency_key 付き mutation。保持は「stall 点に入った」合図から B + 余裕 | 「stall 点に入った」こと、code・limit_class、行が残らないこと、budget を外した同 key の再送が `CONFLICT` でなく新規実行になること、文の数 | 同上 |
| (iii) DDL の前 | `hold_after_plan_verification` (既存) | `budget.execution_ms = B` の plan 付き schema 操作 (plan は同じ budget を付けた dry run で得る、D-7)。保持は「stall 点に入った」合図から B + 余裕 | 「stall 点に入った」こと、code・limit_class、revision が動かないこと、文の数 | 同上 (plan は自分の予算の dry run で取り直す) |

- 文の数は要求が使う pool の `execute_count` の差 + transaction / savepoint を開いた回数 (enter 側だけ) − checkout の維持の文の回数 (§6.4、§11.6 N-3)。
- B と余裕・保持の測り方は D-7 (B は conformance の WP で決める。初期値の候補 500 ms)。決定性の論法は D-7 の単調性 (保証は放した後の拒否だけ)。修正前に測れる分の実証は §12.4、残り (100/100、vector (i)、完了ゲートの負荷の下の B) は M-8。
- 費用の見積もり: 1 plug あたり (i) 0.1 s ×2 (positive control 込み) + (ii)(iii) 1.2B ×2 ×2 ≒ 0.2 + 4.8B s、6 plug で 6 × (0.2 + 4.8B) s (直列。例 B = 0.5 s なら約 16 s)。保持は budget で選ぶ B に比例し、配備の execution_ms (既定 5000) には比例しないので、運用条件 §1.6 の 44 (構成値に比例しない形) に反しない。

### 6.4 port v1.22 の候補

- 新 primitive (仮称 `hold_after_admission`): caller が出す budget 付き要求を、契約の点で「rate・concurrency・budget の bound が確定した後、最初の接続取得の前」で止める。ABC の `@abstractmethod` + 6 plug の実装 + `docs/design/CONFORMANCE_ADAPTER_V1.md` の新節。製品コードに test 用 hook を足さない (X-7)。
- handle の候補: 放した後に plug の backend が発行した文の数を返す (台帳 R-79 の `execute_count`。両 peer の `psycopg_counting.py`)。観測は「放した後に要求のために発行された文が 0 件」と定義する (D-2 の定義の文。要求が保持するすべての接続)。観測値は「要求が使う pool の `execute_count` の差 + transaction / savepoint を**開いた**回数 (enter 側だけ) − checkout の維持の文の回数」とする (§11.6 N-3)。`txn_count` は enter と exit を分けず、transaction を終える COMMIT / ROLLBACK / RELEASE と `commit()`・`rollback()` も数えるので使わない (v0.6 の定義を改めた)。enter 側だけを数える計数は現物に無いので、足す場所 (両 peer の `psycopg_counting.py` か plug 側) は port v1.22 の設計で決める。positive control で PostgreSQL の 4 plug について「放した後の文の数 >= 1」を assert する。in-process の 2 plug は 0 ではなく None (観測不能) を返し、test は None のとき code だけを見る。`execute_count` は pool 維持の文 (r2db の checkout ごとの `SELECT 1`、新規接続の `SET search_path`) も数えるので、それを除く手段は port の設計で決める。候補: 計数 cursor が文の本文を記録して pool 維持の文を除く / 計測前に pool を warm にして新規接続を無くす。いずれも製品コードに test 用 hook を足さない (X-7) 形に限る。既存の 2 primitive の handle にも同じ値を持たせる (U-5 の裁定: 3 vector とも文の数で観測する)。
- 既存 handle は文の数を持たない: `IdempotencyHold` (`conformance-tests/adapter.py:997-1022`) と `PlanVerificationHold` (`:1026-1049`) は `wait_until_held(timeout_s=30.0) -> int` だけを持ち、4 つの実装すべてで戻り値は定数 1。stall 点より前に拒否されると `wait_until_held` は timeout (30 s) まで待って `AssertionError` を上げる (「届かなければ赤」は成り立つが 30 s 掛かる)。新条件の test は「held」か「要求の完了」のどちらかを待ち、完了が先なら即座に赤にする (§11.5 RW-17)。
- 既存 2 primitive の docstring: 放した後の約束は `hold_after_idempotency_lookup` だけにある (`conformance-tests/adapter.py:1902`:「`with` を抜けると先着は解放され、実行・記録・commit まで進む。」)。`hold_after_plan_verification` (`:1966`) は「`with` を抜けると先着は解放される。」だけで、2 件目について「先着が解放されて commit した後にはじめて答えを返すか、または先着が `PRECONDITION_FAILED` で拒否され何も実行しない」と書いており、先着の拒否を既に許す形である。従って port v1.22 で改訂する docstring は `hold_after_idempotency_lookup` の 1 文 (確定文の経路、運用条件 §1.5 の 35) で、`hold_after_plan_verification` は「先着が `LIMIT_EXCEEDED` で拒否される」場合を 2 件目の記述に足すかどうかを port の設計で決める。改訂する文の写しが `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md:374` と `docs/design/CONFORMANCE_ADAPTER_V1.md:3491` にあるので、両文書に【追記】を足す (§11.5 RW-15)。
- stall 点は plug で違う: (ii) で r2db の 2 実装 (`r2db-api/conformance/conformance_adapter_r2db.py:339-344`、`r2db-api/conformance/conformance_adapter_r2db_http.py:893-898`) は `_idempotency_reserve` の**入口** (予約を取る前) で止まり、MitateDB の 2 実装 (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:534-545`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:867-873`) は `_idempotency_check` が戻った後 (照会と予約の後) で止まる。port の docstring (`conformance-tests/adapter.py:1902`) は「予約を取り終え」と書いており、r2db の実装はこれと合わない。(iii) も、r2db in-process は `compute_plan_token` の後 (`r2db-api/conformance/conformance_adapter_r2db.py:410-414`)、r2db-http は `_read_schema_revision` の後 (`r2db-api/conformance/conformance_adapter_r2db_http.py:960-964`) で plan の照合より前、MitateDB は backend の DDL メソッドの入口 (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:612-616`) で plan 検査の後。
  - 監督裁定 (2026-10-02): 直す — port v1.22 の WP で、(ii)(iii) の stall 点の定義 (docstring) と 4 実装を一致させる。新条件の vector は「放した後に発行された文の数 = 0」を見るので、stall 点が plug で違うと「放した後の最初の文」が plug で違い、変異の対応が plug ごとにずれる。既存の C-27 と plan 検証のテストへの影響 (r2db では key lock を保持しているので 2 件目は待つ) は port の設計で確かめる。
  - 【改訂 2026-10-03 (v0.6、§11.5 RW-14)】 揃える先: (ii) は r2db の 2 実装を「予約の後」へ移す (docstring どおり。count lock は先に取られており C-27・C-34 は保たれる、とレビュー B が確認)。(iii) は docstring の点 (「revision の読みの後・DDL の前」) を 4 実装が既に満たすので変えない (上の「4 実装を一致させる」を (ii) だけに改める)。(iii) の positive control は自分の予算で plan を取り直し、dry run は hold を仕掛ける前に済ませる。
  - 【追記 2026-10-03 (v0.7、§11.6 N-3)】 (ii) の r2db の stall 点は「`_idempotency_reserve` が戻った後」(savepoint を解放した後) とする。
- plug ごとの観測:

| plug | backend | 文の数 | 新条件で見るもの |
|---|---|---|---|
| r2db in-process | in-memory `structured.ApplicationCell` (文が無い。`r2db-api/src/r2db_api/service.py:76-77` の `_default_cell_factory` と、adapter が cell_factory 無しで `DataService` を作る `r2db-api/conformance/conformance_adapter_r2db.py:469`) | None (観測不能。§11.5 RW-6。code と limit_class は単体テストで固定、§11.7 F-11 の (A)) | code・limit_class だけ |
| MitateDB in-process | SQLite (psycopg を通らない) | None (観測不能。§11.5 RW-6) | code・limit_class だけ |
| r2db-http / r2db-socket | PostgreSQL | `execute_count` | code・limit_class・文の数 |
| MitateDB-http / MitateDB-socket | PostgreSQL | `execute_count` | code・limit_class・文の数 |

- 義務 (a) (待ちを数え、受理点より遅く始めない) の証拠は conformance では取れない。証拠は `security/CONTROL_MAPPING.md` の claim と peer の単体テスト (r2db は clock 注入、MitateDB は test 側の `time.monotonic` 差し替え。D-9)。

### 6.5 書き換える既存の記述

- C-05 の Disclosed scope limits (1) の `execution_ms` を「never driven」から「新条件で駆動」を指す形に改める。`idempotency_retention_ms` の開示はそのまま。
- 同じ形に改める: C-24 の行 (`conformance-tests/CONDITIONS.md:53`) の「`execution_ms` is not driven at all」、`conformance-tests/test_c24_request_budget.py:40-41` の同文、`security/CONTROL_MAPPING.md:1141` の「never driven by this suite」。
- `security/CONTROL_MAPPING.md` の書き換え対象: `:659` (「per transaction」の記述。lock 待ち後の再設定と D-2 の検査に合わせる)、`:852` (引用の範囲を `backend_postgres.py:1687-1698` に直す。`:1687` は `_set_timeouts` の def、`SET LOCAL` の組み立てと実行は `:1695-1698`。実装 WP で行が動くので、そのときに取り直す)、`:870`、`:1023` (U-6 の接続確立の裁定に合わせ、V-3 の開示 (応答しない宛先は時間切れで `LIMIT_EXCEEDED` になり得る) を足す。§11.5 RW-5)。
- `security/CONTROL_MAPPING.md:905` の「unlike r2db-api's own data plane」は現物と合わない (r2db の `_DURABLE_DENIAL_CODES` は `LIMIT_EXCEEDED` を含まない。§1.3 #9)。書き換え対象に足す (内容は作業指示書で現物と照合してから直す。§11.5 RW-16)。
- CONDITIONS の行を変えるときは、`conformance-tests/CONDITIONS.md` 冒頭の Update convention どおり、現行行を書き換え、旧文を `conformance-tests/CONDITIONS_HISTORY.md` の該当 ID の節へ逐語で移す。

### 6.6 変異の対応の見込み (運用条件 §1.5 の 40。表は作業指示書で確定する)

| 変異 (両 peer) | (i) | (ii) | (iii) | peer の単体テスト (D-9) |
|---|---|---|---|---|
| D-2 (a) = `_timeout_ms` の拒否を外す (0 を返す)。r2db は入口検査をここへ移すので検査点は 1 つ。apply_schema も同じ | helper を置かない形では赤 (文の数で観測)。helper 案では生き残る (前後の検査が同じ code で拒否し、文の数も 0 のまま) | 届かない (検査が先にある) | 届かない | 赤 (閾値の単体テスト。helper 案ではこれが殺す) |
| helper 案 (D-9): helper の検査と transaction を開く前の検査を外す | 赤 (文の数で観測) | 作業指示書で確定 | 作業指示書で確定 | 作業指示書で確定 |
| D-2 (c) 文と文の間の検査を外す | — | 赤 | — | — |
| DDL 前の検査を外す | — | — | 赤 | — |
| 検査の閾値を `<= 0` に戻す | — | — | — | 赤 |
| D-2 (b) lock 待ちの後の検査を外す | — | — | — | 赤 |
| MitateDB schema 3 経路の順序を戻す (pre_commit の後に idempotency を書く。D-9) | — | — | — | 赤 |
| pool 待ち超過・接続確立の時間切れの写像を外す (U-6 の裁定) | — | — | — | 赤 |
| U-8 の裁定 (a) を戻す (最後の文の後の時計検査。`postgres.py:1554` 相当の検査を戻す) | — | — | — | 赤 (最後の文が完了した後に時計が期限を過ぎていても成功する) |
| SQLite backend の検査を外す | — | — | — | 赤 |
| MitateDB の `record_idempotency` の例外の翻訳を外す | — | — | — | 赤 |
| `SET LOCAL` / `_retime` の cancel の execution_ms への写像を外す | — | — | — | 赤 |
| 義務 (c) の文の bound を外す (PostgreSQL は `SET LOCAL` の値が残り以下、SQLite は遅い文の打ち切り) | — | — | — | 赤 |
| SQLite の progress handler を commit・rollback の間も有効にする (D-9) | — | — | — | 赤 (期限を過ぎた直後の commit が成功することを固定する) |

- in-process 2 plug では、単一の検査点の変異は後段の検査が同じ code で拒否するので観測できない。殺すのは PG plug の文の数と peer 単体テスト (§6.4 の表)。r2db の http・socket plug も、応答の code だけでは (ii)(iii) が修正前から緑になる (§12.4、U-5 (c))。
- v0.6 で足した行は §11.5 RW-9。変異の案は作業指示書で確定する (レビュー B の B-M1〜B-M6 を材料にする)。
- v0.7 で D-2 (a) の行を helper 案の有無で書き分け、helper 案の行と SQLite の handler の行を足した (§11.6 N-9・N-4)。

## 7. Security Invariants との関係

新しい不変条件は足さない (§2、`CLAUDE.md`)。

`security/THREAT_MODEL_V1.md` (:100-138) との関係: T-07 (資源枯渇。connections を含む) — execution_ms が pool・lock の待ちを含めて 1 要求の保持を bound する (D-1、D-5)。T-08 (エラーによる情報開示) — 新しい details を足さない (U-3 の裁定 (a)。`futility` は付けない)。T-09 (並行・部分失敗による不整合) — 打ち切られた要求が行・idempotency 記録を残さない (D-3、新条件 (ii)(iii))。T-14 (security evidence の欠落) — error 行の保証は現行のまま (r2db は backend の except 分岐、MitateDB は `_error_row_once_fired`)。変更なし。

| SI | 関係 |
|---|---|
| SI-08 | Verification 句の「deterministic rejection or termination」を execution_ms について初めて検証可能にする (新条件)。C-05 の文「over-bound requests terminate deterministically」の execution_ms の欠けを埋める。義務 (c) が 1 本の長い文を予算で縛る (V-1) |
| SI-11 | 打ち切りが部分状態を残さない。既存の atomic の検証に期限切れの vector が加わる (新条件の (ii)(iii)) |
| SI-10 | 変更なし。`futility` は付けない (U-3 の裁定 (a))。拒否の message に SQL・lock 名・pool の寸法を書かない点は現行のまま |
| SI-14 | `LIMIT_EXCEEDED` は耐久 denial ではない。変更なし。error 行の保証は T-14 の段のとおり現行のまま |
| SI-15 | 関係なし (認可の fail-closed ではない) |

## 8. 作業機で測る項目 (cloud では測らない)

| ID | 項目 | 効く先 | 結果 (2026-10-02) |
|---|---|---|---|
| M-1 | 1 ms 経路の再現 (両 peer): `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 の plugin 法 (`_set_timeouts` の記録) を r2db にも当て、§1.5 の各経路で `timeout_ms == 1` が出ることを修正前に記録する。MitateDB では 200 / 413 / 503 に分かれること、`SET` 自体が 1 ms で cancel され得るかも記録する | §1.5、D-2、D-9 | r2db は全経路で `timeout_ms == 1`、結果は負荷と run で揺れる。MitateDB は期限を過ぎた要求が成功する。503 と `SET LOCAL` の cancel は再現せず。§1.5、§12.1・§12.2 |
| M-2 | 作業機と配備の PostgreSQL の版。17 以上なら `transaction_timeout` の可否 | X-6、U-2 (c) | 作業機は 16.14 で `transaction_timeout` は無い。配備の版は未確認。§12.1 |
| M-3 | 文ごとの `SET LOCAL` 再設定の費用: `tools/perf_baseline.py --roundtrip` (台帳 R-80) で K=1 と K=32、6 plug | U-2 (b) | `SET LOCAL` 1 往復 p50 11 µs、要求あたりの文は 3〜15。U-2 (b) の費用は見積もり。§12.1・§12.5 |
| M-4 | 検証用 DB で COMMIT 自体を遅くする構成 (deferred constraint trigger に `pg_sleep` を置く等) で、`statement_timeout` が COMMIT を cancel したとき transaction が commit 済みになり得るかを PostgreSQL の文書と実測で確かめる | D-3 の commit 段、§9.1 の【保留】、U-6 | `statement_timeout` は COMMIT の仕事 (deferred trigger を含む) を打ち切らない。競合窓でも cancel 0 件。commit 段の【保留】と U-6 の commit 段を削った。§12.1 |
| M-5 | 台帳 R-102 後の MitateDB の advisory lock 待ちと pool 待ちの分布 (台帳 R-78 の値は cell lock 廃止前)。既定 5000 ms に対する余裕の確認 | D-1、U-1 | 32 並列で MitateDB の pool・lock の待ちは 0、r2db の pool 待ちは最大 3.4 ms。§12.5 |
| M-6 | advisory lock の `lock_timeout` 超過の SQLSTATE (55P03 `lock_not_available` か 57014 `query_canceled` か)。両 peer は両方を捕まえているが、記録として 1 回確かめる | §1.3 の 8、§1.4 の 4 | 同値の設定では 57014 (90/90)、`lock_timeout` 単独なら 55P03。D-5、§12.1 |
| M-7 | 受信から受理点までの時間 (認証・body 解析) の実測 | U-1 (a) と (b) の差 | 逐次で r2db 約 0.5 ms・MitateDB 約 5 ms、32 並列で p50 53〜78 ms。§12.3 |
| M-8 | 新条件の駆動の確認。(i): `budget.execution_ms = 1`、保持 100 ms で、完了ゲートの負荷の下でも 6 plug すべてで拒否が 100/100 になること。(ii)(iii): 完了ゲートの負荷の下で受理点から stall 点到達までの時間と、(iii) の plan を得る dry run が B の下で完了する時間を 6 plug で測り、B を決める (余裕は B/5 の形)。その B で、stall 点到達と拒否が 6 plug すべてで 100/100 になること。positive control も同じ回数 | D-7 の B と単調性の実証 | 修正前に測れる分は実測済み (§12.4)。100/100、vector (i)、完了ゲートの負荷の下の B は conformance の WP の完了条件 |

## 9. 契約文言の候補 (**依頼者確定 2026-10-03。逐語は §10 の末尾。版の番号は v0.10 の版数行のとおり読み替える**)

**以下は依頼者裁定 (§10) と設計レビュー 2 回目を反映した候補である。依頼者が確定するまで逐語 pin を置かない** (運用条件 §1.5 の 35)。確定は再確認の後に求める。 v0.4 までの `[U-N (x)]` の差し替え案は裁定で不要になったので落とした (v0.4 は main `23559b8`)。

v0.6 との差は §11.6 の N-1・N-2・N-5・N-8・N-10・N-11・N-12。

### 9.1 `limits.execution_ms` (新 key)

> execution_ms is one request's own wall-clock budget. It applies to the requests limits.request_budget names for execution_ms -- a query, a single-entity or cross-entity mutation and a schema operation, dry runs included; whether or how execution_ms bounds any other request, audit_query included, is not defined in this version. The budget starts no later than the point at which the request has passed this deployment's request-rate and concurrency bounds and the execution_ms in force for it (limits.request_budget) is fixed; an implementation may start it earlier, never later. Everything between that point and the point at which the request begins to commit counts against it: waiting for a database connection, waiting for a lock and executing statements. Once every statement its work requires has completed, a request is not refused for execution_ms by a clock check, and a request that has begun to commit is neither refused nor terminated for execution_ms. Each request has its own budget: each page of a query is one request, and a dry run has a budget of its own, of the same execution_ms as the request it previews, because it executes statements as well. A dry run and the real request issue different statements, so neither one's success nor its execution_ms refusal predicts the other's.

> A statement here is any one the implementation sends to its storage on behalf of the request, on any connection it holds for the request, including the statement that begins each of the request's transactions or savepoints, the statements that set its per-statement bound, and those that read the catalog, take locks, read or write idempotency records, or read or change the request's own data or schema. A statement that ends a transaction or savepoint and a statement that maintains a connection pool are not statements in this sense, nor is audit evidence recorded on a separate connection; where the implementation's storage takes no statements, each storage operation it performs for the request counts as one statement for refusing the request before its next one, and the per-statement bound concerns only statements its storage takes. A request whose execution_ms is exhausted is refused with LIMIT_EXCEEDED and details.limit_class: execution_ms before it issues its next statement. A remaining budget shorter than one millisecond is exhausted. A request whose execution_ms is exhausted while it waits for a database connection, or while one is being established for it, is refused in the same way. On each connection it holds for the request, a request sets its per-statement bound before any statement there other than the one that begins its transaction there and those that set the bound, and every statement it issues there after that runs under the most recent bound set there, which is no longer than what remained of execution_ms when the implementation computed it; a statement that reaches its bound is terminated and the request refused in the same way, while a statement still executing when execution_ms is exhausted may instead complete within its bound, after which the request is refused before its next statement or, if it needs none, proceeds to commit. A request refused or terminated this way has committed nothing of the atomic unit it was executing: that unit leaves no row, no catalog entry, no schema revision and no idempotency record. That list does not govern audit evidence: transactions.atomic and structured_operations.dry_run.external_effects are unchanged. What an earlier request with the same idempotency_key left is governed by structured_operations.idempotency.record, whose digest includes the request's budget field. A request can end later than its execution_ms: a statement already executing runs until it completes or its own bound terminates it, establishing a database connection can outlast what remained, and maintaining the connection pool, recording audit evidence before the commit and the commit itself are not bounded by it.

- 【v0.4 で削除】commit 段の文は置かない (M-4: 予算は commit を打ち切らない)。

### 9.2 `versioning.version_binding` に足す段落

> Only an implementation declaring 1.15.0 or higher additionally claims conformance to the obligations 1.15.0 introduces (subordinate ruling 20). Those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.15.0, independent of any capability's own status -- and each concerns only the requests limits.execution_ms names (a query, a single-entity or cross-entity mutation and a schema operation, dry runs included): (a) execution_ms counts every wait and every statement of such a request from no later than the point limits.execution_ms names until the request begins to commit; (b) such a request whose execution_ms is exhausted is refused with LIMIT_EXCEEDED and details.limit_class: execution_ms before it issues its next statement, and is not refused for execution_ms by a clock check once every statement its work requires has completed; (c) such a request, on each connection it holds for the request, sets its per-statement bound before any statement there other than the one that begins its transaction there and those that set the bound, every statement it issues there after that runs under the most recent bound set there, which is no longer than what remained of execution_ms when the implementation computed it, and a statement that reaches its bound is terminated; and (d) such a request refused or terminated for exhausting execution_ms has committed nothing of the atomic unit it was executing, and that unit leaves no row, no catalog entry, no schema revision and no idempotency record. limits.execution_ms states these four in full, with the terms they use; the sentence 1.15.0 adds to structured_operations.dry_run.decision holds an implementation to no behavior beyond them. 1.15.0 changes no request shape: a request valid under 1.14.0 stays valid, and the only request 1.15.0 newly requires an implementation to refuse is one whose execution_ms is exhausted -- a request that was never guaranteed to succeed under 1.14.0. 1.7.0's obligation (3) -- that a dry run receives the decision the identical request without it would receive -- does not extend to execution_ms in either direction, because a dry run and the real request issue different statements: neither one's success nor its execution_ms refusal predicts the other's. An implementation still declaring 1.14.0 is not held to any 1.15.0-only obligation retroactively.

### 9.3 `versioning.obligations[]` に足す entry

```json
{
  "version": "1.15.0",
  "subordinate_ruling": 20,
  "unconditional": [
    "execution_ms_counts_waits_until_commit",
    "exhausted_execution_ms_refused_before_next_statement",
    "statements_run_under_per_statement_bound",
    "execution_ms_refusal_commits_nothing"
  ],
  "conditional": []
}
```

散文 (§9.2) の無条件義務は four、entry は 4 件。

### 9.4 `structured_operations.dry_run.decision` に足す文 (末尾追記)

> Of the limit refusals named above, an execution_ms refusal is the exception: a dry run and the real request issue different statements, so neither one's success nor its execution_ms refusal predicts the other's (limits.execution_ms).

## 10. 依頼者裁定

依頼者裁定 2026-10-02 (設計 v0.4 の §5 に対して。監督が選択式で尋ね、依頼者が選んだ。問いと選ばれた選択肢の文は逐語。選択肢の「(Recommended)」は監督の推奨の印)。

| U | 問い (逐語) | 依頼者の選択 (逐語) | 選ばれた選択肢の説明 (監督が提示した文、逐語) |
|---|---|---|---|
| U-1 | execution_ms の計測の始点と、待ち (pool・lock) の算入はどれにしますか? | (a) 受理点から (Recommended) | rate・concurrency の gate を通り bound が確定した時点から、pool・lock の待ちと文の実行をすべて数える。両 peer の現行の計算点のまま。受理点の前 (認証・body 解析・worker の順番待ち) は数えない: 実測で逐次 0.5 ms / 5 ms、32 並列で p50 53〜78 ms。契約は「遅くとも受理点」とし、実装がより早く数え始めることは許す。 |
| U-2 | 文の途中で期限が来たときの上限 (文の実行区間) はどの形にしますか? | (a) 現行 + 文の間の検査 (Recommended) | 文の bound は scope 入口 (と lock 待ちの後) で設定し、文と文の間は process 内の時計で検査する。DB の往復を足さない。文の実行区間の合計は「残りの 2 倍未満」。 |
| U-3 | 再送してよいかを利用者にどう伝えますか? | (a) 保証だけ (Recommended) | 「execution_ms で拒否・打ち切られた要求は commit しておらず、何も残していない」という保証だけを契約に書く。再送は常に安全。details に新しい情報は足さない。 |
| U-4 | 契約の版はどうしますか? | (a) minor 1.15.0 (Recommended) | subordinate ruling 20 と obligations entry を足す。未定義だった意味を埋める変更で、1.11.0・1.12.0 と同じ扱い。1.7.0 の義務 (3) (dry run の拒否は real と同じ) が execution_ms には及ばないことを明記する。 |
| U-5 (範囲) | 新条件の conformance はどこまで入れますか? | (a) (i)〜(iii) を全部 (Recommended) | port v1.22 の新 primitive (受理点の後・最初の接続取得の前で止める) を足し、(i) 入口、(ii) 文の間、(iii) DDL の前の 3 vector を 6 plug で固定する。(i) が台帳 R-42 の候補そのもの。 |
| U-5 (観測) | 「次の文を発行しなかった」をどう観測しますか? | 文の数を返す (Recommended) | primitive の handle が「放した後に要求のために発行された文の数」を返す (PostgreSQL の 4 plug)。実測では、応答の code だけだと r2db の 3 plug と SQLite plug が修正前から緑になり、検査点を外す変異が常に生き残る。 |
| U-6 (pool 待ち) | 接続 pool の待ちが予算を超えたときの code は? | (a) 両 peer とも LIMIT_EXCEEDED (Recommended) | execution_ms の超過として返す。MitateDB は現行どおり、r2db は現行の 503 から変える (pool 取得に期限の残りを渡す)。U-1 (a) で待ちを予算に数えることと揃う。 |
| U-6 (接続確立) | 新しい DB 接続の確立が予算を超えて時間切れになったときの code は? | (a) 予算由来の超過は LIMIT_EXCEEDED | connect の時間切れが予算の残りによるものなら execution_ms の超過として返す。DB に到達できない障害 (拒否・到達不能) は SERVICE_UNAVAILABLE のまま。設計は U-6 のこの行に推奨を付けていませんが、pool 待ちを (a) にするなら揃う側です。 |
| U-7 | 「予算を使い切った」と判定する閾値は? | (a) 残り < 1 ms (Recommended) | 整数 ms で 0 なら拒否する。statement_timeout の分解能は 1 ms で、0 は「無効」を意味するので、1 ms 未満の残りで文を発行する手段が無い。 |
| U-8 | 最後の文が完了した後に、時計で検査して拒否しますか? (どちらでも commit 自体は予算で打ち切られません) | (a) 検査しない (Recommended) | 結果は最後の文の完了で決まり、その後は commit へ進む。完了した仕事を捨てない。r2db は現行の SELECT 後の検査を外す。実測では、現行の r2db は仕事が終わっているのに 413 になる回が負荷で変わる (200 21/50・413 29/50)。 |
| U-9 | 契約の execution_ms の文はどこに置きますか? | (a) limits の新 key (Recommended) | limits.execution_ms を新設する。1.8.0 の裁定「limits に新しい sibling key を置かない」を pin しているテスト (_PRE_1_8_0_LIMITS_KEYS) の切り直しが要り、この選択がその確認を兼ねます。 |

### 追加の裁定 (2026-10-03)

依頼者裁定 2026-10-03 (設計レビュー 2 回目の指摘のうち、契約の義務と裁定済みの文面に関わる 3 点。監督が選択式で尋ね、依頼者が選んだ。問いと選ばれた選択肢の文は逐語)。

| # | 問い (逐語) | 依頼者の選択 (逐語) | 選ばれた選択肢の説明 (監督が提示した文、逐語) |
|---|---|---|---|
| V-1 | レビュー A・B 共通の指摘: 契約文候補は「1.15.0 の義務は 3 件だけ」と書く一方で、「実行中の文は文ごとの bound で打ち切られる」とも述べており、打ち切りが義務かどうかが割れます。どうしますか? | 4 件目の義務にする (Recommended) | 「予算が尽きた時に実行中の文は、設定時の残りから算出した文ごとの bound で打ち切る」を義務 (d) に足す。1 本の長い文が予算に縛られない実装を 1.15.0 適合と読めなくする (SI-08)。追加の作業: MitateDB の SQLite backend に文の bound を入れる (現状は無い)、peer の単体テストで固定する。 |
| V-2 | レビュー B の指摘: execution_ms が掛かる「要求」の範囲が未定です (r2db の catalog 読みは期限を計算せず、MitateDB は計算する)。新しい文の範囲はどうしますか? | query・mutation・schema 操作 (Recommended) | 既存の limits.request_budget が execution_ms の適用先として挙げる 3 種 (query、単一 / cross-entity の mutation、schema 操作) に限る。catalog 読みなど他の要求を実装がどう bound するかはこの版では定めない。契約の既存の範囲と揃い、r2db の catalog 経路の変更は要らない。 |
| V-3 | U-6 (接続確立) の裁定の実現方法: 応答しない宛先 (blackhole) は connect の時間切れとして現れ、その時点で予算はほぼ尽きています。判定をどうしますか? | 時計の判定 1 本 + 開示 (Recommended) | 原因を問わず、接続の取得が失敗した時点で予算が尽きていれば LIMIT_EXCEEDED、尽きていなければ SERVICE_UNAVAILABLE。即時の拒否 (接続拒否) は 503 のまま。応答しない宛先は時間切れで 413 になり得ることを設計と CONTROL_MAPPING に開示する。どちらの code でも何も残らず再送は安全。実装が単純で peer で揃う。 |

未確定のまま残るもの: 契約文 (設計 §9) の確定。依頼者が確定するまで逐語 pin を置かない (運用条件 §1.5 の 35)。設計レビュー 2 回目の後に、裁定を反映した 1 本の文として依頼者に提示する。【追記 2026-10-03 (v0.6)】 提示は v0.6 の再確認の後に行う。

### 契約文の確定 (2026-10-03)

監督が選択式で尋ね、依頼者が選んだ (問いと選択の文は逐語)。

| 問い (逐語) | 依頼者の選択 (逐語) | 選ばれた選択肢の説明 (監督が提示した文、逐語) |
|---|---|---|
| 契約文の候補 (設計 v0.9 §9.1〜§9.4、main fb9c32f) を確定してよいですか? 確定後はこの文を逐語で契約 1.15.0 に入れ、pin のテストを置きます。 | 確定する | §9.1 (limits.execution_ms)、§9.2 (version_binding の 1.15.0 の段落、4 義務)、§9.3 (obligations[] の entry)、§9.4 (dry_run.decision への追記) をこのまま確定。上の差 2 点も了承。 |

「上の差 2 点」= 提示時に監督が明示した、依頼者裁定の説明文と確定文の差: (1) V-1 の説明文「予算が尽きた時に実行中の文は…打ち切る」に対し、確定文の (c) は「接続ごとに、BEGIN と bound の設定より前に bound を設定し、以後の各文は算出時の残りを超えない bound の下で走る。bound に届いた文は打ち切る」(U-2 (a) では尽きた時点で実行中の文は bound に届く前に完了し得る)。(2) U-2 (a) の説明文「scope 入口 (と lock 待ちの後) で設定」に対し、r2db は lock 待ちの後に再設定しない (時計の再検査だけ。§11.5 RW-10)。

確定文は scratchpad の確定文ファイルから契約へ逐語で複製し (運用条件 §1.5 の 35)、版の番号 (1.15.0 → 1.16.0、ruling 20 → 21、1.14.0 → 1.15.0) だけを契約 WP で置き換える (v0.10 の版数行)。

## 11. 設計レビュー

### 11.1 1 回目 (2026-10-02)

レビュー A 9 件・B 15 件を監督が 19 件に統合し、採否を決めた。

| # | 元 | 採否 | 反映先 |
|---|---|---|---|
| RV-1 | A-1, B-F2 | 直す (起票 1 件を D-9 に添える) | D-2 (d)、D-3、§1.4 #7・#8、D-9 |
| RV-2 | A-2, B-F3 | 直す | D-3、§9.1 (列挙と【保留】)、§9.2 の (c) |
| RV-3 | B-F1 | 直す | D-2、D-9、§6.6 |
| RV-4 | A-3, B-F7 | 直す | D-7、§6.2、§6.3、M-8 |
| RV-5 | A-4, B-F13 | 依頼者判断 | U-8、D-2、D-9、§9.1・§9.2・§9.3 の [U-8] |
| RV-6 | A-5, B-F11 | 直す | D-5、§1.4 #2、U-6 |
| RV-7 | A-6 | 直す | D-2、§9.1、§6.4 |
| RV-8 | A-7, B-F5 | 直す | §6.4、§6.6、D-9、U-5 (c) |
| RV-9 | A-8, B-F14 | 直す | §9.1、§9.2、§9.3、§6.2 の註 |
| RV-10 | A-9 | 直す | D-2、U-7 (c)、X-2 |
| RV-11 | B-F4 | 直す | D-1、§9.1 |
| RV-12 | B-F6 | 直す | D-7、§6.4、D-9 |
| RV-13 | B-F8 | 直す | §6.4 |
| RV-14 | B-F9 | 直す + 依頼者判断 | U-9、D-6、§9 (旧 idempotency.record の挿入案を削除、§9.2 の「rewrites」) |
| RV-15 | B-F10 | 直す | §1.4 #3・#5、§1.5、M-1、D-9 |
| RV-16 | B-F12 | 直す | U-3 (推奨を (a) へ)、D-4、§7 SI-10 |
| RV-17 | B-F14 残り | 直す (RV-9 に含む) | RV-9 と同じ |
| RV-18 | B-F15 | 直す | §6.1、§6.5、§6.6 の見出し |
| RV-19 | B の照合 | 直す | §1.2、§1.3、§1.4、§1.7、§6.1 (照合済みの印を外し、行番号を訂正) |

### 11.2 再確認 (2026-10-02、担当観点: 指定なし)

12 件と観察 1 件。全件「直す」。

| # | 元 | 採否 | 反映先 |
|---|---|---|---|
| RC-1 | F1 | 直す | D-9 (MitateDB schema 3 経路の並べ替え)、§1.4 #7、§6.6 |
| RC-2 | F2 | 直す | U-8、D-2 の (d) と §6.6 の (d) の行に [U-8 (b)]、§9.1・§9.2 の [U-8 (a)] |
| RC-3 | F3 | 直す | D-2 (a)、§6.6 (i) 列の統合と脚注 |
| RC-4 | F4 | 直す | D-2 の「文」の定義、D-7 の観測、§6.4、§9.1 |
| RC-5 | F5 | 直す | §9.2 (1.7.0 (3) の 1 文)、§9.4 (新)、D-6、U-4 (b) |
| RC-6 | F6 | 直す | §9.1、D-3 |
| RC-7 | F7 | 直す | U-9 (b)(c)、D-6 |
| RC-8 | F8 | 直す | §9.2 の [U-9 (b)/(c)] |
| RC-9 | F9 | 直す | M-4 |
| RC-10 | F10 | 直す | D-2 (d)、D-5 (COMMIT の bound) |
| RC-11 | F11 | 直す | §6.5、§6.1 |
| RC-12 | F12 | 直す | §7 (THREAT_MODEL の段落) |
| RC-13 | 観察 | 直す | §1.4 #4、§6.1・§6.5 の印 |

- RV-14 の採否表にあった pin の記述 (U-9 (b) は「pin はそのまま」、(c) は「切り直す」) は逆だった (監督の事実誤認)。再確認 (RC-7) で正した。

2 回目は依頼者裁定の反映後に行う。

### 11.3 作業機の照合と実測 (2026-10-02)

照合は worktree r42 (設計が引く約 60 の file:line のうち約 50 が一致。食い違い 6 件、行番号ずれ 5 件)。v0.3 の「基点で未照合」の印 12 か所は、一致したものは印だけ外し、食い違い・ずれは訂正後の内容に直した。

| # | 元 | 反映先 |
|---|---|---|
| W-1 | M-4: `statement_timeout` は COMMIT を打ち切らない | D-1、D-2、D-3、D-5、D-9、U-6、U-8、§9.1〜§9.3、§12.1 |
| W-2 | M-6: 同値の 2 つの timeout では lock 待ちの超過は 57014 | D-5、§1.3 #6、§12.1 |
| W-3 | M-2: 作業機 16.14、`transaction_timeout` 無し | §1.6、X-6、U-2 (c)、§12.1 |
| W-4 | M-1 (PostgreSQL 単体): 1 ms の下の軽い文は cancel されず、1 ms を超える文は 1.04〜1.37 ms で cancel | §1.5、U-7 (c)、§12.1 |
| W-5 | M-3 micro: `SET LOCAL` 1 往復 p50 11 µs | U-2 (b)、§12.1 |
| W-6 | 照合: MitateDB schema 操作の `commit_failed` の欠けは存在しない (`_error_row_once_fired`。台帳 v1.151 の R-42 行) | §1.4 #7・#8、D-3、D-9、§7、§8 M-4 |
| W-7 | 照合 (内容 1): 放した後の約束は `hold_after_idempotency_lookup` の docstring だけ | §6.4 |
| W-8 | 照合 (内容 2): r2db in-process が in-memory である出所 | §6.4 の表 |
| W-9 | 照合 (内容 3): `security/CONTROL_MAPPING.md:852` の引用は古くない (範囲が 2 行短い) | §6.5 |
| W-10 | 照合 (内容 4): `security/CONTROL_MAPPING.md:1023` は現物と合う | §6.1、§6.5、U-6 |
| W-11 | 照合 (内容 5): schema 3 経路と行の `delete` の区別 | §1.4 #7、D-9 |
| W-12 | 照合 (内容 6): `commit_failed` の誤りが残る行 (v0.2 の版数行は記録として残す) | §1.4 #7・#8、D-3、D-9、§7 |
| W-13 | 照合 (行番号 5 件): `postgres.py:2416-2420`、`audit_dispatch.py:32-68`、`pool.py:384`/`:386`、`pool.py:467-477`、`test_contract.py:138-146` | §1.3 #9、§1.4 #2・#7、D-2、D-6、U-9 |
| W-14 | 照合 (確かめられた事実): §1.4 #8 の経路、単一行の経路、§1.3 #4・#9、`SET LOCAL` の cancel の peer 差、`PIN_1_7_0_DRY_RUN_DECISION`、`docs/design/CONFORMANCE_ADAPTER_V1.md` §25 の導入、socket plug の subclass | §1.3、§1.4、§1.5、D-6、§6.1 |
| W-15 | M-8 (修正前): MitateDB の PostgreSQL 2 plug は予算を過ぎた要求を commit する。他 4 plug は応答の code では修正前から緑 | §1.5、D-9、U-5 (c)、§6.6、§8、§12.4 |
| W-16 | M-8: B の初期値の候補 500 ms (保持 600 ms) | D-7、§6.3 |
| W-17 | M-8: (iii) の dry run は実要求と同じ budget を付ける | D-7、§6.3 |
| W-18 | M-8: handle は文の数を持たず、`wait_until_held` は 30 s で赤 | D-7、§6.4 |
| W-19 | M-8: stall は両 socket plug でも効く | §6.1 |
| W-20 | M-8: stall 点が plug で違う (監督裁定 2026-10-02: port v1.22 で揃える) | D-7、§6.4 |
| W-21 | M-1 (peer 経由) | §1.5、D-2、U-8、§8、§12.2 |
| W-22 | M-7 | D-1、U-1、§12.3 |
| W-23 | M-3 (perf_baseline の文の数) | U-2 (b)、§12.5 |
| W-24 | M-5 | D-1、§1.6、§12.5 |

### 11.4 依頼者裁定の反映 (2026-10-02、v0.5)

| # | 裁定 | 反映先 |
|---|---|---|
| J-1 | U-1 (a) 受理点から | §5 U-1、D-1、X-3・X-4 |
| J-2 | U-2 (a) 現行 + 文の間の検査 | §5 U-2、D-5 |
| J-3 | U-3 (a) 保証だけ | §5 U-3、D-4 |
| J-4 | U-4 (a) minor 1.15.0 | §5 U-4、D-6、§9.2〜§9.4 |
| J-5 | U-5 (範囲) (a) (i)〜(iii) を全部 | §5 U-5、D-7 |
| J-6 | U-5 (観測) 文の数を返す | §5 U-5、D-7、§6.4 |
| J-7 | U-6 (pool 待ち) (a) 両 peer とも LIMIT_EXCEEDED | §5 U-6、D-9、§6.6、§9.1 |
| J-8 | U-6 (接続確立) (a) 予算由来の超過は LIMIT_EXCEEDED | §5 U-6、D-5、D-9、§6.6、§9.1 |
| J-9 | U-7 (a) 残り < 1 ms | §5 U-7、D-2 |
| J-10 | U-8 (a) 検査しない | §5 U-8、D-2、D-9、§6.6、§9.1、§9.2 |
| J-11 | U-9 (a) limits の新 key | §5 U-9、D-6、§9.1、§9.2、§9.4 |

2 回目の設計レビューは本版 (v0.5) に対して行う。

### 11.5 2 回目 (2026-10-03。1 巡目: 担当観点 A / B の並列)

レビュー A 9 件 + 観察 1 件・B 14 件を監督が 19 件に統合し、採否を決めた。依頼者裁定は §10 の追加の裁定 (V-1〜V-3)。

| # | 元 | 採否 | 反映 |
|---|---|---|---|
| RW-1 | A2-1、B-1 (§9.2 の「no behavior beyond these three」が §9.1 の振る舞いの文を義務の外に出す。(a) に終点が無い) | 直す (依頼者裁定 V-1) | 義務を 4 件にする (文の打ち切りを足す)。(a) に終点 (commit の開始) を入れる。§9.2 の「What else」の句は、`structured_operations.dry_run.decision` に足す文だけを指す形にする。§9.1〜§9.3 (下の §3)。D-5 に「文の bound は契約の義務 (V-1)。SQLite backend に文の bound を入れる (D-9)」。V-1 の逐語の「義務 (d)」は §9.2 の (c) にあたる (§11.6 N-12) |
| RW-2 | B-2 (execution_ms が掛かる要求の範囲が未定。r2db の catalog GET は期限を計算しない。SQLite に文の bound が無い) | 直す (依頼者裁定 V-2・V-1) | §9.1 の冒頭に範囲の文。D-1 に範囲 (query・mutation・schema 操作と、その dry run。catalog 読みなど他の要求はこの版では定めない。r2db の catalog 経路は変えない)。D-9 の MitateDB に「SQLite backend に文の bound (例: `sqlite3` の progress handler で期限を見て打ち切る。手段は実装の自由、DB 往復は無い)」、r2db の in-memory backend は文が無いので (c) の義務は空 (発行する文が無い) と明記 |
| RW-3 | A2-2、B-12 (1.7.0 (3) の狭め方が片方向。§9.4 の「the exception」の先行詞が曖昧) | 直す | §9.1・§9.2・§9.4 の dry run の文を両方向にする (下の §3)。D-1 の dry run の文も両方向に |
| RW-4 | A2-3 (冒頭の「bounds one request's own wall-clock time」は約束しすぎ) | 直す | 冒頭を「wall-clock budget」にし、要求が予算より遅く終わり得ること (実行中の文、接続の確立、commit) を 1 文で開示する (下の §3)。D-5 にも同じ開示 |
| RW-5 | A2-4、B-7 (接続確立の時計判定と「到達不能は SERVICE_UNAVAILABLE」の食い違い) | 直す (依頼者裁定 V-3) | D-5 の接続の確立の項を V-3 の規則 1 本に書き直し、blackhole の開示を足す。§6.5 の `security/CONTROL_MAPPING.md:1023` の項に「開示を足す」。U-6 の接続確立の行に【依頼者裁定 2026-10-03 (V-3)】 |
| RW-6 | A2-5、B-5 (文の数の観測: BEGIN / SAVEPOINT は `txn_count` 側、r2db の checkout ごとの `SELECT 1` は数えられる、MitateDB の ping は数えられない、in-process の定数 0 は空振り) | 直す | §6.4: 観測値は「要求が使う pool の計数の差 (`execute_count` と transaction を開く境界 = `txn_count` の両方) から、checkout の維持の文の回数を引いた値」。positive control で PostgreSQL の 4 plug について「放した後の文の数 >= 1」を assert する。in-process の 2 plug は 0 ではなく None (観測不能) を返し、test は None のとき code だけを見る。D-7 の観測の段と §6.3 の表にも |
| RW-7 | B-3 (版の切り替えの順序と新条件の version gate) | 直す | D-6 に: 契約の版の切り替え (`spec/` の 1.15.0、生成される `OPERATION_CATALOG.json`、両 peer の契約の同梱コピー、両 peer の振る舞い、新条件) は 1 commit で main に入れる (1.11.0 の `e21922a` と同じ形。C-29 が catalog と capability document の版の一致を assert するため)。WP は統合 branch の上で分けて作り、main へは 1 つの変更セットで入れる。D-7 に: 新条件は 1.15.0 以上を宣言する plug に束縛し (version gate)、登録された全 plug が束縛されることを assert する非空振りの guard を置く |
| RW-8 | B-4 (pin と記録の計画の漏れ) | 直す | D-6 に列挙: 壊れる pin = `test_contract_declares_1_14_0` (`conformance-tests/test_contract.py:78-91`)、`_PRE_1_8_0_LIMITS_KEYS` (:138-146、照合 :180-184)、`test_contract_pins_the_1_14_0_version_binding_paragraph_verbatim` (:1555-1568。等値照合の右端を 1.15.0 の段落の開始へ)、:1572 の docstring。更新対象 = `spec/CONTRACT_HISTORY.md` の version_binding の引用 (`conformance-tests/test_contract_history_register.py:343` が全文一致を照合)、`spec/README.md` の版の段落、両 peer の "1.14.0" の pin (`r2db-api/tests/test_foundation.py:252` ほか、`MitateDB-api/tests/test_http.py:393`、`MitateDB-api/tests/test_control_plane_service.py:574`)。散文の義務の個数 (four) と `obligations[]` の entry の一致は `_UNCONDITIONAL_COUNT_RE` (`conformance-tests/test_operation_catalog_register.py:314`) では機械照合されないので、`obligations[12]` の index 固定の pin (`conformance-tests/test_contract.py:1582` の形) を置く |
| RW-9 | B-6 (殺し手の無い完了条件) | 直す | D-9 に「検査は文を発行する helper 1 か所に置く形を推奨する (r2db の `_run`、MitateDB は文を発行する共通の関数。1 つの変異で全点を覆える。pool の維持・COMMIT / ROLLBACK は helper を通らないので D-2 の定義と合う)。採否は作業指示書」。§6.6 に行を足す: U-8 の裁定 (a) を守る単体テスト (最後の文が完了した後に時計が期限を過ぎていても成功する。変異 = `postgres.py:1554` 相当の検査を戻す)、SQLite の検査と文の bound、MitateDB の `record_idempotency` の例外の翻訳、`SET LOCAL` / `_retime` の cancel の写像、義務 (c) の文の bound (PostgreSQL は `SET LOCAL` の値が残り以下、SQLite は遅い文の打ち切り)。変異の案は作業指示書で確定 (レビュー B の B-M1〜B-M6 を材料にする) |
| RW-10 | A2-7、B-10 (r2db の「lock 待ちの後の再設定」は往復を足す) | 直す | D-9 の r2db: lock 待ちの後は時計の再検査だけ (helper の検査が兼ねる)。bound の再設定はしない (往復を足さない。文の実行区間の「残りの 2 倍未満」は再設定が無くても成り立つ: 次の文は残りが尽きる前にしか始まらず、その文は入口の残りまでしか走れない)。MitateDB の `_retime` (実際に待った後だけ再設定) は現行のまま。D-5 の「lock 待ちの後に再設定」の句を peer ごとに書き分ける |
| RW-11 | A2-6 (義務 (c) の無条件化が 1 要求 = 1 transaction を前提にし、将来の best_effort を縛る) | 直す | 契約文の「何も残さない」を atomic unit に範囲付けする (下の §3)。D-3 に 1 文 (`transactions.interactive` のとおり v1 では atomic unit = 1 要求) |
| RW-12 | A2-9 (「never exceeds what remained ... when that bound was set」は字義どおりには偽) | 直す | 「computed from what remained of execution_ms immediately before it set that bound」(下の §3) |
| RW-13 | A2-8 (文の実行区間の外の列挙に pool 維持の ping が無い。r2db の新規接続の箇所がもう 1 つある) | 直す | D-5 の区間外の列挙に「pool の維持の文 (r2db の checkout ごとの `SELECT 1` `postgres.py:621`、MitateDB の idle ping `pool.py:369`。予算の外。MitateDB の ping には timeout が無い)」。D-9 の r2db に「新規接続の箇所は 2 つ (`postgres.py:655`・`:660` の差し替えを含む)。両方に残りを渡す」 |
| RW-14 | B-8 (stall 点を揃える先) | 直す | §6.4・D-7: (ii) は r2db の 2 実装を「予約の後」へ移す (docstring どおり。count lock は先に取られており C-27・C-34 は保たれる、とレビュー B が確認)。(iii) は docstring の点 (「revision の読みの後・DDL の前」) を 4 実装が既に満たすので変えない (v0.5 の「揃える」を (ii) だけに改める)。(iii) の positive control は自分の予算で plan を取り直し、dry run は hold を仕掛ける前に済ませる |
| RW-15 | B-9 (docstring の改訂文の写しが 2 文書にある) | 直す | §6.4 に: `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md:374` と `docs/design/CONFORMANCE_ADAPTER_V1.md:3491` の写しに【追記】を足す |
| RW-16 | B-11 (`security/CONTROL_MAPPING.md:905` の「unlike r2db-api's own data plane」が現物と合わない) | 直す | §6.5 の書き換え対象に足す (内容は作業指示書で現物と照合してから直す) |
| RW-17 | B-13 (stall 点に届かないときの赤が 30 s 待ち) | 直す | §6.4・D-7: test は「held」か「要求の完了」のどちらかを待ち、完了が先なら即座に赤にする |
| RW-18 | B-14 (文書規約: :257 の「D-6.2/§7.3」に文書名が無い。D-2 で「(d) は置かない」が重複) | 直す | 文書名を添える (フェーズ7 設計)。D-2 の重複を 1 行にまとめる |
| RW-19 | A の観察 (COMMIT に外部からの cancel が当たったときの code が peer と経路で違う。どの経路でも commit はしていない) | 観察 (起票しない) | 予算の外の原因で、D-3 の保証は成り立つ。DB の利用者は code の差に当たり得るが、運用者の cancel という稀な操作に限られ、状態は残らない。D-3 に事実として 1 文 (r2db は 413、MitateDB の transact・単一行は 503、schema 3 経路と delete は 413) |

再確認は本版 (v0.6) に対して 1 起動で行う。

### 11.6 2 回目の再確認 (2026-10-03、担当観点: 指定なし)

再確認の 12 件 (N-1〜N-12)。全件「直す」(監督裁定)。依頼者裁定は再審議しない。

| # | 要旨 | 採否 | 反映 |
|---|---|---|---|
| N-1 | 義務 (c) と §9.1 の打ち切りの文が U-2 (a) (bound は入口で 1 回) と字義で衝突する。実行中の文は bound (入口の残り) に届く前に完了し得る | 直す | §9.1・§9.2 を §9 の英文に。D-5 の 1 行目を「文の bound は入口の残りで 1 回設定し (lock 待ちの後の `_retime` は MitateDB のみ)、bound に届いた文は打ち切る。予算が尽きた時点で実行中の文は bound に届く前に完了し得て、その後は次の文の前で拒否されるか、次の文が無ければ commit に進む (U-8 (a))」に。V-1 の説明文 (「予算が尽きた時に実行中の文は…打ち切る」) と新しい (c) の文言の差は、契約文の確定を求めるときに監督が依頼者へ明示する |
| N-2 | (b) の「after its last statement has completed」が「次の文の前で拒否」と矛盾する (文 2 の後に拒否すると文 2 が最後の文) | 直す | 「once every statement its work requires has completed」(§9) |
| N-3 | RW-6 の観測の定義では正しい実装が偽の赤になる (`txn_count` は COMMIT / ROLLBACK / RELEASE と `rollback()` も数える) | 直す | §6.4・D-7: 観測値 = `execute_count` の差 + transaction / savepoint を**開いた**回数 (enter 側だけ) − checkout の維持の文の回数。enter 側だけを数える計数は現物に無いので、足す場所 (両 peer の `psycopg_counting.py` か plug 側) は port v1.22 の設計で決める。(ii) の r2db の stall 点は「`_idempotency_reserve` が戻った後」と明記 |
| N-4 | SQLite の progress handler を commit・rollback の間も有効にすると「commit を始めた要求は打ち切らない」に反し得る | 直す | D-9 の MitateDB (SQLite): handler は文の実行中だけ有効にし、commit・rollback の前に外す。§6.6 に単体テストの行 |
| N-5 | §9.1 の「can end later」の列挙が audit の pre_commit 書き込みと pool の維持を落としている | 直す | §9 の英文 |
| N-6 | D-6 の「1 commit で main に入れる」と「WP は統合 branch で分ける」が衝突する | 直す (監督裁定: (B)) | D-6: `spec/` の 1.15.0、生成 catalog 3 部、両 peer の同梱コピー、両 peer の版の flip、新条件と version gate の guard を、統合 branch 上の同じ 1 commit に入れる。振る舞いの WP (両 peer の検査・写像・port v1.22) はそれより前の commit で、版を動かさない (1.10.0 の `3af11b3` → `5d988c6` の形を踏襲し、flip の commit に spec も入れる)。中間 commit で C-29・guard が赤にならない |
| N-7 | in-memory では (b)(c) が空になるが、§6.3 は r2db in-process plug に `LIMIT_EXCEEDED` を求め、読みの後と loop の後の検査 (U-8 (b) の形) が残る | 直す | D-9 の r2db (in-memory `structured.py`): 1 operation を 1 文とみなし、各 operation の前で検査し、最後の operation の後の検査 (`structured.py:937-938`・`:1161-1162`) は外す。§6.4 の表の r2db in-process の行は「code・limit_class だけ (単体テストで固定)」のまま |
| N-8 | 「文」の定義が savepoint を決めていない。r2db の入れ子の `transaction()` は `_run` を通らない。「implicit begin」は r2db の明示の BEGIN と合わない | 直す | §9 の英文 (transaction / savepoint を開く文は含む、終える文は含まない)。D-2 の定義を同じに。D-9 の r2db: 入れ子の `transaction()` (`postgres.py:1261`・`:1317`・`:1419`・`:1435`) の前にも検査を置く |
| N-9 | helper 案では §6.6 の D-2 (a) の行 (`_timeout_ms` の拒否を外す変異) が (i) で生き残る | 直す | §6.6 の行を書き分ける: (i) を殺すのは「helper の検査と transaction を開く前の検査を外す」変異。`_timeout_ms` の拒否を外す変異は閾値の単体テストで殺す |
| N-10 | 識別子 `execution_ms_refusal_leaves_no_state` が D-3 の避けた「state」を持ち込む | 直す | `execution_ms_refusal_commits_nothing` (§9) |
| N-11 | 再送の判断で budget が digest に入ることへの手掛かりが無い | 直す | §9 の英文 (`structured_operations.idempotency.record` を指す句) |
| N-12 | 文書の整合 (V-1 の逐語は (d)、§9.2 では (c) / MitateDB の版の pin の漏れ / D-9 の新規接続の箇所 `postgres.py:436` / 「1.14.0 で valid な要求は valid のまま」の文) | 直す | §11.5 の RW-1 に 1 句。D-6 の pin の列挙に `MitateDB-api/tests/test_audit_query.py:1727`・`:1757`・`:1769`・`:3849`、`MitateDB-api/tests/test_denial_details_and_request_id.py:552`・`:566` と r2db 側の残りの行 (`r2db-api/tests/test_audit_query.py:1991`・`:4047`・`:4081`、`r2db-api/tests/test_control_plane_service.py:1808`、`r2db-api/tests/test_denial_details_and_request_id.py:514`)。D-9 の r2db の新規接続に `postgres.py:436` (`_acquire`)。§9 の英文 |

再々確認は §9 と N-1〜N-12 の閉じ方に限って 1 起動で行う。

### 11.7 2 回目の再々確認 (2026-10-03、§9 と N-1〜N-12 に限る)

14 件、全件「直す」(監督裁定)。N-1〜N-12 は 9 件が閉じ、N-6・N-7 の残りを F-12・F-11 で閉じた。

| # | 要旨 | 反映 |
|---|---|---|
| F-1 | 義務 (c) の「computed from what remained」が bound の大きさを縛らない | §9.1・§9.2: 「no longer than what remained of execution_ms when the implementation computed it」。残りより短い bound は禁じない (実装はより厳しくてよい) |
| F-2 | 「after it has set its bounds」のため bound を設定しない実装が (c) を空で満たす | §9.1・§9.2: 「sets its per-statement bound before any statement other than the one that begins its transaction and those that set the bound, and every statement it issues after that runs under the most recent such bound」 |
| F-3 | §9.2 の (a)〜(d) に範囲が無い | 前文に「each concerns the requests limits.execution_ms names, …」、各義務に「such a request」 |
| F-4 | 「This says nothing about audit evidence」が直前の文と衝突 | 「no idempotency record.」の直後へ移し「That list does not govern audit evidence: …」 |
| F-5 | 「what 1.15.0 newly requires is refusing …」が網羅に読める | 「the only request 1.15.0 newly requires an implementation to refuse is one whose execution_ms is exhausted」 |
| F-6 | 「rather than issuing that statement under a bound too short for it to complete」は U-2 (a) と合わない | 句を削った |
| F-7 | 「a dry run has the budget of the request it previews」が予算の共有に読める | 「a budget of its own, of the same execution_ms as the request it previews」 |
| F-8 | 範囲の文の語が曖昧 | 「the requests limits.request_budget names for execution_ms -- …」「whether or how execution_ms bounds any other request, audit_query included, is not defined」 |
| F-9 | 文の定義の英文 (「issues from the request's content」、行為と文の並置、(d) の「which」) | 定義を「sends to its storage on behalf of the request」の形に書き直し、(d) を「and that unit leaves …」に |
| F-10 | 設計の古い文言 (§5 U-2 の方針文、D-2 (a) の「最初の `SET LOCAL` の前」、D-6 の要約) | 直した |
| F-11 | in-memory backend は契約の意味での文を発行せず、§6.3 と guard が求める `LIMIT_EXCEEDED` の根拠が契約に無い | (A): 文の定義に「where the implementation's storage takes no statements, each storage operation it performs for the request counts as one」を足し、in-memory も (a)〜(d) に縛られる形にした。D-9 の in-memory の項 (1 operation = 1 文) はこれと合う |
| F-12 | D-6 (B) と契約の version-flip 文の関係 | D-6 に 1 文 (中間 commit は統合 branch 上にだけあり main には 1 つの merge で入る) |
| F-13 | U-2 の裁定の説明文「入口 (と lock 待ちの後) で設定」と、r2db が lock 待ちの後に再設定しないこと (RW-10) の差 | 契約文の確定を求めるときに V-1 の差と併せて明示する (本行が記録) |
| F-14 | 識別子の「admission」は契約に無い語 | `execution_ms_counts_waits_until_commit` |

範囲外の観察 (レビュー担当): `limit_enforcement.execution_ms` の値 `reference_wall_clock` は enum の値だけで契約に定義の文が無い。1.15.0 の無条件義務との関係は未確認 → 作業指示書の契約 WP で、1.15.0 の段落か `limit_enforcement` の説明に 1 文を足すかを確かめる。

### 11.8 §9 の最終確認 (2026-10-03、§9 に限る)

6 件、全件「直す」(監督裁定)。F-1〜F-14 のうち §9 に効くものは閉じた (F-9 と F-11 の残りは FC-1・FC-3)。

| # | 要旨 | 反映 |
|---|---|---|
| FC-1 | 文の定義の列挙にデータを読む文 (query の SELECT、revision の読み、plan の照合) が無く、閉じた列挙に読める | 「any one … including …」の形にし、「read or change the request's own data or schema」を入れた。audit は「nor is audit evidence recorded on a separate connection」。D-2 の定義も同じ範囲 |
| FC-2 | (c) の「its transaction」が単数で、「the most recent such bound」が接続を区別しない。MitateDB は 2 接続 (developer と runtime) で BEGIN → SET の順が接続ごとに繰り返されるので字義どおり満たせない | §9.1・§9.2 (c) を「On each connection it holds for the request, … before any statement there other than the one that begins its transaction there and those that set the bound, … under the most recent bound set there」に |
| FC-3 | F-11 (A) で in-memory の各操作が「文」になり、(c) が bound の設定と打ち切りを求めるが D-9 に手当てが無い | 監督裁定 (A'): 「counts as one statement for refusing the request before its next one, and the per-statement bound concerns only statements its storage takes」。in-memory は義務 (b) にだけ縛られ、D-9 の「義務 (c) は空」はそのまま |
| FC-4 | 「budget」が時間の予算と要求のフィールドの 2 義 | 「whose digest includes the request's budget field」 |
| FC-5 | §9.2 の同格の列挙が要求の種類をもう 1 つ並べたものに読める | 「each concerns only the requests limits.execution_ms names (a query, …, dry runs included):」 |
| FC-6 | 「the bound in force for it」がどの bound か決まらない | 「the execution_ms in force for it (limits.request_budget) is fixed」 |

## 12. 実測の記録 (2026-10-02、作業機。逐語)

### 12.1 PostgreSQL 単体 (M-2・M-4・M-6・M-1・M-3 micro)

throwaway cluster (`tools/testpg/dsa_testpg.py` の `cluster()`)、共有 suite lock、load average 2.5〜2.9。

```
M-2 version: PostgreSQL 16.14 (Homebrew) on aarch64-apple-darwin25.4.0, compiled by Apple clang version 21.0.0 (clang-2100.0.123.102), 64-bit
M-2 transaction_timeout GUC present: 0
M-6 lock_timeout only     : LockNotAvailable/55P03
M-6 statement_timeout only: QueryCanceled/57014
M-6 both = 50 ms (stmt set first) x30: {'QueryCanceled/57014': 30}
M-6 both = 50 ms (lock set first) x30: {'QueryCanceled/57014': 30}
M-6 both = 50 ms (one statement) x30: {'QueryCanceled/57014': 30}
M-4 control  (sleep 0.05 s, timeout 1000 ms): ('commit-ok', 1, 'IDLE', 51.575166173279285)
M-4 cancel   (sleep 0.50 s, timeout 100 ms) : ('commit-ok', 1, 'IDLE', 502.0395405590534)
M-4 cancel x30 (outcome, row_exists, txn_status): {('commit-ok', 1, 'IDLE'): 30}
M-4 race x400 (timeout 46..55 ms vs sleep 50 ms) (outcome, row_exists): {('commit-ok', 1): 400}
M-4 cancelled-but-committed cases: []
M-4 plain COMMIT under statement_timeout = 1 ms x300 (outcome, row_exists): {('commit-ok', 1): 300}
M-4b timeout 100 ms, deferred trigger sleeps 0.5 s, final step = sleep-statement: ('100ms', 'QueryCanceled/57014', '101ms', 'row_exists=0')
M-4b timeout 100 ms, deferred trigger sleeps 0.5 s, final step = set-constraints-immediate: ('100ms', 'QueryCanceled/57014', '101ms', 'row_exists=0')
M-4b timeout 100 ms, deferred trigger sleeps 0.5 s, final step = commit: ('100ms', 'ok', '503ms', 'row_exists=1')
M-4b timeout 100 ms, deferred trigger sleeps 0.5 s, final step = explicit-COMMIT-text: ('100ms', 'ok', '503ms', 'row_exists=1')
M-4b commit x20: {('ok', 'row_exists=1'): 20}
M-1(PG) under statement_timeout = 1 ms, SET LOCAL lock_timeout = 1 (after stmt timeout = 1) x2000: {'ok': 2000}
M-1(PG) under statement_timeout = 1 ms, SELECT 1 x2000: {'ok': 2000}
M-1(PG) under statement_timeout = 1 ms, SELECT by pk x2000: {'ok': 2000}
M-1(PG) under statement_timeout = 1 ms, SELECT 5000 rows ordered x300: {'ok': 300}
M-1(PG) SET LOCAL under an already-installed 1 ms timeout x2000: {'ok': 2000}
M-1(PG) 1 ms control, pg_sleep(0.002) x200: {'QueryCanceled/57014': 200} cancel latency ms min/max = 1.06/1.24
M-1(PG) 1 ms control, pg_sleep(0.01) x200: {'QueryCanceled/57014': 200} cancel latency ms min/max = 1.06/1.37
M-1(PG) 1 ms control, generate_series sort 200k x200: {'QueryCanceled/57014': 200} cancel latency ms min/max = 1.04/1.21
M-3 micro SET LOCAL statement_timeout: n=5000 p50=11.0us p95=13.8us mean=11.6us
M-3 micro set_config x2 in one SELECT: n=5000 p50=10.2us p95=12.6us mean=10.9us
M-3 micro SELECT 1: n=5000 p50=11.5us p95=13.7us mean=11.9us
```

構成: M-4 は表 `m4(id int primary key)` に `CREATE CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED` で `pg_sleep` する関数を付け、transaction の中で `SET LOCAL statement_timeout` (M-4b は `lock_timeout` も同値) を設定して INSERT し、最後の手を変えた。M-6 は別接続が `pg_advisory_xact_lock(42)` を保持した状態で、同じ lock を待たせた。M-3 micro は unix socket の 1 接続で同じ文を 5000 回 (psycopg の `execute` 1 回 = 1 往復)。両 peer の `src/` と migrations に `DEFERRABLE` / constraint trigger は無い (grep 0 件)。r2db の製品コードのコメント (`r2db-api/src/r2db_api/postgres.py:1736`) は既に同じこと (deferred trigger の仕事は `statement_timeout` で bound されない) を述べている。

### 12.2 M-1 (peer 経由、修正前)

計測専用 worktree (main `557cdd2`)、両 peer の tests に一時の未追跡テスト各 1 本 (計測後に削除)、`tools/dev/pt.py`。PostgreSQL 16.14、10 CPU、in-process の ASGI、認証は実 PostgreSQL の credential store。各 50 回、逐次。pt.py の集計行: r2db M-1 `pt: 1 passed, 2 deselected in 22.78s`、MitateDB M-1 `pt: 1 passed, 1 deselected in 44.41s`、r2db 負荷あり `pt: 1 passed, 2 deselected in 4.70s`、MitateDB 負荷あり `pt: 1 passed, 2 deselected in 15.96s`。

読み方: 列は 操作 / 駆動 / 予算 E (ms) / 記録した `_timeout_ms` の値:回数 / 50 回の結果。駆動は、r2db — A = 入口検査を通った後の pool 取得に 50 ms の実 sleep (予算 20 ms)、B = cell の入口の直前に clock を期限の 1 s 後へ (clock 注入)、C = pool 取得の後に残りを 0.6 ms にする、D = `budget.execution_ms = 1` だけ。MitateDB — R1 = `request_scope` の前に 50 ms の sleep (予算 20 ms)、R1b = deadline を now + 0.6 ms に差し替え、R2 = 別接続の advisory lock の競合で実際に待たせ `_retime` の直前に deadline を now + 0.6 ms にする、R2nat = 同じ競合で差し替えなし、D = `budget.execution_ms = 1` だけ。`_load` の節は CPU を busy な 10 process で埋めた状態。結果の `deadline@N` は `postgres.py:N` の `check_deadline` による 413、`cancel57014@<文>` はその文の `statement_timeout` による cancel の 413。

```
## r2db_m1_final
| query_light | baseline | E=20 | 19:50 | 50 x 200/ok |
| query_light | A | E=20 | 1:50 | 50 x 413/deadline@1554 |
| query_light | B | E=20 | none:50 | 50 x 413/deadline@1498 |
| query_light | C | E=20 | 1:50 | 29 x 413/deadline@1554; 21 x 200/ok |
| query_light | D | E=1 | 1:50 | 50 x 200/ok |
| query_heavy | baseline | E=20 | 19:50 | 50 x 200/ok |
| query_heavy | A | E=20 | 1:50 | 49 x 413/cancel57014@SELECT c.table_name, c.col; 1 x 413/cancel57014@SELECT "id", "label", "_r2 |
| query_heavy | B | E=20 | none:50 | 50 x 413/deadline@1498 |
| query_heavy | C | E=20 | 1:50 | 50 x 413/cancel57014@SELECT "id", "label", "_r2 |
| query_heavy | D | E=1 | 1:50 | 50 x 413/cancel57014@SELECT "id", "label", "_r2 |
| transact_light | baseline | E=20 | 19:50 | 50 x 200/ok |
| transact_light | A | E=20 | 1:50 | 49 x 413/cancel57014@SELECT c.table_name, c.col; 1 x 413/deadline@1691 |
| transact_light | B | E=20 | none:50 | 50 x 413/deadline@1613 |
| transact_light | C | E=20 | 1:50 | 50 x 413/deadline@1691 |
| transact_light | D | E=1 | 1:50 | 50 x 413/deadline@1691 |
| transact_heavy | baseline | E=20 | 19:50 | 50 x 200/ok |
| transact_heavy | A | E=20 | 1:50 | 49 x 413/cancel57014@SELECT c.table_name, c.col; 1 x 413/deadline@1691 |
| transact_heavy | B | E=20 | none:50 | 50 x 413/deadline@1613 |
| transact_heavy | C | E=20 | 1:50 | 50 x 413/deadline@1691 |
| transact_heavy | D | E=1 | 1:50 | 50 x 413/deadline@1691 |
| schema_create | baseline | E=20 | 19:50 | 50 x 200/ok |
| schema_create | A | E=20 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| schema_create | B | E=20 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| schema_create | C | E=20 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| schema_create | D | E=1 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| query_light(rep) | baseline | E=20 | 19:50 | 50 x 200/ok |
| query_light(rep) | C | E=20 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| query_light(rep) | A | E=20 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
## r2db_load
| query_light | C | E=20 | 1:50 | 50 x 413/deadline@1554 |
| query_light | D | E=1 | 1:50 | 50 x 413/deadline@1554 |
| query_heavy | C | E=20 | 1:50 | 49 x 413/cancel57014@SELECT c.table_name, c.col; 1 x 413/cancel57014@SELECT "id", "label", "_r2 |
| query_heavy | D | E=1 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| transact_light | C | E=20 | 1:50 | 49 x 413/cancel57014@SELECT c.table_name, c.col; 1 x 413/deadline@1691 |
| transact_light | D | E=1 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| transact_heavy | C | E=20 | 1:50 | 49 x 413/cancel57014@SELECT c.table_name, c.col; 1 x 413/deadline@1691 |
| transact_heavy | D | E=1 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
| schema_create | C | E=20 | 1:50 | 49 x 413/cancel57014@SELECT c.table_name, c.col; 1 x 413/deadline@2202 |
| schema_create | D | E=1 | 1:50 | 50 x 413/cancel57014@SELECT c.table_name, c.col |
## mitatedb_m1_final
| read_light | baseline | E=20 | 19:50 | 50 x 200/ok |
| read_light | R1 | E=20 | 1:50 | 50 x 200/ok |
| read_light | R1b | E=20 | 1:50 | 50 x 200/ok |
| read_light | D | E=1 | 1:50 | 50 x 200/ok |
| read_heavy | baseline | E=20 | 19:50 | 50 x 200/ok |
| read_heavy | R1 | E=20 | 1:50 | 44 x 413/cancel57014@SELECT column_name, data_t; 5 x 200/ok; 1 x 413/cancel57014@SELECT "label", "tag", "_m |
| read_heavy | R1b | E=20 | 1:50 | 50 x 200/ok |
| read_heavy | D | E=1 | 1:50 | 50 x 200/ok |
| transact_light | baseline | E=20 | 19:50 | 50 x 200/ok |
| transact_light | R1 | E=20 | 1:50 | 50 x 200/ok |
| transact_light | R1b | E=20 | 1:50 | 50 x 200/ok |
| transact_light | D | E=1 | 1:50 | 50 x 200/ok |
| transact_light | R2nat | E=5000 | 4999/4983:3, 4999/4984:11, 4999/4985:35, 4999/4986:1 | 50 x 200/ok |
| transact_light | R2 | E=5000 | 4999/1:50 | 50 x 200/ok |
| transact_heavy | baseline | E=20 | 19:50 | 50 x 200/ok |
| transact_heavy | R1 | E=20 | 1:50 | 50 x 200/ok |
| transact_heavy | R1b | E=20 | 1:50 | 50 x 200/ok |
| transact_heavy | D | E=1 | 1:50 | 50 x 200/ok |
| transact_heavy | R2nat | E=5000 | 4999/4983:2, 4999/4985:27, 4999/4984:19, 4999/4986:2 | 50 x 200/ok |
| transact_heavy | R2 | E=5000 | 4999/1:50 | 50 x 200/ok |
| schema_create | baseline | E=20 | 19:50 | 50 x 200/ok |
| schema_create | R1 | E=20 | 1:50 | 43 x 413/cancel57014@CREATE TABLE "m1s_schr1x76; 7 x 200/ok |
| schema_create | R1b | E=20 | 1:50 | 50 x 200/ok |
| schema_create | D | E=1 | 1:50 | 50 x 200/ok |
| schema_create | R2nat | E=5000 | 4999/4983:3, 4999/4984:15, 4999/4985:29, 4999/4986:3 | 50 x 200/ok |
| schema_create | R2 | E=5000 | 4999/1:50 | 50 x 200/ok |
| read_light(rep) | baseline | E=20 | 19:50 | 50 x 200/ok |
| read_light(rep) | R1 | E=20 | 1:50 | 50 x 200/ok |
| read_heavy(rep) | baseline | E=20 | 19:50 | 50 x 200/ok |
| read_heavy(rep) | R1 | E=20 | 1:50 | 44 x 413/cancel57014@SELECT column_name, data_t; 5 x 200/ok; 1 x 413/cancel57014@SELECT "label", "tag", "_m |
| transact_light(rep) | baseline | E=20 | 19:50 | 50 x 200/ok |
| transact_light(rep) | R1 | E=20 | 1:50 | 50 x 200/ok |
## mitatedb_load
| read_light | R1b | E=20 | 1:50 | 50 x 200/ok |
| read_light | D | E=1 | 1:50 | 50 x 200/ok |
| read_heavy | R1b | E=20 | 1:50 | 50 x 200/ok |
| read_heavy | D | E=1 | 1:50 | 50 x 200/ok |
| transact_light | R1b | E=20 | 1:50 | 50 x 200/ok |
| transact_light | D | E=1 | 1:50 | 50 x 200/ok |
| transact_light | R2 | E=5000 | 4999/1:48, 4999:2 | 50 x 200/ok |
| transact_heavy | R1b | E=20 | 1:50 | 50 x 200/ok |
| transact_heavy | D | E=1 | 1:50 | 37 x 200/ok; 12 x 413/cancel57014@SELECT count(*) FROM infor; 1 x 413/cancel57014@SELECT column_name, data_t |
| transact_heavy | R2 | E=5000 | 4999/1:48, 4999:2 | 50 x 200/ok |
| schema_create | R1b | E=20 | 1:50 | 46 x 200/ok; 4 x 413/cancel57014@CREATE TABLE "m1s_ldschr1b |
| schema_create | D | E=1 | 1:50 | 47 x 200/ok; 3 x 413/cancel57014@CREATE TABLE "m1s_ldschdxa |
| schema_create | R2 | E=5000 | 4999/1:49, 4999:1 | 48 x 200/ok; 2 x 413/cancel57014@CREATE TABLE "m1s_ldschr2x |
```

### 12.3 M-7 (受信から受理点まで。n = 200、ms)

M-1 と同じ環境。pt.py の集計行: r2db `pt: 1 passed, 1 deselected in 4.75s`、MitateDB `pt: 1 passed, 2 deselected in 12.63s`。受理点は r2db が `r2db-api/src/r2db_api/service.py:313` / `:374` の期限計算、MitateDB が `MitateDB-api/src/mitatedb_api/cell.py:686-692` の `_limit_gate` が deadline を渡す時点。全系列で 受信 < 認証の開始 < 認証の終了 < body の解析の終了 < 受理点 の順を 200/200 で確認した。MitateDB の「body の解析の終了 → 受理点」の約 2.5 ms の内訳は未調査。

| 系列 | peer | 受信→受理点 p50 / p95 / max | うち認証 p50 | 要求全体 p50 |
|---|---|---|---|---|
| query 軽 | r2db | 0.510 / 0.553 / 0.591 | 0.234 | 1.309 |
| query 重 | r2db | 0.538 / 0.570 / 0.604 | 0.247 | 5.659 |
| mutate 3 operation | r2db | 0.531 / 0.565 / 0.617 | 0.240 | 1.479 |
| mutate 100 operation (body 約 9 KB) | r2db | 0.785 / 0.816 / 0.851 | 0.253 | 5.806 |
| query 軽、32 並列 (n = 224) | r2db | 53.257 / 88.808 / 101.015 | 0.749 | 62.984 |
| read 軽 | MitateDB | 5.090 / 5.180 / 5.336 | 2.436 | 5.616 |
| read 重 | MitateDB | 5.138 / 5.332 / 5.910 | 2.468 | 6.938 |
| mutate 3 operation | MitateDB | 5.141 / 5.267 / 5.744 | 2.456 | 6.146 |
| mutate 100 operation | MitateDB | 5.956 / 6.124 / 6.273 | 2.552 | 27.737 |
| read 軽、32 並列 | MitateDB | 77.954 / 106.097 / 112.655 | 4.906 | 81.101 |

### 12.4 M-8 (修正前に測れる分)

計測専用 worktree (main `557cdd2`)、一時の未追跡テスト 1 本 (計測後に削除)、`tools/dev/pt.py` で 2 回 (`pt: 12 passed in 93.06s (0:01:33)`、`pt: 12 passed in 95.39s (0:01:35)`)。N=20、6 plug。load average は 1 回目 2.3/2.7/2.6、2 回目 3.3/3.4/3.1。完了ゲートの負荷の下ではない。件数は 2 回とも同じ。「到達」は、要求を出す直前から handle の `wait_until_held` が戻るまで。6 plug とも `request_budget` は enabled、`limits.execution_ms` は 5000、`limit_enforcement.execution_ms` は `reference_wall_clock`。

(ii) `hold_after_idempotency_lookup` の stall 点への到達 (budget なし、ms、p50 / max): r2db in-process 0.1 / 0.2、r2db-http 1.2 / 4.1、r2db-socket 4.5 / 7.9、MitateDB in-process 0.1 / 0.3、MitateDB-http 1.2 / 1.8、MitateDB-socket 4.2 / 5.5。全 plug で 20/20 到達。

(iii) `hold_after_plan_verification` の stall 点への到達と、plan を得る dry run 単体 (ms、p50 / max):

| plug | 到達 | dry run |
|---|---|---|
| r2db in-process | 0.1 / 0.2 | 0.1 / 0.2 |
| r2db-http | 2.8 / 3.4 | 4.5 / 5.6 |
| r2db-socket | 5.8 / 6.1 | 8.1 / 17.2 |
| MitateDB in-process | 0.1 / 0.3 | 0.1 / 0.2 |
| MitateDB-http | 1.6 / 1.8 | 1.8 / 2.0 |
| MitateDB-socket | 5.0 / 5.5 | 5.2 / 5.4 |

`budget.execution_ms = B` での到達率: B ∈ {5, 10, 20, 50, 100, 200, 500} のすべてで、(ii)(iii) とも 6 plug で 20/20 が stall 点に届いた (届く前の拒否 0 件)。到達時間は B に依らない。

修正前の挙動 (B = 50、合図から 60 ms 保持して放す。全 plug 20/20 到達):

(ii)

| plug | 放した後の応答 | 残った行 | budget を外した同 key の再送 |
|---|---|---|---|
| r2db in-process / http / socket | `LIMIT_EXCEEDED` / execution_ms 20/20 | 0 | 新規実行で成功 20/20 |
| MitateDB in-process (SQLite) | `LIMIT_EXCEEDED` / execution_ms 20/20 | 0 | 新規実行で成功 20/20 |
| MitateDB-http / MitateDB-socket (PostgreSQL) | **成功 20/20** | **1** | **`CONFLICT` / `idempotency_key` 20/20** |

(iii)

| plug | 放した後の応答 | revision |
|---|---|---|
| r2db in-process / http / socket | `LIMIT_EXCEEDED` / execution_ms 20/20 | 動かない |
| MitateDB in-process (SQLite) | `LIMIT_EXCEEDED` / execution_ms 20/20 | 動かない |
| MitateDB-http / MitateDB-socket (PostgreSQL) | **成功 20/20** | **+1 (field が増える)** |

- r2db の 3 plug と MitateDB の SQLite plug が修正前から期待どおりになるのは、r2db は各 operation 前の `check_deadline`、SQLite は `_check_deadline` による。
- budget の無い dry run で得た plan を budget 付きの実要求に出すと、6 plug すべてで `PRECONDITION_FAILED` (`violated_declaration` は `plan`)。r2db の 3 plug は stall 点に届いてから放した後に拒否され、MitateDB の 3 plug は stall 点より前で拒否される (到達 0)。
- 補足 (推測を含む): B = 5 で合図の直後に放すと、r2db-http と r2db-socket の (ii) だけが 5/20 で `LIMIT_EXCEEDED` を返した (2 回とも 5/20)。新しい application の最初の要求 (pool が冷えている) が遅いためと推測するが、未検証。

### 12.5 perf_baseline (M-3・M-5)

main checkout、他の pytest なし、load average 2.8〜4.1。`./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 1` と `./.venv/bin/python tools/perf_baseline.py --n 15 --warmup 3 --concurrency 32` (K=32 を既定の n で回すと r2db の rate の bound に当たって `LIMIT_EXCEEDED` で止まるので、`tools/PERF_BASELINE_README.md` の D-16 の標本数を使った)。

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=3ce48d2 date=2026-10-02
```

M-3: K=1 の `DBTIME ... scope=app` (PostgreSQL の http plug。各 op は 100 要求 × 2 回 = 200 要求ぶん):

| plug | op | db_calls / 要求 | db_wall_ms / 要求 | 要求の p50 (ms) |
|---|---|---|---|---|
| r2db-api-http | query | 3.0 | 0.437 | 1.627 |
| r2db-api-http | mutate | 3.5 | 0.502 | 1.680 |
| r2db-api-http | batch | 5.5 | 0.584 | 1.851 |
| MitateDB-api-http | query | 6.5 | 0.419 | 1.341 |
| MitateDB-api-http | mutate | 5.0 | 0.359 | 1.153 |
| MitateDB-api-http | batch | 15.0 | 0.945 | 1.947 |
| MitateDB-api-http | cross_entity | 7.5 | 0.460 | 1.325 |

```
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=43.665 db_wall_ms_per_req=0.437
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=50.234 db_wall_ms_per_req=0.502
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=58.423 db_wall_ms_per_req=0.584
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1300 txns=200 db_wall_ms=41.942 db_wall_ms_per_req=0.419
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1000 txns=200 db_wall_ms=35.903 db_wall_ms_per_req=0.359
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=3000 txns=200 db_wall_ms=94.473 db_wall_ms_per_req=0.945
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=3 gone=0 db_calls=1500 txns=200 db_wall_ms=46.038 db_wall_ms_per_req=0.460
```

M-5: K=32 の `POOL` 行の要約:
- MitateDB (http / socket): role の pool (size 6) は runtime / developer とも `waits=0`、`in_use_peak=4`。`schema_lock` (application の advisory lock。acquire は op により 5〜1737) も `waits=0 wait_max_ms=0.000`。台帳 R-102 の後、この負荷の形では pool の待ちも lock の待ちも 0 (台帳 R-78 の「cell lock の最大待ち 28〜67 ms」は廃止前の値で、現物には当てはまらない)。
- r2db (http / socket): runtime の pool (size 2) は `waits` 142〜1207、`wait_max_ms` 3.234〜3.433、`in_use_peak=2`。
- 要求の p50 (K=32): http plug 30.6〜47.5 ms、socket plug 133〜154 ms。
- 既定の execution_ms 5000 ms に対して、受理点の後の待ち (pool・lock) は最大 3.4 ms で、余裕は 3 桁ある。計測は harness の負荷の形 (同じ application への 32 並列、4 op) に限る。schema 操作と data 操作の競合、長い transaction の後ろの待ちは測っていない。

```
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_bf6937d44c41/runtime size=2 acquire=1729 waits=1207 wait_total_ms=647.108 wait_max_ms=3.234 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_471555f7c2d4/runtime size=2 acquire=577 waits=151 wait_total_ms=97.167 wait_max_ms=3.433 in_use_peak=2
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity role=perfbase_9765af0760d6/runtime size=6 acquire=2306 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity schema_lock=perfbase_9765af0760d6 acquire=1737 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity role=perfbase_c65c40a6d067/runtime size=6 acquire=2306 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity schema_lock=perfbase_c65c40a6d067 acquire=1737 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
```
