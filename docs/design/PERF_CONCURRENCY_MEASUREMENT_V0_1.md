# 設計メモ — 接続プールの取得待ちと `K` の実測 (R-78)

## 0. 版数・位置づけ

- **v0.2 (2026-09-23)。** WP-2 (監督) が §2〜§4 を埋めた (sweep 12 run、判断 4 点、R-101・R-102 起票)。
- v0.1 (2026-09-23)。WP-1 (実装担当) が骨だけを置いた。基点は `docs/work-orders/WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md` (以下「WO」)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-78 行。

## 1. 目的と方法

**目的**: 「プールの取得待ちが実際に起きているのか、それとも別の直列化 (uvicorn の threadpool / GIL / PostgreSQL) が支配的なのか」を、数字で区別できる形にする (WO §1.1)。寸法 (pool の `maxconn`、`concurrency`、role の `CONNECTION LIMIT`) の変更判断は本メモの範囲外であり、計測の後に別の変更セットで行う (WO §1.1 (a)、`RM`:305 の P-8、`RM`:448 の R-20)。

**道具と引数**: `tools/perf_baseline.py --warmup <W> --n <N> --concurrency <K>`。WP-1 で `POOL` 行 (D-2) と r2db `-http`/`-socket` plug の `DSA_PERF_POOL_SIZE` 環境変数 (D-2 追補) が追加された。実行は本 worktree の道具を worktree の cwd から呼ぶ。

**K の並びと K ごとの `--warmup`/`--n`** (WO §1.2 D-3 の表、credential ごと毎分 600 件の rate 上限に収めるため):

| K | `--warmup` | `--n` | `(warmup + n) * K` |
|---|---|---|---|
| 1・2・4 | 10 | 100 | 110 / 220 / 440 |
| 8 | 5 | 50 | 440 |
| 16 | 5 | 30 | 560 |
| 32 | 3 | 15 | 576 |

**K > 32 を測らない理由**: `concurrency` の既定 (`ResourceLimits.concurrency` = 32) を超える要求は `DataService._slot` の事前拒否ゲートで待たずに `LIMIT_EXCEEDED` (429) になる (WO §1.3 の (3))。プールの取得待ちを計る前に別の理由で拒否されるので、K > 32 は本件の計測対象にならない。

**r2db の pool の寸法は 2 通りで取る** (WO §1.2 D-3): `DSA_PERF_POOL_SIZE` 未設定 (既定 2、conformance の現状) と `DSA_PERF_POOL_SIZE=32` (production の `role_pool_size(ResourceLimits())` と同じ)。どちらで取った run かは `POOL` 行の `size=` 列に現れる。

**合成環境である旨**: 以下の実測はすべて開発機のローカル PostgreSQL クラスタに対するものであり、ホスト名・実 DSN・作業機の絶対パスは記録しない (WO §1.1 (d)、OPERATING_CONDITIONS.md §1.9)。`PERFRUN` の `host=` は `<OS/arch>` の形式である。

## 2. 実測 (監督、2026-09-23、worktree r78 = commit `7a7f817` の道具、開発機のローカル PostgreSQL)

各 run は `DSA_PERF_POOL_SIZE=<size> tools/perf_baseline.py --concurrency <K> --warmup <W> --n <N>`。`PERFRUN` の `host=` と `role=`/`lock=` の application id は伏せた (合成値)。`POOL` 行は plug 累積 (op ごとに reset しない — `tools/PERF_BASELINE_README.md`)。in-process plug (r2db = in-memory、MitateDB = SQLite) は PostgreSQL を通らないので表からは外す (逐語行には含む)。

### 2.1 `DSA_PERF_POOL_SIZE=2` — `query` の p50 (ms) と、r2db-http の runtime pool / MitateDB-http の cell lock の累積 (`batch`/`cross_entity` 時点)

| K | r2db-http | r2db-socket | MitateDB-http | MitateDB-socket | r2db-http runtime pool waits/acquire, wait_max | MitateDB-http lock waits/acquire, wait_max |
|---|---|---|---|---|---|---|
| 1 | 2.672 | 6.262 | 6.300 | 9.873 | 0/331, 0.000 ms | 0/890, 0.000 ms |
| 2 | 3.387 | 10.114 | 9.417 | 16.340 | 0/661, 0.000 ms | 440/1770, 28.159 ms |
| 4 | 6.986 | 19.030 | 14.709 | 26.621 | 659/1321, 2.541 ms | 985/3530, 34.205 ms |
| 8 | 16.365 | 38.854 | 44.720 | 66.633 | 988/1321, 7.666 ms | 1212/3530, 36.515 ms |
| 16 | 31.911 | 80.371 | 96.914 | 147.754 | 1468/1681, 17.670 ms | 1852/4490, 43.669 ms |
| 32 | 62.672 | 163.904 | 211.453 | 309.189 | 1610/1729, 35.019 ms | 2058/4618, 67.056 ms |

### 2.2 `DSA_PERF_POOL_SIZE=32` — `query` の p50 (ms) と、r2db-http の runtime pool / MitateDB-http の cell lock の累積 (`batch`/`cross_entity` 時点)

| K | r2db-http | r2db-socket | MitateDB-http | MitateDB-socket | r2db-http runtime pool waits/acquire, wait_max | MitateDB-http lock waits/acquire, wait_max |
|---|---|---|---|---|---|---|
| 1 | 2.663 | 6.380 | 6.281 | 9.981 | 0/331, 0.000 ms | 0/890, 0.000 ms |
| 2 | 3.362 | 10.036 | 9.481 | 16.157 | 0/661, 0.000 ms | 440/1770, 25.239 ms |
| 4 | 5.668 | 18.692 | 19.741 | 30.045 | 0/1321, 0.000 ms | 1019/3530, 29.690 ms |
| 8 | 14.626 | 42.967 | 52.822 | 73.352 | 0/1321, 0.000 ms | 1168/3530, 35.870 ms |
| 16 | 31.994 | 90.533 | 110.195 | 159.117 | 0/1681, 0.000 ms | 1846/4490, 57.259 ms |
| 32 | 67.423 | 185.491 | 219.874 | 317.518 | 0/1729, 0.000 ms | 2022/4618, 63.369 ms |

### 2.3 逐語 (12 run の `PERFRUN`/`PERF`/`POOL` 行)

`DSA_PERF_POOL_SIZE=2 --concurrency 1 --warmup 10 --n 100`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.115 p95_ms=0.127 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.174 p95_ms=0.212 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.515 p95_ms=0.700 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.132 p95_ms=0.135 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.109 p95_ms=0.113 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.174 p95_ms=0.181 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.128 p95_ms=0.137 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=2.672 p95_ms=2.880 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=2.675 p95_ms=2.790 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=2.908 p95_ms=3.083 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=446 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=666 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_8eb97af3 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=890 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.300 p95_ms=6.470 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.057 p95_ms=6.331 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.297 p95_ms=7.669 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.316 p95_ms=6.594 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=6.262 p95_ms=6.485 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=6.344 p95_ms=6.587 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=6.584 p95_ms=6.821 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=446 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=666 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_a4ecf49a acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=890 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.873 p95_ms=11.254 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.793 p95_ms=11.009 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=10.919 p95_ms=12.505 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.002 p95_ms=11.322 backend_calls=22.00 concurrency=1
```

`DSA_PERF_POOL_SIZE=2 --concurrency 2 --warmup 10 --n 100`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.170 p95_ms=0.178 backend_calls=1.00 concurrency=2
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.353 p95_ms=0.523 backend_calls=1.00 concurrency=2
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=1.617 p95_ms=2.366 backend_calls=1.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.177 p95_ms=0.185 backend_calls=11.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.129 p95_ms=0.135 backend_calls=7.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.254 p95_ms=0.262 backend_calls=37.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.191 p95_ms=0.198 backend_calls=16.00 concurrency=2
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=2 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=2 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=3.387 p95_ms=3.527 backend_calls=14.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=3.466 p95_ms=3.599 backend_calls=15.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=3.789 p95_ms=3.999 backend_calls=19.00 concurrency=2
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=446 waits=110 wait_total_ms=45.932 wait_max_ms=2.165
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=886 waits=220 wait_total_ms=76.648 wait_max_ms=2.165
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=1326 waits=330 wait_total_ms=250.556 wait_max_ms=3.374
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_54d1ff0e acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=1770 waits=440 wait_total_ms=349.816 wait_max_ms=28.159
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=9.417 p95_ms=9.883 backend_calls=21.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=9.003 p95_ms=9.365 backend_calls=13.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=11.553 p95_ms=11.929 backend_calls=49.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=9.505 p95_ms=9.935 backend_calls=22.01 concurrency=2
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=2 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=2 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=10.114 p95_ms=10.301 backend_calls=14.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=10.224 p95_ms=10.525 backend_calls=15.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=10.544 p95_ms=10.753 backend_calls=19.00 concurrency=2
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=446 waits=110 wait_total_ms=49.332 wait_max_ms=2.281
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=886 waits=220 wait_total_ms=84.667 wait_max_ms=2.281
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=1326 waits=330 wait_total_ms=262.330 wait_max_ms=2.439
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_649dd28f acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=1770 waits=440 wait_total_ms=364.886 wait_max_ms=21.756
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=16.340 p95_ms=17.526 backend_calls=21.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=15.802 p95_ms=16.965 backend_calls=13.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=18.220 p95_ms=19.362 backend_calls=49.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=16.304 p95_ms=17.488 backend_calls=22.01 concurrency=2
```

`DSA_PERF_POOL_SIZE=2 --concurrency 4 --warmup 10 --n 100`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.260 p95_ms=0.281 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=1.049 p95_ms=1.664 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=5.930 p95_ms=8.988 backend_calls=1.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.282 p95_ms=0.299 backend_calls=11.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.201 p95_ms=0.213 backend_calls=7.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.435 p95_ms=0.456 backend_calls=37.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.290 p95_ms=0.304 backend_calls=16.00 concurrency=4
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=2 acquire=441 waits=219 wait_total_ms=404.349 wait_max_ms=2.099 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=2 acquire=881 waits=439 wait_total_ms=826.186 wait_max_ms=2.256 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=2 acquire=1321 waits=659 wait_total_ms=1311.700 wait_max_ms=2.541 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.986 p95_ms=7.180 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=7.137 p95_ms=7.504 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.751 p95_ms=8.046 backend_calls=19.00 concurrency=4
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=886 waits=234 wait_total_ms=182.339 wait_max_ms=6.681
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1766 waits=458 wait_total_ms=319.790 wait_max_ms=23.399
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=2646 waits=743 wait_total_ms=999.438 wait_max_ms=23.399
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_4e1a6da4 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=3530 waits=985 wait_total_ms=1290.815 wait_max_ms=34.205
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=14.709 p95_ms=16.244 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=14.223 p95_ms=15.419 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=18.067 p95_ms=20.347 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=15.323 p95_ms=16.619 backend_calls=22.00 concurrency=4
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=2 acquire=441 waits=218 wait_total_ms=395.116 wait_max_ms=2.194 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=2 acquire=881 waits=438 wait_total_ms=829.018 wait_max_ms=2.447 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=2 acquire=1321 waits=656 wait_total_ms=1315.579 wait_max_ms=3.123 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=19.030 p95_ms=19.790 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=19.319 p95_ms=20.092 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=20.025 p95_ms=20.613 backend_calls=19.00 concurrency=4
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=886 waits=188 wait_total_ms=177.392 wait_max_ms=5.008
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1766 waits=339 wait_total_ms=296.852 wait_max_ms=28.079
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=2646 waits=584 wait_total_ms=898.065 wait_max_ms=28.079
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_d2f30c6d acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=3530 waits=787 wait_total_ms=1149.744 wait_max_ms=33.074
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=26.621 p95_ms=28.914 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=25.818 p95_ms=28.526 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=29.923 p95_ms=33.878 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=26.892 p95_ms=29.662 backend_calls=22.00 concurrency=4
```

`DSA_PERF_POOL_SIZE=2 --concurrency 8 --warmup 5 --n 50`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=50 p50_ms=0.431 p95_ms=0.468 backend_calls=1.00 concurrency=8
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=50 p50_ms=2.197 p95_ms=3.487 backend_calls=1.00 concurrency=8
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=50 p50_ms=12.144 p95_ms=18.508 backend_calls=1.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=50 p50_ms=0.465 p95_ms=0.497 backend_calls=11.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=50 p50_ms=0.322 p95_ms=0.357 backend_calls=7.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=50 p50_ms=0.799 p95_ms=0.837 backend_calls=37.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=50 p50_ms=0.510 p95_ms=0.539 backend_calls=16.00 concurrency=8
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=2 acquire=441 waits=328 wait_total_ms=1304.828 wait_max_ms=6.669 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=2 acquire=881 waits=658 wait_total_ms=2692.324 wait_max_ms=7.611 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=2 acquire=1321 waits=988 wait_total_ms=4261.812 wait_max_ms=7.666 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=50 p50_ms=16.365 p95_ms=17.537 backend_calls=14.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=50 p50_ms=16.847 p95_ms=18.750 backend_calls=15.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=50 p50_ms=18.164 p95_ms=19.084 backend_calls=19.00 concurrency=8
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=886 waits=296 wait_total_ms=580.529 wait_max_ms=8.938
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1766 waits=570 wait_total_ms=938.166 wait_max_ms=36.515
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=2646 waits=911 wait_total_ms=2596.081 wait_max_ms=36.515
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_40fd2bca acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=3530 waits=1212 wait_total_ms=3312.103 wait_max_ms=36.515
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=50 p50_ms=44.720 p95_ms=48.787 backend_calls=21.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=50 p50_ms=43.237 p95_ms=47.735 backend_calls=13.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=50 p50_ms=50.010 p95_ms=55.237 backend_calls=49.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=50 p50_ms=44.779 p95_ms=50.435 backend_calls=22.00 concurrency=8
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=2 acquire=441 waits=323 wait_total_ms=1102.606 wait_max_ms=7.224 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=2 acquire=881 waits=647 wait_total_ms=2261.821 wait_max_ms=9.769 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=2 acquire=1321 waits=972 wait_total_ms=3676.161 wait_max_ms=9.769 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=50 p50_ms=38.854 p95_ms=42.917 backend_calls=14.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=50 p50_ms=38.966 p95_ms=44.532 backend_calls=15.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=50 p50_ms=40.779 p95_ms=42.487 backend_calls=19.00 concurrency=8
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=886 waits=303 wait_total_ms=848.389 wait_max_ms=11.696
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1766 waits=591 wait_total_ms=1397.137 wait_max_ms=33.608
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=2646 waits=952 wait_total_ms=3640.864 wait_max_ms=33.608
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_ae81b8c1 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=3530 waits=1272 wait_total_ms=4601.986 wait_max_ms=33.608
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=50 p50_ms=66.633 p95_ms=71.449 backend_calls=21.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=50 p50_ms=65.349 p95_ms=69.875 backend_calls=13.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=50 p50_ms=73.197 p95_ms=77.797 backend_calls=49.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=50 p50_ms=67.347 p95_ms=72.463 backend_calls=22.00 concurrency=8
```

`DSA_PERF_POOL_SIZE=2 --concurrency 16 --warmup 5 --n 30`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=30 p50_ms=0.788 p95_ms=0.858 backend_calls=1.00 concurrency=16
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=30 p50_ms=5.433 p95_ms=8.459 backend_calls=1.00 concurrency=16
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=30 p50_ms=33.982 p95_ms=47.424 backend_calls=1.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=30 p50_ms=0.872 p95_ms=0.988 backend_calls=11.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=30 p50_ms=0.564 p95_ms=0.651 backend_calls=7.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=30 p50_ms=1.564 p95_ms=1.664 backend_calls=37.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=30 p50_ms=0.950 p95_ms=1.070 backend_calls=16.00 concurrency=16
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=2 acquire=561 waits=488 wait_total_ms=3957.056 wait_max_ms=13.921 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=2 acquire=1121 waits=978 wait_total_ms=8170.543 wait_max_ms=15.659 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=2 acquire=1681 waits=1468 wait_total_ms=12867.534 wait_max_ms=17.670 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=30 p50_ms=31.911 p95_ms=33.037 backend_calls=14.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=30 p50_ms=33.439 p95_ms=36.961 backend_calls=15.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=30 p50_ms=35.653 p95_ms=40.474 backend_calls=19.00 concurrency=16
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1126 waits=453 wait_total_ms=2263.823 wait_max_ms=20.529
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2246 waits=879 wait_total_ms=3630.710 wait_max_ms=39.303
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3366 waits=1380 wait_total_ms=10207.708 wait_max_ms=43.669
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_bbbd4af7 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4490 waits=1852 wait_total_ms=12855.808 wait_max_ms=43.669
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=30 p50_ms=96.914 p95_ms=101.309 backend_calls=21.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=30 p50_ms=94.169 p95_ms=103.527 backend_calls=13.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=30 p50_ms=115.006 p95_ms=122.189 backend_calls=49.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=30 p50_ms=101.096 p95_ms=105.406 backend_calls=22.00 concurrency=16
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=2 acquire=561 waits=477 wait_total_ms=4205.746 wait_max_ms=23.891 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=2 acquire=1121 waits=958 wait_total_ms=9123.575 wait_max_ms=26.684 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=2 acquire=1681 waits=1442 wait_total_ms=14759.273 wait_max_ms=26.684 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=30 p50_ms=80.371 p95_ms=84.384 backend_calls=14.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=30 p50_ms=81.911 p95_ms=92.233 backend_calls=15.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=30 p50_ms=83.585 p95_ms=94.689 backend_calls=19.00 concurrency=16
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1126 waits=490 wait_total_ms=4604.957 wait_max_ms=33.888
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2246 waits=974 wait_total_ms=7949.182 wait_max_ms=37.649
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3366 waits=1486 wait_total_ms=16609.344 wait_max_ms=50.758
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_77b1e3e1 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4490 waits=1982 wait_total_ms=21236.501 wait_max_ms=50.758
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=30 p50_ms=147.754 p95_ms=155.124 backend_calls=21.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=30 p50_ms=145.565 p95_ms=152.607 backend_calls=13.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=30 p50_ms=167.777 p95_ms=172.583 backend_calls=49.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=30 p50_ms=153.113 p95_ms=159.593 backend_calls=22.00 concurrency=16
```

`DSA_PERF_POOL_SIZE=2 --concurrency 32 --warmup 3 --n 15`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=15 p50_ms=1.458 p95_ms=1.612 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=15 p50_ms=11.426 p95_ms=16.543 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=15 p50_ms=65.887 p95_ms=91.261 backend_calls=1.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=15 p50_ms=1.693 p95_ms=1.837 backend_calls=11.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=15 p50_ms=1.081 p95_ms=1.235 backend_calls=7.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=15 p50_ms=3.201 p95_ms=3.998 backend_calls=37.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=15 p50_ms=1.917 p95_ms=2.466 backend_calls=16.00 concurrency=32
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=2 acquire=577 waits=530 wait_total_ms=8702.540 wait_max_ms=34.758 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=2 acquire=1153 waits=1070 wait_total_ms=17728.016 wait_max_ms=34.758 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=2 acquire=1729 waits=1610 wait_total_ms=27888.511 wait_max_ms=35.019 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=15 p50_ms=62.672 p95_ms=65.827 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=63.634 p95_ms=75.384 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=15 p50_ms=68.818 p95_ms=80.546 backend_calls=19.00 concurrency=32
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1158 waits=502 wait_total_ms=4630.007 wait_max_ms=46.909
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2310 waits=994 wait_total_ms=8365.238 wait_max_ms=48.257
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3462 waits=1551 wait_total_ms=27005.237 wait_max_ms=67.056
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_e1df9b47 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4618 waits=2058 wait_total_ms=32131.782 wait_max_ms=67.056
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=15 p50_ms=211.453 p95_ms=224.478 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=204.038 p95_ms=214.132 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=15 p50_ms=239.698 p95_ms=253.925 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=15 p50_ms=208.104 p95_ms=218.880 backend_calls=22.00 concurrency=32
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=2 acquire=577 waits=528 wait_total_ms=12096.768 wait_max_ms=56.287 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=2 acquire=1153 waits=1057 wait_total_ms=25641.169 wait_max_ms=56.287 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=2 acquire=1729 waits=1592 wait_total_ms=40656.484 wait_max_ms=66.836 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=15 p50_ms=163.904 p95_ms=170.661 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=15 p50_ms=170.254 p95_ms=182.135 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=15 p50_ms=177.870 p95_ms=189.247 backend_calls=19.00 concurrency=32
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1158 waits=507 wait_total_ms=9540.689 wait_max_ms=95.613
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2310 waits=1004 wait_total_ms=16081.057 wait_max_ms=97.379
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3462 waits=1548 wait_total_ms=34328.792 wait_max_ms=97.379
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_c6ad0771 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4618 waits=2062 wait_total_ms=41930.578 wait_max_ms=97.379
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=15 p50_ms=309.189 p95_ms=316.533 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=15 p50_ms=297.674 p95_ms=312.178 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=15 p50_ms=327.025 p95_ms=343.234 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=15 p50_ms=302.076 p95_ms=313.591 backend_calls=22.00 concurrency=32
```

`DSA_PERF_POOL_SIZE=32 --concurrency 1 --warmup 10 --n 100`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.124 p95_ms=0.129 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.175 p95_ms=0.220 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.516 p95_ms=0.701 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.129 p95_ms=0.135 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.101 p95_ms=0.105 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.173 p95_ms=0.179 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.136 p95_ms=0.140 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=2.663 p95_ms=2.789 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=2.731 p95_ms=2.844 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=2.976 p95_ms=3.122 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=446 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=666 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_15a1c23e acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=890 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.281 p95_ms=6.876 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.069 p95_ms=6.684 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.428 p95_ms=8.282 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.413 p95_ms=6.977 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=6.380 p95_ms=6.548 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=6.408 p95_ms=6.611 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=6.614 p95_ms=7.033 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=446 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=666 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_285d6315 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=890 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.981 p95_ms=11.413 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.756 p95_ms=11.073 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=11.091 p95_ms=12.553 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.210 p95_ms=11.652 backend_calls=22.00 concurrency=1
```

`DSA_PERF_POOL_SIZE=32 --concurrency 2 --warmup 10 --n 100`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.162 p95_ms=0.181 backend_calls=1.00 concurrency=2
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.362 p95_ms=0.518 backend_calls=1.00 concurrency=2
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=1.637 p95_ms=2.399 backend_calls=1.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.180 p95_ms=0.185 backend_calls=11.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.141 p95_ms=0.148 backend_calls=7.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.267 p95_ms=0.275 backend_calls=37.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.188 p95_ms=0.196 backend_calls=16.00 concurrency=2
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=3.362 p95_ms=3.485 backend_calls=14.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=3.421 p95_ms=3.559 backend_calls=15.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=3.766 p95_ms=3.948 backend_calls=19.00 concurrency=2
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=446 waits=110 wait_total_ms=46.463 wait_max_ms=2.105
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=886 waits=220 wait_total_ms=80.230 wait_max_ms=2.105
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=1326 waits=330 wait_total_ms=251.415 wait_max_ms=2.105
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_076ed096 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=1770 waits=440 wait_total_ms=353.759 wait_max_ms=25.239
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=9.481 p95_ms=9.833 backend_calls=21.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=9.080 p95_ms=9.609 backend_calls=13.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=11.439 p95_ms=12.546 backend_calls=49.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=10.046 p95_ms=11.107 backend_calls=22.01 concurrency=2
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=661 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=10.036 p95_ms=10.436 backend_calls=14.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=10.057 p95_ms=10.381 backend_calls=15.00 concurrency=2
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=10.440 p95_ms=10.724 backend_calls=19.00 concurrency=2
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=446 waits=110 wait_total_ms=47.414 wait_max_ms=2.080
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=886 waits=219 wait_total_ms=82.734 wait_max_ms=2.080
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=1326 waits=329 wait_total_ms=255.205 wait_max_ms=2.080
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_13c65046 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=1770 waits=439 wait_total_ms=365.186 wait_max_ms=31.149
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=16.157 p95_ms=17.405 backend_calls=21.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=15.784 p95_ms=16.955 backend_calls=13.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=18.552 p95_ms=20.015 backend_calls=49.00 concurrency=2
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=16.893 p95_ms=18.293 backend_calls=22.01 concurrency=2
```

`DSA_PERF_POOL_SIZE=32 --concurrency 4 --warmup 10 --n 100`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.259 p95_ms=0.286 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=1.042 p95_ms=1.705 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=6.261 p95_ms=9.212 backend_calls=1.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.281 p95_ms=0.296 backend_calls=11.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.199 p95_ms=0.222 backend_calls=7.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.445 p95_ms=0.456 backend_calls=37.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.296 p95_ms=0.306 backend_calls=16.00 concurrency=4
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=5.668 p95_ms=6.100 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=5.866 p95_ms=6.328 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=6.786 p95_ms=7.563 backend_calls=19.00 concurrency=4
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=886 waits=234 wait_total_ms=241.005 wait_max_ms=5.343
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1766 waits=458 wait_total_ms=414.297 wait_max_ms=27.949
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=2646 waits=755 wait_total_ms=1229.032 wait_max_ms=27.949
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_81ced8a6 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=3530 waits=1019 wait_total_ms=1599.503 wait_max_ms=29.690
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=19.741 p95_ms=21.971 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=17.479 p95_ms=19.254 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=21.470 p95_ms=23.898 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=18.706 p95_ms=20.483 backend_calls=22.00 concurrency=4
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=18.692 p95_ms=19.381 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=19.531 p95_ms=20.444 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=20.508 p95_ms=21.502 backend_calls=19.00 concurrency=4
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=886 waits=191 wait_total_ms=182.799 wait_max_ms=4.704
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1766 waits=352 wait_total_ms=325.572 wait_max_ms=34.055
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=2646 waits=595 wait_total_ms=974.118 wait_max_ms=34.055
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_9b7e7326 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=3530 waits=802 wait_total_ms=1260.878 wait_max_ms=37.448
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=30.045 p95_ms=31.714 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=28.588 p95_ms=30.233 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=32.354 p95_ms=36.832 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=30.866 p95_ms=32.898 backend_calls=22.00 concurrency=4
```

`DSA_PERF_POOL_SIZE=32 --concurrency 8 --warmup 5 --n 50`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=50 p50_ms=0.431 p95_ms=0.466 backend_calls=1.00 concurrency=8
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=50 p50_ms=2.031 p95_ms=3.214 backend_calls=1.00 concurrency=8
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=50 p50_ms=11.902 p95_ms=17.857 backend_calls=1.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=50 p50_ms=0.454 p95_ms=0.481 backend_calls=11.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=50 p50_ms=0.318 p95_ms=0.350 backend_calls=7.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=50 p50_ms=0.803 p95_ms=0.865 backend_calls=37.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=50 p50_ms=0.495 p95_ms=0.532 backend_calls=16.00 concurrency=8
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=8
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=8
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=8
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=50 p50_ms=14.626 p95_ms=15.812 backend_calls=14.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=50 p50_ms=19.157 p95_ms=22.104 backend_calls=15.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=50 p50_ms=24.682 p95_ms=26.905 backend_calls=19.00 concurrency=8
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=886 waits=292 wait_total_ms=654.026 wait_max_ms=10.811
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=1766 waits=552 wait_total_ms=1018.953 wait_max_ms=35.870
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=2646 waits=875 wait_total_ms=2641.136 wait_max_ms=35.870
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_c10d1acb acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=3530 waits=1168 wait_total_ms=3342.807 wait_max_ms=35.870
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=50 p50_ms=52.822 p95_ms=56.827 backend_calls=21.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=50 p50_ms=49.223 p95_ms=54.812 backend_calls=13.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=50 p50_ms=55.497 p95_ms=60.871 backend_calls=49.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=50 p50_ms=50.956 p95_ms=55.784 backend_calls=22.00 concurrency=8
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=441 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=8
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=881 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=8
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1321 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=8
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=50 p50_ms=42.967 p95_ms=45.053 backend_calls=14.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=50 p50_ms=45.514 p95_ms=49.615 backend_calls=15.00 concurrency=8
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=50 p50_ms=47.530 p95_ms=50.306 backend_calls=19.00 concurrency=8
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=886 waits=295 wait_total_ms=842.315 wait_max_ms=12.696
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=1766 waits=574 wait_total_ms=1403.645 wait_max_ms=28.497
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=2646 waits=936 wait_total_ms=3817.695 wait_max_ms=28.497
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_64e1d8c9 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=3530 waits=1255 wait_total_ms=4877.274 wait_max_ms=38.513
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=50 p50_ms=73.352 p95_ms=79.224 backend_calls=21.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=50 p50_ms=71.401 p95_ms=75.079 backend_calls=13.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=50 p50_ms=79.574 p95_ms=86.295 backend_calls=49.00 concurrency=8
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=50 p50_ms=74.380 p95_ms=78.370 backend_calls=22.00 concurrency=8
```

`DSA_PERF_POOL_SIZE=32 --concurrency 16 --warmup 5 --n 30`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=30 p50_ms=0.778 p95_ms=0.856 backend_calls=1.00 concurrency=16
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=30 p50_ms=5.017 p95_ms=8.003 backend_calls=1.00 concurrency=16
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=30 p50_ms=31.288 p95_ms=43.892 backend_calls=1.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=30 p50_ms=0.846 p95_ms=0.914 backend_calls=11.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=30 p50_ms=0.564 p95_ms=0.643 backend_calls=7.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=30 p50_ms=1.586 p95_ms=1.668 backend_calls=37.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=30 p50_ms=0.946 p95_ms=1.062 backend_calls=16.00 concurrency=16
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=561 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=16
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=1121 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=16
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1681 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=16
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=30 p50_ms=31.994 p95_ms=34.941 backend_calls=14.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=30 p50_ms=41.829 p95_ms=51.375 backend_calls=15.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=30 p50_ms=47.953 p95_ms=54.027 backend_calls=19.00 concurrency=16
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1126 waits=453 wait_total_ms=2657.509 wait_max_ms=30.280
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2246 waits=869 wait_total_ms=4067.106 wait_max_ms=30.280
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3366 waits=1377 wait_total_ms=11463.526 wait_max_ms=57.259
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_f354d926 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4490 waits=1846 wait_total_ms=14384.939 wait_max_ms=57.259
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=30 p50_ms=110.195 p95_ms=117.272 backend_calls=21.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=30 p50_ms=106.312 p95_ms=111.460 backend_calls=13.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=30 p50_ms=123.973 p95_ms=130.570 backend_calls=49.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=30 p50_ms=110.024 p95_ms=113.850 backend_calls=22.00 concurrency=16
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=561 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=11
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=1121 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=15
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1681 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=16
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=30 p50_ms=90.533 p95_ms=98.707 backend_calls=14.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=30 p50_ms=94.148 p95_ms=101.720 backend_calls=15.00 concurrency=16
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=30 p50_ms=97.767 p95_ms=106.903 backend_calls=19.00 concurrency=16
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1126 waits=482 wait_total_ms=4469.187 wait_max_ms=28.869
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2246 waits=946 wait_total_ms=7680.943 wait_max_ms=38.315
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3366 waits=1454 wait_total_ms=16159.126 wait_max_ms=61.599
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_6fdbeb3c acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4490 waits=1953 wait_total_ms=21132.321 wait_max_ms=61.599
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=30 p50_ms=159.117 p95_ms=166.446 backend_calls=21.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=30 p50_ms=153.914 p95_ms=164.530 backend_calls=13.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=30 p50_ms=170.118 p95_ms=179.478 backend_calls=49.00 concurrency=16
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=30 p50_ms=160.350 p95_ms=170.043 backend_calls=22.00 concurrency=16
```

`DSA_PERF_POOL_SIZE=32 --concurrency 32 --warmup 3 --n 15`:

```
PERFRUN host=<OS/arch> python=3.11.15 commit=7a7f817-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=15 p50_ms=1.472 p95_ms=1.615 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=15 p50_ms=10.660 p95_ms=15.791 backend_calls=1.00 concurrency=32
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=15 p50_ms=62.260 p95_ms=89.480 backend_calls=1.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=15 p50_ms=1.602 p95_ms=1.881 backend_calls=11.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=15 p50_ms=1.058 p95_ms=1.193 backend_calls=7.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=15 p50_ms=2.972 p95_ms=3.113 backend_calls=37.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=15 p50_ms=1.757 p95_ms=1.972 backend_calls=16.00 concurrency=32
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=31
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=15 p50_ms=67.423 p95_ms=72.303 backend_calls=14.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=89.739 p95_ms=105.875 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=15 p50_ms=95.871 p95_ms=110.163 backend_calls=19.00 concurrency=32
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_<id> acquire=1158 waits=499 wait_total_ms=5110.682 wait_max_ms=39.095
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_<id> acquire=2310 waits=964 wait_total_ms=8341.168 wait_max_ms=47.822
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_<id> acquire=3462 waits=1511 wait_total_ms=23486.159 wait_max_ms=62.266
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_63b4ceee acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_<id> acquire=4618 waits=2022 wait_total_ms=29147.984 wait_max_ms=63.369
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=15 p50_ms=219.874 p95_ms=234.192 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=15 p50_ms=214.689 p95_ms=235.242 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=15 p50_ms=246.232 p95_ms=266.374 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=15 p50_ms=220.866 p95_ms=227.984 backend_calls=22.00 concurrency=32
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_<id>/runtime size=32 acquire=577 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=24
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_<id>/runtime size=32 acquire=1153 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=31
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/developer size=32 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_<id>/runtime size=32 acquire=1729 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=31
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=15 p50_ms=185.491 p95_ms=196.485 backend_calls=14.01 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=15 p50_ms=186.680 p95_ms=201.472 backend_calls=15.00 concurrency=32
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=15 p50_ms=196.779 p95_ms=207.280 backend_calls=19.01 concurrency=32
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_<id> acquire=1158 waits=513 wait_total_ms=8244.236 wait_max_ms=92.842
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_<id> acquire=2310 waits=1009 wait_total_ms=14199.016 wait_max_ms=94.708
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_<id> acquire=3462 waits=1550 wait_total_ms=32164.588 wait_max_ms=122.060
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_c3abadcc acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_<id> acquire=4618 waits=2061 wait_total_ms=40742.979 wait_max_ms=122.060
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=15 p50_ms=317.518 p95_ms=333.485 backend_calls=21.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=15 p50_ms=304.874 p95_ms=327.755 backend_calls=13.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=15 p50_ms=335.748 p95_ms=352.207 backend_calls=49.00 concurrency=32
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=15 p50_ms=315.068 p95_ms=323.754 backend_calls=22.00 concurrency=32
```

## 3. 事実 (§2 の数字だけから。判断語を含まない)

1. **r2db の pool 寸法は p50 をほとんど変えない。** `query` の p50 は size 2 と size 32 で K=1: 2.672 / 2.663、K=4: 6.986 / 5.668、K=8: 16.365 / 14.626、K=16: 31.911 / 31.994、K=32: 62.672 / 67.423 (http)。socket も同じ形 (K=32: 163.904 / 185.491)。
2. **size 32 では r2db の pool 待ちは全 K で 0** (runtime pool `waits=0` / acquire 331〜1729)。size 2 では K ≥ 4 で待ちが出る (K=4: 659/1321、K=32: 1610/1729、wait_max 2.5 → 35.0 ms) が、その K の p50 は size 32 と同程度である。
3. **K に対して p50 がほぼ線形に伸びる** (r2db http: K=1 2.67 → K=32 62.7 = 23 倍、K あたり約 1.9 ms; socket: 6.26 → 163.9 = 26 倍、K あたり約 5.1 ms; MitateDB http: 6.30 → 211.5 = 34 倍、K あたり約 6.6 ms; socket: 9.87 → 309.2 = 31 倍、K あたり約 9.7 ms)。1 process あたりの処理は K に依らず「1 要求ずつ p50(K=1) 相当の時間」で進んでいる。
4. **MitateDB の cell lock は K=2 から待つ** (http: K=2 で 440/1770、K=4 で 985/3530、K=32 で 2058/4618 = acquire の 45%、wait_max 28 → 67 ms)。size の設定は MitateDB に効かない (データ面はプールでなく持続接続 2 本 + cell の `RLock`)。
5. **socket 転送は http (asgi-inprocess) の約 1.5〜2.6 倍**の p50 で、K に対する伸び方は同じ。
6. 12 run すべてで `perf_baseline.py` は exit 0、`PERF` 22 行・`POOL` 22 行 (in-process plug は `POOL` 行なし)。K ≥ 8 は n を下げているので分散は大きい (§1 の表)。

## 4. 判断 (監督、2026-09-23)

- **(1) R-78 の問い「プールの寸法と待ち」への答: プールは律速ではない。** r2db では production 相当の size 32 で待ちが 0 なのに p50 は size 2 と同じ形で K に比例して伸びる (§3 の 1〜3)。size 2 の待ち (max 35 ms) も p50 (62.7 ms) の一部に過ぎない。**寸法 (`role_pool_size` = concurrency) は変えない。未プールの経路の見直しも要らない** (計測経路にプールを経ない DB アクセスは無い)。role の `CONNECTION LIMIT` (F-16 の床) との釣り合いは、size 32 で待ち 0 = 上限まで使い切っていないことを示す。
- **(2) 1 process 内の直列化が支配的である。** K に比例する p50 (§3 の 3) は、要求が process 内でほぼ 1 本ずつ処理されていることを意味する。本計測は「uvicorn の threadpool」「GIL」「PostgreSQL 往復」のどれが主体かを切り分けない (同 process・同 GIL で client と server が動く asgi-inprocess と、uvicorn を同 process の thread で動かす socket の両方で同じ形)。切り分けは別の計測が要る → **台帳 R-101 (起票)**。R-84 (async psycopg) の再検討条件「threadpool の混雑が tail latency を決めている」は、本計測では**確定していない** (R-84 行に本実測を追記、着手条件は不変)。
- **(3) MitateDB は application ごとの `RLock` が実測で直列化点である** (§3 の 4: K ≥ 4 で acquire の 30〜45% が待ち、wait_max 67 ms)。フェーズ10 の設計事実 (application あたり実並行度 1) を数字で裏づけた。解くには「application ごとの接続プール + 細粒度の lock」の設計変更が要る → **台帳 R-102 (起票、設計レビューを着手条件に)**。
- **(4) 本メモの計測器 (`POOL` 行、`DSA_PERF_POOL_SIZE`) は残す。** R-79〜R-82 の前後計測は K=1/K=3 に加えて本 sweep と同じ K の並びで取れる。
- **R-78 は本判断をもって閉じる** (WO §6.2 の最終判定、台帳 R-78 行)。
