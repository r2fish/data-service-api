# 共通conformance実効化設計 v1 — peer adapter port

## 文書情報

- 版数: 1.4 (§13 を新設。port v1.3: `docs/design/R2DB_CCR13_STORAGE_V1.md` work package WP-5a 由来の coordinated revision -- C-17/C-18 の test file 実装・実行可能化、C-12 逆向き条件 (query 演算子)、`attempt_mutation` への `unique_key`、`attempt_mutation_with_addresses`、`attempt_filter`、r2db plug の型配線有効化、C-03 の contains/matches value corpus 拡張。逆向き条件の実提示で発見した `MitateDB-api` の `contains`/`is_null` 非適合 (`CAPABILITY_UNSUPPORTED` ではなく `VALIDATION_FAILED`) を是正)
- 発行日: 2026-08-28
- 設計担当: Opus (§1〜§11)。§12/§13 は `docs/design/R2DB_CCR13_STORAGE_V1.md` (設計: Fable) の指示に基づき、本文書 §11 の coordinated design revision 手順を実装側 (Sonnet) が適用したもの (独立レビュー: Opus)
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

C-03のvalue position corpusに含まれる NUL byte payload (`nul_byte`: `"value\x00tail"`) は、`ApplicationCell` (in-memory) では値としてそのままbyte-equalに往復する。`PostgresCell` では同じpayloadが分類済み `ConformanceDenial` として拒否される: JSONBはNUL byte (` `) を含むテキストを表現できないため (PostgreSQLの制約であり、`PostgresCell`固有の検証ではない)、値をJSONBへ書き込む時点でPostgreSQL自身がエラーを返し、これを安全に分類して拒否する。

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
