# 作業指示書 — R-69 pending の訂正の `old` が、基点の塊で既に縮約された文に当たる

## 0. 版数・位置づけ

- **v1.0 (2026-09-22)。** 基点 main `f8df323`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-69。変更クラスは **Class B** (`tools/` と `tools/tests/`、設計文書の追記)。設計文書 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` は v0.25 の追記 (§9.4) で本書 §1 の規則を写す。設計レビューは行わず、決定は本書 §1 に置く (R-68 と同じ道具の 1 規則の追加。コードレビュー 1 回)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 問題と決定 (監督確定)

**問題**: R-68 (設計 §9.3) の経路で、pending の訂正 (作業ツリーにだけ在る訂正記録) は基点の塊の本文 `ob.retained_text` に当てる (規則 3、`_apply_pending_corrections`、`tools/check_comment_provenance.py:2325-2358`)。`old` がそこに 0 回なら「以前の削除で既に無い」として無変更で進む。しかし基点の塊が受け皿の原文から §4.1 (4)/(6) で**縮約されている**とき (受け皿は `… (R-5).`、塊は `(R-5)` を落とした形)、受け皿の形で書いた `old` は塊に 0 回になり、無変更のまま段 B (`_is_allowed_reduction(pending_basis, nb.retained_text)`、`:2913`) が `FAIL (§4.1 (3)) … no order-preserving match` で赤になる。塊の形で書くと、規則 4 の全訂正検査 (`_corrected_basis` → `_apply_corrections`、`:2865-2868`、受け皿の原文に対して `old` がちょうど 1 回) が `FAIL (§9f) … occurs 0 time(s) in the basis` で赤になる。どちらでも赤で、縮約済みの塊は今も削除でしか直せない。

**あわせて閉じる穴 (実測ではなく読解)**: 同じ「0 回 → 無変更」により、pending の訂正を記録しながらコードの塊に旧文の縮約形を残したままにしても緑になる (段 B の基準が旧文のまま、新しい塊も旧文のまま)。0j より前は受け皿の全訂正を当てた基準と比べていたので赤だった。訂正が事実に合っているかは独立レビューが見る (0g の 7) が、コードが訂正に追随したかは道具が見るべきものである。

**決定**:

- **D-1 (規則 3 の補い)。** `_apply_pending_corrections` で pending の `old` が基準 (flatten 済みの `retained_text`) に **0 回**のとき、無変更で進む前に、基準の各文 (`split_sentences`) のうち **`old` から §4.1 (4)/(6) の許容操作で得られる文** (`_sentence_reachable(old, S, real_paths)`、または `_is_allowed_reduction` と同じく `_strip_leading_label(old)` からの到達) を数える。
  - 候補が **0** — 今までどおり無変更で進む (以前の削除。設計 §9.3 の fixture 4 は緑のまま)。
  - 候補が **ちょうど 1** — その文 S を `new` に置き換える (S は基準の文字列に 1 回だけ現れること。2 回以上なら次項と同じ赤)。新しい塊が `new` の縮約形を持つ場合は、段 B の `_is_allowed_reduction` が `new` → 縮約形を許容操作として通す。
  - 候補が **2 以上** — 赤。専用の診断行: `FAIL (§9.4) <path>:<line> <CH-ID>: pending correction <date>: old sentence occurs 0 time(s) verbatim in the basis block, and <N> of its sentences are reductions of it (ambiguous): <S1!r>, <S2!r>…`。
- **D-2 (規則 4 は変えない)。** 訂正記録の `old` は**受け皿の原文の形**で書く (規則 4 の全訂正検査がそれを要求する)。塊の縮約形で書いた `old` が `FAIL (§9f) … occurs 0 time(s)` になるのは今までどおりで、意図した赤である (fixture で固定する)。
- **D-3 (穴を閉じる)。** D-1 の帰結として、pending の訂正を記録しながら塊に旧文の縮約形を残したままの変更セットは、段 B が `FAIL (§4.1 (3))` で赤になる (基準の S が `new` に置き換わり、新しい塊の S は `new` から得られない)。これは 0j 以前の判定への復帰であり、fixture で固定する。
- **D-4 (`old` が文の一部のとき)。** 訂正記録の `old` / `new` は 1 文の規約 (`:2070-2075` の docstring) だが `_parse_corrections` は強制していない。`old` が文の一部 (部分文字列) のときは、今までどおり部分文字列の一致 (1 回なら置換) で動き、D-1 の文単位の照合は 0 回のときにだけ試みる。部分文字列の `old` が縮約形に当たらないなら候補 0 で無変更 — 今と同じ判定。規約の強制は本件の範囲外。
- **D-5 (設計文書)。** `docs/design/CODE_COMMENT_PROVENANCE_V1.md` に **v0.25** として §9.4 を追記する: 問題、規則 (D-1〜D-3)、fixture 表 (下の §2.2 の 17〜21)、却下した代替案。§9.3 の本文は書き換えない。版数行を足す。
- **却下した代替案**: (a) 段 B の基準を「受け皿の原文 + 全訂正」からの導出に替える — §9.3 が (a) として却下済み (以前の削除で消した文の復活を許す)。(b) `old` を塊の縮約形で書くことを規則 4 の検査で許す (受け皿の原文への一致を「許容操作で得られる」に緩める) — 訂正記録の `old` が受け皿と一致しなくなり、記録を読む人が原文と突き合わせられない。(c) 専用の診断行だけ足して直さない — 縮約済みの塊が削除でしか直せない状態が残る。

## 2. WP-1 — `_apply_pending_corrections` に縮約形の照合を足し、fixture で固定する

### 2.1 触ってよいパス

- `tools/check_comment_provenance.py` (`_apply_pending_corrections` と、必要ならその呼び出し箇所 `:2902-2908` の診断の組み立てだけ)
- `tools/tests/test_comment_provenance.py` (`test_0j_*` の並びに `test_0k_*` を足す。既存のテストは変えない)
- `docs/design/CODE_COMMENT_PROVENANCE_V1.md` (v0.25 の版数行と §9.4 の追記だけ)

### 2.2 完了条件

1. D-1 のとおり動く。診断行の文言は D-1 の形 (`§9.4` を名指す)。
2. fixture (設計 §9.3 の表の続き番号。`_same_changeset_scenario` の型で書く):

| # | fixture | 期待 |
|---|---|---|
| 17 | 受け皿の原文が `… (R-5).` (裸 ID を末尾の括弧に持つ文)、基点の塊は `(R-5)` を落とした形、pending の `old` は受け皿の形、新しい塊は `new` の形 | 緑 |
| 18 | 17 と同じで、新しい塊は `new` から `(R-5)` 相当を落とした縮約形 | 緑 (段 B が `new` → 縮約形を通す) |
| 19 | 基点の塊に `old` の縮約形が 2 文ある (受け皿に同じ文が 2 回 — 受け皿側は規則 4 で赤にならない形にする: `old` は受け皿の**原文 + 基点訂正**に 1 回になるよう、受け皿の 2 文目は基点の訂正で別文に置き換えておく。作れなければ、基準の文字列に S が 2 回現れる形で D-1 の同じ赤を出す) | 赤、診断行が `§9.4` と `ambiguous` と 2 文を名指す |
| 20 | 17 と同じで、新しい塊は基点の塊のまま (縮約形の旧文を残す) | 赤 `FAIL (§4.1 (3))` (D-3) |
| 21 | 17 と同じで、pending の `old` を塊の縮約形で書く | 赤 `FAIL (§9f) … occurs 0 time(s)` (D-2、今までどおり) |
| 4 (既存) | `test_0j_pending_old_absent_from_basis_block_is_noop_green` | 緑のまま (候補 0) |

   空振り禁止: 17・18 は `code == 0` に加え、置換が起きたことを観測する (例: 19 の赤の診断、または 20 の赤が同じ入力で起きること。実装担当の裁量で、17 の scenario を 1 箇所変えると赤になる対を置く)。
3. `tools/dev/pt.py -C . -- tools/tests/test_comment_provenance.py -q` が緑 (既存 `test_0j_*` 21 本を含む)。`tools/tests` 全体は監督が `finalize.py --tools-tests` で回す。
4. 道具の自己検査: `tools/check_comment_provenance.py --register` が緑、`--base f8df323 tools/check_comment_provenance.py` は `tools/` が走査対象外なら「対象外」を報告 (対象なら §4.1 (1) の赤だけ)。`tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。
5. 設計 v0.25 §9.4 が D-1〜D-3 と fixture 表を写し、`_apply_pending_corrections` の docstring が新しい分岐を 1 段落で説明する (経緯トークンを入れない: `WP-`、日付、`review`、`supervisor ruling` を書かない)。
6. 下の対応表に対応の無い行が無い。

### 2.3 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1・2 (17) | M1: 候補 1 のときも無変更で進む (置換を外す) | fixture 17 (または 20) が赤/緑を反転 — 1 変異 = 1 テストで、20 のテストが緑になる (`expect: red` に対する `got=green` を「赤」として書く: mutate.py では 20 のテストを対象に `expect: red`) |
| 2 (19) | M2: 候補 2 以上でも最初の 1 つを置換する | 19 のテストが赤 |
| 2 (18) | M3: S を `new` ではなく `old` に置き換える | 18 のテストが赤 |
| 2 (21) | M4: 規則 4 の全訂正検査で 0 回を許す | 21 のテストが赤 |
| 2 (4) | M5: 候補 0 でも赤にする | fixture 4 のテストが赤 |
| 1 (診断) | M6: 診断行から `§9.4` を消す | 19 のテストが赤 |
| 3・4・5 | 監査照合 (コマンドと集計行を逐語で報告に残す) | — |
| 6 | 監査照合 (本表) | — |

### 2.4 道具の引数

- `tools/dev/pt.py -C . -- tools/tests/test_comment_provenance.py -q` (worktree を cwd に。前景・同期、Bash timeout 600000)
- `tools/dev/mutate.py "$SP/r69-mutations.json" -C .` (1 変異 = 1 テスト。`tools/tests` は conformance と分けて回す)
- python は main checkout の `.venv/bin/python`。終了コードは pipe の外で取る。

## 3. レビューと受け入れ

コードレビュー 1 回 (別に起動した `reviewer`)。受け入れは監督がゲートの集計行と対応表を照合して行う (Class B)。

## 4. 記録 (統合時に監督が埋める)

### 4.1 訂正註と監督裁定 2026-09-22 (§1〜§3 の本文は書き換えない)

- **完了条件 4 の文言の訂正**: `tools/` は `--base` の走査対象で、`--base f8df323 tools/check_comment_provenance.py` は §4.1 (1) (コードが変わった) に加え **§4.1 (2) を 2 件**出す — `_apply_pending_corrections` の docstring への追記と、呼び出し箇所のコメントの追記で、基準 rev に在る対象への塊の追加として道具の設計どおりの赤である (R-67 と同じ形。R-89 の材料)。CI と pre-commit はこの道具を呼ばない。
- **コードレビュー 1 (高 1 / 中 2 / 低 4) は全件修正**: 高 1 — D-1 の括弧書き「S は基準の文字列に 1 回だけ現れること」が未実装だった。ラベル付きの文 (`Rule 4: The connection is closed.`) と同じ本文の文が並ぶ塊で、`working.replace(S, new, 1)` が別の文に当たり、意図どおりの塊が赤・記録の無い改稿が緑になった (レビューが関数を直接呼んで実測)。一意性の検査と fixture 22・変異 M7 を足した。位置指定の置換で緑にする案は採らない (記録の `old` が 1 文を一意に指せない塊は記録の側で直す)。中 2 — ラベルを剥がした `old` からの到達の分岐が変異で空振り (`or (...)` 節を削っても全緑) → fixture 22' (`Ruling U-7:` のラベル付き受け皿、ラベルと括弧を落とした基点の塊) と変異 M8。低 4 件 — 診断の節の出し分けを固定句の文字列一致から戻り値の第 3 要素 (`section`) に、設計の版数行に日付、§9.4 の「規則 4」を「§9.3 の規則 4」に、docstring の「0-for-0」を平叙に、fixture 20 のテストに赤の理由の assert。
- fixture 22' のラベルは `Ruling U-7:` (裁定原文の `(WP-6d)` を外した。`WP-` はソースの追加行で §4.1 (5) が先に赤にする)。

### 4.2 実施と受け入れ

- 差分: `tools/check_comment_provenance.py`、`tools/tests/test_comment_provenance.py` (`test_0k_*` 7 本)、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` (v0.25 §9.4)。
- `tools/dev/pt.py -C . -- tools/tests/test_comment_provenance.py -q`: `pt: 289 passed` (監督が再実行)。変異 M1〜M8 全件 `expect=red got=red`、復元 sha256 × 2。`--register` `OK: 87 files scanned, 430 CH-IDs`、`check_doc_refs` 0 dangling、`public_value_scan` `total_flagged=0`。
- コードレビュー 1 回 (上記)。
- 完了ゲート (監督が単独実行): `3844 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` (finalize.py --tools-tests): `575 passed`
- **最終判定: 受け入れる。**

