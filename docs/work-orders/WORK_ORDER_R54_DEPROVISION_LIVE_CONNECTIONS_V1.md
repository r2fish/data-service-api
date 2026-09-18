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

## 5. 受け入れ監査と監督裁定
