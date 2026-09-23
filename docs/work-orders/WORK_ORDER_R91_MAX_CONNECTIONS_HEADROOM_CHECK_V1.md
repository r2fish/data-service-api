# 作業指示書 — R-91 両 peer の `ops verify-declarations` と起動時に `max_connections` の余裕を検査する (F-18)

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点 main `dd12657`、worktree `.claude/worktrees/r91` (branch `r91-max-connections-headroom-check`)。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の **R-91** 行 (`RM`:516)。関連は同 §8 の **R-52** 行 (`RM`:477、残件 (i)(ii) が開いている)。
- **変更クラスは D** (§1.2 の D-0。`security/CONTROL_MAPPING.md` の両 peer の SI-08 の主張に追記する)。**契約は 1.8.0 のまま**で `spec/` と `conformance-tests/` の差分は **0**。
- **D が求める依頼者裁定の逐語記録**は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) であり、本件の決定はその委任の下で**監督が下した**。完了後に引き継ぎ書で**事後報告**する (R-57・R-59・R-60/R-61・R-62 と同じ扱い)。版付きの security-contract 決定に当たるのは `security/CONTROL_MAPPING.md` の**版**であり、**版数は統合時に監督が割り当てる** (R-87 → R-90 → 本件の順に統合するため)。
- **設計文書は新しく起こさない。** 枠 (D-0〜D-9 と却下案) は §1.2 にあり、これが監督の確定した決定である (先行する形は `docs/work-orders/WORK_ORDER_R62_R2DB_CATALOG_TIMEOUT_V1.md` と `docs/work-orders/WORK_ORDER_R87_MITATEDB_CATALOG_READ_EXECUTION_MS_V1.md`)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`gate.py`・`finalize.py` は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。
- **本件は 1 つの変更セットである** (監督裁定 2026-09-23 の 1)。**WP-1 → WP-2 → WP-3 を同じ worktree・同じ実装担当で直列に行い、1 回で統合する** (D-9)。**並行 WP は無い**ので、触るファイルの重なりの表は置かない (§1.2 の 16・17 は該当しない)。**WP-3 は R-90 の統合の後に rebase してから着手する**。申告と実挙動は単一コミットである (§1.1 の 11)。
- **WP-1 の完了条件は両 peer の `tests` の緑まで**とし、**`conformance-tests/test_control_mapping_register.py` の検査は WP-3 の完了条件に置く** — `security/CONTROL_MAPPING.md`:681 が引用する同型 pin のテスト名の改名は **WP-3 で同時に直す**ので、WP-1 の時点では引用が解決しない状態を通る (同じ変更セットの中で閉じる。監督裁定 2026-09-23 の 1)。
- **本書の確定文 (`security/CONTROL_MAPPING.md` へ入れる文と runbook の追記文) は、実装とテスト名が決まった後に監督が確定する** (§1.5 の 34)。§4.2 と §3.2 は確定文の**形**と**埋める穴**だけを与える。

## 1. 枠

### 1.1 問題設定と守るべき条件

両 peer とも `max_connections` を**起動時にも `ops verify-declarations` にも検査しない**。F-16 (`check_role_connection_limits`) が見るのは role ごとの `pg_roles.rolconnlimit` が `-1` かその role 自身の 1 process 分の pool 構成の床以上であること**だけ**で、配備全体の接続需要が PostgreSQL の `max_connections` に収まるかは見ない。したがって「role 上限は足りるが `max_connections` が足りない」配備は起動時 fail-fast を通り、**負荷が上がってから PostgreSQL の接続拒否に当たる**。r2db-api は配備 script の入口 (`part1a_check_max_connections.sh`) にだけ確認を置き、MitateDB-api の配備経路には自動の確認が無い (`ops inventory` 項目 (8) は運用者が process 数と予約枠を手で渡す別経路である)。

守る条件:

- **(a) 検査は宣言された値だけから判定する** — 運用者の手入力を要しない。使える材料は `process_ceilings` 宣言 (F-15 が読む plane ごとの process 数)、F-16 の床 (role ごとの 1 process あたりの pool 構成)、PostgreSQL の `max_connections`・`superuser_reserved_connections`・`reserved_connections` (PG16。`pg_settings` は誰でも読める) である。
- **(b) runbook の「One formula, not three」と矛盾させない** — `CONNECTION LIMIT` の合計を要件にしない。実需要 = Σ_role 床(role) × その role を使う plane の宣言 process 数 (両 plane が使う role は両方を足す)。
- **(c) 十分条件を名乗らない** — 対話 / 診断のセッションの分を含まないので「**必要条件**」として開示する。
- **(c′) 判定は宣言が保証する「下界」で行い、「上界」は報告だけにする** (設計レビュー 1 の R1-3、監督裁定 2026-09-23)。宣言 (`process_ceilings`) は**どの application をどの process が担うか・control plane が実際に配備されているか・auditreader を使うか**を何も言わないので、「全 registered application × 全 data process」の Σ は**上界**であり、上界で止めると健全な配備が起動できなくなる (runbook の「保守的な代用値は要件ではない」とも矛盾する)。上界が過大になる源は 3 つある — **(i) その process が担当しない application、(ii) まだ配備していない control plane、(iii) 使っていない auditreader**。**下界**は、宣言を守るどんな配備でも必ず開く数 (data plane 1 process が platform pool と、application が 1 件でも在れば 1 件分の runtime / developer を開く。control plane 1 process が control の pool を開く) であり、**赤は「宣言した ceiling をこのクラスタは収容できない」= 宣言が偽であることを意味する**。したがって**偽の赤は無い** (`RM`:130 の P-3)。
- **(d) 契約 1.8.0 と `conformance-tests/` の差分 0。**
- **(e) peer ごとに独立実装** (`RM`:133 の P-6)。同名の純関数は同型 pin (§1.5 の 38)。

### 1.2 決定 (監督確定 2026-09-23。D-0〜D-9)

- **D-0 (変更クラス)** **D**。両 peer の SI-08 の F-16 の主張に **F-18 の主張を 1 本ずつ足す** (追記であり、`security/CONTROL_MAPPING.md`:657 の「F-16 itself still does not read `max_connections`」は**真のまま残す** — F-16 の判定は変えないため)。`CONTROL_MAPPING` の**版数は統合時に監督が割り当てる** (R-87 → R-90 → 本件の順に統合)。**`security/` と両 peer の `ops.py` / `test_audit_query.py` を触る WP は R-90 の統合の後に rebase して行う** (§1.2 の 16)。**設計レビュー 1 回。**
- **D-1 (検査 F-18。R1-3 / R1-5 の裁定で v1.0 の本文を書き直した — 2026-09-23)** `ops verify-declarations` に **F-18** を足す。**判定は宣言が保証する下界で行う**:

  ```
  下界 = data_ceiling   × (platform pool の床 + [registered application が 1 件以上] × application 1 件の床)
       + control_ceiling × (control plane の床)

  判定: 下界 + superuser_reserved_connections + reserved_connections <= max_connections
  ```

  **両 peer の値** (§1.3 の (3) の module 定数): `platform pool の床` = **`_API_ROLE_STORE_COUNT (=2) × concurrency`** (api class)、`application 1 件の床` = **`2 × concurrency`** (runtime + developer の 1 組)、`control plane の床` = **`_CONTROLPLANE_ROLE_POOL_FLOOR (=16)`** (4 store × 4)。**`auditreader` は下界に含めない** — 配備の有無が宣言に無いからである (§1.1 の (c′) の (iii))。`data_ceiling` / `control_ceiling` は `process_ceilings` 宣言の値。

  **上界は判定に使わず、情報として出力する** — `verify-declarations` の F-18 の OK 行に **下界・上界・予約枠・`max_connections`** を出す。上界は「全 registered application × `data_ceiling`」「`auditreader` の床 4 × `control_ceiling`」を含む数である。

  **F-16 からの床の抽出は行わない** (R1-5)。F-18 は **F-16 と同じ module 定数 (class ごとの床) と `concurrency`・registered application 数・`process_ceilings`** から計算する**純関数**であり、per-role の `max(...)` や複数 class の帰属といった問題は生じない。**`plane_of_role` / `planes_of_role` は不要**である。**`check_role_connection_limits` のコードは 1 行も変えない** (除外理由のコメントも不変)。

  **`process_ceilings` 行が無い (F-15 が赤) ときは F-18 は判定せず F-15 に委ねる。**

  **限界 (c) (R1-4)**: 床は `concurrency` と module 定数から導くので、**`R2DB_PLATFORM_POOL_SIZE` による上書きには両 plane とも追随しない** — data plane の platform pool (既定 = `concurrency`) と control plane の store 寸法 (既定 4) をこの env で上げた配備では、下界が実需要を下回る。これは **F-16 が既に持つのと同じ限界**であり、**F-16 と同じ限界として開示する** (新規の起票はしない)。
- **D-2 (終了コード。R1-7 の裁定を反映した)** `_VERIFY_DECLARATIONS_EXIT_CODES["F-18"]` = 次の空き番号 = **17** (§1.3 の (1) の実測。F-17 = 16)。メッセージは `_f18_message` (**同型 pin**) とし、**計算した下界・上界・予約枠 (2 値)・`max_connections`・不足分**を含める。**環境変数名を書かない。** peer 固有の語は `_f16_message` と同じく **`ops_module` 引数**で渡す。案内は「**`max_connections` を上げるか、宣言した `process_ceilings` を下げる**」だけにする (`concurrency` の案内は落とす)。**運用者の入力値をエコーしない** (読んだ設定値と宣言値だけを出す)。
- **D-3 (起動時 fail-fast)** 両 peer の各 plane の起動時に、**D-1 と同じ下界**で、**配備全体で**判定する — **F-16 のような絞り込み (`role_classes` / `application_slugs` / `application_ids`) はしない**。`max_connections` は全 process が共有する資源で、超過はどの process にも当たるからである。超過なら F-16 と同じ形で起動を止める (§1.3 の (6) の 4 箇所)。
- **D-4 (同型性。R1-5 の裁定で対象を入れ替えた)** 両 peer の `_ISOMORPHIC_TARGETS` に載せるのは **`headroom_lower_bound`・`check_max_connections_headroom`・`_f18_message` の 3 行**である。純関数は **peer 固有の語を持たない signature** にする (例: `headroom_lower_bound(*, data_processes, control_processes, platform_pool_floor, application_pair_floor, control_plane_floor, registered_applications) -> int`、`check_max_connections_headroom(...)` が判定して `_f18_message` を組む)。件数は **143 → 146** (R-90 の +4 の後なら実測値。**統合順で監督が確定する**)。**F-16 側の symbol は 1 つも足さない / 変えない** (床の抽出をしないため。R1-9 は対象消滅)。
- **D-5 (テスト。両 peer、実 PostgreSQL の既存 harness。R1-1 / R1-2 / R1-6 の裁定を反映した)**
  1. 使い捨てクラスタは `max_connections=300`、`superuser_reserved_connections` の**既定は 3**、`reserved_connections` の既定は 0 なので、**実効の余裕は 297** である (§1.3 の (7)(8) の実測)。**赤は「下界が 297 を超える `process_ceilings` を宣言する」ことで作る** — application を多数 provision する必要は無く、**宣言を上げるだけ**でよい (例: `{"data":3,"control":1}` の下界 = 3 × 128 + 16 = **400**)。**収まる宣言では緑** (positive control。例: `{"data":2,"control":2}` の下界 = **288**)。v1.0 の (1)(2) はこの 1 件に統合した。
  2. **純関数の単体テスト** (両 peer、同型): 下界の算式 (application 0 件 / 1 件以上、`data` / `control` の倍数) と、予約枠を含めた境界の 3 点 (1 少ない / ちょうど / 1 多い)。
  3. **予約枠の読み取り helper の単体テスト** (R1-6): **偽の cursor に `reserved_connections = 5` を返させ**、読み取り helper がその値を返すことを観測する (実クラスタの静的パラメータを変えずに「読んでいること」を固定する)。
  4. **起動時 fail-fast が F-18 で止まる** (F-16 の startup テストの型。4 箇所)。
  5. **exit code 表の pin。**
  6. **既存の宣言値の棚卸し** (R1-1 / R1-2): **両 peer の `tests` と `conformance-tests` が宣言する `process_ceilings` の全行が、下界で 297 に収まる**こと (§1.3 の**宣言値の表**)。収まらない行は本 WP で**収まる値に下げ**、そのテストの意図が値に依らないことを確かめる (**依るなら止めて報告する**)。

  **完了条件 1 項目 = 変異 1 つ** (§1.5 の 33・40)。
- **D-6 (runbook)** 両 peer の `max_connections` の算式の節に「**`verify-declarations` の F-18 が宣言値からこの必要条件を検査する**。対話セッションと rollout の並走 (`process_ceilings` に織り込む) は運用者の導出」を、**段落単位で現物照合して**足す。**r2db の `part1a` script は残す** (配備**前**の確認であり、F-18 は配備**後**の確認である)。

  **追加 (監督裁定 2026-09-23 の 5)**: **MitateDB の runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`:500-505 の算式 (Σ `CONNECTION LIMIT` + 対話セッション + 予約枠) を、段落単位で書き換える** — r2db と同じ**一つの算式** (`max_connections >= 実同時接続 + 予約枠`、Σ `CONNECTION LIMIT` は導出していない運用者向けの**保守的な代用値**) に揃える。却下案 (1) を両 peer の runbook から消すための書き換えであり、`0014` の註・表・F-16 の段落は触らない。
- **D-7 (開示。Class D)** 両 peer の SI-08 の F-16 の主張の**直後**に F-18 の主張を 1 本ずつ足す (**追記**。証拠のテスト名つき)。**`:657` は真のまま**である。**R-52 (open) との関係**を MitateDB の主張に 1 文 (**rollout の並走分を `process_ceilings` に宣言していれば、その分が F-18 の下界に反映される**)。**主張の制約には「判定は宣言が保証する下界 (application 1 組分) で行い、全 registered application を数えた上界は報告だけに出す」と「道具自身の接続と対話 / 診断セッションは数えない」を含める** (監督裁定 2026-09-23 の 2。§1.3 の項目 (8) との差の表)。**確定文は監督が実装後に確定する。**
- **D-8 (コメント)** docstring は現在形で書く (経緯語を入れない)。`python3 tools/check_comment_provenance.py --base dd12657 <触った src>` は「**§4.1 (1) 以外が 0 行**」。
- **D-9 (WP 分割)** **WP-1** = 両 peer の F-18 (純関数・`ops`・起動時・テスト・同型 pin。**床の抽出は R1-5 で撤回した**)、**WP-2** = runbook 2 本、**WP-3** = `security/CONTROL_MAPPING.md` (**R-90 の統合後**)。**同じ worktree・同じ実装担当で直列に行い、3 本を 1 つの変更セットとして 1 回で統合する** (監督裁定 2026-09-23 の 1)。**WP-1 の完了条件は両 peer の `tests` の緑まで**とし、**`conformance-tests/test_control_mapping_register.py` の検査と `security/CONTROL_MAPPING.md`:681 の引用名の改名は WP-3 に置く。**

### 1.3 起草時の実測 (基点 `dd12657` の現物。起草者が実施)

| # | 観測 | 出所 |
|---|---|---|
| (1) | **F 一覧と exit code 表**: 表は両 peer で**逐語同一**で、`F-3`:3 / `F-3c`:4 / `F-4`:5 / `F-4b`:6 / `F-5`:7 / `F-8`:8 / `F-6`:9 / `F-7`・`F-10`・`F-11`:10 / `F-13`:11 / `F-9`:12 / `F-14`:13 / `F-15`:14 / `F-16`:15 / `F-17`:16。**次の空き番号は 17** (`F-12` は表に無い「予約」で、本コマンドの範囲外と表自身が書く)。判定の並びは `read_platform_declarations` (F-8/F-3/F-4/F-15/F-5/F-4b) → F-3c (`--control` 時) → F-6 (env 有時) → F-7/F-10/F-11/F-13/F-9 → F-14 → F-16 → F-17 → `return 0` | `r2db-api/src/r2db_api/ops.py`:986-1013・:1016-1142、`MitateDB-api/src/mitatedb_api/ops.py`:1260-1287・:1329-1415 |
| (2) | **F-18 を足す 2 箇所はどちらも同型 pin の対象である**: `_VERIFY_DECLARATIONS_EXIT_CODES` と `_verify_declarations_checks` がともに `_ISOMORPHIC_TARGETS` の行である。したがって**表への `"F-18": 17` の追加も、`_verify_declarations_checks` への F-18 の呼び出しも、両 peer で正規化後に一致する文でなければならない**。F-16 の呼び出しは peer 差を `_declared_concurrency()` (peer 同名・peer 固有の本体) に押し込んでこの制約を満たしている | `r2db-api/tests/test_audit_query.py`:2615・:2666・:3100・:3132、`MitateDB-api/tests/test_audit_query.py`:2389・:2440・:2873・:2905、`r2db-api/src/r2db_api/ops.py`:1145-1152 |
| (3) | **F-16 の床計算と module 定数** (**R1-5 の裁定により、抽出は行わない — F-18 は同じ定数から計算する。以下の行範囲は「触らない範囲」の記録である**): r2db は `check_role_connection_limits` が :1020-1024 (signature)・:1025-1063 (docstring)・:1064-1110 (**床の計算**)・:1111-1112 (`if not floors: return`)・:1113-1123 (`pg_roles` 読み + 比較 + raise)。MitateDB は :993-997・:998-1035・:1036-1084・:1085-1086・:1087-1097。(v1.0 の「切れ目は `if not floors:` の直前」という抽出の設計は R1-5 で撤回した。) 床の値は api = `_API_ROLE_STORE_COUNT (=2) × concurrency`、controlplane = `_CONTROLPLANE_ROLE_POOL_FLOOR (=16)`、auditreader = `_AUDITREADER_ROLE_POOL_FLOOR (=4)`、application の runtime / developer = `concurrency`。複数 class に当たる role は `max(...)` で最強の床を採る (M-1) | `r2db-api/src/r2db_api/platform_declarations.py`:947・:954・:960・:1020-1123、`MitateDB-api/src/mitatedb_api/platform_declarations.py`:917・:927・:934・:993-1097 |
| (4) | **role → plane の対応 (両 peer で同じ形)**: `api` class の role → **data**、`controlplane` class の role → **control**、`auditreader` class の role → **control**、application の runtime / developer role → **data**。出所は**起動時の絞り込みそのもの**である (各 process が自分の pool が当たる role だけを渡している) と、MitateDB の `ops inventory` 項目 (8) の需要計算 (`api_demand = data_process_count_total × api_floor`、`controlplane_demand` / `auditreader_demand` = `control_process_count_total × 各床`、`app_role_demand = data_process_count_total × concurrency`)。`auditreader` を control 側だけに数える根拠は項目 (8) の docstring が逐語で持つ (「measured: only `mitatedb_api.control_composition.build_control_service` ever pools a connection against it, `mitatedb_api.main.build_app` never does」)。**role が 2 class に当たる場合 (M-1)** は D-1 の「両 plane が使う role は両方を足す」に従う | `r2db-api/src/r2db_api/main.py`:471-475、`同 control_main.py`:578-585、`MitateDB-api/src/mitatedb_api/main.py`:378-382、`同 control_composition.py`:181-185、`MitateDB-api/src/mitatedb_api/ops.py`:2446-2478・:2540-2549 |
| (5) | **`process_ceilings` の読み方**: `read_platform_declarations` が返す `PlatformDeclarations.process_ceilings` (`ProcessCeilings(data:int, control:int)`、どちらも正の整数)。行が無い / 値が壊れているときは**どちらも `code="F-15"`** で raise する。**4 つの composition root はすべて起動時に既に `read_platform_declarations` を呼び、`process_ceilings` を使っている**ので、F-18 のために新しい読みは要らない | `r2db-api/src/r2db_api/platform_declarations.py`:168-190・:453-484・:489-535、`MitateDB-api/src/mitatedb_api/platform_declarations.py`:156-175・:428-459・:489-509、`r2db-api/src/r2db_api/main.py`:376・:394、`同 control_main.py`:521・:604、`MitateDB-api/src/mitatedb_api/main.py`:345・:479、`同 control_composition.py`:125・:268 |
| (6) | **起動時の F-16 呼び出しの 4 箇所と接続の login role**: r2db data = `main.py`:471-475 (`durable_audit` の pool から借りた接続。login role は実際の `application_audit` writer = api role。`role_classes={"api"}`, `application_slugs=slugs`)、r2db control = `control_main.py`:578-585 (`role_classes` は `{"controlplane"}` + `R2DB_AUDIT_DSN` が在れば `"auditreader"`、`application_slugs=()`)、MitateDB data = `main.py`:378-382 (`declarations_conn`、`role_classes={"api"}`, `application_ids=ids`)、MitateDB control = `control_composition.py`:181-185 (同形、`application_ids=()`)。いずれも `try/except` で包まれておらず**例外はそのまま伝播して起動を止める** | 同上 |
| (7) | **`pg_settings` の 3 GUC の読みと権限 (実測 2026-09-23、PostgreSQL 16.14)**: **非 superuser の role で `SET ROLE` した session から、`max_connections` / `superuser_reserved_connections` / `reserved_connections` の 3 つとも `SHOW`・`current_setting()`・`pg_settings` のいずれでも読めた** (superuser 限定 GUC ではない)。したがって (6) の 4 箇所の接続 (api / controlplane role) でも `ops verify-declarations` の接続でも読める。既定値は `superuser_reserved_connections` = **3**、`reserved_connections` = **0**。`reserved_connections` は **PG16 で追加された GUC** である。**既存の読みの例**: `SHOW max_connections` は `MitateDB-api/src/mitatedb_api/ops.py`:2495-2497 (項目 (8)) の 1 箇所だけ、3 GUC を `pg_settings` から読む例は runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`:3267 の運用者向け `psql` 例、`SHOW` 2 本を bash から読む例は `r2db-api/deploy/scripts/part1a_check_max_connections.sh`。**`r2db-api/src` に `max_connections` を読むコードは 1 行も無い** | 実測 (ローカル PostgreSQL 16.14、`SET ROLE <非 superuser>` の後に 3 GUC を読み出した)、および上記の各ファイル |
| (8) | **使い捨てクラスタの `max_connections` は 300 固定** (`postgres -c max_connections=300`。静的パラメータであり、テストから下げることはできない)。`superuser_reserved_connections` は既定 3、`reserved_connections` は既定 0 なので、**F-18 の判定に使える余裕は 297** である。r2db の `concurrency` は**固定 32** (`ResourceLimits.concurrency`、env で上書きされない)、MitateDB は `FoundationConfig.max_concurrency` (既定 32、`MITATEDB_MAX_CONCURRENCY` で上書き可)。`process_ceilings` が `{"data":1,"control":1}` のとき、platform-plane の需要は 64 (api) + 16 (controlplane) + 4 (auditreader) = **84**、application 1 件あたり **64** (runtime 32 + developer 32)。したがって **application 3 件で 84+192 = 276 ≤ 297 (緑)、4 件で 84+256 = 340 > 297 (赤)** となる。宣言 `process_ceilings` を `{"data":2,...}` に上げれば同じ構成で赤にできる (D-5 の (2)) | `tools/testpg/dsa_testpg.py`:826-840、`r2db-api/src/r2db_api/limits.py`:17、`MitateDB-api/src/mitatedb_api/ops.py`:1418-1431 |
| (9) | **既存の F-16 テストと fixture**: 両 peer の `tests/test_ops_verify_declarations.py` に `test_verify_declarations_f16_passes_after_migration_0013` (MitateDB は `..._0012`)、`::test_verify_declarations_f16_fails_when_a_role_connection_limit_is_lowered_below_its_pool_composition_floor` (exit 15 と役名・現在値・床を assert)、`::test_f16_floor_for_a_role_matching_multiple_classes_is_the_max_not_the_last_assigned`、`::test_f16_the_schema_owning_role_is_never_flagged_even_though_it_matches_every_class`。fixture は module 内の `platform` (実 PostgreSQL、`0008` まで migrate、application は既定で 0 件)、application を足すのは `_provision_app_for_verify(platform, slug)` (実 `0003_provision_application.sql` を流す)、宣言行の書き換えは `_set_row(platform, key, value)`、検査の起動は `_run_verify(monkeypatch, dsn=..., schema=...)`。**起動時 fail-fast の既存テスト**は r2db が `tests/test_credential_persistence.py`:1642 と `tests/test_surfaces_env.py`:353、MitateDB が `tests/test_application_audit.py`:921 と `tests/test_control_main.py`:127 | `r2db-api/tests/test_ops_verify_declarations.py`:218-266・:571-593・:729-843、`MitateDB-api/tests/test_ops_verify_declarations.py`:755-869、上記 4 ファイル |
| (10) | **`_ISOMORPHIC_TARGETS` の正規化規則**: `_normalize` が落とすのは (a) 先頭 docstring、(b) 両 peer の package 名 (`r2db_api` / `mitatedb_api` → 同一の placeholder)、(c) 行末の空白、(d) 連続空行のみ。加えて `ResourceLimits` / `FoundationConfig` と `R2DB_` / `MITATEDB_` も placeholder に寄せる。**字下げ・行内の空白・数値リテラルは正規化しない** (数値を畳まないことを専用テストが固定する)。したがって **`application_slugs` / `application_ids` のような peer 差のある識別子を含む関数は pin できない** — `check_role_connection_limits` が pin の対象外なのはこの理由で、除外の理由がコメントに逐語で在る。表は現在 **143 行**で、**件数は pin テストの名前にも入っている** (`test_isomorphic_target_table_is_pinned_to_its_current_143_rows`、両 peer)。この pin テストは**表自身の行でもあり**、さらに `security/CONTROL_MAPPING.md`:681 がこのテスト名を証拠として引用している (`conformance-tests/test_control_mapping_register.py` は引用されたテスト名が実在の `def` に解決することを検査する) | `r2db-api/tests/test_audit_query.py`:2899-2921・:2924・:3250・:3331-3432、`MitateDB-api/tests/test_audit_query.py`:2698・:3023・:3104-3205、`security/CONTROL_MAPPING.md`:681、`conformance-tests/test_control_mapping_register.py`:923 |
| (11) | **runbook の該当段落**: r2db は **§4 Connection ceiling** (:162-) の中に、`CONNECTION LIMIT` 表 (:333-340)、**「One formula, not three」** (:342-368。「It is not an additional term to sum into `max_connections`」「roles may be deliberately over-subscribed」「Summing the CONNECTION LIMIT table instead is a conservative, easy-to-compute stand-in … not a PostgreSQL requirement in its own right」と逐語で書く)、**F-16 の段落** (:377-389。「independently of `max_connections`」)、**`part1a` の段落** (:391-408) が並ぶ。真の需要の式は「declared `concurrency` × role count (runtime + developer) × applications served by this process、plus `2 × platform_pool_size`」+ 対話セッション + `superuser_reserved_connections` である (`platform_pool_size` の既定は `concurrency` と同じ 32 で、`R2DB_PLATFORM_POOL_SIZE` で上書きできる)。MitateDB は §3 の「Phase 10 WP-4f … adds a role `CONNECTION LIMIT` …」の段 (:440-) に `CONNECTION LIMIT` 表 (:479-486)、`0014` の倍化の註 (:488-498)、**算式** (:500-505。「`max_connections` … must be >= the sum of every role's own `CONNECTION LIMIT` above, PLUS … interactive/diagnostic `psql` sessions … PLUS `superuser_reserved_connections` (default 3)」)、**F-16 の段落** (:507-510) が並ぶ。**D-6 の追記位置は両 peer とも F-16 の段落の直後**である (r2db は `:389` と `:391` の間、MitateDB は `:510` と `:512` の間) | `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`:162・:270-290・:333-408、`MitateDB-api/docs/cloud-run-cloud-sql.md`:440-514、`r2db-api/src/r2db_api/main.py`:431 |
| (12) | **SI-08 のブロック長と F-16 行の位置** (上限は block 15,200 字 / 1 物理行 1,400 字): F-18 の主張が入る先は **`### r2db-api -- capacity and concurrency`** (:642 開始、**9,226 字**、残り **5,974**。F-16 の主張は `:651`、`part1a` の主張は `:656`-`:657` で `:657` は 1,302 字) と **`### MitateDB-api -- capacity and concurrency`** (:728 開始、**7,467 字**、残り **7,733**。F-16 は `:737`、`0014` は `:738`、R-52 に触れる行は `:739`)。どちらも `#### Control` の箇条にあり、`#### Evidence` は `- —`、`#### Status` は r2db が 1 件・MitateDB が `- —`。文書の最長ブロックは SI-09 の `MitateDB-api -- platform upgrade` (12,747 字) | 実測 (`conformance-tests/test_control_mapping_register.py` の分割規則で数えた)、`security/CONTROL_MAPPING.md`:5・:11-28・:642-666・:728-752 |
| (13) | **MitateDB `ops inventory` 項目 (8) の現物の算式** (D-1 の突き合わせ先): `api_demand = data_process_count_total × (2 × concurrency)`、`controlplane_demand = control_process_count_total × 16`、`auditreader_demand = control_process_count_total × 4` (`--control-not-deployed` なら後 2 者は 0)、`app_role_demand = data_process_count_total × concurrency`、`total_demand = api + controlplane + auditreader + app_shared_demand + _INVENTORY_MAX_CONCURRENT_CONNECTIONS (=2)`。判定は `total_demand + reserved_connections > max_connections` なら `blocked`。**`app_shared_demand` は `app_role_demand` そのもの (application が 1 件でも N 件でも同じ値)** であり、項目 (8) は application 件数に比例する物理的 worst case を数えない (`RM`:477 の残件 (ii) が自己言及する)。process 数と予約枠は CLI 引数 (`--data-process-count-total` 等) で**運用者が渡す** | `MitateDB-api/src/mitatedb_api/ops.py`:2446-2601・:2025・:3249-3253 |
| (14) | **`part1a_check_max_connections.sh` の式** (D-6 で残すもの): `R2DBSVC_CONTROL_DSN` で `SHOW max_connections` と `SHOW superuser_reserved_connections` を読み、差が `98 + 72 × (登録済み application 数 + 1)` 未満なら refuse する。`98`/`72` は `0013` 適用後の `CONNECTION LIMIT` の和 (runbook の conservative stand-in) で、運用者が実数を導出したなら `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` がそれを置き換える。**実行位置は `0002` の直後・`0005` の前**であり、application を provision する前・`process_ceilings` を宣言する前の段である | `r2db-api/deploy/scripts/part1a_check_max_connections.sh`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`:391-407 |
| (15) | **F-15 と F-18 の順序**: `_verify_declarations_checks` は `read_platform_declarations` の例外を最初に捕らえて `return` するので、**`process_ceilings` 行が無い / 壊れている配備では F-15 (exit 14) が返り、後続の検査は 1 つも走らない**。D-1 の「F-15 が赤のときは F-18 を判定しない」は、F-18 を**この早期 return より後ろ**に置けば構造的に満たされる | `r2db-api/src/r2db_api/ops.py`:1060-1070、`MitateDB-api/src/mitatedb_api/ops.py`:1330-1340 |
| (16) | **絞り込み無しで読む先の権限 (D-3 の確認)**: F-18 が要る読みは (a) `pg_settings` の 3 GUC (→ (7) で実測済み、誰でも読める)、(b) `information_schema.role_table_grants` と `pg_tables` (コード自身が「world-readable view」と書き、どの login role でも走る)、(c) `<registry>.applications` の**登録件数** (下界は「1 件以上か」だけを、報告する上界は件数そのものを使う) である。**(c) は両 peer とも api role と controlplane role の双方に `SELECT` が GRANT 済み**なので、(6) の 4 箇所の接続 (api / controlplane) から**絞り込み無しの読み**ができる。data plane は F-16 の現行の呼び出し (`application_slugs=slugs`) で既にこの読みを実行しており、**control plane は現在 `()` を渡すので初めてこの表を読む**ことになる (権限は在る) | `r2db-api/migrations/0005_credential_store.sql`:134、`同 0006_control_plane_http.sql`:471、`MitateDB-api/migrations/0002_registry_and_functions.sql`:253・:263、`r2db-api/src/r2db_api/platform_declarations.py`:963-975 |

**既存のテスト / conformance が宣言する `process_ceilings` の全列挙と下界** (R1-1 / R1-2 の裁定。実測 2026-09-23。下界の算式は D-1、両 peer とも `concurrency` = 32 の既定、registered application 1 件以上のとき `data × 128 + control × 16`、**実効の余裕は 297**):

| 宣言する場所 | 値 | 下界 | 判定 |
|---|---|---|---|
| `r2db-api/tests/test_process_ceilings_declaration.py`:544 (`build_app`) | `{2,1}` | 2 × 128 + 1 × 16 = **272** | 緑 |
| 同:689 (`build_control_app`) | `{1,2}` | 1 × 128 + 2 × 16 = **160** | 緑 |
| 同:765 (`ops declare-process-ceilings` の往復。**起動も `verify-declarations` も走らない**) | `{3,2}` | (判定されない) | — (着手時に現物で再確認する) |
| 同:797 (`build_app`) | `{5,5}` | 5 × 128 + 5 × 16 = **720** | **赤。本 WP で収まる値 (例 `{2,2}` = 288) に下げる** |
| 同:854 / `r2db-api/tests/test_ops_verify_declarations.py`:394 | `{0,1}` | (F-15 の不正値。判定に至らない) | — |
| `MitateDB-api/tests/test_process_ceilings_declaration.py`:291・:349・:382・:453・:539・:588 | `{1,1}` | 1 × 128 + 1 × 16 = **144** | 緑 |
| 同:363 | `{1,2}` | **160** | 緑 |
| 同:426 | `{2,1}` | **272** | 緑 |
| 同:114 (純関数の検証のみ) | `{3,2}` | (判定されない) | — |
| `conformance-tests/test_c26_composition_root.py`:94・:326・:473 (C-26 の起動) | `{1,1}` | **144** | 緑 |
| 同:101 (C-26 の再起動) | `{2,2}` | 2 × 128 + 2 × 16 = **288** | 緑 |
| 両 peer の migration が書く既定 (`0012` / `0011`) と、他の全テストが触らずに使う値 | `{1,1}` | **144** (application 0 件なら 80) | 緑 |

**`conformance-tests/` と `tools/testpg/` は触らない** — C-26 の `{2,2}` は下界 288 で収まる。**CI の docker PostgreSQL も `max_connections` は 300** なので前提は同じである。

**`ops inventory` 項目 (8) との差** (監督裁定 2026-09-23 の 2。**採るのは F-18 の列**):

| 観点 | `ops inventory` 項目 (8) の現物 | **F-18 (本件)** |
|---|---|---|
| process 数の出所 | 運用者が渡す CLI 引数 (`--data-process-count-total` / `--control-process-count-total`) | **宣言 `process_ceilings` の `data` / `control`** (運用者の入力を取らない。§1.1 の (a)) |
| plane ごとの数え方 | plane ごとの count-total × その plane の role の床 | **同じ** (plane ごと。§1.3 の (4) の表) |
| application role の数え方 | **1 件分だけ** (`app_shared_demand = app_role_demand`。application が N 件でも増えない — `RM`:477 の残件 (ii) が自認する既知の過小) | **判定 (下界) は 1 件分だけ** (registered application が 1 件以上なら 1 組を足す。R1-3)。**全 registered application を数えるのは報告する上界の側**であり、判定には使わない |
| 道具自身の接続 | `_INVENTORY_MAX_CONCURRENT_CONNECTIONS` (=2) を予約に足す | **足さない** (`verify-declarations` 自身の接続と対話 / 診断セッションは**必要条件の外**として開示する。§1.1 の (c)) |
| 予約枠 | 運用者が渡す `--reserved-connections` の 1 値 | **`superuser_reserved_connections` + `reserved_connections`** を同じクラスタから読む |
| 判定の場所 | `ops inventory` (Gate-0 の 10 項目の 1 つ) | **`ops verify-declarations` と 4 つの起動経路** |


### 1.4 却下した代替案 (監督確定。蒸し返さない)

- **(1) `CONNECTION LIMIT` の合計 ≤ `max_connections` を判定にする** — runbook が「要件ではない」と明言している (保守的な代用値。§1.3 の (11))。
- **(2) 運用者の入力 (期待ピーク) を引数に取る** — `part1a` と MitateDB の `ops inventory` が既に持つ形であり、**宣言値だけから判定する**条件 (a) に反する。
- **(3) F-16 の中に埋める** — F-16 の判定 (role ごと) と F-18 (配備全体) は別の性質で、失敗の名乗りが混ざる。
- **(4) 起動時は自 process の role だけに絞る** — 資源が共有なので、絞ると偽の緑になる。

### 1.5 未確定 (依頼者判断待ち)

- **無し** (Class D。事後報告)。


### 1.6 設計レビュー 1 の反映 (2026-09-23。監督裁定として全件採用し、本文へ反映した)

本書はまだ実装に渡っていない (v1.0 の確定前) ので、裁定は**本文へ反映**してある (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 57 が言う「実装に渡った後の訂正註」の場面ではない。R-60/R-61・R-62 の先例と同じ扱い)。**覆した判定は下表に根拠と日付とともに残す** (§1.8 の 56)。

| # | 重大度 | 裁定 (要旨) | 反映先 | 覆した v1.0 の判定 |
|---|---|---|---|---|
| **R1-3** | 重大 | **F-18 は宣言が保証する「下界」で判定し、上界は報告だけにする。** 宣言は application の分担・control の配備・auditreader の有無を言わないので、全 application × 全 data process の Σ は**上界**であり、上界で止めると健全な配備が起動不能になる (runbook の「保守的な代用値は要件ではない」とも矛盾する)。赤は「宣言した ceiling をこのクラスタは収容できない」= 宣言が偽、という意味になり**偽の赤は無い** | §1.1 の (c′)、D-1、D-3、完了条件 2・4・9・10、M4 | v1.0 の D-1 の「需要 = Σ_role 床 × plane の process 数」(= 上界) で判定する形。§1.3 の**項目 (8) との差**の表の「全 registered application を数える」行は、**上界の説明**として読む |
| **R1-5** | 中 | **F-16 からの床の抽出はやめる。** F-18 は F-16 と同じ module 定数・`concurrency`・registered application 数・`process_ceilings` から計算する純関数にする。`plane_of_role` は不要。**F-16 のコードと除外理由コメントは不変** | D-1、D-4、§1.3 の (3)、§2.1、完了条件 1・12、§2.3 の 1 行目 | v1.0 の D-1 の「床計算部を `_role_connection_floors(...)` へ抽出し F-16 はそれを使う」、D-4 の「2 行 (143 → 145)」と「床の抽出関数は pin しない」、完了条件 1 と M1 |
| **R1-1** | 重大 | **テストが宣言する `process_ceilings` は、使い捨てクラスタ (300、実効 297) が下界で収容できる値にする。** 全列挙と下界を §1.3 の表に置く | §1.3 の**宣言値の表**、D-5 の 6、§2.1、完了条件 11・17、M10b | — (v1.0 に対応する判定が無かった。欠落の補い) |
| **R1-2** | 重大 | `r2db-api/tests/test_process_ceilings_declaration.py`:797 の `{5,5}` (下界 720) を**収容できる値に下げ**、そのテストの意図が値に依らないことを確かめる (依るなら止めて報告)。`conformance-tests/` と `tools/testpg/` は触らない (C-26 の `{2,2}` は 288 で収まる) | 同上 | — (同上) |
| **R1-4** | 中 | 限界 (c) を**両 plane** (data 既定 = `concurrency`、control 既定 = 4 の `R2DB_PLATFORM_POOL_SIZE` 上書き) に広げる | D-1 の限界 (c) | v1.0 の限界 (c) (data plane だけを述べていた) |
| **R1-6** | 中 | 完了条件 7 と M7 を「**偽の cursor に `reserved_connections=5` を返させる読み取り helper の単体テスト**」に書き換える | D-5 の 3、完了条件 8、M7 | v1.0 の完了条件 7 (実クラスタの境界だけで「読んでいること」を固定しようとしていた) |
| **R1-7** | 中 | D-2: メッセージに**環境変数名を書かない**。peer 固有の語は `ops_module` 引数で渡す。案内は「`max_connections` を上げるか、宣言した `process_ceilings` を下げる」だけ (`concurrency` の案内は落とす) | D-2、完了条件 5、§2.5 の (vi) | v1.0 の D-2 (「`process_ceilings` / `concurrency` を下げる案内」) |
| **R1-8** | 低 | 件数 pin の改名は **peer ごと 4 箇所** (r2db :2416 / :3009、MitateDB :2202 / :2782、および pin テストの名前と本体) **+ `CONTROL_MAPPING.md`:681** | §2.1、完了条件 12 | — (v1.0 は 2 箇所しか挙げていなかった) |
| **R1-9** | 低 | **対象消滅** (床を抽出しないので、抽出先を壊す変異が無い) | §2.3 の完了条件 1 の行に「**不要**」と記した | v1.0 の M1 |
| **R1-10** | 低 | M5 を「`except` 側で `{data:1, control:1}` を**仮定して** F-18 を判定する」形にする | M5b | v1.0 の M5 (判定を早期 `return` より前へ移す形) |
| **R1-11** | 低 | §4.2 に `:739` の**主語を明示する**書き換え (Update convention) を足す | §4.2 | v1.0 の §4.2 (「偽になるなら書き換える」という条件付き) |

---

## 2. WP-1 — 両 peer に F-18 を足す (純関数・`ops`・起動時・テスト・同型 pin)

**目的**: 宣言された値だけから「**宣言した `process_ceilings` を守る配備が必ず開く接続数 (下界)** が `max_connections` に収まる」という**必要条件**を、`ops verify-declarations` と 4 つの起動経路が判定するようにする。**上界は報告だけに使う** (§1.1 の (c′))。

**読むべき正本**: §1.1 (守る条件、とくに (c′)) / §1.2 (D-1〜D-5・D-8) / §1.3 (実測と**宣言値の表**) / §1.4 (却下案) / §1.6 (設計レビュー 1 の反映)。**F-16 のコードは 1 行も変えない。** 規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.4〜§1.6。

### 2.1 触ってよいパス

- `r2db-api/src/r2db_api/platform_declarations.py` — **新しい純関数 2 本** (`headroom_lower_bound` / `check_max_connections_headroom`)、`_f18_message`、予約枠と `max_connections` の読み取り helper、`__all__` への追加 (実測: `__all__` は辞書順である)。**`check_role_connection_limits` とその周辺の定数・コメントは 1 行も変えない** (R1-5。床の抽出はしない)。床の値は既存の module 定数 `_API_ROLE_STORE_COUNT` / `_CONTROLPLANE_ROLE_POOL_FLOOR` を**読むだけ**である。
- `r2db-api/src/r2db_api/ops.py` — `_VERIFY_DECLARATIONS_EXIT_CODES` への `"F-18": 17` と、`_verify_declarations_checks` の **F-16 の後**への F-18 の判定 (OK 行に下界・上界・予約枠・`max_connections` を出す)。**この 2 つは同型 pin の対象**なので、MitateDB 側と正規化後に一致する文にする (§1.3 の (2))。peer 差が要るなら F-16 の `_declared_concurrency()` と同じ技法 (peer 同名・peer 固有の本体の helper) に押し込む。
- `r2db-api/src/r2db_api/main.py` (:471-475 の近傍) と `r2db-api/src/r2db_api/control_main.py` (:578-585 の近傍) — F-16 の呼び出しの**直後**に F-18 を**絞り込み無し**で足す (D-3)。既に読んである `declarations.process_ceilings` を使い、宣言の読みを二重に行わない (§1.3 の (5))。
- `r2db-api/tests/test_ops_verify_declarations.py` — 完了条件 2〜9 の新規テスト。置き場所は既存の F-16 節 (:729-843) と F-17 節の間。既存の F-16 テスト・fixture・helper (`platform` / `_provision_app_for_verify` / `_set_row` / `_run_verify`) は**書き換えない**。
- `r2db-api/tests/test_process_ceilings_declaration.py` — **:797 の `{"data": 5, "control": 5}` を、下界が 297 に収まる値 (例 `{"data": 2, "control": 2}`) に下げる** (R1-1 / R1-2。§1.3 の**宣言値の表**)。**そのテストの意図が値に依らないことを確かめる** — 依るなら**止めて報告する** (§1.5 の 37)。この 1 行以外は触らない。
- `r2db-api/tests/test_credential_persistence.py` (:1642 の近傍) と `r2db-api/tests/test_surfaces_env.py` (:353 の近傍) — 完了条件 10 の新規テスト (data / control)。既存の F-16 の起動時テストは書き換えない。
- `r2db-api/tests/test_audit_query.py` — `_ISOMORPHIC_TARGETS` の **3 行追加** (:2880-2921 の `platform_declarations.py` の並び) と、**同じ表の 2 つ目の写し** (:3009 近傍の `assert _ISOMORPHIC_TARGETS == (...)`)、件数 pin の実測更新。**件数は 1 peer あたり 4 箇所に現れる** (R1-8): r2db は表の自己参照行 **:2416**・2 つ目の写しの同じ行 **:3009**・pin テストの**名前** :2924・本体 `assert len(...) == 143` :3250、MitateDB は **:2202**・**:2782**・:2698・:3023。**加えて `security/CONTROL_MAPPING.md`:681 がこの pin テスト名を引用しており、その改名は WP-3 で行う** (§0、監督裁定 2026-09-23 の 1)。
- `MitateDB-api/src/mitatedb_api/platform_declarations.py` / `ops.py` / `main.py` (:378-382 の近傍) / `control_composition.py` (:181-185 の近傍)、`MitateDB-api/tests/test_ops_verify_declarations.py` / `test_process_ceilings_declaration.py` (§1.3 の表で収まらない行が在れば) / `test_application_audit.py` (:921 の近傍) / `test_control_main.py` (:127 の近傍) / `test_audit_query.py` — r2db と同じ範囲。**コードは共有せず、peer ごとに独立に書く** (P-6)。

**これ以外は 0 件。** とくに `spec/`・`conformance-tests/`・`tools/testpg/`・`security/` (WP-3)・両 peer の `docs/` (WP-2)・`migrations/`・`deploy/`・`tools/` を触らない (変異での一時編集は別。`mutate.py` が復元する)。**既存の検査が新しいコードで赤になったら直さず報告する** (§1.5 の 37)。**設計に無い検査・機構を足さない** (同 37)。

### 2.2 完了条件 (18 件)

| # | 完了条件 |
|---|---|
| 1 | **F-16 は不変**: `check_role_connection_limits` とその周辺の定数・除外理由コメントの差分が **0 行**である (`git diff` で示す。R1-5)。既存の F-16 テスト (両 peer 4 件) と起動時 2 件が**無改変のまま緑** |
| 2 | **下界の純関数**: 両 peer に `headroom_lower_bound(...)` (peer 固有の語を持たない signature) が在り、**D-1 の算式**で下界を返す。**単体テスト**が (a) `data` / `control` の倍数で線形に増えること、(b) **registered application が 0 件なら application の床を足さず、1 件以上なら 1 件分だけ足す** (件数に比例させない) ことを観測する |
| 3 | **判定と予約枠**: `check_max_connections_headroom(...)` が `下界 + superuser_reserved_connections + reserved_connections <= max_connections` を判定する (**等しいときは通す**)。**単体テスト**が境界の 3 点 (1 少ない / ちょうど / 1 多い) を観測する |
| 4 | **上界は報告だけ**: 上界 (全 registered application × `data_ceiling`、`auditreader` の床 4 × `control_ceiling` を含む) が**判定に使われていない**ことを、**上界だけが大きくなる入力で緑のまま**であることを観測して固定する。`verify-declarations` の **OK 行に下界・上界・予約枠・`max_connections` の 4 数**が出る |
| 5 | **`_f18_message`**: 両 peer に同名・同文の `_f18_message` が在り、**下界・上界・予約枠 2 値・`max_connections`・不足分**を含む。**環境変数名を書かない**。peer 固有の語は **`ops_module` 引数**で渡す。案内は「`max_connections` を上げるか、宣言した `process_ceilings` を下げる」だけである (R1-7)。実 PostgreSQL の FAIL テストがこれらの数を逐語で assert する |
| 6 | **`ops` の判定の位置**: `_verify_declarations_checks` が **F-16 の後**に F-18 を判定し、`OK   F-18 …` / `FAIL F-18 …` を出す。**`process_ceilings` 行を消した配備では F-15 (終了コード 14) が返り、F-18 は判定されない** (§1.3 の (15)) ことをテストが観測する |
| 7 | **終了コード**: `_VERIFY_DECLARATIONS_EXIT_CODES["F-18"] = 17` が入り、**表を固定する pin テスト**が両 peer に在る (`F-15` の pin `r2db-api/tests/test_process_ceilings_declaration.py`:860 と同じ型)。**`_VERIFY_DECLARATIONS_EXIT_CODES` も `_verify_declarations_checks` も同型 pin の対象**なので (§1.3 の (2))、**F-18 の追加 (表の行と判定の呼び出しの双方) が両 peer で正規化後に逐語一致する** — 一致しない差は `_declared_concurrency()` と同じ技法の peer 同名 helper に押し込む (監督裁定 2026-09-23 の 8) |
| 8 | **予約枠の読み取り (R1-6)**: `superuser_reserved_connections` / `reserved_connections` / `max_connections` を読む helper が在り、**偽の cursor に `reserved_connections = 5` を返させる単体テスト**がその値を helper が返すことを観測する (実クラスタの静的パラメータは変えない)。実クラスタでの値の突合は完了条件 3 の境界テストが持つ |
| 9 | **実 PostgreSQL の赤 / 緑 (R1-1)**: `_set_row(platform, "process_ceilings", …)` で**下界が 297 を超える宣言** (例 `{"data":3,"control":1}` = 400) にすると `ops verify-declarations` が**終了コード 17** で `FAIL F-18` を出し、**収まる宣言** (例 `{"data":2,"control":2}` = 288) では `OK   F-18` で緑になる。**application を多数 provision する形にしない**。数は §1.3 の**宣言値の表**の算式で書き、**実測した実際の数で確かめる** (§1.5 の 34) |
| 10 | **起動時 fail-fast (4 箇所)**: r2db の data / control、MitateDB の data / control の各 composition root が、**配備全体**の**同じ下界**で起動を止める。テストは「**その process 自身の role は床を満たしているのに**、宣言した ceiling の下界が `max_connections` を超えるので起動が止まる」ことを観測する (**絞り込みを入れると偽の緑になる**ことを示す形。D-3) |
| 11 | **宣言値の棚卸し (R1-1 / R1-2)**: §1.3 の**宣言値の表**の全行が緑である — `r2db-api/tests/test_process_ceilings_declaration.py`:797 の `{5,5}` を収まる値へ下げ、**そのテストの意図が値に依らない**ことを確かめた (依るなら止めて報告)。MitateDB 側も同じ表で確かめた。**両 peer の `tests` 全体**が緑であることをもって示す |
| 12 | **同型 pin**: 両 peer の `_ISOMORPHIC_TARGETS` に `headroom_lower_bound`・`check_max_connections_headroom`・`_f18_message` の **3 行**が入り、**表の 2 つの写し・件数 pin・pin テストの名前** (1 peer あたり 4 箇所。R1-8) が実測で更新されている (**143 → 146**。R-90 の統合後なら実測値。§1.5 の 40b)。**F-16 側の symbol は 1 つも足さない / 変えない**。`test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` が緑 |
| 13 | **監査照合**: `python3 tools/check_comment_provenance.py --base dd12657 <触った src の 8 パス>` の FAIL 行が **§4.1 (1) だけ**で、(2)・(3)・(5)・§9e・`#:` の行が **0 行** (D-8)。出力を逐語で報告に残す。**(2) が出たら止めて報告する**。判定を緩めない (§1.5 の 37) |
| 14 | **監査照合**: `python3 tools/change_class.py <触った全パス>` の出力、`python3 tools/check_doc_refs.py` が 0 dangling、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged。**実 credential・実ホスト名・実 DSN・作業機の絶対パスをテストにも文書にも書かない** (§1.9) |
| 15 | **監査照合**: `r2db-api/tests` と `MitateDB-api/tests` の suite をそれぞれ 1 回ずつ回し、集計行を逐語で報告に残す (§1.6 の 42。完了ゲートは監督)。**WP-1 の完了条件はここまでで、`conformance-tests/test_control_mapping_register.py` は WP-3 に置く** (監督裁定 2026-09-23 の 1。:681 の引用名は WP-3 で直す) |
| 16 | **監査照合**: §2.3 の変異が全件 `expect=red got=red` で、復元が sha256 2 回で照合済み (§1.4 の 29〜31) |
| 17 | **監査照合**: `git diff` が §2.1 の範囲だけであり、**`conformance-tests/` と `tools/testpg/` の差分が 0** である (R1-2) |
| 18 | §2.3 の対応表に**対応の無い行が無い** |

### 2.3 完了条件 → 変異

**両 peer に同じ形の変異を 1 件ずつ置く** (`mutate.py` は最初の失敗で止まるので、**赤にするテスト 1 件につき 1 エントリ**にする。`old` はファイル内に 1 回だけ現れる文字列にする)。

| 完了条件 | 変異 |
|---|---|
| 1 | **監査照合** (`git diff` が 0 行であることの照合。壊す対象が無い — R1-9 により F-16 側の変異は対象消滅した。**不要**) |
| 2 | **M2** (peer ごと 1 件): 下界の純関数から **`data_processes` の乗算**を落とす (床をそのまま足す) → **赤**: 完了条件 2 の単体テスト |
| 3 | **M3** (peer ごと 1 件): 判定から**予約枠の加算**を落とす → **赤**: 完了条件 3 の境界の単体テスト |
| 4 | **M4** (peer ごと 1 件): 判定を**上界**で行うように差し替える → **赤**: 完了条件 4 の「上界だけが大きい入力で緑」のテスト |
| 5 | **M5a** (peer ごと 1 件): `_f18_message` から**不足分**の数を落とす → **赤**: 完了条件 5 の実 PostgreSQL の FAIL テスト |
| 6 | **M5b** (peer ごと 1 件。R1-10): `read_platform_declarations` の `except` 側で `{"data":1,"control":1}` を**仮定して** F-18 を判定する形に差し替える → **赤**: 完了条件 6 の「`process_ceilings` 行が無い配備で終了コード 14」のテスト |
| 7 | **M6** (peer ごと 1 件): 表の値を `"F-18": 17` から `18` に変える → **赤**: 完了条件 7 の pin テスト |
| 8 | **M7** (peer ごと 1 件。R1-6): `reserved_connections` の読みをリテラル `0` に差し替える → **赤**: 完了条件 8 の偽 cursor の単体テスト |
| 9 | **M8** (peer ごと 1 件): `ops` が渡す process 数を `declarations.process_ceilings` から固定の 1 / 1 に差し替える → **赤**: 完了条件 9 の赤/緑のテスト (宣言に追随しなくなる) |
| 10 | **M9a〜M9d** (4 件): r2db `main.py` / `control_main.py`、MitateDB `main.py` / `control_composition.py` の F-18 の呼び出しをそれぞれ落とす → **赤**: 完了条件 10 の 4 件のテスト (1 エントリ 1 テスト) |
| 11 | **M10** (peer ごと 1 件): `_verify_declarations_checks` の F-18 の呼び出しを落とす (`OK` 行だけ残す) → **赤**: 完了条件 9 の FAIL テスト。**加えて M10b**: `test_process_ceilings_declaration.py` の下げた宣言を `{5,5}` に戻す → **赤**: そのテスト自身 (下界 720 が起動を止める) |
| 12 | **M11** (peer ごと 1 件): 片方の peer の `_f18_message` の 1 語を変える → **赤**: `::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`。**加えて M11b**: 件数 pin の数を 1 ずらす → **赤**: 件数 pin テスト |
| 1・13・14・15・16・17・18 | **監査照合** (照合対象は各行の本文のとおり。実行したコマンドと集計行、`file:line`、`git diff` を逐語で報告に残す。§1.5 の 40) |

- **M4 の註**: 「下界で判定する」という本件の核 (R1-3) を壊す唯一の変異である。上界と下界が同じ値になる入力 (registered application 1 件・`auditreader` 無し) では区別がつかないので、**テストは上界だけが大きくなる入力 (application 複数 + auditreader 在り) で書く**。
- **M5b の註**: 変異後も F-18 自体は動くので、「F-15 が先に返る」という**順序の性質だけ**が壊れる。
- **M10 の註**: `OK   F-18` の行だけを残すことで、「判定を通さずに緑を名乗る」という現実の退行の形を作る (§1.5 の 32)。


### 2.4 道具の引数

worktree は `.claude/worktrees/r91` (基点 main `dd12657`、branch `r91-max-connections-headroom-check`)。`pt.py` / `mutate.py` は main checkout を cwd にして走らせ、`$SP` (自分の scratchpad) を export しておく。

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- \
  r2db-api/tests/test_ops_verify_declarations.py MitateDB-api/tests/test_ops_verify_declarations.py \
  r2db-api/tests/test_audit_query.py MitateDB-api/tests/test_audit_query.py \
  r2db-api/tests/test_process_ceilings_declaration.py MitateDB-api/tests/test_process_ceilings_declaration.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- \
  r2db-api/tests/test_credential_persistence.py r2db-api/tests/test_surfaces_env.py \
  MitateDB-api/tests/test_application_audit.py MitateDB-api/tests/test_control_main.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- r2db-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- MitateDB-api/tests -q
tools/dev/mutate.py "$SP/r91-mutations.json" -C .claude/worktrees/r91 --wait 1800
```

**報告の前に両 peer の `tests -q` を 1 回ずつ回す** (上の 3・4 本目。§1.6 の 42)。worktree を cwd にして走らせるもの:

```bash
python3 tools/check_comment_provenance.py --base dd12657 \
  r2db-api/src/r2db_api/platform_declarations.py r2db-api/src/r2db_api/ops.py \
  r2db-api/src/r2db_api/main.py r2db-api/src/r2db_api/control_main.py \
  MitateDB-api/src/mitatedb_api/platform_declarations.py MitateDB-api/src/mitatedb_api/ops.py \
  MitateDB-api/src/mitatedb_api/main.py MitateDB-api/src/mitatedb_api/control_composition.py
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- worktree から subprocess を起こすテスト (composition root・`ops` CLI) には **`PYTHONPATH` を明示する** (§2 の 17。共有 `.venv` の `.pth` は main checkout の `src` を指す)。
- **`pytest` の直接実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。`gate.py` は他の pytest と同時に走らせると落ちるので、レビュー担当と同時刻に走らせない (§1.3)。
- 一時ファイルは `$SP` 配下だけに置く。報告は `$SP/r91-report.md` に書く。

### 2.5 レビュー

- **コードレビュー 1 回** (実装担当とは別の起動)。観点: (i) **`check_role_connection_limits` の差分が 0 行**であること (R1-5)、(ii) 起動時が**絞り込み無し**で、かつ**下界**で判定していること (絞り込むと偽の緑、上界で判定すると偽の赤。D-3・§1.1 の (c′))、(iii) 新規テストの空振り (§1.5 の 32) と代理指標 (§1.7 の 52) — とくに完了条件 4・5 が**数値を逐語で**見ていること、(iv) 同型 pin の 2 行が正規化後に一致すること (`application_slugs` / `application_ids` のような peer 差のある識別子を含んでいないこと。§1.3 の (10))、(v) レビュー担当自身の変異 1〜2 件 (報告に無いもの)、(vi) メッセージが**環境変数名を書かず** (R1-7)、運用者の入力値をエコーしていないこと・実 credential / 実ホスト名を含まないこと (§1.9)、(vii) §1.3 の**宣言値の表**の全行が実際に緑で、`conformance-tests/` と `tools/testpg/` の差分が 0 であること (R1-2)。

---

## 3. WP-2 — 両 peer の runbook の `max_connections` の節に F-18 を書く

**目的**: 配備を行う運用者が読む正本に、「この必要条件は機械が判定する」ことと「何が判定されないか」を残す。**WP-1 の実測 (終了コード・テスト名・メッセージの形) の後に書く** (§1.5 の 34)。

### 3.1 触ってよいパス

- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` — **§4 の F-16 の段落 (:377-389) の直後**に 1 段落を足す (:389 と :391 の間)。**「One formula, not three」(:342-368)・`CONNECTION LIMIT` 表 (:333-340)・`part1a` の段落 (:391-408) は 1 行も書き換えない。**
- `MitateDB-api/docs/cloud-run-cloud-sql.md` — (i) **F-16 の段落 (:507-510) の直後**に 1 段落を足す (:510 と :512 の間)、(ii) **算式の段落 (:500-505) を段落単位で書き換える** (監督裁定 2026-09-23 の 5。D-6)。**`0014` の註 (:488-498)・表 (:479-486)・F-16 の段落 (:507-510) は 1 行も書き換えない。**

**これ以外は 0 件。** コードもテストも `security/` も触らない。

### 3.2 追記する段落の「形」と埋める穴 (**確定文は監督が WP-1 の実測の後に確定する**)

両 peer とも、次の 4 つを**この順で**含む 1 段落とする (peer ごとに、その peer の語彙・既存の文体で書く。片方の文を他方へ写さない)。

1. **`ops verify-declarations` の F-18 が、宣言された値だけからこの必要条件を判定する**こと — 判定式 (Σ_role 床 × その role を使う plane の宣言 `process_ceilings` + `superuser_reserved_connections` + `reserved_connections` ≤ `max_connections`)、**終了コード〈穴 A: WP-1 の実測値。17 の見込み〉**、および**起動時にも同じ判定が走り、超過なら process が起動しない**こと。
2. **これは必要条件であって十分条件ではない**こと — **対話 / 診断の `psql` セッションの分は含まない** (運用者の導出のまま)。
3. **rollout 中の並走**は `process_ceilings` の宣言に織り込む形で F-18 に入る (宣言が 1 のままなら F-18 は 1 process 分しか数えない) こと。
4. **証拠のテスト名〈穴 B: WP-1 の新規テスト名〉**。

**r2db 側の追加の穴 C**: `part1a_check_max_connections.sh` は**残る**ので、両者の役割の違いを 1 文で書く — **`part1a` は配備の前 (`0002` の直後、application を provision する前) の確認、F-18 は配備された宣言に対する確認**である (D-6)。**「One formula, not three」の主張 (`CONNECTION LIMIT` の合計は要件ではない) を打ち消す文を書かない。**

**MitateDB 側の追加の穴 D**: この peer の配備経路にはこれまで自動の確認が無かったこと、および `ops inventory` 項目 (8) との違い — **項目 (8) は運用者が process 数と予約枠を渡す別経路**であり、**F-18 は宣言値だけから判定する**。加えて **F-18 は全 registered application を数え (項目 (8) は 1 件分)、道具自身の接続は数えない**こと (§1.3 の (13) と項目 (8) との差の表)。

### 3.3 完了条件 (8 件)

| # | 完了条件 |
|---|---|
| 1 | **監査照合**: r2db の段落が §3.2 の 1〜4 と穴 C を満たし、**§3.1 が挙げる既存の段落・表が 1 行も変わっていない** (`git diff` を逐語で報告に残す) |
| 2 | **監査照合**: MitateDB の段落が §3.2 の 1〜4 と穴 D を満たし、**§3.1 が挙げる既存の段落・表 (`0014` の註・表・F-16 の段落) が 1 行も変わっていない** (`git diff` を逐語で報告に残す) |
| 2b | **監査照合 (監督裁定 2026-09-23 の 5)**: `MitateDB-api/docs/cloud-run-cloud-sql.md`:500-505 の算式が、r2db の「One formula, not three」(`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`:342-368) と**同じ一つの算式**に揃っている — 要件は `max_connections >= 実同時接続 + 予約枠` であり、**Σ `CONNECTION LIMIT` は導出していない運用者向けの保守的な代用値**であって PostgreSQL の要求そのものではない、と書かれている。**r2db の文を写さず、この peer の語彙で書く**。書き換えた段落の前後を `git diff` で逐語に残す |
| 3 | **監査照合**: 段落中の**終了コードとテスト名が WP-1 の実測**であり、`file:line` の形の参照は実測で合っている (§1.5 の 34)。**両 peer の文は互いの写しではない** |
| 4 | **監査照合**: どちらの段落も「`CONNECTION LIMIT` の合計が `max_connections` の要件である」とは書いていない (§1.1 の (b))。**必要条件である旨が明示**されている (§1.1 の (c)) |
| 5 | **監査照合**: `python3 tools/check_doc_refs.py` が 0 dangling、`python3 tools/public_value_scan.py <2 パス>` が 0 flagged、`python3 tools/change_class.py <2 パス>` の出力を逐語で残す。**実ホスト名・実 DSN・実 credential・作業機の絶対パスを書かない** (§1.9) |
| 6 | **監査照合**: 両 peer の `tests -q` と `tools/tests` が緑 (runbook の literal を固定する既存の静的テストに触れていないことを示す。§1.3 の (14) の `98`/`72` を動かさない) |
| 7 | §3.4 の対応表に**対応の無い行が無い** |

### 3.4 完了条件 → 変異

| 完了条件 | 変異 |
|---|---|
| 1・2・2b・3〜7 | **変異は無い。全件が監査照合である** — 文書だけの WP であり、壊して赤にする実行時の性質を持たない。照合対象は各行の本文のとおりで、**実行したコマンドと集計行、`git diff`、`file:line` を逐語で報告に残す** (§1.5 の 40) |

### 3.5 道具の引数

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- r2db-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- MitateDB-api/tests -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- tools/tests -q
```

worktree を cwd にして: `python3 tools/check_doc_refs.py` / `python3 tools/public_value_scan.py <2 パス>` / `python3 tools/change_class.py <2 パス>`。**`gate.py` / `finalize.py`・commit・merge は監督。**

---

## 4. WP-3 — `security/CONTROL_MAPPING.md` に F-18 の主張を足す (**R-90 の統合後**)

**目的**: 正本順位 5 の文書に、両 peer の F-18 の control とその証拠を 1 本ずつ残す。**追記であり、F-16 の主張は書き換えない。**

**着手の前提**: **R-90 が main に入った後に、この worktree を main へ rebase してから始める** (D-0。`security/` と両 peer の `ops.py` / `test_audit_query.py` が重なるため。§1.2 の 16)。**版数は監督が割り当てる** (R-87 → R-90 → 本件の順)。

### 4.1 触ってよいパス

- `security/CONTROL_MAPPING.md` — (i) `### r2db-api -- capacity and concurrency` の `#### Control` (:651 の F-16 の主張の**直後**) に F-18 の主張 1 本、(ii) `### MitateDB-api -- capacity and concurrency` の `#### Control` (:737 の F-16 の主張の**直後**) に F-18 の主張 1 本、(iii) `:681` が引用する同型 pin のテスト名を WP-1 の実測後の名前に直す、(iv) Version 行 (`:5`) と length cap の再実測段 (`:29-` 近傍)。**行番号は R-90 の統合で動くので、着手時に実測し直す。**
- `security/CONTROL_MAPPING_HISTORY.md` — **(iii) の書き換えで置き換わる旧文を `## SI-08` へ逐語で移す** (冒頭の Update convention `:11-28`)。

**これ以外は 0 件。** コード・テスト・runbook を触らない。

### 4.2 主張の「形」と埋める穴 (**確定文は監督が確定する**)

- **r2db の 1 本** (:651 の直後): F-18 が `ops verify-declarations` を**終了コード〈穴 A〉**で落とし、**4 つの composition root の起動も止める**こと。判定は**宣言された値だけ**から行う (床は F-16 と同一、process 数は `process_ceilings`、予約枠は `superuser_reserved_connections` + `reserved_connections`)。**必要条件であり、対話 / 診断セッションの分を含まない**こと。**証拠のテスト名〈穴 B〉**。
- **MitateDB の 1 本** (:737 の直後): 同じ control をこの peer にも置いたこと (P-6 により独立実装)、および **R-52 (open) との関係を 1 文** — 「`process_ceilings` に rollout の並走分を宣言していれば、F-18 がその需要を数える」。**証拠のテスト名〈穴 C〉**。
- **`:657` は書き換えない** — 「F-16 itself still does not read `max_connections`」は F-18 を足した後も**真**である (F-16 の判定は不変。D-0)。
- **`:739`** (「F-16 の床は意図して倍化していない … `ops inventory` 項目 (8) だけが読む」) は、**F-18 が同じ床の定数を読む**ことで「項目 (8) だけが読む」が偽になるので、**Update convention で書き換え、旧文を逐語で履歴へ移す** (R1-11)。書き換えでは**主語を明示する** — 「倍化した ceiling を読むのは `ops inventory` 項目 (8) だけであり、F-16 と F-18 はどちらも 1 process 分の床の定数を読む」という形で、**何が「だけ」なのか**を取り違えられない文にする。**判定の根拠と新旧の文を報告に逐語で残す。**

### 4.3 完了条件 (8 件)

| # | 完了条件 |
|---|---|
| 1 | **監査照合**: r2db の主張 1 本が §4.2 の形で `:651` の**直後**に入り、既存の主張を 1 本も書き換えていない |
| 2 | **監査照合**: MitateDB の主張 1 本が §4.2 の形で `:737` の**直後**に入り、R-52 との関係の 1 文を含む |
| 3 | **監査照合**: **`:657` が変わっていない** (`git diff` で示す) |
| 4 | **監査照合**: `:739` について §4.2 の判定を行い、根拠と結論 (触った / 触らない) を報告に逐語で残した。書き換えた場合は旧文が `CONTROL_MAPPING_HISTORY.md` の `## SI-08` に**逐語で**在る |
| 5 | **監査照合**: `:681` が引用する同型 pin のテスト名が WP-1 の実測後の名前になり、**旧文が履歴へ逐語で移っている** (Update convention)。`conformance-tests/test_control_mapping_register.py` の**引用テスト名が実在の `def` に解決する**検査が緑 |
| 6 | **監査照合**: 2 つのブロックの**字数を実測**し、上限 15,200 と 1 物理行 1,400 の内側である (§1.3 の (12) の測り方)。Version 行 (`:5`) と length cap の再実測段を更新した (**版数は監督が与える**) |
| 7 | **監査照合**: `conformance-tests/test_control_mapping_register.py` が緑、`python3 tools/check_doc_refs.py` が 0 dangling、`python3 tools/public_value_scan.py <2 パス>` が 0 flagged、`python3 tools/change_class.py <触った全パス>` の出力を逐語で残す |
| 8 | §4.4 の対応表に**対応の無い行が無い** |

### 4.4 完了条件 → 変異

| 完了条件 | 変異 |
|---|---|
| 1〜8 | **変異は無い。全件が監査照合である** — 文書だけの WP である。照合対象は各行の本文のとおりで、**実行したコマンドと集計行、`git diff`、実測した字数を逐語で報告に残す** (§1.5 の 40) |

### 4.5 道具の引数

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- conformance-tests/test_control_mapping_register.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r91 -- r2db-api/tests/test_audit_query.py MitateDB-api/tests/test_audit_query.py -q
```

worktree を cwd にして: `python3 tools/check_doc_refs.py` / `python3 tools/public_value_scan.py <2 パス>` / `python3 tools/change_class.py <触った全パス>`。**`gate.py` / `finalize.py`・commit・merge は監督。**

---

## 5. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **(5-1) 対話 / 診断セッションの分**を判定に織り込むこと。F-18 は宣言値だけから判定する必要条件であり、運用者が開く `psql` の数は宣言に無い。両 peer の runbook がこれを運用者の導出として持ち続ける (§1.1 の (c)、D-6)。
- **(5-2) `part1a_check_max_connections.sh` の `ops` 化** (bash の確認を `ops` のサブコマンドへ移すこと)。script は配備**前**の確認として残す (D-6)。
- **(5-3) R-52 そのもの** — 残件 (i) (r2db-api の配備が 2 process を並走させうるか) と (ii) (`max_connections` が項目 (8) の条件 2 に足りない場合の方針。依頼者裁定 Q-4、本番の読み取りの後) は `RM`:477 の行に残る。本書は F-18 を足すだけで、この 2 件のどちらも決めない。

---

## 6. レビューと受け入れ

- **設計レビュー 1 回** (D-0)。本書 v1.0 に対して行い、裁定は監督が本文へ反映する (実装に渡る前なら本文へ、渡った後なら訂正註で追記する。§1.8 の 57)。
- **コードレビュー 1 回** (WP-1 に対して。観点は §2.5)。
- **受け入れ監査 1 回** (実装担当ともレビュー担当とも別の起動)。**Class D の手順が求めるもので省かない** (`RM` §9 の 8)。観点には **(a) F-16 の判定が不変であることの独立確認、(b) F-18 が「必要条件」としてのみ主張されていること、(c) `security/` の主張と実挙動の突合 (主張 vs 実測)** を含める。

---

## 7. 記録 (統合時に監督が埋める。§1〜§6 の本文は書き換えない)

- (空)

### 7.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-23)】同型 pin の件数 (D-4、§2.2 の 12)。** 起草時の「143 → 146」は基点のずれ (R-90 が 150 にした) と、コードレビュー 1 の指摘 4 (同名 helper `_count_registered_applications`・`_read_connection_headroom_settings`・`HeadroomReport` も §1.5 の 38 で pin) の裁定で **150 → 156 (6 行)** になった。件数 pin のテスト名 8 箇所と `security/CONTROL_MAPPING.md:681` (F-17 の証拠名、旧行は履歴へ) を 156 に。
- **【訂正註 2 (2026-09-23)】D-1 の限界 (d)。** MitateDB の control plane の起動時判定は自 process の `MITATEDB_MAX_CONCURRENCY` で application 1 組の床を計算する (F-16 の起動時判定と同じ既知性質)。data plane と値が食い違えば別の床を判定する — コードは変えず、MitateDB の主張行 2 本目と runbook の段落で開示した (コードレビュー 1 の指摘 5 の裁定)。
- **【訂正註 3 (2026-09-23)】版数行の位置参照。** 確定文の初版は裸の `:651`/`:739` を含み、R-88 の位置参照検査が preamble の裸 `:N` を「path なし」として赤にした。版数行は行番号を持たない形に改めた (allowlist は触らない)。
- **【訂正註 4 (2026-09-23)】§4.2 の `:744` (0014 の主張)。** 受け入れ監査の疑義 (主語の曖昧さ) を Update convention で in place に明確化した (「read only by `ops inventory` item (8)」の主語は倍化した `CONNECTION LIMIT`、F-18 は宣言と床を読む)。旧行は履歴へ。
- **【監督裁定 1】** コードレビュー 1 (中 5・低 3) の裁定は `$SP/r91-return-1.md`: 上界と予約枠を値で観測 (追加変異 M-A/M-B)、ヘッダコメントを現在形に、起動 4 テストは `code == "F-18"`、欠落 GUC は `PlatformDeclarationError(code="F-18")` (M-C)。**【監督裁定 2】** 受け入れ監査 (未充足 = HISTORY の題の件数、コメントの「three」、r2db 主張の「four composition roots」(監督の確定文の誤り、`both` に訂正)、runbook の証拠テスト名と終了コード、`:744`、M11b の再実行) は `$SP/r91-return-2.md` で全件反映。**【監督裁定 3】** 監査の疑義: 両 runbook 段落の冒頭が逐語共有される点は同型の検査を同じ語で述べる意図であり据え置き。`change_class.py` が `MitateDB-api/docs/cloud-run-cloud-sql.md` に分類行を出さない点は道具の盲点として台帳の R-100 に起票。

### 7.2 実施と受け入れ

- **差分**: 両 peer の `platform_declarations.py` (`headroom_lower_bound`・`check_max_connections_headroom`・`_f18_message`・`_count_registered_applications`・`_read_connection_headroom_settings`・`HeadroomReport`。F-16 のコードは差分 0)、両 peer の `ops.py` (`verify-declarations` の F-18、exit 17、F-15 の早期 return の後、OK 行に下界/上界/予約枠/`max_connections`)、r2db `main.py`・`control_main.py` / MitateDB `main.py`・`control_composition.py` (起動時の配備全体の下界判定)、両 peer の `tests/test_ops_verify_declarations.py` (赤/緑/偽 cursor/欠落 GUC/exit 表)、起動系 4 テスト、`test_process_ceilings_declaration.py` (`{5,5}` → `{2,2}`、下界 720 → 288)、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` +6、150 → 156)、runbook 2 本 (r2db F-16 段落の直後に F-18 段落; MitateDB の算式段落を「一つの算式」に書き換え + F-18 段落)、`security/CONTROL_MAPPING.md` (版 **2.25**: SI-08 r2db-api に F-18 主張 1 本、SI-08 MitateDB-api に 2 本を追記、`:681` と `:744` を in place)、`security/CONTROL_MAPPING_HISTORY.md` (旧 2 行を逐語)。`tools/change_class.py` → 最上位 **D**。
- **道具の出力行**: `pt: 416 passed` (対象 8 ファイル、差し戻し 1 後)、`pt: 1428 passed` (`r2db-api/tests`)、`pt: 1444 passed, 2 subtests passed` (`MitateDB-api/tests`)、`pt: 17 passed` (`test_c26_composition_root.py`)、`pt: 195 passed` (register + 両 peer `test_audit_query.py`、最終)。変異 `mutate: 25 mutations, 25 as expected` (M1〜M11b)、`mutate: 6 mutations, 6 as expected` (M-A/M-B/M-C × 両 peer)、`mutate: 1 mutations, 1 as expected` (M11b を 156 で再実行)。`tools/check_control_mapping_split.py --base 088be85 --expect "missing=2 added=5 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` 終了 0。来歴 `--base 088be85` は 8 src とも §4.1 (1) のみ、`--register` OK。`check_doc_refs` 0、`public_value_scan` 0。ブロック長 (register 実測) SI-08 r2db 既定 10,610 / MitateDB 既定 9,184、最長物理行 1,385。
- **設計レビュー 1** (重大 3・中 4・低 4、全件反映 — 需要モデルを上界から**下界**に改めた。§1.6)、**コードレビュー 1** (中 5・低 3、差し戻し 1)、**受け入れ監査 1** (未充足 → 差し戻し 2 で全件解消)。
- **完了ゲート** (監督単独): 差し戻し 2 前の木 `gate: 3976 passed, 2 subtests passed in 333.94s (0:05:33)`、`judge=PASS`; 最終の木 (`--label r91b`): `gate: 3976 passed, 2 subtests passed in 333.59s (0:05:33)`、`judge=PASS`、差分 0。実行クラスタ差分 0 (直前の main 3952 + 24)。
- **最終判定**: 受け入れ。Class D の決定 (F-18 の追加 = `security/CONTROL_MAPPING.md` 2.25 の主張 3 本の追記と 2 行の訂正、同型 pin +6) は 2026-09-19 の委任の下で監督が下し、引き継ぎ書で依頼者へ事後報告する。台帳 R-91 を閉じ (v1.101)、R-100 を起票した。
