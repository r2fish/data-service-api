# 作業指示書 — R-72 SI-09 / MitateDB-api / platform upgrade の production-restriction の主張の「states」

## 0. 出所と基点

- **v1.0 (2026-09-23)。** 基点はローカル main `fadd758` (作業ツリー `.claude/worktrees/r72`)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-72 (R-70 の文のレビューの Low・既存の 1 件)。
- **変更クラスは Class D** (`security/CONTROL_MAPPING.md` の Update convention による訂正)。R-70 (`docs/work-orders/WORK_ORDER_R70_SI09_RUNBOOK_CLAIM_WORDING_V1.md`) の形に倣い、1 区間の置換で裁量の余地が無いので実装担当は起動せず監督が直接行う。文のレビュー 1 回、受け入れは監督が対応表と道具の出力で判定する。
- 決定は 2026-09-19 の委任の下で監督が下し、引き継ぎ書で依頼者へ事後報告する。

## 1. 問題設定と確定文

`security/CONTROL_MAPPING.md` の SI-09 / `### MitateDB-api -- platform upgrade` の production-restriction の主張 (`:826`) は「whose stage 2 preconditions this block's own Platform-upgrade runbook claim below **states** rather than this claim restating a subset of them」と書く。runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.10 の前提は 6 項目 (§10.8 の行の受理 / item (8) の算術 / 3 条件 / stage 1 の読了 / `ledger-unreadable` が無いこと / 本番が isolated の読みと同じ digest で差が無いこと) で、この block の Platform-upgrade runbook claim (`:831-833`) が触れるのは 3 条件と算術だけである。`states` は網羅と読まれうる。

**確定文 (置換する 1 区間)**: `… claim below states rather than this claim restating a subset of them` → `… claim below states in part -- the runbook's section 10.10 holds the complete list -- rather than this claim restating a subset of them`。他の語は変えない。

**却下した代替案**: 6 項目を主張に書き足す (最長ブロックを太らせ、runbook と二重管理になる)、Platform-upgrade runbook claim 側を網羅にする (同じ理由)、`states` を `states some of` に変える (どこが完全な一覧かを指さない)。

## 2. Change Set Manifest

| 触ってよいファイル | 触らないファイル |
|---|---|
| `security/CONTROL_MAPPING.md` (`:826` の 1 区間、`:5` の版数行 2.21 → 2.22、preamble の Length cap 段の実測値、Blocks per subsection 段への再測定文の追記)、`security/CONTROL_MAPPING_HISTORY.md` (`## SI-09` 末尾に旧行を逐語で、R-70 の形)、本書、台帳 (監督) | それ以外の全部 (`spec/`、`conformance-tests/`、両 peer、runbook) |

| # | 完了条件 | 照合 |
|---|---|---|
| 1 | 主張の差分が §1 の 1 区間だけ (`git diff` の `:826` の変更は確定文の置換のみ) | 監査照合 (diff) |
| 2 | 旧行が `CONTROL_MAPPING_HISTORY.md` の `## SI-09` に byte 一致で在る (`git show HEAD:security/CONTROL_MAPPING.md` の 826 行目と比較) | 監査照合 |
| 3 | `tools/check_control_mapping_split.py --base fadd758 --expect "missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` が終了コード 0 | 道具 |
| 4 | preamble の Length cap 段と Blocks per subsection 段の実測値が現物の block 長 (`_split_sections` → `_iter_section_subblocks` → `_subblock_block_text`) と一致し、最長ブロックが SI-09 / MitateDB-api / platform upgrade のまま、`MAX_BLOCK_LENGTH` 15200 と `MAX_LINE_LENGTH` 1400 の内 | 監査照合 (実測の出力行) |
| 5 | `conformance-tests/test_control_mapping_register.py` が緑 (R-88 の位置参照の検査を含む)、完了ゲートの root 集計行が直前の main と同数 | 道具 (pt / gate) |
| 6 | 文のレビュー (言い過ぎ・言い足りず・runbook §10.10 との整合) で指摘が残っていない | レビュー |
| 7 | `check_doc_refs.py`・`public_value_scan.py` が緑、`tools/change_class.py` → D | 道具 |
| 8 | 上の表に照合の無い行が無い | 監査照合 |

変異は置かない (1 区間の文言の置換。R-70 と同じ扱い)。

## 3. 実施記録 (監督が書く)

### 3.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-23)】確定文の最終形。** 文のレビュー 1 (低 5 件) を受け、挿入句を括弧にし (`--` の 3 連で閉じ位置が曖昧)、対比の後半を「carrying a second partial copy」に改めた (「restating a subset」では両方が部分で、なぜ隣に寄せるかが読めない)。最終の 1 区間: `… claim below states in part (the runbook's section 10.10 holds the complete list) rather than this claim carrying a second partial copy`。「section 10.10」は §10.10.1〜.3 を含む広い読みで真 (レビュー指摘 3、監督裁定: この語のまま)。
- **【訂正註 2】** HISTORY の `## SI-10` の直前の `---` 区切りを復元した (挿入で食われていた)。preamble の 2.22 再測定文に、版 2.21 (R-88) が再測定せずに残した SI-08 の 2 ブロックの実測 (`10,304` / `8,053`) を併記した (R-72 の範囲外だが preamble の実測の陳腐化なので同じ変更セットで直す)。

### 3.2 実施と受け入れ

- **差分**: `security/CONTROL_MAPPING.md` (`:826` の 1 区間、版数行 2.22、Length cap 段 12,681 → 12,747 (2,453 left)、Blocks per subsection 段に 2.22 の再測定文)、`security/CONTROL_MAPPING_HISTORY.md` (`## SI-09` 末尾に旧行を逐語、R-70 の形)。監督が直接行い、`tools/change_class.py` → `class=D`。
- **照合**: 旧行は `git show fadd758:security/CONTROL_MAPPING.md` の 826 行目と byte 一致 (533 字)。`tools/check_control_mapping_split.py --base fadd758 --expect "missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` 終了 0 (**worktree 側の道具で実行する** — main の道具はその repo root を測る)。block 長は最長 SI-09 / MitateDB-api / platform upgrade 12,747 (次点 SI-14 / r2db-api 12,624)、物理行 599 字、R-88 の位置参照検査は緑 (`section 10.10` は位置参照でない)。`pt: 58 passed` (`test_control_mapping_register.py`)。`check_doc_refs` 0、`public_value_scan` 0。
- **文のレビュー 1** (低 5: HISTORY の `---`、`--` の 3 連、「complete list」の範囲、対比の論理、preamble の SI-08 数値の陳腐化 → 全件反映、指摘 3 は語のまま)。
- **完了ゲート** (監督単独、最終の木、`--label r72b`): `3874 passed, 2 subtests passed in 397.34s (0:06:37)`、`judge=PASS`、実行クラスタ差分 0 (直前の main と同数)。
- **最終判定**: 受け入れ。Class D の決定 (確定文) は 2026-09-19 の委任の下で監督が下し、引き継ぎ書で事後報告する。台帳 R-72 を閉じる (v1.96)。
