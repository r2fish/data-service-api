# 設計メモ — 1 process 内の直列化の主体 (threadpool / GIL / PostgreSQL 往復) の切り分け (R-101)

## 0. 版数・位置づけ

- **v0.3 (2026-09-28)。WP-3 / WP-4 の再計測を §5 (D-12) と §6 (D-16) に足した。§1〜§4 は書き換えない。** 作業指示書は WO v1.1 (§7〜§12)。判定規則は WO §10.1 (§7.3 の D-12・D-16) の逐語で、計測前に固定したもの。§5・§6 の実測・事実・判断は監督が記入する (WO §10)。
- **v0.2 (2026-09-27)。WP-2 の実測 (§2)・事実 (§3)・判断 (§4) を監督が記入し、§1 の 2 箇所 (`cpu_other_ms` の式、最初の op の `POOL lock=` の例外) を確定した。** v0.1 (2026-09-26) は骨だけだった。 基点は local main `a1c1ee3`、作業指示書は `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` (以下「WO」)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-101** 行、横断条件は同ファイルの **P-8**・**R-20**、再検討条件の受け皿は **R-84**、終了条件は **G-4** である。
- §2 (実測) と §3 (事実) と §4 (判断) は **WO §3 = WP-2 で監督が埋めた** (v0.2)。判定規則は WO §3.3 の逐語で、計測後に動かしていない。
- 先行する実測の記録は `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` (R-78) に在る。本メモはその続きであり、同じ計測器 (`tools/perf_baseline.py`) の新しい行 (`CPU`・`DBTIME`) を使う。

## 1. 目的と方法

**目的**: PostgreSQL 経路で K 要求の group p50 が K にほぼ比例して伸びる現象 (R-78 の実測) について、1 process 内の直列化の主体が (a) anyio の既定 thread limiter、(b) GIL (Python の CPU 時間)、(c) PostgreSQL 往復の待ち、のどれかを数字で切り分ける (WO §1.1)。**寸法 (thread limit、worker 数、pool) と構造 (async psycopg、multi-process) を変える判断は計測の後であり、別の変更セットで行う** (WO §1.1 の (a)、`RM` の P-8・R-20)。

**道具と引数**: `tools/perf_baseline.py --warmup <W> --n <N> --concurrency <K>` に加え、`DSA_PERF_POOL_SIZE`(r2db-api の `-http`/`-socket` のみ)と `DSA_PERF_THREAD_LIMIT`(両peer の `-http`/`-socket`)の 2 つの環境変数。WP-1 で `CPU` 行・`DBTIME` 行 (2 scope) と `DSA_PERF_THREAD_LIMIT` が追加された (WO §1.2 の D-1〜D-3)。

**`CPU` 行の窓と分母**: 窓は **measured の `_run_concurrent` 呼び出しの前後のみ**(warmup を含まない)。`wall_ms=` は測定した group の wall の和。`cpu_total_ms=` は `resource.getrusage(RUSAGE_SELF)` の `ru_utime + ru_stime` の窓内差分 (プロセス全体、どのスレッドの分も含む)。`cpu_main_ms=` は `time.thread_time()` の窓内差分 (呼び出し元スレッド = main thread だけ)。`cpu_other_ms=` は `cpu_total_ms - cpu_main_ms`(anyio worker thread + socket plug の uvicorn thread の分)。`thread_limit=` は plug の `perf_thread_limit()` の値、無ければ (env 無し・無効) 文字列 `default`。`requests=` は **`n * K`(measured のみ)**であり、`ROUNDTRIP` 行の `requests=`(`(warmup + n) * K`)とは分母が異なる。

**`DBTIME` 行 (2 scope) の窓と分母**: 窓は `CPU` と同じ measured 区間。PRE snapshot は `_measure_op` の中で warmup の直後・measured の直前に取り、POST snapshot は `PREPARED` 行が既に使っている POST `prepared_stats()` の呼び出しを共有する (`DBTIME scope=app` と `PREPARED` とで 1 op あたり POST 呼び出しは 1 回だけ)。`scope=app` は `prepared_stats()` が返す接続ごとの `db_wall_ms`/`txn_count`/`execute_count`/`executemany_count` の PRE/POST 差分 (POST にだけ在る接続は PRE を 0 とみなす。`conns=` は POST の接続 label 数、`gone=` は PRE にだけ在る label 数)。`scope=platform` は `platform_db_time_stats()`(r2db: `_credentials`/`_application_durable_audit` の 2 つの `_RolePool.platform_stats()` の和。MitateDB: credential store / audit sink の per-call store の `platform_stats()` の和) の PRE/POST 差分。`scope=platform` の `db_calls=` も PRE/POST 差分 (platform accessor の `execute_count + executemany_count` の畳み込み和)。`db_wall_ms_per_req=` は `scope=app` が `db_wall_ms / requests`、`scope=platform` が `(db_wall_ms + connect_wall_ms) / requests`。

**`txns` の定義**: `commit()`/`rollback()`/`transaction()` の enter・exit の呼び出し回数 (SAVEPOINT/RELEASE を含む)。**R-80 の `ROUNDTRIP` 行の `xacts`(`pg_stat_database.xact_commit + xact_rollback` の差分、サーバ側)とは単位が違うので比べない。**

**`DSA_PERF_THREAD_LIMIT`**: 正整数のとき、data-plane app を薄い ASGI wrapper (`_PerfThreadLimitWrapper`) で包み、実行中の loop で最初の要求のときだけ `anyio.to_thread.current_default_thread_limiter().total_tokens` をその値に設定する (loop ごとに 1 回)。無し・無効 (0 以下、非数) のときは wrapper を作らず、app の identity は既存のまま。`DSA_PERF_POOL_SIZE` は r2db-api の `-http`/`-socket` のみ (既存、R-78)。**この 2 つの環境変数を残したまま `pytest` を走らせない。**

**thread limit × K の sweep 計画 (WP-2 が実施)**: 両 peer の `-http`/`-socket` (in_process は同じ run に出るが判定の表からは外す) で、thread limit ∈ {既定 (env 無し) = 40, 4, 1} × K ∈ {1, 4, 32}、`DSA_PERF_POOL_SIZE=32` 固定、`--warmup`/`--n` は R-78 の表 (K ≤ 4: 10/100、K=32: 3/15) に、「既定 × K=32」の 2 回目の run を足した計 10 run。**ε と δ の求め方**: 2 回取った「既定 × K=32」の `query` の p50 の相対差を plug ごとに ε とし、判定の閾値 **δ = max(10%, 2ε)** を plug ごとに §3 で確定する。

**`POOL lock=` の `acquire` に op ごと probe 2 回分が含まれる事実**: R-78/R-79 時点では `PREPARED` 行の POST `prepared_stats()` 呼び出し (MitateDB では `ApplicationCell.prepared_stats()` がその都度 cell の `RLock` を取る) が op ごと 1 回だった。本 WP からは `DBTIME` 行のための PRE snapshot 呼び出しが同じ op に 1 回追加されるので、**MitateDB の `POOL lock=` の `acquire` は、2 つ目以降の op では probe 2 回分 (その op 自身の PRE と、直前の op の POST。POST は直前の op の `POOL` 行の印字より後に走るので次の op の行に現れる) を含み、最初の op だけは自身の PRE の 1 回分を含む** (`MitateDB-api/src/mitatedb_api/cell.py:615` 付近の `ApplicationCell.prepared_stats`。`tools/PERF_BASELINE_README.md` の `DBTIME` 節の同一記述を参照)。

**合成環境である旨**: 以下の実測 (WP-2 が §2 に記す) はすべて開発機のローカルの使い捨て PostgreSQL クラスタに対するものであり、ホスト名・実 DSN・作業機の絶対パスは記録しない (WO §1.1 の (d)、`OPERATING_CONDITIONS.md` §1.9)。`PERFRUN` の `host=` は `<OS/arch>` の形式である。

## 2. 実測 (WP-2 = 監督が埋める)

監督、2026-09-27、worktree `r101` (commit `3d10d7d`) の道具、開発機のローカルの使い捨て PostgreSQL クラスタ (`tools/perf_baseline.py` 自身が起動)。`PERFRUN` の `host=` と role の application id は伏せた (合成値)。in-process plug (r2db = in-memory、MitateDB = SQLite) は PostgreSQL を通らず判定の表からは外すが、逐語には残す。各 run は他の pytest / nginx が走っていない時間に直列で取った (排他は suite lock)。

### 2.1 非退行 (D-4 の (ii)。基点 `a1c1ee3` の道具 = `.claude/worktrees/r101-base` (detached) と本 worktree の道具。`DSA_PERF_POOL_SIZE=32`、`DSA_PERF_THREAD_LIMIT` 無し。K=1 は 3 組 (1 組目の `r2db-api-http` `batch` が +11.7% で ±10% を外れたため、同条件で 2 組を追加した)、K=3 は 1 組。組の中は base → worktree の順に連続実行)

#### 非退行 K=1 (run1) 基点の道具 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=a1c1ee3 date=2026-09-27
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.115 p95_ms=0.135 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.164 p95_ms=0.208 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.520 p95_ms=0.721 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.133 p95_ms=0.144 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.102 p95_ms=0.112 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.178 p95_ms=0.190 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.127 p95_ms=0.135 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.370 p95_ms=1.450 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.442 p95_ms=1.519 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.602 p95_ms=1.694 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_54bfe958 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.304 p95_ms=6.476 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.042 p95_ms=6.208 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.444 p95_ms=7.966 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.636 p95_ms=7.680 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.903 p95_ms=5.212 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.897 p95_ms=5.033 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.064 p95_ms=5.246 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_9929e068 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.894 p95_ms=11.232 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.641 p95_ms=10.982 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=11.079 p95_ms=12.500 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.006 p95_ms=11.340 backend_calls=22.00 concurrency=1
```

#### 非退行 K=1 (run1) 本 worktree の道具 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=11.607 cpu_total_ms=6.213 cpu_main_ms=6.210 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=16.840 cpu_total_ms=11.373 cpu_main_ms=11.372 cpu_other_ms=0.001
CPU peer=r2db-api plug=r2db-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=51.569 cpu_total_ms=46.062 cpu_main_ms=46.060 cpu_other_ms=0.002
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.113 p95_ms=0.128 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.174 p95_ms=0.205 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.527 p95_ms=0.700 backend_calls=1.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=14.156 cpu_total_ms=8.691 cpu_main_ms=8.689 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=10.522 cpu_total_ms=5.095 cpu_main_ms=5.094 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=17.705 cpu_total_ms=12.249 cpu_main_ms=12.248 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=13.476 cpu_total_ms=8.043 cpu_main_ms=8.041 cpu_other_ms=0.002
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.141 p95_ms=0.144 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.104 p95_ms=0.115 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.177 p95_ms=0.189 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.136 p95_ms=0.141 backend_calls=16.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=147.818 cpu_total_ms=81.070 cpu_main_ms=25.577 cpu_other_ms=55.493
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=46.975 db_wall_ms_per_req=0.470
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=37.970 db_wall_ms_per_req=0.380
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=152.153 cpu_total_ms=81.700 cpu_main_ms=25.032 cpu_other_ms=56.668
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=54.409 db_wall_ms_per_req=0.544
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=37.717 db_wall_ms_per_req=0.377
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=222.884 cpu_total_ms=124.663 cpu_main_ms=38.052 cpu_other_ms=86.611
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=81.777 db_wall_ms_per_req=0.818
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=48.905 db_wall_ms_per_req=0.489
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.472 p95_ms=1.567 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.510 p95_ms=1.615 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.789 p95_ms=4.923 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=666.078 cpu_total_ms=368.187 cpu_main_ms=32.772 cpu_other_ms=335.415
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=69.610 db_wall_ms_per_req=0.696
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=439.638 db_calls=200 txns=0 db_wall_ms=84.550 db_wall_ms_per_req=5.242
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=635.850 cpu_total_ms=349.872 cpu_main_ms=32.732 cpu_other_ms=317.140
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=45.804 db_wall_ms_per_req=0.458
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=439.728 db_calls=200 txns=0 db_wall_ms=84.170 db_wall_ms_per_req=5.239
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=800.472 cpu_total_ms=429.138 cpu_main_ms=36.249 cpu_other_ms=392.889
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=165.472 db_wall_ms_per_req=1.655
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=452.407 db_calls=200 txns=0 db_wall_ms=91.255 db_wall_ms_per_req=5.437
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=659.847 cpu_total_ms=363.910 cpu_main_ms=31.552 cpu_other_ms=332.358
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_3cb11d6e acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=74.717 db_wall_ms_per_req=0.747
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=432.459 db_calls=200 txns=0 db_wall_ms=83.133 db_wall_ms_per_req=5.156
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.604 p95_ms=7.080 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.271 p95_ms=6.681 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.697 p95_ms=9.606 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.566 p95_ms=6.892 backend_calls=22.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=511.263 cpu_total_ms=411.296 cpu_main_ms=323.056 cpu_other_ms=88.241
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=52.818 db_wall_ms_per_req=0.528
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=42.419 db_wall_ms_per_req=0.424
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=496.294 cpu_total_ms=396.738 cpu_main_ms=310.945 cpu_other_ms=85.793
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=58.386 db_wall_ms_per_req=0.584
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=40.060 db_wall_ms_per_req=0.401
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=505.873 cpu_total_ms=404.523 cpu_main_ms=307.709 cpu_other_ms=96.814
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=65.541 db_wall_ms_per_req=0.655
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.600 db_wall_ms_per_req=0.396
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.941 p95_ms=6.159 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.934 p95_ms=5.220 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.047 p95_ms=5.208 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=1015.867 cpu_total_ms=686.944 cpu_main_ms=311.939 cpu_other_ms=375.005
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=70.419 db_wall_ms_per_req=0.704
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=454.987 db_calls=200 txns=0 db_wall_ms=86.009 db_wall_ms_per_req=5.410
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=1045.226 cpu_total_ms=694.505 cpu_main_ms=324.214 cpu_other_ms=370.291
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=53.975 db_wall_ms_per_req=0.540
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=473.590 db_calls=200 txns=0 db_wall_ms=96.431 db_wall_ms_per_req=5.700
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=1160.431 cpu_total_ms=760.781 cpu_main_ms=324.384 cpu_other_ms=436.397
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=165.211 db_wall_ms_per_req=1.652
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=468.100 db_calls=200 txns=0 db_wall_ms=91.327 db_wall_ms_per_req=5.594
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=1107.426 cpu_total_ms=730.183 cpu_main_ms=333.758 cpu_other_ms=396.425
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_65cd02ca acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=85.055 db_wall_ms_per_req=0.851
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=484.572 db_calls=200 txns=0 db_wall_ms=99.589 db_wall_ms_per_req=5.842
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.935 p95_ms=11.271 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.923 p95_ms=11.526 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=11.267 p95_ms=12.853 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.972 p95_ms=12.337 backend_calls=22.00 concurrency=1
```

#### 非退行 K=1 (run2) 基点の道具 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=a1c1ee3 date=2026-09-27
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.116 p95_ms=0.121 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.168 p95_ms=0.209 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.521 p95_ms=0.705 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.143 p95_ms=0.148 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.110 p95_ms=0.116 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.180 p95_ms=0.186 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.137 p95_ms=0.143 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.441 p95_ms=1.529 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.512 p95_ms=1.693 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.673 p95_ms=1.739 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_bd4185df acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.310 p95_ms=7.171 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=5.986 p95_ms=6.201 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.300 p95_ms=7.457 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.362 p95_ms=6.536 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.812 p95_ms=4.962 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.873 p95_ms=5.028 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.044 p95_ms=5.173 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_a6ccb08d acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.915 p95_ms=11.204 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.530 p95_ms=10.863 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=10.804 p95_ms=12.175 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=9.852 p95_ms=11.252 backend_calls=22.00 concurrency=1
```

#### 非退行 K=1 (run2) 本 worktree の道具 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=11.896 cpu_total_ms=6.457 cpu_main_ms=6.455 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=17.013 cpu_total_ms=11.548 cpu_main_ms=11.546 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=51.608 cpu_total_ms=46.175 cpu_main_ms=46.173 cpu_other_ms=0.002
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.117 p95_ms=0.132 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.168 p95_ms=0.216 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.516 p95_ms=0.693 backend_calls=1.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=14.003 cpu_total_ms=8.564 cpu_main_ms=8.562 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=11.016 cpu_total_ms=5.554 cpu_main_ms=5.552 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=17.456 cpu_total_ms=12.009 cpu_main_ms=12.007 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=12.885 cpu_total_ms=7.441 cpu_main_ms=7.441 cpu_other_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.142 p95_ms=0.151 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.109 p95_ms=0.118 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.172 p95_ms=0.188 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.129 p95_ms=0.134 backend_calls=16.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=150.709 cpu_total_ms=83.354 cpu_main_ms=26.212 cpu_other_ms=57.142
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=47.611 db_wall_ms_per_req=0.476
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.291 db_wall_ms_per_req=0.393
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=167.584 cpu_total_ms=91.724 cpu_main_ms=29.805 cpu_other_ms=61.919
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=58.818 db_wall_ms_per_req=0.588
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=41.056 db_wall_ms_per_req=0.411
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=174.098 cpu_total_ms=98.635 cpu_main_ms=26.597 cpu_other_ms=72.038
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=64.210 db_wall_ms_per_req=0.642
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.295 db_wall_ms_per_req=0.393
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.496 p95_ms=1.590 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.633 p95_ms=1.881 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.732 p95_ms=1.812 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=646.752 cpu_total_ms=361.229 cpu_main_ms=30.031 cpu_other_ms=331.198
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=67.974 db_wall_ms_per_req=0.680
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=430.355 db_calls=200 txns=0 db_wall_ms=81.193 db_wall_ms_per_req=5.115
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=611.244 cpu_total_ms=340.220 cpu_main_ms=29.269 cpu_other_ms=310.951
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=42.897 db_wall_ms_per_req=0.429
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=426.915 db_calls=200 txns=0 db_wall_ms=80.634 db_wall_ms_per_req=5.075
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=751.717 cpu_total_ms=412.687 cpu_main_ms=30.404 cpu_other_ms=382.283
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=158.771 db_wall_ms_per_req=1.588
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=430.529 db_calls=200 txns=0 db_wall_ms=81.360 db_wall_ms_per_req=5.119
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=651.825 cpu_total_ms=360.970 cpu_main_ms=30.003 cpu_other_ms=330.967
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_86e1165d acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=73.146 db_wall_ms_per_req=0.731
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=430.103 db_calls=200 txns=0 db_wall_ms=81.659 db_wall_ms_per_req=5.118
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.452 p95_ms=6.623 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.105 p95_ms=6.270 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.497 p95_ms=7.718 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.513 p95_ms=6.712 backend_calls=22.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=492.140 cpu_total_ms=398.065 cpu_main_ms=314.699 cpu_other_ms=83.366
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=50.550 db_wall_ms_per_req=0.505
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=40.152 db_wall_ms_per_req=0.402
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=503.097 cpu_total_ms=403.418 cpu_main_ms=317.206 cpu_other_ms=86.212
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=58.623 db_wall_ms_per_req=0.586
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=40.789 db_wall_ms_per_req=0.408
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=518.663 cpu_total_ms=416.059 cpu_main_ms=317.136 cpu_other_ms=98.923
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=67.111 db_wall_ms_per_req=0.671
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=40.431 db_wall_ms_per_req=0.404
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.918 p95_ms=5.052 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=5.019 p95_ms=5.167 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.174 p95_ms=5.345 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=1018.757 cpu_total_ms=691.770 cpu_main_ms=315.332 cpu_other_ms=376.438
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=70.046 db_wall_ms_per_req=0.700
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=455.134 db_calls=200 txns=0 db_wall_ms=86.384 db_wall_ms_per_req=5.415
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=1001.334 cpu_total_ms=681.796 cpu_main_ms=319.687 cpu_other_ms=362.109
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=46.494 db_wall_ms_per_req=0.465
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=458.822 db_calls=200 txns=0 db_wall_ms=88.747 db_wall_ms_per_req=5.476
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=1132.092 cpu_total_ms=750.330 cpu_main_ms=319.524 cpu_other_ms=430.806
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=162.671 db_wall_ms_per_req=1.627
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=456.955 db_calls=200 txns=0 db_wall_ms=86.867 db_wall_ms_per_req=5.438
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=1030.009 cpu_total_ms=697.348 cpu_main_ms=320.031 cpu_other_ms=377.317
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_eb638a19 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=76.440 db_wall_ms_per_req=0.764
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=454.884 db_calls=200 txns=0 db_wall_ms=86.671 db_wall_ms_per_req=5.416
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=10.003 p95_ms=11.388 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.750 p95_ms=11.116 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=11.157 p95_ms=12.521 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.063 p95_ms=11.490 backend_calls=22.00 concurrency=1
```

#### 非退行 K=1 (run3) 基点の道具 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=a1c1ee3 date=2026-09-27
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.125 p95_ms=0.137 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.174 p95_ms=0.213 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.518 p95_ms=0.724 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.136 p95_ms=0.147 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.100 p95_ms=0.116 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.178 p95_ms=0.185 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.138 p95_ms=0.143 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.486 p95_ms=1.547 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.554 p95_ms=1.649 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.740 p95_ms=1.907 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_f963e6ae acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.389 p95_ms=6.558 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.998 p95_ms=8.906 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.437 p95_ms=7.708 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.480 p95_ms=6.694 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.907 p95_ms=5.039 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.974 p95_ms=5.136 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.142 p95_ms=5.310 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_1968dcf5 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.947 p95_ms=11.331 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.756 p95_ms=11.117 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=11.140 p95_ms=12.508 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.021 p95_ms=11.475 backend_calls=22.00 concurrency=1
```

#### 非退行 K=1 (run3) 本 worktree の道具 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=11.965 cpu_total_ms=6.487 cpu_main_ms=6.484 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=17.045 cpu_total_ms=11.577 cpu_main_ms=11.576 cpu_other_ms=0.001
CPU peer=r2db-api plug=r2db-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=51.742 cpu_total_ms=46.262 cpu_main_ms=46.261 cpu_other_ms=0.001
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.117 p95_ms=0.136 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.169 p95_ms=0.210 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.520 p95_ms=0.708 backend_calls=1.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=13.175 cpu_total_ms=7.776 cpu_main_ms=7.775 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=11.066 cpu_total_ms=5.588 cpu_main_ms=5.586 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=18.001 cpu_total_ms=12.503 cpu_main_ms=12.501 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=12.828 cpu_total_ms=7.365 cpu_main_ms=7.364 cpu_other_ms=0.001
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.132 p95_ms=0.136 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.110 p95_ms=0.117 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.178 p95_ms=0.193 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.128 p95_ms=0.132 backend_calls=16.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=150.683 cpu_total_ms=83.067 cpu_main_ms=25.939 cpu_other_ms=57.128
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=47.716 db_wall_ms_per_req=0.477
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.269 db_wall_ms_per_req=0.393
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=157.031 cpu_total_ms=84.858 cpu_main_ms=25.898 cpu_other_ms=58.960
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=55.873 db_wall_ms_per_req=0.559
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.413 db_wall_ms_per_req=0.394
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=175.078 cpu_total_ms=99.318 cpu_main_ms=26.581 cpu_other_ms=72.737
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=64.815 db_wall_ms_per_req=0.648
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.491 db_wall_ms_per_req=0.395
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.497 p95_ms=1.590 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.562 p95_ms=1.642 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.745 p95_ms=1.835 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=650.065 cpu_total_ms=360.386 cpu_main_ms=30.788 cpu_other_ms=329.598
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=68.016 db_wall_ms_per_req=0.680
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=430.400 db_calls=200 txns=0 db_wall_ms=83.033 db_wall_ms_per_req=5.134
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=613.244 cpu_total_ms=339.156 cpu_main_ms=29.583 cpu_other_ms=309.573
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=42.943 db_wall_ms_per_req=0.429
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=427.883 db_calls=200 txns=0 db_wall_ms=81.023 db_wall_ms_per_req=5.089
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=749.893 cpu_total_ms=410.605 cpu_main_ms=30.169 cpu_other_ms=380.436
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=158.293 db_wall_ms_per_req=1.583
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=429.272 db_calls=200 txns=0 db_wall_ms=81.742 db_wall_ms_per_req=5.110
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=651.914 cpu_total_ms=359.580 cpu_main_ms=29.885 cpu_other_ms=329.695
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_c98983c4 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=73.094 db_wall_ms_per_req=0.731
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=429.352 db_calls=200 txns=0 db_wall_ms=82.671 db_wall_ms_per_req=5.120
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.480 p95_ms=6.757 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.118 p95_ms=6.358 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.487 p95_ms=7.689 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.508 p95_ms=6.713 backend_calls=22.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=487.737 cpu_total_ms=393.742 cpu_main_ms=310.157 cpu_other_ms=83.585
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=50.166 db_wall_ms_per_req=0.502
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=40.669 db_wall_ms_per_req=0.407
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=498.939 cpu_total_ms=399.558 cpu_main_ms=314.109 cpu_other_ms=85.449
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=58.431 db_wall_ms_per_req=0.584
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=40.422 db_wall_ms_per_req=0.404
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=521.480 cpu_total_ms=417.330 cpu_main_ms=317.157 cpu_other_ms=100.173
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=68.597 db_wall_ms_per_req=0.686
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=40.816 db_wall_ms_per_req=0.408
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.868 p95_ms=5.000 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.972 p95_ms=5.130 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.146 p95_ms=5.445 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=1012.128 cpu_total_ms=685.521 cpu_main_ms=313.592 cpu_other_ms=371.929
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=69.852 db_wall_ms_per_req=0.699
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=451.156 db_calls=200 txns=0 db_wall_ms=85.772 db_wall_ms_per_req=5.369
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=986.227 cpu_total_ms=672.556 cpu_main_ms=315.736 cpu_other_ms=356.820
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=45.997 db_wall_ms_per_req=0.460
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=453.091 db_calls=200 txns=0 db_wall_ms=85.830 db_wall_ms_per_req=5.389
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=1133.705 cpu_total_ms=749.818 cpu_main_ms=319.532 cpu_other_ms=430.286
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=163.195 db_wall_ms_per_req=1.632
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=456.913 db_calls=200 txns=0 db_wall_ms=86.805 db_wall_ms_per_req=5.437
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=1024.356 cpu_total_ms=692.590 cpu_main_ms=316.630 cpu_other_ms=375.960
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_7286aebf acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=76.800 db_wall_ms_per_req=0.768
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=453.581 db_calls=200 txns=0 db_wall_ms=86.125 db_wall_ms_per_req=5.397
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.955 p95_ms=11.289 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.707 p95_ms=11.061 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=11.115 p95_ms=12.521 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.094 p95_ms=11.436 backend_calls=22.00 concurrency=1
```

#### 非退行 K=3 (run1) 基点の道具 `--warmup 10 --n 100 --concurrency 3`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=a1c1ee3 date=2026-09-27
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.217 p95_ms=0.238 backend_calls=1.00 concurrency=3
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.670 p95_ms=1.010 backend_calls=1.00 concurrency=3
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=3.413 p95_ms=5.066 backend_calls=1.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.261 p95_ms=0.275 backend_calls=11.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.162 p95_ms=0.171 backend_calls=7.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.368 p95_ms=0.380 backend_calls=37.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.251 p95_ms=0.261 backend_calls=16.00 concurrency=3
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=991 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=2.761 p95_ms=2.902 backend_calls=14.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=2.854 p95_ms=2.980 backend_calls=15.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=3.363 p95_ms=3.562 backend_calls=19.01 concurrency=3
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=666 waits=204 wait_total_ms=153.865 wait_max_ms=5.084
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1327 waits=368 wait_total_ms=220.348 wait_max_ms=5.084
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=1988 waits=588 wait_total_ms=759.542 wait_max_ms=31.269
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_e19680cb acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=2653 waits=798 wait_total_ms=937.778 wait_max_ms=31.269
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=12.307 p95_ms=14.638 backend_calls=21.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=11.150 p95_ms=12.357 backend_calls=13.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=15.066 p95_ms=15.731 backend_calls=49.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=12.081 p95_ms=12.779 backend_calls=22.00 concurrency=3
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=991 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=12.608 p95_ms=13.320 backend_calls=14.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=12.641 p95_ms=13.033 backend_calls=15.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=13.207 p95_ms=15.528 backend_calls=19.01 concurrency=3
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=666 waits=162 wait_total_ms=152.122 wait_max_ms=4.717
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1327 waits=323 wait_total_ms=252.641 wait_max_ms=4.717
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=1988 waits=536 wait_total_ms=820.827 wait_max_ms=23.993
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_bfb25ecf acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=2653 waits=729 wait_total_ms=1088.728 wait_max_ms=23.993
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=21.982 p95_ms=24.042 backend_calls=21.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=21.020 p95_ms=21.828 backend_calls=13.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=25.753 p95_ms=27.693 backend_calls=49.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=22.833 p95_ms=26.037 backend_calls=22.00 concurrency=3
```

#### 非退行 K=3 (run1) 本 worktree の道具 `--warmup 10 --n 100 --concurrency 3`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=3 thread_limit=default requests=300 wall_ms=20.954 cpu_total_ms=15.473 cpu_main_ms=15.470 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=3 thread_limit=default requests=300 wall_ms=67.607 cpu_total_ms=62.063 cpu_main_ms=62.061 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=3 thread_limit=default requests=300 wall_ms=355.416 cpu_total_ms=349.702 cpu_main_ms=349.699 cpu_other_ms=0.003
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.209 p95_ms=0.232 backend_calls=1.00 concurrency=3
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.692 p95_ms=1.014 backend_calls=1.00 concurrency=3
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=3.574 p95_ms=5.545 backend_calls=1.00 concurrency=3
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=3 thread_limit=default requests=300 wall_ms=27.012 cpu_total_ms=21.557 cpu_main_ms=21.555 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=3 thread_limit=default requests=300 wall_ms=16.968 cpu_total_ms=11.459 cpu_main_ms=11.458 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=3 thread_limit=default requests=300 wall_ms=36.828 cpu_total_ms=31.320 cpu_main_ms=31.318 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=3 thread_limit=default requests=300 wall_ms=24.644 cpu_total_ms=19.127 cpu_main_ms=19.127 cpu_other_ms=-0.000
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.269 p95_ms=0.282 backend_calls=11.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.169 p95_ms=0.181 backend_calls=7.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.366 p95_ms=0.378 backend_calls=37.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.244 p95_ms=0.254 backend_calls=16.00 concurrency=3
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=3 thread_limit=default requests=300 wall_ms=294.803 cpu_total_ms=316.669 cpu_main_ms=71.067 cpu_other_ms=245.602
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=3 scope=app conns=4 gone=0 db_calls=1800 txns=600 db_wall_ms=266.319 db_wall_ms_per_req=0.888
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=3 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=2400 txns=1200 db_wall_ms=280.367 db_wall_ms_per_req=0.935
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=3 thread_limit=default requests=300 wall_ms=294.549 cpu_total_ms=321.624 cpu_main_ms=72.611 cpu_other_ms=249.013
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=3 scope=app conns=4 gone=0 db_calls=2100 txns=1200 db_wall_ms=270.518 db_wall_ms_per_req=0.902
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=3 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=2400 txns=1200 db_wall_ms=276.524 db_wall_ms_per_req=0.922
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=3 thread_limit=default requests=300 wall_ms=369.472 cpu_total_ms=400.350 cpu_main_ms=75.587 cpu_other_ms=324.763
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=991 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=3 scope=app conns=4 gone=0 db_calls=3300 txns=1200 db_wall_ms=382.766 db_wall_ms_per_req=1.276
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=3 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=2402 txns=1201 db_wall_ms=328.960 db_wall_ms_per_req=1.097
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=2.861 p95_ms=3.053 backend_calls=14.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=2.925 p95_ms=3.080 backend_calls=15.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=3.432 p95_ms=3.713 backend_calls=19.01 concurrency=3
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=3 thread_limit=default requests=300 wall_ms=1304.390 cpu_total_ms=2175.476 cpu_main_ms=102.939 cpu_other_ms=2072.537
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=667 waits=203 wait_total_ms=168.013 wait_max_ms=4.657
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=3 scope=app conns=2 gone=0 db_calls=5700 txns=1500 db_wall_ms=308.894 db_wall_ms_per_req=1.030
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=3 scope=platform sessions=600 connect_wall_ms=2531.748 db_calls=600 txns=0 db_wall_ms=316.095 db_wall_ms_per_req=9.493
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=3 thread_limit=default requests=300 wall_ms=1225.836 cpu_total_ms=2157.863 cpu_main_ms=103.265 cpu_other_ms=2054.598
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1329 waits=404 wait_total_ms=276.597 wait_max_ms=4.657
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=3 scope=app conns=2 gone=0 db_calls=3300 txns=1200 db_wall_ms=164.793 db_wall_ms_per_req=0.549
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=3 scope=platform sessions=600 connect_wall_ms=2569.589 db_calls=600 txns=0 db_wall_ms=314.088 db_wall_ms_per_req=9.612
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=3 thread_limit=default requests=300 wall_ms=1632.568 cpu_total_ms=2353.694 cpu_main_ms=103.738 cpu_other_ms=2249.956
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=1991 waits=624 wait_total_ms=856.452 wait_max_ms=30.040
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=3 scope=app conns=2 gone=0 db_calls=14100 txns=3600 db_wall_ms=498.756 db_wall_ms_per_req=1.663
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=3 scope=platform sessions=601 connect_wall_ms=2558.436 db_calls=601 txns=1 db_wall_ms=337.174 db_wall_ms_per_req=9.652
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=3 thread_limit=default requests=300 wall_ms=1316.588 cpu_total_ms=2203.683 cpu_main_ms=102.733 cpu_other_ms=2100.950
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_1c202b6e acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=2657 waits=840 wait_total_ms=1077.292 wait_max_ms=30.040
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=3 scope=app conns=4 gone=0 db_calls=6000 txns=1800 db_wall_ms=249.727 db_wall_ms_per_req=0.832
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=3 scope=platform sessions=600 connect_wall_ms=2558.464 db_calls=600 txns=0 db_wall_ms=324.155 db_wall_ms_per_req=9.609
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=13.020 p95_ms=14.186 backend_calls=21.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=12.251 p95_ms=13.040 backend_calls=13.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=15.952 p95_ms=17.162 backend_calls=49.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=13.085 p95_ms=13.766 backend_calls=22.00 concurrency=3
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=3 thread_limit=default requests=300 wall_ms=1265.033 cpu_total_ms=1282.546 cpu_main_ms=937.206 cpu_other_ms=345.340
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=3 scope=app conns=4 gone=0 db_calls=1800 txns=600 db_wall_ms=255.499 db_wall_ms_per_req=0.852
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=3 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=2400 txns=1200 db_wall_ms=340.583 db_wall_ms_per_req=1.135
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=3 thread_limit=default requests=300 wall_ms=1276.909 cpu_total_ms=1296.838 cpu_main_ms=941.109 cpu_other_ms=355.729
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=3 scope=app conns=4 gone=0 db_calls=2100 txns=1200 db_wall_ms=284.167 db_wall_ms_per_req=0.947
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=3 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=2400 txns=1200 db_wall_ms=340.545 db_wall_ms_per_req=1.135
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=3 thread_limit=default requests=300 wall_ms=1347.899 cpu_total_ms=1374.548 cpu_main_ms=943.376 cpu_other_ms=431.172
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=991 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=3
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=3 scope=app conns=4 gone=0 db_calls=3300 txns=1200 db_wall_ms=382.976 db_wall_ms_per_req=1.277
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=3 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=2402 txns=1201 db_wall_ms=389.578 db_wall_ms_per_req=1.299
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=12.627 p95_ms=12.995 backend_calls=14.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=12.756 p95_ms=13.067 backend_calls=15.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=13.133 p95_ms=14.083 backend_calls=19.01 concurrency=3
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=3 thread_limit=default requests=300 wall_ms=2153.316 cpu_total_ms=3001.969 cpu_main_ms=944.703 cpu_other_ms=2057.266
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=667 waits=160 wait_total_ms=148.028 wait_max_ms=4.683
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=3 scope=app conns=2 gone=0 db_calls=5700 txns=1500 db_wall_ms=343.705 db_wall_ms_per_req=1.146
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=3 scope=platform sessions=600 connect_wall_ms=2356.273 db_calls=600 txns=0 db_wall_ms=295.444 db_wall_ms_per_req=8.839
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=3 thread_limit=default requests=300 wall_ms=2104.435 cpu_total_ms=2980.293 cpu_main_ms=963.678 cpu_other_ms=2016.615
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1329 waits=322 wait_total_ms=255.033 wait_max_ms=4.683
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=3 scope=app conns=2 gone=0 db_calls=3300 txns=1200 db_wall_ms=213.152 db_wall_ms_per_req=0.711
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=3 scope=platform sessions=600 connect_wall_ms=2391.419 db_calls=600 txns=0 db_wall_ms=300.361 db_wall_ms_per_req=8.973
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=3 thread_limit=default requests=300 wall_ms=2554.672 cpu_total_ms=3253.210 cpu_main_ms=974.981 cpu_other_ms=2278.229
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=1991 waits=539 wait_total_ms=804.860 wait_max_ms=28.587
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=3 scope=app conns=2 gone=0 db_calls=14100 txns=3600 db_wall_ms=598.492 db_wall_ms_per_req=1.995
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=3 scope=platform sessions=601 connect_wall_ms=2439.881 db_calls=601 txns=1 db_wall_ms=339.526 db_wall_ms_per_req=9.265
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=3 thread_limit=default requests=300 wall_ms=2302.440 cpu_total_ms=3169.264 cpu_main_ms=984.357 cpu_other_ms=2184.907
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_37e5f449 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=2657 waits=728 wait_total_ms=1054.018 wait_max_ms=28.587
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=3 scope=app conns=4 gone=0 db_calls=6000 txns=1800 db_wall_ms=329.800 db_wall_ms_per_req=1.099
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=3 scope=platform sessions=600 connect_wall_ms=2539.797 db_calls=600 txns=0 db_wall_ms=319.851 db_wall_ms_per_req=9.532
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=21.096 p95_ms=22.956 backend_calls=21.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=21.025 p95_ms=22.934 backend_calls=13.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=25.210 p95_ms=27.153 backend_calls=49.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=22.698 p95_ms=25.363 backend_calls=22.00 concurrency=3
```

### 2.2 sweep (D-4 の (i)。本 worktree の道具、`DSA_PERF_POOL_SIZE=32`。thread limit は `DSA_PERF_THREAD_LIMIT` (無し = 既定 40)。K=32 は `--warmup 3 --n 15` で n が小さく分散が大きい。実行順は K ごとに 既定 → 4 → 1、最後に 既定 × K=32 の 2 回目。各 run の `CPU` 行の `thread_limit=` は小見出しと一致する (§3 の 10))

#### thread limit = 既定 (無し) × K=1 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=11.813 cpu_total_ms=6.401 cpu_main_ms=6.398 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=16.724 cpu_total_ms=11.259 cpu_main_ms=11.258 cpu_other_ms=0.001
CPU peer=r2db-api plug=r2db-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=51.471 cpu_total_ms=45.963 cpu_main_ms=45.961 cpu_other_ms=0.002
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.116 p95_ms=0.128 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.164 p95_ms=0.209 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.511 p95_ms=0.696 backend_calls=1.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=13.715 cpu_total_ms=8.263 cpu_main_ms=8.262 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=9.912 cpu_total_ms=4.487 cpu_main_ms=4.486 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=17.674 cpu_total_ms=12.222 cpu_main_ms=12.221 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=13.569 cpu_total_ms=8.034 cpu_main_ms=8.033 cpu_other_ms=0.001
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.135 p95_ms=0.151 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.098 p95_ms=0.105 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.177 p95_ms=0.182 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.136 p95_ms=0.144 backend_calls=16.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=148.227 cpu_total_ms=81.703 cpu_main_ms=25.600 cpu_other_ms=56.103
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=46.673 db_wall_ms_per_req=0.467
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.641 db_wall_ms_per_req=0.386
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=154.050 cpu_total_ms=83.112 cpu_main_ms=25.364 cpu_other_ms=57.748
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=54.415 db_wall_ms_per_req=0.544
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.847 db_wall_ms_per_req=0.388
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=170.476 cpu_total_ms=96.115 cpu_main_ms=25.691 cpu_other_ms=70.424
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=62.520 db_wall_ms_per_req=0.625
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.051 db_wall_ms_per_req=0.391
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.478 p95_ms=1.566 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.535 p95_ms=1.599 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.703 p95_ms=1.762 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 thread_limit=default requests=100 wall_ms=630.555 cpu_total_ms=348.487 cpu_main_ms=29.155 cpu_other_ms=319.332
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=66.559 db_wall_ms_per_req=0.666
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=418.931 db_calls=200 txns=0 db_wall_ms=79.213 db_wall_ms_per_req=4.981
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=598.732 cpu_total_ms=329.424 cpu_main_ms=28.555 cpu_other_ms=300.869
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=42.132 db_wall_ms_per_req=0.421
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=417.987 db_calls=200 txns=0 db_wall_ms=78.870 db_wall_ms_per_req=4.969
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 thread_limit=default requests=100 wall_ms=733.113 cpu_total_ms=398.596 cpu_main_ms=29.268 cpu_other_ms=369.328
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=155.492 db_wall_ms_per_req=1.555
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=419.262 db_calls=200 txns=0 db_wall_ms=79.393 db_wall_ms_per_req=4.987
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=638.376 cpu_total_ms=350.372 cpu_main_ms=29.424 cpu_other_ms=320.948
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_7cbedab7 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=72.142 db_wall_ms_per_req=0.721
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=420.514 db_calls=200 txns=0 db_wall_ms=79.795 db_wall_ms_per_req=5.003
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.301 p95_ms=6.426 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=5.983 p95_ms=6.125 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.330 p95_ms=7.482 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.359 p95_ms=6.591 backend_calls=22.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=485.859 cpu_total_ms=393.359 cpu_main_ms=312.036 cpu_other_ms=81.323
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=49.381 db_wall_ms_per_req=0.494
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.926 db_wall_ms_per_req=0.389
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=495.386 cpu_total_ms=397.489 cpu_main_ms=313.735 cpu_other_ms=83.754
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=57.266 db_wall_ms_per_req=0.573
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.322 db_wall_ms_per_req=0.393
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=510.024 cpu_total_ms=409.328 cpu_main_ms=313.347 cpu_other_ms=95.981
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=65.363 db_wall_ms_per_req=0.654
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.827 db_wall_ms_per_req=0.388
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.834 p95_ms=5.038 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.930 p95_ms=5.123 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.096 p95_ms=5.215 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 thread_limit=default requests=100 wall_ms=1005.917 cpu_total_ms=680.018 cpu_main_ms=311.852 cpu_other_ms=368.166
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=69.365 db_wall_ms_per_req=0.694
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=448.456 db_calls=200 txns=0 db_wall_ms=84.437 db_wall_ms_per_req=5.329
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=977.175 cpu_total_ms=666.029 cpu_main_ms=311.139 cpu_other_ms=354.890
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=45.682 db_wall_ms_per_req=0.457
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=450.862 db_calls=200 txns=0 db_wall_ms=83.875 db_wall_ms_per_req=5.347
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 thread_limit=default requests=100 wall_ms=1117.053 cpu_total_ms=738.296 cpu_main_ms=317.540 cpu_other_ms=420.756
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=160.090 db_wall_ms_per_req=1.601
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=445.032 db_calls=200 txns=0 db_wall_ms=85.089 db_wall_ms_per_req=5.301
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=1004.400 cpu_total_ms=678.945 cpu_main_ms=311.607 cpu_other_ms=367.338
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_4c472027 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=75.390 db_wall_ms_per_req=0.754
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=442.326 db_calls=200 txns=0 db_wall_ms=83.369 db_wall_ms_per_req=5.257
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.869 p95_ms=11.246 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.533 p95_ms=10.852 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=10.908 p95_ms=12.314 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=9.872 p95_ms=11.261 backend_calls=22.00 concurrency=1
```

#### thread limit = 4 × K=1 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=11.800 cpu_total_ms=6.293 cpu_main_ms=6.290 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=16.679 cpu_total_ms=11.228 cpu_main_ms=11.226 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=51.634 cpu_total_ms=46.081 cpu_main_ms=46.080 cpu_other_ms=0.001
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.115 p95_ms=0.141 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.163 p95_ms=0.213 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.516 p95_ms=0.699 backend_calls=1.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=13.378 cpu_total_ms=7.921 cpu_main_ms=7.920 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=10.513 cpu_total_ms=5.104 cpu_main_ms=5.103 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=17.570 cpu_total_ms=12.147 cpu_main_ms=12.146 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=13.438 cpu_total_ms=7.839 cpu_main_ms=7.838 cpu_other_ms=0.001
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.132 p95_ms=0.153 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.105 p95_ms=0.115 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.176 p95_ms=0.184 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.130 p95_ms=0.158 backend_calls=16.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=1 thread_limit=4 requests=100 wall_ms=148.641 cpu_total_ms=82.004 cpu_main_ms=25.881 cpu_other_ms=56.123
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=47.083 db_wall_ms_per_req=0.471
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.108 db_wall_ms_per_req=0.381
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=154.539 cpu_total_ms=83.578 cpu_main_ms=25.658 cpu_other_ms=57.920
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=54.810 db_wall_ms_per_req=0.548
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.483 db_wall_ms_per_req=0.385
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=177.513 cpu_total_ms=100.623 cpu_main_ms=27.770 cpu_other_ms=72.853
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=65.854 db_wall_ms_per_req=0.659
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.451 db_wall_ms_per_req=0.395
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.476 p95_ms=1.620 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.538 p95_ms=1.624 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.744 p95_ms=1.905 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 thread_limit=4 requests=100 wall_ms=637.654 cpu_total_ms=351.266 cpu_main_ms=29.749 cpu_other_ms=321.517
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=66.701 db_wall_ms_per_req=0.667
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=423.166 db_calls=200 txns=0 db_wall_ms=80.989 db_wall_ms_per_req=5.042
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=604.135 cpu_total_ms=331.811 cpu_main_ms=29.045 cpu_other_ms=302.766
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=42.497 db_wall_ms_per_req=0.425
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=420.737 db_calls=200 txns=0 db_wall_ms=80.417 db_wall_ms_per_req=5.012
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=739.765 cpu_total_ms=401.315 cpu_main_ms=30.078 cpu_other_ms=371.237
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=156.448 db_wall_ms_per_req=1.564
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=421.933 db_calls=200 txns=0 db_wall_ms=81.255 db_wall_ms_per_req=5.032
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 thread_limit=4 requests=100 wall_ms=642.036 cpu_total_ms=351.628 cpu_main_ms=29.663 cpu_other_ms=321.965
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_6005f0cb acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=72.154 db_wall_ms_per_req=0.722
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=422.395 db_calls=200 txns=0 db_wall_ms=81.081 db_wall_ms_per_req=5.035
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.360 p95_ms=6.543 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.031 p95_ms=6.197 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.380 p95_ms=7.601 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.410 p95_ms=6.552 backend_calls=22.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=1 thread_limit=4 requests=100 wall_ms=490.209 cpu_total_ms=395.046 cpu_main_ms=312.800 cpu_other_ms=82.246
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=49.650 db_wall_ms_per_req=0.497
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.512 db_wall_ms_per_req=0.395
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=494.194 cpu_total_ms=397.052 cpu_main_ms=313.224 cpu_other_ms=83.828
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=56.821 db_wall_ms_per_req=0.568
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.282 db_wall_ms_per_req=0.393
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=511.380 cpu_total_ms=410.351 cpu_main_ms=312.958 cpu_other_ms=97.393
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=65.429 db_wall_ms_per_req=0.654
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.524 db_wall_ms_per_req=0.395
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.870 p95_ms=5.039 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.931 p95_ms=5.065 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.103 p95_ms=5.238 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 thread_limit=4 requests=100 wall_ms=1004.882 cpu_total_ms=677.579 cpu_main_ms=311.516 cpu_other_ms=366.063
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=68.925 db_wall_ms_per_req=0.689
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=446.836 db_calls=200 txns=0 db_wall_ms=84.916 db_wall_ms_per_req=5.318
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=984.824 cpu_total_ms=670.695 cpu_main_ms=314.253 cpu_other_ms=356.442
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=45.736 db_wall_ms_per_req=0.457
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=453.420 db_calls=200 txns=0 db_wall_ms=85.255 db_wall_ms_per_req=5.387
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=1110.562 cpu_total_ms=734.187 cpu_main_ms=314.318 cpu_other_ms=419.869
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=159.674 db_wall_ms_per_req=1.597
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=446.543 db_calls=200 txns=0 db_wall_ms=84.761 db_wall_ms_per_req=5.313
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 thread_limit=4 requests=100 wall_ms=1004.465 cpu_total_ms=678.583 cpu_main_ms=311.835 cpu_other_ms=366.748
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_c35e85a9 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=74.978 db_wall_ms_per_req=0.750
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=442.862 db_calls=200 txns=0 db_wall_ms=83.973 db_wall_ms_per_req=5.268
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.858 p95_ms=11.253 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.593 p95_ms=11.003 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=10.932 p95_ms=12.358 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=9.885 p95_ms=11.240 backend_calls=22.00 concurrency=1
```

#### thread limit = 1 × K=1 `--warmup 10 --n 100 --concurrency 1`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=12.664 cpu_total_ms=7.193 cpu_main_ms=7.191 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=17.429 cpu_total_ms=11.967 cpu_main_ms=11.966 cpu_other_ms=0.001
CPU peer=r2db-api plug=r2db-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=51.756 cpu_total_ms=46.235 cpu_main_ms=46.235 cpu_other_ms=-0.000
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.125 p95_ms=0.132 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.173 p95_ms=0.214 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.517 p95_ms=0.705 backend_calls=1.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=13.457 cpu_total_ms=8.059 cpu_main_ms=8.057 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=10.057 cpu_total_ms=4.680 cpu_main_ms=4.679 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=17.371 cpu_total_ms=11.797 cpu_main_ms=11.795 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=13.938 cpu_total_ms=8.375 cpu_main_ms=8.374 cpu_other_ms=0.001
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.131 p95_ms=0.150 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.099 p95_ms=0.111 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.168 p95_ms=0.186 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.137 p95_ms=0.157 backend_calls=16.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=1 thread_limit=1 requests=100 wall_ms=149.885 cpu_total_ms=82.728 cpu_main_ms=26.020 cpu_other_ms=56.708
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=47.303 db_wall_ms_per_req=0.473
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.774 db_wall_ms_per_req=0.388
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 thread_limit=1 requests=100 wall_ms=175.730 cpu_total_ms=95.722 cpu_main_ms=31.468 cpu_other_ms=64.254
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=61.189 db_wall_ms_per_req=0.612
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=42.623 db_wall_ms_per_req=0.426
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=1 thread_limit=1 requests=100 wall_ms=176.178 cpu_total_ms=99.417 cpu_main_ms=27.424 cpu_other_ms=71.993
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=64.924 db_wall_ms_per_req=0.649
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.529 db_wall_ms_per_req=0.395
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.489 p95_ms=1.592 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.646 p95_ms=2.269 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.729 p95_ms=1.934 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 thread_limit=1 requests=100 wall_ms=640.675 cpu_total_ms=351.677 cpu_main_ms=29.982 cpu_other_ms=321.695
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=67.228 db_wall_ms_per_req=0.672
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=424.342 db_calls=200 txns=0 db_wall_ms=81.713 db_wall_ms_per_req=5.061
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 thread_limit=1 requests=100 wall_ms=606.329 cpu_total_ms=332.375 cpu_main_ms=29.151 cpu_other_ms=303.224
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=42.502 db_wall_ms_per_req=0.425
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=422.721 db_calls=200 txns=0 db_wall_ms=80.489 db_wall_ms_per_req=5.032
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 thread_limit=1 requests=100 wall_ms=737.353 cpu_total_ms=400.272 cpu_main_ms=29.595 cpu_other_ms=370.677
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=155.488 db_wall_ms_per_req=1.555
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=422.218 db_calls=200 txns=0 db_wall_ms=80.367 db_wall_ms_per_req=5.026
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 thread_limit=1 requests=100 wall_ms=643.295 cpu_total_ms=351.673 cpu_main_ms=29.946 cpu_other_ms=321.727
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_9d0808e9 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=71.972 db_wall_ms_per_req=0.720
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=422.960 db_calls=200 txns=0 db_wall_ms=81.585 db_wall_ms_per_req=5.045
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.385 p95_ms=6.717 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.051 p95_ms=6.230 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.365 p95_ms=7.507 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.407 p95_ms=6.589 backend_calls=22.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=1 thread_limit=1 requests=100 wall_ms=483.465 cpu_total_ms=390.629 cpu_main_ms=308.785 cpu_other_ms=81.844
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=49.296 db_wall_ms_per_req=0.493
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.316 db_wall_ms_per_req=0.393
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 thread_limit=1 requests=100 wall_ms=497.328 cpu_total_ms=399.011 cpu_main_ms=313.484 cpu_other_ms=85.527
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=57.657 db_wall_ms_per_req=0.577
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.961 db_wall_ms_per_req=0.400
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 thread_limit=1 requests=100 wall_ms=528.290 cpu_total_ms=421.064 cpu_main_ms=319.559 cpu_other_ms=101.505
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=68.715 db_wall_ms_per_req=0.687
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=41.966 db_wall_ms_per_req=0.420
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.825 p95_ms=4.958 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.930 p95_ms=5.190 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.117 p95_ms=5.664 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 thread_limit=1 requests=100 wall_ms=1952.403 cpu_total_ms=1006.885 cpu_main_ms=462.112 cpu_other_ms=544.773
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=204.923 db_wall_ms_per_req=2.049
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=platform sessions=200 connect_wall_ms=794.266 db_calls=200 txns=0 db_wall_ms=198.674 db_wall_ms_per_req=9.929
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 thread_limit=1 requests=100 wall_ms=3202.693 cpu_total_ms=1359.784 cpu_main_ms=638.295 cpu_other_ms=721.489
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=316.238 db_wall_ms_per_req=3.162
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=platform sessions=200 connect_wall_ms=1182.457 db_calls=200 txns=0 db_wall_ms=343.503 db_wall_ms_per_req=15.260
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 thread_limit=1 requests=100 wall_ms=1256.530 cpu_total_ms=807.409 cpu_main_ms=352.651 cpu_other_ms=454.758
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=174.447 db_wall_ms_per_req=1.744
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=platform sessions=200 connect_wall_ms=502.495 db_calls=200 txns=0 db_wall_ms=100.130 db_wall_ms_per_req=6.026
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 thread_limit=1 requests=100 wall_ms=1011.378 cpu_total_ms=679.833 cpu_main_ms=310.981 cpu_other_ms=368.852
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_7f0960ef acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=76.013 db_wall_ms_per_req=0.760
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=platform sessions=200 connect_wall_ms=448.139 db_calls=200 txns=0 db_wall_ms=84.625 db_wall_ms_per_req=5.328
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=14.263 p95_ms=43.086 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=28.441 p95_ms=56.795 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=11.832 p95_ms=14.412 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=9.953 p95_ms=11.303 backend_calls=22.00 concurrency=1
```

#### thread limit = 既定 (無し) × K=4 `--warmup 10 --n 100 --concurrency 4`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=4 thread_limit=default requests=400 wall_ms=26.388 cpu_total_ms=20.965 cpu_main_ms=20.960 cpu_other_ms=0.005
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=107.150 cpu_total_ms=101.633 cpu_main_ms=101.631 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=4 thread_limit=default requests=400 wall_ms=626.566 cpu_total_ms=620.701 cpu_main_ms=620.700 cpu_other_ms=0.001
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.258 p95_ms=0.280 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=1.062 p95_ms=1.708 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=6.143 p95_ms=9.636 backend_calls=1.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=4 thread_limit=default requests=400 wall_ms=33.798 cpu_total_ms=28.333 cpu_main_ms=28.333 cpu_other_ms=0.000
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=21.222 cpu_total_ms=15.716 cpu_main_ms=15.714 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=4 thread_limit=default requests=400 wall_ms=46.773 cpu_total_ms=41.293 cpu_main_ms=41.291 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=4 thread_limit=default requests=400 wall_ms=32.011 cpu_total_ms=26.382 cpu_main_ms=26.379 cpu_other_ms=0.003
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.334 p95_ms=0.364 backend_calls=11.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.211 p95_ms=0.229 backend_calls=7.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.465 p95_ms=0.492 backend_calls=37.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.301 p95_ms=0.412 backend_calls=16.00 concurrency=4
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=4 thread_limit=default requests=400 wall_ms=389.380 cpu_total_ms=498.630 cpu_main_ms=95.910 cpu_other_ms=402.720
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=4 scope=app conns=5 gone=0 db_calls=2400 txns=800 db_wall_ms=401.832 db_wall_ms_per_req=1.005
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=591.611 db_wall_ms_per_req=1.479
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=435.157 cpu_total_ms=553.935 cpu_main_ms=100.316 cpu_other_ms=453.619
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 scope=app conns=5 gone=0 db_calls=2800 txns=1600 db_wall_ms=471.929 db_wall_ms_per_req=1.180
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3202 txns=1601 db_wall_ms=609.755 db_wall_ms_per_req=1.524
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=4 thread_limit=default requests=400 wall_ms=481.989 cpu_total_ms=627.845 cpu_main_ms=100.167 cpu_other_ms=527.678
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=4 scope=app conns=5 gone=0 db_calls=4400 txns=1600 db_wall_ms=708.092 db_wall_ms_per_req=1.770
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=592.627 db_wall_ms_per_req=1.482
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=3.889 p95_ms=4.067 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=4.086 p95_ms=4.278 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=4.830 p95_ms=4.968 backend_calls=19.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 thread_limit=default requests=400 wall_ms=1612.487 cpu_total_ms=3802.086 cpu_main_ms=132.502 cpu_other_ms=3669.584
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=887 waits=244 wait_total_ms=245.453 wait_max_ms=5.333
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 scope=app conns=2 gone=0 db_calls=7600 txns=2000 db_wall_ms=397.162 db_wall_ms_per_req=0.993
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 scope=platform sessions=800 connect_wall_ms=4275.921 db_calls=800 txns=0 db_wall_ms=449.050 db_wall_ms_per_req=11.812
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=1611.020 cpu_total_ms=3944.068 cpu_main_ms=138.848 cpu_other_ms=3805.220
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1769 waits=486 wait_total_ms=425.937 wait_max_ms=25.302
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=219.086 db_wall_ms_per_req=0.548
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 scope=platform sessions=801 connect_wall_ms=4511.878 db_calls=801 txns=1 db_wall_ms=489.527 db_wall_ms_per_req=12.504
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 thread_limit=default requests=400 wall_ms=2116.200 cpu_total_ms=4233.820 cpu_main_ms=142.807 cpu_other_ms=4091.013
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=2651 waits=796 wait_total_ms=1373.264 wait_max_ms=25.302
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=18800 txns=4800 db_wall_ms=712.651 db_wall_ms_per_req=1.782
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 scope=platform sessions=800 connect_wall_ms=4575.828 db_calls=800 txns=0 db_wall_ms=479.513 db_wall_ms_per_req=12.638
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 thread_limit=default requests=400 wall_ms=1704.837 cpu_total_ms=3966.630 cpu_main_ms=135.910 cpu_other_ms=3830.720
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_cb592401 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=3537 waits=1067 wait_total_ms=1735.061 wait_max_ms=26.278
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 scope=app conns=4 gone=0 db_calls=8000 txns=2400 db_wall_ms=339.953 db_wall_ms_per_req=0.850
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 scope=platform sessions=801 connect_wall_ms=4448.318 db_calls=801 txns=1 db_wall_ms=496.035 db_wall_ms_per_req=12.361
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=15.891 p95_ms=17.554 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=15.535 p95_ms=20.309 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=20.724 p95_ms=27.425 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=16.779 p95_ms=18.559 backend_calls=22.00 concurrency=4
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=4 thread_limit=default requests=400 wall_ms=1640.878 cpu_total_ms=1768.793 cpu_main_ms=1229.753 cpu_other_ms=539.040
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=4 scope=app conns=5 gone=0 db_calls=2400 txns=800 db_wall_ms=422.585 db_wall_ms_per_req=1.056
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=646.036 db_wall_ms_per_req=1.615
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=1699.685 cpu_total_ms=1840.396 cpu_main_ms=1246.709 cpu_other_ms=593.687
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 scope=app conns=5 gone=0 db_calls=2800 txns=1600 db_wall_ms=489.796 db_wall_ms_per_req=1.224
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3202 txns=1601 db_wall_ms=663.787 db_wall_ms_per_req=1.659
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 thread_limit=default requests=400 wall_ms=1771.433 cpu_total_ms=1945.457 cpu_main_ms=1251.971 cpu_other_ms=693.486
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 scope=app conns=5 gone=0 db_calls=4400 txns=1600 db_wall_ms=749.458 db_wall_ms_per_req=1.874
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=680.035 db_wall_ms_per_req=1.700
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=16.380 p95_ms=16.710 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=16.665 p95_ms=17.523 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=17.517 p95_ms=18.951 backend_calls=19.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 thread_limit=default requests=400 wall_ms=3024.542 cpu_total_ms=5290.819 cpu_main_ms=1331.301 cpu_other_ms=3959.518
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=887 waits=270 wait_total_ms=406.077 wait_max_ms=7.913
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 scope=app conns=2 gone=0 db_calls=7600 txns=2000 db_wall_ms=525.987 db_wall_ms_per_req=1.315
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 scope=platform sessions=800 connect_wall_ms=4371.684 db_calls=800 txns=0 db_wall_ms=463.573 db_wall_ms_per_req=12.088
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=2939.636 cpu_total_ms=5222.682 cpu_main_ms=1342.915 cpu_other_ms=3879.767
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1769 waits=524 wait_total_ms=680.616 wait_max_ms=24.701
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=311.466 db_wall_ms_per_req=0.779
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 scope=platform sessions=801 connect_wall_ms=4365.642 db_calls=801 txns=1 db_wall_ms=484.146 db_wall_ms_per_req=12.124
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 thread_limit=default requests=400 wall_ms=3366.613 cpu_total_ms=5445.845 cpu_main_ms=1318.569 cpu_other_ms=4127.276
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=2651 waits=842 wait_total_ms=1721.228 wait_max_ms=24.701
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=18800 txns=4800 db_wall_ms=773.750 db_wall_ms_per_req=1.934
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 scope=platform sessions=800 connect_wall_ms=4363.765 db_calls=800 txns=0 db_wall_ms=449.444 db_wall_ms_per_req=12.033
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 thread_limit=default requests=400 wall_ms=3060.217 cpu_total_ms=5282.194 cpu_main_ms=1337.379 cpu_other_ms=3944.815
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_55af77c5 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=3537 waits=1121 wait_total_ms=2203.410 wait_max_ms=26.808
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 scope=app conns=4 gone=0 db_calls=8000 txns=2400 db_wall_ms=429.702 db_wall_ms_per_req=1.074
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 scope=platform sessions=801 connect_wall_ms=4354.129 db_calls=801 txns=1 db_wall_ms=474.720 db_wall_ms_per_req=12.072
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=30.044 p95_ms=33.540 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=28.978 p95_ms=31.446 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=33.778 p95_ms=36.001 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=30.292 p95_ms=32.129 backend_calls=22.00 concurrency=4
```

#### thread limit = 4 × K=4 `--warmup 10 --n 100 --concurrency 4`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=4 thread_limit=default requests=400 wall_ms=27.233 cpu_total_ms=21.729 cpu_main_ms=21.724 cpu_other_ms=0.005
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=109.117 cpu_total_ms=103.571 cpu_main_ms=103.568 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=batch concurrency=4 thread_limit=default requests=400 wall_ms=631.823 cpu_total_ms=626.058 cpu_main_ms=626.054 cpu_other_ms=0.004
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.270 p95_ms=0.289 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=1.044 p95_ms=1.738 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=6.262 p95_ms=9.056 backend_calls=1.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=4 thread_limit=default requests=400 wall_ms=34.411 cpu_total_ms=28.965 cpu_main_ms=28.963 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=21.669 cpu_total_ms=16.222 cpu_main_ms=16.220 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=4 thread_limit=default requests=400 wall_ms=49.275 cpu_total_ms=43.810 cpu_main_ms=43.808 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=4 thread_limit=default requests=400 wall_ms=32.162 cpu_total_ms=26.656 cpu_main_ms=26.655 cpu_other_ms=0.001
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.344 p95_ms=0.361 backend_calls=11.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.218 p95_ms=0.235 backend_calls=7.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.491 p95_ms=0.515 backend_calls=37.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.320 p95_ms=0.339 backend_calls=16.00 concurrency=4
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=4 thread_limit=4 requests=400 wall_ms=386.984 cpu_total_ms=495.801 cpu_main_ms=95.883 cpu_other_ms=399.919
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=4 scope=app conns=5 gone=0 db_calls=2400 txns=800 db_wall_ms=397.624 db_wall_ms_per_req=0.994
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=585.047 db_wall_ms_per_req=1.463
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 thread_limit=4 requests=400 wall_ms=432.964 cpu_total_ms=548.430 cpu_main_ms=99.055 cpu_other_ms=449.375
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 scope=app conns=5 gone=0 db_calls=2800 txns=1600 db_wall_ms=475.692 db_wall_ms_per_req=1.189
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3202 txns=1601 db_wall_ms=601.532 db_wall_ms_per_req=1.504
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=4 thread_limit=4 requests=400 wall_ms=480.122 cpu_total_ms=624.658 cpu_main_ms=100.586 cpu_other_ms=524.072
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=4 scope=app conns=5 gone=0 db_calls=4400 txns=1600 db_wall_ms=706.705 db_wall_ms_per_req=1.767
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=588.756 db_wall_ms_per_req=1.472
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=3.850 p95_ms=4.069 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=4.055 p95_ms=4.285 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=4.806 p95_ms=4.972 backend_calls=19.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 thread_limit=4 requests=400 wall_ms=1611.373 cpu_total_ms=3783.392 cpu_main_ms=133.590 cpu_other_ms=3649.802
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=887 waits=248 wait_total_ms=237.338 wait_max_ms=4.734
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 scope=app conns=2 gone=0 db_calls=7600 txns=2000 db_wall_ms=396.963 db_wall_ms_per_req=0.992
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 scope=platform sessions=800 connect_wall_ms=4263.523 db_calls=800 txns=0 db_wall_ms=439.757 db_wall_ms_per_req=11.758
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 thread_limit=4 requests=400 wall_ms=1590.763 cpu_total_ms=3908.311 cpu_main_ms=138.047 cpu_other_ms=3770.264
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1769 waits=484 wait_total_ms=410.468 wait_max_ms=24.107
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=212.701 db_wall_ms_per_req=0.532
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 scope=platform sessions=801 connect_wall_ms=4463.980 db_calls=801 txns=1 db_wall_ms=478.837 db_wall_ms_per_req=12.357
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 thread_limit=4 requests=400 wall_ms=1972.945 cpu_total_ms=4035.639 cpu_main_ms=134.958 cpu_other_ms=3900.681
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=2651 waits=798 wait_total_ms=1252.074 wait_max_ms=24.107
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=18800 txns=4800 db_wall_ms=673.741 db_wall_ms_per_req=1.684
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 scope=platform sessions=800 connect_wall_ms=4318.292 db_calls=800 txns=0 db_wall_ms=434.189 db_wall_ms_per_req=11.881
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 thread_limit=4 requests=400 wall_ms=1683.947 cpu_total_ms=3897.258 cpu_main_ms=137.389 cpu_other_ms=3759.869
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_7e70c2f3 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=3537 waits=1059 wait_total_ms=1590.846 wait_max_ms=25.759
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 scope=app conns=4 gone=0 db_calls=8000 txns=2400 db_wall_ms=335.120 db_wall_ms_per_req=0.838
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 scope=platform sessions=801 connect_wall_ms=4378.566 db_calls=801 txns=1 db_wall_ms=488.714 db_wall_ms_per_req=12.168
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=15.832 p95_ms=17.475 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=15.283 p95_ms=17.610 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=19.824 p95_ms=20.856 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=16.230 p95_ms=18.278 backend_calls=22.00 concurrency=4
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=4 thread_limit=4 requests=400 wall_ms=1663.527 cpu_total_ms=1789.651 cpu_main_ms=1238.333 cpu_other_ms=551.318
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=4 scope=app conns=5 gone=0 db_calls=2400 txns=800 db_wall_ms=429.451 db_wall_ms_per_req=1.074
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=648.637 db_wall_ms_per_req=1.622
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 thread_limit=4 requests=400 wall_ms=1713.478 cpu_total_ms=1849.411 cpu_main_ms=1253.976 cpu_other_ms=595.435
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 scope=app conns=5 gone=0 db_calls=2800 txns=1600 db_wall_ms=507.608 db_wall_ms_per_req=1.269
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3202 txns=1601 db_wall_ms=688.786 db_wall_ms_per_req=1.722
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 thread_limit=4 requests=400 wall_ms=1790.981 cpu_total_ms=1958.246 cpu_main_ms=1266.938 cpu_other_ms=691.308
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 scope=app conns=5 gone=0 db_calls=4400 txns=1600 db_wall_ms=758.044 db_wall_ms_per_req=1.895
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=671.871 db_wall_ms_per_req=1.680
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=16.452 p95_ms=17.478 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=16.790 p95_ms=17.621 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=17.643 p95_ms=19.271 backend_calls=19.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 thread_limit=4 requests=400 wall_ms=3082.631 cpu_total_ms=5420.996 cpu_main_ms=1337.058 cpu_other_ms=4083.938
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=887 waits=280 wait_total_ms=447.685 wait_max_ms=7.999
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 scope=app conns=2 gone=0 db_calls=7600 txns=2000 db_wall_ms=531.717 db_wall_ms_per_req=1.329
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 scope=platform sessions=800 connect_wall_ms=4497.961 db_calls=800 txns=0 db_wall_ms=464.779 db_wall_ms_per_req=12.407
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 thread_limit=4 requests=400 wall_ms=3100.850 cpu_total_ms=5486.229 cpu_main_ms=1375.356 cpu_other_ms=4110.873
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1769 waits=549 wait_total_ms=805.523 wait_max_ms=32.980
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=336.986 db_wall_ms_per_req=0.842
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 scope=platform sessions=801 connect_wall_ms=4718.391 db_calls=801 txns=1 db_wall_ms=523.538 db_wall_ms_per_req=13.105
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 thread_limit=4 requests=400 wall_ms=3427.095 cpu_total_ms=5571.252 cpu_main_ms=1322.390 cpu_other_ms=4248.862
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=2651 waits=872 wait_total_ms=1906.229 wait_max_ms=32.980
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=18800 txns=4800 db_wall_ms=776.081 db_wall_ms_per_req=1.940
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 scope=platform sessions=800 connect_wall_ms=4488.337 db_calls=800 txns=0 db_wall_ms=466.459 db_wall_ms_per_req=12.387
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 thread_limit=4 requests=400 wall_ms=3062.932 cpu_total_ms=5381.562 cpu_main_ms=1326.219 cpu_other_ms=4055.343
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_37ab110e acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=3537 waits=1158 wait_total_ms=2413.828 wait_max_ms=36.505
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 scope=app conns=4 gone=0 db_calls=8000 txns=2400 db_wall_ms=434.418 db_wall_ms_per_req=1.086
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 scope=platform sessions=801 connect_wall_ms=4451.987 db_calls=801 txns=1 db_wall_ms=479.145 db_wall_ms_per_req=12.328
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=30.780 p95_ms=33.202 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=30.240 p95_ms=34.478 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=33.972 p95_ms=36.242 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=30.295 p95_ms=33.125 backend_calls=22.00 concurrency=4
```

#### thread limit = 1 × K=4 `--warmup 10 --n 100 --concurrency 4`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=4 thread_limit=default requests=400 wall_ms=26.702 cpu_total_ms=21.227 cpu_main_ms=21.224 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=112.903 cpu_total_ms=107.461 cpu_main_ms=107.460 cpu_other_ms=0.001
CPU peer=r2db-api plug=r2db-api op=batch concurrency=4 thread_limit=default requests=400 wall_ms=643.840 cpu_total_ms=638.286 cpu_main_ms=638.283 cpu_other_ms=0.003
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.268 p95_ms=0.283 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=1.073 p95_ms=1.847 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=6.301 p95_ms=10.340 backend_calls=1.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=4 thread_limit=default requests=400 wall_ms=35.564 cpu_total_ms=30.091 cpu_main_ms=30.089 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=4 thread_limit=default requests=400 wall_ms=22.100 cpu_total_ms=16.674 cpu_main_ms=16.674 cpu_other_ms=0.000
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=4 thread_limit=default requests=400 wall_ms=51.888 cpu_total_ms=46.479 cpu_main_ms=46.477 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=4 thread_limit=default requests=400 wall_ms=32.807 cpu_total_ms=27.373 cpu_main_ms=27.372 cpu_other_ms=0.001
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.354 p95_ms=0.372 backend_calls=11.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.224 p95_ms=0.239 backend_calls=7.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.518 p95_ms=0.540 backend_calls=37.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.328 p95_ms=0.341 backend_calls=16.00 concurrency=4
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=4 thread_limit=1 requests=400 wall_ms=544.222 cpu_total_ms=295.667 cpu_main_ms=86.396 cpu_other_ms=209.271
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=4 scope=app conns=2 gone=0 db_calls=2400 txns=800 db_wall_ms=188.419 db_wall_ms_per_req=0.471
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=149.344 db_wall_ms_per_req=0.373
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 thread_limit=1 requests=400 wall_ms=658.656 cpu_total_ms=345.923 cpu_main_ms=98.733 cpu_other_ms=247.190
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=2800 txns=1600 db_wall_ms=234.731 db_wall_ms_per_req=0.587
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3202 txns=1601 db_wall_ms=185.672 db_wall_ms_per_req=0.464
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=4 thread_limit=1 requests=400 wall_ms=648.505 cpu_total_ms=367.957 cpu_main_ms=94.289 cpu_other_ms=273.668
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=252.173 db_wall_ms_per_req=0.630
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=152.642 db_wall_ms_per_req=0.382
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=5.451 p95_ms=5.784 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=5.937 p95_ms=7.515 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=6.424 p95_ms=6.831 backend_calls=19.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 thread_limit=1 requests=400 wall_ms=2494.289 cpu_total_ms=1374.009 cpu_main_ms=98.134 cpu_other_ms=1275.875
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=887 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 scope=app conns=2 gone=0 db_calls=7600 txns=2000 db_wall_ms=267.865 db_wall_ms_per_req=0.670
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=4 scope=platform sessions=800 connect_wall_ms=1680.681 db_calls=800 txns=0 db_wall_ms=324.283 db_wall_ms_per_req=5.012
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 thread_limit=1 requests=400 wall_ms=2470.948 cpu_total_ms=1357.248 cpu_main_ms=104.175 cpu_other_ms=1253.073
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1769 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=181.443 db_wall_ms_per_req=0.454
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=4 scope=platform sessions=801 connect_wall_ms=1718.461 db_calls=801 txns=1 db_wall_ms=358.933 db_wall_ms_per_req=5.193
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 thread_limit=1 requests=400 wall_ms=2892.883 cpu_total_ms=1578.541 cpu_main_ms=97.690 cpu_other_ms=1480.851
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=2651 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=18800 txns=4800 db_wall_ms=626.662 db_wall_ms_per_req=1.567
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=4 scope=platform sessions=800 connect_wall_ms=1671.338 db_calls=800 txns=0 db_wall_ms=321.188 db_wall_ms_per_req=4.981
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 thread_limit=1 requests=400 wall_ms=2581.342 cpu_total_ms=1409.211 cpu_main_ms=100.294 cpu_other_ms=1308.917
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_4434e560 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=3537 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 scope=app conns=4 gone=0 db_calls=8000 txns=2400 db_wall_ms=298.940 db_wall_ms_per_req=0.747
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=4 scope=platform sessions=801 connect_wall_ms=1702.358 db_calls=801 txns=1 db_wall_ms=352.818 db_wall_ms_per_req=5.138
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=24.856 p95_ms=25.510 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=23.673 p95_ms=28.390 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=28.839 p95_ms=29.448 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=25.030 p95_ms=26.717 backend_calls=22.00 concurrency=4
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=4 thread_limit=1 requests=400 wall_ms=1784.929 cpu_total_ms=1640.784 cpu_main_ms=1264.291 cpu_other_ms=376.493
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=4 scope=app conns=2 gone=0 db_calls=2400 txns=800 db_wall_ms=227.641 db_wall_ms_per_req=0.569
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=217.461 db_wall_ms_per_req=0.544
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 thread_limit=1 requests=400 wall_ms=1841.887 cpu_total_ms=1670.420 cpu_main_ms=1269.727 cpu_other_ms=400.693
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=2800 txns=1600 db_wall_ms=263.005 db_wall_ms_per_req=0.658
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3202 txns=1601 db_wall_ms=228.854 db_wall_ms_per_req=0.572
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 thread_limit=1 requests=400 wall_ms=1873.483 cpu_total_ms=1694.469 cpu_main_ms=1260.998 cpu_other_ms=433.471
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=294.430 db_wall_ms_per_req=0.736
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=4 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3200 txns=1600 db_wall_ms=206.978 db_wall_ms_per_req=0.517
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=17.719 p95_ms=18.283 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=18.053 p95_ms=19.406 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=18.644 p95_ms=19.066 backend_calls=19.00 concurrency=4
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 thread_limit=1 requests=400 wall_ms=3823.193 cpu_total_ms=2750.453 cpu_main_ms=1237.187 cpu_other_ms=1513.266
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=887 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 scope=app conns=2 gone=0 db_calls=7600 txns=2000 db_wall_ms=280.740 db_wall_ms_per_req=0.702
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=4 scope=platform sessions=800 connect_wall_ms=1749.910 db_calls=800 txns=0 db_wall_ms=344.242 db_wall_ms_per_req=5.235
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 thread_limit=1 requests=400 wall_ms=3660.758 cpu_total_ms=2654.038 cpu_main_ms=1220.820 cpu_other_ms=1433.218
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1769 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 scope=app conns=2 gone=0 db_calls=4400 txns=1600 db_wall_ms=181.950 db_wall_ms_per_req=0.455
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=4 scope=platform sessions=801 connect_wall_ms=1720.832 db_calls=801 txns=1 db_wall_ms=360.109 db_wall_ms_per_req=5.202
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 thread_limit=1 requests=400 wall_ms=4299.298 cpu_total_ms=2988.133 cpu_main_ms=1248.141 cpu_other_ms=1739.992
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=2651 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 scope=app conns=2 gone=0 db_calls=18800 txns=4800 db_wall_ms=652.714 db_wall_ms_per_req=1.632
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=4 scope=platform sessions=800 connect_wall_ms=1776.859 db_calls=800 txns=0 db_wall_ms=354.923 db_wall_ms_per_req=5.329
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 thread_limit=1 requests=400 wall_ms=3814.210 cpu_total_ms=2735.700 cpu_main_ms=1222.309 cpu_other_ms=1513.391
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_8a9a1c1a acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=3537 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 scope=app conns=4 gone=0 db_calls=8000 txns=2400 db_wall_ms=302.985 db_wall_ms_per_req=0.757
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=4 scope=platform sessions=801 connect_wall_ms=1729.880 db_calls=801 txns=1 db_wall_ms=362.416 db_wall_ms_per_req=5.231
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=37.675 p95_ms=41.151 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=36.247 p95_ms=37.024 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=42.576 p95_ms=46.527 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=37.788 p95_ms=38.814 backend_calls=22.00 concurrency=4
```

#### thread limit = 既定 (無し) × K=32 `--warmup 3 --n 15 --concurrency 32`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=23.249 cpu_total_ms=22.429 cpu_main_ms=22.424 cpu_other_ms=0.005
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=157.805 cpu_total_ms=156.902 cpu_main_ms=156.900 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=968.514 cpu_total_ms=965.964 cpu_main_ms=965.961 cpu_other_ms=0.003
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=15 p50_ms=1.510 p95_ms=1.758 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=15 p50_ms=10.658 p95_ms=16.021 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=15 p50_ms=63.138 p95_ms=92.248 backend_calls=1.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=29.751 cpu_total_ms=28.908 cpu_main_ms=28.907 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=16.507 cpu_total_ms=15.694 cpu_main_ms=15.693 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=47.653 cpu_total_ms=46.809 cpu_main_ms=46.808 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=27.933 cpu_total_ms=27.100 cpu_main_ms=27.098 cpu_other_ms=0.002
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=15 p50_ms=1.967 p95_ms=2.128 backend_calls=11.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=15 p50_ms=1.091 p95_ms=1.225 backend_calls=7.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=15 p50_ms=3.173 p95_ms=3.311 backend_calls=37.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=15 p50_ms=1.887 p95_ms=2.049 backend_calls=16.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=32 thread_limit=default requests=480 wall_ms=741.030 cpu_total_ms=1634.527 cpu_main_ms=124.223 cpu_other_ms=1510.304
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=30
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=app conns=32 gone=0 db_calls=2883 txns=963 db_wall_ms=7302.263 db_wall_ms_per_req=15.213
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=10672.423 db_wall_ms_per_req=22.234
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=809.990 cpu_total_ms=1843.716 cpu_main_ms=135.593 cpu_other_ms=1708.123
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=app conns=33 gone=0 db_calls=3361 txns=1921 db_wall_ms=8529.531 db_wall_ms_per_req=17.770
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=10499.685 db_wall_ms_per_req=21.874
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=32 thread_limit=default requests=480 wall_ms=912.061 cpu_total_ms=2130.162 cpu_main_ms=130.249 cpu_other_ms=1999.913
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=app conns=33 gone=0 db_calls=5280 txns=1920 db_wall_ms=11914.824 db_wall_ms_per_req=24.823
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=10844.752 db_wall_ms_per_req=22.593
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=15 p50_ms=49.255 p95_ms=55.162 backend_calls=14.01 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=51.786 p95_ms=63.407 backend_calls=15.01 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=15 p50_ms=58.282 p95_ms=70.030 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 thread_limit=default requests=480 wall_ms=2835.237 cpu_total_ms=18515.389 cpu_main_ms=148.775 cpu_other_ms=18366.614
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1159 waits=546 wait_total_ms=10316.147 wait_max_ms=49.837
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=1194.215 db_wall_ms_per_req=2.488
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=49920.332 db_calls=960 txns=0 db_wall_ms=5899.303 db_wall_ms_per_req=116.291
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=2792.990 cpu_total_ms=19010.878 cpu_main_ms=145.036 cpu_other_ms=18865.842
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2313 waits=1075 wait_total_ms=16718.654 wait_max_ms=56.239
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=839.385 db_wall_ms_per_req=1.749
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=50537.641 db_calls=961 txns=1 db_wall_ms=5149.029 db_wall_ms_per_req=116.014
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 thread_limit=default requests=480 wall_ms=3411.791 cpu_total_ms=18942.016 cpu_main_ms=135.792 cpu_other_ms=18806.224
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3467 waits=1633 wait_total_ms=38763.747 wait_max_ms=83.552
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=1487.660 db_wall_ms_per_req=3.099
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=47744.284 db_calls=961 txns=1 db_wall_ms=6588.873 db_wall_ms_per_req=113.194
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=2863.606 cpu_total_ms=18081.086 cpu_main_ms=152.456 cpu_other_ms=17928.630
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_add5a19c acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4625 waits=2176 wait_total_ms=49355.782 wait_max_ms=83.552
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=1013.938 db_wall_ms_per_req=2.112
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=46714.720 db_calls=960 txns=0 db_wall_ms=5159.267 db_wall_ms_per_req=108.071
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=15 p50_ms=188.586 p95_ms=199.392 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=184.124 p95_ms=204.764 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=15 p50_ms=227.786 p95_ms=243.001 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=15 p50_ms=191.348 p95_ms=200.297 backend_calls=22.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=32 thread_limit=default requests=480 wall_ms=2317.563 cpu_total_ms=3310.761 cpu_main_ms=1580.169 cpu_other_ms=1730.592
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=app conns=33 gone=0 db_calls=2881 txns=961 db_wall_ms=7023.288 db_wall_ms_per_req=14.632
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=11429.441 db_wall_ms_per_req=23.811
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=2300.719 cpu_total_ms=3428.680 cpu_main_ms=1522.920 cpu_other_ms=1905.760
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=app conns=33 gone=0 db_calls=3360 txns=1920 db_wall_ms=8296.064 db_wall_ms_per_req=17.283
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=10786.187 db_wall_ms_per_req=22.471
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 thread_limit=default requests=480 wall_ms=2463.329 cpu_total_ms=3716.805 cpu_main_ms=1540.799 cpu_other_ms=2176.006
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=app conns=33 gone=0 db_calls=5280 txns=1920 db_wall_ms=12350.108 db_wall_ms_per_req=25.729
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=11792.421 db_wall_ms_per_req=24.568
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=15 p50_ms=153.881 p95_ms=165.149 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=15 p50_ms=150.544 p95_ms=162.120 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=15 p50_ms=162.176 p95_ms=174.638 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 thread_limit=default requests=480 wall_ms=4403.785 cpu_total_ms=19724.512 cpu_main_ms=1656.681 cpu_other_ms=18067.831
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1159 waits=544 wait_total_ms=12953.832 wait_max_ms=50.320
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=1400.052 db_wall_ms_per_req=2.917
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=55427.094 db_calls=960 txns=0 db_wall_ms=7741.952 db_wall_ms_per_req=131.602
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=4243.030 cpu_total_ms=19881.020 cpu_main_ms=1627.799 cpu_other_ms=18253.221
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2313 waits=1067 wait_total_ms=20469.939 wait_max_ms=61.100
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=941.501 db_wall_ms_per_req=1.961
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=57404.210 db_calls=961 txns=1 db_wall_ms=6869.203 db_wall_ms_per_req=133.903
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 thread_limit=default requests=480 wall_ms=4795.269 cpu_total_ms=19410.797 cpu_main_ms=1650.540 cpu_other_ms=17760.257
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3467 waits=1618 wait_total_ms=40497.170 wait_max_ms=87.079
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=1646.229 db_wall_ms_per_req=3.430
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=56063.658 db_calls=961 txns=1 db_wall_ms=7644.430 db_wall_ms_per_req=132.725
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=4480.021 cpu_total_ms=19170.938 cpu_main_ms=1705.749 cpu_other_ms=17465.189
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_da0e0dda acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4625 waits=2154 wait_total_ms=52618.313 wait_max_ms=96.526
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=1179.524 db_wall_ms_per_req=2.457
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=55277.273 db_calls=960 txns=0 db_wall_ms=7162.824 db_wall_ms_per_req=130.084
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=15 p50_ms=291.281 p95_ms=312.299 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=15 p50_ms=279.114 p95_ms=305.035 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=15 p50_ms=315.386 p95_ms=337.650 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=15 p50_ms=290.094 p95_ms=332.862 backend_calls=22.00 concurrency=32
```

#### thread limit = 4 × K=32 `--warmup 3 --n 15 --concurrency 32`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=23.485 cpu_total_ms=22.647 cpu_main_ms=22.644 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=161.281 cpu_total_ms=160.317 cpu_main_ms=160.314 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=1018.431 cpu_total_ms=1016.648 cpu_main_ms=1016.644 cpu_other_ms=0.004
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=15 p50_ms=1.562 p95_ms=1.824 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=15 p50_ms=11.249 p95_ms=16.552 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=15 p50_ms=66.446 p95_ms=96.357 backend_calls=1.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=32.344 cpu_total_ms=31.502 cpu_main_ms=31.499 cpu_other_ms=0.003
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=17.636 cpu_total_ms=16.810 cpu_main_ms=16.809 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=50.829 cpu_total_ms=49.983 cpu_main_ms=49.981 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=29.920 cpu_total_ms=29.087 cpu_main_ms=29.085 cpu_other_ms=0.002
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=15 p50_ms=2.176 p95_ms=2.265 backend_calls=11.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=15 p50_ms=1.164 p95_ms=1.334 backend_calls=7.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=15 p50_ms=3.382 p95_ms=3.555 backend_calls=37.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=15 p50_ms=1.997 p95_ms=2.130 backend_calls=16.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=32 thread_limit=4 requests=480 wall_ms=435.616 cpu_total_ms=583.831 cpu_main_ms=110.188 cpu_other_ms=473.643
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=app conns=5 gone=0 db_calls=2880 txns=960 db_wall_ms=506.729 db_wall_ms_per_req=1.056
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=698.344 db_wall_ms_per_req=1.455
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=542.717 cpu_total_ms=707.781 cpu_main_ms=130.263 cpu_other_ms=577.518
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=app conns=5 gone=0 db_calls=3360 txns=1920 db_wall_ms=664.205 db_wall_ms_per_req=1.384
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=838.085 db_wall_ms_per_req=1.746
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=780.341 cpu_total_ms=963.398 cpu_main_ms=165.907 cpu_other_ms=797.491
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=app conns=5 gone=0 db_calls=5280 txns=1920 db_wall_ms=1186.600 db_wall_ms_per_req=2.472
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=1048.279 db_wall_ms_per_req=2.184
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=15 p50_ms=28.681 p95_ms=30.937 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=32.367 p95_ms=48.896 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=15 p50_ms=50.199 p95_ms=64.441 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 thread_limit=4 requests=480 wall_ms=1503.615 cpu_total_ms=3522.864 cpu_main_ms=152.175 cpu_other_ms=3370.689
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1159 waits=212 wait_total_ms=132.508 wait_max_ms=6.811
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=547.898 db_wall_ms_per_req=1.141
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=4183.017 db_calls=960 txns=0 db_wall_ms=558.365 db_wall_ms_per_req=9.878
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=1496.794 cpu_total_ms=3728.279 cpu_main_ms=149.851 cpu_other_ms=3578.428
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2313 waits=355 wait_total_ms=220.322 wait_max_ms=32.606
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=327.612 db_wall_ms_per_req=0.683
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=4392.318 db_calls=961 txns=1 db_wall_ms=562.513 db_wall_ms_per_req=10.323
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=1891.657 cpu_total_ms=3467.448 cpu_main_ms=162.371 cpu_other_ms=3305.077
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3467 waits=910 wait_total_ms=2077.222 wait_max_ms=32.606
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=917.168 db_wall_ms_per_req=1.911
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=3746.377 db_calls=961 txns=1 db_wall_ms=520.256 db_wall_ms_per_req=8.889
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 thread_limit=4 requests=480 wall_ms=1515.825 cpu_total_ms=3558.406 cpu_main_ms=152.608 cpu_other_ms=3405.798
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_8ef919b8 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4625 waits=1290 wait_total_ms=2300.102 wait_max_ms=32.606
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=560.525 db_wall_ms_per_req=1.168
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=4162.350 db_calls=960 txns=0 db_wall_ms=557.332 db_wall_ms_per_req=9.833
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=15 p50_ms=96.931 p95_ms=117.233 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=96.485 p95_ms=115.564 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=15 p50_ms=123.901 p95_ms=139.039 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=15 p50_ms=98.909 p95_ms=112.138 backend_calls=22.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=32 thread_limit=4 requests=480 wall_ms=2447.587 cpu_total_ms=2814.745 cpu_main_ms=1829.022 cpu_other_ms=985.723
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=app conns=5 gone=0 db_calls=2880 txns=960 db_wall_ms=1037.987 db_wall_ms_per_req=2.162
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=1472.523 db_wall_ms_per_req=3.068
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=2905.576 cpu_total_ms=3256.670 cpu_main_ms=2116.322 cpu_other_ms=1140.348
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=app conns=5 gone=0 db_calls=3360 txns=1920 db_wall_ms=1706.277 db_wall_ms_per_req=3.555
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=1809.994 db_wall_ms_per_req=3.771
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=2623.396 cpu_total_ms=3098.801 cpu_main_ms=1883.640 cpu_other_ms=1215.161
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=app conns=5 gone=0 db_calls=5280 txns=1920 db_wall_ms=1750.481 db_wall_ms_per_req=3.647
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=1505.660 db_wall_ms_per_req=3.137
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=15 p50_ms=160.032 p95_ms=175.695 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=15 p50_ms=198.221 p95_ms=221.293 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=15 p50_ms=171.193 p95_ms=189.328 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 thread_limit=4 requests=480 wall_ms=3106.435 cpu_total_ms=5028.003 cpu_main_ms=1752.416 cpu_other_ms=3275.587
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1159 waits=542 wait_total_ms=875.791 wait_max_ms=29.915
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=904.146 db_wall_ms_per_req=1.884
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=3793.136 db_calls=960 txns=0 db_wall_ms=559.462 db_wall_ms_per_req=9.068
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=2950.191 cpu_total_ms=5011.227 cpu_main_ms=1709.085 cpu_other_ms=3302.142
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2313 waits=1073 wait_total_ms=1212.093 wait_max_ms=42.539
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=593.728 db_wall_ms_per_req=1.237
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=3899.104 db_calls=961 txns=1 db_wall_ms=609.101 db_wall_ms_per_req=9.392
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=3667.015 cpu_total_ms=5280.026 cpu_main_ms=1787.508 cpu_other_ms=3492.518
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3467 waits=1627 wait_total_ms=3663.265 wait_max_ms=42.539
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=1154.725 db_wall_ms_per_req=2.406
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=3892.717 db_calls=961 txns=1 db_wall_ms=638.320 db_wall_ms_per_req=9.440
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 thread_limit=4 requests=480 wall_ms=3247.287 cpu_total_ms=5194.971 cpu_main_ms=1824.842 cpu_other_ms=3370.129
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_34b948d5 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4625 waits=2179 wait_total_ms=4596.868 wait_max_ms=42.539
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=734.105 db_wall_ms_per_req=1.529
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=3971.399 db_calls=960 txns=0 db_wall_ms=581.958 db_wall_ms_per_req=9.486
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=15 p50_ms=203.321 p95_ms=226.055 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=15 p50_ms=194.658 p95_ms=210.555 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=15 p50_ms=235.710 p95_ms=280.188 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=15 p50_ms=209.844 p95_ms=256.550 backend_calls=22.00 concurrency=32
```

#### thread limit = 1 × K=32 `--warmup 3 --n 15 --concurrency 32`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=23.991 cpu_total_ms=23.134 cpu_main_ms=23.131 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=174.077 cpu_total_ms=172.925 cpu_main_ms=172.923 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=1029.705 cpu_total_ms=1027.135 cpu_main_ms=1027.131 cpu_other_ms=0.004
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=15 p50_ms=1.602 p95_ms=1.824 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=15 p50_ms=11.659 p95_ms=17.230 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=15 p50_ms=70.300 p95_ms=99.118 backend_calls=1.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=32.320 cpu_total_ms=31.434 cpu_main_ms=31.431 cpu_other_ms=0.003
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=17.615 cpu_total_ms=16.750 cpu_main_ms=16.747 cpu_other_ms=0.003
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=49.749 cpu_total_ms=48.885 cpu_main_ms=48.881 cpu_other_ms=0.004
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=29.472 cpu_total_ms=28.593 cpu_main_ms=28.591 cpu_other_ms=0.002
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=15 p50_ms=2.144 p95_ms=2.363 backend_calls=11.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=15 p50_ms=1.204 p95_ms=1.288 backend_calls=7.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=15 p50_ms=3.310 p95_ms=3.415 backend_calls=37.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=15 p50_ms=1.928 p95_ms=2.413 backend_calls=16.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=32 thread_limit=1 requests=480 wall_ms=650.879 cpu_total_ms=355.098 cpu_main_ms=98.999 cpu_other_ms=256.099
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=app conns=2 gone=0 db_calls=2880 txns=960 db_wall_ms=227.344 db_wall_ms_per_req=0.474
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=185.397 db_wall_ms_per_req=0.386
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 thread_limit=1 requests=480 wall_ms=702.665 cpu_total_ms=380.337 cpu_main_ms=98.421 cpu_other_ms=281.916
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=3360 txns=1920 db_wall_ms=263.684 db_wall_ms_per_req=0.549
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=205.602 db_wall_ms_per_req=0.428
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=32 thread_limit=1 requests=480 wall_ms=783.661 cpu_total_ms=443.707 cpu_main_ms=100.297 cpu_other_ms=343.410
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=308.202 db_wall_ms_per_req=0.642
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=202.425 db_wall_ms_per_req=0.422
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=15 p50_ms=42.783 p95_ms=45.778 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=44.938 p95_ms=55.807 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=15 p50_ms=50.568 p95_ms=61.598 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 thread_limit=1 requests=480 wall_ms=3074.430 cpu_total_ms=1674.554 cpu_main_ms=109.203 cpu_other_ms=1565.351
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1159 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=328.863 db_wall_ms_per_req=0.685
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=2090.152 db_calls=960 txns=0 db_wall_ms=400.958 db_wall_ms_per_req=5.190
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 thread_limit=1 requests=480 wall_ms=2910.286 cpu_total_ms=1600.764 cpu_main_ms=113.191 cpu_other_ms=1487.573
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2313 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=207.544 db_wall_ms_per_req=0.432
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=2062.540 db_calls=961 txns=1 db_wall_ms=410.821 db_wall_ms_per_req=5.153
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 thread_limit=1 requests=480 wall_ms=3660.748 cpu_total_ms=1970.777 cpu_main_ms=114.477 cpu_other_ms=1856.300
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3467 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=774.446 db_wall_ms_per_req=1.613
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=2123.496 db_calls=961 txns=1 db_wall_ms=433.386 db_wall_ms_per_req=5.327
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 thread_limit=1 requests=480 wall_ms=3051.792 cpu_total_ms=1666.117 cpu_main_ms=106.841 cpu_other_ms=1559.276
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_d7fda0dd acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4625 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=350.180 db_wall_ms_per_req=0.730
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=2060.459 db_calls=960 txns=0 db_wall_ms=394.681 db_wall_ms_per_req=5.115
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=15 p50_ms=204.302 p95_ms=212.474 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=191.212 p95_ms=207.034 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=15 p50_ms=237.542 p95_ms=265.728 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=15 p50_ms=201.643 p95_ms=213.309 backend_calls=22.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=32 thread_limit=1 requests=480 wall_ms=2115.594 cpu_total_ms=2001.886 cpu_main_ms=1549.859 cpu_other_ms=452.027
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=app conns=2 gone=0 db_calls=2880 txns=960 db_wall_ms=290.326 db_wall_ms_per_req=0.605
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=279.735 db_wall_ms_per_req=0.583
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 thread_limit=1 requests=480 wall_ms=2171.270 cpu_total_ms=2034.048 cpu_main_ms=1555.634 cpu_other_ms=478.414
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=3360 txns=1920 db_wall_ms=327.915 db_wall_ms_per_req=0.683
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=306.004 db_wall_ms_per_req=0.638
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 thread_limit=1 requests=480 wall_ms=2302.310 cpu_total_ms=2135.204 cpu_main_ms=1573.550 cpu_other_ms=561.654
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=376.491 db_wall_ms_per_req=0.784
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=319.240 db_wall_ms_per_req=0.665
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=15 p50_ms=140.355 p95_ms=147.044 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=15 p50_ms=142.122 p95_ms=157.820 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=15 p50_ms=149.397 p95_ms=177.482 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 thread_limit=1 requests=480 wall_ms=4466.992 cpu_total_ms=3259.866 cpu_main_ms=1520.983 cpu_other_ms=1738.883
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1159 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=334.852 db_wall_ms_per_req=0.698
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=2124.569 db_calls=960 txns=0 db_wall_ms=412.692 db_wall_ms_per_req=5.286
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 thread_limit=1 requests=480 wall_ms=4353.717 cpu_total_ms=3202.213 cpu_main_ms=1516.915 cpu_other_ms=1685.298
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2313 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=216.849 db_wall_ms_per_req=0.452
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=2126.049 db_calls=961 txns=1 db_wall_ms=436.356 db_wall_ms_per_req=5.338
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 thread_limit=1 requests=480 wall_ms=4988.280 cpu_total_ms=3526.576 cpu_main_ms=1529.237 cpu_other_ms=1997.339
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3467 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=776.156 db_wall_ms_per_req=1.617
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=2106.352 db_calls=961 txns=1 db_wall_ms=433.756 db_wall_ms_per_req=5.292
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 thread_limit=1 requests=480 wall_ms=4520.259 cpu_total_ms=3280.945 cpu_main_ms=1527.013 cpu_other_ms=1753.932
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_2c5a91dd acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4625 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=365.101 db_wall_ms_per_req=0.761
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=2144.951 db_calls=960 txns=0 db_wall_ms=417.533 db_wall_ms_per_req=5.339
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=15 p50_ms=295.909 p95_ms=307.606 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=15 p50_ms=287.979 p95_ms=305.986 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=15 p50_ms=329.478 p95_ms=347.280 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=15 p50_ms=298.573 p95_ms=320.002 backend_calls=22.00 concurrency=32
```

#### thread limit = 既定 (無し)、2 回目 (ε 用) × K=32 `--warmup 3 --n 15 --concurrency 32`

```
PERFRUN host=<OS/arch> python=3.11.15 commit=3d10d7d-dirty date=2026-09-27
CPU peer=r2db-api plug=r2db-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=23.538 cpu_total_ms=22.699 cpu_main_ms=22.696 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=158.169 cpu_total_ms=157.202 cpu_main_ms=157.200 cpu_other_ms=0.002
CPU peer=r2db-api plug=r2db-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=990.555 cpu_total_ms=988.811 cpu_main_ms=988.809 cpu_other_ms=0.002
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=15 p50_ms=1.559 p95_ms=1.755 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=15 p50_ms=10.909 p95_ms=15.884 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=15 p50_ms=65.029 p95_ms=96.028 backend_calls=1.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=29.999 cpu_total_ms=29.166 cpu_main_ms=29.165 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=16.652 cpu_total_ms=15.826 cpu_main_ms=15.824 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=47.521 cpu_total_ms=46.682 cpu_main_ms=46.679 cpu_other_ms=0.003
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=28.032 cpu_total_ms=27.205 cpu_main_ms=27.202 cpu_other_ms=0.003
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=15 p50_ms=2.006 p95_ms=2.112 backend_calls=11.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=15 p50_ms=1.146 p95_ms=1.230 backend_calls=7.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=15 p50_ms=3.141 p95_ms=3.339 backend_calls=37.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=15 p50_ms=1.842 p95_ms=1.992 backend_calls=16.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=32 thread_limit=default requests=480 wall_ms=733.901 cpu_total_ms=1670.434 cpu_main_ms=122.874 cpu_other_ms=1547.560
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=31
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=app conns=33 gone=0 db_calls=2881 txns=961 db_wall_ms=7190.885 db_wall_ms_per_req=14.981
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=10798.750 db_wall_ms_per_req=22.497
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=795.919 cpu_total_ms=1890.973 cpu_main_ms=126.013 cpu_other_ms=1764.960
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=app conns=33 gone=0 db_calls=3360 txns=1920 db_wall_ms=8469.004 db_wall_ms_per_req=17.644
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=10751.593 db_wall_ms_per_req=22.399
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=32 thread_limit=default requests=480 wall_ms=917.288 cpu_total_ms=2164.422 cpu_main_ms=134.738 cpu_other_ms=2029.684
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=app conns=33 gone=0 db_calls=5280 txns=1920 db_wall_ms=11897.755 db_wall_ms_per_req=24.787
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=10981.613 db_wall_ms_per_req=22.878
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=15 p50_ms=47.820 p95_ms=55.096 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=50.924 p95_ms=64.076 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=15 p50_ms=59.288 p95_ms=72.191 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 thread_limit=default requests=480 wall_ms=2816.060 cpu_total_ms=18363.784 cpu_main_ms=153.831 cpu_other_ms=18209.953
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1159 waits=537 wait_total_ms=8107.833 wait_max_ms=54.921
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=1071.969 db_wall_ms_per_req=2.233
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=47389.388 db_calls=960 txns=0 db_wall_ms=4491.194 db_wall_ms_per_req=108.085
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=2746.337 cpu_total_ms=18428.213 cpu_main_ms=154.714 cpu_other_ms=18273.499
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2313 waits=1058 wait_total_ms=14305.640 wait_max_ms=54.921
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=732.022 db_wall_ms_per_req=1.525
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=44530.911 db_calls=961 txns=1 db_wall_ms=5250.429 db_wall_ms_per_req=103.711
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 thread_limit=default requests=480 wall_ms=3458.221 cpu_total_ms=17749.789 cpu_main_ms=162.809 cpu_other_ms=17586.981
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3467 waits=1615 wait_total_ms=38660.380 wait_max_ms=85.398
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=1573.015 db_wall_ms_per_req=3.277
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=46521.457 db_calls=961 txns=1 db_wall_ms=6333.315 db_wall_ms_per_req=110.114
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=2847.266 cpu_total_ms=18343.982 cpu_main_ms=151.295 cpu_other_ms=18192.687
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_a8ebeb76 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4625 waits=2164 wait_total_ms=49143.959 wait_max_ms=85.398
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=1006.914 db_wall_ms_per_req=2.098
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=45651.393 db_calls=960 txns=0 db_wall_ms=5685.815 db_wall_ms_per_req=106.953
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=15 p50_ms=188.334 p95_ms=194.499 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=182.405 p95_ms=201.670 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=15 p50_ms=224.682 p95_ms=256.863 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=15 p50_ms=189.672 p95_ms=197.220 backend_calls=22.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=32 thread_limit=default requests=480 wall_ms=2365.526 cpu_total_ms=3335.765 cpu_main_ms=1606.329 cpu_other_ms=1729.436
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=31
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=app conns=32 gone=0 db_calls=2883 txns=963 db_wall_ms=7414.644 db_wall_ms_per_req=15.447
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=11885.371 db_wall_ms_per_req=24.761
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=2346.971 cpu_total_ms=3473.991 cpu_main_ms=1551.623 cpu_other_ms=1922.368
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=app conns=33 gone=0 db_calls=3360 txns=1920 db_wall_ms=8612.820 db_wall_ms_per_req=17.943
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=11485.820 db_wall_ms_per_req=23.929
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 thread_limit=default requests=480 wall_ms=2458.868 cpu_total_ms=3725.810 cpu_main_ms=1544.045 cpu_other_ms=2181.765
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=app conns=33 gone=0 db_calls=5280 txns=1920 db_wall_ms=12041.259 db_wall_ms_per_req=25.086
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=11339.893 db_wall_ms_per_req=23.625
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=15 p50_ms=154.963 p95_ms=169.676 backend_calls=14.01 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=15 p50_ms=154.007 p95_ms=169.609 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=15 p50_ms=161.537 p95_ms=178.706 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 thread_limit=default requests=480 wall_ms=4301.363 cpu_total_ms=19583.378 cpu_main_ms=1627.359 cpu_other_ms=17956.019
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1159 waits=534 wait_total_ms=10741.562 wait_max_ms=50.310
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=1326.046 db_wall_ms_per_req=2.763
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=platform sessions=960 connect_wall_ms=53931.763 db_calls=960 txns=0 db_wall_ms=6460.059 db_wall_ms_per_req=125.816
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=4253.844 cpu_total_ms=19510.521 cpu_main_ms=1673.999 cpu_other_ms=17836.522
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2313 waits=1055 wait_total_ms=18298.612 wait_max_ms=59.217
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=830.276 db_wall_ms_per_req=1.730
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=platform sessions=961 connect_wall_ms=57130.682 db_calls=961 txns=1 db_wall_ms=7089.289 db_wall_ms_per_req=133.792
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 thread_limit=default requests=480 wall_ms=4785.225 cpu_total_ms=19728.114 cpu_main_ms=1631.758 cpu_other_ms=18096.356
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3467 waits=1607 wait_total_ms=38939.689 wait_max_ms=84.403
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=1650.459 db_wall_ms_per_req=3.438
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=platform sessions=961 connect_wall_ms=55390.257 db_calls=961 txns=1 db_wall_ms=7125.960 db_wall_ms_per_req=130.242
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=4396.711 cpu_total_ms=19854.149 cpu_main_ms=1695.668 cpu_other_ms=18158.481
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_5146d3bc acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4625 waits=2142 wait_total_ms=49823.075 wait_max_ms=84.403
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=1076.194 db_wall_ms_per_req=2.242
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=platform sessions=960 connect_wall_ms=55856.916 db_calls=960 txns=0 db_wall_ms=7778.382 db_wall_ms_per_req=132.574
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=15 p50_ms=283.523 p95_ms=298.987 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=15 p50_ms=284.884 p95_ms=296.683 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=15 p50_ms=317.065 p95_ms=334.707 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=15 p50_ms=288.040 p95_ms=308.621 backend_calls=22.00 concurrency=32
```

## 3. 事実 (§2 の数字だけから。判断語を含まない。WP-2 = 監督が埋める)

以下、plug は `r2db-api-http` / `r2db-api-socket` / `MitateDB-api-http` / `MitateDB-api-socket` の順。`query` の p50 (ms)。

1. **非退行 (D-4 の (ii))**: K=1 の 1 組目は 21 (plug, op) のうち 20 が ±10% 以内、`r2db-api-http` `batch` だけ +11.7% (1.602 → 1.789)。同条件の 2 組目・3 組目の同 op は +3.5% (1.673 → 1.732)・+0.3% (1.740 → 1.745) で、1 組目の +11.7% は再現しない。K=3 の 1 組は 21 すべて ±10% 以内 (最大 +9.9% = `MitateDB-api-http` `mutate` 11.150 → 12.251)。
2. **`query` p50 (thread limit × K)**:

| plug | 既定 K1 | 4 K1 | 1 K1 | 既定 K4 | 4 K4 | 1 K4 | 既定 K32 | 4 K32 | 1 K32 | 既定 K32 (2 回目) |
|---|---|---|---|---|---|---|---|---|---|---|
| r2db-api-http | 1.478 | 1.476 | 1.489 | 3.889 | 3.850 | 5.451 | 49.255 | 28.681 | 42.783 | 47.820 |
| r2db-api-socket | 4.834 | 4.870 | 4.825 | 16.380 | 16.452 | 17.719 | 153.881 | 160.032 | 140.355 | 154.963 |
| MitateDB-api-http | 6.301 | 6.360 | 6.385 | 15.891 | 15.832 | 24.856 | 188.586 | 96.931 | 204.302 | 188.334 |
| MitateDB-api-socket | 9.869 | 9.858 | 14.263 | 30.044 | 30.780 | 37.675 | 291.281 | 203.321 | 295.909 | 283.523 |

3. **ε と δ** (既定 × K=32 の 2 run の `query` p50 の相対差): ε = 2.9% / 0.7% / 0.1% / 2.7%。δ = max(10%, 2ε) = **10%** (4 plug とも)。
4. **`RM` §0.1.4 の 2 に対する現状** (`query` p50 の K=32 / K=1、既定 limit): **33.3 / 31.8 / 29.9 / 29.5 倍** (8 倍以内はどの plug も満たさない)。thread limit 4 では 19.4 / 32.9 / 15.2 / 20.6 倍。
5. **J-1 が読む値 (K=32)**: p50 の limit 4 − limit 40 の相対差 = **−41.8% / +4.0% / −48.6% / −30.2%** (負 = limit 4 の方が速い)。p50 の limit 1 − limit 40 = **−13.1% / −8.8% / +8.3% / +1.6%**。p95 の limit 4 − limit 40 = **−43.9% / +6.4% / −41.2% / −27.6%** (p95: 既定 55.162 / 165.149 / 199.392 / 312.299、limit 4 30.937 / 175.695 / 117.233 / 226.055)。
6. **J-2 が読む値 (既定 limit、K=32、`CPU` 行 `op=query`)**: r = cpu_total_ms / wall_ms = **2.206 / 1.429 / 6.530 / 4.479**。cpu_other_ms / cpu_total_ms = **0.924 / 0.523 / 0.992 / 0.916**。4 plug とも r > 1、すなわち窓の中で process の CPU 時間が wall を超える (複数 core で同時に走った thread の CPU の合計)。要求あたり: cpu_main_ms/req = 0.259 / 3.292 / 0.310 / 3.451、cpu_other_ms/req = 3.146 / 3.605 / 38.264 / 37.641 (ms)。wall/req = 1.544 / 4.828 / 5.907 / 9.175 (ms)。
7. **J-3 が読む値 (K=1、既定 limit)**: d = (scope=app + scope=platform の db_wall_ms_per_req) / p50(K=1) = **0.577 / 0.183 / 0.896 / 0.610**。内訳 (ms/req、K=1 の p50 は 1.478 / 4.834 / 6.301 / 9.869): r2db-http app 0.467 + platform 0.386 (platform は sessions=0、常駐 pool); r2db-socket app 0.494 + platform 0.389; MitateDB-http app 0.666 + platform 4.981 (うち connect_wall_ms 4.189、sessions = 2/req); MitateDB-socket app 0.694 + platform 5.329 (うち connect 4.485)。J-3 の前提 (K=32 の r < 0.5) は 4 plug とも満たさない (§3 の 6)。
8. **J-5 が読む値 (MitateDB、K=32、既定 limit、`POOL lock=` の `op=query`)**: waits / acquire = **0.471** (http: 546 / 1159) / **0.469** (socket: 544 / 1159)、wait_total_ms = **10316.147 / 12953.832**、wait_max_ms = 49.837 / 50.320。r2db の runtime pool (size 32) の waits は全 run で 0。
9. **J-4 (計測の限界の定量化)**: socket plug の cpu_main_ms/req (= client の CPU) = r2db 3.292 ms、MitateDB 3.451 ms。asgi plug − socket plug の cpu_main_ms/req = 0.259 − 3.292 = **−3.033** (r2db)、0.310 − 3.451 = **−3.141** (MitateDB) ms (負 = 実 socket + h11 の client 経路の CPU が、app の async 層の CPU より大きい)。
10. **`thread_limit=` 列の照合**: 10 run × 4 plug の 40 行すべてで、`CPU` 行の `thread_limit=` が小見出しと一致する (既定 run は `default`、4 の run は `4`、1 の run は `1`)。どの run も `LIMIT_EXCEEDED` で欠けていない (`PERF` 行は run ごと 22 行)。
11. **DBTIME の窓の中身 (K=32 既定、`op=query`、requests=480)**: r2db-http app db_calls=2883 txns=963、platform db_calls=3840 txns=1920 (要求あたり app 6 文 2 txn、platform 8 文 4 txn); MitateDB-http app db_calls=9120 txns=2400、platform sessions=960 (2/req)、connect_wall_ms 合計 49920.332 ms (104.0 ms/req、K=1 の 4.189 ms/req の 24.8 倍)。**要求あたりの DB wall (app + platform、connect 込み) は K=32 で 37.4 / 38.4 / 118.8 / 134.5 ms** (K=1 の 0.853 / 0.883 / 5.647 / 6.023 ms の 43.9 / 43.5 / 21.0 / 22.3 倍。p50 の伸び (§3 の 4) と同じ桁)。

## 4. 判断 (監督)

判定規則は作業指示書 §3.3 (D-5) の逐語で、計測後に動かしていない。§3 の数字だけに当てはめる。δ = 10% (4 plug とも)。

| 規則 | r2db-api-http | r2db-api-socket | MitateDB-api-http | MitateDB-api-socket |
|---|---|---|---|---|
| J-1 (i) limit 4 vs 40 の p50 差 ≤ δ → threadpool は律速でない | **場合分けの外** (差 −41.8% > δ だが limit 4 の方が**速い**。規則は「limit 4 が遅い」場合しか定めない) | **成立** (+4.0% ≤ δ) | **場合分けの外** (−48.6%、limit 4 が速い) | **場合分けの外** (−30.2%、limit 4 が速い) |
| J-1 (ii) limit 1 が limit 40 の ±δ 内 → 直列化は thread 数に依らない | 不成立 (−13.1%、limit 1 の方が速い) | **成立** (−8.8%) | **成立** (+8.3%) | **成立** (+1.6%) |
| R-84 再検討条件 (K=32、p95 の limit 4 vs 40 の差 > δ かつ limit 40 が遅い) | **充足** (−43.9%: limit 40 が遅い) | 不充足 (+6.4% ≤ δ) | **充足** (−41.2%) | **充足** (−27.6%) |
| J-2 r ≥ 0.8 → 主体は Python の CPU (GIL) | **成立** (r = 2.206) | **成立** (1.429) | **成立** (6.530) | **成立** (4.479) |
| J-2 内訳 cpu_other / cpu_total ≥ 0.6 → server 側の CPU が主 | 成立 (0.924: server 側) | 不成立 (0.523: main thread = client の CPU が主。socket plug なので読み替え先は無い) | 成立 (0.992: server 側) | 成立 (0.916: server 側) |
| J-3 K=32 の r < 0.5 かつ K=1 の d ≥ 0.5 → 主体は DB 往復の待ち | 不成立 (r ≥ 0.5) | 不成立 | 不成立 (MitateDB は J-5 へ) | 不成立 (同左) |
| J-5 MitateDB の lock 待ち waits / acquire ≥ 0.3 → 主体は cell lock の待ち (R-102) | — | — | **成立** (0.471) | **成立** (0.469) |
| `RM` §0.1.4 の 2 (K=32 / K=1 ≤ 8) | 不成立 (33.3) | 不成立 (31.8) | 不成立 (29.9) | 不成立 (29.5) |

**判定不能の plug**: 無し (4 plug とも J-2 が成立する)。追加計測の要否を依頼者確認に上げる案件は無い。

**判断**:

1. **直列化の主体 (規則の出力)**: 4 plug とも J-2 が成立し、主体は **Python の CPU (GIL)** である。内訳は r2db-http / MitateDB-http / MitateDB-socket で **server 側** (anyio worker thread + uvicorn thread) の CPU が主、r2db-socket は client (harness) の CPU が process の CPU の半分弱を占め、server 側は要求あたり 3.6 ms で client の 3.3 ms と同程度である。MitateDB の 2 plug は J-5 も成立し (K=32 で acquire の 47% が待ち、待ち合計 10〜13 s)、**cell lock の待ちが主体** (R-102) と規則どおり併記する。J-3 (DB 往復の待ち) はどの plug でも成立しない。
2. **threadpool は「不足」の意味では律速でない**: limit 1 でも p50 は既定と ±δ 内 (r2db-http は limit 1 の方が 13% 速い)。逆に **thread 数を減らすと速くなる**: limit 4 は既定 40 より p50 で 30〜49%、p95 で 28〜44% 速い (r2db-socket を除く 3 plug)。これは J-1 (i) の場合分けの外で、規則は動かさず事実として記す。r > 1 (§3 の 6) と併せると、worker thread が複数 core で同時に CPU を使いながら GIL を取り合う形と整合するが、これは規則の出力ではなく観察である。
3. **R-84 の再検討条件** (「threadpool の混雑が tail latency を決めている」) は、規則の定義どおり **3 plug (r2db-http / MitateDB-http / MitateDB-socket) で充足、r2db-socket で不充足**。R-84 行に追記する。着手 (規模 L、設計レビューが着手条件) は依頼者判断。
4. **R-101 は閉じない**: `RM` §0.1.4 の 2 (8 倍以内) はどの plug も満たさない (29.5〜33.3 倍。thread limit 4 でも 15.2〜32.9 倍)。
5. **是正の候補 (本書では選ばない。作業指示書 v1.1 で依頼者確認)**: (a) production の composition root で anyio の既定 limiter を小さくする (計測上の効きは上記 2。それだけでは 8 倍に届かない)、(b) process を分ける (multi-process worker。GIL の外に出す)、(c) MitateDB の cell lock (R-102)、(d) async psycopg (R-84)。(a) は寸法の変更なので P-8 / R-20 の別変更セット。
6. **規則の次版への申し送り (今回は動かさない)**: r > 1 の場合 (複数 core) と、J-1 (i) で limit 4 の方が速い場合の扱い。J-2 と J-5 が同時に成立したときの優先順位。

## 5. WP-3 の再計測 (D-12。監督が埋める)

**目的**: WP-3 (両 peer の `create_app` の thread limiter、既定 4。MitateDB の http adapter の credential store の platform pool) の効きを、計測前に固定した D-12 で判定する。8 倍 (`RM` §0.1.4 の 2) は WP-3 では判定しない (床。WO §7.1)。

**方法**: §2.2 と同じ道具・同じ条件 — `tools/perf_baseline.py`、`DSA_PERF_POOL_SIZE=32`、`DSA_PERF_THREAD_LIMIT` 無し、K=1 は `--warmup 10 --n 100 --concurrency 1`、K=32 は `--warmup 3 --n 15 --concurrency 32`。道具の木は `d7a7500` (r101b、WP-3 と WP-4 の merge)。基準は v0.2 §2.2 の既定 run (小見出し「thread limit = 既定 (無し) × K=1」と「thread limit = 既定 (無し) × K=32」の 1 回目。D-12 の逐語の行番号 :625- / :1213- は v0.2 のもので、v0.3 では §0 の 1 行分ずれる)。他の pytest と nginx を止めて直列に取る (WO §10.2 の 1)。

### 5.1 実測 (逐語)

#### K=1 `--warmup 10 --n 100 --concurrency 1`

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=d7a7500 date=2026-09-28
CPU peer=r2db-api plug=r2db-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=11.951 cpu_total_ms=6.499 cpu_main_ms=6.495 cpu_other_ms=0.004
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=16.611 cpu_total_ms=11.178 cpu_main_ms=11.178 cpu_other_ms=0.000
CPU peer=r2db-api plug=r2db-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=51.194 cpu_total_ms=45.745 cpu_main_ms=45.743 cpu_other_ms=0.002
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.117 p95_ms=0.137 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.163 p95_ms=0.207 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.510 p95_ms=0.700 backend_calls=1.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=1 thread_limit=default requests=100 wall_ms=13.536 cpu_total_ms=8.126 cpu_main_ms=8.125 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=1 thread_limit=default requests=100 wall_ms=10.417 cpu_total_ms=4.946 cpu_main_ms=4.945 cpu_other_ms=0.001
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=1 thread_limit=default requests=100 wall_ms=16.978 cpu_total_ms=11.617 cpu_main_ms=11.615 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=1 thread_limit=default requests=100 wall_ms=12.827 cpu_total_ms=7.401 cpu_main_ms=7.399 cpu_other_ms=0.002
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.133 p95_ms=0.144 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.102 p95_ms=0.120 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.168 p95_ms=0.182 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.127 p95_ms=0.143 backend_calls=16.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=1 thread_limit=4 requests=100 wall_ms=140.068 cpu_total_ms=76.490 cpu_main_ms=25.092 cpu_other_ms=51.398
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_73efe9e7e787/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_73efe9e7e787/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=44.549 db_wall_ms_per_req=0.445
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=35.095 db_wall_ms_per_req=0.351
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_73efe9e7e787/developer@93521 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_73efe9e7e787/runtime@93523 executes=668 executemany=0 prepared=6 prepared_execs=633 share=0.948
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=146.911 cpu_total_ms=78.790 cpu_main_ms=25.110 cpu_other_ms=53.680
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_73efe9e7e787/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_73efe9e7e787/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=52.137 db_wall_ms_per_req=0.521
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=35.825 db_wall_ms_per_req=0.358
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_73efe9e7e787/developer@93521 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_73efe9e7e787/runtime@93523 executes=1438 executemany=0 prepared=8 prepared_execs=1395 share=0.970
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=162.490 cpu_total_ms=91.141 cpu_main_ms=25.149 cpu_other_ms=65.992
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_73efe9e7e787/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_73efe9e7e787/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=60.512 db_wall_ms_per_req=0.605
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=35.591 db_wall_ms_per_req=0.356
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_73efe9e7e787/developer@93521 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_73efe9e7e787/runtime@93523 executes=2648 executemany=0 prepared=8 prepared_execs=2605 share=0.984
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.388 p95_ms=1.518 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.454 p95_ms=1.596 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.602 p95_ms=1.748 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 thread_limit=4 requests=100 wall_ms=127.513 cpu_total_ms=76.937 cpu_main_ms=24.777 cpu_other_ms=52.160
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_9ea1cc4785d9 acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=57.406 db_wall_ms_per_req=0.574
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=14.480 db_wall_ms_per_req=0.145
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@93539 executes=334 executemany=0 prepared=3 prepared_execs=305 share=0.913
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@93540 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=99.124 cpu_total_ms=60.665 cpu_main_ms=23.894 cpu_other_ms=36.771
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_9ea1cc4785d9 acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=35.086 db_wall_ms_per_req=0.351
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=14.135 db_wall_ms_per_req=0.141
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@93539 executes=664 executemany=0 prepared=4 prepared_execs=631 share=0.950
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@93540 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=230.648 cpu_total_ms=131.299 cpu_main_ms=25.251 cpu_other_ms=106.048
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_9ea1cc4785d9 acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=147.310 db_wall_ms_per_req=1.473
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=14.746 db_wall_ms_per_req=0.147
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@93539 executes=1434 executemany=0 prepared=6 prepared_execs=1401 share=0.977
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@93540 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 thread_limit=4 requests=100 wall_ms=132.219 cpu_total_ms=77.942 cpu_main_ms=24.582 cpu_other_ms=53.360
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_34caaa6d acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_9ea1cc4785d9 acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=62.284 db_wall_ms_per_req=0.623
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=14.550 db_wall_ms_per_req=0.146
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@93553 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@93554 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@93539 executes=1874 executemany=0 prepared=9 prepared_execs=1828 share=0.975
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@93540 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.266 p95_ms=1.381 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=0.986 p95_ms=1.084 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=2.238 p95_ms=2.410 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=1.311 p95_ms=1.410 backend_calls=22.00 concurrency=1
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=1 thread_limit=4 requests=100 wall_ms=484.182 cpu_total_ms=392.894 cpu_main_ms=313.560 cpu_other_ms=79.334
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_e8d1c51479f9/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_e8d1c51479f9/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=600 txns=200 db_wall_ms=48.813 db_wall_ms_per_req=0.488
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=37.757 db_wall_ms_per_req=0.378
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_e8d1c51479f9/developer@93579 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_e8d1c51479f9/runtime@93580 executes=668 executemany=0 prepared=6 prepared_execs=633 share=0.948
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=494.435 cpu_total_ms=397.667 cpu_main_ms=315.316 cpu_other_ms=82.351
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_e8d1c51479f9/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_e8d1c51479f9/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=700 txns=400 db_wall_ms=56.575 db_wall_ms_per_req=0.566
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=38.640 db_wall_ms_per_req=0.386
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_e8d1c51479f9/developer@93579 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_e8d1c51479f9/runtime@93580 executes=1438 executemany=0 prepared=8 prepared_execs=1395 share=0.970
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=514.363 cpu_total_ms=413.114 cpu_main_ms=316.277 cpu_other_ms=96.837
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_e8d1c51479f9/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_e8d1c51479f9/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=65.752 db_wall_ms_per_req=0.658
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=800 txns=400 db_wall_ms=39.069 db_wall_ms_per_req=0.391
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_e8d1c51479f9/developer@93579 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_e8d1c51479f9/runtime@93580 executes=2648 executemany=0 prepared=8 prepared_execs=2605 share=0.984
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=4.837 p95_ms=4.981 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=4.937 p95_ms=5.133 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.137 p95_ms=5.336 backend_calls=19.00 concurrency=1
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 thread_limit=4 requests=100 wall_ms=476.907 cpu_total_ms=398.663 cpu_main_ms=301.772 cpu_other_ms=96.891
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_14754dc0d276 acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=app conns=2 gone=0 db_calls=1900 txns=500 db_wall_ms=66.612 db_wall_ms_per_req=0.666
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=25.587 db_wall_ms_per_req=0.256
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@93599 executes=334 executemany=0 prepared=5 prepared_execs=303 share=0.907
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@93600 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 thread_limit=4 requests=100 wall_ms=451.597 cpu_total_ms=384.705 cpu_main_ms=303.720 cpu_other_ms=80.985
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_14754dc0d276 acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=app conns=2 gone=0 db_calls=1100 txns=400 db_wall_ms=50.867 db_wall_ms_per_req=0.509
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=17.157 db_wall_ms_per_req=0.172
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@93599 executes=664 executemany=0 prepared=6 prepared_execs=629 share=0.947
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@93600 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 thread_limit=4 requests=100 wall_ms=584.174 cpu_total_ms=454.144 cpu_main_ms=304.173 cpu_other_ms=149.971
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_14754dc0d276 acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=app conns=2 gone=0 db_calls=4700 txns=1200 db_wall_ms=157.256 db_wall_ms_per_req=1.573
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=26.894 db_wall_ms_per_req=0.269
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@93599 executes=1434 executemany=0 prepared=6 prepared_execs=1393 share=0.971
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@93600 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 thread_limit=4 requests=100 wall_ms=487.909 cpu_total_ms=404.814 cpu_main_ms=305.327 cpu_other_ms=99.487
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_5c84f812 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_14754dc0d276 acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=app conns=4 gone=0 db_calls=2000 txns=600 db_wall_ms=78.627 db_wall_ms_per_req=0.786
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=1 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=200 txns=200 db_wall_ms=17.639 db_wall_ms_per_req=0.176
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@93617 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@93618 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@93599 executes=1874 executemany=0 prepared=9 prepared_execs=1828 share=0.975
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@93600 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=4.630 p95_ms=5.892 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=4.376 p95_ms=5.662 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=5.687 p95_ms=7.008 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=4.733 p95_ms=6.093 backend_calls=22.00 concurrency=1
```
```

#### K=32 `--warmup 3 --n 15 --concurrency 32`

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=d7a7500 date=2026-09-28
CPU peer=r2db-api plug=r2db-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=23.189 cpu_total_ms=22.379 cpu_main_ms=22.376 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=157.492 cpu_total_ms=156.612 cpu_main_ms=156.609 cpu_other_ms=0.003
CPU peer=r2db-api plug=r2db-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=959.307 cpu_total_ms=957.614 cpu_main_ms=957.611 cpu_other_ms=0.003
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=15 p50_ms=1.517 p95_ms=1.740 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=15 p50_ms=10.582 p95_ms=15.977 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=15 p50_ms=63.713 p95_ms=91.481 backend_calls=1.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api op=query concurrency=32 thread_limit=default requests=480 wall_ms=30.325 cpu_total_ms=29.445 cpu_main_ms=29.442 cpu_other_ms=0.003
CPU peer=MitateDB-api plug=MitateDB-api op=mutate concurrency=32 thread_limit=default requests=480 wall_ms=17.210 cpu_total_ms=16.320 cpu_main_ms=16.318 cpu_other_ms=0.002
CPU peer=MitateDB-api plug=MitateDB-api op=batch concurrency=32 thread_limit=default requests=480 wall_ms=51.257 cpu_total_ms=50.424 cpu_main_ms=50.414 cpu_other_ms=0.010
CPU peer=MitateDB-api plug=MitateDB-api op=cross_entity concurrency=32 thread_limit=default requests=480 wall_ms=28.548 cpu_total_ms=27.687 cpu_main_ms=27.683 cpu_other_ms=0.004
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=15 p50_ms=2.030 p95_ms=2.241 backend_calls=11.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=15 p50_ms=1.122 p95_ms=1.361 backend_calls=7.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=15 p50_ms=3.228 p95_ms=4.237 backend_calls=37.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=15 p50_ms=1.905 p95_ms=2.055 backend_calls=16.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-http op=query concurrency=32 thread_limit=4 requests=480 wall_ms=438.250 cpu_total_ms=591.218 cpu_main_ms=109.320 cpu_other_ms=481.898
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_ad4d86316d7d/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_ad4d86316d7d/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=app conns=5 gone=0 db_calls=2880 txns=960 db_wall_ms=513.376 db_wall_ms_per_req=1.070
DBTIME peer=r2db-api plug=r2db-api-http op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=703.870 db_wall_ms_per_req=1.466
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_ad4d86316d7d/developer@93758 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_ad4d86316d7d/runtime@93764 executes=859 executemany=0 prepared=6 prepared_execs=826 share=0.962
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_ad4d86316d7d/runtime@93760 executes=896 executemany=0 prepared=6 prepared_execs=861 share=0.961
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_ad4d86316d7d/runtime@93765 executes=853 executemany=0 prepared=6 prepared_execs=820 share=0.961
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_ad4d86316d7d/runtime@93766 executes=859 executemany=0 prepared=6 prepared_execs=826 share=0.962
CPU peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=479.818 cpu_total_ms=644.030 cpu_main_ms=115.520 cpu_other_ms=528.510
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_ad4d86316d7d/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_ad4d86316d7d/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=app conns=5 gone=0 db_calls=3360 txns=1920 db_wall_ms=614.439 db_wall_ms_per_req=1.280
DBTIME peer=r2db-api plug=r2db-api-http op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=708.155 db_wall_ms_per_req=1.475
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_ad4d86316d7d/developer@93758 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_ad4d86316d7d/runtime@93764 executes=1867 executemany=0 prepared=8 prepared_execs=1824 share=0.977
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_ad4d86316d7d/runtime@93765 executes=1861 executemany=0 prepared=8 prepared_execs=1818 share=0.977
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_ad4d86316d7d/runtime@93766 executes=1867 executemany=0 prepared=8 prepared_execs=1824 share=0.977
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_ad4d86316d7d/runtime@93760 executes=1904 executemany=0 prepared=8 prepared_execs=1861 share=0.977
CPU peer=r2db-api plug=r2db-api-http op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=575.665 cpu_total_ms=775.738 cpu_main_ms=125.333 cpu_other_ms=650.405
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_ad4d86316d7d/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_ad4d86316d7d/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=app conns=5 gone=0 db_calls=5280 txns=1920 db_wall_ms=850.879 db_wall_ms_per_req=1.773
DBTIME peer=r2db-api plug=r2db-api-http op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=775.070 db_wall_ms_per_req=1.615
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_ad4d86316d7d/developer@93758 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_ad4d86316d7d/runtime@93765 executes=3445 executemany=0 prepared=8 prepared_execs=3402 share=0.988
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_ad4d86316d7d/runtime@93764 executes=3451 executemany=0 prepared=8 prepared_execs=3408 share=0.988
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_ad4d86316d7d/runtime@93760 executes=3488 executemany=0 prepared=8 prepared_execs=3445 share=0.988
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_ad4d86316d7d/runtime@93766 executes=3451 executemany=0 prepared=8 prepared_execs=3408 share=0.988
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=15 p50_ms=28.868 p95_ms=31.296 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=30.564 p95_ms=37.904 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=15 p50_ms=37.001 p95_ms=46.747 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 thread_limit=4 requests=480 wall_ms=562.456 cpu_total_ms=481.284 cpu_main_ms=109.376 cpu_other_ms=371.908
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_3149b9d5ceab acquire=1159 waits=558 wait_total_ms=1217.444 wait_max_ms=8.174
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=546.929 db_wall_ms_per_req=1.139
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=960 txns=960 db_wall_ms=193.137 db_wall_ms_per_req=0.402
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@93779 executes=1732 executemany=0 prepared=9 prepared_execs=1673 share=0.966
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@93780 executes=9244 executemany=0 prepared=5 prepared_execs=9204 share=0.996
CPU peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=424.351 cpu_total_ms=379.386 cpu_main_ms=103.776 cpu_other_ms=275.610
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_3149b9d5ceab acquire=2313 waits=1116 wait_total_ms=2082.047 wait_max_ms=30.775
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=250.962 db_wall_ms_per_req=0.523
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=mutate concurrency=32 scope=platform sessions=1 connect_wall_ms=2.638 db_calls=961 txns=961 db_wall_ms=219.162 db_wall_ms_per_req=0.462
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@93779 executes=3460 executemany=0 prepared=10 prepared_execs=3395 share=0.981
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@93780 executes=13852 executemany=0 prepared=6 prepared_execs=13809 share=0.997
CPU peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=1076.639 cpu_total_ms=720.901 cpu_main_ms=114.544 cpu_other_ms=606.357
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_3149b9d5ceab acquire=3467 waits=1674 wait_total_ms=5107.784 wait_max_ms=30.775
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=824.396 db_wall_ms_per_req=1.717
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=batch concurrency=32 scope=platform sessions=1 connect_wall_ms=2.580 db_calls=961 txns=961 db_wall_ms=214.852 db_wall_ms_per_req=0.453
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@93779 executes=7492 executemany=0 prepared=16 prepared_execs=7401 share=0.988
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@93780 executes=36892 executemany=0 prepared=6 prepared_execs=36849 share=0.999
CPU peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 thread_limit=4 requests=480 wall_ms=566.902 cpu_total_ms=452.173 cpu_main_ms=112.218 cpu_other_ms=339.955
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_719f1470 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_3149b9d5ceab acquire=4625 waits=2232 wait_total_ms=6518.476 wait_max_ms=30.775
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=395.865 db_wall_ms_per_req=0.825
DBTIME peer=MitateDB-api plug=MitateDB-api-http op=cross_entity concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=960 txns=960 db_wall_ms=195.892 db_wall_ms_per_req=0.408
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@93804 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@93805 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@93779 executes=9796 executemany=0 prepared=17 prepared_execs=9690 share=0.989
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@93780 executes=46128 executemany=0 prepared=6 prepared_execs=9186 share=0.199
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=15 p50_ms=36.928 p95_ms=39.536 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=26.282 p95_ms=35.421 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=15 p50_ms=69.825 p95_ms=81.381 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=15 p50_ms=37.288 p95_ms=39.887 backend_calls=22.00 concurrency=32
CPU peer=r2db-api plug=r2db-api-socket op=query concurrency=32 thread_limit=4 requests=480 wall_ms=2072.362 cpu_total_ms=2457.744 cpu_main_ms=1601.485 cpu_other_ms=856.259
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_5ca13b9d9e14/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_5ca13b9d9e14/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=app conns=5 gone=0 db_calls=2880 txns=960 db_wall_ms=869.818 db_wall_ms_per_req=1.812
DBTIME peer=r2db-api plug=r2db-api-socket op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3840 txns=1920 db_wall_ms=1306.472 db_wall_ms_per_req=2.722
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_5ca13b9d9e14/developer@93834 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_5ca13b9d9e14/runtime@93840 executes=853 executemany=0 prepared=6 prepared_execs=816 share=0.957
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_5ca13b9d9e14/runtime@93835 executes=896 executemany=0 prepared=6 prepared_execs=859 share=0.959
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_5ca13b9d9e14/runtime@93841 executes=853 executemany=0 prepared=6 prepared_execs=820 share=0.961
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_5ca13b9d9e14/runtime@93839 executes=865 executemany=0 prepared=6 prepared_execs=832 share=0.962
CPU peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=2125.689 cpu_total_ms=2547.886 cpu_main_ms=1629.055 cpu_other_ms=918.831
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_5ca13b9d9e14/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_5ca13b9d9e14/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=app conns=5 gone=0 db_calls=3360 txns=1920 db_wall_ms=1135.155 db_wall_ms_per_req=2.365
DBTIME peer=r2db-api plug=r2db-api-socket op=mutate concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=1264.746 db_wall_ms_per_req=2.635
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_5ca13b9d9e14/developer@93834 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_5ca13b9d9e14/runtime@93841 executes=1861 executemany=0 prepared=8 prepared_execs=1818 share=0.977
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_5ca13b9d9e14/runtime@93839 executes=1866 executemany=0 prepared=8 prepared_execs=1823 share=0.977
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_5ca13b9d9e14/runtime@93835 executes=1911 executemany=0 prepared=8 prepared_execs=1864 share=0.975
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_5ca13b9d9e14/runtime@93840 executes=1861 executemany=0 prepared=8 prepared_execs=1814 share=0.975
CPU peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=2243.284 cpu_total_ms=2732.379 cpu_main_ms=1640.622 cpu_other_ms=1091.757
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_5ca13b9d9e14/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_5ca13b9d9e14/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=app conns=5 gone=0 db_calls=5280 txns=1920 db_wall_ms=1511.751 db_wall_ms_per_req=3.149
DBTIME peer=r2db-api plug=r2db-api-socket op=batch concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=3842 txns=1921 db_wall_ms=1385.632 db_wall_ms_per_req=2.887
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_5ca13b9d9e14/developer@93834 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_5ca13b9d9e14/runtime@93841 executes=3467 executemany=0 prepared=8 prepared_execs=3424 share=0.988
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_5ca13b9d9e14/runtime@93835 executes=3495 executemany=0 prepared=8 prepared_execs=3446 share=0.986
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_5ca13b9d9e14/runtime@93840 executes=3434 executemany=0 prepared=8 prepared_execs=3385 share=0.986
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_5ca13b9d9e14/runtime@93839 executes=3439 executemany=0 prepared=8 prepared_execs=3396 share=0.987
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=15 p50_ms=137.486 p95_ms=144.378 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=15 p50_ms=139.778 p95_ms=149.785 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=15 p50_ms=147.695 p95_ms=158.195 backend_calls=19.00 concurrency=32
CPU peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 thread_limit=4 requests=480 wall_ms=2147.333 cpu_total_ms=2213.648 cpu_main_ms=1577.751 cpu_other_ms=635.897
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_414bba9d27bc acquire=1159 waits=556 wait_total_ms=1816.279 wait_max_ms=7.026
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=app conns=2 gone=0 db_calls=9120 txns=2400 db_wall_ms=786.683 db_wall_ms_per_req=1.639
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=query concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=960 txns=960 db_wall_ms=357.535 db_wall_ms_per_req=0.745
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@93864 executes=1732 executemany=0 prepared=15 prepared_execs=1645 share=0.950
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@93865 executes=9244 executemany=0 prepared=5 prepared_execs=9204 share=0.996
CPU peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 thread_limit=4 requests=480 wall_ms=1995.349 cpu_total_ms=2113.840 cpu_main_ms=1565.971 cpu_other_ms=547.869
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_414bba9d27bc acquire=2313 waits=1112 wait_total_ms=3215.567 wait_max_ms=37.142
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=app conns=2 gone=0 db_calls=5280 txns=1920 db_wall_ms=469.110 db_wall_ms_per_req=0.977
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=mutate concurrency=32 scope=platform sessions=1 connect_wall_ms=2.641 db_calls=961 txns=961 db_wall_ms=400.158 db_wall_ms_per_req=0.839
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@93864 executes=3460 executemany=0 prepared=16 prepared_execs=3367 share=0.973
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@93865 executes=13852 executemany=0 prepared=6 prepared_execs=13809 share=0.997
CPU peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 thread_limit=4 requests=480 wall_ms=2651.762 cpu_total_ms=2448.662 cpu_main_ms=1582.182 cpu_other_ms=866.480
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_414bba9d27bc acquire=3467 waits=1670 wait_total_ms=6855.898 wait_max_ms=37.142
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=app conns=2 gone=0 db_calls=22560 txns=5760 db_wall_ms=1039.630 db_wall_ms_per_req=2.166
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=batch concurrency=32 scope=platform sessions=1 connect_wall_ms=2.664 db_calls=961 txns=961 db_wall_ms=359.423 db_wall_ms_per_req=0.754
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@93864 executes=7492 executemany=0 prepared=24 prepared_execs=7367 share=0.983
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@93865 executes=36892 executemany=0 prepared=6 prepared_execs=36849 share=0.999
CPU peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 thread_limit=4 requests=480 wall_ms=2155.417 cpu_total_ms=2191.265 cpu_main_ms=1602.857 cpu_other_ms=588.408
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_3d9104f4 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_414bba9d27bc acquire=4625 waits=2228 wait_total_ms=8822.115 wait_max_ms=37.142
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=app conns=4 gone=0 db_calls=9600 txns=2880 db_wall_ms=613.251 db_wall_ms_per_req=1.278
DBTIME peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity concurrency=32 scope=platform sessions=0 connect_wall_ms=0.000 db_calls=960 txns=960 db_wall_ms=324.808 db_wall_ms_per_req=0.677
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@93900 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@93901 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@93864 executes=9796 executemany=0 prepared=25 prepared_execs=9664 share=0.987
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@93865 executes=46128 executemany=0 prepared=6 prepared_execs=9186 share=0.199
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=15 p50_ms=142.583 p95_ms=150.958 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=15 p50_ms=131.104 p95_ms=146.901 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=15 p50_ms=174.617 p95_ms=188.120 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=15 p50_ms=141.771 p95_ms=155.670 backend_calls=22.00 concurrency=32
```
```

### 5.2 事実 (§5.1 の数字だけから。判断語を含まない)

1. **`query` の p50 (ms)**。基準は v0.2 §3 の 2 の「既定 K1」「既定 K32」列の転記。相対差 = (今回 − 基準) / 基準。

| plug | 基準 K=1 | 今回 K=1 | 相対差 K=1 | 基準 K=32 | 今回 K=32 | 相対差 K=32 |
|---|---|---|---|---|---|---|
| r2db-api-http | 1.478 | 1.388 | -6.1% | 49.255 | 28.868 | -41.4% (K=32/K=1 = 20.8) |
| r2db-api-socket | 4.834 | 4.837 | +0.1% | 153.881 | 137.486 | -10.7% (K=32/K=1 = 28.4) |
| MitateDB-api-http | 6.301 | 1.266 | -79.9% | 188.586 | 36.928 | -80.4% (K=32/K=1 = 29.2) |
| MitateDB-api-socket | 9.869 | 4.630 | -53.1% | 291.281 | 142.583 | -51.1% (K=32/K=1 = 30.8) |

2. **`CPU` 行の `thread_limit=`**: PostgreSQL の 4 plug の各行 は K=1・K=32 とも `thread_limit=4` (4 plug × 2 run = 8 行、`op=query`。他の op も同じ)。in-process の 2 plug は D-10 のとおり accessor を持たないので `thread_limit=default` のまま (WO §7.3 D-10、起草の疑義 (8) の残り)。
3. **MitateDB 2 plug の `DBTIME scope=platform`**: 基準は K=1 で connect_wall_ms 4.189 / 4.485 ms/req、sessions 2/req (v0.2 §3 の 7)。今回は K=1・K=32 とも `sessions=0 connect_wall_ms=0.000` (http / socket、`op=query`)。db_wall_ms_per_req は K=1 で 0.145 / 0.256、K=32 で 0.402 / 0.745 ms。
4. どの run も `LIMIT_EXCEEDED` で欠けていない (`PERF` 行は run ごと 21 行 = 6 plug、in-process 2 plug は 3 op)。r2db の `POOL` 行の waits は全 run で 0。in-process 2 plug の `CPU` 行は `thread_limit=default` (accessor を持たない。WO §7.3 D-10)。

### 5.3 判断 (監督)

判定規則 (WO §10.1 の逐語。計測前に固定):

```text
D-12 判定規則 (計測前に固定): 同じ道具・同じ条件 (`DSA_PERF_POOL_SIZE=32`、K=1 `--warmup 10 --n 100`、K=32 `--warmup 3 --n 15`、`DSA_PERF_THREAD_LIMIT` 無し)、基準 = 設計メモ v0.2 §2.2 の既定 run (K=1 :625-、K=32 :1213-)。合格: query p50 (K=32) が 4 plug 中 3 plug 以上で 10% を超えて改善、どの plug も 10% を超えて悪化しない、K=1 の p50 が ±10% 内 (MitateDB 2 plug の K=1 は D-11 で connect が消えるので「悪化しない」だけを見る)。設計メモ v0.3 §5 に逐語。8 倍は WP-3 では判定しない (床)。
```

| 項 | r2db-api-http | r2db-api-socket | MitateDB-api-http | MitateDB-api-socket |
|---|---|---|---|---|
| K=32 の p50 が 10% を超えて改善 (4 plug 中 3 plug 以上) | 成立 (−41.4%) | 成立 (−10.7%) | 成立 (−80.4%) | 成立 (−51.1%) |
| K=32 の p50 が 10% を超えて悪化しない | 成立 | 成立 | 成立 | 成立 |
| K=1 の p50 が ±10% 内 (MitateDB は悪化しないことだけ) | 成立 (−6.1%) | 成立 (+0.1%) | 成立 (−79.9%、悪化なし) | 成立 (−53.1%、悪化なし) |

**判定**: **D-12 成立** (改善 >10% は 4/4 plug、悪化 0、K=1 は r2db 2 plug が ±10% 内、MitateDB 2 plug は悪化なし)。8 倍 (`RM` §0.1.4 の 2) は現行 plug では 20.8 / 28.4 / 29.2 / 30.8 倍で不成立 — WO §7.1 の床 (client が同 GIL) のとおりで、判定は §6 (D-16) に委ねる。WP-3 の効きの読み (規則の出力ではなく観察): thread limiter 4 は K=32 で −41% / −11% (r2db)、MitateDB は platform pool で K=1 から −80% / −53% (per-call `psycopg.connect` ×2 が消えた分) が主。

## 6. real-server plug の実測 (D-16。監督が埋める)

**目的**: R-101 の閉止を D-16 (`RM` §0.1.4 の 2 の改訂形) で判定する。8 倍を満たさないときは、その実測を R-113 (multi-process worker) の出発点にする (WO §10.1)。

**方法**: `tools/perf_baseline.py --real-server r2db-api` と `--real-server MitateDB-api`。server は `conformance-tests/registry.json` の `composition_roots` の launcher (C-26) が production の composition root で別 process に起動する (`start(ceilings={"data": 1, "control": 1})`、thread limit は既定 4)。client は子 process (`--client-processes` 既定 8、実際の数は min(8, K))。K=1 と K=32 を取り、K=32 は 2 run。いずれも `--warmup 3 --n 15`。`REALCPU` は床の可視化であり判定に使わない。server 側の `CPU` / `DBTIME` 行は出ない (別 process。WO §7.3 の D-15)。実行順は r2db K=1 → K=32 → K=32、MitateDB K=1 → K=32 → K=32 (直列、他の pytest と nginx 無し)。道具の木は `fdb5e61` (r101b。`d7a7500` での最初の試行は両 peer とも `POST /control/v1/credentials -> 403` で止まり (WO §6.1 の訂正註 14)、launcher の `control_credential_id` と perf tool の自己 rotate を足した木で取り直した)。

### 6.1 実測 (逐語)

#### 【1 回目 = 欠陥のある計測器 (tree fdb5e61、子 process を group ごとに生成)】r2db-api K=1

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=fdb5e61 date=2026-09-28
REALPERF peer=r2db-api plug=r2db-api-real transport=real-server op=query concurrency=1 client_processes=1 n=15 p50_ms=10.425 p95_ms=11.771
REALCPU peer=r2db-api plug=r2db-api-real op=query concurrency=1 client_processes=1 requests=15 wall_ms=162.368 cpu_client_ms=120.456
```
```

#### 【1 回目 = 欠陥のある計測器 (tree fdb5e61、子 process を group ごとに生成)】r2db-api K=32 (1 回目)

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=fdb5e61 date=2026-09-28
REALPERF peer=r2db-api plug=r2db-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=48.265 p95_ms=50.910
REALCPU peer=r2db-api plug=r2db-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=726.414 cpu_client_ms=1822.714
```
```

#### 【1 回目 = 欠陥のある計測器 (tree fdb5e61、子 process を group ごとに生成)】r2db-api K=32 (2 回目)

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=fdb5e61 date=2026-09-28
REALPERF peer=r2db-api plug=r2db-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=47.712 p95_ms=51.009
REALCPU peer=r2db-api plug=r2db-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=721.201 cpu_client_ms=1825.603
```
```

#### 【1 回目 = 欠陥のある計測器 (tree fdb5e61、子 process を group ごとに生成)】MitateDB-api K=1

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=fdb5e61 date=2026-09-28
REALPERF peer=MitateDB-api plug=MitateDB-api-real transport=real-server op=query concurrency=1 client_processes=1 n=15 p50_ms=10.905 p95_ms=11.404
REALCPU peer=MitateDB-api plug=MitateDB-api-real op=query concurrency=1 client_processes=1 requests=15 wall_ms=160.788 cpu_client_ms=123.702
```
```

#### 【1 回目 = 欠陥のある計測器 (tree fdb5e61、子 process を group ごとに生成)】MitateDB-api K=32 (1 回目)

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=fdb5e61 date=2026-09-28
REALPERF peer=MitateDB-api plug=MitateDB-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=46.761 p95_ms=49.208
REALCPU peer=MitateDB-api plug=MitateDB-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=708.138 cpu_client_ms=1833.484
```
```

#### 【1 回目 = 欠陥のある計測器 (tree fdb5e61、子 process を group ごとに生成)】MitateDB-api K=32 (2 回目)

```
```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=fdb5e61 date=2026-09-28
REALPERF peer=MitateDB-api plug=MitateDB-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=46.571 p95_ms=49.115
REALCPU peer=MitateDB-api plug=MitateDB-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=705.120 cpu_client_ms=1836.824
```
```

**2 回目 (D-15a、WO §6.1 監督裁定 17)。** 受け入れ監査の観察 1 (client の子 process と `httpx.AsyncClient` が group ごとに新しく作られ、K=1 の measured 窓に httpcore の遅延 import (CPU 6.5〜7.4 ms) が入る) を計測器の欠陥として採り、子を (plug, K) ごとに 1 回だけ作って warmup と measured の全 group を同じ子で送る形に直した (差し戻し 5〜6、M215〜M217)。tree `715e8ad` (最終ゲート r101d の tree)。実行順は 1 回目と同じ。

#### 【2 回目 = D-15a (tree 715e8ad、子 process は (plug, K) ごとに 1 回、warmup も同じ子)】r2db-api K=1

```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=715e8ad date=2026-09-28
REALPERF peer=r2db-api plug=r2db-api-real transport=real-server op=query concurrency=1 client_processes=1 n=15 p50_ms=2.252 p95_ms=3.570
REALCPU peer=r2db-api plug=r2db-api-real op=query concurrency=1 client_processes=1 requests=15 wall_ms=40.518 cpu_client_ms=8.250
```

#### 【2 回目 = D-15a (tree 715e8ad、子 process は (plug, K) ごとに 1 回、warmup も同じ子)】r2db-api K=32 (1 回目)

```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=715e8ad date=2026-09-28
REALPERF peer=r2db-api plug=r2db-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=35.414 p95_ms=37.754
REALCPU peer=r2db-api plug=r2db-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=535.706 cpu_client_ms=599.113
```

#### 【2 回目 = D-15a (tree 715e8ad、子 process は (plug, K) ごとに 1 回、warmup も同じ子)】r2db-api K=32 (2 回目)

```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=715e8ad date=2026-09-28
REALPERF peer=r2db-api plug=r2db-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=35.491 p95_ms=36.746
REALCPU peer=r2db-api plug=r2db-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=533.868 cpu_client_ms=591.860
```

#### 【2 回目 = D-15a (tree 715e8ad、子 process は (plug, K) ごとに 1 回、warmup も同じ子)】MitateDB-api K=1

```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=715e8ad date=2026-09-28
REALPERF peer=MitateDB-api plug=MitateDB-api-real transport=real-server op=query concurrency=1 client_processes=1 n=15 p50_ms=1.915 p95_ms=2.996
REALCPU peer=MitateDB-api plug=MitateDB-api-real op=query concurrency=1 client_processes=1 requests=15 wall_ms=33.893 cpu_client_ms=8.160
```

#### 【2 回目 = D-15a (tree 715e8ad、子 process は (plug, K) ごとに 1 回、warmup も同じ子)】MitateDB-api K=32 (1 回目)

```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=715e8ad date=2026-09-28
REALPERF peer=MitateDB-api plug=MitateDB-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=35.757 p95_ms=37.344
REALCPU peer=MitateDB-api plug=MitateDB-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=541.236 cpu_client_ms=576.760
```

#### 【2 回目 = D-15a (tree 715e8ad、子 process は (plug, K) ごとに 1 回、warmup も同じ子)】MitateDB-api K=32 (2 回目)

```text
PERFRUN host=Darwin/arm64 python=3.11.15 commit=715e8ad date=2026-09-28
REALPERF peer=MitateDB-api plug=MitateDB-api-real transport=real-server op=query concurrency=32 client_processes=8 n=15 p50_ms=36.058 p95_ms=37.518
REALCPU peer=MitateDB-api plug=MitateDB-api-real op=query concurrency=32 client_processes=8 requests=480 wall_ms=543.595 cpu_client_ms=584.081
```

### 6.2 事実 (§6.1 の数字だけから。判断語を含まない)

1. **`query` の p50 (ms) と K=32 / K=1 の比**:

| peer | K=1 | K=32 (1 回目) | K=32 (2 回目) | 比 (1 回目) | 比 (2 回目) |
|---|---|---|---|---|---|
| r2db-api | 10.425 | 48.265 | 47.712 | 4.63 | 4.58 | (1 回目、欠陥のある計測器)
| MitateDB-api | 10.905 | 46.761 | 46.571 | 4.29 | 4.27 | (1 回目、欠陥のある計測器)
| r2db-api (2 回目、D-15a) | 2.252 | 35.414 | 35.491 | 15.72 | 15.76 |
| MitateDB-api (2 回目、D-15a) | 1.915 | 35.757 | 36.058 | 18.67 | 18.83 |

2. **ε と δ** (記録のみ。判定に使わない): ε = K=32 の 2 run の p50 の相対差 = r2db 1.1% (48.265 vs 47.712) / MitateDB 0.4% (46.761 vs 46.571)。δ = max(10%, 2ε) = 10% (両 peer)。 **2 回目**: ε = r2db 0.2% (35.414 vs 35.491) / MitateDB 0.8% (35.757 vs 36.058)。δ = 10%。
3. **`REALCPU`** (床の可視化): `client_processes=` は K=1 で 1、K=32 で 8 (両 peer)。`cpu_client_ms` / `requests` = r2db K=1 8.03 ms/req (120.456 / 15)、K=32 3.80 / 3.80 ms/req (1822.714 / 480、1825.603 / 480); MitateDB K=1 8.25 (123.702 / 15)、K=32 3.82 / 3.83 ms/req。K=1 の wall/req (162.368 / 15 = 10.82 ms、160.788 / 15 = 10.72 ms) の 74〜77% が client 自身の CPU。K=32 では 8 process に分かれるので client の床 = 32 × 3.80 / 8 = 15.2 ms (r2db)、15.3 ms (MitateDB) で、group p50 48 / 47 ms の約 1/3。real-server の K=1 p50 (10.4 / 10.9 ms) は socket plug の K=1 (4.837 / 4.630 ms、§5) の 2.2 / 2.4 倍で、差は client 経路 (別 process の httpx、nginx 経由) の固定費。 **2 回目**: `cpu_client_ms` / `requests` = r2db K=1 0.55 ms/req (8.250 / 15)、K=32 1.25 / 1.23 ms/req; MitateDB K=1 0.54、K=32 1.20 / 1.22 ms/req。K=1 の wall/req (40.518 / 15 = 2.70 ms、33.893 / 15 = 2.26 ms) のうち client の CPU は 20〜24%。1 回目との差 (K=1 の client CPU 8.0 → 0.55 ms/req、p50 10.4 → 2.25 ms) が、監査の観察 1 の「子の初回コスト」そのものである。real-server の K=1 p50 (2.25 / 1.92 ms) は socket plug の K=1 (4.837 / 4.630 ms、§5) より小さい (client が別 process で GIL を分け合わないため)。
4. **後始末の照合** (WO §10.2 の 4): 6 run とも `perf_baseline` は launcher の `stop()` を 1 回呼んで終了し (run の最終行は `REALCPU`、traceback 無し)、run 後の `ps` に uvicorn / nginx / perf_baseline の残プロセスは 0 (監督が `ps -eo args=` で照合)。使い捨て cluster は run ごとに作られ捨てられる (`suite_lock(exclusive=True)` の下、WO §7.5 の (W-12))。 **2 回目**も同じ (6 run とも最終行は `REALCPU`、run 後の `ps` に今回の uvicorn / nginx / perf_baseline / 子 process は 0。開発機には 2026-09-05〜17 の別セッションの socket harness の nginx と conformance の uvicorn が残っているが、今回の run のものではない = 引き継ぎ書に観察として記す)。共有クラスタの pg_database / pg_roles 差分は完了ゲート r101d で 0。

### 6.3 判断 (監督)

判定規則 (WO §10.1 の逐語。計測前に固定):

```text
D-16 閉止の判定規則 (計測前に固定): real-server plug で K=1 と K=32 (`--warmup 3 --n 15`) を取り、K=32 は 2 run 取る。query の p50 の K=32 / K=1 の比が両 peer で K=32 の 2 run とも 8 倍以内 = R-101 閉止 (RM §0.1.4 の 2 の改訂形)。ε (K=32 の 2 run の相対差) と δ = max(10%, 2ε) は記録だけで、判定には使わない。本変更セットでは server は 1 process なので 8 倍は満たさない見込み — その実測を設計メモ v0.3 §6 に逐語で残し、R-113 (multi-process、規模 L) の出発点にする。
```

| peer | K=32 (1 回目) の比 ≤ 8 | K=32 (2 回目) の比 ≤ 8 |
|---|---|---|
| r2db-api | 1 回目 成立 (4.63 / 4.58 ≤ 8) → **無効** (計測器の欠陥) / **2 回目 不成立 (15.72 / 15.76 > 8)** | **不成立** |
| MitateDB-api | 1 回目 成立 (4.29 / 4.27 ≤ 8) → **無効** (計測器の欠陥) / **2 回目 不成立 (18.67 / 18.83 > 8)** | **不成立** |

**判定**: **D-16 不成立** (2 回目 = 欠陥を直した計測器。両 peer とも K=32 の 2 run が 8 倍を超える: r2db 15.7 / 15.8、MitateDB 18.7 / 18.8)。1 回目の「成立」は計測器の欠陥 (K=1 の分母に子の初回コストが入る) による見かけで、無効とする (WO §6.1 監督裁定 17・20)。規則 D-16 は動かしていない。
**R-101 の閉止**: **否** — `RM` §0.1.4 の 2 (改訂形) を満たさない。台帳 R-101 行の「閉止 2026-09-28」は監督裁定 20 で取り消す (R-14 の形で行を残す)。**観察**: 2 回目の分母 (K=1 2.25 / 1.92 ms) は client の CPU が 20〜24% で、1 回目の懸念 (分母が client に支配される) は解消している。server 1 process・thread limiter 4 での実効並行は 32 / 15.7 ≈ 2.0 (r2db)、32 / 18.7 ≈ 1.7 (MitateDB)。
**R-113 への申し送り**: 1 process の server では 8 倍以内に届かない (15.7 / 18.7 倍、実効並行 2.0 / 1.7) ので、§0.1.4 の 2 を満たす候補は GIL の外に出る multi-process worker (R-113、規模 L、設計レビュー、in-memory の limit 状態の置き場を含む) である。着手は依頼者判断 (引き継ぎ書 §4)。出発点の数字: 2 回目の `REALPERF` / `REALCPU` (§6.1)、server 側の直列区間 ≈ group p50 − client の床 (32 × 1.25 / 8 = 5.0 ms) ≈ 30 ms = 要求あたり約 0.95 ms (r2db)。
