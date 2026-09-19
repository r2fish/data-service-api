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

## 5. 受け入れ監査と監督裁定

### 5.1 実施記録

### 5.2 完了条件の判定表

### 5.3 完了ゲートの集計行

### 5.4 変異表

### 5.5 レビュー指摘と対応

### 5.6 主張と実測の突合 (§1.5 の 34・35 の独立項目)

### 5.7 未解決事項

### 5.8 監督裁定

### 5.9 最終判定
