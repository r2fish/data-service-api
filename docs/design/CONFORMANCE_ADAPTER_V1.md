# 共通conformance実効化設計 v1 — peer adapter port

## 文書情報

- 版数: 1.2 (§10.7 に Phase B レビュー由来の mutation test M5〜M11 を追加、§10.8/§10.9 を新設)
- 発行日: 2026-08-27
- 設計担当: Opus
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
