# 作業指示書 — R-56 r2db-api の auditreader の `statement_timeout`

## 0. 版数と位置づけ

- **v1.0 (2026-09-19)。** 台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-56** (`RM`:453)。設計文書は **`docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` v1.0 (監督確定、設計レビュー 1 回)** で、枠・決定・却下案・実測はすべてそちらにある。本書はその Change Set Manifest である。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。
- 基点 main `7ad7588`。

### 0.1 変更クラス (`tools/change_class.py` の path 規則と `RM` §9 の 8)

| WP | クラス | 導出 |
|---|---|---|
| WP-1 | **B** | 触る path に `security/`・`spec/`・`conformance-tests/`・`CLAUDE.md` が無く、`.md` 以外 (migration `.sql`・テスト・conformance adapter・配備 script) を含む |
| WP-2 | **C** | 登録済みの同型 helper の本体の変更 (`_verify_declarations_checks` ほか) と `_ISOMORPHIC_TARGETS` への行の追加 (後者は単独では D の契機) |
| WP-3 | **D** | `security/CONTROL_MAPPING.md` は最重ルール (`security/` 配下)。先例は `docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md`:16 |

- **全体は D** (設計 §9)。D が求める追加証拠 (依頼者裁定の逐語、版付き security-contract 決定 = `CONTROL_MAPPING` 版 2.12) は設計 §9.1 に在る。
- 契約版数は **1.8.0 のまま据え置く** (`spec/` に触れない。設計 §2 の (i))。設計レビューは 1 回で済んでいる (設計 §9)。

## 1. 共通の枠

### 1.1 読むべき正本

- 設計 `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` v1.0 の §3 (現物の事実)、§4 (D-1〜D-4)、§5 (追随する現物)、§6 (テストと変異)、§7 (証拠と `CONTROL_MAPPING`)、§9・§9.1 (変更クラス)。
- `CLAUDE.md` (正本の順序・境界)、`docs/work-orders/OPERATING_CONDITIONS.md` §0・§1.4・§1.5・§1.6・§1.9・§1.10。

### 1.2 全 WP 共通の触らないファイル

`spec/`、`security/SECURITY_INVARIANTS_V1.md`、`security/CONTROL_MAPPING_HISTORY.md`、`conformance-tests/CONDITIONS.md`・`CONDITIONS_HISTORY.md`、`conformance-tests/` の各テスト本体、`r2db-api/migrations/0002_provisioning_functions.sql` の `begin_provision_application` (設計 D-2)、`r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql`・`0013_role_connection_limits.sql` (設計 §2 の (ii))、`MitateDB-api/migrations/` 全部 (MitateDB の migration は本件で変えない。設計 §4 D-4)、`docs/design/` の記録 (統合の記録は監督が行う)、`.github/`、`tools/dev/`。

### 1.3 順序と触るファイルの重なり

- **直列**: WP-1 → WP-2 → WP-3。**WP-1 と WP-2 は同じ実装担当が続けて行う** (監督裁定 2026-09-19)。
- WP-1 と WP-2 は `r2db-api/tests/test_ops_verify_declarations.py` と `r2db-api/tests/test_audit_query.py` で触るファイルが重なる。したがって**並行にはできない** (`OPERATING_CONDITIONS.md` §1.2 の 16・17 の「重なり 0」を満たせない)。同一担当の直列で扱う。
- WP-3 の触るパスは WP-1・WP-2 と重ならない (§4.2 の表)。

### 1.4 worktree と道具の引数

- worktree は監督が起こす (想定名 `r56-impl` = WP-1 → WP-2 を通しで、`r56-wp3`)。以下の `-C` はその worktree を指す。
- テスト: `tools/dev/pt.py -C <worktree> -- <pytest 引数>` (前景・Bash timeout 600000。§1.6 の 42)。
- 変異: `tools/dev/mutate.py "$SP/r56-wp1-mutations.json" -C <worktree>`。`$SP` は自分の scratchpad。
- **`gate.py` / `finalize.py` / `pytest` の直接実行・commit・merge は行わない** (監督)。

### 1.5 実装担当の注意 (全 WP 共通)

1. **下請けの Agent を起動しない** (§1.7 の 47)。
2. **suite 全体を回さない。** 担当範囲のファイルだけを `pt.py` で回す (完了ゲートは監督)。
3. **commit・`gate.py`・`finalize.py` は監督が行う。** 作業ツリーを綺麗にしたまま報告で終わる。
4. **疑義は実装せず報告に書く。** 設計に無い検査・機構を足さない (§1.5 の 37)。設計と現物が食い違ったら止まって上げる。
5. **絶対パス・一時ディレクトリ名 (`dsa-testpg-…` / `pytest-of-…`)・traceback を文書やコメントに書かない** (§1.9、§2 の 13)。接続は一般形で書く。
6. **実 credential・実ホスト名・実ドメイン・実 DSN を 1 つも書かない。** 合成値と `example.invalid` のみ。
7. conformance は**担当ファイルだけを前景の 1 回**で回しきる。`conformance-tests` と `tools/tests` を 1 回の pytest に結合しない (別々に呼ぶ)。
8. 変異は **1 項目 1 テスト** (`mutate.py` は `expect=red` に `-x` を付け、先頭の失敗で打ち切る)。
9. 新規ファイルを足すと件数 pin の静的テストが赤くなることがある。赤が出たら**直さずに実測を報告**する (§1.5 の 40b)。
10. **報告は必ずファイルに書く** (`$SP/r56-wp<N>-report.md`)。**最終の往復も報告ファイルに残す** — 口頭の応答だけで終わらせない。

## 2. WP-1 — migration `0014` と実 PostgreSQL のテスト

### 2.1 目的と範囲

設計 §4 の **D-1** を現物にする。`r2db-api/migrations/0014_auditreader_statement_timeout.sql` を新規に置き、`r2dbsvc_auditreader` に role 設定の `statement_timeout = '5000ms'` を 1 文で置く。あわせて設計 §6 の完了条件 1・2・3 と、§5 の追随 (位置 slice の直し → migration 一覧・conformance adapter・件数 pin・配備 script) を行う。**MitateDB-api には触らない。**

### 2.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/migrations/0014_auditreader_statement_timeout.sql` (**新規**)、`r2db-api/tests/test_ops_verify_declarations.py` (`MIGRATION_NAMES` と位置 slice)、`r2db-api/tests/test_audit_query.py`・`test_application_audit.py`・`test_credential_persistence.py`・`test_process_ceilings_declaration.py`・`test_ops_declarations.py`・`test_control_plane_store.py` (migration 一覧と fixture)、`r2db-api/tests/test_platform_upgrade_ledger_scan.py` (件数 pin)、`r2db-api/conformance/conformance_adapter_r2db_http.py`・`real_server_r2db.py`、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh`、新規テストファイル (置く場合) | §1.2 の共通。`r2db-api/src/` (WP-1 では製品コードを変えない。設計 §6 の完了条件 2 は「製品コードを伴わないテスト追加」)、`security/`、`docs/`、両 runbook (WP-2)、MitateDB-api 全部 |

- **`0014` の形の指定** (設計 §4 D-1): 本体は `ALTER ROLE r2dbsvc_auditreader SET statement_timeout = '5000ms';` の 1 文。**存在検査を付けない** (MitateDB `0013`:71 と同じ作法)。`BEGIN;`/`COMMIT;` で囲む。role 名は**リテラル**で書く (prefix 置換方式が効く。理由は設計 §4 D-1 の「様式の理由」)。
- **ヘッダに現在形で書く項目**: WHO RUNS THIS (`$R2DBSVC_CONTROL_DSN`、`-v ON_ERROR_STOP=1`)、ORDER (`0007` の後。役が無ければ undefined-role で失敗しファイル全体が巻き戻る)、PERMISSIONS (CREATEROLE + 対象 role への ADMIN OPTION。auditreader を作ったのと同じ役で繋いだときだけ成功する)、IDEMPOTENCY、COMPATIBILITY (ADDITIVE ONLY)、**そして「既存の session には効かない。適用後に reader の pool を持つ process (control) を再起動する」** (設計 §4 D-1 の高 1)。
- **着手の順序 (設計 §5、中 7)**: **先に位置 slice の直しを行う。** `r2db-api/tests/test_ops_verify_declarations.py`:69 の `MIGRATION_NAMES_WITHOUT_DECLARATIONS = MIGRATION_NAMES[:-2]` は同型 pin 済み (`r2db-api/tests/test_audit_query.py`:2697)。位置 slice に依る箇所を**全部実測して列挙**し、**位置ではなく名前で選ぶ形**に直す。同型 pin の対象なので**両 peer を同じ形にする** — この 1 点だけは MitateDB-api の `tests/test_ops_verify_declarations.py` に触ってよい (§1.2 の例外。触ったら報告に明記する)。直した後に `0014` を `0007` の後の位置へ入れる。
- **配備 script**: `part1_provision_host_and_db.sh` に足すのは **`0014` だけ** (設計 §5 の中 8)。`0013` は足さない。位置は `0007` の段 (:341-345) の後、形は既存の `0012` の段 (:406-409) と同じ。適用順のヘッダコメント (:280-292) にも 1 行足す。

### 2.3 完了条件

| # | 完了条件 |
|---|---|
| W1-1 | 実 PostgreSQL で、`0014` 適用後に **reader の DSN で新しく開いた**接続の実効値が **5000** である。読みは `pg_settings.setting` (生の ms) と `5000` の比較 — `SHOW`/`current_setting` は使わない (設計 §6 の 1、低 9) |
| W1-2 | 実 PostgreSQL で、5000ms を**超える**監査の問い合わせが 503・code `SERVICE_UNAVAILABLE` になり、body に DSN・SQL・PostgreSQL のエラー文が現れない。**テストは自前の締め切りを持ち、経過時間が上限 (例 8 秒) 未満であることを assert する。** 遅さは reader の SQL を遅くする方法で作る (**ロック待ちに依らない** — 依ると変異時に無限待ちになる)。store は scenario の中で**新規に構築**し、最初の問い合わせがその store の最初の使用であることを確かめる。接続が pool に戻っていることは**直後の通常の問い合わせが通ること**で観測する (設計 §6 の 2、中 6) |
| W1-3 | `0014` を 2 回続けて適用しても 2 回目が成功し、終端状態が同じである (冪等) |
| W1-4 | **位置 slice の直しが終わっている**: 位置で migration を選ぶ箇所が両 peer に 1 つも残らず、名前で選ぶ形になっている。直した箇所を `file:line` で報告に列挙する |
| W1-5 | §5 の追随の一覧に載る r2db の現物がすべて `0014` を含み、`test_platform_upgrade_ledger_scan.py` の集計が `対象外: 11` になる |
| W1-6 | `part1_provision_host_and_db.sh` に `0014` の段と適用順ヘッダの 1 行が在り、`0013` は足されていない |
| W1-7 | 触ったファイルに実値が無い (§1.9)。`python3 tools/public_value_scan.py <触ったファイル>` の集計行を報告に貼る |
| W1-8 | **本番に対して何も実行していない。** 試験の接続先は使い捨ての PostgreSQL だけである |
| W1-9 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) |

### 2.4 完了条件 → 変異

赤になる test id は予想であり、**実装担当が実名に置き換えて報告する**。

| # | 変異 (操作) | 期待 |
|---|---|---|
| W1-1 | **M1**: `0014` の `ALTER ROLE … SET statement_timeout = '5000ms';` の行を外す | 赤 (実効値が既定値のまま) |
| W1-2 | **M2**: `r2db-api/src/r2db_api/credential_store.py`:1778 の `except psycopg.Error:` を外す | 赤 (503 にならない) |
| W1-3 | **M3**: `0014` の `ALTER ROLE … SET` を `ALTER ROLE … RESET statement_timeout` に変える | 赤 (冪等の終端状態が違う) |
| W1-4 | **監査照合**: 位置 slice を名前選択に直した箇所の `file:line` と直した後の式を逐語で報告に残す。あわせて「位置 slice が 0 件」を示す grep の出力を貼る | — |
| W1-5 | **M4**: migration 一覧のどれか 1 本から `0014` を落とす (1 ファイル 1 項目) | 赤 (その fixture を使うテスト) |
| W1-6 | **監査照合**: script の該当行 (`file:line`) と、`0013` を grep して 0 件であることを報告に残す | — |
| W1-7 | **監査照合**: `public_value_scan` の集計行 | — |
| W1-8 | **監査照合**: 接続先の出所 (テスト基盤の管理 DSN の**環境変数名**) の `file:line`。**実 DSN・実ホスト名を書かない** | — |
| W1-9 | **監査照合**: 本表の行数と対応数 | — |

- **M2 と M1 は必ず別項目にする** (監督裁定 2026-09-19)。1 項目の `tests` に 2 件以上を並べない (§1.5 の 8)。

### 2.5 変異の JSON (雛形。`old` は実装後の現物に合わせて埋める)

```json
{
  "pytest": ["-q"],
  "mutations": [
    {"id": "M1", "file": "r2db-api/migrations/0014_auditreader_statement_timeout.sql",
     "old": "ALTER ROLE r2dbsvc_auditreader SET statement_timeout = '5000ms';", "new": "",
     "tests": ["r2db-api/tests/<W1-1 のテスト>"], "expect": "red"},
    {"id": "M2", "file": "r2db-api/src/r2db_api/credential_store.py",
     "old": "        except psycopg.Error:", "new": "        except _NeverRaised:",
     "tests": ["r2db-api/tests/<W1-2 のテスト>"], "expect": "red"},
    {"id": "M3", "file": "r2db-api/migrations/0014_auditreader_statement_timeout.sql",
     "old": "SET statement_timeout = '5000ms'", "new": "RESET statement_timeout",
     "tests": ["r2db-api/tests/<W1-3 のテスト>"], "expect": "red"},
    {"id": "M4-verify", "file": "r2db-api/tests/test_ops_verify_declarations.py",
     "old": "    \"0014_auditreader_statement_timeout.sql\",\n", "new": "",
     "tests": ["r2db-api/tests/test_ops_verify_declarations.py::<F-8 の fixture を使うテスト>"], "expect": "red"}
  ]
}
```

- M2 の `new` は「絶対に一致しない例外型」にするのが確実だが、**その型が未定義だと import 時に落ちて赤の理由が変わる**。実装担当が「捕らえない形」を現物で選び、選んだ理由を報告に書く。

### 2.6 実行するコマンド

```bash
# r2db のテスト (担当範囲。suite 全体は回さない)
tools/dev/pt.py -C .claude/worktrees/r56-impl -- r2db-api/tests/test_audit_query.py r2db-api/tests/test_ops_verify_declarations.py r2db-api/tests/test_platform_upgrade_ledger_scan.py -q
tools/dev/pt.py -C .claude/worktrees/r56-impl -- r2db-api/tests/test_application_audit.py r2db-api/tests/test_credential_persistence.py r2db-api/tests/test_process_ceilings_declaration.py r2db-api/tests/test_ops_declarations.py r2db-api/tests/test_control_plane_store.py -q
# 位置 slice を両 peer で直した場合のみ、MitateDB 側の該当ファイル 1 本
tools/dev/pt.py -C .claude/worktrees/r56-impl -- MitateDB-api/tests/test_ops_verify_declarations.py MitateDB-api/tests/test_audit_query.py -q
# conformance (audit_query を通る担当ファイルだけ。前景で 1 回)
tools/dev/pt.py -C .claude/worktrees/r56-impl -- conformance-tests/test_c05_limit_declaration_agreement.py conformance-tests/test_c09_audit_evidence.py conformance-tests/test_c11_response_schema_conformance.py conformance-tests/test_c19_client_self_sufficiency.py conformance-tests/test_c25_result_request_id.py -q
# tools 側 (conformance と結合しない)
tools/dev/pt.py -C .claude/worktrees/r56-impl -- tools/tests -q
# 変異
tools/dev/mutate.py "$SP/r56-wp1-mutations.json" -C .claude/worktrees/r56-impl
```

- conformance のファイルの根拠 (2026-09-19 の実測): `audit_query` / `audit/query` を参照する conformance のテストは `test_c05`・`test_c09`・`test_c11_response_schema_conformance`・`test_c19`・`test_c22`・`test_c25`・`test_c27`・`test_contract` である。上の 5 本は r2db の adapter の bootstrap (migration 一覧) と `audit_query` の両方を通る。**残りを回す必要があると判断したら、回す前に報告する。**

### 2.7 記録 (統合時に監督が埋める)

WP-1〜WP-3 は 2 つのコミット `bb0caa3` (WP-1〜WP-3 の本体) と `b10f4a0` (統合時に赤になった件数 pin の更新) で統合した (main `623d47c`、2026-09-20)。実施の記録・完了条件 → 変異 → 赤になった test id の対応表・完了ゲートの集計行は §5.1 以下に在る。

## 3. WP-2 — F-17 を両 peer に、と両 runbook

### 3.1 目的と範囲

設計 §4 の **D-4** を現物にする。`platform_declarations` に F-17 の検査を足し、`ops verify-declarations` から**だけ**呼ぶ。同じ枝を**両 peer**に置く (同型 pin。設計 §4 D-4)。`_ISOMORPHIC_TARGETS` に `_f17_message` (と F-17 が足す定数) を**行として足し**、件数 pin を実測で更新する。runbook に順序と開示を書く。**migration は 1 本も触らない。**

### 3.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/platform_declarations.py`・`ops.py`、`MitateDB-api/src/mitatedb_api/platform_declarations.py`・`ops.py`、両 peer の `tests/test_ops_verify_declarations.py`、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` と件数 pin)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` | §1.2 の共通。両 peer の `migrations/`、`r2db-api/src/r2db_api/main.py`・`control_main.py` (**起動時検査にしない**。設計 §8 の X-2)、`credential_store.py`・`postgres.py`、`security/`、配備 script (WP-1) |

- **F-17 の判定 (設計 §4 D-4)**: **(i)** 実際の GRANT で auditreader と同定できた役の `setdatabase = 0` の `statement_timeout` を `ms_from_pg_timeout_text` で解釈して**正の値**であること (0・負・解釈不能は赤)。宣言が無いのも赤。**(ii)** その役に `statement_timeout` に言及する per-database 行 (`ALTER ROLE … IN DATABASE … SET`) が**無い**こと (在れば赤)。読みは既存の `_role_setting_rows` を使う。**同定できる役が 0 件なら緑** (F-16 と同じ作法)。
- **終了コードは 16** (次の未使用)。`_VERIFY_DECLARATIONS_EXIT_CODES` に `"F-17": 16` を足す (両 peer で逐語に同じ)。
- **reader の DSN で接続しない。** `verify-declarations` は control DSN 1 本の読み取り専用という性格を保つ (設計 §4 D-4)。
- **出力に値も ms も raw の文字列も出さない** (`OK`/`FAIL` の既存の形を崩さない)。
- **runbook に書くこと**: (a) 「`0014` の適用 → reader の pool を持つ process (control) の再起動 → `ops verify-declarations` で F-17 を読む」の順序、(b) `verify-declarations` を実行する役の明記、(c) **本番は `0014` を適用するまで `FAIL F-17` / 終了コード 16 になること、それが意図した信号であること** (設計 §7 の中 4)、(d) ADMIN OPTION の前提と満たされないときの直し方。

### 3.3 完了条件

| # | 完了条件 |
|---|---|
| W2-1 | **両 peer**で、宣言が正の値なら `OK F-17` と終了コード 0、値を `0` にすると `FAIL F-17` と終了コード 16、宣言を `RESET` しても `FAIL F-17`。出力に値も ms も raw の文字列も現れない |
| W2-2 | **両 peer**で、`ALTER ROLE <auditreader> IN DATABASE <platform db> SET statement_timeout = 0` を置くと `FAIL F-17` になる (role 単位の宣言は正のまま) |
| W2-3 | **両 peer**で、auditreader の役が無い platform では `OK F-17` と終了コード 0 になる |
| W2-4 | **役の同定が実際の DSN で成立する** (設計 §6 の 4c)。`verify-declarations` が実際に使う DSN の役で走らせて「auditreader は在るが宣言が無い → 赤」が成立する。**同定が 0 件になるなら実装せず実測を報告して止まる** (裁定は監督) |
| W2-5 | 両 peer の `_verify_declarations_checks` が正規化差分で一致したままである。`_ISOMORPHIC_TARGETS` に `_f17_message` (と F-17 が足す定数) の行が足され、件数 pin (**138**) と逐語の期待値が**実測で更新**されている |
| W2-6 | 両 runbook に (a)〜(d) の 4 点が在る。**本番に対して何も実行していない** |
| W2-7 | `python3 tools/check_comment_provenance.py --base 7ad7588` が通る (両 peer の `src/` のコメント・docstring を変えるため) |
| (W2-7 の訂正註) | **【訂正註 2026-09-20 (監督)】** 本行の字義「通る」(終了コード 0) は §5.8 の裁定 A-1 が訂正する。読みは「`tools/check_comment_provenance.py` §4.1 の (2)〜(5) が 0 件。機能コードの追加で必ず出る (1) は対象外」である (本文は書き換えない。§1.8 の 57)。道具が `src/` の新しい関数に docstring を付けられなくしている件は台帳 R-63 |
| W2-8 | 触ったファイルに実値が無い。`python3 tools/public_value_scan.py <触ったファイル>` の集計行を報告に貼る |
| W2-9 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) |

### 3.4 完了条件 → 変異

変異は **peer ごとに 1 項目**に分ける。

| # | 変異 (操作) | 期待 |
|---|---|---|
| W2-1 | **M5**: F-17 の検査の `declared_ms <= 0` の枝を外す | 赤 |
| W2-1 | **M6**: `_VERIFY_DECLARATIONS_EXIT_CODES` の `"F-17"` を別の数 (例 17) に変える | 赤 |
| W2-2 | **M7**: per-database 行を見る枝を外す (`setdatabase = 0` の行だけ見る形に戻す) | 赤 |
| W2-3 | **M8**: 同定できない役を赤にする (黙って飛ばす分岐を外す) | 赤 |
| W2-4 | **監査照合**: 使い捨てクラスタでの実測 — 同定できた役の**数** (役名は prefix 置換後の合成値) と、そのときの `verify-declarations` の終了コードを報告に残す |  — |
| W2-5 | **M9**: r2db 側の F-17 の枝だけを消す | 赤 (同型のテスト) |
| W2-5 | **M10**: `_ISOMORPHIC_TARGETS` から `_f17_message` の行を外す | 赤 (件数 pin) |
| W2-6 | **監査照合**: runbook の (a)〜(d) の該当行を `file:line` で報告に残す。本番未実行の根拠も 1 行 | — |
| W2-7 | **監査照合**: `check_comment_provenance.py --base 7ad7588` の出力の最終行 | — |
| W2-8 | **監査照合**: `public_value_scan` の集計行 | — |
| W2-9 | **監査照合**: 本表の行数と対応数 | — |

### 3.5 変異の JSON (雛形)

```json
{
  "pytest": ["-q"],
  "mutations": [
    {"id": "M5-r2db", "file": "r2db-api/src/r2db_api/platform_declarations.py",
     "old": "<declared_ms <= 0 の枝>", "new": "",
     "tests": ["r2db-api/tests/test_ops_verify_declarations.py::<W2-1 のテスト>"], "expect": "red"},
    {"id": "M5-mitate", "file": "MitateDB-api/src/mitatedb_api/platform_declarations.py",
     "old": "<同上>", "new": "",
     "tests": ["MitateDB-api/tests/test_ops_verify_declarations.py::<W2-1 のテスト>"], "expect": "red"},
    {"id": "M6-r2db", "file": "r2db-api/src/r2db_api/ops.py",
     "old": "\"F-17\": 16,", "new": "\"F-17\": 17,",
     "tests": ["r2db-api/tests/test_ops_verify_declarations.py::<終了コードのテスト>"], "expect": "red"},
    {"id": "M7-r2db", "file": "r2db-api/src/r2db_api/platform_declarations.py",
     "old": "<per-database 行を見る枝>", "new": "",
     "tests": ["r2db-api/tests/test_ops_verify_declarations.py::<W2-2 のテスト>"], "expect": "red"},
    {"id": "M8-r2db", "file": "r2db-api/src/r2db_api/platform_declarations.py",
     "old": "<同定できない役を飛ばす分岐>", "new": "<赤にする形>",
     "tests": ["r2db-api/tests/test_ops_verify_declarations.py::<W2-3 のテスト>"], "expect": "red"},
    {"id": "M9", "file": "r2db-api/src/r2db_api/ops.py",
     "old": "<F-17 の枝 (r2db 側だけ)>", "new": "",
     "tests": ["r2db-api/tests/test_audit_query.py::<同型のテスト>"], "expect": "red"},
    {"id": "M10", "file": "r2db-api/tests/test_audit_query.py",
     "old": "<_f17_message の登録行>", "new": "",
     "tests": ["r2db-api/tests/test_audit_query.py::<件数 pin のテスト>"], "expect": "red"}
  ]
}
```

### 3.6 実行するコマンド

```bash
# peer ごとに別々に
tools/dev/pt.py -C .claude/worktrees/r56-impl -- r2db-api/tests/test_ops_verify_declarations.py r2db-api/tests/test_audit_query.py -q
tools/dev/pt.py -C .claude/worktrees/r56-impl -- MitateDB-api/tests/test_ops_verify_declarations.py MitateDB-api/tests/test_audit_query.py -q
# コメント出所 (src/ を触るため)
python3 tools/check_comment_provenance.py --base 7ad7588
# tools 側 (conformance と結合しない)
tools/dev/pt.py -C .claude/worktrees/r56-impl -- tools/tests -q
# 変異
tools/dev/mutate.py "$SP/r56-wp2-mutations.json" -C .claude/worktrees/r56-impl
```

- **conformance は WP-2 では回さない** (`src/` の変更は `verify-declarations` の経路だけで、adapter の bootstrap は WP-1 で済んでいる)。回す必要があると判断したら、回す前に報告する。

### 3.7 記録 (統合時に監督が埋める)

WP-1〜WP-3 は 2 つのコミット `bb0caa3` (WP-1〜WP-3 の本体) と `b10f4a0` (統合時に赤になった件数 pin の更新) で統合した (main `623d47c`、2026-09-20)。実施の記録・完了条件 → 変異 → 赤になった test id の対応表・完了ゲートの集計行は §5.1 以下に在る。

## 4. WP-3 — `security/CONTROL_MAPPING.md` 版 2.12

### 4.1 目的と範囲

設計 §7 を現物にする。**SI-08 / r2db-api** の既定の小ブロックに統制 1 本と証拠 1 本を足し、版を **2.11 → 2.12** にする。**WP-1・WP-2 の実測が出た後に書く** (§1.5 の 34: 主張は実測の後)。

### 4.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `security/CONTROL_MAPPING.md` | §1.2 の共通。`security/CONTROL_MAPPING_HISTORY.md` (既存の文を**移さない**。本件は追加のみ)、`tools/control_mapping_axes.tsv` (同じ (SI, peer) の中で bullet を並べ替えないので不変)、`src/`・`tests/`・`migrations/`・runbook (WP-1/WP-2) |

### 4.3 完了条件

| # | 完了条件 |
|---|---|
| W3-1 | **SI-08 / r2db-api** の Control に統制 1 本、Evidence にテスト名 1 本を足した。置き場は**既定の小ブロック** (名前付きブロックを新設しない) |
| W3-2 | 統制文が設計 §7 の限定を持つ: 「**適用後に開かれる**接続にだけ効く / 適用後に reader の pool を持つ process を再起動する必要がある」「F-17 は**宣言の検査**であって稼働中の process の実効値の検査ではない」 |
| W3-3 | peer 間の差を開示している: 「MitateDB-api は application role にも role 水準の `statement_timeout` を置くが、**r2db-api は application role に role 水準の timeout を置かず、取引ごとの `SET LOCAL` に依る。`PostgresCell.catalog` の 1 経路はそれを通らない (台帳項目)**」 |
| W3-4 | Status に (a) 本番の証拠が `absent` であること、(b) **本番は `0014` を適用するまで `FAIL F-17` になり、それが意図した信号であること** が在る |
| W3-5 | 版行が **2.12** で、変更内容を 1 文で書いている |
| W3-6 | **足した後のブロックの字数と残りを報告する** (基点は主張 24 本・8,914 字、上限 15,200、残り 6,286)。**残りが 2,000 未満なら報告して止まる** (分割の要否は監督の裁定) |
| W3-7 | `conformance-tests/test_control_mapping_register.py` と `tools/tests` が緑 |
| W3-8 | `python3 tools/public_value_scan.py security/CONTROL_MAPPING.md` の集計行を報告に貼る |
| W3-9 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) |

### 4.4 完了条件 → 変異

| # | 変異 (操作) | 期待 |
|---|---|---|
| W3-1 | **M11**: 足した Evidence のテスト名を実在しない名前に変える | 赤 (register の照合) |
| W3-2 | **監査照合**: 該当の 1 文を逐語で報告に残す | — |
| W3-3 | **監査照合**: 同上 | — |
| W3-4 | **監査照合**: Status の 2 行を逐語で報告に残す | — |
| W3-5 | **M12**: 版行を 2.11 のままにする | 赤 (版の照合が在る場合。無ければ監査照合に落とし、その実測を報告する) |
| W3-6 | **監査照合**: 字数と残りの実測値 | — |
| W3-7 | **監査照合**: `pt.py` の集計行 | — |
| W3-8 | **監査照合**: `public_value_scan` の集計行 | — |
| W3-9 | **監査照合**: 本表の行数と対応数 | — |

### 4.5 実行するコマンド

```bash
tools/dev/pt.py -C .claude/worktrees/r56-wp3 -- conformance-tests/test_control_mapping_register.py -q
tools/dev/pt.py -C .claude/worktrees/r56-wp3 -- tools/tests -q
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py security/CONTROL_MAPPING.md
tools/dev/mutate.py "$SP/r56-wp3-mutations.json" -C .claude/worktrees/r56-wp3
```

### 4.6 記録 (統合時に監督が埋める)

WP-1〜WP-3 は 2 つのコミット `bb0caa3` (WP-1〜WP-3 の本体) と `b10f4a0` (統合時に赤になった件数 pin の更新) で統合した (main `623d47c`、2026-09-20)。実施の記録・完了条件 → 変異 → 赤になった test id の対応表・完了ゲートの集計行は §5.1 以下に在る。

## 5. 受け入れ監査と監督裁定

本節は受け入れ監査パケットの写し (§5.1〜§5.7) と、それに対する監督裁定 (§5.8)・最終判定 (§5.9) である。監査は `evidence-auditor` 1 回、統合後の木 (作業コミット `bb0caa3`・`b10f4a0`、main `623d47c`) に対する**読み取りのみ**で、判定は 充足 / 未充足 / 証拠不足 の 3 値であり裁定は含まない。以下で「設計 §n」と書くのは設計メモ `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` v1.0 の節であり、同メモのローカルの族 (D-N・X-N) は同メモのもので、台帳 `RM` §8 の R-N とは別である (§1.8 の 59)。**変異 id は WP を跨ぐと一意でない** — WP-2 と WP-3 に同名の `M11`・`M12` が在るので、参照するときは WP を添える (§5.8 の A-4)。

対象: `docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md` v1.0 の WP-1・WP-2・WP-3。
準拠設計: `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` v1.0。変更クラス **D**。
監査は読み取り専用。`gate.py` / `finalize.py` / suite 全体の pytest は実行していない (§1.3 の 19、§1.6 の 43)。監査が自分で再測したのは静的な道具 (`check_comment_provenance.py`・`public_value_scan.py`・`check_control_mapping_split.py`・`check_doc_refs.py`・登録テストの `_subblock_block_text` の直接呼び出し・grep) のみである。

### 5.1 実施記録

- **統合**: 作業コミット `bb0caa3` (WP-1〜WP-3)、`b10f4a0` (統合時に赤になった件数 pin の更新)、main `623d47c` (merge)。基点 main `6b5213b`。差分 `git diff 6b5213b..b10f4a0` = **23 ファイル、1,004 挿入 / 51 削除**。`b10f4a0` の木と `623d47c` の木は同一 (監査が `git diff` で確認、差分 0)。
  - migration: `r2db-api/migrations/0014_auditreader_statement_timeout.sql` (新規 +57)。
  - 製品コード: 両 peer の `src/**/platform_declarations.py` (各 +47)、`src/**/ops.py` (各 +7)。
  - テスト: `r2db-api/tests/test_auditreader_statement_timeout.py` (新規 +287)、両 peer の `tests/test_ops_verify_declarations.py` (+189 / +180)、両 peer の `tests/test_audit_query.py` (+29 / +24)、`r2db-api/tests/` の追随 5 ファイル、`r2db-api/tests/test_platform_upgrade_ledger_scan.py`、`tools/tests/test_no_shared_cluster_defaults.py`。
  - conformance adapter: `r2db-api/conformance/conformance_adapter_r2db_http.py`・`real_server_r2db.py`。
  - 配備: `r2db-api/deploy/scripts/part1_provision_host_and_db.sh` (+28/-14)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (+59)。
  - 主張: `security/CONTROL_MAPPING.md` (+18/-3、版 2.11 → 2.12)。`security/CONTROL_MAPPING_HISTORY.md` は差分 0 (追加のみ、移動なし)。
- **WP の切り方**: WP-1 → WP-2 を同一実装担当が直列、WP-3 はその後 (§1.3)。`MitateDB-api/migrations/` は差分 0 (設計 D-4 のとおり、MitateDB に migration を足していない)。§1.2 の明示の例外 (`MitateDB-api/tests/test_ops_verify_declarations.py` の位置 slice の直し) は報告に明記されている。
- **変更クラス**: 宣言どおり **D**。`_ISOMORPHIC_TARGETS` は 138 → **140** 行 (監督裁定どおり。`_f17_message` と `check_auditreader_statement_timeout` の 2 行)。
- **依頼者確定の逐語記録**: 設計 §9.1 に依頼者委任の 1 文が逐語で在り (「その方針で進めてください、…」)、D-1〜D-4 は「この委任の下で監督が推奨として下した」と明記されている。この確定文言を写した箇所は差分内に無い (写しが無いので言い換えの危険も無い)。
- **道具 (実装報告が引いた集計行、verbatim)**:
  - WP-1: `pt: 130 passed in 35.74s` / `pt: 305 passed in 22.67s` / `pt: 95 passed in 31.08s` / `pt: 258 passed in 226.12s (0:03:46)` (conformance c05/c09/c11/c19/c25) / `pt: 528 passed in 35.77s` (tools/tests)。
  - WP-2: `pt: 112 passed in 35.11s` / `pt: 101 passed in 30.99s` / `pt: 528 passed in 34.01s`。差し戻し後の再実行: `pt: 112 passed in 35.25s` / `pt: 101 passed in 30.78s` / `pt: 3 passed in 0.71s` / `pt: 305 passed in 22.67s`。
  - WP-3 (最終状態): `pt: 34 passed in 0.23s` (`conformance-tests/test_control_mapping_register.py`) / `pt: 528 passed in 31.99s` (tools/tests、別呼び出し)。
  - `# mode=tree files_scanned=14 total_flagged=0` (WP-1)、`… files_scanned=10 …` (WP-2)、`… files_scanned=1 …` (WP-3)。**監査の独立再測**: 差分 23 ファイル全部に対して `# mode=tree files_scanned=23 total_flagged=0`。
  - `missing=0 added=7 moved=0 empty_axis_added=0 empty_axis_removed=1 subsequence=ok preamble=differs ccr14=identical rule=identical` (`tools/check_control_mapping_split.py --base 6b5213b`、exit 0。**監査が再実行して同一**)。
  - `check_doc_refs OK: 0 dangling references` (`tracked markdown files scanned: 145`、**`empty markdown files: 0`** — §2 の 15 の 0 バイト化なし。監査が再実行)。
  - 統合時: 1 回目 `finalize: tools/tests: 1 failed, 527 passed`、pin 更新後 `finalize: tools/tests: 528 passed`。
- **公開リポジトリ規律 (§1.9) の独立確認**: 差分の追加行に作業機の絶対パス・一時領域の名前・`pytest-of-…`・`dsa-testpg-…`・`{scratchpad}` 参照は **0 件**。接続先は環境変数名のみ (`R2DB_TEST_ADMIN_DSN`・`R2DBSVC_CONTROL_DSN`・`R2DB_CONTROL_DSN`・`R2DB_AUDIT_DSN`・`MITATEDB_PROVISION_DSN`)。実 DSN・実ホスト名・traceback は無い。

### 5.2 完了条件の判定表

#### 5.2.1 WP-1 (migration `0014` と実 PostgreSQL のテスト)

| # | 判定 | 証拠 |
|---|---|---|
| W1-1 | **充足** | `r2db-api/tests/test_auditreader_statement_timeout.py`:169 `test_reader_connection_effective_statement_timeout_is_5000ms_after_0014`。`SELECT setting FROM pg_settings WHERE name = 'statement_timeout'` を **reader の DSN で新しく開いた**接続で読み `== "5000"` (`SHOW`/`current_setting` を使っていないことを監査が本文で確認)。変異 **M1** が赤 (`'0' == '5000'`) |
| W1-2 | **充足** | 同 :232 `test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection`。**設計 §6 条件 2 の確定文言どおり** role 水準の `ALTER ROLE … SET statement_timeout = '200ms'` を `platform.control_dsn` で発行 → `PostgresAuditQueryStore` を**その後に**構築 → `_AUDIT_QUERY_UNION_SQL` を `SELECT pg_sleep(2)` に monkeypatch (ロック待ちに依らない) → `elapsed < 8.0`・`code == "SERVICE_UNAVAILABLE"`・`status == 503`・`problem()` に DSN/role/`SELECT`/`canceling statement` が無いこと → 同じ store の次の問い合わせが通る → `finally` で `pg_roles.rolconfig` から読んだ元値へ復元。変異 **M2** が赤 (`QueryCanceled` が未捕捉で伝播、1.10s で終了 = 無限待ちなし) |
| W1-3 | **充足** | 同 :186 `test_0014_reapplication_is_idempotent`。変異 **M3** が赤 |
| W1-4 | **充足 (監査照合 + 独立再測)** | `r2db-api/tests/test_ops_verify_declarations.py`:72,76 と `MitateDB-api/tests/test_ops_verify_declarations.py`:84,87 が `_MIGRATION_NAMES_DECLARATIONS_ONLY` + 内包表記の名前選択。**監査の再測**: `MIGRATION_NAMES[` の全出現は 6 件、いずれも `# ` で始まる経緯コメント中の文字列 (r2db :68・:2695・:2702、Mitate :80・:2469・:2476)。実コードの位置 slice は **0 件** |
| W1-5 | **充足** | `r2db-api/tests/test_platform_upgrade_ledger_scan.py`:658 `{"適合": 3, "違反": 0, "免除": 0, "対象外": 11}`、:683 タプルに `"0014_auditreader_statement_timeout.sql"`。変異 **M4-verify** が赤 (`KeyError`)。**監査の再測**: `0007_application_audit.sql` を列挙する r2db の `.py`/`.sh` のうち `0014` を持たないのは `src/` の 3 ファイル (`credential_store.py`・`platform_declarations.py`・`main.py`) だけで、いずれも散文 (migration 一覧ではない) |
| W1-6 | **充足 (監査照合)** | `r2db-api/deploy/scripts/part1_provision_host_and_db.sh`:357 (`log`) / :360 (`psql -v ON_ERROR_STOP=1 -f`)、適用順ヘッダ :279・:283。`0013_role_connection_limits.sql` の grep は **0 件**、`0013` の文字列は :293・:295 の「足さない理由」の説明コメントのみ |
| W1-7 | **充足 (監査照合)** | `# mode=tree files_scanned=14 total_flagged=0`。監査の独立再測 (23 ファイル) も `total_flagged=0` |
| W1-8 | **充足 (監査照合)** | `r2db-api/tests/test_auditreader_statement_timeout.py`:34 `ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"`、:49 `os.environ.get(ADMIN_DSN_ENV)` (未設定なら skip ではなく失敗)。実 DSN・実ホスト名は無い。**本番未実行**は設計 §7 の Status 主張と runbook の記述で担保されており、差分に本番へ向けた実行の痕跡は無い |
| W1-9 | **充足** | 本表 9 行すべてに変異 (M1・M2・M3・M4-verify) または監査照合が在る。対応の無い行は 0 |

#### 5.2.2 WP-2 (F-17 を両 peer に、と両 runbook)

| # | 判定 | 証拠 |
|---|---|---|
| W2-1 | **充足 (残り 1 点あり)** | 両 peer の `tests/test_ops_verify_declarations.py` に `test_verify_declarations_f17_passes_after_migration_0014` (Mitate は `…_passes_from_migration_0013`)・`…_fails_when_declared_timeout_is_zero`・`…_fails_when_declared_timeout_is_reset`。`…_is_zero` は両 peer とも `assert rc == 16` / `FAIL F-17` / `"5000" not in f17_line` / `" ms" not in f17_line` を持つ (監査が本文で確認)。変異 **M5-r2db**・**M5-mitate**・**M6-r2db** が赤。**残り**: 終了コード定数だけを壊す変異は r2db 側の `M6-r2db` のみで、`MitateDB-api/src/mitatedb_api/ops.py`:1287 の `"F-17": 16` を単独で壊す `M6-mitate` は実行されていない (指示書 §3.5 の雛形も `M6-r2db` だけを挙げている) |
| W2-2 | **充足** | 両 peer の `…_fails_when_a_per_database_override_exists`。変異 **M7-r2db**・**M7-mitate** が赤 |
| W2-3 | **充足 (指示書の変異を差し替え)** | 両 peer の `test_verify_declarations_f17_passes_when_auditreader_role_is_absent`。**差し戻し 1 で `dsn=platform.api_dsn` → `platform.control_dsn` / `platform.provision_dsn` (本番と同じ DSN) に直され**、空振りが解消した。変異 **M11-r2db**・**M11-mitate** (`DROP OWNED BY`+`DROP ROLE` の塊 → `ALTER ROLE … RESET statement_timeout`) が両 peer で赤 = 非空振り。**指示書 §3.4 の M8 (「同定できない役を赤にする」) は owner 除外の変異に差し替えられており**、その旨は実装報告の「指示外の判断 2」に明記されている。差し替え先の **M8-r2db**・**M8-mitate** は `test_f17_the_schema_owning_role_is_never_flagged_despite_an_explicit_select_grant` を赤にする |
| W2-4 | **充足 (監査照合)** | 実装報告 §W2-4: 宣言正値 = 同定 **1 件**・`OK F-17`・終了コード 0 / 宣言 0・RESET・per-database 上書き = 同定 1 件・`FAIL F-17`・終了コード 16 / `DROP ROLE` 後 = 同定 **0 件**・`OK F-17`・終了コード 0。役名は記録されておらず実値の混入は無い。同定 0 件で止まる事態は起きていない |
| W2-5 | **充足** | `_verify_declarations_checks` の同型は `r2db-api/tests/test_audit_query.py::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` が固定し、変異 **M9** (r2db 側の F-17 呼び出しだけを削除) が赤。`_ISOMORPHIC_TARGETS` は両 peer で `_f17_message` と `check_auditreader_statement_timeout` の **2 行**が足され (r2db :2913-2914 / Mitate :2687-2688)、件数 pin は **140** (`test_isomorphic_target_table_is_pinned_to_its_current_140_rows`、両 peer)。変異 **M12** が赤。監督裁定 (138 → 140) と一致 |
| W2-6 | **充足 (監査照合、監査が現物で再確認)** | `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` 新設 §19: (a) :1955「**Order of operations, in this exact sequence:**」の 1.〜3. (`0014` 適用 → `r2dbsvc-control.service` 再起動 → `verify-declarations` で `F-17` を読む)、(b) :1944「**Run once, after `0007`, as the role that created `r2dbsvc_auditreader`**」と 3. の `R2DB_CONTROL_DSN`、(c) :1965 付近「**On an existing deployment, `ops verify-declarations` reports `FAIL F-17` (exit code 16) until `0014` has been applied.** This is the intended signal, not a regression:…」、(d) :1982「**ADMIN OPTION precondition.**」の段。加えて「F-17 は宣言の検査であって稼働中 process の実効値の検査ではない」旨の段も在る。`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`:66-70 も同旨。本番への適用の痕跡は差分に無い |
| W2-7 | **読み替え後は充足 / 字義では未充足** | 監査の独立再実行: `check_comment_provenance.py --base 7ad7588 <src 4 本>` は **exit=1**、出力は `FAIL (§4.1 (1))` の **4 行のみ** (r2db `platform_declarations.py`:1126・`ops.py`:1013、Mitate `platform_declarations.py`:1100・`ops.py`:1287)。**§4.1 の (2)〜(5) は 0 件** (監査が grep で計数)。監督の読み替え (「(2)〜(5) が 0 件。(1) は機能コードの追加で必ず出るので対象外」) を満たす。字義の「exit 0 で通る」は満たしていない |
| W2-8 | **充足 (監査照合)** | `# mode=tree files_scanned=10 total_flagged=0`。監査の独立再測 (23 ファイル) も 0 |
| W2-9 | **充足** | 本表 9 行すべてに変異 (M5・M6・M7・M8・M9・M11・M12) または監査照合が在る。対応の無い行は 0 |

#### 5.2.3 WP-3 (`security/CONTROL_MAPPING.md` 版 2.12)

| # | 判定 | 証拠 |
|---|---|---|
| W3-1 | **充足** | SI-08 / r2db-api / **既定の小ブロック**に Control 3 bullet (`;` で連なる 1 統制。:576-578)、Evidence 1 bullet (:582、旧 `- —` を置換)、Status 2 bullet (:587-588)。SI-08 / MitateDB-api / 既定にも Control 1 bullet (:610)。名前付きブロックの新設なし (`check_control_mapping_split.py` が `moved=0 subsequence=ok`)。変異 **M11b** (足した Evidence bullet を丸ごと外す) が赤 — `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` (`SI-08/r2db-api/None/Evidence: no content lines at all`) |
| W3-2 | **充足 (監査照合、逐語)** | (前半) :576「…but a role setting is copied into a session at login, so it reaches connections OPENED AFTER the file is applied: a connection `_RolePool` (`r2db-api/src/r2db_api/postgres.py`) is already holding keeps the value it logged in with, and the control process is restarted once `0014` has been applied (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` section 19 carries that order -- apply, restart the control process, then `ops verify-declarations`);」 (後半) :577「**F-17 judges the DECLARATION, not the effective value inside a running process**, which is what the Evidence tests below read on a reader connection opened for that purpose;」 |
| W3-3 | **充足 (監査照合、逐語)** | :578「**disclosed difference between the peers**: MitateDB-api's `0013_role_statement_timeouts.sql` puts a role-level `statement_timeout` on its application runtime/developer roles as well, while r2db-api leaves those two roles without a role-level timeout and relies on the per-transaction `SET LOCAL` `_set_timeouts` issues (`r2db-api/src/r2db_api/postgres.py:2282-2297`); `PostgresCell.catalog` (`:803-807`) opens its transaction without that call, so that one path carries no statement bound of its own -- an open ledger item (R-56, design section 10), not a closed gap.」 |
| W3-4 | **充足 (監査照合、逐語)** | (a) :587「**Production evidence for `0014` is `absent`** (R-56): the measurements recorded above were taken on throwaway PostgreSQL clusters started by the test suite, and the VPS deployment was left as it stands, with `0014` unapplied.」 (b) :588「On that deployment `ops verify-declarations` answers `FAIL F-17` (exit code 16) while `0014` is unapplied, and **that is the intended signal, not a regression**: …」 |
| W3-5 | **充足 (監査照合)** | :5 が `Version: **2.12** (2026-09-20; R-56 -- SI-08 gains one control and its evidence on the r2db-api side (…) … Additive: no existing claim is rewritten and nothing moves into `CONTROL_MAPPING_HISTORY.md` -- docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md)`。変異 **M12-version-line-left-at-2-11** は **緑** = 版数を見る自動検査はこの repository に無い (指示書 §4.4 の但し書きに従い監査照合へ落ちている。その実測が報告に在る) |
| W3-6 | **充足 (監査が独立に再測、完全一致)** | 監査が `conformance-tests/test_control_mapping_register.py` の `_subblock_block_text` / `MAX_BLOCK_LENGTH = 15200` を直接呼んで最終木を再測: SI-08 / r2db-api / 既定 = **12,928 (残り 2,272)**、SI-08 / MitateDB-api / 既定 = **13,023 (残り 2,177)**、SI-08 / MitateDB-api / `ops inventory` = 8,349 (残り 6,851)、SI-08 / Common / 既定 = 2,257。実装報告の数値と **1 字も違わない**。残りはどちらも 2,000 以上なので「止まる」条件には掛からない。最長の物理行は :571 の 1,384 字 (既存行、上限 1,400)。**SI-08 / MitateDB-api / 既定 (13,023) がファイル最長ブロック**になり、SI-14 / r2db-api / 既定 (12,624) を上回った |
| W3-7 | **充足** | `pt: 34 passed in 0.23s` (`conformance-tests/test_control_mapping_register.py`) / `pt: 528 passed in 31.99s` (`tools/tests`、conformance とは別呼び出し) |
| W3-8 | **充足 (監査照合)** | `# mode=tree files_scanned=1 total_flagged=0` |
| W3-9 | **充足** | 本表 9 行すべてに変異 (M11b・M11・M12) または監査照合が在る。対応の無い行は 0 |

#### 5.2.4 「完了条件番号 → 変異」対応表の欠落検査 (§1.5 の 40)

- WP-1 の 9 行・WP-2 の 9 行・WP-3 の 9 行 = **27 行すべて**に変異または監査照合が対応している。対応の無い行は **0 件**。
- 変異を持たない行 (W1-4・W1-6・W1-7・W1-8・W1-9・W2-4・W2-6・W2-7・W2-8・W2-9・W3-2・W3-3・W3-4・W3-6・W3-7・W3-8・W3-9) はすべて「監査照合」と明示され、逐語記録または道具の集計行が実装報告に在る。
- **変異 anchor の最終木への追随 (監査の独立確認)**: 各変異 spec の `old` 文字列が最終木 (`b10f4a0`) に何件在るかを数えた結果、**M10 を除く全変異で 1 件ちょうど**であり、対象 test id も現存する。すなわち M1〜M9・M11・M11b・M12 の赤の実測は最終木にそのまま当たる。**M10 のみ 0 件** (`test_isomorphic_target_table_is_pinned_to_its_current_139_rows` が `…_140_rows` へ改名されたため陳腐化)。その役目は **M12** が引き継いでいる。

### 5.3 完了ゲートの集計行

監督がリポジトリルートで単独実行 (コミット前の同じ木)。**verbatim**:

```
gate: 3763 passed, 2 subtests passed in 313.11s (0:05:13)
gate: judge=PASS
gate: pg_database/pg_roles diff 0
```
log = `gate-r56-<日時>.log` (ログ本体の末尾も `3763 passed, 2 subtests passed in 313.11s (0:05:13)` と `== gate: pg_database / pg_roles diff (names sorted) ==` に続く `0`)。

- **合格条件 (§1.3 の 22・26) に対する判定: 充足。** 集計行に `failed` / `skipped` / `xfailed` / `xpassed` / `deselected` はいずれも現れない (= すべて 0)。`2 subtests passed` は passed 側の内訳であり、§1.3 の 22 の禁止項目ではない。
- **§1.3 の 23: 充足。** `pg_database` / `pg_roles` の差分 0 (`gate.py` が併せて見る。§2 の 12)。
- **件数の整合: 一致。** 直前の main が 3748。差分の `+def test_` は 18、`-def test_` は 3 (件数 pin テスト 3 本の改名 — 両 peer の `…_139_rows` → `…_140_rows`、`…_pinned_to_26_files` → `…_27_files`)。差し引き **+15**、3748 + 15 = **3763**。
- **ゲートを走らせた木と最終木の差 (監督が名指しした扱いの材料)**: gate は件数 pin の更新 (`b10f4a0`) **より前**の木で走っている。監査が `git diff bb0caa3..b10f4a0` を取った結果、両者の差は **`tools/tests/test_no_shared_cluster_defaults.py` の 1 ファイル・4 挿入 4 削除のみ** (定数 `26` → `27` と、それを指す docstring・テスト名の 2 箇所) であり、他の 22 ファイルは **byte 同一**である。
  - gate が緑だった理由: 当該テストは `git ls-files` で列挙するため、新規ファイル `r2db-api/tests/test_auditreader_statement_timeout.py` が**未追跡である間は数に入らない**。commit `bb0caa3` で追跡された瞬間に 27 になり赤化した (`finalize: tools/tests: 1 failed, 527 passed`)。これは §2 の「新規ファイルを足すと件数 pin が赤くなる」既知の性質 (`RM` の「Scan enumeration method」と同じ) で、実装担当・gate のどちらの手落ちでもない。
  - 最終木に対する再測: `finalize: tools/tests: 528 passed` が当該ファイルを含む `tools/tests` 全体を覆っている。
  - **判定**: 集計行 `3763 passed` は最終木のテスト本数と一致し、gate の木と最終木の差は `tools/tests` の 1 ファイルに閉じており、その 1 ファイルは finalize が緑で再測している。したがって「最終木で完全な gate を回した実測」は**無い**が、**未測の残余は `tools/tests` の 1 ファイルのみ**であり、それは別途緑が測られている。最終木で gate を再実行するかどうかは監督の裁定事項。

### 5.4 変異表

#### 5.4.1 WP-1 の 4 件 (初回。`mutate.py` の出力 verbatim)

```
M1       expect=red   got=red       OK  | 1 failed in 0.22s | restore=ok
M2       expect=red   got=red       OK  | 1 failed in 0.46s | restore=ok
M3       expect=red   got=red       OK  | 1 failed in 0.91s | restore=ok
M4-verify expect=red   got=red       OK  | 1 error in 0.23s | restore=ok
mutate: 4 mutations, 4 as expected, restores verified 3/3 files (sha256 x2), grep counts unchanged (n/a for 2 edits whose lines all exist in the pristine file)
```

#### 5.4.2 WP-2 の 9 件 (初回。verbatim)

```
M5-r2db  expect=red   got=red       OK  | 1 failed in 0.27s
M5-mitate expect=red   got=red       OK  | 1 failed in 0.25s
M6-r2db  expect=red   got=red       OK  | 1 failed in 0.28s
M7-r2db  expect=red   got=red       OK  | 1 failed in 0.27s
M7-mitate expect=red   got=red       OK  | 1 failed in 0.26s
M8-r2db  expect=red   got=red       OK  | 1 failed in 0.28s
M8-mitate expect=red   got=red       OK  | 1 failed in 0.25s
M9       expect=red   got=red       OK  | 1 failed in 2.11s
M10      expect=red   got=red       OK  | 1 failed in 0.14s
mutate: 9 mutations, 9 as expected, restores verified 4/4 files (sha256 x2)
```

#### 5.4.3 レビュー担当の自作変異 (verbatim)

```
V1-vacuity expect=red   got=green     NG  | 1 passed in 0.31s | restore=ok
mutate: 1 mutations, 0 as expected, restores verified 1/1 files (sha256 x2)
```

`NG` は**当時の実装の空振りを暴いた実測**であり、差し戻し 1 で直されている。直した後の同じ操作が **M11-r2db / M11-mitate** として赤になった (§5.4.4)。

#### 5.4.4 差し戻し後の再実行 (実装報告の記録。`mutate.py` のログで監査が裏を取った)

- `M11-r2db expect=red got=red OK` — 赤: `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_when_auditreader_role_is_absent` (`1 failed in 0.29s`、`:1009 AssertionError`)
- `M11-mitate expect=red got=red OK` — 赤: `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_when_auditreader_role_is_absent` (`1 failed in 0.30s`、`:1037 AssertionError`)
- `M12 expect=red got=red OK` — 赤: `r2db-api/tests/test_audit_query.py::test_isomorphic_target_table_is_pinned_to_its_current_140_rows` (`1 failed in 0.20s`)
- `M1 expect=red got=red OK` (`1 failed in 0.95s`) / `M2 expect=red got=red OK` (`1 failed in 1.10s`) — W1-2 の書き直し後の再確認。どちらも 1 秒台で終了しており、**無限待ちにならない**ことが実測されている

#### 5.4.5 WP-3 の 3 件 (最終状態。verbatim)

```
M11b-evidence-bullet-removed expect=red   got=red       OK  | 1 failed, 9 passed in 0.23s | restore=ok
M11-evidence-test-name-does-not-exist expect=green got=green     OK  | 34 passed in 0.24s | restore=ok
M12-version-line-left-at-2-11 expect=green got=green     OK  | 34 passed in 0.23s | restore=ok
mutate: 3 mutations, 3 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged (n/a for 1 edits whose lines all exist in the pristine file)
```

#### 5.4.6 完了条件番号 → 変異 id → 赤になった test id (実装報告からの写し)

| # | 変異 id | 赤になった test id |
|---|---|---|
| W1-1 | M1 (`0014` の `ALTER ROLE … SET` の行を外す) | `r2db-api/tests/test_auditreader_statement_timeout.py::test_reader_connection_effective_statement_timeout_is_5000ms_after_0014` |
| W1-2 | M2 (`credential_store.py` の `except psycopg.Error:` → `except OSError:`) | `r2db-api/tests/test_auditreader_statement_timeout.py::test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection` |
| W1-3 | M3 (`SET statement_timeout = '5000ms'` → `RESET statement_timeout`) | `r2db-api/tests/test_auditreader_statement_timeout.py::test_0014_reapplication_is_idempotent` |
| W1-4 | 監査照合 | — |
| W1-5 | M4-verify (`MIGRATION_NAMES` から `0014` の行を落とす) | `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_exits_0_when_every_check_passes` |
| W1-6〜W1-9 | 監査照合 | — |
| W2-1 | M5-r2db / M5-mitate (`declared_ms <= 0` の枝を `pass` に) | 両 peer の `tests/test_ops_verify_declarations.py::test_verify_declarations_f17_fails_when_declared_timeout_is_zero` |
| W2-1 | M6-r2db (`"F-17": 16` → `17`) | `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_fails_when_declared_timeout_is_zero` (`rc == 17` で `assert rc == 16` が失敗) |
| W2-2 | M7-r2db / M7-mitate (per-database の枝を `pass` に) | 両 peer の `::test_verify_declarations_f17_fails_when_a_per_database_override_exists` |
| W2-3 | M8-r2db / M8-mitate (owner 除外の `if` を `if False` に。**指示書 M8 の差し替え**) | 両 peer の `::test_f17_the_schema_owning_role_is_never_flagged_despite_an_explicit_select_grant` |
| W2-3 | M11-r2db / M11-mitate (`DROP` の塊 → `ALTER ROLE … RESET`。**差し戻し 1 で追加**) | 両 peer の `::test_verify_declarations_f17_passes_when_auditreader_role_is_absent` |
| W2-4 | 監査照合 | — |
| W2-5 | M9 (r2db 側の F-17 の呼び出しだけを削除) | `r2db-api/tests/test_audit_query.py::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` |
| W2-5 | M12 (`_ISOMORPHIC_TARGETS` の新しい登録行を外す) | `r2db-api/tests/test_audit_query.py::test_isomorphic_target_table_is_pinned_to_its_current_140_rows` |
| W2-5 | ~~M10~~ (139 pin。**陳腐化**、M12 が引き継ぐ) | ~~`::test_isomorphic_target_table_is_pinned_to_its_current_139_rows`~~ |
| W2-6〜W2-9 | 監査照合 | — |
| W3-1 | M11b (足した Evidence bullet を丸ごと外す) | `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` |
| W3-5 | M12-version-line-left-at-2-11 (**緑**。版数の自動検査が無いことの実測) | — |
| W3-1 (参考) | M11-evidence-test-name-does-not-exist (**緑**。テスト名の実在を解決する検査が無いことの実測) | — |
| W3-2・W3-3・W3-4・W3-6・W3-7・W3-8・W3-9 | 監査照合 | — |

### 5.5 レビュー指摘と対応

| # | 指摘 | 対応 | 監査の確認 |
|---|---|---|---|
| 高 1 | W2-3 のテストが空振り (両 peer)。`dsn=platform.api_dsn` では `information_schema.role_table_grants` が 1 行も返さず、同定は役の有無に関係なく 0 件になる。自作変異 `V1-vacuity` が緑 | 両 peer を `platform.control_dsn` / `platform.provision_dsn` に戻し、`_declare_control_role_as_the_writer` / `_declare_provision_role_as_the_writer` を復元。docstring を事実に合わせて書き直し。変異 M11-r2db / M11-mitate を追加 | **確認済み。** 現物 r2db :1012 `rc = _run_verify(monkeypatch, dsn=platform.control_dsn, …)`、Mitate :1040 `dsn=platform.provision_dsn`。docstring も「Connects with the SAME DSN `verify-declarations` uses in production」に直っている。M11 が両 peer で赤 |
| 中 2 | `_ISOMORPHIC_TARGETS` の新行のコメントが偽 (「a real per-peer difference: this peer's own docstring notes…」— 実際には両 peer とも docstring 無し・本体逐語同一) | 監督裁定 (a) を採り、`check_auditreader_statement_timeout` の行を追加。pin 139 → **140**、テスト名を `…_140_rows` に改名。コメントを実測どおりに書き直し | **確認済み。** r2db :2906-2914 / Mitate :2680-2688 の新しいコメントは「`check_auditreader_statement_timeout` carries no docstring and no peer-specific literal on either peer -- verified normalize-and-diff equal before adding both rows.」で、監査が現物で照合しても偽の箇所は無い |
| 中 3 | W1-2 が設計 §6 条件 2 の確定文言 (`ALTER ROLE … SET` を短くして戻す) ではなく接続水準の `options=-c` を使い、報告がその確定文言を落として言い換えていた | 監督が確定文言へ差し戻し。role 水準の `ALTER ROLE … SET '200ms'` (control_dsn) → store をその**後**に構築 → `finally` で `pg_roles.rolconfig` の元値へ復元、に書き直し。報告も原文引用つきで訂正 | **確認済み。** 現物 :225-229 の `_set_auditreader_statement_timeout` / :205-222 の `_read_auditreader_statement_timeout`、:260 で store を構築。`options=` の使用は 0 件。レビューが挙げた「残る穴」(role 水準 → pool 接続を固定するテストが無い) も、この書き直しで同じ 1 テストが覆うようになった |
| 中 4 | 新規関数 `check_auditreader_statement_timeout` が docstring 無し。道具の §4.1 (2) は基準 rev に無い statement に docstring を付けると必ず赤にする | 監督裁定により現状維持 (docstring 無し)。W2-7 は「(2)〜(5) が 0 件」で読み替え。docstring を付けられない件は台帳に起票予定 | **確認済み。** 監査の再実行で (1) 4 件・(2)〜(5) 0 件。読み替えの先例 (R-52 WP-3) と同形 |
| 低 5 | MitateDB 側で既存の非空振り `assert` が消えた | 両 peer に `assert _MIGRATION_NAMES_DECLARATIONS_ONLY <= set(MIGRATION_NAMES)` を同形で追加 | 確認済み (両 peer の該当行) |
| 低 6 | `_ISOMORPHIC_TARGETS` の経緯コメントが現物とずれたまま | 旧文を消さずに「追記 2026-09-20 (R-56 WP-1)」を追加 | 確認済み (r2db :2699-2703 / Mitate :2473-2477) |
| 低 7 | `pt.py` の log 1 本が scratchpad の外に出ていた | `$SP` を export し直して当該 5 ファイルを再実行、`log=` を貼り直し (`pt: 305 passed in 22.67s`) | 確認済み (当該ログは scratchpad の `dev-logs` 配下に在る) |
| クラス | 引き上げ無し。宣言どおり D | — | 確認済み。`_ISOMORPHIC_TARGETS` が 138 → 140 (D の契機) であり、`security/` も触るので D |

設計レビュー (1 回、`review-r56-design.md`) の指摘は設計 v1.0 に取り込み済みで、その番号 (高 1・高 2・中 4・中 5・中 6・中 7・中 8・低 9・低 12) は設計 §4〜§7 の本文に逐語で現れる。

### 5.6 主張と実測の突合 (§1.5 の 34・35 の独立項目)

| 主張 | 実測 | 判定 |
|---|---|---|
| WP-3 報告「SI-08 / r2db-api 既定 12,928 (残り 2,272)、MitateDB-api 既定 13,023 (残り 2,177)」 | 監査が登録テストの `_subblock_block_text` を直接呼んで再測 → **完全一致** | 一致 |
| WP-3 報告「SI-08 / MitateDB-api 既定がファイル最長ブロックになった (SI-14 / r2db-api 既定 12,624 を上回る)」 | 監査の再測でも SI-14 / r2db-api 既定 = 12,624 < 13,023 | 一致 |
| WP-3 報告「引いた test id 16 本すべてを実在確認済み」 | 監査が `security/CONTROL_MAPPING.md` の追加行から test 名 **11 種**を抽出し、全件 `def <name>` を現物で照合 → **不一致 0**。`::` 短縮形の解決先も両 peer のファイルに実在 | 一致 |
| WP-2 報告「(2)〜(5) は 0 件」 | 監査の独立再実行で (2)〜(5) 0 件、(1) 4 件、exit=1 | 一致 |
| WP-1 報告「位置 slice が実コードに 0 件」 | 監査の grep で残存 6 件はすべて `#` 始まりの経緯コメント中の文字列 | 一致 |
| WP-1 報告「`0013` は script に足していない」 | 監査の grep: `0013_role_connection_limits.sql` は 0 件、`0013` は :293・:295 の説明コメントのみ | 一致 |
| `public_value_scan` `total_flagged=0` (14 / 10 / 1 ファイル) | 監査が差分 23 ファイル全部で再測 → `# mode=tree files_scanned=23 total_flagged=0` | 一致 |
| `check_control_mapping_split.py --base 6b5213b` の 1 行 | 監査の再実行で逐語同一 (`missing=0 added=7 … rule=identical`) | 一致 |
| `check_doc_refs` `empty markdown files: 0` | 監査の再実行で同じ。差分の `.md` 3 本はいずれも追加行を持ち 0 バイト化なし (§2 の 15) | 一致 |
| **設計 §7 の「8,914 字・残り 6,286」** | 実装担当の着手時実測は **8,912・残り 6,288**。実装担当は実測を採り、その旨を報告と `preamble` の再測定文に書いた | **2 字の差。実測優先で妥当。設計側の註の起票は監督裁定事項** |
| WP-1 初期報告「設計は具体形を実装担当に委ねている」「設計 §6 条件2 が明示的に許容する形」 | 設計 §6 条件 2 の註は `ALTER ROLE ... SET` を**確定文言**で指定していた。報告は確定文言を落とした言い換えであった (§1.5 の 35) | **当初は不一致。差し戻し 3 で実装・報告とも訂正済み。現状は一致** |
| `r2db-api/tests/test_auditreader_statement_timeout.py`:233 の docstring 「Completion condition W1-2 (design §6 条件 2, **verbatim**)」 | 続く本文は設計の日本語確定文言の**英語による忠実な言い換え**であって逐語引用ではない | **軽微な不一致。**「verbatim」という自称を「per design §6 条件 2」等に改めるか否かは監督裁定事項 (§1.5 の 36) |
| 依頼者確定の逐語 (設計 §9.1) | 差分内に写した箇所は無く、言い換えの機会そのものが発生していない | 一致 |

### 5.7 未解決事項 (監査が挙げたもの。裁定は §5.8)

1. **gate を走らせた木が最終木ではない。** 差は `tools/tests/test_no_shared_cluster_defaults.py` の件数 pin 1 ファイルのみ (監査が独立確認)。その 1 ファイルは `finalize: tools/tests: 528 passed` が覆っている。最終木 `623d47c` での gate 再実行の要否は監督裁定。
2. **変異 M10 の陳腐化。** `…_139_rows` への参照は最終木に存在しない。役目は M12 が引き継いでおり実質の穴は無いが、記録としては「M10 は最終木に当たらない」と読めるようにしておく必要がある (本パケット §5.4.6 で取り消し線)。
3. **変異 id の衝突。** WP-2 の `M11`/`M12` と WP-3 の `M11`/`M11b`/`M12` が同名である。WP を跨ぐと一意でないため、記録の参照時は WP を添える必要がある。
4. **W2-1 の MitateDB 側の終了コード定数に専用変異が無い。** `MitateDB-api/src/mitatedb_api/ops.py`:1287 の `"F-17": 16` だけを壊す `M6-mitate` は実行されていない (指示書 §3.5 の雛形も `M6-r2db` だけ)。実害は小さい (`M5-mitate` が同じテストを赤にし、同型テストが両 peer の逐語一致を固定する) が、「peer ごとに 1 項目」(§3.4) の字義からは 1 つ欠けている。
5. **W2-3 の変異が指示書の M8 と別物である。** 「同定が 0 件なら緑」を直接壊す変異 (指示書の M8) は無く、代わりに M8 (owner 除外) と M11 (非空振り) が置かれている。実装報告に「指示外の判断」として記録済み。この差し替えの受理は監督裁定。
6. **`security/CONTROL_MAPPING.md` の Evidence のテスト名は機械で固定されていない** (M11 が緑)。今回は監査が 11 種すべてを独立に grep 照合して実在を確かめたが、将来の改名・削除は静かに通る。台帳起票の要否は監督裁定 (WP-3 報告 §8 の 2 と同旨)。
7. **W2-7 の完了条件の文言と道具の挙動の食い違い。** 字義の「exit 0」は機能コードを足す変更では原理的に満たせない。監督の読み替えで受理される前提だが、完了条件の文言そのものの修正か、道具側への除外の起票かは未決 (監督は「新しい関数に docstring を付けられない件は台帳に起票予定」と既に述べている)。
8. **SI-08 の両既定ブロックの残りが 2,272 / 2,177 字**で、次に SI-08 へ主張を足す作業はほぼ上限で始まる。SI-08 / MitateDB-api / 既定がファイル最長ブロックになった。監督は分割の台帳項目を起票予定と述べている。
9. **設計 §7 の字数 (8,914・残り 6,286) と実測 (8,912・残り 6,288) の 2 字差。** 実測が採られ、preamble にも実測が書かれている。設計側に訂正註を置くかは監督裁定。
10. **F-16 の既存 docstring と本 WP の実測の食い違い** (WP-2 報告 §疑義 2)。`test_f16_the_schema_owning_role_is_never_flagged_even_though_it_matches_every_class` の docstring が「AND, as owner, an implicit SELECT on both」と述べるが、実測では owner は SELECT 権限の交差に自然には現れない。F-16 は本 WP の対象外なので触られていない。台帳材料。
11. **`PostgresCell.catalog` に文の上限が無い件** (設計 §10 の 1) は `CONTROL_MAPPING` :578 に「open ledger item (R-56, design section 10), not a closed gap」として開示済み。台帳への起票そのものは未実施 (監督の作業)。同じく §10 の 2 (`r2dbsvc_control` に role 水準 timeout が無い)、§10 の 3 (`0013` が配備 script に無い)、§10 の 4 (r2db の監査 reader に R-51 相当の 2 段分類が無い) も起票待ち。
12. **本番への適用は行われていない** (`0014` 未適用)。したがって本番で `ops verify-declarations` を走らせると `FAIL F-17` / 終了コード 16 が返る。これは設計・runbook・`CONTROL_MAPPING` の Status で意図した信号として開示済みだが、**運用者への周知そのものは本変更セットの外**である。

### 5.8 監督裁定 (2026-09-20、受け入れ監査パケットに対して。逐語)

- A-1 (W2-7 の読み替え): `tools/check_comment_provenance.py --base 7ad7588` は機能コードの追加で §4.1 の (1) を必ず出す。完了条件は「§4.1 の (2)〜(5) が 0 件。(1) は対象外」と読む (R-52 WP-3 の先例)。監査の独立再実行で (1) の 4 行のみ・(2)〜(5) は 0 件。作業指示書 §3 の W2-7 の字義「通る」は本項をもって訂正する。道具が `src/` の新しい関数に docstring を付けられなくしている件は台帳 R-63 に起票した (道具の側を直す)。
- A-2 (`M6-mitate` の欠落): 監督が統合後の木で足して実行した。`MitateDB-api/src/mitatedb_api/ops.py` の `"F-17": 16` を 17 にする → `MitateDB-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_fails_when_declared_timeout_is_zero` が `assert 17 == 16` で赤、復元は sha256 2 回で照合。

`M6-mitate` の実行 (`mutate.py` の出力、**verbatim**):

```
M6-mitate expect=red   got=red       OK  | 1 failed | restore=ok
```

これにより §5.7 の 4 は解消した。

- A-3 (W2-3 の変異の差し替え): 指示書 §3.4 の M8 は実装の途中で owner 除外の変異に差し替えられ、コードレビューが空振りを実測して差し戻した。非空振りは M11-r2db / M11-mitate (役は残して `ALTER ROLE … RESET statement_timeout`) が担う。差し替えは実装報告に記録済みで、受け入れる。
- A-4 (陳腐化した M10 と変異 id の衝突): M10 は `…_139_rows` のテスト名が `…_140_rows` に改名されて対象を失い、役目は WP-2 の M12 が引き継いだ。WP-2 と WP-3 の M11 / M12 は別の spec ファイルの別の変異であり、記録では `WP-2 M11` / `WP-3 M11` のように WP を添えて指す。
- A-5 (gate の木と最終の木の差): 1 回目の gate (3763 passed) の後に入ったのは `tools/tests/test_no_shared_cluster_defaults.py` の pin 26 → 27 と、テストの docstring の 1 語 (`verbatim` → `rendered in English`。監査の指摘) だけである。最終の木で gate を再実行した。結果は本節に貼る。新しいテストファイルが未追跡の間は `git ls-files` の列挙に入らず、実装担当の実行でも 1 回目の gate でも pin が緑だった — 新しいファイルを足す WP の発注には「`git add -N` した状態で `tools/tests` を回す」を入れる。

最終の木 (main `623d47c` に docstring の 1 語の訂正を足した木) での `gate.py` の集計行 (**verbatim**):

```
gate: 3763 passed, 2 subtests passed in 308.51s (0:05:08)
gate: judge=PASS
gate: pg_database/pg_roles diff 0
```

log = `gate-r56-<日時>.log`。1 回目 (§5.3) は `3763 passed, 2 subtests passed in 313.11s (0:05:13)` で、**件数は同じ 3763** である。これにより §5.7 の 1 は解消した。

- A-6 (F-17 の主張を peer ごとに書くか Common に寄せるか): peer ごとのままとする (F-15・F-16 の先例と同じ形。証拠の test id が peer ごとに別である)。
- A-7 (`security/CONTROL_MAPPING.md` の Evidence のテスト名を解決する機械検査が無い): 台帳 R-64 に起票した。本件では監査が 11 種を全件現物で照合し不一致 0。
- A-8 (SI-08 の両ブロックの残り 2,272 / 2,177 字): 台帳 R-65 に起票した (R-59 と同じ純粋な移動で解ける)。
- A-9 (範囲外として残したもの): r2db-api の `PostgresCell.catalog` が取引ごとの timeout を通らない件は台帳 R-62、`0013` が配備 script に無い件と control / provision role に role 水準の timeout が無い件は R-66 に起票した。reader の例外の 2 段分類が r2db-api に無い件は応答が同じ 503 であり起票しない (設計メモ §10 の 4)。
- A-10 (変更クラス): 本件は Class D。依頼者の委任の逐語は設計メモ §9.1。R-54 と R-59 の作業指示書が Class C と宣言していたのは誤りで (`security/` 配下は D)、両書に訂正註を足した。事後の依頼者確認を引き継ぎ書で伺う。
- A-11 (本番): 何も適用していない。`0014` を適用するまで本番の `verify-declarations` は `FAIL F-17` (終了コード 16) になる。意図した信号である。

### 5.9 最終判定 (逐語)

最終判定: R-56 の WP-1〜WP-3 を受け入れる。台帳の R-56 行は閉じる。
