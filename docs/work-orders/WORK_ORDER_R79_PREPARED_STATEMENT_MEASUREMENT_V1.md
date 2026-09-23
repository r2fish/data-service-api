# 作業指示書 — R-79 prepared statement が実際に効いているかを `pg_prepared_statements` で実測する (計測が成果物)

## 0. 版数・位置づけ

- **v1.1 (2026-09-23)。** WP-1 と WP-2 (§3) の完了を受け、設計メモ `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` v0.2 の **§4 の判断**により、**§3.4 の WP-3 を確定した** (候補 (D) を r2db にだけ適用し、MitateDB は (C))。合わせて **§1.3 に (15)** を、**§4 に (4-7)・(4-8)** を、**§5 に WP-3 の 3 行**を足した。**§1〜§3.3 の既存の本文は 1 行も書き換えていない** — v1.0 の §3.4 の本文は §3.4.6 に引用で残す (§1.8 の 56)。§1.5 の (U-1) は §3.4 で確定した (行は消さない)。訂正註は §6.1 に追記する (§1.8 の 57)。
- **v1.0 (2026-09-23)。** 基点 local main `ce27b52`。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の **R-79** 行 (`RM`:510) で、横断条件は `RM`:308 (**P-8**) と `RM`:451 (**R-20**) である。worktree は `.claude/worktrees/r79` (branch `r79`)。
- **変更クラスは B** (実測: §1.3 の (12)。`class=B` / `conformance_required=true`。`docs/design/`・`tools/PERF_BASELINE_README.md` は A、両 peer の `src`・`tests`・`conformance`、`tools/perf_baseline.py`・`tools/tests/` が B)。**契約は 1.8.0 のまま**で `spec/`・`conformance-tests/`・`security/` の差分は **0**。
- **設計文書は新しく起こさない。** 枠 (D-1〜D-7 と却下案) は §1 にあり、これが監督の確定した決定である (R-62・R-71・R-87・R-78 の先例)。**設計レビュー 1 回**を本書に対して行う。本件の成果物である実測の記録は、新規の設計メモ `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` に置く (**§3 = WP-2、監督が実施する**)。
- **本件は計測と記録が成果物である。** ただし台帳 `RM`:510 の R-79 行は「効かない経路だけを直す」を本件の範囲に含めるので、**修正は WP-3 として本書に予約し、その内容は WP-2 の §4 の判断の後に監督が本書 v1.1 で確定する** (§3.4。今は候補の列挙だけで、完了条件は書かない)。
- **WP-1 (実装担当) と WP-2 (監督) は順に行う。** WP-2 は WP-1 の完了ゲートの後に始まるので、**並行 WP は無く**、触るファイルの重なりの表は置かない (`OPERATING_CONDITIONS.md` §1.2 の 16・17 は該当しない)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`gate.py`・`finalize.py`・`perf_baseline.py` は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。**実装担当の裁量は実装詳細のみ** — §1 の決定・§2.1 の触ってよいパス・§2.2 の完了条件を実装担当が動かさない。

## 1. 枠

### 1.1 問題設定と守るべき条件

**問題**: psycopg 3.3.5 は同じ `(query bytes, param types)` を同じ接続で `prepare_threshold` (既定 5) 回実行すると自動で server-side prepare し、`prepared_max` (既定 100) を超えると LRU で捨てる。両 peer の `src` に `prepare_threshold` / `prepared_max` の指定は **0 件**である。**実運用経路の文が実際に prepared で走っているかを誰も計測していない。**

機構上の事実は §1.3 の (1)〜(5) (**監督が一次資料で確認済み**、F1〜F5) に置く。要点は次の 3 つである。

- **F1 (起草時の裁定 1 で実測に合わせた)**: 両 peer の `_set_timeouts` は `SET LOCAL statement_timeout` / `SET LOCAL lock_timeout` の**値を SQL 本文に焼き込む** (`sql.Literal`)。**可変鍵になるのは `_timeout_ms(deadline)` の戻り値を渡す箇所だけ**である — r2db は 4 箇所すべて、MitateDB は 10 箇所 (§1.3 の (14))。この経路では 2 文が毎回 `PrepareManager` の新しい鍵になり、閾値に届かないまま `_counts` (上限 100) に積もって実文の計数 entry を押し出す。**MitateDB の catalog 読み 8 本の `SET LOCAL` は構築時定数 `_catalog_timeout_ms` を渡すので固定鍵 2 個**であり、**閾値に届けば prepared になり得る** (実際に在るかは WP-2 の実測で見る。D-4 の §3 事実 (ii))。
- **F2**: `Connection.rollback()` (接続が IDLE でないとき) と `Transaction` の rollback (savepoint を含む) は prepared を**全消去**する。commit は消さない。**r2db はこれを checkout ごとに踏む** — `_RolePool._liveness_check` (`postgres.py`:408-428) が貸し出しのたびに `SELECT 1` を打ってから `conn.rollback()` するので、`SELECT 1` の後は INTRANS であり早期 return に掛からず、**毎回 `DEALLOCATE ALL` が走る** (設計レビュー 1 の H-2)。
- `cur.execute(..., prepare=False)` でも鍵は `_counts` に足される。`prepare=False` は汚染の回避にならない。

**守るべき条件**:

- **(a)** 本件は**計測と記録が成果物**である。直すのは計測の後である (`RM`:308 の P-8、`RM`:451 の R-20)。ただし台帳 R-79 行が範囲に含める「効かない経路だけを直す」は **WP-3 として本書に予約**し、内容は WP-2 の §4 の判断の後に監督が本書 v1.1 で確定する (§3.4)。
- **(b)** 計測は挙動を変えない。**hot path に足すのは接続ごとの整数加算 1 回だけ**であり、DB 往復・lock・thread を足さない。`pg_prepared_statements` の読み (probe) は harness からのみ、**計測の後に**行う。
- **(c)** 契約 1.8.0 のまま、`conformance-tests/` の差分は **0**。
- **(d)** 公開規律 (`OPERATING_CONDITIONS.md` §1.9)。ホスト名・実 DSN・実パスを書かない (§2 の 13)。
- **(e)** **psycopg の private 属性 (`_prepared`・`_counts`・`_names`) をどこでも読まない・触らない。** 真実は server 側の `pg_prepared_statements` である。公開 property `prepare_threshold` / `prepared_max` は報告に載せてよい。

### 1.2 決定 (監督確定。D-1〜D-7)

- **D-1 (計数。Class B)。** 両 peer に `psycopg.Cursor` の subclass `CountingCursor` (`execute` / `executemany` を override して接続の counter を +1 して `super()` を呼ぶ) と `psycopg.Connection` の subclass `CountingConnection` (**`execute_count` / `executemany_count`** の整数属性を持ち、`cursor_factory` に上記 cursor を持つ) を置く (属性名は設計レビュー 1 の M-7 の裁定)。**置き場は両 peer の新 module `r2db-api/src/r2db_api/psycopg_counting.py` / `MitateDB-api/src/mitatedb_api/psycopg_counting.py` である** (起草時の裁定 3。**同名・byte 一致**)。`postgres.py` / `backend_postgres.py` / `pool.py` はそこから import する。

  **対象は「接続を要求をまたいで使い回す 4 箇所」に限る** (起草時の裁定 2) — r2db `_RolePool._connect` (`postgres.py`:312)、MitateDB `PostgresBackend.__init__` の 2 本 (`backend_postgres.py`:272-273)、MitateDB `BoundedConnectionPool._new_connection` (`pool.py`:131)。この 4 箇所で `psycopg.connect(...)` を `CountingConnection.connect(...)` に替える。**`ops.py`・`main.py`・per-call の認証 store・`postgres.py`:811 のような 1 呼びで閉じる接続は範囲外である** (§4 の (4-6))。

  **lock は取らない** (接続の利用は pool / cell lock で直列化されている。docstring に明記する)。

  **同一性の固定は `_ISOMORPHIC_TARGETS` ではなく file の sha256 一致で行う** (設計レビュー 1 の H-1・H-5 の裁定)。両 peer の `tests` に **`psycopg_counting.py` の sha256 が両 peer で一致することを assert するテストを 1 本ずつ**置く (先例は `test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` の型)。**理由**: `_ISOMORPHIC_TARGETS` は「別 module に埋め込まれた同名 helper」を正規化して比べる仕組みで、先頭 docstring を落として比べるため module 全体の同一性は押さえられない。**module 全体が byte 一致する本件では file の同一性 pin の方が強く、表への登録は冗長である。** したがって **`_ISOMORPHIC_TARGETS` は両 peer とも 0 行差分**とし、**変更クラスは B のまま**である (§1.3 の (12))。**新 module が R-75〜R-77 系の走査集合 pin (module 一覧) に掛かるかを着手時に grep し、掛かるなら編集前に報告する** (§1.5 の 37)。
- **D-2 (probe)。** `src` に**読み取り専用の probe** を置く。r2db は `SharedPoolManager.prepared_stats()` が各 pool の **idle 接続**を `get_nowait` で全部取り出して probe し、戻す (**in-use の接続は対象外**。計測後は全て idle である)。MitateDB は `PostgresBackend.prepared_stats()` が `_runtime` / `_developer` を probe し、**`cell.py` に足す `ApplicationCell.prepared_stats()` が `with self._lock:` の下でそれへ委譲する** (起草時の裁定 4。backend に `prepared_stats` が無ければ `[]` を返す)。adapter は cell のこの method を呼ぶ。**r2db 側は lock を取らない** — queue から idle 接続を取り出すからである。

  probe は**素の `psycopg.Cursor(conn)`** (counting cursor ではない) で

  ```
  SELECT name, statement, prepare_time, generic_plans, custom_plans FROM pg_prepared_statements ORDER BY prepare_time
  ```

  を **`prepare=False`** で読み、**直後に `conn.commit()`** する。**`rollback()` は F2 (§1.3 の (2)) で cache を消すので禁止**である (docstring と完了条件に書く)。

  **probe は接続が IDLE のときだけ行う** (設計レビュー 1 の L-13 の裁定) — 開始時に `conn.info.transaction_status` を見て、**IDLE でなければ probe せず** `probed` を `false` にし、`transaction_status` にその名前を載せる。**接続ごとに例外を捕え、`finally` で必ず `put_nowait` で pool に戻す** (同 H-4 の裁定) — 例外が出た接続は `probed` を `false` にし、`error` に**例外の class 名だけ**を載せる (**message は載せない**。§1.1 の (d))。

  **`label` は両 peer とも `conn.info.backend_pid` を末尾に付ける** (起草時の裁定 5) — r2db が `<application_id>/<role>@<pid>`、MitateDB が `runtime@<pid>` / `developer@<pid>` である。**再接続が label の変化として見える。**

  戻り値は接続ごとの dict で、**鍵は常に次の 11 個**である (設計レビュー 1 の L-13・H-4 の裁定): `label`・`transaction_status`・`probed`・`execute_count`・`executemany_count`・`prepared` (行数)・`prepared_execs` (Σ `generic_plans` + `custom_plans`)・`prepare_threshold`・`prepared_max`・`prepared_statements` (`name`・`generic_plans`・`custom_plans`・`statement` の先頭 80 文字の一覧)・`error`。probe が成功したときは `probed` が `true` で `error` が `None`、非 IDLE で probe しなかったときと例外のときは `probed` が `false` である。probe の `SELECT` 自身は F3 (§1.3 の (3)) で `_counts` に 1 鍵入るが、`prepare=False` なので prepared にはならず view にも現れない。**この点を docstring に開示する。**
- **D-3 (harness)。** `tools/perf_baseline.py` が各 (plug, op) の計測の**後**に、plug が `prepared_stats()` を持てば接続ごとに 1 行出す。**同じ op の `POOL` 行の後に `PREPARED` 行を出す** (設計レビュー 1 の H-3 の裁定)。

  ```
  PREPARED peer=<peer> plug=<plug> op=<op> conn=<label> executes=<n> executemany=<n> prepared=<n> prepared_execs=<n> share=<prepared_execs/executes を 0.000 形式、executes=0 なら 0.000>
  ```

  列名は `executes=` / `executemany=` である (設計レビュー 1 の M-7 の裁定。`statements` の一語二義を避ける)。**`transaction_status` / `probed` / `error` は dict の鍵であって `PREPARED` 行の列ではない。**

  `share` は「現存する prepared statement の実行数 / その接続の `execute` 総数」であり、**消去 (F2) された分の実行数は数えられないので下界である。** さらに**分母には prepared になり得ない文 (`SET LOCAL`・DDL・`prepare=False` の読み) も入るので構造的な上限があり、1.000 には届き得ない** (同 M-8 の裁定)。**判定は `share` の大小ではなく `PREPSTMT` の一覧 (どの文が prepared に在るか) で行う。** counter は**接続の生涯累積**で、op ごとに reset しない (r2db は pool の接続が op をまたいで残る)。`--prepared-detail` を付けたときだけ、接続ごとの prepared statement を次の形で出す。

  ```
  PREPSTMT peer=<peer> plug=<plug> op=<op> conn=<label> name=<name> generic=<n> custom=<n> stmt=<先頭 80 文字、空白を 1 つに畳む>
  ```

  **出力の行順は先例どおり、plug の `PERF` 行より前に塊で出る** (`_emit_pool_rows` と同じ。設計レビュー 1 の L-10 の裁定)。**「計測の後」は実行順の話であって、出力の行順の話ではない。**

  両 http plug に `prepared_stats()` を置き、socket plug は継承する (R-78 §1.3 の (8) と同じ。§1.3 の (13) で同 plug の `POOL` 行が実際に出ていることを確認済み)。R-78 の `pool_stats()` の置き方 (`r2db-api/conformance/conformance_adapter_r2db_http.py`:3989-3995、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:3048-3060、`tools/perf_baseline.py`:760-800) に倣う。**`PERF` / `POOL` 行の書式は不変である。** ただし **MitateDB の `POOL lock=` の `acquire` は、R-79 以降、先行する op の probe 1 回分を含む** (probe が `ApplicationCell.prepared_stats()` 経由で cell lock を 1 回取るため。設計レビュー 1 の H-3 の裁定)。**この旨を `tools/PERF_BASELINE_README.md` と設計メモ §1 に明記する。**
- **D-4 (計測は監督、記録は設計メモ)。** 完了ゲートの後、監督が両 peer の PostgreSQL 経路の plug (`-http` / `-socket`) で **K=1 (`--warmup 10 --n 100`)** と **K=4 (`--warmup 10 --n 100`)** を **`--prepared-detail` 付き**で取る。r2db は `DSA_PERF_POOL_SIZE` 既定 (2) のみとする。`PERFRUN` / `PERF` / `PREPARED` / `PREPSTMT` 行を**逐語で**設計メモ `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` の §2 に置く。**§3 事実**: (i) 接続・op ごとの `share` (**構造的上限が在るので判定は `PREPSTMT` の一覧で行う**)、(ii) prepared に在る文の形と無い文の形 — **`SET LOCAL` は在るか。とくに MitateDB の catalog 読みの固定鍵の `SET LOCAL` (§1.3 の (14)) が prepared に在るか**、(iii) `prepared` と `executes` の比から見える消去 (F2) の痕跡、(iv) peer の差、(v) K=1 と K=4 の差、(vi) **認証接続** — harness の MitateDB plug は `pool=None` で呼びごとに開いて閉じるので認証文は prepared になり得ないこと、(vii) **r2db の消去が checkout ごとの liveness rollback (`postgres.py`:428) によるものか** (設計レビュー 1 の H-2 の裁定)、(viii) **本計測は plug 1 回につき application 1 個なので、台帳 `RM`:510 の R-79 行の「application ごとに識別子が変わる」条件は観測されない**こと (同 L-11 の裁定)。**§4 判断 (監督)**: 効かない経路の特定と WP-3 の内容。
- **D-5 (性能の非退行)。** 基点 `ce27b52` の K=1 / K=3 は監督が採取済みで、逐語は §1.3 の (13) に在る。統合前に**本 worktree の道具で同じ引数**を取り、`PERF` の p50 の差が **±10% 以内**であること (`OPERATING_CONDITIONS.md` §1.3 の 27)。**判定は p50 ≥ 1 ms の行で行い、p50 < 1 ms の行 (in-process plug) は記録のみとする** (設計レビュー 1 の L-12 の裁定。sub-ms では ±10% が計時の分解能に埋もれる)。
- **D-6 (テスト)。完了条件 1 項目 = 変異 1 つ。** `CountingCursor` / `CountingConnection` の単体 (`execute` で `execute_count` +1、`executemany` で `executemany_count` +1、`cursor_factory` が実際に入っている)、**D-1 の 4 箇所が `CountingConnection` を返す**こと、**両 peer の `psycopg_counting.py` の sha256 が一致する**こと、probe が行を返し **probe 後に接続が IDLE** であること (`conn.info.transaction_status`)、probe が prepared を消さないこと (6 回 probe しても `prepared` が減らない。`commit` → `rollback` の変異で赤)、probe の文自身が view に現れないこと、**同じ文を 6 回実行した接続で `prepared` ≥ 1 かつ `prepared_execs` ≥ 1** であること (計測器が正の値を観測できる = 空振り禁止)、**dict の鍵が 11 個ちょうど**であること、**`label` が `backend_pid` で区別される**こと、**例外時に `finally` で接続が戻る**こと、**非 IDLE では probe しない**こと、**probe が増やす `lock_acquire_count` が probe 回数と一致する**こと、**probe 前後で r2db pool の `acquire_count` / `wait_count` / `in_use_peak` が不変**であること、`PREPARED` 行の書式と `share` の算術 (`tools/tests`、plug の stub)、`--prepared-detail` の有無、socket plug でも行が出ること、`tools/tests` の件数 pin (`tools/tests/test_no_shared_cluster_defaults.py`:275 の **29** ほか。新規テストファイルを足すなら pin を更新し、**`git add -N` してから `tools/tests` を回す**)、`_BACKEND_LAYER_ALLOWLIST` の行ずれ (R-78 の教訓)。
- **D-7 (コメント)。** docstring は現在形で書く。`python3 tools/check_comment_provenance.py --base ce27b52` の FAIL が「**§4.1 (1) 以外が 0 行**」であること。

### 1.3 起草時の実測 (基点 `ce27b52` の現物)

(1)〜(5) は **監督が一次資料で確認済み**の機構上の事実 (F1〜F5) であり、起草者が現物で行番号を再確認した。(6)〜(14) は起草者の実測である。

| # | 観測 | 出所 |
|---|---|---|
| (1) | **監督確認済み (F1)。両 peer の `_set_timeouts` は timeout 値を SQL 本文に焼き込む。** r2db は `_timeout_ms` (:2351-2356) が要求の `deadline` と `time.monotonic()` から残り ms を求め、`_set_timeouts` (:2358-2372) が `sql.Literal(f"{timeout_ms}ms")` で `SET LOCAL statement_timeout` / `SET LOCAL lock_timeout` の 2 文を組む。MitateDB も同型である (`_timeout_ms` :1505-1509、`_set_timeouts` :1511-1523)。値は要求ごとにほぼ毎回違うので、この 2 文は毎回 `PrepareManager` の新しい鍵になり (`_preparing.py` の `key()` = `(query.query, query.types)`、:48-50)、閾値に届かず、かつ `_counts` (上限 100、`_rotate` が最古を捨てる。:37-40・:113-123) に積もって実文の計数 entry を押し出す (entry は自分より新しい鍵が 100 個入ると消える)。MitateDB は R-87 で developer 接続の catalog 読み 8 本の各々が `SET LOCAL` を 2 つ打つが、**その値は構築時定数である** — **起草時の裁定 1 により、この点は (14) の実測を正とする** (固定鍵 2 個であり、可変鍵は deadline 由来の 10 箇所だけ) | `r2db-api/src/r2db_api/postgres.py`:2351-2372、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:1505-1523、`.venv/lib/python3.11/site-packages/psycopg/_preparing.py`:36-50・:113-123 |
| (2) | **監督確認済み (F2)。rollback は prepared を全消去する。commit は消さない。** `Connection.rollback()` は接続が IDLE でないとき `ROLLBACK` の後に `self._prepared.clear()` → `maintain_gen` (= `DEALLOCATE ALL`) を走らせる (`_connection_base.py`:618-621。IDLE なら :617 で早期 return)。`Transaction` の rollback (savepoint を含む) も同じく `clear()` する (`transaction.py`:159-161)。**r2db は checkout ごとにこれを踏む** — `_RolePool._liveness_check` (:408-428) が貸し出しのたびに `SELECT 1` を打ってから :428 で `conn.rollback()` し、`SELECT 1` の後は INTRANS なので早期 return に掛からず毎回 `DEALLOCATE ALL` が走る (`connection()` の全経路が :441 でこれを呼ぶ。設計レビュー 1 の H-2)。ほかの該当経路は MitateDB の各 op の error 分岐 (`self._runtime.rollback()` / `self._developer.rollback()`、`backend_postgres.py` に `rollback()` は 76 箇所)、r2db の pool 返却時の非 IDLE (`postgres.py`:462-463)、r2db の dry_run (`psycopg.Rollback`、:1438・:2096 付近)、`_load_field_constraints` の savepoint の `UndefinedTable` (:1018-1022) である。成功経路は両 peer とも commit で終わる (MitateDB `read` は :1422 で `self._runtime.commit()`、r2db は `with conn.transaction():`)。MitateDB `begin()` の先頭の `rollback()` (:1529) は IDLE なら早期 return で消さない **【訂正註 2026-09-23 WP-1】現物 (WP-1 完了時点) では `_RolePool._liveness_check` は :462-489 (rollback 行は :482)。起草時の実測 (:408-428) は基点 `ce27b52` 時点の行番号のまま残す** | `psycopg/_connection_base.py`:617-621、`psycopg/transaction.py`:159-161、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:1422・:1529、`r2db-api/src/r2db_api/postgres.py`:408-428・:441・:462-463・:1018-1022・:1438 |
| (3) | **監督確認済み (F3)。`prepare=False` でも鍵は `_counts` に入る。** `_maybe_prepare_gen` は `prep is Prepare.NO` の枝でも `maybe_add_to_cache` を必ず呼ぶ (`_cursor_base.py`:302)。`maybe_add_to_cache` は `prepare_threshold is None` のときだけ何もしない (`_preparing.py`:125-127)。**したがって `prepare=False` は `_counts` の汚染の回避にならない** | `psycopg/_cursor_base.py`:275-302、`psycopg/_preparing.py`:125-152 |
| (4) | **監督確認済み (F4)。文の同一性。** `sql.Identifier` の collection / table 名は query bytes に焼き込まれるので、鍵は (接続, 文の形, 識別子) ごとになる。r2db は `_RolePool` (`queue.Queue` FIFO。class は `postgres.py`:235-514、`_acquire` :318-361、`_connect` :312) から毎回借りる。MitateDB のデータ面は application ごとに起動時の持続接続 2 本である (`backend_postgres.py`:271-273)。認証文は両 peer とも固定文字列で、table 識別子も platform 全体で固定である (r2db `_SELECT_BY_ID` `credential_store.py`:147・:356-360、MitateDB `credential_store_postgres.py`:367-420) | `r2db-api/src/r2db_api/postgres.py`:235-361、`r2db-api/src/r2db_api/credential_store.py`:147・:356-360、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:271-273、`MitateDB-api/src/mitatedb_api/credential_store_postgres.py`:367-420 |
| (5) | **監督確認済み (F5)。`pg_prepared_statements` の形。** ローカル PostgreSQL は 16.14。view は `name`・`statement`・`prepare_time`・`parameter_types`・`result_types`・`from_sql`・`generic_plans`・`custom_plans` を持つ (PG14+)。**session ごと**なので接続ごとに読む必要がある。`generic_plans + custom_plans` がその prepared statement の実行回数である | PostgreSQL 16 の同 view。起草時の実測は (6) の (i) |
| (6) | **プロトタイプの実測 (§1.3 の逐語 A)。** 使い捨て PostgreSQL (`tools/testpg/dsa_testpg.py` の `suite_lock(exclusive=False)` + `cluster()`) に `psycopg.Connection` の subclass で接続し、(i)〜(v) を観測した。**(i)** 同じ SELECT を 6 回 → view に 1 行、`generic_plans + custom_plans` = 1 (6 回目のみ prepared で走る)。**(ii)** 値が変わる `SET LOCAL statement_timeout` を transaction 内で 10 回 → view に現れない (行数は 1 のまま)。**(iii)** 非 IDLE (`transaction_status` = 2 = INTRANS) の接続で `conn.rollback()` → view が空 (rows=0)。**(iv)** `prepare=False` の SELECT を 6 回 → view に現れない。**(v)** probe (素の `psycopg.Cursor` + `prepare=False`) の後に `commit()` → view が保たれる。**あわせて `prepare_threshold` = 5、`prepared_max` = 100 を公開 property から読めることと、counting cursor の `statement_count` が 23 (= 6 + 10 + 6 + 1) になることを観測した。** **`cursor_factory` は `__init__` で代入する必要がある** — `psycopg.Connection.__init__` が `self.cursor_factory = Cursor` を無条件に代入するので (`connection.py`:78)、subclass の class 属性だけでは効かない (最初の試行で `statement_count` が 0 のままだった) | `$SP/proto-r79.py` (起草者が実行)、`psycopg/connection.py`:78・:145-146・:255 |
| (7) | **`psycopg.connect(` の全箇所。** `src`: r2db は `ops.py` 15 箇所・`postgres.py`:312 (`_RolePool._connect`)・`postgres.py`:811 (cell open 時の platform-upgrade 確認、pool を通さない 1 回限りの接続)・`control_main.py`:518・`main.py`:281・:373。MitateDB は `ops.py` 15 箇所・`backend_postgres.py`:272-273・`pool.py`:131・`credential_store_postgres.py`:300・`control_credential_store_postgres.py`:85・`control_plane.py`:451・:1070・`application_audit.py`:328・`audit_query.py`:407・`control_audit.py`:214・`control_composition.py`:124・`main.py`:225。conformance adapter: r2db `conformance_adapter_r2db_http.py`:234・:479・:637・:660・:1115・:1878・:2674・:3980 と `real_server_r2db.py` 5 箇所、MitateDB `conformance_adapter_mitatedb_http.py`:238・:393・:421・:526・:577・:590・:907・:1649・:2235・:3039 と `real_server_mitatedb.py` 5 箇所。**これを件数 pin / grep している tests は `MitateDB-api/tests/test_ops_inventory.py`:570-571 の 1 組だけ**で、対象は `ops._inventory_connect` の source text であり D-1 の 4 箇所を含まない。`psycopg.connect` を monkeypatch / `setattr` するテストは **15 件**である (設計レビュー 1 の M-6 で 4 件から差し替え) — r2db 5 件: `tests/test_ops_upgrade.py`:814、`tests/test_ops_apply_platform_migration.py`:1217、`tests/test_ops_verify_declarations.py`:506・:1286・:1310。MitateDB 10 件: `tests/test_ops_upgrade.py`:937、`tests/test_audit_query_reader_errors.py`:105・:118・:206、`tests/test_ops_inventory.py`:585・:1498・:2623、`tests/test_ops_verify_declarations.py`:545・:1315・:1339。**いずれも `ops.py` / audit reader の経路を狙っており D-1 の 4 箇所には掛からない** (着手時に peer suite の緑で確かめる。§2.4) | `grep -rn 'psycopg\.connect(' <src/conformance>`、`grep -rn 'psycopg.connect' <tests>` (起草者が実行) |
| (8) | **`executemany` の使用箇所数は両 peer の `src` で 0 件である** (`grep -rn 'executemany' r2db-api/src MitateDB-api/src` が 0 行)。**帰結**: D-1 の `executemany_count` は実運用経路では常に 0 であり、D-6 の単体テストが唯一の観測点になる (空振り禁止 (`OPERATING_CONDITIONS.md` §1.5 の 32) は単体テストで満たす) | `grep -rn 'executemany' r2db-api/src MitateDB-api/src` (起草者が実行) |
| (9) | **r2db の platform pool は `default_pool_manager` に届かない。** 認証面の各 store (`PostgresCredentialStore` ほか 3 つ) は `SharedPoolManager` を通さず**自前の `_RolePool` を直接構築する** (`credential_store.py`:281・:756・:1116・:1317、いずれも `_RolePool(dsn, schema=..., maxconn=...)`)。`SharedPoolManager.stats()` (`postgres.py`:656-660) が返すのは `self._entries` に在る pool だけである。実測 (§1.3 の逐語 B) でも `POOL` 行の `role=` は `<application_id>/developer` と `<application_id>/runtime` の 2 種類だけで、platform pool の鍵は 1 つも現れない。**MitateDB の `BoundedConnectionPool` も harness 経路には無い** (両 http plug が `pool=None` を渡す。R-78 §1.3 の (5)) | `r2db-api/src/r2db_api/credential_store.py`:281・:756・:1116・:1317、`r2db-api/src/r2db_api/postgres.py`:656-660、§1.3 の逐語 B |
| (10) | **`_ISOMORPHIC_TARGETS` の現在の件数 pin は 156 である。** 表の定義は `r2db-api/tests/test_audit_query.py`:2393 と `MitateDB-api/tests/test_audit_query.py`:2179 で、要素数はいずれも実測 156。件数 assert は r2db :3286 / MitateDB :3059 の `assert len(_ISOMORPHIC_TARGETS) == 156`。全内容 assert は `test_isomorphic_target_table_is_pinned_to_its_current_156_rows` (r2db :2942 / MitateDB :2716) で、**この表自身が `_ISOMORPHIC_TARGETS` の 1 行になっている** (r2db :2416 / MitateDB :2202) ので、**テスト名が変われば表の中身も同じ変更セットで直す**。**設計レビュー 1 の H-1 の裁定により本件はこの表を 1 行も触らない** — 同一性は `psycopg_counting.py` の sha256 一致テストで固定する (D-1) | `r2db-api/tests/test_audit_query.py`:2393・:2416・:2942・:3286、`MitateDB-api/tests/test_audit_query.py`:2179・:2202・:2716・:3059 |
| (11) | **`tools/tests` の件数 pin と `_BACKEND_LAYER_ALLOWLIST` の所在。** 件数 pin は `tools/tests/test_no_shared_cluster_defaults.py`:275 の `assert len(files) == 29` (R-78 の訂正註 1 で 28 → 29 になっている。列挙は `git ls-files` 経由なので**追跡前の新規ファイルは見えない**)。`_BACKEND_LAYER_ALLOWLIST` は `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:127 と `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`:277 に在り、`(module, lineno)` の組で `postgres.py` / `backend_postgres.py`・`backend_sqlite.py` の行を固定する (r2db :544、MitateDB :651)。**`src` に行を挿入すると行番号がずれるので、同じ変更セットで実測更新する** (`OPERATING_CONDITIONS.md` §1.5 の 40b) | `tools/tests/test_no_shared_cluster_defaults.py`:275、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:127・:544、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`:277・:651 |
| (12) | **変更クラスの実測。** §2.1 の代表パスを `python3 tools/change_class.py` に渡すと `class=B` / `conformance_required=true` (`docs/design/`・`tools/PERF_BASELINE_README.md` が A、両 peer の `src`・`tests`・`conformance` と `tools/perf_baseline.py`・`tools/tests/` が B)。**`_ISOMORPHIC_TARGETS` の集合を増やすと `RM` §9 の 8 の表の D 行に当たって Class D になるが、設計レビュー 1 の H-1 の裁定により本件はこの表を 1 行も触らないので B のままである** — 同一性は `psycopg_counting.py` の sha256 一致テスト (D-1) で固定する。同型表は先頭 docstring を落として正規化するので module 全体の同一性を押さえられず、**module 全体が byte 一致する本件では file の同一性 pin の方が強く、表への登録は冗長である。** 着手時に**触った全パス**で測り直す | `tools/change_class.py` (起草者が実行) |
| (13) | **基点 `ce27b52` の K=1 / K=3 の `PERFRUN` / `PERF` (各 21 行)** は §1.3 の逐語 B に逐語で在る (監督が採取。`$SP/perf-base-k1.log` / `$SP/perf-base-k3.log`)。D-5 の判定はこの数字と本 worktree の道具の数字の p50 の差である。同じログの `POOL` 行から (9) の鍵を読んだ | §1.3 の逐語 B |
| (14) | **1 要求あたりの `SET LOCAL` の回数。** r2db は `_set_timeouts` の呼び出しが 4 箇所 (`postgres.py`:875・:1251・:1360・:1829) で、**1 transaction あたり 2 文**である (`statement_timeout` + `lock_timeout`)。MitateDB は `_set_timeouts` の呼び出しが 18 箇所で、うち **8 箇所が R-87 の catalog 読み** (:370・:411・:475・:509・:569・:631・:663・:871) であり、**これらは `self._catalog_timeout_ms` を渡す** — この値は `PostgresBackend.__init__` (:285-287) が構築時に 1 回決める**定数**である。残る 10 箇所 (:711・:945・:1055・:1225・:1409・:1438・:1470・:1538・:1713・:1803) は `_timeout_ms(deadline)` の戻り値を渡し、`deadline` が `None` のときは `_set_timeouts` を呼ばない。**したがって MitateDB の developer 接続には、値が固定の `SET LOCAL` の組と、要求ごとに値が変わる `SET LOCAL` の組の両方が流れる** | `r2db-api/src/r2db_api/postgres.py`:875・:1251・:1360・:1829、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:285-287・:370-871 (catalog 8 箇所)・:711-1803 (deadline 由来 10 箇所) |
| (15) | **(v1.1 の追記。§3.4 の WP-3 の枠の確認。起草者が現物で確認した)。psycopg の `autocommit` の setter は、接続が IDLE のときサーバへ何も送らない。** `Connection.autocommit` の setter は `_set_autocommit` → `set_autocommit` → `self.wait(self._set_autocommit_gen(value))` であり (`connection.py`:496-502)、`_set_autocommit_gen` は `_check_intrans_gen("autocommit")` を通した後に `self._autocommit = bool(value)` を代入するだけである (`_connection_base.py`:184-193)。`_check_intrans_gen` は `pgconn.transaction_status` が IDLE なら (pipeline が無い限り) 何もせず、IDLE でなければ `ProgrammingError` を投げる (:252-267)。**したがって IDLE の接続での `autocommit` の切り替えは client 側の属性の代入だけで、SQL は 1 文も出ない。** 併せて `Connection.rollback()` は `pgconn.transaction_status == IDLE` のとき `_rollback_gen` の中で早期 return し、`self._prepared.clear()` と `maintain_gen` (= `DEALLOCATE ALL`) に届かない (:598-623。§1.3 の (2) の F2 の裏返しであり、§3.4.3 の M27 が `rollback()` を足すだけでは赤にならない理由である) | `.venv/lib/python3.11/site-packages/psycopg/connection.py`:496-502、`.venv/lib/python3.11/site-packages/psycopg/_connection_base.py`:184-193・:252-267・:598-623 |

#### §1.3 の逐語 A — プロトタイプ `$SP/proto-r79.py` の出力 ((6))

```
threshold= 5 max= 100
[i: same SELECT x6] rows=1
    name=_pg3_0 generic=0 custom=1 stmt='SELECT 1 WHERE $1 = $2'
    statement_count= 6
[ii: SET LOCAL x10 (changing literal)] rows=1
    name=_pg3_0 generic=0 custom=1 stmt='SELECT 1 WHERE $1 = $2'
[iv: prepare=False SELECT x6] rows=1
    name=_pg3_0 generic=0 custom=1 stmt='SELECT 1 WHERE $1 = $2'
[v: probe then commit (again)] rows=1
    name=_pg3_0 generic=0 custom=1 stmt='SELECT 1 WHERE $1 = $2'
    transaction_status before rollback = 2
[iii: after conn.rollback()] rows=0
    statement_count(total)= 23
```

#### §1.3 の逐語 B — 基点 `ce27b52` の `PERFRUN` / `PERF` ((13)・D-5)

`--warmup 10 --n 100 --concurrency 1`:

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=ce27b52 date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.115 p95_ms=0.119 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.161 p95_ms=0.215 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.490 p95_ms=0.694 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.120 p95_ms=0.148 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.101 p95_ms=0.116 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.162 p95_ms=0.188 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.126 p95_ms=0.149 backend_calls=16.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=2.562 p95_ms=2.702 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=2.589 p95_ms=2.738 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=2.802 p95_ms=2.955 backend_calls=19.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=6.231 p95_ms=6.576 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=6.011 p95_ms=6.341 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=7.192 p95_ms=7.588 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=6.399 p95_ms=7.073 backend_calls=22.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=6.160 p95_ms=6.607 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=6.118 p95_ms=6.347 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=6.362 p95_ms=6.655 backend_calls=19.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=9.801 p95_ms=11.221 backend_calls=21.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=9.696 p95_ms=11.001 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=10.689 p95_ms=12.081 backend_calls=49.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=9.848 p95_ms=11.220 backend_calls=22.00 concurrency=1
```

`--warmup 10 --n 100 --concurrency 3`:

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=ce27b52 date=2026-09-23
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.205 p95_ms=0.241 backend_calls=1.00 concurrency=3
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.653 p95_ms=0.982 backend_calls=1.00 concurrency=3
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=4.079 p95_ms=6.210 backend_calls=1.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.222 p95_ms=0.297 backend_calls=11.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.166 p95_ms=0.189 backend_calls=7.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.346 p95_ms=0.369 backend_calls=37.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.237 p95_ms=0.267 backend_calls=16.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=5.790 p95_ms=9.828 backend_calls=14.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=5.819 p95_ms=6.194 backend_calls=15.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=6.664 p95_ms=10.094 backend_calls=19.01 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=13.102 p95_ms=17.121 backend_calls=21.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=11.477 p95_ms=13.718 backend_calls=13.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=15.193 p95_ms=16.031 backend_calls=49.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=13.757 p95_ms=19.554 backend_calls=22.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=14.846 p95_ms=16.393 backend_calls=14.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=15.356 p95_ms=17.641 backend_calls=15.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=15.888 p95_ms=16.381 backend_calls=19.01 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=22.752 p95_ms=23.837 backend_calls=21.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=21.886 p95_ms=23.192 backend_calls=13.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=25.939 p95_ms=29.094 backend_calls=49.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=22.676 p95_ms=24.285 backend_calls=22.00 concurrency=3
```

### 1.4 却下した代替案 (監督確定。蒸し返さない)

- **(1) psycopg の private な `_prepared._counts` / `_names` を読む** — private API である。server 側の view で足りる (§1.1 の (e))。
- **(2) `pg_stat_statements` を使う** — 使い捨て cluster の `shared_preload_libraries` を変える必要があり、`tools/testpg/` に波及する。
- **(3) 計測の前に `SET LOCAL` を直す** — `RM`:308 の P-8 に反する。
- **(4) 統計用の HTTP endpoint を足す** — 契約面に計測の口を足すことになる (R-78 §1.4 の (4) と同じ理由)。
- **(5) `src` の `_run` / `_execute` ヘルパで数える** — `cur.execute` を直接呼ぶ箇所を取りこぼす。`cursor_factory` は `conn.cursor()` の全てを覆う。

### 1.5 未確定 (監督判断待ち。両論のまま残す)

- **(U-1) WP-3 の内容。** WP-2 の §4 の判断の後に監督が本書 v1.1 で確定する (§3.4)。候補は次の 3 つである。
  - **(A)** `SET LOCAL … = '<N>ms'` を `SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)` の **1 文・bind parameter** に替える。鍵が安定して自身も prepared になり、往復も 2 → 1 になる。**条件**: 宣言 `execution_ms` の実効上限の意味 (SI-08 / R-87 の確定文) を変えないこと。
  - **(B)** `timeout_ms` を刻み (例: 100ms 切り上げ) に**量子化**して文字列の種類を減らす。
  - **(C)** 何もしない (計測で効いていると分かった場合)。
  - **(D)** **r2db の liveness ping の後始末を `rollback()` 以外にする** (設計レビュー 1 の H-2 の裁定で追加)。`_RolePool._liveness_check` (`postgres.py`:408-428) は checkout ごとに `SELECT 1` → `rollback()` を走らせ、そのたびに `DEALLOCATE ALL` が起きる。例: `autocommit` での ping、`SELECT 1` を `commit()` で閉じる。**条件**: 貸し出す接続が「きれいな状態で始まる」という現在の保証 (R-78 §1.3 の (1) の防御) を弱めないこと。
- **(U-2) 認証面の接続 (r2db の platform pool、MitateDB の `BoundedConnectionPool`) の probe を harness の行に出すか。** 実測は §1.3 の (9) のとおりで、**r2db の platform pool は `default_pool_manager` に届かず、MitateDB の pool は harness 経路に無い。** したがって枠の規則 (「届くなら D-2 の対象に含める」) の条件は成立せず、**D-2 の対象は §1.2 のままである。** これらを別の経路で probe するかどうかは**未確定**であり、WP-1 では行わない。

## 2. WP-1 — 両 peer に文の計数と `pg_prepared_statements` の probe を置き、harness に `PREPARED` 行を足す (実装担当)

**目的**: 「どの接続のどの文が実際に prepared で走っているか」を数字で出せる形にする。**寸法も文の形も 1 つも変えない。**

**読むべき正本**: §1.1 (守る条件) / §1.2 (D-1〜D-7) / §1.3 (実測) / §1.4 (却下案) / §1.5 (未確定)。規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.3〜§1.6・§1.9・§1.10、性能計測の同時実行の禁止は同 §2 の 19。

### 2.1 触ってよいパス

- `r2db-api/src/r2db_api/psycopg_counting.py` / `MitateDB-api/src/mitatedb_api/psycopg_counting.py` — **新規** (起草時の裁定 3)。D-1 の `CountingCursor` / `CountingConnection` の定義だけを置く。**両 peer で同名・byte 一致**であり、peer 固有のものを 1 つも書かない。
- `r2db-api/src/r2db_api/postgres.py` — 上記 module からの import、`_RolePool._connect` (:312) の `psycopg.connect(...)` を `CountingConnection.connect(...)` に替える 1 箇所、`SharedPoolManager.prepared_stats()` の追加 (D-2) だけ。**`maxconn` / `_DEFAULT_ACQUIRE_TIMEOUT_S` / `_DEFAULT_CONNECT_TIMEOUT_S` / eviction・LRU の条件 / `retire()` / `_acquire()` / `_set_timeouts` / R-78 の統計を 1 つも変えない。** `postgres.py`:811 の接続 (cell open 時の platform-upgrade 確認) は D-1 の対象外なので触らない。
- `MitateDB-api/src/mitatedb_api/backend_postgres.py` — 上記 module からの import、`__init__` の 2 本 (:272-273) の置き換え、`PostgresBackend.prepared_stats()` の追加 (D-2) だけ。**`_catalog_timeout_ms` の値・`_timeout_ms` / `_set_timeouts` の本文・rollback / commit の枝を 1 つも変えない** (§1.3 の (2)・(14))。
- `MitateDB-api/src/mitatedb_api/pool.py` — 上記 module からの import と `_new_connection` (:131) の置き換えだけ。`_max_size` / `acquire_timeout` / fail-closed の例外 (`AuthorizationStateUnavailable`) の型・文言・発火条件と R-78 の統計を変えない。
- `MitateDB-api/src/mitatedb_api/cell.py` — **`ApplicationCell.prepared_stats()` を 1 つ足すだけ** (起草時の裁定 4)。`with self._lock:` の下で backend に `prepared_stats` が在れば委譲し、無ければ `[]` を返す読み取り専用の method である。**既存の `with self._lock:` が覆う範囲を 1 箇所も広げない・狭めない**、再入の可否を変えない、`_limit_gate` / `_rate_lock` / `_active_lock` と R-78 の `_CountingRLock` に触らない。
- `r2db-api/tests/test_r79_prepared_stats.py` / `MitateDB-api/tests/test_r79_prepared_stats.py` — **新規**。D-6 のテスト。
- `tools/perf_baseline.py` — `PREPARED` / `PREPSTMT` 行の追加と `--prepared-detail` の追加 (D-3) だけ。**`PERF` 行と `POOL` 行の列名・並び・書式・行数、`--concurrency` の既存の意味、`suite_lock` / 使い捨て cluster の扱い、`_run_self_check` を 1 文字も変えない。**
- `tools/tests/test_perf_baseline.py` — `PREPARED` / `PREPSTMT` 行の形式と `share` の算術、`--prepared-detail` の有無、socket plug でも行が出ることのテストを追加する。**既存のテストの本体は変えない。**
- `r2db-api/conformance/conformance_adapter_r2db_http.py` / `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` — **`prepared_stats()` の追加だけ** (D-3)。plug の composition・profile・停止点・`transport_kind`・`_DEFAULT_PLATFORM_POOL_SIZE`・`DSA_PERF_POOL_SIZE` の扱い・既存の `pool_stats()` を 1 つも変えない。
- `r2db-api/conformance/conformance_adapter_r2db_socket.py` / `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` — **socket plug は http plug から `prepared_stats()` を継承してそのまま使う。差分が 0 で済むならこの 2 ファイルは触らない。**
- **`r2db-api/tests/test_audit_query.py` / `MitateDB-api/tests/test_audit_query.py` は触らない** — 設計レビュー 1 の H-1 の裁定により `_ISOMORPHIC_TARGETS` は両 peer とも **0 行差分**である (D-1、§1.3 の (10)・(12))。同一性は §2.1 の新規テストに置く sha256 一致テストで固定する。
- `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` / `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` — **`_BACKEND_LAYER_ALLOWLIST` の行ずれの実測更新だけ** (§1.3 の (11))。件数と site identity は変えない。
- `tools/tests/test_no_shared_cluster_defaults.py` — **新規テストファイルと新 module を足したことによる件数 pin (:275 の 29) の実測更新だけ。**
- **R-75〜R-77 系の走査集合 pin (module 一覧) を持つテスト** — 新 module `psycopg_counting.py` が走査対象に入ることによる**実測更新だけ**。着手時に grep して所在を確かめ、**掛かるなら編集前に報告する** (§1.5 の 37。掛からなければこの行は 0 件)。
- `tools/PERF_BASELINE_README.md` — `## Output format` (:109) と `## POOL lines (R-78)` (:144) の後に `PREPARED` / `PREPSTMT` 行の説明を足す (D-3)。**`share` が下界であること・counter が接続の生涯累積であること・probe は計測の後に走ること**を書く。既存の `PERF` / `POOL` 行の記述と 21 行の総数を書き換えない。
- `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` — **本書と同じ変更セットで起草済みの骨**である。WP-1 は §1 の記述が実装と食い違っていたときだけ直す。**§2〜§4 を埋めない。判断を先に書かない。**
- `docs/code-history/` — コメントの来歴検査 (`tools/check_comment_provenance.py --register`) が求める記録が要る場合だけ、その 1 箇所。

**これ以外は 0 件。** とくに `spec/`・`conformance-tests/`・`security/`・両 peer の `migrations`・`main.py`・`service.py` / `http.py`・`limits.py` / `config.py`・`ops.py`・`credential_store*.py`・`RM` を触らない (変異での一時編集は別。`mutate.py` が復元する)。**§2.1 に挙げた 2 つの新 module 以外に新しい module を作らない。** **既存の検査が新しいコードで赤になったら直さず報告する** (§1.5 の 37)。

### 2.2 完了条件 (32 件)

| # | 完了条件 |
|---|---|
| 1 | **(D-1)** `CountingCursor.execute` が接続の **`execute_count`** を **+1** する。**実 PostgreSQL** の接続で N 回実行して `execute_count == N` を観測する (counter を直接叩いて代替しない。§1.5 の 52)。**lock を取らず、加算以外に何もしない。** |
| 2 | **(D-1)** `CountingCursor.executemany` が **`executemany_count`** を **+1** する。`src` の実運用経路に `executemany` は 0 件なので (§1.3 の (8))、単体テストで駆動する |
| 3 | **(D-1)** `CountingConnection` の `cursor_factory` が実際に `CountingCursor` であり、`conn.cursor()` が返す object の型で観測する。**`psycopg.Connection.__init__` が `cursor_factory` を無条件に代入するので、class 属性だけでは効かない** (§1.3 の (6)) |
| 4 | **(D-1)** r2db `_RolePool._connect` (`postgres.py`:312) が `CountingConnection` を返す。**pool から借りた接続の型**で観測する (source text や env の代理指標にしない。§1.5 の 52) |
| 5 | **(D-1)** MitateDB `PostgresBackend.__init__` の `_runtime` / `_developer` (`backend_postgres.py`:272-273) が `CountingConnection` である。**属性の型**で観測する |
| 6 | **(D-1)** MitateDB `BoundedConnectionPool._new_connection` (`pool.py`:131) が `CountingConnection` を返す。**pool から借りた接続の型**で観測する |
| 7 | **(D-1・設計レビュー 1 の H-1/H-5)** 両 peer の `src/<pkg>/psycopg_counting.py` の **sha256 が一致する**ことを assert するテストが**両 peer の `tests` に 1 本ずつ**在る (先例 `test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` の型)。**`_ISOMORPHIC_TARGETS` には足さない** |
| 8 | **(D-2・設計レビュー 1 の H-3)** r2db `SharedPoolManager.prepared_stats()` が各 pool の **idle 接続を `get_nowait` で全部取り出して probe し、戻す**。in-use の接続を待たない・奪わない。pool が空のときは空を返す。**probe の前後で当該 pool の `acquire_count` / `wait_count` / `in_use_peak` が 1 つも変わらない**ことを R-78 の `stats()` で観測する (probe が R-78 の計測を汚さない) |
| 9 | **(D-2)** MitateDB `PostgresBackend.prepared_stats()` が `_runtime` / `_developer` を label `runtime@<pid>` / `developer@<pid>` で probe し、**`cell.py` の `ApplicationCell.prepared_stats()` が `with self._lock:` の下でそれへ委譲する** (backend に `prepared_stats` が無ければ `[]`)。adapter は cell のこの method を呼ぶ。**既存の `with self._lock:` の覆う範囲が基点と同じ**であることを `git diff` で示す |
| 10 | **(D-2)** probe は**素の `psycopg.Cursor(conn)`** で **`prepare=False`** で読み、**直後に `conn.commit()`** する。**probe の後に接続が IDLE である** ことを `conn.info.transaction_status` で観測する |
| 11 | **(D-2)** probe が prepared を消さない。**同じ接続に 6 回 probe しても `prepared` が減らない**ことを観測する (`commit` を `rollback` に替える変異で赤になること) |
| 12 | **(D-2)** **probe の `SELECT` 自身が `pg_prepared_statements` に現れない** (`prepare=False` なので prepared にならない)。6 回 probe した後も `prepared_statements` に probe の文が 1 件も無いことを観測する |
| 13 | **(D-2) 空振り禁止 (§1.5 の 32)**: **同じ文を 6 回実行した接続で `prepared` ≥ 1 かつ `prepared_execs` ≥ 1** を観測する。計測器が正の値を観測できることを、実 PostgreSQL で示す |
| 14a | **(D-2・設計レビュー 1 の L-9)** 接続ごとの dict の**鍵の集合が §1.2 の D-2 の 11 個ちょうど**である (`label`・`transaction_status`・`probed`・`execute_count`・`executemany_count`・`prepared`・`prepared_execs`・`prepare_threshold`・`prepared_max`・`prepared_statements`・`error`)。**余分な鍵も欠けた鍵も赤。** `prepared_statements` の各要素は `name`・`generic_plans`・`custom_plans`・`statement` の先頭 80 文字を持つ |
| 14b | **(D-2・設計レビュー 1 の L-9)** **`label` が `conn.info.backend_pid` を末尾に持つ** (r2db `<application_id>/<role>@<pid>`、MitateDB `runtime@<pid>` / `developer@<pid>`)。**同一 pool の 2 つの接続が pid で区別される**ことを、2 本同時に貸し出した pool で観測する |
| 15 | **(D-2・設計レビュー 1 の H-4)** probe が例外を投げても、**`finally` で接続が必ず `put_nowait` で pool に戻る**。例外を注入した接続について `probed` が `false`、`error` が**例外の class 名だけ** (message を含まない) であり、**probe の後に pool から同じ本数を借りられる**ことを観測する |
| 16 | **(D-2・設計レビュー 1 の L-13)** probe は開始時に `conn.info.transaction_status` が **IDLE のときだけ**行う。非 IDLE の接続を渡すと **probe せず**に `probed` が `false`、`transaction_status` にその状態の名前が載ることを観測する (その接続の `prepared` が probe で書き換わらないこと) |
| 17 | **(D-3・設計レビュー 1 の H-3)** MitateDB の probe が増やす **`lock_acquire_count` が probe の回数と一致する** (probe 1 回につき cell lock 1 回)。R-78 の `pool_stats()` の値を probe の前後で読んで差分を観測する |
| 18 | **(D-3)** `tools/perf_baseline.py` が各 (plug, op) の計測の**後**に、plug が `prepared_stats()` を持つときだけ §1.2 の D-3 の書式で `PREPARED` 行を接続ごとに 1 行出し、**同じ op の `POOL` 行の後に置く**。列名は **`executes=` / `executemany=`**。**`share` の算術** (`prepared_execs / executes` を `0.000` 形式、`executes == 0` なら `0.000`) を **stub の adapter** で pin する (実 plug の起動に依らないテスト) |
| 19 | **(D-3)** **`--prepared-detail` を付けたときだけ** `PREPSTMT` 行が出る。`stmt=` は先頭 80 文字で、**空白を 1 つに畳む**。付けないときは 0 行であることも観測する |
| 20 | **(D-3)** **socket 転送の plug でも `PREPARED` 行が出る**。stub の adapter が `transport_kind == "socket"` を宣言していても行が出ることを観測する |
| 21 | **(D-3・守る条件 (c)) 監査照合**: `PERF` 行と `POOL` 行の列名・並び・書式・行数と `--concurrency` の既存の意味が **1 文字も変わっていない**。既存の `test_perf_row_format_is_stable` と R-78 の `POOL` 行のテストが緑のまま。**ただし MitateDB の `POOL lock=` の `acquire` の値は先行 op の probe 1 回分を含む** — この旨が `tools/PERF_BASELINE_README.md` と設計メモ §1 に書かれていること (設計レビュー 1 の H-3)。`git diff` で示す |
| 22 | **(守る条件 (b)・(e)) 監査照合**: hot path に足したのは**接続ごとの整数加算 1 回だけ**である。DB 往復・lock・thread・timer・`print` / `logging` を 1 つも足していない。**psycopg の private 属性 (`_prepared` / `_counts` / `_names`) を読む箇所が `src`・`tests`・`conformance`・`tools` を通して 0 件**である。`git diff` で両 peer の `src` の差分を逐語で示し、grep の 0 件を報告に残す |
| 23 | **(守る条件 (c)) 監査照合**: `spec/`・`conformance-tests/`・`security/` の差分が **0 行**で、契約は **1.8.0** のままである。**両 peer の `tests/test_audit_query.py` の差分も 0 行** (`_ISOMORPHIC_TARGETS` に触らない。設計レビュー 1 の H-1)。`git diff --stat` で示す |
| 24 | **監査照合**: `tools/tests/test_no_shared_cluster_defaults.py`:275 の件数 pin と両 peer の `_BACKEND_LAYER_ALLOWLIST` (§1.3 の (11)) を**実測で**更新した。**新規テストファイルは `git add -N` してから `tools/tests` を回す** (R-78 の訂正註 1)。件数 pin を実測値へ合わせるだけで済ませず、走査対象に入ったことを確認する (§1.5 の 40b) |
| 25 | **(D-6) 監査照合**: `tools/PERF_BASELINE_README.md` に `PREPARED` / `PREPSTMT` 行の書式と、**`share` が下界であり構造的上限を持つこと・counter が接続の生涯累積であること・probe は計測の後に走ること・probe 自身は prepared にならないこと・MitateDB の `POOL lock=` の `acquire` が probe 1 回分を含むこと**が書かれている。`docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` の §2〜§4 が**空のまま**である。`python3 tools/check_doc_refs.py` が 0 dangling |
| 26 | **(D-7) 監査照合**: `python3 tools/check_comment_provenance.py --base ce27b52 <触った src の 6 パス>` の FAIL 行が **§4.1 (1) だけ**で、(2)・(3)・(5)・§9e・`#:` の行が **0 行**。`--register` が緑。出力を逐語で報告に残す。**(2) が出たら止めて報告する。worktree を cwd にして走らせる** |
| 27 | **監査照合**: `python3 tools/change_class.py <触った全パス>` が `class=B`、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged。ホスト名・実 DSN・作業機の絶対パスを新規の文書とテストに書いていない (§1.9、§2 の 13) |
| 28 | **監査照合**: 報告前に `r2db-api/tests -q` を **1 回**、`MitateDB-api/tests -q` を **1 回**、`tools/tests -q` を **1 回**、`conformance-tests -q` を **1 回** 回して緑 (§1.3 の (12) の `conformance_required=true`)。集計行を逐語で報告に残す (**完了ゲートは監督**) |
| 29 | **(起草時の裁定 3) 手動検証 (`mutate.py` では扱えない)**: 新 module `psycopg_counting.py` が R-75〜R-77 系の走査集合 pin (module 一覧) に**入っている**こと。**pt.py で手動に確かめる** — 当該 module に probe (走査が検出するはずの一行) を置いて対象テストが**赤**になることを観測し、probe を削除して**緑**に戻す。実行した 2 回の集計行を逐語で報告に残す。**掛かる pin が 1 つも無いと分かったらその grep の結果を報告に残す** (§1.5 の 37) |
| 30 | **(設計レビュー 1 の M-6) 監査照合**: §1.3 の (7) の **15 件**の `psycopg.connect` の monkeypatch / `setattr` の下で **D-1 の 4 箇所が呼ばれない**ことを、両 peer の suite が緑であることで確かめた。**赤が出たら直さず報告して止まる** (§1.5 の 37) |
| 31 | §2.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み (§1.4 の 29〜31)。かつ §2.3 の対応表に**対応の無い行が無い** |

### 2.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) |
|---|---|
| 1 | **M1**: `CountingCursor.execute` の override から `execute_count` の加算を落とす (`super()` はそのまま) → 完了条件 1 のテストが赤 |
| 2 | **M2**: `executemany` の override から `executemany_count` の加算を落とす → 完了条件 2 のテストが赤 |
| 3 | **M3**: `CountingConnection.__init__` から `cursor_factory` の代入を落とす (psycopg の既定 `Cursor` に戻る) → 完了条件 3 のテストが赤 |
| 4 | **M4**: r2db `_RolePool._connect` を素の `psycopg.connect(...)` に戻す → 完了条件 4 のテストが赤 |
| 5 | **M5**: MitateDB `PostgresBackend.__init__` の `_developer` を素の `psycopg.connect(...)` に戻す → 完了条件 5 のテストが赤 |
| 6 | **M6**: MitateDB `BoundedConnectionPool._new_connection` を素の `psycopg.connect(...)` に戻す → 完了条件 6 のテストが赤 |
| 7 | **M7**: 片側の `psycopg_counting.py` の docstring を 1 文字変える → 完了条件 7 の sha256 一致テストが赤 |
| 8 | **M8**: r2db `prepared_stats()` が接続を pool から `_acquire()` で借りる (R-78 の `acquire_count` が動く) → 完了条件 8 のテストが赤 |
| 9 | **M9**: `ApplicationCell.prepared_stats()` の `with self._lock:` を外す (lock 無しで委譲する) → 完了条件 9 のテストが赤 |
| 10 | **M10**: probe の末尾の `conn.commit()` を落とす (接続が INTRANS のまま残る) → 完了条件 10 のテストが赤 |
| 11 | **M11**: probe の末尾の `conn.commit()` を `conn.rollback()` に替える → 完了条件 11 のテストが赤 |
| 12 | **M12**: probe の `SELECT` の `prepare=False` を外す → 完了条件 12 のテストが赤 |
| 13 | **M13**: probe の `prepared_execs` を `generic_plans + custom_plans` の和ではなく定数 0 にする → 完了条件 13 のテストが赤 |
| 14a | **M14a**: 接続ごとの dict に鍵を 1 つ足す (例 `statement`) → 完了条件 14a の鍵集合 pin が赤 |
| 14b | **M14b**: `label` から `@<backend_pid>` を落とす (同一 pool の 2 接続が同じ label になる) → 完了条件 14b のテストが赤 |
| 15 | **M15**: probe の `finally` を外す (例外の接続が pool に戻らない) → 完了条件 15 のテストが赤 |
| 16 | **M16**: probe 開始時の `transaction_status` の判定を外し、非 IDLE でも probe する → 完了条件 16 のテストが赤 |
| 17 | **M17**: `ApplicationCell.prepared_stats()` が backend の `prepared_stats` を 2 回呼ぶ (lock 取得が 2 倍になる) → 完了条件 17 のテストが赤 |
| 18 | **M18**: `PREPARED` 行の列名を 1 つ変える (例 `prepared_execs=` → `execs=`) → 完了条件 18 の形式テストが赤 |
| 19 | **M19**: `--prepared-detail` の有無に関わらず `PREPSTMT` 行を出す → 完了条件 19 のテストが赤 |
| 20 | **M20**: harness の `PREPARED` 行の出力を plug 名の `-socket` で抑止する → 完了条件 20 のテストが赤 |
| 21・22・23・24・25・26・27・28・30 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す) |
| 29 | **手動検証 (`mutate.py` では扱えない)** — 「新 module が走査対象に入る」型の条件は変異の注入と復元で表現できないので、**`pt.py` で probe を置く → 赤 → 削除 → 緑**の 2 回の実行で確かめる (起草時の裁定 3)。集計行を逐語で報告に残す |
| 31 | **対応表の完全性** (§1.5 の 40。本表に対応の無い完了条件の行が 1 つも無いこと) |

- **M1〜M20 が赤にする test id は新規テストの名前**なので、実装担当が §2.2 の各行に対応するテストを作り、その id を `mutations` の `tests` に **1 件だけ**書く (§1.5 の 40。`mutate.py` は最初の失敗で止まる)。
- **peer をまたぐ変異と `tools/` の変異は別の run に分ける** (1 run に複数 peer の suite を混ぜない)。変異ファイルは `$SP/r79-mutations.json` に置き、形は R-78 §2.3 に倣う。

### 2.4 道具の引数

`$SP` (自分の scratchpad) を export しておく。`pt.py` / `mutate.py` は main checkout を cwd にして走らせ、`-C` で worktree を指す (**渡し忘れると main を測る**)。

```bash
tools/dev/pt.py -C .claude/worktrees/r79 --wait 300 -- r2db-api/tests/test_r79_prepared_stats.py MitateDB-api/tests/test_r79_prepared_stats.py tools/tests/test_perf_baseline.py -q
tools/dev/pt.py -C .claude/worktrees/r79 --wait 1800 -- r2db-api/tests -q
tools/dev/pt.py -C .claude/worktrees/r79 --wait 1800 -- MitateDB-api/tests -q
tools/dev/pt.py -C .claude/worktrees/r79 --wait 1800 -- tools/tests -q
tools/dev/pt.py -C .claude/worktrees/r79 --wait 1800 -- conformance-tests -q
tools/dev/mutate.py "$SP/r79-mutations.json" -C .claude/worktrees/r79 --wait 300
```

- **`tools/tests` は新規テストファイルを `git add -N` した後に別実行する** (R-78 の訂正註 1。列挙が `git ls-files` 経由なので追跡前のファイルは見えない)。
- **着手時の確認 (設計レビュー 1 の M-6)**: §1.3 の (7) の **15 件**の `psycopg.connect` の monkeypatch / `setattr` の下で **D-1 の 4 箇所が呼ばれない**ことを、両 peer の suite (`r2db-api/tests -q` / `MitateDB-api/tests -q`) の緑で確かめる。**赤が出たら直さず報告して止まる** (§1.5 の 37)。
- worktree を cwd にして走らせるもの (この worktree に `.venv` は無いので `python3` で走らせる):

```bash
python3 tools/check_comment_provenance.py --base ce27b52 r2db-api/src/r2db_api/psycopg_counting.py r2db-api/src/r2db_api/postgres.py MitateDB-api/src/mitatedb_api/psycopg_counting.py MitateDB-api/src/mitatedb_api/backend_postgres.py MitateDB-api/src/mitatedb_api/pool.py MitateDB-api/src/mitatedb_api/cell.py
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- worktree から subprocess を起こすテストが在る場合の `PYTHONPATH` は **`OPERATING_CONDITIONS.md` §2 の 17** に従って明示する (明示しないと main checkout の `src` を測る)。
- **`pytest` の直接実行・`tools/perf_baseline.py` の実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。`gate.py` は他の pytest と同時に走らせると落ちるので、レビュー担当と同時刻に走らせない (§1.3)。**性能計測の実行中は pytest と nginx を走らせない** (§2 の 19)。
- 一時ファイルは `$SP` 配下だけに置く。複数手順のシェル処理は `$SP` の bash スクリプト (bash 3.2 互換) にする。報告は `$SP/r79-report.md` に書く。

## 3. WP-2 — K=1 / K=4 で実測し、`docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` に記録する (**監督が実施する**)

**目的**: 本件の成果物である実測を取り、逐語で残す。**WP-1 の完了ゲートの後に行う。**

### 3.1 手順

1. **他の pytest と nginx を止める** (§2 の 19)。同一ローカル PostgreSQL クラスタと CPU を共有するので、他 worktree の suite が走っていると値が計測ではなく負荷の記録になる。
2. **非退行 (D-5)**: `tools/perf_baseline.py --warmup 10 --n 100 --concurrency 1` と `--concurrency 3` を**本 worktree の道具**で取り、§1.3 の逐語 B (基点 `ce27b52`) と `PERF` の p50 を比べる。差が **±10% 以内**であることを確かめる (§1.3 の 27)。
3. **計測 (D-4)**: 本 worktree の道具で **K=1** と **K=4** を、いずれも `--warmup 10 --n 100 --prepared-detail` で取る。見るのは両 peer の **PostgreSQL 経路の plug** (`r2db-api-http` / `r2db-api-socket` / `MitateDB-api-http` / `MitateDB-api-socket`) である。**r2db は `DSA_PERF_POOL_SIZE` 既定 (2) のみ**とする。K=4 の `(warmup + n) * K` は 440 で、credential ごと毎分 600 件の bound の内に収まる (R-78 §1.3 の (12))。
4. **記録**: `PERFRUN` / `PERF` / `PREPARED` / `PREPSTMT` 行を**逐語で** §2 に置く (K ごとに小見出し)。ホスト名・実 DSN・作業機の絶対パスを書かない (§1.9、§2 の 13)。`PERFRUN` の `host=` は既に `<OS/arch>` の形である。
5. **事実** (§3): (i) 接続・op ごとの `share`、(ii) prepared に在る文の形と無い文の形 — **`SET LOCAL` は在るか。とくに MitateDB の catalog 読みの固定鍵の `SET LOCAL` (§1.3 の (14)) が prepared に在るか**、(iii) `prepared` と `executes` の比から見える消去 (F2) の痕跡、(iv) peer の差、(v) K=1 と K=4 の差、(vii) **r2db の消去が checkout ごとの liveness rollback (`postgres.py`:428) によるものか** (設計レビュー 1 の H-2)、(viii) **本計測は plug 1 回につき application 1 個なので、台帳 `RM`:510 の R-79 行の「application ごとに識別子が変わる」条件は観測されない**こと (同 L-11)。**(i) の判定は `share` の大小ではなく `PREPSTMT` の一覧で行う** (同 M-8)。**事実だけを書く。**
6. **認証接続について記す** (起草時の裁定 2): harness の MitateDB plug は `pool=None` で**認証接続を呼びごとに開いて閉じる** (R-78 §1.3 の (5))。**1 呼びで閉じる接続は自動 prepare の恩恵を受け得ない**ので、認証文は prepared になり得ない。**これを §3 の事実として記す** (計測の対象外であることの根拠であって、判断ではない)。
7. **判断** (§4): **監督が書く。** 効かない経路の特定と、**WP-3 の内容** (§3.4 の候補 (A) / (B) / (C) のどれを採るか) を、§2 の数字だけに基づいて判定する。**この節は WP-1 では空欄である。**

### 3.2 設計メモの骨 (本書と同じ変更セットで起草済み。WP-2 が埋める)

| 節 | 内容 | 埋める者 |
|---|---|---|
| §0 | 版数 (v0.1) と位置づけ | 起草 (済) / WP-2 (版数を上げる) |
| §1 | 目的と方法 (本書 §1.1 の問題設定、機構上の事実 F1〜F5 の要約と本書への参照、道具と引数、K の並び、r2db の pool の寸法は既定 (2) のみである旨、`share` が下界である旨、合成環境である旨) | 起草 (済) / WP-2 (確定) |
| §2 | 実測 (`PERFRUN` / `PERF` / `PREPARED` / `PREPSTMT` の逐語。K=1 と K=4 の小見出しだけが在る) | **WP-2 (監督)** |
| §3 | 事実 (§3.1 の 5 の (i)〜(v)) | **WP-2 (監督)** |
| §4 | 判断 (効かない経路の特定と WP-3 の内容) | **WP-2 (監督)。WP-1 では見出しと空欄だけ** |

### 3.3 完了条件 (監督が自ら照合する)

1. D-5 の前後比較が取れ、`PERF` の p50 の差が ±10% 以内である。**判定は p50 ≥ 1 ms の行で行い、p50 < 1 ms の行 (in-process plug) は記録のみとする** (設計レビュー 1 の L-12)。外れたら本書 §6.1 に訂正註として残し、原因を切り分ける。
2. K=1 と K=4 の `PERFRUN` / `PERF` / `PREPARED` / `PREPSTMT` 行が §2 に**逐語で**在り、`--warmup` / `--n` / `--prepared-detail` と r2db の pool の寸法 (既定 2) が併記されている。どの run も `LIMIT_EXCEEDED` で欠けていない。
3. §3 が事実だけで書かれており、判断語 (「〜すべき」「〜が原因である」) を含まない。
4. §4 が監督の判断として書かれ、**WP-3 の内容が §3.4 の候補から確定して本書 v1.1 に入る** (§3.4)。
5. 台帳 `RM` §8 の R-79 行への追記は **WP-3 の完了後**に監督が行う (**行は消さない**)。

### 3.4 WP-3 (確定) — r2db の liveness ping を transaction の外で打つ (実装担当)

**本節は v1.1 で確定した** (設計メモ `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` v0.2 の §4 の判断。v1.0 の本節は候補の列挙だけであり、候補の行は下の採否表に残す。§1.5 の (U-1) はこれで確定した)。

**目的**: 設計メモ §4 が特定した「効かない経路 = r2db の data 面の全経路」を、その原因に対して直す — `_RolePool._liveness_check` が checkout ごとに `SELECT 1` で開いた transaction を `rollback()` で閉じ、psycopg がそのたびに client 側の prepared 表を消して `DEALLOCATE ALL` を送る (§1.1 の F2、§1.3 の (2))。**MitateDB は候補 (C) = 何もしない** (設計メモ §3 の (ii)・§4)。

**採否** (設計メモ §4 の判断。理由はそこに在る。蒸し返さない):

| 候補 (§1.5 の (U-1)・v1.0 の §3.4) | 採否 |
|---|---|
| **(D)** r2db の liveness ping の後始末を `rollback()` 以外にする | **採用。r2db にだけ適用する** |
| **(C)** 何もしない | **採用。MitateDB はこれである** |
| **(A)** `SET LOCAL … = '<N>ms'` を `SELECT set_config(...)` の 1 文・bind parameter に替える | 採らない (§4 の (4-7)) |
| **(B)** `timeout_ms` の量子化 | 採らない (§4 の (4-7)) |
| ping の廃止 | 採らない (切断検知を失う) |
| `prepare_threshold` / `prepared_max` の変更 | 採らない (§4 の (4-2)) |

**変更の形 (監督確定。実装担当が動かさない)**: `_RolePool._liveness_check` の ping を transaction の外で打つ。**ping の直前に `conn.autocommit = True`、`SELECT 1` を実行、`finally` で `conn.autocommit = False` に戻す。`rollback()` は削除する。** **ping の前に事前確認を置く** — `conn.info.transaction_status` が IDLE でなければ `conn.rollback()` してから ping する (**監督裁定 2026-09-23**: 非 IDLE の接続が checkout された場合に、現状どおり rollback して**再利用**する。prepared が消えるのはこの異常時だけである)。 ping の失敗時の扱い (接続を閉じて `False` を返し、`connection()` が `_connect()` で開き直す) は**現状のまま**である。**貸し出す接続は ping の後も IDLE で `autocommit=False` である** — 現在の保証を弱めない。`autocommit` の切り替えが IDLE の接続では SQL を 1 文も出さないことは §1.3 の (15) の実測に在る。

**守るべき条件**: 変更クラスは **B** (着手時に `tools/change_class.py` で触った全パスを測り直す)。**契約は 1.8.0 のまま**で `spec/`・`conformance-tests/`・`security/` の差分は **0**、**`MitateDB-api/` を 1 行も触らない**。**hot path の往復は増えない** — ping は `BEGIN` / `SELECT 1` / `ROLLBACK` の 3 往復から `SELECT 1` の 1 往復に減る。§1.1 の (b)・(d)・(e) は WP-3 にも掛かる。

**読むべき正本**: §1.1 (守る条件) / §1.3 の (2)・(11)・(15) / §1.4 (却下案) / 設計メモ §3 の (i)(iii)(vii) と §4。規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.3〜§1.6・§1.9・§1.10。**疑義は実装せず報告に書く** (§1.5 の 37)。**下請けの Agent を起動しない** (§1.7 の 47)。

#### 3.4.1 触ってよいパス

- `r2db-api/src/r2db_api/postgres.py` — **`_RolePool._liveness_check` の本文だけ** (現物 :470-497。**基点 `ce27b52` では :408-428**。行番号は WP-1 完了時点の実測)。`_acquire` / `connection()` / `_connect` / `prepared_stats` / `close_all` / `retire()` / eviction・LRU の条件 / `_set_timeouts` / R-78 の統計を 1 つも変えない。**docstring (:471-481) に文を足さない** (§3.4.4 の来歴の手順)。
- `r2db-api/tests/test_r79_prepared_stats.py` — **完了条件 33〜37・40 のテストの追加だけ。** 既存のテストの本体を変えない。
- `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` — **行番号 pin の実測更新だけ** (:195 の `("postgres.py", 1592)`。§1.3 の (11))。件数と site identity は変えない。
- `docs/code-history/r2db-api/postgres.md` — **§3.4.4 の来歴の手順のとおり**、`## CH-0541` の節を 1 つ (**本書で予約する**。実測: 現在の最大は `CH-0540`)。

**これ以外は 0 件。** とくに `MitateDB-api/`・`spec/`・`conformance-tests/`・`security/`・`tools/`・`docs/design/`・`RM` を触らない (変異での一時編集は別。`mutate.py` が復元する)。**既存の検査が新しいコードで赤になったら直さず報告する** (§1.5 の 37)。

#### 3.4.2 完了条件 (33〜44)

| # | 完了条件 |
|---|---|
| 33 | **(D)・空振り禁止 (§1.5 の 32)**: **実 PostgreSQL** の pool から **6 回以上 checkout** し、**各 checkout で同じ 1 文を 1 回実行**して実運用経路と同じく **commit で閉じる** (`with conn.transaction():`)。その後 `SharedPoolManager.prepared_stats()` (又は `_RolePool.prepared_stats`) の**当該接続**で **`prepared` ≥ 1 かつ `prepared_execs` ≥ 1** を観測する。**同じ接続が 6 回とも使われる形にする** (pool の寸法は実装詳細。`maxconn=1` で足りる)。counter の直叩きや source text の代理指標で置き換えない (§1.5 の 52) |
| 34 | **(D)** ping の後に**貸し出される接続**が **`conn.info.transaction_status` が IDLE** かつ **`conn.autocommit is False`** である。`pool.connection()` が渡す接続そのもので観測する |
| 35 | **(D)** ping の `SELECT 1` が transaction を開かない — **`SELECT 1` の直後、後始末の前**の `transaction_status` が IDLE である。観測点は貸し出し後ではなく **ping の中**であり、`cursor_factory` を差し替えた接続 (`super().execute()` の直後に、その cursor 自身の接続の `conn.info.transaction_status` に当たる値を記録する cursor) を `_liveness_check` に直接渡して観測する |
| 36 | **(D)** **ping が失敗した接続は捨てられる** (基点の振る舞いが残る)。**既存テストは 0 件である** — 実測: `r2db-api/tests` で `_liveness_check` を扱うのは `test_threadpool_offload.py`:356・:746 の monkeypatch 2 件だけで、ping 失敗時の振る舞いを見るテストは無い。したがって本 WP で **1 本足す**: server 側で backend を落とした接続 (`pg_terminate_backend`) を pool に入れて checkout し、渡される接続が**使えること**と **`backend_pid` が別であること**を観測する |
| 37 | **(D-1 の計数の解釈用)** `CountingConnection.execute_count` が **checkout 1 回につき ping の分の 1 だけ**増える。`pool.connection()` を 1 回通し (中で文を 1 つも実行せず)、差分がちょうど **1** であることを観測する |
| 38 | **(D-7) 監査照合**: `python3 tools/check_comment_provenance.py --base ce27b52 r2db-api/src/r2db_api/postgres.py` の FAIL 行が **§4.1 (1) だけ**で、(2)・(3)・(5)・§9e・§9f・§9.4・`#:` の行が **0 行**。`--register` が緑。出力を逐語で報告に残す。**(2) が出たら止めて報告する。worktree を cwd にして走らせる** |
| 39 | **監査照合**: 走査集合・行番号 pin の**実測更新** — `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:195 の `("postgres.py", 1592)` を実測値に直した (§1.3 の (11)、`OPERATING_CONDITIONS.md` §1.5 の 40b)。`tools/tests/test_no_shared_cluster_defaults.py`:275 の件数 pin は**新規ファイルを足さないので不変**であることを実測で確かめる (数を合わせるのではなく、走査対象の集合が変わっていないことを見る) |
| 40 | **(D。監督裁定 2026-09-23)** **非 IDLE の接続が checkout されても、現状どおり rollback して再利用される** — `_queue` に **INTRANS のまま**の接続を直接戻してから `pool.connection()` で checkout すると、**同じ `backend_pid`** の接続が **IDLE** で貸し出される (接続が捨てられて別の backend に替わらない) |
| 41 | **監査照合 (守る条件)**: `spec/`・`conformance-tests/`・`security/`・**`MitateDB-api/`** の差分が **0 行**で、契約は **1.8.0** のまま。`python3 tools/change_class.py <触った全パス>` が `class=B`、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged、`python3 tools/check_doc_refs.py` が 0 dangling。`git diff --stat` で示す。ホスト名・実 DSN・作業機の絶対パスを新しいテストと記録に書いていない (§1.9、§2 の 13) |
| 42 | **監査照合 (hot path)**: ping の往復が **3 から 1 に減り、増えていない** (`BEGIN` / `SELECT 1` / `ROLLBACK` → `SELECT 1`)。`_liveness_check` の `git diff` を逐語で示し、**lock・thread・timer・`print` / `logging`・DB 往復を 1 つも足していない**ことと、psycopg の private 属性 (`_prepared` / `_counts` / `_names`) を読んでいないこと (§1.1 の (e)) を示す |
| 43 | **監査照合**: 報告前に `r2db-api/tests -q` を **1 回**、`tools/tests -q` を **1 回**、`conformance-tests -q` を **1 回** 回して緑 (§1.3 の (12) の `conformance_required=true`)。集計行を逐語で報告に残す (**完了ゲートは監督**) |
| 44 | §3.4.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み (§1.4 の 29〜31)。かつ §3.4.3 の対応表に**対応の無い行が無い** |

#### 3.4.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) |
|---|---|
| 33 | **M27**: `_liveness_check` を**基点の形に戻す** — `conn.autocommit = True` と `finally` の `conn.autocommit = False` を落とし、ping の後に `conn.rollback()` を置く (**`edits` で 1 つの変異にまとめる**)。**`conn.rollback()` を足すだけでは赤にならない**: `Connection.rollback()` は接続が IDLE のとき早期 return し、prepared を消さない (§1.3 の (15)・(2))。→ 完了条件 33 のテストが赤 |
| 34 | **M28**: `finally` の `conn.autocommit = False` を落とす (autocommit のまま貸し出す) → 完了条件 34 のテストが赤 |
| 35 | **M29**: ping の直前の `conn.autocommit = True` を `conn.autocommit = False` にする (`SELECT 1` が BEGIN を出して INTRANS になる) → 完了条件 35 のテストが赤 |
| 36 | **M30**: ping の失敗時に接続を捨てない (`except` 枝の `conn.close()` を落として `True` を返す) → 完了条件 36 のテストが赤 |
| 37 | **M31**: ping の `SELECT 1` を 2 回打つ → 完了条件 37 のテストが赤 |
| 40 | **M32**: ping の前の事前確認 (`transaction_status` が IDLE でなければ `conn.rollback()`) を外す — 非 IDLE の接続で `conn.autocommit = True` が `ProgrammingError` を投げ (§1.3 の (15))、`except` 枝で接続が捨てられて `backend_pid` が変わる → 完了条件 40 のテストが赤 |
| 38・39・41・42・43 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す) |
| 44 | **対応表の完全性** (§1.5 の 40。本表に対応の無い完了条件の行が 1 つも無いこと) |

- **M27〜M32 が赤にする test id は新規テストの名前**なので、実装担当が完了条件 33〜37・40 に 1 対 1 のテストを作り、その id を `mutations` の `tests` に **1 件だけ**書く (§1.5 の 40。`mutate.py` は最初の失敗で止まる)。
- 変異は **r2db の 1 peer だけ**なので 1 run でよい。変異ファイルは `$SP/r79-wp3-mutations.json` に置き、形は §2.3 と同じ。

#### 3.4.4 道具の引数と来歴の手順

`$SP` (自分の scratchpad) を export しておく。`pt.py` / `mutate.py` は main checkout を cwd にして走らせ、`-C` で worktree を指す (**渡し忘れると main を測る**)。

```bash
tools/dev/pt.py -C .claude/worktrees/r79 --wait 300 -- r2db-api/tests/test_r79_prepared_stats.py -q
tools/dev/pt.py -C .claude/worktrees/r79 --wait 1800 -- r2db-api/tests -q
tools/dev/pt.py -C .claude/worktrees/r79 --wait 1800 -- tools/tests -q
tools/dev/pt.py -C .claude/worktrees/r79 --wait 1800 -- conformance-tests -q
tools/dev/mutate.py "$SP/r79-wp3-mutations.json" -C .claude/worktrees/r79 --wait 300
```

- worktree を cwd にして走らせるもの (この worktree に `.venv` は無いので `python3` で走らせる):

```bash
python3 tools/check_comment_provenance.py --base ce27b52 r2db-api/src/r2db_api/postgres.py
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- **`pytest` の直接実行・`tools/perf_baseline.py` の実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。`gate.py` は他の pytest と同時に走らせると落ちるので、レビュー担当と同時刻に走らせない (§1.3)。**性能計測の実行中は pytest と nginx を走らせない** (§2 の 19)。
- 一時ファイルは `$SP` 配下だけに置く。複数手順のシェル処理は `$SP` の bash スクリプト (bash 3.2 互換) にする。報告は `$SP/r79-wp3-report.md` に書く。

**来歴 (コメント) の手順 (監督裁定 2026-09-23。初回の移動の経路を採る)**: 現物の `_liveness_check` は **CH-ID を持たない** (実測: docstring :471-481 と `#` 塊 :486-489 のどちらにも `CH-` が無い)。**(D) は :486-489 の塊の事実 (ping の後に roll back する) を偽にする。塊を削除して説明を失わせるのではなく、新しい説明の塊に置き換えて登録する。** 規則は `docs/design/CODE_COMMENT_PROVENANCE_V1.md` の §4.1・§9 の 0g・§9.3 に在る (本書に複製しない)。手順は次のとおりで、**迷う点は実装せず報告する** (§1.5 の 37)。

1. **受け皿の節を起こす** — `docs/code-history/r2db-api/postgres.md` に **`## CH-0541`** の節を足す (**本書で予約した ID**。実測: 現在の最大は `CH-0540`)。節には同 D-2 の「受け皿の節」の規則どおり、**移動元** (`src/r2db_api/postgres.py` (`_RolePool._liveness_check`))・**親コミット**・**種別** (comment)・**旧版の塊 (:486-489) を逐語で**置く (fenced block)。
2. **訂正を記録する** — 事実が変わる文を、同じ節に `### correction: <日付>` として `- reason:` 1 行と `old:` / `new:` の fenced block で記録する (形の先例は `docs/code-history/r2db-api/service.md` の `## CH-0120` の節)。`old:` は平坦化と正規化の後の形で書く (§9 の 0g の 7)。**訂正は保護参照を減らさない** (同 5)。
3. **新しい in-code の塊を書く** — 「訂正を当てた基準」から §4.1 (3)(4)(6) の許容操作で得られる形にする (§9.3 の問題文が言う「基点に CH-ID の無い初回の移動は、訂正を当てた基準と新しい塊を比べるので通る」経路)。**塊の末尾に参照行 `# history: CH-0541` を 1 行**置く (同 D-2 の「コード側」。`#` 塊の形)。
4. **既存の docstring (:471-481) に文を 1 つも足さない** — 旧版に在る symbol の塊への追加は §4.1 (2) (v0.22 の D-2) で赤になる (既知の制約として `RM` の R-89 に在る)。
5. 完了条件 38 の `--base` と `--register` を worktree を cwd にして走らせ、**出力を逐語で報告に残す。(2) の FAIL が出たら止めて報告する。** 訂正が事実に合っているかの照合は独立レビューで行う (§9 の 0g の 7)。

#### 3.4.5 計測と非退行 (**監督が実施する。WP-3 の統合前**)

1. **他の pytest と nginx を止める** (§2 の 19)。
2. **効いたことの確認**: 本 worktree の道具で r2db の plug の **K=1** (`tools/perf_baseline.py --warmup 10 --n 100 --concurrency 1 --prepared-detail`) を取り、`PERFRUN` / `PERF` / `PREPARED` / `PREPSTMT` 行を**逐語で**設計メモ `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` の **§2.3** に置く。**§3 に (ix) として r2db の `prepared` / `share` の変化**を追記する (WP-2 の §2.1 の r2db の行との比較)。**設計メモの §1〜§3 の既存の行は書き換えない** (追記だけ。版数を上げる)。
3. **非退行 (D-5)**: **K=1 と K=3** (`--warmup 10 --n 100 --concurrency 1` / `--concurrency 3`) を**基点の道具と交互に**取り、`PERF` の p50 の差が **±10% 以内**であること (`OPERATING_CONDITIONS.md` §1.3 の 27)。**判定は p50 ≥ 1 ms の行で行い、p50 < 1 ms の行 (in-process plug) は記録のみとする** (§3.3 の 1 と同じ)。外れたら本書 §6.1 に訂正註として残し、原因を切り分ける。
4. 台帳 `RM` §8 の R-79 行への追記と引き継ぎ書は、**WP-3 の完了後**に監督が行う (**行は消さない**。§4 の (4-5))。

#### 3.4.6 v1.0 の §3.4 の本文 (予約。参照用に消さずに残す。§1.8 の 56)

> 台帳 `RM`:510 の R-79 行は「効かない経路だけを直す」を本件の範囲に含める。**その内容は WP-2 の §4 の判断が決めるので、本書 v1.0 では候補の列挙だけを行い、完了条件・触ってよいパス・変異は書かない。** 候補は §1.5 の (U-1) と同じ 3 つである。
>
> - **(A)** `SET LOCAL … = '<N>ms'` を `SELECT set_config('statement_timeout', %s, true), set_config('lock_timeout', %s, true)` の 1 文・bind parameter に替える。**条件**: 宣言 `execution_ms` の実効上限の意味 (SI-08 / R-87 の確定文) を変えないこと。
> - **(B)** `timeout_ms` を刻み (例: 100ms 切り上げ) に量子化して文字列の種類を減らす。
> - **(C)** 何もしない (計測で効いていると分かった場合)。
> - **(D)** r2db の liveness ping (`postgres.py`:408-428) の後始末を `rollback()` 以外にする (例: `autocommit` での ping、`SELECT 1` を `commit()` で閉じる)。**条件**: 貸し出す接続が「きれいな状態で始まる」という現在の保証を弱めないこと。
>
> **WP-1 と WP-2 では (A)・(B)・(C)・(D) のいずれにも寄せない。** §1.3 の (14) の実測 (MitateDB の catalog 読み 8 本は定数の `SET LOCAL` を打ち、残る 10 箇所は deadline 由来である) も、判断ではなく事実として扱う。

## 4. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **(4-1) 寸法の変更。** pool の `maxconn`、`ResourceLimits.concurrency`、role の `CONNECTION LIMIT`、`DSA_PERF_POOL_SIZE` の既定を 1 つも変えない。
- **(4-2) `prepare_threshold` / `prepared_max` の変更。** 両 peer の `src` は基点で 0 件の指定 (psycopg の既定 5 / 100) であり、本書はこれを変えない。変えるかどうかは WP-2 の §4 の判断の後である。
- **(4-3) `RM`:511 の R-80 (pipeline)・`RM`:512 の R-81 (idempotency の往復)・`RM`:513 の R-82 (スキーマのキャッシュ)。** いずれも別件である。
- **(4-4) `RM`:514 の R-83 (認証キャッシュ)。** 設計レビューを着手条件とする別件である。
- **(4-5) 台帳 `RM` の R-79 行の追記・引き継ぎ書。** **統合時に監督が行う** (§3.3 の 5)。
- **(4-6) 1 呼びで閉じる接続の計測** (起草時の裁定 2)。`ops.py`・`main.py`・per-call の認証 store・`postgres.py`:811 のように**開いて 1 度使って閉じる接続は、自動 prepare の恩恵を受け得ない** — psycopg の閾値 (既定 5) は同じ接続で同じ文を繰り返したときに初めて効き、`pg_prepared_statements` も session ごとだからである (§1.3 の (5) の F5)。**したがって計測の対象外とし、D-1 の counting も D-2 の probe も置かない。** 同じ理由で、harness の MitateDB plug が `pool=None` で呼びごとに開く認証接続の文も prepared になり得ない (§3.1 の 6 で §3 の事実として記す)。
- **(4-7) 候補 (A) の往復削減と候補 (B) の量子化** (v1.1)。設計メモ §4 の判断により WP-3 では採らない。**(A) の往復削減 (`SET LOCAL` 2 文 → `set_config` 1 文) は `RM`:511 の R-80 の範囲として台帳に申し送る** (同 §4)。(B) は値の種類が 3〜12 で `prepared_max` (100) に遠いので不要である (同)。
- **(4-8) MitateDB 側の変更** (v1.1)。設計メモ §3 の (ii)・§4 のとおり MitateDB は既に効いており、WP-3 は候補 (C) = 何もしない。**`MitateDB-api/` を 1 行も触らない** (§3.4.1)。

## 5. レビューと受け入れ

- **設計レビュー 1 回** (本書 §1 に対して、WP-1 の着手前)。観点: 守る条件 (a)〜(e) が D-1〜D-7 で満たされているか、**§1.3 の実測と枠の食い違い** (とくに (6) の `cursor_factory` の代入位置、(7) の接続生成箇所と D-1 の 4 箇所の関係、(8) の `executemany` 0 件、(9) の platform pool が届かないこと、(14) の MitateDB の定数 `SET LOCAL` — **いずれも §6.1 の起草時の裁定 1〜5 が §1〜§5 に入っている**)、完了条件と変異の対応の穴、probe が挙動を変えていないこと (とくに rollback の禁止と idle 接続の戻し)。
- **コードレビュー 1 回** (実装担当とは別の起動)。観点: (i) hot path に足したのが整数加算 1 回だけで、lock・DB 往復・ログ・thread を増やしていないこと、(ii) psycopg の private 属性を 1 箇所も読んでいないこと、(iii) 新規テストの空振り (§1.5 の 32) と代理指標 (§1.5 の 52) — とくに完了条件 4・5・6 が**型**で観測されていること、(iv) probe が接続を IDLE で返し、prepared を消さず、pool の接続を全て戻していること、(v) `PERF` / `POOL` 行の書式が不変であること、(vi) socket plug でも `PREPARED` 行が出ることの観測、(vii) **`_ISOMORPHIC_TARGETS` の差分が両 peer とも 0 行**で、同一性が `psycopg_counting.py` の sha256 一致テストで固定されていること、新 module が走査集合 pin に入ったことの手動検証 (完了条件 29) が逐語で在ること、(viii) `label` が `@<backend_pid>` を持ち、`ApplicationCell.prepared_stats()` が `with self._lock:` の下で委譲していること、probe が非 IDLE では走らず、例外時も `finally` で接続を戻し、`error` に message を載せていないこと、probe が R-78 の `acquire_count` / `in_use_peak` を動かさないこと、(ix) レビュー担当自身の変異 1〜2 件 (報告に無いもの。ただし完了ゲートと並行させないこと)。
- **受け入れ監査 1 回** (レビュー担当とも別の起動)。**Class B だが `src` の hot path に触るので省略しない。**
- **(v1.1) WP-3 のコードレビュー 1 回** (実装担当とは別の起動)。観点: (i) ping が transaction を開かず `rollback()` が残っていないこと、(ii) 貸し出す接続が IDLE で `autocommit is False` であること、(iii) ping 失敗時の振る舞いが基点と同じであること、(iv) 完了条件 33〜37 の空振り (§1.5 の 32) と代理指標 (§1.5 の 52) — とくに 35 の観測点が ping の中に在ること、(v) 来歴の経路 ((a) / (b)) と受け皿の記録が §3.4.4 のとおりであること、(vi) hot path に往復・lock・ログを足していないこと、(vii) レビュー担当自身の変異 1〜2 件 (報告に無いもの。完了ゲートと並行させないこと)。
- **(v1.1) WP-3 の受け入れ監査 1 回** (レビュー担当とも別の起動)。**Class B だが `src` の hot path の振る舞いを変えるので省略しない。**
- **(v1.1) WP-3 の完了ゲートと計測は監督**が行う (`tools/dev/gate.py -C .claude/worktrees/r79`、計測と非退行は §3.4.5)。受理したら設計メモ §2.3 / §3 の (ix) を監督が埋め、台帳 `RM` §8 の R-79 行に追記する (§4 の (4-5))。
- **完了ゲートと性能差分は監督**が行う (`tools/dev/gate.py -C .claude/worktrees/r79`、`tools/perf_baseline.py` を §1.3 の逐語 B と同じ引数で。D-5)。監督が集計行と §2.2 を照合して判定する。受理したら **WP-2 (§3)** に進み、その §4 の判断をもって **WP-3 (§3.4)** の内容を本書 v1.1 で確定する。

## 6. 記録 (統合時に監督が埋める。§1〜§5 の本文は書き換えない)

### 6.1 訂正註と監督裁定

**起草時の裁定 (監督、2026-09-23。起草段階なので §1〜§5 の本文に直接反映した)**:

1. **F1 の MitateDB 部分は §1.3 の (14) の実測を正とする。** 可変鍵は `_timeout_ms(deadline)` を渡す箇所だけ (MitateDB は 10 箇所) で、catalog 読み 8 本の `SET LOCAL` は構築時定数 `_catalog_timeout_ms` による固定鍵 2 個であり、閾値に届けば prepared になり得る。§1.1 の F1・§1.3 の (1)・D-4 の §3 事実 (ii)・§3.1 の 5 に反映した。
2. **D-1 の「接続を作る全箇所」は、接続を要求をまたいで使い回す 4 箇所に限る。** 1 呼びで閉じる接続は自動 prepare の恩恵を受け得ないので計測対象外である (§4 の (4-6))。harness の MitateDB plug の認証接続 (`pool=None`) も同じ理由で prepared になり得ず、これは §3 の事実として記す (§3.1 の 6)。
3. **counting class の置き場は両 peer の新 module `src/<pkg>/psycopg_counting.py` (同名・byte 一致) とする。** `postgres.py` / `backend_postgres.py` / `pool.py` はそこから import する。R-75〜R-77 系の走査集合 pin に掛かるかは着手時に grep し、掛かるなら編集前に報告する。「新 module が走査対象に入る」型の条件は `mutate.py` で扱えないので `pt.py` で手動に確かめる (完了条件 26、§2.3 の同番の行)。
4. **MitateDB の lock 主体は `cell.py` の `ApplicationCell.prepared_stats()` とする** — `with self._lock:` の下で backend の `prepared_stats` へ委譲し、無ければ `[]` を返す。adapter は cell のこの method を呼ぶ。r2db は queue から取り出すので lock を取らない (D-2、§2.1、完了条件 9、M9)。
5. **`label` は両 peer とも `conn.info.backend_pid` を末尾に付ける** — r2db `<application_id>/<role>@<pid>`、MitateDB `runtime@<pid>` / `developer@<pid>`。再接続が label の変化として見える (D-2・D-3、完了条件 14、M14)。

**設計レビュー 1 の裁定 (監督、2026-09-23。生出力は `$SP/review-r79-design.md`。起草段階なので §1〜§5 の本文に直接反映した)**:

- **H-1・H-5 (変更クラス)**: `_ISOMORPHIC_TARGETS` には足さず **Class B のまま**とし、両 peer の `psycopg_counting.py` の **sha256 一致テスト**を両 peer の `tests` に 1 本ずつ置く (D-1、§1.3 の (10)・(12)、§2.1、完了条件 7・23、M7)。
- **H-2 (liveness rollback)**: 全面採用。r2db は checkout ごとに `SELECT 1` → `rollback()` で全消去する (§1.1 の F2、§1.3 の (2) に :408-428・:441)。WP-3 の候補に **(D) liveness ping の後始末を rollback 以外にする**を追加し (§1.5 の U-1、§3.4)、§3 の事実に (vii) を足した (D-4、§3.1、設計メモ §3)。
- **H-3 (probe が R-78 の計測に混ざる)**: 採用。`PREPARED` 行は同じ op の `POOL` 行の後に出し、MitateDB の `POOL lock=` の `acquire` が probe 1 回分を含む旨を README と設計メモ §1 に明記する。完了条件 17 (`lock_acquire_count` == probe 回数) を新設し、完了条件 8 を「probe 前後で r2db pool の `acquire_count` / `wait_count` / `in_use_peak` が不変」に書き替えた (D-3、M8・M17)。
- **H-4 (例外時に接続が戻らない)**: 採用。接続ごとに例外を捕え `finally` で必ず `put_nowait` で戻し、例外の接続は `probed=false` + `error=<例外の class 名>` (message は載せない) とする (D-2、完了条件 15、M15)。
- **M-6 (monkeypatch の件数)**: §1.3 の (7) を **15 件**に差し替えて列挙した。完了条件にはせず、§2.4 の着手時確認と完了条件 30 の監査照合に置いた。
- **M-7 (`statements` の一語二義)**: 採用。行の列名は `executes=` / `executemany=`、属性名は `execute_count` / `executemany_count`、dict の一覧鍵は `prepared_statements`、`share` = `prepared_execs / executes` (D-2・D-3・完了条件・§3 の (iii)・設計メモ §1)。
- **M-8 (`share` の構造的天井)**: 採用。分母に prepared になり得ない文が入るので `share` には構造的上限があり、判定は `PREPSTMT` の一覧で行う (D-3・D-4 の (i)、設計メモ §1・§3)。
- **L-9 (完了条件 14 が 3 主張)**: **14a (鍵集合、変異は鍵を 1 つ増やす)** と **14b (pid)** に割った。
- **L-10 (出力位置)**: D-3 に「行順は先例どおり plug の `PERF` 行より前に塊で出る。『計測の後』は実行順の話」を書いた。
- **L-11 (application をまたぐ識別子)**: 採用。plug 1 回につき application 1 個なので台帳 R-79 行の「application ごとに識別子が変わる」条件は観測されない旨を §3 の事実 (viii) に置いた (D-4、§3.1、設計メモ §3)。
- **L-12 (sub-ms の ±10%)**: 判定は p50 ≥ 1 ms の行で行い、< 1 ms の行は記録のみとする (D-5、§3.3 の 1)。
- **L-13 (probe 開始時の `transaction_status`)**: 採用。IDLE のときだけ probe し、非 IDLE なら `probed=false` と `transaction_status` 名を載せる。dict の鍵は **11 個** (`error` を含む) に確定した (D-2、完了条件 14a・16、M14a・M16)。

**WP-1 の実装中の裁定 (監督、2026-09-23)**:

- **worktree**: 実装担当の Write が監督の作った worktree `r79` へはフックで拒まれたため、branch `r79` を監督チャットの割り当て worktree に載せ替えて実装した。本書の `.claude/worktrees/r79` は記号名であり、道具には `-C .` を渡した。
- **来歴検査 §4.1 (2) の 2 件**: 実装担当が `_RolePool._connect` と `PostgresBackend.__init__` の `CountingConnection.connect` の直前に置いた CH-ID 無しの説明コメント塊 2 つを監督が削除した (説明は `psycopg_counting.py` の docstring と import 行のコメントに在る)。これに伴い両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` の allowlist を −7 / −6 行、最終修正 (docstring 追加) の後に r2db 側を +8 行、いずれも現物の `_fail_call_sites` で照合して更新した。
- **コードレビュー 1 の裁定**: 指摘 (A)(B)(C) (MitateDB `prepared_stats()` の 2 label と pid の観測、probe が `execute_count` を増やさない観測、`PREPARED` が同 op の `POOL` の後に出る観測) を採用し M21〜M24 を追加。指摘 3 (両 peer に複製された probe 本体に pin が無い) は **複製をやめて probe 本体を `psycopg_counting.py` に統合** (byte 一致の sha256 pin が覆う。`_ISOMORPHIC_TARGETS` は 0 差分のまま、Class B のまま)。指摘 5 (例外時に接続が aborted のまま戻る) は **例外分岐で非 IDLE なら `rollback()`** (M25)。指摘 6 (README の F3 の注記) と 7 (設計メモ・§1.3 (2) の `_liveness_check` の行参照) は採用。指摘 8: D-7 の「§4.1 (1) 以外 0 行」は、新規 2 ファイルの `could not read … at ce27b52` 2 行を構造的に除く。
- **受け入れ監査の裁定**: 14a の 80 文字切り詰めを赤にするテスト (M26a/M26b) と、完了条件 13 の MitateDB 側 (`runtime@<pid>` で `prepared >= 1`) の観測を追加。probe 移動後の取り残し参照 3 箇所を現物に直した。監査の設計疑義 (`_RolePool.prepared_stats` の drain が並行 `_acquire()` を待たせ得る) は docstring に「要求処理中に呼ばない。呼び元は harness の op 間だけ」を明記して閉じた。
- **完了ゲート 1 回目は赤 3 件** (r2db `test_l1_details_vocabulary_ast_scan.py` の 3 本): 実装担当の最終修正で `postgres.py` が 8 行伸びたのに allowlist が更新されていなかった。監督が現物で +8 に直して再実行。
- **D-5 の訂正註**: 最初の非退行計測 (基点は本チャット冒頭、本 worktree はゲート直後) は全 21 行が +14〜+77% と一様に遅く、psycopg に触れない in-process plug (`r2db-api` / `MitateDB-api`) の行まで +14〜+57% だったので、計測器ではなく別チャットの並行作業 (load average 5〜7) によるものと判断し、**基点の道具と本 worktree の道具を交互に**取り直した。K=1 は判定行 14 本すべて **−1.2%〜+2.8%** で D-5 を満たす。K=3 は 2 回の交互計測で同じ行の符号が反転し (MitateDB-http: −7.7〜−12.3% → +2.7〜+17.3%、MitateDB-socket: +0.3〜+14.5% → −0.8〜+7.7%、r2db-http: −0.3〜−4.6% → +12.9〜+17.4%)、基点同士でも run 間に 8〜10% 動く (load average 3〜5)。したがって **K=3 はこの環境では ±10% に収束せず、D-5 は K=1 の結果で判定した**。計数の追加は execute 1 回あたり Python の method 呼び 1 段と整数加算 1 回であり、K=1 の差 (≤ 2.8%) がその上限の実測である。

**v1.1 の追記 (監督、2026-09-23。§1〜§3.3 の本文は書き換えず、追記だけで行った)**:

1. **§3.4 の WP-3 を確定した** — 設計メモ `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` v0.2 の §4 の判断により、候補 **(D) を r2db にだけ適用し、MitateDB は (C)** とする。(A)・(B)・ping の廃止・`prepare_threshold` の変更は採らない (理由は設計メモ §4 に在る)。v1.0 の §3.4 の本文 (予約と候補の列挙) は **§3.4.6 に引用で残した** (§1.8 の 56)。§1.5 の (U-1) の行は消していない。
2. **§1.3 に (15) を足した** — psycopg の `autocommit` の setter は IDLE の接続では SQL を 1 文も出さず、`rollback()` は IDLE のとき早期 return して prepared を消さない (現物で確認)。WP-3 の変更の形と §3.4.3 の M27 の作り方の根拠である。
3. **§4 に (4-7)・(4-8)、§5 に WP-3 の 3 行を足した。**
4. **裁定 (2026-09-23)**: §3.4.3 の **M27 は「基点の形に戻す複数編集 (`edits`)」で可**とする (`rollback()` を足すだけでは IDLE の早期 return で赤にならないため。§1.3 の (15))。
5. **裁定 (2026-09-23)**: **非 IDLE の接続が checkout された場合は現状の振る舞い (rollback して再利用) を保つ** — ping の前に `transaction_status` の事前確認を置く。完了条件 **40** と変異 **M32** を足した。
6. **裁定 (2026-09-23)**: 完了条件 33 の「**commit で閉じる**」句はテストの実装詳細の明示として残す。
7. **裁定 (2026-09-23)**: 来歴は **初回の移動の経路 (登録) を採る** — 旧塊を新しい説明の塊に置き換え、`# history: CH-0541` を付けて `docs/code-history/r2db-api/postgres.md` に登録する。**塊を削除するだけの経路は採らない** (説明が消えるため)。手順は §3.4.4。
8. **裁定 (2026-09-23)**: **WP-3 の設計レビューは省略する** — 変更は 1 method で、判断は設計メモ §4 の実測で確定済みである (速度規律 3)。コードレビュー 1 回・受け入れ監査 1 回・完了ゲートは §5 のとおり。

**WP-3 の実装中の裁定 (監督、2026-09-23)**:

- **コードレビューの指摘 1** (条件 33 の assert は ping 自身の `SELECT 1` が prepared になるだけでも通る) を採用し、監督が「data 面の文 (`WHERE 1 = 1`) が `prepared_statements` に在る」assert を 1 行足した (M27 は引き続き赤、監査の独自変異 A1 で載荷を確認)。**指摘 5** (CH-0541 の親コミット) を `fc891cb` に直した。
- **コードレビューの指摘 2 (事実の訂正)**: 事前確認 `if transaction_status != IDLE: rollback()` は INTRANS だけでなく **INERROR** の接続にも当たる。基点では INERROR の接続は `SELECT 1` が `InFailedSqlTransaction` を投げて捨てられていたが、WP-3 では rollback して再利用する (`search_path` は接続時に commit 済み、timeout は `SET LOCAL` なので安全性は変わらない)。§6.1 の v1.1 の裁定 2 の「現状どおり」は INTRANS についての記述であり、INERROR はこの訂正註を正とする。
- **条件 38 の `--base`**: 本文は `ce27b52` のままだが、WP-3 の変更集合の親は `fc891cb` である。両 base とも FAIL は §4.1 (1) の 1 行のみ (監査で実測)。
- **M29 / M30 のテスト docstring** が書いていた「赤になる assert」は実測と違った (M29 は `finally` の `autocommit = False` が INTRANS で `ProgrammingError` を投げ `assert ok is True` で赤、M30 は `OperationalError: the connection is closed` で赤)。監督が docstring を実測どおりに直した (§1.5 の 34)。
- **条件 43 の conformance 初回赤 2 件** (`test_testpg_cluster.py::test_peer_root_starts_and_cleans_up_its_own_cluster` 2 件、`subprocess.TimeoutExpired`) は、別チャットの `gate.py` が排他ロックを握っていた時間帯と重なった資源競合で、ロック解放後の再実行で `1104 passed`。完了ゲートの集計行は監督の単独実行 (§6.2) を正本とする。
- **監査の設計疑義** (`connection()` の `finally` の防御 rollback は、caller が非 IDLE で解放した接続に毎回 `ROLLBACK` を打ち、F2 で prepared を全消去する): 実運用経路は `with conn.transaction():` の commit / rollback で閉じるので IDLE で戻り発火しないが、**例外で終わる要求の接続は `conn.transaction()` 自身の rollback で消去される** (F2 のとおり)。これは WP-3 の範囲外の事実として設計メモ §3 (ix) に残す。
- **設計レビューは省略** (§6.1 v1.1 の裁定 5)。コードレビュー 1 回 (差し戻し 0、監督の直接修正 2 件)、受け入れ監査 1 回 (差し戻し 0)。

### 6.2 実施と受け入れ

- **WP-1 (実装担当 Sonnet、コードレビュー Opus 1 回 (差し戻し 1)、受け入れ監査 Opus 1 回 (差し戻し 1)、監督の小修正 3 回)**: 新規 `r2db-api/src/r2db_api/psycopg_counting.py` / `MitateDB-api/src/mitatedb_api/psycopg_counting.py` (byte 一致、`CountingCursor` / `CountingConnection` / `probe_prepared_statements` / `prepared_stats_skeleton`)、`_RolePool._connect`・`PostgresBackend.__init__`・`BoundedConnectionPool._new_connection` が `CountingConnection.connect`、`SharedPoolManager.prepared_stats()` / `_RolePool.prepared_stats()` / `PostgresBackend.prepared_stats()` / `ApplicationCell.prepared_stats()`、両 http plug の `prepared_stats()` (socket は継承)、`tools/perf_baseline.py` の `PREPARED` / `PREPSTMT` 行と `--prepared-detail`、新規テスト `r2db-api/tests/test_r79_prepared_stats.py` / `MitateDB-api/tests/test_r79_prepared_stats.py`、`tools/tests/test_perf_baseline.py` の追加、走査集合 pin 4 ファイルと件数 pin (`tools/tests` 29 → 31) の更新。変異 **M1〜M26 (28 run) 全件 `expect=red got=red`**、レビュー担当の変異 RV-A〜RV-D (RV-B/C/D の緑が差し戻し (A)(B) の根拠)、監査担当の変異 AUD-1〜AUD-4 (AUD-4 の緑が M26 の根拠)。peer suite: `pt: 1450 passed`、`pt: 1456 passed, 2 subtests passed`; `tools/tests`: `1 failed, 608 passed` (赤は `test_0f_both_peers_all_src_rev_vs_itself_is_green` の未コミット新規ファイルによる構造赤で、コミット後に緑。`finalize --tools-tests` で再確認); conformance-tests `1104 passed`。来歴検査: §4.1 (1) 4 行 + 新規 2 ファイルの could-not-read 2 行のみ。`change_class`: 22 パスで `class=B`。`public_value_scan`: 0 flagged。
- **完了ゲート (監督)**: 1 回目 `gate: 3 failed, 4009 passed, 2 subtests passed in 504.86s` / `judge=FAIL` (上記の allowlist の +8)、**2 回目 `gate: 4012 passed, 2 subtests passed in 494.92s (0:08:14)` / `judge=PASS` / `pg_database/pg_roles diff 0`** (3987 + 25)。
- **WP-2 (監督)**: K=1 / K=4 (`--warmup 10 --n 100 --prepared-detail`、r2db pool 既定 2) を設計メモ v0.2 §2 に逐語で置き、§3 (i)〜(viii) と §4 を記入した。要点: **r2db は全接続・全 op で `prepared=0`** (checkout ごとの liveness rollback による全消去と整合)、**MitateDB は持続接続 2 本で `share` 0.91〜0.998** (deadline 由来の `SET LOCAL` の値は K=1 で 3 種、K=4 で 12 種に収まり自身が prepared になる; cross_entity の developer 接続で error 分岐の消去 1 回)。判断: **WP-3 = (D) を r2db に適用、MitateDB は (C)**。D-5 は §6.1 の訂正註のとおり K=1 で判定 (≤ 2.8%)。
- **WP-3 (実装担当 Sonnet、コードレビュー Opus 1 回 (差し戻し 0、監督の直接修正 2 件)、受け入れ監査 Opus 1 回 (差し戻し 0))**: `_RolePool._liveness_check` の ping を `autocommit=True` の下で 1 往復に (非 IDLE なら事前に `rollback()`、`finally` で `autocommit=False`)、CH-0541 (`docs/code-history/r2db-api/postgres.md`)、新規テスト 6 本 (`r2db-api/tests/test_r79_prepared_stats.py`、完了条件 33〜37・40)、`_BACKEND_LAYER_ALLOWLIST` の pin 1592 → 1604。変異 **M27〜M32 全件 `expect=red got=red`**、レビュー担当 RV-1 (赤) / RV-2 (緑 = 意図の確認)、監査担当 A1〜A3 (赤)。`r2db-api/tests`: `pt: 1457 passed`; `tools/tests`: `pt: 611 passed`; conformance-tests `1104 passed` (2 回目。1 回目の赤 2 件は §6.1 のとおり資源競合)。来歴: `--base fc891cb` で §4.1 (1) 1 行のみ、`--register OK (431 CH-IDs)`。`change_class`: B。`public_value_scan`: 0。監査は 42 を実 PG の `log_statement=all` で裏取り (checkout ごとに `SELECT 1` 単独、`BEGIN`/`ROLLBACK` 無し)。
- **完了ゲート (監督)**: `gate: 4018 passed, 2 subtests passed in 502.79s (0:08:22)` / `judge=PASS` / `pg_database/pg_roles diff 0` (4012 + 6)。
- **再計測と非退行 (監督、§3.4.5)**: 設計メモ v0.3 §2.3 / §3 (ix)。r2db runtime 接続で `prepared` 6〜8、`share` 0.948〜0.984 (WP-2 では 0)。基点 `fc891cb` の道具と交互に取った K=1 / K=3 で、r2db-http の p50 は **−49〜−52% (K=1)** / −41〜−46% (K=3)、r2db-socket −26〜−44% / −12〜−15%、MitateDB は −9.3〜+5.8% (socket batch −11.4% のみ帯の外、WP-3 は MitateDB を触っていない)。D-5 の ±10% は非退行の判定線であり、r2db の低下は WP-3 の意図した効果 (往復 3 → 1、prepared plan) である。
