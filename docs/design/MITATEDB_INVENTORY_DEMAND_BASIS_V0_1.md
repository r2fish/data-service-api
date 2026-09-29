# MitateDB の Gate-0 inventory 項目 (8) の需要の基準 設計メモ（v0.2 (監督裁定 1〜16 を §10 に追記。本文は書き換えず §10 が優先する)）

## 0. 版数・位置づけ

- **v0.2 (監督裁定 1〜16 を §10 に追記。本文は書き換えず §10 が優先する) (2026-09-29)** 起票。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-113** (`RM`:533) の中の WP-7 (作業指示書 `docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md` の WP-7)。
- 依頼者裁定: 同作業指示書 §6.1 の「依頼者裁定 (2026-09-29) と監督裁定 51」(`WO113`:481-488)。逐語「(A)で進めてください」(`WO113`:485) は、R-113 の中で inventory の需要の算術を起動時の検査と同じ基準に揃えることを指す。再審議しない (`OC` §1.7 の 51)。依頼者判断待ちの選択肢は無い。
- **行番号の木**: src と tests の `file:line` は、MitateDB の移植が入った木 (worktree `r113-wp3`、`c0abb3d`) のものである。「旧 code」の `file:line` は WP-7 の担当 worktree の基点 `bd961ac` の木 (移植前)、runbook の `file:line` は worktree `r113-wp5` (`9fb4920`) の木、設計文書と作業指示書の行は基点 `bd961ac` の木のものである。
- 公開規律: 数値はすべて本リポジトリの現物から読んだ値と算式である。本番の値・DSN・ホスト名・project 識別子を含まない (`OC` §1.9)。
- クラス D (R-113 全体。`WO113` §0)。設計レビュー 1 回。

**本書内の略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`WO113` = `docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md`、`MPW` = `docs/design/MULTI_PROCESS_WORKER_V0_1.md`、`RCL` = `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md`、`INV` = `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md`、`OPS` = `MitateDB-api/src/mitatedb_api/ops.py`、`PD` = `MitateDB-api/src/mitatedb_api/platform_declarations.py`、`CFG` = `MitateDB-api/src/mitatedb_api/config.py`、`TINV` = `MitateDB-api/tests/test_ops_inventory.py`、`THELP` = `MitateDB-api/tests/test_ops_help_text.py`、`CR` = `MitateDB-api/docs/cloud-run-cloud-sql.md`。「新しい code」= pool を thread limit から導く code (移植後)、「古い code」= pool を `concurrency` から導く code (移植前)。

## 1. 問題

- inventory の項目 (8) は接続の需要を宣言値の `concurrency` を基準に数える。api role は process あたり `_API_ROLE_STORE_COUNT` × `concurrency` (`OPS`:2636、:2640)、application role は process あたり `concurrency` (`OPS`:2659)。
- 起動時の検査 (F-16 / F-18) は thread limit 基準に改まった。pool = `role_pool_size(thread limit)` (`CFG`:335-370、`main.py`:388、`control_composition.py`:224-226、`OPS`:1499-1519)、床は `PD`:1072、:1102-1103、:1362-1363 (`MPW`:757 の裁定 16、`WO113`:433 の監督裁定 28)。
- 同じ process について inventory と起動時の検査が違う床を言う。既定の `concurrency` 32 では、古い 1 process + 新しい W process の rollout は W ≥ 2 で api role の 132 を超え (3 × 2 × 32 = 192)、必ず blocked になる (`CR`:2417-2423 が現状として開示)。MitateDB の multi-worker をゲート付きの手順 (`CR` §10) で配備できない。

## 2. 守るべき条件

1. inventory は読み取りだけ (現行のまま)。
2. 需要を実際より小さく数えない。分からないときは `unknown`、足りないときは `blocked` (現行の語彙のまま。`OPS`:2129)。
3. 入力は運用者が声に出して宣言する (CLI は稼働中の process の env を観測できない)。省略を既定値で埋めない。
4. 起動時の検査と inventory が、同じ revision の同じ process について違う床を言わない。
5. 契約 1.11.0・conformance・Security Invariants は変えない。
6. rollout の重なりで保つもの・保たないものの規律 (台帳 R-52、`RM`:472) は変えない。
7. r2db は inventory を持たないので対象外。

## 3. 現物の事実 (file:line)

### 3.1 inventory の項目 (8) (新しい code の木)

| 事実 | 出所 |
|---|---|
| 引数 7 つ。`--concurrency`・`--data-process-ceiling`・`--data-process-count-total`・`--control-process-ceiling`・`--control-process-count-total` は正の整数 (`_inventory_positive_int`、0・負・非整数は終了コード 1)。`--reserved-connections` は 0 以上。`--control-not-deployed` は flag | `OPS`:3312-3352、:2174-2204、:3355-3363 |
| 入力の形の検査は DB 接続の前に行い、誤りは固定文言で終了コード 1 (`--control-not-deployed` と control の 2 引数の排他、合計 < ceiling の拒否) | `OPS`:2957-2984、:2995 |
| `concurrency` の省略は `unknown`。data の 2 引数・control の 2 引数 (未配備の宣言が無いとき) の省略も `unknown` | `OPS`:2583-2588 |
| api の床 = `_API_ROLE_STORE_COUNT` × `concurrency`、controlplane = `_CONTROLPLANE_ROLE_POOL_FLOOR`、auditreader = `_AUDITREADER_ROLE_POOL_FLOOR` (いずれも process あたり) | `OPS`:2636-2638 |
| 需要: api = data 合計 × api の床、controlplane / auditreader = control 合計 × 床 (auditreader は role が在るときだけ)、application role = data 合計 × `concurrency` | `OPS`:2640-2646、:2659 |
| 条件 1: role ごとに `CONNECTION LIMIT` ≥ 需要 (`-1` は先に `unknown`) | `OPS`:2633-2634、:2648-2662 |
| 宣言 `process_ceilings` との比較は各 revision 単体の上限 (`--*-process-ceiling`) で行う | `OPS`:2681-2687 |
| 条件 2: 合計需要 = api + controlplane + auditreader + application の需要 (登録が在れば 1 回だけ) + `_INVENTORY_MAX_CONCURRENT_CONNECTIONS` (2)。合計 + `--reserved-connections` ≤ `SHOW max_connections` | `OPS`:2122、:2590-2596、:2692-2699 |
| 出力は `judgment`・`remediation_required`・`control_deployed` の 3 key | `OPS`:2580-2581 |
| テスト: `TINV` は 117 本、うち `test_inventory_connection_headroom*` 38 本。入力の既定は `_HEADROOM_OK` (`concurrency=2`、ceiling = 合計 = 1) | `TINV`:289-299 |
| 引数の dest の集合を固定する静的テスト | `TINV`:480-489 |
| `--data-process-count-total` / `--control-process-count-total` の help は確定文言として逐語で pin されている | `THELP`:75-98 |

### 3.2 起動時の検査 (新しい code の木)

| 事実 | 出所 |
|---|---|
| `role_pool_size(thread_limit)` = `thread_limit` + `_POOL_SIZE_HEADROOM` (2) | `CFG`:304、:370 |
| thread limit の既定 `DEFAULT_THREAD_LIMIT` = 4。data は `MITATEDB_THREAD_LIMIT` を読み、未設定・空は既定、不正値は起動失敗 | `http.py`:252、`main.py`:313、`CFG`:307-332 |
| data の pool = `role_pool_size(thread_limit)`。ただし `MITATEDB_PLATFORM_POOL_SIZE` が在ればそれが勝つ。F-16 / F-18 に渡すのは `role_pool_size(thread_limit)` の方 | `main.py`:388-390、:482-490 |
| 新しい code は `MITATEDB_WORKERS` を必須にする (未設定・空・0・負・非整数は起動失敗) | `main.py`:234-246、:344 |
| F-16 の床: api = `_API_ROLE_STORE_COUNT` × `pool_size` × `process_ceilings.data`、controlplane = 16 × `process_ceilings.control`、auditreader = 4 × `process_ceilings.control`、application の runtime / developer = `pool_size` × `process_ceilings.data` | `PD`:923、:933、:940、:1072、:1077、:1084、:1102-1103 |
| F-16 は床を関数の中で計算し例外で返す。床の値を返す関数は無い | `PD`:999-1104 |
| F-18 の下限 = data × (`_API_ROLE_STORE_COUNT` × p + (登録 ≥ 1 なら 2 × p)) + control × 16。auditreader は下限に入らない | `PD`:1230-1255、:1361-1373 |
| control の F-16 / F-18 も `role_pool_size(thread limit)` を渡すが、control の床は定数 (16 / 4) で `pool_size` に依らない | `control_composition.py`:212-235、`PD`:1077、:1084 |

### 3.3 古い code (基点 `bd961ac` の木)

| 事実 | 出所 |
|---|---|
| `role_pool_size(config)` は `config.max_concurrency` を返す。既定 32 | `CFG`:300-319、:79 |
| data の pool の既定 = `role_pool_size` (= `concurrency`)、`MITATEDB_PLATFORM_POOL_SIZE` が勝つ | `main.py`:345-349 |
| F-16 の床: api = 2 × `concurrency`、controlplane 16、auditreader 4、application = `concurrency` (process 数の倍率は無い) | `PD`:1052、:1057、:1064、:1082 |
| `MITATEDB_WORKERS` を読まない (`main.py` に該当 0 件) | `main.py` |

- control の床は古い code でも新しい code でも定数 16 / 4 で、`concurrency` にも thread limit にも依らない。**D-5 は現物と合う。**

### 3.4 上限の値

| role | `CONNECTION LIMIT` (0014) | 出所 |
|---|---|---|
| `mitatedbsvc_api` | 132 | `MitateDB-api/migrations/0014_role_connection_limits_rollout.sql`:89 |
| `mitatedbsvc_controlplane` | 36 | 同 :90 |
| `mitatedbsvc_auditreader` | 12 | 同 :91 |
| 各 application の runtime / developer | 68 | 同 :113、:116 (将来分 :175、:181、:188、:194) |

### 3.5 runbook の現状 (`r113-wp5` の木)

- process 数 = 各 revision の maxScale × その revision の worker 数。worker 数は `MITATEDB_WORKERS`、無ければ `WEB_CONCURRENCY`、それも無ければ 1 (`CR`:2402-2415)。
- 「Demand is still counted from `concurrency`」の開示 (`CR`:2417-2423)。
- env の値の許可表は `MITATEDB_MAX_CONCURRENCY` の 1 行だけで、「表に無い env 名の値は読まない」と書く (`CR`:2313-2320)。
- §10.10 の前提条件の算術と worked example は `concurrency` 基準 (`CR`:2855-2918)。§6.5 の接続予算の表は thread limit 基準 (`CR`:1666-1700)。
- step 13 は候補の `MITATEDB_MAX_CONCURRENCY` と `MITATEDB_WORKERS` を読み返す (`CR`:3590-3614)。
- §10.8 の §10.10 の行は Current version 8、not accepted (`CR`:2729-2740)。

## 4. 決定

### D-1 新しい code の process の需要は F-16 の床と同じ式・同じ定数から導く

- process あたり: api = `_API_ROLE_STORE_COUNT` × `role_pool_size(thread limit)`、application role = `role_pool_size(thread limit)`、controlplane = `_CONTROLPLANE_ROLE_POOL_FLOOR`、auditreader = `_AUDITREADER_ROLE_POOL_FLOOR`。
- inventory は式を複製せず、F-16 が使う関数 (`config.role_pool_size`) と定数 (`platform_declarations._API_ROLE_STORE_COUNT` ほか) を呼ぶ (条件 4)。F-16 の本体には床の値を返す関数が無い (§3.2) ので、本書の範囲では「同じ関数・同じ定数を名前で引き、積は inventory の中に置く」形になる。これで足りるかは §9 の 2。

### D-2 需要は revision の基準ごとに数えて足す

- rollout の最初の 1 回は、古い code の revision と新しい code の revision が並ぶ。古い code の process の実需要は `concurrency` 基準のまま (api 2 × `concurrency`、application role `concurrency`。§3.3) なので、全 process を新しい基準で数えると需要を小さく数える (条件 2 に反する)。
- 記号: O = 古い基準の data process 数、N = 新しい基準の data process 数、c = `concurrency`、p = `role_pool_size(thread limit)`、A = `_API_ROLE_STORE_COUNT` (2)。

```text
api 需要                 = O × (A × c) + N × (A × p)
application role 需要    = O × c       + N × p          (runtime / developer のそれぞれ)
controlplane 需要        = control 合計 × 16             (D-5。基準の区別なし)
auditreader 需要         = control 合計 × 4              (同上。role が在るときだけ)
合計需要 (条件 2)        = api + controlplane + auditreader
                           + application role 需要 (登録が在れば 1 回だけ。現行の数え方のまま)
                           + _INVENTORY_MAX_CONCURRENT_CONNECTIONS (2)
```

- O = 0 のとき c は式に現れない。

### D-3 入力

- 運用者が明示する: 新しい基準の thread limit (`--thread-limit`)、基準ごとの data process 数。古い基準の process 数は 0 を明示できる。O ≥ 1 のときだけ `--concurrency` が要る。要る入力の省略は `unknown` (条件 3)。入力の形の誤りは DB 接続の前に終了コード 1 (現行の流儀、§3.1)。
- 引数の形は両論 (起草者の案。裁定は監督):

| 案 | 引数 | 合計と内訳の検査 | 利点 | 欠点 |
|---|---|---|---|---|
| **(甲)** 合計を保ち内訳を足す | 既存の 7 つ + `--thread-limit N` (正の整数) + `--data-process-count-old-basis N` (0 以上の整数、`_inventory_nonnegative_int` と同じ扱い)。N = `--data-process-count-total` − O | O > 合計 は終了コード 1 | 確定文言の help (`THELP`:75-86) と runbook の合計の算出 (`CR`:2425-2464) を変えずに済む。足すのは内訳の 1 行 | 合計と内訳の整合の検査が 1 つ増える |
| **(乙)** 合計を内訳に置き換える | `--data-process-count-total` を外し、`--data-process-count-old-basis N` (0 以上) と `--data-process-count-new-basis N` (正の整数) + `--thread-limit N`。合計は 2 つの和 | 和の整合の検査は不要 | 入力が基準ごとの数だけになる | 確定文言の help と既存テスト (`THELP`:75-86、`TINV`:480-489) と runbook の §10.5 の script (`CR`:2535-2542) を置き換える。確定文言の差し替えが要る (`OC` §1.5 の 35) |

- 両案に共通の検査の案 (枠に無いので裁定を要する。§9 の 5・6):
  - 候補は常に新しい基準である (D-4: 新しい code は `MITATEDB_WORKERS` を必須にする) ので、N < `--data-process-ceiling` は入力の形の誤り (終了コード 1) とする案。
  - O = 0 で `--concurrency` が与えられたとき、(a) 終了コード 1 で拒否する / (b) 受け取って使わない、の両論。
  - `--thread-limit` の省略: N ≥ 1 のときは `unknown`。候補が新しい基準なので N ≥ 1 は常に成り立つ。
- 出力の形 (`OPS`:2580-2581 の 3 key) は変えない (枠に出力の変更が無い)。

### D-4 revision の基準の見分け方 (runbook に書く)

- revision の env に `MITATEDB_WORKERS` が在れば新しい基準 (新しい code は必須にする。`main.py`:344)、無ければ古い基準。
- process 数は各 revision の maxScale × その revision の worker 数。古い基準の revision は worker 1 (枠)。現行の runbook は `WEB_CONCURRENCY` を読む (`CR`:2409-2413)。食い違いは §9 の 7。
- 新しい基準の revision の thread limit は `MITATEDB_THREAD_LIMIT` の値。未設定の revision の扱いは §9 の 4 (両論)。

### D-5 control plane は基準の区別を要らない

- control の床は古い code でも新しい code でも定数 16 / 4 で、`concurrency` にも thread limit にも依らない (§3.2、§3.3 で現物確認)。`--control-process-count-total` の意味は変えない。

### D-6 application role の床は F-16 と同じ `role_pool_size(thread limit)`

- MitateDB の application role の実需要は process あたり永続接続 1 本 (監督保管 `r113_wp3_code_review_1.md` の F6、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:294-295) で、床はそれより大きい。保守側であり、起動時の検査と同じ床を言う (条件 4) ことを優先する。床を実需要に寄せる件は本 WP の範囲外。

### D-7 検算

- §5 の表のとおり。

### D-8 クラスと受理

- クラス D (R-113 全体)。設計レビュー 1 回。
- runbook §10 の表の版数が上がる。§10.8 は「not accepted」のまま統合し、再受理は依頼者が行う (`WO113`:488)。

## 5. 検算の表

- 前提: 0014 の値 (§3.4)、thread limit 4 → p = 6、古い基準の c = 32、登録 application ≥ 1。process あたりの床: 古い api 2 × 32 = 64、古い application 32、新しい api 2 × 6 = 12、新しい application 6。

### 5.1 条件 1 (role ごと)

**(i) 古い 1 process (c = 32) + 新しい W process (thread limit 4)**

| role | 需要 | 上限 | 収まる W |
|---|---|---|---|
| api | 64 + 12W | 132 | 12W ≤ 68 → **W ≤ 5** |
| application | 32 + 6W | 68 | 6W ≤ 36 → W ≤ 6 |
| 結論 | | | **W ≤ 5** |

**(ii) 新しい V process + 新しい W process (新しい code どうしの rollout)**

| role | 需要 | 上限 | 収まる V + W |
|---|---|---|---|
| api | 12 (V + W) | 132 | V + W ≤ 11 |
| application | 6 (V + W) | 68 | V + W ≤ 11 (11.33) |
| 結論 | | | **V + W ≤ 11**。V = W (同じ大きさの入れ替え) なら **W ≤ 5**。V = 1 なら W ≤ 10 |

**control (D-5。(i)(ii) に共通)**: controlplane 16 × C ≤ 36 → C ≤ 2、auditreader 4 × C ≤ 12 → C ≤ 3。C = control の合計。control の 1 process の入れ替え (C = 2) は収まる。

**対照 (採らない数え方)**

| 数え方 | (i) の api の需要 | 収まる W |
|---|---|---|
| 現行 (全 process を `concurrency` 基準) | 64 (1 + W) | W ≤ 1 (W = 2 で 192 > 132) |
| 全 process を新しい基準 (却下。§6) | 12 (1 + W) | W ≤ 10 (古い 1 process を 12 と数え、実需要 64 を 52 小さく数える) |

### 5.2 条件 2 (`max_connections`)

- M = `max_connections`、R = `--reserved-connections`。control の需要 = 20C (16C + 4C)。
- (i): 合計需要 = (64 + 12W) + 20C + (32 + 6W) + 2 = **98 + 18W + 20C**。条件は 98 + 18W + 20C + R ≤ M。
- (ii): 合計需要 = 12 (V + W) + 20C + 6 (V + W) + 2 = **18 (V + W) + 20C + 2**。
- 登録 application が 0 のときは application の項 ((i) で 32 + 6W、(ii) で 6 (V + W)) が消える。
- 条件 2 を通すのに要る M − R の最小値 (C = 2):

| W | (i) 98 + 18W + 40 | (ii) V = W: 36W + 42 |
|---|---|---|
| 1 | 156 | 78 |
| 2 | 174 | 114 |
| 3 | 192 | 150 |
| 4 | 210 | 186 |
| 5 | 228 | 222 |

- 本番の `max_connections` と予約はリポジトリに無い (`RCL`:96)。

## 6. 却下した代替案

| 代替案 | 理由 |
|---|---|
| 全 process を新しい基準で数える | 最初の rollout で古い revision の需要を小さく数える (D-2。§5.1 の対照で古い 1 process あたり 52) |
| `--concurrency` を小さく偽って通す運用 | 入力が事実でなくなる |
| inventory が revision の env を自分で読む | inventory は DB 層の読み取りだけで、Cloud Run の API を呼ばない (現行の設計の境界。`INV` §4 D-1、`INV`:107-112) |
| CONNECTION LIMIT を上げる migration を足す | 0014 の値は thread limit 基準なら値を上げる理由が無い (枠の理由の文言と §5.1 の数の関係は §9 の 1) |

## 7. 壊すとどう見えるか

| 外す決定 | 何が起きるか | 赤になるべきテスト |
|---|---|---|
| D-1 (新しい基準の床を p から導く) を `thread_limit` や `concurrency` に置き換える | 起動時の F-16 が通す role の上限で inventory が blocked / confirmed を違えて言う (条件 4) | 新しい基準だけの入力で、上限をちょうど F-16 の床に置いた cluster で confirmed、1 引いて blocked を観測し、同じ cluster で F-16 も通る / 止まることを確かめるテスト (api と application の 2 本) |
| D-1 の「同じ関数・定数を引く」を外し、inventory に `thread_limit + 2` 等を書き写す | 将来 `_POOL_SIZE_HEADROOM` や `_API_ROLE_STORE_COUNT` を変えたとき inventory だけ古い床を言う | inventory の項目 (8) が `role_pool_size` と `_API_ROLE_STORE_COUNT` を名前で参照し、数値の直書きが無いことを確かめる AST の静的テスト |
| D-2 (基準ごとに足す) を外し全 process を新しい基準で数える | 最初の rollout で古い revision の需要を 52 / process 小さく数え、PostgreSQL の `too many connections for role` が負荷時に出うる状態を confirmed と言う (条件 2) | O = 1、c = 32、N = W の入力で、上限を D-2 の需要ちょうどに置いて confirmed、1 引いて blocked (api と application の 2 本)。条件 2 は `--reserved-connections` を合計需要の境に置く 1 本 |
| D-2 の古い基準の床を外す (古い process を `concurrency` 以外で数える) | 同上 | 既存の `concurrency` 基準のテスト (O = 合計の入力に直したもの。例 `TINV`:1777 の 2 × `concurrency`) |
| D-3 の省略の規則 (O ≥ 1 で `--concurrency` 省略、`--thread-limit` 省略、O の省略) を既定値で埋める | 運用者が宣言していない値で判定する (条件 3) | それぞれの省略で `unknown` を観測するテスト (3 本) |
| D-3 の O = 0 で `--concurrency` を要しない、を外す | 全 revision が新しい code の配備で、読んでも意味の無い値を要求し `unknown` で止まる | O = 0・`--concurrency` 無しで judgment が出る (`unknown` でない) テスト |
| D-3 の入力の形の検査 (O > 合計、N < ceiling) を外す | 事実でありえない入力で判定する | 終了コード 1 と、DB 接続を開かないことを観測するテスト |
| D-5 (control は基準の区別なし) を外し control の床に p や c を掛ける | control の需要が thread limit や `concurrency` で動く | thread limit と `concurrency` を変えても control の境 (36 / 12) での判定が動かないテスト |
| D-6 (application の床 = p) を実需要 1 に寄せる | F-16 が止める上限で inventory が confirmed と言う (条件 4) | D-1 の application の境のテスト |

## 8. レビューで確かめてほしい点

1. D-2 の式が、古い code の実需要 (§3.3) を小さく数える経路を持たないか。特に `MITATEDB_PLATFORM_POOL_SIZE` (§3.2、§3.3) と、traffic を取れない古い revision の `concurrency` (§9 の 9)。
2. D-1 の床と F-16 の床が、同じ revision の同じ process について一致するか (api・application・controlplane・auditreader の 4 つ)。
3. §5 の数値の再計算。特に (i) の W ≤ 5 と、対照の W ≤ 10 の食い違いの読み方 (§9 の 1)。
4. D-3 の (甲)(乙) の比較に抜けている利点・欠点が無いか。
5. D-4 の見分け方が、古い image と新しい image の起動の実際 (新しい image の `CMD` は `--workers "${MITATEDB_WORKERS}"`、古い image は `--workers` を渡さない) と合うか。
6. 条件 2 の application の数え方 (登録が在れば 1 回) と F-18 の pair (2 × p) の差 (§9 の 3) が、条件 4 に反するか。
7. 条件 6 (R-52 の規律) を変えていないか。

## 9. 起草の疑義 (枠の矛盾・欠落・現物との食い違い。本文は枠に従った)

1. **却下案「CONNECTION LIMIT を上げる migration を足す」の理由の数**: 枠は「thread limit 基準なら worker 10 まで収まる」とする。この 10 は古い 1 process も新しい基準 (12) で数えた値 (監督保管 `r113_wp5_code_review_1.md` の F3 の算術 (1 + W) × 12 ≤ 132) で、D-2 が却下する数え方である。D-2 の下では最初の rollout で W ≤ 5、新しい code どうしで V + W ≤ 11 (V = W なら W ≤ 5。§5.1)。runbook §6.5 も「`MITATEDB_WORKERS` up to 5」と書く (`CR`:1691-1697)。「migration は要らない」の結論が W ≤ 5 の範囲で成り立つことは変わらないが、理由の文言は監督の訂正を要する。
2. **D-1「式を複製せず、F-16 が使う関数・定数を呼ぶ」**: F-16 には process あたりの床を返す関数が無い (`PD`:1072、:1102-1103 で積を関数内に書く)。触ってよいパス (`OPS`・`TINV`・`THELP`・runbook・`INV`) の中では「同じ関数・定数を引き、積は inventory に置く」までしかできない。(a) この形で足りる (AST の静的テストと境界の一致テストで固定) / (b) `PD` に床の helper を足して F-16 と inventory が共に呼ぶ (`PD` が触ってよいパスの外。r2db の同名関数との同型性の扱いも要る)、の両論。
3. **条件 4 は条件 2 (合計) にも掛かるか**: F-18 の下限は data process あたり application の pair (2 × p、`PD`:1363) を足し、inventory の条件 2 は application の需要を 1 role 分・1 回だけ足す (`OPS`:2692、`INV` の裁定 Z-27)。D-1 で role ごとの床は揃うが、合計では F-18 の方が process あたり p 大きい (古い code でも同じ形の差があった。基点 `bd961ac` の `PD`:1336 の `2 × concurrency`)。枠は条件 2 の application の数え方を決めていない。本書は現行 (Z-27) のまま書いた。
4. **thread limit の読み方 (枠に無い)**: 新しい基準の revision が `MITATEDB_THREAD_LIMIT` を持たないとき、(a) `--thread-limit` を省いて `unknown` (`--concurrency` の現行の規則 `CR`:2401 と同じ。候補の deploy に明示を要する) / (b) code の既定 4 (`http.py`:252) を運用者が出所付きで宣言する、の両論。新しい基準の revision どうしで値が違うとき、(a) 省く / (b) 最大値を使う、の両論。
5. **N < ceiling を拒否する検査 (枠に無い)**: D-4 から候補は常に新しい基準なので、D-3 に案として置いた。採るかは裁定を要する。
6. **O = 0 で `--concurrency` が与えられたとき (枠に無い)**: 拒否 / 無視の両論 (D-3)。
7. **古い基準の revision の worker 数**: 枠 D-4 は「worker 1」、現行の runbook は `MITATEDB_WORKERS` が無ければ `WEB_CONCURRENCY`、それも無ければ 1 (`CR`:2409-2413。古い image は `--workers` を渡さず uvicorn が `WEB_CONCURRENCY` を読む)。`WEB_CONCURRENCY` を持つ古い revision を 1 と数えると需要を小さく数える (条件 2)。どちらに揃えるかは裁定を要する。
8. **`MITATEDB_PLATFORM_POOL_SIZE`**: 新旧どちらの code でも、この env が在れば pool はそれになる (§3.2、§3.3) が、F-16 も D-1 / D-2 の式も `role_pool_size` で数える。値が p (古い code では c) より大きい revision では需要を小さく数える (条件 2)。現行から在る穴で、枠に扱いが無い。runbook で「在れば省く」とするか、範囲外として記録するかは裁定を要する。
9. **traffic を取れない古い revision の `concurrency`**: 現行の runbook は、合計に数えるが traffic を取れない revision (minScale ≥ 1、percent 0、tag 無し) の値を比べない (`CR`:2401)。D-2 はその revision も `--concurrency` で数えるので、その revision の値の方が大きいと需要を小さく数える。現行から在る穴。
10. **env の許可表**: `CR`:2313-2320 は `MITATEDB_MAX_CONCURRENCY` だけを載せ「表に無い env 名の値は読まない」と書くが、`CR`:2409-2413 は `MITATEDB_WORKERS` と `WEB_CONCURRENCY` を読む (WP-5 の木)。WP-7 は `MITATEDB_THREAD_LIMIT` を足す。`MITATEDB_WORKERS` / `WEB_CONCURRENCY` の行も WP-7 で足すかは裁定を要する (WP-5 の残りの可能性)。
11. **設計の置き場**: `WO113`:488 の監督裁定 51 は「設計は `RCL` の追補」とする。本書は別ファイルで起こした (発注の指示)。裁定 51 への訂正註か、`RCL` からの指し先が要る。
12. **「設計 §10 の裁定 16・28」**: `MPW` §10 の裁定 16 (`MPW`:757) は接続予算の件だが、`MPW` §10 の裁定 28 (`MPW`:796) は slot ファイルの件である。接続予算の倍率の件は `WO113` §6.1 の監督裁定 28 (`WO113`:433)。本書は後者を指した。
13. **runbook の重なり**: WP-7 と WP-5 は `CR` を共に触る (§1.2 の 16)。WP-7 は WP-5 の統合の後に直列で行う必要がある (`WO113` §2.1 は WP-7 を WP-3 の後とだけ書く)。
14. **確定文言**: (甲) は既存の確定文言の help を変えないが、新しい引数の help と runbook の新しい段の文言は `OC` §1.5 の 35 の確定文ファイルを要するか、実装担当の起草でよいかの指定が無い。
15. **`security/CONTROL_MAPPING.md` の追随**: 同書の SI-08 の MitateDB の写像は「`concurrency` の省略は unknown」(r113-wp3 の木の :852) と「`concurrency=32`・合計 2 で confirmed、合計 3 で 3 × 2 × 32 = 192 により blocked」(同 :859-860) を主張し、Evidence 欄は `TINV` の headroom のテスト名を引く (同 :868-889)。WP-7 の後、前者は O ≥ 1 のときだけの主張になり、後者は古い基準だけの入力の主張になる。`security/` は枠の触ってよいパスに無い (クラス D。`WO113` §9 の WP-6 が 3.7 を監督の作業とする)。WP-6 の触るパスと完了条件 175 に足すか、WP-7 に入れるかの指定が要る。WP-7 では、同書が引く test 名を改名・削除しないことを完了条件に置いた (作業指示書の節の案)。

## 10. 監督裁定 (v0.2、2026-09-29。§9 の起草の疑義 1〜15 と D-3 の両論への裁定。本文と食い違うときは本節が優先する)

1. (疑義 1) 枠の却下案の理由「worker 10 まで収まる」は誤りで、撤回する。10 は古い 1 process も新しい基準で数えた値であり、D-2 が却下する数え方である。正しくは §5.1 のとおり、最初の rollout (古い 1 process + 新しい W) で W ≤ 5、新しい code どうしで V + W ≤ 11。「CONNECTION LIMIT を上げる migration を足さない」の結論は W ≤ 5 の範囲で成り立つ。それを超える worker 数は、依頼者裁定 (2026-09-18) Q-2 のとおり同じ算式で上限を導く migration を要し、本 WP の範囲外である。
2. (疑義 2) (a) を採る。inventory は F-16 が使う定数 (`_API_ROLE_STORE_COUNT`・`_CONTROLPLANE_ROLE_POOL_FLOOR`・`_AUDITREADER_ROLE_POOL_FLOOR`) と `role_pool_size` を名前で引き、積は inventory に置く。一致は挙動で固定する: 同じ thread limit・同じ process 数について、F-16 (`check_role_connection_limits`) が通す最小の CONNECTION LIMIT と inventory が confirmed にする最小の CONNECTION LIMIT が、4 つの role class それぞれで等しいことを観測するテストを置く (条件 4)。`platform_declarations.py` に helper は足さない。
3. (疑義 3) 条件 2 (合計) の application の数え方は現行 (inventory の設計の裁定 Z-27) のまま変えない。F-18 の下限との差は着手前から同じ形で在り、inventory が confirmed と言った candidate を起動時の F-18 が止めることはあっても、その逆 (起動時の検査が通す構成を inventory が危険側に通す) は無い。差は設計レビューで確かめ、記録に残す (観察)。
4. (疑義 4) thread limit は (a) を採る。Gate-0 の対象になる新しい基準の revision は `MITATEDB_THREAD_LIMIT` を env に明示する。無ければ `--thread-limit` を省き `unknown` (`--concurrency` の現行の規則と同じ)。新しい基準の revision どうしで値が違うときは最大値を宣言する (需要を小さく数えない)。
5. (疑義 5) 採る。新しい基準の process 数が `--data-process-ceiling` より小さい入力は形の誤り (終了コード 1、DB 接続の前)。
6. (疑義 6) 古い基準の process 数が 0 で `--concurrency` が与えられたら、形の誤りとして拒否する (終了コード 1)。既存の「両立しない引数の組は拒否する」流儀に合わせる。
7. (疑義 7) 枠 D-4 の「古い基準の revision は worker 1」を訂正する。古い基準の revision の worker 数は現行の runbook のとおり `WEB_CONCURRENCY` が在ればその値、無ければ 1 (需要を小さく数えない)。
8. (疑義 8) `MITATEDB_PLATFORM_POOL_SIZE` を持つ revision が数える対象に 1 つでも在れば、runbook は (8) の入力を省かせ `unknown` とする。この env による pool の上書きを F-16 も数えないことは着手前から在る性質で、本 WP では変えない (観察として記録する)。
9. (疑義 9) `--concurrency` は、数える対象の古い基準の revision すべて (traffic を取れない revision を含む) の値の最大値を宣言する。runbook の該当の段をそう改める。
10. (疑義 10) runbook の env の許可表に `MITATEDB_WORKERS`・`WEB_CONCURRENCY`・`MITATEDB_THREAD_LIMIT`・`MITATEDB_PLATFORM_POOL_SIZE` の行を本 WP で足す。
11. (疑義 11) 設計は本書 (別ファイル) に置く。作業指示書 §6.1 の監督裁定 51 の「`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` の追補」は本書を指すと読み替え (訂正註)、同書には本書への指し先を訂正註で 1 行足す。
12. (疑義 12) 本書の読みが正しい。接続予算の倍率は作業指示書 §6.1 の監督裁定 28。
13. (疑義 13) 順は WP-3 → WP-5 → WP-7 の直列とする。
14. (疑義 14) 新しい引数の help と runbook の新しい段は実装担当が起草し、help は既存の help text のテストと同じ形で文字列を pin する。契約の文ではないので確定文ファイルは要らない。既存の確定文言の help は変えない。
15. (疑義 15) `security/CONTROL_MAPPING.md` の SI-08 の MitateDB の写像の追随は、記録の WP (作業指示書 §9) で監督が行う。本 WP は同書が引く test 名を改名・削除しない。
16. (D-3) 引数の形は (甲) を採る。既存の 7 つを保ち、`--thread-limit` と `--data-process-count-old-basis` を足す。新しい基準の process 数 = `--data-process-count-total` − 古い基準の process 数。古い基準の process 数の省略は `unknown` (0 は明示する)。
