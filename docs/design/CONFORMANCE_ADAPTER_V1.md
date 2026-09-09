# 共通conformance実効化設計 v1 — peer adapter port

## 文書情報

- 版数: 1.15 (§25 を新設。port v1.15: phase 10 WP-6d-ii、design `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-13「実装の形 (6d-ii) の確定」由来の coordinated revision -- 1 新規 abstract method `hold_after_idempotency_lookup(session, idempotency_key)` (新条件 C-27、同一 idempotency key の同時送信を決定的に直列化させる primitive) と、非 normative な yield handle `IdempotencyHold` (`wait_until_held(timeout_s=30.0) -> int`) を追加する。`hold_in_flight` (port v1.12) の構造を踏襲するが、この primitive 自身は要求を出さない (呼び出し側が先着・後着の両方を別々の OS スレッドから出す) 点が唯一の構造上の違いである。既存 4 registered adapter が実現し、5・6 番目の socket plug (`r2db-api-socket`/`MitateDB-api-socket`) は http adapter の composition をそのまま継承する (socket 固有のコードは無い)。削除は無い。詳細は §25
- 版数: 1.14 (§24 を新設。port v1.14: phase 10 WP-3、design `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` D-1 (A) 4 由来の coordinated revision -- `ConformanceAdapter` に既定を持たない抽象属性 `transport_kind` (`"in_process"` / `"asgi"` / `"socket"`) を 1 個追加する。新規 abstract method は無い。既存 4 registered adapter は現状どおりの値 (`in_process` × 2、`asgi` × 2) を宣言し挙動は変わらない。5・6 番目の plug (`r2db-api-socket`/`MitateDB-api-socket`、`socket` を宣言) は本 WP では未登録 (WP-4 が登録する)。詳細は §24
- §24.3 追補 (2026-09-08, WP-3 差し戻し反映、監督裁定 `{scratchpad}/phase10/wp3-rulings.md`): port v1.14 のまま (バージョン番号は据え置き、port-level 変更なし)。`_build_client` の契約を明記 (F-2 (c): app 1個につきclient 1個。socket実装はappごとにuvicorn+nginxの対を持ってよく、1 nginxで2 upstreamを束ねる形は要求しない)。3個目の hook `_reset_surface_state(self) -> None` (既定no-op、`isolated_application_surface`が`copy.copy(self)`直後に呼ぶ) を追加 (F-2 (b))。`hold_in_flight`実現 (`_hold_in_flight_via_http_requests`/`_hold_in_flight_via_http_requests_over_stalled_gate`) も`_build_client`hookを経由するよう修正 (F-10、旧extraction が見落としていた直接構築箇所)。§24.3末尾の未実測断定を訂正 (F-7)。§24.2 に、`test_c19_surfaces_are_really_dialable_on_socket_plugs` が `registry-guards` xdist group に入ることと WP-4a の非 vacuity assert がその group を跨がない形にすべき旨の注記を追加 (F-8 (ii))。詳細は §24.3
- 版数: 1.13 (§23 を新設。port v1.13: phase 9 WP-1、design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §6.1 由来の coordinated revision -- 5 新規 abstract method (`schema_operation_with_result`/`attempt_mutation_with_result`/`attempt_batch_with_result`/`attempt_cross_entity_batch_with_result`/`query_with_budget`) を追加し、契約 1.7.0 が新設する 8 項目 (`dry_run`/`plan`/`budget`/schema `idempotency_key`/`enum`・`nullable`・`field_constraints`/結果側 `request_id`/結果側 `descriptor`/`alter_field`) を運ぶ。`alter_field` は独立 primitive ではなく `schema_operation_with_result` の `operation` 引数へ畳んだ (§23.2、監督裁定 2026-09-07)。5 限界 (i)〜(v) は `ConformanceAdapter` の class docstring に置く (WP-1b rework)。削除は無い。詳細は §23
- 版数: 1.12 (§22 を新設。port v1.12: phase 8 WP-1b、design docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-2 由来の coordinated revision -- 2 新規追加: `hold_in_flight(session, n)` (C-05 V2 の in-flight 保持 primitive、`concurrency` を初めて駆動可能にする) と `select_eq`/`attempt_filter` への `limit`/`extra_predicates` optional フィールド (L7-21、`result_items` 両側化・`query_complexity` の能力判定化)。削除は無い。詳細は §22
- 版数: 1.11 (§21 を新設。port v1.11: phase 7 WP-4、design docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md D-6 由来の coordinated revision -- 2 新規追加: `isolated_application_surface()` (C-05 V2 の隔離 data-plane primitive、`isolated_control_surface()` と対だが yield する形が異なる) と `BatchOperation`/`ScopedBatchOperation` への `idempotency_key` optional フィールド (C-07 (ii))。削除は無い。**この改訂で §19 (v1.9)/§20 (v1.10) の間に文書情報の版数行が追随していなかった欠落 (1.8 のまま) も同時に解消した** (事実のみの記録、コード変更なし — port は既に v1.10 の内容を持っていた)
- §21.4 追補 (2026-09-06, WP-5 rework round 2, 監督裁定 item 1): port v1.11 のまま (バージョン番号は据え置き)。`isolated_control_surface()` に optional keyword-only `limits_override` 引数を追加し、yield 形を bare callable から非normative `IsolatedControlHandle` (`capabilities`/`register_application`/`list_applications`) に拡張、`adapter.py` に非normative `apply_limits_override` ヘルパーを追加。`test_c14_authority_boundary.py` の `applications` vector を隔離 surface 駆動 (override 8) に変更。4 plug 実装。詳細は §21.4。
- §23.4 追補 (2026-09-07, 監督裁定 A `{scratchpad}/rulings-wp3a-review.md`): port v1.13 のまま (バージョン番号は据え置き)。`schema_operation_with_result(..., enum=...)` に tri-state sentinel `ENUM_CLEAR` (`adapter.py` モジュールレベル、`_EnumClear` 単一インスタンス) を追加し、「省略」(`None`、既定) と「明示 `enum: null`」(`ENUM_CLEAR`) を区別できるようにした。既存呼び出し (省略、または `Sequence` を渡すもの) は byte 互換のまま。4 adapter (`conformance_adapter_r2db{,_http}.py`/`conformance_adapter_mitatedb{,_http}.py`) の `schema_operation_with_result` を同型に更新し、`test_c20_constraint_declaration_agreement.py` の肯定枝に leg (9) (`alter_field(enum=ENUM_CLEAR)` で enum が解除される) を追加。詳細は §23.4。
- port v1.8: `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` phase 4 WP-1 由来の coordinated revision -- 3 新規 abstract method (`audit_query`/`flush_audit_buffer`/`audit_visibility_lag_ms`)、declare-first dispatch、`SurfaceAbsent` の意味拡張 (audit_query 専用)。全 4 registered adapter は本 WP 時点で `audit_query: unavailable` のままのため、PROVIDED 分岐は本 WP では実行されない (WP-2(b)/WP-3(b) で初実行) -- CONDITIONS.md C-09/C-11 行にこの限界を明記。**§17 (v1.7) 欠番の解消 (WP-1 コードレビュー指摘、2026-09-02)**: `conformance-tests/adapter.py` のコメントが既に "port v1.7" (`ScopedBatchOperation`/`attempt_cross_entity_batch`、phase 3.5 WP-3 由来) を名乗っているのに本文書に対応節が無い欠落を、v1.8 追記と同一改訂で §17 として backfill した (事実のみの記録、コード変更なし) — v1.8 は空き番号 §17 ではなく §18 として新設し、番号を整合させた
- 発行日: 2026-08-30 (v1.6)。§17 (v1.7 backfill) / §18 (v1.8) 追記日: 2026-09-02。§21 (v1.11) 追記日: 2026-09-06。§22 (v1.12) / §23 (v1.13) 追記日: 2026-09-07。§24 (v1.14) 追記日: 2026-09-08
- 設計担当: Opus (§1〜§11)。§12/§13 は `docs/design/R2DB_CCR13_STORAGE_V1.md` (設計: Fable) の指示に基づき、本文書 §11 の coordinated design revision 手順を実装側 (Sonnet) が適用したもの (独立レビュー: Opus)。§15 は `docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` (設計: Fable) work package WP-1 の指示に基づき、同じ coordinated design revision 手順を実装側 (Sonnet) が適用したもの。§16 は `docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` (設計: Fable) work package WP-2 の指示に基づき、同じ coordinated design revision 手順を実装側 (Sonnet) が適用したもの。§17 は `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` (設計: Fable) work package WP-3 の事実を、実装側 (Sonnet) が phase 4 WP-1 の際に事実のみ backfill したもの。§18 は `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (設計: Fable) phase 4 WP-1 の指示に基づき、同じ coordinated design revision 手順を実装側 (Sonnet) が適用したもの
- 位置づけ: `conformance-tests/` が両peer実体に対して同一condition IDを実行できるようにするための正規設計。実装はこの設計に従う。

## 1. 解決する問題

`conformance-tests/README.md` は「同一suiteが `r2db-api` と `MitateDB-api` の両方に対して実行可能でなければならない」と宣言している。しかし現状の `conformance-tests/test_contract.py` は `spec/data-service-api.v1.json` の文書形状のみを検査しており、**実体に対する振る舞い検証は一件も含まない**。

runtime証拠は各peer配下 (`r2db-api/tests/`、`MitateDB-api/tests/`) に、異なるtest名・異なる例外型・異なる前提で個別に存在する。したがって:

- condition ID (C-00〜C-10) は文書上の識別子にとどまり、実行可能な検証に接続していない。
- 片方のpeerだけが満たしている性質と、両方が満たしている性質を機械的に区別できない。
- 新しいpeerを追加したとき、何を満たせば適合なのかがコードとして存在しない。

本設計は C-01 / C-03 / C-08 を対象に、この接続を確立する。

## 2. 設計原則

1. **portは共通repositoryが所有し、plugは各peerが所有する。** 抽象interfaceと条件testは `conformance-tests/` に置く。実体への接続コードは各peer配下に置く。これにより `r2db-api` / `MitateDB-api` が共通契約の暗黙的所有者にならない (CLAUDE.md Boundaries)。
2. **portはcondition駆動で最小にする。** C-01/C-03/C-08 の検証に必要な操作のみを定義し、共通契約全体をmirrorしない。表面積を広げると、peer差分がportに漏れる。
3. **negative testには必ずpositive controlを組にする。** 「全部拒否するadapter」が自明に合格することを防ぐ。これは全条件testに適用する必須規則である。
4. **不明を沈黙で許可に変えない。** adapterが「この攻撃面は存在しない」と主張する場合、主張ではなく**構造的証明**を要求する (§4.3)。
5. **denialは共通契約の error code に正規化する。** 正規化先は `spec/data-service-api.v1.json` の `errors.codes` から読み込み、adapterの自称ではなく契約に固定する。
6. **peer間の意味論差はportで吸収し、契約差は記録する。** 吸収できない差は本設計の §8 に発見事項として残し、勝手に共通契約へ昇格させない。

## 3. 配置

```text
conformance-tests/
  adapter.py                 # port定義、Denial、TamperVector、taxonomy、必須被覆集合
  payloads.py                # injection payload corpus (共通)
  registry.json              # 登録adapterの宣言
  conftest.py                # adapter discovery、parametrized fixture、conditionマーカー
  test_contract.py           # (既存) 契約文書検査
  test_c01_scope_binding.py
  test_c03_structured_injection.py
  test_c08_revocation_boundary.py
  test_conditions_register.py  # CONDITIONS.md と実行可能testの追跡整合
r2db-api/conformance/conformance_adapter_r2db.py         # build_adapter() を公開
MitateDB-api/conformance/conformance_adapter_mitatedb.py # build_adapter() を公開
pyproject.toml                          # (新規、repository root) 統合実行設定
```

root `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["r2db-api/src", "MitateDB-api/src", "conformance-tests"]
testpaths = ["conformance-tests", "r2db-api/tests", "MitateDB-api/tests"]
markers = ["condition(cid): common conformance condition identifier"]
```

各peerの既存 pytest 実行 (`r2db-api/pyproject.toml`) は変更しない。

`registry.json`:

```json
{
  "adapters": [
    {"name": "r2db-api", "module": "conformance_adapter_r2db", "required": true},
    {"name": "MitateDB-api", "module": "conformance_adapter_mitatedb", "required": true}
  ]
}
```

module解決は `conftest.py` が各peerの `conformance/` を `sys.path` に載せて行う。**`required: true` のadapterがimportまたは構築に失敗した場合、suiteはskipせずfailする。** skipは「不明の沈黙許可」であり、原則4に反する。

## 4. port定義 (`conformance-tests/adapter.py`)

### 4.1 値型

```python
@dataclass(frozen=True)
class CredentialHandle:
    credential_ref: str      # control planeがcredentialを指すための不透明参照
    application_id: str
    role: str                # "runtime" | "developer"
    secret: str              # 合成テスト値のみ。実credentialを入れてはならない

@dataclass(frozen=True)
class ScopeView:
    application_id: str
    role: str

class ConformanceDenial(Exception):
    code: str                # spec errors.codes の要素であること
    adapter: str
    native_type: str         # native例外のクラス名 (診断用、message本文は保持しない)
```

`ConformanceDenial` は native例外の **message本文を保持しない**。保持するとassertion経由でpayload echoが見逃される。native messageの安全性はadapterの `classify()` 前に §6.3 の非echo検査で別途行う。

### 4.2 Fixture

```python
@dataclass(frozen=True)
class Fixture:
    adapter: "ConformanceAdapter"
    app_a: str
    app_b: str
    runtime_a: object        # session handle
    developer_a: object
    runtime_b: object
    shared_entity: str       # A と B の双方に同名で存在する
    a_only_entity: str       # A のみに存在する
    b_only_entity: str       # B のみに存在する
```

`shared_entity` を同名でA/B双方に作ることが重要である。「名前が違うから届かなかった」ではなく「同名でも到達できない」ことがSI-01の証拠になる。

identifier は両peerの交差集合に収まる形式 (小文字開始、`[a-z][a-z0-9_]*`) を使う。理由は §8 の発見事項2を参照。

### 4.3 TamperVector

```python
TAMPER_KINDS = ("forged_scope_object", "role_elevation",
                "request_field_scope", "cross_application_handle")

@dataclass(frozen=True)
class TamperVector:
    kind: str                # TAMPER_KINDS の要素
    name: str
    disposition: str         # "must_deny" | "must_ignore" | "structurally_absent"
    attempt: Callable[[], Any] | None = None
    surface: Sequence[Callable] | None = None
    forbidden_parameters: Sequence[str] = ()
```

disposition の意味:

- `must_deny` — `attempt()` は `ConformanceDenial` を送出しなければならない。
- `must_ignore` — `attempt()` は成功してよいが、**server-bound scopeが変化していない**こと、および改竄先applicationの状態が変化していないことを検証する。
- `structurally_absent` — 「この攻撃面はAPI上存在しない」という主張。suiteは主張を受け入れず、`surface` に挙げられた全public callableの署名を `inspect.signature` で検査し、`forbidden_parameters` のいずれの名前もparameterとして存在しないことを確認する。存在すれば失敗とする。

adapterは `MUST_COVER_TAMPER_KINDS = set(TAMPER_KINDS)` の全kindについて、少なくとも1つのvectorを返さなければならない。suiteはこの被覆を検査する。kindを省略したadapterは合格しない。

### 4.4 抽象adapter

```python
class ConformanceAdapter(ABC):
    name: str

    # --- control plane (application authorityの外) ---
    def provision_application(self, application_id: str) -> None: ...
    def issue_credential(self, application_id: str, role: str) -> CredentialHandle: ...
    def revoke_credential(self, handle: CredentialHandle) -> None: ...
    def disable_application(self, application_id: str) -> None: ...
    def enable_application(self, application_id: str) -> None: ...
    def set_authorization_state_available(self, available: bool) -> None: ...
    def propagation_bound_ms(self) -> int: ...       # 有限、>= 0

    # --- application plane ---
    def authenticate(self, handle: CredentialHandle) -> object: ...   # ConformanceDenial可
    def scope_of(self, session: object) -> ScopeView: ...
    def create_entity(self, session, entity: str, fields: Mapping[str, str]) -> None: ...
    def insert(self, session, entity: str, values: Mapping[str, Any]) -> None: ...
    def select_eq(self, session, entity: str, select: Sequence[str],
                  field: str | None, value: Any) -> list[dict]: ...
    def delete(self, session, entity: str, field: str, value: Any, *,
               destructive: bool, confirmation: str | None) -> int: ...
    def count(self, session, entity: str) -> int: ...
    def entities(self, session) -> set[str]: ...

    # --- 攻撃面の宣言 ---
    def native_command_surface(self) -> None: ...          # 必ず None を返すこと
    def public_operation_callables(self) -> Sequence[Callable]: ...
    def tamper_vectors(self, fixture: Fixture) -> Sequence[TamperVector]: ...
    def identifier_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]: ...
    def value_positions(self, fixture: Fixture) -> Mapping[str, Callable[[Any], Any]]: ...

    # --- 正規化 ---
    def classify(self, exc: BaseException) -> str: ...     # 共通 error code へ

    # --- 構築 ---
    def build_fixture(self) -> Fixture: ...
    def close(self) -> None: ...
```

field型は `{"text", "integer"}` の2種のみを共通語彙とする。両peerの交差である。

`identifier_positions` の必須被覆:

```python
MUST_COVER_IDENTIFIER_POSITIONS = {
    "entity", "select_field", "filter_field",
    "insert_field", "schema_entity", "schema_field",
}
```

各probeは payload を1つ受け取り、その位置に payload を置いた操作を実行する。suiteは全payload×全位置で denial を要求する。

`value_positions` の必須被覆:

```python
MUST_COVER_VALUE_POSITIONS = {"insert_value", "filter_value"}
```

`insert_value` probe は payload を値として書き込み、読み戻した値を返す。`filter_value` probe は payload を等値比較の右辺に置き、一致行を返す。

## 5. condition test 設計

全testに `@pytest.mark.condition("C-0x")` を付し、`adapter` fixtureでparametrizeする。test IDにadapter名が入ることで、どのpeerで落ちたかが即座に分かる。

### 5.1 C-01 — scope改竄 (SI-01, SI-06)

`test_c01_scope_binding.py`

1. **positive control** — `runtime_a` は `shared_entity` に対する正当な read/write が成功し、`scope_of(runtime_a) == ScopeView(app_a, "runtime")` である。
2. **tamper vector 被覆** — `tamper_vectors(fixture)` が `MUST_COVER_TAMPER_KINDS` を全て含む。
3. **must_deny vector** — 各vectorが `ConformanceDenial` を送出し、`code` が `{"SCOPE_MISMATCH", "AUTH_INVALID", "FORBIDDEN", "AUTH_REQUIRED", "NOT_FOUND", "VALIDATION_FAILED"}` に含まれる。
4. **must_ignore vector** — 実行後も `scope_of(session)` が不変であり、`app_b` 側の行数・entity集合が不変である。
5. **structurally_absent vector** — §4.3 の署名検査。
6. **role非昇格** — `runtime_a` を `developer` と自称させた状態でschema操作を試み、拒否されること、かつ `entities(developer_a)` が不変であること。
7. **cross-application非到達** — `runtime_a` から `b_only_entity` への read / write / delete が全て失敗し、かつ `runtime_b` から見た `b_only_entity` の行数が不変であること。
8. **存在差の非開示** — `runtime_a` から `b_only_entity` を触ったときの denial code が、`runtime_a` から完全な不在名 (`nonexistent_entity_xyz`) を触ったときの denial code と**同一**であること。異なると、他application上のentity存在を推測できる。

項目8は現行の両peerで満たされる見込みだが、満たさない場合はSI-01の「enumerate、infer sensitive contents of」に対する実際の欠陥であり、実装修正の対象とする。

### 5.2 C-03 — structured injection (SI-04, SI-05)

`test_c03_structured_injection.py`

1. **positive control** — 正当な entity / field / value による create → insert → select_eq → delete の一巡が成功する。
2. **native command surface不在** — `native_command_surface() is None`。加えて `public_operation_callables()` の全署名に `sql|query_text|statement|command|script|raw|expression|native` のいずれの名前を含むparameterも存在しない。
3. **identifier位置の拒否** — `MUST_COVER_IDENTIFIER_POSITIONS` の全位置 × `IDENTIFIER_PAYLOADS` + `NON_STRING_IDENTIFIERS` の全payloadで `ConformanceDenial` が送出され、`code` が `{"IDENTIFIER_INVALID", "VALIDATION_FAILED", "NOT_FOUND"}` に含まれる。
4. **value位置の binding証明** — `MUST_COVER_VALUE_POSITIONS` の全位置 × `VALUE_PAYLOADS` について、次のいずれかであること:
   - payloadが**バイト等価で往復する** (書いた値がそのまま読み戻る、比較が一致する)、または
   - 分類済み `ConformanceDenial` として拒否される。

   **黙って改変・切り詰め・正規化されることは失格とする。** これがparameter binding境界の実効的なAPI-level証明である。
5. **構造完全性** — 上記corpus全実行の前後で `entities(session)` と `count(session, shared_entity)` が不変であること。injection payloadが1件でも実行に至れば、この不変性が壊れる。
6. **payload非echo** — 全denialについて、native例外の `str()` にpayload文字列が逐語的に含まれないこと。安全なfield-level診断は契約上許容されるが、攻撃payloadの逐語反射は許容しない。

### 5.3 C-08 — revoke境界 (SI-13, SI-15)

`test_c08_revocation_boundary.py`

1. **positive control** — `runtime_a` の操作が成功する。
2. **既存sessionの停止** — credential revoke後、**既にauthenticate済みのsession handle**での次操作が `AUTH_REVOKED` (または `AUTH_INVALID`) で拒否される。新規authenticateの拒否だけでは不十分である。「以前有効だっただけのsessionを無期限に使わせない」がSI-13の要求である。
3. **再認証の拒否** — revoke済みsecretでの `authenticate` が拒否される。
4. **application disable の波及** — `app_a` をdisableすると、`app_a` の**revokeされていない別credential**のsessionも拒否される (`APPLICATION_DISABLED` / `AUTH_INVALID`)。
5. **封じ込め (過剰失敗の否定)** — 項目4の状態で `runtime_b` は正常に動作し続ける。片方のapplication停止が他へ波及しないこと。
6. **enable後の非復活** — `app_a` をenableに戻したとき、通常credentialは復帰するが、**revoke済みcredentialは復帰しない**。
7. **authorization state不可用時のfail-closed** — `set_authorization_state_available(False)` の下で、新規authenticateも**既存session操作**も `AUTH_STATE_UNAVAILABLE` (または `SERVICE_UNAVAILABLE`) で拒否される。cachedな許可へfallbackしないこと。復旧後は正常動作に戻る。
8. **伝播boundの有限性** — `propagation_bound_ms()` が `int` かつ `>= 0` の有限値である。加えて §7 の契約追加により、adapterのcapability documentがこの値を公開していることを検査する。
9. **冪等性** — 同一credentialの二重revoke、disable済みapplicationの再disableが、拒否状態を緩めないこと。

## 6. 正規化と共通語彙

### 6.1 error code正規化

`classify(exc)` の戻り値は `spec/data-service-api.v1.json` の `errors.codes` に含まれなければならない。suiteはこれを実行時に検査する。adapterが契約外のcodeを返した時点で失格とする。

`r2db-api` は既に `FoundationError.code` が契約codeであるため恒等写像に近い。`MitateDB-api` は型ベースの写像を実装する:

| MitateDB例外 | 共通code |
|---|---|
| `AuthenticationError` | `AUTH_INVALID` |
| `AuthorizationStateUnavailable` | `AUTH_STATE_UNAVAILABLE` |
| `AuthorizationError` | `FORBIDDEN` |
| `ValidationError` | `VALIDATION_FAILED` |
| `ResourceLimitError` | `LIMIT_EXCEEDED` |
| `ConflictError` | `CONFLICT` |
| `NotFoundError` | `NOT_FOUND` |

`AUTH_REVOKED` / `APPLICATION_DISABLED` を `MitateDB-api` は型として区別しない。これは §8 の発見事項1として記録し、C-08 の受理codeを `{"AUTH_REVOKED", "AUTH_INVALID"}` / `{"APPLICATION_DISABLED", "AUTH_INVALID"}` の集合とすることで、共通suiteは「拒否されること」を要求し「code粒度」は要求しない。粒度の統一は別途契約判断とする。

### 6.2 payload corpus (`payloads.py`)

`IDENTIFIER_PAYLOADS` には最低限、次の分類を各1件以上含めること: statement終端 (`;`)、comment開始 (`--`, `/* */`)、quote脱出 (`'`, `"`)、tautology (`' OR '1'='1`)、識別子quote記法 (backtick、bracket)、改行埋め込み、NUL埋め込み、空白埋め込み、修飾名 (`a.b`)、wildcard (`*`)、空文字、数字開始、長大文字列 (300文字)、非ASCII、全角。

`NON_STRING_IDENTIFIERS`: `None`, `0`, `1`, `True`, `[]`, `{}`, `1.5`。

`VALUE_PAYLOADS` には statement断片、format placeholder (`%s`, `?`, `$1`)、template記法 (`{{7*7}}`)、NULバイト、改行、非ASCIIを含める。

### 6.3 非echo検査

denialから native例外の `str()` を取り出し、payloadの逐語一致を検査する。この検査は `ConformanceDenial` への変換**前**に行う (§4.1)。

## 7. 契約側の小規模追加

`spec/data-service-api.v1.json` の `lifecycle.propagation_bound` は「各deploymentが有限の伝播boundをprofileで公開する」ことを要求しているが、`CapabilityDocument` schemaにはその値を置く場所がない。契約文言と機械可読形状が一致していない。

追加 (additive、v1互換の範囲):

- `CapabilityDocument.properties` に `authorization_propagation_bound_ms` (`{"type": "integer", "minimum": 0}`) を追加する。
- `CapabilityDocument.required` に追加する。**required化は既存実装に変更を強制する**が、公開されない伝播boundはSI-13の検証を不可能にするため、v1の欠落修正として扱う。
- `r2db-api` の `DataService.capabilities()` にこの値を含める。

これは CCR-10 で既に採用済みの意味論を機械可読にするだけであり、新しいCCRを要しない。ただし `required` 追加は契約形状の変更であるため、レビュー時に明示的に判断する。

## 8. 発見事項 (本設計で吸収せず記録する)

1. **`MitateDB-api` は revoke / disable / expiry を型で区別しない。** 全て `AuthenticationError` になる。SI-13は「拒否されること」を要求しSI-10は過剰開示を禁じるため、粒度の低さ自体は不適合ではない。ただし共通errorsは `AUTH_REVOKED` と `APPLICATION_DISABLED` を別codeとして定義しており、HTTP adapter化の時点で粒度差が表面化する。共通suiteは今回codeの集合一致にとどめ、粒度統一は契約判断へ回す。
2. **識別子構文の差。** 共通契約は `^[A-Za-z_][A-Za-z0-9_]*$`、`MitateDB-api` は `^[a-z][a-z0-9_]{0,62}$`。契約は「implementation may apply a stricter known-catalog policy」を明示的に許容しているため適合である。共通suiteは交差集合のみを使う。
3. **`MitateDB-api` の `CredentialStore.revoke()` は未知credential IDを黙って無視する。** これは control plane 側の fail-open である。運用者がrevokeしたと信じたcredentialが実際には有効なまま残りうる。共通invariantの違反ではない (application planeの性質ではない) が、実装局所の堅牢性欠陥として `MitateDB-api` 側で修正すべきである。本phaseの実装範囲に含める。
4. **`r2db-api` には credential expiry が無い。** `MitateDB-api` には `expires_at` がある。C-08 の核には不要のため今回は扱わない。共通契約の `lifecycle.credential` は expiry を必須化していない。

## 9. 完了条件

- `pytest` をrepository rootで実行すると、C-01 / C-03 / C-08 の全testが **両adapterに対して** parametrizeされて実行され、全て成功する。
- `registry.json` の `required` adapterがimport不能な場合、suiteはskipではなくfailする。
- `test_conditions_register.py` が、`CONDITIONS.md` で `executable` と宣言された全condition IDに対応するmarked testの存在と、marked testの全IDが `CONDITIONS.md` に存在することを検査し、成功する。
- `CONDITIONS.md` に status列が追加され、C-01/C-03/C-08 が `executable (both peers)` として記録される。
- `security/CONTROL_MAPPING.md` の SI-01 / SI-04 / SI-05 / SI-06 / SI-13 / SI-15 行の「Common conformance evidence」列が、抽象的な語ではなく実際のtestファイル・test名を指す。
- `conformance-tests/README.md` に「新しいpeerを追加する手順」が記載される。
- 発見事項3 (`MitateDB-api` revoke fail-open) が修正され、未知credential IDのrevokeが拒否またはaudit記録されること。
- 既存test (`r2db-api/tests/`、`MitateDB-api/tests/`、`conformance-tests/test_contract.py`) が全て引き続き成功する。
- 実credential・実host名・実データを一切含まない (CLAUDE.md 公開Repository Security Gate)。

## 10. v1.1 修正 (実装レビュー由来)

初回実装のレビューで、suite自身の完全性を損なう3件の欠陥が判明した。いずれも「testが通る」ことを優先して検証力を落とす方向の妥協であり、conformance suiteとしては最も危険な失敗様式である。port側を修正して構造的に防ぐ。

### 10.1 destructive確認の素通し (VALID_CONFIRMATION)

初回実装のadapterは `delete()` の `destructive` / `confirmation` 引数を無視し、常にpeer固有の確認トークンを送っていた。結果:

- portのdestructive意味論が装飾になり、C-06 を将来この port 上で正直に表現できない。
- C-01 の cross-application delete negative test は `destructive=False, confirmation=None` を渡すが、adapterがこれを完全なdestructive deleteへ**昇格**させていた。scope検査が退行した瞬間に、negative testが他applicationの実データを削除する。

原因はpeer間で確認トークンの綴りが異なること (`r2db-api` はリテラル `"DELETE"`、`MitateDB-api` は boolean `confirm`) である。portは綴りではなく**意図**を正規化する:

| `confirmation` | adapterの動作 |
|---|---|
| `None` | 確認を一切付けずにpeerへ渡す |
| `VALID_CONFIRMATION` (sentinel) | そのpeerが要求する正規トークンを補って渡す |
| その他の文字列 | 逐語でpeerへ渡す (誤トークン検証用、C-06で使用) |

`destructive` は常に忠実に渡す。**adapterが非destructive要求をdestructive要求へ昇格させることを禁じる。**

### 10.2 native例外のlaundering禁止 (UNCLASSIFIED)

初回実装の `classify()` は、peer固有error以外の任意のnative例外 (`sqlite3.Error`、`TypeError` 等) を `VALIDATION_FAILED` へ写像していた。これは **injection payloadでpeerがcrashした場合に、そのcrashを正常な拒否として合格させる**。C-03が捕まえるべき当のものを隠す。

修正:

- adapterはpeer自身のerror基底クラスのみを捕捉して `ConformanceDenial` に変換する。
- それ以外のnative例外は `UNCLASSIFIED` (契約 `errors.codes` に含まれない値) へ写像する。suiteのcode所属検査が自然に失敗し、findingとして表面化する。
- storage driver由来の生errorがAPI境界へ漏れること自体が SI-10 の懸念であり、隠すのではなく報告する。

### 10.3 表現不能payloadの扱い (PayloadNotExpressible)

`{[]: value}` のようにunhashable payloadをmapping keyへ置く位置では、requestをPythonで**構築すらできない**。これはpeerの検証性質ではなくharnessの制約である。初回実装はこれを `TypeError` → `VALIDATION_FAILED` として合格させていた (10.2と同根)。

修正: probeは `PayloadNotExpressible(position, payload, reason)` を送出する。suiteはこれを「この位置ではこのpayloadを観測できなかった」として記録し、**別途、全payloadが少なくとも1つの位置で拒否されていること**を要求する。位置ごとの取りこぼしが全体の取りこぼしにならないようにする。

### 10.4 非echo検査の誤検知抑制

`assert_no_payload_echo` は非文字列payloadの `repr()` や1文字payload (`"*"`) まで照合していた。契約が明示的に許容する安全なfield-level診断に対して誤検知する。文字列payloadかつ4文字以上のみを対象とする。

### 10.5 adapterによる実装欠陥の代償を禁じる

初回実装は `r2db-api` の `DataService.authenticate()` が application-disabled を検査しない点を、adapter内で private な `_check()` を呼ぶことで補っていた。これはportの役目ではない。**adapterはpeerの振る舞いを忠実に写すものであり、peerの不足を埋めてはならない。** 埋めた瞬間、suiteは実体ではなくadapterを検証することになる。

契約 `lifecycle.application` は「disabled Applicationは全てのapplication-facing操作を拒否する」と定めており、`authenticate` はapplication-facing操作である。したがってこれは `r2db-api` 側の実装欠陥であり、`r2db-api` 側で修正する。

### 10.6 実装から表面化した適合上の欠陥

- **`r2db-api` の識別子に長さ上限がない。** `structured.py` の `IDENTIFIER` 正規表現は構文のみを見ており、300文字の識別子が新規entity/field名として受理される。`MitateDB-api` は63文字で境界を持つ。PostgreSQLのidentifier上限も63であり、SI-08 の「全適用資源クラスに有限bound」に照らして欠陥である。`r2db-api` 側で修正する。

この欠陥は共通suiteが実体に対して初めて実行された結果として検出された。conformance実効化の目的がそのまま達成された事例であり、記録として残す。

- **`MitateDB-api` の destructive確認がトークンを検証しない。** `cell.py` の `delete()` は `if not confirm:` のみで判定するため、**任意のtruthy値が有効な確認として受理される**。実測で `confirm="not-the-real-token"` による削除成功を確認した。`r2db-api` は `confirmation != "DELETE"` を `DESTRUCTIVE_CONFIRMATION_REQUIRED` で拒否する。共通契約の `Mutation.confirmation` は `{"type": "string"}` であり、HTTP境界では**任意の非空文字列が確認として通る**ことを意味する。SI-09「ambiguous requests do not execute」に照らして欠陥である。

  ただし修正には「有効な確認とは何か」の契約判断が要る (r2db は操作別の固定トークン `DELETE` / `DROP_ENTITY` を使うが、共通契約はトークン値を規定していない)。実装固有の振る舞いを共通契約の決定なしに持ち込まない (CLAUDE.md Boundaries) ため、本phaseでは修正せず記録する。**C-06 の共通suite化の前提条件**として扱う。

### 10.7 suiteの検出力検証 (mutation test)

「通るsuite」が「検出できるsuite」であることを確認するため、実装へ意図的な退行を入れて検出を確認した。

| 変異 | 期待 | 結果 |
|---|---|---|
| M1 `r2db` `assert_active` の application_id/role 比較を削除 | C-01 が検出 | 検出 (1 failed) |
| M2 `r2db` 識別子長boundを削除 | C-03 が検出 | 検出 (2 failed) |
| M3 `r2db` `assert_active` の revoked 検査を削除 | C-08 が検出 | 検出 (2 failed) |
| M4 `MitateDB` `delete()` の確認gateを削除 | 検出されない (C-06 は本phase範囲外) | 検出されず |

M1が1件のみの失敗にとどまるのは、`assert_active` が record 由来の canonical context を返すため、比較を消しても scope 自体は server-bound のまま残り、`must_deny` から `must_ignore` への降格として現れるためである。r2db の server-binding が構造的に堅牢であることの傍証でもある。

M4は本phaseの範囲境界を正直に示している。C-06 を共通suite化するまで、destructive確認の検出力は無い。

### 10.7.1 Phase B レビュー由来の mutation test (M5〜M11)

`r2db-api-http` adapter (実HTTP + PostgreSQL) の追加を受け、レビューではM1〜M4の対象を超えて、この新しい実体経路と suite 自身の完全性検証を対象に追加の mutation を投入した。結果は以下の通り (verbatim、再実行・言い換えなし)。番号 M7 は欠番ではなく、レビュー時に検討されたが実装に投入されなかった候補のため付番のみ予約されている。

| Mutation | Expectation | Result |
|---|---|---|
| M5 packaged contract copy drifts from `spec/` | drift guard detects | detected (1 failed) |
| M6 `PostgresCell` stops enabling/forcing RLS on new entity tables | PostgreSQL suite detects | detected (1 failed) |
| M8 shared identifier validator weakened to `^.*$` | both backends detect | **initially NOT detected by the PostgreSQL suite (25 passed)** — see below; after the fix, 90 failed |
| M9 HTTP layer honours an `X-Application-Id` header overriding scope | ? | not detected — and correctly so: `CredentialStore.assert_active` rejects with `SCOPE_MISMATCH` (403). Verified by direct request. Defence in depth; nothing was broken |
| M10 `assert_active` stops rejecting revoked credentials | in-process detects | detected for `[r2db-api]`; not for `[r2db-api-http]`, because over HTTP every request re-authenticates through `CredentialStore.authenticate`, which has its own revocation check — a different guard, same property |
| M11 a later `required` adapter fails to import | suite fails, no resource leak | suite failed (not skipped); no PostgreSQL residue |

M9は「検出されないことが正しい」という、M1〜M8/M10/M11とは異なる読み方を要する結果である。tamper vectorとして観測される事象自体は起きている (`X-Application-Id` headerがserverに読まれる余地は無い) が、それを検証する別のdefence-in-depth層 (`CredentialStore.assert_active` の `SCOPE_MISMATCH`) が先に働くため、suiteはこのvectorについて「壊れている」という結果を出さない。これはsuiteの穴ではなく、多層防御が層として機能していることの確認である。

M10は grain の異なる二つの正しい結果である。in-process adapterでは `assert_active` 自体がrevocation検査の唯一の経路であるため、そこを壊せば直接検出される。HTTP adapterでは、経路が異なる (`DataService.authenticate` 経由で毎回`CredentialStore.authenticate`を通る) ため、`assert_active`側の検査を壊しても別の検査が同じ性質を担保し続ける。「検出されない」ことは欠陥ではなく、同じproperty (SI-13) を担保する独立したguardが複数存在することの記録である。

M8の詳細な原因分析と修正内容は §10.8 を参照。

### 10.8 Phase B レビューで発見された実装欠陥

「通るsuite」を装備するmutation testが、実際に2件の実装欠陥を発見した。いずれも「suiteは通っていたが、実際には検証していなかった」という、conformance suiteとして最も警戒すべき失敗様式である。

**M8の発見: DDL経路の識別子検証が未検証だった。** `r2db-api/tests/test_postgres.py` の識別子injection testは、read経路 (`query`/`select_eq` など) のみを対象にしていた。read経路では、`PostgresCell` が識別子をSQLへ合成する前に必ず `_load_catalog` (`information_schema` に対する照合) を通すため、たとえ構文allowlist (`structured.validate_identifier`) を完全に破壊しても、未知の識別子はcatalog照合の段階で独立に拒否される。結果として、識別子構文バリデータを `^.*$` (=何でも通す) へ弱体化させても、read経路のtestは何も気づかずに通過した (25 passed)。

一方、`create_entity`/`add_field` のようなDDL経路では、識別子は定義上まだcatalogに存在しない新規名であるため、catalog照合はそもそも救済にならない。この経路は元のtest群に含まれておらず、未検証のまま残っていた。

これは実際のinjection脆弱性ではない: `PostgresCell` は識別子を常に `psycopg.sql.Identifier` で合成しており安全にquoteされる。corpus中の全payloadを実際にDDL経路へ投入して確認したが、いずれも実行には成功せず、単に奇妙な名前のtableが作られるだけだった (例: `'; DROP TABLE items; --` はテーブル名の一部として解釈され、別文としては実行されない)。しかし、契約が定めるSI-05の識別子ポリシーが構文バリデータ側で沈黙裏に迂回可能であり、既存suiteはそれに気づけなかったという点で、これは実在するテスト完全性の欠陥である。

修正: DDL経路 (`create_entity`/`add_field`) の識別子injection testを`test_postgres.py`に追加し、構文的に不正なpayloadについては `IDENTIFIER_INVALID` を具体的に要求するようにした。修正後、同じ mutation (バリデータを `^.*$` へ弱体化) を再投入すると 90 failed となり、DDL経路を含む全体が確実に検出するようになったことを確認している。

なお、共通suite側の C-03 (`conformance-tests/test_c03_structured_injection.py`) は `identifier_positions` の必須被覆に `schema_entity`/`schema_field` (=DDL経路) を最初から含んでいたため、この欠陥はr2db-api peer-local suiteだけの穴であり、共通suiteはこの欠陥発生時点でも broader だった。

**cluster残留の発見: 異常終了経路でPostgreSQLオブジェクトが残留する。** `r2db-api-http` conformance adapterは、正常な `close()` 経路でのみ teardown を行っていた。テスト中に例外で異常終了した場合や、`conftest.py` が後続の `required` adapter の構築失敗を理由にsuite全体を止めた場合、既に構築済みだったadapterの `close()` が一度も呼ばれず、それが作成したplatform databaseとcluster-globalなroleがローカルclusterに孤児として残ることを確認した。

修正は二段。(1) `conformance_adapter_r2db_http.py` に idempotentな `atexit` safety net を追加し、インスタンス構築直後から登録することで、`close()` を経ない異常終了でもプロセス終了時に teardown が走るようにした。加えて、次回起動時に前回実行分の残留を一掃する起動時sweep (`_sweep_stale_artifacts`) を追加し、`SIGKILL` 等 Pythonのcleanupコード自体が一切走らない終了様式にも対応した。(2) 根本原因である harness 側の欠陥 -- `conformance-tests/conftest.py` が、後続の `required` adapter が構築に失敗した際、それより前に構築済みだった adapter を `close()` せずに例外を送出していた点 -- を別途修正し、失敗時には既に構築済みの adapter を全て `close()` してから raise するようにした。

### 10.9 backend間の意味論差 (記録、欠陥ではない)

C-03のvalue position corpusに含まれる NUL byte payload (`nul_byte`: `"value\x00tail"`) は、`ApplicationCell` (in-memory) では値としてそのままbyte-equalに往復する。`PostgresCell` では同じpayloadが分類済み `ConformanceDenial` として拒否される: JSONBはNUL byte (`\x00`) を含むテキストを表現できないため (PostgreSQLの制約であり、`PostgresCell`固有の検証ではない)、値をJSONBへ書き込む時点でPostgreSQL自身がエラーを返し、これを安全に分類して拒否する。

C-03の value position 要件 (design §5.2 項目4) は、「byte-equalに往復する」か「分類済み denial として拒否される」のいずれかであることを要求しており、両方とも許容される。したがってこれはC-03を通過する。これは実装欠陥ではなく、Security Invariantsが明示的に許容する、backend間の正当な物理データモデル差 (`postgres.py` モジュールdocstring既述の JSONB 順序意味論差と同種) として記録する。

## 11. v1.1 port revision (coordinated with docs/design/CONFORMANCE_CONDITIONS_V1_1.md)

`docs/design/CONFORMANCE_CONDITIONS_V1_1.md` raises C-11 (discovery/catalog
document conformance), C-12 (capability declaration agreement), and C-13
(credential revocation terminality) on this same port/plug design, and
strengthens C-01 with one additional tamper vector. Making those three
conditions executable required three coordinated additions to the
NORMATIVE surface this document's §4 defines. Per this document's own
design principle 1 (port owned by the common repository, plug owned by
each peer) and principle 4 (uncertainty must not silently become
permission), these are ABC-level additions to `conformance-tests/
adapter.py`, implemented identically in shape -- though not identically in
behavior, since peers differ -- across all three registered plugs
(`conformance_adapter_r2db.py`, `conformance_adapter_r2db_http.py`,
`conformance_adapter_mitatedb.py`) in the same change. No plug was left
with a stub or a `NotImplementedError`: every plug either performs the
real operation against its peer, or -- where a peer structurally has no
surface for it -- says so through the sentinel/`structurally_absent`
mechanisms below, never by fabricating a value on the peer's behalf.

### 11.1 `catalog_document(self, session)`

Returns the peer's own real `CatalogDocument`, the way an authenticated
application caller would observe it -- not a document the adapter
assembles from other calls. Two peers (`r2db-api`, both plugs) have a real,
present catalog surface (`DataService.catalog()` in-process, `GET /v1/
catalog` over HTTP) and return it unmodified. `MitateDB-api` has no catalog
operation anywhere on its public surface at all (confirmed by source
inspection of `cell.py`/`service.py`; its own `capabilities()` already
declares `application_catalog: unavailable`), so its plug returns a new
sentinel, `CATALOG_SURFACE_ABSENT`, rather than assembling a
`CatalogDocument`-shaped dict out of the private `sqlite_master` reach-
around its `entities()` port method already uses for its own, narrower
purpose. This is why the sentinel exists as a third outcome alongside "a
real document" and "a `ConformanceDenial`": a peer's discovery surface can
genuinely not exist, as opposed to existing and refusing one particular
request.

### 11.2 `attempt_mutation(self, session, entity, operation, *, values, where_field, where_value)`

Presents one operation from the mutation vocabulary (`insert`/`update`/
`upsert`/`delete`) to the peer exactly as a real client would, returning
rows affected. `r2db-api` (both plugs) has a single, real dispatcher that
already accepts an `operation` string this way (`DataService.mutate` /
`POST /v1/data/{entity}/mutations`), so both plugs pass the request
straight through. `MitateDB-api` has no such generic dispatcher --
`insert`/`update`/`delete` are three separate typed methods, and there is
no `upsert` method or `"upsert"`-accepting branch anywhere on the peer at
all (confirmed by source inspection; its `ApplicationCell.transact`'s own
operation-type dispatch accepts only `"insert"`). Its plug therefore
dispatches `insert`/`update`/`delete` to the corresponding real method, and
for `upsert` denies directly with `ConformanceDenial(code=
"CAPABILITY_UNSUPPORTED", ...)` rather than inventing a call: there is
truly no path on this peer's real, observable surface to even attempt that
operation, which is the honest meaning of `CAPABILITY_UNSUPPORTED` in the
first place, not a workaround for an adapter gap.

### 11.3 `credential_reactivation_vectors(self, handle)`

Declares every control-plane surface of the peer that could conceivably
re-activate an already-revoked credential, using the same `TamperVector`
dataclass as `tamper_vectors` with a new, C-13-specific fixed `kind`,
`"credential_reactivation"` (deliberately outside `TAMPER_KINDS` /
`MUST_COVER_TAMPER_KINDS`, since it is not part of C-01's taxonomy). Both
`r2db-api` plugs declare the same two vectors, matching the one real
control surface this peer has (`ControlAuthority.set_credential_state` /
`PostgresCredentialStore.set_state`, both taking independent `enabled`/
`revoked` booleans): a direct `revoked=False` attempt (`must_deny`, backed
by the terminal-revoke enforcement added in `docs/design/
CONFORMANCE_CONDITIONS_V1_1.md` §5), and an `enabled=True` attempt after
revoke (`must_ignore` -- this succeeds, since `enabled` is a distinct,
non-terminal flag, but must not actually let the credential authenticate
again). `MitateDB-api`'s `CredentialStore` (`auth.py`) has no un-revoke/
enable-credential call of any kind -- `revoke()` is one-way, and the only
other credential-touching call, `issue()`, always mints a brand-new
`credential_id` with no parameter to force reuse of an existing one -- so
its plug declares one `must_deny` vector against the one real, adjacent
surface worth checking behaviorally (`enable_application` after revoke
must not resurrect the credential, since applications and credentials are
independent flags on this peer) plus one `structurally_absent` vector
proving, by signature inspection of the entire `CredentialStore` surface,
that no method accepts an `enabled`/`revoked`/`reactivate`-shaped
parameter at all.

### 11.4 C-01 strengthening: `http_smuggled_entity_field_in_mutation_operation_body`

One new `tamper_vectors()` vector was added to `conformance_adapter_r2db_http.py`
only (design docs/design/CONFORMANCE_CONDITIONS_V1_1.md §4, a pull-forward
of one C-16 vector): a per-entity mutation request whose body smuggles an
`entity` field inside one *operation* dict of `operations`, distinct from
the pre-existing top-level `application_id`-smuggling vector. This is
`must_deny`, kind `request_field_scope`, and is HTTP-only: it is a real
JSON-body-shape probe with no in-process equivalent (the in-process plug
has no HTTP body to smuggle a field into at all; its existing
`request_field_scope` vector already covers the kind through a different,
in-process-appropriate probe), so `conformance_adapter_r2db.py` and
`conformance_adapter_mitatedb.py` are unchanged by this specific addition.

## 12. v1.2 port revision (coordinated with docs/design/R2DB_CCR13_STORAGE_V1.md work package WP-1)

`docs/design/R2DB_CCR13_STORAGE_V1.md` §4 raises C-17 (declaration/
addressability/uniqueness agreement) and C-18 (revision-precondition
semantics) on this same port/plug design, both registered in
`conformance-tests/CONDITIONS.md` as `not yet executable` -- their test
files are deliberately deferred to that design's work package WP-5, since
no registered peer implements the behavior they would exercise yet
(`docs/design/R2DB_CCR13_STORAGE_V1.md`'s own correction m-8: a
condition's port primitives may be readied ahead of the peer
implementation they will one day exercise, but the *test* itself must wait
until there is a real, non-vacuous case to run it against). What WP-1
*does* do now, per this
document's own design principle 1 (port owned by the common repository,
plug owned by each peer) and principle 4 (uncertainty must not silently
become permission), is a coordinated revision across the NORMATIVE surface
this document's §4 defines and all three registered plugs
(`conformance_adapter_r2db.py`, `conformance_adapter_r2db_http.py`,
`conformance_adapter_mitatedb.py`), in the same change, exactly as §11 did
for C-11/C-12/C-13.

### 12.1 Reserved field names: common fixtures/probes must not use `id`

`r2db-api` reserves the field name `id` (its server-assigned, immutable
address column) and the entity/field-name prefix `_r2db` (docs/design/
R2DB_CCR13_STORAGE_V1.md R-3). Before this revision, all three plugs'
`build_fixture()` used `id` as an ordinary integer field on `shared_entity`/
`a_only_entity`/`b_only_entity`, and `test_c01_scope_binding.py`'s
`_PLACEHOLDER_FIELD` was `"id"` -- both would silently stop meaning what
they appear to mean the moment `r2db-api` actually enforces this
reservation (docs/design/R2DB_CCR13_STORAGE_V1.md's own correction B-1).

The common fixture/probe convention is now `item_key` in place of `id`.
This is not merely a `build_fixture()` edit: any probe in a plug that
selects/filters a *fixture* entity's fields by the literal name `id` (as
opposed to a brand-new, throwaway entity a probe creates for its own
one-off purpose, which remains that peer's own business) had to move to
`item_key` in the same change, on pain of a silent loss of test fidelity
rather than an outright failure -- several of these probes reach an
entity-existence or request-shape denial *before* the renamed field is ever
looked up (`NOT_FOUND`/`VALIDATION_FAILED`, both already accepted denial
codes), so the old field name would not have failed the suite; it would
have quietly stopped exercising the position the probe exists to test (the
`filter_field` identifier-position probes on both `r2db-api` plugs, and the
`must_ignore` header/query-parameter vectors on `conformance_adapter_r2db_http.py`,
are the cases where this actually mattered. Verified directly, not merely
reasoned about: reverting those two vectors' `select` back to `id` and
re-running the suite still leaves `test_c01_scope_binding.py` fully green,
because both land on `ConformanceDenial(NOT_FOUND)`, which the consuming
test (`test_must_ignore_vectors_leave_scope_and_other_app_unchanged`)
already tolerates as an acceptable outcome for a `must_ignore` vector
(`except ConformanceDenial: pass`) -- the silent-hollowing failure mode
this paragraph describes, not a visible one.

The general rule, stated once here rather than per-peer: **a name reservable
by any one registered peer is not safe for the common fixture/probes to use,
even on peers that do not themselves reserve it.** `MitateDB-api` does not
reserve `id`; its own plug-local, non-fixture probe entities (the role-
elevation and schema-field-identifier probes' throwaway `create_collection`
calls) may keep using `id` freely, since they never touch the shared
`Fixture` entities. `conformance-tests/adapter.py`'s `Fixture` docstring now
states this rule normatively.

### 12.2 C-12 upsert positive control: unique-key precondition (R2DB_CCR13_STORAGE_V1.md correction B-2, deferred)

The contract's own precondition for `upsert`'s existence test
(`structured_operations.upsert`) is the entity's *declared domain
uniqueness*. `test_c12_capability_agreement.py`'s positive control
previously exercised `upsert` (when declared supported) on the same bare
entity `insert`/`update` share -- an entity with no declared unique key,
which is not a request the contract actually permits `upsert` to succeed
against. The positive control now creates a dedicated entity and calls the
new `create_unique_index` (§12.4 below) to give it exactly one declared
unique key before attempting `upsert` on it. The corresponding negative
case -- verifying `upsert` is refused on an entity that declares *no*
unique key, once a peer can declare `upsert` supported at the whole-
capability level while still gating it per-entity -- is left to C-17's
future test, not C-12's: C-12 only ever checked capability-declaration
agreement at the whole-service granularity.

This revision is not yet exercised by any positive-control path today: as
of WP-1, both `r2db-api` (`service.py capabilities()`) and `MitateDB-api`
(`cell.py capabilities()`) independently declare `atomic_mutation` with
`upsert` in `unsupported`, so every registered adapter still takes C-12's
existing negative branch for `upsert` (`CAPABILITY_UNSUPPORTED`, unaffected
by this change), and `test_at_least_one_adapter_exercises_a_positive_control_mutation`'s
vacuity guard is satisfied by `insert`/`update` alone.
The revision is nonetheless made now, ahead of any adapter needing it, so a
future adapter that does declare `upsert` supported (docs/design/
R2DB_CCR13_STORAGE_V1.md work package WP-5) exercises a request the
contract actually permits from the moment its capability document changes,
without a second coordinated revision of this test.

### 12.3 `attempt_mutation(..., expected_revision: str | None = None)`

A new keyword-only parameter, carried through to the peer's real mutation
entry point exactly like `values`/`where_field`/`where_value` -- never
interpreted by the adapter itself. `r2db-api` (both plugs) has a real
parameter position for it already (`Mutation.expected_revision`,
`structured.py`'s `_MUTATION_KEYS`), so both plugs forward it unconditionally
into the operation dict they already construct; the peer's own dispatcher
currently refuses it with `CAPABILITY_UNSUPPORTED`
(`revision_preconditions: unavailable`, a real and present denial, since
`bind_mutation` explicitly checks for this key).

**WP-1 implementation review, correction B-2 (Opus; distinct from
R2DB_CCR13_STORAGE_V1.md's own "correction B-2" in section 12.2 above,
which is a different document's different finding):** the first revision
of this section declared `MitateDB-api` `SurfaceAbsent` for this parameter, on the
reasoning that none of `session.insert`/`.update`/`.delete` has anything
resembling it. That reasoning missed a real, present entry point:
`ApplicationRuntime.transact`/`ApplicationCell.transact` already accepts an
arbitrary operation-dict shape (the same dispatcher the `upsert` branch in
§12.2 relies on) and, at the time, did not allowlist that dict's keys at
all -- so `expected_revision` rode along on an otherwise well-formed
`{"type": "insert", ...}` operation, and the row committed with the
precondition never even inspected. Review confirmed this by direct
measurement. Declaring this `SurfaceAbsent` would have been the adapter
fabricating an absence claim to paper over a real, observed peer defect --
precisely what design principle 4 forbids, mirrored onto `SurfaceAbsent`
instead of `ConformanceDenial`. Two changes, in the same review pass, fix
this properly:

1. **The plug** (this section's own scope) presents `expected_revision` as
   a real extra key on the `transact()` operation dict for every operation
   type, exactly as a real client attempting the contract's
   revision-precondition vocabulary would, and returns whatever `transact()`
   itself produces -- never `SurfaceAbsent`.
2. **`MitateDB-api` itself** (`cell.py`, a legitimate fix within this
   revision's scope, not a design change: the common contract's
   `versioning.unknown_capability` already requires "The service returns
   CAPABILITY_UNSUPPORTED without executing a fallback"). `transact()`'s
   `"insert"` branch now rejects any operation-dict key outside
   `{"type", "collection", "values"}` with `CapabilityError`
   (`CAPABILITY_UNSUPPORTED`) *before* touching the database, exactly the
   same reasoning its neighboring branch already applies to an unsupported
   operation *type*. A new peer-local test,
   `MitateDB-api/tests/test_foundation.py::FoundationTests::test_transact_insert_with_expected_revision_is_rejected_before_execution`,
   pins this: an `expected_revision`-carrying insert in a batch is refused
   and the batch's well-formed sibling insert never commits either (the
   whole `transact()` call is one atomic unit).

With that fix, presenting `expected_revision` to `MitateDB-api`'s plug now
observes a genuine `ConformanceDenial(CAPABILITY_UNSUPPORTED)` -- a real,
present denial, not a structural absence, and not the silently-dropped
precondition the unfixed peer used to produce.

### 12.4 `create_unique_index(session, entity, index, fields)`

Presents a real `create_index` (`unique: true`) schema operation to the
peer, exactly as a real client attempting the contract's `create_index`
vocabulary (CCR-13, contract 1.1.0; already present in `spec/
data-service-api.v1.json`'s `SchemaOperationRequest` as `index`/`unique`)
would. `r2db-api` (both plugs) presents this to the same real, single
`schema()` dispatcher every other schema operation already goes through --
there is no separate index-specific entry point, exactly like
`attempt_mutation`'s `upsert` branch reuses the single mutation dispatcher. This is
a real, present call, so whatever it returns is a genuine `ConformanceDenial`,
never fabricated. `MitateDB-api`'s only schema-mutation call,
`ApplicationDeveloper.create_collection(name, fields)`, has no parameter
for indexes of any kind, and no other schema-operation call exists on this
peer at all (confirmed by source inspection of `cell.py`); its plug raises
`SurfaceAbsent` rather than presenting this to a call that could not
possibly express it.

**Finding (not fixed in this revision):** exercising `create_unique_index`
against `r2db-api` today returns `VALIDATION_FAILED`, not
`CAPABILITY_UNSUPPORTED`. The common contract's `capability_status.rules`
states "optional target operations may be unavailable and must fail with
`CAPABILITY_UNSUPPORTED`", and `create_index` is exactly such a declared-
`unsupported` operation in this peer's own `schema_operations` capability
entry (`service.py`) -- but `structured.py`'s `bind_schema_operation`
rejects the request during its whole-shape key-allowlist check
(`_SCHEMA_KEYS`, which does not yet include `index`/`unique`) before it
ever reaches the operation-name branch that would produce
`CAPABILITY_UNSUPPORTED`. This is a genuine, currently-existing
`r2db-api` non-conformance with the letter of that contract rule,
discovered by presenting a real, contract-shaped request rather than
assuming the peer's behavior (this document's own design principle 4).
It is recorded here rather than fixed: `create_index`'s real implementation
(including the request-shape allowlist that must widen to accept it) is
`docs/design/R2DB_CCR13_STORAGE_V1.md` work package WP-3's job, and fixing
only the denial code ahead of that would still leave the operation
unimplemented while inviting a second, redundant edit to the same
validation path once WP-3 lands.

**Finding, recorded for completeness (m-6):** `MitateDB-api`'s own
`cell.py capabilities()` lists `create_index` in `schema_operations`'s
`unsupported` array -- so the *vocabulary* is known to this peer's own
discovery document -- while `ApplicationDeveloper` has no callable that
could receive a request shaped like one at all (the structural absence
this section's `SurfaceAbsent` raise documents). This sits in a mild
tension with `capability_status.rules`'s "optional target operations may
be unavailable and must fail with `CAPABILITY_UNSUPPORTED`": that rule
presumes an operation named as `unsupported` still has some real refusal
path to observe, whereas here there is no path to observe at all, only a
name declared absent. This is not the same defect as the `r2db-api`
finding above (which returns the *wrong code* through a *real* path); it
is a peer naming an operation in its own vocabulary listing that its
public surface cannot even receive. Recorded, not fixed, for the same
reason: `create_index` does not exist on either peer's real, executable
surface yet.

### 12.5 `query_with_revisions(session, entity, select, field, value)` and `SurfaceAbsent`

Same request shape as `select_eq`, returning `(items, revisions)`:
`revisions` is the contract's `QueryResult.revisions` (index-aligned with
`items`) when the peer's real query response carries one, or `None` when it
does not. As of WP-1 every registered peer returns `None` here --
`revision_preconditions` is `unavailable` on both `r2db-api` and
`MitateDB-api`, and neither peer's query response shape has a revisions
field yet (`r2db-api`'s gets one in docs/design/R2DB_CCR13_STORAGE_V1.md
work package WP-4) -- so this is presently plumbing with no adapter
divergence to observe, readied for WP-5's C-18 test.

**WP-1 implementation review, correction M-1 (Opus):** `None` must be an
*observation*, not an assumption. The in-process `r2db-api`/`MitateDB-api`
plugs' underlying calls (`DataService.query()`, `ApplicationCell.read()`)
each return a bare `list[dict]`, not a wrapping object, so `None` there is
a structural fact about that return type -- there is no dict to have
looked at and not looked at. `conformance_adapter_r2db_http.py`'s real
`POST .../query` response, in contrast, *is* a JSON object; the first
revision of this method discarded it entirely and hardcoded `None`
regardless of what the peer actually sent back, which is an assertion
wearing an observation's clothing. It now inspects the real response
directly (`result.get("revisions")`) instead of going through `select_eq`,
so it still evaluates to `None` today (the response genuinely has no such
key yet) but will pick up a real value the moment work package WP-4 adds
one, with no adapter edit required.

`SurfaceAbsent` (`conformance-tests/adapter.py`) is a new exception,
introduced because `create_unique_index` (`-> None`) and
`attempt_mutation`'s `expected_revision` (`-> int`) cannot reuse
`catalog_document`'s `CATALOG_SURFACE_ABSENT` string-sentinel approach
without colliding with a genuine return value of their own type. It plays
the identical structural role `CATALOG_SURFACE_ABSENT` plays for
`catalog_document` and `structurally_absent` plays for
`tamper_vectors`/`credential_reactivation_vectors`: the honest answer when
a peer's public surface has no real call that could plausibly receive a
request at all, confirmed by source inspection and never assumed, and
never a substitute for a genuine `ConformanceDenial` when the peer did
receive and refuse the request.

**WP-1 implementation review, correction B-1 (Opus):** the first revision
of this exception carried only `adapter`/`operation`/`reason` -- a bare claim, with
nothing a consumer could check independently, unlike every other
structural-absence mechanism on this port (`structurally_absent`'s own
`surface`/`forbidden_parameters` pair, inspected via
`signature_forbids_parameters`). `SurfaceAbsent` now *requires*
(constructor-enforced, `ValueError` on an empty value) the same
`surface: Sequence[Callable]` and `forbidden_parameters: Sequence[str]`
pair, so a future C-17/C-18 test can run
`signature_forbids_parameters(exc.surface, exc.forbidden_parameters)`
itself rather than trust the claim on its word. `MitateDB-api`'s
`create_unique_index` now raises it with
`surface=self.public_operation_callables()` (this peer's entire
application-facing surface) and `forbidden_parameters=["index", "unique"]`.
The port docstring states the consuming norm explicitly: **a consumer must
never catch this exception and convert it to a skip or a pass without
performing that signature check** -- doing so would be exactly the "silent
permission of the unknown" design principle 4 forbids, only relocated from
a bare `except: pass` to an unchecked `except SurfaceAbsent: pass`.

### 12.6 `create_entity`'s type-wiring obligation (correction M-8, not yet activated)

`create_entity(session, entity, fields: Mapping[str, str])`'s `fields`
values have always been type names (`COMMON_FIELD_TYPES`: `"text"`,
`"integer"`), but every plug has only ever forwarded field *names* to its
peer, discarding the type. `ConformanceAdapter.create_entity`'s docstring
now records the obligation this leaves standing: a plug must wire
`field_type` through to the peer's own typed-column mechanism where one
exists, so a typed column is not left permanently unexercised by the common
suite. For `r2db-api`, the wiring target is `add_field` + `field_type`
(docs/design/R2DB_CCR13_STORAGE_V1.md R-2); activating it is deferred to
that design's work package WP-5, once `r2db-api` itself implements
`add_field`'s `field_type` parameter. Until then, both `r2db-api` plugs
continue to pass only field names, as they did before this revision --
this section records the obligation without discharging it, exactly as
`docs/design/R2DB_CCR13_STORAGE_V1.md`'s own correction M-8 describes.

### 12.7 Compatibility impact (WP-1 implementation review, correction M-5)

This revision's two new `@abstractmethod`s (`create_unique_index`,
`query_with_revisions`) and `attempt_mutation`'s new keyword-only
`expected_revision` parameter are additions to the NORMATIVE surface this
document's §4 defines (design principle 1: port owned by the common
repository). Per §11's own precedent, they were applied identically in
shape across all three plugs registered in `conformance-tests/registry.json`
in the same change, so nothing in *this* repository is left with a stub or
a `NotImplementedError`. This is stated here explicitly because it is
**breaking for any plug outside this repository**: `ConformanceAdapter` is
an `ABC`, so any third-party plug that does not implement the two new
methods fails to instantiate at all (`TypeError: Can't instantiate
abstract class ... with abstract methods create_unique_index,
query_with_revisions`), and `attempt_mutation`'s new parameter, though
it has a default and is therefore backward-compatible for *callers*, still
requires every plug's own `attempt_mutation` override to accept it (a
plug's override must repeat a compatible default, or every existing call
site breaks). This is the same class of change principle 1 already commits
this document to whenever the NORMATIVE surface grows -- consistent with,
not a departure from, how §11 introduced `catalog_document`,
`attempt_mutation` itself, and `credential_reactivation_vectors` in the
prior coordinated revision.

## 13. v1.3 port revision (coordinated with docs/design/R2DB_CCR13_STORAGE_V1.md work package WP-5a)

By the time work package WP-5a began, `r2db-api` had already landed WP-2
through WP-4 (in-memory + PostgreSQL CCR-13 storage, committed) and WP-5b
(the `capabilities()` declaration update -- `row_addressability`/
`revision_preconditions: enabled`, `upsert`/`create_index`/`drop_index`
real operations, the provisional gate from R2DB_CCR13_STORAGE_V1.md §3
removed)
was staged in the same working tree. §12's port additions were therefore
plumbing with no adapter divergence to observe when they were written; this
section is where they -- and several more the C-17/C-18 test files
themselves needed -- become genuinely exercised, per this document's own
design principle 1 (port owned by the common repository, plug owned by
each peer) and principle 4, exactly as §11/§12 did for their own additions.
Every plug implements every addition below in the same change; none is
left with a stub.

### 13.1 `attempt_mutation`/`attempt_mutation_with_addresses`: `unique_key`

`unique_key` (contract 1.1.0, CCR-13 §0.5 Q-1 adjudication plan B:
`Mutation.unique_key`) is a new keyword-only parameter on
`attempt_mutation`, carried through exactly like `expected_revision` -- never
interpreted by the adapter. It names, by the catalog's own key name, which
of an entity's declared uniqueness keys `upsert` should use as its
existence test when more than one is declared. `r2db-api` (both plugs) has
a real parameter position for it already (the same mutation-operation
dispatcher every other keyword here uses); `MitateDB-api` has no
uniqueness-key concept at all, so a real value is expected to be refused,
but that refusal is required to come from presenting it to the real
`transact()` dispatcher (the same one `expected_revision` already uses,
per §12.3's correction B-2), never from the adapter deciding the answer
itself.

A second new method, `attempt_mutation_with_addresses`, has the identical
parameter set but returns `(affected, assigned_addresses)` instead of a
bare `int`. It exists because C-12 already depends on `attempt_mutation`
returning a plain `int` compared with `>= 1`, and C-17 needs to observe the
real mutation response's `assigned_addresses` directly -- in particular,
that only the insert-resolved half of an `upsert` batch ever appears there,
never the update-resolved half. `assigned_addresses` is `None` only when
the peer's real response structurally has no such slot at all (the same
convention `query_with_revisions` uses for `revisions`); `r2db-api` (both
plugs) always returns a real list (`MutationResult.assigned_addresses`
never being `None` in `service.py`'s own shape); `MitateDB-api` always
returns `None`, since none of its real return shapes (`{"rowid": ...}`,
`{"updated": ...}`, `{"deleted": ...}`, a `transact()` results list) carry
anything resembling a published address -- consistent with this peer
declaring `row_addressability: unavailable`. Synthesizing an address out of
`insert()`'s own `rowid` would be this adapter fabricating an
addressability concept the peer itself does not publish to a real caller.

### 13.2 `attempt_filter`

`select_eq` generalized to an arbitrary predicate operator:
`attempt_filter(session, entity, select, field, operator, value)`, presenting a
single-predicate query to the same real query entry point `select_eq`
already uses. Needed by two consumers that both already existed but had no
way to exercise a *non-`eq`* operator at all: C-12's reverse condition
(§13.3 below) and C-03's new `contains`/`matches` value-corpus tests
(§13.5).

### 13.3 C-12 reverse condition: undeclared query operators

C-12 previously only ever checked "declared enabled ⇒ executes" for
mutation operations; the opposite direction -- "an operation/operator this
peer's own capability document does NOT declare must be refused with
`CAPABILITY_UNSUPPORTED` before execution" -- went completely unchecked
for query *operators* specifically (`structured_query.operators`), even
though the mutation-operation half of this reverse direction was already
implicit in C-12's own "undeclared operation" branch. `docs/design/
R2DB_CCR13_STORAGE_V1.md` §4 names this explicitly: two real defects (WP-2
review B-1, WP-3 review blocker-1) took exactly this shape -- a
capability-document `unavailable`/`unsupported` entry with a shared
validation boundary that executed it anyway.
`test_c12_capability_agreement.py`'s new
`test_undeclared_query_operators_are_refused_before_execution` presents
every operator in the contract's own `allowed_query_operators` that a
peer's `structured_query.operators` does not list,
via `attempt_filter`, and requires `CAPABILITY_UNSUPPORTED` with state
unchanged.

**Finding, fixed in this revision:** presenting this real request against
`MitateDB-api` found that `contains` and `is_null` -- both declared
`unsupported` in its own `structured_query` capability entry, same as
`matches` -- were in fact refused with `VALIDATION_FAILED`, not
`CAPABILITY_UNSUPPORTED`. `cell.py::_where` special-cased only `matches`
with the correct `CapabilityError`; `contains`/`is_null` fell through to
the generic "operator this peer does not implement at all" branch and
raised `ValidationError` instead, disagreeing with their own declared
status (`capability_status.rules`: "optional target operations ... must
fail with CAPABILITY_UNSUPPORTED"). This is corrected in `cell.py` itself
(a legitimate scope for this revision, the same precedent §12.3's
correction B-2 already set for a `MitateDB-api` fix discovered by
presenting a real request rather than assuming behavior): all three
contract-vocabulary-but-unimplemented operators now share one code path.
Peer-local coverage: `MitateDB-api/tests/test_foundation.py`'s
`test_contains_filter_is_honestly_rejected_never_executed_as_a_like_wildcard`
(updated) and new
`test_is_null_filter_is_capability_unsupported_not_validation_failed`.

### 13.4 r2db plug type-wiring activation (M-8, deferred in §12.6, now live)

§12.6 recorded the obligation without discharging it, pending `r2db-api`'s
own `add_field` `field_type` parameter (work package WP-5, since landed).
Both `r2db-api` plugs' `create_entity` now issue `create_entity` (no
inline fields) followed by one `add_field(field_type=...)` per field,
mapping the port's own two-member vocabulary
(`adapter.COMMON_FIELD_TYPES`: `text`/`integer`) to this peer's real `field_type` enum
(`spec/data-service-api.v1.json`: `string`/`integer`/`number`/`boolean`/
`object`/`array`) via an explicit `{"text": "string", "integer":
"integer"}` table in each plug -- the mapping design section 4 item 3
originally asked for. Verified empirically against the real HTTP+PostgreSQL
plug: a field wired this way is a genuine typed column (an `integer`-typed
field now refuses a non-integer value with `VALIDATION_FAILED`), and the
common fixture's own existing string-only value corpus (`payloads.py`)
continues to round-trip through the newly-typed `label`/`probe_key`/
`probe_value` fields unaffected, since every value in that corpus was
already a plain string.

### 13.5 `query_with_revisions`/`attempt_mutation_with_addresses` now observe real data

Both r2db plugs' `query_with_revisions` and the new
`attempt_mutation_with_addresses` were written in §12 against a peer that did not yet
populate `revisions`/`assigned_addresses` at all (WP-1's plumbing-only
state). With WP-4/WP-5b now landed and staged, the in-process plug's
`query_with_revisions` was found to still be calling `DataService.query()`
-- the plain-list form that deliberately stays byte-for-byte pre-CCR13
compatible and never exposes `revisions` -- rather than `DataService.
query_page()`, the real, present entry point that does. This is corrected
here: the in-process plug now calls `query_page()` and returns its real
`.revisions`. `conformance_adapter_r2db_http.py`'s sibling method needed no
code change at all -- it already inspected the real HTTP response
(`result.get("revisions")`, §12.5's correction M-1) rather than asserting a
hardcoded `None`, so it began returning real data the moment the server
response gained the key, which is the entire point of observing instead of
asserting.

### 13.6 C-03 value corpus: `contains`/`matches`

Two new test functions,
`test_contains_value_position_is_literal_never_wildcard_interpreted` and
`test_matches_value_position_applies_real_wildcard_grammar_and_rejects_bad_patterns`,
using `attempt_filter` (§13.2)
to place `%`/`_`/`\`-bearing values at the `contains`/`matches` *value*
position specifically -- a position neither the existing
`MUST_COVER_VALUE_POSITIONS` taxonomy (always `eq`) nor C-12's reverse condition (which
only proves an undeclared operator is refused, never a declared one's
semantics) ever reached. The core proof is negative, not just a round
trip: a `%`-bearing `contains` pattern must not additionally match a row
only a wildcard interpretation would reach, which is the live-regression
shape Q-2's literal/wildcard split exists to foreclose (docs/design/
R2DB_CCR13_STORAGE_V1.md §0.5 Q-2). `matches`'s trailing-unescaped-
backslash grammar violation (the same contract text WP-3 review blocker-2
already hardened `r2db-api` against) is checked as `VALIDATION_FAILED`
here too, from the common suite's own side rather than only `r2db-api`'s
peer-local tests. On a peer where an operator is undeclared, the test
takes the same real-refusal branch C-12's reverse condition already
established, rather than a second, redundant structural check.

### 13.7 C-17/C-18: test files, CONDITIONS.md, mutation-detection results

`test_c17_declaration_agreement.py` and
`test_c18_revision_precondition_semantics.py` are new files, registered `@pytest.mark.condition("C-17")`/
`"C-18"` respectively, parametrized over all three adapters exactly like
every other executable condition. `CONDITIONS.md`'s C-17/C-18 rows move
from `not yet executable` to `executable (three adapters)`; the C-12 row's
condition/evidence text records the reverse direction (§13.3); the C-03
row's evidence text records the `contains`/`matches` value-corpus addition
(§13.6). Both new files follow the same "branch once at the top on the
peer's own declared capability status" structure C-12 already established,
so every test function makes a genuine, non-vacuous assertion against
every registered adapter -- never a skip -- per this document's own design
principle 4 and this repository's "skip is fail" rule: C-17's unavailable
branch is `SurfaceAbsent`-based structural evidence (§4 item 4's
mechanism, since `create_unique_index` truly has no receiving call on
`MitateDB-api`); C-18's unavailable branch is a real, present
`CAPABILITY_UNSUPPORTED` denial instead (§13.1's `unique_key` reasoning
applies identically to `expected_revision`: `MitateDB-api`'s `transact()`
is a real entry point that refuses it, not an absent one, since the §12.3
correction B-2 fix).

Detection-power verification (design §5 WP-5 completion condition: at
least the property-4 removal, precondition-silencing, and revisions-
identity-string mutations must each turn a test red) is recorded in this
work's own completion report rather than duplicated here; see that report
for the mutation table.

### 13.8 Compatibility impact (mirrors §12.7)

Two more additions to the NORMATIVE surface, applied identically in shape
across all three plugs in the same change as §12.7 already established the
precedent for: `attempt_mutation`'s new `unique_key` keyword-only
parameter, and two new `@abstractmethod`s
(`attempt_mutation_with_addresses`, `attempt_filter`). Identical breaking-change consequence for
any plug outside this repository: `ConformanceAdapter` remains an `ABC`, so
a third-party plug missing either new method fails to instantiate at all,
and every plug's own `attempt_mutation` override must accept `unique_key`
(a compatible default satisfies existing call sites, but the override
itself must be edited to declare it).

## 14. v1.4 port revision (WP-5 final review recommendation)

C-17's own test file (§13.7) checks `assigned_addresses`' insert-only
membership rule (contract 1.1.0, CCR-13 `MutationResult.assigned_
addresses`) by calling `attempt_mutation_with_addresses` once per
operation -- which cannot catch a defect that only appears when operations
of different kinds share one real atomic batch (for example, an
accumulation bug that attaches an address entry to a non-insert operation
only because a real insert elsewhere in the same batch happens to precede
it). The WP-5 final review recommended closing this gap with a genuine
multi-operation batch test, which needs its own port addition: splitting
the batch into several single-operation `attempt_mutation_with_addresses`
calls would prove nothing about batch-level behavior, since each call
would be its own atomic unit on the peer's side.

### 14.1 `BatchOperation` and `attempt_batch_with_addresses`

`BatchOperation` (`conformance-tests/adapter.py`) is a frozen dataclass
naming one element of a batch -- field-for-field the same shape
`attempt_mutation`'s own keyword arguments already use (`operation`,
`values`, `where_field`, `where_value`, `expected_revision`, `unique_key`,
`destructive`, `confirmation`), so a caller building a batch from what
would otherwise be several separate `attempt_mutation` calls does not
learn a second vocabulary.

`attempt_batch_with_addresses(self, session, entity, operations: Sequence[
BatchOperation]) -> tuple[int, list[Mapping[str, Any]] | None]` is a new
`@abstractmethod` that presents every operation to the same real
multi-operation dispatcher `attempt_mutation`/`attempt_mutation_with_
addresses` already use with exactly one operation each, and returns the
whole batch's `(affected, assigned_addresses)`. Every plug implements it
by building its own real batch payload/item list from the `BatchOperation`
sequence and handing the whole thing to that one real entry point in a
single call -- never splitting it into several single-operation calls
itself:

- `r2db-api` (in-process): `DataService.mutate_result` given every
  built mutation item at once (`r2db-api/conformance/
  conformance_adapter_r2db.py`) -- the same facade method §13.1
  introduced for `attempt_mutation_with_addresses`, here given more than
  one item.
- `r2db-api-http`: one `POST /v1/data/{entity}/mutations` request whose
  body's `operations` array carries every item (`r2db-api/conformance/
  conformance_adapter_r2db_http.py`) -- the real HTTP batch shape a real
  multi-operation client request would use.
- `MitateDB-api`: `ApplicationRuntime.transact`/`ApplicationCell.transact`
  given every item (`MitateDB-api/conformance/
  conformance_adapter_mitatedb.py`) -- this peer's *only* real
  multi-operation atomic dispatcher. Consistent with `row_addressability:
  unavailable`, this peer's `transact()` only ever truly executes an
  `"insert"` item; every other type in the batch (`update`/`delete`/
  `upsert`) is refused with `CapabilityError` regardless of what else
  shares the batch (`cell.py`'s own op-type dispatch) -- so a real mixed
  batch is genuinely refused here, not silently split apart by the
  adapter to avoid that refusal.

### 14.2 C-17 test: batch-level membership

`test_assigned_addresses_membership_holds_when_mixed_in_one_batch`
(`conformance-tests/test_c17_declaration_agreement.py`) presents one real
batch mixing an insert, an update, an upsert that resolves to an update
(matching a pre-seeded row's own declared unique key), and a properly
confirmed delete, and requires `affected == 4` with exactly one
`assigned_addresses` element -- the insert's -- no matter what else shares
the batch. On a `row_addressability: unavailable` peer this takes the same
structural-evidence branch every other declaration-dependent C-17 check
does (§4's `signature_forbids_parameters`), rather than being skipped.

### 14.3 Compatibility impact (mirrors §12.7/§13.8)

One more addition to the NORMATIVE surface: the new `@abstractmethod`
`attempt_batch_with_addresses`, plus the `BatchOperation` dataclass it
takes a sequence of. Identical breaking-change consequence for any plug
outside this repository: `ConformanceAdapter` remains an `ABC`, so a
third-party plug missing the new method fails to instantiate at all.

## 15. v1.5 port revision (coordinated with docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md work package WP-1)

`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` §4 raises C-14 (control-plane
authority boundary) and C-15 (bootstrap/reset lifecycle), both registered
in `conformance-tests/CONDITIONS.md` as `not yet executable` before this
revision. Unlike §12's C-17/C-18 (whose *test* files were deliberately
deferred to a later work package because no registered peer had landed
the behavior they exercise), WP-1 makes C-14/C-15 executable immediately:
every registered adapter has an honest, real answer to give right now --
"no such surface exists" -- and design principle 4 (uncertainty must not
silently become permission) treats an unwritten test for an honestly
absent surface as exactly the kind of silent permission it forbids. This
section is therefore a coordinated revision across the NORMATIVE surface
this document's §4 defines and all three registered plugs
(`conformance_adapter_r2db.py`, `conformance_adapter_r2db_http.py`,
`conformance_adapter_mitatedb.py`), in the same change, exactly as §11-§14
did for their own additions -- and it is a *complete* one this time (no
plug left with a stub pending a future landing), because every plug's
answer this time is uniformly the same, honest `SurfaceAbsent`.

### 15.1 `ControlCredentialHandle`

A new frozen dataclass, `credential_ref: str` / `secret: str`, deliberately
*not* a variant of `CredentialHandle`: a control credential belongs to no
Application at all (the contract's `control_credential` scheme has no
`application_id`/`role` slot the way `runtime`/`developer` credentials do,
design R2DB_CCR14_CONTROL_PLANE_V1 §R-2). Minting one with a placeholder
`application_id`/`role` to reuse `CredentialHandle`'s shape would let a
scope-tampering defect hide behind a value this port itself fabricated;
the two types stay disjoint so such a value is a type error rather than a
silent coercion. It duck-types compatibly with every currently-registered
plug's `authenticate()` (which reads only `.secret`, or `.credential_ref`
+ `.secret` for `MitateDB-api`), which is what lets C-14 vector 2 present
a `ControlCredentialHandle` to the application-plane `authenticate()`
without a third, unifying handle type.

### 15.2 Thirteen new `@abstractmethod`s

The contract's 11 `/control/v1` endpoints fold onto 9 in-band port
operations (`set_application_enabled_inband`/`set_credential_enabled_
inband` each carry an `enabled: bool` instead of being split into an
`enable_*_inband`/`disable_*_inband` pair): `control_capabilities`,
`register_application_inband`, `list_applications`, `set_application_
enabled_inband`, `issue_credential_inband`, `list_credentials`, `rotate_
credential`, `revoke_credential_inband`, `set_credential_enabled_inband`.
Two out-of-band ritual hooks follow the same shape as the pre-existing
`provision_application`/`issue_credential` privileged-setup group rather
than the in-band group: `bootstrap`/`reset` (no `actor` parameter at all
-- by contract these rituals have no in-band caller, plan B's own
premise). Two more privileged setup/observation operations complete the
set: `control_credential` (a ritual-completed, fully-authorized control
credential, ready to use as `actor`) and `control_audit_events` (an
observation of the peer's own real audit trail).

Every in-band operation's `actor` parameter is typed `CredentialHandle |
ControlCredentialHandle` and is presented to the peer's real entry point
exactly as received, with no adapter-side pre-filtering by credential
kind or role -- **authorization is the peer's decision, never the
port's**. This is what lets C-14 vector 1 (an ordinary application
credential, `issue_credential`'s own output, handed here as `actor`
against all 11 endpoints) be a genuine measurement of the peer's own
fail-closed behavior rather than the adapter enforcing the boundary
itself and reporting success regardless of what the peer would have
done. `adapter.py`'s own new group-header comment (immediately preceding
`control_capabilities` in the ABC) states this, and the shared
resource-boundary-exercisability requirement (recommended <=200 for
every SI-08 class a conformance build declares), once for the whole
group rather than duplicated 13 times.

**Fourteenth method, WP-1 fix-round (§15.9 below):** `deprovision_
application(application_id: str) -> None` was added alongside
`provision_application` (not in this in-band group -- it is a privileged,
out-of-band, test-harness-only cleanup operation, never a public API
capability) to give C-14 vector 5's `applications` resource-bound drive a
way to undo what it registers.

### 15.3 Two absence forms, both genuinely verified

Design §4 defines two shapes a peer without a real, `enabled` in-band
surface may honestly take, neither of which is a skip:

- **(a) surface-absent**: no real call on the peer's public surface could
  receive the request at all. The port operation raises `SurfaceAbsent`
  (the same exception §12.5 introduced for `create_unique_index`/
  `expected_revision`), carrying `surface`/`forbidden_parameters` so a
  consumer independently re-verifies the claim via `signature_forbids_
  parameters` rather than trusting it.
- **(b) declared-unavailable**: a real entry point exists, but the peer's
  `control_plane` capability is declared `unavailable`, so every real
  entry point refuses uniformly with `CAPABILITY_UNSUPPORTED`. No
  currently-registered peer takes this branch; the mechanism is defined
  now so a future deployment shape that does (design §4's own adapter x
  phase table leaves room for one) needs no further port revision.

`test_c14_authority_boundary.py`/`test_c15_bootstrap_reset_lifecycle.py`
dispatch between "provided" (`control_plane: enabled`) and "absent"
(anything else) once, at the top of every test function, on
`capability_document()["capabilities"]["control_plane"]["status"]` --
the same pattern §13.7 established for C-17/C-18's `row_addressability`/
`revision_preconditions` branching. Both files' absence branch goes one
step further than that precedent: a shared per-file helper (`_assert_
control_operation_absent_or_uniformly_refused`, deliberately duplicated
between the two files rather than factored into a third module -- §15.6
below) requires every operation exercised in one test to report the
*same* form, since a `control_plane` declaration is supposed to mean one
consistent thing about the peer's topology, not a per-operation coin
flip.

### 15.4 All three plugs: uniformly `SurfaceAbsent`, one shared helper each

As of this revision, control-plane HTTP work (`docs/design/
R2DB_CCR14_CONTROL_PLANE_V1.md` work packages WP-2 onward) has not landed
in either peer's `src/`. Every one of the 13 new operations therefore
takes the surface-absent branch, unconditionally, on all three plugs --
via one shared private helper per plug (`_control_surface_absent`,
avoiding 13 near-duplicate `SurfaceAbsent` call sites per plug that could
drift out of sync with each other), each carrying comment density
matching the C-17 precedent
(`MitateDB-api/conformance/conformance_adapter_mitatedb.py:443-476`,
`create_unique_index`'s own `SurfaceAbsent` raise) for why its own
particular evidence supports the "absent" claim:

- **`r2db-api` (in-process)**: evidence is `public_operation_callables()`
  (the same five `DataService` callables C-03's native-command-surface
  check already inspects). `ControlAuthority` is a private,
  non-application-facing authority; `r2db_api.topology`'s own structural
  validation, not this adapter, is what keeps it unreachable from that
  five-callable surface.
- **`r2db-api-http`**: same signature-level evidence, plus a live
  measurement no other plug can make: before raising, the helper
  inspects `self._app.app.routes` -- the real, running Starlette app's
  own route table (`self._app` is the exact `RequestByteBoundMiddleware`-
  wrapped app `create_app` built in `__init__`, now kept on the instance
  for this purpose; `.app` is that middleware's own wrapped Starlette
  instance) -- for any route whose `.path` starts with `/control`. Finding
  one raises `AssertionError` rather than proceeding on a claim the
  peer's own live state would contradict. This turns the absence claim
  from a comment into a measurement, the strongest form of "confirmed by
  source inspection, never assumed" available to an HTTP-boundary plug.
- **`MitateDB-api`**: **superseded by the WP-1 fix-round (§15.9, independent
  review major M-7)** -- an earlier revision of this plug excluded
  `MitateDataService.open_session` from its evidence `surface` entirely to
  dodge a signature-check false positive; that exclusion is reverted here
  in favor of the `exempt_parameters` mechanism (§15.9 below), which keeps
  the evidence surface honestly complete (the FULL, unmodified
  `public_operation_callables()`) while still not treating the one known-
  harmless name collision as a finding. `open_session(self, credential_id,
  secret)`'s real `credential_id` parameter is this peer's ordinary
  session-authentication argument (identifying which *already-issued*
  application credential is authenticating) -- structurally incapable of
  originating a bootstrap/reset/issue-role-control/rotate/revoke-shaped
  request under any argument value. Its name nonetheless contains the
  substring `"credential"`, which trips `signature_forbids_parameters`'s
  deliberately coarse substring match. **Verified empirically, not
  assumed, both before and after the fix**: running `signature_forbids_
  parameters` against the full `public_operation_callables()` reports
  exactly one violation, `MitateDataService.open_session.credential_id`
  -- confirmed against this peer's own real `__qualname__` rather than
  guessed -- which the plug now declares verbatim as its one
  `exempt_parameters` entry.

All three plugs pass the same `forbidden_parameters=["credential",
"control", "bootstrap", "rotate", "revoke"]` -- verified, per-plug, to
produce zero `signature_forbids_parameters` violations against the
surface each one actually declares.

### 15.5 Mutation-injection results (WP-1 completion condition)

Recorded in this work's own implementation report
(`WP1_IMPLEMENTATION_REPORT.md`) rather than duplicated here, per §13.7's
precedent for C-17/C-18's own detection-power verification. Six mutations
were exercised in the initial round (M1-M6): weakening a plug's declared
`SurfaceAbsent` `surface` to include a real, control-shaped parameter; a
plug returning a fabricated success instead of `SurfaceAbsent`; a plug's
capability document lying `control_plane: enabled` while no real surface
backs it; weakening `forbidden_parameters` to a narrow, non-covering
fragment list; an adapter fabricating a `CAPABILITY_UNSUPPORTED` denial
instead of raising `SurfaceAbsent` (a measured, reported result, not an
assumed one); and reverting `CONDITIONS.md`'s C-14 row to `not yet
executable` (a measured gap in `test_conditions_register.py`, closed by
§15.9's item 10 below). **The WP-1 fix-round (§15.9) re-ran M1-M6 under
the strengthened M-7 helper and added three more (M7-M9)** -- see the
implementation report's fix-round section for the full, re-measured
table.

### 15.6 Design decision: no shared `_c1415_common.py`

`test_c14_authority_boundary.py` and `test_c15_bootstrap_reset_lifecycle.py`
share several helpers in shape (`_control_plane_status`, `_assert_control_
operation_absent_or_uniformly_refused`, `_assert_uniform_absence_form`).
Rather than factor these into a third shared module, or have one file
import from the other, each file carries its own copy. This mirrors
design principle 2 (the port stays condition-driven and minimal) applied
one level down: a helper that exists only to serve two specific
condition files' own dispatch logic is not NORMATIVE port surface, and
`adapter.py` is deliberately not the place test-only, condition-specific
logic accumulates. A new shared test-support module would trade a small,
easily-audited ~40-line duplication for a permanent cross-file coupling
(a change to one condition's helper silently changing the other
condition's behavior) -- judged the worse trade, especially since every
other condition file in this suite (`test_c01_scope_binding.py` through
`test_c18_revision_precondition_semantics.py`) is already independently
self-contained in exactly this way.

### 15.7 `CONDITIONS.md`: C-14/C-15 move to `executable (three adapters)`

Both rows' `Status` column now begins `executable (three adapters)` and
records: the test file name and marker; that all three adapters currently
take the structural-evidence (surface-absent) branch; the declared-
unavailable form (b)'s definition, with no currently-registered peer
example; and that the "provided" branch is real, executable verification
code that becomes non-vacuous once a registered adapter's peer implements
`/control/v1` and flips its declaration (`r2db-api`/`r2db-api-http`, work
package WP-5; `MitateDB-api` stays surface-absent through the next phase
per design §4's own adapter x phase table). The C-14 row's `Invariants`
column gains `SI-08` (the resource-boundary vector, §4 vector 5); C-15's
stays `SI-13, SI-14` unchanged.

### 15.8 Compatibility impact (mirrors §12.7/§13.8/§14.3)

One new value type (`ControlCredentialHandle`) and, after the WP-1
fix-round (§15.9), fourteen new `@abstractmethod`s (`deprovision_
application` being the fourteenth) plus one new keyword-only field on the
pre-existing `SurfaceAbsent` exception (`exempt_parameters`, defaulted to
`()` so every pre-existing `SurfaceAbsent` call site anywhere in this
repository remains source-compatible unchanged) are additions to the
NORMATIVE surface this document's §4 defines. Identical breaking-change
consequence for any plug outside this repository, at a larger scale than
any prior revision: a third-party `ConformanceAdapter` subclass missing
even one of the fourteen fails to instantiate at all (`ConformanceAdapter`
remains an `ABC`). Applied identically in shape across all three plugs
registered in this repository in the same change, so nothing here is left
with a stub -- and, unlike every prior coordinated revision (§11-§14),
every plug's *behavior* is identical too (uniformly `SurfaceAbsent`), not
merely its shape, since no registered peer yet has a real control-plane
surface to diverge over.

### 15.9 WP-1 fix-round (independent review: blocker 2 / major 7 / minor 7 / nit 2, verdict approve-with-fixes; supervisor rulings)

An independent review of the initial WP-1 implementation (§15.1-§15.8
above) found two blockers, seven majors, seven minors, and two nits. Every
item was applied in one coordinated fix-round across `adapter.py`, all
three plugs, both condition test files, `CONDITIONS.md`,
`test_conditions_register.py` (a supervisor-authorized, narrow scope
extension: item 10 only), and this document. §15.1-§15.8 above were
edited in place where a fix superseded their original account (marked
explicitly, e.g. §15.4's `MitateDB-api` bullet); this section records the
fix-round as a whole for audit-trail completeness, the same role §10
plays for the original v1.0 implementation review.

**Blockers B-1/B-2 -- C-14 vector 5 rewritten (positional arithmetic, not
a contract resource label).** The original vector 5 had two defects: (1)
`LIMIT_EXCEEDED` carries no class-discriminating field in the contract's
own problem+json shape (`spec/data-service-api.v1.json` `errors.shape`:
`details` is free-form, no canonical `resource` key -- the reviewer's own
suggestion to use one was independently checked against the contract text
by the supervisor and found to not exist; this suite does not invent
contract vocabulary to paper over that absence), so a rate-limiter-only
peer could pass all three class checks vacuously, and with the contract's
`example_profile` (`applications: 100`, `credentials_per_application: 10`,
`control_requests_per_minute: 60`) the `applications` drive would
necessarily trip the rate limiter at request 61 before ever reaching its
own bound; (2) the `applications` drive permanently saturated the
registry with no deletion path, poisoning the session-scoped adapter for
every later test. Fixed by: a new 14th port op, `deprovision_application`
(§15.2 above); reading the current `applications` count before driving
and requiring EXACTLY `bound - current` successes before `LIMIT_EXCEEDED`
(any earlier refusal fails with an explicit "cannot attribute the refusal
to this class" message); the same exact-position requirement for
`credentials_per_application`; running `control_requests_per_minute`
LAST, via a burst of `control_capabilities` (an operation no permanent
bound applies to -- that operation choice IS the class attribution); a
documented headroom precondition (`rate_limit >
applications_headroom_drive + credentials_drive + 64`) that fails loudly,
before any drive runs, if a conformance build's rate limit cannot
possibly give the other two drives room to reach their own bounds; and a
post-burst recovery check (sleep to the next minute-window rollover,
bounded <=61s, provided-branch-only, documented cost) proving the refusal
was transient rather than permanent and un-poisoning the rate window for
later tests.

**Major M-1 -- C-15 vector 1 cross-test-ordering dependency removed.** The
original provided branch assumed some *other* test in the module had
already called `control_credential()`, establishing a control credential
to test bootstrap's `CONFLICT` refusal against. Fixed: the test now calls
`control_credential()` itself, first.

**Major M-2 -- response-shape normalization documented, and a real bug
fixed.** `list_applications`/`list_credentials`/`issue_credential_inband`/
`rotate_credential`'s port docstrings now state explicitly that the
adapter unwraps the contract's envelope response and returns the row
sequence, and that row keys are the CONTRACT's own field names
(`credential_id`, not this port's own `CredentialHandle.credential_ref`
field name) -- `list_credentials()`'s real response rows have no
`credential_ref` key at all. This corrected a real bug in C-15 vector 1's
revoke loop, which read `row["credential_ref"]` (a `KeyError` waiting to
happen against a real peer's real response) instead of
`row["credential_id"]`.

**Major M-3 -- C-14 vector 4 no longer requires data-plane reachability.**
The original provided branch authenticated the in-band-issued credential
and asserted a successful `scope_of()` roundtrip. Per design R-4, an
in-band-registered Application is legitimately "registered but
unprovisioned" -- its data-plane `authenticate()` fails closed by design
until an operator separately provisions it, so asserting success there
would fail a conformant peer. Fixed: the provided branch now asserts
presence in `list_applications()` plus a non-empty secret from in-band
issuance -- both control-plane-level properties -- and the test's
docstring records this reasoning as a supervisor ruling, overridable.

**Major M-4 -- `control_credential()`'s "valid at call time" contract made
explicit.** The port docstring now states explicitly that this method
must never return a memoized handle from an earlier call: C-15
deliberately revokes and resets control credentials mid-test, and a
caching implementation would silently exercise a stale credential instead
of a live one.

**Major M-5 -- C-14 vector 2's authenticate-only contraction documented.**
The provided branch was, and remains, a single `authenticate()` call
rather than a probe of every data/schema endpoint individually. The
test's docstring now states explicitly why that is sufficient today (both
peers gate every data-plane operation behind one `authenticate()` step,
design R-8) and what would require widening it (a future peer with a
data-plane entry point reachable without that step) -- a supervisor
ruling, overridable.

**Major M-6 -- C-15 vector 2 implements what `CONDITIONS.md` already
claimed.** The provided branch now snapshots `control_audit_events()`
before reset and asserts the pre-reset sequence survives as a PREFIX of
the post-reset trail (append-only across reset -- new events may be
appended, none rewritten or removed), and asserts via `list_credentials()`
that exactly one non-revoked control credential remains afterward.

**Major M-7 -- `SurfaceAbsent` gains `exempt_parameters`; the absence
helper's verification strengthened; `MitateDB-api` reverts to the full
surface.** See §15.1 (`SurfaceAbsent`'s own docstring), the M-7 paragraphs
now in §15.4's `MitateDB-api` bullet (superseding the original open_
session-exclusion account), and both test files' `_assert_control_
operation_absent_or_uniformly_refused`. Summary: `exempt_parameters` names
real, justified parameters that match a forbidden fragment by coincidence
but cannot carry the absent capability; the absence helper now requires
`signature_forbids_parameters`'s violations to EXACTLY equal the declared
exemptions (not merely a subset) and requires the declared evidence
`surface` to cover at least the peer's own `public_operation_callables()`
-- closing both a false-negative gap (an adapter exempting away a real
violation) and a new one this same review surfaced (an adapter shrinking
its evidence surface to dodge a violation elsewhere on the peer).

**Minors (all fixed):** C-15 vector 1's revoke loop now revokes the
actor's own credential last and passes no `destructive`/`confirmation`
fields, with a docstring note that this call site will need the
canonical confirmation phrase once contract Q-1 (design §0.5) is
adjudicated; `_control_plane_status` (both test files) now raises an
explicit, actionable `AssertionError` naming the missing key instead of
propagating a bare `KeyError`; C-14 vector 3-iv's `credentials_per_
application` saturation now uses in-band issuance (the control actor)
rather than the out-of-band `issue_credential` setup primitive, with
cleanup revokes; C-15 vector 4's secret-echo check now also asserts the
control actor's own secret (not only the application credential's) never
appears in an audit event; this document's §15.4 `r2db-api-http` bullet
is softened to note the live route-table check guards only the co-hosted
misconfiguration case under design R-1's default separate-ASGI-app
deployment shape, not the default shape itself.

**Nits (both fixed):** §15.8 above now says "one new value type" (not
"two") and separately calls out the new `exempt_parameters` field; C-14
vector 1's redundant-but-more-specific `not in {NOT_FOUND,
CAPABILITY_UNSUPPORTED}` pre-assertion is now commented explaining why it
is kept despite being logically implied by the membership check that
follows it.

**Item 10 (supervisor-authorized scope extension) -- `test_conditions_
register.py` gains a third check.** The original two checks are both
one-directional and cannot detect a condition's status regressing (e.g.
CONDITIONS.md text reverted to "not yet executable") while its test file
and markers remain collected and passing -- measured directly by mutation
M6 (§15.5), which the original two checks did not catch. A new test,
`test_every_marked_condition_id_maps_to_an_executable_status`, closes
this: every condition id carried by a collected `@pytest.mark.
condition(...)` marker must map to a CONDITIONS.md row whose Status
starts with `executable`.

**Form (b) authenticity (M5 disposition, documentation-only, no code
change).** Recorded in full in `CONDITIONS.md`'s C-14 status text and
both test files' module docstrings: the declared-unavailable form's
uniform `CAPABILITY_UNSUPPORTED` acceptance is adapter-honesty plus
review evidence at this port level, since `ConformanceDenial` carries no
provenance evidence the way `SurfaceAbsent`'s `surface`/`forbidden_
parameters` do (measured directly, mutation M5, re-measured as M9 under
this fix-round). A positive-existence check is deliberately DEFERRED
until a real form-(b) peer first registers, rather than speculatively
designed against no real example now.

**Re-verification:** full mutation table (M1-M9, all re-measured under
the strengthened M-7 helper) and exact pass counts are in this work's
implementation report (`WP1_IMPLEMENTATION_REPORT.md`), fix-round
section.

### 15.10 WP-5: the flip -- `r2db-api` (both plugs) leave §15.4's uniform `SurfaceAbsent` branch

`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` work package WP-5 (the
single-commit declaration flip) lands the actual `/control/v1` product
code (`control_plane.py`/`control_http.py`/`control_main.py`, WP-2
through WP-4) and, in the same commit, both `r2db-api` plugs' own
`control_plane` declaration flips to `enabled`. §15.4's "all three plugs:
uniformly `SurfaceAbsent`" is therefore no longer the current state for
two of the three registered adapters -- current adapter x phase state:

| plug | branch as of WP-5 |
|---|---|
| `r2db-api` (in-process) | **provided** -- `ControlPlaneService` + `InMemoryControlBackend`, constructed directly on the plug's own `DataService`/`ControlAuthority`/`CredentialStore` (§15.2's own abstract-method group is now real service calls, not `_control_surface_absent`) |
| `r2db-api-http` | **provided** -- a real `/control/v1` ASGI app driven by real HTTP (`httpx`/`ASGITransport`), `bootstrap`/`reset` run as the real `python -m r2db_api.ops` CLI subprocess. Assembled via the shared product assembler `r2db_api.control_main.assemble_control_stack` (round-2 review MINOR-3 -- the same assembly core `build_control_app` itself calls) rather than calling `build_control_app` itself, so this adapter can hold a closeable handle back to the 4 Postgres stores it needs to periodically rebuild `ControlPlaneService` and avoid exhausting `r2dbsvc_controlplane`'s real `CONNECTION LIMIT 10` (§13.3's own anticipated "session-scoped adapter shares one R-7 window with everything else" concern, measured this WP against real ordinary fixture-building traffic once C-08's own operations moved in-band too); this adapter's remaining departure from `build_control_app` is only that it does not drive ASGI lifespan (it closes the 4 stores directly instead) |
| `MitateDB-api` | unchanged -- still `SurfaceAbsent` (§15.4 applies to this plug only, as of WP-5) |

§15.4's own per-plug evidence description (the shared `_control_surface_
absent` helper, `public_operation_callables()` as signature evidence, the
HTTP plug's live-route-table assertion) is retired for the two flipped
plugs along with the helper itself -- `MitateDB-api`'s own §15.4 entry is
unaffected and remains the accurate description of that plug's real
surface. Full implementation detail, the provided-branch defects WP-1's
static-review-only gate could not catch until first execution, and the
mutation-injection re-verification for this WP are in
`WP5_IMPLEMENTATION_REPORT.md`.

## 16. v1.6 port revision (coordinated with docs/design/DESTRUCTIVE_CONFIRMATION_V1.md work package WP-2)

`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §R-6 (Q-1 effectivation:
declare-and-echo destructive confirmation, contract 1.2.0) requires four
port-level changes plus a new common condition suite. As with §12-§15, this
is a coordinated revision across the NORMATIVE surface this document's §4
defines and all three registered plugs, in one change.

### 16.1 `ConformanceDenial.details` (additive)

`ConformanceDenial.__init__` gains an additive, keyword-only `details:
Mapping[str, Any] | None = None`, stored as `self.details: dict[str, Any]`
(never `None` -- an empty mapping when nothing is available, so every
caller can read `denial.details.get(...)` unconditionally). This does NOT
weaken the exception's existing message-exclusion rationale (§4.1: never
carrying the native exception's `str()`, to keep a payload-echo assertion
made directly against `ConformanceDenial` itself meaningful) -- `details`
is never free text, and each plug wires only the peer's own genuine
structured details mapping, never a string built from interpolating
request data:

- `r2db-api` (in-process): `getattr(exc, "details", None)` off the caught
  `FoundationError` -- that class already carries a real `details: dict`
  attribute (`errors.py`), used unchanged for this new purpose.
- `r2db-api-http`: the real problem+json response's own `details` object
  (`_HttpFailure.body["details"]`, via a new `_failure_details()` helper),
  exactly as `errors.py`'s `FoundationError.to_dict()` publishes it over
  HTTP -- never assembled or interpreted by the plug.
- `MitateDB-api`: `getattr(exc, "details", None)` off the caught
  `FoundationError` -- that peer's own error base class has NO `details`
  attribute at all today (untouched by this WP, per CLAUDE.md's "peer 実装
  には一切触れない"), so this always falls through to an empty mapping;
  written as a `getattr` (not simply omitting `details=`) so the plug picks
  up a real attribute for free the moment a future WP adds one to that
  peer's own error hierarchy, without a second edit to this call site.

`adapter.assert_no_payload_echo_in_details(details, payload, *, context="")`
is `assert_no_payload_echo`'s identical substring/length-floor check,
applied to every string value of a `details` mapping instead of a native
exception's `str()` -- used by C-06 vector V8 (below).

### 16.2 `VALID_CONFIRMATION`: declare-and-echo

Before this revision, every plug resolved the `VALID_CONFIRMATION`
sentinel to a hardcoded, peer-specific fixed token (`r2db-api`: the
literal string `"DELETE"`; `MitateDB-api`: the boolean `confirm=True`).
Contract 1.2.0's own client obligation forbids exactly this for a peer
declaring `contract_version >= 1.2.0` ("句の綴りは契約で固定せず...
クライアントは常に復唱", Q1-D2) -- a real client obtains the phrase from
the peer's own denial and echoes it back; hardcoding it defeats the
protocol's own state-fingerprinting guarantee.

Two new shared, normative-adjacent functions on the port (`adapter.py`)
implement the dispatch and the resolution, so no plug hand-rolls either:

- `parse_semver(version: str) -> tuple[int, int, int]` / `contract_
  version_at_least(contract_version: str, minimum: str) -> bool`: a
  MAJOR.MINOR.PATCH string parsed into a comparable int tuple, never
  compared as a string (the design's own named trap: `"1.10.0" < "1.2.0"`
  as strings, but `1.10.0 >= 1.2.0` as versions).
- `resolve_valid_confirmation(*, contract_version: str, legacy_token: Any,
  probe: Callable[[], Any]) -> Any`: below 1.2.0, returns `legacy_token`
  unchanged (every plug's own pre-1.6 behavior, preserved byte-for-byte for
  a 1.1.0 peer); at or above 1.2.0, calls `probe()` (expected to present
  the SAME destructive request the caller is about to retry, with
  `destructive=True` and no confirmation, through whatever real entry
  point a genuine client would use), and returns the `required_
  confirmation` phrase read directly off the peer's own
  `DESTRUCTIVE_CONFIRMATION_REQUIRED` denial -- never guessed, hardcoded,
  or assembled by this port itself. A probe that succeeds outright, denies
  with the wrong code, or denies without a non-empty `required_
  confirmation` in its `details` raises `AssertionError` (a suite finding,
  not a harness bug): each is a real, observable non-conformance a
  contract_version >= 1.2.0 peer must not exhibit.

Every plug now exposes a small private pair, `_declared_contract_version()`
(cached after the first real `capability_document()` call -- a peer's
declaration is static for that adapter instance's whole lifetime, so
re-fetching it on every destructive-operation call site would only add
cost) and `_resolve_confirmation(confirmation, *, probe, legacy_token)` (the
`VALID_CONFIRMATION`-sentinel dispatch itself, delegating to `adapter.
resolve_valid_confirmation`), and applies this at every call site that
previously hardcoded a fixed token: `delete()` (all three plugs) and the
per-operation batch item builder behind `attempt_batch_with_addresses`
(`_build_mutation_item`, both `r2db-api` plugs; `MitateDB-api`'s own
per-op loop). Each such call site's probe presents the SAME operation/
entity/where shape the real (non-probe) call is about to use, snapshotted
before `confirmation` is attached, so the phrase read back is valid for the
call that immediately follows it. As of this WP, every registered plug
still declares `contract_version: 1.1.0` (r2db/MitateDB's own flips are
WP-3/WP-5's single-commit work), so `resolve_valid_confirmation` always
takes the `legacy_token` branch in practice today -- the declare-and-echo
branch is written to spec but not yet exercised against a real peer (see
§16.5's own disclosure, mirrored in `CONDITIONS.md`'s C-06 row).

The `VALID_CONFIRMATION` sentinel's own doc-comment (`adapter.py`, the
block immediately preceding its definition) is rewritten for this new
two-mode resolution; the sentinel's *external* contract (`None`/
`VALID_CONFIRMATION`/any other string, from a call site's point of view)
is unchanged.

### 16.3 New port op: `drop_entity`

A 15th abstract method, `drop_entity(self, session, entity, *, destructive:
bool, confirmation: str | None) -> None` -- `SchemaOperationRequest.
operation == "drop_entity"`'s destructive twin to `create_unique_index`,
following the identical pass-through convention `delete()`'s own docstring
already establishes (`destructive` always faithful; `confirmation` follows
the `VALID_CONFIRMATION` protocol). `drop_index` is deliberately left to a
future port revision (Q1-D5; tracked as C-06 v2 in the design's own ledger,
`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §R-6 item 3).

- `r2db-api` (both plugs): real, executable vocabulary already
  (`structured.py`'s `bind_schema_operation`/execution branches accept
  `drop_entity` unconditionally) -- presented to the same single
  `DataService.schema()` (in-process) / `POST /v1/schema/operations`
  (HTTP) dispatcher every other schema operation already uses, exactly
  like `create_unique_index`.
- `MitateDB-api`: `SurfaceAbsent`, mirroring `create_unique_index`'s own
  reasoning verbatim -- `ApplicationDeveloper.create_collection(name,
  fields)` is this peer's only schema-mutation call and has no drop/
  destroy parameter of any kind; no other developer-facing method exists
  on this peer's public surface (confirmed by source inspection) that
  could even receive a destructive drop request. `forbidden_parameters=
  ["drop", "destroy"]` against the same `public_operation_callables()`
  evidence `create_unique_index` already uses.

### 16.4 Shared absence mechanism: `conformance-tests/absence.py`

`test_c14_authority_boundary.py`'s own `_assert_control_operation_absent_
or_uniformly_refused`/`_assert_uniform_absence_form`/`_unclassified_hint`/
`_assert_is_contract_code` (previously private, module-local helpers) move
to a new shared module, `conformance-tests/absence.py`, as `assert_
control_operation_absent_or_uniformly_refused`/`assert_uniform_absence_
form`/`unclassified_hint`/`assert_is_contract_code`. This is a pure move,
not a revision: pass/fail behavior for C-14 is equivalent, not byte-for-
byte identical (review correction m-7) -- that file's own suite stays
green against the shared module, but the move itself generalized
assertion-message text (no longer says "control-plane" specifically) and
turned the `{"credential", "control"}` forbidden-vocabulary check into the
optional `required_forbidden_vocabulary` parameter, described below.
`test_c14_authority_boundary.py` now imports the shared functions and
wraps them in two thin, file-local functions of its own original names
that additionally pass `required_forbidden_vocabulary=("credential",
"control")` (C-14's own vocabulary-narrowness guard, §15.9's independent-
review-driven addition, kept file-local rather than promoted to the shared
module's default -- a capability's forbidden-parameter vocabulary is
specific to what that capability's own absence claim is about, and does
not generalize).

The shared function gains one new, optional keyword-only parameter to
carry this: `required_forbidden_vocabulary: Sequence[str] = ()` (both on
`assert_control_operation_absent_or_uniformly_refused` and `assert_
uniform_absence_form`, the latter passing it through unchanged to every
call it makes). Empty by default, so a caller with no such vocabulary
requirement (C-06's own use, below) need not supply one.

C-06 vector V6 (`drop_entity` state-fingerprint invalidation) reuses this
exact shared mechanism for `MitateDB-api`'s absent branch, and vector V7
(control-credential revoke gate) reuses it for any peer without a real,
`enabled` control-plane surface -- proving this extraction's own stated
purpose (design R-6 item 4 / WP-0 m-4): a second condition suite needing
the identical "structurally absent, independently re-verified, OR
uniformly `CAPABILITY_UNSUPPORTED`" mechanism no longer duplicates or
risks drifting from C-14's own.

### 16.5 C-06 suite: `test_c06_destructive_confirmation.py`

New file, `@pytest.mark.condition("C-06")`. Branches on the peer's own
declared `contract_version` (`adapter.contract_version_at_least`, §16.2),
mirroring C-14's `_control_plane_status` dispatch pattern:

- **strict branch (>= 1.2.0)**: vectors V1-V8 (unconfirmed delete denied
  with all four declaration keys present/non-empty/null-or-non-empty per
  design R-1-2's `details_rules`; `destructive: false` with an otherwise-
  correct phrase still denied -- see that test's own docstring for why
  V2b's literal "field omitted on the wire" collapses onto the identical
  port-level assertion as V2, this port's `delete()` signature always
  requiring an explicit `destructive: bool`; full-match adversarial checks
  -- suffix, a proper prefix DERIVED from the real phrase never
  hardcoded, case-changed, another entity's/operation's/selection's
  correct phrase -- all denied, state unchanged; phrase determinism
  across repeated probes and across a second credential for the same
  Application; probe-then-echo executes; `drop_entity`'s state-fingerprint
  invalidation after an unrelated schema change -- `create_unique_index`
  stands in for the design text's own "`add_field`" example, since this
    port has no standalone `add_field` operation and `create_unique_index`
  bumps the identical monotonic state fingerprint design R-2 item 1
  requires of "every schema operation" -- with the shared absence
  mechanism (§16.4) for a surface-absent peer, plus a V3-equivalent
  adversarial subset against `drop_entity` itself; the in-band last-
  control-credential revoke gate, control-plane-provided peers only, `
  audited: true` included, with the shared absence mechanism for a
  surface-absent peer otherwise; no payload-echo in any declaration
  value, via §16.1's `assert_no_payload_echo_in_details`).
- **baseline branch (< 1.2.0)**: every vector instead asserts the pre-1.2.0
  floor -- an unconfirmed destructive delete never executes (whatever
  code), and `VALID_CONFIRMATION` succeeds -- against a freshly `insert()`-
  ed, uniquely-marked row of its own (never the shared fixture's single
  seeded row), so this floor check is safe to call repeatedly.

**As of this WP, all three registered adapters still declare
`contract_version: 1.1.0`** (§16.2), so every one of the 8 vector tests
takes the baseline branch for every currently-registered adapter today --
the strict branch's own vector bodies are exercised, in this WP, only by
this file's own direct unit tests of the pure dispatch/derivation
functions they depend on (`parse_semver`/`contract_version_at_least`/
`resolve_valid_confirmation`/`assert_no_payload_echo_in_details`/the
adversarial-variant deriver), proving those skeletons import and compute
correctly, not that a real >= 1.2.0 peer satisfies them end-to-end. First
real execution of the strict branch is WP-3's own completion condition
(`r2db-api`, both plugs) and WP-5's (`MitateDB-api`) -- disclosed here and
in `CONDITIONS.md`'s C-06 row, per design R-6's own "将来 peer の受け入れ
口として残置し、未実行分岐である旨を明記" (mirroring §16.4's C-14
precedent for the exact same kind of disclosed, deliberate floor).

**Applications-headroom regression (found, root-caused, and fixed this
WP -- full record, since the first-pass diagnosis during implementation
was itself wrong and had to be corrected under review):**

A first version of this file made TWO independent out-of-band `provision_
application` sources uncached, and their combination broke `test_c15_
bootstrap_reset_lifecycle.py`'s own `register_application_inband` audit
call with `LIMIT_EXCEEDED` (`details={"resource": "applications", "limit":
100}`) at session end, on BOTH r2db plugs. The regression was verified
genuine (not pre-existing) the correct way: the whole WP's diff was
stashed, the full root suite was run against the byte-identical 7d739be
tree (727 passed, 0 failed), then the diff was restored and the full suite
re-run with this file present (2 failed) and absent (0 unexpected
failures) -- an earlier attempt to establish "pre-existing" by running a
file *subset* under `git stash` was correctly rejected on review: a
subset's collection order and shared-adapter state are not the same
condition as the full suite, so it cannot stand in for this comparison.

The two sources, both now fixed:

1. This file's own `fx` override (below) builds a full two-Application
   `Fixture` via `adapter.build_fixture()`. Left at conftest.py's own
   function scope, 8 vector tests x 3 adapters would call this 24 times
   (16 `provision_application` calls per r2db adapter alone) -- so `fx` is
   overridden here with a same-named, module-local fixture (pytest
   resolves a fixture defined in the test module itself in preference to
   conftest.py's for tests in that module) that memoizes ONE real,
   unmodified `Fixture` per adapter for this whole module's run. This
   suite never reads `Fixture`'s B-side fields (`app_b`/`runtime_b`/
   `b_only_entity` -- every vector operates within a single Application),
   so nothing is lost by sharing one. Every check that might actually
   mutate state operates on a freshly `insert()`-ed, uniquely-marked row
   of its own (`_assert_baseline_delete_invariant`), so repeated
   invocations against the SAME cached `Fixture` never step on each other.
2. **The dominant contributor, missed by the first pass:** `_branch_for`
   (the strict/baseline dispatch every one of the 8 vector tests calls
   first) calls `_contract_version`, which called the PUBLIC `adapter.
   capability_document()` directly -- and every registered plug's
   `capability_document()` provisions its OWN fresh, disposable probe
   Application on every single call (it has no anonymous path; see each
   plug's own docstring). Called uncached from 8 vector tests, this alone
   cost 8 more `provision_application` calls per adapter -- more than
   `fx`'s own 2. Fixed the same way: `_contract_version` now memoizes the
   peer's declared `contract_version` (static for the whole run regardless)
   in a second module-level cache, cutting this to 1 call per adapter.

With both fixes, this file's total added footprint is 1 (`capability_
document` probe) + 2 (`fx`'s own two Applications) = 3 out-of-band
Applications per r2db adapter for the file's ENTIRE run -- smaller than a
single ordinary condition-test file's own per-test-uncached footprint
elsewhere in this suite. Verified: the full root suite passes GREEN twice
consecutively (0 failed, 0 skipped both times) with this file present, and
`conformance-tests/` alone and `r2db-api/tests/test_postgres.py` alone are
both green. No SI-08 limit value, no `test_c15_*` assertion, and no
conftest.py shared-fixture semantics were changed to reach this state --
the fix is confined entirely to this file's own two caches.

### 16.6 `CONDITIONS.md`

C-06's row moves from "not yet executable" to "executable (three
adapters)", with the strict/baseline branch split and the "all three
adapters still declare 1.1.0 today" floor stated explicitly (mirroring how
C-14's own row records its WP-5 flip state) -- this row's own text is the
authoritative disclosure that the strict branch is unexecuted in this WP,
not an incidental mention buried in this design document alone. C-12's
existing "delete は C-06 へ" note (`test_c12_capability_agreement.py`'s own
`attempt_mutation` docstring and CONDITIONS.md's C-12 row) is unchanged and
remains accurate: C-12 still deliberately never exercises `delete` in its
own capability-agreement context.

### 16.7 Compatibility impact (mirrors §12.7/§13.8/§14.3/§15.8)

- `ConformanceDenial.details` is additive (a new optional constructor
  keyword, defaulting to an empty mapping); no existing call site that
  constructs or catches a `ConformanceDenial` needs to change.
- `VALID_CONFIRMATION`'s external contract (`None`/`VALID_CONFIRMATION`/
  any other string) is unchanged; only its INTERNAL resolution gained a
  version-gated second mode. Every existing test that already uses
  `VALID_CONFIRMATION` (`test_c01_scope_binding.py`, `test_c03_structured_
  injection.py`, `test_c17_declaration_agreement.py`, `test_c18_revision_
  precondition_semantics.py`) is unaffected: all three registered plugs
  still declare 1.1.0, so `resolve_valid_confirmation` still returns each
  plug's own unchanged legacy token for every one of those call sites,
  verified this WP by running the full existing suite unmodified against
  all three plugs (see this work's own implementation report for the
  pass count).
- `drop_entity` is a new abstract method; a plug that does not implement
  it fails to instantiate (Python's own `ABC` enforcement) -- all three
  registered plugs implement it as of this revision (§16.3), so this is
  not a live compatibility break for any currently-registered adapter.
- `conformance-tests/absence.py`'s extraction preserves every existing
  call site's observable behavior for C-14 (§16.4); no C-14 test assertion
  changed.

## 17. v1.7 port revision (coordinated with docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md work package WP-3)

**Backfilled 2026-09-02** (phase 4 WP-1 review finding, this document's own
§18 header note before this backfill): `conformance-tests/adapter.py`
already names its `ScopedBatchOperation`/`attempt_cross_entity_batch`
addition "port v1.7" in its own source comments, but this document never
carried a corresponding numbered section for it. This section states only
the facts already recorded elsewhere (`adapter.py`'s own comments,
`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §3/§10.3) --
it is a record backfill, not a new design decision, and changes no code.

Port v1.7 (phase 3.5 WP-3, contract 1.3.0's CCR-15 cross-entity semantics)
added:

- **`ScopedBatchOperation`**: `BatchOperation` (§14) plus a required
  `entity` field -- one element of a cross-entity batch has no single
  shared entity for the whole call to name the way `attempt_batch_with_
  addresses`'s own `entity` parameter does, so each operation names its
  own (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §3).
- **`ConformanceAdapter.attempt_cross_entity_batch(session, operations:
  Sequence[ScopedBatchOperation])`**: presents one atomic unit across
  multiple entities to the peer's real `POST /v1/data/mutations`-
  equivalent entry point (contract `cross_entity_mutate`). Availability is
  `capability_document()["capabilities"]["cross_entity_mutation"]["status"]
  in ("enabled", "partial")`. `destructive`/`confirmation` on any
  `delete`-class element within the batch reuse the existing C-06
  probe/echo machinery, unchanged.
- **`conformance-tests/test_c16_cross_entity_atomicity.py`** (new file,
  C-16 registered and made executable): vectors V1-V5 plus two vacuity
  guards (`test_at_least_one_available_adapter_can_construct_the_v3_
  boundary_vector`, and V5's own per-adapter absence-form pin).
- **C-12/C-11 extensions**: C-12 gained a `cross_entity_mutation`
  declared-vs-executed direction; C-11 gained the `raw_cross_entity_
  mutation_result` optional raw-accessor family (reverse-validated
  against the same closed `MutationResult` schema the per-entity endpoint
  already uses).
- **`CONDITIONS.md`**: C-16's row moved to executable (four adapters) --
  as of that WP, both `MitateDB-api` adapters took the PROVIDED branch
  (`cross_entity_mutation: partial`) and both `r2db-api` adapters took the
  ABSENT branch (`unavailable`, P35-D1).
- Four plug files edited (both `r2db-api` and both `MitateDB-api`
  adapters), mirroring phase 3 WP-2.5's own "4-file commit" shape
  (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` review m-7).

### 17.1 Compatibility impact

- `attempt_cross_entity_batch` is a new abstract method; a plug that does
  not implement it fails to instantiate (Python's own `ABC` enforcement)
  -- all four registered plugs implemented it as of this revision.
- `ScopedBatchOperation` is additive (a new dataclass); no existing
  `BatchOperation` caller is affected.

## 18. v1.8 port revision (coordinated with docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md phase 4 WP-1)

`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §8.3 (port への追加) requires
three new port-level operations plus an extended meaning for `SurfaceAbsent`,
so that the common suite can observe `audit_query` at all -- this WP does
not implement a durable audit sink or a real `audit_query` on any peer
(phase 4 WP-2/WP-3's own scope); it only builds the port-side observation
path and wires all four currently-registered plugs to it, honestly taking
the `SurfaceAbsent` branch throughout (§18.4).

### 18.1 Three new abstract methods

Added to `ConformanceAdapter` immediately after `control_audit_events()`
(port v1.5, §15), before the `# --- application plane ---` group:

- `audit_query(self, actor: CredentialHandle | ControlCredentialHandle, request: Mapping[str, Any]) -> Mapping[str, Any]`
  -- presents a real `AuditQueryRequest`-shaped mapping to the peer's
  control-host `audit_query`-equivalent entry point and returns the raw
  `AuditResult` document on success. `request` is a raw mapping, not a
  typed port object (mirrors `capability_document()`'s own "never a value
  the adapter invents" discipline; `AuditResult`/`AuditQueryRequest` stay
  observed as raw JSON-shaped documents, exactly as the design's own §8.2
  reverse-validation approach needs).
- `flush_audit_buffer(self) -> None` -- adapter-privileged hook (same
  category as `control_audit_events()`) forcing the peer's own bounded
  data-operation-event buffer (design D-4) to flush synchronously, so a
  test can observe a buffered event without depending on the buffer's own
  real flush timer.
- `audit_visibility_lag_ms(self) -> int` -- reads the peer's own declared
  `visibility_lag_ms` (design D-6: derived from the two durable-write
  connection timeouts) off its real `audit_query` capability declaration.
  Exists specifically so a condition test never writes a fixed `sleep` of
  its own (design principle 4 applied to timing: a hardcoded wait is
  exactly the kind of assumption-not-proof this design already forbids
  elsewhere, and is additionally a structural source of flaky reds under
  real-PostgreSQL load, per the work order's own testing discipline).

All three are written against the REAL, eventual dispatch shape (read the
live capability declaration, then present a real request) rather than a
stub -- see §18.4.

### 18.2 Declare-first dispatch (work order WP-1 supplementary ruling 1)

Unlike every other in-band port operation (§15), which presents a request
and lets the PEER's own authorization/capability checks decide the
outcome, `audit_query` (and, by the same rule, `flush_audit_buffer`/
`audit_visibility_lag_ms`) reads the peer's OWN `audit_query` capability
declaration FIRST, before presenting any request at all -- the same
"capability refusal precedes every other check" discipline §15 already
established for in-band `role="control"` issuance (C-14 vector 3), applied
one layer earlier: at the port's own dispatch, not inside the peer.

- `audit_query` undeclared, or declared anything other than
  `enabled`/`partial` (most commonly `unavailable`) -> `SurfaceAbsent`,
  without presenting any request. This holds even though a real,
  routed HTTP entry point may exist that would itself answer
  `CAPABILITY_UNSUPPORTED` if reached directly (design D-5/M-4's dual
  posture: AUDIT DSN unset still registers the route) -- this port method
  never reaches that route in the first place once the declaration itself
  says the surface is not provided.
- `audit_query` declared `enabled`/`partial` -> a real request is
  presented with `actor` exactly as given (no pre-filtering by credential
  kind, the same convention every other in-band method already follows).
  Returns the peer's raw `AuditResult` document on success (PROVIDED), or
  raises `ConformanceDenial` with a genuine contract-code (design's own
  §8.1 vector 3: `FORBIDDEN` for an application credential, `VALIDATION_
  FAILED` for a malformed cursor, etc.). A 404, a 405, or an
  unclassified/`UNCLASSIFIED` response in this branch is a suite failure,
  not a denial (sink truthfulness -- `test_c09_declared_enabled_audit_
  query_actually_answers`, `conformance-tests/test_c09_audit_evidence.py`).

### 18.3 `SurfaceAbsent`'s extended meaning

Before this revision, `SurfaceAbsent` meant only "no Python callable on
this peer's public surface could structurally receive this request at
all" (§4.3's `structurally_absent` mechanism; every pre-v1.8 raise site
proves this by source inspection). `audit_query`/`flush_audit_buffer`/
`audit_visibility_lag_ms` extend this meaning for themselves specifically:
they ALSO raise `SurfaceAbsent` for a second, narrower reason -- "this
deployment's own capability declaration says it does not provide the
audit surface" -- a claim about the peer's DECLARED posture (§18.2),
checked before any request is presented, not only about whether a Python
callable structurally exists.

As of this WP, before any peer implements a real `audit_query` entry
point at all, both readings coincide for every currently-registered
plug -- there genuinely is no callable either way. A future peer that
implements a real entry point internally (phase 4 WP-2/WP-3) but leaves
it declared `unavailable` (AUDIT DSN unset) still raises `SurfaceAbsent`
under the extended reading, even though a real callable now exists
somewhere on that peer. `conformance-tests/absence.py`'s own module
docstring documents this same extension from the shared-assertion-helper
side, and explicitly excludes `audit_query` from its general two-form
("surface-absent" XOR "declared-unavailable", `assert_control_operation_
absent_or_uniformly_refused`) mechanism -- `audit_query` collapses form
(b) into form (a) for itself, rather than participating in the ordinary
split every other control-plane capability still uses unchanged.

### 18.4 The four plugs, as of this WP

All four currently-registered plugs (`r2db-api`, `r2db-api-http`,
`MitateDB-api`, `MitateDB-api-http`) implement all three new methods
against the real, eventual dispatch shape:

- A shared per-plug `_audit_query_status()` helper reads `audit_query`'s
  declared `status` via that plug's OWN privileged `control_credential()`
  -- never via the `actor` a caller of `audit_query` supplies, since
  `control_plane.authority` fails an APPLICATION credential closed on
  `control_capabilities` itself; gating the declare-first check on
  `actor`'s own authority would make C-09 vector 3 (application
  credential -> `FORBIDDEN` on `audit_query` once enabled) structurally
  unreachable.
- `audit_query`'s PROVIDED branch calls a well-grounded forward reference
  to each peer's own eventual real entry point -- `ControlPlaneService.
  audit_query(secret, request)` (in-process plugs, following that
  service's own existing per-endpoint method-naming convention) or a real
  HTTP `POST /v1/audit/query` against the CONTROL client, never the
  data-plane one (HTTP plugs, design R1: the contract path string is
  served by the control host as `control_endpoints.audit_query`'s own
  alias, design D-5; each HTTP plug's own `audit_query` method carries
  this rationale as an in-line comment, per the work order's own
  instruction).
- `flush_audit_buffer`'s PROVIDED branch deliberately raises
  `NotImplementedError` on all four plugs instead of guessing a specific
  WP-2/WP-3 buffer-flush mechanism shape: unlike `audit_query`,
  `flush_audit_buffer` names no contract endpoint at all (it is an
  adapter-privileged test hook), so no naming convention exists yet to
  extrapolate from. This branch is unreachable as of this WP (every
  plug's own `audit_query` status is `unavailable`), so this is honest
  dead code, not a functional gap.
- As of this WP, `_audit_query_status()` always returns `"unavailable"`
  for all four plugs (`capabilities()`/`control_capabilities()` always
  publish `audit_query: {"status": "unavailable"}` until WP-2(b)/WP-3(b)'s
  own flip), so `audit_query`/`flush_audit_buffer`/`audit_visibility_
  lag_ms` always take the `SurfaceAbsent` branch today, each raised with
  `forbidden_parameters=["audit"]` and `surface=self.public_operation_
  callables()` (this port's own existing convention for every
  `SurfaceAbsent` raise site, e.g. `attempt_cross_entity_batch`/`create_
  unique_index`/`drop_entity`) -- never the C-14-specific `{"credential",
  "control"}` vocabulary, which is a different capability's own claim.

### 18.5 `conformance-tests/test_c09_audit_evidence.py` (new file)

Makes C-09 executable for the first time (`CONDITIONS.md`'s prior status:
"not yet executable (common suite) -- peer-local evidence only"). Four
vectors (design §8.1) plus a declaration-truthfulness test plus two
vacuity guards -- see that file's own module docstring for the full
rationale; not duplicated here. All 21 non-`xfail` cases pass as of this
WP (every vector's "provided" half is unreachable and therefore untested
by real execution, same disclosure as this document's own §16.5-style
"written to spec but not yet exercised" pattern), and the whole-registry
vacuity guard is registered `xfail(strict=True)`, removed only by the
last flip WP (WP-3(b), same commit as that flip).

### 18.6 `conformance-tests/test_c11_response_schema_conformance.py`

Two additions, closing part of that file's own previously-documented
`AuditResult`/`AuditQueryRequest` zero-coverage gap (subordinate ruling
7(A)'s reverse-validation requirement): `test_c11_audit_result_reverse_
validates_against_the_closed_schema` (real-document reverse-validation via
`audit_query`, declare-first, `SurfaceAbsent` for all four plugs as of
this WP -- honestly still zero real-document coverage, but now a live
path that starts validating automatically the moment a peer flips) and
`test_audit_query_request_closed_schema_rejects_an_excess_key` (a
schema-only positive control needing no adapter at all, closing that half
of the gap outright today).

### 18.7 Compatibility impact (mirrors §12.7/§13.8/§14.3/§15.8/§16.7)

- The three new abstract methods are additive to the ABC; a plug that
  does not implement them fails to instantiate (Python's own `ABC`
  enforcement) -- all four registered plugs implement them as of this
  revision, so this is not a live compatibility break for any
  currently-registered adapter.
- `SurfaceAbsent`'s constructor signature is unchanged; only its
  documented MEANING is extended for these three methods specifically
  (§18.3). No existing `SurfaceAbsent` raise site or consumer changes
  behavior.
- `conformance-tests/absence.py`'s shared two-form mechanism
  (`assert_control_operation_absent_or_uniformly_refused`/`assert_
  uniform_absence_form`) is unchanged in code; only its module docstring
  gained a disclosure that `audit_query` does not participate in the
  two-form split. No existing caller of that mechanism (C-06/C-14/C-16)
  is affected.
- The contract's own `versioning.version_binding` conditional-obligation
  discipline for 1.4.0 (`spec/CCR_DISPOSITION.md` subordinate ruling 9)
  is what makes `_audit_query_status()` always reading `"unavailable"`
  today, not a limitation of the port -- port v1.8 itself imposes no new
  requirement on a peer that has not yet flipped.

## 19. v1.9 port revision (coordinated with docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md phase 5 WP-1)

`docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §6.2 (D-2) requires
one new port-level operation so the common suite can observe contract
1.4.0's unconditional obligation (b), same-label-amended by
`spec/CCR_DISPOSITION.md` subordinate ruling 10 item 2: a control/audit
credential presented on the DATA-plane host's own `POST /v1/audit/query`
alias is not thereby owed acceptance merely because that host also
declares `control_plane` as something other than `unavailable`. This WP
does not change any peer's product behavior at all -- both peers' real
data-plane alias handlers already reject a control/audit credential with
`AUTH_INVALID` (their application-only credential store never recognizes
it); this revision only builds the port-side observation path and wires
all four currently-registered plugs to it.

### 19.1 Two new abstract methods

Added to `ConformanceAdapter` immediately after `audit_visibility_lag_ms()`
(port v1.8, §18.1), before the `# --- application plane ---` group:

- `audit_query_on_data_plane_host(self, actor: CredentialHandle |
  ControlCredentialHandle, request: Mapping[str, Any]) -> Mapping[str,
  Any]` -- presents `request` (the same raw `AuditQueryRequest`-shaped
  mapping `audit_query` takes) to this peer's DATA-PLANE host's own
  `POST /v1/audit/query` alias -- never the control host `audit_query`
  reaches, the mirror image of that method's own "control base URL,
  never the data-plane one" rule (§18.4/design R1).
- `control_surface_cohosted_with_data_plane(self) -> bool` -- fix-round
  addition (F-2/F-3, independent review). Declares, for THIS test
  harness's own construction, whether the control surface and the
  data-plane host are provided on the same host/process. A pure topology
  fact, not derived from any request; see §19.3 for why this exists and
  how `test_c09_data_plane_host_audit_query_alias_rejects_control_
  credential_unless_cohosted` uses it.

Unlike `audit_query`/`flush_audit_buffer`/`audit_visibility_lag_ms`
(port v1.8), `audit_query_on_data_plane_host` carries NO declare-first
dispatch gated on `audit_query`'s own status: the obligation it observes
binds on `control_plane` (whether a control surface is provided at all),
not on whether `audit_query` itself is `enabled`/`partial` -- the same
distinction `versioning.version_binding`'s own 1.4.0 unconditional item
(b) draws from its conditional items (1)-(6).

### 19.2 Reaching the alias handler itself (design §6.2) -- honest per-plug fidelity

D-2's contract proposition is "the data-plane host's `POST /v1/audit/
query` alias endpoint does not accept a control credential" -- so this
method is required to reach the alias HANDLER ITSELF, not merely the
peer's authentication surface in general, wherever a plug genuinely can.
Fix-round F-4 (independent review) corrected this section's own prior
overclaim ("both reach the real handler's own full behavior") -- what
each plug ACTUALLY does:

- **HTTP plugs** (`r2db-api-http`/`MitateDB-api-http`) send a real POST
  to the DATA base URL (`self._client`, never `self._control_client`) --
  the mirror image of `audit_query`'s own control-only client choice, and
  a genuine, full-fidelity round trip through the real ASGI handler. This
  is a genuinely new HTTP path for both adapters: `audit_query` above
  documents that it "reaches it via the CONTROL base URL, never the
  data-plane one", so no existing method already exercised this route.
- **`r2db-api` (in-process)** calls the real `DataService.authenticate`
  then the real `DataService.deny_unsupported` -- the exact two product
  methods `http.py::post_audit_query`'s own body calls, in the same
  order. One disclosed fidelity gap (`conformance-tests/CONDITIONS.md`
  C-09 limit (c)): `request_id` is not threaded through this in-process
  call, unlike the real handler's own `_authenticate(request, service)`,
  which passes the ASGI request's own `_request_id(request)` -- this
  harness call has no `Request` object to read one from.
  `deny_unsupported`'s own second step is unreached in practice
  (`authenticate` always raises `AUTH_INVALID` first, since this
  foundation's application-only `CredentialStore` never recognizes a
  control/audit credential), so the gap has no observable effect today.
- **`MitateDB-api` (in-process)** calls the real `MitateDataService.
  open_session`, which reaches the same `auth.CredentialStore.
  authenticate` call `HttpService.authenticate` itself makes first -- a
  real product-code call for the FIRST step, same as r2db-api. The
  SECOND step is NOT a call into a real product function: `http.py::
  post_audit_query`'s own second step (`raise CapabilityError("audit
  evidence query requires control/audit authority this peer does not
  expose here")`) is written inline in that HTTP handler's body, with no
  separate importable product-code callable for this plug to invoke
  instead -- unlike r2db-api's `DataService.deny_unsupported`, a real,
  reusable method. This plug's second step is therefore a literal,
  hand-written copy of that inline message string (disclosed,
  `CONDITIONS.md` C-09 limit (c)), not a call to product code -- and, as
  with r2db-api, unreached in practice since `open_session` always
  raises `AUTH_INVALID` first.
- No plug currently registered needed the narrower "authentication
  surface only" fallback design §6.2 anticipates for a plug that cannot
  reach even the first step at all; if a future plug needs it, that
  plug's own limitation must be disclosed on `conformance-tests/
  CONDITIONS.md`'s C-09 row (design §6.3), naming the plug and stating it
  observes the authentication surface rather than the alias handler.

### 19.3 Judging `provided` by declared topology, not by response content (fix-round F-2/F-3)

The port revision's own independent review found a real detection gap in
the FIRST cut of this mechanism: a `provided` outcome was accepted
whenever the returned document's events overlapped with a real
control-host `audit_query` response. This could not distinguish a
genuinely co-hosted acceptance from a PORT-LEVEL identity mistake -- a
mutation reproducing exactly this bug (`audit_query_on_data_plane_host`
implemented as `return self.audit_query(actor, request)`, i.e.
accidentally forwarding to the control-host method) still returns a
GENUINE control-host document, which trivially overlaps with itself, and
would have passed silently.

The mechanism is replaced: `control_surface_cohosted_with_data_plane()`
(§19.1) declares the deployment's own TOPOLOGY (a fact about how this
harness is built, established once, not derived from any request); the
condition test (`conformance-tests/test_c09_audit_evidence.py::test_c09_
data_plane_host_audit_query_alias_rejects_control_credential_unless_
cohosted`) requires a `provided` outcome to be accompanied by a `True`
declaration, and is RED otherwise -- catching the proxy-mutation bug
class directly, independent of what the returned document happens to
contain. All four currently-registered plugs declare `False` (§19.4), so
`provided` is conformant for none of them today; `denied` must still be
exactly `AUTH_INVALID` regardless of the declaration (a cohosted
deployment may still keep separate credential stores).

### 19.4 Return convention and `SurfaceAbsent`

Mirrors `audit_query`'s own convention exactly (§18.1/§18.2): success (the
credential was genuinely accepted) returns the peer's raw `Mapping`
document; the peer's own genuine refusal raises `ConformanceDenial` with a
real contract code (most commonly `AUTH_INVALID`). `SurfaceAbsent` is
reserved for a peer that declares `control_plane` `unavailable`, or that
has no data-plane `/v1/audit/query` alias at all -- neither condition
holds for any of the four currently-registered plugs (`control_plane` is
always `enabled` in this harness's own construction, and the alias route
is always unconditionally mounted per contract 1.4.0 item (c)), so this
branch is unreached by any of them today, exactly like `audit_query`'s own
`SurfaceAbsent` branch was unreached throughout port v1.8 before any peer
flipped.

### 19.5 The four plugs, as of this WP

All four currently-registered plugs implement `audit_query_on_data_plane_
host` against a control/audit credential genuinely presented to the real
data-plane alias (HTTP plugs) or the real authenticate step plus a
deny/refusal (in-process plugs, §19.2), and every one of them currently
observes `AUTH_INVALID`. All four also implement `control_surface_
cohosted_with_data_plane` returning `False` (§19.3) -- their control and
data-plane surfaces are genuinely separate objects/processes with no
shared credential store, so the `provided`/co-hosted branch is
conformant for none of them today, the same "written against the real
eventual shape, currently unreached" honesty this document's other
new-method sections already carry (§18.4).

### 19.6 `conformance-tests/test_c09_audit_evidence.py`

One new UNCONDITIONAL test, `test_c09_data_plane_host_audit_query_alias_
rejects_control_credential_unless_cohosted` -- registered `xfail`-free
(unlike every other new-method test this document's §12-§18 sections
describe, which are all conditional on a capability/version): D-2's
obligation is unconditional (subordinate ruling 10 item 2), and both
currently-registered peers are already conformant to it without any
product change. A `provided` outcome is judged against `control_surface_
cohosted_with_data_plane()`'s own declaration (§19.3), never against
response content -- `provided` while declaring non-cohosted is red,
catching a port-level identity mistake (the proxy-mutation bug class
§19.3 names) directly. Also added: `test_c09_every_control_surface_
adapter_declares_1_5_0`, the 1.5.0 whole-registry vacuity guard for D-1
(registered `xfail(strict=True)`, mirroring §18's own 1.4.0 whole-
registry guard).

### 19.7 Compatibility impact (mirrors §12.7/§13.8/§14.3/§15.8/§16.7/§18.7)

- The two new abstract methods are additive to the ABC; a plug that does
  not implement either one fails to instantiate (Python's own `ABC`
  enforcement) -- all four registered plugs implement both as of this
  revision, so this is not a live compatibility break for any currently-
  registered adapter.
- `SurfaceAbsent`'s constructor signature and documented meaning are both
  unchanged by this revision; `audit_query_on_data_plane_host`'s own
  `SurfaceAbsent` raise conditions are the SAME two structural absences
  (§4.3's classic meaning, never the port v1.8 audit-surface extension of
  §18.3) -- D-2's obligation does not depend on whether `audit_query`
  itself is declared available. `control_surface_cohosted_with_data_
  plane` never raises `SurfaceAbsent` at all -- it is a plain boolean
  declaration, not a request-dispatching operation.
- `audit_query`/`flush_audit_buffer`/`audit_visibility_lag_ms`'s own
  documented semantics (port v1.8, §18.1-§18.3) are unchanged: they still
  reach only the control host, exactly as documented; `audit_query_on_
  data_plane_host` is the first to reach the data-plane host for an
  audit-shaped request.
- No peer's product code changed in this WP -- both peers' real data-plane
  alias handlers already rejected a control/audit credential with
  `AUTH_INVALID` before this revision; only the port and the four plugs
  gained a way to observe that existing behavior.

## 20. v1.10 port revision (coordinated with docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md phase 6 WP-1, and its own WP-3)

`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §6.1 (D-1/D-2/D-3)
requires three port changes so the common suite can observe contract
1.6.0's three "client self-sufficiency" obligations (subordinate ruling
11): (1) a credential's `secret` is the complete, verbatim bearer token
for the surface it is for; (2) `CapabilityDocument.surfaces` names where
the OTHER surface is reached; (3) `EntityDescriptor.field_types` names
every field's real type. This revision **is the first port revision that
removes a method, and it does so in two work packages, not one**: WP-1
(this revision's own commit) adds everything below WITHOUT removing
`control_surface_cohosted_with_data_plane` or the adapter-side
credential-composition sites §20.4 below records; WP-3 (the LAST peer's
1.6.0 flip) removes both, in the SAME commit as that flip, and is
recorded as part of THIS v1.10 revision, not a v1.11 -- one port
revision spanning two work packages, exactly as §6.1 item 2 of the
design states it must. Python's `ABC` machinery does not remove an
unneeded method on its own; WP-3 must delete `control_surface_cohosted_
with_data_plane`'s own abstract declaration AND all four plugs'
concrete overrides in that same commit, or a stale, no-longer-called
override survives silently on whichever plug its author forgets.

### 20.1 Two new abstract methods (D-3, catalog fixture) -- three counting §20.7's own addition

Added to `ConformanceAdapter` immediately after `catalog_document()`,
before `attempt_mutation`:

- `create_entity_with_declared_types(self, session, entity: str, fields:
  Sequence[str], field_types: Mapping[str, str] | None) -> None` --
  presents a real `create_entity` request carrying the CONTRACT's own
  `fields`/`field_types` (the seven-word vocabulary `string`/`integer`/
  `number`/`boolean`/`object`/`array`/`json`), verbatim, to the peer's
  real schema-operation entry point.
- `add_field_with_declared_type(self, session, entity: str, field: str,
  field_type: str) -> None` -- the same, for a single `add_field` call.

Design §6.1 item 3 left open whether the "common suite must know its own
declared types to compare against `catalog_document()`" need was met by
extending `Fixture` or by adding new method(s); this WP resolves it as
**new methods, not a `Fixture` change**: `test_c19_client_self_
sufficiency.py`'s own D-3 vector calls these two methods itself, with
type declarations it already holds locally, so no test ever needs
`Fixture` (built once per test, before any of that vector's own entities
exist) to carry declared-type state.

**Deliberately a SEPARATE vocabulary from `create_entity`'s own
`fields: Mapping[str, str]`** (`COMMON_FIELD_TYPES`, `"text"`/
`"integer"`, unchanged by this revision): the two new methods speak the
CONTRACT's seven-word vocabulary directly, with no port-level
translation table -- putting a translation table at the port level
would place peer-mapping knowledge on the wrong side of the port/plug
split (design principle 1), the same reasoning `adapter.py`'s own
`_PORT_FIELD_TYPE_TO_R2DB`/`_PORT_FIELD_TYPE_TO_WIRE` tables (each
plug's own, not the port's) already embody for the OLDER, two-word
vocabulary.

Neither method is reachable by any currently-registered adapter as of
this revision -- both are declare-first gated (`>= 1.6.0`) by every
caller in `test_c19_client_self_sufficiency.py`, and no peer declares
1.6.0 until WP-2 (r2db-api)/WP-3 (MitateDB-api). Each plug's own
implementation is written against the REAL eventual entry point (the
same "written for the real eventual shape, currently unreached" honesty
§18.4/§19.5 already document for other declare-first methods, not a
stub) -- see each plug's own docstring/comment (`conformance_adapter_
r2db.py`/`conformance_adapter_r2db_http.py`/`conformance_adapter_
mitatedb.py`/`conformance_adapter_mitatedb_http.py`) for what real call
it targets and why it may currently deny with `VALIDATION_FAILED`
(r2db's pre-1.6.0 `_SCHEMA_KEYS` does not yet recognize `field_types` at
all; MitateDB's pre-1.6.0 `_FIELD_TYPE_VOCABULARY` is a DIFFERENT
five-word set -- `text`/`integer`/`real`/`boolean`/`json` -- not the
contract's seven) rather than succeed.

### 20.2 Credential verbatim regulation (D-1) -- no new method, a port-level rule

Unlike every other port revision on this document, D-1's own port change
is **not a new abstract method** -- it is a REGULATION on the EXISTING
methods that already issue/rotate/bootstrap/reset a credential
(`issue_credential_inband`/`rotate_credential`/`bootstrap`/`reset`), and
on the value types those methods return (`CredentialHandle`/
`ControlCredentialHandle`). `adapter.py`'s own docstrings on all six now
state it directly: `.secret` is the credential's COMPLETE bearer token,
used verbatim; `.credential_ref` is the peer's own `credential_id`, held
verbatim; an adapter composes neither from the other, and derives
neither by splitting the other. This is additive to what a well-behaved
adapter already had to do (three of the four currently-registered
plugs already satisfied it structurally, §20.4 below) -- the change is
that it is now a documented, port-level obligation, independently
re-verified by §20.4's own static test, rather than an unstated
convention living only in each plug's own comments.

### 20.3 `surfaces_cohosted` (D-2) -- a free function, not an abstract method

`adapter.surfaces_cohosted(document, *, fallback)` judges co-hosting from
a 1.6.0+ peer's own declared `surfaces.data`/`surfaces.control` origins
(`scheme, host, port` -- never the path, design §3 D-2's own definition),
falling back to the PRE-1.6.0 mechanism (`ConformanceAdapter.control_
surface_cohosted_with_data_plane`, port v1.9 §19.1/§19.3) when `document`
does not affirmatively demonstrate a 1.6.0+ `surfaces` object. It is a
plain function, not an ABC method, because the judgment itself needs no
peer-specific knowledge once it has a real `CapabilityDocument` in hand
-- unlike `control_surface_cohosted_with_data_plane` (a topology fact
only the PLUG can state, since it alone knows whether its own two ASGI
apps/service objects are the same process), `surfaces_cohosted` is pure
computation over a document every plug already knows how to produce.

**`control_surface_cohosted_with_data_plane` is NOT removed by this
WP** -- design §6.1 item 2 requires its removal to land in the SAME
commit as the LAST 1.6.0 flip (WP-3), for the identical reason §19.3
already gives for why the method exists at all: `test_c09_audit_
evidence.py:868`'s own `test_c09_data_plane_host_audit_query_alias_
rejects_control_credential_unless_cohosted` calls it UNCONDITIONALLY
(no version branch at all, by design -- §19.6's own "registered `xfail`-
free... this is an UNCONDITIONAL obligation"). Removing the method in
WP-1, before any peer's `surfaces` exists for `surfaces_cohosted` to
prefer, would make that unconditional vector's own dispatch source
disappear for two work packages with nothing to replace it. WP-1
therefore rewires that one call site to `adapter.surfaces_cohosted(
adapter.capability_document(), fallback=adapter.control_surface_
cohosted_with_data_plane)` -- a REPLACEMENT of the judgment SOURCE, not
of the OBSERVED BEHAVIOR: every currently-registered plug still declares
`False` under the fallback (no plug has `surfaces` yet), so the vector's
own observed outcome for that call site is unchanged (work order WP-1
completion condition 11's own "置換が挙動を変えないことの実測" -- see
the WP-1 completion report's own mutation 8 result for the measured
proof: removing the fallback branch entirely, so a `surfaces`-less
peer's judgment source silently returns `True` instead of falling
through to the topology declaration, turns that same vector red on all
four plugs).

### 20.4 The four plugs, as of this WP

All four currently-registered plugs implement both new abstract methods
(§20.1), written against their own real eventual schema-operation entry
point (unreachable today, §20.1's own closing paragraph).

**Credential composition, as found (D-1(e), the static test's own
subject, §20.5)**: `conformance_adapter_r2db.py`, `conformance_adapter_
r2db_http.py`, and `conformance_adapter_mitatedb.py` (the in-process
MitateDB plug) already compose and decompose nothing -- each already
carries `credential_id` and `secret` as two separate values end to end,
never joined into one string by the ADAPTER itself (MitateDB's own
in-band composition, where it exists, happens inside the PEER's product
code, `http.py`, on the wire -- never inside this adapter). Only
`conformance_adapter_mitatedb_http.py` composes, at **five** sites
(`issue_credential`/`issue_credential_inband`/`_control_send`/`audit_
query_on_data_plane_host`/`isolated_control_surface`, each an
`f"{credential_id}.{secret}"`-shaped expression) -- because THIS plug's
own real wire protocol (`http.py`'s `Authorization` header, pre-1.6.0)
already requires the composite form on the wire, and no bare-secret
entry point exists for it to use instead. **Correction (review finding
F3 / audit finding (iv), 2026-09-04, common-suite discipline 3)**: this
row originally said "four sites" and did not name `isolated_control_
surface` -- accurate at the ORIGINAL port v1.10 delivery, but addendum A
(§20.7) added a 5th composition site inside that new method, and this
row (plus §20.5's own reason string and `test_c19_client_self_
sufficiency.py`'s own `xfail` reason) were not updated when addendum A
landed. §20.5's static test finds exactly these FIVE sites and no
others (WP-1 completion report has the calibration run, re-run against
the broadened scanner §20.5 also now describes). Removing all five is
WP-3's job, same commit as this plug's own 1.6.0 flip (design §3
D-1(d)'s own "混在期間を作らない" instruction: all of this plug's
issue/rotate/bootstrap/reset/addendum-A points move to peer-side
composition in one commit, never some points before others).

**実施記録 (WP-3 追補, supervisor ruling 2026-09-04)**: the five composition sites named above are removed from `conformance_adapter_mitatedb_http.py`, in the same commit as MitateDB's own last 1.6.0 flip -- every real issuance point on that peer (`credential_store_postgres.PostgresCredentialStore.issue`, `auth.CredentialStore.issue`/`.rotate`, `control_auth.ControlCredentialStore.issue`/`.rotate`, `control_credential_store_postgres.PostgresControlCredentialStore.issue`/`.rotate`, `control_plane.ControlPlaneService.issue_credential`/`.rotate_credential`'s own response dicts) now returns an already-composed, ready-to-present bearer, so the adapter has nothing left to compose. The static test `test_c19_adapters_never_compose_or_decompose_the_bearer_secret` (§20.5) confirms zero findings across all four registered adapters. The port-level topology-declaration method (§20.7 below) is removed in the same commit, and its own fallback branch inside `surfaces_cohosted` (§20.3) is removed alongside it -- `surfaces_cohosted` is surfaces-derived only from this commit forward.

### 20.5 Two new `xfail(strict=True)` registrations, `test_c19_client_self_sufficiency.py`

Mirrors §18.6/§19.6's own whole-registry-guard discipline, plus one NEW
kind of fixed test this document has not carried before:

- `test_c19_every_control_surface_adapter_declares_1_6_0` -- the
  whole-registry guard, SAME shape as `test_c09_every_control_surface_
  adapter_declares_1_5_0` (§19.6, phase 5's identically-purposed guard
  for the PRIOR contract bump): a non-parametrized function that walks
  `registered_adapters()` itself (never a hardcoded adapter-name list),
  requiring every control-surface-bearing adapter to declare
  `contract_version >= 1.6.0`. False today (collected as 1 item);
  registered `xfail(strict=True)`, reason "no peer declares 1.6.0 yet;
  un-xfailed by the last flip WP" -- removed in the SAME commit as the
  LAST 1.6.0 flip (WP-3), the guard's own body unchanged.
- `test_c19_adapters_never_compose_or_decompose_the_bearer_secret` --
  the FIRST static, SOURCE-LEVEL fixed test on this port (every prior
  fixed test in this document observes RUNTIME behavior through the
  ABC; this one parses every REGISTERED adapter's own module file's AST
  -- `_scanned_adapter_files()`, derived from `registered_adapters()`
  itself, never a hardcoded file list, review finding F7/audit finding
  (vi) -- and never calls any of them). Fixes two properties at once
  (D-1(e), design §6.2's own warning that dropping ONLY the first
  leaves a real gap): (a) no expression concatenates an id-shaped value
  with a secret-shaped value joined by a literal `"."` (an f-string, a
  `+` chain, or a `".".join([...])` call); (b) no `.split(".")`/
  `.rsplit(".")`/`.partition(".")`/`.rpartition(".")` call (nor the
  hand-rolled find/index-based slice equivalent) -- (b) exists because
  dropping composition alone while still deriving `credential_id` by
  SPLITTING the bearer would pass (a) while remaining exactly the
  behavior the verbatim regulation (§20.2) forbids. Genuinely RED today
  (§20.4's FIVE real findings on `conformance_adapter_mitatedb_http.py`
  -- corrected from "four", review finding F3/audit finding (iv),
  2026-09-04, §20.4's own correction note), so registered
  `xfail(strict=True)` with a reason naming that plug and its five
  sites by the operations that create them -- removed in the SAME WP-3
  commit that removes those five sites (§20.4), which is also the same
  commit that removes `control_surface_cohosted_with_data_plane`
  (§20.3) -- design §6's own "撤去 3 点を分割しない" instruction (work
  order WP-1 §7 item 11): the guard `xfail`, the static-test `xfail`,
  and the adapter composition sites all move together, or none of them
  do, because dropping any ONE alone either goes vacuously green
  (masking a still-missing implementation) or breaks a still-load-
  bearing fallback.

The scanning rule was prototyped and measured against every registered
plug's own module file BEFORE being placed in the suite (common-suite
discipline: an undesigned mechanism is measured, not assumed) --
`scratchpad/wp1y/static_proto.py`, one calibration finding (a false
positive on a literal error-message string that happened to mention
both "credential_id" and "secret" in prose, fixed by scoping the
id-/secret-shape check to INTERPOLATED expressions only, never literal
text runs) and zero findings needing an exclusion list. **Broadened
(review finding F7 / audit finding (vi), 2026-09-04)**: decomposition
detection (property (b)) originally flagged a split/partition call only
when its own RECEIVER expression's text mentioned "secret"/"bearer" --
measured (review's own mutation) to miss `token = handle.secret;
token.split(".")` entirely, since an intermediate variable's name
carries neither word. The rule now flags ANY `.split(".")`/
`.rsplit(".")`/`.partition(".")`/`.rpartition(".")` call (plus the
hand-rolled find/index-based slice equivalent) whose own argument is
the literal delimiter `"."`, regardless of receiver -- re-calibrated
against every registered plug's own module file with zero new findings
(no allowlist entry was needed) and confirmed to catch the review's own
`token.split(".")` example. **Residual, disclosed limit
(CONDITIONS.md's C-19 row limit (e))**: this remains a SYNTACTIC scan
-- it cannot see decomposition performed by a function this file
merely CALLS (e.g. handing the bearer to an external helper that
itself splits it), only expressions written directly in the scanned
file's own AST. WP-1's own completion report has the full transcript
for both the original calibration and the F7 re-calibration.

### 20.6 Compatibility impact (mirrors §12.7/§13.8/§14.3/§15.8/§16.7/§18.7/§19.7)

- The two new abstract methods (§20.1) are additive to the ABC; a plug
  that does not implement both fails to instantiate (`ABC` enforcement)
  -- all four registered plugs implement both as of this revision, so
  this is not a live compatibility break for any currently-registered
  adapter.
- `control_surface_cohosted_with_data_plane` (§20.3) is UNCHANGED and
  still required on every plug as of this WP -- its eventual removal is
  WP-3's, not this commit's.
- `CredentialHandle`/`ControlCredentialHandle`'s own field SHAPES
  (`credential_ref`/`application_id`/`role`/`secret`, `credential_ref`/
  `secret`) are unchanged by §20.2 -- only their documented MEANING
  gained a stated regulation; no plug's construction of either type
  needed to change to comply (three of the four already complied
  structurally, §20.4).
- No peer's product code changed in this WP (work order §7 item 3 /
  work order completion condition 18) -- only the port, the two-method
  addition on all four plugs, and (temporarily, until WP-3) nothing else
  on the adapter-composition side.

### 20.7 Addendum A extension: `isolated_control_surface` (supervisor ruling 2026-09-04)

A THIRD new abstract method, approved and specified by the supervisor
after reviewing the WP-1 addendum A standalone prototype (§20's own
initial delivery covered only §20.1's two D-3 methods): `isolated_
control_surface(self) -> AbstractContextManager[Callable[[CredentialHandle
| ControlCredentialHandle], Mapping[str, Any]]]`, placed on the ABC
immediately after `control_audit_events()`. A context manager that
yields a callable presenting a `control_capabilities`-equivalent request
to a FRESH, throwaway control surface -- sharing the adapter's own real
registered application/credential state (the SAME backend/store objects
`control_credential()`'s own actor already authenticates against) but
starting from its own EMPTY `control_requests_per_minute` rate window --
and releases whatever real resources building it opened on exit (an
HTTP+PostgreSQL plug's own fresh connection pools in particular).

**Not a contract capability.** Used by exactly one caller: `test_c14_
authority_boundary.py::test_c14_resource_bounds_published_and_enforced`'s
own `control_requests_per_minute` sub-drive, which this addendum
rewrites to burst against the isolated surface instead of the adapter's
shared one -- eliminating both the prior `time.sleep(61)` recovery-wait
(nothing shared is touched, so there is nothing to wait to recover) and
its own "un-poison the shared window for later tests" side effect
(unnecessary by construction: the isolated surface's rate window was
never shared in the first place). The rewrite also ADDS a property this
class's own sub-drive never checked before this addendum: exact-position
attribution (`successes == rate_limit` before the first refusal) --
previously only the `applications`/`credentials_per_application`
sub-drives asserted this; the isolated surface's genuinely empty window
makes it free to check for `control_requests_per_minute` too.

**Per-plug realization**: the two in-process plugs (`conformance_
adapter_r2db.py`/`conformance_adapter_mitatedb.py`) construct a second
`ControlPlaneService` sharing the SAME backend/audit/limits objects the
adapter's own shared `ControlPlaneService` was built from -- no real
resource to release on exit. The two HTTP plugs reuse their own real
product-code control-plane assembly a second time (`conformance_
adapter_r2db_http.py`'s own `_build_control_stack()`, the SAME function
`__init__`/`_privileged_control_send`'s periodic-rebuild path already
call; `conformance_adapter_mitatedb_http.py`'s own `build_control_
service(self._control_env)`, the SAME function `__init__` already calls,
against a newly-saved `self._control_env` so it can be called a second
time) against the SAME real Postgres DSN/schema, and release the real
resources that second call opened on exit -- `r2db-api-http` closes the
fresh httpx client AND each of the 4 fresh stores `_build_control_
stack()` returns (mirrors `_privileged_control_send`'s own rebuild-path
cleanup, `store is not None` guard included); `MitateDB-api-http`
closes only the fresh httpx client (`build_control_service`'s own
registries/backend open one connection per call, no pool to release,
per that function's own docstring).

**Measured (WP-1 completion report has the full transcript)**: `test_
c14_resource_bounds_published_and_enforced`'s own `call` duration
across all 4 plugs combined -- previously ~4 * (61 + few seconds) ≈ 248s
-- is now under 4 seconds total (r2db-api/MitateDB-api in-process:
0.01s each; r2db-api-http: 0.74s; MitateDB-api-http: 3.13s), a
>60x reduction, comfortably under the addendum's own 60-second target.
Configured `applications`/`credentials_per_application`/`control_
requests_per_minute` values on all four plugs are UNCHANGED by this
addendum (still `115`/`5`/`200` r2db-api, `100`/`5`/`200` MitateDB-api)
-- the isolated surface shares `self._control_limits` verbatim, so no
adapter construction-time value needed to move.

Compatibility impact: additive to the ABC (§20.6's own first bullet
applies identically -- a plug not implementing it fails to instantiate;
all four now do). No peer's product code changed. `MitateDB-api-http`'s
own real wire protocol still requires the pre-1.6.0 composite bearer
form for a control credential, so this new method's own call helper
composes it too (this file's 5th such site -- §20.4, as corrected by
review finding F3 / audit finding (iv), 2026-09-04, now records all
5 from the start, this one included) -- removed together with the
other 4 in WP-3.

## 21. v1.11 port revision (coordinated with docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md phase 7 WP-4)

`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` D-6
requires the common suite to executable-ify C-05 (SI-08's "finite,
discoverable resource bounds" evidence) for the first time. Two additions,
no removals.

### 21.1 `isolated_application_surface()` (D-6.1 V2, D-6.5 addendum)

Added to `ConformanceAdapter` immediately after `isolated_control_surface()`:

```python
def isolated_application_surface(self) -> AbstractContextManager["ConformanceAdapter"]
```

A context manager that, on entry, builds a FRESH, throwaway data-plane
instance bound to its OWN small conformance profile (small enough that
C-05's V2 vectors can drive every applicable resource class past its
declared bound within one test), and yields a SECOND object that itself
conforms to this exact `ConformanceAdapter` ABC -- self-similar, not a
bespoke stand-in. A test drives the yielded instance with the SAME
ordinary port operations it already uses against the shared, session-
scoped adapter (`authenticate`/`create_entity`/`insert`/`attempt_batch_
with_addresses`/`attempt_cross_entity_batch`/`select_eq`/`attempt_filter`/
`capability_document`/...) -- no drive-recipe-specific method was added to
this port for this purpose.

**Shape differs deliberately from `isolated_control_surface()`** (design
review 1, B-5): that method yields a single callable because its own
driven class (`control_requests_per_minute`) is the only one it ever
presents; the application plane's own D-6.2 drive recipes need row
insertion, entity/schema-object creation, batch mutation, cross-entity
batch mutation, query, and a read of the isolated instance's own
`capability_document()` -- more surface than any single callable could
honestly present without becoming a second, adapter-invented
implementation of "drive a resource class."

**Resource-sharing shape differs by plug** (D-6.5 addendum's own "(推測)"
point, resolved by WP-4 measurement; corrected here WP-4 rework 2026-09-
06, 差し戻し 2 巡目, F-port-docstring: an earlier draft of this paragraph
claimed uniform "shares nothing with the shared, session-scoped adapter's
own application/credential registry", which was true only for the two
in-process plugs). **In-process** (`r2db-api`, `MitateDB-api`): the
isolated instance is built from a wholly fresh service/foundation object
with no reference back to the shared adapter at all -- every credential,
application, and cell registry it touches is genuinely private, from
construction through exit. **HTTP** (`r2db-api-http`, `MitateDB-api-
http`): the isolated instance is a shallow copy (`copy.copy(self)`) of
the shared adapter -- only the data-plane pieces are freshly constructed
and bound to the small profile, while the control-plane client/app, the
credential stores, and the shared, already-bootstrapped PostgreSQL
platform database are the SAME objects the shared surface already holds
(see the per-plug realization below for why this borrowing is necessary,
not an oversight). In both shapes, the whole point of the small profile
is a low-cardinality surface a V2 drive can genuinely exhaust; the HTTP
plugs' additional control-plane/platform sharing costs nothing to that
positional exactness because V2's own drives never touch the
`applications`/`credentials_per_application` bounds the shared state
carries. Test code obtains its own application/credential state against
the yielded instance the ordinary way (`provision_application`/
`issue_credential`).

**Per-plug realization** (D-6.5 addendum, "Q4 確定後の追補"): none of the
four plugs' own construction goes through a composition root (`main.py`'s
`build_app`/`MitateDB-api`'s `build_control_service`) -- addendum (1)'s
own per-plug table found that path either unavailable (no `limits=`
injection point) or unnecessarily heavy (deprecated-env rejection,
platform-declaration reads, writer-role checks the isolated surface has
no need of). Instead:

- `r2db-api` (in-process): a genuinely fresh `R2DBConformanceAdapter(
  limits=_ISOLATED_APPLICATION_LIMITS)` -- the class's own ordinary
  constructor, now accepting an optional `limits` keyword. True self-
  similarity, no shared state at all. No real resource to release on exit
  (in-memory construction only, D-6.6's own supervisor note) -- the (e)
  resource check for this plug observes Python object liveness via a
  weakref instead.
- `r2db-api-http`: `copy.copy(self)` (a shallow copy, so the control-
  plane client/app/pepper/credential-ref/stores and the already-
  bootstrapped PG platform are shared by construction) with the DATA-
  plane pieces (`_app_pg`, `_provisioned_cells`, `_counter`, `_service`,
  `_app`, `_loop`, `_client`) deliberately overwritten with fresh ones
  bound to the small profile. `copy.copy`, not `object.__new__` +
  selective assignment, because `issue_credential` on this plug is
  itself an IN-BAND `/control/v1/credentials` HTTP call that needs the
  real control-plane client/credential-ref state `self` already holds --
  D-6.5 addendum's own finding that no extra control seed is needed to
  build the isolated APPLICATION surface. On exit: closes its own httpx
  client and `PostgresCell` pools (`pool_size=2` each) FIRST, then
  deprovisions every application it provisioned (order matters: a
  provisioned application's PostgreSQL database cannot be dropped while
  its own pool still holds live connections to it) -- WP-4's own first-
  execution finding: `provision_application` writes into the SAME shared
  platform database's `applications` registry table C-14 vector 5's own
  `n_existing < apps_limit` precondition reads, so leaving those
  uncleaned silently saturates that shared bound for every later test in
  the session.
- `MitateDB-api` (in-process): a fresh `MitateDBConformanceAdapter(
  config=small_foundation_config)` -- mirrors the r2db in-process
  realization; `FoundationConfig` is a pure, local dataclass, so no Q4
  platform-declaration/role-setting machinery is ever reached (addendum
  (4): "Q4 の宣言表・role設定はこの経路に一切現れない"). This adapter's
  own `close()` is a documented no-op for the SHARED surface (correct
  there -- the whole process exits anyway); the isolated surface instead
  closes every real per-cell `SQLiteBackend` connection it provisioned
  directly, so the (e) resource check has something real to observe.
- `MitateDB-api-http`: same `copy.copy(self)` shape as `r2db-api-http`,
  for the identical reason (`issue_credential` is a direct write against
  a shared `PostgresCredentialStore`, costing nothing to share, kept
  consistent with the sibling peer's own construction). `provision_
  application`'s own per-cell `FoundationConfig` was moved from an inline
  literal to a named `self._application_config` instance attribute
  (constructor-set) specifically so the isolated copy can override just
  that one attribute with the small profile, with no other change to
  `provision_application` itself. Same deprovision-after-close-then-
  deprovision ordering and same shared-registry cleanup fix as `r2db-api-
  http` above.

**Per-class isolation choice (work order completion condition 13(b))**:
C-05's own V2 drivers each open a FRESH `isolated_application_surface()`
PER driven resource class -- no two classes' drives ever share one
isolated instance. This is the "class ごとに新しい isolated_application_
surface() を張る" branch condition 13(b) offers, not the alternative (one
shared isolated instance reused across every driven class, which would
need a checked headroom precondition on EVERY later class's drive to
account for what earlier classes' drives already consumed of a shared
rate window). The one exception that DOES need, and asserts, a headroom
precondition is `requests_per_minute`'s own driver, entirely WITHIN its
own single isolated instance: setup traffic against that SAME instance
(`create_entity` under the developer credential, an HTTP plug's own real
`authenticate()` round trip under the SAME runtime credential the drive
then measures) can consume part of the very rate window being driven --
measured (WP-4) at exactly 1 unit on an HTTP plug (a real `GET /v1/
capabilities`), 0 on an in-process plug (a bare local lookup that never
touches the rate-window primitive at all), so the driver's own expected
success count is `bound - already_consumed` rather than a bare `bound`.
This choice, and the reasoning above, is stated identically in the port's
own `isolated_application_surface()` docstring (`conformance-tests/
adapter.py`).

**(e) resource check** (D-6.6): each plug's own real, measured resource
(D-6.5 addendum (3)) -- PG plug: `pg_stat_activity` count matching a
caller-supplied `datname_like` pattern (a new non-normative `_live_pg_
backend_count(datname_like)` accessor on each HTTP plug, mirroring the
existing "optional raw-accessor methods" convention; **WP-4 rework 2026-
09-06, 完了条件 15/F1**: the caller scopes the pattern to ONLY the one
per-application database the isolated instance itself provisioned
(`<prefix>_app_<application_id>`), never a bare `<prefix>%` pattern --
that also matched the shared PLATFORM database (`<prefix>_platform`)
where the shared control stack's own lazily-opened connections live,
making the check's `before`/`after` depend on whether an earlier test in
the same worker process had already warmed that shared pool); in-memory
plug: live per-cell connection liveness (`SQLiteBackend`'s own sqlite
connection) or Python object liveness (r2db in-process, which owns no
real resource at all).

**Load-bearing scope of (e), disclosed** (差し戻し指示 1, 監督裁定 2 回
目, `conformance-tests/CONDITIONS.md`'s own C-05 row carries the same
disclosure): a removed `close()`/pool-release step turns this check red
on 2 of the 4 plugs only -- `r2db-api-http` (mutation-verified: the
context-manager protocol is driven by hand, `__enter__`/`__exit__`,
specifically so the resource-leak assertion is reached and asserted EVEN
WHEN `__exit__` itself subsequently raises, decoupling the leak
measurement from `deprovision_application()`'s own downstream failure to
DROP a still-in-use database) and `MitateDB-api` in-process (mutation-
verified: a live per-cell sqlite connection). It is NOT load-bearing on
the other 2, for two different structural reasons: `r2db-api` in-process
owns no external resource at all to leak (D-6.6's own supervisor note,
"資源ゼロ") -- no close-removal mutation can even be constructed there,
so its own half of (e) observes Python object liveness (a `weakref`)
instead; `MitateDB-api-http`'s own `deprovision_application()`
(`0004_deprovision_application.sql`) issues `pg_terminate_backend`
directly against the application's PostgreSQL database as part of the
DROP, so its connection-count guarantee holds structurally REGARDLESS of
whether the pool's own `close()` ran first -- accepted as a genuine
acceptance boundary rather than a test defect to force red (監督裁定 2
回目: MitateDB's own deprovision path independently guarantees the
outcome close would have guaranteed).

### 21.2 `idempotency_key` optional field (D-6.7 C-07 (ii))

Added as an optional field (default `None`) to `BatchOperation` and
`ScopedBatchOperation`: carries the contract's own `Mutation.idempotency_
key`/`MutationRequest.idempotency_key` through to whatever real entry
point already receives the rest of the operation -- never interpreted by
the adapter itself, exactly like `expected_revision`/`unique_key`.
**Addition is this one field only; no positive-side primitive (key
generation/storage/replay/result comparison) was added** (裁定 S-4) --
nothing on either currently-registered peer would exercise it yet.

**Contract placement note**: the contract's own `idempotency_key` is a
REQUEST-level field (`MutationRequest`/`ScopedMutationRequest`), not a
per-operation (`Mutation`/`ScopedMutation`) one -- those two definitions
are `additionalProperties: false` closed shapes with no slot for it. Each
plug's own wiring reflects this: the two in-process plugs place it inside
the per-operation dict (their own internal dispatch convention, pre-
existing, already rejects it there with a real `CAPABILITY_UNSUPPORTED`);
the two HTTP plugs hoist it to the request body's own top-level key
before sending, matching the real wire shape.

### 21.3 Compatibility impact

Additive to the ABC (§20.6's own first bullet applies identically -- a
plug not implementing `isolated_application_surface()` fails to
instantiate; all four now do). No peer's PRODUCT code changed for either
§21.1 or §21.2 -- §21.1's own `MitateDB-api-http` realization required
its conformance PLUG's `provision_application` to read a named `self.
_application_config` attribute instead of an inline literal
(conformance plug code only, not `mitatedb_api`'s own package); §21.2
required each plug's own mutation-item construction to carry through one
additional optional field. Peer-local declaration additions (`MitateDB-
api/src/mitatedb_api/cell.py`'s `limit_enforcement` block, four missing
classes) are a separate, peer-local change tracked in the phase 7 WP-4
completion report, not a port revision.

### 21.4 `isolated_control_surface()` `limits_override` addendum (WP-5 rework round 2, supervisor ruling 2026-09-06 item 1)

Diagnosed problem (WP-5 rework, round 2): the WP-5 rework round 1 fix
(a conftest-level `_ApplicationResidueTracker` deprovisioning every
Application a tracked adapter's own `provision_application`/`register_
application_inband` leaves behind at each test's own teardown) correctly
stopped the SHARED, session-scoped adapter's own `applications` registry
from growing unboundedly across the whole suite -- but that same fix had
a second-order effect: `test_c14_authority_boundary.py::test_c14_
resource_bounds_published_and_enforced`'s own `applications` drive
(§4 vector 5) reads the registry's own pre-existing count (`n_existing`)
before driving to the declared bound, and with the registry no longer
padded by leftover Applications from earlier tests, `n_existing` dropped
close to zero -- so this drive, for the first time, actually registered
close to the FULL declared `applications` bound (115 on both r2db-api
plugs) in a single test. That is 100+ real `/control/v1` calls against
the SHARED adapter's own `control_requests_per_minute` window (200 on
both r2db-api plugs) within the same test, leaving too little headroom
for whatever OTHER test happens to share that window within the same
60-second period -- measured directly: 24 unrelated tests failing with
`LIMIT_EXCEEDED`, reproduced 3 times.

**Fix**: extend `isolated_control_surface()` (§20.7) -- already the
`control_requests_per_minute` vector's own primitive for driving a
resource class to its exact declared bound without touching the shared
window -- with an optional, keyword-only `limits_override: Mapping[str,
int] | None = None` parameter (default `None`, so every pre-addendum call
site, in particular the `control_requests_per_minute` vector's own, is
unaffected). When given, the ISOLATED surface's own control-plane limits
profile is built with the named fields replaced by the override's own
values (`adapter.py`'s new `apply_limits_override` helper, a type-agnostic
`dataclasses.replace` -- both peers' own `ControlPlaneLimits` dataclasses
share the same 3 control-plane field names) before the isolated surface
is constructed; every field NOT named in the override keeps the shared
surface's own value. `test_c14_authority_boundary.py`'s own `applications`
vector now drives an isolated surface overridden to a small value derived,
not hardcoded (WP-5 rework, supervisor ruling 2026-09-06 item 2 --
corrected from an earlier, now-removed `_ISOLATED_APPLICATIONS_OVERRIDE =
8` constant that a review finding showed could be padded out from under
by leftover Applications from earlier tests): `n_existing_shared +
_APPLICATIONS_OVERRIDE_MARGIN`, where `n_existing_shared` is a fresh
`len(adapter.list_applications(control_actor))` read via the SHARED
surface and `_APPLICATIONS_OVERRIDE_MARGIN = 3` is the small, fixed
headroom above whatever the registry already holds -- rather than the
real, large declared bound. This is the same precedent `isolated_
application_surface()`'s own small conformance profile already
established for the application plane (D-6.1 V2): the ENFORCEMENT
MECHANISM is what the vector proves, not the literal production-
configured value (the "classes" loop in the same test separately
confirms the real, large value is a positive, discoverable, `enforced`-
labeled, conformance-buildable int).

The isolated surface's own `applications` bound still counts against the
SAME underlying application registry the shared surface reads (§20.7's
own "sharing this adapter's own real registered application/credential
state" -- unchanged by this addendum), so a vector driving it still needs
the same headroom arithmetic C-14's own `control_requests_per_minute`
vector never needed (that class's own isolated rate window always starts
genuinely empty) but the ORIGINAL, pre-addendum `applications` vector
always did: read the current count through the isolated surface's own
`list_applications` first, then expected successes = override − that
count.

**Shape**: since the `applications` drive needs `register_application`/
`list_applications` in addition to the pre-existing `capabilities`
(`control_capabilities`-equivalent) call, the context manager's own yield
type changes from a bare callable to a new, non-normative dataclass,
`IsolatedControlHandle` (`capabilities`, `register_application`, `list_
applications`, all `Callable`s against the SAME isolated instance) --
`IsolatedControlHandle.__call__` delegates to `.capabilities`, so
`isolated_call(actor)` (the `control_requests_per_minute` vector's own
pre-existing call shape) is unchanged syntactically and behaviorally.

**Residue**: `isolated_control_surface()` now tracks, internally, every
application `register_application` on its own yielded handle registers
successfully, and deprovisions every one of them on the context
manager's own `with`-block exit -- after releasing whatever connection
pools it opened (WP-5 rework, review finding 8: corrected from an earlier
"before releasing..." wording that had the order backwards; both HTTP
plugs' own `finally` blocks close the client/connection pools FIRST, then
deprovision -- `close -> deprovision`, matching `test_c05_limit_
declaration_agreement.py`'s own module docstring, which documents this
identical order for `isolated_application_surface()`. No code changes to
match: the two currently-registered HTTP plugs already implemented
`close -> deprovision`; only this design text's own description of that
order was wrong). A caller must not also deprovision an application it
registered through this handle itself (a double deprovision attempt
against an application the primitive already removed); the `applications`
vector's own pre-addendum `finally: adapter.deprovision_application(...)`
loop is removed accordingly.

**Compatibility impact**: additive/optional -- `limits_override` is
keyword-only with a `None` default, and `None` produces the exact
pre-addendum construction on every plug (`apply_limits_override(limits,
None) is limits`). The yielded type change (bare callable ->
`IsolatedControlHandle`) is a plug/common-suite-internal detail:
`isolated_control_surface()` is never part of the normative contract
surface (§20.7's own "not a contract capability"), and its only two
callers (`test_c14_authority_boundary.py`'s `control_requests_per_minute`
and `applications` vectors) are both updated in the same change. All 4
registered plugs implement the new signature and yield shape (r2db-api
in-process/HTTP, MitateDB-api in-process/HTTP) -- a plug that has not
been updated fails to instantiate, the same §20.6 compatibility rule
every other addition to this ABC already follows.

## 22. v1.12 port revision (Phase 8 WP-1b, coordinated with docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md D-2)

Phase 8's own D-2 requires the common suite to executable-ify `concurrency`
(SI-08's own resource-bound evidence, the one application-plane class port
v1.11 had no primitive to drive at all) and to close L7-21 (`result_items`/
`query_complexity`'s peer-name-keyed drive exclusions, replaced by a
port-level capability). Two additions, no removals.

### 22.1 `hold_in_flight(session, n)` (D-2 決定 1/2, 実装の形 (a)/(b))

Added to `ConformanceAdapter` immediately after `isolated_application_
surface()`:

```python
def hold_in_flight(self, session, n: int) -> AbstractContextManager[None]
```

Meaning (verbatim, design §3 D-2 決定 1 -- carried into the port docstring
unparaphrased, per this repository's own 常設規律 4): "n 個の application
plane 要求を、service の in-flight 窓の内側で停止させたまま保持する。保持
中に n+1 個目を出すと `LIMIT_EXCEEDED`(`concurrency`) で拒否される。解放
後、保持していた n 個はすべて正常に完了する。"

**Realization is adapter-internal, never a product-code hook** (design §4):
each plug wraps a real object it already constructs out-of-band for
`isolated_application_surface()` (a cell/backend object), replacing one of
its own bound methods (or, on `MitateDB-api`, its own `_limit_gate`) with a
small proxy that blocks the first `n` real calls on a shared `threading.
Event` until released. `n` real background OS threads each issue one
genuine, full port-level request that reaches this stall point; the
primitive waits for all `n` to have genuinely entered the stall (a
`threading.Semaphore`, never a fixed sleep) before yielding, and on exit
releases them, joins every thread, and re-raises the first background
failure (if any) only after every thread has been joined.

**Per-plug stall-point realization** (design D-2 実装の形 (b), measured):

| plug | wraps | why the stop point sits inside the counter, before backend/DB | concurrency mechanism |
|---|---|---|---|
| `r2db-api` (in-process) | the isolated instance's own per-application cell object's `catalog()` method (whole-method wrap: stall before delegating to the original) | `DataService._slot` (external to the cell) increments `self._active` and dispatches to the cell object ONLY after that increment -- by the time the cell's own method runs, the counter is already +1 | `n` real `threading.Thread`s, each a plain synchronous `DataService.catalog(session)` call |
| `r2db-api-http` | the SAME per-application cell object (a `PostgresCell`), same wrap shape as the in-process plug (the underlying `DataService`/`_slot` is identical regardless of transport) | identical to the in-process plug's own reasoning | `n` real `GET /v1/catalog` HTTP round trips, each issued from its own OS thread against its own fresh event loop + `httpx.AsyncClient(ASGITransport(app=...))` -- the shared adapter's single `self._loop.run_until_complete` cannot itself hold more than one request in flight |
| `MitateDB-api` (in-process) | the cell's own `_limit_gate` bound method (NOT any one operation method wholesale) -- a wrapper that calls the REAL `_limit_gate` generator context manager's own `__enter__()` first (rate acquire + in-flight counter increment + request_bytes/operation_depth checks, all real), THEN stalls, THEN returns the real `deadline` value back to the caller | this peer's own gate is entered FROM INSIDE an operation method's own body (`ApplicationCell.catalog`/`.insert`/...), unlike r2db's external `_slot` -- wrapping a whole operation method wholesale would stall BEFORE the counter increment ever ran; wrapping `_backend` instead would hang permanently at `n >= 2` (the first held thread would hold `ApplicationCell._lock` stalled inside `_backend`, and the second held thread would then block forever on `_lock.acquire()`, never reaching this primitive's own stall point at all -- the SAME structural reason D-1 already forbids wrapping `_backend` for this peer) | `n` real `threading.Thread`s, each a plain synchronous `session.catalog()` call (parameterless, needs no pre-existing entity) |
| `MitateDB-api-http` | the SAME per-application `ApplicationCell`'s own `_limit_gate`, identical wrap shape to the in-process plug (the real HTTP dispatch reaches the SAME `ApplicationCell` class through `http.py::get_catalog` -> `session.catalog()`) | identical to the in-process plug's own reasoning | `n` real `GET /v1/catalog` HTTP round trips, each from its own OS thread + fresh event loop + `httpx.AsyncClient`, identical shape to `r2db-api-http` |

**Disclosed limits** (design D-2 開示事項, carried verbatim in meaning into
the port docstring and `CONDITIONS.md`'s own C-05 row):

1. The concurrency `hold_in_flight` creates is IN-PROCESS concurrency only
   -- every plug realizes it with real OS threads calling directly into
   the same process's own service/foundation object (an HTTP plug's own
   `ASGITransport`, never a real socket). Genuine wire-level/reverse-proxy
   concurrency stays out of this primitive's scope until a future phase's
   own multi-transport work (L7-2).
2. `MitateDB-api` allows at most ONE in-flight operation per cell
   (`ApplicationCell._lock`) -- `hold_in_flight`'s own stop point sits
   BEFORE that lock is acquired, so holding `n > 1` in flight against one
   cell is still structurally possible (the held requests queue behind the
   lock once released), but the `concurrency` bound this peer declares is
   therefore a REFUSAL THRESHOLD, never a claim of `n`-way parallel
   EXECUTION capacity.
3. The scope of the counter a bound protects (a per-deployment in-flight
   count; a per-credential rate window) is not observable by the common
   suite from the outside -- the isolated surface's own application/
   credential population is deliberately small (often exactly one of
   each).

**`_drive_concurrency`'s own recipe** (`test_c05_limit_declaration_
agreement.py`, `_V2_DRIVERS`): declared bound `N` held in flight via
`hold_in_flight` -> an ordinary N+1st request denied (`LIMIT_EXCEEDED`/
`concurrency`) -> release -> the `N` held requests all complete
successfully AND an ordinary request succeeds again (this last check is
this driver's own OBSERVABLE confirmation that `hold_in_flight.__exit__`
genuinely joined every held thread before returning, not merely set the
release event and moved on). A rate-headroom precondition is asserted
before holding (r2db's own `_slot` checks `requests_per_minute` BEFORE
`concurrency`, so an under-provisioned rate window would make the N+1st
probe's denial ambiguous) -- the identical "assert the precondition, don't
silently depend on it" discipline `isolated_application_surface()`'s own
docstring already established for `requests_per_minute`'s own driver.

### 22.2 `select_eq`/`attempt_filter` optional fields (D-2 決定 4, L7-21 実装の形 (c))

Two OPTIONAL, keyword-only fields, additive to both existing signatures --
no existing call site's behavior changes when they are omitted:

```python
def select_eq(self, session, entity, select, field, value, *, limit: int | None = None) -> list[dict]
def attempt_filter(self, session, entity, select, field, operator, value, *,
                    extra_predicates: Sequence[tuple[str, str, Any]] | None = None) -> list[dict]
```

`limit` is the client's own requested page size, presented to the peer's
real page-size parameter verbatim (`QueryRequest.page.size` on the wire,
`spec/data-service-api.v1.json`) -- `None` omits it, exactly the
pre-v1.12 behavior. `extra_predicates` is zero or more additional
`(field, operator, value)` predicates, ANDed with the primary predicate and
presented as additional entries of the SAME real `where`/filter-list entry
point (`QueryRequest.where`, `maxItems: 50`) -- `None`/empty is exactly the
pre-v1.12 single-predicate behavior. Both map directly onto a pre-existing,
unexposed parameter each of the 4 plugs' own real query methods already
had (r2db's `DataService.query(..., page_size=...)`; MitateDB's
`session.read(..., limit=...)`; both HTTP plugs' own internal `_query`/
`_query_request` helpers already accepted `page_size`) -- port v1.12 only
exposes what was already there, on every plug, uniformly.

**L7-21's own capability-判定化** (replacing the peer-name exclusion these
two fields make possible to remove): a V2 driver's decision of WHETHER to
drive a class is now the plug's own LIVE `limit_enforcement` declaration
alone -- never `adapter.name`. `_drive_result_items` is now two-sided on
all 4 plugs (the port-shape gap that kept it r2db-only is closed: r2db's
own check is `min(len(rows), page_size)` against the bound, MitateDB's own
check is the REQUESTED `limit` value directly -- with `bound + 1` actual
rows present, both peers agree `page_size = bound` succeeds and `page_size
= bound + 1` is denied). `_drive_query_complexity` stays ONE-SIDED on all
4 plugs -- a CONCLUSION from the two peers' own incompatible metric
definitions (r2db: `len(where) + len(select) + order_by_count`; MitateDB:
`len(filters)` alone), never an artifact of the removed exclusion -- but is
now driven (and observed) on MitateDB too, via `extra_predicates` inflating
`len(filters)` directly (the pre-v1.12 recipe's `select`-list-length trick
only ever inflated r2db's own metric).

Two static assertions in `test_c05_limit_declaration_agreement.py` pin
L7-21's own proposition going forward (design D-2 実装の形 (c), limited
to "駆動可否を peer 名で決めない" -- deliberately NOT "zero `adapter.name`
reads in this file", which would also flag legitimate, non-exclusionary
peer-specific facts): (i) no `_V2_DRIVERS` driver body contains an early
`return False` guarded by reading `adapter.name`; (ii) every peer-name
equality/prefix read in the module is inside one of 3 allowlisted
functions (`_schema_objects_unit_cost`'s own counting-rule fact;
`_drive_requests_per_minute`'s own `already_consumed` transport-specific
correction; `test_c05_e_isolated_application_surface_releases_resources`'s
own observation-mechanism difference) -- AST-scoped, not a line-number pin,
so the check survives the file being edited/reflowed.

### 22.3 Compatibility impact

Additive to the ABC (§20.6's own first bullet applies identically -- a
plug not implementing `hold_in_flight()` fails to instantiate; all four
now do). `select_eq`/`attempt_filter`'s two new fields are optional
keyword-only additions with `None`/empty defaults -- every pre-v1.12 call
site (every condition file besides `test_c05_limit_declaration_
agreement.py`) is unaffected, byte-for-byte. No peer's PRODUCT code
changed for §22.1 -- `hold_in_flight` is realized entirely inside each
peer's own conformance PLUG (`*/conformance/conformance_adapter_*.py`),
wrapping objects those plugs already construct out-of-band, never a
test-only hook added to `r2db_api`/`mitatedb_api` themselves. §22.2 is
likewise plug-only: each plug's own query helper already accepted the
underlying `page_size`/`limit` parameter before this port revision: only
the plug method's own signature (an optional keyword forwarded through)
changed. `MitateDB-api`'s own `_attempt_mutation_outcome` (used by
`_drive_operation_depth`'s own updated recipe, R-A) additionally routes an
`operation="update"` attempt with a real filter through `session.
transact()` (matching the pre-existing `operation="insert"`+filter
routing) -- a conformance-PLUG dispatch-routing change, not a port
signature change, and verified (by inspection) not to affect any other
caller in this repository: every "update" attempt anywhere else that
carries a real `where_field` is gated behind `revision_preconditions:
enabled`, which this peer declares `unavailable`.

## 23. v1.13 port revision (Phase 9 WP-1, coordinated with docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md §6.1)

Phase 9 contract 1.7.0 adds 7 endpoint-facing capabilities (`dry_run`,
`plan`, `budget`, schema `idempotency_key`, `field_constraints`/`enum`/
`nullable`, result-side `request_id`, result-side `descriptor`) and one
new primitive (`alter_field`) the port had no way to express before this
revision (neither peer implements it yet either). §6.1's own table lists
8 additions; this section fixes their exact shape, additive only, no
removals, matching §21/§22's own compatibility discipline.

### 23.1 New methods and fields

| # | added | to |
|---|---|---|
| 1 | `dry_run: bool = False` (request-unit keyword) | `attempt_mutation_with_result`, `attempt_batch_with_result`, `attempt_cross_entity_batch_with_result`, `schema_operation_with_result` |
| 2 | `plan: str \| None = None` (request-unit keyword) and result-side `plan` | same 4 methods (request side); their return `Mapping`s (result side) |
| 3 | `budget: Mapping[str, int] \| None = None` (request-unit keyword) | same 4 methods, plus `query_with_budget` |
| 4 | `idempotency_key: str \| None = None` | `schema_operation_with_result` (new -- `SchemaOperationRequest.idempotency_key` is itself new in contract 1.7.0) |
| 5 | `enum`/`nullable`/`field_constraints` keywords | `schema_operation_with_result` |
| 6 | result-side `request_id` | `attempt_mutation_with_result`, `attempt_batch_with_result`, `attempt_cross_entity_batch_with_result`, `schema_operation_with_result`, `query_with_budget` |
| 7 | result-side `descriptor` | `schema_operation_with_result` (schema dry-run response only) |
| 8 | `alter_field` primitive | folded into `schema_operation_with_result`'s own `operation` argument (§23.2 below), not a new dedicated method |

Five new abstract methods carry this table: `schema_operation_with_
result`, `attempt_mutation_with_result`, `attempt_batch_with_result`,
`attempt_cross_entity_batch_with_result`, `query_with_budget`. The five
limits §6.1 requires stating (dry_run's observable-state-change scope,
`plan`'s opacity, the per-request-not-per-operation cardinality of
`dry_run`/`plan`/`budget`, `budget`'s downward-only narrowing, and
`BatchOperation`/`ScopedBatchOperation.idempotency_key`'s per-item-field-
vs-per-request-value fold rule) are stated on `ConformanceAdapter`'s own
class docstring (WP-1b rework, review point K: a `#` comment block is not
a docstring -- moved there from a comment block that used to sit just
above `schema_operation_with_result`), not repeated in this document.

### 23.2 `alter_field` folded into `schema_operation_with_result`, not a dedicated method (§6.1 item 8, review point L, monitor 裁定 2026-09-07)

**§6.1 item 8's own table entry reads "`alter_field` primitive (新設)"** --
read most narrowly, a literal new sentence, this could mean a SIXTH new
abstract method, `alter_field(session, entity, field, ...)`, mirroring
`add_field`'s own dedicated-method shape. **WP-1b's implementation instead
folds `alter_field` into the existing, single `schema_operation_with_
result(session, entity, operation, ...)` primitive** as one more value its
`operation` argument accepts, alongside `create_entity`/`add_field`/
`drop_entity`.

**Why the general form, not a sixth dedicated method:**

1. `schema_operation_with_result` already exists as this port's ONE
   general schema-operation primitive (§6.1 items 1-5, 7 all land there:
   `dry_run`/`plan`/`budget`/`idempotency_key`/`field_constraints`/`enum`/
   `nullable`), built specifically because C-20/C-22/C-23/C-24/C-25 each
   need a schema-side observation carrying some subset of these 7 new
   fields against ANY of `create_entity`/`add_field`/`alter_field`/
   `drop_entity` -- a dedicated `alter_field(...)` method would need to
   duplicate that entire keyword surface a second time, or the five new
   condition files would need to call two different methods depending on
   which schema operation they meant, for no different underlying
   request shape.
2. `r2db-api`'s own real dispatcher (`DataService.schema(session, op)`,
   `service.py`) is ALREADY the single generic entry point every schema
   operation on that peer goes through -- there is no PER-OPERATION
   method on that peer's own product code for the port to mirror in the
   first place. A dedicated `alter_field` port method would be a port-
   level distinction the underlying peer does not itself have.
3. `MitateDB-api`'s own peer is a family of dedicated session methods
   (`create_entity`/`add_field`), and genuinely has NO `alter_field`
   session method at all as of this port revision (confirmed by source
   inspection) -- `schema_operation_with_result`'s own `elif operation ==
   "alter_field":` branch raises `SurfaceAbsent` there today, exactly the
   same honest "no real entry point exists yet" claim a dedicated method
   would have to make too. Folding costs nothing extra on this peer.
4. The contract itself does not distinguish `alter_field` from the other
   3 schema operations at the SCHEMA level either --
   `structured_operations.alter_field` is its own contract section (§6.1
   item in the json_path table), but `SchemaOperationRequest.operation`
   is already a single closed-vocabulary field naming all 4 operations on
   the SAME request shape (`create_entity`/`add_field`/`alter_field`/
   `drop_entity`) -- the port's own `operation`-argument dispatch already
   mirrors the wire shape faithfully.

**Limit disclosed**: this folded form means a caller mistyping `operation`
(a value none of `create_entity`/`add_field`/`alter_field`/`drop_entity`
recognizes) is a `str`, not a distinct Python method the type checker
could catch at call sites -- `schema_operation_with_result`'s own `else:`
branch (WP-1b rework, review point I) raises `SurfaceAbsent` for an
unrecognized operation name, never a fabricated `ConformanceDenial`, so a
typo surfaces as a structural-absence claim rather than a silent
misinterpretation.

**Disposition**: raised as a design-vs-implementation discrepancy during
WP-1 implementation (差し戻し指示 11); the supervisor's ruling (2026-09-07,
work order §6 訂正註 3) adopts the folded form as an improvement, records
the reason here, and leaves the work order's own object/completion
condition text unedited (the folded form satisfies §6.1 item 8's own
completion condition -- "port が v1.13 であり、8 追加がすべて入ってい
る" -- without requiring a sixth method).

### 23.3 Compatibility impact

Additive to the ABC: 5 new abstract methods (§23.1), all 4 registered
plugs implement them. Existing methods (`attempt_mutation`, `attempt_
batch_with_addresses`, `attempt_cross_entity_batch`, `create_entity_with_
declared_types`, `add_field_with_declared_type`, `select_eq`, `attempt_
filter`, `catalog_document`, etc.) are byte-for-byte unchanged -- no
existing call site's behavior changes. `BatchOperation`/
`ScopedBatchOperation.idempotency_key` (port v1.11) is unchanged in
shape; its own uniform-or-absent fold rule (§6.1 item (v)) is now
enforced by ONE shared function, `fold_batch_idempotency_key` (module-
level, `conformance-tests/adapter.py`), which every batch-shaped method
on all 4 plugs routes through -- including the pre-v1.13 `attempt_batch_
with_addresses`/`attempt_cross_entity_batch` methods, which before this
WP-1b rework (review point H) folded the per-item field with either an
unguarded `next(...)` (both HTTP plugs) or no folding at all, just the
per-operation raw value (both in-process plugs) -- neither form enforced
the uniform-or-absent rule at all. No peer's PRODUCT code changed for
§23: every new field this section adds is carried through unedited to
the peer's own real entry point (or refused there, pre-flip, by that
peer's own provisional gate, WP-1's own §2 (9)), exactly as every
pre-v1.13 optional field on this port already was.

### 23.4 追補 (2026-09-07): `enum` の tri-state 化 (`ENUM_CLEAR` sentinel, 監督裁定 A)

Contract 1.7.0 amended `alter_field`'s own text (監督裁定 A,
`{scratchpad}/rulings-wp3a-review.md`): "A constraint the request omits
is left as it is; enum: null clears the field's enum, and on add_field
enum: null means the same as omitting it." `SchemaOperationRequest.enum`
is therefore genuinely tri-state on the wire (`["array", "null"]`), but
`schema_operation_with_result`'s own `enum: Sequence[Any] | None = None`
parameter (§23.1) could not express the difference between "the caller
omitted `enum`" and "the caller wants a literal JSON `enum: null`" -- both
collapsed onto the same Python `None`. `test_c20_constraint_declaration_
agreement.py`'s own leg (8) (omit -> unchanged) could be written under the
pre-addendum port; the sibling leg (9) (`enum: null` -> cleared) could
not, and was left as an explicit, disclosed gap in that test module's own
docstring pending this port addition.

This addendum adds one module-level sentinel to `conformance-tests/
adapter.py`, `ENUM_CLEAR` (a single instance of a dedicated `_EnumClear`
class, carrying its own `repr()` for diagnostics -- not a plain string,
unlike `VALID_CONFIRMATION`/`CATALOG_SURFACE_ABSENT`, because an `enum`
value is itself an arbitrary `Sequence[Any]` and a string sentinel could
collide with a legitimate declared enum member). `schema_operation_with_
result`'s `enum` parameter is now `Sequence[Any] | _EnumClear | None`:
`None` (default, unchanged) omits the `enum` key entirely; `ENUM_CLEAR`
puts a literal `enum: null` on the wire; any other `Sequence` puts
`enum: [...]` on the wire, exactly as before. All 4 registered plugs
(`conformance_adapter_r2db.py`, `conformance_adapter_r2db_http.py`,
`conformance_adapter_mitatedb.py`, `conformance_adapter_mitatedb_http.py`)
resolve the sentinel the same way, at the same request-construction site
`field_constraints`/`field_types` already use (`enum is ENUM_CLEAR ->
key = None`; `enum is not None -> key = list(enum)`; `enum is None ->` no
key). Disclosed limit (`conformance_adapter_mitatedb.py`'s own in-process
`add_field` branch, read directly off `mitatedb_api.cell.
ApplicationDeveloper.add_field`'s real `enum=None` keyword default): a
bare Python keyword call cannot itself distinguish "omitted" from
"explicitly `None`" the way a wire-level dict/JSON body can, so this
adapter's own `kwargs` construction resolves the sentinel faithfully, but
that distinction reaching a real behavioral difference on this ONE
in-process entry point would additionally require that peer-side
signature to grow its own tri-state convention -- peer-side territory
this port change does not reach. `test_c20_constraint_declaration_
agreement.py`'s leg (9) (`alter_field(enum=ENUM_CLEAR)` clears the
field's enum, observed both via the catalog's `field_constraints` and via
a subsequent write outside the old enum) replaces that test module's own
prior disclosed-gap comment. Additive only: every pre-addendum call site
(passing a `Sequence`, or omitting `enum`) keeps its exact prior
byte-for-byte request shape.

### 23.5 追補 (2026-09-07): `attempt_mutation_with_result` gains `destructive`/`confirmation`

`test_c22_dry_run_and_plan.py`'s own `_confirm_probe` presents a destructive `delete` through `attempt_mutation_with_result(..., destructive=True, dry_run=...)`, but §23.1 left that method without the pair -- added now as keyword-only `destructive: bool = False, confirmation: Any = None`, following the identical `VALID_CONFIRMATION` protocol `delete`/`drop_entity`/`schema_operation_with_result`/`BatchOperation` already use, in all 4 registered plugs; byte-compatible for every pre-addendum caller that omits both.

### 23.6 追補 (2026-09-07): `attempt_mutation_with_result` gains `transaction`

`test_c22_dry_run_and_plan.py`'s (10) digest-scope leg needs an always-available (never capability-gated, unlike `budget`) request key to prove a plan digest is not `operations`-only -- added as keyword-only `transaction: str | None = None`, carrying `MutationRequest`'s own PRE-EXISTING `transaction` key (`spec/data-service-api.v1.json`) through unedited to whatever real entry point already receives `dry_run`/`plan`/`budget`, in all 4 registered plugs; byte-compatible for every pre-addendum caller that omits it (the key stays off the wire entirely, same as before this addendum).

### 23.7 追補 (2026-09-07): `attempt_mutation_with_result` gains `idempotency_key`

`test_c25_result_request_id.py`'s (4) replay leg needs a request-level idempotency key on a single-operation call -- added as keyword-only `idempotency_key: str | None = None`, carried through unedited to whatever real entry point already receives `dry_run`/`plan`/`budget`/`transaction` (embedded on the single operation item for an in-process plug whose real dispatcher reads it there, exactly where `fold_batch_idempotency_key`'s existing callers already place it; on the request body's own top-level `extra_body` key for a wire-surface plug, exactly where `attempt_batch_with_addresses` already places its own folded value), in all 4 registered plugs; byte-compatible for every pre-addendum caller that omits it.

## 24. v1.14 port revision (Phase 10 WP-3, coordinated with docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-1 (A) 4 / D-1 (A) 6 / D-12)

Phase 10 gives the port a way to know, DECLARATIVELY, which transport an
adapter's own client actually dials through -- previously this could only
be guessed from an adapter's `name` string (`"http+postgres"` substring)
or attribute shape, both of which design D-12 calls a proxy indicator
(`OPERATING_CONDITIONS.md` section 1.7 item 52: "代理指標を使わない").
This revision adds one class attribute, no new abstract methods, no
removals.

### 24.1 `transport_kind` -- a bare, default-less abstract attribute

`ConformanceAdapter` gains:

```python
transport_kind: str
```

placed immediately after the existing `name: str` line. This is a PEP
526 variable annotation ONLY -- no `=` assignment -- so it never becomes
a real class attribute on the ABC itself (`"transport_kind" not in
vars(ConformanceAdapter)`); a concrete subclass that forgets to set its
own `transport_kind = "..."` class attribute raises `AttributeError` the
first time anything reads `adapter.transport_kind`, rather than silently
inheriting a fallback value. This mirrors `name`'s own existing
convention exactly (design D-1 (A) 4, monitor 裁定 2026-09-08: "既定は無
い (各 adapter が明示する抽象属性)").

Three values, closed vocabulary (contract-independent -- this word list
lives in the port, never in `spec/data-service-api.v1.json`):

| value | meaning | declared by |
|---|---|---|
| `"in_process"` | drives the peer's own product objects directly; no ASGI/HTTP boundary at all | `conformance_adapter_r2db.py`, `conformance_adapter_mitatedb.py` |
| `"asgi"` | an in-process ASGI transport (`httpx.ASGITransport`) -- no real socket | `conformance_adapter_r2db_http.py`, `conformance_adapter_mitatedb_http.py` |
| `"socket"` | a real loopback TCP socket, fronted by a real reverse proxy (`conformance-tests/socket_harness.py`) | `conformance_adapter_r2db_socket.py` / `conformance_adapter_mitatedb_socket.py` (WP-4; not registered as of WP-3) |

All 4 currently-registered adapters declare their own value as a single
class-attribute line (`transport_kind = "in_process"` / `"asgi"`),
immediately after their own `name = "..."` line -- the SAME declared
value every one of them already implied by construction; this revision
changes no adapter's own behavior, only makes the classification
explicit and machine-readable.

### 24.2 Consumers

- `tools/perf_baseline.py`'s `_classify_plug` (design D-12) reads this
  declaration instead of an adapter's `name` suffix and attribute shape,
  so its own `transport=` label on the `PERF` line is 1:1 with the
  adapter's own declared value, never a re-derived guess. A plug whose
  name/attribute shape disagrees with its OWN declared `transport_kind`
  still raises `UnknownAdapterShape` (unchanged: a genuinely undeclared
  or malformed plug must still fail loud, not silently fall back to a
  broadened heuristic).
- `test_c19_client_self_sufficiency.py`'s real-dial branch (design D-4)
  is driven by `adapter.transport_kind == "socket"`, never a name/URL
  shape guess -- as of WP-3 this branch's own parametrize list is empty
  (no adapter declares `"socket"` yet), a deliberate, documented vacuity
  (monitor 裁定 `{scratchpad}/wo-rulings-1.md` 裁定 2: the non-vacuity
  assert on this branch is added by WP-4a, once a `"socket"` plug is
  registered). **registry-guards group との相互作用 (F-8 (ii) 差し戻し,
  監督裁定 2026-09-08):** この branch を持つ関数 (`test_c19_surfaces_are_
  really_dialable_on_socket_plugs`) は `@pytest.mark.parametrize("adapter",
  ...)` を持たない (ループ形式の単一関数) ため、`conformance-tests/
  conftest.py`'s own `pytest_collection_modifyitems` (`group = str(
  adapter_param) if adapter_param else "registry-guards"`) によって
  `registry-guards` xdist group に入る -- この group は本来
  `registered_adapters()` を読むだけで実プロビジョニング/実プロセス起動
  を伴わない前提 (同ファイルの `_wp5_application_residue_guard`/`_wp5_
  residue_guard_is_not_vacuous` の docstring 「carries no real cost for
  e.g. `registry-guards`-group tests」) の上に立つ。WP-4a がこの branch へ
  「registry に `transport_kind == "socket"` の plug が 1 件以上ある」の
  非 vacuity assert を足し、かつその本体 (実 socket dial のループ) を実行
  させると、`registry-guards` group を担当する worker が socket plug の
  実 nginx+uvicorn 面を追加で起動することになり、上記前提が崩れる (完了
  条件 14 の起動プロセス数もこの分を含めて数える必要がある)。したがって
  WP-4a は、非 vacuity の判定 (registry の読み取りのみ、実面を起動しな
  い) をこの一関数の外へ切り出す場合でも `registry-guards` group を跨い
  で別の group のテストへ持ち出さないこと -- 実 dial は元々この一関数に
  閉じているので、判定を分離しても同じ関数内に留めるのが最も単純。
- `conformance-tests/socket_harness.py`'s own self-test
  (`test_socket_harness.py::test_every_registered_adapter_declares_
  transport_kind`) pins both halves of this section: every currently
  registered adapter carries a value from the 3-word vocabulary, AND the
  ABC itself carries no default.

### 24.3 Hook extraction on the two HTTP+PostgreSQL plugs (design D-1 (A) 6) -- non-normative, no port change

Not a port-level change (no new abstract method, no signature change on
any existing one) -- recorded here because it is the OTHER half of what
makes `transport_kind == "socket"` realizable in WP-4 without a second,
independently-written HTTP+PostgreSQL plug. `conformance_adapter_r2db_
http.py`'s `R2DBHttpConformanceAdapter` and `conformance_adapter_
mitatedb_http.py`'s `MitateDBHttpConformanceAdapter` each gain two
overridable instance methods (identical shape, independently
implemented, P-6):

- `_build_client(self, app, base_url) -> httpx.AsyncClient` -- default:
  `httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
  base_url=base_url)` (byte-for-byte what every call site constructed
  directly before this extraction). **Contract (監督裁定 2026-09-08, F-2
  (c)):** exactly one `app` per call, exactly one client back -- `app` is
  always a single composed ASGI callable (the data plane's OR the control
  plane's, never both at once). A `transport_kind == "socket"` override
  (WP-4) is free to give EACH `app` its own dedicated uvicorn + its own
  dedicated nginx (one real reverse-proxy pair per app, so "one surface"
  becomes a DATA pair plus a CONTROL pair, two independent real reverse
  proxies) -- this hook never requires, and no caller may assume, that a
  single shared nginx instance fronts two upstreams the way `conformance-
  tests/socket_harness.py`'s own `RealSocketSurface` convenience class
  happens to compose them. `RealSocketSurface` is ONE way to satisfy this
  hook's contract, not the contract itself.
- `_surfaces_value(self) -> dict` -- default: the plug's own existing
  synthetic, non-dialable `surfaces` constant (r2db: the module-level
  `_SURFACES` dict; MitateDB: `{"data": {"base_url": _DATA_SURFACE_
  BASE_URL}, "control": {"base_url": _CONTROL_SURFACE_BASE_URL}}`,
  which now also feeds the `platform_declarations` DB row `_bootstrap_
  platform` seeds via a new `surfaces` parameter, replacing that
  function's own former direct reference to those two module constants).
- `_reset_surface_state(self) -> None` (監督裁定 2026-09-08, F-2 (b)) --
  default: no-op. Called on `isolated_application_surface()`'s own fresh
  `copy.copy(self)` instance, immediately after the copy and before that
  copy's own composition begins. `copy.copy` is a SHALLOW copy: a
  `transport_kind == "socket"` subclass that holds real per-surface OS
  state (a port reservation, a server handle) on `self` would otherwise
  have its isolated copy silently ALIAS the parent's own live handles
  with no hook-driven place to replace them; this hook is that place.

Every construction site that used to build a client or inject `surfaces`
directly (both plugs' own `__init__` data/control clients, r2db's
control-stack rebuild path, both plugs' `isolated_control_surface`, both
plugs' `isolated_application_surface`, and both plugs' `hold_in_flight`
realization -- `_hold_in_flight_via_http_requests` / `_hold_in_flight_
via_http_requests_over_stalled_gate`, the one remaining direct-
construction site the original extraction missed, closed by 監督裁定
2026-09-08 F-10) now goes through one of these hooks, including the
isolated-surface sites (design D-1 (A) 6 point (c): "隔離surfaceの構築
も同じhookを通す"). A socket-adapter subclass (WP-4) overrides
`_build_client`/`_surfaces_value`/`_reset_surface_state`; its isolated
surface then gets its own dedicated uvicorn+nginx instance rather than
silently sharing the parent's (the exact failure design D-1 (A) 6 names:
"隔離面が親の共有appをserveしたまま緑で通りC-05の隔離駆動が無音で誤
る"), and `hold_in_flight`'s own held requests dial the real socket too,
never falling back to an in-process ASGI transport the parent surface
itself no longer uses.

Behavior-preserving for all 4 currently-registered plugs, fixed by
running `conformance-tests` before and after this extraction and
observing an identical 4-number tally for the pre-existing test surface
(WP-3 completion condition 10). 監督裁定 2026-09-08 (F-7): that before/
after tally is recorded in WP-3's own completion report
(`{scratchpad}/phase10/wp3-report.md`/`wp3-report-2.md`), not in this
design document -- `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §11
carries no such record as of this revision. Completion condition 14 (the
real launch-COUNT question -- how many uvicorn/nginx processes a full run
starts once a `transport_kind == "socket"` plug exists) cannot be
measured at all until WP-4a registers one; WP-4a measures it then and
records it, together with this section's own before/after tally, in
`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §11.

## 25. v1.15 port revision (Phase 10 WP-6d-ii, coordinated with docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md §3 D-13 「実装の形 (6d-ii) の確定」)

Phase 10's own D-13 closes a real gap external review 2 found: two
concurrent requests carrying the SAME idempotency key could both observe
"no record" and both execute (`docs/design/ROADMAP_POST_PHASE7_V1.md` §8
R-24). WP-6d-i closed this inside both peers' own backend/in-memory
locks; this revision gives the common suite a deterministic way to
DRIVE that closure -- new condition C-27 -- the same "test-driving
primitive, never a test-only hook on product code" discipline `hold_in_
flight` (port v1.12) already established, applied to the idempotency
admission window instead of the concurrency counter. One addition, no
removals.

### 25.1 `hold_after_idempotency_lookup(session, idempotency_key)` (D-13 「実装の形 (6d-ii) の確定」(1)/(2))

Added to `ConformanceAdapter` immediately after `hold_in_flight`:

```python
def hold_after_idempotency_lookup(self, session, idempotency_key: str) -> AbstractContextManager["IdempotencyHold"]
```

Meaning (verbatim, design §3 D-13 「実装の形 (6d-ii) の確定」(1) -- carried
into the port docstring unparaphrased, per this repository's own 常設
規律 4): 「`session` 上で次に到着する、`idempotency_key` に一致する key を
持つ要求を 1 件だけ、その要求自身の **idempotency 受理区間の末尾**で停止
させたまま保持する。受理区間の末尾とは、照会が「記録なし」を返し、
`idempotency_entries` の予約を取り終え、その区間が取った lock をすべて
保持したまま、効果をまだ 1 件も実行していない地点である。保持中に
同じ key を持つ 2 件目の要求を出すと、2 件目はその同じ lock の上で実際に待ち、
先着が解放されて commit した後にはじめて答えを返す。`with` を抜けると
先着は解放され、実行・記録・commit まで進む。保持するのは 1 件だけであり、
`idempotency_key` に一致しない要求は素通しする。」

**Structural difference from `hold_in_flight`** (design 同 (2)): this
primitive never issues any request of its own. The held request ("A")
and the second, waiting request ("B") are both issued by the CALLER,
each from its own OS thread -- this method only arms the ONE stall
point and yields the `IdempotencyHold` handle a caller uses to wait for
A to actually reach it. A caller confirms B has not completed while A
is held with a bounded wait window of its own -- the same shape both
peers' own `tests/test_idempotency_concurrency.py::_assert_second_call_
is_blocked` already uses.

**`IdempotencyHold`** (non-normative, `adapter.py` module level, the
same "non-normative handle yielded by a primitive" status `Isolated
ControlHandle` (§21.4) already carries): one method,

```python
def wait_until_held(self, timeout_s: float = 30.0) -> int
```

Blocks until the held request has actually reached the stall point,
then returns the REAL measured count of requests held there (always `1`
for a correct realization -- this primitive holds exactly one request,
never more; `hold_in_flight`'s own `entered_count`/裁定 5 rationale,
carried over unchanged: a caller must be able to tell "did this
primitive actually hold something" without a tautological check).
Raises `AssertionError` -- never skips, never times out silently -- if
the held request has not reached that point within `timeout_s` seconds
(`OPERATING_CONDITIONS.md` §1.3 の 26). Default `30.0` matches the 4
adapters' own pre-existing `_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S` constant.

**Why the stall point sits at the END of the admission section, not at
the lookup's own return point** (design 同 (3)): the monitor's own
original framing ("照会の直後・実行の前") is satisfied by either point,
but only the END of the admission section keeps observation (iii)
(the `idempotency_entries` count bound) genuinely load-bearing. Stalling
at the lookup's own return leaves the count-bound lock un-taken, so a
concurrent second, different-key request would race UNHELD and this
suite's own test orchestration -- not the real lock -- would end up
serializing the two attempts, staying green even with the count-bound
lock removed (a vacuous observation, design's own words: "既存の逐次経路
の bound 検査 (C-23) と同じものを二度書くだけの、変異で赤くならない
観測になる").

### 25.2 Per-plug realization (design D-13 「実装の形 (6d-ii) の確定」(4), measured)

**Realization is adapter-internal, never a product-code hook** (design
§4, same discipline as `hold_in_flight`): each plug monkeypatches a real
bound method (or pair of methods) on the SAME cell/backend object it
already constructs out-of-band for `isolated_application_surface()`.
Both peers' own `tests/test_idempotency_concurrency.py` already stop at
this exact same point, by this exact same technique -- this port
revision only lifts that shape up to the common port.

| plug | wraps | why the stall point is the end of the admission section on this peer's own structure | what a concurrent second request actually waits on |
|---|---|---|---|
| `r2db-api` (in-process) | the isolated instance's own per-application `structured.ApplicationCell`'s own `_idempotency_lookup` (arms the calling thread when the key matches and the record is absent) and `_idempotency_reserve` (stalls the armed thread at its own return) | `transact`/`apply_schema` hold the cell's own `self._idempotency_lock` (a `threading.Lock`) for their ENTIRE call -- lookup -> reserve -> execute -> store -- so `_idempotency_reserve`'s own return is already past the reservation and still inside that lock | the cell's own `threading.Lock` (`transact`'s/`apply_schema`'s own outer entry) -- a second request never even reaches `_idempotency_lookup` while the first is held |
| `r2db-api-http` | the SAME per-application `PostgresCell`'s own `_idempotency_lookup`/`_idempotency_reserve` (`postgres.py`), identical wrap shape | the effect's own outer transaction takes `_idempotency_key_lock` (a `pg_advisory_xact_lock` on the key) before `_idempotency_lookup`, and `_idempotency_reserve_lock` (a table-level `pg_advisory_xact_lock`) before `_idempotency_reserve` -- `_idempotency_reserve`'s own return holds BOTH | the real `pg_advisory_xact_lock`s themselves -- a second request for the SAME key blocks inside its own `_idempotency_key_lock` call; a second request for a DIFFERENT key, once past its own key lock, blocks inside `_idempotency_reserve_lock` |
| `MitateDB-api` (in-process) | the SAME per-application `ApplicationCell`'s own `_idempotency_check` (`cell.py`) -- the ONE choke that performs both the lookup AND the reservation and returns `(replay_response, digest, now_ms)`; a fresh admission is exactly `replay_response is None` | every public entry point holds this cell's own `self._lock` (an `RLock`, phase 10 WP-8b's own outer lock) for its ENTIRE call -- lookup -> pass-1 -> pass-2 -- so `_idempotency_check`'s own return is already past the reservation and still inside that lock | the cell's own `RLock` -- a second request never even reaches `_idempotency_check` while the first is held |
| `MitateDB-api-http` | the SAME per-application `ApplicationCell`, identical wrap shape (the real HTTP dispatch reaches the SAME cell class the in-process plug does) | identical to the in-process plug's own reasoning -- this common suite drives exactly one `ApplicationCell` per Application, one process, one cell | the SAME cell's own `RLock` -- the PostgreSQL SESSION advisory locks `idempotency_begin`/`idempotency_reserve` also take are never reached by a second in-process request either (disclosed limit, §25.3) |

**Socket plugs (WP-4) are two subclasses of the http adapters and inherit
this realization unchanged** -- no socket-specific code exists for this
primitive (design D-1 (A) 6 composition, §24.3): an HTTP plug's app runs
in the same process as the test, so the monkeypatch reaches it exactly
as `hold_in_flight` already established (C-05's own precedent).

**xdist group** (design 同 (8)): no explicit `xdist_group` marker on
C-27's own per-plug tests -- `conformance-tests/conftest.py`'s own
adapter-param-based auto-grouping already places them, the same
treatment C-05's own tests get (C-05 itself carries no explicit marker
either). Only the registry-wide, non-parametrized non-vacuity guard
(driven-plug-count) falls into the shared `registry-guards` group.

### 25.3 Disclosed limit (design D-13 「実装の形 (6d-ii) の確定」(7), carried verbatim in meaning into `CONDITIONS.md`'s own C-27 row)

On `MitateDB-api-http`, removing the PostgreSQL SESSION advisory locks
(`idempotency_begin`/`idempotency_reserve` take) does NOT turn C-27 red.
This common suite drives exactly one `ApplicationCell` per Application
(one process, one cell), and that cell's own `RLock` already serializes
the two concurrent requests before either ever reaches the advisory
lock -- the advisory lock only becomes load-bearing ACROSS cells (that
is, across processes sharing one PostgreSQL-backed Application), a
shape this common suite has no way to construct (the same observation
boundary `process_ceilings` and C-26 (4) already disclose: this suite
cannot serve one deployment from two processes). This is an
observation-scope disclosure, not a weakening of C-27 itself -- the
`r2db-api-http` row of §25.2's own table pins the equivalent real
advisory lock directly, inside this very suite; the MitateDB advisory
lock's own non-vacuity is instead carried by the PEER-LOCAL `MitateDB-
api/tests/test_idempotency_concurrency.py`, which drives two separate
`cell_a`/`cell_b` objects against the SAME PostgreSQL database precisely
to exercise it where the in-process cell lock cannot.
