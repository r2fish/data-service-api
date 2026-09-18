# deprovision の接続の締め出しと一時的な role 付与 設計メモ (v1.0)

- 状態: **監督確定 (2026-09-19)。設計レビュー 2 回を反映済み**。作業指示書は `docs/work-orders/WORK_ORDER_R54_DEPROVISION_LIVE_CONNECTIONS_V1.md`。依頼者判断待ちの項目は無い (§11)。
- 台帳: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-54** (`RM`:448)。
- 起票: 2026-09-18 (R-45 WP-D の設計レビュー 1 回目の佐 1 件。当時の扱いは作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`:556 の D1-8「provision role 自身に `GRANT pg_signal_backend` を実行させる既存の形は触らない (台帳へ起票した)」)。**起票時の理解より深い問題だった** — §1。
- 改版: v0.1 (2026-09-19) 起草。v0.2 (2026-09-19) 監督裁定 1〜7 を反映。**v0.3 (2026-09-19) 設計レビュー 1 回目 (13 件) と監督裁定 R-1〜R-7 を反映**: **`WITH (FORCE)` を不採用とし (M-11)、採用形を H-1 の 6 段の順序に差し替えた** (§4 D-2R)、FORCE 案を X-5 として残した (§8)、追随一覧に 4 件を足し範囲外を明記した (§5)、完了条件と変異を組み直した (§6)、主張の置き場を SI-00 に確定した (§9.1)、同名ヘルパを置かない方針でクラスは C のまま (§9)、失敗時の状態と掃除手順を表にした (§4.1)。**本文の行は消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。**v1.0 (2026-09-19) 設計レビュー 2 回目 (F-1〜F-8) と監督裁定を反映**: (4) に `pg_database` の存在検査を足し (F-1)、(2) の形を `format()` + `\gexec` に直し (F-2)、`datallowconn=false` の残骸が fleet 運用コマンドを degrade させる旨を足し (F-3)、事前検査の例外は**リトライ対象に含めない**と裁定し (F-4)、(2)(3)(4) の枝の位置を確定し (F-5)、完了条件 2・5 を**構造テスト**で pin すると裁定し (F-6)、D-1 に到達可能性の 1 文 (F-7) と追随先 1 件 (F-8) を足した。あわせて MitateDB `0001`:176-181 は**触らない**、SQL と `tests/test_postgres.py` は全部 WP-1 に寄せる、と裁定した。**行は消していない**。
- 公開規律: `OPERATING_CONDITIONS.md` §2 の 13、§1.9。本メモの実測はすべて使い捨ての PostgreSQL 16 クラスタで採ったもので、本番の DSN・ホスト名・値・作業機のパスを 1 つも含まない。接続は一般形 (「その application の database への client backend 1 本」等) で書く。
- 実測の出所: 監督の実測記録 **M-1〜M-13・H-1・H-2** (2026-09-19、PostgreSQL 16.14、使い捨てクラスタ)。数値とエラー文は逐語で引き、言い換えない (`OPERATING_CONDITIONS.md` §1.5 の 34、35)。

---

## 1. 問題

R-54 の起票は「runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §9 項目 3 (:1651-1664) が provision role 自身に `GRANT pg_signal_backend` (:1658) を実行させる形で、権限の出所 (誰がその GRANT を実行できるのか) が手順から読めない」だった。実測で、問題はそれより深いと分かった。

- **(a) 自己付与は拒否される** — provision role として `GRANT pg_signal_backend TO prov` は
  `DETAIL: Only roles with the ADMIN option on role "pg_signal_backend" may grant this role.` で失敗する (M-1)。すなわち runbook 項目 3 の手順は、書かれた role では実行できない。
- **(b) 他者が素の GRANT をしても効かない** — superuser が `GRANT pg_signal_backend TO prov` を行うと `pg_auth_members` は `inherit_option=f, set_option=t, admin_option=f` になり、terminate は
  `DETAIL: Only roles with privileges of the role whose process is being terminated or with privileges of the "pg_signal_backend" role may terminate this process.` で拒否のままである (M-3。両 peer の provision / control role は `NOINHERIT`、§3.1)。
- **(c) 効かせても terminate の段は黙って何もしない** — `pg_signal_backend` を `WITH INHERIT TRUE` で持たせても (M-4)、その role からは対象 backend の `usename`・`datname` は読めるが `backend_type IS NULL` = `t` であり、`0004` の `AND backend_type = 'client backend'` は **0 行**に一致する (M-5)。`pg_read_all_stats` を `WITH INHERIT TRUE` で足すと **1 行**になる。
- **(d) その結果、生きた接続が 1 本あると deprovision は落ちる** — runtime role の接続を 1 本開けたまま provision DSN で `0004` を 1 回実行すると
  `0004_deprovision_application.sql:84: ERROR: database "..._app_r54probe" is being accessed by other users / DETAIL: There is 1 other session using the database.` で止まる。terminate の段はエラーを出さずに通過している (0 行に一致) (M-6)。

テストはリトライで通っていただけで、**生きた接続の前で deprovision するテストは両 peer とも無い** (§3.3)。

## 2. 守るべき条件

- (i) provision / control role を superuser にしない。
- (ii) cluster 全体に効く predefined role (`pg_signal_backend`・`pg_read_all_stats`) を**常設では持たせない**。持たせると他 application・他 role の backend まで terminate でき、統計も読める (least privilege。`security/SECURITY_INVARIANTS_V1.md` の SI-00 (:65)・SI-01 (:93)・SI-02 (:111) が守る封じ込めの土台)。
- (iii) operator の事前 GRANT という**手順上の前提を残さない** (現行 §9 項目 3 と `MitateDB-api/migrations/0001_bootstrap_platform.sql`:30-32 の「a runbook/operator precondition」)。
- (iv) 両 peer で同じ安全結果 (`CLAUDE.md` Boundaries / Security Invariants の節)。
- (v) 公開契約 `spec/` は変えない。
- (vi) 失敗は fail-closed。`0004` は再実行できるまま。

## 3. 現物の事実

### 3.1 現行の形

| 事項 | r2db-api | MitateDB-api |
|---|---|---|
| 実行 role | `r2dbsvc_control` (`migrations/0001_bootstrap_control_plane.sql`:95-99、属性の理由は :69-94) | `mitatedbsvc_provision` (`migrations/0001_bootstrap_platform.sql`:128、理由は :113-126) |
| 属性 | `LOGIN ... NOSUPERUSER CREATEDB CREATEROLE NOINHERIT` (:96) | 同じ (:128)。`NOINHERIT` の理由コメントは :124-126 |
| terminate の段 | `migrations/0004_deprovision_application.sql`:100 (コメント :73-99) | `migrations/0004_deprovision_application.sql`:81-82 (コメント :66-80) |
| `DROP DATABASE` | 同 :102 | 同 :84 |
| `DROP ROLE` | 同 :103-104 | 同 :85-86 |
| credential guard | 同 :67-71 の `\gexec` (理由は :40-61。「`pg_terminate_backend`/`DROP DATABASE`/`DROP ROLE` -- anything at all -- ever runs」より前だと断言) | 無し (credential の削除は `finish_deprovision_application` 側) |
| 条件分岐 | 無し (3 変数とも set 前提) | `\if :{?database_name}` (:64) / `\if :{?runtime_role}` (:95) |
| R-1 語彙 allowlist | **無い** (`0001` に同種の注記が無い。grep 0 件) | `0001_bootstrap_platform.sql`:18-32。`pg_terminate_backend` の項は :30-32、証拠状態の文は :35-39 |
| `0004` を呼ぶ経路 | ops CLI に `deprovision` サブコマンドは**無い** (運用者が psql で実行) | `src/mitatedb_api/ops.py`:752 (`_run_deprovision_script`) / :767 (`cmd_deprovision`)。リトライ無し |

- 同族の構文 `GRANT <role> TO CURRENT_USER WITH SET TRUE` は既に両 peer の `0003` が使い (r2db `0003_provision_application.sql`:149、Mitate `0003_provision_application.sql`:105)、Mitate の R-1 allowlist にも入っている (`0001`:23-26)。
- 条件付き DDL を `SELECT CASE ... \gexec` で書く慣用は `0004` 自身が既に持つ (r2db `0004`:67-71)。存在しない role を飛ばす防御は `MitateDB-api/migrations/0013_role_statement_timeouts.sql`:91-94 と `0014_role_connection_limits_rollout.sql`:112-115 が持つ。
- 「GRANT → 使用 → 明示 `REVOKE`」はこの repo の家の作法である (Mitate `0010_idempotency_records_upgrade.sql`:96-99、runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`:300「4. Revoke the temporary membership.」、同 :2397「A failure leaves the temporary membership behind (§3.4b's cleanup)」)。
- application database に製品内から接続するのは **runtime / developer / 実行 role 自身** (per-application upgrade の `\c :database_name`) の 3 者だけで、auditreader・api・controlplane は platform database 側である (設計レビュー 1 回目の指摘 7、確実)。

### 3.2 実測 (M-1〜M-13・H-1・H-2 の該当部。逐語)

- **M-7 (一時付与 + 現行の絞った terminate)**: `prov` が `CREATE ROLE app_rt ... NOINHERIT` と `CREATE DATABASE appdb` を行った直後の membership は `inherit_option=f, set_option=f, admin_option=t`。`GRANT app_rt TO CURRENT_USER WITH INHERIT TRUE` → `GRANT ROLE`、terminate は `1`、`DROP DATABASE`・`DROP ROLE` 成功、`prov` の membership 残り 0 行。「cluster 全体の predefined role (`pg_signal_backend`・`pg_read_all_stats`) は一切使っていない。」
- **M-8 (FORCE 単独)**: `prov` として `DROP DATABASE appdb WITH (FORCE)` →
  `ERROR: permission denied to terminate process / DETAIL: Only roles with privileges of the role whose process is being terminated or with privileges of the "pg_signal_backend" role may terminate this process.`
- **M-9 (一時付与 + FORCE)**: `GRANT app_rt TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` → `DROP DATABASE appdb WITH (FORCE)` → `DROP DATABASE`、`DROP ROLE app_rt` → `DROP ROLE`。`prov` の membership 残り 0 行。「0.1 秒間隔で再接続し続けるクライアントがいる状態でも同じ 2 文で落とせた (1 回の実測。terminate と DROP が 1 文なので、その間に再接続が割り込む窓が無い)。」
- **M-10 (superuser の接続)**: 一時付与の後に `DROP DATABASE appdb WITH (FORCE)` →
  `ERROR: permission denied to terminate process / DETAIL: Only roles with the SUPERUSER attribute may terminate processes of roles with the SUPERUSER attribute.` 「database は残る。」
- **M-11 (FORCE は autovacuum worker の前で拒否される)**: `appdb` に autovacuum worker が 1 本付いている状態 (`autovacuum_naptime=1s`、cost delay を最大にした表で worker を留めた) で、一時付与の後に `DROP DATABASE appdb WITH (FORCE)` →
  `ERROR: permission denied to terminate process / DETAIL: Only roles with privileges of the role whose process is being terminated or with privileges of the "pg_signal_backend" role may terminate this process.` 「database は残る。」
- **M-12 (素の `DROP DATABASE` は autovacuum worker が付いていても通る)**: 「M-11 の直後、同じ状態 (worker 1 本を再確認) で `prov` として `DROP DATABASE appdb` → `DROP DATABASE`。」
- **M-13 (残った一時付与は実行 role 自身で剥がせる)**: 「M-12 の後 (role は残っている)、`prov` として `REVOKE app_rt FROM prov` → `REVOKE ROLE`。`pg_auth_members` に残る 1 行は `CREATE ROLE` 時の暗黙の ADMIN OPTION の行 (M-7 の `f|f|t`) である。」
- **H-1 (採用形の実測)**: `appdb` (`prov` が作成 = 所有、`REVOKE CONNECT … FROM PUBLIC`、`GRANT CONNECT … TO app_rt`) に、autovacuum worker 1 本、`app_rt` の接続 3 本、0.1 秒以内に再接続し続ける `app_rt` のクライアント 1 つが居る状態で、`prov` として 1 セッションで:
  `GRANT app_rt TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` → `GRANT ROLE`
  `ALTER DATABASE appdb WITH ALLOW_CONNECTIONS false` → `ALTER DATABASE`
  `SELECT count(*) FROM (SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='appdb' AND pid<>pg_backend_pid() AND backend_type='client backend') s` → `4`
  `DROP DATABASE appdb` → `DROP DATABASE`、`DROP ROLE app_rt` → `DROP ROLE`。database 残り 0、`prov` の membership 残り 0 行。
- **H-2 (第三の role の接続は付与の後も `backend_type` が NULL に見える)**: `other` (通常の LOGIN role、`appdb` に CONNECT を付与) が接続中。`prov` が `app_rt` の一時付与を得た後に `SELECT usename, backend_type IS NULL FROM pg_stat_activity WHERE datname='appdb'` → `other|t`。「したがって `backend_type='client backend'` の絞りはこの接続を黙って飛ばす。`usesysid IS NOT NULL` で絞って terminate すると M-2 と同じ `permission denied to terminate process` になる。`usename` / `usesysid` は付与が無くても読める。」

### 3.3 生きた接続の前の deprovision を測るテストは無い

- 両 peer のテストヘルパ `tests/test_postgres.py::deprovision_app` (r2db :249、Mitate :335) は `is being accessed by other users` の文字列だけを見て 8 回リトライする (r2db :275、Mitate :344)。conformance adapter にも同型のリトライがある (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:468-483 の :474)。r2db の adapter の `deprovision_application` (:2599) はリトライを持たない。
- 「他 role の生きた client backend を保持したまま deprovision する」テストは両 peer・conformance のいずれにも無い (探索担当の列挙、および `held_conn` 等の grep 0 件)。
- 一方、本番経路 (Mitate の `cmd_deprovision`、r2db の手動 psql) にはリトライが無い。**Data service の pool が接続を持つ限り、本番の deprovision は通らない。**

## 4. 決定 — `0004` の形

### D-1 実行 role 自身への一時的な role 付与

両 peer の `0004` は、database を落とす前に、その application の role (runtime / developer。**存在するものだけ**) を実行 role 自身へ一時付与する:

```
GRANT <その application の role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE
```

- 根拠: 実行 role はその role を自分で `CREATE ROLE` したので **ADMIN OPTION を既に持つ** (`admin_option=t`、M-7)。外部の権限の出所を要さない (条件 (iii))。`WITH INHERIT TRUE` が無いと `NOINHERIT` のため効かない (M-3)。`SET FALSE` は `SET ROLE` を開けないため (M-9)。
- 付与の範囲は**その application の role だけ**で、cluster 全体に効く predefined role は使わない (条件 (ii)、M-7 の末尾)。MitateDB `0004` 冒頭の「Never touches any other application's database, role, or data.」(:12-13) は、この範囲に限る限り成立する。
- **正常系では** membership は直後の `DROP ROLE` で消える (M-7・M-9・H-1 の「残り 0 行」)。**D-3 の経路 (止まったとき) では残る** — 扱いは §4.1。
- **権限の上昇ではない**: 実行 role は元々その role に ADMIN OPTION を持ち、`GRANT ... TO CURRENT_USER` はその権限の範囲内である。既存の検査も乱れない — `mitatedb_registry.assert_role_has_no_memberships` は `pg_auth_members` を **member 側**で数えるので (`MitateDB-api/migrations/0002_registry_and_functions.sql`:346-349、呼び出しは `0013_role_statement_timeouts.sql`:179-180)、member になるのが実行 role である本件では発火しない。同じ問い (provision role が membership を持つと既存の検査 / `ops inventory` が乱れるか) は設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md`:700 の (c)(d)(f) で実測済みで、乱れない。
- **形 (監督裁定 2026-09-19 で採用)**: `0004` は psql スクリプトなので、存在しない role を飛ばす防御は
  `SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'<role 変数>') THEN format('GRANT %I TO CURRENT_USER WITH INHERIT TRUE, SET FALSE', :'<role 変数>') ELSE 'SELECT 1' END` + `\gexec` で書く (`DROP ROLE IF EXISTS` と違い `GRANT` は非存在 role で失敗するため)。慣用の出所は §3.1。
- **r2db での位置 (設計レビュー 1 回目の指摘 3)**: r2db では `assert_no_credentials_for_deprovision` の `\gexec` (`0004`:67-71) の**後**に置く。前に置くと、credential 残留で abort したときに membership だけが残り、同ファイル :47-52 の「`pg_terminate_backend`/`DROP DATABASE`/`DROP ROLE` -- anything at all -- ever runs」より前に guard が走るという断言も偽になる。
- Mitate の `\if :{?database_name}` の else 側 (database が無い枝、`0004`:95-101) には database が無いので、この段は掛からない。**else 枝に一時付与は要らない** (設計レビュー 2 回目の F-5): `DROP ROLE` が要求するのは対象 role の ADMIN OPTION であって membership ではなく、実行 role は自分で `CREATE ROLE` したのでそれを既に持つ (M-7 の `admin_option=t`)。`0002` に `SECURITY DEFINER` は 1 件も無く (grep 0 件)、role 作成は実行 role の権限で走る。
- **前提が成り立たない corner (F-7。両論のまま記す)**: 一時付与の前提は「実行 role がその role を**自分で作った**こと」である。`begin_provision_application` は `CREATE ROLE` が `duplicate_object` のとき `ALTER ROLE` へフォールバックするので (Mitate `0002_registry_and_functions.sql`:429-465)、同名 role が**別の role によって**作られていた復元シナリオ (dump / Cloud SQL restore) では実行 role に `admin_option` が無く、(3) は `must have admin option on role` で **fail-closed に止まる (何も変わらない)**。ただしその状況では provisioning 側の `ALTER ROLE` フォールバック自体も `permission denied to alter role` で止まるはずなので、実運用で到達するかは**不確実**である。

### D-2 (v0.2 の決定。**撤回**)

> **訂正註 (2026-09-19、設計レビュー 1 回目の指摘 1・2 と監督裁定 R-1)**: 以下の v0.2 の D-2 —「`pg_stat_activity` + `pg_terminate_backend` をやめ、`DROP DATABASE IF EXISTS … WITH (FORCE)` に置き換える」— は**撤回する。行は消さない** (`OPERATING_CONDITIONS.md` §1.8 の 56)。撤回の根拠は **M-11**: FORCE は database 内の全 backend を対象にし `backend_type` で絞れないため、autovacuum worker が付いていると権限検査で `permission denied to terminate process` となり database が残る。素の `DROP DATABASE` は worker を PostgreSQL 自身が止めるので通る (M-12)。FORCE の失敗は「持ち主が閉じてから再実行する」という指示が通じない失敗であり、条件 (vi) の fail-closed の趣旨にも合わない。FORCE 案は §8 の **X-5** として理由とともに残す。採用形は **D-2R**。

v0.2 の本文 (撤回済み、記録として残す): 「`0004` の terminate の段 (r2db :100、Mitate :81-82) を削り、`DROP DATABASE IF EXISTS … WITH (FORCE)` にする。根拠 — `backend_type` の可視性に依らない (M-5 の罠が構造的に消える) / terminate と DROP が 1 文なので、その間に再接続が割り込む窓が無い (M-9) / `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`:45 が代替として挙げ実測を求めていた案である」。

- なお、根拠の 1 つ目 (`backend_type` の可視性) は FORCE 固有の利点ではない。**D-1 の一時付与を得た時点で `backend_type` は見える** (M-7) ので、M-5 の罠は付与だけで消える。FORCE の真の差分は「再接続の窓が無い」の 1 点であり、D-2R はその窓を `ALLOW_CONNECTIONS false` で閉じる (H-1)。

### D-2R 採用形 — `0004` の段の順序 (監督裁定 2026-09-19、実測は H-1)

`0004` は次の順序にする。**terminate の文と `DROP DATABASE` / `DROP ROLE` の文は現行のまま変えない。**

| # | 段 | 内容 | 出所 |
|---|---|---|---|
| (1) | 既存の guard | `begin_deprovision_application`、r2db の credential guard (`0004`:67-71)。**変更しない** | 現行 |
| (2) | **事前検査 (新設)** | その database に、runtime / developer / 実行 role 自身の**いずれでもない** `usesysid IS NOT NULL` の接続が 1 本でも在れば、**何も変える前に明示の例外で止まる**。文言は「application の role でない接続が在る。持ち主が閉じてから再実行する」の趣旨。`usesysid IS NULL` (autovacuum 等の background worker) は**数えない** | H-2 (`usename` / `usesysid` は付与が無くても読める)、M-12 |
| (3) | **一時付与 (新設)** | D-1 の `GRANT … WITH INHERIT TRUE, SET FALSE` (存在する role だけ、`\gexec`)。r2db では credential guard の後 | M-7、H-1 |
| (4) | **再接続の窓を閉じる (新設)** | **`pg_database` の存在検査つき**の `ALTER DATABASE … WITH ALLOW_CONNECTIONS false` (下の F-1)。実行 role は `0003` で自らこの database を作った所有者である (両 peer の `0003`「No `OWNER` clause: it defaults to the executing role」— Mitate :58-63、r2db :96-102) ので、一時付与が無くても通る | H-1、F-1 |
| (5) | 既存の絞った terminate | 現行の `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = … AND pid <> pg_backend_pid() AND backend_type = 'client backend'` (r2db :100、Mitate :81-82)。**文は変えない。** (3) の後なので `backend_type` が見える | M-5、M-7、H-1 (`4` 本を落とした) |
| (6) | 既存の DROP | 素の `DROP DATABASE IF EXISTS`、続いて `DROP ROLE IF EXISTS` (現行のまま)。autovacuum worker は PostgreSQL 自身が止める | M-12、H-1 |

- 事前検査 (2) の形: ~~`DO $$ ... RAISE EXCEPTION ... $$` (registry 関数群と同じ慣用) を `\set ON_ERROR_STOP on` の下に置く。~~ 実行 role 自身の pid は `pg_backend_pid()` で除く。
  - **訂正 (2026-09-19、設計レビュー 2 回目の F-2。行は消さない。§1.8 の 56)**: psql は dollar-quoted 文字列を literal として扱うので、`DO $$ … :'database_name' … $$` と書くと psql 変数が展開されず `syntax error` になる (両 peer の migrations の `DO $$` 7 箇所 — Mitate `0002`:224・`0005`:243・`0012`:126・`0013`:82・`0014`:103、r2db `0006`:113・`0013`:122 — は**本体に psql 変数を持つものが 0 件**である)。採る形は **(3) と同じ家の作法**、すなわち `format()` + `\gexec` で文字列を組み立てて実行する:
    `SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname = :'database_name' AND pid <> pg_backend_pid() AND usesysid IS NOT NULL AND usename NOT IN (:'runtime_role', :'developer_role', CURRENT_USER)) THEN format('DO $check$ BEGIN RAISE EXCEPTION %L; END $check$', <定数の文言>) ELSE 'SELECT 1' END` + `\gexec`。
  - **例外の文言には接続の role 名を入れない (定数)**。診断は runbook の admin の読み (§5.1 の 1 の (a)) で行う。
- **(4) の存在検査 (F-1)**: (4) は (3) と同じ慣用で書く —
  `SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name') THEN format('ALTER DATABASE %I WITH ALLOW_CONNECTIONS false', :'database_name') ELSE 'SELECT 1' END` + `\gexec`。無条件に書くと、`DROP DATABASE` が成功した後 `DROP ROLE` / `finish_deprovision_application` で止まった状態 (database 無し・registry 行あり) からの再実行が `ERROR: database "..." does not exist` で毎回止まり、**`0004` が二度と完了できなくなる** (条件 (vi) 違反)。現行はこの状態を `DROP DATABASE IF EXISTS` で吸収しており、無条件の `ALTER DATABASE` はその吸収を壊す。
- **枝の位置 (F-5)**: **(2)(3)(4) はいずれも、MitateDB では `\if :{?database_name}` の真の枝の中** (`0004`:64 以降)、**r2db では credential guard の `\gexec` (`0004`:67-71) の後**に置く。`\if` の外に置くと registration-only 行 (`database_name` が未設定) のときに未設定変数を参照し、ghost role 掃除の枝 (`0004`:95-101。`MitateDB-api/tests/test_ops.py`:518 以下の deprovision 系が実際に通る経路) が壊れる。
- (2) が `usesysid IS NULL` を数えないのは、background worker は terminate の対象外であり (現行コメント r2db `0004`:81-99)、素の `DROP DATABASE` が自ら止めるからである (M-12)。**worker の存在で deprovision を止めてはならない。**
- H-1 は autovacuum worker 1 本・`app_rt` の接続 3 本・0.1 秒で再接続し続けるクライアント 1 つが同時に居る状態で、この順序が 1 セッションで通ることを実測している。

### 4.1 失敗時の状態と掃除 (D-3。監督裁定 R-1)

| 止まった段 | 残る状態 | 次にすること |
|---|---|---|
| **(2) の事前検査** | **何も変わっていない** — `datallowconn` は true のまま、membership 無し、database も registry 行もそのまま | その接続の持ち主が閉じてから `0004` を再実行する |
| **(4) 以降、`DROP DATABASE` まで** (事前検査の後に割り込んだ接続、superuser の接続 (M-10)、その他の失敗) | database は**接続不可のまま残り** (`datallowconn=false`)、**membership も残る**。registry 行も残る | 再実行すれば完了する。取りやめるなら**実行 role 自身で** `ALTER DATABASE <database> WITH ALLOW_CONNECTIONS true` と `REVOKE <role> FROM <実行 role>` (M-13。自己剥奪できることは実測済み)。**掃除するまで fleet 運用コマンドが degrade する** — 下の F-3 |
| **(6) の `DROP DATABASE` の後、`DROP ROLE` / `finish_deprovision_application` で止まった** (role が platform database のオブジェクトを所有している、`ops deprovision` が渡す `lock_timeout` の発火 (`MitateDB-api/src/mitatedb_api/ops.py`:758)、psql が落ちた、等) | **database は無い**。role・membership・registry 行が残る (`database_name` は非 NULL のまま) | **再実行すれば完了する** — (2) は接続が無いので対象なし、(4) は F-1 の存在検査により対象なし、(5) も対象なし、(3) は残った role に付与し直し、(6) の `DROP ROLE IF EXISTS` と `finish_deprovision_application` が完了する |

- (3) の途中で落ちた場合 (片方の role だけ付与済み) も、残るのは membership だけなので同じ `REVOKE` で足りる。
- **F-3 (2026-09-19、設計レビュー 2 回目)**: `datallowconn=false` の残骸が在る間、**全 application の database に接続する ops コマンドはその application で失敗 / unknown になる** — `ops verify-declarations` の F-14 は接続失敗を「空 ledger = 全番号 pending」の番兵に落とすので**その application を「全 upgrade 未適用」と読んで FAIL に転び** (`MitateDB-api/src/mitatedb_api/ops.py`:1491-1508、docstring :1484-1488)、`ops inventory` は judgment を **`unknown`** に落とし (同 :2264-2271)、`ops upgrade-applications` はその行で失敗する (同 :1893-1923)。`0004` を**再実行すれば解消する**。取りやめるなら上の 2 文で戻す。現行は失敗しても database が接続可能なのでこれは起きない = D-2R が新たに持ち込む性質である。
- この表を**両 peer の runbook に書く** (§5.1 の 1・4)。`REVOKE` を実行するのは実行 role 自身であり、外部の権限の出所は要らない (M-13)。これは repo の家の作法 (§3.1 の末尾) と同じ形である。
- **`datallowconn` を読む既存コードは 0 件** (`git grep -e datallowconn -e ALLOW_CONNECTIONS` → 0、2026-09-19)。誤動作する既存検査は見当たらない。掃除 (sweep) も壊れない — §5.1 の (v) の sweep は admin DSN で `pg_database` を列挙して `DROP DATABASE IF EXISTS` するだけで、application database へは接続しないので `datallowconn=false` の残骸もそのまま落とせる。
- fail-closed の意味は v0.2 から変わらない: 黙って権限を広げる経路は作らない (条件 (ii))。

## 5. 追随する現物 (D-4)

### 5.1 同じ変更セットで文言を新しい手段に合わせる現物

1. **MitateDB runbook §9 項目 3** (`MitateDB-api/docs/cloud-run-cloud-sql.md`:1651-1664): 「`pg_signal_backend` の GRANT」(:1658) をやめ、「接続を 1 本開けた application を deprovision して `0004` が通ることを確かめる」に差し替える。**新しい項目 3 には次を含める (監督裁定 R-3)**: (a) 実行前に **admin で `pg_stat_activity` を 1 回読み**、その database に runtime / developer / 実行 role 以外の接続が在るかを記録する。(b) §4.1 の失敗時の状態と掃除の 2 行。(c) **Cloud SQL 側の管理接続が事前検査 (2) に掛かるかは未実測 (`absent`)** — `git grep cloudsqladmin` は **0 件**で、repo はこの前提をどこにも書いていない。管理 agent が application database に接続していれば (2) で恒常的に止まりうる。
2. **MitateDB runbook §9.1 の 2026-09-01 の記録** (:1685-1717): 履歴として**書き換えない**。項目 3 の行 (:1703-1706) に**訂正註**を足す (§1.8 の 56)。註の内容: 当時適用した `GRANT pg_signal_backend TO mitatedbsvc_provision` は実測 M-3 のとおり `NOINHERIT` の下で効果を持たない。その membership は不要なので `REVOKE` してよい。**誰が REVOKE するか** = その GRANT を実行できた bootstrap の `postgres` (§3.1 の実行 role には自己剥奪の権限の出所が無い、M-1 と同じ理由。D-1 の一時付与の自己剥奪 (M-13) とは別の話である)。
3. **MitateDB `0001_bootstrap_platform.sql` の R-1 allowlist コメント**: **:30-32 の `pg_terminate_backend` の項だけ**を直す。terminate 自身は残るので、**足すのは `ALTER DATABASE … WITH ALLOW_CONNECTIONS false` と `GRANT … WITH INHERIT TRUE, SET FALSE`**、および「`pg_signal_backend` member であることを前提としない」旨である。**コメントだけの変更で、`0001` の SQL は変えない。** 同 **:35-39 の証拠状態の文は変えない** — Cloud SQL 証拠は `absent` のままで D-6 と整合している。r2db の `0001` には同種の allowlist コメントが無いので、allowlist の直し先は MitateDB の 1 箇所だけである。
4. **r2db runbook の残骸掃除の手順**: `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §14 (:983) の branch (B) の 1 の段 (:1087-1093、SQL は :1091-1092) を D-2R の順序に合わせる。:1100-1105 の註も同じ段に属する。§4.1 の 2 行もこの runbook に書く。
5. **r2db runbook :476 付近**: credential guard が「`pg_terminate_backend`・`DROP DATABASE` の前に」走ることの説明。D-2R では (2) の事前検査と (3) の一時付与が加わるので、guard の位置 (指摘 3) に合わせて直す。
6. **`r2db-api/tests/test_credential_persistence.py`:774 付近の docstring**: 同じ順序を述べる文。同じく合わせる。
7. **`MitateDB-api/README.md`:190**: §9.1 の「deprovision (`pg_terminate_backend`) は未実行」の要約。同じく合わせる (未実行であること自体は変わらない、§7)。
8. **両 peer の `0004` のコメント** (r2db :73-99 と :40-61、Mitate :66-80): terminate の段と guard の順序を説明する文なので、D-2R の SQL と同じファイル・同じ変更セットで書き換わる (§1.5 の 34)。

**追加 (設計レビュー 1 回目の指摘 4、監督裁定 R-2)**:

- **(i) `MitateDB-api/docs/cloud-run-cloud-sql.md`:2398** — lock / 影響範囲の表の deprovision 行。terminate と `DROP DATABASE` は残るので**既存の記述は真のまま**である。**足す行だけ**を書く: `ALTER DATABASE … WITH ALLOW_CONNECTIONS false` (database 行の catalog 更新) と一時付与 (`GRANT … TO CURRENT_USER`)。同じ表の per-application upgrade 行 (:2397) は既に「A failure leaves the temporary membership behind」と書いており、deprovision 行も同じ性質を持つことになる (§4.1)。
- **(ii) `r2db-api/tests/test_postgres.py`:138-140 の docstring** — 「`pg_terminate_backend` is scoped to `backend_type = 'client backend'` for the same reason `0004_deprovision_application.sql` is」。terminate の段は残るので指示先は消えないが、`0004` 側に (2)(3)(4) が加わるため、理由の指す先を確かめて文言を合わせる。
- **(ii-b) `r2db-api/tests/test_postgres.py`:249 付近の `deprovision_app` の docstring (F-8)** — 「Retrying the entire script from the top is safe: on a failed attempt, `begin_deprovision_application` (a plain `SELECT`, no side effect) is the only step that ran, so the registry row is exactly as it was before this function was called.」。D-2R の後、失敗した試行は `datallowconn=false` と membership を残すので**この断言は偽になる**。§4.1 の表に合わせて直す。**MitateDB 側の `deprovision_app` (`MitateDB-api/tests/test_postgres.py`:335-341) は現物で確かめた — 同じ断言を持たない** (リトライの理由だけを書く) ので追随不要である。
- **(iii) 両 peer の `0003` の全称文** — r2db `0003_provision_application.sql`:145-148「`r2dbsvc_control` never holds standing membership in any application's developer role between provisioning runs」、Mitate `0003_provision_application.sql`:101-104 (同旨)。§4.1 の「(4) 以降で止まると membership が残る」を含む形に直す (**WP-1 の SQL 変更セット側**、監督裁定 R-7)。~~**MitateDB `0001`:176-181** も同型の全称文として裁定に挙がっている~~ — **監督裁定 (2026-09-19): MitateDB `0001`:176-181 は触らない。** 行は消さない (§1.8 の 56)。理由は現物のとおり、この文の主語は bootstrap admin、射程は「between runs of this file」であり、deprovision の一時付与とは**主体も期間も別**だからである。
- **(iv) `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`:247** — 「M-10 の大半 (= M-11/pg_terminate_backend)」の重複整理の行。§5.2 と同じく**本文は書き換えず訂正註を 1 行**足す。
- **(v) 範囲外 (admin 権限の sweep。触らない)** — `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:537、`r2db-api/conformance/conformance_adapter_r2db_http.py`:485-503、両 peer の `tests/test_postgres.py` の掃除ループ、両 peer の `conformance/real_server_*.py`。いずれも admin DSN の権限で行う後始末であり、`0004` の段ではない。
- **peer の `src/` は追随不要** (監督裁定 R-7): 現時点で `src/` 側の該当は `r2db-api/src/r2db_api/postgres.py`:354 のみで、これは pool の liveness の説明であり `0004` と無関係である。したがって `tools/check_comment_provenance.py` と `docs/code-history/` の追随も生じない。

### 5.2 本文を書き換えず、本メモを指す訂正註を 1 行足す現物

| 所在 | 現行の文面の要旨 | 足す註 |
|---|---|---|
| `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`:45 | R-1 語彙の一覧。`pg_terminate_backend` を挙げ、`DROP DATABASE ... WITH (FORCE)` を「実測選択する」代替として併記している | 実測は本メモ §3.2 (M-8〜M-12) で行い、**FORCE は採らず** terminate を残して `ALLOW_CONNECTIONS false` で窓を閉じる形にした旨の 1 行 |
| `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`:247 | 重複整理の行 (M-10/`pg_terminate_backend`) | 同上を指す 1 行 |
| `docs/design/CONFORMANCE_ADAPTER_V1.md`:2786-2792 | C-05 (e) の受理境界「`MitateDB-api-http` の `deprovision_application()` (`0004_deprovision_application.sql`) は `pg_terminate_backend` を直接発行するので、pool の `close()` の有無に依らず接続数の保証が構造的に成立する」 | terminate の段は残り、(2)(3)(4) が加わった旨と本メモを指す 1 行。**受理境界の性質は保たれる** |

### 5.3 触らない現物

- `conformance-tests/CONDITIONS_HISTORY.md`:42・:49 (C-05 の過去版。`pg_terminate_backend` を名指す文はここにある)。`*_HISTORY.md` は触らない。
- §5.1 の (v) に挙げた admin 権限の sweep 一式。

### 5.4 v0.1 の一覧に対する訂正 (2026-09-19)

- **訂正註 (2026-09-19、監督の指摘を受けた再実測)**: v0.1 の追随一覧は `conformance-tests/CONDITIONS.md`:34 (C-05 行) を「手段を名指す現物」として挙げていた。**この判定は誤りである。行は消さない** (§1.8 の 56)。実測: `grep -c pg_terminate_backend conformance-tests/CONDITIONS.md` → **0**。現行の C-05 行は受理境界を「for peer-specific structural reasons (full account in history, unchanged)」とだけ書き、手段を名指していない。名指しているのは §5.3 の history だけである。したがって `CONDITIONS.md` は**追随先ではない**。
- **C-05 (e) が言う terminate の区別 (1 文)**: C-05 (e) の受理境界が指すのは **`0004` 自身の段**である — `MitateDB-api-http` の `deprovision_application()` は provision DSN で `0004` を走らせる経路 (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:468-483) であり、同じファイルの `_sweep_prefix` (:530-545、terminate は :535-537) や r2db の同型の sweep (`conformance_adapter_r2db_http.py`:485-503) が admin DSN の権限で行う後始末とは別物である。**sweep は本件の範囲外**で、そのまま残る (§5.1 の (v))。

## 6. テストと変異 (D-5)

両 peer に置く。テストヘルパ経由ではなく、**リトライなしで 1 回**実行する形にする (リトライは §3.3 のとおり現行の赤を隠していた)。**両 peer に同名の共有ヘルパは置かず、peer ごとにテスト本体へ直書きする** (監督裁定 R-6。`_ISOMORPHIC_TARGETS` (`r2db-api/tests/test_audit_query.py`:2388 / `MitateDB-api/tests/test_audit_query.py`:2179) を増減しないので、`RM` §9 の 8 の「集合の増減 = Class D」には当たらない)。

### 6.1 完了条件と変異 (1 項目 1 テスト。監督裁定 R-4)

| # | 完了条件 (テスト) | 対応する変異 |
|---|---|---|
| 1 | 生きた接続 3 者のうち **runtime role の接続**を 1 本開けたまま、provision / control の DSN で `0004` を**リトライなしで 1 回**実行して通る | D-1 の一時付与 (`GRANT … WITH INHERIT TRUE, SET FALSE`) を外す → 赤 |
| 2 | **再接続の窓を閉じる文が在る** — `0004` の本文を読む**構造テスト**で、`ALLOW_CONNECTIONS false` の文が**一時付与の後・terminate の前**に在ることを assert する (監督裁定 F-6)。行動面の裏づけは H-1 の**引用**に留める (§1.5 の 34) | `ALTER DATABASE … WITH ALLOW_CONNECTIONS false` の文を外す → 赤 (構造テストは確定的に赤になる) |
| 3 | **role と membership が残らない** (両 role が消え、実行 role の `pg_auth_members` の該当行が 0) | `DROP ROLE IF EXISTS :"runtime_role"` を外す → 赤 (role 残存と membership 残存の両方で赤になる) |
| 4 | **事前検査 (2)** — その application の role でも実行 role でもない**通常の LOGIN role** の接続が在ると、`0004` は明示の例外で止まり、**何も変わっていない** (database が残り、`datallowconn` が true のまま、membership 無し、registry 行も残る) | 事前検査を外す → 「何も変わっていない」の assert が赤になる (検査が無ければ (4) まで進んで `datallowconn=false` になる) |
| 5 | **`SET FALSE`** — `0004` の本文を読む**構造テスト**で、一時付与の `GRANT` が `WITH INHERIT TRUE, SET FALSE` の形であることを assert する (監督裁定 F-6)。行動面の裏づけは M-9 の**引用**に留める | `GRANT` から `, SET FALSE` を外す → 赤 (構造テストは確定的に赤になる) |
| 6 | **database を先に落としてから再実行しても `0004` が完了する** (§4.1 の 3 行目の状態からの再実行。F-1) | (4) から `pg_database` の存在検査を外す → 赤 (`ERROR: database "..." does not exist`) |

- 完了条件 4 が **pin するのは「止まること」と「何も変わっていないこと」**であり、`DETAIL:` の文面は pin しない (M-8 と M-10 で DETAIL が異なるため。事前検査の例外文言は `0004` 自身のものなので、そちらは pin してよい)。
- **構造テストの慣用** (完了条件 2・5): migration の本文を読むテストは repo の慣用である (`MitateDB-api/tests/test_platform_migration_reapply.py`:287、`MitateDB-api/tests/test_ops.py`:185 の prefix 置換の読み取り)。docstring には「行動面の裏づけは実測 H-1 / M-9 の引用である」と明記する (§1.5 の 34、35)。**両 peer に同名のヘルパを置かず、それぞれのテスト本体に直書きする** (§6 冒頭と同じ規律)。
- **訂正註 (2026-09-19、設計レビュー 2 回目の F-6。行は消さない)**: v0.3 の完了条件 2 は「書けなければ監査照合とする」、5 は「観測方法は実装担当が提案する」と書いていた。**格下げと観測方法の判断は裁定事項である** (§1.7 の 49) ため、上のとおり**構造テストで pin する**に確定し、実装担当へ委ねる文は撤回する。
- 変異は `tools/dev/mutate.py` が**先頭の失敗で打ち切る**ため、**示したいテストごとに変異の項目を分ける** (上表のとおり 6 項目)。
- 「空振り禁止」(§1.5 の 32): 完了条件 3 の「0 件を期待する」assert は、変異 3 が赤になることで空振りでないことを示す。
- 変異の実測結果は実装時に報告へ添える (§1.5 の 32、33)。

### 6.2 v0.2 の表に対する訂正註 (2026-09-19)

- **訂正註 (設計レビュー 1 回目の指摘 9、監督裁定 R-4)**: v0.2 の §6 は変異 3 項目 (一時付与を外す / `WITH (FORCE)` を外す / `ON_ERROR_STOP` を off にする) を挙げていた。**行は消さず**、§6.1 の 5 項目に組み直す。理由: (a) FORCE は不採用 (§4 D-2 の訂正註)、(b) v0.2 の完了条件 1 は「database・両 role・membership が残らない」の 3 つを 1 項目で assert しており、role / membership 側に対応する変異が無かった (→ 完了条件 3)、(c) `SET FALSE` を pin する変異が無かった (→ 完了条件 5)、(d) 事前検査 (2) は v0.2 に存在しなかった (→ 完了条件 4)。
- **訂正註 (2026-09-19、監督裁定 R-6)**: v0.2 の §6 末尾の「両 peer に同名で置くヘルパは同型性テストの対象 (§1.5 の 38)」は、**同名ヘルパを置かない**方針の確定により本件では該当しない。行は消さない。

## 7. 証拠の状態 (D-6)

- `ALTER DATABASE … WITH ALLOW_CONNECTIONS false` と `GRANT … WITH INHERIT TRUE, SET FALSE` が **Cloud SQL (PostgreSQL 16) で通ることは未実測**である。`security/CONTROL_MAPPING.md` の production 証拠は **`absent` のまま**と正直に書く (:118「the deprovision path and the cloudsqlsuperuser probe remain unexercised」、:177 も同旨)。`MitateDB-api/migrations/0001_bootstrap_platform.sql`:35-39 の証拠状態の文も同じ理由で変えない (§5.1 の 3)。
- **Cloud SQL 側の管理接続が事前検査 (2) に掛かるかも未実測 (`absent`)**。`git grep cloudsqladmin` は 0 件 (§5.1 の 1 の (c))。
- **PostgreSQL の doc が `WITH (FORCE)` の拒否条件として挙げる prepared transaction / logical replication slot / subscription は本製品では使っていない** (`prepared transaction`・`max_prepared_transactions`・`replication slot`・`CREATE SUBSCRIPTION`・`wal_level` の git grep はいずれも 0 件、2026-09-19)。FORCE は不採用になったので本件の判断には効かないが、X-5 を読む人のために記録する。Cloud SQL 側で PITR や外部レプリカを使う場合の影響は未確認である。
- 実測の場は runbook §9 の**新しい項目 3** (§5.1 の 1) である。
- **本番には何も適用しない。**

## 8. 却下した代替案

- **X-1 runbook だけ直し、bootstrap の `postgres` が `GRANT pg_signal_backend … WITH INHERIT TRUE` と `GRANT pg_read_all_stats … WITH INHERIT TRUE` を行う形にする** — cluster 全体に効く権限を**常設**で持たせることになり (条件 (ii) に反する)、operator の前提も残る (条件 (iii))。Cloud SQL の `postgres` がこれらに ADMIN OPTION を持つかも未確認。**却下。**
- **X-2 role を `INHERIT` に変える** — その role の**全 membership の意味**が変わる。`0001` の `NOINHERIT` は意図した設計で、理由がコメントに書かれている (r2db `0001`:92-94、Mitate `0001`:124-126)。**却下。**
- **X-3 `pg_terminate_backend` を残し、filter を `backend_type` から可視の列 (`usesysid IS NOT NULL` 等) に変える** — terminate と DROP の間の再接続の窓が残り、可視性の規則への依存も残る。加えて H-2 のとおり、`usesysid IS NOT NULL` で絞って第三の role の接続を terminate すると M-2 と同じ `permission denied to terminate process` になる。**却下。** (D-2R は同じ列を**事前検査の読み取りだけ**に使い、terminate はしない。)
- **X-4 テストのリトライに任せる (現状維持)** — 本番の deprovision は Data service の pool が接続を持つ限り通らない (§3.3)。**却下。**
- **X-5 一時付与 + `DROP DATABASE … WITH (FORCE)`** (v0.2 の D-2) — 利点は「terminate と DROP が 1 文なので再接続の窓が無い」(M-9) の 1 点。**却下の根拠は M-11**: FORCE は `backend_type` で絞れず全 backend を対象にするので、autovacuum worker が付いていると
  `ERROR: permission denied to terminate process` で止まり database が残る。素の `DROP DATABASE` は worker を PostgreSQL 自身が止めるので通る (M-12)。既存のリトライは 4 箇所とも `is being accessed by other users` の文字列しか見ず (§3.3)、本番経路にはリトライが無いので、この失敗は拾われない。D-2R は同じ利点を `ALLOW_CONNECTIONS false` で得る (H-1)。**却下。**

## 9. 変更クラス (D-7)

- **監督裁定 (2026-09-19): Class C。** `security/CONTROL_MAPPING.md` に、**両 peer へ**次の主張を足す: 「deprovision は cluster 全体の predefined role を要さず、その application の role への一時的な INHERIT 付与だけで行う。Cloud SQL での証拠は `absent`」。版を上げる (現行 **2.9** → **2.10**、`security/CONTROL_MAPPING.md`:5)。
- **クラスが D に上がる契機は避ける** (設計レビュー 1 回目の指摘 12、監督裁定 R-6): 両 peer に同名のテストヘルパを置けば `_ISOMORPHIC_TARGETS` の増減となり `RM` §9 の 8 の表で Class D になる。§6 のとおり**同名ヘルパは置かない**ので **Class C のまま**である。`tools/change_class.py` はパスだけを見るのでこの契機は機械判定に出ない — 実装時に設計どおりであることを確かめる。
- **訂正註 (2026-09-19)**: v0.1 の §9 は「既存の主張で偽になるものは見当たらない = Class B の見込み」と書いた。**行は消さない** (§1.8 の 56)。既存の主張が偽にならないという実測は今も有効だが、**新しい主張を足す**という監督裁定により **Class C** になった。
- v0.1 で採った判定材料 (現物で実測、2026-09-19、版 2.9):
  - `grep -n -e pg_signal_backend -e pg_terminate_backend security/CONTROL_MAPPING.md` → **0 行**。
  - `deprovision` に触れる行: :92、:118、:158、:167、:177、:215、:275、:493、:588、:593、:685、:692、:694、:773、:788、:789。内訳は (あ) 配備時に `0004` を適用しない旨 (:92、:158、:215、:275)、(い) 本番で deprovision が未実行である旨 (:118、:177)、(う) `0003` の `REVOKE CONNECT` を `0004` が戻す旨 (:167)、(え) `deprovision` サブコマンドの確認語句・`--lock-timeout`・DSN の秘匿 (:493、:588、:593、:685、:692、:694、:773、:788、:789)。**いずれも手段を名指さず、D-1・D-2R・D-3 と D-6 の下で偽にならない** (訂正は不要、追加のみ)。

### 9.1 主張の置き場 — **SI-00 の既定の小ブロック (両 peer)** に確定 (監督裁定 R-5)

- **裁定の理由**: SI-00 の Protected assets (`security/SECURITY_INVARIANTS_V1.md`:71) が「administrative credentials, database administration capability」を挙げて資産が一致し、Required property (:75-81) が単一侵害の波及範囲そのものであり、証拠 `absent` の受理境界 (`security/CONTROL_MAPPING.md`:118) も既にここに在る。
- 置く前の実測 (2026-09-19、版 2.9、`conformance-tests/test_control_mapping_register.py` の `_subblock_block_text` と同じ数え方): **SI-00 / r2db-api 既定 2,939 字 (残り 12,261)、SI-00 / MitateDB-api 既定 2,502 字 (残り 12,698)**。上限は 1 小ブロック **15,200 字** (同ファイル :97 の `MAX_BLOCK_LENGTH`)、名前付き小ブロックは (SI, peer) ごと 3 本まで (同 :118)、既定 (無名) の小ブロックは各 (SI, peer) に必須でちょうど 1 つ・先頭 (設計 `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §5)。分割の照合は `tools/check_control_mapping_split.py`。
- 検討した候補 (記録として残す。判定は上の裁定):

| 候補 | SI | 小ブロック | 字数 (r2db / Mitate) | 残り | 材料 |
|---|---|---|---|---|---|
| A | SI-01 Application Isolation (:93) | 既定 | 1,716 / 1,750 | 13,484 / 13,450 | 既に deprovision に触れる主張がある (:167、:177)。ただし Statement (:96) の主語は「A credential scoped to one Application」で、新しい主張の主語 (provision / control role) は射程外 |
| B | SI-02 Control Plane Isolation (:111) | 既定 | 2,611 / 2,034 | 12,589 / 13,166 | Protected assets (:117) が「provisioning credentials, database administration capability」を逐語で挙げ資産の一致は最良。ただし Statement (:114) は「Application-facing API → Control Plane」の向きで、本件は向きが違う |
| **C (採用)** | **SI-00 Single-Compromise Containment (:65)** | **既定** | **2,939 / 2,502** | **12,261 / 12,698** | 上の裁定の理由のとおり |
| D | SI-09 Controlled Destructive Operations (:253) | MitateDB-api 既定は 13,745 字 (**残り 1,455**) | 2,211 / 13,745 | 12,989 / **1,455** | 主題 (破壊的操作の範囲が bounded、:256) の一致は最良。既定ブロックは残りが 2,000 字を切るので使えないが、**両 peer に同じ名前の小ブロックを新設すれば非対称は生じない** (この (SI, peer) の名前付きはどちらも 0 本、上限 3)。v0.2 はこの選択肢を挙げていなかった (設計レビュー 1 回目の指摘 11) |

- 参考 (残りが少ない順): SI-09 / MitateDB-api 既定 **1,455**、SI-14 / r2db-api 既定 2,576、SI-08 / MitateDB-api 既定 3,342、SI-10 / MitateDB-api 既定 4,575。**2,000 字を切るのはこの 1 本だけ**である。

## 10. 台帳 (D-8)

- `RM`:448 の R-54 行は**消さず**、【追記】で (1) 起票時の理解より深い問題だったこと (§1 の (a)〜(d))、(2) 本メモを指すこと、を書く (R-14、§1.8 の 56)。
- **roadmap の編集は本起草の範囲外** (監督が行う)。

## 11. 実装時に実測して決める事項 / 依頼者判断待ち

- ~~**完了条件 2 (再接続の窓) に確実に赤になる変異テストが書けるか**。書けなければ「監査照合」に落とす。~~ ~~**完了条件 5 の観測方法**。実装担当が提案する。~~ → **監督裁定 (2026-09-19、F-6)**: どちらも構造テストで pin する (§6.1)。行は消さない (§1.8 の 56)。
- **既存のリトライの扱い — 監督裁定 (2026-09-19、F-4)**: **事前検査 (2) の例外はリトライ対象に含めない。** 意図した拒否であり、待てば消える種類の失敗ではない (テストと adapter は自分の接続を先に閉じる)。既存のリトライ 4 箇所 (§3.3) は**変えない** — 判定はいずれも `is being accessed by other users` の文字列のままとし、`0004` の事前検査の例外文言を足す作業は行わない。素の `DROP DATABASE` を残すので、autovacuum worker が居る間の待ちは従来どおり PostgreSQL 側の経路になる (M-12)。
- 依頼者判断待ちの選択肢は**無い**。依頼者の指示 (2026-09-19、監督経由) により、判断は推奨で進め、後から報告する。

## 12. レビューと WP の切り方

- **設計レビュー**: 1 回目 (13 件) と 2 回目 (F-1〜F-8) を実施済みで、本 v1.0 に反映した。公開契約 `spec/` は触らない。作業指示書は `docs/work-orders/WORK_ORDER_R54_DEPROVISION_LIVE_CONNECTIONS_V1.md`。
- WP は**直列**。§1.5 の 34 (主張は実測の後) により、WP-2 の文言は WP-1 の変異結果を得てから書く。
- **監督裁定 (2026-09-19)**: **SQL ファイル (`0001` の allowlist コメントを含む) と `tests/test_postgres.py` の変更は全部 WP-1 に寄せる。** これで 3 WP の触るパスは重ならない (v0.3 が挙げていた 2 件の跨ぎは解消した。v0.3 の行は消さず本行で更新する。§1.8 の 56)。

| WP | 内容 | 触るパス |
|---|---|---|
| **WP-1** | D-2R の 6 段 ((2) 事前検査・(3) 一時付与・(4) `ALLOW_CONNECTIONS false` の新設。(5)(6) は現行のまま) を両 peer の `0004` に入れる。同ファイル内のコメント (§5.1 の 8)、両 peer の `0003` の全称文 (§5.1 の (iii))、MitateDB `0001`:30-32 の R-1 allowlist コメント (§5.1 の 3)、両 peer の `tests/test_postgres.py` の docstring (§5.1 の (ii)(ii-b)) も同じ変更セット。§6.1 の完了条件 6 件と変異 6 件 | `r2db-api/migrations/0004_deprovision_application.sql`、`MitateDB-api/migrations/0004_deprovision_application.sql`、`r2db-api/migrations/0003_provision_application.sql`、`MitateDB-api/migrations/0003_provision_application.sql`、`MitateDB-api/migrations/0001_bootstrap_platform.sql` (:30-32 **のみ**。:176-181 は触らない)、両 peer の `tests/test_postgres.py`、両 peer の deprovision のテストを置くファイル |
| **WP-2** | §5.1 の 1・2・4・5・7 と (i)、§5.2 の訂正註 3 件、`test_credential_persistence.py` の docstring (§5.1 の 6) | `MitateDB-api/docs/cloud-run-cloud-sql.md` (§9・§9.1・:2398)、`MitateDB-api/README.md`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/tests/test_credential_persistence.py`、`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`、`docs/design/CONFORMANCE_ADAPTER_V1.md` |
| **WP-3** | §9 の主張を **SI-00 の両 peer の既定ブロック**に足し、版を上げる (2.9 → 2.10) | `security/CONTROL_MAPPING.md` |
- 変更クラスの確定は着手時に `tools/change_class.py` と `RM` §9 の 8 の表で行う (§9 のとおり Class C)。
