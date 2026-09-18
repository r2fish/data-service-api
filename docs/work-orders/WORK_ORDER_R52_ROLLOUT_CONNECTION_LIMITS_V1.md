# 作業指示書 — R-52 rollout 中の role `CONNECTION LIMIT`

## 0. 版数と位置づけ

- **v1.0 (2026-09-18)。** 基点 main `e3ace9e`。台帳は計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-52**。
- **正本の設計は `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` v0.3** である。本書は枠・裁定・却下案を写さず節番号で指す (`RM` §9 の 9)。値の根拠は同 §4、依頼者裁定は同 §10.1、WP の切り方は同 §11。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit とマージは監督のみ、完了ゲートは監督のみ、道具は `tools/dev/`)。
- 手順: WP-1 → WP-2 → WP-3 → WP-4 の **直列**。受け入れ監査 (テンプレ 6 `evidence-auditor`) は**全 WP の後に 1 回**。コードレビュー (テンプレ 5) は WP ごと。
- **WP-1 の実装は 2 段**とする (§2.2)。第 1 段 = 実測のみ → 監督の一括裁定 → 第 2 段 = 実装。

### 0.1 変更クラス (`tools/change_class.py` の path 規則と `RM` §9 の 8)

| WP | クラス | 導出 |
|---|---|---|
| WP-1 | **B** | 触る path に `security/`・`spec/`・`conformance-tests/`・`CLAUDE.md` が無く、`.md` 以外 (migration `.sql`・`ops.py`・tests) を含む |
| WP-2 | **A** | 触る path が `MitateDB-api/docs/cloud-run-cloud-sql.md` の 1 本だけで、`.md` かつ `spec/`・`security/`・`conformance-tests/` の外 |
| WP-3 | **D** | `security/CONTROL_MAPPING.md` は最重ルール (`security/` 配下) に当たる。枠の「C 以上」を満たす |
| WP-4 | **A** | 触る path が `.md` 2 本 (runbook と設計メモ) だけ |

- 契約版数は **1.8.0 のまま据え置く** (`spec/` に触れない。設計 §2 の (iii))。
- 機械判定は**下限**であり、本表が正本である (`tools/change_class.py` の docstring の disclosure)。**監督裁定 (2026-09-18): 本件は機械判定のとおりとする (WP-2 = A、WP-3 = D)。**

## 1. 共通の枠

### 1.1 読むべき正本

- 設計メモ `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §2 (守るべき条件)・§3 (現物の事実)・§4 (候補 (a) と追随一覧の `file:line`)・§7・§10.1 (依頼者裁定)・§11。
- `docs/work-orders/OPERATING_CONDITIONS.md` §1.4・§1.5 (特に 32・33・37・40)・§1.6・§1.9・§1.10。
- 前例としての manifest: `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` §6B (WP-F = migration 0013)。**再説明しない。粒度の手本としてのみ読む。**

### 1.2 全 WP 共通の触らないファイル

`r2db-api/` 全部、`spec/` 全部、`conformance-tests/` 全部 (**全 WP で読むだけ。触らない**。字数上限 `conformance-tests/test_control_mapping_register.py`:88 の扱いは roadmap R-50 が決める。監督裁定 2026-09-18)、`MitateDB-api/src/mitatedb_api/platform_declarations.py` の F-16 の床 (`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §10.1 の Q-3 の裁定により 1 process 分のまま。読む・呼ぶのはよい)、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS`)、`MitateDB-api/migrations/` の既存の 13 本 (変異の一時編集を除く)、`.github/`、`CLAUDE.md`。

### 1.3 順序と触るファイルの重なり (§1.2 の 16・17)

| 組 | 重なり (実ファイル名) | 扱い |
|---|---|---|
| WP-1 と WP-2 | なし (WP-1 は `MitateDB-api/migrations/`・`MitateDB-api/src/mitatedb_api/ops.py`・`MitateDB-api/tests/`、WP-2 は `MitateDB-api/docs/cloud-run-cloud-sql.md`) | 直列 (WP-2 は WP-1 の統合後に基点を取り直す) |
| WP-2 と WP-4 | `MitateDB-api/docs/cloud-run-cloud-sql.md` | **直列。WP-2 → WP-4** |
| WP-1 と WP-3・WP-4 | なし | 直列 |
| WP-3 と WP-2・WP-4 | なし (WP-3 は `security/CONTROL_MAPPING.md` のみ) | 直列。**前提条件は roadmap R-50 の統合後** |

並行して動かす WP は無い。4 本とも直列である。

### 1.4 worktree と道具の引数

| WP | worktree | `pt.py` | `mutate.py` |
|---|---|---|---|
| WP-1 | `r52-wp1` | `tools/dev/pt.py -C .claude/worktrees/r52-wp1 -- MitateDB-api/tests -q` | `tools/dev/mutate.py "$SP/r52-wp1-mutations.json" -C .claude/worktrees/r52-wp1` |
| WP-2 | `r52-wp2` | `tools/dev/pt.py -C .claude/worktrees/r52-wp2 -- MitateDB-api/tests -q` | (変異なし。§3.3 は全件 監査照合) |
| WP-3 | `r52-wp3` (着手は R-50 の統合後) | — | — |
| WP-4 | `r52-wp4` | — | — |

- `SP` は担当 subagent の scratchpad。実装担当は root suite・`conformance-tests/`・`tools/dev/gate.py`・`tools/dev/finalize.py` を回さない (§1.10 の 70)。
- 個別ファイルを速く回すときも `pt.py` を使う (例: `tools/dev/pt.py -C .claude/worktrees/r52-wp1 -- MitateDB-api/tests/test_ops_apply_platform_migration.py -q`)。道具が REFUSED (75) を返したら待つか監督に上げる (§1.10 の 66)。

### 1.5 記録の規律

**変異の定義は scratchpad を手放す前に本書の訂正註へ写す** (§1.8 の 57。前例: `docs/work-orders/WORK_ORDER_R53_OPS_HELP_TEXT_V1.md` §2 の末尾)。

## 2. WP-1 — platform migration `0014` と受け付け・追随テスト (Class B)

### 2.1 目的と範囲

`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §4 の候補 (a) を現物にする。role の `CONNECTION LIMIT` を **132 / 36 / 68 / 12** に上げる platform migration を 1 本足し、`apply-platform-migration` の受け付けと、値・件数に依存する既存テストを同じ変更セットで追随させる。設計 §4 の追随一覧のうち runbook と `security/CONTROL_MAPPING.md` は WP-2・WP-3 が扱う。

**名前 (監督確定 2026-09-18)**: `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql` (`0012_role_connection_limits.sql`・`0013_role_statement_timeouts.sql` の命名に倣う)。

**テストの置き場 (監督裁定 2026-09-18)**: 新規テストは既存の 3 ファイル (`MitateDB-api/tests/test_platform_migration_reapply.py`・`MitateDB-api/tests/test_ops_apply_platform_migration.py`・`MitateDB-api/tests/test_ops_inventory.py`) に足す。**新規テストファイルを作らない** (R-45 WP-F の F-R16 と同じ扱い)。新規ファイルを作らないので `tools/tests/test_no_shared_cluster_defaults.py` の件数 pin は変わらない見込みである (実測で変わったら止まって監督へ上げる。§1.5 の 40b)。

### 2.2 2 段の進め方 (枠。R-45 WP-F の形)

**第 1 段 — 実測のみ。`0014` を書く前に行い、疑義を 1 回の報告にまとめる。** 監督が一括で裁定するまで実装に入らない (§1.5 の 37)。

1. 使い捨てクラスタで `0012` → `0013` を適用した後の各 role の `rolconnlimit` を読む (api / controlplane / auditreader / 既存 application の `_rt`・`_dv`)。
2. `mitatedb_registry.begin_provision_application` の**現行の本体**を読む (`0013` が置き換えた版)。`0014` が置き換えるときに落としてはいけない要素 (`statement_timeout`、`CONNECTION LIMIT` の位置、`application_id` の正規表現、NAMEDATALEN の検査、password の長さの検査、二重 provision の例外、`assert_role_has_no_memberships`、戻り値、末尾の `REVOKE ALL ON FUNCTION`) を列挙する。
3. **ADMIN OPTION が無い role に対する `ALTER ROLE ... CONNECTION LIMIT` の失敗の形**を実測する (エラーの種類と、途中まで走ったトランザクションの後始末)。
4. `0014` の適用後に `0012` を単独で再適用したときの値、`0013` を単独で再適用したときの値を実測する (設計 §4 の「付随して要る事実」の 2 点が現物でそのとおりかを確かめる)。
5. 完了条件 W1-7 (`0014` の後の `0012` / `0013` 単独再適用を既存の検査が捕らえるか) を実測する。**捕らえない場合は、設計外の検査を勝手に足さず、疑義として本報告に含める。**
6. `MitateDB-api/tests/test_ops_inventory.py`:1653-1664・:1700-1710 の **2 件それぞれの `0014` 適用後の判定を実測**し、blocked を保てない方**だけ**の入力の見直し案を出す (W1-9)。
7. `MitateDB-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` を読み、本 WP が本体を変える関数・定数が 1 つも登録されていないことを確かめて報告する。登録済みの本体に触る必要が出たら止まって上げる。

**第 2 段 — 実装。** 監督の一括裁定の後にだけ着手する。

### 2.3 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql` (新規)、`MitateDB-api/src/mitatedb_api/ops.py` の `_PLATFORM_MIGRATION_FILENAMES` (:2627-2633) と `_PLATFORM_MIGRATION_VARIABLE_TABLE` (:2641-2647) **だけ**、`MitateDB-api/tests/test_ops_apply_platform_migration.py` (:329・:339・:849)、`MitateDB-api/tests/test_platform_migration_reapply.py` (:293-296・:829-835・:842・:1039)、`MitateDB-api/tests/test_ops_inventory.py` (:1653-1664・:1700-1710)、`docs/code-history/MitateDB-api/` (`tools/check_comment_provenance.py` の結果で登録の更新が要る場合だけ) | §1.2 の全 WP 共通、`MitateDB-api/tests/test_ops_help_text.py` (help の列挙は定数由来なので緑のまま。W1-8 で確かめるだけ)、`MitateDB-api/src/mitatedb_api/ops.py` の `_inventory_connection_headroom` ((8)) の**振る舞い** (読む・呼ぶのはよい)、`MitateDB-api/docs/` (runbook は WP-2)、`security/` (WP-3)、`docs/design/` (記録は監督が行う) |

### 2.4 完了条件 → 変異

変異の `file` は、特記の無い行は `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`。赤になる test id は予想であり、実装担当が実名に置き換えて報告する。「apm」は `MitateDB-api/tests/test_ops_apply_platform_migration.py`、「reapp」は `MitateDB-api/tests/test_platform_migration_reapply.py`、「inv」は `MitateDB-api/tests/test_ops_inventory.py`。

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| W1-1 | `0014` の適用後、既存の 4 つの role class の `rolconnlimit` が **132 / 36 / 68 / 12** である (api / controlplane / auditreader / 既存 application の `_rt`・`_dv`)。application は **2 本以上**で観測する (§1.5 の 32) | 5 件。(a) api の `ALTER ROLE` を外す。(b) controlplane を外す。(c) auditreader を外す。(d) 既存 application のループから `runtime_role` の `ALTER` を外す。(e) 同ループから `developer_role` の `ALTER` を外す | apm: `0014` 適用後に `rolconnlimit` を読むテスト (各 role class) |
| W1-2 | `0014` の**後に provision した** application の `_rt`・`_dv` が **68** である。role の新規作成の枝と、role が既に在る枝 (`duplicate_object` の fallback) の**両方**で観測する | 2 件。(i) 新規作成の枝の `CONNECTION LIMIT` を 36 に戻す。(ii) fallback の枝を 36 に戻す | apm: `0014` 適用後に provision した application の両 role の値のテスト |
| W1-3 | `0014` の後に provision した application の role が **`0013` の `statement_timeout` を保持する** (設計 §4 の適用順の不変量) | `0014` の関数から `statement_timeout` の設定行を落とす | apm/inv: `0014` 適用後に provision した role の `statement_timeout` を読むテスト (および (6) が confirmed のままであるテスト) |
| W1-4 | ファイル全体が 1 つの `BEGIN … COMMIT` で、**ADMIN OPTION を欠く role があると失敗して何も残らない** (途中の role だけ上がった状態が残らない。第 1 段の 3 の実測の形で観測する) | トランザクションの囲みを外す | apm: 途中で失敗する状態を作り、先に処理される role の値も上がらないことを確かめるテスト |
| W1-5 | 再適用が冪等である (1 回目と 2 回目が一致)。`_REAPPLY_PLATFORM_MIGRATION_FILENAMES` に `0014` を足し、`_drift_platform_objects_before_reapplication` に `0014` の対象のずらしを、`_snapshot()` に 4 role class の `rolconnlimit` を足す (既存の比較項目を 1 つも減らさない) | 2 件。(i) `_REAPPLY_PLATFORM_MIGRATION_FILENAMES` から `0014` を外す (`file` は reapp)。(ii) `0014` の既存 application ループを丸ごと外す | reapp: 再適用の冪等のテスト (起点ごとの列) |
| W1-6 | numbered set の順で **`0014` が最後**である (起点の列が `0014` まで連続する prefix として伸び、除外の pin が変わらない) | `0014` を起点の列から外す (`file` は reapp) | reapp: `test_reapply_starting_points_cover_every_migration_file_as_a_contiguous_prefix`・`test_excluded_starting_points_are_pinned` |
| W1-7 | `0014` の後に `0012` または `0013` を**単独で再適用した状態**を、`ops inventory` の (8) または既存の検査の**どれが捕らえる / 捕らえないか**を実測で固定する。捕らえるなら、その検査が捕らえることを 1 件のテストで観測する | 実測で捕らえる場合: その検査の判定を無効にする変異 (`file` は実測で決まる)。**捕らえない場合: 監査照合**とし、実測の逐語記録 (コマンドと出力) を残したうえで**疑義として第 1 段の報告に含める** (設計外の検査を足さない。§1.5 の 37) | 実測で決まる |
| W1-8 | `apply-platform-migration` が `0014` を受け付ける: `_PLATFORM_MIGRATION_FILENAMES` に `0014` が入り、`_PLATFORM_MIGRATION_VARIABLE_TABLE` のキー集合と一致し、`0014` は psql 変数を 1 つも参照せず (`:app_id` を含む)、help の列挙に `0014` が現れる (`MitateDB-api/tests/test_ops_help_text.py` は定数由来なので**触らずに緑**であることを確かめる) | 3 件。(i) 定数から `0014` を外す (`file` は `MitateDB-api/src/mitatedb_api/ops.py`)。(ii) 変数表から `0014` のキーを外す (同)。(iii) `0014` に `:app_id` の参照を 1 箇所足す | apm: `test_apply_platform_migration_accepted_filenames_are_pinned_and_exist_without_app_id`・`test_apply_platform_migration_variable_table_matches_each_files_own_references`、`MitateDB-api/tests/test_ops_help_text.py` の列挙のテスト |
| W1-9 | `MitateDB-api/tests/test_ops_inventory.py` の (8) の固定値 2 件 (:1653-1664 の合計 20、:1700-1710 の `concurrency=35`) について、**第 1 段で 2 件それぞれの `0014` 適用後の判定を実測し、blocked を保てない方だけ**入力を見直す (保てる方の入力は変えない) | (8) の条件 1 の比較を常に満たすようにする (`file` は `MitateDB-api/src/mitatedb_api/ops.py`) | inv: 見直した 2 件 |
| W1-10 | **rollout の検算 (R-52 の解消そのもの)**: 上限 132 / 36 / 68 / 12 のクラスタで、process 合計 **2**・`concurrency` 32 のとき (8) の条件 1 が **confirmed**、合計 **3** のとき **blocked** である | `0014` の api の値を 68 (0012 の値) に戻す | inv: 合計 2 で confirmed のテスト (合計 3 のテストは緑のまま) |
| W1-11 | `0014` が自分自身で `\set ON_ERROR_STOP on` を宣言する (既存の静的テストが `migrations/*.sql` の走査で自動的に対象に入れる) | `0014` から `\set ON_ERROR_STOP on` を消す | reapp: `test_platform_migrations_declare_on_error_stop_in_the_file` |
| W1-12 | `0014` のヘッダが `0012`:78-79 の「auditreader は触らない」を**明示的に上書きし**、覆した根拠と日付を添える (行を消さない。§1.8 の 56) | **監査照合**: ヘッダの当該記述と、`0012`:78-79 を指す参照を `file:line` で逐語記録に残す | — |
| W1-13 | 件数・タプルの静的 pin を**実測で**更新する (`MitateDB-api/tests/test_platform_migration_reapply.py`:1039 の `len(_PLATFORM_MIGRATION_FILENAMES) == 5`、apm:329・:339・:849)。件数を実測値に合わせるだけで済ませず、`0014` が走査対象に入ったことを確かめる (§1.5 の 40b) | **監査照合**: 更新した pin の `file:line` と更新前後の値、`0014` が走査対象に入ったことの実測を逐語記録に残す | — |
| W1-14 | 追加・変更した migration・コード・テストに実値が無い (§1.9) | **監査照合**: `python3 tools/public_value_scan.py <触ったファイル>` の集計行を逐語記録に残す | — |
| W1-15 | `0014` と `apply-platform-migration` を**本番に対して実行していない**。試験の接続先は使い捨ての PostgreSQL だけである | **監査照合**: 接続先の出所 (テスト基盤の管理 DSN の環境変数名) の `file:line` を逐語記録に残す。**実 DSN・実ホスト名を書かない** | — |
| W1-16 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す | — |

### 2.5 実行するコマンド

```bash
tools/dev/pt.py -C .claude/worktrees/r52-wp1 -- MitateDB-api/tests/test_ops_apply_platform_migration.py -q
tools/dev/pt.py -C .claude/worktrees/r52-wp1 -- MitateDB-api/tests/test_platform_migration_reapply.py -q
tools/dev/pt.py -C .claude/worktrees/r52-wp1 -- MitateDB-api/tests/test_ops_inventory.py -q
tools/dev/pt.py -C .claude/worktrees/r52-wp1 -- MitateDB-api/tests -q
tools/dev/mutate.py "$SP/r52-wp1-mutations.json" -C .claude/worktrees/r52-wp1
python3 tools/public_value_scan.py MitateDB-api/migrations/0014_role_connection_limits_rollout.sql MitateDB-api/src/mitatedb_api/ops.py MitateDB-api/tests/test_ops_apply_platform_migration.py MitateDB-api/tests/test_platform_migration_reapply.py MitateDB-api/tests/test_ops_inventory.py
python3 tools/check_comment_provenance.py --base "e3ace9e" MitateDB-api/src/mitatedb_api/ops.py
```

- `MitateDB-api/tests` 全体を回すのは、migration を 1 本足すと tests / conformance の bootstrap helper の列挙に波及するためである (§1.5 の 40a に準じる)。回すのは第 2 段の反映後と仕上げの 1 回。
- 変異定義は 1 変異 1 件とし、変異ごとに赤になる test id を名指しする。migration ファイルを対象にするときも同じ形で、変異は一時編集として `mutate.py` が戻す。

### 2.6 記録 (統合時に監督が埋める)

- 第 1 段の実測と一括裁定、実装・レビューの回数と差し戻し、`pt.py` の集計行、`mutate.py` の変異表 (全件 `expect=red got=red` と復元の照合)、監査照合 W1-12〜W1-16 の逐語記録、統合先の main SHA。**変異の定義は scratchpad を手放す前にこの節へ写す** (§1.5)。

## 3. WP-2 — runbook (Class A)

### 3.1 目的と範囲

`MitateDB-api/docs/cloud-run-cloud-sql.md` を `0014` の現物に合わせる。**版数の記入は行わない** (§10.6 / §10.7 / §10.10 の版数と §10.8 の再受理は WP-4)。

### 3.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/docs/cloud-run-cloud-sql.md` の §10.6・§10.7・§10.10・§10.10.1 の該当行**だけ** | §1.2 の全 WP 共通、同 runbook の §10.8 (WP-4)・版数の行 (:2277・:2326・:2469、WP-4)、`MitateDB-api/` のコード・テスト・migration、`security/`、`docs/design/` |

### 3.3 完了条件 → 変異

| # | 完了条件 | 変異 (操作) |
|---|---|---|
| W2-1 | §10.6 に `0014` の行を足す (値 132 / 36 / 68 / 12 と、`0012` を後から単独で再適用すると値が下がる性質)。既存の `0012` 行 (:2310) と `0013` 行 (:2311「additive; it drops and revokes nothing」) の記述を、`0014` の後に単独で再適用したときの帰結 (設計 §4 の「付随して要る事実」) に合わせて直す | **監査照合**: 足した行・直した行を `file:line` で逐語記録に残す |
| W2-2 | §10.7 に `0014` の行と **`lock_timeout` の値**を足す (:2356-2358 の `0012` / `0013` の行と同じ形)。**値は `0013` の行 (:2358) と同じ `3s` とする** — `0014` が触る対象は `ALTER ROLE` と `begin_provision_application` の置換で `0013` と同種である (監督裁定 2026-09-18) | **監査照合**: 足した行と値、出所の `file:line` (:2358) を逐語記録に残す |
| W2-3 | §10.10 の前提条件の検算例 (:2495-2532) を `0014` 適用後の上限と process 合計 2 で更新する。**需要の数え方 (worst-case) は変えない** (設計 §2 の (i)) | **監査照合**: 更新前後の算式を逐語記録に残す |
| W2-4 | §10.10.1 の (8) の行 (:2701) の値を `0014` の上限に合わせる | **監査照合**: 更新前後の行を逐語記録に残す |
| W2-5 | §10.10.1 の step 7 (:2866-2872) の適用順を `0012` → `0013` → **`0014`** にする (適用順の不変量。設計 §4) | **監査照合**: 更新前後の手順を逐語記録に残す |
| W2-6 | 覆した記述は消さず、覆した根拠と日付を該当行に残す (§1.8 の 56) | **監査照合**: 残した根拠と日付を `file:line` で逐語記録に残す |
| W2-7 | 実 credential・実ホスト名・実ドメイン・実 DSN を 1 件も足さない。文書参照が壊れていない | **監査照合**: `python3 tools/public_value_scan.py MitateDB-api/docs/cloud-run-cloud-sql.md` と `python3 tools/check_doc_refs.py` の集計行を逐語記録に残す |
| W2-8 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す |

- **本 WP は監査照合だけで構成される。** runbook の文面を機械的に固定するテストが基点に無いためである (実測: `.py` からの `cloud-run-cloud-sql.md` の参照はコメント・docstring のみ)。**逐語記録の置き場は下の §3.4「記録」**とする (監督裁定 2026-09-18。§1.5 の 40)。
- **runbook の机上通し** (想定の本番の状態を 10 項目に通すレビュー) は本 WP では行わない。**WP-4 の独立の設計レビューが担う** (§5 の 1)。

### 3.4 記録 (統合時に監督が埋める)

- 実装・レビューの回数と差し戻し、`pt.py` の集計行、監査照合 W2-1〜W2-8 の逐語記録 (`file:line`、更新前後の行、`public_value_scan.py` と `check_doc_refs.py` の集計行)、統合先の main SHA。

## 4. WP-3 — `security/CONTROL_MAPPING.md` (Class D。枠のみ)

- **前提条件: roadmap R-50 の統合後に着手する** (監督裁定 2026-09-18。逐語は `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §11 の 3)。R-50 が閉じるまで着手しない。
- 範囲 (設計 §4 の追随一覧): `security/CONTROL_MAPPING.md` の :5 (版数と適用 migration の記述)、:548 (「r2db-api と同じ算式」の主張)、:641 (受け付けファイルの列挙)、:647 (`0012` alone afterward … の順序)、:650 (numbered set と再適用が value-neutral でない旨)、:659 (§10.8 の受理と版数の対応)。
- 字数の上限 15,200 字は `conformance-tests/test_control_mapping_register.py`:88 が検査する。**同ファイルは読むだけで触らない** (§1.2。上限そのものの扱いは roadmap R-50 が決める。監督裁定 2026-09-18)。
- **本書は枠だけを置く。完了条件 → 変異の manifest と「記録」の小節は、R-50 の統合後に本書の訂正註として追記する** (§1.8 の 57。本文は書き換えない)。

## 5. WP-4 — runbook §10.8 の再受理 (Class A。最終)

- 前提: 版が上がると受理は無効に戻る (「版が一致しない記録は記録が無いのと同じ」、runbook:2384-2385)。現行の受理は §10.6 版 2 / §10.7 版 2 / §10.10 版 5 で、記録先は `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12.6 (同:689)。
- 順序 (設計 §11 の 4):
  1. **独立の設計レビュー** (テンプレ 4、WP-1〜WP-2 の統合後の runbook に対して 1 回)。**runbook の机上通し** (想定の本番の状態を §10.10.1 の 10 項目に通す) はこのレビューが担う (監督裁定 2026-09-18)。
  2. **版の記入**: `MitateDB-api/docs/cloud-run-cloud-sql.md` の版数の行 (:2277・:2326・:2469) と §10.8 の受理記録 (:2380-2392)。
  3. **逐語記録**: `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12 の**次の番号の節** (§12.6 の次) に置く。
- 完了条件 → 変異

| # | 完了条件 | 変異 (操作) |
|---|---|---|
| W4-1 | 独立の設計レビューを 1 回行い、指摘と裁定を逐語で残す (§1.7 の 50) | **監査照合**: レビューの実施記録と裁定を逐語記録に残す |
| W4-2 | §10.6・§10.7・§10.10 の版数の行が新しい版になり、§10.8 の受理記録がその版を指す | **監査照合**: 更新前後の版数を `file:line` で逐語記録に残す |
| W4-3 | 受理の逐語記録が設計メモ §12 の次の番号の節にあり、版数が §10.8 と一致する | **監査照合**: 節番号と版数の対応を逐語記録に残す |
| W4-4 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す |

### 5.1 記録 (統合時に監督が埋める)

- 設計レビューの実施記録と裁定、監査照合 W4-1〜W4-4 の逐語記録 (版数の `file:line` と更新前後、受理の節番号)、統合先の main SHA。

## 6. 監督の確定待ちの項目 (実装に入る前に決まる)

1. `0014` のファイル名 (§2.1 の提案の可否)。
2. 第 1 段の実測 (§2.2 の 1〜7) への**一括裁定**。W1-7 が「捕らえない」だった場合の扱いを含む。

(2026-09-18 の監督裁定により、新規テストの置き場・`lock_timeout` の値・WP-3 と WP-4 の worktree 名・`conformance-tests/` の扱い・変更クラスは確定済みで、本節から外した。)

## 7. 訂正註 1 (2026-09-18) — WP-1 第 1 段の実測への監督の一括裁定

第 1 段の実測 (追跡ファイルの変更 0。`pt.py`: `4 passed`、追加 `1 passed, 3 deselected`) の要点と裁定。

- **実測 1〜4 (疑義なし)**: `0012`+`0013` の後は 68 / 20 / 5 / 36。下書きの `0014` の後は 132 / 36 / 12 / 68 (適用後に provision した application を含む)。ADMIN OPTION を欠くと `InsufficientPrivilege` (42501) でトランザクション全体が戻り、先行の `ALTER` も残らない。`0014` の後の `0012` 単独再適用は api・controlplane・既存 application を下げ戻し、auditreader は変えない。`0013` 単独再適用は既存 role を変えず、以後に provision した application だけが 36 になる。
- **S-1 (実測 5、W1-7)**: `ops inventory` の (8) は、process 合計 2 で読めば `0012` 単独・`0013` 単独 (その後に provision した application が在る場合) の両方を blocked として捕らえる。**`0013` 単独再適用の後に application を 1 件も provision していない間は、どの既存の検査も捕らえない。** 裁定: 設計外の検査は足さない。W1-7 のテストは「合計 2・`0013` 単独再適用の後に provision した application が在る」組と「`0012` 単独再適用」の組で (8) が blocked になることを固定する。捕らえない組は、捕らえないことを 1 件のテストで固定する (現物の限界の記録。直ったら赤になる)。runbook (WP-2) にこの限界と「再適用は必ず `0012` → `0013` → `0014` の列で行う」を書く。構造的な直し (後続の migration が上書きする対象を持つファイルの単独再適用を `apply-platform-migration` が機械的に扱う) は台帳に別件として起票する (`0012` → `0013` の間にも同じ形が在るため、本 WP の範囲にしない)。
- **S-2 (実測 6、W1-9)**: `0014` の値では固定値 2 件の**両方**が blocked を保てない (起草時の見込み「片方だけ」は外れた)。裁定: 両方の入力を見直す。値は実測の案 (data 35・concurrency 2 で api の需要 140 > 132 / concurrency 67・data 1 で 134 > 132) を採る。W1-9 の「保てない方だけ」は「2 件とも」と読み替える。
- **実測 7 (疑義なし)**: `_ISOMORPHIC_TARGETS` に本 WP が本体を変える関数・定数は 0 件。

## 8. 訂正註 2 (2026-09-18) — WP-1 の記録 (§2.6 の中身)

- **経過**: 第 1 段 (実測) → 訂正註 1 の一括裁定 → 第 2 段 (実装) → コードレビュー 1 回目 (中 2・低 3) → 差し戻し 1 (新しい起動) → コードレビュー 2 回目 (差し戻し不要)。
- **差し戻し 1 の監督裁定 (α)**: `0014` の section 2 のループに `0013_role_statement_timeouts.sql`:91-96 と同じ `IF EXISTS` の防御を足す。理由: `0004_deprovision_application.sql` は 1 トランザクションにできず、途中で落ちると registry 行に role 名だけが残る。防御が無いと、その cluster で `0014` が `undefined_object` で失敗して全部巻き戻り、rollout 中に上限を上げられない。**完了条件 W1-17 として足す** (実装担当は新しい条件を W1-14 に挿入して旧 14〜16 を繰り下げて報告したが、既存の番号は動かさない。変異の id `W1-14-remove-if-exists-guard` は W1-17 の変異と読む)。観測は `test_apply_platform_migration_0014_survives_a_registry_role_dropped_before_it_runs`。
- **`pt.py`** (MitateDB-api/tests): `1357 passed, 2 subtests passed` (基点 1345 + 新規 12)。**`mutate.py`**: 22 件とも `expect=red got=red`、復元は sha256 2 回で照合済み。第 2 段の 1 回目は W1-11 と W1-5(ii) が green で、原因を直して再実行した。
- **完了ゲート** (worktree、`gate.py -C`、基点 main `300853b`): `3704 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。
- **対応表の註**: W1-5(ii) は W1-1d/e と同一の編集・同一の観測テストであり、再適用の冪等の観測は W1-5i が担う (赤になるのは `_snapshot()` に足した auditreader の `rolconnlimit` があるため)。W1-8 の「help の列挙に `0014` が現れる」は、`MitateDB-api/tests/test_ops_apply_platform_migration.py` の実定数のタプルの pin × help が定数由来であること (`MitateDB-api/tests/test_ops_help_text.py`) の合成で満たす (後者は実定数に合成名を足して比べるので W1-8i では緑のまま)。
- **監査照合**: W1-12 = `0014` のヘッダが `0012_role_connection_limits.sql`:78-79 を明示的に参照し、根拠と日付を添えて上書きしている (レビューが現物で確認)。W1-13 = 件数とタプルの pin を実測で更新し、`0014` が `migrations/*.sql` の走査に入ったことは W1-11 の変異が示す。`tools/check_comment_provenance.py --base e3ace9e MitateDB-api/src/mitatedb_api/ops.py` は worktree では `FAIL (§4.1 (1)) … ops.py:2633 code changed` (コードを変える差分では必ず出る) で、(2)〜(5) は何も出ない = コメント・docstring は不変、`docs/code-history/` の更新は不要 (実装担当の報告の「OK: 110 blocks」は main を測った値で、レビューが訂正した)。`tools/public_value_scan.py`: `total_flagged=0`。
- **共有 fixture**: `0014` は temp dir にコピーするだけで適用しない (適用するテストが自分で適用する)。`0013` までの cluster は `0014` の適用前の実在する運用状態であり、`0014` は運用者が手で適用するため (レビューも妥当と判断)。
- **検知の限界 (S-1) の置き場**: `0014` のヘッダには書かず、WP-2 の runbook が持つ。構造的な直しは roadmap R-57。
- **変異の定義 (scratchpad を手放す前の写し。id は `r52-wp1-mutations.json` のもの)**: W1-1a-api / W1-1b-controlplane / W1-1c-auditreader (各 `ALTER ROLE` を外す)、W1-1d-existing-runtime-loop / W1-1e-existing-developer-loop (既存 application のループの片方を外す)、W1-2i-new-creation-branch / W1-2ii-duplicate-object-fallback (関数の 68 を 36 に戻す)、W1-3-drop-statement-timeout、W1-4-remove-transaction-wrapper、W1-5i-remove-0014-from-reapply-filenames、W1-5ii-remove-0014-existing-application-loop、W1-6-exclude-0014-from-starting-points、W1-7a / W1-7b (`ops.py` の (8) の条件 1 を無効にする → `0012` 単独・`0013` 単独を捕らえるテストが赤)、W1-8i / W1-8ii / W1-8iii (定数・変数表から外す、`:app_id` の参照を混ぜる)、W1-9a / W1-9b ((8) の条件 1 を無効にする → 固定値 2 件が赤)、W1-10-api-value-reverted-to-0012、W1-11-remove-on-error-stop、W1-14-remove-if-exists-guard (= W1-17)。

## 9. 訂正註 3 (2026-09-18) — WP-2 の記録 (§3.4 の中身) と WP-4 の前倒し

- **WP-2 の統合**: main `da75ee2` (作業 `3c1194c`)。runbook 1 本、217 行追加・30 行削除。Class A。`pt.py` は回していない (コード・テストの変更 0)。
- **範囲の追加 (監督裁定)**: §3.2 の「触るファイル」は §10.6・§10.7・§10.10・§10.10.1 の該当行だけだったが、同じ runbook の自己矛盾を残さないために次を範囲に足した。**W2-9** = §10.7 の値の渡し方の列挙、§10.10 の numbered set の列挙と理由・ADMIN OPTION の前提と対象 role の表・「single transaction」の列挙、§10.10.1 の item (6)・(8) の `-1` の行。**W2-10** = §3 の適用例と role floor の表の註、§10 冒頭の platform migration の列挙、§10.5 の `-1` の註、§10.10.3、`0014` の ADMIN OPTION の実測記録 (出所は §7 訂正註 1 の実測 1〜4 と `test_apply_platform_migration_0014_is_transactional_and_rolls_back_on_permission_failure`)。**W2-11** = 独立レビューの差し戻し 1 (中 4・低 4): step 7 の段落の矛盾、`0014` は値を SET する (高い上限は下がる) 旨、item (8) の初回 blocked を step 7 が直すことの明示、deprovision の残骸 (`0012` に `IF EXISTS` の防御が無い) と出口 (§7 の deprovision の再実行。`0004` は `DROP … IF EXISTS` と無条件の `finish_deprovision_application`)、`max_connections` の出口、合計 3 の出口、テストの引き方、§3 の表の見出し。いずれも監査照合。
- **監査照合の逐語記録**: 更新前後の行の正本は作業コミット `3c1194c` の差分である (`git show 3c1194c -- MitateDB-api/docs/cloud-run-cloud-sql.md`)。W2-7: `tools/public_value_scan.py` = `files_scanned=1 total_flagged=0`、`tools/check_doc_refs.py` = `0 dangling references`・`empty markdown files: 0` (起草担当とレビュー担当がそれぞれ実行)。W2-6: 覆した行は 1 行も消さず `(2026-09-18: …)` の註を付けた (レビューが現物で確認)。作業名・R 番号・経緯の叙述は 0 件。
- **独立レビュー (机上通し)**: 2 回。想定の本番の状態 10 通り — (a) `0014` 未適用の初回の読みは (8) blocked、step 7 が直す / (b) `0013` も未適用 / (c) `0012` 単独再適用 → (8) blocked で検知、補償は `0014` の再適用 / (d) `0013` 単独再適用 → provision の後は (8) blocked、provision するまではどの検査も回らない旨を明記 / (e) ADMIN OPTION の欠如 / (f) deprovision の中断の残骸 → 出口まで通る / (g) Control 未配備 / (h) `max_connections` の不足 / (i) 合計 3 / (j) rollback (`0014` は戻さない)。2 回目で行き止まりと堂々巡りは 0 件、受理。主張と現物 (0014 の SQL、`ops.py`) の照合と検算の再計算 (128 / 32 / 8 / 64、合計 234、合計 3 で 192 > 132) も一致。
- **step 7 の形 (事実)**: `0012`・`0013` が適用済みの deployment でも 3 本とも無条件に再適用させる。numbered set の規律どおりとして変えない (道具の側の直しは roadmap R-57)。
- **WP-4 の前倒し (監督裁定)**: §1.3 は WP-2 → WP-3 → WP-4 の直列としたが、runbook の本文が変わった時点で §10.8 の受理記録は版の据え置きのまま無効と同じ状態になる。この状態を R-50 の統合 (WP-3 の前提) まで放置しないために、WP-4 のうち runbook (§10.6 版 2→3・§10.7 版 2→3・§10.10 版 5→6 と §10.8 の記入) と設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12 の記録を、上の独立レビューの結果をもって先に行う。`security/CONTROL_MAPPING.md` の中の版の記述の追随は WP-3 に入れる。

## 10. 訂正註 4 — WP-3 の manifest と記録の材料

§4 は「完了条件 → 変異の manifest と『記録』の小節は、R-50 の統合後に本書の訂正註として追記する」と定めた。R-50 は main `d2e7333` (版 2.8) で統合されたので、ここに置く。本文 (§4) は書き換えない (§1.8 の 57)。

### 10.1 WP-3 の manifest (Class D。基点 main `d2e7333`、worktree `r52-wp3`)

触るファイルは 6 本 (差し戻し 1 の後の実測。§10.5): `security/CONTROL_MAPPING.md`、`security/CONTROL_MAPPING_HISTORY.md` (書き換えた主張の旧文の移送先。`CONTROL_MAPPING.md` 冒頭の Update convention が定める)、本書、`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` (§4 の行番号の訂正註と改版)、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` (§4 の訂正註 1 本)、`MitateDB-api/tests/test_ops_apply_platform_migration.py` (module docstring と節見出しコメントの 2 箇所のみ。**テストの本体は 1 行も変えない**)。いずれも §1.2 の触らないファイルには当たらない。実行される振る舞いを 1 つも変えないので **変異は 0 件、全 12 件が 監査照合**である (§1.5 の 40 の 2 文目。WP-2 と同じ扱い、§1.4 の表)。照合対象の逐語記録は §10.2〜§10.5 に置く。

| # | 完了条件 | 変異 / 監査照合 |
|---|---|---|
| W3-1 | `0014` の**値と算式** (132 / 36 / 68 / 12 = 2 × 1 process 分の pool + 4、margin は 1 つ) が SI-08 / MitateDB-api の**既定ブロック**に在り、r2db-api との差 (F-16 の床は両 peer とも 1 process 分のまま、上限の算式だけが違う) が正確に書かれている | 監査照合 (§10.2 の :580-582) |
| W3-2 | `0014` の**性質** (1 トランザクションで失敗時に何も残さない、存在しない role を飛ばす、`0013` の `statement_timeout` を保持、ADMIN OPTION、`0012` → `0013` → `0014` の適用順、ヘッダが `0012`:78-79 を上書きする) が SI-09 / MitateDB-api の既定ブロックに在る | 監査照合 (§10.2 の :697-699) |
| W3-3 | `apply-platform-migration` の**受け付けファイルの列挙**と runbook の **numbered set** がともに `0005/0007/0011/0012/0013/0014` になっている | 監査照合 (§10.2 の :691・:702) |
| W3-4 | `ops inventory` の **(8)** について、合計 2 で confirmed・合計 3 で blocked、`0012` 単独再適用は捕らえる、`0013` 単独再適用は後に application を provision すれば捕らえる、provision しない間は**捕らえない** (S-1) の 4 点が SI-08 / MitateDB-api / `ops inventory` に在り、Evidence が実在するテスト名を引く | 監査照合 (§10.2 の :611-612・:626) |
| W3-5 | **条件 2 の scope limit** (上限を上げても `max_connections` の余力は増えない、Z-27 の合計は物理的 worst case でない、`max_connections` が足りない場合の方針は未決 = 依頼者裁定 Q-4) を 1 行で開示している | 監査照合 (§10.2 の :630) |
| W3-6 | runbook §10.6 / §10.7 / §10.10 の版が **3 / 3 / 6**、記録先が設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12.7 に追随し、Status に **`0014` も本番未適用**である事実が書かれている | 監査照合 (§10.2 の :710・:714、現物は `MitateDB-api/docs/cloud-run-cloud-sql.md`:2313・2363・2507・2427-2429) |
| W3-7 | 書き換えた 7 行の**旧文が逐語**で `security/CONTROL_MAPPING_HISTORY.md` の該当 SI 節に在る (SI-08 に 1 件、SI-09 に 6 件)。行は消していない | 監査照合 (§10.3) |
| W3-8 | Evidence のテスト名が**実在**し、完全形 `<path>::<name>` で始まり、裸の `::name` は同じ小ブロックの中の直前の完全形と同じファイルに在る (R-50 WP-3 の規律) | 監査照合 (§10.4 の grep の記録) |
| W3-9 | **字数**が上限 (1 ブロック 15,200 字・1 行 1,400 字) に収まり、最長ブロックが変わったので preamble の再実測の文を実測値で置き換えた | 監査照合 (§10.4 の実測) |
| W3-10 | 道具 4 本 (`tools/check_control_mapping_split.py --expect`・登録テスト・`tools/check_doc_refs.py`・`tools/public_value_scan.py`) が緑で、`missing` / `added` の各対が「書き換えた主張」「足した主張」に 1 対 1 で対応する | 監査照合 (§10.4 の集計行と §10.2 の対応表) |
| W3-11 | `MitateDB-api/tests/test_ops_apply_platform_migration.py` の module docstring と節見出しコメントが現物と一致する (受け付け 6 本、drift-then-restore を持つのは 5 本、当該節が持つのは 4 本) | 監査照合 (§10.5 の 6) |
| W3-12 | **W3-1〜W3-11 に対応の無い行が、触った 6 本の差分に 1 行も無い** | 監査照合 (§10.2・§10.3・§10.5 が差分の全行を尽くす) |

### 10.2 触った行 — `security/CONTROL_MAPPING.md` (旧 = main `d2e7333`、新 = 作業後)

**書き換えた主張 7 件 (= 集計行の `missing=7` の内訳。旧文は §10.3 へ逐語で移送)**

| # | 主張 (置き場) | 旧 file:line | 新 file:line | 字数 旧 → 新 | 何が偽になったか |
|---|---|---|---|---|---|
| R1 | 0012 と F-16 の peer 対称 (SI-08 / MitateDB-api / 既定 / Control) | :578 | :580 | 1,011 → 1,190 | 「same formula」。`0014` で MitateDB 側だけ上限が並走 2 の値になった |
| R2 | `apply-platform-migration` の受け付け列挙 (SI-09 / MitateDB-api / Control) | :684 | :691 | 500 → 505 | `0005/0007/0011/0012/0013` 止まり |
| R3 | `0013` の適用順と stray `0012` の補償 (同上) | :690 | :697 | 449 → 777 | 「corrected by the next `apply-platform-migration 0013`」。`0014` の後は `0013` 単独では戻らない |
| R4 | numbered set と value-neutral でない再適用 (同上) | :693 | :702 | 1,114 → 1,210 | numbered set・関数を置き換えるファイルの列・ADMIN OPTION の列がいずれも `0013` 止まり |
| R5 | 2 つの migration テストファイルと件数 (SI-09 / MitateDB-api / Evidence) | :700 | :709 | 725 → 815 | 「44 tests」「each of the 5 accepted files」。実測は 51 件・受け付け 6 本 (うち drift-then-restore は 5 本) |
| R6 | runbook の受理と版 (同上) | :701 | :710 | 564 → 543 | 版 2 / 2 / 5 と「記録は §10.8 を埋める変更セットで書く」(WP-4 で書き終えた) |
| R7 | section 10 の版と本番未適用 (SI-09 / MitateDB-api / Status) | :705 | :714 | 441 → 599 | 版 2 / 2 / 5。`0014` の本番未適用にも合わせた |

**足した主張 8 件 (= 集計行の `added=15` − `missing=7`)**

| # | 主張 | 新 file:line (字数) | 対応する完了条件 |
|---|---|---|---|
| A1 | `0014` の値と算式、および peer 間の差が未検証の非対称である旨 (SI-08 / MitateDB-api / 既定 / Control) | :581 (734) | W3-1 |
| A2 | margin は 1 つ・F-16 の床は据え置き・下げ戻しは (8) だけが読む (同上) | :582 (757) | W3-1 |
| A3 | rollout の検算 (合計 2 = confirmed、合計 3 = blocked) (SI-08 / MitateDB-api / `ops inventory` / Control) | :611 (431) | W3-4 |
| A4 | 単独再適用の 3 状態と検知の限界 S-1 (同上) | :612 (991) | W3-4 |
| A5 | 上の 4 件のテスト名 (同 / Evidence) | :626 (518) | W3-4・W3-8 |
| A6 | 条件 2 の scope limit (同 / Status。`- —` を置換 = `empty_axis_removed=1`) | :630 (455) | W3-5 |
| A7 | `0014` の適用範囲と 1 トランザクション (SI-09 / MitateDB-api / Control) | :698 (540) | W3-2 |
| A8 | 適用順・ヘッダの上書き・ADMIN OPTION とそのテスト名 (同上) | :699 (833) | W3-2・W3-8 |

**主張以外に触った行 (preamble。登録テストのブロック集合には入らない)**

- :5 版数行を 2.8 → **2.9** に置き換え (963 字)。形は版 2.8 の行に倣い、R-52 と設計メモ `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` を引く。
- :47-53 の「Blocks per subsection」段落末尾の**再実測の文**を置き換え (§10.4 の実測による。最長ブロックが SI-14 / r2db-api / 既定 から SI-09 / MitateDB-api / 既定 に変わったため)。旧の 12,624 字という値は文中に残し、消していない。

### 10.3 触った行 — `security/CONTROL_MAPPING_HISTORY.md` (追記のみ、42 行)

R1 の旧文を `## SI-08` 節の末尾に 1 件 (:190)、R2〜R7 の旧文を `## SI-09` 節の末尾に 6 件 (:225・:231・:237・:243・:249・:255) 追記した。1 件の形は版 2.8 (R-50 WP-3) の追記に倣い、`*MitateDB-api <軸> claim, <何の主張か>, superseded 2026-09-19 (Version 2.9, R-52 WP-3 -- <なぜ偽になったか>), verbatim:*` の見出し 1 行 + 旧文 1 行。旧文は 1 文字も編集していない (抽出は作業前の同ファイルから行単位で取り、字数 1,011 / 500 / 449 / 1,114 / 725 / 564 / 441 を照合した)。既存の行は 1 行も消していない。

### 10.4 実測と道具の集計行 (すべて worktree `r52-wp3`、基点 main `d2e7333`)

- **字数** (登録テストの `_split_sections` / `_iter_section_subblocks` / `_subblock_block_text` を import して実測):
  - 最長ブロックは **SI-09 / MitateDB-api / 既定 = 13,745 字** (上限 15,200、残り 1,455)。基点では SI-14 / r2db-api / 既定 = 12,624 字が最長で、この行は今回変えていないので 12,624 のままである。
  - 次いで SI-14 / r2db-api / 既定 12,624、SI-08 / MitateDB-api / 既定 11,858 (基点 10,190)、SI-10 / MitateDB-api / 既定 10,625、SI-08 / MitateDB-api / `ops inventory` 8,187 (基点 5,958)。どれも上限内。
  - 最長の物理行は **1,384 字** (:547、SI-08 / r2db-api の既存の行。今回足した行ではない)。上限 1,400。今回足した / 書き換えた行の最長は :702 の 1,210 字 (差し戻し 1 の後も同じ)。
  - **途中の実測**: R1 を 1 行に収めた最初の形は 1,433 字で 1 行 1,400 字の上限を超えた。「両 peer の算式が同じでない」という節を A1 の行の冒頭へ移して 1,190 字に収めた (主張の内容は移動しただけで、増減していない)。
- **`python3 tools/check_control_mapping_split.py --base d2e7333 --expect "<下の行>"`** → 集計行 `missing=7 added=15 moved=0 empty_axis_added=0 empty_axis_removed=1 subsequence=ok preamble=differs ccr14=identical rule=identical`、**exit=0**。期待行は §10.2 の 2 つの表 (書き換え 7 件 → `missing=7`、書き換え 7 + 追加 8 = `added=15`、小ブロック間の移動なし → `moved=0`、`ops inventory` の Status の `- —` を主張に置換 → `empty_axis_removed=1`、既存の主張の順序を変えていない → `subsequence=ok`、版数行と再実測の文を書き換えた → `preamble=differs`) から導いた。
- **`tools/dev/pt.py -C .claude/worktrees/r52-wp3 -- conformance-tests/test_control_mapping_register.py -q`** (リポジトリルートで実行) → `34 passed in 0.24s`、exit=0。
- **`python3 tools/check_doc_refs.py`** → `tracked markdown files scanned: 137` / `empty markdown files: 0` / `check_doc_refs OK: 0 dangling references`。
- **`python3 tools/public_value_scan.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md`** → `mode=tree files_scanned=2 total_flagged=0`。
- **テスト名の実在** (W3-8): 新たに引いた 11 件は `MitateDB-api/tests/test_ops_apply_platform_migration.py` の 7 件 (`test_apply_platform_migration_0014_sets_role_connection_limits_for_every_role_class`・`::_new_application_connection_limit_is_68`・`::_duplicate_object_fallback_connection_limit_is_68`・`::_preserves_0013_statement_timeout_on_provisioned_roles`・`::_is_transactional_and_rolls_back_on_permission_failure`・`::_survives_a_registry_role_dropped_before_it_runs`・`test_apply_platform_migration_accepts_0014_via_the_subcommand`) と `MitateDB-api/tests/test_ops_inventory.py` の 4 件 (`test_inventory_connection_headroom_rollout_two_processes_confirmed_three_processes_blocked`・`::_catches_0012_reapplied_alone_after_0014`・`::_catches_0013_reapplied_alone_after_0014_when_a_new_application_exists`・`::_misses_0013_reapplied_alone_after_0014_with_no_new_application`) で、いずれも `def test_` を grep で確認した。裸の `::name` は各行の冒頭の完全形と同じファイルに在る。
- **件数の実測** (R5): `grep -c 'def test_' MitateDB-api/tests/test_ops_apply_platform_migration.py` = **51** (同ファイルに `parametrize` は 0 件なので収集数と一致する)。`ops._PLATFORM_MIGRATION_FILENAMES` = 6 本、そのうち drift-then-restore のテストを持つのは 0005/0007/0011/0012/0013 の 5 本 (`0014` の drift-then-restore は無い)。`MitateDB-api/tests/test_platform_migration_reapply.py`:1053 の件数 pin も 6。

### 10.5 差し戻し 1 の記録 (2026-09-19。コードレビュー 1 回目 → 監督裁定 → 直し)

レビューは主張 15 件の断言を現物と突合し、全件一致。指摘 6 件はいずれも監督裁定済みで、次のとおり直した。**期待集計行は変わらない** (`missing=7 added=15 …`): 1 の対象行は本 WP が新しく足した bullet (`git show d2e7333:security/CONTROL_MAPPING.md` に当該文言 0 件) なので、その場の書き換えで済み、HISTORY への移送は生じない。

1. **[中] 事実誤り**: A4 (`security/CONTROL_MAPPING.md`:612) の「a stray `0012` … lowers **every** existing platform-plane and application role」は偽。`0012` は `mitatedbsvc_auditreader` を `ALTER` しない (`MitateDB-api/migrations/0012_role_connection_limits.sql`:78-81、`MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`:42-51、runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`:2346 の `0012` 行)。「`0012` が名指す role (api・controlplane・各 application の runtime/developer) を 68/20/36 に戻し、`mitatedbsvc_auditreader` は `0014` の 12 のままである」形に直した。字数 829 → 991。
2. **[中。監督裁定: 開示する] 未検証の非対称**: A1 (:581) の末尾に、r2db-api の配備が同じ plane の process を 2 つ並走させうるかは未検証であり、この差は受理済みの差ではない旨を 1 文足した (台帳 R-52 を引く。形は SI-00 の `a separate, still-open asymmetry (ledger item L4-13, still open)` に倣う。出所は設計メモ `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §9 の残課題)。字数 510 → 734。
3. **[中] 設計メモの改版**: `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` を **v0.4** に上げ、改版の行に「v0.4（2026-09-19）§4 の行番号に実測の訂正註を足した。本文の決定は変えていない。」を足した。既存の記述は 1 行も消していない。
4. **[低〜中。監督裁定] 行番号の引用**: `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の「## 4. 訂正註」に訂正註を 1 本足した。実測: 当該行 (`` `execution_ms` is declared `reference_wall_clock` `` で始まる bullet) は版 2.9 で `:570`。既存の訂正註の `:567` は版 2.7 時点の値で、版 2.8 (R-50 WP-3) の preamble 追記で既に `:568` へずれていた (`git show d2e7333:security/CONTROL_MAPPING.md` で実測)。**所在はレビューの示唆と異なり `### r2db-api` ではなく `### MitateDB-api` (既定の小ブロック)** で、`## SI-08 Bounded Resource Consumption` → `### MitateDB-api` → `#### Control` である。行番号に頼らない所在を併記し、以後ずれのたびに訂正註を足さない旨を書いた。`docs/design/CODE_COMMENT_PROVENANCE_V1.md` は v0.21 で既に同等の所在を持つので触っていない。
5. **[低] 触るファイルの本数**: §10.1 の「2 本のみ」を実測の 6 本の列挙に直した。
6. **[低。監督裁定: 直す] テストの記述**: `MitateDB-api/tests/test_ops_apply_platform_migration.py` の module docstring (`:11`-`:13`)「drift-then-restore for each of the **four** accepted files」を「5 of the 6 accepted files (0005/0007/0011/0012/0013; 0014 has none)」に、節見出しコメント (`:526`-`:527`)「drift-then-restore for each accepted file」を「drift-then-restore -- 0005/0007/0011/0012 (0013's own is in its own section below; 0014 has none)」に直した。実測: `ops._PLATFORM_MIGRATION_FILENAMES` は 6 本、drift-then-restore のテストを持つのは 5 本 (`0005`:603・`0007`:621・`0011`:643・`0012`:671 が当該節、`0013`:888 は自分の節)、`0014` は持たない。テストの本体は 1 行も変えていない。
7. **[別件]** SI-09 / MitateDB-api の既定が 13,745 字 (上限 15,200、残り 1,455) になった件は監督が台帳に起票する。本 WP では触らない。`0014` の主張に作業名は付けない (現状のまま)。

**差し戻し 1 の後の実測と集計行** (基点 main `d2e7333`、worktree `r52-wp3`):

- `python3 tools/check_control_mapping_split.py --base d2e7333 --expect "missing=7 added=15 moved=0 empty_axis_added=0 empty_axis_removed=1 subsequence=ok preamble=differs ccr14=identical rule=identical"` → 同じ集計行、**exit=0**。
- `tools/dev/pt.py -C .claude/worktrees/r52-wp3 -- conformance-tests/test_control_mapping_register.py -q` → `34 passed in 0.23s`、exit=0。
- `tools/dev/pt.py -C .claude/worktrees/r52-wp3 -- MitateDB-api/tests/test_ops_apply_platform_migration.py -q` → `51 passed in 6.74s`、exit=0 (§10.4 の件数 51 を実行でも裏付けた)。
- `python3 tools/check_doc_refs.py` → `tracked markdown files scanned: 137` / `empty markdown files: 0` / `check_doc_refs OK: 0 dangling references`。
- `python3 tools/public_value_scan.py` (触った 6 本) → `files_scanned=6 total_flagged=0`。
- **字数**: 最長ブロックは SI-09 / MitateDB-api / 既定 = **13,745 字のまま**変わらないので、preamble の (F) の再実測の文は §10.2 で置き換えた形のままでよい (測り直して確認)。SI-08 / MitateDB-api / 既定は 11,634 → **11,858** 字 (残り 3,342)。最長の物理行は **1,384 字** (:547、既存の行) のままで、今回の 2 件の伸び (:581 = 734、:612 = 991) はいずれも 1 行 1,400 字の上限内。

## 11. 訂正註 5 (2026-09-19) — WP-3 の統合、受け入れ監査、監督の受け入れ

- **WP-3 の統合**: main `dccceeb`。`security/CONTROL_MAPPING.md` 版 2.9 (追加 8・書き換え 7。旧文 7 件は `security/CONTROL_MAPPING_HISTORY.md` へ逐語)。コードレビュー 1 回 + 差し戻し 1 (事実誤り 1 件 = 「`0012` の単独再適用は全 role を下げる」→ auditreader は下がらない / r2db-api の並走が未確認であることの開示 / テストの docstring の「4 本」→ 受け付け 6 本・drift-then-restore は 5 本)。`tools/check_control_mapping_split.py --base d2e7333` = `missing=7 added=15 moved=0 empty_axis_added=0 empty_axis_removed=1 subsequence=ok preamble=differs ccr14=identical rule=identical`、exit 0 (起草担当・レビュー担当・監督・監査がそれぞれ再現)。完了ゲート (worktree を main へ早送りした木): `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。
- **受け入れ監査** (`evidence-auditor` 1 回、main `dccceeb`): **未充足 0、証拠不足 2、要訂正 3**。充足 = W1-1〜W1-13 と W1-17 (変異 22 件の log を全件読み、各 log とも収集 1 件・名指しのテストが FAILED)、W2-1〜W2-8 と S-1 の runbook の記載、W3-1〜W3-12、W4-2〜W4-4、依頼者裁定の 6 項 (132 / 36 / 68 / 12、並走 2、F-16 の床は不変 = `platform_declarations.py` の差分 0、`max_connections` は未決として開示、r2db-api の差分 0、裁定文の逐語)、公開規律。3704 + 6 (R-51 の新規テスト) = 3710 の独立照合も一致。
- **監督裁定**:
  - **A-1 (証拠不足: W4-1。WP-2 の独立レビューの指摘の原文が残っていない)** → 下の 11.1 に 1 回目の指摘 8 件を写して充足とする。
  - **A-2 (証拠不足: W2-1〜W2-11 の更新前後の行の逐語)** → 逐語の正本は作業コミット `3c1194c` (WP-2) と WP-4 の runbook 部分のコミットの差分とする。git の履歴は scratchpad と違って失われず、1 字も丸めない。§9 訂正註 3 の宣言のままで充足と裁定する。
  - **A-3 (要訂正 a)**: §2.4 の W1-1 の括弧の並び「api / controlplane / auditreader / application」に対する値の並びは **132 / 36 / 12 / 68** が正しい (auditreader = 12、application role = 68。設計 §4 と §7 訂正註 1 が正)。依頼者裁定の「132 / 36 / 68 / 12」は api / controlplane / application / auditreader の順である。**(b)** 実装報告の `ADMIN_DSN_ENV` の所在は `MitateDB-api/tests/test_ops_apply_platform_migration.py` の `:43` (報告の `:42` は誤り)。**(c)** §8 の「新規テスト 12 件」は、テスト関数 11 件 + `test_platform_migration_reapply.py` の parametrize の増分 1 件である。
  - **A-4 (設計疑義: `security/CONTROL_MAPPING.md` の「ledger item R-52, still open」)** → **R-52 は閉じない。** 実装 WP (WP-1〜WP-4) は受け入れるが、台帳の R-52 行は次の 2 つの残りを持つ未決の項目として開けておく: (i) r2db-api の配備が 2 つの process を並走させうるかの確認 (設計 §9)、(ii) 依頼者裁定 Q-4 (`max_connections` が条件 2 に足りない場合の方針。本番の読み取りの後)。
  - **A-5**: SI-09 / MitateDB-api の既定の小ブロックが 13,745 字 (残り 1,455) の件を roadmap に R-59 として起票する (R-50 の形で名前付き小ブロックへ分ける候補は `apply-platform-migration`・0013・0014・numbered set・runbook の受理の 7 行、計 5,223 字 — WP-3 のレビューの実測)。
- **受け入れ (監督、2026-09-19)**: **R-52 の WP-1〜WP-4 を受け入れる。** 本番には何も適用していない。`0014` の本番への適用は runbook §10 の手順と依頼者の指示による。

### 11.1 WP-2 の独立レビュー 1 回目の指摘 (A-1 の写し。runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` の当時の行番号)

1. 中 — step 7 の新規の段落で「never one of them on its own」と「The compensation for either case is to apply `0014` once more」が矛盾する。前者を `0012`・`0013` に限定し、`0014` 単独が安全である根拠 (自分の値しか SET しない、関数の置換が `0013` の `statement_timeout` も運ぶ) を足す。
2. 中 — §10.6 の `0014` の行の「idempotent and lowers nothing」「lowers none」は現物と食い違う。`0014` は無条件に値を SET するので、それより高くしてある上限は下がる。`0012` の行と同じ強さの警告にする。
3. 中 — §10.10.1 の item (8) の行と直後の「this stage does not resolve … Report and stop」の列挙が食い違う。`0014` 未適用の本番の初回の読みは必ず (8) blocked (api 68 < 128) で、step 7 が直せる。「step 7 の値を代入しても不足するものだけが止まる」と明示する。
4. 中 — deprovision が途中で落ちて registry に role 名だけ残る cluster では、`0013`・`0014` は `IF EXISTS` で飛ばすが `0012` に防御が無く、step 7 の第 1 命令が `undefined_object` で全部戻る。出口が §10.10 に無い。→ 出口 (§7 の deprovision の再実行。`0004` は `DROP … IF EXISTS` と無条件の `finish_deprovision_application`) を現物で裏付けて書いた。
5. 低 — 前提条件の括弧は条件 1 の話で、条件 2 (`max_connections` の不足) の出口 (Cloud SQL の `max_connections` の設定) が名指しされていない。
6. 低 — 検算例の合計 3 は blocked で終わり、出口 (旧 revision の tag の除去・`minScale` の見直しで合計を 2 に戻す。traffic projection の変更としての条件付き) が書かれていない。
7. 低 — 引いたテストが固定するのは rc≠0 と api = 68 の据え置きだけで、`InsufficientPrivilege` (42501) 自体は固定していない。「holds the rollback; the SQLSTATE is from the same measurement」に緩める。
8. 低 — §3 の role floor の表は古い値 (68 / 20 / 36) が表、現行の値が直後の註、という並びで、表だけ読むと読み違える。列名に 1 句足す。

2 回目の再確認で 8 件とも現物で解消、机上通し 10 状態の行き止まりと堂々巡りは 0 件、受理 (§9 訂正註 3)。
