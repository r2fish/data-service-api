# 引き継ぎ — 2026-09-21 その 3 (R-71 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260921_FABLE2.md` で、**同書の §4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。本書は前書と同じチャットで書いた。

## 1. 現在地

- ローカルの main は `96c8043` に本書のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-71 の最終の木で `3822 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` は `568 passed` (R-68 の統合時。以後 `tools/` は触っていない)。
- 進行中のサブエージェントは無い。未コミットの作業は無い。`security/CONTROL_MAPPING.md` は版 **2.19**、台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.84。前書の後に別のチャットが R-75〜R-86 を起票している (main `1493e8d`・`1f82348`)。

## 2. 本チャットで閉じたもの (前書の後)

| 項目 | main | 要点 |
|---|---|---|
| R-71 (MitateDB-api の catalog 読みの打ち切りが `VALIDATION_FAILED` に写る) | `96c8043` | 欠陥は台帳の 2 本ではなく developer 接続の catalog 読み **8 本**に在り、全部に既存の 12 箇所と逐語同形の枝を足した (`LIMIT_EXCEEDED`、`limit_class=execution_ms`)。この peer は `LIMIT_EXCEEDED` を durable audit に残さない (変えていない)。版 2.19 が SI-08 / MitateDB-api で開示する。テスト 17 件、変異 14 件が赤。作業指示書 `docs/work-orders/WORK_ORDER_R71_MITATEDB_CATALOG_READ_CANCEL_MAPPING_V1.md` |

- **起票**: R-87 (この 8 本の上限は role 水準の 5000ms で、宣言した `execution_ms` に追随しない)、R-88 (`security/CONTROL_MAPPING.md` の `file:line` の位置参照を解決する検査が無い。陳腐化した実例 2 件)、R-89 (`tools/check_comment_provenance.py` の §4.1 (2) が、塊の直後の文が変わっただけで赤になる)。

## 3. 次の一手

1. **R-66**、**R-67**、**R-69**。順序は監督が着手時に決める。その後 R-72〜R-74、R-87〜R-89、別チャットの起票 R-75〜R-86 (順序と保留は台帳の各行)。
2. 依頼者の指示を待つものは前書と同じ。push の再開は依頼者の指示による。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(k) R-71 の決定の事後報告と確認。** Class D で、決定 (作業指示書 §1 の D-1〜D-6、§4.1 の裁定、`security/CONTROL_MAPPING.md` 2.19 の確定文) は依頼者指示 2026-09-19 の委任の下で監督が下した。
- **(l) client に見える挙動が 1 点変わった。** MitateDB-api で catalog 系の読みが打ち切られたとき、400 `VALIDATION_FAILED` だったものが `LIMIT_EXCEEDED` になる (契約の error 語彙の内。r2db-api の前書々 (h) と同じ向き)。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

- **台帳が名指す箇所の数を信じず、同じ形を grep で数え直す。** R-71 の台帳は 2 本、現物は 8 本だった。
- **peer の対称を前提に完了条件を書かない。** r2db-api は `LIMIT_EXCEEDED` の denial を監査に残すが、MitateDB-api は残さない。起草時の完了条件は r2db-api の結果を持ち込んでおり、設計レビューが止めた。
- **実装担当の「道具は緑」は、監督が worktree を cwd にして再実行して確かめる。** R-71 では comment provenance の `OK` の報告が 2 回とも実測と違った (1 回目は main checkout を測っていた)。`cmd | tail; echo $?` は pipe の終了コードを見せるので、終了コードは pipe の外で取る。
- **`src/` を変える WP で `check_comment_provenance.py --base` の §4.1 (1) は必ず赤になる。** 完了条件は「`--register` が緑、`--base` は (1) のほかに正当な赤が無い」と書く。既存の docstring の直後の文を変えると (2) も赤になる (R-89)。
