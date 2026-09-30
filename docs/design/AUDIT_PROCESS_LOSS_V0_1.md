# worker process の突然死による audit の欠落 設計文書 (v0.5)

## 0. 位置づけと依頼者裁定

- 版: v0.1 (2026-09-30) 起草 (drafter)、監督が起草の指摘を反映。**v0.2 (2026-09-30)**: 設計レビュー 1 回目 (指摘 F1〜F11、§12) を反映。v0.2 の監督案は 1-A (i) + 2-B + M だった。**v0.3 (2026-09-30)**: 設計レビュー 2 回目 (指摘 G1〜G11、§12) を反映。M (印) と 2-B を監督案から外し、監督案の組を **1-A (i) + 2-A** (2-A は sweep・DELETE を要しない形に改めた) とした。**v0.4 (2026-09-30)**: v0.3 の再確認 (指摘 H1〜H11、§12) を反映 (2-A の形の確定、実測の読みの訂正、契約文案の前提)。**v0.5 (2026-09-30)**: 依頼者裁定 (Q-1〜Q-5、すべて監督案) を §10 に逐語で記録。以後この設計が確定である。
- 台帳: 計画文書 `RM` §8 の **R-115** (規模 M)。
- 変更クラス: **D** (監督の実測。`tools/change_class.py` に見込みの path を渡して class=D、conformance_required=true。`security/CONTROL_MAPPING.md` が D、`spec/`・`conformance-tests/` が C)。契約に触れる案を採るなら設計レビューは 2 回 (`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 50)。
- 基点: main `b2be64d` (v0.1 の起草時は `f7dc503`。R-114・R-116 の閉止を取り込んだ後も、本書が引く `file:line` は変わっていないことを確かめた)。uvicorn は開発機の 0.52.4。契約は現行 1.12.0 (R-114)、`security/CONTROL_MAPPING.md` は 3.10 (R-116)。
- 出所の記法は `docs/work-orders/OPERATING_CONDITIONS.md` §0。本書の Q-N / WP-N / F-N (§12) と決定 1・2、候補 1-A〜2-C・M は本書ローカルの ID である。
- 公開規律: 実 DSN・実ホスト名・作業機の絶対パスを置かない (同 §1.9)。

**依頼者裁定 (逐語、2026-09-30)**

監督の問い 2「R-115 に着手するか。着手する場合、Class D の見込みで進めてよいか」に対し (2026-09-30):
「1は(i)、2は着手、Dで進めてください、別セッションで。」
(「1は(i)」は別件 R-114 への回答で、本件には当たらない。)

## 1. 問題

- 台帳 R-115 の文のとおり。ただし対象を「uvicorn supervisor の SIGKILL」に限らず **worker process の突然死一般** とする (OOM kill、Cloud Run の SIGTERM 後の SIGKILL、host の kill。1 process の配備でも起こる)。lifespan の最終 flush に依存する限り同じ欠落が起こるからである。host / instance の消失 (電源断、instance の破棄。process だけでなく filesystem も消える) を含むかは候補ごとに書く (§4、§5)。
- **脅威**: `security/THREAT_MODEL_V1.md` T-14 (:135-138、証拠の破壊)。healthcheck に応答できないほど worker を忙しくさせて supervisor に SIGKILL させれば、攻撃者は自分の flood の件数 (と直前の成功 event) を消せる。費用の側は T-07 (:100-103、資源枯渇)。
- **契約との接点**: 契約 `audit.sink_failure_policy` (`spec/data-service-api.v1.json`:955) は、通常の data-operation event の buffer による吸収を「explicit operational alert」付きに限り、「must not silently discard events without that alert」とする。突然死の欠落は alert を出せない = 黙った破棄である。
- **これまでの許容の経緯**:
  - SI-14 の Verification は「Representative events yield correlated evidence」(`security/SECURITY_INVARIANTS_V1.md`:374-375)。Does not require は「Logging every successful read at unlimited granularity」(同 :371-372)。
  - フェーズ4 設計 (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`) D-3 は「クラッシュ時に失うのは窓内の計数のみ」(:194)、合体カウンタをプロセスローカルとした (:195)。D-4 は通常 event を process ごとの bounded buffer に積む (:204-206)。同書 §4 の R-F は「全 event を同期耐久化する」を却下した (:337。理由は SI-14 の Does not require と buffer 緩和の放棄)。
  - 両 peer の lifespan のコメントがこの許容を前提にする: MitateDB「D-3 only sanctions losing counts to an actual crash」(`MitateDB-api/src/mitatedb_api/main.py`:697-698、`MitateDB-api/src/mitatedb_api/audit_dispatch.py`:519)、r2db「D-3's "crash loses only the in-progress window's count" allowance does not apply」(`r2db-api/src/r2db_api/main.py`:785-786。graceful shutdown の側から同じ許容を指す)。
- 現状の開示: `security/CONTROL_MAPPING.md` SI-14 の Status (r2db :1757、MitateDB :1867)、R-113 の設計 `docs/design/MULTI_PROCESS_WORKER_V0_1.md` D-2 の表 (r2db #10 :195、MitateDB #11 :214)、同 §10 の裁定 21 (:825)。
- **本設計はこの許容を改める。**

## 2. 事実 (両 peer とも同じ構造)

`R` = `r2db-api/src/r2db_api`、`M` = `MitateDB-api/src/mitatedb_api`。

1. **失われるのは 2 種類だけ。**
   - (a) buffer 経由の event = 通常の data 操作の成功 (query、catalog、非 destructive の mutate / insert / update、mutate の replay)。r2db は `_event` の分岐 (`R/service.py`:1243-1252)、MitateDB は `_push_data_operation_event` / `_push_replayed_data_operation_event` (`M/cell.py`:873-906。呼び出しは insert :2243、query :2374 ほか)。
   - buffer は process ごと (`R/service.py`:168、`M/audit_dispatch.py`:131)。上限は件数のみ 1000 (`R/service.py`:71、`M/application_audit.py`:65)。800 件で要求 thread が同期 flush (`R/service.py`:221、:226、:250。`M/audit_dispatch.py`:146)。2.0 s 周期の daemon thread (`R/service.py`:80、`R/main.py`:757-758。`M/application_audit.py`:66、`M/main.py`:668-669)。lifespan の最終 flush (`R/main.py`:790、`M/main.py`:700)。要求の終わりには flush しない。
   - (b) 拒否の窓の 2 件目以降の件数 (`repeat_count`)。key は (application_id, actor_id or "unknown", operation, reason_code) (`R/service.py`:1264、`M/audit_dispatch.py`:623)。窓の長さは DB 宣言 `audit_coalescing_window_ms` (既定 60000。コード既定 `R/service.py`:67、`M/application_audit.py`:69)。対象は durable 6 code (`R/service.py`:52、`M/audit_dispatch.py`:69)。2 件目以降は memory の加算だけ (`R/service.py`:555-558、`M/audit_dispatch.py`:473-475)。最初の 1 件は同期 INSERT 済みで失われない (`M/audit_dispatch.py`:492-497)。
2. **失われないもの**: destructive な mutate・全 schema 操作 (pre_commit の hook で data commit の前に別接続で commit。`R/postgres.py`:1705-1707、`M/audit_dispatch.py`:112-118)、拒否の最初の 1 件、overflow の alert 行、control plane の event (状態変更と同じ transaction。control plane の拒否は毎回同期で耐久化する)。
3. **失われうる量の上限** (現状、worker 1 本あたり): (a) 最大 1000 件 (実際は直近 2 s に成功した操作の数と 800 の小さい方に近い)。(b) 開いている窓すべての repeat_count (最大 60 s 分、件数に上限なし)。
4. **読み手は欠落を検出できない**: audit の行に worker / process / 起動を識別する列は無い。`audit_seq` (bigserial) はある (`r2db-api/migrations/0007_application_audit.sql`:114、`MitateDB-api/migrations/0005_application_audit.sql`:161) が、`audit_query` は返さない (`M/audit_query.py`:355-358。r2db も同じ)。`AuditQueryRequest` の filter は `event_classes` だけで、actor や key では絞れない。
5. `visibility_lag_ms` は書き手の transaction の timeout から導く値 (出荷既定 11000、conformance は 4000) で、flush 間隔・窓の長さを含まない。`visibility_lag_ms`・`coalescing_window_ms` の語は `spec/` に無く、capabilities の `audit_query` の実装宣言である (`R/control_plane.py`:707-708、`M/control_plane.py`:1661-1662)。
6. audit の書き先は platform DB の `application_audit` (`R/credential_store.py`:1577)。r2db は専用 pool、MitateDB は呼び出しごとの fresh 接続 (`M/application_audit.py`:295-308)。MitateDB の pre_commit は cell lock の内側で走る (`M/cell.py`:3130、:3178)。
7. uvicorn 0.52.4: supervisor は 0.5 s ごとに子を ping し、`timeout_worker_healthcheck` (既定 5 s) に応答しない子を `kill()` して置き換える (`uvicorn/supervisors/multiprocess.py` `keep_subprocess_alive`)。
8. real-server launcher (`r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py`、`conformance-tests/socket_harness.py`) は `--workers N` で起動でき (`socket_harness.py`:794、:872)、停止は process group への SIGTERM → 10 s → SIGKILL (同 :391-425)。worker 1 本だけを kill する手段と、**worker を** kill する既存テストは無い (`MitateDB-api/tests/test_r113_multi_process_wiring.py`:1738 の SIGKILL は flock の子 process であって worker ではない)。要求を処理した worker の pid は access log から取れる (`access_log_pids_for_status`、r2db :1224、MitateDB :1056。`tools/perf_baseline.py --real-server` の `REALWORKERS` 行の出所)。process group の成員は `socket_harness.py`:966 の `_pids_with_pgid`。launcher は data plane の env を自分で組み (`_data_env`)、ambient の `R2DB_*` / `MITATEDB_*` を取り除く (`r2db-api/conformance/real_server_r2db.py`:120-140)。
9. R-113 で `requests_per_minute` は PG の sliding 行 (r2db `0015_credential_request_rate.sql`、MitateDB `0016_credential_request_rate.sql`) に移っており、認証済みの要求ごとに platform DB へ書く前例がある (grant は INSERT / SELECT / UPDATE。DELETE は無い: r2db 0015:82、MitateDB 0016:82)。
10. **拒否の経路で durable な書き込みより前に効く limit** (両 peer): byte bound → pre-auth の `concurrency` の slot (credential に依らない配備全体の資源) → 認証 → rate の順 (`R/http.py`:452-466、`M/http.py`:632)。`requests_per_minute` は credential 単位なので認証の後に効く (`R/service.py`:1178-1188)。**bearer 無し (AUTH_REQUIRED) と locator 不正 (AUTH_INVALID) の要求は現状 platform DB を一度も読まない** (`R/credential_store.py`:858-862、`M/http.py`:515-529) — 2 件目以降は memory の加算だけである。認証の拒否の件数を bound する rate は無い (SI-14 の Status `security/CONTROL_MAPPING.md`:1758)。フェーズ4 設計 P4-D3 は data-plane への pre-auth の window の追加を却下している (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`:366)。
11. **r2db の pre_commit の後の例外**: `transact` は pre_commit (:1705-1707) の後に idempotency 記録 (:1715-1720) を実行し、その後の `QueryCanceled`・`LockNotAvailable`・`UniqueViolation`・`DataError` の分岐 (`R/postgres.py`:1721-1728) は `hook_fired` を見ず error 行を書かない (一般の `psycopg.Error` の分岐 :1736 だけが書く)。allow 行は commit 済みでデータは rollback、error 行も無い状態が、process の喪失なしに起こりうる。`outcome_note` (`R/control_plane.py`:715-720) は「その 1 例 (process の喪失) だけ」と宣言しており、食い違う。MitateDB は `except Exception` の中で `hook_fired` を見る (`M/cell.py`:3304)。到達頻度は低いと推測 (未実測)。
12. 観察 (調査担当、未実行確認): r2db の schema の replay は durable にも buffer にも入らない (`R/service.py`:1011 と :1243-1244。MitateDB は `write_replayed_fail_closed_event` で同期に書く、`M/audit_dispatch.py`:655)。`append_many` の docstring が古い (`R/credential_store.py`:1644-1647)。扱いは §11 の 3。

## 3. 実測 (監督、2026-09-30)

commit `f7dc503`、Darwin/arm64、load average 2.1〜3.0 / 10 core、pytest 0 本。`tools/perf_baseline.py --real-server <peer> --warmup 20 --n 200` (K=1、op=query)。「同期」= buffer 容量 1 (毎 event を要求 thread で同期 flush)。launcher の data env へ監督の scratch の driver で注入した。注入が届くことは、壊す値で起動が落ちることで確認した。交互に 3 巡。

| peer | buffer あり p50 / p95 (ms) | 毎 event 同期 p50 / p95 (ms) | p50 差 |
|---|---|---|---|
| r2db-api | 2.369 / 2.488、2.354 / 2.526、2.352 / 2.512 | 2.480 / 2.602、2.465 / 2.582、2.473 / 2.718 | +0.115 ms (+4.9%、3 巡の平均) |
| MitateDB-api | 2.101 / 2.263、2.117 / 2.303、2.144 / 2.311 | 4.640 / 5.731、4.612 / 4.820、4.617 / 5.157 | +2.5 ms (+118%) |

- 読み: r2db (pool) は閾値 (p50 +40% / p95 +50%、`RM` §0.1.4 の 1) の内側。MitateDB は fresh 接続の費用で閾値を超える。MitateDB の sink を pool (thread_limit 本が同時に書くので、1 本の持続接続なら直列化が要る) にすれば r2db と同水準になる見込みだが、これは **未実測の推測** であり、実装 WP の最初に測る。pool は worker ごとの接続予算 (F-16 の床) に本数分を足す。
- 限界: 開発機の local PG (往復が速い)。本番 (Cloud SQL / VPS) の往復の費用は測っていない。real-server 計測は op=query のみ (mutate の K=1 と、MitateDB の K=4 の cell lock 待ちは §8 で測る)。
- 無効な計測の記録: 先に env で渡して測った 8 run は、launcher が env を取り除くため無効 (差なしに見えた)。

**同じ 1 行への加算の費用** (監督、2026-09-30、local PG、load average 2.6〜2.8。scratch の table に `INSERT ... ON CONFLICT DO UPDATE SET n = n + 1` を K 本の接続から 4 s ずつ。比較は同じ形の 1 行 SELECT。client は Python の thread なので K > 1 の絶対値は client 側の GIL を含む。table は計測後に消した):

| K | SELECT ops/s、p50 / p95 (ms) | 加算 ops/s、p50 / p95 (ms) |
|---|---|---|
| 1 | 76,672、0.012 / 0.015 | 20,065、0.046 / 0.051 |
| 8 | 26,240、0.284 / 0.579 | 12,990、0.295 / 2.374 |
| 32 | 23,760、1.249 / 2.657 | 16,299、1.321 / 5.925 |

- 読み (表から言える範囲): 1 行への加算は K=1 で 1 回 0.046 ms (SELECT の 3.8 倍)、この計測の範囲で 12,990〜20,065 回/s。K > 1 の値は client の GIL を含むので DB 側の比較にはならない。p95 が SELECT より伸びる原因 (行 lock の待ちと推測) は測っていない。約 20 万回の加算で table は 1.2 MB (vacuum 前)。持続接続での値であり、MitateDB の現行の fresh 接続 (1 つ目の表の +2.5 ms) には当てはまらない — 加算は WP-3 で pool にした sink の接続を使う。

## 4. 決定 1: 通常の data 操作の event (§2 の 1 (a))

問題は (a) event と (b) 拒否の件数で性質が違うので、決定を 2 つに分ける。

**1-A (監督案) 応答の前に同期で書く。**
- 非 destructive の mutate は destructive と同じ pre_commit の経路に乗せる (data commit の前に allow 行を commit。`outcome_note` の既存の意味 = allow は「認可され submit された」のまま)。query / catalog と mutate の replay の event も応答の前に書く (H11)。buffer の経路が消える (pre_commit・応答前の同期書き込み・error 行の経路は残る)。
- **実装要件 (F5 / G10)**: r2db の pre_commit を `_idempotency_store` の後、transaction の真に最後の文へ移す (`R/postgres.py`:1705-1720)。これで pre_commit の後に起こりうるのは commit の失敗だけになり、既存の一般の分岐 (:1736) が error 行を書く。413 / 400 の応答は変えない。COMMIT 自体が `QueryCanceled` として上がりうるか (413 の分岐が error 行を書かずに抜ける経路) は実装 WP の最初に実行で確かめ、起こるならその分岐でも error 行を書く (H11)。
- **語彙 (G8)**: buffer を削ると `audit_buffer` / `audit_sink` を出す箇所が消えるが、過去の行は `audit_query` が返し続けるので宣言からは外さない (契約 1.5.0 の superset 義務、`spec/data-service-api.v1.json`:987)。両 peer の「宣言 = 実際に出す語」の等式テスト (`r2db-api/tests/test_audit_query.py`:2112、`MitateDB-api/tests/test_audit_query.py`:1972) に「宣言するが今は出さない語」の明示の集合を足す (作業指示書で確定)。
- 利点: 応答を受け取った操作の event は必ず永続化済み。欠落 0 (process 死でも host / instance の消失でも)。worker 間の共有状態なし。
- 費用: 要求ごとに platform DB へ 1 往復 (§3)。MitateDB は sink を pool にする必要がある。MitateDB では pre_commit が cell lock の内側なので、非 destructive の transact も往復の間 lock を握る (§8 で K=4 の前後を測る)。認証済みの要求が pre-auth の slot を握る時間も 1 往復分延びる (G11)。
- **1-A' (MitateDB の非 destructive mutate だけ commit の後に lock の外で書く変種) — 採らない (G4)。** (i) の下で commit 後の書き込みが失敗すると、データは commit 済みなのに 503 になり、idempotency_key の無い再送で行が二重になる。突然死では「commit されたが行が無い」になり `outcome_note` と逆向きになる。K=4 の lock 待ちが前後で悪化したときは、切り替えずに依頼者へ上げる (§8)。
- フェーズ4 設計 §4 の R-F (全 event の同期耐久化の却下) を覆す案である (§1)。
- **下位の決定 1-A-f (sink が落ちているときの通常操作)**:
  - (i) fail-closed (503)。buffer・overflow alert の機構を削除する。前例: 認証済みの要求は rate 行 (§2 の 9) で既に platform DB へ書き、失敗時は 503 である。両論: platform DB が読めても書けない状態 (read-only への failover、disk full) では query も 503 になる。
  - (ii) 同期の書き込みが失敗したときだけ既存の bounded buffer に吸収する。機構は残り、二重障害 (sink 障害中の突然死) のときだけ欠落しうる。
  - 監督案は (i) — 単純で、欠落の経路が残らない。

**1-B worker の外の耐久の置き場** (local journal file)。利点: 要求の経路に DB 往復を足さない。欠点: host / instance の消失と、実配備の再起動 (r2db の systemd `RuntimeDirectory=` は自動再起動で消える — R-113 設計 §10 の裁定 36、Cloud Run は instance ごと消える) で失う (G1)。回収の所有権・重複排除の機構が増える。

**1-C 欠落を検出できる印だけを置く。** 欠点: 証拠 (最大 1000 件) は戻らない。印を host-local の file に置く形は実配備の再起動で消える (G1)。DB に置く形は生死の判定に持続接続か heartbeat が要る。

**1-D flush 間隔を縮め、失われうる量を宣言するだけ — 却下。** 依頼者の原則 (開示の言い換えだけで閉じない) による。

## 5. 決定 2: 拒否の件数 (§2 の 1 (b))

**2-A (監督案) 窓の件数を platform DB の共有の行に持ち、拒否の応答の前に加算する。**
- 形: key と窓ごとに 1 行の counter table。runtime role には table の権限を与えず、加算だけを行う SECURITY DEFINER の関数の EXECUTE だけを与える (runtime role は件数を減らせず、消せない)。**これは R-113 の `credential_request_rate_admit` とは違う型である** (H1): あちらは SECURITY INVOKER で、runtime role が table に SELECT / INSERT / UPDATE を持つ (r2db 0015:82、:93-95、MitateDB 0016:82、:91)。rate 行は証拠ではないのでそれで足りるが、counter 行は audit の証拠なので UPDATE を直接渡さない。両 peer で最初の SECURITY DEFINER になるので、作業指示書で次を完了条件にする: `search_path` の固定、PUBLIC からの EXECUTE の REVOKE、owner は schema の owner role (provision role にしない)、verify / 起動時の検査への追加。
- 窓 (H4): 窓は時計に整列する (`window_start` = `clock_timestamp()` を窓の長さで切り捨てた値)。主 key (合成 key, `window_start`) が同時の最初の 1 件を直列化し、「key・窓あたり counter 1 行」を保つ。key の `application_id` NULL は合成 key 列で 1 つの値に畳む。
- 1 回の呼び出し (H7): 関数は 1 文・autocommit で走り、その窓の最初の 1 件なら counter 行を作って最初の 1 件の audit 行 (現行の同期 INSERT に当たる) を同じ文の中で書き、2 件目以降は加算する。counter 行には、作成時に決めた summary の event_id、最初の 1 件の fields、窓の終わりを保存する (H3。cursor が安定する)。
- 読み: `audit_query` は **閉じた窓** の counter 行を summary event として直接読む (既存の UNION に枝を 1 つ足し、auditreader role に SELECT を与える — H9)。`plane` は application、`recorded_at` は窓の終わり、event_id は counter 行に保存した値。判定は既存の threshold と同じ式 (`recorded_at` < 現在 − `visibility_lag_ms`) で、関数が 1 文・autocommit・`clock_timestamp()` で走り、その role が `audit_writer_roles` に入っている限り、読まれた後の行に加算は入らない (H7)。
- 件数の意味 (H2): counter の値を n とすると、最初の 1 件は自分の audit 行で表され、summary は 2 件目以降の n − 1 件を表す (現行の summary 行と同じ意味)。n = 1 の窓は summary を返さない。n − 1 = 1 のとき `count` を付けない (`count` は 0 / 1 を取らない)。合計は常に n になる。**sweep・DELETE・summary の INSERT が要らず、書き手が全滅しても読める** (F2・F6・F7 の解消)。
- process 内の coalescer (memory の窓) は削除する。PG を持たない in-process の plug (両 peer の memory backend) は、同じ件数の意味を process 内の表で実現する (突然死の性質は composition root にだけ当てはまり、新条件もそこでだけ走る — H8)。集約が配備全体になり、SI-14 Status の「process-local ceilings (2 × windows × M)」(`security/CONTROL_MAPPING.md`:1755) も解消する (配備全体で key・窓あたり 2 行)。
- 失敗時: 加算の失敗は拒否を 503 にする (fail-closed)。契約 `sink_failure_policy` は拒否の記録の失敗を fail-closed の類に置いており、現行の「最初の 1 件」と同じ扱いである。
- 利点: 応答を返した拒否は必ず数えられている。worker の飢餓 (T-14 の状況) でも sink の障害でも上限が崩れない (応答の前に書くので)。host / instance の消失でも失わない。
- 費用 (F1): 拒否のたびに platform DB へ 1 往復。未認証の flood (bearer 無し / locator 不正) は現状 0 往復なので、0 → 1 になる。待つ間、配備全体で共有の pre-auth `concurrency` slot と worker thread を握る。
  - 実測 (§3 の 2 つ目の表): 同じ 1 行への加算は local PG・持続接続で 1 回 0.046 ms (K=1)。real-server の 1 要求 (p50 約 2 ms) に比べ小さい。
  - 比較の基準: 形の整った locator を持つ無効な token の flood は、現状でも 1 件ごとに platform DB を 1 回読む (認証の読み)。未認証の要求が platform DB の往復を生む経路は既にあり、2-A は bearer 無しの flood にも往復 1 回 (書き込み) を足し、無効な token の flood では読み 1 回に書き込み 1 回が加わる。読みと書き込みの費用は同じではない (上の 3.8 倍)。
  - 残る懸念: 加算ごとに dead tuple と WAL が増える (実測: 約 20 万回で 1.2 MB、vacuum 前)。flood の下での正規 tenant の 429 率は real-server で未実測 — 実装 WP で前後を測り、悪化したら依頼者へ上げる (§8)。

**2-B 周期の checkpoint (append-only の増分 summary 行)。** 利点: table・関数が要らず、要求の経路に往復を足さない。欠点 (G2): 「直近 1 周期分」の上限は、本件の動機である状況で成り立たない — healthcheck kill の時点では checkpoint thread も同じ GIL の飢餓の下にあり、sink の障害中は件数が memory に溜まり続ける。残る欠落は黙った破棄のままで、検出の印 (M) を足しても実配備の再起動で印 file が消える (G1)。**監督案から外す。**

**2-A' 共有の行に周期ごとの増分を加算** — 2-B と同じ理由 (G2) で上限が崩れ、2-A の table も要る。採らない。

**2-C 集約をやめて毎回 audit 行を書く — 却下。** flood で行数が無制限になり、集約の目的 (未認証の書き込みの行数の bound。フェーズ4 設計 D-3 (2)) を壊す。2-A は行数の bound を保ったまま件数だけを耐久にする。

**M 突然死の印 — 採らない (G1・G5・G6)。** host-local の印 file は実配備の再起動で消え、1-A (i) + 2-A では印が知らせるべき欠落が残らない。

**組み合わせ**
- 監督案 = **1-A (i) + 2-A**。応答を返した操作の event と拒否の件数は、process の突然死でも host の消失でも失われない。buffer・process 内の窓・周期 flush の thread・lifespan の最終 flush が消え、audit の経路に非同期の部分が残らない。足すものは counter table と加算の関数 (両 peer に migration 1 本)。
- 対案 (費用最小) = **1-A (i) + 2-B**。event は 0、拒否の件数は「通常は直近 1 周期分」に減るが上限ではなく、宣言で開示する。

## 6. 契約と conformance

**契約 (監督案)**: 共通の安全の結果を契約に足す。版は merge 時に main の次の版 (現行 1.12.0 の次 = 1.13.0 の見込み)。実現手段は書かない。確定文言は依頼者裁定の対象 (Q-4)。文案 (監督案の組 1-A (i) + 2-A を前提):

```json
"process_loss_policy": "An implementation declaring 1.13.0 or higher loses, when a service process stops without completing a graceful shutdown, neither the audit event of an operation whose response the service had already returned nor the count of any denial occurrence whose response the service had already returned. A buffer that such a stop can empty is therefore not the bounded buffer sink_failure_policy permits."
```

- 前提 (H5): この文案は Q-1 = 1-A、Q-2 = (i)、Q-3 = 2-A のときだけ成り立つ。Q-2 = (ii) なら二重障害の除外句、Q-3 = 2-B なら拒否の件数の側を「宣言した周期の内に限る (上限ではない)」に弱める必要があり、1-B / 1-C なら「失わない」と書けない。
- 版の束ね方 (G7): `version_binding` の列挙と `obligations` に 1.13.0 の項目を足す (既存の版の項目と同じ形)。「1.13.0 or higher」の限定により、1.12.0 以下を宣言する実装の `sink_failure_policy` の MAY は遡って狭まらない。`audit_query` を提供しない実装にも掛かる (書き込み側の性質なので無条件)。
- 範囲: 「service process」の停止。host / instance の消失は文に含めない (監督案の実装は結果として耐えるが、共通条件では再現できないので契約にしない。Q-4 の選択肢)。応答を返していない in-flight の要求は対象外 (最大で同時実行数)。
- 可視化: 文は欠落しないことだけを述べ、いつ見えるかは既存の実装宣言 (`visibility_lag_ms`、`coalescing_window_ms`) と `completeness_note` に従う。共通条件は port (`audit_visibility_lag_ms()` と、窓の長さを返す port を 1 つ足す) から上限を導く (G7 の「`spec/` に無い key を読む」への答え)。
- 両論: 契約に足さず peer の実装と `security/CONTROL_MAPPING.md` だけで閉じる案 (契約不変)。欠点は、共通の性質が契約に現れず、読み手 (AI agent) が依拠できないこと。

**共通条件 (新条件 1 件。番号は merge 時に振る)**: この条件専用に real-server を workers=2・短い窓 (platform の宣言 `audit_coalescing_window_ms` を数秒) で起動し (kill が起動を壊すので他の条件と共有しない)、
1. fresh な credential を発行し、成功する操作 N 件と、同じ credential の同じ key の拒否 M 件 (例: role 外の操作の FORBIDDEN) を送る。N + M は `requests_per_minute` の内に置く (guard を assert)。M は workers + 1 以上とし、access log の pid から「ある worker が 2 件以上の拒否を処理した」ことを assert する (M が小さいと現行実装でも緑になりうる — H10)。
2. 最後の応答の直後に、process group の成員 (`_pids_with_pgid`) から supervisor と補助 process を除いた全 worker を SIGKILL する。kill が効いたこと (`os.kill(pid, 0)` が `ProcessLookupError`) と、supervisor が置き換えたこと (新しい pid が要求に応答する) を assert する。合計 M の assert は、窓が時計に整列していて拒否が窓の境界をまたいでも成り立つ (最初の 1 件の行が窓ごとに増えるだけ)。
3. control plane の `audit_query` の結果を client 側でこの credential の `actor_id` で絞り、N 件の request_id がすべて在ること、拒否の件数の合計 (`count` 無しは 1) が M であることを、port から導いた上限 (窓 + `visibility_lag_ms` + 余裕。固定の sleep は置かない) まで poll して assert する。
- 対応する変異 (作業指示書で確定): (1) 通常 event の同期の書き込みを外す → request_id の欠けで赤、(2) 加算を process 内の memory に戻す → 合計 < M で赤。現行実装 (buffer + memory の窓) は、周期 flush (2 s) が kill に間に合うと (1) が偶然緑になりうる — 着手時に現行実装でこの条件が赤になることを確かめ、間に合ってしまうなら「最後の応答から kill まで」を周期より十分短く保つ guard を足す (G3)。
- 所要時間: 起動 + 送信 + 置き換え待ち + 窓 (数秒) + lag (conformance は 4 s) で 1 peer あたり 15 s 前後の見込み (未実測)。

## 7. テスト (SIGKILL の再現)

- launcher (両 peer) に「worker の pid の一覧 (pgid の成員から supervisor と補助 process を除く)」と「指定 pid への SIGKILL と置き換え待ち」を足す (同名 helper は同型性テストの対象。§1.5 の 38)。spawn 方式の補助 process (resource_tracker) の実挙動は実装 WP の最初に実測する。
- 1 process の配備 (workers=1): 監督案の組では audit の経路に process 内の状態が残らないので、workers=1 の突然死に固有の経路は無い。共通条件は workers=2 で足りる。
- 孤児掃除 (R-113 設計 §10 の裁定 19 の pidfile / `sweep_orphans`) と両立させる。

## 8. 性能の測り方

- 閾値: `RM` §0.1.4 の 1 (同一 plug・同一 op の直近基準値に対し p50 +40% 以内、p95 +50% 以内)。
- 形: K=1、`tools/perf_baseline.py --real-server <peer> --warmup 20 --n 200`、op=query と op=mutate。変更の前と後を同じ条件で交互に測り、load average を記録する (§3 の手順)。
- MitateDB: sink の pool 化を実装 WP の最初に測る。K=4 の cell lock の waits/acquire (`RM` §0.1.4 の 3) を前後で測り、記録する。悪化が閾値を超えたら依頼者へ上げる (1-A' には切り替えない)。
- 2-A: 未認証の flood (bearer 無し、K=32) を掛けた状態で、正規 tenant の query の p50 / p95 と 429 の数を前後で測る (real-server)。悪化したら依頼者へ上げる。

## 9. WP 分割の骨子

開発順序 (`CLAUDE.md` Development order) に従い、契約 → conformance → 実装 → 記録の順に置く。監督案の組を前提にした骨子であり、Q-1〜Q-5 の裁定で組み替える。各 WP の完了条件・触ってよいパス・変異の対応表は作業指示書 (Change Set Manifest、`RM` §9) で定める。WP-4 と WP-5 は同じ module (flush の thread、lifespan) を触るので直列に行う (G3)。

| WP | 内容 | 主な path |
|---|---|---|
| WP-1 | 契約 (Q-4 が「足す」のときのみ)。`audit` 節の新 key、版、`version_binding` / `obligations`、確定文の文字列ピン (§1.5 の 35) | `spec/`、`conformance-tests/` |
| WP-2 | launcher の helper (pid 一覧・SIGKILL・置き換え待ち)、窓の長さの port、新条件のテスト | 両 peer の `conformance/`、`conformance-tests/` |
| WP-3 | MitateDB の sink の pool 化と実測 (§8) | `MitateDB-api/` |
| WP-4 | 決定 1 の実装 (両 peer)。buffer の削除に依存する物を含む: conformance の port `flush_audit_buffer` (`conformance-tests/adapter.py`:1966。no-op 化と docstring) とその利用 (`test_c25_result_request_id.py`:334、`test_c27_concurrent_same_key.py`:263)、両 peer の `conformance/conformance_adapter_*.py`、`r2db-api/deploy/env/api.env.example`:163-170 の knob、両 peer の `tests/test_application_audit.py` (overflow の alert)、`conformance-tests/CONDITIONS.md` の C-09 行の port 記述、語彙の等式テスト (G8)、r2db の pre_commit の位置 (F5) | 両 peer の `src/` と `tests/`、`conformance-tests/` |
| WP-5 | 決定 2 の実装 (両 peer): migration (counter table と加算の関数)、coalescer の削除、`audit_query` の読み、verify / 起動時の検査への追加 | 両 peer の `src/`・`migrations/`・`tests/` |
| WP-6 | 記録: SI-14 の Status と Control、R-113 設計 D-2 の表 #10 / #11 とフェーズ4 設計 D-3 / D-4 / R-F に覆しの註 (§1.8 の 56)、配備手順 (migration の適用の段と容量の行)、台帳 | `security/CONTROL_MAPPING.md`、`docs/design/`、runbook |

## 10. 依頼者への問いと裁定

**依頼者裁定 (逐語、2026-09-30)**: 監督が Q-1 / Q-2 (event の扱い)、Q-3 (拒否の件数)、Q-4 (契約)、Q-5 (範囲) をそれぞれ監督案付きで問うたのに対し:
「すべて監督案どおりで進めてください」

確定: Q-1 = 1-A、Q-2 = (i)、Q-3 = 2-A、Q-4 = 契約に足す (§6 の文案を確定文言とする。版は merge 時の main の次の版。host / instance の消失は文に含めない)、Q-5 = §2 の 11 と 12 の 2 件を同じ変更セットに含める。以下は問いの原文である。

- **Q-1 決定 1**: 1-A (監督案: 応答の前に同期で書く) / 1-B / 1-C のどれを採るか。
- **Q-2 1-A-f** (1-A を採る場合): (i) fail-closed (監督案) / (ii) 同期の書き込みの失敗時だけ bounded buffer に吸収。
- **Q-3 決定 2**: 2-A (監督案: 共有の行に応答の前に加算。欠落 0、拒否ごとに 1 往復) / 2-B (周期の checkpoint。往復なし、欠落は減るが上限ではなく開示が残る)。
- **Q-4 契約**: 共通の安全の結果を契約に足すか (監督案: 足す、1.13.0 の見込み、§6 の文案。文案は Q-1〜Q-3 が監督案のときの形で、他の裁定なら弱めた文に改めて再提示する) / peer の実装と `security/CONTROL_MAPPING.md` だけで閉じるか。足す場合、host / instance の消失を文に含めるか (監督案: 含めない)。
- **Q-5 範囲**: §2 の 12 の 2 件 (r2db の schema の replay が durable に入らない観察、`append_many` の古い docstring) を本件に含めるか (監督案: 含める。前者は実装 WP の最初に実行で確かめ、事実なら同じ変更セットで MitateDB と揃える。後者は buffer の削除で文ごと消える)。

## 11. 未確定・開示

1. 性能: 開発機の local PG でのみ測った。本番 (Cloud SQL / VPS) の往復の費用は未実測 (§3)。
2. MitateDB の pool で r2db と同水準になるかは未実測の推測 (§3)。pool の本数分を F-16 の床に足す。
3. 2-A の下での未認証 flood と正規 tenant の 429 率は real-server で未実測 (§8 で測る)。counter table の膨張 (dead tuple) の運用 (autovacuum の設定、古い窓の行の保持期間) は配備手順に書く — 行は audit の証拠なので runtime role は消せず、保持は audit table と同じ扱いにする。
4. 並行作業: R-114 (契約 1.12.0) と R-116 (`security/CONTROL_MAPPING.md` 3.10) は main に入った。版は merge 時に main の最新に合わせて振る。runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.6・§10.7・§10.10 は受理済みで、変えない。
5. 本番には何も適用しない。監督案では両 peer に migration が 1 本ずつ増え、配備手順に適用の段が要る。容量の算式の行 (r2db `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15.1、MitateDB `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2d。どちらも §10 の外) は buffer と process-local の項が消えるので、追記が要る。
6. 応答を返す前に死んだ in-flight の要求の event と件数は対象外である (最大で同時実行数)。pre_commit の allow 行が残り data が commit されなかった場合の読みは既存の `outcome_note` のとおり。

## 12. 設計レビューの指摘と反映

**1 回目 (2026-09-30、F1〜F11)**

| 指摘 | 重大度 | 反映 (v0.3 時点) |
|---|---|---|
| F1 未認証 flood の費用は「0 → 書き込み 1」、共有の pre-auth slot を握る | 高 | §2 の 10、§5 の 2-A の費用と実測、§8。v0.2 では 2-A を外したが、2 回目の G1・G2 で 2-B + M が成り立たないと分かり、費用を実測した上で 2-A に戻した |
| F2 契約文案が検証できない | 高 | §6 (応答を返した拒否に限定、sweep の担い手を要しない読み) |
| F3 `sink_failure_policy` の MAY との優先関係、host の消失 | 中高 | §6 |
| F4 MitateDB の pre_commit は cell lock の内側 | 中 | §4、§8 |
| F5 r2db の pre_commit 後の例外で error 行が無い | 中 | §4 の実装要件 (pre_commit を最後の文へ) |
| F6 2-A の原子性 / F7 DELETE の grant | 中 | §5 の 2-A の形 (関数、DB の時計、sweep・DELETE なし) |
| F8 新条件の空振り | 中 | §6 の 1〜3 |
| F9〜F11 接続の見積もり、事実の細部、WP-4 の path | 低中〜低 | §3、§1、§2、§9 |

**2 回目 (2026-09-30、G1〜G11)**

| 指摘 | 重大度 | 反映 |
|---|---|---|
| G1 印 file は実配備の再起動で消える (systemd `RuntimeDirectory=`、Cloud Run、launcher の `restart()`) | 高 | M を採らない (§5)。1-B・1-C の欠点にも記載 (§4) |
| G2 2-B の上限は飢餓と sink 障害で崩れる | 高 | 2-B を監督案から外した (§5) |
| G3 新条件の順序と knob、WP-4 / WP-5 の並行 | 中高 | §6 の変異の註、§9 (直列) |
| G4 1-A' の切り替え条件が常に真、欠点の漏れ | 中高 | 1-A' を採らない (§4、§8) |
| G5・G6 M の走査の競合と失敗時の意味 | 中 | M を採らないので該当なし |
| G7 契約文案の版の限定、`version_binding`、宣言値の所在、語の定義 | 中 | §6 |
| G8 語彙の等式テストと superset 義務 | 中 | §4 の語彙、§9 の WP-4 |
| G9 新条件の細部 (印の行、合計 < M、rate の guard、専用の起動) | 低中 | §6 |
| G10 F5 の応答と reason_code | 低 | §4 (pre_commit を最後の文へ移し、応答を変えない) |
| G11 checkpoint 行の request_id、slot を握る時間 | 低 | 前者は 2-B を採らないので該当なし。後者は §4 の費用 |

**再確認 (2026-09-30、v0.3 に対して。H1〜H11)**

| 指摘 | 重大度 | 反映 |
|---|---|---|
| H1 rate の関数は SECURITY INVOKER で、2-A の前例ではない | 中高 | §5 の 2-A の形 (違う型と明記、DEFINER の完了条件) |
| H2 summary の件数の意味 / H3 summary event の識別と fields / H4 窓の決め方と直列化 | 中 | §5 の 2-A の形・窓・読み・件数の意味 |
| H5 契約文案は他の裁定と両立しない | 中 | §6 の前提、Q-4 |
| H6 実測の読みが数値を超える | 中 | §3、§5 の費用 |
| H7 `visibility_lag_ms` で足りる条件 / H9 grant と UNION の枝 | 低中・低 | §5 の読み |
| H8 PG を持たない plug | 低中 | §5 |
| H10 M の下限 | 低 | §6 の 1 |
| H11 replay の event、COMMIT の `QueryCanceled` | 低 | §4 |

レビュー担当が Q-3 の材料として出した混成案 (認証済みの key は毎回 audit 行、未認証だけ集約) は採らない: 2-A は両方を 1 つの機構で覆い、行数の bound も保つ。
