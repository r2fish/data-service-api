# 引き継ぎ — 2026-09-21 (R-62 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260920_FABLE3.md` で、**同書の §4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。本書は前書と同じチャットで書いた。

## 1. 現在地

- ローカルの main は `a1ee7c5` に本書のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-62 の最終の木 (main へ統合済み) で `3796 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` は `568 passed` (R-68 の統合時。以後 `tools/` は触っていない)。
- 進行中のサブエージェントは無い。未コミットの作業は無い。

## 2. 本チャットで閉じたもの (前書の後)

| 項目 | main | 要点 |
|---|---|---|
| R-62 (r2db-api の `PostgresCell.catalog` が取引ごとの timeout を通らない) | 変更 `3a52296`、記録 `a1ee7c5` | `catalog(self, limits=None)` が取引の中で `_set_timeouts` を通す。`limits` が無ければ `ResourceLimits()`、`DataService.catalog` は `self.limits` を渡す。打ち切りと lock timeout は他の 3 操作と同じ `LIMIT_EXCEEDED` に写る。**deadline は渡さない** (C-05 の `hold_in_flight` が cell の `catalog` を差し替えて停止させるので、deadline が停止を跨ぐ)。MitateDB-api はコードを変えず、catalog の経路の developer 接続が role 水準の `statement_timeout` を持つことをテストで固定した。**台帳の「Class B の見込み」は誤りで Class D**: `security/CONTROL_MAPPING.md` の SI-08 / r2db-api の開示文が偽になるので同じコミットで直した (**版 2.15**)。変異 11 件が赤。作業指示書 `docs/work-orders/WORK_ORDER_R62_R2DB_CATALOG_TIMEOUT_V1.md` |

- **起票**: R-71 (MitateDB-api の catalog の打ち切りが VALIDATION_FAILED として返る)。R-65 の行に追記した。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.78。

## 3. 次の一手

1. **R-65 を次に行う** (SI-08 の既定の小ブロックの分割)。R-62 で SI-08 / r2db-api / default block が **14,105 字 (上限 15,200、残り 1,095)** になり文書の最長になった。次に SI-08 へ主張を足す作業は上限に当たる。着手時に preamble `:27`-`:28` の古い実測記録も直す (R-60 の申し送り)。R-70 (同じファイルの別の主張の訂正) と変更セットを分けるかを着手時に決める。
2. その後: **R-64** (着手時に実在しない 6 件も直す)、**R-66**、**R-67**、**R-69**、**R-70**、**R-71**。
3. 依頼者の指示を待つものは前書と同じ。push の再開は依頼者の指示による。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(g) R-62 の決定の事後報告と確認。** Class D で、決定 (作業指示書 §1 の D-1〜D-9、J-1〜J-4、設計レビュー 1 の裁定 — 特に deadline を渡さない裁定、`security/CONTROL_MAPPING.md` 2.15 の確定文) は依頼者指示 2026-09-19 の委任の下で監督が推奨として下した。前書 §4 (a) (委任が Class D に及ぶかの事後確認) に R-62 を足す。
- **(h) client に見える挙動が 1 点変わった。** r2db-api の catalog が打ち切られたとき、以前は一律 503 だったものが `LIMIT_EXCEEDED` の 413 になる (他の 3 操作と同じ。契約の error 語彙の内)。

## 5. 本チャットで足した運用上の教訓 (前書 §6 に足すもの)

- **着手時に `security/CONTROL_MAPPING.md` を対象の語で grep する。** 台帳が B と見込んだ項目でも、開示文が現在形でその穴を述べていれば、直すと偽になるので Class D になる (R-62)。
- **plug が cell の操作を差し替えて停止させる試験 (C-05) が在る操作に、呼び出し側で作った deadline を渡さない。**
- **`security/CONTROL_MAPPING.md` の確定文は、実装の実測 (テスト名・行番号・ブロック長) の後に監督が確定し、実装担当にスクリプトで逐語複製させる。** 1 行を 2 本の主張に分けると分割検査の期待行は `added=2` になる。
- **zsh は `$VAR` を語分割しない。** `tools/change_class.py` へ複数パスを変数で渡すと 1 本の巨大なパスになり `class=A` と誤測定する。stdin で 1 行 1 パスを渡す。
- **既存の関数に docstring を足すと、コメント検査の §4.1 (2) で赤になることがある** (直後の文が基点と整列したままのとき)。signature だけの変更に留めるか、R-63 の規則で通る形かを先に見る。
- **サブエージェントが API の利用上限で落ちたら、worktree の状態 (git status、変異 journal、pytest) を見てから同じ担当を `SendMessage` で再開する** (今回は読解の途中で落ち、worktree は未変更だった)。
