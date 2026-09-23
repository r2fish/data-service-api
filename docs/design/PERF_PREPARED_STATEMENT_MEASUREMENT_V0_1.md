# 設計メモ — prepared statement が効いているかの実測 (R-79)

## 0. 版数・位置づけ

- **v0.3 (2026-09-23)。** WP-3 の後の r2db の再計測を §2.3 と §3 (ix) に、結果を §4 に足した。
- **v0.2 (2026-09-23)。** WP-2 で §2〜§4 を埋めた (v0.1 は骨だけ)。 基点は `docs/work-orders/WORK_ORDER_R79_PREPARED_STATEMENT_MEASUREMENT_V1.md` (以下「WO」)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-79 行。
- §2 (実測) と §3 (事実) と §4 (判断) は **WO §3 = WP-2 で監督が埋める。** WP-1 (実装担当) はこの骨を動かさず、**判断を先に書かない。**

## 1. 目的と方法

**目的**: 「両 peer の実運用経路の文が、実際に server-side prepared で走っているのか」を、`pg_prepared_statements` の数字で区別できる形にする (WO §1.1)。psycopg 3.3.5 は同じ `(query bytes, param types)` を同じ接続で `prepare_threshold` (既定 5) 回実行すると自動で prepare し、`prepared_max` (既定 100) を超えると LRU で捨てるが、両 peer の `src` にはこの 2 つの指定が 0 件であり、効いているかを誰も計測していない。**効かない経路を直す判断は本メモの §4 より後であり、計測の後に別の変更セット (WO §3.4 の WP-3) で行う** (WO §1.1 (a)、`RM`:308 の P-8、`RM`:451 の R-20)。

**機構上の事実** (一次資料で確認済み。逐語と `file:line` は WO §1.3 の (1)〜(5) に在る):

- **F1**: 両 peer の `_set_timeouts` は timeout 値を `sql.Literal` で SQL 本文に焼き込む。**可変鍵になるのは `_timeout_ms(deadline)` の戻り値を渡す箇所だけ**で (r2db は 4 箇所すべて、MitateDB は 10 箇所)、この経路では `SET LOCAL statement_timeout` / `SET LOCAL lock_timeout` の 2 文が毎回新しい鍵になり、閾値に届かないまま `_counts` (上限 100) に積もって実文の計数 entry を押し出す。**MitateDB の catalog 読み 8 本の `SET LOCAL` は構築時定数 `_catalog_timeout_ms` を渡すので固定鍵 2 個であり、閾値に届けば prepared になり得る** (WO §1.3 の (14)、WO §6.1 の起草時の裁定 1)。
- **F2**: `Connection.rollback()` (接続が IDLE でないとき) と `Transaction` の rollback (savepoint を含む) は prepared を全消去する。commit は消さない。**r2db は checkout ごとにこれを踏む** — `_RolePool._liveness_check` (`postgres.py`:462-489、rollback 行は :482) が貸し出しのたびに `SELECT 1` → `rollback()` を走らせるので、毎回 `DEALLOCATE ALL` が起きる (WO §6.1 の設計レビュー 1 の H-2)。
- **F3**: `cur.execute(..., prepare=False)` でも鍵は `_counts` に足される。
- **F4**: `sql.Identifier` の識別子は query bytes に焼き込まれるので、鍵は (接続, 文の形, 識別子) ごとである。
- **F5**: `pg_prepared_statements` は **session ごと**なので接続ごとに読む必要があり、`generic_plans + custom_plans` がその prepared statement の実行回数である。

**道具と引数**: `tools/perf_baseline.py --warmup 10 --n 100 --concurrency <K> --prepared-detail`。WP-1 で接続ごとの文の計数 (WO §1.2 の D-1。両 peer の新 module `src/<pkg>/psycopg_counting.py` の `CountingCursor` / `CountingConnection`、**接続を要求をまたいで使い回す 4 箇所だけ**に適用)、読み取り専用の probe (同 D-2)、`PREPARED` / `PREPSTMT` 行と `--prepared-detail` (同 D-3) が追加された。行の列名は `executes=` / `executemany=`、接続の属性名は `execute_count` / `executemany_count`、dict の一覧鍵は `prepared_statements` である (WO §6.1 の設計レビュー 1 の M-7)。`PREPARED` 行の `conn=` は `conn.info.backend_pid` を末尾に持つので (r2db `<application_id>/<role>@<pid>`、MitateDB `runtime@<pid>` / `developer@<pid>`)、**再接続は label の変化として現れる**。実行は本 worktree の道具を worktree の cwd から呼ぶ。

**K の並び**: **K=1 と K=4** の 2 つである (WO §1.2 の D-4)。どちらも `--warmup 10 --n 100` で、`(warmup + n) * K` は 110 と 440 であり、credential ごと毎分 600 件の rate 上限の内に収まる。

**r2db の pool の寸法は既定 (2) のみ**である (WO §1.2 の D-4)。R-78 の `DSA_PERF_POOL_SIZE` による上書きは本件では使わない。

**`share` は下界であり、構造的な上限も持つ**: `PREPARED` 行の `share` は「その接続に**現存する** prepared statement の実行数 (Σ `generic_plans` + `custom_plans`) / その接続の `execute` 総数」であり、F2 で消去された分の実行数は数えられない。したがって「実際に prepared で走った割合」の下界であって、等しい値ではない (WO §1.2 の D-3)。**さらに分母には prepared になり得ない文 (`SET LOCAL`・DDL・`prepare=False` の読み) も入るので、`share` は 1.000 に届き得ない** — **判定は `share` の大小ではなく `PREPSTMT` の一覧 (どの文が prepared に在るか) で行う** (WO §6.1 の設計レビュー 1 の M-8)。

**R-79 以降、MitateDB の `POOL lock=` の `acquire` は先行する op の probe 1 回分を含む**: probe は `ApplicationCell.prepared_stats()` 経由で cell lock を 1 回取るからである (WO §6.1 の設計レビュー 1 の H-3、`tools/PERF_BASELINE_README.md`)。r2db 側の `POOL role=` の `acquire` / `waits` / `in_use_peak` は probe では動かない。

**counter は接続の生涯累積である**: op ごとに reset しない。r2db は pool の接続が op をまたいで残るからである (WO §1.2 の D-3)。

**probe は計測の後に走り、自身は prepared にならない**: probe は素の `psycopg.Cursor` で `prepare=False` で読み、直後に `commit()` する (`rollback()` は F2 で cache を消すので使わない)。`prepare=False` でも鍵は `_counts` に 1 つ入るが (F3)、prepared にはならないので view には現れない (WO §1.2 の D-2)。

**合成環境である旨**: 以下の実測はすべて開発機のローカル PostgreSQL クラスタ (16.14) に対するものであり、ホスト名・実 DSN・作業機の絶対パスは記録しない (WO §1.1 (d)、`OPERATING_CONDITIONS.md` §1.9)。`PERFRUN` の `host=` は `<OS/arch>` の形式である。

## 2. 実測 (WP-2 = 監督が埋める)

### 2.1 K=1 (`--warmup 10 --n 100 --concurrency 1 --prepared-detail`)

r2db の pool の寸法は既定 2 (`DSA_PERF_POOL_SIZE` 未設定)。`POOL` 行は R-78 の行で、同じ op の `PREPARED` 行がその後に続く。負荷: 計測中は別チャットの作業が同じ開発機で走っており (load average 5〜7)、`PERF` の絶対値は §1.3 の基準値より一様に大きい — `PREPARED` / `PREPSTMT` は比率と件数なので負荷の影響を受けない。

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=ce27b52-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.125 p95_ms=0.134 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.191 p95_ms=0.244 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.643 p95_ms=0.954 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.138 p95_ms=0.161 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.105 p95_ms=0.111 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.189 p95_ms=0.207 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.142 p95_ms=0.148 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_0c6dd14a4391/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_0c6dd14a4391/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_0c6dd14a4391/developer@51956 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_0c6dd14a4391/runtime@51958 executes=668 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_0c6dd14a4391/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_0c6dd14a4391/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_0c6dd14a4391/developer@51956 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_0c6dd14a4391/runtime@51958 executes=1438 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_0c6dd14a4391/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_0c6dd14a4391/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_0c6dd14a4391/developer@51956 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_0c6dd14a4391/runtime@51958 executes=2648 executemany=0 prepared=0 prepared_execs=0 share=0.000
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=3.473 p95_ms=3.694 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=3.542 p95_ms=3.910 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=3.833 p95_ms=4.179 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_6e47dffa80b0 acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@51980 executes=334 executemany=0 prepared=3 prepared_execs=305 share=0.913
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@51980 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_af0437269487" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@51980 name=_pg3_1 generic=100 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@51980 name=_pg3_2 generic=100 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@51981 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@51981 name=_pg3_0 generic=439 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@51981 name=_pg3_1 generic=439 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@51981 name=_pg3_2 generic=432 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@51981 name=_pg3_3 generic=212 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@51981 name=_pg3_4 generic=211 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_6e47dffa80b0 acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@51980 executes=664 executemany=0 prepared=4 prepared_execs=631 share=0.950
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@51980 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_af0437269487" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@51980 name=_pg3_1 generic=210 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@51980 name=_pg3_2 generic=210 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@51980 name=_pg3_3 generic=101 custom=5 stmt=INSERT INTO "perfq_af0437269487" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@51981 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@51981 name=_pg3_0 generic=659 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@51981 name=_pg3_1 generic=659 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@51981 name=_pg3_2 generic=542 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@51981 name=_pg3_3 generic=322 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@51981 name=_pg3_4 generic=321 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@51981 name=_pg3_5 generic=102 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_6e47dffa80b0 acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@51980 executes=1434 executemany=0 prepared=6 prepared_execs=1395 share=0.973
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@51980 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_af0437269487" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@51980 name=_pg3_1 generic=210 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@51980 name=_pg3_2 generic=210 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@51980 name=_pg3_3 generic=651 custom=5 stmt=INSERT INTO "perfq_af0437269487" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@51980 name=_pg3_4 generic=107 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@51980 name=_pg3_5 generic=107 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@51981 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@51981 name=_pg3_0 generic=1759 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@51981 name=_pg3_1 generic=1759 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@51981 name=_pg3_2 generic=1092 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@51981 name=_pg3_3 generic=872 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@51981 name=_pg3_4 generic=871 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@51981 name=_pg3_5 generic=652 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_7e4c6061 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_6e47dffa80b0 acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@52690 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@52691 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 executes=1874 executemany=0 prepared=7 prepared_execs=1820 share=0.971
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_af0437269487" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 name=_pg3_1 generic=314 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 name=_pg3_2 generic=314 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 name=_pg3_3 generic=761 custom=5 stmt=INSERT INTO "perfq_af0437269487" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 name=_pg3_4 generic=108 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 name=_pg3_5 generic=108 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@51980 name=_pg3_6 generic=100 custom=5 stmt=INSERT INTO "perfx_a3514bc04d31" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@51981 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@51981 name=_pg3_6 generic=435 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@51981 name=_pg3_7 generic=435 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@51981 name=_pg3_8 generic=210 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@51981 name=_pg3_9 generic=210 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@51981 name=_pg3_10 generic=210 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@51981 name=_pg3_11 generic=210 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=8.371 p95_ms=8.623 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=8.028 p95_ms=8.420 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=9.564 p95_ms=9.919 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=8.451 p95_ms=8.846 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_72ab5feae224/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_72ab5feae224/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_72ab5feae224/developer@52953 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_72ab5feae224/runtime@52954 executes=668 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_72ab5feae224/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_72ab5feae224/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_72ab5feae224/developer@52953 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_72ab5feae224/runtime@52954 executes=1438 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_72ab5feae224/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_72ab5feae224/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_72ab5feae224/developer@52953 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_72ab5feae224/runtime@52954 executes=2648 executemany=0 prepared=0 prepared_execs=0 share=0.000
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=7.987 p95_ms=8.574 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=8.310 p95_ms=8.920 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=8.480 p95_ms=9.117 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_590fb32d0bc0 acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@52994 executes=334 executemany=0 prepared=3 prepared_execs=305 share=0.913
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@52994 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_150809e54c85" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@52994 name=_pg3_1 generic=100 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@52994 name=_pg3_2 generic=100 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@52995 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@52995 name=_pg3_0 generic=439 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@52995 name=_pg3_1 generic=439 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@52995 name=_pg3_2 generic=432 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@52995 name=_pg3_3 generic=212 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@52995 name=_pg3_4 generic=211 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_590fb32d0bc0 acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@52994 executes=664 executemany=0 prepared=4 prepared_execs=629 share=0.947
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@52994 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_150809e54c85" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@52994 name=_pg3_1 generic=209 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@52994 name=_pg3_2 generic=209 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@52994 name=_pg3_3 generic=101 custom=5 stmt=INSERT INTO "perfq_150809e54c85" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@52995 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@52995 name=_pg3_0 generic=659 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@52995 name=_pg3_1 generic=659 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@52995 name=_pg3_2 generic=542 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@52995 name=_pg3_3 generic=322 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@52995 name=_pg3_4 generic=321 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@52995 name=_pg3_5 generic=102 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_590fb32d0bc0 acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 executes=1434 executemany=0 prepared=8 prepared_execs=1393 share=0.971
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_150809e54c85" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_1 generic=209 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_2 generic=209 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_3 generic=651 custom=5 stmt=INSERT INTO "perfq_150809e54c85" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_4 generic=106 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_5 generic=106 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_6 generic=1 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@52994 name=_pg3_7 generic=1 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@52995 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@52995 name=_pg3_0 generic=1759 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@52995 name=_pg3_1 generic=1759 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@52995 name=_pg3_2 generic=1092 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@52995 name=_pg3_3 generic=872 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@52995 name=_pg3_4 generic=871 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@52995 name=_pg3_5 generic=652 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_2906a3cf acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_590fb32d0bc0 acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@53716 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@53717 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 executes=1874 executemany=0 prepared=9 prepared_execs=1820 share=0.971
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_150809e54c85" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_1 generic=311 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_2 generic=311 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_3 generic=761 custom=5 stmt=INSERT INTO "perfq_150809e54c85" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_4 generic=109 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_5 generic=109 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_6 generic=2 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_7 generic=2 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@52994 name=_pg3_8 generic=100 custom=5 stmt=INSERT INTO "perfx_7d437abacc17" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@52995 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@52995 name=_pg3_6 generic=435 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@52995 name=_pg3_7 generic=435 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@52995 name=_pg3_8 generic=210 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@52995 name=_pg3_9 generic=210 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@52995 name=_pg3_10 generic=210 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@52995 name=_pg3_11 generic=210 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=13.039 p95_ms=14.913 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=13.011 p95_ms=14.905 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=14.205 p95_ms=16.351 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=13.121 p95_ms=15.068 backend_calls=22.00 concurrency=1
```

### 2.2 K=4 (`--warmup 10 --n 100 --concurrency 4 --prepared-detail`)

r2db の pool の寸法は既定 2 (`DSA_PERF_POOL_SIZE` 未設定)。`POOL` 行は R-78 の行で、同じ op の `PREPARED` 行がその後に続く。負荷: 計測中は別チャットの作業が同じ開発機で走っており (load average 5〜7)、`PERF` の絶対値は §1.3 の基準値より一様に大きい — `PREPARED` / `PREPSTMT` は比率と件数なので負荷の影響を受けない。

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=ce27b52-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.336 p95_ms=0.357 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=1.448 p95_ms=2.300 backend_calls=1.00 concurrency=4
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=8.235 p95_ms=12.697 backend_calls=1.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.356 p95_ms=0.393 backend_calls=11.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.248 p95_ms=0.274 backend_calls=7.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.586 p95_ms=0.614 backend_calls=37.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.381 p95_ms=0.406 backend_calls=16.00 concurrency=4
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_37c678da3f08/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_37c678da3f08/runtime size=2 acquire=441 waits=219 wait_total_ms=618.285 wait_max_ms=3.430 in_use_peak=2
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_37c678da3f08/developer@54119 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_37c678da3f08/runtime@54125 executes=1315 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_37c678da3f08/runtime@54121 executes=1334 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_37c678da3f08/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_37c678da3f08/runtime size=2 acquire=881 waits=439 wait_total_ms=1307.296 wait_max_ms=10.849 in_use_peak=2
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_37c678da3f08/developer@54119 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_37c678da3f08/runtime@54121 executes=2874 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_37c678da3f08/runtime@54125 executes=2855 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_37c678da3f08/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_37c678da3f08/runtime size=2 acquire=1321 waits=659 wait_total_ms=2071.160 wait_max_ms=10.849 in_use_peak=2
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_37c678da3f08/developer@54119 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_37c678da3f08/runtime@54121 executes=5294 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_37c678da3f08/runtime@54125 executes=5275 executemany=0 prepared=0 prepared_execs=0 share=0.000
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=11.066 p95_ms=12.008 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=11.559 p95_ms=12.603 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=12.372 p95_ms=13.418 backend_calls=19.00 concurrency=4
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_0686864f2f3c acquire=886 waits=245 wait_total_ms=375.725 wait_max_ms=7.097
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 executes=1324 executemany=0 prepared=11 prepared_execs=1261 share=0.952
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_6bf803808412" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_1 generic=90 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_2 generic=90 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_3 generic=103 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_4 generic=103 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_5 generic=146 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_6 generic=146 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_7 generic=63 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_8 generic=63 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_9 generic=11 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@54160 name=_pg3_10 generic=11 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@54161 executes=7068 executemany=0 prepared=5 prepared_execs=7028 share=0.994
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@54161 name=_pg3_0 generic=1759 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@54161 name=_pg3_1 generic=1759 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@54161 name=_pg3_2 generic=1752 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@54161 name=_pg3_3 generic=872 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@54161 name=_pg3_4 generic=871 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_0686864f2f3c acquire=1767 waits=472 wait_total_ms=632.207 wait_max_ms=37.560
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 executes=2644 executemany=0 prepared=12 prepared_execs=2575 share=0.974
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_6bf803808412" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_1 generic=297 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_2 generic=297 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_3 generic=154 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_4 generic=154 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_5 generic=325 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_6 generic=325 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_7 generic=65 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_8 generic=65 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_9 generic=11 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_10 generic=11 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@54160 name=_pg3_11 generic=431 custom=5 stmt=INSERT INTO "perfq_6bf803808412" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@54161 executes=10588 executemany=0 prepared=6 prepared_execs=10545 share=0.996
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@54161 name=_pg3_0 generic=2639 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@54161 name=_pg3_1 generic=2639 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@54161 name=_pg3_2 generic=2192 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@54161 name=_pg3_3 generic=1312 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@54161 name=_pg3_4 generic=1311 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@54161 name=_pg3_5 generic=432 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_0686864f2f3c acquire=2648 waits=768 wait_total_ms=1764.354 wait_max_ms=37.560
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 executes=5724 executemany=0 prepared=22 prepared_execs=5609 share=0.980
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_6bf803808412" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_1 generic=297 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_2 generic=297 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_3 generic=246 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_4 generic=246 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_5 generic=325 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_6 generic=325 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_7 generic=157 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_8 generic=157 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_9 generic=76 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_10 generic=76 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_11 generic=2631 custom=5 stmt=INSERT INTO "perfq_6bf803808412" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_12 generic=45 custom=0 stmt=SET LOCAL statement_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_13 generic=45 custom=0 stmt=SET LOCAL lock_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_14 generic=39 custom=0 stmt=SET LOCAL statement_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_15 generic=39 custom=0 stmt=SET LOCAL lock_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_16 generic=46 custom=0 stmt=SET LOCAL statement_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_17 generic=46 custom=0 stmt=SET LOCAL lock_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_18 generic=11 custom=0 stmt=SET LOCAL statement_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_19 generic=11 custom=0 stmt=SET LOCAL lock_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_20 generic=27 custom=0 stmt=SET LOCAL statement_timeout = '4991ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@54160 name=_pg3_21 generic=27 custom=0 stmt=SET LOCAL lock_timeout = '4991ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@54161 executes=28188 executemany=0 prepared=6 prepared_execs=28145 share=0.998
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@54161 name=_pg3_0 generic=7039 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@54161 name=_pg3_1 generic=7039 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@54161 name=_pg3_2 generic=4392 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@54161 name=_pg3_3 generic=3512 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@54161 name=_pg3_4 generic=3511 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@54161 name=_pg3_5 generic=2632 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_7a200861 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_0686864f2f3c acquire=3533 waits=1023 wait_total_ms=2242.413 wait_max_ms=37.990
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@56934 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@56935 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 executes=7484 executemany=0 prepared=23 prepared_execs=7360 share=0.983
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_6bf803808412" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_1 generic=331 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_2 generic=331 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_3 generic=365 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_4 generic=365 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_5 generic=507 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_6 generic=507 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_7 generic=240 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_8 generic=240 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_9 generic=90 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_10 generic=90 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_11 generic=3071 custom=5 stmt=INSERT INTO "perfq_6bf803808412" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_12 generic=45 custom=0 stmt=SET LOCAL statement_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_13 generic=45 custom=0 stmt=SET LOCAL lock_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_14 generic=44 custom=0 stmt=SET LOCAL statement_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_15 generic=44 custom=0 stmt=SET LOCAL lock_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_16 generic=46 custom=0 stmt=SET LOCAL statement_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_17 generic=46 custom=0 stmt=SET LOCAL lock_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_18 generic=11 custom=0 stmt=SET LOCAL statement_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_19 generic=11 custom=0 stmt=SET LOCAL lock_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_20 generic=28 custom=0 stmt=SET LOCAL statement_timeout = '4991ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_21 generic=28 custom=0 stmt=SET LOCAL lock_timeout = '4991ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@54160 name=_pg3_22 generic=430 custom=5 stmt=INSERT INTO "perfx_9c31ea89a563" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@54161 executes=35248 executemany=0 prepared=6 prepared_execs=7010 share=0.199
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@54161 name=_pg3_6 generic=1755 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@54161 name=_pg3_7 generic=1755 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@54161 name=_pg3_8 generic=870 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@54161 name=_pg3_9 generic=870 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@54161 name=_pg3_10 generic=870 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@54161 name=_pg3_11 generic=870 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=27.697 p95_ms=31.956 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=26.262 p95_ms=30.190 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=32.421 p95_ms=35.195 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=27.662 p95_ms=32.016 backend_calls=22.00 concurrency=4
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_073394286df7/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_073394286df7/runtime size=2 acquire=441 waits=219 wait_total_ms=553.528 wait_max_ms=3.370 in_use_peak=2
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_073394286df7/developer@57885 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_073394286df7/runtime@57886 executes=1334 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_073394286df7/runtime@57890 executes=1315 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_073394286df7/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_073394286df7/runtime size=2 acquire=881 waits=439 wait_total_ms=1194.055 wait_max_ms=4.031 in_use_peak=2
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_073394286df7/developer@57885 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_073394286df7/runtime@57890 executes=2855 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_073394286df7/runtime@57886 executes=2874 executemany=0 prepared=0 prepared_execs=0 share=0.000
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_073394286df7/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_073394286df7/runtime size=2 acquire=1321 waits=659 wait_total_ms=1948.299 wait_max_ms=4.753 in_use_peak=2
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_073394286df7/developer@57885 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_073394286df7/runtime@57890 executes=5275 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_073394286df7/runtime@57886 executes=5294 executemany=0 prepared=0 prepared_execs=0 share=0.000
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=27.932 p95_ms=30.671 backend_calls=14.00 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=31.046 p95_ms=33.275 backend_calls=15.01 concurrency=4
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=32.367 p95_ms=34.787 backend_calls=19.00 concurrency=4
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_3699aefe9828 acquire=886 waits=204 wait_total_ms=344.685 wait_max_ms=6.280
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 executes=1324 executemany=0 prepared=13 prepared_execs=1245 share=0.940
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_973a386fe765" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_1 generic=152 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_2 generic=152 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_3 generic=78 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_4 generic=78 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_5 generic=59 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_6 generic=59 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_7 generic=76 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_8 generic=76 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_9 generic=34 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_10 generic=34 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_11 generic=6 custom=0 stmt=SET LOCAL statement_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@57977 name=_pg3_12 generic=6 custom=0 stmt=SET LOCAL lock_timeout = '4994ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@57978 executes=7068 executemany=0 prepared=5 prepared_execs=7028 share=0.994
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@57978 name=_pg3_0 generic=1759 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@57978 name=_pg3_1 generic=1759 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@57978 name=_pg3_2 generic=1752 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@57978 name=_pg3_3 generic=872 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@57978 name=_pg3_4 generic=871 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_3699aefe9828 acquire=1767 waits=401 wait_total_ms=613.510 wait_max_ms=47.157
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 executes=2644 executemany=0 prepared=14 prepared_execs=2559 share=0.968
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_973a386fe765" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_1 generic=267 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_2 generic=267 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_3 generic=165 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_4 generic=165 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_5 generic=82 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_6 generic=82 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_7 generic=283 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_8 generic=283 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_9 generic=40 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_10 generic=40 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_11 generic=7 custom=0 stmt=SET LOCAL statement_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_12 generic=7 custom=0 stmt=SET LOCAL lock_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@57977 name=_pg3_13 generic=431 custom=5 stmt=INSERT INTO "perfq_973a386fe765" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@57978 executes=10588 executemany=0 prepared=6 prepared_execs=10545 share=0.996
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@57978 name=_pg3_0 generic=2639 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@57978 name=_pg3_1 generic=2639 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@57978 name=_pg3_2 generic=2192 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@57978 name=_pg3_3 generic=1312 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@57978 name=_pg3_4 generic=1311 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@57978 name=_pg3_5 generic=432 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_3699aefe9828 acquire=2648 waits=682 wait_total_ms=1829.679 wait_max_ms=47.157
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 executes=5724 executemany=0 prepared=26 prepared_execs=5565 share=0.972
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_973a386fe765" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_1 generic=276 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_2 generic=276 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_3 generic=246 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_4 generic=246 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_5 generic=161 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_6 generic=161 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_7 generic=283 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_8 generic=283 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_9 generic=93 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_10 generic=93 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_11 generic=50 custom=0 stmt=SET LOCAL statement_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_12 generic=50 custom=0 stmt=SET LOCAL lock_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_13 generic=2631 custom=5 stmt=INSERT INTO "perfq_973a386fe765" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_14 generic=37 custom=0 stmt=SET LOCAL statement_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_15 generic=37 custom=0 stmt=SET LOCAL lock_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_16 generic=30 custom=0 stmt=SET LOCAL statement_timeout = '4991ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_17 generic=30 custom=0 stmt=SET LOCAL lock_timeout = '4991ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_18 generic=18 custom=0 stmt=SET LOCAL statement_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_19 generic=18 custom=0 stmt=SET LOCAL lock_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_20 generic=38 custom=0 stmt=SET LOCAL statement_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_21 generic=38 custom=0 stmt=SET LOCAL lock_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_22 generic=9 custom=0 stmt=SET LOCAL statement_timeout = '4989ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_23 generic=9 custom=0 stmt=SET LOCAL lock_timeout = '4989ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_24 generic=6 custom=0 stmt=SET LOCAL statement_timeout = '4988ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@57977 name=_pg3_25 generic=6 custom=0 stmt=SET LOCAL lock_timeout = '4988ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@57978 executes=28188 executemany=0 prepared=6 prepared_execs=28145 share=0.998
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@57978 name=_pg3_0 generic=7039 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@57978 name=_pg3_1 generic=7039 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@57978 name=_pg3_2 generic=4392 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@57978 name=_pg3_3 generic=3512 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@57978 name=_pg3_4 generic=3511 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@57978 name=_pg3_5 generic=2632 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_a00f04eb acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_3699aefe9828 acquire=3533 waits=895 wait_total_ms=2247.064 wait_max_ms=47.157
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@60788 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@60789 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 executes=7484 executemany=0 prepared=27 prepared_execs=7316 share=0.978
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_0 generic=430 custom=5 stmt=SELECT "label" FROM "perfq_973a386fe765" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_1 generic=457 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_2 generic=457 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_3 generic=332 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_4 generic=332 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_5 generic=229 custom=0 stmt=SET LOCAL statement_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_6 generic=229 custom=0 stmt=SET LOCAL lock_timeout = '4996ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_7 generic=339 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_8 generic=339 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_9 generic=129 custom=0 stmt=SET LOCAL statement_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_10 generic=129 custom=0 stmt=SET LOCAL lock_timeout = '4995ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_11 generic=56 custom=0 stmt=SET LOCAL statement_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_12 generic=56 custom=0 stmt=SET LOCAL lock_timeout = '4994ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_13 generic=3071 custom=5 stmt=INSERT INTO "perfq_973a386fe765" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_14 generic=39 custom=0 stmt=SET LOCAL statement_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_15 generic=39 custom=0 stmt=SET LOCAL lock_timeout = '4993ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_16 generic=30 custom=0 stmt=SET LOCAL statement_timeout = '4991ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_17 generic=30 custom=0 stmt=SET LOCAL lock_timeout = '4991ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_18 generic=18 custom=0 stmt=SET LOCAL statement_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_19 generic=18 custom=0 stmt=SET LOCAL lock_timeout = '4990ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_20 generic=40 custom=0 stmt=SET LOCAL statement_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_21 generic=40 custom=0 stmt=SET LOCAL lock_timeout = '4992ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_22 generic=9 custom=0 stmt=SET LOCAL statement_timeout = '4989ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_23 generic=9 custom=0 stmt=SET LOCAL lock_timeout = '4989ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_24 generic=7 custom=0 stmt=SET LOCAL statement_timeout = '4988ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_25 generic=7 custom=0 stmt=SET LOCAL lock_timeout = '4988ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@57977 name=_pg3_26 generic=430 custom=5 stmt=INSERT INTO "perfx_be8c4f016c08" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@57978 executes=35248 executemany=0 prepared=6 prepared_execs=7010 share=0.199
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@57978 name=_pg3_6 generic=1755 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@57978 name=_pg3_7 generic=1755 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@57978 name=_pg3_8 generic=870 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@57978 name=_pg3_9 generic=870 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@57978 name=_pg3_10 generic=870 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@57978 name=_pg3_11 generic=870 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=44.872 p95_ms=52.327 backend_calls=21.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=41.538 p95_ms=48.544 backend_calls=13.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=48.712 p95_ms=73.160 backend_calls=49.00 concurrency=4
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=41.640 p95_ms=47.306 backend_calls=22.00 concurrency=4
```

### 2.3 WP-3 の後の K=1 (`--warmup 10 --n 100 --concurrency 1 --prepared-detail`、r2db の liveness ping を transaction の外に出した木)

WO §3.4 (WP-3) の統合直前に、完了ゲート (`4018 passed`) の後で取った。r2db の pool の寸法は既定 2。負荷は §2.1 と同程度 (load average 4 前後)。MitateDB-api は WP-3 で触っていないので、その行は §2.1 との再現性の参照値である。

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=fc891cb-dirty date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.129 p95_ms=0.146 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.197 p95_ms=0.243 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.691 p95_ms=1.021 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.141 p95_ms=0.166 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.111 p95_ms=0.137 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.197 p95_ms=0.219 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.140 p95_ms=0.152 backend_calls=16.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_15aa2bc6f308/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=query role=perfbase_15aa2bc6f308/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/developer@73238 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/runtime@73240 executes=668 executemany=0 prepared=6 prepared_execs=633 share=0.948
PREPSTMT peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_0 generic=106 custom=0 stmt=SELECT 1
PREPSTMT peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_1 generic=101 custom=5 stmt=SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name FR
PREPSTMT peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_2 generic=101 custom=5 stmt=SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, array_
PREPSTMT peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_3 generic=105 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_4 generic=105 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-http op=query conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_5 generic=100 custom=5 stmt=SELECT "label", "_r2db_revision"::text FROM "perfq_f2c5b62f4eaa" WHERE "label" =
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_15aa2bc6f308/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=mutate role=perfbase_15aa2bc6f308/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/developer@73238 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 executes=1438 executemany=0 prepared=8 prepared_execs=1395 share=0.970
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_0 generic=216 custom=0 stmt=SELECT 1
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_1 generic=211 custom=5 stmt=SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name FR
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_2 generic=211 custom=5 stmt=SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, array_
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_3 generic=215 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_4 generic=215 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_5 generic=100 custom=5 stmt=SELECT "label", "_r2db_revision"::text FROM "perfq_f2c5b62f4eaa" WHERE "label" =
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_6 generic=106 custom=0 stmt=SELECT entity_name, field_name, nullable, enum_values FROM public."_r2db_field_c
PREPSTMT peer=r2db-api plug=r2db-api-http op=mutate conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_7 generic=101 custom=5 stmt=INSERT INTO "perfq_f2c5b62f4eaa" ("label") VALUES ($1) RETURNING "id"
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_15aa2bc6f308/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-http op=batch role=perfbase_15aa2bc6f308/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/developer@73238 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 executes=2648 executemany=0 prepared=8 prepared_execs=2605 share=0.984
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_0 generic=326 custom=0 stmt=SELECT 1
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_1 generic=321 custom=5 stmt=SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name FR
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_2 generic=321 custom=5 stmt=SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, array_
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_3 generic=325 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_4 generic=325 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_5 generic=100 custom=5 stmt=SELECT "label", "_r2db_revision"::text FROM "perfq_f2c5b62f4eaa" WHERE "label" =
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_6 generic=216 custom=0 stmt=SELECT entity_name, field_name, nullable, enum_values FROM public."_r2db_field_c
PREPSTMT peer=r2db-api plug=r2db-api-http op=batch conn=perfbase_15aa2bc6f308/runtime@73240 name=_pg3_7 generic=651 custom=5 stmt=INSERT INTO "perfq_f2c5b62f4eaa" ("label") VALUES ($1) RETURNING "id"
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=1.861 p95_ms=2.179 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=1.942 p95_ms=2.221 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=2.002 p95_ms=2.311 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-http op=query lock=perfbase_381e70be7c60 acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@73262 executes=334 executemany=0 prepared=3 prepared_execs=303 share=0.907
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@73262 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_dd087037f910" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@73262 name=_pg3_1 generic=99 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=runtime@73262 name=_pg3_2 generic=99 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@73263 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@73263 name=_pg3_0 generic=439 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@73263 name=_pg3_1 generic=439 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@73263 name=_pg3_2 generic=432 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@73263 name=_pg3_3 generic=212 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=query conn=developer@73263 name=_pg3_4 generic=211 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
POOL peer=MitateDB-api plug=MitateDB-api-http op=mutate lock=perfbase_381e70be7c60 acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@73262 executes=664 executemany=0 prepared=4 prepared_execs=629 share=0.947
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@73262 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_dd087037f910" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@73262 name=_pg3_1 generic=209 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@73262 name=_pg3_2 generic=209 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=runtime@73262 name=_pg3_3 generic=101 custom=5 stmt=INSERT INTO "perfq_dd087037f910" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@73263 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@73263 name=_pg3_0 generic=659 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@73263 name=_pg3_1 generic=659 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@73263 name=_pg3_2 generic=542 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@73263 name=_pg3_3 generic=322 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@73263 name=_pg3_4 generic=321 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=mutate conn=developer@73263 name=_pg3_5 generic=102 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-http op=batch lock=perfbase_381e70be7c60 acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 executes=1434 executemany=0 prepared=8 prepared_execs=1393 share=0.971
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_dd087037f910" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_1 generic=209 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_2 generic=209 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_3 generic=651 custom=5 stmt=INSERT INTO "perfq_dd087037f910" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_4 generic=103 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_5 generic=103 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_6 generic=4 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=runtime@73262 name=_pg3_7 generic=4 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@73263 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@73263 name=_pg3_0 generic=1759 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@73263 name=_pg3_1 generic=1759 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@73263 name=_pg3_2 generic=1092 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@73263 name=_pg3_3 generic=872 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@73263 name=_pg3_4 generic=871 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=batch conn=developer@73263 name=_pg3_5 generic=652 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=cap_probe_1_f3550c2e acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-http op=cross_entity lock=perfbase_381e70be7c60 acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73968 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73969 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 executes=1874 executemany=0 prepared=9 prepared_execs=1822 share=0.972
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_dd087037f910" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_1 generic=312 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_2 generic=312 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_3 generic=761 custom=5 stmt=INSERT INTO "perfq_dd087037f910" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_4 generic=105 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_5 generic=105 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_6 generic=6 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_7 generic=6 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=runtime@73262 name=_pg3_8 generic=100 custom=5 stmt=INSERT INTO "perfx_cbafebd66155" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73263 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73263 name=_pg3_6 generic=435 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73263 name=_pg3_7 generic=435 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73263 name=_pg3_8 generic=210 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73263 name=_pg3_9 generic=210 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73263 name=_pg3_10 generic=210 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-http op=cross_entity conn=developer@73263 name=_pg3_11 generic=210 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=8.106 p95_ms=8.546 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=7.775 p95_ms=8.121 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=9.394 p95_ms=9.779 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=8.239 p95_ms=8.713 backend_calls=22.00 concurrency=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_0d349f14f247/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=query role=perfbase_0d349f14f247/runtime size=2 acquire=111 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/developer@74235 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/runtime@74237 executes=668 executemany=0 prepared=6 prepared_execs=633 share=0.948
PREPSTMT peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_0 generic=106 custom=0 stmt=SELECT 1
PREPSTMT peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_1 generic=101 custom=5 stmt=SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name FR
PREPSTMT peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_2 generic=101 custom=5 stmt=SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, array_
PREPSTMT peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_3 generic=105 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_4 generic=105 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-socket op=query conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_5 generic=100 custom=5 stmt=SELECT "label", "_r2db_revision"::text FROM "perfq_49a5fd56c1dc" WHERE "label" =
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_0d349f14f247/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=mutate role=perfbase_0d349f14f247/runtime size=2 acquire=221 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/developer@74235 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 executes=1438 executemany=0 prepared=8 prepared_execs=1395 share=0.970
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_0 generic=216 custom=0 stmt=SELECT 1
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_1 generic=211 custom=5 stmt=SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name FR
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_2 generic=211 custom=5 stmt=SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, array_
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_3 generic=215 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_4 generic=215 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_5 generic=100 custom=5 stmt=SELECT "label", "_r2db_revision"::text FROM "perfq_49a5fd56c1dc" WHERE "label" =
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_6 generic=106 custom=0 stmt=SELECT entity_name, field_name, nullable, enum_values FROM public."_r2db_field_c
PREPSTMT peer=r2db-api plug=r2db-api-socket op=mutate conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_7 generic=101 custom=5 stmt=INSERT INTO "perfq_49a5fd56c1dc" ("label") VALUES ($1) RETURNING "id"
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_0d349f14f247/developer size=2 acquire=2 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
POOL peer=r2db-api plug=r2db-api-socket op=batch role=perfbase_0d349f14f247/runtime size=2 acquire=331 waits=0 wait_total_ms=0.000 wait_max_ms=0.000 in_use_peak=1
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/developer@74235 executes=21 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 executes=2648 executemany=0 prepared=8 prepared_execs=2605 share=0.984
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_0 generic=326 custom=0 stmt=SELECT 1
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_1 generic=321 custom=5 stmt=SELECT c.table_name, c.column_name, c.data_type, c.is_identity, c.domain_name FR
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_2 generic=321 custom=5 stmt=SELECT c.relname AS table_name, i.relname AS index_name, idx.indisunique, array_
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_3 generic=325 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_4 generic=325 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_5 generic=100 custom=5 stmt=SELECT "label", "_r2db_revision"::text FROM "perfq_49a5fd56c1dc" WHERE "label" =
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_6 generic=216 custom=0 stmt=SELECT entity_name, field_name, nullable, enum_values FROM public."_r2db_field_c
PREPSTMT peer=r2db-api plug=r2db-api-socket op=batch conn=perfbase_0d349f14f247/runtime@74237 name=_pg3_7 generic=651 custom=5 stmt=INSERT INTO "perfq_49a5fd56c1dc" ("label") VALUES ($1) RETURNING "id"
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=6.036 p95_ms=6.410 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=6.297 p95_ms=6.652 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=6.387 p95_ms=6.710 backend_calls=19.00 concurrency=1
POOL peer=MitateDB-api plug=MitateDB-api-socket op=query lock=perfbase_458f5f154eee acquire=226 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@74253 executes=334 executemany=0 prepared=3 prepared_execs=303 share=0.907
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@74253 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_68798a6bf244" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@74253 name=_pg3_1 generic=99 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=runtime@74253 name=_pg3_2 generic=99 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@74254 executes=1788 executemany=0 prepared=5 prepared_execs=1748 share=0.978
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@74254 name=_pg3_0 generic=439 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@74254 name=_pg3_1 generic=439 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@74254 name=_pg3_2 generic=432 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@74254 name=_pg3_3 generic=212 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=query conn=developer@74254 name=_pg3_4 generic=211 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
POOL peer=MitateDB-api plug=MitateDB-api-socket op=mutate lock=perfbase_458f5f154eee acquire=447 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@74253 executes=664 executemany=0 prepared=4 prepared_execs=627 share=0.944
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@74253 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_68798a6bf244" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@74253 name=_pg3_1 generic=208 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@74253 name=_pg3_2 generic=208 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=runtime@74253 name=_pg3_3 generic=101 custom=5 stmt=INSERT INTO "perfq_68798a6bf244" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@74254 executes=2668 executemany=0 prepared=6 prepared_execs=2625 share=0.984
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@74254 name=_pg3_0 generic=659 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@74254 name=_pg3_1 generic=659 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@74254 name=_pg3_2 generic=542 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@74254 name=_pg3_3 generic=322 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@74254 name=_pg3_4 generic=321 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=mutate conn=developer@74254 name=_pg3_5 generic=102 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-socket op=batch lock=perfbase_458f5f154eee acquire=668 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 executes=1434 executemany=0 prepared=8 prepared_execs=1393 share=0.971
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_68798a6bf244" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_1 generic=208 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_2 generic=208 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_3 generic=651 custom=5 stmt=INSERT INTO "perfq_68798a6bf244" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_4 generic=100 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_5 generic=100 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_6 generic=8 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=runtime@74253 name=_pg3_7 generic=8 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@74254 executes=7068 executemany=0 prepared=6 prepared_execs=7025 share=0.994
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@74254 name=_pg3_0 generic=1759 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@74254 name=_pg3_1 generic=1759 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@74254 name=_pg3_2 generic=1092 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@74254 name=_pg3_3 generic=872 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@74254 name=_pg3_4 generic=871 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=batch conn=developer@74254 name=_pg3_5 generic=652 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=cap_probe_1_5d5edc48 acquire=0 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
POOL peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity lock=perfbase_458f5f154eee acquire=893 waits=0 wait_total_ms=0.000 wait_max_ms=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@75005 executes=1 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@75006 executes=0 executemany=0 prepared=0 prepared_execs=0 share=0.000
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 executes=1874 executemany=0 prepared=9 prepared_execs=1820 share=0.971
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_0 generic=100 custom=5 stmt=SELECT "label" FROM "perfq_68798a6bf244" WHERE "label" = $1 LIMIT $2
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_1 generic=308 custom=0 stmt=SET LOCAL statement_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_2 generic=308 custom=0 stmt=SET LOCAL lock_timeout = '4999ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_3 generic=761 custom=5 stmt=INSERT INTO "perfq_68798a6bf244" ("label") VALUES ($1) RETURNING ctid
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_4 generic=105 custom=0 stmt=SET LOCAL statement_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_5 generic=105 custom=0 stmt=SET LOCAL lock_timeout = '4998ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_6 generic=9 custom=0 stmt=SET LOCAL statement_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_7 generic=9 custom=0 stmt=SET LOCAL lock_timeout = '4997ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=runtime@74253 name=_pg3_8 generic=100 custom=5 stmt=INSERT INTO "perfx_569addcbb890" ("label") VALUES ($1) RETURNING ctid
PREPARED peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@74254 executes=8848 executemany=0 prepared=6 prepared_execs=1730 share=0.196
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@74254 name=_pg3_6 generic=435 custom=0 stmt=SET LOCAL statement_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@74254 name=_pg3_7 generic=435 custom=0 stmt=SET LOCAL lock_timeout = '5000ms'
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@74254 name=_pg3_8 generic=210 custom=5 stmt=SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' AN
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@74254 name=_pg3_9 generic=210 custom=5 stmt=SELECT field, declared_type, enum_json, nullable FROM "_mdb_field_types" WHERE e
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@74254 name=_pg3_10 generic=210 custom=5 stmt=SELECT column_name, data_type FROM information_schema.columns WHERE table_schema
PREPSTMT peer=MitateDB-api plug=MitateDB-api-socket op=cross_entity conn=developer@74254 name=_pg3_11 generic=210 custom=5 stmt=SELECT field, declared_type FROM "_mdb_field_types" WHERE entity = $1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=12.954 p95_ms=15.415 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=13.466 p95_ms=16.695 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=14.050 p95_ms=15.910 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=13.069 p95_ms=14.950 backend_calls=22.00 concurrency=1
```

## 3. 事実 (§2 の数字だけから。判断語を含まない。WP-2 = 監督が埋める)

- (i) 接続・op ごとの `share` (**構造的上限が在るので判定は `PREPSTMT` の一覧で行う**): **r2db は全接続・全 op で `prepared=0`、`share=0.000`** (K=1: runtime 接続 1 本、`executes` は query 668 → mutate 1438 → batch 2648 と累積; K=4: runtime 接続 2 本 (pool 2)、`executes` 各 5,275 / 5,294 まで。developer 接続は `executes=21` で不変)。http と socket の plug で数字は同一である。**MitateDB は `runtime@<pid>` が 0.913〜0.983、`developer@<pid>` が 0.978〜0.998**、例外は cross_entity の developer 接続の **0.196** (K=1) / **0.199** (K=4) で、これは (iii) の消去の後の値である。cross_entity で現れる第 2 の cell (`runtime@…` `executes=1`、`developer@…` `executes=0`) は同 op が作る 2 つ目の application で、実行回数が閾値に届かないので `prepared=0` である。
- (ii) prepared に在る文の形と無い文の形 — `SET LOCAL` は在るか。**とくに MitateDB の catalog 読みの固定鍵の `SET LOCAL` が prepared に在るか**: **在る。** MitateDB の developer 接続では `SET LOCAL statement_timeout = '5000ms'` / `SET LOCAL lock_timeout = '5000ms'` (構築時定数 `_catalog_timeout_ms`) が `_pg3_0` / `_pg3_1` として prepared に在り、`generic_plans` は query 439 → batch 1,759 と累積する。catalog 読みの SELECT 4 形 (`_mdb_field_types` の 2 形、`information_schema.columns` の 2 形) も prepared に在る (いずれも `custom_plans=5` の後 `generic_plans` が増える = 6 回目から generic plan)。runtime 接続では data 面の `SELECT … WHERE "label" = $1 LIMIT $2` と `INSERT … RETURNING ctid` が prepared に在り、**deadline 由来の `SET LOCAL … = '<N>ms'` も prepared に在る**: 値は K=1 で 3 種 (`4997ms`〜`4999ms`)、K=4 で 12 種 (`4988ms`〜`4999ms`) に収まり、各値が 5 回現れた後にそれぞれ別の prepared statement になる (F1 の「毎回新しい鍵」は本 harness では成立せず、`_timeout_ms(deadline)` の戻り値は要求の開始からの経過 ms (数 ms) の分だけしか散らばらない)。**r2db の prepared 一覧は空** (`PREPSTMT` 行 0 本) で、`SET LOCAL`・data 面の SELECT / INSERT・idempotency の文のどれも在らない。
- (iii) `prepared` と `executes` の比から見える消去 (F2) の痕跡: **r2db**: 同じ query 文字列が op ごとに 100 回以上実行されているのに (`executes` 668〜5,294)、probe のたびに `prepared=0` である。**MitateDB developer 接続 (cross_entity)**: batch までの `_pg3_0`〜`_pg3_5` (`prepared_execs` 7,025) が消え、`_pg3_6`〜`_pg3_11` が新たに現れて `prepared_execs=1,730` (K=1) / 7,010 (K=4) に落ちる一方 `executes` は 7,068 → 8,848 (K=1) / 28,188 → 35,248 (K=4) と増える — この op の間に developer 接続で 1 回の全消去が起きている。runtime 接続は `_pg3_0`〜`_pg3_6` が連番のまま残り、消去は無い。
- (iv) peer の差: r2db は data 面で prepared statement が 1 本も観測されない (0 / 5,294 executes)。MitateDB は 2 本の持続接続で `share` ≥ 0.91 であり、消去は cross_entity の developer 接続の 1 回だけである。
- (v) K=1 と K=4 の差: r2db は K=4 で pool の 2 接続 (`runtime@54121` / `runtime@54125`) が交互に使われ、どちらも `prepared=0`。MitateDB は `share` がほぼ同じ (runtime 0.940〜0.983、developer 0.994〜0.998) で、runtime 接続の `prepared` 件数が 3〜7 → 11〜27 に増える — 増分は deadline 由来の `SET LOCAL` の値の種類 (3 → 12) である。
- (vi) 認証接続 — harness の MitateDB plug は `pool=None` で認証接続を呼びごとに開いて閉じるので (R-78 §1.3 の (5))、**1 呼びで閉じる接続は自動 prepare の恩恵を受け得ず、認証文は prepared になり得ない** (WO §4 の (4-6)、WO §3.1 の 6): 本計測の `PREPARED` 行に認証接続は現れない (対象外)。両 http / socket plug は認証 store に pool を渡さず、認証の文は 1 呼びごとに開いて閉じる接続で走る。
- (vii) r2db の消去が **checkout ごとの liveness rollback** (`postgres.py`:462-489) によるものか (WO §6.1 の設計レビュー 1 の H-2): r2db の成功経路で `rollback()` を打つ箇所は `_liveness_check` の 1 つだけであり (WO §1.3 の (2))、貸し出しのたびに `SELECT 1` → `rollback()` が走る。観測は「probe のたびに `prepared=0`、かつ同じ文字列の `executes` が数千回」であり、checkout ごとの全消去と整合する。他の消去経路 (dry_run の `psycopg.Rollback`、error 分岐、`_load_field_constraints` の savepoint) は本 harness の op では踏まない。
- (viii) 本計測は **plug 1 回につき application 1 個**なので、台帳 `RM`:510 の R-79 行の「application ごとに識別子が変わる」条件は**観測されない** (WO §6.1 の設計レビュー 1 の L-11): `PREPARED` の label は plug ごとに 1 つの `perfbase_*` application だけを示す (cross_entity が作る 2 つ目の cell を除く)。application ごとに識別子が変わる場合の鍵の増え方は本計測の範囲外である。

- (ix) **WP-3 の後の r2db** (§2.3): runtime 接続で `prepared` が 6 (query) → 8 (mutate / batch)、`share` 0.948 → 0.970 → 0.984 (K=1、http と socket で同一の数字)。prepared に在る文は、ping の `SELECT 1` (`generic_plans` 106 → 326 = checkout ごとに 1 回)、catalog 読み 2 形 (`information_schema` 相当の列読みと index 読み。`custom_plans=5` の後 generic、op ごとに 100 回 = **要求ごとに 1 回ずつ読んでいる**)、`SET LOCAL statement_timeout` / `lock_timeout` = `'4999ms'` (値は 1 種)、data 面の `SELECT … "_r2db_revision"::text FROM …`、制約 registry の読み (`SELECT entity_name, field_name, nullable, enum_values FROM public.…`、mutate 以降)、`INSERT … RETURNING` である。developer 接続は `executes=21` のまま `prepared=0` (閾値に届く文が無い)。**同じ木で基点 `fc891cb` の道具と交互に取った非退行 (K=1 / K=3、WO §6.2)**: r2db-http の p50 は K=1 で 3.440 → 1.664 ms (query)、3.499 → 1.789 (mutate)、3.805 → 1.922 (batch) = **−49〜−52%**、r2db-socket は −26〜−44%、K=3 では r2db-http −41〜−46%、r2db-socket −12〜−15%。MitateDB の行は −9.3〜+5.8% (socket batch のみ −11.4%) で、WP-3 が触っていない peer の run 間の散らばりと同程度である。**`connection()` の `finally` の防御 rollback** (受け入れ監査の実測): caller が非 IDLE で解放した接続には毎回 `ROLLBACK` が打たれ、F2 で prepared が全消去される。実運用経路は `with conn.transaction():` の commit / rollback で閉じるので IDLE で戻り、この rollback は発火しない。ただし**例外で終わる要求は `conn.transaction()` 自身の rollback で消去される** (F2 のとおり、WP-3 の範囲外)。

## 4. 判断 (WP-2 = 監督が書く。WP-1 では空欄)

- 効かない経路の特定: **r2db の data 面の全経路。** 原因は `_RolePool._liveness_check` が貸し出しのたびに `SELECT 1` を開いた transaction を `rollback()` で閉じることで、psycopg はこの `rollback()` で client 側の prepared 表を消し `DEALLOCATE ALL` を送る (F2)。自動 prepare は同じ接続で同じ文を 5 回数えることが前提なので、checkout ごとに 0 に戻る r2db では一度も成立しない (§3 の (i)(iii)(vii))。**MitateDB は効いている**: 持続接続 2 本で `share` ≥ 0.91、deadline 由来の `SET LOCAL` の値も 3〜12 種に収まって自身が prepared になるので、F1 の可変鍵は本 harness では問題にならない (§3 の (ii))。cross_entity の developer 接続の 1 回の消去は error 分岐の `rollback()` (F2) と整合し、経路の欠陥ではない。
- WP-3 の内容 (WO §3.4 の候補 (A) / (B) / (C) のどれを採るか): **(D) を r2db に適用し、MitateDB は (C) とする** (監督判断 2026-09-23)。(D) の形: `_liveness_check` の `SELECT 1` を transaction の外で打つ (ping の間だけ `conn.autocommit = True` にし、直後に `False` へ戻す。psycopg の `autocommit` の切り替えは IDLE のときサーバへ何も送らない) — `ROLLBACK` が出ないので prepared 表は残り、ping の往復は `BEGIN` / `SELECT 1` / `ROLLBACK` の 3 から `SELECT 1` の 1 に減る。貸し出す接続が IDLE で始まる保証は変わらない。**(A) は採らない**: r2db では ping の消去がある限り (A) だけでは 1 本も prepared にならず、MitateDB では既に prepared になっている。(A) の往復削減 (2 文 → 1 文) は R-80 の範囲として台帳に申し送る。**(B) は不要** (値の種類は 3〜12 で `prepared_max` 100 に遠い)。R-84 の再検討条件には触れない。WP-3 の後に r2db の K=1 を再計測して §2.3 に置き、`prepared` > 0 と `share` を §3 に追記する。
- **WP-3 の結果 (2026-09-23)**: (D) を r2db に適用した木で、r2db の data 面は prepared で走るようになった (§3 の (ix): `share` 0.95〜0.98、p50 は http で約半分)。**R-79 は閉じる。** 申し送り: (1) 候補 (A) (`SET LOCAL` 2 文 → `set_config` 1 文) は往復削減として **R-80** の材料 (両 peer とも `SET LOCAL` は既に prepared に在るので prepare の観点では不要)。(2) r2db が**要求ごとに catalog を 2 形読んでいる**事実 (§3 の (ix)) は **R-82** (スキーマ情報の要求ごとの読み直し) の起点の実測である。(3) 例外で終わる要求の接続は `conn.transaction()` の rollback で prepared を失う (F2) — エラー率が高い運用では再 prepare のコストが残るが、psycopg の機構であり本件では扱わない。
