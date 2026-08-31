# Q-1 実効化設計 — 宣言と復唱 (destructive confirmation)、契約 1.2.0

- 版数: v1.6 (2026-08-30。WP-6 (記録整理 — Q-1 実効化の最終 WP。ドキュメントのみ、コード変更なし) を §8 に記録し、Q-1 全体の完了総括と将来課題台帳を新設。suite は WP-5 followup の 814 passed から不変 (文書のみの変更のため))。v1.5 は WP-5 実装 (MitateDB-api の確認内容検証の適合修正 — R-5 全部 + 版数 flip + limits 語彙適合 + C-06 厳格分岐の初実行デバッグ) を §7 に記録)。v1.4 は WP-4 実装 (儀式 CLI `ops.py` の `reset`/`delete-credential` declare-and-echo 化 + runbook/playbook 更新) を §6.1-6.6 に記録し、その独立レビュー (Opus、blocker 0 / major 3 / minor 5 / nit 4、全件実測裏付き) への全対応を §6.7-6.8 に追記したもの (WP-3 followup が §5.6 で v1.3 のまま追記記録したのと同じ前例に倣い、WP-4 時点では版数を据え置いた)。v1.3 は WP-3 実装 (r2db-api の declare-and-echo 実効化 — R-2 全部 + R-3 + limit_class/212 再分類 + 版数 flip 両面 + 旧固定句 27+ 箇所更新 + TRUTHFUL_DETERRENCE 更新) を §4 に記録したもの。v1.2 は v1.1 への WP-1 実装フェーズ独立レビュー (Opus、blocker 1 / major 8 / minor 4 / nit 4、全件実測裏付き) を全反映。v1.1 は v1.0 への WP-0 独立レビュー (blocker 3 / major 7 / minor 10 / nit 3、全件実測裏付き) を全反映し、従属判断7 (契約スキーマ閉鎖ほか) を統合したもの)
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

## 6. WP-4 実装記録 (儀式 CLI declare-and-echo 化、v1.4 追記)

### 6.1 実装内容

- **句構成の共有モジュール**: `r2db_api/structured.py` に `RESET_CONTROL_CREDENTIALS` (定数 -- `reset` の対象は「control_credentials ストア全体」であり、名前による再作成という概念自体が存在せず、帰結クラス (全行失効・新規1本発行) も現在の行数・状態に依存しないため、状態指紋を持たない定数句とした。理由はコメントとして関数のすぐ上に記録) と `delete_credential_confirmation_phrase(credential_id)` (`DELETE_CREDENTIAL <credential_id>` -- `credential_id` はランダム生成・再利用皆無 (`ops._new_credential_id`) であり、`revoke_last_control_credential_confirmation_phrase` と同じ理由でそれ自体が指紋を兼ねる) を追加。両者とも既存の3関数 (`delete_confirmation_phrase`/`drop_entity_confirmation_phrase`/`drop_index_confirmation_phrase`) と同じモジュールに置き、`ops.py` はこれを import して参照する (再実装しない -- `test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases` がオブジェクト同一性で固定)。
- **CLI gate**: `ops.py` に `_require_cli_confirmation` を新設し、`reset`/`delete-credential` の両サブコマンドの**先頭**で呼ぶ (`_control_store()`/`_store()` の構築より前 -- store 未構築のためデータベースへは一切接続しない)。不一致/未指定時は `FoundationError("DESTRUCTIVE_CONFIRMATION_REQUIRED", ..., status=409)` を組み立てその `.problem()` (`type`/`code`/`message`/`request_id`/`details` -- 公開 HTTP 面の problem+json と同形) を1行の JSON として stderr に出力し `SystemExit(2)` する。`main()` の通常の `FoundationError` ハンドラ (`error: CODE: message` + exit 1) は経由しない -- store/監査シンク構築前であり巻き戻すトランザクションが存在しないための意図的な分岐。拒否は state-changing でないため `control_audit` への書き込みも行わない (既存の `_write_control_audit`/MI-3 の規約と整合)。
- **`--confirm`引数**: `reset`/`delete-credential` の argparse サブパーサに `--confirm PHRASE` (default `None`) を追加。`--help` 文言も更新したが、既存テストがアサートする "CCR-14"/"ritual"/"break-glass" の3語はいずれもモジュール冒頭の description 文字列にあり変更していないため green のまま。
- **`revoke-credential` は不変**: Q1-D4/WP-0 MA-1 の裁定どおり対象外。`--confirm` 引数自体を追加していない (存在しないフラグを渡すと argparse の "unrecognized arguments" で失敗する -- `test_cli_revoke_credential_remains_ungated_and_has_no_confirm_flag` で固定)。

### 6.2 宣言の確定文言

一次ソース (`POSTGRES_PROVISIONING_RUNBOOK.md` §12/§13、`CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` step 1、`credential_store.py::delete`/`set_state` の docstring) から導出。設計書 R-4 の目安文言とは reversible_alternative の対象操作名が異なる (§6.4 で報告) が、consequence/recovery の骨子は目安と一致する。

**`reset`**:
- `required_confirmation`: `RESET_CONTROL_CREDENTIALS`
- `consequence`: "Every existing control credential is revoked and exactly one new, must_rotate credential is issued in the same transaction; the in-band control-plane surface (/control/v1) is then usable for nothing beyond GET .../capabilities and self-rotate until that new credential completes its first rotation (POSTGRES_PROVISIONING_RUNBOOK.md §12)."
- `reversible_alternative`: "If the specific problem is only a disabled (not revoked) control credential, or only an uncaptured secret for one that is still enabled and not revoked, `enable-control-credential <credential_id>` or `rotate-control-credential <credential_id>` respectively recovers without revoking anything at all -- narrower than reset, but only available when credential_id is known and that credential is not already revoked (POSTGRES_PROVISIONING_RUNBOOK.md §13). Once a control credential is actually revoked, or none is known/trusted, reset is the only recovery."
- `recovery`: "Reset itself remains available if access is lost again for any reason -- it needs no prior credential to run and is the universal fallback for every one of §13's lockout paths. It is not meant to be re-run routinely after a prior invocation already reported success (CONTROL_PLANE_COMPROMISE_PLAYBOOK.md step 1: run once per incident, not on every retry)."

**`delete-credential`**:
- `required_confirmation`: `DELETE_CREDENTIAL <credential_id>`
- `consequence`: "The credential row is permanently removed; unlike revoke, no row remains afterward at all -- it disappears from list-credentials and there is nothing left to inspect or re-enable by this credential_id."
- `reversible_alternative`: "revoke-credential <credential_id> -- terminal (no un-revoke) but the row itself stays on record and remains listable; it does not, however, clear 0004_deprovision_application.sql's foreign-key guard, which requires the row's removal, not merely its revocation."
- `recovery`: `null` (真に不可逆 -- `delete`/`drop_entity` と同じ理由で捏造しない)

### 6.3 conformance adapter の CLI 呼び出し追随

`r2db-api/conformance/conformance_adapter_r2db_http.py` の grep で、`ops` を subprocess 経由で呼ぶ箇所は `_run_ops_cli` の2呼び出し元 (`_repair_control_actor` と port `reset()`) のみで、いずれも `self._run_ops_cli("reset")` を呼んでいた。両方とも新設の `_run_reset_ops_cli()` (probe→echo の2段呼び出しを内包し、従来の `CompletedProcess` 契約をそのまま返す) に差し替えた。`bootstrap` 呼び出し (`_repair_control_actor` の非-has_any分岐、port `bootstrap()`) は無変更 (bootstrap は gate 対象外)。`_run_reset_ops_cli` は WP-0 MA-1/Q1-D2 の「句のハードコード禁止」を CLI 呼び出し側でも守り、`RESET_CONTROL_CREDENTIALS` が今回の実装では定数であることを知っていても宣言から毎回読み取る (port v1.6 の `_resolve_confirmation`/`resolve_valid_confirmation` と同じ規律)。これは conformance の意味論変更ではなく「CLI 利用者としての追随」であることを確認: `test_c15_bootstrap_reset_lifecycle.py` (15 件) と `test_c13_revocation_terminality.py` を含む `test_c06_destructive_confirmation.py` (計 44 件) が無変更で green。

### 6.4 逸脱・疑義

- **reversible_alternative の対象操作名**: 設計書 R-4 の目安文言は `reset` の reversible_alternative を「個別の revoke-credential・disable 系」としていたが、実装を確認すると CLI の `revoke-credential`/`disable-credential` サブコマンドは application credential 専用 (`_store()` = `PostgresCredentialStore`) であり、control credential には作用しない。control credential 単体を狙う軽量な代替として CLI に実在するのは `enable-control-credential`/`rotate-control-credential` のみ (`POSTGRES_PROVISIONING_RUNBOOK.md` §13 が明記する2つの限定的シナリオ)。真実側に合わせ、reversible_alternative はこの2コマンドを指す文言とし、適用条件 (credential_id が既知かつ未失効の場合のみ) も明記した。
- CLI の gate 評価順序 (§ evaluation_order の「対象存在確認の後」) は、`delete-credential` については字義どおりには実装していない -- 確認ゲートを `_store()` 構築 (= 対象存在/失効前提の確認と同じ関数呼び出し) より完全に前に置いたため、存在しない/未失効の credential_id に対しても不一致な `--confirm` は `NOT_FOUND`/`VALIDATION_FAILED` ではなく `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返す。これは「拒否時に一切 DB へ触れない」という本 WP のテスト要求 (item D) を字義通りに満たすための意図的な選択であり、CLI には元々 HTTP 面のような分離された「対象存在チェック」ステップが存在しない (`store.delete` 自身が存在確認と実行を一体で行う) ため、契約 R-1-5 の評価順序をそのまま移植する対象が無い。既存テスト `test_0004_refuses_to_deprovision_while_a_credential_remains_and_touches_nothing` はこの選択の影響 (正しい `--confirm` を渡さなければ "not yet revoked" という本来の precondition 拒否を観測できない) を受けるため、正しい句を渡すよう更新した (§6.5 参照)。
- `POSTGRES_PROVISIONING_RUNBOOK.md` §9 (0004 の deprovision ガード付近) にも `delete-credential` の実行例があったため、design が明示的に指定した §12/§13 に加えてここも更新した (スコープをわずかに超えるが、更新しなければ読者に旧い1段呼び出しの誤った例を示すことになるため)。

### 6.5 テスト + 変異

- 新設 CLI テスト: `r2db-api/tests/test_control_plane_store.py` に `reset` gate 用5件 (無 --confirm/誤句/決定論/echo成功/3面共有identity)、`r2db-api/tests/test_credential_persistence.py` に `delete-credential` gate 用4件 + `revoke-credential` 非gate確認1件を追加。既存テスト2箇所 (`test_0004_refuses_to_deprovision_while_a_credential_remains_and_touches_nothing` の delete-credential 呼び出し2箇所、`test_control_plane_store.py` の `reset` 呼び出し3箇所) を `--confirm` 付きに更新。
- 変異3本 (`structured.py`/`ops.py` を scratchpad へバックアップ後に注入、実測後に復元し `diff` で完全一致確認):
  - (a) `confirm != phrase` を `not confirm` (存在チェック化) に変異 → `test_cli_reset_wrong_confirm_phrase_declares_and_touches_nothing`/`test_cli_delete_credential_wrong_confirm_phrase_declares_and_touches_nothing` が赤 (末尾に文字を足した誤句が誤って通過)。
  - (b) 拒否後も `SystemExit(2)` を発生させず実行を継続させる変異 → `test_cli_reset_without_confirm_declares_and_touches_nothing` が赤 (returncode が 2 でなく 0 になり、reset が実際に実行されたことを検出)。
  - (c) details から `recovery` キーを欠落させる変異 → `test_cli_reset_without_confirm_declares_and_touches_nothing`/`test_cli_delete_credential_without_confirm_declares_and_touches_nothing` の両方が赤 (`set(details) == 4キー` アサーションが検出)。

### 6.6 テスト実測 (すべて同期・フォアグラウンド実行)

- root suite (`pytest -q`、リポジトリルート、conformance-tests + r2db-api/tests + MitateDB-api/tests): **1 回目 797 passed / 0 failed / 0 skipped (198.20s)、2 回目 797 passed / 0 failed / 0 skipped (191.71s)** (WP-3 の 787 baseline + 本 WP 新設 10 件 = 797。`test_control_plane_store.py` に 6 件 (`reset` gate 5件 + 3面共有 identity 1件)、`test_credential_persistence.py` に 4 件 (`delete-credential` gate 3件 + `revoke-credential` 非gate確認 1件))
- conformance-tests 単独: **251 passed / 0 failed / 0 skipped (156.98s)** -- WP-3 baseline と完全一致 (本 WP は conformance-tests 配下のテストファイルを一切変更していない。儀式経路 (`test_c15_bootstrap_reset_lifecycle.py` 15件・`test_c13_revocation_terminality.py`・`test_c06_destructive_confirmation.py` 計44件) は adapter 追随のみで無変更 green)
- `r2db-api/tests/test_postgres.py` 単独: **181 passed / 0 failed / 0 skipped (28.94s)** -- WP-3 baseline と完全一致 (本 WP はデータ/schema 面に触れていない)
- `test_control_plane_store.py`/`test_credential_persistence.py` の2ファイル単独: **102 passed / 0 failed / 0 skipped (13.6s)**

### 6.7 Opus レビュー往復 (WP-4 followup、blocker 0 / major 3 / minor 5 / nit 4、全件実測裏付き)

WP-4 の独立レビュー (Opus) が発見した項目と、その全対応の記録。以降 "MA-1"/"MA-2"/"MA-3" は本 followup 固有のラベル -- `ops.py` 内の既存コメントにある同名の "MA-3 (round-2 review)"(儀式 advisory lock の理由付け、WP-2 由来)や `_write_control_audit` の "MI-3" note とは別物であり、混同しないこと。

**major MA-1 (`delete-credential` の未検証 credential_id 反射)**: gate **直前** (`_require_cli_confirmation` 呼び出しより前、`_store()` 構築より前 -- DB へは一切触れない) に `_APPLICATION_CREDENTIAL_ID_PATTERN = re.compile(r"^crd_[0-9a-f]{16}$")` (`ops.py`) による書式検証を追加。不一致は `fail("VALIDATION_FAILED", ...)` (既存の `main()` エラー経路、exit 1、DB 接続なしのまま)。これにより契約 `phrase_construction` rule (c) (未検証入力の句反射禁止) と (d) (長さ有界) が CLI の `delete-credential` でも構造的に成立する: `structured.py::delete_credential_confirmation_phrase` の `assert len(phrase) <= _PHRASE_MAX_LENGTH` は、書式検証済み id (常に20文字) しか到達しなくなったため到達可能性という意味では実質不変だが、"到達しうる入力の範囲" という意味で健全化された (前回 WP-4 本体コミット時点ではこの assert は未検証の任意長文字列を理論上受け得た -- 後述の逸脱是正参照)。実測: `test_cli_delete_credential_rejects_malformed_credential_id_before_any_env_var_is_required` (7 パラメータ -- 非16進・大文字・17桁・`ctl_`接頭辞・空文字列など) を新設、全件 green。レビュア変異 (検証自体を `if False:` に無効化) を自分で再注入し 7 件すべて赤を実測 (無効化後は不正な id がそのまま `required_confirmation` に反射される様子も実測ログに残る) -- scratchpad 経由で復元、`diff` で完全一致確認済み。

**逸脱の存在と本修正での解消 (報告漏れの是正)**: WP-4 本体 (§6.1-6.6) の時点では、`delete-credential` の句構成が **未検証の `args.credential_id` をそのまま `delete_credential_confirmation_phrase` に渡していた** -- これは契約 `phrase_construction` rule (c) (「対象名は当該実装の識別子検証を通過したものに限る」) に対する r2db CLI 側の実際の逸脱であり、WP-4 本体の §6.4 逸脱一覧にこの項目を記載すべきだったが記載していなかった (報告漏れ)。データ面/schema 面 (`structured.py` の `delete`/`drop_entity`/`drop_index`) は `validate_identifier` を経由済みの値だけを句に渡すため元々 rule (c) を満たしていたが、CLI の `delete-credential` だけはこの検証ステップを持たず、コマンドライン引数をほぼ生のまま渡していた。実害の有無: 本 WP-4 本体時点でも `--confirm` 側は exact-match 必須のため、任意の credential_id 文字列を渡しても実際に `store.delete` へ到達するには依然として exact-match した `--confirm` を用意する必要があり、悪用可能な穴ではなかった (declare-and-echo の exact-match 性質そのものが実害を防いでいた) -- が、契約の字義には反しており、MA-1 で構造的に解消した。

**major MA-2 (句テストの自己比較)**: `test_cli_reset_*`/`test_cli_delete_credential_*` の宣言内容 assert を、本番関数/定数の再呼び出し (`RESET_CONTROL_CREDENTIALS`/`delete_credential_confirmation_phrase(credential_id)`) との自己比較から、リテラル期待値 (`"RESET_CONTROL_CREDENTIALS"` / `f"DELETE_CREDENTIAL {credential_id}"`) への直接 assert に置換 (`test_control_plane_store.py` 3箇所、`test_credential_persistence.py` 3箇所)。加えて cross-target テスト `test_cli_delete_credential_cross_target_phrase_is_rejected` を新設 -- credential A の宣言句を credential B の `--confirm` に流用すると拒否され、A・B いずれも削除されないことを確認。レビュア変異 M-C (`delete_credential_confirmation_phrase` から `credential_id` を除去し常に `"DELETE_CREDENTIAL"` を返す) を自分で再注入し実測: リテラル期待値を使う5テスト (無 --confirm・誤句・決定論・no-env・cross-target) すべて赤。**同時に、関数 identity テスト (`test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases`) はこの変異下でも green のまま** であることを実測で確認 (同一関数オブジェクトを指しているという事実は変異後も真のまま -- 関数の中身が壊れたことは identity では検出できない)。これは MI-3 の指摘 (下記) を裏付ける実測でもあり、「関数 assert (identity) + リテラル期待値 assert」の両輪がそれぞれ異なる欠陥クラス (誤ったシンボル参照 vs. 正しいシンボルだが誤った実装) を担当することを実証した。scratchpad 経由で復元、`diff` で完全一致確認済み。

**major MA-3 (拒否時「接続すら開かない」の未検証)**: `_run_cli_no_env` ヘルパーを両テストファイルに新設 -- `R2DB_*` 環境変数を一切与えず (`PYTHONPATH` のみ) `reset`/`delete-credential` を起動し、exit 2 + stderr の宣言 JSON を assert、かつ `"R2DB_CONTROL_DSN" not in stderr` (= `_require_env` の到達なし) を assert。`test_cli_reset_without_confirm_refuses_before_any_env_var_is_required`・`test_cli_delete_credential_without_confirm_refuses_before_any_env_var_is_required` を新設、両方 green (`platform`/`_provision_platform` フィクスチャ不要 -- 本物の PostgreSQL に一切触れないため)。レビュア変異 M-A (gate を `_control_store()`/`_store()` 構築の**後**へ移動) を自分で再注入し実測: 両テストとも赤 (`_require_env` の `"R2DB_CONTROL_DSN is required"` という平文エラーが stderr に現れ、JSON 宣言も `R2DB_CONTROL_DSN` 不在の assert も両方失敗)。scratchpad 経由で復元、`diff` で完全一致確認済み。

**minor MI-1 (拒否識別記述の統一)**: `exit 2` 単独ではなく **「exit 2 かつ stderr の JSON 宣言」** が本 R-4 拒否の識別条件であることを明記 -- `ops.py` の module docstring (`--confirm` フラグの概要段落)、`POSTGRES_PROVISIONING_RUNBOOK.md` §9/§12、`CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` step 1 のコメント/地の文を訂正。理由: `argparse` 自身の usage error と、この CLI の他の `_die` 系失敗 (環境変数欠落等) も exit 2 を返すため、exit code 単独では R-4 拒否を一意に識別できない (`_require_cli_confirmation` 自身の docstring は元々この区別を書けていたため訂正不要 -- 逸脱ではなく、他箇所の言い回しを本来の意図に揃える訂正)。

**minor MI-2 (FK guard 帰属の訂正)**: 「`0004_deprovision_application.sql`'s foreign-key guard」という帰属は不正確 -- 実際の外部キー (`ON DELETE RESTRICT`) は `0005_credential_store.sql` の `credentials.application_slug` 列定義にあり、`0004` はその FK 違反を検知して拒否する側 (`assert_no_credentials_for_deprovision` 関数 -- この関数自体も定義は 0005 側)。`ops.py` の `_DELETE_CREDENTIAL_REVERSIBLE_ALTERNATIVE`・`cmd_delete_credential` 冒頭コメント・`POSTGRES_PROVISIONING_RUNBOOK.md` §9 を「0005 の FK、0004 のスクリプトが検知」という正確な帰属に訂正。

**minor MI-3 (定数の identity assert は無保証)**: `test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases` の docstring を訂正 -- `delete_credential_confirmation_phrase is ...` (関数オブジェクト) は再定義/コピーを確実に検出するが、`RESET_CONTROL_CREDENTIALS is ...` (文字列リテラル定数) は CPython の文字列 interning により、`ops.py` が独自に同一テキストのリテラルをハードコードしていても `is` が真になりうる (レビュアが実測: 別々に書いた同一内容のリテラルが同一オブジェクトに intern される)。よって定数側の実効的な回帰網は MA-2 のリテラル期待値テスト群であり、identity assert ではないことを docstring に明記。テスト自体は削除せず維持 (共有の意図を示す文書的価値はある)。

**minor MI-4 (RAISE EXCEPTION 文言の追随)**: `0005_credential_store.sql:164`(`assert_no_credentials_for_deprovision` 内)の `RAISE EXCEPTION` 文言を、`delete-credential` が2段 (`--confirm` なしで宣言取得→復唱) になったことを反映して更新 (`--confirm ...; run it once without --confirm first to see the exact value to pass` を追記)。`POSTGRES_PROVISIONING_RUNBOOK.md` §9 の引用 ERROR ブロックも同文言に同期。**設計記録**: この migration ファイルは `CREATE OR REPLACE FUNCTION` で定義された関数本体の文言のみの変更であり、スキーマ自体(列・制約・インデックス)は無変更。実機で `0005` を適用済みの provisioned database は本 followup 時点で存在しない (このリポジトリの `r2db-api/tests/` は毎回使い捨てのテスト用プラットフォームを都度 `psql -f` で再構築する運用であり、`test_credential_persistence.py`/`test_control_plane_store.py` の実行そのものが実質的な「適用」を都度行っている) ため、既存の実運用データベースに対する追加のロールバック/再適用スクリプトは不要 -- 次にこのファイルを `psql -f` する実行(テストの次回実行含む)から新文言が有効になる。

**minor MI-5 (delete-credential consequence の反実仮想化)**: gate はカレデンシャルの存在確認より前に走るため、「行は必ず削除される」という宣言は、存在しない credential_id に対しては真でない (反実仮想) 主張になり得た。`_DELETE_CREDENTIAL_CONSEQUENCE` を「The credential row, **if it exists**, is permanently removed...」+ 条件付けの理由 (gate が存在確認より前にあること) の注記を追加する文言に訂正。

**nit N-1**: `test_0004_refuses_to_deprovision_while_a_credential_remains_and_touches_nothing` の第1アサーション (`--confirm` 付き delete-credential が「未失効」で拒否される箇所) を `returncode == 1` + `"VALIDATION_FAILED"`/`"Credential is not revoked"` という具体的な理由の固定に締めた (旧: `returncode != 0` + `"revoke" in stderr.lower()` -- gate 拒否 (exit 2) でも `reversible_alternative` 文言に "revoke-credential" が含まれるため偶然 green になりうる曖昧なアサーションだった)。

**nit N-2**: `conformance_adapter_r2db_http.py::_run_reset_ops_cli` の stderr パースを「stderr 全体を1つの JSON としてパース」から「stderr の**最終非空行**を JSON としてパース」に変更 -- 前置の警告行等があっても頑健になる一方、最終行自体が壊れた JSON なら従来どおり fail-loud (例外を捕捉し probe をそのまま返す、フェイク句を捏造しない) という性質は維持。

**nit N-3**: `DEPLOYMENT_RUNBOOK.md:562` の「`ops.py reset` is the single recovery step」を、2段ゲート化と整合する文言 (「a two-step, `--confirm`-gated invocation」+ playbook/runbook への参照) に更新。

**nit N-4**: `structured.py::delete_credential_confirmation_phrase` の docstring に、application credential のミンタが2系統存在すること (`ops._new_credential_id` = CLI `issue-credential`、`control_plane._new_credential_id` = in-band `POST /control/v1/credentials`) を併記 (旧文言は CLI 側のミンタしか言及していなかった)。

**完了条件チェック**: (1) 全件対応済み (上記)。(2) レビュア変異 M-A (MA-3)・M-C (MA-2 -- 「M-D」相当、関数 identity assert では非検出・リテラル期待値 assert でのみ検出という両輪性を実測で確認)・MA-1 独自変異 (検証無効化) をいずれも自分で再注入し赤を実測、scratchpad 経由で復元し `diff` で完全一致確認済み (詳細は各 major 項目内)。(3) 下記実測結果を参照。(4) 本節が該当 (MA-1 実測ログは同項目内、逸脱 (c) の「WP-4 本体時点で実害はなかったが契約の字義には反していた」という判定は上記「逸脱の存在と本修正での解消」に記載)。

### 6.8 テスト実測 (followup、すべて同期・フォアグラウンド実行)

- root suite (`pytest -q`、リポジトリルート): **1 回目 807 passed / 0 failed / 0 skipped (195.82s)、2 回目 807 passed / 0 failed / 0 skipped (198.82s)** (§6.6 の 797 + 本 followup 新設 10 件 = 807 -- `test_control_plane_store.py` +1 (`reset` no-env)、`test_credential_persistence.py` +9 (cross-target 1 + delete-credential no-env 1 + malformed-id 7パラメータ))
- conformance-tests 単独: **251 passed / 0 failed / 0 skipped (156.44s)** -- 無変更 (adapter 内部実装のみの変更であり conformance テストファイル自体は touch していない)
- `r2db-api/tests/test_postgres.py` 単独: **181 passed / 0 failed / 0 skipped (28.76s)** -- 無変更
- 儀式経路 conformance (`test_c15_bootstrap_reset_lifecycle.py`/`test_c13_revocation_terminality.py`/`test_c06_destructive_confirmation.py`): 59 passed (N-2 のパース変更後も green)

## 7. WP-5 実装記録 (MitateDB-api 適合修正、v1.5 追記)

### 7.1 実装内容

- **`ApplicationCell.delete`** (`MitateDB-api/src/mitatedb_api/cell.py`): シグネチャを `delete(self, principal, collection, filters, *, destructive=False, confirm=None)` へ変更 (旧 `confirm=False` の bool 単独引数を廃止)。評価順序を (a) 認可 (`_require_data`) → (b) `destructive`/`confirm` の型検査 (非 bool/非 str は `ValidationError`) → (c) `collection` 識別子検証 → (d) filters の非空検査 → (e) `_where(collection, filters)` (フィルタ識別子検証・演算子検証・**対象存在検査** — `_field_names` 経由。契約 evaluation_order の「target-existence checks」を兼ねる) → (f) 確認検査 (`destructive is not True or confirm != phrase`) → (g) 実行、へ並べ替えた。B-3 (識別子検証を確認検査より前に) と契約 evaluation_order (shape → 認証・認可 → 対象存在 → 確認 → precondition → 実行) を同時に満たす。`ApplicationRuntime.delete` も同型のキーワード引数へ追随。
- **確認句**: `DELETE <collection> @where=<digest16>` (`_delete_confirmation_phrase`/`_canonical_where_json`、`cell.py` 冒頭に新設)。digest はフィルタ列の正準 JSON (各 `Filter` を `field`/`operator`/`value` の key-sorted dict 化、リスト自体の順序は保持 — r2db n-6 と同じ設計選択) の SHA-256 先頭 16 hex。`default=str` は使わない (r2db WP-3 followup m-7 と同じ理由 — `_where` の `_encode_value` が既に非 JSON-native 値を弾くため、収束による取り違えより即時 `TypeError` を選ぶ)。長さ assert (最長 94 文字 ≤ 256) を関数内に固定。
- **状態指紋なし**: r2db の delete 句 (Q1-D10) と異なり、schema_revision 相当の指紋を含めない — §7.3 に裏取りを記録。
- **新設 `DestructiveConfirmationRequired(FoundationError)`** (`errors.py`): 機械可読 `details` 属性 (4 キー: `required_confirmation`/`consequence`/`reversible_alternative`/`recovery`)。データ面には耐久監査が無いため `audited` は載せない (r2db Q1-D6 と同じ判断)。`consequence` = 実データ削除・復元不可の説明、`reversible_alternative`/`recovery` はともに `None` (真実として代替・復旧経路が無い)。
- **`ResourceLimitError` の構造化 details**: `__init__(self, message, *, limit_class)` へ変更 (キーワード必須、デフォルト無し — 呼び出し漏れは `TypeError` で即座に検出される)。9 箇所全てに `limit_class` を付与 (§7.2 参照)。
- **`transact` の except タプル**に `DestructiveConfirmationRequired` を追加 (現状到達しないが穴を残さない、r2db m-8 と同じ予防的対応)。
- **conformance adapter** (`conformance_adapter_mitatedb.py`): `delete()` を faithful pass-through化 (`destructive` を常に配線、`confirmation` は `_resolve_confirmation` 経由で probe→echo。legacy_token=True は 1.2.0 flip 後は到達しない死コードとして維持 — r2db が旧句 "DELETE" を維持したのと同じ流儀)。`_attempt_mutation_outcome` の delete 分岐 (`confirm=True` 直書き) も probe→echo 化。`attempt_batch_with_addresses` の `destructive`/`confirm` 配線を分離 (r2db WP-3 の V2b-wire 修正と同型 — decoupling 自体は独立に正しい修正だが、後述 §7.4 のとおりこれだけでは MitateDB 自身の構造的制約を解決しない)。`_CLASSIFY_ORDER` に `DestructiveConfirmationRequired → DESTRUCTIVE_CONFIRMATION_REQUIRED` を追加。
- **`capabilities()` の flip**: `contract_version` を `"1.2.0"` へ。
- **conformance 側の追随**: `test_c06_destructive_confirmation.py` の `_EXPECTED_STRICT_ADAPTER_NAMES`/`_EXPECTED_BASELINE_ADAPTER_NAMES` を `{"r2db-api", "r2db-api-http", "MitateDB-api"}`/`frozenset()` に更新。陳腐化していたモジュール docstring・`fx` override コメント・V2 の docstring (MitateDB の `delete()` に `destructive` パラメータが無いという記述) を実態に更新。`CONDITIONS.md` C-06 行の「MitateDB は 1.1.0 のまま」という記述も実態 (全 3 adapter が 1.2.0/strict) に更新。
- **MitateDB ローカルテスト**: `test_foundation.py:179` の交絡 (空 filters vs 確認欠落) を解消し、非空 filters + 確認欠落で gate を単独検証する新テスト (`test_delete_without_confirmation_is_gated_not_conflated_with_empty_filters`) と型検査テスト (`test_delete_rejects_non_boolean_destructive_and_non_string_confirm`) を新設。r2db の `test_limit_class_vocabulary.py` を模した静的 AST スキャン (`test_limit_class_vocabulary.py`、MitateDB 版) を新設 — ただし `ResourceLimitError.__init__` が `limit_class` をキーワード必須にしたため「存在漏れ」の検出はコンストラクタ自身が構造的に保証しており、このスキャンは「値が 15 classes のメンバーか」のみを検証する (r2db 版との役割分担の違いとして明記)。

### 7.2 limits 語彙の判断 (fields/filter_terms の対応先・台帳送りの根拠)

調査対象: `config.max_fields` (3 箇所で使用 — `create_collection` のスキーマ定義フィールド数、`_fields`/`read` の射影フィールド数、`_prepare_values`/insert・update・transact-insert の values フィールド数) と `config.max_filter_terms` (`_where` のフィルタ数、1 箇所のみ)。

- **`filter_terms` → `query_complexity` へ改称 (クリーンな 1:1 対応)**: `_where` の唯一の呼び出しで enforce される値がそのまま `query_complexity` の宣言値になる。r2db 自身の `query_complexity` が `len(where) + len(select) + order_by_count` を束ねる「クエリの構造的複雑度」という同じ概念であり、`_where` の filter 数だけを数える MitateDB の実現はその部分集合として真実に対応する。
- **`fields` → 宣言から削除 (改称せず)**: `max_fields` は 3 箇所で異なる意味 (スキーマ定義幅・読み取り射影幅・書き込みペイロード幅) に使われており、そのどれも 15 classes の既存メンバーの宣言値と数値が一致しない (`schema_objects` は別のカウンタ [collection 総数] を持つ、`query_complexity` は `max_filter_terms` の値を持つ)。改称してどちらかの名前を再利用すると、宣言された数値 (`capabilities().limits[class]`) と実際に踏んだ境界値が食い違う、という別の不誠実を生む。よって `fields` キー自体は宣言から外した (r2db の L4 `request_bytes` 宣言ギャップと同型 — enforce されているが discovery 未宣言)。
- **`ResourceLimitError.details.limit_class` (エラー詳細のクラス名) — WP-5 本体時点の暫定判断 (Q1-D11 により不採用、次項参照)**: `max_fields` を使う 3 箇所を最も近い kind-match として `query_complexity` に分類したが、`capabilities().limits.query_complexity` が公開する数値 (`max_filter_terms`) とこれら 3 箇所が実際に踏む数値 (`max_fields`) が食い違ったまま残るという不正確な宣言だった。

#### Q1-D11 (監督裁定、2026-08-30。依頼者が覆せる): max_fields 系 3 箇所を `ValidationError` へ再分類

WP-5 本体の上記判断 (「宣言数値と不一致のまま `query_complexity` にタグ付け」) は不正確な宣言であるとして監督裁定 Q1-D11 により不採用となり、各箇所の実性質を再調査したうえで次のとおり修正した:

- **write-payload 幅 (`_prepare_values`)**: 契約 `Mutation.values.maxProperties: 100` に直接対応する shape 境界。r2db 自身の Q1-D8 (`structured.py` 旧212、"mirrors the contract's own fixed ... shape bound, not a deployment-tunable limits.classes resource") と同一の理路で `ValidationError` (`VALIDATION_FAILED`) へ再分類。
- **schema-field count (`create_collection`)**: r2db の実装を確認したところ、`bind_schema_operation` の `create_entity` 分岐 (`structured.py`) が同じ実世界の操作 (新規 entity の列一覧を 1 回の呼び出しで定義する) を、資源集計に一切参加しない単独の `VALIDATION_FAILED` (`len(raw_fields) > 100`) として扱っている — r2db 自身がこの操作を「資源クラスでなく shape」と判定した実例であり、MitateDB も同型として `ValidationError` へ再分類。
- **read-projection width (`_fields`)**: r2db の `validate_projection` (`structured.py`) を確認したところ、`len(select) > 100` は単独の `VALIDATION_FAILED` であり、`query_complexity` 集計 (`limits.check("query_complexity", len(where) + len(select) + order_by_count)`) とは**別建て**の、それ自体は資源集計に参加しないチェックだった (r2db は select 件数を「shape 境界」と「資源複雑度への寄与」の両方で扱うが、前者は独立した shape チェックとして存在する)。MitateDB の `_fields` は集計の仕組み自体を持たず単独カウントのみであり、r2db の shape 側チェックと同型 — `ValidationError` へ再分類。
- **資源消費境界として残ったもの (再分類しなかった箇所)**: `_where` のフィルタ数チェック (`query_complexity` のまま) — こちらは Q1-D7 時点で `filter_terms`→`query_complexity` の 1:1 改称が既に宣言値と一致しており (`capabilities().limits.query_complexity == config.max_filter_terms`)、監督から明示的に「維持」と指示された。他 3 箇所 (`batch_items` ×2、`result_items`、`schema_objects`、`request_bytes`) はいずれも WP-5 本体時点から宣言値と実施値が一致しており、対象外。
- **結果**: `ResourceLimitError` の emission は 9 → 6 箇所に減少し、残る全箇所で `capabilities().limits[limit_class]` の宣言数値と実際に踏む閾値が完全に一致する (`test_every_resource_limit_error_declared_and_enforced_values_agree` で実測確認)。「新契約クラス候補として台帳へ」という前回の代替案は不要になった — 3 箇所とも既存の shape 概念 (`ValidationError`) で真実に説明できたため、`limits.classes` へ新規クラスを追加する CCR は提起しない。
- **conformance への波及確認**: `grep -rn "LIMIT_EXCEEDED" conformance-tests/*.py` は `test_c14_authority_boundary.py` (r2db 制御面のレート制限、MitateDB 無関係) のみがヒット。`test_c01_scope_binding.py`/`test_c03_structured_injection.py` はいずれも `ResourceLimitError`/`max_fields`/`LIMIT_EXCEEDED` を参照しておらず、この 3 箇所を叩く既存ベクタは無い。実測 (`pytest conformance-tests -k "mitatedb or MitateDB"` 66 passed、`test_c01_scope_binding.py`/`test_c03_structured_injection.py`/`test_c11_document_conformance.py` 計 52 passed) でも退行なしを確認済み。

### 7.3 句に状態指紋が不要である理由 (実装調査による裏取り)

契約 `phrase_construction` rule (b) は「名前で破壊・再作成できる対象」にのみ状態指紋を要求する。MitateDB の `collection` がこれに当たるかをソース調査した:

1. **drop 経路の不在**: `cell.py` 全体を確認 — `ApplicationCell`/`ApplicationDeveloper`/`ControlPlane` のいずれにも `drop_collection`/`drop_entity` に相当するメソッドは存在しない。`capabilities().schema_operations.unsupported` も `drop_entity`/`drop_index` を明示。よって同名での drop→create は構造的に不可能。
2. **既存 collection への schema 変更経路の不在**: `add_field`/`alter_field`/`create_index` もすべて `unsupported` であり、`schema_revision` 相当のカウンタも存在しない (grep 済み、ゼロ件)。よって「同名再作成」だけでなく「その他の schema 変化」の経路も存在しない。
3. **結論**: collection は一度 create されると、そのプロセスの生存期間中は形状が不変であり、delete 句が無効化されるべき「状態変化」自体が発生し得ない。指紋を省略することは見落としではなく、r2db の Q1-D10 (同名 drop→create が可能なため指紋必須) とは異なる、MitateDB 自身の実際の機能に基づく別の真実の答えである。

(補記、P3 WP-1: add_field 解禁により前提が変わり、delete 句に @schema_revision 指紋を追加した。docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md §0 例外節参照)

### 7.4 C-06 厳格分岐の MitateDB 初実行デバッグ (発見一覧)

初回実行 (`pytest conformance-tests -k mitatedb`) で 1 件のみ失敗した (V1/V2/V3/V4/V5/V8 はすべて初回 green — 想定リスクは的中しなかった):

1. **V2b-wire (`test_c06_v2b_wire_destructive_omitted_with_valid_confirmation_denied`) が想定外に赤化 (suite 側の想定漏れ、製品側は正常)**: この vector は `attempt_batch_with_addresses`/`BatchOperation` (port v1.4) 経由で `destructive` を wire レベルで真に省略する。MitateDB の唯一の複数操作ディスパッチャ `ApplicationCell.transact` は `"insert"` 以外の operation type (`update`/`delete`/`upsert`) を**確認検査より前に無条件で** `CapabilityError` (→ `CAPABILITY_UNSUPPORTED`) で拒否する (このコードパス自体は WP-5 以前からの、正直で正しい既存の宣告— capabilities().atomic_mutation が正しく反映)。よって probe (`destructive=True`, 確認なし) が `DESTRUCTIVE_CONFIRMATION_REQUIRED` ではなく `CAPABILITY_UNSUPPORTED` を返し、`resolve_valid_confirmation` が `AssertionError` を送出した。**根本原因**: この vector が「対象操作を確認ゲートまで到達させられる複数操作エントリポイントがどの strict peer にも存在する」という、r2db (単一の `mutate()` が全 mutation type を均一に扱う) では真だが MitateDB では偽の前提を置いていたこと。**対応 (suite 側)**: `test_c06_destructive_confirmation.py` に `_batch_delete_capability_absent` ヘルパーを新設 — 無害な probe (確認なし・存在しない行を狙う where) を実際に `attempt_batch_with_addresses` へ送り、`CAPABILITY_UNSUPPORTED` が返れば「この peer のバッチ経由 delete は構造的に到達不能」と判定 (r2db 系は同じ probe が `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返すため false になり、既存の実アサーションへ進む — 退行なし)。この判定が真の場合、V2b-wire は単一操作 `delete()` 側の V2/V2b テストで既に同じ意味論を検証済みとして状態不変のみ確認し return する — `SurfaceAbsent` は使わない (`transact()` は実際にリクエストを受理して拒否しており、`SurfaceAbsent` の「受理する実エントリポイントが存在しない」という定義には当たらないため)。(補記、P3 WP-1.5: transact は update/delete まで atomic 実行するよう収束し、両解釈とも真になった。docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md R-5 P3-D2 参照)
2. **adapter 自身の decoupling バグ (製品側でなく adapter 側)**: `attempt_batch_with_addresses` は `confirmation` の設定を `if op.destructive:` の内側に置いていた (r2db が WP-3 で既に修正した同型のバグ)。`destructive=False` + `confirmation=VALID_CONFIRMATION` という V2b-wire 自身の入力形は、この結合により `confirm` キー自体が never 設定されないという別の失敗モードを生んでいた。r2db の `_build_mutation_item` と同じ形に decouple した (上記 7.1)。この修正単独では 1. の構造的制約は解決しないが、正しい修正として独立に必要だった。
3. **`_attempt_mutation_outcome` の delete 分岐**: `confirm=True` (旧 bool) を直書きしていた箇所。現行 test suite はここを実際には踏まない (C-12 は delete を意図的に除外、C-17/C-18 の delete 利用はいずれも `row_addressability`/`revision_preconditions` が `unavailable` のため absent 分岐に落ちる) が、シグネチャ変更後は `bool` が `confirm` に非 str として渡り即座に `ValidationError` で壊れる死んだコードだったため、probe→echo 化して修正 (未使用でも穴を残さない、という r2db m-8 と同じ流儀)。
4. **V3/V4 の個別懸念 (発注書の名指し)**: 「別 where の正句」(V3) は where-digest 実装の存在が前提だったが、実装済みのため初回 green。「別 credential で同一句」(V4) も、句が `operation`/`collection`/`filters` のみに依存し requester の credential/role を一切参照しないため初回 green (懸念は的中せず)。
5. **suite 自体のバグ**: 上記 1./2. 以外には見つからなかった。

### 7.5 変異注入結果 (5 本、全数赤を実測ののち scratchpad 経由で復元・diff 一致確認済み)

| # | 変異内容 | 対象 | 赤の実測方法 | 結果 |
|---|---|---|---|---|
| (i) | 全文一致→存在チェック化 (`confirm != phrase` → `not confirm`) | `ApplicationCell.delete` | `conformance-tests/test_c06_destructive_confirmation.py -k v3` | 赤 (`DID NOT RAISE ConformanceDenial` — 正句+接尾辞の変異句が誤って通過) |
| (ii) | where digest 除去 (`_delete_confirmation_phrase` の digest を定数化) | `cell.py` | `test_c06_destructive_confirmation.py -k v3` | 赤 (別 where の正句が同一句に収束し `different_where_phrase != phrase` assertion が失敗) |
| (iii) | details キー1個欠落 (`recovery` を details から除外) | `ApplicationCell.delete` | `test_c06_destructive_confirmation.py -k v1` | 赤 (`_assert_four_declarations` が `recovery` 欠落を検出) |
| (iv) | `destructive` 型検査除去 (`isinstance(destructive, bool)` チェックを削除) | `ApplicationCell.delete` | MitateDB ローカル `test_delete_rejects_non_boolean_destructive_and_non_string_confirm` | 赤 (`destructive="true"` が `ValidationError` ではなく `DestructiveConfirmationRequired` を送出 — `destructive is not True` という等価性検査自体は truthy 文字列を弾き続けるため実行はされないが、`assertRaises(ValidationError)` が誤った例外型を検出) |
| (v) | limit_class を非メンバー化 (`"batch_items"` → `"NOT_A_CLASS"`、`transact` のバッチ上限) | `ApplicationCell.transact` | MitateDB ローカル `test_limit_class_vocabulary.py` (静的 AST スキャン) と `test_foundation.py::test_bounded_inputs_and_explicit_destructive_confirmation` (実応答の behavioral assertion) の両方 | 赤 (両テストとも検出 — 静的スキャンと実応答検査の両輪性を実測で確認、r2db WP-3 followup M-2 と同じ知見) |

各変異は `MitateDB-api/src/mitatedb_api/cell.py` を scratchpad のバックアップコピー (実装完了直後の状態) で復元し、`diff` で完全一致を確認済み (`git checkout` は使用していない)。

### 7.6 テスト実測 (WP-5 本体時点、すべて同期・フォアグラウンド実行)

- root suite (`pytest -q`、リポジトリルート): **3 回連続で 810 passed / 0 failed / 0 skipped** (204.67s、197.37s、205.70s)。806 baseline (WP-4 followup の 807 + WP-6 分の変動なし、との前提から逆算した参考値ではなく実測値) + 本 WP 新設 3 件 (`test_foundation.py` +2、`test_limit_class_vocabulary.py` (MitateDB 版) +1) = 810。**訂正記録**: 初回の完全実行 (フォアグラウンド開始 → 120秒でバックグラウンド遷移) は `809 passed` と報告されたが、その直後の独立な 3 回 (バックグラウンド起動から一貫、出力をファイルへ直接リダイレクト) はいずれも `810 passed` で一致し、`--collect-only` も両時点で 810 件収集を確認 — 遷移時の出力キャプチャの artifact と判断し、810 を正とする (テスト自体の非決定性ではない)。
- conformance-tests 単独: **251 passed / 0 failed / 0 skipped (157.03s)** — 件数は WP-4 baseline と同一 (本 WP は既存テスト関数の書き換え・ヘルパー追加のみで新規テスト関数は追加していない)。
- `r2db-api/tests/test_postgres.py` 単独: **181 passed / 0 failed / 0 skipped (27.07s)** — 無変更 (r2db-api には一切触れていない)。
- `MitateDB-api/tests` 単独: **15 passed (0.02s)** (`test_foundation.py` 14 件 [12 baseline + 2 新設]、`test_limit_class_vocabulary.py` 1 件)。

### 7.7 逸脱・疑義

- ~~limits 語彙の不完全性 (§7.2)~~ Q1-D11 により解消済み (§7.2 参照) — `max_fields` 系 3 箇所を `ValidationError` へ再分類し、残る全 `ResourceLimitError` 箇所で宣言数値=実施数値の対応が真実になった。
- **V2b-wire の suite 側修正 (§7.4-1)**: 設計上は WP-2 の管轄領域 (port/共通 suite) だが、WP-5 の実効化がなければ検出できない不具合だったため、WP-3 が C-13/C-15 を自 WP 内で修正した前例に倣い、本 WP の完了条件の一部として本 WP 内で修正した。
- ~~CONTROL_MAPPING.md SI-09 行の MitateDB 列~~ MA-3 (§7.9) で更新済み。
- **`create_collection` の未使用 `destructive` パラメータ**: `ApplicationCell.create_collection(self, principal, name, fields, destructive=False)` に既存の (WP-5 以前からの) `destructive` 引数があるが、どこからも渡されず、契約上も `create_entity` は destructive_confirmation の対象操作ではないため意味論的に無関係 — 本 WP はこれに触れていない (スコープ外の既存コードであり、削除・変更は本 WP の完了条件に含まれない)。

### 7.8 WP-6 への申し送り

- CONDITIONS.md C-06 行の「基線分岐は現在どの adapter も踏んでいない」という残置宣言そのもの (WP-0 MA-7) は本 WP で行った暫定更新 (§7.1) に加え、WP-6 の正式なチェックリスト項目として改めて確認すること。
- ~~`security/CONTROL_MAPPING.md` SI-09 行の MitateDB 列を...更新すること~~ MA-3 (§7.9) で完了。
- ~~§7.2/§7.7 に記録した limits 語彙の不完全性...を監督判断事項として提起すること~~ Q1-D11 (§7.2) で解決済み。新クラス追加の CCR は不要になった。
- **新規 (§7.9 MA-1)**: `capabilities().atomic_mutation` の `operations` 語彙が「バッチ経由の可否」か「一般的な mutation 語彙の実行可否」かという契約 `capability_status.defined.atomic_mutation` (「Single-entity atomic mutation batches」) 自体の解釈論点は、本 WP の調査で「genuinely ambiguous」と判定し宣言・挙動とも変更しなかった (§7.9 MA-1 参照)。次回この capability に触れる WP、または契約改定の機会に、この論点自体を監督判断として提起すること (`capability_status.defined` への注記追加、または `structured_operations.allowed_mutations` 相当の別語彙の新設を検討)。

### 7.9 独立レビュー往復 (Opus、blocker 0 / major 5 / minor 6 / nit 7、全件実測裏付き)

WP-5 (§7.1-7.8) への独立レビューが発見した項目と、その全対応の記録。

### major

**MA-1 (`atomic_mutation` 申告の解釈論点)**: レビュアは `capabilities().atomic_mutation` が `operations: ["insert","update","delete"]` を申告する一方 `ApplicationCell.transact` が `update`/`delete` を無条件で `CAPABILITY_UNSUPPORTED` 拒否する点 (cell.py の旧コメント自身がこの落差を記していた) を「申告が偽」と指摘した。一次ソースを確認:
- 契約 `capability_status.defined.atomic_mutation` = 「Single-entity atomic mutation batches」— 文言上は「バッチ (複数操作をまとめた atomic 実行)」自体の話に読める。
- r2db-api 自身の宣言 (`"atomic_mutation": {"status": "enabled", "operations": [...4種全部...]}`) はこの論点を判別しない — r2db は単一の `mutate()` が単発でもバッチでも全 4 種を均一に実行するため、「バッチ経由」と「一般的な実行可否」が常に一致し、両解釈のどちらであっても同じ宣言になる。
- `conformance-tests/test_c12_capability_agreement.py::_declared_mutation_operations` は `atomic_mutation.operations` を読み取り、`ConformanceAdapter.attempt_mutation` (港レベルの ABC docstring: 「present one mutation-vocabulary operation ... to the peer exactly as a real client would」、バッチという限定は一切ない) で実際に叩く。MitateDB の `attempt_mutation` は `insert`/`update`/`delete` それぞれを**専用の実メソッド**(`session.insert`/`update`/`delete`、いずれも transact を経由しない、実際に動く経路) で実行する — C-12 は実質「一般的な mutation 語彙の実行可否」を検証している。
- **実験で確認**: (a) 宣言を `operations: ["insert"], unsupported: ["update","delete","upsert"]` (バッチ限定解釈) に変更したところ、`test_declared_mutation_operations_match_observed_behavior[MitateDB-api]` が赤化 (`update` の実行が実際には専用メソッド経由で成功するため、「unsupported」の申告と矛盾)。(b) さらに adapter 側で `update` を `transact()` 経由に付け替えて C-12 を green にすることは技術的に可能だと確認したが (66 passed 実測)、これは「real client がどうこの peer を使うか」を偽る変更である (実際のクライアントは単発 update に transact をラップしない) と判断し不採用。
- **結論**: 現行宣言 (`operations: ["insert","update","delete"], unsupported: ["upsert"]`) は「一般的な mutation 語彙の実行可否」解釈のもとでは真実 (全て実メソッドで動く) であり、この解釈は契約自身の `attempt_mutation` 抽象 (バッチ限定と書いていない) および C-12 の実運用と整合する。「バッチ限定」解釈のもとでは偽 (transact は insert のみ) だが、この解釈を採用するには adapter 側の不誠実な付け替えが必要になり、それ自体が別の不正確な申告を生む。**依頼者裁定 (b) の「解釈が契約上曖昧なら独断せず両解釈と影響を報告」に該当すると判断し、宣言・挙動とも変更しなかった**。cell.py の該当コメントを、この調査の全内容 (両解釈・r2db 比較・C-12 実測・不採用の adapter 変更とその理由) を明記する形に全面書き換えた。契約 `capability_status.defined.atomic_mutation` の文言自体を明確化する CCR を将来提起することを推奨 (§7.8 に追記)。(補記、P3 WP-1.5: transact は update/delete まで atomic 実行するよう収束し、両解釈とも真になった。docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md R-5 P3-D2 参照)

**MA-2 (declared==enforced が片側検証だった)**: `test_every_resource_limit_error_declared_and_enforced_values_agree` を拡張し、残る全 5 クラス (`batch_items`/`result_items`/`query_complexity`/`schema_objects`/`request_bytes`) それぞれに負の対照 (宣言値ちょうどの入力が成功する) を追加。レビュア変異 M-F (query_complexity: `len(filters) > max_filter_terms` → `len(filters) + 1 > max_filter_terms`、過大申告方向に 1 ずらす) と M-F3 (result_items/batch_items: 同じ方向に 5 ずらす) を再注入し、いずれも新設の負の対照が赤を検出することを実測 (§7.9 変異表参照)。scratchpad 経由で復元、diff 完全一致確認済み。

**MA-3 (本コミットが壊した evidence 参照)**: `security/CONTROL_MAPPING.md` SI-09 行の MitateDB 列を、現行のテスト構成 (gate 専用テスト `test_delete_without_confirmation_is_gated_not_conflated_with_empty_filters`・型テスト `test_delete_rejects_non_boolean_destructive_and_non_string_confirm`・句性質テスト・C-06 strict 実行) に合わせて全面更新。`test_bounded_inputs_and_explicit_destructive_confirmation` を `test_batch_and_request_size_limits_and_empty_filters_shape_check` へリネーム (post Q1-D11 の実態 — 破壊的確認は検証しておらず、shape 検査のみであることを名前が正しく示すように)。

**MA-4 (`foundation.json` の限界クラス残置)**: `MitateDB-api/contracts/foundation.json` の `resource_bounds.classes` (`fields`/`filter_terms`/`result_rows` を含む旧語彙) を現行の真実な集合 (`batch_items`/`result_items`/`query_complexity`/`request_bytes`/`schema_objects` — 契約 `limits.classes` の部分集合と厳密一致) へ更新。`destructive_data_operation` の文言も「explicit confirm required」という bool 時代の記述から declare-and-echo の実態へ更新。

**MA-5 (§7.6 実測数値の訂正)**: 下記 §7.10 テスト実測を参照 (root/MitateDB tests/新設件数を本 followup の実際の値に更新)。

### minor

**mi-1 (V2b absence gate の V6 水準化)**: (a) `_batch_delete_capability_absent` を、MA-1 で「atomic_mutation は本 WP では変更しない」と結論したため、その宣言に依存せず独立に補強 — `delete` に加えて `update` も同じバッチ経由で `CAPABILITY_UNSUPPORTED` になることを追加検証し、2つの無関係な operation type が一致して拒否されることでディスパッチャ自体の構造的拒否である (delete/confirmation 固有の偶然の一致ではない) ことを裏付ける。(b) 新設 `test_c06_v2b_wire_vacuity_guard` — registry 全体で「少なくとも1 adapter が V2b-wire の実アサーションを実行した」ことを検証 (C-12 の `test_at_least_one_adapter_exercises_a_positive_control_mutation` と対称)。キャッシュ済み fixture への依存を避けるため、自前で最小構成の Application/entity を都度用意する設計とした。

**mi-2 (受理境界の正直化)**: `_batch_delete_capability_absent` の docstring 「this probe never mutates state anywhere」を「peer 依存の性質であり、過剰削除は呼び出し側の before/after 行数検査が間接的に捕捉するが、要求どおり 0 行を削除しつつ *拒否として振る舞う* (実際には受理して実行し、たまたま0行だった) ケースは、この機構だけでは構造的に検出不能」という正直な受理境界の記述に訂正。ブラックボックス conformance テストの一般的限界として記録 (下記「受理境界」参照)。

**mi-3 (details 属性コメントの陳腐化)**: `conformance_adapter_mitatedb.py::_deny` 直上のコメント (「details 属性は存在しない」) を、WP-5 で `errors.py` に `details` を実装済みであり `getattr(exc, "details", None)` がその配線の**生命線**である (他に details を C06 の denial へ渡す経路が無い) という実態へ全面訂正。

**mi-4 (陳腐化コメント「MitateDB still declares 1.1.0」)**: `test_c06_branch_dispatch_vacuity_guard` 前置コメントを flip 後の実態 (全 3 adapter が 1.2.0/strict、baseline 分岐は現在どの adapter も未踏) へ更新。`grep -rn "1\.1\.0" conformance-tests/` の残存を全数確認 — 歴史的引用 (CCR-13 の契約バージョン言及、`resolve_valid_confirmation`/`contract_version_at_least` 自体の単体テスト入力、`test_schema_check.py` のフィクスチャデータ) のみで、adapter の現在状態を誤って記述する箇所はゼロ。

**mi-5 (`_canonical_where_json` の単体テスト)**: `test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies` を新設 — (1) 各 Filter の key-sorted 化、(2) 外側リストの順序保持 (ソートしない)、(3) `default=str` 不使用 (非 JSON-native 値で `TypeError`) の3性質を実測で固定。レビュア変異 M-B (`default=str` を再追加) を再注入し、性質(3)のアサーションが赤化することを実測、scratchpad 経由で復元・diff 完全一致確認済み。

**mi-6 (型検査防護が peer-local 単独である構造的理由)**: 変異 (iv) (`destructive` 型検査除去) は共通 conformance suite からは検出できず、MitateDB ローカルテストのみが検出する。理由: port (`ConformanceAdapter.delete`) は `destructive: bool` という型付き Python シグネチャを持つため、共通 suite からは「wire 上で destructive が文字列である」という敵対的形状を構成できない (adapter が Python レベルで型を強制する)。この種の型検査は各実装がローカルに保持する責務であり、共通 suite の対象外である — r2db-api WP-3 followup B-1 の「wire 型ベクタは peer-local」という整理と同一の理由づけであり、本 WP でも同じ結論になることを明記する。

### nit

**n-1**: `_delete_confirmation_phrase` の長さ assert 直上コメントを、`assert` が `-O`/`PYTHONOPTIMIZE` 下で完全に除去される事実を踏まえ、「不変条件は識別子長 63 (`validate_identifier` の正規表現) から数学的に証明されており、assert はその証明を実行可能な形で固定する開発時の backstop に過ぎず、`-O` 下での唯一の防御ではない」という正確な記述へ訂正。

**n-2**: `test_foundation.py` 内の存在しないテスト名参照 (`test_delete_gate_*`) を、MA-3 のリネーム作業と同時に実在するテスト名 (`test_delete_without_confirmation_is_gated_not_conflated_with_empty_filters`) へ修正。

**n-3/n-6**: 現状維持 (レビュアの指示どおり、変更なし)。

**n-4/n-5/n-7 (コード変更なし、設計記録のみ)**:
- n-4: bool/int の別句が衝突する懸念は、衝突方向が「安全側」(誤って別の正当な確認が通ってしまう方向ではなく、正しい確認が誤って拒否される、または的外れな拒否になる方向) であることを確認 — `destructive is not True` という同一性検査により、`1`/`1.0` 等の truthy な非-bool は既に `destructive` の型検査 (§7.1) で `ValidationError` として弾かれ、句の同一性判定にすら到達しない。
- n-5: 句に `application_scope` (テナント境界識別子) が含まれない点は、契約 `destructive_confirmation.scope_limit` が明記する「意図しない/悪意ある正規要求への防御はこの機構の責務外」という免責範囲内 — 同一 credential が既に application 境界で認可されている前提のもとでの話であり、境界を跨いだ句の使い回しは SI-01/SI-06 (application scope 分離) が別途担う。
- n-7: `ApplicationCell.create_collection` の未使用 `destructive=False` 引数 (WP-5 以前から存在) は既知の死引数として記録 (§7.7 参照) — 本 WP のスコープ外。

### 変異注入表 (MA-2/mi-5 追加分、全数赤を実測ののち scratchpad 経由で復元・diff 一致確認済み)

| # | 変異内容 | 対象 | 赤の実測方法 | 結果 |
|---|---|---|---|---|
| M-F | query_complexity 過大申告方向 +1 (`len(filters) > max_filter_terms` → `len(filters) + 1 > max_filter_terms`) | `ApplicationCell._where` | `test_every_resource_limit_error_declared_and_enforced_values_agree` (宣言値ちょうどの filters が失敗) | 赤 (負の対照が検出 -- 宣言値 2 の filters が誤って拒否) |
| M-F3 | result_items/batch_items 過大申告方向 +5 (`limit > max_result_rows` → `limit + 5 > max_result_rows`、`len(operations) > max_batch_items` → `len(operations) + 5 > max_batch_items`) | `ApplicationCell.read`/`transact` | 同上 | 赤 (batch_items の負の対照が先に検出 -- 宣言値 2 の operations が誤って拒否) |
| M-B | `_canonical_where_json` に `default=str` を再追加 | `cell.py` | `test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies` | 赤 (性質3のアサーション `assertRaises(TypeError)` が検出 -- 非 JSON-native 値が握りつぶされて文字列化された) |

各変異は `MitateDB-api/src/mitatedb_api/cell.py` を scratchpad のバックアップコピー (本 followup 実装直後の状態) で復元し、`diff` で完全一致を確認済み。

**完了条件チェック**: (1) 全件対応済み (上記)。(2) M-F/M-F3/M-B いずれも再注入し赤を実測、scratchpad 経由で復元・diff 一致確認済み。(3) 下記 §7.10 テスト実測を参照。(4) 本節が該当 (MA-1 の申告訂正の根拠は同項目内、mi-2 の受理境界は同項目内、変異表は上記)。

### 7.10 テスト実測 (Opus レビュー followup、MA-5 訂正値、すべて同期・フォアグラウンド実行)

WP-5 本体 (§7.6) から Q1-D11 (root 812) を経て、本 followup (MA-1〜n-7) 完了時点の最終実測値:

- root suite (`pytest -q`、リポジトリルート): **2 回連続で 814 passed / 0 failed / 0 skipped** (197.91s、217.99s)。Q1-D11 後の 812 + 本 followup 新設 2 件 (`MitateDB-api/tests/test_foundation.py::test_canonical_where_json_key_sorts_each_filter_preserves_list_order_never_stringifies` +1、`conformance-tests/test_c06_destructive_confirmation.py::test_c06_v2b_wire_vacuity_guard` +1) = 814。
- conformance-tests 単独: **252 passed / 0 failed / 0 skipped (156.02s)** — 251 (Q1-D11 後、無変更) + `test_c06_v2b_wire_vacuity_guard` 1 件 = 252。
- `r2db-api/tests/test_postgres.py` 単独: **181 passed / 0 failed / 0 skipped (21.74s)** — 無変更 (r2db-api には一切触れていない)。
- `MitateDB-api/tests` 単独: **18 passed (0.02s)** (`test_foundation.py` 17 件 [Q1-D11 後の 16 + 本 followup 新設 1 件]、`test_limit_class_vocabulary.py` 1 件)。

## 8. Q-1 完了総括と将来課題台帳 (WP-6、v1.6)

WP-6 (記録整理 — Q-1 実効化の最終 WP) を実施した。**本 WP はドキュメントのみで、コード変更・コミットを伴わない** (発注の制約どおり)。裁定 (`spec/CCR_DISPOSITION.md` 従属判断6/7) は WP-1〜WP-5 の単一コミット群で実施済み — 契約 1.2.0 文言化 (WP-1) → C-06 共通 suite + port v1.6 (WP-2) → r2db-api 実効化 (WP-3) → 儀式 CLI declare-and-echo 化 (WP-4) → MitateDB-api 適合修正 (WP-5)。本節はその完了を宣言し、実装中に生まれた将来課題を一本の台帳に集約する。

### 8.1 台帳

**(a) C-06 v2 候補: port `drop_index` op** (出典: §1 R-6 item 3、監督決定 Q1-D5)。port v1.6 が追加した破壊的 schema op は `drop_entity` のみ — `drop_index` は句構成・宣言 details とも r2db 側は実装済み (`drop_index_confirmation_phrase`、SI-09 行のとおり)だが、共通 conformance の C-06 検証ベクタとしてはまだ被覆されていない。次に C-06 へ触れる WP で追加すること。

**(b) `atomic_mutation` の `operations` 語彙の解釈 (バッチ固有 vs 一般語彙 — 契約質問)** (出典: §7.9 MA-1、§7.8)。MitateDB-api の WP-5 独立レビューが、`capabilities().atomic_mutation.operations` の文言 (`capability_status.defined.atomic_mutation` = "Single-entity atomic mutation batches") が「複数操作をまとめたバッチ実行の可否」を指すのか「一般的な mutation 語彙の実行可否」を指すのか、契約自身が判別しない論点であることを発見した。r2db-api はどちらの解釈でも同一の宣言になる (単一の `mutate()` が単発・バッチを均一に扱うため両解釈が収束する) ため、この論点を顕在化させない。MitateDB-api は現行宣言 (`operations: ["insert","update","delete"]`) を「一般語彙」解釈のもとでは真実、「バッチ限定」解釈のもとでは偽と判定し、依頼者裁定の指示 (独断せず両解釈と影響を報告) に従い**解釈も挙動も変更しなかった** (`cell.py` のコメントに調査全内容を記録)。契約 `capability_status.defined.atomic_mutation` の文言自体を明確化する CCR を将来提起することを推奨する。

> **RESOLVED — 追記 (2026-08-31、フェーズ3.5 WP-1、house style — 原文は上記のまま保持)**: 契約 1.3.0 §1-F (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md`、従属判断8) が `capability_status.defined.atomic_mutation` の `operations` を「バッチ実行面が実行する mutation 語彙」であると明記し、この論点を解消した。両 peer とも**フェーズ3の** WP-1.5 収束後は両解釈が一致していたため (レビュー n-1 実測確認)、この明確化は実装影響ゼロの純文言訂正である。

**(c) 受理境界一覧** (ブラックボックス conformance suite が構造的に検出できない、または当実装では観測不能な事項):
- **V2b の「0 行削除+拒否偽装」は原理的に検出不能** (出典: §7.9 mi-2)。`_batch_delete_capability_absent` のような「要求どおり 0 行を削除しつつ拒否として振る舞う」経路 (実際には受理して実行し、たまたま 0 行だったケース) は、前後の行数検査だけでは構造的に区別できない。ブラックボックス conformance テスト一般の限界として記録する。
- **句の正規化禁止 (Unicode 正規化・大小文字畳み込みの禁止) は純 ASCII peer では観測不能** (出典: §5.6 nit n-4)。r2db の句が entity/index/credential_id (すべて ASCII 識別子または16進 digest) のみで構成される純 ASCII 文字列であるため、r2db 自身の実装では「正規化により偽陽性一致が起きる」具体的なケースが観測不能。規範自体は契約の一般原則として有効であり、r2db がたまたまこの穴の実例を提供しないという限界。
- **CLI 定数句の interning による identity assert の無保証** (出典: §6.7 minor MI-3)。`RESET_CONTROL_CREDENTIALS` のような文字列リテラル定数は CPython の文字列 interning により、`ops.py` が独自に同一内容のリテラルをハードコードしていても `is` 比較が偶然真になりうる — 定数側の実効的な回帰網はリテラル期待値テスト (MA-2) であり、identity assert (`test_cli_phrases_share_the_structured_module_with_data_and_control_plane_phrases`) はこの種の欠陥を捕捉しない。関数オブジェクトの identity assert は依然有効 (再定義・コピーの検出に機能する) が、定数の identity assert は文書的価値のみと理解すること。
- **null の真実性は検証不能** (出典: §1 R-1 item 2)。`reversible_alternative`/`recovery` の null は「真実として存在しない」の宣言だが、実在する代替を null と偽る実装をテストで検出することはできない — 真実性は宣言原則 (SI 全体) が負う限界であり、機構では埋められない。

**(d) L4 (r2db `request_bytes` の control discovery 宣言) は Q-1 に吸収されず未実施のまま** (出典: `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §14.4 L4、監督決定 D-2、§13.3)。CCR-14 WP-6 (D-2) は「宣言面の変更は conformance 証拠を伴うコード WP に載せる規律を優先する」として、`GET /control/v1/capabilities` が `request_bytes` リソースクラスを公開していない既知ギャップ (enforce は実在するが discovery が未宣言) を「Q-1 バッチ、契約 1.2.0 検討時」に繰延べる、と申し送っていた。**本 WP-6 の実施範囲を確認した結果、Q-1 (§1-§7 の全 WP) はこの宣言追加を一度も実施していない** — Q-1 は destructive confirmation の文言化・実効化に閉じたスコープであり、`request_bytes` discovery はそのスコープに含まれる作業項目ではなかった。D-2 が見込んだ「次のコード WP」は Q-1 では実現しなかったことをここに正直に記録し、次のコード WP (契約変更を伴わない宣言 flip のみで完結する) へ改めて繰延べる。

> **RESOLVED — 追記 (2026-08-31、フェーズ3.5 WP-4、house style — 原文は上記のまま保持)**: `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §4「L4」がこの繰延べを引き取った。`ControlPlaneLimits` に `request_bytes` を追加しソースを一本化 (`control_http` の `_BYTE_BOUND_LIMITS` が新設フィールドを読む)、宣言は service 層 `unavailable` / HTTP mount 側 `enforced` の二層形 (MitateDB と対称)。`r2db-api/tests/test_control_http.py`・`test_control_plane_service.py` のローカル固定を同一コミット更新。詳細は `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §14.4 の同種追記を参照。

**(e) 契約 additive 候補束 (1.3.0 検討時に一括判断)** (出典: `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §14.4「契約 additive 候補束」、`security/CONTROL_MAPPING.md` R-11 節、本書 §2 R-1 item 「従属判断7 (A)」の封筒閉鎖注記):
1. **`CredentialsResult.must_rotate` の露出** (出典: R2DB_CCR14 §2、§8 m-9)。運用者が儀式未完遂の credential を in-band で見分けたくなった場合の additive フィールド。現行は契約に無いフィールドの独自追加を避け、非露出のまま。
2. **`audit.fields` への対象識別子 (`target_id`) の追加** (出典: R2DB_CCR14 §12.2 MI-6/MI-11、§12.4)。credential lifecycle イベントが対象 credential を識別できず、`CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` の「侵害窓中に発行/失効された credential の列挙」が監査行だけでは完結しない (`list-credentials` との突合で補っているが恒久策ではない)。
3. **`audit` role による制御面読み取り (一覧・capabilities) の許可** (出典: R2DB_CCR14 §1 R-11、§14.4)。「配れる弱い credential」を用意し、root (`role=control`) を配る動機を消す。
4. **per-application 発行凍結 (CLI 限定トグル)** (出典: R2DB_CCR14 §1 R-11、§14.4)。盗まれた control credential からデータ面への最短経路 (任意 app への credential 発行) を app 単位で閉じる。

これら4件はいずれも独立に判断してよいが、契約バージョンの分散 (小さな additive 変更を都度別バージョンで出す) を避けるため、1.3.0 検討時に一括して依頼者へ諮ることを推奨する (CCR-14 側の台帳の推奨方針を継承)。

> **SHIPPED — 追記 (2026-08-31、フェーズ3.5、house style — 原文は上記のまま保持)**: 依頼者直接承認 (2026-08-31) によりフェーズ3.5として着手し、契約 1.3.0 (WP-1) に4件一括で additive 収載、両 peer の制御面実装 (r2db = WP-4、MitateDB = WP-5) で出荷完了した (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md`)。4件それぞれの結末: (1) `must_rotate` 露出 — §1-B、両 peer の `list_credentials` で実値公開。(2) `target_id` — §1-C、両 peer で13番目の `audit.fields` として実装・値設定。(3) `audit` role による読み取り — §1-D、`control_capabilities`/`list_applications`/`list_credentials` の3読み取り endpoint のみ許可、他8件は `FORBIDDEN` fail-closed。in-band 発行は転換せず帯域外儀式限定のまま (B-2 裁定、従属判断1 不変)。(4) per-application 発行凍結 — §1-E、CLI 限定トグル、凍結時 `FORBIDDEN`。詳細な制御/証跡は `security/CONTROL_MAPPING.md` の SI-02/SI-06/SI-07/SI-10/SI-15 各行を参照。

### 8.2 Q-1 の完了宣言

契約 1.2.0 (declare-and-echo destructive confirmation) は文言化・r2db-api 実効化・儀式 CLI 実効化・MitateDB-api 適合修正のすべてが単一コミット規律のもとで完了し、C-06 は3 adapter で厳格分岐が executable として走る。CCR-14 の `revoke_credential` 休止条項 (`spec/CCR_DISPOSITION.md` 従属判断6) は解除された。残る作業は上記台帳の5項目 (a)-(e) のみであり、いずれも新規の安全ギャップではなく、既知の・正直に記録された future-work candidate である。
