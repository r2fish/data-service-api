# 作業指示書 — R-66 配備 script が `0013` を流さない件と、provision 役の役水準 timeout の判断

## 0. 版数・位置づけ

- **v1.1 (2026-09-22)。** v1.0 からの変更は設計レビュー 1 (高 5・中 8・低 6、全件採用) への監督裁定の反映だけで、裁定の逐語は §1・§2・§3・§5a の該当箇所に置いた。基点 main `980068c`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-66。変更クラスは **Class D** (`security/CONTROL_MAPPING.md` に主張を足し、`r2db-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` の集合が増える。契約 `spec/` は触らない)。D が求める依頼者裁定は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) の下で監督が下し、事後確認を引き継ぎ書で伺う。版付きの security-contract 決定は `security/CONTROL_MAPPING.md` の版 (番号は WP-3 で監督が確定する)。
- 設計文書は起こさず、決定は本書 §1 に置く (R-62・R-64・R-71 の先例)。設計レビュー 1 回を本書に対して行う。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit・完了ゲート・`finalize.py` は監督のみ、道具は `tools/dev/`、下請け Agent は起動しない)。
- worktree は `.claude/worktrees/r66` (branch `r66-control-roles`)。**WP-1 と WP-2 は同じ script を触るので直列**に行う (WP-1 → WP-2)。WP-3 は監督の確定文ファイルを待つ。
- 実装担当の裁量は実装詳細のみ。本書に無い検査・機構・引数は実装前に報告し、監督裁定を得る (§1.5 の 37)。

## 1. 問題と決定 (監督確定)

### 1.1 問題 A — 配備 script が `0013_role_connection_limits.sql` を流さない

`r2db-api/deploy/scripts/part1_provision_host_and_db.sh` の Step 3 が流す migration は `0001` (`:300`) → `0002` (`:319`) → `0005` (`:332`) → `0006` (`:339`) → `0007` (`:346`) → `0014` (`:357-360`) → `0008` (`:395-406`) → `0012` (`:420-423`) → `0003` (`:425-433`) で、`0013` はどこからも呼ばれない。Step 3 のコメント (`:293-297`) は理由を「`0014` と違い `0013` には自分自身の前提条件 (`max_connections` の再確認) があり、この script はそれを検証しない」とする。

台帳 (`ROADMAP_POST_PHASE7_V1.md`:478) は「取りこぼし」と書くが、帰結はそれより重い。`0013` 抜きの初期 `CONNECTION LIMIT` は api 10 (`r2db-api/migrations/0005_credential_store.sql:113`)、controlplane 10 (`0006_control_plane_http.sql:457`)、runtime 20 / developer 10 (`0002_provisioning_functions.sql:117`,`:121`) で、F-16 (`check_role_connection_limits`、`r2db-api/src/r2db_api/platform_declarations.py:1020`) が既定 `concurrency` 32 (`r2db-api/src/r2db_api/limits.py:17`) で課す床 64 / 16 / 32 / 32 を全て下回る。この F-16 は `ops verify-declarations` だけでなく**両 process の起動時 fail-fast** に組み込まれている (data-plane: `r2db-api/src/r2db_api/main.py:471`、control-plane: `r2db-api/src/r2db_api/control_main.py:581`)。したがって **この script だけで配備した新規ホストでは、既定 `concurrency` のまま `0013` を手で流さない限り data-plane も control-plane も起動できない** (コード読解による。実 PostgreSQL での確認は WP-1 の完了条件 5 で取る)。

runbook `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §5 の `0013` の行 (`:421-423`) は「additive only、`0002`/`0005`/`0006`/`0007` があればいつでも安全」とだけ書き、同じ段落の `0008` (`:418-419`)・`0012` (`:419-421`) にある「REFUSES TO START」の開示が無い (陳腐化)。`max_connections` の検査は両 peer とも全て手動で、SQL 内の自動検査は 0 件、F-16 も `max_connections` を見ない (runbook `:375-376` が「independently of `max_connections`」と明記)。script の migration 一覧・順序を pin するテストは無く、CI の `deploy-assets-lint` (`.github/workflows/ci.yml:535-547`) は `bash -n` / shellcheck 等の構文・資産検査に留まる。MitateDB-api に配備 script は無い。

### 1.2 問題 B — 両 peer の control / provision 役に役水準の `statement_timeout` が無い

`r2dbsvc_control` (`r2db-api/migrations/0001_bootstrap_control_plane.sql:96`) と `mitatedbsvc_provision` (`MitateDB-api/migrations/0001_bootstrap_platform.sql:134`) には `ALTER ROLE ... SET` が 1 件も無い。**出所は 2 役で別である** (設計レビュー 1 の低 4):

- `r2dbsvc_control`: 見落としではなく Q4 の明示の設計判断 (`docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md:933` (LQ4-6): provisioning 役は長時間の DDL を流すので `statement_timeout` を置くと migration 自体が途中で止まる)。
- `mitatedbsvc_provision`: 同種の判断を書いた文書は無く、R-56 §10 の 2 の監督裁定 2 (`docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md:243`) が「(MitateDB の provision 役 を含めて) R-56 の範囲外。別に判断する」として本件に送った状態である。

同じ裁定 (同 `:243`、および設計本文 `:86`,`:89-90`) は、この判断を「`ops` が `--lock-timeout` を要求する経路との関係を含めて」行うことを求めている。

MitateDB-api は同じ判断を共有した上で、migration ファイルを流す 3 サブコマンド (`deprovision` / `upgrade-applications` / `apply-platform-migration`) に **既定値なしの必須 `--lock-timeout`** を課している (`MitateDB-api/src/mitatedb_api/ops.py:3068`,`:3161`,`:3191` の `required=True`、値検証 `_LOCK_TIMEOUT_VALUE_RE`:633 / `_validate_lock_timeout_value`:636-646、`PGOPTIONS` への付与 `_with_lock_timeout_option`:740-749、理由 `_inventory_ddl_lock_declaration`:2349-2360)。r2db-api の `ops.py` に `lock_timeout` は 0 件で、唯一の psql 経路 `_run_upgrade_script` (`r2db-api/src/r2db_api/ops.py:1451-1460`) は MitateDB の呼び出し形だけ写して (`:1452` に明記) lock_timeout を写していない。役水準の設定は login 時に session へ複写されるので、役水準に置けば `psql -f` の全 migration が同じ上限を受け、ファイルごとの制御はできない。

### 1.3 守るべき条件

- SI-08 (資源の有界性) の安全上の結果を、client から到達できない運用者経路についても「判断せず放置」ではなく「判断して開示」にする。
- 配備 script は runbook §5 の順序と一致し、次の migration 追加で同じ取りこぼしが起きない (機械検査)。
- `0013` の前提 (`max_connections` の確認) を script が実際に検証する。runbook §4 の算式 (`max_connections >= 実同時接続 + superuser_reserved_connections`、`:358-361`。CONNECTION LIMIT の合計は「導出していない運用者向けの安全側の代用」`:368-372`) と矛盾させない。
- 長時間の DDL を壊さない (`Q4_DB_SIDE_SINGLE_TRUTH_V1.md:933` の理由は生きている)。
- peer 対称: r2db-api に MitateDB と同じ `--lock-timeout` の統制を置く。共有コードは書かず、同名ヘルパは同型性テストに登録する (§1.5 の 38)。

### 1.4 決定

**D-1 (A)。script が `0013` を流す。** 位置は `0007` の直後 (`0013_role_connection_limits.sql:14` の「apply this migration right after `0007`」と runbook §5 に合わせる)、`0014` の前。`0003` より前に流すので、この配備の最初の application は `0013` が置き換える provisioning 関数 (`:181`,`:185` の `CONNECTION LIMIT 36`) から 36/36 を得て、既存 application を回すループ (`:131-132`) は空で通る。Step 3 のコメント (`:276-298`) の順序表と「`0013` は流さない」段落 (`:293-297`) を書き換える (経緯として R-56 が `0014` だけ足した事実は残す)。

**D-2 (A)。`max_connections` の確認を単独 script に置き、part1 から呼ぶ。** (設計レビュー 1 の高 1・高 3・中 1・中 2・中 3・中 7 への監督裁定 2026-09-22)

- **置き場**: 新規 `r2db-api/deploy/scripts/part1a_check_max_connections.sh`。part1 本体からは `part1c_declare_surfaces.sh` の呼び出し (`part1_provision_host_and_db.sh:466-467` の `SCRIPT_DIR` 形式) と同じ様式で呼ぶ。単独 script にするのは pytest が stub `psql` を PATH に置いて直接起動できるようにするためである — part1 本体は `:227` の `sudo useradd`、`:244-249` の `sudo mkdir` / venv 作成を踏むので、テストから Step 3 まで到達する実行は起こせない (基点で deploy script を起動するテストは `r2db-api/tests/`・`conformance-tests/` に 0 件)。
- **位置**: **`0002` の直後、`0005` の前**。control 役と `r2dbsvc_registry.applications` が存在する最初の点であり、`0013` より前という前提を満たす。ここで止まったホストは `0001`/`0002` が冪等なので再実行が安全で、`0005` 以降を適用した中途状態を残さない。
- **接続**: **`R2DBSVC_CONTROL_DSN`** (近傍の既存検査 `:387` と同じ)。`max_connections` も `superuser_reserved_connections` も superuser 限定 GUC ではないので `r2dbsvc_control` で読める。
- **判定**: `SHOW max_connections` と `SHOW superuser_reserved_connections` を読み、`max_connections - superuser_reserved_connections` を必要数と比べ、足りなければ script 既存の `refusing to proceed:` 形式 (`:376`/`:380`/`:391` と同形) で非 0 終了する。
- **必要数の既定**: **`98 + 72 × (N + 1)`**。N は `r2dbsvc_registry.applications` の provisioned 行数 (`runtime_role IS NOT NULL AND developer_role IS NOT NULL`。`0002_provisioning_functions.sql:71-73` は `NOT NULL` で作るが `0006_control_plane_http.sql:76-78` が `DROP NOT NULL` するので、登録済みで未 provision の行を除く述語として必要である (`0013` §2 の loop と同じ形)。表が無ければ 0 — `to_regclass` で判定する)。98 = platform 分 (api 68 + controlplane 20 + control 5 + auditreader 5)、72 = 1 application 分 (runtime 36 + developer 36)。application 1 件なら 170 になり、runbook §4 の CONNECTION LIMIT 表の合計と一致する。`+ 1` はこの実行が provision する application の分で、script が既存 platform DB への再実行を想定している (`:496-510`) 以上、N を数えずに 170 固定にすると 2 つめ以降の application で判定が緩む。
- **運用者の導出値**: `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` (正の整数) が在ればそれを必要数にする。runbook §4 の手順 2 (`:243-245`) が運用者に求める導出結果の受け渡しであり、迂回ではない。**`98 + 72 × (N + 1)` は runbook `:363-366` が定義する conservative stand-in であって PostgreSQL の要求そのものではない**: 1 application の真の需要は §4 の算式で runtime + developer 64 + `2 × platform_pool_size` (既定は `concurrency` と同じ 32、`:277-283`) = 128 に control-plane 16・auditreader 4・運用者の `psql` を足した数 + `superuser_reserved_connections` である。この peer で実際に下げられる knob は `R2DB_PLATFORM_POOL_SIZE` (`:277-283`) だけで、**`ResourceLimits.concurrency` は固定である** (`r2db-api/src/r2db_api/ops.py:1146` が逐語で「`ResourceLimits.concurrency` is fixed on this peer -- no env var overrides it anywhere in this peer's own composition roots」と書く)。値の検証は正の整数のみ。
- **refusal の文**は、読んだ 2 値・使った必要数・N・runbook §4 の節、および **`R2DBSVC_EXPECTED_PEAK_CONNECTIONS`** を名指す (中 7: 正当な進め方が message から分かること)。
- 98 と 72 は script に literal で置き、D-4 (iii) のテストが `0001`/`0007`/`0013` の `CONNECTION LIMIT` から再計算して pin する。

**D-3 (A、文書)。** runbook §5 の `0013` の行 (`:421-423`) に、同じ段落の `0008`/`0012` と同じ形で「既定 `concurrency` では両 process が F-16 で REFUSES TO START (`main.py` / `control_main.py`)」を足す。**同段落の列挙順 (`:412-423`) を script の実行順に合わせる** (設計レビュー 1 の低 1: 基点は `0014`→`0008`→`0012`→`0013` の順で、D-4 (ii) の literal 列と食い違う)。§4 に `part1a_check_max_connections.sh` の判定と `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` を書く。`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` は script の手順を記述しているので (`:640-641`,`:656-670`,`:688-713`)、同じ変数と確認の段を足す。

**D-4 (A、検査)。新規の静的テスト `r2db-api/tests/test_deploy_script_migrations.py`** (実 PostgreSQL 不要。既存の静的テストの型 — `r2db-api/tests/test_platform_upgrade_ledger_scan.py` — に合わせる)。**(i) と (ii) は同一の抽出結果 — script 本文の invocation 行 (`-f` / `\i`) だけを抽出し、コメント行を除いたもの — に対して判定する** (設計レビュー 1 の高 5: Step 3 のコメントは `0004` (`:286`)・`0009` (`:288`,`:293`)・`0013` (`:293-297`) を本文で名指すので、script 全文の grep では (i)(ii) の変異が空振りする):

- (i) `r2db-api/migrations/*.sql` の platform migration が抽出結果に現れることを、**明示の除外集合**を引いて検査する — 除外は `0004` (deprovision = 運用者の teardown) と `0009`/`0010`/`0011` (per-application upgrade script で `ops upgrade-applications` が流す) の 4 本で、それぞれ理由を書く。**除外集合が `platform_upgrades.PLATFORM_UPGRADE_NUMBERS | {4}` と一致することを assert する** (中 8。基点は `frozenset({9, 10, 11})`、`r2db-api/src/r2db_api/platform_upgrades.py:83`)。失敗メッセージには「per-application upgrade は `ops upgrade-applications` が流す (script の `psql -f` に足さない)」を書き、将来の `0015_*_upgrade.sql` で赤が誤読されないようにする。次の platform migration を script に足し忘れると赤になること。
- (ii) 抽出結果の出現順が runbook §5 の順序 (`0001 0002 0005 0006 0007 0013 0014 0008 0012 0003`) と一致する。この literal 列が順序の正本であり、D-3 が runbook §5 の本文をこれに合わせる。
- (iii) D-2 の literal `98` と `72` が、`0013` (`:108` api 68、`:109` controlplane 20、`:131-132`/`:181`,`:185` runtime/developer 36/36)・`0001` (`:96` control 5)・`0007` (`:194` auditreader 5) の `CONNECTION LIMIT` から再計算した値 (98 = 68+20+5+5、72 = 36+36) と一致する。
- (iv) part1 が `part1a_check_max_connections.sh` を呼ぶ行が、`0005` の invocation より前に在る (D-2 の位置)。

除外集合の変更は監督裁定 (§1.5 の 40b)。

**D-5 (A、実 PostgreSQL)。** 完了条件として、`0013` 抜きの state で `check_role_connection_limits` が既定 `concurrency` で FAIL することと、`0013` 適用後に通ることを固定する。既存の F-16 テスト (`r2db-api/tests/test_ops_verify_declarations.py` の F-16 群。基点で `check_role_connection_limits` を直接呼ぶのは `:816` と `:857` の 2 件) が既にこの 2 つを固定しているなら**そのテスト名を引用して足さない**。足りなければ 1 本足す。どちらであるかは実装担当が現物を確認して報告する。

**D-6 (B)。役水準の `statement_timeout` を `r2dbsvc_control` / `mitatedbsvc_provision` に置かない — 判断として確定し、開示する。** 理由: (1) `Q4_DB_SIDE_SINGLE_TRUTH_V1.md:933` のとおり長時間の DDL (`CREATE DATABASE` / `DROP DATABASE` / 非 CONCURRENTLY の `CREATE INDEX` — `r2db-api/migrations/0011_idempotency_records_upgrade.sql:112` が現に持つ / 将来の `ADD CONSTRAINT`) が途中で ERROR になり migration が部分適用で終わる、(2) 役水準の設定は全 psql session に複写されファイルごとの上限にできない、(3) この役は client から到達できず (threat model の境界)、運用者が 1 回ずつ流す。

代わりにこの経路で有界にするのは、呼び出し単位の `lock_timeout` による **lock の取得待ち**である (MitateDB の既存の形)。`lock_timeout` は ACCESS EXCLUSIVE / ACCESS SHARE の要求が待ち行列の先頭に居座って後続の要求まで塞ぐ窓を閉じる。**取得後の保持時間は上の (1) の理由により意図して無界のままである** (`0011_idempotency_records_upgrade.sql:112` の非 CONCURRENTLY な `CREATE INDEX` は、lock を取ってからの実行時間を `lock_timeout` では切れない)。残余リスクの受容根拠は「client から到達できず、運用者が 1 回ずつ流す経路である」ことであり、`lock_timeout` が保持時間まで有界にするからではない (設計レビュー 1 の中 4)。

**D-7 (B、r2db-api)。`ops upgrade-applications` に既定値なしの必須 `--lock-timeout` を足す。** 値検証は MitateDB の `_LOCK_TIMEOUT_VALUE_RE` / `_validate_lock_timeout_value` と同一、`PGOPTIONS` への付与は `_with_lock_timeout_option` と同一 (同名で写し、共有コードは書かず `_ISOMORPHIC_TARGETS` に登録して件数 pin を実測更新する)。`_run_upgrade_script` (`r2db-api/src/r2db_api/ops.py:1451-1460`) が `_psql_connection_env` (`:1361`、呼び出しは `:1459`) の作る env に付与する。`--dry-run` でも必須 (MitateDB と同じ: `MitateDB-api/src/mitatedb_api/ops.py:1891` は dry-run 分岐の前で検証する)。`part1_provision_host_and_db.sh` の `upgrade-applications` 呼び出し (`:513-515`) に `--lock-timeout 2s` を渡す (3.2 の 6)。runbook の `upgrade-applications` の呼び出し形を更新する (`POSTGRES_PROVISIONING_RUNBOOK.md:426`,`:1727`,`:1731`,`:1812`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:100`)。r2db-api には `apply-platform-migration` / `deprovision` サブコマンドが無い (手で `psql -f`) — **サブコマンドの新設は範囲外** (§5a)。代わりに runbook の「稼働中クラスタへ手で流す migration」の手順 (`0004`: `:489`、`0013`、`0014`: `:1949`) に `PGOPTIONS='-c lock_timeout=<value>'` を添える (文書のみ)。

**D-8 (B、MitateDB-api)。コードは触らない。** 既に `--lock-timeout` を 3 サブコマンドで要求している。

**D-9 (開示)。`security/CONTROL_MAPPING.md` の SI-08 に、両 peer の control / provision 役について主張を足す** (追記であり、既存の主張は書き換えない): 役水準の `statement_timeout` を意図して置かないこと (D-6 の理由の要約)、migration ファイルを流す `ops` 経路が呼び出しごとの `--lock-timeout` を必須にすること、根拠のテスト名。**`lock_timeout` の効き方は D-6 の最後の段落の形で書く** — 取得待ちを有界にし、取得後の保持は意図して無界であり、受容根拠は client 到達不能の運用者経路であること (設計レビュー 1 の中 4。裏付けの無い断言を正本に入れない、§1.5 の 34)。r2db-api ブロックは R-65 で分割済みで残り容量が小さいので、ブロック長の上限に当たるなら R-65 の分割の形に従う。**文案は実測 (テスト名) の後に監督が確定する** (§1.5 の 34・35)。実装担当は WP-1・WP-2 の報告に版数行・主張・再実測文の案を先例の形で書き、`security/` は監督の確定文ファイル `$SP/r66-final/` を待って WP-3 で逐語複製する。R-64 の検査が効くので、引くテスト名は裸の形なら当該 peer の `tests` に在る名前、完全形なら実在の path で書く。

### 1.5 却下した代替案

- **(a)** script に `0013` を足さず runbook の手作業のままにする — 起動不能の帰結を隠したまま先送り。
- **(b)** `max_connections` の確認を script で行わず警告だけ出す — 前提の検証を運用者の目に委ねる形は「検証できない条件を許可に変える」に近い。
- **(c)** 環境変数無しで `98 + 72 × (N + 1)` の refusal だけ — この数は runbook `:363-366` が定義する conservative stand-in であって PostgreSQL の要求そのものではない。真の需要を §4 の手順で導出した運用者 (この peer で実在する knob は `R2DB_PLATFORM_POOL_SIZE` のみ。`ResourceLimits.concurrency` は固定、`ops.py:1146`) を script が正当な理由なく止めることになり、制約で回避する形。
- **(d)** provision 役に短い役水準 `statement_timeout` を置き migration ごとに `SET statement_timeout = 0` で解除 — 全 migration ファイルの改修で、解除を忘れた 1 本が本番で壊れる。
- **(e)** r2db-api に `--lock-timeout` を任意引数 (既定あり) で足す — MitateDB との非対称が残り、既定値の根拠が無い。

## 2. WP-1 — script が `0013` を流し、`max_connections` を検証し、順序を機械検査で固定する (D-1〜D-5)

### 2.1 触ってよいパス

- `r2db-api/deploy/scripts/part1_provision_host_and_db.sh`
- `r2db-api/deploy/scripts/part1a_check_max_connections.sh` (新規。D-2)
- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`
- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (script の手順を記述している現物の path)
- `r2db-api/tests/test_deploy_script_migrations.py` (新規)
- `r2db-api/tests/test_deploy_script_max_connections.py` (新規。D-2 の stub `psql` のテスト。D-4 のファイルに同居させてもよい — 実装担当の裁量)
- D-5 でテストを足す場合のみ `r2db-api/tests/test_ops_verify_declarations.py`

### 2.2 完了条件

1. script が `0013_role_connection_limits.sql` を `0007` の後・`0014` の前で流す。呼び出しの形は同じく変数を持たない `0014` の行 (`:357-360`、`-v ON_ERROR_STOP=1 -f`) と同形にする。
2. 新規 `r2db-api/deploy/scripts/part1a_check_max_connections.sh` が D-2 のとおり判定する。`R2DBSVC_CONTROL_DSN` で接続し、`SHOW max_connections` と `SHOW superuser_reserved_connections` を読み、`max_connections - superuser_reserved_connections` が必要数未満なら既存の `refusing to proceed:` 形式で非 0 終了する。必要数の既定は script 内の literal `98` と `72` から `98 + 72 × (N + 1)` で計算し、N は `r2dbsvc_registry.applications` の provisioned 行数 (表が無ければ 0、`to_regclass` で判定)。part1 本体は `0002` の直後・`0005` の前でこの script を `SCRIPT_DIR` 形式で呼び、非 0 なら `0005` 以降を流さない。
3. `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` が正の整数として与えられたときはそれが必要数になり、正の整数でない値 (空文字・0・負・非数字) は同じ refusal 形式で拒否される。refusal の文は読んだ 2 値・使った必要数・N・runbook §4・`R2DBSVC_EXPECTED_PEAK_CONNECTIONS` を名指す。
4. stub `psql` を `PATH` に置いて `part1a_check_max_connections.sh` を**直接起動する** pytest が、(a) 不足時の非 0 終了と refusal 文の内容、(b) 充足時の 0 終了、(c) `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` の不正値の拒否、(d) 正の整数のときそれが既定の必要数を置き換えること、の 4 つを固定する。stub は `SHOW` の 2 値と N を試験ごとに差し替えられる形にする。空振り禁止 (§1.5 の 32): 全ケースで assert が走ること。
5. Step 3 のコメント (`:276-298`) の順序表が新しい実行順と一致し、`0013` を流さない段落 (`:293-297`) が置き換わっている。R-56 が `0014` だけ足した経緯は残っている。
6. D-5 の実 PostgreSQL の固定。既存の F-16 テストが「`0013` 抜きの state で既定 `concurrency` の `check_role_connection_limits` が FAIL する」と「`0013` 適用後に通る」の両方を既に固定しているかを `r2db-api/tests/test_ops_verify_declarations.py` の現物で確認し、**テスト名を引用して報告**する。片方でも無ければ足りない方を 1 本足す。
7. 新規の静的テスト `r2db-api/tests/test_deploy_script_migrations.py` が D-4 の (i)〜(iv) を固定する。(i)(ii) は invocation 行 (`-f` / `\i`) だけを抽出した同一の結果に対して判定し、コメント行を除く。除外集合は `platform_upgrades.PLATFORM_UPGRADE_NUMBERS | {4}` と一致することを assert し、理由と失敗メッセージを D-4 (i) のとおり書く。空振り禁止 (§1.5 の 32): 実 script・実 `migrations/` に対して観測件数が 1 件以上であることを assert する。
8. D-3 の文書。runbook §5 の `0013` の行に REFUSES TO START の開示、**同段落の列挙順を script の実行順に合わせる**、§4 に `part1a_check_max_connections.sh` の判定と `R2DBSVC_EXPECTED_PEAK_CONNECTIONS`、`DEPLOYMENT_RUNBOOK.md` に同じ変数と確認の段。主張は実測の後に書く (§1.5 の 34)。
9. `bash -n` が `part1_provision_host_and_db.sh` と `part1a_check_max_connections.sh` の両方で終了コード 0 (CI の `deploy-assets-lint` と同じ検査、`.github/workflows/ci.yml:535-547`。同 job は `deploy/scripts/*.sh` 全件を見るので新規 script も対象に入る)。shellcheck が使える環境なら shellcheck も回し、出力を報告に添える。
10. `tools/dev/pt.py` で `r2db-api/tests/test_deploy_script_migrations.py`・`r2db-api/tests/test_deploy_script_max_connections.py`・`r2db-api/tests/test_ops_verify_declarations.py` が緑。
11. `tools/check_comment_provenance.py` は `--register` も `--base 980068c` も緑 (本 WP は `src/` を触らないので §4.1 (1) の赤も出ない)。`tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。
12. D-9 のための主張案 (テスト名込み) を報告に書く。`security/` は触らない。
13. 下の対応表に対応の無い行が無い。

### 2.3 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1 | M1: script から `0013` の **invocation 行 (`-f`) だけ**を消す (Step 3 コメント中の `0013` の言及は残す) | D-4 (i) のテストが赤 |
| 1 (位置) | M2: `0013` と `0014` の invocation 行の順を入れ替える | D-4 (ii) のテストが赤 |
| 2 (literal) | M3: `part1a_check_max_connections.sh` の literal `72` を `62` にする | D-4 (iii) のテストが赤 |
| 2 (呼ぶ位置) | M4: part1 の `part1a_check_max_connections.sh` の呼び出し行を `0005` の invocation の後ろへ移す | D-4 (iv) のテストが赤 |
| 4 (a) | M5: `part1a_check_max_connections.sh` が不足時に refusal を出さず 0 で終わる形にする | stub `psql` の不足シナリオのテスト 1 本が赤 |
| 4 (b) | M6: 充足していても常に refusal で非 0 終了する形にする | stub `psql` の充足シナリオのテスト 1 本が赤 |
| 4 (c) | M7: `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` の値検証を外し、任意の文字列をそのまま必要数にする | stub `psql` の不正値のテスト 1 本が赤 |
| 4 (d) | M8: `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` を読まず常に既定の必要数を使う | 環境変数が必要数を置き換えるテスト 1 本が赤 |
| 3 | M9: refusal 文から `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` の名指しを消す | refusal 文の内容を assert するテスト 1 本が赤 |
| 6 | M10: F-16 の床の計算を `concurrency` に依らない定数にする (`r2db-api/src/r2db_api/platform_declarations.py`)。**定数の値と対象テストは実装担当が `r2db-api/tests/test_ops_verify_declarations.py:740` と `:757` を読んで 1 本に決め、報告する** (設計レビュー 1 の低 2。`mutate.py` は 1 変異 = 1 テスト)。**`src/` を変える変異なので、この 1 件だけは実行後に基点との sha256 一致を 2 回確認する** | 決めた 1 本が赤 |
| 7 (除外集合) | M11: 除外集合の literal から `4` を外す | D-4 (i) のテスト (`PLATFORM_UPGRADE_NUMBERS` との一致 assert) が赤 |
| 5・8・9・10・11・12 | 監査照合 (実行したコマンドと集計行、または file:line を報告に逐語で残す) | — |
| 13 | 監査照合 (本表) | — |

### 2.4 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/r66 -- r2db-api/tests/test_deploy_script_migrations.py r2db-api/tests/test_deploy_script_max_connections.py r2db-api/tests/test_ops_verify_declarations.py -q` (前景・同期、Bash timeout 600000。実 PostgreSQL を使う F-16 テストを含む)
- `tools/dev/mutate.py "$SP/r66-wp1-mutations.json" -C .claude/worktrees/r66` (1 変異 = 1 テスト。`mutate.py` は最初の失敗で止まる)
- `bash -n r2db-api/deploy/scripts/part1_provision_host_and_db.sh` と `bash -n r2db-api/deploy/scripts/part1a_check_max_connections.sh`
- `tools/check_comment_provenance.py` の引数は `--help` で確認する。`tools/check_doc_refs.py`・`tools/public_value_scan.py` は引数なし。
- worktree から subprocess を起こすテストの `PYTHONPATH` は `OPERATING_CONDITIONS.md` §2 の 17 に従う。

## 3. WP-2 — `ops upgrade-applications` に必須の `--lock-timeout` を置く (D-7。WP-1 の後に直列で行う)

### 3.1 触ってよいパス

- `r2db-api/src/r2db_api/ops.py`
- `r2db-api/tests/` の該当ファイル — `r2db-api/tests/test_ops_upgrade.py` (`upgrade-applications` の既存 CLI テスト)、`r2db-api/tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` の表と件数 pin)、`r2db-api/tests/test_deploy_script_migrations.py` (WP-1 新設。script の呼び出し形の検査を足す)
- `r2db-api/tests/test_constraints_declaration.py` (`:672`) と `r2db-api/tests/test_application_audit.py` (`:3370`) — `ops.main(["upgrade-applications", …])` を呼ぶ既存のテストで、必須化で argparse の `SystemExit(2)` により赤になる (設計レビュー 1 の高 4。基点の `ops.main(["upgrade-applications", …])` は r2db-api のテストに 22 件、残り 20 件は `test_ops_upgrade.py`)
- `MitateDB-api/tests/test_audit_query.py` — `_ISOMORPHIC_TARGETS` の表と件数 pin だけ (3.2 の 5。MitateDB-api の `src/` は触らない)
- `r2db-api/deploy/scripts/part1_provision_host_and_db.sh` の `upgrade-applications` の行 (`:513-515`) — **WP-1 と同じファイルなので直列**
- `r2db-api/deploy/scripts/part2_enable_units_and_nginx.sh` の FAILED ログの案内文 (`:479`) だけ (3.2 の 7)
- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (呼び出し形と手作業 migration の手順)
- `docs/code-history/` は `tools/check_comment_provenance.py` が登録を求める場合だけ、その 1 箇所

### 3.2 完了条件

1. `upgrade-applications` の `add_parser` (`r2db-api/src/r2db_api/ops.py:1835-1845`) に `--lock-timeout` を `required=True`・既定値なしで足す。**`--lock-timeout` を欠く `upgrade-applications` は argparse の usage error = 終了コード 2 で止まり、`--dry-run` を付けても同じ**。両方をテストで固定する。
2. `_LOCK_TIMEOUT_VALUE_RE`・`_validate_lock_timeout_value`・`_with_lock_timeout_option` を MitateDB の現物 (`MitateDB-api/src/mitatedb_api/ops.py:633`、`:636-646`、`:740-749`) から**同名で**写す。peer 間でコードは共有しない (§1.5 の 38)。docstring と経緯コメントは逐語で移し、指す先が変わる位置参照だけを括弧書きで補う (§1.5 の 40c)。**ただし同型性テストの `_normalize` が落とすのは先頭 docstring だけで、本体はインデント・トークン間空白・数値リテラルまで保存する** (`r2db-api/tests/test_audit_query.py:3352-3398` の (a)〜(d))。したがって **登録する 3 記号は本体を 1 字も変えない**。位置参照の補いは docstring 内に限る (設計レビュー 1 の中 6)。`_LOCK_TIMEOUT_VALUE_RE` 直上の `#:` ブロック (`MitateDB-api/src/mitatedb_api/ops.py:628-632`) は `ast.get_source_segment` の範囲外で同型性テストの対象にならないので、§1.5 の 40c の要求として別途逐語で移す。
3. 値検証が `5000`・`5000ms`・`5s`・`1min` を受け、`0`・`0ms`・負・`1h`・`1d`・非数字を拒否する。拒否は既存の `_die` の固定メッセージで行い、拒否した値そのものを echo しない (R-45 WP-A の規律)。
4. `cmd_upgrade_applications` が値を検証し (MitateDB の `:1891` と同じく dry-run 分岐より前)、`_run_upgrade_script` が `_psql_connection_env(app_dsn)` の作った env の `PGOPTIONS` に `-c lock_timeout=<value>` を**追記**する (DSN 由来の既存 `options` を捨てない)。**これを subprocess の env を捕まえるテストで固定する**: `subprocess.run` を monkeypatch して渡された `env["PGOPTIONS"]` を assert し、既存 `PGOPTIONS` 有り / 無しの 2 件を置く。`_run_upgrade_script` の docstring は登録済みの来歴ブロックである (`r2db-api/src/r2db_api/ops.py:1452-1455` の `History: CH-0326`) ので、`lock_timeout` 引数の追加で署名が変わる分の書き換えは **R-68 の「同一変更セット内の reword」の形**で扱う (設計レビュー 1 の低 5)。
5. `r2db-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` に写したヘルパの行を足し、**逐語の表 (`:2990-3242`) と件数 pin (`:3243`、基点 `140`) の両方を実測で更新する** (§1.5 の 40b。件数を実測値に合わせるだけで済ませず、新しい行が実際に両 peer の現物を解決して走査されることを確認する)。登録は `_validate_lock_timeout_value` と `_with_lock_timeout_option` の 2 行に加え、`_LOCK_TIMEOUT_VALUE_RE` も登録する — 解決器 `_isomorphic_symbol_source` は module 水準の `Assign` (bare `Name` 標的) も照合する (同 `:3271-3276` の逐語)。**MitateDB-api 側の同じ表 (`MitateDB-api/tests/test_audit_query.py`、件数 pin `:3016`) も同じ変更セットで同じ 3 行と件数を更新する** (先例 `bb0caa3`、R-56 の 138 → 140 が両 peer を同時に更新した形。監督裁定 2026-09-22)。
6. script (`:513-515`) の `upgrade-applications` 呼び出しが `--lock-timeout <値>` を渡す。値は **`2s`** (監督裁定 2026-09-22: peer の同等行 `MitateDB-api/docs/cloud-run-cloud-sql.md:2455` と同値。新規ホストの初回配備では待たせる相手が無いので短くてよく、値の根拠は peer との対称)。runbook の `upgrade-applications` の呼び出し形にも同じ値を例示する。`r2db-api/tests/test_deploy_script_migrations.py` に、この呼び出しが `--lock-timeout` を持つことの検査を足す。
7. `r2db-api/deploy/scripts/part2_enable_units_and_nginx.sh:479` の FAILED ログが案内する `python -m r2db_api.ops upgrade-applications` に `--lock-timeout <value>` を添える (設計レビュー 1 の中 5 への監督裁定 2026-09-22: 必須化後はこの案内どおり叩くと exit 2 になる)。**`r2db-api/src/r2db_api/platform_upgrades.py:180` の F-12 案内文 (HTTP 応答に出る唯一の文) は両 peer 共通の既存の欠陥として §5a に起票し、本 WP では触らない** (同裁定)。
8. runbook の呼び出し形を更新する: `POSTGRES_PROVISIONING_RUNBOOK.md:426`・`:1727`・`:1731`・`:1812`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:100`。加えて、手で流す migration の手順 (`0004`: `:489`、`0013`、`0014`: `:1949`) に `PGOPTIONS='-c lock_timeout=<value>'` を添える (文書のみ。サブコマンドは新設しない)。
9. `tools/dev/pt.py` で `r2db-api/tests/test_ops_upgrade.py`・`r2db-api/tests/test_audit_query.py`・`r2db-api/tests/test_deploy_script_migrations.py`・`r2db-api/tests/test_constraints_declaration.py`・`r2db-api/tests/test_application_audit.py` が緑。
10. `tools/check_comment_provenance.py` は **`--register` が緑、`--base 980068c` は §4.1 (1) のほかに正当な赤が無い** (`src/` を変える WP では (1) は構造上必ず赤になる)。`tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。既存の関数に docstring を足さない。足すコメントは最小限で、R-63 の規則で通る形にする。
11. D-9 のための主張案 (テスト名込み) を報告に書く。`security/` は触らない。
12. 下の対応表に対応の無い行が無い。

### 3.3 完了条件 → 変異

v1.0 の M9〜M16 を M12〜M19 に付け替えた (WP-1 の変異が M11 まで増えたため)。設計レビュー 1 の裁定が指す「M10」は本版の **M13**、「M11」は本版の **M14** である。

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1 | M12: `--lock-timeout` を `required=False` + 既定値ありにする | 引数を欠く呼び出しの usage error (exit 2) のテストが赤 (`--dry-run` の 1 件も同じテストファイルで固定する) |
| 2 | M13: 写した `_validate_lock_timeout_value` の**仮引数名を `value` → `raw` に変える** (挙動不変。値検証テストは緑のまま) | 同型性テストが赤 (設計レビュー 1 の高 2: `_normalize` は docstring を落とすので docstring の変更では赤にならない) |
| 3 | M14: `_LOCK_TIMEOUT_VALUE_RE` を `0` を許す形 (`^[0-9]*...`) にする。**`mutate.py` の対象テストは値検証のテスト 1 本に絞る** (同型性テストも赤になるが、`mutate.py` は最初の失敗で止まる。設計レビュー 1 の低 3) | 値検証のテスト 1 本が赤 |
| 3 (メッセージ) | M15: 拒否の `_die` のメッセージに拒否した値を埋め込む | メッセージを assert するテストが赤 |
| 4 (併存) | M16: `_with_lock_timeout_option` が既存 `PGOPTIONS` を捨てて `option` だけを返す形にする | 既存 `PGOPTIONS` 有りの env テストが赤 |
| 4 (付与) | M17: `_run_upgrade_script` から `PGOPTIONS` への付与を外す | subprocess の env を捕まえるテストが赤 |
| 5 | M18: `_ISOMORPHIC_TARGETS` の新しい行を 1 つ消す | 件数 pin のテストが赤 |
| 6 | M19: script の `upgrade-applications` 行から `--lock-timeout` を消す | 完了条件 6 で足した静的検査が赤 |
| 7・8・9・10・11 | 監査照合 (実行したコマンドと集計行、または file:line を報告に逐語で残す) | — |
| 12 | 監査照合 (本表) | — |

### 3.4 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/r66 -- r2db-api/tests/test_ops_upgrade.py r2db-api/tests/test_audit_query.py r2db-api/tests/test_deploy_script_migrations.py r2db-api/tests/test_constraints_declaration.py r2db-api/tests/test_application_audit.py -q` (前景・同期、Bash timeout 600000。後ろの 2 ファイルは設計レビュー 1 の高 4 で足した — 必須化で赤になる呼び出しを持つ)
- `tools/dev/mutate.py "$SP/r66-wp2-mutations.json" -C .claude/worktrees/r66` (1 変異 = 1 テスト)
- `tools/check_comment_provenance.py` の引数は `--help` で確認する (`--base 980068c` と `--register` の両方)。
- 変異の復元は §1.4 の規律に従い、`src/` を変える変異の後は基点との sha256 一致を 2 回確認する。

## 4. WP-3 — `security/CONTROL_MAPPING.md` に確定文を複製する (D-9。監督の確定文の後)

### 4.1 触ってよいパス

- `security/CONTROL_MAPPING.md` のみ

### 4.2 完了条件

1. 監督の確定文ファイル `$SP/r66-final/` の内容を**逐語で複製**する (§1.5 の 35)。言い換えない。要約しない。版数行も確定文どおりに置く。追記であり、既存の主張の書き換え・削除・移動はしない。
2. `conformance-tests/test_control_mapping_register.py` が `tools/dev/pt.py` で緑 (ブロック長・行長・軸の形・テスト名の解決)。引くテスト名は R-64 の検査を通る形 (裸の形なら当該 peer の `tests` に実在する名前、完全形なら実在の path) であること。
3. `tools/check_control_mapping_split.py --base 980068c` を監督の指定する `--expect` 文字列で回し、終了コード 0 (既存主張の欠落・移動が 0 であることの照合。R-71 §4.2 の先例)。
4. `tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。
5. 複製したブロックの字数・ブロック全体の長さ・この peer の最長ブロックを実測して報告する。r2db-api の SI-08 ブロックが上限に当たる場合は複製せず報告し、R-65 の分割の形についての監督裁定を待つ。
6. 下の対応表に対応の無い行が無い。

### 4.3 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 2 | M20: 複製した主張が引くテスト名を実在しない名前に変える | `conformance-tests/test_control_mapping_register.py` が赤 (R-64 の検査) |
| 1 | 監査照合 (確定文ファイルと複製結果の diff が空であることを逐語で記録する) | — |
| 3・4・5 | 監査照合 (実行したコマンドと集計行を報告に逐語で残す) | — |
| 6 | 監査照合 (本表) | — |

### 4.4 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/r66 -- conformance-tests/test_control_mapping_register.py -q`
- `tools/dev/mutate.py "$SP/r66-wp3-mutations.json" -C .claude/worktrees/r66`
- `tools/check_control_mapping_split.py --base 980068c --expect "<監督が指定>"`

## 5. レビューと受け入れ

設計レビュー 1 回 (本書 §1 に対して、WP-1 の着手前。**実施済み 2026-09-22**: 高 5・中 8・低 6 を全件採用して裁定し、v1.1 の本文に反映した — 環境変数の根拠、同型性テストの `_normalize` が docstring を落とす件、確認の段を単独 script に切り出す機構、必須化で赤くなる既存テスト 2 件、invocation 行のみの抽出、application 数 N、refusal の位置と DSN と脱出口、`lock_timeout` の効き方、除外集合のドリフト対策、CH-0326、F-12 案内文。未コミットの起草版への反映なので本文を直した)。コードレビュー 1 回。受け入れ監査 1 回。監督が完了ゲートの集計行・完了条件・監査のパケットを照合して判定する。完了ゲートは監督が単独で実行する (`OPERATING_CONDITIONS.md` §1.3。実装担当・レビュー担当は `gate.py` と `finalize.py` を実行しない)。性能差分は添えない (配備経路と CLI の引数の変更で、要求の処理経路の文は変わらない)。

## 5a. 範囲外 (起票のみ)

- r2db-api に `ops apply-platform-migration` / `ops deprovision` サブコマンド (MitateDB と同形) が無い件。
- `check_role_connection_limits` (F-16) が `max_connections` を見ない件 (両 peer。runbook `:375-376` が「independently of `max_connections`」と明記する設計判断であり欠陥ではないが、起動時の fail-fast が「役の上限は足りるが `max_connections` が足りない」配備を通す)。
- MitateDB-api の配備経路 (`MitateDB-api/docs/cloud-run-cloud-sql.md`) に `0012`/`0014` の `max_connections` 確認の自動化が無い件。
- **F-12 の案内文が `--lock-timeout` を含まない件 (両 peer 共通、既存)** — `r2db-api/src/r2db_api/platform_upgrades.py:180` と MitateDB-api の同名 module の同一文が `Run 'python -m <pkg>.ops upgrade-applications'` を返す。これは本フェーズで唯一 HTTP 応答に出る文であり (同 `:167-176`、SI-10)、MitateDB では既に 3 サブコマンド必須化後もこの文のままなので、r2db を揃えると peer 対称に欠陥も揃う (設計レビュー 1 の中 5 への監督裁定 2026-09-22: 本 WP では触らず起票のみ)。
- `r2db-api/migrations/0005_credential_store.sql:106-107` の「`R2DB_PLATFORM_POOL_SIZE`, default 4」が WP-4e 以後陳腐化している件 (runbook `:277-283` は既定を `concurrency` と書く)。R-21 系の文書陳腐化に合流させる材料 (設計レビュー 1 の低 6)。

- **【追記 2026-09-22】台帳への起票先**: 1 件目 (サブコマンドの欠如。migration ヘッダの手動例が素の `psql` のままである点 = コードレビュー WP-2 の低 7 と、MitateDB-api の `test_ddl_flowing_subcommands_match_the_required_lock_timeout_set` に当たる AST 検査が r2db-api に無い点を含む) = roadmap **R-90**、2・3 件目 (`max_connections`) = **R-91**、F-12 の案内文 = **R-92**、`0005` のヘッダ = **R-93**。

## 6. 記録 (統合時に監督が埋める)

### 6.1 訂正註 2026-09-22 (§1〜§5 の本文は書き換えない)

1. **変異の番号。** コードレビュー WP-1 の差し戻しで WP-1 に 2 件足した変異 (単独 script の実行権 = 手順による監査照合、確認の段が `0002` より後 = 変異) は実装担当の表では M12・M13 で、§3.3 の WP-2 の M12〜M19 と番号が重なる。WP-2 は差し戻しで M12 を M12a / M12b に割り、M20 (CLI の検証を外す)・M21 (検証を dry-run 分岐の後ろへ)・M22 (CLI の値の配線をリテラルに固定) を足した。§4.3 の「M20」は WP-2 の M20 と重なるので、WP-3 の変異は **M23-wp3** として実行した。実測の表は下の 6.3 の log= にある。
2. **`r2db-api/docs/DEPLOYMENT_RUNBOOK.md` は実在しない。** 現物は `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` で、本書は v1.0 から実在の path で書いている (枠の誤り)。
3. **WP-3 は監督が直接行った** (§4 は実装担当が複製する形で書いてある)。確定文 `$SP/r66-final/*.txt` を script で逐語挿入し、受け入れ監査が「確定文 7 行が 1 回ずつ完全一致で出現」を照合した。コードレビュー 1 段が抜けた分、監査が §4.2 の 3 と §4.3 の変異の証拠不足を挙げ、監督が実行して埋めた (6.3)。
4. **WP-3 は追記だけでは済まなかった。** SI-08 / MitateDB-api / 既定 / Control の F-17 の主張が、件数を名前に持つ pin テスト `…_140_rows` を引いており、WP-2 の改名 (`…_143_rows`) で解決しなくなった (R-64 の検査が赤にした)。その場で直し、旧文を `security/CONTROL_MAPPING_HISTORY.md` の SI-08 に逐語で移した (R-64 の先例の形)。

### 6.2 監督裁定

- 設計レビュー 1 (高 5 / 中 8 / 低 6): 全件採用。裁定は v1.1 の本文に反映済み。
- コードレビュー WP-1 (高 2 / 中 6 / 低 3): 全件修正。中 3 は `DEPLOYMENT_RUNBOOK.md` §1 Prerequisites に `0013` を足す。中 5 (runbook §5 の「additive only、手で流しても安全」の復活) は実装担当の修正に入っていなかったので監督が 1 文を戻した。
- コードレビュー WP-2 (高 1 / 中 3 / 低 5): 低 5 を除き全件修正。中 4 は監督が `docs/work-orders/DEPLOY_Q4_20260905.md` に訂正註を足した (当時のコードブロックは書き換えない)。**低 5 (CH-0326 の correction の `old` / `new` の境界) は実装担当の形を採る**: レビューの案は `tools/check_comment_provenance.py --base` を赤にする (pending の訂正は現行ソースに無い部分文字列を `old` に取れない。受け入れ監査が構造上の制約として再確認)。
- 受け入れ監査: (a) stub のテストの `assert "7" in stderr` は refusal 文の literal `72` に一致して空振りする → 監督が `"superuser_reserved_connections (7)"` に締めた。(b) 2.20 の peer 間の差の主張に「初回配備では script が platform migration を `lock_timeout` 無しで流す (待たせる相手が無い)」の 1 句を足した (確定文ファイルと `security/` の両方。字数を再実測)。(c) `part2_enable_units_and_nginx.sh` の案内文を pin するテストは足さない (案内文は F-12 の文の写しで、R-92 で両 peer の文と併せて扱う)。
- Class D の決定 (§1 の D-1〜D-9、上の裁定、`security/CONTROL_MAPPING.md` 2.20 の確定文) は依頼者指示 2026-09-19 の委任の下で監督が下した。事後確認は引き継ぎ書 `docs/work-orders/HANDOVER_20260922_FABLE.md` §4 で伺う。

### 6.3 実施と受け入れ

- WP-1: 対象 `pt: 50 passed`、変異 13 件が `expect=red got=red`、`bash -n` / shellcheck 緑。WP-2: 対象 `pt: 256 passed` と MitateDB-api の `test_audit_query.py` `pt: 62 passed`、変異 12 件が赤、`_ISOMORPHIC_TARGETS` は両 peer 140 → 143。`check_comment_provenance.py --register` 緑、`--base 980068c r2db-api/src/r2db_api/ops.py` は §4.1 (1) の 1 行だけ (監督が worktree を cwd にして再実行)。
- WP-3: `conformance-tests/test_control_mapping_register.py` と stub のテストで `pt: 51 passed`。`tools/check_control_mapping_split.py --base 980068c --expect "missing=1 added=8 moved=0 empty_axis_added=0 empty_axis_removed=1 subsequence=ok preamble=differs ccr14=identical rule=identical"` 終了コード 0 (missing 1 = F-17 のその場訂正、added 8 = その訂正後の文 + 新規 6 + Status 1、empty_axis_removed 1 = r2db-api `capacity and concurrency` の Status の `- —`)。M23-wp3 `expect=red got=red`、復元 sha256 × 2。ブロック長: SI-08 r2db-api 既定 10,268 (残 4,932)・`capacity and concurrency` 9,226・MitateDB-api 既定 8,010。最長は SI-09 MitateDB-api `platform upgrade` の 12,681 のまま。
- 受け入れ監査 1 回: §1.3 の 5 項、WP-1 の 13 項、WP-2 の 12 項は充足。WP-3 の証拠不足 2 件は上のとおり監督が埋めた。
- 完了ゲート (最終の木、監督が単独実行): `3844 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0 (前回 main は 3822。差 22 は新規テスト 22 件)。
- **最終判定: 受け入れる。** 本番 (VPS) では script を流していない。

