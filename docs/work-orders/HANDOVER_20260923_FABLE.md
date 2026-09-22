# 引き継ぎ — 2026-09-23 (R-76・R-75・R-77・R-92/R-93/R-73・R-94 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260922_FABLE.md` で、**同書の §4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。

## 1. 現在地

- ローカルの main は **`7452b5b`** (本書の起草時点)。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-94 の最終の木での再実行で `3844 passed, 2 subtests passed`、`judge=PASS` (進行中の R-74 の木では `3859` = +15)。`tools/tests` は **585 本**。
- `security/CONTROL_MAPPING.md` は版 **2.20** (進行中の R-88 が 2.21 にする)、台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` は **v1.93**。
- **進行中 (本書の起草時点)**:
  - **R-74** — worktree `.claude/worktrees/r74`、**Class C**。`conformance-tests/test_conditions_register.py` に 15 本を足し (`conformance-tests/CONDITIONS.md` の散文が引くテスト名を現物に解決する機械検査)、完了ゲートは済み (`3859`)。コードレビュー 2 巡目の低 3 件を反映中。
  - **R-88** — worktree `.claude/worktrees/r88`、**Class D**。`security/CONTROL_MAPPING.md` の `file:line` を現物に解決する検査の追加と、偽の指し先 3 主張行の訂正、版 2.21。実装中。
  - 閉じた時点で監督が本書に **§6・§7** として追記する (前書 §6・§7 と同じ形)。
- 統合済みで未 fold の worktree は無い (`r75`・`r76`・`r77`・`r92`・`r94` は fold 済み)。

## 2. 本チャットで閉じたもの

| 項目 | 要点 |
|---|---|
| R-76 (B) `src/` の循環 import を検査するテストが無い | main `4b738f4`。新規 `tools/tests/test_src_import_cycles.py` (node id 2) が両 peer の `src/` の import graph を AST で組み (関数内・`TYPE_CHECKING` 下・`try` 下を含む全辺、`from . import X` と `from <pkg> import X` は submodule に解決、親 package の暗黙 import は辺にしない、`from <pkg> import <非 module 属性>` だけ package への辺)、非自明 SCC 0 を assert する。走査集合は peer ごとの dotted name の逐語一覧で pin (監督裁定。件数 pin にしない)。実測 module 87 / 辺 238 / 循環 0。変異 11 件、コードレビュー 1 (中 3・低 5)。「独立設計レビューの論点は未決」は §5.46 が反映済みで差し戻しが無かったことを D-7 に記して更新した |
| R-75 (B) `src/` の SQL 構築形を見る静的走査が無い | main `f2517ed`。新規 `tools/tests/test_sql_statement_safety_scan.py` (node id 5)。規則 1 = `sql.SQL(...)` の引数は静的に畳める式に限る (名前は **scope chain** で解決し、局所束縛・`global`/`nonlocal` は module へ fallback しない)、規則 2 = 実行呼出し (`.execute(`/`.executemany(` と修飾名 6 関数の statement 引数) に f-string・`%`・`+`・`.format()` を直接置かない。加えて `psycopg.sql` の import 形と構築子別名を pin (注釈と `isinstance` の型引数は除外 — 除外なしでは偽陽性 35 件)。畳めない既存は許可表 **3 件** (`IfExp` 1、dict 内包の for-target 2) を `old` の完全一致 + 違反集合との等価で pin。観測 6 関数 42/42/17/9/9/37、`sql.SQL(...)` 173/141。変異 28 件 (1 件 expect green)、**コードレビュー 4 巡** |
| R-77 (B) 読み手 0 の判定が文字列注釈を見落とす | main `882963c`。**監督裁定: 恒久のテストにする** (Z5-13 の「恒久にしない」は WP-5 の範囲縮小下の判断)。新規 `tools/tests/test_src_import_readers.py` (node id 3) が全 import 名の読み手 (`ast.Name` Load・`__all__`・文字列注釈、入れ子を含み `Literal`/`Annotated` の slice は除く) を数え、読み手 0 は理由付き許可表 41 行と集合として等価であることを assert する (pin 一覧は `test_src_import_cycles.py` と byte 同一)。実測 import 名 1164 / 読み手 0 = 41 (R-94 の後 39)。変異 14 件、コードレビュー 3 巡。残余 **R-94 を起票**。**記録の抜け**: コード commit `239c944` は指示書 §6 と台帳の閉止追記を欠いたまま merge され、docs commit `ec054c3` で補った |
| R-92 + R-93 + R-73 (C) 文言の陳腐化 3 件 | main `adea2b5`。**1 つの変更セット** (WP 間の触るファイルの重なり 0)。(1) F-12 の案内文が両 peer で `--lock-timeout` を名指す (逐語 pin は起草時の 2 件ではなく **5 件**、同型 helper `_f12_message` は `_ISOMORPHIC_TARGETS` に載る。設計 `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §3.8 は v1.5 の訂正註)。(2) `0005` のヘッダは数値だけでなく**段落全体を書き直した** (同 role で 2 pool、上限は `0013` が引き上げる。SQL 本文は不変)。(3) R-73 のコメントは時点つきの実測を現在形の測り方に置き換えた (`MAX_BLOCK_LENGTH = 15200` 不変)。変異 3 件 + WP-2/WP-3 は監査照合。コードレビュー 1 (中 4・低 2) |
| R-94 (B) 読み手 0 で記録も無い import 2 件 | main `7452b5b`。2 件とも**削った** (`structured.py` の `Decimal` は行ごと、`control_http.py` の `_CredentialMissing` は `from .http import (…)` の 1 名)。§1.5 の 40a を準用し、削除前後で r2db `1373` / MitateDB `1422` / `tools/tests` `585` が同数。許可表は 39 行、`_NO_RECORD_KEYS` は空 (機構は残す)。変異 5 件、コードレビュー 1。範囲外の指摘から **R-95 を起票** |

- 作業指示書: `docs/work-orders/WORK_ORDER_R76_SRC_IMPORT_CYCLES_V1.md` §6、`docs/work-orders/WORK_ORDER_R75_SQL_STATEMENT_SAFETY_SCAN_V1.md` §6、`docs/work-orders/WORK_ORDER_R77_SRC_IMPORT_READERS_V1.md` §6、`docs/work-orders/WORK_ORDER_R92_R93_R73_DOC_STALENESS_V1.md` §6、`docs/work-orders/WORK_ORDER_R94_UNREAD_IMPORTS_V1.md` §4。いずれも完了ゲートは `3844 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0、root collection の増分 0。
- **起票**: R-94 (R-77 の許可表の「記録なし」2 件の処置。同じチャットで閉じた)、R-95 (`conformance-tests/test_c20_constraint_declaration_agreement.py:154` と `conformance-tests/test_c22_dry_run_and_plan.py:186` の docstring が `r2db-api/src/r2db_api/structured.py:1583` を引くが現物は `:1821`。R-88 と同型の穴が conformance の docstring にもある)。

## 3. 次の一手

1. **R-74** と **R-88** の完了 (監督が本書の §6・§7 に追記する)。
2. その後 **R-72**、**R-87**、**R-89**、**R-90**、**R-91**、**R-95**、**R-78〜R-86** (順序と保留は台帳の各行)。R-89 には R-67・R-69 の材料が乗っている。
3. fold は `tools/dev/fold.py --min-age-hours 0 --apply` で回す。その前に**他チャットの worktree (`r22-status`) と進行中の worktree を `git worktree lock` で保護する** (既定の age 24h では当日の worktree が skip されるので `--min-age-hours 0` が要り、そのままでは他チャットの分まで対象に入る)。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(o) R-88 の Class D の決定の事後報告。** 位置参照 (`file:line`) を現物に解決する検査の追加と、`security/CONTROL_MAPPING.md` の偽の指し先 3 主張行の訂正 (版 2.21) は、依頼者指示 2026-09-19 の委任の下で監督が下す。R-88 を閉じた時点で本書の §7 に要点を書く。
- **(p) R-77 の裁定の事後報告。** 「読み手 0 の検査を恒久のテストにする」は、R-37 WP-5 当時の Z5-13 (「恒久にしない」= scratchpad の一回限りのスクリプトで手当てする) を、**WP-5 の範囲縮小の下での判断として覆した**ものである。覆した根拠と日付は台帳 R-77 行と作業指示書 §2 に残してある。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

- **Bash の複数コマンドを改行で並べると、前段の python の assert が失敗しても後段の `finalize.py` が走る。** 記録の編集と finalize は `&&` で繋ぐ (R-77 で記録を欠いた merge が起き、docs commit で補った)。
- **`tools/dev/mutate.py` は新規ファイルの作成を扱えない。** 「新しい module が走査対象に入る」型の完了条件は spec に載せず、`tools/dev/pt.py` で手動実施し (probe を置く → 赤 → 削除 → 緑 → `git status --short` クリーン)、コードレビューが再現する (R-75 の完了条件 12)。
- **実装担当が報告する `tools/tests` の集計行は、最終のファイルより古いことがある。** 監査はログの時刻と最終の木を突き合わせる (R-76)。
- **`tools/change_class.py` は未追跡だけの変更セットでは `unknown` を返す。** 新規ファイルを足す WP ではパスを明示して渡す。
- **監督の事前集計は、実装担当の着手時の再照合で覆ることがある** (R-77: 39 件 / 8 件 → 27+1 件 / 9 件)。指示書に「**現物が正本**」と書き、食い違ったら止まって報告する手順を残す。
- **数値だけを直すと、周囲の文が現物と矛盾する** (R-93 の `0005` ヘッダ: 「1 process 1 pool」「CONNECTION LIMIT 10 で足りる」が偽になっていた)。陳腐化の訂正は**段落単位で現物照合**する。
- **逐語 pin は起票時の想定より多い** (R-92: 2 件 → 5 件)。文字列リテラルを変える WP は、着手時に全テストを `grep` して pin を数え直す。
- **`fold.py` は既定 24h 未満の worktree を「最近」として skip する。** 当日中に畳むときは `--min-age-hours 0` と、他チャット・進行中の worktree の `git worktree lock` を組で使う。
- **姉妹テストの間で pin を import しない。** 読み手検査 (R-77) と循環検査 (R-76) は走査集合の pin 一覧を byte 同一で**複製**する (`tools/tests` 同士の import は依存を作る)。

## 6. 追記 — 同じチャットで R-74 を閉じた (2026-09-23)

§1〜§5 は書いた時点のまま残す。この節が上書きするのは次の点だけである。

- **R-74 を閉じた。** ローカル main `7d6805a` (コミット `2365955`)。`conformance-tests/test_conditions_register.py` に自前の索引と検査 15 本 (5 形の解決、床 5 本、対象定数 pin、全行走査、allowlist、索引の非空、backtick 外の `test_` token 0)。現物の未解決 0 (`CONDITIONS.md` は不変)。設計レビュー 1 (高 3・中 6・低 4、全件反映 — R-64 からの import 廃止、node id 列挙の pt、5 本の床、対象定数 pin)、コードレビュー 2 巡 (中 2・低 8、全件閉)、受け入れ監査 1 (未充足 0)、変異 22 件。完了ゲート (最終の木) `3859 passed, 2 subtests passed in 370.61s (0:06:10)`、`judge=PASS`、実行クラスタ差分 0 (3844 + 15)。Class C。台帳 **v1.94**。作業指示書 `docs/work-orders/WORK_ORDER_R74_CONDITIONS_TEST_NAME_RESOLUTION_V1.md` §5。
- **`COLLECTION_FLOOR` (3326) は未更新** — 下限であり、更新はフェーズ完了時の監督の仕事 (`conformance-tests/README.md`)。
- 進行中は R-88 だけ (worktree `r88`)。閉じたら §7 に追記する。
- 教訓: **register ファイルを単独で pytest に掛けると `_collect_marked_condition_ids` の marker 3 本が仕様どおり赤になる** — 新検査は node id を列挙して回し、報告前に `conformance-tests/` 全体を 1 回。**「索引が空でない」の検査は dict の truthy では固定できない** (空集合を値に持つ dict は真) — 名前の総数で判定する。**変異が赤にならないと実測で分かったら、変異を広げて性質を固定する** (M12)。

## 7. 追記 — 同じチャットで R-88 を閉じた (2026-09-23)

- **R-88 を閉じた (Class D、事後報告)。** ローカル main `279b41a` (コミット `cdcdc05`)。`conformance-tests/test_control_mapping_register.py` に位置参照の検査 (node id 15): `security/CONTROL_MAPPING.md` の 6 形の `file:line` 参照を 4 経路で解決し行番号の範囲を検査、許可表 2 行 (他 peer の裸ファイル名、集合 pin)、床 10 本、3 限界 (範囲内の別箇所指し / basename 解決は directory を固定しない / 同一行に path の無い `:line`) を docstring に開示。**CONTROL_MAPPING は版 2.21**: SI-08 の主張行 3 本 (`:619`・`:667`・`:668`) を Update convention で訂正 (腐り 5 件 + 範囲内の別箇所 4 件。旧文は HISTORY へ逐語、`check_control_mapping_split.py --base adea2b5` は `missing=3 added=3 moved=0`)。`:667` の関数名は現行の `build_capabilities_document` に改めた。設計レビュー 1 (高 3・中 6・低 4)、コードレビュー 2 巡、受け入れ監査 1、変異 28 件、完了ゲート `3874 passed, 2 subtests passed`、`judge=PASS`。台帳 **v1.95**。作業指示書 `docs/work-orders/WORK_ORDER_R88_CONTROL_MAPPING_POSITION_REFS_V1.md` §6。
- **依頼者への事後報告 (§4 (o) の具体)**: 決定 = 検査の追加 (D-1〜D-9)、3 主張行の訂正、版数行 2.21 の確定文 (指示書 §6.1 監督裁定 1)。いずれも 2026-09-19 の委任の下で監督が下した。
- 教訓: **`mutate.py` の 1 entry に fixture と現物のテストを並べると `-x` で現物側が走らない** — 現物依存を示す変異は entry を分ける (M5b/M12b)。**Version 行の因果 (「R-37 の分割で腐った」) は `git log -S` で確かめてから書く** — 1 件は R-62 で path 無しのまま追加されたものだった。
- 進行中は R-89 だけ (worktree `r89`、Class B、来歴検査 §4.1 (2) の鍵 — `replace` 区間の対付けと本文 byte 一致ゲート)。閉じたら §8 に追記する。
