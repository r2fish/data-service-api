# Q-1 実効化設計 — 宣言と復唱 (destructive confirmation)、契約 1.2.0

- 版数: v1.3 (2026-08-30。WP-3 実装 (r2db-api の declare-and-echo 実効化 — R-2 全部 + R-3 + limit_class/212 再分類 + 版数 flip 両面 + 旧固定句 27+ 箇所更新 + TRUTHFUL_DETERRENCE 更新) を §4 に記録。v1.2 は v1.1 への WP-1 実装フェーズ独立レビュー (Opus、blocker 1 / major 8 / minor 4 / nit 4、全件実測裏付き) を全反映。v1.1 は v1.0 への WP-0 独立レビュー (blocker 3 / major 7 / minor 10 / nit 3、全件実測裏付き) を全反映し、従属判断7 (契約スキーマ閉鎖ほか) を統合したもの)
- 正典: `spec/CCR_DISPOSITION.md` 従属判断6 (裁定、2026-08-29) および従属判断7 (2026-08-29、依頼者裁定案を監督検証のうえ WP-1 で記録)。たたき台と守備範囲合意は `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §0.5。本書は裁定を**実施する**設計であり、裁定内容を再交渉しない
- 適用範囲: 共通契約 (spec) + conformance (C-06) + r2db-api (データ/schema 面・制御面・儀式 CLI) + MitateDB-api
- 実施順序は裁定どおり: 契約 1.2.0 文言化 → C-06 共通 suite → CCR-14 休止条項の実効化 (r2db) → MitateDB の確認内容検証の適合修正

## 0. 裁定の要件 (逐語準拠の要約)

### 0.1 従属判断6 (宣言と復唱)

1. 確認なしの破壊的要求は `DESTRUCTIVE_CONFIRMATION_REQUIRED` で拒否し、problem+json に機械可読で宣言する: `required_confirmation` (正準確認句 — 操作・対象・帰結クラスから決定論的に構成。再作成可能な対象は状態指紋を含め、古い句の再利用を無効化)、`consequence`、`reversible_alternative`、`recovery`
2. 有効な確認 = `destructive: true` **かつ**確認句の全文一致。存在チェックのみの実装は不適合
3. サーバは句を再計算できるため無状態 — トークン保存・失効管理・SI-08 の新資源を持ち込まない
4. 適用範囲は全破壊的操作の共通定義 (C-06 の共通化): CCR-14 の失効確認条項、既存の破壊的 schema 操作、儀式 CLI の確認引数、将来の削除系
5. 守備範囲は「要求の曖昧さの排除」まで。意図しない/悪意の正規要求の防御は R-11 層 (確認機構の責務ではない)。**残余の明記** (WP-0 n-2): 決定論的な句はクライアントスクリプトへの直書き・復唱の自動化を妨げられない。誤操作防御の実効は「エージェントが宣言を読む」前提 (本契約の利用者前提) に依存する
6. 契約 1.1.0 は公開済みのため additive 契約変更 = **1.2.0**

### 0.2 従属判断7 (外部レビュー指摘5への裁定。依頼者案 2026-08-29、監督検証で数値訂正)

新規 CCR ではなく additive 変更として扱い、契約 1.2.0 に同梱する (同梱判断は依頼者委任のもと監督決定 Q1-D7):

- **(A) スキーマ閉鎖**: 開いている応答スキーマ **11 種** (`QueryResult, MutationResult, CatalogDocument, SchemaOperationResult, AuditResult, ApplicationStateResult, ApplicationsResult, CredentialIssued, CredentialsResult, CredentialRotated, CredentialStateResult`) + `definitions.EntityDescriptor` + 唯一開いている request の `AuditQueryRequest` に `additionalProperties: false`。同一コミットで「現応答に schema 超過フィールド無し」の逆向き検証を追加 (r2db 全応答構築は実測 0 violation 済み)。**封筒のみ閉鎖**: `CapabilityDocument` 内部の 3 辞書 (capabilities/limits/limit_enforcement) と capability entry 値スキーマは「開いたキー空間」が意図された別機構であり閉じない (実装が operators/operations 等の追加キーを現に置く)。この意図を契約注記として明文化する
- **(B) details 語彙の codify**: `LIMIT_EXCEEDED` の details に必須 `limit_class` (`limits.classes` のメンバー)。`control_plane.py` が既に emit する `audited`/`attribution` と、同系の `futility` (監督追加提案、同じ `_deny` 系で emit 済み) を定義済み optional details キーとして codify。**details 自体は閉じない** (将来の宣言追加の余地。SI-10 の非開示規範の下で内容は縛られる — SI-10 は details 自由の積極根拠ではなく非開示規範である点を記録文に明記)。あわせて宣言語彙規則: `capabilities().limits`/`limit_enforcement` のキーは `limits.classes` のメンバーでなければならない (MitateDB の独自語彙 `fields`/`filter_terms` は WP-5 で適合修正)
- **(C)** OpenAPI 化は不要 (document_type 宣言済み)。1.2.0 同梱 (Q1-D7)
- **既存決定の明示的転換**: CCR-14 設計 MINOR-3 の「response schema は意図的に additionalProperties: false を宣言しない (additive 変更許容)」は本判断で**覆される**。転換根拠: 公開後は additive 変更も版数を上げる規律が確立済みで開放の前方互換益は消滅し、閉鎖の宣言真実性益が上回る。見落とし是正ではなく方針転換として記録する

## 1. 設計要件

### R-1: 契約 1.2.0 文言 (additive)

`spec/data-service-api.v1.json` に以下を加える。`DESTRUCTIVE_CONFIRMATION_REQUIRED` は 1.1.0 の `errors.codes` に既在 — 追加するのは**意味論**のみ。

- トップレベルに `destructive_confirmation` セクションを新設 (新セクション追加は排他検査に掛からないことを実測済み):
  1. **対象操作**: `delete` (Mutation/ScopedMutation)、`drop_entity`、`drop_index` (SchemaOperationRequest)、`revoke_credential` のうち「最後の有効な control credential の失効」。将来の削除系はこの定義を継承
  2. **拒否**: 有効な確認を伴わない対象操作は実行せず `DESTRUCTIVE_CONFIRMATION_REQUIRED` (HTTP 409)。`details` は 4 キーを**すべて**持つ: `required_confirmation` (string)、`consequence` (string)、`reversible_alternative` (string または null)、`recovery` (string または null)。**string 値は非空でなければならない** (WP-0 MA-6)。null は「真実として存在しない」の宣言であり省略は不適合。null の真実性 (実在する代替を null と偽る実装) はテストで検証不能 — この限界を契約に明記する (真実性は SI 全体の宣言原則が負う)。**複数の破壊的操作が確認を要する要求では、宣言は最初に拒否した操作を指す**。操作の識別子 (`operation_index` 等) は将来の additive 追加余地として残す (WP-0 MA-5)
  3. **有効な確認**: `destructive` が `true` (**フィールド欠落は false と同値**と明記、WP-0 m-6)、かつ `confirmation` が「サーバがこの要求に対しいま宣言する `required_confirmation`」と **JSON デコード後の Unicode コードポイント列として完全一致** (正規化・大小文字畳み込み・トリムを行わない。WP-0 追記4)。部分一致・存在チェック・truthy 判定は不適合
  4. **句の構成**: 操作・対象(その作用範囲を含む)・帰結クラス**のみ**から決定論的に構成する — 要求の `destructive`/`confirmation` フィールド自身・`request_id`・時刻等、要求ごとに変わる付帯情報は導出入力に含めない。したがって確認フィールドの有無だけが異なる同一要求は同一句を得る(WP-1 fix-round B-1。「the same request」の曖昧さを排除)。構成規則は実装固有 (契約は綴りを固定しない) だが: (a) 同一要求への再計算は常に同一句 (無状態)、(a') **対象には操作の作用範囲を含める(例: delete では選択条件)。作用範囲が異なる要求は異なる句を得る**(WP-1 fix-round M-3。Q1-D9 の契約側への昇格)、(b) 名前で再作成可能な対象 (entity・index 等) には状態指紋を含め、**対象の再作成 (同名での drop→create) および schema 変化のいずれによっても** 旧句が無効になること(WP-1 fix-round M-2。「schema 変化」のみでは同一 schema での再作成後に旧句が復活する読みを塞げなかった)、(c) **句に載せる対象名は当該実装の識別子検証を通過したものに限る** (未検証クライアント入力の応答反射の禁止。WP-0 B-3)、(d) 句は `confirmation` の maxLength に収まること — **収まらない対象は有界の決定論的 digest で指す** (契約は識別子長を縛らないため、この逃げ道が無いと充足不能な合法状態が構成できる。WP-0 B-2)
  5. **確認検査の誤り優先順位**: shape/認証・認可/対象存在の検証より**後**、precondition 評価と実行より**前** (WP-0 m-5。現行実装の順序と一致)
  6. **クライアント義務**: 句は拒否応答の宣言から取得して復唱する。綴りの推測・ハードコードは互換対象外
  7. **非対象操作**: destructive 意味論を持たない要求 (および gate 条件を満たさない revoke) では `destructive`/`confirmation` は schema どおり受理され検査されない
  8. **守備範囲**: §0.1-5 の合意 (残余含む) を契約文として明記
- `confirmation` の maxLength を **128 → 256** に引き上げ (Mutation/ScopedMutation/SchemaOperationRequest/CredentialRevokeRequest の 4 箇所。受理域の拡大 = additive。WP-0 B-1/B-2 の主解)
- `revoke_credential` semantics の休止条項を実効化文言に差し替え: 「最後の有効な control credential の失効は destructive_confirmation 定義に従う有効な確認を要する。それ以外の失効 (application credential・最後でない control credential) は確認を要さない」。解決を 1.2.0 と記す
- **従属判断7 (A)**: §0.2 のとおり 13 schema の封筒を閉鎖。WP-1 fix-round M-7 (独立レビュー、SECRET_LEAK 級の実証): 封筒のみでは不十分で、ネスト行 schema 4 箇所 (`ApplicationsResult.applications[]`/`CredentialsResult.credentials[]`/`MutationResult.assigned_addresses[]`/`EntityDescriptor.unique_keys[]`) も閉鎖し、余剰キー拒否の positive control を追加。意図的に開けたまま残す4箇所 (`CapabilityDocument` 内部辞書、`MutationResult...address`、`AuditResult.events[]`、`Mutation`/`ScopedMutation.values`) には契約自身に開放意図を注記
- **従属判断7 (B)**: `errors` セクションに details 定義済みキーを codify — `LIMIT_EXCEEDED` は `limit_class` (required、`limits.classes` メンバー)、全コード共通の optional キーとして `audited` (bool。真実の場合のみ)・`attribution` (string)・`futility` (string)。details は開いたまま。`capabilities().limits`/`limit_enforcement` のキーは `limits.classes` メンバー限定の宣言語彙規則を追加
- `contract_version` → `1.2.0`。実装は自らの宣言が 1.2.0 以上のときに限り本定義群への適合を申告したことになる。1.1.0 宣言実装は 1.1.0 意味論のまま適合 — **各実装の版数 flip はその実挙動と同一コミットでのみ** (peer 単位の単一コミット規則)

### R-2: r2db データ/schema 面 — 句構成と宣言 details

現行 `require_destructive_confirmation` (`structured.py`) は既に全文一致検査を行う。変更点:

1. **句構成の共有モジュール** (WP-0 m-10): 句書式は `structured.py` に一元定義し、data 面・制御面 (`control_plane.py`)・CLI (`ops.py`) は同一の定義/定数を参照する。3 面の書式一致を固定するテストを置く。書式:
   - `delete`: `DELETE <entity> @where=<digest16>` — digest16 は**識別子検証・bind 済み**の where 述語列の正準直列化 (キー順固定 JSON) の SHA-256 先頭 16 hex。probe した狭い句が広い削除 (where 空 = 全行) に流用できる穴を塞ぐ (WP-0 MA-4)。where 空にも digest は定まる。行は名前で再作成される対象でないため schema 指紋は不要
   - `drop_entity`: `DROP_ENTITY <entity> @schema_revision=<n>`
   - `drop_index`: `DROP_INDEX <entity>.<index> @schema_revision=<n>` — 索引名は entity 単位の名前空間 (`structured.py` の indexes[entity][index] / PostgreSQL 物理名 `<table>__<index>`) のため entity を句に含める (WP-0 B-1)
   - 長さ検算 (r2db 固有の識別子上限 63 — 契約由来でない旨を注記): 最長は drop_index の 11+63+1+63+18+20 = 176 ≤ **256** (R-1 の引き上げ後。WP-3 followup nit n-1: 実装時点の式は "@schema_revision=" 部分を 19 と誤カウントし 177 としていたが、正しくは 18 で 176 — assert 自体は保守側のため実害なし、値の意味のみ訂正)。句構成関数はこの帰結を assert しテストで固定。delete 句にも同じ指紋を含める設計変更 (監督決定 Q1-D10、WP-3 followup m-2) により、delete 句の最長も 7+63+8+16+18+20=132 として同様に assert される
   - n は当該アプリの現在 schema_revision。in-memory は `ApplicationCell.schema_revision`。**PostgreSQL は読み取り経路を新設**する: `_r2db_schema_revision` は `_bump_revision` (UPDATE…RETURNING) しか持たないため、同一トランザクション内 SELECT を追加 (行は 0003 が revision 0 で挿入済み・developer_role 所有。WP-0 m-1)。全 schema 操作で単調増加すること (両 backend 実測済み) により同名再作成を含む schema 変化で旧句が失効
2. **拒否 details の合成**: `require_destructive_confirmation` を「句 + 4 宣言」を受けて `fail(..., details={...})` する形に拡張。呼び出し 6 箇所 (ApplicationCell / PostgresCell × delete / drop_entity / drop_index) の配置と順序は不変 (R-1-5 の優先順位 = 現行 m-5 順序)。宣言の真実値:
   - `delete`: consequence = filter に一致する行を恒久削除、in-band 復元なし / reversible_alternative = null / recovery = null
   - `drop_entity`: consequence = entity と全行・索引を恒久破壊、同名再作成は新しい entity / reversible_alternative = null / recovery = null
   - `drop_index`: consequence = 索引を破壊 (クエリ意味論不変、性能のみ) / reversible_alternative = null / recovery = `create_index` による同定義再作成 (索引はデータを持たないため完全復旧)
   - null は捏造しない。データ面には耐久監査が無いため `audited` は**載せない** (Q1-D6)
3. 旧固定句 (`"DELETE"`/`"DROP_ENTITY"`/`"DROP_INDEX"`) の受理は終了 (declare-and-echo 下で互換問題なし、Q1-D2)。**影響一覧 (WP-0 実測、WP-3 発注書に逐語で載せる)**: 実装 6 箇所 (`structured.py:910/1070/1108`、`postgres.py:1150/1481/1509`)、adapter 4 箇所 (`conformance_adapter_r2db.py:448,507`、`conformance_adapter_r2db_http.py:1647,1709`)、r2db ローカルテスト **17 箇所** (`test_foundation.py:479,803,806,898,1273,1297,1563,1577,1602,1688,1734`、`test_http.py:623,731`、`test_postgres.py:975,1032,1368,1371,1522,1603,1637,1953,1968,1985`)。取りこぼし 1 箇所 = 旧句受理の残存なので、WP-3 完了条件に「上記全箇所の更新確認 + 旧句 grep ゼロ」を含める
4. **従属判断7 (B) の r2db 分**: `LIMIT_EXCEEDED` 全 emission (21 箇所、WP-0/検証調査で列挙済み) に `limit_class` を追加 (既存 `resource` キーは残してよい)。**`structured.py:212` (Mutation values 100 フィールド超) は `VALIDATION_FAILED` へ再分類** — 契約 `Mutation.values.maxProperties: 100` の鏡写しであり shape 境界の enforce のため (LIMIT_EXCEEDED のままでは limit_class ∈ classes が満たせない。監督決定 Q1-D8)。status も 413→400 系へ。関連ローカルテストを追随

### R-3: r2db 制御面 — 最後の有効 control credential の gate

- **判定の新設** (`ControlPlaneService`、service 層 — B-1 教訓により HTTP 層・backend 層に置かない): revoke 対象の kind が control のとき「対象が唯一の enabled かつ未 revoked の行か」を判定し、該当時のみ gate 発動
- **判定は状態変更と同一 unit_of_work 内で直列化する** (WP-0 MA-2): `control_credentials_unit_of_work` の中で行ロック (`SELECT … FOR UPDATE`) または advisory lock を取ってから数える。uow 外の判定は「2 本同時 revoke で両方 count=2 を観測 → 確認なしロックアウト」の競合を許す。この TOCTOU は機構レベルの決定的 2 コネクション干渉テストで固定する (WP-2 儀式 lock の前例と同型)。probe→echo 間に credential が増えて gate が外れる方向は無状態設計として許容 (対象がもはや破壊的クラスでない)
- gate 発動時に有効な確認がなければ `_deny` 経路で拒否: `DESTRUCTIVE_CONFIRMATION_REQUIRED` (409)、`extra_details` に 4 宣言。`_deny` を通るため耐久監査 + `audited`/`attribution` が真実として同乗 (TRUTHFUL_DETERRENCE の 1.2.0 sibling 宣言)。C-06 は「4 キーが存在する」を見る (「4 キーのみ」ではない — audited 等が同居する)
- 句: `REVOKE_LAST_CONTROL_CREDENTIAL <credential_id>` (id はランダム生成・再利用皆無で指紋を兼ねる)
- 宣言の真実値: consequence = 最後の有効 control credential を失効させ、in-band 制御面アクセスは帯域外 reset 儀式まで失われる / reversible_alternative = `disable_credential` — **ただし最後の 1 本を disable した場合の再 enable も帯域外 break-glass (`enable-control-credential`) を要する旨まで宣言に含める** (WP-0 m-7) / recovery = 帯域外 CLI reset 儀式。`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §13 (ロックアウト復旧) と一致させる (WP-0 m-2: 参照先は同 runbook §12/§13。DEPLOYMENT_RUNBOOK ではない)
- 非 gate の revoke は現行どおり不検査で実行。順序: 認証 → must_rotate gate → 確認 gate → 実行
- 版数 flip: `service.py`/`control_plane.py` の `contract_version` を `1.2.0` へ本 WP の単一コミットで (既存 1.1.0 assert・`test_revoke_request_accepts_q1_fields_without_inspecting_them` を同時更新)

### R-4: 儀式 CLI (`ops.py`) — declare-and-echo の CLI 形

- 対象は **`reset` と `delete-credential` のみ** (WP-0 MA-1 で `revoke-credential` を除外 — CLI `revoke-credential` は application credential 対象であり、Q1-D1 が確認不要と定めた操作クラスそのもの。playbook step 3 の一括 revoke 動線 (インシデント対応) に摩擦を持ち込まない)。`bootstrap` は非破壊 (既在で CONFLICT)、`disable-*`/`enable-*` は可逆で対象外
- 機構: `--confirm <句>` を追加。無指定/不一致は実行せず stderr に problem+json 同形 (code + 4 宣言) を出力し exit 2。句は R-2 の共有定義を参照: `reset` = `RESET_CONTROL_CREDENTIALS` (store 全体が対象で名前再作成の概念がなく帰結クラスが状態非依存のため定数 — 指紋なしの理由を明記)、`delete-credential` = `DELETE_CREDENTIAL <credential_id>` (id が指紋を兼ねる)
- CLI gate は HTTP 面の revoke gate とは対象が異なる (CLI 側は erasure/全失効という帯域外・より重い操作) — 「HTTP 面の転写」ではなく「同一の宣言と復唱プロトコルの CLI 適用」と位置づける (WP-0 MA-1 の記述訂正)
- runbook §12/§13・playbook step 1 を同一 WP で更新。playbook には「reset の 1 回目の失敗は宣言取得であり reset は実行されていない」を明記 (WP-0 n-3、「run once per incident」との衝突回避)
- 拒否は state-changing でないため監査を書かない (既存 CLI 規約と整合。逸脱があれば報告)

### R-5: MitateDB — 確認内容検証の適合修正

- `cell.py` の `delete`: truthy 判定を廃し declare-and-echo に適合。**識別子検証 (`validate_identifier(collection)`) を確認検査より前に移す** — 句合成が未検証クライアント入力を応答へ反射する経路を作らないため (WP-0 B-3。r2db は既にこの順序)。確認なし/不一致は新設 `DestructiveConfirmationRequired` (FoundationError 系、機械可読 `details` 属性に 4 宣言) を raise
- `confirm` は bool から句 (str) へ。`confirm=True` 旧形は受理しない (truthy 検証こそが既知欠落)。内部呼び出し・テスト全数更新。**`transact` の rollback except タプルに新例外型を追加** (現状到達しないが穴を残さない。WP-0 m-8)
- 句: `DELETE <collection> @where=<digest16>` (R-2 と同規則 — filters 正準直列化の digest。実装固有の綴りでよいが対象規則は共通)
- adapter: `peer_confirm = confirmation` 素通し分岐を除去し port 規約 (R-6) に従う。`_CLASSIFY_ORDER` に新例外型 → `DESTRUCTIVE_CONFIRMATION_REQUIRED` を追加
- **従属判断7 の MitateDB 分**: `ResourceLimitError` に構造化 details (`limit_class`) を持たせ、`capabilities().limits` の独自語彙 `fields`/`filter_terms` を契約 15 classes への対応付けまたは削除で適合させる (対応付け先は実装調査のうえ報告 — 独断で新語彙を維持しない)
- 版数 flip: `cell.py` の `contract_version` を `1.2.0` へ本 WP の単一コミットで

### R-6: conformance — C-06 共通 suite と port v1.6

- **port 改訂 (v1.6)**:
  1. `VALID_CONFIRMATION` の実現手段: 1.2.0 以上を宣言する peer には **probe (確認なし) → 拒否宣言から `required_confirmation` 取得 → echo** の 2 段 (句のハードコード禁止)。1.1.0 宣言 peer には従来どおり peer 固有トークン供給 (互換保持)。probe が既存 suite (C-01/03/17/18 の 5 箇所) を壊さないことは WP-0 が複製リポジトリで実証済み (両 adapter 56 passed、batch probe は transact 巻き戻りで状態復元)
  2. `ConformanceDenial` に **`details` マッピングのみ**を additive に追加 (`message` は運ばない — payload 反射を port に持ち込まない既存設計の維持)。C-06 は details の**全値**に `assert_no_payload_echo` 相当を掛ける (WP-0 MA-3)
  3. 破壊的 schema op `drop_entity` を port に追加。`drop_index` は C-06 v2 として台帳へ (Q1-D5)
  4. **C-14 の absent 機構 (`_assert_control_operation_absent_or_uniformly_refused` 等) を共有モジュールへ抽出** (現状 test モジュール private。WP-0 m-4)
- **C-06 suite (`test_c06_destructive_confirmation.py`)**: 分岐は宣言 `capabilities().contract_version` の **semver パース比較** (文字列比較は 1.10.0 < 1.2.0 の罠。WP-0 m-3。契約版数分岐は本 suite が初例であることを記録):
  - **≥1.2.0 (厳格分岐)**:
    - V1 確認なし destructive delete → `DESTRUCTIVE_CONFIRMATION_REQUIRED`、4 キー全存在・string 値非空・行不変
    - V2 `destructive: false` + 正句 → 拒否。**V2b `destructive` 欠落 + 正句 → 拒否 (欠落 ≡ false)** (WP-0 m-6)
    - V3 全文一致の敵対検査: 正句+接尾辞 / 正句の**前方部分** (旧固定句 "DELETE" の残存受理はここで機械的に被覆 — 接頭辞は実句から導出しハードコードしない) / 大小文字変え / 別 entity の正句 / **別操作の正句** (drop_entity の句を delete に等) / **異なる where の正句** (MA-4 対応の digest が効くこと) → すべて拒否・状態不変
    - V4 句の決定論: 2 回の probe が同一句、**別 credential (同一アプリの別 developer) の probe も同一句** (WP-0 m-6)
    - V5 復唱 → 実行され行が消える
    - V6 指紋失効 (drop_entity): probe → 無関係な schema 変更 (add_field) → 旧句拒否 → 再 probe 新句で成功。surface-absent peer は共有 absent 機構で処理。**drop_entity にも V3 相当 (別 entity の正句・接尾辞・大小文字) を掛ける** (WP-0 m-6)
    - V7 in-band 最終 control credential gate (control plane provided peer のみ): 唯一有効状態で確認なし revoke → 拒否 + 4 宣言 + `audited: true`、復唱 → revoke 成功 → adapter 特権経路で stack 復旧。復旧コストが C-13 ベクタ5 級を超えるなら報告のうえ分割裁定
    - V8 **payload-echo probe**: 敵対的な対象名/値で probe し、details 全値に反射が無いこと (WP-0 B-3/MA-3)
  - **<1.2.0 (基線分岐)**: 確認なし destructive delete が実行されない (コード不問) + `VALID_CONFIRMATION` で成功。分岐の記録は C-14 同様。**WP-5 完了後この分岐を通る adapter はゼロになる** — 将来 peer の受け入れ口として残置し、未実行分岐である旨を CONDITIONS.md に明記 (WP-0 MA-7)
- CONDITIONS.md C-06 行を executable 化 (SI-09 のまま) + `test_conditions_register.py` の双方向照合のため condition marker 付与。C-12 の「delete は C-06 へ」注記と整合確認
- **従属判断7 (A) の逆向き検証**: c11 型の `assert_valid` (実応答 vs 閉鎖後 schema) を実応答の得られる既存フローに追加 (schema_check は additionalProperties:false 実装済み・response 系 schema は実装済みキーワードのみ — 追加は低コスト、検証調査済み)。**契約閉鎖と同一コミット (WP-1)**
- 変異注入 (各実装 WP の完了条件): 全文一致→存在チェック化 / 指紋除去 / where digest 除去 / details キー 1 個欠落 / gate の「最後の 1 件」判定除去 / **gate 判定を uow 外へ移動** (機構テストで赤) — がそれぞれ赤

### R-7: 文書

- `docs/security/TRUTHFUL_DETERRENCE_DECLARATIONS.md`: sibling 宣言節を landed へ (WP-3)
- `POSTGRES_PROVISIONING_RUNBOOK.md` §12/§13・playbook step 1: CLI declare-and-echo 化 (WP-4)
- `spec/CCR_DISPOSITION.md`: 従属判断7 の記録 (WP-1。§0.2 の訂正込み文言) と従属判断6 の実施済み追記 (WP-6)
- `R2DB_CCR14_CONTROL_PLANE_V1.md` §0.5 実施済み追記・MINOR-3 転換の相互参照 (WP-6)
- CONTROL_MAPPING SI-09 行・C-06 evidence (WP-6)

## 2. WP 分割 (各 WP = 実装 → 独立レビュー → コミット+push+main マージ)

| WP | 内容 | 完了条件 |
|---|---|---|
| WP-0 | 本設計の独立レビューと確定 | 完了 (v1.1 に全反映) |
| WP-1 | 契約 1.2.0 文言化 — 従属判断6 意味論 + maxLength 256 + 従属判断7 (A)(B) 閉鎖/codify + packaged copy 同期 (byte-identity テスト実在確認済み) + 逆向き検証テスト + CCR_DISPOSITION 従属判断7 記録 | root suite green (WP-0 が spec 1.2.0 化単独で 719 passed を実証済み)。schema_check fixture 追随は不要 (WP-0 m-9 実測) |
| WP-2 | port v1.6 (details/drop_entity/absent 機構抽出/probe→echo) + C-06 suite + CONDITIONS.md | 3 adapter とも基線/厳格分岐で green + suite 変異 |
| WP-3 | r2db 実効化 単一コミット (R-2 全部 + R-3 + limit_class/212 再分類 + 版数 flip 両面 + 旧固定句 27 箇所更新 + TRUTHFUL_DETERRENCE 更新) | C-06 厳格分岐 green・変異赤・旧句 grep ゼロ |
| WP-4 | 儀式 CLI (reset/delete-credential) + runbook/playbook | テスト + 変異 |
| WP-5 | MitateDB 適合修正 単一コミット (R-5 全部 + 版数 flip) | C-06 厳格分岐 green・変異赤 |
| WP-6 | 記録整理 (R-7 残り・基線分岐残置宣言・台帳・引き継ぎ) | 文書突合 |

## 3. 監督決定 (依頼者が覆せる)

- Q1-D1: revoke gate は「最後の有効 control credential」のみ (公開済み 1.1.0 条項どおり)。application credential・最後でない control credential は確認不要のまま
- Q1-D2: 句の綴りは契約で固定せず互換対象外 (クライアントは常に復唱)。旧固定句の受理終了はこの帰結
- Q1-D3: 状態指紋は既存 schema_revision (アプリ全体の単調カウンタ)。失効が要求より広いのは安全側
- Q1-D4: CLI gate 対象は `reset`/`delete-credential` (v1.1 で `revoke-credential` を除外 — WP-0 MA-1)
- Q1-D5: port v1.6 の破壊的 schema op は `drop_entity` のみ。`drop_index` は C-06 v2 で台帳へ
- Q1-D6: データ面の拒否に `audited` を載せない (耐久監査未実装のため虚偽になる)
- Q1-D7: 従属判断7 は 1.2.0 同梱 (依頼者委任分の判断。WP-1 未着手で手戻りゼロ・(A) は挙動変更なし・(B) は flip WP 同乗が最安)
- Q1-D8: `structured.py:212` は `VALIDATION_FAILED` へ再分類 (契約 maxProperties の鏡写し = shape 境界)
- Q1-D9: delete 句に正規化 where digest を含める (WP-0 MA-4 の受容ではなく修正を選択 — 「狭い句が広い削除に通る」は宣言と復唱の趣旨に反する)

## 4. 訂正・改訂記録

- v1.1 (2026-08-29): WP-0 独立レビュー全反映 — B-1 (drop_index 句の entity 欠落と 128 超過 → entity 込み + maxLength 256)、B-2 (識別子長非有界 → digest 逃げ道の規範化)、B-3 (句合成の入力反射 → 識別子検証後置の規範化 + V8)、MA-1 (CLI gate から revoke-credential 除外)、MA-2 (gate 判定の uow 内直列化)、MA-3 (ConformanceDenial は details のみ + echo 検査)、MA-4 (where digest、Q1-D9)、MA-5 (複数操作時の宣言指示対象)、MA-6 (非空要求 + null 限界表明)、MA-7 (基線分岐の残置宣言)、m-1〜m-10・n-1〜n-3 全反映 (個別処置は本文へ織込み)。従属判断7 を §0.2/R-1/R-2-4/R-5/R-6/WP-1 に統合 (11 種への数値訂正・MINOR-3 転換の明示・封筒のみ閉鎖・futility 追加 codify・212 再分類 Q1-D8)
- v1.2 (2026-08-29): WP-1 実装 (契約 1.2.0 文言化 + packaged copy 同期 + conformance 逆向き検証 + CCR_DISPOSITION 従属判断7 記録) への独立レビュー (Opus、blocker 1 / major 8 / minor 4 / nit 4、全件実測裏付き) を全反映。**契約文言 (R-1-4 へ統合)**: B-1 (句の導出入力を操作・対象〈作用範囲込み〉・帰結クラスのみに限定する規則を明記 — 確認フィールド自身・request_id・時刻等は導出入力に含めない。「the same request」の曖昧さを排除)、M-1 (`denial.when` を「request 全体を拒否・一部実行なし」に — 部分適用後 409 の読みを封鎖)、M-2 (状態指紋の無効化契機を「対象の再作成」と「schema 変化」の両方に — 同一 schema での drop→create 再作成による旧句復活の読みを封鎖)、M-3 (作用範囲規則を追加 — Q1-D9 の契約側への正式な昇格)、M-4 (`version_binding` の 1.2.0 新設義務 4 系統を網羅列挙 + `capability_status.rules` 新語彙規則自体への版数拘束参照)、M-5 (`versioning.compatibility` にスキーマ閉鎖を minor として扱う調停条項を追加)、M-7 (**独立レビューが SECRET_LEAK 級の実証で指摘**: 封筒閉鎖だけではネスト行 schema 経由の余剰キー漏洩を塞げない — `ApplicationsResult.applications[]`/`CredentialsResult.credentials[]`/`MutationResult.assigned_addresses[]`/`EntityDescriptor.unique_keys[]` の4箇所を追加閉鎖し、逆向き検証に余剰キー拒否の positive control を追加。意図的に開放したまま残す4箇所には契約自身に注記)、m-1 (`applies_to` の連言記述を2要素に分割)、m-2 (`errors.details_vocabulary` と `destructive_confirmation.denial.details_keys` の相互参照)、n-3 (`http_status: 409` 以外のコードの status 無記載は「未定義」であり「任意」でない旨を明記)。**conformance テスト**: M-6 (`test_c11_response_schema_conformance.py` が独自の skip 規約に初めて違反していたことの是正 — MitateDB の `pytest.skip` を C-14 型の `SurfaceAbsent` 主張検証〈3 assertion〉に置換、raw-accessor 不在の `_skip_no_raw_accessor` 系を fail に転換し vacuity guard 相当のメッセージを付与)、n-1 (raw accessor への直接属性アクセスを fail-loud に統一)、n-2 (到達不能 `return` の除去)。**台帳**: M-8+m-4 (`spec/CCR_DISPOSITION.md` 従属判断7 の実施記録を実被覆〈3 adapter: CatalogDocument/EntityDescriptor、2 adapter: ApplicationStateResult 系3種、r2db http のみ: 6種、0: AuditResult/AuditQueryRequest〉どおりに訂正し、`conformance-tests/CONDITIONS.md` C-11 行の Description/Status も実態に合わせ更新)、m-3 (`conformance_adapter_r2db_http.py` のコメント誤ファイル名を訂正)。この往復は WP-1 が「実装コードに触れず契約文言化のみ」という当初の限定スコープの範囲内で完結している

## 5. WP-3 実装記録 (r2db-api 実効化、v1.3 追記)

### 5.1 実装内容

- **句構成の共有モジュール**: `r2db_api/structured.py` に `delete_confirmation_phrase`/`drop_entity_confirmation_phrase`/`drop_index_confirmation_phrase`/`revoke_last_control_credential_confirmation_phrase` を一元定義。`control_plane.py` はこれらを import して参照 (CLI `ops.py` からの参照は WP-4)。`delete` の where 句は識別子・演算子検証済み `Predicate` 列のキー順固定 JSON (SHA-256 先頭16桁)。`drop_index` の最長句 (176 文字 — nit n-1: 実装当初は式の誤りで 177 と記録していたが訂正) は関数内 assert で固定。監督決定 Q1-D10 (followup m-2) により `delete` 句にも `@schema_revision=<n>` を追加し、その最長句 (132 文字) も同様に assert される。
- **PostgresCell の revision 読み取り経路**: `_read_schema_revision` を新設 (同一トランザクション内 `SELECT revision FROM _r2db_schema_revision`)。`_bump_revision` (UPDATE) とは独立した読み取り専用経路。
- **`require_destructive_confirmation` の拡張**: 句 + 4 宣言 (`consequence`/`reversible_alternative`/`recovery` をキーワード引数化) を受け、`details` を合成して `fail` する形に変更。呼び出し 6 箇所 (`ApplicationCell`/`PostgresCell` × delete/drop_entity/drop_index) の位置・順序は不変。データ面には `audited` を載せていない (Q1-D6 のまま)。
- **旧固定句の受理終了**: 実装 6 箇所・adapter 4 箇所・r2db ローカルテスト 27+ 箇所を新句 (probe→echo または実測 phrase 関数) に更新。`grep -rn '"DELETE"\|"DROP_ENTITY"\|"DROP_INDEX"' r2db-api/` は `legacy_token="DELETE"`/`"DROP_ENTITY"` (port v1.6 の <1.2.0 フォールバック値、r2db は 1.2.0 宣言のため実行時に到達しない) とコメント中の言及のみが残存 — 実行時の旧句送信はゼロ。
- **limit_class**: 全 `LIMIT_EXCEEDED` emission (19 箇所、`structured.py:212` の再分類後。WP-3 followup nit n-3: 実装時点は誤って 20 箇所と記録していたが実測 19 — `test_limit_class_vocabulary.py` の AST 静的スキャンで確定) に `limit_class` を追加。`structured.py:212` (Mutation values 100 フィールド超) は `VALIDATION_FAILED` (400) へ再分類。
- **V2b wire 欠落ベクタ**: 両 r2db adapter の `_build_mutation_item` で confirmation 設定を `destructive` から分離。C-06 に `test_c06_v2b_wire_destructive_omitted_with_valid_confirmation_denied` を追加 (`BatchOperation`/`attempt_batch_with_addresses` 経由で wire `destructive` 省略 + 正句を構成)。
- **制御面ゲート**: `ControlPlaneService.revoke_credential` を再構成 — kind=control かつ「唯一の enabled・未 revoked 行」の判定を `control_credentials_unit_of_work` の中で `control_credentials_locked` (Postgres: `FOR UPDATE` 全行ロック、in-memory: `ControlCredentialStore.unit_of_work` 自体が `threading.Lock` を保持) を用いて行い、gate 発動時は `_deny` 経由で拒否 (`audited`/`attribution` 同乗)。非 gate 経路 (application credential・最後でない control credential) は不検査のまま。
- **版数 flip**: `service.py`/`control_plane.py` の `contract_version` を `"1.2.0"` へ。`config/capabilities.json` は `contract_version` を含まないため変更不要 (確認済み)。C-06 の `_EXPECTED_STRICT_ADAPTER_NAMES = {"r2db-api", "r2db-api-http"}` / baseline = `{"MitateDB-api"}` に更新。

### 5.2 初回実行デバッグでの発見 (全数)

WP-2 レビューが予想した項目のうち実際に発生したもの、および未予想の発見:

1. **conformance-tests の C-13/C-15 が想定外に赤化 (suite 側の想定漏れ、製品側は正常)**: `test_c13_revocation_terminality.py::test_revoked_credential_stays_revoked_across_every_reactivation_vector` と `test_c15_bootstrap_reset_lifecycle.py::test_c15_bootstrap_refused_while_any_control_credential_exists` は、いずれも「唯一の control credential を無確認で revoke する」という、この WP 以前は常に成功していた前提のコードを含んでいた (前者: `credential_reactivation_vectors` の `inband_rotate_revoked_control_credential_attempt` が revoke をセットアップ手順として使用。後者: bootstrap 再拒否確認のための一括 revoke ループ)。ゲートの実装は正しく機能しており (これらの呼び出しが本来拒否されるべきものを拒否した)、**suite 側の修正**として: (a) 両 r2db adapter (`conformance_adapter_r2db.py`/`conformance_adapter_r2db_http.py`) の `inband_rotate_revoked_control_credential_attempt` を probe→echo 化、(b) 共通 `test_c15_bootstrap_reset_lifecycle.py` の revoke ループを probe→echo 化 (Q-1 adjudication 未定という古いコメントも実効化済みに更新)。
2. **V7 の rate 窓 429 (予想項目 (7)) は発現せず**: 実測では C-06 単独実行・全体実行のいずれでも 429 は観測されなかった (`control_requests_per_minute=60` に対し probe+echo+復旧の消費が十分小さい)。予想リスクは的中しなかったが、要注意項目として残す。
3. **V6 の決定論 re-probe が句構成の非決定性を暴く懸念 (予想項目 (1))**: 発現せず。句は entity/where/schema_revision のみの純関数であり、re-probe は毎回同一句を返した (V4/V6 とも green)。
4. **V2/V2b の評価順序 (予想項目 (2))・V3 の where/operation 別正句 (予想項目 (3)(4))・V4 の developer credential probe (予想項目 (5))**: いずれも初回実行で green。特別な追加修正は不要だった。
5. **suite 自体のバグ (予想項目 (8))**: 上記 1. 以外には見つからなかった。

### 5.3 変異注入結果 (6 本、全数赤を実測ののち scratchpad 経由で復元・diff 一致確認済み)

| # | 変異内容 | 対象 | 赤の実測方法 | 結果 |
|---|---|---|---|---|
| (i) | 全文一致→存在チェック化 (`confirmation != phrase` → `not confirmation`) | `structured.require_destructive_confirmation` | `conformance-tests/test_c06_destructive_confirmation.py -k v3` | 赤 (V3 の接尾辞付き変異句が誤って通過) |
| (ii) | schema_revision 指紋除去 (`drop_entity_confirmation_phrase` から revision を削除) | `structured.py` | `test_c06_destructive_confirmation.py -k v6` | 赤 (schema 変化後も旧句が通過) |
| (iii) | where digest 除去 (`delete_confirmation_phrase` から digest を削除) | `structured.py` | `test_c06_destructive_confirmation.py -k v3` | 赤 (別 where の正句が同一句に収束) |
| (iv) | details キー1個欠落 (`recovery` を details から除外) | `structured.require_destructive_confirmation` | `test_c06_destructive_confirmation.py -k v1` | 赤 (`_assert_four_declarations` が `recovery` 欠落を検出) |
| (v) | gate の「唯一判定」除去 (`len(active_ids)==1 and ...` を `True` に固定) | `control_plane.py::revoke_credential._body` | 新設 r2db ローカルテスト `test_revoking_a_non_last_control_credential_accepts_q1_fields_without_inspecting_them` | 赤 (最後でない control credential の revoke も無確認で拒否されるようになった) |
| (vi) | gate判定を uow 外へ (locked read を `control_credentials_unit_of_work` の外・閉じたトランザクションの `work` に対して実行) | `control_plane.py::revoke_credential` | 新設の決定的機構テスト `test_revoke_credential_gate_judgment_is_made_inside_the_open_transaction` (`_GateOrderProbeBackend` — `work.active` フラグで uow 内外を判定する test double。実 2 コネクション干渉の実測は `test_control_plane_store.py::test_control_credentials_locked_scan_serializes_against_a_concurrent_scan` が別途担う) | 赤 (assertion failure、`work` が非 active 状態で呼ばれたことを検出) |

各変異は `structured.py`/`control_plane.py` を scratchpad のバックアップコピーで復元し、`diff` で完全一致を確認済み (`git checkout` は使用していない)。

### 5.4 逸脱・疑義

- design R-2 item 1 は「CLI (`ops.py`) も共有定義を参照できる形」を求めるが、CLI 自体の declare-and-echo 化は WP-4 の管轄であり、本 WP では `ops.py` に変更を加えていない (共有関数はすでに `structured.py` に公開済みで WP-4 から import 可能)。
- C-15/C-13 の共通 suite 修正 (5.2-1) は「WP-3 は r2db-api 実効化」という本 WP のスコープ外の共通ファイルへの変更を含む。設計上は WP-2 の管轄領域だが、WP-3 の実効化がなければ検出できない不具合だったため、本 WP の完了条件 (「初回実行デバッグの発見一覧」) の一部として本 WP 内で修正した。
- ~~`conformance-tests/CONDITIONS.md` の C-06 行はまだ「全 adapter が 1.1.0 のまま」という記述のままで、本 WP の版数 flip 後は事実と異なる。~~ Opus レビュー M-2 で指摘され、本 followup コミットで実態 (r2db 両 adapter は 1.2.0 で strict 実行済み、MitateDB のみ baseline) に更新済み。基線分岐の残置宣言そのもの (「未実行分岐である旨を明記」する項) は WP-6 のまま。

### 5.5 WP-4/WP-5 への申し送り

- WP-4 (儀式 CLI): `ops.py` の `reset`/`delete-credential` に `--confirm` を追加する際は `structured.py` の `revoke_last_control_credential_confirmation_phrase` と同型の新規関数 (`RESET_CONTROL_CREDENTIALS` 定数、`DELETE_CREDENTIAL <credential_id>`) を追加し、既存の句構成関数と同じモジュールに置くこと。
- WP-5 (MitateDB): 本 WP は MitateDB-api に一切触れていない (`MitateDB-api/` 配下は無変更)。`_EXPECTED_STRICT_ADAPTER_NAMES`/`_EXPECTED_BASELINE_ADAPTER_NAMES` の更新は WP-5 で `{"r2db-api", "r2db-api-http", "MitateDB-api"}` / `frozenset()` に切り替えること。

### 5.6 Opus レビュー往復 (v1.3 followup、blocker 1 / major 3 / minor 7 / nit 6、全件実測裏付き)

WP-3 の独立レビュー (Opus) が発見した項目と、その全対応の記録。

**blocker B-1 (非 boolean truthy `destructive` の受理)**: `bind_schema_operation` (structured.py) に `bind_mutation` と同一の `isinstance(bool)` 検査を追加 (非 bool → `VALIDATION_FAILED`、確認検査より前)。`ControlPlaneService.revoke_credential` にも同型の型検査を追加 (gate 有無に関わらず適用— データ面 `bind_mutation` と同じ「request schema の enforce」であり、契約 `non_destructive_requests` が言う「検査されない」は確認*意味論*の話であって shape 検査の話ではない、という整理)。ゲート判定自体も `destructive is not True` に精密化。**「wire 型ベクタは peer-local」の整理**: port は typed (`destructive: bool` という Python シグネチャ) のため、共通 conformance suite からは「wire 上で destructive が文字列」という敵対的形状を構成できない (adapter が Python レベルで型を強制する) — この種の検査は各実装がローカルに保持する責務であり、共通 suite の対象外である。データ面 (既存挙動の固定)・schema 面・制御面 (service 直呼び + 実 HTTP wire) の計 3+ テストを r2db ローカルに追加。**実 wire 実測** (`test_control_http.py` の新設 2 テスト + 手動実行ログ): `destructive: "false"` (文字列) を実 HTTP 経由で送信 → `400 VALIDATION_FAILED` (`message: "destructive must be boolean."`)、対象の唯一 control credential は非 revoke のまま (`/capabilities` が同一 secret で 200 のまま)。別途、実 `destructive: true` 無確認 revoke → `409 DESTRUCTIVE_CONFIRMATION_REQUIRED` + 4 宣言、を同一ハーネスで確認。

**major M-1 (limit_class 無防備)**: (a) `r2db-api/tests/test_limit_class_vocabulary.py` を新設 — AST で `r2db_api` 全モジュールの `fail("LIMIT_EXCEEDED", ...)` 呼び出し (実測 19 箇所) を走査し、`details["limit_class"]` の存在と、値が契約 `limits.classes` メンバー (リテラル) または既知の動的 kind (`ResourceLimits.check`の `kind` 引数、call-site 側がすべてリテラルを渡すことが前提の名指し allowlist) であることを全数 assert。レビュア変異 B (全値 `"NOT_A_CLASS"` 化) を自分で再注入し 18 箇所の違反を実測 (赤)、scratchpad 復元で diff 完全一致確認。(b) `applications`/`credentials_per_application`/`control_requests_per_minute` (制御面) と `batch_items`/`result_items`/`query_complexity` (データ面、`ResourceLimits.check`の動的 kind 経路を含む) の計 6 経路に実応答 `limit_class` の behavioral assertion を追加。

**major M-2 (陳腐化文言)**: `test_c06_destructive_confirmation.py` のモジュール docstring・`fx` override コメント・vacuity guard 前後のコメント計 4 箇所を、r2db 両 adapter が 1.2.0/strict である実態へ更新。`CONDITIONS.md` C-06 行の「全 adapter 1.1.0」太字も同コミットで実態に更新 (基線分岐の残置宣言自体は WP-6 のまま)。

**major M-3 (audited の耐久裏付け)**: `_deny` の docstring を「`_body` から呼ばれる場合、`self._audit` は別プール/別接続で独立にコミットされ、`_body` 自身のトランザクションの rollback では消えない」という実態に更新。`test_revoking_the_last_live_control_credential_denial_carries_audited_and_attribution` に (a) 拒否直後の監査行数が +1 であること、(b) その行の `outcome`/`reason_code`/`actor_id` が実際の拒否と一致すること、(c) 拒否後も対象 credential が `capabilities()` で認証できる (revoke されていない) こと、の3 assertion を追加。

**minor m-1 (対象同一性)**: `test_revoking_an_already_revoked_different_credential_is_never_gated_by_target_identity` を新設 — 有効 control credential がちょうど1本の状態で、別の既に失効済みの credential への revoke が gate されない (無確認で実行される) ことを assert。レビュア変異 C (`len(active_ids)==1 and active_ids[0]==credential_id` → `len(active_ids)==1`) を再注入し赤を実測、復元・diff 一致確認済み。

**minor m-2 (Q1-D10)**: `delete_confirmation_phrase` に `@schema_revision=<n>` を追加 (`DELETE <entity> @where=<digest16> @schema_revision=<n>`)。監督決定 **Q1-D10**: 行は名前で再作成される対象ではないが、where-digest 単体は entity の現在の schema と無関係な純関数であるため、drop→同名 recreate を跨いで旧 delete 句が生存しうる (レビュア実測、契約 rule (b) の字義違反) -- 3句すべてに指紋規律を統一することでこの解釈の穴を閉じる (Q1-D3 の「広めの失効は安全側」の踏襲)。r2db ローカルテスト (`test_foundation.py`/`test_postgres.py` 双方に追加): レビュアの実シナリオ (revision N で probe → drop_entity → 同名 create → 旧句 echo) が実際に `DESTRUCTIVE_CONFIRMATION_REQUIRED` で拒否されることを確認 (in-memory・実 Postgres の両方で実測 green)。長さ assert も `delete` 用に新設 (worst case 132 ≤ 256)。

**minor m-3**: レビュア指摘のとおり元の WP-3 実装時点にこの再分類の専用テストが実在しなかったことを確認 -- `test_mutation_values_over_100_fields_is_validation_failed_not_limit_exceeded` を新設 (structured.py:212 相当。101 フィールドの `insert` → `VALIDATION_FAILED`、`details == {"field": "values"}`、`LIMIT_EXCEEDED` ではないこと、を assert)。

**minor m-4**: C-13/C-15 と両 r2db adapter の3箇所の probe→echo ヘルパー (`inband_rotate_revoked_control_credential_attempt` × 2 adapter、C-15 の revoke ループ) の `except ConformanceDenial` を `code == "DESTRUCTIVE_CONFIRMATION_REQUIRED"` 限定に変更 (他コードは re-raise)、echo 後の応答に `revoked: True` が含まれることを assert 追加。

**minor m-5**: `PostgresControlCredentialStore.unit_of_work` に `SET LOCAL lock_timeout` を追加 (データ面 `postgres.py::_set_timeouts` と同型)。`ControlPlaneLimits` に execution_ms 相当の設定可能値が無いため、データ面のデフォルト値 (5000ms) を固定定数として再利用 (`_CONTROL_LOCK_TIMEOUT_MS`)。既存の TOCTOU 干渉テスト (`test_control_credentials_locked_scan_serializes_against_a_concurrent_scan`) は green のまま (別接続の明示的 `SET lock_timeout` で上書きされるため無干渉)。

**minor m-6**: (a) `drop_index` の `recovery` 宣言を「非 unique index は完全復旧、unique index の再作成はデータが違反していれば `CONFLICT` になりうる」旨の条件付きに修正。(b) revoke の `reversible_alternative` 宣言から「同じ帯域外儀式」という誤った同一視を除去し、`enable-control-credential` (再有効化) と `recovery` の `reset` (新規発行) が **別々の** 帯域外手続きであることを正確に記述。

**minor m-7**: `_canonical_where_json` の `json.dumps(..., default=str, ...)` から `default=str` を除去。理由: JSON ネイティブでない値 (将来 `bind_mutation` が Decimal/datetime 等を許容するようになった場合) を `str()` に暗黙変換すると、異なる値が同じ文字列表現に収束し同一 digest に潰れる可能性がある — 除去後はそのような値が来た時点で `TypeError` が即座に上がる (握りつぶされた収束ではなく、導入時点での気づきに変わる)。

**nit n-1**: `drop_index_confirmation_phrase` の長さ検算式の誤り (`" @schema_revision="` を19文字と誤カウント、正しくは18文字) を訂正 — 最長は 177 ではなく **176**。`assert` 自体は保守側の値だったため実害なし (176 < 177 のどちらでも 256 以下)。docstring・本設計書 §1 R-2・§5.1 の該当箇所を訂正。

**nit n-2**: `revoke_last_control_credential_confirmation_phrase` の docstring 内、関数名の誤記 `_new_control_control_credential_id` (control が重複) を `control_plane._new_control_credential_id` に訂正。

**nit n-3**: 本設計書 §5.1 の「`LIMIT_EXCEEDED` 全 20 箇所」を実測 **19 箇所** に訂正 (`test_limit_class_vocabulary.py` の AST スキャンで確定)。

**nit n-4/n-5/n-6 (コード変更なし、設計記録のみ)**:
- n-4: 正規化 (大文字小文字畳み込み・Unicode 正規化) を禁止する契約 `valid_confirmation` の規範は、r2db の句が entity/index/credential_id (すべて ASCII 識別子または16進digest) のみで構成される純 ASCII 文字列であるため、r2db 自身の実装では「正規化により偽陽性一致が起きる」具体的なケースが観測不能 (規範自体は契約の一般原則として有効、r2db はたまたまこの穴の実例を提供しない、という限界の記録)。
- n-5: `delete` の空 `where` に対する digest 定義 (「where 空にも digest は定まる」) は、`bind_mutation` (structured.py:253-254) が `delete`/`update` に対して非空 filter を既に必須としているため、r2db の実行時には**到達不能**な防御的仕様である。契約定義としては一般性のために維持するが (将来他実装や将来の r2db 自身の仕様変更で到達しうる)、現行 r2db では実測できない旨を記録する。
- n-6: `delete` の digest は述語の **リスト** (`list[Predicate]`) の正準化であり、リストの**順序**もハッシュ入力に含まれる (`_canonical_where_json` は各要素内の dict キーのみ `sort_keys=True` でソートし、リスト自体の順序は保持する) -- 同じ述語集合でも順序が異なれば別の digest になる、という仕様上の挙動を意図的なものとして記録する (異なる順序の where を「同じ selection」とみなして digest を畳み込む正規化は行わない、という設計選択)。

**完了条件チェック**: (1) 全件対応済み、(2) レビュア変異 B・C を自分で再注入し赤を実測、scratchpad 経由で復元し diff 一致確認済み、(3) 下記 §5.7 参照、(4) B-1 の実 wire 再現ログは本節の B-1 記載を参照、(5) 本節が該当。

### 5.7 テスト実測 (followup、すべて同期・フォアグラウンド実行)

- root suite (`pytest -q`、リポジトリルート、conformance-tests + r2db-api/tests + MitateDB-api/tests): **1 回目 787 passed / 0 failed / 0 skipped (192.43s)、2 回目 787 passed / 0 failed / 0 skipped (193.82s)**
- conformance-tests 単独: **251 passed / 0 failed / 0 skipped (155.09s)**
- `r2db-api/tests/test_postgres.py` 単独: **181 passed / 0 failed / 0 skipped (22.48s)**
- 新設/更新テストファイル: `r2db-api/tests/test_limit_class_vocabulary.py` (新設)、`test_foundation.py`/`test_postgres.py`/`test_control_plane_service.py`/`test_control_plane_store.py`/`test_control_http.py` (追加テスト)、`conformance-tests/test_c06_destructive_confirmation.py`/`test_c15_bootstrap_reset_lifecycle.py`/`CONDITIONS.md` (陳腐化文言修正)。
