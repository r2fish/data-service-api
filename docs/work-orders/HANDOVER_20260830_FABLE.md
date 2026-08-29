# 引き継ぎ — 2026-08-30 (第7次。Q-1 実効化フェーズ完了時点)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー: Opus subagent (独立レビュー + 敵対的変異、各 WP で継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: `HANDOVER_20260829_FABLE.md` §3 (判断の軸と約束事)・§4 (再発防止)、`HANDOVER_20260829_FABLE3.md` §4 (追加ルール)、`HANDOVER_20260829_FABLE4.md` §4 (教訓) は**全て継続**。現在地のみ本書が上書きする

## 1. 現在地 (branch `conformance-effectivation-and-r2db-service-layer`)

**Q-1 実効化 (宣言と復唱、契約 1.2.0) は WP-0〜WP-6 まで全 WP 完了。** 正典は `spec/CCR_DISPOSITION.md` 従属判断6 (裁定) と従属判断7 (裁定)、実施設計・記録は `docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` v1.6 (本 WP-6 で最終化、§8 に完了総括と将来課題台帳を新設)。

WP-1〜WP-5 のコミット (**全て main マージ済み・push 済み**):

| コミット | WP | 内容 |
|---|---|---|
| `16be7cb` | WP-0 | 設計 (Q-1 実効化: 宣言と復唱、契約 1.2.0) |
| `fe8d0b7` | WP-1 | 契約 1.2.0 公開 — declare-and-echo 意味論 + maxLength 256 + 従属判断7 (A)(B) スキーマ閉鎖/details codify + packaged copy 同期 + 逆向き検証テスト |
| `5d3e930` | WP-2 | C-06 destructive-confirmation suite 新設 + conformance port v1.6 (details マッピング・`drop_entity`・probe→echo) |
| `4cfe00a` | WP-3 | r2db-api 実効化単一コミット — 句構成共有モジュール・6 call site の details 宣言・制御面ゲート (uow 内直列化)・`limit_class` 全数・版数 flip 両面 |
| `97163de` | WP-4 | 儀式 CLI (`ops.py` の `reset`/`delete-credential`) の declare-and-echo 化 + runbook/playbook 更新 |
| `dcff077` | WP-5 | MitateDB-api 適合修正単一コミット — truthy 判定廃止・句構成・`limit_class` 適合 (Q1-D11) + 版数 flip |

**WP-6 (本セッション、記録整理 — 最終 WP) はドキュメントのみで、コミットしていない** (発注の制約どおり)。作業ツリーに以下の変更を残したまま報告する:

- `spec/CCR_DISPOSITION.md`: 従属判断6 に実施済み追記、従属判断7 (B) の実装完了 (r2db WP-3・MitateDB WP-5、limit_class 全数 + AST 固定) を反映
- `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md`: §0.5 見出しに実施完了の追記 (本文の休止条項記述は削除せず保持)
- `security/CONTROL_MAPPING.md`: SI-09 行の r2db 列に Q-1 実効化 evidence (共有句構成モジュール・6 call site・制御面ゲートの uow 内直列化・CLI declare-and-echo・型検査、実在テスト名を確認のうえ引用)、Common evidence 列に C-06 (3 adapter 厳格) を追記
- `conformance-tests/CONDITIONS.md`: C-06 行に基線分岐の残置宣言 (`test_c06_branch_dispatch_vacuity_guard` が実行毎にこれを機械的に固定する旨) を追記
- `r2db-api/README.md`: `r2db-api-http` adapter の条件列挙に C-06 を追加 (`C-01/C-03/C-06/C-08/C-11/C-12/C-14/C-15/C-17/C-18`)。ルート README・r2db-api README の destructive 関連記述は declare-and-echo 後の実態と矛盾なしを確認済み (変更なし)
- `docs/design/DESTRUCTIVE_CONFIRMATION_V1.md`: v1.5 → v1.6 (最終化)。§8 新設 — Q-1 完了総括と将来課題台帳 (a)〜(e)
- 本書 `docs/work-orders/HANDOVER_20260830_FABLE.md` (新規)

- root suite 実測 (WP-5 followup 時点、文書のみの本 WP-6 では suite に影響なし): **814 passed / 0 failed / 0 skipped** (2 回連続実測、`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §7.10)。本 WP-6 完了条件として同期 1 回の再実測を行うこと (下記 §3 参照 — 本書執筆時点ではまだ実測前)

## 2. 本セッションの監督決定一覧 (依頼者が覆せる形。すべて `docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` に一次記録)

Q-1 全体を通じて確定した監督決定 (Q1-D1〜D11、§3 および各 WP 実装記録に分散して記録されているものをここに集約):

- **Q1-D1**: revoke gate は「最後の有効 control credential」のみ (公開済み 1.1.0 条項どおり)。application credential・最後でない control credential は確認不要のまま
- **Q1-D2**: 句の綴りは契約で固定せず互換対象外。クライアントは常に拒否宣言から復唱する。旧固定句 (`"DELETE"`/`"DROP_ENTITY"`/`"DROP_INDEX"`) の受理はこの帰結として終了した
- **Q1-D3**: 状態指紋は既存 `schema_revision` (アプリ全体の単調カウンタ) を流用する。失効が要求より広くなる方向は安全側として許容
- **Q1-D4**: CLI gate 対象は `reset`/`delete-credential` のみ (`revoke-credential` は対象外 — application credential 向けの確認不要操作であり、インシデント対応時の一括 revoke に摩擦を持ち込まない)
- **Q1-D5**: port v1.6 の破壊的 schema op は `drop_entity` のみ。`drop_index` は C-06 v2 候補として台帳へ (本書 §1・design §8.1(a))
- **Q1-D6**: データ面の拒否宣言に `audited` を載せない (耐久監査が data-plane に未実装のため虚偽になる)
- **Q1-D7**: 従属判断7 (外部レビュー指摘5 — スキーマ閉鎖・details codify・OpenAPI 化不要) は契約 1.2.0 に同梱する (依頼者委任のもとの監督決定)
- **Q1-D8**: `structured.py` の Mutation values 100 フィールド超チェックは `LIMIT_EXCEEDED` でなく `VALIDATION_FAILED` へ再分類 (契約 `maxProperties` の shape 境界の鏡写しであり、配備可変なリソースクラスではないため)
- **Q1-D9**: `delete` の確認句に正規化 where digest を含める (probe した狭い句が広い削除 — where 空 = 全行 — に流用できる穴を塞ぐ)
- **Q1-D10**: `delete` の確認句にさらに `@schema_revision` 指紋を追加する。行自体は名前で再作成される対象ではないが、where-digest 単体は entity の現在 schema と無関係な純関数であり、drop→同名 recreate を跨いで旧 delete 句が生存しうる読みの穴を、3句すべてに指紋規律を統一することで閉じた (実測: revision N で probe → drop_entity → 同名 create → 旧句 echo が実際に拒否されることを in-memory・実 PostgreSQL 両方で確認済み)
- **Q1-D11**: MitateDB の `max_fields` 系 3 箇所 (write-payload 幅・schema-field 数・read-projection 幅) は `ResourceLimitError`(`limit_class`) でなく `ValidationError` へ再分類。宣言数値 (`capabilities().limits[class]`) と実際に踏む閾値が食い違ったまま `limit_class` をタグ付けする WP-5 本体時点の暫定判断 (不正確な宣言) を、レビューを受けて監督裁定で不採用にした
- **従属判断7 (C) の再確認 (`spec/CCR_DISPOSITION.md`)**: OpenAPI 化は不要 (`document_type` で非 OpenAPI であることを既に宣言済み)。1.2.0 同梱判断も Q1-D7 に含まれる。WP-6 で改めて確認し、本フェーズを通じて覆す事由は生じなかった (依頼者が覆せる標準記録として継続)

## 3. 次の一手

1. **本 WP-6 の残作業 (本書執筆と同一セッションで完了させること)**: root suite を同期 1 回実行し 814 passed / 0 failed / 0 skipped を再確認する。文書のみの変更であり suite は不変のはずだが、実測せずに報告しないこと (本セッションの発注 items 8 の完了条件)
2. **フェーズ3: MitateDB-api の HTTP 層と永続化** (C-14/C-15 の provided 化を含む。r2db-api は WP-5 で両 adapter とも provided 化済みだが MitateDB-api はまだ surface-absent のまま — `conformance-tests/CONDITIONS.md` C-14/C-15 行参照)
3. **フェーズ4: application-plane の耐久 audit sink** (control-plane 分は CCR-14 WP-6 の `control_audit` で先行実施済み。この形状を再利用してよいが拘束しない — `security/CONTROL_MAPPING.md` R-11 節)
4. **契約 additive 候補束の一括判断 (1.3.0 検討時)**: `docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(e) に集約した4件 (`CredentialsResult.must_rotate` 露出・`target_id` 監査語彙・`audit` role 読み取り・per-app 発行凍結)。個別に判断してよいが、契約バージョンの分散を避けるため一括を推奨
5. **L4 (r2db `request_bytes` の control discovery 宣言)** は Q-1 で実施されなかった (§1 参照)。次のコード WP (宣言 flip のみで完結、契約変更不要) へ改めて繰延べる
6. 配備実機適用 (運用者作業。runbook は CCR-14 WP-6 で現行化済み)

## 4. 教訓の追加 (前書 §3/§4 継承に追加。本セッションの実記録から抽出)

- **厳格分岐の初実行は計画された工程であり、事後の偶然の検証ではない**: WP-0/WP-1 は provided 分岐 (厳格分岐) を静的レビューのみで確定させ、実行は意図的に WP-3 (r2db) / WP-5 (MitateDB) の完了条件へ据え置いた。両 WP とも実際に「初回実行デバッグでの発見」節を持ち、conformance suite 側の想定漏れ (r2db: C-13/C-15 の想定外赤化、`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §5.2。MitateDB: V2b-wire の想定外赤化、同 §7.4) を製品側の欠陥と取り違えずに切り分けた。「静的レビューのみの門を通過したコードは、初回実行まで実証されていない」という前提(CCR-14 WP-5 §14.2 の先例と同型)を、破壊的確認の実効化でも再確認した
- **レビュー変異はテストの検出力そのものを測る道具であり、実装の正しさを測る道具ではない**: 各 WP のレビュー追加テストは、そのテストを守るべき性質を実際に壊す変異 (存在チェック化・指紋除去・details キー欠落・gate 判定の弱化等) を注入し赤化を実測してから、scratchpad 経由 (`git checkout` 不使用) で復元・diff 一致確認する、という完了条件が全 WP で一貫していた (WP-3: 6 本、WP-4: 3+3 本、WP-5: 5+3 本、WP-6: 3 本 + レビュア5本)。生存変異は「受理境界」(構造的に検出不能な領域、本書 design §8.1(c)) として正直に記録し、テストで埋めようとしない規律も一貫していた
- **申告 flip WP のレビューは宣言義務の全数突合を要求する**: `limit_class` の付与漏れ (WP-3 followup MA-1) は AST 静的スキャン (`test_limit_class_vocabulary.py`、r2db 19 箇所・MitateDB 6 箇所) による全数固定で解決された。個別テストの追加だけでは「新しい emission 箇所が将来追加されたときの付与漏れ」を防げない — 版数 flip を伴う WP は、宣言語彙 (details キー・limit_class 等) を持つ全 call site を静的解析で列挙し尽くす完了条件を課すこと
- **設計文書の規範文は削除せず、新しい決定は追記または導出文書側の訂正で表現する**: `R2DB_CCR14_CONTROL_PLANE_V1.md` R-5 m-2 (「唯一の復旧は reset」) が後続の R-10 (break-glass 追加) で古くなった際、m-2 の原文は書き換えず「(補記、WP-6 レビュー: ...)」を追記するに留めた (同ファイル §1 R-5)。本 WP-6 の §0.5 見出し追記もこの前例に倣い、休止条項の原文を保持したまま実施完了の事実だけを追記した
- **契約解釈が genuinely ambiguous なときは、独断で片方を選ばず両解釈と影響を報告する**: MitateDB WP-5 レビュー MA-1 (`atomic_mutation.operations` がバッチ限定か一般語彙かの解釈論点) は、adapter 側を書き換えれば conformance を green にできることを確認した上で、それが「実クライアントの使い方を偽る」変更になると判断し不採用にした。宣言・挙動とも変更せず、両解釈・実測・不採用理由をコードコメントに全て記録し、契約側の明確化を将来の CCR として提起する形に留めた (design §8.1(b))
- **将来課題は個別に埋もれさせず一本の台帳に集約する**: CCR-14 の契約 additive 候補が §14.4 に集約されていた前例に倣い、Q-1 自身の将来課題 (v2 候補・解釈論点・受理境界・未実施のまま残った項目・契約候補束) も本 WP-6 で `DESTRUCTIVE_CONFIRMATION_V1.md` §8 の一本の台帳にまとめた。次フェーズの担当者が個別の WP 記録を読み返さなくても済む形にすることが記録整理 WP 自体の目的である
