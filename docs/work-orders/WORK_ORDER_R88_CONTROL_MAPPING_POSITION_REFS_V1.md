# 作業指示書 — R-88 `security/CONTROL_MAPPING.md` の `file:line` 位置参照を現物に解決する機械検査

## 0. 版数・位置づけ

- **v1.0 (2026-09-22)。** 基点 main `adea2b5`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-88。変更クラスは **Class D** (`security/CONTROL_MAPPING.md` の訂正 = D と `conformance-tests/` = C に跨るので重い方)。契約 (`spec/`) は触らない。D が求める依頼者裁定は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) の下で監督が下し、事後確認を引き継ぎ書で伺う。版付きの security-contract 決定は `security/CONTROL_MAPPING.md` の版 **2.20 → 2.21**。
- 設計文書は起こさず、決定は本書 §1 (と WP の §2) に置く (R-64・R-62 の先例)。設計レビュー 1 回を本書に対して行う。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 問題と決定 (監督確定)

**問題**: R-64 の検査は `security/CONTROL_MAPPING.md` が引く**テスト名**しか見ない。主張が証拠として引く `file:line` の**位置参照**は、path が実在するかも、行番号がそのファイルの範囲に収まるかも検査されない。R-37 の module 分割の後、現物で腐った参照が在る (実測、基点 `adea2b5`):

- `security/CONTROL_MAPPING.md`:667 の `cell.py:3811`・`:4051`・`:4055`、同 `:668` の `cell.py:4044` — いずれも `MitateDB-api/src/mitatedb_api/cell.py` (現行 3,757 行) を超える。宣言は `capabilities_document.py` に移っている。
- 同 `:667` の `cell.py:744`・`:775-782`・`:785-794` — 行数の範囲内だが現行の位置と合わない。現行では `_LimitStateHolder` は `MitateDB-api/src/mitatedb_api/cell.py:305` (class)、`acquire_rate` は `:336`、`concurrency_slot` は `:346` である (設計レビュー 1 の実測)。
- 同 `:668` の `backend_postgres.py:1658-1661` — 範囲内だが、主張の述べる `SET LOCAL statement_timeout` は現行では `:1496-1498` である (実装担当が再照合する)。範囲内の指し先違いは機械では検出しない (D-9)。
- 同 `:619` の `` `:803-819` `` — 同じ行に path が無く、どのファイルの行か文面から決まらない。

**決定**:

- **D-1 (置き場所)。** 検査は `conformance-tests/test_control_mapping_register.py` に足す (`CONTROL_MAPPING.md` の検査はこのファイルに集める。R-64 と同じ)。R-64 のテスト名解決の関数 (`_extract_bullet_references`・`_build_def_index`・`_resolve_*`) は **import も改変もしない** — 位置参照のための抽出・解決関数を新規に足す。R-64 の定数 (`TEST_NAME_RESOLUTION_TARGET_PATH` ほか) も触らない。
- **D-2 (対象と走査)。** 対象は `security/CONTROL_MAPPING.md` 1 本で、**既存の定数 `CONTROL_MAPPING_PATH` を使う** (`security/*.md` の glob にしない。`security/CONTROL_MAPPING_HISTORY.md` は逐語の旧文の保管場所で、**腐った参照を逐語で持つのが正しい**ので対象外)。走査は R-64 §6.1 の形と同じ: SI 節の中は `- ` の bullet 行 (peer は囲む subsection)、SI 節の外 (preamble・`## CCR-14`・`## Rule`) は非空の全行 (peer 無し)。
- **D-3 (参照の形と抽出)。** 次の形を位置参照として拾う。
  - (a) `` `path:line` ``、(b) `` `path:line-line` `` (colon と行番号が backtick の**中**)。
  - (a') `` `path`:line `` / `` `path`:line-line `` (colon と行番号が backtick の**外**。現物 2 件、`:148`・`:175`)。検査は (a)/(b) と同じである。
  - (c) **同一行の直前の backtick path を引き継ぐ** `:NNN` / `:NNN-NNN` (**backtick の内外を問わない**。`(:377, :398, :424, …)` の列挙形を含む。現物 12 件 — `:160` と `:192` の R-54 evidence boundary の 6 件ずつ)。carry-forward は**同一行内**に限る。
  - (d) `` `path` `` だけ (行番号無し。存在だけ検査)。
  - (e) `` `NNNN`:line `` / `` `NNNN`:line-line `` の短い数字ラベル (現物 4 件、`:149`・`:150`・`:177`・`:178` の `` `0004` ``)。**囲む peer の `migrations/` で `NNNN_*.sql` に一意に解決**し、行番号を検査する。一意でなければ `ambiguous`、0 件なら `file not found`。
  - `path` は拡張子ホワイトリスト (`.py`・`.sql`・`.md`・`.sh`・`.yml`・`.yaml`・`.toml`・`.txt`・`.json`・`.ini`) を持つものだけを path とみなす。**照合は大小を区別する** (`psycopg.sql.SQL`・`sql.SQL` は対象外)。これは `audit.fields`・`AuthContext.application_id`・`psycopg.sql.Composed` のようなドット付きの識別子を除くためである。
  - `path.py::test_name` の形 (テスト node id) は位置参照ではなく R-64 の検査の対象であり、本検査は拾わない。
- **D-4 (解決)。** 順に試す。
  - (i) repository ルートからの相対 path として実在すれば解決。
  - (i') 実在しなければ、**本文書の兄弟** (`security/` を前置) で実在すれば解決 (preamble の `` `CONTROL_MAPPING_HISTORY.md` `` 4 件がこの形)。
  - (ii) それでも無ければ、囲む subsection の peer (`### r2db-api` / `### MitateDB-api`) の directory を前置して実在すれば解決 (peer 省略形。現物 6 件)。
  - (iii) それでも無ければ basename を探す。**探索範囲は「囲む peer の dir + 共有 dir」**とする (R-64 の `_PEER_SCOPED_DIR_KEYS` と同じ考え方): 当該 peer の `src/<pkg>/`・`migrations/`・`docs/`・`tests/`・`deploy/`・`config/`・`docker/` と、共有の `conformance-tests/`・`tools/`・`security/`・`spec/`・repository 直下の `docs/`。peer の無い箇所 (preamble・`Common`) は両 peer + 共有 dir の全体。その範囲で**一意なら**解決、複数なら `ambiguous`、0 なら `file not found`。
  - (iv) 行番号は `1 <= line <= そのファイルの行数`、範囲は `start <= end` かつ `end` も範囲内。`.md`・`.sql` も同じ規則で行数を見る。
- **D-5 (明示許可表)。** 機械的に解決できないが正当な参照は、**理由付きの許可表**に置いて通す。表の引き方は `CONTROL_MAPPING.md` の行番号ではなく **(参照文字列, 囲む SI, 囲む peer)** とする (行番号は編集で動くため)。表は**集合として pin する**: 表の行が 1 つ欠けても赤、**今は解決するようになった参照が表に残っていても (死んだ許可行) 赤**。
  - 現物では 2 件だけである (比較目的で**相手 peer** のファイルを裸の名前で引くもの): `:618` (SI-08 / r2db-api) の `` `0013_role_statement_timeouts.sql` ``、`:729` (SI-08 / MitateDB-api) の `` `0013_role_connection_limits.sql` ``。`:808` の `` `test_c06_destructive_confirmation.py` `` は D-4 (iii) の共有 dir で解決するので許可表に入れない。
  - 末尾の成分が拡張子と同綴りの識別子 (path でないのに (d) として拾われるもの) が将来現れた場合も、**この許可表が受け皿**である (ホワイトリストを緩めない)。
  - `:619` の `` `:803-819` `` は許可表に置かず、WP-2 で path を書き足して形 (c) で解決させる (D-6・§3.1)。
- **D-6 (腐りの訂正、Class D)。** **`:667` と `:668` の bullet に在る位置参照を全数現物照合し**、現行と合わないものを Update convention (preamble `:11-23`) で直す。加えて `:619` の path を補う。現行行を in place で書き換え、旧文を逐語で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` へ移す。版数は **2.20 → 2.21**。
  - 確定している訂正: `cell.py:744`・`:775-782`・`:785-794` → `_LimitStateHolder` は `MitateDB-api/src/mitatedb_api/cell.py:305` (class)、`acquire_rate` は `:336`、`concurrency_slot` は `:346`。
  - 実装担当が現物で特定する訂正: `cell.py:3811`・`:4051`・`:4055`・`cell.py:4044` → 現行の `capabilities_document.py` (または `cell.py`) の該当行。`backend_postgres.py:1658-1661` → `SET LOCAL statement_timeout` の現行の行 (設計レビュー 1 の実測は `:1496-1498`。再照合する)。
  - 訂正の指す先の妥当性 (その行の中身が主張と合うこと) は**実装担当が各件の `file:line` の周辺 ±10 行を報告に貼り**、コードレビューが照合する。
- **D-7 (床・空振り禁止)。** 現物の文書に対して、(1) 形 (a)(a')(b)(c)(d)(e) ごとの観測件数がそれぞれ下限以上であること、(2) 解決の経路 (i)(i')(ii)(iii) ごとの観測件数がそれぞれ下限以上であることを assert する (`OPERATING_CONDITIONS.md` §1.5 の 32)。下限は実測から余裕を引いた定数とし、由来 (実測日・基点・実測値) をコメントに書く (R-64 D-4 の形)。**参考実測** (設計レビュー 1、基点 `adea2b5`、参照 183 件): 形は (a) 3 / (a') 2 / (b) 2 / (c) 5 + 列挙形 12 / (d) 167 / (e) 4、経路は (i) 97 / (i') 4 / (ii) 6 / (iii) 68。**参考値であり、実装担当が自分の実装で再測した値を使う**。
- **D-8 (失敗の形)。** 1 件 1 行で全件出す。折り畳まない。形: `CONTROL_MAPPING.md:<行>: <参照> (<file not found | ambiguous | line N beyond EOF M | bad range>)`。
- **D-9 (限界)。** (1) 行数の範囲内で**別の箇所**を指す腐りは機械では検出しない (今日の `cell.py:744` 系・`backend_postgres.py:1658-1661` がその型で、人が読んで見つけた)。(2) **経路 (iii) で解決した参照 (実測 68 件) は directory を固定しない** — basename が repository のどこかに生き残り行番号が範囲内であれば、module がほかの directory へ移っても検出しない。(3) 同一行に path の無い `:line` は解決しない (path を足す訂正で運用する)。この 3 点を検査の docstring と台帳 R-88 行の両方に現在形で書く。

**却下した代替案**: (1) R-64 の索引の流用 — あれは 4 つの test directory 専用で `src/`・`migrations/`・`docs/` を索引しないので、位置参照の解決には使えない。(2) 範囲内の指し先違いの機械検出 — 主張語が ±N 行に在るかのヒューリスティックは偽陽性・偽陰性が多く、検査にしない (起草時の試行は 11 件中 1 件しか挙げず、確定した腐り 3 件を落とした)。(3) `:line` の carry-forward を複数行に広げる — どの path を継ぐかが曖昧になる (R-64 が「直前の path」の追跡を却下したのと同じ理由)。(4) 腐りを許可表で通す — 腐りは直す。

**未確定で依頼者判断待ち**: 無し (Class D、事後報告)。

**設計レビュー 1 の反映 (2026-09-22)**: F-1〜F-12 を**全件採用**し、未コミットの起草版なので本文を直した (訂正註ではない)。F-1 = D-6 を `:667`・`:668` の bullet の位置参照の**全数照合**に広げ、範囲内で指し先の違う 3 件を腐りに加えた (起草版は「4 件 + 疑い 1 件」と述べていた)。F-2 = D-4 (iii) の範囲を「peer の dir + 共有 dir」に直した (起草版の集合では `:808` が偽の赤になった)。F-3 = 訂正対象は主張行 3 本、完了条件と履歴の題をそれに合わせた。F-4 = 床の変異を形ごと・経路ごとに分け、対象ファイルを広げる変異 (M13) を足した。F-5 = 形 (c) を backtick の外の列挙形まで広げた (起草版は 12 件を落としていた)。F-6 = D-9 に経路 (iii) の限界を足した。F-7 = 参考値を再実測に直した。F-8 = 拡張子照合の大小区別。F-9 = 許可表が受け皿であることを明記。F-10 = register テストの一覧は現物に無い (grep 0 件)。F-11 = `:619` の訂正の確定文。F-12 = 変異表に無変異の基準行。

## 2. WP-1 — 位置参照の検査を足す

### 2.1 タスク

- `conformance-tests/test_control_mapping_register.py` に D-2〜D-9 の検査を足す (D-1: 新規の関数・定数。R-64 の資産は触らない)。テストは少なくとも: (1) 現物の全参照が解決する、(2) 合成 fixture で「同一行に path の無い `:line` は未解決」「複数の候補に当たる basename は `ambiguous`」「架空 path は `file not found`」「逆順の範囲は `bad range`」が検出される、(3) 形と経路の床 (D-7)、(4) 許可表の集合 pin (D-5)、(5) 対象が `CONTROL_MAPPING.md` 1 本であること (D-2)。
- 検査を現行の `security/CONTROL_MAPPING.md` に掛け、赤になる参照の**全件**を報告する。
- コメント・docstring は `tools/check_comment_provenance.py` の規則に掛かる。`--register` の緑を道具そのもので確かめる (`--base` はコードを足す変更では構造上赤になる。R-64 §6.1)。
- 経緯トークンを tests に足さない (docstring に `R-88:` と文書パスを書くのは可)。

### 2.2 触ってよいパス

- `conformance-tests/test_control_mapping_register.py`。
- `conformance-tests/COLLECTION_FLOOR` は触らない (監督が完了ゲートで更新する)。
- `conformance-tests/README.md` / `CONDITIONS.md` に register テストの一覧は**無い** (設計レビュー 1 の grep で 0 件)。新設しない。

### 2.3 完了条件

1. **(a) の解決**: `` `path:line` `` が実在の path と範囲内の行に解決する。
2. **(a') backtick の外の colon**: `` `path`:line `` / `` `path`:line-line `` も (a)/(b) と同じ検査に掛かる。
3. **(b) の範囲**: `end` が範囲内で `start <= end` である。
4. **(c) の carry-forward**: 同一行の直前の backtick path を引き継ぐ `:NNN` / `:NNN-NNN` を backtick の内外を問わず拾い、**前の行の path は継がない**。
5. **(d) の実在**: 行番号の無い `` `path` `` も存在を検査する。
6. **(e) の短い数字ラベル**: 囲む peer の `migrations/` で `NNNN_*.sql` に一意に解決し、行番号を検査する。
7. **(i') 兄弟の解決**: `security/` を前置して解決する経路が在る。
8. **(ii) peer 省略形**: peer の directory を前置して解決する経路が在る。
9. **(iii) basename の解決範囲**: 「囲む peer の dir + 共有 dir」で一意なときだけ解決する (D-4 (iii))。
10. **許可表の集合 pin** (D-5): 表の行の欠落も、死んだ許可行も赤。
11. **拡張子ホワイトリスト** (D-3): 大小を区別し、ドット付き識別子を path として拾わない。
12. **床** (D-7): 形 6 種・経路 4 種のそれぞれに下限が在る。
13. **対象の固定** (D-2): 検査の対象は `CONTROL_MAPPING.md` 1 本で、`CONTROL_MAPPING_HISTORY.md` を含まない。
14. **(監査照合)** 失敗メッセージが D-8 の形で 1 件 1 行・全件出る。赤の実行の出力をそのまま報告に貼る。
15. **(監査照合)** 現行文書に対して赤になる参照の全件を報告する。**D-6 の訂正対象と D-5 の許可表の 2 件以外が出たら、直さず監督の裁定を待つ** (監督の再実測が正本)。
16. **(監査照合)** D-9 の 3 つの限界が検査の docstring に現在形で在る (台帳 R-88 行への同じ記載は監督が統合時に行い、§6 で照合する)。
17. **(監査照合)** 新しい検査以外の register テストが緑、`tools/tests -k control_mapping` が緑、`tools/check_comment_provenance.py --register`・`tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。各コマンドと集計行を報告に逐語で貼る。
18. §2.4 の表に対応の無い行が無い。

### 2.4 完了条件 → 変異

現物に掛ける変異は、現行文書が WP-2 の訂正まで赤なので **WP-2 の後にまとめて 1 回** `tools/dev/mutate.py` で実行してよい。fixture に掛かる変異 (M3・M6) は WP-1 の時点で実行できる。

| 完了条件 | 変異 | 期待 |
|---|---|---|
| (基準) | M0: 変異なし (訂正後の木そのまま) | `expect: green` |
| 1 | M1: `:667`・`:668` の外の、照合済みの位置参照 1 件 (例 `:148` の `` `r2db-api/migrations/0004_deprovision_application.sql`:140-150 ``) の行番号を `99999` にする | 現物の検査が赤 |
| 2 | M10: (a') の抽出 (backtick の外の colon) を外す | 現物の検査が赤 (`:148`・`:175` が無検査になり (a') の床が赤) |
| 3 | M2a: `:618` の `` `…/postgres.py:2294-2308` `` の `end` を EOF 超にする / M2b: 同じ参照を `2308-2294` (逆順) にする | それぞれ `line N beyond EOF M` / `bad range` で赤 |
| 4 | M3: 解決器の carry-forward を行跨ぎに広げる | 「同一行に path の無い `:line` は未解決」の fixture が赤 |
| 5 | M4: 現物の `` `path` `` 1 件 (行番号を持たないもの) を架空の path にする | 現物の検査が赤 |
| 6 | M11: (e) の抽出 (短い数字ラベル) を外す | 現物の検査が赤 (`:149`・`:150`・`:177`・`:178` が無検査になり (e) の床が赤) |
| 7 | M12: 解決から (i') の `security/` 前置を外す | 現物の 4 件が `file not found` で赤 |
| 8 | M5: 解決から (ii) の peer 前置を外す | 現物の 6 件が `file not found` で赤 |
| 9 | M6: basename の一意性を見ず最初の候補を採る | 「複数の候補に当たる basename は `ambiguous`」の fixture が赤 |
| 10 | M7a: 許可表から 1 行外す / M7b: 許可表に架空の参照行を足す | M7a は現物の検査が赤、M7b は死んだ許可行の検査が赤 |
| 11 | M8: 拡張子ホワイトリストを外し、ドット付き識別子も path として拾う形にする | 現物の検査が `file not found` で赤 |
| 12 | M9a〜M9f: 形 (a)(a')(b)(c)(d)(e) の床定数を 1 つずつ実測 +1 にする / M14a〜M14d: 経路 (i)(i')(ii)(iii) の床定数を 1 つずつ実測 +1 にする | それぞれ床のテストが赤 (10 entry) |
| 13 | M13: 対象を `CONTROL_MAPPING_HISTORY.md` まで広げる | 現物の検査が赤 (WP-2 の後、履歴は腐った参照を逐語で持つ) |
| 14〜17 | 監査照合 (逐語記録は §2.3 のとおり報告に貼る) | — |
| 18 | 本表そのもの | — |

### 2.5 道具の引数

- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r88 -- conformance-tests/test_control_mapping_register.py -q` (このファイルは単独で走る。`tools/tests` と**同じ呼び出しに混ぜない** — 混ぜると WP と無関係の teardown の error が 1 件出る。`WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md` §6 の訂正註)。
- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r88 -- tools/tests -q -k control_mapping` (別呼び出し)。
- 報告の前に `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r88 -- conformance-tests -q` を 1 回 (収集の増分を報告する)。
- `tools/dev/mutate.py "$SP/r88-mutations.json" -C .claude/worktrees/r88 --wait 1800`。
- 完了ゲート `tools/dev/gate.py -C .claude/worktrees/r88 --label r88` は**監督のみ**。実装担当は走らせない。

## 3. WP-2 — 位置参照の訂正・許可表・版数 2.21

WP-1 と**同じ変更セット・同じ worktree・同じ実装担当**で、WP-1 → WP-2 の順に行う (検査だけを入れると main が赤になる。R-64 D-6 と同じ)。並行 WP は無い。

### 3.1 タスク

- D-6 の全数照合を行い、主張行 **3 本** (`:619`・`:667`・`:668`) を in place で直す (行の他の部分は 1 字も変えない。置換はスクリプトで行う)。各件の指す先の `file:line` の周辺 ±10 行を報告に貼る。
- `:619` の訂正は確定文 — 同じ行の `` `:803-819` `` の**直前**に path を backtick 付きで書き足し、**形 (c) の carry-forward で解決する形**にする。解決後に指す先の確定文字列: `r2db-api/src/r2db_api/postgres.py:803-819` (書き足す path は `r2db-api/src/r2db_api/postgres.py`)。
- 許可表に D-5 の 2 件を理由付きで置く。
- 旧文 3 本は逐語・無編集で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` の節の末尾へ、次の確定した題を付けて移す (R-64 §3 の形)。
  - `:619`: `*r2db-api Control claim, the four client-reachable operations of `PostgresCell` and their `SET LOCAL` timeout bound, superseded 2026-09-22 (Version 2.21, R-88 -- the claim's position reference carried no path on its own line, so the lines it cited resolved to no file), verbatim:*`
  - `:667`: `*MitateDB-api Control claim, the application-plane `requests_per_minute`/`concurrency` bounds and their `limit_enforcement` declaration, superseded 2026-09-22 (Version 2.21, R-88 -- every position reference in this claim was stale after the R-37 module split: three cited lines past the end of the current `cell.py`, three more pointed at lines the split had moved), verbatim:*`
  - `:668`: `*MitateDB-api Control claim, `execution_ms` declared `reference_wall_clock` rather than `enforced`, superseded 2026-09-22 (Version 2.21, R-88 -- the cited `cell.py` line is past the end of the current file and the cited `backend_postgres.py` range is no longer the `SET LOCAL statement_timeout` conversion it names), verbatim:*`
- 版数行 (`security/CONTROL_MAPPING.md`:5) を **2.21** にする。実装担当は現行 2.20 の書き方と `WORK_ORDER_R71_MITATEDB_CATALOG_READ_CANCEL_MAPPING_V1.md` §4.2 の先例に沿って案 (位置参照の解決検査が入ったこと、その範囲と D-9 の限界、直した主張行 3 本) を報告に書き、**確定文は監督が統合前に確定する** (`OPERATING_CONDITIONS.md` §1.5 の 34・35)。`security/` へは監督の確定文ファイル `$SP/r88-final/` から逐語複製する。
- 最長ブロックが変わらなければ preamble の `Length cap measurement` の段は触らない。変われば実測して直す。

### 3.2 触ってよいパス

- `security/CONTROL_MAPPING.md`、`security/CONTROL_MAPPING_HISTORY.md`。

### 3.3 完了条件

19. WP-1 の検査が**現行の文書に対して緑**になる (許可表の 2 件を除いて未解決が 0)。
20. **(監査照合)** 旧文 **3 本**が `CONTROL_MAPPING_HISTORY.md` に逐語で在る (`git diff` で基点と byte 一致を確かめ、差分を報告に貼る)。`tools/check_control_mapping_split.py --base adea2b5 --expect "<実測した集計行。形は missing=3 added=3 moved=0 …>"` の**終了コード 0** (期待文字列は実装担当が実測して報告し、監督が §6 に pin する)。
21. **(監査照合)** `:667`・`:668` の bullet の位置参照を**全数**照合した記録 (各件の訂正後の `file:line` と周辺 ±10 行) を報告に貼る。
22. §3.4 の表に対応の無い行が無い。

### 3.4 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 19 | M0〜M14 (§2.4。訂正後の現物に掛ける) | M0 は `expect: green`、他は全件 `expect=red got=red` |
| 20 | 監査照合 (`git diff`、`check_control_mapping_split.py` の集計行と終了コードを逐語で報告) | — |
| 21 | 監査照合 (訂正後の `file:line` と ±10 行を逐語で報告) | — |
| 22 | 本表そのもの | — |

## 4. 範囲外 (起票のみ)

- 範囲内で別の箇所を指す腐りの機械検出、および経路 (iii) が directory を固定しない件 (D-9)。
- `conformance-tests/CONDITIONS.md`・`docs/` の位置参照への同型の検査。

## 5. レビューと受け入れ

- 設計レビュー 1 回 (本書 §1〜§2 に対して、WP-1 の着手前。**実施済み 2026-09-22**: F-1〜F-12 を全件採用して本文に反映した。反映の要約は §1 末尾)。
- コードレビュー 1 回 (WP-1 + WP-2 の後。D-6 の全数照合 (±10 行) の照合を含む)。
- 受け入れ監査 1 回。監督が完了ゲートの集計行・完了条件・監査のパケットを照合して判定する。
- Class D が求める依頼者裁定は 2026-09-19 の委任の下で監督が下す。統合後、引き継ぎ書で依頼者へ**事後報告**する。

## 6. 記録 (統合時に監督が埋める)

### 6.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-23)】完了条件 7〜9 の変異と、fix で増えた参照。** 経路 (ii)/(i') を外す変異 (M5/M12) は現物では経路 (iii) が黙って代替解決して赤にならず、fixture テスト 2 本に付け替えた上で、現物の経路の床 (M5b: (ii) 6 ≥ 5、M12b: (i') 4 ≥ 3) で現物依存を示した。形 (c) 16 → 18・経路 (iii) 67 → 69・総参照 195 → 197 の増分は `:667` の訂正で生じた `` `:240` ``・`` `:283` `` (fix 5 の隣接 colon の扱いは現物では 0 件。fixture + M16 で潜在ケースを固定)。
- **【監督裁定 1 (2026-09-23)】版数行 `:5` と `:667` の確定文** は `$SP/r88-return-1.md` の逐語 (版数行は R-37 起因の因果を書かず、検査の 3 限界を開示し、末尾は台帳参照; `:667` は現行の関数名 `build_capabilities_document` と `capabilities_document.py:23` / dict `:240` / entries `:283`・`:288`)。
- **【監督裁定 2】** 経路 (iii) が `rglob` で未追跡ファイルも見る点 (監査所見) は R-64 の索引と同じ性質で、fail-closed 側 (手元だけの参照は CI で赤) なので据え置き。

### 6.2 実施と受け入れ

- **差分**: `conformance-tests/test_control_mapping_register.py` (+13 → +15 node id、位置参照の検査: 6 形 (a)(a')(b)(c)(d)(e) の抽出、4 経路 (i)(i')(ii)(iii) の解決、行番号の範囲、許可表 2 行の集合 pin、床 10 本、D-9 の 3 限界を docstring に)、`security/CONTROL_MAPPING.md` (版 2.21、`:619` に path を書き足し、`:667`・`:668` の位置参照を現行に)、`security/CONTROL_MAPPING_HISTORY.md` (旧文 3 本を `## SI-08` へ逐語)。`tools/change_class.py` → `class=D`。
- **実測 (最終、main db92b5b の上)**: 位置参照 197 (a 3 / a' 2 / b 2 / c 18 / d 168 / e 4)、経路 i 112 / i' 4 / ii 6 / iii 69 (+ e-migration 4)、未解決 = 許可表 2 件 (`:618`・`:729` の他 peer の裸ファイル名) のみ、訂正前は + 腐り 5 件。`tools/check_control_mapping_split.py --base adea2b5 --expect "missing=3 added=3 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` 終了 0。全数照合: `postgres.py:803-819` (`PostgresCell.catalog`)、`cell.py:305/336/346`、`capabilities_document.py:23/240/283/288/270`、`backend_postgres.py:1496-1499`。
- **道具の出力行**: `pt: 58 passed` (単独ファイル)、`pt: 1062 passed` (`conformance-tests`、基点 adea2b5)。`mutate: 28 mutations, 28 as expected, restores verified 2/2 files (sha256 x2)` (M1〜M16、M5b/M12b、M9a〜f、M14a〜d)。M0 (無変異) = 単独 58 passed。`--register` OK 87/430、`check_doc_refs` 0、`public_value_scan` 0。
- **設計レビュー 1** (高 3・中 6・低 4、全件反映)、**コードレビュー 2 巡** (1 巡目 高 1・中 4・低 4 → 差し戻し 1; 2 巡目 全件閉、残り 1 件 = M5b/M12b の分割 → 反映)、**受け入れ監査 1** (未充足 3 = D-9 の docstring・絶対パスのメッセージ・`WP-2` トークン → 差し戻し 1 で解消; Class D の要点 = 旧文 3 本 byte 一致、新 `file:line` 8 件現物一致、Update convention 適合)。
- **完了ゲート** (監督単独、最終の木、`--label r88b`): `gate: 3874 passed, 2 subtests passed in 388.36s`、`judge=PASS`、実行クラスタ差分 0 (直前の main 3859 + 15)。
- **最終判定**: 受け入れ。Class D の決定 (検査の追加、3 主張行の訂正、版 2.21) は 2026-09-19 の委任の下で監督が下し、引き継ぎ書 §7 で依頼者へ事後報告する。台帳 R-88 を閉じる (v1.95)。
