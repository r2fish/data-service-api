# conformance 条件の 1.1.0 対応 設計 (C-11〜C-16)

- 起票日: 2026-08-28
- 設計: Fable (監督・設計)。実装: Sonnet、レビュー: Opus
- 背景: CCR-13/14/15 採用と契約 1.1.0 文言化 (`spec/CCR_DISPOSITION.md` 実装順序) の次段。契約レビューが指摘した「応答を契約 schema で検証するテストが無い」(欠陥 R1 の見逃し原因) をここで塞ぐ
- 前提文書: `docs/design/CONFORMANCE_ADAPTER_V1.md`、`conformance-tests/CONDITIONS.md`

## 0. 原則 (既存設計の継承)

- port は共通リポジトリが所有し、plug は peer が所有する。**adapter は peer の不足を埋めない**
- negative test には positive control を組にする
- 「面が存在しない」主張は構造的に証明させる (署名検査)。主張を受理しない
- skip は未検証を許可に変える。実行できない条件は「not yet executable」として登録簿に正直に記す (既存 C-00/C-02 の流儀)

## 1. 新条件

| ID | 条件 | Invariants | 状態 (本作業後) |
|---|---|---|---|
| C-11 | peer が公開する discovery / catalog 文書は契約の schema (`CapabilityDocument` / `CatalogDocument` + `EntityDescriptor`) に適合し、申告される capability 名はすべて `capability_status.defined` の語彙である | SI-08, SI-15 | executable (3 adapters) |
| C-12 | capability 申告は観測可能な挙動と一致する: 申告された操作は実行でき (positive control)、申告されない操作は**実行前に** `CAPABILITY_UNSUPPORTED` で拒否され状態を変えない | SI-15, SI-05 | executable (3 adapters) |
| C-13 | credential の失効は終端である: revoke 後、peer のいかなる制御面も当該 credential を再有効化できず、authenticate は拒否され続ける | SI-13 | executable (3 adapters) |
| C-14 | control 面の権限境界: application credential は全 control endpoint に fail-closed、control credential は data/schema endpoint で拒否、`role=control` の in-band 発行要求は `CAPABILITY_UNSUPPORTED` (案B) | SI-00, SI-02, SI-03 | not yet executable (control 面の実装が両 peer に無い。実装時に executable 化する) |
| C-15 | bootstrap / reset のライフサイクル条項: 既存 control credential がある間 bootstrap は再実行不能、reset は既存 control credential を全失効、初回 credential は非恒久 | SI-13, SI-14 | not yet executable (同上) |
| C-16 | entity をまたぐ atomicity: 単一リクエスト単位、全 entity の検証が実行に先行、`batch_entities` の有限境界 | SI-08, SI-11 | not yet executable (cross_entity_mutation が両 peer で unavailable)。ただし「per-entity endpoint が body の `entity` を拒否する」は本作業で C-01 の tamper vector として実効化する (下記 §4)。**RESOLVED — 追記 (2026-08-31、フェーズ3.5 WP-3、house style — 原文は上記のまま保持)**: executable (4 adapters) へ移行済み。`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §3 (port v1.7、`test_c16_cross_entity_atomicity.py` 新設) で MitateDB 側の `cross_entity_mutation` が `partial` として実体化されたことに伴い、C-16 は MitateDB 2 adapter が PROVIDED 分岐 (V1〜V4)、r2db 2 adapter が ABSENT 分岐 (V5) を走る4 adapter executable 条件となった。詳細は `conformance-tests/CONDITIONS.md` の C-16 行を参照 |

## 2. port の改訂 (CONFORMANCE_ADAPTER_V1 の coordinated design revision)

`conformance-tests/adapter.py` に以下を追加する。3 plug すべてを同時に更新する。

```python
CATALOG_SURFACE_ABSENT = "<peer-has-no-catalog-surface>"   # sentinel

class ConformanceAdapter(ABC):
    @abstractmethod
    def catalog_document(self, session) -> Mapping[str, Any] | str:
        """peer の CatalogDocument をそのまま返す。peer が catalog を提供
        しない場合: 拒否面があるなら ConformanceDenial を送出し、操作面が
        構造的に存在しないなら CATALOG_SURFACE_ABSENT を返す。文書の捏造
        (adapter が組み立てた dict) は禁止。"""

    @abstractmethod
    def attempt_mutation(self, session, entity: str, operation: str, *,
                         values: Mapping[str, Any] | None,
                         where_field: str | None, where_value: Any) -> int:
        """mutation 語彙 (insert/update/upsert/delete) の1操作を peer に
        そのまま提示する。delete は非破壊文脈では使わない (C-12 は
        insert/update/upsert のみ exercise し、delete の申告一致は既存
        C-06 領域に残す)。拒否は ConformanceDenial。"""

    @abstractmethod
    def credential_reactivation_vectors(self, handle: CredentialHandle) -> Sequence[TamperVector]:
        """失効済み credential を再有効化しうる peer の全制御面を
        TamperVector として申告する (kind は "credential_reactivation" 固定、
        TAMPER_KINDS には追加しない — C-01 の MUST_COVER には含めない)。
        disposition の意味は C-13 で次のとおり:
        - must_deny: attempt() が ConformanceDenial を送出しなければならない
        - must_ignore: attempt() は成功してよいが、直後の authenticate が
          依然拒否されなければならない (例: enable が「disable の解除のみ」
          として no-op になる面)
        - structurally_absent: surface + forbidden_parameters の署名検査で
          再有効化面の不在を構造的に示す
        少なくとも1 vector を申告する (空の申告は fail)。"""
```

## 3. 条件テストの設計

### C-11 (`test_c11_document_conformance.py`)

- 検証器は依存を増やさず自前で書く (`conformance-tests/schema_check.py`)。対応キーワードは `type` / `required` / `properties` / `additionalProperties` / `enum` / `const` / `pattern` / `items` / `minItems` / `maxItems` / `if`+`then` / `$ref` (同一文書内) に限定。`if` は draft 規則どおり「不在プロパティに空虚に真」で実装し、**契約側が `required` を `if` に置いていることを前提にしない** (検証器が正しければ、契約側の R1 型の欠陥を将来も検出できる)
- `capability_document()` を `schemas.CapabilityDocument` に当てる。加えて: 申告 capability 名 ⊆ `capability_status.defined`、`status` ∈ `status_enum`、`limit_enforcement` の値 ∈ `enforcement_enum`
- `catalog_document()`: 文書が返れば `schemas.CatalogDocument` (entities は `EntityDescriptor`) に当てる。`ConformanceDenial` なら code は `CAPABILITY_UNSUPPORTED` かつ `application_catalog` の申告が unavailable であること。`CATALOG_SURFACE_ABSENT` なら同じく申告が unavailable であること (positive control: 少なくとも1 adapter は文書を返す — registry 全体での vacuity 防止は suite 側で assert する)
- 検証器自身の単体テストを書く (R1 型の4ケース: 宣言なし/append_only/mutable 完全/mutable 不完全)

### C-12 (`test_c12_capability_agreement.py`)

- `capability_document()` の `atomic_mutation` から「申告された操作集合」を導く (enabled → 契約の `allowed_mutations` 全部、partial → `operations` リスト、unavailable → 空)
- insert / update / upsert それぞれについて:
  - 申告あり → `attempt_mutation` が成功する (positive control)
  - 申告なし → `ConformanceDenial(code=CAPABILITY_UNSUPPORTED)` かつ **状態不変** (直前直後の `count` 一致)。さらに batch 文脈での failure-before-execution は per-adapter に強制しない (単発操作で判定する — batch 形は peer-local テスト済み)
- catalog: `application_catalog` の申告と `catalog_document()` の結果の一致 (C-11 と観点が異なる: C-11 は形、C-12 は申告との一致)
- 現時点の期待値: 両 peer とも upsert 未申告 → 拒否が必須。insert/update は申告あり → 成功が必須 (これが positive control)

### C-13 (`test_c13_revocation_terminality.py`)

- 手順: issue → authenticate 成功 (positive control) → revoke → authenticate 拒否 (`AUTH_REVOKED` または `AUTH_INVALID`) → `credential_reactivation_vectors` の各 vector を disposition どおりに評価 → **最終 authenticate が依然拒否**
- 空の vector 申告は fail (未検証を許可に変えない)

### C-14 / C-15 / C-16

- `CONDITIONS.md` に行を追加し、Status は「not yet executable (common suite)」+ 実装待ちの内容を明記。`test_conditions_register.py` の既存機構が新行を正しく扱うこと。実際の検査方向は2つ: (a) Status が `executable` で始まる行はすべて対応する `@pytest.mark.condition(...)` を持つこと、(b) 収集された suite 中の `@pytest.mark.condition(...)` id はすべて `CONDITIONS.md` に行として存在すること。C-14/15/16 は Status が `executable` で始まらないため (a) の対象外であり、marked test を持たない (b) の起点にもならない — 「持ってはならない」を積極的に検査する第三の方向はない

## 4. C-01 の強化 (C-16 の前倒し分)

`r2db-api-http` plug の `tamper_vectors` に kind `request_field_scope` の vector を1本追加する: per-entity mutation リクエストの body に `entity` フィールドを混入させ (`{"operation": "insert", "values": {...}, "entity": "<他entityや自entity>"}` を operations 要素に、または top-level に)、`must_deny` (契約 1.1.0 `endpoints.mutate.semantics`: body の entity は未知フィールドとして拒否)。in-process adapter は対象外 (HTTP body という面が存在しない — 既存 vector で kind は充足済み)。

## 5. 実装側の変更 (契約 1.1.0 の既採用条項の実装であり、先取りではない)

1. **終端 revoke の enforcement**: `auth.CredentialStore.set_state` と `credential_store.PostgresCredentialStore.set_state` は、失効済み credential への `revoked=False` を `VALIDATION_FAILED` で拒否する (「revocation is terminal」の実装)。未失効への `revoked=False` は従来どおり no-op 相当で許容。`r2db-api/tests/test_foundation.py` の un-revoke をフィクスチャ都合で使っている箇所は新規 credential 発行に書き換える
2. **stub の資源計上 (レビュー R12)**: `DataService` に `deny_unsupported(context, operation, message)` を追加 — `_slot` を通した上で `CAPABILITY_UNSUPPORTED` を送出し、拒否の audit イベントを出す。`_slot` は rate (`_acquire_rate`) と concurrency (`_active` カウンタ) の両方を計上する単一の実装経路であり、他の全 application-plane メソッド (`query`/`mutate`/`schema`/`catalog`) もこの同じ経路を通る。したがって concurrency 計上は「stub も他メソッドと同じ `_slot` を通る」という実装構造そのものによって担保され、専用の concurrency テストは追加しない。専用テストを追加するのは rate のみ (`requests_per_minute` を使い切った2回目の呼び出しが `LIMIT_EXCEEDED` になることを直接観測できるため)。`http.py` の `post_audit_query` / `post_cross_entity_mutate` は `deny_unsupported` を使う
3. **MitateDB の discovery 適合**: C-11 が要求する `CapabilityDocument` の required (`limits` / `limit_enforcement` / `authorization_propagation_bound_ms` 等) を欠いていれば、peer 実装として補う (契約が既に要求している事項)

## 6. 検出力の確認 (変異注入)

最低限次の3変異で suite が落ちることを確認して復元する (scratchpad バックアップ、`git checkout` 禁止):

1. r2db の capability 文書に契約外の capability 名 (`made_up_capability`) を足す → C-11 が落ちる
2. `structured.py` の upsert 拒否を外す (申告は unavailable のまま) → C-12 が落ちる
3. 終端 revoke の enforcement を外し、adapter の reactivation vector が un-revoke に成功する状態にする → C-13 が落ちる
