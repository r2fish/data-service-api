# 引き継ぎ — 2026-08-29 (第5次。CCR-14 実装 WP-1〜WP-5 完了時点)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagents、レビュー: Opus subagents (全 WP で独立レビュー + 変異注入を実施)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: 前書 `HANDOVER_20260829_FABLE2.md`、および `HANDOVER_20260829_FABLE.md` §3 (判断の軸と約束事)・§4 (再発防止) は**全て継続**。現在地のみ本書が上書きする

## 1. 現在地 (branch `conformance-effectivation-and-r2db-service-layer`。**全コミットは main マージ済み・push 済み**)

**CCR-14 の実装フェーズは WP-5 (申告 flip) まで完了した。** 残るは WP-6 (ドキュメント) のみ。

| コミット | 内容 |
|---|---|
| `79161fb` (merge) | 初回 main マージ = **契約 1.1.0 の公開**。以後の契約変更は版数を上げる (additive なら 1.2.0) |
| `782e3ee` | WP-1: conformance port v1.5 (14 op + `ControlCredentialHandle` + `exempt_parameters`)、C-14/C-15 executable 化 (3 adapter surface-absent) |
| `f36c551` | WP-2: 0006 migration (二状態 registry — **列確定は finish 側** (設計訂正)、control_credentials/control_audit/r2dbsvc_controlplane)、work 必須 unit-of-work、ControlCredentialStore ペア、儀式 CLI |
| `8408813` | WP-3: `ControlPlaneService` + backend ペア。AUTH_REQUIRED 監査対象化、抑止宣言2分割 (記録/帰属)、同一トランザクション監査 + 拒否耐久記録 |
| `09511ca` | WP-4: `control_http.py` (11 endpoint) + `control_main.py` (factory) + topology 拡張。rate 前課金 (`check_rate`+`rate_precharged`)、control_plane_http→audit 辺の訂正 |
| `1758213`/`1fc7050`/`faf357f` | **並行セッション**: Q-1 裁定記録 (declare-and-echo、`spec/CCR_DISPOSITION.md` 従属判断6)、抑止宣言パターン文書化、非 OpenAPI 宣言 |
| `5a83e89` | WP-5: **申告 flip 単一コミット** — 両 r2db adapter provided 化、C-14/C-15 provided 分岐初実行 green、C-08 格上げ、儀式コア製品コード化、C-13 ベクタ5本追加、逆向き両方向の変異赤 |
| `43c00e3` | 台帳 L2: conformance sweeper の並行性バグ修正 (per-prefix advisory lock — レビュアが `--collect-only` による実行中 run 破壊を決定的に再現した実在バグ) |

- テスト実測: root suite **709 passed** (~190-210s、C-14 ベクタ5 の rate 回復 sleep ≤61s×2 を含む) / `conformance-tests/` 単独 **202 passed** (~153s) / `r2db-api/tests/test_postgres.py` 単独 **180 passed**。root の 709 は conformance と test_postgres を**包含する** (testpaths 確認済み)
- **全記録は設計文書 `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` v1.8 の §10〜§14** (WP ごとのレビュー結果・監督決定・変異注入・台帳)。port 側は `docs/design/CONFORMANCE_ADAPTER_V1.md` v1.5 §15

## 2. 次の一手: WP-6 (ドキュメント。設計 §5 の最終 WP)

内容 (設計 §5 WP-6 行 + 各 WP 記録の申し送りを拾うこと):
1. CONTROL_MAPPING: SI-00/02/06/08/13/14 行 + C-14 行の SI-08。**SI-14 行には rate limit 拒否と AUTH_STATE_UNAVAILABLE の監査対象外の線引きを並べて明記** (WP-3 の条件付き承認事項)
2. DEPLOYMENT_RUNBOOK / POSTGRES_PROVISIONING_RUNBOOK: 0006・儀式手順・ロックアウト復旧 (R-5 m-2)・`R2DB_CONTROL_PLANE_STATUS` 運用・begin が残す role 残骸 (クラッシュ時) の手動回収
3. R-11 成果物: 侵害/誤操作 playbook・sandbox 規則・`ops.py audit-report --since`
4. README・`ops.py` 再定義文言 (「儀式 + break-glass」へ。--help の "CCR-14" アサートに注意)・`WWW-Authenticate` の両面判断
5. 設計文書 §14.4 の L2 記載を「修正済み (`43c00e3`)」へ更新。台帳整理 (L1 fx deprovision フック=予定化 / L3 特権 stack 分離 / L4 request_bytes 宣言 / target_id 監査語彙 (契約 additive 候補) / audit role 読み取り / 発行凍結 / CredentialsResult.must_rotate)

## 3. WP-6 の後の残作業 (順序)

1. **Q-1 実施** (裁定済み、独立作業単位): 契約 1.2.0 (公開後初の additive) → C-06 共通 suite → CCR-14 休止条項 (revoke 確認) の実効化 → MitateDB 確認検証修正
2. フェーズ3: MitateDB の HTTP 層と永続化 (C-14/C-15 の provided 化を含む)
3. フェーズ4: application-plane の耐久 audit sink (control_audit の形状を再利用可)
4. 配備実機適用 (運用者作業)

## 4. 本セッションの追加ルール・教訓 (§3/§4 継承に追加)

- **コミット・プッシュ・main マージは1セット** (依頼者指示、2026-08-29。マージは --no-ff)。識別確認 (r2fish noreply) は merge commit にも掛ける
- **provided 分岐のような「書くが実行されない」コードは、初実行の WP で必ずバグが出る前提で工程を組む** (WP-5 で実証: テストバグ2 + build 現実2。発見一覧自体を成果物にさせると検証が働く)
- **発注側のスコープ制約が実装の設計逸脱を誘発することがある** (WP-2 の work 省略可化)。逸脱報告を見たらまず自分の指示を疑う
- **「一過性」と報告された事象は再現を試みる** (WP-5: 実装者の残留状態診断をレビュアが覆し実在の並行性バグを確定)
- レビュア誤りも記録する慣例は継続 (WP-2: `details.resource` が契約に既在という誤指摘を一次ソースで却下)
- サブエージェントがホストのスリープで中断したら同一 agent の再開で損失なく続行できる。サブエージェントに長時間検証をさせるときは同期実行を指示する (バックグラウンド監視で turn が止まる)
