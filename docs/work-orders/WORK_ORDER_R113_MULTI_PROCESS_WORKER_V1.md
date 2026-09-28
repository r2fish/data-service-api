# 作業指示書 — R-113 multi-process worker と区分 (ii) の limit 状態の置き場 (Change Set Manifest)

## 0. 版数・位置づけ

- **v1.0 (2026-09-28)。** 基点 local main `e3b0f5a` (契約 1.11.0、変えない)。file:line はこの木の現物。worktree は発注時に監督が指定する (本書では `$WT`)。起草時の疑義への監督裁定 1〜8 (§6.1) を本文に反映済み。
- 台帳 `RM` §8 の **R-113** (`RM`:533)。**規模 L** (`OC` §1.13 の 74)。**変更クラス D** (設計 §10 の裁定 22。`RM` §9 の 8)。D の証拠: C の全部 (コードレビュー・受け入れ監査・完了ゲート・conformance の完走) + 依頼者裁定の逐語 (§1.2) + 版付きの security-contract 決定 (`security/CONTROL_MAPPING.md` 3.6 → 3.7、WP-6)。
- 設計の正本は `docs/design/MULTI_PROCESS_WORKER_V0_1.md` v0.5。**設計 §10 (裁定 1〜42) が設計の本文より優先する。** 本書は設計の決定・却下案・背景を写さず節と裁定の番号で指す (`RM` §9 の 9)。逐語は依頼者裁定の指し先 (§1.2)、§6.1 の監督裁定、§10 の D-16 だけ。
- 手本: `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` (以下「R-101 作業指示書」)。
- 番号: 完了条件は全 WP の通し番号。変異は **M<完了条件番号>** (両 peer に掛けるものは `r` / `m` の 2 件)。変異の無い完了条件は「監査照合」とし、照合対象の逐語 (コマンドと集計行、`file:line`、`git diff`) を報告に残すことを完了条件とする (`OC` §1.5 の 40)。
- 新しい共通条件は WP-1 が `conformance-tests/CONDITIONS.md` の C-31 の次で採番するまで「新条件」と呼ぶ (設計 §10 の裁定 7)。
- 規律は `OC` に従い、条項は番号で指す。下請けの Agent を起動しない (`OC` §1.7 の 47)。疑義は実装せず報告する (`OC` §1.5 の 37)。実装担当の裁量は実装詳細だけ。

**本書内の略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`ROLES` = `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`、「設計」= `docs/design/MULTI_PROCESS_WORKER_V0_1.md`、`MPW`:行番号 = 設計の行。L_c / L_r = data plane の `limits.concurrency` / `limits.requests_per_minute` の宣言値 (テストは capability document から読む)。

## 1. 枠

### 1.1 問題設定・守るべき条件・決定・却下案

- 問題設定と守るべき条件: 設計 §1・§2。
- 決定: 設計 §3 D-1〜D-7 と §10 の裁定 1〜42、本書 §6.1 の監督裁定 1〜8。
- 却下案: 設計 §4 (蒸し返さない)。依頼者判断待ち: 無し。

### 1.2 依頼者裁定

設計 §5 の Q-1 の裁定の行 (`MPW`:446、依頼者裁定 2026-09-28「Q-1 は (A')、Q-3 は 1、Q-4 は (B)、Q-5 は行う で進めます。」)。Q-3・Q-4・Q-5 の行 (`MPW`:462、:473、:481) は同じ逐語を指し、Q-2 は監督裁定 15 で閉じた (`MPW`:454)。Class D に要る依頼者裁定の逐語はこの行である (§6.1 の監督裁定 5)。

### 1.3 起草時の現物 (基点 `e3b0f5a`。各 WP の触ってよいパスに無いもの)

- **同型性**: `_ISOMORPHIC_TARGETS` は両 peer の `tests/test_audit_query.py` に在り (r2db :2393、MitateDB :2188)、件数 pin は 169 (r2db :2982・:3369・:2416・:3093、MitateDB :2765・:3151・:2211・:2875、r2db `tests/test_r78_pool_wait_stats.py`:295)。pin のテスト名は `security/CONTROL_MAPPING.md`:819 が引く。同型性テストは同じ木の兄弟 peer を読み、兄弟側に無い symbol と本体の違う symbol を不一致とする (r2db `tests/test_audit_query.py`:3640-3667)。`ops verify-declarations` の `_VERIFY_DECLARATIONS_EXIT_CODES` / `_verify_declarations_checks` / `cmd_verify_declarations` は登録済みの同型 helper (r2db `ops.py`:986・:992・:1064・:1230、MitateDB :1260・:1331・:1549)。
- **http adapter** は composition root を通らず、r2db は `DataService(...)` (`conformance_adapter_r2db_http.py`:1293、隔離 surface :2492)、MitateDB は `_LimitStateHolder()` (`conformance_adapter_mitatedb_http.py`:1072、隔離 surface :2021-、`max_concurrency=3` :2071) を直接組む。宣言は data 1 / control 1。
- **launcher**: `conformance-tests/socket_harness.py` の `start_uvicorn_subprocess` (:743-814) は `--workers` を渡さず、出力を捨て (:801-806)、pidfile に子の pid (:809)、掃除は pid 単位 (:884-)。C-26 の lifecycle は ceiling 1 で起動し 2 で再起動 (`conformance-tests/test_c26_composition_root.py`:94、:100)、(4) :220-241、(5) :244-258。
- **両 peer の src を走査する `tools/tests` の共有 pin**: `tools/tests/test_sql_statement_safety_scan.py` (:199 `_EXPECTED_DISCOVERED_MODULES`、:346 行番号付きの `_ALLOWED_UNFOLDABLE`)、`tools/tests/test_src_import_readers.py` ほか。どの WP の触ってよいパスにも入れない (赤は報告)。
- **K=1 の直近基準値** (`--warmup 20 --n 200`): `docs/design/PHASE11_KEYSET_PAGING_V1.md` の「WP-7 実施記録 (2026-09-25)」(:855-、`PERFRUN` :862、6 plug 21 行)。real-server plug の同じ引数の記録は無い。
- **記録**: `conformance-tests/CONDITIONS.md` の C-05 :34、C-26 :55、最後は C-31 :60。`COLLECTION_FLOOR` 4342。`security/CONTROL_MAPPING.md` 3.6 (:5)、SI-08 の r2db 写像 :711-712、MitateDB 写像 :904、C-26 の開示 :988。

## 2. 順序・役割

### 2.1 順序 (監督裁定 1)

**WP-1** (conformance) → **WP-2** (r2db) → **WP-3** (MitateDB) → **WP-4** (計測器) → 監督の計測と判定 (§7.5・§10) → **WP-5** (配備) → **WP-6** (記録、監督)。

- WP-2 と WP-3 は並行しない。WP-3 は WP-2 の同名 helper を正規化 diff で一致するよう移植し、`_ISOMORPHIC_TARGETS` の登録と件数 pin の更新は WP-3 だけが行う。
- WP-1 と WP-2 は触るファイルの重なりが 0 なら並行してよいが、現物では `r2db-api/conformance/real_server_r2db.py` の 1 本が重なる (WP-1 = workers ほか、WP-2 = migration 一覧)。よって直列とする。
- WP-1 の新テストは WP-2・WP-3 が入るまで赤である (変異先行、設計 §6)。src に掛かる WP-1 の変異は WP-2 (r) / WP-3 (m) の実装担当が取り込んだ木で走らせる。
- 統合の前に main を取り込み、件数 pin・`COLLECTION_FLOOR`・台帳の版の衝突を先に解く。

### 2.2 役割と実装担当への制約

- **実装担当** (`ROLES` の 2): WP-1〜WP-5 に 1 起動ずつ (差し戻しは別起動)。穴は 担当 worktree = `$WT`、作業指示書 = 本書の該当 WP の節、正本設計 = 各 WP の「読むべき正本」、タスク = 完了条件と変異表、テスト / 変異 = 各 WP の「道具の引数」。
- **制約** (全 WP): 下請けの Agent を起動しない。commit・merge・push・branch 操作・`git stash` をしない (`OC` §1.1 の 2)。`pytest` を直接走らせず `tools/dev/pt.py` / `tools/dev/mutate.py` を前景直列で使う (timeout 600000、`OC` §1.5 の 39・§1.6 の 42)。suite 全体・`gate.py`・`finalize.py`・`tools/perf_baseline.py` の計測を実行しない。**設計 §10 が設計の本文より優先する。** 設計に無い検査・機構は実装前に報告する。触ってよいパスの外の赤は直さず報告する。一時ファイルは `$SP` 配下、複数手順は `$SP` の bash 3.2 互換スクリプト。報告は `$SP/r113-wp<N>-report.md`。新規のコメント・docstring は現在形、経緯語 (フェーズ・WP・R-番号) を書かない。
- **コードレビュー** (`ROLES` の 5、Class D): WP ごとに 1 回、別の起動。観点は各 WP の「レビューの観点」と空振り (`OC` §1.5 の 32)・代理指標 (`OC` §1.7 の 52)。自作の変異 1〜2 件 (完了ゲートと並行させない)。
- **受け入れ監査** (`ROLES` の 6): 全 WP の後に 1 回、レビュー担当とも別の起動。全完了条件の主張 vs 実測 (`OC` §1.5 の 34) と変異の再現。
- **監督**: 完了ゲート (`tools/dev/gate.py -C $WT`、単独)、`tools/tests` は別に (`tools/dev/finalize.py --tools-tests`)、§7.5 と §10、WP-6、commit・merge、指摘の 1 件ごとの裁定 (`OC` §1.15 の 77)。

### 2.3 道具の引数 (全 WP 共通の形)

`$SP` を export し、`pt.py` / `mutate.py` は main checkout を cwd にして `-C $WT` で worktree を指す (渡し忘れると main を測る)。

```bash
tools/dev/pt.py --wait 1800 -C $WT -- <WP ごとのパス> -q
tools/dev/mutate.py "$SP/r113-wp<N>-mutations.json" -C $WT --wait 1800   (peer と tools は run を分ける)
```

worktree を cwd にして:

```bash
python3 tools/check_comment_provenance.py --base e3b0f5a <触った src>   (src を触る WP)
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- `-k` の id は `--collect-only -q` で確かめる。`PYTHONPATH` は `OC` §2 の 17。REFUSED (75) は迂回しない。
- 変異の test id は各完了条件に対応するテストを **1 件だけ**書く (`mutate.py` は最初の失敗で止まる)。同じ数行に掛かる変異も赤にするテストが違えば別の変異として走らせる。`old` / `new` の具体は実装担当が書き、報告に表で残す。

## 3. WP-1 — 新条件と C-26 (4)(5) の改訂、launcher の workers 化 (実装担当)

**目的**: 区分 (ii) の `concurrency` と `requests_per_minute` が 2 worker をまたいで宣言値ちょうどで効くことを観測する新条件と C-26 (4)(5) の改訂を、実装より先に置く。launcher に workers・process group・pgid の掃除・slot directory・preflight・pid 付き access log・保持の port を足す。

**読むべき正本**: 設計 §3 D-4 (v0.3・v0.4 の改定)、D-3 (4) の plug ごとの配線の表、§10 の裁定 11・12・14・19・23・26・27・32・33・35・42。**クラス**: C (全体 D)。**テンプレート**: `ROLES` の 2。

### 3.1 触ってよいパス

- `conformance-tests/socket_harness.py` — `start_uvicorn_subprocess` (:743-814) に `workers` (既定 1、1 でも `--workers 1` を渡す)、自分の process group での起動と killpg、pidfile の pgid、`sweep_orphans` (:884-) の pgid 単位化、access log の保存先 (uvicorn の log 設定で要求の行に pid)。socket plug の挙動は変えない。
- `conformance-tests/test_socket_harness.py`、`conformance-tests/test_c26_composition_root.py` ((4) を 3 通り、(5) に workers ≥ 2 の起動形。他のテストは変えない)、新規テスト 1 本 (`test_c<採番>_…py`)、`conformance-tests/conftest.py` (新テストが launcher の xdist group (:98-127) に入らないときだけ)、`conformance-tests/CONDITIONS.md` (:34、:55、新しい行) と `conformance-tests/CONDITIONS_HISTORY.md`。
- `r2db-api/conformance/real_server_r2db.py` / `MitateDB-api/conformance/real_server_mitatedb.py` (`start` r2db :613- / MitateDB :563-、`restart` :711- / :651-、C-26 (5) :847-904 / :772-) — `workers` 引数、env (`R2DB_WORKERS` / `MITATEDB_WORKERS`、control は `R2DB_CONTROL_WORKERS` / `MITATEDB_CONTROL_WORKERS` = 1、起動ごとに `mkdtemp` した `R2DB_SLOT_DIR` / `MITATEDB_SLOT_DIR` を停止で消す)、workers ≥ 2 の起動形 (preflight → uvicorn の supervisor)、C-26 (5) の workers ≥ 2 の起動、pid 付き access log の保存と読み出し、保持の port (launcher 自身の特権接続で served application の entity の保存先に `LOCK TABLE … IN ACCESS EXCLUSIVE MODE`)、lock 待ちの session の `application_name` を読む accessor。**本番コードに stall フックを足さない** (裁定 14)。両 launcher の新 method は同じ名前・引数。
- **これ以外は 0 件** (両 peer の `src/`・`tests/`・`migrations/`・http / socket adapter、`spec/`・`security/`・`COLLECTION_FLOOR`)。adapter の配線は WP-2・WP-3 (監督裁定 2)。

### 3.2 完了条件 (1〜24)

新条件と C-26 のテストは registry の両 launcher で走り、各 launcher で観測対象が 1 件以上あることを assert する (`OC` §1.5 の 32)。

| # | 完了条件 |
|---|---|
| 1 | `start_uvicorn_subprocess(..., workers=n)` は n = 1 を含め常に `--workers <n>` を渡し、n = 2 の supervisor の process group に supervisor 1 本と子 2 本が在る |
| 2 | supervisor は自分の process group で起動し、`stop()` の後にその pgid の process が 0 本 (裁定 19) |
| 3 | pidfile は pgid を記録し、子 1 本を SIGKILL して supervisor が置き換えた後に `sweep_orphans` で掃除すると group の process が 0 本 (裁定 33) |
| 4 | 両 launcher の `start` / `restart` は data に workers と起動ごとの `mkdtemp` の slot directory (0700)、control に workers 1 を env で渡す。2 つの instance の directory は異なり、`stop()` の後に残らない (裁定 27、監督裁定 4) |
| 5 | workers ≥ 2 の起動形は preflight (`python -m <package>.main --preflight`、子と同じ env) が 0 で終わってから supervisor を起動し、起動の事象の記録で preflight が data の uvicorn より前 (裁定 26) |
| 6 | 両 launcher は data の子の access log を保存し、200 の要求の行ごとに応答した pid を読み出せる (裁定 17・32、監督裁定 2) |
| 7 | 保持の port の上限は `execution_ms` と application role の statement_timeout の小さい方より短い (テストが値を読んで比べる。裁定 14) |
| 8 | C-26 (4) ceiling 1 / workers 1: data の `concurrency`・`requests_per_minute`、control の `control_requests_per_minute` がすべて `enforced` (裁定 35) |
| 9 | ceiling 2 / workers 2 (slot を配線): data の `concurrency` が `enforced` (裁定 35) |
| 10 | ceiling 2 / workers 1: data の `concurrency` が `deployment_required` (裁定 35) |
| 11 | ceiling 2 の 2 つの起動形で data の `requests_per_minute` が `enforced` (裁定 18・27) |
| 12 | control の ceiling 2 (control の workers 1) で `control_requests_per_minute` が `deployment_required` |
| 13 | C-26 (5) の workers ≥ 2 の起動形: `process_ceilings` の無い配備で preflight が非 0、stderr に `F-15`、supervisor は起動しない (裁定 26) |
| 14 | 新条件 (a): ceiling 2 / workers 2 で entity の保存先を保持し、新しい接続で L_c + 2 本を同時に送ると、保持中に応答の返らない本数がちょうど L_c、残り 2 本は保持中に 429 (`limit_class` = `concurrency`) (client 側で数える。裁定 14・23) |
| 15 | 新条件 (a): 保持中の lock 待ちの session の `application_name` (`"<peer>:data:<pid>"`) に 2 種以上の pid (裁定 14・23) |
| 16 | 新条件 (b): `concurrency` 以下の波に分けて新しい接続で 2 L_r 本を送ると 200 がちょうど L_r 本 (裁定 32) |
| 17 | 新条件 (b): 429 (`limit_class` = `requests_per_minute`) がちょうど L_r 本 (裁定 32) |
| 18 | 新条件 (b): 200 の pid (access log) が 2 種以上 (裁定 32) |
| 19 | `CONDITIONS.md` に C-31 の次番の行 (Condition・SI-08・test form・status・history の link) が在り、新テストの `@pytest.mark.condition` がその番号で、`conformance-tests/test_conditions_register.py` が緑 |
| 20 | **監査照合**: C-26 の行 (:55) の (4)(5) が完了条件 8〜13 の観測と一致 (`git diff`) |
| 21 | **監査照合**: C-05 (:34) の honest limits (6) を新条件の分だけ狭め (2 worker の process 間の bound は新条件が観測、1 host の外は観測しない)、`int[61]` が境目で最大 1 秒分を多めに数え L を超えて通さないことを開示 (裁定 42。`git diff`) |
| 22 | **監査照合 (変異先行)**: WP-2・WP-3 の前の木で完了条件 8〜18 の緑 / 赤と、赤の失敗 assert の逐語 (9・11・14〜17 は赤が期待) |
| 23 | **監査照合**: 触ったファイルの既存テストが緑 (集計行) |
| 24 | **監査照合**: §3.3 で変異も監査照合も持たない行が 0 件 |

### 3.3 完了条件 → 変異 (`expect=red`)

「木」: WP-1 = WP-1 の木。r / m = WP-2 / WP-3 を取り込んだ木で、その peer の launcher の id に絞る。

| 完了条件 | 変異 | 木 |
|---|---|---|
| 1 | **M1**: `--workers` を渡さない | WP-1 |
| 2 | **M2**: 停止を supervisor 1 本への signal に戻す | WP-1 |
| 3 | **M3**: pidfile に起動時の子の pid を記録する (設計 §6) | WP-1 |
| 4 | **M4r / M4m**: 固定の slot directory を渡す | WP-1 |
| 5 | **M5r / M5m**: preflight を飛ばす | WP-1 |
| 6 | **M6r / M6m**: access log を保存しない | WP-1 |
| 7 | **M7r / M7m**: 保持の上限を `execution_ms` と同じにする | WP-1 |
| 8 | **M8r / M8m**: data の区分 (ii) の写像を常に `deployment_required` | r / m |
| 9 | **M9r / M9m**: slot directory を写像の入力に渡さない | r / m |
| 10 | **M10r / M10m**: 写像から ceiling ≤ workers を外す (設計 §6) | r / m |
| 11 | **M11r / M11m**: rate の写像を未配線の戦略に固定 | r / m |
| 12 | **M12r / M12m**: control の写像を常に `enforced` | r / m |
| 13 | **M13r / M13m**: preflight が例外を握って 0 (設計 §6) | r / m |
| 14 | **M14r / M14m**: slot を process 内の counter に戻す (設計 §6) | r / m |
| 15 | **M15r / M15m**: `application_name` の pid を定数に | r / m |
| 16 | **M16r / M16m**: rate の窓を process 内に戻す (設計 §6) | r / m |
| 17 | **M17r / M17m**: 1 文の WHERE を「合計 ≤ L」に | r / m |
| 18 | **M18r / M18m**: access log の pid を定数に | r / m |
| 19 | **M19**: `CONDITIONS.md` の新しい行を消す | WP-1 |
| 20〜24 | **監査照合** | — |

### 3.4 道具の引数

§2.3 の形で、パスは `conformance-tests/test_socket_harness.py conformance-tests/test_c26_composition_root.py conformance-tests/test_conditions_register.py conformance-tests/<新条件のファイル>`。`conformance-tests -q` の全体は回さない。

### 3.5 レビューの観点

本番の起動形を保つこと (裁定 14)、(a) の数え方 (裁定 23)、(b) の 3 主張 (裁定 32)、後始末が例外経路でも対になること、C-26 (4) の 3 通り (裁定 35)、C-05 の開示 (裁定 42)。

## 4. WP-2 — r2db の区分 (ii) の置き場・起動時の検査と preflight・接続予算 (実装担当)

**目的**: r2db の `requests_per_minute` を platform 表の 1 行 (`int[61]` の環 + 基点の秒) を数える 1 文に、`concurrency` を host 内で共有する slot に移す。写像を 2 戦略の helper にし、両 plane の composition root に workers と slot directory の起動時検査と `--preflight` の entry を置き、`application_name` と thread limit 基準の pool / F-16 / F-18 を入れる。

**読むべき正本**: 設計 §3 D-1 (v0.4 改定)・D-2 (表の #11〜#13 と preflight の段)・D-3 ((1) の v0.5 の骨子、(2)、(2')、(4)、(5))、§1.4 の (1)(2)(4)(6)、§9 の (c)(q)(r)(s)(u)、§10 の裁定 10・11・14〜16・18・25〜30・33・34・36・37・40・41、本書 §6.1 の監督裁定 1・3・4。**クラス**: D (登録済み同型 helper の本体)。**テンプレート**: `ROLES` の 2。

### 4.1 触ってよいパス

- `r2db-api/migrations/0015_<名>.sql` (新規、platform 単発) — platform schema の rate 表 (`credential_id` 主キーで credential の表を参照し `ON DELETE CASCADE`、`base_s bigint`、`counts int[]` 長さ 61)。api role に SELECT / INSERT / UPDATE だけ。他の role に権限を足さない。
- `r2db-api/src/r2db_api/` の次のファイル:
  - `concurrency_slots.py` (新規) — slot の helper (directory の検査、`selfcheck` の自己検査、要求ごとの open / flock / close、乱数始点、errno の区別)。stdlib のみ。
  - `service.py` (:641、:691-694、:1019-1109) — rate を「配線された PG の 1 文 / 未配線の in-memory 窓」、`acquire_concurrency_slot` を「配線された slot / 未配線の counter」に分ける。未配線の経路 (`tests/test_threadpool_offload.py` の AST pin を含む) と denial の details (:1085・:1109) は変えない。
  - `credential_store.py` — rate の 1 文を credentials pool (api role) の autocommit で打つ method。計数用の pool を新設しない。
  - `capabilities_document.py` (:12、:118-137) と `control_plane.py` (:626-629) — 写像の 2 戦略の helper (control の 2 class も同じ helper を通す。監督裁定 4)。
  - `main.py` — `R2DB_WORKERS` / `R2DB_SLOT_DIR` (必須)、宣言の読み取り (:430-455) の後の workers ≤ `process_ceilings.data` の検査、slot directory の検査と自己検査、pool の寸法 (:465-466、:492)、F-16 / F-18 (:532-540)、`DataService` への配線 (:600-618)、`--preflight` の entry (module の `app` を使い回し、開いた cell と pool を閉じて 0、例外は非 0)。検査は `build_app()` の中 (裁定 41)。
  - `control_main.py` (`build_control_app` :368-) — `R2DB_CONTROL_WORKERS` (必須)、workers ≤ `process_ceilings.control` の検査、`--preflight` の entry、`application_name` (:522 ほか)。
  - `limits.py` (:121-165) — pool = 実効 thread limit + c (c = 2)。docstring :153-157 を事実に (F-1 の理由 :128-142 は残す)。
  - `platform_declarations.py` (:947-960、:1020- F-16、:1234-1262、:1343- F-18) — thread limit 基準の式。
  - `postgres.py` (:335 `_RolePool._connect`、:1007)、`main.py`:337・:430 — `application_name`。preflight の後始末で cell を閉じる経路が無ければ足す。
  - `ops.py` — 0015 の受け付け (:1719-1734)、`verify-declarations` の workers 検査 (:992、:1064。登録済み同型 helper)、:1183-1187 の docstring。
  - `http.py` — 呼び出し (:492、:514 ほか) の形を変える必要があるときだけ。評価順は変えない。
- `r2db-api/conformance/conformance_adapter_r2db_http.py` — migration 一覧 (:364-392) に 0015、session (:1293) と隔離 surface (:2492) に instance ごとの `mkdtemp` の slot directory と PG の rate、写像の入力 ceiling 1 / workers 1 (監督裁定 3)。`hold_in_flight` 系・profile は変えない。
- `r2db-api/conformance/real_server_r2db.py` — migration 一覧 (:407-429) に 0015 だけ。`r2db-api/deploy/scripts/part1_provision_host_and_db.sh` — 0015 の適用 (:393-405 と同じ形)。
- `r2db-api/tests/` — 新規テストと migration 一覧を持つテストの追随。**`_ISOMORPHIC_TARGETS` と件数 pin は触らない** (WP-3。監督裁定 1)。`docs/code-history/r2db-api/`。
- **これ以外は 0 件** (`spec/`・`security/`・`conformance-tests/`・`tools/`・`MitateDB-api/`・unit・runbook)。

### 4.2 完了条件 (25〜82)

peer-local のテストは小さい L を宣言した構成で駆動してよい。実 PostgreSQL で観測する行は関数を直接叩いて代替しない (`OC` §1.7 の 52)。

| # | 完了条件 |
|---|---|
| 25 | 0015 を当てた platform schema に rate 表が在り、credential の行を消すと rate の行も消える (`ON DELETE CASCADE`。裁定 15) |
| 26 | rate 表の権限は api role に SELECT / INSERT / UPDATE だけで、DELETE・TRUNCATE は無く、application・controlplane・auditreader の role には無い (`has_table_privilege`) |
| 27 | `ops apply-platform-migration` が 0015 を受け付け、adapter・launcher・`part1_provision_host_and_db.sh` の一覧が 0015 を当てる |
| 28 | PG の rate を配線した構成で同じ credential の L_r 本が通り、L_r + 1 本目が `LIMIT_EXCEEDED` (details は現行と同じ。`service.py`:1109) |
| 29 | **監査照合**: 1 文は credentials pool の autocommit で要求の tx に入らず、`clock_timestamp()` を 1 回だけ読み、秒の位置は監督裁定 3 の 61 の環 (index = s mod 61、`base_s` は単調、shift = LEAST(61, GREATEST(0, s − base_s))、(base_s+1 .. base_s+shift) mod 61 を 0 にしてから s mod 61 に +1、shift = 61 は全部 0、詰め直さない) である。SQL の逐語を報告に残す |
| 30 | 古い秒を持つ要求が行 lock を待つ間に新しい秒の要求が commit する並びで、`base_s` は戻らず通った本数の合計が L_r を超えない (裁定 37) |
| 31 | `base_s` を 61 秒以上前に書き換えた行で 1 本送ると全部 0 から数えられて通る |
| 32 | 60 秒前の秒に L_r を置いた行で 1 本送ると拒否される (`int[61]`。裁定 34) |
| 33 | 既知の位置に計数を置き `base_s` を k 秒前にした行で 1 本送ると、(base_s+1 .. base_s+k) mod 61 の位置だけが 0 になり他は残る (環。監督裁定 3) |
| 34 | rate の文が DB の失敗になった要求は既存の DB 失敗と同じ 503 で拒否され、通らない (裁定 15) |
| 35 | AST pin: rate の呼び出しは認証の借用 (`service.py`:1096 の `assert_active`) の `with` の外にあり、rate の method は 1 回の借用で 1 文だけ (裁定 25 の (ii)・33) |
| 36 | 認証に失敗した要求は rate 表の行を作りも更新もしない (設計 §2 の条件 5) |
| 37 | **監査照合**: 未配線の構成 (in-process plug) の in-memory の経路が不変で、既存テスト (`tests/test_threadpool_offload.py` の AST pin を含む) が緑 |
| 38 | `R2DB_SLOT_DIR` が未設定・空なら変数名を含む例外で起動に失敗する (裁定 27) |
| 39 | slot directory が無ければ起動に失敗し、`build_app()` は作らない |
| 40 | slot directory の所有者が実効 uid でなければ起動に失敗する |
| 41 | slot directory の mode が 0700 でなければ (0755) 起動に失敗する |
| 42 | slot ファイルが symlink なら open が失敗する (`O_NOFOLLOW`。裁定 28) |
| 43 | helper が作る slot ファイルの mode は 0600 |
| 44 | 取得中の slot の fd は close-on-exec |
| 45 | flock が EWOULDBLOCK / EAGAIN / EACCES 以外 (EPERM の偽装) を返すと 503 で拒否され、429 にも取得にもならない (裁定 28) |
| 46 | 2 本目の `LOCK_EX | LOCK_NB` が拒まれない偽装の flock では起動に失敗する (自己検査。裁定 28) |
| 47 | 自己検査は専用ファイル `selfcheck` を使い、`slot-<i>` を開かない (裁定 36) |
| 48 | 同じ process の 2 thread: L_c = 1 で 1 本目が持つ間、2 本目は 429 (裁定 29) |
| 49 | 本体が例外で終わっても slot は解放される |
| 50 | 拒否の後に open fd の数が増えていない (裁定 29) |
| 51 | 探索の始点は乱数源に従う (差し替えた乱数源で観測) |
| 52 | L_c 本が塞がっているとき L_c + 1 本目は待たずに 429 (`limit_class` = `concurrency`、`limit` = L_c。`service.py`:1085) (`LOCK_NB`。裁定 10) |
| 53 | 1 つの HTTP 要求は slot を 1 本だけ使う (L_c = 1 の配線で 1 要求が通る) |
| 54 | **監査照合 (監督裁定 6)**: 開発機で、slot を握った子 process の SIGKILL の後と fd の close の後に同じ slot を取れることをテストで確かめ、テスト id・集計行・`HAVE_FLOCK` の値を報告に残す |
| 55 | 写像 (`requests_per_minute`): PG の行が配線されていれば ceiling 1 / 2 とも `enforced`、未配線なら現行の式 (裁定 18) |
| 56 | 写像 (`concurrency`): slot を配線した構成で (ceiling, workers) = (1, 1)・(2, 2) は `enforced`、(2, 1) は `deployment_required`。未配線なら現行の式 (裁定 27・35) |
| 57 | control の 2 class の写像は同じ helper を通り、値は現行と同じ (control の ceiling 1 で `enforced`、2 で `deployment_required`。監督裁定 4) |
| 58 | `R2DB_WORKERS` が未設定・空・0・負・非数なら変数名を含む例外で起動に失敗する (裁定 11) |
| 59 | control の composition root は `R2DB_CONTROL_WORKERS` が未設定・空・0・負・非数なら起動に失敗する (監督裁定 4) |
| 60 | `R2DB_WORKERS` > `process_ceilings.data` なら起動に失敗する (裁定 27) |
| 61 | `R2DB_CONTROL_WORKERS` > `process_ceilings.control` なら control の起動に失敗する (監督裁定 4) |
| 62 | 検査は composition root の build の中にある: lifespan を走らせない preflight が workers > ceiling で非 0 (裁定 41) |
| 63 | `python -m r2db_api.main --preflight` は正しい env で 0、`process_ceilings` の無い配備で非 0 と stderr の `F-15` (裁定 26) |
| 64 | `python -m r2db_api.control_main --preflight` は正しい env で 0、control の workers > ceiling で非 0 (監督裁定 4) |
| 65 | preflight は module の `app` を使い回し、build の呼び出しは 1 回 (裁定 41) |
| 66 | preflight は終わる前に開いた cell と pool を閉じる。経路が在ったか足したかを報告に書く (裁定 36) |
| 67 | **監査照合**: preflight の DB への作用が読み取りだけ (設計 D-2 の #13 と照合、`file:line`) |
| 68 | data plane の接続は `application_name` = `r2db-api:data:<pid>` を持つ (`pg_stat_activity`。裁定 14) |
| 69 | control plane の接続は `r2db-api:control:<pid>` を持つ |
| 70 | application role pool と platform pool の既定の寸法は実効 thread limit + 2 で、`R2DB_THREAD_LIMIT` = 6 なら 8 (裁定 16・25 の (i)) |
| 71 | F-18 の下限は P × (2 × (thread limit + c)) + control 分で、P = 4・4・c = 2 で 64、`concurrency` に依らない (裁定 16) |
| 72 | 起動時の F-16 の床は `process_ceilings.data` × (1 process の pool 構成) (裁定 16・40) |
| 73 | **監査照合**: `limits.py`:153-157 を事実に改め、F-1 の理由は残す (`git diff`) |
| 74 | `ops verify-declarations` は data / control の workers > ceiling を専用の終了コードで報告する (運用者の手動検査。裁定 26) |
| 75 | **監査照合**: `verify-declarations` の docstring が「読むのは自分の process の env」を開示する (設計 §9 (c)、裁定 21) |
| 76 | http plug の session と隔離 surface は instance ごとの `mkdtemp` の slot directory を配線し、1 要求の間その slot ファイルに flock が掛かる |
| 77 | http plug の要求は rate 表に credential の行を作る |
| 78 | **監査照合 (監督裁定 1)**: WP-2 の木で同型性テストの赤が、本体を変えた登録済み helper (`verify-declarations` の 3 つほか、列挙) の行だけである |
| 79 | **監査照合**: 新規 module が入るべき静的検査 (`tests/test_l1_details_vocabulary_ast_scan.py` ほか) に入り、`tools/tests` の共有 pin の赤は直さず一覧で報告 (`OC` §1.5 の 40b) |
| 80 | **監査照合**: `check_comment_provenance.py --base e3b0f5a` の出力と、新規コメントが現在形で経緯語を含まないこと |
| 81 | **監査照合**: `r2db-api/tests -q` と §4.4 の conformance の集計行 |
| 82 | **監査照合**: §4.3 で変異も監査照合も持たない行が 0 件 |

### 4.3 完了条件 → 変異 (`expect=red`。run = r2db)

| 完了条件 | 変異 |
|---|---|
| 25 | **M25**: `ON DELETE CASCADE` を外す |
| 26 | **M26**: api role に DELETE を与える |
| 27 | **M27**: `ops.py` の受け付けから 0015 を外す |
| 28 | **M28**: WHERE を「合計 ≤ L」に (設計 §6) |
| 30 | **M30**: `GREATEST` を外す (裁定 37) |
| 31 | **M31**: shift = 61 の全 0 化を外す |
| 32 | **M32**: 配列の長さを 60 に (裁定 34) |
| 33 | **M33**: 0 にする範囲を base_s .. base_s+shift−1 にずらす |
| 34 | **M34**: DB 失敗を素通しする |
| 35 | **M35**: rate の呼び出しを認証の借用の内側へ |
| 36 | **M36**: rate を認証の前に数える |
| 38 | **M38**: 未設定で既定の path に落ちる |
| 39 | **M39**: directory を作る |
| 40 | **M40**: 所有者の検査を外す |
| 41 | **M41**: mode の検査を外す (設計 §6) |
| 42 | **M42**: `O_NOFOLLOW` を外す (設計 §6) |
| 43 | **M43**: mode 0644 で作る |
| 44 | **M44**: `O_CLOEXEC` を外す |
| 45 | **M45**: どの errno も「塞がっている」と読む (設計 §6) |
| 46 | **M46**: 自己検査を外す (設計 §6) |
| 47 | **M47**: 自己検査に `slot-0` を使う |
| 48 | **M48**: fd を process 内で共有する (設計 §6) |
| 49 | **M49**: 例外経路で close しない |
| 50 | **M50**: 拒否した fd を閉じない |
| 51 | **M51**: 始点を 0 に固定 |
| 52 | **M52**: `LOCK_NB` を外す (裁定 10) |
| 53 | **M53**: 1 要求で slot を 2 回取る |
| 55 | **M55**: rate の写像を配線に依らず `enforced` (裁定 18) |
| 56 | **M56**: ceiling ≤ workers を外す (設計 §6) |
| 57 | **M57**: control の写像を helper を通さず常に `enforced` |
| 58 | **M58**: `R2DB_WORKERS` 未設定で 1 に落ちる |
| 59 | **M59**: `R2DB_CONTROL_WORKERS` 未設定で 1 に落ちる |
| 60 | **M60**: data の workers 検査を外す (設計 §6) |
| 61 | **M61**: control の workers 検査を外す |
| 62 | **M62**: 検査を lifespan へ移す |
| 63 | **M63**: data の preflight が例外を握って 0 (設計 §6) |
| 64 | **M64**: control の preflight が例外を握って 0 |
| 65 | **M65**: entry で build をもう一度呼ぶ |
| 66 | **M66**: 後始末の close を飛ばす |
| 68 | **M68**: `_RolePool._connect` から `application_name` を外す |
| 69 | **M69**: plane を `data` に固定 |
| 70 | **M70**: pool を `DEFAULT_THREAD_LIMIT` から導く |
| 71 | **M71**: F-18 の下限を `2 × concurrency` のまま |
| 72 | **M72**: F-16 の床に `process_ceilings.data` を掛けない |
| 74 | **M74**: `verify-declarations` の workers 検査を外す |
| 76 | **M76**: adapter が slot を配線しない |
| 77 | **M77**: adapter が PG の rate を配線しない |
| 29・37・54・67・73・75・78〜82 | **監査照合** |

§3.3 の `r` の行も本 WP の実装担当が WP-1 と WP-2 を取り込んだ木で走らせる。

### 4.4 道具の引数

§2.3 の形で、パスは `r2db-api/tests` と `conformance-tests/test_c05_limit_declaration_agreement.py conformance-tests/test_c26_composition_root.py conformance-tests/<新条件のファイル> -k <r2db の plug と launcher の id>`。

### 4.5 レビューの観点

1 文 (28〜36、監督裁定 3)、slot の helper と未配線の経路 (37〜54)、写像 (55〜57)、両 plane の検査と preflight (58〜67)、pool と F-16 / F-18 (70〜72)。

## 5. WP-3 — MitateDB への移植と同型性の登録 (実装担当。WP-2 の統合の後)

**目的**: WP-2 と同じ帰結を MitateDB に置き、同名 helper は WP-2 の本体を正規化 diff で一致するよう移植する。`_ISOMORPHIC_TARGETS` の登録と件数 pin の更新を両 peer で行う (監督裁定 1)。加えて永続接続 × N の需要を数え (設計 §9 (e))、`hold_in_flight` が pool の接続を持たずに止まることを確かめる (裁定 42 の (n))。

**読むべき正本**: WP-2 の「読むべき正本」、設計 D-3 (5)、§1.4 の (6)、§9 の (e)(n)、裁定 42。**クラス**: D (`_ISOMORPHIC_TARGETS` の増減)。**テンプレート**: `ROLES` の 2。

### 5.1 触ってよいパス

- `MitateDB-api/migrations/0016_<名>.sql` (新規、platform 単発。名を `_upgrade.sql` で終えない)。
- `MitateDB-api/src/mitatedb_api/` の次のファイル: `concurrency_slots.py` (新規、WP-2 から移植)、`cell.py` (:306-411。`_LimitStateHolder` の `acquire_rate` :337-344 と `acquire_concurrency_slot` :373- を 2 戦略に。`_CONCURRENCY_RESERVED` の入れ子の扱いと `limit_class` は変えない)、`http.py` (:538。必要なときだけ)、`capabilities_document.py` (:44、:322、:327) と `control_plane.py` (:1575-1577)、`main.py` (`MITATEDB_WORKERS` / `MITATEDB_SLOT_DIR`、workers と slot の検査、platform pool :345-349、F-16 / F-18 :411-419、`_LimitStateHolder` :477、`--preflight`)、`control_main.py` (:59-) と `control_composition.py` (:73-。`MITATEDB_CONTROL_WORKERS`、workers ≤ `process_ceilings.control`、`--preflight`)、`config.py` (:300-319)、`platform_declarations.py` (:917-934、:993-、:1209-1235、:1318-)、rate の 1 文の置き場 (`credential_store_postgres.py` か `pool.py`。platform pool、api role、autocommit)、接続工場 (`application_name`: data は `pool.py`:164・`backend_postgres.py`:293-294・`credential_store_postgres.py`:326・`application_audit.py`:352・`main.py`:256、control は `control_plane.py`:451・:1070・`control_credential_store_postgres.py`:85・`control_audit.py`:214・`control_composition.py`:145・`audit_query.py`:407)、`ops.py` (0016 の受け付け :2669-2710、`verify-declarations` :1260・:1331)。
- `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (一覧 :380・:433 に 0016、session :1072・:1169 と隔離 surface :2021- に別々の `mkdtemp` の slot directory と PG の rate、ceiling 1 / workers 1)、`MitateDB-api/conformance/real_server_mitatedb.py` (一覧 :366・:387 に 0016 だけ)。
- `MitateDB-api/tests/` (新規テスト、`tests/control_plane_harness.py`:162・:195 ほか一覧の追随)、`docs/code-history/MitateDB-api/`。
- **同型性の登録** (本 WP だけ): 両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` と件数 pin (§1.3)、`r2db-api/tests/test_r78_pool_wait_stats.py`:295。r2db の src は触らない (不一致は MitateDB 側を合わせる。r2db 側を変える必要があれば報告)。
- **これ以外は 0 件。**

### 5.2 完了条件 (83〜145)

**83〜135・137〜139 は WP-2 の 25〜77・79〜81 を MitateDB に読み替えたもの** (番号 = WP-2 の番号 + 58。本文は §4.2 の同じ行に下の読み替えを掛ける)。

| WP-3 の # (WP-2 の #) | 読み替え |
|---|---|
| 83 (25)・84 (26) | 0016。表と role は MitateDB の platform schema のもの (`mitatedbsvc_api` ほか) |
| 85 (27) | 受け付けは `ops.py`:2669-2710、一覧は adapter・launcher・`tests/control_plane_harness.py` |
| 86 (28) | denial は現行の `ResourceLimitError(limit_class="requests_per_minute")` (`cell.py`:343) の写像 |
| 87 (29)・93 (35) | platform pool (`main.py`:349)。認証の借用は `credential_store_postgres.py`、rate の呼び出しは `cell.py`:710 |
| 96 (38)・116 (58)・117 (59) | `MITATEDB_SLOT_DIR` / `MITATEDB_WORKERS` / `MITATEDB_CONTROL_WORKERS` |
| 111 (53) | 1 要求 1 本は `_CONCURRENCY_RESERVED` の対 (変異は「pre-auth の取得が立てない」) |
| 113 (55)〜115 (57) | `capabilities_document.py`:44・:322・:327、control は `control_plane.py`:1575-1577 |
| 121 (63)〜124 (66) | `python -m mitatedb_api.main --preflight` / `python -m mitatedb_api.control_main --preflight`。閉じる対象は served application の永続接続 (`backend_postgres.py`:293-294) と platform pool |
| 126 (68)・127 (69) | `MitateDB-api:data:<pid>` / `MitateDB-api:control:<pid>` |
| 128 (70) | `config.py`:300-319、`main.py`:345-349、`MITATEDB_THREAD_LIMIT` |
| 129 (71)・130 (72) | `platform_declarations.py`:1209-1235・:1318-、:993- |
| 131 (73) | F-1 の対の docstring は `config.py`:300-319 |
| 132 (74)・133 (75) | `ops.py`:1260・:1331・:1549 |
| 134 (76)・135 (77) | adapter の session と隔離 surface |

| # | 完了条件 (MitateDB だけ、または WP-2 と対でないもの) |
|---|---|
| 136 | 同名 helper を両 peer の `_ISOMORPHIC_TARGETS` に登録し、件数 pin を実測で更新し、両 peer の同型性テストが緑 (WP-2 の 78 の赤が消える。`OC` §1.5 の 38・40b。監督裁定 1) |
| 140 | 0016 は platform 単発で名が `_upgrade.sql` で終わらず、`ops apply-platform-migration` が platform 単発として受け付ける |
| 141 | **監査照合 (設計 §9 (e))**: N = 4 の role ごとの需要 (api role の platform pool と audit sink の per-call 接続、application の runtime / developer role の永続接続 × N、controlplane、auditreader) を設計 §7.3 の形で算え、`MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`:89-91・:113・:116 の値と並べる |
| 142 | `hold_in_flight` の保持中、platform pool の貸出数が 0 (裁定 42 の (n)) |
| 143 | 隔離 surface (`max_concurrency=3`) は session と別の slot directory を配線する (設計 §1.4 の (6)) |
| 144 | platform pool の既定の寸法は `MITATEDB_MAX_CONCURRENCY` に依らない (裁定 16) |
| 145 | **監査照合**: §5.3 で変異も監査照合も持たない行が 0 件 |

### 5.3 完了条件 → 変異 (`expect=red`。run = MitateDB)

- **M83〜M135・M137〜M139 は WP-2 の M25〜M77・M79〜M81 を MitateDB の対応箇所に掛けたもの** (差 58)。監査照合は 87・95・112・125・131・133・137〜139、141・145。

| 完了条件 | 変異 |
|---|---|
| 136 | **M136**: r2db 側の同名 helper の本体の 1 箇所を変える (MitateDB の同型性テストが赤) |
| 140 | **M140**: 0016 の名を `_upgrade.sql` で終える |
| 142 | **M142**: rate の借用を `hold_in_flight` の停止点を跨いで持つ |
| 143 | **M143**: 隔離 surface に session の directory を渡す |
| 144 | **M144**: pool の既定を `MITATEDB_MAX_CONCURRENCY` から導く |

§3.3 の `m` の行も本 WP の実装担当が走らせる。

### 5.4 道具の引数

§4.4 の `r2db-api/tests` を `MitateDB-api/tests` に、`-k` を MitateDB の id に替える。登録の後に `r2db-api/tests/test_audit_query.py` と `r2db-api/tests/test_r78_pool_wait_stats.py` も回す。

### 5.5 レビューの観点

§4.5 を MitateDB に読み替えたもの、移植した helper の正規化後の一致と登録 (136)、永続接続 × N の算術 (141)、`hold_in_flight` と pool (142)、隔離 surface の directory (143)。

## 6. 記録 (統合時に監督が埋める)

### 6.1 訂正註と監督裁定

**【監督裁定 1〜8 (2026-09-28、起草時)】** 起草の疑義 (a)〜(h) への裁定 (逐語)。起草前の裁定なので本文に反映した。

```text
1. (a) WP-2 と WP-3 は並行しない。順は WP-1 → WP-2 (r2db) → WP-3 (MitateDB)。WP-3 は WP-2 の同名 helper を正規化 diff で一致するよう移植し、`_ISOMORPHIC_TARGETS` の登録と件数 pin の更新は WP-3 だけが触る (WP-2 は登録しない。WP-2 の間、同型性テストは WP-2 の新 helper を読まない)。「並行 worktree 可」の文は削る。WP-1 と WP-2 は触るファイルの重なり 0 なら並行してよい。
2. (b)(c) 採る (adapter / launcher / part1 script の配線は WP-2・WP-3、pid 付き access log は WP-1)。
3. (d) 秒の位置は **61 の環** (index = s mod 61)。基点 base_s は単調 (裁定 37)。進める幅 shift = LEAST(61, GREATEST(0, s − base_s)) で、(base_s+1 .. base_s+shift) mod 61 の位置を 0 にしてから s mod 61 の位置に +1、shift = 61 なら全部 0。配列を詰め直さない。完了条件 29 の裁定待ちを消してこれに置き換える。他の (d) の扱い (AST pin、http plug は ceiling 1 / workers 1、表 7-2 の出所) は採る。
4. (e) control plane も env の同一変数から `--workers` を渡す: `R2DB_CONTROL_WORKERS` / `MITATEDB_CONTROL_WORKERS` (必須、値は 1。runbook はこれを 1 に固定する)。preflight は control でも workers ≤ `process_ceilings.control` を検査し、写像は control の 2 class についても「配線 かつ ceiling ≤ workers」の同じ helper を通す (裁定 4 の「伸ばさない」は保ち、裁定 11・39 の「常に明示・直書き禁止」を control にも及ぼす)。`WEB_CONCURRENCY` の入口は両 plane で閉じる。
5. (f) Class D に要る依頼者裁定の逐語は設計 §5 の Q-1 の裁定行 (「Q-1 は (A')、Q-3 は 1、Q-4 は (B)、Q-5 は行う で進めます。」) がそれに当たる。§1 でそこを指す (再転記しない)。WP-6 に R-18 行への【追記】(R-18 (c) の「共有 limiter」を rate にだけ採り、concurrency は host 共有 slot にした旨) を足す。
6. (g) 採る (runbook の確認手順として置く。完了条件 158 の文言は「配備先での確認手順を runbook に置き、開発機では systemd の無い旨を記す」)。
7. (h) 大きさ: 設計 §1・§2 の逐語転記を消し、`docs/design/MULTI_PROCESS_WORKER_V0_1.md` §1・§2 への 1 行の参照に置き換える (転記の規約は設計文書に掛かるもので作業指示書には掛からない)。逐語で残すのは 依頼者裁定 (§1 の指し先) と D-16 (§10) と本裁定だけ。完了条件と変異表は残す。目安 60 KB 以下。
8. (h) キー `MPW` は本書ローカルの略記として冒頭の「本書内の略記」に定義する (`OPERATING_CONDITIONS.md` §0 には足さない)。
```

- 番号の註: 裁定 3 の「完了条件 29」は本文でも 29、裁定 6 の「完了条件 158」は本文では 170 (control の配備の行を足して番号が動いた)。

### 6.2 実施と受け入れ

## 7. WP-4 — `--real-server <peer> --workers N` (実装担当) と計測 (監督)

**目的**: real-server plug を N worker で起動して測れる形にし (実装担当)、監督が rate の文の小実験と D-16 の計測を行う (§7.5・§10)。**読むべき正本**: 設計 §3 D-5、§7、§10 の裁定 17・30・31。R-101 作業指示書 §9・§10。**クラス**: B (全体 D)。**テンプレート**: `ROLES` の 2。

### 7.1 触ってよいパス

- `tools/perf_baseline.py` — `--workers` (既定 1、`--real-server` のときだけ)。launcher を workers N・宣言 data = N・control = 1 で起動、出力に N、各 run の後に pid 付き access log (WP-1) から worker ごとの受付数を 1 行、`concurrency` を上書きしない (裁定 31)。既存の行の書式・並び、200 以外で run を止める挙動 (:2279-2281)、`suite_lock` と使い捨て cluster は変えない。閾値を持たない (`RM` §4 の P-8)。
- `tools/tests/test_perf_baseline.py` — テストの追加だけ。**これ以外は 0 件** (launcher・両 peer・`tools/PERF_BASELINE_README.md` (WP-6))。

### 7.2 完了条件 (146〜154)

| # | 完了条件 |
|---|---|
| 146 | `--real-server <peer> --workers N` は launcher を workers N、宣言 data = N・control = 1 で起動し、supervisor の子が N 本 (設計 §7.2) |
| 147 | `--workers` を `--real-server` 無しで渡すと引数の誤り (終了コード 2) |
| 148 | run の出力に N が載り、N = 1 と N = 4 を出力だけで区別できる |
| 149 | 各 run の後に worker ごとの受付数 (pid ごとの 200 の数) を 1 行で出す (裁定 17) |
| 150 | launcher に渡す env は `concurrency` を上書きしない (裁定 31) |
| 151 | **監査照合**: 200 以外で run を止める挙動 (:2279-2281) の差分 0、止まった run は出力に残る |
| 152 | **監査照合**: `--workers` 無しと `--real-server` 無しの run の既存の行が 148 の追加分を除いて不変、既存テストが緑 |
| 153 | 各 run の後に launcher の process group の process が 0 本 (N = 4 の子を含む) |
| 154 | **監査照合**: §7.3 で変異も監査照合も持たない行が 0 件 |

### 7.3 完了条件 → 変異 (`expect=red`。run = tools)

| 完了条件 | 変異 |
|---|---|
| 146 | **M146**: launcher に `workers` を渡さない (設計 §6) |
| 147 | **M147**: `--real-server` 無しの `--workers` を受け付ける |
| 148 | **M148**: 出力に N を載せない |
| 149 | **M149**: 受付数の行を出さない |
| 150 | **M150**: env に `concurrency` の上書きを入れる |
| 153 | **M153**: run の後に launcher を止めない |
| 151・152・154 | **監査照合** |

### 7.4 道具の引数

§2.3 の形で、パスは `tools/tests/test_perf_baseline.py` と `tools/tests`。`tools/perf_baseline.py` の計測は実行しない。

### 7.5 監督の計測 (WP-2・WP-3・WP-4 の完了ゲートの後)

1. **rate の文の小実験** (裁定 30、設計 §7.3): 使い捨て cluster に 0015 / 0016 を当て、同じ credential の 1 行に 32 並行で rate の 1 文を流し、p50 / p95 を設計の表 7-5 に記す。**0.2 ms/文を超えたら計測に進まず再裁定する。**
2. 他の pytest と nginx を止める (`OC` §2 の 19。計測器の nginx は除く)。
3. peer ごとに N = 1 の K = 1 → K = 32 → K = 32、次に N = 4 の同じ 3 run (`tools/perf_baseline.py --real-server <peer> --workers N --warmup 3 --n 15 --concurrency K`。設計 §7.2)。`concurrency` は既定 32。
4. worker ごとの受付数を表 7-3 に (N = 4 で 4 worker すべてが受けたこと)。429 で止まった run は捨てて表 7-4 に記し、裁定 31 のとおり再検討する。
5. K = 1 の非退行 (`RM` §0.1.4 の 1): 完了ゲートの後に `--warmup 20 --n 200` (6 plug 21 行) を取り、§1.3 の直近基準値と同じ plug・op で比べて表 7-2 に記す。real-server plug の N = 1 / N = 4 の K = 1 も同じ表に行を足す (基準値は無い)。
6. 各 run の後、`pg_database` / `pg_roles` の差分 0、launcher の process group の process 0 本。
7. 記録は設計 §7.4 の表 7-1〜7-5。ホスト名・実 DSN・作業機の絶対パスを書かない。判定は §10 の規則だけで行う。

## 8. WP-5 — 配備物と runbook (実装担当)

**目的**: 両 plane の配備物に preflight と env からの `--workers`、data に slot directory を置き、両 runbook に 1 host の規律と開示を書く。**読むべき正本**: 設計 §3 D-1、D-3 (2')、§9 の (c)(d)(u)、§10 の裁定 4・10・11・20・26・27・33・36・39・40・42、本書 §6.1 の監督裁定 4・6。**クラス**: B (runbook は A、全体 D)。**テンプレート**: `ROLES` の 2。

### 8.1 触ってよいパス

- `r2db-api/deploy/systemd/r2dbsvc-api.service` — `ExecStartPre=` (同じ `EnvironmentFile=` (:53) で `python -m r2db_api.main --preflight`)、`ExecStart=` (:60) に `--workers ${R2DB_WORKERS}`、`RuntimeDirectory=<unit>/slots` と `RuntimeDirectoryMode=0700`。既存の hardening の行は変えない。
- `r2db-api/deploy/systemd/r2dbsvc-control.service` — `ExecStartPre=` (`python -m r2db_api.control_main --preflight`)、`ExecStart=` (:91) に `--workers ${R2DB_CONTROL_WORKERS}`。
- `r2db-api/deploy/env/api.env.example` (`R2DB_WORKERS`、`R2DB_SLOT_DIR`)、`r2db-api/deploy/env/control.env.example` (`R2DB_CONTROL_WORKERS=1`)。値は例示のみ。
- `MitateDB-api/docker/Dockerfile` — `USER` (:134) 所有の 0700 の slot directory と `MITATEDB_SLOT_DIR`。`CMD` (:145) の両方の枝を `set -e` (か `&&`) で繋ぎ、preflight の後に `exec uvicorn … --workers "${MITATEDB_WORKERS}"` (data) / `"${MITATEDB_CONTROL_WORKERS}"` (control)。
- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (:96-106 ほか)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`MitateDB-api/docs/cloud-run-cloud-sql.md` (Invariant 1 :1327- ほか)。
- `r2db-api/tests/` と `MitateDB-api/tests/` の新規の静的テスト各 1 本 (unit / Dockerfile / env の例の文面を読む。裁定 39)。**これ以外は 0 件。**

### 8.2 完了条件 (155〜171)

| # | 完了条件 |
|---|---|
| 155 | api の unit の `ExecStart=` は `--workers ${R2DB_WORKERS}` を持ち、数字の直書きが無い (裁定 39) |
| 156 | api の unit は同じ env で `python -m r2db_api.main --preflight` を走らせる `ExecStartPre=` を持つ (裁定 26) |
| 157 | api の unit は `RuntimeDirectory=` (slots) と `RuntimeDirectoryMode=0700` を持つ (裁定 27) |
| 158 | `api.env.example` は `R2DB_WORKERS` と `RuntimeDirectory=` と同じ path の `R2DB_SLOT_DIR` を持つ |
| 159 | control の unit の `ExecStart=` は `--workers ${R2DB_CONTROL_WORKERS}` を持ち、数字の直書きが無い (監督裁定 4) |
| 160 | control の unit は `python -m r2db_api.control_main --preflight` の `ExecStartPre=` を持つ (監督裁定 4) |
| 161 | `control.env.example` は `R2DB_CONTROL_WORKERS=1` を持つ (監督裁定 4) |
| 162 | Dockerfile は `USER` 所有の mode 0700 の slot directory を作り、`MITATEDB_SLOT_DIR` がそれを指す |
| 163 | `CMD` の data の枝は `--workers "${MITATEDB_WORKERS}"` を持ち直書きが無い (裁定 39) |
| 164 | `CMD` の data の枝は preflight の失敗で uvicorn に進まない (`set -e` か `&&`。裁定 41) |
| 165 | `CMD` の data の枝は `python -m mitatedb_api.main --preflight` を持つ (裁定 26) |
| 166 | `CMD` の control の枝は `--workers "${MITATEDB_CONTROL_WORKERS}"` を持ち直書きが無い (監督裁定 4) |
| 167 | `CMD` の control の枝は `python -m mitatedb_api.control_main --preflight` を持ち、その失敗で uvicorn に進まない (監督裁定 4) |
| 168 | **監査照合**: r2db の 2 runbook に、1 host、`R2DB_WORKERS` の必須と `process_ceilings.data` = workers (等しいときだけ `concurrency` が `enforced`。裁定 27)、`R2DB_CONTROL_WORKERS` = 1 に固定 (監督裁定 4)、両 unit の preflight と `RuntimeDirectory=` / `R2DB_SLOT_DIR`、SIGTTIN と SIGHUP の禁止 (再起動は stop / start。裁定 11・40)、`verify-declarations` の workers 検査は手動 (裁定 26)、接続予算は thread limit 基準 (裁定 16)、0015 の適用、`int[61]` の開示 (裁定 42)、rollout の重なりで保つもの・保たないもの (設計 §9 (d)) が在る |
| 169 | **監査照合**: MitateDB の runbook に、Invariant 1 を 1 host に改め `--max-instances=1` のまま `--workers` と `--cpu` ≥ workers で伸ばす (Q-4 (B)、裁定 20)、`MITATEDB_WORKERS` と `process_ceilings.data` = workers、`MITATEDB_CONTROL_WORKERS` = 1、slot directory、`CMD` の preflight、SIGTTIN と SIGHUP の禁止、Cloud Run が一時的に max-instances を超えうる件を「推測」と明記した 1 行 (裁定 33)、接続予算 (永続接続 × N、完了条件 141)、0016 の適用、`int[61]` の開示、rollout の重なり (R-52 の射程) が在る |
| 170 | **監査照合 (監督裁定 6)**: 配備先での確認手順 (unit の停止で `RuntimeDirectory` が消えること、preflight の自己検査が通ること) を runbook に置き、開発機では systemd の無い旨を記す |
| 171 | **監査照合**: §8.3 で変異も監査照合も持たない行が 0 件 |

### 8.3 完了条件 → 変異 (`expect=red`)

| 完了条件 | 変異 | run |
|---|---|---|
| 155 | **M155**: `--workers 4` の直書き | r2db |
| 156 | **M156**: api の `ExecStartPre=` を外す | r2db |
| 157 | **M157**: `RuntimeDirectoryMode=0755` | r2db |
| 158 | **M158**: `R2DB_SLOT_DIR` を消す | r2db |
| 159 | **M159**: control の `--workers 1` の直書き | r2db |
| 160 | **M160**: control の `ExecStartPre=` を外す | r2db |
| 161 | **M161**: `R2DB_CONTROL_WORKERS` を消す | r2db |
| 162 | **M162**: slot directory の mode を 0755 | MitateDB |
| 163 | **M163**: data の `--workers 4` の直書き | MitateDB |
| 164 | **M164**: data の preflight と uvicorn を `;` で繋ぐ | MitateDB |
| 165 | **M165**: data の preflight を外す | MitateDB |
| 166 | **M166**: control の `--workers 1` の直書き | MitateDB |
| 167 | **M167**: control の preflight を外す | MitateDB |
| 168〜171 | **監査照合** | — |

### 8.4 道具の引数

§2.3 の形で、パスは両 peer の新規の静的テスト。変異は peer ごとに run を分ける。

## 9. WP-6 — 記録 (監督)

**触るパス**: `RM` (§8 の R-113 :533・R-101 :521・R-18 :438 の行と版、版数ログの回転)、`security/CONTROL_MAPPING.md` (:5、:711-712、:819、:904、:988)、`conformance-tests/COLLECTION_FLOOR`、`tools/PERF_BASELINE_README.md`、引き継ぎ書 `docs/work-orders/HANDOVER_<日付>*.md`、本書 §6。

| # | 完了条件 (すべて監査照合) |
|---|---|
| 172 | R-113 行に【追記】(WP-1〜WP-5 の結果、完了ゲートの集計行、§10 の判定)、版上げ、版数ログの回転 (`OC` §1.8 の 56、§1.13 の 75、§1.16 の 78) |
| 173 | R-101 行に【追記】、閉止は §10 の判定のとおり (Q-5) |
| 174 | R-18 行に【追記】: R-18 (c) の「共有 limiter」は `requests_per_minute` にだけ採り (PostgreSQL の行)、`concurrency` は host 共有の slot にした (監督裁定 5) |
| 175 | `security/CONTROL_MAPPING.md` 3.7: SI-08 の r2db (:711-712)・MitateDB (:904) の写像の Control 主張を設計 D-3 の置き場 (rate = PG の行、`concurrency` = host 共有の slot で ceiling ≤ workers のときだけ `enforced`、control の 2 class は process 内の窓) に、C-26 の開示 (:988) を新条件と 1 host の規律に改め、:819 の件数 pin のテスト名を追随。`conformance-tests/test_control_mapping_register.py` が緑 |
| 176 | `COLLECTION_FLOOR` が完了ゲートの collected の実測値 (`OC` §1.3 の 25) |
| 177 | `tools/PERF_BASELINE_README.md` に `--workers`、計測は既定の `concurrency` 32 (裁定 31)、worker ごとの受付数の行、access log の置き場 |
| 178 | 設計 §7.4 の表 7-1〜7-5 が §7.5 の実測で埋まっている |
| 179 | 引き継ぎ書がファイル名で指され (`OC` §1.8 の 58)、「裁定」節に指摘の 1 件ごとの裁定 (`OC` §1.15 の 77) |
| 180 | 172〜179 の照合対象 (`git diff` と集計行) が §6.2 に在る |

## 10. 計測の判定規則と R-101 の閉止 (**監督**)

### 10.1 判定規則 (設計 §7.1 = R-101 作業指示書 §10.1 の D-16、逐語。計測前に固定し、計測後に動かさない)

```text
D-16 閉止の判定規則 (計測前に固定): real-server plug で K=1 と K=32 (`--warmup 3 --n 15`) を取り、K=32 は 2 run 取る。query の p50 の K=32 / K=1 の比が両 peer で K=32 の 2 run とも 8 倍以内 = R-101 閉止 (RM §0.1.4 の 2 の改訂形)。ε (K=32 の 2 run の相対差) と δ = max(10%, 2ε) は記録だけで、判定には使わない。本変更セットでは server は 1 process なので 8 倍は満たさない見込み — その実測を設計メモ v0.3 §6 に逐語で残し、R-113 (multi-process、規模 L) の出発点にする。
```

### 10.2 当てはめと照合

当てはめは設計 §7.1 の 3 項 (判定は N = 4 の行だけ、N = 1 は対照、D-16 の最後の文は本件の判定に使わない)。監督は次を照合する。

1. 表 7-5 が 0.2 ms/文以内 (超えたら計測に進んでいない。裁定 30)。
2. 表 7-1 の N = 4 の行で、両 peer とも K = 32 の 2 run の比がともに 8 以下なら **R-101 を閉じる** (Q-5)。どれか 1 つでも 8 を超えれば閉じず、実測を R-101 行に【追記】する。
3. 表 7-3 で 4 worker すべてが受けている。表 7-4 に捨てた run と理由が在る。
4. 表 7-2 で `RM` §0.1.4 の 1 の判定 (p50 +40%、p95 +50%) を行ごとに記している。
5. 規則の文言が §10.1 と同じ。

## 11. 本書の範囲外 (列挙のみ)

- **R-102** (MitateDB の cell lock の待ち)。混ぜない (設計 §1)。
- **R-52** (rollout の重なり)。本件で保つもの・保たないものは WP-5 の runbook に開示し、Cloud Run の revision の重なりで 2 host になる間の slot の非共有は R-52 の射程 (裁定 25・33、R-52 行の v1.130 の【追記】)。
- **R-114** (`spec/data-service-api.v1.json`:925 の "fixed window" と実装の sliding の食い違い)。直さない (裁定 13)。
- **複数 host の共有 limiter**。slot の射程は 1 host (設計 D-3 (2)、裁定 10)。複数 host は `deployment_required` の宣言か、R-18 (c) の続きとして別に起票する。
