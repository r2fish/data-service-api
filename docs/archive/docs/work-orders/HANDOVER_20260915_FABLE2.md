# 引き継ぎ — 2026-09-15 (R-22 変更セット 5・6 と R-37 WP-3d。契約は 1.8.0 のまま)

前書 `docs/work-orders/HANDOVER_20260915_FABLE.md` の全項を継承する。規律は `docs/work-orders/OPERATING_CONDITIONS.md` (§1.5 の 40a〜40c、§1.10 の 64〜67) に従う。

## 1. 現在地 (main)
- main は `5650203`。
- 最後の root gate は main `42842de` の上で `3390 passed`、pg_database / pg_roles の差分 0。tools/tests は `404 passed`。
- push は GitHub の請求上限のため停止中で、ローカルの main だけを進めている。
- 作業ツリー:
  - `ccp-cs0`、`r37-wp0`、`r37-wp3d`: いずれも未コミットの変更は無い。`r37-wp0` と `r37-wp3d` は main より少し古い。着手前に main に揃える。
  - `dev-tools`: 触っていない。
  - `mitatedb-operation-depth-platform-plan`: 別のエージェントのもの。ロードマップに未コミットの編集があり、R-37 の ID が main と衝突する。触らない。

## 2. 到達した状態
- **R-22**。設計は `docs/design/CODE_COMMENT_PROVENANCE_V1.md` v0.16。
  - 変更セット 0h: `2d47e52`
  - 変更セット 5: `708ee4c` (merge `db82663`)。レビュー 4 回、修正 3 回。
  - 変更セット 6: `1f9342f` (merge `42842de`)。R6-1 で日付だけの除去に縮小した。
  - 登録済みの CH-ID は 427。
  - 記録は設計 §10.4 と §10.5、作業指示書 §13 と §14。
- **R-37**。設計は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` v1.13。
  - WP-3a〜3c の記録: §10.9
  - WP-3d (ST10 → `storage_outcomes.py`): merge `ead4893`、root gate 3390、記録は §10.10
  - WP-3d〜3i の manifest と裁定 W3-6〜W3-14: 作業指示書 `WORK_ORDER_R37_WP0_INVENTORY_V1.md` v1.11 の §5.32〜§5.39
- **R-39**: (3a) を閉じた (`d85bd42`、`service.py` と `service_results.py` の docstring)。§10.9 の穴 24・25 と §5.39 の既知の穴は未着手。

## 3. クライアント連携状態
前書から変更なし。

## 4. 次の一手 (優先順)
1. **事故の後始末 (最初に行う)**: 変更セット 6 で、赤い gate (`judge=FAIL`) を pipe の終了コードで見落として統合した (設計 §10.5)。main の再 gate は緑。
   - 疑いのあるテスト: MitateDB `tests/test_threadpool_offload.py::test_pass1_and_pass2_serialize_through_cell_lock_no_developer_connection_race@registry-guards`。全 suite の負荷の下で 413 になり、単独では 3/3 緑だった。
   - 負荷で揺れるのか、実際の競合なのかを調べる。原因を特定するまで「flaky」と断定しない。
2. **R-37 WP-3e (CE5)**: 作業指示書 §5.34。`r37-wp3d` か新しい worktree を main に揃え、行番号を測り直してから着手する。以後 3f → 3g → 3h → 3i を直列に進める。裁定は §5.39 (W3-6〜W3-14) を読む。
3. **R-22 の次**: 設計 §10.5 の次の候補を行う。
   - 0i: チェッカーで F-ID、peer 相対パス、入れ子の括弧の中の条項 ID を保護する
   - 0e・0f の手元のコピーを検査するテストの置き換え
   - R6-4 で残した日付の除去
   - 変更セット 7 の選定
4. **R-39 への追記**: 作業指示書 §5.39 に列挙した移動前からの古い位置参照を、ロードマップの R-39 行に足す。

## 4-5. 依頼者判断待ち
前書 §4-4 から変更なし (R-40、R-38 / R-39 / R-41 はフェーズ11)。

## 4-6. GitHub 復旧後にすること
前書 §4-5 を継承する。

## 4-7. 運用規律 (本チャットで足したもの)
- **gate と finalize**: 1 本の pipe でつながない。出力はファイルに書き、gate の終了コードと `judge=` の行を読んでから finalize する。
- **待ち方の指示**: subagent には foreground 実行を明記する。背景の pytest や監視を待たせると、その agent は起きない。止まったら SendMessage で foreground での再実行を指示する。
- **他 worktree への書き込み**: subagent の Edit / Write は、このチャットの割り当て worktree の外を拒否される。Bash の python heredoc で書かせ、許可するファイルを列挙する。
- **コメント整理の文面の判断**:
  - Opus に任せる。
  - スクリプトで塊ごと折り返し直さない。
  - 除去の可否は、除去した後の文で判定する。
  - F-ID、peer 相対パス、条項 ID、WP の位置指定を保護する。
  - 除去の残らない塊は基準のバイト列に戻し、欠番にする。
- **git 操作の逸脱**: 変更セット 6 の実装担当が、禁止されていた `git checkout -- <file>` を 2 回使った。コミット前の作業ツリーだけで、実害は無い。発注時に明示して禁じる。

## 5. 教訓の追加
- チェッカーが許す除去は、文が読めることを保証しない。変更セット 5・6 の差し戻しの大半は、機械的な除去から出た。
- 範囲を「日付だけ」のように単純な規則に絞ると、レビューの往復が止まった (R6-1)。
