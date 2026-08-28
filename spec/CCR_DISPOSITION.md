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

入力は `r2db-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md` 第3版。CCR-01〜12 と異なり、**起票時点では採否未決である。** いずれも共通契約の骨格に関わるため、実装着手前に判断する。

第1版・第2版はそれぞれ独立レビューを経て改稿した。訂正の記録は下記および CCR 文書内の訂正欄に保持する。

| CCR | 判定 | 論点 | 判断に必要なもの |
|---|---|---|---|
| CCR-13 行の指し示し可能性 | **審議中** | `allowed_mutations` に既にある `upsert` は、一意性の概念なしには意味を定義できない。契約が意味を与えられない操作を許可している。要求は行を狙った mutation を支持する entity に限り、結果を4性質 (宣言・可視・照準・一意不変) に分解、revision の被参照先は5条項で固定 | `MutationResult` の拡張を v1 で行うか (サーバ側採番の識別子を返す唯一の応答形状変更) |
| CCR-14 制御プレーン | **審議中** | `control` role、`control_credential` scheme、`lifecycle.credential` の意味論は採用済みで endpoint だけが無い。乖離は起きた問題ではなく見込みの問題 (統治下2 peer の公開面乖離はゼロ、旧 VPS 実装は統治外)。提供は必須とせず `capability_status` で申告 | 採用時期 (全体採用 / 安全条項のみ先行 / 全体延期)。in-band 発行 (案A / 案B)。base path `/control/v1` の確認 |
| CCR-15 entity をまたぐ atomicity | **審議中** | mutation 経路が `/v1/data/{entity}/mutations` であり atomic batch が単一 entity に閉じる。第3版で形状を定義 (`POST /v1/data/mutations`、各 `Mutation` に必須 `entity`)。対話的トランザクションは明示的に排除 | `batch_entities` の境界値と enforcement layer の申告方法 |

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

**レビュー側の誤り (同じく記録する)**

- 第2版レビューは「契約側 r2db-api は schema-per-application」と結論したが、事実に反する (`r2db-api/migrations/0003_provision_application.sql` が `CREATE DATABASE` を発行し、`PostgresCell` の `schema` 引数は各 DB 内の `public` を指す)。ただし「CCR が peer の topology を断定すべきでない」という指摘自体は妥当であり、第3版は topology の断定を除いた

### 未決事項 (依頼者判断)

1. **CCR-13/14/15 の採否そのもの**
2. CCR-13: `MutationResult` の v1 拡張
3. CCR-14: 採用時期 — (a) 全体採用 (b) 安全条項のみ先行し endpoint 形状は peer 起動後に確定 (c) 全体延期。(b) は前レビュー担当の推奨だが決定ではない
4. CCR-14: control credential の in-band 発行 — 案A (発行も in-band。運用一貫、ただし盗まれた1本が失効を生き延びる永続性を得る) / 案B (発行は帯域外の儀式。永続性の危険を断つが、運用者追加にサーバ権限が要る)。既存 invariant は control credential の侵害を扱っていないため、採る案により conformance 条件が変わる
5. CCR-14: base path `/control/v1`
6. CCR-15: `batch_entities` の境界値と enforcement layer

### 未採用のまま実装してはならない

いずれも共通契約の変更であり、`r2db-api` 側の実装判断として先行させない (CLAUDE.md: peer を共通契約の暗黙的所有者にしない)。採用が決まるまでの暫定手段は帯域外 (CLI) とし、暫定であることを明記する。

CCR-14 の実装には前提条件 (credential の永続化、composition root) がある。この前提作業自体は契約変更を伴わないため採否を待たずに進められるが、credential 記録の形・ライフサイクル状態・bootstrap の形を先取りで固定しないよう、採否判断を先に依頼者へ諮る。
