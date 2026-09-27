# 作業指示書 — R-101 1 process 内の直列化の主体 (threadpool / GIL / PostgreSQL 往復) を切り分ける計測を足し、thread limit × K で実測する (計測が成果物)

## 0. 版数・位置づけ

- **v1.1 (2026-09-27)。是正 WP を足す改版。** 基点 local main `2e746cc` (契約 1.11.0。契約は変えない)。worktree は `.claude/worktrees/r101b` (branch `r101b`)。§0〜§6 の本文は書き換えない (`OC` §1.8 の 56・57)。**足した節**: §0 の本行、§6.1 の【依頼者裁定 (2026-09-27、逐語)】、§7 (枠 v1.1 と起草時の実測)、§8 (WP-3)、§9 (WP-4)、§10 (再計測と閉止の判定、監督)、§11 (レビューと受け入れ)、§12 (範囲外)。**規模は M × 2 WP** (台帳 R-101 行の規模 M のまま。`OC` §1.13 の 73・74)。**変更クラスはパス上 B、全体は Class D (提示待ち。逐語は §6.1 に足す)** — 契機は両 peer の `http.py` に同名・本体同一で置く middleware class (と定数) の `_ISOMORPHIC_TARGETS` への登録と、WP-1 の adapter wrapper class の登録の削除 (集合の増減。`RM` §9 の 8 の D の行。§7.5 の (W-18))。
- **v1.0 (2026-09-26)。** 基点 local main `a1c1ee3` (契約 1.11.0。契約は変えない)。Change Set Manifest 形式 (`RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §9 の 9)。worktree は `.claude/worktrees/r101` (branch `r101`)。
- 台帳は `RM` §8 の **R-101** 行 (`RM`:521)。**規模 M** (同行の冒頭。`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.13 の 73・74)。横断条件は `RM`:284 の **P-8** と `RM`:440 の **R-20**、再検討条件の受け皿は `RM`:504 の **R-84**、終了条件は `RM`:40 の **G-4** (閾値は `RM`:60-67 の §0.1.4)。出発点は R-78 の実測 (`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` §3 の 3、§4 の (2))。
- **変更クラスは、パス上の下限が B、全体が D** (§1.1 の (c))。D の契機は、両 peer の http adapter に同名・本体同一で置く 3 helper (env の読み取り関数、wrapper class、accessor `perf_thread_limit()`) を `OC` §1.5 の 38 に従って `_ISOMORPHIC_TARGETS` に登録すること (集合の増減。`RM` §9 の 8 の D の行)。`tools/change_class.py` はパスだけで判定するので、この契機を検出せず B を返す (§1.3 の (13))。**D の証拠** (`RM` §9 の 8): C の全部 (コードレビュー・受け入れ監査・完了ゲート・conformance の完走) + **依頼者裁定の逐語記録** (クラス D の宣言と 3 helper の登録を依頼者に提示し、逐語を本書 §6.1 に記す) + **版付きの security-contract 決定は該当なし** (`security/` は不変、`security/CONTROL_MAPPING.md` は 3.4 のまま)。登録済み helper の本体には触れない (触れると C の行に当たる。§2.1)。`spec/`・`conformance-tests/`・`security/` の差分は **0**。
- **設計文書は持たない** (規模 M は作業指示書 1 節。`OC` §1.13 の 74)。枠は本書 §1 (監督確定。出所は監督の scratchpad の `$SP/r101-frame.md` v1.4。起草時・改版時の疑義と設計レビュー 1 の F1〜F14 の裁定は `$SP/rulings-r101.md`)。本件の成果物である実測の記録は、新規の設計メモ `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` に置く (**§3 = WP-2、監督が実施する**)。
- 手本: `docs/work-orders/WORK_ORDER_R78_POOL_WAIT_MEASUREMENT_V1.md` の節構成 (§0〜§6)。写さず節番号で指す。
- **設計レビュー 1 回を実施済み** (2026-09-26、opus。指摘 F1〜F14 は `$SP/design-review-r101.md`、裁定は `$SP/rulings-r101.md`。本書は裁定を反映した版である)。役割: 実装担当 (`docs/work-orders/ROLE_PROMPT_TEMPLATES.md` の 2) 1 回、コードレビュー (同 5、Class D) 1 回、**受け入れ監査 (同 6) 1 回** (Class D。`OC` §1.13 の 74)。commit・完了ゲート・`tools/perf_baseline.py` の実行・merge は監督。
- **本書 v1.0 の範囲は切り分けと判断まで** (WP-1 の計測器、WP-2 の実測と判定)。寸法 (thread limit、worker 数、pool) と構造 (async psycopg、multi-process) を変える判断は計測の後に**別の変更セット**で行う (§1.1 の (a))。**R-101 の閉止は `RM` §0.1.4 の 2 の形を満たしたとき**であり、是正 WP は WP-2 の判断の後に本書の改版 (v1.1) で足す (是正の形は依頼者確認。§1.5)。
- **WP-1 (実装担当) と WP-2 (監督) は順に行う。** WP-2 は WP-1 の完了ゲートの後に始まるので**並行 WP は無く**、触るファイルの重なりの表は置かない (`OC` §1.2 の 16・17 は該当しない)。
- 規律は `OC` に従う。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (`OC` §1.7 の 47)。**疑義は実装せず報告に書く** (`OC` §1.5 の 37)。**実装担当の裁量は実装詳細のみ** — §1 の決定・§2.1 の触ってよいパス・§2.2 の完了条件を実装担当が動かさない。

## 1. 枠

§1.1・§1.2・§1.4・§1.5 は監督の枠 (`$SP/r101-frame.md` v1.4 の §1.1〜§1.5) の**逐語**である (改行位置も元のまま。fenced block に入れてある)。逐語中の「§2」「§3」「§4」「WP-2 §4」(D-4・D-5・J-5・§1.5) は設計メモ `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` の節、「§1.9」「§1.15」は `OC` の節、「RM」は `docs/design/ROADMAP_POST_PHASE7_V1.md` を指す。D-2 の「本書 §6.1」は本書の §6.1、§1.5 の「本書の改版 (v1.1)」は本書の次の版、§1.5 の「§0 / §5」は本書の §0・§5 を指す。D-2 の「§1.3 で実測し D-2 の表に固定」の表は本書 §1.3 の (19)・(20) である。枠の「§1.2 の (a)〜(f)」は本書では §1.1 の「守るべき条件」の (a)〜(f) である。行番号は枠の起草時のもので、基点 `a1c1ee3` での実測は §1.3 に置く。

### 1.1 問題設定と守るべき条件

**問題設定** (枠 §1.1):

```text
R-78 (docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md §3 の 3、§4 の (2)): 両 peer の PostgreSQL 経路で K 要求の group p50 が K にほぼ比例して伸びる (r2db-http K=1 2.67 ms → K=32 62.7 ms、MitateDB-http 6.30 → 211.5)。r2db は pool size 32 で待ち 0 でも同じ形。1 process 内で要求が 1 本ずつ処理されているが、主体が
 (a) anyio の既定 thread limiter (40 token。両 peer とも既定のまま: r2db-api/src/r2db_api/http.py:405-406、MitateDB-api/src/mitatedb_api/http.py:515)、
 (b) GIL (Python の CPU 時間)、
 (c) PostgreSQL 往復の待ち、
のどれかは切り分けられていない。asgi-inprocess plug は client と server が同 process・同 GIL・同 main thread の同 loop で動く (httpx.ASGITransport が直結: r2db-api/conformance/conformance_adapter_r2db_http.py:1078) ので、client 自身の CPU も group wall に混ざる。socket plug は uvicorn が別 thread・別 loop (conformance-tests/socket_harness.py:696-699) だが同 process・同 GIL。
G-4 (RM §0.1.1) は R-101 の閉止を終了条件に含む。R-84 の再検討条件「threadpool の混雑が tail latency を決めている」の判定材料でもある。
```

**守るべき条件** (枠 §1.2):

```text
(a) 成果物は計測と記録。寸法・構造の変更は別の変更セット (P-8、R-20)。
(b) 計測は挙動を変えない。src に足すのは time.perf_counter の読みと加算だけ。DB 往復・ログ・thread を増やさず、既存の lock を fast path に足さない (統計専用の threading.Lock の中の加算は可。R-78 D-1 の前例)。
(c) 契約 1.11.0 のまま。conformance-tests/ の差分 0 (socket_harness.py は conformance-tests/ 配下なので触らない)。spec/・security/ に触れない。変更クラスは D (`_ISOMORPHIC_TARGETS` の集合の増減。RM §9 の 8)。監査担当 1 回を起動する (OC §1.13 の 74)。
(d) 公開規律 §1.9。
(e) 判定規則 (D-5) は計測の前に固定し、計測後に動かさない (フェーズ10 D-8 U-2 の前例)。
(f) 既存の PERF / POOL / PREPARED / ROUNDTRIP 行の書式・並びは変えない (tools/tests/test_perf_baseline.py の pin)。
```

### 1.2 決定 (監督確定。D-1〜D-7。枠 §1.3)

```text
D-1 CPU 行 (tools/perf_baseline.py のみ)。measured group の区間 (warmup を除く。_run_concurrent の measured 呼び出しの前後、tools/perf_baseline.py:584-619) で resource.getrusage(RUSAGE_SELF) の ru_utime+ru_stime と time.thread_time() (呼び出し thread = main thread。harness の loop も client も、asgi plug では app の async 層もここで回る) の差分を取り、(plug, op) ごとに 1 行:
  CPU peer=<peer> plug=<plug> op=<op> concurrency=<K> thread_limit=<adapter の公開 accessor が返す解析値 | default> requests=<n*K> wall_ms=<sum of group durations> cpu_total_ms=<x.xxx> cpu_main_ms=<x.xxx> cpu_other_ms=<total-main>
  cpu_other = anyio worker thread (両 peer の run_in_threadpool の同期区間 = 認証 + service + psycopg) + socket plug では uvicorn thread。比率の計算と判定は監督 (道具は閾値を持たない、P-8)。in_process plug でも行は出す (機構は同じ)。行の位置は op ごとの先頭 (並びは D-2 末尾。PERF 行は plug の 4 op の後にまとめて出る現状 (:1587-1594) を変えない)。
D-2 DB 往復時間 (src、両 peer。パス上の下限は B、全体は D)。両 peer の psycopg_counting.py (byte-identical、r2db-api/tests/test_r79_prepared_stats.py:141 の sha256 pin。両 copy を同一に変える) に、connection 単位の db_wall_ms (float、ms) と txn_count (int) を足す。加算点は 4 つ: CountingCursor.execute / executemany (:63-69) の前後、CountingConnection.commit() / rollback() の override (txn_count +1)、CountingConnection.transaction() の override (@contextmanager で super().transaction(...) の __enter__ と __exit__ の前後を計り、それぞれ txn_count +1。r2db は `with conn.transaction():` (postgres.py の 30 箇所) で BEGIN/COMMIT を送り、psycopg はそれを private の _exec_command で送るので commit() override も CountingCursor も通らない。private には触らず公開 API の transaction() を包む)。例外時も加算する (失敗した文も 1 往復)。文の execute の中で psycopg が送る暗黙の BEGIN は execute 自身の時間の内側で txn_count には入らない (docstring に明記)。prepared_stats_skeleton (:113) の dict に db_wall_ms / txn_count の 2 鍵を足す (13 鍵)。probe_prepared_statements (:124-171) 自身の commit (:162) は psycopg.Connection.commit(conn) (基底クラスの method を直接) で終え、override を通さない (probe は計測器自身の往復)。
  DBTIME は測定経路の全 DB 往復 (application DB と platform 側の両方) を対象にし、(plug, op) ごとに scope=app と scope=platform の 2 行を出す:
  DBTIME peer=<peer> plug=<plug> op=<op> concurrency=<K> scope=app conns=<POST snapshot に在る接続 label の数> gone=<PRE にだけ在る label の数> db_calls=<execute+executemany の差分> txns=<txn_count の差分> db_wall_ms=<差分合計> db_wall_ms_per_req=<x.xxx>
  DBTIME peer=<peer> plug=<plug> op=<op> concurrency=<K> scope=platform sessions=<窓内に新規に開いた接続数> connect_wall_ms=<connect() の内側の wall の差分> db_calls= txns= db_wall_ms= db_wall_ms_per_req=<(db_wall_ms + connect_wall_ms)/requests>
  scope=app は prepared_stats() の PRE/POST snapshot (下記) から。scope=platform は probe をしない読みだけの accessor (adapter の `platform_db_time_stats()`。peer で機構が違うので同型 pin はしない — R-78 の `pool_stats()` と同じ裁定) から。実測 (起草 §1.3 (19)(20)): r2db の測定経路の platform 接続は `_credentials` と `_application_durable_audit` の 2 つの `_RolePool` の常駐 CountingConnection; MitateDB は `_read_store` の authenticate / assert_active (1 要求あたり 2 session) と audit sink の append が素の `psycopg.connect` を呼び出しごとに開閉する (`BoundedConnectionPool` は plug に無い)。数え方は両 peer とも「畳み込み」で統一する: 接続を閉じる側 (r2db `_RolePool` の liveness 失敗 / retire、MitateDB の per-call の close) が close の前にその接続の db_wall_ms / txn_count を所有者 (pool / store) の累積に足し、connect() の wall と回数 (sessions / connect_wall_ms) も所有者の累積に足す。累積の加算は統計専用の threading.Lock の中で行う (worker thread から並行に畳み込まれる)。accessor は「生きている接続の現在値 + 累積」を返すので、窓内の差分が負になることはない。呼び出しごとの接続は `CountingConnection.connect` に替える (Class B の src 変更、挙動不変)。
  txns の定義: commit() / rollback() / transaction() の enter・exit の呼び出し回数 (SAVEPOINT / RELEASE を含む。peer 間で単位が違い、R-80 の xacts とは比べない — README にも同じ 1 行)。
  窓は D-1 と同じ measured 区間。PRE snapshot は `_measure_op` の両方の枝 (real loop / in_process) で warmup の後・measured の前に取り、POST は既存の _emit_measurement_rows 内の prepared_stats() 呼び出しを使う。DBTIME を出すかは `prepared_stats` 属性の有無で決める (transport_kind では決めない)。`_emit_measurement_rows` / `_measure_op_and_emit` に足す引数は keyword で既定値を持ち、既定値のときの出力は基点と同じ。接続の対応は label で取り (ROUNDTRIP の _emit_roundtrip_conn_rows と同じ)、POST にだけ在る接続は PRE を 0 とみなす。prepared_stats() の呼び出し回数が op ごと 1 → 2 (--roundtrip 時は 2 → 3) になるので、tools/tests/test_perf_baseline.py の R-80 の 2 つの pin (21b :1098 付近、:657 付近) を同じ変更セットで実測値に改め、訂正註を本書 §6.1 に残す (--roundtrip 無しで admin_conn に触らない点は不変)。MitateDB の prepared_stats は cell の RLock を取るので POOL lock= の acquire に op ごと probe 2 回分 (R-78 時点は 1 回) が含まれる事実を README と設計メモ §1 に書く。in_process plug (prepared_stats 無し) では行を出さない。op ごとの行の並びは CPU → POOL → DBTIME → PREPARED → ROUNDTRIP (DBTIME は PREPARED と同じ 1 回の POST prepared_stats() を共有し、既存の POOL → PREPARED の呼び出し順と R-78 の POOL lock= の数え方を変えない)。probe が失敗したときは呼び出し側の conn.rollback() が override を通り PRE/POST の窓に 1 txn として入る (観察。README に記す)。
D-3 thread limiter の寸法 (peer 所有の conformance/ の http adapter。パス上の下限は B、全体は D)。環境変数 DSA_PERF_THREAD_LIMIT (正整数。無効・未設定なら無効化 = 挙動不変) を、DSA_PERF_POOL_SIZE と同じ形 (r2db-api/conformance/conformance_adapter_r2db_http.py:1019-1038 の _perf_pool_size の隣) で両 peer の http adapter が読む。在るときだけ、data-plane app を薄い ASGI wrapper で包む: wrapper は `async def __call__(self, scope, receive, send)` を持つ class (uvicorn の interface="auto" が asgi3 と判定する形。MitateDB-socket は wrapper をそのまま uvicorn に渡す) で、__call__ のたびに実行中の loop の identity を見て、その loop で初めてなら anyio.to_thread.current_default_thread_limiter().total_tokens = N を設定し (loop ごとに 1 回)、以後は素通し。adapter は解析した値を返す公開 accessor (`perf_thread_limit()` → int | None) を持ち、harness の CPU 行の thread_limit= 列がそれを読む。lifespan は両 transport とも発火しない (ASGITransport は叩かない :1300-1303、socket_harness は lifespan="off" :692) ので lifespan hook は使わない。wrapper は app object が作られる 1 箇所 (登録済み helper `_build_client` / `_surfaces_value` / `_reset_surface_state` / `_live_pg_backend_count` の本体ではなく、その呼び出し側) で掛け、asgi plug (_build_client) と socket plug (_AppDispatch / _AppSocketSurface に渡る app) の両方が同じ wrapped app を受け取る形にする。両 peer に同名で本体も同一に置く 3 helper (env の読み取り関数、wrapper class、accessor `perf_thread_limit()`) は OC §1.5 の 38 を適用して `_ISOMORPHIC_TARGETS` に登録する (件数 pin 159 → 162。Class D の契機)。`platform_db_time_stats()` は peer で機構が違う (pool vs per-call store) ので登録しない (R-78 の `pool_stats()` の裁定と同じ。理由を作業指示書 §1.2 に書く)。README に「env を残したまま pytest を走らせない」を 1 行書く。anyio の既定 limiter は loop ごとの RunVar (anyio/_backends/_asyncio.py:2235) なので、socket plug では uvicorn thread の loop 上で最初の要求時に設定される (構成上の帰結。監査照合)。env 無し = wrapper 無し (app の identity 不変)。production の composition root (main.py) と src の http.py は触らない。
D-4 sweep (監督、WP-2)。両 peer の -http と -socket (in_process は同 run に出るが表からは外す) で:
  (i) thread limit ∈ {既定 (env 無し) = 40, 4, 1} × K ∈ {1, 4, 32}、DSA_PERF_POOL_SIZE=32、warmup/n は R-78 の表 (K ≤ 4: 10/100、K=32: 3/15)。これに「既定 × K=32」の 2 回目の run を足して計 10 run。2 run の query p50 の相対差を plug ごとの雑音 ε とし、判定の閾値 δ = max(10%, 2ε) を D-5 で使う。各 run の CPU 行の thread_limit= が小見出しと一致することを記録の完了条件にする。
  (ii) 非退行: 基点 a1c1ee3 の道具と本 worktree の道具で K=1 / K=3 (--warmup 10 --n 100) を取り、PERF p50 の差が ±10% 内 (R-78 D-5 と同じ)。
  記録は新規 docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md (§1 目的と方法、§2 実測逐語 (PERFRUN/PERF/CPU/DBTIME/POOL)、§3 事実、§4 判断 = 監督)。WP-1 は骨だけ置く。
D-5 判定規則 (計測前に固定。§2 の数字だけで判定。計測後に動かさない):
  判定の単位: `query` の p50 (p95 は R-84 の判定にだけ使う)、plug = r2db-http / r2db-socket / MitateDB-http / MitateDB-socket の 4 つそれぞれ。J-2〜J-5 の K=32・K=1 の数字は thread limit 既定 (env 無し) の run から取る。閾値 δ = max(10%, 2ε) (ε は D-4 の 2 run の相対差、plug ごと)。規則ごと・plug ごとに成立 / 不成立を表にして §4 に置く。どの J も成立しない plug は「判定不能」と書き、是正を選ばず、追加計測の要否を依頼者確認に上げる。
  J-1 threadpool (K=32): (i) limit 4 と 40 の p50 差 ≤ δ → threadpool は律速でない (構成上の期待でもある: 1 要求が同時に持つ worker token は 1 つ (`_authenticate` と本体は順に呼ぶ) で 32 ≤ 40)。差 > δ で limit 4 が遅い → 「thread 数を減らすと悪化する」と事実として記し、主体の候補とは呼ばない。(ii) limit 1 の p50 が limit 40 の ±δ 内 → 直列化は thread 数に依らない。R-84 の再検討条件「threadpool の混雑が tail latency を決めている」は、K=32 で limit 4 と 40 の p95 差 > δ かつ limit 40 の方が遅いときだけ充足、それ以外は不充足。
  J-2 CPU / GIL (既定 limit、K=32): r = cpu_total_ms / wall_ms。r ≥ 0.8 → 1 core 飽和 = 直列化の主体は Python の CPU (GIL)。その内訳は cpu_other_ms / cpu_total_ms ≥ 0.6 → server 側 (anyio worker + uvicorn thread) の CPU が主、< 0.6 → main thread (client + asgi では app の async 層) の CPU が主 (asgi plug でこれに当たるときは socket plug の数字で server 側を判定し直す)。0.5 ≤ r < 0.8 → 「CPU と待ちの混在」(J-3 / J-5 と併記し、どちらも「主」とは書かない)。r < 0.5 → CPU は主体でない (J-3 / J-5 へ)。
  J-3 PostgreSQL 往復 (既定 limit): d = (scope=app と scope=platform の db_wall_ms_per_req の和 (platform は connect_wall_ms 込み)) / p50(K=1)。K=32 の r < 0.5 かつ K=1 の d ≥ 0.5 → 主体は DB 往復の待ち。MitateDB では K=32 の POOL lock= の waits / acquire ≥ 0.3 のとき J-3 を適用せず J-5 とする。
  J-4 計測の限界の定量化 (判定には使わない): socket plug の cpu_main_ms / req = client の CPU。asgi plug と socket plug の cpu_main_ms / req の差 = app の async 層の CPU − client 経路 (ASGITransport と実 socket + h11) の差 (負になり得る)。数字として §3 に記す。
  J-5 MitateDB の lock 待ち (R-102 の領分): K=32 の POOL lock= の waits / acquire と wait_total を §3 に記し、≥ 0.3 の plug は「主体は cell lock の待ち (R-102)」と書く。
  §0.1.4 の 2 (依頼者裁定 2026-09-24) に対する現状: query の p50 の K=32 / K=1 の比を plug ごとに 1 行で §3 に書く (8 倍以内が R-101 の閉止形。本書では閉じない)。
D-6 テスト (完了条件 1 項目 = 変異 1 つ。transaction() override の 3 性質 (Rollback を握りつぶす / それ以外の例外は伝播する / 例外経路でも exit 側で加算する) は 3 行 3 変異に分ける。skeleton の db_wall_ms の値 (pg_sleep 後に属性と一致)、行の並び (CPU が ROUNDTRIP の後 / DBTIME が PREPARED の後に出る変異)、CPU の wall_ms (warmup 込みにする変異)、thread_limit= 列 (accessor が常に default を返す変異)、wrapper が asgi3 と判定される (`uvicorn.Config(wrapper, lifespan="off").load()` の後 `config.interface == "asgi3"`。__call__ を同期関数にする変異)、platform 行の累積 (per-call 接続の close 前の畳み込みを外す変異) にも 1 組ずつ): psycopg_counting の db_wall_ms が execute / executemany / commit / rollback / transaction() の enter / exit で増える (それぞれ)、txn_count が commit / rollback / transaction() の enter / exit で +1、失敗した文でも db_wall_ms が増える、probe_prepared_statements を 1 回呼んでも db_wall_ms / txn_count が変わらない、skeleton の鍵集合 (13 鍵) pin、sha256 pin 緑; 既存テストファイルに足し新規ファイルは作らない; harness の CPU 行・DBTIME 行の書式 pin (stub plug)、in_process で DBTIME が出ない、DBTIME の PRE/POST 差分と POST にだけ在る接続の扱い、prepared_stats() の呼び出し回数 2; adapter の env 有無で wrapper の有無 (app identity)、wrapper が走った loop の limiter が N になる (fresh loop の単体テスト + asgi plug 経由)。
D-7 文書とコメント: tools/PERF_BASELINE_README.md に CPU / DBTIME 行と DSA_PERF_THREAD_LIMIT、窓 (measured 区間) と denominators。docstring は現在形、フェーズ/WP 語を新規 src コメントに書かない (来歴検査 --base a1c1ee3 の FAIL が §4.1 (1) 以外 0 行、--register 緑)。
```

**補足 (監督裁定。枠 D-2・D-3 が求める理由の記載)**: `platform_db_time_stats()` は `_ISOMORPHIC_TARGETS` に登録しない。r2db は `_RolePool` の常駐接続の現在値と pool の累積を合計し、MitateDB は呼び出しごとに開閉する接続を畳み込んだ store の累積を合計するので、両 peer で機構が違い本体を一致させられないからである (R-78 の `pool_stats()` と同じ裁定)。`OC` §1.5 の 38 は本体を一致させられる helper に掛かる (本体同一の env 読み取り関数・wrapper class・`perf_thread_limit()` の 3 つは登録する)。

### 1.3 起草時の実測 (基点 `a1c1ee3` の現物。起草者が実施)

以下 `RH` = `r2db-api/conformance/conformance_adapter_r2db_http.py`、`RS` = `r2db-api/conformance/conformance_adapter_r2db_socket.py`、`MH` = `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`、`MS` = `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py`、`PB` = `tools/perf_baseline.py`、`TPB` = `tools/tests/test_perf_baseline.py`。venv の版は anyio 4.15.0、starlette 1.6.0、httpx 0.28.1、uvicorn 0.52.4、psycopg 3.3.5 (`.venv` の `*.dist-info`)。

| # | 観測 | 出所 |
|---|---|---|
| (1) | **anyio の既定 thread limiter。** `current_default_thread_limiter()` は loop ごとの `RunVar` (`_default_thread_limiter`) を読み、未設定なら `CapacityLimiter(40)` を作ってその loop に置く。**寸法は loop ごとであり、最初に参照した loop の上で 40 になる。** starlette の `run_in_threadpool` は `anyio.to_thread.run_sync` を呼ぶだけで、limiter を渡さない (既定の limiter を使う)。両 peer の `src` に `total_tokens` / `CapacityLimiter` を設定するコードは **0 件** (出現は r2db `http.py`:405-407 と MitateDB `http.py`:515 のコメントだけで、どちらも「既定 40 のまま」と述べる) | `anyio/_backends/_asyncio.py`:2235・:3158-3164、`starlette/concurrency.py`:32-34、`r2db-api/src/r2db_api/http.py`:405-407、`MitateDB-api/src/mitatedb_api/http.py`:515 |
| (2) | **lifespan は両 transport とも発火しない。** asgi-inprocess plug の client は `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), ...)` で、adapter 自身のコメントが「`ASGITransport` に `lifespan` 引数は無く、この repo の adapter は ASGI lifespan を駆動しない」と述べる。socket plug の uvicorn は `uvicorn.Config(..., lifespan="off", ...)` で起動する。`create_app` の `lifespan=` 引数 (r2db `http.py`:738、MitateDB `http.py`:1261) はどちらの plug でも使われない | `RH`:1072-1078・:1300-1304、`MH`:943-946、`conformance-tests/socket_harness.py`:692 |
| (3) | **r2db の data-plane app の生成は 1 箇所。** `app = create_app(self._service)` (`RH`:1279) → `self._app = app` (:1285) → `self._loop = asyncio.new_event_loop()` (:1286) → `self._client = self._build_client(app, BASE_URL)` (:1287)。socket plug (`RS`) は `_build_client` を上書きし、**`app is getattr(self, "_app", None)` の identity で data surface へ振り分ける** (`RS`:612-614) → `_DeclaredSocketSurface.rebind_app` (:218-231) → 起動時に `_AppDispatch(self._app)` (:263) を `socket_harness.start_uvicorn_thread` に渡す (:264)。**帰結**: `RH`:1279 の直後に app を包み、包んだ object を `self._app` と `_build_client` の両方に渡せば、asgi plug の client と socket plug の uvicorn が同じ wrapped app を受け取る (identity の振り分けも保たれる) | `RH`:1072-1078・:1279-1287、`RS`:126-177・:218-231・:263-264・:572-620 |
| (4) | **MitateDB の data-plane app の生成も 1 箇所。** `app = create_app(self._service, request_bytes_limit=1_048_576)` (`MH`:1137) → `self._app = app` (:1138) → `self._loop = asyncio.new_event_loop()` (:1141) → `self._client = self._build_client(app, BASE_URL)` (:1142)。socket plug (`MS`) の `_build_client` (:420) は `_socket_surface_for(app)` (:434、定義 :483) を呼び、**`app is getattr(self, "_app", None)` の identity** (:505) で data-plane の予約 port を選んで `_AppSocketSurface(app, reservation)` (:521) を作り、起動時に `sh.start_uvicorn_thread(self.app)` (:198) へ渡す。帰結は (3) と同じ | `MH`:943-946・:1137-1142、`MS`:198・:420-434・:483-523 |
| (5) | **app を作る他の箇所と別 loop。** 隔離 surface は別の app を作り (`RH`:2466、`MH`:2071)、`hold_in_flight` 系の helper は自前の loop を作る (`RH`:794 = `_hold_in_flight_via_http_requests` (:760) の内側、`MH`:777 = `_hold_in_flight_via_http_requests_over_stalled_gate` (:734) の内側)。**`PB` はこれらを呼ばない** (`isolated_` / `hold_in_flight` の出現は `PB`:679 の docstring の 1 件だけ)。`self._app` を読む箇所は `RH`:2517 と `MH`:2108 (いずれも `hold_in_flight`) だけである | `RH`:760・:794・:2466・:2517、`MH`:734・:777・:2071・:2108、`PB`:679 |
| (6) | **thread の配置。** asgi plug では client (harness の `_replay_factory`) と app の async 層が **main thread の `adapter_obj._loop`** 上で回る (`PB`:756・:763 の `run_until_complete`)。app の同期区間は `run_in_threadpool` で anyio の worker thread に出る。socket plug の server は **uvicorn の thread と loop** (`threading.Thread(target=lambda: server.run(...))`) で同じ process・同じ GIL。**前段の nginx は別 process** (`subprocess.Popen`) なので `getrusage(RUSAGE_SELF)` には入らない | `PB`:716-730・:748-763、`conformance-tests/socket_harness.py`:428・:691-699 |
| (7) | **measured 区間。** `_measure_op` は real-loop の plug で (i) warmup の request を capture (`PB`:752) → (ii) warmup の `_run_concurrent` (:756、timing は捨てる) → (iii) measured の request を capture (:758) → (iv) measured の `_run_concurrent` (:763) の順に進む。in_process plug は (ii) :775 → (iv) :777。**capture は `_client.send` を差し替えた stub が送信の前に例外を投げる**ので server に届かない (`PB`:663-714)。group ごとの wall は `_run_concurrent` の `time.perf_counter()` の前後差 (`PB`:615-617)。**`PB` は現状 `resource` も `time.thread_time` も使わない** (出現 0 件)。`time.thread_time` は開発機の python 3.11 で使える | `PB`:584-619・:663-714・:732-780 |
| (8) | **行の印字位置。** `_emit_measurement_rows` は op ごとに `POOL` (`PB`:1207) → `PREPARED` (:1208) → `ROUNDTRIP` (:1209-1229、`--roundtrip` のときだけ) の順に印字する。`PERF` 行は `_measure_plug` が返す行を `_run` が plug の 4 op の後にまとめて印字する (`PB`:1587-1594)。**したがって plug ごとの出力は「4 op 分の POOL/PREPARED/ROUNDTRIP → その plug の PERF 4 行」の順である。** 順序の pin は `TPB`:390 (POOL → PREPARED) と :988 (PREPARED → ROUNDTRIP conn)。書式の pin は `TPB`:198 (`PERF`)・:214・:234 (`POOL` の role / lock)、出ない場合と socket の pin は :249・:257 | `PB`:1184-1230・:1233-1287・:1570-1605、`TPB`:198・:214・:234・:249・:257・:390・:988 |
| (9) | **`prepared_stats()` の呼び出し回数の pin (現行)。** `--roundtrip` 無しでは op ごと **1 回** (POST のみ): `TPB`:1098 の `test_default_run_probes_prepared_stats_exactly_once_per_op` が `len(call_log) == 1` (:1124) を assert する (R-80 の完了条件 21b)。`--roundtrip` 在りでは PRE (`_roundtrip_pre_probe`、`PB`:1153-1182、`_measure_op` の前 = warmup の前に呼ばれる :1265-1270) と POST の **2 回**で、`TPB`:657 のテストが `len(call_log) == 2` (:684) を assert する (R-80 の完了条件 3)。POST の呼び出しは `_emit_prepared_rows` (`PB`:921-954) の中の 1 回で、戻り値のリストを返す (R-80 の `ROUNDTRIP conn=` 行がそれを再利用する)。`ROUNDTRIP conn=` の差分は `label` で PRE と突き合わせ、PRE に無い label は 0 を基準にする (`PB`:998-1019) | `PB`:921-954・:998-1019、`TPB`:1098-1124 |
| (10) | **`prepared_stats()` を持つ plug。** 定義は両 `-http` adapter だけ (`RH`:4144、`MH`:3315)。`-socket` plug は継承する。in_process plug (r2db in-memory、MitateDB SQLite) の adapter には無い。peer 側の実体は r2db `_RolePool.prepared_stats` (`postgres.py`:415、queue の idle 接続を `get_nowait` で抜いて probe し戻す) と MitateDB `ApplicationCell.prepared_stats` (`cell.py`:615、cell の `RLock` の下で backend に委譲) | `RH`:4144、`MH`:3315、`r2db-api/src/r2db_api/postgres.py`:415-467、`MitateDB-api/src/mitatedb_api/cell.py`:615- |
| (11) | **`psycopg_counting.py` は両 peer で byte 一致** (`cmp` で一致、171 行)。`CountingCursor.execute` (:63-65) / `executemany` (:67-69) が接続の `execute_count` / `executemany_count` を加算してから `super()` に委ね、`CountingConnection.__init__` (:81-85) が 2 つの整数と `cursor_factory` を置く。`commit` / `rollback` / `transaction` の override は**無い**。r2db の `postgres.py` は `with conn.transaction():` を 30 箇所で使う (`catalog` :963、`query` :1339、`transact` :1471 ほか)。psycopg 3.3.5 の `Connection.transaction()` は `@contextmanager` で `Transaction` を enter / exit し (`psycopg/connection.py`:344-363)、その BEGIN / COMMIT / ROLLBACK は `_conn._exec_command` で送られる (`psycopg/transaction.py`:100-160) ので、`commit()` / `rollback()` も `CountingCursor` も通らない。MitateDB の `backend_postgres.py` は明示の `commit()` / `rollback()` を使う。`probe_prepared_statements` は自身の SELECT を素の `psycopg.Cursor(conn)` で行い (:159)、`conn.commit()` で終える (:162)。`prepared_stats_skeleton` (:100-121) は **11 鍵**の dict を返す。一致の pin は `r2db-api/tests/test_r79_prepared_stats.py`:141-153 (sha256)、11 鍵の pin は同ファイル :53 (`_ELEVEN_KEYS`) と :267 (`set(result.keys()) == _ELEVEN_KEYS`)。`.executemany(` の呼び出し数の静的 pin は両 peer とも 1 (`tools/tests/test_sql_statement_safety_scan.py`:321) で、`psycopg_counting.py` 自身の `super().executemany(...)` がその 1 件である | `r2db-api/src/r2db_api/psycopg_counting.py`:57-121・:159-162、`r2db-api/src/r2db_api/postgres.py`:963・:1339・:1471、`MitateDB-api/src/mitatedb_api/psycopg_counting.py` (同)、`r2db-api/tests/test_r79_prepared_stats.py`:53・:141-153・:267、`tools/tests/test_sql_statement_safety_scan.py`:314-321 |
| (12) | **環境変数の前例。** `_PERF_POOL_SIZE_ENV = "DSA_PERF_POOL_SIZE"` (`RH`:1027) と `_perf_pool_size()` (:1030-1038: 未設定・空・非数・0 以下なら既定を返す)。使用は `_make_cell` の 1 箇所 (:1543)。**MitateDB の http adapter には `DSA_PERF_*` の読みが無い** (出現 0 件) | `RH`:1019-1038・:1543 |
| (13) | **変更クラスの実測。** §2.1 のパスを `python3 tools/change_class.py` に渡すと `class=B` / `conformance_required=true` (`.md` の 3 本が A、残りが B)。**この道具はパスだけで判定し、`_ISOMORPHIC_TARGETS` の集合の増減を検出しない** (両 peer の `tests/test_audit_query.py` 単独でも B)。宣言クラスは D (§0) | `tools/change_class.py` (実行) |
| (13a) | **`_ISOMORPHIC_TARGETS`。** 表は `r2db-api/tests/test_audit_query.py`:2393 と `MitateDB-api/tests/test_audit_query.py`:2188、件数 pin は **159** (:3296 / :3078。テスト名 `test_isomorphic_target_table_is_pinned_to_its_current_159_rows` は :2945 / :2728)。http adapter の登録済み helper は `_build_client`・`_surfaces_value`・`_reset_surface_state` (r2db :2818-2820 / MitateDB :2601-2603) と `_live_pg_backend_count` (r2db :2599-2603)。比較の対象は同名の `FunctionDef` / `AsyncFunctionDef` / `ClassDef` / module 水準の `Assign` で (r2db :3303-3380)、正規化は package 名・先頭 docstring・行末空白・連続空行だけである。同型性の本体テストは r2db :3528 (`test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`)。本件で触る src の関数 (`psycopg_counting.py`、MitateDB の `credential_store_postgres.py` / `application_audit.py`、r2db の `postgres.py` の `_RolePool`) はどれも登録されていない | `r2db-api/tests/test_audit_query.py`:2393・:2599-2603・:2818-2820・:2945・:3296・:3303-3380・:3528、`MitateDB-api/tests/test_audit_query.py`:2188・:2601-2603・:2728・:3078 |
| (14) | **テストの置き場と件数 pin。** adapter 側の既存テストは `r2db-api/tests/test_r78_pool_wait_stats.py` (`DSA_PERF_POOL_SIZE` の :169、plug の `pool_stats` の :207) と `MitateDB-api/tests/test_r78_pool_wait_stats.py` (:192) に在り、どちらも adapter module を `sys.path` 経由で import 済みである。`psycopg_counting` のテストは両 peer の `tests/test_r79_prepared_stats.py` に在る。`tools/tests/test_no_shared_cluster_defaults.py`:280 は module 水準で admin DSN の環境変数を定義する追跡済みテストファイルを数えて **32** を pin する (新規ファイルを足すとこの pin が動く)。**本書は新規テストファイルを足さず、上の既存ファイルにテストを足す** (§2.1) | `r2db-api/tests/test_r78_pool_wait_stats.py`:25-32・:169・:207、`MitateDB-api/tests/test_r78_pool_wait_stats.py`:26-33・:192、`tools/tests/test_no_shared_cluster_defaults.py`:268-280 |
| (15) | **来歴検査の対象。** `tools/check_comment_provenance.py` は両 peer の `src/` のコメント・docstring だけを対象にする (`tests/`・`conformance/`・`tools/` は対象外)。`psycopg_counting.py` は `docs/code-history/` に登録が無い (出現 0 件) | `tools/check_comment_provenance.py`:1-35 |
| (16) | **R-78 の warmup / n の表。** K = 1・2・4: `--warmup 10 --n 100`、K = 8: 5/50、K = 16: 5/30、K = 32: 3/15 (credential ごと毎分 600 件の上限の下に `(warmup + n) * K` を収める)。道具の既定は `--n 100 --warmup 10` | `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md`:16-21、`PB`:1524-1525 |
| (17) | **R-78 の出発点の数字** (`query` の p50、`DSA_PERF_POOL_SIZE=32`): r2db-http K=1 2.663 → K=32 67.423 ms、MitateDB-http 6.281 → 219.874 ms、socket も同じ形。r2db の runtime pool の待ちは全 K で 0 | `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md`:44-53・:645-652 |
| (19) | **r2db の platform 側の接続 (測定経路)。** 全て `_RolePool` (`postgres.py`:242) が `CountingConnection.connect` (:319) で開く**プールの接続**で、寿命は process 内 (閉じるのは `close_all` :558・`retire` :571・liveness の失敗 :506・:551)。窓内の新規接続は warmup で pool が満ちた後は起きない想定。(i) **`self._credentials`** (`PostgresCredentialStore`、`credential_store.py`:238、pool :281。`RH`:1231-1236、api DSN、maxconn 32) — `_authenticate` → `DataService` の `authenticate` (`service.py`:701)・`assert_active` (:1096)・`canonical_context` (:1126)。(ii) **`self._application_durable_audit`** (`PostgresApplicationAuditSink`、`credential_store.py`:1471、pool :1520。`RH`:1268-1270) — `DataService._durable_audit` (`service.py`:685-687、pre-commit hook :1195)。(iii) `self._write_credentials` (`RH`:1237-1242、control DSN) は adapter の準備にだけ使われ、測定経路には無い。(iv) control plane の store (`RH`:1407 の `_control_stores`、:1416 の `_control_audit_reader`。いずれも `_RolePool`: `credential_store.py`:756・:1116・:1334) は data plane の測定経路には無い。**r2db の測定経路に「呼び出しごとに開閉する接続」は無い** (`psycopg.connect(` の出現は `main.py` / `control_main.py` / `ops.py` / `postgres.py`:900 の起動・運用経路だけ) | `r2db-api/src/r2db_api/postgres.py`:242・:319・:506・:551・:558・:571・:900、`credential_store.py`:238・:281・:756・:1116・:1334・:1471・:1520、`service.py`:685-701・:1096・:1126・:1195、`RH`:1231-1242・:1268-1270・:1407・:1416 |
| (20) | **MitateDB の platform 側の接続 (測定経路)。** (i) **`self._read_store`** (`PostgresCredentialStore`、`credential_store_postgres.py`:222。`MH`:1106-1109、api DSN、**`pool` を渡さない**) を `_AuthGate` (`MH`:877-901) が `authenticate` (:367、接続は :389) と `assert_active` (:463、接続は :474) で使う。どちらも `_borrow_connection` (:303-353) の no-pool の枝で `_connect` (:290-302) = **素の `psycopg.connect(...)` を呼び出しごとに開き、`finally` で閉じる** (:349-353)。R-80 の記録の「1 要求あたり新規 session 2 本」がこれである (`docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md`:88 の `sessions_per_req=2.00`)。(ii) **`self._application_durable_audit`** (`PostgresApplicationAuditSink`、`application_audit.py`:285。`MH`:1101-1104、`AuditRouter` 経由) も `_connect` (:327-328) = 素の `psycopg.connect` を `append` (:330-356)・`append_many` (:358-)・`events` (:388-) の呼び出しごとに開閉する。(iii) `self._write_store` (`MH`:1110-1113、control DSN) は adapter の準備にだけ使われる。(iv) **`BoundedConnectionPool` (`pool.py`:56、接続は `CountingConnection`、:135-142) は http adapter では構成されない** (`MH`:1055-1100 のコメント: 逐次実行の adapter で idle 接続を持つと `max_connections` を圧迫したので `pool=None` に戻した)。使うのは `main.build_app` の composition root と C-26 である。control plane の per-call 接続 (`control_plane.py`:451・:1070、`control_credential_store_postgres.py`:85) と `audit_query.py`:407 は、`PB` が測る 4 op の経路には無い | `MitateDB-api/src/mitatedb_api/credential_store_postgres.py`:222・:290-353・:367・:389・:463・:474、`application_audit.py`:285・:327-358・:388、`pool.py`:56・:135-142、`MH`:877-901・:1055-1113 |
| (21) | **uvicorn の ASGI 版の判定。** `interface="auto"` のとき、app が class でも関数でもない object なら `iscoroutinefunction(app.__call__)` で asgi3 / asgi2 を決める。`socket_harness.start_uvicorn_thread` は `interface` を指定しない。r2db-socket は `_AppDispatch` (`async def __call__`、`RS`:176-177) を挟むが、**MitateDB-socket は wrapper をそのまま uvicorn に渡す** (`MS`:198) | `uvicorn/config.py`:508-516、`conformance-tests/socket_harness.py`:691-694、`RS`:176-177、`MS`:198 |
| (18) | **`PERF-README` の節。** `## Environment` :85、`## Output format` :109、``## `POOL` lines (R-78)`` :144、``## `PREPARED` / `PREPSTMT` lines (R-79)`` :209、``## `ROUNDTRIP` lines (R-80)`` :293、`## The limits of what these numbers mean` :414 | `PERF-README`:85-414 |

### 1.4 却下した代替案 (監督確定、蒸し返さない。枠 §1.4)

```text
- py-spy / 外部 profiler: venv に無く依存 (constraints・image pin) を足す。要るのは関数の hot spot ではなく 3 主体の取り分。
- psutil の per-thread CPU: venv に無い。getrusage + thread_time の差分で main / other が分かれる。
- server を別 process にした socket 計測 (C-26 の real_server_*): client の混入は J-4 で数字にできる。別 process の CPU は macOS では ps 経由で粗い。
- src の http.py の run_in_threadpool 呼び出し (r2db 11、MitateDB 12 箇所) を包む: D-1 の cpu_other で server 側 CPU が出る。
- 契約・production の env に thread limit を足す: 計測専用 (harness 側)。
- lifespan hook で limiter を設定: 両 transport とも lifespan が発火しない。
```

### 1.5 未確定と本書の範囲 (枠 §1.5)

```text
- 設計レビュー 1 回 (2026-09-26、opus) を実施済み。F1〜F14 の裁定は $SP/rulings-r101.md。§0 / §5 の「設計レビューは行わない」は起草段階の記述なので本文を直す (未 commit)。
- RM §0.1.4 の 2 (依頼者裁定 2026-09-24) は R-101 が「閉じた」と言える計測上の形を「K=32 の query の p50 が K=1 の 8 倍以内 (両 peer の http / socket plug)」と定める。本書の WP-1 / WP-2 は切り分けと判断まで。R-101 の閉止はその形を満たしたときであり、是正 WP は WP-2 §4 の判断の後に本書の改版 (v1.1) で足す (是正の形は依頼者確認)。WP-2 は §0.1.4 の 2 に対する現状 (query の K=32 / K=1 の比、plug ごと) を設計メモ §3 に 1 行で書き、台帳 R-101 行に【追記】するが閉じない。
- 依頼者判断待ちの選択肢: 無し。結果次第の是正 (multi-process worker、async psycopg 等) は WP-2 §4 の判断の後に別起票 (起票は §1.15 の 2 問を通す)。
```

## 2. WP-1 — CPU 行・DBTIME 行 (app / platform)・`DSA_PERF_THREAD_LIMIT` を足す (実装担当)

**目的**: 1 process 内の直列化の主体 (threadpool / GIL / PostgreSQL 往復) の取り分を数字で出せる形にする。**寸法は 1 つも変えない** (env が無いときの挙動は基点と同じ)。

**読むべき正本**: 本書 §1.1 (守る条件 (a)〜(f)) / §1.2 (D-1〜D-3・D-6・D-7) / §1.3 (実測。とくに (19)・(20) の platform 接続の表) / §1.4 (却下案)。規律は `OC` §1.3〜§1.6・§1.10、同型性は `OC` §1.5 の 38、性能計測の同時実行の禁止は同 §2 の 19。

**変更クラス**: D (§0)。**使用テンプレート**: `ROLE_PROMPT_TEMPLATES.md` の 2 (実装)。

### 2.1 触ってよいパス

**D-2 (計数。src、両 peer)**

- `r2db-api/src/r2db_api/psycopg_counting.py` / `MitateDB-api/src/mitatedb_api/psycopg_counting.py` — 接続単位の `db_wall_ms` (float、ms) と `txn_count` (int) の初期化、4 つの加算点 (`CountingCursor.execute` / `executemany` の前後、`CountingConnection.commit()` / `rollback()` の override、`CountingConnection.transaction()` の override (`@contextmanager` で `super().transaction(...)` の `__enter__` と `__exit__` の前後を計る))、例外時の加算、`prepared_stats_skeleton` の 2 鍵、`probe_prepared_statements` の commit を `psycopg.Connection.commit(conn)` に替えること。**両 copy を同じ変更で byte 一致に保つ。** psycopg の private (`_exec_command` ほか) には触らない。`transaction()` の override は基底と同じ引数 (`savepoint_name` / `force_rollback`) を受け、例外の伝播と握りつぶし (`psycopg.Rollback` は基底の `Transaction.__exit__` が握りつぶす) を基底と同じに保ち、例外経路でも exit 側で加算する。`probe_prepared_statements` のそれ以外の本体・`PREPARED_STATEMENTS_SQL`・既存 11 鍵の名前と値は変えない。lock・thread・ログ・DB 往復を足さない (§1.1 の (b))。`super().executemany(...)` の呼び出しは 1 件のまま (§1.3 の (11) の静的 pin)。docstring には「文の execute の中で psycopg が送る暗黙の BEGIN は execute 自身の時間の内側にあり、`txn_count` には入らない」ことを書く。
- `MitateDB-api/src/mitatedb_api/credential_store_postgres.py` — **§1.3 の (20) の (i) の per-call 接続だけ**: `_connect` の `psycopg.connect(...)` を `CountingConnection.connect(...)` (同じ引数) に替えてその前後で connect の wall を計り、`_borrow_connection` の no-pool の枝で `conn.close()` の**前に**その接続の `db_wall_ms` / `txn_count` を store の累積 (`db_wall_ms` / `txn_count` / `connect_wall_ms` / `sessions`) に畳み込むこと (累積の加算は**統計専用の `threading.Lock` の中**。worker thread から並行に畳み込まれる)、その累積を DB 往復なしで返す読みだけの method。**pool の枝・fail-closed の例外 (`AuthorizationStateUnavailable`) の型・文言・発火条件・各 method の SQL と commit / rollback は変えない。**
- `MitateDB-api/src/mitatedb_api/application_audit.py` — **§1.3 の (20) の (ii) だけ**: `PostgresApplicationAuditSink._connect` を `CountingConnection.connect` に替えて connect の wall を計り、各呼び出し (`append` / `append_many` / `events`) の `close()` の前に同じ 4 つの累積へ畳み込むこと (統計専用の `threading.Lock` の中)、読みだけの method。SQL・例外の伝播は変えない。
- `r2db-api/src/r2db_api/postgres.py` — **`_RolePool` の統計だけ** (R-78 と同じ制限: `maxconn` / 取得と接続の timeout / eviction・LRU の条件 / 例外の型と文言 / 待ちの枝を変えず、既存の `self._lock` を fast path に足さない)。足すのは、`_connect` の `CountingConnection.connect` の前後の connect の wall と回数 (`connect_wall_ms` / `sessions`) の累積、接続を閉じる側 (liveness の失敗 :506・:551、`retire` :571) で close の**前に**その接続の `db_wall_ms` / `txn_count` を pool の累積へ足すこと、累積の加算を**統計専用の `threading.Lock` の中**で行うこと (R-78 の統計 lock を使ってよい)、「生きている接続の現在値 + 累積」を DB 往復なしで返す読みだけの method (`_acquire()` を通らない = R-78 の `acquire_count` を動かさない)。行を挿入したら `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` の行番号 (:221 ほか) を同じ変更で実測により更新する (件数と site の identity は不変。`OC` §1.5 の 40b の手順。R-78 の訂正註 2 の先例)。

**D-2 (harness)・D-1**

- `tools/perf_baseline.py` — `_measure_op` の**両方の枝** (real loop / in_process) の measured `_run_concurrent` 呼び出しの前後での `resource.getrusage(RUSAGE_SELF)` と `time.thread_time()` の読み、両方の枝の warmup の後・measured の前の PRE (`prepared_stats()` と `platform_db_time_stats()`)、`CPU` 行と `DBTIME` 行 (`scope=app` / `scope=platform`) の組み立てと印字。**op ごとの並びは `CPU` → `POOL` → `DBTIME` → `PREPARED` → `ROUNDTRIP`**。`DBTIME` の `scope=app` は `PREPARED` と同じ 1 回の POST `prepared_stats()` (`_emit_measurement_rows` の中、`pool_stats()` の後) の戻り値を共有する (POST の呼び出しを 2 回にしない)。DBTIME を出すかは `prepared_stats` 属性の有無で決める (`transport_kind` では決めない)。`CPU` 行の `thread_limit=` は plug の `perf_thread_limit()` (無ければ `default`)。`_emit_measurement_rows` / `_measure_op_and_emit` に足す引数は keyword で既定値を持ち、既定値のときの出力は基点と同じ。**既存の `pool_stats()` → POST `prepared_stats()` の呼び出し順、`PERF` / `POOL` / `PREPARED` / `PREPSTMT` / `ROUNDTRIP` 行の列名・並び・書式・行数とそれら同士の相対順、`--concurrency` / `--roundtrip` の既存の意味、`--roundtrip` 無しで `admin_conn` に触らないこと、`suite_lock` / 使い捨て cluster の扱い、`_run_self_check` を変えない** (§1.1 の (f))。閾値を持たない (P-8)。

**D-3 と accessor (peer 所有の conformance)**

- `r2db-api/conformance/conformance_adapter_r2db_http.py` — (1) `DSA_PERF_THREAD_LIMIT` の読み取り関数 (`_perf_pool_size` (§1.3 の (12)) の隣に同じ形で置く)、(2) wrapper class (`async def __call__(self, scope, receive, send)`、実行中の loop の identity ごとに 1 回だけ既定 limiter の `total_tokens` を設定する)、(3) `RH`:1279 の app 生成の直後に env が在るときだけ包む 1 箇所 (包んだ object を `self._app` と `self._build_client(...)` の両方に渡す。§1.3 の (3))、(4) 公開 accessor `perf_thread_limit()` (解析値 `int | None`)、(5) 公開 accessor `platform_db_time_stats()` (§1.3 の (19) の (i)・(ii) の `_RolePool` について「生きている接続の現在値 + 累積」を**読むだけ**で合計する。probe しない、`_acquire()` を通らない、DB 往復 0)。**(1)・(2)・(4) は MitateDB 側と同名・本体同一に書く** (`OC` §1.5 の 38)。(5) は peer で機構が違うので同型にしない (§1.2 の補足)。**登録済み helper `_build_client` / `_surfaces_value` / `_reset_surface_state` / `_live_pg_backend_count` の本体には触れない** (触れると Class C。包むのはその呼び出し側の `__init__` だけ)。`_perf_pool_size` と `DSA_PERF_POOL_SIZE` の既存の挙動、plug の composition・profile・停止点・`transport_kind`、隔離 surface (`RH`:2466) と `hold_in_flight` 系 (§1.3 の (5)) は変えない。
- `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` — r2db と同じ (1)〜(4) を `MH`:1137 の app 生成の直後に置き、(5) `platform_db_time_stats()` は §1.3 の (20) の (i)・(ii) の store の累積を読むだけで合計する (per-call 接続は呼び出しの間しか生きていないので、窓の境目では累積だけになる)。登録済み helper の本体・隔離 surface (`MH`:2071)・`hold_in_flight` 系・composition・profile・`transport_kind` は変えない。
- `r2db-api/conformance/conformance_adapter_r2db_socket.py` / `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` — **触らない。** socket plug は identity の振り分け (§1.3 の (3)・(4)) で同じ wrapped app を受け取り、accessor は継承する。差分が要ると判断したら実装せず報告する (`OC` §1.5 の 37)。

**テスト (既存ファイルに足す。新規テストファイルは作らない)**

- `r2db-api/tests/test_audit_query.py` / `MitateDB-api/tests/test_audit_query.py` — `_ISOMORPHIC_TARGETS` に 3 行 (`conformance/conformance_adapter_r2db_http.py` / `conformance/conformance_adapter_mitatedb_http.py` の env 読み取り関数・wrapper class・`perf_thread_limit`) を足し、件数 pin を **159 → 162** に改める (両 peer、テスト名の `159` も合わせる。§1.3 の (13a))。**他の行と他のテストは変えない。**
- `tools/tests/test_perf_baseline.py` — D-1・D-2 のテストの追加と、**R-80 の 2 つの pin を実測値に改めること**: `TPB`:1098-1124 の 21b (`len(call_log) == 1` → 2) と `TPB`:657-687 (`--roundtrip` 時、:684 の `len(call_log) == 2` → 3)。2 本の名前と docstring はその事実に合わせてよい。**他の既存テストの本体は変えない。**
- `r2db-api/tests/test_r79_prepared_stats.py` — `psycopg_counting` と `_RolePool` の畳み込み (完了条件 24・25) の単体テストの追加と、**`_ELEVEN_KEYS` (:53) を 13 鍵に改めること** (名前と :258-267 の docstring をその事実に合わせてよい)。sha256 の pin (:141-153) は変えない。
- `MitateDB-api/tests/test_r79_prepared_stats.py` — MitateDB の per-call 接続の畳み込み (credential store・audit sink) のテストの追加。
- `r2db-api/tests/test_r78_pool_wait_stats.py` / `MitateDB-api/tests/test_r78_pool_wait_stats.py` — D-3 と adapter の accessor のテストの追加だけ。既存テストの本体は変えない。

**文書**

- `tools/PERF_BASELINE_README.md` — D-7。`CPU` / `DBTIME` 行の節と `DSA_PERF_THREAD_LIMIT` (`## Environment` 付近)、窓 (measured 区間) と分母、op ごとの行の並び、`scope=app` / `scope=platform` の中身 (§1.3 の (19)・(20))、**`txns` の定義 (`commit()` / `rollback()` / `transaction()` の enter・exit の呼び出し回数。SAVEPOINT / RELEASE を含み、peer 間で単位が違い、R-80 の `xacts` とは比べない)**、**`POOL lock=` の `acquire` に op ごと probe 2 回分 (R-78 時点は 1 回) が含まれること**、probe が失敗したときは呼び出し側の rollback が 1 txn として窓に入ること、**env (`DSA_PERF_THREAD_LIMIT`) を残したまま pytest を走らせないこと**。既存の節の記述のうち本件で事実が変わる箇所 (`prepared_stats()` の呼び出し回数、行の並び) だけを直す。
- `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` — **新規。WP-1 では骨 (§3.2 の表の §1〜§4 の見出しと §1 の方法の下書き。§1 には `POOL lock=` の `acquire` に op ごと probe 2 回分が含まれる事実を書く) だけを置く。** §2〜§4 は WP-2 で監督が埋める。**判断を先に書かない。**
- `docs/code-history/` — 来歴検査 (`python3 tools/check_comment_provenance.py --register`) が求める記録が要る場合だけ、その 1 箇所。

**これ以外は 0 件。** とくに `spec/`・`conformance-tests/` (`socket_harness.py` を含む)・`security/`・両 peer の `main.py`・`http.py`・`service.py`・`limits.py`・`config.py`・`migrations`、r2db の `credential_store.py`、MitateDB の `pool.py` / `backend_postgres.py` / `cell.py` / `control_plane.py` / `control_credential_store_postgres.py` / `audit_query.py`、`tools/tests/test_no_shared_cluster_defaults.py` (件数 pin 32 は動かない。§1.3 の (14))、`RM` を触らない (`RM` への追記は WP-2 で監督。変異での一時編集は別で、`mutate.py` が復元する)。**既存の検査 (import の形・行番号・件数を固定する静的テストを含む) が新しいコードで赤になったら、上に名指しした更新以外は直さず報告する** (`OC` §1.5 の 37)。

**書き方**: 新規の `src` コメント・docstring は現在形で書き、フェーズ・WP・R-番号などの経緯語を書かない (§1.2 の D-7)。

### 2.2 完了条件 (77 件)

以下 `PC` = `r2db-api/src/r2db_api/psycopg_counting.py`、`MC` = `MitateDB-api/src/mitatedb_api/credential_store_postgres.py`、`MA` = `MitateDB-api/src/mitatedb_api/application_audit.py`。「実 PostgreSQL で観測する」行は counter を直接叩いて代替しない (`OC` §1.7 の 52)。

| # | 完了条件 |
|---|---|
| 1 | **(D-2)** 実 PostgreSQL の `CountingConnection` で `cursor().execute(...)` を 1 回行うと、接続の `db_wall_ms` が実行前より増える (待ちのある文、例えば `pg_sleep` を使い、増分が 0 より大きいことを観測する) |
| 2 | **(D-2)** 同じ接続で `cursor().executemany(...)` を 1 回行うと `db_wall_ms` が増える |
| 3 | **(D-2)** 明示の `commit()` を 1 回行うと `db_wall_ms` が増える |
| 4 | **(D-2)** 明示の `commit()` を 1 回行うと `txn_count` がちょうど 1 増える |
| 5 | **(D-2)** 明示の `rollback()` を 1 回行うと `db_wall_ms` が増える |
| 6 | **(D-2)** 明示の `rollback()` を 1 回行うと `txn_count` がちょうど 1 増える |
| 7 | **(D-2)** `with conn.transaction():` に入ると (block の内側で観測して) `db_wall_ms` が入る前より増える |
| 8 | **(D-2)** `with conn.transaction():` に入ると `txn_count` がちょうど 1 増える |
| 9 | **(D-2)** `with conn.transaction():` を出ると (block の内側の値と比べて) `db_wall_ms` が増える |
| 10 | **(D-2)** `with conn.transaction():` を出ると `txn_count` がちょうど 1 増える |
| 11 | **(D-2・守る条件 (b))** block の中で `psycopg.Rollback` を送出すると、override を通しても握りつぶされて block の外へ出ない (基底と同じ) |
| 12 | **(D-2・守る条件 (b))** block の中で `psycopg.Rollback` 以外の例外 (例: 独自の例外 class) を送出すると、その例外が同じ型のまま呼び出し元へ出る |
| 13 | **(D-2)** block の中で例外を送出した経路でも、exit 側の `db_wall_ms` / `txn_count` の加算が行われる |
| 14 | **(D-2)** **失敗した文** (実 PostgreSQL が拒否する SQL) の `execute` でも `db_wall_ms` が増え、`execute_count` も従来どおり 1 増える (例外は呼び出し元へそのまま出る) |
| 15 | **(D-2)** `probe_prepared_statements` を 1 回呼んでも、その接続の `db_wall_ms` と `txn_count` が変わらない |
| 16 | **(D-2)** `prepared_stats_skeleton` の返す dict の鍵集合が**既存 11 鍵 + `db_wall_ms` / `txn_count` の 13 鍵ちょうど** (`_ELEVEN_KEYS` を 13 鍵に改めた pin) |
| 17 | **(D-2)** `pg_sleep` を含む文を実行した接続で、`prepared_stats_skeleton` の `db_wall_ms` / `txn_count` の値が接続の属性と一致し、`db_wall_ms` > 0 である |
| 18 | **(D-2)** 両 peer の `psycopg_counting.py` の sha256 が一致する (`r2db-api/tests/test_r79_prepared_stats.py`:141 の既存 pin が緑) |
| 19 | **(D-2・守る条件 (b)) 監査照合**: 両 `psycopg_counting.py` の差分が `time.perf_counter` の読み・加算・2 属性の初期化・`commit` / `rollback` / `transaction` の override (`super()` への委譲)・skeleton の 2 鍵・probe の commit の書き替えだけで、**新しい psycopg の呼び・SQL・`print`・`logging`・thread・lock が 0 件**、psycopg の private 名の出現が 0 件。暗黙の BEGIN が `txn_count` に入らない旨の docstring が在る。`tools/tests/test_sql_statement_safety_scan.py` の `.executemany(` の pin (:321) が緑。`git diff` を逐語で報告に残す |
| 20 | **(D-2)** 実 PostgreSQL で `MC` の store の `authenticate` を 1 回呼ぶと、store の累積の `sessions` がちょうど 1、`connect_wall_ms` > 0、`db_wall_ms` > 0 だけ増え、`txn_count` は 0 のまま (per-call 接続は SELECT だけで明示の commit / rollback を送らず close する。close の前に畳み込んでいる) **【訂正 2026-09-26 (第 1 段の実装報告、§6.1 の 1)】** |
| 21 | **(D-2)** 実 PostgreSQL で `MA` の sink の `append` を 1 回呼ぶと、sink の累積の `sessions` がちょうど 1、`db_wall_ms` > 0、`txn_count` ≥ 1 だけ増える |
| 22 | **(D-2)** r2db の `-http` plug で data plane に 1 要求を通すと、`platform_db_time_stats()` の `db_wall_ms` と `txn_count` が要求の前より増える (credential store の pool の接続が合計に入っている) |
| 23 | **(D-2)** r2db の `platform_db_time_stats()` を呼んでも、platform の `_RolePool` の `acquire_count` (R-78) と各接続の `execute_count` / `db_wall_ms` が変わらない (読みだけ。DB 往復 0) |
| 24 | **(D-2)** 実 PostgreSQL で r2db の `_RolePool` の接続に往復を積んだ後、その接続を閉じる経路 (retire、または liveness の失敗) で閉じても、pool の「生きている接続の現在値 + 累積」の `db_wall_ms` / `txn_count` が閉じる前の値から減らない (close の前に所有者の累積へ畳み込んでいる) |
| 25 | **(D-2)** 実 PostgreSQL で r2db の `_RolePool` が新しい接続を 1 本開くと、pool の累積の `sessions` がちょうど 1、`connect_wall_ms` が 0 より大きく増える |
| 26 | **(D-2・守る条件 (b))** 所有者の累積への加算は統計専用の `threading.Lock` の中で行われ、多数の thread から同時に畳み込んでも合計が失われない (`MC` の store の累積に、例えば 32 thread × 各 1000 回の畳み込みを同時に行い、合計が期待値と一致する。`sys.setswitchinterval` を小さくするなどして、lock を外した変異で**確実に**赤になる形にする。確実に赤にできなければ実装せず報告する) | **【監督裁定 3: AST の静的 pin (3 箇所) に置き換え】**
| 27 | **(D-2・守る条件 (b)) 監査照合**: §1.3 の (19)・(20) の表で「測定経路」とした接続がすべて `scope=platform` の値に入る。照合対象は、`MC` / `MA` の `psycopg.connect(` が `CountingConnection.connect(` に替わった `git diff`、両 adapter の `platform_db_time_stats()` が読む所有者 (pool / store) の一覧 (`file:line`)、`MC` / `MA` の SQL と例外の差分が 0 行であること、`postgres.py` の差分が `_RolePool` の統計 (connect の計時・閉じる前の畳み込み・統計専用 lock・読みだけの method) だけで既存の `self._lock` を fast path に足していないこと |
| 28 | **(D-2)** `DBTIME ... scope=app` 行の書式が §1.2 の D-2 のとおり (`concurrency` の後に `scope=app conns= gone= db_calls= txns= db_wall_ms= db_wall_ms_per_req=`、列の名前と並び) である。**plug の stub で pin する** |
| 29 | **(D-2)** `DBTIME ... scope=platform` 行の書式が §1.2 の D-2 のとおり (`scope=platform sessions= connect_wall_ms= db_calls= txns= db_wall_ms= db_wall_ms_per_req=`) である。stub で pin する |
| 30 | **(D-2)** `scope=app` の `db_calls` / `txns` / `db_wall_ms` が **POST − PRE の差分**である (stub の `prepared_stats()` が PRE と POST で異なる値を返し、差分が出ることを観測する) |
| 31 | **(D-2)** POST にだけ在る label の接続は PRE を 0 とみなして `scope=app` の集計に入る |
| 32 | **(D-2)** `conns=` が POST snapshot に在る接続 label の数である (PRE に無い label を含む) |
| 33 | **(D-2)** `gone=` が PRE にだけ在る label の数である |
| 34 | **(D-2)** `scope=platform` の各値が `platform_db_time_stats()` の POST − PRE の差分で、`db_wall_ms_per_req` が `(db_wall_ms + connect_wall_ms) / requests` である |
| 35 | **(D-2)** `prepared_stats` 属性を持たない plug では `DBTIME` 行が 2 行とも出ない (例外も出ない) |
| 36 | **(D-2)** `--roundtrip` 無しの op で `prepared_stats()` の呼び出しが**ちょうど 2 回** (PRE 1 + POST 1) である (`TPB`:1098 の pin を 1 → 2 に改めたもの) |
| 37 | **(D-2)** in_process の枝 (`_loop` / `_client` を持たない stub) で、PRE が warmup の group の後・measured の最初の group の前に取られる (呼び出しの順序を記録して観測する) |
| 38 | **(D-2)** real loop の枝 (`_loop` と差し替え可能な `_client` を持つ stub) で、PRE が warmup の `_run_concurrent` の後・measured の `_run_concurrent` の前に取られる |
| 39 | **(D-2) 監査照合**: `_emit_measurement_rows` / `_measure_op_and_emit` に足した引数が keyword で既定値を持ち、既存の直接呼び出しテスト (`TPB`:390-416・:988-1010・:1127-) の本体の差分が 0 行で緑。`git diff` で示す |
| 40 | **(D-1)** `CPU` 行の書式が §1.2 の D-1 のとおり (`concurrency` の後に `thread_limit= requests= wall_ms= cpu_total_ms= cpu_main_ms= cpu_other_ms=`) である。stub で pin する |
| 41 | **(D-1)** `thread_limit=` が plug の `perf_thread_limit()` の値 (stub が 4 を返せば `thread_limit=4`) で、accessor が `None` を返すか accessor が無いときは `default` である |
| 42 | **(D-1)** `cpu_total_ms` が `ru_utime + ru_stime` の差分、`cpu_main_ms` が `time.thread_time()` の差分、`cpu_other_ms` が `cpu_total_ms − cpu_main_ms` である (両方の読みを monkeypatch した値で算術を観測する) |
| 43 | **(D-1)** CPU の差分の窓が measured の `_run_concurrent` の前後であり warmup を含まない (warmup の group ごとに進む monkeypatch の計数器で観測する) |
| 44 | **(D-1)** `CPU` 行の `wall_ms=` が measured の group の wall の和であり、warmup の group を含まない |
| 45 | **(D-1)** in_process の plug (real loop を持たない stub) でも `CPU` 行が出る |
| 46 | **(D-1・D-2)** `CPU` 行が op の行の**先頭** (`POOL` / `DBTIME` / `PREPARED` / `ROUNDTRIP` のどれよりも前) に出る (`pool_stats()` と `prepared_stats()` を持つ stub、`--roundtrip` 在りで観測する) |
| 47 | **(D-1・D-2)** `DBTIME` 行が `POOL` 行の後・`PREPARED` 行の前に出る (同じ stub で観測する) |
| 48 | **(D-1・D-2)** `CPU` 行と `DBTIME` 行の `requests=` が **`n * K`** (measured のみ) である |
| 49 | **(守る条件 (f)) 監査照合**: `PB` の `_format_row` / `_format_pool_row` / `_format_prepared_row` / `_format_prepstmt_row` / `_format_roundtrip_conn_row` / `_format_roundtrip_db_row` の差分が 0 行、`TPB`:198・:214・:234・:249・:257・:390・:988 のテストの本体の差分が 0 行で緑 (とくに既存の順序 pin の `TPB`:390 (`POOL` → `PREPARED`) と :988 (`PREPARED` → `ROUNDTRIP conn=`) が緑のまま)。`_emit_measurement_rows` の中の `pool_stats()` → POST `prepared_stats()` の呼び出し順が基点と同じで、POST の呼び出しが op ごと 1 回である。`git diff` で示す |
| 50 | **(D-2) 監査照合**: R-80 の 2 つの pin を同じ変更セットで実測値に改めた — `TPB`:1098-1124 (21b、1 → 2) と `TPB`:657-687 (`--roundtrip` 時、2 → 3)。照合対象は `git diff` (2 本の assert の値と、名前・docstring の変更だけ) と、改めた 2 本を含む `tools/tests/test_perf_baseline.py` の `pt.py` の集計行。訂正註は監督が本書 §6.1 に残す (§3.4 の 5) |
| 51 | **(D-2・D-7) 監査照合**: `POOL lock=` の `acquire` に op ごと probe 2 回分 (R-78 時点は 1 回) が含まれる事実が `tools/PERF_BASELINE_README.md` と設計メモ §1 に書かれている。照合対象は両ファイルの該当行 (`file:line`) と、MitateDB の `prepared_stats` が cell の `RLock` を取る所在 (`MitateDB-api/src/mitatedb_api/cell.py`:615) |
| 52 | **(D-3)** r2db の `-http` plug を `DSA_PERF_THREAD_LIMIT` 無しで作ると、`adapter._app` は `create_app` の返した app そのもの (wrapper でない) である |
| 53 | **(D-3)** MitateDB の `-http` plug について 49 と同じ |
| 54 | **(D-3)** r2db の `-http` plug を `DSA_PERF_THREAD_LIMIT=<正整数>` で作ると `adapter._app` が wrapper であり、**asgi client が叩く app と、`-socket` plug の data surface に渡る app (`_data_surface` の束縛先) が同じ wrapper object** である (uvicorn を起動せずに identity で観測してよい) |
| 55 | **(D-3)** MitateDB について 51 と同じ (`-socket` plug では `_socket_surfaces` の data-plane の surface の `app`) |
| 56 | **(D-3)** r2db の env の読み取り関数が、未設定・空・非数・0・負のとき**無効 (`None`、wrapper 無し)** を返す |
| 57 | **(D-3)** MitateDB について 53 と同じ |
| 58 | **(D-3)** r2db の wrapper を fresh な event loop 上で 1 回 `__call__` すると、**その loop の** `anyio.to_thread.current_default_thread_limiter().total_tokens` が N になり、呼ばれていない別の fresh loop では 40 のままである (§1.3 の (1)) |
| 59 | **(D-3)** MitateDB の wrapper について 55 と同じ |
| 60 | **(D-3)** r2db の wrapper は**同じ loop では 1 回だけ**設定する (1 回目の後にその loop の `total_tokens` を別の値へ戻し、2 回目の `__call__` の後もその値のままであることを観測する) |
| 61 | **(D-3)** r2db の wrapper は**loop ごとに**設定する (loop A で 1 回呼んだ後、別の fresh loop B で初めて呼ぶと B の `total_tokens` も N になる) |
| 62 | **(D-3)** MitateDB の wrapper について 57 と同じ |
| 63 | **(D-3)** MitateDB の wrapper について 58 と同じ |
| 64 | **(D-3)** r2db の wrapper を `uvicorn.Config(wrapper, lifespan="off")` に渡して `load()` した後、`config.interface == "asgi3"` である (§1.3 の (21)) |
| 65 | **(D-3)** MitateDB の wrapper について 61 と同じ |
| 66 | **(D-3)** r2db の `-http` plug の `perf_thread_limit()` が、env が N のとき N、無し・無効のとき `None` を返す |
| 67 | **(D-3)** MitateDB について 63 と同じ |
| 68 | **(D-3)** r2db の `-http` plug を `DSA_PERF_THREAD_LIMIT=N` で作り、data plane に 1 要求を通した後、`adapter._loop` の既定 limiter の `total_tokens` が N である (asgi plug 経由の観測) |
| 69 | **(D-3)** MitateDB について 65 と同じ |
| 70 | **(D-3・`OC` §1.5 の 38)** 両 peer の `_ISOMORPHIC_TARGETS` に env 読み取り関数・wrapper class・`perf_thread_limit` の 3 行が在り、件数 pin が 162 で、同型性テスト (r2db `tests/test_audit_query.py`:3528 と MitateDB 側の対応テスト) が緑である |
| 71 | **(D-3) 監査照合**: socket plug では limiter が uvicorn の thread の loop 上で最初の要求時に設定される (構成上の帰結)。照合対象は 54・55・64・65 の観測と、wrapped app が uvicorn に届く経路の `file:line` (`RS`:612-614 → :263-264、`MS`:434 → :505・:521 → :198)。socket 側の効きは WP-2 の sweep の `thread_limit=` と数字で見る |
| 72 | **(D-3・守る条件 (c)) 監査照合**: env 無しで conformance の挙動が不変 (完了条件 76 の `conformance-tests -q` が緑)。登録済み helper `_build_client` / `_surfaces_value` / `_reset_surface_state` / `_live_pg_backend_count` の本体の差分が両 peer で 0 行。両 peer の `main.py`・`http.py` と `conformance-tests/`・`spec/`・`security/` の差分が 0 行、`git status --short` が §2.1 のパスだけを示す |
| 73 | **(D-7) 監査照合**: `tools/PERF_BASELINE_README.md` に `CPU` / `DBTIME` (2 scope) 行の書式・窓・分母・op ごとの並び、`DSA_PERF_THREAD_LIMIT` の意味 (env 無しは wrapper 無し、loop ごとの limiter)、`txns` の定義と R-80 の `xacts` と比べない旨、probe 失敗時の rollback が 1 txn として窓に入る旨、env を残したまま pytest を走らせない旨が在り、`prepared_stats()` の呼び出し回数の記述が実測に合っている。`docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` が §1〜§4 の骨を持つ (§2〜§4 は空欄。**判断を書かない**)。`python3 tools/check_doc_refs.py` が 0 dangling |
| 74 | **(D-7) 監査照合**: `python3 tools/check_comment_provenance.py --base a1c1ee3 <触った src の全パス>` の FAIL 行が **§4.1 (1) だけ**で、(2)・(3)・(5) の行が **0 行**。`--register` が緑。出力を逐語で報告に残す。(2) が出たら**止めて報告する**。**worktree を cwd にして走らせる** |
| 75 | **監査照合**: `python3 tools/change_class.py <触った全パス>` の出力 (パスの判定は B。宣言クラス D の契機は 70 の集合の増減で、道具は検出しない — §1.3 の (13)) と、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged。ホスト名・実 DSN・作業機の絶対パスを新規の文書・テスト・コメントに書いていない (`OC` §1.9、§2 の 13) |
| 76 | **監査照合**: 報告前に `r2db-api/tests -q`・`MitateDB-api/tests -q`・`tools/tests -q`・`conformance-tests -q` を**各 1 回**回して緑 (`conformance_required=true`)。集計行を逐語で報告に残す (**完了ゲートは監督**) |
| 77 | §2.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み (`OC` §1.4 の 29〜31)。かつ §2.3 の対応表に**対応の無い行が無い** |

### 2.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) | run |
|---|---|---|
| 1 | **M1**: `PC` の `CountingCursor.execute` から `db_wall_ms` への加算を落とす | r2db |
| 2 | **M2**: `PC` の `executemany` から `db_wall_ms` への加算を落とす | r2db |
| 3 | **M3**: `PC` の `commit` override から `db_wall_ms` への加算を落とす | r2db |
| 4 | **M4**: `PC` の `commit` override から `txn_count` の加算を落とす | r2db |
| 5 | **M5**: `PC` の `rollback` override から `db_wall_ms` への加算を落とす | r2db |
| 6 | **M6**: `PC` の `rollback` override から `txn_count` の加算を落とす | r2db |
| 7 | **M7**: `PC` の `transaction` override から enter 側の `db_wall_ms` への加算を落とす | r2db |
| 8 | **M8**: `PC` の `transaction` override から enter 側の `txn_count` の加算を落とす | r2db |
| 9 | **M9**: `PC` の `transaction` override から exit 側の `db_wall_ms` への加算を落とす | r2db |
| 10 | **M10**: `PC` の `transaction` override から exit 側の `txn_count` の加算を落とす | r2db |
| 11 | **M11**: `PC` の `transaction` override が block 内の例外を常に再送出する (`psycopg.Rollback` を握りつぶさない) | r2db |
| 12 | **M12**: `PC` の `transaction` override が block 内の例外を再送出せず return する | r2db |
| 13 | **M13**: `PC` の `transaction` override の exit 側の加算を成功経路だけに移す | r2db |
| 14 | **M14**: `PC` の `execute` の `db_wall_ms` の加算を成功経路だけに移す (例外時に加算しない) | r2db |
| 15 | **M15**: `PC` の `probe_prepared_statements` の commit を `conn.commit()` (override 経由) に戻す | r2db |
| 16 | **M16**: `PC` の `prepared_stats_skeleton` の dict から `txn_count` を落とす | r2db |
| 17 | **M17**: `PC` の `prepared_stats_skeleton` の `db_wall_ms` を定数 `0.0` にする | r2db |
| 18 | **M18**: `MitateDB-api/src/mitatedb_api/psycopg_counting.py` の docstring を 1 文字変える (テストは r2db の sha256 pin) | r2db |
| 20 | **M19**: `MC` の no-pool の枝で close の前の畳み込みを外す | MitateDB |
| 21 | **M20**: `MA` の `append` で close の前の畳み込みを外す | MitateDB |
| 22 | **M21**: `RH` の `platform_db_time_stats()` から credential store (`self._credentials`) の pool を外す | r2db |
| 23 | **M22**: `RH` の `platform_db_time_stats()` の読みを `pool.connection()` (`_acquire()` 経由) にする | r2db |
| 24 | **M62**: `r2db-api/src/r2db_api/postgres.py` の `_RolePool` で、接続を閉じる前の累積への畳み込みを外す | r2db |
| 25 | **M63**: 同 `_RolePool` の `_connect` から connect の計時と `sessions` の加算を外す | r2db |
| 26 | **M64**: `MC` の累積への加算から統計専用 lock を外す (並行加算が失われる) | MitateDB |
| 28 | **M23**: `PB` の `scope=app` 行の列名を 1 つ変える (例 `gone=` → `lost=`) | tools |
| 29 | **M24**: `PB` の `scope=platform` 行の列名を 1 つ変える (例 `connect_wall_ms=` → `connect_ms=`) | tools |
| 30 | **M25**: `scope=app` の `db_wall_ms` に PRE を引かずに POST の値を出す | tools |
| 31 | **M26**: POST にだけ在る label の接続を `scope=app` の集計から落とす | tools |
| 32 | **M27**: `conns=` を PRE と POST の両方に在る label の数にする | tools |
| 33 | **M28**: `gone=` に常に 0 を出す | tools |
| 34 | **M29**: `scope=platform` の `db_wall_ms_per_req` から `connect_wall_ms` を外す | tools |
| 35 | **M30**: `prepared_stats` が無い plug でも 0 の `DBTIME` 行を出す | tools |
| 36 | **M31**: PRE の `prepared_stats()` 呼び出しを外す (1 回に戻る) | tools |
| 37 | **M32**: in_process の枝で PRE を warmup の `_run_concurrent` の前に移す | tools |
| 38 | **M33**: real loop の枝で PRE を warmup の `_run_concurrent` の前に移す | tools |
| 40 | **M34**: `CPU` 行の列名を 1 つ変える (例 `cpu_main_ms=` → `main_cpu_ms=`) | tools |
| 41 | **M35**: `thread_limit=` に accessor を読まず常に `default` を出す | tools |
| 42 | **M36**: `cpu_other_ms` に `cpu_total_ms` をそのまま出す | tools |
| 43 | **M37**: CPU の前側の読みを warmup の `_run_concurrent` の前に移す | tools |
| 44 | **M38**: `CPU` 行の `wall_ms` を warmup 込みの group の wall の和にする | tools |
| 45 | **M39**: `CPU` 行を real loop を持つ plug の枝だけで出す | tools |
| 46 | **M40**: `CPU` 行を `ROUNDTRIP` 行の後に出す | tools |
| 47 | **M41**: `DBTIME` 行を `PREPARED` 行の後に出す | tools |
| 48 | **M42**: `requests=` を `(warmup + n) * K` にする | tools |
| 52 | **M43**: `RH` で env に依らず常に wrapper で包む | r2db |
| 53 | **M44**: `MH` で env に依らず常に wrapper で包む | MitateDB |
| 54 | **M45**: `RH` で包んだ object を `self._app` に入れず、`_build_client` にだけ渡す | r2db |
| 55 | **M46**: `MH` で同じく `self._app` に包む前の app を入れる | MitateDB |
| 56 | **M47**: `RH` の読み取り関数から正の判定を外す (0 以下も採る) | r2db |
| 57 | **M48**: `MH` の読み取り関数から正の判定を外す | MitateDB |
| 58 | **M49**: `RH` の wrapper から `total_tokens` の設定を落とす | r2db |
| 59 | **M50**: `MH` の wrapper から `total_tokens` の設定を落とす | MitateDB |
| 60 | **M51**: `RH` の wrapper が毎回 `total_tokens` を設定する (loop ごとの記録を外す) | r2db |
| 61 | **M52**: `RH` の wrapper の「設定済み」を loop ごとではなく wrapper 全体の 1 つの印にする | r2db |
| 62 | **M53**: `MH` の wrapper が毎回設定する | MitateDB |
| 63 | **M54**: `MH` の wrapper の「設定済み」を wrapper 全体の 1 つの印にする | MitateDB |
| 64 | **M55**: `RH` の wrapper の `__call__` を同期関数にし、内側の coroutine を返す形にする | r2db |
| 65 | **M56**: `MH` の wrapper の `__call__` を同じく同期関数にする | MitateDB |
| 66 | **M57**: `RH` の `perf_thread_limit()` が常に `None` を返す | r2db |
| 67 | **M58**: `MH` の `perf_thread_limit()` が常に `None` を返す | MitateDB |
| 68 | **M59**: `RH` で `_build_client` に包む前の app を渡す (asgi client が wrapper を通らない) | r2db |
| 69 | **M60**: `MH` で `_build_client` に包む前の app を渡す | MitateDB |
| 70 | **M61**: `MH` の wrapper class の本体の 1 箇所を r2db 側と違う形にする (例: 属性名を変える。テストは r2db の同型性テスト) | r2db |
| 19・27・39・49・50・51・71・72・73・74・75・76・77 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す) | — |

- **M1〜M64 が赤にする test id は新規テスト (M18 は既存の sha256 pin、M31 は改めた 21b の pin、M16 は改めた 13 鍵の pin、M61 は既存の同型性テスト) の名前**なので、実装担当が §2.2 の各行に対応するテストを作り、その id を `mutations` の `tests` に **1 件だけ**書く (`OC` §1.5 の 40。`mutate.py` は最初の失敗で止まる)。
- **run 列ごとに別の JSON / 別の run に分ける** (r2db = `r2db-api/tests`、MitateDB = `MitateDB-api/tests`、tools = `tools/tests`。1 run に複数の suite を混ぜない)。
- `RH` の M43・M45・M59 と `MH` の M44・M46・M60 はそれぞれ同じ数行に掛かるので、`old` が互いに重ならない粒度を実装担当が選ぶ。変異の具体的な `old` / `new` は実装の形に合わせて実装担当が書き、報告に表で残す。

### 2.4 道具の引数

`$SP` (自分の scratchpad) を export しておく。`pt.py` / `mutate.py` は **main checkout を cwd にして走らせ、`-C` で worktree を指す** (渡し忘れると main を測る)。`conformance-tests -q` は約 9 分で、前景の 1 回 (Bash の timeout 600000) に収まる。

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101 -- r2db-api/tests/test_r79_prepared_stats.py MitateDB-api/tests/test_r79_prepared_stats.py tools/tests/test_perf_baseline.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101 -- r2db-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101 -- MitateDB-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101 -- tools/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101 -- conformance-tests -q   (約 9 分、前景 1 回で収まる)
tools/dev/mutate.py "$SP/r101-mutations.json" -C .claude/worktrees/r101 --wait 1800  (peer と tools は run を分ける)
```

worktree を cwd にして走らせるもの (`python3` で走らせる):

```bash
python3 tools/check_comment_provenance.py --base a1c1ee3 r2db-api/src/r2db_api/psycopg_counting.py MitateDB-api/src/mitatedb_api/psycopg_counting.py
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```


- 開発中は 1 行目 (対象 3 ファイル) と、テストを足した `r2db-api/tests/test_r78_pool_wait_stats.py` / `MitateDB-api/tests/test_r78_pool_wait_stats.py` / 両 peer の `tests/test_audit_query.py` を同じ形で回してよい。
- worktree から subprocess を起こすテストが在る場合の `PYTHONPATH` は `OC` §2 の 17 に従って明示する。
- **`pytest` の直接実行・`tools/perf_baseline.py` の実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。**性能計測の実行中は pytest と nginx を走らせない** (`OC` §2 の 19)。**`DSA_PERF_THREAD_LIMIT` を環境に残したまま pytest を走らせない** (§1.2 の D-3)。道具が REFUSED (終了コード 75) を返したら待つか報告する (`OC` §1.10 の 66)。
- 一時ファイルは `$SP` 配下だけに置く。複数手順のシェル処理は `$SP` の bash スクリプト (bash 3.2 互換) にする。報告は `$SP/r101-report.md` に書く。

## 3. WP-2 — thread limit × K を実測し、`docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` に記録して判定する (**監督が実施する**)

**目的**: 本件の成果物である実測を取り、逐語で残し、計測前に固定した判定規則 (D-5) だけで主体を判定する。**WP-1 の完了ゲートの後に行う。**

### 3.1 手順

1. **他の pytest と nginx を止める** (`OC` §2 の 19)。
2. **非退行 (D-4 の (ii))**: `tools/perf_baseline.py --warmup 10 --n 100 --concurrency 1` と `--concurrency 3` を、**基点 `a1c1ee3` の道具**と**本 worktree の道具**のそれぞれで取る。`PERF` 行の p50 の差が **±10% 以内**であることを確かめる。
3. **sweep (D-4 の (i))**: 本 worktree の道具で、`DSA_PERF_POOL_SIZE=32` を常に置き、`DSA_PERF_THREAD_LIMIT` を **無し (= 既定 40)・4・1** の 3 通り × **K ∈ {1, 4, 32}** の 9 run に、**「既定 × K=32」の 2 回目の run** を足した **10 run** を取る。`--warmup` / `--n` は R-78 の表 (§1.3 の (16)): K = 1・4 は `--warmup 10 --n 100`、K = 32 は `--warmup 3 --n 15`。見るのは両 peer の `-http` と `-socket` の plug で、in_process の plug は同じ run に出るが表から外す。
4. **雑音と閾値 (D-4 の (i)・D-5)**: 「既定 × K=32」の 2 run の `query` の p50 の相対差を plug ごとに求めて ε とし、**δ = max(10%, 2ε)** を plug ごとに設計メモ §3 に書く。
5. **記録**: `PERFRUN` / `PERF` / `CPU` / `DBTIME` (2 scope) / `POOL` 行を**逐語で**設計メモ §2 に置く (run ごとに小見出し。thread limit・K・`--warmup` / `--n`・`DSA_PERF_POOL_SIZE=32` を併記し、K = 32 は n が小さく分散が大きい旨を書く)。**各 run の `CPU` 行の `thread_limit=` が小見出しの thread limit と一致すること** (既定の run は `default`) を確かめる。ホスト名・実 DSN・作業機の絶対パスを書かない (`OC` §1.9、§2 の 13)。
6. **事実** (設計メモ §3): §2 の数字から、D-5 の各規則が読む値 (判定単位の `query` の p50 とその比、`r` = `cpu_total_ms / wall_ms`、`cpu_other_ms / cpu_total_ms`、`d`、`POOL lock=` の waits / acquire と wait_total、J-4 の 2 つの数字) を plug ごとに**事実として**書く。併せて **`RM` §0.1.4 の 2 に対する現状** (`query` の K=32 / K=1 の p50 の比、plug ごと) を 1 行で書く (§1.5)。
7. **判断** (設計メモ §4): **監督が書く。** §3.3 の規則 (計測前に固定。動かさない。§1.1 の (e)) を §2 の数字だけに当てはめ、規則ごと・plug ごとの成立 / 不成立の表を置く。どの J も成立しない plug は「判定不能」と書き、是正を選ばず、追加計測の要否を依頼者確認に上げる。R-84 の再検討条件は J-1 の p95 の節だけで判定する。

### 3.2 設計メモの骨 (WP-1 が置き、WP-2 が埋める)

| 節 | 内容 | 埋める者 |
|---|---|---|
| §1 | 目的と方法 (本書 §1.1 の問題設定、道具と引数、`CPU` / `DBTIME` (2 scope) 行の窓と分母と `txns` の定義、`DSA_PERF_THREAD_LIMIT` と `DSA_PERF_POOL_SIZE`、thread limit × K の 10 run と K ごとの `--warmup` / `--n`、ε と δ の求め方、`POOL lock=` の `acquire` に op ごと probe 2 回分 (R-78 時点は 1 回) が含まれる事実、合成環境である旨) | WP-1 (骨) / WP-2 (確定) |
| §2 | 実測逐語 (`PERFRUN` / `PERF` / `CPU` / `DBTIME` / `POOL`。run ごと) と非退行の前後比較 | WP-2 (監督) |
| §3 | 事実 (§3.1 の 4・6。ε と δ、`RM` §0.1.4 の 2 に対する現状の 1 行を含む) | WP-2 (監督) |
| §4 | 判断 (§3.3 の規則の成立 / 不成立の表、判定不能の plug、R-84 の再検討条件) | **WP-2 (監督)。WP-1 では見出しと空欄だけ** |

### 3.3 判定規則 (D-5 の逐語。計測前に固定し、計測後に動かさない)

```text
D-5 判定規則 (計測前に固定。§2 の数字だけで判定。計測後に動かさない):
  判定の単位: `query` の p50 (p95 は R-84 の判定にだけ使う)、plug = r2db-http / r2db-socket / MitateDB-http / MitateDB-socket の 4 つそれぞれ。J-2〜J-5 の K=32・K=1 の数字は thread limit 既定 (env 無し) の run から取る。閾値 δ = max(10%, 2ε) (ε は D-4 の 2 run の相対差、plug ごと)。規則ごと・plug ごとに成立 / 不成立を表にして §4 に置く。どの J も成立しない plug は「判定不能」と書き、是正を選ばず、追加計測の要否を依頼者確認に上げる。
  J-1 threadpool (K=32): (i) limit 4 と 40 の p50 差 ≤ δ → threadpool は律速でない (構成上の期待でもある: 1 要求が同時に持つ worker token は 1 つ (`_authenticate` と本体は順に呼ぶ) で 32 ≤ 40)。差 > δ で limit 4 が遅い → 「thread 数を減らすと悪化する」と事実として記し、主体の候補とは呼ばない。(ii) limit 1 の p50 が limit 40 の ±δ 内 → 直列化は thread 数に依らない。R-84 の再検討条件「threadpool の混雑が tail latency を決めている」は、K=32 で limit 4 と 40 の p95 差 > δ かつ limit 40 の方が遅いときだけ充足、それ以外は不充足。
  J-2 CPU / GIL (既定 limit、K=32): r = cpu_total_ms / wall_ms。r ≥ 0.8 → 1 core 飽和 = 直列化の主体は Python の CPU (GIL)。その内訳は cpu_other_ms / cpu_total_ms ≥ 0.6 → server 側 (anyio worker + uvicorn thread) の CPU が主、< 0.6 → main thread (client + asgi では app の async 層) の CPU が主 (asgi plug でこれに当たるときは socket plug の数字で server 側を判定し直す)。0.5 ≤ r < 0.8 → 「CPU と待ちの混在」(J-3 / J-5 と併記し、どちらも「主」とは書かない)。r < 0.5 → CPU は主体でない (J-3 / J-5 へ)。
  J-3 PostgreSQL 往復 (既定 limit): d = (scope=app と scope=platform の db_wall_ms_per_req の和 (platform は connect_wall_ms 込み)) / p50(K=1)。K=32 の r < 0.5 かつ K=1 の d ≥ 0.5 → 主体は DB 往復の待ち。MitateDB では K=32 の POOL lock= の waits / acquire ≥ 0.3 のとき J-3 を適用せず J-5 とする。
  J-4 計測の限界の定量化 (判定には使わない): socket plug の cpu_main_ms / req = client の CPU。asgi plug と socket plug の cpu_main_ms / req の差 = app の async 層の CPU − client 経路 (ASGITransport と実 socket + h11) の差 (負になり得る)。数字として §3 に記す。
  J-5 MitateDB の lock 待ち (R-102 の領分): K=32 の POOL lock= の waits / acquire と wait_total を §3 に記し、≥ 0.3 の plug は「主体は cell lock の待ち (R-102)」と書く。
  §0.1.4 の 2 (依頼者裁定 2026-09-24) に対する現状: query の p50 の K=32 / K=1 の比を plug ごとに 1 行で §3 に書く (8 倍以内が R-101 の閉止形。本書では閉じない)。
```

### 3.4 完了条件 (監督が自ら照合する)

1. D-4 の (ii) の前後比較が取れ、`PERF` の p50 の差が ±10% 以内である (外れたら本書 §6.1 に訂正註として残し、原因を切り分ける)。
2. 10 run の `PERFRUN` / `PERF` / `CPU` / `DBTIME` / `POOL` 行が設計メモ §2 に**逐語で**在り、run ごとに thread limit・K・`--warmup` / `--n`・`DSA_PERF_POOL_SIZE=32` が併記されている。**各 run の `CPU` 行の `thread_limit=` が小見出しと一致している** (既定の run は `default`)。どの run も `LIMIT_EXCEEDED` で欠けていない。
2a. 設計メモ §3 に plug ごとの ε と δ = max(10%, 2ε) が在る (「既定 × K=32」の 2 run から)。
3. 設計メモ §3 が事実だけで書かれ、判断語 (「〜すべき」「〜が原因である」) を含まない。
4. 設計メモ §4 が §3.3 の規則だけで判定し、規則ごと・plug ごとの成立 / 不成立を表にしている。どの J も成立しない plug は「判定不能」と書かれ、是正を選ばず追加計測の要否が依頼者確認に上がっている。§3.3 の規則の文言が本書 v1.0 と同じである (計測後に動かしていない。§1.1 の (e))。
5. 本書 §6.1 に、R-80 の 2 つの pin の訂正註 (完了条件 21b の `TPB`:1098、1 → 2 と、完了条件 3 の `TPB`:657、2 → 3) が根拠 (§1.2 の D-2) と日付付きで在る (`OC` §1.8 の 56・57。R-80 の作業指示書は書き換えない)。
6. 設計メモ §3 に、`RM` §0.1.4 の 2 に対する現状 (`query` の K=32 / K=1 の p50 の比、両 peer の `-http` / `-socket` plug ごと) が 1 行で在る (§1.5)。
7. `RM` §8 の R-101 行に結論を【追記】する。**R-101 は閉じない** (閉止は §0.1.4 の 2 の形を満たしたとき。§1.5)。R-84 行に判定を追記する (**行は消さない**。`OC` §1.8 の 56)。結果次第の是正は起票の 2 問 (`OC` §1.15 の 77) を通してから別に起票する (§1.5)。

## 4. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **(4-1) 是正。** thread limit・worker 数・process 数の変更、async psycopg への移行 (`RM`:504 の R-84)、multi-process worker は本書では行わない (§1.1 の (a)、§1.5)。本書は判定の材料を供給するだけである。
- **(4-2) MitateDB の cell の `RLock` による直列化** (`RM`:522 の R-102)。本件では CPU / DB の取り分を出すだけで、lock 待ちの wall は「その他」に含める (§1.2 の J-5)。
- **(4-3) `conformance-tests/socket_harness.py`** (Class C)。limiter は adapter 側の wrapper だけで設定する (§1.1 の (c)、§1.2 の D-3)。
- **(4-4) production の composition root (`main.py`) と契約への thread limit の追加** (§1.4)。`DSA_PERF_THREAD_LIMIT` は harness 専用である。
- **(4-5) 台帳 `RM` の R-101 / R-84 行の追記と引き継ぎ書。** 統合時に監督が行う (§3.4 の 7)。
- **(4-6) 是正 WP。** R-101 を閉じる是正 (`RM` §0.1.4 の 2 の形を満たす変更) は、WP-2 の §4 の判断の後に**本書の改版 (v1.1) で足す**。是正の形は依頼者確認を経る (§1.5)。

## 5. レビューと受け入れ

- **設計レビュー 1 回を実施済み** (2026-09-26、opus。指摘 F1〜F14 は `$SP/design-review-r101.md`、裁定は `$SP/rulings-r101.md`。本書 §1 は裁定を反映した枠 v1.3 である)。
- **コードレビュー 1 回** (`ROLE_PROMPT_TEMPLATES.md` の 5、Class D。実装担当とは別の起動)。観点: (i) `psycopg_counting.py` の差分が `perf_counter` の読みと加算・回数の加算・`super()` への委譲だけで、DB 往復・ログ・thread・lock を増やしていないこと、両 copy が byte 一致であること (§1.1 の (b))、(ii) CPU と DBTIME の窓が measured 区間であり warmup を含まないこと、PRE の位置 (完了条件 37・38・43)、probe の往復が計測に入らないこと (完了条件 15)、`transaction()` の override が例外の伝播と握りつぶしを基底と同じに保ち例外経路でも加算すること (完了条件 11〜13)、(iii) 既存の行の書式と相対順が不変で、op ごとの並びが `CPU` → `POOL` → `DBTIME` → `PREPARED` → `ROUNDTRIP` であること (§1.1 の (f)、完了条件 46・47・49)、(iv) env 無しで adapter の app の identity と conformance の挙動が不変であること、env 在りで asgi と socket の両方が同じ wrapper を受け取ること (完了条件 52〜72)、(v) 新規テストの空振り (`OC` §1.5 の 32) と代理指標 (`OC` §1.7 の 52)、(vi) 新規 `src` コメントに経緯語が無いこと (完了条件 74)、(vi-2) platform の計数が §1.3 の (19)・(20) の測定経路の接続を漏れなく捉え、閉じる側 (r2db の liveness 失敗・retire、MitateDB の per-call の close) の畳み込みが close の前にあり、累積の加算が統計専用 lock の中にあること、MitateDB の store の SQL と例外が不変であること (完了条件 20〜27)、同型性の 2 行と登録済み helper の本体の不変 (完了条件 70・72)、wrapper が asgi3 と判定されること (完了条件 64・65)、(vii) レビュー担当自身の変異 1〜2 件 (報告に無いもの。完了ゲートと並行させない)。
- **受け入れ監査 1 回** (`ROLE_PROMPT_TEMPLATES.md` の 6。Class D のため。`OC` §1.13 の 74。レビュー担当とも別の起動)。観点は §2.2 の全行の主張 vs 実測 (`OC` §1.5 の 34) と、§2.3 の変異の再現。
- **Class D の証拠** (§0、`RM` §9 の 8): 上のレビューと監査、完了ゲート、conformance の完走に加え、**依頼者裁定の逐語** (クラス D の宣言と 3 helper の登録を依頼者に提示して得た文言) を監督が本書 §6.1 に記す。版付きの security-contract 決定は**該当なし** (`security/` 不変、`security/CONTROL_MAPPING.md` 3.4 据え置き) と §6.2 に記す。
- **完了ゲートは監督**が行う (`tools/dev/gate.py -C .claude/worktrees/r101`)。監督が集計行と §2.2 を照合して判定する。受理したら **WP-2 (§3)** に進み、§3.4 をもって台帳 `RM` §8 の R-101 行に【追記】する (閉じない。§1.5)。

## 6. 記録 (統合時に監督が埋める。§1〜§5 の本文は書き換えない)

### 6.1 訂正註と監督裁定

- **【依頼者裁定 (2026-09-26、逐語)】「D で進める」** — 監督の提示 (両 peer の http conformance adapter に同名・同一本体で置く helper 3 つ (`DSA_PERF_THREAD_LIMIT` の読み取り関数、thread limiter を設定する ASGI wrapper class、`perf_thread_limit()`) を OC §1.5 の 38 に従い `_ISOMORPHIC_TARGETS` に登録するので RM §9 の 8 の表により Class D。「版付きの security-contract 決定」は該当なし (`security/` の変更は SI-08 Evidence の参照追随と版行 3.4 → 3.5 のみ、契約 1.11.0 不変)。代替案 = 38 の適用除外で Class B に留める、は本体が同一なので除外の理由がない) に対する裁定。Class D の証拠の「依頼者裁定の逐語記録」は本項。
- **【訂正註 1 (2026-09-26)】完了条件 20 の `txn_count` ≥ 1 は誤り。** `MC` の `authenticate` / `assert_active` は SELECT だけで commit / rollback を呼ばず (暗黙の BEGIN は execute の内側、close は明示の ROLLBACK を送らない)、`txn_count` ≥ 1 を作るには DB 往復を足すことになり守る条件 (b) に反する。実装担当の疑義 1 を受け、監督が完了条件 20 を「`txn_count` は 0 のまま」に改めた (変異 M19 はそのまま。close 前の畳み込みを外せば `sessions` / `connect_wall_ms` / `db_wall_ms` の assert が赤)。
- **【訂正註 2 (2026-09-26)】§2.1 に `tools/tests/test_src_import_readers.py` を足す** (`STRING_ANNOTATION_ONLY_READERS` の 1 行。`MA` の `psycopg.connect` → `CountingConnection.connect` の置き換えの機械的帰結。第 2 段の実装報告の疑義 3、監督受理)。
- **【訂正註 3 (2026-09-26)】§2.1 に `security/CONTROL_MAPPING.md` を足す (監督だけが触る)**: 件数ピンの改名 (`_159_rows` → `_162_rows`) で SI-08 Common の Evidence 参照 (:819) が dangling になり `conformance-tests/test_control_mapping_register.py` が赤になった (第 2 段の疑義 0)。監督が参照を追随させ、版を 3.4 → 3.5 に上げた (Control 主張の追加・変更なし。前例: keyset paging 設計 §851)。再実行: `pt: 58 passed in 3.01s` (2026-09-26)。
- **【監督裁定 3 (2026-09-26)】完了条件 26 (統計専用 lock を外すと並行の畳み込みが失われる → 赤) は、AST の静的 pin に置き換えて受理する** (並行加算の喪失を確実に赤にする試験は本質的に不安定。コードレビュー 1 の F3)。pin は `MC` の credential store・`MA` の audit sink・r2db `_RolePool._fold_closed_connection_stats` の 3 箇所の畳み込みが統計専用 lock の `with` の内側に在ることを固定し、変異は 3 箇所それぞれで `with` を外す 3 件。
- **【訂正註 4 (2026-09-26)】完了条件 22 の「`db_wall_ms` と `txn_count` が増える」は「`db_wall_ms` と `db_calls` が増える」に改める** (r2db の `_authenticate` の SELECT は明示の transaction 境界を送らない。差し戻し 1 の 4 のとおり `db_calls` を実値にしたのでそれを観測する)。§0・§5 の「`security/CONTROL_MAPPING.md` は 3.4 のまま」は訂正註 3 のとおり 3.5 に読み替える。
- **【監督裁定 4 (2026-09-26)】コードレビュー 1 (opus、Class D) の F1〜F10 は F3 (上の裁定 3) と F10 (記録、監督が直した) を除き全件「直す」** (`$SP/r101-return-2.md`)。
- **【監督裁定 2 (2026-09-26)】第 2 段の疑義 1・2・4 (完了条件 52〜55・68〜69・22・23 の未実装、platform 行の `db_calls=` 常時 0) は差し戻し** (`$SP/r101-return-1.md`)。時間予算は完了条件を落とす理由にならない。
- **【監督裁定 1 (2026-09-26)】`tools/check_comment_provenance.py --base a1c1ee3` の §4.1 (2) の 11 行 (両 peer の `psycopg_counting.py` 各 5 箇所、`MC` 1 箇所。第 1 段の報告は 12 行と書いたが、コードレビュー 1 の再実行で 11 行 = 列挙どおり)。** 既存の関数・class に新しい counter の docstring を足したことによる赤で、設計 v0.22 D-2 の仕様どおり (道具の不具合ではない)。R-67 の前例に倣い受理する。条件: 各 docstring が現在形で経緯語を含まないことをコードレビューで 1 箇所ずつ確認し、12 箇所の file:line を §6.2 に残す。

- **【監督裁定 5 (2026-09-26、再開チャット)】完了条件 26 の AST pin の 3 箇所化で、MitateDB `tests/test_r79_prepared_stats.py` の helper `_self_attr` / `_find_with_lock_body` / `_body_contains` を r2db 側にも同名・本体同一で置いた。** `OC` §1.5 の 38 により `_ISOMORPHIC_TARGETS` に 3 行を登録し、件数 pin は 162 → **165** (§2.1 の「159 → 162」、完了条件 70 の「162」は 165 に読み替える。`security/CONTROL_MAPPING.md`:819 と版行 3.5 の文言は監督が追随、版は 3.5 のまま)。集合の増分は本変更セット全体で 6 行 (perf-harness helper 3 + AST helper 3)。**依頼者裁定「D で進める」はクラスの宣言への裁定であり、同じ変更セット内で同じ契機 (38 の登録) の行が増えてもクラスは D のまま**と監督が読む (コードレビュー 2 の指摘 10 の読み 1。異論があれば引き継ぎ書の依頼者判断待ちで扱う)。変異は M64 (`MC`)・M64b (`MA`)・M64c (r2db `_RolePool`)。
- **【監督裁定 6 (2026-09-26、再開チャット)】`tools/check_comment_provenance.py --base a1c1ee3` の §4.1 (2) のうち、裁定 1 の 11 行の範囲外の行 (`r2db-api/src/r2db_api/postgres.py`:589 `_RolePool.connection` の末尾 4 block、両 http adapter の `__init__` の 1 block、`tools/perf_baseline.py` の 4 関数) は、いずれも既存関数の本体に新規コードと共に足した comment block で削除行 0 (今回分)。裁定 1 と同じ扱いで受理し、各 block の現在形・経緯語なしはコードレビュー 2 で確認した (残った経緯語は差し戻し 3 で除去)。検査器の対象外 (conformance / tools) の comment にも D-7 の書き方を同じに掛ける。
- **【監督裁定 7 (2026-09-26、再開チャット)】コードレビュー 2 (opus、10 件 + 観察 4 件) の指摘 1 (`--roundtrip` の `ROUNDTRIP db=app xacts=` に DBTIME の PRE probe の commit が入り、補正が POST 側しか引かない) は案 (a) で直す**: PRE snapshot の probe 済み本数も補正で引く (keyword 引数、既定値は従来どおり)、stub テスト 1 本と変異 M107、README :485 の段落に 1 文。D-2 がこの相互作用を扱っていなかった設計の穴として本項を訂正註にも兼ねる。指摘 2〜9 と観察 (a)〜(c) は差し戻し 3 (`$SP/r101-return-3.md`) で直す。指摘 10 は裁定 5 のとおり記録で扱う。

- **【監督裁定 8 (2026-09-26、再開チャット)】受け入れ監査 (opus、充足 77 / 未充足 0 / 証拠不足 0、観察 5 件) の裁定**: O-1 (main が R-112 `31f981d` まで進み `_ISOMORPHIC_TARGETS` の件数 pin が衝突) は監督が main を merge して解消 (合算 159 + 2 (R-112) + 6 (本件) = **167**。裁定 5 の 165 は 167 に読み替える。CM :819 と版行 3.5 の文言を追随、r2db `tests/test_r78_pool_wait_stats.py` の件数 assert も 167。merge 後の tree で完了ゲートを再実行する)。O-2 (完了条件 66・67 が accessor を stand-in で読むだけ) と O-4 (M45・M46 の docstring の assert の取り違え) は差し戻し 4 で直す (`$SP/r101-return-4.md`)。O-3 (`MitateDB-api/src/mitatedb_api/cell.py`:622-627 の `prepared_stats` docstring の呼び出し回数の主張が古い) は**観察**: `cell.py` は §2.1 の範囲外で、既存 docstring の変更は来歴の登録 (`docs/code-history/`) を伴うので、`cell.py` に触る次の変更セット (R-102) で直す。O-5 (設計メモ §1 の 2 箇所) は WP-2 で監督が直す。**完了条件 76 の読み替え**: 実装担当が suite ごとに回した最終集計の代わりに、監督の木の状態の確定 (再開チャット冒頭の 3 suite) と最終 tree の完了ゲート + `tools/tests` を証拠とする (監査パケットの注記のとおり)。

- **【訂正註 9 (2026-09-27)】§3.4 の 1 (非退行 ±10%)**: K=1 の 1 組目で `r2db-api-http` `batch` だけが +11.7% (1.602 → 1.789 ms) と外れた。同条件で 2 組を追加した結果 +3.5% (1.673 → 1.732)・+0.3% (1.740 → 1.745) で再現せず、他の 20 (plug, op) と K=3 の 21 はすべて ±10% 内。1 組目は完了ゲート直後の最初の run で、雑音と判断する (計測器が measured 経路に足したのは `time.perf_counter` の読みと加算だけで、守る条件 (b) のとおり)。設計メモ §2.1 に 3 組の逐語、§3 の 1 に数字を残す。
- **【訂正註 10 (2026-09-27)】§3.3 の規則の場合分けの外の結果**: J-1 (i) は「limit 4 と 40 の差 ≤ δ」と「差 > δ で limit 4 が遅い」の 2 場合しか定めないが、3 plug で limit 4 の方が 30〜49% 速かった。J-2 の r は 4 plug とも 1 を超えた (規則は r ≥ 0.8 を「1 core 飽和」と呼ぶ)。いずれも規則は動かさず (守る条件 (e))、設計メモ §4 の表に「場合分けの外」と事実で記し、§4 の 6 に規則の次版への申し送りとした。

- **【訂正註 11 (2026-09-27)】`conformance-tests/COLLECTION_FLOOR` 4262 → 4314。** 守る条件 (c) の「`conformance-tests/` の差分 0」は条件・テストについてであり、件数の床は `OC` §1.3 の 25 のとおり完了ゲートで監督が前回 main の実測値に合わせる (前チャットの引き継ぎ書 §3 の 3「merge 時に照合」)。最終 tree の完了ゲート (r101b) の 4314 = main `31f981d` の 4262 + 本変更セットの 52。

- **【依頼者裁定 (2026-09-27、逐語)】是正の形 (本書 §7〜§12)。** 監督の scratchpad の `ruling-r101-remedy.md` の逐語 (言い換えない。`OC` §1.5 の 35):

  ```text
  【依頼者裁定 (2026-09-27、逐語)】

  監督の提示 ($SP/r101-remedy-frame.md v1.0 §1.6 の 4 点: 1. §0.1.4 の 2 を real-server plug で判定する形に改める (R-14 の形)、2. (a') を WP-3、(e) を WP-4 として WO v1.1 に足し、(b) は規模 L で起票、(d) は却下、3. (a') の既定値 4 (env で上書き可)、4. MitateDB adapter の pool 無しを WP-3 で production と同じ配線に直す) に対して:

  「1〜4 すべて監督案どおりで進める」
  ```

- **【依頼者裁定 (2026-09-28、逐語)】「D で進める」** — v1.1 の変更クラス D の宣言に対する裁定。監督の提示: 契機は `_ISOMORPHIC_TARGETS` の集合の増減 (追加 = 両 peer の `src/*/http.py` に同名・本体同一で置く thread-limit の pure-ASGI middleware class と定数 `DEFAULT_THREAD_LIMIT = 4`、両 `main.py` の env 読み取り helper が同名・本体同一ならそれも; 削除 = WP-1 の `_PerfThreadLimitWrapper`)。「版付きの security-contract 決定」は該当なし (`security/` は件数 pin のテスト名が変わるときの Evidence 参照追随と版行のみ、契約 1.11.0 不変、Security Invariants 不変)。証拠は C の全部 + 本項の逐語。代替案 = 38 の適用除外で Class B に留める、は本体が同一なので除外の理由がない (WP-1 の裁定と同じ)。
- **【監督裁定 9 (2026-09-28)】WP-3 と WP-4 の worktree**: §7.6 の重なり (`tools/PERF_BASELINE_README.md` 1 本) を承知のうえで、WP-4 を worktree `r101b` (branch `r101b`)、WP-3 を同じ基点 `01d38c5` から切った worktree `r101b-wp3` (branch `r101b-wp3`) で並行させる。README の重なりは統合時に監督が解く (WP-4 は新しい節を足し、WP-3 は既存の文を直すので、行の重なりは無い見込み。重なれば監督が手で合成し、両 implementer の記述を残す)。

- **【訂正註 12 (2026-09-28)】完了条件 92・93・97・98 (r2db の D-9)** の「`build_app(env)` を実行し fresh loop で 1 回呼ぶ」は、r2db では既存ファイルの方針 (`r2db-api/tests/test_threadpool_offload.py` は実 platform DB を要する `build_app` を実行しない。`test_main_composition_root_wires_pool_size_from_role_pool_size` と同型) に従い、「`build_app` が `_thread_limit_from_env(env)` の値を `create_app(thread_limit=)` に渡す AST 構造 pin + `_thread_limit_from_env` の単体テスト (未設定・空 → 4、正整数、0 / 負 / 非数 → 例外)」の合成で充足と読む (create_app 側の fresh loop の観測は D-8 のテストが持つ)。MitateDB は `test_main.py` の既存の `build_app` 実行系で `build_app(env)` を実行し、返った app の `Middleware.kwargs` から `thread_limit` を読む (要求は通さない。fresh loop の観測は同じく D-8 のテスト)。第 1 段の疑義 (1)、コードレビュー 1 の F8 (c) で文言を改めた。
- **【監督裁定 10 (2026-09-28)】`tools/check_comment_provenance.py --base 2e746cc` の §4.1 (1) 4 行 (両 `http.py`・両 `main.py` のコード変更) と §4.1 (2) 4 行 (両 `create_app` の docstring、両 `main.py` の module docstring の env 表) は、既存の関数・module に新規コードと共に足した docstring の変更で削除行 0。裁定 1・6 と同じ扱いで受理する。条件: 現在形・経緯語なしをコードレビューで確認する。`--register` は緑 (`92 files scanned, 434 CH-IDs`)。R2H の limiter 40 の塊は実測で :383-453 の 1 塊 (WO の「:405-424」より広い) で、塊全体を CH-0544 として登録し旧 40 の 2 文だけを削除した (第 1 段の逸脱 (c))。
- **【観察 (2026-09-28)】MitateDB の `LIMIT_EXCEEDED` (concurrency) の HTTP status は 413、r2db は 429** (第 1 段の疑義 (2))。契約 `spec/data-service-api.v1.json` は HTTP status を束縛しない (429 / 413 の出現 0 件) ので契約違反ではなく、本変更セットでは直さない。引き継ぎ書の裁定表で扱う。
- **【監督裁定 11 (2026-09-28)】`security/CONTROL_MAPPING.md` 3.5 → 3.6**: SI-08 Common Evidence の件数 pin 参照 (`_167_rows` → `_169_rows`) の追随のみ (Control 主張の追加・変更なし)。両 `http.py` (27 件ずつ) と両 `main.py` (6 件ずつ) への行番号参照は、WP-3 第 2 段と WP-4 の統合後に監督が一括で追随させる。

- **【監督裁定 13 (2026-09-28)】WP-3 のコードレビュー 1 (opus、F1〜F11、`$SP/review-wp3.md`)**: F1 (r2db D-9 の AST pin が env と既定値を固定しない)・F2 (R2H CH-0544 の縮約で文意が壊れた)・F3 (MTH CH-0202 が D-13 と矛盾)・F4 (新 docstring の断言 (a)〜(d))・F7 (8+1 が slot 保持を直接観測しない)・F8 (a)(b)・F9 (古い記述)・F10 (README :513-515 の偽の理由) は差し戻し 1 で直した。F5 = 監督裁定: `pool.py`:101・:136 の来歴検査 §4.1 (1)(2) は裁定 10 と同じ読みで受理、`:157` の「No other line changes.」(経緯の文) は削除。F6 = 逸脱 (a) (acquire() の死接続の畳み込み) を採り、fake の死接続テスト 2 本 + 変異 2 件で固定。F8 (c) = 訂正註 12 の文言を改めた、(d) = CM 3.6 の版行に `_thread_limit_from_env` を足した。F11 = `create_app` が `thread_limit` を検証し `None` か正整数以外は `ValueError` (起動時に失敗する方が要求ごとの 500 より良い)、両 peer にテスト + 変異。観察 3 件 (同 loop での limiter の上書き、`hold_in_flight` の bound、socket plug の効果) は受理。差し戻し 1 の逸脱 1 (F6 の 2 本目の初版が stage (1) しか通らず M204 が緑 → 背景 thread で届ける形に直して赤) と 2 (122 の一覧の形) は受理。

- **【監督裁定 12 (2026-09-28)】WP-4 のコードレビュー 1 (opus、F1〜F9 + P1、`$SP/review-wp4.md`)**: F1 (client_processes= が算術値)・F2 (141 の既知 CPU の stub 未実装)・F3 (144 の空振り)・F4 (出所・文書名・経緯語)・F6 (`requests=` が算術)・F7 (例外の包み漏れ)・F8 (要求数の上限の注意)・F9 (`_warm_forkserver` の主張) は差し戻し 1 で直した。F5 (group の開始時刻) は採る = 各子が barrier から戻った直後の `time.time_ns()` の最小値 (差し戻し 1、M210)。F2 の実現法 = stub の子が固定回数の busy loop を回し `time.process_time()` の差分を返す (measured の合計と ±20% で一致、warmup 分を含まない)。F6 = 応答数が n×K に満たない run は `RealServerMeasurementFailure`。P1 (指示書外 (a)〜(d) の事後報告) は中身が妥当なので受理。差し戻し 1 の指示書外 1〜4 (F6 の補助テスト、RV1 の形の変更、mutate.py の `--recover`、README のプレースホルダ) と疑義 1 (子の pid は返り値を spy で観測、HTTP 越しの独立経路は D-15 に無いので不採用)・疑義 2 (README に composition root の 600 と adapter の 50 は別と明記) は受理。
- **【訂正註 13 (2026-09-28)】`.github/workflows/ci.yml` の `tools-tests` job を §9.1 の触ってよいパスに足す (監督だけが触る)。** コードレビュー 1 の範囲外の観察: 同 job は pytest しか入れないが、`tools/tests/test_perf_baseline.py` は R-101 WP-1 (5b73b48) 以来 `import httpx` を持ち、WP-4 も子 process で httpx を使う。push 停止中で CI は走っておらず、再開時に collection が赤になる見込みなので、同 job の install を `pip install -c constraints.txt pytest httpx` に改める (tools/ 配下の third-party import は httpx だけ = `grep -rlE '^(import|from) (anyio|httpx|psycopg|starlette|uvicorn)\b' tools/` の実測)。検証は push 再開後の CI に委ねる (`OC` §2 の 20)。

- **【監督裁定 14 (2026-09-28)】コードレビューの再確認 (2 回目、opus) の残件**: WP-3 (`$SP/review-wp3-2.md`) の N1 (fake 死接続テストの決定性: `acquire()` 後に `assert pool._idle.empty()`) と N2 (`create_app` の非 int・bool の拒否 + テスト + 変異 M207/M208) は差し戻し 2 で直した (`1f736b8`)。WP-4 (`$SP/review-wp4-2.md`) の F4 の残り (文書名の無い `D-15:` 16 箇所と裸の「completion condition N」18 箇所)・N1 (道具の 2 箇所の経緯語)・N2 (144 のテストの例外の飲み込み)・N3 (README の「well under」)・観察の `--n 0` (`--real-server` は `--n >= 1`、M211) は差し戻し 2 で直した (`f7a60ac`)。F7 の残り (実在しない module の ImportError と `LauncherStartupError` が traceback のまま) は**観察** (start の失敗は launcher 自身が `stop` するので残骸は出ない。`RM` §0.1 の終了条件に触れず、道具の利用者は監督だけ)。141 のテストが本物の worker の CPU の窓を固定しない点も観察 (F2 の裁定の帰結)。実装の逸脱で裁定の無かったもの — WP-3 第 1 段 (d) 不要 import の削除・(e) `tools/tests` 未実行 (第 2 段で実行)、第 2 段 (b) 見出しコメントの書き換え・(c) README の隣接の誤記 (F10 で直した)、WP-4 第 1 報告の逸脱 (e) 裸の「R-101 WP-4」の除去・疑義 (1) 先頭の確認 1 本 = 予備確認 1 本と読む・疑義 (2) 同一 worktree の順序、差し戻し 2 の逸脱 1 (「20 箇所」は概数で実測 18) — は全て受理 (直す必要なし)。

- **【訂正註 14 (2026-09-28)】§9.1 に両 launcher (`r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py`) を足す (Class B の経路。登録済み helper `_parse_issued_secret` の本体は触らない)。** 監督の D-16 の実測 (tree `d7a7500`) で `--real-server` が両 peer とも `POST /control/v1/credentials -> 403` で止まった。原因 (調査 `$SP/explore-d16-403.md`): launcher の `control_bearer` は `ops bootstrap` の control credential で `must_rotate=true` のまま (r2db `ops.py`:699-700、MitateDB `ops.py`:298)、control plane は must_rotate の間 `control_capabilities` と自己宛て `rotate_credential` しか許さない (r2db `control_plane.py`:1289-1304、MitateDB `control_plane.py`:1460-1473)。自己 rotate は `POST /control/v1/credentials/{credential_id}/rotate` (body 無し、応答 `{"credential_id", "secret"}`) で path の id が自分の id と一致することを要するが、launcher は id を公開せず、bearer からの導出は契約 (`spec/data-service-api.v1.json` の `CredentialIssued.secret`: "A client MUST NOT compose it from, split it into, or derive it from any other field of the response") が禁じる。実装担当は実装せず報告した (OC §1.5 の 37、`$SP/r101-wp4-report-3.md`)。
- **【監督裁定 15 (2026-09-28)】上の閉塞は (a) launcher が `ops bootstrap` の stdout の `credential_id: ` 行を読み property `control_credential_id` で公開する、で解く** (class の method の中に両 peer 同じ文面。module 水準の同名 helper は足さず登録の増減を増やさない)。perf tool は rotate → 新 secret で developer credential 発行 → entity → `query` (runtime bearer) の順。stub に must_rotate ゲート (path の id 不一致 / 旧 secret は 403) を写し、変異 3 件 (rotate を外す、旧 secret で issue、別の id で rotate)。launcher の解析そのものは単体テストを置かず、監督の実 launcher での再計測 (`REALPERF` が出ること) を監査照合とする。C-26 は `control_bearer` を `GET /control/v1/capabilities` にしか使っておらず、この経路は本 WP-4 まで未踏だった (事実)。

- **【監督裁定 16 (2026-09-28)】WP-4 差し戻し 3 (裁定 15 の実装) の再確認 (opus、`$SP/review-wp4-3.md`)**: (i)〜(v) は閉じた (自作変異 RV3 = rotate の bearer を runtime に替える → 赤)。残り N1 (M212 のテストの docstring が赤の理由を取り違え) と N2 (新規 3 テストの完了条件の対応付け「128 相当 (rotate 追加分)」→ 裁定 15 の rotate の手順、164 の側) は差し戻し 4 (docstring のみ) で直した。観察 2 件は受理: run の後の launcher の `control_bearer` は無効になった旧 secret を返し続ける (perf tool は launcher を 1 run で捨てる。C-26 は rotate しない)、launcher は C-26 と共有される経路で本件の conformance の再実行は完了ゲートが担保する。

- **【監督裁定 17 (2026-09-28)】受け入れ監査 (opus、`$SP/acceptance-packet-r101-v11.md`、tree e55c344): 充足 95 / 未充足 0 / 証拠不足 3、観察 5 件。** 観察 1 (中〜高) を**計測器の欠陥として採る**: real-server plug の client の子 process と `httpx.AsyncClient` が group ごとに新しく作られ (`tools/perf_baseline.py`:2194・:2252・:2147)、barrier 後の最初の要求で httpcore の anyio backend が遅延 import される (CPU 6.5〜7.4 ms)。warmup は別 process なので client 側が温まらず、K=1 の分母 (client_processes=1、group = 1 要求) に子の初回コストが入る。D-15 は子の寿命を定めていなかった (設計の穴。本項が D-15 の補足)。**補足 D-15a**: 子 process は (plug, K) ごとに 1 回だけ作り、warmup と measured の全 group を同じ子で送る (client も持ち続ける)。`REALCPU` は measured の区間だけ。差し戻し 5 で直し、D-16 は同じ規則 (§10.1、動かさない) で再計測する。1 回目の D-16 (tree fdb5e61、4.63 / 4.58・4.29 / 4.27 倍) は設計メモ v0.3 §6 に「1 回目 (欠陥のある計測器)」として残し、閉止の可否は再計測で判定し直す (台帳 R-101 行の「閉止 2026-09-28」は再計測の結果で確定または取り消す。R-14 の形で行を残す)。証拠不足 3 件の読み: 162 (接続ピークは MitateDB tests 13 / conformance 59 の 2 suite だけ) → platform pool を構成するのは MitateDB の http adapter だけで、r2db-api/tests と tools/tests はそれを作らないので対象外と読む (充足)。§10.5 の 2 (設計メモ §6 に pg diff の記述無し) → 再計測の記録で run 後の共有クラスタの pg_database/pg_roles 差分 0 を監督が照合して書く。§10.5 の 4 (WO §6.2 の監査欄) → 本項と §6.2 で埋める。観察 2 (D-16 の tree fdb5e61 はゲート前) → 再計測は最終ゲート後の tree で取る (順序を正す)。観察 3 (変異 ID M201〜M208 が WP-3 の JSON / docstring と §9.3 で別の変異を指す) → **訂正註 15**: §9.3 の M201〜M208 は WP-4 の JSON では M201〜M214 のうち該当行に読み替える (対応は `$SP/r101-wp4-mutations-tools.json` の `id` 列。WP-3 の M201〜M208 は `r101-wp3a-mutations-*.json` の追加分で別物)。行を書き換えない。観察 4 (記録の小さな不一致: −51.0 / −51.1 の混在、設計メモ :1957 の根拠は §7.3 D-10 の疑義 (8)、台帳 R-101 行が中間ゲートを引く、§6.1 の裁定 13 が 12 の前に並ぶ) → 前 3 つは直す、並びは記入順のまま (本項に注記)。観察 5 (122 の実装報告の一覧が不完全) → 観察 (報告の不備、テストは在る)。

- **【監督裁定 18 (2026-09-28)】差し戻し 5 (D-15a) の実装の疑義**: (1) 子の measured の CPU 基準は「group ごとに取り直す」(子は warmup / measured を知らない) でよい — 裁定 17 の「親の指示で伝える」と数値は同値で、信号経路が減る。(2) 子の停止は `multiprocessing.Barrier.abort()` + join でよい (sentinel の queue を要求しない)。残 process 0 はコードレビューの再確認で見る。(3) tools/ だけの差分なので `conformance-tests -q` の再実行は完了ゲートに委ねる (§9.4 の列挙は WP-4 全体の道具の引数で、段ごとの必須ではない)。実装後の報告 (指示書外の判断 3 件) は受理。

### 6.2 実施と受け入れ

- **WP-1 (実装担当 sonnet、2 チャットで 4 起動: 前チャットは 1 起動を 3 段継続 (第 1 段 / 第 2 段 + 差し戻し 1 / 差し戻し 2)、再開チャットは条件 26 の段 / 差し戻し 3 / 差し戻し 4 を段ごとに別起動)。** 差分は `git diff a1c1ee3` の 22 file (`security/CONTROL_MAPPING.md` を含む)。`spec/`・`conformance-tests/`・`security/` (CM の参照追随 2 行を除く) の差分 0。
- **コードレビュー**: 1 回目 (前チャット、opus `claude-opus-5-5`、F1〜F10) は差し戻し 2 で全件反映 (F3 は裁定 3)。2 回目 (再開チャット、opus `claude-opus-5-5`、指摘 10 件 + 観察 4 件、`$SP/review2-wp1.md`) は差し戻し 3 で指摘 1〜9 と観察 (a)〜(c) を直し、指摘 10 は裁定 5、観察 (d) は完了ゲート。裁定 1 の 11 行の docstring の現在形・経緯語なしの確認 (file:line) はレビュー報告 `$SP/review2-wp1.md` §0 の表のとおり (両 `psycopg_counting.py` の module / `CountingCursor` / `CountingConnection` / `prepared_stats_skeleton` / `probe_prepared_statements` の 5 箇所ずつ、`credential_store_postgres.py` `_connect` の 1 箇所。全 11 箇所が現在形・経緯語なし)。
- **受け入れ監査** (opus、1 回): 充足 77 / 未充足 0 / 証拠不足 0、観察 5 件 (裁定 8)。完了条件 76 は最終 tree の完了ゲート + `tools/tests` で代替 (裁定 8)。前チャットの変異 JSON は失われたので、監査担当が §2.3 の表から M1〜M63・M100〜M106 を作り直して再現した (`$SP/audit-mutations-*.json`)。差し戻し 4 (O-2 / O-4) の後に最終ゲート (r101b)。
- **完了ゲート** (監督、solo、使い捨てクラスタ) 2 回: 1 回目 (main `0d7065c` を merge した tree `8c56e13`、監査の前) `label r101 gate: 4291 passed, 2 subtests passed in 424.12s (0:07:04)`、judge=PASS、pg_database/pg_roles diff 0 (main 4241 + 本変更セット 50); 2 回目 (main `31f981d` (R-112) を merge し差し戻し 4 を入れた最終 tree `3d10d7d`) `label r101b gate: 4314 passed, 2 subtests passed in 334.79s (0:05:34)`、judge=PASS、pg_database/pg_roles diff 0 (main 4262 + 52)。`tools/tests` (root gate の対象外): `pt: 613 passed in 138.49s`。木の状態の確定 (再開チャット冒頭、WIP `cdd9f9f`): `pt: 611 passed` / `pt: 1502 passed` / `pt: 1493 passed, 2 subtests passed`。
- **変異**: 前チャット M1〜M63・M100〜M106 (変異 JSON は失われ、監査で作り直した)、再開チャット M64/M64b/M64c (条件 26)、M107〜M112 + M100 再実行 (差し戻し 3)、レビュー担当 RV2-T1/T2・RV2-R1/R2・RV2-M1 (T1 = 赤、他 4 件 = 生存 → 差し戻し 3 で赤に)。
- **Class D の証拠**: 依頼者裁定の逐語 (§6.1 冒頭)、コードレビュー 2 回、受け入れ監査 1 回、完了ゲート、conformance の完走 (gate に含む)。版付きの security-contract 決定は該当なし (`security/` は CM の Evidence 参照追随 (3.5) のみ、契約 1.11.0 不変)。
- **WP-2** (監督): 2026-09-27、最終 tree `3d10d7d` の道具と基点 `a1c1ee3` の道具 (detached worktree)。非退行 K=1 3 組 + K=3 1 組 (訂正註 9)、sweep 10 run、ε ≤ 2.9%、δ = 10%。設計メモ v0.2 §2 (逐語 16 run)・§3 (事実 11 項)・§4 (規則ごと・plug ごとの表と判断 6 項)。§3.4 の 1〜7 は充足 (2: 40 行の `thread_limit=` 一致、`LIMIT_EXCEEDED` 欠落なし; 4: 規則の文言は v1.0 と同一; 7: `RM` v1.128 の R-101 / R-84 行)。判定: 4 plug とも J-2 (GIL) 成立、MitateDB は J-5 も成立、J-3 不成立、判定不能なし。§0.1.4 の 2 は 29.5〜33.3 倍で不成立 (R-101 は閉じない)。R-84 の再検討条件は 3 plug で充足。是正 WP は本書 v1.1 で足す (依頼者確認)。

## 7. 枠 (v1.1。是正 WP-3 / WP-4)

§7.1・§7.2・§7.4 は監督の枠 (`$SP/r101-remedy-frame.md` の v1.0 §1.1・§1.2・§1.4) と監督の算術 (`$SP/r101-floor-arithmetic.md` の §1・§2) の**逐語**である (fenced block。改行位置も元のまま)。ただし監督の訂正 2 点 (`$SP/rulings-r101-v11.md`、2026-09-27) を反映してある: limit 4 の MitateDB-http の比は 15.4 ではなく **15.2** (設計メモ §3 の 4。K=1 の分母は limit 4 の run)、MitateDB の production の platform pool を受け取るのは **credential store だけ** (audit sink は production でも pool 無し。§7.5 の (W-9))。算術の見出しは太字の行に下げてある。§7.3 は枠 v1.1 の D-8〜D-16 に、起草時の疑義 (1)〜(10) への監督裁定 (同ファイル) を**本文として組み込んだもの**である。逐語中の「設計メモ」は `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md`、「算術 §2」は §7.1 の 2 つ目の block、「探索 a / 探索 bcd」は監督の scratchpad の調査ノート、「RM」は `docs/design/ROADMAP_POST_PHASE7_V1.md`、「WO v1.1」「作業指示書 v1.1」は本書のこの版を指す。D-N は本書 §1.2 の D-1〜D-7 に続く番号である。行番号は枠の起草時のもので、基点 `2e746cc` での実測は §7.5 に置く。

### 7.1 問題設定 (枠 v1.0 §1.1) と床の算術

```text
- WP-2 の判定: 4 plug とも主体は Python の CPU (GIL)。MitateDB は cell lock 待ちも (R-102)。J-3 (DB 往復) 不成立。
- 閉止形 RM §0.1.4 の 2「K=32 の query p50 が K=1 の 8 倍以内 (両 peer の http / socket plug)」は現状 29.5〜33.3 倍。
- **計測器の床** (算術 §2): perf_baseline の 4 plug は client (httpx / ASGITransport、main thread) と server が同 process・同 GIL。
  group p50(K=32) ≥ 32 × (同一 GIL 上で直列に走る 1 要求あたり CPU)。K=1 の CPU 行 (無競合) から:
  - client だけの床: r2db-http 5.5 / r2db-socket 20.7 / MitateDB-http 1.5 / MitateDB-socket 10.1 倍。
  - client + server CPU の床: 17.7 / 26.0 / 17.7 / 22.0 倍。limit 4 の実測 (19.4 / 32.9 / 15.2 / 20.6) はこの床にほぼ着いている。
  - HTTP も DB も無い in-process plug ですら 13.0 / 14.6 倍 (`_measure_op`: "no real I/O to overlap regardless of concurrency")。
  → **8 倍は、server をどう直しても現行の計測器では出ない。** socket 2 plug は client だけで 8 倍超。asgi 2 plug は server を別 process にできない (ASGITransport 直結)。
- 計測器の忠実度の穴 (探索 bcd Q2): MitateDB の production `main.py` は credential store に `BoundedConnectionPool` を配線するが (audit sink は production でも pool 無し)、http conformance adapter は pool 無し (呼び出しごと `psycopg.connect`、1 要求 2 session、K=1 で connect_wall 4.19 ms/req = p50 6.30 の 66%)。MitateDB plug の K=1 p50 は production の形を表していない。
```

**床の算術** (監督、`$SP/r101-floor-arithmetic.md` §1・§2 の逐語):

```text
出所: docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md §2.2 (thread limit 既定 × K=1 :625-, × K=32 :1213-)。
`query` op。1 要求あたりの値 = 行の値 / requests。

**1. K=1 (既定、無競合) の 1 要求あたり CPU (ms)**

| plug | p50 K=1 | cpu_main/req (client + asgi では app async 層) | cpu_other/req (server 側 worker) | cpu_total/req |
|---|---|---|---|---|
| r2db-http (asgi) | 1.478 | 0.256 | 0.561 | 0.817 |
| r2db-socket | 4.834 | 3.120 | 0.813 | 3.934 |
| MitateDB-http (asgi) | 6.301 | 0.292 | 3.193 | 3.485 |
| MitateDB-socket | 9.869 | 3.119 | 3.682 | 6.800 |
| r2db in-process | 0.116 | 0.064 | 0 | 0.064 |
| MitateDB in-process | 0.135 | 0.083 | 0 | 0.083 |

**2. 床の算術**

group p50(K=32) ≥ 32 × (同一 GIL 上で直列に走る 1 要求あたり CPU)。client (harness の httpx / ASGITransport) は main thread で server と同じ GIL を使い、
重なりようがない (in-process plug は「no real I/O to overlap regardless of concurrency」= tools/perf_baseline.py `_measure_op` docstring)。

| plug | 実測 K=32/K=1 (既定 / limit 4) | client だけの床 = 32 × cpu_main/req ÷ p50(K=1) | client + server CPU の床 = 32 × cpu_total/req ÷ p50(K=1) |
|---|---|---|---|
| r2db-http | 33.3 / 19.4 | 5.5 | 17.7 |
| r2db-socket | 31.8 / 32.9 | 20.7 | 26.0 |
| MitateDB-http | 29.9 / 15.2 | 1.5 | 17.7 |
| MitateDB-socket | 29.5 / 20.6 | 10.1 | 22.0 |
| r2db in-process | 13.0 (1.510/0.116) | — | 17.7 (実測 13.0: K=1 の p50 に group 固定費が乗る) |
| MitateDB in-process | 14.6 (1.967/0.135) | — | 19.7 (実測 14.6) |

読み:
- socket 2 plug: client の CPU だけで 8 倍を超える (20.7 / 10.1)。server をどう直しても (別 process にしても) 現行の計測器では 8 倍以内にならない。
- asgi 2 plug: 8 倍にするには server 側の GIL 保持 CPU を r2db 0.561 → ≤ 0.114 ms/req (1/5)、MitateDB 3.193 → ≤ 1.28 ms/req (1/2.5) に減らす必要がある。
  asgi plug は構造上 server を別 process にできない (ASGITransport 直結)。limiter 縮小は CPU を減らさない (limit 4 で 19.4 / 15.2 = 床に近い)。
- limit 4 の実測は床 (17.7 / 17.7) とほぼ一致 → 「thread 数を減らす」は床まで届いた。残りは床そのもの。
- MitateDB-http の cpu_other/req 3.19 ms のうち platform connect (per-call psycopg.connect ×2、SCRAM) が K=1 で connect_wall 4.19 ms/req (§3 の 7) — CPU の内訳は未計測 (推測: libpq の SCRAM は C 側で GIL を離す → r > 1 の一因)。
```

### 7.2 守るべき条件 (枠 v1.0 §1.2)

```text
(a) 契約 1.11.0 のまま (是正 1 段目)。`limit_enforcement` の適用単位は契約 1.8.0 (`spec/data-service-api.v1.json:303`) が既に配備全体と定め、`process_ceilings` → `enforced` / `deployment_required` の写像がある (フェーズ10 D-5、C-26)。
(b) Security Invariants 不変。in-memory の limit 状態 (r2db `_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES`、MitateDB `_LimitStateHolder`) が process を跨いで偽にならない形だけを採る。
(c) 寸法の変更は P-8 / R-20 の変更セットとして完了ゲートに性能差分を添える。判定規則は計測前に固定 (フェーズ10 U-2、R-101 (e))。
(d) 代理指標を使わない (OC §1.7 の 52): 閉止形は「実並行」そのものを読む形にする。
(e) 公開規律 §1.9。
```

### 7.3 決定 (監督確定。D-8〜D-16。枠 v1.1 + 監督裁定 2026-09-27)

```text
D-8 両 peer の `create_app(...)` に keyword 引数 `thread_limit: int | None = DEFAULT_THREAD_LIMIT` を足す (module 定数 `DEFAULT_THREAD_LIMIT = 4`)。正整数のとき、Starlette の pure-ASGI middleware (`__init__(self, app, thread_limit)`、`async def __call__(self, scope, receive, send)`) を `create_app` が作る Starlette の middleware 列に足す。middleware は要求ごとに実行中の loop を判定し、loop につき 1 回だけ `anyio.to_thread.current_default_thread_limiter().total_tokens = thread_limit` を設定し、以後は素通しする。`None` = middleware を足さない (anyio の既定 40 のまま)。どちらでも create_app の返り値の形は基点と同じ (`RequestByteBoundMiddleware` が Starlette app を包む。app の identity・`.app.state`・`.app.routes` は不変)。middleware class と定数は両 peer に同名・本体同一で置き `_ISOMORPHIC_TARGETS` に登録する (Class D の契機。依頼者への D 宣言の提示は WO v1.1 の確認と同時)。
D-9 composition root: `main.py` の `build_app(env)` が `R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT` を読む。未設定・空文字 → `DEFAULT_THREAD_LIMIT` (4)。それ以外は正整数のみ受け付け、0・負・非数は起動時に失敗する (変数名を含む例外。理由: 資源の寸法であり、黙って既定に落とすと配備者の誤設定が見えない)。文書は両 `main.py` の docstring の env 表、r2db `deploy/env/api.env.example`、MitateDB `docs/cloud-run-cloud-sql.md` の env 一覧 (在れば) に 1 行ずつ。
D-10 harness: 両 http adapter の `DSA_PERF_THREAD_LIMIT` は wrapper を掛けるのをやめ、解析値を `create_app(thread_limit=...)` に渡す。未設定・無効 (空・非数・0 以下) → create_app の既定 (4)、正整数 → その値。`perf_thread_limit()` accessor は create_app に渡した実効値 (int) を返し、`default` ラベルは accessor を持つ plug では出なくなる (WP-1 のテストは実測で更新)。`tools/perf_baseline.py` の側は変えず、accessor を持たない plug (in_process の 2 plug) の `CPU` 行は従来どおり `thread_limit=default` のまま (監督裁定 2026-09-27、疑義 (8) の残り)。WP-1 の adapter wrapper class は削除し `_ISOMORPHIC_TARGETS` から外す (集合の増減 = D)。件数 pin を実測で更新。
D-11 MitateDB http adapter: `_read_store` だけに `BoundedConnectionPool(dsn, max_size=<production と同じ導出 = role_pool_size(FoundationConfig(max_concurrency=<この surface の宣言値>))>)` を配線し、production `main.py` の credential store と同じ形にする (audit sink は production でも pool 無し = `main.py`:343 なので変えない)。isolated surface (`iso`) は浅い複製で同じ store を使う。pool は adapter の `_cleanup` で閉じる (残骸 0)。conformance の挙動は不変 (認証の SQL・例外は同じ)。`BoundedConnectionPool` に「閉じる前の畳み込み」を足す (r2db `_RolePool._fold_closed_connection_stats` と同じ形: 生きている接続の `db_wall_ms` / `txn_count` の現在値 + 閉じた接続の累積、`sessions` / `connect_wall_ms` は `_new_connection` で加算、加算は `_stats_lock` の中、AST 静的 pin 1 箇所)。adapter の `platform_db_time_stats()` は store の pool から読む。`MT78`:474-506 の期待値は実測で更新。adapter のコメントが記す接続枯渇の実測は R-44 (使い捨てクラスタ) 以前のもので、実装担当は suite の実行中の接続のピークを報告し、枯渇が再現したら監督へ上げる (裁定は監督)。
D-12 判定規則 (計測前に固定): 同じ道具・同じ条件 (`DSA_PERF_POOL_SIZE=32`、K=1 `--warmup 10 --n 100`、K=32 `--warmup 3 --n 15`、`DSA_PERF_THREAD_LIMIT` 無し)、基準 = 設計メモ v0.2 §2.2 の既定 run (K=1 :625-、K=32 :1213-)。合格: query p50 (K=32) が 4 plug 中 3 plug 以上で 10% を超えて改善、どの plug も 10% を超えて悪化しない、K=1 の p50 が ±10% 内 (MitateDB 2 plug の K=1 は D-11 で connect が消えるので「悪化しない」だけを見る)。設計メモ v0.3 §5 に逐語。8 倍は WP-3 では判定しない (床)。
D-13 文書化する trade-off: limiter 4 < 宣言 concurrency 32。slot は両 peer とも loop thread で先に取る (r2db `acquire_concurrency_slot`、MitateDB `http.py`:597) ので、thread 待ちの要求も slot を保持し N+1 の拒否 (C-05) は不変、循環待ちは無い。代わりに同期区間 (DB 待ちを含む) を同時に走らせるのは最大 4。env で上書き可。完了条件に「limit 4 で 8 要求を in-flight にして 9 本目が concurrency で拒否され、8 本とも完了する (deadlock 無し)」を置く。既存テストのうち宣言 concurrency の同時到達を試すもの (`r2db-api/tests/test_threadpool_offload.py`:728、pool 寸法の試験) は `create_app(..., thread_limit=None)` を明示する (docstring に 1 文)。limiter 40 を述べる既存コメント (`R2H`:405-424、`MTH`:515 の CH-0202) は事実に合わせて直し、来歴登録 (`docs/code-history/`、`--register`) を同じ変更セットで行う (OC §1.5 の 40c の書き方)。
D-14 テスト (完了条件 1 = 変異 1): create_app の既定で limiter が 4 になる (fresh loop)、None で middleware 無し、返り値の形が基点と同じ、env の厳格 parse (未設定・空 → 4、正整数 → その値、0 / 負 / 非数 → 起動失敗)、adapter の env 有無・無効値で create_app に渡る値、accessor の値、同型性の登録、D-11 の pool 配線 (credential store が per-call で接続を開かない) と pool の畳み込み、D-13 の 8+1。既存テストの `thread_limit=default` の期待は実測で更新。
D-15 `tools/perf_baseline.py` に `--real-server` (peer 名を取る。`registry.json` の `composition_roots` から launcher を読む。registry は読むだけ) を足す。`--real-server` の run は real plug だけを走らせる (registry の adapters は作らない)。手順: `launcher.start(ceilings={"data": 1, "control": 1})` → `control_bearer` で control plane の HTTP (`/control/v1/credentials`) から developer credential を発行し、それで entity と行を作る → `query` op だけを `runtime_bearer` で測る (閉止形は query。K=1 の先頭で 200 と行数 > 0 を確かめる = 空振り禁止) → `launcher.stop()`。launcher は変えない。client は N 個の子 process (`--client-processes`、既定 8。実際の数は N = min(N, K))。各子は group ごとに K/N 本 (余りは先頭の K % N 個の子に 1 本ずつ) を 1 回の `asyncio.gather` で同時に送り、親は `multiprocessing.Barrier` で開始を揃え、group wall = 子の完了時刻 (time.time_ns) の最大 − 開始時刻。warmup/n は既存と同じ引数。既存の行の書式は変えず、新行 `REALPERF peer=<peer> plug=<peer>-real transport=real-server op=query concurrency=<K> client_processes=<N> n=<n> p50_ms= p95_ms=` と、client の CPU を `REALCPU peer= plug= op=query concurrency= client_processes= requests= wall_ms= cpu_client_ms=<子の getrusage 合計>` で出す (床の可視化。判定には使わない)。REALPERF / REALCPU は PERFRUN の後に自身の塊として印字する。server 側の CPU/DBTIME 行は出ない (別 process)。
D-16 閉止の判定規則 (計測前に固定): real-server plug で K=1 と K=32 (`--warmup 3 --n 15`) を取り、K=32 は 2 run 取る。query の p50 の K=32 / K=1 の比が両 peer で K=32 の 2 run とも 8 倍以内 = R-101 閉止 (RM §0.1.4 の 2 の改訂形)。ε (K=32 の 2 run の相対差) と δ = max(10%, 2ε) は記録だけで、判定には使わない。本変更セットでは server は 1 process なので 8 倍は満たさない見込み — その実測を設計メモ v0.3 §6 に逐語で残し、R-113 (multi-process、規模 L) の出発点にする。
```

**D-13 の trade-off (本文)。** anyio の既定 thread limiter は loop ごとに 1 つで、既定 40 (§1.3 の (1))。D-8 はそれを `DEFAULT_THREAD_LIMIT = 4` に下げるので、**limiter (4) は宣言 `concurrency` (両 peer とも既定 32。§7.5 の (W-17)) より小さい**。それでも C-05 の N+1 の拒否は変わらない: 両 peer とも concurrency slot は handler の最初の文として **event loop の thread の上で**取り (r2db `http.py`:460 ほか、MitateDB `http.py`:608 ほか。§7.5 の (W-2))、slot が満ちていれば待たずに拒否する。thread の token を待つ要求は slot を保持したまま待つので、in-flight の数え方と N+1 目の拒否は limiter の大きさに依らない。**循環待ちは無い**: slot の取得は worker thread の token を持たずに loop の上で終わり、worker thread の側が slot を待つ経路は無い。代わりに、**同期区間 (認証・service・psycopg の DB 待ちを含む) を同時に走らせる要求は最大 4** になる (DB 待ちの間も token を持つので、DB が遅いときの実並行は 4 で頭打ちになる)。寸法は composition root の env (`R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT`、D-9) で上書きできる。完了条件 116〜119 (§8.2) がこの 3 つ (N+1 の拒否・8 本の完了・同期区間の同時数 4) を観測する。limiter は `create_app` の middleware 列の中で設定されるので、返り値の形 (app の identity・`.app.state`・`.app.routes`) は変わらない (D-8)。宣言 concurrency の同時到達そのものを試す既存テスト (pool 寸法) は `thread_limit=None` を明示する (D-13)。

### 7.4 却下した代替案 (監督確定、蒸し返さない。枠 v1.0 §1.4)

枠 v1.0 §1.4 の表の逐語。採った 2 行 ((a') = WP-3、(e) = WP-4) を含む。**却下・範囲外は 4 つ**: (a) `main.py` だけに置く案 (perf_baseline の plug が `create_app` を直に呼び `main.py` を通らない)、(b) multi-process worker (本書では起票のみ = R-113、§12)、(c) R-102 (本書に混ぜない)、(d) R-84 async psycopg (J-3 不成立、limit 1 でも CPU は減らない)。

```text
| 候補 | 実測の効き | 触る範囲 / クラス / 規模 | 扱い (監督案) |
|---|---|---|---|
| (a') thread limiter を src の `create_app(..., thread_limit=)` に置き、既定 4、main.py が `<PEER>_THREAD_LIMIT` で上書き。adapter の `DSA_PERF_THREAD_LIMIT` wrapper は create_app 経由に付け替え | p50 −30〜49% (3 plug)、r2db-socket ±0。8 倍には届かない (床) | 両 http.py (create_app) + 両 main.py + 両 http adapter + tests + README。change_class = B (両 peer 同名 helper を登録すれば D、WP-1 と同じ契機)。規模 M | **採る (1 段目)**。main.py に置く案 (a) は perf_baseline の plug が create_app 直呼びで main.py を通らないので却下 (探索 a Q2) |
| (b) multi-process worker | 未計測 (計測器が無い)。GIL の外に出る唯一の候補 | limit 状態の置き場 (in-memory → PostgreSQL 共有) を変えれば `enforced` を保てる (R-18 の (c)、Class B+C)。変えなければ `process_ceilings` > 1 → `deployment_required` に落ちる (宣言値の変更 = C)。規模 L、設計レビュー | **2 段目の候補として起票**。着手は計測器 (下) の後 |
| (c) R-102 cell lock | K=32 で acquire の 47% が待ち | cell.py 4085 行、`with self._lock` 20 箇所、規模 L、設計レビュー | **R-102 のまま** (本 WP に混ぜない)。ただし adapter の pool 無し (忠実度の穴) は本 WP で直す候補 |
| (d) R-84 async psycopg | J-3 不成立。limit 1 (thread 手渡し最少) でも p50 は既定の ±13% 内 = thread を無くしても CPU は減らない | 27 file 約 24k 行、規模 L | **却下** (再検討条件は形式上 3 plug で充足だが、主体が CPU なので効かない。R-84 行に理由を追記) |
| (e) 計測器: perf_baseline に real-server 経路 (registry の `composition_roots` = C-26 launcher で production composition root を subprocess 起動、client は harness process) を足す | 8 倍判定を可能にする前提 | tools + 両 peer conformance/ (launcher 再利用)、registry.json は読むだけ。Class B。規模 M。client の CPU (socket 経路 3.1 ms/req) が別の床になるので K 並列 client (process 分割) を含む | **採る (閉止形の計測器)**。§0.1.4 の 2 の「両 peer の http / socket plug」を「real-server plug」に R-14 の形 (行を残し日付付きで上書き) で改める裁定が要る |
```

### 7.5 起草時の実測 (基点 `2e746cc` の現物。起草者が実施)

略記は §1.3 の `RH` / `RS` / `MH` / `MS` / `PB` / `TPB` に加え、`R2H` = `r2db-api/src/r2db_api/http.py`、`MTH` = `MitateDB-api/src/mitatedb_api/http.py`、`R2M` = `r2db-api/src/r2db_api/main.py`、`MTM` = `MitateDB-api/src/mitatedb_api/main.py`、`RAQ` / `MAQ` = 両 peer の `tests/test_audit_query.py`、`RT78` / `MT78` = 両 peer の `tests/test_r78_pool_wait_stats.py`、`RLS` = `r2db-api/conformance/real_server_r2db.py`、`MLS` = `MitateDB-api/conformance/real_server_mitatedb.py`、`CM` = `security/CONTROL_MAPPING.md`。

| # | 観測 | 出所 |
|---|---|---|
| (W-1) | **`create_app` の署名と本体。** r2db `def create_app(service: DataService, *, lifespan: ... = None) -> ASGIApp` (本体 :738-767、返り値は `RequestByteBoundMiddleware(app, service.limits)` :767)。MitateDB `def create_app(service: HttpService, *, request_bytes_limit: int, lifespan: Any = None) -> ASGIApp` (本体 :1261-1276、返り値は `RequestByteBoundMiddleware(app, request_bytes_limit=...)` :1276)。どちらも thread limit の引数を持たず、両 `src` に `total_tokens` / `CapacityLimiter` を設定するコードは 0 件 (§1.3 の (1) から不変)。`create_app` は `_ISOMORPHIC_TARGETS` に登録されていない。呼び出し元: `R2M`:664 / `MTM`:590 (composition root)、`RH`:1330 / :2531、`MH`:1188 / :2136 (adapter の共有 surface と隔離 surface)、テストは r2db 11 箇所 (7 ファイル)・MitateDB 6 箇所 (3 ファイル) | `R2H`:738-767、`MTH`:1261-1276、`R2M`:664、`MTM`:590、`RH`:1330・:2531、`MH`:1188・:2136 |
| (W-2) | **limiter 40 を述べる既存コメントと slot の位置。** `R2H`:405-424 の塊が「default capacity 40」と「40 > 32」の関係を述べ、`MTH`:515 (`# history: CH-0202` が :516) が「40 threads unless the composition root raises ... which this WP does not do」と述べる。D-8 の後はどちらも事実と合わなくなる。slot は両 peer とも handler の最初の文として loop の thread で取る: r2db `with service.acquire_concurrency_slot():` (`R2H`:460・:482・:494 ほか、実体 `r2db-api/src/r2db_api/service.py`:1056)、MitateDB (`MTH`:608・:633・:647 ほか、実体 `MTH`:501 → `cell.py`:373)。その説明は `MTH`:597-599 (`# history: CH-0206` が :600)。`R2H` には `# history:` の札が無く、`MTH` には在る | `R2H`:405-424・:460・:482・:494、`r2db-api/src/r2db_api/service.py`:1056、`MTH`:501・:515-516・:597-600・:608、`MitateDB-api/src/mitatedb_api/cell.py`:373 |
| (W-3) | **`create_app` / `build_app` の返り値の形を読むテスト。** r2db の tests 5 ファイルが返り値の `.app.state` / `.app.routes` (= `RequestByteBoundMiddleware.app` が Starlette であること) を読む: `test_application_audit.py` 19 行、`test_process_ceilings_declaration.py` 9 行、`test_control_http.py` 3 行 (:585 は data app)、`test_surfaces_env.py` 2 行、`test_credential_persistence.py` 1 行 (control app の `.app.state.control_service` を除いた grep の数。data app の分の内訳は実装担当が実測する)。MitateDB の tests で data app の返り値をこの形で読むものは 0 件 (`test_control_http_unmounted.py` の 3 行は control app)。src の handler の `request.app.state` は Starlette の request が指す app なので返り値の形に依らない | `grep -rn '\.app\.state\|\.app\.routes'` (両 peer の `tests/`)、`r2db-api/tests/test_control_http.py`:585 |
| (W-4) | **composition root の env の読み方。** `R2M` の `_optional_int` (:229-246) は未設定・空・非数を黙って既定に落とす。`_optional_float` (:249-271) は未設定・空なら既定、非空で不正なら `ValueError` (変数名入り) で起動を止める。r2db の `concurrency` は env から読まない (`ResourceLimits()` :434、既定 32 = `r2db-api/src/r2db_api/limits.py`:17)。`MTM` の `_optional_int` (:159-170)・`_optional_float` (:173-) は同形。MitateDB の `MITATEDB_MAX_CONCURRENCY` は `FoundationConfig.from_env` (`MitateDB-api/src/mitatedb_api/config.py`:181-) が読み、未設定なら既定、`int()` できない値 (空文字を含む) と 0 以下は `ValidationError` で止める。`_optional_float` (main.py) は `_ISOMORPHIC_TARGETS` に登録済み (`RAQ`:2410 / `MAQ`:2205)。env の表: `R2M`:30- の docstring「Environment variable contract」、`MTM`:46 付近の docstring。r2db の `DEPLOYMENT_RUNBOOK.md` の env 表は §7 (control-plane、:612-623) で、application-plane の env の一覧は `r2db-api/deploy/env/api.env.example` (`R2DB_PLATFORM_POOL_SIZE` は :107)。MitateDB には env の表を持つ runbook が無い | `R2M`:30・:229-271・:434、`r2db-api/src/r2db_api/limits.py`:17、`MTM`:46・:159-186、`MitateDB-api/src/mitatedb_api/config.py`:181-240、`RAQ`:2410、`MAQ`:2205、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`:612-623、`r2db-api/deploy/env/api.env.example`:107 |
| (W-5) | **WP-1 の adapter の thread limit。** `RH`: `_PERF_THREAD_LIMIT_ENV` :1048、`_perf_thread_limit_value()` :1051-1059 (未設定・空・非数・0 以下は `None`)、`_PerfThreadLimitWrapper` :1062-1087 (loop を `weakref.WeakSet` で覚える)、包む箇所 :1330-1352 (`create_app` の直後、`self._app` と `_build_client` に同じ object)、`perf_thread_limit()` :4218-4222 (`self._perf_thread_limit` を返す)。`MH`: :911 / :914 / :925 / :1188-1207 / :3395-3399 (同形)。`_perf_pool_size` は `RH`:1032 (MitateDB には無い) | `RH`:1032・:1048-1087・:1330-1352・:4218-4222、`MH`:911-950・:1188-1207・:3395-3399 |
| (W-6) | **`_ISOMORPHIC_TARGETS` と件数 pin。** 表は `RAQ`:2393 / `MAQ`:2188。WP-1 の 3 行は `RAQ`:2953-2955 / `MAQ`:2736-2738。件数 pin のテストは `test_isomorphic_target_table_is_pinned_to_its_current_167_rows` (`RAQ`:2973 / `MAQ`:2756)、そのテスト名自体も表に登録 (`RAQ`:2416 / `MAQ`:2211)、pin のテストの中の期待集合に同じ 3 行 (`RAQ`:3338-3340 / `MAQ`:3120-3122)、wrapper の名を挙げる docstring (`RAQ`:3038-3039 / `MAQ`:2820-2821)。件数の assert は `RT78`:377 にも在る (`== 167`)。`CM`:819 (SI-08 Common の Evidence) がこのテスト名を指し、`CM`:5 の版行 3.5 が改名の経緯を述べる (§6.1 の訂正註 3 の前例: 改名で参照が dangling になった)。比較対象は同名の `FunctionDef` / `AsyncFunctionDef` / `ClassDef` / module 水準の `Assign` (§1.3 の (13a)) | `RAQ`:2393・:2416・:2953-2955・:2973・:3038・:3338-3340、`MAQ`:2188・:2211・:2736-2738・:2756・:2820・:3120-3122、`RT78`:377、`CM`:5・:819 |
| (W-7) | **WP-1 の wrapper を対象にする既存テスト。** `RT78`:229-600 (`test_perf_thread_limit_value_*` :238・:245、`test_perf_thread_limit_wrapper_*` :262・:327・:577、accessor :349・:413、登録 :366、env 無しで包まない :393、asgi / socket の同一性 :444・:490) と `MT78`:210-540 (同形)。env 無しの期待 (`perf_thread_limit() is None`、`adapter._app` が wrapper でない) は `RT78`:406・:439、`MT78`:357・:390 | `RT78`:229-600、`MT78`:210-540 |
| (W-8) | **MitateDB の http adapter の platform 接続。** `self._application_durable_audit = PostgresApplicationAuditSink(api_dsn, schema=...)` (`MH`:1152-1154)、`self._read_store = PostgresCredentialStore(api_dsn, pepper=..., schema=..., audit_router=...)` (:1157-1160、`pool` を渡さない)、`self._write_store` (:1161-1164、準備専用)。pool を持たない理由のコメント (`MH`:1117-1137) は「逐次の adapter で idle 接続を持つと共有 cluster の `max_connections` を圧迫し、同じ root suite の `r2db-api-http` のテストが接続枯渇で断続的に落ちた (実測)」と記す (当時。開発機の `max_connections` は現在 300 = `OC` §2 の 3、完了ゲートは使い捨て cluster)。`_cleanup` (`MH`:1297-1315) は `self._read_store.close()` を呼ぶ (:1308) — store の `close()` は pool があれば `closeall()` する (`MitateDB-api/src/mitatedb_api/credential_store_postgres.py`:424-431)。隔離 surface は `copy.copy(self)` の浅い複製で (`MH`:2053)、`_read_store` / `_gate` を共有 surface と共有する (`create_app` は :2136)。共有 surface の `max_concurrency` は既定 32 (`MH`:1086 の `FoundationConfig(...)`、`config.py`:79)、`role_pool_size(config)` は `config.max_concurrency` を返す (`config.py`:300-318) | `MH`:1086・:1117-1164・:1297-1315・:2053・:2136、`MitateDB-api/src/mitatedb_api/credential_store_postgres.py`:232-260・:424-431、`MitateDB-api/src/mitatedb_api/config.py`:79・:300-318 |
| (W-9) | **MitateDB の production の platform 接続。** `platform_pool = BoundedConnectionPool(platform_dsn, max_size=pool_size)` (`MTM`:317。`pool_size` は `pool_size_from_env(MITATEDB_PLATFORM_POOL_SIZE, default=role_pool_size(FoundationConfig(max_concurrency=_declared_concurrency)))` :313-316) を**credential store だけ**が受け取る (`MTM`:420-421 の `pool=platform_pool`)。**audit sink は production でも pool 無し**: `durable_audit = PostgresApplicationAuditSink(platform_dsn, schema=schema)` (`MTM`:343)、class の docstring が「No pooling, one connection per call」(`MitateDB-api/src/mitatedb_api/application_audit.py`:289-300)、`__init__` (:316) は `pool` 引数を持たない | `MTM`:313-317・:343・:420-421、`MitateDB-api/src/mitatedb_api/application_audit.py`:289-316 |
| (W-10) | **`BoundedConnectionPool` の口。** class は `pool.py`:56、接続は `CountingConnection` (:135-142)、`stats()` (:123-133) は 6 鍵 (`size` = `max_size`、`acquire_count`、`wait_count`、`wait_total_ms`、`wait_max_ms`、`in_use_peak`)、`closeall()` は :226。**`db_wall_ms` / `txn_count` / `sessions` / `connect_wall_ms` の累積 (WP-1 の畳み込み) は持たない**。credential store の `platform_stats()` の累積は no-pool の枝の close の前だけで畳み込まれ、pool の枝は対象外 (`credential_store_postgres.py`:336-344)。`MH` の `platform_db_time_stats()` (:3401-3416) は `_read_store` と `_application_durable_audit` の `platform_stats()` の和。既存の `MT78`:474-506 (`test_platform_db_time_stats_observes_a_real_authenticated_http_request`) は 1 要求で `sessions` / `connect_wall_ms` / `db_wall_ms` / `db_calls` が増えることを assert する | `MitateDB-api/src/mitatedb_api/pool.py`:56・:123-142・:226、`MitateDB-api/src/mitatedb_api/credential_store_postgres.py`:336-360、`MH`:3401-3416、`MT78`:474-506 |
| (W-11) | **limiter 4 の下での既存の保持の数。** C-05 の N+1 は隔離 surface の `concurrency` = 3 を `hold_in_flight` で保持する (`conformance-tests/test_c05_limit_declaration_agreement.py`:738、`RH`:970 / `MH`:2102) ので 4 以下。`r2db-api/tests/test_threadpool_offload.py`:728 (`test_role_pool_sized_to_declared_concurrency_avoids_premature_503`) は `create_app` (既定) の app に `concurrency = 6` の要求を 0.6 s ずつ pool の接続を持たせて同時に送り、「pool が宣言 concurrency より小さいと赤」を docstring で主張する (:740)。**limiter 4 の下では同時に pool を持つのは最大 4 本になる**。他の `create_app` を使う既存テストの保持数は 1〜3 (`r2db-api/tests/test_preauth_concurrency_bound.py`、`MitateDB-api/tests/test_preauth_concurrency_bound.py`、`MitateDB-api/tests/test_application_plane_limits.py`:421-436) | `conformance-tests/test_c05_limit_declaration_agreement.py`:738、`RH`:970、`MH`:2102、`r2db-api/tests/test_threadpool_offload.py`:728-776 |
| (W-12) | **`tools/perf_baseline.py` の骨。** `_load_registry` (`PB`:183-185) は `data["adapters"]` だけを返す。`_run_concurrent` (:585-620) は group ごとに 1 回の `asyncio.gather` を `time.perf_counter()` で挟む。`_measure_op` は :754-。`PERF` 行の書式は `_format_row` (:883-894)、印字は `_run` の中 (:1845。plug の 4 op の後)。`main` (:1859-1888) は `dsa_testpg.suite_lock(exclusive=True, ...)` (:1869) → `dsa_testpg.cluster()` (:1871) → cluster の env を `os.environ` に入れて `_run` を呼び、lock が取れないと `REFUSED` を返す。引数は `_build_parser` (:1763-1809: `--n` / `--warmup` / `--concurrency` / `--registry` / `--prepared-detail` / `--roundtrip`)。`multiprocessing` は import していない (:85-100) | `PB`:85-100・:183-185・:585-620・:754・:883-894・:1763-1809・:1821-1888 |
| (W-13) | **`TPB` の既存 pin。** 書式: `PERF` :199、`POOL` :215・:235、`PREPARED` :288、`ROUNDTRIP` :625・:640、`CPU` :1305、`DBTIME` :1324・:1340。並び: :391 (`POOL` → `PREPARED`)、:1019 (`PREPARED` → `ROUNDTRIP conn=`)、:1624 (`CPU` が先頭)。lock と cluster: :428 (`test_perf_baseline_takes_the_exclusive_lock_and_uses_its_own_cluster`)、env の復元 :518・:576。既定値: :183・:279・:1261 | `TPB`:183-1340・:1624 |
| (W-14) | **`registry.json` の `composition_roots`。** 2 件 (`{"name": "r2db-api", "module": "real_server_r2db", "launcher_class": "RealServerR2db"}`、`{"name": "MitateDB-api", "module": "real_server_mitatedb", "launcher_class": "RealServerMitateDB"}`)。発見は `conformance-tests/conftest.py`:311-344 (`<name>/conformance` を `sys.path` に足して module を import し class を取る。instance は作らない) | `conformance-tests/registry.json`:10-21、`conformance-tests/conftest.py`:311-344 |
| (W-15) | **launcher の口。** `RLS`: `start(self, *, ceilings)` :601-697 (初回に使い捨て platform と application `c26app` を provision し runtime credential と control credential を発行 :515-535 → `declare-surfaces` / `declare-process-ceilings` の ops CLI → `r2db_api.main:app` と `control_main:app` の 2 つの uvicorn subprocess → 前段の nginx → readiness。失敗時は `stop()` まで走る)、`stop()` :774-806 (冪等。process を止め、prefix の DB / role を掃き、prefix lock を解く)、`data_base_url` :811、`runtime_bearer` :821、`control_bearer` :826。admin DSN は env `R2DB_TEST_ADMIN_DSN` (:153・:176-184) = `dsa_testpg.R2DB_DSN` (`tools/testpg/dsa_testpg.py`:94)。`MLS`: `start` :550、`stop` :704、`data_base_url` :735、`runtime_bearer` :745、`control_bearer` :750、admin DSN は `MITATEDB_TEST_ADMIN_DSN` (:91 = `dsa_testpg.py`:95)、runtime credential は store から発行 (:447-454)。subprocess の `PYTHONPATH` は launcher 自身が明示する (`_with_pythonpath`、`RLS`:105 / `MLS`:101。`OC` §2 の 17) | `RLS`:105・:153・:176-184・:477-535・:601-697・:774-830、`MLS`:91・:101・:447-454・:550・:704・:735-752、`tools/testpg/dsa_testpg.py`:94-95 |
| (W-16) | **C-26 の smoke が runtime bearer でできること。** `tools/deploy_smoke.py` は 3 段 (capabilities / catalog / catalog の最初の entity への query) で、**entity を作らない**。C-26 は `--allow-empty-catalog` を付けて呼ぶ (`conformance-tests/test_c26_composition_root.py`:53-75、:99) — launcher の application の catalog は空である (launcher は schema を作らない)。契約では `/v1/schema/operations` の roles は `developer` だけ、query は `runtime` / `developer`、control の `issue_credential` (`/control/v1/credentials`) は `control` (`spec/data-service-api.v1.json` の `endpoints` / `control_endpoints`) | `tools/deploy_smoke.py`:1-60、`conformance-tests/test_c26_composition_root.py`:53-75・:99、`spec/data-service-api.v1.json` |
| (W-17) | **real server の既定の bound。** r2db `concurrency` 32、`requests_per_minute` 600 (`r2db-api/src/r2db_api/limits.py`:17-18)。MitateDB `max_concurrency` 32、`max_requests_per_minute` 600 (`config.py`:78-79)。K=32 で `--warmup 3 --n 15` の要求数は `(3 + 15) × 32 = 576` (entity の用意の要求は別) | `r2db-api/src/r2db_api/limits.py`:17-18、`MitateDB-api/src/mitatedb_api/config.py`:78-79 |
| (W-18) | **変更クラスの実測。** WP-3 のパス (両 `http.py`・両 `main.py`・`MitateDB-api/src/mitatedb_api/pool.py`・両 http adapter・両 `tests/test_threadpool_offload.py`・両 `tests/test_audit_query.py`・両 `tests/test_r78_pool_wait_stats.py`・`MitateDB-api/tests/test_r79_prepared_stats.py`・`MitateDB-api/tests/test_main.py`・`tools/PERF_BASELINE_README.md`・`r2db-api/deploy/env/api.env.example`・`MitateDB-api/docs/cloud-run-cloud-sql.md`・`docs/code-history/MitateDB-api/http.md`) を `python3 tools/change_class.py` に渡すと `class=B` / `conformance_required=true` (`.md` の 3 本が A、`api.env.example` を含む残りが B)。WP-4 のパス (`tools/perf_baseline.py`・`tools/tests/test_perf_baseline.py`・`tools/PERF_BASELINE_README.md`) は `class=B` / `conformance_required=true`。`security/CONTROL_MAPPING.md` 単独は `class=D`。道具はパスだけで判定し `_ISOMORPHIC_TARGETS` の集合の増減を検出しない (§1.3 の (13)) | `tools/change_class.py` (実行) |
| (W-19) | **`CM` が行番号で指す箇所 (WP-3 が触るファイル)。** `R2H`:228・:296・:407・:445・:649・:696、`MTH`:102・:127・:178・:494・:506・:1228、`R2M`:482、`MTM`:237。登録の検査は行番号がファイルの範囲内にあることを見るだけで、指す内容は見ない (`conformance-tests/test_control_mapping_register.py`:70-72)。adapter・`tools/`・`RT78` / `MT78` を行番号で指す主張は 0 件 | `CM` (grep)、`conformance-tests/test_control_mapping_register.py`:70-72 |

### 7.6 WP の順序と触るファイルの重なり

WP-3 (§8.1) と WP-4 (§9.1) が触るファイルの重なりは **`tools/PERF_BASELINE_README.md` の 1 本**である (他は 0)。したがって両 WP はそのままでは並行 worktree にできない (`OC` §1.2 の 16・17)。順序は枠 v1.0 §1.6 の 2 のとおりどちらが先でもよい。§10 の再計測は、D-12 が WP-3 の後、D-16 が WP-3 と WP-4 の両方の後である。

## 8. WP-3 — thread limiter を `create_app` の middleware に置き (既定 4)、composition root の env で上書きし、MitateDB の http adapter の credential store に platform pool を配線する (実装担当)

**目的**: production の寸法として anyio の既定 thread limiter を `create_app` の middleware で 4 に下げ (D-8)、composition root の env で上書きでき (D-9)、harness の `DSA_PERF_THREAD_LIMIT` がその同じ引数を通る (D-10) 形にする。MitateDB の http adapter の credential store を production と同じ pool 配線にし、pool の DB 時間を `DBTIME scope=platform` に残す (D-11)。**R-101 は本 WP では閉じない** (D-12 は改善の判定、8 倍は §10 の D-16)。

**読むべき正本**: 本書 §7.1〜§7.3 (問題設定・守る条件・D-8〜D-16 と D-13 の trade-off)、§7.4 (却下案)、§7.5 (実測。とくに (W-1)〜(W-11)・(W-18)・(W-19))。v1.0 の §1.3 の (1)・(3)・(4)・(13a)・(19)・(20) と §6.1 の監督裁定 3・5 (統計専用 lock の AST pin の前例) は前提として有効。規律は `OC` §1.3〜§1.6・§1.10、同型性は `OC` §1.5 の 38、件数・行番号を固定する静的テストは同 40b、コメントの書き換えは同 40c。

**変更クラス**: パス上 B、全体 **D** (§0 の v1.1 行。提示待ち)。登録済み helper (`perf_thread_limit`、`_perf_thread_limit_value`) の本体に触れるときは `RM` §9 の 8 の C の行にも当たる (全体は D のまま)。**使用テンプレート**: `ROLE_PROMPT_TEMPLATES.md` の 2 (実装)。規模 M (`OC` §1.13 の 74)。

### 8.1 触ってよいパス

**D-8・D-13 (src、両 peer)**

- `r2db-api/src/r2db_api/http.py` / `MitateDB-api/src/mitatedb_api/http.py` — module 定数 `DEFAULT_THREAD_LIMIT = 4`、pure-ASGI middleware class (両 peer で同名・本体同一。`__init__(self, app, thread_limit)`、`async def __call__(self, scope, receive, send)`、要求ごとに実行中の loop を判定し loop につき 1 回だけ `anyio.to_thread.current_default_thread_limiter().total_tokens` を設定し以後は素通し。loop の覚え方は §7.5 の (W-5) の WP-1 の wrapper と同じ `weakref.WeakSet`)、`create_app` の keyword 引数 `thread_limit: int | None = DEFAULT_THREAD_LIMIT` (正整数 = Starlette の middleware 列に足す、`None` = 足さない)、`create_app` の docstring (現在形で D-13 の trade-off を述べる)。**返り値の形 (`RequestByteBoundMiddleware` が Starlette app を包む。identity・`.app.state`・`.app.routes`)、各 handler、評価順 (BYTE BOUND → CONCURRENCY SLOT → AUTHENTICATION → …)、`run_in_threadpool` の呼び方は変えない。** limiter 40 を述べる既存コメント (`R2H`:405-424 の塊、`MTH`:515 の CH-0202 の塊。§7.5 の (W-2)) は事実 (既定 4、env で上書き) に合わせて直す (`OC` §1.5 の 40c の書き方: 現在形、経緯語なし)。同名で両 peer に置く class・定数は `OC` §1.5 の 38 に従い `_ISOMORPHIC_TARGETS` に登録する。
- `docs/code-history/` — 上の既存コメントの書き換えと、来歴検査 (`python3 tools/check_comment_provenance.py --register`) が求める記録 (同じ変更セットで行う。D-13)。

**D-9 (composition root、両 peer)**

- `r2db-api/src/r2db_api/main.py` / `MitateDB-api/src/mitatedb_api/main.py` — `build_app(env)` が `R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT` を読み、未設定・空文字なら `DEFAULT_THREAD_LIMIT`、正整数ならその値を `create_app(..., thread_limit=...)` に渡し、0・負・非数は起動時に失敗させる (変数名を含む例外)。docstring の env の表に 1 行。**他の env の読み方 (`_optional_int` の寛容側を含む)・`build_app` の他の手順は変えない。** 両 peer に同名の helper を置くときは `OC` §1.5 の 38 に従い登録する。
- `r2db-api/deploy/env/api.env.example` — `R2DB_THREAD_LIMIT` の 1 行 (既定の説明付き、値は例示のみ)。
- `MitateDB-api/docs/cloud-run-cloud-sql.md` — env の一覧が在ればそこに `MITATEDB_THREAD_LIMIT` の 1 行。在るか無いか (と在ればその位置) を報告に書く。

**D-10 (harness、両 peer の http adapter)**

- `r2db-api/conformance/conformance_adapter_r2db_http.py` / `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` — `_PerfThreadLimitWrapper` を削除し、`create_app` の呼び出し (§7.5 の (W-5) の 1 箇所) に `DSA_PERF_THREAD_LIMIT` の実効値を `thread_limit=` で渡す (未設定・無効は `DEFAULT_THREAD_LIMIT`、正整数はその値)。`perf_thread_limit()` はその実効値 (int) を返す。`self._app` と `_build_client(...)` と socket plug の data surface が同じ object を受け取る形 (§1.3 の (3)・(4)) は保つ。**登録済み helper `_build_client` / `_surfaces_value` / `_reset_surface_state` / `_live_pg_backend_count` の本体、隔離 surface の `create_app` の呼び出し (`RH`:2531・`MH`:2136) の引数、`_perf_pool_size`・`pool_stats()` は変えない。**
- `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` のみ (D-11) — `BoundedConnectionPool(api_dsn, max_size=role_pool_size(FoundationConfig(max_concurrency=self._application_config.max_concurrency)))` を作って adapter が保持し、それを `self._read_store` に渡すこと (production の `MTM`:313-317・:420-421 と同じ導出)、`platform_db_time_stats()` の credential store の分をその pool の読みだけの統計から取ること (audit sink の分は従来どおり store の累積)、pool を持たない理由を述べる既存コメント (`MH`:1117-1137) を事実に合わせること。`_cleanup` は既に `self._read_store.close()` を呼ぶ (§7.5 の (W-8))。**`self._application_durable_audit`・`self._write_store`・認証の SQL と例外・`_AuthGate` は変えない。**
- `r2db-api/conformance/conformance_adapter_r2db_socket.py` / `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` — **触らない** (identity の振り分けで同じ app を受け取る)。

**D-11 (src、MitateDB のみ)**

- `MitateDB-api/src/mitatedb_api/pool.py` — `BoundedConnectionPool` に「閉じる前の畳み込み」を足すこと: `_new_connection` の `CountingConnection.connect` の前後の connect の wall と回数 (`connect_wall_ms` / `sessions`) の累積、接続を閉じる側 (`discard`・`closeall`、ほかに pool が接続を閉じる経路が在ればそれも) が close の**前に**その接続の `db_wall_ms` / `txn_count` / `execute_count + executemany_count` を累積へ足すこと、累積の加算を既存の `self._stats_lock` の中で行うこと、「生きている接続の現在値 + 累積」を DB 往復なしで返す読みだけの method (返す鍵は store の `platform_stats()` と同じ 5 つ: `sessions` / `connect_wall_ms` / `db_wall_ms` / `txn_count` / `db_calls`。`acquire()` を通らない = `stats()["acquire_count"]` を動かさない)。形は r2db `_RolePool._fold_closed_connection_stats` (§6.1 の監督裁定 3) と同じ。**`max_size`・acquire の timeout・待ちの枝・`self._lock`・例外の型と文言・既存の `stats()` の 6 鍵は変えない。既存の `self._lock` を fast path に足さない。** 既存の静的検査 (`tools/tests/test_sql_statement_safety_scan.py`:281 が `pool.py` を走査する) は緑のまま (SQL を足さない)。

**テスト (既存ファイルに足す。新規テストファイルは作らない)**

- `r2db-api/tests/test_threadpool_offload.py` / `MitateDB-api/tests/test_threadpool_offload.py` — D-8 の単体テスト (fresh loop・同じ loop・別 loop・middleware の `__call__`・返り値の形・`None`・明示値) と D-13 の 8+1。r2db の D-9 のテストもここに置く (既存の composition root のテストが :649 に在る)。**r2db の :728 (`test_role_pool_sized_to_declared_concurrency_avoids_premature_503`) は `create_app(..., thread_limit=None)` を明示し、docstring に 1 文 (宣言 concurrency の同時到達を試すので limiter を外す旨) を足す** (D-13)。
- `MitateDB-api/tests/test_main.py` — MitateDB の D-9 のテスト。
- `r2db-api/tests/test_r78_pool_wait_stats.py` / `MitateDB-api/tests/test_r78_pool_wait_stats.py` — WP-1 の adapter wrapper を対象にする既存テスト (§7.5 の (W-7)) を src の middleware と D-10 の形に改め (env 無し・無効の期待は `4` に変わる)、D-10・D-11 の adapter のテストを足す。`RT78`:377 の件数 assert と `MT78`:474-506 の期待値を実測で改める。
- `MitateDB-api/tests/test_r79_prepared_stats.py` — `BoundedConnectionPool` の畳み込みの実 PostgreSQL のテストと、畳み込みが `self._stats_lock` の `with` の内側に在ることを固定する AST 静的 pin 1 本 (既存の登録済み helper `_find_with_lock_body` ほか (§6.1 の監督裁定 5) を使う。helper の本体は変えない)。
- `r2db-api/tests/test_audit_query.py` / `MitateDB-api/tests/test_audit_query.py` — `_ISOMORPHIC_TARGETS` に src の middleware class の行 (と 38 が掛かる他の同名 helper・定数の行) を足し、WP-1 の `_PerfThreadLimitWrapper` の行を外し、件数 pin・pin のテストの期待集合・wrapper の名を挙げる docstring (§7.5 の (W-6)) を実測で改める。**他の行と他のテストは変えない。**

**文書**

- `tools/PERF_BASELINE_README.md` — `DSA_PERF_THREAD_LIMIT` の意味の変化 (未設定・無効は `create_app` の既定 4 であり anyio の 40 ではない、正整数はその値、`-http` / `-socket` plug の `CPU` 行の `thread_limit=` は常に整数) と、MitateDB の `DBTIME scope=platform` の credential store の分が pool の畳み込みから来ること (`sessions` は pool が新しく開いた接続の数)、env を残したまま pytest を走らせない旨 (既存) を事実に合わせる。

**監督だけが触る**

- `security/CONTROL_MAPPING.md` — (i) 件数 pin のテスト名が変わるとき `CM`:819 の参照と版行を追随させる (§6.1 の訂正註 3 の前例)、(ii) §7.5 の (W-19) の行番号の指す先がずれたとき追随させる。Control 主張は変えない (枠「記録」の「参照追随のみ」)。触れば Class D の経路 (`RM` §9 の 8)。
- `conformance-tests/COLLECTION_FLOOR` — 完了ゲートで前回 main の実測値に合わせる (§6.1 の訂正註 11 の前例、`OC` §1.3 の 25)。

**これ以外は 0 件。** とくに `spec/`・`conformance-tests/` (registry・`socket_harness.py`・launcher の呼び出し側を含む)・`security/` (上の監督分を除く)、両 peer の `service.py`・`limits.py`・`config.py`・`cell.py`・`credential_store*.py`・`application_audit.py`、両 launcher (`real_server_*.py`)、`tools/perf_baseline.py`・`tools/tests/` (WP-4)、`RM` と設計メモ (監督) を触らない。**既存の検査やテストが新しい既定 (limiter 4) で赤になったら、上に名指しした更新以外は直さず報告する** (`OC` §1.5 の 37)。

**書き方**: 新規の `src` コメント・docstring は現在形で書き、フェーズ・WP・R-番号などの経緯語を書かない (§1.2 の D-7 と同じ)。主張は変異の結果を得た後に書く (`OC` §1.5 の 34)。

### 8.2 完了条件 (61 件。番号は §2.2 の続き。152〜163 は監督裁定 (2026-09-27) で足した行で、表では 125 の後に置く。WP-3 の最後の完了条件は 126)

「fresh loop」は `asyncio.new_event_loop()` で作り、まだ既定 limiter を参照していない loop を指す。「1 回呼ぶ」は http scope の最小の要求 (例: `GET /v1/capabilities`) を 1 回通すことを指す。

| # | 完了条件 |
|---|---|
| 78 | **(D-8)** r2db の `create_app(service)` (引数省略) の返り値を fresh loop 上で 1 回呼ぶと、**その loop の** `anyio.to_thread.current_default_thread_limiter().total_tokens` が 4 (= `DEFAULT_THREAD_LIMIT`) である |
| 79 | **(D-8)** MitateDB について 78 と同じ |
| 80 | **(D-8)** r2db の `create_app(service, thread_limit=None)` の返り値の Starlette app の middleware 列 (`.app.user_middleware`) に limiter の middleware class が無く、それを fresh loop 上で 1 回呼んでもその loop の `total_tokens` は 40 のままである |
| 81 | **(D-8)** MitateDB について 80 と同じ |
| 82 | **(D-8)** r2db の `create_app(service, thread_limit=7)` の返り値を fresh loop 上で 1 回呼ぶと、その loop の `total_tokens` が 7 である |
| 83 | **(D-8)** MitateDB について 82 と同じ |
| 84 | **(D-8)** r2db の middleware は同じ loop では 1 回だけ設定する (1 回目の後にその loop の `total_tokens` を別の値へ戻し、2 回目の後もその値のままである) |
| 85 | **(D-8)** r2db の middleware は loop ごとに設定する (loop A で 1 回呼んだ後、別の fresh loop B で初めて呼ぶと B の `total_tokens` も設定値になる) |
| 86 | **(D-8)** MitateDB について 84 と同じ |
| 87 | **(D-8)** MitateDB について 85 と同じ |
| 88 | **(D-8)** r2db の middleware class の `__call__` が coroutine function である (`inspect.iscoroutinefunction`。pure-ASGI middleware の形) |
| 89 | **(D-8)** MitateDB について 88 と同じ |
| 90 | **(D-8)** r2db の `create_app(service)` (既定) の返り値の形が基点と同じ: 返り値は `RequestByteBoundMiddleware` の instance で、その `.app` が Starlette app、`.app.state.service is service`、`.app.routes` の path の集合が `create_app(service, thread_limit=None)` のものと等しい |
| 91 | **(D-8)** MitateDB について 90 と同じ |
| 92 | **(D-9)** r2db の `build_app(env)` を `R2DB_THREAD_LIMIT` 未設定の env で作り、返り値を fresh loop 上で 1 回呼ぶと、その loop の `total_tokens` が 4 である |
| 93 | **(D-9)** r2db で `R2DB_THREAD_LIMIT=6` のとき、同じ観測で `total_tokens` が 6 である |
| 94 | **(D-9)** r2db で `R2DB_THREAD_LIMIT=0` のとき、`build_app(env)` が例外で止まり、例外の文言が変数名 `R2DB_THREAD_LIMIT` を含む |
| 95 | **(D-9)** r2db で `R2DB_THREAD_LIMIT=-3` のとき、94 と同じく止まる |
| 96 | **(D-9)** r2db で `R2DB_THREAD_LIMIT=abc` のとき、94 と同じく止まる |
| 97 | **(D-9)** MitateDB (`MITATEDB_THREAD_LIMIT`) について 92 と同じ |
| 98 | **(D-9)** MitateDB について 93 と同じ |
| 99 | **(D-9)** MitateDB について 94 と同じ |
| 100 | **(D-9)** MitateDB について 95 と同じ |
| 101 | **(D-9)** MitateDB について 96 と同じ |
| 102 | **(D-10)** r2db の `-http` plug を `DSA_PERF_THREAD_LIMIT` 無しで作ると `perf_thread_limit()` が 4 を返す |
| 103 | **(D-10)** MitateDB について 102 と同じ |
| 104 | **(D-10)** r2db の `-http` plug を `DSA_PERF_THREAD_LIMIT=5` で作り、data plane に 1 要求を通した後、`adapter._loop` の既定 limiter の `total_tokens` が 5 である |
| 105 | **(D-10)** MitateDB について 104 と同じ |
| 106 | **(D-10)** r2db の `-http` plug を `DSA_PERF_THREAD_LIMIT=5` で作ると `perf_thread_limit()` が 5 を返す |
| 107 | **(D-10)** MitateDB について 106 と同じ |
| 108 | **(D-10)** r2db の `-http` plug で、`adapter._app` が `create_app` の返した object そのもので、asgi client が叩く app と `-socket` plug の data surface に渡る app が同じ object である (uvicorn を起動せず identity で観測してよい) |
| 109 | **(D-10)** MitateDB について 108 と同じ (`-socket` plug では `_socket_surfaces` の data-plane の surface の `app`) |
| 110 | **(D-8・`OC` §1.5 の 38)** 両 peer の `_ISOMORPHIC_TARGETS` に src の middleware class の行が在り、同型性テスト (`RAQ` の `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` と MitateDB 側の対応テスト) が緑である |
| 111 | **(D-10・D-14) 監査照合**: 両 adapter に `_PerfThreadLimitWrapper` の出現が 0 件、両 `_ISOMORPHIC_TARGETS` から同名の行が外れ、足した行・外した行の一覧と件数 pin の新しい値 (実測) が一致し、`RT78`:377 の件数 assert が同じ値である。件数が変わってテスト名が改まったときは、監督が `CM`:819 と版行を追随させたことを `conformance-tests/test_control_mapping_register.py` の `pt.py` の集計行で示す。照合対象は `git diff` (両 `tests/test_audit_query.py`・両 adapter・`RT78`) と集計行 |
| 112 | **(D-11)** MitateDB の `-http` plug で、1 本目の要求の後に 2 本目の認証済み要求を通すと、adapter が保持する pool の畳み込みの `sessions` の差分が 0 で、pool の `stats()["acquire_count"]` が増える (credential store が要求ごとに接続を開かない) |
| 113 | **(D-11)** MitateDB の `-http` plug の `_read_store` の pool の `stats()["size"]` が `role_pool_size(FoundationConfig(max_concurrency=adapter._application_config.max_concurrency))` と等しい |
| 114 | **(D-11)** MitateDB の `-http` plug で要求を通して pool に接続を持たせた後 `close()` すると、pool が保持していた接続がすべて閉じている (取り出して記録した接続 object の `closed` が真、または `pg_stat_activity` に adapter の `svc_api` role の接続が 0) |
| 115 | **(D-11) 監査照合**: 隔離 surface が共有 surface と同じ `_read_store` を使う (`MH`:2053 の浅い複製。`isolated_application_surface()` の `_read_store` が共有 surface のものと `is` で一致することを 1 行で観測し、出力を報告に残す)。`MH` の認証の SQL・例外・`_AuthGate`・`_write_store` の差分 0 行。完了条件 125 の `conformance-tests -q` が緑 (conformance の挙動は不変) |
| 116 | **(D-13)** r2db で `concurrency` 8 の service を `create_app` (既定 = limiter 4) で包み、同期区間で止まる要求を 8 本 in-flight にした状態 (service の in-flight の数が 8) で 9 本目を送ると、9 本目が `LIMIT_EXCEEDED` (class `concurrency`、429) で拒否される |
| 117 | **(D-13)** 116 の状態で止めを解くと 8 本とも 200 で完了し (待ちの上限を置き、deadlock しない)、その間に同期区間を同時に走っていた要求の数の最大が 4 である |
| 118 | **(D-13)** MitateDB (`max_concurrency` 8) について 116 と同じ |
| 119 | **(D-13)** MitateDB について 117 と同じ |
| 120 | **(D-13) 監査照合**: 両 peer の `create_app` の docstring (と middleware class の docstring) が、limiter 4 < 宣言 `concurrency`、slot が loop の thread で先に取られること、N+1 の拒否が不変であること、同期区間の同時数が最大 4 であること、env で上書きできることを現在形で述べる。照合対象は `file:line` と、116〜119 のテスト名 (主張は実測の後。`OC` §1.5 の 34) |
| 121 | **(D-9・D-10・D-11) 監査照合**: 両 `main.py` の docstring の env の表、`r2db-api/deploy/env/api.env.example`、`MitateDB-api/docs/cloud-run-cloud-sql.md` の env の一覧 (在れば。無ければその旨) に `R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT` の 1 行 (未設定・空は 4、正整数のみ、他は起動失敗) が在り、`tools/PERF_BASELINE_README.md` の `DSA_PERF_THREAD_LIMIT` と MitateDB の `scope=platform` の記述が D-10・D-11 の事実に合っている。`python3 tools/check_doc_refs.py` が 0 dangling |
| 122 | **監査照合**: 本体を変えた既存テストの一覧 (ファイル・テスト名・変えた assert・理由) を報告に残す。§8.1 に名指しした更新 (§7.5 の (W-6)・(W-7)) 以外の既存テストの本体の差分が 0 行。赤になって直さなかった既存テストがあれば、その test id と失敗の要旨を報告に残す (`OC` §1.5 の 37) |
| 123 | **(D-13・D-7 と同じ書き方) 監査照合**: limiter 40 を述べる既存コメント (`R2H`:405-424、`MTH`:515 の CH-0202) が事実 (既定 4、env で上書き) に合わせて直され、`docs/code-history/` に同じ変更セットで登録されている。`python3 tools/check_comment_provenance.py --base 2e746cc <触った src の全パス>` の FAIL が**登録した行以外 0 行**で (FAIL 行を逐語で報告に残す)、`--register` が緑。書き方は `OC` §1.5 の 40c (現在形、経緯語なし)。**worktree を cwd にして走らせる** |
| 124 | **監査照合**: `python3 tools/change_class.py <触った全パス>` の出力 (パスの判定は B。宣言クラス D の契機は 110・111 の集合の増減で、道具は検出しない — §7.5 の (W-18)) と、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged。ホスト名・実 DSN・作業機の絶対パスを新規の文書・テスト・コメントに書いていない (`OC` §1.9、§2 の 13) |
| 125 | **監査照合**: 報告前に `r2db-api/tests -q`・`MitateDB-api/tests -q`・`tools/tests -q`・`conformance-tests -q` を**各 1 回**回して緑 (`conformance_required=true`)。集計行を逐語で報告に残す (**完了ゲートは監督**) |
| 152 | **(D-9)** r2db で `R2DB_THREAD_LIMIT` が空文字のとき、92 と同じ観測で `total_tokens` が 4 である (起動は失敗しない) |
| 153 | **(D-9)** MitateDB (`MITATEDB_THREAD_LIMIT` が空文字) について 152 と同じ |
| 154 | **(D-10)** r2db の `-http` plug を `DSA_PERF_THREAD_LIMIT=0` (無効値) で作ると `perf_thread_limit()` が 4 を返し、data plane に 1 要求を通した後の `adapter._loop` の既定 limiter の `total_tokens` が 4 である |
| 155 | **(D-10)** MitateDB について 154 と同じ |
| 156 | **(D-11)** 実 PostgreSQL の `BoundedConnectionPool` が新しい接続を 1 本開くと、pool の畳み込みの `sessions` がちょうど 1、`connect_wall_ms` が 0 より大きく増える |
| 157 | **(D-11)** 実 PostgreSQL で pool の接続に往復を積んだ後、その接続を `discard` で閉じても、pool の「生きている接続の現在値 + 累積」の `db_wall_ms` / `txn_count` / `db_calls` が閉じる前の値から減らない |
| 158 | **(D-11)** 157 と同じことが `closeall` で閉じたときにも成り立つ |
| 159 | **(D-11)** pool の読みだけの統計の method を呼んでも、pool の `stats()["acquire_count"]` と各接続の `execute_count` / `db_wall_ms` が変わらない (DB 往復 0) |
| 160 | **(D-11・v1.0 §1.1 の (b))** pool の累積への加算が `self._stats_lock` の `with` の内側に在る (AST 静的 pin 1 本。§6.1 の監督裁定 3 の前例) |
| 161 | **(D-11)** MitateDB の `-http` plug で data plane に 1 要求を通すと、`platform_db_time_stats()` の `db_wall_ms` と `db_calls` が要求の前より増える (pool の接続の分が合計に入っている。`MT78`:474-506 を実測で改めたもの) |
| 162 | **(D-11) 監査照合**: §8.4 の各 suite (とくに `conformance-tests -q` と `MitateDB-api/tests -q`) の実行中の PostgreSQL の接続数のピーク (`pg_stat_activity` を `$SP` の bash スクリプトで数秒ごとに数えた最大) を suite ごとに報告に残す。接続枯渇 (`too many clients` 等) が出たら止めて報告する (裁定は監督) |
| 163 | **(D-13)** `r2db-api/tests/test_threadpool_offload.py`:728 のテストが `create_app(..., thread_limit=None)` で app を作り、docstring の主張する変異 (pool の寸法を宣言 concurrency より小さく固定する) で赤になる |
| 126 | §8.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み (`OC` §1.4 の 29〜31)。かつ §8.3 の対応表に**対応の無い行が無い** |

### 8.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) | run |
|---|---|---|
| 78 | **M120**: `R2H` の `DEFAULT_THREAD_LIMIT = 4` を `40` にする | r2db |
| 79 | **M121**: `MTH` の `DEFAULT_THREAD_LIMIT = 4` を `40` にする | MitateDB |
| 80 | **M122**: `R2H` の `create_app` が `thread_limit=None` でも middleware を足す (値は 40) | r2db |
| 81 | **M123**: `MTH` で同じ | MitateDB |
| 82 | **M124**: `R2H` の middleware が渡された値ではなく `DEFAULT_THREAD_LIMIT` を設定する | r2db |
| 83 | **M125**: `MTH` で同じ | MitateDB |
| 84 | **M126**: `R2H` の middleware が毎回 `total_tokens` を設定する (loop の記録を外す) | r2db |
| 85 | **M127**: `R2H` の middleware の「設定済み」を loop ごとではなく instance 全体の 1 つの印にする | r2db |
| 86 | **M128**: `MTH` の middleware が毎回設定する | MitateDB |
| 87 | **M129**: `MTH` の middleware の「設定済み」を instance 全体の 1 つの印にする | MitateDB |
| 88 | **M130**: `R2H` の middleware の `__call__` を同期関数にし、内側の coroutine を返す形にする | r2db |
| 89 | **M131**: `MTH` で同じ | MitateDB |
| 90 | **M132**: `R2H` の `create_app` が middleware 列に足す代わりに返り値を最外側で包む | r2db |
| 91 | **M133**: `MTH` で同じ | MitateDB |
| 92 | **M134**: `R2M` で env が未設定のとき `create_app` に `None` を渡す | r2db |
| 93 | **M135**: `R2M` で env の値を捨て常に `DEFAULT_THREAD_LIMIT` を渡す | r2db |
| 94 | **M136**: `R2M` の正の判定を「負なら失敗」にする (0 を通す) | r2db |
| 95 | **M137**: `R2M` の正の判定を「0 なら失敗」にする (負を通す) | r2db |
| 96 | **M138**: `R2M` で `int()` できない値を黙って既定に落とす | r2db |
| 97 | **M139**: `MTM` で 92 と同じ | MitateDB |
| 98 | **M140**: `MTM` で 93 と同じ | MitateDB |
| 99 | **M141**: `MTM` で 94 と同じ | MitateDB |
| 100 | **M142**: `MTM` で 95 と同じ | MitateDB |
| 101 | **M143**: `MTM` で 96 と同じ | MitateDB |
| 102 | **M144**: `RH` の `perf_thread_limit()` が env 無しのとき `None` を返す | r2db |
| 103 | **M145**: `MH` で同じ | MitateDB |
| 104 | **M146**: `RH` が env の解析値を `create_app` に渡さない (常に既定) | r2db |
| 105 | **M147**: `MH` で同じ | MitateDB |
| 106 | **M148**: `RH` の `perf_thread_limit()` が常に `DEFAULT_THREAD_LIMIT` を返す | r2db |
| 107 | **M149**: `MH` で同じ | MitateDB |
| 108 | **M150**: `RH` で `_build_client` に 2 つ目の `create_app` の返り値を渡す (asgi client と `self._app` が別 object) | r2db |
| 109 | **M151**: `MH` で同じ | MitateDB |
| 110 | **M152**: `MTH` の middleware class の本体の 1 箇所を r2db 側と違う形にする (例: 属性名を変える。テストは `RAQ` の同型性テスト) | r2db |
| 112 | **M153**: `MH` で `_read_store` を pool 無しで作る (基点の形) | MitateDB |
| 113 | **M154**: `MH` の pool の `max_size` を `1` に固定する | MitateDB |
| 114 | **M155**: `MH` の `_cleanup` から `self._read_store.close()` を外す | MitateDB |
| 116 | **M156**: `R2H` で、116 のテストが保持に使う handler の slot の取得を `run_in_threadpool` に渡す関数の中へ移す (slot が thread の token の後になる) | r2db |
| 117 | **M157**: `R2H` の middleware から `total_tokens` の設定を落とす (limiter が 40 のまま) | r2db |
| 118 | **M158**: `MTH` で 116 と同じ | MitateDB |
| 119 | **M159**: `MTH` で 117 と同じ | MitateDB |
| 152 | **M190**: `R2M` で空文字を起動失敗にする | r2db |
| 153 | **M191**: `MTM` で空文字を起動失敗にする | MitateDB |
| 154 | **M192**: `RH` が無効値のとき `create_app` に `None` を渡す (limiter 40、accessor が既定を返さない) | r2db |
| 155 | **M193**: `MH` で同じ | MitateDB |
| 156 | **M194**: `pool.py` の `_new_connection` から `sessions` / `connect_wall_ms` の加算を外す | MitateDB |
| 157 | **M195**: `pool.py` の `discard` で close の前の畳み込みを外す | MitateDB |
| 158 | **M196**: `pool.py` の `closeall` で close の前の畳み込みを外す | MitateDB |
| 159 | **M197**: `pool.py` の読みだけの method が `acquire()` 経由で接続を取って読む | MitateDB |
| 160 | **M198**: `pool.py` の畳み込みの加算を `self._stats_lock` の `with` の外へ出す (テストは AST pin) | MitateDB |
| 161 | **M199**: `MH` の `platform_db_time_stats()` の合計から pool の分を外す | MitateDB |
| 163 | **M200**: `r2db-api/src/r2db_api/limits.py` の `role_pool_size` が常に `4` を返す (テストは :728) | r2db |
| 111・115・120・121・122・123・124・125・126・162 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す) | — |

- **M120〜M159・M190〜M199 が赤にする test id は新規テスト (M152 は既存の同型性テスト、M199 は改めた `MT78`:474 のテスト、M200 は既存の :728 のテスト) の名前**なので、実装担当が §8.2 の各行に対応するテストを作り、その id を `mutations` の `tests` に **1 件だけ**書く (`OC` §1.5 の 40。`mutate.py` は最初の失敗で止まる)。
- **run 列ごとに別の JSON / 別の run に分ける** (r2db = `r2db-api/tests`、MitateDB = `MitateDB-api/tests`。1 run に複数の suite を混ぜない)。
- 同じ数行に掛かる変異 (M122・M132、M124・M126・M127・M157、M195・M196・M198 など) は `old` が互いに重ならない粒度を実装担当が選ぶ。変異の具体的な `old` / `new` は実装の形に合わせて実装担当が書き、報告に表で残す。

### 8.4 道具の引数

`$SP` (自分の scratchpad) を `export SP=...` しておく。`pt.py` / `mutate.py` は **main checkout を cwd にして走らせ、`-C` で worktree を指す** (渡し忘れると main を測る)。`conformance-tests -q` は前景の 1 回 (Bash の timeout 600000) で走らせる。

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- r2db-api/tests/test_threadpool_offload.py MitateDB-api/tests/test_threadpool_offload.py MitateDB-api/tests/test_main.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- r2db-api/tests/test_r78_pool_wait_stats.py MitateDB-api/tests/test_r78_pool_wait_stats.py MitateDB-api/tests/test_r79_prepared_stats.py r2db-api/tests/test_audit_query.py MitateDB-api/tests/test_audit_query.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- r2db-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- MitateDB-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- tools/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- conformance-tests -q
tools/dev/mutate.py "$SP/r101-wp3-mutations-r2db.json" -C .claude/worktrees/r101b --wait 1800
tools/dev/mutate.py "$SP/r101-wp3-mutations-mitatedb.json" -C .claude/worktrees/r101b --wait 1800
```

worktree を cwd にして走らせるもの (`python3` で走らせる):

```bash
python3 tools/check_comment_provenance.py --base 2e746cc r2db-api/src/r2db_api/http.py MitateDB-api/src/mitatedb_api/http.py r2db-api/src/r2db_api/main.py MitateDB-api/src/mitatedb_api/main.py MitateDB-api/src/mitatedb_api/pool.py
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- **`pytest` の直接実行・`tools/perf_baseline.py` の実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。**`DSA_PERF_THREAD_LIMIT` / `R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT` を環境に残したまま pytest を走らせない。** 道具が REFUSED (終了コード 75) を返したら待つか報告する (`OC` §1.10 の 66)。worktree から subprocess を起こすテストの `PYTHONPATH` は `OC` §2 の 17 に従って明示する。
- 一時ファイルは `$SP` 配下だけに置く。複数手順のシェル処理は `$SP` の bash スクリプト (bash 3.2 互換) にする。報告は `$SP/r101-wp3-report.md` に書く。

## 9. WP-4 — `tools/perf_baseline.py` に real-server plug (`--real-server`) を足す (実装担当)

**目的**: server を production の composition root (C-26 の launcher) で別 process に起動し、client を K 並列の子 process に分けて `query` を測る計測器を足す (D-15)。閉止形 (`RM` §0.1.4 の 2 の改訂形、D-16) の判定はこの計測器で行う (§10)。**既存の 6 plug の経路と既存の行は変えない。**

**読むべき正本**: 本書 §7.1 (とくに床の算術 = client と server が同 process・同 GIL の計測器では 8 倍が出ない理由)、§7.3 の D-15・D-16、§7.5 の (W-12)〜(W-17)。v1.0 の §1.3 の (6)〜(8) (thread の配置・measured 区間・行の印字位置) は前提として有効。規律は `OC` §1.3〜§1.6・§1.10、性能計測の同時実行の禁止は同 §2 の 19。

**変更クラス**: B (§7.5 の (W-18)。`_ISOMORPHIC_TARGETS`・`spec/`・`conformance-tests/`・`security/` に触れない)。**使用テンプレート**: `ROLE_PROMPT_TEMPLATES.md` の 2 (実装)。規模 M。

### 9.1 触ってよいパス

- `tools/perf_baseline.py` — `--real-server <peer>` と `--client-processes <N>` (既定 8。実際の子の数は `min(N, K)`) の引数、`registry.json` の `composition_roots` の読み (読むだけ。発見の形は §7.5 の (W-14) の `conformance-tests/conftest.py` と同じく `<name>/conformance` を `sys.path` に足して class を取る)、`--real-server` の run では real plug だけを走らせること (registry の `adapters` は作らない)、launcher の `start(ceilings={"data": 1, "control": 1})` → launcher の `control_bearer` で control plane の HTTP (`POST /control/v1/credentials`) から developer credential を発行し、それで entity と行を作る → K=1 の先頭で `query` が 200 で行数 > 0 であることを確かめる → `query` op だけを launcher の `runtime_bearer` で測る → `stop()` (例外でも必ず 1 回)、子 process の client (group ごとに `multiprocessing.Barrier` で開始を揃え、各子が K/N 本 (余りは先頭の K % N 個の子に 1 本ずつ) を 1 回の `asyncio.gather` で送り、完了時刻を `time.time_ns()` で返し、measured 区間の `getrusage(RUSAGE_SELF)` の `ru_utime + ru_stime` の差分を親に返す)、group wall (= 子の完了時刻の最大 − 開始時刻) の集計、`REALPERF` 行と `REALCPU` 行の組み立てと印字 (書式は D-15 の逐語。`PERFRUN` の後に自身の塊として出す)。`--real-server` の経路も既存の `main()` の `suite_lock(exclusive=True)` と使い捨て cluster の下で走らせる (§7.5 の (W-12)。launcher の admin DSN は cluster の env から読まれる = (W-15))。**既存の関数 (`_load_registry`・`_discover_and_build`・`_run_concurrent`・`_measure_op`・`_emit_*`・`_format_*`) の本体、既存の行 (`PERF` / `CPU` / `POOL` / `DBTIME` / `PREPARED` / `PREPSTMT` / `ROUNDTRIP`) の列名・並び・書式・行数・相対順、既存の引数の意味、`--real-server` 無しの run の出力を変えない** (v1.0 §1.1 の (f))。閾値を持たない (P-8)。server 側の `CPU` / `DBTIME` 行は出さない (別 process。D-15)。
- `tools/tests/test_perf_baseline.py` — 完了条件 127〜145・164〜171 のテストの追加 (stub の launcher・stub の HTTP server は `tmp_path` と test の中で作る。新規テストファイルは作らない)。**既存テストの本体は変えない。**
- `tools/PERF_BASELINE_README.md` — `--real-server` / `--client-processes` と `REALPERF` / `REALCPU` 行の節 (書式、窓と分母、`REALCPU` は床の可視化であり判定に使わないこと、server 側の `CPU` / `DBTIME` 行が出ない理由、launcher の start / stop と後始末、credential の使い分け (control → developer の発行と entity・行の用意、`query` は runtime) と先頭の確認、子の数 `min(N, K)` と余りの配り方、`--real-server` の run は real plug だけであること)。既存の節の記述は事実が変わる箇所だけを直す。

**これ以外は 0 件。** とくに `conformance-tests/` (`registry.json`・`conftest.py`・`socket_harness.py`・`test_c26_composition_root.py` を含む)、両 launcher (`RLS` / `MLS`)、`tools/deploy_smoke.py`、両 peer の `src/` と `conformance/`、`spec/`・`security/` を触らない (launcher は変えずに再利用する。D-15)。**launcher や registry に差分が要ると判断したら実装せず報告する** (`OC` §1.5 の 37)。

**書き方**: `tools/` のコメント・docstring も現在形で書き、経緯語を足さない (§6.1 の監督裁定 6 と同じ扱い)。

### 9.2 完了条件 (33 件。164〜171 は監督裁定 (2026-09-27) で足した行で、表では 150 の後に置く。WP-4 の最後の完了条件は 151)

以下「stub launcher」は `start` / `stop` / `data_base_url` / `control_base_url` / `runtime_bearer` / `control_bearer` を持ち呼び出しを記録する test 内の class、「stub server」は test の中で立てる HTTP server (標準ライブラリで足りる) で、受けた要求の path・`Authorization`・同時 in-flight の最大・送り手の process を記録し、control の credential 発行と schema 操作に合成の応答を返し、応答を遅らせたり状態コードや行数を選べるものを指す。stub は `--registry` に渡す `tmp_path` の registry の `composition_roots` から読ませる。

| # | 完了条件 |
|---|---|
| 127 | **(D-15)** `--real-server <peer>` で走らせると、`--registry` に渡した registry の `composition_roots` の `<peer>` の行が名指す module / class (stub launcher) が instance 化され、その `start` が呼ばれる |
| 128 | **(D-15)** stub launcher の `start` が `ceilings={"data": 1, "control": 1}` で呼ばれる |
| 129 | **(D-15)** 測定の途中で例外が出ても (stub server が途中で接続を切る等)、stub launcher の `stop` がちょうど 1 回呼ばれる |
| 130 | **(D-15)** 正常に終わった run でも `stop` がちょうど 1 回呼ばれる |
| 131 | **(D-15)** 測られる op は `query` だけ: entity と行の用意の後に stub server が受けた data plane の要求の path がすべて `/v1/data/<entity>/query` で、`REALPERF` 行は `op=query` の 1 行だけである |
| 132 | **(D-15)** `--client-processes` を省いた K=32 の run で、stub で観測した子 process の数が 8 で、`REALPERF` 行の `client_processes=8` と一致する |
| 133 | **(D-15)** K=1 の run では子 process の数が 1 (= `min(8, 1)`) で、`client_processes=1` である |
| 134 | **(D-15)** 各 group で子が受け持ちの本数を同時に送る: stub server が各要求を一定時間 (例 50 ms) 保持するとき、観測した同時 in-flight の最大が K である |
| 135 | **(D-15)** group wall が「子の完了時刻 (`time.time_ns`) の最大 − 開始時刻」である (集計の関数に既知の開始時刻と完了時刻の列を渡して値を観測する) |
| 136 | **(D-15) 監査照合**: group ごとの開始が `multiprocessing.Barrier` で揃えられ、開始時刻と完了時刻がどちらも `time.time_ns()` で取られ、process を跨いで `time.perf_counter()` を比べる箇所が 0 件である。照合対象は該当箇所の `file:line` |
| 137 | **(D-15)** warmup の group は `REALPERF` の分布に入らない: stub server が warmup の要求だけを遅く返すとき、`p95_ms` が遅い側の値を含まない |
| 138 | **(D-15)** `p50_ms` / `p95_ms` が measured の group wall の列に既存の `_percentile` を掛けた値である (既知の列で観測する) |
| 139 | **(D-15)** `REALPERF` 行の書式が D-15 のとおり (`REALPERF peer=<peer> plug=<peer>-real transport=real-server op=query concurrency=<K> client_processes=<N> n=<n> p50_ms=<x.xxx> p95_ms=<x.xxx>`、列の名前と並び) である。stub launcher で pin する |
| 140 | **(D-15)** `REALCPU` 行の書式が D-15 のとおり (`REALCPU peer= plug= op=query concurrency= client_processes= requests= wall_ms= cpu_client_ms=`) である。stub launcher で pin する |
| 141 | **(D-15)** `cpu_client_ms` が子の `getrusage(RUSAGE_SELF)` の差分の合計である: 子が既知の CPU を使う stub の run で、`cpu_client_ms` が子の消費の和の下限以上で、親 process 自身の同区間の `RUSAGE_SELF` の差分より大きい |
| 142 | **(D-15)** `REALCPU` の `requests=` が `n × K` (measured のみ)、`wall_ms=` が measured の group wall の和である |
| 143 | **(D-15)** `query` の応答に 200 以外が 1 本でもあると、`REALPERF` / `REALCPU` 行を出さずに 0 以外の終了コードで終わり (stub server が 500 を返す)、`stop` は呼ばれる |
| 144 | **(D-15・v1.0 §1.1 の (f))** `--real-server` 無しの run では `REALPERF` / `REALCPU` 行が出ず、launcher が instance 化されない (stub の registry で観測する) |
| 145 | **(D-15)** `--real-server` の経路が `dsa_testpg.suite_lock(exclusive=True)` の中と使い捨て cluster の中で走る (`TPB`:428 と同じ形の stub で観測する) |
| 146 | **(v1.0 §1.1 の (f)) 監査照合**: 既存の `_format_row` / `_format_cpu_row` / `_format_pool_row` / `_format_dbtime_*` / `_format_prepared_row` / `_format_prepstmt_row` / `_format_roundtrip_*` と `_run_concurrent` / `_measure_op` の本体の差分が 0 行、`TPB` の既存 pin (§7.5 の (W-13)) の本体の差分が 0 行で緑。`git diff` で示す |
| 147 | **監査照合**: `conformance-tests/` (`registry.json` を含む)・両 launcher・`tools/deploy_smoke.py`・両 peer の差分が 0 行、`git status --short` が §9.1 のパスだけを示す |
| 148 | **監査照合**: `tools/PERF_BASELINE_README.md` に §9.1 の文書の項目が在り、`python3 tools/check_doc_refs.py` が 0 dangling |
| 149 | **監査照合**: `python3 tools/change_class.py <触った全パス>` が `class=B`、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged。ホスト名・実 DSN・作業機の絶対パスを新規の文書・テスト・コメントに書いていない |
| 150 | **監査照合**: 報告前に `tools/tests -q` と `conformance-tests -q` を各 1 回回して緑 (`conformance_required=true`。`tools/tests` は完了ゲートの root suite に入らない)。集計行を逐語で報告に残す |
| 164 | **(D-15)** entity の用意の前に、stub server が `POST /control/v1/credentials` (役割 `developer`) を launcher の `control_bearer` の `Authorization` で受ける |
| 165 | **(D-15)** schema 操作 (`/v1/schema/operations`) と行の作成の要求の `Authorization` が、164 で発行された developer credential である |
| 166 | **(D-15)** 測定の `query` の要求の `Authorization` がすべて launcher の `runtime_bearer` である |
| 167 | **(D-15、`OC` §1.5 の 32)** K=1 の先頭の `query` が 200 でも行数 0 のとき (stub server が空の結果を返す)、`REALPERF` / `REALCPU` 行を出さずに 0 以外の終了コードで終わり、`stop` は呼ばれる |
| 168 | **(D-15)** `--client-processes 8` で K=4 の run では子 process の数が 4 (= `min(8, 4)`) で、`client_processes=4` である |
| 169 | **(D-15)** K=10・N=4 のとき子ごとの本数が `[3, 3, 2, 2]` (余り 2 本を先頭の 2 個の子に 1 本ずつ) である (本数を配る関数に K と N を渡して観測する) |
| 170 | **(D-15)** `--real-server` の run では registry の `adapters` が作られない (stub の registry の `adapters` に、作られたら記録する stub の adapter を置いて観測する) |
| 171 | **(D-15)** 出力で `PERFRUN` 行が `REALPERF` / `REALCPU` 行より前にあり、`REALPERF` / `REALCPU` 行が他の行を挟まず連続する塊である |
| 151 | §9.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み。かつ §9.3 の対応表に**対応の無い行が無い** |

### 9.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/perf_baseline.py`) | run |
|---|---|---|
| 127 | **M170**: registry を読まず launcher の module 名を固定で import する | tools |
| 128 | **M171**: `start` に渡す `ceilings` の `data` を `2` にする | tools |
| 129 | **M172**: `stop` の呼び出しを成功経路だけに移す (例外経路で呼ばない) | tools |
| 130 | **M173**: 成功経路の `stop` の呼び出しを外す | tools |
| 131 | **M174**: `query` に加えて別の op (例 `insert`) も測る | tools |
| 132 | **M175**: `--client-processes` の既定を `4` にする | tools |
| 133 | **M176**: K=1 でも `--client-processes` の値の数だけ子を起こす | tools |
| 134 | **M177**: 子が K/N 本を 1 本ずつ逐次に `await` する | tools |
| 135 | **M178**: group wall を子の完了時刻の最大ではなく平均で取る | tools |
| 137 | **M179**: warmup の group の wall も分布に入れる | tools |
| 138 | **M180**: `p50_ms` に平均を出す | tools |
| 139 | **M181**: `REALPERF` 行の列名を 1 つ変える (例 `client_processes=` → `clients=`) | tools |
| 140 | **M182**: `REALCPU` 行の列名を 1 つ変える (例 `cpu_client_ms=` → `client_cpu_ms=`) | tools |
| 141 | **M183**: `cpu_client_ms` に親 process 自身の `RUSAGE_SELF` の差分を出す | tools |
| 142 | **M184**: `requests=` を `(warmup + n) × K` にする | tools |
| 143 | **M185**: 応答の状態コードを見ない | tools |
| 144 | **M186**: `--real-server` 無しでも real-server の経路を走らせる | tools |
| 145 | **M187**: `--real-server` の経路を `suite_lock` の外で走らせる | tools |
| 164 | **M201**: developer credential を発行せず、schema 操作に `runtime_bearer` を使う | tools |
| 165 | **M202**: schema 操作と行の作成に `control_bearer` を使う | tools |
| 166 | **M203**: 測定の `query` に developer credential を使う | tools |
| 167 | **M204**: 先頭の確認から行数 > 0 の判定を外す (200 だけを見る) | tools |
| 168 | **M205**: 子の数を `min(N, K)` ではなく `N` にする | tools |
| 169 | **M206**: 余りを末尾の子に配る | tools |
| 170 | **M207**: `--real-server` の run でも `_discover_and_build` を呼ぶ | tools |
| 171 | **M208**: `REALPERF` / `REALCPU` 行を `PERFRUN` 行より前に印字する | tools |
| 136・146・147・148・149・150・151 | **監査照合** (照合対象は各行の本文のとおり) | — |

- M170〜M187・M201〜M208 が赤にする test id は新規テストの名前なので、実装担当が §9.2 の各行に対応するテストを作り、その id を `tests` に **1 件だけ**書く。run は `tools/tests` の 1 本 (別 suite を混ぜない)。`old` / `new` は実装の形に合わせて実装担当が書き、報告に表で残す。
- 子 process を起こすテストは、他の pytest と並行して走っても stub server の port と子 process が衝突しない形にする (port は OS に選ばせる)。

### 9.4 道具の引数

§8.4 と同じ (`export SP=...`、main checkout を cwd に `-C .claude/worktrees/r101b`)。

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- tools/tests/test_perf_baseline.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- tools/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r101b -- conformance-tests -q
tools/dev/mutate.py "$SP/r101-wp4-mutations-tools.json" -C .claude/worktrees/r101b --wait 1800
```

worktree を cwd にして `python3 tools/change_class.py` / `python3 tools/check_doc_refs.py` / `python3 tools/public_value_scan.py` (§8.4 と同じ)。**`tools/perf_baseline.py` を実 registry に対して走らせない** (実測は §10 で監督)。報告は `$SP/r101-wp4-report.md` に書く。§8.4 の禁止事項がそのまま掛かる。

## 10. 再計測と閉止の判定 (**監督が実施する**)

**目的**: WP-3 の効きを計測前に固定した D-12 で判定し、R-101 の閉止を D-16 (`RM` §0.1.4 の 2 の改訂形) で判定する。記録は設計メモ `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` を v0.3 に上げて §5・§6 に置く。**判定規則は計測前に固定し、計測後に動かさない** (§7.2 の (c))。

### 10.1 判定規則 (§7.3 の D-12・D-16 の逐語)

```text
D-12 判定規則 (計測前に固定): 同じ道具・同じ条件 (`DSA_PERF_POOL_SIZE=32`、K=1 `--warmup 10 --n 100`、K=32 `--warmup 3 --n 15`、`DSA_PERF_THREAD_LIMIT` 無し)、基準 = 設計メモ v0.2 §2.2 の既定 run (K=1 :625-、K=32 :1213-)。合格: query p50 (K=32) が 4 plug 中 3 plug 以上で 10% を超えて改善、どの plug も 10% を超えて悪化しない、K=1 の p50 が ±10% 内 (MitateDB 2 plug の K=1 は D-11 で connect が消えるので「悪化しない」だけを見る)。設計メモ v0.3 §5 に逐語。8 倍は WP-3 では判定しない (床)。
D-16 閉止の判定規則 (計測前に固定): real-server plug で K=1 と K=32 (`--warmup 3 --n 15`) を取り、K=32 は 2 run 取る。query の p50 の K=32 / K=1 の比が両 peer で K=32 の 2 run とも 8 倍以内 = R-101 閉止 (RM §0.1.4 の 2 の改訂形)。ε (K=32 の 2 run の相対差) と δ = max(10%, 2ε) は記録だけで、判定には使わない。本変更セットでは server は 1 process なので 8 倍は満たさない見込み — その実測を設計メモ v0.3 §6 に逐語で残し、R-113 (multi-process、規模 L) の出発点にする。
```

### 10.2 手順

1. **他の pytest と nginx を止める** (`OC` §2 の 19。real-server plug と socket plug が起こす計測器自身の nginx は除く)。
2. **D-12 (WP-3 の完了ゲートの後)**: WP-3 を入れた木の道具で、`DSA_PERF_POOL_SIZE=32` を置き `DSA_PERF_THREAD_LIMIT` を置かずに、K=1 (`--warmup 10 --n 100 --concurrency 1`) と K=32 (`--warmup 3 --n 15 --concurrency 32`) を取る。基準は設計メモ v0.2 §2.2 の既定 run (K=1 :625-、K=32 :1213-)。各 run の `CPU` 行の `thread_limit=` が `4` であることを確かめる (D-10)。D-12 の 3 項 (3 plug 以上で 10% を超えて改善 / どの plug も 10% を超えて悪化しない / K=1 が ±10% 内、MitateDB の 2 plug の K=1 は悪化しないことだけ) を plug ごとの表にする。
3. **D-16 (WP-3 と WP-4 の両方の完了ゲートの後)**: `tools/perf_baseline.py --real-server r2db-api` と `--real-server MitateDB-api` のそれぞれで、K=1 と K=32 (`--warmup 3 --n 15`) を取り、K=32 は 2 run 取る。`REALPERF` の `query` の p50 の K=32 / K=1 を peer ごと・K=32 の run ごとに書き、2 run とも 8 以下かを判定する。ε と δ は記録だけで判定に使わない (D-16)。`REALCPU` は床の可視化として記すだけで判定に使わない (D-15)。
4. **後始末の照合**: real-server の各 run の後、`pg_database` / `pg_roles` の差分が 0 で、launcher が起こした uvicorn / nginx の process が残っていない (`OC` §2 の 18 の形で python / nginx の process を数える)。
5. **記録**: 実測を逐語で設計メモ v0.3 に置く (ホスト名・実 DSN・作業機の絶対パスを書かない。`PERFRUN` の `host=` は `<OS/arch>` の形)。判定は §10.1 の規則だけで行う。

### 10.3 設計メモ v0.3 の骨 (§5・§6 を足す。§1〜§4 は書き換えない)

| 節 | 内容 |
|---|---|
| §5 | WP-3 の再計測: 方法 (D-12 の条件と基準の run)、実測逐語 (`PERFRUN` / `PERF` / `CPU` / `DBTIME` / `POOL`)、D-12 の逐語、plug ごとの 3 項の成立 / 不成立の表、判定 |
| §6 | real-server plug の実測: 方法 (launcher・`ceilings`・client process 数・K と `--warmup` / `--n`・ε と δ)、実測逐語 (`PERFRUN` / `REALPERF` / `REALCPU`)、peer ごとの K=32 / K=1 の比、D-16 の判定、後始末の照合 (§10.2 の 4)、8 倍を満たさないときはその実測を R-113 の出発点として記す |

### 10.4 記録 (統合時、監督。枠 v1.1「記録」の逐語)

```text
- RM §0.1.4 の 2: 行を残し「【改訂 2026-09-27 (v1.x)】計測器は real-server plug (`tools/perf_baseline.py --real-server`)。理由 = 床の算術」を日付付きで追記 (R-14)。
- RM §8: R-101 行に【追記】(WP-3 / WP-4 の結果、閉止しない)、R-84 行に却下理由、R-113 を起票 (multi-process worker と limit 状態の PostgreSQL 共有、規模 L、設計レビュー、Class C 見込み)。
- CONTROL_MAPPING: 制御が変わらなければ参照追随のみ。
- 設計メモ v0.3: §5 WP-3 の再計測、§6 WP-4 の real-server 実測。
```

### 10.5 完了条件 (監督が自ら照合する)

1. 設計メモ v0.3 §5 に D-12 の逐語と、plug ごとの 3 項の表と判定が在り、各 run の `CPU` 行の `thread_limit=` が `4` である。規則の文言が本書 §7.3 と同じである (計測後に動かしていない)。
2. 設計メモ v0.3 §6 に両 peer の `REALPERF` / `REALCPU` の逐語、K=32 の 2 run それぞれの K=32 / K=1 の比、記録としての ε と δ、D-16 の判定が在る。§10.2 の 4 の後始末の照合の結果 (差分 0、残った process 0) が在る。
3. `RM` §0.1.4 の 2 に【改訂 2026-09-27 (v1.x)】が行を残して追記されている (R-14、`OC` §1.8 の 56)。`RM` §8 の R-101 行に【追記】(WP-3 / WP-4 の結果)、R-84 行に却下の理由、R-113 の行 (§12 の文案。起票の 2 問は `OC` §1.15 の 77) が在る。**R-101 を閉じるのは D-16 を両 peer で満たしたときだけ。**
4. §0.1.4 の 2 の改訂と同じ変更セットで、本書 §6.2 に WP-3 / WP-4 の実施と受け入れを記す。

## 11. レビューと受け入れ (v1.1)

- **コードレビュー 1 回** (`ROLE_PROMPT_TEMPLATES.md` の 5、opus、Class D。実装担当とは別の起動)。観点: (i) 両 peer の middleware class と `DEFAULT_THREAD_LIMIT` が同名・本体同一で登録され、`create_app` の返り値の形が既定でも `None` でも基点と同じであること (完了条件 78〜91・110・152〜155)、(ii) D-13 の trade-off (slot が loop の thread で先、N+1 の拒否が不変、同期区間の同時数 4、循環待ちが無い) がコードと 116〜119 のテストで成り立つこと、(iii) env の厳格 parse の失敗が起動時に変数名付きで出ること (92〜101)、(iv) adapter が `create_app` の同じ引数を通り、WP-1 の wrapper が残っていないこと、`perf_thread_limit()` の実効値 (102〜111・154・155)、(v) MitateDB の adapter の pool の寸法と後始末、`pool.py` の畳み込みが close の前・`_stats_lock` の中にあり fast path の `self._lock` に触れないこと、`scope=platform` に pool の分が入ること、接続のピーク (112〜115・156〜162)、(v-2) limiter 40 を述べた既存コメントの書き換えと来歴の登録、:728 のテストの `thread_limit=None` (123・163)、(vi) real-server plug の窓 (Barrier・`time.time_ns`・warmup の除外)、子の数と余りの配り方、子の CPU の取り方、credential の使い分け (control → developer 発行、測定は runtime)、先頭の 200 と行数 > 0 の確認、launcher の start / stop が例外でも対になること、既存の行と `--real-server` 無しの出力が不変で `--real-server` の run が real plug だけであること (127〜147・164〜171)、(vii) 新規テストの空振り (`OC` §1.5 の 32) と代理指標 (`OC` §1.7 の 52)、新規コメントに経緯語が無いこと、(viii) レビュー担当自身の変異 1〜2 件 (報告に無いもの。完了ゲートと並行させない)。
- **受け入れ監査 1 回** (`ROLE_PROMPT_TEMPLATES.md` の 6、Class D。レビュー担当とも別の起動)。観点は §8.2・§9.2 の全行の主張 vs 実測 (`OC` §1.5 の 34) と、§8.3・§9.3 の変異の再現。
- **完了ゲートは監督** (`tools/dev/gate.py -C .claude/worktrees/r101b`)。ゲート中の PostgreSQL の接続のピークを記録し、接続枯渇が出たら裁定する (D-11)。`tools/tests` は root suite に入らないので別に回す (`tools/dev/finalize.py --tools-tests`)。**統合の前に main を取り込み** (件数 pin・`COLLECTION_FLOOR`・台帳の版の衝突を先に解く。§6.1 の監督裁定 8 の前例)、取り込んだ木で完了ゲートを取る。
- **Class D の証拠** (`RM` §9 の 8): 上のレビューと監査、完了ゲート、conformance の完走に加え、**依頼者裁定の逐語** (クラス D の宣言と src の middleware class の登録・adapter の wrapper class の登録の削除を依頼者に提示して得た文言。§0 の v1.1 行のとおり提示待ちで、逐語は §6.1 に足す)。版付きの security-contract 決定は、`security/` の変更が `CM` の参照追随に留まる限り**該当なし** (契約 1.11.0 不変、Security Invariants 不変)。
- レビュー・監査の指摘のうち同じ変更セットで直さなかったものは、監督が `OC` §1.15 の 77 で 1 件ずつ裁定する。

## 12. 本書 v1.1 の範囲外 (申し送り。列挙のみ)

- **(12-1) multi-process worker = R-113 (起票の文案)。** 監督が §10.2 の 3 の実測の後に `RM` §8 に起票する (起票の 2 問は `OC` §1.15 の 77)。文案:

  ```text
  | **R-113** | **規模 L — multi-process worker と in-memory の limit 状態の置き場の変更は両 peer の data plane の構造 (設計レビュー、Class C 見込み)。** 1 process の server は Python の CPU (GIL) で直列化される (作業指示書 docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md の WP-2 の判定 J-2)。real-server plug の K=32 / K=1 (同書 §10 の D-16) が 8 倍を超える場合、GIL の外に出る候補は multi-process worker である。in-memory の limit 状態 (r2db `_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES`、MitateDB `_LimitStateHolder`) を PostgreSQL の共有状態に移せば `limit_enforcement` の `enforced` を保てる (R-18 の (c))。移さなければ `process_ceilings` > 1 で `deployment_required` に落ちる (宣言値の変更)。 | 起票 (R-101 の是正の 2 段目。依頼者裁定 2026-09-27 の 2)。着手は設計レビューが条件。出発点は設計メモ docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md v0.3 §6 の実測。 |
  ```

- **(12-2) R-102 (MitateDB の cell lock)。** 本書に混ぜない (§7.4)。v1.0 §6.1 の監督裁定 8 の O-3 (`cell.py` の `prepared_stats` の docstring) も R-102 の変更セットで扱う。
- **(12-3) `RM` §0.1.4 の 2 の改訂、R-101 / R-84 行の追記、R-113 の起票。** 監督が台帳で行う (§10.4・§10.5 の 3)。本書は台帳を書き換えない。
- **(12-4) 判定規則の次版への申し送り** (設計メモ v0.2 §4 の 6: r > 1 の場合、J-1 (i) で limit 4 の方が速い場合、J-2 と J-5 の同時成立) は本書 v1.1 では扱わない。
- **(12-5)** v1.0 §4 の (4-4) (production の composition root への thread limit) は本書 v1.1 の WP-3 が扱う。(4-6) (是正 WP) は本書 v1.1 の §7〜§11 である。§4 の本文は書き換えない。

**v1.1 (WP-3 / WP-4、2026-09-28)**: worktree `r101b` (WP-4) と `r101b-wp3` (WP-3、`01d38c5` から分岐、`d7a7500` で merge)。implementer sonnet ×8 起動 (WP-3 第 1 段 / 第 2 段 / 差し戻し 1〜2、WP-4 第 1 段 / 差し戻し 1〜4)、コードレビュー opus (`claude-opus-5-5`) WP-3 2 回・WP-4 3 回 (全件閉じ、`$SP/review-wp3*.md` / `review-wp4*.md`)、受け入れ監査 opus 1 回 (充足 95 / 未充足 0 / 証拠不足 3、観察 5 件 → 裁定 17。観察 1 を計測器の欠陥として採り差し戻し 5、D-16 を再計測)。変異: WP-3 r2db 26 + MitateDB 22 + 11、WP-4 tools 35、レビュー担当の自作 RV1〜RV3 / RV3-R1 / RV3-M1 (全件 red)。完了ゲート (監督、solo、使い捨てクラスタ): tree `d7a7500` `label r101b gate: 4342 passed, 2 subtests passed in 330.44s (0:05:30)`、最終 tree `b25841f` `label r101c gate: 4342 passed, 2 subtests passed in 323.21s (0:05:23)`、judge=PASS、pg_database/pg_roles diff 0 (main `2e746cc` の 4314 + 28)。`tools/tests` (root gate の対象外) `pt: 645 passed in 78.61s (0:01:18)`。再計測: D-12 成立、D-16 成立 (設計メモ v0.3 §5・§6)。Class D の証拠: 依頼者裁定の逐語 2 件 (§6.1)、コードレビュー、受け入れ監査、完了ゲート、conformance 完走; `security/` は CM 3.6 の参照追随のみ (Control 主張の追加・変更なし)、契約 1.11.0 不変。`spec/`・`conformance-tests/` の差分は `COLLECTION_FLOOR` (4314 → 4342) だけ。
