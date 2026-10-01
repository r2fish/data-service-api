# MitateDB のデータ面の application 単位の直列化 設計文書 (v0.6)

## 0. 版数・位置づけ

- 版: **v0.7 (2026-10-01) 実装後の註のみ** (§13)。決定 D-1〜D-8 と §11.1 は書き換えていない。註は該当行の末尾に【v0.6 註】で置いた。
- 版: **v0.5 (2026-09-30) 依頼者裁定済み (§11.1)。設計は確定**。設計レビュー 1 回目 (A / B 並行) と再確認を経た。作業指示書は R-115 の merge 後の main に対して書く (Q-7)。履歴は §13。
- 台帳: 計画文書 `RM` §8 の **R-102** (`RM`:459)。規模 L。設計レビューが着手条件 (同行)。G-4 の終了条件の 1 つ (`RM`:40)。
- 基点: worktree の HEAD `173371d` (`6a1d893` からの差は引き継ぎ書のみ。src の行番号は変わらない)。本書の file:line はこの木の現物である。
- 契約: 1.12.0 のまま (見込み。§9)。変更クラス: 実装は **Class D** の見込み (§9。依頼者確認事項、§11)。本書自身は文書のみ。
- 略記 (本書ローカル): `M/` = `MitateDB-api/src/mitatedb_api/`、`R/` = `r2db-api/src/r2db_api/`、`MT/` = `MitateDB-api/tests/`、`CM` = `security/CONTROL_MAPPING.md`、`COND` = `conformance-tests/CONDITIONS.md`。出所の記法は `docs/work-orders/OPERATING_CONDITIONS.md` §0。
- 本書ローカルの ID: 決定 D-1〜D-8、問い Q-1〜Q-9、候補 (甲)〜(戊)、計測規則 D-R102、lock の段 1・2・3a・3b・4・5 (D-3 の順序表)、事実ラベル 守1〜守4 (lock が守るもの)・穴1 (lock の穴)・既1〜既6 (PostgreSQL が既に保証)・開1〜開4 (process 間で開いている)、監督裁定 J-1〜J-8 (v0.2 の反映元) と K-1〜K-16 (v0.3 の反映元、レビュー反映) と L-1〜L-9 (v0.4 の反映元、再確認の反映)。本文の該当箇所に「(J-N)」「(K-N)」「(L-N)」で示す。他文書の同形 ID には文書名を添える (同 §1.8 の 59)。
- 公開規律: 実 DSN・実ホスト名・作業機の絶対パスを置かない (同 §1.9)。材料は監督の調査 (2026-09-30) と起草時の現物読み。

**依頼者裁定 (逐語、2026-09-30)**

監督の提案「2 = R-102 の設計 (設計文書だけなら src に触れない。G-4 の終了条件で、設計レビューが着手条件)」に対し:
「1と2を別セッションで、R-46はDで進めてください」
(「1」と「D」は別件 R-46 で、別チャットで進む。)

## 1. 問題設定と出所

MitateDB-api のデータ面は、application 単位の in-process lock (`ApplicationCell._lock`、`M/cell.py`:645、`_CountingRLock` は :508-603) と、cell ごとの持続接続 2 本 (`PostgresBackend._runtime` / `_developer`、`M/backend_postgres.py`:294-295) で要求を直列化する。実測 (R-78、thread limit 既定 40 の時代) で K=4 の acquire の約 28〜29% が待ち (§2.7)。`RM` §0.1.4 の 3 (K=4 で waits/acquire 10% 以下) が G-4 の終了条件の 1 つである。R-113 で multi-process になり、lock は process ごとに別 instance である。

`RM`:459 の「R-79〜R-82 の結果を見てから着手するかを決める」は起票時の監督裁定であり、本設計の着手は依頼者指示 2026-09-30 (§0) による (K-14)。

| 事項 | 出所 |
|---|---|
| 台帳 | `RM`:459 (R-102)、:458 (R-101)、:461 (R-107)、:460 (R-106)、:463 (R-115)、:453 (R-52)、:454 (R-80)、:455 (R-81)、:456 (R-82) |
| 終了条件と閾値 | `RM`:40 (G-4)、:66 (§0.1.4 の 3)、:64 (同 1)、:65 (同 2)、:67 (同 4) |
| 実測 | `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` §2.1・§2.2・§3 の 4、`docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` §3 の 8・§4、`docs/design/MULTI_PROCESS_WORKER_V0_1.md` §7.4 表 7-1 |
| multi-process の前提 | `docs/design/MULTI_PROCESS_WORKER_V0_1.md` §1.1 の枠 (:26。R-102 を混ぜないと明記。同行の「process 間は tx 隔離と LOCK TABLE が担う」は §2.5 のとおり開1〜開4 について成り立たない) |

## 2. 事実

### 2.1 lock の形 【監督再確認済み】

| 事実 | 出所 |
|---|---|
| lock は cell に 1 個。public メソッドは `_require_*` → gate (`_gate` / `_limit_gate`: rate・concurrency slot) → 外側 `with self._lock:` の順で、lookup → pass 1 (検証・catalog 読み・idempotency check) → pass 2 (execute・commit) を通しで囲む | 経緯コメント `M/cell.py`:646-685。例: `read_page` :2309-2310、`alter_field` :1885-1886、`transact` :2935-2936 |
| 内側の `with self._lock:` は RLock の再入 | `M/cell.py`:2354 (read_page)、:3130 (transact)、:2151 (`_schema_revision_uncounted`) |
| `transact` は commit 後の監査 (`__record` / `_push_data_operation_event`) まで lock の内側 | `M/cell.py`:3337、:3346 |
| cell と backend は `build_app()` が served application ごとに eager に 1 組作る。`app = build_app()` は module import 時に走り、uvicorn の子 process ごとに import し直す | `M/main.py`:573-613、:733。`docs/design/MULTI_PROCESS_WORKER_V0_1.md` §1.3 (uvicorn は `spawn`) |
| cell.py・backend_postgres.py に cache は無い。catalog・revision は毎回 SELECT し、developer 接続で commit する | `grep -i cache` は comment 1 件のみ。`M/backend_postgres.py`:518-(`field_types`)、:921-936 (`schema_revision`) |

### 2.2 lock が守っているもの (process 内のみ)

| ラベル | 内容 | 出所 |
|---|---|---|
| 守1 | 持続接続 2 本の transaction 状態の非共有。メソッドをまたぐ状態: transact の `begin` → `*_in_transaction` → `commit`、idempotency の begin → unlock、session advisory lock 2 種、`SET LOCAL` の timeout。lock なしでは、ある要求の commit / rollback が別要求の transaction に着弾する | `M/cell.py`:654-660 (実測の記録)。`begin` は先頭で `self._runtime.rollback()` (`M/backend_postgres.py`:1609)、unlock は先頭で `conn.rollback()` (:1939) |
| 守2 | pass 1 (catalog・制約・revision の読み = 別 transaction、多くは `_developer`) と pass 2 (書き込み) の間に、同じ process の同じ application の他要求が入らない (check-then-act の直列化) | `M/cell.py`:646-660 |
| 守3 | 同一接続上では session advisory lock が再入になり排他にならない [PostgreSQL 一般、repo では未確認] ので、同一 process の同一 key の競合は cell lock が直列化している | `M/cell.py`:1155-1165。`COND`:56 (C-27 の MitateDB 2 plug の変異は「cell の RLock を外す」) |
| 守4 | SQLiteBackend (in-process plug の既定 backend) は単一 `:memory:` 接続 + dict の状態で、cell lock の直列化を前提にする | `M/backend_sqlite.py`:88、:748 (lookup → 実行 → store の窓全体を cell lock が覆うので advisory lock 相当は要らない、と明記)、`M/cell.py`:623 |

### 2.3 lock の穴 (現行、process 内) 【監督再確認済み】

| ラベル | 内容 | 出所 |
|---|---|---|
| 穴1 | `read_page` は lock と gate を出た後に `_decode_rows` → `backend.field_types` を呼び、`_developer` 接続で SELECT と commit / rollback を行う。同じ process で同じ application の schema 操作が `_developer` 上の transaction の途中にあるとき、この commit がそこに着弾しうる (守1 の記録と同じ形)。事実は構造のみ。再現は未実施、実害は未計測 | `M/cell.py`:2357、:3407。`M/backend_postgres.py`:518-555 |

### 2.4 PostgreSQL 側が既に保証しているもの (process をまたいで成立)

| ラベル | 内容 | 出所 |
|---|---|---|
| 既1 | 1 要求の原子性: DML / batch は runtime 接続の 1 transaction、schema 操作は developer 接続の 1 transaction (DDL・registry・revision 加算・idempotency 行を同一 commit) | `M/backend_postgres.py`:1605-1624、:946-1089、:740-918 |
| 既2 | 同一 key の idempotency: per-key の session `pg_advisory_lock(76176100, hashtext(key))` と件数 lock `pg_advisory_lock(761761762)`。別接続 (別 process・別 cell) 間で成立 | `M/backend_postgres.py`:1794-1795、:1884、:1941-1943。`MT/test_idempotency_concurrency.py`:228 (`_pg_pair`、独立 2 cell)、:253・:298・:347 |
| 既3 | revision の加算: 単一行の `UPDATE revision = revision + 1`。行 lock で直列化 | `M/backend_postgres.py`:938-940 |
| 既4 | schema 操作の表 lock: `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE` (alter の走査、nullable:false の add_field) | `M/backend_postgres.py`:818、:1152。`MT/test_constraints_declaration.py`:1422 |
| 既5 | application の隔離 (SI-01) の MitateDB での実現: application ごとの database / role / DSN。cell lock は寄与しない | `MitateDB-api/migrations/0003_provision_application.sql`:77-79 |
| 既6 | rate (platform DB の行) と concurrency (host 共有の slot) は cell lock から独立 (slot は lock の外側で取る) | `M/cell.py`:676-685、`M/main.py`:567-571 |

### 2.5 R-113 以降、process 間では何も保証していないもの

いずれも再現は未実施。構造からの帰結である。`docs/design/MULTI_PROCESS_WORKER_V0_1.md`:26 の「process 間の同時実行は PostgreSQL の tx 隔離と LOCK TABLE が担う」は、以下の開1〜開4 については成り立たない (構造のみ、未再現。K-15)。

| ラベル | 内容 | 出所 |
|---|---|---|
| 開1 | plan token の check-then-act 【監督再確認済み】: `current_revision` は別 transaction で読み (`schema_revision()` は読んで commit)、DDL の transaction は revision を再確認しない。別 process の schema 操作が間に入ると、古い revision に対する plan が適用される | `M/cell.py`:1466-1484、:2125-2152。`M/backend_postgres.py`:921-936 |
| 開2 | alter 同士の lost update: `alter_field_constraints` は registry 行を `LOCK TABLE` の前に読み (`FOR UPDATE` 無し)、後で enum / nullable の両方を UPDATE する 【読み取り順は監督再確認済み。lost update の成立は未再現】 | `M/backend_postgres.py`:765-767 (SELECT)、:818 (LOCK)、:850-852 (UPDATE) |
| 開3 | pass 1 の検証 (enum / nullable は DB の制約ではなく registry を読んで Python で検証) と pass 2 の DML の間に別 process の alter が commit しうる。新しい制約に反する行が入りうる | 列定義は型のみ (`M/backend_postgres.py`:1096-1098、`M/postgres_types.py`:23-25)。検証は `M/cell.py`:3638 (`check_declared_value`) |
| 開4 | `create_collection` の `schema_count() >= max_schema_objects` の確認も check-then-act。`schema_count` は developer 接続で数えて自己 commit する。別 process の create が間に入ると上限を超えうる (構造のみ、未再現)。MitateDB は `schema_objects` を無条件に `enforced` と宣言し、`CM`:716 は「要求単位なのでどの ceiling でも enforced」と分類する。開4 が成り立てば process 数 > 1 でこの宣言 (SI-08) は偽になる。契約 1.8.0 の無条件の義務 (`spec/data-service-api.v1.json`:37: limit_enforcement は server process 1 つではなく deployment 全体を述べ、同時に serve しうる全 process で上限が成り立つときだけ `enforced` と宣言し、process ごとにしか成り立たず複数 process が serve しうるなら `deployment_required` と宣言する) にも、process 数 > 1 で現に合わない (構造のみ、未再現。超過は上限際で並行した create の数だけ。L-3)。3a の後・同 transaction で数えるので閉じる (J-5、K-1、K-7)。閉じるまでの扱いは Q-4 | `M/cell.py`:1266。`M/backend_postgres.py`:420-437。`M/capabilities_document.py`:325 |

### 2.6 r2db-api 側 (対照)

- application 単位の in-process lock は無い。接続は要求ごとに (application, role) の pool から借り、1 要求 = 1 `conn.transaction()` (`R/postgres.py`:904 `_PoolHandle`、:1007-1008、:1623 transact、:2089-2092 apply_schema)。pool は返却前に rollback する (:679)。idempotency は `pg_advisory_xact_lock` (:1381、:1401)。
- plan の revision は DDL と同じ transaction の中で読む (`R/postgres.py`:2138)。
- **構造上開いている見込み、未再現** (J-7、K-7): idempotency key が同一でない任意の 2 つの schema 操作 (unkeyed、または異なる key の keyed。per-key lock は同一 key しか直列にしない) について、次の 3 つの check-then-act が開いている。isolation の明示設定は見当たらない (READ COMMITTED の見込み)。application 単位の lock が無いので 1 process 内でも同じ → Q-5。
  - plan: 2 つの schema 操作が同じ revision を読んで両方通る。読みは素の `SELECT` (`R/postgres.py`:2583-2598、`FOR UPDATE` 無し)、加算は :2387 (`_bump_revision`)、表 lock (:2242、:2307) は読みの後。`_load_catalog` (:1126-) に lock は無い。
  - 確認句: `drop_entity` / `drop_index` の確認句も同じ素の読みを使う (:2206、:2351)。並行する schema 操作が revision を進めた後に古い確認句で破壊操作が通りうる (SI-09、C-06)。
  - `schema_objects`: `_load_catalog` (:2094) の後に lock 無しで上限を検査する (:2151-2172)。r2db も `schema_objects` を `enforced` と宣言する (`CM`:716) ので、1 process 内から `spec/data-service-api.v1.json`:37 の義務に合わない (§2.5 開4 と同じ。構造のみ、未再現。L-3)。

### 2.7 実測 (既存。新しい計測はしない)

| 出所 | 値 |
|---|---|
| R-78 (`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` §2.1 / §2.2、MitateDB-http、thread limit 既定 40) | cell lock の waits/acquire: K=4 985/3530・1019/3530 (約 28〜29%)、K=32 2058/4618・2022/4618 (約 44〜45%)、wait_max 最大 67.056 ms。acquire は RLock の再入も数える (query 1 要求で外側 + 内側の 2 回、`MT/test_r78_pool_wait_stats.py`:138) ので、「要求のうち待った割合」は waits/acquire より大きい |
| R-101 (`docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` §3 の 8、§4) | K=32 の waits/acquire 0.471 (http) / 0.469 (socket)。4 plug とも R-101 設計 (`docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md`) の J-2 (GIL) が成立、MitateDB 2 plug は同 J-5 も成立、同 J-3 (DB 往復の待ち) は不成立 |
| R-113 (`docs/design/MULTI_PROCESS_WORKER_V0_1.md` §7.4 表 7-1、real-server、thread limit 4) | `query` p50 (ms)。N=1 K=32: r2db 39.499 / 38.908、MitateDB 38.907 / 39.000。N=4 K=32: r2db 24.917 / 26.614、MitateDB 24.653 / 24.005 |
| 現行の既定 (thread limit 4) | cell lock の waits/acquire は**未計測** |

### 2.8 起草時に現物で確かめた補足 (D-2・D-3・D-6 の前提)

| 事実 | 出所 |
|---|---|
| `BoundedConnectionPool` の利用者は platform pool の 1 箇所 | `M/main.py`:390、:533 |
| 同 pool の取得待ちは固定の `acquire_timeout` 5.0 s。枯渇時は `AuthorizationStateUnavailable` ("platform registry connection pool exhausted") を投げる。接続失敗も同じ例外 ("authorization state unavailable")。`release` は rollback せずに idle へ戻す | `M/pool.py`:115、:307、:311-321、:334-340 |
| platform pool の唯一の借用点は、release の前に rollback し、rollback や本体が `psycopg.Error` で失敗したときは `discard` する | `M/credential_store_postgres.py`:401-418 |
| `role_pool_size(thread_limit)` = thread_limit + 2。docstring は「本 peer のデータ面は pool しない (cell lock で直列化)」と書く | `M/config.py`:304、:335、:362-366 |
| `create_app(thread_limit=None)` は thread limit の middleware を足さず、anyio の既定の limiter のまま [anyio 一般では 40] | `M/http.py`:1310-1315 |
| runtime role は `_mdb_schema_revision` / `_mdb_field_types` に権限を持たない (registry と revision は developer 接続でしか読めない) | `MitateDB-api/migrations/0003_provision_application.sql`:133-146、:214-226 |
| catalog 読みはそれぞれ自己 commit し、各自 `SET LOCAL` の timeout を打つ。そのため idempotency の lock は xact ではなく session scope にしてある | `M/backend_postgres.py`:423、:1722-1745 |
| 件数 lock は `idempotency_reserve` から `idempotency_unlock` まで保持される。keyed の非 replay 要求は application database 内で process をまたいで直列になる | `M/backend_postgres.py`:1846-1858、:1884、:1943 |
| `create_collection` は `schema_count` の上限検査 (:1266) → field の識別子・語彙・`field_constraints` の検証と `enum_members` の制限 (:1268-1360) → idempotency の受付 (:1419-1431) の順。受付の註は「after every VALIDATION_FAILED/LIMIT_EXCEEDED refusal above」と書く (:1423-1430) | `M/cell.py`:1266、:1268-1360、:1419-1431 |
| r2db の schema 操作は `bind_schema_operation` (field の識別子・語彙の検証を含む) → lookup → `schema_objects` → `enum_members` の順 | `R/postgres.py`:2078、:2113、:2172、:2193。`R/structured.py`:321 |
| DML・idempotency の経路で `QueryCanceled` / `LockNotAvailable` 以外の `psycopg.Error` (40P01 を含む) は `ValidationError("storage backend rejected the request")` に写る | `M/backend_postgres.py`:1388-1392、:1837-1839 |
| F-12 (台帳未適用) の検査は `PostgresBackend.__init__` が eager の runtime 接続の上で行い、`build_app` が起動時に 1 行記録する。検出時は message を保持し、storage に触るメソッドが拒否する (refusing cell) | `M/backend_postgres.py`:330-366、`M/main.py`:589-603 |
| `ops startup-checks` は git object と platform DB だけを読み、application 接続に依存しない。ただし `main.py`・`config.py`・`platform_declarations.py` の変更は指紋を変え、現行世代の行の更新が要る | `M/startup_checks.py`:1-14、:56-66 |
| F-16 / F-18 は platform 接続 (`declarations_conn`) で走る。application role の床は `pool_size × process_ceilings.data`、F-18 の下限は登録 application ≥ 1 のとき 1 組分だけ数え、上限側は報告のみ | `M/main.py`:482-490。`M/platform_declarations.py`:1102-1103、:1254、:1362-1375 |
| `alter_field` は `field_type` を拒否する。registry の `declared_type` は INSERT だけで、UPDATE されるのは `enum_json` / `nullable` だけ。DROP の経路は無い | `M/cell.py`:1887-1891。`M/backend_postgres.py`:985-987、:1109-1111、:850-852 |
| `tools/perf_baseline.py` の op は idempotency key を付けない (`grep -i idempotency` 0 件) | `tools/perf_baseline.py` |

## 3. 守るべき条件

1. 1 要求 = 1 原子単位 (SI-11、`security/SECURITY_INVARIANTS_V1.md`:302)。
2. idempotency: 同一 key の競合 (C-27) が in-process でも process 間でも閉じていること。
3. `revision` の意味と plan token の前提条件 (契約 1.7.0 の dry-run / plan。「schema operation が間に revision を進めたら PRECONDITION_FAILED で何も実行しない」、`spec/data-service-api.v1.json`:826)。
4. 監査の順序と fail-closed (schema 操作の pre-commit 行、SI-14 系。R-115 の設計と矛盾しない)。
5. application の隔離 (SI-01、`security/SECURITY_INVARIANTS_V1.md`:93)。実現は application ごとの database / role / DSN (既5)。
6. rate / concurrency の `enforced` 宣言 (SI-08) の帰結を変えない。
7. 共通契約 (`spec/`) の観測可能な振る舞いを変えない。ただし K-2 の優先順位の変化 (L-4 の範囲を含む) を除く (D-3、§9、Q-9)。
8. 依頼者の設計原則: 先送りしない・シンプル・制約で回避しない・誇れる成果物。長期的に正しい案を既定とする。

## 4. 候補と両論

| 候補 | 内容 | 利点 | 欠点 / 費用 | 監督 |
|---|---|---|---|---|
| **(甲)** | lock を外し、接続を要求ごとに借り、要求間の不変条件を PostgreSQL に寄せる。application × role ごとの上限付き pool (`BoundedConnectionPool`)。上限は thread limit 基準。要求間の調停は 2 段の advisory lock: 3a = application database に 1 つ (schema 操作だけが排他で取る)、3b = 実体単位 (schema 操作は対象実体を排他、DML は触る実体を共有)。検証 (pass 1) はこの lock の後に読む。schema 操作は 3a の後に revision を読んで plan token を照合する (D-3) | r2db と同じ形に揃う。lock の正しさが「同じ process か」に依存しない。守1・守3・穴1 が構造として消え、守2 と開1〜開4 が process 内・間の両方で閉じる。遅い 1 要求 (長い batch、`LOCK TABLE` を伴う alter の走査、`execution_ms` いっぱいの query) が同じ application の他要求を止めなくなる (DB 往復の待ちは GIL を放す)。schema 操作が待っている・走っている間も、無関係な実体の DML は止まらない (K-1) | 接続数が増える (application × 2 role × process × pool 上限。現行は × 1)。`CONNECTION LIMIT` 68、F-18 の床、`ops inventory` の算式、runbook。MitateDB には r2db の `R2DB_POOL_CACHE_MAX` に当たる上限が無い (idle の切り詰めを入れる、D-2)。要求あたりの advisory lock の文が増える (DML は 3b を触る実体の数だけ。`RM` §0.1.4 の 4 で理由の記録)。backend の自己 commit する catalog 読み群を「渡された接続の transaction の中で読む」形へ作り替える (J-1)。SQLiteBackend の扱い (D-6)。C-27 の変異指定、C-05 の Concurrency note、`CM` の主張 (§9) が変わる。規模が大きい。「遅い 1 要求が他要求を止めない」の範囲は unkeyed の要求・replay・query で、keyed の非 replay の書き込み同士は件数 lock で application database 内・process 間の直列が残る (r2db も同じ、`R/postgres.py`:1401。J-2)。replay も失効行があると先行要求の commit まで待ちうる (K-8)。keyed の非 replay の DML が件数 lock (2) を持ったまま 3b を待つと、別実体の keyed の書き込みも schema 操作の終わりまで止まる (別 process 間では現行も同じ。退行ではない。L-6)。拒否の優先順位が変わる (K-2・L-4、Q-9)。同一 process の DML 同士でも 40P01 が起きうる (K-2) | **推奨** |
| (乙) | process 内の lock を細粒度にする (reader-writer lock) + pool。起票時 (`RM`:459) の案 | DB 往復を増やさない | process 間の開1〜開4 は閉じず、別に DB 側の機構が要る。入れれば process 内の lock は冗長。正しさが「同じ process か」に依存する構造が残る | 採らない |
| (丙) | 読み取り (query) だけを lock の外に出す (query は pool の runtime 接続。書き込みは現行) | 変更が小さい。query 主体の負荷では §0.1.4 の 3 を満たす見込み | 書き込みの直列化と開1〜開4 が残る。接続の持ち方が 2 通り。R-107 の実装時に作り直す。先送りに当たる | 採らない |
| (丁) | 変えない (multi-process の N で並行度を得る) + §0.1.4 の 3 を取り下げる | 費用 0。K=32 の p50 は lock の無い r2db と同水準 (§2.7)。lock を外しても閾値 2 への寄与は小さい見込み | 閾値を動かして回避する形。穴1・開1〜開4 が別件で残る。遅い 1 要求が process 内の同 application を止める性質が残る | 採らない (依頼者が選べる選択肢として Q-1 に載せる) |
| (戊) | thread ごとの持続接続 (thread-local。thread limit 本を thread に固定) | pool が要らない | 接続数は pool 上限と同じで常時開く。thread と要求の対応に正しさが依存する (anyio の worker thread の入れ替わり)。既存の pool を使わない理由が無い | 採らない |

## 5. 監督案 (決定 D-N)

**D-1** (甲) を採る。`ApplicationCell._lock` による要求の直列化を廃止する。

**D-2 接続**: application × role の上限付き pool。pool は cell ごとの backend instance が自分で持つ (application ごとに 1 組)。process 全体の key 付き registry には置かない (key の取り違えが application の越境になるため。SI-01、K-10)。上限の出所は thread limit (1 process の同時実行数の上限。`role_pool_size(thread_limit)` 相当、§2.8)。要求の範囲 (D-6) は入口で必要な接続をすべて固定順 (developer → runtime。schema 操作は developer のみ) で借り、範囲の終わりまで持って出口で返す。DB の lock を持ったまま pool を待つ経路は無い (K-3)。1 要求が同時に持つのは role ごとに高々 1 本 (schema 操作は developer の主接続のみ。DML は runtime の主接続 + pass 1 の読みに使う developer (K-6)。idempotency の lock と記録は主接続の transaction の中、D-3)。

| 論点 | 両論 | 監督案 |
|---|---|---|
| 遅延 / eager | eager: 起動時に上限まで張る。F-12 の検査 (§2.8) は現行どおり起動時に走る。接続は常に上限本数 / 遅延: 最初の借用で張る。起動時の接続は減るが、F-12 の検査は現行 eager 接続の上で走っているので置き場が要る | 遅延 + 上限のみ。ただし `build_app` は起動時に served application ごとに runtime 接続を 1 本借りて F-12 の検査を行い、現行どおり 1 行記録して返す。refusing cell の意味論 (§2.8、`M/backend_postgres.py`:330-366) は変えない。起動時の接続は application あたり 1 本 (J-6) **【v0.6 註 2026-10-01】** refusing cell は要求の範囲の入口 (`request_scope`) で拒否するので、F-12 状態の application では、範囲の内側で検査される不正 (識別子・語彙・宣言との照合など) を持つ要求も (旧の `VALIDATION_FAILED` ではなく) `SERVICE_UNAVAILABLE` になる (http 層が cell の前に検査する body の形の不正は従来どおり `VALIDATION_FAILED` (400))。どちらも拒否であり、F-12 状態の application に限る (M-12 の「意味論は不変」への註。作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` 訂正註 4 の 6) |
| idle の切り詰め | 入れる: 使わない application の接続を閉じる (r2db は idle 300 s、`R/postgres.py`:809) / 入れない: 機構が 1 つ減り、上限で数は抑えられる | 入れる (K-4)。切り詰めが無いと実接続が application × role × process × 上限 まで増えて戻らず、served application が多い配備で cluster の max_connections に達し、platform pool・audit の接続まで失敗しうる (F-18 は下限だけを判定し上限側は報告のみ、§2.8)。形 (L-1): pool の持ち主は cell ごとの backend のまま (K-10)。加えて process に 1 つ「掃除専用の一覧」(弱参照。lookup には使わないので SI-01 の越境の経路にならない) を置き、どの pool の借用でも、全 pool の閾値超えの idle 接続を閉じる (r2db は `get_pool()` のたびに全 pool を掃く、`R/postgres.py`:815-829。同じ形)。専用 thread・timer は持たない。閾値は r2db と同じ 300 s。R-115 の idle ping が接続に持たせる返却時刻を使う。開示: 要求が 1 件も来ない process は掃かない (r2db も同じ。peer 対称) |

起動時の検査への依存 (現物): `ops startup-checks` と F-16 / F-18 は application 接続に依存しない。F-12 の台帳検査は上の表のとおり起動時の 1 本で行う。

pool の class (J-3): 既存の `BoundedConnectionPool` を直して使う (別に作らない。pool class は peer に 1 つ)。

- (i) `acquire` に呼び出しごとの待ち上限を渡せるようにする。データ面は deadline の残り、既定は現行の 5.0 s。
- (ii) 枯渇・接続失敗は pool 自身の中立な例外にし、利用者が写像する。platform 側の利用者は現行どおり `AuthorizationStateUnavailable` と同じ文面へ写す (観測可能な振る舞いは不変)。データ面は取得待ちの超過 → `ResourceLimitError(execution_ms)` (lock 待ちと同じ写像、`M/backend_postgres.py`:1828-1836)。接続失敗の写像は作業指示書で現物に合わせて確定する (§12 の 10)。
- (iii) `release` は idle へ戻す前に必ず rollback する (全利用者共通。IDLE 状態の rollback は往復なし [psycopg 一般、repo では未確認])。rollback が失敗した接続は捨てる。platform 側の唯一の借用点は既に rollback してから release し、失敗時は discard する (§2.8) ので、この変更で platform 側の書き込みは消えない。 **【v0.6 註 2026-10-01】** 実装は `transaction_status` が IDLE でないときだけ rollback する (IDLE の rollback は psycopg が往復なしで返し、計数用の `CountingConnection.txn_count` だけが進むため)。開いた transaction と `SET LOCAL` が戻り、INERROR も戻るという観測可能な結果は本項と同じ (`MT/test_r102_pool.py`::`test_release_rolls_back_so_the_next_borrower_gets_a_clean_connection`・`test_release_rolls_back_a_connection_left_in_an_aborted_transaction`。作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` 訂正註 2 の 4)。

**D-3 lock と 1 要求の transaction**: (甲) の形。

- **3a schema 操作の直列化 lock** (K-1): application database に 1 つの固定 key の 1 引数形 advisory lock (advisory lock は database ごとに別 [PostgreSQL 一般の挙動、repo では未確認])。`pg_advisory_xact_lock` の排他のみ。schema 操作だけが取り、DML・query は取らない。開1・開2・開4 を閉じる (revision・plan token・schema_count は application 単位)。既存の `761761761` (ops の儀式)・`761761762` (件数 lock、`M/backend_postgres.py`:241) と別の値にする。
- **3b 実体単位の lock** (K-1): 2 引数形の新しい namespace + `hashtext(実体名)`。既存の namespace `76176100` (:233) と別の値にする。1 引数形と 2 引数形は別空間である (:212-232 の註)。schema 操作は対象実体を `pg_advisory_xact_lock` で排他、DML (mutate / batch / cross_entity) は触る実体を `pg_advisory_xact_lock_shared` で共有に取る。batch / cross_entity は触る実体を key の昇順で取る。開3 を閉じる。`hashtext` の衝突は直列化が過剰になるだけで不足にはならない (既存の per-key lock と同じ理屈、`M/backend_postgres.py`:1772-1774)。query は D-4。
- 2 段にする理由 (K-1): application に 1 つの排他 lock だと、実体 A の schema 操作が遅い query を待つ間 (ALTER TABLE の ACCESS EXCLUSIVE、alter の `LOCK TABLE` + 走査)、全 process の無関係な実体 B・C の DML が共有待ちになる。現行は別 process の B・C は止まらないので退行になる。PostgreSQL の待ち行列の性質 (排他の待ちが後続の共有を並ばせる [PostgreSQL 一般、repo では未確認]) は 3b では対象実体に限られ、ALTER TABLE 自体と同じ範囲である。単一 lock 案は Q-8 に両論で載せる。
- **1 要求 = 主接続の 1 transaction** (J-1)。主接続は schema 操作 = developer、DML = runtime。要求の範囲 (D-6) が行うのは接続の借用 + transaction の開始 + timeout の設定だけで、lock は範囲の中の決まった点で順に取る: per-key = idempotency の受付、件数 = 非 replay と分かった後、3a・3b = その後、pass 1 の読みの前 (K-2)。schema lock を lookup の前に取らない。
  - schema 操作: developer を借りる → transaction を開き timeout を設定 → (keyed) per-key → lookup → (非 replay) 件数 → 3a 排他 → 3b 排他 (対象実体) → pass 1 の catalog 読み・revision 読み・plan token 照合・`schema_count` を同じ transaction の中で自己 commit せずに行う → DDL・registry・revision 加算・idempotency 行 → commit。
  - DML: developer → runtime の順で借りる → runtime の transaction を開き timeout を設定 → keyed なら per-key・件数 (xact) → 3b 共有 (触る実体、key の昇順) → pass 1 の catalog 読みは developer 接続で、共有 lock を取った後に行う (runtime role は registry を読めない、§2.8) → DML → commit。
  - 帰結: idempotency の advisory lock 2 種も session scope から xact scope へ変える。session scope にしていた理由 (catalog 読みが同じ接続で自己 commit する、`M/backend_postgres.py`:1722-1745) が消えるため。r2db と同形になる (`R/postgres.py`:1381、:1401)。session lock が無くなるので pool へ返す前の解放漏れの類は構造として無くなる (release 時の rollback が全 lock を放す、D-2 の (iii))。`idempotency_begin` / `idempotency_reserve` の途中 commit と `idempotency_unlock` は不要になる。
  - 費用: backend の catalog 読みメソッド群 (`field_types`、`schema_revision`、`field_domains`、`schema_count` ほか自己 commit するもの、`M/backend_postgres.py`:420、:440、:518、:668、:921) を「渡された接続の transaction の中で読む」形へ作り替える。idempotency 系の docstring (session scope の理由、`M/backend_postgres.py`:1722-1763 ほか) の書き換えは `docs/code-history/MitateDB-api/backend_postgres.md` の register と `tools/check_comment_provenance.py` の規律に掛かる (K-13)。規模が増える。
  - 却下: (b) session scope の schema lock = 全経路で明示解放が要り、pool 返却時に「解放済みか捨てるか」の規律が増える。session lock を 3 種に増やす方向で、J-1 と逆。(c) pass 1 用に developer をもう 1 本借りる = 1 要求が同 role を 2 本持ち、pool 上限での自己 deadlock と寸法の倍増を招く。
- 拒否の優先順位の変化 (K-2・L-4。観測可能): `create_collection` の `schema_count` の上限検査 (`M/cell.py`:1266) は idempotency の受付 (:1419-1431) の後・3a の後へ移る。field の検証と `enum_members` の制限 (:1268-1360) は受付の前に残る (§2.8)。上限に達した状態で次が変わる。
  - 再送: 同一 digest = `LIMIT_EXCEEDED(schema_objects)` → replay、異なる digest = → `CONFLICT`、両方の上限が満杯 = → `idempotency_entries`。r2db は既にこの順 (§2.8)。peer が揃う方向で、「記録済みの key の再送は記録から答える」に合う。
  - unkeyed の不正な要求: `LIMIT_EXCEEDED(schema_objects)` → `VALIDATION_FAILED`。r2db は識別子・語彙の検証を `bind_schema_operation` で lookup より前に行うので、識別子・語彙については揃う方向。`field_constraints` の検証の r2db での位置は未確認。
  - `enum_members` と `schema_objects` の拒否の順が入れ替わる (後 = `enum_members` が先)。r2db は `schema_objects` (:2172) → `enum_members` (:2193) の順なので、この組は r2db と逆になる (現行は同じ順)。
  - dry-run: 実行と同じ点で 3a・3b を取り、同じ transaction の中で `schema_count` と revision を読み、rollback する (dry-run の応答と plan token が実行時と同じ読みに基づく)。
  - 受け入れるかは Q-9。
- 40P01 (deadlock_detected) (K-2): 現行は `except psycopg.Error` で `VALIDATION_FAILED` に落ちる (§2.8)。R-102 の後は同一 process の DML 同士 (逆順に行を更新する 2 batch) でも起きる (process 間では R-113 以降すでに起きうる。r2db の写像は未確認)。決定: client 起因の code に写さない。どの code に写すかは両 peer の現物と契約の語彙を作業指示書で突き合わせて決める (§12 の 7。契約に触れるなら別途依頼者確認)。
- 件数 lock (J-2): 容量検査の形は R-102 では変えない (scope だけ上のとおり xact になる。容量検査の設計は別件、idempotency の往復は `RM` の R-81)。keyed の非 replay の要求は reserve から commit まで application database 内・process 間で直列のまま。r2db も同じ (`R/postgres.py`:1401) で、peer 対称の性質である。
- reap (K-8): J-1 で失効行の reap (DELETE) が要求の transaction の中に入る。失効行があると、別 key の要求 (replay を含む) が先行要求の commit まで行 lock で待ちうる。r2db も同形 (`R/postgres.py`:1407)。「replay は止まらない」は失効行が無いときに限る。形は変えない。
- 順序 (全要求がこの昇順で取り、上位を取った後に下位を取らない):

| 順 | lock | 取る要求 | scope・接続 | 出所 |
|---|---|---|---|---|
| 1 | per-key advisory lock `(76176100, hashtext(key))` | keyed・非 dry-run | transaction・主接続 (transact は runtime、schema 3 種は developer) | 現行は session 形、`M/backend_postgres.py`:1794 |
| 2 | 件数 advisory lock `(761761762)` | keyed・非 replay | transaction・主接続 | 現行は session 形、:1884 |
| 3a | schema 操作の直列化 lock (新、排他のみ) | schema 操作 | transaction・developer | 本書 |
| 3b | 実体単位の lock (新): schema 操作は対象実体を排他、DML は触る実体を共有 (key の昇順) | schema 操作・DML | transaction・主接続 (schema は developer、DML は runtime) | 本書 |
| 4 | 表 lock: `LOCK TABLE ... SHARE ROW EXCLUSIVE`、DDL の暗黙の表 lock、DML の行・表 lock | 各要求 | transaction | :818、:1152 |
| 5 | revision 行の行 lock | schema 操作 | transaction・developer | :939 |

- deadlock が無いことの筋 (K-1): 1 → 2 → 3a → 3b の順に取り、後の段を取った後に前の段を取る要求は無い。3b の共有同士は競合しない。schema 操作は 3b を 1 実体しか持たず (現行の MitateDB に複数の実体に触る schema 操作は無い。将来足すときは DML と同じく key の昇順で取る)、3a を持つ schema 操作は高々 1 つ。3b の排他を持つ間、その実体に共有保持者はいないので、同じ実体について schema 操作と DML が同時に 4 を持つことは無い。DML 同士の 4 (行 lock) の循環は lock 順序では防げず、40P01 として上の写像で扱う。query は 4 (ACCESS SHARE) だけを持ち、待つ間に他要求が待つものを持たない。pre-commit の監査行は platform DB (別 database・別接続) なので application database の lock の順序に入らない (`docs/design/AUDIT_PROCESS_LOSS_V0_1.md` §2 の 6)。網羅は §12 の 1 でレビューに委ねる。
- **前提 (K-3 が J-1 のこの 1 点を改める)**: 接続は範囲の入口ですべて借りるので、DB の lock を持ったまま pool を待つ経路は無い。「pool の上限 ≥ thread limit」は正しさではなく性能の前提 (待ちを 0 にする条件) である。`create_app(thread_limit=None)` (§2.8) や adapter・peer テストの直接の cell 呼び出しで同時要求数が上限を超えても、pool 待ちは deadline で打ち切られるだけで、互いを待つ輪にならない。R-115 の後は audit sink の pool も待ちの連鎖に入る (§12 の 8)。
- timeout (K-9・L-8): 範囲の入口で、借りた全接続 (主接続と DML・query の pass 1 の developer 接続) に deadline 由来の timeout を 1 回設定する。developer 接続の読み取り transaction は範囲の終わりの release 時の rollback で閉じる。範囲の中の catalog 読みは自分で timeout を打ち直さない (`SET LOCAL` は後から打った値が勝つ、`M/backend_postgres.py`:423、:1591-1602)。DDL が別の上限を要るなら、その文の直前で打ち直すことを作業指示書で確かめる (§12 の 9)。lock の待ちはこの timeout で打ち切り、`LockNotAvailable` → `ResourceLimitError(execution_ms)` に写す (既存の advisory lock と同じ、:1784-1795、:1828-1836)。pool の取得待ちは D-2 の (i) で deadline の残りを上限にする。 **【v0.6 註 2026-10-01】** 作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` 訂正註 4 の 1 が M-4 の「範囲の入口で 1 回」を改めた: 競合した lock の取得 (try 形で取れず block 形で取り直した 3a / 3b、per-key / 件数 lock の待ち) の後・pass 2 / DDL の前に、残りの deadline から `SET LOCAL` を 1 回打ち直す (残りが 0 以下なら `LIMIT_EXCEEDED(execution_ms)`)。競合の無い要求では往復は増えない。打ち直しは `M/backend_postgres.py`:504 (`_retime`)、固定する test は `MT/test_r102_request_scope.py`::`test_a_lock_wait_shortens_the_timeouts_of_the_statements_that_follow` (変異 V52a) と `test_an_uncontended_request_sets_its_timeouts_once_per_connection` (競合の無い要求は接続ごとに 1 回)。lock の取得中の接続断は `test_a_connection_lost_while_taking_a_lock_is_service_unavailable` (503、同 訂正註 4 の 3)。

**D-4 query は 3a・3b を取らない**。schema 操作は追加的で、query は 1 文の snapshot で読む。対象実体の schema 操作とは表 lock (4) で待ち合う。`_decode_rows` と型変更の食い違いの有無 (現物): `alter_field` は `field_type` を拒否し、registry の `declared_type` は INSERT のみ、DROP の経路も無い (§2.8)。既存 field の宣言型は変わらないので、読み取りと `_decode_rows` の間に型が変わるシナリオは現物から見つからなかった。間に `add_field` が commit しても、新しい field は読んだ行に含まれない (select は pass 1 で決まる、`M/cell.py`:2325)。

**D-5** (K-6) `read_page` の応答の decode は pass 1 で読んだ field types を使い、範囲を出た後に catalog を読まない (範囲の外・gate の外の DB 往復を無くす)。穴1 はこれで構造として消える。

**D-6 SQLiteBackend と要求の範囲** (J-6、K-2): backend が「要求の範囲 (request scope)」を与える共通の形を持つ (種別 = schema / DML / query と deadline を受ける context manager)。範囲が行うのは接続の借用 + transaction の開始 + timeout の設定だけで、lock は範囲の中の決まった点で D-3 の順に取る。PostgresBackend = 上のとおり。SQLiteBackend = 自分の RLock を範囲全体 (idempotency の lookup → 実行 → store、守4、`M/backend_sqlite.py`:748) で保持する。cell は現行の外側 `with self._lock:` の位置でこの範囲を開き、backend の種類で分岐しない。両論: SQLite を引退させ in-process plug も PostgreSQL にする案 (規模が別。本件では採らない)。

**D-7 計測器**: `_CountingRLock` の統計 (`POOL lock=` 行、`tools/perf_baseline.py`:955-960) は lock と共に無くなる。代わりに次を出す (K-11)。

- pool の acquire / waits: r2db の `POOL role=` 行と同じ形 (:965)。
- schema lock: 3a と 3b の合算で 1 行。新しい POOL 行の形 `schema_lock=<application>` (acquire / waits / wait_total_ms / wait_max_ms)。`_format_pool_row` (`tools/perf_baseline.py`:944-969) に 3 つ目の形を足す。
- schema lock の「待ち」の定義: 先に try 形 (`pg_try_advisory_xact_lock` / `pg_try_advisory_xact_lock_shared`) で取り、取れなかった取得を 1 waits と数えてから待つ形で取り直す。競合が無いとき往復は増えない。
- 作り替える対象: `MT/test_r78_pool_wait_stats.py`:138、`MT/test_r79_prepared_stats.py`:120- (`prepared_stats` が lock を 1 回取る)、`prepared_stats` の docstring (`docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md`:993 の O-3)、`tools/PERF_BASELINE_README.md`:265-307 (lock 行の説明)、`tools/tests/test_perf_baseline.py`:239-246 (lock 行の形の pin。root の完了ゲートの外なので finalize は `--tools-tests`) (K-13)、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:3378-3389 の `pool_stats` (`cell._lock.stats()` を返す。`MitateDB-api/conformance/` の他の adapter に `pool_stats` の定義は無い) (L-7)。

**D-8** r2db-api 側は変更しない。ただし Q-5 で「足す」なら改め、r2db は WP の先頭で再現テストを置き、赤なら同じ変更セットで閉じる。r2db の lock は `_load_catalog` より前に置く (plan・確認句・`schema_objects` の 3 つを同じ 1 文で閉じる見込み)。共通条件で駆動するのは plan の前提条件、`schema_objects` と確認句は peer テストで固定する (K-7)。「足さない」なら §2.6 の窓は台帳に別行で起票する (J-7)。 **【v0.6 註 2026-10-01】** 実装 (r2db の `apply_schema`、`pg_advisory_xact_lock(761761763)`、1 引数形・排他・transaction scope) は per-key → lookup (replay は記録から答える) → schema lock → 件数 lock → `_load_catalog` → revision の読みの順で取る。D-3 の順序表 (MitateDB: 1 per-key → 2 件数 → 3a) と schema lock と件数 lock の順が逆になる (peer 非対称)。作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` 訂正註 3 の 1 の M-17 (監督裁定) による。r2db の DML の検証と書き込みの間の窓 (K-7 の 3 窓の外) は台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` の R-120 に起票した (同 訂正註 3 の 3)。

## 6. 「壊していない」ことの示し方

| 性質 | 既存の証拠 | 足す証拠 | 変異 |
|---|---|---|---|
| 原子性 (SI-11) | `MT/test_foundation.py`:111、`CM` の SI-11 MitateDB の Evidence (`test_transact_two_pass_structure_zero_backend_calls_when_a_later_operation_fails_validation` ほか)、C-07・C-16 | pool 化後の同テストの再実行 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_postgres.py`::`test_transact_rollback_is_unconditional_for_a_non_foundation_error_raised_mid_pass_2` (V39) と既存の SI-11 の証拠の再実行 | commit を途中に入れる |
| 同一 key (C-27) | `COND`:56、`conformance-tests/test_c27_concurrent_same_key.py`:57-74 (開示済みの限界)、`MT/test_idempotency_concurrency.py`:253・:298・:347 | 変異指定を plug ごとに分ける (K-5)。in-process plug (SQLiteBackend、`MitateDB-api/conformance/conformance_adapter_mitatedb.py`) = D-6 の backend の RLock の範囲を外す。http plug (PostgresBackend) = per-key lock (xact) を外す、件数 lock (xact) を外す。http plug では advisory lock が in-process でも唯一の担い手になり、開示済みの限界が 1 つ消える 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`conformance-tests/test_c27_concurrent_same_key.py`::`test_c27_same_digest_executes_once[MitateDB-api]` (V40 = backend の RLock を外す)、同 `[MitateDB-api-http]` (V41 = per-key lock を共有に)、`test_c27_entries_bound_holds_under_concurrency[MitateDB-api-http]` (V42 = 件数 lock を共有に) | 上の 3 つ |
| 接続の非共有 (旧 守1) | `MT/test_threadpool_offload.py`:561 | 同テストを「同一 application への並行要求が互いの transaction に触れない」を固定する形に作り替える 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_threadpool_offload.py`::`test_concurrent_requests_on_one_application_never_touch_each_others_transaction` (V44) | 2 要求に同じ接続を渡す |
| 開1〜開4 | 無し | 2 cell (別接続組) の再現テストを先に赤で置き、実装で緑にする 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_cross_cell_windows.py`::`test_window1_plan_is_checked_against_the_revision_inside_the_ddl_serialization`・`test_window2_concurrent_alter_field_calls_do_not_lose_each_others_update`・`test_window3_data_write_validated_before_an_alter_is_not_committed_against_the_new_constraint`・`test_window4_concurrent_create_collection_cannot_exceed_max_schema_objects` (V1〜V5・V9・V10)。r2db は `r2db-api/tests/test_r102_schema_windows.py` の 3 本 (V6〜V8・V9r・V10r)。WP-1 の時点で 7 本とも赤 (再現成立) | 3a の取得を消す (開1・開2・開4) / 3b の取得を消す (開3) / 排他の代わりに共有を使う |
| 並行性 | 無し (現行は「1 concurrent lock holder」、`M/cell.py`:683-685) | 同一 application の 2 要求が同時に pass 2 にいることを観測するテスト 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_two_requests_of_one_application_are_in_pass_2_at_the_same_time` (V46) | pool の上限を 1 にする |
| 監査の順序 | `MT/test_application_audit.py`:2163 (sink 失敗で schema 操作が 503)、:2330 (commit 失敗で error 行)。buffer 行は cell lock に依存しない (push は lock の外、`M/cell.py`:2374 等) | 既存の再実行 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_application_audit.py` の全緑の再実行と、`test_a_schema_operation_waiting_for_the_audit_pool_is_refused_in_bounded_time_and_leaves_no_lock` (V48、M-3) | (既存) |
| release 時の rollback と失敗時に捨てる経路 (D-2 (iii)) | 無し | 開いた transaction と `SET` を残して返した接続が次の借用で clean 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_pool.py`::`test_release_rolls_back_so_the_next_borrower_gets_a_clean_connection` (V30)・`test_release_rolls_back_a_connection_left_in_an_aborted_transaction` (V30b)・`test_release_discards_a_connection_whose_rollback_fails` (V31) | rollback を消す |
| lock 順序 (1 → 2 → 3a → 3b) | 無し | keyed `create_collection` × keyed `add_field` を交差させて 40P01 が出ない (L-2) 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_keyed_create_collection_and_keyed_add_field_do_not_deadlock` (V49) | `create_collection` だけ 3a を受付の前に取る |
| 実体単位の粒度 (K-1) | 無し | 実体 A の schema 操作が待っている間に実体 B の DML が通る 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_a_schema_operation_on_one_entity_does_not_hold_up_data_writes_to_another` (V50) | 3b の key を固定値にする |
| D-4 | 無し | schema 操作が lock を持つ間も別実体の query が通る (対象実体の query は表 lock で待つ) 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_a_query_is_not_held_by_a_schema_operations_locks` (V51) | query に 3b を取らせる |
| lock 待ち・pool 待ちの timeout の写像 | 無し | deadline 超過で `LIMIT_EXCEEDED(execution_ms)` 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_a_write_waiting_for_an_entity_lock_is_cut_by_the_deadline` (V52)・`test_a_pool_wait_that_outlasts_the_deadline_is_limit_exceeded_execution_ms` (V53) | timeout の設定を消す |
| 起動時の F-12 の借用 | 既存テスト | 台帳未適用の application が refusing cell になり、他の application は serve する (既存テストの再実行) 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_main.py`::`test_build_app_h1_serves_every_application_and_refuses_only_the_one_with_a_pending_upgrade` (V63) | 起動時の検査を消す |
| 拒否の優先順位 (K-2) | 無し | 上限に達した状態での同一 key の再送が replay 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_a_resend_at_the_schema_object_bound_is_answered_from_its_record` (V61) | `schema_count` の検査を受付の前に戻す |
| 借用順 (K-3) | 無し | pool 上限 1・同じ実体の DML と schema 操作の並行 2 要求で輪にならず deadline で打ち切られる (L-7) 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_a_write_and_a_schema_operation_on_one_entity_with_pools_of_one_do_not_wait_in_a_ring` (V66) | lock を取ってから developer を借りる |
| 40P01 の写像 (K-2) | 無し | 逆順 2 batch で client 起因の code にならない 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_request_scope.py`::`test_a_deadlock_between_two_batches_is_service_unavailable_not_a_client_error` (V55)・`test_a_serialization_failure_is_service_unavailable_not_a_client_error` (V56) | 写像を消す |
| idle の切り詰め (K-4・L-1) | 無し | 別の application の要求で、止まった application の閾値超えの idle 接続が閉じられる 【v0.6 実測 (変異は作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` の番号)】`MT/test_r102_pool.py`::`test_another_pools_acquire_closes_stale_idle_connections_and_spares_in_use_ones` (V32)・`test_the_idle_sweep_runs_at_most_once_per_second_in_the_process` (V33) | 掃除を自分の pool だけにする |

共通条件を足すか否か (§9、Q-5) で、開1 の証拠の置き場 (peer テスト / 共通条件) が変わる。

## 7. 干渉

| 相手 | 内容 |
|---|---|
| R-107 (`RM`:461、「R-102 と干渉しうる」) | `expected_revision` の判定は「読んで比べて書く」を 1 transaction で行う必要がある (`spec/data-service-api.v1.json`:818-819)。(甲) の「要求ごとの接続 + DB 側の調停」はその前提を作る。R-102 を先に行うのが自然である。R-107 の着手条件は Mitate の実需のまま |
| R-106 (`RM`:460) | 直接の干渉は無い見込み。unique 制約の保存形が schema 操作を増やすなら D-3 の 3a・3b の対象に入る |
| R-115 (`docs/design/AUDIT_PROCESS_LOSS_V0_1.md` v0.5。依頼者裁定 2026-09-30「すべて監督案どおりで進めてください」、同書 §10) | 同書の決定 1 (1-A (i)) は通常の event を応答前に同期で書く。現行は pre_commit が cell lock の内側で走り、監査の往復の間 lock を握る (同書 §2 の 6、§4 の費用、`M/cell.py`:3130、:3178)。(甲) の後は application の直列化点が無くなり、同期書き込みが他要求を止めない。ただし監査の同期書き込みは application の transaction と lock を持ったまま audit の接続を借りる (§12 の 8)。R-115 の作業指示書 (`docs/work-orders/WORK_ORDER_R115_AUDIT_PROCESS_LOSS_V1.md` WP-3、訂正註 :303) は audit sink を上限 `role_pool_size(thread_limit)` で pool 化する。本件も同じ寸法の出所を使う。R-115 の branch `r115-cont` は `M/pool.py` に idle ping (`IDLE_PING_THRESHOLD_S`、同 branch の :64) を足し、audit sink を同じ class で pool 化する。R-102 は R-115 merge 後の `M/pool.py` の上に積む (J-3。idle の切り詰めは idle ping の返却時刻を使う、D-2)。触るファイル (`M/cell.py`、`M/main.py`、`M/pool.py`、`M/config.py`、`M/platform_declarations.py`) が重なるので並行 worktree にしない (`OPERATING_CONDITIONS.md` §1.2 の 16)。実施順は Q-7 |
| R-82 (`RM`:456、印あり) | R-102 の後は process 内の直列化点が無い。process ごとの catalog cache は別 process の schema 操作で陳腐化するので、schema lock (3a / 3b) の下で読んだ revision に対して検証する形が要る。runtime role は revision 表を読めない (§2.8) ので、検証は developer 接続の読みになる。順序は課さない: どちらが後でも、後の側が相手を織り込む。R-82 の設計は cell lock の直列化を前提にしない。R-80 / R-81 (`RM`:454、:455) も同じ経路の往復数を変え、同じ扱いとする (K-14 が J-5 のこの部分を改める) |
| R-108 (参照クライアント) | 契約を変えないので干渉しない |
| R-52 (`RM`:453) | 接続数の算式が変わりうる (§9) |
| 同型性テスト (`MT/test_audit_query.py`:2188 `_ISOMORPHIC_TARGETS`、件数 pin 199、:2812) | cell lock・`BoundedConnectionPool`・`PostgresBackend` は未登録。pool 化で触れうる登録済み helper (`role_pool_size`、`_POOL_SIZE_HEADROOM`、`headroom_lower_bound`、`check_max_connections_headroom`、`_declared_pool_size` 等) は本体を変えれば Class C、集合の増減は Class D。`psycopg_counting.py` は両 peer の byte 一致 pin (その docstring :40-48 は「pool checkout / cell lock」のどちらでも成立する) |
| `ops startup-checks` | `M/main.py`・`M/config.py`・`M/platform_declarations.py` を変えると現行世代の行の指紋の更新が要る (§2.8) |
| r2db-api | 同じ直列化は無い (§2.6)。Q-5 で「足す」なら D-8 のとおり改める |

## 8. 計測計画

本書では計測しない。規則は計測の前に固定し、計測後に動かさない (`docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` の D-5 / D-16 の形)。

前提の指摘: `RM` §0.1.4 の 3 の「cell lock の waits/acquire」は、(甲) では測る対象 (cell lock) が無くなる。数字の対象を「同一 application の要求を直列化する点 (pool の取得と schema lock (3a・3b))」に読み替える必要があり、§0.1.4 は依頼者裁定なので読み替えは依頼者裁定 (Q-2) である。idempotency の lock は読み替えに含めない: perf の op は idempotency key を付けない (§2.8) ので、件数 lock の待ちは D-R102 の負荷に現れない (J-2)。

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

- 正直な開示: pool の上限は thread limit 以上 (D-2) で、1 要求が role ごとに持つ接続は高々 1 本なので、pool の waits は構造上 0 になる見込み。計測の負荷に schema 操作が混ざらなければ schema lock の waits も 0 に近い見込み。閾値 3 は実装後は構造で満たされる。p50 の前後は記録し、退行の判定は `RM` §0.1.4 の 1 (完了ゲートの K=1) が担う (K-11)。

## 9. 契約・共通条件・`CONTROL_MAPPING`・変更クラス

- `spec/`: 直列化を述べる文は idempotency の義務 (:37 の 1.8.0 の義務「同一 key の 2 要求の直列化と、`idempotency_entries` を同じ直列化の下で評価する」、:192、:826・:829) で、実並行度を述べる文は無い。本設計はこの義務を保つ (per-key lock と件数 lock は scope が変わるだけ)。同じ :37 の 1.8.0 の無条件の義務 (limit_enforcement は deployment 全体を述べる) には、開4 と §2.6 の窓が成り立つ限り、両 peer の `schema_objects: enforced` が現に合わない (構造のみ、未再現。閉じるまでの扱いは Q-4。L-3)。K-2 の拒否の優先順位の変化 (L-4 の範囲を含む、D-3) は観測可能な振る舞いの変化であり、受け入れるかは Q-9。契約文 :829 は「記録に合う再送は target existence・destructive confirmation・precondition の評価より前に記録から答える — after this request's own authentication, authorization and bounds, which it consumes like any other request」と書く。この bounds に `schema_objects` が入るかで読みが分かれる: (読み 1、監督) bounds は要求が消費するもの (rate・concurrency・要求の大きさ) を指し、replay は schema object を 1 つも足さないので `schema_objects` は入らない → K-2 の順序と r2db の現行順が契約どおりで、MitateDB の現行順が外れている / (読み 2) `schema_objects` も bounds に入る → MitateDB の現行順が契約どおりで、r2db の現行順と K-2 が外れる。読みの出所 (L-5): 読み 1 の側 = 起草元の `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md`:582 (D-5 (8)) は bound を rate / concurrency / request_bytes / operation_depth / shape / capability / budget の妥当性と列挙し、`schema_objects` を含まない。読み 2 の側 = MitateDB の実装の註 `M/cell.py`:1423-1430 (「after every VALIDATION_FAILED/LIMIT_EXCEEDED refusal above」)。どちらの読みでも両 peer は現に食い違っている (構造のみ。conformance に当該の順序を固定する条件は見つからなかった、`grep schema_objects conformance-tests/*.py` に再送との組は 0 件。C-23 の容量の試験は DML だけ、`conformance-tests/test_c23_idempotency_semantics.py`:388-415。C-05 の `schema_objects` の駆動に再送は無い)。読みの確定は依頼者裁定 (Q-9)。読み 1 なら文面に触れず、契約の版は上げない見込み。文面を明確化するなら契約変更 (版上げ、設計レビュー 2 回) になる。
- `conformance-tests/`: `COND`:34 の C-05 の Concurrency note (「MitateDB-api allows one in-flight op per cell」) は SQLite plug では D-6 の backend の RLock の下で真のまま (担い手が cell から SQLite backend に移る、K-5)。http plug について改める。`COND`:56 の C-27 の変異指定 (plug ごとに分ける、§6) と開示済みの限界 (「SESSION advisory locks」の語も xact へ)、`conformance-tests/adapter.py`:1802-1810 の (ii) (「at most one in-flight operation PER CELL」)、`conformance-tests/test_c27_concurrent_same_key.py`:57-74 (:59 の「session advisory lock」の語を含む) が変わる → Class C。
- 共通条件を 1 つ足すか (plan の前提条件が並行する schema 変更の下でも成り立つこと。両 peer で駆動) は両論 (Q-5): 足す = 共通の安全性として固定できる。r2db 側の §2.6 の窓を閉じる変更が同じ変更セットに入り (D-8)、規模が増える / 足さない = peer テストで固定し、r2db の窓は別行で起票する。`CLAUDE.md` は「invariant を機能ごとに足さない」と定めるが、本件は invariant ではなく既存の契約文 (:826) の conformance 条件の追加である。
- `CM` (K-13): :979 (「per-application `PostgresBackend` pools nothing」)、:998-1000 (cell lock の 3 主張、いずれも `M/cell.py`:645 を指す) が偽になる。:1029 は §6 で作り替えるテスト (`test_pass1_and_pass2_serialize_through_cell_lock_no_developer_connection_race`) を旧名で証拠に挙げる。:1500・:1505 の SI-11 の証拠 (`MT/test_postgres.py`:1013) は `backend.begin` を差し替えて窓を作るので、D-6 で差し替え点が変わる → 主張と証拠の書き換え = Class D。
- `CM`:1505 (SI-11 MitateDB の Status「pass 1 runs outside `self._lock`」) は現物と合わない: pass 1 は外側 lock の内側にある (`M/cell.py`:646-660、:2936)。開示している窓そのもの (別接続の schema 変更が pass の間に入る) は別接続について在り、Evidence はそれを駆動する。理由の記述が陳腐化している (本書では直さない。上の書き換えで扱う)。
- migration: advisory lock は表も権限も要らない見込み [PostgreSQL 一般。repo では未確認]。runtime role が読めない表 (§2.8) に依存しない形にする。migration は不要の見込み。
- 接続数: application role の `CONNECTION LIMIT` 68 (`MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`:113)。現行の算式は既に「application role あたり `pool_size` × process」を数える: F-16 の床 `pool_size × process_ceilings.data` (`M/platform_declarations.py`:1102-1103)、`ops inventory` item (8) の `new_basis_count × pool_size` (`M/ops.py`:2700-2701)。(甲) の後の実接続は「application × role あたり process 数 × pool 上限」で、上限が `role_pool_size(thread_limit)` (既定 6) なら算式の値は変わらない見込み。68 に収まる条件は 6 × (並走する全 revision の process 数の和) ≤ 68、すなわち和 ≤ 11。cluster 全体の最悪値は served application 数 × 2 role × 上限 × process 数 (K-4。idle の切り詰めで平常時は戻る)。F-18 の下限は application 1 組分しか数えず (:1254)、served application 数に比例する実需は上限側 (:1375) にだけ現れ、上限側は報告のみである (既存の性質。判定に変えるかは `RM` の R-31 / R-52 の範囲で、本件では変えない)。runbook の式 (`MitateDB-api/docs/cloud-run-cloud-sql.md`:526) は旧 concurrency 基準の書き方のまま。`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §3 の表も concurrency 基準 (同書の時点の値)。
- 実装の変更クラス: **Class D** (`security/` の Control 主張の書き換えを含む。conformance の変更で C。重い方)。見込みの path で `tools/change_class.py` を実行して `class=D` を得た (`M/` 4 本 = B、`COND`・adapter・C-27 テスト = C、`CM` = D)。規模 L。設計レビューは契約を触らないので 1 回 (規模 L なので 1 巡目は A / B の 2 名並行)。

## 10. R-101・G-4 との関係 (見込み)

- 閾値 3 (`RM` §0.1.4 の 3): (甲) で満たせる見込み (構造上、§8)。読み替えの裁定が要る (Q-2)。
- 閾値 2 (8 倍以内) への寄与は小さい見込み。根拠: (a) R-101 の判定は 4 plug とも R-101 設計 (`docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md`) の J-2 (GIL) が主体で、同 J-3 は不成立 (§2.7)、(b) real-server の K=32 の p50 は application lock の無い r2db と MitateDB で N=1 (39.5 / 38.9 ms)・N=4 (24.9 / 24.7 ms) とも同水準。lock を外しても CPU の直列 (GIL) は残る。
- R-102 の価値は閾値 2 ではない: G-4 の終了条件 (R-102 の閉止と閾値 3)、穴1 と開1〜開4 の解消、遅い 1 要求による同 application の head-of-line blocking の解消 (範囲は unkeyed の要求・replay・query。keyed の非 replay の書き込み同士は件数 lock で直列のまま (D-3・J-2)。replay は失効行が無いときに限る (K-8)。schema 操作と待ち合うのは、unkeyed の要求については対象実体の要求だけ (K-1)。keyed の非 replay の DML が件数 lock を持ったまま 3b を待つと、別実体の keyed の書き込みも schema 操作の終わりまで止まる (別 process 間では現行も同じ。退行ではない。L-6))、R-107 と R-115 の前提。
- R-101 は本件で閉じない。

## 11. 依頼者判断待ち (両論のまま)

| Q | 問い | 選択肢 | 監督の推奨 |
|---|---|---|---|
| Q-1 | 採る案 | (甲) / (丙) / (丁)。(乙)(戊) は監督が却下 (§4) | (甲) |
| Q-2 | `RM` §0.1.4 の 3 の読み替え (§8) | 「同一 application の要求を直列化する点 (pool の取得と schema lock。idempotency の lock は含めない) の waits/acquire の合算が K=4 で 10% 以下」と読み替える / 読み替えず cell lock が無いことをもって充足とする / 取り下げる。「読み替える」を選んでも、実装後は構造上満たされる見込み (§8 の開示) | 読み替える |
| Q-3 | 穴1 の扱い (現行 main に在る、process 内、構造のみ確認、実害未計測) | (i) R-102 の実装で構造として消す (それまで残る) / (ii) 小さい修正 (decode を lock の内側へ) を規模 S・別項目として先に行う。(ii) は `M/cell.py` に触るので R-115 (Q-7) と同じファイルに重なり、R-115 の merge 後に行う | (ii)。R-102 は規模 L で時間がかかる。先送りしない |
| Q-4 | 開1〜開4 の扱い (R-113 以降 process 間で開いている、未再現) | (i) R-102 の WP の先頭で再現テストを置き、R-102 で閉じる / (ii) 別項目として起票し先に閉じる (schema lock だけを先に入れる)。(ii) を現行の構造 (自己 commit する catalog 読み) のまま行うには session scope の lock が要り、D-3 で却下した (b) と同じ形になる。(i) の場合の閉じるまでの間の扱い (L-3): (i-a) 台帳の R-102 行に開示として記録し、宣言は変えない / (i-b) 閉じるまで `schema_objects` の宣言を下げる (両 peer の宣言と conformance の変更 = Class C、契約の語彙の範囲内) | (i)・(i-a)。WP の先頭の再現テストで成立を確かめ、成立したら依頼者に報告する。窓は上限際の並行 create に限られ、宣言を下げて戻す 2 回の変更の方が重い |
| Q-5 | 共通条件を足すか (§9)。r2db の §2.6 の窓の扱いを含む | 足す (r2db は D-8 のとおり同じ変更セットで閉じる。決定的に駆動するには port の hook (port の版上げ) が要る見込み。in-process plug (SQLite) では空振りになりうる) / 足さない (peer テストで固定し、r2db の窓は台帳に別行で起票) | 足す。契約文 (`spec/data-service-api.v1.json`:826) に並行下の証拠が無い。r2db も plan の revision を同 transaction の素の SELECT で読み、その前に lock が無い (§2.6、構造のみ、未再現)。同じ窓が確認句 (SI-09) と `schema_objects` (SI-08) にも及ぶ。共通条件だけが両 peer を同じ形で固定できる |
| Q-6 | 接続数の増加を受け入れるか。pool の上限の出所 | 受け入れる・thread limit 基準 (`role_pool_size(thread_limit)`) / 別の設定値 (上限 ≥ thread limit は pool の待ちを 0 にする条件なので、下回れば待ちが出る。下限の検査が要る)。材料: cluster 全体の最悪値は served application 数 × 2 role × 上限 × process 数、idle の切り詰めで平常時は戻る (D-2、§9) | 受け入れる・thread limit 基準。上限 ≥ thread limit は待ちを 0 にする条件 (K-3)。既存の算式 (F-16、`ops inventory`) が既に pool_size × process を数える。設定値を増やさない |
| Q-7 | R-115 との実施順 (§7) | R-102 が先 / R-115 が先 | R-115 が先。R-115 は実装が進行中 (branch `r115-cont` に WP-1〜WP-4b、`docs/work-orders/HANDOVER_20260930_R115_FABLE.md`)。同じファイル (`M/pool.py` を含む) に触る。R-102 の作業指示書は R-115 merge 後の main に対して書く |
| Q-8 | schema lock の粒度 (D-3、K-1) | 2 段 (3a = application の schema 操作の直列化、3b = 実体単位。無関係な実体の DML は schema 操作の間も止まらない。DML は触る実体の数だけ lock の文が増える) / 単一 lock (application に 1 つ、schema 操作は排他・DML は共有。単純。無関係な実体の DML が schema 操作の間 process をまたいで止まり、現行より退行する) | 2 段 |
| Q-9 | K-2 の拒否の優先順位の変化を受け入れるか (D-3) | 受け入れる (上限到達時の再送が replay / CONFLICT / `idempotency_entries` になる。r2db と揃う。契約文 :829 の bounds を「要求が消費するもの」と読む = §9 の読み 1。併せて L-4 の範囲も変わる: unkeyed の不正な要求が `VALIDATION_FAILED` に、`enum_members` と `schema_objects` の順が入れ替わる (この組は r2db と逆になる)、dry-run も同じ点で数える。D-3) / 現行順を保つ (全 schema 操作が 3a を最初に取る (3a → 1 → 2 → 3b)。費用: schema 操作の replay が走行中の schema 操作の終わりを待つ。DML の順 (1 → 2 → 3b) とは 3a を共有しないので交差しない。`create_collection` だけを 3a → 1 にする形は、他の keyed schema 操作 (1 → 2 → 3a) と件数 lock (2) を挟んで deadlock するので不可 (L-2)。§9 の読み 2 を採るなら r2db 側の順序を直す変更が別に要る) | 受け入れる (読み 1)。replay は何も実行せず schema object を足さないので、`schema_objects` で拒否する理由が無い。:829 自身が「その配置でなければ再送に記録から答えられない」と理由を述べる |
| — | 変更クラス D の確認 (依頼者確認事項) | D で進める / 他 | D |

### 11.1 依頼者裁定 (逐語、2026-09-30)

監督が Q-1〜Q-9 と変更クラスの確認を上の表 (選択肢と監督の推奨) で示し、「『すべて監督案どおり』か、番号ごとの指定でお答えください」と求めたのに対し:
「すべて監督案どおりで進めてください」

帰結 (上の表の「監督の推奨」の欄のとおり。再審議しない、`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 51):

| Q | 確定 |
|---|---|
| Q-1 | (甲) |
| Q-2 | `RM` §0.1.4 の 3 を「pool の取得と schema lock の waits/acquire の合算が K=4 で 10% 以下」と読み替える (idempotency の lock は含めない) |
| Q-3 | (ii)。穴1 は規模 S の別項目 (`RM` R-119) として先に直す。R-115 の merge 後 |
| Q-4 | (i)・(i-a)。R-102 の WP の先頭で再現テストを置き、R-102 で閉じる。閉じるまでは台帳の R-102 行に開示として記録し、宣言は変えない。再現が成立したら依頼者に報告する |
| Q-5 | 足す。r2db の §2.6 の窓は D-8 のとおり同じ変更セットで閉じる |
| Q-6 | 受け入れる・thread limit 基準 |
| Q-7 | R-115 が先 |
| Q-8 | 2 段 (3a・3b) |
| Q-9 | 受け入れる (契約文 :829 は §9 の読み 1) |
| 変更クラス | D |

### 11.2 依頼者確認 (逐語、2026-10-01)

監督が R-102 の閉止 (local main `67bf62c`) の報告で、依頼者指示 2026-10-01「裁定は監督の推奨で進めてあとで確認」の下で進めた裁定の一覧 (引き継ぎ書 `docs/work-orders/HANDOVER_20261001_R102_FABLE.md` §4 の A〜G: 1 = 監督裁定 M-1〜M-17・M-19、2 = 再現の報告 (7 本とも赤)、3 = M-18 の問い (推奨 (a))、4 = R-120 の起票、5 = runbook §10.10 版 12 の再受理、6 = C-34 の条件文と hook の文の改訂、7 = 検査器の既知の穴の候補) を示し確認を求めたのに対し:
「確認事項は了承します」

帰結 (再審議しない、`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 51): M-1〜M-19 は確定 (M-18 は (a) = 設計どおり、plan 付き DML は 3a を取らない。観察として記録)。R-102 前の `schema_objects: enforced` が process 数 > 1 で契約 1.8.0 の義務に合っていなかった事実 (再現 7/7) は依頼者が了承した事実として記録する。R-120 の起票を確定。runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.10 の版 12 を受理 (§10.8 は 12 / accepted、`security/CONTROL_MAPPING.md` 3.15)。C-34 の条件文と hook の文 (plan / dry_run 付きの schema 操作に限る) を確定文とする。検査器の既知の穴 (`tools/check_comment_provenance.py` がコードごと消える経緯コメントの逐語移動を保護参照の削除として赤にする) は `OC` §1.12 の 71 により docstring の Known gaps に書く (次の変更セット)。

## 12. レビューで確かめてほしい点

1. K-1 の 2 段 lock (1 → 2 → 3a → 3b) で deadlock が無いことの網羅。共有を持つ DML が `LOCK TABLE` を待つ schema 操作と絡む経路を含む (再確認)。
2. D-4 (query が 3a・3b を取らない) で壊れるシナリオ。
3. session scope の状態 (advisory lock・`SET`・prepared statement) が、要求ごとに借りた接続を pool に返した後に残らないこと (D-2 の (iii) の rollback と、rollback が失敗した接続を捨てる経路を含む)。
4. pool 化で `SET LOCAL` / prepared statement / `application_name` が接続をまたいで漏れないか (D-2 の (iii) で rollback する。r2db は返却前に rollback する、`R/postgres.py`:679)。
5. §8 の規則が計測後に動かせない形になっているか。
6. §2 の事実に推測が混ざっていないか。
7. (起草) 40P01 の写像 (D-3。client 起因の code に写さない。両 peer の現物と契約の語彙を突き合わせる。契約に触れるなら依頼者確認)。
8. (起草) R-115 の後、監査の同期書き込みが application の transaction と lock を持ったまま audit の接続を借りる経路で、待ちの輪ができないこと (audit の接続の保持者は application database の lock を待たないので輪にならない見込み)。
9. (起草) DDL が範囲の先頭の timeout と別の上限を要るとき、その文の直前で打ち直していること (D-3 の timeout)。
10. (起草) データ面の接続失敗をどの応答に写すか (D-2 の (ii)。作業指示書で現物に合わせて確定する)。
11. (起草) D-6 の要求の範囲の形で、cell に backend の種類による分岐が残らないか。
12. (起草) J-1 で schema 操作の transaction が長くなる (pass 1 の間、developer の transaction と 3a・3b の排他を保持する) ことで壊れる経路 (対象実体の DML の共有 lock の待ちの長さ、`execution_ms` の予算)。
13. (起草) batch / cross_entity が多数の実体に触るときの 3b の取得数と往復 (`RM` §0.1.4 の 4 の理由の記録)。

## 13. 改版履歴

| 版 | 日付 | 内容 |
|---|---|---|
| v0.1 | 2026-09-30 | 起草 (監督の枠 v1.0 による) |
| v0.2 | 2026-09-30 | 監督裁定 J-1〜J-8 を反映 (J-1 1 要求 = 主接続の 1 transaction と idempotency lock の xact 化、J-2 件数 lock の範囲の開示、J-3 `BoundedConnectionPool` の直し、J-4 D-R102 の未記入 2 箇所、J-5 開4 と R-80〜R-82、J-6 要求の範囲と F-12、J-7 Q-5〜Q-7 の推奨、J-8 SI-01 の語) |
| v0.3 | 2026-09-30 | 設計レビュー 1 回目 (A / B) の監督裁定 K-1〜K-16 を反映 (K-1 lock を 3a・3b の 2 段に・Q-8、K-2 拒否の優先順位と範囲の形・40P01・Q-9、K-3 入口で全部借りる (J-1 の「上限 ≥ thread limit は正しさの前提」を性能の前提に改める)、K-4 idle の切り詰めを入れる、K-5 C-27 の変異を plug ごとに、K-6 D-5、K-7 r2db の窓の範囲、K-8 reap、K-9 timeout、K-10 pool の持ち主、K-11 D-R102、K-12 §6 の行、K-13 §9・D-7 の対象、K-14 R-80〜R-82 に順序を課さない (J-5 の該当部分を改める)、K-15 R-113 設計への追記、K-16 問いの材料と語) |
| v0.4 | 2026-09-30 | 再確認の監督裁定 L-1〜L-9 を反映 (L-1 idle の切り詰めを全 pool の掃除に、L-2 Q-9 の対案と §6 の lock 順序の行、L-3 spec:37 の義務と開4・Q-4 の (i-a)/(i-b)、L-4 K-2 の範囲と dry-run、L-5 2 つの読みの出所、L-6 §10 の開示、L-7 §6 の借用順の行と D-7 の adapter、L-8 developer 接続の timeout と終わり、L-9 R-113 設計の版は上げない (本書は変更なし)) |
| v0.5 | 2026-09-30 | 依頼者裁定 (§11.1、逐語) を記録し、設計を確定 |
| v0.6 | 2026-10-01 | 実装後の註のみ (決定 D-1〜D-8 と §11.1 は書き換えない): D-2 (iii) の rollback の形 (作業指示書 訂正註 2 の 4)、D-2 の遅延 / eager の行に F-12 の拒否の時点 (同 訂正註 4 の 6)、D-3 の timeout の打ち直し (同 訂正註 4 の 1)、D-8 の r2db の lock 順 (同 訂正註 3 の 1、M-17) と R-120、§6 の各行に実測した test 名と変異の番号 |
| v0.7 | 2026-10-01 | §11.2 (依頼者確認、逐語) を足した。決定は変えていない |
