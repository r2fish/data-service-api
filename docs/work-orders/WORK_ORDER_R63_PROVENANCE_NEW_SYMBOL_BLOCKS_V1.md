# 作業指示書 — R-63 `check_comment_provenance.py` が新しい symbol の説明を書けなくする

## 0. 版数・位置づけ

- **v1.0 (2026-09-20)。** 基点 main `2172fb0`。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の R-63 (`RM`:461)。変更クラスは **Class B** (`tools/change_class.py` 実測: 3 パスで `class=B`、`docs/design/…` は A、`tools/…` の 2 件が B)。新しい設計文書は起こさない (本書 §1 が枠。既存設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` を D-3 で改版する)。形の先行は `docs/work-orders/WORK_ORDER_R58_PERF_BASELINE_ENV_RESTORE_V1.md`。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 枠 (監督確定)

### 1.1 問題設定と守るべき条件

§4.1 (2) の実装は、CH-ID の無い塊を `(scope, anchor)` の鍵で旧版と新版の列として**対称に**比べる (`tools/check_comment_provenance.py` の `check_provenance_semantics` の末尾、鍵は `_scope_and_anchor_for_block`)。このため、基準 rev に無い symbol (新しい関数・class・module 水準の定数) に付けた docstring や `#:` コメントは必ず赤になる。設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md`:150 の (2) の文は「旧版の塊が新版から消えた」側だけを言う。道具の目的は経緯の語りがコメントに残るのを防ぐこと・既存の塊を register なしで消したり動かしたりさせないことであって、**新しい symbol の説明を禁じることではない**。

守る条件:

- (a) 既存の塊の削除・改変・別の文への移動は今までどおり赤。
- (b) 新しい symbol の塊にも (5) の経緯トークン走査は掛かる。
- (c) 「新しい symbol の塊」を装って既存の塊を移す抜け道を作らない (旧側の鍵から塊が消えれば旧側で赤になることをテストで固定する)。
- (d) (1)・(3)・(4) と `--register` の判定は変えない。

### 1.2 現行の実測 (2026-09-20、起草時。基点 `2172fb0` の `check_provenance_semantics` を合成ソースに直接呼んだ)

| # | 形 | 現行 (index 鍵 `stmt#N`) の出力 |
|---|---|---|
| (i) | 既存の module 水準の `#:` 塊の**前**に文を 1 つ足す (塊の本文は 1 字も変えない) | `('<module>','stmt#2')` で old 1 / new 0、`stmt#3` で old 0 / new 1 の **§4.1 (2) が 2 件**。既存の塊の誤った赤 |
| (ii) | 同じ位置に**新しい関数**を足す | (i) の 2 件 + 新しい関数の docstring 自身の 1 件 (計 3 件) |
| (iii) | 既存の関数の本体に文を足す (その関数の docstring の後ろ) | 赤にならない (docstring の anchor は `stmt#1` のまま) |
| (iv) | scope 末尾の塊 (anchor `<end>`) の**後ろ**に新しい関数を足す | `('<module>','<end>')` と `('<module>','stmt#2')` で **2 件**。既存の塊の誤った赤 |

現行の index 鍵は、コードを変える差分 (文の挿入) で既存の塊を誤って赤にする。鍵の取り方を D-1 で改める。

### 1.3 決定

- **D-1.** CH-ID の無い新版の塊のうち、**その塊が付く対象が基準 rev に存在しない**ものは (2) の列比較から外す (= 追加を許す)。「対象が存在しない」の判定は、docstring ならその塊を所有する scope (dotted name) が旧版の AST に無いこと、コメント塊なら anchor の文が旧版の同じ scope に無いこと。**anchor の鍵は J-1、比較の形は J-2 による** (index でも構造そのものでもなく、旧版の scope の body への整列で得た旧版の index)。
- **D-2.** 既存の対象 (旧版に在る scope / 文) に新しい塊を足すことは、今までどおり赤のままにする。本件の範囲は新しい symbol だけで、広げない。
- **D-3.** 設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` に、この扱いを版を上げて追記する (既存の文は消さない。追記先は J-3)。
- **D-4.** docstring 無しで置かれた既存の関数 (両 peer の `check_auditreader_statement_timeout` ほか) に docstring を足す作業は**本件に含めない** (J-5)。

### 1.4 却下した代替案

- **(x) (2) を完全に片側 (旧→新) だけにする** — 既存の文に register なしで経緯の塊を足せるようになり、(5) のトークン表に無い語りを通す。
- **(y) 運用の読み替え (R-56 の監督裁定 A-1、`docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md`:558) を続ける** — 新しい関数が docstring を持てないままになる。

### 1.5 監督裁定 (2026-09-20)

- **J-1.** anchor の鍵は「構造そのもの」ではなく、**旧版の scope の body への整列で得た旧版の index** にする。整列は scope ごとに、文ごとの token の列を旧版と新版で作り `difflib.SequenceMatcher` (`autojunk=False`) の一致ブロックで対応を取る。token は def / class = (種別, 名前)、`Assign` / `AnnAssign` / `AugAssign` = (種別, target の `ast.dump`)、それ以外 = docstring を除いた `ast.dump`。これにより (i) 値や本体だけが変わった定数・関数は同じ文として対応が取れ、付いている塊を誤って赤にしない、(ii) 構造の等しい兄弟文 (`pass` が 2 つ) も位置で区別され、片方からもう片方へ塊を移すと今までどおり赤、(iii) 旧版に対応の無い文は「新しい文」になる。scope の対応は dotted name (今のまま)。
- **J-2.** 新版の塊の鍵は「その塊の後ろで最初に現れる、**旧版に対応の在る文**の旧 index (無ければ `<end>`)」とする (新しい文は透過)。比較は鍵ごとに「旧版の列が、新版の列から**新しい symbol の塊だけを削除して得られる**こと」(順序を保つ部分列)。削除してよいのは、直後の文が新しい文である塊と、旧版に無い scope の docstring・その scope の中の塊だけ。既存の文の直前に CH-ID なしの塊を足すのは削除してよい塊に当たらないので赤のまま (D-2)。
- **J-3.** 設計の追記は §4.1 (2) の表の行と §0 の訂正註 (版を上げた新しい註。`:24` の v0.4 註 (6) を指し、消さない) の**両方**。
- **J-4.** 本 WP の自己照合 (`--base` を `tools/check_comment_provenance.py` 自身に掛ける) は完了条件にしない。R-58 の作業指示書の `tools/` への companion 条項は R-58 側で監督が処理する。
- **J-5.** 両 peer の `check_auditreader_statement_timeout` に docstring を足す件は監督が台帳に起票する。本書は範囲外の 1 行に留める。

## 2. WP-1 — (2) の列比較を「新しい symbol の塊」の分だけ開ける

### 2.1 触ってよいパス

- `tools/check_comment_provenance.py` — `_scope_and_anchor_for_block` と `check_provenance_semantics` の CH-ID の無い塊の比較まわりのみ。(1)・(3)・(4)・`--register` の判定と、CH-ID を持つ塊の対応付けには触らない。
- `tools/tests/test_comment_provenance.py`
- `docs/design/CODE_COMMENT_PROVENANCE_V1.md` (D-3・J-3。§0 に版の行と新しい訂正註、§4.1 の (2) の行に追記。既存の行は書き換えない)
- 件数 pin がこの変更で動く場合だけ、その pin (実測して報告に書く)

### 2.2 完了条件

各テストは合成ソースを `--base` に掛け、観測対象 (緑なら「§4.1 (2) の行が 0」、赤ならその行の存在) を 1 件以上 assert する (空振り禁止)。

| # | 形 | 求める結果 |
|---|---|---|
| 1 | 基準 rev に無い関数に docstring を付ける | 緑 |
| 2 | 基準 rev に無い module 水準の定数に `#:` コメント塊を付ける | 緑 |
| 3 | 1 の docstring に (5) の語 (例: `WP-1`) が在る | 赤 (`§4.1 (5)`)。条件 (b) |
| 4 | 旧版に在る塊を、新しい関数の中へ CH-ID 無しで移す | 赤。**旧側の鍵** (old 1 / new 0) から出ることを出力の文言で固定する。条件 (c) |
| 5 | 旧版に在る文の直前に CH-ID 無しの塊を足す | 赤 (D-2) |
| 6 | 既存の `#:` 塊の**前**に文を挿入する (§1.2 (i)) | 緑 (塊の本文は不変) |
| 7 | 塊の付いた定数の**値だけ**を変える | 緑 (J-1 の token) |
| 8 | scope 末尾の塊の**後ろ**に新しい関数を足す (§1.2 (iv)) | 緑 (J-2 の透過と部分列) |
| 9 | 構造の等しい兄弟文 (`pass` が 2 つ) の間で塊を移す | 赤 (J-1 (ii)) |
| 10 | (1) を通る差分 (コード不変) | 整列が恒等になり、現行と同じ判定。観測は既存 246 件が全て緑であること |
| 11 | 実リポジトリの `--register` | 緑 (`test_repository_register_passes`) |
| 12 | D-3・J-3 の追記 (表の行と §0 の新しい訂正註の両方) | 入っている |
| 13 | 下の対応表に対応の無い行が無い | — |

### 2.3 完了条件 → 変異 (1 項目 1 テスト、expect=red)

| 完了条件 | 変異 |
|---|---|
| 1 | M1: 「新しい scope / 新しい文」の判定を常に「旧版に在る」にする |
| 2 | M2: 削除してよい塊を docstring の塊だけに限る (コメント塊を除外しない) |
| 3 | M3: (5) の走査から、削除してよい塊の行を外す |
| 4 | M4: 削除してよい塊を**旧側の列からも**取り除く |
| 5 | M5: 「直後の文が新しい文である」条件を外し、新版で追加された塊を一律に削除してよい塊とする |
| 6 | M6: 整列をやめ、新版の body の index をそのまま鍵にする |
| 7 | M7: `Assign` の token を target ではなく文全体の `ast.dump` にする |
| 8 | M8: 比較を「削除してよい塊を**全て**削除した列との一致」に変える (部分列ではなく) |
| 9 | M9: 鍵を旧 index ではなく、対応の在る文の token そのものにする |
| 10・11 | 監査照合 (`pt.py` の集計行と、`test_repository_register_passes` を含む実行の pass 件数を逐語で §3 に残す) |
| 12 | 監査照合 (設計の追記 2 箇所を逐語で §3 に残す) |
| 13 | 監査照合 (本表) |

`mutate.py` は最初の失敗で止まるので、変異 1 件につきテスト 1 件を指す。

### 2.4 道具の引数 (main checkout を cwd にし、`SP` を export する)

- `tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- tools/tests/test_comment_provenance.py -q`
- `tools/dev/pt.py -C .claude/worktrees/inspiring-dewdney-461b95 -- tools/tests -q`
- `tools/dev/mutate.py "$SP/r63-mutations.json" -C .claude/worktrees/inspiring-dewdney-461b95`

### 2.5 範囲外 (直さない)

- D-4・J-5: 既存の関数に docstring を足す作業 (両 peer の `check_auditreader_statement_timeout` ほか)。本件では 1 行も足さない。起票は監督が行う。
- J-4: `--base` を `tools/` のパスに掛ける自己照合と、その受け皿の有無。
- 実リポジトリの `--base` で他の変更を測り直すこと (R-58 の `tools/perf_baseline.py` を含む)。

## 3. 記録 (統合時に監督が埋める)

- **実施 2026-09-20。** 基点 main `03c1b53`。変更は `tools/check_comment_provenance.py` (CH-ID の無い塊の列比較だけを置き換え。`_scope_and_anchor_for_block` と CH-ID 有りの対応付け、(1)・(3)・(4)・(5)、`--register` は無変更)、`tools/tests/test_comment_provenance.py` (テスト 15 件)、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` (v0.22: §0 の註と §4.1 (2) の行。既存の文は消していない)。
- **訂正註 1 (コードレビュー 1 回目への監督裁定。J-1 の「scope の対応は dotted name (今のまま)」を超える)**: (重大 1) 同名の兄弟 scope (`@property` と setter、`@overload`) が名前引きで 1 本に潰れ、無変更のソースが赤になった → **scope の同一性は dotted name + 同名の兄弟の中での出現順**とし、新版の塊の body は行包含の降下で得る (表示する鍵は dotted name のまま)。(重大 2) 既定の token が docstring を剥がしておらず、`if` の中の def の docstring を直すと無関係な不変の塊が赤になった → 文の deep copy に (1) と同じ剥がしを掛けてから dump する。(中) 完了条件 10 の観測を、AST 等価な差分で整列が恒等になることの直接の assert に強めた。(低) 新しい文の直前に既存の塊と同文の塊を置くことは、原本が残る限り許す (試験で固定)。(低) 内容に依らない docstring の token は (1) と同じ docstring の定義に当たる 1 文だけに使う。いずれも今の追跡ファイルでは発火しない潜在の形であった。
- **道具**: `pt: 261 passed` (`tools/tests/test_comment_provenance.py`。既存 246 + 新規 15)、`pt: 547 passed` (`tools/tests`)。`mutate.py`: 15 件とも `expect=red got=red`、復元は sha256 2 回で照合済み。
- **完了条件 → 変異 → test id** (`tools/tests/test_comment_provenance.py::` を省く): 1 ← M1 → `test_r63_new_function_with_docstring_is_green` / 2 ← M2 → `test_r63_new_module_constant_with_comment_is_green` / 3 ← M3 → `test_r63_new_function_docstring_history_token_is_red` / 4 ← M4 → `test_r63_moved_block_into_new_function_is_red_at_old_key` / 5 ← M5 → `test_r63_new_block_before_existing_statement_is_red` / 6 ← M6 → `test_r63_insert_statement_before_existing_block_is_green` / 7 ← M7 → `test_r63_value_only_change_of_commented_constant_is_green` / 8 ← M8 → `test_r63_new_function_after_scope_final_block_is_green` / 9 ← M9 → `test_r63_block_moved_between_identical_siblings_is_red` / 訂正註 1 の重大 1 ← M10・M11 → `test_r63_review1_property_setter_unchanged_is_green`・`test_r63_review1_new_setter_sibling_getter_unaffected_is_green` / 重大 2 ← M12 → `test_r63_review1_docstring_edit_inside_if_body_is_red_once` / 完了条件 10 ← M13 → `test_r63_review1_ast_equal_diffs_align_by_identity` / 低 2 件 ← M14・M15 → `test_r63_review1_duplicated_block_before_new_function_is_green`・`test_r63_review1_non_leading_bare_string_is_content_sensitive`。残りの完了条件は監査照合 (集計行・設計の追記・本表)。
- **コードレビュー** 2 回。1 回目: 抜け道は見つからず (関数の改名、新しい scope への移動、既存の文の削除と置き換え、scope 末尾の塊の改稿・削除・移動はいずれも旧側の鍵で赤)、偽陽性の重大 2・中 1・低 2。2 回目: 偽陽性 2 件の解消、出現順の鍵が抜け道を作らないこと (同名の兄弟の挿入・削除・入れ替えと書き換えの組はいずれも赤) を合成ソースで実測、コードとテストは差し戻し不要、設計文書の追記の不足 1 件 (中) は監督が v0.22 の行と §4.1 (2) の行に書き足した。
- **実リポジトリでの実測 (完了条件ではない)**: `--base 2172fb0 tools/perf_baseline.py` と、R-56 の変更を含む範囲の `r2db-api/src/r2db_api/platform_declarations.py` は、どちらも (1) の 1 行だけで (2)〜(5) は 0 行。
- **完了ゲート** (worktree、`gate.py -C`): `3763 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。
- **範囲外の起票**: 両 peer の `check_auditreader_statement_timeout` に docstring を足す件を台帳 R-67 に起票した (J-5)。

