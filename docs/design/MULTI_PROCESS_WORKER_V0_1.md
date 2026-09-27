# multi-process worker と in-memory の limit 状態の置き場 設計文書（v0.4）

## 0. 版数・位置づけ

- 状態: **v0.5 (2026-09-28): 依頼者裁定 Q-1 (A')・Q-3 = 1・Q-4 = (B)・Q-5 = 行う を §5 に逐語記録、設計レビュー 1 回目 + 再確認 3 回 (旧 13 / 新 8 / 新 A〜F) を裁定 1〜42 で反映。作業指示書の起草に進める。** 起草 (v0.1) + 監督裁定 1〜9 (v0.2) + 設計レビュー 1 回目への監督裁定 10〜22 (v0.3、§10) + 同レビューの再確認 (新 1〜8) への監督裁定 26〜33 (v0.4、§10.4)。§5 の Q-1・Q-3・Q-4・Q-5 は依頼者判断待ち。Q-2 は監督裁定 15 で閉じた。** 着手条件は設計レビュー 1 回 (1 回目は済み) と、裁定 10〜22 の反映の再確認 (同じレビュー担当。済み、新 1〜8 は裁定 26〜33 で反映) である (§10 の裁定 22)。v0.2 の「(A)(C) なら 2 回」は、裁定 1 が裁定 10 で覆ったので失効した。
- 台帳: 計画文書 `RM` §8 の **R-113** (規模 L)。R-101 の是正の 2 段目 (`RM`:521、:533)。
- 基点: main `443a79a`。本書の file:line はこの木の現物である (uvicorn は開発機の venv の 0.52.4。両 peer の `pyproject.toml` は `uvicorn>=0.30`、`r2db-api/pyproject.toml`:33、`MitateDB-api/pyproject.toml`:30)。v0.3 で足した事実 (§1.4) と v0.4 で足した事実 (§1.4 の (6)) も同じ木で確かめた。
- 契約: **1.11.0 不変** (§10 の裁定 10・13)。v0.2 の「Q-1 が (A)(C) なら 1.12.0」は裁定 10 で覆した。
- クラス: **Class D** (§10 の裁定 22。§3 D-6)。
- 改版: v0.1 (2026-09-28) 起草 (drafter)。v0.2 (2026-09-28) 監督裁定 1〜9 を §10 に追記 (起草の疑義への裁定。本文は書き換えず、§10 が優先する)。v0.3 (2026-09-28) 設計レビュー 1 回目 (13 件とクラスの引き上げ) への監督裁定 10〜22 と Q-1 の書き換えを §10 に逐語で追記し、本文 (§0、§1.2〜§1.4、D-1〜D-7、§4〜§9) を裁定に合わせて書き換えた。覆した判定は行を残し、覆した裁定の番号と日付を添えた (`OPERATING_CONDITIONS.md` §1.8 の 56)。v0.4 (2026-09-28) 設計レビュー 1 回目の再確認 (新 1〜8) への監督裁定 26〜33 を §10.4 に逐語で追記し、覆された旧裁定 (11 の事前検査の手段、17 の計測時 64、18 の `concurrency` の写像、24) の末尾に覆した裁定の番号を添えた。本文 (§0、D-1〜D-5、§4、§6、§7、§9) を裁定に合わせて書き換えた (事前検査を one-shot の `--preflight` entry に、`concurrency` の写像に workers の条件、slot の扱いの決定、rate 行を int[60] に、計測は既定 32)。
- 出所の記法は `docs/work-orders/OPERATING_CONDITIONS.md` §0。キーの無いファイルは経路で書く。
- 公開規律: 実 DSN・実ホスト名・作業機の絶対パスを置かない (`OPERATING_CONDITIONS.md` §1.9)。
- 本書の D-N / Q-N / WP-N は本書ローカルの ID である。他文書の同形 ID には文書名を添える (§1.8 の 59)。新しい共通条件は番号を確定する WP まで「新条件」と呼ぶ (§3 D-4)。台帳に新しく起こす行は番号を確定するまで「(次番)」と呼ぶ (§8)。

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
| 契約 | `spec/data-service-api.v1.json`:279-284 (enforcement_enum)、:303 (1.8.0 の無条件義務)、:905 (`limits.profile`)、:925 (`audit_requests_per_minute_note` の "pre-authentication fixed window"。§8 の起票文案)。`process_ceilings` は契約に無い (`spec/CCR_DISPOSITION.md`:233) |
| 不変条件 | `security/SECURITY_INVARIANTS_V1.md`:226-250 (SI-08。"Implementation freedom" は :242-243) |
| 現行の制御主張 | `security/CONTROL_MAPPING.md`:710 (r2db の宣言行)、:711-712 (r2db の写像と in-memory の class)、:903 (MitateDB の宣言行)、:904 (MitateDB の写像)、:962 (R-52 と下限)、:985-988 (開示された限界。C-26 は 1 process、:988) |
| uvicorn の supervisor | `uvicorn/supervisors/multiprocess.py`:214-240 (子の監視と置き換え)、:267-272 (SIGTTIN で 1 本増やす)、`uvicorn/main.py`:603-607 (import string の要求)、:628-629 (`STARTUP_FAILURE` での終了は workers == 1 のときだけ) |

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
- 死んだ・応答しない子は kill の後に置き換える (kill が先、`uvicorn/supervisors/multiprocess.py`:214-240)。子が起動前に失敗 (`STARTUP_FAILURE`) すると親ごと止まる (同 :225-230)。 **【訂正 v0.3、2026-09-28 (裁定 11)】** 親ごと止まるのは子の終了コードが `STARTUP_FAILURE` (3) のときだけである。`build_app()` の例外は子の終了コード 1 になり、supervisor はそれを「死んだ子」として置き換え続ける (同 :218-239)。supervisor が止まっても、親の終了コードは 0 である (`uvicorn/main.py`:628-629 の `sys.exit(STARTUP_FAILURE)` は workers == 1 のときだけ)。
- SIGHUP の `restart_all` は子を 1 本ずつ「新を ready にしてから旧を止める」(同 :173-194)。この間だけ子は N+1 本になる。
- `--workers` を渡さないとき `WEB_CONCURRENCY` を読む (`uvicorn/config.py`:352-353)。
- `--fd` は単一 process と multi-process で同じ `socket.fromfd` を通る (`uvicorn/config.py`:568-569、`uvicorn/server.py`:149-151)。
- 応答しない子は healthcheck の timeout の後に SIGKILL で止めて置き換える (`uvicorn/supervisors/multiprocess.py`:218-223)。SIGTTIN を受けた supervisor は稼働中に子を 1 本増やす (同 :267-272)。

### 1.4 v0.3 で確かめた事実

**(1) r2db の pool の寸法とフェーズ10 WP-8a レビュー F-1 (裁定 16 の前提)**

- `r2db-api/src/r2db_api/limits.py`:121-165 の `role_pool_size` は `limits.concurrency` を返す。application の role pool (runtime / developer) の寸法 (`r2db-api/src/r2db_api/main.py`:466) と platform pool の既定 (同 :492。credential store :493 と durable audit sink :502 が同じ値の pool を別々に持つ) はこの関数から来る。MitateDB の platform pool も同型である (`MitateDB-api/src/mitatedb_api/config.py`:300-319、`main.py`:345-348)。
- F-1 の理由 (`limits.py`:128-142 の docstring、逐語):

```text

    Before WP-8a's `run_in_threadpool` delegation, a single event-loop
    thread serialized every request's synchronous section, so one
    application could never actually present more than 1 concurrent
    request to its own pool regardless of how small that pool was
    (WP-4b ruling 3). Once delegation let concurrent requests reach the
    pool for real, a pool sized below the declared `concurrency` ceiling
    (previously: whatever `SharedPoolManager`'s own fixed default worked
    out to -- `R2DB_POOL_SIZE + R2DB_POOL_MAX_OVERFLOW`, default 2 + 2 =
    4, entirely disconnected from `ResourceLimits.concurrency`, default
    32) opened a NEW failure mode: the 5th concurrent request against ONE
    application, still comfortably under the declared bound, timed out in
    `_RolePool.connection()` (`postgres.py`'s own `_DEFAULT_ACQUIRE_
    TIMEOUT_S`) and failed closed with 503 SERVICE_UNAVAILABLE instead of
    the declared 429 LIMIT_EXCEEDED a client is told to expect at 32. This
```

- F-1 が書かれた時点 (フェーズ10 WP-8a) では、同時に pool を借りられる要求の数を抑えるのは anyio の既定の thread limiter (40、`r2db-api/src/r2db_api/http.py`:469-472 のコメント) であり、`concurrency` 32 より大きかった。R-101 WP-3 以降は `create_app` の `ThreadLimitMiddleware` が event loop ごとの thread limiter を `DEFAULT_THREAD_LIMIT` (4) に絞る (r2db `http.py`:286、:289-316。MitateDB `MitateDB-api/src/mitatedb_api/http.py`:252、:255-。env 上書きは `R2DB_THREAD_LIMIT` / `MITATEDB_THREAD_LIMIT`、r2db `main.py`:284-301、MitateDB `main.py`:209-226)。
- 判定: F-1 の理由 (同時に pool を借りる要求が pool の寸法を超えると、宣言値の手前で 503 になる) は今も成り立つ。ただし「同時に pool を借りる要求の数」の上限は、今は `concurrency` ではなく **実効の thread limit** (と thread limiter の外で pool を借りる thread の数) である。よって裁定 16 の「pool の最大 = thread limit + 定数」は F-1 の理由を満たす。条件は 2 つある: (a) pool の寸法は定数 4 ではなく、env で上書きされた後の実効 thread limit から導く (上書きで thread limit だけを上げると F-1 の形が戻る)。(b) 1 つの同期区間が同じ pool から同時に 2 本借りない (未確認。§9 (q))。この 2 条件の下で代案 (pool = max(…) 等) は要らないと判断した。
- F-1 の docstring の「pool を増やしたい運用者は `concurrency` を上げる」(`limits.py`:153-157) は、裁定 16 の後は当てはまらない (docstring の改訂は WP-2)。

**(2) event loop 側 (threadpool の外) の DB 使用 (裁定 16 の前提)**

- r2db: data plane の全 handler (`http.py`:489-744) は、`acquire_concurrency_slot()` (process 内のカウンタ) だけを event loop で取り、`_authenticate` と `DataService` の呼び出しを `run_in_threadpool` で実行する (同 :423-440 のコメント、:494、:527、:550 ほか)。event loop で走る残りは body の読み取り (`_read_json_object`) と middleware (byte bound、request id、thread limit) で、DB に触れない。
- MitateDB: 同じ形 (`MitateDB-api/src/mitatedb_api/http.py`:552 のコメント、:639-1272 の handler。DB を使う `_authenticate` と session の呼び出しは `run_in_threadpool` の中)。
- thread limiter の外で DB を使うのは両 peer とも次の 2 つだけである: (i) lifespan の audit flush thread (r2db `main.py`:657、MitateDB `main.py`:587。1 本の daemon thread)、(ii) lifespan の終了時の最終 flush (r2db `main.py`:677、MitateDB `main.py`:606。event loop 上で走るが、要求の serve が終わった後)。要求の処理中に event loop で DB を使う箇所は見つからなかった (handler と例外 handler、r2db `http.py`:361-381、MitateDB `http.py`:555-580 を読んだ)。
- 推測: Starlette の他の `run_in_threadpool` の利用者 (同期 endpoint、file 応答) は両 peer に無いので、thread limiter の token はすべて要求の同期区間に使われる。

**(3) r2db の `concurrency` の宣言値を env で変える入口**

- r2db には無い。`r2db-api/src/r2db_api/ops.py`:1183-1187 の docstring が「`ResourceLimits.concurrency` is fixed on this peer -- no env var overrides it anywhere in this peer's own composition roots」と明記し、`main.py`:465 は `ResourceLimits()` を引数なしで作る。
- MitateDB には在る (`MITATEDB_MAX_CONCURRENCY`、`MitateDB-api/src/mitatedb_api/main.py`:345、`config.py`:205)。
- 裁定 17 (計測時 64) の与え方は §7.2 に両論で置く。 **【v0.4、2026-09-28】裁定 31 で不要 (計測は本番既定の 32。r2db に env の入口を足さない)。**

**(4) `fcntl.flock` の挙動 (裁定 10 の前提)**

- Python の `fcntl.flock` の docstring は「See the Unix manual page for flock(2) for details (On some systems, this function is emulated using fcntl())」である。開発機の Python 3.11 は `sysconfig.get_config_var("HAVE_FLOCK")` = 1 (flock(2) を直接呼ぶ。fcntl() での模倣ではない)。本番 (Linux / container) の値は未確認。
- `LOCK_NB`: darwin の flock(2) の man は「If LOCK_NB is included in operation, then this will not happen; instead the call will fail and the error EWOULDBLOCK will be returned」。Python の `fcntl.lockf` の docstring は、`LOCK_NB` で取れないときの `OSError` の errno を「EACCES or EAGAIN (depending on the operating system -- for portability, check for either value)」とする。
- fork / dup: darwin の flock(2) の man は「Locks are on files, not file descriptors. That is, file descriptors duplicated through dup(2) or fork(2) do not result in multiple instances of a lock, but rather multiple references to a single lock」。
- close での解放と process の死での解放: 推測。手元の darwin の man に close 時の解放の記述は無い。flock の lock は open file に付き、その open file を指す fd がすべて閉じたとき (process の終了で fd が閉じるときを含む) に外れる、というのが一般の記述である (Linux の flock(2) の man は手元で未確認)。
- fd の継承: 開発機の Python 3.11 では `os.open` の fd は既定で継承不可 (`os.get_inheritable` が False。Python 3.4 以降の既定)。`multiprocessing` の spawn 文脈は明示した fd だけを子に渡す (標準ライブラリ `multiprocessing/popen_spawn_posix.py`:38-72 の `_launch`、:58 の `util.spawnv_passfds`)。uvicorn の supervisor は app を読み込まない (§1.3) ので、slot の fd を持たないまま子を起こす。
- 同じ process 内の別 thread が同じ slot ファイルを別々に open して `LOCK_EX | LOCK_NB` を掛けたとき、2 本目が拒まれること: 推測 (open file が別なので拒まれる)。確かめる点として §9 (k) に置く。 **【v0.4、2026-09-28】** 推測のまま残るが、配備先ごとの成否は起動時の自己検査 (裁定 28、D-3 (2)) が確かめ、拒まれなければ起動を失敗させる。本番の `HAVE_FLOCK` の未確認も同じ検査が覆う。

**(5) 配備物の現物**

- r2db の unit: `EnvironmentFile=` (`r2db-api/deploy/systemd/r2dbsvc-api.service`:53)、`ExecStart=` (:60、`--workers` 無し)、`Restart=on-failure` (:68)、`ProtectSystem=strict` (:82)、`PrivateTmp=true` (:109)、`UMask=0077` (:126)、`SystemCallFilter=@system-service` (:141)。`ExecStartPre=` と `RuntimeDirectory=` は無い。
- MitateDB の container: `USER mitatedb` (`MitateDB-api/docker/Dockerfile`:134)、`CMD` (:145)。
- 両 peer とも PostgreSQL の接続に `application_name` を設定していない (`application_name` は両 peer の `ops.py` の libpq 環境変数の対応表 `r2db-api/src/r2db_api/ops.py`:1349、`MitateDB-api/src/mitatedb_api/ops.py`:579 にだけ現れる)。

**(6) v0.4 で確かめた事実 (設計レビュー 1 回目の再確認の出所。同じ木)**

- `ops verify-declarations` は provision の DSN で走る: `r2db-api/src/r2db_api/ops.py`:986 (「run OUT OF BAND against the provision DSN」)。env の名は r2db `R2DB_CONTROL_DSN` (`r2db-api/src/r2db_api/platform_declarations.py`:105)、MitateDB `MITATEDB_PROVISION_DSN` (`MitateDB-api/src/mitatedb_api/platform_declarations.py`:94)。MitateDB の runbook はこの secret を「operator/break-glass CLI only -- never a Cloud Run service」と定める (`MitateDB-api/docs/cloud-run-cloud-sql.md`:1079)。
- 両 peer の `main.py` に `if __name__ == "__main__"` の entry は無い (r2db `build_app` :349、module 末尾 `app = build_app()` :698。MitateDB :268、:639)。
- r2db の unit は `SystemCallFilter=@system-service` と `SystemCallErrorNumber=EPERM` を持つ (`r2db-api/deploy/systemd/r2dbsvc-api.service`:141-142)。filter に弾かれた syscall は EPERM を返す。
- `concurrency` の slot の `with` は応答を作る前に抜ける: r2db `post_query` (`r2db-api/src/r2db_api/http.py`:524-557、`with service.acquire_concurrency_slot()` の後に `return JSONResponse`)、MitateDB (`MitateDB-api/src/mitatedb_api/http.py`:645-656)。
- MitateDB の http plug の `isolated_application_surface` は `concurrency` 3 を宣言する (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:2071)。同じ slot directory を session の adapter と共有すると宣言値の手前で 429 になる経路である。
- plug の登録 (`conformance-tests/registry.json`): in-process (`r2db-api`、`MitateDB-api`、in-memory の cell)、http (`r2db-api-http`、`MitateDB-api-http`、`httpx.ASGITransport` で PostgreSQL)、socket (`r2db-api-socket`、`MitateDB-api-socket`、実 socket + nginx + PostgreSQL)、composition root の launcher (`real_server_r2db`、`real_server_mitatedb`)。

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

## 3. 決定 (監督案と監督裁定。依頼者裁定の対象は §5)

### D-1 worker の形 = uvicorn の `--workers N`

```text
D-1 **worker の形 = uvicorn の `--workers N`** (uvicorn 0.52 の multiprocess supervisor。app は既に import string `main:app`)。r2db は systemd unit の ExecStart に `--workers` を足す。MitateDB は Dockerfile CMD に `--workers` を足し、Cloud Run では process 数 = instances × workers を `process_ceilings` に宣言する (Invariant 1 の一般化は D-5 (iii) で済んでいる)。N は env (`R2DB_WORKERS` / `MITATEDB_WORKERS`)。既定は 1 (現行の配備を変えない)。計測は N=4 (thread limiter 4 × 4 process、開発機 10 core)。
  根拠: 既存の起動形 (import string) をそのまま使え、supervisor が別途要らない。gunicorn は依存を増やす。OS レベルの N unit は nginx 側の upstream 変更を要し peer ごとに形が違う。
```

- **【v0.3 改定、2026-09-28 (裁定 4・10・11・20)】**
  - **宣言の検査は worker を起こす前に親の側で 1 回走らせる** (裁定 11)。r2db は unit の `ExecStartPre=` で `ops verify-declarations` (F-15 は exit 14) を走らせる。MitateDB は Dockerfile の `CMD` で `exec uvicorn` の前に同じ CLI を置く。理由: uvicorn の supervisor は `build_app()` の例外で終わった子を置き換え続け、親は 0 で終わる (§1.3 の訂正)。fail-fast を観測できるのは親側の事前検査である。 **【v0.4、2026-09-28】手段 (`ops verify-declarations`) は裁定 26 で覆す (provision の DSN を data plane に置くことになる。下の v0.4 改定)。事前検査を親側で走らせること自体は残る。**
  - `verify-declarations` に「`--workers` の値 (env `R2DB_WORKERS` / `MITATEDB_WORKERS`) ≤ `process_ceilings.<plane>`」の検査を足す (裁定 11)。 **【v0.4、2026-09-28】起動を止める検査としては裁定 27 で `build_app()` の中に移す。`verify-declarations` への追加は運用者の手動検査として残す (裁定 26)。**
  - `--workers` は 1 のときも常に明示し、env に必須で置く。`WEB_CONCURRENCY` の入口 (`uvicorn/config.py`:352-353) はこれで閉じる (裁定 11)。
  - SIGTTIN による増員 (§1.3) は runbook で禁じる (裁定 11。§9 (c))。
  - control plane には workers を足さない (裁定 4)。MitateDB の `CMD` は data / control が 1 行を共有するので、SERVICE ごとの workers 変数にする (control は 1 固定)。
  - Cloud Run は `--max-instances=1` のまま `--workers` と `--cpu` で伸ばす (裁定 10 の射程「base URL を serve する process は 1 host に置く」。Q-4 の監督案、裁定 20)。上の枠の「Cloud Run では process 数 = instances × workers を `process_ceilings` に宣言する」は、instances ≥ 2 (複数 host) を含む限り裁定 10 で本件の範囲外になった (Q-4 は依頼者判断のまま)。
- **【v0.4 改定、2026-09-28 (裁定 26・27)】**
  - **事前検査 = service 自身の env と DSN で `build_app()` を 1 回実行して捨てる one-shot** (裁定 26)。両 peer の composition root に entry を足す: `python -m r2db_api.main --preflight` / `python -m mitatedb_api.main --preflight`。entry は `build_app()` を呼び、開いた cell を閉じて 0 で終わる。例外は非 0 で終わる。
  - 置き場: r2db は unit の `ExecStartPre=` (preflight) の後に `ExecStart=` (uvicorn)。MitateDB は `CMD` の `exec uvicorn` の前に preflight を置く (SERVICE = data の枝)。
  - 観測できるもの: 起動時の検査の全部 (F-13 / F-15 / F-16 / F-18 / registry / pepper、`build_app()` 内の workers ≤ ceiling の検査 (裁定 27)、slot の自己検査 (裁定 28)) が、子と同じ経路・同じ権限で非 0 終了として現れる。provision の DSN は data plane の unit / container に置かない (§1.4 の (6))。
  - **workers ≤ ceiling の検査は `build_app()` の中に置く** (裁定 27)。env `R2DB_WORKERS` / `MITATEDB_WORKERS` の値が `process_ceilings.data` を超えれば起動失敗。preflight と各子の両方で走る。`verify-declarations` への同じ検査の追加は運用者の手動検査として残す (裁定 26)。
  - `--workers` は 1 のときも常に明示し、env に必須で置く (裁定 11、変わらない)。
- 変える行: r2db `r2db-api/deploy/systemd/r2dbsvc-api.service`:60 の `ExecStart` (`--workers` を足す) と、新しい `ExecStartPre=` の行 (**【v0.4】** 中身は preflight の entry。裁定 26)。MitateDB `MitateDB-api/docker/Dockerfile`:145 の `CMD` (事前検査と SERVICE ごとの workers。**【v0.4】** 事前検査は preflight の entry)。両 peer の `main.py` (preflight の entry。§1.4 の (6) のとおり現行は entry が無い)。
- 待受は supervisor の 1 socket を子が共有する (§1.3)。nginx の upstream は 1 本のまま。
- 根拠 (補足): 子が死んでも supervisor が置き換える (§1.3)。子の起動失敗は親ごと止まるので、F-15 等の fail-fast は配備全体の起動失敗として現れる (推測: `build_app()` の例外が子の `STARTUP_FAILURE` になる経路は現物で未確認)。**【訂正 v0.3、2026-09-28 (裁定 11)】** 親ごとは止まらない (§1.3 の訂正)。fail-fast は上の事前検査が担う。
- **壊すとどう見えるか**: `--workers` を外すと N=1 に戻り、§7 の D-16 が 15.7 / 18.7 倍 (§1.1) に戻って不成立。import string でない app に `--workers` を渡すと uvicorn が起動を拒む (`uvicorn/main.py`:603-607)。事前検査を外すと、宣言の欠けた配備で子の置き換えが繰り返され、supervisor は止まっても 0 で終わる。C-26 (5) の workers ≥ 2 の起動形 (§3 D-4) が赤になる。 **【v0.4】** preflight の entry が例外を 0 で握りつぶすと同じく C-26 (5) が赤。workers ≤ ceiling の検査を `build_app()` から外すと、workers > ceiling の起動が通り、宣言より多い process が serve して接続予算 (F-16 / F-18、宣言の ceiling で数える) を少なく見積もる。

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
| 10 | (経路) supervisor が子を SIGKILL したとき | uvicorn `supervisors/multiprocess.py`:218-223。最終 flush は :661-681 | 失うもの | lifespan の最終 flush が走らず、audit buffer と開いている denial 窓が失われる。1 process には無い経路である。起こりにくさは両論: pong thread は GIL の下でも通常は応答する / 長い C 呼び出しで GIL を握る要求があれば起こりうる (裁定 21) |
| 11 | **【v0.4】** workers ≤ ceiling の検査 (裁定 27) | 新規 (`build_app()` 内、#3 の宣言の読み取りの後) | env と #3 の値の比較 | 外部状態を書かない |
| 12 | **【v0.4】** slot directory の検査と自己検査 (裁定 27・28) | 新規 (`build_app()` 内) | directory の stat と、slot directory 内のファイル 1 つの open 2 回・flock・close | directory は作らない (配備側が作る)。ファイルは `O_CREAT` で作りうるが中身を持たず、lock は検査の間だけで close で外れる。検査の間は 1 本の lock を瞬間的に握る (どのファイルを使うかは §9 (r)) |
| 13 | **【v0.4】** (経路) preflight の one-shot (裁定 26) | 新しい entry `python -m r2db_api.main --preflight` | #1〜#8、#11、#12 を 1 回余分に走らせ、開いた cell を閉じて終わる | 下の「preflight が 1 回余分に走ること」 |

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
| 11 | (経路) supervisor が子を SIGKILL したとき | uvicorn `supervisors/multiprocess.py`:218-223。最終 flush は :571-621 (:606) | 失うもの | r2db の #10 と同じ (裁定 21) |
| 12 | **【v0.4】** workers ≤ ceiling の検査 (裁定 27) | 新規 (`build_app()` 内、#6 の宣言の読み取りの後) | env と #6 の値の比較 | 外部状態を書かない |
| 13 | **【v0.4】** slot directory の検査と自己検査 (裁定 27・28) | 新規 (`build_app()` 内) | r2db の #12 と同じ | r2db の #12 と同じ |
| 14 | **【v0.4】** (経路) preflight の one-shot (裁定 26) | 新しい entry `python -m mitatedb_api.main --preflight` | #1〜#9、#12、#13 を 1 回余分に走らせ、開いた backend / cell を閉じて終わる | 下の「preflight が 1 回余分に走ること」 |

- 両 peer とも migration は `ops` CLI が打ち、`main.py` は打たない。
- 量が N 倍になるもの (安全帰結は変わらない): audit buffer の容量 (`service.py`:162、`MitateDB-api/src/mitatedb_api/audit_dispatch.py`:141 が「per-process, not per-deployment」と明記)、denial coalescer の行 (`service.py`:414 が「one row per process/instance」を正常とする)、thread limiter (`http.py`:286-321 r2db、:252- MitateDB) は process ごとに 4。
- **壊すとどう見えるか**: startup に共有状態への書き込みを足すと N 回走る (本表に「書く」行が現れる)。F-15 の行を消すと各子が起動に失敗し、supervisor ごと止まる (§1.3)。 **【訂正 v0.3、2026-09-28 (裁定 11)】** supervisor ごとは止まらない。各子の起動失敗と置き換えが繰り返され、止めるのは親側の事前検査 (D-1) である。
- **【追記 v0.3、2026-09-28 (裁定 9・11)】** 裁定 9 の「`build_app()` の例外が子の `STARTUP_FAILURE` になる経路」は設計レビュー 1 回目の指摘 1 で現物を確かめた。`build_app()` の例外は子の終了コード 1 になる。supervisor は 3 以外の終了を「死んだ子」として 0.5 秒周期で置き換え続ける (`uvicorn/supervisors/multiprocess.py`:218-239)。親は `uvicorn/main.py`:628-629 の `sys.exit(STARTUP_FAILURE)` が workers == 1 のときだけなので、0 で終わる。よって「子の起動失敗は supervisor が全体を止める」は成り立たない。fail-fast の観測可能性は D-1 の事前検査が担う。
- **【追記 v0.4、2026-09-28 (裁定 26)】preflight が 1 回余分に走ること。** preflight は上の表の startup の副作用を、子 N 本の前に 1 回だけ余分に走らせる (合計 N + 1 回)。副作用が無い根拠は表のとおりである: DB への作用は読み取りだけ、他は process 内資源 (pool・cell・`DataService`・in-memory の登録) で、preflight の process の終了とともに消える。lifespan は serve しないと走らないので、audit flush thread (r2db #9、MitateDB #10) は preflight では起きない。F-12 の log 1 行は preflight の分だけ 1 行増える。preflight は子の起動の前に終わる (`ExecStartPre=` は `ExecStart=` の前に完了し、`CMD` は逐次) ので、その pool は子の pool と同時には接続予算 (D-3 (5)) に加わらない。slot の自己検査 (r2db #12、MitateDB #13) は lock を検査の間だけ握る。cell の eager open と close が DB 側に残すもの (session の開閉の記録、MitateDB の永続接続の短い 1 組) は §9 (r) で確かめる。
- **壊すとどう見えるか (v0.4)**: preflight の entry が DB に書く処理を呼ぶと、本表に「書く」行が現れ、N + 1 回走る。preflight が cell を閉じずに終わっても、接続は process の終了で切れるので外からは見えにくい (「cell を閉じて 0 で終わる」は裁定 26 の entry の仕様であり、その完了条件と変異は作業指示書で置く)。

### D-3 区分 (ii) の置き場

**v0.2 の枠 (逐語。2026-09-28 に裁定 10・15・16・18 で覆した。行は残す)**

```text
D-3 **区分 (ii) の置き場 = class ごとに 2 分する (両 peer 同型)**:
  - post-auth で credential 単位の `requests_per_minute` → **PostgreSQL の共有状態** (platform DB の 1 表、credential ごとの fixed window 行を `UPDATE ... RETURNING` で原子的に数える)。= R-18 (c)。1 要求 1 往復を足す (R-80 の実測では r2db 8 tx/req、MitateDB 5 tx/req に対する +1)。sliding → fixed window は宣言の意味 (1 分あたり) を変えない: 文書に明記。
  - pre-auth の `concurrency`、`control_requests_per_minute`、`audit_requests_per_minute` → **静的分割** (process ごとの bound = 宣言値 ÷ `process_ceilings` の該当 plane の値、切り捨て、最小 1)。合計が宣言値を超えないので 1.8.0 の意味で `enforced` が真。crash 安全 (process が死ねば slot も消える)。DB 往復なし (条件 5)。
  - 写像: 区分 (ii) は ceiling に依らず `enforced`。`deployment_required` はどちらの peer も宣言しなくなる (enum の値は契約に残る)。
  根拠: 共有 counter を PG に置くと concurrency の slot は process が死んだとき漏れる (session 束縛の advisory lock で N slot を表すのは O(limit) 往復)。分割は crash 安全でゼロ往復だが利用率を落とす (負荷が偏ると宣言値の 1/N で拒否)。rate window は時間で自然に回収されるので PG に置ける。post-auth の class だけを DB に置けば未認証要求の増幅が無い。
```

**D-3 (v0.3、裁定 10・15・16・18 と裁定 4。v0.4 で裁定 27〜30 を反映)**

| class | plane | 置き場 | 仕組み | 写像 | 裁定 |
|---|---|---|---|---|---|
| `requests_per_minute` | data (認証の後) | PostgreSQL の platform 表 | credential ごとの 1 行に sliding window の時刻の配列を持ち、1 文で数える (**【v0.4】裁定 30 で覆す: 秒単位の 60 個の計数の配列 + 基点の秒**) | PG の行が配線されていれば ceiling に依らず `enforced` (裁定 27 で確認、変わらない) | 15、18、27、30 |
| `concurrency` | data (認証の前) | host 内で共有する OS の file lock | 宣言値 L 本の slot ファイルを `fcntl.flock` で握る (**【v0.4】** directory は env で明示、ファイルの扱いは (2)。裁定 27〜29) | slot directory が配線されていれば ceiling に依らず `enforced` (**【v0.4】裁定 27 で覆す: 配線 かつ `process_ceilings.data` ≤ workers のときだけ `enforced`、他は `deployment_required`**) | 10、18、27〜29 |
| `control_requests_per_minute`・`audit_requests_per_minute` | control (認証の前) | 現行のまま (process 内の sliding window) | 現行のまま。control plane は 1 process (workers を足さない) | 現行のまま (ceiling 1 → `enforced`) | 4、10 |

接続予算は thread limit で数え、宣言値 L に比例させない (裁定 16。(5))。

**(1) `requests_per_minute` = PostgreSQL の sliding window の行 (裁定 15)**

- 行の形: 1 credential 1 行 (`credential_id`, `stamps timestamptz[]`)。 **【v0.4、2026-09-28】裁定 30 で覆す (下の v0.4 の行の形)。**
- 数え方 (1 文): `INSERT … ON CONFLICT (credential_id) DO UPDATE SET stamps = (期限切れを落とした配列 || clock_timestamp()) WHERE cardinality(期限切れを落とした配列) < L RETURNING …`。行が返らなければ `LIMIT_EXCEEDED` (`limit_class` = `requests_per_minute`、現行と同じ details)。配列の上限は L (既定 600、`r2db-api/src/r2db_api/limits.py`:18)。 **【v0.4、2026-09-28】裁定 30 で覆す (配列は固定長 60、下の 1 文の骨子)。**
- 窓は DB の時計 (`clock_timestamp()`) で決める。process ごとの時計のずれは窓に入らない。fixed window の境目の flake (C-05 V2、新条件 (b)) と境目での 2L の突発は起きない。 **【v0.4、v0.5 で 61 個】** int[61] でも窓は DB の時計の秒で決まる。境目の 1 秒は多めに数える (裁定 30。数え方の正しさは §9 (s))。
- **【v0.4、2026-09-28 (裁定 30)】行の形 = 秒単位の 61 個の計数の配列 + 基点の秒 (v0.4 の 60 個は裁定 34 で 61 個に改めた)。** 1 credential 1 行 (`credential_id`、基点の秒 `base_s` (bigint)、`counts int[61]`)。約 244 B で TOAST にならない。配列は固定長なので 1 文の費用が L (既定 600) に依らない。境目の 1 秒を多めに数えるので上限を超えて通すことが無く、60 s 未満の drive (C-05 V2) では拒否位置が変わらない。
- **1 文の骨子 (v0.4)**。`<…>` は作業指示書で具体化する部分である。秒の位置の決め方 (秒 mod 61 の環か、基点から詰め直すか) も作業指示書で固定する。基点の進め方は裁定 37 のとおり単調 (戻さない)。

```sql
-- v0.5 (裁定 37): 基点は単調に進め (GREATEST)、進める幅は max(0, s - base_s)、61 以上なら全部 0。
WITH t AS (SELECT floor(extract(epoch FROM clock_timestamp()))::bigint AS s)
INSERT INTO <platform の rate 表> (credential_id, base_s, counts)
SELECT $credential_id, t.s, <長さ 61 の 0 の配列の t.s の位置を 1 にしたもの> FROM t
ON CONFLICT (credential_id) DO UPDATE
   SET base_s = GREATEST(<現在の base_s>, EXCLUDED.base_s),
       counts = <既存の counts を shift = LEAST(61, GREATEST(0, EXCLUDED.base_s - 現在の base_s)) だけ進めた配列 (過ぎた秒の位置を 0 に落とす。shift = 61 なら全部 0)> の
                GREATEST(現在の base_s, EXCLUDED.base_s) の位置に +1
 WHERE <進めた配列の合計> < $L
RETURNING 1;
```

- 行が返らなければ `LIMIT_EXCEEDED` (`limit_class` = `requests_per_minute`、現行と同じ details)。`clock_timestamp()` は文の中で 1 回だけ読む (CTE の `t.s`)。接続・失敗時・回収・数える位置・migration の番号は下の v0.3 の行のまま。
- 借りる順序 (裁定 33): rate の文は、認証で借りた接続を返した後に借りる。借りたまま 2 本目を借りない (F-1 の条件 (ii)、裁定 25。作業指示書の完了条件に置く)。
- 費用の上限: 計測の前に 1 文の p50 / p95 を小実験で取る。0.2 ms/文を超えれば監督に上げる (裁定 30。§7.3)。
- 窓の形は現行 (sliding 60 s、§1.3 の表) を保つ。Q-2 は裁定 15 で閉じた (§5)。
- 接続: 既存の api role の pool (r2db は credentials pool、MitateDB は platform pool) の autocommit 1 文。要求の tx に入れない (行 lock を要求の終わりまで持たない)。application role に platform 表の権限を足さない。api role には新表の INSERT / UPDATE (と SELECT) だけを与える。計数用の pool を新設しない (F-16 の需要を増やさない)。
- 失敗時: fail-closed。DB の失敗は既存の DB 失敗と同じ写像で拒否し、素通ししない。
- 回収: revoke 済み credential の行は credential の削除に連動する (FK `ON DELETE CASCADE`)。1 credential 1 行なので増えない。
- 数える位置は現行と同じ認証の後 (r2db `service.py`:1041、MitateDB `cell.py`:710)。未認証の要求はこの表に触れない (条件 5)。
- 表は platform schema に置き、追加は platform 単発 migration とする。番号は現物の次番: **r2db `0015`** (`r2db-api/migrations/` の最後は `0014_auditreader_statement_timeout.sql`)、**MitateDB `0016`** (最後は per-application の `0015_row_order_column_upgrade.sql`。platform 単発は `_upgrade.sql` で終わらせない、`DP10` の D-5 (ii) 機構の実装点)。
- 1 要求あたりの往復は +1 (R-80 の実測 `RM`:500 は r2db 8 tx/req、MitateDB 4 tx/req。§10 の裁定 6)。

**(2) `concurrency` = host 内で共有する slot (裁定 10)**

- 宣言値 L 本の slot ファイルを runtime directory に置く (`<plane>/slot-<i>`。**【v0.4】** directory は plane ごとの env で明示し、ファイルは `<slot directory>/slot-<i>`。裁定 27)。in-flight の要求 1 本が `fcntl.flock(LOCK_EX | LOCK_NB)` で slot 1 本を握る。始点を乱数で選び、L 本を順に試す。全部塞がっていれば `LIMIT_EXCEEDED` (`limit_class` = `concurrency`)。
- 解放は fd の close。process が死ねば kernel が解放する (crash 安全。§1.4 の (4)、close での解放は推測)。DB 往復は無い (条件 5)。stdlib のみ (`fcntl` は darwin / linux に在る)。
- 両 peer 同型の helper 1 つを置き、`_ISOMORPHIC_TARGETS` に登録する (`r2db-api/tests/test_audit_query.py`:2393)。
- 取る位置と保持の範囲は現行の `acquire_concurrency_slot()` と同じ: event loop で認証の前に取り、要求の終わりまで持つ (r2db `http.py`:492、:514、:526 ほか、MitateDB `http.py`:546、:645 ほか)。
- 公開する `limits.concurrency` と denial の `details.limit` は L のまま (r2db `service.py`:1047、:1085)。宣言値 L はそのまま 1 host 全体の上限として届く (利用率の損失なし)。
- 射程: 共有は 1 host (1 composition root の worker 群) に閉じる。base URL を serve する process は 1 host に置く (条件 7 の runbook 規律に「1 host」を足す)。複数 host は本件の範囲外 (宣言 `process_ceilings` は process 数であり host 数を持たない。複数 host にするときは `deployment_required` を宣言するか、共有 limiter を PG に置く R-18 (c) の続きで別起票)。
- 契約との関係: 1.8.0 の :303「the bound holds across every process that may serve that base URL at the same time」は 1 host の全 process で真。:905 の「a bound kept in per-process memory」に当たらない (状態は kernel が持つ)。契約 1.11.0 不変 (裁定 10・13)。 **【v0.4】** 「1 host の全 process が同じ directory を使う」ことは写像の条件 (ceiling ≤ workers、(4)) と directory の明示・検査 (下) で担う (裁定 27)。

**(2') slot の扱いの決定 (v0.4、2026-09-28、裁定 27〜29)**

- **directory**: plane ごとに env で明示し、既定値を持たない (`R2DB_SLOT_DIR` / `MITATEDB_SLOT_DIR`)。control plane は slot を使わない ((3))。
- **作るのは配備側**: r2db は systemd の `RuntimeDirectory=<unit>/slots` と `RuntimeDirectoryMode=0700`。MitateDB は Dockerfile で `USER` (`mitatedb`、`MitateDB-api/docker/Dockerfile`:134) 所有の 0700 の directory を作る。
- **`build_app()` は検査だけする**: directory の存在・所有者 (この process の実効 uid)・mode 0700 を確かめ、合わなければ起動失敗。自分では作らない (worker ごとに別の directory が起きる経路を作らない)。preflight (D-1) でも同じ検査が走る。
- **conformance**: adapter (http / socket) と launcher は instance ごとに `mkdtemp` した directory を配線する (session の adapter と `isolated_application_surface` の取り合いを避ける。§1.4 の (6))。
- **ファイルの開き方**: `O_CREAT | O_NOFOLLOW | O_CLOEXEC`、mode 0600 (裁定 28)。
- **errno の扱い**: 「塞がっている」は EWOULDBLOCK / EAGAIN / EACCES だけ。他の errno (syscall filter の EPERM を含む、§1.4 の (6)) は fail-closed で、既存の DB 失敗と同じ 503 の写像にする。素通ししない (裁定 28)。
- **起動時の自己検査**: 同じ process で同じファイルを 2 回 open し、1 本目の `LOCK_EX` の下で 2 本目の `LOCK_EX | LOCK_NB` が拒まれることを確かめる。拒まれなければ起動失敗。模倣の flock (fcntl() による process 単位の lock)・syscall filter・gVisor 等の差をここで捕らえ、本番の `HAVE_FLOCK` の未確認 (§1.4 の (4)) も覆う (裁定 28)。使うファイルは §9 (r)。
- **fd は要求ごと**: slot の fd は要求ごとに新しく open し、`with` の `finally` で必ず close する。process 内で fd を共有しない (同じ open file への 2 回目の `flock(LOCK_EX)` は取り直しとして成功し、同じ process の 2 要求が同じ slot を持つため)。取得に失敗した fd も同じ `finally` で閉じる (裁定 29)。
- **拒否経路の費用**: 全部塞がっているときは L 回の open / flock / close = 3L 回の syscall を、認証の前に event loop で行う (L = 32 で 96 回)。最適化 (fd を開いたまま持ち process 内の空き表で絞る) は採らない (共有の危険を増やす。§4、裁定 29)。数字は §9 (i)。
- **壊すとどう見えるか (v0.4)**: fd を process 内で共有すると、同じ process の 2 要求が同じ slot を取り、新条件 (a) と peer-local の 2 thread テストが赤 (裁定 29)。EPERM 等を「塞がっている」と読むと全要求が 429、「取れた」と読むと上限が消える。自己検査を外すと模倣 flock の配備で上限が process 内で二重に取れる。directory を `build_app()` が作ると worker ごとに別 directory が起きうる。

**(3) control plane の 2 class (裁定 4・10)**

- `control_requests_per_minute`・`audit_requests_per_minute` は現行のまま (process 内の sliding window、r2db `control_plane.py`:1398-1412、:1421-1435、MitateDB `control_plane.py`:1320-1330、:1344-1358)。control plane は workers を足さず 1 process なので、`process_ceilings.control` = 1 の下で写像は現行どおり `enforced`。

**(4) 写像 (裁定 18、v0.4 で裁定 27・28)**

| peer / plane | 現行 | v0.3 | v0.4 |
|---|---|---|---|
| r2db data | `capabilities_document.py`:131 `"enforced" if process_ceiling <= 1 else "deployment_required"` (集合 :12) | `requests_per_minute` は PG の行が配線されているとき、`concurrency` は slot directory が配線されているとき、それぞれ ceiling に依らず `enforced`。配線されていない構成 (in-process plug、PG の無い構成の in-memory の窓とカウンタ) は現行の式 (**【v0.4】`concurrency` の部分は裁定 27 で覆す**) | `requests_per_minute`: PG の行が配線されていれば ceiling に依らず `enforced` (裁定 18 のまま)。`concurrency`: slot directory が配線されている **かつ** `process_ceilings.data` ≤ この supervisor の workers (env `R2DB_WORKERS` / `MITATEDB_WORKERS`) のときだけ `enforced`、それ以外は `deployment_required` (裁定 27)。配線されていない構成は現行の式 |
| MitateDB data | `capabilities_document.py`:44 `_in_memory_enforcement`、:322、:327 | 同上 | 同上 |
| r2db control | `control_plane.py`:626-629 (集合 :141) | 変えない | 変えない |
| MitateDB control | `control_plane.py`:1575-1577 | 変えない | 変えない |

- **【v0.4】`concurrency` の条件の読み (裁定 27)**: 宣言 (`process_ceilings.data`) が workers より多ければ、別 host に process がありうる (別 host の slot は共有されない) と読んで `deployment_required` にする。正直な宣言から正直な写像が導かれる性質 (1.8.0 以降の現行の写像が持つ性質) を保つ。起動時に workers ≤ ceiling を検査する (D-1) ので、`enforced` になるのは workers = ceiling のときに限る。

**plug ごとの配線 (v0.4、裁定 28)**

| plug (`conformance-tests/registry.json`) | `concurrency` | `requests_per_minute` | 写像 |
|---|---|---|---|
| in-process (`r2db-api`、`MitateDB-api`) | in-memory counter のまま | in-memory の窓のまま | 現行 (ceiling 1 → `enforced`) |
| http (`r2db-api-http`、`MitateDB-api-http`) | instance ごとに `mkdtemp` の directory を配線 | PG の行を配線 | 上の v0.4 の列 |
| socket (`r2db-api-socket`、`MitateDB-api-socket`) | 同上 | 同上 | 同上 |
| real-server (launcher `real_server_r2db`、`real_server_mitatedb`、perf の `--real-server` を含む) | launcher が起動ごとに `mkdtemp` した directory を env で渡す | 同上 | 同上 |

- C-05 V2 の「宣言値 = 実拒否位置」は、http / socket / real-server の plug では slot を通る (裁定 28)。
- http / socket の plug と real-server の launcher が写像の条件に与える workers と ceiling の値 (たとえば launcher の workers 1・ceiling 2 の起動は `deployment_required`、workers 2・ceiling 2 は `enforced`) は D-4 と作業指示書で固定する。

- 2 つの戦略 (共有 / in-memory) を両 peer 同型の helper にする (裁定 18)。
- `process_ceilings` は、配線されていない構成の写像の入力、接続予算 (F-18) の乗数、`verify-declarations` の workers 検査 (D-1) に残る (条件 4)。 **【v0.4】** 加えて、配線された構成の `concurrency` の写像の入力 (ceiling ≤ workers) と、`build_app()` の workers 検査 (裁定 27) にも使う。フェーズ10 設計 L10-3 が拡張点として挙げた「ceiling ≥ 2 でも `enforced`」の形 (`DP10`:828) に当たる。
- 区分 (i) と (iii) の行は変えない。`execution_ms` / `idempotency_retention_ms` の `reference_wall_clock` も変えない。

**(5) 接続予算 = thread limit で数える (裁定 16)**

- 1 process が同時に DB を使う数は thread limiter (既定 4) で抑えられる (§1.4 の (1)(2))。1 process の pool の最大は **thread limit + 定数 c** (c = audit flush thread と platform 1 文の分) とする。
- F-18 の下限は P × (2 × (thread_limit + c)) + control 分、F-16 は P × (1 process の pool 構成) とする。宣言値 L (`concurrency`) は接続予算に入らない (slot は接続を持たない)。
- F-1 との関係 (§1.4 の (1)): F-1 の理由は「同時に借りる数 ≤ pool」の形で残り、同時に借りる数の上限は実効 thread limit (+ c) なので、この寸法で満たされる。pool は env 上書き後の実効 thread limit から導く (WP-2 / WP-3)。
- 現行の式 (v0.2 の記述、参考): F-18 の下限 = P_data × (platform_pool_floor + application_pair_floor [登録 application ≥ 1 のとき]) + P_control × control_plane_floor。platform_pool_floor = 2 × `concurrency`、application_pair_floor = 2 × `concurrency`、control_plane_floor = 16 (r2db `r2db-api/src/r2db_api/platform_declarations.py`:1343-1375、定数 :947、:954、:960。MitateDB `MitateDB-api/src/mitatedb_api/platform_declarations.py`:1209-1235、:1318-1350、定数 :917、:927、:934)。判定は `下限 + superuser_reserved_connections + reserved_connections <= max_connections`。F-16 (role の `CONNECTION LIMIT`) は起動した process の pool 構成 1 本分だけを床にする (r2db `main.py`:517-536、MitateDB `main.py`:411)。
- role の `CONNECTION LIMIT` の現行値: r2db `r2db-api/migrations/0013_role_connection_limits.sql`:109-110 (api 68、controlplane 20)、:132-133 (application の runtime / developer 各 36)。MitateDB `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`:89-91 (api 132、controlplane 36、auditreader 12)、:113、:116 (application の role 各 68。並走 2 を前提にした値、`RM`:472)。
- MitateDB の application は process ごとに永続接続を持つ (served application ごとに 2 本、`MitateDB-api/src/mitatedb_api/config.py`:313-316、`backend_postgres.py`:294)。N process なら N 組になる。role ごとの需要は作業指示書で数える (§9 (e))。
- 算術は §7.3。

**根拠**: 静的分割 (v0.2) は、K=32 の一斉送信が 4 worker に 8/8/8/8 に分かれる確率が 0.54% で、宣言 32 のうち 9〜20 本目で 429 が出る (設計レビュー 1 回目の指摘 2。裁定 10)。宣言値を読んで計画する AI client に見える欠陥であり、計測 (D-16) も完走しない。host 共有の slot は宣言値 L をそのまま届け、crash で漏れず、DB 往復を足さない。`requests_per_minute` は credential を鍵にし認証の後でしか数えないので、PG に置いても未認証要求の増幅が無い (条件 5)。

**壊すとどう見えるか**: slot を process 内に戻すと、2 worker で L を超えて in-flight になり新条件 (a) が赤になる。`LOCK_NB` を外すと満杯時に待ちになり (429 が出ない) C-05 V2 が赤になる (裁定 10)。`requests_per_minute` を process 内の窓に戻すと、2 process に振った要求が 2L まで通り、新条件 (b) が赤になる。写像を「配線に依らず `enforced`」にすると、in-process plug で ceiling ≥ 2 のとき偽の `enforced` になる (裁定 18)。 **【v0.4】** `concurrency` の写像から「ceiling ≤ workers」を外すと、2 host × 2 workers を正直に ceiling 4 と宣言した配備が `enforced` と出る (実際の上限は 2L。裁定 27)。rate 行の配列を L に比例させる形に戻すと、1 文の費用が L に比例する (裁定 30)。

### D-4 conformance

```text
D-4 **conformance**: C-26 (4) を「ceiling 2 でも `enforced`」に改め、**新条件 (番号は conformance WP で採番。§10 の裁定 7)** (launcher で実 process を 2 本起動し、(a) `concurrency` を hold_in_flight で process をまたいで数え宣言値を超えないこと、(b) `requests_per_minute` を 2 process に振って宣言値ちょうどで LIMIT_EXCEEDED になること) を足す。launcher (`socket_harness.start_uvicorn_subprocess`、両 `real_server_*.py`) に `workers` 引数。C-05 の honest limits (「実 process 数を観測しない」) を 新条件 の分だけ狭める。
```

- **【v0.3 改定、2026-09-28 (裁定 11・12・14・19)】**
  - **C-26 (4) は宣言と実際の bound の一致を見る** (裁定 12、(甲))。ceiling 1 → `enforced`。ceiling 2 → 宣言が `enforced` と `deployment_required` のどちらでもよいが、`enforced` を宣言した peer には新条件 (a)(b) を課す (宣言で分岐。C-30 の版分岐と同じ形)。`deployment_required` を宣言する peer は現行どおり適合。義務の追加は無い (契約不変と整合)。両 peer は `enforced` を宣言する (D-3)。上の枠の「C-26 (4) を『ceiling 2 でも `enforced`』に改め」は本裁定で改めた。
  - **新条件 (a) `concurrency`** (裁定 14): launcher (両 `real_server_*.py`) に port「entity の保存先を PostgreSQL の lock で保持する」を足す (自前の特権接続で `LOCK TABLE … IN ACCESS EXCLUSIVE MODE`)。保持時間は `execution_ms` と role の statement_timeout より短くする。workers = 2 の起動形で L + P 本 (以上) を同時に送り、429 を除いた「保持中の本数」がちょうど L であること、かつ保持中の要求が 2 worker 以上に分かれていることを主張する。worker の識別は各 worker の PostgreSQL 接続の `application_name` (`"<peer>:<plane>:<pid>"`) を `pg_stat_activity` で数える。`application_name` は本番にも残る観測性の改善であり、テスト用フックではない。本番コードに stall フックを足さない。上の枠の「hold_in_flight で」は本裁定で改めた。
  - **新条件 (b) `requests_per_minute`**: workers = 2 の起動形で要求を 2 process に振り、宣言値ちょうどで `LIMIT_EXCEEDED` になること (枠のとおり)。窓は DB の時計の sliding なので、窓の境目を待つ手順は要らない (D-3 (1))。
  - **C-26 (5)** は launcher の workers ≥ 2 の起動形 (事前検査 → uvicorn) でも fail-fast (非 0 終了と F-15 の文言) を観測する (裁定 11)。 **【v0.4】** 事前検査は preflight の one-shot (D-1、裁定 26)。
  - **launcher** (裁定 19): supervisor を process group で起動し、停止は killpg。pidfile に子の pid も記録し、孤児掃除の対象に足す。 **【v0.4】** 子の pid の記録は裁定 33 で pgid の記録に改める (下)。
- **【v0.4 改定、2026-09-28 (裁定 26・27・28・32・33)】**
  - **新条件 (b) の観測法** (裁定 32): `concurrency` 以下の波に分けて、新しい接続で 2L 本送る。主張は 3 つ: (i) 200 がちょうど L 本、(ii) `requests_per_minute` の 429 が L 本、(iii) 200 の pid (子の access log、裁定 17 の pid 付き access log) が 2 種以上。窓を process 内に戻す変異は 200 が L を超えて赤になる。上の v0.3 の「要求を 2 process に振り」の観測手段は本裁定で決めた (§9 (g))。
  - **孤児掃除は pgid で記録する** (裁定 33)。子の pid は supervisor の置き換えで古くなる。pidfile には supervisor の pgid (killpg と同じ単位) を記録し、掃除は pgid 単位で行う。
  - **C-26 (5) の起動形** (裁定 26): launcher の workers ≥ 2 の起動形は「preflight の one-shot → uvicorn の supervisor」とし、宣言の欠けた配備で preflight の非 0 終了と F-15 の文言を観測する。
  - **slot の配線** (裁定 27・28): launcher と http / socket の adapter は instance ごとに `mkdtemp` した slot directory を env (`R2DB_SLOT_DIR` / `MITATEDB_SLOT_DIR`) で渡す。launcher は workers を env (`R2DB_WORKERS` / `MITATEDB_WORKERS`) でも渡す (`build_app()` の workers 検査と写像の入力。D-3 (4))。
  - **C-26 (4) の分岐と workers** (裁定 27): 写像は ceiling ≤ workers のときだけ `enforced` なので、C-26 (4) の ceiling 2 の起動形の workers の値で、観測される宣言 (`enforced` / `deployment_required`) が決まる。上の v0.3 の「両 peer は `enforced` を宣言する」が成り立つのは workers 2 で起動したときである (起動形の workers の値は §9 (t))。
- 本書の本文 (枠の逐語を除く) では新条件の番号を書かない (`conformance-tests/CONDITIONS.md` の最後は C-31、:60。`tools/check_doc_refs.py` は定義の無い条件番号を参照切れとして止める)。番号は WP-1 が行を足すときに確定する。
- 触る現物: C-26 (4) のテスト `conformance-tests/test_c26_composition_root.py`:220- (`test_c26_ceiling_maps_to_limit_enforcement`)、C-26 (5) のテスト :245-258 (`test_c26_missing_declaration_fails_fast`)、C-26 の行 `conformance-tests/CONDITIONS.md`:55、C-05 の行 :34 の honest limits (6)、launcher `conformance-tests/socket_harness.py`:743-814 (`start_uvicorn_subprocess`、1 呼び出し 1 process、pidfile :809、停止 :364-383、孤児掃除 :884-)、`r2db-api/conformance/real_server_r2db.py`:613- (`start`)、:711- (`restart`)、:847-887 (C-26 (5) の起動)、`MitateDB-api/conformance/real_server_mitatedb.py`:563-、:651-。
- 現行の launcher は `ceilings` を宣言に渡すだけで、起動する uvicorn は data・control 各 1 本である (`real_server_r2db.py`:667-677)。
- **壊すとどう見えるか**: 写像だけを変えて C-26 (4) を直さないと C-26 (4) が赤。launcher に `workers` を足さないと新条件は実 process 1 本で走り、(a)(b) とも観測対象が無い (`OPERATING_CONDITIONS.md` §1.5 の 32 の空振り)。slot を process 内に戻すと保持が 2L になり (a) が赤。L + 1 本目が通ると (a) が赤 (裁定 14)。 **【v0.4】** rate の窓を process 内に戻すと、(b) の 200 が L を超えて赤 (裁定 32)。200 がすべて 1 つの pid なら (b) の (iii) が赤 (空振りの検出)。孤児掃除を子の pid で行うと、置き換えられた子の後の pid を取り逃す (裁定 33)。

### D-5 計測

```text
D-5 **計測**: `tools/perf_baseline.py --real-server <peer> --workers N`。判定規則は D-16 の逐語 (K=1 と K=32 `--warmup 3 --n 15`、K=32 は 2 run、両 peer とも 2 run が 8 倍以内)。加えて K=1 の非退行 (§0.1.4 の 1) を N=1 と N=4 で記録。R-101 行はこの結果で閉じる (R-113 と同じ変更セットで判定)。
```

- **【v0.3 追記、2026-09-28 (裁定 17)】** 計測の固定事項は §7.2 に置く: 計測時の `concurrency` の宣言値 64、worker ごとの受付数の記録、429 が出た run は捨てて記録に残す、判定規則 D-16 の逐語は変えない、K=1 の非退行は N=1 と N=4 で記録する。 **【v0.4、2026-09-28】「計測時の `concurrency` の宣言値 64」は裁定 31 で覆す (計測は本番既定の 32)。他の項は残る。**
- **【v0.4 追記、2026-09-28 (裁定 30・31)】** 計測は本番既定の `concurrency` 32 で行う。slot の `with` は応答を作る前に抜ける (§1.4 の (6)) ので、K=32 の group は 32 本の応答が返ってから次へ進み、溢れない。実測で 429 が出たときだけ再検討する (裁定 31)。計測の前に rate の文の小実験を行う (§7.3、裁定 30)。
- 計画は §7。R-101 行の閉止を本変更セットで行うかは Q-5。
- **壊すとどう見えるか**: 判定規則を計測の後に動かすと、R-101 作業指示書 §7.2 の (c) (計測後に動かさない) に反する。

### D-6 クラス

```text
D-6 **クラス**: `conformance-tests/` と `security/CONTROL_MAPPING.md`、migration (platform 表の追加 = r2db `0015` / MitateDB 次番。platform 単発、`_upgrade.sql` ではない) に触るので Class C 以上 (`tools/change_class.py` で確定)。契約に触れないので設計レビュー 1 回。規模 L (台帳)。
```

- **【v0.3 改定、2026-09-28 (裁定 22)】 Class D。** 根拠: `security/CONTROL_MAPPING.md` の SI-08 の主張を改める (`security/` 配下)、`_ISOMORPHIC_TARGETS` の集合を増やす (slot helper、写像の 2 戦略の helper)。`RM` §9 の 8 の表の D 行に当たる。契約に触れないので設計レビューは 1 回 + 裁定 10〜22 の反映の再確認 (同じレビュー担当)。依頼者裁定 (Q-1〜Q-5) は逐語で §5 に記録する。上の枠の「Class C 以上」と v0.2 の「(A)(C) なら設計レビュー 2 回」(裁定 1) は本裁定で改めた。
- 現物で確定した番号: r2db `0015`、MitateDB `0016` (D-3 の (1))。
- 規模 L (台帳)。規模の表は `OPERATING_CONDITIONS.md` §1.13 の 74。WP ごとのクラスの見込みは §6。
- **壊すとどう見えるか**: 宣言したクラスが `tools/change_class.py` の判定より軽いと、必要な証拠 (`RM` §9 の 8 の証拠列) が欠ける。

### D-7 記録

```text
D-7 **記録**: 台帳 R-113・R-101・R-18・R-52 行に【追記】、CONTROL_MAPPING の SI-08 の Control 主張 (区分 (ii) の写像) を改める、両 runbook (workers と ceilings の対応、接続予算)、`tools/PERF_BASELINE_README.md`。
```

- 経路は §8。`security/CONTROL_MAPPING.md` の出所の行は r2db の写像 :711-712、MitateDB の写像 :904、C-26 の開示 :988 である (裁定 21 の訂正。§1.2)。
- 台帳に起こす行: `spec/data-service-api.v1.json`:925 の fixed window と両 peer の sliding window の食い違い (裁定 13)。起票文案は §8。
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

**v0.3 で足す却下案 (2026-09-28、裁定 10・21)**

- 静的分割 (v0.2 の D-3 の pre-auth 3 class、b = ⌊L/P⌋): K=32 の一斉送信が 4 worker に 8/8/8/8 に分かれる確率は 0.54% で、本番でも宣言 32 のうち 9〜20 本目で 429 が出る。宣言値を読んで計画する AI client に見える欠陥であり、計測 (D-16) も完走しない。却下 (裁定 10)。上の枠の (γ) の「却下 (pre-auth の class だけ分割 = D-3)」の括弧内は、本裁定で分割そのものが撤回されたので当てはまらない。
- PostgreSQL の共有 counter (`concurrency`): crash で slot が漏れる / pre-auth に DB 往復 (条件 5)。却下 (裁定 10)。
- POSIX 名前付き semaphore: 依存 `posix_ipc` を足す。却下 (裁定 10)。
- `multiprocessing` の semaphore: uvicorn の spawn 子に渡せない。却下 (裁定 10)。
- nginx `limit_conn`: 429 の envelope を app が出せない / Cloud Run に nginx が無い。却下 (裁定 10)。
- nginx / Cloud Run の rate limit を pre-auth の 3 class に使う案: 配備層の bound は `deployment_required` の意味になる / Cloud Run に nginx が無い (裁定 21。上の枠の nginx の行の理由は credential 単位の class にだけ当てはまる)。

**v0.4 で足す却下案 (2026-09-28、裁定 26・29・30)**

- 事前検査に `ops verify-declarations` を使う案 (v0.3 の D-1、裁定 11): provision の DSN を data plane の unit / container に置くことになり最小権限に反する (`MitateDB-api/docs/cloud-run-cloud-sql.md`:1079)。検査の集合も data plane の起動時の検査と一致しない (serve する application の registry 検証と、この process の構成で数える F-16 を含まない)。却下 (裁定 26)。運用者の手動検査としては残す。
- slot の fd の共有による最適化 (fd を開いたまま持ち、process 内の空き表で探索を絞る): 拒否経路の 3L 回の syscall は減るが、同じ open file への 2 回目の `flock(LOCK_EX)` は取り直しとして成功するので、同じ process の 2 要求が同じ slot を持つ危険が増える。却下 (裁定 29)。
- rate 行を `timestamptz[]` (要求ごとの時刻の配列、v0.3 の D-3 (1)) にする案: 配列が上限 L (既定 600、約 4.8 KB) まで伸び、1 文ごとに走査して作り直す費用が L に比例し、TOAST の閾値を超えうる。同じ credential の 32 要求が全 worker をまたいで 1 行に並ぶ計測では、最悪の費用が毎回出る。却下 (裁定 30。int[60] + 基点の秒に改める)。

## 5. 依頼者判断待ち (枠 §5。両論のまま置く)

依頼者裁定は各項の「裁定:」に逐語で記録する (裁定 22)。

### Q-1 区分 (ii) の置き場

- **【v0.3 書き換え、2026-09-28】** v0.2 の選択肢 (A) D-3 の 2 分 (rate = PG 共有 / pre-auth = 静的分割)、(B) (α)、(C) (γ) 4 class 全部を静的分割、と監督案 (A) は、静的分割の撤回 (裁定 10) により次の (A')(B)(C') に書き換えた。
- 選択肢: (A') `requests_per_minute` → PG の sliding 行、`concurrency` → host 共有 slot、control 2 class → 現行 (control plane 1 process)。(B) 宣言で落とす (`deployment_required`)。(C') 静的分割 + 契約 1.12.0。
- (A') の側: 契約不変。宣言値 L が 1 host 全体の上限としてそのまま届き、pre-auth に DB 往復を足さない。代わりに 1 要求 1 往復と platform 表 1 つ、slot directory の配備 (runtime directory) を足し、serve する process を 1 host に置く規律が要る。
- (B) の側: 契約不変。コードの変更が最小。代わりに bound が N 倍に緩み、条件 9 の「制約で回避」に当たる。
- (C') の側: 撤回 (設計レビュー 1 回目の指摘 2)。却下理由: K=32 が 4 worker に均等に分かれる確率は 0.54% で、宣言 32 のうち 9〜20 本目で 429 が出る (§4)。加えて契約 1.12.0 の文言の明確化を要する (v0.2 の裁定 1、裁定 10 で覆した)。
- 監督案: (A')。
- 裁定: **依頼者裁定 2026-09-28 (逐語: 「Q-1 は (A')、Q-3 は 1、Q-4 は (B)、Q-5 は行う で進めます。」)** → (A') を採る。再審議しない (`OPERATING_CONDITIONS.md` §1.7 の 51)。

### Q-2 `requests_per_minute` の窓の形

- 選択肢: (A) fixed window (PG の 1 行)。(B) sliding (現行) のまま PG に置く。
- (A) の側: credential ごと・窓ごとに 1 行を 1 文で原子的に数えられる。契約は「1 分あたり」しか言わない (D-3 の (1))。
- (B) の側: 現行の挙動を変えない。r2db の control plane の窓の docstring は、fixed window は窓の境目で 2 窓分の突発を許し sliding の方が厳しい、として sliding を意図して残すと書く (`r2db-api/src/r2db_api/control_plane.py`:1402)。推測: PG の上で sliding を表すには要求ごとの時刻を持つ行か区間の集計が要り、1 行 1 文にはならない。 **【v0.3、2026-09-28】** この推測は誤り。1 credential 1 行の時刻の配列を 1 文で更新する形がある (裁定 15、D-3 (1))。
- 監督案: (A) fixed。 **【v0.3、2026-09-28】** 裁定 15 で覆す。
- 裁定: **監督裁定 15 で閉じた (2026-09-28)。現行の sliding を保つ (依頼者判断を要しない)。**

### Q-3 N の既定値

- 選択肢: (A) 1 (現行の配備を変えない。配備者が明示する)。(B) core 数から導く。
- (A) の側: 既存配備は宣言 `process_ceilings` = 1 のままで一致する。N と ceiling を配備者が同時に書く。
- (B) の側: 何も書かなくても GIL の外に出る。代わりに実 process 数が宣言と独立に決まり、不一致 (§9 (c)) の機会が増える。
- 監督案: (A) 1。
- 裁定: **依頼者裁定 2026-09-28 (逐語: 「Q-1 は (A')、Q-3 は 1、Q-4 は (B)、Q-5 は行う で進めます。」)** → N の既定値は 1。
- 註 (v0.3): 裁定 11 で `--workers` は 1 のときも常に明示し、env に必須で置く。

### Q-4 MitateDB の Cloud Run で増やす軸

- **【v0.3 書き換え、2026-09-28 (裁定 10・20)】** v0.2 の選択肢は (A) container 内の workers、(B) instances、(C) 両方可 (ceilings = instances × workers)、監督案は (C) だった。裁定 20 は監督案を「(B) instance は 1 のまま `--workers` と `--cpu` で伸ばす」とするので、選択肢の記号を裁定の文言に合わせて並べ替えた (v0.2 の (A) が v0.3 の (B)、v0.2 の (B) が v0.3 の (A))。
- 選択肢: (A) instances で伸ばす (container の形は変えない)。(B) instance は 1 のまま `--workers` と `--cpu` で伸ばす。(C) 両方可、ceilings = instances × workers。
- (A) の側: container の形 (CMD) を変えない。水平に増える。代わりに instance は別 host なので host 共有の slot (D-3 (2)) が共有されず、`concurrency` は `enforced` と宣言できない (`deployment_required` を宣言するか、共有 limiter を PG に置く別起票。裁定 10 の射程)。 **【v0.4】** 裁定 27 の写像では、instances × workers を ceiling に宣言すると ceiling > workers なので `concurrency` は自動的に `deployment_required` になる。
- (B) の側: 1 instance の中で GIL の外に出る。Cloud Run の instance 数は現行の Invariant 1 (`MitateDB-api/docs/cloud-run-cloud-sql.md`:1327-1358) のまま。host 共有の slot がそのまま効く。`--cpu` ≥ workers を runbook に置く。 **【v0.4】** 推測 (現物未確認): Cloud Run は急な負荷で一時的に max-instances を超えることがある。その間は 2 host になり slot が共有されない。runbook の開示に「推測」と明記して 1 行添える (裁定 33)。revision の切り替えの重なりは R-52 の射程 (裁定 25)。
- (C) の側: 両方の自由度を残す。代わりに runbook に積の算術と、両方を変えたときの宣言の書き直しを置く。autoscaling の算術: P = max-instances × workers を分母にすると、Cloud Run が縮退している平常時 (実 instance 数 < max) は宣言値に届かない (例: max-instances 4 × workers 4 = 16 で、v0.2 の分割なら `concurrency` 32 に対して b = 2)。container の vCPU が workers より少なければ GIL の外にも出ないので、`--cpu` ≥ workers が要る。instances ≥ 2 は (A) と同じく host 共有の slot の射程の外である。
- 監督案: (B) (裁定 20。v0.2 の監督案 (C) は裁定 20 で改めた)。
- 裁定: **依頼者裁定 2026-09-28 (逐語: 「Q-1 は (A')、Q-3 は 1、Q-4 は (B)、Q-5 は行う で進めます。」)** → (B) instance は 1 のまま `--workers` と `--cpu` で伸ばす。

### Q-5 R-101 の閉止を本変更セットの D-5 の結果で行うか

- 選択肢: (A) 行う (D-5 の D-16 成立で R-101 を閉じる)。(B) 行わない (R-113 と R-101 を別に閉じる)。
- (A) の側: 閉止形 (`RM` §0.1.4 の 2) は R-101 のものであり、同じ判定規則で同じ計測器を使う。R-101 の行は「次は R-113」と記している (`RM`:521)。
- (B) の側: R-101 の範囲は直列化の切り分けと 1 process 内の是正で、multi-process は R-113 の範囲として起票された (R-101 作業指示書 §12 の (12-1))。
- 監督案: (A) 行う。
- 裁定: **依頼者裁定 2026-09-28 (逐語: 「Q-1 は (A')、Q-3 は 1、Q-4 は (B)、Q-5 は行う で進めます。」)** → 行う (R-101 の閉止は本変更セットの D-5 の結果 = D-16 で判定する)。

## 6. WP 分割案 (conformance を実装より先に置く)

各 WP の完了条件・変異の対応表・道具の引数は作業指示書 (Change Set Manifest、`RM` §9 の 9) に置く。クラスは `tools/change_class.py` で確定する。契約は不変なので契約の WP は置かない (v0.2 の「(A)(C) のとき契約 WP を先に置く」は裁定 10 で失効)。

| WP | 内容 | 触る経路 (現物) | クラス見込み |
|---|---|---|---|
| **WP-1** conformance | C-26 (4) を宣言で分岐する形に改める (裁定 12)。新条件 (a)(b) の行とテストを足す (裁定 14)。C-26 (5) を workers ≥ 2 の起動形 (事前検査 → uvicorn) でも観測する (裁定 11)。launcher に `workers`、`LOCK TABLE` で保持する port、process group の起動と killpg、pidfile への子の pid の記録と孤児掃除 (裁定 19)。C-05 の honest limits (6) を新条件の分だけ狭める。`COLLECTION_FLOOR` の追随。**【v0.4】** 新条件 (b) の 3 主張と波の送り方 (裁定 32)。孤児掃除を pgid で記録 (裁定 33。子の pid の記録を改める)。C-26 (5) の起動形を preflight → uvicorn に (裁定 26)。launcher が `mkdtemp` の slot directory と workers を env で渡す (裁定 27) | `conformance-tests/CONDITIONS.md` (:34、:55、新しい行)、`conformance-tests/test_c26_composition_root.py`、新条件のテストファイル (新規)、`conformance-tests/socket_harness.py`、`r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py`、`conformance-tests/` の `COLLECTION_FLOOR` | C (`conformance-tests/` 配下)。launcher に同名 helper を足して登録すれば D |
| **WP-2** r2db 実装 | migration `0015` (rate の表、FK `ON DELETE CASCADE`、api role への INSERT / UPDATE / SELECT)。`requests_per_minute` を PG の sliding 行へ (裁定 15)。slot helper (裁定 10)。写像の 2 戦略の helper (裁定 18)。接続の `application_name` (裁定 14)。`verify-declarations` の workers 検査 (裁定 11)。接続予算の式 (pool の寸法、F-16、F-18 を thread limit 基準に。裁定 16)。配線と migration 一覧の追随。**【v0.4】** `main.py` に preflight の entry (裁定 26)。`build_app()` に workers ≤ ceiling の検査と slot directory の検査 (存在・所有者・0700、裁定 27)。slot helper は D-3 (2') の決定どおり (開き方・errno・自己検査・要求ごとの open / close。裁定 28・29)。rate 表は int[61] (裁定 34) + 基点の秒の 1 文 (裁定 30。上の「sliding 行」の形を改める)。写像の `concurrency` に ceiling ≤ workers (裁定 27)。rate の文は認証で借りた接続を返した後に借りる (裁定 33。完了条件)。http adapter は instance ごとに `mkdtemp` の slot directory を配線 | `r2db-api/migrations/0015_*.sql` (新規)、slot helper の module (新規。名は作業指示書)、`r2db-api/src/r2db_api/service.py` (:1019-1109)、`http.py`、`capabilities_document.py`、`limits.py` (:121-165)、`main.py`、`platform_declarations.py` (:1343-1375)、`ops.py` (:1183-1187 ほか)、`postgres.py` と credential store / audit sink の接続工場、`r2db-api/conformance/conformance_adapter_r2db_http.py`、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh`、`r2db-api/tests/` (`test_audit_query.py`:2393 の `_ISOMORPHIC_TARGETS` を含む) | D (`_ISOMORPHIC_TARGETS` の増減。`RM` §9 の 8) |
| **WP-3** MitateDB 実装 | WP-2 と同型。migration `0016`、`_LimitStateHolder` の `requests_per_minute` を PG の sliding 行へ、slot helper、写像の 2 戦略、`application_name`、`verify-declarations` の workers 検査、接続予算の式、配線と migration 一覧の追随。**【v0.4】** WP-2 の v0.4 の項と同型 (preflight の entry、`build_app()` の workers と slot directory の検査、slot helper、rate 表 int[61] (裁定 34)、写像、借りる順序、http adapter の `mkdtemp`) | `MitateDB-api/migrations/0016_*.sql` (新規)、slot helper の module (新規)、`MitateDB-api/src/mitatedb_api/cell.py` (:306-411)、`http.py`、`capabilities_document.py`、`config.py` (:300-319)、`main.py`、`platform_declarations.py` (:1209-1235、:1318-1350)、`ops.py` (:1452- ほか)、`backend_postgres.py` と platform pool の接続工場、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`、`MitateDB-api/tests/` | D (同上) |
| **WP-4** 計測 | `tools/perf_baseline.py --real-server <peer> --workers N` (launcher に渡し、宣言 ceiling を N にする)。計測時の `concurrency` 64 の宣言 (§7.2、r2db の入口は両論。**【v0.4】裁定 31 で覆す: 本番既定の 32 で計測し、`concurrency` を上書きしない**)。子の access log を pid 付きで保存し、worker ごとの受付数を記録する (裁定 17)。§7 の実測は監督。**【v0.4】前提: rate の文の小実験 (§7.3、表 7-5) が 0.2 ms/文以内であること。超えれば監督に上げる (裁定 30)** | `tools/perf_baseline.py`、`tools/tests/`、`tools/PERF_BASELINE_README.md`、launcher (`r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py`) の log 設定 | B (launcher に触れれば C) |
| **WP-5** 配備 | r2db の unit に `ExecStartPre=` (`ops verify-declarations`) と `--workers`、env `R2DB_WORKERS` を必須に。MitateDB の Dockerfile `CMD` に事前検査と SERVICE ごとの workers。slot directory の置き場 (§9 (j))。runbook に「1 host」「`--max-instances=1`、`--cpu` ≥ workers」、SIGTTIN の禁止、workers と ceilings の対応、接続予算。**【v0.4】** `ExecStartPre=` の中身は preflight の entry (裁定 26。`ops verify-declarations` は置かない)。unit に `RuntimeDirectory=<unit>/slots` と `RuntimeDirectoryMode=0700`、env に `R2DB_SLOT_DIR`。Dockerfile に `USER` 所有の 0700 の slot directory、env に `MITATEDB_SLOT_DIR`、`CMD` の data の枝に preflight (裁定 27)。runbook に `verify-declarations` の workers 検査を運用者の手動検査として (裁定 26)、Cloud Run が一時的に max-instances を超えうる件を「推測」と明記して 1 行 (裁定 33) | `r2db-api/deploy/systemd/r2dbsvc-api.service` (:60 ほか)、`r2db-api/deploy/env/api.env.example`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (:96-106)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`MitateDB-api/docker/Dockerfile` (:145)、`MitateDB-api/docs/cloud-run-cloud-sql.md` (:1327-1358 Invariant 1 ほか) | B (unit・Dockerfile)。runbook だけなら A |
| **WP-6** 記録 | 台帳・`CONTROL_MAPPING`・本書の版上げ、起票文案 (§8) の台帳行 | §8 | D (`security/` 配下) |

- 順序: WP-1 → WP-2 → WP-3 → WP-4 → §7 の実測 → WP-5 → WP-6。 **【v0.4】** WP-4 の前に §7.3 の小実験 (裁定 30)。WP-1 の新テストは WP-2 / WP-3 が入るまで赤である (変異先行の形)。統合の単位は監督が決める。
- WP-2 と WP-3 を並行させるときは、触るファイルの重なりが 0 であることを作業指示書の表で示す (`OPERATING_CONDITIONS.md` §1.2 の 16、17)。同名 helper の本体を両 peer で一致させる (条件 3) ので、登録の表 (`r2db-api/tests/test_audit_query.py`:2393 の `_ISOMORPHIC_TARGETS`) を触る WP は 1 つに寄せる。
- WP-1 と WP-4 は launcher の 2 ファイルを共に触る。順序で分ける (並行させない)。
- **【v0.4】変異の対応表の候補** (作業指示書で「完了条件番号 → 変異」の表に落とす。`OPERATING_CONDITIONS.md` §1.5 の 40)。変異を持たない行は「監査照合」とし、照合対象の逐語を作業指示書に残す。

| WP | 変異 (候補) | 赤になるもの |
|---|---|---|
| WP-1 | rate の窓を process 内に戻す | 新条件 (b) の (i) (200 が L を超える) (裁定 32) |
| WP-1 | slot を process 内の counter に戻す | 新条件 (a) (保持 2L) (裁定 14) |
| WP-1 | preflight の entry が例外を握って 0 で終わる | C-26 (5) の workers ≥ 2 の起動形 (裁定 26) |
| WP-1 | 孤児掃除の記録を pgid から子の pid に戻す | launcher の掃除のテスト (子の置き換えの後に残る process が 0) (裁定 33) |
| WP-2 / WP-3 | slot の fd を process 内で共有する | 新条件 (a) と peer-local の 2 thread テスト (裁定 29) |
| WP-2 / WP-3 | EWOULDBLOCK / EAGAIN / EACCES 以外の errno を「塞がっている」と読む | peer-local テスト (flock が EPERM を返す偽装で 503 を期待) (裁定 28) |
| WP-2 / WP-3 | 起動時の自己検査を外す | peer-local テスト (二重に取れる偽装の flock で起動失敗を期待) (裁定 28) |
| WP-2 / WP-3 | `O_NOFOLLOW` を外す | peer-local テスト (slot が symlink のとき open が失敗) (裁定 28) |
| WP-2 / WP-3 | `build_app()` の slot directory の mode 検査を外す | peer-local テスト (0755 の directory で起動失敗を期待) (裁定 27) |
| WP-2 / WP-3 | `build_app()` の workers ≤ ceiling の検査を外す | peer-local テスト (workers > ceiling で起動失敗を期待) (裁定 27) |
| WP-2 / WP-3 | 写像の `concurrency` から ceiling ≤ workers を外す | peer-local の写像テスト (workers 1・ceiling 2 で `deployment_required` を期待) (裁定 27) |
| WP-2 / WP-3 | rate の 1 文の WHERE を「合計 ≤ L」にする | C-05 V2 (L + 1 本目が通る) (裁定 30) |
| WP-2 / WP-3 | rate の文を認証の接続を借りたまま借りる | 裁定 33 の借りる順序の pin (AST 走査) か監査照合 (作業指示書で選ぶ) |
| WP-4 | launcher に `--workers` を渡さない | `tools/tests/` の起動形のテスト (supervisor の子が N 本) |
| WP-5 | unit / Dockerfile の slot directory の 0700 と env | 監査照合 (該当行の逐語)。配備時は `build_app()` の検査 (裁定 27) が起動を止める |
| WP-6 | 台帳・`CONTROL_MAPPING` の主張 | 監査照合 |

- WP の表の「migration 一覧の追随」の経路は、直近の platform migration の名前を持つファイルの現物 (`git grep` で r2db `0014_auditreader_statement_timeout`、MitateDB `0011_process_ceilings` / `0014_role_connection_limits_rollout` を持つもの) から拾った。テスト以外の全件を作業指示書で確定する。

## 7. 計測計画

### 7.1 判定規則 (R-101 作業指示書 §10.1 の D-16、逐語。計測前に固定)

```text
D-16 閉止の判定規則 (計測前に固定): real-server plug で K=1 と K=32 (`--warmup 3 --n 15`) を取り、K=32 は 2 run 取る。query の p50 の K=32 / K=1 の比が両 peer で K=32 の 2 run とも 8 倍以内 = R-101 閉止 (RM §0.1.4 の 2 の改訂形)。ε (K=32 の 2 run の相対差) と δ = max(10%, 2ε) は記録だけで、判定には使わない。本変更セットでは server は 1 process なので 8 倍は満たさない見込み — その実測を設計メモ v0.3 §6 に逐語で残し、R-113 (multi-process、規模 L) の出発点にする。
```

- 本件での当てはめ: 判定は N=4 の行だけで行う。N=1 の行は同じ木での対照として記録する。最後の文 (1 process の見込み) は R-101 のものであり、本件の判定に使わない。
- K=1 の非退行 (`RM` §0.1.4 の 1): 変更セットの完了ゲートで取る K=1 の `perf_baseline.py --warmup 20 --n 200` の p50 が同一 plug・同一 op の直近基準値の +40% 以内、p95 が +50% 以内。
- D-16 の逐語は変えない (裁定 17)。

### 7.2 条件

- 道具: `tools/perf_baseline.py --real-server <peer> --workers N` (WP-4)。client は子 process (`--client-processes` 既定 8、実際の数は min(8, K))。thread limit は既定 4。
- 宣言: launcher の `start(ceilings=...)` に data = N を渡す。control の値は launcher が起動する control の process 数 (1) とする。
- **計測時の `concurrency` の宣言値は 64** (裁定 17)。理由: K=32 の一斉送信が slot の解放の遅れ (応答送信後の `finally`) で 429 を踏まないため。宣言値は接続予算に入らない (D-3 (5)) ので他に影響しない。本番既定は 32 のまま。 **【v0.4、2026-09-28】裁定 31 で覆す。理由の前提が現物と違う (slot の `with` は応答を作る前に抜ける。r2db `r2db-api/src/r2db_api/http.py`:524-557、MitateDB `MitateDB-api/src/mitatedb_api/http.py`:645-656)。**
- **【v0.4】計測時の `concurrency` は本番既定の 32** (裁定 31)。launcher は `concurrency` を env で上書きしない。実測で 429 が出たときだけ再検討する (表 7-4 に記録し、監督に上げる)。
- **【裁定 31 (v0.4) で不要になった両論。記録として残す】** **r2db での 64 の与え方 (両論。監督が決める)**: r2db には `concurrency` を env で変える入口が無い (§1.4 の (3))。MitateDB は launcher の env に `MITATEDB_MAX_CONCURRENCY=64` を置けば足りる。 **【v0.4、2026-09-28】裁定 31 で不要 (64 を与えないので、下の (甲)(乙) はどちらも採らない。裁定 24 の (甲) も裁定 31 で覆した)。**
  - (甲) r2db に env の入口を足す (MitateDB の `MITATEDB_MAX_CONCURRENCY` と対称)。launcher は両 peer とも env で 64 を与える。代わりに本番の設定面が 1 つ増え、`ops.py`:1183-1187 の「fixed on this peer」の docstring と `verify-declarations` の F-16 の値の出所が変わる (WP-2 の範囲が広がる)。
  - (乙) r2db の `build_app` に limits の引数を足し、launcher が計測用の import string (factory) で 64 を渡す。本番の設定面は増えない。代わりに計測の起動形が本番の起動形 (`r2db_api.main:app`) と分かれ、real-server plug が「文書化された composition root をそのまま起動する」性質を r2db だけ失う。
- 各 run で worker ごとの受付数を記録する (launcher が子の access log を pid 付きで保存する。uvicorn の log 設定で pid を出す)。均等でなくてもよいが、4 worker すべてが受けたことを確かめる (裁定 17)。
- 429 が 1 件でも出た run は捨てる (現行どおり、`tools/perf_baseline.py`:2280-2281)。捨てた run は記録に残す (表 7-4)。
- K=1 の非退行 (`RM` §0.1.4 の 1) は N=1 と N=4 で記録する (裁定 17)。
- 実行順: peer ごとに N=1 の K=1 → K=32 → K=32、次に N=4 の K=1 → K=32 → K=32 (直列、他の pytest と nginx 無し。R-101 作業指示書 §10.2 の 1)。
- 後始末の照合: 各 run の後、`pg_database` / `pg_roles` の差分 0、launcher が起こした uvicorn (supervisor と子の全部。process group で数える) / nginx が残っていない (同 §10.2 の 4)。
- 推測: 開発機 10 core を server の N process、client 8 process、PostgreSQL が分け合う。

### 7.3 前提の算術 (計測の前に確かめる)

- 使い捨てクラスタの `max_connections` は 300 (`tools/testpg/dsa_testpg.py`:837)。
- 現行の式 (v0.2 の記述。D-3 (5) の改定前): F-18 の下限を既定 `concurrency` 32・登録 application ≥ 1 で数えると、P_data × 128 + P_control × 16。P_data = 4、P_control = 1 で 528 となり 300 を超える。P_data = 2 では 272。v0.2 の裁定 3 の b 基準 (4 × (16 + 16) + 16 = 144) は裁定 16 で覆した。
- **thread limit 基準 (裁定 16)**: P = 4、thread_limit 4、c = 2 → F-18 の下限は 4 × (2 × (4 + 2)) + 16 = 64 ≤ 300。計測は本番既定の 32 で行う (裁定 31。宣言値は接続予算に入らない。
- role の `CONNECTION LIMIT` に対する需要 (r2db): application の role (runtime / developer 各 36) は P × (4 + c) = 24。api role (68) は credential store と durable audit sink の 2 つの pool が同じ role なので (`main.py`:493、:502) P × 2 × (4 + c) = 48。どちらも収まる。
- MitateDB の role ごとの需要 (api role 132 に対する platform pool と audit sink の一時接続、application の role 68 に対する永続接続 × N) は作業指示書で数える (§9 (e))。
- **【v0.4、2026-09-28 (裁定 30)】rate の文の小実験 (WP-4 の前提)**: 使い捨て cluster で、同じ credential の 1 行に 32 並行の upsert (D-3 (1) の 1 文) を流し、1 文の p50 / p95 を取る。**0.2 ms/文を超えるなら監督に上げる (再裁定)**。
  - 0.2 ms の出所 (設計レビュー 1 回目の再確認、新 5 の算術): K=1 ≈ 2.25 ms + 往復なので、8 倍の上限は約 18〜20 ms。client の床 5.0 ms と worker あたりの直列区間 8 × 0.95 ≈ 7.6 ms で約 12.6 ms を使い、残りは約 6 ms。同じ bearer の 32 要求は全 worker をまたいで 1 行に並ぶので、32 本の直列で割ると 1 文あたり約 0.2 ms を超えると 8 倍を割る。
  - 前提: R-101 の計測は runtime bearer 1 本で `query` を送る (R-101 作業指示書 D-15) ので、K=32 の全要求が 1 行を取り合う。D-16 の 1 run は 18 group × 32 = 576 要求を送る (`tools/perf_baseline.py`:2155-2162 の group の送り方)。int[61] (裁定 34) の行は L に依らず固定長 (約 240 B) である (D-3 (1))。
  - 記録: 表 7-5。

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

**表 7-3 worker ごとの受付数 (N=4、裁定 17)**

| peer | run | worker 1 | worker 2 | worker 3 | worker 4 | 全 worker が受けたか |
|---|---|---|---|---|---|---|
| | | | | | | |

**表 7-4 捨てた run (429 が出た run、裁定 17)**

| peer | N | K | run | 429 の件数 | 捨てた理由 |
|---|---|---|---|---|---|
| | | | | | |

**表 7-5 rate の文の小実験 (32 並行の upsert、裁定 30)**

| peer | 文の数 | p50 (ms/文) | p95 (ms/文) | 0.2 ms/文以内 |
|---|---|---|---|---|
| | | | | |

## 8. 記録 (統合時、監督)

- 台帳 `RM` §8: R-113 (:533)、R-101 (:521)、R-18 (:438)、R-52 (:472) の各行に【追記】。行は消さない (`OPERATING_CONDITIONS.md` §1.8 の 56)。版上げは変更セットごと (同 §1.13 の 75)、版数ログの回転 (同 §1.16 の 78)。
- `security/CONTROL_MAPPING.md`: SI-08 の r2db の写像の主張 (:711-712)、MitateDB の写像の主張 (:904)、開示された限界の C-26 の行 (:988) を、区分 (ii) の置き場 (D-3) と新条件に合わせる。
- `conformance-tests/CONDITIONS.md`: C-05 (:34) の honest limits (6)、C-26 (:55)、新条件の行 (WP-1)。
- runbook: r2db `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (:96-106 の `declare-process-ceilings --data 1 --control 1` と単一 uvicorn の記述。`ExecStartPre=` の事前検査、`R2DB_WORKERS` の必須、SIGTTIN の禁止、1 host。**【v0.4】** 事前検査は preflight の entry (裁定 26)、`verify-declarations` の workers 検査は運用者の手動検査、`RuntimeDirectory=` と `R2DB_SLOT_DIR` (裁定 27))、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (接続予算を thread limit 基準に)。MitateDB `MitateDB-api/docs/cloud-run-cloud-sql.md` の Invariant 1 (:1327-1358。「in-process windows」「ceiling が 1 のときだけ honest」の記述) と §6.1 / §6.2 の `--max-instances` の値 (1 host、`--max-instances=1`、`--cpu` ≥ workers)。**【v0.4】** Dockerfile の slot directory と `MITATEDB_SLOT_DIR`、`CMD` の preflight (裁定 26・27)、Cloud Run が一時的に max-instances を超えうる件の 1 行 (「推測」を明記。裁定 33)。
- `tools/PERF_BASELINE_README.md`: `--workers`、計測時の `concurrency` 64、worker ごとの受付数。 **【v0.4】**「計測時の `concurrency` 64」は裁定 31 で覆す (本番既定の 32 で計測する旨を書く)。
- **【v0.4】** 台帳 R-52 行の【追記】には §9 (p) (Cloud Run の revision の重なりで 2 host になる間は slot が共有されない) を含める (裁定 25・33)。
- 設計メモ `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md` か本書に §7 の実測 (置き場は作業指示書で決める)。
- **起票文案 (裁定 13。台帳の行の形。番号は起票時に確定し、それまで「(次番)」と呼ぶ)**:

```text
| **(次番)** | **規模 S — 契約の記述 1 文と実装の食い違い (Class C の文言)。着手条件: 印なし。** **`spec/data-service-api.v1.json`:925 は `audit_requests_per_minute` を "pre-authentication fixed window" と定めるが、両 peer の現物は sliding window である** (r2db `r2db-api/src/r2db_api/control_plane.py`:1421-1435、MitateDB `MitateDB-api/src/mitatedb_api/control_plane.py`:1344-1358)。R-113 より前からの契約と実装の食い違い。sliding は fixed より緩くならないので client の不利は無いが、契約の記述が実装と違う。起票の 2 問 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.15 の 77): (a) 検査器の穴ではない、(b) 契約の記述を読む client が窓の境目の挙動を誤って計画しうる = 気づく。 | **起票 (日付は起票時)** (R-113 設計 `docs/design/MULTI_PROCESS_WORKER_V0_1.md` v0.3 §10 の裁定 13)。R-113 では直さない。 |
```

## 9. レビューで確かめてほしい点

**(a) 静的分割で 1.8.0 の「bound holds across every process」が真になる論証。** **【v0.3】裁定 10 で解けた (静的分割を撤回。host 共有の slot では宣言値 L がそのまま 1 host 全体の上限になる)。**
- 論証: plane p を同時に serve する process は P_p 以下 (宣言と runbook 規律、条件 7)。各 process は `concurrency` を同時に b = ⌊L/P_p⌋ まで、rate を自分の 60 秒窓で b まで通す。よって配備全体の同時数・任意の 60 秒の数は ≤ P_p × b ≤ L (L ≥ P_p のとき)。`requests_per_minute` は credential・窓ごとに 1 行を全 process が共有するので、process 数に依らず窓ごとに ≤ L。
- 確かめてほしいこと: 切り捨て規則 (最小 1) の境界で合計が宣言値以下に収まるか。公開する `limits` が L のままで、process 1 本あたり b で拒否することが C-05 V2 (宣言値と実拒否位置の一致、ceiling 1 で駆動) と両立するか。

**(b) fixed window 行の UPDATE の競合と role の最小権限。** **【v0.3】行の形・作成・接続・権限・時計・回収・失敗時は裁定 15 で解けた (D-3 (1))。残る問いは (m) に移した。**
- 同じ credential の要求は全 process で 1 行に集まり、行 lock で直列化する。R-101 の計測は runtime bearer 1 本で `query` を送る (R-101 作業指示書 D-15) ので、K=32 の全要求が 1 行を取り合う。推測: 行 lock の保持は 1 文の間だけ。
- 行の作成 (credential の初回・窓の切り替わり) を 1 文で原子的に行う形 (`UPDATE ... RETURNING` だけで足りるか)。
- どの role (r2db `r2dbsvc_api` / MitateDB `mitatedbsvc_api` か別の role か) がどの pool で UPDATE するか。その role に新表以外の権限を足さないこと。revoke 済み credential の行の後始末。
- 窓の時刻を DB の時計と process の時計のどちらで決めるか (process ごとに時計がずれると窓の境目がずれる)。

**(c) `process_ceilings` と実 process 数の不一致。**
- 宣言 P < 実 M: pre-auth 3 class の合計は M × ⌊L/P⌋ で L を超え、`enforced` が偽になる (現行の「宣言 1・実 >1」と同じ種類の破れで、緩み幅は M/P 倍)。`requests_per_minute` は PG の行で保たれる。F-16 / F-18 も宣言 P で数えるので接続を少なく見積もる。
- 宣言 P > 実 M: bound は保たれ、利用率が M/P に落ちる。
- 不一致の入口: `--workers` の値、`WEB_CONCURRENCY` (`--workers` 無しでも読まれる、`uvicorn/config.py`:352-353)、Cloud Run の instances。SIGHUP の `restart_all` は一時的に N+1 本にする (`uvicorn/supervisors/multiprocess.py`:173-194)。
- 一致を担うのは runbook 規律と配備後チェック (フェーズ10 設計 L10-2、条件 7)。
- **【v0.3】** 静的分割の撤回 (裁定 10) で、宣言 P < 実 M でも同じ host 上なら `concurrency` は host 共有の slot で ≤ L に保たれ、`requests_per_minute` は PG の行で保たれる。破れるのは接続予算 (F-16 / F-18 が宣言 P で数える) である。
- 入口の追加 (裁定 11): SIGTTIN を受けた supervisor は稼働中に子を 1 本増やす (`uvicorn/supervisors/multiprocess.py`:267-272)。runbook で禁じる。`WEB_CONCURRENCY` は `--workers` を常に明示すれば読まれない (D-1)。
- 開示 (裁定 21): `verify-declarations` が読む値 (L_c と workers の env) は自分の process の env である。api の process の env と一致している限りでしか効かない。 **【v0.4】** 起動時の検査としては裁定 26・27 で解けた (preflight と各子は service 自身の env を読み、workers ≤ ceiling は `build_app()` の中で検査する)。`verify-declarations` の同じ検査は運用者の手動検査に残り、この限界も残る。

**(d) rollout の重なり (R-52) で保たれないもの。**
- 旧と新の revision が同時に serve すると、process は最大 2P になる。pre-auth 3 class の合計は最大 2L になり保たれない。`requests_per_minute` は共有の行なので保たれる。
- 重なりの process 数を `process_ceilings` に宣言すれば、分割の分母と F-18 の下限がその数を数える (`security/CONTROL_MAPPING.md`:962)。代わりに平常時の 1 process の分け前が半分になる。
- r2db の systemd の再起動で重なりが生じるか。推測: `Type=simple` の restart は停止の後に起動するので重ならない (`r2db-api/deploy/systemd/r2dbsvc-api.service`:39)。
- **【v0.3】** 上の 2 行は静的分割 (v0.2) の下での記述である。v0.3 の置き場では次のとおり (推測を含む): `requests_per_minute` は共有の行なので保たれる。`concurrency` は、旧と新の process が同じ host で同じ slot directory を使うなら保たれ、別 host (Cloud Run の revision が別 instance に載るとき) なら最大 2L になる。control の 2 class は process 内なので、control plane の旧と新が重なれば最大 2 倍になる。

**(e) MitateDB の cell 永続接続 × N の接続予算。**
- application ごとの永続接続 (`backend_postgres.py`:294) は process ごとに 1 組で、N process なら N 組。application の role の `CONNECTION LIMIT` は 68 (`0014`、並走 2 前提)。
- platform の api role は process ごとに platform pool (`main.py`:349) と audit sink の一時接続を持つ。F-18 は `process_ceilings.data` を掛けるが (§3 D-3 の (4))、F-16 は 1 process 分だけを床にする (`main.py`:411)。api role の `CONNECTION LIMIT` 132 に対する N process の需要。
- r2db も同じ問い: role pool の最大は `concurrency` (`r2db-api/src/r2db_api/limits.py`:121-) で、role の `CONNECTION LIMIT` は application 36・api 68 (`0013`)。静的分割で 1 process の同時数が b になるとき、pool の最大を L のままにするか b にするか。
- §7.3 の F-18 の算術 (P_data = 4 で 528 > 300) を計測の前提としてどう満たすか。
- **【v0.3】** pool の寸法 (L のままか b か) と §7.3 の算術は裁定 16 で解けた (thread limit 基準)。MitateDB の application ごとの永続接続 × N と、api role に対する platform pool と audit sink の一時接続の需要は作業指示書で数える。

**(f) 新条件 (a) の保持の手段。** **【v0.3】裁定 14 で解けた (launcher の特権接続の `LOCK TABLE` で保持する)。**
- `hold_in_flight` は adapter の port で (`conformance-tests/adapter.py`:1742-)、stall 点は concurrency の取得の後・DB 実行の前にある。launcher が起動する本番の composition root の子 process に同じ保持の手段があるか。

**(g) 新条件 (b) の空振り禁止。** **【v0.4】裁定 32 で解けた (波に分けて 2L 本、200 の pid が 2 種以上を主張に含める。D-4)。**
- supervisor の 1 socket を子が共有するので、どの子が要求を受けるかは OS が決める。要求が 2 つの子に実際に分かれたことを観測する手段 (`OPERATING_CONDITIONS.md` §1.5 の 32)。
- **【v0.3】** 新条件 (a) の分散は `application_name` の pid で観測する (裁定 14)。新条件 (b) の要求は短く `pg_stat_activity` の瞬間には現れにくいので、2 つの子に分かれたことを何で観測するか (子の access log の pid (裁定 17) を使えるか) を確かめてほしい。

**(h) 写像の入力から `process_ceilings` が外れること。** **【v0.3】裁定 18 で解けた (配線されていない構成では `process_ceilings` が写像の入力に残る)。**
- 写像は ceiling に依らなくなり (§3 D-3 の (3))、ceiling は分割の分母と接続予算に残る。フェーズ10 設計 D-5 (ii) の「壊すとどう見えるか」(`DP10`:241、写像を「常に `enforced`」に固定すると C-26 (4) が赤) の前提が変わる。

**(i) slot 探索の O(L) の費用。** **【v0.4】裁定 29 で解けた (要求ごとの open / close、最適化は採らない)。**
- 満杯に近いとき、1 要求が最大 L 回の open と `flock` を event loop の thread で行う (L = 32、計測時 64)。拒否の経路 (全部塞がっている) は必ず L 回である。fd を process 内で開いたまま持つか、要求ごとに開くかで費用が変わる。K=1 の非退行 (§7.2) に効くか。
- **【v0.4】数字 (裁定 29)**: 拒否の経路 (全部塞がっている) は L 回の open / flock / close = 3L 回の syscall で、L = 32 なら 96 回を認証の前に event loop で行う。空きがあれば、始点の slot が空いている限り 3 回 (open / flock / close) で済む (K=1 はこの場合)。計測時の宣言値 64 は裁定 31 で取り下げたので、計測でも L = 32。

**(j) slot directory の置き場と権限。** **【v0.4】裁定 27・28 で解けた (env で明示・既定なし・配備側が 0700 で作る・`build_app()` は検査だけ・ファイルは `O_CREAT | O_NOFOLLOW | O_CLOEXEC` の 0600。D-3 (2'))。**
- r2db の unit は `ProtectSystem=strict` (`r2db-api/deploy/systemd/r2dbsvc-api.service`:82) と `PrivateTmp=true` (:109) を持ち、`RuntimeDirectory=` が無い (§1.4 の (5))。systemd の `RuntimeDirectory=` で置くか。`UMask=0077` (:126) の下で同じ user の子だけが開ける。
- MitateDB の container は `USER mitatedb` (`MitateDB-api/docker/Dockerfile`:134) で、container の tmp に置くか。
- slot ファイルを誰が作るか (事前検査か、helper が `O_CREAT` で作るか)。宣言値 L を変えたときに余った slot ファイルが残っても bound が崩れないか。 **【v0.4】** ファイルは helper が `O_CREAT` で作る (directory は配備側)。r2db の `RuntimeDirectory=` は停止で消えるので古いファイルは残らない (設計レビュー 1 回目の再確認の新 3)。helper は `slot-0` 〜 `slot-<L-1>` だけを試すので、L を下げたときの余ったファイルは数に入らない (推測: 探索の範囲が L で決まる限り)。

**(k) flock の継承と thread 間の排他。** **【v0.4】裁定 28・29 で解けた (起動時の自己検査が模倣 flock と syscall filter を捕らえる、EPERM 等は fail-closed、fd は要求ごとで process 内で共有しない)。**
- spawn の子が slot の fd を共有しないこと。事実: fd は既定で継承不可で、`multiprocessing` の spawn は明示した fd だけを渡し、supervisor は app を読み込まない (§1.4 の (4))。supervisor か事前検査が slot の fd を開いたまま子を起こす経路が無いことを確かめてほしい (fork / dup で共有された lock は 1 つの lock への複数の参照になる、darwin の flock(2))。
- 同じ process の 2 thread が同じ slot を別々に開いたとき、2 本目の `LOCK_EX | LOCK_NB` が拒まれること (推測、§1.4 の (4))。`fcntl.flock` が fcntl() で模倣される環境では lock が process 単位になり、同じ process 内で二重に取れる恐れがある (本番の `HAVE_FLOCK` は未確認)。
- r2db の unit の `SystemCallFilter=@system-service` (:141) が `flock` を許すこと (推測: 許す。未確認)。
- **【v0.4】** preflight は `ExecStartPre=` (r2db) / `CMD` の前段 (MitateDB) の別 process で、uvicorn の起動の前に終わる。slot の fd を持ったまま子を起こす経路にはならない (推測: 別 process が終わるので fd は残らない)。

**(l) `application_name` の長さ制限。** **【v0.4】裁定 33 で閉じた (`"<peer>:<plane>:<pid>"` は約 25 byte)。**
- PostgreSQL の `application_name` は 63 bytes を超えると切り詰められる (推測: NAMEDATALEN − 1。本書では未確認)。`"<peer>:<plane>:<pid>"` が収まること。

**(m) rate 行の配列 UPDATE の費用 (L = 600)。** **【v0.4】裁定 30 で解けた (int[60] + 基点の秒で費用は L に依らない。1 文の費用は §7.3 の小実験で測り、0.2 ms/文を超えれば再裁定)。**
- 1 文ごとに最大 600 要素の配列を走査して作り直す。推測: 600 個の `timestamptz` (約 4.8 KB) は TOAST の閾値を超え、更新ごとに行の外の値を書き直す。
- 同じ credential の要求は全 process で 1 行に集まり、行 lock で直列化する。R-101 の計測は runtime bearer 1 本で `query` を送る (R-101 作業指示書 D-15) ので、K=32 の全要求が 1 行を取り合う。行 lock の保持は 1 文の間だけ (autocommit、D-3 (1))。D-16 の比に効くか。

**(n) thread limit 基準の pool と C-05 V2 の「実拒否位置 = 宣言値」の両立。**
- C-05 V2 は `concurrency` を宣言値まで in-flight にして、宣言値 + 1 本目で拒否されることを見る。pool が thread limit + c のとき、thread を待つ要求は slot を持ったまま pool を借りないので、宣言値の手前で 503 にならない (推測)。C-05 V2 の保持点 (`hold_in_flight`、`conformance-tests/adapter.py`:1742-) が pool の接続を持ったまま止まる構成が無いことを確かめてほしい。

**(o) 新条件 (a) の「保持中の本数」の数え方。** **【v0.4 で記す】裁定 23 で解けた (client 側で数え、`pg_stat_activity` は worker の分散の観測にだけ使う)。**
- `LOCK TABLE` で止まった要求が `pg_stat_activity` に現れるのは、thread を得て DB に達した分 (worker あたり最大 thread limit) だけである (§1.4 の (2))。thread を待つ要求は slot を持つが DB に現れない。よって「保持中の本数 = L」は client 側 (応答が返らない数) で数え、`pg_stat_activity` は worker の分散の観測に使う形になる、と読んだ。この読みでよいか。

**(p) Cloud Run の revision の重なりと 1 host。** **【v0.4】裁定 25・33 で R-52 の射程とした (台帳 R-52 行に【追記】、§8)。Cloud Run が一時的に max-instances を超えうる件は推測 (現物未確認) のまま runbook の開示に 1 行 (§5 Q-4)。**
- `--max-instances=1` でも revision の切り替えで旧と新の instance が同時に serve しうる ((d))。この間は 2 host になり slot が共有されない。R-52 の射程として扱うか。

**(q) F-1 の条件 (§1.4 の (1))。** **【v0.4】条件 (ii) は裁定 33 で確かめた (同じ受け手から入れ子で借りる箇所は AST 走査で 0 件)。新しい rate の文は認証で借りた接続を返した後に借りることを作業指示書の完了条件に置く。条件 (i) (pool は実効 thread limit から導く) は WP-2 / WP-3 のまま。**
- 1 つの同期区間が同じ pool から同時に 2 本借りない (未確認)。借りるなら、その区間の分だけ c を足す必要がある。
- pool の寸法を実効 thread limit (env 上書き後) から導くこと。thread limit だけを上げて pool が追随しないと F-1 の形 (宣言値の手前の 503) が戻る。

**(r) preflight の cell の eager open と close の副作用 (v0.4)。**
- preflight は `build_app()` を 1 回余分に走らせ、served application の cell (r2db の `PostgresCell`、MitateDB の `PostgresBackend` の永続接続) を開いて閉じる (D-2)。DB 側に残るもの (接続の開閉、F-12 の log 1 行) が「読み取りか process 内資源」の範囲に収まるか。cell の close の経路が両 peer に在るか (無ければ entry が何を閉じるか)。
- slot の自己検査 (D-3 (2')) に使うファイル: slot ファイル (`slot-<i>`) を使うと、rolling restart の間に新しい子の検査が稼働中の要求と 1 本の slot を瞬間的に取り合う。専用のファイルを使うと slot の数には入らない。どちらでも自己検査の目的 (同じ process の 2 本目が拒まれること) は満たすか。

**(s) int[60] の境目の数え方の正しさ (v0.4)。**
- 裁定 30 は「境目の 1 秒を多めに数えるので上限を超えて通すことが無い」とする。60 s の sliding 窓 (現在の時刻から 60 s 前まで) は、時刻が秒の途中なら整数秒の境で 61 個の秒にまたがる。60 個の計数と基点の秒の進め方 (どの秒の計数をいつ 0 に落とすか) で、どの時刻の要求も 60 s 以上数えに残ることを確かめてほしい (残らない時刻があれば、窓の中の要求を数え落として L を超えて通しうる)。
- DB の時計の秒が基点より戻ったとき (時計の調整) の扱い。

**(t) C-26 (4) の ceiling 2 の起動形の workers の値 (v0.4)。**
- 裁定 27 の写像では、ceiling 2 の起動を workers 1 で行うと `deployment_required`、workers 2 で行うと `enforced` になる (D-4)。裁定 12 の分岐の `enforced` の側 (新条件 (a)(b) を課す側) を両 peer で観測するには、C-26 (4) の ceiling 2 の起動を workers 2 で行う必要があるか。現行の launcher は data・control 各 1 本を起動する (`r2db-api/conformance/real_server_r2db.py`:667-677)。

**(u) workers = ceiling の等式が rolling restart の間に破れるときの写像 (v0.4)。**
- SIGHUP の `restart_all` は子を 1 本ずつ置き換え、その間だけ子は N + 1 本になる (§1.3、`uvicorn/supervisors/multiprocess.py`:173-194)。写像の入力 (env の workers と宣言の ceiling) は変わらないので `enforced` のままである。この間、`concurrency` は同じ host の同じ slot directory で L に保たれ、`requests_per_minute` は PG の行で保たれる、と読んだ。破れるのは接続予算 (N + 1 本目の pool が F-16 / F-18 の見積りの外) だけか。runbook に SIGHUP の扱いを書くか (SIGTTIN は禁じた、裁定 11)。

## 10. 監督裁定 (v0.2、2026-09-28。起草の疑義に対する裁定。本文と食い違うときは本節が優先する)

1. **契約の文言との衝突 (起草の疑義 1、重大)。** `spec/data-service-api.v1.json`:905 (`limits.profile`) は「a bound kept in per-process memory is enforced for the deployment only while exactly one process serves that base URL」、:303 (`capability_status.rules`) は「declares deployment_required when the bound is held per process and more than one process may serve」と言う。静的分割 (D-3 の (2)) は process 内メモリで数えるので、この 2 文を文字どおりに読むと `enforced` と宣言できない。1.8.0 の義務の趣旨 (bound が全 process にわたって成り立つ) は分割で満たされるが、文言は満たさない。**裁定: Q-1 の (A) と (C) は契約の文言の明確化を伴う = 契約 1.12.0** (従属判断 17: 「宣言値 L を process 数 P で分割し、各 process が ⌊L/P⌋ を超えて通さない bound は、同時に serve する process が P 以下である限り全 process にわたって成り立つので `enforced` である。`deployment_required` は各 process が宣言値 L そのものを独立に持つときに限る」の趣旨で :303 と :905 を改める。義務の追加も client の送るものの変更も無い)。手順はフェーズ9 / 10 と同じ (契約 JSON + companion + obligations entry + `spec/CCR_DISPOSITION.md` + catalog 再生成 + 3 複製 byte 一致 + pair-closing の版フリップ)。**(B) だけが契約に触れない。** 従って設計レビューは (A)(C) で 2 回、(B) で 1 回 (`OPERATING_CONDITIONS.md` §1.7 の 50)。D-6 と §0 はこの裁定で読み替える。§6 の WP 分割は (A)(C) のとき契約 WP を conformance WP の前に置く。 **【v0.3、2026-09-28】裁定 10 で覆す (静的分割の撤回により契約 1.11.0 不変、1.12.0 は不要)。**
2. **切り捨て規則の「最小 1」は撤回する (疑義 2)。** b_c = ⌊L_c / P_p⌋ とし、分割対象のどの class でも L_c < P_p なら **起動時 fail-fast** (F-15 と同じ扱い。`ops verify-declarations` にも同じ検査を足す。番号は作業指示書で採番)。理由: 最小 1 では合計が P_p になり L_c を超える (§9 (a) の論証は L_c ≥ P_p を前提にしており、その前提を検査で保証する)。 **【v0.3、2026-09-28】裁定 10 で覆す (分割が無くなるので L_c < P_p の fail-fast も撤回)。**
3. **pool の寸法と接続予算は分け前 b で数える (疑義 6、§9 (e)、§7.3)。** 静的分割のとき、1 process の pool の最大は b (`concurrency` の分け前) とし、F-18 の下限の `2 × concurrency` は `2 × b` に、F-16 (role の `CONNECTION LIMIT` の床) は P_data × (1 process の pool 構成) に改める。こうすると総需要は P × 2b ≤ 2L で現行 (1 process、2L) と同じ水準に収まる。§7.3 の算術は b で数え直す: P_data = 4、`concurrency` 32 → b = 8、下限 = 4 × (16 + 16) + 16 = 144 ≤ 300 (使い捨てクラスタ)。**D-5 の N=4 の計測はこの改定の後に行う** (改定前は 528 で起動時に落ちる = 起草の指摘のとおり)。MitateDB の application ごとの永続接続 (× N) は role の `CONNECTION LIMIT` (application role 68、並走 2 前提) の中で N ≤ 4 まで収まるかを作業指示書で数える。 **【v0.3、2026-09-28】裁定 16 で覆す (接続予算は thread limit で数える)。**
4. **control plane は workers を足さない (疑義 7)。** `--workers` は data plane だけ。P_control は宣言のまま (既定 1)。分割の仕組みは class 一般に書き、control の 2 class は P_control = 1 なら b = L で現行と同じ値になる。MitateDB の Dockerfile CMD (data / control が 1 行を共有) は SERVICE ごとの workers 変数にする (control は 1 固定)。`control_main` の startup 副作用の列挙は不要 (process 数を変えない)。 **【v0.3、2026-09-28】分割に関する文は裁定 10 の撤回に従う (control の 2 class は現行のまま)。control plane に workers を足さない点は残る。**
5. **窓の形の事実 (疑義 8)。** control / audit の窓は現物では sliding であり、分割は窓の形を変えない (上限値だけが b になる)。fixed への変更の可否 (Q-2) は `requests_per_minute` (PG の行) にだけ掛かる。
6. **事実の訂正 (疑義 8)。** R-80 の MitateDB は platform 4 tx/req (`RM`:500。枠の「5 tx」は誤り)。runbook の Invariant 1 は `MitateDB-api/docs/cloud-run-cloud-sql.md`:1327 から。MitateDB の次の platform 単発 migration は `0016`、r2db は `0015` (本文のとおり)。
7. **新条件の番号 (疑義 3)。** 本書では「新条件」と呼び、番号は conformance WP で採番する (`tools/check_doc_refs.py` が未存在の C-NN を参照切れとして止めるため)。
8. **新条件 (a) の保持の手段 (疑義 4、§9 (f)) は設計レビューに問う。** 監督の前提: 本番の composition root に test 用の stall フックを足さない。候補は (i) 本番の要求だけで in-flight を作る (`execution_ms` 内で時間の掛かる `query` を L + P 本同時に送り、`concurrency` の LIMIT_EXCEEDED を少なくとも 1 件観測する) と (ii) 共通条件では `requests_per_minute` の process 間の bound (新条件 (b)) だけを観測し、`concurrency` の分割は peer-local の実 PG テスト (2 worker を起動して b で拒否) で pin する。裁定はレビュー後。 **【v0.3、2026-09-28】裁定 14 で決めた ((iii) launcher の特権接続の `LOCK TABLE`)。**
9. **`build_app()` の例外が子 process の `STARTUP_FAILURE` になる経路 (未確認)。** 作業指示書の実装 WP で現物 (uvicorn `supervisors/multiprocess.py`) を読んで確かめ、結果を D-2 に【追記】する。設計は「子の起動失敗は supervisor が全体を止める」を前提にしない (F-15 の fail-fast が 1 process のときと同じ観測可能性で残ることを要求する)。 **【v0.3、2026-09-28】設計レビュー 1 回目の指摘 1 で確かめ、D-2 に【追記】した (裁定 11)。**

### 監督裁定 10〜22 と Q-1 の書き換え (v0.3、2026-09-28。設計レビュー 1 回目への裁定。逐語)

- 逐語の例外は 1 箇所: 裁定 13 の台帳行の番号は、`tools/check_doc_refs.py` が定義の無い R 番号を参照切れとして止めるので「(次番)」と書く。

```text
## 裁定 10 (指摘 2 = 設計の芯) 静的分割は撤回する。`concurrency` は host 内の全 worker で共有する OS の file lock の slot にする
- 事実: b = ⌊L/P⌋ の分割では、K=32 の一斉送信が 4 worker に 8/8/8/8 に分かれる確率は 0.54% で、本番でも宣言 32 のうち 9〜20 本目で 429 が出る。宣言値を読んで計画する AI client (前提: client は宣言を読む) に見える欠陥であり、計測 (D-16) も完走しない。
- 決定: `concurrency` の admission slot を **host 内で共有する**。仕組み = 宣言値 L 本の slot ファイル (runtime directory、`<plane>/slot-<i>`) を置き、in-flight の要求 1 本が `fcntl.flock(LOCK_EX | LOCK_NB)` で slot 1 本を握る (乱数で始点を選び L 本を順に試し、全部塞がっていれば LIMIT_EXCEEDED)。解放は fd の close で、process が死ねば kernel が解放する (crash 安全)。DB 往復なし (条件 5)。stdlib のみ (`fcntl` は darwin / linux に在る)。両 peer 同型の helper 1 つ (`_ISOMORPHIC_TARGETS` に登録)。
- 射程: 共有は 1 host (1 composition root の worker 群) に閉じる。**base URL を serve する process は 1 host に置く** (条件 7 の runbook 規律に「1 host」を足す。Cloud Run は `--max-instances=1` のまま `--workers` と `--cpu` で伸ばす = Q-4 の監督案を (B) に改める)。複数 host は本件の範囲外 (宣言 `process_ceilings` は process 数であり host 数を持たない。複数 host にするときは `deployment_required` を宣言するか、共有 limiter を PG に置く R-18 (c) の続きで別起票)。
- 帰結: 宣言値 L はそのまま 1 host 全体の上限として届く (利用率の損失なし)。1.8.0 の :303「bound holds across every process」は 1 host の全 process で真、:905「per-process memory」に当たらない (kernel が持つ)。**契約 1.11.0 不変 = 1.12.0 は不要**。裁定 1 (1.12.0) は本裁定で覆す。裁定 2 (L < P の fail-fast) は分割が無くなるので撤回 (control plane の 2 class は裁定 4 のとおり現行のまま)。
- 却下 (§4 に足す): 静的分割 (上記の欠陥)、PG の共有 counter (crash で漏れる / pre-auth 往復)、POSIX 名前付き semaphore (依存 `posix_ipc` を足す)、`multiprocessing` の semaphore (uvicorn の spawn 子に渡せない)、nginx `limit_conn` (429 の envelope を app が出せない / Cloud Run に nginx が無い)。
- 壊すとどう見えるか: slot を process 内に戻すと、2 worker で L を超えて in-flight になり新条件 (a) (裁定 14) が赤になる。`LOCK_NB` を外すと満杯時に待ちになり (429 が出ない) C-05 V2 が赤になる。

## 裁定 11 (指摘 1) 宣言の検査は worker を起こす前に親側で 1 回走らせる
- r2db: systemd の `ExecStartPre=` で `ops verify-declarations` (F-15 は exit 14) を走らせる。MitateDB: Dockerfile CMD で `exec uvicorn` の前に同じ CLI を置く。uvicorn の supervisor は `build_app()` の例外を持つ子を置き換え続け、親は 0 で終わる (レビューの現物確認: uvicorn `supervisors/multiprocess.py:218-239`、`main.py:628-629`) ので、fail-fast の観測可能性は親側の事前検査が担う。 【v0.4、2026-09-28】事前検査の手段 (`ops verify-declarations`) は裁定 26 で覆す (preflight の one-shot に改める。親側で事前検査を走らせること自体は残る)。
- `verify-declarations` に足す検査: `--workers` の値 (env `R2DB_WORKERS` / `MITATEDB_WORKERS`) ≤ `process_ceilings.<plane>` (指摘 11)。`--workers` は 1 のときも常に明示し、env に必須で置く (`WEB_CONCURRENCY` の入口を閉じる)。SIGTTIN による増員は runbook で禁じる (§9 (c) に足す)。 【v0.4、2026-09-28】起動を止める workers ≤ ceiling の検査は裁定 27 で `build_app()` に移す (`verify-declarations` への追加は運用者の手動検査として残す、裁定 26)。
- C-26 (5) は launcher の `workers ≥ 2` の起動形 (事前検査 → uvicorn) でも fail-fast (非 0 終了と F-15 の文言) を観測する。裁定 9 の「現物で確かめる」は指摘 1 で済んだので D-2 に【追記】。

## 裁定 12 (指摘 3) conformance は宣言と実際の bound の一致を見る ((甲) を採る)
- C-26 (4) は「ceiling 2 で `enforced`」を要求しない。改訂後の C-26 (4): ceiling 1 → `enforced`、ceiling 2 → **宣言が `enforced` と `deployment_required` のどちらでもよい**が、`enforced` を宣言した peer には新条件 (a)(b) を課す (宣言で分岐。C-30 の版分岐と同じ形)。`deployment_required` を宣言する peer は現行どおり適合。義務の追加は無い (契約不変と整合)。両 peer は `enforced` を宣言する (D-3)。

## 裁定 13 (指摘 4) 契約の文言は変えない (裁定 10 の帰結)。(c) の :925 は起票する
- (a)(b) は分割の撤回で消える (`details.limit` は L のまま)。
- (c) `spec/data-service-api.v1.json:925` は `audit_requests_per_minute` を "pre-authentication fixed window" と定めるが、現物 (両 peer) は sliding window。本件より前からの契約と実装の食い違い。本件で直さず **(次番) (規模 S、Class C の文言。sliding は fixed より緩くならないので client の不利は無いが、契約の記述が実装と違う) として起票**する (起票の 2 問: (a) 検査器の穴ではない、(b) 契約の記述を読む client が窓の境目の挙動を誤って計画しうる = 気づく)。

## 裁定 14 (指摘 5) 新条件 (a) は launcher の特権接続の `LOCK TABLE` で要求を保持する ((iii) を採る)
- 本番コードに stall フックを足さない。launcher (両 `real_server_*.py`) に port「entity の保存先を PostgreSQL の lock で保持する」を足す (自前の特権接続で `LOCK TABLE … IN ACCESS EXCLUSIVE MODE`)。保持時間は `execution_ms` と role の statement_timeout より短くする。
- 主張: workers = 2 の起動形で L + P 本 (以上) を同時に送り、429 を除いた「保持中の本数」が **ちょうど L** であること、かつ保持中の要求が **2 worker 以上に分かれている**こと (§9 (g) の非空振り)。worker の識別は各 worker の PostgreSQL 接続の `application_name` に process id を含める (両 peer の接続工場で `application_name = "<peer>:<plane>:<pid>"`。`pg_stat_activity` で launcher が数える) — これは本番にも残る観測性の改善であり、テスト用フックではない。
- 変異: slot を process 内に戻す → 保持 2L で赤。L+1 本目が通る → 赤。

## 裁定 15 (指摘 6・7) `requests_per_minute` の PG の行は sliding window の 1 文とする (Q-2 は監督裁定で閉じる = 現行の意味を保つ)
- 1 credential 1 行 (`credential_id`, `stamps timestamptz[]`)。1 文: `INSERT … ON CONFLICT (credential_id) DO UPDATE SET stamps = (期限切れを落とした配列 || clock_timestamp()) WHERE cardinality(期限切れを落とした配列) < L RETURNING …` (通らなければ LIMIT_EXCEEDED)。窓は DB の時計 (`clock_timestamp()`)。fixed window の境目の flake (C-05 V2、新条件 (b)) と 2L の突発は起きない。配列の上限は L (既定 600)。
- 接続: 既存の api role の pool (r2db は credentials pool、MitateDB は platform pool) の **autocommit 1 文**。要求の tx には入れない (行 lock を要求の終わりまで持たない)。application role に platform 表の権限を足さない。api role には新表の INSERT / UPDATE (と SELECT) だけ。
- 失敗時: fail-closed (DB の失敗は既存の DB 失敗と同じ写像で拒否。素通ししない)。
- 回収: revoke 済み credential の行は credential の削除に連動 (FK ON DELETE CASCADE)。1 credential 1 行なので増えない。
- 計数用の pool を新設しない (F-16 の需要を増やさない)。

## 裁定 16 (指摘 2 の後半・裁定 3 の改定) 接続予算は thread limit で数え、L に比例させない
- WP-3 (R-101) 以降、1 process が同時に DB を使う数は thread limiter (既定 4) で抑えられる (DB 仕事は threadpool の中。event loop 側の DB 使用が無いことを起草で現物確認し、あれば列挙する)。1 process の pool の最大は **thread limit + 定数** (audit flush thread、platform 1 文) とし、F-18 の下限は P × (2 × (thread_limit + c)) + control 分、F-16 は P × (1 process の pool 構成) とする。宣言値 L (`concurrency`) は接続予算に入らない (slot は接続を持たない)。
- 算術 (§7.3): P=4、thread_limit 4、c=2 → 4 × 12 + 16 = 64 ≤ 300。r2db api role 68・application role 36 に対する需要も P × (4 + c) で収まる。
- 裁定 3 は本裁定で覆す。

## 裁定 17 (指摘 2、§7) 計測の固定事項
- launcher の env で計測時の `concurrency` を **64** に宣言する (K=32 の一斉送信が slot の解放の遅れ (応答送信後の `finally`) で 429 を踏まないため。宣言値は接続予算に入らないので他に影響しない)。本番既定は 32 のまま。理由と値を §7.2 に固定する。 【v0.4、2026-09-28】裁定 31 で覆す (計測は本番既定の 32。理由の前提が現物と違う)。本裁定の他の項は残る。
- 各 run で worker ごとの受付数を記録する (launcher が子の access log を pid 付きで保存。uvicorn の log 設定で pid を出す)。均等でなくてもよいが、4 worker すべてが受けたことを確認する。
- 429 が 1 件でも出た run は捨てる (現行どおり)。捨てた run は記録に残す。
- 判定規則 D-16 の逐語は変えない。K=1 の非退行 (§0.1.4 の 1) は N=1 と N=4 で記録する。

## 裁定 18 (指摘 8) 写像は「共有の仕組みが配線されているときだけ ceiling に依らず `enforced`」
- `requests_per_minute` は PG の行が配線されているとき、`concurrency` は slot directory が配線されているとき、それぞれ ceiling に依らず `enforced`。in-memory の窓 / counter (in-process plug、PG の無い構成) は現行の写像 (ceiling ≥ 2 で `deployment_required`) のまま。2 つの戦略を両 peer 同型の helper にする。 【v0.4、2026-09-28】`concurrency` の部分は裁定 27 で覆す (配線 かつ `process_ceilings.data` ≤ workers のときだけ `enforced`)。`requests_per_minute` の部分は残る。

## 裁定 19 (指摘 9) launcher は supervisor を process group で起動し、停止は killpg、pidfile に子の pid も記録し、孤児掃除の対象に足す (WP-1 の範囲に明記)。

## 裁定 20 (指摘 10・Q-4) Q-4 の監督案を「(B) instance は 1 のまま `--workers` と `--cpu` で伸ばす」に改める。(C) の側に autoscaling の算術 (縮退時に宣言値に届かない) と `--cpu ≥ workers` を書く。依頼者判断のまま置く。

## 裁定 21 (指摘 12・13) D-2 の表に「supervisor の SIGKILL 経路では lifespan の最終 flush が走らない (1 process には無い経路。起こりにくい: 両論)」を足す。出所の行番号を訂正 (CONTROL_MAPPING :711-712 / :903 / :989)。`verify-declarations` の L_c は自 process の env を読む限界を §9 (c) に開示。§4 の nginx の却下理由に pre-auth 3 class 分を足す。 【v0.4、2026-09-28】本裁定の行番号 (:903 / :989) はレビュー担当の誤りで、本文の :904 / :988 が正しい (裁定 33 の註。逐語は書き換えない)。

## 裁定 22 (クラス) Class **D** (`security/CONTROL_MAPPING.md` の SI-08 の主張を改める、`_ISOMORPHIC_TARGETS` の増減)。契約不変なので設計レビューは 1 回 + 本裁定の反映の再確認 (同じレビュー担当)。D-6 と §0 を改める。依頼者裁定 (Q-1〜Q-5) は逐語で §5 に記録する。

## Q-1 の書き換え
- (A') 監督案: `requests_per_minute` → PG の sliding 行、`concurrency` → host 共有 slot、control 2 class → 現行 (control plane 1 process)。契約不変。
- (B) 宣言で落とす (`deployment_required`)。契約不変。bound が N 倍に緩む。
- (C') 静的分割 + 契約 1.12.0: 撤回 (指摘 2)。却下理由付きで残す。
- Q-2 は裁定 15 で閉じる (現行の sliding を保つ = 依頼者判断を要しない)。Q-3・Q-5 は据え置き。Q-4 は裁定 20。
```

### 10.3 監督裁定 23〜25 (v0.3 の起草の疑義への裁定、2026-09-28)

23. **§9 (o) の読みを採る。** 新条件 (a) の「保持中の本数 = L」は client 側で数える (launcher が L + P 本以上を同時に送り、応答が返らない (429 でも 200 でもない) 本数がちょうど L、L 本目より後の要求は 429 `concurrency`)。`pg_stat_activity` は worker の分散 (lock 待ちの session の `application_name` に 2 つ以上の pid) の観測にだけ使う。thread を待つ要求が DB に現れないことは thread limiter の設計どおりであり、欠陥ではない。
24. **§7.2 の r2db の 64 の与え方は (甲)** (env `R2DB_MAX_CONCURRENCY`、MitateDB の `MITATEDB_MAX_CONCURRENCY` と対称)。real-server plug が本番の起動形をそのまま起動する性質を両 peer で保つことを優先する。`ops.py`:1183-1187 の docstring と F-16 の値の出所は WP-2 で追随する (`verify-declarations` は同じ env を読む。§9 (c) の開示と同じ限界)。 **【v0.4、2026-09-28】裁定 31 で覆す (計測時 64 の取り下げにより `R2DB_MAX_CONCURRENCY` は足さない)。**
25. **裁定 16 と F-1 の関係 (起草の確認結果を確定)。** F-1 (`r2db-api/src/r2db_api/limits.py:121-`、pool < 同時借用数だと 5 本目が pool 待ちの timeout で 503 になり宣言の 429 と食い違う) の理由は今も成り立つ。同時に pool から借りる数の上限は今は実効の thread limit + c (flush thread、platform 1 文) なので、pool をその値から導けば F-1 の失敗は起きない。条件 2 つ: (i) pool は env 上書き後の実効 thread limit から導く (`ThreadLimitMiddleware` に渡す値と同じ出所)、(ii) 1 つの区間が同じ pool から 2 本同時に借りないこと (未確認 = WP-2 の実装で現物確認し、あれば c に足す)。§9 (p) (Cloud Run の revision の重なりで 2 host になる間は slot が共有されない) は R-52 の射程として台帳 R-52 行に【追記】する (本件で解かない)。

### 10.4 監督裁定 26〜33 (v0.4、2026-09-28。設計レビュー 1 回目の再確認 (新 1〜8) への裁定。逐語)

26. **(新 1) 親側の事前検査は `verify-declarations` ではなく、service 自身の env と DSN で `build_app()` を 1 回実行して捨てる one-shot にする。** 裁定 11 の「`ExecStartPre=` で `ops verify-declarations`」はこれで覆す (provision の DSN を data plane の unit / container に置くことになり最小権限に反する。`MitateDB-api/docs/cloud-run-cloud-sql.md:1079`)。両 peer の composition root に entry (`python -m r2db_api.main --preflight` / `python -m mitatedb_api.main --preflight`。`build_app()` を呼び、cell を閉じて 0 で終わる。例外は非 0) を足し、r2db は `ExecStartPre=`、MitateDB は CMD の `exec uvicorn` の前に置く。起動時の検査の全部 (F-13 / F-15 / F-16 / F-18 / registry / pepper、裁定 27 の workers 検査、裁定 28 の slot 自己検査) が子と同じ経路・同じ権限で非 0 終了として観測できる。`verify-declarations` への workers ≤ ceiling の追加は運用者の手動検査として残す。C-26 (5) は one-shot を含む起動形 (workers ≥ 2) で非 0 終了と F-15 の文言を観測する。
27. **(新 2) `concurrency` の写像は「slot directory が配線されている、かつ `process_ceilings.data` ≤ この supervisor の workers (env `R2DB_WORKERS` / `MITATEDB_WORKERS`)」のときだけ `enforced`、それ以外は `deployment_required`。** 宣言の方が多ければ別 host に process がありうると読む (正直な宣言 ⇒ 正直な写像を保つ)。合わせて起動時に workers ≤ ceiling を検査する (裁定 11 の検査を `build_app()` に移す) ので、`enforced` は workers = ceiling のときに限る。`requests_per_minute` の写像は PG の行が配線されているときだけ ceiling に依らず `enforced` (裁定 18 のまま)。slot directory は plane ごとに env で明示し既定値を持たない (`R2DB_SLOT_DIR` / `MITATEDB_SLOT_DIR`)。directory は配備側が作る (r2db: systemd `RuntimeDirectory=<unit>/slots` + `RuntimeDirectoryMode=0700`、MitateDB: Dockerfile で `USER` 所有の 0700)。`build_app()` は存在・所有者・mode 0700 を確かめ、自分では作らない (worker ごとの別 directory を起こさない)。conformance の adapter と launcher は instance ごとに `mkdtemp` する。
28. **(新 3) slot ファイルの扱いを決定にする。** `O_CREAT | O_NOFOLLOW | O_CLOEXEC`、mode 0600。「塞がっている」は EWOULDBLOCK / EAGAIN / EACCES だけ、他の errno は fail-closed (既存の DB 失敗と同じ 503 の写像、素通ししない)。起動時の自己検査: 同じ process で同じ file を 2 回 open し、1 本目の `LOCK_EX` の下で 2 本目の `LOCK_EX | LOCK_NB` が拒まれることを確かめ、拒まれなければ起動失敗 (模倣 flock・syscall filter・gVisor を捕らえる。`HAVE_FLOCK` の未確認も覆う)。D-3 (4) の plug 表に「どの plug が slot を配線するか」を書く: http / socket / real-server の plug は `mkdtemp` の directory を配線する (C-05 V2 の「宣言値 = 実拒否位置」は slot を通る)、in-process plug は in-memory counter のまま (写像は現行 = ceiling 1 で enforced)。
29. **(新 4) slot の fd は要求ごとに open し、`with` の `finally` で必ず close する。process 内で fd を共有しない。** 変異の対応表に「fd を process 内で共有 → 新条件 (a) と peer-local の 2 thread テストが赤」を置く。拒否経路の費用 (L 回の open / flock / close = 3L 回の syscall、L=32 で 96 回、認証前、event loop) を §9 (i) に数字で書く。最適化 (process 内の空き表) は本件では採らない (共有の危険を増やす)。
30. **(新 5) rate 行の形は「秒単位の 60 個の計数の配列 + 基点の秒」(int[60]、約 240 B) にする** (v0.3 の timestamptz[] を覆す)。境目の 1 秒を多めに数えるので上限を超えて通すことが無く、60 s 未満の drive (C-05 V2) では拒否位置が変わらない。配列は固定長なので 1 文の費用が L に依らない。計測前の小実験 (WP-4 の前提): 使い捨て cluster で 32 並行の upsert を流し 1 文の p50 / p95 を取り、0.2 ms/文 (8 倍の余裕から出る上限) を超えるなら監督に上げる (再裁定)。
31. **(新 6) 裁定 17 の「計測時 64」と裁定 24 (`R2DB_MAX_CONCURRENCY`) は取り下げる。** 計測は本番既定の 32 で行う (slot の `with` は応答を作る前に抜けるので溢れない: `r2db-api/src/r2db_api/http.py:524-557`、`MitateDB-api/src/mitatedb_api/http.py:645-656`)。実測で 429 が出たときだけ再検討する。裁定 17 の他の項 (pid 付き access log、429 run は捨てて記録、D-16 逐語不変、K=1 非退行) は残す。
32. **(新 7) 新条件 (b) の観測法**: `concurrency` 以下の波に分けて新しい接続で 2L 本送り、「200 がちょうど L 本、`requests_per_minute` の 429 が L 本、200 の pid (access log) が 2 種以上」の 3 つを主張する。窓を process 内に戻す変異は 200 が L を超えて赤。
33. **(新 8) 細部**: 孤児掃除は pgid で記録する (子の pid は置き換えで古くなる)。§9 (l) は閉じた (約 25 byte)。Cloud Run が一時的に max-instances を超えうる件は現物未確認のまま runbook の開示に 1 行 (「推測」を明記) 添える。§9 (p) は裁定 25 のとおり R-52 へ。裁定 21 の逐語の行番号 (:903 / :989) はレビュー担当の誤りで、本文の :904 / :988 が正しい (逐語は書き換えず本註で訂正)。裁定 25 の条件 (ii) は AST 走査で 0 件 (scratchpad `nested_borrow.py`)。「rate の文は認証で借りた接続を返した後に借りる」を作業指示書の完了条件に置く。

### 10.5 監督裁定 34〜36 (v0.4 の起草の疑義への裁定、2026-09-28)

34. **(§9 (s)) rate 行の計数は 61 個にする** (`int[61]` = 現在の整数秒 + 直前の 60 秒。裁定 30 の「60 個」を覆す)。秒の途中から始まる 60 秒の窓は 61 個の整数秒にまたがるので、60 個では数え落としが出て L を超えて通しうる。61 個は境目で多めに数えるだけで、上限を超えて通すことは無い。固定長 (約 244 B) は変わらない。
35. **(§9 (t)) C-26 (4) の起動形**: ceiling 1 / workers 1 → `enforced`、**ceiling 2 / workers 2 → `enforced`** (slot directory を配線した launcher)、**ceiling 2 / workers 1 → `deployment_required`** の 3 通りを観測する (裁定 27 の写像の両側を pin する。3 通り目は安い)。新条件 (a)(b) は ceiling 2 / workers 2 の起動形で駆動する。
36. **(§9 (r)、未確認 4 件)** 自己検査は slot directory 内の専用ファイル `selfcheck` を同じ process で 2 回 open して行う (slot ファイルを使わない)。flock が close で外れること (POSIX の flock 意味論。fcntl 模倣では同 process のどの fd の close でも外れる = 自己検査が捕らえる) と、systemd の `RuntimeDirectory` が unit の停止で消えること (`RuntimeDirectoryPreserve=no` が既定) は文書上の事実として採り、作業指示書 WP-2 / WP-5 の完了条件に「開発機と配備先の現物で確かめた」を置く。両 peer の cell を閉じる経路 (preflight の後始末) は WP-2 / WP-3 の実装で現物確認し、無ければ足す (preflight は process 終了で接続が閉じるので、閉じる経路が無くても正しさは損なわれない。行儀のためだけ)。Cloud Run の一時超過は「推測」のまま (裁定 33)。

### 10.6 監督裁定 37〜42 (最終再確認 `r113_design_review_1c.md` の新 A〜F への裁定、2026-09-28。v0.5)

37. **(新 A、高) rate の 1 文の基点は単調に進める。** `base_s = GREATEST(現在の base_s, EXCLUDED.base_s)`、進める幅は `LEAST(61, GREATEST(0, EXCLUDED.base_s − 現在の base_s))`、61 以上なら配列を全部 0 にする。行 lock を待った要求が古い秒を持ち込んでも基点を戻さない (戻すと次の要求がその秒の計数を 0 に落として L を超えて通す)。時計が大きく進んでから戻った場合は窓が伸びる (厳しい側) ので開示で足りる。D-3 (1) の骨子を v0.5 で書き換えた。変異: `GREATEST` を外す → 新条件 (b) と peer-local の「秒の境目で lock 待ちが混ざる」テストが赤。
38. **(新 B、中) 本文の残りの「60」を 61 に、§7.3 の「64」の記述を「裁定 31 で取り下げ (計測は既定 32)」に揃えた** (v0.5 で監督が直接編集。D-3 (1)、WP-2 の表、§7.3)。
39. **(新 C、低中) 配備物は env の同じ変数からだけ `--workers` を渡す** (systemd の `ExecStart=… --workers ${R2DB_WORKERS}`、Dockerfile の CMD は `${MITATEDB_WORKERS}`)。引数の直書きを禁じ、静的テスト (unit / Dockerfile の文面を読む) で pin する。WP-5 の完了条件。
40. **(新 D、低中) SIGHUP による reload は runbook で禁じる** (再起動は stop / start。SIGHUP の間は N+1 process になり、接続予算 F-16 が P で数える前提が破れる: N=5 で 72 > r2db api role 68)。F-16 は P のまま。両 runbook に 1 行、§9 (c) の入口の表に 1 行。
41. **(新 E、低) preflight entry は module の `app` (= `build_app()` の結果) を使い回し、二重に `build_app()` を呼ばない。MitateDB の CMD は `set -e` (または `&&`) で繋ぐ。起動時の検査は `build_app()` の中に置き、lifespan に置かない。** WP-2 / WP-3 / WP-5 の完了条件。
42. **(新 F、低) int[61] は境目で最大 1 秒分を多めに数える (L を超えて通すことは無い)。** C-05 の honest limits と両 runbook に開示する。 **(n)**: `hold_in_flight` が pool の接続を持たずに止まることは r2db で現物確認済み (レビュー担当)、MitateDB は WP-3 の完了条件に置く。

