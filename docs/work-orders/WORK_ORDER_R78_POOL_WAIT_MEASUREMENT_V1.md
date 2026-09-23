# 作業指示書 — R-78 接続プールの取得待ちを数え、`tools/perf_baseline.py` で K を振って実測する (計測が成果物)

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点 local main `088be85`。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の **R-78** 行 (`RM`:506) で、横断条件は `RM`:305 (**P-8**) と `RM`:448 (**R-20**)、再検討条件の受け皿は `RM`:512 (**R-84**)。worktree は `.claude/worktrees/r78` (branch `r78-pool-wait-measurement`)。
- **変更クラスは B** (実測: §1.3 の (11)。`class=B` / `conformance_required=true`。`docs/design/`・`tools/PERF_BASELINE_README.md` は A、両 peer の `src`・`tests`・`conformance`、`tools/perf_baseline.py`・`tools/tests/` が B)。**契約は 1.8.0 のまま**で `spec/`・`conformance-tests/`・`security/` の差分は **0**。
- **設計文書は新しく起こさない。** 枠 (D-1〜D-7 と却下案) は §1 にあり、これが監督の確定した決定である (R-62・R-71・R-87 の先例)。**設計レビュー 1 回**を本書に対して行う。本件の成果物である実測の記録は、新規の設計メモ `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` に置く (**§3 = WP-2、監督が実施する**)。
- **本件は計測と記録が成果物である。** 寸法 (pool の `maxconn`、`concurrency`、role の `CONNECTION LIMIT`) と未プールの経路を変える判断は、計測の後に**別の変更セット**で行う (§1.1 の (a)、`RM`:305 の P-8、`RM`:448 の R-20 の「実測前に直さない」)。
- **WP-1 (実装担当) と WP-2 (監督) は順に行う。** WP-2 は WP-1 の完了ゲートの後に始まるので、**並行 WP は無く**、触るファイルの重なりの表は置かない (`OPERATING_CONDITIONS.md` §1.2 の 16・17 は該当しない)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`gate.py`・`finalize.py`・`perf_baseline.py` は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。**実装担当の裁量は実装詳細のみ** — §1 の決定・§2.1 の触ってよいパス・§2.2 の完了条件を実装担当が動かさない。

## 1. 枠

### 1.1 問題設定と守るべき条件

**問題**: プールの取得待ち・接続数と role の `CONNECTION LIMIT` の釣り合いが計測されていない。基点で分かっている事実は次の 3 つである。

- r2db のデータ面は role ごとの `_RolePool` であり、寸法は `role_pool_size(limits)` = `limits.concurrency` (既定 32)。満杯なら `queue.Queue.get(timeout)` で待ち、待ち時間の counter は無い。
- MitateDB のデータ面は application ごとの持続接続 2 本と `cell` の `RLock` による直列化であり (実並行度 1)、プールではない。`pool.py` の `BoundedConnectionPool` は認証 (platform registry) 専用である。
- `tools/perf_baseline.py --concurrency K` は K 要求の wall-clock の p50/p95 と `backend_calls` しか出さない。
- **計測に使う conformance の r2db plug は `PostgresCell(..., pool_size=2)` で作られる** (§1.3 の (2))。宣言上の 32 ではない。したがってフェーズ10 の K=3 の socket 実測は **pool 2 < K 3** であり、プールの取得待ちが在り得た。

フェーズ10 の実測では socket plug の K=3 の p50 が K=1 の約 2〜3 倍 (r2db 8.5→18.2ms、MitateDB 10.9→18.6ms、`DP10`:980-1032) である。**プール待ちなのか、それ以外の直列化** (uvicorn の threadpool / GIL / PostgreSQL) **なのかは、現在の出力からは区別できない。**

**守るべき条件**:

- **(a)** 本件は**計測と記録が成果物**である。寸法や経路を変える判断は計測の後に別の変更セットで行う (`RM`:305 の P-8、`RM`:448 の R-20)。
- **(b)** 計測は挙動を変えない。counter は lock の中の整数加算だけにとどめ、hot path の DB 往復を増やさない。
- **(c)** 契約 1.8.0 のまま、`conformance-tests/` の差分は 0。
- **(d)** 公開規律 (§1.9)。基準値は合成環境の値として記録し、ホスト名・実 DSN・実パスを書かない (§2 の 13)。

### 1.2 決定 (監督確定。D-1〜D-7)

- **D-1 (counter。Class B)。** r2db の `_RolePool` に取得の統計 — `acquire_count`、`wait_count` (満杯で `get(timeout)` に入った回数)、`wait_total_ms`、`wait_max_ms`、`in_use_peak`、`size` — を数え、`SharedPoolManager.stats()` で読める形にする。**数えるのは統計専用の `threading.Lock` の中で行い、既存の `self._lock` を fast path に足さない** (監督裁定 2026-09-23。§1.3 の (1) のとおり `get_nowait()` の成功経路は基点で lock を取らない)。**`stats()` の鍵は `"<application_id>/<role>"` の文字列**とする (監督裁定 2026-09-23。`SharedPoolManager` の entry は `(application_id, role)` の 2 要素で、role だけでは application 間で衝突する)。MitateDB は `pool.py` の `BoundedConnectionPool` に**同じ統計**を置く (認証面)。**データ面の持続接続 2 本には `cell` の `RLock` の取得待ち** (`wait_count` / `wait_total_ms` / `wait_max_ms`) を同じ形で数える — `RLock.acquire(blocking=False)` で先に試し、失敗したときだけ時刻を取って blocking で取り直す (挙動は変えず、待ちだけを計る)。**取得の総数は再入を含むので、鍵名を `lock_acquire_count` として r2db の `acquire_count` と区別し、docstring に「同一 thread の再入も数える」と明記する** (監督裁定 2026-09-23)。**待ちの 3 つの鍵名は両 peer で同じにする。** **統計の同型 pin は行わない** (監督裁定 2026-09-23: プールとロックで機構が違うので、同名の純関数を作らない。§1.3 の (10))。
- **D-2 (harness)。** `tools/perf_baseline.py` に `POOL` 行を足す。各 (plug, op) の計測の**後**に、plug が `pool_stats()` を持てばそれを呼び、1 行に出す。

  ```
  POOL peer=<peer> plug=<plug> op=<op> role=<role> size=<n> acquire=<n> waits=<n> wait_total_ms=<x.xxx> wait_max_ms=<x.xxx> in_use_peak=<n>
  ```

  MitateDB のデータ面は `role=` の代わりに `lock=` の行を出す。**socket 転送の plug も `POOL` 行を出す** (監督裁定 2026-09-23。§1.3 の (8) のとおり uvicorn は同じ process の thread であり、cell / pool に届く。別 process なのは前段の nginx だけである) — `PERF-README` にはその旨を書く。`--concurrency` の形は既存のままにする (K の sweep は監督が K を変えて複数回実行する)。

  **追補 (監督裁定 2026-09-23)**: r2db の `-http` plug (`-socket` は継承) に **harness 専用の環境変数 `DSA_PERF_POOL_SIZE` (正整数)** を足す。**在れば `PostgresCell` の `pool_size` をその値にし、無ければ従来の 2 のまま**にする (§1.3 の (2))。conformance の挙動は既定で不変であり、変更は peer 所有の `r2db-api/conformance/` に閉じる (Class B)。**production の寸法 (`role_pool_size` / `concurrency` / `CONNECTION LIMIT`) は変えない** (§1.1 の (a))。
- **D-3 (計測は監督、記録は設計メモ)。** 完了ゲートの後、監督が両 peer の PostgreSQL 経路の plug (`-http` = asgi-inprocess、`-socket`) で **K ∈ {1, 2, 4, 8, 16, 32}** (32 = `concurrency`) を取り、`PERF` / `POOL` 行を**逐語で**新規 `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` の §2 に置く。**K > `concurrency` は事前拒否ゲートで `LIMIT_EXCEEDED` になるので測らない** (理由を同文書に書く)。

  **`--warmup` / `--n` は K ごとに変える** (監督裁定 2026-09-23。§1.3 の (12) の credential ごと 600 件/分の下に収めるため。**plug の limits は変えない**):

  | K | `--warmup` | `--n` | `(warmup + n) * K` |
  |---|---|---|---|
  | 1・2・4 | 10 | 100 | 110 / 220 / 440 |
  | 8 | 5 | 50 | 440 |
  | 16 | 5 | 30 | 560 |
  | 32 | 3 | 15 | 576 |

  設計メモには **K ごとの `n` を併記し、`n` が小さい K は分散が大きい**旨を書く。**r2db は pool の寸法を 2 通りで取る** (監督裁定 2026-09-23): `DSA_PERF_POOL_SIZE=32` (= production の `role_pool_size` = `concurrency`) と**既定の 2** の両方。**どちらで取った run かが分かるよう、pool の寸法を `PERFRUN` 行または `POOL` 行に記録する。**同 §3 に「p50 が K に比例して伸びる区間」「`POOL` の待ちが出る K」「r2db と MitateDB の差」を**事実として**書く。**§4 の判断 (寸法・未プールの経路・`RM`:512 の R-84 の再検討条件の充足) は監督が書く** — 本書の起草者と実装担当は**見出しと空欄だけ**を用意する。
- **D-4 (テスト)。** counter の単体 (満杯で待たせて `wait_count` / `wait_max_ms` が増える、待ちが無ければ 0、`in_use_peak`)、`stats()` の鍵の集合と鍵の形の pin、harness の `POOL` 行の形式 (`tools/tests`、plug の stub)、**socket の plug でも `POOL` 行が出ること**、`DSA_PERF_POOL_SIZE` の有無で `pool_size` が変わること。**MitateDB の認証面 (`BoundedConnectionPool`) の統計は harness の経路には出ない** (§1.3 の (5)) ので、**単体テストだけで駆動する** (監督裁定 2026-09-23)。**完了条件 1 項目 = 変異 1 つ。**
- **D-5 (性能の非退行)。** counter 追加の前後で `tools/perf_baseline.py` の K=1 / K=3 を監督が取り (基点 `088be85` の道具と本 worktree の道具)、差が **±10% 以内**であること (§1.3 の 27)。
- **D-6 (文書)。** `tools/PERF_BASELINE_README.md` に `POOL` 行の説明と socket 転送で出ない理由を足す。`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` を新設する (§1 目的と方法、§2 実測、§3 事実、§4 判断 (空))。
- **D-7 (コメント)。** docstring は現在形で書く。`python3 tools/check_comment_provenance.py --base 088be85` の FAIL が「**§4.1 (1) 以外が 0 行**」であること。

### 1.3 起草時の実測 (基点 `088be85` の現物。起草者が実施)

| # | 観測 | 出所 |
|---|---|---|
| (1) | **`_RolePool` の取得経路。** `_acquire` は :307-350。**fast path (`self._queue.get_nowait()`、:308-311) は `self._lock` を取らない。** lock を取るのは新規接続の予約 (:323-326) と失敗時の巻き戻し (:331-332) だけ。満杯時の待ちは :345 の `self._queue.get(timeout=self._acquire_timeout)` で、`queue.Empty` を `psycopg.OperationalError` に読み替える (:346-348)。返却は `connection()` の `finally` (:396-423) で、lock は `_retired` の読み (:409) と `_created` の減算 (:423) で取る。`_DEFAULT_ACQUIRE_TIMEOUT_S = 10.0` (:222)。**帰結**: `acquire_count` を `self._lock` の中で数えると、基点では lock を取らない fast path に uncontended な lock 取得が 1 回増える。この増分を判定するのが D-5 の ±10% である | `r2db-api/src/r2db_api/postgres.py`:222・:307-350・:396-423 |
| (2) | **寸法の実測。** `role_pool_size(limits)` は `return limits.concurrency` (`limits.py`:165)、`ResourceLimits.concurrency = 32` (:17)。**ただし conformance の r2db plug は `PostgresCell(..., pool_size=2)` を渡す** (`conformance_adapter_r2db_http.py`:1476-1484)。`-socket` plug は同じ class を継承し `_make_cell` を上書きしないので**同じ 2 である**。platform pool (認証面) は `_DEFAULT_PLATFORM_POOL_SIZE = role_pool_size(ResourceLimits())` = **32** (同:998)。`SharedPoolManager` の既定 `maxconn` は `R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW` = 2+2 = 4 (`postgres.py`:530-533)、pool cache の上限は `R2DB_POOL_CACHE_MAX` = 32 (:529) | `r2db-api/src/r2db_api/limits.py`:17・:165、`postgres.py`:523-533、`r2db-api/conformance/conformance_adapter_r2db_http.py`:998・:1476-1484 |
| (3) | **事前拒否ゲート。** `DataService._slot` は `self._active >= self.limits.concurrency` で待たずに `LIMIT_EXCEEDED` 429 を返す (`service.py`:1000-1005)。`acquire_concurrency_slot` (:1011-) を `http.py` が**認証より前**に取り、要求の全体で保持する | `r2db-api/src/r2db_api/service.py`:1000-1024 |
| (4) | **MitateDB のデータ面。** `PostgresBackend.__init__` が `self._runtime` / `self._developer` の **2 本**を持つ (`backend_postgres.py`:272-273)。プール無しである旨は module 冒頭 :71-74 が明記する。直列化は `ApplicationCell._lock = RLock()` (`cell.py`:448) で、`with self._lock:` は同ファイルに **38 箇所**、`_lock.acquire(` / `_lock.release(` の直呼びは **0 件**、`cell.py` の外からこの属性を触るコードも **0 件** (他 module の `self._lock` は `control_auth.py`・`auth.py` の別 object)。**再入で使う箇所が在る** (:1149 のコメントが「`RLock` の再入として無害」と述べる)。**帰結**: 待ちを数える形は (i) 38 箇所を書き換える、(ii) `RLock` と同じ context-manager 面を持つ計数 wrapper に差し替える、のどちらかである。(ii) は**同一 thread の再入も `acquire_count` に数える** (再入の `acquire(blocking=False)` は必ず成功するので `wait_count` は増えない) | `MitateDB-api/src/mitatedb_api/backend_postgres.py`:71-74・:272-273、`cell.py`:448・:1149 (`grep -c`) |
| (5) | **MitateDB の認証面 pool。** `BoundedConnectionPool.acquire()` は (1) idle の再利用 (:104-113、lock 無し)、(2) `self._lock` の下で `_created < _max_size` を見て新規 (:114-127)、(3) 満杯なら `deadline` の loop で `self._idle.get(timeout=min(0.05, remaining))` を繰り返し、尽きたら `AuthorizationStateUnavailable` (:129-144) の 3 段である。`DEFAULT_MAX_SIZE` は 20。**http / socket の MitateDB plug は `PostgresCredentialStore` に pool を渡さない (`pool=None`)** — 理由は adapter 自身の実測コメントに在る (逐次実行の adapter で idle 接続を持つと cluster の `max_connections` を圧迫した)。**したがってこの pool の統計は harness の経路には出ず、使うのは `main.build_app` の composition root と C-26 である** | `MitateDB-api/src/mitatedb_api/pool.py`:64-176、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:990-1035 |
| (6) | **harness の型。** PERF 行を組むのは `_row` (:705-733) と `_format_row` (:735-751)。plug の起動は `_discover_and_build` (:176-) → `main()` (:982-) が `dsa_testpg.suite_lock(exclusive=True)` と使い捨て cluster を取り (:990-1002)、`_run` (:964) が plug ごとに `_measure_plug` (:754-861) を呼ぶ。op ごとの計測は `_measure_op` (:654-)、同時発行は `_run_concurrent` (:506-) の `asyncio.gather` 1 箇所。`registry.json` の読みは `_load_registry` (:171)。`--concurrency` の定義は `_build_parser` (:958-963)、既定は `--n 100 --warmup 10` (:948-949) | `tools/perf_baseline.py`:171-176・:506・:654・:705-751・:754-861・:936-1012 |
| (7) | **両 http plug の cell の所在。** harness の `_resolve_cell` (:318-344) は `adapter._service._cells[app_id]` → `adapter._control.cells[app_id]` → `adapter._cells[app_id]` の順に探す。r2db は `self._service._cells[app_id]` が `PostgresCell` (`_make_cell` :1467-1485)。MitateDB は `self._cells` (`OrderedDict`、:954) が `ApplicationCell` で、`_cell_factory` (:1037-1043) がそこから引く | `tools/perf_baseline.py`:318-344、`r2db-api/conformance/conformance_adapter_r2db_http.py`:1467-1485、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:954・:1037-1043 |
| (8) | **socket plug は http plug の subclass で、同じ process の同じ app object を提供する。** `R2DBSocketConformanceAdapter(R2DBHttpConformanceAdapter)` (:477-) / `MitateDBSocketConformanceAdapter(MitateDBHttpConformanceAdapter)` (:338-) はいずれも `transport_kind` / `_build_client` / `_surfaces_value` / `_reset_surface_state` だけを上書きし、composition は継承する。実 socket は `socket_harness.start_uvicorn_thread` (:628-) による **uvicorn の thread** が担い、**別 process なのは前段の nginx だけ** (`subprocess.Popen`、:405)。**帰結**: socket plug も in-process の cell / pool を保持しており、`_resolve_cell` はそこへ届く。http 側に `pool_stats()` を定義すれば socket 側も継承してそのまま使える (**監督裁定 2026-09-23: socket でも `POOL` 行を出す**。D-2) | `r2db-api/conformance/conformance_adapter_r2db_socket.py`:477-500・:238-300、`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py`:338-355・:198、`conformance-tests/socket_harness.py`:405・:628-640 |
| (9) | **既存の perf テストは 10 本。** `tools/tests/test_perf_baseline.py` の `test_classify_plug_reads_the_declaration` (:48)、`..._rejects_a_name_declaration_mismatch` (:81)、`..._rejects_an_undeclared_or_unrecognized_transport_kind` (:93)、`test_concurrency_issues_requests_simultaneously` (:119)、`test_k1_uses_the_same_path_as_kn` (:145)、`test_default_n_stays_under_the_rate_bound` (:176)、`test_perf_row_format_is_stable` (:192)、`test_perf_baseline_takes_the_exclusive_lock_and_uses_its_own_cluster` (:215)、`..._restores_the_environment_it_borrowed` (:305)、`..._restores_the_environment_when_run_raises` (:363)。module は `importlib` で `perf_baseline.py` をパス指定で読む (:35-38) ので、追加テストも同じ型で書ける | `tools/tests/test_perf_baseline.py` |
| (10) | **正規化規則と pin 可否の判定。** `_normalize` (`MitateDB-api/tests/test_audit_query.py`:3146-、r2db 側も同名・同型) が吸収するのは (a) 先頭 docstring、(b) 両 peer の package 名と両 peer の limits dataclass 名 (同一の placeholder へ)、(c) 行末空白、(d) 連続空行 の 4 つだけで、**識別子・字下げ・数値 literal は吸収しない**。したがって **`_RolePool` / `BoundedConnectionPool` の method 本体は pin できない** (属性名が `self._maxconn` 対 `self._max_size` で異なる)。一方、**plain な引数だけを取る module 水準の純関数** (例: `size` / `acquire_count` / `wait_count` / `wait_total_ms` / `wait_max_ms` / `in_use_peak` を keyword で受けて dict を返す関数) は両 peer で byte 一致に書けるので **pin 可能**である。表は `MitateDB-api/tests/test_audit_query.py`:2179 と `r2db-api/tests/test_audit_query.py`:2393 の両方に在り、件数 pin は **150** (:3037 / :3264)。行を 1 本足すなら**同じ変更セットで**両 peer の表・件数 pin・全内容 assert (`test_isomorphic_target_table_is_pinned_to_its_current_150_rows`、名前も動く) を更新することになる。**監督裁定 2026-09-23: 本件では同型 pin を行わない** — プール (r2db) とロック (MitateDB) で機構が違い、同名の純関数を作ること自体が片側を寄せる操作になるからである。`_ISOMORPHIC_TARGETS` は**両 peer とも 1 行も触らない** | `MitateDB-api/tests/test_audit_query.py`:2179・:3037・:3118-3200、`r2db-api/tests/test_audit_query.py`:2393・:3264 |
| (11) | **変更クラスの実測。** §2.1 の代表パスを `python3 tools/change_class.py` に渡すと `class=B` / `conformance_required=true` (`docs/design/`・`tools/PERF_BASELINE_README.md` が A、両 peer の `src`・`tests`・`conformance` と `tools/perf_baseline.py`・`tools/tests/` が B)。着手時に**触った全パス**で測り直す | `tools/change_class.py` (実行) |
| (12) | **rate の算術 (K の sweep に掛かる事実)。** `DataService._acquire_rate` は **credential ごと**の 60 秒 window で `requests_per_minute` (既定 **600**) を数える (`service.py`:1059-1066、`limits.py`:18)。harness は op ごとに credential を 1 本発行し、その 1 本に `(warmup + n) * K` 要求を載せる (`perf_baseline.py`:768-861、`_build_parser` の註 :937-947 が同じ算術を述べる)。`--warmup 10 --n 100` のとき値は K=1:110、K=2:220、K=4:440、K=8:**880**、K=16:**1760**、K=32:**3520** である (**事実の記録。判断は監督**) | `r2db-api/src/r2db_api/service.py`:1059-1066、`r2db-api/src/r2db_api/limits.py`:18、`tools/perf_baseline.py`:937-947 |
| (13) | **既存の基準値と判定線。** `DP10`:980-1032 に K=1 / K=3 の `PERF` 21 行が逐語で在る (`commit=9361f1b-dirty`、2026-09-10)。判定線 (`K=3 p50 > 2 × K=1 p50`) は `tools/perf_baseline.py`:23-31 と `DP10`:870 に在り、**この道具は閾値を持たない** (P-8) | `DP10`:840-880・:980-1032、`tools/perf_baseline.py`:23-31 |
| (14) | **`POOL` 行の置き場。** `PERF-README` の `## Output format` は :109 に始まり、`PERF` 行の列の並びを逐語で持ち、21 行という総数も述べる (:109-143)。`## The limits of what these numbers mean` は :144 に始まる | `PERF-README`:109-144 |

### 1.4 却下した代替案 (監督確定、蒸し返さない)

- **(1) 計測せずに寸法を変える** — `RM`:305 の P-8、`RM`:448 の R-20 に反する。
- **(2) `pg_stat_activity` の `wait_event` を読む** — 待ちの主体 (プール / lock / threadpool) を区別できない。
- **(3) MitateDB のデータ面をプール化する** — 設計変更であり本件 (計測) の範囲外。計測の結果で決める。
- **(4) socket 転送の plug から統計を取るために HTTP endpoint を足す** — 契約面に計測用の口を足すことになるので却下。

### 1.5 未確定

- **無し** (Class B)。

## 2. WP-1 — 両 peer に取得待ちの counter を置き、harness に `POOL` 行を足す (実装担当)

**目的**: 「どこで待っているか」を数字で出せる形にする。**寸法は 1 つも変えない。**

**読むべき正本**: §1.1 (守る条件) / §1.2 (D-1〜D-7) / §1.3 (実測) / §1.4 (却下案)。規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.3〜§1.6・§1.10、性能計測の同時実行の禁止は同 §2 の 19。

### 2.1 触ってよいパス

- `r2db-api/src/r2db_api/postgres.py` — `_RolePool` の統計 (D-1) と `SharedPoolManager.stats()` だけ。**`maxconn` / `_DEFAULT_ACQUIRE_TIMEOUT_S` / `_DEFAULT_CONNECT_TIMEOUT_S` / eviction・LRU の条件・`retire()` / `_connect()` の中身は 1 つも変えない。** 待ちの枝 (§1.3 の (1) の :345) の `timeout` 値と例外の型・文言も変えない。
- `MitateDB-api/src/mitatedb_api/pool.py` — `BoundedConnectionPool` の統計と `stats()` だけ (D-1)。`_max_size` / `acquire_timeout` / fail-closed の例外 (`AuthorizationStateUnavailable`) の型・文言・発火条件を変えない。
- `MitateDB-api/src/mitatedb_api/cell.py` — `ApplicationCell` の `RLock` の**取得待ちの計数だけ** (D-1)。**`with self._lock:` が覆う範囲 (38 箇所) を 1 箇所も広げない・狭めない**、再入の可否を変えない、`_limit_gate` / `_rate_lock` / `_active_lock` には触らない。
- `r2db-api/tests/test_r78_pool_wait_stats.py` / `MitateDB-api/tests/test_r78_pool_wait_stats.py` — **新規**。D-4 のテスト。
- `tools/perf_baseline.py` — `POOL` 行の追加 (D-2) だけ。**`PERF` 行の列名・並び・書式 (`:.3f` / `:.2f`)・行数・`--concurrency` の既存の意味・`suite_lock` / 使い捨て cluster の扱い・`_run_self_check` を 1 文字も変えない。**
- `tools/tests/test_perf_baseline.py` — `POOL` 行の形式と「socket では出ない」のテストを追加する。**既存 10 本 (§1.3 の (9)) の本体は変えない。**
- `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` — **`pool_stats()` の追加だけ** (D-2)。plug の composition・profile・停止点・`transport_kind` を 1 つも変えない。
- `r2db-api/conformance/conformance_adapter_r2db_http.py` — **`pool_stats()` の追加**と、**`_make_cell` の `pool_size=2` を `DSA_PERF_POOL_SIZE` (正整数) が在るときだけその値にする 1 箇所** (D-2 の追補)。**env が無いときの値は 2 のまま**で、plug の composition・profile・停止点・`transport_kind`・`_DEFAULT_PLATFORM_POOL_SIZE` は 1 つも変えない。
- `r2db-api/conformance/conformance_adapter_r2db_socket.py` / `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` — **socket plug は http plug から `pool_stats()` を継承してそのまま使う** (D-2、§1.3 の (8))。**差分が 0 で済むならこの 2 ファイルは触らない。**
- `tools/PERF_BASELINE_README.md` — `## Output format` (§1.3 の (14)) に `POOL` 行の説明と socket で出ない理由を足す (D-6)。既存の `PERF` 行の記述と 21 行の総数を書き換えない。
- `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` — **新規。WP-1 では骨 (§1 目的と方法、§2 実測 (空)、§3 事実 (空)、§4 判断 (空)) だけを置く。** §2〜§4 は WP-2 で監督が埋める。**判断を先に書かない。**
- `docs/code-history/` — コメントの来歴検査 (`tools/check_comment_provenance.py --register`) が求める記録が要る場合だけ、その 1 箇所。

**これ以外は 0 件。** とくに `spec/`・`conformance-tests/`・`security/`・両 peer の `migrations`・`main.py`・`service.py` / `http.py`・`limits.py` / `config.py`・`RM` を触らない (変異での一時編集は別。`mutate.py` が復元する)。**既存の検査が新しいコードで赤になったら直さず報告する** (§1.5 の 37)。

### 2.2 完了条件 (17 件)

| # | 完了条件 |
|---|---|
| 1 | **(D-1)** r2db の `_RolePool` が `acquire_count` / `wait_count` / `wait_total_ms` / `wait_max_ms` / `in_use_peak` / `size` を持ち、**統計専用の `threading.Lock` の中の整数 (および float) 加算だけ**で更新する (既存の `self._lock` を fast path に足さない。§1.3 の (1))。`size` は当該 pool の `maxconn`。**実 PostgreSQL** で `maxconn=1` の pool を作り、1 本目を保持したまま 2 本目を取りに行かせ、**`wait_count` が 1 増え `wait_max_ms` > 0** になることを観測する (`acquire_timeout` を短くした pool を使ってよい。待ちを入れずに counter を直接叩いて代替しない。§1.5 の 52) |
| 2 | **(D-1・D-4)** 待ちが起きない経路では `wait_count` == 0 かつ `wait_total_ms` == 0.0 である (`maxconn` に余裕のある pool で N 回取得・返却し、`acquire_count` == N、`wait_count` == 0) |
| 3 | **(D-1・D-4)** `in_use_peak` が同時に貸し出された本数の最大を保つ (2 本を同時に保持した後に両方返し、`in_use_peak` == 2 が残る) |
| 4 | **(D-1)** `SharedPoolManager.stats()` が **`"<application_id>/<role>"` の文字列を鍵とする dict** を返し、**値の dict の鍵の集合が §1.2 の D-1 の 6 つ**である (集合と鍵の形の両方を pin する。余分な鍵も欠けた鍵も赤)。2 つの application の pool がキャッシュに在るとき**互いに潰し合わない**ことを観測する。キャッシュに pool が無いときは空を返す |
| 5 | **(D-1)** MitateDB の `BoundedConnectionPool` が**同じ 6 つ**を同じ名前で持ち、`stats()` が同じ鍵の dict を返す。満杯で待つ枝 (§1.3 の (5) の (3) 段) に入ったときだけ `wait_count` が増える。`AuthorizationStateUnavailable` の発火条件・文言は変わらない |
| 6 | **(D-1)** MitateDB の `ApplicationCell` の `RLock` の取得待ちが `wait_count` / `wait_total_ms` / `wait_max_ms` として数えられ (取得の総数の鍵は **`lock_acquire_count`** とし、docstring が「同一 thread の再入も数える」と明記する)、**`acquire(blocking=False)` を先に試し、失敗したときだけ時刻を取って blocking で取り直す**形である。2 thread で同じ cell を叩いて `wait_count` ≥ 1 を観測し、**単独 thread では `wait_count` == 0** であることも観測する。**`with self._lock:` の覆う範囲と再入の可否が基点と同じ**であることを `git diff` で示す (§1.3 の (4)) |
| 7 | **(D-2 の追補)** r2db の `-http` plug が `DSA_PERF_POOL_SIZE` (正整数) を読み、**在ればその値、無ければ 2** を `PostgresCell` の `pool_size` に渡す。両方の場合を観測する (値は `PostgresCell` の実際の pool の `size` で確かめる。env を読んだことの代理指標にしない。§1.5 の 52)。**不正な値 (0・負・非数) のときの扱いは実装裁量だが、conformance の既定の挙動を変えない。** 併せて **監査照合**: 両 peer の `_ISOMORPHIC_TARGETS` の差分が **0 行** (§1.3 の (10) の監督裁定) |
| 8 | **(D-2)** `tools/perf_baseline.py` が各 (plug, op) の計測の**後**に、plug が `pool_stats()` を持つときだけ §1.2 の D-2 の書式で `POOL` 行を出す。列の名前・並びは D-2 のとおり。MitateDB のデータ面は `role=` の代わりに `lock=` を出す。**stub の adapter で形式を pin する** (実 plug の起動に依らないテスト) |
| 9 | **(D-2・守る条件 (c)) 監査照合**: `PERF` 行の列名・並び・書式・行数と `--concurrency` の既存の意味が 1 文字も変わっていない。`test_perf_row_format_is_stable` (§1.3 の (9)) が緑のまま。`git diff` で示す |
| 10 | **(D-2)** **socket 転送の plug でも `POOL` 行が出る** (§1.3 の (8) の監督裁定)。stub の adapter が `transport_kind == "socket"` を宣言していても行が出ることを観測する |
| 11 | **(D-2)** 両 `-http` plug が `pool_stats()` を持ち、r2db は role ごとの行を、MitateDB は cell の lock の行を返す。`-socket` plug はそれを継承する。plug の composition・`transport_kind`・profile と、**env が無いときの `pool_size=2`** は 1 つも変わっていない (`git diff` で示す) |
| 12 | **(守る条件 (b)) 監査照合**: 計測のための DB 往復・ログ出力・thread・timer を 1 つも足していない (counter は lock の中の加算だけ)。`git diff` で両 peer の `src` の差分を逐語で示し、**新しい `psycopg` の呼び・`SELECT`・`print`・`logging` が 0 件**であることを示す |
| 13 | **(D-6)** `tools/PERF_BASELINE_README.md` の `## Output format` に `POOL` 行の書式と、**「socket 転送も同じ process なので統計が取れる。別 process なのは前段の nginx だけである」**旨、および `DSA_PERF_POOL_SIZE` の説明が在り、`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` が §1〜§4 の骨を持つ (§2〜§4 は空欄。**判断を書かない**)。`tools/check_doc_refs.py` が 0 dangling |
| 14 | **(D-7) 監査照合**: `python3 tools/check_comment_provenance.py --base 088be85 <触った src の 3 パス>` の FAIL 行が **§4.1 (1) だけ**で、(2)・(3)・(5)・§9e・`#:` の行が **0 行**。`--register` が緑。出力を逐語で報告に残す。(2) が出たら**止めて報告する**。**worktree を cwd にして走らせる** |
| 15 | **監査照合**: `python3 tools/change_class.py <触った全パス>` が `class=B`、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged。ホスト名・実 DSN・作業機の絶対パスを新規の文書とテストに書いていない (§1.9、§2 の 13) |
| 16 | **監査照合**: 報告前に `r2db-api/tests -q` を **1 回**、`MitateDB-api/tests -q` を **1 回**、`tools/tests -q` を **1 回**、`conformance-tests -q` を **1 回** 回して緑 (§1.3 の (11) の `conformance_required=true`)。集計行を逐語で報告に残す (**完了ゲートは監督**) |
| 17 | §2.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み (§1.4 の 29〜31)。かつ §2.3 の対応表に**対応の無い行が無い** |

### 2.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) |
|---|---|
| 1 | **M1**: `_RolePool` の満杯の枝 (§1.3 の (1) の :345 の周り) から `wait_count` / `wait_max_ms` の更新を落とす → 完了条件 1 のテストが赤 |
| 2 | **M2**: `wait_count` を待ちの枝ではなく `_acquire` の入口で**無条件に**加算する → 完了条件 2 のテスト (待ちが無ければ 0) が赤 |
| 3 | **M3**: `in_use_peak` の更新を `max(...)` から**最後の値の代入**に差し替える → 完了条件 3 のテストが赤 |
| 4 | **M4**: `SharedPoolManager.stats()` の返す dict から鍵を 1 つ (`in_use_peak`) 落とす → 完了条件 4 の鍵集合 pin が赤 |
| 5 | **M5**: `BoundedConnectionPool` の待ちの枝から `wait_count` の更新を落とす → 完了条件 5 のテストが赤 |
| 6 | **M6**: cell の lock の計数から `acquire(blocking=False)` の先行試行を外し、常に blocking で取る (待ちの時刻を取らない) → 完了条件 6 のテストが赤 |
| 7 | **M7**: r2db の `-http` plug から `DSA_PERF_POOL_SIZE` の読みを外し、常に 2 を渡す → 完了条件 7 のテストが赤 |
| 8 | **M8**: `POOL` 行の列名を 1 つ変える (例 `wait_max_ms=` → `max_wait_ms=`) → 完了条件 8 の形式テストが赤 |
| 10 | **M9**: harness の `POOL` 行の出力を `transport != "socket"` で条件付ける → 完了条件 10 のテストが赤 |
| 11 | **M10**: `-http` plug の `pool_stats()` を消す → 完了条件 11 のテストが赤 |
| 9・12・13・14・15・16・17 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す) |

- **M1〜M10 が赤にする test id は新規テストの名前**なので、実装担当が §2.2 の各行に対応するテストを作り、その id を `mutations` の `tests` に **1 件だけ**書く (§1.5 の 40。`mutate.py` は最初の失敗で止まる)。
- **peer をまたぐ変異と `tools/` の変異は別の run に分ける** (`mutate.py` は最初の失敗で止まるので、1 run に複数 peer の suite を混ぜない)。

### 2.4 道具の引数

`$SP` (自分の scratchpad) を export しておく。`pt.py` / `mutate.py` は main checkout を cwd にして走らせ、`-C` で worktree を指す (**渡し忘れると main を測る**)。

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r78 -- r2db-api/tests/test_r78_pool_wait_stats.py MitateDB-api/tests/test_r78_pool_wait_stats.py tools/tests/test_perf_baseline.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r78 -- r2db-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r78 -- MitateDB-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r78 -- tools/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r78 -- conformance-tests -q
tools/dev/mutate.py "$SP/r78-mutations.json" -C .claude/worktrees/r78 --wait 1800
```

worktree を cwd にして走らせるもの (この worktree に `.venv` は無いので `python3` で走らせる):

```bash
python3 tools/check_comment_provenance.py --base 088be85 r2db-api/src/r2db_api/postgres.py MitateDB-api/src/mitatedb_api/pool.py MitateDB-api/src/mitatedb_api/cell.py
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- worktree から subprocess を起こすテストが在る場合の `PYTHONPATH` は **`OPERATING_CONDITIONS.md` §2 の 17** に従って明示する (明示しないと main checkout の `src` を測る)。
- **`pytest` の直接実行・`tools/perf_baseline.py` の実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。`gate.py` は他の pytest と同時に走らせると落ちるので、レビュー担当と同時刻に走らせない (§1.3)。**性能計測の実行中は pytest と nginx を走らせない** (§2 の 19)。
- 一時ファイルは `$SP` 配下だけに置く。複数手順のシェル処理は `$SP` の bash スクリプト (bash 3.2 互換) にする。報告は `$SP/r78-report.md` に書く。

## 3. WP-2 — K を振って実測し、`docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` に記録する (**監督が実施する**)

**目的**: 本件の成果物である実測を取り、逐語で残す。**WP-1 の完了ゲートの後に行う。**

### 3.1 手順

1. **他の pytest と nginx を止める** (§2 の 19)。同一ローカル PostgreSQL クラスタと CPU を共有するので、他 worktree の suite が走っていると値が計測ではなく負荷の記録になる。
2. **非退行 (D-5)**: `tools/perf_baseline.py --warmup 10 --n 100 --concurrency 1` と `--concurrency 3` を、**基点 `088be85` の道具**と**本 worktree の道具**のそれぞれで取る。`PERF` 行の p50 の差が **±10% 以内**であることを確かめる (§1.3 の 27)。
3. **K の sweep (D-3)**: 本 worktree の道具で **K ∈ {1, 2, 4, 8, 16, 32}** を、**K ごとに D-3 の表の `--warmup` / `--n`** (K ≤ 4: 10/100、K=8: 5/50、K=16: 5/30、K=32: 3/15) で取る。**K > `concurrency` (= 32) は事前拒否ゲート (§1.3 の (3)) で `LIMIT_EXCEEDED` になるので測らない。** 見るのは両 peer の **PostgreSQL 経路の plug** (`r2db-api-http` / `r2db-api-socket` / `MitateDB-api-http` / `MitateDB-api-socket`) である。**r2db は `DSA_PERF_POOL_SIZE=32` と既定 (2) の 2 通りで取る** (D-3)。
4. **記録**: `PERFRUN` / `PERF` / `POOL` 行を**逐語で** `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` §2 に置く (K ごとに小見出し。**K ごとの `--warmup` / `--n` と r2db の pool の寸法を併記し、`n` が小さい K は分散が大きい旨を書く**)。ホスト名・実 DSN・作業機の絶対パスを書かない (§1.9、§2 の 13)。`PERFRUN` の `host=` は既に `<OS/arch>` の形である (§1.3 の (13) の先例)。
5. **事実** (§3): (i) p50 が K に比例して伸びる区間、(ii) `POOL` の待ち (`waits` > 0) が出る K、(iii) r2db と MitateDB の差、(iv) r2db の pool 2 と 32 の差。**事実だけを書く。**
6. **判断** (§4): **監督が書く。** 寸法 (pool の `maxconn`、`concurrency`、role の `CONNECTION LIMIT`)、未プールの経路、`RM`:512 の **R-84** の再検討条件 (「threadpool の混雑が tail latency を決めていると実測できたとき」) の充足を、§2 の数字だけに基づいて判定する。**この節は WP-1 では空欄である。**

### 3.2 設計メモの骨 (WP-1 が置き、WP-2 が埋める)

| 節 | 内容 | 埋める者 |
|---|---|---|
| §1 | 目的と方法 (本書 §1.1 の問題設定、道具と引数、K の並びと K ごとの `--warmup` / `--n`、K > 32 を測らない理由、r2db の pool の寸法 2 通り、合成環境である旨) | WP-1 (骨) / WP-2 (確定) |
| §2 | 実測 (`PERFRUN` / `PERF` / `POOL` の逐語。K ごと) | WP-2 (監督) |
| §3 | 事実 (§3.1 の 5 の (i)〜(iv)) | WP-2 (監督) |
| §4 | 判断 (寸法・未プールの経路・R-84 の再検討条件) | **WP-2 (監督)。WP-1 では見出しと空欄だけ** |

### 3.3 完了条件 (監督が自ら照合する)

1. D-5 の前後比較が取れ、`PERF` の p50 の差が ±10% 以内である (外れたら本書 §6.1 に訂正註として残し、原因を切り分ける)。
2. K ∈ {1, 2, 4, 8, 16, 32} の `PERF` / `POOL` 行が §2 に**逐語で**在り、K ごとの `--warmup` / `--n` と r2db の pool の寸法 (32 と 2) が併記されている。どの run も `LIMIT_EXCEEDED` で欠けていない。
3. §3 が事実だけで書かれており、判断語 (「〜すべき」「〜が原因である」) を含まない。
4. §4 が監督の判断として書かれ、`RM` §8 の R-78 行に結論を追記して閉じる (**行は消さない**)。R-84 の再検討条件に触れる場合は同行にも追記する。

## 4. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **(4-1) 寸法の変更。** pool の `maxconn`、`ResourceLimits.concurrency`、role の `CONNECTION LIMIT` (`RM` の R-52 系) を本書では 1 つも変えない (§1.1 の (a))。変えるかどうかは WP-2 の §4 の判断の後、別の変更セットで監督が決める。
- **(4-2) MitateDB のデータ面のプール化。** §1.4 の (3) のとおり本書の範囲外である。
- **(4-3) conformance plug の既定の `pool_size=2` (§1.3 の (2))。** 本書が足すのは `DSA_PERF_POOL_SIZE` による **harness 専用の上書き**だけで (D-2 の追補)、**env が無いときの既定 2 も production の寸法も変えない**。既定を変えるかどうかは WP-2 の §4 の判断の後、監督が台帳で決める。
- **(4-4) async psycopg への移行 (`RM`:512 の R-84)。** 再検討の**条件の充足を判定する材料**を本書が供給するだけで、移行そのものは行わない。
- **(4-5) `RM`:507-510 の R-79〜R-82** (prepared statement、pipeline、idempotency の往復、スキーマのキャッシュ)。いずれも別件である。
- **(4-6) 台帳 `RM` の R-78 行の追記・引き継ぎ書。** **統合時に監督が行う。**

## 5. レビューと受け入れ

- **設計レビュー 1 回** (本書 §1 に対して、WP-1 の着手前)。観点: 守る条件 (a)〜(d) が D-1〜D-7 で満たされているか、**§1.3 の実測と枠の食い違い** (とくに (1) の fast path の lock、(2) の plug の `pool_size=2`、(4) の `RLock` の計り方と再入、(8) の socket plug の継承と同一 process、(12) の rate の算術。いずれも 2026-09-23 の監督裁定が §1.2 に入っている)、完了条件と変異の対応の穴、`POOL` 行が挙動を変えていないこと。
- **コードレビュー 1 回** (実装担当とは別の起動)。観点: (i) counter が**統計専用の lock** の中の加算だけで、既存の `self._lock` を fast path に足しておらず、DB 往復・ログ・thread も増やしていないこと、(ii) 新規テストの空振り (§1.5 の 32) と代理指標 (§1.5 の 52)、(iii) `with self._lock:` の覆う範囲が基点と同じであること、(iv) `PERF` 行の書式が不変であること、(v) socket plug でも `POOL` 行が出ることの観測、(vi) `DSA_PERF_POOL_SIZE` が無いときの既定が 2 のままで conformance の挙動が不変であること、`_ISOMORPHIC_TARGETS` の差分が 0 行であること、(vii) レビュー担当自身の変異 1〜2 件 (報告に無いもの。ただし完了ゲートと並行させないこと)。
- **受け入れ監査 1 回** (レビュー担当とも別の起動)。**本件は機械証拠 (counter の観測・変異・道具の出力) が多いので 1 回とする。**
- **完了ゲートと性能差分は監督**が行う (`tools/dev/gate.py -C .claude/worktrees/r78`、`tools/perf_baseline.py` を基点と本 worktree で同じ引数。D-5)。監督が集計行と §2.2 を照合して判定する。受理したら **WP-2 (§3)** に進み、その結果をもって台帳 `RM` §8 の R-78 行に追記して閉じる (行は消さない)。

## 6. 記録 (統合時に監督が埋める。§1〜§5 の本文は書き換えない)

### 6.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-23)】`tools/tests/test_no_shared_cluster_defaults.py` の `ADMIN_DSN_ENV` 件数 pin。** 基点 088be85 は R-90 が新規テストファイルを足したのに pin を 27 のまま残しており (root ゲートは `tools/tests` を含まず、追跡前の新規ファイルは `git ls-files` に出ないため pre-commit の木では緑だった)、main では赤だった。監督が hotfix (main `8195672`、27 → 28) で直し、本 WP の新規 `r2db-api/tests/test_r78_pool_wait_stats.py` で 28 → 29 にした (触ってよいパスに追加、§1.5 の 40b)。以後、テストファイルを足す WP は新規ファイルを `git add -N` して `tools/tests` を回し、finalize に `--tools-tests` を付ける。
- **【訂正註 2 (2026-09-23)】`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST`** (`postgres.py` の行ずれ 1451 → 1515) を §1.5 の 40b で同じ変更セットで実測更新した (`#:` 段、件数 1 と site identity 不変)。
- **【訂正註 3 (2026-09-23)】§2.3 の M9。** `_emit_pool_rows` は transport を受け取らないので、実装された変異は plug 名の `-socket` 判定である (socket 抑止の規則は裁定 2 で消えたので、完了条件 10 は stub の pin で足りる)。
- **【監督裁定 1】** コードレビュー 1 (高 1・中 3・低 3) の裁定は `$SP/r78-return-2.md`: `POOL` 行は plug 単位で `PERF` 行の前に出る (文言を実測に)、数値は plug 累積で op ごとに reset しない (README に明記、退去で失われる旨も)、`_CountingRLock` は負の timeout で素の `RLock` と同じ `ValueError` を送出し、残る 2 点の差 (非同期例外の窓、`Condition` に渡せない) を docstring に開示する。
- **【監督裁定 2】** MitateDB の `POOL` 行 (`lock=`) は `size=`/`in_use_peak=` を持たない (RLock 統計に無い概念)。同型 pin はしない (プールとロックで機構が違う)。


### 6.2 実施と受け入れ

- **差分** (commit `d612d50` + main `8195672` の merge `7a7f817`): `r2db-api/src/r2db_api/postgres.py` (`_RolePool` の統計 = `acquire_count`・`wait_count`・`wait_total_ms`・`wait_max_ms`・`in_use_peak`・`size`、統計専用 lock、`SharedPoolManager.stats()` の鍵 `"<application_id>/<role>"`)、`MitateDB-api/src/mitatedb_api/pool.py` (同じ統計)、`MitateDB-api/src/mitatedb_api/cell.py` (`_CountingRLock`: `lock_acquire_count` は再入を含む、`wait_count`/`wait_total_ms`/`wait_max_ms`)、両 http plug の `pool_stats()` (socket は継承、同 process)、r2db http plug の `DSA_PERF_POOL_SIZE` (既定 2 不変)、`tools/perf_baseline.py` の `POOL` 行 (計測後に採取、plug 単位で `PERF` 行の前、plug 累積)、`tools/PERF_BASELINE_README.md`、新規 `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` (骨。§2〜§4 は WP-2)、テスト (両 peer の `test_r78_pool_wait_stats.py`、`tools/tests/test_perf_baseline.py`)、allowlist と件数 pin の実測更新。`tools/change_class.py` → `class=B`、`_ISOMORPHIC_TARGETS` 差分 0。
- **道具の出力行**: `pt: 32 passed` (対象 4 ファイル、差し戻し 2 後)、`pt: 1422 passed` (`r2db-api/tests`)、`pt: 1437 passed, 2 subtests passed` (`MitateDB-api/tests`)、`pt: 601 passed` (`tools/tests`)、`pt: 1104 passed` (`conformance-tests`)、`pt: 89 passed` (`test_c05`)。変異 r2db 6 + MitateDB 2 + tools 2 + M10b + M11 = 12 件、全件 red (M0 は無変異を表現できないので直前の pt 緑で代用)。来歴 `--base 088be85` は 3 src とも §4.1 (1) のみ、`--register` OK。`check_doc_refs` 0、`public_value_scan` 0。
- **性能の非退行 (D-5、監督実測 `$SP/r78-perf-nonregression.md`)**: 基点 main da8d807 と本木のそれぞれの道具で `--warmup 10 --n 100`、K=1/K=3。PostgreSQL 経路 14 系列の p50 差は -8.0% 〜 +7.3% (K=1)、-0.3% 〜 +4.5% (K=3) — ±10% 以内。
- **コードレビュー 1** (高 1・中 3・低 3 → 差し戻し 2、全件反映。差し戻し 1 は実装報告の範囲外の赤 2 件の 40b 更新)。受け入れ監査は機械証拠が多く Class B のため省略 (監督がゲートと対応表を照合)。
- **完了ゲート** (監督単独、main 8195672 を merge した最終の木、`--label r78`): `gate: 3987 passed, 2 subtests passed in 333.83s (0:05:33)`、`judge=PASS`、実行クラスタ差分 0 (直前の main 3976 + 11)。
- **WP-2 (監督、2026-09-23)**: sweep 12 run (K ∈ {1,2,4,8,16,32} × `DSA_PERF_POOL_SIZE` 2/32、§1.2 D-3 の (warmup, n)) を `docs/design/PERF_CONCURRENCY_MEASUREMENT_V0_1.md` v0.2 §2 に逐語で置き、§3 に事実 6 点、§4 に判断 4 点を書いた。要点: r2db は size 32 で pool 待ち 0 なのに p50 は K に比例して伸びる (プールは律速でない、寸法は変えない)、1 process 内の直列化が支配的 (主体の切り分けは R-101)、MitateDB は cell の `RLock` が実測で直列化点 (K ≥ 4 で acquire の 30〜45% が待ち → R-102)。
- **最終判定**: 受け入れ。Class B。台帳 R-78 を閉じ (v1.103)、R-101・R-102 を起票、R-84 行に実測を追記した。
