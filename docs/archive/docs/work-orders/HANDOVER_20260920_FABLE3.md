# 引き継ぎ — 2026-09-20 その 3 (R-68・R-60・R-61 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260920_FABLE2.md` で、**同書の §4・§5 と、そこが引く前々書の §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。

## 1. 現在地

- ローカルの main は `888b8e6` に本書のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-60 + R-61 の最終の木 (main へ統合済み) で `3789 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` は `568 passed`。
- 進行中のサブエージェントは無い。未コミットの作業は無い。

## 2. 本チャットで閉じたもの

| 項目 | main | 要点 |
|---|---|---|
| R-68 (登録済みのコメント塊を同じ変更セットで言い換えられない) | コード `b83d9aa`、記録 `3965fe4` | 再編集の経路は、基点 rev の訂正記録で基点の塊の基準を作り、基点の記録が作業ツリーの記録の先頭部分列 (date・reason・old・new の逐語一致) であることを要求し、作業ツリーにだけ在る訂正を基点の塊へ当ててから「文の削除だけ」を検査する。基点の記録が読めないときは 0 件ではなく失敗。rev 同士のガードはソースと同じ rev の記録を読む (訂正を足した変更セットがコミット前に `tools/tests` を赤にする性質は無くなった)。最初の適用として `ops.py` の CH-0538・CH-0539 を列の形に直した。設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` v0.24 §9.3、Class B、変異 19 件が赤。作業指示書 `docs/work-orders/WORK_ORDER_R68_PROVENANCE_SAME_CHANGESET_REWORD_V1.md` |
| R-60 + R-61 (`security/CONTROL_MAPPING.md` の 2 つの Control の文) | 変更 `b0f6e50`、記録 `888b8e6` | **版 2.14**。SI-09 / MitateDB-api / platform upgrade の 2 行: SI-08 の指し方を `default block` で一意にし、失効した「WP-E/WP-D 中は本番禁止」を「本番では runbook section 10 の gated procedure を通してだけ」の現在形に直した (stage 2 の前提は同じ小ブロックの runbook の主張を指す)。旧文は逐語で履歴へ。**Class D**、コード・spec・conformance-tests・migration・runbook の差分 0。作業指示書 `docs/work-orders/WORK_ORDER_R60_R61_CONTROL_MAPPING_WORDING_V1.md` |

- **起票**: R-69 (一部を既に削った文は R-68 の経路でも言い換えられない)、R-70 (`security/CONTROL_MAPPING.md` の Platform-upgrade runbook の Control が、stage 4 の前にも 3 条件が要るという runbook の文より弱く読める。Class D)。R-65 の行に preamble `:27`-`:28` の申し送りを追記した。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.77。

## 3. 次の一手

1. 前書 §3 の 2 の順の残り: **R-62** (r2db-api の `PostgresCell.catalog` が取引ごとの timeout を通らない)、**R-65**、**R-64** (着手時に実在しない 6 件も直す)、**R-66**、**R-67**。その後に **R-69**、**R-70** (R-70 は R-65 と同じ `security/CONTROL_MAPPING.md` を触るので、順序と変更セットの分け方を着手時に決める)。
2. 依頼者の指示を待つものは前書と同じ。push の再開は依頼者の指示による。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(e) R-60 + R-61 の決定の事後報告と確認。** Class D で、決定 (作業指示書 §1.1 の D-1〜D-6、設計レビュー・文のレビューの裁定、確定文から `and stage 4` を外した裁定) は依頼者指示 2026-09-19 の委任の下で監督が推奨として下した。前書 §4 (a) (委任が Class D に及ぶかの事後確認) に R-60・R-61 を足す。
- **(f) 性能差分を計測しなかった。** R-60 + R-61 は実行されるコードが 1 行も変わらない文書 2 ファイルの変更なので、§1.3 の 27 の性能差分を添えていない (監督裁定)。

## 5. worktree (前書 §5 に足すもの)

- 本チャットは、割り当てられた worktree `jovial-almeida-97c9fb` (branch `claude/jovial-almeida-97c9fb`) を使った (着手時にローカル main と同じ位置でクリーンだった。他の checkout への Edit/Write は実行環境が拒否する)。統合済みで未コミット 0。**削除は依頼者が行う。**

## 6. 本チャットで足した運用上の教訓

- **登録済みのコメント塊を言い換えるときは、受け皿に `### correction` を同じ変更セットで追記し、その CH-ID を持つ `src/` の path に `check_comment_provenance.py --base <rev>` を掛ける。** 合格は「FAIL 行 0・exit 0」(道具は成功時に必ず 1 行出す)。
- **root suite の testpaths は `tools/` を収集しない。** 完了ゲートの後の修正が `tools/` だけなら、ゲートの判定は有効で、`tools/tests` は `finalize.py --tools-tests` が見る。`security/` の `.md` は conformance の登録テストが読むので、触ったらゲートを回し直す。
- **設計レビューの反映で確定文が変わったら、変異の anchor が確定文に残っているかを見る** (R-60 の M1 は anchor が消えていた)。
- **文書に道具のログのファイル名を書くと `tools/public_value_scan.py` が project 識別子として拾うことがある。** 集計行・要約行だけを逐語で残す。
- **レビュー担当が API の利用上限で起動直後に落ちたら、リセット後に同じ発注文で起動し直せばよい** (worktree には何も残らない)。
