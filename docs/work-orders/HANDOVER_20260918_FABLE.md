# 引き継ぎ — 2026-09-18 (R-45 の WP-F・WP-D を統合し、受け入れ監査を経て R-45 を受け入れた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260917_FABLE.md` (同書の §5・§6 は引き続き有効)。前のチャットの scratchpad は読めないので、要るものは本書とリポジトリにだけある。監督のモデルは Fable (`OPERATING_CONDITIONS.md` §1.1 の 1)。

## 1. 現在地

- ローカルの main は `84ef53c` に本書のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。**
- 最後の root gate は WP-D の統合後の木で `3688 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。以後 main に入ったのは文書だけ。`tools/tests` は `492 passed`。
- 進行中のサブエージェントは無い。未コミットの作業は無い (worktree `r45-wpd` の古い日本語の起草は不要になった。§5)。

## 2. 本チャットで閉じたもの

| 項目 | main | 要点 |
|---|---|---|
| R-45 WP-F (migration 0013 と (6) の値の検査) | `1620563` (作業 `467b932`)、記録 `607f3b9` | 値は `5000ms`。0013 は 1 トランザクションで、ADMIN OPTION が無ければ失敗して何も残さない。(6) の証拠のテスト名は SI-09 に置いた (SI-08 の MitateDB ブロックは 15,194 / 15,200)。記録は作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` §6B.11、設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12.5。R-48 は解消 |
| R-45 WP-D (runbook §10、英語) | `b484bd4` (作業 `40cdbd0`)、記録 `2cc260f` | Gate-0 は 2 段で読む (依頼者裁定、案 A。設計メモ §1.2 に訂正)。互換性の表・ロックの表は版 2、手順は版 5、独立の設計レビュー (3 起動・6 回) で受理し、runbook §10.8 に記入。`security/CONTROL_MAPPING.md` 2.6。記録は作業指示書 §6.2、設計メモ §12.6 |
| 依頼者裁定 2 件 | 同上 | (1) 0013 の前提を満たさない環境の直し方は `GRANT … WITH ADMIN TRUE, INHERIT FALSE, SET FALSE` の 1 つだけを runbook に書く (作業指示書 §6.1 の WPD-5。使い捨てクラスタで実測済み)。(2) Gate-0 の入口は案 A (作業指示書 §6.2 の (b)) |
| R-45 の受け入れ監査と受け入れ | `84ef53c` | `evidence-auditor` 1 回。未充足 0、証拠不足 6 件は監督裁定 A-1〜A-6 (作業指示書 §6.3。A-4 = WP-B の対応表の欠落は記録の欠落として残した)。**R-45 の WP-A〜WP-F を受け入れた** |
| 起票 | 同上 | roadmap `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.61 の R-50 (SI-08 の MitateDB ブロックが上限に張り付き)、R-51 (`audit_query` が `QueryCanceled` を汎用の 500 にする)、R-52 (下の §4)、R-53 (`ops.py` の help 文 3 点)、R-54 (runbook §9 の `GRANT pg_signal_backend`)。いずれも起票のみ |
| Mitate への報告 | — | セッション「Mitate 監督引き継ぎ」へ送信済み (R-45 の完了、Gate-0 は本番を読む経路の受け入れまで取得しない、R-52 の見込み) |

## 3. 次の一手

1. **依頼者の指示を待つもの**: R-52 の着手 (§4)、R-49 の着手 (前書のとおり)、本番を読む経路の受け入れ。受け入れ後に `inventory` で本番を読み、(3) が blocked なら R-47 を 1 本の WP として開く (依頼者の回答 2。作業指示書 §6A.12)。
2. 指示が無ければ、台帳の順 (roadmap §8) に従う。R-50〜R-54 はどれも小さい。R-53 は Class B で、`ops.py` の help 文を定数から導く形に直すのが筋。
3. push の再開は依頼者の指示による。再開したら main の先頭で CI の run を 1 回取る (`OPERATING_CONDITIONS.md` §2 の 20)。

## 4. 依頼者判断待ち

- **R-52**: MitateDB の role の `CONNECTION LIMIT` (0012 の api 68 / controlplane 20 / application role 36、0005 の auditreader 5) は 1 plane 1 process・concurrency 32 の前提の値で、rollout 中に candidate と traffic を持つ revision が並ぶ (process 数の合計が 2 以上) と `inventory` の (8) の需要が上限を超える。**Control を配備した本番の Gate-0 は (8) が blocked になる見込み。** runbook は状態を変える前の検算で止まる。対処の候補: 新しい platform migration で上限を上げる / 数え方の見直し / 旧 revision を先に止める手順。本番の読み取りより前に着手するかを含めて、依頼者に伺う。

## 5. 並行セッションと worktree

- Mitate の監督セッションの中継は依頼者の回答として扱わず、監督チャットで依頼者本人に確認する (前書 §5)。
- 統合済み・未コミット 0 の worktree: `r45-wpe`・`r45-wpf-manifest`・`handover-0917b`・`r45-wpf`・`r45-wpd2`。`r45-wpd` には古い日本語の起草が未コミットで残るが、WP-D の統合で不要になった。削除は依頼者が行う (区切りで扱いを聞く)。

## 6. 本チャットで足した運用上の教訓

- **実装担当の 2 段 (実測 → 監督の一括裁定 → 実装) と、差し戻しを新しい起動に渡す形は有効だった。** WP-F は第 2 段 1 回 + 差し戻し 1 回で、変異 43 件を回し切った。
- **レビューの続きは同じ起動への `SendMessage` が安い** (文脈を持ったまま差分だけを見る)。起草の狭い直しも同じ。ただし独立性が要る初回のレビューは必ず新しい起動にする。
- **runbook のような手順書は、想定の本番の状態を 10 項目で机上に通すレビューが効く。** 堂々巡り (読めないと直せない / 直さないと読めない) が 3 回見つかった。「状態を変えた後に初めて分かる停止」を探させる。
- **監督が差し戻しに書いた件数を数え間違えた** (38 → 正しくは 39)。件数は表を数え直してから書く。受け入れ監査が記録の 2 箇所の残りを見つけた。
- **`security/CONTROL_MAPPING.md` は 1 行 1,400 字の上限もある。** 起草担当は字数のブロック上限だけを測っていた。発注に `awk 'length($0)>1400'` を入れる。冒頭の Update convention (訂正した旧文は `security/CONTROL_MAPPING_HISTORY.md` へ逐語で移す) は主張の訂正のたびに掛かる。
- **`conformance-tests/test_conditions_register.py` は単独で回すと 3 件赤になる** (suite 全体の収集を前提にしたテスト。main でも同じ)。単独実行の赤を変更のせいと取り違えない。
- **変異定義と対応表は、scratchpad を手放す前に作業指示書の訂正註へ写す** (WP-B は写しておらず、監査で行ごとの照合ができなかった)。
- **libpq の passfile で unix socket の host をどう照合するかは、この作業機では実測できなかった** (テスト基盤は trust 認証)。runbook は host・port を wildcard にし、isolated の組での確認を手順に入れた。
