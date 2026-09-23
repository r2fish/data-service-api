# 作業指示書 — R-90 r2db-api の `ops apply-platform-migration` / `ops deprovision`

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点はローカル main `dd12657` (作業ツリー `.claude/worktrees/r90`、branch `r90-r2db-platform-migration-and-deprovision-ops`)。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の R-90 (`RM`:515)。
- 新しい設計文書は起こさない。**決定は本書 §1 に置く** (先例: `docs/work-orders/WORK_ORDER_R62_R2DB_CATALOG_TIMEOUT_V1.md`、`docs/work-orders/WORK_ORDER_R88_CONTROL_MAPPING_POSITION_REFS_V1.md`)。形の先行は R-88 の作業指示書。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit・完了ゲート・`finalize.py` は監督のみ、道具は `tools/dev/`、`DEVTOOLS`)。実装担当の裁量は**実装詳細に限る** — §1.2 の決定と §2〜§5 の完了条件は動かさない。疑義は報告に書き、本書を書き換えない。

## 1. 枠 (監督確定)

### 1.1 問題設定と守るべき条件

**問題**: r2db-api の `ops` に `apply-platform-migration` と `deprovision` が無い。platform migration の再適用と `0004_deprovision_application.sql` は runbook の手動 `psql -f` で、稼働中クラスタでの lock 待ちの上限 (`--lock-timeout`) を強制するものが無い。MitateDB-api は migration ファイルを流す 3 サブコマンド全てに必須の `--lock-timeout` を課し、AST 検査で「DDL を流すサブコマンドの集合 = `--lock-timeout` 必須の集合」を固定する (`MitateDB-api/tests/test_ops_apply_platform_migration.py::test_ddl_flowing_subcommands_match_the_required_lock_timeout_set`)。`security/CONTROL_MAPPING.md:630` がこの差を現在形で開示している。

**守る条件**:

- (a) 契約 1.8.0 と `conformance-tests/` の差分 0。
- (b) 稼働中クラスタに migration ファイルを流す r2db の全経路 (ops 経由) が `--lock-timeout` を必須で持ち、psql に `PGOPTIONS` の `-c lock_timeout=<値>` で届く。
- (c) 拒否は psql を起動する前に起き、運用者の入力値をエコーしない (MitateDB と同じ)。
- (d) 秘密 (password) を CLI 引数に通さない。
- (e) 実装は peer ごとに独立 (コード共有しない、`RM` の P-6)。同名の helper は同型性 pin に載せる。

### 1.2 決定 (D-0〜D-10)

- **D-0 (変更クラス)。** **Class D** (`security/CONTROL_MAPPING.md:630` の開示を書き換え、SI-09 の r2db-api に主張を足す)。D が求める依頼者裁定は 2026-09-19 の委任の下で監督が下し、事後報告とする。本書に対して**設計レビュー 1 回**を行う。**`security/CONTROL_MAPPING.md` の版数は統合時に監督が割り当てる** — 並行の R-87 が 2.23 を取るので、本件は R-87 の統合後に rebase して次の版になる。`security/` を触る WP (WP-4) は **R-87 の統合後**に行う (運用条件 §1.2 の 16「触るファイルの重なり 0」)。
- **D-1 (r2db の platform set)。** `_PLATFORM_MIGRATION_FILENAMES` = **`0008_platform_declarations_and_writer_timeouts.sql`・`0012_process_ceilings.sql`・`0013_role_connection_limits.sql`・`0014_auditreader_statement_timeout.sql`** の 4 本 (application 非依存、かつ psql 変数に秘密を持たない)。`0001`/`0002` は bootstrap-only (MitateDB と同じ)。**`0005`/`0006`/`0007` は password 変数 (`api_password`/`controlplane_password`/`auditreader_password`) を要求するので除外する** (条件 (d)。初回配備の script だけが流す)。`0003`/`0004`/`0009`〜`0011` は application ごと (`0009`〜`0011` は `upgrade-applications`、`0004` は D-2)。変数表は `0008` の `api_role`/`controlplane_role` だけ (MitateDB の `0007` と同じ対)。順序は番号順。superseded-by の表は MitateDB の R-57 D-3 の型で、**4 本の SQL から静的に導いて定数と一致することをテストで証明する** (同じ関数を `CREATE OR REPLACE` する組、同じ role の同じ `SET`/`CONNECTION LIMIT` を再定義する組)。**監督裁定 2026-09-23 (設計レビュー 1 の R1-5)**: 導出の基準を **3 つ**とし、表は **`{"0008_platform_declarations_and_writer_timeouts.sql": ("0012_process_ceilings.sql",)}` で確定する**。基準は (i) 同じ関数を `CREATE OR REPLACE` する組、(ii) 同じ role の同じ `SET`/`CONNECTION LIMIT` を再定義する組、(iii) **同じ table の同じ名前の制約を張り直す組** (`ALTER TABLE … ADD/DROP CONSTRAINT <名前>` と `CREATE TABLE` 内の `CONSTRAINT <名前>` を table + 名前で対応づけ、静的に導出する)。(iii) を入れる理由: `0012` は冪等なので同時適用を強いても損が無く、retrofit の初回適用で `0008` を単独で流すと `platform_declarations_key_check` が 3 キーのまま残る穴 (§1.3 (2)) を閉じられる。「導出 == 定数」は非空で assert する (§2.3 の 4・4b)。**導出が正本**であり、定数はそれに合わせる側である。
- **D-2 (deprovision)。** `ops deprovision <app_slug> --confirm <phrase> --lock-timeout <値>`。MitateDB の型 (`MitateDB-api/src/mitatedb_api/ops.py`:767-796) に倣う: slug の書式検証 (DB に触る前) → `--lock-timeout` の検証 → DSN は環境変数のみ (r2db の既存 `_control_dsn()` = `R2DB_CONTROL_DSN`) → registry から登録時刻相当を読む (**registry の schema は `_schema()` 経由**。`r2db-api/src/r2db_api/ops.py`:100-106。固定名を書かない) → 確認句 `DEPROVISION application {slug} @registered={digest16}` を計算 → `--confirm` の不一致は JSON の denial (exit 2、`required_confirmation`/`consequence`/`reversible_alternative` を含む。契約 `destructive_confirmation` の declare-and-echo) → 一致で `0004_deprovision_application.sql` を `psql -v ON_ERROR_STOP=1 -v app_slug=<slug> -f` で流す (`PGOPTIONS` に lock_timeout)。登録時刻相当の列は §1.3 (3)。`0004` 自身の「credential 行が残っていれば拒む」挙動は SQL のまま (§1.3 (4))。
- **D-3 (AST 検査)。** `r2db-api/tests/test_ops_apply_platform_migration.py` (新規) に MitateDB と同じ 2 検査を置く: (i) DDL を流すサブコマンドの集合 (AST から導出) = `--lock-timeout` が required かつ既定なしのサブコマンドの集合、かつ厳密に 3 件 (`apply-platform-migration`/`upgrade-applications`/`deprovision`)、(ii) psql にファイルを渡す関数の集合 (AST) の全てが `_with_lock_timeout_option` を呼ぶ。
- **D-4 (配備 script)。** `r2db-api/deploy/scripts/part1_provision_host_and_db.sh` は**変えない**。初回配備は待たせる相手のいないクラスタで、`security/CONTROL_MAPPING.md:630` が既に許容として開示済みであり、script の順序は `r2db-api/tests/test_deploy_script_migrations.py` が pin する別の変更クラスの領域である (§1.3 (9))。runbook の**手動の再適用・deprovision の経路**をサブコマンドに置き換える (D-7)。
- **D-5 (同型性)。** `_resolve_platform_migration_file`・`_validate_platform_migration_run`・`_platform_migration_variables`・`_deprovision_confirmation_phrase` は本体が汎用 (定数名・`_die` のメッセージ・`--api-role`/`--controlplane-role` が同じ) なので、**両 peer の `_ISOMORPHIC_TARGETS` に載せる** (143 → 147 行、両 peer の pin テストの `N` を更新)。Class D は既に宣言済みである。**`_deprovision_confirmation_phrase` は純関数として pin する** (監督裁定 2026-09-23): 引数名は MitateDB の語彙 (`application_id`・`registered_at`) に揃え、**関数本体に peer 固有の語を置かない**。r2db の呼び出し側が slug と `provisioned_at` の値をその引数に渡す。pin しないのは次 — `cmd_apply_platform_migration`・`cmd_deprovision`・`_run_deprovision_script` (DSN 関数名・psql 変数名 `app_slug` と `app_id`・runbook の path が peer 固有。先例 `_run_upgrade_script`) と、**registry から登録時刻を読む関数** (読む列名が `provisioned_at` と `registered_at` で peer 固有。監督裁定 2026-09-23)。正規化の規則と 4 本の pin 可否は §1.3 (6)。
- **D-6 (テスト)。** 置き場は `r2db-api/tests`、実 PostgreSQL は使い捨てクラスタの platform (§1.3 (5))。MitateDB の 75 本を写す義務は無いが、次を最低限固定する — filename 検証 (path separator / 未知名 / symlink 脱出 / 不在)、run の順序・重複・superseded-by の閉包、変数表の不足・余剰、DSN が環境変数のみ、拒否時に psql が起動しない (`subprocess.run` 差し替え)、失敗時の redaction、`PGOPTIONS` の lock_timeout、4 本の drift-then-restore (実 PostgreSQL: 値を動かして再適用で戻る)、AST 検査 2 本、deprovision の 書式不正 / 未登録 / confirm 不一致 (JSON denial、exit 2) / 一致で `0004` が流れて role と DB が消える (実 PostgreSQL) / credential 行が残ると拒む。**完了条件 1 項目 = 変異 1 つ**。
- **D-7 (runbook と migration ヘッダ)。** `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` の手動 `psql -f` の指示 (`0004` は :493-497・:524、`0008` は :1613-1617、`0012` は :1895・:1921、`0013` は :373-375、`0014` は :1988。**`0008` は監督裁定 2026-09-23 で追加** — D-1 の集合に入る以上、手で叩く経路を残さない) を `python -m r2db_api.ops apply-platform-migration … --lock-timeout <値>` / `ops deprovision …` に置き換える (段落単位で現物照合。全文は §1.3 (8))。migration ヘッダ内の手動例 (`0004`:7-8、`0008`:11-12、`0012`:16、`0013`:23、`0014`:12) も同じ (R-66 のコードレビュー 低-7。`0008` は同裁定で追加)。help テキストは runbook の節を名指す。
- **D-8 (開示、Class D)。** `security/CONTROL_MAPPING.md:630` を in place で書き換える (peer 差は解消。旧文は逐語で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` へ)。SI-09 の r2db-api の block に、MitateDB の `:824-846` と同じ形の `apply-platform-migration`/`deprovision` の主張を足す (追記、証拠テスト名つき)。**あわせて同 block の `:784` (「4 つの gate される面の phrase 構築は `structured.py` に 1 度だけ」) と `:788` (「ritual CLI は store/DSN を作る前に gate するので誤った `--confirm` は DB に触れない」) を in place で訂正する** (監督裁定 2026-09-23。deprovision は 5 つ目の gate される面で、確認句は `ops.py` に置かれ、計算に registry 読みが要るので両主張は本件で偽になる。Update convention、旧文は逐語で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` へ)。確定文は監督が実装後に確定する (運用条件 §1.5 の 34・35)。ブロック長 (cap 15,200) と物理行 (cap 1,400) を実測する (現況は §1.3 (7))。
- **D-9 (コメント)。** 新しい関数は docstring を現在形で書く。**`r2db-api/src/r2db_api/ops.py`:331 の `_require_cli_confirmation` の docstring (「in both callers below」「not even a connection is opened」) は WP-2 で同一変更セット内の言い換えとして直す** (監督裁定 2026-09-23。deprovision が 3 つ目の呼び出し元になり、確認句の計算に registry 読みが要るので現物と食い違う。R-68 の経路)。`tools/check_comment_provenance.py --base dd12657` は「§4.1 (1) 以外が 0 行」。
- **D-10 (WP 分割)。** **WP-1** = `apply-platform-migration` + AST 検査、**WP-2** = `deprovision` + **同型 pin 4 行と `147` への改名** (両 peer の `tests/test_audit_query.py`。監督裁定 2026-09-23 の R1-2 で WP-1 から移した — 4 行のうち `_deprovision_confirmation_phrase` は WP-2 で初めて現れるので、表の編集を 2 つの WP に割らない)、**WP-3** = runbook・migration ヘッダ・help、**WP-4** = `security/CONTROL_MAPPING.md` (R-87 の統合後)。WP-1〜3 は**同じ作業ツリー・同じ実装担当で直列**に行う。AST 検査のうち `deprovision` の存在を前提にする 2 つの固定 — (i) DDL 集合が厳密に 3 件、(ii) psql に `-f` を渡す関数が厳密に 3 つ — は **WP-1 で書き、緑の確認と変異は WP-2 の完了条件で行う** (WP-1 で「deprovision 抜きの 2 件」を一旦固定しない)。同型 pin は表の編集ごと WP-2 で行う。

### 1.3 起草時の実測 (2026-09-23、`dd12657`。実装担当は着手時に再測し、食い違いを報告する)

**(1) 4 本の SQL の DDL と psql 変数** (`r2db-api/migrations/`)

| ファイル | 行数 | DDL | psql 変数 |
|---|---|---|---|
| `0008_platform_declarations_and_writer_timeouts.sql` | 168 | `BEGIN` (:121)、`ALTER ROLE :"api_role"/:"controlplane_role" SET statement_timeout`・`idle_in_transaction_session_timeout = '5000ms'` (:127-130)、`CREATE TABLE IF NOT EXISTS r2dbsvc_registry.platform_declarations` (制約名 `platform_declarations_key_check`、:136-142)、`REVOKE`/`GRANT SELECT` (:144-146)、`INSERT … 'audit_coalescing_window_ms' … DO NOTHING` (:154-156)、`INSERT … 'audit_writer_roles' … DO UPDATE` (:164-166)、`COMMIT` (:168) | `api_role`・`controlplane_role` のみ |
| `0012_process_ceilings.sql` | 76 | `BEGIN` (:63)、`ALTER TABLE … DROP CONSTRAINT IF EXISTS platform_declarations_key_check` (:69-70)、`ALTER TABLE … ADD CONSTRAINT` (5 キーに拡げる、:72-74)、`COMMIT` (:76) | 無し |
| `0013_role_connection_limits.sql` | 193 | `BEGIN` (:102)、§1 `ALTER ROLE r2dbsvc_api CONNECTION LIMIT 68`・`r2dbsvc_controlplane CONNECTION LIMIT 20` (:108-109)、§2 `DO $$` で provisioned application の runtime/developer role に `CONNECTION LIMIT 36` (:122-136)、`COMMIT` (:137)、§3 `CREATE OR REPLACE FUNCTION r2dbsvc_registry.begin_provision_application(text,text,text)` (:150-191、トランザクション外) と `REVOKE` (:193) | 無し |
| `0014_auditreader_statement_timeout.sql` | 57 | `BEGIN` (:53)、`ALTER ROLE r2dbsvc_auditreader SET statement_timeout = '5000ms'` (:55)、`COMMIT` (:57) | 無し |

`0012`/`0013`/`0014` はコメントを除くと psql 変数の参照が 0 件 (`grep` 実測)。4 本とも header か runbook に「idempotent / 再適用可」または「代入であって増分ではない」旨が在る (`0008` は runbook :1609-1611、`0012` は :1892、`0014` は :1982、`0013` は本文が代入と `CREATE OR REPLACE`)。

**(2) superseded-by の起草時の見込み**

- D-1 の 2 基準 (同じ関数の `CREATE OR REPLACE` の組、同じ role の同じ `SET`/`CONNECTION LIMIT` の組) を 4 本の内側に当てると、**組が 1 つも立たない見込み**である。根拠 (いずれも `r2db-api/migrations/*.sql` の `grep` 実測):
  - `begin_provision_application` を置き直すのは `0002`:86 → `0006`:190 → `0013`:150 の順で、集合の中では `0013` が最後 (`0014` は関数を触らない)。
  - role の `ALTER ROLE … SET` は repo 全体で 5 行だけ — `0008`:127-130 (api/controlplane) と `0014`:55 (auditreader) で、対象 role が重ならない。
  - `ALTER ROLE … CONNECTION LIMIT` は `0013`:108-109 だけ。他の `CONNECTION LIMIT` は `CREATE ROLE` の一部 (`0001`:96、`0002`:117/121、`0005`:126、`0006`:221/225/457、`0007`:194) で、いずれも集合の外かつ `0013` より前。
- 起草時の 2 基準の外に候補が 1 つある: `0008` の `platform_declarations_key_check` (3 キー) と `0012` の同名制約の張り直し (5 キー)。既に table が在るクラスタへの再適用では `0008` の制約は `CREATE TABLE IF NOT EXISTS` の内側なので効かないが、**retrofit の初回適用 (table がまだ無いクラスタ) では `0008` を単独で流すと 3 キーのまま残る**。→ **監督裁定 2026-09-23 (R1-5): 第 3 基準「同じ table の同じ名前の制約を張り直す組」を足し、表を `{0008: (0012,)}` で確定する** (D-1)。`0012` は冪等なので同時適用を強いても損が無い。
- 逆向き (集合の外の後続が集合の中のファイルを追い越す) は 0 件。
- → 表は 1 組を持つので「導出 == 定数」も閉包の判定も**現物で非空に固定できる** (§2.3 の 4・5)。導出の側が空にならないことは、合成 SQL 2 本に導出を掛けて期待の map と比べる完了条件で別に固定する (§2.3 の 4b、R1-4)。

**(3) registry の「登録時刻相当」の列**

`r2dbsvc_registry.applications` は `0002`:69-75 で `application_slug` (PK) / `database_name` / `runtime_role` / `developer_role` / `provisioned_at timestamptz NOT NULL DEFAULT now()`。`0006` が 4 列の `NOT NULL` を落とし (:76-79)、`provisioned_at` の DEFAULT を落とし (:86)、`issuance_frozen` を足し (:101-102)、two-state の CHECK `applications_registration_state_check` を張る (:113-129)。`finish_provision_application` (`0006`:313-330) が provision の成功時に `provisioned_at = now()` を書くので、**同じ slug を deprovision して再 provision すると必ず変わる**。deprovision の対象は `database_name IS NOT NULL` の行だけ (`begin_deprovision_application`、`0006`:343-) で、two-state CHECK によりその行の `provisioned_at` は必ず非 NULL。→ **`provisioned_at` が MitateDB の `registered_at` (`MitateDB-api/src/mitatedb_api/ops.py`:526-537 の確認句の素材) に当たる。**

**(4) `0004` の現物** (`r2db-api/migrations/0004_deprovision_application.sql`、205 行)

psql 変数は `:'app_slug'` のみ。`database_name`/`runtime_role`/`developer_role` は `begin_deprovision_application` の戻りを `\gset` で受ける (:79)。credential 残留ガードは `to_regprocedure` + `\gexec` の条件つき (:81-86) で、`0005_credential_store.sql` が未適用の platform では**飛ばされる** — 「credential 行が残ると拒む」を実 PostgreSQL で見る完了条件は `0005` を流した platform が要る。以降は live-connection 事前検査 → 一時自己 GRANT → `ALLOW_CONNECTIONS false` → 絞った `pg_terminate_backend` → `DROP DATABASE`/`DROP ROLE`/`finish_deprovision_application` (R-54 の形)。`\set ON_ERROR_STOP on` はファイル自身が持つ (:77) が、`-v ON_ERROR_STOP=1` は D-2 のとおり ops 側でも渡す。

**(5) 実 PostgreSQL の fixture と前置き**

- 現物の `platform` fixture は `r2db-api/tests/test_postgres.py`:178-219 に在り、`scope="module"`、`r2dbsvc` を使い捨て prefix に書き換えた **`0001`/`0002`/`0003`/`0004` の 4 本だけ**を一時 dir に書き出して流す (`0001`/`0002` を適用、`0003`/`0004` は script の path として `SimpleNamespace` に載る)。conftest には無い (`r2db-api/conftest.py` は使い捨てクラスタの起動だけを行う)。
- MitateDB の対応ファイルは**自前の fixture を持つ** — `MitateDB-api/tests/test_ops_apply_platform_migration.py`:122-230 (`_PLATFORM_MIGRATION_NAMES` 8 本を書き換え、`0001`/`0002`/`0005`/`0007`/`0011`/`0012`/`0013` を流し、`0014` は copy のみ)。冒頭 docstring :16-20 が「他のテスト module から import しない」という repo の先例を明記する。
- 4 本を実 PostgreSQL に流すのに要る前置き (ヘッダ実測): `0008` は `0007` の後、`0013` は `0002`/`0005`/`0006`/`0007` が在れば可、`0014` は `0007` の後、`0012` は `0008` の後。`0005`/`0006`/`0007` は password 変数を要るので、**fixture 自身の psql が渡す** (ops は渡さない、条件 (d))。
- schema 名 `r2dbsvc_registry` と role 名 `r2dbsvc_api`/`r2dbsvc_controlplane`/`r2dbsvc_auditreader` は `0012`〜`0014` に literal で在るので、prefix の書き換えは 4 本にも要る。書き換え後の dir は `_migrations_dir()` が読む `R2DB_MIGRATIONS_DIR` (`r2db-api/src/r2db_api/ops.py`:131-149) で指せる。
- **同じ前置きの先例が r2db に既に 2 つある** — `r2db-api/tests/test_audit_query.py`:76-101 (`MIGRATION_NAMES` = `0001`/`0002`/`0005`/`0006`/`0007`/`0014`/`0013`/`0008`/`0012`、順序の理由をコメントで持つ) と :215-233 (prefix 書き換え + `_run_psql` で password 変数を渡す bootstrap)、`r2db-api/tests/test_application_audit.py`:70-84・:213-222 (同型)。新規ファイルはこの形に倣う。
- どの形にするか (自前 fixture の細部) は**実装詳細**として実装担当が決め、報告に書く。

**(6) 同型性の正規化と 4 本の pin 可否**

- `_normalize` (`r2db-api/tests/test_audit_query.py`:3359-3430) が畳むのは (a) 先頭 docstring 全体 (`_strip_leading_docstring` :3331-3356)、(b) `r2db_api`/`mitatedb_api` → `<PEER_PACKAGE>`、(c) `ResourceLimits`/`FoundationConfig` → `<PEER_TYPE>`、(d) `R2DB_`/`MITATEDB_` → `<PEER_ENV_PREFIX>`、(e) 行末空白と連続空行**だけ**である。字下げ・字間・数値は畳まない (`test_isomorphic_normalizer_does_not_absorb_numeric_literals` :3432)。
- → `_resolve_platform_migration_file`・`_validate_platform_migration_run`・`_platform_migration_variables` は MitateDB 側の**本体**に peer 固有の literal が無い (定数名は同名、`_die` の文面は subcommand 名だけ、`MITATEDB_MIGRATIONS_DIR` や `CH-ID` や `ops.py:<行>` の参照は docstring の中で、比較前に落ちる)。byte 一致させられる。
- → `_deprovision_confirmation_phrase` も本体は汎用だが、**引数名 (`application_id`/`registered_at`) と確認句の literal まで一致が要る**。確認句は D-2 が逐語で固定しているので一致する。引数名は D-5 の裁定どおり MitateDB の語彙に揃え、r2db の語彙 (`app_slug`/`provisioned_at`) は**呼び出し側に留める** — 純関数の本体に peer 固有の語を置かない。
- 表の更新箇所は各 peer **3 箇所**: `_ISOMORPHIC_TARGETS` 本体 (r2db :2393-2920 / MitateDB :2179-)、pin テストの全文 assert (r2db :2994-3249 / MitateDB :2782-)、末尾の `assert len(_ISOMORPHIC_TARGETS) == 143` (r2db :3250)。**テスト名 `test_isomorphic_target_table_is_pinned_to_its_current_143_rows` は表の行そのもの** (r2db :2416・:3009 / MitateDB :2202・:2782) なので、`147` への改名は表の中の 1 行も動かす。
- MitateDB 側の `_lookup_application_registered_at` (`MitateDB-api/src/mitatedb_api/ops.py`:540-) に当たる r2db の lookup は、読む列名 (`provisioned_at` と `registered_at`) が peer 固有なので **pin しない** (D-5 の裁定)。

**(7) `security/CONTROL_MAPPING.md` の現況** (版 2.22、`:5`)

| 位置 | 内容 | block 文字数 (cap 15,200) |
|---|---|---|
| `:608` | SI-08 / `### r2db-api` (既定 block)。**`:630` はこの block の中**である | 10,304 (残り 4,896) |
| `:642` | SI-08 / `### r2db-api -- capacity and concurrency` | 9,226 (残り 5,974) |
| `:778` | SI-09 / `### r2db-api` (既定 block)。Control 7 件、Evidence `- —`、Status `- —` | 2,211 (残り 12,989) |
| `:824` | SI-09 / `### MitateDB-api -- platform upgrade` (D-8 が形を倣う先。主張は :828・:833-834・:836・:841・:845-846) | 12,747 (残り 2,453) |

- `:630` の物理行は 616 文字 (cap 1,400、残り 784)。cap の宣言は前文 :28-31 (「最長 block は SI-09 の MitateDB-api `platform upgrade` block、12,747 文字」— 本表の実測と一致)。
- 名前つき block は 1 subsection あたり最大 3 (`MAX_NAMED_SUBBLOCKS`、前文 :36-44)。SI-09 の r2db-api は既定 block のみ。
- 検査は `conformance-tests/test_control_mapping_register.py` (block 長・物理行長・テスト名の解決・位置参照 `file:line` の解決 = R-88 の node id 15)。

**(8) runbook の該当行 (D-7 の対象、全文)** — `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (2,028 行)

- `:373-375` (§4 Connection ceiling、`0013`): 「Applying it by hand (an already-running cluster this script has not touched, or a retrofit after the fact):」に続く ``` ブロック — `PGOPTIONS='-c lock_timeout=<value>' psql "$R2DBSVC_CONTROL_DSN" -v ON_ERROR_STOP=1 \` / `  -f r2db-api/migrations/0013_role_connection_limits.sql`
- `:493-497` (§5 Order of operations、`0004`): 「To remove an application (e.g. tearing down a test/staging application):」に続く ``` ブロック — `PGOPTIONS='-c lock_timeout=<value>' psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' \` / `  -f r2db-api/migrations/0004_deprovision_application.sql`
- `:524` (§5、credential 残留のエラー例の冒頭行): `psql "$R2DBSVC_CONTROL_DSN" -v app_slug='myapp' -f r2db-api/migrations/0004_deprovision_application.sql` (直後 :525-528 が `ERROR:  application myapp still has 2 credential row(s) referencing it -- revoke it first …` の逐語例)
- `:1895` (§18 `process_ceilings`、`0012`): `psql "$R2DBSVC_CONTROL_DSN" -f r2db-api/migrations/0012_process_ceilings.sql` (直前 :1892-1893 が「Run once, after `0008` … (idempotent -- safe to re-run, takes no `-v` variables)」)
- `:1921` (§18、既存ホストの必須順序の 1.): ``1. `psql "$R2DBSVC_CONTROL_DSN" -f r2db-api/migrations/0012_process_ceilings.sql` ``
- `:1988` (§19 auditreader の `statement_timeout`、`0014`): `PGOPTIONS='-c lock_timeout=<value>' psql "$R2DBSVC_CONTROL_DSN" -v ON_ERROR_STOP=1 -f r2db-api/migrations/0014_auditreader_statement_timeout.sql`
- `:1613-1617` (§16 Platform declarations、`0008`。**D-7 に監督裁定 2026-09-23 で追加**): 「Run once, after `0007`, as `r2dbsvc_control` against `r2dbsvc_platform` (idempotent -- safe to re-run; a re-run resets a hand-changed timeout back to the shipped default, so use `ops set-platform-timeouts` for real changes):」に続く ``` ブロック — `psql "$R2DBSVC_CONTROL_DSN" \` / `  -v api_role=r2dbsvc_api -v controlplane_role=r2dbsvc_controlplane \` / `  -f r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql` (`ON_ERROR_STOP` も `PGOPTIONS` も無い)
- migration ヘッダ内の手動例: `0004`:7-8、`0008`:11-12、`0012`:16、`0013`:23、`0014`:12。
- r2db の runbook には MitateDB の section 10 のような「gated procedure」の単一節が**無い**。該当節は `0013` = §4、`0004` = §5、`0008` = §16、`0012` = §18、`0014` = §19 に散る (help が名指す節はファイルごとに違う)。

**(9) `r2db-api/tests/test_deploy_script_migrations.py` が pin するもの** (静的、実 PostgreSQL 不要)

- テスト 6 件 (:75 除外集合、:87 全 migration の出現、:116 順序、:137 `part1a` の 98/72 の再計算、:167 `part1a` の呼び出し位置、:183 `upgrade-applications` の `--lock-timeout`)。
- `_INVOCATION_RE` (:31) は `-f "${…}/NNNN_….sql"` と `\\i` の形**だけ**を拾う。`EXPECTED_EXCLUDED_MIGRATION_NUMBERS = PLATFORM_UPGRADE_NUMBERS | {4}` = `{4, 9, 10, 11}` (`r2db-api/src/r2db_api/platform_upgrades.py`:83)。
- → `test_every_platform_migration_appears_in_the_scripts_invocation_list` は除外集合以外の全 migration が script の psql 行に出ることを要求するので、**part1 の psql 行を `ops` 呼び出しに替えるとこのテストが赤になる** (D-4 の裏づけ)。

**(10) AST 由来の集合の現況** (MitateDB の `_derive_ddl_flowing_subcommands` をそのまま `r2db-api/src/r2db_api/ops.py` に当てた実測)

- 登録サブコマンドは 26。**DDL を流す集合 = `{upgrade-applications}`**、`--lock-timeout` が required かつ既定なしの集合も `{upgrade-applications}` → **今日の時点で等式は成立し、要素数 1**。
- psql に `-f` を渡す関数 = `{_run_upgrade_script}`。sink に当たるのは `_require_psql_16_or_newer`・`_run_upgrade_script`・`cmd_upgrade_applications` の 3 つ。`upgrade-status` は届かない。
- → WP-1 の後に 2 件、WP-2 の後に 3 件になる。

**(11) r2db の既存の型** (`r2db-api/src/r2db_api/ops.py`)

- `_die` :117-119 (stderr に `error: …`、exit 2)、`_require_env` :109、`_control_dsn` :122-123 (`R2DB_CONTROL_DSN`)、`_migrations_dir` :131-149 (`R2DB_MIGRATIONS_DIR`)、`_require_psql_16_or_newer` :1346、`_LOCK_TIMEOUT_VALUE_RE` :1366、`_validate_lock_timeout_value` :1369-1377、`_psql_connection_env` :1382、`_redact_connection_values` :1431、`_with_lock_timeout_option` :1473-1479、`_run_upgrade_script` :1485-1523、`cmd_upgrade_applications` :1527-。parser 登録は `_build_parser` の中 (:1686-1894。`upgrade-applications` は :1872-1887) で、`sub.add_parser(...)` → `p.add_argument(...)` → `p.set_defaults(func=cmd_*)` の型。
- 破壊的確認の既存機構は `_require_cli_confirmation` :320-358 (呼び出し元は :456 `delete-credential` と :709 `reset` の 2 つ)。`FoundationError("DESTRUCTIVE_CONFIRMATION_REQUIRED", …, status=409)` を `problem()` で 1 行 JSON にして stderr に出し `SystemExit(2)`。`details` は `required_confirmation`/`consequence`/`reversible_alternative`/`recovery` の 4 鍵で、D-2 が求める形と同じ。MitateDB 側は `_print_denial_and_exit(DestructiveConfirmationRequired(...))`。
- 確認句関数の置き場: 既存の CLI の 2 つ (`RESET_CONTROL_CREDENTIALS`・`delete_credential_confirmation_phrase`) は `structured.py` (実体は `delete_confirmation.py`) から import され、`r2db-api/tests/test_control_plane_store.py`:1298 `test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases` が object identity を assert する。**この検査はその 2 つだけを見る** (:1326-1328) ので、`ops.py` に新しい確認句の関数を置いても赤にならない (実測)。
- slug の書式は `_APPLICATION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,32}$")` (`r2db-api/src/r2db_api/control_plane.py`:67。MitateDB も同じ正規表現、`control_plane.py`:76)。`ops.py` は現在これを import していない。

**(12) pytest の PYTHONPATH と help の pin**

- root の `pyproject.toml` `[tool.pytest.ini_options]` が `pythonpath = ["r2db-api/src", "MitateDB-api/src", "conformance-tests"]` (:2) を持つので、**pytest 実行に `PYTHONPATH` の export は要らない**。手で `python -m r2db_api.ops --help` を叩くときだけ `PYTHONPATH=r2db-api/src` を付け、main checkout の `.venv/bin/python` を使う。
- r2db に help テキストを逐語で pin するテストは**無い** (`r2db-api/tests/` に `format_help`/`print_help` の参照 0 件、実測)。

### 1.4 却下した代替案

- **(1) `0005`/`0006`/`0007` を platform set に含める** — password を CLI 引数に通すことになる (守る条件 (d))。
- **(2) 配備 script を `ops` 呼び出しに変える** — D-4 (§1.3 (9) の pin が赤になり、別の変更クラスの領域に入る)。
- **(3) MitateDB の `ops` をコード共有する** — `RM` の P-6 に反する。
- **(4) deprovision の確認句を省き `0004` を流すだけにする** — 契約の `destructive_confirmation` と MitateDB の型に反する。
- **(5) `--lock-timeout` に既定値を置く** — MitateDB と R-66 の「必須・既定なし」に反する。
- **(6) deprovision の確認句を `delete_confirmation.py` (共有モジュール) に置き、SI-09 の `:784` の「1 度だけ」の主張を保つ** — 却下 (監督裁定 2026-09-23、R1-6)。確認句の材料は registry の値 (`provisioned_at`) で、data/schema 面の phrase が拠る cell 層には無い。MitateDB は同じ関数を `ops.py` に置いており、同型 pin (D-5) は同じ置き場を要する。→ `ops.py` に置き、`:784` の側を「5 面のうち 4 面は `structured.py` に 1 度だけ、deprovision は `ops.py` (peer 対称)」と述べる形に訂正する (D-8、§5.1 の 3)。

### 1.5 未確定で依頼者判断待ちの選択肢

無し (Class D、事後報告)。

### 1.6 設計レビュー 1 の反映 (2026-09-23、監督裁定として全件採用。R1-1〜R1-11)

未統合の起草版なので、訂正註ではなく**本文を直した** (v1.0 のまま)。裁定を要した 3 件は R1-2・R1-5・R1-6。

| # | 指摘 | 裁定 | 反映先 |
|---|---|---|---|
| R1-1 (高) | `_require_cli_confirmation` の docstring の言い換えは登録済みの塊なので、訂正記録の追記が要る | 採用 | §3.2 (`docs/code-history/r2db-api/ops.md` をパスに追加)、§3.3 の 13 (`## CH-0300` に `### correction: 2026-09-23` を追記、設計 §9.3 の規則、先例 CH-0538/CH-0539、`--register` の形式検査が緑) |
| R1-2 (高) | 同型 pin の 4 行を WP-1 に置くと、WP-1 単独では緑にできない行が残る | **裁定: 4 行と `147` への改名は全て WP-2 に移す** (WP-1 では書かない) | D-10、§2.1、§2.2、§2.3 (旧 21 を削除し 21〜23 に繰り上げ)、§2.4、§2.5、§3.1、§3.2、§2 冒頭の表 |
| R1-3 (中〜高) | M30 (parser から `--lock-timeout` を消す) は完了条件 10 (DDL 集合が 3 件) を赤にしない | 採用 | §3.4 の M30 を「`cmd_deprovision` から `_run_deprovision_script` の呼び出しを外す → 導出集合が 2 件に落ちる」に差し替え |
| R1-4 (中) | 導出が常に空を返す実装でも「導出 == 定数」は通り得る | 採用 | §2.3 に 4b (合成 SQL 2 本に導出を掛け、非空の期待 map と比べる)、§2.4 に M4b (基準 (iii) を外す → 4b が赤) |
| R1-5 (中) | `0008` の制約は retrofit の初回適用では 3 キーのまま残る (空の表では穴が閉じない) | **裁定: 基準を 3 つにし ((iii) 同じ table の同じ名前の制約を張り直す組)、表を `{0008: (0012,)}` で確定する** | D-1、§1.3 (2)、§2.3 の 4・5 (現物で非空に固定)、§2.4 の M4 |
| R1-6 (中) | 確認句を `ops.py` に置くと SI-09 `:784` の「共有モジュールに 1 度だけ」が崩れる。共有モジュールに置く案は検討したか | **裁定: 共有モジュール案は却下し `ops.py` に置く** (確認句の材料が registry の値で cell 層に無く、MitateDB と同じ置き場でなければ同型 pin が成り立たない) | §1.4 の (6)、§5.1 の 3 (`:784` は「5 面のうち 4 面は `structured.py`、deprovision は `ops.py` (peer 対称)」と述べる形に) |
| R1-7 (中) | §16 の「再適用は手で変えた値を既定に戻す」警告が、新しい経路の文言として残るか読めない | 採用 | §4.3 の 5 (runbook :1609-1612 の警告が残り、`apply-platform-migration --help` が `0008`/`0013` の再適用は代入である旨を述べる) |
| R1-8 (低〜中) | denial の前に registry を読むことの契約上の位置づけと、読み以外が起きないことの証拠が無い | 採用 | §5.1 の 3 (`:788` の訂正文に `evaluation_order` の位置の一文)、§3.3 の 3 (denial 時に registry の書き込み 0 行・`control_audit` 0 行) |
| R1-9 (低) | 前置きの fixture は r2db に既に先例が在る。registry の schema 名の出所も書くべき | 採用 | §1.3 (5) に `test_audit_query.py`:76-101・:215-233 と `test_application_audit.py`:70-84・:213-222 を併記、D-2 に「registry 読みは `_schema()` (`ops.py`:100-106) 経由」 |
| R1-10 (低) | 変異表に土台が緑であることを示す行が無い | 採用 | §2.4・§3.4・§5.4 の先頭に M0 (無変異、`expect=green`) |
| R1-11 (低) | 失敗時の出力の完了条件が粗く、確認句の指紋が r2db では何かを運用者が読めない | 採用 | §2.3 の 14 (失敗したファイルは `applied` にも `not run` にも入らない・部分適用の明示・全 run の再実行の指示・redaction の 3 点)、§3.3 の 13b (help)、§4.3 の 6 (runbook §5) |

## 2. WP-1 — `ops apply-platform-migration` と AST 検査

**並行 WP は無い** (運用条件 §1.2 の 16・17)。WP-1〜3 は同じ作業ツリー `.claude/worktrees/r90` で同じ実装担当が直列に行い、WP-4 は R-87 の統合後に行う。触るファイルの実名は次のとおりで、WP-4 だけが `security/` に触る。

| WP | 触るファイル (実名) |
|---|---|
| WP-1 | `r2db-api/src/r2db_api/ops.py`、`r2db-api/tests/test_ops_apply_platform_migration.py` (新規) |
| WP-2 | `r2db-api/src/r2db_api/ops.py`、`r2db-api/tests/test_ops_apply_platform_migration.py`、`r2db-api/tests/` の deprovision テスト (置き場は実装詳細)、`r2db-api/tests/test_audit_query.py`、`MitateDB-api/tests/test_audit_query.py`、`docs/code-history/r2db-api/ops.md` |
| WP-3 | `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/migrations/0004_…`・`0012_…`・`0013_…`・`0014_….sql` の**コメント行のみ**、`r2db-api/src/r2db_api/ops.py` の help 文字列のみ |
| WP-4 | `security/CONTROL_MAPPING.md`、`security/CONTROL_MAPPING_HISTORY.md` |

### 2.1 タスク

D-1・D-3・D-5 のとおり、`r2db-api/src/r2db_api/ops.py` に `apply-platform-migration` を足す。構成は MitateDB の現物 (`MitateDB-api/src/mitatedb_api/ops.py`:2620-2851) に倣い、定数 4 つ (`_PLATFORM_MIGRATION_FILENAMES`・`_PLATFORM_MIGRATION_VARIABLE_TABLE`・`_PLATFORM_MIGRATION_SUPERSEDED_BY`・psql 変数の抽出用の正規表現)、helper (`_resolve_platform_migration_file`・`_validate_platform_migration_run`・`_platform_migration_variables`)、`cmd_apply_platform_migration`、`_build_parser` への登録を置く。DSN は `_control_dsn()` のみ (§1.3 (11))。既存の `_validate_lock_timeout_value`・`_psql_connection_env`・`_with_lock_timeout_option`・`_redact_connection_values`・`_require_psql_16_or_newer` を使い、同じ役目の関数を作り直さない。AST 検査は新規ファイル `r2db-api/tests/test_ops_apply_platform_migration.py` に置く。**実 PostgreSQL の fixture はこの新規ファイルが自前で持ち、他のテスト module から import しない** (監督裁定 2026-09-23。`MitateDB-api/tests/test_ops_apply_platform_migration.py`:16-20 の先例。`0005`〜`0008` の前置きは fixture 自身の psql が password 変数を渡す — ops には渡さない、条件 (d))。形の細部は実装詳細。**同型 pin の 4 行と `147` への改名は本 WP では行わない** — 表の編集ごと WP-2 で行う (D-10、監督裁定 R1-2)。

### 2.2 触ってよいパス

- `r2db-api/src/r2db_api/ops.py` — `apply-platform-migration` の定数・helper・`cmd_*`・parser 登録のみ。既存のサブコマンドの挙動を変えない。
- `r2db-api/tests/test_ops_apply_platform_migration.py` (新規)。
- **触らない**: 両 peer の `tests/test_audit_query.py` (同型 pin は WP-2)、`r2db-api/migrations/` の SQL (WP-3 でコメント行のみ)、`r2db-api/deploy/` (D-4)、`security/`、`conformance-tests/`、`spec/`、`MitateDB-api/`。

### 2.3 完了条件 (assert 水準)

各テストは観測対象を 1 件以上 assert する (空振り禁止)。拒否系は終了コードと、**運用者の入力値が stderr に現れないこと**を併せて見る。

1. **未知の FILENAME と path separator を含む FILENAME を拒む** — exit 2、渡した値が stderr に現れない。
2. **migrations dir の外へ解決する symlink と、不在のファイルを拒む** — exit 2、値を非エコー。
3. **run の順序違いと重複を拒む** — exit 2、拒否文は必要な完全な run 名だけを示し、渡した並びを返さない。
4. **superseded-by の表が 4 本の SQL からの導出と一致する** (静的、§1.3 (2))。**表は `{0008: (0012,)}` で確定** (D-1 の裁定 R1-5) なので、導出は非空で、3 基準 ((i) 関数の `CREATE OR REPLACE`、(ii) role の同じ `SET`/`CONNECTION LIMIT`、(iii) 同じ table の同じ名前の制約) をテストの docstring に書く。
    - **4b**: **合成した SQL 2 本に導出を掛けると、非空の期待 map になる** (R1-4) — 3 基準それぞれが 1 組ずつ立つ最小の合成ソースを用意し、導出の戻りを期待の map と逐語で比べる (現物 4 本だけに頼らず、基準ごとに導出が働くことを固定する)。
5. **後続の欠落を拒む判定が働く** — `0008` を単独で与えると exit 2 になり、拒否文が `0008 0012` の完全な run を示す。`0008 0012` の run は通る (現物で固定する)。
6. **変数表が各ファイルの実 `:name` 参照からの導出と一致する** (静的。コメント行と `::` 型キャストを除く)。
7. **必要な変数の不足を拒む** — exit 2、同じ入力に対して常に同じ変数名を名指す (集合の反復順に依らない)。
8. **要らない変数の余剰を拒む** — exit 2。
9. **DSN は `R2DB_CONTROL_DSN` のみ** — 未設定なら exit 2、CLI に DSN を渡す口が無い (parser の引数に DSN 系が無いことを見る)。
10. **拒否のときに psql が起動しない** — `subprocess.run` を差し替え、1〜3・7・8 のいずれかの拒否で呼び出し 0 回。
11. **`PGOPTIONS` に `-c lock_timeout=<値>` が載り、DSN 由来の `options` を捨てない**。
12. **argv が `psql -v ON_ERROR_STOP=1 … -f <解決後の絶対 path>` で、各ファイルに要る変数だけを `-v` で渡す**。
13. **`--lock-timeout` が required・既定なし**で、値の書式検査が psql 起動前に起きる。
14. **失敗時の出力** (R1-11) — **失敗したファイルは `applied` にも `not run` にも入らない** (`applied` = 成功した分だけ、`not run` = 失敗したファイルより後の分だけ)、**部分適用があり得る旨と「全 run を先頭から再実行する」指示**を出す、**DSN の値が stderr に現れない** (redaction)。3 つを同じテストで assert する。
15. **`0008` の drift-then-restore** (実 PostgreSQL) — role の `statement_timeout` を動かし、再適用で戻る。宣言行 (`audit_writer_roles`) も再収束する。
16. **`0012` の drift-then-restore** (実 PostgreSQL) — 制約を落として再適用で戻る。
17. **`0013` の drift-then-restore** (実 PostgreSQL) — `CONNECTION LIMIT` を下げて再適用で戻る。
18. **`0014` の drift-then-restore** (実 PostgreSQL) — auditreader の `statement_timeout` を動かして再適用で戻る。
19. **AST: DDL を流すサブコマンドの集合 == `--lock-timeout` が required かつ既定なしの集合** (件数の literal を持たない等式)。
20. **AST: psql に `-f` を渡す関数の集合が非空で、その全てが `_with_lock_timeout_option` を呼ぶ** (名前の手書き一覧からではなく導出集合に対して見る)。
21. **来歴** — `tools/check_comment_provenance.py --base dd12657` が「§4.1 (1) 以外 0 行」(D-9)。出力を逐語で §8 に残す (**監査照合**)。
22. **`r2db-api/tests` 全体が緑** (基準 + 新規 N。N は実装担当が報告)。集計行を逐語で §8 に残す (**監査照合**)。
23. **下の対応表に対応の無い行が無い** (**監査照合**、本表)。

### 2.4 完了条件 → 変異

`mutate.py` は最初の失敗で止まるので、変異 1 件につきテスト 1 件を指す (すべて `expect=red`)。

| 完了条件 | 変異 | 期待 |
|---|---|---|
| (基準) | **M0: 無変異** | 対象ファイルが**緑** (`expect=green`。変異の土台が緑であることを先に示す) |
| 1 | M1: `_resolve_platform_migration_file` の「既知の名前か」の検査を外す | 1 のテストが赤 |
| 2 | M2: 同関数の `relative_to` による containment 検査を外す | 2 のテストが赤 |
| 3 | M3: `_validate_platform_migration_run` の昇順・重複の検査を外す | 3 のテストが赤 |
| 4 | M4: `_PLATFORM_MIGRATION_SUPERSEDED_BY` の `0008 -> (0012,)` の組を消す | 4 のテストが赤 |
| 4b | M4b: 導出の 3 基準のうち (iii) (同じ table の同じ名前の制約) を外す | 4b のテストが赤 |
| 5 | M5: `_validate_platform_migration_run` の後続の欠落の分岐を外す | 5 のテストが赤 |
| 6 | M6: `_PLATFORM_MIGRATION_VARIABLE_TABLE` の `0008` の変数を 1 つ削る | 6 のテストが赤 |
| 7 | M7: `_platform_migration_variables` の不足の分岐を外す | 7 のテストが赤 |
| 8 | M8: 同関数の余剰の分岐を外す | 8 のテストが赤 |
| 9 | M9: parser に DSN を受ける引数を足し、`cmd_*` がそれを優先する | 9 のテストが赤 |
| 10 | M10: `cmd_apply_platform_migration` で run の検証を psql の実行より後ろに動かす | 10 のテストが赤 |
| 11 | M11: `env["PGOPTIONS"]` を `_with_lock_timeout_option` を通さず上書きする | 11 のテストが赤 |
| 12 | M12: argv から `-v ON_ERROR_STOP=1` を落とす | 12 のテストが赤 |
| 13 | M13: `--lock-timeout` を `required=False`・既定 `"5s"` にする | 13 のテストが赤 |
| 14 | M14: 失敗時の `_redact_connection_values` を外す | 14 のテストが赤 |
| 15 | M15: `_PLATFORM_MIGRATION_FILENAMES` から `0008` を外す | 15 のテストが赤 |
| 16 | M16: 同表から `0012` を外す | 16 のテストが赤 |
| 17 | M17: 同表から `0013` を外す | 17 のテストが赤 |
| 18 | M18: 同表から `0014` を外す | 18 のテストが赤 |
| 19 | M19: `upgrade-applications` の `--lock-timeout` を `required=False` にする | 19 のテストが赤 |
| 20 | M20: `cmd_apply_platform_migration` から `_with_lock_timeout_option` の呼び出しを外す | 20 のテストが赤 |
| 21・22 | 監査照合 (道具の出力・集計行を逐語で §8 に残す) | — |
| 23 | 監査照合 (本表) | — |

### 2.5 道具の引数 (main checkout を cwd にし、`SP` を export する)

- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r90 -- r2db-api/tests/test_ops_apply_platform_migration.py -q`
- 報告前に 1 回: `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r90 -- r2db-api/tests -q`
- `tools/dev/mutate.py "$SP/r90-mutations.json" -C .claude/worktrees/r90 --wait 1800`
- 来歴: `.venv/bin/python tools/check_comment_provenance.py --base dd12657` (作業ツリーを cwd にする)
- 変更クラス: `.venv/bin/python tools/change_class.py` を実測して報告に書く。
- python は main checkout の `.venv/bin/python`。pytest は `pyproject.toml` の `pythonpath` で解決するので `PYTHONPATH` の export は要らない (§1.3 (12))。手で `python -m r2db_api.ops --help` を叩くときだけ `PYTHONPATH=r2db-api/src` を付ける。**終了コードは pipe の外で取る** (`… > out.txt; rc=$?`)。
- `tools/dev/gate.py` と `tools/dev/finalize.py`、pytest の直接実行は**監督のみ**。

## 3. WP-2 — `ops deprovision`

### 3.1 タスク

D-2・D-3・D-5 のとおり、`r2db-api/src/r2db_api/ops.py` に `deprovision` を足す。構成は MitateDB の現物 (`MitateDB-api/src/mitatedb_api/ops.py`:514-537・:752-796・:3054-3072) に倣い、固定文言 2 つ (`consequence`・`reversible_alternative`)、`_deprovision_confirmation_phrase`、registry から `provisioned_at` を読む lookup、`_run_deprovision_script`、`cmd_deprovision`、parser 登録を置く。denial は §1.3 (11) の既存機構の形に合わせる。slug の書式は `control_plane._APPLICATION_ID_PATTERN` を使い、**DB に触る前**に検査する。WP-1 で書いた 2 つの固定 (DDL 集合 3 件・psql `-f` 関数 3 つ) は本 WP で緑になる。**同型 pin の 4 行と `147` への改名も本 WP で行う** (D-10 の R1-2。両 peer の `tests/test_audit_query.py` の 3 箇所 = 表の本体・全文 assert・`len`、およびテスト名。§1.3 (6))。

### 3.2 触ってよいパス

- `r2db-api/src/r2db_api/ops.py` — deprovision の追加と parser 登録のみ。既存のサブコマンドの挙動を変えない。
- `r2db-api/tests/test_ops_apply_platform_migration.py` — AST の 3 件固定の完了条件のみ。
- `r2db-api/tests/` の deprovision テスト (新規ファイル可。置き場は実装詳細)。
- `r2db-api/tests/test_audit_query.py` と `MitateDB-api/tests/test_audit_query.py` — `_ISOMORPHIC_TARGETS` の 4 行・全文 assert・`len` の数・pin テスト名の 3 箇所のみ (§1.3 (6))。他の行は変えない。
- `docs/code-history/r2db-api/ops.md` — **`## CH-0300` への訂正記録の追記のみ** (R1-1)。既存の fenced block と既存の訂正は書き換えない。
- **触らない**: `r2db-api/migrations/0004_deprovision_application.sql` の SQL 本文 (D-2)、配備 script (D-4)、`security/`、`conformance-tests/`、`spec/`。

### 3.3 完了条件 (assert 水準)

1. **slug の書式不正を DB に触る前に拒む** — psql も psycopg も起動しない (差し替えで呼び出し 0 回)。
2. **未登録 slug と「登録のみで未 provision」の行を拒む** — `0004` を流さない。
3. **`--confirm` 無し・不一致で JSON の denial** — exit 2、`required_confirmation`/`consequence`/`reversible_alternative` を含み、`required_confirmation` が確認句と逐語一致する。`0004` は流れない。**denial のとき registry への書き込みが 0 行、`control_audit` の行も 0 行** (R1-8。読みは起きるが、状態は何も変わらない。実 PostgreSQL で前後を数える)。
4. **確認句が `provisioned_at` に紐づく** — 同じ slug を deprovision して再 provision すると確認句が変わる (実 PostgreSQL)。
5. **一致で `0004` が流れ、DB と 2 つの role が消える** (実 PostgreSQL)。
6. **credential 行が残ると `0004` が拒む** — `0005` を流した platform で、残留のあるまま `--confirm` を合わせても DB と role が残る (§1.3 (4))。
7. **`--lock-timeout` が required・既定なし**で、値の書式検査が psql 起動前に起きる。
8. **argv が `psql -v ON_ERROR_STOP=1 -v app_slug=<slug> -f <0004 の path>` で、`PGOPTIONS` に `-c lock_timeout=<値>` が載る**。
9. **失敗時に redaction が効く** — DSN の値が stderr に現れない。
10. **AST: DDL を流すサブコマンドの集合が厳密に `{apply-platform-migration, upgrade-applications, deprovision}`** で、設定だけを書くサブコマンド (`declare-surfaces`・`declare-process-ceilings`・`set-platform-timeouts` 等) を含まない。
11. **AST: psql に `-f` を渡す関数の集合が厳密に `{_run_upgrade_script, _run_deprovision_script, cmd_apply_platform_migration}`**。
12. **同型 pin が両 peer で緑** — 本 WP で 4 行を足して `_ISOMORPHIC_TARGETS` 147 行、全文 assert と `len` を揃え、pin テスト名を `…_147_rows` に改め、4 行とも正規化後に byte 一致する (§1.3 (6))。表の編集の diff を §8 に逐語で残す。
13. **`_require_cli_confirmation` の docstring を同一変更セット内で言い換える** (D-9 の裁定) — `r2db-api/src/r2db_api/ops.py`:331 の「in both callers below」「not even a connection is opened」を、3 つ目の呼び出し元 (確認句の計算に registry 読みが要る) を含む現物どおりの記述に直す。**`docs/code-history/r2db-api/ops.md` の `## CH-0300` (:321) に `### correction: 2026-09-23` の節を追記する** — `reason` / `old` / `new` を設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §9.3 の規則どおりに書き (`old` は受け皿の原文に逐語で 1 回、保護参照を減らさない)、先例は `docs/code-history/MitateDB-api/ops.md` の CH-0538 (:611-640)・CH-0539。**`tools/check_comment_provenance.py --register` の形式検査が緑**であること。旧文と新文、`--register` の出力行を §8 に逐語で残す (**監査照合**)。
    - **13b**: **help が確認句の指紋を説明する** (R1-11) — `deprovision` の help に、`@registered=` が r2db では registry の **`provisioned_at`** の指紋であり、同じ slug を deprovision して再 provision すると確認句が変わる旨を書く。`--help` の出力を §8 に逐語で残す (**監査照合**)。
14. **来歴** — `tools/check_comment_provenance.py --base dd12657` が「§4.1 (1) 以外 0 行」(13 の言い換えを含めて。R-68 の経路)。出力を逐語で §8 に残す (**監査照合**)。
15. **`r2db-api/tests` と `MitateDB-api/tests` が緑** (集計行を逐語で §8 に残す、**監査照合**)。
16. **下の対応表に対応の無い行が無い** (**監査照合**、本表)。

### 3.4 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| (基準) | **M0: 無変異** | 対象ファイルが**緑** (`expect=green`) |
| 1 | M21: slug の書式検査を registry の読みの後ろに動かす | 1 のテストが赤 |
| 2 | M22: 未登録・未 provision の拒否を握り潰して確認句の計算へ進める | 2 のテストが赤 |
| 3 | M23: `--confirm` の一致判定を「非 None なら通す」に緩める | 3 のテストが赤 |
| 4 | M24: 確認句の digest の素材から `provisioned_at` を外す (slug だけにする) | 4 のテストが赤 |
| 5 | M25: `_run_deprovision_script` の `subprocess.run` を実行せず 0 を返す | 5 のテストが赤 |
| 6 | M26: `-v app_slug=` を渡さず、`0004` の `\gset` より前に別の値を注入する (残留ガードを迂回する形) | 6 のテストが赤 |
| 7 | M27: `deprovision` の `--lock-timeout` を `required=False`・既定 `"5s"` にする | 7 のテストが赤 |
| 8 | M28: `_run_deprovision_script` の argv から `-v ON_ERROR_STOP=1` を落とす | 8 のテストが赤 |
| 9 | M29: 同関数の失敗時の `_redact_connection_values` を外す | 9 のテストが赤 |
| 10 | M30: `cmd_deprovision` から `_run_deprovision_script` の呼び出しを外す (成功時に何も流さない) | 導出集合が 2 件に落ち、10 のテストが赤 |
| 11 | M31: `_run_deprovision_script` の argv の `"-f"` を `"--file"` に変える | 11 のテストが赤 |
| 12 | M32: r2db 側 `_resolve_platform_migration_file` の本体の字下げを 1 段変える (docstring 以外を 1 箇所) | 12 のテスト (両 peer の同型性テスト) が赤 |
| 13・13b・14・15 | 監査照合 (旧文と新文、訂正記録、`--register` と `--help` の出力、集計行を逐語で §8 に残す) | — |
| 16 | 監査照合 (本表) | — |

### 3.5 道具の引数

- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r90 -- r2db-api/tests/test_ops_apply_platform_migration.py r2db-api/tests/test_audit_query.py MitateDB-api/tests/test_audit_query.py -q` (deprovision のテストファイルを足す)
- 報告前に 1 回: `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r90 -- r2db-api/tests -q`
- `tools/dev/mutate.py "$SP/r90-mutations.json" -C .claude/worktrees/r90 --wait 1800`
- 訂正記録の形式検査: `.venv/bin/python tools/check_comment_provenance.py --register` (完了条件 13)。
- 他は §2.5 と同じ。

## 4. WP-3 — runbook・migration ヘッダ・help

### 4.1 タスク

D-7 と R1-7・R1-11 のとおり、§1.3 (8) に挙げた runbook の 7 箇所と migration ヘッダ 5 箇所の手動 `psql -f` を、`python -m r2db_api.ops apply-platform-migration … --lock-timeout <値>` / `python -m r2db_api.ops deprovision <slug> --confirm <phrase> --lock-timeout <値>` の案内に置き換える。**段落単位で現物と照合する** — 置き換えた行の周りの説明文 (「idempotent -- safe to re-run, takes no `-v` variables」「Applying it by hand …」「This drops that application's entire database …」など) が新しい経路と矛盾しないところまで直す。`0004` の credential 残留のエラー例 (:524-528) は、`deprovision` の出す文言と齟齬が出ないようにする。help テキストは runbook の該当節を名指す (`0013` = §4、`0004` = §5、`0008` = §16、`0012` = §18、`0014` = §19。§1.3 (8))。SQL は**コメント行だけ**を触り、本文を変えない (先例: R-93。migration ファイルの hash は ledger に記録されないので配備済みホストに影響しない)。

### 4.2 触ってよいパス

- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` — §1.3 (8) の 7 箇所 (`0008` を含む) とその段落。
- `r2db-api/migrations/0004_deprovision_application.sql`:7-8、`0008_platform_declarations_and_writer_timeouts.sql`:11-12、`0012_process_ceilings.sql`:16、`0013_role_connection_limits.sql`:23、`0014_auditreader_statement_timeout.sql`:12 — **コメント行のみ**。
- `r2db-api/src/r2db_api/ops.py` — `apply-platform-migration`/`deprovision` の help 文字列のみ。
- **触らない**: SQL 本文、`r2db-api/deploy/` (D-4)、`security/`、`conformance-tests/`、`spec/`。

### 4.3 完了条件 (assert 水準)

1. **runbook の 7 箇所が `ops` の案内になっている** — `0013` (:373-375)、`0004` (:493-497・:524)、`0008` (:1613-1617)、`0012` (:1895・:1921)、`0014` (:1988)。置き換え後の `grep -n "migrations/000[48]_\|migrations/001[234]_"` の結果を逐語で §8 に残す (**監査照合**)。
2. **周囲の段落が新しい経路と矛盾しない** — 置き換えた各箇所の前後の段落を読み直し、直した文と直さなかった文を §8 に列挙する (**監査照合**)。
3. **migration ヘッダ 5 箇所 (`0004`/`0008`/`0012`/`0013`/`0014`) が `ops` の案内になっている**。diff が**コメント行だけ**であること (SQL 本文の diff 0 行) を `git diff` で見せる (**監査照合**)。
4. **help が runbook の節を名指す** — `python -m r2db_api.ops apply-platform-migration --help` と `… deprovision --help` の出力を逐語で §8 に残す (**監査照合**)。
5. **§16 の re-apply 警告が新しい経路の文言として残る** (R1-7) — runbook :1609-1612 の「a re-run resets a hand-changed timeout back to the shipped default, so use `ops set-platform-timeouts` for real changes」が `apply-platform-migration` の案内の側でも成り立つ形で残っていること。あわせて **`apply-platform-migration --help` が `0008`/`0013` の再適用は代入 (最終値に収束する) である旨を述べる**。`--help` の出力と当該段落を §8 に逐語で残す (**監査照合**)。
6. **runbook §5 が確認句の指紋を説明する** (R1-11) — `deprovision` の案内に、`@registered=` が registry の **`provisioned_at`** の指紋で、deprovision → 再 provision で確認句が変わる旨を書く (**監査照合**)。
7. **`tools/check_doc_refs.py` が 0 件**、`tools/dev/pt.py … r2db-api/tests -q` の集計が WP-2 の終わりと同数 (**監査照合**)。
8. **来歴** — `--base dd12657` が「§4.1 (1) 以外 0 行」(**監査照合**)。
9. **下の対応表に対応の無い行が無い** (**監査照合**、本表)。

### 4.4 完了条件 → 変異

本 WP は文書とコメントと help 文字列だけを変え、挙動を変えないので**変異を持たない** (土台の緑だけを M0 で示す)。1〜9 はすべて**監査照合**とし、照合の対象 (`grep` の結果、`git diff` の要約、`--help` の出力、道具の出力行) を逐語で §8 に残す。挙動の側は WP-1・WP-2 の変異が担保する。

| 完了条件 | 変異 | 期待 |
|---|---|---|
| (基準) | **M0: 無変異** | `r2db-api/tests` が**緑** (`expect=green`) |
| 1〜9 | 監査照合 (照合対象を逐語で §8 に残す) | — |

### 4.5 道具の引数

- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r90 -- r2db-api/tests -q`
- `.venv/bin/python tools/check_doc_refs.py` (作業ツリーを cwd にする)
- `.venv/bin/python tools/check_comment_provenance.py --base dd12657`
- 他は §2.5 と同じ。

## 5. WP-4 — `security/CONTROL_MAPPING.md` (R-87 の統合後)

### 5.1 タスク

D-0・D-8 のとおり。**着手の前提**: R-87 が main に統合済みで、本作業ツリーを main に ff してから始める (運用条件 §1.2 の 16。R-87 が版 2.23 を取るので、本件は次の版になる)。

1. `security/CONTROL_MAPPING.md:630` を **in place で書き換える** (Update convention、前文 :11-24)。peer 差は解消する — r2db-api も 3 サブコマンド全てに必須の `--lock-timeout` を持ち、AST 由来の集合で固定していること、初回配備の script だけが `lock_timeout` 無しで流すこと (D-4、許容として残る差) を現在形で書く。**旧文は逐語・無編集で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` (:137) へ移す。**
2. SI-09 の `### r2db-api` の block (:778) に、`apply-platform-migration` と `deprovision` の主張を**追記**する。形は SI-09 の `### MitateDB-api -- platform upgrade` (:824-846、特に :828 の受理条件、:833 の AST 検査、:839 の runbook 手順) に倣い、**証拠テスト名を伴う**。
3. 同 block の 2 つの主張を **in place で訂正する** (D-8 の裁定、Update convention)。**`:784`** —「Phrase construction for all 4 gated surfaces … is defined exactly once in the shared module `structured.py`」: **5 面のうち 4 面は今までどおり `structured.py` に 1 度だけ、deprovision の 1 面は `ops.py`** (MitateDB と同じ置き場で peer 対称。確認句の材料が registry の値で cell 層に無い。§1.4 の (6)、D-5) と述べる形に直す。**`:788`** —「The out-of-band ritual CLI gates … before any store/DSN is constructed, so a wrong `--confirm` never touches the database」: deprovision の確認句は `provisioned_at` の読みを要するので、`reset`/`delete-credential` と同じ性質ではない (誤った `--confirm` でも registry の**読み**は起きる。書き込みと `0004` は起きない)。**この読みは契約 `destructive_confirmation` の `evaluation_order` に従う位置にある** (target-existence の解決の後、precondition の評価の前。R1-8) の一文を添える。**旧文 2 本は逐語・無編集で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` (:238) へ移す。**
4. 版数行 (:5) は **監督が統合時に割り当てる** — 実装担当は版数を書かず、書き換えた主張と履歴へ移した旧文を報告する (運用条件 §1.5 の 34・35)。

### 5.2 触ってよいパス

- `security/CONTROL_MAPPING.md` — `:630` の行、SI-09 の `### r2db-api` の block (追記と `:784`・`:788` の in place 訂正)、および前文 :28-31 の最長 block の実測 (変わる場合のみ)。
- `security/CONTROL_MAPPING_HISTORY.md` — `## SI-08` (:137) と `## SI-09` (:238) への旧文の追加のみ。
- **触らない**: 他の SI、他の peer の block、`conformance-tests/`、`spec/`、`r2db-api/`、`MitateDB-api/`。

### 5.3 完了条件 (assert 水準)

1. **`:630` が in place で書き換わり、旧文が逐語で `## SI-08` に在る** — 旧文 (616 文字) と新文を §8 に逐語で残す (**監査照合**)。
2. **SI-09 の r2db-api の block に 2 サブコマンドの主張が在り、証拠テスト名を伴う**。
3. **`:784` と `:788` が in place で訂正され、旧文 2 本が逐語で `## SI-09` に在る** — 旧文と新文を §8 に逐語で残す (**監査照合**)。訂正後の 2 文が deprovision を含めて現物どおりであること (5 つ目の gate される面、確認句は `ops.py`、denial の前に registry の読みが起きる)。
4. **`conformance-tests/test_control_mapping_register.py` が緑** — block 長・物理行長・テスト名の解決・位置参照 (`file:line`) の解決を含む。
5. **block 長と物理行の実測**を §8 に残す (**監査照合**)。現況は SI-08 の r2db-api 既定 block 10,304 / SI-09 の r2db-api 2,211 / cap 15,200・1,400 (§1.3 (7))。前文 :28-31 の「最長 block」の記述が実測と合っていること (合わなければ同じ変更セットで直す)。名前つき block は足さない (SI-09 の r2db-api は既定 block のまま)。
6. **`tools/check_doc_refs.py` が 0 件**、`tools/change_class.py` が `class=D` (**監査照合**)。
7. **下の対応表に対応の無い行が無い** (**監査照合**、本表)。

### 5.4 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| (基準) | **M0: 無変異** | `conformance-tests/test_control_mapping_register.py` が**緑** (`expect=green`) |
| 2 | M33: 追記した主張の証拠テスト名の 1 つを、存在しないテスト名に差し替える | `test_control_mapping_register.py` のテスト名解決が赤 |
| 4 | M34: 追記した主張の位置参照 (`file:line`) の 1 つを、行数の範囲外に差し替える | 同ファイルの位置参照の検査 (R-88 の node id 15) が赤 |
| 1・3・5・6・7 | 監査照合 (旧文と新文、実測、道具の出力を逐語で §8 に残す) | — |

### 5.5 道具の引数

- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r90 -- conformance-tests/test_control_mapping_register.py -q`
- `tools/dev/mutate.py "$SP/r90-mutations.json" -C .claude/worktrees/r90 --wait 1800` (M33・M34)
- `.venv/bin/python tools/check_doc_refs.py`、`.venv/bin/python tools/change_class.py`
- 他は §2.5 と同じ。

## 6. 範囲外 (本件では直さない)

- **配備 script の `ops` 化** — `r2db-api/deploy/scripts/part1_provision_host_and_db.sh` の `psql -f` 列 (D-4、§1.3 (9))。
- **`0005`/`0006`/`0007` の再適用経路** — password 変数を要るので `apply-platform-migration` に載せない (D-1、§1.4 (1))。これらを稼働中クラスタに流し直す手順は runbook の手動のまま残る。
- `0001`/`0002` (bootstrap-only)、`0003`、`0009`〜`0011` (`upgrade-applications` の領分)。
- MitateDB-api の `src/` (本件で変えるのは MitateDB 側の `tests/test_audit_query.py` の同型 pin の 3 箇所だけ)。
- R-91 (`max_connections` を起動時にも `ops verify-declarations` にも検査しない、`RM`:516) と R-92・R-93 の既決事項。

## 7. レビューと受け入れ

- **設計レビュー 1 回** — 本書に対して実施済み (Class D、D-0)。反映は §1.6。
- **コードレビュー 2 回** — WP-1 + WP-2 の実装後に 1 回、WP-3 + WP-4 の実装後に 1 回 (それぞれ別に起動した `reviewer`、`ROLES`)。
- **受け入れ監査 1 回** (`evidence-auditor`)。受け入れ判定は監督が、完了条件 → 変異の対応表・監査照合の逐語記録・集計行を照らして行う。
- **完了ゲート**は監督が単独で行う (`tools/dev/gate.py -C .claude/worktrees/r90 --label r90`)。実装担当は `gate.py`・`finalize.py`・pytest の直接実行を行わない。
- **訂正の扱い**: 本書への訂正は §1〜§7 の本文を書き換えず、§8 に訂正註として日付とともに追記する。

## 8. 実施記録 (統合時に監督が埋める)

### 8.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-23)】同型 pin の件数 (D-5・§3.3 の 12)。** 起草時の 4 行 (147) ではなく **7 行 (150)**: コードレビュー 1 の F4 で `_PSQL_VARIABLE_RE` が両 peer 同綴りで未 pin と分かり、監督裁定で MitateDB と同じ置き場 (src) に `_strip_sql_line_comments`・`_extract_psql_variables` を揃えて 3 行を足した (P-6「同名の helper は同型 pin」)。件数 pin のテスト名は両 peer 4 箇所と `security/CONTROL_MAPPING.md:681` (F-17 の証拠名、Update convention で旧行は履歴へ) を 150 に。
- **【訂正註 2 (2026-09-23)】M0 (無変異、`expect: green`)。** `tools/dev/mutate.py` は `old == new` を `DevError` で弾くので M0 は表現できない。各 mutate 直前の緑 pt (`28`/`42`/`43 passed`) を代用証拠とする (受け入れ監査の註 2)。
- **【訂正註 3 (2026-09-23)】§2.2 の「`MitateDB-api/` を触らない」。** コードレビュー 1 の F5 (fixture の tempdir 残骸) の裁定で `MitateDB-api/tests/test_ops_apply_platform_migration.py` の fixture teardown に `shutil.rmtree` を足した (2 行、テストのみ)。fixture 外の `mkdtemp` 4 箇所と直接 `_bootstrap()` 呼び 1 件は残る (台帳 R-99)。
- **【訂正註 4 (2026-09-23)】§4.3 の (7) `r2db-api/tests` の件数。** 1415 → 1416 の差はコードレビュー 1 の F3 (`--confirm` 省略のテスト 1 件) で、WP-3 由来ではない。
- **【監督裁定 1】** コードレビュー 1 の裁定 (F1〜F5) は `$SP/r90-return-1.md` のとおり。F1 = runbook §16 / 0008 ヘッダ / §18 の 0008 単独コマンドを `0008 0012` の 2 ファイル指定に (閉包検査が単独を拒む)、F2 = 導出 docstring の偽の断言を残存穴込みに (台帳 R-98)、F3 = `--confirm` 省略のテスト + M23b、F4 = 上の訂正註 1、F5 = 訂正註 3。
- **【監督裁定 2】** 受け入れ監査の疑義: (a) `_run_deprovision_script`/`_run_upgrade_script` が `-f` に渡す path を解決・包含検査しない件は両 peer に共通の既存の形なので本件では触らず台帳 R-97 に起票。(b) 導出の綴りの穴は R-98。(c) runbook・0008 ヘッダの `R-90 WP-1/WP-2` トークンは先例 (`R-45 WP-E; R-57 WP-1`) に合わせて残す。
- **【訂正註 5 (2026-09-23)】WP-4 のコードレビュー (中 2・低 2、全件反映)。** HISTORY の題 4 箇所は新版 2.24 を書く (実装は R-87 の 2.23 を書いていた)。`:793`・`:796` の断言に対応する証拠名 (DSN 引数なし / env 必須 / `--lock-timeout` 必須・既定なし / 等式テスト) を足した — 確定文ファイル `$SP/r90-final/si09_r2db_added.txt` は現物から更新。**§5.4 の M34 (位置参照の変異) は該当なし** (追記 6 本に `file:line` が無い) — 実行しない。M33 は実行 (`mutate: 1 mutations, 1 as expected`)。ブロック長は register の `_subblock_block_text` で測り直した値を §8.2 に載せる (実装報告の値は見出し行込みで +100 前後大きかった)。
- **【監督裁定 3】** `check_comment_provenance.py` を tests に掛けると pin 改名で §4.1 (2) が出るという実装担当の報告は、来歴検査の範囲が両 peer の `src/` だけ (`docs/design/CODE_COMMENT_PROVENANCE_V1.md`:93) なので対象外 — 対応不要。


### 8.2 実施と受け入れ

- **差分**: `r2db-api/src/r2db_api/ops.py` (`apply-platform-migration`: `_PLATFORM_MIGRATION_FILENAMES` = 0008/0012/0013/0014、変数表 0008 のみ、`_PLATFORM_MIGRATION_SUPERSEDED_BY = {0008: (0012,)}` (基準 (iii) `platform_declarations_key_check` の再定義)、`_resolve_platform_migration_file`・`_validate_platform_migration_run`・`_platform_migration_variables`・`_PSQL_VARIABLE_RE`・`_strip_sql_line_comments`・`_extract_psql_variables`; `deprovision`: slug 書式 → `--lock-timeout` → `R2DB_CONTROL_DSN` → `_lookup_application_provisioned_at` (`_schema()` 経由) → `_deprovision_confirmation_phrase` (指紋は `provisioned_at`) → JSON denial exit 2 / 一致で `0004` を psql (`PGOPTIONS` lock_timeout); `_require_cli_confirmation` docstring の言い換え (CH-0300 の訂正記録 `docs/code-history/r2db-api/ops.md`); parser に `description=`)、新規 `r2db-api/tests/test_ops_apply_platform_migration.py` (43 テスト、自前の実 PostgreSQL fixture、AST 検査 2 本、drift-then-restore 4 本、合成 SQL の導出 4b、denial の書き込み 0)、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` +7 行、143 → 150)、`MitateDB-api/tests/test_ops_apply_platform_migration.py` (fixture の `rmtree` のみ)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (手動 `psql -f` 7 箇所 + §16/§18 をサブコマンドに、reset 警告を保持)、migrations 5 本のヘッダ (SQL 本文 byte 不変)、`security/CONTROL_MAPPING.md` (版 2.24: `:630`・`:681`・`:786`・`:789` in place、SI-09 r2db に 6 本追記)、`security/CONTROL_MAPPING_HISTORY.md` (旧 4 行を逐語)。`tools/change_class.py` → `class=B` (パスのみ)、`_ISOMORPHIC_TARGETS` 集合の増減と `security/` で **D**。
- **道具の出力行**: `pt: 118 passed` (両 peer の当該ファイル、r2db 43 + MitateDB 75)、`pt: 6 passed, 131 deselected` (`-k isomorphic`)、`pt: 1416 passed in 111.81s` (`r2db-api/tests`)、`pt: 1422 passed, 2 subtests passed in 143.36s` (`MitateDB-api/tests`)、`pt: 58 passed` (register 単独)。変異 `mutate: 21 mutations, 21 as expected` (WP-1 M1〜M20 + M4b)、`mutate: 12 mutations, 12 as expected` (WP-2 M21〜M32)、`mutate: 3 mutations, 3 as expected` (M23b/M33/M34)。`tools/check_control_mapping_split.py --base 43c408c --expect "missing=4 added=10 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` 終了 0。来歴 `--base dd12657 r2db-api/src/r2db_api/ops.py` は §4.1 (1) の 1 行のみ、`--register` OK 87/430。`check_doc_refs` 0、`public_value_scan` 0。ブロック長 (register の `_subblock_block_text`) SI-08 r2db 既定 10,648 / SI-09 r2db 既定 7,093 (上限 15,200、最長は SI-09 MitateDB-api platform upgrade 12,747 で不変)、最長物理行 `:651` 1,384 不変。変異 (WP-4) `mutate: 1 mutations, 1 as expected` (M33、M34 は該当なし)。
- **設計レビュー 1** (高 2・中 6・低 3、全件反映。§1.6)、**コードレビュー 2 回** (WP-1〜3: 高 1・中 2・低 2 → 差し戻し 1 `$SP/r90-return-1.md`; WP-4: 中 2・低 2 → 差し戻し 2 `$SP/r90-return-2.md`; いずれも全件反映)、**受け入れ監査 1** (WP-1〜3、未充足 0、註 6 = 訂正註 1〜4 と裁定 2)。
- **完了ゲート** (監督単独、最終の木、`--label r90`): `gate: 3952 passed, 2 subtests passed in 330.31s (0:05:30)`、`judge=PASS`、実行クラスタ差分 0 (直前の main 3909 + 43); WP-4 の差し戻し 2 の後の最終の木で再実行 (`--label r90b`): `gate: 3952 passed, 2 subtests passed`、`judge=PASS`、差分 0。
- **最終判定**: 受け入れ。Class D の決定 (`CONTROL_MAPPING` 2.24 の 4 行の訂正と 6 本の追記、同型 pin 集合 +7) は 2026-09-19 の委任の下で監督が下し、引き継ぎ書で依頼者へ事後報告する。台帳 R-90 を閉じ (v1.100)、R-97〜R-99 を起票した。
