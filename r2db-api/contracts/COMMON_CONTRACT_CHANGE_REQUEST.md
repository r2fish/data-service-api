# 共通契約変更要求 (r2db-api 起票)

- 起票日: 2026-08-28
- 改訂: 2026-08-28 (第2版: 独立レビューを受けて CCR-13 を全面改稿、CCR-14 を改稿、CCR-15 を追加。第3版: 第2版への独立レビューを受けて CCR-13 のスコープと検証可能性を確定、CCR-14 に discovery / reset / 削除範囲を追加し乖離の数え方を訂正、CCR-15 に形状を定義。第4版: 第3版への独立レビュー (Opus) を受けて、アドレス再利用経路の穴を塞ぎ、CCR-14 の形状表を案A/案B で書き分け、CCR-15 の自己矛盾を解消、ほか下記訂正欄のとおり。第4版自体も採否判断前に差分レビュー (Opus) を受け、区分の normative 化・revoke 終端性・両論の公正化ほかを反映して確定した)
- 起票者: r2db-api 側設計作業
- 宛先: 共通契約 `spec/data-service-api.v1.json`
- 採否記録: `spec/CCR_DISPOSITION.md`

`MitateDB-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md` (CCR-01〜12) と同じ様式で起票する。番号は通番を継承する。

## 起票の基準

いずれも r2db-api 固有の都合ではなく、**共通契約の欠落**として提起する。判断の軸は次の順序に置く。

1. **堅牢で安全であること**
2. その上で**最大限の自由があること**

したがって本要求は、**道路にゲートを設けるのではなく、ガードレールを設けることを目指す。** 具体的には次を守る。

- **機構ではなく結果を要求する。** SI-00 が「containment を要求し、特定の topology を要求しない」のと同じ形にする。機構を契約に書くと、その機構に合わない将来の Capability が「新しいという理由で」通れなくなる。
- **ガードレールは危険のある場所に置く。** 安全要求のスコープは危険の所在から導く。危険の無い区間への無条件の要求は、それ自体がゲートになる (第2版の CCR-13 はこれを誤った)。
- **能力の提供を強制しない。** 必要としない配備に攻撃面を強制するのはゲートである。契約は形状と意味論を定め、可用性は `capability_status` で申告させる。
- **結果は検証可能な性質に分解する。** 散文のままの結果は適合テストが書けず、「機構は自由」が「何も固定されていない」に転化する。機構の自由と相互運用性は、性質の固定によって初めて両立する。

---

## CCR-13 — 行の安定した指し示し可能性 (row addressability)

### 要求

共通契約に、entity が **catalog で自らの mutation 能力の区分を宣言する**仕組みと、**行の同一性なしに意味を定義できない操作 (update / upsert) を支持する entity について、entity 内の行を安定して指し示せること**を結果として要求する。あわせて、ドメイン上の一意性を entity 単位で宣言できる仕組みを定義する。

entity の区分は宣言により次のいずれかとする。

| 区分 | 支持する mutation | addressability |
|---|---|---|
| 読み取り専用 | なし | 不要 |
| 追記専用 | `insert` のみ | 不要 |
| 追記・削除 | `insert` と述語による `delete` | 不要 |
| 可変 (addressable) | 全 mutation | **必須** |

ガードレールは危険のある場所に置く。addressability の不在が危険になるのは、クライアントが**特定の行を読み、後からその行を狙って書く** (read → address → mutate) 場面である。`update` と `upsert` は既存の行を書き換える操作であり、この場面を必然的に生む。一方、`insert` のみの流し込みや、述語による一括削除 (例: 月単位の入れ替えの削除側) はこの場面を持たない — そこへ無条件にアドレス宣言を要求するのは、危険の無い区間への要求でありゲートである (第3版はここを誤っていた。訂正欄参照)。`delete` そのものの危険 (誤った対象の破壊) は、既存の destructive 確認の意味論が引き続き束ねる。

区分選択の帰結として明記する: 追記・削除区分の `delete` は集合意味論 (述語に一致する行すべて) であり、**行を1件だけ確実に削除する要求を持つ entity は、可変区分を宣言する必要がある** — アドレスも一意性宣言も無い entity では「いま読んだこの行だけ」を保証する述語が構成できないためである。

この免除は第1版の「任意宣言」への回帰ではない。第1版の宣言は**可変データが安全から離脱する選択**であったが、本版の区分は **entity が支持する操作の宣言**であり、update / upsert を支持すると宣言した瞬間に addressability が必ず付いてくる。ガードレールの無い区間は生じない。**宣言区分が支持しない mutation はすべて `CAPABILITY_UNSUPPORTED` である** (区分表がそのまま normative であり、読み取り専用 entity への delete も、追記専用 entity への update もこの一文が拒否する)。宣言と実挙動の一致は適合テストの対象である — 区分ごとに検証可能なのは「支持しない操作の種別が拒否されること」であり、追記・削除区分と可変区分の `delete` はワイヤ上同形のため、両区分の弁別は update / upsert の拒否で行う。

**機構は規定しない。** 実装はサーバ採番の連番、クライアント供給の UUID、自然キー、その他いずれを用いてもよい。ただし機構の自由は、クライアントから見た指し示し方が実装ごとに異なってよいことを意味しない。結果を次の5性質に分解して固定する。

### 指し示し可能性の5性質 (適合テストの単位)

1. **宣言** — addressable な entity は、アドレスを構成するフィールド組を catalog で必ず宣言する
2. **可視** — アドレスフィールドは通常の select 可能なフィールドであり、query 結果に現れる
3. **照準** — アドレス組全体に対する `where` + `eq` は高々1行に一致する。アドレス組の重複を生む書き込みは `CONFLICT` で失敗する (この失敗が、性質3の正の適合テストを可能にする)
4. **不変** — アドレス組の値は行の生存期間中変化しない。アドレスフィールドを変更する update は `VALIDATION_FAILED` で拒否される
5. **自発的再割当ての禁止** — 退役したアドレスの再割当ては、クライアントの明示的な mutation (`delete` の後の `insert`) の結果としてのみ生じうる (その可否自体は下記「残余危険」の選択による)。保守動作 (compaction、vacuum、再構築、再起動) がアドレスを振り直し、または再割当てしてはならない

この分解により、機構が自由なままでもクライアントの手順は一様になる: **catalog で宣言を読む → select で取得する → where eq で照準する。** 散文 (「同じ行を後から確実に指せる」) のままでは適合テストが書けない。

性質5の検証は、ブラックボックスの自動テストだけでは完結しない (公開 API から実装の保守動作を起こす手段が契約に無いため)。SI 第7章4号と同じ形で、**自動テスト (削除・再挿入・再起動など起こせる擾乱に対する) と、実装の保守経路がアドレスを保存することの review evidence の併用**を適合証拠とする。

### 残余危険 — アドレスの再利用 (依頼者判断)

5性質は、**退役したアドレスが後続の明示的 insert により別の行へ再利用されること**を禁じていない。read → address → mutate の間に対象行が削除され、新しい行が同じアドレスを得ると、クライアントは別の行を書き換える (ABA)。独立レビューが実測で確認したとおり、SQLite の `INTEGER PRIMARY KEY` は `AUTOINCREMENT` なしでは削除された最大 id を再利用する。

これをどう扱うかは依頼者判断として選択肢を残す。なお各案のコストを正確に述べる: 本要求の catalog 宣言はアドレスフィールド組とドメイン一意性宣言を**別項目として分けている**ため、案i を採っても自然キーは一意性宣言として引き続き使える。また自然キーをアドレスに選ぶ自由は、案の選択以前に性質4 (アドレスフィールドの update 拒否 = 改名不能) によって既に窮屈である。

- **案i — 再利用の禁止を性質に加える (性質は6つになる)**: ABA を構造的に断つ。実コストは**アドレス機構の選択**が `AUTOINCREMENT`・非再利用連番・UUID に限られること (自然キーをアドレスに選べなくなることであり、自然キーを使えなくなることではない)
- **案ii — 再利用は許容し、revision precondition の領分とする**: 明示的な delete → insert はクライアントから観測可能な変化であり、stale なアドレスで書く競合は `expected_revision` が防ぐ (再利用された行は別の revision を持つ)。機構の自由が最大限保たれる。ただし `revision_preconditions` を有効化しない実装では残余危険が残り、**契約にはクライアントが自分の晒され方を知る手段が無い** (実装が再利用するか否かは文書の外)
- **案iii — 再利用の有無を catalog で宣言させる**: 本文書が繰り返し使っている手 (区分宣言、一意性宣言、`capability_status`) をここにも適用する。機構の自由は案ii と同じに保たれ、クライアントは宣言を読んで precondition の要否を判断できる (案ii の情報欠落を消す)。コストは catalog 語彙の追加と、「再利用しない」宣言の適合証拠が性質5と同種の自動テスト + review evidence 併用になること (「再利用する」宣言は自明に満たされるため、宣言の真正性検査は非対称になる)

起票側の推奨は案iii (情報の非対称を消しつつ機構を狭めない) だが、これは決定ではない。本文の5性質は案ii/案iii の前提で書かれており、案i 採択時は6性質に改稿する。

### 問題 — 契約が意味を与えられない操作を、統治下の peer が既に有効と申告している

`structured_operations.allowed_mutations` は既に `upsert` を含む。

```
allowed_mutations: ["insert", "update", "upsert", "delete"]
```

**upsert は「既存かどうか」の判定基準なしには意味を定義できない。** 何をもって「既に在る」とするのかを契約は一切述べていない。これは「実装不能」ではない — 正確には、**各実装が勝手な判定基準を選ぶことを契約が止められず、相互運用可能な形で有効化できない**、である。

そしてこれは見込みの問題ではない。**統治下の peer 間で現に観測できる。** r2db-api は upsert を実装済みで `atomic_mutation` に enabled として申告しており (判定基準は「`where` 一致行を update、0件なら insert」という実装の選択)、MitateDB-api は unsupported と申告する。可用性の差自体は `capability_status` が正当化するが、**enabled 側の意味論が契約でなく実装の選択で決まっている**ことが欠落の実証である。これが本要求の第一の、そして最も強い根拠である。

### 副次的な問題 — 事前条件の被参照先が未定義

`Mutation.expected_revision`、`transactions.retry`、エラーコード `PRECONDITION_FAILED` は revision による事前条件を三度言及するが、revision が何を指すのかを定義していない。entity のスキーマ revision に束ねる読み方も文言上は可能であり、実装ごとに別の意味になりうる。

今日の破綻はない。r2db-api は当該フィールドを `CAPABILITY_UNSUPPORTED` で明示的に拒否し、MitateDB-api は当該フィールドを受理する面を構造的に持たない (行 mutation の内部 API に `expected_revision` に相当する引数が存在しない)。しかしいずれかの peer がこの能力を有効化した瞬間に非互換になるため、有効化前に契約が被参照先を固定しなければならない。

第2版はこの未定義を問題として指摘しながら、変更表で何も固定していなかった。第3版で5条項に固定し、本版で第6条項と結果コードを追加する。**revision の被参照先は次の6条項とする。**

1. revision は実装が発行する**不透明な文字列**であり、クライアントは内容を解釈しない
2. スコープは**行**である (entity のスキーマ revision とは別物である)
3. 当該行への mutation が commit されるたびに変化する
4. **他の行への mutation によって変化しない** (これを欠くと、entity 全体の版番号を全行に返す実装が条項1〜3を字義上満たしつつ、無関係な並行書き込みで `PRECONDITION_FAILED` を返す — 真に行スコープな実装と観測可能に非互換になる)
5. `expected_revision` の比較は mutation と**原子的に**行われる
6. 不一致は `PRECONDITION_FAILED` で失敗する。`expected_revision` は既存行の同一性を前提とするため、対象行が存在しない場合は operation を問わず `NOT_FOUND` — `update` でも、`upsert` で一致行が無い場合でも同じである (`upsert` を insert に解決して precondition を黙って無視する実装を許さない。行の存在は同一 Application のクライアントに query で既に可視であり、`NOT_FOUND` は秘匿対象を漏らさない)。`insert` への `expected_revision` の付与は `VALIDATION_FAILED` (存在しない行への事前条件は意味を構成しない)。なお `expected_revision` を**伴わない** `update` / `delete` が0行に一致する場合は、現行どおり affected=0 の成功である — `NOT_FOUND` になるのは事前条件が存在を主張した場合に限る (この非対称は意図的であり、明記しないと実装が分かれる)

`QueryResult` が revision を行とともに返す要求は、**revision precondition の capability を有効と申告する実装にのみ適用する。** 無効と申告する実装、および申告しない実装に revision の維持を強制しない。この条件は entity の区分とは独立である — capability を有効化した実装では、追記・削除区分の entity でも行 revision が返り、述語 `delete` に `expected_revision` を付けられる (addressability は前提ではない)。なお `revision_preconditions` という名は現状 r2db-api の実装が使う申告名であって契約語彙ではない — 本要求は capability 名の契約への規定を含む (変更表参照)。

### 第1版の誤りの訂正

第1版は「`expected_revision` と `idempotency_key` の双方が行の同一性を前提とする」と記した。**`idempotency_key` について、これは誤りである。**

`idempotency_key` は `MutationRequest` に属するリクエスト単位の項目であり、`Mutation` (行単位) には属さない。サーバはキー→リクエスト要約→結果の重複排除ストアで実装でき、行の同一性を必要としない。

第1版はこの誤りに基づき「同一性を宣言しない entity では `idempotency_key` も利用不可」と提案していた。これは無関係な二つの機構を結合させ、**リトライによる重複追記が最も起きやすい追記専用データから、冪等性を奪う**提案であった。撤回する。

`idempotency_key` はサービス単位の Capability として、行の指し示し可能性とは独立に扱う。

### 証拠 — 実クライアント

r2db-api の現行クライアント (勤務表 etc、18 テーブル) は全テーブルで `id` による行指定を行う。加えて upsert 相当を全箇所で「自然キーで検索 → 見つかれば PATCH、無ければ POST」として手実装している。一意性制約が無いため、競合時に重複を生じうる。

ただしこの証拠の性質を正確に述べる。**このクライアントは現行 VPS 実装 (本契約の統治外) を相手にしており、本契約の利用者が要求したものではない。** 示しているのは「ある実アプリケーションがデータサービスに何を必要としたか」であり、同時に「本契約が唯一の移行対象を収容できない」ことである。統治下の証拠としては、上記の upsert の enabled/unsupported 差のほうが強い。

またこのクライアントは列の型、NOT NULL、DEFAULT も必要としている。**行の指し示し可能性だけでは本契約はこのクライアントを収容できない。** 本要求はスキーマ表現力の欠落の第一項であって、最後の項ではない。

### 必要となる契約変更

書き込み側だけでは足りない。読み取り側を含む。

| 箇所 | 変更 |
|---|---|
| `CatalogDocument.entities` | 現在は型なしの配列であり、**既存のすべての entity が未宣言**である。entity ごとに (a) 上記4区分の宣言、(b) addressable の場合はアドレスフィールド組、(c) ドメイン一意性宣言、を記述する形にする。**宣言は必須とし、既定 (未宣言時の解釈) を契約に残さない** — 未宣言の既定を許すと、既定が緩ければガードレールの抜け、厳しければ採用と同時に既存挙動が黙って変わる。実装は全 entity の宣言を出揃わせるまで本 capability を有効と申告できない |
| `QueryResult` | revision precondition capability が有効な実装は、事前条件に使う行 revision を行とともに返せるようにする。取得できない値を precondition に使えというのは成立しない |
| `MutationResult` | 現在は `{committed, affected}`。サーバ側で採番された識別子を返せるようにする。**サーバ採番識別子の空間は Application スコープ内で閉じ、その値・増分から他 Application の活動を推定できないこと**を条項とする (SI-01 の推定禁止、SI-10 の existence distinction に対応。Application 横断で共有される連番はこれに違反する) |
| `structured_operations` | **宣言区分が支持しない mutation はすべて `CAPABILITY_UNSUPPORTED`** (区分表がそのまま normative になる。個別列挙にしないのは、将来 mutation 語彙が増えたときの配線漏れを防ぐため)。加えて `upsert` の判定基準を宣言済みドメイン一意性に紐づけ、一意性未宣言 entity での `upsert` も `CAPABILITY_UNSUPPORTED` |
| `structured_operations` | 事前条件の6条項 (上記) を契約文言化する。capability 名 (例: `revision_preconditions`) を契約語彙として規定する |
| `limits.classes` | 冪等キーの重複排除ストアは、保持期間の上限を定めなければ無限に増える状態である (SI-08)。保持境界のクラス (例: `idempotency_retention_ms` / `idempotency_entries`) を追加し、enforcement layer を `limit_enforcement` で申告させる |
| `allowed_schema_operations` | 一意性宣言には複合キーが要るため、既存語彙の拡張が必要になる: `create_index` / `drop_index` は現在 `field` (単一文字列) しか持たず index 名の概念も無い。`fields` (配列)、`unique`、index 識別子を追加する。第3版の「新語彙をほぼ増やさない」は不正確であった |

`upsert` の制限は自由の制限ではない。**意味が定義できないものを、定義できないと正直に申告している**にすぎない。なお採用時の帰結として、r2db-api の現行の `atomic_mutation: enabled` (upsert 含む) 申告は一意性宣言の実装まで `capability_status` 規則に照らして維持できなくなる — これは移行作業の一部として明記しておく。

### Security Invariants との関係

新たな invariant は不要と考える。

- SI-11 の retry/precondition 条項が初めて実効化される
- 一意性違反は Application 自身のスコープ内で `CONFLICT` として現れ、他 Application の存在を漏らさない (SI-10 に抵触しない)
- キー宣言は既存の SI-05 の識別子検証境界を通る
- サーバ採番識別子の Application スコープ条項 (変更表) は SI-01/SI-10 を新しい面 (採番空間) に適用したもので、C-01 系の負テストに載る粒度である

### 両 peer 適用可能性

機構を規定しないため、双方が自然な手段を取れる。SQLite の実測結果は機構選択の制約を正確に示している。

- **MitateDB-api (SQLite)**: 裸の rowid は `VACUUM` により振り直される (実測確認済み) ため、性質5「自発的再割当ての禁止」を満たさない。`INTEGER PRIMARY KEY` の別名となった rowid は VACUUM に対して安定であり、**機構として**性質5を満たす (性質1の宣言と性質4の update 拒否は機構からは従わず、実装側の責務として残る)。ただし `AUTOINCREMENT` なしでは削除された最大 id を後続の insert が再利用する (実測確認済み) — これは上記「残余危険」の案i/ii/iii の選択に依存する (案i なら `AUTOINCREMENT` または UUID が必要、案ii/iii なら `INTEGER PRIMARY KEY` で足りる)。いずれも標準機能で足りる
- **r2db-api (PostgreSQL)**: 現在すべてのフィールドを型なし JSONB 列として保存しており、制約機構を持たないため変更は大きい。ただしこれは実装コストであって契約の非適用性ではない。storage 層は `field_type` の実装のためにいずれ型付き列へ作り直す必要があり、その作業と同時に行うのが最も安い

---

## CCR-14 — 制御プレーンのプロビジョニングおよび credential ライフサイクル

### 要求

共通契約に、control 権限で認証する制御プレーンの**形状と意味論**を定義する。**endpoint の提供は必須としない。** 実装は `capability_status` により可用性を申告し、提供しない実装は当該操作を `CAPABILITY_UNSUPPORTED` とする。

**形状は in-band 発行の採否 (案A/案B、後述) に依存する部分を分けて示す。** 以下は両案に共通する。

```
GET    /control/v1/capabilities                 制御面 discovery
POST   /control/v1/applications                 Application 登録
GET    /control/v1/applications                 一覧
POST   /control/v1/applications/{id}/disable    無効化
POST   /control/v1/applications/{id}/enable     有効化
GET    /control/v1/credentials                  一覧 (秘密は含まない)
POST   /control/v1/credentials/{id}/rotate      ローテート
POST   /control/v1/credentials/{id}/revoke      失効
POST   /control/v1/credentials/{id}/disable     無効化
POST   /control/v1/credentials/{id}/enable      有効化
```

**案Aを採る場合のみ**、これに発行が加わる。

```
POST   /control/v1/credentials                  発行 (秘密は一度だけ返す)
```

`lifecycle.credential` が挙げる四つの動詞のうち、案Aでは issue / rotate / revoke / disable のすべてが HTTP に表現され、案Bでは issue を除く三動詞 (と enable) が表現され、issue は bootstrap / reset の帯域外儀式に限られる。なお `enable` (disabled → enabled の復帰) は現行の `lifecycle.credential` に**無い**動詞であり、本要求は disable を可逆な運用状態とするための動詞追加を含む (変更表参照)。

**状態の意味論を固定する: `revoke` は終端であり取り消せない。`disable` / `enable` は可逆な運用状態である。** 現行契約はこの区別を一度も述べておらず、revoke を取り消せる実装は SI-13 (Revocation Effectiveness) の意味を空洞化する — 「失効した」という監査事実が後から偽になるためである。失効済み credential を再び有効にする唯一の道は新しい credential の発行である。

rotate は既存 credential の秘密を差し替える操作であり、新しい credential を作らない。**rotate の応答が成功した時点で旧秘密の失効が確定し、その伝播は `authorization_propagation_bound_ms` に従う。重複有効窓は定義しない** (窓を定義すると SI-13 の失効伝播 bound と別勘定の第二の bound が生まれる)。

**Application の削除は意図的に含まない。** v1 では disable が終端状態である。将来削除を導入する場合は SI-09 の destructive 意味論に従う別途の契約変更とし、監査の連結を切ってはならない (現行 VPS 実装の `ondelete=CASCADE` の教訓)。

### 提供を必須としない理由

設定で宣言する静的な制御プレーン (Application を構成ファイルで宣言し、動的なオンボーディングを持たない配備) は正当な選択肢である。**必要としない配備に HTTP の攻撃面を強制するのはゲートである。**

契約が定めるのは形状と意味論であり、提供するか否かは配備の判断とする。これにより、**制御手段を提供する実装は必ず同じ形で提供する**という性質は保たれる。

### 問題 — 意味論は既にあり、口だけが無い

契約は既に次を定義している。

- `security.roles` に `control` と `audit`
- `security.schemes.control_credential` — 「別途認証される Control/Audit 権限。application credential は受理しない」
- `lifecycle.credential` — control authority は credential を発行・ローテート・失効・無効化してよい
- `POST /v1/audit/query` は `auth=control or audit` として**既に存在する control 認証の HTTP endpoint** である (CCR-12 で採用済み)

すなわち「意味論は採用済みであり、それを行う口だけが未定義」という状態にある。

**乖離の数え方の訂正。** 第2版までは「三実装が三様に乖離している」と述べたが、数え方が誤っている。統治下の2 peer はいずれも HTTP 制御面を持たず (プログラム内部の `ControlAuthority` / `ControlPlane` のみ)、**公開面の乖離は現にゼロ**である。旧 VPS 実装は契約の統治外であり、乖離の数に入らない。正確に述べれば、**乖離は起きた問題ではなく見込みの問題である。** ただしその見込みには根拠がある。統治外の実装は、契約が黙っているときに制御面がどこへ行き着くかを現に示しており (下記の教訓)、統治下の2 peer が今後それぞれ制御面を持つとき、契約が黙っていれば収束すべき形が存在しない。

オンボーディングに運用者のサーバログインを要する状態が汎用データサービスと言えるかという製品上の論点は、この論拠の傍証であって主論拠ではない。

### SI-02 との関係、および同居の問題

SI-02 が制約するのは *Application-facing Runtime and Developer APIs* が到達しうる範囲である。別種の credential で認証される面は Application API ではない。`/v1/audit/query` の存在が、採用済み契約が control 権限の HTTP 面を許容することを既に示している。

**ただし SI-00 の観点で残る問題がある。** 脅威モデルは「application-facing の実装欠陥が単一で起こりうる」と仮定し、SI-00 はそれが制御プレーンを侵さないことを要求する。制御面を Application 面と同一プロセス・同一ルータ・同一ミドルウェアで提供すると、ルーティングまたは認可ミドルウェアの欠陥ひとつが、まさに「単一の application-facing 欠陥による制御プレーン侵害」となる。

一方で「別プロセス・別リスナで動かすこと」を要求すれば、内部境界を保てる単一プロセス配備を潰すゲートになる。**要求すべきは結果である。**

- 制御面は Application 面と**分離して配備可能でなければならない** (契約は同一の network endpoint / プロセスでの提供を要求しない)
- **SI-00 の適合証拠は、同居する場合にその境界がどう保たれるかに答えなければならない**

配置は自由、境界の実証は必須。base path を `/control/v1` として `/v1` から分けるのは、この分離を reverse proxy の切り出しではなく自然な単位にするためである。

### 制御面の discovery と versioning

分離配備される制御面は、`GET /v1/capabilities` が同一ホストに存在することを前提にできない。したがって:

- 制御面を提供する実装は、制御面自身の discovery (`GET /control/v1/capabilities`) を提供する
- `/control/v1` は `versioning.compatibility` と同じ互換性規則 (additive は許可、削除・意味変更は新 major version) に従う
- 既存の `GET /v1/capabilities` が `auth=application or control` であることは同居配備での便宜であり、分離配備において control credential が `/v1` 側へ到達できることを要求しない (control 面の discovery は `/control/v1/capabilities` が担う)

### 制御面の資源境界 (SI-08)

制御面は Application と credential を**生成する**面であり、SI-08 の bounded resource consumption はここにも適用される (SI-08 の resource class には schema/object creation rate or count が明示されている)。CCR-13 が冪等ストアに、CCR-15 が entity 数に境界を置くのと同様に:

- 制御面も `limits` / `limit_enforcement` を `GET /control/v1/capabilities` で公開する
- Application 数、Application あたり credential 数、制御操作レートに有限境界を要求する (クラス例: `applications` / `credentials_per_application` / `control_requests_per_minute`。値は配備 profile)

### control credential の保存と rotate (security.schemes への条項)

契約の `application_credential` scheme は「verifier/digest のみ保存、秘密を返さない」を既に明記しているが、`control_credential` scheme には同じ条項が無い。制御 credential の発行・保存を契約に載せる以上、同じ条項をここにも置く:

- 実装は control credential の**検証子のみを保存**し、秘密は発行 (または rotate) 応答で一度だけ返す
- 認証の秘密を他目的 (トークン署名鍵等) に流用してはならない (下記教訓2の契約化)

### 最後の control credential と reset

- 最後の有効な control credential の失効は**禁止しない**。侵害された credential は常に失効可能でなければならず、失効を禁止すれば「最後の1本が盗まれた場合」に失効できなくなる
- ただし明示的な確認を要する (SI-09 の destructive 意味論と同型)。なお「有効な確認とは何か」は C-06 共通化の前提として未解決の契約判断であり (MitateDB の確認トークン不検証の既知欠落)、本条項はその解決に依存する
- 復旧経路は bootstrap の reset である。reset の意味論を契約に置く: 運用者 / OS 権限のもとでのみ実行可能であり、対象は control credential のみで **Application データと監査証跡を破壊しない**こと、正準の監査イベントを発行すること
- **reset は既存の control credential をすべて失効させる。** これを欠くと、reset が「失効を生き延びる第二の発行経路」になり、案A/案B の論点だった永続性の危険が OS 権限側に残る。reset が発行する credential は bootstrap の初回 credential と同じ非恒久化規則 (下記) に従う

### control credential の in-band 発行 — 未決として両論を残す

rotate / revoke / disable を HTTP に置く論拠は成立する (「個別に失効できる」は操作手段を要する)。しかし**新しい control credential の発行**まで in-band である必然は、この論拠からは従わない。両案を依頼者判断として残す。

- **案A — 発行も in-band**: 運用が一貫し、複数運用者の追加にサーバ権限が要らない。ただし盗まれた1本から新しい credential を発行でき、**失効を生き延びる永続性**を攻撃者に与える。既存 invariant は control credential の侵害を扱っていない (SI-00 は Application credential の条項である)
- **案B — 発行は帯域外の儀式に留める** (Vault root の慣行): 永続性の危険を断つ。ただし運用者追加のたびにサーバ権限が要り、CCR-14 が解こうとした運用形態が control credential についてだけ残る

いずれを採るかで endpoint 形状 (上記) と conformance 条件が変わるため、採否と同時に判断する。

### 現行 VPS 実装からの教訓 — 三つある

1. **単一の共有パスワードで全 Application を支配してはならない。** `/admin/api/*` は環境変数の 1 パスワードで認証し、Application 単位のスコープを持たない。漏洩時に全 Application が同時に落ちる (SI-00)。失効すれば全運用が止まるため実際には失効できない (SI-13)。監査の `actor_id` が意味を持たない (SI-14)。
2. **認証の秘密を署名鍵に流用してはならない。** `admin_session.py` の署名材料は `admin_session_secret` が空のとき `admin_password` にフォールバックする。認証の秘密とトークン署名鍵が同一物になる。
3. **制御プレーンの保存物を Application 面と同居させてはならない。** 制御 DB は各 Application の DB ロールパスワードを平文で保持し、同居するプロセスから読める。Application 面の欠陥ひとつで全 Application の DB 認証情報が抜ける (SI-12、SI-00)。

副次的に、credential 記録が Application に対して `ondelete=CASCADE` であるため、Application 削除時に credential の記録ごと消え監査の連結が切れる (上記「削除は対象外」の根拠)。

### 新規 invariant は不要

上記の失敗はいずれも既存 invariant に分解できる。必要なのは新しい invariant ではなく**新しい conformance 条件**である。

- application credential が全ての control endpoint に対して fail closed であること
- control credential が data/schema endpoint で拒否されること
- bootstrap を再実行して二本目の「最初の credential」を作れないこと (明示的な reset を除く)
- reset が既存 control credential を全て失効させること
- 制御操作が正準の監査イベントを発行すること (`audit.sink_failure_policy` が既に control-plane 変更を fail-closed としている)
- 失効済み credential が `enable` で復活しないこと (revoke の終端性)
- 制御面の資源境界が `limits` として公開され enforce されること
- 「分離して配備可能」は振る舞いテストではなく設計証拠 (review evidence) として審査すること

in-band 発行の採否 (案A/案B) により conformance 条件は追加される。

### bootstrap — endpoint ではなくライフサイクル条項として

最初の control credential だけは帯域外にならざるを得ない (発行する権限を発行する経路が存在しないため)。機構は各 peer の自由 (CLI、初期化ジョブ、その他) とし、契約には次を条項として置く。

- 運用者 / OS 権限のもとで実行され、公開 HTTP 面から実行できないこと
- 既定値やハードコードされた credential が存在しないこと
- control credential が既に存在する場合、明示的な reset なしには再実行できないこと (reset の意味論は上記)
- 正準の監査イベントを発行すること
- 初回 credential が恒久化しないこと (期限またはローテート強制。機構は自由)

### 必要となる契約変更 (一覧)

| 箇所 | 変更 |
|---|---|
| `versioning` | control 面の base path `/control/v1` と、互換性規則の適用を記述 |
| `endpoints` | 上記の形状表 (案A/案B に応じた構成)。可用性は `capability_status` 申告 |
| `security.schemes.control_credential` | verifier のみ保存・秘密は一度だけ返す・他目的への流用禁止の条項を追加 |
| `lifecycle.credential` | bootstrap 条項、reset 意味論 (既存 credential 全失効を含む)、rotate の失効時点、`enable` 動詞の追加、**`revoke` の終端性と `disable`/`enable` の可逆性の明文化** |
| `limits.classes` / `limit_enforcement` | 制御面の資源境界クラス |
| `capability_status` | 制御面 capability 名 (例: `control_plane`) の規定 |

### 両 peer 適用可能性

いずれの peer も Application 登録と credential 発行の内部機構を既に持つ (r2db-api の `ControlAuthority`、MitateDB-api の `ControlPlane`)。公開経路の形状を契約で規定するのみで、内部実装と提供可否は各 peer に委ねられる。

### 採用時期 — 三つの選択肢を依頼者判断として残す

本要求の実装には、本契約の r2db-api において credential の永続化と composition root が先行する (この前提作業自体は契約変更を伴わず進行中)。第2版は「この前提条件は採用を延期する理由にはならない」と断定したが、これはレビューが不確実と明示した判断を断定に変えたものであり、改めた。三案の利害は対称に書く。

1. **全体をいま採用する** — 乖離の見込みを断ち、前提作業 (credential 記録の形、ライフサイクル状態、bootstrap) が契約に沿って行われる。**欠点**: endpoint 形状を運用経験なしに固定する。また in-band 発行 (案A/案B) の判断もこの時点で強制される (案2・案3はこれを先送りできる)
2. **安全条項のみ先に採用し、endpoint 形状は保留する** — bootstrap 規則・分離配備可能性・共有秘密の禁止・個別失効可能性・reset 意味論は運用経験に依存しないためいま採用でき、パス・動詞・req/res 形状は peer がプロセスとして起動できるようになってから確定する。**欠点**: 形状の乖離見込みは残り、契約変更が二段階になる (二度目の採否判断と conformance 改訂が要る)
3. **全体を延期する** — 統治下の公開面の乖離は現にゼロであり、緊急性は見込みに基づくため。**欠点**: 前提作業と暫定 CLI が契約の裏付けなしに形を持ち始め、事実上の先例になる危険。乖離の見込みも残る

---

## CCR-15 — entity をまたぐ atomicity

### 要求

複数の entity にまたがる mutation を、ひとつの atomic な単位として実行できる形を共通契約に定義する。**リクエスト形状は機構ではなく契約であり、形状を定義する。**

```
POST /v1/data/mutations        auth=runtime or developer
```

- リクエスト形状として **`ScopedMutationRequest` / `ScopedMutation` を新規に定義する**。`ScopedMutation` は既存 `Mutation` の全フィールドに加えて必須の `entity` フィールドを持つ。**既存の `Mutation` / `MutationRequest` 定義は一切変更しない** — `Mutation.additionalProperties` は `false` であり、共有定義に `entity` を足すと per-entity endpoint でも body の `entity` が受理されうる。path の entity と body の entity が競合する状態は、C-01 の `request_field_scope` が防ごうとしている当の攻撃面である。契約には「per-entity endpoint (`/v1/data/{entity}/mutations`) は body の `entity` フィールドを引き続き拒否する」と明記する
- `ScopedMutationRequest` の正の定義: `{operations: ScopedMutation の配列 (minItems 1、上限は既存の batch_items が束ねる), idempotency_key (任意)}`、`additionalProperties: false`。`idempotency_key` を引き継ぐのは、CCR-13 がこれを行の同一性と独立なサービス単位 Capability と位置づけたためで、cross-entity でも同じく成立する。`transaction` フィールドは**持たない** — 本 endpoint の batch は定義により atomic であり、`best_effort` は定義しない (部分結果の意味論を entity をまたいで定義する必要が生じるまで導入しない)。`additionalProperties: false` により、`transaction` を付けたリクエストは `VALIDATION_FAILED` で拒否される (未知フィールドとして)
- batch 全体がひとつの atomic 単位である。CCR-04 の failure-before-execution はまたいだ全項目に適用される — **全 entity の全操作の検証 (識別子・形状・authorization) が完了するまで、どの entity の実行も開始しない**。またぐ分だけ部分実行の誘惑が増えるため、明記する
- Capability は `cross_entity_mutation` として `capability_status` で申告し、提供しない実装は `CAPABILITY_UNSUPPORTED` で拒否する

実装がどう atomicity を実現するか (単一トランザクション、WAL、その他) は自由である。自由でないのはリクエスト形状と、次の排除である。

### 明示的に排除するもの — 対話的トランザクション

begin / commit をクライアントの往復にまたがって保持する対話的トランザクション面は**定義しない。本契約 v1 の atomic 単位は単一リクエストに限る。** ロックと接続をクライアントの往復にまたがって保持することは、敵対的クライアントに資源保持を許す SI-08 の危険であり、「堅牢と安全が第一」の軸から排除する。

**再検討条件** (排除がゲート化しないための条項。SI-08 自身が「新機能ごとの手動承認ゲートにするな」と要求している): クライアント往復にまたがる保持時間・保持資源に有限の bound を構造的に証明できる設計 (例: サーバ側 lease と強制失効) が提示された場合、別途の契約変更として審査する。それまで v1 は単一リクエスト atomic のみである。

### 問題

現行契約の mutation 経路は `POST /v1/data/{entity}/mutations` であり、**atomic な batch は単一 entity に閉じる。** `transactions.atomic` は「宣言された atomic 単位の全操作が同時に commit するか、外部から見える部分状態を残さない」と定めるが、その単位を entity をまたいで構成する手段が無い。

### 証拠

現行クライアントの `lib/actions/line_binding_relink.php` は、複数テーブルにまたがる更新に対して補償処理 (saga) を手書きしている。コード内のコメントが理由を明記している。

> r2db has no multi-row transaction, so relink keeps a state row and compensates every successful patch on error.

同様の構造は `lib/actions/month_import.php` の delete-then-insert による置換にも現れる。

**本契約どおりに実装しても、このクライアントは補償処理を書き続けることになる。** 単一 entity の atomic batch では足りないためである。

なおこの証拠は第1版において CCR-13 の証拠欄に置かれていた。誤りである。saga が示すのは行の同一性の欠落ではなく、entity をまたぐ atomicity の欠落である。

### 必要となる契約変更 (一覧)

| 箇所 | 変更 |
|---|---|
| `endpoints` | `POST /v1/data/mutations` (auth=runtime or developer) を追加 |
| `schemas` | `ScopedMutationRequest` / `ScopedMutation` を新規定義 (既存 `Mutation` / `MutationRequest` は無変更)。per-entity endpoint が body の `entity` を拒否し続けることを明記 |
| `transactions` | 単一リクエスト atomic の原則と対話的トランザクションの排除、再検討条件 |
| `limits.classes` | `batch_entities` (またぐ entity 数の class) を追加。値は配備 profile。操作数は既存の `batch_items` が引き続き束ねる |
| `capability_status` | `cross_entity_mutation` の規定 |

### Security Invariants との関係

SI-11 (Atomic Integrity) の適用範囲が広がるのみで、新たな invariant は不要と考える。SI-08 に関しては上記 `batch_entities` の有限境界を要求する。

### 両 peer 適用可能性

いずれの peer も、**ひとつの Application の保存スコープ内で**複数 entity にまたがる atomic 単位を構成できる。契約は peer の topology を断定しない (SI-00 が containment を要求し topology を要求しないのと同じ理由による)。

**Application をまたぐ atomicity は要求しない** (SI-01 の分離と両立しない)。

---

## 第2版の誤りの訂正 (記録として保持)

- **CCR-13: 無条件の普遍的 addressability は新しいゲートであった。** 再計算される読み取り専用 entity (外部表の透過、集計) はどの機構でも安定した識別子を持てず、「新しいという理由で」塞がれる。機構の自由はこれを救わない — 塞いでいたのは要求の普遍性である。可変 entity へスコープを絞った
- **CCR-13: revision の被参照先を、問題として指摘しながら固定していなかった。** 条項で固定した
- **CCR-13: SQLite rowid の引用が自らの結果を満たしていなかった。** `INTEGER PRIMARY KEY` でない rowid は `VACUUM` で振り直される (実測確認済み)
- **CCR-14: 「三実装が三様」の数え方が誤り。** 統治下の公開面の乖離はゼロであり、見込みの問題として論じ直した
- **CCR-14: 採用延期の選択肢を断定で消していた。** 三案として依頼者に戻した
- **CCR-15: 形状を提案しておらず、変更要求になっていなかった。** リクエスト形状は機構ではなく契約であり、「機構は自由」を不完全さの言い訳に使っていた

## 第3版の誤りの訂正 (第4版で実施。独立レビュー Opus による指摘)

- **CCR-13: 性質4がアドレス再利用 (ABA) を塞いでいなかった。** VACUUM 経路だけを塞ぎ、削除後の明示的 insert による再利用経路 (SQLite `INTEGER PRIMARY KEY` は削除された最大 id を再利用する — 実測確認済み) を残していた。これは第3版が自ら訂正した「引用した機構が引用した結果を満たしていない」と同じ形の再発である。性質5 (自発的再割当ての禁止) を追加し、明示的再利用の扱いは案i/案ii として依頼者判断に戻した
- **CCR-13: 「行を狙った mutation」が未定義で、追記・削除型の entity を意図せず塞ぎうた。** entity の宣言区分 (読み取り専用 / 追記専用 / 追記・削除 / 可変) で定義し直し、addressability の要求を update / upsert を支持する entity に限定した。第3版は delete を一律に trigger に含めていたが、述語による一括削除は read → address → mutate の危険を持たず、destructive 確認が既に束ねる
- **CCR-13: 「両 peer は `CAPABILITY_UNSUPPORTED` で拒否」は事実に反した。** r2db-api は拒否するが、MitateDB-api は当該フィールドを受理する面を構造的に持たない。書き分けた
- **CCR-13: 「いかなる実装も正しく実装しようがない」は言い過ぎで、より強い証拠 (r2db-api が upsert を実装の選択した意味論で enabled 申告している統治下の実状) を落としていた**
- **CCR-13: idempotency 保持境界を、指摘しながら変更表で固定していなかった** (第2版が revision で犯した欠陥と同じ形)。`limits.classes` の行として固定した
- **CCR-13: 機構列挙に性質4と両立しない内容ハッシュが混ざっていた。** 除外し、アドレスフィールドの update 拒否を性質4に固定した
- **CCR-14: 形状表が未決のはずの案A (in-band 発行) を既定として書いていた** (不確実性の断定化の変種)。共通部と案A差分に書き分けた
- **CCR-14: 制御面の資源境界 (SI-08)、control credential の保存条項、rotate の失効時点、reset による既存 credential 失効が欠けていた。** いずれも条項化した
- **CCR-14: 採用時期三案の利害が非対称だった** (案1にのみ欠点を記載)。対称に書き直した
- **CCR-15: 要求本文が自己矛盾していた** (「`Mutation` に `entity` 必須」と「`Mutation` に `entity` を追加してはならない」の併記)。`ScopedMutation` / `ScopedMutationRequest` の新規定義として書き直し、レビュー出所表示を本文から訂正欄へ移した
- **CCR-13/14/15: 変更表の欠落・不備** (CCR-14/15 に変更表が無い、`create_index` 拡張の過小見積り、capability 名の契約語彙化漏れ、サーバ採番識別子の越境推論条項の欠落、revision の他行非依存条項の欠落)。いずれも本版で補った

## 未決事項 (依頼者判断)

- CCR-13/14/15 の採否そのもの
- CCR-13: `MutationResult` の拡張を v1 で行うか。サーバ側採番の識別子を返す唯一の応答形状変更である
- CCR-13: アドレス再利用の扱い — 案i (再利用禁止を性質に含める。アドレス機構が非再利用系に限られ、性質は6つになる) / 案ii (revision precondition の領分。クライアントが晒され方を知る手段が無い) / 案iii (再利用の有無を catalog で宣言。起票側の推奨だが、宣言の真正性検査は非対称)
- CCR-14: 採用時期 — 全体採用 / 安全条項のみ先行 / 全体延期 の三案 (利害は本文に対称に記載)
- CCR-14: control credential の in-band 発行 — 案A (発行も in-band) / 案B (発行は帯域外の儀式)
- CCR-14: base path を `/control/v1` として `/v1` から分けることの確認
- CCR-15: `batch_entities` の境界値と、その enforcement layer の申告方法

**採用時に効く既知の依存** (判断項目ではないが、一覧に無いと見落とされるため記す): CCR-14 の「最後の control credential の失効には明示的な確認を要する」条項は、destructive 確認の有効性定義 (C-06 共通化の前提。MitateDB の確認トークン不検証が既知欠落) という**別の未解決の契約判断**に依存する。CCR-14 を採用しても、この定義が決まるまで当該条項は実効化しない。
