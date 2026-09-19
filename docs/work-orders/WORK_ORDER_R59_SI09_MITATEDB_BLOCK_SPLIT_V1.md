# 作業指示書 — R-59 `security/CONTROL_MAPPING.md` の SI-09 / MitateDB-api を名前付き小ブロックへ分ける

## 0. 版数・位置づけ

- **v1.0 (2026-09-19)。** 基点 main `2d47383`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-59。変更クラスは **Class C** (`security/` を触る。契約は触らない)。
- **【訂正註 2026-09-20 (監督)】** 変更クラスの宣言 **Class C は誤り**で、`security/` 配下を触る本件は **Class D** である (`docs/design/ROADMAP_POST_PHASE7_V1.md` §9 の 8 の表、`tools/change_class.py`。R-56 の設計レビューの指摘)。本文は書き換えない (§1.8 の 57)。D が求める依頼者裁定の逐語記録に当たるのは依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) で、版付きの security-contract 決定に当たるのは `security/CONTROL_MAPPING.md` の版 (R-54 は 2.10、R-59 は 2.11) である。事後の依頼者確認は引き継ぎ書 `docs/work-orders/HANDOVER_20260920_FABLE.md` §4 で伺っている。加えて、**R-59 は受け入れ監査を入れていない** (§2)。純粋な移動で照合は道具が行い、コードレビューが独立に再現したためだが、**D の手順は受け入れ監査を求める** — D の手順からの逸脱として記録する。
- 設計は新しく起こさない。方法は `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` v1.0 (依頼者裁定 2026-09-18「複数ブロックを許す」、§5 の見出しの書式、§6 の照合、§7 の訂正註 = 残った側の指示語も見る) がそのまま定めており、本件はその 3 回目の適用である。適用の計画 (どの bullet を移すか) のレビューは §1.6 のレビューが兼ねる。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. WP-1 — platform upgrade の主張を名前付き小ブロックへ移す

**目的**: SI-09 / MitateDB-api の既定の小ブロックは 14,229 字 (上限 15,200 まで残り 971)。次の追記で上限に張り付く。主張の文を 1 字も変えずに、主題の塊を名前付き小ブロックへ移して余地を作る。

### 1.1 枠 (監督確定)

- 名前付き小ブロックは 1 本: `### MitateDB-api -- platform upgrade`。移す候補は、`apply-platform-migration`・migration `0013`・`0014`・numbered set・runbook §10 の表の受理に関する bullet (R-52 WP-3 のコードレビューの実測で 7 行・5,223 字。R-54 WP-3 の訂正後の現物で測り直す)。Control / Evidence / Status のどの軸の bullet も、同じ軸へ移す。
- 帰属の判断は bullet ごとに行い、主題に収まるか迷う bullet は**移さず**報告に挙げる (裁定は監督)。1 つの bullet が 2 つの主題を語る場合は分けない (文を変えない)。
- r2db-api 側は 2,211 字なので触らない。peer 間で小ブロックの構成が非対称になるのは構わない (SI-08 の先例)。
- 指示語の検査は**両側**で行う: 移した側と残った側の両方について、`above` / `below` / `the same` / 裸の `` `::name` `` / `this file` の類が指す先が、分割の後も同じ小ブロックの中で辿れること。辿れなくなる行が在れば、移す範囲を変えて解消できるかを先に試し、文の訂正が要るなら実装せず報告する (文を変えると純粋な移動でなくなり、`CONTROL_MAPPING_HISTORY.md` への移動が要る — 裁定は監督)。
- SI 節の preamble に「最長ブロック」の実測を述べる文が在る (版 2.9・2.10 の先例で in place 更新)。分割後の実測値に合わせて更新する。版は 2.10 → 2.11、版数行は先例の書き方で。
- 他文書が移した bullet の所在を `SI-09 / MitateDB-api / <軸>` の形で現在形で指している箇所を grep し、runbook・README・現行の設計文書で現在形のものだけ `SI-09 / MitateDB-api / platform upgrade / <軸>` に合わせる。記録文書 (work order・handover・設計メモの記録節・`*_HISTORY.md`) は触らず所在を報告する。
  - **【訂正註 2026-09-19 (コードレビューの中 1 件、監督裁定)】**「記録節は触らない」は先例と合わなかった。R-50 WP-3 の完了条件 W3-9 と `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` の訂正註の予告が先例であり、日付つきの訂正註の**追記**は `OPERATING_CONDITIONS.md` §1.8 の 56 に反しない。同書の 3 箇所と `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` の 1 箇所に、監督が訂正註を足した (本文は書き換えていない)。

### 1.2 触ってよいパス

- `security/CONTROL_MAPPING.md`
- §1.1 の最後の項で現在形の所在を直す必要が出た文書 (報告に列挙)。無ければ 0。
- それ以外 (テスト・道具・`CONTROL_MAPPING_HISTORY.md`) は触らない。既存の検査が新しい小ブロックで赤になったら直さず報告する。

### 1.3 完了条件

1. 分割の前後で (SI, peer, 軸, 本文) の多重集合が一致する: `tools/check_control_mapping_split.py --base 2d47383` が `missing=0 added=0`、`moved` は移した bullet 数、`subsequence=ok`、終了コード 0 (`--expect` の使い方は道具の help と R-50 の作業指示書の先例に従う)。
2. `conformance-tests/test_control_mapping_register.py` が緑 (見出しの書式・既定の小ブロックが先頭・各小ブロックに 3 軸・上限・名前付き 3 本まで)。
3. 分割後の両小ブロックの字数を測って報告する。既定の小ブロックの残りが 5,000 字以上であること (足りなければ移す範囲を監督に上げる)。
4. 指示語の検査 (§1.1) の結果を、移した側・残った側それぞれ「確認した指示語の一覧 → 指す先 → 同じ小ブロックに在るか」の表で報告する。辿れなくなった行が 0。
5. `tools/check_doc_refs.py` が 0 dangling、`tools/public_value_scan.py` が 0 flagged。
6. 下の対応表に対応の無い行が無い。

### 1.4 完了条件 → 変異

| 完了条件 | 変異 |
|---|---|
| 1 | M1: 移した bullet の 1 つを別の軸 (Control → Evidence) へ置く → `check_control_mapping_split.py` が非 0 (道具の実行で示す。pytest の変異ではないので、手で 1 回行い scratchpad の複製の上で実行する — 作業ツリーを変異させない) |
| 2 | M2: 名前付き小ブロックの見出しを `### MitateDB-api -- platform  upgrade` (空白 2 つ) にする → register テストが赤 (`tools/dev/mutate.py`) |
| 3・4・5 | 監査照合 (報告の表と道具の出力行) |
| 6 | 監査照合 (本表) |

### 1.5 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/r59-si09-split -- conformance-tests/test_control_mapping_register.py -q`
- `tools/dev/pt.py -C .claude/worktrees/r59-si09-split -- tools/tests -q -k control_mapping` (conformance と 1 回に結合しない)
- `./.venv/bin/python tools/check_control_mapping_split.py --base 2d47383` (worktree の中で)
- `tools/dev/mutate.py "$SP/r59-mutations.json" -C .claude/worktrees/r59-si09-split`

### 1.6 レビュー

コードレビュー 1 回 (別起動)。観点: 帰属の判断、両側の指示語、字数の独立再測、preamble の実測文、他文書の所在。結果はファイルに書かせる。

### 1.7 記録 (統合時に監督が埋める)

- 実施 2026-09-19。移した bullet は 15 (Control 12 / Evidence 2 / Status 1)。`tools/check_control_mapping_split.py --base 2d47383 --expect …` は終了コード 0、`missing=0 added=0 moved=15 empty_axis_added=1 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical` (preamble の差分は版数行と最長ブロックの実測文の 2 つだけ)。register テスト `34 passed`、`tools/tests -k control_mapping` は `58 passed, 449 deselected` (別呼び出し)。`check_doc_refs` 0 dangling、`public_value_scan` 0 flagged。
- 字数: 既定 4,612 (残り 10,588) / `platform upgrade` 9,616 (残り 5,584)。分割前は 14,229 (残り 971)。文書の最長ブロックは SI-14 / r2db-api の既定 12,624。完了条件 3 (既定の残り 5,000 字以上) を満たす。
- 完了条件 → 変異 → 結果: 1 ← M1 (複製の上で移した bullet の 1 つを Control → Evidence へ置く) → 道具が終了コード 1、`missing=1 added=1 moved=14`。作業ツリーは変異させていない / 2 ← M2 (見出しの空白 2 つ) → `expect=red got=red`、赤になったのは `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_subblock_headings_use_the_allowlisted_form`、復元は sha256 2 回で照合 / 3・4・5 ← 監査照合 (上の道具の出力行と、実装報告の指示語の表。コードレビューが字数・道具の出力・指示語を独立に再現した。表から漏れていた `item (5)(6)` の 1 件は実害なしとレビューが確認) / 6 ← 本表。
- 監督裁定: (1) Status の 1 行は**移す** (残すと `above` の指す先が別ブロックへ消える)。既定の小ブロックの Status は `- —` になるが、deprovision の本番未実施は SI-00 / MitateDB-api が現在形で開示しており、Status が `- —` の既定の小ブロックは既存の形である。(2) `ops inventory` に触れる 5 bullet は移さない (既定に 10,588 字の余地があり、2 本目の名前付き小ブロックを今作る理由が無い)。(3) 他文書 4 箇所は先例どおり日付つきの訂正註を足した (§1.1 の訂正註)。(4) `SI-08's own MitateDB-api block` の指し方が一意でない件は台帳 R-60 に起票した。
- コードレビュー 1 回: `security/CONTROL_MAPPING.md` への差し戻し無し、クラスの引き上げ無し。
- 完了ゲート (監督が単独実行、コミット前の同じ木): `gate: 3745 passed, 2 subtests passed in 316.27s (0:05:16)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0`。受け入れる。

## 2. 受け入れ

監督が完了ゲート (`tools/dev/gate.py -C .claude/worktrees/r59-si09-split`) の集計行と §1.3 を照合して判定する。機械判定が主なので受け入れ監査は入れない (Class C だが、純粋な移動で照合は道具が行う — R-50 の WP-2 と同じ性質。レビューがクラスを上げた場合は入れる)。
