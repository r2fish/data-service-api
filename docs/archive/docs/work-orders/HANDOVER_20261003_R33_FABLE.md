# 引き継ぎ書 — 2026-10-03 台帳 R-33 (cell 経路と HTTP 経路で digest の材料が食い違い得る) 閉止

本書は作業機の監督チャット (Fable) の記録である。cloud session の静的読解報告 (`docs/design/R33_DIGEST_MATERIAL_READING_V0_1.md` v0.1、branch `claude/funny-johnson-sw4fn4`、commit `1b712fc`) を取り込み、見込みを実測し、裁定し、実装して閉止した。規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。

## 1. 現在地

- 変更セット `r33` (worktree `.claude/worktrees/r33`、branch `r33`)。基点はローカル main `c7403a4`、途中で main `1abd5e8` (R-118 / R-30 / R-120 の裁定記録、台帳 v1.154) を merge した。main への merge は本書の commit と同じ変更セット (`tools/dev/finalize.py`)。
- 契約 1.14.0 のまま。`spec/`・`conformance-tests/`・`security/`・r2db-api の差分 0。`security/CONTROL_MAPPING.md` の版は変えない (統制は変わらない)。
- 台帳 v1.155。R-33 を §8.2 の索引と記録ファイル `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` へ移した。起票は無し。
- 完了ゲート (監督単独、最終の木、label r33): `5024 passed, 2 subtests passed in 474.56s (0:07:54)`、`judge=PASS`。`COLLECTION_FLOOR` 5019 → 5024。
- main は未送信 (GitHub への送信は Mitate 側の手順で依頼者の指示により行う)。origin の branch `claude/funny-johnson-sw4fn4` の削除は送信側の作業。
- 記録の置き場: `docs/work-orders/HANDOVER_20261002_R42_FABLE.md` を `docs/archive/docs/work-orders/` へ `git mv` した (`OC` §1.16 の 78。最新 2 通は本書と `HANDOVER_20261002_RULINGS_FABLE.md`)。R-42 のチャットが同書に追記するなら archive 側の path で行う。

## 2. 本チャットで閉じたもの

- **R-33 閉止 (規模 M、Class B)。** 作業指示書 `docs/work-orders/WORK_ORDER_R33_DIGEST_MATERIAL_V1.md` (§2 裁定 D-1〜D-4、§3 の表、§5 実施記録)。
- 手順: 報告書の取り込み (merge `2dc4b88`) → 裁定前の特性化 (実装担当が報告書 §4 の E-1〜E-5 をテスト 5 本で実測、5/5 一致。E-6 / E-7 の変異は赤) → 監督裁定 (a) → WP-1 (実装担当) → コードレビュー 1 回 (`reviewer`) → 差し戻し 1 (docstring のみ) → 監督が最終の木で変異 6/6 赤を再実行 → 完了ゲート → finalize。
- **裁定の中身 (`WORK_ORDER` §2)**: (a) `ApplicationCell.create_collection` の死んだ `destructive` 引数を除く。HTTP が body の `destructive` を digest に入れるのは spec どおりで、in-process の公開入口は `digest_extra` keyword で 5 キーを運ぶので一般則は両入口で成立していた。報告書 §3 行 4 (`transact` の in-process 再構築) は観察。報告書 §6 の 1 (`confirmation` / `revision` / `index` / `unique` を `create_entity` に付けると受理して無視) は観察。
- **報告書の訂正 2 件** (本文は書き換えず台帳の閉止註と作業指示書の訂正註に記録): `:29`・`:31` の「in-process の公開入口にも対応する引数が無い」は誤り (`digest_extra` keyword がある。`cell.py:3814-3816`、既存 pin `test_dry_run_and_plan.py:928`)。§4 E-5 の相違の原因は `values` の有無ではなく top level の `entity` の有無。
- テスト 5 本を `MitateDB-api/tests` に足した: 署名 pin、HTTP の `destructive` が digest に入る / 省略と明示 false は別 token / `create_entity` は `destructive: true` を受理して実行、in-process と HTTP の token が違う (KNOWN GAP の pin。閉じる変更セットは `cell.py::_reconstruct_digest_operation` の docstring と同時に反転する)。

## 3. 次の一手

1. worktree `r33` と branch `r33` を `tools/dev/fold.py` で畳む (dry-run → `--apply`)。
2. 残件は `tools/dev/ledger.py --open` で取る。本件からの起票は無い。
3. cloud session に出せる次の作業: 読解報告の形で成果が閉じるもの (本件の型)。報告書の「事実」が作業機で外れた箇所が今回 1 件あった (§2 の訂正 1) ので、裁定前の特性化 (見込みの実測) は今後も省かない。

## 4. 依頼者判断待ち・未決

- 無し。R-33 の裁定 1 つは台帳どおり監督が下した (`RM` §8 の R-33 行「裁定 1 つ (監督)」)。

## 5. 運用上の教訓

- **読解報告の「事実」も作業機で検証する**: 報告書は `digest_extra` keyword を「HTTP 層が組むもの」としか読まず、`ApplicationDeveloper.create_entity` が同じ keyword を公開していることを見落とした。コードレビュー 1 が既存テストから拾った。裁定の結論は変わらなかったが理由は変わった。
- **「違う」を assert するテストは変異で赤にできないことがある**: E-5 は差の有無だけを見るので 1 行の変異 (M4) では緑のまま。赤にするには「揃える」変異 (R-E5-close、2 箇所) が要った。差を pin するテストには「揃える」変異を対応付ける。
- **実装担当の token の対応が逆だった**: 診断変異 2 本の出力の対応を取り違えた。レビュー担当の sha256 の再計算で訂正。値そのものを記録に残すときは、どの実行の値かをログの `id` で引く。
- **`MitateDB-api/conformance` は pytest の対象ではない**: adapter の置き場で、テストは `conformance-tests/` にある。発注では `conformance-tests -q -k mitatedb` と書く。
- main は本チャットの間に 2 回進んだ (R-42 の裁定記録、R-118 / R-30 / R-120 の裁定記録)。ゲートの前に main を merge し、台帳の版は merge 後に取る。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー 1: E-5 の docstring が開示済みの穴を期待挙動のように読ませる | 直した | docstring に KNOWN GAP の pin であることと反転の手順を書いた |
| レビュー 2: 作業指示書 D-1 の前提 (in-process は 5 キーを表現できない) が誤り | 直した | D-1 を差し替え、訂正註 1。報告書 `:29`・`:31` は台帳の閉止註に記録 |
| レビュー 3: 実装担当の報告の token の対応が逆、§3 行 5 の原因の推定が外れ | 直した | 作業指示書 §5.2 に正しい対応を記録、訂正註 2 で変異を R-E5-close に差し替え |
| レビュー 4: test_http の節コメント・E-4 の docstring・module docstring が裁定後の現状とずれる | 直した | 差し戻し 1 (docstring とコメントのみ) |
| レビュー 5: conformance `-k mitatedb` の前の実行で c27 の 2 件 (http / socket) が `/control/v1/capabilities` の `LIMIT_EXCEEDED` で一過性に赤 (src 無変更時点、後の実行で緑、load 約 3) | 観察 | 検査器の穴ではなく偽赤 (製品の欠陥がゲートを抜ける向きではない)。`spec/` 経路の client は気づかない。再発したら control plane の上限と harness の生存確認の関係を見る |
| 報告書 §6 の 1: `confirmation` / `revision` / `index` / `unique` を `create_entity` に付けると受理して無視し digest にだけ入る | 観察 | `revision` の意味は R-107 の範囲。他 3 キーは shape 上許されて意味を持たない要求で、受理して無視しても client の結果は変わらない |
| 報告書 §3 行 4: `transact` の in-process 再構築で digest が HTTP と一致しない | 観察 | `cell.py:236-243` が開示済み。閉じるには port file を触る別の変更セット (Class C 以上)。`spec/` 経路の client は気づかない。E-5 のテストが pin している |
