# Q-1 実効化設計 — 宣言と復唱 (destructive confirmation)、契約 1.2.0

- 版数: v1.2 (2026-08-29。v1.1 への WP-1 実装フェーズ独立レビュー (Opus、blocker 1 / major 8 / minor 4 / nit 4、全件実測裏付き) を全反映。v1.1 は v1.0 への WP-0 独立レビュー (blocker 3 / major 7 / minor 10 / nit 3、全件実測裏付き) を全反映し、従属判断7 (契約スキーマ閉鎖ほか) を統合したもの)
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
   - 長さ検算 (r2db 固有の識別子上限 63 — 契約由来でない旨を注記): 最長は drop_index の 12+63+1+63+18+20 = 177 ≤ **256** (R-1 の引き上げ後)。句構成関数はこの帰結を assert しテストで固定
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
