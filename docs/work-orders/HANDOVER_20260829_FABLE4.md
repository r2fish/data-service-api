# 引き継ぎ — 2026-08-29 (第6次。CCR-14 実装フェーズ完了時点)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent (1体、レビュー往復含め継続)、レビュー: Opus subagent (独立レビュー + 敵対的変異5本)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: `HANDOVER_20260829_FABLE.md` §3 (判断の軸と約束事)・§4 (再発防止)、`HANDOVER_20260829_FABLE3.md` §4 (追加ルール) は**全て継続**。現在地のみ本書が上書きする

## 1. 現在地 (branch `conformance-effectivation-and-r2db-service-layer`。**全コミットは main マージ済み・push 済み**)

**CCR-14 は WP-6 まで全 WP 完了。実装フェーズは閉じた。** 本セッションのコミット:

| コミット | 内容 |
|---|---|
| `b83fe9a` | 既存欠陥の先行修正: 並行セッション `3e0e678` が spec の非 OpenAPI 宣言を packaged copy (`r2db_api.contract`) へ同期し忘れ、main の byte-identity テストが赤だった。spec 原本を逐語コピーで同期 |
| `b3a817a` | **WP-6 本体**: CONTROL_MAPPING (SI-00/02/03/06/08/13/14 + C-14/C-15、SI-14 行に監査対象外2系統の並記 = WP-3 条件付き承認の履行)、runbook 2冊 (0006・儀式・ロックアウト3経路と軽量復旧・`R2DB_CONTROL_PLANE_STATUS`・begin 残骸2分岐回収)、新規 `r2db-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` (R-11)、`ops.py audit-report --since/--until` (テスト10本・変異6本赤 + 受理境界1)、README、設計文書 v1.9 (§15 実装・レビュー記録、台帳整理) |

- テスト実測: root suite **719 passed** (~186s。監督・レビュア・実装者の3者がそれぞれ独立に全数実行) / `r2db-api/tests/test_postgres.py` 単独 **180 passed**
- 全記録は設計文書 `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` v1.9 の **§15** (WP-6 実装記録・レビュー往復 §15.7・変異表・監督決定)

## 2. 本セッションの監督決定 (依頼者が覆せる。設計 §6/§15 に記録済み)

1. **D-1: `WWW-Authenticate` は data 面・control 面とも不採用を恒久判断として確定** (WP-4 からの申し送り「両面判断」の解)。根拠: 契約は要求せず、利用者 AI エージェントは problem+json 宣言を読む。将来採用は契約 additive 候補
2. **D-2: L4 (`request_bytes` の control discovery 宣言) は次のコード WP へ繰延**。宣言面の変更は conformance 証拠を伴うコード WP に載せる規律を優先
3. **D-5: R-11「可逆性の全数」言明の精密化** (レビュー MA-4)。盗まれた control credential は application credential を**不可逆に revoke できる**(可用性実害: 再発行 + 全 consumer への秘密再配布)。残実害は「窓中に issued **or rotated** の credential 経由のデータ面到達 + 可用性実害 + 一時的運用停止」。設計 R-11 本文は削除禁止のため書き換えず、導出文書 (playbook/CONTROL_MAPPING) 側を精密化し §15.7 に訂正記録
- ほか: playbook・sandbox 規則は実装ローカル `r2db-api/docs/` 配置 (reset 等 r2db 固有操作を含むため)。`audit-report` は帯域外 CLI なので docs WP 同乗可と判断

## 3. 次の一手: Q-1 実施 (裁定済み、独立作業単位。FABLE3 §3 の順序どおり)

1. **Q-1**: 契約 1.2.0 (**公開後初の additive** — 版数を上げる) = declare-and-echo (裁定は `spec/CCR_DISPOSITION.md` 従属判断6) → C-06 共通 suite → CCR-14 休止条項 (revoke 確認) の実効化 → MitateDB 確認検証修正。**このとき同時に検討する台帳の束** (設計 §14.4 に集約済み): target_id 監査語彙 / audit role 読み取り / per-app 発行凍結 / `CredentialsResult.must_rotate` 露出 / L4 `request_bytes` 宣言 (D-2 繰延分。契約変更不要、宣言 flip のみ)
2. フェーズ3: MitateDB の HTTP 層と永続化 (C-14/C-15 の provided 化を含む)
3. フェーズ4: application-plane の耐久 audit sink (control_audit の形状を再利用可)
4. 配備実機適用 (運用者作業。runbook は WP-6 で現行化済み)

## 4. 本セッションの教訓 (§3/§4 継承に追加)

- **契約ファイルを触るコミットは root suite 完走を完了条件にする**: 並行セッションの spec 1行変更が packaged copy との byte-identity テストを赤にしたまま main に乗っていた (`b83fe9a` で修正)。「文書だけの変更」にもテストの網が掛かっている前提で動く
- **ドキュメント WP のレビューも実測型が機能する**: レビュアは runbook/playbook の手順を**字義通り実行**して3件の実行不能・誤案内を再現した (無資格 capabilities は 401 + 監査行 / playbook revoke は app 面 pepper 不足で rc=2 / begin 残骸回収は DB 作成後クラッシュで DROP ROLE 失敗)。文書の宣言はコマンド実行と SQL 実観察で検証させること
- **設計本文が後続決定で古くなる**: R-5 m-2「復旧は reset 唯一」は R-10 の break-glass 追加で古くなっていた。実装者が逸脱として報告 → レビュアが3経路とも実測で機能確認 → 設計に補記、の流れが機能した。設計の規範文に矛盾する記述を見たら、新しい方が正しい可能性をまず実測で確かめる
- **CLI 出力の性質 (順序タイブレーカー・TZ 規約・read-only) は明示テストで固定する**: 実装者の変異3本が赤でも、レビュアの別角度の変異3本 (event_id タイブレーカー除去・naive→UTC 除去・読取後の書込み追加) は全部生き残った。宣言した性質1つにつきテスト1本
- 実装者は報告外の軽微変更を落とすことがある (`R2DB_SERVICE_LAYER_ARCHITECTURE.md` への旧 D-3 節の改訂済み注記 +2 行 — 内容は正確だった)。コミット前の `git status`/diff stat 突合は監督の仕事
