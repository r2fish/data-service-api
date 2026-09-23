# 引き継ぎ — 2026-09-21 その 2 (R-65・R-70・R-64 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260921_FABLE.md` で、**同書の §4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。依頼者の指示 (2026-09-21) により R-64 の統合で中断した。

## 1. 現在地

- ローカルの main は `833e106` に本書のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-64 の最終の木で `3805 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0 (ゲートの後の変更は register テストの docstring 1 文だけで、register テスト `43 passed` を再実行済み)。`tools/tests` は `568 passed` (R-68 の統合時。以後 `tools/` は触っていない)。
- 進行中のサブエージェントは無い。未コミットの作業は無い。`security/CONTROL_MAPPING.md` は版 **2.18**、台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.81。

## 2. 本チャットで閉じたもの

| 項目 | main | 要点 |
|---|---|---|
| R-65 (SI-08 の既定の小ブロックの分割) | `4538e1e` | 両 peer の Phase 10 の (a)〜(e) の Control 23 件を `capacity and concurrency` へ純粋に移動 (版 2.16)。r2db-api 既定 14,105 → 7,682、MitateDB-api 既定 13,023 → 5,555。**移動で偽になる指し先 1 件** (SI-09 の `0014` の主張が ceiling の所在として名指す小ブロック) を同じ版で訂正した。preamble の 2 つの段 (`Length cap measurement`・`Blocks per subsection`) を現行の実測に直した。gate 3796 |
| R-70 (SI-09 の runbook の主張が runbook より弱く読める) | `3711a34` | `gated instead by` の 1 区間を「3 条件は状態を変える両方の stage の前に要る」に訂正 (版 2.17)。この訂正で SI-09 / MitateDB-api / `platform upgrade` が 12,681 字 (残り 2,519) で**文書の最長**になった。gate 3796 |
| R-64 (引かれたテスト名の解決検査) | `833e106` | register テストが `ast` の索引 (`async def` を含む) でテスト名を解決する。完全形は 4 つの test directory の中の path と def、裸の形は peer の範囲。**固定するのは名前が範囲に実在することだけ** (同名の def が両 peer に在る 124 件の取り違えとファイルの一致は見ない)。解決できなかったのは 1 件 (SI-06 / r2db-api の `…_all_11_endpoints`) で、同じ変更セットで直した (版 2.18)。変異 9 件が赤。gate 3805 |

- **起票**: R-72 (SI-09 の production-restriction の主張の `states` が網羅と読まれうる)、R-73 (register テストの `MAX_BLOCK_LENGTH` の上のコメントの古い実測)、R-74 (`conformance-tests/CONDITIONS.md` のテスト名の同型の検査)。
- 作業指示書: `docs/work-orders/WORK_ORDER_R65_SI08_DEFAULT_BLOCK_SPLIT_V1.md`、`docs/work-orders/WORK_ORDER_R70_SI09_RUNBOOK_CLAIM_WORDING_V1.md`、`docs/work-orders/WORK_ORDER_R64_CONTROL_MAPPING_TEST_NAME_RESOLUTION_V1.md`。

## 3. 次の一手

1. **R-66** (r2db-api の配備 script が `0013` を流していない + 両 peer の control / provision role の `statement_timeout` の判断)、**R-67** (両 peer の `check_auditreader_statement_timeout` の docstring。同型 helper なので変更クラスを `RM` §9 の 8 の表で判定)、**R-69**、**R-71** (MitateDB-api の catalog の打ち切りが `VALIDATION_FAILED` に写る)。順序は監督が着手時に決める。R-71 は client に見える挙動なので先にする理由が在る。
2. その後: R-72、R-73、R-74。
3. 依頼者の指示を待つものは前書と同じ。push の再開は依頼者の指示による。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(i) R-65・R-70・R-64 の決定の事後報告と確認。** 3 件とも Class D で、決定 (各作業指示書の §1 と訂正註、`security/CONTROL_MAPPING.md` 2.16〜2.18 の確定文) は依頼者指示 2026-09-19 の委任の下で監督が下した。前書 §4 (a)・(g) に足す。client に見える挙動の変更は無い。
- **(j) `conformance-tests/COLLECTION_FLOOR` は 3326 のままである** (現行の gate は 3805)。フェーズ10 の後、どのチャットも上げていない。上げるかどうか・上げる時機は未決 (`OPERATING_CONDITIONS.md` §1.3 の 25)。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

- **テスト名の実在を調べる索引は `ast` で作る。** 正規表現 `def test_` は `async def` を落とす。async の test は `r2db-api/tests` にだけ 95 本在るので、r2db-api だけが不可視になり「証拠のテストが無い・peer の取り違え」に見える (R-64 の最初の調査の 19 件は誤りで、実際は 1 件。設計レビューが見つけた)。**調査担当の「無い」という結果は、枠を決める前に監督が別の方法で測り直す。**
- **小ブロックを移す前に、同じファイルの中でその小ブロックを名指す文を grep する** (`` `SI-NN`'s `<peer>` `default block` `` の形)。純粋な移動でも、名指す側の文が偽になる (R-65)。移動が原因の指し先の訂正は同じ版に入れ、split の道具は 2 段 (純粋な移動の段、最終の木) で照合する。
- **preamble には実測を述べる段が 2 つ在る** (`Length cap measurement` と `Blocks per subsection`)。版を上げるたびに後者へ再実測文を足し、最長ブロックが変わったら前者も直す。版数行に行番号を書かない (自分の変更でずれる)。
- **引き継ぎチップの worktree は古くなかった** (local main と同じコミットに在った)。着手時に `git worktree list` で確かめ、共有ツリーは checkout しない (`OPERATING_CONDITIONS.md` §1.2 の 14)。
- **自動生成の worktree 名 (`語-語-数字6桁`) は `tools/public_value_scan.py` の R3 (project id) に当たる。** コミットする文書には `<担当 worktree>` と書く。
- **`tools/check_comment_provenance.py --base` は `conformance-tests/` のコードを足す変更では構造上赤になる** (走査対象外)。求めるのは `--register` の緑である。
