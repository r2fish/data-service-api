# 設計メモ — 接続プールの取得待ちと `K` の実測 (R-78)

## 0. 版数・位置づけ

- **v0.1 (2026-09-23)。** WP-1 (実装担当) が骨だけを置く。§2〜§4 は WP-2 (監督) が埋める。基点は `docs/work-orders/WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md` (以下「WO」)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-78 行。

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

## 2. 実測 (WP-2 が埋める)

(未実施。WP-1 の完了ゲートの後、監督が実施する。)

## 3. 事実 (WP-2 が埋める)

(未実施。事実だけを書く — 判断語を含まない。)

## 4. 判断 (WP-2 が埋める)

(未実施。§2 の数字だけに基づいて監督が判定する。)
