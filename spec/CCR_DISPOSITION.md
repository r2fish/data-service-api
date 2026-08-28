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

| CCR | 判定 | 論点 | 判断に必要なもの |
|---|---|---|---|
| CCR-13 行の指し示し可能性 | **審議中** | `allowed_mutations` に既にある `upsert` は一意性の概念なしには意味を定義できず、r2db-api は実装の選択した意味論で enabled 申告している (統治下の実証)。要求: entity は mutation 能力区分 (読み取り専用 / 追記専用 / 追記・削除 / 可変) を宣言し、update / upsert を支持する entity にのみ addressability を要求。結果は5性質 (宣言・可視・照準・不変・自発的再割当て禁止) に分解、revision の被参照先は6条項で固定 | `MutationResult` の拡張を v1 で行うか。アドレス再利用の扱い (案i 再利用禁止 / 案ii revision precondition の領分) |
| CCR-14 制御プレーン | **審議中** | `control` role、`control_credential` scheme、`lifecycle.credential` の意味論は採用済みで endpoint だけが無い。乖離は起きた問題ではなく見込みの問題 (統治下2 peer の公開面乖離はゼロ、旧 VPS 実装は統治外)。提供は必須とせず `capability_status` で申告。形状表は案A/案B で書き分け、reset は既存 credential 全失効、制御面にも SI-08 の資源境界 | 採用時期 (全体採用 / 安全条項のみ先行 / 全体延期)。in-band 発行 (案A / 案B)。base path `/control/v1` の確認 |
| CCR-15 entity をまたぐ atomicity | **審議中** | mutation 経路が `/v1/data/{entity}/mutations` であり atomic batch が単一 entity に閉じる。形状は `POST /v1/data/mutations` + 新規定義 `ScopedMutationRequest` / `ScopedMutation` (既存 `Mutation` は無変更、per-entity endpoint は body の `entity` を拒否し続ける)。対話的トランザクションは明示的に排除 (再検討条件付き) | `batch_entities` の境界値と enforcement layer の申告方法 |

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

### 未決事項 (依頼者判断)

1. **CCR-13/14/15 の採否そのもの**
2. CCR-13: `MutationResult` の v1 拡張
3. CCR-13: アドレス再利用の扱い — 案i (再利用禁止を性質に含める。ABA を構造的に断つ。実コストはアドレス機構が AUTOINCREMENT/非再利用連番/UUID に限られること — 自然キーは一意性宣言として引き続き使える。採択時は5性質が6性質になる) / 案ii (revision precondition の領分。機構の自由は最大だが、クライアントが自分の晒され方を知る契約上の手段が無い) / 案iii (再利用の有無を catalog で宣言。機構の自由を保ちつつ情報の非対称を消す。「再利用しない」宣言の適合証拠は自動テスト + review evidence の併用になる)。起票側の推奨は案iii だが決定ではない
4. CCR-14: 採用時期 — (a) 全体採用 (b) 安全条項のみ先行し endpoint 形状は peer 起動後に確定 (c) 全体延期。(b) は前レビュー担当の推奨だが決定ではない。三案の利害は CCR 文書に対称に記載
5. CCR-14: control credential の in-band 発行 — 案A (発行も in-band。運用一貫、ただし盗まれた1本が失効を生き延びる永続性を得る) / 案B (発行は帯域外の儀式。永続性の危険を断つが、運用者追加にサーバ権限が要る)。既存 invariant は control credential の侵害を扱っていないため、採る案により endpoint 形状と conformance 条件が変わる
6. CCR-14: base path `/control/v1`
7. CCR-15: `batch_entities` の境界値と enforcement layer

採用時に効く既知の依存: CCR-14 の失効確認条項は destructive 確認の有効性定義 (C-06 共通化の前提、MitateDB の確認トークン不検証) の解決に依存する。採用してもこの定義が決まるまで当該条項は実効化しない。

### 未採用のまま実装してはならない

いずれも共通契約の変更であり、`r2db-api` 側の実装判断として先行させない (CLAUDE.md: peer を共通契約の暗黙的所有者にしない)。採用が決まるまでの暫定手段は帯域外 (CLI) とし、暫定であることを明記する。

CCR-14 の実装には前提条件 (credential の永続化、composition root) がある。この前提作業自体は契約変更を伴わないため採否を待たずに進められるが、credential 記録の形・ライフサイクル状態・bootstrap の形を先取りで固定しないよう、採否判断を先に依頼者へ諮る。
