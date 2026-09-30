# 引き継ぎ — 2026-09-30 (R-97 + R-99 閉止、R-108 参照クライアントの設計 v0.6 確定、R-118 起票)

本書は前書の全項を写さない。前書は `docs/work-orders/HANDOVER_20260930_R116_FABLE.md`。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`CM` = `security/CONTROL_MAPPING.md`、設計 = `docs/design/REFERENCE_CLIENT_V0_1.md`。

## 1. 現在地

- local main `7057e66`。契約 1.12.0 不変。台帳 v1.140、`CM` 3.11、`conformance-tests/COLLECTION_FLOOR` 4697。push は停止中 (`OC` §2 の 20)。
- 本チャットは、台帳 R-115 の別チャット (別アカウント) が利用枠で止まっている間に、重ならない項目を進めた。R-115 は未 merge で、WP-1・WP-2 が branch に commit 済み、WP-3 が未 commit のまま止まっている (本チャットは R-115 の worktree に触れていない)。
- 依頼者の指示と裁定 (逐語):
  - 2026-09-30「R-97 -> R-99 -> R-108 の設計起草と進めてください」
  - 2026-09-30「Q-1〜Q-4 はすべて監督の推奨どおりで進めてください」(設計 §9 の Q-1 = (A1)、Q-2 = (A)、Q-3 = (A)、Q-4 = (A))
  - 2026-09-30「その案で良いです」(alias `endpoints.audit_query` の扱い。監督の案は設計 §9 の Q-1 に逐語)
- worktree は branch `r97-r99` と `r108-design` のもの。どちらも merge 済みで、未 fold (作成直後のため `tools/dev/fold.py` が対象外にする)。

## 2. 本チャットで閉じたもの

- R-97 + R-99 (規模 S ×2 を 1 変更セット、Class D)。main `f6fd43f`。
  - 両 peer の `ops.py` に `_resolve_contained_migration_path` を足し、`deprovision` の `0004`、`upgrade-applications` の各 script、既存の `_resolve_platform_migration_file` から使う。helper は `_ISOMORPHIC_TARGETS` に登録 (198 → 199 行。pin 名は `…_199_rows`、`r2db-api/tests/test_r78_pool_wait_stats.py` の pin も 199)。
  - 両 peer の `tests/test_ops_script_path_containment.py` (新規)。`MitateDB-api/tests/test_ops_apply_platform_migration.py` の tempdir を `tmp_path` に移し AST の pin 2 本。
  - `CM` 3.11 は両 peer の `ops.py` への行番号参照の追随 (helper の後ろが +11)。claim の文言は変えていない。
  - 完了ゲート (最終形): `gate: 4697 passed, 2 subtests passed in 466.04s (0:07:46)`、`judge=PASS`、pg diff 0 (label r97-r99-final)。変異は 8 + 10 + 5 件、すべて期待どおり。`tools/tests` は `748 passed`。
  - 完了条件と変異の対応は記録ファイル `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の R-97・R-99 の節。
- R-108 の設計 v0.6 (Class A の変更セット 2 回。main `168f25f`、`7057e66`)。設計レビュー 1 (観点 A / B の並列) + 再確認、依頼者裁定、設計レビュー 2 (同) + 再確認を反映。契約に足す・直す文 12 件 (設計 §9.1) は全件 1 つの minor 版に収まる判定 (設計 §9.2)。
- R-118 起票 (alias の保持期限の文言が現物と食い違う。規模 S、依頼者裁定待ち)。

## 3. 次の一手

1. R-115 のチャットが再開したら、WP-6 の前に main を取り込ませる。ぶつかる箇所: 両 peer の `ops.py` (helper の後ろが +11 行)、`CM` の版 (3.11 使用済み) と行番号参照、同型性の件数 pin (R-115 も 198 から改名している。基点は 199)、`COLLECTION_FLOOR` (4697)、台帳の版の行 (v1.140 まで使用済み)。R-115 の作業指示書 :119 は旧名 `_198_rows` を引いたままである。
2. R-108 の作業指示書 (Change Set Manifest) を起草する。R-115 の merge 後が手戻りが少ない (契約版・条件番号・port 版・launcher が重なる。番号は merge 直前に main を読んで振る)。実測事項は設計 §10 の一覧。
3. R-108 の実装 (契約 WP → port → クライアント → 条件)。規模 L、Class D。

## 4. 依頼者判断待ち・未決

- R-118: `endpoints.audit_query.deprecation_note` の文を直す (minor) か alias を撤去する (major) か。
- 前書までの未決 (R-52 の本番の読み取り、R-101 の着手判断ほか) は変わらない。

## 5. 本チャットで足した運用上の教訓

- peer の `ops.py` に行を足すと `CM` の行番号参照がずれ、変更は Class D になる。着手前に `grep -c 'ops.py:' security/CONTROL_MAPPING.md` を見る。追随は完全形 (`path:N`) だけでなく同じ行の短縮形 (`` `:N` ``) にも要る。各参照の指す行の内容が基点と同じことを機械的に assert してから書き換える。
- `CM` の Version の行に裸の `ops.py` を書くと、登録簿の検査が曖昧な参照として赤にする。
- 登録済みの同型 helper の本体を別の helper に抜き出したら、新しい helper も表に登録する (本体のずれが検出されなくなる)。
- 完了ゲートの後に直したら、最終形でゲートを取り直す (本チャットは 2 回実行した)。
- レビュー担当に「pytest と変異を実行しない」と指示すれば、完了ゲートと並行で走らせられる。
- 依頼者が承認した文案でも、レビューで誤りが出たら文を直し、直した点を依頼者に報告して設計に「報告済み」と記す。承認の逐語は確定文のファイルから複製し、承認していないものを承認と書かない。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| R-97/R-99 レビュー 1: `CM` の短縮形の行番号参照 2 件が未追随 | 直した | `CM` 3.11 |
| R-97/R-99 レビュー 2: 新 helper が `_ISOMORPHIC_TARGETS` に未登録 | 直した | 両 peer で登録、pin 199 |
| R-97/R-99 レビュー 3: `-f` の起動が helper を通ることの構造 pin が無い | 直した | 両 peer に AST テスト |
| R-97/R-99 レビュー 4: R-99 の AST pin の取りこぼし | 直した | pin 2 本に置換 |
| R-97/R-99 レビュー 5: TOCTOU とハードリンクは守られない | 観察 | migrations dir は運用者の信頼境界で、本変更は守ると言っていない。DB の利用者は気づかない |
| R-97/R-99 レビュー 4 の範囲外の観察: 同じ tempdir の残骸が `MitateDB-api/tests/test_ops_inventory.py`・`test_ops_verify_declarations.py` にある | 観察 | R-99 の範囲外。テストの衛生で、利用者は気づかない |
| R-97/R-99 レビュー 6: `CM` の r2db の昇順検査の参照が以前からずれていた | 直した | `:1927` |
| R-97/R-99 再確認 1: `-f` の構造 pin の抜け道 3 つ | 直した | `--file`・タプル・`subprocess` の全呼び出し・import 形の pin。変異 5 件 |
| R-97/R-99 再確認 2: `CM` の Version 3.11 の文が事実と違う | 直した | 文を訂正 |
| R-97/R-99 再確認 3: R-115 の作業指示書が旧 pin 名を引く | 観察 | R-115 側が merge 時に取り直す (§3 の 1) |
| R-108 設計レビュー 1 (観点 A の F-1〜F-10、観点 B の 1〜13) | 直した | 全件採用。1 件ごとの反映先は設計 §12 |
| R-108 再確認 (レビュー 1 の後) 1〜8 | 直した | 全件採用。設計 §13 |
| R-108 設計レビュー 2 (観点 A の A-1〜A-8、観点 B の B-1〜B-12) | 直した | 全件採用。設計 §14 |
| R-108 再確認 (レビュー 2 の後) 1〜10 | 直した | 全件採用。設計 §15 |
| R-108 起草時の指摘: alias の保持期限の文言が現物と食い違う | 起票 R-118 | 契約だけを読む client が文から気づく食い違い |
| R-108 起草時の指摘: control / audit の credential だけを持つ client の最初の要求 | 直した | 設計 §9.1 の #1 (credential の面の base URL) |
