# 作業指示書 — R-57 `apply-platform-migration` に再適用の「列」を受け付けさせる

## 0. 版数と位置づけ

- **v1.0 (2026-09-20)。** 台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-57** (`RM`:455)。設計文書は **`docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md` (監督確定、設計レビュー 1 回、裁定 G-1〜G-4 と R-1〜R-12 を反映)** で、枠・決定・却下案・実測はすべてそちらにある。本書はその Change Set Manifest である。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。
- **基点**: **R-63 の統合後の main** (設計 §8 の着手の前提)。**SHA は着手時に監督が埋める** → `9127598` (2026-09-20、R-58・R-63 の統合後)。
- **変更クラスは全体で D** (設計 §8)。WP ごとの導出は下表。

| WP | クラス | 導出 |
|---|---|---|
| WP-1 | **B** | 触る path に `security/`・`spec/`・`conformance-tests/`・`CLAUDE.md` が無く、`.md` 以外 (`ops.py`・テスト) を含む |
| WP-2 | **A** | `MitateDB-api/docs/cloud-run-cloud-sql.md` のみ |
| WP-3 | **D** | `security/` 配下 (`tools/change_class.py` 実測 = `class=D`) |

- **D が求める追加証拠** (設計 §8.1): 依頼者裁定の逐語 (2026-09-19) — 「その方針で進めてください、完了まで行ってください、判断は推奨で進め後から報告してください。推奨は長期的な視点で製品価値のある判断にしてください。」 本件の決定はこの**委任**の下で監督が推奨として下したものであり、完了後に依頼者へ報告する。版付き security-contract 決定は `security/CONTROL_MAPPING.md` **版 2.13** (WP-3)。
- 契約版数は **1.8.0 のまま据え置く** (`spec/` に触れない。設計 §2 の (iv))。設計レビューは 1 回で済んでいる。

## 1. 共通の枠

### 1.1 読むべき正本

- 設計 `docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md` の §3 (現物の事実)、§4 (D-1〜D-8)、§5 (追随する現物)、§7 (証拠)、§8・§8.1〜§8.3 (クラス・WP・裁定)。
- `CLAUDE.md`、`docs/work-orders/OPERATING_CONDITIONS.md` §0・§1.4・§1.5 (とくに 40・40b)・§1.6・§1.9・§1.10。

### 1.2 全 WP 共通の触らないファイル

`spec/`、`conformance-tests/` の各テスト本体、`security/SECURITY_INVARIANTS_V1.md`、**`MitateDB-api/migrations/` 全部** (設計 §2 の (iv))、`r2db-api/` 全部 (設計 D-8)、`MitateDB-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` (設計 §5)、`docs/design/` (統合の記録は監督)、`.github/`、`tools/dev/`。

### 1.3 順序と触るファイルの重なり

**直列**: WP-1 → WP-2 → WP-3 (設計 §8、G-4)。並行 WP は置かない。3 つの WP の触るパスは互いに重ならないが、runbook (WP-2) の文言が WP-1 の確定する拒否の形に依るので直列にする。

### 1.4 worktree と道具の引数

- worktree は `.claude/worktrees/inspiring-dewdney-461b95`。**コマンドは main checkout を cwd にして走らせ**、`$SP` (自分の scratchpad) を export しておく。
- テスト: `tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- MitateDB-api/tests/<担当ファイル> -q` (前景・Bash timeout 600000。§1.6 の 42)。
- peer suite を回すのは **`-- MitateDB-api/tests -q` の前景 1 回だけ** (約 9 分。1 回の呼び出しに収まる)。`conformance-tests` と `tools/tests` は別の呼び出しにする。
- 変異: `tools/dev/mutate.py "$SP/r57-wp<N>-mutations.json" -C .claude/worktrees/inspiring-dewdney-461b95`。
- **`gate.py` / `finalize.py` / `pytest` の直接実行・commit・merge は行わない** (監督)。

### 1.5 実装担当の注意 (全 WP 共通)

1. **下請けの Agent を起動しない** (§1.7 の 47)。**suite 全体は回さない** (完了ゲートは監督)。**疑義は実装せず報告に書く** — 設計に無い検査・機構を足さない (§1.5 の 37)。設計と現物が食い違ったら止まって上げる。
2. 変異は **1 項目 1 テスト**。`mutate.py` は `expect=red` に `-x` を付け**最初の失敗で打ち切る**ので、1 つの変異の `tests` に 2 件以上を並べない。
3. **行番号 pin・件数 pin は同じ変更セットで実測更新する** (§1.5 の 40b)。件数を実測値へ合わせるだけで済ませず、対象が走査に入ったことを確認する。
4. **新しいテストファイルを足す場合は `git add -N` した状態で `tools/tests` を回す。** 未追跡の間は `git ls-files` の列挙に入らず、件数 pin が統合の時まで赤にならない (`docs/work-orders/HANDOVER_20260920_FABLE.md` §6)。
5. **絶対パス・一時ディレクトリ名・traceback・実 DSN / 実ホスト名 / 実ドメインを文書にもコメントにも書かない** (§1.9、§2 の 13)。合成値と `example.invalid` のみ。
6. **報告は必ずファイルに書く** (`$SP/r57-wp<N>-report.md`)。最終の往復も報告ファイルに残す。

### 1.6 確定文言 (英語。言い換えない。§1.5 の 35・36)

`_die` の調子に合わせる (`ops.py`:241-243 = `error: <message>` を stderr、終了コード 2)。**閉包検査は `_resolve_platform_migration_file` の後に走るので、文言に現れるファイル名はすべて `_PLATFORM_MIGRATION_FILENAMES` の要素であり、operator の入力の値そのものではない** (設計 D-2)。

- **T-1 閉包違反** (`<FILE>` と `<RUN>` は定数由来):

  ```
  apply-platform-migration: <FILE> is superseded by a later platform migration; apply the whole run in one call, in this order: <RUN>
  ```

  `<RUN>` は `<FILE>` とその後続を `_PLATFORM_MIGRATION_FILENAMES` の順で空白区切りにしたもの (例: `0012_role_connection_limits.sql 0013_role_statement_timeouts.sql 0014_role_connection_limits_rollout.sql`)。

- **T-2 順序・重複違反**: `apply-platform-migration: FILENAMEs must be given in migration order, each at most once`

- **T-3 途中失敗** (既存の `_redact_connection_values` を通した psql の出力を最後に置く。`ops.py`:2755 の形を保つ):

  ```
  apply-platform-migration failed at <FILE>
  applied: <適用済みのファイル名を空白区切り。無ければ (none)>
  not run: <未実行のファイル名を空白区切り。無ければ (none)>
  An applied file may still carry a value a later file in this run replaces. Re-run the whole run from its first file; every file in it is idempotent.
  ```

## 2. WP-1 — 道具 (`ops.py`) と MitateDB のテスト

**目的**: 設計 D-1・D-2・D-3・D-4 を実装し、D-6 の既存テストを追随させる。**2 段にしない** (実測は設計で済んでいる)。

**触ってよいパス**: `MitateDB-api/src/mitatedb_api/ops.py`、`MitateDB-api/tests/test_ops_apply_platform_migration.py`、`MitateDB-api/tests/test_ops_inventory.py`、`MitateDB-api/tests/test_platform_migration_reapply.py`、`MitateDB-api/tests/test_ops_help_text.py`、`docs/code-history/MitateDB-api/ops.md`。**新しいテストファイルを足してよい** (足すなら §1.5 の 5)。

**範囲外**: migration ファイルの中身、`r2db-api/`、`_ISOMORPHIC_TARGETS`、runbook、`security/`、適用記録の ledger (却下案 X-b)、適用後の検算 (X-c)。

### 2.1 完了条件

設計 D-7 の **#1・1b・2・2b・2c・3a・3b・3c・4・5・6・6b・7・8・9・10・10b** を本 WP が持つ (#10 は help 側。runbook 側は WP-2)。逐語は設計 D-7 の表を正本とし、本書では複製しない。加えて:

- 新設する helper には **docstring を書く** (設計 R-3。基点が R-63 の統合後であるため書ける)。
- `_PLATFORM_MIGRATION_FILENAMES` / `_PLATFORM_MIGRATION_VARIABLE_TABLE` の pin と help のテスト (`MitateDB-api/tests/test_ops_help_text.py`:52-57、:121、:143-158) を**実測で更新**する (§1.5 の 40b)。`:121` の `_SECTION_HEADING_FIRST_LINE` は `ops.py`:2624 の節見出しコメントの逐語 pin なので、コメントを直したら同じ変更セットで合わせる。

### 2.2 完了条件 → 変異

赤になる test id は予想であり、**実装担当が実名に置き換えて報告する**。

| # | 変異 (操作) | 期待 |
|---|---|---|
| 1 | **M1**: 対象水準の写像から `0013` の関数本体の行を外す | 赤 |
| 1b | **M2**: `_PLATFORM_MIGRATION_SUPERSEDED_BY` から `0013` → (`0014`,) を外す | 赤 |
| 2 | **M3**: 抽出の `IF NOT EXISTS` 除外を無効にする | 赤 (余分な対象) |
| 2b | **M4**: `IF EXISTS` の skip guard の中を `IF NOT EXISTS` と同じに扱って除外する | 赤 |
| 2c | **M5**: `CREATE … FUNCTION` の本体の走査除外を外す | 赤 (余分な対象) |
| 3a | **M6**: 閉包検査そのものを無効化する | 赤 |
| 3b | **M7**: T-1 の文言から `<RUN>` の列挙を落とす | 赤 |
| 3c | **M8**: T-1 の文言に入力の値を混ぜる | 赤 |
| 4 | **M9**: 昇順・重複なしの検査を無効化する | 赤 |
| 5 | **M10**: 閉包検査の「表に後続を持たないファイル」の枝を外し、一律に 2 本以上を要求する | 赤 |
| 6 | **M11**: psql 変数の絞り込みを外し、全ファイルに渡す | 赤 |
| 6b | **M12**: 拒否の代わりに、表の後続を自動で足して流す (X-a の形) | 赤 |
| 7 | **M13**: 途中で失敗した後も以後のファイルを流し続ける | 赤 |
| 8 | **M14**: 列の順序の保持を外し、逆順に流す | 赤 (実 PostgreSQL) |
| 9 | **M15**: psql 直打ちへ移した drift-then-restore のうち 1 件から、ops 経由の拒否の assert を落とす | 赤 |
| 10 | **M16**: help の生成を `_PLATFORM_MIGRATION_FILENAMES` から切り離す | 赤 |
| 10b | **監査照合**: `python3 tools/check_comment_provenance.py --base <基点> MitateDB-api/src/mitatedb_api/ops.py` の出力を逐語で報告に残す。コード差分に伴う §4.1 (1) 以外が出ないこと | — |

- 変異の JSON は `$SP/r57-wp1-mutations.json` に置く。`old` は実装後の現物に合わせて埋め、`tests` は**1 件だけ**にする。

### 2.3 実行するコマンド

```bash
export SP=<自分の scratchpad>
tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- MitateDB-api/tests/test_ops_apply_platform_migration.py MitateDB-api/tests/test_ops_help_text.py -q
tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- MitateDB-api/tests/test_platform_migration_reapply.py MitateDB-api/tests/test_ops_inventory.py -q
tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- MitateDB-api/tests -q   # 前景 1 回のみ (約 9 分)
tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- tools/tests -q          # 新規ファイルを足したら git add -N の後
python3 tools/check_comment_provenance.py --base <基点> MitateDB-api/src/mitatedb_api/ops.py
tools/dev/mutate.py "$SP/r57-wp1-mutations.json" -C .claude/worktrees/inspiring-dewdney-461b95
```

## 3. WP-2 — runbook の追随

**目的**: 設計 D-5 の 7 箇所を直す。**凍結範囲 (:2786-2839 の ADMIN OPTION の実測記録) は書き換えず、訂正註を 1 つ添えるだけ** (設計 G-1 / R-1)。

**触ってよいパス**: `MitateDB-api/docs/cloud-run-cloud-sql.md` のみ。**範囲外**: `ops.py`・テスト・`security/`、runbook の §10 以外の節、凍結範囲の書き換え。

### 3.1 完了条件

設計 D-7 の **#10 の runbook 側**を本 WP が持つ。中身は D-5 の 7 箇所すべてである (逐語は設計 D-5)。

1. 手順 7 (:3054-3058) が 1 コマンドの列になり、**失敗窓の段** (D-4) が在る。
2. :3067-3068 が「道具が拒否する」に合っている。S-1 の「捕らえない」限界の記述は残っている。
3. :2772-2775 と :2831-2833 が「そのファイル以降を 1 回の実行の列として流す」になっている。
4. :2455 に「列は §10.7 の値が同じファイルで組む」が在る (R-5)。
5. §10.6 の :2398・:2399・:2400 が追随し、:2400 が「道具が列を強制する」に合っている (R-9)。
6. :1567 と :2702-2726 が列の形になっている (G-2)。
7. :2786-2839 は 1 字も変わっておらず、訂正註が 1 つ添えてある (G-1)。

### 3.2 完了条件 → 変異

| # | 変異 (操作) | 期待 |
|---|---|---|
| 10 (runbook 側) | **監査照合**。上の 1〜7 について、更新前後の行を `file:line` で報告に挙げる。**7 は `git diff` が :2786-2839 に 1 行も差分を出さないことを示す** | — |

- 文書のみの Class A であり、コード変異は持たない (§1.5 の 40 の「監査照合」)。照合対象の逐語記録は設計の実施記録の節に残す。

### 3.3 実行するコマンド

```bash
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py MitateDB-api/docs/cloud-run-cloud-sql.md
python3 tools/change_class.py MitateDB-api/docs/cloud-run-cloud-sql.md
```

## 4. WP-3 — `security/CONTROL_MAPPING.md` 版 2.13

**目的**: 設計 §7 が挙げる 2 行を現物に合わせ、R-8 の照合を行う。

**触ってよいパス**: `security/CONTROL_MAPPING.md`、`security/CONTROL_MAPPING_HISTORY.md`。**台帳 `RM` の R-57 行の更新と設計の実施記録は監督が統合時に行う** (実装担当は触らない)。**範囲外**: `SECURITY_INVARIANTS_V1.md` の本文、`spec/`、契約版数、`ops.py`・テスト・runbook。

### 4.1 完了条件

| # | 完了条件 |
|---|---|
| W3-a | :736 と :751 を現物に合わせる。**改版の作法は `security/CONTROL_MAPPING.md` の冒頭 (Update convention) に従い、現行行を書き換え、旧文は `security/CONTROL_MAPPING_HISTORY.md` へ逐語で移す** (見出しは SI の ID のみ。題を足すとアンカーが壊れる — `CONTROL_MAPPING_HISTORY.md` 冒頭)。版を **2.12 → 2.13** に上げ、冒頭の Version 行に本件の要旨を 1 文で足す |
| W3-b | **R-8 の照合**: :744 と :751 が引く計 5 件の `::test_…` が現物に在ることを grep で確かめ、出力を報告に残す。WP-1 でテストを移したので空振りしない (`RM`:462 の R-64 のとおり、これを見る機械検査は無い) |
| W3-c | `conformance-tests/test_control_mapping_register.py` が緑である |
| 11 | 本書の 3 つの対応表に、対応の無い完了条件が 1 行も無い |

### 4.2 完了条件 → 変異

| # | 変異 (操作) | 期待 |
|---|---|---|
| W3-a | **監査照合**: 書き換えた行と履歴へ移した旧文の `file:line`、`python3 tools/check_control_mapping_split.py --base <基点>` の出力 (逐語) | — |
| W3-b | **監査照合**: grep の出力 (逐語)、5 件とも 1 件以上 | — |
| W3-c | **M17**: Evidence のテスト名を 1 つ実在しない名前に変える | **緑のまま** (R-64 の限界の記録。変異が赤にならないことを実測で残す) |
| 11 | **監査照合** (本表)。照合対象の逐語記録を設計の実施記録の節に残す | — |

### 4.3 実行するコマンド

```bash
tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- conformance-tests/test_control_mapping_register.py -q
tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- tools/tests -q
python3 tools/check_control_mapping_split.py --base <基点>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py security/CONTROL_MAPPING.md
python3 tools/change_class.py security/CONTROL_MAPPING.md
```

## 5. 記録 (統合時に監督が埋める)

### 5.1 起草時の監督裁定 (2026-09-20)

- **K-1**: 設計 §8 の WP 表は D-7 の #9・#10 を WP-2 に置いたが、#9 (16 箇所のテスト呼び出しの移設) は WP-2 の触るパスでは満たせない。**本書の割り付け (#9 は WP-1、#10 は help 側 = WP-1 と runbook 側 = WP-2) を正とする。**
- **K-2**: WP-3 の W3-a〜W3-c は設計 §7 と裁定 R-8 から導いた完了条件であり、新しい決定ではない。採る。
- **K-3**: W3-c の M17 は「緑のまま」を期待する。変異の対応表の 1 行ではなく、**限界の監査照合** (R-64 が解くまで Evidence のテスト名の実在を機械が見ないことの実測) として読む。
- **K-4**: R-63 は main `9127598` で統合済みである。WP-1 が足す helper・定数には docstring・`#:` コメントを書く。`tools/check_comment_provenance.py --base 9127598 MitateDB-api/src/mitatedb_api/ops.py` の合格条件は「(1) 以外が 0 行」である ((1) はコードを変える差分で必ず出る)。

### 5.2 実施と差し戻しへの監督裁定 (2026-09-20)

- **K-5 (WP-1 のコードレビュー 1 回目、低 9)**: psql 直打ちへ移ったテスト `test_inventory_ddl_lock_confirmed_after_apply_platform_migration_0013` を `test_inventory_ddl_lock_confirmed_after_0013_is_applied` に改名し、`security/CONTROL_MAPPING.md` の該当行の追随を WP-3 の範囲に足した。
- **WP-1 のコードレビュー** 2 回 (1 回目: 高 1・中 4・低 4、2 回目: 差し戻し不要)。高 1 = 静的テストの関数見出しの正規表現が `OR REPLACE` を必須にしていた (素の `CREATE FUNCTION` で置いた関数の上書きが導出されない)。中 = 変数不足の文言が set の反復順で揺れる / 再適用テストの定数が死んでいた (solo 群と列を定数と `_PLATFORM_MIGRATION_SUPERSEDED_BY` から導出する形に直した) / 条件 (iii) のテストが完全な列を渡していて判別力が無かった / 「全ての検査が psql の起動より前」を固定するテストが無かった。低の裁定: 入れ子の `IF` を持つガードは抽出の限界として docstring に書く (過検出 = 赤になる安全側) / 余分な変数の拒否は 1 ファイルなら基点の文言、2 ファイル以上なら `no file in this run accepts --X` / M10 は分岐の「追加」の形 (現物に除去すべき明示の分岐が無い)。
- **WP-2 の完了条件 3 と 7 の衝突**: 行番号の範囲が重なっていた。**凍結は ADMIN OPTION の実測記録そのものだけ**で、記録の中の復旧の指示文は生きた手順として書き換える (設計 R-1)。WP-3 の報告の「範囲内のハンク 0 個」は誤りで、復旧の指示文のハンクが 1 つ在る (WP-2 の報告と受け入れ監査が正しい)。訂正註の文 (単独の `0012`・`0013` を拒否し、単独の `0014` は受け付ける) は監督が直した。
- **WP-2・WP-3 の文のレビュー** 2 回 (1 回目: 高 1・中 2・低 4、2 回目: 差し戻し不要)。高 1 = runbook の §10.6 の表と §10.10 の手順を変えたのに版数と §10.8 の受理記録が据え置かれ、`security/CONTROL_MAPPING.md` の版数を引く 2 行も連鎖して古くなる (設計 §7 の「不正確になるのは 2 行」はこの経路を見落としていた)。**裁定: §10.6 を版 4、§10.10 を版 7 に上げ、同じ変更セットで受理を記録する** (先例は R-54)。**§10.7 の版は据え置く** — 変えたのは表の外の「How the table's values are passed」の段落だけで、版数規則の主語は表本体である (レビューは両論を併記し、据え置きを妥当と読んだ)。中 = 「3 本のどれかを含む列は実質 `0012` → `0013` → `0014`」は言い過ぎ (道具は `0014` 単独と `0013 0014` を受け付ける) / §10.6 の `0012` 行・`0013` 行が未追随。低 6 の裁定: 復旧の指示は道具の確定文言 T-3 (列の先頭から流し直す) を正本にする。
- **受け入れ監査への裁定**: (A-1) 指摘 3 (`_validate_platform_migration_run` の docstring は `<RUN>` を `_PLATFORM_MIGRATION_FILENAMES` の順と言うが、実装は表のタプルの順を使う) は**コードを変えない**。表のタプルが `_PLATFORM_MIGRATION_FILENAMES` の順であることは、静的テスト `test_platform_migration_superseded_by_equals_the_target_map_folded_to_file_level` が、導出した後続を同じ順に並べたタプルとの等値で固定している (順が崩れれば赤)。(A-2) M15 は設計 D-7 #9 の字面 (assert を落とす) と違い、ops 側の閉包検査を無効化して赤を示す形である (assert を落とすだけでは緑になるため。等価以上)。(A-3) 監査が見つけた `security/CONTROL_MAPPING.md` の実在しないテスト名 6 件は本件の差分の外で、台帳 R-64 の行に実例として追記した。
- **既知の残件 (台帳 R-68)**: `ops.py` の `apply-platform-migration` の節見出しコメント (CH-0538) と `cmd_apply_platform_migration` の docstring (CH-0539) は「applies one platform migration file」のままである。`tools/check_comment_provenance.py --base` は、基点で CH-ID を持つ塊について「文の削除」しか通さず、訂正記録つきの言い換えを同じ変更セットで通す経路を持たない (R-55 は初回の登録だったので書けた)。help・runbook・新しい helper の docstring は列の形である。`MitateDB-api/tests/test_ops_help_text.py` が古い文を pin しているので、R-68 で直すときに同じ変更セットで動かす。

### 5.3 道具の出力と対応表

- **WP-1**: `pt: 1404 passed, 2 subtests passed` (MitateDB-api の peer suite)、`pt: 547 passed` (`tools/tests`)。`tools/check_comment_provenance.py --base 9127598 MitateDB-api/src/mitatedb_api/ops.py` は `FAIL (§4.1 (1)) … code changed` の 1 行だけ (K-4 の合格条件)、`--register` は `comment provenance register OK: 87 files scanned, 430 CH-IDs` (CH-0540 = `_platform_migration_variables` の docstring)。新設の helper・定数は docstring・`#:` コメントを持つ (R-63 の直しの最初の適用)。
- **変異 22 件とも `expect=red got=red`、復元は sha256 2 回で照合済み** (test id は `MitateDB-api/tests/test_ops_apply_platform_migration.py::` を省く。M19 だけ `MitateDB-api/tests/test_platform_migration_reapply.py::`): M1 (D-7 #1) → `test_platform_migration_target_map_contains_the_4_known_targets` / M2 (#1b) → `test_platform_migration_superseded_by_equals_the_target_map_folded_to_file_level` / M3 (#2) → `test_platform_migration_target_map_excludes_the_if_not_exists_guarded_auditreader_creation` / M4 (#2b) → `test_platform_migration_target_map_includes_the_if_exists_skip_guarded_alters` / M5 (#2c) → `test_platform_migration_target_map_never_scans_inside_a_function_body` / M6・M7・M8 (#3a・#3b・#3c) → `test_apply_platform_migration_solo_0012_is_rejected_with_the_confirmed_closure_message` / M9 (#4) → `test_apply_platform_migration_out_of_order_run_is_rejected` / M10 (#5) → `test_apply_platform_migration_solo_0011_still_passes_the_closure_check` / M11 (#6) → `test_apply_platform_migration_run_psql_argv_carries_only_each_files_own_variables` / M12 (#6b、条件 (iii)) → `test_apply_platform_migration_never_starts_a_files_own_successor_the_operator_omitted` / M13 (#7) → `test_apply_platform_migration_run_stops_at_the_failing_file_with_the_confirmed_t3_message` / M14 (#8) → `test_apply_platform_migration_run_of_0012_0013_0014_leaves_the_newest_values` / M15 (#9) → `test_apply_platform_migration_0012_restores_a_manually_drifted_function_body` / M16 (#10 の help 側) → `test_apply_platform_migration_help_enumeration_is_derived_from_the_constant` / レビュー分 M17 → `test_platform_migration_function_header_regex_matches_a_bare_create_function_too`、M18 → `test_apply_platform_migration_missing_variable_message_is_deterministic_by_table_order`、M19 → `test_reapply_solo_and_run_groups_partition_a_synthetic_7_file_set`、M20 → `test_apply_platform_migration_resolves_every_file_before_any_psql_starts`、M21 → `test_apply_platform_migration_run_variable_mismatch_is_rejected_before_any_psql_starts`、M22 → `test_apply_platform_migration_run_unexpected_variable_message_names_no_file`。
- **WP-2** (文書のみ、監査照合): `check_doc_refs OK: 0 dangling references`、`public_value_scan` `total_flagged=0`。runbook の版数・文を pin するテストは 0 件 (grep 実測)。
- **WP-3**: `pt: 34 passed` (`conformance-tests/test_control_mapping_register.py`)、`tools/check_control_mapping_split.py --base 9127598` は `missing=5 added=7 … subsequence=ok ccr14=identical rule=identical`、旧文 5 行は `security/CONTROL_MAPPING_HISTORY.md` へ逐語。字数の実測: SI-09 / MitateDB-api / platform upgrade 12,200、SI-08 / MitateDB-api / ops inventory 8,335、最長は SI-08 / MitateDB-api の既定 13,023。`security/CONTROL_MAPPING.md` が引く 3 つのテストファイルの `::name` 86 件に実在しない名前は 0 件 (R-8・K-5)。W3-c の M17 (本節の M17 とは別。Evidence のテスト名を実在しない名前に変える) は `expect=green got=green` — 台帳 R-64 が解くまで機械は見ないことの実測 (K-3)。

### 5.4 受け入れ監査と監督の受理 (2026-09-20) — runbook §10.8 が指す受理記録

- **独立の確認**: 設計レビュー 1 回 (高 3・中 5・低 4、全件裁定して設計 v0.2 に反映)、WP-1 のコードレビュー 2 回、**runbook §10.6 (版 4)・§10.10 (版 7) と `security/CONTROL_MAPPING.md` 版 2.13 の文のレビュー 2 回** (実装担当・起草者とは別の起動。1 回目の指摘を直した後の 2 回目で差し戻し不要、言い過ぎは見つからず、各文は `ops.py` の現物の分岐と一致)、受け入れ監査 1 回 (レビュー担当とは別の起動)。
- **受け入れ監査の要点**: 条件 (iv) = `spec/`・`conformance-tests/`・`security/SECURITY_INVARIANTS_V1.md`・`MitateDB-api/migrations/`・`r2db-api/` の差分は 0 行。対応表に対応の無い完了条件は 0。変異 22 件の赤になった test id は道具のログと全件一致。確定文言 T-1〜T-3 は実装・テストとも逐語。D-7 #9 の 16 箇所は独立の実測で全件が移っている。差分に作業機の絶対パス・scratchpad 参照・変異文字列は 0 件。未充足として挙がったのは本節を含む記録 (同じコミットに入れて解消) と、5.2 の A-1〜A-3。
- **完了ゲート** (worktree、`gate.py -C`、WP-1〜3 と全ての差し戻しの後の木): `3789 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0 (基点 3763 から +26)。
- **監督の受理**: runbook §10.6 の版 4 と §10.10 の版 7 を、上の文のレビューと受け入れ監査を根拠に**受理する**。R-57 を受け入れる。決定は依頼者指示 2026-09-19 の委任 (§0 の逐語) の下で監督が推奨として下したもので、**完了後に依頼者へ報告する**。変更クラス D の決定にこの委任が及ぶかの事後確認は、`docs/work-orders/HANDOVER_20260920_FABLE.md` §4 (a) と同じ扱いで伺う。
- **本番には何も適用していない。** 本件は道具・runbook・統制の記述の変更で、クラスタ側の状態を変えない。

