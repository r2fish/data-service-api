# 共通契約変更要求 (r2db-api 起票)

- 起票日: 2026-08-28
- 起票者: r2db-api 側設計作業
- 宛先: 共通契約 `spec/data-service-api.v1.json`
- 採否記録: `spec/CCR_DISPOSITION.md`

`MitateDB-api/contracts/COMMON_CONTRACT_CHANGE_REQUEST.md` (CCR-01〜12) と同じ様式で起票する。番号は通番を継承する。

いずれも r2db-api 固有の都合ではなく、**共通契約の欠落**として提起する。両 peer に等しく適用可能でなければ共通契約に載せるべきではない、という基準で書いている。

---

## CCR-13 — 行の同一性 (row identity)

### 要求

共通契約に、entity 内で行を一意に指し示す**同一性の概念**を導入する。具体的には (a) 同一性を構成するフィールドの宣言、(b) 一意性制約の意味論、(c) サーバ側採番の選択肢、(d) 同一性による mutation の対象指定、を定義する。

### 問題

現行契約には主キー・一意性・行識別子のいずれの概念も存在しない。一方で契約は既に次を定義している。

- `Mutation.expected_revision` — 楽観ロックによる事前条件
- `MutationRequest.idempotency_key` — 冪等なリトライ

**どちらも「どの行か」を安定して指せることを前提とする。** 同一性が無い状態でこの2つは実装できない。契約が自身の条項を実装不能にしている。

実務上も次が成立しない。

- `where` 述語だけでは「ちょうど1行を更新する」を保証できない
- 重複行の発生を防ぐ手段が無い
- delete-then-insert による置換が、途中失敗で重複を残す

### 実クライアントからの証拠

r2db-api の現行クライアント (勤務表 etc、18 テーブル) は、全テーブルで `id` 主キーによる行指定を行っている。加えて実装内に次の痕跡がある。

- `lib/line_binding_relink.php` — 「r2db に複数行トランザクションが無い」ため、失敗時に適用済み変更を逆適用する補償処理 (saga) を手書きしている
- upsert 相当は全箇所で「自然キーで検索 → 見つかれば PATCH、無ければ POST」として手実装されている。一意性制約が無いため、競合時に重複を作りうる

同一性と一意性が契約にあれば、この種の回避策の多くは不要になる。

### 両 peer 適用可能性

PostgreSQL (r2db-api)、SQLite (MitateDB-api) ともに主キーと一意性制約を持つ。実装手段は各 peer に委ねられる。

### Security Invariants との関係

SI-11 (Atomic Integrity) の retry/precondition 条項を実効化する。SI-05 の検証境界は変わらない。新たな invariant は不要と考える。

### 留意点

同一性を必須にするか任意にするかは設計判断が要る。全 entity に強制すると、キーを持たない追記専用データの表現が窮屈になる。**entity 単位で宣言可能とし、宣言しない場合は `expected_revision` / `idempotency_key` を利用不可 (`CAPABILITY_UNSUPPORTED`) とする**のが、既存条項との整合が取りやすい。

---

## CCR-14 — 制御プレーンのプロビジョニングおよび credential ライフサイクル endpoint

### 要求

共通契約に、control 権限で認証する制御プレーンの endpoint 群を定義する。

```
POST /v1/control/applications                 auth=control   Application 登録
GET  /v1/control/applications                 auth=control   一覧
POST /v1/control/applications/{id}/disable    auth=control   無効化
POST /v1/control/applications/{id}/enable     auth=control   有効化
POST /v1/control/credentials                  auth=control   発行 (秘密は一度だけ返す)
POST /v1/control/credentials/{id}/rotate      auth=control   ローテート
POST /v1/control/credentials/{id}/revoke      auth=control   失効
```

### 問題

契約は既に次を定義している。

- `security.roles` に `control` と `audit`
- `security.schemes.control_credential` — 「別途認証される Control/Audit 権限。application credential は受理しない」
- `lifecycle.credential` — 「Control authority は credential を発行・ローテート・失効・無効化してよい」
- `POST /v1/audit/query` は `auth=control or audit` として既に存在する

**すなわち control 認証の HTTP endpoint は契約上すでに正当であり、意味論も定義済みである。それを行う口だけが `endpoints` に無い。**

結果として各実装が独自の帯域外手段を発明する。現行 VPS 実装は `/admin/api/*` を単一のグローバルパスワードで公開しており、Application 単位のスコープを持たない。新実装は手段を持たない。共通契約が定めないため、両者が別物になっている。

### 汎用データサービスとしての要件

制御手段が無いと、新しい Application を載せるたびに運用者のサーバログインが必要になる。それは**特定用途の専用データベースの運用形態**であり、独立した汎用データサービスではない。共通契約が「2つの独立した実装」を成立させることを目的とする以上、オンボーディングの手段は契約に属する。

### SI-02 との関係

SI-02 が要求するのは分離であって不在ではない。

> Keep Control Plane authorization **distinct** from Application authorization.
> Prevent Application credentials from reaching Control Plane storage or privileged provisioning operations.

次を満たすことで SI-02 を保つ。

- control credential は application credential と別種であり、制御面は application credential を受理しない
- `/v1/data/*` および `/v1/schema/*` から制御面への経路が存在しない
- runtime/developer 権限は制御操作に対して fail closed
- ネットワーク面の追加分離 (別ポート、接続元制限) は実装の自由とし、契約では要求しない

### 現行実装からの教訓

**control 権限を単一の共有パスワードにしてはならない。** 現行 VPS 実装の `/admin/api/*` は環境変数の 1 パスワードで全 Application のプロビジョニングとキー発行を許す。これが漏れれば全 Application が同時に落ちる (SI-00 の封じ込めに反する)。

control credential も application credential と同様に、個別に発行・失効・期限を持つ資格情報とする。

### 監査

制御操作は SI-14 の「Control Plane administrative change」および「credential lifecycle change」に該当する。全操作が正準の監査イベントを発行することを契約で要求する。秘密値は監査に含めない (既存の `audit.forbidden_fields` が適用される)。

### 両 peer 適用可能性

いずれの peer も Application 登録と credential 発行の内部機構を既に持つ (r2db-api: `ControlAuthority`、MitateDB-api: `ControlPlane`)。公開経路を契約で規定するのみで、内部実装は各 peer に委ねられる。

---

## 起票時点での未決事項

- CCR-13 の同一性を必須とするか entity 単位の任意宣言とするか
- CCR-14 の control credential 自体の発行経路 (bootstrap をどう行うか。最初の 1 本は帯域外にならざるを得ない)
- CCR-14 を `/v1` 配下に置くか、別の base path に分けるか
