# 作業指示書 — R-89 §4.1 (2) が直後の文の書き換えだけで赤になるのを直す

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点はローカル main `db92b5b` (作業ツリー `.claude/worktrees/r89`)。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の R-89 (`RM`:511。本文と【追記 2026-09-22 (R-67)】)。変更クラスは **Class B** (`tools/change_class.py` 実測: `tools/check_comment_provenance.py` と `tools/tests/test_comment_provenance.py` が B、設計文書は A、全体 `class=B` / `conformance_required=true`)。
- 新しい設計文書は起こさない。**決定は本書 §1 に置き**、設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` には同じ変更セットで §4.1 (2) の**訂正註 (v0.26)** を足す (先例: R-63・R-68・R-69)。形の先行は `docs/work-orders/WORK_ORDER_R69_PROVENANCE_REDUCED_OLD_V1.md`。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 枠 (監督確定)

### 1.1 問題設定と守るべき条件

**問題**: §4.1 (2) の CH-ID の無い塊の鍵は、**塊の直後の文**に依存する。実装は `_scope_and_anchor_for_block` (`tools/check_comment_provenance.py`:2549-2593) で塊の直後の文を anchor とし、`_plain_block_keys` (:2718-2773) がその文を `_align_scope_bodies` (:2664-2715、文ごとの `ast.dump` トークンを `difflib.SequenceMatcher` で整列) で旧版に対応づけた**旧 index** を鍵にする。`ast.dump` は文の中身に依るので、塊の本文が 1 字も変わっていなくても直後の文が変われば (例: `try` 文に except 節を足す) 整列が切れ、鍵が動き、`check_provenance_semantics` (:3059-3070) が `the sequence of CH-ID-less blocks changed (old 1, new 0)` を出す。R-71 の実例 (commit `0d0f8c9`): `MitateDB-api/src/mitatedb_api/backend_postgres.py` の `all_field_types` / `all_field_constraints` の docstring (差分は追加のみ、塊は不変) が赤になった。

**受け皿の問題 (本件では直さない)**: 基準 rev に在る symbol に docstring を初めて足すと `old 0, new 1` で赤になる (`RM`:511 の【追記 (R-67)】。再現: `--base b3dd0c3` を両 peer の `platform_declarations.py` に掛ける)。これは R-63 の D-2 (`docs/work-orders/WORK_ORDER_R63_PROVENANCE_NEW_SYMBOL_BLOCKS_V1.md`:35) が**意図して残した赤**であり、本 WP では変えない。読み方 (正当な赤として変更セットの作業指示書に記録して進める) を設計の訂正註に明記する。

**守る条件**:

- (a) 塊の削除・改変・別の文や別の scope への移動は今までどおり赤。
- (b) R-63 D-1 の免除 (基準 rev に無い symbol / 旧版に対応の無い文につく塊) と、(5) の経緯トークン走査は変えない。
- (c) 「直後の文を書き換えれば鍵が変わる」ことを使って既存の塊を別の塊に差し替える抜け道を作らない (塊の本文の byte 一致をゲートにする)。
- (d) §4.1 (1)(3)(4)(5)(6) と `--register` の判定、§9.4 (R-69) の縮約形の扱いは変えない。

### 1.2 決定

- **D-1 (その場の置換の対応付け)。** scope の文の列を旧版・新版でトークン (現行の `_token_for_stmt`) の列にし、`difflib.SequenceMatcher` の opcode で整列する。**J-1 の整列そのもの (`_align_scope_bodies` の戻り値) は変えない**。`replace` 区間の対は**別の写像** (例 `_replace_pairs`) として作り、**`_plain_block_keys` だけがそれを読む** (`test_r63_review1_non_leading_bare_string_is_content_sensitive` (`tools/tests/test_comment_provenance.py`:4409) は緑のまま)。対の作り方は、**`replace` 区間の旧 i 番目 ↔ 新 i 番目**とし (区間長が違えば短い方の長さまで。残りは insert / delete のまま)、対にする条件を **`_token_for_stmt` の AST ノード種別が同じ、かつ def / class は名前も同じ**ことに絞る (改名・種別違いは対にしない)。CH-ID の無い塊は従来どおり**直後の文の (scope, 整列 index) を鍵**にするが、**塊の本文が byte 一致すること**をゲートに、直後の文が `replace` の対であれば旧版・新版で同じ鍵とみなす (= 直後の文の編集だけでは赤にしない)。塊が別の文の直前へ動いた場合 (対応する文が違う) は従来どおり赤。
- **D-2 (変えないもの・既知の限界)。** (i) **scope 内で塊を別の文の直前へ移すことは赤** (P3。`docs/design/CODE_COMMENT_PROVENANCE_V1.md`:29 の v0.4 訂正註 (6)、`test_r63_block_moved_between_identical_siblings_is_red` (:4273) は緑のまま)。(ii) R-63 D-2 の「基準 rev に在る symbol への新しい塊は `old 0, new 1` で赤」。(iii) R-63 D-1 の新しい symbol の免除と、その**適用順は現行のまま**。(iv) §9.4 (R-69) の縮約形の扱い。(v) §4.1 (1)(3)(4)(5)(6)。(vi) **既知の限界**: 直後の文が**同じ種別の別の文**に書き換えられた場合 (例 `b()` → `d()` の直下のコメント塊) も同じ鍵とみなすので、塊の説明が嘘になっても (2) は黙る。これは docstring と設計の訂正註に書く。
- **D-3 (設計の訂正註)。** `docs/design/CODE_COMMENT_PROVENANCE_V1.md` の §0 の版数行 `:5` (v0.25) の**上に v0.26 の行を足す** (既存の行は書き換えない)。その行の中に次を書く: (1) `replace` 区間の文を旧 i ↔ 新 i で対にし、**本文が byte 一致する塊は直後の文がその対であれば同じ鍵**とみなすこと (対の条件はノード種別と def / class の名前の一致。D-2 (vi) の限界も記す)、(2) 塊を別の文の直前へ移すことは今までどおり赤 (P3 は不変)、(3) `old 0, new 1` (基準 rev に在る symbol への新規 docstring) は正当な赤であり、変更セットはその赤の形を作業指示書の完了条件に書いて進めること (R-67 の先例)、(4) **v0.22 の J-2 の鍵の取り方をこの版で改める**こと。
- **D-4 (テスト)。** `tools/tests/test_comment_provenance.py` に `test_r89_*` を足し、次を固定する: (i) R-71 型 — 旧版「塊 + `try:` 本体」→ 新版「同じ塊 + `try/except`」は**緑**、(ii) 塊の本文を 1 字変えた形は**赤** (失敗行の `(old 1, new 0)` を逐語で assert)、(iii) 別の兄弟文の直前へ塊を移すと**赤** (既存テスト `test_r63_block_moved_between_identical_siblings_is_red` で担保。新規は不要)、(iv) `replace` 区間の長さが違う場合 — 旧 1 文 → 新 2 文で塊が新側の **1 番目**に付けば**緑**、**2 番目**に付けば**赤**、(v) 旧 2 文 → 新 1 文で、塊が**残る側**の文に付けば**緑**、**消える側**の文に付けば**赤**、(vi) 旧版に無い塊を、書き換えられた文の直前に足すのは**緑のまま** (S10 型)、(vii) 改名・種別違いの書き換えの直下の塊は**赤** (S12 型。S17・S18 型も同じ)、(viii) 同じ種別の別の文への差し替えの直下の塊は**緑** (S19 型。D-2 (vi))、(ix) R-67 型 (`old 0, new 1`) は**赤**のまま。fixture は既存の `test_r63_*` (:4157-4409) / `test_r69_*` の形 (`_init_repo` / `_write` / `_commit_all` / `_run_base` による一時 git repo) に倣う。node id の増分は実装担当が報告する。
- **D-5 (実 commit での確認)。** R-71 の実 commit `0d0f8c9` (`MitateDB-api/src/mitatedb_api/backend_postgres.py`) を使い捨て repo で再現する (`0d0f8c9~1` の内容を commit し、`0d0f8c9` の内容を作業ツリーに置いて `--base`)。既存の実 repo 依存テスト 4 件と同じ形で `tools/tests` に置く。実 repo に `0d0f8c9` が無ければ skip ではなく **fail** とする。

### 1.3 却下した代替案

- **(x) §4.1 (2) を廃止する** — 塊の黙った編集・削除を見逃す。
- **(y) anchor を「直後の文」から「直前の def 行」に変える** — module 水準の塊で位置が決まらない。
- **(z) R-67 型 (`old 0, new 1`) も免除する** — R-63 D-2 の意図に反し、経緯を運ばない新規 docstring を無検査にする。

### 1.4 未確定で依頼者判断待ちの選択肢

無し。

### 1.5 設計レビュー 1 の反映 (2026-09-23)

指摘 8 件を全件採用し、本節までに織り込んだ (監督裁定)。高-1 = J-1 の整列は変えず `replace` の対は別の写像にして `_plain_block_keys` だけが読む (D-1)。高-2・高-3 = 実装形は B (塊の本文の byte 一致をゲートにする) に固定し、S10 型の緑と変異 M6、完了条件 2 の `(old 1, new 0)` の逐語 assert を足した (D-1、D-4 (ii)(vi)、§2.2 の 2・7)。中-4 = 対にする条件をノード種別と def / class の名前の一致に絞り、同種別の差し替えが黙ることを D-2 (vi) の既知の限界として明記し、S19 型の緑と S12 型の赤を足した (D-4 (vii)(viii))。中-5 = 完了条件 6 を実 commit `0d0f8c9` の再現に差し替えた (D-5、§2.2 の 9)。中-6 = 訂正註を §0 の `:5` の上の v0.26 の行に置き、J-2 を改める旨を書く (D-3)。低-7 = `tools/tests` の基準を「585 + 新規 N」にした。低-8 = 2 文 → 1 文の fixture を足した (D-4 (v))。

## 2. WP-1 — `replace` 区間の対を別写像で足し、byte 一致する塊の鍵を保つ

### 2.1 触ってよいパス

- `tools/check_comment_provenance.py` — `replace` 区間の対の写像 (新設)、`_plain_block_keys` の鍵の判定、`check_provenance_semantics` の (2) の診断の組み立てのみ。**`_align_scope_bodies` の戻り値**、CH-ID 有りの塊の対応付け、(1)(3)(4)(5)(6)、`--register` には触らない。
- `tools/tests/test_comment_provenance.py` — `test_r89_*` を足す。既存のテストは変えない。
- `docs/design/CODE_COMMENT_PROVENANCE_V1.md` — §0 の `:5` の上の v0.26 の行だけ。既存の行は書き換えない。
- 件数 pin がこの変更で動く場合だけ、その pin (実測して報告に書く)。

### 2.2 完了条件

各テストは合成ソース (または使い捨て repo) を `--base` に掛け、観測対象 (緑なら「`§4.1 (2)` の行が 0」、赤ならその行の存在と鍵・件数の文言) を 1 件以上 assert する (空振り禁止)。

1. **R-71 型が緑** (D-4 (i))。
2. **本文を 1 字変えると赤**。失敗行の `(old 1, new 0)` を逐語で assert する (D-1 の byte 一致ゲート、D-4 (ii)、守る条件 (c))。
3. **塊の移動は赤**。既存テスト `test_r63_block_moved_between_identical_siblings_is_red` が緑のままであることで担保する (D-2 (i)、D-4 (iii))。
4. **`replace` 区間の長さが違う場合 (旧 1 → 新 2)**。塊が新側の 1 番目に付けば 0 行、2 番目に付けば `§4.1 (2)` が出る (D-4 (iv))。
5. **同 (旧 2 → 新 1)**。塊が残る側に付けば 0 行、消える側に付けば `§4.1 (2)` が出る (D-4 (v))。
6. **R-67 型は赤のまま**。基準 rev に在る関数に docstring を初めて足すと `old 0, new 1` が出る (D-2 (ii)、D-4 (ix))。
7. **S10 型が緑のまま**。旧版に無い塊を、書き換えられた文の直前に足しても `§4.1 (2)` は 0 行 (D-4 (vi))。
8. **種別・名前の条件**。改名・種別違いの書き換えの直下の塊は赤 (S12 型)、同じ種別の別の文への差し替えの直下の塊は緑 (S19 型) (D-4 (vii)(viii)、D-2 (vi))。
9. **実 commit の再現**。`0d0f8c9` を使い捨て repo で再現すると、現行の 2 行 — `FAIL (§4.1 (2)) …:619 ('PostgresBackend.all_field_constraints', 'stmt#1') … (old 1, new 0)` と `…:477 ('PostgresBackend.all_field_types', 'stmt#1')` — が **0 行**になる (D-5)。
10. **設計の訂正註と版数** (D-3)。§0 の `:5` の上に v0.26 の行が在り、D-3 の (1)〜(4) を書いていて、既存の行が書き換わっていない。diff を逐語で §6 に残す (**監査照合**)。
11. **`tools/tests` 全体が緑** (**585 + 新規 N**。N は実装担当が報告)。集計行を逐語で §6 に残す (**監査照合**)。
12. **下の対応表に対応の無い行が無い** (**監査照合**、本表)。

### 2.3 完了条件 → 変異

`mutate.py` は最初の失敗で止まるので、変異 1 件につきテスト 1 件を指す (すべて `expect=red`)。

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 1 | M1: `replace` 区間の対応付けを外す (`equal` だけを対応とする) | 完了条件 1 のテストが赤 |
| 2 | M2: 塊の本文の byte 一致の条件を外す (対になった文なら本文が違っても同じ鍵) | 完了条件 2 のテストが赤 |
| 3 | M3: `replace` の対を「同じ区間の中ならどの文でも同じ鍵」に緩める | 完了条件 3 のテスト (既存の移動テスト) が赤 |
| 4 | M4: 区間長が違うとき index で対にせず、区間全体を 1 つの対として扱う | 完了条件 4 の赤側のテストが赤 |
| 5 | M4 と同じ編集 (対象テストを完了条件 5 の赤側にして 1 回追加実行する) | 完了条件 5 の赤側のテストが赤 |
| 6 | M5: `old 0, new 1` (基準 rev に在る symbol への新規塊) を免除する | 完了条件 6 のテストが赤 |
| 7 | M6: byte 一致のゲートを外し、`replace` の対を無条件に鍵の対応に使う | 完了条件 7 のテストが赤 |
| 8 | M7: 対にする条件からノード種別・名前の一致を外す | 完了条件 8 の S12 型 (赤側) のテストが赤 |
| 9 | M1 と同じ編集 (対象テストを完了条件 9 にして 1 回追加実行する) | 完了条件 9 のテストが赤 |
| 10・11 | 監査照合 (diff と集計行を逐語で §6 に残す) | — |
| 12 | 監査照合 (本表) | — |

### 2.4 道具の引数 (main checkout を cwd にし、`SP` を export する)

- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r89 -- tools/tests/test_comment_provenance.py -q`
- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r89 -- tools/tests -q` (基準 585 + 新規 N)
- `tools/dev/mutate.py "$SP/r89-mutations.json" -C .claude/worktrees/r89 --wait 1800`
- `tools/dev/gate.py -C .claude/worktrees/r89 --label r89` (**監督のみ**。root の増分 0 を見る)
- python は main checkout の `.venv/bin/python`。終了コードは pipe の外で取る。

### 2.5 範囲外 (直さない)

- 経緯を運ばない新しい docstring の受け皿を作ること (D-2 (ii)、`RM`:511 の【追記 (R-67)】)。
- D-2 (vi) の既知の限界を塞ぐこと (同じ種別の別の文への差し替え)。
- `check_comment_provenance.py --base` を CI・pre-commit・`finalize.py` に組み込むこと (現状どれも呼んでいない。実測)。
- §4.1 (1)(3)(4)(5)(6)、`--register`、§9.3・§9.4 の判定。

## 3. 経緯トークンの規律

`tools/` と `tools/tests/` の追加行に経緯トークンを足さない (§4.1 (5))。docstring に `R-89:` と文書パスを書くのは可 (D-2 (vi) の限界は docstring に書く)。設計文書の訂正註は規約どおり日付を持つ。

## 4. レビューと受け入れ

- **設計レビュー 1 回** — 実施済み (§1.5)。
- **コードレビュー 1 回** (実装後、別に起動した `reviewer`)。
- **受け入れ監査 1 回** (`evidence-auditor`)。受け入れ判定は監督が完了条件 → 変異の対応表と集計行を照合して行う (Class B)。

## 5. 訂正の扱い

本書への訂正は §1〜§4 の本文を書き換えず、§6 に訂正註として日付とともに追記する。

## 6. 実施記録 (統合時に監督が埋める)

### 6.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-23)】完了条件 5 の赤側 fixture と変異 M3・M4 の形。** 完了条件 5 (旧 2 文 → 新 1 文) の赤側は「塊が丸ごと消える」形だと `_replace_pairs` もゲートも経由せずどの変異でも判別できないので、「塊は旧第 2 文に付いたまま新版の唯一の文の直前に残る」形にした (赤の理由は index ごとの対応)。M3 は「`replace` 区間内ならどの文でも同じ鍵」では当該 fixture に区間が無く無作用なので、「同一 scope 内で本文一致する任意の旧塊を鍵にする」形に広げた。M4 の潰し先は旧 `i1` ではなく `i2-1` (旧 2 → 新 1 の赤側を判別するため)。
- **【監督裁定 1】** コードレビュー 1 の中-1 は (i) を採用: byte 一致ゲートの照合は内部識別 (`_internal_scope_and_anchor_for_block`、`#k` 付き) で行い、同名の兄弟 scope 間の移動は赤のまま (新テスト + M8)。設計 v0.26 の行にもこの扱いを書いた。
- **【監督裁定 2】** 変更セット自身を `--base fadd758` に掛けると `_plain_block_keys` の docstring 書き換えで §4.1 (2) が 1 行出る (`tools/check_comment_provenance.py:2784 … (old 1, new 1)`)。未登録の塊 (CH-ID 無し) の言い換えなので R-68 の手順の対象外、正当な赤として記録する。(5) は 0 行。

### 6.2 実施と受け入れ

- **差分**: `tools/check_comment_provenance.py` (`_replace_pairs`・`_internal_scope_and_anchor_for_block` 新設、`_plain_block_keys` 拡張。`_align_scope_bodies` の戻り値・(1)(3)(4)(5)(6)・`--register` 不変)、`tools/tests/test_comment_provenance.py` (`test_r89_*` 12 件、既存 289 件不変)、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` (`:5` の上に v0.26 の行)。`tools/change_class.py` → `class=B`。
- **道具の出力行**: `pt: 301 passed` (対象ファイル、289 + 12)、`pt: 597 passed` (`tools/tests`、585 + 12)。`mutate: 10 mutations, 10 as expected, restores verified 1/1 files (sha256 x2)` (M1〜M8、M4b、M1b)。完了条件 9: 実 commit `0d0f8c9` の使い捨て repo で現行の 2 行 (`…:619 ('PostgresBackend.all_field_constraints', 'stmt#1') … (old 1, new 0)`、`…:477 (… all_field_types …)`) が 0 行 (テストは `code == 1` と `§4.1 (2)` 12 行の正の観測を持ち、`0d0f8c9` が無ければ fail)。`--register` OK 87/430、`check_doc_refs` 0、`public_value_scan` 0。
- **設計レビュー 1** (高 3・中 3・低 2、全件反映)、**コードレビュー 2 巡** (1 巡目 中 1・低 5 → 差し戻し 1; 2 巡目 中-1 閉、残り 2 = v0.26 行の追記と経緯 ID の除去 → 監督が反映)、**受け入れ監査 1** (完了条件 1〜9・12 充足、10・11 は記録待ち → 本節で充足、未充足 = 経緯トークン 1 → 除去済み)。設計レビューの 25 シナリオは実装で全一致。
- **完了ゲート** (監督単独、`tools/dev/gate.py -C .claude/worktrees/r89 --label r89`): `3874 passed, 2 subtests passed in 336.85s (0:05:36)`、`judge=PASS`、実行クラスタ差分 0 (root は tools/ の変更で不変。`finalize.py --tools-tests` が最終の木で `tools/tests` を回す)。
- **最終判定**: 受け入れ。台帳 R-89 を閉じる (v1.97)。
