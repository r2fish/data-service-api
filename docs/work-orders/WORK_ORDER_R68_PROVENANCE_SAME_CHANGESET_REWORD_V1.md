# 作業指示書 — R-68 `check_comment_provenance.py` が登録済みの塊を同じ変更セットで言い換えられない

## 0. 版数・位置づけ

- **v1.0 (2026-09-20)。** 基点 main `e7562d3`。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の R-68 (`RM`:469)。変更クラスは **Class B** (`tools/change_class.py` 実測: 8 パスで `class=B`、`docs/…` の 3 件が A、`tools/…` と `MitateDB-api/…` の 5 件が B)。契約 1.8.0 のまま、`spec/`・`conformance-tests/`・`security/`・migration の差分 0。新しい設計文書は起こさない。既存設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` は **v0.23 で追記済み** (§0 の版数行、§6 の 0j の行、§9.3)。形の先行は `docs/work-orders/WORK_ORDER_R63_PROVENANCE_NEW_SYMBOL_BLOCKS_V1.md`。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`、下請け Agent を使わない)。

## 1. 枠 (監督確定)

### 1.1 問題設定と守るべき条件

`tools/check_comment_provenance.py` の `check_provenance_semantics` (`:2532`) は、基点の塊が同じ CH-ID を持つとき再編集の経路 (`:2611` の `reedit_candidates`) を取り、段 A (`:2632`) で「基点の塊 `ob.retained_text` が受け皿 + **作業ツリーの**訂正記録を全部当てた基準から導けること」、段 B (`:2640`) で「新しい塊 `nb.retained_text` が `ob.retained_text` から許容操作で得られること」を見る。同じ変更セットで訂正記録を足して塊を言い換えると、段 A は基準が新文・基点の塊が旧文なので赤、段 B も言い換えが文の削除ではないので赤になる。**一度登録したコメントは、事実が変わっても削除でしか直せない。** 実例は `RM`:469 の R-68 行にある。

守る条件:

- (a) 訂正記録なしの言い換え、記録に無い文の追加、塊の移動・削除は今までどおり赤。
- (b) 基点 rev に既に在る訂正記録を、作業ツリーで書き換えたり消したりできない。
- (c) 訂正記録が保護参照を落とす経路を作らない (§9 0g の 5 の迂回を作らない)。
- (d) 初回の移動 (基点に CH-ID が無い) の経路、(1)・(3)・(4)・(5)、CH-ID の無い塊の列比較 (R-63)、`--register` の判定は変えない。

### 1.2 現行の実測 (2026-09-20、起草時。基点 `e7562d3` の実物を読んだ)

| # | 観測 | 出所 |
|---|---|---|
| (i) | 受け皿と訂正記録の読み口は**作業ツリーのファイル**しかない (`_companion_files` が `repo_root` 配下を `glob`、`_load_corrections_lookup` がそれを読む) | `tools/check_comment_provenance.py`:1938、:2089 |
| (ii) | `run_base` は基点 rev の側を `git show` (`_git_show`) と `git ls-tree` (`_tree_paths`) で読んでいる。基点 rev の受け皿を読む口は**無い**が、この 2 つで作れる | 同 :2195、:2213、:2746 |
| (iii) | 訂正は `_apply_corrections` が受け皿の平坦化後の原文へ**順に全部**当て、`old` がちょうど 1 回でなければ赤、保護参照を落とせば赤 | 同 :2155 |
| (iv) | 初回の移動の経路 (`:2684`) は、訂正を当てた基準と新しい塊を比べるので、同じ変更セットの訂正を通す。R-55 の CH-0538・CH-0539 の 2026-09-19 の訂正が書けたのはこのため | 同 :2684 |
| (v) | `MitateDB-api/tests` に CH-ID は 1 件も無く (`grep -c "CH-0"` = 0)、`--register` の走査対象は両 peer の `src/` だけである (`PEER_SRC_DIRS`、`_iter_peer_py_files`) | `tools/check_comment_provenance.py`:59、:2859 |

### 1.3 決定 (監督確定 F-1〜F-6)

- **F-1.** 段 A の基準は**基点 rev の受け皿の訂正記録**で作る (基点 rev の `docs/code-history/` を `git show` で読む)。基点にその受け皿ファイル、又はその CH-ID の節が無ければ、基点の訂正は 0 件として扱う。
- **F-2.** 訂正記録は追記のみ: 基点 rev のその CH-ID の訂正の列が、作業ツリーの列の**先頭部分列 (prefix、逐語一致)** でなければ赤。
- **F-3.** 段 B: 作業ツリーにだけ在る訂正 (pending = 列の残り) を順に `ob.retained_text` へ当てたものを基準にし、`nb.retained_text` がそこから許容操作 (既存の `_is_allowed_reduction`) で得られることを見る。pending の `old` が `ob.retained_text` に 0 回 (以前の削除で既に無い) なら無変更で進む。2 回以上は赤。1 回なら置換。
- **F-4.** 既存の検査は緩めない: 作業ツリーの全訂正を受け皿の原文へ順に当てる検査 (ちょうど 1 回、保護参照を減らさない = §9 0g の 2・5) は今のまま全 CH-ID に掛かる。pending が無い再編集は今と同じ判定。訂正記録なしの言い換え・既存の文の追加・移動は今までどおり赤。`nb` が空で塊を丸ごと移す分岐 (`:2648`) の保護参照の検査は、pending を当てた後の文に掛ける。
- **F-5.** `--register` の形式検査は変えない。事実の照合は今までどおり独立レビュー (§9 0g の 7)。
- **F-6.** 設計は `docs/design/CODE_COMMENT_PROVENANCE_V1.md` v0.23 の §9.3 (変更セット 0j)・§6 の 0j の行・§0 の版数行に置いた。既存の文は書き換えない。

### 1.4 却下した代替案

- **(a) 段 B の基準を、受け皿の全訂正を当てた基準からの導出に替える** — 以前の削除で消した文の復活を許すので採らない。
- **(b) 当てる訂正の数 k を探索する (ある先頭部分列で導ければ通す)** — 基点 rev の記録で k が一意に定まるので探索しない。

### 1.5 最初の適用 (監督確定 F-7・F-8)

- **F-7.** `MitateDB-api/src/mitatedb_api/ops.py` の CH-0538 (節見出しコメント、`:2623-2630`) と CH-0539 (`cmd_apply_platform_migration` の docstring、`:2818-2825`) の第 1 文を列の形に直す。受け皿 `docs/code-history/MitateDB-api/ops.md` の CH-0538 節 (`:611`) と CH-0539 節 (`:641`) に `### correction: 2026-09-20` を追記する (`old` は平坦化後の形。既存の塊と 2026-09-19 の訂正は書き換えない)。`MitateDB-api/tests/test_ops_help_text.py` の `_SECTION_HEADING_FIRST_LINE` (`:120`) ほか古い文の pin を同じ変更セットで動かす。
  - **新文 (監督確定。言い換えない。§1.5 の 35・36)**:
    - コメント: ``apply-platform-migration` -- applies a run of one or more platform migration files (never a per-application upgrade, never the bootstrap-only 0001/0002) a second (or later) time against a running cluster.`
    - docstring: `Applies a run of one or more platform migration files a second (or later) time against a running cluster.`
    - どちらも第 2 文以降 (`Against production, run it only through the runbook's gated procedure (docs/cloud-run-cloud-sql.md section 10).`、docstring の `DSN comes from …` の文) は 1 字も変えない。help・runbook が持つ「in migration order」は**入れない** (§1.6 の J-2)。
  - `MitateDB-api/tests/test_ops_apply_platform_migration.py`:2 の module docstring は **CH-ID を持たない** (§1.2 (v) の実測)。受け皿への記録は要らず、同じ変更セットで直接直す。
- **F-8.** (§1.6 の J-5 でこのまま。) 行数が変わるので、`ops.py` の行番号 pin は実測で更新する (できれば行数を変えない折り返しにする)。起草時の実測では `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` の allowlist に `ops.py` の行番号は 1 件も無い (`grep '"ops\.py", *[0-9]'` = 0 件)。実測で動く pin が出たら、その pin を §3 に逐語で残す。

### 1.6 監督裁定 (2026-09-20、起草時の報告への回答)

- **J-1.** 受け皿と訂正記録の loader (`_load_companion_lookup`・`_load_corrections_lookup`) に **rev を指定して git から読む口**を足す。`check_provenance_semantics` には基点側の訂正記録を渡す引数を足し、**省略時は「pending 無し」**(今と同じ判定) とする。`run_base` は基点 rev の記録を渡す。`tools/tests/test_comment_provenance.py` の rev-vs-itself のガードテスト (`_check_rev_pair` を HEAD の blob どうしで呼ぶもの) は、受け皿・訂正記録も**同じ rev (HEAD) から読む**形に直す — ソースと記録を同じスナップショットで揃え、作業ツリーの未コミットの状態に依らないという同テスト自身の趣旨に合わせる。これにより「訂正を足した変更セットはコミット前に `tools/tests` が赤」という現行の性質も無くなる。作業ツリーの記録の**形式**は今までどおり `--register` が、**遷移** (F-2) は `--base` が検査する。完了条件と変異を 1 組足す (§2.2 の 14、§2.3 の M14)。
- **J-2.** F-7 の新文に「in migration order」は入れない。新文は §1.5 の案のままとする。
- **J-3.** §9e (折返しの壊れ) と `#:` の検査は変えない。§2.2 の 17 でこれらが発火したら、実装担当は作業を止めて報告する (自分で判定を緩めない。§1.5 の 37)。
- **J-4.** R-57 設計メモ `docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md`:167、:253 の残件行への追記は、監督が記録のコミットで行う。本書の範囲外のままとする。
- **J-5.** F-8 は「動く pin が出たら実測で更新し報告」のままとする。

**設計レビュー 1 の反映 (R1-1〜R1-13、2026-09-20。全件採用)**

- **R1-1.** 受け皿の原文 (fenced block) は今までどおり**作業ツリー**から読み、基点 rev から読むのは**訂正記録だけ**とする (原文まで基点から読むと、作業ツリーでの原文の書き換えを検査が見なくなる)。完了条件と変異を 1 組足す (§2.2 の 15、§2.3 の M15)。
- **R1-2.** F-3 の pending は、0g と同じく `_flatten` を掛けた本文へ順に当てる。完了条件 1・2 の基点の塊は**折返しのある塊**にする。
- **R1-3.** 完了条件と変異を 1 組足す: 以前の削除で消した文を pending の訂正で復活させたら赤 (§2.2 の 16、§2.3 の M16)。
- **R1-4.** 基点 rev でも作業ツリーと同じ集合 (その peer の `*.md` + `docs/code-history/pair.md`) を列挙する。完了条件と変異を 1 組足す (§2.2 の 17、§2.3 の M17)。
- **R1-5.** F-2 の一致は date・reason・old・new の**すべてを逐語で**比べる。
- **R1-6.** F-2 の効力は**再編集の経路で検査する CH-ID について**掛かる。並べ替えは同じ比較で落ちるので、完了条件 7 の fixture に並べ替えを含める。
- **R1-7.** 訂正を足した変更セットでは、**触った path に `--base` を掛けること**をレビュー手順とする (rev 同士のガードだけでは未コミットの訂正の遷移を見ない)。
- **R1-8.** 基点側の記録を渡されなければ、**作業ツリーの列をそのまま基点の列とみなす** (pending 0 件、今と同じ判定)。
- **R1-9.** §2.2 の 20 (`--base e7562d3`) の合格条件は**出力 0 行**に締める。F-7 はコメントと docstring しか触らず `ast_signature` が変わらないので、(1) も緑になるためである (本 WP に限る)。
- **R1-10.** 完了条件 10 の fixture は「1 つ目を置換すれば段 B が通る」形にし、2 回現れることだけが赤の理由になるようにする。
- **R1-11.** 設計文書内の `RM` は初出で展開する (設計 §0 の v0.23 行で対応済み)。
- **R1-12.** 却下した代替案 (a) の理由に 1 行補う (pending の `new` に旧文を埋め込む形の復活は §4.1 (5) と 0g の 7 の独立レビューで止める)。
- **R1-13.** `security/CONTROL_MAPPING_HISTORY.md` の旧文言 (凍結記録。`security/` は Class D) は触らない (§2.5)。

### 1.7 未確定

- 無し。

## 2. WP-1 — 再編集の経路に基点 rev の訂正記録を入れ、最初の適用を同じ変更セットで行う

WP は 1 本である (道具 + fixture + 最初の適用)。並行 WP は無い。

### 2.1 触ってよいパス

- `tools/check_comment_provenance.py` — 再編集の経路 (`:2611`〜`:2654`) の基準づくり、loader (`_load_companion_lookup` `:1979`、`_load_corrections_lookup` `:2089`) の rev の口 (段 A の**原文は作業ツリーのまま**で、rev から取るのは訂正記録だけ。rev の口を両方に足すのは rev 同士のガードのため。R1-1・J-1)、基点側の列挙も作業ツリーと同じ集合 (peer の `*.md` + `pair.md`。R1-4)、`check_provenance_semantics` (`:2532`) の基点側の訂正記録の引数、`run_base` (`:2746`) の受け渡しのみ (§1.6 の J-1)。初回の移動の経路 (`:2684` 以下)、(1)・(3)・(4)・(5)、CH-ID の無い塊の列比較 (`_plain_block_keys`)、`--register`、§9e と `#:` の検査 (`:2812` 以下。J-3) には触らない。
- `tools/tests/test_comment_provenance.py`
- `MitateDB-api/src/mitatedb_api/ops.py` — F-7 の 2 箇所の第 1 文のみ。
- `docs/code-history/MitateDB-api/ops.md` — CH-0538・CH-0539 節への訂正の追記のみ。
- `MitateDB-api/tests/test_ops_help_text.py`、`MitateDB-api/tests/test_ops_apply_platform_migration.py` — 古い文の pin と module docstring のみ。
- 実測で動く行番号 pin がある場合だけ、その pin (F-8)。
- 設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` は **触らない** (v0.23 で追記済み)。

### 2.2 完了条件

1〜13 の各テストは合成リポジトリを `--base` に掛け、観測対象 (緑なら「§4.1 (3) / (2) / §9f の行が 0」、赤ならその行の存在) を 1 件以上 assert する (空振り禁止、§1.5 の 32)。

| # | 形 | 求める結果 |
|---|---|---|
| 1 | 訂正記録つきのコメント塊の言い換え (基点で CH-ID を持つ塊、同じ変更セット)。基点の塊は**折返しのある塊**にする (R1-2) | 緑 |
| 2 | 訂正記録つきの docstring の言い換え。基点の塊は**折返しのある塊**にする (R1-2) | 緑 |
| 3 | pending の訂正が 2 本 (2 本目が 1 本目の結果に連鎖する) | 緑 |
| 4 | pending の `old` が基点の塊の本文に 0 回 (以前の削除で既に無い文の訂正) | 緑 (無変更で進む。F-3) |
| 5 | 基点 rev にその CH-ID の受け皿の節が無い (基点の訂正 0 件、全訂正が pending) | 緑 (F-1 の後段) |
| 6 | 訂正記録なしの言い換え | 赤 (`§4.1 (3)`)。条件 (a) |
| 7 | 基点 rev に在る訂正の `new` を作業ツリーで書き換える、又は基点に在る 2 本の訂正を作業ツリーで並べ替える (R1-6) | 赤 (F-2)。条件 (b) |
| 8 | 基点 rev に在る訂正を作業ツリーで削除する (列が短くなる) | 赤 (F-2)。条件 (b) |
| 9 | pending が保護参照 (例: `SI-08`) を落とす訂正である | 赤 (§9 0g の 5)。条件 (c) |
| 10 | pending の `old` が基点の塊の本文に 2 回現れる。「1 つ目を置換すれば段 B が通る」形にし、2 回現れることだけが赤の理由になるようにする (R1-10) | 赤 (F-3) |
| 11 | 記録に無い文の追加を、記録どおりの言い換えに紛れ込ませる | 赤。条件 (a) |
| 12 | pending の `old` が基点の塊の本文には 1 回在るが、受け皿の原文には 0 回である (以前の括弧の除去で形が変わった文) | 赤 (`§9f`、F-4 のとおり今までどおり) |
| 13 | 塊を丸ごと移す (新しい塊が空) 場合に、pending が保護参照を足す | 赤 (F-4 の末尾) |
| 14 | rev-vs-itself のガードテストが受け皿・訂正記録も同じ rev から読む形になっており、作業ツリーに未コミットの pending 訂正が在っても緑 (J-1) | 緑。合成リポジトリで、コミット済みのソースと受け皿に対し、作業ツリーにだけ訂正を足した状態で観測する |
| 15 | 作業ツリーで受け皿の原文 (fenced block) を書き換える (R1-1) | 赤 (原文は作業ツリーから読む) |
| 16 | 以前の削除で消した文を、pending の訂正で復活させる (R1-3) | 赤 (F-3。段 B の基準は基点の塊の本文) |
| 17 | `docs/code-history/pair.md` に節を持つ CH-ID の、基点 rev に在る訂正を作業ツリーで書き換える (R1-4) | 赤 (F-2。基点側も同じ集合を列挙する) |
| 18 | 既存の `tools/tests` が緑 (pending の無い再編集の判定が変わっていない) | 監査照合。`pt.py` の集計行を §3 に逐語で残す |
| 19 | 実リポジトリの `--register` | 緑 (`test_repository_register_passes` を含む実行で観測)。監査照合 |
| 20 | 実リポジトリの `check_comment_provenance.py --base e7562d3 MitateDB-api/src/mitatedb_api/ops.py` | **出力 0 行** (R1-9。F-7 はコメントと docstring しか触らず `ast_signature` が変わらないので (1) も緑になる。本 WP に限る)。監査照合。出力を §3 に逐語で残す。§9e か `#:` の行が出たら作業を止めて報告する (J-3) |
| 21 | F-7 の適用 (`ops.py` の 2 箇所、受け皿の訂正 2 件、pin の更新、module docstring) と `MitateDB-api` の suite | 監査照合。新文の逐語と集計行を §3 に残す |
| 22 | F-8 の行番号 pin の実測 (動いた pin の有無) | 監査照合。実測値を §3 に残す |
| 23 | 設計 v0.23 の追記 3 箇所 (§0 の版数行、§6 の 0j の行、§9.3) が入っている | 監査照合。file:line を §3 に残す |
| 24 | 下の対応表に対応の無い行が無い | — |

### 2.3 完了条件 → 変異 (1 項目 1 テスト、expect=red)

| 完了条件 | 変異 |
|---|---|
| 1 | M1: 段 A の基準を、基点 rev の列ではなく作業ツリーの全訂正で作る (現行に戻す) |
| 2 | M2: 段 B で pending を当てず、基点の塊の本文をそのまま基準にする (現行に戻す) |
| 3 | M3: pending のうち先頭 1 件だけを当てる |
| 4 | M4: pending の `old` の出現が 0 回のとき赤にする |
| 5 | M5: 基点にその CH-ID の節が無いとき、作業ツリーの列をそのまま基点の列とみなす (pending を 0 件にする) |
| 6 | M6: 段 B の許容操作の判定を常に ok にする |
| 7 | M7: F-2 の先頭部分列の照合を、訂正の**件数**の比較だけにする |
| 8 | M8: F-2 の照合で、基点の列を作業ツリーの列の長さに切ってから比べる |
| 9 | M9: `_correction_relaxes_protection` が常に `None` を返すようにする |
| 10 | M10: pending の `old` の出現が 2 回以上のとき、1 つ目だけ置き換えて進む |
| 11 | M11: 段 B の `_is_allowed_reduction` の引数を入れ替える (基準と新しい塊を逆にする) |
| 12 | M12: 再編集の経路で、作業ツリーの全訂正を受け皿の原文へ当てる検査を飛ばす |
| 13 | M13: 丸ごと移す分岐の保護参照の検査を、pending を当てる**前**の本文に掛ける |
| 14 | M14: rev-vs-itself のガードテストの受け皿・訂正記録の読み口を作業ツリーへ戻す (現行の形) |
| 15 | M15: 段 A の受け皿の原文を、作業ツリーではなく基点 rev から読む |
| 16 | M16: 段 B の基準を、基点の塊の本文ではなく受け皿の全訂正適用後の本文に替える |
| 17 | M17: 基点側の受け皿の列挙から `pair.md` を外す |
| 18・19・20 | 監査照合 (`pt.py` の集計行、`--register` を含む実行の pass 件数、`--base` の出力を逐語で §3 に残す) |
| 21・22 | 監査照合 (新文の逐語、`MitateDB-api` の集計行、動いた行番号 pin を §3 に残す) |
| 23 | 監査照合 (設計の追記 3 箇所を file:line で §3 に残す) |
| 24 | 監査照合 (本表) |

`mutate.py` は最初の失敗で止まるので、変異 1 件につきテスト 1 件を指す (`tests` に 1 件だけ書く)。

### 2.4 道具の引数 (main checkout を cwd にし、`SP` を export する)

- `tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- tools/tests/test_comment_provenance.py -q`
- `tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- tools/tests -q`
- `tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- MitateDB-api/tests -q`
- `tools/dev/mutate.py "$SP/r68-mutations.json" -C .claude/worktrees/jovial-almeida-97c9fb`
- 実リポジトリの照合 (worktree を cwd にして): `python3 tools/check_comment_provenance.py --base e7562d3 MitateDB-api/src/mitatedb_api/ops.py`、`python3 tools/check_comment_provenance.py --register`

### 2.5 範囲外 (直さない)

- 初回の移動の経路と `--register` の判定、R-63 の CH-ID の無い塊の列比較、§9e と `#:` の検査 (J-3)。
- R-57 設計メモ `docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md`:167、:253 の残件行 (J-4。監督が記録のコミットで追記する)。
- `security/CONTROL_MAPPING_HISTORY.md`:233、:283 の旧文言 (R1-13。凍結した記録であり、`security/` は Class D)。**触らない。**
- CH-0538・CH-0539 以外の塊の言い換え。受け皿の既存の塊・既存の訂正の書き換え。
- `MitateDB-api/docs/cloud-run-cloud-sql.md` と help の文面 (既に列の言い方である。§1.5 の照合結果は §3)。
- `--base` を `tools/` のパスに掛ける自己照合 (R-63 の J-4 と同じ扱い)。
- 実リポジトリの `--base` で F-7 以外の変更を測り直すこと。

## 3. 記録 (統合時に監督が埋める)

- **実施 2026-09-20。** 基点 main `e7562d3`。統合は文書が main `6ae490e` (作業 `53dfba7`)、コードが main `b83d9aa` (作業 `2ba6dc6`)。push は無し。変更は `tools/check_comment_provenance.py`・`tools/tests/test_comment_provenance.py`・`MitateDB-api/src/mitatedb_api/ops.py`・`docs/code-history/MitateDB-api/ops.md` (訂正 2 件の追記のみ)・`MitateDB-api/tests/test_ops_help_text.py`・`MitateDB-api/tests/test_ops_apply_platform_migration.py`。**変更クラス B** (`tools/change_class.py` 実測 `class=B`、`conformance_required=true`)、契約 1.8.0 のまま、`spec/`・`conformance-tests/`・`security/`・migration の差分 0。
- **道具**: 完了ゲート (worktree の最終の製品の木、`gate.py -C`) `3789 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0、共有クラスタ差分 0 (info)。**ゲート後の修正は `tools/check_comment_provenance.py` と `tools/tests/test_comment_provenance.py` だけで、root suite の testpaths (`conformance-tests`・`r2db-api/tests`・`MitateDB-api/tests`) は `tools/` を収集せず依存もしない。** 統合時の `tools/tests` `568 passed` (`finalize.py --tools-tests`)。`MitateDB-api/tests` `1404 passed, 2 subtests passed`。`mutate.py`: 19 件とも `expect=red got=red`。
- **完了条件 20・19 の実測** (worktree を cwd にして): `python3 tools/check_comment_provenance.py --base e7562d3 MitateDB-api/src/mitatedb_api/ops.py` = `comment provenance OK: 112 blocks checked` (exit 0、FAIL 行 0)。`python3 tools/check_comment_provenance.py --register` = `comment provenance register OK: 87 files scanned, 430 CH-IDs`。§9e と `#:` の行は出ていない (J-3 の停止条件は発火せず)。
- **完了条件 21 (F-7 の適用、新文の逐語)**: `MitateDB-api/src/mitatedb_api/ops.py`:2624 のコメントは ``apply-platform-migration` -- applies a run of one or more platform migration files (never a per-application upgrade, never the bootstrap-only 0001/0002) a second (or later) time against a running cluster.`、:2818 の docstring は `Applies a run of one or more platform migration files a second (or later) time against a running cluster.`。どちらも第 2 文以降は 1 字も変えていない。受け皿 `docs/code-history/MitateDB-api/ops.md` の CH-0538 節・CH-0539 節に `### correction: 2026-09-20` を各 1 件追記した (既存の塊と 2026-09-19 の訂正は書き換えていない)。`MitateDB-api/tests/test_ops_help_text.py`:121 の `_SECTION_HEADING_FIRST_LINE` は、節見出しコメントの第 1 行の逐語を「applies one platform migration file」で終わる形から「applies a run of one or more」で終わる形へ動かした。CH-ID を持たない `MitateDB-api/tests/test_ops_apply_platform_migration.py`:2 の module docstring は直接直した。
- **完了条件 22 (F-8 の実測)**: `ops.py` の 2 箇所とも **5 行 → 5 行**で、**動いた行番号 pin は無い**。
- **完了条件 23 (設計の追記)**: `docs/design/CODE_COMMENT_PROVENANCE_V1.md`:5 (§0 の v0.23 の版数行)、:205 (§6 の 0j の行)、:398 (§9.3 の見出し)。
- **完了条件 → 変異 → test id** (`tools/tests/test_comment_provenance.py::` を省く): 1 ← M1 → `test_0j_comment_reword_with_same_changeset_correction_is_green` / 2 ← M2 → `test_0j_docstring_reword_with_same_changeset_correction_is_green` / 3 ← M3 → `test_0j_two_pending_corrections_chain_is_green` / 4 ← M4 → `test_0j_pending_old_absent_from_basis_block_is_noop_green` / 5 ← M5 → `test_0j_no_basis_section_in_present_companion_file_treats_all_as_pending_is_green` (第 1 形 `test_0j_no_basis_companion_section_treats_all_as_pending_is_green` も在る。訂正註 3) / 6 ← M6 → `test_0j_reword_without_any_correction_record_is_red` / 7 ← M7 → `test_0j_basis_correction_new_rewritten_in_working_tree_is_red` / 8 ← M8 → `test_0j_basis_correction_deleted_in_working_tree_is_red` / 9 ← M9 → `test_0j_pending_correction_drops_protected_reference_is_red` / 10 ← M10 → `test_0j_pending_old_occurs_twice_is_red` / 11 ← M11 → `test_0j_unrecorded_sentence_added_alongside_reword_is_red` / 12 ← M12 → `test_0j_pending_old_absent_from_companion_original_is_red` / 13 ← M13 → `test_0j_whole_block_move_with_pending_added_protected_ref_is_red` / 14 ← M14 → `test_0j_rev_pair_check_ignores_uncommitted_pending_correction_is_green` / 15 ← M15 → `test_0j_working_tree_rewrite_of_companion_original_is_red` / 16 ← M16 → `test_0j_pending_revives_previously_deleted_sentence_is_red` / 17 ← M17 → `test_0j_pair_md_basis_correction_rewritten_is_red` / 25 ← M18 → `test_0j_unreadable_basis_companion_path_is_fail` (+ 監査照合 `test_0j_unreadable_basis_rev_is_fail`) / 26 ← M19 → `test_0j_ls_tree_failure_on_resolvable_rev_is_fail`。18〜24 は監査照合 (集計行・`--register`・`--base` の出力・新文・pin の実測・設計の追記・本表)。**対応の無い行は 0** (完了条件 24)。
- **レビュー**: 設計レビュー 1 回 (13 件、全件採用)。コードレビュー 1 回 + 再確認 1 回。受け入れ監査は入れていない (Class B。監督がゲートの集計行と本表を照合した)。
- **起票**: 部分的に縮約済みの文が R-68 の経路でも言い換えられない件を `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) R-69 に起票した (コードレビュー 1 の実測)。

### 3.1 訂正註 (2026-09-20 追記。§2 の本文は書き換えない)

- **訂正註 1 (完了条件 20 の読み、監督裁定)**: 「出力 0 行」は満たせない — 道具は成功時に必ず `comment provenance OK: N blocks checked` を 1 行出す。**合格条件は「FAIL 行 0・exit 0」と読む。**
- **訂正註 2 (完了条件 25・26 を足した。コードレビュー 1)**: **25.** rev の木に在ると列挙された受け皿 path の `git show` が失敗した場合、および rev 自体が解決できない場合は FAIL とする (「訂正 0 件」として静かに進まない)。変異 **M18** = `test_0j_unreadable_basis_companion_path_is_fail`。rev 不読の `test_0j_unreadable_basis_rev_is_fail` は**監査照合** — `run_base` からは先に src の `git show` 失敗で止まるので end-to-end では到達しない、単体 API の防御である。**26.** 解決できる rev で木の列挙 (`git ls-tree`) が落ちた場合も FAIL とする。変異 **M19** = `test_0j_ls_tree_failure_on_resolvable_rev_is_fail`。
- **訂正註 3 (完了条件 5 の第 2 形)**: 受け皿ファイルは在るが**その CH-ID の節が無い**形 `test_0j_no_basis_section_in_present_companion_file_treats_all_as_pending_is_green` を足し、**M5 の対象をこちらにした** (ファイルごと無い第 1 形も残す)。
- **訂正註 4 (実装担当の逸脱 3 点、監督受理)**: (i) 既存の fixture helper `_correction_scenario` を、受け皿と訂正をコミット前に書く形に変えた (既存 3 テストの assert は不変。検出力の維持をレビューが確認した)。(ii) F-4 の全訂正検査を、再編集の**全塊に無条件で**走らせた (従来は基点の塊が何も残さない場合に走らなかった。強化側の差である)。(iii) 完了条件 10 の fixture は「受け皿の原文では曖昧でなく、基点の塊でだけ 2 回現れる」形にした。
