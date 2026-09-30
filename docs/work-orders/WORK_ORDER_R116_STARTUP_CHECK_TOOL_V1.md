# 作業指示書 — R-116 MitateDB の起動時の検査 (F-16 / F-18) の検算を道具に移す (Change Set Manifest)

## 0. 版数・位置づけ

- **v1.0 (2026-09-30)。** 起草。基点 local main `f7dc503` (v1.1 で `ab20f4e` に改めた)。未発注・未 commit。
- **v1.1 (2026-09-30)。** 未発注・未 commit のまま改版。§7.1 の訂正註 1〜5 の内容を本文 (§0、§1.1、§2.2、§2.3、§3.1、§5) に取り込む (§7.1 は記録として残す)。設計 v0.3 (再確認レビューの裁定 12 件と設計 §12.3 の監督裁定 1〜3 を織り込んだ版) に合わせて §2.2・§2.3・§3.1・§3.2・§5.2 を作り直し、完了条件 46a〜46d・61a を足す (既存の番号は変えない)。§7.2 を足す。
- 基点 local main `ab20f4e` (契約 1.12.0。設計 v0.3 §0 の行番号の木)。worktree `r116` (branch `r116`)、本書では `$WT`。
- 台帳 `RM` §8.1 の **R-116** (`RM`:466)。**規模 M** (`OC` §1.13 の 74)。**変更クラス D** (`tools/change_class.py` の実測: `security/CONTROL_MAPPING.md` に触れる。`RM` §9 の 8)。D の証拠: C の全部 + 依頼者裁定の逐語 (§1.2) + 版付きの security-contract 決定 (`CM`、WP-3)。
- 設計の正本は `docs/design/MITATEDB_STARTUP_CHECK_TOOL_V0_1.md` v0.3 (以下「設計」)。設計 §12.3 の監督裁定 1〜3 と再確認レビューの裁定 (設計 §12.4) は設計の本文に織り込み済み (v1.0 の「§12.3 の監督裁定が設計の本文に優先する」は不要になった)。本書は設計の決定・却下案・背景を写さず節番号で指す (`RM` §9 の 9)。逐語は §1.2 の依頼者裁定と §3.2 の表 (設計 §9) だけ。
- 番号: 完了条件は全 WP の通し番号 (1〜47 と 46a〜46d は設計 §9 の番号、61a は設計 §8 の WP-3 の番号。既存の番号は変えない)。変異は **M<完了条件番号>** (`expect=red`)。変異の無い完了条件は「監査照合」とし、照合対象の逐語 (コマンドと出力、`file:line`、`git diff`) を設計に残すことを完了条件とする (`OC` §1.5 の 40)。実装担当は報告に逐語を貼る。

**略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`ROLES` = `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`、`CR` = `MitateDB-api/docs/cloud-run-cloud-sql.md`、`CM` = `security/CONTROL_MAPPING.md`、`TINV` = `MitateDB-api/tests/test_ops_inventory.py`、`$SP` = 監督が発注時に渡す scratchpad。

## 1. 枠

### 1.1 問題設定・守るべき条件・決定・却下案

- 問題設定と守るべき条件: 設計 §1・§2 (条件 1〜10)。
- 決定: 設計 §4 D-1〜D-10、§5、§6、§10、§12 の裁定 (§12.3 の監督裁定 1〜3、§12.4 の再確認レビューの裁定を含む。いずれも本文に織り込み済み)。却下案: 設計 D-1・D-4・D-7 の「却下」(蒸し返さない)。
- 依頼者判断待ち (両論。設計 §11): §10.10 を版 10 にすると `CR` §10.8 の表の §10.10 の行 (「Current version 9」) が現物と合わなくなる。(i) §10.8 を変えず、受理の記録は本書に置く / (ii) §10.8 のその 1 行だけ変える (§10.6・§10.7 の表の受理を無効にしない、と依頼者が裁定する)。本作業は (i) で進め、(ii) は完了時に依頼者に挙げる。

### 1.2 依頼者裁定 (逐語。設計 §0 から複製。再審議しない、`OC` §1.7 の 51)

  - 2026-09-29「本番の値は分からないので、確かめる手順の形で進めてください」
  - 2026-09-30「推奨の (1) と (3) の組み合わせで進めてください」((1) = 起動を拒む検査の検算を道具に移す項目を起票し、§10.10 の受理はその後)
  - 2026-09-30 監督の問い 1「着手条件に『本番の image の source ref と max_connections が分かること』を含めるか」、問い 2「Class D で進めてよいか」に対し:「1は含めない、2はDで進めてください」

## 2. 順序・役割・道具

### 2.1 順序

**WP-1** (道具とテスト) → **WP-2** (runbook) → §10.10 の受理レビュー → **WP-3** (記録、監督) → 監督の完了ゲート・受け入れ監査・merge。直列 (WP-2 は WP-1 の実物の出力を要する。設計 §8)。並行が無いので触るファイルの重なりの表は置かない。

### 2.2 役割と実装担当への制約

- **実装担当** (`ROLES` の 2): WP-1・WP-2 に 1 起動ずつ (差し戻しは別起動)。穴は 担当 worktree = `$WT`、作業指示書 = 本書の該当 WP の節、正本設計 = 各 WP の「読むべき正本」、タスク = 完了条件と変異の表、テスト / 変異 = §2.3。
- **制約** (全 WP): 下請けの Agent を起動しない (`OC` §1.7 の 47)。commit・merge・push・branch 操作・`git stash` をしない (`OC` §1.1 の 2)。例外は新規 file の `git add -N` (intent-to-add。内容は stage しない。§2.3 の `tools/tests` の `pt.py` の前提) だけ。pytest を直接走らせず §2.3 の道具を前景直列で使う (`OC` §1.5 の 39)。suite 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` を実行しない (`OC` §1.11 の 70)。設計に無い検査・機構は実装前に報告する (`OC` §1.5 の 37)。触ってよいパスの外の赤は直さず報告する。一時ファイルは `$SP` 配下、複数手順は `$SP` の bash 3.2 互換スクリプト。報告は `$SP/r116-wp<N>-report.md` (道具の出力行をそのまま貼る。`OC` §1.10 の 65)。新規のコメント・docstring は現在形で、経緯語 (フェーズ・WP・R-番号) を書かない。本番の値を書かない (設計 §2 の 10、`OC` §1.9)。
- **コードレビュー** (`ROLES` の 5、Class D、担当観点 指定なし): WP-1・WP-2 に 1 回ずつ、別の起動。観点は各 WP の「レビューの観点」と空振り (`OC` §1.5 の 32)・代理指標 (`OC` §1.7 の 52)。
- **§10.10 の受理レビュー**: 道具ができた後 (WP-2 の後) に、独立の受理レビュー (`ROLES` の 4 の設計レビューのモード。起草者・実装担当とは別の起動) で `CR` §10.10 版 10 を受理する。結果は本書 §6 に記録する。
- **受け入れ監査** (`ROLES` の 6、`evidence-auditor`): 全 WP の後に 1 回 (Class D。`OC` §1.13 の 74)。
- **監督**: 完了ゲート `tools/dev/gate.py -C $WT --label r116` (単独)、`tools/dev/finalize.py --tools-tests` (根の gate は `tools/tests` を含まない。WP-1 が `tools/tests` の 2 file を触るため。新規 file は `git add -N` した後。設計 §9 #46b)、WP-3 (実装担当を起動しない)、受け入れ監査の起動、local main への `--no-ff` merge、指摘の 1 件ごとの裁定 (`OC` §1.15 の 77)。push は停止中 (`OC` §2 の 20)。**本番には何も適用しない。**

### 2.3 道具の引数

`$SP` を export し、main checkout を cwd にして `-C $WT` で worktree を指す (渡し忘れると main を測る)。`PYTHONPATH` は worktree の `MitateDB-api/src` を明示する (`OC` §2 の 17)。Bash の timeout 600000、前景。

```bash
tools/dev/pt.py -C $WT -- MitateDB-api/tests/test_ops_startup_checks.py MitateDB-api/tests/test_ops_inventory.py -q
tools/dev/pt.py -C $WT -- tools/tests/test_sql_statement_safety_scan.py tools/tests/test_leaf_import_direction.py -q
tools/dev/mutate.py "$SP/r116-wp1-mutations.json" -C $WT
```

- `tools/tests` の 2 file の `pt.py` は、新規 file を `git add -N` した後に実行する (設計 §9 #46b)。
- 変異は 1 変異 1 entry、`-x` を使わない。各 entry の test id は、その完了条件のテストを 1 件だけ書く (`mutate.py` は最初の失敗で止まる)。`-k` の id は `--collect-only -q` で確かめる。`old` / `new` は実装担当が書き、報告に表で残す。REFUSED (75) は迂回しない (`OC` §1.10 の 66)。
- worktree を cwd にして: `python3 tools/check_comment_provenance.py --base ab20f4e <触った src>`、`python3 tools/check_comment_provenance.py --register`、`python3 tools/change_class.py <触った全パス>`、`python3 tools/check_doc_refs.py`、`python3 tools/public_value_scan.py <触った全パス>`。
- 期待形: 2 つの `pt.py` の集計行がどちらも failed = 0・skipped = 0 (`TINV` を含む)。`mutate.py` の変異表で M1〜M41・M46a・M46c・M46d (44 件) がすべて `red`。

## 3. WP-1 — 道具 `ops startup-checks` とテスト (実装担当)

**目的**: 設計 D-1〜D-8 の subcommand と D-10 のテストを置き、Known gaps (設計 §10 の (1)〜(9)) と D-4 の運用の事実を module docstring に書く。
**読むべき正本**: 設計 §2、§3、§4 D-1〜D-8・D-10、§5、§6、§8 の WP-1、§9、§10、§12。**クラス**: B (変更セット全体は D)。**テンプレート**: `ROLES` の 2。

### 3.1 触ってよいパス

設計 §8 の WP-1 の行のパス (各項は逐語):

- `MitateDB-api/src/mitatedb_api/startup_checks.py` (新規)
- `MitateDB-api/src/mitatedb_api/ops.py` (subparser・dispatch・`main()` の未知の引数の分岐だけ)
- `MitateDB-api/tests/test_ops_startup_checks.py` (新規)
- `tools/tests/test_sql_statement_safety_scan.py` (`_EXPECTED_DISCOVERED_MODULES["mitatedb"]` の 1 entry)
- `tools/tests/test_leaf_import_direction.py` (`NON_LEAF_MODULE_ENTRIES` の mitatedb に `startup_checks.py` の 1 entry と理由 1 行。`ops` 以外の `platform_declarations` / `config` を import するので non-leaf)

- **これ以外は 0 件。** 特に `platform_declarations.py`・`config.py`・`main.py`・`control_composition.py`・`http.py` を触らず、src で 2 つの検査の関数名を参照しない (設計 D-4 の帰結)。`TINV`・migrations・r2db・`spec/`・`security/`・`conformance-tests/`・`tools/` (上の 2 file を除く)・`CR` も触らない。
- import の向き (設計 D-1): `startup_checks.py` は `ops.py` を import しない。`_inventory_connect`・`_inventory_confirmed_read_only`・`_inventory_role_classes` は `cmd_startup_checks` (`ops.py` 側) が呼び、接続と role の class の表を引数で渡す。
- 設計 D-1 の L1 語彙の guard (`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`) は実測し、赤になれば直さず報告する。

### 3.2 完了条件 (1〜47、46a〜46d) → 変異 (設計 §9 の表、逐語)

境界の試験は D = 3、C = 2。試験の ref: G0 = `c387b32` (`9361f1b^1`)・`448c660` (`1f1ef2b^1`、`PD` 無し)、表に無い組 = `5e1eeac`、起動 module 無し = `785b23e` (`26dff2a^1`、Control)。

- #16〜#19 は、各 class の role の現在値 (`rolconnlimit`) を `0012` の値より上 (`0014` の値、#18 は `-1`) に置いてから判定する。#19 は 現在値 ≥ 床 > 窓 となる role (C = 2 の controlplane: 現在 36、床 32、窓 20) で総合が `blocked` になることを見る (再確認 9)。
- 合成の git repo は試験の `tmp_path` に `git init` して作る (#28・#46c が同じ fixture を使う。再確認 3・10)。
- #12〜#15・#25〜#28・#46c の試験は `reason` の語 (D-8) を assert する (再確認 5)。#1〜#5 の比べ方は D-10 (再確認 4)。

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | G3 の api の床が実物の F-16 と床 / 床 − 1 で一致 | 道具の api の床から D を外す |
| 2 | G3 の application の role の床が同上 | application の床から D を外す |
| 3 | G3 の controlplane の床が同上 | controlplane の床から C を外す |
| 4 | G3 の auditreader の床が同上 | auditreader の床から C を外す |
| 5 | G3 の F-18 が実物と等号 / +1 で一致 | 道具の比較の `>` を `>=` に |
| 6 | G1 / G2 の F-16 が代表 ref の `PD` と境界で一致 (api と application の role。コードレビュー 1 の裁定 1) | G1 の api の床に D を掛ける (M6)、application の床を 0 に (M6b) |
| 7 | G2 の F-18 が代表 ref の `PD` と等号 / +1 で一致 | G2 の下限から登録の項 [2x] を落とす |
| 8 | 登録 0 行でも F-18 は「登録 ≥ 1」の下限で判定し、登録 0 の下限を併記 | `max(count, 1)` を `count` に |
| 9 | 出力の登録数は role が NULL の行も数える | 数えを NOT NULL の行に絞る |
| 10 | G1 / G2 の parse が代表 ref の読み手と 6 入力で一致 | 空白を含む値を非整数とみなす |
| 11 | 未設定は世代の既定 (G1 / G2 = 32、G3 = 4) | G2 の既定を 4 に |
| 12 | G3 の env の不正値は両検査 `blocked` (`startup-fails-on-env`) | 不正値を既定 4 に落とす |
| 13 | Data の api の role が 0 件なら F-16 は `unknown` (`no-role-of-class`) | 0 件を `confirmed` に |
| 14 | `audit_dsn_configured: true` で auditreader の role が 0 件なら `unknown` (`no-role-of-class`) | auditreader の 0 件の検査を外す |
| 15 | 3 設定が揃わないとき F-18 を持つ revision は `blocked` (`headroom-settings-missing`)、F-16 は判定され、終了コード 2 | 欠けで例外を投げる (終了コード 1) |
| 16 | 窓 = min(現在、`0012`、`0014`)。api・controlplane・auditreader・application の窓を各々 assert | 窓から `0012` を外す |
| 17 | 窓の値は grant の class で当てる (prefix 付きの fixture の role に当たる) | 窓を `mitatedbsvc_*` の名前で当てる |
| 18 | `-1` は窓の min から外す | `-1` を min に含める |
| 19 | 総合は窓の判定 | 総合に `current_judgment` を使う |
| 20 | `0012` / `0014` の定数が migration の行と一致 | 定数 68 を 69 に |
| 21 | テスト (1): 代表 ref を持つ各行の再計算 = 表の literal | (iv) の切り出しを代入の値の式だけに狭める |
| 22 | テスト (2) Data: 作業木の組 = G3 の行 | `MAIN` にコメント行を 1 行足す (blob の SHA が変わり、テスト (2) Data だけが赤。v0.2 の変異「`CFG` の `_POOL_SIZE_HEADROOM` を 3 に」は M46a と重なるので替えた。再確認 1) |
| 23 | テスト (2) Control: 作業木の組 = G3 の行 | `CC` の `if env.get("MITATEDB_AUDIT_DSN"):` を `if True:` に |
| 24 | テスト (3): first-parent の相異なる組 ⊆ 表の行 | 表から 1 行を消す |
| 25 | 不在の ref は `unknown` (`ref-not-found`) | `cat-file -e` の失敗を G0 として扱う |
| 26 | `5e1eeac` は G0 にならず `unknown` (`fingerprint-not-in-table`)。試験は、起動 module 以外の file だけが検査関数を参照し文字列定数を持たない合成 ref も持つ (`5e1eeac` 単独では G0 の文字列定数の検査 (再確認 3) が先に `unknown` にするため、変異は合成 ref で赤になる。実装時の監督裁定 2026-09-30) | (v) の走査を起動 module だけに狭める |
| 27 | 起動 module の無い ref (`785b23e` の Control) は `unknown` (`startup-module-missing`) | 起動 module の不在を G0 として扱う |
| 28 | 合成の git repo (#46c と同じ fixture) に parse できない `.py` を置いた ref は `unknown` (`source-unparseable`) | parse できない file を参照 0 として扱う |
| 29 | `PD` の無い `448c660` は G0 (`present: false`) | G0 の条件に `PD` の存在を足す |
| 30 | `c387b32` は G0 (ast で数える) | 数えを部分文字列 `F-16` に |
| 31 | D-3 の網羅の欠けは終了コード 1 | 網羅の検査を外す |
| 32 | `control` と `control.*` の併記は終了コード 1 | 併記の検査を外す |
| 33 | `revisions` が空は終了コード 1 | 空の検査を外す |
| 34 | Data の `candidate` 0 件は終了コード 1 (`data.candidate` は語彙に無い) | `data.candidate` を語彙に足す |
| 35 | `env` の key の欠落は終了コード 1 | 欠落を `null` として扱う |
| 36 | 入力の拒否は DB に接続しない | 入力の検査を接続の後に移す |
| 37 | argparse の usage error (必須の引数の欠落) は終了コード 1 | usage error の上書きを外す |
| 38 | 未知の引数は終了コード 1 | `main()` の分岐から `startup-checks` を外す |
| 39 | `unknown` を含めば終了コード 2・`overall` = `unknown` | `unknown` のとき 0 を返す |
| 40 | read-only の接続と読み返し | 読み返しを省く |
| 41 | 出力に `checks_evaluated` と `known_gaps` の 9 項 | `checks_evaluated` を出さない |
| 42 | §5 の残りの拒否の項と `--repository` が git の checkout でないときの終了コード 1 が各 1 件の試験を持つ | 監査照合 (試験名の一覧の逐語を設計に残す) |
| 43 | CI の 3.11 と 3.12 の両 leg でテスト (1)〜(3) が緑。3.12 の leg は push の再開後に main の run で照合する (§12.3 の 3、`OC` §2 の 20) | 監査照合 (両 leg の集計行の逐語を設計に残す) |
| 44 | 新しい試験に skip / xfail が無い | 監査照合 (`git grep` の出力の逐語を設計に残す) |
| 45 | `TINV` 140 件が不変で緑 | 監査照合 (`pt.py` の集計行の逐語を設計に残す) |
| 46 | `PD` の F-16 / F-18 の関数、同型性の対象集合、(i)〜(iii) の file と `http.py` が不変 | 監査照合 (`git diff --stat` の逐語を設計に残す) |
| 46a | 代表 ref を持つ表の全行について、その ref の `PD` (G3 は `CFG` も) を git の object から読み込み、その行の世代の道具の式と、床 / 床 − 1 (F-18 は等号 / +1) で判定が一致する (#6・#7 を全行に広げる) | 作業木の `CFG` の `_POOL_SIZE_HEADROOM` を 2 → 3 (旧 G3 の行の ref は 2 のままなので赤) |
| 46b | `tools/dev/pt.py -C <WT> -- tools/tests/test_sql_statement_safety_scan.py tools/tests/test_leaf_import_direction.py -q` が failed 0・skipped 0 (新規 file を `git add -N` した後) | 監査照合 (`pt.py` の集計行の逐語を設計に残す) |
| 46c | 合成の git repo (起動 module と、改名した関数で `code="F-16"` を投げる `PD` を持つ) の ref は G0 にならず `unknown` (`reason` = `fingerprint-not-in-table`) | 文字列定数の検査を外す |
| 46d | G3 の `pool_input.x` = `role_pool_size(thread_limit)` | x から `role_pool_size` を外す (x = thread_limit) |
| 46e | git の呼び出しの env に `GIT_NO_LAZY_FETCH=1` が在る (コードレビュー 1 の裁定 6) | env の設定を外す |
| 46f | `declaration.current` は `process_ceilings` の 1 row の読みで `not-declared` / 数値 / `unreadable` の 3 値 (WP-2 の疑義 4 への裁定) | `not-declared` の分岐を `unreadable` に |
| 46g | git の呼び出しの env に `GIT_NO_REPLACE_OBJECTS=1` が在る (受理レビューの道具側 10 への裁定、§7.8 の 10) | env の設定を外す |
| 47 | 本表に対応の無い行が無い | 監査照合 |

- 変異 M1〜M41・M46a・M46c・M46d (44 件) は `$SP/r116-wp1-mutations.json` の 1 entry ずつ。42〜47 と 46b は監査照合。

### 3.3 レビューの観点

設計 §2 の条件 2 (read-only)・3 (失敗した読みが `confirmed` と同じ出力にならない)・5 (推測で通さない)・6 (G3 は実物を呼ぶか境界一致で固定)。D-4 の帰結 (指紋の file を触らない)。設計 §12.3 の 1 の代表 ref の無い行の照合 (作業木の組の行だけ、設計 D-4)。D-1 の import の向き。#46a が代表 ref を持つ全行を見ること。境界の試験の入力 (D ≠ C、設計 D-10)。

## 4. WP-2 — runbook (実装担当。WP-1 の統合の後)

**目的**: 設計 D-9。`CR` §10.10.1 step 6 の紙の検算と §10.4.4 step 7 の数えを道具の実行に置き換え、§10.10 を版 9 → 10 にする。
**読むべき正本**: 設計 D-9、§7、§10 (範囲外)、§11。`HANDOVER_20260929_FABLE2.md` §6 (受理の経過と教訓 (ix)〜(xi)。`OC` §0 のとおり `docs/archive/` 配下)。**クラス**: A (変更セット全体は D)。**テンプレート**: `ROLES` の 2。

### 4.1 触ってよいパスと手順の制約

- `CR` の §10.10 (`### 10.10` から) と §10.4.4 step 7 の F-16 / F-18 の段 (基点 `CR`:2689-2704) だけ。これ以外は 0 件。
- **`CR` の `### 10.6` から `### 10.9` の直前 (基点 `CR`:2861-3000、§10.8 の表を含む) は 1 byte も変えない** (設計 §2 の 7、§11 の (i))。基点 `ab20f4e` の sha256 (`f7dc503` と同じ) は `b44422ecdd46923c26931afb8a67c4b4ee1fa0d7bac2d73a365317c9d1529279`。worktree を cwd にして変更の前と後で次を実行し、逐語で記録する。

```bash
f=MitateDB-api/docs/cloud-run-cloud-sql.md
a=$(grep -n '^### 10\.6 ' $f | cut -d: -f1); b=$(grep -n '^### 10\.9 ' $f | cut -d: -f1)
sed -n "${a},$((b-1))p" $f | shasum -a 256
```

- runbook に書くコマンドは、書く前に合成の local cluster で実行して出力を確かめる (本番の値を使わない)。実行したコマンドと出力の逐語を `$SP/r116-wp2-commands.log` に残す。
- 語の機械的な置き換えをしない (`HANDOVER_20260929_FABLE2.md` §6 の教訓 (x))。
- 検証: worktree を cwd にして `python3 tools/check_doc_refs.py`、`python3 tools/public_value_scan.py MitateDB-api/docs/cloud-run-cloud-sql.md`。

### 4.2 完了条件 (48〜55) → 変異

| # | 完了条件 | 変異 |
|---|---|---|
| 48 | `CR` の `### 10.6` から `### 10.9` の直前の sha256 が変更の前と後で一致 (§10.8 の表は変わらない) | 監査照合 (§4.1 のコマンドと前後の出力の逐語) |
| 49 | §10.10.1 step 6 の F-18 と F-16 の段が道具の実行に置き換わり、紙の検算が残らない | 監査照合 (`git diff`) |
| 50 | step 6 が、道具に渡した D / C と `declare-process-ceilings` に渡す値の一致を、道具の出力の `declaration.proposed` と突き合わせる手順を持つ | 監査照合 (`file:line`) |
| 51 | 設計 D-9 が列挙する §10.10 の他の言及が道具の実行を指す | 監査照合 (列挙の各項の `file:line`) |
| 52 | §10.4.4 step 7 の F-16 / F-18 の数えの段が道具の `generation` / `present` を指し、基準の grep と Dockerfile の確認は残る (設計 F10) | 監査照合 (`git diff`) |
| 53 | §10.10 の版が 9 → 10 | 監査照合 (`file:line`) |
| 54 | runbook に書いた各コマンドの、合成の local cluster での実行出力 | 監査照合 (`$SP/r116-wp2-commands.log` の逐語) |
| 55 | 本表に対応の無い行が無い | 監査照合 |

### 4.3 レビューの観点

置き換えた後の各文が真であること (機械的な置き換え)。書いたコマンドと実行出力の一致。設計 §10 の範囲外と §7 の「文」の行を道具に委ねていないこと。

## 5. WP-3 — 記録 (§10.10 の受理レビューの後)

**実施**: 監督 (実装担当を起動しない)。
**読むべき正本**: 設計 §8 の WP-3 と完了条件 61a、`CM` (3.8)、`RM` §8.1 の R-116 の行、`OC` §1.16 の 78・79。**クラス**: D。

### 5.1 触ってよいパス

`security/CONTROL_MAPPING.md`、`docs/design/ROADMAP_POST_PHASE7_V1.md`、`docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` (版数ログの回転)、本書 §6。

### 5.2 完了条件 (56〜61、61a) → 変異

| # | 完了条件 | 変異 |
|---|---|---|
| 56 | `CM` の runbook の行参照は、runbook の行がずれたら同じ変更セットで現物の行に追随する (変更した他のファイルの行参照も同じ) | 監査照合 (変更前後の `file:line` の対) |
| 57 | 変更した各ファイルについて `grep -c '<path>:' security/CONTROL_MAPPING.md` の件数 (基点: `CR` 15、`MitateDB-api/src/mitatedb_api/ops.py` 93) | 監査照合 (コマンドと出力の逐語) |
| 58 | 台帳 R-116 の行の【追記】と版数行。版数ログの回転 (`OC` §1.16 の 78・79)。`tools/dev/ledger.py --check` が緑 | 監査照合 (出力の逐語) |
| 59 | §10.10 の受理レビューの結論が本書 §6 に在る | 監査照合 (`file:line`) |
| 60 | `tools/check_doc_refs.py`・`tools/public_value_scan.py <触った全パス>` が緑、`tools/change_class.py` が D | 監査照合 (出力の逐語) |
| 60a | `tools/dev/pt.py -C $WT -- conformance-tests/test_control_mapping_register.py -q` が緑 (`CM` の形と参照の解決は根の gate でしか走らないので、`CM` を触る WP はゲートの前に単独で回す。受け入れ監査の観察 1) | 監査照合 (集計行の逐語) |
| 61a | `CM`:1072 の「checks that on paper」の主張を道具の実行を指す形に、`CM`:1294 の「not accepted at 9」を版 10 の受理の状態に直し、`CM` の版の行を 3.8 → 3.9 にする | 監査照合 (`git diff`) |
| 61 | 本表に対応の無い行が無い | 監査照合 |

## 6. 記録 (統合時に監督が埋める)

### 6.1 §10.10 版 10 の受理レビュー (2026-09-30)

- 起動: `reviewer` (設計レビューのモード、担当観点なし。起草者・実装担当・WP-2 のコードレビュー担当とは別の起動)。対象: `CR` §10.10 版 10 と同じ変更セットの §10.4.3・§10.4.4 step 7・§6.5 の差分。材料: 設計 v0.3 §7 の表、`HANDOVER_20260929_FABLE2.md` §6・§7.10 の必須 23 件、道具の docstring、合成 cluster の実行記録。
- **結論: 受理。必須 0 件、任意 9 件、道具側の不確実 1 件。** 前の受理レビュー 3 回と確認レビュー 1 回の必須 23 件は、設計 §7 の「道具」の行は道具が、「文」の行は runbook の文が受け止めていることを確かめた。runbook の出力の抜粋は実行記録 ROUND 3 の逐語と一致。
- 裁定: 任意 9 件と道具側 1 件はすべて同じ変更セットで直した (§7.8)。§10.8 の §10.10 の行 (「Current version 9 / not accepted」) は byte 不変の範囲として据え置き。設計 §11 の (i) / (ii) は依頼者判断。
- 完了ゲート 1 回目 (直す前): `gate: 4687 passed, 2 subtests passed in 411.36s (0:06:51)`、`judge=PASS`、pg diff 0。2 回目は §6.2。

### 6.2 完了ゲート 2 回目・3 回目と受け入れ監査

- 完了ゲート 2 回目 (受理レビューの任意を直した後、`CM` 3.9 の主張を書いた後): `gate: 2 failed, 4685 passed, 2 subtests passed in 410.49s (0:06:50)`、`gate: judge=FAIL (failed=2, exit=1)`、pg diff 0。赤は `conformance-tests/test_control_mapping_register.py` の 2 件: 版の行のパス無しの `ops.py` (ambiguous)、SI-08 (`CM`:1072、777 字) と SI-09 (`CM`:1294、615 字) が Status の上限 300 字を超えた。受け入れ監査が検出した。
- 直し: 2 つの主張を参照型の 1 文 (274 字・300 字) に縮め、版の行はパスを全部書いた。`tools/dev/pt.py -C $WT -- conformance-tests/test_control_mapping_register.py -q` → `pt: 58 passed in 2.40s` (#60a)。
- 受け入れ監査 (`evidence-auditor`、2026-09-30): 充足 1〜41・46a・46c〜46f・47〜57・59〜61・61a。未充足 (記録のみ) 42・44・45・46・46b → 設計 §13 に逐語を置いて充足。未充足 58 → 台帳 v1.136 で閉止 (下)。証拠不足 43 → push 再開後 (§12.3 の 3)。観察 4 件: (1) WP-3 に `CM` 登録簿の検査が無い → #60a を足した、(2) 版の説明の 2 段の rollout の入口が step 6 と揃わない → 直した (`CR`:3087-3088)、(3) 未追跡の WO と引き継ぎ書は `check_doc_refs` が見ない → `git add -N` の後に緑を取り直した、(4) 46g の行と設計の版数行 → 足した (設計 v0.4)。
- 完了ゲート 3 回目 (最終形): `gate: 4687 passed, 2 subtests passed in 400.48s (0:06:40)`、`judge=PASS`、pg diff 0 (label r116-3、2026-09-30 13:39)
- 台帳: v1.136 で R-116 を閉止、§8.2 の索引行と記録ファイル、版数ログの回転 (v1.131)。`tools/dev/ledger.py --check`: `ledger --check: GREEN rows(8.1)=32 rows(8.2)=85 archive_sections=85`
- `CM` の行参照の件数 (#57): `grep -c 'MitateDB-api/docs/cloud-run-cloud-sql.md:' security/CONTROL_MAPPING.md` = 15、`grep -c 'MitateDB-api/src/mitatedb_api/ops.py:' security/CONTROL_MAPPING.md` = 93 (基点と同数)、`startup_checks.py:` 1 行 (参照 1)。写像先の行の本文は基点の行と一致 (ops.py 93 対、runbook 14 対。残る 1 対は SI-08 の主張の書き換え)。

## 7. 訂正註 (本文は書き換えない。`OC` §1.8 の 57)

### 7.1 2026-09-30 (監督。再開時の現物照合)

1. **基点は local main `ab20f4e`** (契約 1.12.0 の merge) である。§0 の `f7dc503` と §2.3 の `--base f7dc503` は `ab20f4e` と読み替える。設計が行番号を引く現物 (`PD`・`CFG`・`MAIN`・`CC`・`http.py`・`OPS`・`CR`・migrations) は `f7dc503..ab20f4e` で不変 (`git diff --stat` で 0 件) なので、設計の行番号はそのまま成り立つ。設計 §2 の 1 の「契約 (1.11.0)」は 1.12.0 が現物。台帳は v1.135、R-116 行は `RM`:466 (設計 §0 の `:467` は 1 行ずれ)。設計 §0 の略記 `H0929F2` の実体 `HANDOVER_20260929_FABLE2.md` は `docs/archive/docs/work-orders/` 配下にある (§4 の記載のとおり)。
2. **WP-1 の触ってよいパスに 1 件足す**: `tools/tests/test_sql_statement_safety_scan.py` の `_EXPECTED_DISCOVERED_MODULES` の `"mitatedb"` の集合に `startup_checks.py` を足す (同じ変更セットで実測により更新。`OC` §1.5 の 40b)。この file は変更セット全体の `tools/tests` の対象なので、監督の `finalize.py --tools-tests` の前に `git add -N` する。
3. **`startup_checks.py` は `ops.py` を import しない** (`ops.py` が `startup_checks` を import するので循環になる)。設計 D-6 の読み手のうち `OPS` に在るもの (`_inventory_connect`・`_inventory_confirmed_read_only`・`_inventory_role_classes`) は `cmd_startup_checks` (`OPS` 側) が呼び、接続と role の class の表を `startup_checks` の関数へ引数で渡す。`PD`・`CFG` の読み手 (`_read_connection_headroom_settings`・`_count_registered_applications`・`read_platform_declarations`・`thread_limit_from_env`・`role_pool_size`) は `startup_checks.py` から直接 import してよい (どちらも `OPS` を import しない)。§3.1 の「src で 2 つの検査の関数名を参照しない」はそのまま (指紋 (v) の帰結)。
4. **出力の `known_gaps` は 9 項**: 設計 §10 の (1)〜(8) に §12.3 の 2 (運用者の checkout の未 commit の変更は検出しない。受け止めるのは runbook の「source ref は attested の digest から取る」手順) を (9) として足す。§3.2 の #41 の「8 項」と設計 §6 の例の 8 項は 9 項と読み替える (項の識別子は実装担当が §6 の形で命名し、docstring の Known gaps と同じ順に並べる)。
5. **WP-3 は監督が行う** (実装担当を起動しない)。`CM` は 3.8 → 3.9。行参照の追随は変更した全ファイル (基点の件数: `CR` 15、`OPS` 93。`grep -c '<path>:' security/CONTROL_MAPPING.md` の出力を §6 に逐語で残す)。
6. 再確認レビュー (設計 v0.2、担当観点なし、`OC` §1.7 の 50 の回数に数えない) の結果は本節 7.2 に足す。

### 7.2 2026-09-30 (監督。再確認レビュー)

再確認レビュー (2026-09-30): 12 件、全件反映。裁定は設計 §12.4 の表 (文面は監督の scratchpad、追跡外)、v1.1 に取り込み済み。

### 7.3 2026-09-30 (監督。WP-1 の実装報告への裁定)

1. **WP-1 の触ってよいパスに 2 file を足す**: `tools/tests/test_src_import_readers.py` と `tools/tests/test_src_import_cycles.py` の `PINNED_MODULES["mitatedb"]` に `mitatedb_api.startup_checks` の各 1 entry (新 module の追加で赤になる pin。§3.1 の列挙の漏れ)。§2.3 の `tools/tests` の `pt.py` の引数にこの 2 file を足す (#46b の照合は 4 file の集計行)。
2. **設計 §9 #26 の変異の重なりを許容する**: 再確認 3 で足した文字列定数の検査が `5e1eeac` を単独で `unknown` にするため、変異「(v) の走査を起動 module だけに狭める」は `5e1eeac` では赤にならない。#26 の試験は、起動 module 以外の file だけが検査関数を参照し文字列定数を持たない合成 ref も持ち、変異はその case で赤になる (設計 §9 #26 の註)。
3. 実装報告 (f) の 1〜7・9〜13 (`cat-file --batch-check`、`ls-tree` の blob id、`--repository` の判定、拒否の rule 語 24 語、`known_gaps` の id、G3 の既定 4 の literal と `http.DEFAULT_THREAD_LIMIT` の一致の試験、JSON の重複 key を検査しない、`-1` と `=` 代入の意味、変異の無い追加試験、shallow で fail、`ast.parse` の警告、3.12 未実測) は設計の範囲内として受理。実装報告の疑義 3 件 (代表 ref の無い行、G1 / G2 の 0・負の `concurrency`、全 G0 の入力が `confirmed`) は観察として引き継ぎ書に残す。
4. `tools/change_class.py` は 5 path で B。変更セット全体の D は WP-3 の `CM` による。`check_comment_provenance.py --base ab20f4e` の 2 行 (新規 file、`ops.py`:163 の import 行) は避けられない赤として記録。

### 7.4 2026-09-30 (監督。WP-1 コードレビュー 1 への裁定。6 件、全件「直す」)

1. G1 / G2 の application role の床を #6・#46a の試験が固定していなかった (自作変異で緑)。data の行に application を 1 件登録して runtime role の床 / 床 − 1 を比べる。変異 **M6b** (application の床を 0 に) を足す。
2. M33 の赤は rule 語 `revisions-empty` (**訂正註 2026-09-30、再確認レビューの指摘: 実物の rule 語は `empty-revisions`。以下同じ**) の assert による (網羅の検査が同じ入力を別の rule 語で拒否する)。性質は「専用の rule 語で拒否」として妥当。変異表に註記。M34 は試験の入力の順を入れ替え、性質を壊す case を先に置く。
3. `startup_checks.py` の docstring 2 箇所 (組の要素の番号、argparse の usage error の stderr の行数) を実物に合わせる。
4. `ops.py` の `main()` の既存コメント「Every other subcommand keeps argparse's own default (exit 2)」は `startup-checks` の追加で偽になった。最小の語の追加で真にする。provenance の赤が増えれば register の要否を監督が決める。 **結果**: (2) が 1 行増えたので、監督が旧塊を `docs/code-history/MitateDB-api/ops.md` の CH-0545 (parent `ab20f4e`、correction 2026-09-30) に登録し、塊の末尾に `# history: CH-0545` を置いた。`--base ab20f4e` の赤は避けられない 2 行 (新規 file、`ops.py`:163 の import) だけ、`--register` OK 435 CH-IDs。差し戻し 1 の後の集計: `pt: 215 passed`、`pt: 12 passed` (tools/tests 4 file)、`mutate: 46 mutations, 46 as expected`。
5. `control` を宣言せず Control の revision が 0 件の入力は拒否 (rule 語 `control-revisions-missing`、終了コード 1、DB 接続の前)。`coverage["control"]` は `listed` / `declared-absent` の 2 値。設計 §5 の拒否の列挙に足す (#42)。
6. partial clone の lazy fetch: `_run_git` の env に `GIT_NO_LAZY_FETCH=1` (git 2.44 以降で有効、古い git では無視) を足し、docstring に前提を 1 文。試験 1 件 (subprocess の env を observe) と変異 **M46e** (env の設定を外す)。設計 D-4 の読み方に足す。

### 7.5 2026-09-30 (監督。WP-2 の実装報告への裁定)

1. 設計外の拡張 (`OC` §1.5 の 37) を受理: (i) step 10 の宣言値は step 6 の入力が env-only revision に与えた env と同じ、(ii) step 11 で道具の `database` と読みが違えば stop、(iii) step 13 で candidate の読み戻しが step 6 の入力の env と違えば step 6 へ戻る、(iv) `unknown` / `blocked` は失敗する bound として停止し、入力の誤りなら直して再実行、(v) `python3 -m json.tool` での整形。
2. WP-2 の範囲を広げる: `CR` §10.4.3 の 2342・2344・2345・2461・2482・2564 と 2675 (基点の行) の「step 6 の F-16 / F-18 の計算」「presence」を指す語を、道具の実行と出力を指す形に最小の語で直す (第 2 の判定経路を残さない。設計 F10 と同じ理由)。2461 の宣言既定値の例外は設計 D-5 のとおり step 6 では入力の規則に置き換わる。
3. `declaration.current` (WP-2 の疑義 4): 案 B。WP-1 で `read_platform_declarations` (全 row を読み、`surfaces` 未宣言の step 6 では必ず失敗) を `process_ceilings` の 1 row の読みに替え、値を `"not-declared"` / `{"data", "control"}` / `"unreadable"` の 3 通りにする。試験 1 件と変異 **M46f** を足す。設計 D-6・§6 の註。
4. Known gaps (9) (WP-2 の疑義 6): 足す側。step 6 に「道具は `git status --porcelain` が空の checkout から実行する」の 1 文。設計 §10 (9) の受け止めに足す。
5. `overall` の出力位置 (sort_keys) と版の日付はそのまま。`CM` の `CR` 行参照 15 件の追随は WP-3。

### 7.6 2026-09-30 (監督。WP-2 コードレビュー 1 への裁定。6 件、全件「直す」)

1. `CR` §6.5 の 1611-1612・1699 (変更後の行) が「step 6 の手計算」を指す (第 2 の判定経路)。範囲を広げて直す (§7.5 の 2 と同じ理由)。
2. 2 段の rollout の入口を「F-18 の判定が `blocked` で `reason` が `null`、かつ F-16 に `blocked` が無い」に限定する。版の説明 (3086) も同じ。
3. 終了コード 1 の stderr の記述に、argparse の usage error (usage 行 + error 行) の例外を足す。
4. findings の表と一覧の「Report and stop」を「step 6 が許す入力の訂正の後もなお `confirmed` でない」に限定する。
5. 出力 file を run ごとの `startup-checks-<run-number>.json` にし、最後の run の file 名を記録させる。コマンドの形が変わるので合成 cluster で再実行し log に足す。
6. (乙): step 13 の「step 6 に戻る」に、やり直す範囲 (step 6 から順に。step 7 の再適用と step 10 の env-only revision の扱い) と、deploy 側の値が誤りなら deploy をやり直す選択肢を 1 文で足す。

### 7.7 2026-09-30 (監督。WP-2 再確認の観察 2 件)

再確認 (差し戻し 1 の後) は指摘なし。観察 A (§6.5 の 2 段の rollout の入口の条件が step 6 と揃っていない) と B (step 13 のやり直しで env-only revision は `rollback_target` も持ちうる) は監督が同じ変更セットで直した (`CR`:1612「where step 6 allows it」、`CR`:4509-4510「(and `rollback_target` once step 10 re-fixed the record to it)」)。直後の sha256 (§4.1): a=2861 b=3001、`b44422ecdd46923c26931afb8a67c4b4ee1fa0d7bac2d73a365317c9d1529279`。`check_doc_refs OK: 0 dangling references`、`public_value_scan` `files_scanned=1 total_flagged=0`。

### 7.8 2026-09-30 (監督。§10.10 版 10 の受理レビューへの裁定)

結論は **受理** (必須 0 件、任意 9 件、道具側の不確実 1 件)。記録は §6。完了ゲート 1 回目: `gate: 4687 passed, 2 subtests passed in 411.36s (0:06:51)`、`judge=PASS`、pg diff 0 (label r116、2026-09-30 13:00)。任意の全件を同じ変更セットで直す (`OC` §1.15 の 77 の「直した」)。src に触るので完了ゲートを直した後にもう一度回す。
1. Control の env-only revision: step 6 に、Control が legacy の名を持つならその env-only revision を `control.env_only_revision` として載せる (env は Control のテンプレートの env から legacy の名を除いたもの)、absent は Control が legacy の名を持たないときだけ、の 1 文。
2. 宣言 3 点と `known_gaps` の対応: runbook の括弧を「`known_gaps` が名指しするのは前 2 点で、source_ref の宣言には固有の識別子が無い」旨に。docstring の Known gap 9 の「caught by」に clean-checkout の規則を足す (src)。
3. 前提条件に「step 1 の前にも同じ入力で 1 回実行し、`confirmed` でなければ stage を始めない。後続の step 7・11・13・Rollback が参照するのは step 6 の実行」を足す。
4. `audit_dsn_configured`: 値でも secret 参照でも名を持てば `true` (厳しい側)、名が無いときだけ `false`。
5. §10.4.4 の Dockerfile 検索を step 6 で使うときは `MITATEDB_MAX_CONCURRENCY` / `MITATEDB_THREAD_LIMIT` を設定する hit だけが意味を持つ、の 1 文。
6. Rollback の括弧に「, or `env_only_revision` once step 10 re-fixed the record to it」。
7. 2 段の rollout の入口に「and every other judgment is `confirmed`」。
8. 「nothing is fetched」に git 2.44 以上の前提と、古い git なら full clone、を足す。
9. `CM`:1072 の主張は WP-3 で文ごと直す (行番号だけ直さない)。
10. (道具側、不確実) `refs/replace` の差し替え: `_run_git` の env に `GIT_NO_REPLACE_OBJECTS=1` を足し、env の試験に assert を足し、変異 **M46g** (この設定を外す) を足す。

### 7.9 2026-09-30 (監督。finalize の STOP)

`tools/dev/finalize.py --tools-tests` は commit `c280918` の後の `tools/tests` で 1 件赤 (`tools/tests/test_no_shared_cluster_defaults.py::test_admin_dsn_env_definitions_are_pinned_to_32_files`: `ADMIN_DSN_ENV` を module 先頭で定義する追跡 .py の件数 pin 32 → 33。33 件目は `MitateDB-api/tests/test_ops_startup_checks.py`) で STOP (merged=no)。WP-1 の触ってよいパスに `tools/tests/test_no_shared_cluster_defaults.py` (pin 1 件、試験名と docstring) を足し、実測で 33 に更新 (`OC` §1.5 の 40b)、同 file `6 passed`。commit を amend し、`tools/tests` 全体を回してから local main へ `--no-ff` merge する (finalize の STOP の回復手順)。教訓: 新しいテスト file が `ADMIN_DSN_ENV` を定義するときはこの pin も動く (tools/tests の pin は 5 file)。

