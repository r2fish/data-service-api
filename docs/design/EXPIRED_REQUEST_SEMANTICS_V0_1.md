# 設計メモ — 期限切れ要求の意味論 (R-42)

## 0. 版数・位置づけ

- **v0.3 (2026-10-02)。** 再確認 (担当観点: 指定なし) の 12 件と観察 1 件を反映。U-8 の (d) の扱い、U-9 の pin の向きの訂正。反映の一覧は §11.2。同日、レビュー項目の記号を R-N から RV-N に改めた (台帳の R 族との衝突を避ける)。
- **v0.2 (2026-10-02)。** 設計レビュー 1 回目 (A 9 件・B 15 件 → 19 件に統合) を反映。新しい U-8・U-9。起票候補 1 件 (MitateDB schema 操作の cancel 分岐の `commit_failed` 欠落)。反映の一覧は §11。
- **v0.1 (2026-10-02)。** 基点 local main `4241b55`。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-42 (規模 L、変更クラス D (`RM` §9 の 8))。契約 1.14.0 (subordinate ruling 19)、port v1.21。
- 着手の根拠: 台帳 R-42 行の依頼者裁定 (`RM`:462) 「**【追記 2026-09-15 依頼者裁定】** 「R-42はフェーズ11で」 — **フェーズ11 で扱う**。」
- ファイル名は依頼者指示 2026-10-02 による。台帳項目の設計であり計画文書のフェーズ節ではないので、運用条件 §1.8 の 53 の転記は行わない。
- 範囲: 共通の意味論と契約文言の候補まで (`CLAUDE.md` の開発順序)。契約・conformance・実装は変えない。
- 本 session は cloud で PostgreSQL が無く、新しい実測はしない。PostgreSQL の挙動に依る主張には次のどれかを添える: **【既存実測: 出所】** / **【PG 文書 (未実測)】** / **【未確認 → M-N】** (§8)。
- 表記: file:line は基点 main のもの。r2db の製品コードは `r2db-api/src/r2db_api/`、MitateDB は `MitateDB-api/src/mitatedb_api/` からの相対で書く。「(読解の報告。基点で未照合)」「(レビューの報告。基点で未照合)」を添えた事実は報告であり、照合済みの事実と区別する。出所の記法は運用条件 §0。

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
| 4 | pool 取得 (`self._runtime.connection()` / `self._developer.connection()`) | 期限を渡さない。固定の `_DEFAULT_CONNECT_TIMEOUT_S = 5`、`_DEFAULT_ACQUIRE_TIMEOUT_S = 10.0` (`postgres.py:230-231`) | 待ちの超過は `psycopg.OperationalError` が backend の `try` の外 (`:1502` 対 `:1504`) → http 層で汎用 503 (`http.py:362-367`) |
| 5 | `_timeout_ms` → `_set_timeouts` | `postgres.py:2649-2654` / `:2656-2672` | `max(1, int(remaining))` で残り 0 以下でも 1 ms。transaction ごとに 1 回、再計算なし。`statement_timeout` と `lock_timeout` を同値で `SET LOCAL` |
| 6 | advisory lock (`_idempotency_key_lock` / `_idempotency_reserve_lock` / `_schema_serialization_lock`) | `postgres.py:1352-1412` | `pg_advisory_xact_lock` の待ちは `lock_timeout` に掛かる **【PG 文書 (未実測)】**。待った後の再検査・再設定は無い |
| 7 | 以降の `check_deadline` | query `:1554` (SELECT 後)、transact `:1691` (各 operation 前)・`:1701` (loop 後)、apply_schema `:2202` (DDL 前の 1 回) | `_idempotency_store`・`pre_commit`・COMMIT の前には無い |
| 8 | エラー写像 | `limits.py:101` と `postgres.py` の各 except (`:1120-1123` / `:1544-1547` / `:1735-1744` / `:2428-2437`) | `QueryCanceled` / `LockNotAvailable` → 413 `LIMIT_EXCEEDED`、details `{resource: "execution_ms", limit_class: "execution_ms", limit: <実効の execution_ms>}` |
| 9 | 残るもの | 1 transaction | rollback で部分適用・idempotency 記録は残らない。`pre_commit` (durable audit の allow 行、別接続で commit 済み) の後に COMMIT が cancel されると、data は rollback、allow 行は残り、`commit_failed()` が error 行を best-effort で追記し、応答は 413 (`service.py:112-117`)。transact も apply_schema も同じ (apply_schema は idempotency を pre_commit より前に書く、`postgres.py:2407-2415`、レビューの報告。基点で未照合)。`LIMIT_EXCEEDED` は `_DURABLE_DENIAL_CODES` (`service.py:49-56`) に無く、deny event は in-memory sink のみ |
| 10 | dry_run | 2〜5・catalog・各 operation 前の検査は同じ | idempotency の lock・lookup・reserve を飛ばす。終端は `psycopg.Rollback` |

### 1.4 MitateDB の時系列 (`MitateDB-api/src/mitatedb_api/` 相対)

| # | 段 | 場所 | 期限を既に過ぎていたら |
|---|---|---|---|
| 1 | `_limit_gate`: rate → concurrency slot (待たない) → bytes・depth → budget で狭める → `deadline = time.monotonic() + max_execution_ms/1000` | `cell.py:686-692`。clock の注入は無い | — |
| 2 | `_borrow`: `pool.acquire(timeout = max(0, deadline - now))` | `backend_postgres.py:452-463`、`pool.py:444-508` | 3 経路: (1) idle 接続あり → 残り 0 でも即返る (`pool.py:465-475`)。(2) 上限未満・idle なし → 新規接続。`connect_timeout = min(設定値, max(1, ceil(残り)))` で、psycopg の下限 2 s が掛かる (`pool.py:444-492`)。失敗は `PoolConnectFailed` → `StorageTransientError` 503 (`backend_postgres.py:462-463`)。(3) 上限到達・idle なし → `PoolExhausted` → `ResourceLimitError(limit_class="execution_ms")` 413 (`pool.py:498-508`) |
| 3 | `request_scope`: `_timeout_ms(deadline)` → `SET LOCAL` | `backend_postgres.py:484-500`、`_timeout_ms` は `:1681-1685` | **入口の残り検査は無い**。`max(1, int(remaining))` で残り 0 以下でも 1 ms。`SET LOCAL` の cancel は `psycopg.Error` → `StorageTransientError` 503 (`:493-500`) |
| 4 | advisory lock (`_acquire_advisory`) | `backend_postgres.py:555-606` | try 形で取れれば 1 文で `_retime` 無し。取れなければ block 形で待ち、`lock_timeout` に掛かる (`QueryCanceled` / `LockNotAvailable` → `ResourceLimitError` execution_ms、`:577-578`)。待った後だけ `_retime` (`:604`)。idempotency の key lock・件数 lock も同じ経路 (`:1766`、`:1803-1804`) |
| 5 | `_retime` | `backend_postgres.py:532-552` | `scope.deadline - now <= 0` なら拒否。それ以外は `_timeout_ms` で再 `SET LOCAL`。0 < 残り < 1 ms は `max(1, int(0)) = 1` → 1 ms。再 `SET LOCAL` の cancel は `psycopg.Error` → `StorageTransientError` 503 (`:544-552`) |
| 6 | 文の間 | operation loop (`cell.py:2838-2848`) と create_collection の複数文 (`backend_postgres.py:1176-1218`) の間に検査なし。`begin` は no-op (`backend_postgres.py:1700-1703`) | 検査されない |
| 7 | 残るもの | 1 transaction、release 時に rollback | 部分適用・idempotency 記録は残らない。`LIMIT_EXCEEDED` は耐久 denial の対象外 (`audit_dispatch.py:30-55`、読解の報告。基点で未照合)。順序は経路で違う: transact は idempotency 記録 → pre_commit → commit (`cell.py:2908-2919`) で、pre_commit の前の打ち切りなら audit 行なし。schema 操作は pre_commit (`backend_postgres.py:1204`) を idempotency の書き込み (`:1229`) と commit (`:1230`) より先に行い、その後の cancel 分岐 (`:1231-1233`) も `except Exception` も `commit_failed` を呼ばない — allow 行だけが残り error 行は追記されない (`:1058`、`:1372`、`:1648` の同形はレビューの報告。基点で未照合)。この順序 (pre_commit の後に idempotency の書き込み = 文) は D-2 (pre_commit の後に文を発行しない) と両立しないので、D-9 で並べ替える |
| 8 | 応答の経路差 | (読解の報告。基点で未照合) | schema 操作は commit も同じ try 内で 413 execution_ms (#7 のとおり `commit_failed` なし)。transact の `backend.commit` (`backend_postgres.py:1705`) と `record_idempotency` は psycopg 例外を翻訳しない → commit の cancel は `AuditSinkUnavailable` 503、`record_idempotency` の cancel は http の `except Exception` で汎用 503。read の `_end_reads` の commit 失敗は `StorageTransientError` 503 |
| 9 | HTTP | `http.py:84`、`errors.py:80-91` | `LIMIT_EXCEEDED` は 413、details は `{"limit_class": "execution_ms"}` のみ |
| 10 | SQLite plug | `backend_sqlite.py:22-27`、`:181`、`:646`、`:711` | 入口と begin で `_check_deadline` (strict `>`) を持つ |
| 11 | dry_run | 期限・pool・lock・`SET LOCAL` は同じ | idempotency 検査なし、audit hook 不構築、rollback。create_collection の dry_run は CREATE TABLE を実走し bump と INSERT を飛ばす (`backend_postgres.py:1180-1200`) |

### 1.5 1 ms の文が走る経路 (両 peer に残る)

- r2db: `check_deadline` を通った後の pool 待ち → `_timeout_ms` = 1 ms (pool に期限が渡らない)。apply_schema は入口検査が無いので期限切れでも pool → 1 ms。advisory lock を待った後に再設定が無いので、待ちの後の文は「scope 入口の残り」の満額で走る (超過の方向)。0 < 残り < 1 ms は `check_deadline` を通り `_timeout_ms` = 1 ms。
- MitateDB: `request_scope` の入口 (残り 0 以下でも 1 ms。pool に idle があれば `_borrow` は即返る)、`_retime` の 0 < 残り < 1 ms、その下で走る全文。
- 共通: 1 ms の `statement_timeout` の下では、`SET LOCAL` 自体・catalog 読み・本体の文のどれが cancel されるかが負荷で変わり、同じ要求が 200 にも 413 にもなる。MitateDB について **【既存実測: `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 の【追記 2026-09-15、v0.17】】**。r2db について **【未確認 → M-1】**。
- MitateDB では `SET LOCAL` と `_retime` の cancel が 503 に写るので (§1.4 #3・#5)、同じ要求は 200 / 413 / 503 に分かれる。`SET` 自体が 1 ms で cancel され得るかは **【未確認 → M-1】**。
- 利用者 (AI エージェント) は結果から再送の可否を決められない。契約は期限切れの要求が「何も残していない」ことを明文化していない。

### 1.6 既存の記録にある実測 (再測しない)

- `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 【追記 2026-09-15、v0.17】: MitateDB の要求 B が lock の後ろで約 10 s 待ち、`statement_timeout = 1ms` で走っていた。`timeout_ms == 1` のときに 10 ms の文を強制すると、ゲートの赤が再現した (`a_status: 200`、`b_status: 413`)。
- 台帳 R-78 (`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md`): r2db の pool size 32 の待ちは 0、size 2 の最大待ちは K=4 で 2.5 ms、K=32 で 35.0 ms。MitateDB の cell lock の最大待ちは 28〜67 ms (K=32 で 67.1 ms) — **台帳 R-102 で cell lock が廃止される前の値**。query p50 は K=32 で r2db 63〜67 ms、MitateDB 211〜220 ms。
- 台帳 R-80 (`docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md`): 往復の成分を測る道具 (`tools/perf_baseline.py --roundtrip`)。1 文の追加の費用はこの道具で測る。
- CI は `postgres:16` (`CI`:196)。PostgreSQL 17 の `transaction_timeout` は使えない。作業機の版は **【未確認 → M-2】**。
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

**D-1 execution_ms は 1 要求の wall-clock 予算である。** 始点は遅くとも「受理点」— 要求がその配備の rate・concurrency の gate を通り、budget で狭めた要求固有の bound が確定した時点 (両 peer が今期限を計算している点、§1.3 の 2・§1.4 の 1)。受理点から応答が決まるまでの時間 — pool の取得待ち、lock の待ち、文の実行、commit — はすべて予算に数える。実装はもっと早く (受信時から) 数え始めてよいが、遅く始めてはならない。1 page = 1 要求で、page ごとに新しい予算。dry_run も同じ予算の下で走る (dry run は文を発行する)。ただし dry run の execution_ms の拒否は real の要求の拒否を予言しない (発行する文が違う)。契約は dry run が limit の拒否も決めると読める文を持つ (1.7.0 (3)) ので、execution_ms がその例外であることを §9.1 で明記する。
- 根拠: SI-08 は要求 1 件が資源を無限に持てないことを求め、利用者に見える所要時間を bound するのは待ちを含めてこそである。MitateDB の `_borrow` の docstring は既に「期限を超える待ちは要求が execution_ms を超えたこと」と読んでいる。待ちを別 class に分けると `limits.classes` の語彙 (1.2.0 の規則) に新語が要り、利用者が 2 つの予算を推論する負担が増え、安全の結果は増えない (→ U-1 で両論を残す)。

**D-2 予算を使い切った要求は、次の文を発行する前に拒否する。**
- 「文」の定義: 実装が要求のために保持するすべての接続 (MitateDB の developer 接続の catalog 読みを含む。要求自身の各 transaction) で、要求の内容から発行する文。psycopg の暗黙の BEGIN はその transaction の一部。`SET LOCAL`、catalog 読み、lock の文、idempotency の読み書き、DML / DDL を含む。含めない: pool の維持 (r2db の checkout ごとの `SELECT 1` `postgres.py:621`、新規接続の `SET search_path` `postgres.py:388`、MitateDB の idle ping `pool.py:369`・`:384`。いずれもレビューの報告。基点で未照合)、transaction を終える COMMIT / ROLLBACK (下の (d) で別に扱う)、別接続の audit sink への書き込み。
- 実装は、文を発行しようとする各点で残り予算を process 内の時計で比べ、残りが 1 ms 未満 (整数 ms で 0) なら文を発行せず `LIMIT_EXCEEDED` + `details.limit_class: execution_ms` で終える。`_timeout_ms` 自身も残り 1 ms 未満で `LIMIT_EXCEEDED` を上げ、決して 0 を返さない (`statement_timeout = 0` は timeout の無効 **【PG 文書 (未実測)】** なので、0 を返すと fail-open になる)。v0.1 の「`max(1, …)` の丸めを廃止する」はこの形に改めた (§11 RV-3)。
- 検査点は実装の自由だが、少なくとも (a) pool 取得の後・最初の `SET LOCAL` の前 (`_timeout_ms` の拒否が兼ねる 1 点)、(b) lock 待ちの後、(c) 複数文の要求の文と文の間、(d) [U-8 (b)] durable audit の pre_commit の前、に置く。**検査点はすべて pre_commit より前に置く。pre_commit の後は時計で検査せず COMMIT を発行し、COMMIT は最後に設定した文の bound (lock 待ちの後の再設定を含む) でだけ打ち切られる (D-3 の例外)。**
- 最後の文が完了した後に時計で検査するか ((d) を置くか) は U-8。U-8 (a) では (d) を置かない。
- 検査は時計の比較だけで DB 往復を足さない (X-1)。
- 閾値を「1 ms 未満」とする理由: `statement_timeout` の分解能は 1 ms で、0 は「無効」を意味するので、1 ms 未満の残りで文を発行する手段が無い **【PG 文書 (未実測)】**。→ 閾値は U-7 で確認。
- 範囲: D-2 が決定的にするのは予算を使い切った要求だけである。残りが 1 ms 以上で文の所要時間より短い帯 (例 1.5 ms) では 200 / 413 が負荷に依り、D-3 により再送は安全である。

**D-3 期限で終わった要求は、行・catalog・schema revision・idempotency 記録を残さない。** 1 要求 = 1 transaction の rollback による。idempotency は契約 `structured_operations.idempotency.record` の「失敗した要求は記録を残さない」の帰結であり、execution_ms の失敗もこれに含まれる。同じ key の再送は新規の試行として実行される。
- 語の分け方: 契約 `structured_operations.dry_run.external_effects` は「externally visible な状態変化」に audit event を含めるので、本書と §9 はこの語を使わず、残さないものを列挙する。この列挙は audit の証跡を律しない (どの audit event が残るかは列挙の外で、`transactions.atomic` と `structured_operations.dry_run.external_effects` は変えない)。
- audit: `LIMIT_EXCEEDED` は耐久 denial ではない (両 peer の現物。SI-14 の security-relevant な denial ではない) ので変えない。
- 例外は commit 段 (pre_commit の allow 行の後に COMMIT が cancel される場合)。error 行を best-effort で追記する現行の形を維持するのは **transact と r2db の全経路に限る**。MitateDB の schema 操作は現行で `commit_failed` を呼ばない (§1.4 #7。D-9 で足す)。commit が実際に成立したかの判定は **【未確認 → M-4】** で、commit 段の契約文は M-4 の結果まで【保留】とする (§9.1)。

**D-4 エラーの形は既存のまま**: code `LIMIT_EXCEEDED`、`details.limit_class: execution_ms`。HTTP status は契約で未定義のまま (両 peer の 413 は conformance の cross-peer 証拠で固定済み)。新しい code (X-5)・新しい class (X-4)・新しい details key (X-8) は足さない。再送の可否は D-3 の保証 (何も残っていない) で足りる。既存の `details.futility` を付けるかは U-3。

**D-5 文の途中で期限が来た要求は、実装の文の bound (`statement_timeout` / `lock_timeout`) で打ち切る (現行どおり)。** 打ち切りの結果は D-3 と同じ。
- 上限の主張は**文の実行区間に限る**: 文の bound を「scope 入口の残り」で 1 回設定し (lock 待ちの後に再設定)、文の間は D-2 の時計検査で補う現行の形では、文の実行区間の合計は「残りの 2 倍未満」である (文 n は残りが尽きる前にしか始まらず、その文自身は入口の残りまで走れる) **【PG 文書 (未実測): 文ごとの計測】**。文ごとに bound を再設定すれば「残り + 1 文の分解能」になるが、文ごとに 1 往復が増える。→ U-2 で両論。
- 文の実行区間の外は、次の別の上限で bound される:
  - 接続の確立: 上限は `connect_timeout`。MitateDB は `min(connect_timeout, max(1, ceil(残り)))` で psycopg の下限 2 s が掛かる (`pool.py:444-492`)。r2db は固定 5 s (`postgres.py:230`)。接続の確立の後に期限が切れていれば、D-2 (a) の検査 (pool 取得の後) が文の前で捕まえる。
  - audit sink への書き込み (別接続)。
  - COMMIT (D-2 のとおり最後に設定した文の bound。lock 待ちの後の再設定を含む)。

**D-6 契約の文言を足し、minor 版 1.15.0 (subordinate ruling 20) とする (推奨。→ U-4 で両論)。** 足す場所と記録:
- execution_ms の節 (始点、待ちの算入、要求全体の予算、1 page = 1 要求、dry_run、「予算を使い切った要求は次の文を発行する前に拒否され、行・catalog・schema revision・idempotency 記録を残さない」)。置き場は U-9 (推奨 (a) `limits` の新 key `execution_ms`)。v0.1 では `limits.execution_ms` の新 key に置くと定めていたが、v0.2 (2026-10-02) で `conformance-tests/test_contract.py` の `_PRE_1_8_0_LIMITS_KEYS` の pin (`:137-146`、`:180-184`) が新しい sibling key を 1.8.0 の裁定として禁じていることがわかったので、U-9 に移した (§11 RV-14)。`errors.details_vocabulary.LIMIT_EXCEEDED` は変えない。選択肢ごとの pin: (a) は `_PRE_1_8_0_LIMITS_KEYS` の切り直し、(b) は `limits.profile` の endswith pin (`conformance-tests/test_contract.py:111-115`、`:177`) を 1.8.0 の文より前に挿入すれば保ち、末尾なら切り直す、(c) は `PIN_1_7_0_REQUEST_BUDGET` が包含照合 (`:2267-2268`) なので末尾追記なら保つ (U-9)。
- `structured_operations.idempotency.record` には挿入しない。§9.1 の「no idempotency record」と義務 (c) で足りる。v0.1 の挿入案は、文中への挿入が `PIN_1_7_0_IDEMPOTENCY_RECORD` (`conformance-tests/test_contract.py:2165-2166`、包含で照合 `:2286`) を、末尾への追記が `PIN_1_8_0` の endswith (`:525-532`、`:578`) を壊すので削った (§11 RV-14。行番号はレビューの報告。基点で未照合)。
- `versioning.version_binding` の散文に 1.15.0 の段落 (無条件義務の列挙、「1.14.0 のままの実装は遡って縛られない」)、`versioning.obligations[]` に entry。段落の置き場は 1.14.0 の前例どおり「1.14.0 の段落の直後・version-flip 文の前」。
- `structured_operations.dry_run.decision` に、execution_ms の拒否は dry run と real で同じとは限らない旨の相互参照の 1 文を追記する (§9.4。`PIN_1_7_0_DRY_RUN_DECISION` は包含照合なので追記で壊れない、レビューの報告。基点で未照合)。
- 1.14.0 の前例どおりの記録: `spec/CONTRACT_HISTORY.md` の revision note (`:428` の Revision note 10 の形。既存の義務 1.7.0 (3) を狭めることも記録する)、`spec/CCR_DISPOSITION.md` の ruling 20 (`:343` の ruling 19 の形)。
- 文言は候補として §9 に置き、依頼者が確定する。変える節に掛かる pin (U-9 の選択で決まる) を確定後に更新する (本 session では触らない)。

**D-7 conformance で決定的に固定する: 新しい共通条件を 1 件足す** (番号は conformance の WP で採番し、C-35 の次を見込む。`tools/check_doc_refs.py` が未定義の C 族番号を参照切れとして止めるので本書では番号を書かない。先例 `docs/design/MULTI_PROCESS_WORKER_V0_1.md:766`。以下「新条件」)。性質は §6.2 の (i)〜(iii)。
- 駆動 (i): 新 primitive は、契約の点で「rate・concurrency・budget の bound が確定した後、最初の接続取得の前」で止めると定義する。従って期限の検査と文のどちらよりも前である。受理点から stall 点までに検査が無いので `budget.execution_ms = 1` でよく、十分長く (例 100 ms) 保持して放すと、放した後の最初の検査で拒否される。
- 駆動 (ii)(iii): stall 点に届くまでに文と検査がある (r2db は入口検査・`SET LOCAL`・key lock・lookup、plan 検証)。予算 B は「stall 点に届く」のに足りる値にし、保持は test が受け取る「stall 点に入った」合図 (`hold_after_idempotency_lookup` / `hold_after_plan_verification` の handle の既存の合図) の時点から B + 余裕 (例 B/5) を単調時計で測って放す。受理点は stall 点より前なので、放した時点で受理点からの経過は必ず B + 余裕以上である。test は「stall 点に入った」ことを assert し、届かずに先に拒否されたら赤にする (運用条件 §1.5 の 32 の空振り禁止)。B の値は作業機で stall 点到達までの時間を完了ゲートの負荷の下で測って決める (M-8。`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 の教訓: 窓は `max_execution_ms / 5` の形 — ここで効いている予算は B なので、余裕は B/5)。
- (ii) の再送は budget を外して送る (digest が変わる)。従って「記録があれば `CONFLICT`、無ければ新規実行」で観測し、B の下での成功に依らない。
- 各 vector に positive control (十分な予算で同じ保持 → 完了し効果が残る) を組にする (`docs/design/CONFORMANCE_ADAPTER_V1.md:40` の規則)。
- **決定性の論法**: 拒否の方向は負荷に対して単調である — 放した時点で受理点からの経過が予算より長ければ、負荷はそれを更に長くするだけで短くしない。従って「放した後の拒否」は負荷で揺れない。**単調性が保証するのは放した後の拒否だけである。** stall 点への到達、(iii) の plan を得る dry run、(ii) の再送の成功は B の余裕に依る (成功の方向)。
- (ii) は既存の `hold_after_idempotency_lookup` (lock 保持・効果 0 件で止める)、(iii) は既存の `hold_after_plan_verification` で駆動できる見込み。(i) の点で止める primitive は port v1.21 に無く、port v1.22 の新 primitive (仮称 `hold_after_admission`。ABC + 6 plug) が要る。
- 観測: 応答だけでは「文を発行しなかった」と「1 ms で cancel された」を区別できない。primitive の handle が「放した後に要求のために発行された文の数」(D-2 の定義の文。要求が保持するすべての接続。pool 維持の文を除く手段は §6.4) を返す形を候補にする (台帳 R-79 の `execute_count` が接続ごとの文の数を既に数えている)。in-process 2 plug では文の数を観測できない (§6.4)。→ U-5。
- `limit_enforcement.execution_ms` による分岐は置かない (§6.2 の註)。
- C-05 の開示「execution_ms never driven」は新条件を指す形に書き換える (§6.5)。`security/CONTROL_MAPPING.md` に両 peer の「文発行前の拒否」「rollback」の claim を足す (実装 WP の仕事)。

**D-8 Security Invariants**: 新しい不変条件は足さない。適用は §7。

**D-9 実装の義務 (本書は列挙だけ。作業指示書は裁定後)**:
- r2db — 入口検査 (`postgres.py:1498`、`:1613`) を pool 取得の後へ**移す** (足すのではなく置き換える。検査点は 1 つになる)。apply_schema も同じ位置に 1 つ置く。pool 取得に期限の残りを渡し超過を `LIMIT_EXCEEDED` execution_ms に写す (→ U-6)。advisory lock 待ち後の再検査と再設定、operation loop・DDL・store の前 (pre_commit より前) の検査。`_timeout_ms` は残り 1 ms 未満で `LIMIT_EXCEEDED` を上げ、0 を返さない。`query` の SELECT 後の検査 (`postgres.py:1554`) は U-8 (a) なら外す。
- MitateDB — `request_scope` 入口 (pool 取得後) の検査、文の間の検査、`_retime` の閾値を D-2 に揃える、`_timeout_ms` を D-2 の形にする、transact の commit / `record_idempotency` の psycopg 例外の翻訳 (→ U-6)。`SET LOCAL` (`backend_postgres.py:493-500`) と `_retime` (`:544-552`) の `QueryCanceled` / `LockNotAvailable` を execution_ms に写す。schema 4 経路の cancel 分岐に `commit_failed` を足す (§1.4 #7)。schema 3 経路 (`backend_postgres.py:1058→1069→1070`、`:1204→1229→1230`、`:1372→1382→1383`。`:1204` 系は照合済み、他 2 つはレビューの報告。基点で未照合) の `_write_idempotency_row` を `pre_commit` の前へ移し、r2db (`postgres.py:1725→1733`、`:2416→2426`) と transact の順序 (store → pre_commit → COMMIT) に揃える。U-8 (b) なら read の SELECT 後に検査を足す。
- この `commit_failed` の欠けは R-42 と独立の audit 証跡の欠陥なので、台帳に起票する (R-N は作業機で採番)。
- 両 peer — 閾値を D-2 (残り < 1 ms) に揃える: `check_deadline` (r2db `limits.py:100` は `clock() > deadline`)、SQLite の `_check_deadline` (strict `>`)、r2db の in-memory backend。
- 両 peer — 変異: 各検査点を外すと新条件の対応 vector が赤になること (観測は D-7 の文の数。見込みは §6.6)。
- 共通条件で駆動しない検査点 — D-2 (b) lock 待ちの後、[U-8 (b)] (d) pre_commit の前、U-6 (a) の pool 待ち超過の写像、閾値 — は peer の単体テストで固定する (r2db は clock の注入、MitateDB は test 側での `time.monotonic` の差し替え。製品コードに hook は足さない)。義務 (a) (待ちを数え、受理点より遅く始めない) の証拠もこの単体テストと `security/CONTROL_MAPPING.md` の claim で取る (§6.4)。完了条件 → 変異の対応は作業指示書で確定する (運用条件 §1.5 の 40)。SQLite / in-memory backend は同じ意味論。

## 4. 却下した代替案

| ID | 代替案 | 却下の理由 |
|---|---|---|
| X-1 | 期限検査のための DB 往復 (`SELECT clock_timestamp()`、`SELECT now()`) | 決定軸に反する。process 内の単調時計で足りる (両 peer とも既にそうしている) |
| X-2 | 現行 (`max(1, …)` で 1 ms の文を発行) を維持し「境界では未定義」と文書化 | 予算を使い切った要求の結果が負荷で変わるのは SI-08 の Verification 句 (deterministic) に反し、利用者が再送の可否を決められない (残りが 1 ms 以上の帯は D-2 の範囲の外) |
| X-3 | 計測の始点を「最初の文」にして待ちを数えない | 利用者に見える所要時間が予算と無関係になり、pool・lock の保持が予算で bound されない。MitateDB の現行の読み (待ち超過 = 予算超過) とも逆行。U-1 の選択肢としては残す |
| X-4 | 待ちを別の limit class (例 `queue_ms`) にする | `limits.classes` の語彙に新語が要り (1.2.0 の規則)、利用者が 2 つの予算を推論する。安全の結果は増えない。U-1 の選択肢としては残す |
| X-5 | 文の途中の期限切れを `ATOMICITY_FAILED` で返す | 契約はこの code の意味を定義していない。両 peer の現物は `LIMIT_EXCEEDED` で、limit_class が原因を伝える |
| X-6 | PostgreSQL 17 の `transaction_timeout` を使う (transaction 全体の上限を 1 回で設定) | CI は `postgres:16`。作業機の版も未確認。将来の選択肢として M-2 に残す |
| X-7 | conformance のために製品コードに test 用 hook や clock 注入を足す (MitateDB には clock 注入が無い) | `docs/design/CONFORMANCE_ADAPTER_V1.md` の規律 (adapter の primitive で駆動し、製品コードに test 用 hook を足さない) に反する。stall primitive で実時間を経過させれば決定的に拒否側へ倒せる (D-7 の単調性) |
| X-8 | 新しい details key (`stage` / `executed` など) で「どこで予算が尽きたか」を返す | 既存の `futility` で足り、`details` の語彙を増やさない |

## 5. 未確定の選択肢 (依頼者裁定待ち。推奨は確定ではない)

**U-1 計測の始点と待ちの算入**
- (a) 受理点から、待ちをすべて数える (**推奨**。D-1)。
  - 利点: 実装が制御する所要時間を 1 つの予算で bound する。両 peer の現行の計算点のままで、新しい class が要らない。
  - 欠点: 認証・body 解析の時間は数えない (大きさは M-7)。pool・lock の待ちは他要求の負荷で伸びるので、同じ要求が負荷で拒否され得る (再送は D-3 で安全)。
- (b) 受信時から (認証・body の解析も数える)。
  - 利点: より厳しく、利用者に見える所要時間に最も近い。
  - 欠点: HTTP 層の実装に依る。(a) との差の大きさは未確認 (M-7)。
- (c) 最初の文から (待ちを数えない。X-3)。
  - 利点: 予算が文の実行だけを指し、待ちの長さで拒否されない。
  - 欠点: 利用者に見える所要時間が予算と無関係になり、pool・lock の保持が予算で bound されない。MitateDB の現行の読みと逆行する。
- (d) 待ちを別 class に分ける (X-4)。
  - 利点: 待ちと実行を別々に bound できる。
  - 欠点: `limits.classes` に新語が要る (1.2.0 の規則)。利用者が 2 つの予算を推論し、安全の結果は増えない。

**U-2 文の途中の期限切れの上限 (文の実行区間。区間外は D-5)**
- (a) 現行の形 + 文の間の時計検査 (上限 < 残りの 2 倍。往復を足さない。**推奨**)。
- (b) 文ごとに `SET LOCAL` を再設定 (上限 ≒ 残り。文ごとに 1 往復。費用は M-3 で測る)。
- (c) PostgreSQL 17 の `transaction_timeout` (X-6、M-2)。
- 契約文言は (a) でも成り立つ弱さにする (「文の途中で尽きた予算は実装の文の bound で打ち切られ、その bound は設定時の残りを超えない」)。

**U-3 再送可否の伝達** (v0.1 の推奨は (b)。v0.2 (2026-10-02) で (a) に移した — §11 RV-16)
- (a) D-3 の保証だけ (何も残らない → 再送は常に安全) (**推奨**)。
- (b) 加えて、文の実行で使い切ったときは `details.futility` を MAY で付ける (任意なので conformance は「付くなら SI-10 に適う内容」だけを見る)。欠点: 実装は「再送しても同じ」を知り得ない (文の所要時間は負荷と行 lock の待ちで変わる) ので、`futility` の文を真に書けない。
- (c) 必須の新 key (X-8、却下)。

**U-4 契約の版**
- (a) minor 1.15.0 + subordinate ruling 20 + obligations entry (**推奨**)。先例: 1.11.0 (拒否 code を変える義務)・1.12.0 が minor。本件は未定義の意味を埋めるものであり、文発行前の拒否の型は `structured_operations.idempotency.record` の「before it executes」に既にある。
- (b) major。既存の義務 1.7.0 (3) (dry run の拒否は real と同じ code と details) を execution_ms について狭めるので、この読みを強める。1.14.0 の自制「requires no implementation to refuse a request it accepted under 1.13.0」に照らすと、今 200 になり得る要求を拒否に変える。ただしその 200 は保証されていない偶然の結果である。
- (c) 版を上げず subordinate ruling の註だけ (義務を機械可読にできない)。

**U-5 conformance の範囲**
- (a) 新条件の (i)〜(iii) を全部、port v1.22 の新 primitive を含めて (**推奨**。(i) が台帳 R-42 の候補そのもの)。
- (b) 既存 primitive で駆動できる (ii)(iii) だけを先に、(i) は後続。
- (c) 観測の形: handle が「放した後に発行された文の数」を返す (**推奨**) / 応答 code だけ (変異の赤が確率的になる)。in-process の MitateDB SQLite plug には、SQLite の trace callback で文を数える代替がある (r2db の in-memory plug には文が無い)。

**U-6 pool 待ち超過・接続確立・commit 段の code**
- pool 待ち: (a) 予算を超えたら両 peer とも `LIMIT_EXCEEDED` execution_ms (**推奨**。MitateDB の現行は上限到達の `PoolExhausted` だけ。r2db は 503 から変える)。(b) r2db の現行 (503 `SERVICE_UNAVAILABLE`) を許す (peer で分かれる)。
- 接続確立の時間切れ・失敗: (a) 予算由来の connect timeout の超過は 413 execution_ms。(b) 503 のまま (MitateDB の現行 `PoolConnectFailed`、§1.4 #2)。
- commit 段: (a) 予算による cancel は commit 段でも `LIMIT_EXCEEDED` execution_ms (**推奨**。r2db の現行。MitateDB は 503 から変える)。(b) commit 段は `SERVICE_UNAVAILABLE` (MitateDB の現行)。
- commit が成立したかの判定は M-4 の結果に依る。

**U-7 閾値**
- (a) 残り < 1 ms (整数 ms で 0) で拒否 (**推奨**。D-2)。
- (b) 残り ≤ 0 で拒否し、0 < 残り < 1 ms は 1 ms で発行 (現行の `_retime`)。
- (c) 残り < 安全余裕 (例 5 ms) で拒否。利点: D-2 の範囲の外に残る「残り 1 ms 以上・文の所要時間未満」の帯 (負荷で 200 / 413) を狭める。欠点: 契約で数を決めることになる。

**U-8 最後の文が完了した後の時計検査**
- (a) 検査しない — 結果は要求自身の最後の文の完了で決まり、その後は時計で拒否しない。**(a) では D-2 (d) を置かない**: 最後の文の後は pre_commit → COMMIT と進み、COMMIT は最後に設定した文の bound でだけ打ち切られる (r2db は `postgres.py:1554` の検査を外す) (**推奨**: 文の bound で既に資源は bound されており、完了した仕事を捨てて利用者に何も返さないのは自由の損失)。
- (b) 検査する — (d) を置き、read は SELECT の後にも検査する。予算を wall-clock の上限として厳密に読む (r2db の現行。MitateDB は read の SELECT 後に検査を足す)。
- どちらも決定的 (境界の位置が違うだけ)。§9.1 の差し替えは [U-8 (a)] の印。

**U-9 `limits.execution_ms` の置き場**
- (a) `limits` の新 key `execution_ms` (per-class の key の先例 `enum_members`)。ただし `conformance-tests/test_contract.py:137-146`・`:180-184` の `_PRE_1_8_0_LIMITS_KEYS` は「新しい sibling key を置かない」を 1.8.0 の裁定として pin しており、pin の切り直しに依頼者確認が要る (**推奨**)。
- (b) `limits.profile` の文字列の中 (1.8.0 (2) の先例)。`limits.profile` は endswith の pin (`conformance-tests/test_contract.py:111-115`、`:177`) を持つ。1.8.0 の文より前に挿入すれば pin はそのまま、末尾なら切り直す。
- (c) `limits.request_budget` の末尾。`request_budget` の `PIN_1_7_0` は包含照合 (`:2267-2268`) なので、末尾追記なら pin はそのまま。

## 6. conformance への影響

### 6.1 現状 (基点 main)

- C-05 は「2 classes never driven -- `execution_ms`, `idempotency_retention_ms` (no deterministic construction / not enabled)」と開示する (`conformance-tests/CONDITIONS.md:34`、D-6.2/§7.3)。
- C-24 は execution_ms を駆動せず、宣言 unavailable の budget=1 → `CAPABILITY_UNSUPPORTED` と、配備値 + 1 → `VALIDATION_FAILED` だけを使う (`conformance-tests/test_c24_request_budget.py:40-41`)。
- port v1.21 の stall primitive (`conformance-tests/adapter.py`): `hold_in_flight` (`:1810`。plug 自身の catalog 読みを止める。budget も operation も指定できない)、`hold_after_idempotency_lookup` (`:1901`。caller が出す budget 付き mutation を idempotency 受理区間の末尾 = lock 保持・効果 0 件で止める。C-27 の primitive)、`hold_after_plan_verification` (`:1965`。schema 操作を DDL 前で止める)。clock の注入・期限を操る手段は port に無い。
- 6 adapter: in-process と http の各 plug は個別実装。socket 2 本は http plug の subclass で同一 process 内の cell を差し替えるので、stall は socket 越しでも効く (r2db socket は読解の報告で確認、MitateDB socket は未確認)。
- port の設計原則は `docs/design/CONFORMANCE_ADAPTER_V1.md` の §2 (negative test に positive control を組にする規則は `:40`)。port 拡張の規則 (新節 + ABC の `@abstractmethod` + 全 plug の実装 + 製品コードに test 用 hook を足さない) は同書 §25 (`:3461-3472`) の形。
- `security/CONTROL_MAPPING.md`: r2db `_set_timeouts` が execution_ms を `statement_timeout`/`lock_timeout` に写す second enforcement layer (`:659`)。MitateDB は期限を `SET LOCAL` に写し、pool・lock 待ちが期限を超えれば `LIMIT_EXCEEDED` execution_ms (`:852`、`:869-870`、`:1023`)。ただし現物では接続確立の経路は `PoolConnectFailed` → 503 で (§1.4 #2)、`:1023` の claim と合わない (レビューの報告。基点で未照合)。「文発行前の拒否」「1 ms」「rollback の保証」は claim されていない。

### 6.2 新条件の候補文 (候補。文言は契約の確定後に CONDITIONS.md の形で書く)

execution_ms を使い切った要求は決定的に終わる: (i) 受理点の後・最初の接続取得の前で予算を使い切った要求は、文を発行せず `LIMIT_EXCEEDED` + `details.limit_class: execution_ms` で終わる。(ii) 複数文の要求が文の間で予算を使い切ったら、次の文を発行せず同じ形で終わり、行も idempotency 記録も残らない (同じ idempotency_key で budget を外した再送は `CONFLICT` でなく新規として実行される)。(iii) schema 操作が DDL の前で予算を使い切ったら、DDL を発行せず同じ形で終わり、revision は動かない。各 vector は十分な予算の positive control と組にする。適用: SI-08、SI-11。

**註 (`limit_enforcement.execution_ms` による分岐)**: 新条件は `limit_enforcement.execution_ms` が `unavailable` の配備を `CAPABILITY_UNSUPPORTED` 側に分岐させない。ただし根拠は契約の `limits.finite_required` ではない — `limits.finite_required` (`spec/data-service-api.v1.json:927`) は真偽値 `true` だけで class ごとの必須を述べず、capability document の `limit_enforcement` の schema (`:1351-1360`) はどの class にも `unavailable` を許す。execution_ms を `unavailable` にしないことは C-05 V3 (固定 9 class。`conformance-tests/test_c05_limit_declaration_agreement.py:78-82` の `_FIXED_NINE`、検査は `:1258`。出所はフェーズ7 設計 D-6.1 の裁定 S-2) が conformance で固定している。従って新条件は C-05 V3 を前提とし、`unavailable` の配備は C-05 V3 で赤になる。C-24 の unavailable 分岐は `request_budget` capability のもので、1.9.0 以上を宣言する実装は `request_budget` を unavailable にしない (`versioning.version_binding` の 1.9.0 の段落) ので、新条件には現れない。

### 6.3 3 vector

| vector | 止める primitive | 止める要求と保持 | 観測 | positive control |
|---|---|---|---|---|
| (i) 受理点の後・最初の接続取得の前 | port v1.22 の新 primitive (仮称 `hold_after_admission`) | `budget.execution_ms = 1` の要求。保持は例 100 ms | code・limit_class、放した後の文の数 = 0 (U-5 (c)) | 十分な予算で同じ保持 → 完了し効果が残る |
| (ii) 文の間 | `hold_after_idempotency_lookup` (既存) | `budget.execution_ms = B` の idempotency_key 付き mutation。保持は「stall 点に入った」合図から B + 余裕 | 「stall 点に入った」こと、code・limit_class、行が残らないこと、budget を外した同 key の再送が `CONFLICT` でなく新規実行になること、文の数 | 同上 |
| (iii) DDL の前 | `hold_after_plan_verification` (既存) | `budget.execution_ms = B` の plan 付き schema 操作。保持は「stall 点に入った」合図から B + 余裕 | 「stall 点に入った」こと、code・limit_class、revision が動かないこと、文の数 | 同上 |

- B と余裕・保持の測り方は D-7。決定性の論法は D-7 の単調性 (保証は放した後の拒否だけ)。B の決定と実証は M-8。
- 費用の見積もり: 1 plug あたり (i) 0.1 s ×2 (positive control 込み) + (ii)(iii) 1.2B ×2 ×2 ≒ 0.2 + 4.8B s、6 plug で 6 × (0.2 + 4.8B) s (直列。例 B = 0.5 s なら約 16 s)。保持は budget で選ぶ B に比例し、配備の execution_ms (既定 5000) には比例しないので、運用条件 §1.6 の 44 (構成値に比例しない形) に反しない。

### 6.4 port v1.22 の候補

- 新 primitive (仮称 `hold_after_admission`): caller が出す budget 付き要求を、契約の点で「rate・concurrency・budget の bound が確定した後、最初の接続取得の前」で止める。ABC の `@abstractmethod` + 6 plug の実装 + `docs/design/CONFORMANCE_ADAPTER_V1.md` の新節。製品コードに test 用 hook を足さない (X-7)。
- handle の候補: 放した後に plug の backend が発行した文の数を返す (台帳 R-79 の `execute_count`。両 peer の `psycopg_counting.py`)。観測は「放した後に要求のために発行された文が 0 件」と定義する (D-2 の定義の文。要求が保持するすべての接続)。`execute_count` は pool 維持の文 (r2db の checkout ごとの `SELECT 1`、新規接続の `SET search_path`) も数えるので、それを除く手段は port の設計で決める。候補: 計数 cursor が文の本文を記録して pool 維持の文を除く / 計測前に pool を warm にして新規接続を無くす。いずれも製品コードに test 用 hook を足さない (X-7) 形に限る。既存の 2 primitive の handle にも同じ値を持たせるかは U-5 の裁定に従う。
- 既存 2 primitive (`hold_after_idempotency_lookup`、`hold_after_plan_verification`) の逐語 docstring は「放した後に実行・記録・commit まで進む」と約束している (例 `hold_after_idempotency_lookup`:「`with` を抜けると先着は解放され、実行・記録・commit まで進む。」、レビューの報告。基点で未照合)。vector (ii)(iii) はこれを拒否の駆動に使うので、docstring の改訂 (確定文の経路、運用条件 §1.5 の 35) を port v1.22 に含める。
- plug ごとの観測:

| plug | backend | 文の数 | 新条件で見るもの |
|---|---|---|---|
| r2db in-process | in-memory `structured.ApplicationCell` (文が無い。`r2db-api/conformance/conformance_adapter_r2db.py:394`、レビューの報告。基点で未照合) | 対象外 (常に 0) | code・limit_class だけ |
| MitateDB in-process | SQLite (psycopg を通らない) | 対象外 (代替は SQLite の trace callback、U-5 (c)) | code・limit_class だけ |
| r2db-http / r2db-socket | PostgreSQL | `execute_count` | code・limit_class・文の数 |
| MitateDB-http / MitateDB-socket | PostgreSQL | `execute_count` | code・limit_class・文の数 |

- 義務 (a) (待ちを数え、受理点より遅く始めない) の証拠は conformance では取れない。証拠は `security/CONTROL_MAPPING.md` の claim と peer の単体テスト (r2db は clock 注入、MitateDB は test 側の `time.monotonic` 差し替え。D-9)。

### 6.5 書き換える既存の記述

- C-05 の Disclosed scope limits (1) の `execution_ms` を「never driven」から「新条件で駆動」を指す形に改める。`idempotency_retention_ms` の開示はそのまま。
- 同じ形に改める: C-24 の行 (`conformance-tests/CONDITIONS.md:53`) の「`execution_ms` is not driven at all」、`conformance-tests/test_c24_request_budget.py:40-41` の同文、`security/CONTROL_MAPPING.md:1141` の「never driven by this suite」。
- `security/CONTROL_MAPPING.md` の書き換え対象 (いずれもレビューの報告。基点で未照合): `:659` (「per transaction」の記述。lock 待ち後の再設定と D-2 の検査に合わせる)、`:852` (引く行番号 `backend_postgres.py:1687-1696` が古い。現物の `_timeout_ms` は `:1681-1685`)、`:870`、`:1023` (接続確立の経路は現物では 503。U-6 の裁定に合わせる)。
- CONDITIONS の行を変えるときは、`conformance-tests/CONDITIONS.md` 冒頭の Update convention どおり、現行行を書き換え、旧文を `conformance-tests/CONDITIONS_HISTORY.md` の該当 ID の節へ逐語で移す。

### 6.6 変異の対応の見込み (運用条件 §1.5 の 40。表は作業指示書で確定する)

| 変異 (両 peer) | (i) | (ii) | (iii) | peer の単体テスト (D-9) |
|---|---|---|---|---|
| D-2 (a) = `_timeout_ms` の拒否を外す (0 を返す)。r2db は入口検査をここへ移すので検査点は 1 つ。apply_schema も同じ | 赤 (文の数で観測) | 届かない (検査が先にある) | 届かない | 赤 |
| D-2 (c) 文と文の間の検査を外す | — | 赤 | — | — |
| DDL 前の検査を外す | — | — | 赤 | — |
| 検査の閾値を `<= 0` に戻す | — | — | — | 赤 |
| D-2 (b) lock 待ちの後の検査を外す | — | — | — | 赤 |
| [U-8 (b)] D-2 (d) pre_commit の前の検査を外す | — | — | — | 赤 |
| MitateDB schema 3 経路の順序を戻す (pre_commit の後に idempotency を書く。D-9) | — | — | — | 赤 |
| pool 待ち超過の写像を外す (U-6 (a) のとき) | — | — | — | 赤 |

- in-process 2 plug では、単一の検査点の変異は後段の検査が同じ code で拒否するので観測できない。殺すのは PG plug の文の数と peer 単体テスト (§6.4 の表)。

## 7. Security Invariants との関係

新しい不変条件は足さない (§2、`CLAUDE.md`)。

`security/THREAT_MODEL_V1.md` (:100-138) との関係: T-07 (資源枯渇。connections を含む) — execution_ms が pool・lock の待ちを含めて 1 要求の保持を bound する (D-1、D-5)。T-08 (エラーによる情報開示) — `futility` を付けるなら内部情報を含めない (U-3 (b)、SI-10)。T-09 (並行・部分失敗による不整合) — 打ち切られた要求が行・idempotency 記録を残さない (D-3、新条件 (ii)(iii))。T-14 (security evidence の欠落) — MitateDB schema 操作の `commit_failed` の欠け (D-9 の起票)。

| SI | 関係 |
|---|---|
| SI-08 | Verification 句の「deterministic rejection or termination」を execution_ms について初めて検証可能にする (新条件)。C-05 の文「over-bound requests terminate deterministically」の execution_ms の欠けを埋める |
| SI-11 | 打ち切りが部分状態を残さない。既存の atomic の検証に期限切れの vector が加わる (新条件の (ii)(iii)) |
| SI-10 | `futility` を付けるなら (U-3 (b))、その文は内部情報を含めない。SQL・lock 名・pool の寸法を書かない |
| SI-14 | `LIMIT_EXCEEDED` は耐久 denial ではない。変更なし。MitateDB schema 操作の `commit_failed` の欠け (D-9) は別件として起票する |
| SI-15 | 関係なし (認可の fail-closed ではない) |

## 8. 作業機で測る項目 (cloud では測らない)

| ID | 項目 | 効く先 |
|---|---|---|
| M-1 | 1 ms 経路の再現 (両 peer): `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 の plugin 法 (`_set_timeouts` の記録) を r2db にも当て、§1.5 の各経路で `timeout_ms == 1` が出ることを修正前に記録する。MitateDB では 200 / 413 / 503 に分かれること、`SET` 自体が 1 ms で cancel され得るかも記録する | §1.5、D-2、D-9 |
| M-2 | 作業機と配備の PostgreSQL の版。17 以上なら `transaction_timeout` の可否 | X-6、U-2 (c) |
| M-3 | 文ごとの `SET LOCAL` 再設定の費用: `tools/perf_baseline.py --roundtrip` (台帳 R-80) で K=1 と K=32、6 plug | U-2 (b) |
| M-4 | 検証用 DB で COMMIT 自体を遅くする構成 (deferred constraint trigger に `pg_sleep` を置く等) で、`statement_timeout` が COMMIT を cancel したとき transaction が commit 済みになり得るかを PostgreSQL の文書と実測で確かめる | D-3 の commit 段、§9.1 の【保留】、U-6 |
| M-5 | 台帳 R-102 後の MitateDB の advisory lock 待ちと pool 待ちの分布 (台帳 R-78 の値は cell lock 廃止前)。既定 5000 ms に対する余裕の確認 | D-1、U-1 |
| M-6 | advisory lock の `lock_timeout` 超過の SQLSTATE (55P03 `lock_not_available` か 57014 `query_canceled` か)。両 peer は両方を捕まえているが、記録として 1 回確かめる | §1.3 の 8、§1.4 の 4 |
| M-7 | 受信から受理点までの時間 (認証・body 解析) の実測 | U-1 (a) と (b) の差 |
| M-8 | 新条件の駆動の確認。(i): `budget.execution_ms = 1`、保持 100 ms で、完了ゲートの負荷の下でも 6 plug すべてで拒否が 100/100 になること。(ii)(iii): 完了ゲートの負荷の下で受理点から stall 点到達までの時間と、(iii) の plan を得る dry run が B の下で完了する時間を 6 plug で測り、B を決める (余裕は B/5 の形)。その B で、stall 点到達と拒否が 6 plug すべてで 100/100 になること。positive control も同じ回数 | D-7 の B と単調性の実証 |

## 9. 契約文言の候補

**以下は候補である。依頼者が確定するまで逐語 pin を置かない** (運用条件 §1.5 の 35)。確定文は scratchpad の確定文ファイルから複製する。`[U-N (x)]` は未確定の選択肢ごとの差し替え箇所を示す。

### 9.1 execution_ms の節 (置き場は U-9。推奨 (a) は `limits.execution_ms` の新 key)

> execution_ms bounds one request's own wall-clock time. The bound starts no later than the point at which the request has passed this deployment's request-rate and concurrency bounds and the bound in force for it is fixed; an implementation may start it earlier, never later. Everything between that point and the point at which the request's outcome is decided counts against it: waiting for a database connection, waiting for a lock, executing statements and committing. Each request is bounded on its own: each page of a query is one request with its own bound, and a dry run is bounded exactly as the request it previews, because it executes statements as well. A dry run's own execution_ms refusal does not predict the real request's: the two issue different statements.

- [U-1 (b)] 始点の文を「The bound starts when the request is received, before its authentication and body are processed.」に差し替える。
- [U-1 (c)] 始点の文を「The bound starts when the request issues its first statement; waiting for a database connection or a lock before that is not counted.」に差し替え、待ちの列挙から connection と lock を除く。
- [U-1 (d)] 待ちを `limits.classes` の新しい class で bound する別の文になる (本節の文は実行だけを指す)。
- [U-8 (a)] 「executing statements and committing」の列挙はそのまま (COMMIT は文の bound で bound される)。追記: 「After its last statement has completed, it is not refused for execution_ms by a clock check; its commit remains bounded by the implementation's statement bound.」[U-8 (b)] はそのまま (最後の文の後も予算の内)。

> A statement here is one the implementation issues from the request's content on any connection it holds for the request -- each of the request's own transactions, the implicit begin of each included -- including setting the request's own bounds, reading the catalog, taking locks, reading or writing idempotency records, and the request's own data and schema changes; maintaining a connection pool, the commit or rollback that ends the transaction, and audit recording on a separate connection are not. A request whose execution_ms is exhausted is refused with LIMIT_EXCEEDED and details.limit_class: execution_ms before it issues its next statement, rather than issuing that statement under a bound too short for it to complete. A remaining bound shorter than one millisecond is exhausted. A statement already executing when the bound is exhausted is terminated by the implementation's own per-statement bound, which never exceeds what remained of execution_ms when that bound was set. A request refused or terminated this way before it commits leaves no row, no catalog entry, no schema revision and no idempotency record. This sentence does not govern audit evidence; transactions.atomic and structured_operations.dry_run.external_effects are unchanged.

- [U-7 (b)] 「A remaining bound shorter than one millisecond is exhausted.」を「A remaining bound of zero or less is exhausted.」に差し替える。[U-7 (c)] は数を契約で定める文になる。
- [U-2 (b)] 「which never exceeds what remained of execution_ms when that bound was set」を「which is set again before every statement from what then remains of execution_ms」に差し替える。
- [U-6 (a)] 追記: 「Waiting for a database connection beyond the bound, or failing to establish one within it, is refused in the same way.」(接続確立の部分は U-6 の接続確立の行に依る)。
- [U-3 (b)] 追記: 「Where the bound was spent executing the request's own statements rather than waiting, the denial may carry details.futility.」
- 【保留 — M-4 の結果まで基本文に入れない】commit 段: 「A commit the bound terminates is refused in the same way [U-6 commit (a)].」と、そのときに何が残るかの文。

### 9.2 `versioning.version_binding` に足す段落 ([U-4 (a)]。置き場は 1.14.0 の段落の直後・version-flip 文の前)

> Only an implementation declaring 1.15.0 or higher additionally claims conformance to the obligations 1.15.0 introduces (subordinate ruling 20). Those obligations are unconditional in the same sense as every obligation enumerated above -- they bind simply by declaring 1.15.0, independent of any capability's own status: (a) execution_ms counts every wait and statement from no later than the point limits.execution_ms names; (b) a request whose execution_ms is exhausted is refused with LIMIT_EXCEEDED and details.limit_class: execution_ms before it issues its next statement; and (c) a request refused before commit, or terminated before commit, for exhausting execution_ms leaves no row, no catalog entry, no schema revision and no idempotency record. What else 1.15.0 adds -- limits.execution_ms and the sentence it rewrites in ... -- holds an implementation to no behavior beyond these three. 1.15.0 newly requires refusing a request whose execution_ms is exhausted; such a request was never guaranteed to succeed under 1.14.0. 1.7.0's obligation (3) -- the same code and the same details on a refusal a dry run receives -- does not extend to an execution_ms refusal, because a dry run and the real request issue different statements. An implementation still declaring 1.14.0 is not held to any 1.15.0-only obligation retroactively.

- [U-9 (b)] 「the point limits.execution_ms names」を「the point limits.profile names for execution_ms」に、「What else 1.15.0 adds -- limits.execution_ms」の `limits.execution_ms` を「what it adds to limits.profile」に差し替える。[U-9 (c)] 同じ 2 箇所の名指しを `limits.request_budget` に差し替える。
- 「the sentence it rewrites in ...」の対象は U-9 の選択で決まる ((a) なら書き換える既存の文は無く、この句を落とす。(b) は `limits.profile`、(c) は `limits.request_budget`)。
- [U-1 (b)] (a) を「execution_ms counts every wait and statement from the request's receipt」に。[U-1 (c)] (a) を「execution_ms counts every statement from the request's first statement; waits are not counted」に。[U-1 (d)] (a) を、待ちを bound する新しい class の義務に置き換える。
- [U-7 (b)] (b) の「exhausted」を「whose remaining execution_ms is zero or less」と読む文に。
- [U-8 (a)] (b) の末尾に「; after its last statement has completed, it is not refused for execution_ms by a clock check; its commit remains bounded by the implementation's statement bound」。[U-8 (b)] (b) の末尾に「; and a request whose execution_ms is exhausted when its last statement completes is refused the same way」。
- [U-4 (b)] major 版の段落になり、本段落の形は使わない。[U-4 (c)] 本段落を置かず subordinate ruling の註だけにする。

### 9.3 `versioning.obligations[]` に足す entry ([U-4 (a)]。識別子は候補)

```json
{
  "version": "1.15.0",
  "subordinate_ruling": 20,
  "unconditional": [
    "execution_ms_counts_waits_from_admission",
    "exhausted_execution_ms_refused_before_next_statement",
    "execution_ms_refusal_before_commit_leaves_no_state"
  ],
  "conditional": []
}
```

- [U-1 (b)] 1 つ目を `execution_ms_counts_waits_from_receipt` に。[U-1 (c)] `execution_ms_counts_statements_from_first_statement` に。[U-1 (d)] 待ちを bound する新しい class の識別子に置き換える。
- [U-7] 識別子は変えない (閾値は散文の側)。
- [U-8 (b)] `exhausted_execution_ms_refused_after_last_statement` を足し、散文 (§9.2) の個数を four にする。
- 散文 (§9.2) の無条件義務の個数 (three) と entry の個数を一致させる (`versioning.obligations_note`)。

### 9.4 `structured_operations.dry_run.decision` に足す相互参照 ([U-4 (a)]。末尾追記。包含 pin なので壊れない)

> An execution_ms refusal is the exception: a dry run and the real request issue different statements, so neither one's execution_ms refusal predicts the other's (limits.execution_ms).

- [U-9 (b)/(c)] 括弧内の参照先を `limits.profile` / `limits.request_budget` に差し替える。

## 10. 依頼者裁定

裁定待ち (U-1〜U-9)。

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
