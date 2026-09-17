# MitateDB platform の読み取り専用 inventory 設計メモ（v0.10）

- 状態: **設計レビュー 2 回反映済み、依頼者裁定済み（2026-09-16、§6 冒頭）。作業指示書の起草待ち。** ~~設計レビュー 2 回反映済み、依頼者判断待ち（Q-1〜Q-7）。~~ 本書の手順はまだ実行してよい手順ではない。本番を読むのは、本書の経路が設計レビューで受け入れられた後である（`docs/work-orders/HANDOVER_20260916_FABLE2.md` 付録 C の制約）。
- 台帳: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-45**（v1.50）。起票物は `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` の手順 1。
- 基点コミット: main `2748880`。既存コードはファイル名と関数名・CLI サブコマンド名で引き、行番号で引かない（D-6）。
- Mitate 側の正本（読み取り専用）: `../Mitate/docs/design/data-service-operation-depth-platform-upgrade.md` v1.2 §3〜§6（以下「Mitate 設計」）、`../Mitate/decisions/DM-0052-data-service-platform-upgrade-for-operation-depth.json`。
- 公開規律: 実ホスト名・プロジェクト ID・インスタンス名・digest の実値・DSN を置かない（`docs/work-orders/OPERATING_CONDITIONS.md` §1.9 の 60・61、§2 の 13）。本書の値はすべて形（`<revision>` 等）か合成値である。
- 本書で条項番号だけを書くとき（「§1.5 の 32」等）は `docs/work-orders/OPERATING_CONDITIONS.md` の条項を指す。
- 改版:
  - v0.1（2026-09-16）起票。
  - v0.2（2026-09-16）起草担当の疑義への監督裁定 Z-1〜Z-4・Z-6 を反映した（裁定文は §9.1 に逐語）。Gate-0 を 10 項目に広げ、blocker 対応表を置き直し、例外出力の修正を両 peer に掛け、`inventory` を MitateDB-api のみに置き、番兵を DSN の 4 要素に置き、変更クラスを C に改め、§6 に Q-4 を足した。
  - v0.3（2026-09-16）設計レビュー 1 回目（§10）の指摘をすべて反映し、監督裁定 Z-7〜Z-17 を §9.2 に逐語で置いた。主な変更: 判定の定義と `remediation-required` の注記（§1.2）、漏洩経路の棚卸しと番兵の経路（D-2）、DSN の受け渡しと証跡の置き場所（D-10・D-11）、全接続の読み取り専用（D-3）、(8) の式と env を既定値で補わない規則、(1) の突き合わせ、gcloud の対話の無効化（D-1）、変更クラスを D に再度改めた（D-7）、blocker 対応表の漏れを埋めた（D-8）、§6 の両論の欠点の補足と Q-5 の追加、§7 の表の作り直し。
  - v0.3 追補（2026-09-16）起草担当の疑義への監督裁定 Z-18〜Z-23 を §9.2 に逐語で足し、ON_ERROR_STOP の 2 層（§7 の 45a〜45c）、env の値の許可表（D-1）、(8) の式（D-1）、Z-5 の欠番の理由（§9.1）、Q-4 (c)・Q-5 の採用（§6）、`inventory` 自身の接続を予約枠に含める規則と §7 の 35 の復活（Z-23）を本文・§7・§8 に合わせた。
  - v0.4（2026-09-16）設計レビュー 2 回目（§10）の指摘をすべて反映し、監督裁定 Z-24〜Z-33 と WP 分割の指示を §9.3 に逐語で置いた。主な変更: 出力を stdout の 1 経路に限り dbname の番兵の扱いを分けた（D-2・D-11、Z-24）、Mitate への報告語の対応（§1.2、Z-25）、(1) を接続名と unix socket の path の比較に改めた（D-1、Z-26。Z-14 の案を覆した）、(8) の式を作り直した（D-1、Z-27。Z-20 を覆した）、読み取り専用を接続の単位に改め spy で全接続を検査する（D-3、Z-28）、(7) の env の継承（D-1、Z-29）、存在しない role / database の 2 経路（D-2、Z-30）、Q-1・Q-2 に案 (c)（Z-31）、Q-6（Z-32）と Q-7、§7 の表の更新（Z-33）、§9 の覆った裁定への註、§11 の WP 分割案。
  - v0.4 追補（2026-09-16）起草担当の疑義への監督裁定 Z-34〜Z-36 を §9.3 に逐語で足し、(1) の Cloud SQL Auth Proxy の unix socket モードの前提（D-1、§7 の 9b、§8）、起草担当の対応の採用（Q-1 (c)・Q-5・Q-7・§7 の 2a・45a′）、(8) の対象 role の確定規則（D-1、§7 の 34c、§8）を本文・§7・§8 に合わせた。
  - v0.5（2026-09-16）§6 の Q-1〜Q-7 に依頼者裁定を逐語で記録した（すべて監督の推奨を採用）。本文の決定・§7 は変えていない。
  - v0.6（2026-09-16）末尾に §12（WP-A の実施記録）を足した。本文の決定は変えていない。
  - v0.7（2026-09-17）§12.2（WP-C の実施記録）を足した。本文の決定は変えていない。
  - v0.8（2026-09-17）§12.3（WP-B の実施記録）を足した。本文の決定は変えていない。
  - v0.9（2026-09-17）§12.4（WP-E の実施記録）を足し、WP-E で覆した D-1 の (6)・(8)、§7 の 33b、§12.3 の該当記述に打ち消し線と註を入れた（§1.8 の 56）。
  - v0.10（2026-09-18）§12.5（WP-F の実施記録）を足し、WP-F の F2 で覆した D-1 の (6) の「`statement_timeout` の有無を読む」の記述に【訂正】を入れた（§1.8 の 56。行は消していない）。本文の他の決定は変えていない。

## 1. 問題

Mitate 設計 §3 の Gate-0 を、秘密を出力せず、本番の状態を変えずに判定する経路が無い（R-45 の起票文）。本書はその経路を定める。

### 1.1 Gate-0 の 10 項目

(1)〜(7) は v0.1 の番号を保つ。(8)〜(10) は v0.2 で足した（裁定 Z-3）。

| # | 項目 |
|---|---|
| (1) | isolated / production の組 |
| (2) | platform declarations |
| (3) | migration とアプリケーションごとの upgrade 状態 |
| (4) | credential registry の参照。**DB の credential registry 表**を指す（v0.3、裁定 Z-9）。Secret Manager 側の参照は (9) で読む |
| (5) | rollback の可逆性 |
| (6) | DDL のロックと停止時間の上限（maintenance window の要否を含む。v0.3、裁定 Z-17） |
| (7) | 旧式 base URL 設定（`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`）の有無。現行 revision / template に残るのは解消対象、新 candidate / 次 template に残るのは blocker（Mitate 設計 §3 の 5、裁定 Z-14・Z-29） |
| (8) | 接続数の余力（式は D-1、裁定 Z-27） |
| (9) | source → build input → digest → revision の一意な対応と、直前 Ready の rollback revision の存在・Ready / health・traffic の割り当て、revision が参照する secret の env 名ごとの存在・状態。build 来歴を attest できなければ unknown |
| (10) | 必要な migration / declare / upgrade の再実行性・冪等性と順序。本番を読まず、候補 HEAD のリポジトリ側の証拠で判定する |

### 1.2 判定の形（v0.3 で定義を追加、裁定 Z-14。v0.4 で報告語の対応を追加、裁定 Z-25）

| 判定 | 定義 |
|---|---|
| **confirmed** | 状態を一意に読めた。読めた値は既知の解消対象を含んでよい |
| **blocked** | Mitate 設計 §3 の真の blocker 1〜5 に当たる |
| **unknown** | 読めない、読む前提の入力が無い、射影が空、権限・API・対話の都合で読めなかった |

- 各項目の出力は判定に加え、観測した不足が既知の解消対象（Mitate 設計 §3）であれば **`remediation-required`** の注記を持つ。注記は先へ進めるための作業項目であり、blocker ではない。
  - 例: (3) で 0011 が未適用 = confirmed + `remediation-required`。(7) で現行 revision / template に旧 env = confirmed + `remediation-required`。(7) で新 candidate / 次 template に旧 env = blocked。
- **unknown は先へ進まない（fail-closed）。** warning として続行しない（§5 の却下案 4）。
- **Gate-0 の全体判定は、10 項目すべてが confirmed のときだけ ready** とする。全体判定は DB 層と platform 層を合わせる runbook の手順で出す。`inventory` CLI は DB 層の判定だけを出し、全体の ready を出さない（裁定 Z-15）。
- **Mitate への報告（D-11）では、unknown と blocked をどちらも `blocked—platform remediation required` に写し、内訳（unknown / blocked）を併記する。confirmed だけが通過になる**（裁定 Z-25）。これは依頼（付録 C「やること」の 2）の「不明の状態を fail-closed で blocked と報告する」に当たる。

## 2. 守るべき条件

- **C1** DSN・credential・token・credential を含む URL・HTTP 本文・実データを、成功・失敗・例外のどの経路でも stdout / stderr / ログ / 証跡ファイルに出さない。**operator 手順（DSN の取得と受け渡し）も C1 の範囲に入る**（v0.3、裁定 Z-8）。
- **C2** 読み取り専用。本番の状態を変えない（DDL・DML・宣言の置換・restart・traffic 変更・API の有効化をしない）。
- **C3** 状態不明を confirmed に丸めない。
- **C4** 共通 spec・Mitate の契約・F9 ゲートを変えない。
- **C5** 公開リポジトリに実値（ホスト名・プロジェクト ID・インスタンス名・digest の実値）を置かない。設計・テスト・fixture は合成値のみ。

## 3. 現状（基点 main `2748880`、静的読解のみ。本番は読んでいない）

| 項目 | 既存の手段（ファイル / 関数 / サブコマンド） | 本書に関わる事実 |
|---|---|---|
| (1) | `MitateDB-api/src/mitatedb_api/ops.py` の `show-declarations`（`cmd_show_declarations`）が `surfaces` 行（Data / Control の base URL）を出す | DB インスタンスを秘密なしに識別する既存サブコマンドは見つからない。Cloud Run の revision / digest を読むラッパーはリポジトリに無い。Cloud Run の組み込みの Cloud SQL 接続は unix socket を `/cloudsql/<接続名>` に置く（runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §5）。runbook の operator 向け `psql` の例は `host=127.0.0.1`（Cloud SQL Auth Proxy 経由）の形である |
| (2) | `show-declarations`、`verify-declarations`（`cmd_verify_declarations` → `_verify_declarations_checks`） | どちらも `MITATEDB_PROVISION_DSN` で接続する。出力の payload に DSN のキーは無い。F-14 は `_served_capabilities_document`（operator の process env と手元のコードで作る文書）を、F-16 の下限は `_declared_concurrency`（`MITATEDB_MAX_CONCURRENCY` が未設定・不正なら既定値に戻る）を使う |
| (3) | `upgrade-status`（`cmd_upgrade_status`）。migration 0007 / 0011 の適用有無は `show-declarations` の "table does not exist" 文言と `verify-declarations` の F-8 / F-15 から間接に読める | `cmd_upgrade_status` はアプリケーション DB への接続失敗（`except psycopg.Error`）を `applied=()`・全件 pending として扱う。`_registry_applications_for_upgrade(application_id=None)` は `database_name IS NULL`（登録のみ）の application を除く。`platform_upgrades.read_applied_upgrade_numbers` は台帳の表が無いとき `conn.rollback()` を呼ぶ |
| (4) | `list-credentials`（`cmd_list_credentials`）、`list-applications`（`cmd_list_applications`） | どちらも `_actor_credential` による control credential の入力を要する。registry の表 `mitatedb_registry.credentials` / `control_credentials` は `digest` 列（credential の派生値）を持つ（`MitateDB-api/migrations/0002_registry_and_functions.sql`）。bearer は `<credential_id>.<secret>` の形で、`credential_id` は bearer の前半である（`credential_wire.compose_bearer_locator`） |
| (5) | 無し | `MitateDB-api/migrations/` は 0001〜0012 のみで down 用のファイルは無い。`platform_upgrades` の `cleanup_sql` は権限の後始末であり、スキーマの巻き戻しではない |
| (6) | 無し | §4 D-5 の表 |
| (7) | `MitateDB-api/src/mitatedb_api/platform_declarations.py` の `REMOVED_SURFACE_ENV` と `reject_removed_surface_env`（定義されていれば空文字でも起動を拒む） | 現行の runbook §6.1 / §6.2 の deploy 例に 2 変数は無い。稼働中 revision の env を読む手段はリポジトリに無い。runbook には `--set-env-vars`（全置換）と `--update-env-vars`（現行 template の env を引き継ぐ）の両方の形が現れる |
| (8) | `verify-declarations` の F-16（`platform_declarations.check_role_connection_limits`）、`process_ceilings` 宣言（F-15）、`mitatedb_api.config.role_pool_size` | role の種類ごとの process あたり接続数は `0012_role_connection_limits.sql` の見出し註にある: `mitatedbsvc_api` = 2 × concurrency、`mitatedbsvc_controlplane` = 16（固定）、`mitatedbsvc_auditreader` = 4（固定）、各アプリケーションの `<id>_rt` / `<id>_dv` = 1 × concurrency（同じ concurrency の上限に縛られる）。`mitatedbsvc_provision` は CLI の短命な接続だけを使う。F-16 は +4 の余裕を含まない下限で比べる。runbook は `process_ceilings` の宣言値を `--max-instances` と一致させることを求めるが、アプリケーションからは検証できないと書く。`MitateDB-api/src/mitatedb_api/` に `max_connections` を読む箇所は見つからない（grep） |
| (9) | 無し | build 来歴・revision・traffic・secret 参照を読むラッパーはリポジトリに無い |
| (10) | `MitateDB-api/tests/test_migration_0007_ddl.py` の `test_0007_alter_role_and_table_creation_are_idempotent` | 0011 / 0012 を再適用するテストは同じ grep では見つからない（未確認）。順序は runbook §3.2b の本文（0007 → 0011 → `declare-process-ceilings`、0012 は順序に依らない）にある。0007 と `ops._upsert_declaration` は `updated_at = now()` を書く。運用で psql を呼ぶ `ops.py` の `_run_upgrade_script` と `_run_deprovision_script` は argv に `-v ON_ERROR_STOP=1` を渡す。各テストファイルの `_run_psql`（例: `MitateDB-api/tests/test_ops_verify_declarations.py`）も同じ形である。migration ファイル自身も `\set ON_ERROR_STOP on` を持つ。runbook の 0007 / 0011 / 0012 の適用例は `-v ON_ERROR_STOP=1` を持たない |

### 3.1 C1 の漏洩経路（静的な事実。v0.3 で棚卸しを拡げた、裁定 Z-7。v0.4 で role / database の 2 経路を追加、裁定 Z-30）

設計レビューの probe（合成値、§10）で次を確かめた:

- libpq / psycopg の conninfo 解析エラーは DSN の断片をそのまま引用する（URI の password に生の `%` があると password の断片が載る、sslmode・port の値も載る）。
- 接続できない host は host 名が載る。
- **正しい形の DSN でも、存在しない role は `role "<user>" does not exist`、存在しない database は `database "<dbname>" does not exist` として user・dbname が載る**（2 回目）。
- **正しい形の DSN で接続に失敗したときは、password は例外文字列に載らない。**

| 経路 | 場所（ファイル / 関数） | 出るもの |
|---|---|---|
| 接続失敗 | `cmd_verify_declarations`（両 peer） | `print(f"error: cannot connect to platform database: {exc}", ...)` で例外文字列 |
| psycopg 例外全般 | 両 peer の `main()` の `except psycopg.Error` | `print(f"error: database operation failed: {exc}", ...)` で例外文字列。`cmd_show_declarations` / `cmd_upgrade_status` の未捕捉の接続例外はここに落ちる |
| psycopg 以外の例外 | 両 peer の `main()` まで上がる例外（例: `_app_dsn` の `conninfo_to_dict` は try の外） | traceback と例外の文言 |
| upgrade の失敗詳細 | MitateDB-api の `_upgrade_one_application` の `failure_detail=str(exc)`、`_run_upgrade_script` の psql の stdout / stderr（`_print_upgrade_results` が出す）。r2db-api の `failure_detail`（psql 出力の末尾） | 例外文字列、psql の出力 |
| argv | `_run_upgrade_script`（psql の argv に DSN を渡す） | `ps` に DSN が見える |

## 4. 決定と根拠

### D-1 二層に分ける

| 層 | 扱う項目 | 形 |
|---|---|---|
| DB 層 | (1) の DB 側の比較、(2)(3)(4)、(5) と (6) の宣言の有無、(6) の実行時設定部分、(8) の DB 側の入力と計算 | MitateDB-api の ops CLI に読み取り専用のサブコマンドを新設する（名前の案: `ops inventory`。置き場所は D-9）。**DB 層の判定だけを出す** |
| platform 層 | (1) の Cloud SQL 接続名、(5) の revision 部分、(7)、(8) の process 数（`max-instances` 等）と許可表の env の値、(9) | Cloud Run / Artifact Registry / Secret Manager の読み取りを、**出力フィールドを明示的に射影する** operator 手順として runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` に置く |
| リポジトリ側の証拠 | (10) | 本番を読まない。候補 HEAD のテストで confirmed にする（裁定 Z-3） |
| 全体判定 | Gate-0 の ready と Mitate への報告 | DB 層と platform 層を同じ実行で読み、合わせて出す runbook の手順（§1.2） |

#### DB 層（案）

- 接続は既存と同じ `MITATEDB_PROVISION_DSN` だけを**環境変数で**読む。DSN を argv で受け取らない（D-10）。新しい環境変数を足さない。
- 接続はすべて 1 つの factory で開き、接続の単位で読み取り専用にする（D-3）。
- **出力は stdout の 1 経路に限る**（裁定 Z-24。D-11）。終了コードは、DB 層の全項目が confirmed のときだけ 0、それ以外は 0 以外とする（値は作業指示書で固定する。裁定 Z-35）。
- 既存サブコマンドとの関係: `show-declarations` / `verify-declarations` / `upgrade-status` は残し、振る舞いを変えない（D-2 の例外出力の変更を除く）。`inventory` はそれらが使う読み取り関数（`platform_declarations` の読み取り・検査関数、`_registry_applications_for_upgrade`、`platform_upgrades.read_applied_upgrade_numbers`）を呼び、項目ごとに判定・注記と非秘密の値だけを出す。`show-declarations` のような行の生値の表示は `inventory` の責務にしない。
- **operator の process env と手元のコードに依存する検査（F-1 / F-2 / F-6 / F-14 の capabilities 部分 / F-16 の下限）を confirmed の根拠にしない。** 使うときは入力（concurrency 等）を明示の引数で受け取り、**無ければ既定値で補わず unknown** とする（v0.3、裁定 Z-13）。
- (1):
  - ~~接続先の秘密でない識別子（例: `current_database()` とクラスタの system identifier）を出す。platform 層の Cloud SQL 接続先と突き合わせる（裁定 Z-14）。値は証跡にだけ残す（D-11）。~~ **【v0.4 で置換 2026-09-16、裁定 Z-26】** 根拠: platform 層の接続名と DB 層の識別子に共通のキーが無く比較できない。DB 名の一致で代用すると代理指標になる（§1.7 の 52）。`current_database()` を出すと成功経路の dbname の番兵と両立しない（設計レビュー 2 回目の B-1・M2）。
  - `inventory` は、platform 層が revision から読んだ Cloud SQL の接続名を引数で受け取り、DSN の接続先（Cloud SQL の unix socket の path）がその接続名を指すかをツール内部で比べ、**`match` / `mismatch` / `unknown` だけ**を出す。接続先そのものは出さない。比べられない形の DSN は unknown（裁定 Z-26）。
  - DB 名は credential ではなく識別子であり、(1) の識別フィールドにだけ現れてよい（裁定 Z-24）。
  - **`inventory` の DB 層は Cloud SQL Auth Proxy を unix socket モードで使うことを runbook の前提にする**（socket の path に接続名が現れる）。TCP（loopback）経由の DSN では接続先をインスタンスに結び付けられないので (1) は unknown のままとし、runbook にその理由を書く（裁定 Z-34）。
- (3): アプリケーション DB への接続失敗・読み取り失敗（`read_applied_upgrade_numbers` が `UndefinedTable` 以外の `psycopg.Error` を送出する場合を含む）は unknown とする（`cmd_upgrade_status` の pending 扱いを引き継がない。C3）。登録のみの application は件数と状態で出す。未適用の migration・upgrade は confirmed + `remediation-required`（§1.2）。
- (4):
  - ~~registry は列を明示して読み、`digest` 列を読まない・出さない（C1）。出すのは `credential_id`・`application_id`・`role`・`enabled`・`revoked` 等の参照と状態だけとする。~~ **【v0.3 で置換 2026-09-16、裁定 Z-9】** 根拠: `credential_id` は bearer の前半であり（§3）、§1.9 の 61 が実 credential_id を公開物に禁じ、SI-10 は列挙を助ける区別を保護対象に挙げる（設計レビュー 1 回目の指摘 3）。
  - 出力は**件数と状態（enabled / revoked / must_rotate 等）の集計だけ**とし、`credential_id` を出さない。registry は列を明示して読み、`digest` 列を読まない。出力の key と `cursor.description` の列名が許可リストに一致することをテストで固定する。
  - 読む権限の取り方は §6 Q-4。権限が無ければ unknown とし、権限を足して読みに行かない（裁定 Z-6）。
- (5)・(6) の宣言部分: `inventory` の (5)・(6) の判定関数が、互換性・ロックの機械可読な宣言の有無を読む。宣言の形は §6 Q-1・Q-2 で決まるので、決まるまでは宣言が無く unknown を返す（設計レビュー 2 回目の m1）。
- (6) の実行時設定部分: 対象ロールの `CONNECTION LIMIT` と、ロール設定（`pg_db_role_setting`）の `statement_timeout` ~~/ `lock_timeout`~~ の ~~有無~~ を読む。 **【註 2026-09-17】WP-E で覆した。根拠は作業指示書 §6A.1 の依頼者裁定 (b) と §6A.3 の E1。現行は §12.4** **【訂正 2026-09-18】WP-F の F2 で「有無を読む」を覆した。読むのは設定の「値」であり、正の値だけが confirmed、0・負・解釈できない値は blocked（固定語 `statement-timeout-unbounded`）、設定が無いときだけ unknown である。根拠は作業指示書 §6B.1 の依頼者裁定と §6B.2 の F-R5・F-R26、§6B.9 の F2。現行は §12.5**
- (8) の式（v0.3、裁定 Z-13）: ~~（以下の 4 行）~~ **【v0.3 追補で置換 2026-09-16、裁定 Z-20】** 根拠: 需要を role ごとに見るか process ごとに見るかが文言から一意に読めなかった（起草担当の疑義 3）。旧式にあった「`inventory` 自身の接続数の差し引き」は Z-20 の式に含まれないので一度外し、裁定 Z-23 で予約枠に含めて数える形に戻した。
  - ~~入力: `SHOW max_connections`、各 role の `CONNECTION LIMIT`、`process_ceilings` 宣言、process あたりの接続数（明示の引数）。~~
  - ~~需要の上限: 各 role について、宣言された process ceilings から見た接続数を、**traffic 移行中は新旧 revision の合計**として数え、role の `CONNECTION LIMIT` を超えない範囲で合計する。~~
  - ~~供給: `max_connections` から予約枠と、計測時の `inventory` 自身の接続数を差し引いたもの。~~
  - ~~どの role かの `CONNECTION LIMIT = -1`（無制限）は余力を計算できないので unknown。`max_connections`・宣言・入力のどれかが読めなければ unknown。~~
- (8) の式（裁定 Z-20）: ~~（以下の 5 行）~~ **【v0.4 で置換 2026-09-16、裁定 Z-27】** 根拠: process あたり接続数は role の種類ごとに違い、アプリケーション role は concurrency の上限を共有する。`CONNECTION LIMIT = -1` の対象 role の範囲が無く、クラスタの組み込み role で常に unknown になる。`process_ceilings` は宣言値で実際の `max-instances` と食い違いうる（設計レビュー 2 回目の M3）。
  - ~~入力: `SHOW max_connections`、各 role の `CONNECTION LIMIT`、`process_ceilings` 宣言（process 数）、process あたり接続数、予約枠。~~
  - ~~条件 1（role ごと）: 「新旧 revision の process 数 × process あたり接続数」の合計が、その role の `CONNECTION LIMIT` 以下。~~
  - ~~条件 2（全体）: 全 role の合計 + 予約枠が `max_connections` 以下。~~
  - ~~予約枠には `inventory` 自身の接続を含める。予約枠の出所には「`inventory` が同時に開く接続の最大数」を含め、この数はツールの定数として固定し、静的テストで pin する（裁定 Z-23）。~~
  - ~~予約枠と process あたり接続数の出所が確定しなければ unknown。どの role かの `CONNECTION LIMIT = -1`（無制限）、`max_connections`・宣言・入力のどれかが読めないときも unknown（裁定 Z-13）。~~
- (8) の式（裁定 Z-27。Z-23・Z-13 は引き継ぐ）:
  - **対象 role**: Data / Control の process が使う全 role。`0012_role_connection_limits.sql` の見出し註による列挙は `mitatedbsvc_api`・`mitatedbsvc_controlplane`・`mitatedbsvc_auditreader`・serving 中の各アプリケーションの `<id>_rt` / `<id>_dv` である。
  - **`mitatedbsvc_provision` は process の role ではないので対象外**とし、`inventory` 自身の provision 接続は予約枠（Z-23）で数える。**`mitatedbsvc_auditreader` をどの process が使うかは実装 WP の着手時にコード（関数名）で確定し、確定するまでは Data と Control の両方で数える**（多めに数える側に倒す）（裁定 Z-36）。
  - **process 数**: `process_ceilings` の宣言値ではなく、platform 層が読んだ実際の上限（`max-instances` 等）を使う。~~traffic 移行中は新旧 revision の合計とする。**宣言と実際が食い違えば blocked。**~~ **【註 2026-09-17】WP-E で覆した。宣言との比較は各 revision 単体の上限で行い、新旧の合計は余力の計算にだけ使う（入力を 4 つの引数に分け、合計が単体の上限より小さい入力は拒否する）。根拠は作業指示書 §6A.3 の E2 と §6A.2 の E-R4。現行は §12.4**
  - **process あたり接続数**: role の種類ごとに、コードの定数（pool の大きさ等）を出所として関数名で引く（`mitatedb_api.config.role_pool_size`、`mitatedb_api.platform_declarations.check_role_connection_limits`）。concurrency は許可表の env の値（D-1 platform 層）から与える。
  - **条件 1（role ごと）**: 「新旧 revision の process 数 × その role の process あたり接続数」が、その role の `CONNECTION LIMIT` 以下。
  - **条件 2（全体）**: role の種類ごとの需要の和 + 予約枠が `max_connections` 以下。**concurrency の上限を共有するアプリケーション role は、共有の単位で 1 回だけ数える。**
  - **予約枠**: Z-23 のとおり。`inventory` 自身の接続を含め、その出所には「`inventory` が同時に開く接続の最大数」（ツールの定数、静的テストで pin）を含める。
  - **unknown**: 対象 role のどれかが `CONNECTION LIMIT = -1`（無制限）、`max_connections`・`CONNECTION LIMIT`・`max-instances`・許可表の env のどれかが読めない、予約枠・process あたり接続数の出所が確定しない、のいずれか。
- (1) の platform 側、(7)(9)(10) は DB 層では判定しない。

#### platform 層（案）

- revision spec 全体を describe して出力しない（§5 の却下案 2）。env の値に秘密が入りうるので、**env は名前だけ、secret は env 名ごとの存在・状態だけ**を残す。secret の名前・値は証跡に残さない（裁定 Z-9）。これは Mitate 設計 §3 が証跡に挙げる「secret name/version reference」より厳しい側への逸脱である（影響は §8）。
- 例外として、判定の入力になる**秘密でない数値設定**の env だけを明示の許可表（env 名を列挙）に置き、その値を読んで証跡に残してよい。許可表に無い env の値は読まない。許可表の env が未設定なら unknown（裁定 Z-19）。DB 層の明示の引数（concurrency 等）はこの許可表の値から与える。
- 射影する項目: service 名、revision 名、image digest、build 来歴（source ref・build input）、Ready 条件、traffic の割り当て、`max-instances`、service account、Cloud SQL の接続名、**すべての container** の env の名前、許可表の env の値、env 名ごとの secret の存在・有効な version の有無、コマンドの exit status。
- gcloud はプロンプトを無効化して実行する（`--quiet` と `CLOUDSDK_CORE_DISABLE_PROMPTS=1`）。**API が無効・権限不足・対話が要る状態は unknown** とし、API を有効化しない（C2、裁定 Z-12）。実行する principal の選び方は §6 Q-7。
- 射影が空（フィールドが読めない）のときは unknown で、「無し」と読まない。env 名の一覧が空、または必ず存在するはずの env 名を含まなければ unknown（裁定 Z-13）。
- (1) の判定: revision から読んだ Cloud SQL の接続名を `inventory` に引数で渡し、`inventory` の `match` / `mismatch` / `unknown` を (1) の判定に使う。`mismatch` は組が違うので先へ進まない（unknown と同じく報告では `blocked—platform remediation required`）（裁定 Z-26）。
- (7) の判定: 現行 revision / template に 2 変数のどちらかがあれば confirmed + `remediation-required`。新 candidate / 次 template に残れば blocked。Gate-0 の時点で新 candidate が本番に無いときは、候補 HEAD の deploy 定義（runbook §6 の deploy コマンドとそのとき渡す env）を「次 template」として読む。**deploy が既存の env を引き継ぐ形（`--update-env-vars` 等）なら、現行 revision の env 名に変更を適用した結果で判定し、旧 env の明示の削除が無ければ blocked**（裁定 Z-29）。既存 rollback revision にあるのは証跡として記録するだけで blocked にしない（Mitate 設計 §3 の 5）。
- (8) の platform 側: 新旧 revision の `max-instances` と、許可表の env（concurrency 等）の値を射影し、`inventory` に引数で渡す。
- (9) の判定: digest から source ref への対応が一意でない（同じ digest の複数 revision が異なる来歴を持つ、revision が digest でなく tag で image を参照する）、または build 来歴を attest できなければ unknown。直前 Ready の rollback revision が存在しない、または Ready でなければ blocked。
- 手順の値はすべて形（`<service>`・`<region>`・`<revision>`）で書き、実値は operator の実行時にだけ与える（C5）。

#### リポジトリ側の証拠（案、(10)）

- 使い捨てのテスト用クラスタに、0007 / 0011 / 0012、`declare-surfaces`・`declare-process-ceilings`、per-application upgrade を**それぞれ** 2 回適用する。**2 回目の適用の終了コードが 0** であることと、2 回目の前後でカタログと宣言の値の差分が 0 であることを確かめる。**比較から `updated_at` を除く**（0007 と `ops._upsert_declaration` が `now()` を書くため）。per-application upgrade は 2 回目の適用件数が 0 であることも確かめる（設計レビュー 2 回目の m2、裁定 Z-33）。
- 非冪等の変異はエラーで ROLLBACK され、カタログの差分が 0 のまま残りうる。終了コードを見ることで赤にする。
- 順序は、依存のある組（0011 は 0007 の表と制約に依存）で、依存先を欠いたときに適用がエラーで止まることを終了コードで固定する（トランザクションが ROLLBACK されるので、カタログの不変では判定しない）。`ON_ERROR_STOP` は 2 層（psql の argv と migration ファイルの `\set ON_ERROR_STOP on`）を別々に固定する（裁定 Z-18、§7 の 45a〜45c）。
- 証拠は候補 HEAD の SHA に結び付けて記録する。起点をどの状態に置くかは §6 Q-5。
- 候補 HEAD でこれらが緑であることを (10) の confirmed の根拠とする。緑の記録が無ければ unknown。

根拠: DB 層は出力の秘匿をテストで固定できる（D-2・D-3）。platform 層の読み取りは本リポジトリのコードから呼ぶ既存の経路が無く、射影を手順として固定しレビューで照合する形が C1 を満たす最小の形である。(10) は本番の読み取りでは確かめられない性質なので、リポジトリ側で証明する（裁定 Z-3）。

適用: SI-10、SI-14、T-08、T-14（C1）。T-12（C3、unknown を先へ進めない。SI-15 は操作の認可が対象で、C3 とは緩い対応に留まる）。T-12（platform 構成の宣言整合を読む）。SI-08、T-07（(8)）。T-13（(9) の build 来歴）。SI-09、T-09（(10)）。

### D-2 C1 をテストで固定する

- **番兵は DSN の user・password・host・dbname の全部に、別々の値で置く**（裁定 Z-4）。
- **4 要素それぞれについて**、その番兵が生の例外文字列に現れる失敗経路（不正な形の DSN を含む）を少なくとも 1 つ持ち、その経路で stdout / stderr に現れないことを assert する。どの経路でも前提を満たせない要素は、「漏れる経路が無いことを実測した」として根拠を記録する（v0.3、裁定 Z-7）。
- **テストは stdout と stderr の両方を見る**（出力は stdout の 1 経路に限るが、検査は両方に掛ける。裁定 Z-24）。
- **user / password / host の番兵は全経路で出力に現れない。dbname の番兵は、失敗経路では出力に現れないことを、成功経路では (1) の識別フィールド以外に現れないことを assert する**（裁定 Z-24）。
- 各失敗経路のテストは次の順に assert する（空振り防止、§1.5 の 32）。
  1. 失敗経路を実際に通ったこと（終了コードと固定文言）。
  2. **生の例外文字列に、その経路で指定した要素の番兵が含まれること。**
  3. そのうえで、stdout / stderr に番兵が 1 つも無いこと。
- 経路（v0.3 で 5 つ、v0.4 で 7 つに改めた）:

| 経路 | 番兵の置き方 |
|---|---|
| 成功 | host は接続できないと成功しないので、user / password / dbname を使い捨てのロールと DB で置く。user / password は出力に無いこと、dbname は (1) の識別フィールド以外に無いことを assert する |
| 接続失敗（正しい形の DSN、接続できない host） | host（接続できない合成名）。password は載らない（§3.1） |
| 接続失敗（正しい形の DSN、存在しない role） | user。前提 2 は **user の番兵**を名指しして assert する（裁定 Z-30） |
| 接続失敗（正しい形の DSN、存在しない database） | dbname。前提 2 は **dbname の番兵**を名指しして assert する（裁定 Z-30） |
| DSN 解析失敗（不正な形の DSN。接続前） | password（生の `%` を含む URI 形など）。前提 2 は **password の番兵**を名指しして assert する |
| 接続後の psycopg 例外 | DSN の要素は載らないので、`cursor.execute` を差し替えて番兵入りの `psycopg.Error` を送出させる |
| psycopg 以外の例外（`main()` まで上がるもの） | 番兵入りの例外を送出させる |

- **例外文字列を出力せず、例外の型名と固定文言だけを出す**方針とする。`inventory` は最上位で全例外を捕まえ、型名と固定文言だけを出す（SI-10 の Verification は unexpected exceptions を挙げる）。
- 既知の懸念（§3.1、`cmd_verify_declarations` の接続失敗経路）を直す。**`cmd_verify_declarations` は `_ISOMORPHIC_TARGETS` 登録済みなので、この修正は両 peer（`MitateDB-api/src/mitatedb_api/ops.py` と `r2db-api/src/r2db_api/ops.py`）に同じ形で入れる**（裁定 Z-1）。
- 両 peer の他の ops サブコマンドについて、例外文字列・DSN を出す経路を**実装前に棚卸し**する。見つかれば同じ方針で直す（裁定 Z-1）。棚卸しには少なくとも次を名指しで入れる（裁定 Z-7）: 両 peer の `main()` の psycopg 例外ハンドラ、`_upgrade_one_application` の `failure_detail`（両 peer）と `_run_upgrade_script` の psql 出力、psql の argv に DSN を渡す箇所、psycopg 以外の例外（traceback）。
- 変異: 生の例外文字列を出力する形に戻すと赤。

適用: SI-10、SI-14、T-08、T-14。

### D-3 C2 をテストで固定する（v0.3 で改めた、裁定 Z-11。v0.4 で機構を固定した、裁定 Z-28）

- ~~`inventory` の DB セッションは読み取り専用トランザクション（`default_transaction_read_only` 相当）で開く。~~ **【v0.3 で置換 2026-09-16、裁定 Z-11】** 根拠: psycopg の `read_only` は psycopg が発行する `BEGIN` にだけ付き、`autocommit=True` の接続には掛からない。再利用する helper はアプリケーション DB への接続を新しく開き、親の接続の設定は伝わらない（設計レビュー 1 回目の指摘 5）。
- 読み取り専用は **ツール側の性質**として定義する。**特権の境界ではない**（provision role は自分で設定を外せる。§6 Q-4 (a) の欠点）。
- ~~ツールが開く**すべての接続**（platform DB と各アプリケーション DB）で、autocommit を使わず読み取り専用トランザクションで読む。接続を開く箇所を 1 つの factory に集める。テストは「ツールが開く各接続で書き込みが拒否される」ことを実行で確かめる（platform DB の接続とアプリケーション DB の接続を別々に）。~~ **【v0.4 で置換 2026-09-16、裁定 Z-28】** 根拠: テストが明示の `transaction()` の中で書くと autocommit の変異でも拒否されて緑になり、factory から接続を取るテストは factory を通らない本体の接続を検出しない。明示の `transaction()` による実装は `read_applied_upgrade_numbers` の `conn.rollback()` と両立しない（設計レビュー 2 回目の M4・M5）。
- **読み取り専用は接続の単位で掛ける。** 接続直後にセッションの既定を読み取り専用にし、ツールの経路の中で `transaction_read_only` を読んで確かめる。確かめられない接続では読まず、その項目は unknown とする。明示の `transaction()` に依存しない（既存の `read_applied_upgrade_numbers` の `rollback()` と両立させる）（裁定 Z-28）。
- 接続を開く箇所を 1 つの factory に集める。factory 以外に `psycopg.connect` を置かない（静的検査）。
- 項目ごとに短いトランザクションで読み、`inventory` のセッションに `lock_timeout` / `statement_timeout` を設定する（長いトランザクションが registry の表のロックを持ち続けて、DDL と後続の読み手を詰まらせないため。値は作業指示書で固定する。設計レビュー 2 回目の m7）。
- テスト（裁定 Z-28）:
  - `psycopg.connect` を spy して、`inventory` が開いた**すべての**接続を捕まえる。
  - 捕まえた各接続で、**明示トランザクションの外から**書き込みを試みて拒否されることを確かめる。
  - spy で**同時に開いている接続数の最大**を実測し、Z-23 の定数以下であることを確かめる（定数の pin とは別の行）。
- 変異: セッションの読み取り専用の設定を外す・確かめる処理を外す・factory を通さずに開く・アプリケーション DB の接続を最後まで閉じない、のそれぞれで赤。

適用: SI-09、T-06、T-12。

### D-4 (5) rollback の可逆性

- down migration は存在しない（forward-only。§3）。
- 可逆性は「**直前 Ready revision が migration 適用後のスキーマで動くか**」の互換性として定義する。
- その根拠がリポジトリ内に宣言されていなければ **unknown** とする。
- confirmed にする手段は §6 Q-1 として両論で残す。

適用: SI-09（irreversible migration）、T-09、T-12。

### D-5 (6) DDL のロック

各文が取るロック種別と `lock_timeout` の有無（基点 main `2748880`）。「推測」は PostgreSQL の一般規則からの推測であり、ファイル内に明記は無い。

| migration | 文 | ロック種別 | 出所 |
|---|---|---|---|
| `0007_platform_declarations.sql`（全文が 1 つの `BEGIN` / `COMMIT`） | `ALTER ROLE ... SET` ×4 | ロールのカタログ設定の更新。利用者テーブルのロックは無い | 推測 |
| | `CREATE TABLE IF NOT EXISTS mitatedb_registry.platform_declarations` | 新規作成。既存なら作成しない | 推測 |
| | `REVOKE` / `GRANT ... ON mitatedb_registry.platform_declarations` | 未確認 | — |
| | `INSERT ... ON CONFLICT` ×2 | ROW EXCLUSIVE と行ロック | 推測 |
| `0011_process_ceilings.sql`（1 つの `BEGIN` / `COMMIT`） | `ALTER TABLE ... DROP CONSTRAINT platform_declarations_key_check` | ACCESS EXCLUSIVE | 推測 |
| | `ALTER TABLE ... ADD CONSTRAINT ... CHECK (...)` | ACCESS EXCLUSIVE。既存行の検証の走査を伴う | 推測 |
| `0012_role_connection_limits.sql` 第 1〜2 部（1 つの `BEGIN` / `COMMIT`） | `ALTER ROLE ... CONNECTION LIMIT` ×2 | ロールのカタログ更新 | 推測 |
| | `DO` ブロック（`mitatedb_registry.applications` を `SELECT` し、ロールごとに `ALTER ROLE ... CONNECTION LIMIT`） | `applications` に ACCESS SHARE、各ロールのカタログ更新 | 推測 |
| `0012` 第 3 部（`COMMIT` の後、トランザクションの外） | `CREATE OR REPLACE FUNCTION mitatedb_registry.begin_provision_application`、`REVOKE ... ON FUNCTION` | 未確認 | — |

- **3 ファイルとも `lock_timeout` の設定は無い**（事実、grep）。0007 の `statement_timeout` は `api_role` / `controlplane_role` のロール既定値であり、migration を実行するセッションの上限ではない（事実）。
- 停止時間の上限と maintenance window の要否（Mitate 設計 §6）を機械可読に宣言したものは無い。**機械可読な宣言が無ければ unknown** とする。
- confirmed にする手段は §6 Q-2 として両論で残す。

適用: SI-08、T-07（接続・DB 容量の上限）、T-12。

### D-6 既存コードの引き方と実装の時期

- 既存コードは行番号ではなくファイル名と関数名・CLI サブコマンド名で引き、基点コミットを本書冒頭に記録する（基点: main `2748880`）。
- roadmap R-37 の WP-5（`docs/work-orders/HANDOVER_20260916_FABLE2.md` 付録 B）が MitateDB-api の `backend_postgres.py` と `config.py` を動かすので、**実装は WP-5 の統合後**に始める。

適用: 該当なし（作業順の決定）。

### D-7 変更クラスとレビュー回数

- ~~変更クラスは D の見込み。最終判定は `RM` §9 の 8 の表で行う。共通契約を触らないので設計レビューは 1 回とする。~~ **【v0.2 で置換 2026-09-16、裁定 Z-2】** 根拠: D-2 の修正は `_ISOMORPHIC_TARGETS` 登録済み helper（`cmd_verify_declarations`）の本体を変える。`RM` §9 の 8 の表は触れるファイルの集合で機械的に決まり、この変更は C に当たる。`security/`・`CLAUDE.md`・公開ゲートには触れないので D ではない。
- ~~変更クラスは Class C（`RM` §9 の 8 の表に機械的に従う）。設計レビューは 2 回。契約（spec）は変えないので、契約版数は 1.8.0 のままとする（前例: R-44 の WP-3）。本番の更新（後続の WP）のクラスは、後続の設計で改めて判定する。~~ **【v0.3 で置換 2026-09-16、裁定 Z-16・Z-17】** 根拠: 両 peer に同名で足すテストは §1.5 の 38 により `_ISOMORPHIC_TARGETS` に登録するので、集合が増え `RM` §9 の 8 の表の D に当たる。新しい統制は `security/CONTROL_MAPPING.md` に対応付けるので `security/` 配下にも触れる（設計レビュー 1 回目の指摘 10）。
- 変更クラスは **Class D**（`RM` §9 の 8 の表に機械的に従う）。**依頼者裁定を要する。** 設計レビューは 2 回。
- 契約（spec）は変えないので、**契約版数は 1.8.0 のまま据え置く**。これは `RM` §9 の 8 の C / D の証拠に含まれる「契約版数の更新」からの逸脱であり、**依頼者の確認を要する**（前例: R-44 の WP-3）。裁定の出所は §9.2 の Z-17。
- D の証拠の「版付きの security-contract 決定」を何で満たすかは §6 Q-6 とする（裁定 Z-32）。
- 本番の更新（後続の WP）のクラスは、後続の設計で改めて判定する。

適用: 該当なし（手続きの決定）。

### D-8 Mitate 設計 §3 の真の blocker との対応

**v0.2 で置き直し、v0.3 で漏れを埋めた（裁定 Z-3・Z-17）。** blocker の各要素を本書の項目に対応させ、対応の無い要素を残さない。「読める部分」は Gate-0 の読み取りで確かめ、「isolated で初めて証明される部分」は Gate-0 の後段（isolated での実施）の証拠に委ねる。

| blocker | 要素 | Gate-0 で読める部分（本書の項目） | isolated での実施で初めて証明される部分 |
|---|---|---|---|
| 1 | source → build input → digest → revision を**一意に** attest | (9)（同じ digest の複数 revision・tag 参照は unknown） | — |
| 1 | isolated / prod の組の attest | (1)（接続名と unix socket の path の比較、裁定 Z-26） | — |
| 1 | 直前 Ready rollback revision の attest | (9)、(5) の revision 部分 | — |
| 2 | 必要な migration / declaration / upgrade の状態を読み取り専用で確定 | (2)、(3) | — |
| 2 | 候補 HEAD での順序・再実行性（`declare-surfaces` を含む） | (10) | — |
| 3 | 非冪等 | (10) | — |
| 3 | 不可逆・rollback 不能 | (5) | — |
| 3 | DDL lock の上限 | (6) | — |
| 3 | maintenance 影響（maintenance window の要否） | (6) | — |
| 4 | `max_connections` の余力（traffic 移行中の新旧 revision の二重化を含む） | (8) | — |
| 4 | Data / Control 両 process の restart | (9)（revision の設定・Ready 条件） | restart を実施できること |
| 4 | Ready / health | (9) | restart 後の Ready / health |
| 4 | traffic rollback | (9)（traffic の割り当て、直前 Ready revision の存在） | traffic を戻す操作を実施できること |
| 5 | legacy env を参照する新 candidate / 次 template | (7)（env の継承を含む、裁定 Z-29） | — |

適用: 該当なし（対応表）。

### D-9 `inventory` の置き場所と peer の非対称（v0.2 で追加、裁定 Z-1）

- `inventory` サブコマンドは **MitateDB-api のみ**に置き、`_ISOMORPHIC_TARGETS` に登録しない。
- 非対称の理由: Gate-0 の対象は MitateDB の Cloud Run / Cloud SQL 配備であり、r2db-api は別の配備形（VPS）で同じ状態を持たない。
- 例外出力の修正（D-2）は同型の関数に掛かるので両 peer に入れ、そのために両 peer に同名で足すテストは `_ISOMORPHIC_TARGETS` に登録する（D-7、裁定 Z-16）。非対称は `inventory` の新設に限る。

適用: 該当なし（配置の決定）。

### D-10 DSN の受け渡し（v0.3 で追加、裁定 Z-8）

- DSN は環境変数でのみ渡す。CLI は DSN を argv で受け取らない（静的テストで固定）。
- runbook は `set -x`・HTTP ログ（gcloud の HTTP ログ出力）・シェル履歴・argv への DSN 展開を禁じる。
- Secret Manager からの取り出しは、画面に出さない形（コマンド置換で環境変数へ直接入れる等）だけを書く。
- DSN を入れた環境変数が platform 層の gcloud 実行中もシェルに残らないよう、`inventory` だけをサブシェルで実行する形を書く（設計レビュー 2 回目の n3）。

適用: SI-10、SI-14、T-08、T-14。

### D-11 証跡の置き場所と報告の範囲（v0.3 で追加、裁定 Z-10。v0.4 で出力経路を固定、裁定 Z-24）

- `inventory` の**出力は stdout の 1 経路に限る。** 証跡は operator が stdout を非公開の場所へリダイレクトしたものである（裁定 Z-24）。`inventory` は証跡ファイルを自分で書かない。
- 証跡ファイルは **どの git リポジトリの外**にも置く（operator の手元の非公開の場所）。
- リポジトリ・Mitate への報告に載せるのは、各項目の判定（§1.2 の報告語の対応に従う）と `remediation-required` の注記、識別子を含まない件数だけとする。
- service account・Cloud SQL の接続名・digest の実値・revision 名・DB 名は証跡にのみ残す。
- 証跡を機械可読にするか（§6 Q-3）は依頼者判断待ちのまま。

適用: SI-10、T-08、T-14。

### Security Invariants の扱い

本書は新しい不変条件を足さない。不変条件は機能の許可リストではない（`CLAUDE.md` の Security Invariants are not a feature gate 節）。各決定の「適用」は既存の SI / T 項目への対応付けである。新しい統制は `security/CONTROL_MAPPING.md` に対応付ける（D-7）が、`security/SECURITY_INVARIANTS_V1.md` と `security/THREAT_MODEL_V1.md` は変えない。

## 5. 却下した代替案

1. **本番の Cloud SQL に一般の `psql` で接続して手で読む。** 出力の秘匿をテストで固定できず、C1 を証明できない。
2. **revision spec 全体（`gcloud ... describe` の全出力）を証跡にする。** env の値・secret 参照の値が混ざりうる。
3. **`MitateDB-api/docs/f9-execution-assets-v1/` の資産を流用する。** 参照用・未レビューで、証拠にしない（同ディレクトリの README）。
4. **unknown を warning として続行する。** C3 に反する。
5. **(1) を DB 名の一致で突き合わせる**（v0.4、裁定 Z-26）。代理指標であり（§1.7 の 52）、isolated と production の DB 名が同じだと組を取り違える。
6. **(8) の process 数に `process_ceilings` の宣言値を使う**（v0.4、裁定 Z-27）。宣言は実際の `max-instances` と食い違いうる、需要を過小に数える。

## 6. 依頼者に決めていただく点（両論）

**【依頼者裁定 2026-09-16（逐語）】「すべて推奨で」** — 監督が同日にチャットで示した推奨を、下の表のとおりすべて採用する（§1.7 の 51 により再審議しない）。各 Q の両論は当時のまま残す。

| Q | 採用した案 | 監督が示した推奨の理由（要約） |
|---|---|---|
| Q-1 | **(c)** runbook の互換性の表と独立レビューの受理 | Mitate 設計 §5・§6 の経路に合い、isolated の実施を待たない（(b) は順序が循環する） |
| Q-2 | **(c)** runbook の表と独立レビューの受理 + 適用時の `lock_timeout` | 裁定 Z-31 のとおり |
| Q-3 | **(a)** 機械可読（JSON） | isolated と production の差分比較、Mitate 側の再判定を機械的に行える |
| Q-4 | **(a)** 既存の provision DSN の読み取り専用の接続 | 本番を変えずに Gate-0 を行える（欠点: operator が DDL を実行できる credential を持ち続ける） |
| Q-5 | **(b)** 稼働中 revision の source ref の状態を起点 | (9) が確定しなければ Gate-0 全体が先へ進まないので、(b) で新たに止まる要因は増えない |
| Q-6 | **(a)** Class D、契約版数 1.8.0 据え置き、security-contract 決定は `security/CONTROL_MAPPING.md` の版付きの対応行 | spec の意味を変えない。前例 R-44 WP-3 |
| Q-7 | **(a)** 既存の principal でプロンプトを無効化して実行 | 本番の IAM を変えない。`--quiet` の既定応答は production より前に isolated で確かめる（§8） |

### Q-1 (5) rollback の可逆性を confirmed にする手段（D-4。v0.4 で案 (c) を追加、設計レビュー 2 回目の M8、裁定 Z-35）

| 案 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| (a) migration ごとの互換性宣言 | 各 migration に「直前 Ready revision と互換か」を機械可読に宣言し、`inventory` が読む。宣言の有無を静的テストで固定する | リポジトリ内で完結し、宣言の欠落を機械的に unknown にできる | 宣言の正しさそのものは宣言者の判断に依る。宣言形式を新たに持つ。「直前 Ready revision」は環境ごとに違うので、宣言は「どの source ref の範囲と互換か」の形でしか書けない |
| (b) isolation での実測 | isolated の組で、migration 適用後のスキーマに直前 Ready revision の image を起動し、`verify-declarations` と Ready を確かめた記録を根拠にする | 互換性を実測で示す | 実測の記録は revision の組ごとに取り直しが要る。リポジトリ内の宣言だけでは判定できない。**Mitate 設計 §5 では Gate-0 の受理が isolated の実施より前にあるので、(b) では Gate-0 が isolated の実施を待たないと ready にならず、順序が循環する** |
| (c) runbook の宣言と独立レビューの受理 | runbook に migration ごとの互換性（不可逆か、直前 Ready revision で動くか）を書き、独立レビューで受理する。不可逆なら別 Decision を要求する（Mitate 設計 §5・§6 の経路） | Mitate 設計がすでに求める経路に合う。isolated の実施を待たない | 宣言の正しさはレビューの判断に依る。機械可読でなければ `inventory` は読めず、受理の記録を runbook の手順で (5) に結び付ける必要がある |

### Q-2 (6) ロックと停止時間の上限を confirmed にする手段（D-5。v0.4 で案 (c) の追加と (a) の欠点の修正、裁定 Z-31）

| 案 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| (a) `lock_timeout` の必須化 | platform migration の適用で `lock_timeout` を与えることを必須にし、無ければ赤にする | 待ちの上限が実行時に効く | 上限に達すると migration が失敗し、再実行の手順が要る。停止時間（ACCESS EXCLUSIVE を保持する時間）の上限そのものは表さない。~~適用済みの migration ファイル（0007 / 0011 / 0012）を書き換えることになり、本番の適用状態との対応と (10) の再実行性の証拠に影響する~~ **【v0.4 で修正 2026-09-16、裁定 Z-31】** `lock_timeout` を適用時に与えればファイルを変えずに済む |
| (b) 静的分類テスト | migration の各文をロック種別で分類した宣言を持ち、文と宣言の一致をテストで固定する | どの文が何を止めうるかを事前に読める | 分類は PostgreSQL の規則の写しで、版による差を追う必要がある。待ちの上限は表さない |
| (c) runbook の表と独立レビューの受理 | runbook に migration ごとのロック種別・停止時間の上限・`lock_timeout` の表を置き、独立レビューで受理する（Mitate 設計 §6 の経路） | Mitate 設計 §6 が求める 5 項目（transaction 性、lock 対象、lock / statement timeout、許容待機上限、maintenance window の要否）をそのまま満たせる | 表の正しさはレビューの判断に依る。機械可読でなければ `inventory` は読めず、受理の記録を runbook の手順で (6) に結び付ける必要がある |

- **監督の推奨は (c) と、適用時の `lock_timeout` の併用**（裁定 Z-31）。

### Q-3 inventory 結果の証跡の形

| 案 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| (a) 機械可読（JSON） | 項目・判定・非秘密の識別子を JSON で出す | Mitate 側の再判定や差分比較（isolated と production）を機械的にできる | 出力形式を固定する分、互換性の維持が要る |
| (b) 人間可読のみ | 1 項目 1 行の文で出す | 形式の維持コストが小さい | 比較・再判定は人の読解に依る |

いずれの案でも証跡の置き場所と報告の範囲は D-11 に従う。

### Q-4 credential registry を読む DB 権限（(4)、v0.2 で追加、裁定 Z-6。v0.3 で欠点と案 (c) を補足、裁定 Z-11・Z-22）

| 案 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| (a) 既存の provision DSN | 既存の provision DSN で読み取り専用の接続を使う。秘密の列（`digest` 等）を SELECT しないことをテストで固定する | 本番を変えずに Gate-0 を行える | provision ロールは読み取りより広い権限を持ち、**読み取り専用の設定を自分で外せる**（D-3、特権の境界ではない）。**Gate-0 の間、operator が DDL を実行できる credential を持ち続ける** |
| (b) 最小権限の読み取り専用 role | 読み取り専用の role を新設して読む | 権限が狭い | role の作成自体が本番の変更であり、upgrade より前の Gate-0 に使えない。(3) はアプリケーション DB ごとに台帳を読む権限が要り、新しい role に全 DB への GRANT を足す本番変更の量が大きい |
| (c) 既存の読み取り系 role | 既存の読み取り系 role に必要な権限があるかを列挙し、あれば使う | 本番を変えず、provision より権限が狭い可能性がある | 必要な権限が揃っているかは未確認（§8）。揃っていなければ除外する |

- **監督の推奨は (a)**（Gate-0 の順序と「本番を変えない」制約に合うため。裁定 Z-6）。
- どの案でも、読む権限が無ければその項目は unknown（fail-closed）とし、権限を足して読みに行かない。

### Q-5 (10) の再実行性の証拠の起点（v0.3 で追加、裁定 Z-22。出所は設計レビュー 1 回目の C-7 で、§9.2 の Z-13 の「指摘 7」に当たる。併記は裁定 Z-35）

| 案 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| (a) 空のクラスタ | 使い捨てのクラスタに候補 HEAD の migration 列を最初から適用し、そこからの 2 回目の差分 0 を証拠にする | 手順が単純で、候補 HEAD だけで再現できる。Mitate 設計 §3 の 2 の「候補 HEAD で」に文言どおり合う | 本番が古い版の migration を適用済みのとき、その途中状態からの再実行性は示せない |
| (b) 稼働中 revision の source ref の状態 | (9) で attest した稼働中 revision の source ref の migration を適用した状態を起点に、候補 HEAD の migration を適用し 2 回目の差分 0 を証拠にする | 本番の途中状態に近い起点から示せる | (9) の attest に依存し、起点の組ごとに取り直しが要る。(9) が unknown なら (10) も確定しない |

### Q-6 Class D の「版付きの security-contract 決定」と契約版数（v0.4 で追加、裁定 Z-32）

| 案 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| (a) 据え置き + 対応行 | Class D とし、契約版数は 1.8.0 のまま据え置く。「版付きの security-contract 決定」を、本設計の受理時に `security/CONTROL_MAPPING.md` の版付きの対応行として記録する | spec の意味を変えないので、利用者（AI エージェント）が意味の変化を探す費用が生じない。前例（R-44 の WP-3）に合う | `RM` §9 の 8 の表の「契約版数の更新」からの逸脱であり、依頼者の確認が要る。security-contract 決定が契約の版に現れないので、版だけを見る読み手には決定の存在が見えない |
| (b) 契約の版を上げる | 契約版数を上げ、その版に security-contract 決定を結び付ける | `RM` §9 の 8 の表の文言どおりで、決定が契約の版に現れる | spec の変更が無いのに版が動き、利用者が意味の変化を探す費用が生じる。版の意味（契約の意味の変化）が薄まる |

- **監督の推奨は (a)**（spec の意味を変えないため。前例 R-44 WP-3。裁定 Z-32）。
- クラスを下げる案は置かない（設計レビュー 2 回目の M9）。

### Q-7 platform 層の読み取りを実行する principal（v0.4 で追加、設計レビュー 2 回目の m9、裁定 Z-35）

| 案 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| (a) プロンプトの無効化だけに頼る | operator の既存の principal で、`--quiet` と `CLOUDSDK_CORE_DISABLE_PROMPTS=1` を付けて実行する（D-1） | 本番 IAM を変えない | API の有効化を拒む保証がフラグの既定応答に依る（`--quiet` のときの既定応答は未確認、§8） |
| (b) 閲覧専用の principal | `serviceusage.services.enable` を持たない閲覧専用の principal で実行することを runbook の前提にする | API の有効化が権限の上で起こらない | principal の用意が本番 IAM の変更になり、Gate-0 より前に別の手続きが要る |

## 7. 完了条件と変異（案。作業指示書で WP に割り付ける）

- テストファイル名は案である。DB 層は `MitateDB-api/tests/test_ops_inventory.py` を新設し、`verify-declarations` の出力は両 peer の既存の `tests/test_ops_verify_declarations.py`、(10) は `MitateDB-api/tests/test_migration_0007_ddl.py` と同じ形の migration テストに置く。
- 変異の実行は `tools/dev/mutate.py <変異定義 JSON> -C <worktree>`、テストの実行は `tools/dev/pt.py -C <worktree> -- <テストファイル> -q` による（§1.10 の 64）。
- **変異の箇所が複数の行で重なる（最上位の例外捕捉、片 peer の修正の戻し等）ので、変異定義では変異ごとに赤になる test id を 1 つずつ名指しする**（`RM` §9 の 9 の「`file:操作` → 赤になる test id」。設計レビュー 2 回目の m4）。
- **監査照合の行は、照合対象の逐語記録（実行したコマンドと集計行、または file:line）を設計に残すこと自体を完了条件とする**（§1.5 の 40）。本番の実行結果は記録しない（D-11）。
- 行番号は v0.3 のものを保つ。置き換えた行は取り消し線で残し、足した行は枝番にした（§1.8 の 56）。

**判定と出力**

| # | 完了条件 | 変異（それだけを壊す） | 期待 |
|---|---|---|---|
| 1 | `inventory` が DB 層の各項目（(1) の比較、(2)(3)(4)、(5)・(6) の宣言の有無、(6) の実行時設定部分、(8)）を判定つきで出す（合成の platform DB で 1 件以上観測、§1.5 の 32） | 1 項目の判定を出力から落とす | 赤 |
| 2 | `inventory` は Gate-0 全体の ready を出さない（裁定 Z-15） | 全体の ready を出力に足す | 赤 |
| 2a | `inventory` の終了コードは、DB 層の全項目が confirmed のときだけ 0、unknown / blocked があれば 0 以外（v0.4、裁定 Z-33・Z-35） | unknown があっても 0 を返す | 赤 |
| 3 | Gate-0 全体の ready は、runbook の手順で 10 項目すべてが confirmed のときだけ出す（§1.2） | **監査照合**。runbook の該当手順の節名と手順文を逐語で記録する | — |
| 3a | Mitate への報告で unknown と blocked をどちらも `blocked—platform remediation required` に写し、内訳を併記する（v0.4、裁定 Z-25） | **監査照合**。runbook の報告の書式を逐語で記録する | — |
| 4 | (3) の未適用の migration・upgrade は confirmed + `remediation-required` で、blocked にしない（裁定 Z-14） | 未適用を blocked にする | 赤 |
| 5 | (3) でアプリケーション DB への接続失敗は unknown（C3） | 接続失敗を pending / confirmed に丸める | 赤 |
| 6 | (3) で `read_applied_upgrade_numbers` が `UndefinedTable` 以外の `psycopg.Error` を送出すると unknown | その例外を空の台帳として扱う | 赤 |
| 7 | (3) は登録のみの application を件数と状態で出す | 登録のみの application を集計から除く | 赤 |
| ~~8~~ | ~~(1) の DB 側の識別子を出す~~ **【v0.4 で置換 2026-09-16、裁定 Z-26】** 根拠: 識別子による突き合わせを接続名の比較に改めた。`current_database()` を出す形は 10 と両立しない（設計レビュー 2 回目の B-1） | ~~識別子を出力から落とす~~ | — |
| 8a | (1) で、引数で受け取った接続名を DSN の unix socket の path が指すかを比べ、`match` / `mismatch` / `unknown` だけを出す（裁定 Z-26） | 比較を外して常に `match` を返す | 赤 |
| 8b | (1) で比べられない形の DSN（unix socket の path でない等）は unknown（裁定 Z-26） | 比べられない形を `match` に丸める | 赤 |
| 8c | (1) の出力に接続先（socket の path・接続名）そのものが出ない（裁定 Z-26） | 出力に接続先を足す | 赤 |
| ~~9~~ | ~~(1) で DB 層の識別子と platform 層の接続先を突き合わせ、突き合わせられなければ unknown（裁定 Z-14）~~ **【v0.4 で置換 2026-09-16、裁定 Z-26】** 比較は 8a〜8c でツール内部に移した | ~~監査照合~~ | — |
| 9a | runbook の手順が revision から読んだ Cloud SQL の接続名を `inventory` に渡し、`mismatch` / `unknown` で先へ進まない（裁定 Z-26） | **監査照合**。runbook の該当手順の節名と手順文を逐語で記録する | — |
| 9b | runbook が Cloud SQL Auth Proxy の unix socket モードを `inventory` の前提とし、TCP（loopback）経由では (1) が unknown のままである理由を書く（裁定 Z-34） | **監査照合**。runbook の該当節名と手順文を逐語で記録する | — |

**C1: 秘密を出さない**

| # | 完了条件 | 変異（それだけを壊す） | 期待 |
|---|---|---|---|
| ~~10~~ | ~~成功経路で user / password / dbname の番兵が stdout / stderr に出ない（使い捨てのロールと DB）~~ **【v0.4 で置換 2026-09-16、裁定 Z-24】** dbname の番兵の扱いを成功経路と失敗経路で分けた | ~~出力に接続情報を足す~~ | — |
| 10a | 成功経路で user / password の番兵が stdout / stderr に出ない（使い捨てのロールと DB、裁定 Z-24） | 出力に接続情報（user または password）を足す | 赤 |
| 10b | 成功経路で dbname の番兵が (1) の識別フィールド以外に出ない（裁定 Z-24） | DB 名を識別フィールド以外の項目にも出す | 赤 |
| 10c | `inventory` の出力は stdout の 1 経路に限り、証跡ファイルを自分で書かない（裁定 Z-24、D-11） | 判定の一部を stderr またはファイルに書く | 赤 |
| 11 | 接続失敗経路（接続できない host）: 経路を通ったこと、生の例外文字列に host の番兵があること、stdout / stderr に番兵が無いことを順に assert | 生の例外文字列を出力する形に戻す | 赤 |
| 11a | 接続失敗経路（存在しない role）: 同じ順で、前提 2 は user の番兵を名指しする（裁定 Z-30） | 生の例外文字列を出力する形に戻す | 赤 |
| 11b | 接続失敗経路（存在しない database）: 同じ順で、前提 2 は dbname の番兵を名指しし、出力に dbname の番兵が無いことを assert する（裁定 Z-30・Z-24） | 生の例外文字列を出力する形に戻す | 赤 |
| 12 | DSN 解析失敗経路（不正な形の DSN、接続前）: 同じ順で、前提 2 は password の番兵を名指しする（裁定 Z-15 で旧 9 を置換） | 生の例外文字列を出力する形に戻す | 赤 |
| 13 | 接続後の psycopg 例外経路（`cursor.execute` を差し替えて番兵入りの例外を送出）で出力に番兵が無い | 例外処理で生の例外文字列を出す | 赤 |
| 14 | psycopg 以外の例外は最上位で捕まえ、型名と固定文言だけを出す（traceback を出さない） | 最上位の捕捉を外す | 赤 |
| 15 | 4 要素それぞれに、番兵が生の例外文字列に現れる経路が 1 つ以上ある。無い要素は実測の根拠がある（裁定 Z-7） | **監査照合**。要素 → 経路（テスト名）の表と、経路が作れなかった要素の実測記録を逐語で残す | — |
| 16 | MitateDB-api の `verify-declarations` の接続失敗経路で 11 と同じ assert が成り立つ | MitateDB-api 側で生の例外文字列を出力する形に戻す | 赤 |
| 17 | r2db-api の `verify-declarations` で同じ assert が成り立つ（裁定 Z-1） | r2db-api 側で生の例外文字列を出力する形に戻す | 赤 |
| 18 | 両 peer の `cmd_verify_declarations` が同型のまま（`test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`） | 片 peer だけ修正前の形に戻す | 赤 |
| 19 | 両 peer の ops の漏洩経路を実装前に棚卸しし（§3.1 の経路を名指しで含む）、見つかった経路を同じ方針で直す（裁定 Z-1・Z-7） | **監査照合**。棚卸しの結果（経路の一覧と修正の有無）を逐語で残す。修正した経路はそれぞれ 11 と同じ形のテストと変異を別行で足す | — |
| 20 | `inventory` は DSN を argv で受け取らない（静的テスト、裁定 Z-8） | DSN を受け取る引数を足す | 赤 |
| 21 | runbook の DSN の取得と受け渡しが、`set -x`・HTTP ログ・シェル履歴・argv への展開を禁じ、画面に出さない形だけを書き、`inventory` をサブシェルで実行する（D-10） | **監査照合**。runbook の該当節名と手順文を逐語で記録する | — |
| 22 | (4) の出力の key と `cursor.description` の列名が許可リストに一致し、`credential_id`・`digest` が出ない（裁定 Z-9） | 出力に `credential_id` を足す | 赤 |
| 23 | 同上 | 読み取りを `SELECT *` にする | 赤 |
| 23a | (4) を読む権限が無ければ (4) は unknown（裁定 Z-6、v0.4 で行を追加、裁定 Z-33） | 権限エラーを confirmed に丸める | 赤 |
| 24 | 証跡をどの git リポジトリの外にも置き、報告は判定と識別子を含まない件数だけにする（D-11） | **監査照合**。runbook の該当節名と手順文を逐語で記録する | — |

**C2: 読み取り専用**

| # | 完了条件 | 変異（それだけを壊す） | 期待 |
|---|---|---|---|
| ~~25~~ | ~~factory が開く platform DB の接続で書き込みが拒否される（autocommit を使わない。裁定 Z-11）~~ **【v0.4 で置換 2026-09-16、裁定 Z-28】** 根拠: 明示の `transaction()` の中で書くテストは autocommit の変異を検出しない（設計レビュー 2 回目の M4） | ~~platform DB の接続を autocommit にする~~ | — |
| ~~26~~ | ~~同上~~ **【v0.4 で置換、裁定 Z-28】** | ~~読み取り専用の設定を外す~~ | — |
| ~~27~~ | ~~factory が開くアプリケーション DB の接続で書き込みが拒否される~~ **【v0.4 で置換、裁定 Z-28】** 根拠: factory から接続を取るテストは、factory を通らない本体の接続を検出しない | ~~アプリケーション DB の接続を factory を通さずに開く~~ | — |
| 25a | `psycopg.connect` を spy して `inventory` が開いた全接続を捕まえ、各接続で明示トランザクションの外からの書き込みが拒否される（裁定 Z-28） | セッションの読み取り専用の設定を外す | 赤 |
| 25b | ツールの経路の中で各接続の `transaction_read_only` を読んで確かめ、確かめられない接続では読まず unknown（裁定 Z-28） | 確かめる処理を外す | 赤 |
| 25c | 台帳の表が無いアプリケーション DB でも `read_applied_upgrade_numbers` の `rollback()` と両立し、confirmed + `remediation-required` になる（unknown にならない。裁定 Z-28） | 読み取りを明示の `transaction()` で包む | 赤 |
| 27a | spy が捕まえた接続がすべて factory 経由である（件数一致、裁定 Z-28） | アプリケーション DB の接続を factory を通さずに開く | 赤 |
| 27b | `inventory` の実装で factory 以外に `psycopg.connect` が無い（静的検査、設計レビュー 2 回目の M4） | factory の外に `psycopg.connect` を足す | 赤 |
| 27c | 項目ごとの短いトランザクションで読み、セッションに `lock_timeout` / `statement_timeout` を設定する（設計レビュー 2 回目の m7） | セッションの `lock_timeout` の設定を外す | 赤 |
| 28 | platform 層の手順が gcloud をプロンプト無効で実行し、API 無効・権限不足・対話は unknown とし、API を有効化しない（裁定 Z-12） | **監査照合**。runbook の該当節名とコマンドの形を逐語で記録する | — |

**C3: unknown を丸めない**

| # | 完了条件 | 変異（それだけを壊す） | 期待 |
|---|---|---|---|
| ~~29~~ | ~~env と手元のコードに依存する検査を confirmed の根拠にせず、入力が無ければ unknown（裁定 Z-13）~~ **【v0.4 で 2 行に分割 2026-09-16、裁定 Z-33】** 2 性質に変異が 1 つだった（設計レビュー 2 回目の m5） | ~~入力が無いとき既定値に戻す~~ | — |
| 29a | env と手元のコードに依存する検査（F-14 の capabilities 部分・F-16 の下限等）の結果を confirmed の根拠にしない（裁定 Z-13） | F-16 の結果を (8) の confirmed の根拠に使う | 赤 |
| 29b | 入力（concurrency 等）が引数で与えられなければ unknown（既定値で補わない。裁定 Z-13） | 入力が無いとき既定値に戻す | 赤 |
| 30 | (8) で `max_connections` が読めなければ unknown | 読めないときに余力を計算する | 赤 |
| ~~31~~ | ~~(8) で `process_ceilings` 宣言が無ければ unknown~~ **【v0.4 で置換 2026-09-16、裁定 Z-27】** process 数は宣言値ではなく実際の上限を使う | ~~宣言の欠落を confirmed に丸める~~ | — |
| 31a | (8) で `max-instances` が引数で与えられなければ unknown（裁定 Z-27） | 与えられないとき `process_ceilings` の宣言値で補う | 赤 |
| 32 | (8) で対象 role（D-1 の列挙）のどれかが `CONNECTION LIMIT = -1` なら unknown（裁定 Z-27） | -1 を数として足す | 赤 |
| 32a | (8) で対象 role 以外の role（組み込み・管理用）の `CONNECTION LIMIT = -1` は unknown の理由にしない（裁定 Z-27） | -1 の検査を全 role に広げる | 赤 |
| ~~33~~ | ~~(8) 条件 1 の需要は新旧 revision の process 数の合計で数える（裁定 Z-20）~~ **【v0.4 で置換 2026-09-16、裁定 Z-27】** | ~~1 revision 分だけ数える~~ | — |
| 33a | (8) の process 数は新旧 revision の `max-instances` の合計で数える（裁定 Z-27） | 1 revision 分だけ数える | 赤 |
| 33b | (8) で `process_ceilings` の宣言と ~~実際の `max-instances`~~ が食い違えば blocked（裁定 Z-27） **【註 2026-09-17】WP-E で覆した。宣言と比べるのは各 revision 単体の上限（`--data-process-ceiling` / `--control-process-ceiling`）で、新旧の合計（33a）は余力の計算にだけ使う。根拠は作業指示書 §6A.3 の E2 と §6A.2 の E-R4。現行は §12.4** | 食い違いを無視する | 赤 |
| 34 | (8) 条件 1: role ごとの需要が role の `CONNECTION LIMIT` 以下でなければ confirmed にしない（裁定 Z-20・Z-27） | 条件 1 の比較を外す | 赤 |
| 34a | (8) の process あたり接続数を role の種類ごとに、D-1 の関数名で引く定数から取る（`mitatedbsvc_api` は 2 × concurrency 等、裁定 Z-27） | `mitatedbsvc_api` を 1 × concurrency で数える | 赤 |
| 34b | (8) 条件 2 で、concurrency の上限を共有するアプリケーション role を共有の単位で 1 回だけ数える（裁定 Z-27） | アプリケーションごとに数える | 赤 |
| 34c | (8) で `mitatedbsvc_provision` を対象 role に含めず、`mitatedbsvc_auditreader` は使う process をコードで確定するまで Data と Control の両方で数える（裁定 Z-36） | `mitatedbsvc_auditreader` を片方の process だけで数える | 赤 |
| ~~35~~ | ~~(8) の供給から `inventory` 自身の接続数を差し引く~~ **【v0.3 追補で取り消し 2026-09-16、裁定 Z-20】** Z-20 の式に含まれない | — | — |
| 35 | **【v0.3 追補で復活 2026-09-16、裁定 Z-23】** `inventory` が同時に開く接続の最大数をツールの定数として固定し、静的テストで pin する。この数を (8) の予約枠に含める | 定数を実際に開く接続数より小さくする | 赤 |
| 35a | (8) 条件 2: role の種類ごとの需要の和 + 予約枠が `max_connections` 以下でなければ confirmed にしない（裁定 Z-20・Z-27） | 条件 2 から予約枠を外す | 赤 |
| 35b | (8) で予約枠または process あたり接続数の出所が確定しなければ unknown（裁定 Z-20・Z-27） | 出所の無い値を既定値で補う | 赤 |
| 35c | spy で実測した同時に開いている接続数の最大が、35 の定数以下である（裁定 Z-28。35 の pin とは別） | アプリケーション DB の接続を最後まで閉じない | 赤 |
| 36 | (5) は互換性の根拠が宣言されていなければ unknown（D-4）。**変異を掛ける場所: `MitateDB-api/src/mitatedb_api/ops.py` の `inventory` の (5) の判定関数（案）**（裁定 Z-33） | 既定を confirmed にする | 赤 |
| 37 | (6) は機械可読なロック・maintenance の宣言が無ければ unknown（D-5）。**変異を掛ける場所: 同じく (6) の判定関数（案）**（裁定 Z-33） | 既定を confirmed にする | 赤 |
| 38a | 許可表に無い env の値を読まず、許可表の env が未設定なら unknown（裁定 Z-19） | **監査照合**。runbook の許可表（env 名の列挙）と射影の式を逐語で記録する | — |
| 38 | platform 層の手順が射影された項目だけを出し、すべての container を見て、射影が空・必ずある env 名が無いときは unknown とし、(7)・(9) の判定規則（§4 D-1）を持つ | **監査照合**。runbook の節名と射影の式を逐語で記録する | — |
| 38b | (7) で deploy が env を引き継ぐ形なら、現行 revision の env 名に変更を適用した結果で判定し、旧 env の明示の削除が無ければ blocked（裁定 Z-29） | **監査照合**。runbook の判定手順の節名と手順文を逐語で記録する | — |

**(10) リポジトリ側の証拠**（39〜44 は v0.4 で「`updated_at` を除く」「2 回目の適用の終了コード 0」を明記した。裁定 Z-33）

| # | 完了条件 | 変異（それだけを壊す） | 期待 |
|---|---|---|---|
| 39 | 0007 を 2 回適用し、2 回目の終了コードが 0、`updated_at` を除いて差分 0（既存の `test_0007_alter_role_and_table_creation_are_idempotent` を引用可） | 0007 の 1 文を非冪等にする | 赤 |
| 40 | 0011 を 2 回適用し、同じ条件 | 0011 の 1 文を非冪等にする | 赤 |
| 41 | 0012 を 2 回適用し、同じ条件 | 0012 の 1 文を非冪等にする | 赤 |
| 42 | `declare-surfaces` を 2 回適用し、2 回目の終了コードが 0、`updated_at` を除いて宣言の値の差分 0 | 2 回目で値が変わる形にする | 赤 |
| 43 | `declare-process-ceilings` を 2 回適用し、同じ条件 | 2 回目で値が変わる形にする | 赤 |
| 44 | per-application upgrade を 2 回適用し、2 回目の終了コードが 0、**2 回目の適用件数が 0**、差分 0 | upgrade の台帳への記録を外す | 赤 |
| ~~45~~ | ~~依存先（0007）を欠いた 0011 の適用が失敗する（終了コードで判定）~~ | ~~`_run_psql` の argv 側の `ON_ERROR_STOP` を外す（裁定 Z-15）~~ **【v0.3 追補で置換 2026-09-16、裁定 Z-18】** 根拠: 0011 自身も `\set ON_ERROR_STOP on` を持つので、argv 側だけを外す変異は赤にならないおそれがあった | — |
| ~~45a~~ | ~~`_run_psql` の argv に `ON_ERROR_STOP` があることを静的テストが固定する（裁定 Z-18）~~ **【v0.4 で置換 2026-09-16、裁定 Z-33】** 根拠: テスト harness の helper を固定しても運用の適用経路は守らない（設計レビュー 2 回目の m3） | ~~argv 側の `ON_ERROR_STOP` を外す~~ | — |
| 45a′ | 運用の適用経路が psql の argv に `ON_ERROR_STOP` を渡すことを静的テストが固定する（`ops.py` の `_run_upgrade_script` と `_run_deprovision_script`。裁定 Z-18・Z-33・Z-35） | 運用の適用経路の argv 側の `ON_ERROR_STOP` を外す | 赤 |
| 45b | migration ファイルに `\set ON_ERROR_STOP on` があることを静的テストが固定する（裁定 Z-18。runbook の 0007 / 0011 / 0012 の適用例は argv に持たないので、この層が運用の保証になる） | ファイル側の `\set ON_ERROR_STOP on` を外す | 赤 |
| 45c | 依存先（0007）を欠いた 0011 の適用がエラーで止まる（終了コードで判定、裁定 Z-18） | argv 側とファイル側の `ON_ERROR_STOP` を同時に外す | 赤 |
| 46 | (10) の証拠が候補 HEAD の SHA に結び付いて記録される | **監査照合**。記録の形（SHA と集計行）を逐語で残す | — |

**手続き**

| # | 完了条件 | 変異（それだけを壊す） | 期待 |
|---|---|---|---|
| 47 | 追加・変更したテストと fixture に実値が無い（C5） | **監査照合**。`python3 tools/public_value_scan.py <変更ファイル>` の集計行を逐語で記録する | — |
| 48 | 両 peer に同名で足したテストを `_ISOMORPHIC_TARGETS` に登録し、件数の固定を実測で更新する（§1.5 の 38・40b、裁定 Z-16） | 片 peer のテストだけを書き換える | 赤 |
| 49 | 新しい統制を `security/CONTROL_MAPPING.md` に対応付ける（裁定 Z-16）。§6 Q-6 の裁定に従い版付きで記録する | **監査照合**。追加した行を逐語で記録する | — |
| 50 | 本表に変異も監査照合も持たない行が無い（§1.5 の 40） | **監査照合**。本表の行数と対応数を記録する | — |

## 8. 未確認の点

- ~~番兵をパスワード部だけに置いたとき、libpq の接続失敗文言に番兵が載り、変異が赤になるか。~~ **【v0.2 で解消 2026-09-16、裁定 Z-4】**
- ~~`cmd_show_declarations` / `cmd_upgrade_status` の未捕捉の接続例外の出力に何が載るか。~~ **【v0.3 で静的な事実に置換 2026-09-16、裁定 Z-7】** 両 peer の `main()` の `except psycopg.Error` で例外文字列として stderr に出る（§3.1）。
- ~~user の番兵が生の例外文字列に現れる経路を作れるか（無ければ D-2 のとおり実測の根拠を記録する）。~~ **【v0.4 で解消 2026-09-16、裁定 Z-30】** 存在しない role の経路で載る（§3.1、設計レビュー 2 回目の probe）。
- provision ロールが `mitatedb_registry.credentials` / `control_credentials` を読めるか、既存の読み取り系 role に必要な権限があるか（§6 Q-4）。
- ~~クラスタの system identifier（例: `pg_control_system()`）を provision ロールで読めるか。Cloud SQL の接続先 annotation と突き合わせられる値か。~~ **【v0.4 で不要 2026-09-16、裁定 Z-26】** (1) は接続名と unix socket の path の比較に改めた。
- ~~(1): operator が `inventory` を実行する経路で DSN が unix socket の path の形になるか。runbook の operator 向け `psql` の例は `host=127.0.0.1`（Cloud SQL Auth Proxy 経由）であり、この形では比べられず (1) は unknown になる（§3）。~~ **【v0.4 追補で置換 2026-09-16、裁定 Z-34】** Cloud SQL Auth Proxy の unix socket モードを runbook の前提にし、TCP（loopback）経由では (1) は unknown のままとする（D-1）。
- (8) の予約枠（`superuser_reserved_connections` と Cloud SQL の予約）の値と出所。確定しなければ (8) は unknown（裁定 Z-20・Z-27）。予約枠には `inventory` が同時に開く接続の最大数（ツールの定数）を含める（裁定 Z-23）。
- ~~(8) の対象 role の列挙の確定（`mitatedbsvc_auditreader` を Data / Control のどの process が使うか、`mitatedbsvc_provision` を対象外とするか）~~ **【v0.4 追補で規則を確定 2026-09-16、裁定 Z-36】** `mitatedbsvc_provision` は対象外、`mitatedbsvc_auditreader` は実装 WP の着手時にコード（関数名）で確定し、それまでは Data と Control の両方で数える。残る未確認は `mitatedbsvc_auditreader` を使う process の確定と、process あたり接続数を引く関数（`role_pool_size`・`check_role_connection_limits`）が role の種類ごとの値を全部与えるか。
- ~~env と手元のコードに依存する検査の入力（concurrency 等）を platform 層から得るとき、env の値を射影するか（D-1 は env を名前だけ残す）。~~ **【v0.3 追補で解消 2026-09-16、裁定 Z-19】** 秘密でない数値設定の env だけを許可表に置いて値を読む（D-1）。許可表に載せる env 名は runbook のレビューで確定する。
- secret の名前を証跡に残さないこと（Z-9）が、Mitate 設計 §3 の「secret name/version reference」に照らして Mitate 側の受理に影響しないか（設計レビュー 2 回目の m6）。
- `inventory` のセッションの `lock_timeout` / `statement_timeout` の値と、終了コードの値（作業指示書で固定する）。
- D-5 の表の「推測」「未確認」の行のロック種別。
- platform 層の射影を与える `gcloud` の `--format` の式（フィールドのパス）、build 来歴を読める Artifact Registry / build 記録の項目、`--quiet` のときの既定応答（§6 Q-7）。
- ~~§7 の 45: 0011 自身が `\set ON_ERROR_STOP on` を持つので、`_run_psql` の argv 側だけを外す変異が赤になるか（実測で確かめる）。~~ **【v0.3 追補で置換 2026-09-16、裁定 Z-18】** 2 層を別々の完了条件にした（§7 の 45a′〜45c）。
- 0011 / 0012 と `declare-*`・per-application upgrade の既存の再適用テストの有無。upgrade script 自体が冪等なとき、§7 の 44 の変異「台帳の記録を外す」が「2 回目の適用件数 0」の assert で赤になるか。

## 9. 監督裁定の記録

### 9.1 v0.2 の裁定（Z-1〜Z-4、Z-6。逐語。覆った部分は【註】を添えた）

Z-5 は欠番である。第 1 次の起草の疑義 5（r2db-api の扱い）は Z-1 に統合したため番号を振らなかった（裁定 Z-21）。

- Z-1 (疑義 1・5) 出力秘匿の修正 (例外文字列を出さない) は `_ISOMORPHIC_TARGETS` 登録済みの `cmd_verify_declarations` に掛かるので、**両 peer に同じ修正を入れる**。新設の inventory サブコマンドは **MitateDB-api のみ**に置き、`_ISOMORPHIC_TARGETS` に登録しない (集合を増減しない)。非対称の理由: Gate-0 の対象は MitateDB の Cloud Run / Cloud SQL 配備であり、r2db-api は別の配備形 (VPS) で同じ 7 状態を持たない。この非対称を文書に明記する。両 peer の他の ops サブコマンドについても、例外文字列・DSN を出す経路があるかを実装前に棚卸しすることを完了条件に入れる (見つかれば同じ方針)。
  - **【註 v0.4】** 「`_ISOMORPHIC_TARGETS` に登録しない (集合を増減しない)」のうち、集合を増減しない部分は Z-16 で覆った（両 peer に同名で足すテストを登録する）。`inventory` を登録しない部分は維持する。
- Z-2 (疑義 2) 変更クラスは `RM` §9 の 8 の表に機械的に従い **Class C** (登録 helper の本体を変えるため)。設計レビューは **2 回**。`security/`・`CLAUDE.md`・公開ゲートに触れないので D ではない。契約 (spec) は変えないので契約版数は 1.8.0 のまま (前例: R-44 WP-3 は D でも契約据え置き)。本番の更新 (後続 WP) のクラスは後続の設計で改めて判定する、と書く。D-7 を置き換える。
  - **【註 v0.4】** Class C・設計レビュー 2 回のうち、Class C は Z-16 で覆った（Class D）。
- Z-3 (疑義 3) Gate-0 の項目を 10 に広げる。元の (1)〜(7) の番号は保つ。
  - (8) 接続数の余力: `SHOW max_connections` と role の connection limit・process ceilings の宣言から余力を計算する (DB 層、読み取り)。
    - **【註 v0.4】** 「process ceilings の宣言から余力を計算する」は Z-27 で覆った（process 数は platform 層が読んだ実際の上限を使う）。
  - (9) source → build input → digest → revision の対応と、直前 Ready の rollback revision の存在・Ready/health・traffic の割り当て (platform 層、射影した読み取り)。build 来歴を attest できなければ unknown。
  - (10) 必要な migration / declare / upgrade の再実行性・冪等性と順序: 本番を読むのではなく、**候補 HEAD のリポジトリ側の証拠** (使い捨てクラスタで 2 回適用して差分 0 を確かめるテスト等) で confirmed にする。
  - Mitate 設計 §3 の blocker 1〜5 との対応表を、漏れ 0 になる形で置き直す。restart の「実施できるか」は Gate-0 の読み取りでは確かめられないので、読める部分 (revision の設定・Ready 条件) と、isolated での実施で初めて証明される部分を分けて書く。
- Z-4 (疑義 4) 番兵は DSN の **user・password・host・dbname の全部**に別々の値で置く。空振りを防ぐため、テストは (a) 失敗経路を実際に通ったこと (終了コードと固定文言) と、(b) **生の例外文字列には番兵のどれかが含まれること** を先に assert し、そのうえで stdout / stderr に番兵が 1 つも無いことを assert する。変異 = 生の例外文字列を出力する形 → 赤。
  - **【註 v0.4】** 「(b) 生の例外文字列には番兵のどれかが含まれること」は Z-7 で覆った（4 要素それぞれについて経路を持つ）。成功経路の dbname の番兵の扱いは Z-24 で分けた。
- Z-6 (疑義 6) credential registry を読む DB 権限は依頼者判断待ちとして両論で残す (§6 に Q-4): (a) 既存の provision DSN で読み取り専用トランザクションを使う — 本番の変更なしに Gate-0 を行える。秘密の列 (hash 等) を SELECT しないことをテストで固定する。(b) 最小権限の読み取り専用 role を新設する — 権限は狭いが、role の作成自体が本番の変更であり upgrade より前の Gate-0 に使えない。**監督の推奨は (a)** (Gate-0 の順序と「本番を変えない」制約に合うため)。provision DSN にその権限が無ければその項目は unknown (fail-closed) で、権限を足して読みに行かない。

### 9.2 v0.3 の裁定表（Z-7〜Z-23。逐語。Z-18〜Z-23 は v0.3 追補で足した。覆った部分は註の列に書いた）

裁定の前文（逐語）: 指摘 1〜11 はすべて反映する。裁定を要した項目は次のとおり (Z-7〜Z-17)。本文へは裁定表として逐語で置く。

| 裁定 | 本文（逐語） | 註 |
|---|---|---|
| Z-7 | (指摘 1) 番兵テストは 4 要素 (user / password / host / dbname) **それぞれについて**、その番兵が生の例外文字列に現れる失敗経路 (不正な形の DSN を含む) を少なくとも 1 つ持ち、その経路で stdout / stderr に現れないことを assert する。どの番兵にも前提を満たす経路が作れない場合は、その要素を「漏れる経路が無いことを実測した」として根拠を書く。両 peer の `main()` の psycopg 例外ハンドラ、`_upgrade_one_application` の `failure_detail`、psql の argv に DSN を渡す箇所、psycopg 以外の例外 (traceback) を棚卸しに名指しで入れる。§8 の該当の未確認は静的な事実に置き換える。 | — |
| Z-8 | (指摘 2) operator 手順も C1 の範囲に入れる。DSN は環境変数でのみ渡し、CLI は DSN を argv で受け取らない (静的テストで固定)。runbook は `set -x`・HTTP ログ・シェル履歴・argv への DSN 展開を禁じ、Secret Manager からの取り出しは画面に出さない形だけを書く。 | — |
| Z-9 | (指摘 3) (4) は **DB の credential registry 表**を指す。出力は件数と状態 (enabled / revoked / must_rotate 等) の集計だけで、`credential_id` を出さない。Secret Manager 側は、Data / Control の revision が参照する secret が存在し有効な version を持つかを、**env 名ごとの存在・状態**として (9) の platform 層で読む。secret の名前・値は証跡に残さない。 | — |
| Z-10 | (指摘 4) 証跡ファイルは **どの git リポジトリの外**にも置く (operator の手元の非公開の場所)。リポジトリ・Mitate への報告に載せるのは各項目の confirmed / blocked / unknown と、識別子を含まない件数だけ。service account・Cloud SQL の接続名・digest の実値・revision 名は証跡にのみ残す。Q-3 (JSON か) は依頼者判断待ちのまま。 | — |
| Z-11 | (指摘 5) 読み取り専用は **ツール側の性質**として定義し、特権の境界ではないと明記する。ツールが開くすべての接続 (application DB への接続を含む) で、autocommit を使わず読み取り専用トランザクションで読む。テストは「ツールが開く各接続で書き込みが拒否される」ことを実行で確かめる。provision role が設定を外せることは Q-4 (a) の欠点として書く (Q-4 に「operator が DDL を実行できる credential を持ち続ける」も足す)。 | **【註 v0.4】** 「autocommit を使わず読み取り専用トランザクションで読む」は Z-28 で覆った（接続の単位で掛ける） |
| Z-12 | (指摘 6) gcloud はプロンプトを無効化して実行する (`--quiet` と `CLOUDSDK_CORE_DISABLE_PROMPTS=1`)。API が無効・権限不足・対話が要る状態は unknown。 | — |
| Z-13 | (指摘 7) env 未設定は既定値で補わず unknown。(8) の式を定義する: 各 role の CONNECTION LIMIT と宣言された process ceilings から、traffic 移行中は新旧 revision の合計を上限として `max_connections` と比べる。`CONNECTION LIMIT = -1` (無制限) は余力を計算できないので unknown。射影が空 (フィールドが読めない) のときは unknown で、「無し」と読まない。 | **【註 v0.4】** (8) の式の部分は Z-20、さらに Z-27 で覆った。env を既定値で補わず unknown とする部分と空の射影の部分は維持する |
| Z-14 | (指摘 8) 判定に「解消対象」と「blocker」の区別を入れる (Mitate 設計 §3)。各項目の出力は confirmed / blocked / unknown に加え、観測した不足が既知の解消対象であれば `remediation-required` の注記を持つ (全体判定では先へ進めるための作業項目であり、blocker ではない)。(7) は現行 revision / template の旧 env = 解消対象、新 candidate / 次 template に残る = blocked。(1) は、DB 層と platform 層を同じ実行で読み、DB 層の出力に秘密でない識別子 (例: `current_database()` とクラスタの system identifier) を載せて platform 層の Cloud SQL 接続先と突き合わせる案を書く。突き合わせられなければ unknown。 | **【註 v0.4】** (1) の案（`current_database()` と system identifier）は Z-26 で覆った |
| Z-15 | (指摘 9) 変異表を直す: 20 は `_run_psql` の argv 側の `ON_ERROR_STOP` を外す変異にする。9 は接続前に番兵が載る経路 (Z-7) に置き換える。CLI は DB 層の判定だけを出し、全体の ready は両層を合わせる runbook の手順で出す (2 はそれに合わせる)。変異の無い性質 6 つは、変異を付けるか「監査照合」と明記して照合対象を書く。 | **【註 v0.4】** 「20 は `_run_psql` の argv 側の `ON_ERROR_STOP` を外す変異にする」は Z-18 で覆った |
| Z-16 | (指摘 10) 両 peer に同名で足すテストは §1.5 の 38 により `_ISOMORPHIC_TARGETS` に登録する。新しい統制は `security/CONTROL_MAPPING.md` に対応付ける。したがって **Class D** とする。D-7 を再度覆す (行は消さず根拠と日付を残す)。**依頼者裁定を要する**と明記する。 | — |
| Z-17 | (指摘 11) 対応表の漏れ (blocker 1 の「一意に」、blocker 3 の maintenance、`declare-surfaces`) を埋める。Q-1 (b) の順序の循環を書く。契約版数: spec を変えないので 1.8.0 据え置きとし、C / D 表の「契約版数の更新」からの逸脱として明記し、**依頼者の確認を要する**と書く (前例 R-44 WP-3)。 | — |
| Z-18 | (疑義 1) ON_ERROR_STOP は 2 層 (`_run_psql` の argv と migration ファイルの `\set ON_ERROR_STOP on`) を別々の完了条件にし、静的テストが各層の存在を固定する。変異は層ごとに 1 つ (argv 側を外す → argv の固定テストが赤、ファイル側を外す → ファイルの固定テストが赤)。「エラーで止まる」挙動の実行確認は両層を同時に外す変異で赤を見る。§8 の実測待ちはこれで置き換える。 | **【註 v0.4】** 「`_run_psql` の argv」の層は Z-33 で運用の適用経路に直した |
| Z-19 | (疑義 2) env は名前だけ残すのが原則。例外として、判定の入力になる**秘密でない数値設定**の env だけを明示の許可表 (env 名を列挙) に置き、その値を読んで証跡に残してよい。許可表に無い env の値は読まない。許可表の env が未設定なら unknown。 | — |
| Z-20 | (疑義 3) 解釈を採る: role ごとに「新旧 revision の process 数 × process あたり接続数」の合計が role の CONNECTION LIMIT 以下、かつ全 role の合計 + 予約枠が `max_connections` 以下。予約枠と process あたり接続数の出所が確定しなければ unknown。 | **【註 v0.4】** Z-27 で覆った |
| Z-21 | (疑義 5) Z-5 は欠番である。第 1 次の起草の疑義 5 (r2db-api の扱い) は Z-1 に統合したため番号を振らなかった、と書く。 | — |
| Z-22 | (疑義 4・6) Q-5 と Q-4 (c) の追加を採る。 | — |
| Z-23 | (監督裁定): inventory 自身の接続は Z-20 の「予約枠」に含めて数える。予約枠の出所に「inventory が同時に開く接続の最大数 (ツールの定数として固定し、静的テストで pin)」を足す。取り消した §7 の 35 は、この pin の完了条件として復活させる (変異 = 定数を実際に開く接続数より小さくする → 赤)。§9.2 に逐語で足し、2 チェックを再実行して 1 行で報告。 | — |

### 9.3 v0.4 の裁定表（Z-24〜Z-36 と WP 分割の指示。逐語。Z-34〜Z-36 は v0.4 追補で足した）

裁定の前文（逐語）: 指摘 (blocker 1・major 9・minor 9・nit 3) はすべて反映する。裁定を要した項目は次のとおり。§9 に裁定表として逐語で置き、覆す既存裁定は行を消さず覆した旨を書く。

| 裁定 | 本文（逐語） |
|---|---|
| Z-24 | (B-1) 出力は stdout の 1 経路に限る (operator が非公開の場所へリダイレクトする)。C1 の番兵テストは stdout と stderr の両方を見る。DB 名は credential ではなく識別子であり、(1) の識別フィールドにだけ現れてよい。したがって dbname の番兵は**失敗経路**に限って「出力に現れない」を assert し、成功経路では「識別フィールド以外に現れない」を assert する。user / password / host の番兵は全経路で出力に現れない。§7 の 8 と 10 をこれで両立させる。 |
| Z-25 | (M1) Mitate への報告では、unknown と blocked をどちらも `blocked—platform remediation required` に写し、内訳 (unknown / blocked) を併記する。confirmed だけが通過になる。 |
| Z-26 | (M2) (1) の突き合わせは DB 名の一致を使わない (代理指標、§1.7 の 52)。inventory は platform 層が revision から読んだ Cloud SQL の接続名を引数で受け取り、DSN の接続先 (Cloud SQL の unix socket の path) がその接続名を指すかをツール内部で比べ、`match` / `mismatch` / `unknown` だけを出す (接続先そのものは出さない)。比べられない形の DSN は unknown。Z-14 の (1) の案を覆す。 |
| Z-27 | (M3) (8) の式を作り直す (Z-20 を覆す)。process 数は宣言値ではなく platform 層が読んだ実際の上限 (`max-instances` 等) を使い、宣言と実際が食い違えば blocked。process あたり接続数は role の種類ごとに、コードの定数 (pool の大きさ等) を出所として関数名で引く。concurrency の上限を共有するアプリケーション role は共有の単位で 1 回だけ数える。`CONNECTION LIMIT = -1` を unknown とする対象は Data / Control の process が使う全 role。予約枠は Z-23 のとおり。出所が確定しない項はすべて unknown。 |
| Z-28 | (M4・M5) 読み取り専用は接続の単位で掛ける (接続直後にセッションの既定を読み取り専用にし、ツールの経路の中で `transaction_read_only` を読んで確かめる)。明示の `transaction()` に依存しない — 既存の `read_applied_upgrade_numbers` の `rollback()` と両立させる。テストは `psycopg.connect` を spy してツールが開いた**すべての**接続を捕まえ、各接続で明示トランザクションの外から書き込みを試みて拒否を確かめる。同時接続数の最大は spy で実測する行を足す (Z-23 の定数 pin と別)。 |
| Z-29 | (M6) (7) の next template 判定は deploy 定義だけを読まない。deploy が既存の env を引き継ぐ形 (`--update-env-vars` 等) なら、現行 revision の env 名に変更を適用した結果で判定し、旧 env の明示の削除が無ければ blocked。 |
| Z-30 | (M7) 正しい形の DSN でも例外文言に user・dbname が載る 2 経路 (存在しない role・存在しない database) を D-2 の表と §7 に足す。 |
| Z-31 | (M8) Q-2 に案 (c)「runbook に migration ごとのロック種別・停止時間の上限・`lock_timeout` の表を置き、独立レビューで受理する」(Mitate 設計 §6 の経路) を足す。(a) の欠点は「`lock_timeout` を適用時に与えればファイルを変えずに済む」に直す。監督の推奨は (c) と、適用時の `lock_timeout` の併用。 |
| Z-32 | (M9) §6 に Q-6 を足す: クラス D と契約版数 1.8.0 据え置き、「版付きの security-contract 決定」を本設計の受理時に `security/CONTROL_MAPPING.md` の版付きの対応行として記録する形でよいか。両論 (据え置き+対応行 / 契約の版を上げる) を公平に書く。監督の推奨は前者 (spec の意味を変えないため。前例 R-44 WP-3)。 |
| Z-33 | (minor・nit) すべて反映する。§7 の 36・37 は変異を掛けるコードの置き場所を書く。39〜44 は `updated_at` を比較から除くことと 2 回目の適用の終了コードを見ることを書く。45a は運用の適用経路 (`_run_psql`) を守る行に直す。(4) の権限不足の行と `inventory` の終了コードの行を足す。Q-5 の出所を §9.2 の Z-13 に直す。 |
| （番号なし） | 本書の末尾に、作業指示書へ落とすときの WP 分割案 (両 peer の例外出力の修正 / MitateDB の `inventory` / (10) の migration テスト / runbook の platform 層) を置く。 |
| Z-34 | (疑義 1) inventory の DB 層は Cloud SQL Auth Proxy を **unix socket モード**で使うことを runbook の前提にする (socket の path に接続名が現れる)。TCP (loopback) 経由の DSN では接続先をインスタンスに結び付けられないので (1) は unknown のままとし、runbook に理由を書く。§8 の未確認はこれで置き換える。 |
| Z-35 | (疑義 2・3・4) 起草担当の対応 (45a′、Q-5 の出所の併記、Q-1 の案 (c)、Q-7、終了コード) をすべて採る。 |
| Z-36 | (疑義 5) (8) の対象 role: `mitatedbsvc_provision` は process の role ではないので対象外とし、inventory 自身の provision 接続は Z-23 の予約枠で数える。`mitatedbsvc_auditreader` をどの process が使うかは実装 WP の着手時にコード (関数名) で確定し、確定するまでは Data と Control の両方で数える (多めに数える側に倒す)。 |

## 10. 設計レビューの記録

レビュー記録の原本は scratchpad にあり永続しないので、要点を本節に残す。

- **1 回目**（2026-09-16、対象 v0.2、独立レビュー。静的照合と合成 DSN の probe のみ、pytest は回していない）。記録は scratchpad の `rv/r45-design-review-1.md`。指摘 1〜11（C1 の漏洩経路と番兵の検出力、operator の DSN の受け渡し、`credential_id` の出力、証跡の置き場所、読み取り専用の掛かり方、gcloud の対話、env の既定値と (8) の式と空の射影、解消対象と blocker の区別と (1) の読み方、§7 の変異、クラス、対応表の漏れと両論の公平性）をすべて v0.3 に反映した。裁定を要した項目は §9.2 の Z-7〜Z-17。
- **2 回目**（2026-09-16、対象 v0.3 と追補、独立レビュー。静的照合と合成値の libpq probe（存在しない role / database）のみ、pytest・mutate は回していない）。記録は scratchpad の `rv/r45-design-review-2.md`。指摘は blocker 1・major 9・minor 9・nit 3（監督裁定の前文による集計）。主な指摘: (1) の識別子と成功経路の dbname の番兵が両立しない（B-1）、unknown と Mitate の報告語の対応（M1）、(1) の突き合わせのキーが無い（M2）、(8) の式が接続構成と合わない（M3）、C2 のテストの検出力と `rollback()` との両立（M4・M5）、(7) の env の継承（M6）、user / dbname の経路（M7）、Q-1・Q-2 に Mitate 設計 §6 の経路が無い（M8）、Class D の security-contract 決定（M9）。すべて v0.4 に反映した。裁定を要した項目は §9.3 の Z-24〜Z-33。クラスは D の宣言が妥当で、引き上げ先は無いとの所見だった。

## 11. 作業指示書へ落とすときの WP 分割案（v0.4 で追加、§9.3 の監督の指示）

| WP（案） | 内容 | 主に触るファイル（案） | §7 の行 |
|---|---|---|---|
| WP-A 両 peer の例外出力の修正 | `cmd_verify_declarations` と棚卸しで見つかった経路の例外出力の修正、同名テストの `_ISOMORPHIC_TARGETS` への登録、`security/CONTROL_MAPPING.md` の対応行 | 両 peer の `src/*/ops.py`、`tests/test_ops_verify_declarations.py`、`tests/test_audit_query.py`、`security/CONTROL_MAPPING.md` | 16〜19、48、49 |
| WP-B MitateDB の `inventory` | DB 層の新設（判定、C1、C2、C3、(8) の式） | `MitateDB-api/src/mitatedb_api/ops.py`、`MitateDB-api/tests/test_ops_inventory.py` | 1〜2a、4〜8c、10a〜15、20、22〜23a、25a〜27c、29a〜37（34c を含む） |
| WP-C (10) の migration テスト | 再実行性・冪等性と順序、`ON_ERROR_STOP` の 2 層 | `MitateDB-api/tests/` の migration テスト（新設） | 39〜45c、46 |
| WP-D runbook の platform 層 | 射影の手順、許可表、DSN の受け渡し、全体判定と報告の書式 | `MitateDB-api/docs/cloud-run-cloud-sql.md` | 3、3a、9a、9b、21、24、28、38〜38b |

- WP-A と WP-B は `MitateDB-api/src/mitatedb_api/ops.py` を共に触るので並行にせず直列にする。並行にする WP は、触るファイルの重なりが 0 であることを作業指示書の表と実ファイル名で示す（§1.2 の 16・17）。
- 47・50 は全 WP に掛かる。変更クラスは D-7 と §6 Q-6 の裁定に従い、作業指示書で WP ごとに `RM` §9 の 8 の表で判定する。

## 12. 実施記録

### 12.1 WP-A — 両 peer の ops の例外・接続情報の出力 (2026-09-16)

- 基点 main `0fa4648`、作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` §3・§3.1 (訂正註 A-1〜A-3、監督裁定 A-1〜A-20)。
- **統制** (両 peer の `ops.py`): 例外は型名と固定文言だけを出し traceback を出さない。psql の出力と例外文字列は、実際に渡した接続値 (user・password・host・hostaddr・port・dbname。host 系はカンマで分割) を長い順の一括置換で伏せてから出す。psql には接続情報を argv ではなく libpq の環境変数で渡し、環境変数形の無い conninfo キー、DSN が上書きしない接続設定変数が親の環境にある状態、psql 16 未満・不在をいずれも固定文言で拒否する。`_redact_connection_values` と `_psql_connection_env` を `_ISOMORPHIC_TARGETS` に登録した (136 → 138)。`_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY` は表の仕組みが module 定数を扱えないので未登録 (現時点で両 peer 同一)。
- **§3.1 の訂正**: `_app_dsn` の `conninfo_to_dict` の解析失敗は psycopg 以外の例外ではなく `psycopg.ProgrammingError` だった (経路 2 に落ちる。結論は同じ)。
- **証拠**: 変異 39 件すべて期待どおり。両 peer の suite `MitateDB-api/tests` `1152 passed, 2 subtests passed`・`r2db-api/tests` `1330 passed` (基点 1126 / 1308)。root gate **`3499 passed, 2 subtests passed`**、judge=PASS、実行クラスタ差分 0 (基点 3451 + 48)。`python3 tools/check_comment_provenance.py --register` OK (427 CH-ID)。`--base 0fa4648` の赤 35 件は §4.1(1) 2 件、CH-ID の無い新規の塊 12 件、位置ずれ 21 件 (MitateDB のみ) の類型で、新規コメントには CH-ID を付けない (設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` D-1・D-2)。公開値スキャン flagged 0。`security/CONTROL_MAPPING.md` Version 2.1、SI-10 の両 peer ブロックに統制と証拠を追加 (Q-6 (a) の版付きの security-contract 決定)。
- **レビュー**: 独立コードレビュー 3 回 (差し戻し 2 回)。確実なバグとして、伏字の置換順による接頭辞の漏れと、複数ホストの DSN で伏字が効かないことを直した。A-9 (`PG*` の一律除去) が TLS 設定の格下げを生むことが 2 回目で分かり、A-13 (上書きされない接続設定変数の拒否) で閉じた。
- **WP-D の runbook に書く事項**: ops を動かすホストの psql は 16 以上。接続設定の環境変数 (`PGHOST`・`PGPORT`・`PGUSER`・`PGPASSWORD`・`PGPASSFILE`・`PGSSLMODE`・`PGSSLROOTCERT`・`PGSERVICE`・`PGSERVICEFILE`・`PGSYSCONFDIR` 等) を export したまま upgrade-applications / deprovision を実行すると変数名つきで拒否されるので、DSN に明記する (`passfile=`・`sslrootcert=` 等) か unset する。`~/.pgpass` の既定の読み込みは影響を受けない。
- **残存 (低)**: 1 文字などの極端に短い接続値は、無関係な文字まで伏字にする (過剰に伏せる側であり漏洩ではない)。

### 12.2 WP-C — (10) の migration 再実行性と適用時の `lock_timeout` (2026-09-17)

- 基点 main `9dd7e02` (WP-A 統合後。WP-B より先)。作業指示書 §5・§5.1 (訂正註 C-1・C-2、監督裁定 C-1〜C-12、依頼者裁定)。
- **統制** (MitateDB-api の `ops.py`): `upgrade-applications` と `deprovision` は既定値の無い必須の `--lock-timeout` を取り、値を検証して (不正は入力値を含まない固定文言で拒否)、psql に `PGOPTIONS` の `-c lock_timeout=<値>` として DSN の `options` に連結して渡す。per-application upgrade と deprovision の psql の各ロック待ちに上限がある。argv の `ON_ERROR_STOP=1` は両経路で静的に固定した。
- **(10) のリポジトリ側の証拠** (`MitateDB-api/tests/test_platform_migration_reapply.py`): 起点の列は `migrations/*.sql` から 0004 を除いた 11 ファイル。起点 N は、列の (N+1) 番目のファイルを追加したコミットの親の内容で先頭 N 個を実際の運用の形 (platform DB / provision した application) で適用し、HEAD の内容で全部を適用してから、アップグレードで再実行されるもの (0005・0007・0011・0012 と `upgrade-applications` 経由の 0006・0008〜0010) をもう一度適用して、終了コード 0 と差分 0 (`updated_at` を除く。ロール設定・宣言値・制約・ACL・関数定義・CONNECTION LIMIT・台帳) を確かめる。過去の内容が HEAD と異なる起点で実際にその内容が適用されたことを assert する。手動で入れた ACL・関数本体・ロール設定のずれを再適用が戻すことも確かめる。git の履歴が読めなければ fail する (CI の `conformance` job は `fetch-depth: 0`)。
- **(10) の限界 (R-47)**: 0003 に public schema の USAGE の provision role への付与が入る前 (`b87d1c85` より前) の版で provision され、0008 が未適用の application は、現行の ops の upgrade が台帳を読めず失敗する。その起点 {3, 4, 5, 6} は対象外として pin した。**本番にこの状態の application があれば、Gate-0 の (3)・(10) は blocked になる。**
- **証拠**: 変異 30 件すべて期待どおり (`restores verified 7/7 files (sha256 x2)`)。`MitateDB-api/tests` `1183 passed, 2 subtests passed` (基点 1152)。root gate **`3530 passed, 2 subtests passed`**、judge=PASS、実行クラスタ差分 0 (基点 3499 + 31)。`--register` OK (427 CH-ID)。公開値スキャン flagged 0。`security/CONTROL_MAPPING.md` Version 2.2 (SI-08 の MitateDB ブロック)。
- **レビュー**: 独立コードレビュー 5 回 (差し戻し 4 回)。起点の parametrize が状態を変えていない、per-application の本文が一度も実行されていない、起点の脱落を検出しない、判定文字列が実ファイルの空白と合わない、の各欠陥を直した。
- **作業中の事象**: Google Drive 同期で、変異の復元照合の後に `ops.py` の argv から `ON_ERROR_STOP=1` が消えた状態が 1 度観測され、実装担当が復元して再実行した (`OPERATING_CONDITIONS.md` §2 の 10)。統合前の最終状態で `ON_ERROR_STOP` の grep と変異の残骸 0 を確かめた。

### 12.3 WP-B — MitateDB-api の `inventory` (DB 層) (2026-09-17)

- 基点 main `8a2fe41` (WP-A・WP-C 統合後)。作業指示書 §4・§4.1 (訂正註 B-1〜B-3、監督裁定 B-1〜B-19)。
- **統制** (`ops.py` の `inventory`): DB 層が判定する項目 (1) 接続先の突き合わせ (`comparison` = match / mismatch / unknown と `judgment`)、(2) 宣言 (欠落は confirmed + `remediation-required`、値の不正は blocked)、(3) migration と application ごとの upgrade 状態 (台帳を読めない application は blocked)、(4) credential registry の件数と状態ごとの件数 (credential_id と秘密の列は読まない。返る列名を許可リストで固定)、(6) の実行時設定 (対象 role の CONNECTION LIMIT の値と ~~`lock_timeout` /~~ `statement_timeout`。**【註 2026-09-17】WP-E で覆した。根拠は作業指示書 §6A.1 の依頼者裁定 (b) と §6A.3 の E1。現行は §12.4**)、(8) 接続数の余力 (Data の process 数 × concurrency のアプリケーション role の需要、Control だけが使う auditreader、~~宣言と実際の process 上限の食い違いは blocked~~ (**【註 2026-09-17】WP-E で覆した。宣言と比べるのは各 revision 単体の上限で、需要の計算は新旧の合計から行う。根拠は作業指示書 §6A.3 の E2。現行は §12.4**)、-1 は対象 role の中だけ unknown) を JSON で出す。(5) と (6) のロック・停止時間の部分は `unjudged_items` (`runbook-acceptance`)。終了コードは 0 = 判定した全項目 confirmed、2 = いずれかが blocked / unknown、1 = ツール自身の失敗 (固定文言)。すべての接続 (application DB を含む) を接続単位で読み取り専用にして読み戻し、確かめられない接続は読まずに unknown。各接続に `lock_timeout=3000ms`・`statement_timeout=5000ms`。DSN は環境変数だけで受け取り、user / password / host は全経路で、dbname は識別フィールド以外で出力しない。
- **証拠**: `MitateDB-api/tests/test_ops_inventory.py` 80 テスト、変異 82 件すべて期待どおり。`MitateDB-api/tests` `1263 passed, 2 subtests passed` (基点 1183)。root gate **`3610 passed, 2 subtests passed`**、judge=PASS、実行クラスタ差分 0 (基点 3530 + 80)。`--register` OK (427 CH-ID)。公開値スキャン flagged 0。`security/CONTROL_MAPPING.md` Version 2.3 (SI-08・SI-09・SI-10 の MitateDB ブロック。SI-08 は 14,809 字 / 上限 15,200)。
- **レビュー**: 独立コードレビュー 5 回 (差し戻し 4 回)。接続数の式に Data の process 数が掛かっていない、application 接続の読み取り専用を確かめていない、書き込み拒否を 1 接続でしか試していない、宣言読み取りの失敗が confirmed に進む、user の番兵が DSN に入っていない、を直した。**実装担当が「直した」と報告した項目が 2 回続けて直っていなかった** — 以後、修正の報告には file:line とその箇所だけを壊す変異の赤を必須にした。
- **本番の Gate-0 への帰結**: DB 層だけでは (5) と (6) のロック・停止時間の部分が判定外なので終了コード 0 でも全体は ready ではない。全体は WP-D の runbook で、表の独立レビューの受理記録と platform 層を合わせて判定する。R-47 の状態の application があれば (3) は blocked。

### 12.4 WP-E — `inventory` の (6)・(8) の直しと `apply-platform-migration` (2026-09-17)

- 基点 main `ea316b1` (WP-B 統合後)。作業指示書 §6A・§6A.11 (訂正註 E-1〜E-5、監督裁定 E-S1〜E-S11、監査照合の逐語記録)・§6A.12 (依頼者の回答)。
- **統制** (`ops.py`): (6) の実行時設定の判定から role の `lock_timeout` を外した (`statement_timeout` と CONNECTION LIMIT は残る。E1)。(8) は引数を `--data-process-ceiling`・`--data-process-count-total`・`--control-process-ceiling`・`--control-process-count-total` に分け、宣言との比較は各 revision 単体の上限で行い、需要 (API・controlplane・auditreader・application role・全体) は新旧の合計から計算する (E2)。Control 未配備は `--control-not-deployed` の明示の宣言のときだけ受け付け、出力に `control_deployed` を常に持つ (E3)。`inventory` の入力の拒否は未知の引数を含めすべて終了コード 1 (他のサブコマンドは argparse 既定の 2 のまま)。新サブコマンド `apply-platform-migration` は 0005・0007・0011・0012 だけを受け付け、`--lock-timeout` を必須とし、0007 は `--api-role`・`--controlplane-role` を取る (E4)。DDL を流すサブコマンドの集合と `--lock-timeout` 必須の集合の一致は AST の静的テストで固定した。
- **証拠**: `MitateDB-api/tests/test_ops_inventory.py` 102 テスト (基点 80)、新規 `MitateDB-api/tests/test_ops_apply_platform_migration.py` 29 テスト、`MitateDB-api/tests/test_platform_migration_reapply.py` 31 テスト (件数不変。0005・0007・0011・0012 の 2 回目の適用を `apply-platform-migration` 経由にし、直前に 4 つのオブジェクトをずらし、`_snapshot()` に application_audit の ACL を足した)、`tools/tests/test_no_shared_cluster_defaults.py` の件数 pin 25 → 26。変異 66 件 (manifest の 57 件 + 差し戻しで足した 6 件 + E4-10 の 0007・0011・0012 の個別 3 件) すべて期待どおり。root gate **`3661 passed, 2 subtests passed`**、judge=PASS、実行クラスタの `pg_database` / `pg_roles` 差分 0 (基点 3610 + 51 = `inventory` +22、`apply-platform-migration` +29)。公開値スキャン `files_scanned=6 total_flagged=0`。`check_comment_provenance.py --register` OK (427 CH-ID)、`--base ea316b1` の赤は `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 の (1)(2) の類型 (CH-ID の無い新しい塊。作業指示書 §3.1 の A-15) だけで history-token 0。`security/CONTROL_MAPPING.md` Version 2.4 (SI-08 は置き換えのみで 15,187 字 / 上限 15,200、SI-09 は 6,867 字)。
- **レビュー**: 独立コードレビュー 1 回 (重大 2・中 4・軽 5)、差し戻し 2 回 (1 回目は監督の点検による)。直したもの: 変異 28 件が未実行だった、需要の計算が「上限 ≠ 合計」の入力で観測されていなかった (API 以外の 4 項)、「psql を起動する全関数」の静的テストが手書きの列挙だった (AST で導く形に直した)、E4-2 の包含が片方向、新規コメントの経緯語・文字落ち。
- **作業中の事象と教訓**: (a) 実装担当が、変異を成立させるためだけに製品コードへ常に空の引数を足した (監督が除いた)。変異は「足す」形でも書ける。(b) 実装担当が差し戻しの番号 (「remand 2, item 6」等) を docstring に書いた。以後の発注に「差し戻しの番号も経緯語」と明記する。(c) 実装担当が Google Drive の同期によるテストファイルの巻き戻りを 3 回報告した (`OPERATING_CONDITIONS.md` §2 の 10)。
- **本番の Gate-0 への帰結**: E1 の後も本番の (6) は unknown のままである (auditreader と application ごとの runtime / developer role に `statement_timeout` を設定する経路が無い)。これは台帳 R-48 として起票済みで、R-45 の WP-F で解消する (依頼者の回答 1。作業指示書 §6A.12)。R-47 の状態の application があれば (3) は blocked で、受け入れ後に本番を読んで該当があれば R-47 を 1 本の WP として開く (依頼者の回答 2)。`apply-platform-migration` は WP-E・WP-D・WP-F の作業では本番に対して実行しない。本番での適用は作業指示書 §7 の後続の手順 (isolated での証明 → 独立監査 → 本番更新) で、依頼者の明示の承認の後だけ行う (依頼者の回答 3)。

### 12.5 WP-F — auditreader と application role の `statement_timeout` を設定する 0013 と (6) の値の検査 (2026-09-17〜18)

- 基点 main `80d1495` (WP-E 統合後)。作業指示書 §6B・§6B.11 (訂正註 F-1〜F-5、監督裁定 F-S1〜F-S11、コードレビューと差し戻し 1 の裁定 R1-1〜R1-10、監査照合の逐語記録 6 件)。台帳 R-48 の解消。
- **統制** (新規 `MitateDB-api/migrations/0013_role_statement_timeouts.sql`): `mitatedbsvc_auditreader` と、台帳に載る全 application の runtime / developer role に role 設定の `statement_timeout` を置く (`setdatabase = 0`)。既に provision 済みの role には遡って設定し、`begin_provision_application` を `CREATE OR REPLACE` して以後に作る role にも、新規作成の枝と既存 role の `duplicate_object` の枝の両方で設定する。関数本体の 0012 からの差分は `statement_timeout` の追加行だけである。`runtime_role` / `developer_role` が NULL の登録のみの行と、`pg_roles` に無い role 名の行は飛ばす。ファイル全体が 1 つのトランザクションで、途中で失敗したら何も残らない (差し戻し 1 の R1-1 で `COMMIT;` を末尾へ移した)。0012 の後に適用する (両者が同じ関数を置き換える)。`ops.py` の (6) は、読んだ `statement_timeout` の**値**を判定するようになった: 正の値だけが confirmed、0 / 負 / 解釈できない値は blocked (固定語 `statement-timeout-unbounded`)、設定が無ければ従来どおり unknown。blocked が unknown より強く、CONNECTION LIMIT が -1 の role との混在は unknown のまま (既存の早期 return を変えない)。値そのものも解釈した ms も出力に出さず、項目は常に `reason` キーを持つ。`apply-platform-migration` が受け付けるファイルは 0005・0007・0011・0012・0013 の 5 本になった。
- **値**: `5000ms` (監督裁定 F-S1)。根拠は、0007 が api / controlplane role に置く値、`config.py` の `max_execution_ms` の既定値、`inventory` 自身のセッションの上限と同じ数であり、platform の「期限を渡されない文の上限」が 1 つの数になること。要求の経路は `SET LOCAL` が上書きするため (第 1 段の実測)、この値が効くのは期限を持たない経路 (catalog / schema_revision の読み、起動時の台帳の読み、auditreader の監査クエリ、`deadline=None` の DDL) だけである。値は migration の中の 1 つの SQL の literal に置き、ループ・関数の両枝・auditreader で同じ literal であることを静的テストで固定した (差し戻し 1 の R1-4)。
- **権限の前提** (F-R27 の実測、使い捨てクラスタ): provision role が自ら作った auditreader には 0013 を適用できる。auditreader を provision role 以外 (クラスタの管理 role) が先に作った状態では、0013 は `ERROR: permission denied to alter role` (`DETAIL: Only roles with the CREATEROLE attribute and the ADMIN option on role "..." may alter this role.`) で失敗する。PostgreSQL 16 は CREATEROLE の保持者に、自分が作成した role への暗黙の ADMIN OPTION だけを与えるためである。扱い (監督裁定 F-S3): 0013 は回避しない (SECURITY DEFINER にしない、権限の無い role を飛ばさない)。失敗はトランザクションごと巻き戻り、`apply-platform-migration` は 0 以外で終わる。前提は 0013 のヘッダに現在形で書き、runbook への記載 (前提と直し方) は WP-D が扱う (作業指示書 §6.1 の訂正註 WPD-5。依頼者裁定により直し方は `GRANT ... WITH ADMIN TRUE, INHERIT FALSE, SET FALSE` の 1 つだけを書く)。
- **peer 間の migration 番号の非対称** (F-R19): migration の番号は peer 間で対応させる対象ではない。MitateDB の 0012 (role connection limits) と r2db-api の 0013 は既に同じ内容で番号が違い、本 WP で MitateDB に足した 0013 (role statement timeouts) はこれとは別物である。`security/CONTROL_MAPPING.md` には書かない。
- **証拠**: `MitateDB-api/tests/test_ops_apply_platform_migration.py` 44 テスト (基点 29)、`MitateDB-api/tests/test_ops_inventory.py` 113 テスト (基点 102)、`MitateDB-api/tests/test_platform_migration_reapply.py` 32 テスト (基点 31。0013 を再適用の対象と drift の対象に足した)、`MitateDB-api/tests/test_ops_verify_declarations.py` 33 テスト、`MitateDB-api/tests/test_postgres.py` 87 テスト (コメント 1 行のみ、件数不変)。完了条件 38 件 (変異を持つ行 32 + 監査照合 6)、変異 43 件すべて期待どおり。root gate **`3688 passed, 2 subtests passed`**、judge=PASS、実行クラスタの `pg_database` / `pg_roles` 差分 0。公開値スキャン `files_scanned=11 total_flagged=0` (差し戻し 1 の後の再実行は `files_scanned=6 total_flagged=0`)。`tools/tests/test_no_shared_cluster_defaults.py` の件数 pin 26 は不変。`check_comment_provenance.py --register` OK (427 CH-ID)、`--base 80d1495` の赤は `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 の (1)(2) の類型だけで history-token 0。`security/CONTROL_MAPPING.md` Version 2.5 (SI-08 の MitateDB ブロックは (6) の主張の置き換えのみで 15,187 → 15,194 字 / 上限 15,200、SI-09 の MitateDB ブロックは 6,867 → 8,993 字)。SI-08 の旧文 1 行は `security/CONTROL_MAPPING_HISTORY.md` の SI-08 の節へ逐語で移した。
- **レビュー**: 独立コードレビュー 1 回 (高 2・中 5・低 4・佐 2)、差し戻し 1 回。直したもの: 0013 が 1 つのトランザクションになっていなかった (`COMMIT;` が関数の置き換えの前にあり、権限の失敗で role 設定だけが残りうる形で、ヘッダと SI-09 の「何も残らない」が過大な主張だった)、値の literal の一致を固定する静的テストが無かった、`psycopg.Error` の経路の `reason` キーが未観測だった、`_added_commit` の `None` の分岐が「履歴が読めない」を静かに許可へ変えていた、ON_ERROR_STOP のテストが手書きの列挙だった、実測と食い違う docstring 4 件。SI-08 のブロックが上限に張り付いて証拠のテスト名が入らない件は、実装担当が実測を添えて止まり、監督裁定 F-S11 で SI-09 の Evidence へ 1 行として置いた (主張の本体は SI-08 の (6) の行である旨をその行に書いた)。
- **本番の Gate-0 への帰結**: 本番に 0013 を適用すれば (6) は confirmed になりうる。適用は本 WP では行わない (WP-F の作業中は本番に実行しない)。順序は WP-D の仕上げ (runbook に 0013 の手順と WPD-5 の前提・直し方) → 受け入れ監査 → 作業指示書 §7 の後続の手順で、依頼者の明示の承認の後だけである。
- **記録の所在**: 作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` v1.5 の §6B (manifest)・§6B.11 (訂正註・監督裁定・監査照合・完了ゲート)・§6.1 の訂正註 WPD-5、計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-45・R-48 の行。
