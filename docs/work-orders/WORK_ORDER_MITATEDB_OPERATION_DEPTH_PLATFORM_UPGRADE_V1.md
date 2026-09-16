# Work Order: MitateDB operation_depth platform upgrade

- 台帳: `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-45** (v1.50、2026-09-16)。
- 状態: **起票のみ。設計・レビュー前であり、本書の手順はまだ実行してよい手順ではない。**
- 来歴: 2026-09-14 に worktree `.claude/worktrees/mitatedb-operation-depth-platform-plan` で未コミットのまま起票された版を、2026-09-16 に監督が取り込んだ。起票時の台帳番号 R-37 は main の R-37 (モジュール分割のリファクタ) と衝突したので R-45 に当て直した。下の「起票原文」の番号付き手順 1〜4 は語句を変えていない。依頼の経路と制約は引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE2.md` 付録 C。
- Mitate 側の正本 (読み取り専用): `../Mitate/decisions/DM-0052-data-service-platform-upgrade-for-operation-depth.json`、`../Mitate/docs/design/data-service-operation-depth-platform-upgrade.md` v1.2、`../Mitate/docs/work-orders/data-service-operation-depth-platform-upgrade.md` v1.2。

## 起票原文 (2026-09-14)

- 変更クラス: D
- 対象: MitateDB-apiのCloud SQL/Cloud Run Data・Control運用。共通API、Application、validation Job/bridge/credentialは対象外。
- 目的: product reassessment F9の`operation_depth`を安全に公開・強制する。

1. DSN、credential、tokenを出さないread-only経路でdeclarations、migration、per-application upgrade、isolated/prod tuple、rollback、DDL lock/停止条件を確認する。状態不明はblocked。
2. `MitateDB-api/docs/cloud-run-cloud-sql.md`へ、0007、0011、独立した0012、per-application upgrade、declaration、legacy env除去、Data/Control restart、health、traffic、rollbackのreview済み手順を置く。
3. isolatedで同一candidate digestの`operation_depth=13`、13受理、14拒否を証明する。
4. Sol受理後だけproduction Data/Controlを更新し、独立監査後にMitate側F9を再判定する。

## 取り込み時の註 (監督、2026-09-16)

- 手順 4 の「Sol受理」は起票原文の語である。本リポジトリでの受理者 (独立レビュー・依頼者裁定のどちらか、または両方) は設計で確定する。
- 依頼で指定された制約 (いずれも厳守): 本番を変えない (migration・declaration・restart・candidate・traffic・Job・bridge・probe・fixture・promotion をしない、secret の rotate / revoke / delete をしない、Cloud SQL のリソースを消さない)。**credential の値を出力しない経路が設計とレビューで受け入れられるまでは、本番を読むこともしない。** DSN・credential・token・credential を含む URL を出力・ログ・文書・コミットに置かない。共通の Data Service API の spec、Mitate の契約、mitate-application の F9 ゲートを変えない。`MitateDB-api/docs/f9-execution-assets-v1/` は参照用に限り証拠にしない。依頼者が言うまで push しない。
- 順序: 手順 1 の経路の**設計**は文書のみなので先行できる。実装・テスト・runbook の変更は R-37 WP-5 (MitateDB-api の `backend_postgres.py` と `config.py` の import を削る) の統合後に始める。
- Gate-0 の確認項目には、上の 6 状態に加えて**旧式の base URL 設定 (`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`) の有無**を含める。各項目は confirmed / blocked / unknown で報告し、unknown は blocked と同じく先へ進まない。
- 変更クラスの最終判定は `docs/design/ROADMAP_POST_PHASE7_V1.md` §9 の 8 の表で行う。
