# 引き継ぎ — 2026-08-28 (第2次。Fable 監督期の第1セッション終了時)

- 引き継ぎ元: Fable (監督・設計)。実装: Sonnet subagents、レビュー: Opus subagents
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: `docs/work-orders/HANDOVER_20260828.md` (前任 Opus の引き継ぎ) は歴史的記録として保持。**本書が現在地を上書きする** — 前書の「未決事項」「既知の欠落」の多くは本セッションで解消済み

## 1. 現在地 (branch `conformance-effectivation-and-r2db-service-layer`、origin へ push 済み、`main` 未マージ)

本セッションの9コミット (`2e5e427`〜`7f65853`):

| 領域 | 状態 |
|---|---|
| CCR-13/14/15 | **第4版で全件採用** (依頼者裁定)。訂正記録は CCR 文書と `spec/CCR_DISPOSITION.md` の両方 |
| 従属判断 | **全裁定済み**: アドレス再利用=案iii (catalog 宣言)、in-band 発行=案B (control credential の発行のみ帯域外。application credential の発行は in-band)、base path=`/control/v1` (旧実装の全 router 実測で非重複確認済み)、`batch_entities`=4、`MutationResult` v1 拡張=行う、配備 posture=B (peer 認証) |
| 共通契約 | **1.1.0 文言化済み** (`spec/data-service-api.v1.json`)。全変更 additive。packaged copy は byte-identical 同期 |
| credential 永続化 | 済 (`0005_credential_store.sql`、`PostgresCredentialStore`、verifier のみ保存、per-request 参照で bound 0 維持、終端 revoke enforcement 済み) |
| composition root | 済 (`r2db_api.main:app`。構成宣言型、起動失敗はうるさく落ちる) |
| 暫定 CLI | 済 (`python -m r2db_api.ops`。CCR-14 実装までの暫定と明記。delete-credential は revoke 済みのみ) |
| 配備ファイル | 済 (`r2db-api/deploy/`: systemd/nginx/env/runbook。段階1=8443。**実機適用は未実施**) |
| conformance | C-01/03/08 に加え **C-11 (文書の契約適合)/C-12 (申告と実挙動の一致)/C-13 (revoke 終端性)** が3 adapter で実行可能。C-14/15/16 は not yet executable で登録。port は v1.1 (`CONFORMANCE_ADAPTER_V1.md` §11) |
| テスト | `./.venv/bin/python -m pytest` で **323 passed** (venv 3.11。system python3 は 3.9 で不可) |

## 2. 残る実装フェーズ (依頼者指示: 新セッションで実施)

`spec/CCR_DISPOSITION.md`「実装順序」に従う。

1. **CCR-13 storage 実装** (r2db-api): 型付き列化 (`field_type`) と同時に、catalog の区分宣言 (`mutation_class` / `address_fields` / `address_reuse` / `unique_keys`)、一意性 (`create_index` + `unique`)、upsert 再有効化、revision precondition、`MutationResult.assigned_addresses`、`order_by`、pagination。**勤務表クライアント移行の前提** (前書 §6 の分析は有効: 主キー・型・NOT NULL・DEFAULT・ソート・offset ページングが必要)
2. **CCR-14 control plane HTTP 面** (r2db-api): `/control/v1` の11 endpoint (案B: issue は role=runtime/developer のみ、role=control は CAPABILITY_UNSUPPORTED)。bootstrap/reset の儀式。実装後に C-14/C-15 を executable 化し、暫定 CLI の位置づけを再定義
3. **MitateDB の HTTP 層と永続化**: 二実装要件 (「2つの実装が同じ公開 API を提供」) を HTTP 越しに実証する前提。現在は in-process のみ + `:memory:`
4. **耐久 audit sink** (両 peer 共通の既知ギャップ。CLI 制御操作の永続 audit もこれ待ち)
5. 配備の実機適用 (段階1) は運用者作業。段階2の path 振り分けは `/v1/schema/operations` に exact-match が要る (実測済み、`deploy/DEPLOYMENT_RUNBOOK.md` §4)

## 3. 判断の軸と約束事 (前書 §8 を継承、追加あり)

- 堅牢で安全が第一、次に最大限の自由。ゲートでなくガードレール。機構でなく結果を要求し、結果は検証可能な性質に分解する
- 採否・裁定は依頼者。不確実な点は両論提示 (推奨は付けてよいが決定と書き分ける)
- **利用設計者は AI エージェント** (依頼者言明): 宣言は読まれる前提でよく、declare-the-hazard 型のガードレールが成立しやすい
- **コミットは push とセット** (依頼者ルール)。push 前に `git log --format='%an <%ae>'` で r2fish noreply のみを確認
- adapter は peer の不足を埋めない。skip は fail に変える。変異注入で検出力を確かめる。復元は scratchpad バックアップ経由 (`git checkout` 禁止)
- PostgreSQL 残骸ゼロ (`r2db(test|svc|http)` prefix)。**クラスタ上の `app_*` 11個・`r2db_control`・`r2db_admin`・`auth_api` は旧実装の既存オブジェクトで残骸ではない。触れない** (本セッションでレビュアが残骸と誤認しかけた)
- 公開リポジトリ規約 (実 credential・実ホスト・実パス・個人名なし)。本書もそれに従う

## 4. 本セッションで犯し、レビューで捕捉された誤り (再発防止)

1. **契約 1.1.0 初稿の JSON Schema 欠陥**: `EntityDescriptor` の `if` が `mutation_class` 不在時に空虚に真となり then が発火、既存実装の応答を自契約違反にするところだった (`if` に `required` を足して修正)。教訓: **応答を契約 schema で検証するテストの不在が原因** — C-11 として恒久化した
2. **CCR 第4版初稿の配線漏れ**: 区分表を導入しながら normative 条項 (変更表) に半分しか配線せず、delete が無制限のままだった
3. **案B の schema 体現の取り違え**: role enum から control を外すと拒否が `VALIDATION_FAILED` になり、裁定した `CAPABILITY_UNSUPPORTED` (additive に解除可能) と食い違った。enum に残して意味論で拒否する形に修正
4. **Sonnet の初版 MitateDB plug が拒否を捏造**: peer に提示すれば `VALIDATION_FAILED` が返る実在の不適合を隠していた。原則「adapter は peer の不足を埋めない」の違反であり、修正後の C-12 がこの不適合自体を捕捉・修正させた
5. 前任の誤り7 (git checkout での作業破棄) は再発ゼロ。全復元が scratchpad 経由で行われた

共通する教訓は前任と同じ「検証せずに信じない」だが、形が違う: 本セッションの欠陥はいずれも**初稿を独立レビューに通す運用**で商品到達前に止まった。設計→実装→レビューの3役分離は機能している。レビュー往復は CCR 第3版→第4版で2巡、契約 1.1.0 で1巡、conformance で1巡が実際に必要だった — 1巡で済むと想定しないこと。

## 5. 細部の申し送り

- `r2db-api` の upsert は**現在意図的に CAPABILITY_UNSUPPORTED** (契約 1.1.0 が一意性宣言に意味を紐づけたため)。フェーズ1で宣言実装とともに再有効化する。実行コードは到達不能コメント付きで温存済み
- `revision_preconditions` の6条項、addressability の5性質、案iii の再利用宣言は契約に文言化済み — フェーズ1はこれを実装するだけで、契約判断は残っていない
- C-14/15 の conformance 条件の中身は CCR 文書「新規 invariant は不要」節と契約 `control_plane` 節に列挙済み
- MitateDB の `contract_version` は 1.1.0 申告済み (新 capability は unavailable)。`transact` は契約語彙内の未提供操作を `CapabilityError` で拒否する形に修正済み
- 破壊的確認の有効性定義 (C-06 共通化、MitateDB の確認トークン不検証) は**依然未解決の契約判断**。CCR-14 の失効確認条項はこれに依存 (採用済みだが実効化待ち)
- 旧実装のパス一覧は前書 §2.5 より実測が広い (`/v1/schema` prefix 共有あり)。正は `deploy/DEPLOYMENT_RUNBOOK.md` §4
