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
