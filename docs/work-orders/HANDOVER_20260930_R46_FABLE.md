# 引き継ぎ書 — 2026-09-30 R-46 (公開値スキャナの入れ子 URL) の閉止

本書は R-46 のチャットの区切りの記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`。前のチャット (別アカウント) が修正とテスト 24 本まで終えて未 commit で止まり、本チャットが引き取った。

## 1. 現在地

- R-46 を閉止した (規模 S、Class D)。`RM` v1.142、契約 1.12.0・`security/CONTROL_MAPPING.md`・`conformance-tests/COLLECTION_FLOOR` は不変。push は停止中 (`OC` §2 の 20)。
- 依頼者の指示と裁定 (逐語):
  - 2026-09-30「1と2を別セッションで、R-46はDで進めてください」(監督の提案「1 = R-46、2 = R-102 の設計」と問い「R-46 は Class D の確認」に対して)
  - 2026-09-30「裁定は推奨で進めてください、最後に確認。」(レビューの指摘の扱い)
- worktree は branch `r46` のもの (merge 済み、未 fold)。前のチャットの worktree (branch `claude/sweet-jackson-2bb7af`) には同じ変更の古い版が未 commit で残る。中身は本変更セットに含まれるので、捨ててよい。

## 2. 本チャットで閉じたもの

- R-46。`tools/public_value_scan.py` の R2_url が、1 つの http(s) URL match が運ぶ全ホストを判定する (入れ子の URL、percent-encoding の各段、authority を `@` と `:` で分けた全 piece、placeholder の除外はホスト自身の範囲)。テスト `tools/tests/test_public_value_scan.py` 33 本、変異 20 件すべて赤。
- 完了条件・変異・集計行・直した範囲・再走査の結果は記録ファイル `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の R-46 の節。
- 直さなかった形はスキャナの docstring の Known gaps 項目 1・6 (`tools/dev/README.md` の一覧は 6 件)。

## 3. 次の一手

1. 台帳の残りは `tools/dev/ledger.py --open` で読む。R-115・R-108・R-102 は別チャットで進行中。
2. 公開化の前の履歴走査で、履歴の検出 11 件 (R3_project_id 6、R6_home_path 5。本変更の前後で同じ) を扱う (`docs/security/public-repository-policy.md`)。

## 4. 依頼者判断待ち・未決

- 本書の「裁定」節の確認 (依頼者の指示「最後に確認」)。
- 前書までの未決は変わらない。

## 5. 運用上の教訓

- 完了ゲートは開発機の負荷を見てから回す。load average が 60 を超える間の実行は 37 分かかり、無関係なテスト 1 本が PostgreSQL の接続断で赤になった。取り直しで緑。
- percent-decoding を足すときは、復号後の文字を元の位置へ対応づける。復号後の形に match 全体の範囲を使うと、placeholder の除外が行全体の読みに戻る。
- deny suffix のホストで書いたテストは、deny のトークン走査が常に拾うので、authority の切り方を固定しない。切り方のテストは未許可ホストで書く。
- 前のチャットの変異 spec は scratchpad ごと失われる。spec は 1 テスト 1 entry で作り直し、レビュー担当にパスを渡す。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー 1: 復号後の形で match 内の placeholder が入れ子ホストの `--` 等を免除する | 直した | 復号後のトークンを元の位置へ対応づけた |
| レビュー 2: 復号後の placeholder 判定を固定するテストが無い | 直した | テスト 3 本、変異 3 件 |
| レビュー 3: `?` と `\` で authority を切る性質が固定されていない | 直した | 未許可ホストのテスト 2 本、変異 2 件 |
| レビュー 4: userinfo の位置の未許可ホストが抜ける (修正前は検出) | 直した | authority の全 piece を判定 |
| レビュー 5a: backslash・HTML 実体で書いた入れ子の scheme は未許可ホストを検出しない | 既知の穴 (§1.12 の 71) | `R2_URL_RE` が合致しない形。製品の欠陥がゲートを抜ける経路ではない。Known gaps 項目 1 |
| レビュー 5b: docstring が閉止を先に書いている | 直した | 同じ変更セットで台帳を閉止、日付は docstring から外した |
| レビュー (不確実): `%25` の連鎖で走査が二次の時間になる | 観察 | 止まるだけで通過にならない。利用者は気づかない |
| 再確認 1-1: ASCII の run を文字単位で対応づける性質が固定されていない | 直した | テスト 1 本、変異 1 件 |
| 再確認 1-2: 非 ASCII を含む run の位置が粗い | 直した | 文字単位の対応に変更、テスト 1 本 |
| 再確認 1-3: Known gaps の文が実挙動より広い (password の位置) | 直した | password の位置も判定し、文を合わせた |
| 再確認 1 (c): 点を含む userinfo が新たに赤になる | 既知の穴 (§1.12 の 71) | 過検出で fail-closed。追跡ファイルに該当 0。Known gaps 項目 6 |
| 再確認 2-1: 不正な UTF-8 列が遅れて報告される分岐をテストが通らない | 直した | 標本と値ピン、変異 1 件 |
