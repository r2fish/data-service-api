# 作業指示書 — R-70 `security/CONTROL_MAPPING.md` の SI-09 / MitateDB-api / platform upgrade の Platform-upgrade runbook の主張を runbook と同じ強さに直す

## 0. 版数・位置づけ

- **v1.0 (2026-09-21)。** 基点 main `4538e1e` (R-65 の統合後)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-70。変更クラスは **Class D** (`tools/change_class.py` の実測 `class=D`)。D が求める依頼者裁定は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) の下で監督が下し、事後確認を引き継ぎ書で伺う。版付きの security-contract 決定は `security/CONTROL_MAPPING.md` の版 **2.17**。
- 設計は新しく起こさない。作法は Update convention (`security/CONTROL_MAPPING.md` の preamble) と、先例 `docs/work-orders/WORK_ORDER_R60_R61_CONTROL_MAPPING_WORDING_V1.md` がそのまま定める。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う。

## 1. WP-1 — 1 つの Control の主張を訂正し、版を 2.17 に上げる

### 1.1 枠 (監督確定)

- **欠陥**: 現行の主張は「ready が gate するのは candidate deploy と traffic switch であり、remediation stage は *instead* 3 条件 (isolated proof・independent audit・requester's approval) が gate する」と述べる。`instead` は「3 条件は remediation stage にだけ掛かる」とも読める。runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` の §10 の冒頭 (`Against production, nothing in stage 2 or stage 4 runs until three things are true …`) と §10.10 (`… before anything in §10.10.1 or §10.10.3 runs … Gate-0 ready is not one of the three`) は、3 条件が **stage 2 と stage 4 の両方**の前に要ると述べる。正本順位 5 の主張が runbook より弱く読める。
- **採用形 (確定文)**: 当該行の `, while the remediation stage is gated instead by the isolated proof, the independent audit and the requester's approval -- including that stage's own single move of traffic percentages,` を `; against production, the isolated proof, the independent audit and the requester's approval all come before anything in either state-changing stage runs -- the candidate stage, which ready gates as well, and the remediation stage, which ready does not gate -- including the remediation stage's own single move of traffic percentages,` に in place で直す。行の他の部分は 1 字も変えない。3 条件を新しく立てるのではなく、runbook が既に述べる範囲 (両 stage) に主張を合わせるだけである。runbook は触らない。
- 旧行は逐語で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` の末尾へ、先例の形の題を付けて移す。版数行は R-60 / R-62 の形で 2.17 に置き換える。preamble の `Blocks per subsection` の段に版 2.17 の再実測文を足す。**この訂正で当該ブロックが文書の最長になる**ので、`Length cap measurement` の段の「最長ブロック」の実測も in place で合わせる (同じ日付の R-65 の文の更新で、訂正註は足さない — 旧文は版 2.16 の 1 コミットにしか存在せず、その段の訂正註は 2.15 以前の旧文を保存している)。
- 同じ小ブロックの production-restriction の主張 (`whose stage 2 preconditions this block's own Platform-upgrade runbook claim below states`) は、訂正後も真である (訂正後の主張は stage 2 の前提を述べている) ので触らない。

### 1.2 触ってよいパス

- `security/CONTROL_MAPPING.md`、`security/CONTROL_MAPPING_HISTORY.md`。それ以外は触らない。

### 1.3 完了条件

1. 確定文が逐語で入っており、当該行の差分が §1.1 の 1 区間だけである。
2. 旧行が基点 `4538e1e` の行と byte 一致で履歴の `## SI-09` に在る (機械照合)。
3. `tools/check_control_mapping_split.py --base 4538e1e --expect "missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` が終了コード 0。
4. `conformance-tests/test_control_mapping_register.py` が緑。
5. 訂正後の主張が runbook の 2 段 (§10 の冒頭、§10.10) と矛盾せず、言い過ぎ・言い足りずが無い (文のレビュー)。runbook・`docs/` の他の文書に差分が無い。
6. ブロック長の実測 (対象ブロックの前後、文書の最長、残り) が preamble の 2 つの段の数値と一致する。物理行は 1,400 字未満。
7. `tools/check_doc_refs.py` 0 dangling、`tools/public_value_scan.py` 0 flagged、`tools/change_class.py` が `class=D`。
8. 下の対応表に対応の無い行が無い。

### 1.4 完了条件 → 変異

| 完了条件 | 変異 |
|---|---|
| 4 (1 主張 1 行) | M1: 新しい行の `; against production, the isolated proof` の直前に改行を入れ、後半を `- ` で始まらない物理行にする → `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` が赤 (`tools/dev/mutate.py`) |
| 1・2・3・5・6・7 | 監査照合 (差分、機械照合の出力、道具の出力行、文のレビュー、実測) |
| 8 | 監査照合 (本表) |

### 1.5 レビューと受け入れ

文のレビュー 1 回 (別起動)、受け入れ監査 1 回 (別起動)。監督が完了ゲートの集計行と §1.3 と監査のパケットを照合して判定する。確定文の差し替えは監督がスクリプトで行った (実装担当は起動していない — 1 区間の置換で、裁量の余地が無い)。

### 1.6 記録 (統合時に監督が埋める)

- 実施 2026-09-21。確定文の 1 区間の置換で、旧行 1,157 字 → 新行 1,305 字 (上限 1,400)。旧行は基点 `4538e1e` の行と byte 一致で履歴の `## SI-09` の末尾に在る (監督・レビュー・監査の 3 者が機械照合)。
- `tools/check_control_mapping_split.py --base 4538e1e --expect "missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` 終了コード 0。register テスト `34 passed`。`check_doc_refs` 0 dangling、`public_value_scan` 0 flagged、`change_class.py` は `class=D`。
- 字数: SI-09 / MitateDB-api / `platform upgrade` 12,533 → **12,681** (残り 2,519)。文書の最長ブロックになった (次は SI-14 / r2db-api の既定 12,624、不変)。preamble の 2 つの段はこの実測に合わせた。
- 完了条件 → 変異 → 結果: 4 ← M1 (新しい行を 2 物理行に割る) → `expect=red got=red`、赤は `test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` (失敗メッセージが新しい本文を名指す)、復元は sha256 2 回で照合 / 他 ← 監査照合 / 8 ← 本表。
- 文のレビュー 1 回: runbook の 3 箇所 (§10 の冒頭、stage 表、§10.10) と照合して言い過ぎ・言い足りず無し。Low 2 件 (版数行の `as well` が「remediation も ready が gate する」と誤読されうる / 再実測文の括弧で 12,533 が残り字数と読まれうる) は**採用して直した**。Low・既存の 1 件 (production-restriction の主張の `states` が網羅と読まれうる) は台帳 R-72、Info の 1 件 (register テストのコメントの古い実測) は台帳 R-73 に起票した。`Length cap measurement` の段を訂正註なしで更新した裁定は維持する (版ごとの実測は `Blocks per subsection` の段の各文が保存している)。
- 受け入れ監査 1 回: 完了条件 1〜8 は全件充足、未充足 0。留保 (レビューの Low の逐語がログに無い、ゲートログ単独では測った木を同定できない) は記録上のもので、判定に影響しない。
- 完了ゲート (監督が単独実行、最終の木): `gate: 3796 passed, 2 subtests passed in 317.78s (0:05:17)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0`。**受け入れる。**
