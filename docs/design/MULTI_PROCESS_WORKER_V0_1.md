# multi-process worker と in-memory の limit 状態の置き場 設計文書（v0.1）

## 0. 版数・位置づけ

- 状態: **起草 (v0.1) + 監督裁定 (v0.2、§10)。§5 の Q-1〜Q-5 は依頼者判断待ち。** 設計レビューを着手条件とする (回数は Q-1 の裁定で決まる: 契約の文言に触れる (A)(C) なら 2 回、(B) なら 1 回。§10 の裁定 1)。
- 台帳: 計画文書 `RM` §8 の **R-113** (規模 L)。R-101 の是正の 2 段目 (`RM`:521、:533)。
- 基点: main `443a79a`。本書の file:line はこの木の現物である (uvicorn は開発機の venv の 0.52.4。両 peer の `pyproject.toml` は `uvicorn>=0.30`、`r2db-api/pyproject.toml`:33、`MitateDB-api/pyproject.toml`:30)。
- 契約: Q-1 が (A) または (C) なら **1.12.0** (文言の明確化のみ、義務の追加なし。§10 の裁定 1)。(B) なら 1.11.0 のまま。
- 改版: v0.1 (2026-09-28) 起草 (drafter)。v0.2 (2026-09-28) 監督裁定 1〜9 を §10 に追記 (起草の疑義への裁定。本文は書き換えず、§10 が優先する)。
- 出所の記法は `docs/work-orders/OPERATING_CONDITIONS.md` §0。キーの無いファイルは経路で書く。
- 公開規律: 実 DSN・実ホスト名・作業機の絶対パスを置かない (`OPERATING_CONDITIONS.md` §1.9)。
- 本書の D-N / Q-N / WP-N は本書ローカルの ID である。他文書の同形 ID には文書名を添える (§1.8 の 59)。新しい共通条件は番号を確定する WP まで「新条件」と呼ぶ (§3 D-4)。

## 1. 問題設定と出所

### 1.1 枠 §1 (監督確定、逐語)

```text
- 1 process の server は Python の CPU (GIL) で直列化される (R-101 WP-2 判定 J-2)。real-server plug (server 1 process、thread limiter 4、client 8 process) の `query` p50 K=32 / K=1 は r2db 15.7 / MitateDB 18.7 倍 (実効並行 2.0 / 1.7)。§0.1.4 の 2 は 8 倍以内 (実並行 4 相当) を両 peer に要求する。
- GIL の外に出るには server を複数 OS process にするしかない。現行は両 peer とも 1 process 固定: r2db systemd 1 unit (`r2db-api/deploy/systemd/r2dbsvc-api.service:60`、`--workers` 無し)、MitateDB Dockerfile CMD (`MitateDB-api/docker/Dockerfile:145`) + Cloud Run `--max-instances=1` (runbook Invariant 1、`MitateDB-api/docs/cloud-run-cloud-sql.md:1330-1358`)。composition root は両 peer とも module-level `app = build_app()` (r2db `main.py:698`、MitateDB `main.py:639`)。
- process を増やすと壊れるのは区分 (ii) の 4 class だけ (フェーズ10 D-5 表): `requests_per_minute` (credential 単位の sliding window、post-auth)、`concurrency` (配備全体 1 カウンタ、pre-auth admission)、`control_requests_per_minute`・`audit_requests_per_minute` (control plane の pre-auth fixed window)。現行の写像は ceiling ≥ 2 で `deployment_required` に落とす (r2db `capabilities_document.py:128-135`、MitateDB 同型) = 契約上は正しいが bound は N 倍に緩む。
- 区分 (iii) (`applications` / `credentials_per_application` / `idempotency_entries`) は PostgreSQL の advisory lock / LOCK TABLE で既に multi-process 安全。区分 (i) は無影響。audit buffer / denial coalescer / thread limiter / 統計は per-process で「量が N 倍」になるだけ (設計コメントで明記済み)。
- MitateDB の application cell (永続接続 + process 内 RLock、`cell.py:546-583`) は「1 接続上の commit/rollback 混線」を守る lock であり、process ごとに接続も lock も別なので守る性質は process ごとに保たれる。同一 application の process 間の同時実行は PostgreSQL の tx 隔離と LOCK TABLE (schema 変更) が担う。R-102 (cell lock の待ち) は本件に混ぜない。
```

### 1.2 出所

| 事項 | 出所 |
|---|---|
| 台帳の行 | `RM`:533 (R-113)、:521 (R-101)、:438 (R-18)、:472 (R-52)、:522 (R-102) |
| 閉止形 | `RM`:64 (§0.1.4 の 1 = K=1 の非退行)、:65 (§0.1.4 の 2 = K=32 / K=1 ≤ 8、real-server plug への改訂を含む) |
| 出発点の実測 | `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` v0.3 §6 (§6.1 の 2 回目 = D-15a の逐語、§6.2 の 1 の表、§6.3 の判定と申し送り) |
| 床の算術と判定規則 | `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` §7.1 (:497-549)、§10.1 (:939-944、R-101 作業指示書 D-16 の逐語)、§12 の (12-1) (:987-994) |
| 区分 (i)〜(iii) と写像 | `DP10`:202-214 (フェーズ10 設計 D-5 (ii) の表)、:225-230 (同 (iii) 配備側)、:232-236 (同 (iv) 分担) |
| 共有 limiter の扱い | `DP10`:514-524 (フェーズ10 設計 U-1、(c) は「後から入れられる」)、:497 (同 §4 A-1〜A-4)、:827-828 (同 L10-2・L10-3) |
| 契約 | `spec/data-service-api.v1.json`:279-284 (enforcement_enum)、:303 (1.8.0 の無条件義務)。`process_ceilings` は契約に無い (`spec/CCR_DISPOSITION.md`:233) |
| 不変条件 | `security/SECURITY_INVARIANTS_V1.md`:226-250 (SI-08。"Implementation freedom" は :242-243) |
| 現行の制御主張 | `security/CONTROL_MAPPING.md`:710-711 (r2db の写像)、:903-904 (MitateDB の写像)、:962 (R-52 と下限)、:985-989 (開示された限界、C-26 は 1 process) |

### 1.3 現物で確かめた事実 (本書の補足)

**区分 (ii) の状態の置き場 (両 peer)**

| class | plane | 認証の前後 | r2db の状態 | MitateDB の状態 | 窓の形 (現物) |
|---|---|---|---|---|---|
| `requests_per_minute` | data | 後 (credential 単位) | `r2db-api/src/r2db_api/service.py`:693-694 (`_rate_lock` / `_rate_windows`)、`_acquire_rate` :1103-1109、呼び出し :1041 (`_check` の後) | `MitateDB-api/src/mitatedb_api/cell.py`:332-333、`acquire_rate` :337-344、呼び出し :710 | sliding 60 s |
| `concurrency` | data | 前 (配備全体 1 カウンタ) | `service.py`:691-692 (`_active` / `_active_lock`)、`acquire_concurrency_slot` :1056-、`http.py`:492、:514 | `cell.py`:334-335、`acquire_concurrency_slot` :373- | カウンタ |
| `control_requests_per_minute` | control | 前 (global) | `r2db-api/src/r2db_api/control_plane.py`:587、`_check_rate` :1398-1412 | `MitateDB-api/src/mitatedb_api/control_plane.py`:1263、`_check_rate` :1320-1330 | sliding 60 s (r2db は docstring :1402 が sliding を意図して残すと明記) |
| `audit_requests_per_minute` | control | 前 (global) | `control_plane.py`:599、`_check_audit_rate` :1421-1435 | `control_plane.py`:1285、:1344-1358 | sliding 60 s |

**写像の置き場**: r2db data `r2db-api/src/r2db_api/capabilities_document.py`:12 (集合)、:128-135 (式は :131)。r2db control `control_plane.py`:141 (集合)、:626-629。MitateDB data `MitateDB-api/src/mitatedb_api/capabilities_document.py`:44 (`_in_memory_enforcement`)、:322、:327。MitateDB control `control_plane.py`:1575-1577。

**ceiling の受け渡し**: r2db `main.py`:434 (読み取り)、:617 (`DataService(process_ceiling=...)`)、`service.py`:672-674。MitateDB `main.py`:378、:518。

**uvicorn 0.52.4 の multi-process (package 内の経路)**

- `--workers` > 1 は import string を要し、無ければ起動失敗 (`uvicorn/main.py`:603-607)。supervisor は socket を 1 回 bind して子に渡し、自身は app を読み込まない (同 :603-619)。
- 子は `spawn` 文脈で起動する (`uvicorn/_subprocess.py`:18、:51)。子ごとに module を import し直すので `app = build_app()` は子ごとに走る。
- 死んだ・応答しない子は kill の後に置き換える (kill が先、`uvicorn/supervisors/multiprocess.py`:214-240)。子が起動前に失敗 (`STARTUP_FAILURE`) すると親ごと止まる (同 :225-230)。
- SIGHUP の `restart_all` は子を 1 本ずつ「新を ready にしてから旧を止める」(同 :173-194)。この間だけ子は N+1 本になる。
- `--workers` を渡さないとき `WEB_CONCURRENCY` を読む (`uvicorn/config.py`:352-353)。
- `--fd` は単一 process と multi-process で同じ `socket.fromfd` を通る (`uvicorn/config.py`:568-569、`uvicorn/server.py`:149-151)。

## 2. 守るべき条件 (枠 §2、逐語)

```text
1. 契約 1.11.0 不変。1.8.0 の無条件義務 (:303): `enforced` は「base URL を同時に serve し得る全 process にわたって bound が成り立つ」ときだけ。`deployment_required` は per-process bound かつ複数 process のとき。
2. SI-08 (資源境界) の帰結 = 区分 (ii) の 4 class の宣言と実際の bound が一致していること。実装手段は自由 (SECURITY_INVARIANTS :220-250 "Implementation freedom")。新しい invariant は足さない (CLAUDE.md)。
3. 両 peer が同じ安全帰結を出す。platform 固有の手段は違ってよい。同名 helper は `_ISOMORPHIC_TARGETS` (isomorphism test) に登録。
4. `process_ceilings` 機構 (platform_declarations、F-15 fail-fast、`ops declare-process-ceilings`、C-26 (4)(5)) は残す。意味 (= base URL を同時に serve し得る process 数の上限) は変えない。
5. pre-auth の admission (concurrency slot、control / audit の rate window) は認証前に DB 往復を足さない (未認証要求で DB 仕事を起こさない = T-07 の増幅を避ける)。
6. §0.1.4 の 1 (K=1 の非退行 +40% / p95 +50%) を守る。§0.1.4 の 2 (K=32 / K=1 ≤ 8、両 peer、2 run とも) を real-server plug で満たす。判定規則は R-101 WO §10.1 D-16 の逐語を再利用し、計測前に固定する。
7. 接続予算: process 数 × pool。r2db は R-91 の headroom 算術が既に `process_ceilings.data` を乗数にしている (`platform_declarations.py:1343-1375`)。MitateDB は application ごとの永続接続 × process 数。宣言 (`process_ceilings`) と実 process 数の一致は runbook 規律 + 配備後チェック (L10-2) — これは変えない。
8. R-52 (rollout の重なりで一時的に process が 2 倍) は本件で解かないが、採る置き場がその重なりで何を保つか (何を保たないか) を明記する。
9. 依頼者の設計原則: 先送りしない・シンプル・制約で回避しない・誇れる成果物。宣言値を落として済ませる案は「制約で回避」に当たる。
```

## 3. 決定 (監督案。依頼者裁定の対象は §5)

### D-1 worker の形 = uvicorn の `--workers N`

```text
D-1 **worker の形 = uvicorn の `--workers N`** (uvicorn 0.52 の multiprocess supervisor。app は既に import string `main:app`)。r2db は systemd unit の ExecStart に `--workers` を足す。MitateDB は Dockerfile CMD に `--workers` を足し、Cloud Run では process 数 = instances × workers を `process_ceilings` に宣言する (Invariant 1 の一般化は D-5 (iii) で済んでいる)。N は env (`R2DB_WORKERS` / `MITATEDB_WORKERS`)。既定は 1 (現行の配備を変えない)。計測は N=4 (thread limiter 4 × 4 process、開発機 10 core)。
  根拠: 既存の起動形 (import string) をそのまま使え、supervisor が別途要らない。gunicorn は依存を増やす。OS レベルの N unit は nginx 側の upstream 変更を要し peer ごとに形が違う。
```

- 変える行: r2db `r2db-api/deploy/systemd/r2dbsvc-api.service`:60 の `ExecStart`、MitateDB `MitateDB-api/docker/Dockerfile`:145 の `CMD` (data と control の 2 分岐を持つ 1 行)。
- 待受は supervisor の 1 socket を子が共有する (§1.3)。nginx の upstream は 1 本のまま。
- 根拠 (補足): 子が死んでも supervisor が置き換える (§1.3)。子の起動失敗は親ごと止まるので、F-15 等の fail-fast は配備全体の起動失敗として現れる (推測: `build_app()` の例外が子の `STARTUP_FAILURE` になる経路は現物で未確認)。
- **壊すとどう見えるか**: `--workers` を外すと N=1 に戻り、§7 の D-16 が 15.7 / 18.7 倍 (§1.1) に戻って不成立。import string でない app に `--workers` を渡すと uvicorn が起動を拒む (`uvicorn/main.py`:603-607)。

### D-2 `build_app()` は worker ごとに走る

```text
D-2 **`build_app()` は worker ごとに走る**。startup の副作用 (registry 検証、宣言読み取り、3 段チェック、cell / backend の eager open、audit flush thread) は全部読み取りか process 内資源なので N 回走ってよい (migration は `ops` CLI で別)。設計文書は startup 副作用を全件列挙し、それぞれ「N 回走って安全」と根拠を書く。
```

**startup の副作用の全件表 — r2db (`r2db-api/src/r2db_api/main.py`)**

| # | 副作用 | file:line | 種類 | N 回走って安全な根拠 |
|---|---|---|---|---|
| 1 | thread limit の env 読み取り | :384 (実装 :284-301) | 純関数 | 外部状態を読まない |
| 2 | `R2DB_SERVE_APPS` の registry 検証 | :404 (実装 :317-346、接続 :337) | platform DB の読み取り | SELECT のみ。接続は関数内で閉じる |
| 3 | `process_ceilings` ほか宣言の読み取り (F-15) | :429-439 (接続 :430) | platform DB の読み取り | SELECT のみ |
| 4 | credential store / durable audit sink の構築 | :493、:502 | process 内 pool の生成 | pool は process ごと (接続数は §3 D-3 の接続予算) |
| 5 | writer role の検査・F-16・F-18 | :512-540 (:513、:532、:537) | `pg_roles` / `pg_settings` の読み取り | 読み取りのみ。F-16 はこの process の pool 構成だけを見る (:517-531 のコメント) |
| 6 | served application の cell を eager に open | :550-598 (`PostgresCell` :560、`verify_platform_upgrades_applied` は `r2db-api/src/r2db_api/postgres.py`:979) | 読み取り + process 内 pool | 台帳の読み取りと process 内 pool。F-12 はこの process の log に 1 行 |
| 7 | `DataService` の構築 | :600-617 | process 内状態 | limit 状態・audit buffer・denial coalescer はこの process のもの |
| 8 | `ControlAuthority.register_application` の loop | :620-622 | process 内の登録と in-memory `_audit` への append (`service.py`:1322-1324) | DB に書かない。in-memory の記録が process ごとに 1 件 |
| 9 | lifespan の audit flush thread | :641-694 (thread :657) | process 内 thread | この process の buffer だけを flush する |

**同 — MitateDB (`MitateDB-api/src/mitatedb_api/main.py`)**

| # | 副作用 | file:line | 種類 | N 回走って安全な根拠 |
|---|---|---|---|---|
| 1 | thread limit の env 読み取り | :278 (実装 :209-226) | 純関数 | 外部状態を読まない |
| 2 | pepper の分離検査 | :279-286 | 純関数 | 値の比較のみ |
| 3 | `MITATEDB_SERVE_APPS` の registry 検証 | :315 (実装 :244-265、接続 :256) | platform DB の読み取り | SELECT のみ |
| 4 | platform pool の構築 | :349 | process 内 pool | process ごと |
| 5 | durable audit sink の構築 | :375 | process 内 | 書き込みは要求時 |
| 6 | 宣言の読み取りと writer role・F-16・F-18 の検査 | :378-419 (:394、:411、:416) | 読み取り | 読み取りのみ |
| 7 | `AuditRouter` と credential store | :447-453 | process 内 | process ごと |
| 8 | `_LimitStateHolder()` | :477 | process 内状態 | D-3 で区分 (ii) の置き場が変わる対象 |
| 9 | served application の `PostgresBackend` を eager に構築 | :480-519 (:495、cell :510) | process 内の永続接続 (`MitateDB-api/src/mitatedb_api/backend_postgres.py`:294) | 接続は process ごと (接続予算は §9 (e)) |
| 10 | lifespan の audit flush thread | :571-621 (thread :587) | process 内 thread | この process の buffer だけ |

- 両 peer とも migration は `ops` CLI が打ち、`main.py` は打たない。
- 量が N 倍になるもの (安全帰結は変わらない): audit buffer の容量 (`service.py`:162、`MitateDB-api/src/mitatedb_api/audit_dispatch.py`:141 が「per-process, not per-deployment」と明記)、denial coalescer の行 (`service.py`:414 が「one row per process/instance」を正常とする)、thread limiter (`http.py`:286-321 r2db、:252- MitateDB) は process ごとに 4。
- **壊すとどう見えるか**: startup に共有状態への書き込みを足すと N 回走る (本表に「書く」行が現れる)。F-15 の行を消すと各子が起動に失敗し、supervisor ごと止まる (§1.3)。

### D-3 区分 (ii) の置き場 = class ごとに 2 分する (両 peer 同型)

```text
D-3 **区分 (ii) の置き場 = class ごとに 2 分する (両 peer 同型)**:
  - post-auth で credential 単位の `requests_per_minute` → **PostgreSQL の共有状態** (platform DB の 1 表、credential ごとの fixed window 行を `UPDATE ... RETURNING` で原子的に数える)。= R-18 (c)。1 要求 1 往復を足す (R-80 の実測では r2db 8 tx/req、MitateDB 5 tx/req に対する +1)。sliding → fixed window は宣言の意味 (1 分あたり) を変えない: 文書に明記。
  - pre-auth の `concurrency`、`control_requests_per_minute`、`audit_requests_per_minute` → **静的分割** (process ごとの bound = 宣言値 ÷ `process_ceilings` の該当 plane の値、切り捨て、最小 1)。合計が宣言値を超えないので 1.8.0 の意味で `enforced` が真。crash 安全 (process が死ねば slot も消える)。DB 往復なし (条件 5)。
  - 写像: 区分 (ii) は ceiling に依らず `enforced`。`deployment_required` はどちらの peer も宣言しなくなる (enum の値は契約に残る)。
  根拠: 共有 counter を PG に置くと concurrency の slot は process が死んだとき漏れる (session 束縛の advisory lock で N slot を表すのは O(limit) 往復)。分割は crash 安全でゼロ往復だが利用率を落とす (負荷が偏ると宣言値の 1/N で拒否)。rate window は時間で自然に回収されるので PG に置ける。post-auth の class だけを DB に置けば未認証要求の増幅が無い。
```

**(1) `requests_per_minute` の fixed window の意味**

- 窓 = 60 秒の区切り。credential ごと・窓ごとに 1 行を持ち、その行の数が宣言値 L に達したら `LIMIT_EXCEEDED` (`limit_class` = `requests_per_minute`、現行と同じ details)。
- 宣言の意味は「1 分あたり L」のまま (契約の limits は class 名と値だけを持ち、窓の形を定めない。`spec/data-service-api.v1.json`:914)。現行の sliding window (§1.3 の表) からの変更の可否は Q-2。
- 数える位置は現行と同じ認証の後 (r2db `service.py`:1041、MitateDB `cell.py`:710)。未認証の要求はこの表に触れない (条件 5)。
- 表は platform schema に置き、追加は platform 単発 migration とする。番号は現物の次番: **r2db `0015`** (`r2db-api/migrations/` の最後は `0014_auditreader_statement_timeout.sql`)、**MitateDB `0016`** (最後は per-application の `0015_row_order_column_upgrade.sql`。platform 単発は `_upgrade.sql` で終わらせない、`DP10` の D-5 (ii) 機構の実装点)。
- 1 要求あたりの往復は +1 (R-80 の実測 `RM`:500 の要求あたり transaction 数に対して)。

**(2) 静的分割の規則**

- plane p の宣言 ceiling を P_p (`process_ceilings.data` / `.control`)、class c の宣言値を L_c とする。process ごとの bound は **b_c = max(1, ⌊L_c / P_p⌋)**。
- 当てはめ: `concurrency` と data plane は P_data、`control_requests_per_minute`・`audit_requests_per_minute` と control plane は P_control。
- 各 process の仕組みは現行のまま (カウンタ・sliding 窓)。上限の値だけが L_c から b_c になる。
- 公開する `limits` は宣言値 L_c のまま (`capabilities_document.py` の `limits.as_dict()`、:110)。
- 既定値での例 (P=4): `concurrency` 32 → 8 (`r2db-api/src/r2db_api/limits.py`:17、`MitateDB-api/src/mitatedb_api/config.py`:79)。`control_requests_per_minute` r2db 60 → 15 (`limits.py`:343)、MitateDB 200 → 50 (`MitateDB-api/src/mitatedb_api/control_plane.py`:150)。`audit_requests_per_minute` 60 → 15 (`limits.py`:364、`control_plane.py`:158)。
- 合計: 同時に serve する process が P_p 以下なら、合計 ≤ P_p × ⌊L_c / P_p⌋ ≤ L_c (L_c ≥ P_p のとき)。論証の確認は §9 (a)。

**(3) 写像の変更点**

| peer / plane | 現行 | 変更後 |
|---|---|---|
| r2db data | `capabilities_document.py`:131 `"enforced" if process_ceiling <= 1 else "deployment_required"` (集合 :12) | 区分 (ii) も `"enforced"` |
| r2db control | `control_plane.py`:626-629 (集合 :141) | 同上 |
| MitateDB data | `capabilities_document.py`:44 `_in_memory_enforcement`、:322、:327 | 同上 |
| MitateDB control | `control_plane.py`:1575-1577 (`>= 2` で 2 class を上書き) | 上書きを外す |

- 区分 (i) と (iii) の行は変えない。`execution_ms` / `idempotency_retention_ms` の `reference_wall_clock` も変えない。
- `process_ceilings` は写像の入力でなくなり、静的分割の分母と接続予算 (F-18) の乗数に残る (条件 4)。フェーズ10 設計 L10-3 が拡張点として挙げた「ceiling ≥ 2 でも `enforced`」の形 (`DP10`:828) に当たる。

**(4) 接続予算の算術 (現行の式、乗数は宣言 ceiling)**

- F-18 (両 peer 同型): 下限 = P_data × (platform_pool_floor + application_pair_floor [登録 application ≥ 1 のとき]) + P_control × control_plane_floor。platform_pool_floor = 2 × `concurrency`、application_pair_floor = 2 × `concurrency`、control_plane_floor = 16。上限は登録 application 数を掛け auditreader 4 を足す (開示のみ)。r2db `r2db-api/src/r2db_api/platform_declarations.py`:1343-1375 (定数 :947、:954、:960)、MitateDB `MitateDB-api/src/mitatedb_api/platform_declarations.py`:1209-1235、:1318-1350 (定数 :917、:927、:934)。判定は `下限 + superuser_reserved_connections + reserved_connections <= max_connections`。
- F-16 (role の `CONNECTION LIMIT`) は起動した process の pool 構成 1 本分だけを床にする (r2db `main.py`:517-536、MitateDB `main.py`:411)。
- role の `CONNECTION LIMIT` の現行値: r2db `r2db-api/migrations/0013_role_connection_limits.sql`:109-110 (api 68、controlplane 20)、:132-133 (application の runtime / developer 各 36)。MitateDB `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`:89-91 (api 132、controlplane 36、auditreader 12)、:113、:116 (application の role 各 68。並走 2 を前提にした値、`RM`:472)。
- MitateDB の application は process ごとに永続接続を持つ (`backend_postgres.py`:294)。N process なら同じ application の永続接続も N 組になる。
- r2db の role pool は要求に応じて接続を作る (`postgres.py`:266-271 の `_created`)。
- N と接続予算の整合は §9 (e)、計測の前提は §7.3。

**根拠 (補足)**: 区分 (ii) のうち `requests_per_minute` だけが credential を鍵にし、認証の後でしか数えられない (§1.3 の表)。残り 3 class は認証の前に数える (`service.py`:1056- の docstring、`control_plane.py`:1400 の docstring) ので、DB に置くと未認証要求が DB 仕事を起こす (条件 5)。

**壊すとどう見えるか**: `requests_per_minute` を process 内の窓に戻すと、2 process に振った要求が 2L まで通り、新条件 (b) (§3 D-4) が赤になる。静的分割を外す (各 process が L を持つ) と 2 process で L を超えて in-flight になり、新条件 (a) が赤になる。写像を現行 (ceiling ≥ 2 で `deployment_required`) に戻すと、改めた C-26 (4) が赤になる。

### D-4 conformance

```text
D-4 **conformance**: C-26 (4) を「ceiling 2 でも `enforced`」に改め、**新条件 (番号は conformance WP で採番。§10 の裁定 7)** (launcher で実 process を 2 本起動し、(a) `concurrency` を hold_in_flight で process をまたいで数え宣言値を超えないこと、(b) `requests_per_minute` を 2 process に振って宣言値ちょうどで LIMIT_EXCEEDED になること) を足す。launcher (`socket_harness.start_uvicorn_subprocess`、両 `real_server_*.py`) に `workers` 引数。C-05 の honest limits (「実 process 数を観測しない」) を 新条件 の分だけ狭める。
```

- 本書の本文 (枠の逐語を除く) では新条件の番号を書かない (`conformance-tests/CONDITIONS.md` の最後は C-31、:60。`tools/check_doc_refs.py` は定義の無い条件番号を参照切れとして止める)。番号は WP-1 が行を足すときに確定する。
- 触る現物: C-26 (4) のテスト `conformance-tests/test_c26_composition_root.py`:220- (`test_c26_ceiling_maps_to_limit_enforcement`)、C-26 の行 `conformance-tests/CONDITIONS.md`:55、C-05 の行 :34 の honest limits (6)、launcher `conformance-tests/socket_harness.py`:743-814 (`start_uvicorn_subprocess`、1 呼び出し 1 process)、`r2db-api/conformance/real_server_r2db.py`:613- (`start`)、:711- (`restart`)、`MitateDB-api/conformance/real_server_mitatedb.py`:563-、:651-。
- 現行の launcher は `ceilings` を宣言に渡すだけで、起動する uvicorn は data・control 各 1 本である (`real_server_r2db.py`:667-677)。
- **壊すとどう見えるか**: 写像だけを変えて C-26 (4) を直さないと C-26 (4) が赤。launcher に `workers` を足さないと新条件は実 process 1 本で走り、(a)(b) とも観測対象が無い (`OPERATING_CONDITIONS.md` §1.5 の 32 の空振り)。

### D-5 計測

```text
D-5 **計測**: `tools/perf_baseline.py --real-server <peer> --workers N`。判定規則は D-16 の逐語 (K=1 と K=32 `--warmup 3 --n 15`、K=32 は 2 run、両 peer とも 2 run が 8 倍以内)。加えて K=1 の非退行 (§0.1.4 の 1) を N=1 と N=4 で記録。R-101 行はこの結果で閉じる (R-113 と同じ変更セットで判定)。
```

- 計画は §7。R-101 行の閉止を本変更セットで行うかは Q-5。
- **壊すとどう見えるか**: 判定規則を計測の後に動かすと、R-101 作業指示書 §7.2 の (c) (計測後に動かさない) に反する。

### D-6 クラス

```text
D-6 **クラス**: `conformance-tests/` と `security/CONTROL_MAPPING.md`、migration (platform 表の追加 = r2db `0015` / MitateDB 次番。platform 単発、`_upgrade.sql` ではない) に触るので Class C 以上 (`tools/change_class.py` で確定)。契約に触れないので設計レビュー 1 回。規模 L (台帳)。
```

- 現物で確定した番号: r2db `0015`、MitateDB `0016` (D-3 の (1))。
- `RM` §9 の 8 の表では、`security/` 配下と `_ISOMORPHIC_TARGETS` 集合の増減は Class D、`conformance-tests/` 配下と登録 helper の本体は Class C である。WP ごとの見込みは §6。
- 設計レビューの回数は規模の表 (`OPERATING_CONDITIONS.md` §1.13 の 74、L は「契約変更は設計レビュー 2 回」) による。
- **壊すとどう見えるか**: 宣言したクラスが `tools/change_class.py` の判定より軽いと、必要な証拠 (`RM` §9 の 8 の証拠列) が欠ける。

### D-7 記録

```text
D-7 **記録**: 台帳 R-113・R-101・R-18・R-52 行に【追記】、CONTROL_MAPPING の SI-08 の Control 主張 (区分 (ii) の写像) を改める、両 runbook (workers と ceilings の対応、接続予算)、`tools/PERF_BASELINE_README.md`。
```

- 経路は §8。
- **壊すとどう見えるか**: `security/CONTROL_MAPPING.md`:711、:904 の「ceiling >= 2 publishes exactly those as `deployment_required`」を残すと、Control 主張がコードと食い違う。

## 4. 却下した代替案と理由 (枠 §4、逐語)

```text
- (α) in-memory のまま `process_ceilings` = N を宣言し `deployment_required` に落とす: 契約上は正しいが bound が N 倍に緩む = 「制約で回避」。却下。
- (β) 4 class 全部を PG 共有: concurrency の slot が crash で漏れる / pre-auth に DB 往復 (条件 5)。却下 (rate だけ PG = D-3)。
- (γ) 4 class 全部を静的分割: `requests_per_minute` は credential 単位で負荷が偏りやすく (1 credential の要求が 1 process に偏れば宣言値の 1/N で拒否)、利用者に見える。却下 (pre-auth の class だけ分割 = D-3)。
- Redis 等の外部 limiter: 依存を増やす。PostgreSQL は両 peer に既にある。却下 (フェーズ10 U-1 と同じ理由の半分)。
- nginx / Cloud Run の rate limit: credential 単位の bound は認証後にしか分からない。却下。
- gunicorn + uvicorn worker: 依存追加、uvicorn 単体で足りる。却下。
- free-threaded Python (3.13t) / sub-interpreter: 開発機は 3.11、psycopg / uvicorn の対応未確認、実験的。却下 (将来の再検討点として記す)。
- async psycopg (R-84): J-3 不成立 (DB 待ちが主体でない)。R-84 行の却下理由のとおり。
- threads のみ: 実測済み (limit 1 でも同じ形)。
```

- (α) はフェーズ10 設計 U-1 で採った (a)+(ii) の現行の形そのもの (`DP10`:514-524)。本件はその上で (c) を後から入れる (同 :522 の「(c) を後から入れられる」)。
- 「threads のみ」の実測: `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` §2.2 の thread limit {既定, 4, 1} × K と、R-101 作業指示書 §7.1 の床の算術。
- R-84 の行: `RM`:504。

## 5. 依頼者判断待ち (枠 §5。両論のまま置く)

### Q-1 区分 (ii) の置き場

- 選択肢: (A) D-3 の 2 分 (rate = PG 共有 / pre-auth = 静的分割)。(B) (α) 宣言で済ませる (in-memory のまま ceiling = N、`deployment_required`)。(C) (γ) 4 class 全部を静的分割。
- (A) の側: 1.8.0 の意味で `enforced` を保ち、pre-auth に DB 往復を足さない。`requests_per_minute` の偏りによる早期拒否が無い。代わりに 1 要求 1 往復と platform 表 1 つを足し、pre-auth の 3 class は偏ると宣言値の 1/N で拒否する。
- (B) の側: コードの変更が最小で、契約上は正しい。代わりに bound が N 倍に緩み、条件 9 の「制約で回避」に当たる。
- (C) の側: DB 往復も表も足さない。代わりに `requests_per_minute` も 1 credential の偏りで宣言値の 1/N で拒否し、利用者に見える。
- 監督案: (A) (D-3)。
- 裁定: 

### Q-2 `requests_per_minute` の窓の形

- 選択肢: (A) fixed window (PG の 1 行)。(B) sliding (現行) のまま PG に置く。
- (A) の側: credential ごと・窓ごとに 1 行を 1 文で原子的に数えられる。契約は「1 分あたり」しか言わない (D-3 の (1))。
- (B) の側: 現行の挙動を変えない。r2db の control plane の窓の docstring は、fixed window は窓の境目で 2 窓分の突発を許し sliding の方が厳しい、として sliding を意図して残すと書く (`r2db-api/src/r2db_api/control_plane.py`:1402)。推測: PG の上で sliding を表すには要求ごとの時刻を持つ行か区間の集計が要り、1 行 1 文にはならない。
- 監督案: (A) fixed。
- 裁定: 

### Q-3 N の既定値

- 選択肢: (A) 1 (現行の配備を変えない。配備者が明示する)。(B) core 数から導く。
- (A) の側: 既存配備は宣言 `process_ceilings` = 1 のままで一致する。N と ceiling を配備者が同時に書く。
- (B) の側: 何も書かなくても GIL の外に出る。代わりに実 process 数が宣言と独立に決まり、不一致 (§9 (c)) の機会が増える。
- 監督案: (A) 1。
- 裁定: 

### Q-4 MitateDB の Cloud Run で増やす軸

- 選択肢: (A) container 内の workers。(B) instances。(C) 両方可、ceilings = instances × workers。
- (A) の側: 1 instance の中で GIL の外に出る。Cloud Run の instance 数は現行の Invariant 1 (`MitateDB-api/docs/cloud-run-cloud-sql.md`:1327-1358) のまま。
- (B) の側: container の形 (CMD) を変えない。水平に増える。
- (C) の側: 両方の自由度を残す。代わりに runbook に積の算術と、両方を変えたときの宣言の書き直しを置く。
- 監督案: (C) 両方可、ceilings = 積。runbook に算術。
- 裁定: 

### Q-5 R-101 の閉止を本変更セットの D-5 の結果で行うか

- 選択肢: (A) 行う (D-5 の D-16 成立で R-101 を閉じる)。(B) 行わない (R-113 と R-101 を別に閉じる)。
- (A) の側: 閉止形 (`RM` §0.1.4 の 2) は R-101 のものであり、同じ判定規則で同じ計測器を使う。R-101 の行は「次は R-113」と記している (`RM`:521)。
- (B) の側: R-101 の範囲は直列化の切り分けと 1 process 内の是正で、multi-process は R-113 の範囲として起票された (R-101 作業指示書 §12 の (12-1))。
- 監督案: (A) 行う。
- 裁定: 

## 6. WP 分割案 (契約・conformance を実装より先に置く)

各 WP の完了条件・変異の対応表・道具の引数は作業指示書 (Change Set Manifest、`RM` §9 の 9) に置く。クラスは `tools/change_class.py` で確定する。

| WP | 内容 | 触る経路 (現物) | クラス見込み |
|---|---|---|---|
| **WP-1** 契約・conformance | C-26 (4) を「ceiling 2 でも `enforced`」に改める。新条件 (§3 D-4 の (a)(b)) の行とテストを足す。launcher に `workers`。C-05 の honest limits (6) を新条件の分だけ狭める。`COLLECTION_FLOOR` の追随 | `conformance-tests/CONDITIONS.md` (:34、:55、新しい行)、`conformance-tests/test_c26_composition_root.py`、新条件のテストファイル (新規)、`conformance-tests/socket_harness.py`、`r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py`、`conformance-tests/` の `COLLECTION_FLOOR` | C (`conformance-tests/` 配下)。launcher に同名 helper を足して登録すれば D |
| **WP-2** r2db 実装 | migration `0015` (platform 表)、`requests_per_minute` を PG の fixed window へ、pre-auth 3 class の静的分割、写像の変更、`main.py` / `control_main.py` の配線、migration 一覧の追随 | `r2db-api/migrations/0015_*.sql` (新規)、`r2db-api/src/r2db_api/service.py`、`control_plane.py`、`capabilities_document.py`、`main.py`、`control_main.py`、`credential_store.py` または新 module、`ops.py`、`r2db-api/conformance/conformance_adapter_r2db_http.py`、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh`、`r2db-api/tests/` | D 見込み (同名 helper を `_ISOMORPHIC_TARGETS` に足すとき。`RM` §9 の 8) |
| **WP-3** MitateDB 実装 | migration `0016` (platform 表)、`_LimitStateHolder` の `requests_per_minute` を PG へ、pre-auth 3 class の静的分割、写像の変更、配線、migration 一覧の追随 | `MitateDB-api/migrations/0016_*.sql` (新規)、`MitateDB-api/src/mitatedb_api/cell.py`、`control_plane.py`、`capabilities_document.py`、`main.py`、`control_composition.py`、`credential_store_postgres.py` または新 module、`ops.py`、`platform_declarations.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`、`MitateDB-api/tests/` | 同上 |
| **WP-4** 計測 | `tools/perf_baseline.py` に `--workers N` (launcher に渡し、宣言 ceiling を N にする)。§7 の実測は監督 | `tools/perf_baseline.py`、`tools/tests/`、`tools/PERF_BASELINE_README.md` | B |
| **WP-5** 配備 | `--workers` と env、ceilings との対応、接続予算を配備物と runbook に | `r2db-api/deploy/systemd/r2dbsvc-api.service` (:60)、`r2db-api/deploy/env/api.env.example`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (:96-106)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`MitateDB-api/docker/Dockerfile` (:145)、`MitateDB-api/docs/cloud-run-cloud-sql.md` (:1327-1358 Invariant 1 ほか) | B (unit・Dockerfile)。runbook だけなら A |
| **WP-6** 記録 | 台帳・`CONTROL_MAPPING`・本書の版上げ | §8 | D (`security/` 配下) |

- 順序: WP-1 → WP-2 / WP-3 → WP-4 → §7 の実測 → WP-5 → WP-6。WP-1 の新テストは WP-2 / WP-3 が入るまで赤である (変異先行の形)。統合の単位は監督が決める。
- WP-2 と WP-3 を並行させるときは、触るファイルの重なりが 0 であることを作業指示書の表で示す (`OPERATING_CONDITIONS.md` §1.2 の 16、17)。上表の経路は peer ごとに分かれるが、同名 helper の本体を両 peer で一致させる (条件 3) ので、登録の表 (`r2db-api/tests/test_audit_query.py`:2393 の `_ISOMORPHIC_TARGETS`) を触る WP は 1 つに寄せる。
- 上表の「migration 一覧の追随」の経路は、直近の platform migration の名前を持つファイルの現物 (`git grep` で r2db `0014_auditreader_statement_timeout`、MitateDB `0011_process_ceilings` / `0014_role_connection_limits_rollout` を持つもの) から拾った。テスト以外の全件を作業指示書で確定する。

## 7. 計測計画

### 7.1 判定規則 (R-101 作業指示書 §10.1 の D-16、逐語。計測前に固定)

```text
D-16 閉止の判定規則 (計測前に固定): real-server plug で K=1 と K=32 (`--warmup 3 --n 15`) を取り、K=32 は 2 run 取る。query の p50 の K=32 / K=1 の比が両 peer で K=32 の 2 run とも 8 倍以内 = R-101 閉止 (RM §0.1.4 の 2 の改訂形)。ε (K=32 の 2 run の相対差) と δ = max(10%, 2ε) は記録だけで、判定には使わない。本変更セットでは server は 1 process なので 8 倍は満たさない見込み — その実測を設計メモ v0.3 §6 に逐語で残し、R-113 (multi-process、規模 L) の出発点にする。
```

- 本件での当てはめ: 判定は N=4 の行だけで行う。N=1 の行は同じ木での対照として記録する。最後の文 (1 process の見込み) は R-101 のものであり、本件の判定に使わない。
- K=1 の非退行 (`RM` §0.1.4 の 1): 変更セットの完了ゲートで取る K=1 の `perf_baseline.py --warmup 20 --n 200` の p50 が同一 plug・同一 op の直近基準値の +40% 以内、p95 が +50% 以内。

### 7.2 条件

- 道具: `tools/perf_baseline.py --real-server <peer> --workers N` (WP-4)。client は子 process (`--client-processes` 既定 8、実際の数は min(8, K))。thread limit は既定 4。
- 宣言: launcher の `start(ceilings=...)` に data = N を渡す。control の値は launcher が起動する control の process 数とする。
- 実行順: peer ごとに N=1 の K=1 → K=32 → K=32、次に N=4 の K=1 → K=32 → K=32 (直列、他の pytest と nginx 無し。R-101 作業指示書 §10.2 の 1)。
- 後始末の照合: 各 run の後、`pg_database` / `pg_roles` の差分 0、launcher が起こした uvicorn (supervisor と子の全部) / nginx が残っていない (同 §10.2 の 4)。
- 推測: 開発機 10 core を server の N process、client 8 process、PostgreSQL が分け合う。

### 7.3 前提の算術 (計測の前に確かめる)

- 使い捨てクラスタの `max_connections` は 300 (`tools/testpg/dsa_testpg.py`:837)。
- F-18 の下限 (§3 D-3 の (4)) を既定 `concurrency` 32・登録 application ≥ 1 で数えると、P_data × 128 + P_control × 16。P_data = 4、P_control = 1 で 528 となり 300 を超える。P_data = 2 では 272。
- 計測の launcher の宣言値でこの判定が通るかを WP-4 の作業指示書で確かめる (§9 (e))。

### 7.4 実測の表 (空欄。監督が埋める)

**表 7-1 real-server plug (`query` p50、ms)**

| peer | N | K=1 | K=32 (1 回目) | K=32 (2 回目) | 比 (1 回目) | 比 (2 回目) | ε | 判定 (N=4 のみ) |
|---|---|---|---|---|---|---|---|---|
| r2db-api | 1 | | | | | | | — |
| r2db-api | 4 | | | | | | | |
| MitateDB-api | 1 | | | | | | | — |
| MitateDB-api | 4 | | | | | | | |

**表 7-2 K=1 の非退行 (`--warmup 20 --n 200`)**

| plug | op | 基準 p50 | 後 p50 | 差 | 基準 p95 | 後 p95 | 差 | +40% / +50% 以内 |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

- 表 7-2 の行 (plug と op) と基準値の出所は作業指示書で固定する。real-server plug の N=1 / N=4 は同じ表に行を足す。

## 8. 記録 (統合時、監督)

- 台帳 `RM` §8: R-113 (:533)、R-101 (:521)、R-18 (:438)、R-52 (:472) の各行に【追記】。行は消さない (`OPERATING_CONDITIONS.md` §1.8 の 56)。版上げは変更セットごと (同 §1.13 の 75)、版数ログの回転 (同 §1.16 の 78)。
- `security/CONTROL_MAPPING.md`: SI-08 の r2db の写像の主張 (:710-711)、MitateDB の写像の主張 (:903-904)、開示された限界の C-26 の行 (:988) を、区分 (ii) の置き場と新条件に合わせる。
- `conformance-tests/CONDITIONS.md`: C-05 (:34) の honest limits (6)、C-26 (:55)、新条件の行 (WP-1)。
- runbook: r2db `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (:96-106 の `declare-process-ceilings --data 1 --control 1` と単一 uvicorn の記述)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (接続予算)。MitateDB `MitateDB-api/docs/cloud-run-cloud-sql.md` の Invariant 1 (:1327-1358。「in-process windows」「ceiling が 1 のときだけ honest」の記述) と §6.1 / §6.2 の `--max-instances` の値。
- `tools/PERF_BASELINE_README.md`: `--workers`。
- 設計メモ `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` か本書に §7 の実測 (置き場は作業指示書で決める)。

## 9. レビューで確かめてほしい点

**(a) 静的分割で 1.8.0 の「bound holds across every process」が真になる論証。**
- 論証: plane p を同時に serve する process は P_p 以下 (宣言と runbook 規律、条件 7)。各 process は `concurrency` を同時に b = ⌊L/P_p⌋ まで、rate を自分の 60 秒窓で b まで通す。よって配備全体の同時数・任意の 60 秒の数は ≤ P_p × b ≤ L (L ≥ P_p のとき)。`requests_per_minute` は credential・窓ごとに 1 行を全 process が共有するので、process 数に依らず窓ごとに ≤ L。
- 確かめてほしいこと: 切り捨て規則 (最小 1) の境界で合計が宣言値以下に収まるか。公開する `limits` が L のままで、process 1 本あたり b で拒否することが C-05 V2 (宣言値と実拒否位置の一致、ceiling 1 で駆動) と両立するか。

**(b) fixed window 行の UPDATE の競合と role の最小権限。**
- 同じ credential の要求は全 process で 1 行に集まり、行 lock で直列化する。R-101 の計測は runtime bearer 1 本で `query` を送る (R-101 作業指示書 D-15) ので、K=32 の全要求が 1 行を取り合う。推測: 行 lock の保持は 1 文の間だけ。
- 行の作成 (credential の初回・窓の切り替わり) を 1 文で原子的に行う形 (`UPDATE ... RETURNING` だけで足りるか)。
- どの role (r2db `r2dbsvc_api` / MitateDB `mitatedbsvc_api` か別の role か) がどの pool で UPDATE するか。その role に新表以外の権限を足さないこと。revoke 済み credential の行の後始末。
- 窓の時刻を DB の時計と process の時計のどちらで決めるか (process ごとに時計がずれると窓の境目がずれる)。

**(c) `process_ceilings` と実 process 数の不一致。**
- 宣言 P < 実 M: pre-auth 3 class の合計は M × ⌊L/P⌋ で L を超え、`enforced` が偽になる (現行の「宣言 1・実 >1」と同じ種類の破れで、緩み幅は M/P 倍)。`requests_per_minute` は PG の行で保たれる。F-16 / F-18 も宣言 P で数えるので接続を少なく見積もる。
- 宣言 P > 実 M: bound は保たれ、利用率が M/P に落ちる。
- 不一致の入口: `--workers` の値、`WEB_CONCURRENCY` (`--workers` 無しでも読まれる、`uvicorn/config.py`:352-353)、Cloud Run の instances。SIGHUP の `restart_all` は一時的に N+1 本にする (`uvicorn/supervisors/multiprocess.py`:173-194)。
- 一致を担うのは runbook 規律と配備後チェック (フェーズ10 設計 L10-2、条件 7)。

**(d) rollout の重なり (R-52) で保たれないもの。**
- 旧と新の revision が同時に serve すると、process は最大 2P になる。pre-auth 3 class の合計は最大 2L になり保たれない。`requests_per_minute` は共有の行なので保たれる。
- 重なりの process 数を `process_ceilings` に宣言すれば、分割の分母と F-18 の下限がその数を数える (`security/CONTROL_MAPPING.md`:962)。代わりに平常時の 1 process の分け前が半分になる。
- r2db の systemd の再起動で重なりが生じるか。推測: `Type=simple` の restart は停止の後に起動するので重ならない (`r2db-api/deploy/systemd/r2dbsvc-api.service`:39)。

**(e) MitateDB の cell 永続接続 × N の接続予算。**
- application ごとの永続接続 (`backend_postgres.py`:294) は process ごとに 1 組で、N process なら N 組。application の role の `CONNECTION LIMIT` は 68 (`0014`、並走 2 前提)。
- platform の api role は process ごとに platform pool (`main.py`:349) と audit sink の一時接続を持つ。F-18 は `process_ceilings.data` を掛けるが (§3 D-3 の (4))、F-16 は 1 process 分だけを床にする (`main.py`:411)。api role の `CONNECTION LIMIT` 132 に対する N process の需要。
- r2db も同じ問い: role pool の最大は `concurrency` (`r2db-api/src/r2db_api/limits.py`:121-) で、role の `CONNECTION LIMIT` は application 36・api 68 (`0013`)。静的分割で 1 process の同時数が b になるとき、pool の最大を L のままにするか b にするか。
- §7.3 の F-18 の算術 (P_data = 4 で 528 > 300) を計測の前提としてどう満たすか。

**(f) 新条件 (a) の保持の手段。**
- `hold_in_flight` は adapter の port で (`conformance-tests/adapter.py`:1742-)、stall 点は concurrency の取得の後・DB 実行の前にある。launcher が起動する本番の composition root の子 process に同じ保持の手段があるか。

**(g) 新条件 (b) の空振り禁止。**
- supervisor の 1 socket を子が共有するので、どの子が要求を受けるかは OS が決める。要求が 2 つの子に実際に分かれたことを観測する手段 (`OPERATING_CONDITIONS.md` §1.5 の 32)。

**(h) 写像の入力から `process_ceilings` が外れること。**
- 写像は ceiling に依らなくなり (§3 D-3 の (3))、ceiling は分割の分母と接続予算に残る。フェーズ10 設計 D-5 (ii) の「壊すとどう見えるか」(`DP10`:241、写像を「常に `enforced`」に固定すると C-26 (4) が赤) の前提が変わる。

## 10. 監督裁定 (v0.2、2026-09-28。起草の疑義に対する裁定。本文と食い違うときは本節が優先する)

1. **契約の文言との衝突 (起草の疑義 1、重大)。** `spec/data-service-api.v1.json`:905 (`limits.profile`) は「a bound kept in per-process memory is enforced for the deployment only while exactly one process serves that base URL」、:303 (`capability_status.rules`) は「declares deployment_required when the bound is held per process and more than one process may serve」と言う。静的分割 (D-3 の (2)) は process 内メモリで数えるので、この 2 文を文字どおりに読むと `enforced` と宣言できない。1.8.0 の義務の趣旨 (bound が全 process にわたって成り立つ) は分割で満たされるが、文言は満たさない。**裁定: Q-1 の (A) と (C) は契約の文言の明確化を伴う = 契約 1.12.0** (従属判断 17: 「宣言値 L を process 数 P で分割し、各 process が ⌊L/P⌋ を超えて通さない bound は、同時に serve する process が P 以下である限り全 process にわたって成り立つので `enforced` である。`deployment_required` は各 process が宣言値 L そのものを独立に持つときに限る」の趣旨で :303 と :905 を改める。義務の追加も client の送るものの変更も無い)。手順はフェーズ9 / 10 と同じ (契約 JSON + companion + obligations entry + `spec/CCR_DISPOSITION.md` + catalog 再生成 + 3 複製 byte 一致 + pair-closing の版フリップ)。**(B) だけが契約に触れない。** 従って設計レビューは (A)(C) で 2 回、(B) で 1 回 (`OPERATING_CONDITIONS.md` §1.7 の 50)。D-6 と §0 はこの裁定で読み替える。§6 の WP 分割は (A)(C) のとき契約 WP を conformance WP の前に置く。
2. **切り捨て規則の「最小 1」は撤回する (疑義 2)。** b_c = ⌊L_c / P_p⌋ とし、分割対象のどの class でも L_c < P_p なら **起動時 fail-fast** (F-15 と同じ扱い。`ops verify-declarations` にも同じ検査を足す。番号は作業指示書で採番)。理由: 最小 1 では合計が P_p になり L_c を超える (§9 (a) の論証は L_c ≥ P_p を前提にしており、その前提を検査で保証する)。
3. **pool の寸法と接続予算は分け前 b で数える (疑義 6、§9 (e)、§7.3)。** 静的分割のとき、1 process の pool の最大は b (`concurrency` の分け前) とし、F-18 の下限の `2 × concurrency` は `2 × b` に、F-16 (role の `CONNECTION LIMIT` の床) は P_data × (1 process の pool 構成) に改める。こうすると総需要は P × 2b ≤ 2L で現行 (1 process、2L) と同じ水準に収まる。§7.3 の算術は b で数え直す: P_data = 4、`concurrency` 32 → b = 8、下限 = 4 × (16 + 16) + 16 = 144 ≤ 300 (使い捨てクラスタ)。**D-5 の N=4 の計測はこの改定の後に行う** (改定前は 528 で起動時に落ちる = 起草の指摘のとおり)。MitateDB の application ごとの永続接続 (× N) は role の `CONNECTION LIMIT` (application role 68、並走 2 前提) の中で N ≤ 4 まで収まるかを作業指示書で数える。
4. **control plane は workers を足さない (疑義 7)。** `--workers` は data plane だけ。P_control は宣言のまま (既定 1)。分割の仕組みは class 一般に書き、control の 2 class は P_control = 1 なら b = L で現行と同じ値になる。MitateDB の Dockerfile CMD (data / control が 1 行を共有) は SERVICE ごとの workers 変数にする (control は 1 固定)。`control_main` の startup 副作用の列挙は不要 (process 数を変えない)。
5. **窓の形の事実 (疑義 8)。** control / audit の窓は現物では sliding であり、分割は窓の形を変えない (上限値だけが b になる)。fixed への変更の可否 (Q-2) は `requests_per_minute` (PG の行) にだけ掛かる。
6. **事実の訂正 (疑義 8)。** R-80 の MitateDB は platform 4 tx/req (`RM`:500。枠の「5 tx」は誤り)。runbook の Invariant 1 は `MitateDB-api/docs/cloud-run-cloud-sql.md`:1327 から。MitateDB の次の platform 単発 migration は `0016`、r2db は `0015` (本文のとおり)。
7. **新条件の番号 (疑義 3)。** 本書では「新条件」と呼び、番号は conformance WP で採番する (`tools/check_doc_refs.py` が未存在の C-NN を参照切れとして止めるため)。
8. **新条件 (a) の保持の手段 (疑義 4、§9 (f)) は設計レビューに問う。** 監督の前提: 本番の composition root に test 用の stall フックを足さない。候補は (i) 本番の要求だけで in-flight を作る (`execution_ms` 内で時間の掛かる `query` を L + P 本同時に送り、`concurrency` の LIMIT_EXCEEDED を少なくとも 1 件観測する) と (ii) 共通条件では `requests_per_minute` の process 間の bound (新条件 (b)) だけを観測し、`concurrency` の分割は peer-local の実 PG テスト (2 worker を起動して b で拒否) で pin する。裁定はレビュー後。
9. **`build_app()` の例外が子 process の `STARTUP_FAILURE` になる経路 (未確認)。** 作業指示書の実装 WP で現物 (uvicorn `supervisors/multiprocess.py`) を読んで確かめ、結果を D-2 に【追記】する。設計は「子の起動失敗は supervisor が全体を止める」を前提にしない (F-15 の fail-fast が 1 process のときと同じ観測可能性で残ることを要求する)。

