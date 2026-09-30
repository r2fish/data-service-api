# 作業指示書 — R-115 worker process の突然死による audit の欠落 (Change Set Manifest)

## 0. 版数・位置づけ

- **v1.0 (2026-09-30)。** 起草。基点 local main `f14f305` (契約 1.12.0、`CM` 3.10)。未発注・未 commit。
- worktree `.claude/worktrees/mystifying-hellman-56a270` (branch `claude/mystifying-hellman-56a270`)、本書では `$WT` (main checkout からの相対)。1 worktree・1 branch で WP を直列に進め、WP ごとに監督が branch へ commit し、main への merge は全 WP の後に 1 回 (申告と実挙動を同時に動かす。`OC` §1.1 の 11)。並行 WP は無いので、触るファイルの重なりの表は置かない。
- 台帳 `RM` §8.1 の **R-115**。**規模 M** (`OC` §1.13 の 74)。**変更クラス D** (`security/CONTROL_MAPPING.md` と `_ISOMORPHIC_TARGETS` 集合の増減に触れる。`RM` §9 の 8)。D の証拠: C の全部 + 依頼者裁定の逐語 (§1.2) + 版付きの security-contract 決定 (契約 1.13.0 と `CM` の版上げ)。
- 設計の正本は `docs/design/AUDIT_PROCESS_LOSS_V0_1.md` v0.5 (以下「設計」。確定)。本書は設計の決定・却下案・背景を写さず節番号で指す (`RM` §9 の 9)。逐語は §1.2 の依頼者裁定と、`$SP/confirmed-process-loss-policy.txt` から複製する契約の確定文 (`OC` §1.5 の 35) だけ。
- 番号: 完了条件は全 WP の通し番号。変異は **M<完了条件番号>** (`expect=red`)。変異の無い完了条件は「監査照合」とし、照合対象の逐語 (コマンドと出力、`file:line`、`git diff`) を設計に残すことを完了条件とする (`OC` §1.5 の 40)。実装担当は報告に逐語を貼る。

**略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`ROLES` = `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`、`CM` = `security/CONTROL_MAPPING.md`、`CR` = `MitateDB-api/docs/cloud-run-cloud-sql.md`、`PR` = `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`R` = `r2db-api/src/r2db_api`、`M` = `MitateDB-api/src/mitatedb_api`、`RT` = `r2db-api/tests`、`MT` = `MitateDB-api/tests`、`CT` = `conformance-tests`、`$SP` = 監督が発注時に渡す scratchpad。

## 1. 枠

### 1.1 問題設定・守るべき条件・決定・却下案

- 問題設定と事実: 設計 §1・§2 (§2 の 1〜12)。実測: 設計 §3。
- 決定: 決定 1 = **1-A (i)** (設計 §4)、決定 2 = **2-A** (設計 §5)、契約に `audit.process_loss_policy` を足す (設計 §6、1.13.0)、範囲に設計 §2 の 11 と 12 を含める (設計 §10 の Q-5)。
- 却下・不採用: 1-A'・1-B・1-C・1-D・2-B・2-A'・2-C・M (設計 §4・§5)。蒸し返さない。K=4 の lock 待ちが閾値を超えても 1-A' に切り替えず依頼者へ上げる (設計 §8)。

### 1.2 依頼者裁定 (逐語。設計 §0 と §10 から複製。再審議しない、`OC` §1.7 の 51)

(1) 着手の裁定 (設計 §0):

監督の問い 2「R-115 に着手するか。着手する場合、Class D の見込みで進めてよいか」に対し (2026-09-30):
「1は(i)、2は着手、Dで進めてください、別セッションで。」
(「1は(i)」は別件 R-114 への回答で、本件には当たらない。)

(2) 設計の裁定 (設計 §10):

**依頼者裁定 (逐語、2026-09-30)**: 監督が Q-1 / Q-2 (event の扱い)、Q-3 (拒否の件数)、Q-4 (契約)、Q-5 (範囲) をそれぞれ監督案付きで問うたのに対し:
「すべて監督案どおりで進めてください」

確定: Q-1 = 1-A、Q-2 = (i)、Q-3 = 2-A、Q-4 = 契約に足す (§6 の文案を確定文言とする。版は merge 時の main の次の版。host / instance の消失は文に含めない)、Q-5 = §2 の 11 と 12 の 2 件を同じ変更セットに含める。以下は問いの原文である。

### 1.3 本書の時点で未確定 (監督が発注前に確定する)

1. 契約の `versioning.version_binding` の 1.13.0 段落、`versioning.obligations` の 1.13.0 の項目、`spec/CCR_DISPOSITION.md` の subordinate ruling の文言 (確定文ファイルにあるのは `process_loss_policy` の文だけ)。
2. 設計 §8 の測り方のうち道具に口の無いもの: `tools/perf_baseline.py --real-server` は op=query だけを測る (実物)。real-server の op=mutate、未認証 flood 下の正規 tenant、MitateDB の K=4 の waits/acquire の取り方。

## 2. 順序・役割・道具

### 2.1 順序

**WP-1** (契約) → **WP-2** (conformance。新条件は現行実装に対して赤) → **WP-3** (MitateDB の sink の pool 化) → **WP-4** (決定 1) → **WP-5** (決定 2) → **WP-6** (記録) → 監督の完了ゲート・受け入れ監査・merge。WP-4 と WP-5 は同じ module を触るので直列 (設計 §9)。

### 2.2 役割と実装担当への制約

- **実装担当** (`ROLES` の 2): WP-1〜WP-5 に 1 起動ずつ (差し戻しは別起動)。穴は 担当 worktree = `$WT`、作業指示書 = 本書の該当 WP の節、正本設計 = 各 WP の「読むべき正本」、タスク = 完了条件と変異の表、テスト / 変異 = §2.3。
- **制約** (全 WP): 下請けの Agent を起動しない (`OC` §1.7 の 47)。commit・merge・push・branch 操作・`git stash` をしない (`OC` §1.1 の 2)。例外は新規 file の `git add -N` だけ。pytest を直接走らせず §2.3 の道具を前景直列で使う (`OC` §1.5 の 39)。suite 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` を実行しない (`OC` §1.11 の 70)。設計に無い検査・機構は実装前に報告する (`OC` §1.5 の 37)。触ってよいパスの外の赤は直さず報告する。一時ファイルは `$SP` 配下、複数手順は `$SP` の bash 3.2 互換スクリプト。報告は `$SP/r115-wp<N>-report.md` (道具の出力行をそのまま貼る。`OC` §1.10 の 65)。本番には何も適用しない。port 8000 / 8001 の uvicorn は別 repo の常設 service なので止めない。
- **コードレビュー** (`ROLES` の 5、`reviewer`、Class D): WP-1〜WP-5 の各 WP の後に 1 回ずつ。観点は各 WP の「レビューの観点」と空振り (`OC` §1.5 の 32)・代理指標 (`OC` §1.7 の 52)。
- **受け入れ監査** (`ROLES` の 6、`evidence-auditor`): 全 WP の後に 1 回 (Class D)。
- **監督**: WP ごとの branch への commit、WP-6 (実装担当を起動しない。起草担当に渡してよい)、完了ゲート、`COLLECTION_FLOOR` の更新、指摘の 1 件ごとの裁定 (`OC` §1.15 の 77)、local main への merge 1 回。push は停止中 (`OC` §2 の 20)。

### 2.3 道具の引数

`$SP` を export し、main checkout を cwd にして `-C $WT` で worktree を指す (渡し忘れると main を測る)。Bash の timeout 600000、前景。

```bash
tools/dev/pt.py -C .claude/worktrees/mystifying-hellman-56a270 -- <path> -q
tools/dev/mutate.py "$SP/r115-wp<N>-mutations.json" -C .claude/worktrees/mystifying-hellman-56a270
```

- 変異は 1 変異 1 entry、`-x` を使わない。各 entry の test id はその完了条件のテスト 1 件だけ (`mutate.py` は最初の失敗で止まる)。`-k` の id は `--collect-only -q` で確かめる。`old` / `new` は実装担当が書き、報告に表で残す。REFUSED (75) は迂回しない (`OC` §1.10 の 66)。
- worktree を cwd にして: `python3 tools/check_comment_provenance.py --base f14f305 <触った src>`、`python3 tools/check_comment_provenance.py --register`、`python3 tools/change_class.py <触った全パス>`、`python3 tools/check_doc_refs.py`、`python3 tools/public_value_scan.py <触った全パス>`。
- `tools/tests` に触れた WP は、新規 file を `git add -N` した後に `tools/dev/pt.py -C $WT -- tools/tests -q` を別に回す (根の gate は `tools/tests` を含まない)。

### 2.4 コメントの経緯 (provenance)

新しい src のコメント・docstring は現在形で書き、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §4.1 (5) の語 (WP-・Phase・review・日付ほか) とフェーズ / WP / 台帳 ID の語を入れない。`--base` は (5) の 0 件と `--register` の OK を読む。登録済みの塊 (`# history: CH-NNNN` を持つもの) を言い換えるときは同設計 §9.3 のとおり同じ変更セットで `docs/code-history/` に訂正を追記する。buffer・coalescer の削除で CH-ID を持つ塊がコードごと消えると、受け皿の節が同設計 §4.2 の 1 の孤児になる。その扱いは同設計に定めが無いので、該当が出たら実装前に報告する (`OC` §1.5 の 37)。

## 3. WP-1 — 契約 1.13.0 (実装担当)

**目的**: 設計 §6 の契約の部。`audit.process_loss_policy` を確定文で足し、版を 1.13.0 にし、両 peer の宣言と版のピンを追随させる。
**読むべき正本**: 設計 §1・§6・§10。直近の契約版上げの変更セット `git show --stat e21922a` (新 key と `version_binding` / `obligations` を足した形) と `git show --stat c86a871` (1.12.0 の版の追随)。**クラス**: C。**テンプレート**: `ROLES` の 2。

### 3.1 触ってよいパス

- `spec/data-service-api.v1.json`、`r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` (3 つを byte 一致に)
- `spec/OPERATION_CATALOG.json` と両 peer の `contract/OPERATION_CATALOG.json` (`python3 tools/contract_catalog.py` で再生成。引数なしで書き込むので `--check` と区別する)
- `spec/CONTRACT_HISTORY.md`、`spec/CCR_DISPOSITION.md`、`spec/README.md` (`spec/CONTRACT_HISTORY_MANIFEST.json` は register が要求するときだけ)
- `R/capabilities_document.py`、`R/control_plane.py`、`M/capabilities_document.py`、`M/control_plane.py` (data と control の両面で 1.13.0。C-19)
- 版のピン: `RT/test_foundation.py`、`RT/test_control_plane_service.py`、`RT/test_audit_query.py`、`RT/test_denial_details_and_request_id.py`、`MT/test_control_plane_service.py`、`MT/test_audit_query.py`、`MT/test_denial_details_and_request_id.py`、`MT/test_http.py`
- `CT/test_contract.py` (1.13.0 のピン、確定文の逐語ピン、1.12.0 のピンの右端 = `CT/test_contract.py`:746-767 の追随)、`CT/test_contract_history_register.py`
- `docs/code-history/` (§2.4 の訂正の追記だけ)、`RM` §0.1.1 の G-2 / G-3 行の版 (1.12.0 → 1.13.0) だけ
- 基点で `1.12.0` を含む追跡ファイルは `git grep -l '1\.12\.0' -- ':!docs/archive' ':!docs/code-history'` で実測する (設計・作業指示書・引き継ぎ書の記録は書き換えない)。

### 3.2 完了条件 (1〜12) → 変異

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | `audit.process_loss_policy` の値が `$SP/confirmed-process-loss-policy.txt` の本文 (末尾改行を除く) と逐語一致し、`CT/test_contract.py` の文字列ピンがそれを assert する | 契約の文の `neither` を `not` に |
| 2 | 3 つの契約の `contract_version` が 1.13.0 で、版のピンが 1.13.0 を assert する | spec の `contract_version` を 1.12.0 に戻す |
| 3 | 3 つの契約が byte 一致 (`test_contract_packaged_copies_are_byte_identical`) | r2db の同梱の写しの policy 文に 1 文字足す |
| 4 | `versioning.version_binding` に 1.13.0 の段落、`versioning.obligations` の末尾 (基点で index 10) に version 1.13.0 の項目があり、両方を逐語ピンが assert する (文言は §1.3 の 1) | obligations の 1.13.0 の項目の `unconditional` を空に |
| 5 | 1.12.0 の段落のピンの右端が 1.13.0 の段落の始まりに追随する | 1.13.0 の段落の直前に 1 語足す |
| 6 | OPERATION_CATALOG の 3 つの写しが再生成済みで `python3 tools/contract_catalog.py --check` が up to date | 同梱の OPERATION_CATALOG の `contract_version` を 1.12.0 に |
| 7 | 両 peer が data・control の両面で 1.13.0 を宣言する | `M/control_plane.py` の宣言を 1.12.0 に |
| 8 | `spec/CONTRACT_HISTORY.md` の Revision note が register を通る (`CT/test_contract_history_register.py` 緑) | 監査照合 (集計行の逐語) |
| 9 | `spec/CCR_DISPOSITION.md` に §1.2 の裁定の逐語を持つ subordinate ruling (基点の最後は 17)、`spec/README.md` に 1.13.0 の段落 | 監査照合 (`git diff`) |
| 10 | `RM` §0.1.1 の G-2 / G-3 行の版が 1.13.0 | 監査照合 (`git diff`) |
| 11 | `pt.py -- CT/test_contract.py CT/test_contract_history_register.py CT/test_operation_catalog_register.py -q` と、上の版のピンの 8 file の `pt.py` が failed 0・skipped 0 | 監査照合 (集計行の逐語) |
| 12 | 本表に対応の無い行が無い | 監査照合 |

### 3.3 レビューの観点

確定文の言い換えが無いこと (§1.5 の 35)。「1.13.0 or higher」の限定で 1.12.0 以下の `sink_failure_policy` の MAY が遡って狭まらないこと (設計 §6 の版の束ね方)。版の追随の漏れ (`git grep` の実測)。

## 4. WP-2 — launcher の helper と新条件 (実装担当)

**目的**: 設計 §6 の共通条件と §7。新条件は現行実装に対して **赤** であることを実行で確かめる (設計 §6 の変異の註)。赤のまま branch に commit してよい (main には入らない)。
**読むべき正本**: 設計 §2 の 7・8、§6、§7。`CT/test_c32_shared_limits.py` (workers=2 の launcher の使い方)。**クラス**: D (`_ISOMORPHIC_TARGETS` 集合の増減)。**テンプレート**: `ROLES` の 2。

### 4.1 触ってよいパス

- `r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py` (worker の pid 一覧、指定 pid への SIGKILL と置き換え待ち、短い窓での起動の口 (platform の宣言 `audit_coalescing_window_ms` を数秒)、窓の長さを返す口)。両方に同名で置く。
- `CT/socket_harness.py` (`_pids_with_pgid` の利用に要るときだけ)、`CT/test_socket_harness.py`
- `CT/test_c<NN>_<name>.py` (新規。本書の「新条件」。番号 NN は基点の最後 C-32 の次)、`CT/CONDITIONS.md` (新条件の行)、`CT/CONDITIONS_HISTORY.md` (新条件の節)、`CT/test_conditions_register.py` (要るときだけ)。`CT/registry.json` は `composition_roots` が既に両 peer を持つので、変える必要が出たら報告する。
- 同型性: `RT/test_audit_query.py` と `MT/test_audit_query.py` の `_ISOMORPHIC_TARGETS` に新 helper の行、件数ピン `test_isomorphic_target_table_is_pinned_to_its_current_198_rows` の改名 (実測の行数)、表の自己参照行と pin 本体の表の写し (`OC` §1.5 の 40b)。`CM`:867 がこの pin 名を引くので、WP-6 まで `CT/test_control_mapping_register.py` が赤になりうる (WP-6 で追随)。
- これ以外は 0 件。特に両 peer の `src/` と `conformance_adapter_*.py` を触らない。

### 4.2 完了条件 (13〜24) → 変異

新条件の本体に掛かる変異 (M16・M17) は、新条件が緑になった後 (WP-5 の後) に走らせ、WP-5 の報告に表で残す。13〜15 の試験が WP-2 の時点で緑でないなら、その変異も同じく WP-5 の後に走らせる。

| # | 完了条件 | 変異 |
|---|---|---|
| 13 | pid 一覧の helper が workers=2 の起動で worker 2 本を返し、supervisor と補助 process (spawn の resource_tracker 等。実挙動を最初に実測して報告) を含まない | 除外から supervisor を外す |
| 14 | SIGKILL の helper の後、kill した pid が `ProcessLookupError` になり、supervisor が置き換えた新しい pid が要求に応答する | 置き換え待ちを省く (kill 直後に返す) |
| 15 | 短い窓の口で起動した launcher で、served の `coalescing_window_ms` が口に渡した値と一致する | 起動の口が宣言を書かない (既定 60000 のまま) |
| 16 | 新条件は成功 N 件と同じ key の拒否 M 件 (M ≥ workers + 1) を送り、N + M ≤ `requests_per_minute` の guard と、access log の pid から「ある worker が 2 件以上の拒否を処理した」ことを assert する (設計 §6 の 1) | テストの M を 1 に (guard が赤) |
| 17 | 新条件は最後の応答の直後に全 worker を SIGKILL し、kill と置き換えを assert する (設計 §6 の 2) | kill の対象を worker 1 本に |
| 18 | 新条件は `audit_query` を actor_id で絞り、N 件の request_id と拒否の合計 M を、窓の長さ + `visibility_lag_ms` + 余裕の上限まで poll して assert し、固定の sleep を持たない (設計 §6 の 3) | 監査照合 (`grep -n 'sleep' CT/test_c<NN>_*.py` の逐語と poll の上限の `file:line`) |
| 19 | request_id の欠けと合計 < M の 2 つの赤を 1 回の実行で観測できる形 (assert を別の test に分ける等) で、**現行実装に対して両 composition root で両方が赤**。周期 flush が kill に間に合って緑になるなら、最後の応答から kill までを周期より十分短く保つ guard を足す (設計 §6 の G3) | 監査照合 (`pt.py` の集計行と 2 つの失敗の message 行の逐語) |
| 20 | 新 helper が両 peer の `_ISOMORPHIC_TARGETS` に在り、件数ピンが実測の行数 | r2db の新 helper の本体に正規化で消えない 1 行差を入れる |
| 21 | 新条件の CONDITIONS 行と CONDITIONS_HISTORY の節が register を通る | 監査照合 (`pt.py -- CT/test_conditions_register.py -q` の集計行) |
| 22 | 新しい試験に skip / xfail が無い | 監査照合 (`git grep` の出力の逐語) |
| 23 | 新条件の 1 peer あたりの所要時間 (設計 §6 の見込み 15 s 前後) | 監査照合 (`--durations` の行の逐語) |
| 24 | 本表に対応の無い行が無い | 監査照合 |

### 4.3 レビューの観点

空振り (§1.5 の 32): M の下限、worker の分散の assert、kill が本当に worker に当たったこと。孤児掃除 (R-113 の設計 `docs/design/MULTI_PROCESS_WORKER_V0_1.md` §10 の裁定 19) との両立。launcher の `_data_env` が ambient env を取り除くこと (設計 §2 の 8) に口が依存していないこと。

## 5. WP-3 — MitateDB の durable audit sink の pool 化と実測 (実装担当)

**目的**: 設計 §3 の読みと §8。`M/application_audit.py` の `PostgresApplicationAuditSink` を呼び出しごとの新規接続から pool に移し、接続予算 (F-16 の床) に本数を足す。前後を測る。
**読むべき正本**: 設計 §2 の 6、§3、§8、§11 の 2。**クラス**: B の見込み (`change_class.py` の実測を報告)。**テンプレート**: `ROLES` の 2。

### 5.1 触ってよいパス

- `M/application_audit.py`、`M/main.py` (配線)、`M/config.py`・`M/pool.py` (本数と pool の実装に要るときだけ)
- F-16 の床への波及 (基点の実物): `M/platform_declarations.py` (`check_role_connection_limits` の api の class の床、`_API_ROLE_STORE_COUNT`)、`M/ops.py` (`verify-declarations` の F-16 と inventory の床の項、基点 `M/ops.py`:2582 付近)、`M/startup_checks.py` (`ops startup-checks` の G3 の床と、指紋の表。`M/platform_declarations.py`・`M/config.py`・`M/main.py` を変えると作業木の組が表の行から外れる)
- `MT/test_application_audit.py`、`MT/test_main.py`、`MT/test_ops_startup_checks.py`、`MT/test_ops_inventory.py`、F-16 の床を assert する既存テスト (`git grep -l 'F-16' -- MitateDB-api/tests` で実測)
- 世代表の扱い (G3 の式を変えるか、新しい世代を足すか) は設計に無いので、実装前に報告する (`OC` §1.5 の 37)。`CR` は触らない (WP-6)。

### 5.2 完了条件 (25〜32) → 変異

| # | 完了条件 | 変異 |
|---|---|---|
| 25 | 前の実測: `tools/perf_baseline.py --real-server MitateDB-api --warmup 20 --n 200` を交互 3 巡、load average 付きで記録 (設計 §3 の手順) | 監査照合 (REALPERF 行の逐語) |
| 26 | sink の書き込みが pool の接続を使い、連続する書き込みで接続を新規に開かない | 呼び出しごとの新規接続に戻す |
| 27 | pool の本数を超える同時の書き込みが失われず、行が全件在る | pool の取得の待ちを外す (取れないときに捨てる) |
| 28 | F-16 の api の class の床が pool の本数を含み、床 / 床 − 1 の境界で判定が変わる | 床から sink の本数を外す |
| 29 | `ops startup-checks` と inventory の床が 28 の床と一致し、`MT/test_ops_startup_checks.py` と `MT/test_ops_inventory.py` が緑 | 道具の G3 の床から sink の本数を外す |
| 30 | pre_commit・error 行・最初の 1 件の書き込みが互いに transaction を共有しない (既存の `MT/test_application_audit.py` が緑) | 監査照合 (集計行の逐語) |
| 31 | 後の実測を 25 と同じ条件で交互 3 巡記録し、閾値 (`RM` §0.1.4 の 1) との比較を書く。超えたら監督へ上げる | 監査照合 (REALPERF 行の逐語) |
| 32 | 本表に対応の無い行が無い | 監査照合 |

### 5.3 レビューの観点

pool の本数と F-16 の床の算式が同じ値から導かれること。worker ごとの接続予算の増分。fresh 接続の前提で書かれたコメント (D-4 の「flush は fail-closed の書き込みと transaction を共有しない」) の真偽。

## 6. WP-4 — 決定 1 (両 peer。実装担当)

**目的**: 設計 §4 の 1-A (i) の全項目と §2 の 11・12。
**読むべき正本**: 設計 §2 の 1・2・11・12、§4、§9 の表の WP-4 の行。**クラス**: C (`CT/` に触れる)。**テンプレート**: `ROLES` の 2。

### 6.1 触ってよいパス

設計 §9 の表の WP-4 の path と、基点で buffer・flush・overflow・knob を参照するファイル (`git grep -l -E 'flush_audit_buffer|_AuditBuffer|AUDIT_BUFFER|AUDIT_FLUSH|overflow' -- ':!docs'` の実測):

- r2db: `R/service.py`、`R/main.py`、`R/postgres.py` (pre_commit の位置、COMMIT の `QueryCanceled` の分岐)、`R/audit_query.py`、`R/audit_counts.py`、`R/credential_store.py` (`append_many` の docstring)、`R/control_plane.py` (`outcome_note` が実挙動と食い違うときだけ)、`r2db-api/deploy/env/api.env.example` (knob の段、基点 :160-170)
- MitateDB: `M/application_audit.py`、`M/audit_dispatch.py`、`M/cell.py`、`M/main.py`
- テスト: `RT/test_application_audit.py`、`RT/test_audit_query.py`、`RT/test_credential_persistence.py`、`RT/test_dry_run_and_plan.py`、`RT/test_postgres.py`、`MT/test_application_audit.py`、`MT/test_main.py`、`MT/test_audit_query.py`
- conformance: `CT/adapter.py` (`flush_audit_buffer` の no-op 化と docstring)、`CT/absence.py`、`CT/test_c09_audit_evidence.py`、`CT/test_c25_result_request_id.py`、`CT/test_c27_concurrent_same_key.py`、`CT/CONDITIONS.md` (C-09 行の port の記述だけ)、両 peer の `conformance/conformance_adapter_*.py`
- `docs/code-history/` (§2.4)。runbook と `CM` は触らない (WP-6)。

### 6.2 完了条件 (33〜49) → 変異

| # | 完了条件 | 変異 |
|---|---|---|
| 33 | 着手時に、r2db の COMMIT 自体が `QueryCanceled` として上がるかを実行で確かめて記録する | 監査照合 (実行コマンドと出力の逐語) |
| 34 | 着手時に、r2db の schema の replay が durable にも buffer にも入らないこと (設計 §2 の 12) を実行で確かめて記録する | 監査照合 (同上) |
| 35 | 両 peer で非 destructive の mutate の allow 行が data commit の前に commit される | pre_commit の呼び出しを destructive に限る条件に戻す (peer ごとに 1 entry) |
| 36 | 両 peer で query / catalog の event が応答の前に sink に在る | query の event の書き込みを応答の後に回す |
| 37 | 新条件の request_id の assert が両 composition root で緑 | 設計 §6 の変異 (1): 通常 event の同期の書き込みを外す |
| 38 | 両 peer で mutate の replay の event が応答の前に sink に在る | replay の event の書き込みを外す |
| 39 | sink の書き込みの失敗で通常の操作が 503 (fail-closed) になり、event を保持しない | 失敗を握りつぶして 200 を返す |
| 40 | buffer・overflow alert・周期 flush の thread・lifespan の最終 flush・knob (`R2DB_AUDIT_BUFFER_CAPACITY`・`R2DB_AUDIT_FLUSH_INTERVAL_S`・`MITATEDB_AUDIT_BUFFER_CAPACITY`・`MITATEDB_AUDIT_FLUSH_INTERVAL_S`) が両 peer の `src/` と env 例から消えている | 監査照合 (`git grep` の出力の逐語) |
| 41 | r2db の pre_commit が `_idempotency_store` の後、transaction の最後の文にあり、その後の失敗は error 行を書く | pre_commit を `_idempotency_store` の前に戻す |
| 42 | 33 で COMMIT の `QueryCanceled` が起こるなら、413 の分岐も `hook_fired` のとき error 行を書き、応答は 413 のまま | その分岐の error 行を外す (起こらないなら監査照合: 33 の記録) |
| 43 | 両 peer の語彙の等式テスト (`RT/test_audit_query.py::test_declared_event_classes_cover_every_emittable_class`、`MT/test_audit_query.py::test_declared_operations_cover_every_emittable_operation` ほか) が「宣言するが今は出さない語」の明示の集合を持ち、緑 | 集合から 1 語外す |
| 44 | 34 が事実なら、r2db の schema の replay が MitateDB (`write_replayed_fail_closed_event`) と同じく同期に書かれる | その書き込みを外す (事実でないなら監査照合: 34 の記録) |
| 45 | `append_many` の docstring が実挙動と一致する (または文ごと消える) | 監査照合 (`git diff`) |
| 46 | `flush_audit_buffer` の port が no-op で、docstring が理由を述べ、利用箇所が追随している | 監査照合 (`git diff`) |
| 47 | 性能 (設計 §8): K=1 の query と mutate、MitateDB の K=4 の waits/acquire を前後で測り、閾値との比較を書く。超えたら監督へ上げる (1-A' に切り替えない) | 監査照合 (計測行の逐語) |
| 48 | 両 peer の suite と、触った `CT/` の file の `pt.py` が failed 0 (新条件の合計の assert は WP-5 まで赤のまま) | 監査照合 (集計行の逐語) |
| 49 | 本表に対応の無い行が無い | 監査照合 |

### 6.3 レビューの観点

応答を返した操作の event が必ず永続化済みであること (経路の漏れ: catalog、replay、dry-run)。MitateDB の pre_commit が cell lock の内側で握る時間。`outcome_note` の宣言と実挙動の一致 (設計 §2 の 11)。

## 7. WP-5 — 決定 2 (両 peer。実装担当)

**目的**: 設計 §5 の 2-A の全項目。
**読むべき正本**: 設計 §2 の 1 (b)・9・10、§5、§11 の 3。直近の migration を足した変更セット (`git log --diff-filter=A -- r2db-api/migrations/0015_credential_request_rate.sql MitateDB-api/migrations/0016_credential_request_rate.sql`) の触ったファイルの集合。**クラス**: C の見込み (`change_class.py` の実測を報告)。**テンプレート**: `ROLES` の 2。

### 7.1 触ってよいパス

- migration (新規。番号は基点の最後の次): `r2db-api/migrations/0016_<name>.sql`、`MitateDB-api/migrations/0017_<name>.sql`
- r2db: `R/service.py` (coalescer の削除と加算の呼び出し)、`R/audit_query.py` (UNION の枝)、`R/credential_store.py`、`R/ops.py` (migration の列挙、基点 :1800・:1814 付近、verify の新しい検査 = 基点の最後 F-20 の次)、`R/platform_declarations.py` (migration の file 名の定数、起動時の検査)、`R/main.py`
- MitateDB: `M/audit_dispatch.py`、`M/application_audit.py`、`M/audit_query.py`、`M/ops.py` (基点 :2792・:2808 付近、verify の新しい検査)、`M/platform_declarations.py`、`M/main.py`
- 両 peer の memory backend の audit の実装 (所在を実物で確かめて報告)
- migration の適用系 (基点で `0015_credential_request_rate` / `0016_credential_request_rate` を引く file。`git grep -l` の実測で 27 件): `r2db-api/deploy/scripts/part1_provision_host_and_db.sh`、両 peer の `conformance/real_server_*.py` と `conformance/conformance_adapter_*_http.py`、`MT/control_plane_harness.py`、`MT/test_postgres.py`、`RT/test_credential_persistence.py`、`RT/test_process_ceilings_declaration.py`、両 peer の `tests/test_application_audit.py`、`RT/test_platform_upgrade_ledger_scan.py`、`MT/test_platform_migration_reapply.py`、`MT/test_ops_apply_platform_migration.py`、両 peer の `tests/test_r113_multi_process_wiring.py` (列挙に要るときだけ)
- 両 peer の `tests/test_audit_query.py`、新しい試験 file。`docs/code-history/` (§2.4)。runbook・`CM` は触らない (WP-6)。

### 7.2 完了条件 (50〜65) → 変異

| # | 完了条件 | 変異 |
|---|---|---|
| 50 | runtime role は counter table に直接の INSERT / UPDATE / DELETE / SELECT を持たず、加算の関数の EXECUTE だけを持つ (試験は直接の UPDATE が権限で拒まれることを見る) | migration に runtime role への UPDATE の grant を足す |
| 51 | 加算の関数は SECURITY DEFINER で `search_path` が固定されている | `SET search_path` を外す |
| 52 | PUBLIC からの EXECUTE が REVOKE されている | REVOKE を外す |
| 53 | 関数と table の owner は schema の owner role で、provision role ではない | owner を provision role に |
| 54 | verify と起動時の検査が 51〜53 の欠けを検出する | 検査から `search_path` の項を外す |
| 55 | 窓は時計に整列し (`window_start` = `clock_timestamp()` の切り捨て)、同じ key の同時の最初の 1 件を K 本送っても counter 行は 1 行、最初の 1 件の audit 行は 1 行。`application_id` NULL は合成 key で 1 値に畳む | 窓を切り捨てない (`clock_timestamp()` そのまま) |
| 56 | 関数は 1 文・autocommit で走り、最初の 1 件なら counter 行と最初の 1 件の audit 行を同じ文で書く。counter 行は summary の event_id・fields・窓の終わりを持ち、同じ窓の 2 回の読みで event_id が同じ | event_id を読みごとに生成する |
| 57 | 件数の意味 (設計 §5 の H2): n = 1 は summary を返さず、n − 1 = 1 は `count` を持たず、最初の行と summary の合計が n | summary の件数を n − 1 でなく n に |
| 58 | `audit_query` は閉じた窓 (`recorded_at` < 現在 − `visibility_lag_ms`) の counter 行だけを、plane application・`recorded_at` = 窓の終わりの summary として返す。auditreader role に SELECT がある | 閉じた窓の条件を外す |
| 59 | process 内の coalescer が削除され、両 peer の memory backend が同じ件数の意味を process 内の表で持つ | memory backend の summary の件数を n に |
| 60 | 加算の失敗は拒否を 503 にする | 失敗時に元の拒否の応答を返す |
| 61 | 新条件の拒否の合計 = M の assert が両 composition root で緑 (新条件全体が緑) | 設計 §6 の変異 (2): 加算を process 内の memory に戻す |
| 62 | 新 migration が適用系 (両 peer の `ops` の apply / upgrade の列挙、platform upgrades の台帳、launcher・adapter・harness の列挙、part1 の script) に登録されている | `R/ops.py` の列挙から新 migration を外す (`RT/test_platform_upgrade_ledger_scan.py` が赤) |
| 63 | 性能 (設計 §8): bearer 無しの flood (K=32) の下で正規 tenant の query の p50 / p95 と 429 の数を前後で測る。悪化したら監督へ上げる | 監査照合 (計測行の逐語) |
| 64 | 両 peer の suite、`CT/test_c<NN>_*.py`、触った `CT/` の file の `pt.py` が failed 0・skipped 0。WP-2 の M16・M17 (と、§4.2 の註により後に回した変異) をここで走らせ赤を確かめる | 監査照合 (集計行と変異表の逐語) |
| 65 | 本表に対応の無い行が無い | 監査照合 |

### 7.3 レビューの観点

counter 行は audit の証拠なので runtime role が減らせない・消せないこと (設計 §5 の H1)。読まれた後の行に加算が入らないこと (設計 §5 の H7)。未認証の拒否が加算の前に platform DB を読まない経路で 503 にならないこと。migration の再適用の冪等性。

## 8. WP-6 — 記録 (監督。起草担当に渡してよい)

**読むべき正本**: 設計 §1・§9 の WP-6 の行・§11。`OC` §1.8 の 56、§1.16 の 78・79。**クラス**: D。

### 8.1 触ってよいパス

`CM`、`CT/CONDITIONS.md` (新条件を executable に)、`docs/design/MULTI_PROCESS_WORKER_V0_1.md` (D-2 の表 #10 / #11 への覆しの註)、`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (D-3 / D-4 / §4 の R-F への覆しの註)、`PR` (§15・§15.1・§15.2 と migration の適用の節)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (migration の段)、`CR` の §10 の外 (§3 の migration の適用の段、§3.2d)、`RM`、`docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md`、`docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md`、引き継ぎ書 `docs/work-orders/HANDOVER_<日付>_R115_FABLE.md` (既存の名の形に倣う) と最新 2 通から外れる引き継ぎ書の `docs/archive/` への移動、本書 §10。

### 8.2 完了条件 (66〜76) → 変異

| # | 完了条件 | 変異 |
|---|---|---|
| 66 | `CM` の SI-14 の両 peer の Control・Evidence・Status が 1-A (i) と 2-A の実挙動を述べ (buffer と process-local の上限の記述が残らない)、`CM`:867 の pin 名が WP-2 の改名に追随し、`CM` の版が 3.10 の次 | 監査照合 (`git diff`) |
| 67 | `pt.py -- CT/test_control_mapping_register.py -q` が緑 (主張は 300 字以内、参照が解決する) | 監査照合 (集計行の逐語) |
| 68 | 変更した各ファイルについて `grep -c '<path>:' security/CONTROL_MAPPING.md` の件数を前後で記録し、行参照が現物に追随している | 監査照合 (コマンドと出力の逐語) |
| 69 | `CT/CONDITIONS.md` の新条件が executable で、`pt.py -- CT/test_conditions_register.py -q` が緑 | 監査照合 (集計行の逐語) |
| 70 | R-113 設計 D-2 の #10 / #11、フェーズ4 設計 D-3 / D-4 / R-F の行を消さず、覆した根拠 (本件の設計 §4・§5) と日付の註を足した (`OC` §1.8 の 56) | 監査照合 (`git diff`) |
| 71 | 両 peer の runbook に新 migration の適用の段と、容量の算式の行 (`PR` §15.1、`CR` §3.2d) の追記があり、buffer・overflow の固定 message の行 (`PR` §15.2、`CR` §3.2d) が実挙動に合う。書いたコマンドは合成の local cluster で実行した | 監査照合 (`git diff` と `$SP/r115-wp6-commands.log` の逐語) |
| 72 | `CR` の `### 10.6` から `### 10.8` の直前、および `### 10.10` から末尾の sha256 が変更の前と後で一致 (§8.3 のコマンド) | 監査照合 (前後の出力の逐語) |
| 73 | 台帳: R-115 の行を記録ファイルの末尾へ逐語で移し §8.2 に索引行 (`OC` §1.16 の 79)、版数行と回転 (同 78)、§0.1.1 の G-2 / G-3 行の条件数 (新条件を足した 34 件)。`python3 tools/dev/ledger.py --check` が緑 | 監査照合 (出力の逐語) |
| 74 | 引き継ぎ書に「裁定」節 (`OC` §1.15 の 77) があり、最新 2 通から外れる引き継ぎ書を同じ変更セットで移した | 監査照合 (`git status --short` の逐語) |
| 75 | `tools/check_doc_refs.py`・`tools/public_value_scan.py <触った全パス>` が緑、`tools/change_class.py <全変更セットのパス>` が D | 監査照合 (出力の逐語) |
| 76 | 本表に対応の無い行が無い | 監査照合 |

### 8.3 `CR` の不変の確かめ方

worktree を cwd にして変更の前と後で実行する。

```bash
f=MitateDB-api/docs/cloud-run-cloud-sql.md
a=$(grep -n '^### 10\.6 ' $f | cut -d: -f1); b=$(grep -n '^### 10\.8 ' $f | cut -d: -f1)
c=$(grep -n '^### 10\.10 ' $f | cut -d: -f1)
sed -n "${a},$((b-1))p" $f | shasum -a 256
sed -n "${c},\$p" $f | shasum -a 256
```

## 9. 完了ゲート・性能・監査 (監督)

- 完了ゲート: `tools/dev/gate.py -C .claude/worktrees/mystifying-hellman-56a270 --label r115` を単独実行 (レビュー担当・監査担当が pytest を走らせていないことを確かめてから)。集計行だけを正本にする (`OC` §1.5 の 41)。`CT/COLLECTION_FLOOR` をゲートの実測に更新する。
- `tools/tests` に触れていれば `tools/dev/pt.py -C $WT -- tools/tests -q` を別に回す。
- 性能: WP-3・WP-4・WP-5 の記録 (完了条件 25・31・47・63) を閾値 (`RM` §0.1.4 の 1、MitateDB の K=4 は同 3) と突き合わせる。悪化が閾値を超えたら依頼者へ上げる (1-A' には切り替えない)。
- 受け入れ監査 (`evidence-auditor`) を全 WP の後に 1 回。契約版は merge の直前に main の最新を確かめ、main が 1.13.0 を先に取っていれば版を振り直す。

## 10. 記録 (統合時に監督が埋める)

## 11. 訂正註 (本文は書き換えない。`OC` §1.8 の 57)

1. **訂正註 (監督裁定 1、2026-09-30、§1.3 の 1)**: 契約 1.13.0 の確定文は `$SP/confirmed-contract-1130.txt` の 3 節 (`audit.process_loss_policy` = 依頼者確定、`versioning.version_binding` の 1.13.0 の文と `versioning.obligations` の項目 = 確定文から機械的に導いた監督確定。subordinate ruling は 18)。`spec/CCR_DISPOSITION.md` の ruling 18 の段は、ruling 17 の段と同じ形で、同ファイルの `version_binding` の文を引用して書く。WP-1 はこのファイルから複製し、言い換えない。
2. **訂正註 (監督裁定 2、2026-09-30、§1.3 の 2)**: 設計 §8 の計測のうち `tools/perf_baseline.py` に口の無いもの (real-server の op=mutate、未認証 flood 下の正規 tenant、MitateDB の K=4 の waits/acquire) は、監督が scratch の driver で測り、§10 に数値と手順を記録する (設計 §3 の計測と同じ扱い)。道具は変えない。実装担当は測らない。
3. **訂正註 (監督裁定 3、2026-09-30、WP-3)**: MitateDB の sink の pool は、F-16 の床の式を変えない大きさにする — 床は既に `mitatedbsvc_api` の store を 2 つ (credential store と audit sink) × pool の大きさで数えている (`MitateDB-api/src/mitatedb_api/platform_declarations.py`:920-923 の `_API_ROLE_STORE_COUNT = 2`)。pool の上限は credential store と同じ `role_pool_size(thread_limit)` とする。式が変わらないので `ops startup-checks` に新しい世代は足さず、`KNOWN_FINGERPRINTS` の現行世代の行の指紋だけを同じ変更で更新する (`MitateDB-api/src/mitatedb_api/startup_checks.py` の docstring の Operational fact)。式を変えないと実装できないと分かったら、実装前に報告する (`OC` §1.5 の 37)。
4. **訂正註 (監督裁定 4、2026-09-30、WP-5・WP-6)**: MitateDB の新しい platform migration は、`MitateDB-api/docs/cloud-run-cloud-sql.md` の §10.6 (互換表)・§10.7 (lock の表)・§10.10.1 (適用の段) に行を足さないと既存配備へ適用する手順が書けない。3 節は受理済み (§10.8) で、着手時の依頼者の指示は「変えない」である。**この扱いは依頼者裁定待ちであり、裁定が出るまで WP-5 の MitateDB の migration と WP-6 の runbook には着手しない。** WP-1〜WP-4 は依存しないので先に進める。
5. **訂正註 (監督裁定 5、2026-09-30、§2.4)**: CH-ID の付いたコメントの塊がコードごと消える場合は、実装前に該当の一覧 (file、CH-ID、消える理由) を報告し、監督が受け皿の節の扱いを裁定する。
6. **訂正註 (依頼者裁定、2026-09-30、訂正註 4 の解消)**: 監督の問い「MitateDB に新しい platform migration (拒否の件数の counter) を足すと、受理済みの runbook §10.6・§10.7・§10.10 に行を足さないと既存配備への適用手順が書けません。着手時の指示は『§10.6・§10.7 は 1 byte も変えない』でした。どう扱いますか?」に対し、依頼者は選択肢「§10 を改版し再受理」(§10.6 → 7 版、§10.7 → 7 版、§10.10 → 11 版に新しい migration の行と適用の段だけを足し、R-113 の 0016 と同じく独立レビューの後に依頼者の受理を求める。受理までは §10.8 の記録が版と合わず、Gate-0 は未準備に戻る) を選んだ。これにより §8.3 の「3 節の sha256 不変」の確かめは、足した行・段以外が不変であることの確かめに読み替える。WP-5 の MitateDB の migration と WP-6 の runbook の着手の停止 (訂正註 4) を解く。
7. **訂正註 (監督裁定 6、2026-09-30、WP-1)**: peer の版上げ (両 peer の宣言 4 file、`docs/code-history` の訂正 4 件、版のピン 8 file) は WP-1 から外し、実挙動が揃う最後の実装 WP (WP-5) の commit で行う (契約 `version_binding` の "must land in the same commit as the real behavior change it claims"。先例は 1.10.0)。戻した差分は `git diff c729ab0 95f6906 -- <該当 16 file>` で再現できる。それまで branch 上では C-29 の版一致 6 件と C-33 の証拠の test が赤である (main には入らない)。
8. **訂正註 (監督裁定 7、2026-09-30、WP-4)**: WP-4 は peer ごとに 2 段に分けた (4a = r2db、4b = MitateDB と共有の conformance)。WP-3 の pool には、1.0 s を超えて idle だった接続を貸し出す前に 1 往復で確かめる検査を足した (コードレビューの指摘: 死んだ接続 1 本ごとに書き込みが 1 件 503 になる)。sink 側の再試行は入れない。
9. **訂正註 (依頼者裁定、2026-09-30)**: 監督が「私の判断で進めていて、異論があれば言っていただきたい点」として示した 2 点 — (1) MitateDB の HTTP 層が runtime credential による schema 操作の拒否 (FORBIDDEN) を audit に残さない既存の欠陥を、着手時の範囲 (設計 Q-5 の 2 件) の外だが WP-5 の同じ変更セットで直す、(2) コードごと消えたコメントの塊の `docs/code-history` の節を削除し (履歴は git が持つ、番号は再利用しない)、WP-6 で `docs/design/CODE_COMMENT_PROVENANCE_V1.md` に註を足す — に対し、依頼者は「2点とも監督の判断どおりで進めてください」と裁定した。
10. **訂正註 (監督裁定 8、2026-09-30、main の取り込み)**: WP-3 の後に main `3b8699d` を branch へ取り込んだ (commit `7ff8b69`)。同型性の表の件数 pin は 203 行 (main の 199 + launcher の helper 4)。本書 §4 が引く旧 pin 名 (198) はこの値に読み替える。`COLLECTION_FLOOR` (main 4697)、台帳の版 (v1.139 まで使用済み)、`CM` の版 (3.11) は WP-6 と完了ゲートで取り込み後の実物に合わせる。
11. **訂正註 (監督裁定 9、2026-09-30、WP-4b のコードレビュー)**: (1) 完了条件 40 のうち周期の thread・lifespan の最終 sweep・`*_AUDIT_FLUSH_INTERVAL_S` の knob と env 例の行、および完了条件 46 の port `flush_audit_buffer` の no-op 化は、拒否の窓が process 内に残る間は拒否の窓の sweep だけを担うので WP-4 では残し、WP-5 (拒否の窓が DB に移る段) の完了条件として読む。(2) 完了条件 36 の「catalog の event」は r2db にだけ当たる。MitateDB の `catalog` は基点でも audit event を出さず、宣言する operation の語彙にも無い (`MitateDB-api/src/mitatedb_api/application_audit.py` の宣言)。出していない event は失われないので契約 `audit.process_loss_policy` には反しない。peer 間の非対称は本件の範囲に含めない (観察)。(3) COMMIT の途中で接続が切れ commit の成否が分からない場合は、両 peer の全経路で error 行を書く側に揃え、`outcome_note` に「error 行は commit しなかったこと、または commit の成否を service が知り得なかったことを表す」旨を両 peer 同一の文で足す (WP-5b)。(4) MitateDB の backend の単発 `insert()` / `update()` は呼び出し元が 0 件になったので削除する (hook を通らずに commit する経路を残さない。WP-5b)。(5) `MitateDB-api/src/mitatedb_api/audit_hook.py` の docstring を実挙動に合わせる (schema 操作 3 種が idempotency の記録より前に hook を呼ぶ順序は変えず、docstring の「LAST thing」を事実に直す。その後の失敗は error 行が覆う。WP-5b)。
12. **訂正註 (監督、2026-09-30、作業の場所)**: 2 つ目のチャットから worktree は `.claude/worktrees/r115-cont` (branch `r115-cont`、`9ae742d` から分岐)。本文と §2.3・§9 の `mystifying-hellman-56a270` はこれに読み替える。
