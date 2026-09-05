# Q4 フェーズ 実施設計: 宣言と適用状態の根拠を DB 側の一次情報へ寄せる

- 版数: **v1.2 (2026-09-05、依頼者裁定 U-1〜U-3 を反映、契約無変更で確定)**。v1.1 からの変更点: **(1)** §5 の U-1〜U-3 を**【依頼者裁定 2026-09-05】**で確定にした (両論は経緯として残す)。**(2) U-1 = 載せない (peer-local)** — 適用状態の可視化は両 peer の `ops upgrade-status` (provision DSN) のみ。**共通契約は 1.6.0 のまま無変更、conformance の vector / port も無変更**であり、§6 は 6.1 が本線、6.2 は**採用せず (記録)** となった (§6、D-5、D-6 の 4)。**(3) U-2 = 台帳表に runtime role の `SELECT` のみ付与** — §3.9 の権限表と D-3 (a) の DDL 骨子を確定し、**cell を開く時点の集合検査**を §3.7 と D-3 (f) に置き、§3.8 に **F-12** (`SERVICE_UNAVAILABLE`、メッセージが `ops upgrade-applications` を示す) を追加した。パッケージ定数と `migrations/` の同期義務は **§10 / D-3 (d) の三者一致静的検査**が担保する。**(4) U-3 = 起動時スナップショット** — D-1 (e) / D-2 (g) / §9.2 を確定にし、live 案の差し替え注記を削除した。**(5)** §8 の migration 番号を**本フェーズの割当**として確定した (r2db `0008` / `0009`、MitateDB `0007` / `0008`。L6-2 に従い本フェーズが先に出荷する)。**(6)** §12 の LQ4-1〜LQ4-3 を裁定の記録に改め、**LQ4-20** (U-1「載せる」案を将来再検討する場合の前提) を起票した。
- 版数履歴: **v1.1 (2026-09-05、設計レビュー 2 本を反映)**。v1.0 (2026-09-05、初版) からの変更点: **(1)** D-3 に新項 (e) — 台帳表を作ると r2db の catalog / RLS 監視が恒久的に落ちるため、両 peer の backend の bookkeeping 除外集合と r2db の `_r2db_missing_rls` ビューを同じ WP で拡張する。**(2)** 台帳表の DDL に provision role への `GRANT SELECT` を足し、§3.9 の権限表と「書き込み経路」の記述を現物 (所有者 = developer role) に合わせた。**(3)** 「未適用」を**集合差**で定義し直し、`applied_level` 単一値を廃して applied / pending の集合表示にした (D-4 / D-5)。適用状態の可視化は既存の一覧コマンドを触らず新サブコマンド `ops upgrade-status` に分けた。**(4)** timeout の比較を**両辺 ms 整数の数値比較**に確定し、実効値の取得を `pg_settings` に、GUC 優先順位の記述を訂正し、`0` (無制限) と per-database role 設定を fail-fast (F-10 / F-11) にした。**(5)** ops コマンドを `set-platform-timeouts` に改名し射程を明記。**(6)** 廃止 env の検査対象を composition root に渡された env mapping に限定し、`deploy/env/*.example` を成果物に加えた。**(7)** F-6 の推奨を「`*_CONTROL_PLANE_STATUS` を直す」に反転。**(8)** 宣言表の値検査を Python 側に一本化し F-4b を追加。**(9)** 静的規則の規則文・命名規範・非空振り条件を確定 (§8 / §10 / D-3 (d))。**(10)** §3.11 に射程と残余を 4 項追加し、§12 に LQ4-14〜LQ4-19 を起票。**(11)** §4 / §5 / §7 の SI-02 参照を「invariant の禁止」ではなく**運用上の代償**の記述に書き改めた (Security Invariants を許可リストに使わない)。(v1.1 時点では U-1〜U-3 が未確定であった。)
- 位置づけ: **監督が確定した枠 (2026-09-05 裁定) の実施設計**である。§3 の D-1〜D-6 は監督裁定を受けた確定であり、**§5 の U-1〜U-3 も依頼者裁定 (2026-09-05) で確定した** — 本設計に未確定事項は無い。WP 分割は §11 に素案のみを置き、作業指示書は別途起こす。フェーズ6 設計文書 (`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md`) の構成・粒度・文体をそのまま踏襲する
- テーマ: **「宣言 (または適用状態の判定根拠) を持つプロセスと、値が実際に効いているプロセスが別で、どちらも他方を検証できない」構造の解消**
- 出所と範囲 (**依頼者裁定 2026-09-05**、`PHASE4_DURABLE_AUDIT_SINK_V1.md:1077` / `PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:855`): 次の 3 件を **1 つの設計**として扱う。
  1. **Q4 案 B** — `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合 (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4、:1067-1077)
  2. **L6-5a** — `surfaces` の 2 プロセス間ドリフト (`PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 L6-5a、:794、および §3 D-2 の F9、:291-296)
  3. **L6-20 (f)** — per-application upgrade script の運用性 (台帳 / 一括適用 / 適用状態の可視化、同 :855)
- ブランチ: `q4-db-single-truth` (main `730e5a2` から)
- 体制: Fable 監督/設計/コミット、Opus 起草/独立レビュー/受け入れ監査、Sonnet 実装 (コミットしない)。完了条件・単一コミット規律・identity 確認は既存フェーズと同一
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。既定の重み付けは「最小変更」ではなく「長期に正しい形」。利用者・運用者は AI エージェント (宣言は確実に読まれる)
- 決定軸 (監督、2026-09-05): **堅牢で安全が第一、次に最大限の自由。ガードレールでありゲートではない** — 止めるときは必ず「次に打つコマンド」を示す

---

## 1. 問題設定

3 件はいずれも同一の構造を持つ。**宣言 (または適用状態の判定根拠) を保持するプロセスと、その値が実際に効いているプロセスが別であり、どちらも他方を検証できない。**

### 1.1 `visibility_lag_ms` — 根拠は書き手 role の 2 つの timeout

宣言 `visibility_lag_ms` は **control プロセス**が自プロセスの env から導出する (`r2db-api/src/r2db_api/control_main.py:361-370` の `statement_ms + idle_ms + _VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS`、env 読みは同 `:429-430`。MitateDB は `control_composition.py:172-179`、env 読みは同 `:147-148`)。ところがこの値は**両方の書き手接続についての主張**であり、`application_audit` の書き手は **data-plane プロセス**という別プロセスで、**同名の env を独立に読む** (`r2db-api/src/r2db_api/main.py:427-428`、`MitateDB-api/src/mitatedb_api/main.py:269-270`)。両プロセスが同じ env 名・同じ既定定数 (5000ms / 5000ms) を読む構造なので運用上は一致するが、**機構的な強制も宣言側での検証も無い**。`security/CONTROL_MAPPING.md` の SI-14 行の点 (12) が逐語で **"nothing enforces it"** と記録しているのが現状である。

### 1.2 `coalescing_window_ms` — 根拠は data-plane の窓

宣言は control プロセスが**定数**を渡す (`MitateDB-api/src/mitatedb_api/control_composition.py:206` の `audit_coalescing_window_ms=DEFAULT_COALESCING_WINDOW_MS`。r2db は `control_plane.py` の既定が `audit_query.py:175` の `DECLARED_COALESCING_WINDOW_MS`)。実効値は data-plane 側の `DataService(denial_coalesce_window_s=…)` / `AuditRouter` 同名引数で決まる。`control_composition.py:194-206` のコメントが逐語で「このプロセスは data-plane プロセスの生きた `AuditRouter` を読めない — 別プロセスだから」と書いている。**配備が引数を上書きしても宣言には反映されない。**

### 1.3 `surfaces` — 根拠は配備者の宣言

両プロセスが同じ 2 つの env (`R2DB_`/`MITATEDB_DATA_BASE_URL`, `_CONTROL_BASE_URL`) を**独立に読む** (`r2db-api/src/r2db_api/main.py:250-270` / `control_main.py:261-281`、`MitateDB-api/src/mitatedb_api/config.py:127-155` / `control_composition.py:183-195`、検証ロジックは MitateDB では `surfaces.py:78-111` に単一化されている)。契約 1.6.0 の無条件義務は「**両文書が同じ `surfaces` を返す**」であるのに、`main.py:_surfaces` の docstring 自身が「この関数は兄弟プロセスが同じ値を与えられたかを (構造的に) 検証できない」と書く。検出は**配備後の手動 diff** だけが担う (`docs/work-orders/DEPLOY_PHASE6_20260904.md` :1184-1206)。

### 1.4 per-application upgrade の適用状態 — 根拠は各 application DB の実体

フェーズ6 WP-3 が新設した migration の第 3 類 (per-application upgrade script、初例 `MitateDB-api/migrations/0006_declared_field_types_upgrade.sql`) は、**application DB の数だけ運用者が個別に流す**形で出荷した。**「どの application DB に何番まで当たったか」を記録する場所が無い** — `_r2db_schema_revision` / `_mdb_schema_revision` は application 自身のスキーマ改訂番号であって platform 適用レベルではない。全 application を走査する `ops` コマンドも無い。未適用は起動時ではなく**最初のリクエスト**で `StorageConfigurationError` → `SERVICE_UNAVAILABLE` として判明する。

### 1.5 起草時に実測した前提

**すべて読み取り専用の調査である** (唯一の例外は §1.5 の 6 の catalog 権限確認で、これも `SELECT` のみ)。実装時に食い違えば設計側を訂正する。

**1. 2 プロセスの正体。** data-plane (`r2db_api.main` / `mitatedb_api.main`) と control-plane (`r2db_api.control_main` / `mitatedb_api.control_composition`) は別プロセスであり、互いの**ホストへ接続しない**。ただし**両者とも platform データベースへは接続する** — これが本設計が「DB 側を単一の真実にする」ことを可能にしている構造である。

**2. 書き手 role は platform 単位であり application ごとではない。**

| 書き手 | r2db-api | MitateDB-api |
|---|---|---|
| `application_audit` (data-plane プロセス) | `r2dbsvc_api` — `0007_application_audit.sql:179` が `INSERT` を付与 | `mitatedbsvc_api` — `0005_application_audit.sql:225` が `INSERT` を付与 |
| `control_audit` (control プロセス) | `r2dbsvc_controlplane` — `0006_control_plane_http.sql:501` | `mitatedbsvc_controlplane` — `0002_registry_and_functions.sql:266` |

→ **`ALTER ROLE … SET` は platform 単発 migration で足りる** (application ごとの繰り返しが要らない)。

**2a. 書き手 role は監査書き込み専用ではない (帰結として §3.11 に記録する)。**

| role | 監査以外の用途 |
|---|---|
| `r2dbsvc_api` | credential store の読み取り接続 — `0005_credential_store.sql:121-122` が `applications` / `credentials` に `SELECT` を付与 |
| `mitatedbsvc_api` | 同型 — `0002_registry_and_functions.sql:253-254` が同じ 2 表に `SELECT` を付与 |
| `r2dbsvc_controlplane` | control-plane の registry 全操作 — `0006_control_plane_http.sql:463-491` |
| `mitatedbsvc_controlplane` | 同型 — `0002_registry_and_functions.sql:263-265` |

→ **枠 §6 が r2db について挙げた「射程が role の全接続へ広がる」帰結は、MitateDB でも同型である** (起草時に実測)。

**3. 監査の読み手は別 role である。** `r2dbsvc_auditreader` (`0007_application_audit.sql:190-208`) / `mitatedbsvc_auditreader` (`0005_application_audit.sql:236-266`) は `SELECT` のみを持つ。**本設計は読み手 role の timeout を固定しない** — 宣言 `visibility_lag_ms` は書き手についての主張だからである。

**4. bookkeeping 表の前例は per-application スコープのみで、platform 全体の設定表は両 peer に存在しない。**

| 表 | 位置 | runtime role の権限 |
|---|---|---|
| `public._r2db_schema_revision` | `r2db-api/migrations/0003_provision_application.sql:206-216` | `SELECT, UPDATE` を付与 (:216) |
| `public._mdb_schema_revision` | `MitateDB-api/migrations/0003_provision_application.sql:138-143` | **無権限** (同ファイルのコメントが「r2db より意図的に狭い」と明記) |
| `public._mdb_field_types` | `MitateDB-api/migrations/0006_declared_field_types_upgrade.sql` | **無権限** (`REVOKE ALL … FROM :"runtime_role"`) |

**5. per-application script の作成儀式は両 peer で同一である。** `\c :database_name` → `GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE` → `BEGIN; SET LOCAL ROLE :"developer_role";` → 本体 → `COMMIT;` → `REVOKE :"developer_role" FROM CURRENT_USER` → platform DB へ戻る (`r2db-api/migrations/0003_provision_application.sql:121/149/165-166/244-245/257`、`MitateDB-api/migrations/0003_provision_application.sql:79/119-120/179-180/192`、`MitateDB-api/migrations/0006_declared_field_types_upgrade.sql`)。**PostgreSQL 16 の所有権ハードニングにより、`public` スキーマ内の表を作るには developer role を assume するしかない** — したがって新設する台帳表の**所有者は developer role になる**(**運用上の**書き込み経路が provision DSN に閉じることは、所有ではなく grant と運用で担保する。**構造的には所有者たる developer role の接続も書ける** — 既存 bookkeeping 表と同じ射程である。§3.9)。

**6. `pg_db_role_setting` は全 role が読める (実測)。** ローカル PostgreSQL 16.14 に対する読み取り専用の確認:

```
SELECT relname, relacl, has_table_privilege('public','pg_catalog.pg_db_role_setting','SELECT')
  FROM pg_class WHERE relname='pg_db_role_setting';
-- relacl = {<owner>=arwdDxt/<owner>,=r/<owner>}  → 空 grantee (PUBLIC) に r (SELECT)
-- has_table_privilege('public', …, 'SELECT') = t
SELECT attname, attacl FROM pg_attribute
  WHERE attrelid='pg_catalog.pg_db_role_setting'::regclass AND attnum>0;
-- setdatabase / setrole / setconfig はいずれも attacl が NULL (列単位の制限なし)
```

→ **control プロセスは既存の control-plane 接続のまま `pg_db_role_setting` を読める。** 新しい role も新しい DSN も要らない。なお `pg_db_role_setting` は shared catalog であり、どのデータベースに接続していても同じ内容が見える。`ALTER ROLE … SET`(データベース指定なし) の行は `setdatabase = 0` である。

**7. ops の前例。**

| 事項 | r2db-api | MitateDB-api |
|---|---|---|
| provision/control DSN | `_control_dsn()` → env `R2DB_CONTROL_DSN` (`ops.py:184`) | `_provision_dsn()` → env `MITATEDB_PROVISION_DSN` (`ops.py:369-370`) |
| migrations ディレクトリ解決 | **無い** (新設が要る) | `_migrations_dir()` (`ops.py:373-375`、env `MITATEDB_MIGRATIONS_DIR` で上書き可) |
| `psql` subprocess の前例 | **無い** (`ops.py` は `subprocess` を import していない — 実測) | `_run_deprovision_script` (`ops.py:541-550`、単一 app_id、`ON_ERROR_STOP=1`、失敗時は `_die` = 即時 exit 2) |
| per-app script に渡す psql 変数名 | `-v app_slug=…` (`migrations/0004_deprovision_application.sql:7,65,106` が逐語) | `-v app_id=…` (`migrations/0004_deprovision_application.sql:7,58,105`) |
| application 一覧コマンド | `cmd_list_apps` / CLI 名 `list-apps` (`ops.py:737-750`、provision DSN で registry を **SQL 直読み**) | `cmd_list_applications` (`ops.py:382-387`) / CLI 名 `list-applications` (parser 登録は `ops.py:805-806`)。**control credential で `ControlPlaneService.list_applications` を呼び、契約 shape の `ApplicationsResult` をそのまま出す** (provision DSN に触れない) |
| 終了コード | `_die` = 2 (`ops.py:179-181`)、`FoundationError` / `psycopg.Error` = 1 (`ops.py:1186-1191`) | `_die` = 2 (`ops.py:234-236`)、破壊的確認ゲート = 2 (`ops.py:296-302`)、`FoundationError` / `psycopg.Error` = 1 (`ops.py:892-910`) |

→ **全 application を走査するコマンドは両 peer に無い。** また **application 一覧コマンドの資格要件は両 peer で異なる** (r2db = provision DSN + SQL 直読み / MitateDB = control credential + service 呼び出し) — D-5 はこの非対称を織り込む。

**7a. `psql` の終了コードの実測** (レビュー 2、PG 16.14 の psql)。

| ケース | 終了コード |
|---|---|
| `\set ON_ERROR_STOP on` + 存在しない DB への `\c` | `\connect` エラーで以降を実行せず **3** |
| `\set ON_ERROR_STOP on` + `BEGIN; … エラー …; COMMIT;` | `COMMIT` に到達せず **3** (トランザクションは未コミットのままロールバックされる) |
| `\if :{?未定義変数}` の `\else` 側で `\warn` + `\q` | **0** (静かに成功として返る) |

→ **エラーは 3 で判定できる** (`returncode != 0` で足りる) が、**`\q` による skip は成功と区別できない**。したがって本フェーズ以後の per-app upgrade script は **skip 経路 (`\q`) を持たない** ものとし、`MitateDB-api/migrations/0006_declared_field_types_upgrade.sql:79-83` の `\if :{?database_name}` → `\warn` + `\q` 経路は**出荷済みとして許可リストの一部に記録する** (D-3 (c)、§10)。

**7b. 失敗時に developer role membership が残る (実測に基づく帰結)。** 既存儀式は `GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE;` が `BEGIN` の**外** (`r2db-api/migrations/0003_provision_application.sql:149`、`MitateDB-api/migrations/0003_provision_application.sql:105`、`0006` 同型) で、`REVOKE :"developer_role" FROM CURRENT_USER;` が `COMMIT` の**後** (r2db `0003:247`、MitateDB `0003:183`、`0006` 末尾) にある。本体でエラーが出ると psql は 3 で止まり **`REVOKE` に到達しない**。→ §3.11 の 8、D-4 (c)。

**8. registry の application 表の形。**

| 列 | r2db (`r2dbsvc_registry.applications`、`0002_provisioning_functions.sql:65-71`) | MitateDB (`mitatedb_registry.applications`、`0002_registry_and_functions.sql:103-115`) |
|---|---|---|
| 識別子 | `application_slug` (PK) | `application_id` (PK) |
| DB 名 | `database_name NOT NULL UNIQUE` | `database_name text UNIQUE` (provisioning 完了まで NULL) |
| role 名 | `runtime_role` / `developer_role` (`0006:77` が `runtime_role` の NOT NULL を解除) | `runtime_role` / `developer_role` (同じく NULL 可) |

→ **一括適用コマンドは registry を列挙して `database_name` が NULL でない行だけを対象にできる** (MitateDB `0006` の `\if :{?database_name}` ガードと同じ判定)。

**9. 契約側の現況。** `spec/data-service-api.v1.json` に `visibility_lag_ms` / `coalescing_window_ms` の直接記載は無い (`capabilities().audit_query` の値側、open key space)。`surfaces` の契約文 (:284) は「配備者が宣言する。両文書が同じ object を返す」であり**保管場所を規定しない** — したがって D-1/D-2 は契約を変えない。`ApplicationStateResult` と `ApplicationsResult.applications[]` はともに `additionalProperties: false` で `["application_id","enabled"]` のみを持つ (実測) — **適用レベルを載せるなら契約変更が要る。U-1 の裁定により本フェーズは載せないので、契約は 1.6.0 のまま無変更である。**

**10. conformance plug の実測 (D-1/D-2 の射程に効く)。**

- **in-process plug** は composition root を経由せず service を直接組む (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:359/433/754` は `surfaces` を合成の `example.invalid` URL で直接渡す)。→ **本機構の影響を受けない。**
- **r2db HTTP plug** は env を読む composition root (`build_control_app`) ではなく `assemble_control_stack(…, surfaces=_SURFACES)` (`conformance_adapter_r2db_http.py:1047`、`_SURFACES` は :730) を呼ぶ。ただし**import 時に `R2DB_DATA_BASE_URL` / `R2DB_CONTROL_BASE_URL` を `os.environ.setdefault` している** (:123-124)。
- **MitateDB HTTP plug** は **control-plane composition root そのもの** (`build_control_service(control_env)`) を呼び (`conformance_adapter_mitatedb_http.py:715`)、`control_env` に `MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL` を入れている (:707-708)。

→ **非対称である。** MitateDB HTTP plug は composition root そのものを通るので、**宣言表の読み出しが load-bearing になる**。r2db HTTP plug は `surfaces` を引数で注入し続けるので、**宣言表の読み出し経路は通らない** — r2db 側で効くのは廃止 env の不在検査だけであり、表の読み出しの検証は **peer-local な実 PG テスト**が単独で担う (§6.1、§3.11 の 4、§12 LQ4-11)。

---

## 2. 守るべき条件

1. **出荷済み migration は in-place で触らない** (`PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §2 制約 8)。platform 単発 migration と per-application upgrade script は適用後に編集しない。**`MitateDB-api/migrations/0006_declared_field_types_upgrade.sql` も触らない。** provisioning テンプレート (`0003` / `0004`) は毎回実行されるので改訂してよく、**テンプレート改訂と upgrade script は対で出す**。
2. **契約 1.6.0 の義務を変えない** — 両文書が同じ `surfaces` を返すこと、`surfaces` は配備者の宣言であること、`visibility_lag_ms` は導出値であること。
3. **新しい共通 Security Invariant を足さない。** 台帳表と宣言表は SI-12 に、一括適用は SI-02 に、既存のまま載る (§7)。
4. **peer 間でコードを共有しない。** 同名ヘルパは同型性テストで固定する (要請者決定 2026-09-03)。両 peer は同じ安全成果を**同じ形で**満たす。
5. **conformance の in-process plug は composition root を通らない** (§1.5 の 10)。本機構の検証は両 peer のテスト (実 PG) と HTTP plug が担う。**U-1 の裁定 (2026-09-05) により契約は無変更なので、`conformance-tests/` の vector と port は触らない** — 触るのは adapter の構成側だけである (§6.1)。
6. **公開リポジトリ規律。** 実 credential・実 DSN・実ホスト名を文書にもテストにも置かない。`example.invalid` 等の偽ドメインと合成値のみを使う。
7. **fail-fast のメッセージは次に打つ ops コマンド名まで示す** (利用者・運用者は AI エージェント前提。宣言で誘導するガードレール)。
8. **常設規律 7 項目**を継承する (`docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md` §0.1): 空振り禁止 / 変異先行で完了条件 / 主張は実測の後 / 確定文言はファイル経由 / **静的規則は逐語プロトタイプ後** / 同型性テスト / 設計外の拡張は実装前に上げる。
9. **依頼者原則。** 先送りしない・シンプル・制約で回避しない・誇れる成果物。最小変更ではなく長期に正しい形を既定にする。

---

## 3. 決定と根拠

### D-1 書き手 timeout は role 設定を単一の真実にする (Q4 案 B)

**決定**: `application_audit` と `control_audit` の各書き手 role の 2 つの timeout を **PostgreSQL の role 設定**に固定し、それを唯一の真実とする。書き手はセッションでの `SET` をやめ、control はその role 設定から `visibility_lag_ms` を導出する。

**(a) platform 単発 migration** (r2db `0008` / MitateDB `0007`、§8 で確定) が role 設定を置く。既定値は**現行定数と同一 (5000ms / 5000ms)** であり、**出荷時に挙動は変わらない**。

```sql
-- r2db-api: platform 単発 migration 0008 (§8 で確定)。R2DB_CONTROL_DSN (r2dbsvc_control) で実行する。
-- ALTER ROLE ... SET は上書き代入であり、再実行しても同じ終状態になる (冪等)。
ALTER ROLE r2dbsvc_api          SET statement_timeout                     = '5000ms';
ALTER ROLE r2dbsvc_api          SET idle_in_transaction_session_timeout   = '5000ms';
ALTER ROLE r2dbsvc_controlplane SET statement_timeout                     = '5000ms';
ALTER ROLE r2dbsvc_controlplane SET idle_in_transaction_session_timeout   = '5000ms';
```

MitateDB は同じ 4 文を `mitatedbsvc_api` / `mitatedbsvc_controlplane` に対して置く (`MITATEDB_PROVISION_DSN` で実行)。**読み手 role (`*_auditreader`) には置かない** — 宣言は書き手についての主張だからである。

**(b) 書き手プロセスは接続時のセッション `SET` をやめ、起動時に「宣言と実効値の二重検査」を行う** (**監督裁定 2026-09-05**)。現行は `PostgresApplicationAuditSink` が接続ごとに 2 つの timeout を SESSION レベルで設定している (`r2db-api/src/r2db_api/main.py:420-431` のコメントが逐語でそう書く)。これを廃し、書き手プロセスは起動時に次の**両方**を検査する。

- **(i) 宣言の存在と有効性** — `pg_db_role_setting` に自 role の `statement_timeout` と `idle_in_transaction_session_timeout` の 2 設定が**存在し、かつ ms へ正規化した値が 1 以上であること**。**`0` は PostgreSQL では「無制限」を意味する** (レビュー 2 が実測) ので、存在検査だけでは「無音の unbounded」を通してしまう。0 と負数は F-10 で止める。
- **(ii) 実効値の一致** — **両辺を ms 整数へ正規化したうえで数値比較する**。実効値は `SELECT name, setting FROM pg_settings WHERE name IN ('statement_timeout','idle_in_transaction_session_timeout')` で取る (この列は unit = ms の生整数であり、文字列パースが要らない)。`SHOW` / `current_setting` は**単位が割り切れる表記に丸められる** — `5000ms` は `5s` と表示される (レビュー 2 が PG 16.14 で実測) — ため、**生文字列の比較は禁止する**。
  - **検査を行う接続**: **監査書き手が実際に使う pool の接続、すなわち login role が書き手 role である接続**で行う。role 設定はログイン時にのみ適用されるので、任意の接続や `SET ROLE` した接続で読んでも書き手 role の実効値にはならない。
  - **catalog 側 (`setconfig`) は文字列パースが避けられない。** `ALTER ROLE … SET` は**書いた文字列をそのまま保存する** (レビュー 2 の実測、§10)。単位表記は PostgreSQL の `{us, ms, s, min, h, d}` と単位無し (= ms) を扱う (**監督裁定 2026-09-05、WP-0 差し戻し**: PG 16 の HINT 逐語 `Valid units for this parameter are "us", "ms", "s", "min", "h", and "d".` に合わせ、当初の規範集合が欠いていた `us` を足す)。**既存の逐語実装が `MitateDB-api/tests/test_application_audit.py:94-108` の `_ms_from_pg_timeout_text` にある** — これを両 peer の `src` へ引き上げて同名にし、同型性テストの対象 (`_ISOMORPHIC_TARGETS`) に加える (D-3 (d))。
  - **未知のキーは無視する。** `setconfig` には `search_path` など他の設定が混在し得るので、この 2 キー以外は読み飛ばす (無視しないと将来の `ALTER ROLE` 追加で起動が止まる)。

**どれか一つでも欠ければ fail-fast する** (メッセージは差異の内容を**両辺 ms 表記**で示し、次に打つ ops コマンド名を含む。F-7 / F-9 / F-10 / F-11)。無音の unbounded (timeout 無しの書き込み接続) が危険であり、かつ**宣言と実効値が食い違ったまま動くことも同じ危険**だからである。

**control は catalog (`pg_db_role_setting`) から導出する** ((c))。この二重検査により、**`ALTER ROLE … SET` より優先順位が高い経路**による上書きは、**「宣言と食い違う配備」として起動時に止まる** — 導出元の catalog を実効値が裏切る経路が塞がる (§3.11 の 2、§12 LQ4-5)。GUC の優先順位は低い順に **`postgresql.conf` / コマンドライン < `ALTER DATABASE … SET` < `ALTER ROLE … SET` < `ALTER ROLE … IN DATABASE … SET` < 接続時 `options=-c …` / `PGOPTIONS` < セッション `SET`** である。したがって**上書きし得るのは `ALTER ROLE … IN DATABASE … SET` と接続時 `options` / `PGOPTIONS` であり、`ALTER DATABASE … SET` ではない** (v1.0 はこれを取り違えていた。レビュー 2 の指摘は PostgreSQL の GUC source 順位 `PGC_S_DATABASE` < `PGC_S_USER` < `PGC_S_DATABASE_USER` < `PGC_S_CLIENT` に基づく推論であり、**実装時に実 PG で 1 回確認する**、§10)。

**(c) control は `pg_db_role_setting` を読んで導出する。**

```sql
-- control プロセスの既存 control-plane 接続で実行できる (§1.5 の 6)。
SELECT r.rolname, s.setdatabase, s.setconfig
  FROM pg_db_role_setting s
  JOIN pg_roles r ON r.oid = s.setrole
 WHERE s.setdatabase IN (0, (SELECT oid FROM pg_database WHERE datname = current_database()))
   AND r.rolname IN ('r2dbsvc_api', 'r2dbsvc_controlplane');   -- MitateDB は mitatedbsvc_*
```

**`setdatabase = 0` の行 (database 非依存の `ALTER ROLE … SET`) だけを宣言とみなす。** それでもクエリが per-database 行 (`setdatabase ≠ 0`、`ALTER ROLE … IN DATABASE … SET`) を**拾う**のは、その行が存在すること自体を検出して止めるためである — per-database 行は `ALTER ROLE … SET` より優先順位が高く、宣言の根拠を無効にする。存在すれば **F-11** で fail-fast し、`ALTER ROLE … IN DATABASE … RESET` による除去を指示する。v1.0 のクエリ (`WHERE s.setdatabase = 0`) はこの行を**構造的に見落としていた**。

**`SET ROLE` では実効値は取れない。** `ALTER ROLE … SET` はログイン時にのみ適用されるので、control プロセスが `SET LOCAL ROLE r2dbsvc_api` して読んでも、それは control 自身のセッション値であって書き手 role の実効値ではない (レビュー 2 の確認)。control が読むのは**あくまで catalog** である。

`setconfig` は `{statement_timeout=5000ms,idle_in_transaction_session_timeout=5000ms}` の形の text 配列であり、実装は `key=value` を解いて ms へ正規化する ((b)(ii) の逐語ヘルパを共用する。未知のキーは無視する)。**導出式**:

```
visibility_lag_ms = max( statement_timeout_ms(role) + idle_in_transaction_session_timeout_ms(role)
                         for role in {application_audit の書き手, control_audit の書き手} )
                    + _VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS (1000)
```

出荷既定では `5000 + 5000 + 1000 = 11000ms` であり、**現行の宣言値と一致する** (`CONTROL_MAPPING.md` SI-14 行の点 (12) が記録する現行値と同じ)。いずれかの role で 2 設定が欠けていれば、`audit_query` を `unavailable` に落とすのではなく**起動を止める** — 書き手側と対称にするためである。

**(d) env は廃止する。** `R2DB_AUDIT_STATEMENT_TIMEOUT_MS` / `R2DB_AUDIT_IDLE_TIMEOUT_MS`、`MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS` / `MITATEDB_AUDIT_IDLE_TIMEOUT_MS` を読まない。**起動時にこれらが定義されていれば、値によらず (空文字列を含めて) fail-fast する** — 古い配備設定の取り残しを無音で無視すると「変えたつもりが効いていない」が再発するからであり、Cloud Run / systemd の配備は空文字列で変数を残すことが普通にあるからである。

**検査対象は composition root に渡された env mapping であって `os.environ` ではない。** 両 peer の composition root は env を `Mapping` 引数で受ける (`build_app(env)` / `FoundationConfig.from_env(values)` / `build_control_service(control_env)`)。`os.environ` を直接見る実装にすると、開発者のシェルや CI の親環境に 1 変数残っているだけで全テストが起動時に落ちる (r2db の HTTP adapter は現に import 時に `os.environ.setdefault` している、§1.5 の 10)。

変更手段は **ops サブコマンド (provision DSN で `ALTER ROLE` を発行) + 両プロセス再起動**の 1 経路だけになる。

**(e) 読みは起動時スナップショットである** (**依頼者裁定 2026-09-05**、U-3)。role 設定は**新規接続から効く**ため、ops で変えたら両プロセス再起動が runbook の手順になる (順序は §9.2)。これにより**プール済み接続の実効値と宣言が同じ時点を指す**。

**根拠**: `statement_timeout` / `idle_in_transaction_session_timeout` は **PostgreSQL 自身が意味を持つ設定**であり、role 設定は「実効値そのもの」である。control が読むのは catalog であって、新しい書き込み面を作らない (案 C との違い、§4)。

### D-2 platform 宣言表を新設し、`surfaces` と `coalescing_window_ms` の単一の真実にする

**決定**: platform データベースの registry スキーマに宣言表を 1 つ作り、両プロセスが起動時にそこから読む。

**(a) 表** — D-1 と**同じ platform 単発 migration** で作る。

```sql
-- r2db-api (registry スキーマは r2dbsvc_registry)。MitateDB は mitatedb_registry に同型。
CREATE TABLE IF NOT EXISTS r2dbsvc_registry.platform_declarations (
    key        text PRIMARY KEY
               CONSTRAINT platform_declarations_key_check
               CHECK (key IN ('surfaces', 'audit_coalescing_window_ms')),
    value      jsonb       NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL   ON r2dbsvc_registry.platform_declarations FROM PUBLIC;
GRANT SELECT ON r2dbsvc_registry.platform_declarations TO r2dbsvc_api;
GRANT SELECT ON r2dbsvc_registry.platform_declarations TO r2dbsvc_controlplane;
-- 書きは表の所有者 (provision role) だけが持つ。ops が provision DSN で発行する。

-- 窓の既定行を seed する (現行定数と同値: audit_query.DECLARED_COALESCING_WINDOW_MS = 60000)。
INSERT INTO r2dbsvc_registry.platform_declarations (key, value)
VALUES ('audit_coalescing_window_ms', to_jsonb(60000))
ON CONFLICT (key) DO NOTHING;
-- surfaces は配備固有なので seed しない (下記 (c))。
```

`key` の閉じた集合を `CHECK` で固定するのは**監督裁定 2026-09-05 で採用**した — 表が手で編集され得る前提に立つ以上、綴り違いの行が無音で無視されるより DB が拒否する方が安全であり、キーを増やすときは platform 単発 migration を出すという規律とも整合する。**制約には名前を付ける** (`platform_declarations_key_check`) — 出荷済み migration は in-place で触らない (制約 1) ので、キーを増やす将来の migration は `DROP CONSTRAINT … ADD CONSTRAINT` を書く必要があり、処理系生成の名前に依存できないからである。

**`value` 側の CHECK は置かない** (**監督裁定 2026-09-05**)。値の妥当性検査は **Python 側に一本化する** ((d)) — ops の書き込み時と起動時の読み出し時が**同じ検証関数**を通る形にし、検証を DB と Python の 2 か所に分けない。

**この表には公開 capability document に現れる値のみを置く。秘密・資格情報・内部ホスト名は置かない** (SI-10、公開リポジトリ規律)。`SELECT` を 2 つの platform role へ付与する根拠はこの規律に立つ (§7)。

**(b) 権限。** 書けるのは **provision role のみ** (ops サブコマンド経由)。`SELECT` を data-plane の platform role と control-plane role に付与する。application の runtime / developer role は **platform DB に接続しない** (database-per-application) ので無関係である。

**(c) 行の内容。**

| key | value (jsonb) | seed |
|---|---|---|
| `surfaces` | `{"data": {"base_url": "https://data.example.invalid/v1"}, "control": {"base_url": "https://control.example.invalid/control/v1"}}` — `control` は control surface が提供される配備にのみ置く | **しない** — 配備固有。**行が無ければ起動時 fail-fast** (1.6.0 で `surfaces.data` は無条件義務) |
| `audit_coalescing_window_ms` | 整数 (例 `60000`) | **する** — 現行定数と同値 |

**(d) 検証は書き込み時と読み出し時の両方で行い、両方が同じ Python の検証関数を通る** (表が手で編集され得るため)。

- **`surfaces`**: 検査項目は 1.6.0 で確定済みの 4 点 — 絶対 URL であること、`data` は `/v1` で終わること、`control` は `/control/v1` で終わること、**末尾スラッシュを含まないこと**。**両 peer の既存 validate を再利用する** (`MitateDB-api/src/mitatedb_api/surfaces.py:78-93` の `validate_data_base_url` / `validate_control_base_url`、r2db は `main.py` / `control_main.py` の `_validate_surface_base_url` — 2 コピーある。L6-17 / L6-20 (d)、§12 LQ4-7)。落ちれば **F-5**。
- **`audit_coalescing_window_ms`**: **jsonb の数値であり、整数であり、0 以上であること** (**監督裁定 2026-09-05**。`0` は「coalescing を行わない」を意味する有効な値である。契約の `limits` は `minimum 1` だが、この宣言は `limits` の項目ではなく `audit_query` capability の値側にあるので、その下限は及ばない)。文字列・負数・小数は拒否する。落ちれば **F-4b**。`value jsonb` は DB 側では何でも入るので (`key` の CHECK は key しか見ない)、この経路が無いと「行はあるが値が壊れている」が無検査になる。

**(e) 両プロセスは起動時にこの表を読む。** data-plane は `surfaces` と窓を `DataService` / `AuditRouter` へ、control は `surfaces` と宣言へ渡す。定数 `DECLARED_COALESCING_WINDOW_MS` / `DEFAULT_COALESCING_WINDOW_MS` は **seed 値の出所としてのみ残す** (実行時の宣言の出所ではなくなる)。

**(f) env は廃止する。** `R2DB_DATA_BASE_URL` / `R2DB_CONTROL_BASE_URL`、`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL` を読まない。**定義されていれば値によらず fail-fast** (D-1 (d) と同じ理由・同じ検査対象 = composition root に渡された env mapping)。**現行の data / control 非対称** — data 側は `*_CONTROL_PLANE_STATUS` 依存、control 側は無条件必須 — は**表の 1 行に統合されて消える**。代わりに、**`surfaces` 行に `control` があるか否かと、そのプロセスの `*_CONTROL_PLANE_STATUS` の整合を起動時に検査する**: `unavailable` を宣言するのに `control` 行がある、またはその逆は fail-fast である (F-6)。

**これは Phase 6 監督裁定 5 を上書きする** (記録として明示する)。現行実装は「`*_CONTROL_BASE_URL` が環境に残っていても `control_plane_status == 'unavailable'` なら**決して採用しない**」を明示の裁定として持つ (`MitateDB-api/src/mitatedb_api/config.py:146-158` のコメントが逐語で「a stale/leftover value from a previous configuration, say — it is never adopted」と書く。r2db `main.py` の `_surfaces` も同型のゲートを持つ)。宣言が env から**両プロセス共通の 1 行**へ移る以上、「黙って無視する」ではなく**行の存在自体を矛盾として拒否する**形に改める。単一の宣言表では、無視した側が兄弟プロセスの宣言と食い違ったまま動くことになるからである。

**(g) 読みは起動時スナップショットである** (D-1 (e) と同じ。**依頼者裁定 2026-09-05**、U-3)。宣言表を変えたら**両プロセス再起動**が要る (§9.2)。

### D-3 per-application platform upgrade 台帳を各 application DB に置く

**決定**: 「何番まで当たったか」を、**実体と同じデータベースの中に**記録する。

**(a) 表** — 既存 bookkeeping 表と同じ場所 (`public`)、同じ作成儀式 (§1.5 の 5) で作る。

```sql
-- \c :database_name → GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE
-- → BEGIN; SET LOCAL ROLE :"developer_role"; の中で作る (0003 / 0006 と同じ儀式)。
CREATE TABLE IF NOT EXISTS public._r2db_platform_upgrades (   -- MitateDB は public._mdb_platform_upgrades
    upgrade_number integer     PRIMARY KEY,
    script_name    text        NOT NULL,
    applied_at     timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL    ON public._r2db_platform_upgrades FROM :"runtime_role";
-- 依頼者裁定 2026-09-05 (U-2): runtime role には SELECT のみを付与する。
-- ALTER DEFAULT PRIVILEGES 由来の DML を REVOKE で打ち消したうえで読み取りだけを戻す。
GRANT  SELECT ON public._r2db_platform_upgrades TO :"runtime_role";
-- `SET LOCAL ROLE :"developer_role"` の内側なので CURRENT_USER は developer role、
-- SESSION_USER は script を流している provision role である。
GRANT  SELECT ON public._r2db_platform_upgrades TO SESSION_USER;
```

**`GRANT SELECT` を provision role に置く理由 (両 peer)**: 表の所有者は developer role であり、儀式の末尾の `REVOKE :"developer_role" FROM CURRENT_USER` が provision role の一時 membership を落とす。したがって script 終了後の provision role は**この表に対して無権限**になる (provision role は superuser ではなく、データベースの所有権はその中の表への権限を与えない — レビュー 2 の実測)。付与が無いと D-4 / D-5 の「provision DSN で各 application DB の台帳を読む」が `permission denied` で失敗し、**`--dry-run` すら動かない**。付与は `SET LOCAL ROLE :"developer_role"` の内側で所有者として発行する。

**台帳表に RLS は付けない** (**監督裁定 2026-09-05**)。`_r2db_schema_revision` と同型にして `FORCE ROW LEVEL SECURITY` を置くと、provision → `SET ROLE developer` での書き込みがポリシー無しで拒まれる (FORCE RLS は所有者にも適用される)。代わりに r2db の RLS 監視ビューの除外名を増やす ((e))。

`REVOKE` が要る理由は `0006` が逐語で書いているとおりである — 既存 application では `ALTER DEFAULT PRIVILEGES FOR ROLE developer_role` が既に立っており、表を作った瞬間に runtime role へ DML が自動付与されてしまうため、**両 provisioning 経路が同一の終状態に着くように明示的に打ち消す**。**打ち消したうえで runtime role へ `SELECT` を戻すのが U-2 の裁定 (2026-09-05) である** — 終状態は「runtime role は台帳を読めるが書けない」であり、developer role は所有者として既存 bookkeeping 表と同じ射程を持つ (§3.9)。

**(b) 出し方は §2 制約 8 の「対」である。**

- **(i) provisioning テンプレート `0003_provision_application.sql` を改訂する** — 新規 application は台帳付きで provision され、かつ**その時点で存在する per-app upgrade 番号をすべて「適用済み」として記録**した状態で生まれる (テンプレートは終状態を直接作るため)。**MitateDB の seed は `{6, 8}`、r2db は `{9}`** である (§8 の割当。r2db には先行 per-app upgrade が無い)。
- **(ii) 既存 application 用の per-app upgrade script** (r2db `0009` / MitateDB `0008`、§8 で確定) が台帳を作り、**自番号を記録する**。**MitateDB はさらに `0006` の適用済みを backfill する** — 判定は `public._mdb_field_types` の存在 (`to_regclass('public._mdb_field_types') IS NOT NULL`)。r2db には backfill 対象が無い。**`_mdb_field_types` が無ければ 6 を記録しない** — これは D-4 (b) の集合差による「未適用」定義と組み合わさって正しく機能する: 台帳が `{8}` になった DB では 6 が**未適用として残り**、`ops upgrade-applications` が後から `0006` を当てる。v1.0 の「最大番号」定義ではこの穴が永久に検出されなかった。

**(c) 規律** (以後の per-app upgrade script が満たすもの):

1. **末尾で自番号を台帳へ `INSERT … ON CONFLICT DO NOTHING` する。** `\c` 後の本体は 1 トランザクションで包み、**DDL と台帳記録を原子にする** (既存儀式が既に `BEGIN … COMMIT` である)。
2. **冪等でなければならない** — 再実行しても終状態が変わらない (`CREATE … IF NOT EXISTS` / `ON CONFLICT` / `to_regclass` ガード)。
3. **skip 経路 (`\q`) を持たない。** psql は `\q` で **exit 0** を返すので、skip は成功と区別できない (§1.5 の 7a)。対象外の application は ops 側が registry の `database_name` で絞る (§1.5 の 8)。
4. **命名は `NNNN_<name>_upgrade.sql`** (§8 の命名規範)。

**`0006` は出荷済みで in-place で触らないため、この規律の対象外として明示の許可リストに載せる** (`\q` 経路を持つこと、自番号の台帳 INSERT を持たないことの両方が許可の対象である)。

**(d) 規律は静的テストで固定する。** 両 peer のテストが自 peer の `migrations/` 配下の per-app upgrade script (命名 `NNNN_<name>_upgrade.sql`) を走査する。**許可リストは番号の集合**であり、各 peer のテストが自 peer 分だけを持つ (MitateDB = `{6}`、r2db = 空)。

**検査する規則** (プロトタイプの実挙動に逐語で寄せた確定文、§10):

- **(b) 走査規則** — 各 script が `INSERT INTO public._{r2db,mdb}_platform_upgrades` を含む**1 つの文**の中に、**自番号の整数リテラル (ゼロ埋めを外したもの)** と **`ON CONFLICT`** の両方を含むこと。`VALUES ('0009', …)` のようなゼロ埋め文字列は**不適合**である。
- **トランザクション内の位置は静的には検査しない。** 規律ではあるが (上の 1)、静的に見るのは脆い。代わりに**実 PG テスト「本体が失敗したとき台帳行が残らない」**で担保する。
- **(d) 三者一致** — {`*_upgrade.sql` の番号集合} == {テンプレート `0003` の seed 集合} == {パッケージ定数の集合} を静的に照合する。per-app 番号は (1) script のファイル名、(2) テンプレートの seed リスト、(3) 「パッケージが知る番号」定数 (D-3 (f)、§12 LQ4-2) の 3 か所に散るため、同期漏れを機械的に閉じる。**(3) は U-2 の裁定 (runtime `SELECT` + cell open 時の集合検査) により無条件に存在する** — 三者一致は本フェーズの必須検査である。
- **(c) 非空振り** — 本フェーズ出荷後の期待は **適合 ≥ 1** (r2db `0009` / MitateDB `0008`) **かつ 違反 0 かつ 免除 = {MitateDB `0006`}** である (常設規律 8)。**変異先行の完了条件**: 新 script から台帳 INSERT を落とすと違反 1 件が出ること。
- **(e) 冪等性**は規律として明文化するが静的には検査しない (レビュー証拠として §10 に置く)。

**常設規律 5 に従い、設計を実装に移す前に逐語スキャナのプロトタイプを両 peer に走らせ、出力を §10 に貼る。** 走査ヘルパは両 peer 同名にし、`_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py:2298` / MitateDB 同型) に行を足して同型性を固定する — D-1 (b)(ii) の ms 正規化ヘルパも同じ対象に加える。表の内容を pin するテストは行数を名前に持つため (`test_isomorphic_target_table_is_pinned_to_its_current_18_rows`、r2db `tests/test_audit_query.py:2335` / MitateDB `:2074`)、**その関数名も同時に改める**。(着手時 18 行 → WP-0 最終追補後 24 行、監督裁定 2026-09-05 裁定 4。改称後の pin テスト名は `test_isomorphic_target_table_is_pinned_to_its_current_24_rows`、r2db `tests/test_audit_query.py:2394` / MitateDB `:2133`。)

**(e) 既存 backend の除外集合を同じ WP で拡張する** (**監督裁定 2026-09-05**、レビュー 2 本の重大指摘)。台帳表を `public` に作ると、**現物の bookkeeping 除外がどちらも 1 件だけ**であるため、台帳を作った瞬間に既存の機構が壊れる。**この作業を WP-C の完了条件に明記する** (§11)。

- **(i) 両 peer の backend の bookkeeping 除外集合を集合化して台帳名を加える。**
  - **r2db**: `r2db-api/src/r2db_api/postgres.py:139` の `_REVISION_TABLE` (`_r2db_schema_revision`) が**唯一の除外名**であり、3 か所で除外に使われている — `_load_catalog` の表列挙 (`:861` の `t.table_name <> {revision_table}`)、同じく列の収集 (`:891`)、そして RLS 検査 `_rls_offenders` (`:1780`)。除外用の**名前の集合**を新設し (`_REVISION_TABLE` 自体は `:1861` / `:1869` の当該表への実アクセスで名前として使われ続けるため残す)、この 3 か所を集合に対する除外へ改める。**放置すると**: 台帳表は `id bigint GENERATED ALWAYS AS IDENTITY` も `_r2db_revision` も持たないので `offenders` に入り (`:915-925`)、`application_catalog` と catalog を読む**すべての schema operation** (`:1589` 近傍の `schema_objects` 会計は `_load_catalog` を呼ぶ) が恒久的に `SERVICE_UNAVAILABLE` (503) になる。**共通 conformance の catalog 系 vector も落ちる。** さらに `_rls_offenders` は `verify_row_level_security` (`:1783`) だけでなく `_create_entity` の直後検査 (`:1724`) からも呼ばれるので、除外しないと**すべての `create_entity` が 503 になる** (§8.5 condition 3(b) の inline 検査)。
  - **MitateDB**: `MitateDB-api/src/mitatedb_api/backend_postgres.py:384-391` の `schema_count()` が `table_name NOT IN (%s, %s)` で `_SCHEMA_REVISION_TABLE` (`:329`) と `_FIELD_TYPES_TABLE` (`:338`) の 2 件だけを除いている。**第 3 の名前を足す。** 足さないと全 application の `schema_objects` 会計が +1 ずれる (SI-08 の限度検査に効く)。catalog 本体は `_mdb_field_types` 由来なので entity 列挙には出ない (peer 非対称、§3.10)。
- **(ii) r2db の RLS 監視ビュー `public._r2db_missing_rls` の除外名に台帳名を加える。** ビューは `r2db-api/migrations/0003_provision_application.sql:234-241` で `_r2db_schema_revision` **1 件だけ**を名指しで除外し、RLS が enable / force でない `public` の表を列挙する「live view, not a point-in-time claim」(§8.5 condition 3(b) の運用証拠)。台帳表に RLS を付けない ((a)) 以上、除外しないと**全 application で 1 行が恒久的に残る** — `r2db-api/tests/test_postgres.py:519-520` の clean-state assert が落ち、runbook の運用証拠が恒常的な偽陽性を出し続ける。**既存 application のビューは `0003` 適用時点の定義で固まっている**ので、**テンプレート `0003` の改訂と per-app upgrade script の両方**で `CREATE OR REPLACE VIEW` が要る (§2 制約 1 の「対」の規律がビューにも及ぶ)。**MitateDB に同型のビューは無い** (実測) — §3.10 に非対称として記録する。

**(f) data-plane は cell を開く時点で台帳を検査する** (**依頼者裁定 2026-09-05**、U-2)。

- **比較は D-4 (b) と同じ集合差である** — 未適用 = {パッケージ定数が持つ per-app 番号の集合} − {台帳に行が存在する番号の集合}。**台帳表が無い application DB は `applied = {}`** として扱い、全 per-app 番号が未適用になる。
- **未適用が空でなければ、その cell を開く時点で `SERVICE_UNAVAILABLE` を返す** — 最初のリクエストが storage の深部で失敗するのを待たない (現状は `StorageConfigurationError` → `SERVICE_UNAVAILABLE` として最初のリクエストで判明する、§1.4)。メッセージは**未適用の番号**と**次に打つコマンド `ops upgrade-applications`** を示す (§3.8 の **F-12**、制約 7)。
- **検査を起動時ではなく cell open 時に置く理由**: 台帳は **application DB の中**にあり、data-plane プロセスは cell を開くまでその DB へ接続しない。起動時に全 application を走査すると、data-plane に registry の列挙と全 application DB への到達を新たに要求することになる (§4 で退けた「到達範囲を広げる」形と同じ代償である)。
- **読み取りは runtime role の `SELECT` 1 本**である ((a) の `GRANT SELECT` はこの目的で置く)。読み取りは迂回経路にならない (SI-12 が禁じるのは runtime が**特権を行使する**経路である、§7)。
- **パッケージ定数の置き場は WP が決める**が、**その集合が `migrations/` の per-app script 番号および `0003` の seed リストと一致することは D-3 (d) 規則 (d) の三者一致静的検査が無条件に担保する** (§10、§9.4 の 5、§12 LQ4-2) — これが U-2 の裁定が名指しした「代償の固定」である。
- **台帳にパッケージが知らない番号がある配備は止めない** — 集合差の向きは D-4 (b) と同じ「パッケージが要求する番号がすべて記録されているか」だからである。

### D-4 ops 一括適用コマンド

**決定**: `ops upgrade-applications` を両 peer に新設する。**provision DSN のみで動く** (API プロセスはこの資格を持たない。§7 の SI-02 行)。

**(a) 引数**

| 引数 | 意味 |
|---|---|
| `--application <id>` | 対象を 1 つに限る。既定は registry の**全 application** (`database_name` が NULL でない行のみ、§1.5 の 8) |
| `--script <NNNN>` | 当てる per-app upgrade を 1 つに限る。**その番号が未適用である DB にだけ当てる** — 台帳に記録済みの DB では `recorded, skipped` と出力し、**当該 DB は成功扱い**とする。既定は**未適用のすべて** |
| `--dry-run` | 何も当てず、application ごとの applied / pending だけを出力する (`upgrade-status` と同じ集計) |

**`enabled` は対象選択に影響しない** — **無効化中の application の DB も一括適用の対象に含める**。無効化は API 提供の停止であって DB の凍結ではなく、終状態を揃えておくことが再有効化を安全にするからである。

**(b) 未適用の定義と手順。**

**未適用 = {パッケージが持つ per-app 番号の集合} − {台帳に行が存在する番号の集合}** である (**集合差**。v1.0 の「台帳の最大番号より大きい」は誤り — 台帳は `upgrade_number` を PK に持つ**行の集合**であり、最大値方式では**穴**、例えば台帳が `{8}` で 6 が欠けている状態が永久に検出されない)。**台帳が無ければ全 per-app script**が未適用である。

手順: registry の applications を列挙 → 各 application DB の台帳を読む → 未適用を**番号順**に `psql` subprocess で当てる。

- **application DB への接続**: ops が持つのは platform DB を指す provision DSN だけなので、**`psycopg.conninfo.conninfo_to_dict(provision_dsn)` の `dbname` を registry の `database_name` に差し替えて接続する** (台帳の読み出しは Python 側で行う。script 側の `\c :database_name` とは別経路である)。
- **`psql` の呼び出し形**: `MitateDB-api/src/mitatedb_api/ops.py:541-550` の `_run_deprovision_script` の**呼び出し形だけ**を踏襲する — `subprocess.run(["psql", dsn, "-v", "ON_ERROR_STOP=1", "-v", f"<識別子変数>=<id>", "-f", str(script)], capture_output=True, text=True)`。**`_die` は使わない** (`_die` は即時 exit 2 であり、(c) の「止めずに全 DB を回す」と両立しない) — **`returncode` を application ごとに集計する**。
- **識別子変数名は peer で異なる**: **r2db は `-v app_slug=…`、MitateDB は `-v app_id=…`** (それぞれの `0004_deprovision_application.sql` が逐語でそう書く)。§3.10 に対応表として置く。
- **r2db 側には `psql` subprocess も `_migrations_dir()` も無いので新設する** (§1.5 の 7)。

**(c) 冪等と失敗時の扱い**: 再実行で何も起きない。**1 つの DB の失敗で止めず全 DB を回し、失敗した DB を列挙して非 0 で終わる。**

**失敗した DB については developer role membership の掃除手順を出力に含める。** 既存儀式は `GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE` が `BEGIN` の外、`REVOKE` が `COMMIT` の後にあり、本体でエラーが出ると psql は exit 3 で止まって **`REVOKE` に到達しない** (§1.5 の 7b)。全 DB を回す設計である以上、**1 回の一括適用で複数 application 分の membership が provision role に累積し得る**。SI-02 / SI-12 が守る境界を破りはしない (provision role は元から全 application DB へ到達できる) が、「儀式の membership は一時的である」という既存の設計意図 (`0003` のコメントが逐語で `the temporary membership itself is revoked explicitly below rather than left to accrue` と書く) を崩す。したがって **ops は失敗した application ごとに `REVOKE <developer_role> FROM <provision role>;` を出力に含める** (§9.1、§3.11 の 8)。

**(d) 出力**: application ごとに **`applied = [番号…]` / `pending = [番号…]`** と当てた結果を 1 行。**skip した DB (`--script` が記録済み、`database_name` が NULL) は別枠で列挙する** — psql の `\q` skip は exit 0 で返り成功と区別できないため、無音で成功に見える経路を出力側で閉じる (§1.5 の 7a)。末尾に成功数 / 失敗数 / skip 数。

**(e) 終了コード**

| コード | 意味 |
|---|---|
| `0` | 全対象 DB で未適用なし (`--dry-run` を含む) |
| `1` | 列挙に失敗した (registry が読めない、provision DSN へ接続できない — 両 peer の既存慣行 `FoundationError` / `psycopg.Error` = 1 と同じ、§1.5 の 7) |
| `2` | 使い方の誤り (provision DSN が env に無い、引数不正 — 両 peer の既存慣行 `_die` = 2 と同じ、§1.5 の 7) |
| `3` | 少なくとも 1 つの DB で適用に失敗した (psql exit 3、または `database_name` が NULL) |
| `4` | `--dry-run` で未適用があった |

(監督裁定 2026-09-05、v1.1 起草者の疑義 1 への回答: 既存慣行 `1` / `2` を保ち、本フェーズ固有の結果には `3` / `4` を割り当てる。)

**(f) `0006` の単独再実行は安全ではない** (v1.0 の「冪等だから安全」は削除する)。`0006` の backfill は `information_schema.columns` を走査し、除外は `('_mdb_schema_revision', '_mdb_field_types')` の 2 件だけである。**台帳表 `public._mdb_platform_upgrades` が既に存在する DB に `--script 0006` を流すと、台帳表の 3 列が `_mdb_field_types` に混入する** (`ON CONFLICT (entity, field) DO NOTHING` は新しい 3 行の挿入を止めない。しかも物理型マッピングにより `upgrade_number integer` は `boolean` として記録される)。`0006` は出荷済みで in-place 改訂できない (制約 1) ため、**防御は ops 側にしか置けない — これが (a) で `--script` を未適用限定にする根拠である。**

通常経路 (台帳が無い DB に全 per-app script を番号順に当てる) ではこの穴に落ちない。台帳が無い既存 MitateDB DB では `0006` が再実行され得るが、その時点では台帳表がまだ無いので混入は起きず、台帳 init script (`(b)(ii)`) の backfill と同じ終状態に収束する。

### D-5 適用状態の可視化 (peer-local。**U-1 の裁定によりこれが唯一の可視化経路である**)

**決定**: **既存の application 一覧コマンドは変更しない** (r2db `list-apps` / `cmd_list_apps` (`ops.py:737-750`)、MitateDB `list-applications` / `cmd_list_applications` (`ops.py:382-387`、CLI 登録は `:805-806`))。代わりに**両 peer に新サブコマンド `ops upgrade-status [--application <id>]` を新設する**。

理由は**既存 2 コマンドの非対称**にある (§1.5 の 7)。r2db の `list-apps` は provision DSN で registry を SQL 直読みするが、**MitateDB の `list-applications` は control credential で `ControlPlaneService.list_applications` を呼び、契約 shape の `ApplicationsResult` をそのまま出す**。ここに列を足すと、(i) service の返り値にキーを足す = `additionalProperties: false` の**契約変更**になる (U-1 の裁定「載せない」と矛盾する)、または (ii) このコマンドに provision DSN を新たに要求することになり、「control credential だけで application 一覧を見る」という現在の資格要件が変わる。**どちらも避ける。**

**`ops upgrade-status`**:

- **provision DSN のみで動く。**
- application ごとに **`applied = [番号…]`**、**`pending = [番号…]`**、`database_name` を表示する。台帳が無い application は `applied = []` とする。
- 終了コード: **`0` = 未適用なし / `4` = 未適用あり / `1` = 列挙失敗 / `2` = 使い方の誤り** (D-4 (e) と同じ割当)。
- `ops upgrade-applications --dry-run` は**これと同じ集計**を出す。

**MitateDB の `list-applications` は契約 shape のまま**である (§3.10 に非対称として記録)。

**契約への露出は行わない** (U-1 の裁定: peer-local に留める。共通契約は 1.6.0 のまま無変更)。**cell を開く時点の検出は行う** (U-2 の裁定。D-3 (f)、§3.7、§3.8 の F-12) — 適用漏れは `ops upgrade-status` で見えるだけでなく、当該 application の cell を開く時点で `SERVICE_UNAVAILABLE` として現れる。

### D-6 文書と対応表

**決定**: 次を本フェーズで更新する。

1. **`security/CONTROL_MAPPING.md`**
   - **SI-02 行** — `ops upgrade-applications` が provision DSN のみで動き、API プロセスがその資格を持たないこと。
   - **SI-12 行** — 台帳表と宣言表の権限 (**台帳表の runtime role は `SELECT` のみ**、依頼者裁定 U-2。宣言表は application role が接続しない platform DB にある)。**cell open 時の集合検査 (D-3 (f)) と F-12 も併せて記す** — runtime 資格から見えるのは自 application の台帳の読み取り 1 本だけであり、特権を行使する経路は増えない。
   - **SI-14 行の点 (12)** — 逐語 "nothing enforces it" を改める。**置換文言は限定付きである**: 「**同一の platform データベースを前提に**、宣言の根拠と実効値の根拠が**同一の catalog** になった。両プロセスは同じ一次情報から導出し、各プロセスは自身の実効値との一致を起動時に検査する」。**両プロセスが同じ platform DB を指していること自体は本設計が検証しない** (§3.11 の 7) ので、この限定を落とすと過大主張になる。**この点は本フェーズの成果そのものであり、更新を落とすと文書が現物と逆になる。**
2. **runbook と配備設定の例** — `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`、`MitateDB-api/docs/cloud-run-cloud-sql.md`、DEPLOY 系作業指示書に、**「ops declare → 両プロセス再起動」「ops upgrade-applications」「ops upgrade-status」の手順**と**廃止 env の一覧**を置く (§9)。

   **配備設定の例ファイルも成果物に含める** — 廃止 4 変数を**実値で設定したまま残すと、それをコピーした配備は次回起動で必ず F-1 / F-2 で止まる**。起草時に `DATA_BASE_URL|CONTROL_BASE_URL|AUDIT_STATEMENT_TIMEOUT_MS|AUDIT_IDLE_TIMEOUT_MS` を grep して列挙した該当箇所:

   | ファイル | 廃止変数を**実値で設定**している行 | 言及のみの行 |
   |---|---|---|
   | `r2db-api/deploy/env/api.env.example` | `:120-121` (`R2DB_AUDIT_STATEMENT_TIMEOUT_MS` / `_IDLE_TIMEOUT_MS`)、`:162` (`R2DB_DATA_BASE_URL`) | `:110`、`:168`、`:175` (`R2DB_CONTROL_BASE_URL` はコメントアウト) |
   | `r2db-api/deploy/env/control.env.example` | `:72` (`R2DB_DATA_BASE_URL`)、`:79` (`R2DB_CONTROL_BASE_URL`)、`:139-140` (timeout 2 本) | `:25-26`、`:77` |
   | **MitateDB の対応物** | **`deploy/env/*.example` に相当するファイルは存在しない** (実測: `MitateDB-api/config/foundation.env.example` は 4 変数のいずれにも触れていない)。**配備時の env は `MitateDB-api/docs/cloud-run-cloud-sql.md` の `gcloud … --set-env-vars=…` 例に直接書かれている** — `:843` (`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`)、`:890` (同 2 本) | 同ファイル `:324`、`:343`、`:848-856`、`:893` |

   → **MitateDB 側は上記 runbook 1 本の改訂で覆われ、新たに触る example ファイルは無い。** r2db 側は runbook 2 本に加えて `deploy/env/*.example` 2 本を改訂する (廃止 4 変数の削除と、代わりに打つ ops コマンドの案内)。
3. **正本 2 文書への日付付き注記** (本文は書き換えない、既存規律) — `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4、`PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 L6-5a と L6-20 (f) に閉止注記を置く。
4. **契約バージョン** — **契約無変更 (1.6.0 のまま)** である (**依頼者裁定 2026-09-05**、U-1)。`spec/data-service-api.v1.json` も `conformance-tests/` の vector / port も触らない (§6.1)。**本フェーズは契約公開コミットも版束縛の追記も伴わない。**

### 3.7 起動シーケンス

**data-plane プロセス** (`r2db_api.main` / `mitatedb_api.main`)

1. 既存の env 読み取り (DSN、pepper、`*_CONTROL_PLANE_STATUS` ほか)。
2. **廃止 env の不在検査** — **composition root に渡された env mapping** (`os.environ` ではない) に 4 変数のいずれかが**定義されていれば、値によらず** fail-fast (F-1 / F-2)。
3. platform 接続の確立 (既存)。
4. **宣言表の読み出し。** 検査は**この順**で行う — **(a) 表そのものの存在** (無ければ F-8)、**(b) 行の存在** (`surfaces` 行が無ければ F-3、`audit_coalescing_window_ms` 行が無ければ F-4)。順序を守らないと、migration 未適用の配備が `relation does not exist` の生の psycopg 例外で落ちる。
5. **値の検証** — `surfaces` の形式検証 (既存 validate、落ちれば F-5)、`audit_coalescing_window_ms` の型・範囲検証 (落ちれば F-4b)、**`control` 行 × `*_CONTROL_PLANE_STATUS` の整合検査** (F-6)。
6. **書き手 role の設定検査 (二重検査、D-1 (b))** — (i) `pg_db_role_setting` (`setdatabase = 0` の行) に `statement_timeout` と `idle_in_transaction_session_timeout` の両方があること (欠ければ F-7)、その ms 値が 1 以上であること (0 / 負数なら F-10)、per-database 行 (`setdatabase ≠ 0`) が無いこと (あれば F-11)、(ii) **監査書き手が使う pool の接続 (login role = 自 role)** で `pg_settings` から取った実効値が、(i) の値と **ms 整数で一致**すること (食い違えば F-9)。
7. audit sink を構築する。**セッション `SET` はしない** (D-1 (b))。
8. `DataService` / `AuditRouter` へ窓を渡し、capability document へ `surfaces` を注入する。

**1〜8 はすべて起動時であり、読みは起動時スナップショットである** (D-1 (e) / D-2 (g)、依頼者裁定 U-3)。

**data-plane プロセスの cell open 時** (application ごと。起動シーケンスの後、当該 application の cell を初めて開くとき)

9. **台帳 `public._<peer>_platform_upgrades` の番号集合を読む** (runtime role の `SELECT`、D-3 (a))。**台帳表が無ければ `applied = {}` として扱う。**
10. **未適用 = {パッケージ定数の番号集合} − {台帳の番号集合}** を求め、**空でなければその cell を提供せず `SERVICE_UNAVAILABLE` を返す** (**F-12**。メッセージは未適用の番号と `ops upgrade-applications` を示す)。D-3 (f)、依頼者裁定 U-2。

**control-plane プロセス** (`r2db_api.control_main` / `mitatedb_api.control_composition`)

1〜5 は同じ (control プロセスは自らの control surface を必ず持つので、`surfaces.control` は**無条件必須**)。
6. **両書き手 role の 4 設定を catalog から読む** → 欠ければ F-7、0 / 負数なら F-10、per-database 行があれば F-11。`visibility_lag_ms` を D-1 (c) の式で導出する。control プロセス自身も `control_audit` の書き手であるから、**自 role については D-1 (b)(ii) の実効値一致検査も行う** (食い違えば F-9)。**`*svc_api` (data-plane の書き手) の実効値は検証できない** — role 設定は login 時にのみ適用され、`SET ROLE` では取れないからである。その検証は data-plane プロセスが自分で行う (§3.11 の 9)。
7. `audit_coalescing_window_ms` を宣言表から読む。
8. capability document を組む。

### 3.8 fail-fast メッセージ一覧

**env 名 / migration 番号 / 次に打つ ops コマンド名**を含めて出す (制約 7)。`<peer>` は `r2db_api` / `mitatedb_api`、`<NNNN>` は §8 が確定した番号 (r2db `0008` / `0009`、MitateDB `0007` / `0008`) に置き換える。

**F-1〜F-11 はプロセス起動時の出力であり、API 応答や公開 endpoint には現れない** (SI-10)。F-5 / F-9 のように宣言値そのものをメッセージに含めるものがあるため、readiness / health endpoint へ転記しないことを規律として明記する。

**F-12 だけは起動時ではなく cell open 時であり、API 応答として利用者に届く** (依頼者裁定 2026-09-05、U-2)。**F-12 のメッセージは未適用の番号と ops コマンド名を示す** (裁定文のとおり)。API 応答に現れる以上、**DSN・資格情報・内部ホスト名・宣言値は置かない** (SI-10)。

| # | 条件 | 出す側 | メッセージ骨子 |
|---|---|---|---|
| F-1 | `*_AUDIT_STATEMENT_TIMEOUT_MS` または `*_AUDIT_IDLE_TIMEOUT_MS` が **env mapping に定義されている** (値は問わない。空文字列を含む) | 両 | `R2DB_AUDIT_STATEMENT_TIMEOUT_MS is no longer read (Q4 D-1): the audit writer roles carry statement_timeout / idle_in_transaction_session_timeout as PostgreSQL role settings, applied by migration <NNNN>. This variable is rejected whenever it is defined, whatever its value (an empty string included). Unset this variable, then set the value with 'python -m <peer>.ops set-platform-timeouts --statement-ms <N> --idle-ms <N>' and restart both processes. Note this setting also bounds every other connection made by this role (credential store lookups and control-plane registry operations included).` |
| F-2 | `*_DATA_BASE_URL` または `*_CONTROL_BASE_URL` が **env mapping に定義されている** (値は問わない) | 両 | `R2DB_DATA_BASE_URL is no longer read (Q4 D-2): surfaces are declared in <registry>.platform_declarations, created by migration <NNNN>. This variable is rejected whenever it is defined, whatever its value (an empty string included). Unset this variable, then declare with 'python -m <peer>.ops declare-surfaces --data-base-url <URL> [--control-base-url <URL>]' and restart both processes.` |
| F-3 | `platform_declarations` に `surfaces` 行が無い | 両 | `no 'surfaces' row in <registry>.platform_declarations: contract 1.6.0 requires surfaces.data unconditionally. Declare it with 'python -m <peer>.ops declare-surfaces --data-base-url <URL> [--control-base-url <URL>]', then restart both processes.` |
| F-4 | `audit_coalescing_window_ms` 行が無い | 両 | `no 'audit_coalescing_window_ms' row in <registry>.platform_declarations: migration <NNNN> seeds it with the shipped default (60000). Apply that migration, or set the value with 'python -m <peer>.ops declare-coalescing-window --ms <N>', then restart both processes.` |
| **F-4b** | `audit_coalescing_window_ms` 行はあるが**値が壊れている** (jsonb の数値でない / 整数でない / 負数) | 両 | `'audit_coalescing_window_ms' in <registry>.platform_declarations must be a non-negative integer (0 means no coalescing), got '<value>'. This table can be edited by hand, so the value is validated on every read as well as on write. Re-set it with 'python -m <peer>.ops declare-coalescing-window --ms <N>', then restart both processes.` |
| F-5 | 宣言された `base_url` が形式検査に落ちる (絶対 URL でない / 接尾辞違い / 末尾スラッシュ) | 両 | `surfaces.data.base_url in <registry>.platform_declarations must be an absolute URL ending in '/v1' with no trailing slash, got '<value>'. Re-declare it with 'python -m <peer>.ops declare-surfaces …'.` |
| F-6 | `surfaces.control` の有無と `*_CONTROL_PLANE_STATUS` が食い違う | data-plane | `surfaces.control is declared but R2DB_CONTROL_PLANE_STATUS is 'unavailable' (contract 1.6.0: a deployment declaring control_plane unavailable omits surfaces.control). The surfaces row is shared by BOTH processes: re-declaring with '--no-control' removes the control declaration for the control-plane process too, and that process will then fail to start (F-3). Unless this deployment really offers no control surface, change R2DB_CONTROL_PLANE_STATUS on this process instead, then restart both processes. If the deployment genuinely has no control surface, re-declare with 'python -m <peer>.ops declare-surfaces --data-base-url <URL> --no-control'.` (逆向き — `unavailable` 以外なのに `control` 行が無い — も同型の 1 文で出す) |
| F-7 | 書き手 role に 2 設定のいずれかが無い | 両 | `role 'r2dbsvc_api' has no statement_timeout / idle_in_transaction_session_timeout in pg_db_role_setting: migration <NNNN> is not applied to this platform database, and an audit writer must never run unbounded. Apply migration <NNNN>, or set the values with 'python -m <peer>.ops set-platform-timeouts --statement-ms <N> --idle-ms <N>', then restart both processes. Note this setting also bounds every other connection made by this role (credential store lookups and control-plane registry operations included).` |
| F-8 | 宣言表そのものが無い (migration 未適用) | 両 | `relation <registry>.platform_declarations does not exist: migration <NNNN> (Q4 D-2) has not been applied to this platform database. Apply it with 'psql "$R2DB_CONTROL_DSN" -f r2db-api/migrations/<NNNN>_….sql', then restart both processes.` |
| F-9 | 実効値が `pg_db_role_setting` の値と食い違う (D-1 (b)(ii)) | 両 | `role 'r2dbsvc_api' declares statement_timeout = 5000 ms in pg_db_role_setting but this connection's effective value is 30000 ms (both shown in milliseconds; PostgreSQL renders these settings in whichever unit divides evenly, so never compare the rendered strings): the declared visibility_lag_ms would not describe the effective connection. Remove the override -- a connection-string 'options=-c …', PGOPTIONS, or an 'ALTER ROLE … IN DATABASE … SET' row -- so the role setting is the effective value, or change the role setting with 'python -m <peer>.ops set-platform-timeouts --statement-ms <N> --idle-ms <N>', then restart both processes. Note this setting also bounds every other connection made by this role.` |
| **F-10** | 書き手 role の設定はあるが **ms 値が 0 または負数** | 両 | `role 'r2dbsvc_api' declares statement_timeout = 0 in pg_db_role_setting, which PostgreSQL reads as "no limit": an audit writer must never run unbounded, and the declared visibility_lag_ms would describe a bound that does not exist. Set a positive value with 'python -m <peer>.ops set-platform-timeouts --statement-ms <N> --idle-ms <N>' (the command rejects 0 and negative values), then restart both processes.` |
| **F-11** | 書き手 role に **per-database の role 設定行が存在する** (`pg_db_role_setting.setdatabase ≠ 0`) | 両 | `role 'r2dbsvc_api' has an 'ALTER ROLE … IN DATABASE …' setting row for database '<db>', which takes precedence over the database-independent role setting this deployment declares. The role setting must be a single database-independent row. Remove it with 'ALTER ROLE r2dbsvc_api IN DATABASE <db> RESET statement_timeout, idle_in_transaction_session_timeout;' (issued on the provision DSN), then restart both processes.` |
| **F-12** | **cell open 時**: 台帳の番号集合に対して**未適用の per-app upgrade がある** (台帳表が無い場合を含む) | data-plane (**起動時ではなく cell open 時。API 応答に現れる唯一の項目**) | `This application's storage is missing platform upgrade(s) <未適用の番号…>: the deployment must apply them before this application can serve requests. Run 'python -m <peer>.ops upgrade-applications' (its '--dry-run' shows applied and pending per application), then retry.` — HTTP 503 / `SERVICE_UNAVAILABLE` (D-3 (f)、§3.7 の 9〜10) |

**F-12 についての注記** (**依頼者裁定 2026-09-05**、U-2): 現状の検出は**最初のリクエスト**が storage の深部で `StorageConfigurationError` になる形であり (§1.4)、原因も次に打つ手も応答から読み取れない。F-12 は同じ `SERVICE_UNAVAILABLE` を**適用漏れという原因と `ops upgrade-applications` という手当て付き**で、cell を開く時点に前倒しする。**止めるときは必ず次に打つコマンドを示す** (決定軸、制約 7)。

**F-6 の推奨の向きについての注記**: **既定の推奨は「`*_CONTROL_PLANE_STATUS` を直す」である** (**監督裁定 2026-09-05**)。宣言表の `surfaces` 行は**両プロセス共通の 1 行**なので、`--no-control` で再宣言すると control 行が消え、**次に再起動した control プロセスが F-3 で起動不能になる** (§3.7 control 1〜5 は `surfaces.control` を無条件必須とする)。運用者は AI エージェント前提であり提示されたコマンドを素直に打つので、破壊的でない側を既定に置く。

**F-6 の対称性についての注記**: `*_CONTROL_PLANE_STATUS` は各プロセスの env のまま残る (本設計は廃止しない) — control プロセスは定義上 control surface を持ち、data-plane プロセスの宣言だけが配備で変わるためである。受理値は r2db では `{"enabled", "unavailable"}` であり (`r2db-api/src/r2db_api/main.py:182` 実測)、契約の "control_plane other than unavailable" との照合で F-6 が誤爆する余地は無い。

### 3.9 新設する 2 表の DDL 骨子と権限

| 表 | 位置 | 所有者 | provision role | data-plane platform role | control-plane role | runtime role | developer role |
|---|---|---|---|---|---|---|---|
| `<registry>.platform_declarations` (D-2) | platform DB / registry スキーマ | provision role | 全権 (owner) | `SELECT` | `SELECT` | 接続しない | 接続しない |
| `public._<peer>_platform_upgrades` (D-3) | 各 application DB / `public` | **developer role** (§1.5 の 5 の儀式により構造的にこうなる) | **`GRANT SELECT`** (D-3 (a))。書きは儀式で developer role を一時 assume して行う | 接続しない | 接続しない | **`SELECT` のみ** (**依頼者裁定 2026-09-05**、U-2。cell open 時の集合検査のため。D-3 (f)) | **所有者** (既存 bookkeeping 表と同じ射程) |

**台帳表の書き込み経路について** (v1.0 の記述を現物に合わせて訂正する)。

- **運用上の書き込み経路は provision DSN に閉じる** — 台帳を書くのは ops と migration script だけであり、application DB へ `\c` できるのは provision role だけである。
- **構造的には、表の所有者が developer role であり、data-plane プロセスが保持する developer 接続 (`MitateDB-api/src/mitatedb_api/backend_postgres.py:371` の `self._developer = psycopg.connect(developer_dsn, autocommit=False)`、r2db は `postgres.py:781` の `self._developer = _PoolHandle(…, developer_dsn, …)`) は同じ DB 内でこの表に完全な権限を持つ。** これは `_mdb_field_types` / `_r2db_schema_revision` と**同じ射程**であり、application isolation の**内側に閉じる** (他 application にも platform DB にも届かない)。
- **application API から到達する経路は無い** — 両 peer とも `_` で始まる識別子を構造的に拒否する (r2db は `structured.py:59` の `_reject_reserved_prefix` が `IDENTIFIER_INVALID` を返し、MitateDB は `identifiers.py:19` の `_IDENTIFIER = ^[a-z][a-z0-9_]{0,62}$` が `[a-z]` 始まりを要求する)。
- したがって **台帳は運用の一次記録であって、改竄不能な証拠ではない。** 脅威モデルが明示的に想定する「application-facing implementation defect が 1 つ起こる」(`security/SECURITY_INVARIANTS_V1.md:58`) の下では、台帳行は当該 application の DB 内で改竄され得る — 射程は既存 bookkeeping 表と同一である。

**runtime role の権限は `SELECT` のみである** (**依頼者裁定 2026-09-05**、U-2)。**書き込みは付与しない**ので、上の「運用上の書き込み経路は provision DSN に閉じる」は runtime 側からも構造的に保たれる。developer role については既存 bookkeeping 表と同じ射程 (所有者) を追認する。

### 3.10 両 peer の対応表

| 事項 | r2db-api | MitateDB-api |
|---|---|---|
| platform DB | `r2dbsvc_platform` | `mitatedb_platform` |
| registry スキーマ | `r2dbsvc_registry` | `mitatedb_registry` |
| provision role | `r2dbsvc_control` | `mitatedbsvc_provision` |
| provision DSN env | `R2DB_CONTROL_DSN` | `MITATEDB_PROVISION_DSN` |
| data-plane platform role (= `application_audit` 書き手 + credential store 読み手) | `r2dbsvc_api` | `mitatedbsvc_api` |
| control-plane role (= `control_audit` 書き手) | `r2dbsvc_controlplane` | `mitatedbsvc_controlplane` |
| 監査読み手 role (本設計の対象外) | `r2dbsvc_auditreader` | `mitatedbsvc_auditreader` |
| application 識別子列 | `application_slug` | `application_id` |
| 既存 bookkeeping 表 | `public._r2db_schema_revision` | `public._mdb_schema_revision` |
| 既存 per-app upgrade の初例 | **無し** | `public._mdb_field_types` (`0006`) |
| **新設** 宣言表 (D-2) | `r2dbsvc_registry.platform_declarations` | `mitatedb_registry.platform_declarations` |
| **新設** 台帳表 (D-3) | `public._r2db_platform_upgrades` | `public._mdb_platform_upgrades` |
| data-plane composition root | `src/r2db_api/main.py` | `src/mitatedb_api/main.py` + `config.py` |
| control-plane composition root | `src/r2db_api/control_main.py` | `src/mitatedb_api/control_composition.py` |
| `surfaces` 検証 | `main.py` / `control_main.py` の `_validate_surface_base_url` **2 コピー** (L6-17) | `src/mitatedb_api/surfaces.py` の**単一モジュール** |
| 窓の定数 | `audit_query.DECLARED_COALESCING_WINDOW_MS` (`:175`) | `audit_query.DEFAULT_COALESCING_WINDOW_MS` (`:178`) |
| timeout 既定定数 | `credential_store.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS` / `_IDLE_TIMEOUT_MS` | `application_audit.DEFAULT_AUDIT_STATEMENT_TIMEOUT_MS` / `_IDLE_TIMEOUT_MS` (`:52-53`) |
| ops モジュール | `src/r2db_api/ops.py` | `src/mitatedb_api/ops.py` |
| ops の application 一覧 (**本設計は触らない**、D-5) | `list-apps` / `cmd_list_apps` — **provision DSN + registry の SQL 直読み** | `list-applications` / `cmd_list_applications` — **control credential + `ControlPlaneService` 呼び出し**、出力は契約 shape の `ApplicationsResult` のまま |
| **新設** 適用状態コマンド (D-5) | `upgrade-status` (provision DSN) | `upgrade-status` (provision DSN) |
| ops の `psql` subprocess | **無し (新設)** | `_run_deprovision_script` (`:541-550`)。**呼び出し形のみ踏襲し `_die` は使わない** (D-4 (b)) |
| per-app script に渡す psql 変数名 (D-4 (b)) | **`-v app_slug=…`** | **`-v app_id=…`** |
| ops の migrations ディレクトリ解決 | **無し (新設)** | `_migrations_dir()` (`:373-375`) |
| RLS 監視ビュー (D-3 (e)(ii)) | `public._r2db_missing_rls` (`0003:234-241`)。**台帳表の除外名追加が要る** | **無し** (同型のビューを持たない) |
| bookkeeping 表の RLS 規律 | `_r2db_schema_revision` は `ENABLE` + `FORCE ROW LEVEL SECURITY` + application isolation ポリシー (`0003:212-216`)、runtime に `SELECT, UPDATE` (`0003:217`) | `_mdb_schema_revision` (`0003:137-142`) / `_mdb_field_types` (`0003:164-169`) は RLS 無し・runtime 無権限 |
| backend の bookkeeping 除外集合 (D-3 (e)(i)) | `postgres.py:139` の `_REVISION_TABLE` **1 件**、使用箇所は `:861` / `:891` / `:1780` | `backend_postgres.py:384-391` の `NOT IN (%s, %s)` **2 件** (`:329` / `:338`) |
| catalog に台帳表が現れるか | `_load_catalog` が `information_schema.tables` を列挙するので**現れる** (除外が要る) | catalog 本体は `_mdb_field_types` 由来なので entity 列挙には**現れない** (`schema_count()` の会計にだけ効く) |
| HTTP plug が宣言表を通るか (§6.1) | **通らない** (`assemble_control_stack(…, surfaces=…)` の明示注入)。表の読み出しは peer-local 実 PG テストが担う | **通る** (`build_control_service(env)` = composition root そのもの) |
| runbook | `docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`deploy/DEPLOYMENT_RUNBOOK.md` | `docs/cloud-run-cloud-sql.md` |
| env 接頭辞 | `R2DB_` | `MITATEDB_` |

### 3.11 既知の帰結 (決定の一部として記録する)

1. **`ALTER ROLE … SET` は role の全接続に効く。** `r2dbsvc_api` は `application_audit` の書き手であると同時に **credential store の接続 role** でもあり (§1.5 の 2a)、`mitatedbsvc_api` も同型である (起草時に実測)。したがって timeout の射程が「audit 書き手 pool」から**その role の全接続**へ広がる。既定 5000ms / 5000ms は credential 照会 (短い単発文) に実害が無い見込みだが、**射程が広がること自体は本設計の帰結である**。同様に `*_controlplane` role の設定は control-plane の registry 操作すべてに効く。
2. **`pg_db_role_setting` は「ALTER ROLE で明示的に設定された値」を映す catalog であり、接続の実効値そのものではない。** `ALTER ROLE … SET` を上回る優先順位を持つのは、**`ALTER ROLE … IN DATABASE … SET`、接続時 `options=-c …` / `PGOPTIONS`、セッション `SET`** である (`postgresql.conf` と `ALTER DATABASE … SET` は `ALTER ROLE … SET` より**低い**ので上書きにならない — v1.0 の列挙は誤っていた)。**この経路は設計で閉じた (D-1 (b)、監督裁定 2026-09-05)** — 書き手プロセスは起動時に catalog の 2 設定の存在と有効性 (F-7 / F-10)、per-database 行の不在 (F-11)、そして**書き手 pool の接続の実効値が catalog 値と ms 整数で一致すること** (F-9) を検査し、どれか欠ければ fail-fast する。したがって上書きされた配備は「宣言と食い違う配備」として起動時に止まる。§12 LQ4-5。
3. **r2db は `r2dbsvc_control` (CLI/provision role) にも `application_audit` への `INSERT` を持つ** (`0007_application_audit.sql:186`、将来の break-glass 用)。MitateDB は provision role に同じ付与をしていない (実測)。**宣言 `visibility_lag_ms` はこの帯域外経路について何も主張しない** — 本設計は 2 つの**サービス**書き手 role の設定だけを固定する。§12 LQ4-6。
4. **conformance の HTTP plug への影響は peer で非対称である** (§1.5 の 10)。**MitateDB HTTP plug は control-plane composition root そのもの (`build_control_service(control_env)`) を env 付きで呼ぶので、宣言表の読み出しが load-bearing になる** — `control_env` から廃止 env を除き、fixture の platform DB に宣言表を seed する。**r2db HTTP plug は `assemble_control_stack(…, surfaces=_SURFACES)` の明示注入を続けるので、宣言表の読み出し経路を通らない** — r2db 側で効くのは廃止 env の不在検査だけであり (import 時の `os.environ.setdefault` を撤去する)、**表の読み出しの検証は peer-local な実 PG テストが単独で担う**。v1.0 の「両 HTTP plug が本機構の影響を直接受ける」は r2db について過大主張であった。§6.1、§12 LQ4-11。
5. **data / control の非対称は r2db 固有ではない** — MitateDB も data 側 (`config.py:127-155`) は `MITATEDB_CONTROL_BASE_URL` を `control_plane_status` 依存とし、control 側 (`control_composition.py:189-190`) は無条件必須である。**D-2 (f) の統合は両 peer に等しく効く。**
6. **`surfaces` が「宣言された URL に実際に到達できる」ことを保証しない性質は残る** (L6-5)。本設計が変えるのは**宣言の保管場所が 2 プロセスの env から 1 つの表になる**ことだけであり、到達性の検証は依然として HTTP plug の declare-and-echo と配備後チェックが担う。

7. **「単一の真実」は両プロセスが同じ platform データベースを見ていることに依存し、それ自体は検証しない。** D-1 / D-2 は「両プロセスが platform DB へ接続する」(§1.5 の 1) に立つが、**どちらのプロセスも相手の DSN を知らない**。配備者が control プロセスにだけ古い platform DSN を渡せば、L6-5a が記述したドリフトが**そのままの形で再発する**。これは設計の欠陥ではなく**射程の境界**であり、検出は従来どおり配備後チェック (両 surface の `/capabilities` 突合、`DEPLOY_PHASE6_20260904.md:1184-1206` と同じ形) が担う。**D-6 の SI-14 行の置換文言はこの限定を含める。** §12 LQ4-16。

8. **一括適用が失敗した DB では developer role membership が provision role に残る** (§1.5 の 7b)。「止めずに全 DB を回す」設計 (D-4 (c)) である以上、**1 回の実行で複数 application 分が累積し得る**。SI-02 / SI-12 が守る境界は破らない (provision role は元から全 application DB へ到達できる) が、既存儀式の「membership は一時的である」という設計意図を崩す。**ops は失敗した application ごとに `REVOKE` 文を出力に含める** (D-4 (c)、§9.1)。§12 LQ4-14。

9. **各プロセスが実効値を検査できるのは自 role についてだけである。** role 設定はログイン時にのみ適用され、`SET ROLE` では他 role の実効値を取れない。したがって **control プロセスは `*svc_api` (data-plane の書き手) の実効値を検証できない** — data-plane が停止中/未再起動でも control は起動し、catalog を根拠に宣言を出す。`*svc_api` の実効値は data-plane プロセスが自分で検証する。**「二重検査で塞いだ」の射程はここまでである。** 併せて、**検査は起動時スナップショットであり、pool が後から張った新しい接続は検査されない** — 接続プーラ (PgBouncer / Cloud SQL Auth Proxy 経由の再接続) がある配備では、起動時の 1 回の一致が以後も成り立つとは限らない (**現配備にプーラがあるかは未確認**)。§12 LQ4-15。

10. **宣言を変えるときの過渡的なずれは残る。** D-1 (e) / D-2 (g) の「プール済み接続の実効値と宣言が同じ時点を指す」が成立するのは**両プロセスの再起動が完了した後**である。機構は片側再起動を止めない。timeout を**縮める**変更で control を先に再起動すると、control は短い `visibility_lag_ms` を宣言する一方 data-plane は古い長い timeout のプール接続で書き続け、C-09 (宣言 lag だけ待ってポーリングする) の消費者はまだ見えていない行を見逃す。**伸ばす**変更では data-plane を先に再起動すると同型のずれが出る。→ §9.2 が再起動順序を規定する。**本設計が閉じるのは 2 プロセス間の恒常的ドリフトであって、宣言変更時の過渡的なずれではない。** §12 LQ4-17。

---

## 4. 却下した代替案

- **案 A (現状維持、runbook の規律)** — 食い違いが無音のまま宣言を嘘にする。依頼者原則「先送りしない」に反する。
- **案 C (書き手が実効値を表に書き、control が読む)** — 案 B より軽く見えるが、**新しい書き込み面**が増え、**書き手が死んでいる間の古い値の扱い**を決める必要がある。D-1 は catalog を読むだけで書き込み面が無い。
- **`surfaces` / 窓も role 設定 (custom GUC、`ALTER ROLE`/`DATABASE SET x.y`) に載せる案** — 機構は 1 つになるが、**型無しの文字列 GUC で JSON を持つ**ことになり、`DATABASE` 単位にすると reader / control-plane 接続にも効き、`ROLE` 単位にすると role の数だけ真実が増える。timeout は **PostgreSQL 自身が意味を持つ設定**だから role 設定が「実効値そのもの」なのであって、`surfaces` は PostgreSQL にとって無意味である。宣言表なら `SELECT` 1 本で inspect でき、権限規律も既存 bookkeeping 表と同型になる。
- **env をフォールバックとして残す案** — 真実が 2 つに戻り、ドリフトが再発する。
- **廃止 env を無視して警告のみにする案** — AI エージェント運用者にとっては、警告を読み落とす可能性より **fail-fast の明示メッセージ**の方が確実である。ゲートではなくガードレールとして成立するのは、**メッセージが次に打つコマンドを示している**からである。
- **platform 台帳案 (control-plane の共通表で全 application の適用レベルを持つ)** — 台帳が application DB の外にあると、**DB の restore / clone で台帳と実体がずれる**。実体と同じ DB に置く方が原子的である (D-3 (c) の 1 トランザクション)。一括表示は各 DB を読めば足りる。
- **台帳表を `public` 以外の専用スキーマ (例 `_platform`) に置く案** — r2db の catalog 除外も RLS 監視ビューも触らずに済む可能性はあるが、**新スキーマの所有と grant を設計し直す必要があり、既存 bookkeeping 表 (`_r2db_schema_revision` / `_mdb_schema_revision` / `_mdb_field_types`) との非対称を生む**。既存の作成儀式 (§1.5 の 5) と PG16 の所有権ハードニングを前提にすると `public` が自然である。却下し、代わりに D-3 (e) で除外集合を拡張する。
- **適用状態の検出を control-plane の readiness に置く案** — **却下する。理由は invariant の禁止ではなく運用上の代償である。** SI-02 の本文 (`security/SECURITY_INVARIANTS_V1.md:111-129`) が禁じるのは「Application-facing Runtime and Developer APIs が Control Plane データや管理能力への経路を提供すること」であって、**control-plane プロセスが application DB に接続してはならないとはどこにも書いていない** (CLAUDE.md が禁じる「invariant を許可リストとして使う」形になるため、v1.0 の理由づけを改める)。却下の実質的な理由は、**control-plane プロセスに全 application DB への到達性を与えると、現在 provision 資格に閉じている単一侵害の影響範囲 (blast radius) が広がる**ことである。禁じられてはいないが、**新たな証拠 (`CONTROL_MAPPING.md` の行と conformance) を要する形の変更**であり、本フェーズの「実体と同じ DB に台帳を置く」原則に対して得るものが少ない。

---

## 5. 依頼者裁定 (U-1〜U-3、2026-09-05 に確定)

**本節の 3 件は依頼者裁定で確定した。裁定文は逐語で置き、両論は経緯として残す。**

### U-1 per-application の適用レベルを契約に載せるか、peer-local に留めるか

**【依頼者裁定 2026-09-05】**

> per-application の upgrade 適用状態は **peer-local に留める**。共通契約は無変更 (1.6.0 のまま)。可視化は両 peer の `ops upgrade-status` (provision DSN) のみ。§6.2 (契約に載せる場合) は「採用せず」として記録に残す。

**帰結**: §6 は **6.1 が本線**であり、6.2 は**採用せず (記録)** である。`conformance-tests/` の vector と port は**無変更**、`spec/data-service-api.v1.json` も**無変更**である (D-6 の 4)。適用状態の可視化は D-5 の `ops upgrade-status` のみが担う。**WP-E は着手しない** (§11)。将来再検討する場合の前提は §12 LQ4-20 に記録する。

**経緯 (両論。裁定前の記述をそのまま残す)**

- **載せる**: `ApplicationStateResult` / `ApplicationsResult.applications[]` の行に additive フィールドを足す (**契約 1.7.0**)。骨子は `platform_upgrade: {applied: [<integer>…], pending: [<integer>…]}` である (D-4 (b) の集合意味に揃える。v1.0 の `applied_level: <integer>` / `pending: <boolean>` は最大番号方式の名残なので廃する)。
  - **利点**: control 資格を持つ AI エージェント運用者が **API だけで適用漏れを見られる**。ただし **非破壊的に読める経路は `list_applications` だけ**である — 契約の application 系 endpoint は `register_application` / `list_applications` / `disable_application` / `enable_application` の 4 つであり (`spec/data-service-api.v1.json:110-113` 実測)、**`get_application` は存在しない**。`ApplicationStateResult` を返す 3 つはいずれも状態を変える操作である。
  - **代償 (1) 経路**: **control-plane プロセスが application DB の台帳を読む経路が要る**。現状 control は application DB に接続しない — **全 application DB への到達性を control プロセスに与えると単一侵害の影響範囲が広がる**か (§4 の却下理由と同じ運用上の代償。invariant が禁じているわけではない)、data-plane 側が platform DB へ状態を複製する**二次情報**が要る (単一真実という本設計の趣旨と衝突する)。**この代償は重い。**
  - **代償 (2) 公開範囲**: **`list_applications` は control 資格だけでなく audit 資格でも読める** (`spec:111`、`:125` が逐語で「An audit credential is accepted only on the read-only control_capabilities, list_applications, list_credentials, …」)。したがって載せると、**各 application の platform 適用状態が audit 資格にも公開される**。意図した公開であれば問題ないが、**決めずに載せると公開範囲が既定で広がる** (SI-07)。
  - **契約英文の骨子 (採用せず。将来再検討する場合の記録として残す)** — 1.3.0 の `target_id` / `must_rotate` と同じ「OPTIONAL、省略も適合」の形に寄せる:
    > `platform_upgrade` is an OPTIONAL per-application operational field. An implementation that does not track this state omits the key entirely, and omitting it is conformant. When present, it reports the deployment's own record of which platform upgrades have been applied to that application's storage: `applied` lists the upgrade numbers the implementation has recorded for this application, and `pending` lists the upgrade numbers the implementation ships that this application has not recorded. It is not a capability declaration — `capabilities()` remains the only place capability status is declared — and a client MUST NOT condition contract behavior on it.
- **載せない (peer-local)**: `ops upgrade-status` の出力だけ (D-5)。
  - **利点**: 機構が provision DSN の中に閉じ、**契約は無変更**である。
  - **代償**: API からは見えない。
- **監督の見立て (見立てであり決定ではない)**: **載せない方が本設計の原則 (単一真実、control-plane の到達範囲を広げない) と整合する。** 載せるなら二次情報の是非と audit 資格への公開範囲を別途決める必要がある。**→ 依頼者裁定は「載せない」であった。**

### U-2 台帳表に対する runtime / developer role の権限

**【依頼者裁定 2026-09-05】**

> 台帳表に対する runtime role の権限は **SELECT のみ付与**。data-plane は cell を開く時点で台帳の番号集合をパッケージ定数 (最新 per-app 番号集合) と比べ、未適用があれば最初のリクエストを待たずに `ops upgrade-applications` を示す明示メッセージで SERVICE_UNAVAILABLE を返す。代償 (パッケージ定数と migrations/ の同期義務) は §10 の三者一致静的検査で固定する。

**帰結**: D-3 (a) の DDL 骨子は `REVOKE ALL` の直後に **`GRANT SELECT … TO :"runtime_role"`** を置く (確定)。§3.9 の権限表の runtime role 列は **`SELECT`** である。cell を開く時点の集合検査は **D-3 (f)** と **§3.7** に置き、その応答は **§3.8 の F-12** である。パッケージ定数と `migrations/` の同期は **D-3 (d) 規則 (d) の三者一致静的検査**が無条件に担保する (§10、§9.4 の 5)。developer role については既存 bookkeeping 表と同じ射程 (所有者) を追認する。

**経緯 (両論。裁定前の記述をそのまま残す)**

**前提 (監督裁定 2026-09-05 で確定した所有と書き込み経路)**: 台帳表の**所有者は developer role** であり (§1.5 の 5 の儀式により構造的にそうなる)、**書き込み経路は provision DSN に閉じる** (§3.9)。所有者が developer role である以上、**developer 資格は自 DB の台帳を書ける** — これは application isolation の**内側に閉じる**性質であり、`_mdb_schema_revision` / `_r2db_schema_revision` と**同じ射程**である (どちらも当該 application の DB の中だけで完結し、他 application にも platform DB にも届かない)。したがって U-2 が選ぶのは **runtime role の権限**であり、developer role については既存 bookkeeping 表と同じ射程を追認する。

- **無権限** (`_mdb_schema_revision` / `_mdb_field_types` と同型): 厳格。data-plane は適用漏れを**最初のリクエスト**の `StorageConfigurationError` → `SERVICE_UNAVAILABLE` で検出する (現状どおり)。
- **`SELECT` のみ付与**: data-plane が cell を開くときに台帳の番号集合を**パッケージが知る per-app 番号の集合**と比べ、差があれば最初のリクエストを待たずに**明示メッセージ** (`ops upgrade-applications` を示す) 付きで `SERVICE_UNAVAILABLE` にできる。読み取り 1 本は迂回経路にならない (SI-12 が禁じるのは runtime が**特権を行使する経路**である)。
  - **この側の代償**: **パッケージ定数 (per-app 番号の集合) と `migrations/` の同期義務が data-plane 側にも生じる**。定数の置き場と、番号を増やし忘れたときの挙動を WP が決める必要があり、静的規則の三者一致検査 (D-3 (d)) がその同期を担保する対象に加わる (§12 LQ4-2)。
- **監督の見立て (見立てであり決定ではない)**: **`SELECT` のみ付与が「宣言で誘導する」原則に合う。** ただし `_r2db_schema_revision` の runtime `UPDATE` 付与 (既存、`0003:216`) との整合は本設計の対象外である。**→ 依頼者裁定は「`SELECT` のみ付与」であった。**

### U-3 宣言 (D-1 / D-2) の読みをスナップショットにするか live にするか

**【依頼者裁定 2026-09-05】**

> 宣言 (timeout catalog と宣言表) の読み出しは **起動時スナップショット**。ops で変えたら両プロセス再起動 (縮めるときは data-plane 先、伸ばすときは control 先)。

**帰結**: D-1 (e) / D-2 (g) は**起動時スナップショットで確定**であり、live 案を採る場合の差し替え注記は削除した。§9.2 の「宣言 → 両プロセス再起動」の 1 組と再起動順序 (**timeout を縮めるときは data-plane 先、伸ばすときは control 先**) が定常運用の手順として確定する。

**経緯 (両論。裁定前の記述をそのまま残す)**

- **起動時スナップショット**: 単純。ops で変えたら**両プロセス再起動**が要る (runbook)。プール済み接続の実効値と宣言が**同じ時点**を指す。
- **live 読み**: capability document の要求ごとに 1 `SELECT` (+ catalog 1 本)。再起動は要らないが、**書き手のプール済み接続は古い timeout のまま動く**ので宣言が先行し得る (ドリフトが逆向きに再発する)。
- **どちらを採っても残るもの**: **片側だけ再起動した窓の過渡的なずれ** (§3.11 の 10)、および **pool が後から張った接続は起動時検査を通らない**こと (§3.11 の 9)。両論の比較はこの残余を差し引いたうえで行う。
- **監督の見立て (見立てであり決定ではない)**: **スナップショット。** §3 の記述はこの見立てに沿って書いてある。**→ 依頼者裁定は「起動時スナップショット」であった** (§3 の記述がそのまま確定になる)。

**帰結 (監督、2026-09-05)**

> 契約に触らないので設計レビューは 2 本で完了。作業指示書へ進む。migration 番号は本フェーズ内で r2db 0008 (platform 単発) / 0009 (per-app 台帳 init)、MitateDB 0007 (platform 単発) / 0008 (per-app 台帳 init) を割り当てる (L6-2: 本フェーズが先に出荷する。以後の予約ではなく本フェーズの割当)。

→ migration 番号は §8 に**本フェーズの割当**として確定で置いた。

---

## 6. conformance への影響

**依頼者裁定 2026-09-05 (U-1) により、本フェーズは 6.1 が本線である。共通契約 (`spec/data-service-api.v1.json`) は 1.6.0 のまま無変更、`conformance-tests/` の vector と port も無変更である。6.2 は採用せず、記録として残す。**

### 6.1 契約無変更の場合 (本線。U-1 の裁定 = 「載せない」)

**前提**: **D-3 は application DB のスキーマを変える**ので、**両 peer の backend の bookkeeping 除外集合を更新して初めて** (D-3 (e)) vector が無変更で通る。除外を落とすと r2db の catalog 系 vector が 503 になり、MitateDB の `schema_objects` 会計が +1 ずれる。

- **`conformance-tests/` の vector は変更しない。** D-1 / D-2 は宣言の**出所**を変えるだけで、wire に現れる値も形も変えない。`adapter.audit_visibility_lag_ms()` (`conformance-tests/adapter.py:1339-1347`) はこれまでどおり宣言値を使い、C-09 は宣言 lag だけ待ってからポーリングする。C-19 の `surfaces` vector (両文書一致 / declare-and-echo / origin 比較による同居判定) も**そのまま通る**。
- **port は改訂しない。** 新しい申告メソッドを増やさない (本設計は申告を減らす方向であり、増やす要素が無い)。
- **ただし adapter の構成側は触る** (§3.11 の 4)。in-process plug は composition root を通らないので影響を受けない。**HTTP plug は影響を受けるが、その射程は peer で非対称である** (**監督裁定 2026-09-05**、レビュー 2 本の実測):
  - **MitateDB HTTP plug (α)** — `build_control_service(control_env)` を呼ぶ (`conformance_adapter_mitatedb_http.py:715`) ので **composition root そのもの**であり、**宣言表の読み出しが load-bearing になる**。`control_env` (`:707-708`) から 2 つの `*_BASE_URL` を除き、**fixture の platform DB に宣言表の行 (`surfaces` / `audit_coalescing_window_ms`) と書き手 role の 2 設定を seed する**。
  - **r2db HTTP plug (γ)** — `assemble_control_stack(…, surfaces=_SURFACES)` (`:1047`、`_SURFACES` は `:730-733`) の**明示注入のまま**とする。`surfaces` が引数で入る以上、fixture に宣言表の行を seed しても**何も検証しない飾り**にしかならない。したがって **r2db 側で行うのは import 時の `os.environ.setdefault` (`:123-124`) の撤去だけ**であり、**宣言表の読み出し経路の検証は r2db peer-local の実 PG テストが単独で担う**。
  - どちらも**実 PG を要する plug** であり、MitateDB 側は既存の platform fixture に migration を 1 本足すことで満たせる。
- **上記 adapter の改修は本フェーズの成果物である**。「conformance は契約無変更なら触らない」の**例外ではなく、adapter 構成側の必須作業**として WP の完了条件に載る (§11 WP-B)。**vector と port は変更しない。**
- **CONDITIONS.md**: 新しい条件は増えない。C-19 の限界の記述 (「宣言が実在を保証しない」) は**そのまま残る** (§3.11 の 6)。

### 6.2 契約に載せる場合 (**採用せず。記録として残す**)

**本項は U-1 の裁定により採用しない。** 将来再検討する場合の前提は §12 LQ4-20 に記録する。以下は裁定前の検討をそのまま残したものである。

- **契約 1.7.0 (additive)** となり、1.5.0 / 1.6.0 と同じ版束縛規律を採る — 契約公開は単独コミット、各 peer の flip は挙動出荷と同一コミット、`versioning.version_binding` に 1.7.0 の義務を逐条列挙、全体 vacuity guard を `xfail(strict=True)` で先置きして最後の flip と同一コミットで撤去する。
- `ApplicationStateResult` と `ApplicationsResult.applications[]` はともに `additionalProperties: false` である (§1.5 の 9) ので、**キーを足す契約変更なしには 1 バイトも足せない**。
- **新 vector**: `platform_upgrade` を宣言する実装について、**`list_applications` が返す行と、`register_application` / `enable_application` / `disable_application` が返す `ApplicationStateResult`** が**同じ値**を返すこと、および `pending` が `applied` と実装が持つ per-app 番号の集合差と整合すること (**`get_application` という endpoint は契約に無い**、§5 U-1)。**4 plug 全数で非空 precondition を持てるか**は、in-process plug が per-application DB を持たないため成立しない可能性が高く、その場合は**射程を CONDITIONS.md に開示する**。
- **この経路を採るなら、U-1 の代償 (control が application DB を読む / 二次情報) の設計を先に決める必要がある** — conformance の形はその決定に従属する。

---

## 7. Security Invariants との関係

**新しい共通 invariant は足さない** (制約 3)。本設計が導入する 3 つの新要素はいずれも既存の invariant に載る。

| 新要素 | 載る invariant | 根拠 |
|---|---|---|
| 書き手 role の timeout を role 設定に固定し、control が `pg_db_role_setting` を読む (D-1) | **SI-14** (Security-Relevant Auditability) | 監査証拠の**可視性についての宣言**が現物と一致することを機構で担保する。`CONTROL_MAPPING.md` SI-14 行の点 (12) の "nothing enforces it" が**解消される** (D-6)。invariant 本文 (`security/SECURITY_INVARIANTS_V1.md:355-378`) は「十分な証拠が残ること / 秘密を記録しないこと」を求めており、本設計はそのどちらも弱めない — 読むのは catalog であって秘密ではない |
| platform 宣言表 (D-2)、per-application 台帳表 (D-3) | **SI-12** (No Data-Service Bypass、`:319-335`) | どちらも **application-facing API から到達できない**。宣言表は application role が接続しない platform DB にあり、台帳表は application DB 内にあり、**runtime role が持つのは `SELECT` のみ** (依頼者裁定 2026-09-05、U-2。cell open 時の集合検査のため — 読み取り 1 本は特権の行使ではない) である — **developer role は表の所有者**であり (§1.5 の 5 の儀式の構造的帰結)、その射程は `_r2db_schema_revision` / `_mdb_field_types` と同一で、当該 application の DB の中に閉じる (§3.9)。SI-12 が禁じるのは「DB 資格情報 / 無制限の接続能力 / 特権的な private endpoint / 認可モデルを迂回できる鍵」を application API から得られることであり、**bookkeeping 行の読み取りはそのいずれでもない**。invariant 本文の "Operational administrators may have separately governed maintenance paths; those paths are outside the Application API and must not be derivable from Application credentials" (`:330-331`) が、provision DSN 経由の書き込み経路をそのまま覆う |
| `ops upgrade-applications` による一括適用 (D-4) | **SI-02** (Control Plane Isolation、`:111-129`) | SI-02 が禁じるのは逐語で「Application-facing Runtime and Developer APIs MUST NOT provide a route to Control Plane data or administrative capability」であり、主語は application 資格・application API である。本コマンドは **provision DSN のみで動き、API プロセスはその資格を持たない**ので、その禁止に触れない。`CONTROL_MAPPING.md` SI-02 行が既に「provisioning とは application の database と 2 つの role を作ることであり、だからこそ API プロセスはこの資格情報を決して持たない」と記述しており、**本コマンドはその既存の境界の内側に増える 1 操作**である。application DB へ `\c` できるのは provision role だけなので、境界の形は変わらない |

**「bookkeeping 表規律 (runtime role 無権限)」という語は invariant 本文には無い** (起草時に確認) — それは migration コメントに書かれた実装側の慣行 (`0003` の両 peer、`0006`) であり、**共通 invariant として昇格させる必要はない**。SI-12 の下位の実装選択として `CONTROL_MAPPING.md` に記述するのが正しい位置である (D-6)。

**覆す根拠は見つからなかった** — 3 つの新要素はいずれも、既存 invariant が守る資産 (control plane データ、provisioning 資格、application 間の分離、監査証拠) の**どれも新しい経路に晒さない**。**設計レビュー 2 本 (2026-09-05) も、この結論を覆す根拠を見つけなかった** — 宣言表への `SELECT` 付与は、置くのが公開 capability document に現れる値そのもの (base URL 2 本と窓の整数) である以上 SI-10 / SI-12 の観点で**新しい露出を作らない** (D-2 (a) の「秘密を置かない」規律がこれを規範化する)。台帳表の改竄可能性 (§3.9) についても、射程が当該 application の内側に閉じ既存 bookkeeping 表と同型である以上、SI-01 / SI-12 の下位の実装選択として `CONTROL_MAPPING.md` に書けば足りる。

**なお、Security Invariants を許可リストとして使わない** (CLAUDE.md)。§4 と §5 U-1 で control-plane プロセスの到達範囲を広げる案を退けたのは、**SI-02 がそれを禁じているからではなく、単一侵害の影響範囲が広がるという運用上の代償による**。invariant はその変更を禁じてはおらず、採るなら新たな証拠 (`CONTROL_MAPPING.md` の行と conformance) を要する形の変更になる。

**SI-15 (Fail-Closed Authorization) との関係**: 本設計の fail-fast (§3.8) は、SI-15 が求める「認可の入力が欠けたまま実行しない」の**プロセス起動時への拡張**であり、SI-15 の "Does not mean" 節 (あらゆるインフラ劣化がサービス全体を止める必要はない) と矛盾しない — 止めるのは**安全な運転に必要な設定が無いとき**だけである。

---

## 8. migration 一覧と番号規則

**規則 (L6-2、監督裁定 2026-09-04)**: **文書上の予約は番号の割当てではなく、先に出荷したフェーズが次の空き番号を取る。**

**本フェーズの割当 (2026-09-05 確定)**: **r2db `0008` (platform 単発) / `0009` (per-app 台帳 init)、MitateDB `0007` (platform 単発) / `0008` (per-app 台帳 init)。** L6-2 の規則に従い、**本フェーズが先に出荷する**ことによる割当であり、以後のフェーズのための予約ではない。他フェーズが先に出荷する事態が生じた場合は、そのときの空き番号を本フェーズが取り直す。

**現存 (実測)**

| r2db-api/migrations | MitateDB-api/migrations |
|---|---|
| `0001_bootstrap_control_plane.sql` | `0001_bootstrap_platform.sql` |
| `0002_provisioning_functions.sql` | `0002_registry_and_functions.sql` |
| `0003_provision_application.sql` (テンプレート) | `0003_provision_application.sql` (テンプレート) |
| `0004_deprovision_application.sql` (テンプレート) | `0004_deprovision_application.sql` (テンプレート) |
| `0005_credential_store.sql` | `0005_application_audit.sql` |
| `0006_control_plane_http.sql` | `0006_declared_field_types_upgrade.sql` (**per-app upgrade の初例**) |
| `0007_application_audit.sql` | — |

**本フェーズが出す migration (3 分類のうち 2 つに属する)**

| 種別 | 内容 | r2db (確定) | MitateDB (確定) |
|---|---|---|---|
| **platform 単発** | D-1 の `ALTER ROLE … SET` 4 文 + D-2 の宣言表 + 窓の seed 行 | **`0008`** | **`0007`** |
| **provisioning テンプレート改訂** | D-3 (b)(i) — 新規 application に台帳を作り、現時点の全 per-app 番号を適用済みとして記録 | `0003` の改訂 (番号を取らない) | `0003` の改訂 (番号を取らない) |
| **per-application upgrade script** | D-3 (b)(ii) — 既存 application に台帳を作り、自番号を記録 (MitateDB は `0006` を backfill) | **`0009`** | **`0008`** |

→ したがって **D-3 (b)(i) のテンプレート seed は r2db が `{9}`、MitateDB が `{6, 8}`** であり、**D-3 (f) のパッケージ定数も同じ集合**である (三者一致、D-3 (d) 規則 (d))。

**platform 単発を 1 本にまとめる理由**: D-1 と D-2 は**同じ配備手順の同じ時点**で当たり、どちらも「両プロセス再起動」を要求する。2 本に割ると、片方だけ適用した中間状態 (宣言表はあるが role 設定が無い、等) が運用上あり得てしまう。

**per-app upgrade を platform 単発と分ける理由**: 台帳は **application DB の中**にあり、platform 単発 migration は application DB に何も作らない (L6-2 の状態注記が MitateDB `0006` について記録した理由と同じ)。

### 8.1 命名規範 (本フェーズで規範化する)

静的規則 (D-3 (d)) は**命名で走査対象を決める**ので、命名を規範として置かないと規則が空振りにも誤検出にもなる (レビュー 2 の指摘)。

1. **per-application upgrade script は `NNNN_<name>_upgrade.sql` と命名する。**
2. **platform 単発 migration は `_upgrade.sql` で終わる名前を使わない。** 使うと走査対象に入り、「自番号の台帳 INSERT が無い」= 違反として即座に落ちる (本フェーズの platform 単発、r2db `0008` / MitateDB `0007` が該当し得た)。
3. **provisioning テンプレートは `0003_provision_application.sql` / `0004_deprovision_application.sql` に固定**であり、番号を取らない (既存)。

命名を外した per-app script は静的規則をすり抜けるので、**D-3 (d) の検査項目に「per-app 分類の script がこの命名に一致すること」を含める**。

**per-app upgrade script の台帳 INSERT と `0003` テンプレートの seed 文は `VALUES (n), (m)` の整数リテラルのタプルのみで書く (関数呼び出し・ドル引用符・入れ子括弧を置かない)。逸脱は静的規則で違反 / 不一致 (fail-safe 側) になる** (監督裁定 2026-09-05、WP-0 最終追補。`scan_platform_upgrade_ledger_script` の自番号照合、`template_seed_numbers` の seed 抽出は、いずれも最内の丸括弧 (`\(([^()]*)\)`) しか拾わず `$$…$$` のドル引用符には未対応であるため — `VALUES (9, coalesce(x, 42))` は `42` を拾って `9` を落とし、`$$…;…$$` を含む適合文は誤って違反に落ちる。audit-wp0-delta.log §6 (3)/(4) の実測)。

---

## 9. 運用手順の骨子

**両 peer 共通の形で書き、runbook には peer の実名 (env 名・role 名・コマンド名) で置く** (D-6 の 2)。

### 9.1 本フェーズの適用 (既存配備)

1. **platform 単発 migration を当てる** — `psql "$R2DB_CONTROL_DSN" -f r2db-api/migrations/0008_….sql` (MitateDB は `$MITATEDB_PROVISION_DSN` で `0007_….sql`)。role 設定と宣言表ができ、窓の既定行が入る。
2. **`surfaces` を宣言する** — `python -m <peer>.ops declare-surfaces --data-base-url https://data.example.invalid/v1 --control-base-url https://control.example.invalid/control/v1` (control surface を持たない配備は `--no-control`)。**この時点で ops が形式検査を行う** (D-2 (d))。
3. **廃止 env を配備設定から外す** — `*_AUDIT_STATEMENT_TIMEOUT_MS` / `*_AUDIT_IDLE_TIMEOUT_MS` / `*_DATA_BASE_URL` / `*_CONTROL_BASE_URL` の 4 本。**残っていると次の起動が F-1 / F-2 で止まる。**
4. **per-application upgrade を当てる** — `python -m <peer>.ops upgrade-applications` (まず `--dry-run` で確認する。未適用があれば `--dry-run` は 4 を返す — D-4 (e) の表)。**失敗した application があれば、出力に含まれる `REVOKE <developer_role> FROM <provision role>;` を発行して一時 membership を掃除する** (§3.11 の 8) — 失敗時は script の `REVOKE` に到達しないためである。**この手順を飛ばした application は、data-plane 再起動後に cell を開く時点で F-12 (`SERVICE_UNAVAILABLE`) になる** (D-3 (f)、依頼者裁定 U-2) — 応答が `ops upgrade-applications` を示すので、そこから復旧できる。
5. **両プロセスを再起動する** (初回適用では値が変わらないので順序は問わない。**値を変える定常運用の順序は §9.2**)。
6. **確認** — `python -m <peer>.ops show-declarations` と `python -m <peer>.ops upgrade-status`、および両 surface の `/capabilities` が同じ `surfaces` と `visibility_lag_ms` を返すこと (既存の配備後チェック手順、`DEPLOY_PHASE6_20260904.md:1184-1206` と同じ形)。**この突合は依然として必要である** — 両プロセスが同じ platform DB を指していること自体は本設計が検証しないからである (§3.11 の 7)。

### 9.2 宣言を変える (定常運用)

- **timeout を変える**: `ops set-platform-timeouts --statement-ms <N> --idle-ms <N>` → **両プロセス再起動**。**このコマンドは 2 つのサービス書き手 role (`*svc_api` / `*svc_controlplane`) に同じ 2 値を置く単一ノブである。射程はその role の全接続であり、監査書き込みに限られない — credential store 照会と control-plane registry 操作もこの timeout の下に入る** (§3.11 の 1)。**`0` と負数は拒否する** (`0` は PostgreSQL では無制限を意味する。F-10)。**role 別の指定は設けない** — 導出式が 2 role の max を取る以上、role ごとに別値を置く利点が無いからである。
- **`surfaces` を変える**: `ops declare-surfaces …` → **両プロセス再起動**。**`surfaces` 行は両プロセス共通の 1 行である** — `--no-control` は control プロセスの起動条件も同時に消す (F-6 の注記)。
- **窓を変える**: `ops declare-coalescing-window --ms <N>` → **両プロセス再起動**。
- **いずれも「宣言 → 再起動」の 1 組**である (**依頼者裁定 2026-09-05**、U-3: 読みは起動時スナップショット)。

**再起動の順序** (**監督裁定 2026-09-05、依頼者裁定 2026-09-05 が追認**。timeout を変える場合):

- **timeout を縮めるときは data-plane を先、control を後。**
- **timeout を伸ばすときは control を先、data-plane を後。**

理由: 逆順にすると、宣言された `visibility_lag_ms` が実際の書き手接続の bound より**短い**窓が生じ、C-09 の消費者 (宣言 lag だけ待ってからポーリングする) がまだ見えていない行を見逃す。過渡のずれ自体は消せない (§3.11 の 10) が、**危険な向きのずれは順序で避けられる**。

### 9.3 新しい application を provision する

改訂後の `0003` が台帳を作り、その時点の全 per-app 番号を適用済みとして記録するので、**追加手順は無い**。`ops upgrade-applications` を後から流しても何も起きない (冪等)。

### 9.4 新しい per-application upgrade script を出す (以後の規律)

1. **`NNNN_<name>_upgrade.sql` と命名する** (§8.1)。
2. script の本体を `\c` 後の 1 トランザクションに包む。**skip 経路 (`\q`) を持たない** (§1.5 の 7a)。
3. **冪等にする** (再実行で終状態が変わらない)。
4. **末尾で自番号を台帳へ `INSERT … ON CONFLICT DO NOTHING` する** (D-3 (c))。静的テストがこれを検査する — **自番号はゼロ埋めを外した整数リテラル**で書く。
5. `0003` テンプレートの seed リストに自番号を足す (**対で出す**、制約 1)。**パッケージ定数 (D-3 (f)) にも足す** (依頼者裁定 U-2 により無条件)。静的テストが三者一致を検査する (D-3 (d))。**足し忘れると CI が落ちる** — 足し忘れたまま出荷すれば cell open 時の検査が新番号を要求しないので、規律ではなく検査で閉じる。
6. 配備時に `ops upgrade-applications` を流し、`ops upgrade-status` で確認する。

---

## 10. 静的規則のプロトタイプ結果

**常設規律 5** (静的規則は逐語プロトタイプの後に確定する) に従い、D-3 (d) のスキャナを両 peer に走らせる。

- 走査対象: `r2db-api/migrations/NNNN_<name>_upgrade.sql`、`MitateDB-api/migrations/NNNN_<name>_upgrade.sql` (各 peer のテストが**自 peer の `migrations/` だけ**を走査する)
- 検査: D-3 (d) の規則 (b) — `INSERT INTO public._{r2db,mdb}_platform_upgrades` を含む 1 文の中に、自番号の整数リテラル (ゼロ埋めを外したもの) と `ON CONFLICT` の両方があること。加えて**規則 (d) の三者一致** = {`*_upgrade.sql` の番号集合} == {テンプレート `0003` の seed 集合} == {**パッケージ定数の集合** (D-3 (f))}。**この三者一致が U-2 の裁定 (2026-09-05) が名指しした「代償を固定する検査」である** — パッケージ定数と `migrations/` の同期義務はここで機械的に閉じる。本フェーズ出荷後の期待値は **r2db = `{9}`、MitateDB = `{6, 8}`** (§8)。
- 許可リスト: **番号の集合**。MitateDB = `{6}` (`0006_declared_field_types_upgrade.sql`、出荷済み、in-place で触らない)、r2db = 空
- **期待 (本フェーズ出荷後)**: **適合 ≥ 1** (r2db `0009` / MitateDB `0008`) **かつ 違反 0 かつ 免除 = {MitateDB `0006`}**。**変異先行の完了条件**: 新 script から台帳 INSERT を落とすと違反 1 件が出ること。

**現時点 (規則確定前) のプロトタイプ出力** — 本フェーズの新 per-app script がまだ無いため、**検査が成立した script は 1 つも無い**:

```
### TALLY
  適合: 0
  違反: 0
  免除(許可リストで免除): 1
  対象外(命名不一致): 12
```

**規則 (b) に合わせたスキャナ改訂と再実測は WP-0 で行った (レビュー指摘 8 / 監督裁定 2026-09-05、WP-0 差し戻し訂正: 作業指示書 v1.0 で WP-0 へ移ったのは§11 の WP-C 全体ではなく、その一部である静的規則スキャナの改訂・設置だけである -- §11 の WP-C 行と本節直前の :327 の記述は、台帳表・per-app upgrade script・`ops upgrade-applications`/`ops upgrade-status` を含む WP-C の残り部分であり、作業指示書では WP-3/WP-4 に対応する)。改訂版 (`{scratchpad}/proto_ledger_scan_v2.py`、実装は各 peer の `tests/test_platform_upgrade_ledger_scan.py::scan_platform_upgrade_ledger_script`) を両 peer の実 `migrations/` に個別に走らせた結果 (各 peer が自 peer の `migrations/` だけを走査、`{scratchpad}/proto_ledger_scan_v2.out` に保存):**

```
### r2db-api/migrations  (peer=r2db-api)
  適合: 0
  違反: 0
  免除(許可リストで免除): 0
  対象外(命名不一致): 7

### MitateDB-api/migrations  (peer=MitateDB-api)
  適合: 0
  違反: 0
  免除(許可リストで免除): 1
  対象外(命名不一致): 5
```

**完了条件 6 のとおり**: 違反 0 かつ 免除 = r2db 空 / MitateDB `{6}` (本フェーズにまだ per-application upgrade script が無いため 適合 は両 peer とも 0 — 完了条件 8 のとおり `xfail(strict=True)` で登録し、r2db = WP-3 / MitateDB = WP-4 で撤去する)。

**実 PG での確認項目** (WP で実測し、ここに結果を貼る):

1. **`setconfig` の保存形** — `ALTER ROLE … SET statement_timeout = '5000ms'` を実際に発行したときに catalog が `5000ms` を逐語で保持すること。**済 (レビュー 2 が実測)**: `pg_db_role_setting.setconfig` は書いた文字列をそのまま保持し、正規化されない。一方 `SHOW` / `current_setting` は `5s` を返す。→ D-1 (b)(ii) の両辺 ms 正規化の根拠。
2. **GUC 優先順位** — `ALTER ROLE … SET` / `ALTER DATABASE … SET` / `ALTER ROLE … IN DATABASE … SET` / `PGOPTIONS` の実優先順位 (D-1 (b) の列挙は PostgreSQL の GUC source 順位に基づく推論であり、**未実測**)。
3. **F-9 の変異先行検証** — 上書きを注入して F-9 が出ること (§12 LQ4-5)。
4. **本体失敗時に台帳行が残らないこと** — D-3 (d) がトランザクション内位置を静的に検査しない代わりの担保。
5. **台帳表を作っても catalog / RLS 監視が壊れないこと** — D-3 (e) の変異先行テスト (台帳表がある DB で `application_catalog` が 200 を返し台帳表が entities に現れないこと、`_r2db_missing_rls` が空のままであること、`schema_objects` 会計がずれないこと)。
6. **cell open 時の集合検査 (D-3 (f)) が効くこと** — 変異先行テスト: 台帳から 1 番号を削った application DB では cell を開く時点で **F-12** (`SERVICE_UNAVAILABLE`、メッセージが `ops upgrade-applications` を含む) になり、台帳が揃った DB では通常どおり通ること。**runtime role の `SELECT` だけで台帳を読めること**も併せて実測する (D-3 (a) の `GRANT SELECT`、依頼者裁定 U-2)。

---

## 11. WP 分割の素案 (作業指示書で確定する)

**本節は素案であり、着手順・粒度・完了条件は作業指示書が確定する** (依頼者裁定 2026-09-05: 「着手順は Q4 フェーズの作業指示書で決める」)。**U-1〜U-3 は 2026-09-05 に確定したので、下表の「依存」列の未確定依存は解消した。**

| WP | 内容 | 依存 |
|---|---|---|
| **WP-A** | 両 peer の platform 単発 migration (D-1 の `ALTER ROLE` + D-2 の宣言表と seed) と、ops の宣言系サブコマンド (`set-platform-timeouts` / `declare-surfaces` / `declare-coalescing-window` / `show-declarations`)。値の検証関数 (D-2 (d)) と ms 正規化ヘルパ (D-1 (b)(ii)) を src に置く。**この時点ではまだプロセスは env を読む** (出荷順の安全のため) | — |
| **WP-B** | 両 peer の composition root を宣言表 + `pg_db_role_setting` 読みへ切り替え、廃止 env の fail-fast (env mapping 対象) を入れ、セッション `SET` を撤去し、**D-1 (b) の二重検査 (存在 + 有効性 + per-database 行の不在 + 実効値の ms 一致。F-7 / F-9 / F-10 / F-11) を入れる**。**HTTP adapter の改修をこの WP の成果物に含める** — MitateDB は `control_env` から廃止 env を除き fixture に宣言表と role 設定を seed (α)、**r2db は `os.environ.setdefault` の撤去のみ (γ) で、宣言表の読み出しは peer-local 実 PG テストが担う** (§6.1)。**U-3 の裁定 (起動時スナップショット) がここに効く** — 読みは起動時 1 回であり、live 読みの経路は作らない | (U-3 確定済み) |
| **WP-C** | D-3 の台帳表 (テンプレート改訂 + per-app upgrade script) と静的規則テスト、D-4 の `ops upgrade-applications`、D-5 の `ops upgrade-status`。**完了条件に D-3 (e) を明記する** — **(i) 両 peer の backend の bookkeeping 除外集合に台帳名を加える** (r2db `postgres.py` の `:861` / `:891` / `:1780`、MitateDB `backend_postgres.py:384-391`)、**(ii) r2db の `public._r2db_missing_rls` の除外名に台帳名を加える** (テンプレート `0003` の改訂と per-app script の両方で `CREATE OR REPLACE VIEW`)。いずれも**変異先行テスト**を伴う (§10 の実 PG 確認項目 5)。**U-2 の裁定 (runtime `SELECT` + cell open 時の集合検査) がここに効く** — 台帳 DDL の `GRANT SELECT`、D-3 (f) の検査と F-12、パッケージ定数と三者一致静的検査 (D-3 (d) 規則 (d)) を完了条件に含める | (U-2 確定済み) |
| **WP-D** | 文書 (D-6) — `CONTROL_MAPPING.md` の 3 行、runbook 3 本 + `r2db-api/deploy/env/*.example` 2 本、正本 2 文書への閉止注記、本設計の §10 / §12 / §13 の確定 | WP-A〜C |
| ~~**(WP-E)**~~ | **着手しない** — U-1 の裁定は「載せない (peer-local)」であり、契約 1.7.0 も control が適用レベルを得る経路も本フェーズでは作らない (§6.2 は採用せず、記録)。将来再検討する場合の前提は §12 LQ4-20 | — |

**両 peer 同時性**: D-1 / D-2 / D-3 はいずれも「両 peer が同じ安全成果を同じ形で満たす」対象であり (制約 4)、**片 peer だけ出荷した中間状態を長く置かない**。WP 内での peer 分割は作業指示書の判断とする。

---

## 12. 台帳 (本フェーズの起票項目)

- **LQ4-1 U-1 は確定した (2026-09-05、依頼者裁定)** — **適用状態は peer-local に留め、共通契約は 1.6.0 のまま無変更**である。可視化は D-5 の `ops upgrade-status` のみ。**control が application DB の台帳を読む経路も、data-plane が platform DB へ複製する二次情報も作らない。** §5 U-1、§6。**将来再検討する場合の前提は LQ4-20。**
- **LQ4-2 U-2 は確定した (2026-09-05、依頼者裁定)** — 台帳表に対する **runtime role の権限は `SELECT` のみ**であり、data-plane は **cell を開く時点で集合検査を行い、未適用があれば `ops upgrade-applications` を示して `SERVICE_UNAVAILABLE` を返す** (D-3 (f)、§3.7 の 9〜10、§3.8 の F-12)。**developer role は所有者であり U-2 の対象ではない** (§3.9)。**代償は「パッケージが持つ per-app 番号の集合」定数と `migrations/` の同期義務**であり、**D-3 (d) 規則 (d) の三者一致静的検査が機械的に閉じる** (§10)。**定数の置き場は WP が決める** (集合の内容は §8 の割当より r2db `{9}` / MitateDB `{6, 8}`)。
- **LQ4-3 U-3 は確定した (2026-09-05、依頼者裁定)** — **読みは起動時スナップショット**であり、ops で変えたら**両プロセス再起動** (縮めるときは data-plane 先、伸ばすときは control 先) である。§5 U-3、D-1 (e)、D-2 (g)、§9.2。**live 読みの経路は作らない。**
- **LQ4-4 `ALTER ROLE … SET` の射程は監査書き込みに限られない**。`*svc_api` は credential store の接続 role、`*svc_controlplane` は control-plane registry 操作の role でもある (§1.5 の 2a、§3.11 の 1)。**「既定値では実害が無い」は見立てであって実測ではない** — credential store 照会が接続確立を含めて 5s に収まるかは配備依存である (Cloud SQL のコールドスタート等)。ops コマンド名を `set-platform-timeouts` に改め、F-1 / F-7 / F-9 のメッセージと §9.2 の runbook に射程を明記することで、**宣言でこの帰結を運用者に伝える**。**将来 timeout を大きく縮める運用があれば、その影響は監査以外の経路にも及ぶ。**
- **LQ4-5 `pg_db_role_setting` は role 設定を映すのであって接続の実効値そのものではない**。**上書きし得るのは `ALTER ROLE … IN DATABASE … SET` と接続時 `options=-c …` / `PGOPTIONS` である** (`postgresql.conf` / `ALTER DATABASE … SET` は `ALTER ROLE … SET` より優先順位が**低い**ので上書きにならない。§3.11 の 2)。**この点は設計で閉じた (D-1 (b)、監督裁定 2026-09-05)** — 書き手プロセスは catalog の 2 設定の存在と有効性、per-database 行の不在、および**書き手 pool の接続の実効値が catalog 値と ms 整数で一致すること**を起動時に検査し、どれか欠ければ fail-fast する (F-7 / F-9 / F-10 / F-11)。WP への持ち越しは無く、**WP は実装と実 PG テスト (上書きを注入して F-9 が出ることの変異先行検証) を負う**。
- **LQ4-6 r2db は provision role にも `application_audit` への `INSERT` を持つ** (`0007:186`、break-glass 用)。MitateDB は持たない (実測)。**宣言 `visibility_lag_ms` はこの帯域外経路について何も主張しない** (§3.11 の 3)。peer 非対称としても記録する。**`r2dbsvc_control` に timeout を置かない理由**: これは provisioning role であり、長時間かかる DDL (`\c` して application DB を作る / 落とす、テンプレートと per-app upgrade の適用) を流す役である。`statement_timeout` を置くと **migration 自体が途中で止まる**ので、D-1 (a) の 4 文は 2 つの**サービス**書き手 role にのみ置く。
- **LQ4-7 r2db の `surfaces` 検証ヘルパは 2 コピーある** (`main.py` / `control_main.py` の `_validate_surface_base_url`。L6-17、フェーズ7候補 L6-20 (d))。D-2 で読み出し元が表になるため**両方が同じ表の値を検証する**形になり、重複解消の動機が強まる。1 モジュールへ寄せれば同型性の対応表に載せられる (MitateDB は既に `surfaces.py` 1 本)。
- **LQ4-8 `_r2db_schema_revision` の runtime `UPDATE` 付与** (`0003:216`) は、MitateDB の同型表が無権限であることと非対称である (`0003` のコメント自身がそう書く)。**本設計の対象外**だが、U-2 で台帳表の権限を決めるときに参照される既存事実として記録する。
- **LQ4-9 宣言された `base_url` の到達性は依然として検証されない** (L6-5 の射程は残る、§3.11 の 6)。本設計が閉じるのは**2 プロセス間のドリフト**であって、宣言と実在の一致ではない。
- **LQ4-10 `0006` は静的規則の許可リストに載る** (出荷済み、in-place で触らない、制約 1)。許可リストが 1 件のまま増えないことを、以後の per-app upgrade を出す WP が確認する。
- **LQ4-11 conformance の HTTP plug への影響は peer で非対称である** (§1.5 の 10、§3.11 の 4、§6.1)。**MitateDB HTTP plug のみが宣言表を通る** (control-plane composition root そのものを env 付きで呼ぶ)。**r2db HTTP plug は `surfaces` を引数注入し続けるので宣言表を通らず、r2db 側の表読み出しの検証は peer-local な実 PG テストが単独で担う**。in-process plug はどちらの peer でも影響を受けない。したがって本機構は**共通 conformance では検証されない** (制約 5)。
- **LQ4-12 data / control の非対称は両 peer にある** (§3.11 の 5)。枠は r2db について記していたが、MitateDB の `config.py` / `control_composition.py` も同じ非対称を持つ。D-2 (f) の統合は両 peer に等しく効く。
- **LQ4-13 閉止対象**: 本フェーズの完了により、`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4、`PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 L6-5a、同 L6-20 (f) の 3 件を閉じる (D-6 の 3)。**閉止注記は日付付きで正本に置き、本文は書き換えない。**
- **LQ4-14 一括適用の失敗は provision role に developer role membership を残す** (§1.5 の 7b、§3.11 の 8、D-4 (c))。**本フェーズでは ops の出力に掃除用の `REVOKE` 文を含める形で扱う**。「次回実行の先頭で自動的に掃除する」形にするかは本設計の対象外とし、記録に留める。
- **LQ4-15 起動時検査の射程**: (i) **control プロセスは `*svc_api` の実効値を検証できない** — role 設定は login 時にのみ適用され `SET ROLE` では取れないため、その検証は data-plane プロセスが自分で行う。(ii) **検査は起動時スナップショットであり、pool が後から張った接続は検査されない**。**接続プーラ (PgBouncer / Cloud SQL Auth Proxy 経由の再接続) がある配備では、起動時の 1 回の一致が以後も成り立つとは限らない** — **現配備にプーラがあるかは未確認である** (§3.11 の 9)。
- **LQ4-16 「単一の真実」は両プロセスが同じ platform DB を見ていることに依存する** (§3.11 の 7)。どちらのプロセスも相手の DSN を知らないので、control プロセスにだけ古い platform DSN を渡す配備では **L6-5a のドリフトがそのままの形で再発する**。検出は配備後チェック (両 surface の `/capabilities` 突合) のままであり、**`CONTROL_MAPPING.md` SI-14 行の置換文言はこの限定を含める** (D-6 の 1)。
- **LQ4-17 宣言変更時の過渡的なずれは残る** (§3.11 の 10)。機構は片側再起動を止めない。**危険な向きのずれは §9.2 の再起動順序で避ける**が、ずれ自体は消えない。U-3 でスナップショットを採っても live を採っても残る性質である。
- **LQ4-18 一括適用の並行実行は保護されていない** (レビュー 2 の両論指摘)。`CREATE TABLE IF NOT EXISTS` は並行実行下で `relation … already exists` 等を返し得る (`IF NOT EXISTS` は競合を完全には吸収しない)。台帳 INSERT 同士は `ON CONFLICT DO NOTHING` で吸収される。1 DB あたり数秒の処理なので現実の衝突確率は低いが、**衝突すると片方の運用者には失敗として見える**。`pg_advisory_xact_lock` を per-app script の規律に足すかは**本設計では決めず、記録に留める**。
- **LQ4-20 U-1「載せる」案は採用しなかったが、記録として残す** (§5 U-1 の「載せる」側、§6.2)。**将来再検討する場合に先に決める必要がある前提**: (i) **適用レベルを control が得る経路** — control プロセスに全 application DB への到達性を与えるか (単一侵害の影響範囲が広がる)、data-plane が platform DB へ複製する二次情報を置くか (本設計の単一真実の趣旨と衝突する) のいずれかを決めること、(ii) **公開範囲** — `list_applications` は control 資格だけでなく **audit 資格でも読める** (`spec:111` / `:125`) ため、適用状態を audit 資格へ公開してよいかを明示的に決めること (SI-07)、(iii) **契約の形** — `ApplicationStateResult` / `ApplicationsResult.applications[]` は `additionalProperties: false` なので **additive な契約変更 (1.7.0) が必須**であり、1.5.0 / 1.6.0 と同じ版束縛規律 (単独コミットでの契約公開、flip と挙動出荷の同一コミット、vacuity guard) を採ること、(iv) **conformance の射程** — in-process plug は per-application DB を持たないため **4 plug 全数で非空 precondition を持てない可能性が高く**、その場合は射程を `CONDITIONS.md` に開示すること。**骨子は `platform_upgrade: {applied: [<integer>…], pending: [<integer>…]}`** であり (§5 U-1 の契約英文骨子)、**D-4 (b) / D-3 (f) の集合意味に揃える**。
- **LQ4-19 静的規則の許可リストの鍵は番号の集合である** (§10)。各 peer のテストが自 peer の `migrations/` だけを走査するので、peer 名の導出は要らない。**MitateDB `0006` は自番号の台帳 INSERT を持たないことと `\q` skip 経路を持つことの両方について免除される** (LQ4-10 の許可リストと同一のもの)。
- **LQ4-21 モジュール定数は同型性対応表の対象外であり、各 peer の単位テストが担保する** (WP-0 最終追補、監督裁定 2026-09-05、裁定 4)。`ms_from_pg_timeout_text` の `_UNIT_MULTIPLIER_MS` / `_PATTERN` はモジュール定数であり、`_ISOMORPHIC_TARGETS` は `ms_from_pg_timeout_text` という**関数**を pin するだけでその内部が参照するモジュール定数までは辿らない。したがって片 peer だけが `_UNIT_MULTIPLIER_MS["h"]` を `3_600_000` から `3_500_000` へドリフトさせても、同型性テストは赤にならない (audit-wp0-delta.log §6 (5) の実測)。**この経路の安全性は各 peer 自身の `tests/test_pg_timeouts.py` の単位別ケース (`h` を含む) が担保する** — 定数を対応表へ追加するのではなく、単位テストの存在が代替の担保であることを記録する。

---

## 13. 実施記録

(WP 完了後に確定する。集計行、WP ごとのコミット、受理境界、実測事項をここに置く。)

### 13.1 集計行

```
(WP 完了後に実測を貼る)
```

### 13.2 WP ごとの記録

(空欄)
