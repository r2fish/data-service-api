# 引き継ぎ — 2026-09-01 (第9次。フェーズ3.5 完了時点)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: 過去引き継ぎの約束事 (`HANDOVER_20260829_FABLE.md` §3/§4、FABLE3 §4、FABLE4 §4、`HANDOVER_20260830_FABLE.md` §4、`HANDOVER_20260831_FABLE.md` §4) は**全て継続**。現在地のみ本書が上書きする

## 1. 現在地 (main)

**フェーズ3.5 (cross_entity_mutation + 契約 1.3.0 additive 束、`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` v1.2) は WP-0〜WP-6 まで全 WP 完了し、全て main マージ済み・push 済み。** 依頼者直接承認 (2026-08-31「一括で進めてください」) に基づく。

| コミット (merge) | WP | 内容 |
|---|---|---|
| `a3873ca` | WP-0 | 設計 v1.1 (独立レビュー blocker 4 全数裁定 — audit role in-band 発行撤回、WP 順序反転ほか) |
| `9b0dd87` | WP-1 | **契約 1.3.0 公開** (cross-entity 意味論明確化 + 束4件 + atomic_mutation 明確化 + 従属判断8。以後の契約変更は 1.4.0) |
| `bd13604` | WP-2 | MitateDB cross_entity (二段パス transact / batch_entities=10 / HTTP 実体化 / 宣言 flip status=partial。**B-2: 孤立サロゲートの原子性穴を実測発見・二重閉塞**) |
| `85e60e2` | WP-3 | 共通 suite: port v1.7 + **C-16 executable 化 (4 adapter)** + C-12/C-11 拡張 |
| `064f4dd` | WP-4 | r2db 制御面束 + L4 request_bytes + **contract_version 1.3.0 flip** |
| `04235b7` | WP-5 | MitateDB 制御面束 + **contract_version 1.3.0 flip** (B-1 テスト 13 等値復元) |
| `100fc3f` | WP-6 | 記録整理 (CONTROL_MAPPING 8 行 / 台帳 4 冊 RESOLVED 追記 / 陳腐 prose 全数) |

最終実測 (単独実行、2026-09-01): **root suite 1292 passed / 0 failed / 0 skipped** (フェーズ開始時 1161 から +131)。conformance 364 (4 adapter、C-16 含む)。

各 WP の実装記録・レビュー裁定・変異注入ログ・受理境界は設計文書 §9/§10.1〜10.6 が正本。監督決定 P35-D1〜D14 は §6 (依頼者が覆せる)。将来課題台帳は §7 (idempotency 名前空間 / audit-role 共通ベクタ C-14 v2 / ScopedMutation.entity の C-03 被覆 / applications margin の fixture teardown / PG OverflowError ほか)。

## 2. クライアント連携状態

- mitate-30/mitate-cd へ wire 形状確定 (WP-0 後)・flip 成立 (WP-2 後) を通知済み。**フェーズ3.5 完了の最終一報は本セッションで送信** (クライアント作業指示書の起草は先方で進行)
- クライアント向け確定仕様: `POST /v1/data/mutations` + 契約既存 `ScopedMutationRequest`、応答 `{"committed","affected"}` のみ、batch_entities=10 (distinct entity 数)、upsert/idempotency_key/expected_revision は CAPABILITY_UNSUPPORTED、孤立 UTF-16 サロゲートは VALIDATION_FAILED、batch 内 delete は per-entity declare-and-echo
- Phase B カットオーバー前提 (HTTP 面 + cross_entity_mutation) は**両方成立済み** — カットオーバー実施はクライアント側作業

## 3. 次の一手 (優先順)

1. **フェーズ4: application-plane の耐久 audit sink** (control-plane の 13 フィールド `control_audit` 形状を再利用してよいが拘束しない。入力: フェーズ3 WP-1.5 申し送り N-1 = バッチ監査の遅延発火と同一 tx 規律の整合、`audit_query` の C-11 zero-coverage 解消もこのフェーズ)
2. 配備実機適用 (Cloud Run / Cloud SQL。runbook 現行化済み、`foundation.json` の platform_evidence_required_before_production は配備時)
3. 台帳消化 (設計 §7 + 継承分)。契約 1.4.0 候補が溜まったら一括判断の前例 (従属判断8) を踏襲
4. **運用規律 (本フェーズの新教訓)**: suite 完了ゲートの実測は「他の pytest 実行が走っていないことを確認してから」— PG クラスタ並走衝突で偽陰性 2 回 (§10.6)。また applications margin (115/122) 逼迫時は bump でなく fixture teardown

## 4. 教訓の追加 (前書全項継承に追加)

- **「宣言が偽になっている実装現状」はフェーズ順序を決める一級の事実である**: WP-0 レビュー B-4 (in-process transact が既に cross-collection 実行可能 = unavailable 宣言が偽) の実測発見が、フェーズ3 の suite-first 順序を実装先行へ反転させた (P35-D11)。設計は「契約の現状」だけでなく「実装の現状」を実測してから WP 順序を確定すること
- **能力を宣言する flip コミットは、その能力の安全主張を load-bearing にする**: WP-2 B-2 (サロゲート rollback 不発) は pre-existing だったが、cross_entity_mutation を宣言する瞬間に SI-11 違反になる。flip WP のレビューは「宣言が真になる瞬間に昇格する既存欠陥」を明示的に探すこと
- **対称実装 (peer 2 週目) には前週レビューの教訓を発注書に織り込む**: WP-5 は WP-4 の裁定 (revoke gate 濾過・儀式ロック・構造的列挙・snapshot) を最初から要求し、レビュー結果は 1 major (無関係アサーション削除) まで縮んだ。教訓の伝搬は発注書が担う
- **一括版数戦略 (従属判断8) は機能した**: 4 additive 候補 + 意味論明確化 + 新 capability 実効化を単一 1.3.0 で出荷し、版数分散なし・peer flip は各自の挙動出荷コミットに束縛 (version_binding 規律)。次の候補束too この形を既定とする
