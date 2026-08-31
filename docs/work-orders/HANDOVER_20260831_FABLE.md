# 引き継ぎ — 2026-08-31 (第8次。フェーズ3 完了時点)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー: Opus subagent (体制は `HANDOVER_20260830_FABLE.md` 冒頭と同一)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: `HANDOVER_20260829_FABLE.md` §3/§4、`HANDOVER_20260829_FABLE3.md` §4、`HANDOVER_20260829_FABLE4.md` §4、`HANDOVER_20260830_FABLE.md` §4 は**全て継続**。現在地のみ本書が上書きする

## 1. 現在地 (main)

**フェーズ3 (MitateDB-api の HTTP 層と永続化、`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`) は WP-0〜WP-6 まで全 WP 完了し、全て main マージ済み・push 済み。** 契約変更なし (contract 1.2.0 の実装のみ)。

| コミット | WP | 内容 |
|---|---|---|
| (branch 履歴) | WP-0 | 設計 + 独立レビュー二重実施 (本セッション側 + 並行 mitate-30 側、v1.2 確定) |
| — | WP-1 | PostgreSQL 基盤 (pyproject / migrations / backend seam / `add_field` 解禁 P3-D1 / delete 句 fingerprint / database-per-application) |
| — | WP-1.5 | mutate バッチ意味論の収束 (P3-D2: transact の update/delete atomic 拡張) |
| — | WP-2 | credential 永続化 (Postgres store、enabled/revoked 独立2値化、parity、fail-closed) |
| — | WP-2.5 | 共通側変更 (C-17 present-denial 形態、C-11 全 adapter 反復化、繰延べ2件) |
| — | WP-3 | application-plane HTTP + composition root + `MitateDB-api-http` adapter 登録 |
| — | WP-4 | control plane 本体 (未 mount で実装、二重 store parity、同一 tx 監査、topology 実行可能証拠) |
| `8a7d11c` | WP-5 | 宣言 flip (/control/v1 mount、`control_plane: enabled` 両 adapter、C-13 実ベクタ、C-14/C-15 PROVIDED 初実行) |
| `516c955` | WP-6 | 記録整理 (Dockerfile / Cloud Run runbook / compromise playbook / break-glass CLI / CONTROL_MAPPING TBD 解消 / CONDITIONS / README) |
| `89c52ad` | — | WP-6 の main マージ (本セッション)。`CONTROL_MAPPING.md` SI-10 行の競合を解決 |

**SI-10 競合解決の内容 (89c52ad)**: WP-6 分岐は「control-plane HTTP に専用の非漏洩ネガティブテストが無い」を open gap として正直に記録していたが、main 側 `79884d9` が先にそのテスト (`MitateDB-api/tests/test_control_http_unmounted.py::test_control_problem_response_never_leaks_the_underlying_exception_message`、実 mount `/control/v1` 経由・secret-shaped marker の全身不在 assert) を追加してギャップを閉じていた。解決は WP-6 の二面構造 (Application-plane / Control-plane) を採り、open-gap 記述だけを main の閉鎖 evidence へ置換。SI-10 以外の 11 行は base から WP-6 側のみの変更であり WP-6 版をそのまま採用。

マージ後 main での実測 (本セッション、同期実行):

- `MitateDB-api/tests/`: **282 passed**
- `conformance-tests/` (4 adapter: r2db / MitateDB / r2db-http / MitateDB-http、C-14/C-15 PROVIDED 分岐含む): **335 passed** (313s)
- root suite 全体: **1161 passed / 0 failed / 0 skipped (1 warning、373s)。WP-6 記録の分岐時点 1160 + main 側 SI-10 リークテスト 1 件 = 1161 で整合**

## 2. 未解決の依頼者判断 — D-L (フェーズ3.5)

`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` §5 D-L / §7 台帳筆頭。**`cross_entity_mutation` の凍結解除 = フェーズ3.5**。

- クライアント側 (mitate-application、Mitate repo `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` v1.2 §6) から 2026-08-30 に「**採用 — フェーズ3.5 として実装依頼**」の正式回答を受領済み。根拠: 監査保証 (成功した状態変更 = ちょうど1 audit event) は原子性の問題であり、cross_entity_mutation 成立まで Phase B カットオーバーを待つ (保証を毀損する縮退カットオーバーはしない)
- スコープ下限 (クライアント回答): 1 atomic unit = 複数 entity にまたがる insert/update/delete の列 (全成功 or 全無効)、batch 上限 10、upsert / read-your-writes / preconditions / 実行順序観測 / 新エラー語彙は不要
- 採用なら C-16 の executable 化と共通 suite 作業が発生 (クライアント側了解済み)
- **他セッション経由の伝聞を依頼者承認とは扱わない規律により、着手には本 repo の依頼者の直接確認が必要。フェーズ3完了報告 (本書と同時) で提起済み — 回答待ちが次セッションの最初の分岐**

## 3. 次の一手 (優先順)

1. **D-L の依頼者回答の受領** → 採用ならフェーズ3.5 設計 (WP-0 独立レビューから。契約への capability 追加は additive、1.3.0 束との一括判断も選択肢 — `DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(e) 4件と合流させるか依頼者判断)
2. **フェーズ4: application-plane の耐久 audit sink** (control-plane の `control_audit` 形状を再利用してよいが拘束しない。WP-1.5 申し送り N-1 — バッチ監査の遅延発火と同一 tx 規律の整合 — をフェーズ4 設計の入力に含めること)
3. 配備実機適用 (Cloud Run / Cloud SQL。runbook = `MitateDB-api/docs/cloud-run-cloud-sql.md`、`foundation.json` の platform_evidence_required_before_production 3項目は配備時に閉じる)
4. 台帳残置分は `MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` §7 が正本 (rate limit 共有 window、revision_preconditions、SI-08 残クラス、positive-existence check、RLS 併用、IAM DB 認証ほか)

## 4. 教訓の追加 (前書全項継承に追加)

- **並行セッションと main の同時進行では、記録 WP の分岐は「自分が書いた時点の真実」を運ぶ**: WP-6 が open gap と書いた欠落を main 側が先に閉じており、マージ競合の解決は「どちらの文面を採るか」ではなく「どちらの事実が新しいか」の三方比較で決めた (base 比較で片側変更 11 行を機械的に分離し、両側変更は SI-10 の 1 行のみと特定してから統合)。競合解決も実測で裏取りする — 引用テストの実在を grep で確認し、マージ後ツリーで suite を完走させてからコミットした
