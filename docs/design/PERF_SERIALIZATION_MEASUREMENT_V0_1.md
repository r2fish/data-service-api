# 設計メモ — 1 process 内の直列化の主体 (threadpool / GIL / PostgreSQL 往復) の切り分け (R-101)

## 0. 版数・位置づけ

- **v0.1 (2026-09-26)。骨だけである。** 基点は local main `a1c1ee3`、作業指示書は `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` (以下「WO」)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-101** 行、横断条件は同ファイルの **P-8**・**R-20**、再検討条件の受け皿は **R-84**、終了条件は **G-4** である。
- §2 (実測) と §3 (事実) と §4 (判断) は **WO §3 = WP-2 で監督が埋める。** WP-1 (実装担当) はこの骨を動かさず、**判断を先に書かない。**
- 先行する実測の記録は `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` (R-78) に在る。本メモはその続きであり、同じ計測器 (`tools/perf_baseline.py`) の新しい行 (`CPU`・`DBTIME`) を使う。

## 1. 目的と方法

**目的**: PostgreSQL 経路で K 要求の group p50 が K にほぼ比例して伸びる現象 (R-78 の実測) について、1 process 内の直列化の主体が (a) anyio の既定 thread limiter、(b) GIL (Python の CPU 時間)、(c) PostgreSQL 往復の待ち、のどれかを数字で切り分ける (WO §1.1)。**寸法 (thread limit、worker 数、pool) と構造 (async psycopg、multi-process) を変える判断は計測の後であり、別の変更セットで行う** (WO §1.1 の (a)、`RM` の P-8・R-20)。

**道具と引数**: `tools/perf_baseline.py --warmup <W> --n <N> --concurrency <K>` に加え、`DSA_PERF_POOL_SIZE`(r2db-api の `-http`/`-socket` のみ)と `DSA_PERF_THREAD_LIMIT`(両peer の `-http`/`-socket`)の 2 つの環境変数。WP-1 で `CPU` 行・`DBTIME` 行 (2 scope) と `DSA_PERF_THREAD_LIMIT` が追加された (WO §1.2 の D-1〜D-3)。

**`CPU` 行の窓と分母**: 窓は **measured の `_run_concurrent` 呼び出しの前後のみ**(warmup を含まない)。`wall_ms=` は測定した group の wall の和。`cpu_total_ms=` は `resource.getrusage(RUSAGE_SELF)` の `ru_utime + ru_stime` の窓内差分 (プロセス全体、どのスレッドの分も含む)。`cpu_main_ms=` は `time.thread_time()` の窓内差分 (呼び出し元スレッド = main thread だけ)。`cpu_other_ms=` は `cpu_total_ms - cpu_other_ms` ではなく `cpu_total_ms - cpu_main_ms`(anyio worker thread + socket plug の uvicorn thread の分)。`thread_limit=` は plug の `perf_thread_limit()` の値、無ければ (env 無し・無効) 文字列 `default`。`requests=` は **`n * K`(measured のみ)**であり、`ROUNDTRIP` 行の `requests=`(`(warmup + n) * K`)とは分母が異なる。

**`DBTIME` 行 (2 scope) の窓と分母**: 窓は `CPU` と同じ measured 区間。PRE snapshot は `_measure_op` の中で warmup の直後・measured の直前に取り、POST snapshot は `PREPARED` 行が既に使っている POST `prepared_stats()` の呼び出しを共有する (`DBTIME scope=app` と `PREPARED` とで 1 op あたり POST 呼び出しは 1 回だけ)。`scope=app` は `prepared_stats()` が返す接続ごとの `db_wall_ms`/`txn_count`/`execute_count`/`executemany_count` の PRE/POST 差分 (POST にだけ在る接続は PRE を 0 とみなす。`conns=` は POST の接続 label 数、`gone=` は PRE にだけ在る label 数)。`scope=platform` は `platform_db_time_stats()`(r2db: `_credentials`/`_application_durable_audit` の 2 つの `_RolePool.platform_stats()` の和。MitateDB: credential store / audit sink の per-call store の `platform_stats()` の和) の PRE/POST 差分。`scope=platform` の `db_calls=` も PRE/POST 差分 (platform accessor の `execute_count + executemany_count` の畳み込み和)。`db_wall_ms_per_req=` は `scope=app` が `db_wall_ms / requests`、`scope=platform` が `(db_wall_ms + connect_wall_ms) / requests`。

**`txns` の定義**: `commit()`/`rollback()`/`transaction()` の enter・exit の呼び出し回数 (SAVEPOINT/RELEASE を含む)。**R-80 の `ROUNDTRIP` 行の `xacts`(`pg_stat_database.xact_commit + xact_rollback` の差分、サーバ側)とは単位が違うので比べない。**

**`DSA_PERF_THREAD_LIMIT`**: 正整数のとき、data-plane app を薄い ASGI wrapper (`_PerfThreadLimitWrapper`) で包み、実行中の loop で最初の要求のときだけ `anyio.to_thread.current_default_thread_limiter().total_tokens` をその値に設定する (loop ごとに 1 回)。無し・無効 (0 以下、非数) のときは wrapper を作らず、app の identity は既存のまま。`DSA_PERF_POOL_SIZE` は r2db-api の `-http`/`-socket` のみ (既存、R-78)。**この 2 つの環境変数を残したまま `pytest` を走らせない。**

**thread limit × K の sweep 計画 (WP-2 が実施)**: 両 peer の `-http`/`-socket` (in_process は同じ run に出るが判定の表からは外す) で、thread limit ∈ {既定 (env 無し) = 40, 4, 1} × K ∈ {1, 4, 32}、`DSA_PERF_POOL_SIZE=32` 固定、`--warmup`/`--n` は R-78 の表 (K ≤ 4: 10/100、K=32: 3/15) に、「既定 × K=32」の 2 回目の run を足した計 10 run。**ε と δ の求め方**: 2 回取った「既定 × K=32」の `query` の p50 の相対差を plug ごとに ε とし、判定の閾値 **δ = max(10%, 2ε)** を plug ごとに §3 で確定する。

**`POOL lock=` の `acquire` に op ごと probe 2 回分が含まれる事実**: R-78/R-79 時点では `PREPARED` 行の POST `prepared_stats()` 呼び出し (MitateDB では `ApplicationCell.prepared_stats()` がその都度 cell の `RLock` を取る) が op ごと 1 回だった。本 WP からは `DBTIME` 行のための PRE snapshot 呼び出しが同じ op に 1 回追加されるので、**MitateDB の `POOL lock=` の `acquire` は op ごと probe 2 回分を含む** (`MitateDB-api/src/mitatedb_api/cell.py:615` 付近の `ApplicationCell.prepared_stats`。`tools/PERF_BASELINE_README.md` の同一記述を参照)。

**合成環境である旨**: 以下の実測 (WP-2 が §2 に記す) はすべて開発機のローカルの使い捨て PostgreSQL クラスタに対するものであり、ホスト名・実 DSN・作業機の絶対パスは記録しない (WO §1.1 の (d)、`OPERATING_CONDITIONS.md` §1.9)。`PERFRUN` の `host=` は `<OS/arch>` の形式である。

## 2. 実測 (WP-2 = 監督が埋める)

(空欄。WP-1 では埋めない。)

## 3. 事実 (§2 の数字だけから。判断語を含まない。WP-2 = 監督が埋める)

(空欄。WP-1 では埋めない。)

## 4. 判断 (監督)

(空欄。WP-1 では埋めない。判定規則は作業指示書 §3.3 の逐語 (D-5) を計測前に固定し、計測後に動かさない。)
