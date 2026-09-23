# 設計メモ — 1 要求あたりの DB 往復の実測 (R-80)

## 0. 版数・位置づけ

- **v0.1 (2026-09-23)。骨だけである。** 基点は local main `c589785`、作業指示書は `docs/work-orders/WORK_ORDER_R80_ROUNDTRIP_MEASUREMENT_V1.md` (以下「WO」)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-80** 行 (`RM`:605) で、横断条件は `RM`:389 (**P-8**) と `RM`:545 (**R-20**) である。
- §2 (実測) と §3 (事実) と §4 (判断) は **WO §3 = WP-2 で監督が埋める。** WP-1 (実装担当) はこの骨を動かさず、**判断を先に書かない。**
- 先行する実測の記録は `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` (R-79) に在る。本メモはその続きであり、同じ計測器 (`tools/perf_baseline.py`) の新しい行を使う。

## 1. 目的と方法

**目的**: 「1 要求が DB と何回やり取りしているのか」を、成分 (文・transaction・session) に分けて数字で出せる形にする (WO §1.1)。R-79 で接続ごとの文の数 (`execute_count`) は数えられるようになったが、**要求あたりの往復** — 文に加えて transaction の `BEGIN` / `COMMIT` と新規 session の確立 — はまだ集計されていない。**pipeline 化・キャッシュ・接続の使い回しは計測の後であり、別の変更セットで行う** (WO §1.1 の (a)、`RM`:389 の P-8、`RM`:545 の R-20)。

**機構上の事実** (一次資料で確認済み。逐語と `file:line` は WO §1.3 の (1)〜(5) に在る):

- **F1**: 監査の書き込み (SI-14) は両 peer とも**本体の処理とは別の接続**で走る。r2db は sink 自身の `_RolePool` から、MitateDB は呼びごとの新しい接続から。**別接続の文は pipeline にまとめられない** — pipeline は 1 つの接続の機能だからである。**同期の書き込みは destructive のときだけ**なので、**本メモの計測の op (select / insert) では 1 回も走らない** (WO §1.3 の (10b))。
- **F2**: r2db の 1 要求は 1 本の runtime 接続の上で、liveness ping (transaction の外、autocommit) → `BEGIN` → `SET LOCAL` ×2 → catalog 読み 2 形 → (client 側の判定) → data 文 → `COMMIT` と進む。
- **F3**: MitateDB の 1 要求は cell の `RLock` で直列化され、catalog 読みは**呼びごとに独立した transaction** (developer 接続) で行われる。data 文は runtime 接続の 1 transaction である。
- **F4**: psycopg 3.3.5 の pipeline 中の `execute()` は queue するだけで、**未取得の結果に触れた瞬間に暗黙の sync (往復) が起きる**。エラーの後は次の sync まで `PipelineAborted` である。`BEGIN` / `COMMIT` / `SAVEPOINT` / `RELEASE` は `Cursor.execute` を通らないので `execute_count` には入らない (§1 の「計測の限界」)。
- **F5**: PostgreSQL 16 の `pg_stat_database` は `xact_commit` / `xact_rollback` / `sessions` を持ち、DB ごとに数えられる。**統計の反映には遅れが在る** — 持続接続の 100 commit の burst は直後には +2 しか見えず、**+10.03 秒後**に +101 になった (WO §1.3 の (5) の実測)。

**道具と引数**: `tools/perf_baseline.py --warmup 10 --n 100 --concurrency <K> --roundtrip`。WP-1 で `ROUNDTRIP` 行と `--roundtrip` フラグが追加された (WO §1.2 の D-1、WO §6.1 の起草時の裁定 1)。**`--roundtrip` を付けたときだけ行が出る** — `pg_stat_database` の値の確定待ちが 1 op につき数秒かかるので、通常の run の所要時間を変えないためである。行は 2 種類で、接続ごとの文の数 (`conn=` の行) と DB ごとの transaction / session の数 (`db=` の行) である。**往復の総数を 1 つの数字にまとめない** — autocommit の文は `BEGIN` / `COMMIT` を伴わないので、成分を単純加算できないからである (同 D-1)。

**K の並び**: **K=1** (`--warmup 10 --n 100`) である (WO §1.2 の D-3)。`(warmup + n) * K` は 110 で、credential ごと毎分 600 件の rate 上限の内に収まる。

**r2db の pool の寸法は既定 (2) のみ**である。R-78 の `DSA_PERF_POOL_SIZE` による上書きは本件では使わない。

**probe 自身の分は差分から除く**: `prepared_stats()` の probe は素の `psycopg.Cursor` で 1 文を `prepare=False` で読み (counting cursor ではないので `execute_count` に入らない)、直後に `conn.commit()` する。この `commit()` は probe した接続 1 本につきその接続の DB の `xact_commit` を 1 増やすので、**`db=` の行の `xacts` からは、その op で probe した接続の本数 (probe が実際に走った接続だけ) を引く** (WO §1.2 の D-1、`tools/PERF_BASELINE_README.md`)。

**統計の反映には遅れが在る**: `pg_stat_database` の値は backend が共有メモリへ出した分だけであり、出す頻度には下限の間隔が在る — **idle のままの接続では約 10 秒**である (WO §1.3 の (5) の実測)。そこで `db=` の行は、**probe の後に**、`pg_stat_clear_snapshot()` の後に **最短 12 秒待ってから 1 秒ごとに読み、3 回連続で値が動かなければ確定、上限 30 秒**として取る (WO §1.2 の D-1、WO §6.1 の設計レビュー 1 の H-1)。**上限に達しても値が動き続けたときは、その時点の値に `stale=1` を付けて出す** (確定したときは `stale=0`)。`stale=1` の行は確定値として扱わない。**差の基準は各 op の `_measure_op` の直前 (pre) の読みであり、probe も pre / post の 2 回行う** (同 M-3・M-6)。

**計測の限界** (WO §6.1 の起草時の裁定 2・5):

- **`BEGIN` / `COMMIT` / `ROLLBACK` / `SAVEPOINT` / `RELEASE` は `Cursor.execute` を通らないので `execute_count` に入らない。** `BEGIN` / `COMMIT` / `ROLLBACK` は `db=` の行の `xacts` に transaction として現れるが、**`SAVEPOINT` / `RELEASE` はどちらにも現れない** — savepoint を使う文 (r2db の制約 registry 読み・idempotency の読みと予約) の往復は、本計測のどの成分にも数えられない。該当箇所は WO §1.3 の依存表で **【SP】** の印を付けてある。**`src` に counter は足さない** (WO §1.4 の (2))。
- **`cross_entity` op が作る 2 つ目の application は、その application DB が `db=app` の行に入らない** (WO §1.3 の (8))。
- **安定 ≠ 確定である**: 「値が動かないこと」は「backend が flush 済み」の証拠にならない。**flush 前の平坦区間は 20 秒を超えることがある** (WO §1.3 の (5b) の run 1 — 真値 +101 に対し +5 が 20 秒間不動だった)。**probe された接続の pending は probe の直後に flush される**が (同 run 3)、**probe されない接続 (r2db の監査 sink の自前 pool 等) の pending は idle flush 待ちである**。上の最短待ちと `stale` はこの性質への手当てであり、**`stale=1` の行はその op の確定値ではない。**
- **`db=app` の `sessions` は 0 が期待値である**: 監査の同期書き込みが走らず (上の F1)、app DB の接続は r2db が pool、MitateDB が cell の持続 2 本だからである。**MitateDB の認証 (credential store) は呼びごとに接続を開いて閉じるので、`sessions` は `db=platform` 側に出る** (WO §1.3 の (10b))。

**合成環境である旨**: 以下の実測はすべて開発機のローカルの使い捨て PostgreSQL クラスタ (16.14) に対するものであり、ホスト名・実 DSN・作業機の絶対パスは記録しない (WO §1.1 の (d)、`OPERATING_CONDITIONS.md` §1.9)。`PERFRUN` の `host=` は `<OS/arch>` の形式である。

## 2. 実測 (WP-2 = 監督が埋める)

### 2.1 K=1 (`--warmup 10 --n 100 --concurrency 1 --roundtrip`)

実行は WP-1 の完了ゲート (`4018 passed`) の後、本 worktree の道具で。r2db の pool の寸法は既定 2。`ROUNDTRIP` 行 60 本、`stale=1` は 0 本。`requests=110` = warmup 10 + n 100。`PERF` の絶対値は `--roundtrip` の待ちを含まない (待ちは op の外) が、性能の比較には §3.3 の 7 のとおり既定 run を使う。負荷は load average 3〜4 (別チャットの作業が並走)。

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=c589785-dirty date=2026-09-24
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.127 p95_ms=0.141 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.188 p95_ms=0.245 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.646 p95_ms=0.869 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.132 p95_ms=0.140 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.105 p95_ms=0.115 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.188 p95_ms=0.205 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.140 p95_ms=0.148 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_4a24a44a396d/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_4a24a44a396d/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_4a24a44a396d/developer@47393 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_4a24a44a396d/runtime@47395 executes=668 executemany=0 prepared=6 prepared_execs=633 share=0.948
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=query requests=110 conn=perfbase_4a24a44a396d/developer@47393 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=query requests=110 conn=perfbase_4a24a44a396d/runtime@47395 stmts=660 stmts_per_req=6.00
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=query requests=110 db=app xacts=220 xacts_per_req=2.00 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=query requests=110 db=platform xacts=880 xacts_per_req=8.00 sessions=0 sessions_per_req=0.00 stale=0
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_4a24a44a396d/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_4a24a44a396d/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_4a24a44a396d/developer@47393 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_4a24a44a396d/runtime@47395 executes=1438 executemany=0 prepared=8 prepared_execs=1395 share=0.970
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=mutate requests=110 conn=perfbase_4a24a44a396d/developer@47393 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=mutate requests=110 conn=perfbase_4a24a44a396d/runtime@47395 stmts=770 stmts_per_req=7.00
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=mutate requests=110 db=app xacts=220 xacts_per_req=2.00 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=mutate requests=110 db=platform xacts=880 xacts_per_req=8.00 sessions=0 sessions_per_req=0.00 stale=0
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_4a24a44a396d/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_4a24a44a396d/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_4a24a44a396d/developer@47393 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_4a24a44a396d/runtime@47395 executes=2648 executemany=0 prepared=8 prepared_execs=2605 share=0.984
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=batch requests=110 conn=perfbase_4a24a44a396d/developer@47393 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=batch requests=110 conn=perfbase_4a24a44a396d/runtime@47395 stmts=1210 stmts_per_req=11.00
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=batch requests=110 db=app xacts=224 xacts_per_req=2.04 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=r2db-api plug=r2db-api-http op=batch requests=110 db=platform xacts=880 xacts_per_req=8.00 sessions=0 sessions_per_req=0.00 stale=0
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.476 p95_ms=1.594 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.507 p95_ms=1.589 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=1.681 p95_ms=1.923 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_b98fc67e0623 acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@47911 executes=334 executemany=0 prepared=3 prepared_execs=305 share=0.913
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@47912 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=query requests=110 conn=runtime@47911 stmts=330 stmts_per_req=3.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=query requests=110 conn=developer@47912 stmts=1760 stmts_per_req=16.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=query requests=110 db=app xacts=550 xacts_per_req=5.00 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=query requests=110 db=platform xacts=442 xacts_per_req=4.02 sessions=220 sessions_per_req=2.00 stale=0
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_b98fc67e0623 acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@47911 executes=664 executemany=0 prepared=4 prepared_execs=631 share=0.950
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@47912 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=mutate requests=110 conn=runtime@47911 stmts=330 stmts_per_req=3.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=mutate requests=110 conn=developer@47912 stmts=880 stmts_per_req=8.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=mutate requests=110 db=app xacts=332 xacts_per_req=3.02 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=mutate requests=110 db=platform xacts=440 xacts_per_req=4.00 sessions=220 sessions_per_req=2.00 stale=0
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_b98fc67e0623 acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@47911 executes=1434 executemany=0 prepared=6 prepared_execs=1399 share=0.976
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@47912 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=batch requests=110 conn=runtime@47911 stmts=770 stmts_per_req=7.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=batch requests=110 conn=developer@47912 stmts=4400 stmts_per_req=40.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=batch requests=110 db=app xacts=1212 xacts_per_req=11.02 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=batch requests=110 db=platform xacts=440 xacts_per_req=4.00 sessions=220 sessions_per_req=2.00 stale=0
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_5ce703a7 acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_b98fc67e0623 acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@49116 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@49117 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@47911 executes=1874 executemany=0 prepared=9 prepared_execs=1828 share=0.975
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@47912 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=cross_entity requests=110 conn=runtime@49116 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=cross_entity requests=110 conn=developer@49117 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=cross_entity requests=110 conn=runtime@47911 stmts=440 stmts_per_req=4.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=cross_entity requests=110 conn=developer@47912 stmts=1760 stmts_per_req=16.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=cross_entity requests=110 db=app xacts=551 xacts_per_req=5.01 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-http op=cross_entity requests=110 db=platform xacts=442 xacts_per_req=4.02 sessions=220 sessions_per_req=2.00 stale=0
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=7.612 p95_ms=8.306 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.852 p95_ms=7.302 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=8.411 p95_ms=10.015 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=7.305 p95_ms=7.899 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_ee96c82e2810/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_ee96c82e2810/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_ee96c82e2810/developer@49546 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_ee96c82e2810/runtime@49547 executes=668 executemany=0 prepared=6 prepared_execs=633 share=0.948
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=query requests=110 conn=perfbase_ee96c82e2810/developer@49546 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=query requests=110 conn=perfbase_ee96c82e2810/runtime@49547 stmts=660 stmts_per_req=6.00
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=query requests=110 db=app xacts=220 xacts_per_req=2.00 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=query requests=110 db=platform xacts=880 xacts_per_req=8.00 sessions=0 sessions_per_req=0.00 stale=0
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_ee96c82e2810/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_ee96c82e2810/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_ee96c82e2810/developer@49546 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_ee96c82e2810/runtime@49547 executes=1438 executemany=0 prepared=8 prepared_execs=1395 share=0.970
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=mutate requests=110 conn=perfbase_ee96c82e2810/developer@49546 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=mutate requests=110 conn=perfbase_ee96c82e2810/runtime@49547 stmts=770 stmts_per_req=7.00
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=mutate requests=110 db=app xacts=220 xacts_per_req=2.00 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=mutate requests=110 db=platform xacts=880 xacts_per_req=8.00 sessions=0 sessions_per_req=0.00 stale=0
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_ee96c82e2810/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_ee96c82e2810/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_ee96c82e2810/developer@49546 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_ee96c82e2810/runtime@49547 executes=2648 executemany=0 prepared=8 prepared_execs=2605 share=0.984
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=batch requests=110 conn=perfbase_ee96c82e2810/developer@49546 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=batch requests=110 conn=perfbase_ee96c82e2810/runtime@49547 stmts=1210 stmts_per_req=11.00
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=batch requests=110 db=app xacts=220 xacts_per_req=2.00 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=r2db-api plug=r2db-api-socket op=batch requests=110 db=platform xacts=880 xacts_per_req=8.00 sessions=0 sessions_per_req=0.00 stale=0
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=5.418 p95_ms=5.767 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=5.655 p95_ms=5.869 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=5.689 p95_ms=6.054 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_b757301b57c3 acquire=227 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@50099 executes=334 executemany=0 prepared=3 prepared_execs=303 share=0.907
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@50100 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=query requests=110 conn=runtime@50099 stmts=330 stmts_per_req=3.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=query requests=110 conn=developer@50100 stmts=1760 stmts_per_req=16.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=query requests=110 db=app xacts=550 xacts_per_req=5.00 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=query requests=110 db=platform xacts=442 xacts_per_req=4.02 sessions=220 sessions_per_req=2.00 stale=0
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_b757301b57c3 acquire=449 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@50099 executes=664 executemany=0 prepared=4 prepared_execs=629 share=0.947
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@50100 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=mutate requests=110 conn=runtime@50099 stmts=330 stmts_per_req=3.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=mutate requests=110 conn=developer@50100 stmts=880 stmts_per_req=8.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=mutate requests=110 db=app xacts=332 xacts_per_req=3.02 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=mutate requests=110 db=platform xacts=440 xacts_per_req=4.00 sessions=220 sessions_per_req=2.00 stale=0
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_b757301b57c3 acquire=671 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@50099 executes=1434 executemany=0 prepared=6 prepared_execs=1397 share=0.974
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@50100 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=batch requests=110 conn=runtime@50099 stmts=770 stmts_per_req=7.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=batch requests=110 conn=developer@50100 stmts=4400 stmts_per_req=40.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=batch requests=110 db=app xacts=1216 xacts_per_req=11.05 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=batch requests=110 db=platform xacts=440 xacts_per_req=4.00 sessions=220 sessions_per_req=2.00 stale=0
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_fb14923d acquire=1 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_b757301b57c3 acquire=897 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@51325 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@51326 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@50099 executes=1874 executemany=0 prepared=9 prepared_execs=1828 share=0.975
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@50100 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity requests=110 conn=runtime@51325 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity requests=110 conn=developer@51326 stmts=0 stmts_per_req=0.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity requests=110 conn=runtime@50099 stmts=440 stmts_per_req=4.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity requests=110 conn=developer@50100 stmts=1760 stmts_per_req=16.00
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity requests=110 db=app xacts=551 xacts_per_req=5.01 sessions=0 sessions_per_req=0.00 stale=0
ROUNDTRIP peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity requests=110 db=platform xacts=440 xacts_per_req=4.00 sessions=220 sessions_per_req=2.00 stale=0
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=12.847 p95_ms=14.443 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=11.644 p95_ms=13.439 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=13.486 p95_ms=15.399 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=11.619 p95_ms=13.291 backend_calls=22.00 concurrency=1
```

## 3. 事実 (§2 の数字だけから。判断語を含まない。WP-2 = 監督が埋める)

- (i) **op・接続ごとの文/要求** (`conn=` 行。http と socket で同一): r2db runtime = query **6.00**、mutate **7.00**、batch **11.00**、developer は 0 (query / transact で使われない)。MitateDB runtime = query **3.00**、mutate 3.00、batch 7.00、cross_entity 4.00; MitateDB developer = query **16.00**、mutate 8.00、batch **40.00**、cross_entity 16.00。cross_entity で現れる 2 つ目の cell の接続は 0 (probe は在るが要求は流れない)。
- (ii) **DB ごとの transaction/要求と session/要求** (`db=` 行): r2db `db=app` = **2.00** (query / mutate)、2.04 (batch) = ping の autocommit 文 1 + data の transaction 1; r2db **`db=platform` = 8.00** (全 op で同じ、`sessions` 0 = pool 経由)。MitateDB `db=app` = query **5.00**、mutate 3.02、batch 11.02、cross_entity 5.01 (catalog 読みの独立 transaction が主体); MitateDB `db=platform` = **4.00〜4.02、`sessions` 2.00** (要求ごとに新規 session 2 本)。`db=app` の `sessions` は両 peer で 0 (期待どおり)。監査の同期書き込みは走らない (§1.3 の (10b))。**MitateDB の `sessions=2.00/要求` は harness の plug が認証 store に pool を渡さない配線 (`pool=None`、R-78 §1.3 の (5)) によるもので、production の composition root は `BoundedConnectionPool` を渡す — production の値ではない。** r2db の platform 8 tx/要求は pool 経由なので session は増えないが transaction は 8 回ある。
- (iii) **依存表に照らした「独立」の連続** (pipeline で節約できる往復の上限): r2db query = ping (autocommit、別 transaction) の後、`BEGIN` → `SET LOCAL` ×2 → catalog SELECT ×2 の **5 往復が独立** (上限 4)、続く data SELECT は catalog に依存、`COMMIT` は最後。r2db mutate / batch = `BEGIN` → `SET LOCAL` ×2 → catalog ×2 → `SAVEPOINT`【SP】→ 制約 registry の SELECT → `RELEASE` の **8 往復が独立** (上限 7、うち savepoint 系 2 は `execute_count` に入らない)、以後の data 文は依存。MitateDB query = developer 接続の catalog 読み **5 transaction (各 `BEGIN` + `SET LOCAL` ×2 + SELECT + `COMMIT` = 5 往復、計 25 往復) は互いに独立** (transaction の切り方を変えずに pipeline にまとめると上限 24 だが、R-82 が読みそのものを消す); runtime の `BEGIN` + `SET LOCAL` ×2 の 3 往復が独立、data SELECT は catalog に依存。MitateDB mutate = developer 2 transaction (10 往復、独立)、runtime 3 往復 + INSERT。実測の文数 (16 / 8 / 40) は依存表の並びと一致し、食い違いは無い。
- (iv) **R-82 / R-81 が消す文の数**: R-82 (schema のプロセス内キャッシュ) が消すのは r2db の catalog SELECT 2 文/要求 (query / mutate / batch 共通) と MitateDB developer の catalog 読み **16 文 (5 transaction) /query 要求**・8 文/mutate・40 文/batch。R-81 (idempotency) は本計測では **0** (harness が idempotency key を送らない。§1.3 の (10))。`SET LOCAL` ×2 (両 peer、runtime の transaction ごと) は R-79 の申し送り (B) の 1 文化で 1 文減る。
- (v) **peer の差**: app DB の transaction/要求は r2db 2 対 MitateDB 5 (query)、文/要求は r2db 6 対 MitateDB 19 (runtime 3 + developer 16)。platform DB は r2db 8 tx (session 0) 対 MitateDB 4 tx + session 2 (harness の配線)。http と socket の数字は両 peer とも同一 (往復は転送に依らない)。

## 4. 判断 (監督、2026-09-24)

- **pipeline 化の候補と期待値**: (iii) のとおり、r2db は要求の先頭 (`BEGIN` + `SET LOCAL` ×2 + catalog ×2、mutate ではさらに制約 registry の savepoint 3 往復) が独立で、pipeline 1 回にまとめると **1 要求あたり最大 4 (query) 〜 7 (mutate / batch) 往復**が減る。ただしそのうち catalog ×2 は R-82 が読みごと消す対象で、R-82 の後に残る独立区間は `BEGIN` + `SET LOCAL` ×2 (+ savepoint 系) の **2〜5 往復**である。MitateDB は catalog 読み 5 transaction (25 往復/query) が最大の成分だが、これも R-82 が消す対象であり、pipeline でまとめる ((U-1) の (C)) と R-82 の設計 (キャッシュ + DB 上の版数の読み) と二重投資になる。**したがって pipeline 化 (WP-2) は R-82 の後に、R-82 が残した独立区間に対して行う方が無駄が無い。** 候補 (B) (`SET LOCAL` 2 文 → `set_config` 1 文) は R-82 と独立で、両 peer の runtime transaction ごとに 1 往復減る (r2db 8 → 7、MitateDB 3+ → 2+)。
- **着手順 (依頼者裁定に上げる。両論)**: 台帳は R-80 → R-81 → R-82 の順を固定している。(甲) 順のまま: R-80 WP-2 で pipeline を先に入れる — 効果は r2db 最大 4〜7 往復、MitateDB 最大 24 往復 (catalog 5 transaction をまとめる) だが、後者は R-82 で消える文に対する投資で、R-82 の後に作り直しになる。(乙) **R-82 を先に**: catalog 読みを消してから (r2db −2 文、MitateDB −16〜−40 文・−5〜−10 transaction/要求) R-80 WP-2 で残る独立区間 (`BEGIN` + `SET LOCAL` ×2 + savepoint 系) を pipeline / (B) で詰める。監督の推奨は (乙)。R-81 は本計測の経路に無く (harness が key を送らない)、順序の判断材料が無い — R-81 の着手時に harness の mutate に idempotency key を送る op を足すのが先である。
- **計測が示した本件の範囲外の事実 (台帳へ)**: r2db は **platform DB に要求ごと 8 transaction** (pool 経由、session 0)、MitateDB は platform DB に 4 transaction。これは認証 (credential の照合)・rate / concurrency の bookkeeping 等の platform 側の往復で、R-83 (API キー検証結果のキャッシュ) の判断材料になる。MitateDB の `sessions=2.00/要求` は harness の配線 (`pool=None`) によるもので production の値ではない — ただし **conformance / perf の harness が production と違う接続の持ち方で動いている**という事実は、計測の代表性の問題として記録する。
- **R-80 の状態**: WP-1 (計測器) と WP-2 (計測) は完了。**pipeline 化 (修正) は着手順の裁定待ちで、本メモの結論は R-82 先行の推奨である。** 台帳 R-80 行は open のまま追記する。
