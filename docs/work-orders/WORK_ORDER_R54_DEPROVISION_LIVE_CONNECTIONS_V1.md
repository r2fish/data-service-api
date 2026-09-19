# 作業指示書 — R-54 生きた接続の前の deprovision

## 0. 版数と位置づけ

- **v1.0 (2026-09-19)。** 台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-54** (`RM`:448)。設計文書は **`docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0 (監督確定、設計レビュー 2 回)** で、枠・決定・却下案・実測はすべてそちらにある。本書はその Change Set Manifest である。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。

### 0.1 変更クラス

- 全体の見込みは **Class C** — `security/CONTROL_MAPPING.md` に主張を**足す** (設計 §9 の監督裁定)。各 WP の確定は着手時に `tools/change_class.py` と `RM` §9 の 8 の表で行う。
- **D に上げない条件** (設計 §9): 両 peer に**同名のテストヘルパを置かない**。`_ISOMORPHIC_TARGETS` (`r2db-api/tests/test_audit_query.py`:2388 / `MitateDB-api/tests/test_audit_query.py`:2179) を増減しない。増減が要ると判断したら**実装せず報告に書く**。
- 公開契約 `spec/`・`security/SECURITY_INVARIANTS_V1.md`・`conformance-tests/` の本文は触らない。

## 1. 共通の枠

### 1.1 読むべき正本

- 設計 `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0 の §4 (D-1・D-2R の 6 段)、§4.1 (失敗時の状態)、§5 (追随一覧)、§6.1 (完了条件と変異)、§7 (証拠)、§9 (変更クラスと置き場)。
- `CLAUDE.md` (正本の順序・境界)、`docs/work-orders/OPERATING_CONDITIONS.md` §0・§1.4・§1.5・§1.6・§1.9・§1.10。

### 1.2 全 WP 共通の触らないファイル

`spec/`、`security/SECURITY_INVARIANTS_V1.md`、`security/CONTROL_MAPPING_HISTORY.md`、`conformance-tests/CONDITIONS.md`・`CONDITIONS_HISTORY.md`、`conformance-tests/` の各テスト本体、両 peer の conformance adapter と `real_server_*.py` の **sweep** (設計 §5.1 の (v)。admin DSN の後始末であって `0004` の段ではない)、`MitateDB-api/migrations/0001_bootstrap_platform.sql`:176-181 (監督裁定: 主語が bootstrap admin で射程が別。触らない)、`docs/design/` の記録 (統合の記録は監督が行う)、`.github/`、`tools/dev/`。

### 1.3 順序と触るファイルの重なり

- **直列**: WP-1 → WP-2 → WP-3。§1.5 の 34 (主張は実測の後) により、WP-2 の runbook の文言は WP-1 の変異結果を得てから書く。
- 監督裁定 (2026-09-19) により **SQL と `tests/test_postgres.py` は全部 WP-1**、runbook・README・設計文書の訂正註・`test_credential_persistence.py` の docstring は WP-2、`security/CONTROL_MAPPING.md` は WP-3 とする。**3 WP の触るパスは重ならない** (§2.2・§3.2・§4.2 の表で実ファイル名により示す)。並行はしないが、重なり 0 は確認済みである (§1.2 の 16・17)。

### 1.4 worktree と道具の引数

- worktree は WP ごとに分ける (想定名 `r54-wp1` / `r54-wp2` / `r54-wp3`。実名は監督が起こす)。以下のコマンド例の `-C` はその worktree を指す。
- テスト: `tools/dev/pt.py -C <worktree> -- <pytest 引数>` (前景・Bash timeout 600000。§1.6 の 42)。
- 変異: `tools/dev/mutate.py "$SP/r54-wp1-mutations.json" -C <worktree>`。`$SP` は自分の scratchpad。
- **`gate.py` / `finalize.py` / `pytest` の直接実行・commit・merge は行わない** (監督)。

### 1.5 実装担当の注意 (全 WP 共通)

1. **下請けの Agent を起動しない** (§1.7 の 47)。
2. **suite 全体を回さない。** 担当範囲のファイルだけを `pt.py` で回す (完了ゲートは監督)。
3. **commit・`gate.py`・`finalize.py` は監督が行う。** 作業ツリーを綺麗にしたまま報告で終わる。
4. **疑義は実装せず報告に書く。** 設計に無い検査・機構を足さない (§1.5 の 37)。設計と現物が食い違ったら止まって上げる。
5. **絶対パス・一時ディレクトリ名 (`dsa-testpg-…` / `pytest-of-…`)・traceback を文書やコメントに書かない** (§1.9、§2 の 13)。接続は一般形で書く。
6. **実 credential・実ホスト名・実ドメイン・実 DSN を 1 つも書かない。** 合成値と `example.invalid` のみ。
7. conformance (約 9 分) は**前景の 1 回**で回しきる。`conformance-tests` と `tools/tests` を 1 回の pytest に結合しない (別々に呼ぶ)。
8. 変異は **1 項目 1 テスト** (`mutate.py` は `expect=red` に `-x` を付け、先頭の失敗で打ち切る)。
9. 新規ファイルを足すと件数 pin の静的テストが赤くなることがある。赤が出たら**直さずに実測を報告**する (§1.5 の 40b)。

## 2. WP-1 — 両 peer の `0004` と deprovision のテスト

### 2.1 目的と範囲

設計 §4 の **D-1** と **D-2R** を現物にする。`0004` を 6 段 ((1) 既存 guard → (2) 事前検査 → (3) 一時付与 → (4) `ALLOW_CONNECTIONS false` → (5) 既存の絞った terminate → (6) 素の `DROP DATABASE` / `DROP ROLE`) にし、生きた接続の前で 1 回で通ることを両 peer で固定する。**(5) の terminate の文と (6) の DROP の文は変えない。** `WITH (FORCE)` は使わない (設計 §8 の X-5、実測 M-11)。

### 2.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/migrations/0004_deprovision_application.sql`、`MitateDB-api/migrations/0004_deprovision_application.sql` (段の追加とコメント)、`r2db-api/migrations/0003_provision_application.sql`:145-148 と `MitateDB-api/migrations/0003_provision_application.sql`:101-104 (全称文。設計 §5.1 の (iii))、`MitateDB-api/migrations/0001_bootstrap_platform.sql`:30-32 (**R-1 allowlist の当該項のみ**。SQL は変えない。:35-39 の証拠状態の文も変えない)、`r2db-api/tests/test_postgres.py` (:138-140 と :249 付近の docstring、および新しいテスト)、`MitateDB-api/tests/test_postgres.py` (新しいテスト)、両 peer の新規テストファイル (置く場合) | §1.2 の共通。`security/`、`docs/`、両 peer の `src/` (設計 §5.1 の末尾: `r2db-api/src/r2db_api/postgres.py`:354 は pool の liveness の説明で `0004` と無関係。追随不要)、`conformance-tests/`、既存のリトライ 4 箇所 (設計 §11 の F-4 裁定: **変えない**) |

- **形の指定** (設計 §4 D-2R): (2) と (4) は `SELECT CASE WHEN EXISTS (…) THEN format(…) ELSE 'SELECT 1' END` + `\gexec`。**`DO $$ … $$` の中に psql 変数を書かない** (psql は dollar-quote の中を展開しない。F-2)。(2) の例外の文言は**定数**で、接続の role 名を入れない。(3) は存在する role だけに `GRANT … TO CURRENT_USER WITH INHERIT TRUE, SET FALSE`。
- **位置**: (2)(3)(4) は MitateDB では `\if :{?database_name}` の真の枝の中、r2db では credential guard の `\gexec` (`0004`:67-71) の**後**。else 枝 (database 無し) に一時付与は置かない (設計 §4 D-1 の理由)。
- **実装の最初に psql の挙動を 1 行で実測する** (dollar-quote の中で psql 変数が展開されないこと)。結果を報告に書く。

### 2.3 完了条件

| # | 完了条件 |
|---|---|
| W1-1 | 生きた接続 3 者のうち **runtime role の接続を 1 本開けたまま**、provision / control の DSN で `0004` を**リトライなしで 1 回**実行して通る (両 peer) |
| W1-2 | `0004` の本文を読む**構造テスト**: `ALLOW_CONNECTIONS false` の文が**一時付与の後・terminate の前**に在る (両 peer。docstring に「行動面の裏づけは設計 §3.2 の H-1 の引用」と明記する) |
| W1-3 | W1-1 の後、**両 role が消え、実行 role の `pg_auth_members` の該当行が 0** である |
| W1-4 | **事前検査**: その application の role でも実行 role でもない**通常の LOGIN role** の接続が在ると、`0004` は明示の例外で止まり、**何も変わっていない** (database が残り、`datallowconn` が true のまま、membership 無し、registry 行も残る)。pin するのは「止まること」と「何も変わっていないこと」で、PostgreSQL の `DETAIL:` は pin しない |
| W1-5 | `0004` の本文を読む**構造テスト**: 一時付与の `GRANT` が `WITH INHERIT TRUE, SET FALSE` の形である (両 peer。裏づけは M-9 の引用) |
| W1-6 | **database を先に落としてから再実行しても `0004` が完了する** (設計 §4.1 の 3 行目の状態からの再実行) |
| W1-7 | MitateDB の **registration-only / ghost role の枝**が壊れていない (`0004`:95-101 を通る既存のテストが緑) |
| W1-8 | `0003` の全称文 (両 peer) と MitateDB `0001`:30-32 の allowlist コメントが、D-2R と設計 §4.1 に合う。**`0001` の SQL と :35-39・:176-181 は変えない** |
| W1-9 | `r2db-api/tests/test_postgres.py`:249 付近の docstring の「Retrying the entire script from the top is safe …」が設計 §4.1 に合う (MitateDB 側 :335-341 は同じ断言を持たないので変えない) |
| W1-10 | 触ったファイルに実値が無い (§1.9)。`python3 tools/public_value_scan.py <触ったファイル>` の集計行を報告に貼る |
| W1-11 | **本番に対して何も実行していない。** 試験の接続先は使い捨ての PostgreSQL だけである |
| W1-12 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) |

### 2.4 完了条件 → 変異

変異の `file` は、特記の無い行は両 peer の `0004_deprovision_application.sql` (peer ごとに 1 項目ずつ分ける)。赤になる test id は予想であり、**実装担当が実名に置き換えて報告する**。

| # | 変異 (操作) | 期待 |
|---|---|---|
| W1-1 | **M1**: (3) の `GRANT … WITH INHERIT TRUE, SET FALSE` の段を外す | 赤 (`permission denied to terminate process`。M-8) |
| W1-2 | **M2**: (4) の `ALTER DATABASE … WITH ALLOW_CONNECTIONS false` の文を外す | 赤 (構造テスト) |
| W1-3 | **M3**: (6) の `DROP ROLE IF EXISTS :"runtime_role"` を外す | 赤 (role 残存と membership 残存の両方) |
| W1-4 | **M4**: (2) の事前検査の段を外す | 赤 (「何も変わっていない」の assert が落ちる。検査が無ければ (4) まで進み `datallowconn=false` になる) |
| W1-5 | **M5**: (3) の `GRANT` から `, SET FALSE` を外す | 赤 (構造テスト) |
| W1-6 | **M6**: (4) の `pg_database` の存在検査を外す | 赤 (`ERROR: database "..." does not exist`) |
| W1-7 | **監査照合**: 既存の該当テスト名と、それが緑である `pt.py` の集計行を報告に残す | — |
| W1-8 | **監査照合**: 直した行の `file:line` と直した後の文を逐語で報告に残す | — |
| W1-9 | **監査照合**: 同上 | — |
| W1-10 | **監査照合**: `public_value_scan` の集計行 | — |
| W1-11 | **監査照合**: 接続先の出所 (テスト基盤の管理 DSN の**環境変数名**) の `file:line`。**実 DSN・実ホスト名を書かない** | — |
| W1-12 | **監査照合**: 本表の行数と対応数 | — |

### 2.5 変異の JSON (雛形。`old` は実装後の現物に合わせて埋める)

```json
{
  "pytest": ["-q"],
  "mutations": [
    {"id": "M1-r2db", "file": "r2db-api/migrations/0004_deprovision_application.sql",
     "old": "<(3) の GRANT の段>", "new": "",
     "tests": ["r2db-api/tests/<W1-1 のテスト>"], "expect": "red"},
    {"id": "M1-mitate", "file": "MitateDB-api/migrations/0004_deprovision_application.sql",
     "old": "<同上>", "new": "",
     "tests": ["MitateDB-api/tests/<W1-1 のテスト>"], "expect": "red"},
    {"id": "M2-r2db", "file": "...0004...", "old": "<(4) の ALTER の文>", "new": "",
     "tests": ["<W1-2 の構造テスト>"], "expect": "red"},
    {"id": "M3-r2db", "file": "...0004...", "old": "DROP ROLE IF EXISTS :\"runtime_role\";", "new": "",
     "tests": ["<W1-3 のテスト>"], "expect": "red"},
    {"id": "M4-r2db", "file": "...0004...", "old": "<(2) の事前検査の段>", "new": "",
     "tests": ["<W1-4 のテスト>"], "expect": "red"},
    {"id": "M5-r2db", "file": "...0004...", "old": ", SET FALSE", "new": "",
     "tests": ["<W1-5 の構造テスト>"], "expect": "red"},
    {"id": "M6-r2db", "file": "...0004...", "old": "<(4) の存在検査>", "new": "<無条件の ALTER>",
     "tests": ["<W1-6 のテスト>"], "expect": "red"}
  ]
}
```

- **M1〜M6 は peer ごとに 1 項目**に分ける (両 peer で 12 項目)。1 項目の `tests` に 2 件以上を並べない (§1.5 の 8)。

### 2.6 実行するコマンド

```bash
# 担当範囲の peer テスト (別々に。suite 全体は回さない)
tools/dev/pt.py -C .claude/worktrees/r54-wp1 -- MitateDB-api/tests/test_postgres.py MitateDB-api/tests/test_ops.py -q
tools/dev/pt.py -C .claude/worktrees/r54-wp1 -- r2db-api/tests/test_postgres.py r2db-api/tests/test_control_plane_store.py r2db-api/tests/test_credential_persistence.py -q
# 新規テストを別ファイルに置いた場合はそのファイルも同じ形で 1 回
# deprovision を通る残りの peer テスト (広めの確認。peer ごとに 1 回)
tools/dev/pt.py -C .claude/worktrees/r54-wp1 -- MitateDB-api/tests -q
tools/dev/pt.py -C .claude/worktrees/r54-wp1 -- r2db-api/tests -q
# conformance (両 peer の http adapter の deprovision を通るファイル。約 9 分、前景で 1 回)
tools/dev/pt.py -C .claude/worktrees/r54-wp1 -- conformance-tests/test_c05_limit_declaration_agreement.py conformance-tests/test_c09_audit_evidence.py conformance-tests/test_c14_authority_boundary.py conformance-tests/test_c19_client_self_sufficiency.py -q
# tools 側 (conformance と結合しない)
tools/dev/pt.py -C .claude/worktrees/r54-wp1 -- tools/tests -q
# 変異
tools/dev/mutate.py "$SP/r54-wp1-mutations.json" -C .claude/worktrees/r54-wp1
```

- **conformance のファイルの根拠** (2026-09-19 の実測): adapter の `deprovision_application` を呼ぶのは `conformance-tests/conftest.py` (residue tracker、12 箇所) と `test_c05_limit_declaration_agreement.py`・`test_c09_audit_evidence.py`・`test_c14_authority_boundary.py` (7 箇所)・`test_c19_client_self_sufficiency.py` である。`conftest.py` は上の 4 ファイルの実行で自動的に効く。
- **事実 (指示との差)**: r2db-api には `tests/test_ops.py` が無い (`test_ops_declarations.py` / `test_ops_upgrade.py` / `test_ops_verify_declarations.py` のみで、ops CLI に `deprovision` サブコマンドが無いため)。上のコマンド列はその実測に合わせてある。

### 2.7 記録 (統合時に監督が埋める)

WP-1〜WP-3 は単一のコミット `42ebc2c` (main `a586a17`、2026-09-19) で統合した (申告と実挙動を同じコミットで動かすため)。実施の記録・完了条件 → 変異 → 赤になった test id の対応表・完了ゲートの集計行は §5.1 以下に在る。

## 3. WP-2 — runbook・README・設計文書の訂正註

### 3.1 目的と範囲

設計 §5.1 の 1・2・4・5・6・7 と (i)、§5.2 の訂正註 3 件を現物にする。**WP-1 の変異結果を得てから書く** (§1.5 の 34)。

### 3.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/docs/cloud-run-cloud-sql.md` (§9 の項目 3、§9.1 の項目 3 の**訂正註**、:2398 の lock 表)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (:476 付近、§14 の branch (B) の 1 の段 :1087-1105)、`MitateDB-api/README.md`:190、`r2db-api/tests/test_credential_persistence.py`:774 付近の docstring、`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` (:45 と :247 に**訂正註 1 行ずつ**)、`docs/design/CONFORMANCE_ADAPTER_V1.md`:2786-2792 (**訂正註 1 行**) | §1.2 の共通。WP-1 が触った SQL とテスト、`security/`、`docs/design/DEPROVISION_FORCED_DROP_V0_1.md` (記録は監督) |

### 3.3 完了条件

| # | 完了条件 |
|---|---|
| W2-1 | MitateDB runbook §9 の**新しい項目 3**: `GRANT pg_signal_backend` をやめ、「接続を 1 本開けた application を deprovision して `0004` が通ることを確かめる」に差し替える。(a) 実行前に **admin で `pg_stat_activity` を 1 回読み**、その database に runtime / developer / 実行 role 以外の接続が在るかを記録する手順、(b) 設計 §4.1 の失敗時の状態と掃除の**表**、(c) **Cloud SQL の管理接続が事前検査に掛かるかは未実測 (`absent`)** の 1 行を含む |
| W2-2 | 同 §9.1 の項目 3 の行 (:1703-1706) に**訂正註**を足す。**本文は書き換えない** (§1.8 の 56)。当時の GRANT は効果を持たない (M-3)、その membership は `REVOKE` してよい、実行するのは bootstrap の `postgres` である、を書く |
| W2-3 | 同 :2398 の lock 表の deprovision 行に、**足す行だけ**を書く (`ALTER DATABASE … ALLOW_CONNECTIONS` と一時付与)。**既存の記述は真のまま**なので消さない |
| W2-4 | r2db runbook: §14 の branch (B) の 1 の段を D-2R の順序に合わせ、:476 付近の guard の順序の説明を合わせ、設計 §4.1 の表を書く |
| W2-5 | `MitateDB-api/README.md`:190 と `r2db-api/tests/test_credential_persistence.py`:774 付近の docstring が新しい手段に合う |
| W2-6 | `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`:45・:247 と `docs/design/CONFORMANCE_ADAPTER_V1.md`:2786-2792 に**本メモを指す訂正註を 1 行ずつ**足す。**本文は書き換えない**。`*_HISTORY.md` と `conformance-tests/CONDITIONS.md` は触らない |
| W2-7 | `python3 tools/check_doc_refs.py` が dangling 0、`python3 tools/public_value_scan.py <触ったファイル>` が `total_flagged=0` |
| W2-8 | 触った docstring を持つテストファイルが緑である |
| W2-9 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) |

### 3.4 完了条件 → 変異

| # | 変異 |
|---|---|
| W2-1〜W2-6 | **監査照合** (文書と docstring の変更で、振る舞いを持たない)。**照合対象の逐語記録**として、直した各箇所の `file:line` と直した後の文 (要旨ではなく逐語) を報告に残す |
| W2-7 | **監査照合**: 2 つの道具の集計行を逐語で残す |
| W2-8 | **M7**: `r2db-api/tests/test_credential_persistence.py` の docstring だけを直した状態で当該ファイルを回して緑であることを確かめる (変異ではなく実行の記録。集計行を残す) |
| W2-9 | **監査照合**: 本表の行数と対応数 |

### 3.5 実行するコマンド

```bash
tools/dev/pt.py -C .claude/worktrees/r54-wp2 -- r2db-api/tests/test_credential_persistence.py -q
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触ったファイル...>
```

### 3.6 記録 (統合時に監督が埋める)

WP-1〜WP-3 は単一のコミット `42ebc2c` (main `a586a17`、2026-09-19) で統合した (申告と実挙動を同じコミットで動かすため)。実施の記録・完了条件 → 変異 → 赤になった test id の対応表・完了ゲートの集計行は §5.1 以下に在る。

## 4. WP-3 — `security/CONTROL_MAPPING.md`

### 4.1 目的と範囲

設計 §9 の主張を **SI-00 の両 peer の既定の小ブロック**に足す (監督裁定)。主張は「deprovision は cluster 全体の predefined role を要さず、その application の role への一時的な INHERIT 付与だけで行う。Cloud SQL での証拠は `absent`」。**既存の主張は訂正不要** (設計 §9 の判定材料。手段を名指す行は 0 行) — 足すだけである。

### 4.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `security/CONTROL_MAPPING.md` (SI-00 の r2db-api / MitateDB-api の**既定**の小ブロックと、:5 の版数行) | §1.2 の共通。`security/CONTROL_MAPPING_HISTORY.md`、他の SI・他のブロック、WP-1/WP-2 が触ったファイル |

### 4.3 完了条件

| # | 完了条件 |
|---|---|
| W3-1 | SI-00 / r2db-api / **既定** と SI-00 / MitateDB-api / **既定**の両方に、上の主張が Control と Evidence と Status の軸の規約に沿って入る (peer ごとに文面を書き分ける。**同じ安全結果**であればよい) |
| W3-2 | 証拠は **`absent`** と正直に書く (設計 §7。Cloud SQL 未実測、本番に何も適用していない)。証拠のテスト名は WP-1 の実名を使う |
| W3-3 | **足した後の SI-00 の両ブロックの字数を測って報告する。残りが 2,000 字未満なら報告する** (置く前の実測は r2db-api 2,939 / MitateDB-api 2,502、残り 12,261 / 12,698。上限 15,200 = `conformance-tests/test_control_mapping_register.py`:97) |
| W3-4 | 版数を **2.9 → 2.10** に上げ、:5 の版数行にこの変更を書く (版数行はその版の変更を述べる行で、累積しない) |
| W3-5 | `python3 tools/check_control_mapping_split.py --base <基点 main SHA>` を実行し、**集計行を逐語で報告に貼る** (本 WP は分割ではなく追記なので `added` が非 0 になる。`subsequence=ok` / `ccr14=identical` / `rule=identical` であること) |
| W3-6 | 登録テストが緑: `tools/dev/pt.py -C <worktree> -- conformance-tests/test_control_mapping_register.py -q` |
| W3-7 | `python3 tools/check_doc_refs.py` が dangling 0、`python3 tools/public_value_scan.py security/CONTROL_MAPPING.md` が `total_flagged=0` |
| W3-8 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) |

### 4.4 完了条件 → 変異

| # | 変異 |
|---|---|
| W3-1・W3-2・W3-4 | **監査照合**: 足した bullet の逐語と、置いた (SI, peer, ブロック, 軸) を報告に残す |
| W3-3 | **監査照合**: 測った字数と残りの数値、測り方 (登録テストの `_subblock_block_text` と同じ数え方) を残す |
| W3-5 | **監査照合**: `check_control_mapping_split.py` の集計行を逐語で残す |
| W3-6 | **M8**: 足した bullet を 1 つ外した状態で登録テストを回しても緑である (= 登録テストは字数と形だけを見る) ことを確かめ、集計行を残す。**この WP は振る舞いの変異を持たない**ことの記録である |
| W3-7 | **監査照合**: 2 つの道具の集計行 |
| W3-8 | **監査照合**: 本表の行数と対応数 |

### 4.5 実行するコマンド

```bash
tools/dev/pt.py -C .claude/worktrees/r54-wp3 -- conformance-tests/test_control_mapping_register.py -q
python3 tools/check_control_mapping_split.py --base <基点 main SHA>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py security/CONTROL_MAPPING.md
```

### 4.6 記録 (統合時に監督が埋める)

WP-1〜WP-3 は単一のコミット `42ebc2c` (main `a586a17`、2026-09-19) で統合した (申告と実挙動を同じコミットで動かすため)。実施の記録・完了条件 → 変異 → 赤になった test id の対応表・完了ゲートの集計行は §5.1 以下に在る。

## 5. 受け入れ監査と監督裁定

本節は受け入れ監査パケットの写し (§5.1〜§5.7) と、それに対する監督裁定 (§5.8)・最終判定 (§5.9) である。監査は `evidence-auditor` 1 回、統合後の木 (作業コミット `42ebc2c`、main `a586a17`) に対する**読み取りのみ** (pytest・`gate.py`・`finalize.py` は実行していない)。監査の判定は 充足 / 未充足 / 証拠不足 の 3 値で、裁定は含まない。設計メモは `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0 で、以下で「設計 §n」と書くのは同メモの節である (同メモのローカルの族 R-1〜R-7・F-1〜F-8・M-1〜M-13・H-1・H-2 も同様に同メモのもので、台帳 `RM` §8 の R-N とは別である)。

### 5.1 実施記録

- **統合**: 作業コミット `42ebc2c`、main `a586a17` (merge)。基点 main `3a6be62`。差分は単一コミット `git diff 3a6be62..42ebc2c` = **15 ファイル、867 挿入 / 69 削除**。
  - SQL: 両 peer `migrations/0004_deprovision_application.sql` (r2db +104/-5、Mitate +110/-9)、両 peer `0003_provision_application.sql` (各 +6/-1)、`MitateDB-api/migrations/0001_bootstrap_platform.sql` (+9/-3)。
  - テスト: `r2db-api/tests/test_postgres.py` (+230/-10)、`MitateDB-api/tests/test_postgres.py` (+201/-0)、`r2db-api/tests/test_credential_persistence.py` (+5/-1)。
  - 文書: `MitateDB-api/docs/cloud-run-cloud-sql.md` (+70/-18)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (+74/-10)、`MitateDB-api/README.md`、`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`、`docs/design/CONFORMANCE_ADAPTER_V1.md`。
  - 主張: `security/CONTROL_MAPPING.md` (+24/-9、版 2.9 → 2.10)、`security/CONTROL_MAPPING_HISTORY.md` (+12/-0)。
- **WP の切り方と触るパス**: WP-1 = SQL と `tests/test_postgres.py`、WP-2 = runbook / README / 設計文書の訂正註 / `test_credential_persistence.py` の docstring、WP-3 = `security/`。**3 WP の触るパスに重なりは無い** (差分のファイル一覧で照合)。
- **変更クラス**: 宣言どおり **Class C**。`_ISOMORPHIC_TARGETS` (`r2db-api/tests/test_audit_query.py` / `MitateDB-api/tests/test_audit_query.py`) は差分 0 (両ファイルとも差分に現れない)。両 peer に同名の共有テストヘルパは置かれておらず、追加されたのは同名の**テスト関数 6 件 × 2 peer** のみ (本体は peer ごとに直書き。設計 §6 の監督裁定 R-6 どおり)。
- **段の形 (D-2R)**: 両 peer の `0004` で、非コメントの追加行は **(2) 事前検査・(3) 一時付与 2 本・(4) `ALLOW_CONNECTIONS false`** の 4 つの `SELECT CASE … \gexec` のみ。**(5) terminate の文と (6) `DROP DATABASE` / `DROP ROLE` の文は 1 字も変わっていない** (差分の非コメント行を実測)。`0003` 両 peer と `0001` の変更は**コメントのみ** (非コメント変更行 0)。`WITH (FORCE)` は現物に無い。
- **位置**: MitateDB は `\if :{?database_name}` の真の枝の中 (`0004`:77 の `\if` と :189 の `\else` の間に (2)(3)(4) が在る)、r2db は credential guard の `\gexec` の後。`\else` 枝 (registration-only / ghost role) には新しい段が無い。
- **道具 (実装報告が引いた集計行、verbatim)**:
  - `pt: 93 passed in 6.42s` / `pt: 357 passed in 42.28s` / `pt: 1369 passed, 2 subtests passed in 133.90s (0:02:13)` / `pt: 1336 passed in 97.05s (0:01:37)` / `pt: 249 passed in 163.35s (0:02:43)` (conformance c05/c09/c14/c19、前景 1 回) / `pt: 507 passed in 30.22s` (tools/tests) / `pt: 300 passed in 32.30s` (round 3 後の両 peer `test_postgres.py`) / `pt: 61 passed in 6.93s` (WP-2) / `pt: 34 passed in 0.23s` (WP-3 登録テスト、訂正後) / `pt: 57 passed in 0.02s` (WP-3 が選んだ tools/tests 2 本)。
  - `# mode=tree files_scanned=7 total_flagged=0` (WP-1 の 7 ファイル) / `# mode=tree files_scanned=6 total_flagged=0` (WP-2 の 6 ファイル) / `# mode=tree files_scanned=2 total_flagged=0` (WP-3、`CONTROL_MAPPING.md` と `CONTROL_MAPPING_HISTORY.md`)。
  - `check_doc_refs OK: 0 dangling references` (WP-2・WP-3 とも、最終状態で再実行)。
  - `missing=2 added=14 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical` (`tools/check_control_mapping_split.py --base 3a6be62`、exit 0)。
  - 統合時: `finalize: tools/tests: 507 passed in 29.61s`。

### 5.2 完了条件の判定表

#### 5.2.1 WP-1 (`0004` と deprovision のテスト)

| # | 判定 | 証拠 |
|---|---|---|
| W1-1 | **充足** | `r2db-api/tests/test_postgres.py`:377 / `MitateDB-api/tests/test_postgres.py`:1939 `test_deprovision_succeeds_in_a_single_pass_with_a_live_runtime_role_connection`。runtime DSN の接続を開けたまま `_run_psql` を **1 回**呼ぶ形 (リトライを持つ `deprovision_app` を意図的に使わないと docstring に明記)。r2db は control DSN、Mitate は provision DSN。変異 M1 が両 peer で赤 (§5.4) |
| W1-2 | **充足** | 同 :398 / :1960 `test_0004_allow_connections_false_is_between_the_temporary_grant_and_terminate`。**コメント行 (先頭空白を除き `--` で始まる行) を落としたテキスト**に対して `grant_index < allow_connections_index < terminate_index` を assert。docstring に「Behavioural backing is design H-1's own quoted single-session run, in that same order, not re-exercised here.」。変異 M2 が両 peer で赤。軽微: 指示書の文言は「設計 §3.2 の H-1 の引用」で、docstring は節番号を書かず H-1 を名指す |
| W1-3 | **充足 (解釈の補足あり)** | 同 :424 / :1987 `test_deprovision_leaves_no_role_or_executor_membership_behind`。membership の count assert を `pg_roles` 残存 assert の**前**に置き直し済み (レビュー指摘 1)。count は `pg_auth_members … AND m.inherit_option = true` に絞る — 絞らないと module 共有 fixture の他 application の `CREATE ROLE` 暗黙 ADMIN OPTION 行 (`inherit_option=false`、M-7) が混じり 0 にならない、という実装報告の逸脱記録あり。変異 M3 が両 peer で赤、赤の行は membership assert 自身 (`M3-r2db.log:52` → `r2db-api/tests/test_postgres.py:461`、`M3-mitate.log:51` → `MitateDB-api/tests/test_postgres.py:2023`) |
| W1-4 | **充足** | 同 :469 / :2031 `test_deprovision_pre_check_stops_and_changes_nothing_for_an_unrelated_connected_role`。無関係の LOGIN role を作って接続 → `pytest.raises(RuntimeError)` → `datallowconn` が `True`、`inherit_option=true` の membership が 0、registry 行が 1。PostgreSQL の `DETAIL:` は pin していない。変異 M4 が両 peer で赤 |
| W1-5 | **充足** | 同 :530 / :2091 `test_0004_temporary_grant_uses_inherit_true_set_false`。コメント除去後のテキストで `GRANT %I TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` を 2 件 assert。裏づけは M-9 の引用と docstring に明記。変異 M5 が両 peer で赤 |
| W1-6 | **充足** | 同 :546 / :2107 `test_deprovision_completes_on_rerun_after_the_database_was_already_dropped`。database を直接落としてから `0004` を 1 回。変異 M6 が両 peer で赤 (`ERROR: database "..." does not exist`) |
| W1-7 | **充足 (監査照合)** | `MitateDB-api/tests/test_postgres.py`:2139 `test_ghost_roles_from_an_incomplete_provisioning_attempt_are_dropped_by_deprovision`、同 :2483 `test_two_state_registry_allows_deprovisioning_a_registered_but_unprovisioned_application` が現物に在り、`MitateDB-api/tests` の `pt: 1369 passed, 2 subtests passed` に含まれて緑。新しい段は `\if` の真の枝の中だけで、`\else` 枝に変更が無いことを差分で確認。報告の行番号 (2124 / 2468) は最終編集前の値で、現物は 2139 / 2483 (名前は一致) |
| W1-8 | **充足 (監査照合)** | `r2db-api/migrations/0003…`:148-152「outside of a `0004` deprovision attempt that fails at or after its own temporary self-grant stage (D-2R stage (3), design docs/design/DEPROVISION_FORCED_DROP_V0_1.md §4.1), whose own temporary self-grant on the runtime/developer role can then still be standing until that script is retried to completion or the membership is revoked by hand.」、Mitate `0003`:104-108 同旨。`MitateDB-api/migrations/0001…`:30-36 の allowlist 項は「pg_terminate_backend (requires privileges of the role whose backend is being terminated, M-2's own `DETAIL:` -- `0004` obtains that via the temporary self-grant listed next, not via `pg_signal_backend` membership or an operator's own advance `GRANT`), ALTER DATABASE … WITH ALLOW_CONNECTIONS false, and GRANT <role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE (0004's own temporary self-grant onto its own already-created application roles -- does NOT assume `pg_signal_backend` membership; design …)」。**`0001` の SQL は不変、証拠状態の文と :176-181 相当も不変** (差分の非コメント変更行 0 で実測) |
| W1-9 | **充足 (監査照合)** | `r2db-api/tests/test_postgres.py` の `deprovision_app` docstring が「Retrying the entire script from the top remains safe after design D-2R … the state left behind is no longer exactly as it was: the registry row itself is untouched … but the database is left non-connectable and the temporary self-grant is left standing」に差し替え。MitateDB 側の同関数は差分に現れず不変 |
| W1-10 | **充足 (監査照合)** | `# mode=tree files_scanned=7 total_flagged=0`。監査側の独立確認: 差分の追加行に作業機の絶対パス・一時ディレクトリ名・作業用の一時領域への参照は 0 件。追跡中の 0 バイト `.md` も 0 件 |
| W1-11 | **充足 (監査照合)** | 接続先は環境変数 `R2DB_TEST_ADMIN_DSN` (`r2db-api/tests/test_postgres.py`:57 `ADMIN_DSN_ENV`) / `MITATEDB_TEST_ADMIN_DSN` (`MitateDB-api/tests/test_postgres.py`:59)。実 DSN・実ホスト名は現物にも報告にも無い。完了ゲートの `pg_database/pg_roles diff 0` も本番非関与と整合 |
| W1-12 | **充足** | 本表 12 行すべてに変異または監査照合が在る (変異 6 × 2 peer + 監査照合 6) |

#### 5.2.2 WP-2 (runbook・README・設計文書の訂正註)

| # | 判定 | 証拠 |
|---|---|---|
| W2-1 | **充足** | `MitateDB-api/docs/cloud-run-cloud-sql.md` §9 項目 3 を「Live-connection deprovision」に差し替え。(a) 実行前の admin の `SELECT usename, usesysid IS NOT NULL AS is_a_login_role FROM pg_stat_activity …` の読みと記録手順、(b) 失敗時の状態と掃除の表 (設計 §4.1 の 3 行 + レビュー B-4 由来の「stage (3)/(4) が `--lock-timeout` で cancel された」4 状態目)、(c)「Whether Cloud SQL's own management connections … is unexercised against a real instance (`absent`)」の文。`GRANT pg_signal_backend` の手順は消えている。使い捨て application に対してのみ実施・稼働中には実行しない旨も入る |
| W2-2 | **充足** | 同 §9.1 の 2026-09-01 の記録の**本文は不変**で、その下に `- **Correction note (2026-09-19, …)**` の子 bullet。M-3 (NOINHERIT で効果無し)・`REVOKE` してよい・実行者は bootstrap `postgres`・D-2R は `pg_signal_backend` を使わない、の 4 点が入る |
| W2-3 | **充足** | 同 §10.7 lock 表の deprovision 行に、`GRANT <role> TO CURRENT_USER WITH INHERIT TRUE, SET FALSE` (stage (3)) と `ALTER DATABASE … WITH ALLOW_CONNECTIONS false` (stage (4)) を**足す形**で追記。既存の terminate / `DROP DATABASE` / `DROP ROLE` の記述は保持。前文の「lock の記述が無いコマンド」の列挙にも `ALTER DATABASE` が入った |
| W2-4 | **充足** | `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`:473-484 の guard の順序の説明 (「no live-connection pre-check, no temporary self-grant, no `ALLOW_CONNECTIONS` change, … all of which still run strictly after this guard, never before it」)、§14 branch (B) の 1 の段を pre-check → 一時付与 → `ALLOW_CONNECTIONS false` → 絞った terminate の順に書き直し、同じ段に失敗時状態の表 (2 行)、§5 の「being accessed by other users」段落に訂正註 (本文不変、2 原因併記・M-12 は 1 回の実測) |
| W2-5 | **充足** | `MitateDB-api/README.md`:187-198 が「deprovision (§9 item 3 -- the live-connection pre-check, temporary self-grant, `ALLOW_CONNECTIONS false`, and narrowed `pg_terminate_backend` … no longer a bare `pg_terminate_backend`/`pg_signal_backend` grant)」に。`r2db-api/tests/test_credential_persistence.py`:771-781 の docstring も同順序に |
| W2-6 | **充足** | `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md`:46・:249 に訂正註 1 行ずつ、`docs/design/CONFORMANCE_ADAPTER_V1.md`:2795-2802 に訂正註 1 段 (いずれも本文不変、`§1.8 の 56` を引く)。`*_HISTORY.md` と `conformance-tests/CONDITIONS.md` は差分に現れない |
| W2-7 | **充足 (監査照合)** | `check_doc_refs OK: 0 dangling references` / `# mode=tree files_scanned=6 total_flagged=0` (最終往復後に再実行、報告 3) |
| W2-8 | **充足** | `pt: 61 passed in 6.93s` (`r2db-api/tests/test_credential_persistence.py`)。最終往復後は同ファイルを再実行していないが、そのファイルの変更は docstring 5 行のみで、完了ゲートの `3745 passed` に含まれる |
| W2-9 | **充足** | 本表 9 行すべてに監査照合または実行記録が在る |
| (W2-1〜W2-6 の逐語記録) | **証拠不足** | §3.4 は「直した各箇所の `file:line` と直した後の文を**逐語で**報告に残す」を求めるが、実装報告 (`r54-wp2-report.md`・`-2`・`-3`) は**要旨**で、最終往復 (レビュー 2 回目の 2-1・2-2・2-3 の反映) は**報告ファイル自体が無い**。逐語の正本は作業コミット `42ebc2c` の差分で、監査は当該 6 ファイルの差分を全文読み、上の各行の判定はその現物に拠る。`docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md` §11 の監督裁定 A-2 と同じ扱い (git の差分を逐語の正本とする) を採るかは裁定事項 |

#### 5.2.3 WP-3 (`security/CONTROL_MAPPING.md`)

| # | 判定 | 証拠 |
|---|---|---|
| W3-1 | **充足 (監査照合)** | SI-00 / r2db-api / 既定に Control 4 本 + Status 2 本、SI-00 / MitateDB-api / 既定に Control 4 本 + Status 2 本。peer ごとに文面は別 (r2db = `r2dbsvc_control` が OWNER・`NOSUPERUSER`、Mitate = `mitatedbsvc_provision` が `NOINHERIT` ゆえ `INHERIT TRUE` が効く理由と ops の degrade 開示)。軸は Control / Evidence / Status の既定の並びを保ち、`- —` は触っていない |
| W3-2 | **充足** | 証拠は両 peer とも `absent` (r2db = production 未適用、Mitate = Cloud SQL 未実測 + 管理接続が事前検査に掛かるかも `absent`)。**証拠のテスト名と行番号は現物と全件一致** (監査で実測: r2db :377/:398/:424/:469/:530/:546、Mitate :1939/:1960/:1987/:2031/:2091/:2107)。`0004` の行参照も一致 (r2db 事前検査 :102-113・一時付与 :140-150・`ALTER DATABASE` :164-168、Mitate :96-107・:134-144・:158-162)。「predefined role の GRANT が 1 つも無い」「`pg_signal_backend` はコメントのみ」「r2db に `pg_read_all_stats` は出現 0」も grep で一致 |
| W3-3 | **充足 (監査照合、独立再測で一致)** | 登録テストの `_subblock_block_text` と同じ数え方で監査が再測: SI-00 / r2db-api 既定 **6,550** (残り 8,650)、SI-00 / MitateDB-api 既定 **6,210** (残り 8,990)、最長は SI-09 / MitateDB-api 既定 **14,229** (残り **971**、上限 15,200)。最長の物理行 1,384 (上限 1,400)。報告の数値と 1 字も違わない。**残り 2,000 字未満は SI-09 / MitateDB-api 既定の 1 件で、報告済み** |
| W3-4 | **充足** | `:5` の版数行が **2.10** に上がり、その版の変更 (SI-00 両 peer への追加、SI-09 の 2 本の訂正と履歴への移動) を述べている。累積していない |
| W3-5 | **充足 (監査照合)** | `missing=2 added=14 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical` (exit 0)。`subsequence=ok` / `ccr14=identical` / `rule=identical` を満たす。`missing=2` は監督裁定による SI-09 の 2 本の訂正 (旧文 2 本は `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ**逐語**で移動済み — 監査で削除行と履歴の行を 1 字ずつ照合して一致)。`preamble=differs` は版数行と測定文の書き換え |
| W3-6 | **充足** | `M8-cm-bullet-removed expect=green got=green OK \| 34 passed in 0.24s \| restore=ok`。足した bullet を 1 本外しても登録テストは緑 = 本 WP は振る舞いの変異を持たない、の記録 |
| W3-7 | **充足 (監査照合)** | `check_doc_refs OK: 0 dangling references` / `# mode=tree files_scanned=2 total_flagged=0` |
| W3-8 | **充足** | 本表 8 行すべてに監査照合または M8 が在る |

### 5.3 完了ゲートの集計行

監督がリポジトリルートで単独実行 (コミット前の同じ木)。**verbatim**:

```
gate: 3745 passed, 2 subtests passed in 314.99s (0:05:14)
gate: judge=PASS
gate: pg_database/pg_roles diff 0
gate: info=shared pg_database/pg_roles diff 0
gate_exit=0
```
log = `gate-r54-<日時>.log` (2026-09-19 19:27 の実行) (ログ本体の末尾も `3745 passed, 2 subtests passed in 314.99s (0:05:14)` と `== gate: pg_database / pg_roles diff (names sorted) ==` に続く `0`)。

- **合格条件 (§1.3 の 22・26) に対する判定: 充足。** 集計行に `failed` / `skipped` / `xfailed` / `xpassed` / `deselected` はいずれも現れない (= すべて 0)。`2 subtests passed` は passed の内訳。
- **§1.3 の 23: 充足。** `pg_database`/`pg_roles` の差分 0 (`gate.py` が両方を見る)。
- **件数の整合: 一致。** 直前の main が 3733、本変更セットが足したテストは 6 件 × 2 peer = 12 件、3733 + 12 = **3745**。
- 統合時 `finalize: tools/tests: 507 passed in 29.61s`、`finalize: check_doc_refs: check_doc_refs OK: 0 dangling references`。

### 5.4 変異表

#### 5.4.1 WP-1 の 12 件 (初回。`mutate.py` の出力 verbatim)

```
M1-r2db  expect=red   got=red       OK  | 1 failed in 5.46s | restore=ok
M2-r2db  expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M3-r2db  expect=red   got=red       OK  | 1 failed in 0.31s | restore=ok
M4-r2db  expect=red   got=red       OK  | 1 failed in 6.02s | restore=ok
M5-r2db  expect=red   got=red       OK  | 1 failed in 0.09s | restore=ok
M6-r2db  expect=red   got=red       OK  | 1 failed in 0.29s | restore=ok
M1-mitate expect=red   got=red       OK  | 1 failed in 5.47s | restore=ok
M2-mitate expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M3-mitate expect=red   got=red       OK  | 1 failed in 0.33s | restore=ok
M4-mitate expect=red   got=red       OK  | 1 failed in 5.45s | restore=ok
M5-mitate expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M6-mitate expect=red   got=red       OK  | 1 failed in 0.33s | restore=ok
mutate: 12 mutations, 12 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged (n/a for 8 edits whose lines all exist in the pristine file)
```
log = `mutate-<日時>/` (2026-09-19 08:28 の実行)。

#### 5.4.2 差し戻し後の再実行 (verbatim)

```
M2-r2db  expect=red   got=red       OK  | 1 failed in 0.10s | restore=ok
M5-r2db  expect=red   got=red       OK  | 1 failed in 0.09s | restore=ok
M2-mitate expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M5-mitate expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
mutate: 4 mutations, 4 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged (n/a for 2 edits whose lines all exist in the pristine file)
```
log = `mutate-<日時>/` (2026-09-19 09:28 の実行) (構造テストのコメント除去の強化の後)。

```
M3-r2db  expect=red   got=red       OK  | 1 failed in 0.32s | restore=ok
M3-mitate expect=red   got=red       OK  | 1 failed in 0.34s | restore=ok
mutate: 2 mutations, 2 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged
```
log = `mutate-<日時>/` (2026-09-19 19:10 の実行) (membership assert を先に動かした後)。

#### 5.4.3 WP-3 の M8 (verbatim)

```
M8-cm-bullet-removed expect=green got=green     OK  | 34 passed in 0.24s | restore=ok
mutate: 1 mutations, 1 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged (n/a for 1 edits whose lines all exist in the pristine file)
```
log = `mutate-<日時>/` (2026-09-19 19:19 の実行)。

#### 5.4.4 完了条件番号 → 変異 id → 赤になった test id

| 完了条件 | 変異 (操作) | 赤になった test id (両 peer) |
|---|---|---|
| W1-1 | M1-r2db / M1-mitate ((3) の `GRANT … WITH INHERIT TRUE, SET FALSE` の段を外す) | `…/tests/test_postgres.py::test_deprovision_succeeds_in_a_single_pass_with_a_live_runtime_role_connection` |
| W1-2 | M2-r2db / M2-mitate ((4) の `ALTER … ALLOW_CONNECTIONS false` の文を外す) | `::test_0004_allow_connections_false_is_between_the_temporary_grant_and_terminate` |
| W1-3 | M3-r2db / M3-mitate (`DROP ROLE IF EXISTS :"runtime_role"` を外す) | `::test_deprovision_leaves_no_role_or_executor_membership_behind` |
| W1-4 | M4-r2db / M4-mitate ((2) の事前検査の段を外す) | `::test_deprovision_pre_check_stops_and_changes_nothing_for_an_unrelated_connected_role` |
| W1-5 | M5-r2db / M5-mitate (`GRANT` から `, SET FALSE` を外す) | `::test_0004_temporary_grant_uses_inherit_true_set_false` |
| W1-6 | M6-r2db / M6-mitate ((4) の `pg_database` 存在検査を外す) | `::test_deprovision_completes_on_rerun_after_the_database_was_already_dropped` |
| W1-7〜W1-12 | 監査照合 (§5.2.1 に逐語記録) | — |
| W2-1〜W2-7・W2-9 | 監査照合 | — |
| W2-8 | M7 (変異ではなく実行の記録) | `pt: 61 passed in 6.93s` |
| W3-1〜W3-5・W3-7・W3-8 | 監査照合 | — |
| W3-6 | M8 (足した bullet を 1 本外しても緑) | `34 passed` (`conformance-tests/test_control_mapping_register.py`) |

**変異ログの監査側の独立確認**: WP-1 の 12 ログ + 再実行 6 ログはいずれも `collected 1 item` で、名指しのテストが `FAILED` と記録されている (1 項目 1 テスト、§1.5 の 8 を満たす)。M1 は両 peer とも `ERROR: database "…" is being accessed by other users`、M6 は `ERROR: database "…" does not exist` で、設計 §6.1 が予告した赤の理由と一致。**12 件の変異の `old` 文字列は統合後の現物にちょうど 1 回ずつ在る** (監査で実測) ので、変異の仕様は統合後の木にそのまま適用可能である。**`new` の文字列は統合後の現物に 1 件も無い** (§1.4 の 31 = 変異を含むコミットでないことの静的確認)。

### 5.5 レビュー指摘と対応

- **設計レビュー 2 回** (`review-r54-design.md`・`-2`): 設計 v1.0 に反映済み (F-1〜F-8、M-11 による FORCE 不採用、R-1〜R-7 の監督裁定。いずれも設計メモのローカルの族)。
- **WP-1 コードレビュー 1 回 + 差し戻し 3 往復**:
  - (c) 構造テストをコメント除去後のテキストに対する検索へ強化 → 現物で確認、M2・M5 再実行で赤。
  - 指摘 1 (membership assert が空振り) → assert の順序を入れ替え、M3 再実行で membership assert 自身が赤 (`:461` / `:2023`)。
  - 指摘 2 (「fails at or after its own `ALLOW_CONNECTIONS` stage」は射程が狭い) → 両 peer `0003` を「fails at or after its own temporary self-grant stage (D-2R stage (3))」に。現物で確認。
  - 指摘 3 (`deprovision_app` docstring が registry 行について事実と逆) → 差し替え済み。現物で確認。
  - 指摘 4 (H-1 の引用が実測と違う) → 「three open connections plus a client reconnecting every 0.1 s (four terminated in that run), with an autovacuum worker left alone」。両 peer の `0004` で確認。
  - 指摘 5 (migration の非存在 idiom の参照が偽) → r2db 側は `MitateDB-api/migrations/0013_role_statement_timeouts.sql` / `0014_role_connection_limits_rollout.sql`、Mitate 側は 0013/0014 に。現物で確認。
  - 指摘 6 (欠語) → 「without anything the temporary grant stage below adds (H-2)」。現物で確認。
  - 指摘 7 (再実行) → `pt: 300 passed in 32.30s`。
  - **未記録 (証拠不足)**: 指摘 1 の後段「完了条件 4 側の同 assert は M4 で `datallowconn` が先に赤になる構造で pin できない旨を報告に明記」が、実装報告のどこにも書かれていない。監査が現物で確認した限り指摘のとおりの構造 (W1-4 のテストは `datallowconn` の assert が membership の assert より前) で、テストの docstring にも pin の限界は書かれていない。
- **WP-2 独立レビュー 2 回** (`review-r54-wp2.md` A-1〜A-10・(b)①〜④、`review-r54-wp2-2.md`):
  - 1 回目の A-1・A-3〜A-9 と B-1〜B-4 は 2 回目のレビューが「解消」と判定。A-2 は監督裁定の内容 (2 原因併記・M-12 は 1 回の実測・(ii) は `usename` で持ち主特定) で反映、レビュー文案の断定は不採用。A-10 は WP-1 側で解消 (`0001` の allowlist)。
  - 2 回目の残り 3 件は、いずれも**統合後の現物で解消済み** (監査が差分で確認、報告ファイルは無い):
    - 2-1 (`cloudsqladmin` の列挙が自己矛盾) → runbook §9 項目 3 は「no runbook step, migration, configuration, or code in this repository **depends on** `cloudsqladmin`; every occurrence of the name is prose recording this same gap.」、`CONTROL_MAPPING.md` SI-00 / MitateDB / Status も「no control anywhere in this repository depends on `cloudsqladmin`; every occurrence of the name is prose recording this same evidence gap」。数える形は残っていない。
    - 2-2 (§5 と §14 で M-12 の強さが食い違う) → §14 の当該括弧が「the autovacuum-worker condition this note previously named is not the usual cause here … (M-12, a single measurement -- see §5's correction note for the two causes and why waiting is not free)」に。
    - 2-3 (stage (3) の 1 本目で落ちた場合) → §9 項目 3 の表 2 行目が「possibly neither, if the cancel hit the first `GRANT` -- then nothing changed, same as the row above」、§10.7 の Transaction 欄が「A failure after stage (3) (and after either `GRANT` that already succeeded -- a cancel on the first `GRANT` itself leaves nothing changed)」に。
  - **§10.7 の受理**: 2 回目のレビューの結論は「**accepted**」(内容判定)。版数の扱いは推奨 (版 5) と代替 (版 4 のまま + 記録欄に 1 行) の両論で、裁定は監督。現物は**版 4 のまま**で、§10.8 の行は次のとおり更新済み。

```
| §10.7 lock / stop time / `lock_timeout` | 4 | accepted | 4 | docs/work-orders/WORK_ORDER_R54_DEPROVISION_LIVE_CONNECTIONS_V1.md §5 | 2026-09-19 | supervisor |
```

- **WP-3 が報告した既存記述 3 件**: (1) `0001`:30-32 の矛盾 → WP-1 側で解消済み (現物確認)。(2) SI-09 の §10.7 版数の 2 行 → 監督裁定により本変更セットで訂正、旧文は履歴へ逐語。(3) runbook の `cloudsqladmin` の自己矛盾 → WP-2 側で解消済み。

### 5.6 主張と実測の突合 (§1.5 の 34・35 の独立項目)

- **一致を確認したもの**: `CONTROL_MAPPING.md` が引く 12 件のテスト名と行番号 (両 peer 6 件ずつ)、`0004` の 3 つの段の行番号 (両 peer)、「predefined role の GRANT は migration 集合に 0 件」「`pg_signal_backend` はコメントのみ」「r2db に `pg_read_all_stats` は 0 件」、字数 6,550 / 6,210 / 14,229 と残り 8,650 / 8,990 / 971、最長物理行 1,384、`3733 + 12 = 3745`、履歴へ移した旧文 2 本の逐語一致、変異 12 件の `old` が現物に各 1 回。
- **主張の弱め方が実測どおりのもの**: 証拠は両 peer とも `absent` (production / Cloud SQL 未実測)、F-3 の ops degrade は「read from `ops.py`, with no test of its own」と明記、M-12 は「a single measurement」と明記。設計 §7 の「本番には何も適用しない」と矛盾する記述は差分に無い。
- **依頼者確定の文言**: 本変更セットに依頼者確定の契約文・裁定文の写しは無い (契約 `spec/`・`security/SECURITY_INVARIANTS_V1.md`・`conformance-tests/` の本文は差分に現れない)。したがって §1.5 の 35 の逐語 pin の対象は生じていない。
- **公開リポジトリ規律 (§1.9、§2 の 15)**: 追加行に実 credential・実ホスト名・実 DSN・作業機の絶対パス・一時領域への参照・traceback は 0 件 (合成の `<slug>` / `<application database>` / `example.invalid` 相当のみ)。追跡中の `.md` の 0 バイト化も 0 件。`public_value_scan` は 3 回とも `total_flagged=0`。

### 5.7 未解決事項 (監査が挙げたもの。裁定は §5.8)

1. **作業指示書 §5 が空のままでは、`MitateDB-api/docs/cloud-run-cloud-sql.md` §10.8 の §10.7 の行が指す「Where the review is recorded」が実体を持たない。** 同ブロックの主張自身が「§10.8 is the single place that state is read from」と言うので、§5 に (a) 独立レビューの結論 accepted、(b) 監督が版 4 のままとした裁定、(c) レビュー代替案が求めた「版 4 は独立レビューの差し戻しを 1 回経て確定した」旨、を書いて初めて記録が閉じる。`security/CONTROL_MAPPING.md` の SI-09 / Evidence も同じ §5 を指している。
2. **SI-09 / MitateDB-api 既定の残りが 971 字** (上限 15,200 に対し 14,229)。ファイル中で唯一 2,000 字を割っており、本変更セットでさらに 484 字増えた。台帳 R-59 の対象 (監督裁定として既出)。名前付き小ブロックはこの (SI, peer) に 0 本 (上限 3) なので分割の余地は残る。
3. **`conformance-tests/COLLECTION_FLOOR` は `3326` のまま** (実測 3745)。floor なので赤にはならず、更新は §1.3 の 25 により監督の別コミット。監督裁定として「更新していない」が既出。
4. **WP-2 の逐語記録**が報告に無く、正本がコミット差分である (§5.2.2 の最終行)。`docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md` §11 の A-2 と同じ扱いにするかは裁定事項。
5. **レビュー指摘 1 の後段**(W1-4 側の membership assert が M4 では pin されない旨の明記) が報告にも docstring にも無い (§5.5 の「未記録」)。
6. **r2db runbook §14 branch (B) の失敗時表は 2 行**で、設計 §4.1 の 3 行目 (`DROP DATABASE` の後 `DROP ROLE` の前) に当たる状態は表に無い。branch (B) の手順自身がその状態からの復旧手順であるためと読めるが、MitateDB 側の表 (4 行) と非対称である。
7. **`MitateDB-api/migrations/0001_bootstrap_platform.sql`:176-181 相当の同型の全称文**は監督裁定どおり不触 (主語が bootstrap admin で射程が別)。残置していることの記録。
8. **M1 / M4 / M6 の赤は、差し戻し 3 回目のコメント訂正より前の木で実測されたもの**である (M2・M5 は 2 回目の後、M3 は 3 回目の後に再実行)。3 回目の `0004` への変更はコメントのみ (非コメント変更行 0 を差分で実測) で、12 件の `old` は統合後の現物に各 1 回在るため、有効性は保たれると判断した。再実行の要否は裁定事項。
9. `security/CONTROL_MAPPING_HISTORY.md` の追記位置に区切り `---` が 2 つ連続している (既存の区切りの直後に新しい区切りを足したため)。登録テストは緑で、意味上の影響は無い。

### 5.8 監督裁定 (2026-09-19、受け入れ監査パケットに対して。逐語)

- A-1 (WP-2 の逐語記録が報告に無い): 逐語の正本はコミット `42ebc2c` の差分とする。監査が当該 6 ファイルの差分を全文読んで各完了条件を現物で確認したことをもって充足と扱う (R-52 の作業指示書 §11 の A-2 と同じ扱い)。以後、文書 WP の発注には「最終の往復も報告ファイルに残す」を入れる。
- A-2 (完了条件 4 のテストの membership assert は M4 で pin できない): 事実として記録する。M4 (事前検査を外す) では同じテストの `datallowconn` の assert が先に赤になる構造であり、membership の assert はその後ろの副次の観測である。membership の 0 件 assert が空振りでないことは、完了条件 3 のテストで M3 が membership assert の行 (r2db :461 / MitateDB :2023、レビュー時点) で赤になることで示している。追加の変異は置かない。

#### 5.8.1 runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.7 (表 版 4) の受理記録 — 裁定 A-3

**本小節が、同 runbook §10.8 の §10.7 の行が「Where the review is recorded」として指す受理記録の本文である。** 裁定 A-3 の逐語:

- A-3 (runbook §10.8 の参照先): §10.7 の版は 4 のままとする。版 4 は一度もコミットも受理もされないまま、独立レビューの差し戻しを 1 回経て確定した (1 回目 not accepted の 4 点を反映 → 2 回目の結論 accepted、[低] の追記 1 行は同じ往復で反映)。§10.8 の `Version reviewed` 4 は、その最終の内容を読んだ独立レビューの結論を指す。受理の記録の本文は本節である。

#### 5.8.2 裁定 A-4〜A-8

- A-4 (M1 / M4 / M6 の赤が最後のコメント訂正より前の木での実測): 統合後の木 (main `a586a17`) で 12 変異を全部再実行した。結果は本節に貼る。

統合後の木 (main `a586a17`) での 12 変異の再実行 (`mutate.py` の出力 verbatim):

```
M1-r2db  expect=red   got=red       OK  | 1 failed in 5.47s | restore=ok
M2-r2db  expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M3-r2db  expect=red   got=red       OK  | 1 failed in 0.35s | restore=ok
M4-r2db  expect=red   got=red       OK  | 1 failed in 6.16s | restore=ok
M5-r2db  expect=red   got=red       OK  | 1 failed in 0.09s | restore=ok
M6-r2db  expect=red   got=red       OK  | 1 failed in 0.30s | restore=ok
M1-mitate expect=red   got=red       OK  | 1 failed in 5.48s | restore=ok
M2-mitate expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M3-mitate expect=red   got=red       OK  | 1 failed in 0.44s | restore=ok
M4-mitate expect=red   got=red       OK  | 1 failed in 5.46s | restore=ok
M5-mitate expect=red   got=red       OK  | 1 failed in 0.08s | restore=ok
M6-mitate expect=red   got=red       OK  | 1 failed in 0.34s | restore=ok
mutate: 12 mutations, 12 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged (n/a for 8 edits whose lines all exist in the pristine file)
exit=0
```
log = `mutate-<日時>/` (2026-09-19 19:44 の実行)。これにより §5.7 の 8 は解消した (12 件とも統合後の木で期待どおり赤)。

- A-5 (r2db runbook §14 の失敗時の表が 2 行で MitateDB 側は 4 行): 変えない。r2db の表は手で行う残骸掃除の手順の途中の状態を扱い、r2db には `ops deprovision` が無いので `--lock-timeout` の行が無く、「`DROP DATABASE` の後・`DROP ROLE` の前」はその手順自身の次の段である。
- A-6 (SI-09 / MitateDB-api の既定の小ブロックの残り 971 字): 既存の台帳 R-59 の対象。R-59 行に実測値の更新を【追記】する。
- A-7 (`conformance-tests/COLLECTION_FLOOR` 3326 のまま): 本件では上げない (floor は下限であり、3745 は floor を満たす)。
- A-8 (Cloud SQL での証拠): `absent`。本番には何も適用していない。runbook §9 の新しい項目 3 が実測の場。2026-09-01 に付与された `pg_signal_backend` の membership は効果を持たず不要 (REVOKE は bootstrap の `postgres` が行う。runbook §9.1 の訂正註)。

### 5.9 最終判定 (逐語)

最終判定: R-54 の WP-1〜WP-3 を受け入れる。台帳の R-54 行は閉じる (Cloud SQL での実測は runbook §9 の未実行項目として残り、R-54 の範囲ではない)。
