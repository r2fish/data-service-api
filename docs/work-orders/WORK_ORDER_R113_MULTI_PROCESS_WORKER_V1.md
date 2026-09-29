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

**監督裁定 9〜16 (2026-09-28、WP-1 の実装報告の逸脱 1〜8 への裁定)**

9. preflight は両 plane で常時実行する (逸脱 1)。§6.1 の裁定 4 (control でも workers ≤ ceiling を検査) の帰結であり、完了条件 5 の「data の uvicorn より前」は control にも同じ順で読む。
10. access log の pid 付き FileHandler は `UVICORN_LOG_CONFIG` (env) で注入し、`start_uvicorn_subprocess` の引数は `workers` 以外増やさない (逸脱 2)。採る。
11. probe entity 用の developer credential 発行を launcher の `_ensure_provisioned` に足す (逸脱 3)。§3.1 の範囲内。採る。
12. WP-1 の `_run_preflight` は `python -m <package>.main --preflight` を呼び、現行 (WP-2/3 前) は module-level の `app = build_app()` が同じ検査を同じ権限で走らせて終了コードを決める (逸脱 4)。**WP-2 / WP-3 の完了条件に足す: `--preflight` entry を足した後も launcher 側を変えずに完了条件 5・13 が緑のままであること (entry は module の `app` を使い回し、引数を解釈して 0 / 非 0 で終わる。設計 §10 の裁定 41)。**
13. lock 保持の接続の `application_name` は `"<peer>:lockholder:<pid>"` とし、WP-2 / WP-3 の `"<peer>:<plane>:<pid>"` と衝突させない (逸脱 5)。採る。完了条件 15 の絞り込みは data plane の名前だけを数える。
14. `CONDITIONS.md` / `CONDITIONS_HISTORY.md` は cell 長 3000 の制約下で追記方式でよい (逸脱 6)。条件: 既存の文が偽にならないこと (C-26 (4) の「ceiling 2 → deployment_required」は workers 1 のとき今も真)。偽になる文が出たときは旧文を history へ移す通常の訂正に戻す。レビュー担当が (e) で確かめる。
15. 新 method 名は両 peer 同名同引数 (逸脱 7)。採る (launcher は `_ISOMORPHIC_TARGETS` の対象外だが、対称性はレビューの観点 (g))。
16. `sweep_orphans` の `PermissionError` を pid 再利用として許容する (逸脱 8)。採るが、レビュー担当が (b) で「本当の残骸を見逃さない」ことを確かめる。許容は `os.getpgid(pid) == pid` の場合に限る現行の形を保つ。
17. 完了条件 22 の赤リストは §3.2 の本文 (9・11・14〜17) が正で、発注プロンプトの「5・13」は誤り (実測は本文と一致)。

**監督裁定 18〜19 (2026-09-28、WP-1 コードレビュー 1 回目 (18 件、全件「直す / 採る」。裁定表は監督保管 `r113_wp1_rework_1.md`) の帰結)**

18. **訂正註: §3.2 の完了条件 14・17 と §3.3 の「429」は HTTP status ではなく error envelope の `code == "LIMIT_EXCEEDED"` かつ `details.limit_class` を指す** (契約は LIMIT_EXCEEDED の HTTP status を定めない。r2db は 429、MitateDB は 413)。本文は書き換えない。
19. **WP-2 / WP-3 の完了条件に足す**: (i) control plane の `--preflight` entry は app を実際に構築して起動時の検査を走らせる (r2db の `control_main` は app を遅延構築するので、entry が構築を呼ばないと preflight が空振りする = レビュー F4)。(ii) `--preflight` entry を足した後も WP-1 の launcher を変えずに完了条件 5・13 と control の preflight 観測テストが緑であること (裁定 12 の再掲)。(iii) F-15 / F-16 の起動経路 (launcher) が渡す workers / slot の env を、`build_app()` の必須 env の集合と一致させる (レビュー F9)。

**監督裁定 20 (2026-09-28、WP-1 差し戻し 1 の報告: レビュー F18 = 宣言分岐)**

20. 完了条件 9・11 と新条件 (a)(b) (14〜17) は **宣言で分岐する** (設計 §10 の裁定 12、本書 §6.1 の (甲))。`limit_enforcement` が `enforced` なら (a)(b) を駆動、`deployment_required` なら現行の写像の検査だけを行い分岐を記録して緑、他の値は赤。空振り禁止 (`OC` §1.5 の 32) は launcher の「配線した (slot directory + workers = ceiling)」accessor との cross-check で担う: 配線したのに `deployment_required` は赤 (WP-2/3 前は期待の赤 = 完了条件 22)、配線していないのに `enforced` も赤。C-30 の版分岐と同じ書き方。差し戻し 2 で実装。

**監督裁定 21 (2026-09-28、WP-1 コードレビューの再確認 1b / 1c)**

21. WP-1 のコードレビュー (opus): 1 回目 18 件 (F1〜F18)、再確認 1b で新規 4 件 (N1〜N4)、再確認 1c で全件閉止・新規 0。裁定: F14 (leader が死んだ後の process group を `sweep_orphans` が掃除できない = cmdline に識別子が無い) は **既知の穴** (`OC` §1.12 の 71: 製品の欠陥がゲートを抜ける穴ではない) として同関数の docstring の `Known gaps` に置き、効かない枝は削った。N1 は launcher の既存 `.name` (`"r2db-api"` / `"MitateDB-api"`) を peer token に使う (WP-2 の 68 / WP-3 の 126 と同値)。N3 は残骸テストを ceiling 2 / workers 2 に広げて (6) の「nor any of its own workers」を実測にした。N4 (pt log が `$SP` の外) は観察 = 発注プロンプトに `export SP` を必ず書く。観察 3 点 (レビュー 1c): C-05 の int[61] の文は WP-2/3 の後に現物と一致する (WP-1 だけを main に統合しない)、C-26 の行は control の preflight fail-fast に触れないが偽ではない、C-26 の残り 21 字 (次の訂正は参照を HISTORY へ)。

**監督裁定 22〜27 (2026-09-28、WP-2 の実装報告 1 回目の逸脱 (a)〜(f) への裁定。裁定表は監督保管 `r113_wp2_rulings_1.md`)**

22. (a) 0015 の rate 加算は PL/pgSQL 関数 `credential_request_rate_admit` でよい (api role pool の autocommit 1 文の呼び出し、SECURITY INVOKER、`clock_timestamp()` 1 回、環の算術は裁定 3 と同値)。設計 D-3 (1) の「1 文」はこの性質を指す。migration ヘッダの経緯トークンは既存 migration と同じ慣行 = 観察。
23. (b) 【裁定 28 で撤回】F-16 の倍率を control にも呼び出し元で掛ける。
24. (c) provenance regex の誤書き換えは復元済み (レビュー担当が 65 hunk を囲みの symbol に写し、触った symbol の外の docstring / comment の変更 0 件を実測)。
25. (d) `record_rate_and_check` の流用 History 行の削除を受理 (新規の塊に History 行は要らない)。
26. (e) CH-0322 の訂正記録は全文置換 1 件でよい (設計 `CODE_COMMENT_PROVENANCE_V1` §9.3 規則 3 は `old` がちょうど 1 回現れれば足りる)。ただし記録の `old` が基点の塊と一致せず赤だったので差し戻し。
27. (f) `--base` の残る赤のうち §4.1 (1) の AST 差分と `old 0, new 1` の新規塊 (Known gap 3) は受理。登録済みの塊 (CH-0137 / CH-0257 / CH-0322) の直後への書き足しと偽になった本文は既知の穴ではなく差し戻し (CH-0137 は訂正記録の上で言い換え、CH-0257 は切り離し)。

**監督裁定 28〜36 (2026-09-28、WP-2 コードレビュー 1 回目 (14 件、F1〜F14。裁定表は監督保管 `r113_wp2_rulings_2.md`、レビューは `r113_wp2_code_review_1.md`) の帰結)**

28. **訂正註 (裁定 23 を撤回)**: F-16 の process 数の倍率は `check_role_connection_limits` の中に置く (keyword `process_ceilings`。api / application の床 × `process_ceilings.data`、controlplane / auditreader の床 × `process_ceilings.control`)。3 つの呼び出し元 (main / control_main / ops `verify-declarations`) は `pool_size` を掛けずに渡す。control の F-18 の `pool_size` は `ResourceLimits().concurrency` ではなく data と同じ `role_pool_size(実効 thread limit)`。実効 thread limit の読み方は `limits.py` の 1 関数 (未設定は既定、空でない不正値は fail-loud) に統一し 3 箇所が使う (裁定 25 の (i))。**完了条件を足す**: 71c (control の F-18 の下限は data と同じ式)、72c (control の F-16 の床 = 定数の床 × `process_ceilings.control`)、74b (`verify-declarations` の F-16 も同じ関数・同じ倍率)。変異 M71c (control の `pool_size` を `ResourceLimits().concurrency` に戻す)、M72c (control の倍率を掛けない)、M74b (ops が 1/1 を渡す)。
29. **訂正註 (§4.1)**: WP-2 は `conformance-tests/test_c26_composition_root.py::test_c26_ceiling_maps_to_limit_enforcement` の 1 テストだけ触ってよい。WP-2 の rate の配線で real-server launcher の ceiling 2 の `requests_per_minute` は `enforced` になる (設計 D-3 (4)) ので、期待値は裁定 20 と同じ宣言分岐 + launcher の rate 配線 accessor との cross-check にする。`CONDITIONS.md` の C-26 は WP-6 で監督が直す。
30. `_declared_concurrency` → `_declared_pool_size` の改名は残す (名が事実と一致することを優先)。改名で scope の鍵が変わるため `--base` の (2) は赤のまま残る。報告で「改名 (scope key)」と分類し、検査器の Known gaps への追記は WP-6 で監督が行う。
31. CH-0174 (削除した定数 `_IN_MEMORY_PROCESS_WIDE_LIMIT_CLASSES` の塊) は定数と一緒に削除する。
32. code に追随した CH 無しの塊の書き換え (ops.py 2、limits.py 1、platform_declarations.py 2、main.py 1) は code を変える WP に固有として受理 (Known gap 3 と同じ扱い)。新しい文が事実で現在形であることが条件。
33. F8 の壊れた文と経緯語は直す (完了条件 73・80)。`docs/code-history/r2db-api/ops.md` の reason 行は訂正記録の場所なので観察。
34. **訂正註 (裁定 3)**: +1 する位置は `s mod 61` ではなく `GREATEST(base_s, s) mod 61` (通した秒 = 行の現在の基点)。lock を待った古い秒の要求も通した時点の秒に入る。完了条件 29 の逐語もこの形。
35. `real_server_mitatedb.py::stop` の同型性の赤 (WP-2 の変更ではない) は、差が r2db 側なら WP-2 で揃え、MitateDB 側なら WP-3 で揃える。
36. F13: `DataService` は `concurrency_configured=True` かつ slot 未配線を `ValueError` にする (**完了条件 56b**、変異 = 検査を外す)。F14: 完了条件 75 の開示は `verify-declarations` の docstring に置く。

**監督裁定 37〜39 (2026-09-29、WP-2 差し戻し 1 の報告の逸脱への裁定。裁定表は監督保管 `r113_wp2_rulings_3.md`)**

37. main.py の `_thread_limit_from_env` は登録済み同型 helper なので本体を残し、`limits.thread_limit_from_env` (control_main / ops が使う) との同値を 1 テストで pin する (**完了条件 70b**、変異 M70b = 共有関数の 1 分岐を変える)。裁定 28 の (ii) の「3 箇所が使う」はこの形で満たす。
38. service.py の「before this WP」2 文は基点 74d90f3 に在る文で WP-2 の追加ではない (観察)。
39. **訂正註 (裁定 31)**: CH-0174 の塊は削除せず、訂正記録の上で `resolve_limit_enforcement` を説明する現在形の文に言い換える。`--base 74d90f3` の `capabilities_document.py:10` の残る赤は基点のソース本文と受け皿の原文の不一致 (WP-2 より前) の顕在化 = 基点由来。WP-2 では直さず引き継ぎ書に観察として残す。

**監督裁定 40 (2026-09-29、差し戻し 1 の報告の逸脱 (f)(g)。裁定表は監督保管 `r113_wp2_rework_1b.md`)**

40. 完了条件 76 / 77 は http plug の adapter の session と隔離 surface が配線していることの観測であり、composition root (`build_app()`) のテストでは代替できない (代理指標の禁止、`OC` §1.7 の 52)。composition root 側のテストは **76a** として残し、76 / 77 は adapter の session (`hold_in_flight` で保持中の slot の flock、credential の rate 行) と隔離 surface (session と別の directory) で観測する。変異 M76 / M76i / M77 は adapter 側の配線を外す形。

**監督裁定 41〜42 (2026-09-29、WP-2 再確認 1b (G1〜G8。裁定表は監督保管 `r113_wp2_rulings_4.md`、レビューは `r113_wp2_code_review_1b.md`) の帰結)**

41. **訂正註 (§4.1)**: launcher `real_server_r2db.py` が controlplane / auditreader の CONNECTION LIMIT を 32 / 8 に上げる ALTER ROLE を受理する (C-26 の lifecycle が control の ceiling 2 を宣言するので、裁定 28 の倍率の下で必要なテスト環境の provisioning)。製品側は migration を足さない (0013 の値は control 1 process の値。ceiling ≥ 2 の配備は F-16 が要る床を名指しで報告する)。**WP-5 の完了条件に足す**: runbook に「`process_ceilings.control` ≥ 2 は controlplane ≥ 16 × control、auditreader ≥ 4 × control の CONNECTION LIMIT が要り、F-16 が正確な床を報告する」の 1 段。
42. **訂正註 (裁定 39)**: CH-0174 の `--base` の (3) の赤は訂正記録の `old` を第 1 文だけにすれば消える (レビュー担当の clone 実測) ので WP-2 で直す。「基点由来」の分類を撤回。

**監督裁定 43 (2026-09-29、WP-4 の実装報告 1 の逸脱 (a)〜(g)。裁定表は監督保管 `r113_wp4_rulings_1.md`)**

43. WP-4 の逸脱 (a) stub テンプレートへの `workers=` / access log accessor の追加、(b) `REALWORKERS` の 1 行 (REALCPU の直後)、(c) 受付数の窓 (sanity の後〜最後の group、止まった run でも出す)、(d) process group の特定 (`ps` の前後差分、stop 後 10 s、残骸は stderr + 終了コード 1)、(e) `--workers` < 1 は終了コード 2、(f) 146 は stub で観測 (本物の N 本は WP-1 と表 7-3)、(g) 既存コメントの追記、をすべて受理。疑義 2 点 (子の数を道具が数える、成功時の 1 行) は §7.1 の範囲外で採らない (観察)。

**監督裁定 44 (2026-09-29、WP-4 コードレビュー 1 (4 件。裁定表は監督保管 `r113_wp4_rulings_2.md`、レビューは `r113_wp4_code_review_1.md`) の帰結)**

44. 表 7-4 の件数は `REALWORKERS` 行の非 200 の status ごとの件数 (access log から) で埋める (**完了条件 149b**、変異 M149b)。§7.5 の 4 と表 7-4 の「429」は LIMIT_EXCEEDED の意 (r2db 429 / MitateDB 413、裁定 18)。`ps -e` は macOS の legacy モードで全 process を列挙しないので `ps -A` に改め、start 後に launcher の process group を観測できなければ終了コード 1 の番兵を置く (**完了条件 153c**、変異 M153c)。zombie は残骸に数えず件数だけ情報として出す。nginx は道具の検査に入れず、§7.5 の 6 に「nginx の残存 0 (`ps` で確認)」を足す (訂正註)。

**監督裁定 45 (2026-09-29、WP-4 差し戻し 1 の報告の逸脱 (a)〜(f)。裁定表は監督保管 `r113_wp4_rulings_3.md`)**

45. WP-4 差し戻し 1 の逸脱 (a) 非 200 の件数は status 100〜599 の順問い合わせ (非 200 が無ければ問わない)、(b) group stub の拡張、(c) zombie の観測テストと M153z、(d) 153c は monkeypatch の stub で観測、(e) group 候補から zombie を除く、(f) docstring の「live」削除、をすべて受理。再確認は次チャット。

**監督裁定 46〜47 (2026-09-29、WP-4 再確認 1b (新 1〜6。裁定表は監督保管 `r113_wp4_rework_2.md`、レビューは `r113_wp4_code_review_1b.md`) と再確認 1c (指摘なし、観察 3。`r113_wp4_code_review_1c.md`) の帰結)**

46. **訂正註 (裁定 45 の (e) を撤回)**: launcher の process group の leader 候補から zombie を除かない (start の最中に leader が死に子が残った group が残骸検査から外れるため。レビュー担当の probe で孤児 2 本が生存のまま残骸 0 を実測)。zombie を残骸に数えない扱い (裁定 44) は変えない。**完了条件を足す**: 148b (止まった run の `REALWORKERS` 行が `concurrency=<K>` を持つ)、149c (非 200 が 2 種の run で `non_200=429:2,500:1`)、149d (分類できない行が n 本の log で `unclassified=<n>`。`unclassified=` は常に出す)、153d (start の最中に leader が exit し子が残った group を残骸として報告し終了コード 1)。変異 M148b・M149c・M149d・M153d。client の timeout (599) で止まった run では件数が 1 時点の値にならない旨を docstring に置く。stub の accessor は status を stub server の記録から読む。**訂正註 (§7.3)**: §7.3 の表に、裁定 44 と本裁定で足した変異 M149b・M153b・M153c・M153z・M148b・M149c・M149d・M153d を読み足す (154 の「変異も監査照合も持たない行が 0 件」は足した完了条件を含めて読む)。
47. 差し戻し 2 の逸脱 (a) `unclassified` は `max(remaining, 0)`、(b) 分類できない行は stub が JSON でない行で作る、(c) status を書くのは非 dropped の query 行だけ、(d) 153d の stub は group を 2 つ起こす、(e) M148b の new、(f) `ps` の呼び出しに timeout、をすべて受理。再確認 1c の観察 1 ((a) の丸めで docstring の文が事実と合わない) は監督が docstring に 1 句足して直した。観察 2 (§7.3 への転記) は裁定 46 の訂正註。観察 3 (`tools/tests` の共有 pin 4 件は root の gate の外) は WP-6 で監督が pin を更新し、`tools/tests` を gate と別に回す (§2.2)。

**監督裁定 48〜50 (2026-09-29、WP-3 の実装報告 1 の逸脱 (a)〜(m)・疑義 3 件、コードレビュー 1 (F1〜F8。裁定表は監督保管 `r113_wp3_rulings_1.md`、レビューは `r113_wp3_code_review_1.md`)、設計 裁定 43 (設計 §10.7。設計レビューは `r113_design_review_43.md`) の帰結)**

48. WP-3 の逸脱 (a) launcher `real_server_mitatedb.py` の ALTER ROLE (controlplane 32 / auditreader 8。裁定 41 と同じテスト環境の provisioning、監督の事前裁定)、(c) M94 / M94b、(d) M142、(e) M143、(f) M121b / M122b / M13m、(g)(h) テストの追加と既存テストへの割り当て、(i) 一時 probe、(k)、(m) を受理。(b) M93 は代理変異なので直す (F4)。疑義 (2): F-18 の下限は登録 application ≥ 1 で 112、設計 §7.3 の 64 は登録 0 の形で、runbook は application の床を含む式を書く。疑義 (3) と F6 (MitateDB の application role の床は実需要より大きい) は観察 (保守側、改定前より小さい)。
49. コードレビュー 1: F1 (`security/CONTROL_MAPPING.md` の test 名参照 5 件) と F2 (`tools/tests` の共有 pin 4 件) は完了ゲートの前に監督が直す (§9)。F3 (`_declared_pool_size` の同型登録漏れ、件数 pin 192、変異 M136b)、F4 (認証の借用の入れ子を行動で赤に。変異 M93c、r2db は M35c)、F7 (src に残る作業指示書の番号を両 peer 同時に性質の言葉へ)、F8 (87b / 29b のテストの同期を lock 待ちの観測に) は実装担当が直す。F5 は直す: **完了条件を足す (両 peer)** — (m1) rate の関数が無い platform で data plane の `build_app()` と `--preflight` は適用すべき migration (r2db 0015 / MitateDB 0016) の名を挙げて失敗する、(m2) 関数は在るが data plane の role に EXECUTE が無いときも同じ、(m3) 検査は読み取りだけで `verify-declarations` の検査の一覧には足さない。変異 Mm1・Mm2。
50. **訂正註 (設計 裁定 43、§5.1、完了条件 52 / 110)**: slot の走査を `scan` の lock で host 内に直列化する (設計 §10.7 の逐語)。**§5.1 の「r2db の src は触らない」の例外**として、WP-3 の差し戻しは `r2db-api/src/r2db_api/concurrency_slots.py`・`ops.py` (コメント)・起動時の検査に要る r2db の src・`r2db-api/tests/` を触ってよい。完了条件 52 (MitateDB は 110) の「待たずに 429」は「slot の空きを待たずに 429 (`scan` の待ちは期限内)」と読む。**完了条件を足す (両 peer)**: s1-a / s1-b (走査の途中の解放と取得を挟む決定的な再現で拒否が出ない。同じ process の別 thread と別 process の 2 形)、s7 (slot の保持中に別の取得が成功する)、s2 (`scan` の期限切れは `SlotBackendError` → 503)、s2e (他の errno・open の失敗・symlink は待たずに `SlotBackendError`)、s3 (`scan` の fd はどの経路でも閉じる)、s4 (SIGKILL された保持者の後で取得できる、監査照合)、s5 (`scan` は保持の観測に混ざらない)、s8 (docstring の費用と待ちの文、監査照合)。変異 Ms1・Ms1f・Ms1p・Ms7・Ms2・Ms2n・Ms2e・Ms2s・Ms3・Ms5。**§7.5 に足す (監督の実測)**: 統合後に C-32 (b) を両 peer で各 24 drive 以上回し `other` が 0 (補強。未修正の拒否率 3/14400 に対し 24 drive の見逃しは約 0.25%。証明は s1)。**WP-5 の runbook に足す**: slot directory の中身は `slot-<i>`・`selfcheck`・`scan`、単独の worker を SIGSTOP・debugger で止めない (止めている間、各要求は最大 1 s 待って 503 になる)。

**依頼者裁定 (2026-09-29) と監督裁定 51 (WP-5 コードレビュー 1 の F3 = MitateDB の Gate-0 inventory の需要の算術)**

- 事実: `MitateDB-api/src/mitatedb_api/ops.py` の inventory の項目 (8) は接続の需要を宣言値の `concurrency` を基準に数える (api は process あたり 2 × `concurrency`、application role は `concurrency`)。既定の 32 では、旧 1 process + 新 W process の rollout が W ≥ 2 で api role の CONNECTION LIMIT 132 を超え、必ず blocked になる。起動時の検査 (F-16 / F-18) は thread limit 基準 (裁定 16・28) で、inventory だけが基準を異にする。
- 監督が示した選択肢: (A) R-113 の中で inventory の需要の算術を起動時の検査と同じ基準に揃える (受理済みの Gate-0 の道具と手順を変えるので受理のやり直しが要る)、(B) runbook に開示して別に起票する。
- 依頼者裁定 (逐語): 「(A)で進めてください」
- 同日の依頼者裁定 (逐語): 「Sonnet の週次上限 (2026-10-03 20:00 JST まで) の間、opusで続けてください」(実装担当と読解の調査を起動時の `model` 指定で opus にする。役割定義と `ROLES` の役割表は変えない)。

51. inventory の修正は **WP-7** として本書に足す (設計は `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` の追補、設計レビュー 1 回、実装担当、コードレビュー、Class D)。順は WP-3 の統合の後。§11 の「R-52 (rollout の重なり) は範囲外」は保つ: WP-7 が変えるのは inventory の需要の算術の基準と入力だけで、rollout の重なりで保つもの・保たないものの規律は変えない。runbook §10 の再受理は依頼者が行う (§10.8 は「not accepted」のまま統合する)。

**監督裁定 52〜54 (2026-09-29、WP-3 の再確認 1b / 1c / 1d、WP-5 のコードレビュー 1 / 1b、WP-7 の設計、実装担当のモデル)**

52. WP-3 の再確認 1b (指摘 6 件)・1c (2 件)・1d (1 件) はすべて「直す」(裁定表は監督保管 `r113_wp3_rework_1b.md`・`r113_wp3_rework_1c.md`・`r113_wp3_rework_1d.md`): `scan` の open の close-on-exec を固定するテスト (s2c)、`scan` の待ちと候補の区間の割り込みで fd を閉じる (s3b)、保持が決まった slot の fd を `scan` の close の後の例外で閉じる (s3c)、slot の backend の失敗の log は process ごとに間隔 1 s あたり高々 1 行で抑えた件数を載せる (s9。裁定 50 と設計 裁定 43 の「message が名指しする」は、この log の行で運用者に届く)、既定の時計と実体の共有の固定、完了条件 72 のテストの docstring、src に残る作業指示書の番号 (R-113 の追加行だけ)。同型登録の件数 pin は 198。差し戻し 1d (テスト 2 本と docstring の 1 文) は監督が差分と変異の log を照合して閉じた。
53. WP-5 のコードレビュー 1 (F1〜F9) と再確認 1b (N1〜N6) の裁定 (裁定表は監督保管 `r113_wp5_rework_1.md`): **訂正註 (§8.1)** 触ってよいパスに `r2db-api/deploy/scripts/lint_deploy_assets.sh` を足す。MitateDB の 0016 は runbook §10 のゲート付き手順に入れ (§10.6・§10.7・§10.10.1 の step 7a)、表の版数は 5 / 5 / 8、§10.8 は「not accepted」。**完了条件を足す**: worker 数の変数の既定値が unit・Dockerfile・env の例のどこにも無い (変異 M155d・M159d・M163d・M166d)。N1 (統合の順) は WP-3 → WP-5 の順で統合し、両 peer の `main.py` に起動時の検査の呼び出しが在ることを確かめた。N3・N4 は監督が直した。
54. **訂正註 (監督裁定 51、依頼者裁定 2026-09-29 の 2 件目)**: WP-7 の設計は `docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md` (別ファイル) に置いた。節は本書 §12。Sonnet の週次上限は、監督が 2026-09-29 にこのチャットのアカウントで確かめたところ成り立たない (Sonnet の起動は成功し、アカウントの利用状況に Sonnet の上限の表示が無い。前の引き継ぎ書の記述は別のアカウントの状態と見られる)。依頼者裁定の前提が成り立たないので、WP-3 の差し戻し 1d 以降の実装担当は `ROLES` の役割表どおり sonnet で起動する。それまでの実装担当 (WP-3 の再開〜差し戻し 1c、WP-4 の差し戻し 2、WP-5 の初回と差し戻し 1) は opus である。

**依頼者裁定 (2026-09-29) と監督裁定 55 (§7.5 の計測と §10 の当てはめ)**

- 依頼者裁定 (逐語): 「R-101は閉じない」
- 依頼者の指示 (同日、逐語): 「孤児の nginx と uvicorn は止めてください」(2026-09-14・09-16 起動の conformance の socket harness の nginx 50 本と uvicorn 7 本。親が 1 のものだけに SIGTERM。2026-09-04 起動の常設のローカル MitateDB は対象外)。

55. §7.5 の実測は設計 §7.4 の表 7-1・7-3・7-4・7-5 のとおり。§10.2 の照合: 1 (表 7-5 は直列の 1 文あたり 0.079〜0.083 ms で 0.2 ms の内側)、3 (表 7-3 で 4 worker すべてが受け、表 7-4 は捨てた run 0)、5 (規則の文言は §10.1 と同じ) は成立。2 は、正式の run (手順どおりの 1 回目) では両 peer とも K = 32 の 2 run の比が 8 以下 (r2db 6.78 / 7.24、MitateDB 7.60 / 7.40) だが、同じ手順の繰り返し 2 回では 8 を超える比が出た (最大 10.30) ので、依頼者裁定により **R-101 は閉じない**。R-101 の行には実測と「worker の外に直列の区間が残る」を【追記】する (§9 の 173)。4 (表 7-2、K = 1 の非退行) は完了ゲートの後に取る。計測の前に機械全体の負荷 (load average) を確かめる手順を §7.5 の 2 に読み足す (1 回目の 12 run は load average 12〜15 の下で取り、無効として捨てた)。§7.5 の 6 の「nginx の残存 0」は各 run の後に `ps -A` で確かめ、全 run で 0 だった (裁定 44)。C-32 (b) の 24 drive (裁定 50) は両 peer とも `other` = 0 (peer あたり 28800 要求)。

**監督裁定 56 (2026-09-29、受け入れ監査 1 回 (監督保管 `acceptance-packet.md`。未充足 0、証拠不足 2、観察 3) の帰結)**

56. 受け入れ監査: 完了条件は WP-1〜WP-5・WP-7 と裁定で足した s / m の行がすべて充足 (WP-1 の 7 行と WP-2 の 38 行は、前のチャットの log が読めないので報告とレビューの記述による。監査担当は製品の安全に関わる変異 17 件を最終の木で再現し、全件 red)。証拠不足 1 (§7.5 の 6 の各 run の後の catalog の差分): **訂正註** — 計測は run ごとの使い捨て cluster で走るので、共有 cluster の `pg_database` / `pg_roles` の差分は残骸の証拠にならない (`OC` §1.10 の訂正註と同じ)。§7.5 の 6 は「終了コード 0 (launcher の process group の残骸なし)・nginx の残存 0」と読み、共有 cluster の数は表 7-2 の計測の前後で情報として記録した (9 / 30 で不変)。証拠不足 2 (C-32 (b) の 24 drive の選び方): 実行した引数は `-k requests_per_minute_429_count_matches_declared_bound` (両 peer の 2 件。各 run の log は監督保管)。監査の指摘で直したもの: `conformance-tests/CONDITIONS.md` の C-32 の行の「両 peer が src 側の配線をまだ負っている」の文 (配線済みの事実に改め、旧文と実測を HISTORY へ)、テストの docstring の古い件数 1 か所、設計の表題の版。監査の観察 1 (DB の時計が前へ跳ぶと rate の計数が早く消える) は `security/CONTROL_MAPPING.md` の両 peer の Status に開示、観察 3 (`scan` の lock が直列区間の候補に無い) は設計の表 7-1 の註に足した。観察 2 (launcher の uvicorn が pytest の異常終了で孤児になる経路) は観察 (開発機の残骸で、製品の欠陥が完了ゲートを抜ける穴ではない。引き継ぎ書に残す)。設計疑義 (1) (表 7-5 で 0.2 ms と比べる量) は、設計 §7.3 の算術の出所 (32 本の直列で割った値) に従い直列の 1 文あたりの時間で判定し、文ごとの p50 / p95 も表に併記した。表 7-2 (K = 1 の非退行) は 21 行とも閾値の内側 (設計 §7.4)。

### 6.2 実施と受け入れ

- **完了ゲートと受け入れ (監督、2026-09-29)**: 受け入れ監査 1 回 (未充足 0。監督裁定 56)。完了ゲート 1 回目 (木 `ea1ed75`、label `r113`): `gate: 4609 passed, 2 subtests passed in 387.08s (0:06:27)`、`judge=PASS`、`pg_database/pg_roles diff 0`。その後に監査の指摘 (C-32 の行、開示の 2 行、docstring) と記録 (設計の表 7-2、台帳 v1.131、引き継ぎ書 `HANDOVER_20260929_FABLE2.md`、`COLLECTION_FLOOR` 4342 → 4609) を足し、最終の木 (`049fedb` に本変更セットの記録 = 台帳・引き継ぎ書・`COLLECTION_FLOOR` を足した作業ツリー) の完了ゲート (監督、単独、使い捨ての cluster、label `r113-final`): `gate: 4609 passed, 2 subtests passed in 387.98s (0:06:27)`、`judge=PASS`、`pg_database/pg_roles diff 0`。`tools/tests`: `pt: 665 passed in 75.60s (0:01:15)`。 WP-6 の完了条件 172〜180 の照合対象: 台帳の R-113 (閉止)・R-101 (開いたまま、依頼者裁定)・R-18 の行と版 v1.131、`security/CONTROL_MAPPING.md` 3.7 (`conformance-tests/test_control_mapping_register.py` は完了ゲートの中で緑)、`COLLECTION_FLOOR` = 4609、`tools/PERF_BASELINE_README.md`、設計 §7.4 の表 7-1〜7-5、引き継ぎ書の「裁定」節。**受け入れ判定 (監督): 受け入れる。** R-113 は閉止、R-101 は開いたまま。依頼者に残る事項は引き継ぎ書の「依頼者判断待ち・未決」。
- **WP-7 (2026-09-29、worktree `r113-wp7`、設計 `e7cf10a` → WIP `5fa990d` → `3c24ebe` → `d4ffa1c` → `9c6607e`、r113 に merge `87fb4f4`)**: 設計メモ `docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md` v0.3 (起草 opus、設計レビュー 1 回 opus = 指摘 8 件、監督裁定 1〜27)。実装担当 sonnet (初回 + 差し戻し 1 / 1b / 1c)、コードレビュー opus (1 回 + 再確認 1b)。差し戻し 1c はテストの入力と runbook の文だけなので、監督が差分・検算・変異の log を照合して閉じた。`ops.py` の算術への指摘は 0 件で、指摘はテストの証拠 (空振り 3 本、過剰決定 1 本、宣言値を観測しない一致テスト) と runbook に集中した。最終 pt: `pt: 150 passed in 27.94s` (test_ops_inventory.py + test_ops_help_text.py)、`pt: 1651 passed, 2 subtests passed` (MitateDB-api/tests、初回の実装後)。変異: 初回 31 + 差し戻し 1 の 34 (取り直しを含む) + 1b の 13 + 1c の 5、全件 red、赤の理由は assert の中身。runbook §10 の表の版数は 5 / 5 / 8 (本変更セットで 1 版)、§10.8 は 3 行とも「not accepted」= **再受理は依頼者**。再受理で確かめる点: 古い基準の revision の `concurrency` を、その image の元の commit の既定値から出所付きで宣言してよいとした例外 (設計メモ 裁定 20)。
- **WP-5 (2026-09-29、worktree `r113-wp5`、WIP `9e1d058` → `f67b19b` → `9fb4920`、r113 に merge `0d07195`)**: 実装担当 opus (初回 + 差し戻し 1)、コードレビュー opus (1 回 + 再確認 1b、1b は差し戻しなし)。監督裁定 53 (§6.1)。最終 pt: `pt: 13 passed in 0.03s` (新規の静的テスト 2 本)、`pt: 61 passed, 3163 deselected in 5.03s` (配備物と runbook を読む既存テストを含む run)。変異: r2db 9 + MitateDB 8 = 17 件 red (M155〜M167 + M155d・M159d・M163d・M166d)。`shellcheck` 指摘なし、`lint_deploy_assets.sh` (`--require-tools` 無し) は `systemd-analyze verify: SKIPPED (tool absent)` で他は PASS。**開発機に systemd-analyze と docker は無く、lint の ExecStartPre の stub 置換が CI で効くかは未検証** (push の再開後の最初の run で確かめる)。
- **WP-3 (2026-09-29、worktree `r113-wp3`、WIP `96985e8` → `dfb069e` → `c0abb3d` → `0d0e376` → `69a5359` → `9a8c85c`、r113 に merge `d22aadc`)**: 実装担当 opus (再開 + 差し戻し 1 / 1b / 1c) と sonnet (差し戻し 1d)、コードレビュー opus (1 回 + 再確認 1b / 1c / 1d)。差し戻し 1d は監督が照合して閉じた。監督裁定 48〜50・52 (§6.1)、設計 裁定 43 (設計 §10.7、設計レビュー 1 回)。実装の途中で、宣言値未満の同時送信で `concurrency` の拒否が出る欠陥 (slot の走査の非原子性) を見つけ、両 peer の helper を `scan` の lock で直列化した。最終 pt: `pt: 1629 passed in 119.01s` (r2db-api/tests)、`pt: 1620 passed, 2 subtests passed in 158.76s` (MitateDB-api/tests)、`pt: 140 passed in 62.43s` (c05 / c26 / c32、両 peer)、`pt: 303 passed` (tools/tests/test_comment_provenance.py)。差し戻し 1d の後は対象 4 ファイル `321 passed`。変異: 再開 78 + 差し戻し 1 の 60 + 1b の 62 + 1c の 69 + 1d の 14 (各回は helper に掛かる既存の変異の取り直しを含む)、全件 red。同型登録 169 → 198。静的検査: `--register` OK (94 files, 434 CH-IDs)、`--base 18f9c0d` 33 行 ((3)(5) 0、CH-ID の塊への変更 0)、`check_doc_refs OK`、`public_value_scan total_flagged=0`。統合後の補強: C-32 (b) を両 peer で各 24 drive、`other` = 0。
- **統合の後 (監督、2026-09-29)**: `tools/tests` の共有 pin 4 件に `concurrency_slots.py` を足し (`17cc7fa`)、`pt: 665 passed in 157.26s` (tools/tests 全体)。`tools/PERF_BASELINE_README.md` と `tools/check_comment_provenance.py` の Known gaps 7 (`94f421a`)。
- **WP-4 (2026-09-29、worktree `r113-wp4`、WIP `8a54a74` → `2e0fec9` → `06f59ad`、r113 に merge `01d8a75`)**: 実装担当 opus (初回 + 差し戻し 1 / 2)、コードレビュー opus (1 回 + 再確認 1b / 1c、1c は「指摘なし」+ 観察 3)。監督裁定 43〜47 (§6.1)。最終 pt: `pt: 124 passed in 19.19s` (tools/tests/test_perf_baseline.py)、`pt: 4 failed, 661 passed in 74.95s (0:01:14)` (tools/tests。赤 = `concurrency_slots.py` の分類の共有 pin 4 件、WP-6 で監督が更新)。変異: `mutate: 14 mutations, 14 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged` (M146〜M150、M148b、M149b、M149c、M149d、M153、M153b、M153c、M153d、M153z。赤の理由は全件 assert の中身、再確認 1b が 10 件を再実行・1c が 14 件を log で照合)。監査照合: 151 = 基点 `18f9c0d` からの差分で `status != 200` を含む行 0 件、152 = `REALPERF` / `REALCPU` の書式と並びの差分 0 件・既存テスト緑。静的検査: `change_class` = B、`check_doc_refs OK`、`public_value_scan total_flagged=0`。`REALWORKERS` 行の形: `REALWORKERS peer= plug= workers= concurrency= pids= accepted_200= non_200= unclassified=`。
- **WP-2 (2026-09-28〜29、worktree `r113-wp2`、WIP `934554c` → `2d23741`、r113 に merge)**: 実装担当 sonnet (初回 + 差し戻し 1 / 1b) と opus (差し戻し 1c。sonnet は週次上限)、コードレビュー opus (1 回 + 再確認 1b / 1c、1c は「指摘なし」+ 観察 3)。監督裁定 22〜42 (§6.1)。最終 pt: `pt: 1 failed, 1609 passed in 122.05s` (r2db-api/tests。赤 = 同型性テスト 1 件、残る helper は `_VERIFY_DECLARATIONS_EXIT_CODES` / `_verify_declarations_checks` / `check_max_connections_headroom` の 3 つ = 完了条件 78、WP-3 で消える)、`pt: 67 passed, 73 deselected in 32.78s` (c05 / c26 / c32 -k r2db)、`pt: 303 passed in 36.97s` (tools/tests/test_comment_provenance.py、commit 後)。期待される赤: C-26 `test_c26_ceiling_maps_to_limit_enforcement[MitateDB-api]` (WP-3 まで)、tools/tests の共有 pin 4 件 (`concurrency_slots.py` の分類。完了ゲートで監督が更新)。変異: 初回 `mutate: 47 mutations, 47 as expected` + 差し戻しで足した / 差し替えた 22 件 (M29b、M56b、M70、M70b、M71c、M72c、M74b、M35b、M36b、M45b、M76、M76i、M77、M77i、M8r〜M18r、M31、M32) = 全 69 件 red (変異表は監督保管 `wp2-mutation-table.md` と実装報告 `r113-wp2-report-4.md` 付録)。静的検査: `check_comment_provenance --register` OK (93 files, 434 CH-IDs)、`--base 74d90f3` は 29 行 ((1) AST 差分 10、CH-0322 の改名 2 (裁定 30)、新規ファイル 1、(2) 新規 / 追随 / 改名の追随 16 (裁定 32)、(3)(5) 0)、`check_doc_refs OK`、`public_value_scan total_flagged=0`、`change_class` = C (宣言は D)。`HAVE_FLOCK` = 1。完了条件 29 の SQL 逐語・67 の file:line は `r113-wp2-report-4.md` 付録。
- **WP-1 (2026-09-28、worktree `r113-wp1`、WIP `8a0327d`、r113 に merge)**: 実装担当 sonnet (差し戻し 1〜4)、コードレビュー opus (1 回 + 再確認 2 回、全件閉止)。最終 pt (4 ファイルの絞った run): `pt: 16 failed, 105 passed in 56.11s` — 赤は完了条件 9・11・14〜18 の両 peer (宣言分岐の cross-check「configured … but declares deployment_required」= WP-2/3 待ちの期待、完了条件 22)、r2db control の preflight 観測 (WP-2 待ち)、`test_every_executable_condition_has_a_marked_test` (部分実行の既知の穴)。変異: `mutate: 12 mutations, 12 as expected, restores verified 4/4 files (sha256 x2)` (M1〜M7 r/m、M19)。静的検査: `check_doc_refs OK`、`change_class` = C、`public_value_scan total_flagged=0`。新条件は **C-32** (`conformance-tests/test_c32_shared_limits.py`、`CONDITIONS.md` の行、cell 長 C-05 2966 / C-26 2979)。

### 6.3 runbook §10 の再受理の記録 (2026-09-30) — runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.8 が指す受理記録

- **対象**: `MitateDB-api/docs/cloud-run-cloud-sql.md` の §10.6 (互換表)、§10.7 (lock・停止時間・`lock_timeout` の表)、§10.10 (upgrade の手順、stage 2〜4)。R-113 (本書 WP-5・WP-7) で表の版が 4 / 4 / 7 から上がり、§10.8 の受理は無効に戻った。
- **独立のレビュー** (設計レビューのモード、opus、いずれも runbook の起草者・実装担当・ほかのレビュー担当とは別の起動): 1 回目 (main `41b9fa6`、版 5 / 5 / 8) = §10.6 accepted、§10.7 accepted、§10.10 not accepted (必須 6 件)。監督の差し戻し 1 (`1889608`、版 6 / 6 / 9)。2 回目 = §10.6・§10.7 accepted、§10.10 not accepted (必須 9 件)。差し戻し 2 (`528626c`)。3 回目 = §10.6・§10.7 accepted、§10.10 not accepted (必須 8 件)。差し戻し 3 (`c61e4f2`) と、その確認のレビュー 1 回 (統合を止める 3 件、止めない 7 件)。差し戻し 4 (`9eb52dd`)。**§10.6 と §10.7 の表は差し戻し 1 の後、1 字も変えていない** (差し戻し 2〜4 の後に `### 10.6` から `### 10.9` の直前までを byte 単位で照合)。レビューの全文と検算、差し戻しの指示と報告は監督保管 (`r113-handoff/` の `r113_runbook_s10_acceptance_review*.md`、`accept-s10*`、`confirm-s10`、`r113_accept_rework_1〜4.md`、`r113-accept-report-1〜4.md`)。
- **依頼者裁定 (逐語)**: 2026-09-29「本番の値は分からないので、確かめる手順の形で進めてください」。2026-09-30「推奨の (1) と (3) の組み合わせで進めてください」— (1) 起動を拒む検査の検算を道具に移す項目 (台帳 R-116) を起票し、§10.10 の受理はその後。(3) 直した runbook を §10.10「not accepted」のまま main に入れ、§10.6 と §10.7 の受理を記録する。同日「main への統合まで続けてください」。
- **受理**: §10.6 版 6 と §10.7 版 6 を、3 回の独立レビュー (すべて accepted、現物との不一致なし) を根拠に**受理する** (依頼者裁定 2026-09-30)。§10.10 版 9 は **not accepted** (version reviewed 9)。Gate-0 は §10.10 が受理されるまで ready にならない。
- **§10.10 が受理されない理由 (3 回のレビューの要旨)**: `process_ceilings` の宣言を変えると、動いている全 revision と rollback target の起動時の検査 (F-18 = `max_connections` の下限、F-16 = role ごとの `CONNECTION LIMIT` の床) の可否が新旧の code で変わる。migration を当て直す途中で上限が古い値に下がる窓。確認のコマンドが失敗しても「確認できた」と読める形。手順の「古い revision を数える」部分が使えるのは `443a79a` (2026-09-28) から R-113 の統合の前までの code だけで、本番の image がそれより古ければ最初の読みで `unknown` で止まる。人の手の検算に依る手順は、文を直し続けても収束しなかった (3 回で計 23 件の必須の指摘)。版 9 は、起動時の検査の紙の検算・実在の確認・古い image の env の確認・2 段の rollout を持つが、受理は R-116 (検算を道具に移す) の後に行う。
- **本番には何も適用していない。**
- **次に §10.6 の表の版を上げるときの事項**: `0015` の行の「unchanged by the two revisions between it and this one」は、参照を絶対の commit (`f3b10ca`、`0015` を足した commit の親) にした後は成り立たない (3 回目のレビューの任意 g。判定と条件は変わらない)。

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

## 12. WP-7 — MitateDB の Gate-0 inventory 項目 (8) の需要の基準 (実装担当。WP-3 と WP-5 の統合の後)

**目的**: inventory の項目 (8) の接続の需要を、起動時の検査 (F-16 / F-18) と同じ thread limit 基準に揃える。rollout で古い code の revision と新しい code の revision が並ぶ間は、需要を revision の基準ごとに数えて足す。runbook §10 をこの算術と入力に合わせる。

**読むべき正本**: 設計メモ `docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md` v0.3 (以下「WP-7 設計」) の §1・§2 (問題と条件)、§4 (決定)、§5 (検算)、§7 (壊すとどう見えるか)。**WP-7 設計の §10 (監督裁定 1〜16) と §10.1 (監督裁定 17〜25) が本文 (§4 の決定、§9 の疑義) より優先し、§10.1 が §10 より優先する。** 却下案は WP-7 設計 §6 と裁定 1 (蒸し返さない)。本書 §6.1 の「依頼者裁定 (2026-09-29) と監督裁定 51」。接続予算の倍率は設計 §10 の裁定 16 と本書 §6.1 の監督裁定 28。runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` の §6.5 (接続予算)、§10.4 (env の値の許可表)、§10.4.3、§10.5、§10.8、§10.9、§10.10 (前提条件)、§10.10.1 (項目 (8) の行)、§10.10.3 の step 13。

**クラス**: 宣言は D (R-113 全体。本書 §0)。`tools/change_class.py` の判定を報告に記す。**テンプレート**: `ROLES` の 2。**設計レビュー**: WP-7 設計に対して 1 回、済 (裁定は WP-7 設計 §10.1)。**コードレビュー**: `ROLES` の 5 で 1 回 (本書 §2.2)。

**順**: WP-3 → WP-5 → WP-7 の直列 (WP-7 設計の裁定 13)。runbook を WP-5 と共に触るので並行しない (`OC` §1.2 の 16)。担当 worktree は、統合 branch r113 に WP-3 と WP-5 を統合した後の木から監督が作る (本節では `$WT`、その基点を `<WP-7 の基点>`)。依頼者判断待ちの選択肢は無い。

**監督が行い、実装担当が触らないもの**: `security/CONTROL_MAPPING.md` の SI-08 の MitateDB の写像の追随 (WP-7 設計の裁定 15。本書 §9)、`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` への指し先の訂正註 (裁定 11)、本書 §6.1 の監督裁定 51 への訂正註 (裁定 11)、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` への訂正註 (裁定 17 の Z-27 の読み方)。

**記号** (WP-7 設計 §4 D-2 と裁定 17): O = 古い基準の data process 数 (`--data-process-count-old-basis`)、N = `--data-process-count-total` − O (新しい基準の data process 数)、c = `--concurrency`、t = `--thread-limit`、p = `config.role_pool_size(t)`、A = `platform_declarations._API_ROLE_STORE_COUNT`、K = inventory が `applications` の表から読む、role を持つ登録 application の数。境の上限はテストの中で `ALTER ROLE ... CONNECTION LIMIT` で置く。

### 12.1 触ってよいパス

| パス | 範囲 |
|---|---|
| `MitateDB-api/src/mitatedb_api/ops.py` | inventory の項目 (8) (`_inventory_connection_headroom` と、それが呼ぶ ops.py 内の helper)、入力の検査 (`_inventory_validate_headroom_inputs`)、`_build_parser` の inventory の節 (引数と help)、`_inventory_positive_int` / `_inventory_nonnegative_int` の docstring の引数一覧。ops.py の他の関数・他のサブコマンドは触らない |
| `MitateDB-api/tests/test_ops_inventory.py` | 項目 (8) のテスト、入力の既定 `_HEADROOM_OK`、引数の dest の集合のテスト |
| `MitateDB-api/tests/test_ops_help_text.py` | 新しい 2 引数の help のテスト (既存のテストは変えない) |
| `MitateDB-api/docs/cloud-run-cloud-sql.md` | §10 の該当箇所 (§10.4 の許可表、§10.4.3、§10.5、§10.8 の §10.10 の行、§10.9 の項目 (8) の文、§10.10 の版の行と前提条件、§10.10.1 の項目 (8) の行、step 13) と、§10 の外で同じ事実を述べる文 (§6.5 の「`ops inventory` は `concurrency` から数える」の文など) |
| `docs/code-history/MitateDB-api/` | 登録済みの塊を変えたときの訂正記録だけ |

**これ以外は 0 件。** `platform_declarations.py`・`config.py`・`main.py`・migration・`security/`・`conformance-tests/`・`spec/`・r2db-api・上の「監督が行うもの」の 4 文書は触らない (WP-7 設計 §2 の 5・7、裁定 2)。触ってよいパスの外の赤は直さず報告する。設計に無い検査・機構は実装前に報告する (`OC` §1.5 の 37)。

### 12.2 完了条件 (181〜228)

| # | 完了条件 |
|---|---|
| 181 | `--thread-limit` は正の整数だけを受け、0・負・非整数は inventory の usage error (終了コード 1) |
| 182 | `--data-process-count-old-basis` は 0 を受ける (0 は「古い基準の process は無い」の明示) |
| 183 | `--data-process-count-old-basis` は負・非整数を終了コード 1 で拒む |
| 184 | O > `--data-process-count-total` は固定文言で終了コード 1。入力値を出力しない。テストは文言を逐語で assert する (O > 合計 は N < ceiling の検査にも掛かるので、終了コードだけでは見分けられない) |
| 185 | N < `--data-process-ceiling` は固定文言で終了コード 1 (WP-7 設計の裁定 5)。テストは合計 ≥ ceiling かつ O ≥ 1 の入力で観測する (既存の「合計 < ceiling」の検査に吸われない形) |
| 186 | O = 0 を明示し `--concurrency` も与えた入力は固定文言で終了コード 1 (裁定 6)。O の省略はこの検査に掛からない |
| 187 | 184〜186 の検査は DB 接続の前に行う。テストは `MITATEDB_PROVISION_DSN` をテストの platform に向けたうえで、接続の factory (か `psycopg.connect`) の spy が 0 回であることを観測する |
| 188 | O の省略は項目 (8) を `unknown` にする (0 で埋めない)。テストは O = 0 なら `confirmed` になる入力で観測する |
| 189 | O ≥ 1 で `--concurrency` を省くと `unknown` (既定値で埋めない)。赤にするテストは既存の `test_inventory_connection_headroom_concurrency_missing_is_unknown` を名を変えず O ≥ 1 の入力に直したもの。既定値で埋めれば `confirmed` になる入力にする |
| 190 | O = 0 で `--concurrency` が無い入力は、他の入力が揃えば判定する (`confirmed` を観測) |
| 191 | `--thread-limit` の省略は `unknown` (`DEFAULT_THREAD_LIMIT` で埋めない)。テストは t = `DEFAULT_THREAD_LIMIT` なら `confirmed` になる入力で観測する |
| 192 | **一致 (api)**: O = 0、N = 合計 = ceiling = n、同じ t で、F-16 (`platform_declarations.check_role_connection_limits`、`pool_size=config.role_pool_size(t)`、`process_ceilings.data = n`、`role_classes={"api"}`) が通す最小の上限 L と、inventory が `confirmed` にする最小の上限が等しい。L で両方が通り、L − 1 で両方が止まる (WP-7 設計の裁定 2・22、条件 4)。他の role の上限と条件 2 は判定を左右しない入力にする |
| 193 | **一致 (application)**: 192 と同じ形で、1 つの application の runtime / developer role (`application_ids` をその application に絞る) |
| 194 | **一致 (controlplane)**: 192 と同じ形で、`role_classes={"controlplane"}`、`process_ceilings.control` = control の合計 = ceiling |
| 195 | **一致 (auditreader)**: 194 と同じ形で、`role_classes={"auditreader"}` |
| 196 | **定数の差し替え (pool)**: テストの中で `config._POOL_SIZE_HEADROOM` を元と違う値に差し替えても、F-16 が通す最小の上限と inventory が `confirmed` にする最小の上限が一緒に動く (裁定 22。差し替えは module 属性に対して行い、inventory は呼び出しの時点で引く) |
| 197 | **定数の差し替え (api)**: 196 と同じ形で `platform_declarations._API_ROLE_STORE_COUNT` |
| 198 | **定数の差し替え (controlplane)**: 196 と同じ形で `platform_declarations._CONTROLPLANE_ROLE_POOL_FLOOR` |
| 199 | **定数の差し替え (auditreader)**: 196 と同じ形で `platform_declarations._AUDITREADER_ROLE_POOL_FLOOR` |
| 200 | **混在 (api、条件 1)**: O ≥ 1、N ≥ 1、c ≠ p の入力で、api role の上限 = O × A × c + N × A × p で `confirmed`、1 引いて `blocked` (WP-7 設計 D-2) |
| 201 | **混在 (application、条件 1)**: 200 と同じ形で、application role の上限 = O × c + N × p |
| 202 | 古い基準の api の process あたりの床は A × c。赤にするテストは既存の `test_inventory_connection_headroom_role_coefficient_is_two_times_concurrency_for_api` を名を変えず O ≥ 1 の入力に直したもの |
| 203 | control の需要は t にも c にも依らない: O ≥ 1 で c を与え、t と c を変えても controlplane と auditreader の境の判定が動かない (WP-7 設計 D-5) |
| 204 | **条件 2 (第 1 項)**: O ≥ 1、K = 1 で O × c + N × p > 2 × K × (O + N) の入力で、`--reserved-connections` = `max_connections` − 合計需要 で `confirmed`、1 足して `blocked`。合計需要の application の項は max(O × c + N × p, 2 × K × (O + N)) (裁定 17) |
| 205 | **条件 2 (第 2 項)**: 2 × K × (O + N) > O × c + N × p の入力 (例: O = 0、t = 4、K ≥ 4) で、204 と同じ境の両側を観測する (裁定 17)。登録 application が 0 のときの項は WP-7 設計 §5.2 のとおり |
| 206 | 条件 1 の application の床は K に依らず O × c + N × p (裁定 17 の末尾、WP-7 設計 D-6)。テストは K ≥ 4 の入力で、上限 = 条件 1 の床 で `confirmed` を観測する |
| 207 | 項目 (8) の出力は `judgment`・`remediation_required`・`control_deployed` の 3 key のまま (既存の `test_inventory_top_level_and_item_keys_are_pinned` が緑) |
| 208 | inventory の引数の dest の集合 (`test_inventory_does_not_accept_a_dsn_argument`) が、既存の集合に `thread_limit` と `data_process_count_old_basis` を足した集合と一致する |
| 209 | `--thread-limit` の help は実装担当が起草し、`MitateDB-api/tests/test_ops_help_text.py` の既存の help のテストと同じ形で文字列を逐語で pin する (裁定 14。確定文ファイルは要らない) |
| 210 | `--data-process-count-old-basis` の help を 209 と同じ形で pin する |
| 211 | **監査照合**: `--concurrency` の help が「古い基準の revision の値で、O ≥ 1 のときだけ要る」ことを述べ、「省けば項目 (8) は `unknown`」を O ≥ 1 に限った形になっている。改めた help の逐語を報告に置く |
| 212 | **監査照合**: 既存の確定文言の help (`--data-process-count-total` / `--control-process-count-total`) と、それを pin する `MitateDB-api/tests/test_ops_help_text.py` の 2 テストの差分が 0 (`git diff <WP-7 の基点>` の該当部分の逐語を報告に置く) |
| 213 | `security/CONTROL_MAPPING.md` が引く `MitateDB-api/tests/test_ops_inventory.py` の test 名を改名・削除しない (`conformance-tests/test_control_mapping_register.py` が緑。裁定 15) |
| 214 | **監査照合**: 既存の項目 (8) のテスト — `_HEADROOM_OK` は O と t を持ち 184〜186 の検査に掛からない入力である。`concurrency` 基準の算術を証するテストは O ≥ 1 の入力で意味を保つ (O = 合計 は 185 で拒まれる)。`test_inventory_connection_headroom_shared_application_role_budget_counts_once` は名を変えず中身を裁定 17 の項に合わせる。`test_inventory_connection_headroom*` の件数は基点の件数以上。基点との差分で、各テストの入力と期待の変更を表にして報告に置く |
| 215 | **監査照合**: runbook §10.4.3 — revision の基準は image digest と `MITATEDB_WORKERS` の有無の両方で決め、両者が食い違う revision が数える対象に在れば古い基準の process 数を省く (裁定 19)。加数表に「基準」の列 (根拠 = digest と `MITATEDB_WORKERS` の有無) を置き、古い基準の process 数を合計と同じく 2 回数えて一致させ、列が空の行が在れば古い基準の process 数を省く (裁定 21)。古い基準の revision の worker 数は `WEB_CONCURRENCY`、無ければ 1 (裁定 7) |
| 216 | **監査照合**: runbook §10.4.3 の引数の表 — `--thread-limit` の行 (新しい基準の revision の `MITATEDB_THREAD_LIMIT`。値が違えば最大値、1 つでも無ければ省く。裁定 4)、`--data-process-count-old-basis` の行、`--concurrency` の行を「数える対象の古い基準の revision すべて (traffic を取れない revision を含む) の最大値、O ≥ 1 のときだけ」に改める (裁定 9。現行の「値が揃わなければ省く」と「traffic を取れない revision は比べない」を置き換える)。env を変えられない古い基準の revision が `MITATEDB_MAX_CONCURRENCY` を持たないとき、commit の既定値を出所 (commit とファイルの行) を加数表に書いて宣言してよいこと、`--thread-limit` には適用しないこと (裁定 20) |
| 217 | **監査照合**: runbook §10.4.3 に項目 (8) の入力を省かせる場合の列挙 — `MITATEDB_PLATFORM_POOL_SIZE` を持つ revision が数える対象に在る (裁定 8)、古い基準の revision が `MITATEDB_THREAD_LIMIT` を持つかその `concurrency` が 6 未満 (裁定 18)、digest と env の食い違い (裁定 19)、新しい基準の revision が `MITATEDB_THREAD_LIMIT` を持たない (裁定 4)。限界の開示の文「inventory は古い基準の process 数の正しさを検査できない。誤った宣言は需要を小さく数える」(裁定 21) |
| 218 | **監査照合**: runbook の「Demand is still counted from `concurrency`」の段を、基準ごとの需要 (WP-7 設計 D-2 と裁定 17) の段に置き換える。§10 の外で同じ事実を述べる文 (§6.5 の `ops inventory` の文、§10.9 の最初の読み取りの項目 (8) の文ほか) も同じ事実に揃え、「項目 (8) は `concurrency` から数える」と述べる文が古い基準の revision についての文のほかに残っていない (該当の grep の出力を報告に置く) |
| 219 | **監査照合**: runbook §10.4 の env の値の許可表に `MITATEDB_WORKERS`・`WEB_CONCURRENCY`・`MITATEDB_THREAD_LIMIT`・`MITATEDB_CONTROL_WORKERS` の行 (裁定 10・23) と、値ではなく「在るか無いか」を読む `MITATEDB_PLATFORM_POOL_SIZE` の行 (裁定 24)。`MITATEDB_MAX_CONCURRENCY` の行と表の後の文を古い基準の revision の入力として読める形に改める |
| 220 | **監査照合**: runbook §10.5 の inventory の呼び出しの script に新しい 2 引数の行 (空なら渡さない、既存の行と同じ形) と、変数の数の文の追随。O = 0 のとき `--concurrency` を渡さない旨を script の側に明記する (裁定 6・23)。script の後の箇条書き (受ける値、両立しない組) を新しい引数と検査に揃える |
| 221 | **監査照合**: runbook §10.10 の前提条件の算術を WP-7 設計 D-2 の式と裁定 17 の application の項に、worked example を WP-7 設計 §5 の値 (古い 1 process + 新しい W で W ≤ 5、条件 2 の 98 + 18W + 20C、新しい code どうしで V + W ≤ 11) に改める。「At a worst-case total of 3」の段と「application の需要は登録数に依らず 1 回」の段を、基準ごとの算術と裁定 17 で書き直す |
| 222 | **監査照合**: runbook §10.10.1 の項目 (8) の `unknown` の行に、`--thread-limit` と古い基準の process 数の省略の原因 (217 の列挙を含む) を足す。解き方が WP-7 設計 (§10・§10.1 を含む) に無い原因は、同節の既存の規則のとおり stage 2 では解けない (報告して止まる) と書く |
| 223 | **監査照合**: step 13 — deploy の env は `MITATEDB_THREAD_LIMIT=<--thread-limit に使った値>` を含む。deploy の後に候補の `MITATEDB_THREAD_LIMIT` を読み返し、第 2 の読み取りが使った値と違えば読み直す (既存の読み返しの規則と同じ形)。`MITATEDB_MAX_CONCURRENCY` の必須は残し、項目 (8) の判定の値としての説明は古い基準の revision に限る形に改める (裁定 23 が採った設計レビュー指摘 7 の 10) |
| 224 | **監査照合**: runbook §10.10 の版の行を上げ、変更の内容を日付付きで記す。§10.8 の §10.10 の行の Current version を同じ値に上げ、Conclusion は `not accepted` のまま、Version reviewed は変えない (WP-7 設計 D-8、本書 §6.1 の監督裁定 51) |
| 225 | **監査照合**: runbook の rollout の重なり (`RM` の R-52) の段 (保つもの・保たないもの) の意味を変えていない (該当行の差分の逐語を報告に置く。WP-7 設計 §2 の 6) |
| 226 | **監査照合**: `git diff --stat <WP-7 の基点>` が §12.1 のパスだけ。`spec/`・`conformance-tests/`・`security/`・r2db-api・`platform_declarations.py`・`config.py`・`main.py`・migration と、「監督が行うもの」の 4 文書の差分が 0 |
| 227 | **監査照合**: 静的検査の出力行 (`check_comment_provenance.py --base <WP-7 の基点>` と `--register`、`change_class.py`、`check_doc_refs.py`、`public_value_scan.py`) を報告に置く |
| 228 | **監査照合**: §12.3 で変異も監査照合も持たない行が 0 件 |

### 12.3 完了条件 → 変異 (`expect=red`。run = MitateDB。213 だけ run = conformance)

変異は各完了条件の機構だけを外す。赤の理由は assert の中身であること (例外による赤は数えない)。

| 完了条件 | 変異 | 赤にするテスト (1 件) |
|---|---|---|
| 181 | **M181**: `--thread-limit` の `type=` を `int` にする | 0 を渡して終了コード 1 を期待するテスト |
| 182 | **M182**: `--data-process-count-old-basis` の `type=` を `_inventory_positive_int` にする | 0 を受けるテスト |
| 183 | **M183**: `--data-process-count-old-basis` の `type=` を `int` にする | −1 を渡して終了コード 1 を期待するテスト |
| 184 | **M184**: O > 合計 の検査を外す | 184 の固定文言を逐語で見るテスト |
| 185 | **M185**: N < ceiling の検査を外す | 185 のテスト |
| 186 | **M186**: O = 0 と `--concurrency` の組の検査を外す | 186 のテスト |
| 187 | **M187**: 184〜186 の検査を `_inventory_validate_headroom_inputs` から `_inventory_connection_headroom` の先頭 (接続の後) へ移す | 187 の spy のテスト |
| 188 | **M188**: O の省略を 0 で埋める | 188 のテスト |
| 189 | **M189**: O ≥ 1 のときの `--concurrency` の省略の検査を外し、code の `concurrency` の既定値で埋める | `test_inventory_connection_headroom_concurrency_missing_is_unknown` |
| 190 | **M190**: `--concurrency` の省略を O に依らず `unknown` にする (O ≥ 1 の条件を外す) | 190 のテスト |
| 191 | **M191**: `--thread-limit` の省略を `DEFAULT_THREAD_LIMIT` で埋める | 191 のテスト |
| 192 | **M192**: 新しい基準の api の process あたりの床から A を外す (p だけにする) | 192 の一致のテスト |
| 193 | **M193**: 新しい基準の application の process あたりの床を `role_pool_size(t)` から t にする (headroom を外す) | 193 の一致のテスト |
| 194 | **M194**: controlplane の process あたりの床を `_CONTROLPLANE_ROLE_POOL_FLOOR` から p にする (WP-7 設計 D-5 を外す) | 194 の一致のテスト |
| 195 | **M195**: auditreader の process あたりの床を `_AUDITREADER_ROLE_POOL_FLOOR` から p にする | 195 の一致のテスト |
| 196 | **M196**: inventory の `role_pool_size(t)` を `t + 2` の直書きにする (差し替えの無い既定では同じ値) | 196 の差し替えのテスト |
| 197 | **M197**: inventory の `platform_declarations._API_ROLE_STORE_COUNT` を `2` の直書きにする | 197 の差し替えのテスト |
| 198 | **M198**: inventory の `_CONTROLPLANE_ROLE_POOL_FLOOR` を `16` の直書きにする | 198 の差し替えのテスト |
| 199 | **M199**: inventory の `_AUDITREADER_ROLE_POOL_FLOOR` を `4` の直書きにする | 199 の差し替えのテスト |
| 200 | **M200**: api の需要の古い基準の項を外す (全 process を新しい基準 (O + N) × A × p で数える) | 200 の境のテスト |
| 201 | **M201**: application の需要の古い基準の項を外す (条件 1 の床を (O + N) × p にする) | 201 の境のテスト |
| 202 | **M202**: 古い基準の api の process あたりの床から A を外す (c だけにする) | `test_inventory_connection_headroom_role_coefficient_is_two_times_concurrency_for_api` |
| 203 | **M203**: O ≥ 1 のとき controlplane の process あたりの床を c にする | 203 のテスト |
| 204 | **M204**: 条件 2 の application の項の第 1 項から O × c を外す (N × p だけ。条件 1 は変えない) | 204 の境のテスト |
| 205 | **M205**: 条件 2 の application の項から第 2 項 2 × K × (O + N) を外す | 205 の境のテスト |
| 206 | **M206**: 条件 1 の application の床を条件 2 の項 (max の形) にする | 206 のテスト |
| 207 | **M207**: 項目 (8) の `_result` に key を 1 つ足す | `test_inventory_top_level_and_item_keys_are_pinned` |
| 208 | **M208**: inventory に `--provision-dsn` 引数を足す | `test_inventory_does_not_accept_a_dsn_argument` |
| 209 | **M209**: `--thread-limit` の help の 1 語を変える | 209 の help のテスト |
| 210 | **M210**: `--data-process-count-old-basis` の help の 1 語を変える | 210 の help のテスト |
| 213 | **M213**: `security/CONTROL_MAPPING.md` が引く test を 1 つ改名する (テストファイル側) | `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_test_name_reference_resolves` |
| 211、212、214〜228 | **監査照合** (照合対象の逐語を報告に残す。`OC` §1.5 の 40) | — |

- 変異は 31 件 (M181〜M210 の 30 件は run = MitateDB、M213 は run = conformance)。
- M196〜M199 は差し替えの無い既定では値が同じなので、一致のテスト (192〜195) では赤にならない。赤にするのは差し替えのテストだけである。
- M200 と M204、M201 と M206 は同じ数行に掛かりうるが、赤にするテストが違うので別の変異として走らせる (本書 §2.3)。
- 192〜199 のテストは F-16 の関数をテストの中で直接呼ぶ。製品の `platform_declarations.py` は触らない。`main.py` が F-16 に渡す引数と inventory の引く値の一致は、これらのテストの範囲外である (裁定 22)。

### 12.4 道具の引数

本書 §2.3 の形で:

```bash
export SP=<scratchpad>
tools/dev/pt.py --wait 1800 -C $WT -- MitateDB-api/tests/test_ops_inventory.py MitateDB-api/tests/test_ops_help_text.py -q
tools/dev/pt.py --wait 1800 -C $WT -- conformance-tests/test_control_mapping_register.py -q
tools/dev/mutate.py "$SP/r113-wp7-mutations.json" -C $WT --wait 1800        (M181〜M210。pytest は 1 行目のパス)
tools/dev/mutate.py "$SP/r113-wp7-mutations-conf.json" -C $WT --wait 1800   (M213。pytest は 2 行目のパス)
```

worktree を cwd にして:

```bash
python3 tools/check_comment_provenance.py --base <WP-7 の基点> MitateDB-api/src/mitatedb_api/ops.py
python3 tools/check_comment_provenance.py --register
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

- 報告は `$SP/r113-wp7-report.md`。変異の `old` / `new` の具体と赤の理由 (assert の中身) を表で残す。

### 12.5 レビューの観点

- 条件 2 (小さく数えない): WP-7 設計 D-2 の式と裁定 17 の application の項が、古い code の実需要と登録 K 個の永続接続を小さく数える経路を持たないか。境のテスト (192〜206) が境の両側を観測しているか (空振り、`OC` §1.5 の 32)。
- 条件 4: 192〜195 が F-16 と同じ cluster・同じ入力で 4 つの role class の一致を観測しているか。196〜199 の差し替えが F-16 と inventory の両方に届いているか (inventory が定数を名前で束縛して差し替えを素通りしていないか)。数値の一致だけを見る代理になっていないか (`OC` §1.7 の 52)。
- 条件 3: 省略の規則 (188・189・191) が既定値で埋めていないか。入力の形の誤り (184〜186) が DB 接続の前に止まるか (187)。
- 既存のテストの意味の保存 (202・214): `concurrency` 基準の証拠が O ≥ 1 の入力で残っているか。`security/CONTROL_MAPPING.md` が引く test 名が残っているか (213)。確定文言の help が変わっていないか (212)。
- runbook: WP-7 設計 §5 の数値の再計算。基準の見分け (215) と step 13 の env・読み返し (223) の対称。`unknown` にする場合の列挙 (217) が裁定 4・8・18・19 と一致するか。rollout の重なりの段の意味が変わっていないか (225)。§10.8 が `not accepted` のままか (224)。
- 新規のコメント・docstring が現在形で、経緯語 (フェーズ・WP・R-番号・裁定の番号) を持たないか (本書 §2.2)。
