# 作業指示書 — R-80 1 要求あたりの DB 往復を `pg_stat_database` と `execute_count` で実測する (計測が成果物)

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点 local main `c589785`。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の **R-80** 行 (`RM`:605) で、横断条件は `RM`:389 (**P-8**) と `RM`:545 (**R-20**) である。台帳の規模は **M** (`RM`:605 の【追記 2026-09-23 (v1.105)】)。worktree は branch `r80`。
- **変更クラスは B** (実測: §1.3 の (13)。`docs/design/`・`tools/PERF_BASELINE_README.md` が A、`tools/perf_baseline.py`・`tools/tests/` が B)。**契約は 1.8.0 のまま**で `spec/`・`conformance-tests/`・`security/` の差分は **0**。
- **設計文書は新しく起こさない。** 枠 (D-1〜D-6 と却下案) は §1 に在り、これが監督の確定した決定である (R-78・R-79 の先例)。**設計レビュー 1 回**を本書に対して行う。本件の成果物である実測の記録は、新規の設計メモ `docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` に置く (**§3 = WP-2、監督が実施する**)。
- **本件は計測と記録が成果物である** (`RM`:389 の P-8、`RM`:545 の R-20)。台帳 `RM`:605 の R-80 行が範囲に含める pipeline 化は、**WP-2 の §4 の判断の後の別の変更セット**である。本書では **§3.4 に候補を列挙するだけ**で、完了条件・触ってよいパス・変異を書かない。
- **WP-1 (実装担当) と WP-2 (監督) は順に行う。** WP-2 は WP-1 の完了ゲートの後に始まるので、**並行 WP は無く**、触るファイルの重なりの表は置かない (`OPERATING_CONDITIONS.md` §1.2 の 16・17 は該当しない)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`gate.py`・`finalize.py`・`perf_baseline.py` は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。**実装担当の裁量は実装詳細のみ** — §1 の決定・§2.1 の触ってよいパス・§2.2 の完了条件を実装担当が動かさない。

## 1. 枠

### 1.1 問題設定と守るべき条件

**問題** (台帳 `RM`:605 の R-80 行): 「1 要求の中の DB 往復がまとめられていない。両 peer の `src` に psycopg の `pipeline()` は 0 件。本体の処理・監査の書き込み・idempotency の記録を pipeline mode でまとめ、往復を減らす。SI-11 (原子性) と SI-14 (監査) の結果を変えないことを条件にする」。

R-79 の計測器で**接続ごとの文の数は数えられるようになった** (`execute_count`) が、**要求あたりの往復** — 文に加えて transaction の `BEGIN` / `COMMIT` と新規 session の確立 — はまだ集計されていない。R-79 の記録 (`docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` §3 の (ix)・§4) から出る事実は次のとおりである: K=1・110 要求あたり、r2db の runtime 接続で query 668 文 (≈6 文/要求 = ping 1 + catalog 2 + `SET LOCAL` 2 + data 1)、mutate +770 (≈7)、batch +1210 (≈11)。MitateDB は runtime 接続で query 334 (≈3)、**developer 接続で query 1788 (≈16 文/要求)** である。

機構上の事実は §1.3 の (1)〜(5) (**監督が一次資料で確認済み**、F1〜F5) に置く。要点は次の 3 つである。

- **F1**: **監査の書き込み (SI-14) は両 peer とも本体の処理とは別の接続で走る。** r2db は `_PreCommitHook` が `sink.append` を呼び、sink は自前の pool から接続を取って自分の transaction を開いて閉じる。MitateDB の `PostgresApplicationAuditSink.append` は**呼び出しごとに `psycopg.connect` → INSERT → commit → close** する (docstring が「No pooling, one connection per call」と設計意図を述べる)。両 harness plug はこの実 sink を使う。同期の書き込みは fail-closed 級 (pre-commit) と buffer の flush だけで、buffer 級の成功事象は同期しない。**別接続の文は pipeline にまとめられない** — pipeline は同一接続の機能だからである。**補足 (起草時の裁定 8)**: r2db の sink は**自前の pool** を持ち (接続を使い回す)、MitateDB の sink は**呼びごとに接続を開いて閉じる**。したがって **`sessions` の見え方が peer で違う** — r2db は監査の書き込みで session が増えず、MitateDB は 1 回の書き込みにつき 1 session 増える。
- **F4**: psycopg 3.3.5 の pipeline 中の `execute()` は queue するだけで、**未取得の結果に `fetchone()` 等で触れた瞬間に暗黙の sync (往復) が起きる**。エラーの後は次の sync まで `PipelineAborted` になる。COPY と `stream()` は pipeline 中に使えない。`CountingCursor` は `execute` / `executemany` の override だけなので pipeline に無関係である。
- **F5**: PostgreSQL 16 の `pg_stat_database` は `xact_commit` / `xact_rollback` / **`sessions`** (PG14+) を持つ。**統計の反映には遅れが在る** — **枠の「最大 ~1 秒」は §1.3 の (5) の実測と食い違い、idle の接続では約 10 秒である** (起草時の裁定 1 で D-1 の poll をこの実測に合わせた)。

**守るべき条件**:

- **(a)** 本件は**計測と記録が成果物**である (`RM`:389 の P-8、`RM`:545 の R-20)。pipeline 化・キャッシュ・接続の使い回しは計測の後の**別の変更セット**である。**§3.4 の「WP-2 修正」は予約だけ**で、候補の列挙にとどめる。
- **(b)** **WP-1 は harness と tests だけを触り、両 peer の `src` を触らない** (Class B)。要求あたりの文数は R-79 の `execute_count` の op 前後の差から、transaction 数と session 数は `pg_stat_database` の差から出す。
- **(c)** 契約 **1.8.0** のまま、`conformance-tests/` の差分は **0**。**SI-11 / SI-14 に触れない。**
- **(d)** 公開規律 (`OPERATING_CONDITIONS.md` §1.9)。ホスト名・実 DSN・実パスを書かない (§2 の 13)。
- **(e)** **psycopg の private 属性を読まない。**

### 1.2 決定 (監督確定。D-1〜D-6)

- **D-1 (harness の `ROUNDTRIP` 行)。** `tools/perf_baseline.py` が各 (plug, op) の計測の前後で次の 2 つを取る。**`ROUNDTRIP` 行は `--roundtrip` フラグを付けたときだけ出す** (起草時の裁定 1。統計の確定待ちが 1 op につき数秒かかるので、**通常の run の所要時間を変えない**)。

  **(i) 接続ごとの文**: plug の `prepared_stats()` を、**各 op の `_measure_op` の直前 (pre) と直後 (post) に 1 回ずつ**呼び、接続ごとの `execute_count` を取る。**差分は pre → post** である (設計レビュー 1 の M-3 の裁定 (A))。こうすると **op と op の間に走る credential の発行・`authenticate`・`cross_entity` の `create_entity`** (`tools/perf_baseline.py`:931・:945・:974-975) **が当該 op の差に混ざらない** (起草時の裁定 6 が最初の op について除いたのと同じ混入を、すべての op について除く)。**pre の probe は `--roundtrip` を付けたときだけ行う** (同 M-5) — **既定の run では `prepared_stats()` の呼び出しは R-79 のまま op ごとに 1 回 (post) である**。**前の probe に同じ `conn=` が無いとき (再接続で label が変わったとき) は基準を 0 とする** (起草時の裁定 7)。

  **(ii) DB ごとの transaction と session**: 使い捨て cluster の `pg_stat_database` から、**application DB と platform DB** の `xact_commit` / `xact_rollback` / `sessions` を読む。読みは **harness 自身の管理接続**で行い、**基準は (i) と同じく当該 op の pre と post** である (設計レビュー 1 の M-6)。手順は次のとおりである (同 H-1)。

  - **(a) 読みは必ず probe の後に行う** — probe (接続への 1 文 + `commit()`) が **その接続の pending 統計を flush させる**からである (§1.3 の (5b) の run 3)。
  - **(b) `pg_stat_clear_snapshot()` の後、最短 12 秒**待ってから 1 秒ごとに読み、**3 回連続で値が動かなければ確定**とする。**最短待ちより前には確定しない** — §1.3 の (5b) の run 1 のとおり、**flush 前の平坦区間は 20 秒を超えることがあり、「値が動かないこと」は「flush 済み」の証拠にならない**からである。
  - **(c) 上限は 30 秒**とし、超えても値が動き続けるときは、その時点の値でその行を出し **`stale=1`** を付ける (確定したときは `stale=0`)。

  **補正に数える接続の導出規則** (設計レビュー 1 の M-4): 下の「probe 自身の分は行に含めない」で引く本数は、**r2db は `label` の `<application_id>` が当該 run の `app_id` に一致する接続だけ**、**MitateDB は当該 cell の backend が返す 2 本だけ**を `db=app` の補正に数える (`cross_entity` が作る 2 つ目の application の接続は数えず、`db=app` にも入らない)。**`db=platform` の補正は常に 0 である** — r2db の platform / credential / 監査 sink の pool は `default_pool_manager` に登録されず (`credential_store.py`:281・:756・:1116・:1334・:1520・:1747。plug が返すのはその manager である。`conformance_adapter_r2db_http.py`:3997-4004)、MitateDB の plug は cell の 2 本だけを返す (`backend_postgres.py`:358) からである。

  行は 2 種類である。

  ```
  ROUNDTRIP peer=<peer> plug=<plug> op=<op> requests=<(warmup+n) を K 倍した数> conn=<label> stmts=<Δexecute_count> stmts_per_req=<x.xx>
  ROUNDTRIP peer=<peer> plug=<plug> op=<op> requests=<同上> db=<app|platform> xacts=<Δcommit+Δrollback> xacts_per_req=<x.xx> sessions=<Δsessions> sessions_per_req=<x.xx> stale=<0|1>
  ```

  前者は接続ごとに 1 行、後者は DB ごとに 1 行である。**往復の総数は 1 つの数字にまとめず、成分 (文・transaction・session) を並べる** — autocommit の文は `BEGIN` / `COMMIT` を伴わないので単純加算できないからである。`requests` は harness が実際に送った要求数 (warmup 込み) である。**行の並びは `POOL` → `PREPARED` (+`PREPSTMT`) → `ROUNDTRIP`** とし、**probe を op ごとに 1 回に保つため `_emit_prepared_rows` が `prepared_stats()` の戻り値を返す形にする** (起草時の裁定 7)。

  **probe 自身の分は行に含めない**: probe の 1 文は `prepare=False` の SELECT で、counting cursor ではないので `execute_count` に入らない (差 0)。probe の `commit()` は probe した接続 1 本につきその接続の DB の `xact_commit` を **+1** するので、**`db=` の行の `xacts` からは「その op で probe が実際に走った接続の本数」を引く**。**除く量を `tools/PERF_BASELINE_README.md` と設計メモ §1 に明記する。**

  **計測の限界** (起草時の裁定 2・5。**`src` に counter は足さない** — §1.4 の (2) のまま): **`BEGIN` / `COMMIT` / `ROLLBACK` / `SAVEPOINT` / `RELEASE` は `Cursor.execute` を通らないので `execute_count` に入らず、savepoint は `pg_stat_database` にも現れない** (§1.3 の (4))。したがって savepoint の往復は本計測のどの成分にも現れない。**`cross_entity` が作る 2 つ目の application DB は `db=app` の行に入らない** (§1.3 の (8))。**この 2 点を設計メモ §1 の「計測の限界」に明記する。**
- **D-2 (`src` 不変)。** 両 peer の `src` は **1 行も触らない**。plug 側 (`conformance_adapter_*_http.py`) も既存の `prepared_stats()` で足りる。`db=` の名前の解決 (application DB 名と platform DB 名) は、**harness が plug から受け取る既存の情報** (`_resolve_cell` / DSN) から得る。**実測は §1.3 の (8) に在る** — platform DB 名は両 http plug の `_platform.platform_db`、application DB 名は r2db が cell の `_runtime_dsn`、MitateDB が backend の `_runtime.info.dbname` (公開 property) から得られる。**この 2 形の解決を採る** (起草時の裁定 5)。
- **D-3 (計測は監督)。** 完了ゲートの後、**K=1** (`--warmup 10 --n 100`) を**両 peer の PostgreSQL 経路の plug** で取り、`ROUNDTRIP` 行を設計メモ `docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` の §2 に**逐語で**置く。**§3 事実**: (i) op・接続ごとの文/要求、(ii) DB ごとの transaction/要求と session/要求 — **監査の同期書き込みは本計測の op では走らない**ので `db=app` の `sessions` は **0 として観測される** (§1.3 の (10b)。設計レビュー 1 の H-2)、**MitateDB の認証の per-call 接続は `db=platform` の `sessions` に現れる**、(iii) §1.3 の依存表に照らして「結果を見ずに続けて送れる文の連続」の長さ (= pipeline で節約できる往復の上限)、(iv) R-82 (catalog のキャッシュ) が消す文の数、R-81 (idempotency) が消す文の数、(v) peer の差。**§4 判断 (監督)**: pipeline 化の候補と期待値、R-81 / R-82 との重なりと着手順 (**順序の変更は依頼者裁定**なので両論で提示する)。

  **K=1 のみとする理由** (設計レビュー 1 の L-9): 台帳 `RM`:605 は「基準値 (K=1 / K=3) を前後で取る」と書くが、**K=3 はこの環境では ±10% に収束しない**ことが R-79 の実測で結論されている (`docs/work-orders/WORK_ORDER_R79_PREPARED_STATEMENT_MEASUREMENT_V1.md` §6.1 の D-5 の訂正註)。**完了ゲートに添える性能差分** (`OPERATING_CONDITIONS.md` §1.3 の 27) は **`--roundtrip` を付けない既定の run** で K=1 / K=3 を取る (§3.3 の 7)。
- **D-4 (依存表)。** **§1.3 に**、要求種別 (query / mutate / batch / cross_entity) × peer × 接続ごとの文の並びを `file:line` 付きで表にし、各文に「**独立** / **前の結果に依存** / **別接続**」を付ける。推測は推測と書く。
- **D-5 (テスト)。完了条件 1 項目 = 変異 1 つ。** `ROUNDTRIP` 行の書式と算術 (`tools/tests`、stub)、差分の基準 (前の probe の値) の扱い、`pg_stat_database` の poll が値の安定で止まること (stub)、実 PG での `sessions` +1 / `xact_commit` +1 の観測 (`tools/tests` に実 cluster を使う先例があれば従う。**先例は無い** — §1.3 の (11) の実測。**監督裁定を仰ぐ**)、`tools/PERF_BASELINE_README.md`、`tools/tests` の件数 pin、**`PERF` / `POOL` / `PREPARED` 行の書式不変**。
- **D-6 (コメント)。** docstring は現在形で書く。`python3 tools/check_comment_provenance.py --base c589785` の FAIL が「**§4.1 (1) 以外 0 行**」であること。

### 1.3 起草時の実測 (基点 `c589785` の現物)

(1)〜(5) は **監督が一次資料で確認済み**の機構上の事実 (F1〜F5) であり、起草者が現物で行番号を再確認した。(6)〜(14) は起草者の実測である。

| # | 観測 | 出所 |
|---|---|---|
| (1) | **監督確認済み (F1)。監査の書き込み (SI-14) は両 peer とも本体とは別の接続で走る。** r2db: `service.py`:118 の `_PreCommitHook` の `pre_commit` (:136) が `self._sink.append(...)` を呼び、sink は `credential_store.py`:1471 の `PostgresApplicationAuditSink` で、**自前の `_RolePool`** (:1520) を持つ (`SharedPoolManager` を通さない。R-79 §1.3 の (9))。`append` (:1547) は pool の接続 1 本で 1 transaction を開いて閉じる。**MitateDB**: `application_audit.py`:285 の `PostgresApplicationAuditSink` は docstring (:290) が「No pooling, one connection per call」と述べ、`_connect` (:327) / `append` (:330) が**呼びごとに接続を開いて INSERT → commit → close** する。**harness plug はどちらも実 sink を使う** (r2db `conformance_adapter_r2db_http.py`:1242 は `pool_size=_DEFAULT_PLATFORM_POOL_SIZE` 付き、MitateDB `conformance_adapter_mitatedb_http.py`:1022)。**帰結**: 監査の文は data 面の接続と別の接続に出るので pipeline に入れられない (同一接続の機能。(4))。**session の見え方は peer で違う** — r2db は pool で使い回すので要求ごとに増えず、MitateDB は呼びごとに 1 session 増える | `r2db-api/src/r2db_api/service.py`:118・:136、`r2db-api/src/r2db_api/credential_store.py`:1471・:1520・:1547、`MitateDB-api/src/mitatedb_api/application_audit.py`:285・:290・:327・:330、`r2db-api/conformance/conformance_adapter_r2db_http.py`:1242、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:1022 |
| (2) | **監督確認済み (F2)。r2db の 1 要求。** `query()` は :1318-1390。`self._runtime.connection()` (:1336) が `_PoolHandle.connection` → `_RolePool.connection` (:512) → `_acquire` (:325) → `_liveness_check` (:470) を通り、ping は **`autocommit = True` の下の `SELECT 1` 1 往復**である (:497-502、R-79 WP-3 の CH-0541)。続いて `with conn.transaction():` (:1339) が `BEGIN`、`_set_timeouts` (:1340 → :2447) が **`SET LOCAL` 2 文**、`_load_catalog(with_constraints=False)` (:1343 → :974) が **SELECT 2 形** (`information_schema` の列読みと index 読み。互いに独立)、client 側で entity の存在を判定 (:1344-1345)、data SELECT (:1367)、`COMMIT` である。`transact()` は :1397-。`_set_timeouts` (:1449)、idempotency (:1457 / :1458 / :1479 / :1480。**本計測では通らない** — (10))、`_load_catalog(conn)` (:1481、制約の side-table 読み `_load_field_constraints` :1092 を含む)、各 operation の `_apply` (:1505 → :1608)、`audit_hook.pre_commit()` (:1531、**別接続**)、`_idempotency_store` (:1541、本計測では通らない)、`COMMIT` である。**developer 接続は `query` / `transact` では使われない** (`apply_schema` :1918 だけ) **【起草時の確認】枠が書いた行番号 (:1336-1390 / :1397-1570) は R-79 WP-3 の後の現物で :1318-1390 / :1397- にずれている。並びと依存は枠のとおりである** | `r2db-api/src/r2db_api/postgres.py`:325・:470・:497-502・:512・:974・:1092・:1318-1390・:1397・:1449・:1457-1481・:1505・:1531・:1541・:1608・:1918・:2447 |
| (3) | **監督確認済み (F3)。MitateDB の 1 要求。** 要求は cell の `RLock` で直列化される (`cell.py`:2116 と :2138 の二重の `with self._lock:`)。catalog 読みは**呼び出しごとに独立した transaction**である — `field_domains` (`backend_postgres.py`:426) は `self._developer.cursor()` の下で `_set_timeouts` (:450 → :1550) の **`SET LOCAL` 2 文** + `information_schema.columns` の SELECT (:451-455) + 条件付きで `_field_types_locked` の SELECT (:494) を打ち、**末尾で `self._developer.commit()`** (:483) する。`read()` (:2103) は `_select_fields` (:3066。`field_domains` :3067、`fields` が `None` なら `field_types` :3118) → `_bind_filters` (:3390。`field_domains` :3424、`field_types` :3427) → `_bind_order_by` (:3147。`field_domains` :3172) で **最大 5 回**呼ぶ。`insert()` (:2058) は `_check_missing_required_fields` (:3199 → `field_types_and_constraints` :3235) 1 回 (prefetch を `_prepare_values` :3251 が :3287 で共有する) と `field_domains` (:3262) である。data 文は catalog の結果 (型・domain) からテキストを組むので **catalog の結果に依存する** | `MitateDB-api/src/mitatedb_api/cell.py`:2058・:2103・:2116・:2138・:3066-3067・:3118・:3147・:3172・:3199・:3235・:3251・:3262・:3287・:3390・:3424・:3427、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:426・:450・:483・:494・:504・:654・:1236・:1550 |
| (4) | **監督確認済み (F4)。psycopg 3.3.5 の pipeline。** `Connection.pipeline()` は `connection.py`:437。pipeline 中の `execute()` は `_cursor_base.py`:436 で command queue に積むだけである。`cursor.py`:336 の `_fetch_pipeline` が **`fetchone()` / `fetchall()` / `rowcount` 等 (:247・:263・:280・:290・:309) から呼ばれ、その場で `flush=True` の往復を起こす** — つまり**次の独立な文を queue する前に結果に触れると、その境界の節約は失われる**。エラーの後は次の sync まで `PipelineAborted` (`_cursor_base.py`:494・:618)。**COPY は pipeline 中に使えず** (:397)、**`stream()` も使えない** (`cursor.py`:166)。`CountingCursor` は `execute` / `executemany` の override だけで pipeline に無関係である (`psycopg_counting.py`:63・:67)。**併せて**: `BEGIN` / `COMMIT` / `ROLLBACK` / `SAVEPOINT` / `RELEASE` は `Connection._exec_command` (`_connection_base.py`:445) を通り、**`Cursor.execute` を通らないので `execute_count` に入らない** (`transaction.py`:99-107・:139-140・:156-157・:169-179)。**savepoint の往復は `pg_stat_database` にも現れない** | `.venv/lib/python3.11/site-packages/psycopg/connection.py`:437、`_cursor_base.py`:397・:436・:494・:618、`cursor.py`:166・:247-309・:336、`transaction.py`:99-179、`_connection_base.py`:445、`r2db-api/src/r2db_api/psycopg_counting.py`:63・:67 |
| (5) | **監督確認済み (F5) + 起草者の実測 (逐語 A)。`pg_stat_database` の形と反映の遅れ。** 使い捨て cluster (`tools/testpg/dsa_testpg.py` の `suite_lock(exclusive=False)` + `cluster()`、PostgreSQL 16.14) で観測した。**(i)** view は `xact_commit`・`xact_rollback`・`sessions`・`numbackends` ほかを持つ (列の全体は逐語 A)。**(ii)** 接続を 1 本開いて 1 文を commit して閉じると `sessions` **+1**、`xact_commit` **+2** (client の commit 1 回ぶんと、接続の確立が伴う 1 transaction)。autocommit の 1 文も `xact_commit` を増やす。`rollback()` 1 回で `xact_rollback` +1。接続を 3 本開いて閉じると `sessions` +3。**(iii) 反映の遅れ**: 持続接続で 100 回 commit した burst は、直後には **+2** しか見えず、**+10.03 秒後**に +101 になった。**backend が pending 統計を共有メモリへ出す間隔には下限が在り、idle のままの接続では約 10 秒、接続を閉じるときは即時である。** `pg_stat_clear_snapshot()` の後に読み直す点は枠のとおりである | `$SP/proto-r80.py` / `$SP/proto-r80d.py` (起草者が実行。出力は §1.3 の逐語 A)、`tools/testpg/dsa_testpg.py`:94・:142-151・:191・:346 |
| (5b) | **(設計レビュー 1 の実測。H-1 の根拠。逐語 C)** **「値が動かないこと」は「flush 済み」の証拠にならない。** run 1: 持続接続の 100 commit の burst の後、1 秒ごとに 20 秒読むと **`delta_commit=+5` が 20 秒間ずっと不動**で、**3 回連続不動の規則は t=2.01 で「確定 (stale=0)」と誤判定する** (真値は +101)。run 2: 同じ burst を idle のまま置くと t≈8 秒まで +2、**t≈11 秒で +101**、close で +102 ((5) の +10.03 秒と一致)。run 3: burst の 1.2 秒後に**同じ接続で 1 文 + commit (= probe 相当)** を打つと **probe の 0.2 秒後に +102** になる — **probe された接続の pending は probe の直後に flush される**が、**probe されない接続 (r2db の監査 sink の自前 pool 等) は idle flush 待ちで 20 秒でも来ないことがある** | `$SP/review-r80-design.md` (設計レビュー 1 の生出力)、`$SP/poll-check.log` / `poll-check2.log` / `poll-check3.log` |
| (10b) | **(設計レビュー 1 の H-2)** **監査の同期書き込みは本計測の op では 0 回である。** 同期の pre-commit は **destructive のときだけ**走る — r2db は `if destructive and audit_hook is not None:` (`postgres.py`:1530-1531)、MitateDB は `if destructive and not dry_run:` (`cell.py`:2841) と `if destructive and hook is not None: hook.pre_commit()` (:2894-2895)。**harness の op は `select_eq` / `insert` / 単一 entity の batch / `cross_entity` の insert だけで destructive ではない。** **帰結**: `db=app` の `sessions` は **0 が正しい観測**である (app DB の接続は r2db が pool、MitateDB が cell の持続 2 本)。**MitateDB の credential store は呼びごとに接続を開いて閉じる** (`credential_store_postgres.py`:26-28 の「No pooling, one connection per call」・:300) ので、**`sessions` は `db=platform` 側に出る** | `r2db-api/src/r2db_api/postgres.py`:1530-1531、`MitateDB-api/src/mitatedb_api/cell.py`:2841・:2894-2895、`MitateDB-api/src/mitatedb_api/credential_store_postgres.py`:26-28・:300 |
| (6) | **harness が 1 op で送る要求数。** `_measure_op` (`tools/perf_baseline.py`:654) は `warmup * concurrency` 件の warmup と `n * concurrency` 件の計測を送る (:673-:687 の実ループ plug 経路、:695-:700 の in-process 経路)。`_measure_plug` も `(warmup + n) * concurrency` 件ぶんの値を前もって用意する (式は :932・:956。:924・:955 はその註の行である — 設計レビュー 1 の観察を現物で確かめた)。**K=1・`--warmup 10 --n 100` で 1 op = 110 要求**である。`PERF` 行の `n=` は計測ぶんの標本数 (:705-:734) であって要求数ではないので、**`ROUNDTRIP` の `requests=` は別の値である** | `tools/perf_baseline.py`:654-702・:705-734・:924・:955 |
| (7) | **probe が何を出すか。** `probe_prepared_statements` (`psycopg_counting.py`:124) は接続が IDLE のときだけ (:157)、**素の `psycopg.Cursor`** で 1 文を `prepare=False` で読み (:159-160)、**直後に `conn.commit()`** する (:162)。counting cursor ではないので `execute_count` は増えない。**probe した接続 1 本につきその接続の DB の `xact_commit` が +1 になる** ((5) の (ii))。非 IDLE の接続は早期 return で commit しない。r2db は `_RolePool.prepared_stats` (`postgres.py`:415) が **idle 接続を `get_nowait` で drain して probe し `put_nowait` で戻す** ので probe する本数は可変であり、MitateDB は `PostgresBackend.prepared_stats` (`backend_postgres.py`:358) が `_runtime` / `_developer` の **2 本**、`ApplicationCell.prepared_stats` (`cell.py`:614) が cell lock の下で委譲する | `r2db-api/src/r2db_api/psycopg_counting.py`:124・:157-162、`r2db-api/src/r2db_api/postgres.py`:415、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:358、`MitateDB-api/src/mitatedb_api/cell.py`:614 |
| (8) | **(D-2・U-2) `db=` の名前の解決は harness の手の内で済む。** **platform DB 名**: 両 http plug は `_bootstrap_platform` が作る `_Platform` を `self._platform` に持ち、その `platform_db` が `<prefix>_platform` である (r2db :271・:319・:395・:1131、MitateDB :259・:354・:441・:921)。**socket plug は http plug を継承する**ので同じ属性を持つ (`conformance_adapter_r2db_socket.py`:477、`conformance_adapter_mitatedb_socket.py`:338)。**application DB 名**: r2db は `_resolve_cell` (`tools/perf_baseline.py`:318) が返す `PostgresCell` の `_runtime_dsn` (`postgres.py`:852) を `psycopg.conninfo.conninfo_to_dict` で解けば得られる。MitateDB の `PostgresBackend` は **dsn を属性に持たない**ので、`_resolve_backend_object` (:345) が返す backend の `_runtime.info.dbname` (psycopg の公開 property) から得る。**2 形の解決が要る。** **管理接続**: 使い捨て cluster の admin DSN は `main()` が `os.environ` に入れている (`tools/perf_baseline.py`:1138-1147、`dsa_testpg.py`:94・:142-151)。**注**: MitateDB の `cross_entity` op は 2 つ目の application を作る (R-79 設計メモ §3 の (i)) ので、その application DB は `db=app` の行には入らない | `r2db-api/conformance/conformance_adapter_r2db_http.py`:271・:319・:395・:1131、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:259・:354・:441・:921、`r2db-api/conformance/conformance_adapter_r2db_socket.py`:477、`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py`:338、`r2db-api/src/r2db_api/postgres.py`:852、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:280、`tools/perf_baseline.py`:318・:345・:1138-1147 |
| (9) | **R-79 の実測の内訳 (本件の出発点)。** K=1・110 要求で r2db runtime 接続は query 668 / mutate +770 / batch +1210 文、MitateDB は runtime 接続が query 334、developer 接続が query 1788 文である (`docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` §3 の (i))。**r2db の 6 文/要求の内訳は (2) の並びと 1 対 1 で合う** (ping 1 + `SET LOCAL` 2 + catalog 2 + data 1)。**MitateDB の 16 文/要求は (3) の catalog 読み 5 回 × (`SET LOCAL` 2 + SELECT 1) + `_field_types_locked` の 1 文と合う** (**この対応付けは起草者の推測である** — 1 要求の文を逐語で採った記録は無い。WP-2 の実測で確かめる) | `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` §3 の (i)・(ix)、§1.3 の (2)・(3) |
| (10) | **計測経路に idempotency の文は 1 つも流れない。** harness の mutate / batch は `_mutate_request` (`conformance_adapter_r2db_http.py`:1703) が body に `{"operations": …}` しか載せず、idempotency key を送らない。r2db の `transact` は `if idempotency_key:` の枝 (`postgres.py`:1455-1480・:1538-1541) に入らない。**帰結**: D-3 の §3 事実 (iv) のうち **R-81 (idempotency) が消す文の数は本計測では 0 として観測される** | `r2db-api/conformance/conformance_adapter_r2db_http.py`:1703-1717、`r2db-api/src/r2db_api/postgres.py`:1455-1480・:1538-1541 |
| (11) | **(D-5) `tools/tests` に実 PostgreSQL を使う先例は無い。** `tools/tests/pytest.ini` は rootdir を `tools/tests` に固定して**リポジトリルートの `conftest.py` (使い捨て cluster の起動) を読み込ませない**。その註自身が「a suite that never touches PostgreSQL at all」と述べ、設計 `docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` v0.2 の D-1 を出所に挙げる。`grep -rn 'psycopg' tools/tests` の hit は docstring の文字列と allowlist の表だけで、**実接続は 0 件**である。**したがって D-5 の「実 PG での `sessions` +1 / `xact_commit` +1 の観測」を `tools/tests` に置く先例は無く、監督裁定を要する** (§2.2 の 17) | `tools/tests/pytest.ini`:1-16、`docs/design/TEST_POSTGRES_ISOLATION_V0_1.md`、`grep -rn 'psycopg' tools/tests` (起草者が実行) |
| (12) | **件数 pin と既存の行。** `tools/tests/test_no_shared_cluster_defaults.py`:278 の `assert len(files) == 31` (列挙は `git ls-files` 経由なので**追跡前の新規ファイルは見えない**)。harness の行は `_format_row` (`PERF`、:735)、`_format_pool_row` (`POOL`、:749)、`_format_prepared_row` (`PREPARED`、:800)、`_format_prepstmt_row` (`PREPSTMT`、:826) で、順序は `_emit_measurement_rows` (:866) が `POOL` → `PREPARED` と固定する。README の該当節は `## Output format` (:109)、`## POOL lines (R-78)` (:144)、`## PREPARED / PREPSTMT lines (R-79)` (:209) | `tools/tests/test_no_shared_cluster_defaults.py`:278、`tools/perf_baseline.py`:735・:749・:800・:826・:866、`tools/PERF_BASELINE_README.md`:109・:144・:209 |
| (13) | **変更クラスの実測。** §2.1 の代表パスを `python3 tools/change_class.py` に渡すと **`class=B`** (`docs/`・`tools/PERF_BASELINE_README.md` が A、`tools/perf_baseline.py`・`tools/tests/` が B)。着手時に**触った全パス**で測り直す | `python3 tools/change_class.py` (起草者が実行。§1.3 の逐語 B) |
| (14) | **(D-4) 依存表** は下の「§1.3 の依存表」に在る | 同表の `file:line` |

#### §1.3 の逐語 A — プロトタイプ `$SP/proto-r80.py` / `$SP/proto-r80d.py` の出力 ((5))

```
view columns: ['datid', 'datname', 'numbackends', 'xact_commit', 'xact_rollback', 'blks_read', 'blks_hit', 'tup_returned', 'tup_fetched', 'tup_inserted', 'tup_updated', 'tup_deleted', 'conflicts', 'temp_files', 'temp_bytes', 'deadlocks', 'checksum_failures', 'checksum_last_failure', 'blk_read_time', 'blk_write_time', 'session_time', 'active_time', 'idle_in_transaction_time', 'sessions', 'sessions_abandoned', 'sessions_fatal', 'sessions_killed', 'stats_reset']
[base] xact_commit=0 xact_rollback=0 sessions=0 (stabilize 0.34s, polls=7)
[after] xact_commit=2 xact_rollback=0 sessions=1 (stabilize 0.35s, polls=7)
[delta] xact_commit=+2 xact_rollback=+0 sessions=+1
[autocommit 1 stmt] xact_commit=+2 sessions=+1
[held open] xact_commit=+1 sessions=+1
[after close] xact_commit=+2 sessions=+1
[1 rollback] delta_commit=+9 delta_rollback=+1
[3 open/close] delta_sessions=+3 delta_commit=+6
```

```
stats_fetch_consistency / track_counts:
    stats_fetch_consistency = cache
    track_counts = on
    track_activities = on
[base] (5, 0, 2, 1)
[burst of 100 commits in 0.004s, then IDLE 20s]
    burst + 0.000s (7, 0, 2, 1) dcommit=+2
    burst +10.029s (106, 0, 2, 1) dcommit=+101
  -> visible 101 of 100
[1 further commit, poll 5s]
    one + 0.000s (106, 0, 2, 1) dcommit=+0
  -> visible 0 of 1 (+ pending backlog)
[close, poll 5s]
    close + 0.000s (107, 0, 2, 0) dcommit=+1
  -> on close +1 commits, sessions +0
[total since base] +102 commits for 100+2 client commits
```

#### §1.3 の逐語 B — `tools/change_class.py` の出力 ((13))

```
class=B
conformance_required=true
A docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md
A docs/work-orders/WORK_ORDER_R80_ROUNDTRIP_MEASUREMENT_V1.md
A tools/PERF_BASELINE_README.md
B tools/perf_baseline.py
B tools/tests/test_no_shared_cluster_defaults.py
B tools/tests/test_perf_baseline.py
```

#### §1.3 の逐語 C — 設計レビュー 1 の `poll-check*.log` の要旨 ((5b))

```
base (2, 1)
burst done in 0.004s
t=0.00 xact_commit=7 sessions=1 delta_commit=+5
t=1.01 xact_commit=7 sessions=1 delta_commit=+5
t=2.01 xact_commit=7 sessions=1 delta_commit=+5
  -> WO rule would CONFIRM here (stale=0): delta=+5 at t=2.01
t=19.13 xact_commit=7 sessions=1 delta_commit=+5
decided: (2.0139379501342773, 5) final delta: 5
```

```
base (1, 1)
idle t~ 0s delta=+2
idle t~ 8s delta=+2
idle t~11s delta=+101
after close delta=+102 sessions=1
```

```
base 1
t=0.0 delta=+2
t=1.2 delta=+2 (before probe)
probe+0.2s delta=+102
probe+1.7s delta=+102
```

#### §1.3 の依存表 (D-4)

**読み方**: 「文」は 1 回の `Cursor.execute` である。`BEGIN` / `COMMIT` / `SAVEPOINT` / `RELEASE` は `execute` を通らないので別行に「(往復)」と書く ((4))。**savepoint を使う文には【SP】の印を付ける** (起草時の裁定 2) — **`SAVEPOINT` / `RELEASE` の往復は `execute_count` にも `pg_stat_database` にも現れない**ので、その行の往復は本計測のどの成分にも数えられない。**独立** = 直前までの結果を見ずに送れる、**依存** = 直前の文の結果を client 側で使ってから組み立てる、**別接続** = その接続では送れない。**pipeline で節約できる往復の上限は「独立」が連続する長さ − 1 である。**

**r2db — `query`** (`postgres.py`:1318-1390。runtime 接続 1 本)

| # | 文 / 往復 | 区分 | 出所 |
|---|---|---|---|
| 1 | ping `SELECT 1` (autocommit) | 独立 (要求の処理の前。接続の貸し出しに属する) | :470-509 |
| 2 | `BEGIN` (往復) | 独立 | :1339 |
| 3 | `SET LOCAL statement_timeout` | 独立 | :1340 → :2447 |
| 4 | `SET LOCAL lock_timeout` | 独立 | :2447 |
| 5 | catalog SELECT (列) | 独立 | :1343 → :974 |
| 6 | catalog SELECT (index) | 独立 | :974 |
| 7 | data SELECT | 依存 (5・6 の結果で entity / 列を判定してから組む) | :1344-1367 |
| 8 | `COMMIT` (往復) | 依存 (7 の後) | :1339 の block 終端 |
| — | 監査 (buffer 級の成功事象) | 同期の書き込みは無い | `service.py`:118 |

**r2db — `mutate`** (1 operation の `transact`。`postgres.py`:1397-)

| # | 文 / 往復 | 区分 | 出所 |
|---|---|---|---|
| 1 | ping `SELECT 1` (autocommit) | 独立 | :470-509 |
| 2 | `BEGIN` (往復) | 独立 | :1448 |
| 3-4 | `SET LOCAL` ×2 | 独立 | :1449 → :2447 |
| 5-6 | catalog SELECT ×2 | 独立 | :1481 → :974 |
| 7 | **【SP】** `SAVEPOINT` (往復) | 独立 | :1092 の block |
| 8 | **【SP】** 制約 registry の SELECT | 独立 | :1092-1119 |
| 9 | **【SP】** `RELEASE SAVEPOINT` (往復) | 依存 (8 の後) | :1092 の block |
| 10 | data INSERT … RETURNING | 依存 (5・6・8 の結果で列と制約を判定してから組む) | :1505 → :1608 |
| 11 | 監査 pre-commit の INSERT + その `BEGIN` / `COMMIT` | **別接続** (destructive のときだけ。insert は非 destructive) | :1531、(1) |
| 12 | `COMMIT` (往復) | 依存 | :1448 の block 終端 |
| — | **【SP】** idempotency の文 (`_idempotency_lookup` / `_idempotency_reserve` は savepoint の中で読む) | 本計測では通らない ((10)) | :1251・:1264・:1455-1480・:1538-1541 |

**r2db — `batch`** (5 operations)。上の 1〜9 と 12 は同じで、**10 が 5 回繰り返される** (`_apply` :1505 のループ)。各 `_apply` は前の結果に**依存しない**形 (insert のみ) だが、**現在の実装は 1 件ずつ結果を取り出してから次を送る** (:1505-1520)。**upsert 系の operation は前段の存在確認の結果に依存する** (`_apply_upsert` :1764。本計測の batch は insert だけなので通らない)。

**MitateDB — `query` (`read`)** (`cell.py`:2103。developer 接続と runtime 接続の 2 本)

| # | 文 / 往復 | 接続 | 区分 | 出所 |
|---|---|---|---|---|
| 1 | `BEGIN` + `SET LOCAL` ×2 + catalog SELECT (+ 型 registry の SELECT) + `COMMIT` | developer | 独立 (`_select_fields` の `field_domains`) | :3066-3067 → `backend_postgres.py`:426-503 |
| 2 | 同上 | developer | 独立 (`_select_fields` の `field_types`。`fields` が `None` のときだけ) | :3118 → :504 |
| 3 | 同上 | developer | 独立 (`_bind_filters` の `field_domains`) | :3424 → :426 |
| 4 | 同上 | developer | 独立 (`_bind_filters` の `field_types`) | :3427 → :504 |
| 5 | 同上 | developer | 独立 (`_bind_order_by` の `field_domains`) | :3172 → :426 |
| 6 | `BEGIN` + `SET LOCAL` ×2 (:1448) + data SELECT (:1449) + `COMMIT` (:1462) | runtime | 依存 (1〜5 の型と domain で WHERE / ORDER BY の値を組む) | :2138 → `backend_postgres.py`:1397-1462 |

**1〜5 は互いに独立だが、それぞれが自分の transaction を `commit()` で閉じる** (`backend_postgres.py`:483)。**同じ接続の独立な文の連続なので pipeline の対象になり得るが、transaction の切り方を変えることは R-82 と重なる** (§1.5 の (U-1) の候補 (C))。

**MitateDB — `mutate` (`insert`)** (`cell.py`:2058)

| # | 文 / 往復 | 接続 | 区分 | 出所 |
|---|---|---|---|---|
| 1 | `BEGIN` + `SET LOCAL` ×2 + 型と制約の SELECT + `COMMIT` | developer | 独立 (`_check_missing_required_fields`。prefetch として `_prepare_values` と共有する) | :3235 → `backend_postgres.py`:654 |
| 2 | `BEGIN` + `SET LOCAL` ×2 + catalog SELECT + `COMMIT` | developer | 独立 (`_prepare_values` の `field_domains`) | :3262 → :426 |
| 3 | `BEGIN` + `SET LOCAL` ×2 + INSERT … RETURNING + `COMMIT` | runtime | 依存 (1・2 の型と domain で値を符号化する) | `backend_postgres.py`:1236 |
| 4 | 監査 pre-commit の INSERT (+ 接続の確立と切断) | **別接続** | destructive のときだけ | `application_audit.py`:330 |

**MitateDB — `batch` / `cross_entity`** (`cell.py`:2572)。**2 pass** である。pass 1 は operation ごとに `_plan_operation` が上の `mutate` の 1〜2 と同じ catalog 読みを行う (**独立**、operation の数だけ繰り返す)。pass 2 は `self._backend.begin()` (:2852 付近) の 1 transaction の中で `insert_in_transaction` / `update_in_transaction` / `delete_in_transaction` を順に送り (**各文は pass 1 の結果に依存**、`update` / `delete` は WHERE の評価結果に依存する)、`audit_hook.pre_commit()` (**別接続**) の後に commit する。**この並びの逐語は WP-2 の実測で確かめる** (**本行は起草者の読解であり、文の数の逐語記録は無い**)。

### 1.4 却下した代替案 (監督確定。蒸し返さない)

- **(1) 計測の前に pipeline 化する** — `RM`:389 の P-8 に反する。
- **(2) `src` に transaction / session の counter を足す** — `pg_stat_database` で足りる (D-2)。
- **(3) `log_statement=all` の解析** — cluster 設定に依存し壊れやすい。
- **(4) 監査 sink の接続の使い回しを本件で決める** — F1 の設計意図 (呼びごとに別接続であることが D-4 の要求を構造で満たす) を変える判断は**計測の後**である。

### 1.5 未確定 (監督判断待ち。両論のまま残す)

- **(U-1) WP-2 修正 (§3.4) の内容。** WP-2 の §4 の判断の後に監督が確定する。候補は次の 4 つである。
  - **(A)** 依存の無い文の連続 (`SET LOCAL` ×2 + catalog 読み) を `pipeline()` にまとめる。
  - **(B)** `SET LOCAL` 2 文を `SELECT set_config(...), set_config(...)` の 1 文にする (R-79 の申し送り。`docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` §4)。
  - **(C)** MitateDB の catalog 読みの独立 transaction を 1 transaction にまとめる (**R-82 と重なる**)。
  - **(D)** 何もしない (R-81 / R-82 の後に再計測する)。
  - **着手順の変更は依頼者裁定である** (`RM`:605-607 の「着手順は … R-80 → R-81 → R-82 …」、依頼者指示 2026-09-21)。
- **(U-2) `db=` の解決が harness から届くか。** **【確定 2026-09-23 (起草時の裁定 5)。行は消さない (`OPERATING_CONDITIONS.md` §1.8 の 56)】 届く。2 形の解決を採り、`cross_entity` が作る 2 つ目の application DB は `db=app` の行に入らない — これは計測の限界として設計メモ §1 に明記する。** (以下は確定前の記述) **届く** — §1.3 の (8) の実測のとおり、platform DB 名は両 plug の `_platform.platform_db`、application DB 名は r2db が cell の `_runtime_dsn`、MitateDB が backend の `_runtime.info.dbname` から得られる。**ただし 2 形の解決が要り、`cross_entity` が作る 2 つ目の application DB は `db=app` の行に入らない** (同 (8))。この 2 点の扱いは監督判断である。

## 2. WP-1 — harness に `ROUNDTRIP` 行を足す (実装担当)

**目的**: 「1 要求が DB と何回やり取りしているか」を、文・transaction・session の 3 成分で出せる形にする。**両 peer の `src` を 1 行も触らない。**

**読むべき正本**: §1.1 (守る条件) / §1.2 (D-1〜D-6) / §1.3 (実測と依存表) / §1.4 (却下案) / §1.5 (未確定)。規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.3〜§1.6・§1.9・§1.10、性能計測の同時実行の禁止は同 §2 の 19。

### 2.1 触ってよいパス

- `tools/perf_baseline.py` — **`ROUNDTRIP` 行と `--roundtrip` フラグの追加だけ** (D-1)。**`PERF` / `POOL` / `PREPARED` / `PREPSTMT` 行の列名・並び・書式・行数、`--concurrency` の既存の意味、`suite_lock` / 使い捨て cluster の扱い、`_run_self_check` を 1 文字も変えない。** `_emit_measurement_rows` (:866) に 3 つ目の emit を足すことと、**probe を op ごとに 1 回に保つために `prepared_stats()` の戻り値を `_emit_prepared_rows` と新しい emit で共有する**ことは認める (完了条件 3)。
- `tools/tests/test_perf_baseline.py` — `ROUNDTRIP` 行の形式と算術、差分の基準、poll、probe が 1 回であること、行の並びのテストを追加する。**既存のテストの本体は変えない。**
- `tools/tests/test_no_shared_cluster_defaults.py` — **件数 pin (:278 の 31) の実測更新だけ** (新規テストファイルを足す場合)。
- `tools/PERF_BASELINE_README.md` — `## PREPARED / PREPSTMT lines (R-79)` (:209) の後に `ROUNDTRIP` 行の説明を足す (D-1)。**`--roundtrip` の run では最初の op の `POOL lock=` の `acquire` が pre の基準 probe 1 回分を含む旨も、この新しい節に*追記*する** (設計レビュー 1 の M-5。**既存の `## POOL lines (R-78)` 節 (:144) の本文は 1 文字も書き換えない**)。**成分を単純加算しない理由・`requests` が warmup 込みの実要求数であること・probe の `commit()` を差分から除くこと (除く量)・統計の反映に遅れが在ること**を書く。既存の `PERF` / `POOL` / `PREPARED` / `PREPSTMT` の記述を書き換えない。
- `docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` — **本書と同じ変更セットで起草済みの骨**である。WP-1 は §1 の記述が実装と食い違っていたときだけ直す。**§2〜§4 を埋めない。判断を先に書かない。**
- `docs/code-history/` — コメントの来歴検査 (`tools/check_comment_provenance.py --register`) が求める記録が要る場合だけ、その 1 箇所。

**これ以外は 0 件。** とくに **両 peer の `src`・`tests`・`conformance` を 1 行も触らない**。`spec/`・`conformance-tests/`・`security/`・両 peer の `migrations`・`RM` も触らない (変異での一時編集は別。`mutate.py` が復元する)。**既存の検査が新しいコードで赤になったら直さず報告する** (§1.5 の 37)。

### 2.2 完了条件 (26 件)

| # | 完了条件 |
|---|---|
| 1 | **(D-1)** `ROUNDTRIP` の **`conn=` の行**が §1.2 の D-1 の書式ちょうどである (`peer` / `plug` / `op` / `requests` / `conn` / `stmts` / `stmts_per_req` の名前・順序・`0.00` 形式)。**stub の接続 dict** で pin する (実 plug の起動に依らないテスト) |
| 2 | **(D-1)** `ROUNDTRIP` の **`db=` の行**が §1.2 の D-1 の書式ちょうどである (`db` の値は **`app`** か **`platform`** の 2 語、`xacts` / `xacts_per_req` / `sessions` / `sessions_per_req` / **`stale`**)。stub の統計 dict で pin する |
| 3 | **(D-1・設計レビュー 1 の M-3)** `--roundtrip` の run では **probe が op ごとに pre 1 回 + post 1 回 = 2 回**である。`prepared_stats()` を数える stub で、1 つの (plug, op) を通じて **呼び出しが 2 回**であり、**`PREPARED` 行と `ROUNDTRIP` の `conn=` 行が同じ post の戻り値を使う** (post が 2 回呼ばれない) ことを観測する |
| 4 | **(D-1)** `stmts` が **直前の probe の値との差**である。stub で同じ (plug) に対し 2 回続けて emit を駆動し、2 回目の `stmts` が**累積値ではなく差**であることを観測する |
| 5a | **(D-1・設計レビュー 1 の M-3)** **基準は当該 op の pre の probe の値**である。stub で、op と op の間に `execute_count` が動いても (credential の発行・`authenticate` 相当)、その分が**次の op の `stmts` に入らない**ことを観測する |
| 5b | **(D-1・起草時の裁定 7)** **pre の probe に同じ `conn=` が無いとき** (再接続で label が変わったとき) は**基準を 0** とする。stub で label が変わった接続の `stmts` が post の値そのものになることを観測する (例外を投げず、前の label の値も使わない) |
| 6 | **(D-1)** `stmts_per_req` / `xacts_per_req` / `sessions_per_req` が **`requests` で割った値**であり、`requests == 0` のとき `0.00` である (`ZeroDivisionError` を出さない) |
| 7 | **(D-1)** `requests` が **`(warmup + n) * concurrency`** である (§1.3 の (6))。`PERF` 行の `n=` と**別の値**であることを、`warmup > 0` の stub で観測する |
| 8 | **(D-1・設計レビュー 1 の M-6)** `xacts` が **`Δxact_commit + Δxact_rollback`**、`sessions` が **`Δsessions`** であり、**差の基準は当該 op の pre の読み**である (`conn=` の行と同じ基準)。stub の pre / post の値で観測する |
| 9 | **(D-1・設計レビュー 1 の M-4)** **probe の `commit()` を `xacts` から除く。** 除く量は「その op で probe が実際に走った接続 (`probed` が true) のうち、**D-1 の導出規則でその DB に属すと決まる接続**の本数」である (r2db は `label` の `<application_id>` が当該 run の `app_id` と一致する接続、MitateDB は当該 cell の 2 本。**`db=platform` は常に 0**)。stub で `db=app` から probe 2 本ぶんが引かれ、`db=platform` から 0 本ぶんが引かれること、および**別 application の label の接続が数えられない**ことを観測する |
| 10 | **(D-1)** `pg_stat_database` の読みの前に **`pg_stat_clear_snapshot()`** を打つ。fake の管理接続が受け取った SQL の並びで観測する |
| 11 | **(D-1・設計レビュー 1 の H-1)** poll は **最短 12 秒待ってから** 1 秒ごとに読み、**3 回連続で値が動かなければ確定**し、**上限 30 秒**で打ち切る。**最短待ちより前には確定しない**ことを、fake の管理接続が「最初から値が動かない」場合に**最短待ちを経るまで確定しない**ことで観測する。**値が変わり続ける場合に上限で戻る**ことも観測する。**実時間に依存しない形にする** — 時計と待ちを注入するか、最短待ち・間隔・上限を引数で渡す |
| 12a | **(D-1・D-2)** `db=` の解決が **§1.3 の (8) の 2 形**で行われる。stub の adapter (r2db 形: cell が `_runtime_dsn` を持つ / MitateDB 形: backend が `_runtime.info.dbname` を持つ) の両方で application DB 名が取れ、`_platform.platform_db` から platform DB 名が取れることを観測する |
| 12b | **(D-1・D-2)** **どちらの形でも解決できない plug では `db=` の行を出さず、例外も投げない。** どちらの属性も持たない stub で、行が 0 行であり呼び出しが正常に戻ることを観測する |
| 13 | **(D-1)** `ROUNDTRIP` 行は **同じ op の `PREPARED` 行の後**に出る (`POOL` → `PREPARED` (+`PREPSTMT`) → `ROUNDTRIP`)。`_emit_measurement_rows` を直接呼ぶテストで観測する (既存の順序テストの型に倣う) |
| 14 | **(D-1)** `prepared_stats()` を持たない plug では `ROUNDTRIP` の `conn=` 行が **0 行**である (例外を投げない)。既存の `PREPARED` 行の扱いと同じ |
| 15 | **(D-1)** **socket 転送の plug でも `ROUNDTRIP` 行が出る**。stub が `transport_kind == "socket"` を宣言していても行が出ることを観測する |
| 16 | **(D-2) 監査照合**: **両 peer の `src`・`tests`・`conformance` の差分が 0 行**である。`git diff --stat` で示す |
| 17 | **(D-5・起草時の裁定 4) 監査照合 (監督が WP-2 で照合する)**: **実 PostgreSQL を使うテストは `tools/tests` に置かない** — 同 suite は PostgreSQL に触らない造りであり先例が無いからである (§1.3 の (11))。代わりに**空振り禁止 (§1.5 の 32) の実証を WP-2 の実測で行う** — 監督の `ROUNDTRIP` 行で、**`db=app` について `xacts ≥ requests`**、**`sessions` は (i) MitateDB の `db=platform` で `≥ 1`、(ii) `db=app` では 0 が期待値であり 0 でも空振りではない** (設計レビュー 1 の H-2、§1.3 の (10b)) ことが観測されること (§3.3 の 2)。**実装担当は `$SP/proto-r80.py` 相当を使い捨て cluster で 1 回走らせ、その出力を報告に貼る** (完了条件にはしない) |
| 18 | **(D-5) 監査照合**: `PERF` / `POOL` / `PREPARED` / `PREPSTMT` 行の列名・並び・書式・行数と `--concurrency` の既存の意味が **1 文字も変わっていない**。既存の `test_perf_row_format_is_stable`・`test_pool_row_format_is_stable_*`・`test_prepared_row_format_is_stable`・`test_emit_measurement_rows_prints_pool_lines_before_prepared_lines` が緑のまま。`git diff` で示す |
| 19 | **(D-5・D-6) 監査照合**: `tools/PERF_BASELINE_README.md` に `ROUNDTRIP` 行の書式と、**`--roundtrip` を付けたときだけ出ること・成分を単純加算しない理由・`requests` の意味・probe の `commit()` を除く量・統計の反映の遅れと `stale=1` の意味・`BEGIN` / `COMMIT` / savepoint がどの成分にも現れないこと**が書かれている。`docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` の §2〜§4 が**空のまま**である。`python3 tools/check_doc_refs.py` が 0 dangling。`tools/tests/test_no_shared_cluster_defaults.py`:278 の件数 pin について、**`git add -N` の後に `tools/tests` を回し、pin が実測と一致することを確認した** (設計レビュー 1 の L-7。この 31 は「module 直下で admin DSN の環境変数名を定義する追跡ファイル」の数であって `tools/tests` のファイル数ではない (同ファイル :270-277)。**新規ファイルがその定義を持たない限り 31 のままである** — 無条件に +1 しない) |
| 20 | **監査照合**: `python3 tools/check_comment_provenance.py --base c589785 tools/perf_baseline.py` の FAIL 行が **§4.1 (1) だけ** (D-6)、`python3 tools/change_class.py <触った全パス>` が `class=B`、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged。報告前に `tools/tests -q` を **1 回**回して緑 (集計行を逐語で報告に残す。**完了ゲートは監督**)。§2.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み (§1.4 の 29〜31)。かつ §2.3 の対応表に**対応の無い行が無い** |
| 21a | **(D-1・起草時の裁定 1)** `ROUNDTRIP` 行は **`--roundtrip` を付けたときだけ**出る。付けないときは `conn=` の行も `db=` の行も **0 行**であり、**`pg_stat_database` の読みも走らない** (fake の管理接続が 1 度も呼ばれない) ことを観測する。既定値が `False` であることも観測する |
| 21b | **(D-1・設計レビュー 1 の M-5)** **既定の run (`--roundtrip` 無し) では `prepared_stats()` の呼び出しが op ごとに 1 回 (post) のまま**である。`prepared_stats()` を数える stub で観測する (**pre の基準 probe がフラグの外で走らない** — R-79 が `tools/PERF_BASELINE_README.md`:144 に確定させた `POOL lock=` の `acquire` の値と `PREPARED` の基準をずらさないため) |
| 22a | **(D-1・設計レビュー 1 の H-1)** poll が**確定した**とき (最短待ちの後に 3 回連続不動) は **`stale=0`** である。fake の管理接続で観測する |
| 22b | **(D-1・設計レビュー 1 の H-1)** poll が**上限に達しても値が動き続けた**とき、その時点の値で `db=` の行を出し **`stale=1`** を付ける。fake の管理接続で観測する |

### 2.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) |
|---|---|
| 1 | **M1**: `conn=` の行の列名を 1 つ変える (例 `stmts_per_req=` → `per_req=`) → 完了条件 1 の形式テストが赤 |
| 2 | **M2**: `db=` の行の列名を 1 つ変える (例 `sessions_per_req=` → `sess_per_req=`) → 完了条件 2 の形式テストが赤 |
| 3 | **M3**: post の `prepared_stats()` を `PREPARED` 用と `ROUNDTRIP` 用に 1 回ずつ呼ぶ (op ごと 3 回になる) → 完了条件 3 の呼び出し回数テストが赤 |
| 4 | **M4**: `stmts` を差ではなく `execute_count` の累積値にする → 完了条件 4 のテストが赤 |
| 5a | **M5**: pre の probe を落とし、基準を「前の op の post」に戻す → 完了条件 5a のテストが赤 |
| 5b | **M19**: pre に無い `conn=` のとき基準を 0 にせず、その接続の行を落とす → 完了条件 5b のテストが赤 |
| 6 | **M6**: `requests == 0` のときの `0.00` の枝を落とす (割り算をそのまま行う) → 完了条件 6 のテストが赤 |
| 7 | **M7**: `requests` を `n * concurrency` にする (warmup を落とす) → 完了条件 7 のテストが赤 |
| 8 | **M8**: `xacts` から `Δxact_rollback` を落とす → 完了条件 8 のテストが赤 |
| 9 | **M9**: probe の `commit()` ぶんを引かない → 完了条件 9 のテストが赤 |
| 10 | **M10**: 読みの前の `pg_stat_clear_snapshot()` を落とす → 完了条件 10 のテストが赤 |
| 11 | **M11**: poll の**最短待ちの枝を落とす** (最短待ちを経ずに 3 回連続不動だけで確定する) → 完了条件 11 のテストが赤 (設計レビュー 1 の H-1) |
| 12a | **M12**: application DB 名の解決から 2 形のうち 1 形 (`_runtime.info.dbname`) を落とす → 完了条件 12a のテストが赤 |
| 12b | **M20**: どちらの形でも解決できないときに例外を投げる → 完了条件 12b のテストが赤 |
| 13 | **M13**: `_emit_measurement_rows` の中で `ROUNDTRIP` の emit を `PREPARED` の emit より前に置く → 完了条件 13 の並びテストが赤 |
| 14 | **M14**: `prepared_stats` を持たない plug でも `conn=` の行を出そうとする (`getattr` の既定を外す) → 完了条件 14 のテストが赤 (例外) |
| 15 | **M15**: `ROUNDTRIP` 行の出力を plug 名の `-socket` で抑止する → 完了条件 15 のテストが赤 |
| 21a | **M16**: `--roundtrip` の有無に関わらず `ROUNDTRIP` 行を出す (フラグの判定を外す) → 完了条件 21a のテストが赤 |
| 21b | **M18**: pre の基準 probe をフラグの外でも走らせる → 完了条件 21b のテストが赤 (設計レビュー 1 の M-5) |
| 22a | **M21**: 確定したときも `stale=1` を出す (常に 1 にする) → 完了条件 22a のテストが赤 |
| 22b | **M17**: poll が上限に達したときも `stale=0` を出す (上限到達の枝を落とす) → 完了条件 22b のテストが赤 |
| 16・17・18・19・20 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す)。**完了条件 17 は監督が WP-2 で照合する** (起草時の裁定 4) |

- **M1〜M21 が赤にする test id は新規テストの名前**なので、実装担当が §2.2 の各行に対応するテストを作り、その id を `mutations` の `tests` に **1 件だけ**書く (§1.5 の 40。`mutate.py` は最初の失敗で止まる)。
- 変異ファイルは `$SP/r80-mutations.json` に置き、形は R-79 §2.3 に倣う。**本件は `tools/` だけを触るので peer をまたぐ変異は無い。**

### 2.4 道具の引数

`$SP` (自分の scratchpad) を export しておく。`pt.py` / `mutate.py` は **`-C .`** (自分の worktree) を渡す (**渡し忘れると main を測る**)。

```bash
tools/dev/pt.py -C . --wait 300 -- tools/tests/test_perf_baseline.py -q
tools/dev/pt.py -C . --wait 300 -- tools/tests -q
tools/dev/mutate.py "$SP/r80-mutations.json" -C . --wait 300
python3 tools/check_comment_provenance.py --base c589785 tools/perf_baseline.py
python3 tools/change_class.py <触った全パス>
python3 tools/public_value_scan.py <触った全パス>
python3 tools/check_doc_refs.py
```

- **新規テストファイルを足したら `git add -N` してから `tools/tests` を回す** (R-79 の先例。件数 pin は `git ls-files` 経由で追跡前のファイルを見ない)。
- **`tools/perf_baseline.py` は実行しない** (計測は監督。§0)。**ただし `$SP/proto-r80.py` 相当 (`dsa_testpg.suite_lock(exclusive=False)` + `cluster()` の上で `pg_stat_database` の `sessions` / `xact_commit` の差を見る使い捨てのスクリプト) は 1 回走らせ、出力を報告に貼る** (起草時の裁定 4。完了条件ではない)。

## 3. WP-2 — K=1 で実測し、`docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` に記録する (**監督が実施する**)

**目的**: 本件の成果物である実測を取り、逐語で残す。**WP-1 の完了ゲートの後に行う。**

### 3.1 手順

1. **他の pytest と nginx を止める** (§2 の 19)。同一の使い捨て cluster と CPU を共有するので、他 worktree の suite が走っていると値が計測ではなく負荷の記録になる。
2. **計測 (D-3)**: 本 worktree の道具で **K=1** (`--warmup 10 --n 100 --roundtrip`) を取る (起草時の裁定 1。`--roundtrip` を付けないと `ROUNDTRIP` 行は出ない)。見るのは両 peer の **PostgreSQL 経路の plug** (`r2db-api-http` / `r2db-api-socket` / `MitateDB-api-http` / `MitateDB-api-socket`) である。**r2db は `DSA_PERF_POOL_SIZE` 既定 (2) のみ**とする。`(warmup + n) * K` は 110 で、credential ごと毎分 600 件の bound の内に収まる。**所要時間の見積り** (設計レビュー 1 の L-10): PostgreSQL 経路の plug 4 本 × op 3〜4 × **pre / post の 2 回** × (最短待ち 12 秒 + α) で、**既定の run より +6〜8 分**かかる。止まったように見えても待つ。
3. **記録**: `PERFRUN` / `PERF` / `POOL` / `PREPARED` / `ROUNDTRIP` 行を**逐語で** §2 に置く。ホスト名・実 DSN・作業機の絶対パスを書かない (§1.9、§2 の 13)。`PERFRUN` の `host=` は既に `<OS/arch>` の形である。
4. **事実** (§3): §1.2 の D-3 の (i)〜(v)。**(iii) は §1.3 の依存表に照らして数える** — 「独立」が連続する長さ − 1 が、その区間で pipeline が節約できる往復の上限である。**(iv) のうち R-81 ぶんは本計測では構造的に 0 である** — harness が idempotency key を送らないからである (§1.3 の (10))。**これを §3 の (iv) に事実として書き、「harness に key を送る op を足すか」は §4 の判断材料 (R-81 の設計の側の問題) に回す** (起草時の裁定 3)。**事実だけを書く。**
5. **統計の遅れを併記する** (§1.3 の (5)): `db=` の行は backend が共有メモリへ出した分の差であり、**出す間隔に下限が在る** (idle の接続では約 10 秒)。この性質を §3 の事実として記し、**文の数 (`conn=` の行、probe が直接読む値) と DB の数 (`db=` の行) の食い違いが出たらそのまま記す。`stale=1` の行が在れば、その行を確定値として扱わない。**
6. **判断** (§4): **監督が書く。** pipeline 化の候補と期待値、R-81 / R-82 との重なりと着手順。**着手順の変更は依頼者裁定**なので両論で提示する (§1.5 の (U-1))。**この節は WP-1 では空欄である。**

### 3.2 設計メモの骨 (本書と同じ変更セットで起草済み。WP-2 が埋める)

| 節 | 内容 | 埋める者 |
|---|---|---|
| §0 | 版数 (v0.1) と位置づけ | 起草 (済) / WP-2 (版数を上げる) |
| §1 | 目的と方法 (本書 §1.1 の問題設定、F1〜F5 の要約と本書への参照、道具と引数、K の並び、r2db の pool の寸法は既定 (2) のみである旨、probe の分を除く旨、統計の遅れ、合成環境である旨) | 起草 (済) / WP-2 (確定) |
| §2 | 実測 (`PERFRUN` / `PERF` / `POOL` / `PREPARED` / `ROUNDTRIP` の逐語。K=1 の小見出しだけが在る) | **WP-2 (監督)** |
| §3 | 事実 (§3.1 の 4 の (i)〜(v)) | **WP-2 (監督)** |
| §4 | 判断 (pipeline 化の候補と期待値、R-81 / R-82 との重なりと着手順) | **WP-2 (監督)。WP-1 では見出しと空欄だけ** |

### 3.3 完了条件 (監督が自ら照合する)

1. K=1 の `PERFRUN` / `PERF` / `POOL` / `PREPARED` / `ROUNDTRIP` 行が §2 に**逐語で**在り、`--warmup` / `--n` / `--roundtrip` と r2db の pool の寸法 (既定 2) が併記されている。どの run も `LIMIT_EXCEEDED` で欠けていない。
2. **空振り禁止の実証 (§2.2 の 17、起草時の裁定 4、設計レビュー 1 の H-2)**: **`db=app` の行で `xacts ≥ requests`** が観測されている。**`sessions` は (i) MitateDB の `db=platform` で `≥ 1`、(ii) `db=app` では 0 が期待値であり、0 は空振りではない** (監査の同期書き込みは本計測の op では走らない。§1.3 の (10b))。**`stale=1` の行はこの判定に使わない** (確定していないため。使わざるを得ないときは §6.1 に訂正註として残す)。
3. §3 が事実だけで書かれており、判断語 (「〜すべき」「〜が原因である」) を含まない。
4. §3 の (iii) が §1.3 の依存表の行と 1 対 1 で対応している (依存表の読解が実測と食い違ったら、**依存表を直さず** §3 に食い違いとして記す)。
5. §4 が監督の判断として書かれ、**着手順の変更を要する結論なら依頼者裁定に上げる** (§1.5 の (U-1))。
6. 台帳 `RM` §8 の R-80 行への追記は **WP-2 の完了後**に監督が行う (**行は消さない**)。
7. **完了ゲートに添える性能差分** (`OPERATING_CONDITIONS.md` §1.3 の 27) は、**`--roundtrip` を付けない既定の run** で K=1 / K=3 を取る (設計レビュー 1 の L-9)。`ROUNDTRIP` を取る run は待ちを含むので性能の比較に使わない。

### 3.4 WP-2 修正 (予約。本書では内容を確定しない)

台帳 `RM`:605 の R-80 行は pipeline 化を範囲に含める。**その内容は WP-2 の §4 の判断が決めるので、本書 v1.0 では候補の列挙だけを行い、完了条件・触ってよいパス・変異は書かない** (§1.1 の (a))。候補は §1.5 の (U-1) と同じ 4 つである。

- **(A)** 依存の無い文の連続 (`SET LOCAL` ×2 + catalog 読み) を `pipeline()` にまとめる。**条件**: SI-11 と SI-14 の結果を変えないこと、`_fetch_pipeline` の暗黙 sync (§1.3 の (4)) で節約が消えない形にすること。
- **(B)** `SET LOCAL` 2 文を `SELECT set_config(...), set_config(...)` の 1 文にする。**条件**: 宣言 `execution_ms` の実効上限の意味 (SI-08 / R-87 の確定文) を変えないこと。
- **(C)** MitateDB の catalog 読みの独立 transaction を 1 transaction にまとめる。**条件**: R-82 との重なりの扱いを先に決めること。
- **(D)** 何もしない (R-81 / R-82 の後に再計測する)。

**WP-1 と WP-2 では (A)・(B)・(C)・(D) のいずれにも寄せない。** §1.3 の依存表も、判断ではなく事実として扱う。

## 4. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **(4-1) pipeline 化そのもの。** 両 peer の `src` に `pipeline()` を入れる変更は本書の WP に含まれない (§3.4)。
- **(4-2) 監査 sink の接続の使い回し。** F1 の形 (r2db は sink 自前の pool、MitateDB は呼びごとの接続) を変える判断は計測の後である (§1.4 の (4))。
- **(4-3) `RM`:606 の R-81 (idempotency の往復) と `RM`:607 の R-82 (スキーマ情報のキャッシュ) の実装。** いずれも別件であり、着手順は台帳で固定されている (`RM`:605-607)。
- **(4-4) 台帳 `RM` の R-80 行の追記・引き継ぎ書。** **統合時に監督が行う** (§3.3 の 5)。
- **(4-5) 認証面の接続の計測。** R-79 §4 の (4-6) と同じ理由で範囲外である (1 呼びで閉じる接続。ただし **`sessions` の行には現れる** ので、§3 の事実として記す — D-3 の (ii))。
- **(4-6) 寸法の変更。** pool の `maxconn`、`ResourceLimits.concurrency`、role の `CONNECTION LIMIT`、`DSA_PERF_POOL_SIZE` の既定を 1 つも変えない。

## 5. レビューと受け入れ

- **設計レビュー 1 回** (本書 §1 に対して、WP-1 の着手前)。観点: 守る条件 (a)〜(e) が D-1〜D-6 で満たされているか、**§1.3 の実測と枠の食い違い** (とくに (2) の行番号のずれ、(5) の統計の遅れ、(8) の `db=` の解決、(10) の idempotency が通らないこと、(11) の実 PG の先例が無いこと)、依存表の読解の妥当性、完了条件と変異の対応の穴、`ROUNDTRIP` 行が既存の行を 1 文字も動かさないこと。
- **コードレビュー 1 回** (実装担当とは別の起動)。観点: (i) 両 peer の `src`・`tests`・`conformance` の差分が 0 行であること、(ii) probe が op ごとに 1 回に保たれていること、(iii) 新規テストの空振り (§1.5 の 32) と代理指標 (§1.5 の 52) — とくに完了条件 4・5・9 が**値の差**で観測されていること、(iv) poll が実時間に依存せずテストできる形であること、(v) `PERF` / `POOL` / `PREPARED` / `PREPSTMT` 行の書式が不変であること、(vi) 管理接続が harness 自身のものであり plug の接続を使っていないこと、(vii) レビュー担当自身の変異 1〜2 件 (報告に無いもの。ただし完了ゲートと並行させないこと)。
- **受け入れ監査は省略する** (起草時の裁定 9)。台帳の規模は **M** で変更クラスは **B** であり、`OPERATING_CONDITIONS.md` §1.13 の 74 の表は「M の監査担当は Class C / D のときだけ」と定める。本件は両 peer の `src` を 1 行も触らない。
- **完了ゲートと計測は監督**が行う (`tools/dev/gate.py -C .`、計測は §3.1)。監督が集計行と §2.2 を照合して判定する。受理したら **WP-2 (§3)** に進む。

## 6. 記録 (統合時に監督が埋める。§1〜§5 の本文は書き換えない)

### 6.1 訂正註と監督裁定

**起草時の裁定 (監督、2026-09-23。起草段階なので §1〜§5 の本文に直接反映した)**:

1. **統計の flush**: D-1 の poll を「`pg_stat_clear_snapshot()` の後 1 秒ごとに読み、3 回連続で値が動かなければ確定、上限 15 秒」に改め、**`ROUNDTRIP` 行は `--roundtrip` を付けたときだけ**出す (通常の run の所要時間を変えない)。上限に達した行には **`stale=1`** を付ける。根拠は §1.3 の (5) の実測 (+2 → 10.03 秒後に +101)。§1.1 の F5・§1.2 の D-1・§2.1・§2.2 の 2・11・19・21・22・§2.3 の M11・M16・M17・§3.1 の 2・5・§3.3 の 1 に反映した。
2. **計測の限界**: `BEGIN` / `COMMIT` / `SAVEPOINT` / `RELEASE` は `execute_count` に入らず、**savepoint は `pg_stat_database` にも現れない**。これを設計メモ §1 の「計測の限界」に明記し、§1.3 の依存表で savepoint を使う行に **【SP】** の印を付けた。**`src` に counter は足さない** (§1.4 の (2) のまま)。§1.2 の D-1 の「計測の限界」にも置いた。
3. **R-81 ぶんが構造的に 0** (harness が idempotency key を送らない。§1.3 の (10)) は **§3 の (iv) の事実**として書き、「harness に key を送る op を足すか」は **§4 の判断材料** (R-81 の設計の側) に回す。§3.1 の 4 に反映した。
4. **実 PostgreSQL のテストは `tools/tests` に置かない** (先例が無い。§1.3 の (11))。**完了条件 17 を監督の監査照合に置き換えた** — WP-2 の `ROUNDTRIP` 行で application DB の **`xacts ≥ requests`** かつ **`sessions ≥ 1`** が観測されること (空振り禁止の実証。§3.3 の 2)。実装担当は `$SP/proto-r80.py` 相当を使い捨て cluster で **1 回**走らせ、出力を報告に貼る (完了条件ではない。§2.4)。
5. **`db=` は 2 形で解決する** (r2db は cell の `_runtime_dsn`、MitateDB は backend の `_runtime.info.dbname`)。**`cross_entity` が作る 2 つ目の application DB は `db=app` に入らない** — 計測の限界として設計メモ §1 に明記する。**§1.5 の (U-2) はこれで確定した** (行は消さない。`OPERATING_CONDITIONS.md` §1.8 の 56)。§1.2 の D-2・§2.2 の 12 に反映した。
6. **(設計レビュー 1 の M-3 で全 op に一般化した。行は消さない)** **基準の probe は「その plug の最初の op の計測に入る直前」**とする (adapter の構築直後では r2db の pool がまだ無く、provisioning と seed の文が最初の op の差に混ざる)。§1.2 の D-1 (i)・§2.2 の 5 に反映した。
7. **再接続 (label の変化) のときは基準を 0** とし、**行の並びは `POOL` → `PREPARED` (+`PREPSTMT`) → `ROUNDTRIP`**、**`_emit_prepared_rows` が `prepared_stats()` の戻り値を返す形**にして **probe を op ごとに 1 回**に保つ。§1.2 の D-1・§2.1・§2.2 の 3・5・13 に反映した。
8. **F2 / F3 の `file:line` は現物 (基点 `c589785`) に合わせる** (枠の行番号は R-79 WP-3 の後にずれている。§1.3 の (2))。**F1 の補足** (r2db の監査 sink は自前の pool、MitateDB は呼びごとの接続、`sessions` の見え方が peer で違う) を **§1.1 に足した**。
9. **受け入れ監査は省略する** (Class B・規模 M。`OPERATING_CONDITIONS.md` §1.13 の 74 の表)。§5 は**設計レビュー 1 回・コードレビュー 1 回・完了ゲート (監督)** とした。

**設計レビュー 1 の裁定 (監督、2026-09-23。生出力は `$SP/review-r80-design.md`。起草段階なので §1〜§5 の本文に直接反映した)**:

- **H-1 (「値が動かないこと」を「確定」と読み替えている)**: 全面採用。D-1 (ii) を「**probe の後に読む** (probe がその接続の pending を flush する) / **最短 12 秒**待ってから 1 秒ごとに 3 回連続不動で確定 / **上限 30 秒** (超えたら `stale=1`)」に改めた。レビュー担当の実測を **§1.3 の (5b)** と**逐語 C** に載せた (run 1 = +5 が 20 秒不動で誤確定、run 3 = probe の直後に +102)。完了条件 11 に「**最短待ちより前に確定しない**」を足し、**M11 を「最短待ちの枝を落とす → 赤」**に差し替えた。設計メモ §1 の限界に「**安定 ≠ 確定**」を明記した。
- **H-2 (`db=app` の `sessions ≥ 1` は構造的に 0)**: 採用。**§2.2 の 17** と **§3.3 の 2** を「`db=app` で `xacts ≥ requests`; `sessions` は MitateDB の `db=platform` で `≥ 1`、`db=app` では **0 が期待値** (0 は空振りではない)」に直した。**§1.3 に (10b)** (監査の同期書き込みは本計測の op では 0 回。destructive のときだけ走る) を足し、**D-3 の §3 の (ii) の問い**を直した。
- **M-3 (op 間の setup が次の op の差に混入する)**: **(A) を採用**。各 op の `_measure_op` の**直前 (pre) と直後 (post)** に probe + 統計読みを行い、**差は pre → post** とする。完了条件 3 と M3 を「**op ごと pre 1 + post 1 = 2 回**」に直した。run 時間は `--roundtrip` のときだけ伸びる (L-10 の見積りに反映)。
- **M-4 (補正の本数が label から導けない)**: 採用。**D-1 に導出規則**を書いた — r2db は `label` の `<application_id>` が当該 run の `app_id` に一致する接続だけ、MitateDB は当該 cell の 2 本だけを `db=app` の補正に数え、**`db=platform` の補正は常に 0**。根拠の `file:line` はレビューのとおり (現物で確認した)。完了条件 9 に反映した。
- **M-5 (基準 probe がフラグ制御されていない)**: 採用。**pre の基準 probe も `--roundtrip` のときだけ**とし、完了条件を **21a / 21b** に割って **21b (既定の run では `prepared_stats()` が op ごと 1 回)** と **M18** を足した。README は **`ROUNDTRIP` 節へ追記**し、既存の `POOL` 節 (:144) を書き換えない (§2.1)。
- **M-6 (基準の定義の食い違い)**: 採用。(A) に合わせて **D-1 の (i) と (ii)、完了条件 8 の基準を「当該 op の pre / post」に統一**した。
- **L-7 (件数 pin の文言)**: 採用。完了条件 19 を「**`git add -N` の後に `tools/tests` を回し、:278 の pin が実測と一致することを確認する** (新規ファイルが module 直下で admin DSN env を定義しない限り 31 のまま)」に直した。
- **L-8 (1 完了条件に 2 性質)**: 採用。**5 / 12 / 22 を 2 分割**し (5a・5b / 12a・12b / 22a・22b)、**M19 (5b)・M20 (12b)** を足した。**22 の両半分を 1 対 1 にするため M21 (22a: 常に `stale=1` を出す) も足した** (§1.5 の 33)。
- **L-9 (K=3 を取らない理由)**: 採用。**D-3 に K=1 のみとする理由**を書いた (`docs/work-orders/WORK_ORDER_R79_PREPARED_STATEMENT_MEASUREMENT_V1.md` §6.1 の D-5 の訂正註 = K=3 はこの環境で ±10% に収束しない)。**§3.3 に 7** を足した — 完了ゲートに添える性能差分は **`--roundtrip` 無しの既定の run**で K=1 / K=3 を取る。
- **L-10 (run 時間の見積り)**: 採用。**§3.1 の 2** に「+6〜8 分」の見積りを置いた。
- **観察 (行番号の微差)**: 現物に合わせた — `tools/perf_baseline.py` の `(warmup + n) * concurrency` の**式は :932・:956** (:924・:955 はその註)。`MitateDB-api/src/mitatedb_api/backend_postgres.py` は **:280 が `self._runtime` の代入**であり (§1.3 の (8) の引用はそのまま)、レビューの「:284」は当たらない (起草者が現物で再確認した)。

**WP-1 の実装中の裁定 (監督、2026-09-24)**:

- **完了条件 20 / D-6 (来歴検査) の訂正註**: 来歴検査の対象は `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §3 のとおり両 peer の `src/` だけであり、本 WP は src を触らないので `tools/perf_baseline.py` に出る §4.1 (2) 4 行は対象外である (CH-ID の新規登録は行わない)。条件 20 の文言は「src の差分 0 により自明に充足」と読む。
- **実機で見つかった設計外の不整合**: `_poll_pg_stat_database` は実 DB 名で返し、`_emit_roundtrip_db_rows` は論理名 (`app` / `platform`) で引いていたため、stub の単体テスト (両方に `"app"` を使い回していた) では緑のまま `db=` 行が 1 本も出なかった。実装担当が実機確認で発見し re-key を足し、監督指示で実名 → 論理名の回帰テスト (M22) を追加した。**教訓: stub の名前は実物と同じ形 (異なる 2 つの実名) にする。**
- **コードレビュー 1 の裁定**: (1) 行の `stale` は PRE と POST の poll の論理和 (M23 / M24)、(2) `probed=False` の接続を補正に数えないテスト (M25)、(3) 最短待ち 12.0 / 上限 30.0 の既定値の pin (M26)、(4) README の ROUNDTRIP 節に `POOL lock=` の `acquire` の累積 (op ごとに pre probe 1 回分。実測 20/35/50/69 → 21/37/53/73) を追記、(5) app と platform が同名 DB でも poll が確定するよう `db_names` を一意化 (M27)、(6) `after_measure` の docstring の「順序が少し動く」を「順序は保存されている」に訂正。いずれも採用。
- **受け入れ監査は省略** (Class B・規模 M、`OPERATING_CONDITIONS.md` §1.13 の 74。起草時の裁定 9)。

- **D-5 / §3.3 の 7 (非退行) の訂正註**: 基点 `c589785` の道具と交互に取った既定 run は K=1 が **+0.2〜+7.4%** (判定行 14 本すべて ±10% 内)、K=3 は 3 行が +10.4 / +10.6 / +15.3% (MitateDB-http cross_entity、r2db-socket query / mutate) で残りは ±10% 内 — R-79 §6.1 の訂正註と同じく K=3 はこの環境 (別チャットの並走、load average 3〜4) では ±10% に収束せず、判定は K=1 で行った。本 WP は既定 run の経路を変えていない (probe は op ごと 1 回のまま) ので、差は run 間の散らばりである。

### 6.2 実施と受け入れ

- **WP-1 (実装担当 Sonnet、コードレビュー Opus 1 回 (差し戻し 1)、監督の指示 1 回 (M22))**: `tools/perf_baseline.py` の `--roundtrip`、op ごとの pre/post probe と `pg_stat_database` の poll (最短 12 秒・3 回不動・上限 30 秒・`stale`)、`ROUNDTRIP` の `conn=` 行と `db=` 行、`tools/tests/test_perf_baseline.py` の新規 27 本、`tools/PERF_BASELINE_README.md` の `## ROUNDTRIP lines (R-80)` 節。変異 **M1〜M27 全件 `expect=red got=red`** (M1〜M21 は §2.3、M22 は re-key、M23〜M27 はコードレビュー 1)、レビュー担当の変異 RM1〜RM3 (3 件とも緑 = 差し戻しの根拠)。`tools/tests`: `pt: 638 passed in 63.54s`。実機 (`--warmup 2 --n 5 --roundtrip`): `ROUNDTRIP` 行が 4 つの PG 経路 plug で出て `db=app` 行 28 本が `stale=0`・`xacts ≥ requests`; `--roundtrip` 無しでは 0 行、所要 5.3 秒 (付きは 5:44)。`change_class`: B。`public_value_scan`: 0。両 peer の src / conformance adapter / spec / security / conformance-tests の差分 0。
- **完了ゲート (監督)**: `gate: 4018 passed, 2 subtests passed in 438.42s (0:07:18)` / `judge=PASS` / `pg_database/pg_roles diff 0` (root suite は tools/tests を含まないので R-79 WP-3 と同数)。
- **WP-2 (監督、2026-09-24)**: K=1 `--roundtrip` を設計メモ v0.2 §2 に逐語 (`ROUNDTRIP` 60 行、`stale=1` は 0)、§3 (i)〜(v)、§4 (判断)。要点: r2db は app DB 2 tx + **platform DB 8 tx**/要求、MitateDB は app DB 5 tx (catalog 読み 5 transaction = developer 16 文) + platform 4 tx + **session 2 本/要求 (harness の `pool=None` 配線、production の値ではない)**。独立区間は r2db 5〜8 往復、MitateDB 25 往復 (catalog) だが後者は R-82 が消す。§3.3 の 2 (空振り禁止): `db=app` で `xacts ≥ requests` (220〜1216 ≥ 110)、MitateDB `db=platform` で `sessions` 220 ≥ 1、`db=app` の `sessions` 0。判断: **pipeline 化 (WP-2 修正) は R-82 の後に残る独立区間へ** — 着手順の変更 (R-82 先行) は依頼者裁定に上げる (引き継ぎ書 §4)。台帳 R-80 行は open のまま追記。
