# 作業指示書 — R-51 MitateDB の監査クエリの reader 例外

## 0. 版数・位置づけ

- **v1.0 (2026-09-18)。** 基点 main `04c62b4`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-51。変更クラスは **Class B** (契約・不変条件・migration・runbook に触れない)。設計文書は持たない (本書 §1 が枠)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 枠 (監督の現物確認 2026-09-18)

- 台帳の「汎用の 500」は不正確である。`MitateDB-api/src/mitatedb_api/audit_query.py` の `PostgresAuditQueryStore.query` は `psycopg.Error` を捕らえず、例外は `MitateDB-api/src/mitatedb_api/control_http.py` の `_endpoint` の `except Exception` に落ちて `_generic_service_unavailable` (HTTP 503、code `SERVICE_UNAVAILABLE`) になる。契約 (`spec/data-service-api.v1.json` の `errors.codes`) に timeout の語彙は無く、`SERVICE_UNAVAILABLE` が合う。**応答の code と status は今も正しい。**
- 直すもの: (i) この経路だけが最後の網に頼っていること (同 peer の platform 側の他の store は `except psycopg.Error` → `StorageConfigurationError` の型を通り、`_CLASSIFY_ORDER` で分類される。r2db-api の同じ `query` は `except psycopg.Error` → `SERVICE_UNAVAILABLE` を持つ)。(ii) `0013_role_statement_timeouts.sql` が `mitatedbsvc_auditreader` に置いた `statement_timeout` (5000ms) による `QueryCanceled` の挙動を固定するテストが無いこと。
- 変えないもの: 応答の code・status、契約、migration、r2db-api、同型性 pin (`_ISOMORPHIC_TARGETS` に `query` 本体は無い)。

## 2. WP-1

### 2.1 触ってよいパス

- `MitateDB-api/src/mitatedb_api/audit_query.py` — `PostgresAuditQueryStore.query` の接続〜fetch の範囲に `except psycopg.Error` を足し、同 peer の platform 側 store と同じ型 (`StorageConfigurationError`。メッセージは既存の同型の箇所に合わせ、DSN・SQL・PostgreSQL のエラー文を含めない) を送出する。接続の close は今のとおり保つ。
- `MitateDB-api/tests/test_audit_query_reader_errors.py` (新規)。
- 新規ファイルで赤になる静的 pin があれば実測して報告する (直さない)。

### 2.2 完了条件

1. `query` の中で起きた `psycopg.Error` は `StorageConfigurationError` になり、接続は閉じられる (store の単位のテスト。例外の型で最後の網と区別する)。
2. 実 PostgreSQL での `QueryCanceled`: 監査表に別接続で `ACCESS EXCLUSIVE` のロックを保持し、reader 側に短い `statement_timeout` を効かせた状態で `query` を呼ぶと 1 の型になる (sleep の長さに結果が依存しない形にする。timeout の効かせ方は既存の fixture で可能な方法を選び、報告に書く)。
3. HTTP の面: reader が `psycopg.Error` を出すとき、監査クエリの応答は 503・code `SERVICE_UNAVAILABLE` で、body に DSN・SQL・PostgreSQL のエラー文が現れない。
4. 下の対応表に対応の無い行が無い。

### 2.3 完了条件 → 変異

| 完了条件 | 変異 |
|---|---|
| 1・2 | M1: 足した `except psycopg.Error` を外す → 1 と 2 のテストが赤 |
| 1 (close) | M2: `finally: conn.close()` を外す → 赤 |
| 3 | M3: 送出するメッセージに `str(exc)` を混ぜる → 赤 |
| 4 | 監査照合 (本表) |

### 2.4 道具の引数

- テスト: `tools/dev/pt.py -C .claude/worktrees/r51-audit-query -- MitateDB-api/tests -q`
- 変異: `tools/dev/mutate.py "$SP/r51-mutations.json" -C .claude/worktrees/r51-audit-query`

## 3. 訂正註 1 (2026-09-18、監督裁定 S-1) — 送出する型

実装担当の疑義を採る。§1・§2.1 が指定した「`except psycopg.Error` → `StorageConfigurationError`」は現物と合わない: `MitateDB-api/src/mitatedb_api/errors.py` の `StorageConfigurationError` は PERMANENT な権限・GRANT の誤設定の型で、TRANSIENT な不達 (timeout を含む) を入れないと docstring が定めている。`AuthorizationStateUnavailable` は契約 code `AUTH_STATE_UNAVAILABLE` に写るので、認証・認可が済んだ後の reader の不達には使わない (r2db-api の同じ経路は `SERVICE_UNAVAILABLE`)。control plane 側に「依存先が今は応えない」→ `SERVICE_UNAVAILABLE` の型が無い (`AuditSinkUnavailable` は書き込み側の sink 専用で、data plane の `http.py` だけが分類する)。

**裁定**:
- `errors.py` に `AuditReaderUnavailable(FoundationError)` を足す (監査の読み取り側の依存先が今は応えない、の型。docstring は `AuditSinkUnavailable` と同じ粒度で、3 つの既存の型との区別を書く)。
- `control_http.py` の `_CLASSIFY_ORDER` に `(AuditReaderUnavailable, "SERVICE_UNAVAILABLE")` を足す。
- `PostgresAuditQueryStore.query` は同 peer の platform 側 store と同じ 2 段にする: `psycopg.errors.InsufficientPrivilege` → `StorageConfigurationError`、それ以外の `psycopg.Error` → `AuditReaderUnavailable`。メッセージに DSN・SQL・PostgreSQL のエラー文を含めない。
- 触ってよいパスに `MitateDB-api/src/mitatedb_api/errors.py` と `MitateDB-api/src/mitatedb_api/control_http.py` (上の 1 行と import だけ) を足す。応答の code・status は変わらない (Class B のまま)。
- 完了条件 1・2 の「型」は `AuditReaderUnavailable` と読み替える。足す完了条件 5: `InsufficientPrivilege` は `StorageConfigurationError` になる。足す完了条件 6: HTTP の面の 503 が最後の網 (`_generic_service_unavailable`) ではなく分類の経路を通る。
- 足す変異: M4 = `InsufficientPrivilege` の節を外す → 5 が赤 / M5 = `_CLASSIFY_ORDER` の足した行を外す → 6 が赤。M1〜M3 は同じ。
- `errors.py`・`_CLASSIFY_ORDER` を件数や集合で固定する静的テスト・同型性 pin があれば、実測して報告する (集合の増減は監督裁定)。
