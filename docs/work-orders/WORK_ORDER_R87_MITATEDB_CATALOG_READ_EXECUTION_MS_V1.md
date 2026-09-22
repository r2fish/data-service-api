# 作業指示書 — R-87 MitateDB-api の developer 接続の catalog 読み 8 本の上限を宣言した `execution_ms` に追随させる (`CONTROL_MAPPING` 版 2.23)

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点 main `dd12657`。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の **R-87** 行 (`RM`:512)。worktree は `.claude/worktrees/r87` (branch `r87-mitatedb-catalog-execution-ms`)。
- **変更クラスは D** (実測: WP-1 + WP-2 の代表パスで `class=D`、`conformance_required=true`。`security/` の 2 ファイルが D、`MitateDB-api/src`・`MitateDB-api/tests` が B — 着手時に触った全パスで実測し直す)。台帳の起票文は「Class B 以上 (D の見込み)」で、**実測は D** である。理由は §1.2 の D-0。**契約は 1.8.0 のまま**で `spec/`・`conformance-tests/` の差分は **0**。
- **D が求める依頼者裁定**は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) の下で**監督が下し**、完了後に引き継ぎ書で**事後報告**する (R-88 §0 と同じ書き方)。版付きの security-contract 決定に当たるのは `security/CONTROL_MAPPING.md` の**版 2.23**。
- **設計文書は新しく起こさない。** 枠 (D-0〜D-9 と却下案) は §1 にあり、これが監督の確定した決定である (R-62・R-71 の先例)。**設計レビュー 1 回**を本書に対して行う。方法の正本は `security/CONTROL_MAPPING.md` 冒頭の **Update convention** (:11-:23) と `security/CONTROL_MAPPING_HISTORY.md` 冒頭 (見出しは SI の ID のみ)。先行する形は `docs/work-orders/WORK_ORDER_R62_R2DB_CATALOG_TIMEOUT_V1.md` (r2db-api の同型) と `docs/work-orders/WORK_ORDER_R71_MITATEDB_CATALOG_READ_CANCEL_MAPPING_V1.md` (本件の前段)、`docs/work-orders/WORK_ORDER_R88_CONTROL_MAPPING_POSITION_REFS_V1.md` (履歴の題と位置参照の訂正の形)。
- **WP-1 (コードとテスト) と WP-2 (`security/`) は 1 つのコミットに入れる** — 申告と実挙動は単一コミットである (§1.1 の 11)。したがって**並行 WP は無く**、触るファイルの重なりの表は置かない (§1.2 の 16・17 は該当しない)。**WP-2 の確定文は WP-1 の実測 (テスト名・行範囲・ブロック長・行長) の後に監督が確定する。** §3.2 は確定文の**形**と**埋める穴**だけを与える。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`gate.py`・`finalize.py` は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。**実装担当の裁量は実装詳細のみ** — §1 の決定・§2.1/§3.1 の触ってよいパス・§2.2/§3.3 の完了条件を実装担当が動かさない。

## 1. 枠

### 1.1 問題設定と守るべき条件

`MitateDB-api/src/mitatedb_api/backend_postgres.py` の developer 接続の catalog 読み 8 本 — `schema_count`・`field_domains`・`field_types`・`all_field_types`・`field_constraints`・`field_types_and_constraints`・`all_field_constraints`・`schema_revision` — は取引ごとの `SET LOCAL` (`_set_timeouts`) を通らず、実効の上限は role 水準の `statement_timeout` (`0013_role_statement_timeouts.sql`、5000ms 固定) である。したがって宣言した `execution_ms` (`MITATEDB_MAX_EXECUTION_MS`、`capabilities_document.py`:214) に追随しない。打ち切りは R-71 以後 `limit_class=execution_ms` を名乗る のに、上限は宣言値と違う — `RM` の P-3「宣言は真である」に触れる。

守る条件:

- **(a)** 上限を持つことが**呼び出し側の正しさに依らない**こと (R-62 の (a) と同じ)。
- **(b)** 契約 1.8.0 を動かさないこと (`spec/`・`conformance-tests/` の差分 0)。
- **(c)** 契約の error 語彙の外の結果を作らないこと (写像は R-71 のまま `ResourceLimitError(limit_class="execution_ms")`)。
- **(d)** backend の protocol (`backend.py`) と `backend_sqlite.py` の signature を変えないこと (8 本の直呼びはテストに多数在る)。
- **(e)** C-05 の `hold_in_flight` (cell の `_limit_gate` を止めて `session.catalog()` を保持する) を**跨ぐ期限を作らない**こと (R-62 の設計レビュー 1 R1-2 の裁定と同じ理由)。

### 1.2 決定 (監督確定 2026-09-23。D-0〜D-9)

- **D-0 (変更クラス)** **D** である。`security/CONTROL_MAPPING.md`:683 (SI-08 / MitateDB-api / 既定 / Control。R-71 が足した主張) が「この読みの上限は role 水準の値で、要求ごとの budget では縮まらず、`MITATEDB_MAX_EXECUTION_MS` を 5000 以外にした配備では宣言した `execution_ms` と一致しない (ledger R-87)」と**現在形で開示**しており、直すとこの主張が偽になる。コードと同じ変更セットで現行行を訂正し、旧文を履歴へ移し、版を **2.22 → 2.23** にする。
- **D-1 (上限の出所)** `PostgresBackend.__init__` に keyword 引数 `max_execution_ms: int | None = None` を足す。`None` なら `FoundationConfig` の既定 (§1.3 の (5) の実測により**クラス属性として読める**。読めない実装形に変わっていたら `FoundationConfig()` の値) を使う。値は `self._catalog_timeout_ms` (名前は実装裁量) に持つ。**bare の構築 (テスト・tooling) でも上限が掛かる** — 守る条件 (a) を満たす。r2db の `limits or ResourceLimits()` と同型。
- **D-2 (掛け方)** 8 本それぞれ、developer 接続の cursor を開いた直後・**既存の `try` の内側**・**最初の実文の前に無条件で** `self._set_timeouts(cur, self._catalog_timeout_ms)` を呼ぶ (r2db の `catalog` が無条件で呼ぶのと同型。`if timeout_ms is not None:` のガードは**無い**)。**`try` の内側に置くのは確定である** (設計レビュー 1 R1-4): 外に置くと `SET LOCAL` 自体が上げた例外が R-71 の写像を通らず、合成注入のテストが最初の `SET LOCAL` で発火する形にもならない。`_set_timeouts` は既存のまま (`SET LOCAL statement_timeout` と `lock_timeout` の 2 文) で、この helper 自体を変えない。既存の `except (QueryCanceled, LockNotAvailable)` の枝 (R-71) はそのまま。
  - **対象外の 3 helper** (設計レビュー 1 R1-9): `_field_types_locked` (:438)・`_field_constraints_locked` (:529)・`_field_types_and_constraints_locked` (:574) には**足さない**。いずれも呼び出し元の cursor を共有するうえ、後者は `deadline` 由来の `SET LOCAL` を既に持つ DDL 取引の内側から呼ばれる (:786・:1080) ので、足すと**残り budget を構築時の定数で上書きしてしまう**。
- **D-3 (deadline は通さない)** 8 本の signature に `deadline` を足さない。理由: (i) cell の `catalog`/`schema_revision` は意図して deadline を捕まえない (`cell.py`:1857・:1910、Phase 8 裁定 3)。(ii) C-05 の plug が `catalog()` を止めるので、事前に計算した期限は保持を跨いで間欠的に赤くなる (R-62 の R1-2 の (ii))。gate の内側の helper 経由で呼ばれる 6 本 (insert/read/update 系から `field_domains` 等) にも**残り budget を通さない** — helper の signature 変更が広範であり、`execution_ms` は `reference_wall_clock` 宣言 (`capabilities_document.py`:270) であって、本件の要求は「**宣言した値が上限である**」ことだからである。residual (残り budget) での絞り込みは**限界として開示する** (D-6) し、§4 に申し送る。
- **D-4 (配線)** `main.py`:458 の `PostgresBackend(...)` に `max_execution_ms=config.max_execution_ms` を渡す (`config` は `main.build_app` の局所変数。§1.3 の (4) で実測済み)。他の構築箇所 (`ops` 系・tests・conformance plug) は実装担当が grep し (§1.3 の (6) に基点の一覧が在る)、**本番経路は全て渡す**、**テストの bare 構築は既定のまま**にする。各件について「渡した/渡さない」とその根拠を報告に列挙する。
- **D-5 (テスト)** `MitateDB-api/tests/` に新規 `test_r87_catalog_read_execution_ms.py` を置き、既存 2 ファイルを手直しする。実 PostgreSQL を使い、fixture は `test_postgres.py` の `platform`/`app_a`、`test_application_audit.py` の `timeout_probe_app`/`make_backend` の先例に倣う。
  - **(1)** 8 本を parametrize し、各読みの取引の**中**で `statement_timeout`・`lock_timeout` が構築時の値 (**生 ms**、`pg_settings.setting`。`SHOW` は使わない) であることを観測する。観測は `backend_postgres._execute` をテスト側で包み、**最初の非 `SET LOCAL` 文の直前に同じ cursor で** `pg_settings` を読む形 (R-62 の `_load_catalog` 差し替えと同型)。**8 本全てで観測件数 ≥ 1** を assert する (空振り禁止、§1.5 の 32)。
  - **(2)** 構築時に `max_execution_ms=200` を渡し、role 水準は 5000 のまま、別の admin 接続で `_mdb_field_types` に ACCESS EXCLUSIVE lock を持ち、`all_field_types()` が `ResourceLimitError(limit_class="execution_ms")` になり、**経過が 5 秒より十分短い** (上限が role 値でなく構築値であること) ことを固定する。R-71 の `test_all_field_types_real_postgresql_query_canceled_becomes_resource_limit_error` は role を 200ms に縮める型で、`SET LOCAL` が role 値を上書きするので**この型に書き直す** (role の `ALTER ROLE` は使わない)。
  - **(3)** bare 構築 (`max_execution_ms` を渡さない) で、取引の中の値が **5000** (既定) であること。
  - **(4)** `SET LOCAL` が取引の外へ漏れないこと: 同じ developer 接続で読みの**後**に (取引の外で) `pg_settings` を読むと role 水準の 5000 に戻っている。`test_application_audit.py` の既存テストは呼び出し**前**に読むので、**呼び出し後の観測を 1 件足す**。**既存テストは改名しない** (監督裁定 2026-09-23、設計レビュー 1 R1-12): 観測しているのは**取引の外の値**であり、本件の後も role 水準の値である — 名前は今も事実に合う。ただし docstring の「rather than a per-transaction `SET LOCAL`」は偽になるので、**同じ変更セットで「これは 8 本の取引の外での値であり、取引の中では構築時の値が優越する (完了条件 5 のテスト)」と限定する形に直す**。
  - **(5)** `main.build_app` が `config.max_execution_ms` を渡すこと (`PostgresBackend` を monkeypatch して受け取った kwarg を観測するか、構築された backend の属性を読む)。
  - **書き直すのは `test_all_field_types_real_postgresql_query_canceled_becomes_resource_limit_error` の 1 本だけである** (監督裁定 2026-09-23)。R-71 の他の 2 本 — `test_catalog_read_cancel_synthetic_injection_maps_to_resource_limit_error` と `test_get_catalog_returns_limit_exceeded_not_validation_failed_when_the_read_is_canceled` — はどちらも合成注入で駆動しており role 縮小に依らない (§1.3 の (7))。**触らない。**
  - 完了条件 1 項目 = 変異 1 つ (`expect=red`) の表を §2.3 に置く。
- **D-6 (開示、Class D)** SI-08 / MitateDB-api / 既定 / Control を **2 本の `- ` 主張行に分ける** (監督裁定 2026-09-23。R-62 の設計レビュー 1 R1-10 の先例)。理由は実測である: 基点の `:683` は **1,339 字**で物理行の上限 **1,400** まで残り **61 字**しかなく、1 行に足せない (§1.3 の (14))。ブロックの方は余裕がある — SI-08 / MitateDB-api / 既定は基点 **8,053 字**で上限 15,200 まで残り **7,147 字**、文書の最長ブロックは SI-09 / MitateDB-api / `platform upgrade` の **12,747 字**である (§1.3 の (15))。
  - **(i) `:683` は in place で書き換える** (Update convention。旧文は**逐語**で `CONTROL_MAPPING_HISTORY.md` の `## SI-08` 末尾へ、題は R-88 §3.1 の形)。R-71 が述べた**写像だけ**を述べる短い行にし、「no per-transaction `SET LOCAL` of their own」と「the bound on these reads is the ROLE-level value … differs from the declared `execution_ms` (ledger R-87)」の部分を**落とす**。
  - **(ii) その直後に新しい `- ` 主張行を足す** (**追記なので履歴への移動は無い**): 8 本は取引ごとの `SET LOCAL statement_timeout`/`lock_timeout` を**構築時の `max_execution_ms`** (配備の `MITATEDB_MAX_EXECUTION_MS` = 宣言した `execution_ms` と同じ値) で掛けること、**役割水準の値との関係**、**要求ごとの budget では縮まらない**こと (限界)、証拠のテスト名。
    - **「下敷き」とは書かない** (監督裁定 2026-09-23、設計レビュー 1 R1-2)。事実はこうである: `0013` の role 水準の値は **`SET LOCAL` を持たない developer 接続の文にだけ残り**、8 本の取引の中では**構築時の値が優越する** (`SET LOCAL` が role 既定を上書きする)。
    - **緩む方向も開示する** (同裁定): 宣言値が 5000 を超える配備では、8 本の実効の上限も **5000 を超える** — 本件は上限を宣言値に一致させる変更であって、常に狭める変更ではない。この事実を主張から落とさない。
  - **(iii)** **どちらの行も 1 物理行 1,400 字以内**であることを実測で確かめる。
  - **(iv)** `:676` の `backend_postgres.py:1496-1499` 等の位置参照はコードの変更でずれるので**実測で直す** (in place、旧行は履歴へ)。
  - **(v) `:626` (SI-08 / r2db-api / 既定 / Control の「peer 間の差の開示」) も第 3 の in-place 訂正対象に入れる** (監督裁定 2026-09-23、設計レビュー 1 R1-3)。この行は「MitateDB は role 水準の `statement_timeout` を置き、r2db はそれを置かず取引ごとの `SET LOCAL` に依る」「`lock_timeout` を設定するのは r2db の `SET LOCAL` だけで、MitateDB の role 水準の設定は `statement_timeout` だけ」という**対比**を現在形で述べており、本件で MitateDB 側も取引ごとの `SET LOCAL` (両方の timeout) を持つようになるため、対比の文を**現物に合わせて直す**。旧行は逐語で履歴へ移す。**版 2.23 の版数行には、SI-08 の 2 ブロック (r2db-api と MitateDB-api) に触れた旨を書く。**
  - **確定文は実装とテスト名が決まった後に監督が確定する** (§1.5 の 34・35)。§3.2 は**穴の形**だけを与える。実装担当は版数行 2.23・2 本の主張の案を先例の形で報告に書き、`security/` へは監督の確定文ファイル `$SP/r87-final/` から**逐語複製**する。R-64 のテスト名検査と R-88 の位置参照検査が効くので、引くテスト名・`file:line` は**実在の形**で書く。`tools/check_control_mapping_split.py --base dd12657` の集計行を報告する。
- **D-7 (他の文書の陳腐化)** `MitateDB-api/docs/*.md`・`MitateDB-api/migrations/0013_role_statement_timeouts.sql` のヘッダ・`capabilities_document.py`:255-275 のコメント・`backend_postgres.py` の module 冒頭コメントに「catalog 読みは `SET LOCAL` を通らない / role 水準だけ」と述べる箇所が無いか実装担当が grep し、在れば同じ変更セットで**段落単位で現物照合して**直す (`docs/work-orders/HANDOVER_20260923_FABLE.md` §5 の教訓)。§1.3 の (17) に起草時の実測が在る。監督裁定 2026-09-23:
  - **`MitateDB-api/docs/cloud-run-cloud-sql.md`:2405 は直す** (確定。§1.3 の (17) の ① — 本件の後に偽になる文が在る)。段落単位で現物照合して直す。
  - **残る 3 件** (§1.3 の (17) の ②`0013` のヘッダ・③`capabilities_document.py`:258-270・④`backend_postgres.py`:1474-1480) は、**本変更で偽になる文だけを直し、真のままの文は触らない**。実装担当は 3 件それぞれについて「偽になる文の有無」と `git diff` を報告し、**コードレビューが照合する**。`backend_postgres.py` の CH-ID 付きの塊に当たるなら **D-9 の経路** (R-68) を使う。
- **D-8 (性能)** 増えるのは **catalog 読み 1 本につき `SET LOCAL` 2 文**である (設計レビュー 1 R1-8 の裁定により、以下の数は実測に合わせて確定する): **plain な insert は 4 文**増える (`field_types_and_constraints` と `field_domains` の 2 本を通るため)、**`cell.catalog()` は 4 文**増える (`all_field_types` と `all_field_constraints` の 2 本)。いずれも developer 接続の往復である。`RM` の P-8 (実測前に直さない → 前後で測る) に従い、**監督**が完了ゲートの後に差分を取り、§6 に記す。**実装担当は測らない。**
  - **計測の形** (設計レビュー 1 R1-14): `tools/perf_baseline.py` は**自分の位置から `src` を解く**ので `PYTHONPATH` では worktree に向けられない。したがって**基点 (main `dd12657`) の `tools/perf_baseline.py` と本 worktree の `tools/perf_baseline.py` を、それぞれの木で、同じ `--n` / `--warmup` / `--concurrency` (**K=1 と K=3**) で実行して比べる。**基点の K=1 / K=3 は監督が取得済みである。**
  - 往復をまとめる最適化 (1 文化・pipeline) は本件で行わず、台帳 **R-80** (pipeline mode) の対象として §4 に申し送る。
- **D-9 (コメント)** 変えた関数の docstring は**現在形**で書く (経緯語を入れない)。`backend_postgres.py` の CH-ID 付きの塊を言い換えるなら R-68 の経路を使う。`tools/check_comment_provenance.py --base dd12657 <path>` は「**§4.1 (1) 以外が 0 行**」を合格条件にする (R-71 §4.1 の読み替えと同じ)。`--register` は緑。

### 1.3 起草時の実測 (基点 `dd12657` の現物。起草者が実施)

| # | 観測 | 出所 |
|---|---|---|
| (1) | **8 本の行範囲** (AST 実測): `schema_count` :352-368 / `field_domains` :371-436 / `field_types` :448-482 / `all_field_types` :485-513 / `field_constraints` :541-572 / `field_types_and_constraints` :595-633 / `all_field_constraints` :636-662 / `schema_revision` **:846-860**。`_field_types_locked` :438-445 は `cur` を引数で受ける (呼び出し元の cursor を共有) ので D-2 の対象外。枠が書く `schema_revision` の `:846-859` は AST の `end_lineno` では **860** である | `MitateDB-api/src/mitatedb_api/backend_postgres.py` (`ast` で実測) |
| (2) | **`_set_timeouts` は 8 本から 1 度も呼ばれない。** 定義は `_timeout_ms` :1482-1486 / `_set_timeouts` :1488-1499 で、`src` の呼び出しは **10 箇所** (:689・:922・:1032・:1202・:1386・:1415・:1447・:1515・:1690・:1780)。いずれも `timeout_ms = self._timeout_ms(deadline)` → `if timeout_ms is not None:` の形で、8 本の行範囲には 1 件も無い | 同 :1482-1499、`grep -rn "_set_timeouts" MitateDB-api/src` |
| (3) | **constructor の signature** は `def __init__(self, runtime_dsn, developer_dsn, *, application_id=None)` (:270-329)。既に keyword-only の区切りが在るので D-1 の追加はその並びに入る | 同 :270 |
| (4) | **`main.py` の構築行は :458**、`backend = PostgresBackend(runtime_dsn, developer_dsn, application_id=application_id)`。`config` の変数名は **`config`** (`main.build_app` :236 の中、:419 の `config = FoundationConfig.from_env(...)`。同じ関数の :507・:516・:583 が `config.max_concurrency` 等を読む) | `MitateDB-api/src/mitatedb_api/main.py`:236・:419・:458 |
| (5) | **D-1 の答: `FoundationConfig.max_execution_ms` はクラス属性として読める。** `FoundationConfig` は `@dataclass(frozen=True)` (`config.py`:11-12) で `max_execution_ms: int = 5_000` (:78) を持ち、実測で `FoundationConfig.max_execution_ms` = `5000`、`FoundationConfig().max_execution_ms` = `5000`。環境変数の対応は `"max_execution_ms": "MITATEDB_MAX_EXECUTION_MS"` (:184) | `MitateDB-api/src/mitatedb_api/config.py`:11-12・:78・:184 (実行して確認) |
| (6) | **`PostgresBackend(` の構築箇所は 32 件。** 内訳: `src` **1 件** (`main.py`:458)、conformance plug **1 件** (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:1311、`self._application_config` を並べて渡す形)、`MitateDB-api/tests` **30 件** (9 ファイル)。**`tools/` と `conformance-tests/` は 0 件**、`ops` 系のモジュールにも 0 件。in-process の plug (`conformance_adapter_mitatedb.py`) は `ControlPlane` 経由で `SQLiteBackend` を使い、`PostgresBackend` を構築しない (:598)。**HTTP plug の `_application_config` は共有 profile も `isolated_application_surface` の profile も `max_execution_ms=5000`** (:1883) なので、この 1 件に渡す/渡さないは基点では観測差を生まない。**監督裁定 2026-09-23: この 1 件にも渡す** (plug が宣言する `execution_ms` と上限を一致させる。D-4) | `grep -rn "PostgresBackend(" MitateDB-api tools conformance-tests` |
| (7) | **D-5 の (2)・(6) の答。** R-71 の 3 テストのうち **role 縮小 (`ALTER ROLE ... SET statement_timeout = '200ms'`) で駆動するのは 1 本だけ**である: `test_all_field_types_real_postgresql_query_canceled_becomes_resource_limit_error` (:185-236、`_set_role_statement_timeout` :85-93 を使う) → **D-5 (2) の書き直し対象**。`test_catalog_read_cancel_synthetic_injection_maps_to_resource_limit_error` (:162-182) は `bp_module._execute` の差し替えによる合成注入。**`test_get_catalog_returns_limit_exceeded_not_validation_failed_when_the_read_is_canceled` (:239-256) も `_raise_on_next_execute(psycopg.errors.QueryCanceled(...))` の合成注入で駆動しており、role 縮小に依らない** → この実測により**監督裁定 2026-09-23 で D-5 の (6) を削り、書き直す対象を 1 本に確定した** (§1.2 の D-5) | `MitateDB-api/tests/test_r71_catalog_read_cancel_mapping.py`:85-93・:162・:185・:239 |
| (8) | **D-5 の (4) の対象。** `test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout` は def が **:415**、docstring :417-430、観測 :431-438 (`backend._developer.cursor()` で `pg_settings` を読み `== "5000"` を assert)。読むのは**どの catalog 呼び出しより前**で、取引を開始していない。docstring は `0013` が role 水準の `ALTER ROLE ... SET statement_timeout = '5000ms'` で縛ることを「**rather than** a per-transaction `SET LOCAL` (r2db's own mechanism ...)」と述べており、本件の後は**事実として偽**になる。helper は `timeout_probe_app` :369-380 (module scope、deprovision しない)、`make_backend` :383-384 | `MitateDB-api/tests/test_application_audit.py`:369-384・:411-440 |
| (9) | **同型性 pin の対象外**: `_ISOMORPHIC_TARGETS` (`MitateDB-api/tests/test_audit_query.py`:2179-、件数 pin `len(_ISOMORPHIC_TARGETS) == 143` :3023) に `_set_timeouts`・`_timeout_ms`・`backend_postgres.py` の行は **0 件** (`timeout` を含む 5 行はいずれも `pg_timeouts.py` / `platform_declarations.py` の別の記号) | 同 :2179-2310・:3023 |
| (10) | **行番号 pin は 20 件ある。** `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` (:260-289) が `backend_postgres.py` の行番号を 20 件持つ。うち 9 件 (:365・:425・:477・:507・:567・:628・:656・:837・:857) は 8 本の内側または直後、残り 11 件はそれより下 (最大 :1805)。8 本に 1 行ずつ足し `__init__` にも足すので **20 件すべてが動く**。照合は `test_allowlist_entries_match_real_bare_call_sites` (:607) と `test_backend_layer_allowlist_is_confined_to_backend_modules` (:629)。ファイルは基点で 1,865 行 | 同 :260-289・:607・:629 |
| (11) | **`limit_class` の件数 pin は動かない見込み。** `MitateDB-api/tests/test_limit_class_vocabulary.py`:125 の `len(findings) == 44` は `limit_class` の出現数で、本件は `ResourceLimitError(limit_class=...)` を 1 件も増やさない。実装担当が実測して確かめる | 同 :125・:167 |
| (12) | **`_set_timeouts` の呼びを数えるテストが 1 件ある。** `MitateDB-api/tests/test_threadpool_offload.py` の U-10 probe が `PostgresBackend._set_timeouts` を差し替えて記録し (:615・:634・:702)、`after_release_timeouts` が空でないこと (:716) と `all(t > 1 ...)` (:721) を assert する。B の read 経路は `field_domains` を通る (:604 の `_watched_domains`) ので、本件の後は release 後の記録が**増える**。構築時定数 (既定 5000) は 1 より大きいので**緑のまま**の見込み。docstring :600 の「the one `_set_timeouts` call observed after A's own `release`」は本件の後は事実として不正確になる。**監督裁定 2026-09-23: この docstring を現物に合わせて直す** (文の言い換えではなく**事実の訂正**。§2.1・完了条件 10)。**assert が赤になるなら直さず止めて報告する** — 裁定は監督 (§1.5 の 37) | 同 :580-724 |
| (13) | **守る条件 (e) の現物。** MitateDB の 2 plug の `hold_in_flight` の停止点は cell の `_limit_gate` の差し替え (`_hold_in_flight_via_stalled_gate` :407-441、`hold_in_flight` :1158-1166) で、保持する呼びは `session.catalog()`。`ApplicationCell.catalog` (`cell.py`:1890-1935) は `_limit_gate(principal, None, request_id=...)` を **`as deadline` 無し**で使い (:1910)、`schema_revision` (:1813-1859) も同型 (:1857)。`_limit_gate` が deadline を作るのは :579-580。**isolated profile の `max_execution_ms` は 5000** で本番既定と同値 (`conformance_adapter_mitatedb_http.py`:1883) | `MitateDB-api/conformance/conformance_adapter_mitatedb.py`:407-441・:598・:1158-1166、同 `_http.py`:1311・:1883、`MitateDB-api/src/mitatedb_api/cell.py`:579-580・:1857・:1910 |
| (14) | **`:676` と `:683` の全文と実測長。** `:676` は **361 字**で、`` `backend_postgres.py:1496-1499` `` を引く — 基点ではその 4 行が `_set_timeouts` の本体 (`SET LOCAL` の 2 文の組み立てと `_execute` 2 本) である。`:683` (R-71 の主張) は **1,339 字**で、物理行上限 **1,400** に対し残りは **61 字**しかない。文書の最長物理行は **:651 の 1,384 字**。`:5` (版数行) は 514 字 | `security/CONTROL_MAPPING.md`:5・:676・:683 (実測) |
| (15) | **ブロック長の実測** (register の `_split_sections`/`_iter_section_subblocks`/`_subblock_block_text` を直接呼んだ値): **SI-08 / MitateDB-api / 既定 = 8,053 字** (上限 15,200、残り **7,147**)。同 `ops inventory` 8,335、同 `capacity and concurrency` 7,467、SI-08 / r2db-api / 既定 10,304。**文書の最長ブロックは SI-09 / MitateDB-api / `platform upgrade` の 12,747 字** (残り 2,453) で、preamble の `Length cap measurement` 段 (:26-28、R-72 が 2026-09-23 に再実測した値) と一致する。`## SI-08` の履歴節は `security/CONTROL_MAPPING_HISTORY.md`:137 に始まり :237 の `---` で終わる (:238 が `## SI-09`) | 実測、`security/CONTROL_MAPPING.md`:26-28、`security/CONTROL_MAPPING_HISTORY.md`:137・:237-238 |
| (16) | **位置参照の機械検査は意味のずれを捕まえない。** `conformance-tests/test_control_mapping_register.py`:1635 の `test_control_mapping_md_every_position_reference_resolves_or_is_allowlisted` は「ファイルが在ること + 行番号が範囲内であること」までを見る (`_resolve_position_ref` :1490-1495 の docstring が「行番号は見ない」と明記)。`backend_postgres.py` は 1,865 行あるので、本件で `_set_timeouts` が下へずれても `:1496-1499` は**機械検査を通り続ける** — `:676` の訂正 (D-6) は**監査照合でしか捕まらない** | 同 :1490-1495・:1626-1668 |
| (17) | **D-7 の grep の結果: 候補 4 件、うち偽になることが確実なのは 1 件。** ① `MitateDB-api/docs/cloud-run-cloud-sql.md`:2405 (`0013` の行) が「A revision that lacks it passes its own per-request deadline with `SET LOCAL`, which overrides the role setting; the setting therefore bites only on paths that carry no deadline」「a path that carries no deadline of its own is bounded by the role setting」と述べる — 本件の後、8 本は deadline を持たないまま `SET LOCAL` を発行するので**この 1 文は 8 本について偽になる**。② `MitateDB-api/migrations/0013_role_statement_timeouts.sql` のヘッダ :1-7 が「explicit deadline を持たずに走る文を縛る」と述べる (要判断)。③ `capabilities_document.py`:258-270 が「`_limit_gate` が deadline を計算して `self._backend` に渡し、`backend_postgres.py` がそれを `SET LOCAL` に変換する」と述べる — 8 本は deadline を受けないのでこの文は 8 本を含意しないが、要判断。④ `backend_postgres.py`:1474-1480 (`_set_timeouts` の直前の節のコメント) が「`cell.ApplicationCell._limit_gate` の残り budget から計算した」と述べる — 本件で第 2 の出所が増えるので要判断。**`backend_postgres.py` の module 冒頭 (:1-80) に「catalog 読みは `SET LOCAL` を通らない / role 水準だけ」と述べる箇所は 0 件** (`SET LOCAL` の語が無い) | `grep -rn` (docs / migrations / capabilities_document / module 冒頭) |
| (18) | **変更クラスの実測**: `python3 tools/change_class.py` に WP-1 + WP-2 の代表パスを渡すと `class=D` / `conformance_required=true` (`security/` の 2 ファイルが D、`MitateDB-api/src`・`MitateDB-api/tests` が B)。着手時に**触った全パス**で測り直す | `tools/change_class.py` (実行) |

### 1.4 却下した代替案 (監督確定、蒸し返さない)

- **(1) 8 本に `deadline` を通す** (台帳の候補) — D-3 の理由による: C-05 の保持を跨ぐこと、helper の signature 変更が広範なこと、cell が意図して deadline を捕まえないこと。
- **(2) developer 接続の session 水準 `SET statement_timeout` を接続時に 1 回** — 往復は減るが session 状態に依存し (接続 pooler の下で保証されない)、既存の機構は取引スコープの `SET LOCAL` であり peer (r2db) も同じ形である。
- **(3) DSN の `options=-c statement_timeout=…`** — (2) と同じ session 依存に加え、DSN の `options` の合成が要る。
- **(4) role 水準の `0013` を配備ごとに `MITATEDB_MAX_EXECUTION_MS` に合わせて書き換える運用** — 宣言とコードの一致を運用者に委ねることになり、P-3 に反する。
- **(5) 台帳が言う 2 本 (`all_field_types`/`all_field_constraints`) だけ直す** — R-71 の D-1 と同じ理由で **8 本**を直す。

### 1.5 未確定

- **無し。** Class D の決定は依頼者指示 2026-09-19 の委任の下で監督が下し、事後報告する (§0)。

### 1.6 設計レビュー 1 の反映 (2026-09-23、監督裁定として全件採用。R1-1〜R1-15)

本書はまだ実装に渡っていない (v1.0 の確定前) ので、裁定は**本文へ反映してある** (R-62 §1.7 と同じ扱い。`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 57 が言う「実装に渡った後の訂正註」の場面ではない)。**版は v1.0 のままで、覆した判定の行は無い** (§1.2 の D-0〜D-9 はいずれも撤回ではなく確定・限定である)。

| # | 指摘 | 反映 |
|---|---|---|
| R1-1 (高) | (1a) の落とす対象に `the role-level `statement_timeout` cancels` の句が入っていない — 本件の後、打ち切るのは role 水準の値ではない | §3.2 (1a) の「落とす部分」に 3 つ目として足し、`a statement `statement_timeout`/`lock_timeout` cancels` 相当の**どちらの層が切ったかを名指さない**形に直す旨を書いた。§3.2 の制約の「(1a) は落とす 3 箇所以外を 1 字も変えない」も合わせた |
| R1-2 (高) | 「role 水準の `0013` は下敷きとして残る」は誤り — `SET LOCAL` が取引内で role 既定を上書きするので、8 本では構築値が優越する。宣言値が 5000 超の配備では上限も 5000 超になる (緩む方向) | **裁定: 「下敷き」を改める。** D-6 の (ii) と §3.2 (1b) を書き換え、① role 水準の値は **`SET LOCAL` を持たない developer 文にだけ残る**、② 8 本では**取引ごとの構築値が優越する**、③ **宣言値が 5000 超なら上限も 5000 超になる** (常に狭める変更ではない) の 3 点を**開示に含める**と確定した |
| R1-3 (高) | `:626` (SI-08 / r2db-api / 既定) の peer 差の開示が本件で偽になる — 「取引ごとの `SET LOCAL` に依るのは r2db だけ」「`lock_timeout` を置くのは r2db だけ」が 8 本について成り立たなくなる | **裁定: `:626` を第 3 の in-place 訂正対象に入れる。** D-6 に (v) を足し、§3.2 に **(1c)** を新設 (残る差と消える差を書き分ける / 旧行は逐語で履歴へ / 物理行とブロック長を実測)。§3.2 (3) の移す行を **3 本**に、(4) の版数行を「**SI-08 の 2 ブロック**に触れた」形に、§3.3 の完了条件 1・2・6 と §3.4 の監査照合行を合わせた |
| R1-4 (高) | `_set_timeouts` を `try` の外に置くと、`SET LOCAL` 自体が上げた例外が R-71 の写像を通らない | D-2 に「**既存の `try` の内側**・**最初の実文の前**」を確定として書き、合成注入のテストが**最初の `SET LOCAL` で発火する**形になることを理由として明記。完了条件 2 も同じ文言に揃えた |
| R1-5 (高) | `test_r71_catalog_read_cancel_mapping.py` の module コメント :147-150 (「`LockNotAvailable` は production では発火しない」) が本件で偽になるのに、§2.1 が「helper は変えない」としか書いていない | **裁定: module コメントの事実訂正を §2.1 で許す。** §2.1 の当該行を (a) 完了条件 4 の書き直し / (b) **module コメント :147-150 の事実訂正** / (c) R1-13 の helper 削除 の 3 点に改めた。完了条件 7 を「**テスト本体 (合成注入 15 件と `GET /v1/catalog` の 1 本) は不変、`git diff` はコメント行だけ**」に改めた |
| R1-6 (高) | 構築値に 5000 を使うと role 既定と区別がつかず、テストが空振りする。`lock_timeout` の assert も無い | 完了条件 2 に「**構築値は 5000 と異なる値 (例 `1234`)**」「**`statement_timeout` と `lock_timeout` の両方**を assert」「`lock_timeout` の role 既定は `0` なのでこの 1 件だけでも独立した証拠になる」を足した。完了条件 5 も取引の外で**両方** (`5000` と `0`) を assert する形にした |
| R1-7 (中) | 完了条件 4 のテスト名を実測した例外クラスに合わせると、どちらが先に発火するかが環境で変わったときに名前が嘘になる | **裁定: 例外クラスに依らない中立なテスト名にする** (例 `test_blocked_catalog_read_is_bounded_by_the_constructed_value_not_the_role_value`)。固定するのは `ResourceLimitError`・message・`details`・経過時間だけで、**実測したクラスは報告にのみ**書く。完了条件 4 を書き換えた |
| R1-8 (中) | D-8 の「1 データ操作あたり 2 文」は過少 — plain insert は 2 本の catalog 読みを通る | D-8 を実測の数に直した: **catalog 読み 1 本につき 2 文**、**plain insert で 4 文** (`field_types_and_constraints` + `field_domains`)、**`cell.catalog()` で 4 文** (`all_field_types` + `all_field_constraints`) |
| R1-9 (中) | D-2 が `_field_types_locked` だけを対象外と書くが、同型の helper が他に 2 つ在り、うち 1 つは deadline 由来の `SET LOCAL` を持つ DDL 取引の内側から呼ばれる | D-2 に**対象外の 3 helper** (`_field_types_locked`:438・`_field_constraints_locked`:529・`_field_types_and_constraints_locked`:574) を列挙し、後者が :786・:1080 から呼ばれるため**足すと残り budget を定数で上書きする**ことを理由として書いた。完了条件 2 にも明記 |
| R1-10 (中) | `test_threadpool_offload.py` の訂正を docstring :600 の 1 文に限ると、同じ段の他の文が古いまま残る | §2.1 の許可を **M2 測定段 (:592-604) 全体**の事実訂正に広げ、**「記録に構築時の定数上限による catalog 読みの呼びも混ざる」かを実測して段に書く**ことを求めた (完了条件 10 の (b))。**assert は不変**で、赤になれば止めて報告 |
| R1-11 (小) | `_BACKEND_LAYER_ALLOWLIST` の 20 件を動かすのに、なぜ動いたかの記録が残らない | 完了条件 10 の (a) に、**R-87 の `#:` 段を先例 (R-71 の :243-259) の形で 1 つ足す**ことを足した。**件数 20 と site identity が不変**であること (本件は `_VOCAB_CLASSES` の呼びを 1 件も増やさない) を段に書く |
| R1-12 (小) | `test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout` は改名が要るのではないか | **裁定: 改名しない。** 観測しているのは**取引の外の値**であり、本件の後も role 水準の値なので名前は事実に合う。D-5 の (4) と完了条件 5 に、**docstring で「8 本の取引の外での値であり、取引の中では構築値が優越する」と限定する**形を確定として書いた |
| R1-13 (小) | 完了条件 4 の書き直しで R-71 の `_set_role_statement_timeout`/`_read_role_statement_timeout` が未使用になる | **裁定: 削除する** (死にコードを残さない)。§2.1 の「helper は変えない」を改め、(c) として 2 つの helper の削除を明記した |
| R1-14 (小) | `tools/perf_baseline.py` は自分の位置から `src` を解くので、`PYTHONPATH` では worktree に向けられない | D-8 の計測の形を書き直した: **基点と worktree のそれぞれの `tools/perf_baseline.py` を、それぞれの木で、同じ `--n`/`--warmup`/`--concurrency` (`K=1` と `K=3`) で実行して比べる**。**基点 (main `dd12657`) の K=1 / K=3 は監督が取得済み**である旨を書いた |
| R1-15 (小) | 確定文が `enforced` と読める語を使ったり、「1 要求あたりの上限」と読める書き方をすると偽になる | §3.2 の確定文の制約に 2 行足した: **`enforced` と読める語を使わない** (`reference_wall_clock` 宣言のまま)、**上限は 1 文ごとであり 1 要求ごとではない** (1 操作で最大 2 本の catalog 読みを通す) |

## 2. WP-1 — 8 本に構築時の上限を掛け、配線し、テストで固定する

**目的**: developer 接続の catalog 読み 8 本の実効の上限を、呼び出し側に依らず、**宣言した `execution_ms` と同じ値**にする。

**読むべき正本**: §1.1 (守る条件) / §1.2 (D-0〜D-9) / §1.3 (実測) / §1.4 (却下案)。コード側の手本は同じファイルの `insert` (:1198-1206) と `begin` (:1512-1516) — ただし本件は `deadline` を取らないので `if timeout_ms is not None:` のガードは置かない (D-2)。規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.3〜§1.6・§1.10。

### 2.1 触ってよいパス

- `MitateDB-api/src/mitatedb_api/backend_postgres.py` — `PostgresBackend.__init__` (:270、D-1) と 8 本 (§1.3 の (1)、D-2) だけ。`_timeout_ms`/`_set_timeouts` 自体 (:1482-1499)、`_field_types_locked` (:438-445)、R-71 の例外の枝、8 本の本体の SQL は**変えない**。
- `MitateDB-api/src/mitatedb_api/main.py` — :458 の `PostgresBackend(...)` に kwarg を 1 つ足すだけ (D-4)。
- `MitateDB-api/tests/test_r87_catalog_read_execution_ms.py` — **新規**。D-5 の (1)・(3)・(5)、および (2) の書き直し後の置き場 (どちらのファイルに置くかは実装裁量。R-71 の当該テストを本ファイルへ移すなら、移したこととその理由を報告に書く)。
- `MitateDB-api/tests/test_r71_catalog_read_cancel_mapping.py` — 3 点だけ。(a) **D-5 の (2) の書き直し** (§1.3 の (7) の 1 本)。(b) **module コメント :147-150 の事実訂正** (監督裁定 2026-09-23、設計レビュー 1 R1-5)。現行は「`LockNotAvailable` は migration が `lock_timeout` を宣言しないので production では発火しない」と述べるが、本件の後は 8 本が取引ごとに `SET LOCAL lock_timeout` を置くので**偽になる** — コメント行だけを現物に合わせて直す。(c) **未使用になる helper `_set_role_statement_timeout` (:85-93)・`_read_role_statement_timeout` (:59-83) を削除する** (監督裁定、設計レビュー 1 R1-13。死にコードを残さない)。**合成注入の 15 件と `GET /v1/catalog` の 1 本のテスト本体は 1 行も変えない。**
- `MitateDB-api/tests/test_application_audit.py` — **D-5 の (4) だけ**: 既存テスト (§1.3 の (8)) の docstring の訂正と、呼び出し**後**の観測 1 件の追加。`timeout_probe_app`/`make_backend` ほかの既存 fixture・helper は書き換えない。
- `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` — **確定事項** (§1.3 の (10) の実測により 20 件すべてが必ず動く)。`_BACKEND_LAYER_ALLOWLIST` (:260-289) の**行番号だけ**を実測値へ更新する (§1.5 の 40b)。**allowlist の集合を増減させない。**
- `MitateDB-api/tests/test_threadpool_offload.py` — **U-10 probe の docstring の M2 測定段 (:592-604) 全体の事実訂正** (監督裁定 2026-09-23、設計レビュー 1 R1-10。:600 の「the one `_set_timeouts` call observed after A's own `release`」だけに留めない)。**「記録には構築時の定数上限による catalog 読みの `_set_timeouts` 呼びも混ざる」かどうかを実測し、その結果を段に書く。** **assert とコードは変えない** — 赤になるなら直さず止めて報告する (裁定は監督)。
- `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` — **:1311 の `PostgresBackend(...)` に `max_execution_ms=self._application_config.max_execution_ms` を渡す 1 箇所だけ** (監督裁定。§1.3 の (6))。peer 自身の plug であり、**共通 suite `conformance-tests/` の差分は 0 のまま**。plug の挙動・停止点・profile は変えない。
- `MitateDB-api/docs/cloud-run-cloud-sql.md` — **:2405 の段落だけ** (D-7 の確定分)。段落単位で現物照合して直す。
- D-7 の残る 3 件で**偽になると判定した文**だけ — §1.3 の (17) の ②`MitateDB-api/migrations/0013_role_statement_timeouts.sql` のヘッダ・③`MitateDB-api/src/mitatedb_api/capabilities_document.py`:258-270・④`backend_postgres.py`:1474-1480。**真のままの文は触らない。** 判定と根拠を 3 件それぞれ報告に列挙する。
- `docs/code-history/` — コメントの来歴検査 (`tools/check_comment_provenance.py --register`) が求める記録が要る場合だけ、その 1 箇所。

**これ以外は 0 件。** とくに `spec/`・`conformance-tests/`・`security/` (WP-2 が触る)・`MitateDB-api/migrations`・`MitateDB-api/src` の他のモジュール・`r2db-api/`・`tools/`・`docs/design/` を触らない (変異での一時編集は別。`mutate.py` が復元する)。**既存の検査が新しいコードで赤になったら直さず報告する** (§1.5 の 37) — ただし §1.3 の (10) の行番号 pin は §1.5 の 40b により実測更新する。

### 2.2 完了条件 (16 件)

| # | 完了条件 |
|---|---|
| 1 | **(D-1)** `PostgresBackend.__init__` が keyword 引数 `max_execution_ms: int \| None = None` を受け、`None` のとき `FoundationConfig` の既定 (実測 5000、§1.3 の (5)) を使う。属性名は実装裁量。既存の `runtime_dsn`/`developer_dsn`/`application_id` の受け方を変えない。**監査照合** (完了条件 3・6 の変異が実効を押さえる) |
| 2 | **(D-2 + D-5 (1)、設計レビュー 1 R1-4・R1-6)** 8 本それぞれが、developer 接続の cursor を開いた直後・**既存の `try` の内側**・**最初の実文の前に無条件で** `self._set_timeouts(cur, <構築時の値>)` を呼ぶ (`if ... is not None:` のガードを置かない)。3 helper (`_field_types_locked`・`_field_constraints_locked`・`_field_types_and_constraints_locked`) には**足していない** (D-2)。**実 PostgreSQL のテスト**が 8 本を parametrize し、`backend_postgres._execute` をテスト側で包んで**最初の非 `SET LOCAL` 文の直前に同じ cursor で** `pg_settings.setting` の**生 ms** を読み、**`statement_timeout` と `lock_timeout` の両方**が構築時の値と一致することを assert する (`SHOW` は使わない。発行 SQL 文字列の照合や `_set_timeouts` の直呼びで代替しない。§1.5 の 52)。**構築値は role 水準の 5000 と異なる値 (例 `1234`) を使う** — 5000 では role 既定と区別がつかない。**`lock_timeout` は role 既定が `0` なので、この 1 件だけでも「取引ごとの設定が効いている」ことの独立した証拠になる。** **8 本すべてで観測件数 ≥ 1** を assert する (§1.5 の 32) |
| 3 | **(D-5 (3))** bare 構築 (`max_execution_ms` を渡さない) でも同じ経路で上限が掛かり、取引の中の値が **5000** (`FoundationConfig` の既定から導いた値) である。「0 でない」等の代理指標にしない (§1.5 の 52) |
| 4 | **(D-5 (2))** 構築時に `max_execution_ms=200` を渡し、**role 水準は 5000 のまま**、別の admin 接続が `_mdb_field_types` に ACCESS EXCLUSIVE lock を持つとき、`all_field_types()` が `ResourceLimitError`(`limit_class == "execution_ms"`、メッセージは既存と同じ) になり、**経過が 5 秒より十分短い**。R-71 の `test_all_field_types_real_postgresql_query_canceled_becomes_resource_limit_error` を**この型に書き直す** (`ALTER ROLE` を使わない)。**テスト名は例外クラスに依らない中立な形にする** (監督裁定 2026-09-23、設計レビュー 1 R1-7。例 `test_blocked_catalog_read_is_bounded_by_the_constructed_value_not_the_role_value`) — `lock_timeout` と `statement_timeout` のどちらが先に発火するかは環境で変わりうるからである。**固定するのは `ResourceLimitError` であること・message・`details`・経過時間だけ**で、実際に上がったクラスは**報告にのみ**書く (テストで assert しない)。rollback 後に同じ接続の次の呼びが通ることは R-71 の既存の assert のまま残す |
| 5 | **(D-5 (4)、設計レビュー 1 R1-6・R1-12)** `SET LOCAL` が取引の外へ漏れない: 同じ developer 接続で 8 本のいずれかを呼んだ**後**に、取引の外で `pg_settings.setting` を読むと **`statement_timeout` は role 水準の 5000、`lock_timeout` は role 既定の `0`** に戻っている (**両方を assert する**。呼びは構築値 `1234` 等、5000 と異なる値の backend で行う)。`test_application_audit.py` の既存テスト (§1.3 の (8)) に**呼び出し後の観測を 1 件**足す。**このテストは改名しない** (観測は取引の外の値で、今も role 値である)。docstring は「これは 8 本の**取引の外**での値であり、**取引の中では構築時の値が優越する** (完了条件 5 のテスト)」と限定する形に直す (経緯語を入れない。D-9) |
| 6 | **(D-5 (5))** `main.build_app` が構築時に `config.max_execution_ms` を渡す。`PostgresBackend` を monkeypatch して受け取った kwarg を観測するか、構築された backend の属性を読む |
| 7 | **(D-4、監督裁定 2026-09-23) 監査照合**: conformance の HTTP plug `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:1311 に `max_execution_ms=self._application_config.max_execution_ms` を渡し、plug が宣言する `execution_ms` と上限が一致する形にする。**テストは足さない** (基点で値が同じ — §1.3 の (6))。`git diff` がこのファイルで**この 1 箇所だけ**であること、`conformance-tests/` の差分が **0** であることを示す。併せて **(設計レビュー 1 R1-5)**: `test_r71_catalog_read_cancel_mapping.py` の**テスト本体は不変**である — 合成注入の **15 件**と `GET /v1/catalog` の **1 本**に `git diff` が **0 行**。同ファイルで変わるのは **module コメント :147-150 の事実訂正 (コメント行だけ)** と、完了条件 4 の書き直し 1 本、R1-13 で削除する未使用 helper 2 つだけであることを `git diff` で示す |
| 8 | **(D-4) 監査照合**: 他の構築箇所を grep し (§1.3 の (6) に基点の一覧が在る)、**本番経路は全て渡し** (`main.py`:458 = 完了条件 6、conformance HTTP plug :1311 = 完了条件 7 — どちらも監督裁定で渡すと確定)、**テストの bare 構築は既定のまま**にする。各件について「渡した / 渡さない」とその根拠を報告に列挙する。`grep -rn "PostgresBackend(" MitateDB-api tools conformance-tests` の出力を逐語で残す |
| 9 | **(守る条件 (b)(c)(d)) 監査照合**: 8 本の signature に `deadline` を足していない (D-3)。`MitateDB-api/src/mitatedb_api/backend.py` の protocol と `backend_sqlite.py` の差分が **0**。`spec/`・`conformance-tests/`・`MitateDB-api/migrations`・`r2db-api/` の差分が **0**。R-71 の例外の枝と `limit_class` の語彙を 1 字も変えていない。`git diff` で示す |
| 10 | **(§1.3 の (10)、§1.5 の 40b、監督裁定 2026-09-23)** `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` の **20 件の行番号**を同じ変更セットで実測更新し、**`test_allowlist_entries_match_real_bare_call_sites` (:607) 相当の両方向照合が緑**である (件数を合わせるだけで済ませない)。**集合を増減させない。** 併せて: (a) **(R1-11)** `_BACKEND_LAYER_ALLOWLIST` の直前に **R-87 の `#:` 段を 1 つ足す** — 先例は R-71 の段 (:243-259) で、同じ形にし、**件数 20 と site identity が不変**であること (本件は `_VOCAB_CLASSES` の呼びを 1 件も増やさない) と、20 件すべてがずれた理由を書く。(b) **(R1-10)** `MitateDB-api/tests/test_threadpool_offload.py` の U-10 probe の docstring の **M2 測定段 (:592-604) 全体**を現物に合わせて訂正し、「記録に構築時の定数上限による catalog 読みの呼びも混ざる」かを**実測して書く** (assert とコードは変えない。**assert が赤になるなら直さず止めて報告する**)。(c) `test_limit_class_vocabulary.py`:125 の件数 pin (§1.3 の (11)) を実測して結果を報告する — 動いていたら直さず報告する (§1.5 の 37) |
| 11 | **(D-7、監督裁定 2026-09-23) 監査照合**: `MitateDB-api/docs/cloud-run-cloud-sql.md`:2405 を**段落単位で現物照合して直す** (確定分)。残る 3 件 (§1.3 の (17) の ②③④) は**本変更で偽になる文だけを直し、真のままの文は触らない**。3 件それぞれについて「偽になる文の有無」と `git diff` を報告に列挙し、**コードレビューが照合する**。`backend_postgres.py` の CH-ID 付きの塊に当たるなら D-9 の経路 (R-68) を使う |
| 12 | **(D-9) 監査照合**: `python3 tools/check_comment_provenance.py --base dd12657 <触った src の 2 パス>` の FAIL 行が **§4.1 (1) だけ**で、(2)・(3)・(5)・§9e・`#:` の行が **0 行**。`--register` が緑。出力を逐語で報告に残す。(2) が出たら**止めて報告する** (R-71 §4.1 の先例と R-89 の修正の後なので、出るかどうかは実測で判断する)。判定を緩めない (§1.5 の 37)。**worktree を cwd にして走らせる** (main checkout を測らない — R-71 §4.1 の教訓) |
| 13 | **監査照合**: `python3 tools/change_class.py <触った全パス>` が `class=D`、`python3 tools/check_doc_refs.py` が 0 dangling、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged |
| 14 | **監査照合**: 報告前に `MitateDB-api/tests -q` を **1 回**、`conformance-tests -q` を **1 回**回して緑 (両 backend の同型性、L1 語彙の AST 走査、行番号 allowlist の pin、`test_control_mapping_register.py` の検査が動くかを見る — 動いたら §1.5 の 40b に従い同じ変更セットで実測更新する)。集計行を逐語で報告に残す (§9 の 10 の「開発中」の段。**完了ゲートは監督**) |
| 15 | §2.3 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み (§1.4 の 29〜31) |
| 16 | §2.3 の対応表に**対応の無い行が無い** |

### 2.3 完了条件 → 変異 (`expect=red`。1 項目 1 テスト)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) |
|---|---|
| 2 | **M1〜M8**: 8 本それぞれから D-2 の無条件の `_set_timeouts` 呼びを 1 本ずつ削る (**1 変異 = 1 メソッド**) → その 1 本の parametrize の 1 件だけを `tests` に置く (`mutate.py` は最初の失敗で止まる) |
| 3 | **M9**: `__init__` の `max_execution_ms is None` のときの既定を `FoundationConfig` の既定でない値 (例 `3_600_000`) に差し替える (明示 `max_execution_ms` の経路は緑のまま) → 完了条件 3 のテストが赤 |
| 4 | **M10**: `all_field_types` の `_set_timeouts` 呼びを削る (role 水準の 5000 だけが残り、経過が 5 秒を超える) → 完了条件 4 の書き直したテストが赤 |
| 5 | **M11**: 8 本のうち 1 本の上限設定を、`SET LOCAL` ではなく session 水準の `SET` (= `LOCAL` 無し) の発行に差し替える (`_set_timeouts` 自体は触らない) → 完了条件 5 の漏れのテストが赤 |
| 6 | **M12**: `main.py`:458 から `max_execution_ms=` の kwarg を落とす → 完了条件 6 のテストが赤 |
| 10 | **M13**: `_BACKEND_LAYER_ALLOWLIST` の更新後の 1 行の行番号を 1 ずらす → `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` が赤 |
| 1・7・8・9・11・12・13・14・15・16 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す) |

- **M1〜M13 が赤にする test id は新規・書き直したテストの名前**なので、実装担当が §2.2 の各行に対応するテストを作り、その id を `mutations` の `tests` に **1 件だけ**書く (§1.5 の 40、`mutate.py` は最初の失敗で止まる)。
- **M11 の註**: 完了条件 5 の観測は「取引の後に既定へ戻っている」ことであり、M11 はその性質だけを壊す (M1〜M8 と違い、当該取引の中では上限が掛かったままになる)。次の取引の値は `"5000"` の直書きではなく、**呼び出しの前に同じ接続で読んだ baseline** と比べる (R-62 §6.1 の訂正註 5 の先例。クラスタ既定値を前提にしない)。
- **M9 の註**: 完了条件 3 のテストは、観測した有効値が **`FoundationConfig` の既定から導いた値**であることを assert する (§1.5 の 52)。
- **M10 の註**: 完了条件 4 の「経過が 5 秒より十分短い」の閾は実装担当が実測して決める (CI の揺れに耐える幅を取り、その幅と根拠を報告に書く)。

### 2.4 道具の引数

`$SP` (自分の scratchpad) を export しておく。`pt.py` / `mutate.py` は main checkout を cwd にして走らせ、`-C` で worktree を指す (**渡し忘れると main を測る**)。

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r87 -- MitateDB-api/tests/test_r87_catalog_read_execution_ms.py MitateDB-api/tests/test_r71_catalog_read_cancel_mapping.py MitateDB-api/tests/test_application_audit.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r87 -- MitateDB-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r87 -- conformance-tests -q
tools/dev/mutate.py "$SP/r87-mutations.json" -C .claude/worktrees/r87 --wait 1800
```

worktree を cwd にして走らせるもの (この worktree に `.venv` は無いので `python3` で走らせる。R-62 §3.5 の先例と同じ):

```bash
python3 tools/check_comment_provenance.py --base dd12657 MitateDB-api/src/mitatedb_api/backend_postgres.py MitateDB-api/src/mitatedb_api/main.py
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- worktree から subprocess を起こすテストが在る場合の `PYTHONPATH` は **`OPERATING_CONDITIONS.md` §2 の 17** に従って明示する (明示しないと main checkout の `src` を測る)。
- **`pytest` の直接実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。`gate.py` は他の pytest と同時に走らせると落ちるので、レビュー担当と同時刻に走らせない (§1.3)。
- 一時ファイルは `$SP` 配下だけに置く。複数手順のシェル処理は `$SP` の bash スクリプト (bash 3.2 互換) にする。報告は `$SP/r87-report.md` に書く。

## 3. WP-2 — `security/CONTROL_MAPPING.md` を版 2.23 に上げ、旧文を履歴へ移す

**目的**: 正本順位 5 の文書が現在形で述べている「この読みの上限は role 水準の値で、宣言した `execution_ms` と一致しない (ledger R-87)」という主張を、WP-1 の実挙動に合わせる。**WP-1 と同じコミットに入る。**

### 3.1 触ってよいパス

- `security/CONTROL_MAPPING.md`
- `security/CONTROL_MAPPING_HISTORY.md`

これ以外は 0 件 (台帳 `RM` の R-87 行の追記、引き継ぎ書、D-8 の性能差分は**統合時に監督が行う**)。

### 3.2 確定文の「形」と埋める穴 (**確定文は監督が WP-1 の実測の後に確定する**)

編集は **(1a) → (1b) → (1c) → (2) → (3) → (4) → (5) の順**で行う。行番号は基点 `dd12657` の現物で、追記で以後の行番号は下へずれるので、対象は行番号ではなく**文の中身**で同定する。

#### (1) SI-08 / **MitateDB-api** / 既定 / Control を 2 本の `- ` 主張行に分ける (監督裁定 2026-09-23)

**なぜ分けるか**: 基点の `:683` は **1,339 字**で物理行の上限 **1,400** まで残り **61 字**しかない (§1.3 の (14))。1 行に足せないので、R-62 の設計レビュー 1 R1-10 の先例に倣って 2 本に分ける。ブロックの方は余裕がある (基点 8,053 字、残り 7,147 字。§1.3 の (15))。

##### (1a) `:683` を in place で書き換える (写像だけを述べる短い行にする)

**形**: `- **<太字の導入>**: …` の既存の形を保つ。**残すのは R-71 の写像の主張だけ** — 8 本の列挙と、role 水準の `statement_timeout` が打ち切った文が他の操作と同じ `LIMIT_EXCEEDED` (`limit_class` = `execution_ms`) に写り `VALIDATION_FAILED` にはならないこと、この peer は `LIMIT_EXCEEDED` の denial を durable audit に残さないこと、R-71 の証拠のテスト名。

**落とす部分** (逐語):

- `with no per-transaction `SET LOCAL` of their own` — 本件で偽になる。
- **`the role-level `statement_timeout` cancels` の句** (監督裁定 2026-09-23、設計レビュー 1 R1-1) — 本件の後、打ち切るのは role 水準の値ではなく**取引ごとの `SET LOCAL`** である。`a statement `statement_timeout`/`lock_timeout` cancels` 相当の、**どちらの層が切ったかを名指さない**形に直す。
- `the bound on these reads is the ROLE-level value (`0013_role_statement_timeouts.sql`, 5000ms), a per-request budget does not narrow it, and on a deployment whose `MITATEDB_MAX_EXECUTION_MS` is not 5000 it differs from the declared `execution_ms` (ledger R-87)` — (1b) の新しい行が置き換える。

**旧 `:683` は逐語で履歴へ移す** ((3))。

##### (1b) その直後に新しい `- ` 主張行を足す (追記。履歴への移動は無い)

述べること (D-6 の (ii)):

- 8 本は取引ごとの `SET LOCAL statement_timeout`/`lock_timeout` を、**構築時の `max_execution_ms`** — 配備の `MITATEDB_MAX_EXECUTION_MS`、すなわち**宣言した `execution_ms` と同じ値** — で掛ける (`_set_timeouts`、〈穴 A〉)。
- **role 水準の値との関係** (設計レビュー 1 R1-2。「下敷き」とは書かない): `0013_role_statement_timeouts.sql` の role 水準の `statement_timeout` (5000ms) は **`SET LOCAL` を持たない developer 接続の文にだけ残り**、この 8 本の取引の中では**構築時の値が優越する**。
- **要求ごとの budget では縮まらない** (限界。残り budget は 8 本へ渡らない — D-3 の帰結)。
- **宣言値が 5000 を超える配備では、8 本の実効の上限も 5000 を超える** (同裁定) — 本件は上限を宣言値に**一致させる**変更であって、常に狭める変更ではない。
- 証拠のテスト名 〈穴 C・D・E〉。

**埋める穴**:

| 穴 | 埋めるもの | 出どころ |
|---|---|---|
| A | `_set_timeouts` の**新しい**行範囲 (基点 `:1488-1499`) | WP-1 後の実測 |
| B | 8 本の**新しい**行範囲 (基点は §1.3 の (1)) — 現行の `:683` が個々の行を引いていないので、足すかどうかは行長の実測しだい | WP-1 後の実測 |
| C | WP-1 の完了条件 2・3・6・7 を固定する `MitateDB-api/tests/test_r87_catalog_read_execution_ms.py::<テスト名>` (先例どおり `::` 区切りで列挙し、実在を確かめる) | WP-1 の新規テスト名 |
| D | WP-1 の完了条件 4 で**書き直した**実 PostgreSQL のテスト名 (置き場が移ったなら移動先の path) | WP-1 の実測 |
| E | WP-1 の完了条件 5 の `MitateDB-api/tests/test_application_audit.py::<テスト名>` (漏れないこと / role 水準が下敷きに残ること) | WP-1 の実測 |

#### (1c) SI-08 / **r2db-api** / 既定 / Control (`:626`) を in place で書き換える (監督裁定 2026-09-23、設計レビュー 1 R1-3)

`:626` は「MitateDB-api は `0013` で application の runtime/developer role にも role 水準の `statement_timeout` を置き、r2db-api はそれを置かず取引ごとの `SET LOCAL` (`_set_timeouts`) に依る」「`statement_timeout` と `lock_timeout` の**両方**を置くのは r2db 側の `SET LOCAL` だけで、MitateDB の role 水準の設定は `statement_timeout` だけ」「MitateDB では catalog の経路が読む developer 接続が**その role 水準の値を担う**」という**対比**を現在形で述べている。本件で MitateDB 側の 8 本も取引ごとの `SET LOCAL` (両方の timeout) を持つので、**対比の文を現物に合わせて直す。**

- **残る差**と**消える差**を実測して書き分ける — 「role 水準の設定を置くか置かないか」の差は残り、「取引ごとの `SET LOCAL` に依るのは r2db だけ」「`lock_timeout` を置くのは r2db だけ」の部分は**この 8 本については偽になる**。
- 引いているテスト名 `MitateDB-api/tests/test_application_audit.py::test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout` は**改名しない**ので (R1-12)、そのまま残せるかを現物で確かめる。
- **旧 `:626` は逐語で履歴へ移す** ((3))。**これは in place の訂正であって、ブロック間の移動ではない。**
- **物理行 ≤ 1,400 字**を実測で確かめる (基点の `:626` の字数も測って報告する)。SI-08 / r2db-api / 既定のブロックは基点 **10,304 字**、上限まで残り **4,896 字** (§1.3 の (15))。

#### 確定文の制約 ((1a)・(1b)・(1c) のすべてに掛かる)


- **peer 間で client に見える結果の一致を述べない** (R-62 §3.2 の制約を引き継ぐ)。
- **限界を落とさない** — 「要求ごとの budget では縮まらない」は (1b) に**必ず残す** (D-3 の帰結であり、開示すべき限界である)。
- **`0013` が無くなったとは書かない** — role 水準は下敷きとして残る。
- **射程は developer 接続の catalog 読み 8 本に限る** — 「この backend のすべての取引」とは書かない。
- **R-71 の写像の主張を弱めない** — (1a) は落とす 3 箇所 (R1-1 を含む) 以外を 1 字も変えない。
- **`enforced` と読める語を使わない** (設計レビュー 1 R1-15) — `execution_ms` の宣言は `reference_wall_clock` のままであり (`capabilities_document.py`:270)、本件はそれを変えない。
- **上限は 1 文ごとであり 1 要求ごとではない** (同) — `SET LOCAL statement_timeout` は個々の文に掛かる。1 操作が最大 2 本の catalog 読みを通す (`cell.catalog()` は `all_field_types` + `all_field_constraints`、plain insert は `field_types_and_constraints` + `field_domains`) ので、「1 要求の総時間が宣言値で抑えられる」とは書かない。

#### 満たす不変量 (`conformance-tests/test_control_mapping_register.py`)

 1 主張 1 行 / `|` 表なし / **2 本とも物理行 ≤ 1,400 字** (実測で確かめる。D-6 の (iii)) / ブロック ≤ 15,200 字 / 名前付き小ブロックを増やさない / テスト名が解決する / 位置参照が解決する。

#### (2) `:676` の位置参照の訂正

`:676` が引く `` `backend_postgres.py:1496-1499` `` は、本件で `_set_timeouts` が下へずれるため指す先が変わる (§1.3 の (14)・(16): 機械検査は**通り続ける**ので監査照合で見る)。**行の他の部分は 1 字も変えず**、行番号だけを実測値へ直す (R-88 §3.1 の形)。旧行は (3) で履歴へ移す。

#### (3) `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` への追記

`## SI-08` 節の**末尾**に足す。節は :237 の `---` で終わり :238 が `## SI-09` なので、**その既存の `---` に続けて preface 行から始める** (`---` を新しく足さない)。**旧 `:626` (1c の書き換え前)・旧 `:676` (2 の訂正前)・旧 `:683` (1a の書き換え前) の 3 本**を現物から切り出してそのまま移し、再入力しない。**(1b) で足す行は追記なので履歴へは移さない。** 3 本とも `## SI-08` 節へ入る (`:626` は r2db-api の Control 主張なので題の主語がそちらになる)。 題は R-88 §3.1 の形:

```
*MitateDB-api Control claim, 〈この主張の呼び名〉, superseded 2026-09-〈日〉 (Version 2.23, R-87 -- 〈覆した根拠〉), verbatim:*

<ここに旧行をそのまま 1 行で置く>

---
```

#### (4) 新しい Version 行 (`:5` を置き換える。**1 物理行のまま**にする)

**形** (R-72 の `:5` と同じ組み立て。1 物理行):

```
Version: **2.23** (2026-09-〈日〉; R-87 -- 〈**SI-08 の 2 ブロック (r2db-api の既定と MitateDB-api の既定)** の Control 主張を in place で直し、MitateDB-api の既定に主張を 1 本足し、位置参照 1 件も直したこと、**ブロック間の移動は無いこと**〉: 〈何が偽になったので直したか〉. No new invariant or control. The superseded text is in `CONTROL_MAPPING_HISTORY.md` -- docs/design/ROADMAP_POST_PHASE7_V1.md R-87)
```

#### (5) preamble の `Length cap measurement` 段 (:26-28)

**最長ブロックが変わらなければ触らない** (R-88 §3.1 の先例)。基点の最長は SI-09 / MitateDB-api / `platform upgrade` の **12,747 字**で、本件が伸ばすのは SI-08 / MitateDB-api / 既定 (基点 8,053 字) なので、**変わらない見込み**である。実測して判断し、変わっていれば実測値で直す。

### 3.3 完了条件 (9 件)

| # | 完了条件 |
|---|---|
| 1 | §3.2 の (1a)・(1b)・(1c)・(2) の確定文 (**監督が `$SP/r87-final/` に確定したもの**) が `security/CONTROL_MAPPING.md` に**逐語で**入っている: `:683` は写像だけを述べる行に書き換わり、**その直後に (1b) の新しい `- ` 主張行が 1 本**在り、**`:626` (SI-08 / r2db-api / 既定) の peer 差の対比が現物に合っており**、`:676` の位置参照が実測値に直っている。旧 `:626`・旧 `:676`・旧 `:683` は現行の位置から消えている。**ブロック間の移動は 0 である。****(2) の訂正後の行番号が正しい箇所を指していること**を現物 (±10 行) で確かめて報告に貼る (§1.3 の (16): 機械検査は捕まえない) |
| 2 | 旧 `:626`・旧 `:676`・旧 `:683` の **3 本**が §3.2 (3) の形で `## SI-08` 節に**逐語で**移っている ((1b) で足した行は追記なので移さない)。`git show dd12657:security/CONTROL_MAPPING.md` から切り出した各 1 行と履歴の行の完全一致を**機械的に照合**し、出力を報告に残す |
| 3 | Version 行が §3.2 (4) の確定文で **1 物理行**。§3.2 (5) の判断 (preamble の段を触った / 触っていない) を実測値つきで報告する |
| 4 | `conformance-tests/test_control_mapping_register.py` が緑 (軸の形・1 主張 1 行・物理行長・ブロック長・履歴リンク・テスト名の解決・位置参照の解決) |
| 5 | `python3 tools/check_control_mapping_split.py --base dd12657` の集計行を、**まず `--expect` 無しで走らせて逐語で記録**し、予測と一致したら同じ行を `--expect "<その行>"` に渡して終了コード 0 を取る。一致しなければ**止めて報告する**。**予測にあたっての註**: R-62 は 1 本を 2 本に分けたとき `added` が予測の 1 から 2 に動いた (R-62 §6.1 の訂正註 1)。本件も (1a) の書き換え + (1b) の追記なので同種のずれが起こりうる — **実測を正とし、予測との差は報告に書く** |
| 6 | ブロック長・行長の実測を報告する: SI-08 / MitateDB-api / 既定の**訂正前後** (基点 8,053、残り 7,147)、文書の最長ブロック (基点 SI-09 / MitateDB-api / `platform upgrade` の 12,747)、上限までの残り、**書き換えた `:683`・足した (1b) の行・書き換えた `:626`・訂正した `:676` の 4 本**と Version 行の字数 (いずれも 1 物理行、**≤ 1,400**。D-6 の (iii))、文書の最長物理行 (基点 :651 の 1,384)。**SI-08 / r2db-api / 既定のブロックの訂正前後**も測る (基点 10,304、残り 4,896) |
| 7 | **監査照合**: 差分が `security/` の 2 ファイルと WP-1 のパスだけである (`git status --short`)。`spec/`・`conformance-tests/`・`docs/design/`・`r2db-api/`・`MitateDB-api/migrations` に 1 行も作らない |
| 8 | §3.4 の変異が**全件** `expect=red got=red` で、復元が sha256 2 回で照合済み |
| 9 | §3.4 の対応表に**対応の無い行が無い** |

### 3.4 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 4 (1 主張 1 行) | **M14**: (1b) で足した新しい主張行の途中に改行を入れ、後半を `- ` で始まらない物理行にする | **赤**: `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` |
| 4 (物理行長) | **M15**: (1b) で足した新しい主張行を 1 物理行のまま 1,400 字超にする (詰め物は合成文字列だけで、実 DSN・実ホスト名・絶対パスを書かない)。**この変異が本裁定 (2 本に分ける) の根拠そのものを押さえる** | **赤**: `::test_control_mapping_md_lines_do_not_exceed_the_line_length_cap` |
| 4 (ブロック長) | **M16**: (1b) の行の**直後**に `- ` で始まる詰め物の主張を足して SI-08 / MitateDB-api / 既定を上限超にする (各物理行 < 1,400 字、合計で完了条件 6 の残り +1 字以上) | **赤**: `::test_control_mapping_md_blocks_do_not_exceed_the_length_cap` |
| 4 (位置参照) | **M17**: 訂正後の `:676` の行番号を、`backend_postgres.py` の行数を超える範囲に差し替える | **赤**: `::test_control_mapping_md_every_position_reference_resolves_or_is_allowlisted` |
| 4 (履歴リンク) | **M18**: `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` の見出しに題を足す (アンカーが変わる) | **赤**: `::test_every_control_mapping_section_has_a_resolving_history_link` |
| 1・2・3・5・6・7・8・9 | **監査照合** (照合対象は各行の本文のとおり。`git diff`・機械照合の出力・道具の集計行・実測値の表を逐語で報告に残す)。**`:626` の訂正 (1c) も監査照合である** — 対比の文が現物と合っていること、`lock_timeout` の対称性の主張が偽でないこと、旧行が逐語で履歴に在ることをレビューと受け入れ監査が独立に突合する | — |

- **M16 の註**: 詰め物は行長の検査も同時に満たしうるので、`tests` には**ブロック長の 1 件だけ**を置く。新しい本文が測られる側に入っている直接の証拠は完了条件 6 の実測 (訂正前後の差) である。
- **M18 の註**: M18 は**基点でも赤になる**変異であり、本変更セットが足した文言そのものは観測しない — 旧文を置いた節の**履歴リンクの不変量が生きていること**の生存確認である。逐語の照合は完了条件 2 (機械照合) が担う。`::test_control_mapping_history_has_exactly_the_main_sections_ids` も同時に赤になりうるので、`tests` には上の 1 件だけを置く。
- **M17 の註**: §1.3 の (16) のとおりこの検査は「ファイルが在ること + 行番号が範囲内であること」までしか見ない。**訂正後の行番号が正しい箇所を指していること自体は完了条件 1 の監査照合で見る** (機械では捕まらない)。

### 3.5 道具の引数

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r87 -- conformance-tests/test_control_mapping_register.py -q
tools/dev/mutate.py "$SP/r87-cm-mutations.json" -C .claude/worktrees/r87 --wait 1800
```

worktree を cwd にして (`python3`。この worktree に `.venv` は無い):

```bash
python3 tools/check_control_mapping_split.py --base dd12657
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md
```

## 4. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **(4-1) residual budget による絞り込み。** cell の `_limit_gate` が持つ残り budget を 8 本へ通して上限をさらに縮めることは **D-3 で行わない**と決めた。限界として `security/CONTROL_MAPPING.md` に開示する (D-6)。別件として扱うかは監督が台帳で判断する。
- **(4-2) 往復の削減。** `field_domains` はデータ操作のたびに通るので、本件は 1 操作あたり developer 接続の往復を 2 文増やす。1 文化・pipeline での削減は本件で行わず、台帳 **R-80** (pipeline mode) の対象である。
- **(4-3) runtime 接続の直呼びで `deadline=None` のまま上限を持たない操作。** 在るかどうかは本書の射程外で、実装担当が気づいたら**報告だけする** (実装しない)。
- **(4-4) `MitateDB-api/migrations/0013_role_statement_timeouts.sql` 自体の変更。** role 水準の 5000ms は下敷きとして**そのまま残す** (D-6)。migration の差分は 0 (変異での一時編集を除く)。
- **(4-5) 台帳 `RM` の R-87 行の追記・引き継ぎ書・D-8 の性能差分。** いずれも**統合時に監督が行う**。

## 5. レビューと受け入れ

- **設計レビュー 1 回** (本書 §1 に対して、WP-1 の着手前)。観点: 守る条件 (a)〜(e) が D-1〜D-5 で満たされているか、D-3 の帰結 (残り budget を通さない) が開示と一致しているか、§1.3 の実測と枠の食い違い、完了条件と変異の対応の穴。
- **コードレビュー 1 回** (実装担当とは別の起動)。観点: (i) 上限が呼び出し側に依らないこと (bare 構築の経路を含む)、(ii) 新規テストの空振り (§1.5 の 32) と代理指標 (§1.5 の 52)、(iii) 8 本すべてが**無条件で**呼んでいること (ガードの残りが無いこと)、(iv) 行番号 pin の実測、(v) D-7 の段落単位の照合が現物に当たっていること、(vi) C-05 の経路に期限が入っていないこと、(vii) レビュー担当自身の変異 1〜2 件 (報告に無いもの。ただし完了ゲートと並行させないこと — R-62 §6.1 の訂正註 7 の先例)。
- **受け入れ監査 1 回** (レビュー担当とも別の起動)。**Class D の手順が求めるもので省かない** (`RM` §9 の 8)。
- **完了ゲートと性能差分は監督**が行う (`tools/dev/gate.py -C .claude/worktrees/r87`、`tools/perf_baseline.py` を基点と本 worktree で同じ引数。D-8)。監督が集計行と §2.2・§3.3 を照合して判定する。受理したら台帳 `RM` §8 の R-87 行に追記して閉じ (行は消さない)、引き継ぎ書で依頼者へ**事後報告**する (§0)。

## 6. 記録 (統合時に監督が埋める。§1〜§5 の本文は書き換えない)

### 6.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-23)】`MitateDB-api/migrations` の差分 0 (完了条件 9・WP-2 の 7)。** コードレビュー 1 の F4 で `0013_role_statement_timeouts.sql` のヘッダ (`bounds every statement … without an explicit deadline`) が 8 本について偽になると分かり、監督裁定でヘッダに 1 文を足した (SQL 本文は byte 不変、`git diff` は `--` 行のみ)。完了条件 9・7 の「差分 0」は「SQL 本文の差分 0」と読み替える。
- **【訂正註 2 (2026-09-23)】主張行の本数 (§3.2 (1b)、完了条件 1・§3.3 の 3)。** 監督の確定文は (1b) を 1 物理行に収めず **2 本の `- ` 主張行** (`:684`・`:685`) に分けた (物理行 1,400 字の上限。起草時の見込み 1 本を上書き)。版数行はこれに合わせ `two MitateDB-api default-block claims were added` とした (受け入れ監査の指摘で `one` から直した)。
- **【訂正註 3 (2026-09-23)】完了条件 2 の構築値。** 起草時の例示 1234 を **7654** (5000 超) に変えた — `:685` の「宣言値が 5000 超の配備では上限も 5000 超」を直接実測する (受け入れ監査の疑義 (i))。
- **【監督裁定 1】** D-7 ④ (`backend_postgres.py:1496-1503` の execution_ms ヘッダ「residual budget から計算」) は据え置き (Phase 8 helper の由来として真、排他を主張しない)。同ヘッダが引く r2db `postgres.py:1936-1959` の陳腐化は本件外で台帳 R-96 に載せた。D-7 ③ (`capabilities_document.py:258-270`) は偽になる文なし (排他を主張しない)、② `0013` は訂正註 1、① `cloud-run-cloud-sql.md:2405` は段落単位で訂正。
- **【監督裁定 2】** コードレビュー 1 の F1: 完了条件 4 のテストは fixture に `0013` が無い (role 値 0) ため、テスト内で developer role に `statement_timeout='5000ms'` を置き (`finally` で復元)、構築値 200 の下で `elapsed` 0.20s を実測した — 「構築値が role 値に勝つ」の証拠。F7: 取引外の観測は baseline 比較 (クラスタ既定に依らない)。R1-12: テスト名は改名しない。F3: U-10 M2 は `mutate.py` で実測 (`[5000, 1, 5000]`、baseline `[5000, 3952, 5000]`、`log=` は §6.2)。
- **【監督裁定 3】** 受け入れ監査の疑義 (ii) `:685` の `remains in force` は role 水準の PostgreSQL 設定について述べる語で、宣言 class の `enforced` ではない — そのまま。(iii) `:626` が引くテスト名の距離は R1-12 の裁定どおり docstring で限定済み。

### 6.2 実施と受け入れ

- **差分**: `MitateDB-api/src/mitatedb_api/backend_postgres.py` (`PostgresBackend.__init__` に `max_execution_ms` (既定 = `FoundationConfig` の 5000)、8 本の catalog 読みの `try` 内側・最初の実文の前で無条件に `_set_timeouts`)、`main.py` (`config.max_execution_ms` を渡す)、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (plug の `FoundationConfig` の値を渡す)、新規 `MitateDB-api/tests/test_r87_catalog_read_execution_ms.py` (4 テスト、8 本 parametrize を含め node id 11: 取引内の `pg_settings` 生 ms = 7654 (`statement_timeout`・`lock_timeout`)、bare 構築 = 5000、role 5000 の下で構築値 200 が打ち切る (elapsed 0.20s、watchdog thread)、`build_app` の配線)、`test_r71_catalog_read_cancel_mapping.py` (実 QueryCanceled テストを新ファイルへ移動、module コメント訂正、未使用 helper 2 つ削除。合成注入 15 + GET 1 は不変)、`test_application_audit.py` (docstring 限定 + 取引外の baseline 比較 1 件)、`test_threadpool_offload.py` (M2 段の docstring を実測に)、`test_l1_details_vocabulary_ast_scan.py` (`_BACKEND_LAYER_ALLOWLIST` 20 件 +16〜+23、`#:` 段)、`MitateDB-api/migrations/0013_role_statement_timeouts.sql` (ヘッダ 1 文)、`MitateDB-api/docs/cloud-run-cloud-sql.md:2405` (段落)、`security/CONTROL_MAPPING.md` (版 2.23: `:626`・`:676`・`:683` in place、`:684`・`:685` 追記)、`security/CONTROL_MAPPING_HISTORY.md` (旧 3 行を `## SI-08` へ逐語)。`tools/change_class.py` → `class=D`。
- **道具の出力行**: `pt: 112 passed` (r87/r71/application_audit/threadpool)、`pt: 1432 passed, 2 subtests passed in 137.32s` (`MitateDB-api/tests`)、`pt: 58 passed` (`conformance-tests/test_control_mapping_register.py`)。`mutate: 14 mutations, 14 as expected` (M1〜M14、7654 の木で再実行、mutate ログ 2026-09-23 08:48:25)、`mutate: 5 mutations, 5 as expected` (§3.4 M14〜M18、`security/`)。U-10 baseline は pt ログ 2026-09-23 08:48:02 (`[5000, 3952, 5000]`)。`tools/check_control_mapping_split.py --base dd12657 --expect "missing=3 added=5 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` 終了 0。来歴 `--base dd12657` は §4.1 (1) の 2 行のみ、`--register` OK 87/430。`check_doc_refs` 0、`public_value_scan` 0。ブロック長: SI-08 r2db 既定 10,440、MitateDB 既定 9,327 (上限 15,200)、最長物理行 `:651` 1,384 不変。
- **性能 (D-8、監督実測 `$SP/r87-perf-delta.md`)**: `tools/perf_baseline.py --warmup 10 --n 100` を基点 (main dd12657) と本 worktree のそれぞれの道具で K=1/K=3。`backend_calls` は catalog 読み 1 本につき +2 文 (query 13→21、mutate 9→13、batch 29→49、cross_entity 14→22)。p50 の差は ±6% 以内 (K=1 は全 op で僅かに速く、K=3 の batch が +0.9ms) でノイズ域。往復数の増分は台帳 R-80 (pipeline) の対象。in-process plug (SQLite) は対象外。
- **設計レビュー 1** (高 6・中 4・小 5、全件反映。§1.6)、**コードレビュー 1** (高 1・中 3・小 3 → 差し戻し 1 `$SP/r87-return-1.md`、F5 据え置き以外反映)、**受け入れ監査 1** (未充足 3 → 差し戻し 2 `$SP/r87-return-2.md`: WP-2 の変異 5 件を実行、版数行の件数、7654; conformance 全体の緑は完了ゲートが供給)。
- **完了ゲート** (監督単独、最終の木、`--label r87b`): `gate: 3909 passed, 2 subtests passed in 322.41s (0:05:22)`、`judge=PASS`、実行クラスタ差分 0 (直前の main 3899 + 10 = 新規 11 node id − 移動元 1)。
- **最終判定**: 受け入れ。Class D の決定 (8 本の上限を構築時の `max_execution_ms` に、`CONTROL_MAPPING` 2.23 の 3 主張行の訂正と 2 主張行の追記) は 2026-09-19 の委任の下で監督が下し、引き継ぎ書で依頼者へ事後報告する。台帳 R-87 を閉じる (v1.99)。
