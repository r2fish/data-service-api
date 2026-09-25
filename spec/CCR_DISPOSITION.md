# CCR-01〜12 共通契約採否記録

入力は `MitateDB-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md`。判断は実装固有の都合ではなく、共通Capability、Security Invariants v1、両peer適用可能性で行った。

| CCR | 判定 | 理由 | 再検討条件 |
|---|---|---|---|
| CCR-01 | 採用 | versioned structured API、raw SQL/物理名/DB credential非依存は SI-04/05/12 と両peerに共通 | structured APIが表現力不足となる実証があれば、SQL公開以外の拡張を提案する |
| CCR-02 | 採用 | domain-neutralな永続化境界は共通責務を明確化し、business workflow混入を防ぐ | 上位層との責務衝突を示す新Capabilityがあれば境界を再評価 |
| CCR-03 | 採用 | logical catalog、generic entity、CRUD/query、bounded bulkは共通Capabilityとして有用 | peerの表現力不足が確認された場合は構造化拡張を追加 |
| CCR-04 | 採用 | validation、authorization、binding、failure-before-executionを必須化し SI-05/06/15 を満たす | 新操作で不足する検証クラスが発見された場合に契約を拡張 |
| CCR-05 | 採用 | atomicity、rollback、retry/race preconditionは SI-11 の共通意味論 | 分散操作を導入する際、追加の整合性証拠が必要になれば改訂 |
| CCR-06 | 採用 | canonical service-observed auditとsecret/SQL/row-value非開示は SI-10/14 に共通 | 法令やpeer差で保持項目が不足する実証があれば最小項目を再評価 |
| CCR-07 | 採用 | requestからschema proliferationまで有限boundを要求し SI-08 を直接反映 | 実測で不足する資源クラスがあれば追加 |
| CCR-08 | 採用 | scope/roleをserver-boundにし、control-plane証拠とは分離することで SI-00/01/02/03/06 を共通化 | 新しい認証方式が導入される際に同じ非昇格性が証明できるか再検討 |
| CCR-09 | 採用 | structured schema/destructive/job意味論は将来Capabilityとして必要。権限・bound・atomicityを明示する | long-running jobを実装する時点で状態遷移とcancel/expiry条件を追加 |
| CCR-10 | 採用 | revoke/disable伝播boundとfail-closedは SI-13/15 に不可欠 | セッションキャッシュを導入する際、bound証拠が不足なら方式を再検討 |
| CCR-11 | 採用 | Application-bound user/session、role/scope/policyを共通意味論とし、business PersonやUI authorityは除外 | user/identity capability実装時にpeer同等の policy/revoke 証拠を確認 |
| CCR-12 | 採用 | audit emission/query分離とcontrol/audit-only queryは SI-02/10/14 に整合 | business auditを上位層から取り込む場合、security evidenceとの混同がない契約を別途審査 |

CCR-01〜12について、却下・保留となるCCRはない。Google Cloud、SQLite、PostgreSQL、Cloud Run、secret manager等の実装制御は共通契約へ昇格せず、各peerの証拠として扱う。

## 追加契約変更 (2026-08-27, 依頼者承認済み)

以下の2件は新規CCRではなく、既採用の意味論を機械可読化する additive 変更 (`versioning.compatibility` の範囲内)。判断は `docs/design/R2DB_SERVICE_LAYER_ARCHITECTURE.md` D-6 の要判断事項として依頼者へ提示され、承認された。

| 変更 | 実現するCCR | 内容 | 再検討条件 |
|---|---|---|---|
| `audit.sink_failure_policy` の追加 | CCR-06 | security-relevant denial・control-plane変更はaudit sink障害時にfail-closed、通常のdata-operation eventはbounded buffer + 明示的alertとする方針を契約文言化 | 実sinkの運用実績でbounded bufferの許容遅延・alert経路の要件が不足すると判明した場合 |
| `CapabilityDocument.authorization_propagation_bound_ms` の追加 (`required`化含む) | CCR-10 | `lifecycle.propagation_bound` が要求する「有限boundをprofileで公開する」を検証可能にする機械可読フィールドを追加 | 将来sessionキャッシュ等でbound値が0固定でなくなる場合、より詳細な粒度 (credential種別別など) が必要か再評価 |

いずれも新しい共通Capabilityや安全outcomeを追加するものではなく、既存の CCR-06 (canonical audit) / CCR-10 (revoke/disable伝播bound) が既に要求していた意味論を、`spec/data-service-api.v1.json` 上で検証・実装可能な形にしたものである。

## CCR-13〜15 採否記録 (r2db-api 起票)

入力は `r2db-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md` 第4版。CCR-01〜12 と異なり、**起票時点では採否未決である。** いずれも共通契約の骨格に関わるため、実装着手前に判断する。

第1版〜第3版はそれぞれ独立レビューを経て改稿した (第3版へのレビューは体制変更後の Opus による)。訂正の記録は下記および CCR 文書内の訂正欄に保持する。

| CCR | 判定 | 論点 | 残る従属判断 |
|---|---|---|---|
| CCR-13 行の指し示し可能性 | **採用 (2026-08-28)** | `allowed_mutations` に既にある `upsert` は一意性の概念なしには意味を定義できず、r2db-api は実装の選択した意味論で enabled 申告している (統治下の実証)。entity は mutation 能力区分 (読み取り専用 / 追記専用 / 追記・削除 / 可変) を宣言し、update / upsert を支持する entity にのみ addressability を要求。結果は5性質に分解、revision の被参照先は6条項で固定。アドレス再利用は案iii (catalog 宣言) で裁定済み。**`MutationResult` の v1 拡張も行う (依頼者裁定 2026-08-28)** | なし |
| CCR-14 制御プレーン | **採用 (2026-08-28、全体)** | `control` role、`control_credential` scheme、`lifecycle.credential` の意味論は採用済みで endpoint だけが無かった。提供は必須とせず `capability_status` で申告。reset は既存 credential 全失効、revoke は終端、制御面にも SI-08 の資源境界 | in-band 発行 (案A / 案B — CCR 文書が「採否と同時に判断」と定める)。base path `/control/v1` の確認 |
| CCR-15 entity をまたぐ atomicity | **採用 (2026-08-28)** | 形状は `POST /v1/data/mutations` + 新規定義 `ScopedMutationRequest` / `ScopedMutation` (既存 `Mutation` は無変更、per-entity endpoint は body の `entity` を拒否し続ける)。対話的トランザクションは明示的に排除 (再検討条件付き) | `batch_entities` の境界値 (配備 profile) と enforcement layer の申告方法 |

### 判断の軸

優先順位は **堅牢で安全であること、次に最大限の自由があること**。道路にゲートを設けるのではなく、ガードレールを設ける。

- **機構ではなく結果を要求する。** SI-00 が containment を要求して topology を要求しないのと同じ形にする
- **ガードレールは危険のある場所に置く。** 安全要求のスコープは危険の所在から導く。危険の無い区間への無条件の要求はそれ自体がゲートになる
- **能力の提供を強制しない。** 契約は形状と意味論を定め、可用性は `capability_status` で申告させる
- **結果は検証可能な性質に分解する。** 散文のままの結果は適合テストが書けず、「機構は自由」が「何も固定されていない」に転化する

### 各版の誤りの記録

**第1版 (第2版で訂正)**

- `idempotency_key` は行の同一性を前提としない。`MutationRequest` に属するリクエスト単位の項目であり、これに基づく「未宣言 entity では利用不可」提案は追記専用データから冪等性を奪うものだった。撤回
- `upsert` を引用していなかった。契約が意味を与えられない操作を既に許可しているという最強の根拠を落としていた
- `expected_revision` の「実装不能」は言い過ぎ。正確には「相互運用可能な形で有効化できない」
- saga の証拠を誤った要求に紐づけていた。示すのは entity をまたぐ atomicity の欠落であり、CCR-15 として分離した
- 読み取り側 (catalog のキー宣言、query 結果の revision) を欠いていた
- 現行 VPS 実装の教訓を一つしか記録していなかった (実際は三つ)

**第2版 (第3版で訂正)**

- 無条件の普遍的 addressability は、読み取り専用 entity を塞ぐ新しいゲートだった。可変 entity へスコープを絞った
- revision の被参照先を、問題と指摘しながら固定していなかった。5条項で固定した
- SQLite rowid の引用が自らの結果 (不変性) を満たしていなかった (`VACUUM` による振り直し、実測確認済み)
- 「三実装が三様に乖離」は数え方が誤り。統治下の公開面乖離はゼロであり、見込みの問題として論じ直した
- 採用延期の選択肢を断定 (「延期する理由にはならない」) で消していた。三案として依頼者に戻した
- CCR-15 が形状を提案しておらず変更要求になっていなかった

**第3版 (第4版で訂正。独立レビュー Opus の指摘による)**

- 性質4がアドレス再利用 (ABA) を塞いでいなかった。VACUUM 経路だけを塞ぎ、削除後の明示的 insert による再利用 (SQLite `INTEGER PRIMARY KEY` の最大 id 再利用、実測確認済み) を残していた — 自ら訂正した誤りと同じ形の再発。性質5を追加し、明示的再利用の扱いは案i/案ii として依頼者判断へ
- 「行を狙った mutation」が未定義で、追記・削除型 entity を意図せず塞ぎうた。宣言区分で定義し直し、addressability の trigger を update / upsert に限定
- CCR-15 の要求本文が自己矛盾 (「`Mutation` に `entity` 必須」と「追加禁止」の併記)。`ScopedMutation` / `ScopedMutationRequest` の新規定義として解消
- CCR-14 の形状表が未決のはずの案A を既定として書いていた (不確実性の断定化の変種)。共通部と案A差分に書き分けた
- 「両 peer は `CAPABILITY_UNSUPPORTED` で拒否」は事実誤認 (MitateDB-api は受理する面を構造的に持たない)
- ほか: idempotency 保持境界の変更表への固定漏れ、機構列挙の内容ハッシュ (性質4と非両立)、revision の他行非依存条項、サーバ採番識別子の越境推論条項、制御面の資源境界 (SI-08)、control credential 保存条項、rotate 失効時点、reset の既存 credential 失効、三案の非対称な利害記載、CCR-14/15 の変更表欠落 — いずれも第4版で補った

**レビュー側の誤り (同じく記録する)**

- 第2版レビューは「契約側 r2db-api は schema-per-application」と結論したが、事実に反する (`r2db-api/migrations/0003_provision_application.sql` が `CREATE DATABASE` を発行し、`PostgresCell` の `schema` 引数は各 DB 内の `public` を指す)。ただし「CCR が peer の topology を断定すべきでない」という指摘自体は妥当であり、第3版は topology の断定を除いた

### 裁定の記録 (依頼者)

1. **CCR-13/14/15: 三件とも採用** (2026-08-28)。CCR-14 は全体採用 (安全条項のみ先行 / 全体延期は不採用)
2. **CCR-13: `MutationResult` の v1 拡張を行う** (2026-08-28)
3. **CCR-13: アドレス再利用は案iii (再利用の有無を catalog で宣言)** (2026-08-28)。理由: 宣言による見える化が本契約の設計思想 (区分宣言・一意性宣言・`capability_status`) に最も馴染み、想定利用形態では利用設計者が AI エージェントであるため「宣言を読まないクライアント」という案iii の弱点が実質消える。案i (再利用禁止。将来のサロゲート鋳造不能な可変データ — 外部表透過 — を塞ぐ) / 案ii (precondition の領分。晒され方を知る手段が無い) は不採用。案iii強 (再利用宣言 entity への precondition 必須化) は将来の additive 強化として残す

### 従属判断 — すべて裁定済み

1. **CCR-14: in-band 発行は案B** (依頼者が起票側推奨に委任)。control credential の発行は bootstrap / reset の帯域外儀式に限り、公開 HTTP 面での `role=control` 発行要求は `CAPABILITY_UNSUPPORTED`。根拠: 失効を生き延びる永続性の排除が安全第一の軸で優先し、案Aの利便 (運用者追加にサーバ権限不要) は単一運用者の現配備では実質発生しない。**明確化 (裁定時)**: 帯域外に限るのは control credential のみ — application credential (runtime/developer) の発行は in-band に残る。オンボーディングをサーバログインなしに完結することが本 CCR の目的の一部であり、永続性の論証は自己複製する control credential に固有のため。**再検討条件**: 運用者追加が頻繁になり帯域外儀式が実運用の障害と実証された場合、案Aへの移行を additive な契約変更として審査 (endpoint の追加は削除より容易 — 案Bから始めることは後戻りのない選択ではない)
2. **CCR-14: base path は `/control/v1` で確定** (依頼者、旧実装との非重複を条件とし、条件は同日、旧実装の実ソースから全 router を列挙して検証済み) — 旧実装の最上位パス名前空間 (`/`、`/health`、`/ready`、`/v1/tables`、`/v1/schema`、`/v1/meta`、`/admin`、`/admin/api`、`/console`、`/embed`) に `/control` で始まるものは無い。なおこの実測で、引き継ぎ文書の旧パス一覧に無かった `/v1/schema` prefix の共有が判明した (完全一致は無し。段階2の path 振り分けで `/v1/schema/operations` に exact-match が要る — `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §4 に記録)
3. **CCR-15: `batch_entities` の参照 profile 値は 4** (依頼者が起票側推奨に委任)。保守的に始めて実証で緩める (SI-08 のガードレールの流儀)。申告は既存の `limits` / `limit_enforcement` に載せる。**再検討条件**: 実クライアントで不足が実証されれば profile 値の引き上げは additive。**(2026-08-31 追記) 再検討条件が発火し従属判断8で解決** — 参照 profile 不変、配備宣言 10。

4. **CCR-13 実装期の追加従属判断 (2026-08-28、依頼者裁定): 複数 unique key 下の upsert は案B (キー選択フィールド)。** 契約が upsert の存在判定を「宣言された一意性キー」と単数で定めたまま、キーが2つ以上宣言された entity での判定キーが未定義だった (実装フェーズの独立レビューが指摘)。裁定は `Mutation` / `ScopedMutation` への任意フィールド `unique_key` (catalog の `unique_keys[].name` を参照) の追加。意味論: キー1つなら省略可 (そのキーに既定)、複数キーで省略は `VALIDATION_FAILED` (判定が曖昧)、未宣言キー名は `NOT_FOUND`、upsert 以外の operation への付与は `VALIDATION_FAILED`。判断材料: 「upsert の判定キーは1つだが、別系統の一意性をガードレールとして併置する」形 (users の username+email 等) は予見可能に発生し、PostgreSQL 自身の `ON CONFLICT` も同じ理由で conflict 対象の明示を必須にしている。案A (複数キー時は拒否を契約に明記) は不採用 — ただし案A から案B への後日移行も additive であることは確認済みで、選好は「必要が実証されてから足す」より「曖昧さを最初から契約語彙で消す」に置かれた。**版数の扱い**: 契約 1.1.0 は main 未マージ・未リリースのため、本追補は 1.1.0 の公開前訂正として織り込み、版数は据え置く (公開後であれば 1.2.0 となる変更である)。同時に残る open question: `contains` 演算子の意味定義 (リテラル部分一致か) は依然裁定待ち

5. **CCR-13 実装期の追加従属判断 (2026-08-28、依頼者裁定): `contains` の意味定義は案i + 補足案 (`matches` の同時追加)。** `contains` は契約上 operator 名の列挙のみで意味が無く、実装間でワイルドカード解釈が分岐しうる状態だった (実装フェーズの独立レビューが指摘。当時の r2db-api は `%`/`_` を素通し — バインド境界は無事で、意味論のみの問題)。裁定: (a) `contains` を「リテラル部分一致 (値のどの文字もワイルドカードとして解釈しない)」と契約に明記、(b) 同時にパターン一致演算子 `matches` (`%` = 任意列、`_` = 任意1文字、バックスラッシュでエスケープ) を additive 追加する。依頼者の判断理由: **一般的に行える (期待される) ことは最初から普通に行えるべき** — パターン検索の道を「必要が実証されてから」に先送りせず、安全な既定 (リテラル) と明示的なパターン演算子を最初から並置する。**両演算子とも大文字小文字を区別する** (依頼者確認済み。PostgreSQL と SQLite の LIKE の既定差という peer 間分岐を契約側で封鎖する。区別しない比較は将来の別演算子として additive に追加可能)。`matches` を提供しない実装は `CAPABILITY_UNSUPPORTED` で正直に拒否し、別演算子として黙って解釈しない。版数の扱いは従属判断4と同じ (1.1.0 の公開前追補)。実装への反映: r2db-api 両 cell のエスケープ修正と `matches` 実装、MitateDB-api の `contains` エスケープ (定義された以上ワイルドカード素通しは不適合) と `matches` の正直拒否、C-03 value corpus へのワイルドカード・エスケープ文字 probe 追加。**文言確定 (2026-08-28、実装レビューでの発見を受けた厳格読みの明文化)**: 末尾の裸バックスラッシュ (エスケープすべき次の文字が無い) は `VALIDATION_FAILED` — PostgreSQL の LIKE はこの形を格納データ依存で実行時エラーにするため、リテラル扱い・黙認のどちらも peer 間分岐か非決定性を生む。拒否は最も厳格で、緩和は将来 additive に可能

6. **CCR-14 実装期の追加従属判断 (2026-08-29、依頼者裁定): 破壊的確認の有効性定義は「宣言と復唱」方式。** 契約は `destructive`/`confirmation` フィールドを持ちながら「有効な確認とは何か」を定めておらず、CCR-14 の「最後の control credential の失効には明示的確認を要する」条項は解決まで実効化しないと自ら定めていた (MitateDB の確認トークン不検証も同根の既知欠落)。裁定: 確認なしの破壊的要求は `DESTRUCTIVE_CONFIRMATION_REQUIRED` で拒否し、problem+json に正準の確認句 (`required_confirmation` — 操作・対象・帰結クラスから決定論的に構成。再作成可能な対象は状態指紋を含め、古い句の再利用を無効化)、帰結 (`consequence`)、可逆な代替 (`reversible_alternative`)、復旧経路 (`recovery`) を機械可読で宣言する。有効な確認 = `destructive: true` かつ確認句の**全文一致** (存在チェックのみの実装は不適合)。サーバは句を再計算できるため無状態 — トークン保存・失効管理・SI-08 の新資源を持ち込まない。適用範囲は**全破壊的操作の共通定義 (C-06 の共通化)**: CCR-14 の失効確認条項、既存の破壊的 schema 操作、儀式 CLI の確認引数、将来の削除系。**守備範囲の確定 (裁定時の依頼者・監督合意)**: 確認機構が保証するのは「要求の曖昧さの排除」まで — 正規 credential と正規手順を備えた意図しない/悪意の要求は in-band 確認では区別できず、その防御は別層 (設計 R-11: 可逆性・監査不可消去・持続化不能・playbook・抑止宣言) が担う。**版数の扱い**: 契約 1.1.0 は 2026-08-29 に main マージ = 公開済みのため、本定義は**公開後初の additive 契約変更 (1.2.0)** となる。**実施時期**: CCR-14 WP-5 (申告 flip) 完了後の独立作業単位として、契約 1.2.0 文言化 → C-06 共通 suite (3 adapter) → CCR-14 休止条項の実効化 → MitateDB の確認内容検証の適合修正、の順。検討経緯の一次記録は `docs/work-orders/CCR14_DESIGN_PHASE_RECORD_20260829.md` と `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §0.5。**実施済み (2026-08-30)**: 契約 1.2.0 で文言化・実効化完了。休止条項 (CCR-14 の `revoke_credential` 最終 control credential 失効の確認要件) は解除され、C-06 は 3 adapter (`r2db-api`, `r2db-api-http`, `MitateDB-api`) で厳格分岐 (≥1.2.0) が executable として走る。実施記録は `docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` (v1.6)

7. **外部レビュー指摘5 (response schema 非閉鎖 / error details 自由形 / request 側 closed の非対称) への裁定 (2026-08-29、依頼者)。** 新規 CCR ではなく additive 変更として扱い、契約 1.2.0 に同梱する (同梱は依頼者委任のもと監督決定、Q1-D7)。
   - **(A) スキーマ閉鎖**: 開いている応答スキーマ **11 種** (`QueryResult`, `MutationResult`, `CatalogDocument`, `SchemaOperationResult`, `AuditResult`, `ApplicationStateResult`, `ApplicationsResult`, `CredentialIssued`, `CredentialsResult`, `CredentialRotated`, `CredentialStateResult`) + `definitions.EntityDescriptor` + 唯一開いていた request `AuditQueryRequest` に `additionalProperties: false` を追加する。**依頼者案の「12 種」は監督検証で 11 に訂正した — `CapabilityDocument` は 1.1.0 の時点で既に閉鎖済みであり、本裁定の対象ではない (封筒レベルでは変更なし、内部 3 辞書の開放意図の注記のみ追加)。** 封筒本体に加え、独立レビュー(Opus、fix-round M-7)の指摘により4箇所のネスト行 schema も閉鎖する: `ApplicationsResult.applications[]` / `CredentialsResult.credentials[]` / `MutationResult.assigned_addresses[]` / `definitions.EntityDescriptor.unique_keys[]`。意図的に開けたまま残す4箇所 — `CapabilityDocument` 内部の `capabilities`/`limits`/`limit_enforcement` の3辞書と capability entry 値スキーマ(「開いたキー空間」を意図した別機構)、`MutationResult.assigned_addresses[].address`(entity定義のaddress fieldsに依存し固定キー集合を持たない)、`AuditResult.events[]`(`audit.fields`自体が追加的な開放語彙)、`Mutation`/`ScopedMutation.values`(entity定義のフィールド語彙で固定キー集合を持たない) — には触れず、契約自身に各々の開放意図を注記する。同一コミットで、(a)「現に動く実装の実応答が閉鎖後スキーマに適合する」ことの逆向き検証、および (b) 閉鎖した4箇所のネスト行 schema が実際に余剰キーを拒否することを示す positive control を conformance suite に追加する (`conformance-tests/test_c11_response_schema_conformance.py`、既存 C-11 の `assert_valid` 手法の踏襲)。
   - **(B) details 語彙の codify**: `LIMIT_EXCEEDED` の details に必須 `limit_class` (`limits.classes` のメンバー) を定義する。各実装が既に emit している `audited`/`attribution` と、同系の `futility` (監督追加提案、同じ拒否経路で emit 済みの実測に基づく) を、全コード共通の定義済み optional details キーとして codify する。**details 自体は閉じない** (将来の宣言追加の余地を残す。SI-10 の非開示規範は details の内容を制約するものであり、details を自由形のままにしてよいという積極的根拠ではない — この点を契約自身に明記する)。あわせて宣言語彙規則として、`capabilities().limits`/`limit_enforcement` のキーは `limits.classes` のメンバーに限られることを契約に明記する。**注意**: `LIMIT_EXCEEDED.limit_class` の必須化は 1.2.0 の意味論であり、1.1.0 を宣言し続ける実装には遡及しない — 実装の契約宣言バージョンとどの版の意味論に適合を申告したことになるかの一般則を契約自身 (`versioning.version_binding`) に明記し、この一般則が本件を含むすべての版数依存の適合義務を統括する。
   - **(C) OpenAPI 化は不要** (`document_type` で非 OpenAPI であることを既に宣言済み、`docs/security/...` 3e0e678 参照)。1.2.0 に同梱する判断も Q1-D7 に含まれる。
   - **CCR-14 設計 MINOR-3 の明示的転換**: CCR-14 設計文書の「response schema は意図的に `additionalProperties: false` を宣言しない (additive 変更許容)」という決定は、本裁定によって明示的に覆される。転換根拠: 契約 1.1.0 の main マージ (2026-08-27) をもって公開後は additive な契約変更であっても版数を上げる規律がこのリポジトリに確立しており、応答スキーマを開放しておくことの前方互換上の利益は実質的に消滅した一方、閉鎖しておくことの宣言真実性上の利益 (実装が実際に返さないフィールドの存在を暗示しない) は残る。これは見落としの是正ではなく、方針転換として記録する。
   - **実施記録**: 契約 1.2.0 での文言化は WP-1 (本項目) で完了。conformance 側の逆向き検証は `conformance-tests/test_c11_response_schema_conformance.py`(既存 c11 の `assert_valid` 手法の踏襲)で、実被覆は次のとおり(独立レビューでの実測に基づき訂正): **3 adapter**(登録済み全adapter)で検証 — `CatalogDocument` / `EntityDescriptor`(既存 c11 テストが閉鎖後スキーマを自動的に検証)。**2 adapter**(r2db-api の in-process/http、両方とも control plane 実装済み。MitateDB-api は control-plane surface 自体が構造的に不在であることを `SurfaceAbsent` の主張検証〈C-14型の3assertion〉で確認し、検証対象文書自体が存在しないことを確定)で検証 — `ApplicationStateResult` / `CredentialRotated` / `CredentialStateResult`。**r2db-api (http+postgres) のみ**で検証(他adapterはこの経路の実応答を提供しない) — `QueryResult` / `MutationResult` / `SchemaOperationResult` / `ApplicationsResult` / `CredentialIssued` / `CredentialsResult` の6種。**0 adapter**(検証対象の実文書が現状どのpeerにも存在しない、正直な既知ギャップとして記録) — `AuditResult`(全実装が `audit_query` capability を unavailable と申告しており、`POST /v1/audit/query` へ実際にリクエストを提示するadapter経路が存在しないため。実効化は audit sink/query 実装フェーズ〈引き継ぎ資料でいう「フェーズ4」〉以降)と `AuditQueryRequest`(同じ理由で request 側も未検証)。あわせて、閉鎖した4箇所のネスト行 schema (`ApplicationsResult.applications[]`/`CredentialsResult.credentials[]`/`MutationResult.assigned_addresses[]`/`EntityDescriptor.unique_keys[]`) が実際に余剰キーを拒否することを示す positive control を同ファイルに追加した。`limit_class` の実装側 emission (各実装が実際に details へ載せる作業) は、それぞれの契約版数 flip を行う WP (r2db-api WP-3、MitateDB-api WP-5) で行う — 本項目自体は契約の文言化と conformance 側の逆向き検証を担い、実装(src)の挙動は変えない。**(B) 実施完了 (2026-08-30)**: r2db-api は WP-3 で全 `LIMIT_EXCEEDED` emission (実測 19 箇所。当初の暫定記録 20 箇所は WP-3 followup nit n-3 で 19 に訂正) に `limit_class` を付与し、`r2db-api/tests/test_limit_class_vocabulary.py::test_every_limit_exceeded_call_site_declares_a_contract_limit_class` の AST 静的スキャンで全数固定した。MitateDB-api は WP-5 で `ResourceLimitError.__init__` を `limit_class` キーワード必須化 (call site 欠落はコンストラクタ自身が `TypeError` で構造的に検出) したうえで、監督裁定 Q1-D11 (`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §7.2 の Q1-D11 節) により宣言数値と実施数値が一致しない3箇所 (write-payload 幅・schema-field 数・read-projection 幅) を `ValidationError` (shape 境界) へ再分類し、`ResourceLimitError` emission は 9 → 6 箇所に収束、`MitateDB-api/tests/test_limit_class_vocabulary.py::test_every_resource_limit_error_call_site_declares_a_contract_limit_class` の同種 AST スキャンで固定した。両実装とも「宣言した limit_class の数値と実際に踏む閾値が一致する」ことを behavioral test で確認済み (r2db: `test_control_plane_service.py` の6経路、MitateDB: `test_every_resource_limit_error_declared_and_enforced_values_agree`)。**(C) 上記「0 adapter」ギャップの解消 (2026-09-03、フェーズ4。原文は記録として保存)**: `AuditResult` / `AuditQueryRequest` の zero-coverage は閉じた。`AuditQueryRequest` の閉鎖検査は adapter 非依存の positive control (`test_audit_query_request_closed_schema_rejects_an_excess_key`) として WP-1 で、`AuditResult` の逆向き検証 (`test_c11_audit_result_reverse_validates_against_the_closed_schema`) は **登録済み 4 adapter すべての実応答に対して** WP-2(b)/WP-3(b) 以降走っている — 「全実装が `audit_query` capability を unavailable と申告しており」という上記の前提はもはや真ではなく、両 peer が control ホスト上で `enabled` を宣言している。あわせて `audit_requests_per_minute` が両 peer の `limit_class` 語彙全数固定テストに追加された。**追補 (2026-09-24、従属判断 14)**: `schemas.OperationCatalogDocument` と `definitions.OperationCatalogEntry` を `additionalProperties: false` で新設し、本項目 (A) の closed 列挙に加える (設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` §6.6、監督裁定 §15 の 4)。この 2 schema は 1.2.0 で開放から閉鎖されたのではなく、1.9.0 で最初から閉鎖形として新設される — 実施記録は従属判断 14 を参照。

8. **フェーズ3.5 契約 1.3.0 additive 束 (A〜F) への裁定 (2026-08-31、依頼者裁定)。** 新規 CCR ではなく、既存の意味論を明確化・実効化する additive 変更として一括採用する。実施設計は `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` (v1.1、依頼者直接承認は同文書冒頭に記録) §1。契約への反映は WP-1 単一コミットで完了。**版数の扱い**: A〜F はすべて additive (`versioning.compatibility` の範囲内、応答/リクエスト schema の削除・意味変更を伴わない) であり、依頼者指示「一括で進めてください」のとおり単一の 1.3.0 束として出荷する (従属判断4/5のような個別版数据え置きの余地はない — 契約 1.2.0 は既に公開済みのため)。

   - **(A) cross_entity 意味論の明確化** (`endpoints.cross_entity_mutate.semantics`): `batch_entities` は operations[] が参照する distinct entity 名の数を束縛し、同一 entity の複数 operation は許容され、operation 総数は `batch_items` が独立に束縛する (P35-D2)。各 `ScopedMutation` の per-operation 意味論 (mutation_class・upsert `unique_key`・`expected_revision`・destructive confirmation) は per-entity `Mutation` と同一である旨を明示的に相互参照した。**再検討条件**: 特になし — 新たな挙動を導入しない構文上の曖昧性解消のみ。
   - **(B) `CredentialsResult.credentials[].must_rotate`**: 閉鎖 schema に optional boolean を追加。意味 = 「儀式未完遂 (rotate 前) の credential」。application credential 行では省略可 (概念が存在しない)。**再検討条件**: application credential 側に同種の儀式が導入されたら省略規則を再訪。
   - **(C) `audit.fields` へ `target_id` 追加**: 追加とあわせて任意性を契約本文 (`audit.fields_note`) に明記した — `target_id` は「イベントが単一の対象 credential/application を持つときに設定される optional フィールド」であり、全 event への必須列ではない。`audit.fields` は additive 語彙であって固定列集合ではないことも同文で明確化した。`forbidden_fields` とは非衝突 (識別子であり秘密でない、実測確認済み)。**再検討条件**: 複数対象イベントが必要になったら配列化を別途裁定。
   - **(D) `audit` role の実効化 — 読み取り権限の付与のみ**: `control_capabilities` / `list_applications` / `list_credentials` の auth を `"control"` → `"control or audit"` へ改め、`control_plane.issuance` に「audit credential も control と同じく帯域外儀式でのみ発行される」旨を、`control_plane.authority` に「audit credential は上記3読み取り専用 endpoint のみ許可され、他は FORBIDDEN で fail-closed」旨を追記した。`CredentialIssueRequest` / `CredentialIssued` の enum は不変 — in-band 発行は行わない。**従属判断1 は本裁定によって転換されない**: control credential の帯域外限定 (案B) はそのまま保持される。**再検討条件**: audit role の書込系需要が実証されたら in-band 発行と併せ別 additive 裁定 (§7 台帳)。
   - **(E) per-application 発行凍結の意味論注記**: `control_endpoints.issue_credential.semantics` へ「配備は application 単位で発行を凍結でき (out-of-band 操作)、凍結中の application への発行要求は `FORBIDDEN` で拒否される」を追記。凍結トグル自体は CLI 限定で、公開 API に凍結操作の endpoint は追加しない。**再検討条件**: in-band 凍結操作の需要 (§7 台帳)。
   - **(F) `capability_status.defined.atomic_mutation` の文言明確化**: `operations` は「バッチ実行面が実行する mutation 語彙」であることを明記し、`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(b) が記録した「バッチ限定 vs 一般語彙」の解釈論点を解消した。両 peer ともフェーズ3 WP-1.5 収束後は両解釈が一致しているため実装影響ゼロの純明確化。**再検討条件**: 特になし — 設計 §1-F の記録どおり実装影響がないための純文言明確化。

   **従属判断3 の再検討トリガー発火と解決**: 従属判断3「`batch_entities` の参照 profile 値は 4」は「実クライアントで不足が実証されれば profile 値の引き上げは additive」を再検討条件としていた。本フェーズで実クライアント (mitate-application、`docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` v1.2 §6 および v1.3 差分報告 2026-08-31) が 10 を実証要求し、トリガーが発火した。解決は「MitateDB 配備宣言 `batch_entities: 10`」(deployment-declared な limits/limit_enforcement の枠内、実装は WP-2) で満たし、契約参照 profile (`limits.example_profile.batch_entities`) の値 4 は**不変** — profile は非規範の参照例であり、宣言はもともと deployment-declared であるため (P35-D2)。

   **positive control**: additive 束では「旧形状が新契約で不適合」は構成不能 (受理集合は広がるだけ) であるため、逆向き — `must_rotate` を持つ `CredentialsResult` が 1.2.0 schema (現行スキーマから `must_rotate` を除いて再構成) では不適合、1.3.0 で適合になることを `conformance-tests/test_contract.py` に固定した。

   **B-1 措置 (単一 peer コミット規律の明示的例外、テストのみ、P35-D14)**: MitateDB-api の `CONTROL_AUDIT_FIELDS` 契約突合テストは、当時 12 フィールドだった契約 `audit.fields` に対する set 等値で固定されていた。`target_id` 追加 (契約側が 13 フィールド化) がこの等値を直接赤化させるため、WP-1 で「12 コア ⊆ CONTROL_AUDIT_FIELDS ⊆ 契約 fields」の包含形へ緩めた (挙動変更なし・テストのみ)。WP-5 で 13 フィールド等値へ復元する。r2db 側の同型ハードコード (`_CONTROL_AUDIT_COLUMNS`) は契約突合テストが無いため本 WP では赤化せず、WP-4 で列追加と同時に更新する。

9. **フェーズ4 契約 1.4.0 additive 束 (候補 8 件) への裁定 (2026-09-02、依頼者裁定 P4-D4)。** 新規 CCR ではなく、既存の意味論 (CCR-06 canonical audit、CCR-12 audit query 分離、CCR-14 制御プレーン) を明確化・実効化する additive 変更として一括採用する。実施設計は `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (v1.4) §5 P4-D4 (依頼者直接回答は同節冒頭に記録)。契約への反映は WP-1 単一コミットで完了。前例は従属判断8 (1.3.0 の束 A〜F 一括)。

   **(a) 8 件それぞれの内容と根拠**:
   1. `AuditQueryRequest.after` の意味論 = **不透明 cursor**。`(recorded_at, plane, event_id)` を encode し、各 event の `cursor` フィールドで受け渡す。decode 不能・不正な cursor は `VALIDATION_FAILED`。根拠: `event_id` の一意性は各耐久表の PK でしか保証されず、`control_audit`/`application_audit` の UNION 全体では一意でない (MitateDB は `text` 型のため型でも防げない) — `after` を生の `event_id` にすると跨表衝突で cursor が進まなくなる無限ループが起きうる。不透明化はサーバに位置づけの再計算を要求せず、行が既に消えていても位置づけ可能にする。
   2. 順序 = `(recorded_at, plane, event_id)` の全順序。根拠: `plane` を第 2 キーに入れないと、上記の跨表 `event_id` 衝突で全順序が壊れる。
   3. `plane` フィールド (`"control"` | `"application"`) の追加。根拠: `AuditResult.events[]` は従属判断7(A)により既に開放スキーマであるため、フィールド追加はスキーマ変更を要さない純 additive。
   4. 「`event_class` は各実装が宣言する語彙である」旨の文言化。契約に enum は作らない (設計 D-7)。根拠: 契約に固定 enum を作ると、両 peer の既存 class 名と `control_audit` に既に入っている行が「契約不適合な過去の証拠」になり証拠の連続性が切れる。
   5. audit role の `audit_query` 許可を `control_plane.authority` の記述に追記し、既存の「3 endpoint 限定」記述との文言整合を取る。根拠: 従属判断8(D)で `audit` role は `control_capabilities`/`list_applications`/`list_credentials` の3読み取り専用endpointにのみ許可されると裁定済みであり、`audit_query` はその素性 (読み取り専用、audit 権限が意味を持つ) からして同じ許可集合に加わるのが自然な拡張である。
   6. `audit_events` 予約 collection 名の文書化。台帳の既存項目 (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §7 由来、`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11 で RESOLVED)。根拠: 両 MitateDB backend (`backend_sqlite.py` `_RESERVED`、`backend_postgres.py` `_RESERVED_EXACT`) が既に防御的に予約している実装事実を契約に文書化するのみで、新しい挙動を導入しない。
   7. `audit_query` の endpoint 分類の整理 — `control_endpoints` に正本を追加し (`POST /control/v1/audit/query`)、`endpoints.audit_query` は `POST /v1/audit/query` を **1 minor の間の alias** として明示的に残す (削除しない)。根拠: 設計 D-5 が実装側で既に両パスを両建てする構造 (単一 ingress のパス前置詞ルーティングと `/control/v1` 限定エッジポリシーの両方に対応するため) を持つため、契約側の分類がそれに追いつく形。
   8. `audit_requests_per_minute` limit class の新設。根拠: 既存の `control_requests_per_minute` は単一の global window であり、`audit_query` の高頻度ポーリングがその窓を食い潰すと、同じ窓に依存する break-glass 操作 (`revoke_credential` 等) が `LIMIT_EXCEEDED` で締め出されうる (設計 M-8)。専用窓の新設によりこの相互作用が構造的に解消される。実体は WP-2(b)/WP-3(b) で `audit_query` 両パス専用の pre-auth 固定窓として実装・宣言される (監督裁定3)。

   **(b) すべて additive である根拠**: 8 件のいずれも既存キーの削除・意味変更・enum 縮小を伴わない。項目1・2・4は元々未定義だった意味論の確定注記であり、既に受理されていた値集合を狭めない後方互換の明確化である。項目3は`AuditResult.events[]`が従属判断7(A)により既に開放スキーマであるための追加フィールドであり、閉鎖スキーマの変更を要さない。項目5は`audit`roleの許可集合を広げる(狭めない)。項目6は実装が既に行っている防御的予約の文書化のみで新しい拒否経路を導入しない。項目7は`endpoints.audit_query`を削除せず、`control_endpoints.audit_query`という新規キーの追加として実施した — 「分類の移動」は正本の所在が変わる契約上の主張であって、旧キー自体は1 minorの間alias として実在し続けるため、既存キー削除には当たらない。項目8は`limits.classes`への新規メンバー追加であり、既存メンバーを変更しない。`versioning.version_binding`への1.4.0節追記も、既存の1.1.0/1.2.0/1.3.0節をいずれも変更せず末尾に追記する形を取った。
   **義務の条件付き性 (監督裁定8。WP-1 コードレビュー指摘 F-2 反映 — 項目7が無条件(c)と条件付き(5)に分割されたことに伴い、本節の個数表記を実際の`versioning.version_binding`本文 (a)(b)(c) / (1)〜(6) に一致させた)**: 1.4.0 が導入する義務のうち、(1)不透明cursor・(2)全順序・(3)`plane`・(4)宣言される`event_class`語彙・(5)正本パスとaliasパスの両方が実際に応答すること (2パス両建ての実効側)・(6)`audit_requests_per_minute`の**6件**は、**`audit_query`をその実装が`enabled`または`partial`と宣言する場合にのみ**適用される条件付き義務である。(a)`audit_events`予約名の文書化・(b)audit roleの`audit_query`許可(ルート常時登録済みのため`control_plane`さえ提供されていれば`audit_query`自体の可否によらず真)・(c)`audit_query`の正本分類が`control_endpoints`である旨と`endpoints.audit_query`が1 minorの間aliasとして残る旨 (契約文書自体の記述事実であり、`audit_query`の提供可否に依存しない) の**3件**は無条件の1.4.0義務である。この条件付き性は`versioning.version_binding`本文に逐条で明記した — **AUDIT DSN未設定の配備(`audit_query`を`unavailable`と宣言したまま)は1.4.0を宣言できる**。

   **(c) 版数の扱い**: 1.3.0 は既に main へマージ・公開済み (従属判断8実施記録参照) であるため、従属判断4/5のような個別版数据え置きの余地はなく、8件を単一の1.4.0束として出荷する (依頼者裁定P4-D4)。

   **(d) 依頼者裁定の参照**: `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §5 P4-D4 (旧 U-4(a))。判断根拠は同文書§2末尾の依頼者設計原則(1. 今やれることは今のうちにやる、2. シンプルに、3. 制約・制限で回避しない、4. 誇れる成果物であること)。却下した側 (次の束まで繰延べ) とその理由は同節に記録済み — 原則1に反すること、項目7を繰延べると「契約上application endpointなのにcontrolホストにある」という説明しづらい状態が続くこと、項目8を繰延べると監査ポーリングとbreak-glassの相互作用がrunbookの注意書きだけで運用されること (原則3に抵触) の3点。

   **再検討条件**: 項目6は特になし (実装事実の文書化のみ)。項目7の alias は1 minor経過後 (1.5.0以降) に`endpoints.audit_query`を除去するかどうかを別途裁定する。項目8の窓サイズ設計はWP-4のrunbookが監査エージェント数×ポーリング頻度を根拠に定める。その他は本記録(a)に記した根拠が覆らない限り再検討しない。

   **実施記録 (2026-09-03、フェーズ4 完了)**: 契約 1.4.0 は WP-1 (`09233dd`) で公開し、両 peer が挙動出荷と同一コミットで `contract_version` を flip した (r2db = WP-2(b) `a1a1409`、MitateDB = WP-3(b) `a3571dc`) — **1.4.0 の version_binding 義務は全数出荷完了**。8 件のうち実装義務を伴うものはすべて実測で固定されている: 項目1/2 は不透明 keyset cursor と `(recorded_at, plane, event_id)` の全順序 (両 peer の `tests/test_audit_query.py`)、項目3 の `plane` は行の出所テーブルからの導出値であって書き手が指定できる列ではない、項目4 の宣言語彙は AST 走査で実 emit 集合の上位集合であることを両 peer で固定、項目5 の audit role 受理は両 peer の control 面で実測、**項目6 は文書化にとどまらず「entity 識別子を受け取るあらゆる位置で `audit_events` を予約する」実装義務**として確定した (WP-2(b) 受け入れ監査 C。設計 §5.1 P4-D10)、項目7 は両パスを同一ハンドラで両建て、項目8 は既定 60 の専用 pre-auth 窓として両 peer で `enforced` 宣言済み。**受理レンジは契約が定めておらず、実装裁量として peer で異なる** — MitateDB は既存 3 クラスと同じ `[1, 200]` を掛け、r2db は「正の整数」のみを検査して上限を持たない (開示済みの非対称。設計 §11.1 L4-4 / L4-7、`security/CONTROL_MAPPING.md` SI-08 行)。窓サイズ設計は `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15 と `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c に算式として記載し、MitateDB 側には 200 の天井が既定より先に効く条件も書いた。 **【訂正注記 2026-09-04】この段落の受理レンジに関する記述 (MitateDB が `[1, 200]` を掛ける / 200 の天井が既定より先に効く) は、フェーズ5 WP-4 (依頼者裁定 2026-09-03 Q3 = 案 A) により偽になった** — MitateDB の 4 クラス一律の上限は撤廃され、**両 peer とも「正の整数であること」のみを検査する** (エラー文言も `must be a positive integer` で同一)。契約は依然として受理レンジを宣言しておらず本項目の裁定自体は変わらないが、**開示済み非対称として記録した受理レンジの差は解消済み**である (実施設計 `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §3 D-3、実施記録 同 §10.5、台帳 `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 L4-4 / L4-7(iii) は CLOSED)。原文は当時の記述として残す。実施記録の正本は `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (v1.5) §9.4。

10. **フェーズ5 契約 1.5.0 (監査語彙の宣言化 + 無条件義務 (b) の適用範囲) への裁定 (2026-09-03、依頼者裁定 Q1・Q2、束ね方は Q5 = 一括、従属判断 8→9 の前例踏襲)。** 新規 CCR ではなく、既存の意味論 (CCR-06 canonical audit、CCR-12 audit query 分離、CCR-14 制御プレーン、および従属判断 9 項目 4 の event_class 宣言化) を明確化・実効化する additive 変更として一括採用する。実施設計は `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` (v1.3) §3 D-1/D-2 (依頼者直接回答は `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q1/Q2 が記録)。契約への反映は WP-1 単一コミットで完了。前例は従属判断 8 (1.3.0 の束 A〜F 一括) および従属判断 9 (1.4.0 の束 8 件一括)。

    **(a) 各項目の内容と根拠**:
    1. **`capabilities().audit_query` へ `operations` / `target_kinds` の 2 宣言キーを追加する** (D-1)。値はその実装が宣言する語彙であり、契約は enum を持たない (declare-the-hazard、`event_class` の従属判断 9 項目 4 と同じ姿勢)。`audit_query` を `unavailable` 以外で宣言する 1.5.0 以上の実装は、`audit_query` が返しうるすべての event の `operation` / `target_kind` をそれぞれの宣言に含めなければならない。根拠: `operation` / `target_kind` は 1.3.0 以前から `audit.fields` に列挙されている監査フィールドでありながら、その値の語彙は契約にも宣言にも存在しなかった。帰結は共通 conformance suite に直接現れていた — C-09 vector 1 が破壊的操作の耐久行を同定するために `_LIKELY_DESTRUCTIVE_OPERATIONS` / `_LIKELY_DESTRUCTIVE_TARGET_KINDS` という手書きの候補集合を使っており、両 peer が自分の語彙の綴りを変えても共通 suite は気付けなかった。`capabilities().audit_query.operations` / `.target_kinds` という機械可読な宣言先を設けることで、この相関条件を宣言参照へ置換できる。
    2. **1.4.0 無条件義務 (b) の適用範囲を、1.4.0 の義務 (b) 本文そのものへの補筆として一意にする** (D-2)。「Since 1.5.0」の新義務としては置かない — `versioning.version_binding` は「Every obligation introduced under a given version label -- whether enumerated above or added by a later revision of this document still under that same label -- follows this same general rule」と自ら定めており、義務 (b) の適用範囲の明確化はまさにこれに当たる。根拠: 両 peer の data-plane ホストは `control_plane: enabled` を宣言しつつ control credential store を構造的に持たない。義務 (b) を「control surface の control endpoint に掛かる」と読めば両 peer は適合、「capabilities 文書を出すそのホストに掛かる」と読めば不適合であり、契約文言はどちらの読みかを一意に言っていなかった。補筆は前者の読み (control surface の endpoint に掛かる) を契約文言として固定し、data-plane ホストが control/audit credential を `AUTH_INVALID` として拒否してよい (拒否しなければならない、ではない) ことを明示する。**許容形**である — `versioning.control_discovery` の co-hosting 容認 (「convenience, not a requirement」) を狭めない。**`forwarded` の禁止は作らない** — data ホストの alias が control surface へ転送する実装は 1.4.0 条件付き義務 (5) を分離配備で満たす自然な手段でありうるため、禁止すればその形の 1.4.0 実装が遡って非適合になる。

    **(b) すべて additive である根拠**: 2 件のいずれも既存キーの削除・意味変更・enum 縮小を伴わない。項目 1 は追加キー (`operations`/`target_kinds`) であり、既存の `event_classes` キーや `audit.fields` の列挙を狭めない。項目 2 は既存 1.4.0 義務 (b) の**適用範囲の明確化**であり、`versioning.control_discovery` の co-hosting 容認を狭めない (義務形にすれば既に許されていた配備を禁止することになり additive でなくなるため、意図的に許容形を選んだ)。**項目 2 の additive 根拠には実測を添える**: 補筆の第 1 文は受理対象に「control ホスト上の alias」を明示するため、文言上は義務 (b) の受理経路が 1 つ増える (現行の (b) は `audit_query` control endpoint しか名指ししていない)。**両 peer とも control ホストで alias を同一ハンドラへ載せている** — `r2db-api/src/r2db_api/control_http.py:398-399` と `MitateDB-api/src/mitatedb_api/control_http.py:391-392` がいずれも `/control/v1/audit/query` と `/v1/audit/query` を同じ `post_audit_query` へルーティングしている (実測、2026-09-03)。したがって**既存 1.4.0 peer の適合は変わらない** — 補筆が明示する受理経路は、両 peer が現に同一ハンドラで既に提供している経路と一致する。

    **義務の条件付き性 (独立した太字段落、従属判断 9 の house style を踏襲)**: **項目 1 は条件付き** — `audit_query` を `unavailable` 以外で宣言する 1.5.0 以上の実装にのみ適用される (1.4.0 条件付き義務 (1)〜(6) と同じ条件付き性)。`audit_query` が `unavailable` の実装 (監査データストアが構成されていない配備) は 1.5.0 を宣言したまま本義務を負わない。**項目 2 は無条件** — 1.4.0 の義務 (b) 自身が無条件であり (`control_plane` が `unavailable` でない限り適用される)、その適用範囲の明確化も無条件である。この 1 条件付き・1 無条件の分割は `version_binding` 本文の 1.5.0 段落 (項目 1 のみを条件付き義務として逐条列挙) と 1.4.0 の義務 (b) 本文への直接補筆 (項目 2、無条件のまま) という配置に 1 対 1 で対応する。

    **(c) 版数の扱い**: 1.4.0 は既に main へマージ・公開済み (従属判断 9 実施記録参照) であるため、従属判断 4/5 のような個別版数据え置きの余地はなく、2 件を単一の 1.5.0 束として出荷する (依頼者裁定、Q5 = 一括)。

    **(d) 依頼者裁定の参照**: `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q1/Q2 (2026-09-03、依頼者裁定)。判断根拠は同節が記録する監督推奨 (案A) をそのまま踏襲。**却下した側**:
    - **項目 1 (Q1) について**: 共通語彙への統一 (`entity` に寄せる等) — 両 peer の既存 `control_audit` / `application_audit` 行と出荷済み語彙を破り、D-7 (各 peer が宣言する) と衝突するため不採用。現状維持 (手書き候補集合のまま) — 検出不能がそのまま残り、設計原則 1 (先送りしない) に反するため不採用。
    - **項目 2 (Q2) について**: 読み 2 を採る (data ホストが control credential を受理する) — data-plane プロセスに control credential store を持たせることになり、SI-00/SI-02 の分離と正面から衝突するため不採用。peer-local テストだけを足す — 契約上の義務の適用範囲という共通の論点に対して共通テストが無い状態が残るため不採用。
    - **Q4 (`visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合) は本束に入らない** — 独立の設計フェーズとして残る (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4 の監督推奨どおり)。

    **再検討条件**: 項目 1 は特になし — 宣言語彙の追加キーであり、既存語彙・既存証拠に影響しない。項目 2 は特になし — 適用範囲の明確化であり、依頼者が別途裁定しない限り再検討しない。

    **実施記録 (契約公開、WP-1)**: 契約 1.5.0 は `docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md` (v1.1) WP-1 で公開する。**この WP は両 peer の `contract_version` を動かさない** — 各 peer の flip はその peer が 1.5.0 の挙動 (宣言 2 キー + 走査器 + D/N) を出荷する WP (WP-2/WP-3) の同一コミットに落ちる。共通 suite の全体 vacuity guard (`test_c09_every_control_surface_adapter_declares_1_5_0`) は WP-1 で `xfail(strict=True)` 登録され、最後の flip WP と同一コミットで外れる (D-4、1.4.0 の全体 guard が WP-1→WP-3(b) で辿った経路と同型)。

11. **フェーズ6 契約 1.6.0 (credential の完全 bearer 化 + surface 発見 + 型付き catalog) への裁定 (2026-09-04、依頼者裁定、承認「進めてください」)。** 新規 CCR ではなく、既存の意味論 (CCR-01 structured API/非 SQL 公開、CCR-08 server-bound scope、CCR-13 行の指し示し可能性、CCR-14 制御プレーン) を明確化・実効化する additive 変更として一括採用する。実施設計は `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` (v1.4) §3 D-1/D-2/D-3/D-3(vii)。契約への反映は WP-1 単一コミットで完了する。前例は従属判断 8 (1.3.0 の束 A〜F 一括)・従属判断 9 (1.4.0 の束 8 件一括)・従属判断 10 (1.5.0 の束 2 件一括)。

    **(a) 各項目の内容と根拠**:
    1. **`CredentialIssued.secret` および rotate 応答の `secret` は、その credential が属する surface の完全な bearer token であると明文化する** (D-1)。クライアントはそれを合成・分解・派生してはならず、`credential_id` は常に別フィールドとして返る。根拠: 契約はこれまで credential の wire 表現に構造上の意味を与えておらず、r2db は secret を単独の bearer として扱う一方、MitateDB は `<credential_id>.<secret>` の合成形を返してきた。共通 conformance suite はこの非互換を adapter 側の合成 (bearer を組み立ててから提示する) で吸収しており、検出できていなかった。secret を完全な bearer と明文化することで、両 peer とも「クライアントが受け取った文字列をそのまま提示できる」形 (locator 付き token) へ揃え、adapter の合成をなくせる (実装は WP-2/WP-3)。
    2. **`CapabilityDocument` に任意キー `surfaces` を追加し、`data`/`control` それぞれの絶対 base URL を配備者が宣言する** (D-2)。data 文書と control 文書は同じ `surfaces` を返し、同居判定は origin 比較 (scheme + host + port) で行う。`control_plane` が `unavailable` の配備は `surfaces.control` を省略する。根拠: 契約は共通仕様 + base URL + API key だけで peer 非依存に利用できることを目指すが、control surface の所在をクライアントが発見する手段が無く、`CapabilityDocument` にも所在キーが無かった。`surfaces` はこの欠落を埋める宣言キーであり、値は配備者の申告 (declare-the-hazard) であって契約が導出や検証を行うものではない。
    3. **型語彙に 7 語目 `json` (any JSON value) を追加し、型を宣言せずに作られた field の型は `json` であると契約が定める。`definitions.EntityDescriptor.field_types` (条件付き義務) と `schemas.SchemaOperationRequest.field_types` (任意キー、要求してはならない) を追加する** (D-3)。不正 3 ケース (`fields` に無い名前・語彙外の値・`fields` を伴わない `field_types`) は `VALIDATION_FAILED`。catalog は schema operations で定義できる事実のみを返し、null 可否・既定値・必須性は宣言しない。根拠: catalog は型を返さず、MitateDB は catalog そのものが `unavailable` のままだった。r2db の型無し列は既に JSONB (any JSON value) であり、`json` はその実在の既定を正直に名付けたものである。`unknown` のような非型のプレースホルダーではなく、クライアントが「そこに何を書けるか」を判断できる実在の型を採る。
    4. **`structured_operations.upsert` の一文へ `row_addressability` の限定を同ラベルで補筆する** (D-3 (vii))。前半 (宣言された一意性キーが無い entity での upsert 拒否) は逐語で残し、後半 (mutable class を宣言しない entity での upsert/update 拒否) にだけ「`row_addressability` が (`unavailable` 以外で) 提供されている限り」という限定を足す。根拠: `mutation_classes.rule` は「`row_addressability` が enabled のとき、全 entity が mutation class を宣言する」と定める一方、`upsert` の一文はこの前提を持たずに「mutable class を宣言しない entity への update/upsert を拒否する」と読める形になっていた。`row_addressability: unavailable` の実装 (mutation class の宣言そのものが存在しない配備) に対しては、この一文が `atomic_mutation` capability が宣言する mutation を意図せず塞ぐ読みが立ちうる。1.6.0 段落へは置かない — フェーズ5 従属判断 10 項目 2 (1.4.0 義務 (b) 本文への直接補筆) と同じ「同ラベル補筆」の形を踏襲する。

    **(b) すべて additive である根拠**: 4 件のいずれも既存キーの削除・意味変更・enum 縮小を伴わない。1.5.0 との再帰比較で確認した内容は次のとおり — 削除されたキー 0、型変更 0、enum・required・additionalProperties の退行 0、enum は `SchemaOperationRequest.field_type` への `json` の追加 1 件のみ。項目 1 は契約に新しいキーを足さず、既存 `secret` の意味を明文化するだけである — 1.5.0 以前の実装は「不透明な文字列を返す」と読んでおり、その読みは変わらない。項目 2 は `CapabilityDocument` (`additionalProperties: false` の閉じた封筒) へ任意プロパティを 1 つ足すものであり、`required` は変えていない。既存の 1.5.0 文書は依然としてこの schema に適合する。項目 3 は `EntityDescriptor` と `SchemaOperationRequest` の双方に任意プロパティ `field_types` を 1 つずつ足し、`fields` の型 (string 配列) は変えず、`field_types` を要求もしない — したがって 1.5.0 で有効なリクエストは 1.6.0 実装でもそのまま有効であり、`versioning.compatibility` が言う semantic change に当たらない。`field_type` の enum への `json` の追加は受理域の拡大であって狭化ではない。項目 4 は `row_addressability` を提供する実装 (`enabled` / `partial`) に対しては現状と完全に同義であり、義務は 1 つも減らない — `row_addressability: unavailable` の実装に対して「mutation_class を宣言していないことを理由に update を禁じる」読みを閉じるだけである。**MitateDB の挙動変更 3 件 (型無し field の既定 `text` → `json`、`json`/`object`/`array` の読み出し表現を JSON 値へ復元、宣言 `boolean` の wire 表現を 0/1 → JSON boolean) は契約の additive 性を損なわない** — いずれも MitateDB 自身の実装 (WP-3) の是正であり、契約はこれらの表現形式を 1.5.0 以前から定めていない。(α) は受理域が広がるだけの変更 (文字列は引き続き書ける)、(β)(γ) は契約が定める "any JSON value" / 宣言型との一致へ実挙動を近づける是正であって、契約側の義務を新設するものではない。これらは 1.6.0 を宣言する MitateDB のコミット (WP-3) と同一コミットに落ち、契約自体は WP-1 の時点でどちらの peer の宣言も動かさない。

    **義務の条件付き性 (独立した太字段落、従属判断 9・10 の house style を踏襲)**: **項目 1 (D-1) と項目 2 (D-2) は無条件義務**である — 1.6.0 を宣言するだけで簡単に掛かり、いずれの capability の status にも依存しない。そのうち control surface に関わる部分 (項目 1 の control 側 secret、項目 2 の `surfaces.control`) は「control surface が提供されている限り (`control_plane` が `unavailable` 以外、subordinate rulings 8・9 と同じ前提)」という前提を句として持つ (契約既存の 1.4.0 義務 (b) と同じ分類)。**条件付きなのは項目 3 (D-3) だけ**であり、`application_catalog` を `unavailable` 以外で宣言する実装にのみ `EntityDescriptor.field_types` の義務が、`schema_operations` を `unavailable` 以外で宣言する実装にのみ `field_types`/`field_type` 受理の義務が、それぞれ掛かる。**項目 4 (D-3 (vii)) は 1.6.0 段落へ置かない同ラベル補筆であるため、この分類の外である** — `structured_operations.upsert` の本文そのものへの補筆であり、`versioning.version_binding` の 1.6.0 段落が列挙する義務の一つではない。この分割は `version_binding` 本文の 1.6.0 段落 (無条件義務 (a)(b) と条件付き義務 (1)(2) の列挙) および `upsert` 本文への直接補筆 (項目 4、分類外) という配置に 1 対 1 で対応する。

    **(c) 版数の扱い**: 1.5.0 は既に main へマージ・公開済み (従属判断 10 実施記録参照) であるため、従属判断 4/5 のような個別版数据え置きの余地はなく、4 件を単一の 1.6.0 束として出荷する (依頼者裁定、承認「進めてください」)。

    **(d) 依頼者裁定の参照**: `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §3 D-1〜D-3・D-3(vii)、§4 (却下案)。判断根拠は同文書が記録する監督推奨をそのまま踏襲する。**却下した側**:
    - **項目 1 (Q1) について**: MitateDB のみ合成返却し r2db は現状維持 (wire 形式の peer 非対称が残るため不採用) / MitateDB を digest 索引へ揃える (帰属能力と rotate 後の locator 安定性を失う、弱い側へ揃える選択のため不採用) / 契約に `<id>.<secret>` の内部構造を明記する (credential の不透明性を失い契約が実装の内部構造に縛られるため不採用) / 二形式受理の互換シムを置く (常設化の危険があり目先の回避になるため不採用)。
    - **項目 2 (Q2) について**: `control_base_url` 単独キー (片方向であり declare-and-echo が成立しないため不採用) / `.well-known` 文書 (契約外の新しい発見経路を作るため不採用) / `capabilities.control_plane` の value 内に URL を置く (capability の status と配備トポロジを混ぜるため不採用)。
    - **項目 3 (Q3) について**: r2db のみ型付きとし MitateDB は `unavailable` のまま (発見性の peer 非対称が残るため不採用) / null 可否・既定値も宣言する (契約の schema operations がそれらを定義していないため根拠を持たない宣言になり不採用) / 新 endpoint `/v1/schema` を作る (catalog と二重化するため不採用) / `unknown` を型語彙に足す (型ではなくクライアントの判断材料にならないため不採用) / 型無し field を作れなくする (`field_types` を必須化する。1.5.0 で有効なリクエストを拒否する semantic change になるため不採用)。
    - **項目 4 (D-3 (vii)) について**: `mutation_classes.rule` 側の語法 (`Where row_addressability is enabled`) を変更する案は不採用 — 補筆の対象は `upsert` 節の 1 文に限定し、`rule` 側は変えない (射程の限定、L6-10)。

    **項目ごとの再検討条件**: 項目 1 は特になし — secret の意味明文化であり、既存の受理範囲を変えない。項目 2 は特になし — 任意キーの追加であり、`required` を変えない。項目 3 は特になし — 任意プロパティの追加と enum への追加のみであり、既存語彙・既存リクエストを狭めない。項目 4 は特になし — `row_addressability` を提供する実装への義務を 1 つも減らさない同ラベル補筆である。

    **実施記録 (契約公開、WP-1)**: 契約 1.6.0 は `docs/work-orders/WORK_ORDER_PHASE6_CONTRACT_160_V1.md` (v1.2) WP-1 で公開する。**この WP は両 peer の `contract_version` を動かさない** — 各 peer の flip はその peer が 1.6.0 の挙動 (locator 形 credential / `surfaces` / `field_types` / MitateDB の `application_catalog` flip) を出荷する WP (WP-2/WP-3) の同一コミットに落ちる。共通 suite の全体 vacuity guard (`…_every_adapter_declares_1_6_0`) は WP-1 で `xfail(strict=True)` 登録され、最後の flip WP (WP-3) と同一コミットで外れる (D-5、1.5.0 の全体 guard が WP-1→WP-3(b) で辿った経路と同型)。

12. **フェーズ9 契約 1.7.0 (「宣言と検証」— 制約宣言 (`enum`/`nullable`) と `alter_field`、検証エラーの固定 details 語彙、`dry_run` と無状態 `plan`、`idempotency` の実装と契約追記、request budget、成功応答の `request_id`、派生の操作カタログ、`R-10 (B)` 接頭辞剥離) への裁定 (2026-09-07、依頼者裁定、委任「判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。」)。** 新規 CCR ではなく、既存の意味論 (CCR-01 structured API/非 SQL 公開、CCR-04 検証必須化、CCR-05 atomicity/rollback/retry、CCR-07 有限 bound) を明確化・実効化する additive 変更として一括採用する。実施設計は `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` (v1.4) §3 D-1〜D-9。契約への反映は WP-1 単一コミットで完了する。前例は従属判断 9 (1.4.0 の束 8 件一括)・従属判断 10 (1.5.0 の束 2 件一括)・従属判断 11 (1.6.0 の束 4 件一括)。

    **(a) 本文 — 1.7.0 が足す 7 項目、および契約文書のみの変更 3 種**:
    1. **R-2 制約宣言 (`enum`/`nullable`) と `alter_field` の新設** (D-2)。`SchemaOperationRequest.field_constraints`/`enum`/`nullable`、`definitions.EntityDescriptor.field_constraints` (総計報告)、独立節 `structured_operations.alter_field` を追加する。強制点は書き込み経路 (insert/update/upsert) にのみ効き、query predicate は検査しない。既存行が新宣言に反する `alter_field` は同一トランザクション内で全件検証し `CONFLICT` で rollback する。新設 capability `constraint_declarations`、新設 limit class `enum_members` (`example_profile: 64`)。根拠: 契約に `alter_field` は enum として存在するが実装が無く (F-1)、宣言型 (`field_types`) と対称な制約宣言の欠落が「クライアントが書ける値をサーバ側でしか知らない」状態を生んでいた。
    2. **R-3 検証エラーの固定 details 語彙** (D-3)。`errors.details_vocabulary` に `VALIDATION_FAILED`/`IDENTIFIER_INVALID`/`CAPABILITY_UNSUPPORTED` の 4 key (`field`/`declared_type`/`observed_type`/`violated_declaration`) を追加し、`violated_declaration_vocabulary` (10 語の閉じた語彙) と `layer_rule` を追加する。根拠: 現行 details は 3 code のいずれについても構造化された固定語彙を持たず (MitateDB は 105 箇所の `ValidationError` が details 引数 0 件、F-7)、AI エージェントが denial の理由を機械的に判別できなかった。
    3. **R-4 `dry_run` と無状態 `plan`** (D-4)。`MutationRequest`/`ScopedMutationRequest`/`SchemaOperationRequest` に `dry_run`/`plan` を、4 request schema すべてに `budget` を追加する (budget は本文 5 と共有)。`dry_run` は実呼びと同一の gate をすべて通り、外部可視の状態変化 0 (監査行を含む) を返す。`plan` は要求の正規化 digest + Application の schema revision から成る無状態トークンで、`MutationResult`/`SchemaOperationResult` に `plan` (optional string) を追加する。新設 capability `dry_run`。根拠: 破壊的操作や大規模書き込みの事前確認手段が契約に無く、AI エージェントが「試してから実行する」安全なパターンを持てなかった。
    4. **R-5 `idempotency` の実装と契約追記** (D-5)。`structured_operations.idempotency` (`record`/`correlation`/`key_secrecy` の 3 段落) を追加し、`SchemaOperationRequest.idempotency_key` を新規に追加する (`MutationRequest`/`ScopedMutationRequest` は既存)。同一 key・異なる digest は `CONFLICT`、保持期間内の同一 key・同一 digest の再送は元の結果 (`request_id` を含む全体) を再実行せずに返す。根拠: 契約は `idempotency` capability と 2 limit class をすでに宣言しているが、両 peer とも present-denial で拒否しており (F-19)、C-07 (ii) の肯定枝が一度も実行されていない (L7-8)。
    5. **R-6 request budget** (D-6)。`QueryRequest`/`MutationRequest`/`ScopedMutationRequest`/`SchemaOperationRequest` に `budget` (object、`result_items`/`execution_ms`/`batch_items`) を追加し、`limits.request_budget` 節を追加する。実効 bound = min(配備値, budget)、budget は配備値を上回る方向には一切効かない。新設 capability `request_budget`。根拠: 配備が宣言する bound は固定であり、1 要求が「自分の取り分をさらに絞る」手段が無く、AI エージェントが探索的な要求に慎重な bound を自分で課せなかった (P-5)。
    6. **R-7 成功応答の `request_id`** (D-7)。`QueryResult`/`MutationResult`/`SchemaOperationResult` に `request_id` (optional string、`required` は不変) を追加する。1.7.0 を宣言する実装は必ず載せる (無条件義務)。値は監査行の `request_id` と同一。根拠: 契約は denial 側に `errors.shape.request_id` を既に持つが成功応答には無く、client が自分の応答を監査証跡と相関させる手段が非対称だった。
    7. **R-8 派生の操作カタログ** (D-8)。`endpoints.*`/`control_endpoints.*` に `roles`/`requires_capability`/`atomicity` (固定 3 語 `atomic`/`none`/`atomic_unless_best_effort`) を、`destructive_confirmation` に `applies_to_structured` を、`versioning` に `obligations`/`obligations_note` を追加する。`tools/contract_catalog.py` が契約 JSON から `spec/OPERATION_CATALOG.json` を機械的に射影する。根拠: 現行 JSON からは role・destructive・atomicity・能力依存を機械的に導けず (F-20)、AI エージェント統合者が自然文を都度解釈する必要があった。
    8. **契約文書のみの変更 (実装に義務を課さない) — その 1: R-10 (B) 接頭辞剥離** (D-9)。付録 B の 29 値のうち機械的に分離できた 26 値から、provenance 接頭辞・挿入句を除去し `spec/CONTRACT_HISTORY_MANIFEST.json` に記録する。規範文は 1 語も変えない (`schemas.AuditResult.properties.events.items.description` の 1 件のみ、宙に浮く後方参照 `this ruling closes` → `this contract closes` の語改訂を伴う)。
    9. **契約文書のみの変更 — その 2: `versioning.obligations` 配列の追加** (D-8 (3))。`version_binding` 散文の機械可読索引であり、散文を代替しない。
    10. **契約文書のみの変更 — その 3: R-8 の構造化フィールドと派生カタログ**。上記 7 と同一 (`operation_catalog_url` は `CapabilityDocument` の optional 1 項目であり義務にしない)。

    **(b) 義務の条件付き性**: **無条件義務は 2 件** — (i) `VALIDATION_FAILED`/`IDENTIFIER_INVALID`/`CAPABILITY_UNSUPPORTED` の details 語彙遵守 (本文 2)、(ii) 成功応答の `request_id` (本文 6)。いずれも 1.7.0 を宣言すること自体に結び、いずれの capability の status にも依存しない。**条件付き義務は 5 件** — 本文 1 (`constraint_declarations` かつ `schema_operations`、および `constraint_declarations` かつ `application_catalog` の 2 連言)、本文 3 (`dry_run`)、本文 4 (`idempotency`)、本文 5 (`request_budget`)。この分割は `versioning.version_binding` の 1.7.0 段落 (無条件 (a)(b)、条件付き (1)〜(5)) および `versioning.obligations` の 1.7.0 エントリと 1 対 1 で対応する。

    **(c) 契約文案の所在**: 設計の契約文案ブロックを持つ値は逐語複製、次の2値とendpoint_fields_noteは監督確定(設計v1.4 §5 U-8 #30〜#32に逐語記録) — 契約に置いた新規/改訂の英語文言のうち、`docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` §3 D-1〜D-9 が「契約文案」ブロックを持つ値はすべてそこから逐語で複製した (常設規律 4)。置き場所の確定 (§5 U-8) を含め、言い換え・要約・語順の入れ替えは行っていない。`schemas.SchemaOperationResult.properties.descriptor.description` と `schemas.CapabilityDocument.properties.operation_catalog_url.description` (WP-1a レビュー L-6 が指摘した実装担当起草の散文) および `endpoint_fields_note` (同レビュー M-4) の3値は、設計に「契約文案」ブロックを持たないため、監督が確定し設計 v1.4 §5 U-8 #30〜#32 に実値を逐語で記録した。

    **(d) 依頼者裁定と委任の記録**: 依頼者裁定 (2026-09-07、逐語) — 「判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。」。この委任のもとで監督が確定した項目 (U-1〜U-8) はいずれも設計 §3/§5 に逐語で記録されている。

    **(e) 版数の扱い**: 1.6.0 は既に main へマージ・公開済み (従属判断 11 実施記録参照) であるため、従属判断 4/5 のような個別版数据え置きの余地はなく、7 項目を単一の 1.7.0 束として出荷する (依頼者裁定の委任に基づく監督確定)。

    **(f) 依頼者裁定の参照と却下した側**: `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` §4 A-1〜A-10。主な却下: **A-1** backend 層の物理制約 (NOT NULL/CHECK) の追加 (契約は宣言 registry からの報告に留め、物理制約は課さない — SI-12 の契約外バイパスの姿勢を変えない)。**A-6** `versioning.version_binding` の散文を配列へ全面置換 (依頼者確定文言の破棄になるため不採用。`obligations` は索引として併存させる)。**A-7** カタログ生成器に自然文解釈を持たせる (P-7 の趣旨に反し、生成が非決定的になるため不採用)。**A-9** dry_run 応答に `assigned_addresses` を仮の値で載せる (未確定の採番を返せば偽の宣言になるため不採用)。他の却下項目は設計文書 §4 に列挙のとおり。

    **項目ごとの再検討条件**: 本文 1〜7 のいずれも特になし — 既存キーの削除・型変更・enum 縮小を伴わない additive 変更であり (禁止事項 3、§9 の実測で確認)、新設フィールドはすべて optional、新設 capability は既定で `unavailable` を正直に宣言できる。契約文書のみの変更 (8)(9)(10) も特になし — 規範文を変えない剥離、既存散文の索引化、義務を課さない optional キーである。

    **R-10 (B) の剥離 (契約文書のみの変更。実装に義務を課さない)**: 付録 B の 29 値のうち 26 値を剥離し、`unstripped` 3 値 (`versioning.version_binding`、`versioning.compatibility`、`destructive_confirmation.phrase_construction.rules[3]`) は規範文と不可分なため残す。剥離前後の deep-equal (マニフェスト逆適用) 26/26 一致を実測済み (WP-1 完了報告 §監査照合項目 5)。

    **`versioning.obligations` の追加 (契約文書のみの変更)**: `version_binding` 散文の機械可読索引。1.2.0〜1.7.0 の 6 版を載せ、件数語 (`N of those obligations are unconditional`) を持つ 1.4.0/1.6.0/1.7.0 の 3 版についてのみ無条件件数を散文と一致させる。

    **R-8 の構造化フィールドと派生カタログ (契約文書のみの変更)**: `endpoints.*`/`control_endpoints.*` の `roles`/`requires_capability`/`atomicity`、`destructive_confirmation.applies_to_structured`。`operation_catalog_url` は `CapabilityDocument` の optional 1 項目であり義務にしない。

    **実施記録 (契約公開、WP-1)**: 契約 1.7.0 は `docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md` (v1.0、v1.3 整合) WP-1 で公開する。**この WP は両 peer の `contract_version` を動かさない** — 各 peer の flip はその peer の無条件義務 (R-3 + R-7) を出荷する最後のサブ WP (2e/3e) の同一コミットに落ちる。両 peer には provisional gate (新フィールド 7 種を実行前に `CAPABILITY_UNSUPPORTED` で拒否) と新設 capability 3 語の `unavailable` 宣言が、この WP と同一コミットで入る。

    **U-5 = (B) により `error_codes` を初版から外したこと**: `endpoints.*.error_codes` (返し得る code の配列) は R-8 の派生カタログに含めない。根拠 (§5 U-5 = (B)、2026-09-07 監督確定): ある endpoint がどの code を返し得るかは、宣言された capability の組み合わせ・配備の limit 構成・request の形に依存する条件的事実であり、endpoint 単体の静的な列挙として固定すると「この code は返らない」という誤った安全側の期待を client に持たせる (返り得る code が増えることは additive だが、client が「この一覧にない code は来ない」と読めば非 additive な保証を契約が暗黙に負うことになる)。`errors.codes` の全域列挙と `errors.details_vocabulary` の閉じた語彙で足りるとし、endpoint ごとの部分集合は初版では公開しない。

13. **フェーズ10 契約 1.8.0 (`limit_enforcement` の適用単位を配備全体と定義し、配備者宣言 `process_ceilings` から複数プロセス配備は `deployment_required` を導く) への裁定 (2026-09-08、監督確定、依頼者委任「判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。」)。** 新規 CCR ではなく、既存の意味論 (`capability_status.rules` の enforcement 語彙制限、`limits`/`limit_enforcement` の宣言規律) を明確化する additive 変更として採用する。実施設計は `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §3 D-5 (R-18 の裁定) (i)〜(v)、§5 U-1。契約への反映は WP-5 で完了する (公開前の追補 (c) を含む)。前例は従属判断 9 (1.4.0 の束 8 件一括)・従属判断 10 (1.5.0 の束 2 件一括)・従属判断 11 (1.6.0 の束 4 件一括)・従属判断 12 (1.7.0 の束 7 件一括)。

    **(a) 本文 — 1.8.0 が足す 1 項目目 (無条件義務)**: `limit_enforcement` の `enforced`/`deployment_required` は、これまで契約上どちらも「単位」を明示していなかった (1 プロセスの話なのか、配備全体の話なのか)。1.8.0 は `capability_status.rules` に 1 文 (`limit_enforcement values describe the whole deployment reachable at the declared surfaces base URL, never one server process...`) を足して単位を配備全体に固定し、`limits.profile` の末尾に同じ規律を要約する 1 文を足す。無条件義務は `limit_enforcement_scoped_to_deployment_behind_base_url` の 1 件のみ (subordinate ruling 13)。根拠: r2db-api は各 base URL を単一プロセスで serve するが、MitateDB-api は Cloud Run 上で複数プロセスが同じ base URL を serve し得る (`--max-instances` > 1) — 契約がこの単位を定義しないまま `enforced` を宣言させると、in-memory per-process の bound を「配備全体で保たれている」と読める偽の宣言になり得た。**この項目に関する契約の変更はここまでである** (1.8.0 全体の項目数は下記 (c) を参照): 配備者宣言 `process_ceilings` 機構そのもの (両 peer への `platform_declarations` 追加、`limit_enforcement` の 3 区分写像、起動時 fail-fast) は契約を要さない配備/実装の変更であり、WP-6 の範囲である。

    **(b) 却下した代替案**: `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §4 A-1〜A-4 (配備制約への固定 (`--max-instances=1`)・共有 limiter・契約文なしの `deployment_required`) を却下する。理由は同文書 §5 U-1 のとおり — 契約の沈黙が共通の問題である以上、埋めるべきは契約であり、配備制約への固定は「高性能が大前提」という依頼者目標と矛盾する。

    **(c) 追補 — 1.8.0 が足す 2 項目目 (条件付き義務、同一 idempotency key の同時送信)**: 2026-09-08、監督確定 (裁定 U-9、設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` v1.3)。外部レビュー 2 (2026-09-08) が PostgreSQL 16 上で再現したとおり、同一 `idempotency_key` を持つ 2 要求が同時に到着すると両 peer とも lookup がどちらも「記録なし」を読み、効果を 2 回実行し得た (digest が異なっても CONFLICT にならなかった)。契約 1.7.0 の `structured_operations.idempotency.record` は「without executing anything a second time」で既にこれを含意していたが、明文としては逐次的な再送しか述べていなかった。1.8.0 は `structured_operations.idempotency.record` の末尾に、同時到着した同一キーの 2 要求は直列化され高々 1 件のみが実行されること (他方は先着の commit 後に、digest が一致すれば記録からの replay、異なれば CONFLICT として答えられ、先着が失敗して記録を残さなかった場合は新規要求として実行されること)、および `idempotency_entries` の上限も同じ直列化の下で評価されることを述べる 2 文を足す。`versioning.obligations` の 1.8.0 entry の `conditional` は空リストから 1 要素 (`idempotency_concurrent_same_key_sends_serialized`、capability `idempotency`) になり、`versioning.version_binding` の 1.8.0 段落は無条件 1 件・条件付き 1 件を列挙する形に書き替えられる。実装 (両 peer の key 単位直列化) と検証 (`conformance-tests/CONDITIONS.md` に新設する同時送信の共通条件) は WP-6d の範囲であり、この追補は契約文のみを動かす。**版数の扱い**: 1.8.0 はこの時点で `main` に未公開 (branch `phase10-wp5` のみ) であるため、版数は動かさず 1.8.0 の本文そのものを改める。前例に照らせば、公開済みの版に同じ変更を足す場合は新しい版数を要する。

    **版数の扱い**: 1.7.0 は既に main へ公開済みであるため、従属判断 4/5 のような個別版数据え置きの余地はなく、この裁定を単独の 1.8.0 として出荷する (依頼者裁定の委任に基づく監督確定)。1.8.0 が足す義務は (a) と (c) の 2 件である。**実施記録 (契約公開、WP-5)**: 契約 1.8.0 は第10次作業指示書 WP-5 節で公開する。**この WP は両 peer の `contract_version` を動かさない** — 両 peer は 1.7.0 を宣言したまま (`process_ceilings` 宣言と `limit_enforcement` 写像を実装する WP-6 の pair-closing コミットで flip する)。

14. **フェーズ11 契約 1.9.0 (最低共通機能プロファイル `common_baseline` の実行義務と `operation_catalog_url` の宣言・byte 一致配布) への裁定 (2026-09-24、依頼者裁定 U-1 = (α)・U-4 = (α))。** 新規 CCR ではなく、両 peer が既に宣言している capability の交差を契約本文に明文化する additive 変更として採用する。実施設計は `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` §3 D-1 (プロファイルの内容 = 現物の交差)・D-4 (契約版 1.9.0 の obligation は baseline の実行義務)・D-5 (`operation_catalog_url` の最小形 = 宣言と byte 一致の配布)。契約への反映は作業指示書 `docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` WP-1 で行う。**この WP は両 peer の `contract_version` を動かさない** — 両 peer の flip は同作業指示書 WP-3 の同一コミットに落ちる。`schemas.OperationCatalogDocument` と `definitions.OperationCatalogEntry` は `additionalProperties: false` で書き、従属判断 7(A) の closed 列挙に加える。

15. **フェーズ11 契約 1.10.0 (keyset ページング — `structured_operations.paging` の新設、`versioning.obligations`/`version_binding` の 1.10.0 entry、`Page.cursor` の `maxLength` 撤去) への裁定 (2026-09-24、依頼者裁定 Q-1/Q-2/Q-3/Q-5、監督起票)。** 新規 CCR ではなく、既存の意味論 (CCR-01 structured API/非 SQL 公開、CCR-13 行の指し示し可能性) を明確化・実効化する additive 変更として採用する。実施設計は `docs/design/PHASE11_KEYSET_PAGING_V1.md` (v0.6) §3 D-1〜D-9、§5.1 (依頼者裁定)、§6.1 (C-30)。契約への反映は作業指示書 `docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md` WP-1 で完了する。前例は従属判断 9 (1.4.0 の束 8 件一括)・従属判断 10 (1.5.0 の束 2 件一括)・従属判断 11 (1.6.0 の束 4 件一括)・従属判断 12 (1.7.0 の束 7 件一括)・従属判断 13 (1.8.0 の束 2 件一括)。

    **本文 — 1.10.0 が足す義務 (すべて条件付き、`structured_query` が `unavailable` 以外の実装にのみ束縛。無条件義務は 0 件)**: (1) query が返す行の全順序化 (`order_by` + 実装任意の tie-break)、(2) `QueryResult.next_page` は「続きの行が存在するとき、かつそのときに限り非 null」、(3) `next_page` が非 null のときそれは無状態の keyset cursor (offset でも件数でもない)、(4) cursor は Application・entity・`where`・`order_by` に束縛され (`where` は述語の順序に依らない)、`select`/`page.size` の変更を跨いで有効、(5) 復号不能・順序値不一致・束縛不一致の cursor は `VALIDATION_FAILED`/`request_schema`/`page/cursor` で拒否、(6) 走査を通じて順序項が変わらない行はちょうど 1 回返る、(7) `page.size` を省いた要求は 1000・宣言 `limits.result_items`・要求 `budget.result_items` の最小値を運んだものとして答えられる (既定ページ)。契約文言は `structured_operations.paging` の 6 節 (`ordering`/`next_page`/`cursor`/`binding`/`refusal`/`traversal`) に置く。`Page.cursor` は `maxLength` を持たない (`{"type": "string"}`) — keyset cursor は順序キーの値そのものを運ぶため 512 バイトを超えうり、要求文字列の長さは `request_bytes` が bound する (依頼者裁定 Q-5 = (a))。

    **依頼者裁定 Q-1 (MitateDB の保存形を変えるか。逐語、`docs/design/PHASE11_KEYSET_PAGING_V1.md` §5.1)**:

    > D-2 (保存形の変更、保証は完全)で。

    **依頼者裁定 Q-2 (cursor の束縛範囲。逐語、同 §5.1)**:

    > select/size の変更は取り違えではなく正当な意図でありうるなら束縛してはいけないように思う

    裁定は A (Application, entity, `where`, `order_by` のみ。`select` と `page.size` は自由)。

    **依頼者裁定 Q-3 (契約文と C-30 の Condition 文の逐語確定。逐語、同 §5.1)**:

    > Q-3 は見直し 1 点を含めて確定、Q-5 は (a)、Q-4 はその形で。

    見直し 1 点: 案文 C-4 の `where` の束縛を、述語の順序に依らない形 (field・演算子・値で整列した正規 JSON) に改める。

    **依頼者裁定 Q-5 (`Page.cursor` の `maxLength`。逐語、同 §5.1、Q-3 と同じ返信)**:

    > Q-3 は見直し 1 点を含めて確定、Q-5 は (a)、Q-4 はその形で。

    裁定は (a) — `maxLength` を外す。

    **版数の扱い**: 契約 1.9.0 は既に main へ公開済みであるため、この裁定を単独の 1.10.0 として出荷する。**実施記録 (契約公開、WP-1)**: 契約 1.10.0 は作業指示書 `docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md` WP-1 で公開する。**この WP は両 peer の `contract_version` を動かさない** — 両 peer は 1.8.0 を宣言したまま (両 peer の keyset 実装と C-30 の緑化が揃う WP-6 の pair-closing コミットで flip する)。受け入れ監査 2026-09-25 観察 4b の訂正: この一文は WP-1 時点の実装状態を述べるものであり、番号の振り直し (下記) が契約版・従属判断番号・条件番号にだけ適用されるはずが機械的な置換で誤って追随していた (`git show 3af11b3` で両 peer とも 1.8.0 を実測)。

    **番号の振り直し (2026-09-25)**: 本項は起票時に従属判断 14・契約 1.9.0・C-28 を仮に名乗っていた。並走した最低共通機能プロファイルの裁定 (上の 14.) が main (`b283f48`) で従属判断 14・契約 1.9.0・C-28/C-29 を先に消費したため、本項を従属判断 15・契約 1.10.0・C-30 に振り直した (設計 `docs/design/PHASE11_KEYSET_PAGING_V1.md` §0 と作業指示書 §9 の訂正註)。依頼者裁定の逐語引用は起票時のまま改めない。

16. **契約 1.11.0 (未宣言 field 名の拒否を両 peer で `VALIDATION_FAILED`/`request_schema`/位置 path に揃える) への裁定 (2026-09-25、依頼者裁定「A で 1.11.0、規模 M で進めてください」、監督起票 R-110)。** 新規 CCR ではなく、既存の意味論 (`errors.details_vocabulary` の `VALIDATION_FAILED` 語彙、CCR-13 storage の field 宣言可能性) を明確化・実効化する additive 変更として採用する。実施は作業指示書 `docs/work-orders/WORK_ORDER_R110_UNDECLARED_FIELD_REFUSAL_V1.md` WP-1 で完了する。前例は従属判断 9 (1.4.0 の束 8 件一括)・10 (1.5.0 の束 2 件一括)・11 (1.6.0 の束 4 件一括)・12 (1.7.0 の束 7 件一括)・13 (1.8.0 の束 2 件一括)・14 (1.9.0)・15 (1.10.0)。

    **発端**: `order_by` に未知の field を指定したときの拒否コードが両 peer で違った — r2db-api は `NOT_FOUND` (詳細なし。訂正記録 m-6 による)、MitateDB-api は `VALIDATION_FAILED`/`request_schema`/`order_by/<i>/field`。同じ誤りに別のコードが返るので、共通契約を読んで書いたクライアントが片方でしか通らない分岐を持つ。契約の沈黙は `order_by` に限らず、`select`・`where`・mutation の `values` の未宣言 field 名にも及んでいた。

    **本文 — 1.11.0 が足す義務 (無条件義務 1 件のみ、`errors.details_vocabulary.undeclared_field` の全文)**:

    > A request that names a field the entity does not declare -- an entry of a query's select, where or order_by, a key of a mutation's values, or the field of a mutation's where predicate -- is refused with VALIDATION_FAILED, violated_declaration request_schema and field naming the position that carries the undeclared name (select/<i>, where/<i>/field, order_by/<i>/field, operations/<i>/values/<name>, operations/<i>/where/<j>/field); declared_type and observed_type are absent, since no declaration exists for that name. Schema operations that address a field by name are outside this rule. NOT_FOUND is not a conforming refusal of an undeclared field name at these positions.

    schema 操作 (`alter_field`・`create_index` などが未知の field を名指す場合) はこの規則の対象外とする — 利用者は catalog を読んで宣言 field を知り、既存の拒否 (r2db の `NOT_FOUND`、MitateDB の `constraint_declaration`) を変えない。

    **依頼者裁定 A (逐語)**:

    > A で 1.11.0、規模 M で進めてください

    起票側の疑義に対する回答であり、A は「4 位置 (`select`/`where`/`order_by`/mutation `values`) を両 peer で `VALIDATION_FAILED`/`violated_declaration: request_schema`/`field` = 位置 path に揃え、`declared_type`・`observed_type` は載せない」案を指す。監督裁定 (作業指示書 §1 監督確定事項) が mutation の `where` (`operations/<i>/where/<j>/field`) を明示的に含め、schema 操作の不一致を範囲外と明記した。

    **版数の扱い**: 契約 1.10.0 は既に main へ公開済みであるため、この裁定を単独の 1.11.0 として出荷する。**実施記録 (契約公開・両 peer の拒否・宣言、WP-1)**: 契約 1.11.0 は作業指示書 `docs/work-orders/WORK_ORDER_R110_UNDECLARED_FIELD_REFUSAL_V1.md` WP-1 で公開する。**この WP は両 peer の `contract_version` を同一コミットで動かす** (4 位置の拒否コードの実装と `select`/`where`/`order_by`/`values` の path 統一が実挙動として揃うため、契約の文言化・実装・宣言 flip を 1 commit に収める — 従属判断 9〜15 が契約文と実装 flip を別 WP に分けたのとは異なる)。

配備の DB 認証 posture も同日 (2026-08-28)、依頼者が起票側推奨に委任し **posture B (UNIX socket + peer 認証)** で確定した。これは契約ではなく配備の判断であり、記録は `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §3 と設計文書 §3。問題が生じた場合は posture A へ切り替え可能 (code は両 posture で同一に動く)。

採用時に効く既知の依存: CCR-14 の失効確認条項は destructive 確認の有効性定義 (C-06 共通化の前提、MitateDB の確認トークン不検証) の解決に依存する。この定義が決まるまで当該条項は実効化しない。**→ 2026-08-29 に解決 (従属判断6「宣言と復唱」方式)。実効化は契約 1.2.0 の作業単位 (WP-5 完了後) で行われるまで、条項は休止を続ける。**

### 実装順序 (採用後)

CLAUDE.md の開発順序に従う: 共通契約 (`spec/data-service-api.v1.json`) の文言化 → conformance 条件 → 各 peer 実装。CCR-13 の storage 実装は `field_type` の型付き列化と同時に行うのが最も安い (CCR 文書「両 peer 適用可能性」)。

**文言化は完了した (2026-08-28、契約 1.1.0)。** 全従属判断の裁定を反映し、独立レビュー (Opus) を経て確定。1.1.0 の追加はすべて additive であり、両 peer は 1.1.0 を申告した上で新 capability (`row_addressability` / `cross_entity_mutation` / `control_plane`) を unavailable と申告する。あわせて r2db-api の `upsert` は、一意性宣言 (`unique_keys`) の実装が公開面の申告更新とともに完了するまで `CAPABILITY_UNSUPPORTED` として拒否される (2026-08-28 追記: CCR-13 storage 実装 WP-2 で意味論は in-memory 実装済み。公開面の拒否は `DataService` の暫定ゲートで維持され、WP-5 の申告更新と同一コミットで解除される — `docs/design/R2DB_CCR13_STORAGE_V1.md` §3) — 契約が意味を与えられない操作を enabled と申告し続けることが 1.1.0 で規則違反になったため。次段は conformance 条件の登録 (`conformance-tests/CONDITIONS.md`): application credential の control endpoint への fail-closed、control credential の data/schema 拒否、`role=control` 発行の拒否 (案B)、revoke の終端性、per-entity endpoint の body `entity` 拒否、cross-entity の実行前検証、応答の契約 schema 検証。
