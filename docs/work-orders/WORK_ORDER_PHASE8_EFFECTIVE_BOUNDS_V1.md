# フェーズ8 作業指示書 — 実効 bound と基盤衛生 (契約 1.6.0 不変)

- 版数: **v1.0 (2026-09-06、起草)**
- 正本設計: `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` (**v1.2、確定**)。**§5 の依頼者裁定 U-1 = (A)、U-2 = (A) は確定であり再審議しない** (計画文書 §9 手順 4)。**本書は WP 分割と発注のみを扱う** — 裁定の根拠・却下案・実装の具体形・命題の言葉遣いは設計文書が正本であり、本書はそれを重複させない。**設計と本書が食い違ったら設計が正であり、本書の誤りとして監督へ差し戻すこと** (フェーズ6 §11 L6-18 の流儀。訂正註は本書 §5 に置く)
- 上位計画: `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.1)。**§4 (P-1〜P-9)・§5 フェーズ8 節・§9 (着手手順) が正本**であり、設計 §1〜§2 がそれを転記済みである。本書は再導出しない
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260906_FABLE.md` (第 14 次)。**本フェーズは第 15 次引き継ぎを起こす** (WP-6)
- 体制: Fable 監督/判断/コミット、Sonnet 実装 (**コミットしない**)、Opus 起草/独立レビュー/受け入れ監査
- 先行作業指示書: `docs/work-orders/WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md` (v1.4)。**§0.1 の常設規律 7 項目・完了ゲートの実測規律・禁止事項・コミット規律・「完了条件番号 → 変異」対応表の書式を本書がそのまま引き継ぐ**
- 設計レビュー回数: **1 回** (契約を触らないフェーズ。計画文書 §9 の 3)。設計レビュー 1 回目の 18 件は設計 v1.1 に反映済みである。**追加の設計レビューは行わない**
- **確定文言のファイル所在**: **U-1 / U-2 の依頼者裁定の逐語は設計 §5**、その複製が `{scratchpad}/phase8-ruling-verbatim.txt` にある。**そこから複製し、言い換え・要約・語順の入れ替えを行わない** (常設規律 4)。**`hold_in_flight` の意味 1 文 (設計 §3 D-2 決定 1) と PERF 行の形式 (設計 §3 D-6) も同ファイルに逐語で置いた。** **C-05 行の新しい開示文だけは例外である** — 文言は WP-1 の実装担当が**実測後に**書き、監督が確認する (§2 WP-1b)

---

## 0. 前提と規律 (全 WP 共通)

### 0.0 前提

1. **正本設計は v1.2 である。** §3 の D-1〜D-6 は監督確定、§5 の U-1 / U-2 は依頼者裁定済みで確定である。**本書はその実施発注のみを書く。**
2. **前提となる main は `69c9e7a` 以降である** (設計 v1.1 のマージ)。**起草時点の main は `845d0a1`** (設計 v1.2 のマージ) であり、**着手はこの head 以降で行う**。
3. **作業 branch は `phase8-effective-bounds` である。** 監督が main から切る。
4. **worktree 規則**: **WP ごとに `.claude/worktrees/phase8-wpN` を `phase8-effective-bounds` から切る。** 完了後に**監督が branch へ取り込む**。**共有ツリー (`<REPO_ROOT>` = リポジトリルートの作業ツリー) を checkout しない** — 同一ディレクトリで動く別チャットと衝突する (第 14 次 §4-3、SHARED-CHECKOUT RULE)。**merge は専用の別 worktree 経由で行い、branch の確認は commit と同一コマンドで行う。**
5. **並行 worktree の着手前に「触るファイルの重なり 0」を確認する** (設計 §8.1 の表を実ファイル名で照合する)。**重なりが見つかったら実装に入る前に監督へ上げる。**
6. **設計 §8.1 が確認済みの重なり 0 のうち、1 点だけ運用で守るものがある** — **WP-1 と WP-4 はともに `MitateDB-api/tests/` にファイルを足す。** **WP-1 は limit 系、WP-4 は ops 系のファイル名にする** (設計 §8.1)。**同一ファイルに両者が書き込まない。**
7. **契約は 1 バイトも変えない。** `spec/data-service-api.v1.json` と両 peer の packaged 複製 2 本は**全 WP を通じて無変更**である (設計 §2 C1、U-2 = (A))。**新しい Security Invariant も足さない** (C2)。**新しい共通条件 (C-20 以降) も足さない** (設計 §6.6)。

### 0.1 常設規律 (フェーズ7 §0.1 を逐語継承。全 WP に適用)

1. **空振り禁止**: 新規テストは観測対象が 1 件以上あることを assert する (パラメータ化された全 plug/adapter で)。「このテストは X を固定する」と書くなら、X を壊す変異を全 plug で赤にした実測を報告に添える。
2. **変異先行**: 完了条件 1 項目につき、それだけを壊す変異を 1 つ対応付ける。対応する変異の無い完了条件は残さない。
3. **主張は実測の後**: docstring / CONDITIONS / runbook の断言 (「load-bearing」「必ず赤」等) は変異結果を得た後に、その数値・テスト名を引用して書く。レビュー・監査は「主張 vs 実測」を独立項目として突合する。
4. **確定文言はファイル経由**: 依頼者確定の契約文・裁定文は scratchpad の確定文ファイルから複製し、言い換えない。契約側には確定文を逐語 assert する文字列ピンのテストを置く。
5. **設計外の拡張は実装前に上げる**: 設計に無い検査・機構は実装前に報告し、監督裁定を得てから実装する。
6. **同型性テスト**: 両 peer に同名で置くテストヘルパは、peer 名・パッケージ名・パス・空白を正規化して diff する同型性テスト (両 peer 同名 `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`) で一致を固定する。peer 間でコードを共有しない慣行は維持する (依頼者裁定 2026-09-03、案 (a))。
7. **実行規律**: テストは前景 Bash で直列、timeout パラメータ 600000 を明示、`ps` で他の pytest が無いことを確認してから。変異の復元は scratchpad backup からのコピー (`git checkout` 禁止)、`sleep 3` 後に sha256 を 2 回照合、変異文字列を全文 grep。

**対応表の書き方 (規律 2 の運用、フェーズ6 §0.1 を逐語継承)**: 各 WP の末尾に「完了条件番号 → 変異」の対応表を置く。**テストで固定される条件にはそれだけを壊す変異を 1 つ**対応付ける。**文書・記録・設定・無変更の条件には変異を作らず、「監査が何を何と突き合わせるか」を当該条件の本文に「監査照合」として明記する**。各 WP の最後の完了条件は「**対応表に対応の無い行が無いこと**」というメタ条件である。

**本フェーズでの適用**: 除外は無い — **WP-1a から WP-6 まで全 WP が対応表を持つ**。**変異を持たない完了条件については、設計 §9 の 6 に従い「照合対象の逐語記録 (実行したコマンドと集計行、または file:line) を設計 §11 に残すこと」自体を完了条件とする** — 受け入れ監査はその記録を逐語で報告に引く。

### 0.1b 速度規律 5 項目 (第 13 次 §2.4 / 第 14 次 §4-3 から転記。全 WP に適用)

1. **完了ゲートは監督が単独実行し、その集計行だけを正本にする。**
2. **subagent には suite 全体を回させず、対象ファイル・対象テストの前景直列実行に限る** (`timeout` 600000 明示)。
3. **レビュー・監査は `--collect-only -q` と静的照合を主とし、変異は自作分のみ最小回数。**
4. **時間を食う vector は「構成値に比例しない形」へ作り替える。**
5. **並列化は集計行が逐次と一致することを実測してから採る。**

**運用の前提 (第 14 次 §4-3)**: **共有 `.venv` を使う** (`./.venv/bin/python`、3.11)。システム python を使わない。**`.pre-commit-config.yaml` の local hook が staged なファイルに対して走る** (entry はシステム `python3`)。**ローカル PostgreSQL の `max_connections = 300` が前提である。** **完了ゲートは `ps` で他の pytest が 0 件であることを確認してから。** **変異の復元は scratchpad backup からの `cp` + `sleep 3` 後の sha256 二重照合 + コミット前の変異文字列の全文 grep** — **`git checkout --` は使わない** (本リポジトリは Google Drive 同期ツリーである)。**push 前に identity を確認する** (§4)。**GitHub Actions の job ログは run 完了後にしか読めない。workflow に concurrency の cancel が入っているので「赤」と「cancel」を取り違えない。**

### 0.2 WP-9 (フェーズ7 公開ゲート) との非干渉

- **本フェーズは WP-9 と並行できる** (設計 §8.1 最終行)。WP-9 が触るのは **`tools/rewrite_hash_refs.py` (新設)** と **`docs/` 配下の hash 参照の一括更新**のみである。
- **本フェーズは `tools/rewrite_hash_refs.py` を作らない。** WP-2 / WP-4 / WP-5 が `tools/` に足すのは `check_collection_floor.py` / `deploy_smoke.py` / `perf_baseline.py` の 3 本だけである。
- **本フェーズの文書に commit hash を書いた場合、WP-9 の commit-map 適用対象になるだけで衝突しない** (設計 §0 の最終箇条)。**hash を書くこと自体は禁止しない。**
- **WP-9 の着手合図が来たら、進行中の WP は worktree を畳んで待つ** — filter-repo の前に worktree を畳む必要があるためである (第 14 次)。**この判断は監督が行う。実装担当は自分で判断しない。**

### 0.3 本フェーズ固有の規律

1. **宣言と実装は同一コミットである** (P-3、設計 D-1)。`cell.py` の `limit_enforcement` の値の変更、その class の enforcement 実装、C-05 V3 の当該組の `_V3_KNOWN_UNAVAILABLE` からの削除は、**class ごとに 1 コミットに収める**。**先に宣言だけを `enforced` へ上げない。**
2. **`_V3_KNOWN_UNAVAILABLE` の削除は実装と同一コミットである。** `xfail(strict=True)` により順序を間違えれば必ず赤になる (実装が先なら XPASS で赤、削除が先なら通常の assert が赤)。**この赤を「順序の合図」として使い、`strict=True` を落として回避しない。**
3. **`skip` を使わない。** 非 enabled 側は skip せず、宣言の正直さを assert する (C-17 型)。**`skipped` は 0 のままである。**
4. **新しいテストに `@pytest.mark.condition(...)` を付けない** (設計 §6.5 / §6.6)。**`CONDITIONS.md` に新しい行を足さない。** 触るのは **C-05 行だけ**であり、それは WP-1b の範囲である。
5. **plug を増やさない** (4 plug のまま)。`tools/deploy_smoke.py` のローカル実証で uvicorn を起動するのは**運用道具の実証**であり、conformance の plug ではない (L7-2 はフェーズ10 の項目である)。
6. **`COLLECTION_FLOOR` を WP の途中で上げない。** 初期値は着手時点の実測 (**2274**) であり、**最終更新は監督が完了ゲートで行う** (設計 §6.4 / §9 の 4)。
7. **設計外の検査・機構を足す前に報告して裁定を待つ** (常設規律 5)。**とくに WP-1 は設計 D-1 / D-2 が形を細かく決めているので、「ついでに」の追加検査・追加 primitive・追加 bound を入れない。**

---

## 1. WP 一覧

| WP | 内容 | 主に触るファイル (設計 §8。存在を現物で確認済み) | 着手条件 | 並行 | 担当テンプレート |
|---|---|---|---|---|---|
| **WP-1a** | **L7-1 (MitateDB application plane の 4 class + `request_bytes` 副項目) + V3 撤去 + `test_c05:646-659` 撤去** | `MitateDB-api/src/mitatedb_api/config.py` / `cell.py` / `http.py` / `backend_postgres.py` / `backend_sqlite.py` / `main.py` / `service.py`、`MitateDB-api/tests/` (**limit 系のファイル名**)、`MitateDB-api/conformance/conformance_adapter_mitatedb.py` / `conformance_adapter_mitatedb_http.py` (隔離 profile のみ)、`conformance-tests/test_c05_limit_declaration_agreement.py` (`:646-659` 撤去と `_V3_KNOWN_UNAVAILABLE` の削減のみ) | branch 作成後 | **単独 worktree `phase8-wp1`。1a → 1b の直列 2 段** | Sonnet 実装 → Opus コードレビュー → Opus 証拠監査 |
| **WP-1b** | **port v1.12 (`hold_in_flight` + 要求側 optional フィールド) + `_drive_concurrency` + `result_items` 両側化 + L7-21 (peer 名分岐撤去・allowlist 静的 assert) + `CONFORMANCE_ADAPTER_V1.md` 改版 + C-05 行の書き換え** | `conformance-tests/adapter.py`、4 adapter (`*/conformance/conformance_adapter_*.py`)、`conformance-tests/test_c05_limit_declaration_agreement.py`、`conformance-tests/CONDITIONS.md` (**C-05 行のみ**)、`conformance-tests/CONDITIONS_HISTORY.md` (**`#c-05` へ L8-7 の訂正を逐語で移す**)、`docs/design/CONFORMANCE_ADAPTER_V1.md`、`r2db-api/conformance/conformance_adapter_r2db.py:148` / `conformance_adapter_r2db_http.py:758` (**隔離 profile の `concurrency` 値のみ。`r2db-api/src` は無変更**) | **WP-1a の完了後** (同一 worktree) | 同上 (直列) | 同上 |
| **WP-2** | **R-9 (テスト総数の下限) + L7-23 (register 収集 0 件ガード) + L7-22 注記** | `conformance-tests/COLLECTION_FLOOR` (新設)、`tools/check_collection_floor.py` (新設)、`.github/workflows/ci.yml`、`conformance-tests/test_conditions_register.py`、`conformance-tests/README.md` | branch 作成後 | **並行可** (worktree `phase8-wp2`) | 同上 |
| **WP-3** | **R-10 (A) provenance companion (契約 JSON 0 バイト不変)** | `spec/CONTRACT_HISTORY.md` (新設)、`conformance-tests/test_contract_history_register.py` (新設)、`spec/README.md` (1 段落追記) の **3 ファイルのみ** | branch 作成後 (**U-2 = (A) は確定済み**) | **並行可** (worktree `phase8-wp3`) | 同上 |
| **WP-4** | **R-11 (`ops verify-declarations` 両 peer 同型 + smoke test + backup/restore + argv secret 検査)** | 両 peer の `src/*/ops.py` / `platform_declarations.py`、両 peer の `tests/` (**ops 系のファイル名**)、`tools/deploy_smoke.py` (新設)、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh`、`r2db-api/migrations/0001_bootstrap_control_plane.sql` (**冒頭コメントの使用例のみ**)、`docs/ops/BACKUP_RESTORE_R2DB.md` (新設ディレクトリ)、`conformance-tests/test_deploy_secret_argv_scan.py` (新設) | branch 作成後 | **並行可** (worktree `phase8-wp4`) | 同上 |
| **WP-5** | **R-12 (性能基準値ハーネス)** | `tools/perf_baseline.py` (新設)、`tools/PERF_BASELINE_README.md` (新設) | branch 作成後 | **並行可** (worktree `phase8-wp5`)。**基準値の実測は完了ゲート (監督)** | 同上 |
| **WP-6** | **記録・第 15 次引き継ぎ・計画文書 §1 / §5 / §8 の改版 (L8-8: R-10 行と R-12 行) + `COLLECTION_FLOOR` 最終更新** | 設計 §10 / §11、`docs/design/ROADMAP_POST_PHASE7_V1.md`、`docs/work-orders/PHASE7…_V1.md` §11 相当の状態注記、`docs/work-orders/HANDOVER_20260906_FABLE.md` §4-2、`docs/work-orders/HANDOVER_2026MMDD_FABLE.md` (第 15 次、新設)、`conformance-tests/COLLECTION_FLOOR` (**監督のゲート作業**) | **WP-1〜WP-5 の完了後** | **最後** | Opus 起草 → 監督 → Opus 証拠監査 |

**依存順の根拠**

- **WP-1a → WP-1b は直列である。** `_drive_concurrency` は MitateDB 側の in-flight カウンタが実在しないと駆動できず (4 plug 全数で駆動する)、C-05 行の開示 (3)「`enforced` と宣言された class で V2 の検査形を持たないものが 0 件である」は **1b の `_drive_concurrency` が入って初めて真になる**。**したがって C-05 行を書き換えるのは 1b である** — 1a では `CONDITIONS.md` に触らない。
- **WP-2 / WP-3 / WP-4 / WP-5 は相互に独立である** (設計 §8.1 の重なり 0 表)。
- **WP-6 は最後である** — WP-1〜WP-5 の実測を設計 §11 に記録し、`COLLECTION_FLOOR` をゲート時の実測値へ締めるためである。

---

## 2. 各 WP の発注

### WP-1a L7-1 — MitateDB application plane の 4 class + `request_bytes` 副項目

#### 目的

**MitateDB の application plane に、r2db と契約上の意味が一致する enforcement を置く。** 拒否の位置・error code・`details.limit_class`・宣言語を r2db と一致させ (P-6)、**宣言を上げるコミットと実装を入れるコミットを同一にする** (P-3)。**これにより C-05 V3 の xfail 9 組が撤去可能になる。**

#### 前提として読む箇所 (設計)

**§1.2 (1)(2)(3)(4)**、**§3 D-1 全文** (決定の表・順序・カウンタのスコープ・置き場・実装の形 1〜8・検査の形・開示事項)、**§5 U-1 の依頼者裁定 (逐語)**、**§6.3**、**§7 の SI-08 段落**、**§10 L8-3 / L8-6**。

#### 成果物 (ファイル単位)

1. **`MitateDB-api/src/mitatedb_api/config.py`** — `FoundationConfig` に **4 フィールド**を足す: `max_requests_per_minute` / `max_concurrency` / `max_execution_ms` / `max_operation_depth` (U-1 = (A) 確定)。**既存フィールドと同じく既定値を持つ配備宣言**であり (`:20-35` の既定値群と同型)、**env 名の対応表 (`:106-109`) にも同型で足す**。**既存の `validate_request_size` (`:172-178`) は残す** — in-process の構造推定は cell 層に置く (バイト長ではなく構造推定であり、意味が違う)。
2. **`MitateDB-api/src/mitatedb_api/cell.py`** — **限度状態ホルダを新設する (1 プロセス 1 個)**。ホルダが持つのは **(i) rate 窓** (`principal.credential_id` をキーにした `dict[str, list[float]]` + `Lock`。**credential 単位**)、**(ii) in-flight カウンタ + `Lock` の contextmanager** (**プロセス = 配備単位**) である。**判定は `ApplicationRuntime.__authorize` (`:1348-1350`) の直後**に置く。**`ApplicationRuntime.__slots__` (`:1338`) は変更しない** — session はホルダに `self.__cell` 経由で到達する。**`ApplicationDeveloper` の schema 操作 (`:1543-1560`) も同じ gate を通る。** `limit_enforcement` ブロック (`:1494-1534`) と `limits` ブロック (`:1481-1493`) を**同一コミットで**更新する。
3. **合成根の配線 (同一コミット)** — `MitateDB-api/src/mitatedb_api/main.py` (`:391` `cells` / `:420` `ApplicationCell(...)` / `:446` `HttpService(...)`) と `MitateDB-api/src/mitatedb_api/service.py` (`:11` `ProvisioningFacade` / `:41` `self.cells` / `:72` `MitateDataService`) が**ホルダを 1 個だけ**構築し、**そのプロセスの全 `ApplicationCell` に同じ instance を渡す**。**`audit_dispatch.AuditRouter` と同じ注入経路をそのまま再利用する** (`cell.py:308-318` のコメントと `main.py` の配線)。**conformance 2 plug も同型に配線する** (`conformance_adapter_mitatedb.py:358` `ControlPlane(` / `:374` `MitateDataService(`、`conformance_adapter_mitatedb_http.py:651` `self._cells` / `:723-730` `_cell_factory` と `HttpService`)。**隔離 instance は自分専用のホルダを 1 個持つ** (`conformance_adapter_mitatedb.py:836` `isolated_application_surface`、`conformance_adapter_mitatedb_http.py:1477` 近傍) — **共有 adapter のホルダに触れない。**
4. **`MitateDB-api/src/mitatedb_api/backend_postgres.py`** — 実行前に **`SET LOCAL statement_timeout` / `lock_timeout` を残余から逆算して張り**、`psycopg` の `QueryCanceled` / `LockNotAvailable` を **`LIMIT_EXCEEDED`(`execution_ms`)** へ写す。**r2db `postgres.py:1936-1959` と同型だがコードは共有しない** (P-6)。
5. **`MitateDB-api/src/mitatedb_api/backend_sqlite.py`** — 変更は **app 側 deadline 検査の呼び出しのみ** (sqlite3 に query timeout API が無い)。
6. **`MitateDB-api/src/mitatedb_api/http.py`** — **`:591` の `request_bytes` 上書き行を削除する。** **middleware (`:208-293` の `RequestByteBoundMiddleware`) は残す。**
7. **`MitateDB-api/tests/`** — 4 class それぞれの peer-local テスト (**拒否位置・error code・`limit_class`・`finally` での解放**)、**順序の固定**、**request_bytes の二重層の応答同一性**。**ファイル名は limit 系にする** (WP-4 の ops 系と分ける。§0.0 の 6)。
8. **`MitateDB-api/conformance/conformance_adapter_mitatedb.py:837-847` と `conformance_adapter_mitatedb_http.py:1477-1478` 近傍** — 隔離 profile (`small_config`) に新フィールドの小さな値を与える。**すべての count 値は `_MAX_EXERCISABLE_LIMIT`(200、`test_c05:70`) 以下**にする。**`concurrency` は駆動で実際に N 本の要求を保持するので、スレッド数として現実的な小さい値 (例 3) を置く。** **`requests_per_minute` は 1b の headroom assert が通る値にする** (r2db 2 plug の現行値は 50: `conformance_adapter_r2db.py:150` / `conformance_adapter_r2db_http.py:757`)。
9. **`conformance-tests/test_c05_limit_declaration_agreement.py`** — **(a)** `:646-659` の V1 統制 assert (`if adapter.name == "MitateDB-api":` 以下) を**撤去する**、**(b)** `_V3_KNOWN_UNAVAILABLE` (`:700-710`) から**該当組を class ごとに削除する**。**この 2 つ以外は 1a では触らない** (driver の追加・peer 名分岐の撤去は 1b)。

#### 実装の指示

**順序 (設計 D-1「順序は r2db の実順序に一致させる」。逐語)**:

```
認証・認可 (__authorize / _require_data)
  → requests_per_minute        (credential 単位の窓)
  → concurrency 取得           (カウンタ + Lock、finally で解放)
  → request_bytes              (要求 dict の構造推定)
  → operation_depth            (U-1 (A) の場合のみ)
  → deadline = 受理時刻 + execution_ms を作って backend へ渡す
```

**これは本設計が新たに決めた順序ではなく r2db の現物の順序である** — `_slot` (`r2db-api/src/r2db_api/service.py:1133-1144`) が `_acquire_rate` (`:1156-1163`) → concurrency の順に置かれ、`_slot` の内側で `check_request` → `check_depth` → deadline 生成が並ぶ (`:996-999` / `:1037-1039` / `:1072-1074`)。**この順序を変えない。**

**class ごとの実現方式 (設計 D-1 の表。逐語)**

| class | 実現方式 (MitateDB) | 宣言値 | V2 駆動 | 撤去する xfail 組 |
|---|---|---|---|---|
| `requests_per_minute` | **credential_id 毎の 60 秒 sliding window** (r2db `service.py:1156-1163` と同型。control plane の**グローバル**窓 `control_plane.py:1162-1172` とは**別物**として置き、**control plane は変えない**) | **`enforced`** | 既存 `_drive_requests_per_minute` (`test_c05:359-401`) | `(MitateDB-api, requests_per_minute)` / `(MitateDB-api-http, requests_per_minute)` |
| `concurrency` | **in-flight カウンタ + `threading.Lock`** (r2db `service.py:1133-1144` と同型。**取得後は例外経路を含めて `finally` で必ず解放する**) | **`enforced`** | **1b の `_drive_concurrency`** | `(MitateDB-api, concurrency)` / `(MitateDB-api-http, concurrency)` |
| `execution_ms` | **二重構え** — (i) app 側 deadline 検査 (要求受理時刻 + `execution_ms` の wall-clock 判定、r2db `limits.py:73-75` と同型)、(ii) **PG backend では残余から逆算した `SET LOCAL statement_timeout` / `lock_timeout`**。**SQLite backend は app 側 wall-clock のみ** | **`reference_wall_clock`** (r2db `service.py:936-937` と同じ。**`enforced` にしない**) | **駆動しない** (V1 と V3 のみ) | `(MitateDB-api, execution_ms)` / `(MitateDB-api-http, execution_ms)` |
| `operation_depth` | **U-1 = (A) 確定。** r2db `limits.check_depth` (`limits.py:77-89`) と同型の**汎用再帰深さ検査** (要求 dict 全体への再帰、循環検出付き) を置く | **`enforced`** | 既存 `_drive_operation_depth` (`test_c05:299-356`) | `(MitateDB-api, operation_depth)` / `(MitateDB-api-http, operation_depth)` |
| **`request_bytes` (in-process、副項目)** | **r2db `limits.check_request` (`limits.py:37-70`) と同型の構造推定** — str は `len × 4`、bytes は `len`、scalar / None / bool は 8、container は 2 として積算し、**container の要素数が `bound // 8` を超えた時点で拒否**、総和が bound を超えた時点で拒否 | **`enforced`** (in-process 面も) | 既存 `_drive_request_bytes` (`test_c05:429-460`、**片側検査**) | `(MitateDB-api, request_bytes)` |

**`operation_depth` の実測分岐 (U-1 裁定の逐語に従う)**: 依頼者裁定は「xfail は 9 → 0 を目標とし、**in-process 経路に要求 dict が無い形であれば in-process 側の 1 組だけ `unavailable` を残して理由を C-05 行と §10 に開示する** (実装 WP が実測)」である。**どちらであるかを実装担当が事実として確かめ、根拠 (`file:line`) を完了報告と設計 §11.3 に書く。推測で決めない。** **既存 driver は N+1 を「同じ insert に `where` を足す」形で作るので、深さ検査が内容検証より前に走ることが要る** (`test_c05:299-356`)。**隔離 profile の `operation_depth` は 4 である** (r2db 2 plug と同じ。`test_c05:330-334` が 4 であること自体を assert する)。

**状態の置き場 (禁止形の明示)**: **`ApplicationRuntime` に状態を持たせない** — HTTP 面は `http.py:447` の `HttpService.authenticate` が**要求ごとに**新規構築し、in-process 面も `service.py:78` の `open_session` が**呼ばれるたびに**新しい session を返すので、session に窓やカウンタを持たせると要求ごとに初期化され、**宣言だけが `enforced` に上がって実挙動は無制限になる (P-3 違反)**。**`ApplicationCell` に置くのも禁止である** — 「application 単位」にしかならず、決定 (配備単位) を満たさない。

#### 完了条件 (assert 水準)

1. **`requests_per_minute` が credential 単位の 60 秒 sliding window で `enforced` である。** 宣言が `enforced` であり、`limits.requests_per_minute` が有限値 (integer ≥ 1) を持ち、**MitateDB 2 plug で `_drive_requests_per_minute` (`test_c05:359-401`) が真を返して N / N+1 の位置で `LIMIT_EXCEEDED` + `details.limit_class == "requests_per_minute"` が観測される**。
2. **`concurrency` の in-flight カウンタが上限で決定的に拒否し、例外経路を含めて `finally` で解放される。** peer-local テストが **N 本保持 → N+1 本目が `LIMIT_EXCEEDED` + `limit_class == "concurrency"` → 解放後 N 本が完了**を固定する。
3. **`execution_ms` が `reference_wall_clock` で宣言され、PG backend が `SET LOCAL statement_timeout` / `lock_timeout` を張り、`QueryCanceled` / `LockNotAvailable` を `LIMIT_EXCEEDED`(`execution_ms`) へ写す。** (peer-local。`MITATEDB_TEST_ADMIN_DSN` が要る)
4. **`request_bytes` が in-process 面でも `enforced` であり、構造推定が `bound // 8` の早期拒否を持つ。** MitateDB in-process plug が `_drive_request_bytes` (`test_c05:429-460`) の駆動対象に入り、真を返す。
5. **`operation_depth` が `enforced` であり、`_drive_operation_depth` (`test_c05:299-356`) が MitateDB plug で真を返す。** **`enforced` になった面 (in-process / HTTP) と、残った xfail 組があればその組を実測して設計 §11.3 に記録する。**
6. **限度状態ホルダが「1 プロセス 1 個」であり、合成根が構築して全 `ApplicationCell` に注入している。** 要求ごと・application ごとに初期化されない。
7. **拒否の順序が r2db の実順序と一致する** (rpm → concurrency → request_bytes → operation_depth → deadline)。peer-local テストが順序を固定する。
8. **`request_bytes` の二重層 (HTTP middleware と in-process 構造推定) の応答が同一である** — 「middleware が先に拒否する要求」と「middleware を通過して構造推定が拒否する要求」の**両方**が `LIMIT_EXCEEDED` + `details.limit_class == "request_bytes"` を返す (peer-local)。
9. **`http.py:591` の `limit_enforcement.request_bytes` 上書きが削除され、middleware (`:208-293`) は残っている。** — **監査照合**: 監査は `git diff -- MitateDB-api/src/mitatedb_api/http.py` が **上書き 1 行の削除に限られる**こと、middleware の本体が無変更であることを確認し、その diff を報告に逐語で引く (設計 §9 の 6)。
10. **`test_c05:646-659` の V1 統制 assert が撤去され、V1 (d) の命題は同テスト前半 (`:645` の `_assert_v1_self_consistency` 呼び出し) が全 plug に対して保持している。** **撤去後に「`unavailable` かつ `limits` 値を持つ」実例が 0 件になったことを実測して設計 §11.3 に記録する。**
11. **`_V3_KNOWN_UNAVAILABLE` (`test_c05:700-710`) から該当組が class ごとに削除され、その削除と実装が同一コミットである。** ゲート後の C-05 V3 の `xfailed` は **0** である (**U-1 裁定に従い、in-process の `operation_depth` 1 組だけが実測で残る場合は 1**)。
12. **隔離 profile の新フィールド値がすべて `_MAX_EXERCISABLE_LIMIT`(200) 以下であり、`concurrency` は 3 程度の小さい値である。**
13. **`already_consumed` (`test_c05:383`) の前提を MitateDB 2 plug について再測定した。** gate を `__authorize` の直後へ置いたことで前提が変わるか否かを実測し、**必要なら `:383` の式を能力/実測ベースへ直し、いずれの場合も測定結果を設計 §11.3 に記録する。** **判定条件**: 隔離 surface の `capability_document()` / `authenticate()` が**専用の probe application/credential** を使い回すなら (MitateDB in-process は `conformance_adapter_mitatedb.py:497-516` がその形)、drive が測る runtime credential の窓を消費しないので **0 のままでよい**。
14. **対応表に対応の無い行が無いこと** (メタ条件)。
15. **1a の部分ゲート** — `MitateDB-api/tests` と `conformance-tests/test_c05_limit_declaration_agreement.py` が `failed` 0 / `skipped` 0 / `xfailed` 0 (または 1) であること。**`passed` の増減内訳を完了報告に書く。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 `requests_per_minute` | **変異 1** |
| 2 `concurrency` | **変異 2** |
| 3 `execution_ms` | **変異 3** |
| 4 `request_bytes` (in-process) | **変異 4** |
| 5 `operation_depth` | **変異 5** |
| 6 ホルダが 1 プロセス 1 個 | **変異 6** |
| 7 拒否の順序 | **変異 7** |
| 8 二重層の応答同一性 | **変異 8** |
| 9 `http.py:591` の削除 | **監査照合** (設計 §9 の 6 に従い diff を逐語記録) |
| 10 `test_c05:646-659` の撤去 | **変異 9** |
| 11 V3 の撤去と同一コミット | **変異 10** |
| 12 隔離 profile の値 | **変異 11** |
| 13 `already_consumed` の再測定 | **監査照合** (実測記録。設計 §11.3 (i)) |
| 14 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 15 1a の部分ゲート | **監査照合** |

**変異 (「どのファイルのどの行をどう変える → どのテストが赤になる」)**

1. **`cell.py` の gate から rate 窓の判定 (60 秒窓の超過判定 `if len(window) >= bound: raise`) の 1 行を削除する** → `conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_v2_declaration_and_position_agree` が **`MitateDB-api` / `MitateDB-api-http` の 2 plug で赤** (`_drive_requests_per_minute` の位置 assert が落ちる)。
2. **`cell.py` のホルダの in-flight 上限判定 (`if self._active >= bound: raise`) の 1 行を削除する** → **MitateDB peer-local の concurrency テストが赤** (N+1 本目が拒否されない)。
3. **`backend_postgres.py` の `SET LOCAL statement_timeout` / `lock_timeout` を張る 1 行を削除する** → **MitateDB PG の peer-local `execution_ms` テストが赤** (長時間クエリが `LIMIT_EXCEEDED` にならない)。
4. **`cell.py` の構造推定から `bound // 8` の早期拒否 (container 要素数の判定) の 1 行を削除する** → `test_c05_v2_declaration_and_position_agree` が **`MitateDB-api` (in-process) で赤**。
5. **`cell.py` の深さ検査呼び出しの 1 行を削除する** → `test_c05_v2_declaration_and_position_agree` が **`operation_depth` を駆動する MitateDB plug で赤**。
6. **ホルダの構築を合成根から `ApplicationCell.__init__` の内側へ移す (1 行)** → **rate 窓と concurrency の peer-local テストが赤** (application ごとに初期化され、配備単位の意味が壊れる)。**あわせて `ApplicationRuntime` 生成時に作る形へ移すと、要求ごとに初期化されて同テストが赤**になることも実測する。
7. **`cell.py` の gate で `request_bytes` の構造推定を rate 窓判定より前へ移す (2 行の入れ替え)** → **順序を固定する peer-local テストが赤** (bound 超過の要求が `requests_per_minute` ではなく `request_bytes` で拒否される)。
8. **`cell.py` の構造推定側の `limit_class` を `"request_bytes"` 以外の値にする (1 行)** → **二重層の応答同一性を固定する peer-local テストが赤**。
9. **`test_c05_limit_declaration_agreement.py` に撤去した `:646-659` を復元する** → `test_c05_v1_d_unavailable_class_may_still_publish_a_limits_value` が **`MitateDB-api` plug で赤** (`unavailable` かつ `limits` 値を持つ組が 0 件になっているため)。**これは「同一コミットで撤去しなければならない」ことの実測である。**
10. **`_V3_KNOWN_UNAVAILABLE` (`test_c05:700-710`) に削除した組を 1 つ戻す** → **`xfail(strict=True)` により XPASS で赤**。**併せて、その組の `strict=True` を落とすと赤にならなくなること (strict が load-bearing であること) を実測し、実測後に必ず戻す。**
11. **`conformance_adapter_mitatedb.py` の隔離 profile の `concurrency` を 201 に上げる** → **1b の `_drive_concurrency` の `bound <= _MAX_EXERCISABLE_LIMIT` assert が赤** (1a 時点では peer-local の profile 検査で赤にする形でもよい。**どちらで観測したかを報告に書く**)。

#### 非空振り要件

- **新規 peer-local テストは、観測対象が 1 件以上あることを assert する。** 「N 本保持 → N+1 拒否 → 解放後 N 完了」は**実際に N ≥ 1 本を保持したこと**を assert してから位置を測る。
- **共通 suite 側は 4 plug 全数で観測する** — `_drive_requests_per_minute` / `_drive_request_bytes` / `_drive_operation_depth` が **MitateDB 2 plug で真を返す**ことを、`test_c05_v2_declaration_and_position_agree` の per-plug 非空性 assert (`test_c05:684`) と併せて示す。
- **変異は全 plug で赤にした実測を報告に添える。** **「1 plug で赤になった」で済ませない** — どの plug のどの class で赤になったかを **class 名つき**で報告する。

#### 確定文言のファイル所在

- **U-1 の依頼者裁定の逐語は設計 §5 (複製が `{scratchpad}/phase8-ruling-verbatim.txt`)。** **`operation_depth` の実測分岐と、残った組の理由を書く際は、この逐語から複製し言い換えない** (常設規律 4)。
- **`limits.classes` の 16 語と `limit_enforcement` の 4 語 (`enforced` / `reference_wall_clock` / `deployment_required` / `unavailable`) は契約の既存語彙である。新語を作らない。**
- **C-05 行の新しい開示文は 1a では書かない** (1b の範囲)。

#### 同型性テストの対象

- **両 peer に同名で置くヘルパが生じたら、同型性テストの対応表 `_ISOMORPHIC_TARGETS` に行を足す** (常設規律 6)。**本 WP では r2db 側の `src` が無変更であるため、同名ヘルパは現時点で想定されていない。** **必要が生じたら実装前に監督へ上げる** (常設規律 5)。
- **コードは共有しない** — MitateDB の実現は r2db と「契約上の意味」を一致させるが、**実装は別に書く** (P-6)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests/test_c05_limit_declaration_agreement.py
```

**root suite は回さない** (監督の完了ゲートのみ。速度規律 1・2)。**`timeout` パラメータ 600000 を明示し、前景で直列に実行する。**

#### 禁止事項

1. **契約を変えない。** `spec/` と両 peer の packaged 複製に 1 バイトも触らない。**`limits.classes` の 16 語も `limit_enforcement` の 4 語も既存のまま使う。**
2. **宣言だけを先に上げない。** 宣言・実装・V3 の組の削除は **class ごとに同一コミット**である。
3. **`ApplicationRuntime.__slots__` (`cell.py:1338`) を変更しない。** 状態を session や `ApplicationCell` に置かない。
4. **control plane を変えない。** `control_plane.py:1162-1172` のグローバル窓は application plane の窓とは別概念であり、**触らない**。
5. **`execution_ms` を `enforced` で宣言しない** — wall-clock は決定的に N+1 を構成できない (設計 §4)。**r2db と同じ `reference_wall_clock` である。**
6. **`xfail` の `strict=True` を落として緑にしない。** **緑にする正しい手段は実装を真にすることだけである。**
7. **`skip` を使わない。** `skipped` は 0 のままである。
8. **新しい bound を発明しない** (P-5)。実装するのは契約 `limits.classes` に既にある class だけである。
9. **`CONDITIONS.md` に触らない** (1b の範囲)。**`conformance-tests/adapter.py` にも触らない** (1b の範囲)。
10. **製品コードにテスト用フックを足さない** (`before_execute` callable、人工遅延 endpoint 等。設計 §4)。
11. **設計外の検査・機構を足す前に報告して裁定を待つ** (常設規律 7)。

#### 報告形式

1. 触ったファイルと変更行数 (ファイル単位)。
2. **完了条件番号 → 変異の実測**: 変異のコマンド、赤になったテスト id、**plug 名と class 名**、復元の sha256 二重照合の結果。
3. **設計 §11.3 に記録する実測項目**: (i) `already_consumed` の再測定結果と式を変えたか否か、(ii) `operation_depth` が `enforced` になった面と残った xfail 組、(iii) `test_c05:646-659` 撤去後に V1 (d) の非空振り担保が 0 件になったことの確認、(iv) 隔離 profile の確定値。
4. **設計との食い違い** (あれば。**独断で読み替えず監督へ差し戻す**)。

---

### WP-1b port v1.12 — in-flight 保持 primitive と L7-21 の能力判定化

**着手条件: WP-1a の完了後 (同一 worktree `phase8-wp1` で直列)。**

#### 目的

**`concurrency` を共通 suite で初めて駆動可能にし、V2 の駆動可否から peer 名固定の除外を消す。** SI-08 の Verification が `concurrency` について**一度も確認されていなかった**状態と、**宣言が偽でも緑になり得た**除外の形 (L7-21) を同時に閉じる。

#### 前提として読む箇所 (設計)

**§1.2 (4)(5)(6)**、**§3 D-2 全文** (決定 1〜5、実装の形 (a)(b)(c)、検査の形、開示事項)、**§6.1**、**§6.2 (C-05 行の書き換え表と足す 4 文)**、**§10 L8-6 / L8-7**。

#### 成果物 (ファイル単位)

1. **`conformance-tests/adapter.py` を port v1.12 へ上げる。追加は 2 項目、削除は無い。**
   - **`hold_in_flight(session, n)`** — in-flight 保持の context manager。**signature は設計 D-2 実装の形 (a) を逐語で使う**:

     ```python
     @abstractmethod
     def hold_in_flight(self, session, n: int) -> AbstractContextManager[None]:
         """n 個の application plane 要求を、この instance の in-flight 窓の
         内側 (concurrency カウンタ取得後、DB 実行前) で停止させたまま保持する。

         - `with` の内側では、n 個が in-flight のまま保持されている。
         - その状態で通常の port 操作を 1 つ出すと `ConformanceDenial`
           (`LIMIT_EXCEEDED` / `details.limit_class == "concurrency"`) になる。
         - `with` を抜けると保持していた n 個はすべて解放され、正常に完了する
           (例外を上げない)。抜ける時点で n 個の完了を待ち合わせる。
         - `n` は、この instance が宣言する `limits.concurrency` 以下でなければ
           ならない (呼び出し側が assert する)。
         """
     ```

     **docstring には加えて 3 点を書く** (設計 §6.1 / D-2 開示事項): **(i)** 作る並行性は **in-process の並行性**である (4 plug とも ASGITransport / 直接構築。L7-2 前)、**(ii)** **実ソケット・reverse proxy 越しの concurrency は射程外**である、**(iii)** **MitateDB は 1 cell あたり同時 1 操作である** (`ApplicationCell._lock`、`cell.py:329`) ため、**宣言する `concurrency` は拒否の閾値であって並列実行能力ではない**。
   - **要求側の optional フィールド** — `select_eq` (`adapter.py:1720-1722`) / `attempt_filter` (`:1725-1727`) 系に **(i) page size (`limit`)** と **(ii) 複数述語 filter** を運ぶ手段を足す。**既存 signature は壊さない** (optional 追加のみ)。
2. **4 plug への実装** (`hold_in_flight` と要求側フィールド)。**停止点の作り方は設計 D-2 実装の形 (b) の表に従う** (下記「実装の指示」)。
3. **`conformance-tests/test_c05_limit_declaration_agreement.py`**
   - **`_drive_concurrency` を新設し、`_V2_DRIVERS` (`:529-538`) に 1 行足す。**
   - **peer 名固定の除外 2 箇所を撤去する** — `_drive_result_items` (`:473-474`) と `_drive_query_complexity` (`:507-508`) の `if not adapter.name.startswith("r2db-api"): return False`。**除外判定を「その adapter がこのフィールドを port 経由で運べるか」の能力判定へ置き換える。**
   - **`result_items` を両側化する** (実測で確認)。**`query_complexity` は片側のままとする** (結論。実測待ちではない)。
   - **L7-21 の静的 assert 2 項目を置く** (下記)。
4. **`docs/design/CONFORMANCE_ADAPTER_V1.md`** — **§22 (v1.12) を新設**する (§21 = v1.11 と同じ構成: 追加メソッドの意味論 / 既存機構との関係 / 互換性影響)。**文書情報の版数行 (現行 `:5` の「版数: 1.11」) も更新する。**
5. **`conformance-tests/CONDITIONS.md` の C-05 行** — 開示部分の**4 箇所**を書き換える (下記)。**Status の先頭 (`executable (four adapters) -- …`) は変えない。**
6. **`conformance-tests/CONDITIONS_HISTORY.md#c-05`** — **L8-7 の訂正の事実を逐語で移す** (現行/履歴分離の規約どおり)。
7. **`r2db-api/conformance/conformance_adapter_r2db.py:148` と `conformance_adapter_r2db_http.py:758`** — 隔離 profile の `concurrency` を現行 32 から**駆動可能な小さい値へ下げる** (32 本のスレッドを保持する形は避ける)。**`r2db-api/src` は無変更である。**

#### 実装の指示

**停止点の作り方 (設計 D-2 実装の形 (b) の表。逐語)**

| plug | ラップ対象 | 停止点が「カウンタの内側」である根拠 | 並行性の作り方 |
|---|---|---|---|
| `r2db-api` (in-process) | 隔離 instance の `DataService` が持つ cell オブジェクト (`conformance_adapter_r2db.py:649-650` が作る fresh adapter の service。dispatch は `service.py:1000` / `:1048` / `:1079`) | dispatch は `_slot` の `with` の内側にある (`service.py:986-1000` 等) ので、cell の `query` / `transact` / `apply_schema` に入った時点で `self._active` は既に +1 されている | **n 本の `threading.Thread`** から素の同期呼び出しを出す |
| `r2db-api-http` | `cell_factory=iso._make_cell` (`conformance_adapter_r2db_http.py:1959-1961`) が返す `PostgresCell` をラップ | 同上 (service は同じ `service.py` の `_slot` を通る) | **n 本のスレッドが各自の event loop と `httpx.AsyncClient(ASGITransport(app))` を持ち、同一の ASGI app (= 同一 service) を叩く。** `_active_lock` は `threading.Lock` (`service.py:847`) なので複数 OS スレッドから安全である |
| `MitateDB-api` (in-process) | **`ApplicationCell` の操作メソッド入口** — adapter が out-of-band で構築した cell (`conformance_adapter_mitatedb.py:358` の `ControlPlane.cells` 配下) の当該メソッドを gate 付き proxy に差し替える。**`_backend` はラップしない** | D-1 の gate が in-flight を取った**後**、`ApplicationCell._lock` (`cell.py:329`) を取る**前**に入る。停止時点でカウンタは +1 済みであり `_lock` はまだ握っていない | 同 in-process、n 本のスレッド |
| `MitateDB-api-http` | 同上 — plug が自分で組む `ApplicationCell(..., backend=PostgresBackend(...))` (`conformance_adapter_mitatedb_http.py:651` の `self._cells` が保持) の**操作メソッド入口** | 同上 | 同 HTTP、n 本のスレッド + 各自の loop と client (`:1477-1481` の隔離構成の延長) |

**ラップの中身は「最初の n 回の呼び出しだけ `threading.Event().wait()` で止め、`with` の終了時に `set()` する」小さな proxy である。** **adapter 内部の実装詳細であり、port の意味には現れない。**

**MitateDB 側でラップ対象を `_backend` にしてはならない**: `ApplicationCell._lock = RLock()` (`cell.py:329`) は application plane の**全操作**を包み、`_backend` の呼び出しはその `with self._lock:` の**内側**にある。`_backend` で止めると 1 本目が `_lock` を掴んだまま停止し、**2 本目以降が `_lock` の獲得で止まって停止点に到達せず、n ≥ 2 で恒久ハングする**。**cell の操作メソッド入口 (lock 取得前) に置く。** **r2db 側にこの制約は無い** (`postgres.py:328` は接続プールの短い critical section であって操作を直列化しない) — **service の `_slot` の内側 = backend 呼び出し前であればどこでもよい。**

**HTTP plug の単一 loop 構造との折り合い**: 現行の `self._loop.run_until_complete` (`conformance_adapter_r2db_http.py:1156-1157` / `conformance_adapter_mitatedb_http.py:838-839`) は **1 本の loop で複数要求を同時に in-flight にできない**。**`hold_in_flight` の HTTP 実装は、保持用のスレッドごとに新しい event loop と `AsyncClient` を作る。** **共有 adapter の `self._loop` / `self._client` には触れない** — 隔離 instance の中だけで完結する。

**`_drive_concurrency` の形 (設計 D-2 検査の形)**: 宣言 `enforced` を確認 → **`bound <= _MAX_EXERCISABLE_LIMIT`(200) を assert** → **rate headroom を assert する** (「この隔離 instance の `requests_per_minute` の残りが n+1 以上である」。**前提を書かずに依存しない**) → `hold_in_flight(bound)` で N 本保持 → **N+1 本目が `LIMIT_EXCEEDED` / `limit_class == "concurrency"`** → **解放後、保持していた N 本がすべて成功して完了**。**4 plug 全数で駆動する。**

**L7-21 の静的 assert (命題を限定する。設計 D-2 実装の形 (c))**: 固定する命題は **「V2 driver が『駆動するか否か』を peer 名で決めない」の 1 つに限定する。** **「`test_c05` から `adapter.name.startswith(` を 0 件にする」という形は採らない。**

- **(i) 駆動可否の命題**: `_V2_DRIVERS` (`:529-538`) の各 driver 本体に、`adapter.name` を読んで early `return False` する分岐が無いこと。
- **(ii) allowlist と理由表**: `test_c05` 内で `adapter.name` を読む箇所を **allowlist 以外 0 件**に固定する (`adapter.name.startswith(` / `adapter.name ==` の逐語走査)。**本フェーズ後に残る allowlist は次の 3 行だけである。**

| 行 | 何のための名前使用か | なぜ除外ではないか |
|---|---|---|
| `test_c05:266` (`_schema_objects_unit_cost`) | **peer ごとの実測計数規則** (r2db は entity + field 数で 3、MitateDB は table 1 個で 1) | 駆動可否ではなく**期待値の計算**である |
| `test_c05:383` (`_drive_requests_per_minute`) | **HTTP plug の `authenticate()` が同じ rate 窓を 1 単位消費する**ことの補正 (`already_consumed`) | 駆動可否ではなく**観測位置の補正**である。**WP-1a で再測定済みの値を使う** |
| `test_c05:835` (`test_c05_e_isolated_application_surface_releases_resources`) | **MitateDB in-process (SQLite) 固有の資源解放観測経路** | 駆動可否ではなく**観測手段の違い**である |

**`test_c05:653` は allowlist に載せない** — WP-1a で撤去済みの行だからである。**撤去後、`:473-474` / `:507-508` と併せて peer 名分岐は 3 行になる。**

**`result_items` の両側化 (実測で確認する)**: 宣言値 N に対して「page size = N を要求して N 行 → 成功」「page size = N+1 を要求して N+1 行 → 拒否」。**両 peer の検査位置は一致し得る** — r2db は `limits.check("result_items", min(len(rows), page_size))` (`r2db-api/src/r2db_api/postgres.py:1069`、`structured.py:1198`)、MitateDB は `limit > self.config.max_result_rows` で拒否する (`MitateDB-api/src/mitatedb_api/cell.py:557-560`)。**実装担当がこの一致を実測して確認し、設計 §11.3 に記録する。一致しなければ片側のままとし、理由を C-05 行に書き直す。**

**`query_complexity` は片側のままとする (結論。実測待ちではない)**: r2db の metric は `len(where) + len(select) + order_by_count`、MitateDB は `len(filters)` のみであり、**port の要求は select を必ず 1 個以上運ぶ**ので「N 成功 / N+1 拒否」の位置は**構造的に一致しない**。**両側化を試みない。** **能力判定化 (除外の撤去) は `query_complexity` にも適用する** — 片側であることと peer 名で除外することは別である。

**C-05 行の書き換え 4 箇所 (設計 §6.2 の表)**

| 現行の開示 | 本フェーズ後 |
|---|---|
| **(1)** 「駆動しない 3 class = `execution_ms` / `concurrency` / `idempotency_retention_ms`」 | **`concurrency` を外す。** 残りは `execution_ms` / `idempotency_retention_ms` の **2 class** |
| **(2)** 「片側のみ = `request_bytes` / `query_complexity`。`result_items` は両側だが r2db のみ」 | **`request_bytes` は全 plug で片側**、**`query_complexity` は 4 plug とも片側のまま** (理由は metric 定義の差から決まっている)、**`result_items` は両側化**。**「r2db のみ」という限定は消える** |
| **(3)** 「`concurrency` は両 r2db plug が `enforced` と宣言しているが検査形が無い」 | **逐語で限定して書く** — 「**`enforced` と宣言された class で、V2 の検査形を持たないものが 0 件である**」。**「差集合が空」とだけ書かない** (`execution_ms` は `reference_wall_clock` のままで V2 では駆動されず、開示 (1) に残るため) |
| **L7-21 の既知ギャップ 1 文** | **削除する。** **訂正の事実 (現行の文は `request_bytes`/`query_complexity` と書いているが、実装上 peer 名で除外されていたのは `result_items`/`query_complexity` である) は `CONDITIONS_HISTORY.md#c-05` へ逐語で移す** |
| **(4)(5)** および Acceptance boundary | **変えない** |

**あわせて足す 4 文** (設計 §6.2。**実装担当が実測後に文言を書き、監督が確認する**):

1. 「V2 の `concurrency` 駆動は **in-process の並行性**に対するものであり、実ソケット・reverse proxy 越しの並行性は L7-2 まで射程外である」。
2. 「**MitateDB は 1 cell あたり同時 1 操作である** (`ApplicationCell._lock`)。宣言する `concurrency` は**拒否の閾値**であって並列実行能力ではない」。
3. 「**カウンタのスコープ (配備単位の in-flight、credential 単位の rate 窓) の一致は共通 suite では観測できない** — 隔離 surface の application が 1 個だからである」。
4. 「**V1 (d) の非空振り担保 (`unavailable` かつ `limits` 値を持つ実例) は 0 件になった**」 — 命題自体は同テスト前半が保持する。

**セル長**: `conformance-tests/test_conditions_register.py:56` の `MAX_CELL_LENGTH = 3000` に対し、**C-05 の Status セルは現在 2,524 文字であり、余裕は 476 文字である。** **書き換え後のセル長を実測して設計 §11.3 に記録する。** **3,000 を超える場合は、開示の一部を `CONDITIONS_HISTORY.md#c-05` へ逐語で移して現行行を縮める** — **開示を削って辻褄を合わせない。**

#### 完了条件 (assert 水準)

1. **`hold_in_flight` が 4 plug すべてで観測対象 ≥ 1 を assert する** — **N 本保持 / N+1 本目が `LIMIT_EXCEEDED` + `details.limit_class == "concurrency"` / 解放後 N 本すべて成功して完了**の 3 点を、**`r2db-api` / `r2db-api-http` / `MitateDB-api` / `MitateDB-api-http` の全 plug**で観測する。**N ≥ 1 であることを assert してから位置を測る。**
2. **停止点が in-flight カウンタの内側 (カウンタ取得後、DB 実行前) にある。**
3. **解放後の完了を待ち合わせている** (`with` を抜ける時点で n 個の完了を待つ)。
4. **`_drive_concurrency` が rate headroom を assert してから保持に入る。**
5. **`bound <= _MAX_EXERCISABLE_LIMIT`(200) を assert する。**
6. **L7-21 (i)**: `_V2_DRIVERS` の各 driver 本体に、`adapter.name` を読んで early `return False` する分岐が **0 件**である。
7. **L7-21 (ii)**: `test_c05` 内の `adapter.name` 使用が **allowlist の 3 行以外 0 件**である。
8. **`result_items` が 4 plug すべてで両側 (N 成功 / N+1 拒否) で駆動される。** **位置一致の実測結果を設計 §11.3 に記録する。**
9. **`query_complexity` が 4 plug すべてで片側 (宣言を確実に超える構成の拒否 + 安全側の最小要求の成功) で駆動され、peer 名による除外を持たない。**
10. **C-05 行の Status セルが `MAX_CELL_LENGTH`(3000) 以下である。**
11. **C-05 行の開示 4 箇所が設計 §6.2 の表どおりに書き換わり、足す 4 文が入っている。** — **監査照合**: 監査は `git diff -- conformance-tests/CONDITIONS.md` を設計 §6.2 の表と 1 対 1 で突き合わせ、**(4)(5) と Acceptance boundary が無変更**であることを確認し、書き換え後の C-05 行を報告に逐語で引く (設計 §9 の 6)。
12. **L8-7 の訂正の事実が `CONDITIONS_HISTORY.md#c-05` へ逐語で移っている。** — **監査照合**: 監査は移した逐語と `test_c05:473-474` / `:507-508` の実装を突き合わせる。
13. **`CONFORMANCE_ADAPTER_V1.md` に §22 (v1.12) があり、文書情報の版数行が 1.12 へ更新されている。** — **監査照合**: §21 と同じ構成 (追加メソッドの意味論 / 既存機構との関係 / 互換性影響)。**§9 完了条件には追記しない。**
14. **対応表に対応の無い行が無いこと** (メタ条件)。
15. **1b の部分ゲート** — `conformance-tests/test_c05_limit_declaration_agreement.py` と `conformance-tests/test_conditions_register.py` が `failed` 0 / `skipped` 0。**`passed` の増減内訳を完了報告に書く。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 `hold_in_flight` 4 plug 観測 | **変異 1** |
| 2 停止点の位置 | **変異 2** |
| 3 解放後の完了待ち合わせ | **変異 3** |
| 4 rate headroom | **変異 4** |
| 5 上限 assert | **変異 5** |
| 6 L7-21 (i) 駆動可否の命題 | **変異 6** |
| 7 L7-21 (ii) allowlist | **変異 7** |
| 8 `result_items` 両側化 | **変異 8** |
| 9 `query_complexity` 片側 + 能力判定 | **変異 9** |
| 10 C-05 セル長 | **変異 10** |
| 11 C-05 行の開示 4 箇所 | **監査照合** (設計 §9 の 6 に従い逐語記録) |
| 12 `CONDITIONS_HISTORY.md#c-05` | **監査照合** |
| 13 §22 (v1.12) | **監査照合** |
| 14 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 15 1b の部分ゲート | **監査照合** |

**変異**

1. **製品側の concurrency 上限判定を外す** — `MitateDB-api/src/mitatedb_api/cell.py` のホルダの `if self._active >= bound: raise` 1 行、および `r2db-api/src/r2db_api/service.py:1137` 近傍の同判定 1 行 → **`test_c05_v2_declaration_and_position_agree` が 4 plug すべてで赤** (N+1 本目が拒否されない)。**r2db 側の変異は実測後に必ず戻す** (`r2db-api/src` は本 WP で無変更である)。
2. **`hold_in_flight` のラップを「カウンタの外側」で止める形に変える** — 各 plug の proxy の差し込み位置を gate に入る前 (r2db なら `_slot` の外、MitateDB なら `__authorize` の前) へ 1 行移す → **N+1 本目が拒否されず赤** (= 停止点の位置が load-bearing であることの実測)。
3. **解放後の完了を待たない実装にする** — proxy の `__exit__` から `thread.join()` の 1 行を削除する → **「N 本すべて成功」の assert が赤**。
4. **隔離 profile の `requests_per_minute` を、`concurrency` の駆動が消費する n+1 を下回る値に設定する** (`conformance_adapter_mitatedb.py` の `small_config` 1 行) → **`_drive_concurrency` の headroom 前提 assert が赤**。
5. **隔離 profile の `concurrency` を 201 にする** (1 行) → **`bound <= _MAX_EXERCISABLE_LIMIT` の assert が赤**。
6. **`_drive_result_items` に `if not adapter.name.startswith("r2db-api"): return False` を 1 行戻す** → **L7-21 (i) の静的 assert が赤**。
7. **`test_c05` の allowlist 外の場所に `adapter.name == "MitateDB-api"` を 1 行足す** → **L7-21 (ii) の静的 assert が赤**。
8. **いずれかの plug の `limits.result_items` の宣言値を 1 大きく偽る** (adapter の隔離 profile 1 行) → **`_drive_result_items` の N / N+1 位置が該当 plug で赤**。
9. **いずれかの plug の `limits.query_complexity` の宣言値を 1 大きく偽る** (同上) → **`_drive_query_complexity` の片側検査が該当 plug で赤**。
10. **`CONDITIONS.md` の C-05 の Status セルに 500 文字のダミー文字列を足す** → **`test_conditions_register.py` のセル長テスト (`MAX_CELL_LENGTH = 3000`) が赤**。

#### 非空振り要件

- **`hold_in_flight` の完了条件 1 は、4 plug すべてで観測対象 ≥ 1 を assert する** — **N 保持 / N+1 拒否 / 解放後 N 完了の 3 点を、全 plug で実測した結果を報告に添える。** **「1 plug で赤になった」で済ませない。**
- **`_drive_concurrency` は `test_c05_v2_declaration_and_position_agree` の per-plug 非空性 assert (`test_c05:684`) の下で走る** — 駆動 class が 0 になれば赤になる形が既に存在する。**session 横断の集約 guard は採らない** (`-n 5 --dist loadgroup` では成立しない)。
- **L7-21 の静的 assert 2 項目は、走査対象が 1 件以上あることを assert する** (allowlist の 3 行が現に見つかること)。**走査が空振りして緑になる形にしない。**

#### 確定文言のファイル所在

- **`hold_in_flight` の意味 1 文は設計 §3 D-2 決定 1 が正本である** (複製が `{scratchpad}/phase8-ruling-verbatim.txt`)。**port docstring にはこの逐語を置き、言い換えない** (常設規律 4)。
- **signature と docstring の骨子は設計 D-2 実装の形 (a) が正本である。**
- **C-05 行の新しい開示文は例外である** — **文言は実装担当が実測後に書き、監督が確認する。** 主張は実測の後に、その数値・テスト名を引用して書く (常設規律 3)。**「差集合が空」のような緩い言い方をせず、設計 §6.2 (3) の逐語限定形を使う。**

#### 同型性テストの対象

- **両 peer に同名で置くもの**: **`hold_in_flight` の proxy ヘルパ**が両 peer の conformance adapter に同名で生じる場合、**同型性テストの対応表 `_ISOMORPHIC_TARGETS` に行を足す** (常設規律 6)。**行を足す場合は、行数を含む pin テスト名の更新と、表内の自己参照行の更新を踏む。**
- **`limit gate` のテスト**は WP-1a の peer-local であり、**MitateDB 固有である** (r2db は既存実装)。**同名で両 peer に置く必要が生じたら実装前に監督へ上げる** (常設規律 5)。
- **コードは共有しない** (P-6)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_c05_limit_declaration_agreement.py
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

**root suite は回さない** (監督の完了ゲートのみ)。**`timeout` 600000 を明示し、前景で直列に実行する。**

#### 禁止事項

1. **製品コードにテスト用フックを足さない** — 停止点は **adapter 側のラップ**で作る (設計 §4)。
2. **MitateDB で `_backend` をラップしない** — n ≥ 2 で恒久ハングする。**cell の操作メソッド入口 (lock 取得前) に置く。**
3. **共有 adapter の `self._loop` / `self._client` に触れない** — 隔離 instance の中だけで完結させる。
4. **「実際に遅い要求」で in-flight を作らない** — 決定的でない (設計 §4)。
5. **`query_complexity` を両側化しようとしない** (結論であり実測待ちではない)。
6. **「`adapter.name.startswith(` を 0 件にする」形の静的検査を書かない** — 命題を「駆動可否を peer 名で決めない」に限定する。
7. **allowlist を勝手に増やさない。** 3 行以外が必要になったら実装前に監督へ上げる。
8. **`r2db-api/src` を変更しない** — 本 WP で触る r2db 側は `conformance/` の隔離 profile の `concurrency` 値だけである。
9. **契約を変えない。** `CONDITIONS.md` は **C-05 行のみ**、新しい条件行を足さない。
10. **開示を削って C-05 のセル長の辻褄を合わせない** — 超える場合は `CONDITIONS_HISTORY.md#c-05` へ逐語で移す。
11. **設計外の検査・機構を足す前に報告して裁定を待つ** (常設規律 7)。

#### 報告形式

1. 触ったファイルと変更行数。
2. **完了条件番号 → 変異の実測**: コマンド、赤になったテスト id、**plug 名**、復元の sha256 二重照合の結果。
3. **設計 §11.3 に記録する実測項目**: (i) `result_items` 両側化の N / N+1 位置が両 peer で一致したか、(ii) C-05 Status セルの書き換え後の文字数、(iii) 4 plug それぞれの `hold_in_flight` の停止点 (ラップ対象のファイル名と関数名)、(iv) 隔離 profile の `concurrency` 確定値 (4 plug)。
4. **C-05 行の新しい開示文の案** (監督確認用に逐語で添える)。
5. **設計との食い違い** (あれば)。

---

### WP-2 R-9 (テスト総数の下限) + L7-23 + L7-22 注記

#### 目的

**証拠の消失を検知する。** 前回 main の収集件数を下限として持ち、**明示の更新なしにテストが減れば赤になる**状態を作る。あわせて **register テストが単独実行で静かに vacuous 緑になる罠 (L7-23)** を閉じる。

#### 前提として読む箇所 (設計)

**§1.2 (7)(8)(9)**、**§1.3 の 1**、**§3 D-3 全文**、**§4 の R-9 に関する却下 2 行**、**§6.4**、**§10 L8-1**。

#### 成果物 (ファイル単位)

1. **`conformance-tests/COLLECTION_FLOOR` (新設)** — **1 行、10 進整数のみ。** 前文もコメントも置かない (parser を単純に保つ)。**初期値は着手時点の実測 `2274`** (設計 §1.3)。
2. **`tools/check_collection_floor.py` (新設)** — **標準ライブラリのみ。** `python -m pytest --collect-only -q` を repo root で実行し、末尾の `<N> tests collected` を正規表現で読み、`COLLECTION_FLOOR` の値と比較する。**下回れば非 0 終了し、実測値・下限・差分を 1 行で出す。** **上回るのは正常である。** **引数で floor ファイルのパスを上書きできる。**
3. **`.github/workflows/ci.yml`** — `conformance` job (`:63`、matrix 3.11 / 3.12) に **1 step** を足す (`python3 tools/check_collection_floor.py`)。**置き場は「PostgreSQL 起動 step (`:77-82`) より後、pip install の後、pytest 本体 (`:103-106`) より前」である。** **3.11 / 3.12 の各 job で、その job 自身の collect 件数を `COLLECTION_FLOOR` と比較するだけにする。**
4. **`conformance-tests/test_conditions_register.py`** — `_collect_marked_condition_ids` (`:166-176`) の末尾に **`assert ids, "<理由>"`** を置く。**メッセージには「このテストは conformance 全体 run の内側でのみ評価できる」という理由を書く。** **`skip` にはしない** (常設規律 1)。
5. **`conformance-tests/README.md`** — **`COLLECTION_FLOOR` の運用規約を散文で書く** (設計 §6.4): (i) 値は**前回 main の実測値**であり**完了ゲートで監督が更新する**、(ii) **下げるコミットには理由を commit message に書く**、(iii) **上げるのも完了ゲートの一部として監督が行う** (WP 途中で上げると他 WP のマージが赤くなる)、(iv) **残余リスクの開示** — ゲート間は「(実測 − 下限) 本まで」のテスト削除が検知されない。**下限が守るのは「大きく減ったこと」であって「1 本も減っていないこと」ではない。**

#### 実装の指示

- **前提と費用の開示** (設計 D-3): `--collect-only` は**収集時に 4 adapter を実構築する** (`conformance-tests/conftest.py:107-145` の `_discover_and_build` が `registry.json` の各 entry を import して `build_adapter()` を呼ぶ)。**したがってこの step にも PostgreSQL と全 DSN 環境変数が要り、HTTP plug の使い捨て DB provisioning が 1 job あたり 2 回走る。** **この費用の倍化は既知の代償として受け入れる。** **README に 1 文で書く。**
- **`tally-consistency` job (`:207-242`) は触らない。** **collect 件数を tally artifact に載せて突合しない** (将来の version 分岐で赤になる新しい義務を作らないため。設計 §6.4)。
- **pytest テストとしては置かない** (設計 §4) — 部分実行で常に赤になる形 (L7-23 と同じ罠) を増やさない。

#### 完了条件 (assert 水準)

1. **`tools/check_collection_floor.py` が、実測 < 下限のとき非 0 終了し、実測値・下限・差分を 1 行で出す。**
2. **比較そのものが load-bearing である** (常に真へ倒すと下限超過を見逃す)。
3. **`COLLECTION_FLOOR` が 1 行の 10 進整数のみであり、初期値が着手時点の実測 `2274` である。** — **監査照合**: 監査はファイルの中身 (`cat`) と設計 §1.3 の実測値を突き合わせる。
4. **CI の step が 3.11 / 3.12 の両 job にあり、PG 起動 step より後・pytest 本体より前に置かれている。** — **監査照合**: 監査は `git diff -- .github/workflows/ci.yml` の step の位置を `:77-82` / `:103-106` と突き合わせ、**`tally-consistency` job が無変更**であることを確認する。
5. **L7-23 のガードが、register ファイル単独実行で「収集 0 件」を明示して赤にする。** 従来の誤誘導的な赤 (「全 20 条件にマーカーが無い」) ではなく、**理由を書いたメッセージで落ちる。** **同時に `:198` 以降の vacuous pass が消える。**
6. **L7-23 のガードが完了ゲート形式 (`-n 5 --dist loadgroup`) で緑である。** — **監査照合 (実測記録)**: **実装担当が完了ゲート形式でこのガードが緑であることを実測し、コマンドと結果を設計 §11.3 に記録する** (xdist の各 worker が session 全体を収集する前提の確認。設計 D-3)。**この前提が崩れるとゲート全体が赤になる。**
7. **L7-22 の状態訂正**: `security/CONTROL_MAPPING.md:33` の SI-00 行に「ledger item L4-13, still open」が、`conformance-tests/CONDITIONS.md:38` の C-09 行に「P4-D18 (L4-8, still open)」が**現行行として在る**。**ファイル変更は行わない。** — **監査照合**: 監査はこの 2 行を読み、**逐語引用を報告に引き**、設計 §10 L8-1 の状態注記と一致することを突き合わせる (設計 §9 の 6)。
8. **`conformance-tests/README.md` に運用規約 4 点と残余リスクの開示が書かれている。** — **監査照合**: 監査は設計 §6.4 の 4 点および残余リスク段落と 1 対 1 で突き合わせる。
9. **対応表に対応の無い行が無いこと** (メタ条件)。

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 floor 未満で非 0 終了 | **変異 1** |
| 2 比較が load-bearing | **変異 2** |
| 3 `COLLECTION_FLOOR` の初期値 | **監査照合** |
| 4 CI step の位置 | **監査照合** |
| 5 L7-23 ガードの単独実行での赤 | **変異 3** |
| 6 ガードが完了ゲート形式で緑 | **監査照合** (実測記録。設計 §11.3) |
| 7 L7-22 の状態訂正 | **監査照合** (逐語引用。設計 §9 の 6) |
| 8 README の運用規約 | **監査照合** |
| 9 対応表が全行埋まる | 本表そのもの (メタ条件) |

**変異**

1. **`conformance-tests/COLLECTION_FLOOR` の値を `2274` → `2275` にする** (実測より大きい下限) → **`./.venv/bin/python tools/check_collection_floor.py` が非 0 終了し、実測 2274 / 下限 2275 / 差分 −1 を 1 行で出す。** **CI 上でも同 step が赤になる。**
2. **`tools/check_collection_floor.py` の比較 (`if measured < floor:`) を常に偽へ倒す 1 行** → **変異 1 の状態 (floor 2275) でも 0 終了する** (= 比較が load-bearing であることの実測)。**実測後に必ず戻す。**
3. **`conformance-tests/test_conditions_register.py:166-176` の末尾に置いた `assert ids, "…"` の 1 行を削除する** → **`./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py` の単独実行で `:198` 以降が緑に戻る** (= ガードが load-bearing であることの実測)。**この変異の観測は「単独実行のコマンド」自体で行う** — 全体 run では両方とも緑なので差が出ない。

#### 非空振り要件

- **L7-23 のガードは「観測 0 件なら fail-loud」であり、これ自体が空振り禁止の実装である。** **`skip` にしない。**
- **`tools/check_collection_floor.py` は、`tests collected` 行が読めなかった場合も非 0 終了する** — 「読めなかったので緑」にしない。**この分岐を報告で明示する。**
- **CI の step が実際に走ったことを、run のログ行で示す** (3.11 / 3.12 の両 job)。

#### 確定文言のファイル所在

- **本 WP に依頼者確定文言は無い。** **`COLLECTION_FLOOR` の運用規約 4 点と残余リスクの文言は設計 §6.4 が正本であり、そこから複製する。**

#### 同型性テストの対象

- **両 peer に同名で置くものは無い。** `tools/` と CI workflow と register テストのみである。

#### テストコマンド

```
./.venv/bin/python tools/check_collection_floor.py
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py conformance-tests/test_c00_contract_discovery.py
```

**3 本目は「全体 run の内側なら緑」であることを部分的に確認するためのものである。** **完了ゲート形式 (`-n 5 --dist loadgroup`) での確認は完了条件 6 に従い実装担当が 1 回だけ実行してよい** — **これは速度規律 2 の例外であり、監督の完了ゲートとは別物である。実行前に監督へ一報する。**

#### 禁止事項

1. **R-9 を pytest テストとして置かない** (設計 §4) — 部分実行で常に赤になる形を増やさない。
2. **collect 件数を tally artifact に載せない。** `tally-consistency` job を触らない。
3. **`COLLECTION_FLOOR` を WP の途中で上げない。** 最終更新は監督のゲート作業である。
4. **L7-23 のガードを `skip` にしない。**
5. **L7-22 でファイルを変更しない** — 手当ては状態注記の訂正 (WP-6) だけである。
6. **`tools/check_collection_floor.py` に外部依存を入れない** (標準ライブラリのみ。`tools/public_value_scan.py:1-23` の規約)。
7. **CI の trigger や `concurrency` の設定を変えない。**
8. **設計外の検査・機構を足す前に報告して裁定を待つ** (常設規律 7)。

#### 報告形式

1. 触ったファイルと変更行数。
2. **完了条件番号 → 変異の実測**: コマンド、終了コード、出力 1 行、復元の sha256 二重照合。
3. **設計 §11.3 に記録する実測項目**: L7-23 のガードが完了ゲート形式で緑であることのコマンドと集計行。
4. **CI の run id と、3.11 / 3.12 の両 job で floor step が緑であることのログ行。**
5. **設計との食い違い** (あれば)。

---

### WP-3 R-10 (A) — 契約 JSON の provenance companion (0 バイト不変)

#### 目的

**`spec/` ディレクトリから 1 hop で経緯の一次資料へ辿れる状態にする。** **契約 JSON は 1 バイトも動かさない** (U-2 = (A) 確定)。**新しい経緯マーカーが契約に入れば companion に anchor を足すまで赤になる**という機械的な網羅性を置く。

#### 前提として読む箇所 (設計)

**§1.2 (10)**、**§3 D-4 全文** (決定 1〜9、実装の形、検査の形、開示事項)、**§5 U-2 の依頼者裁定 (逐語)**、**§6.5**、**§10 L8-4 / L8-8**、**付録 A 全文** (§A.0 の sha256、§A.1 の逐語インベントリ、§A.2 の集計、§A.3a の ruling → 行の対応表)。

#### 成果物 (ファイル単位)

1. **`spec/CONTRACT_HISTORY.md` (新設)** — **見出しは `## <json_path>` (ID のみ。タイトルを付けない)**、配下に **3 点**: **(i) マーカーの逐語**、**(ii) 該当する subordinate ruling の `spec/CCR_DISPOSITION.md` 上の見出し / 行**、**(iii) 導入版**。**割当の無い見出しを作らない。** **冒頭 (見出しの外) に前文を置き**、更新規約 (「契約 JSON に新しくマーカー付きの値が入ったら、**同一コミットで**本ファイルに anchor を足す」) と、**本方式の限界 3 点**を散文で書く:
   - **契約 JSON の長さは 1 文字も減らない。** P-7 への効きは「`spec/` ディレクトリから 1 hop で経緯の一次資料へ辿れる」ことに限られる。
   - **契約 JSON の中から companion への in-band の参照は 1 つも無い。** 到達経路は `spec/README.md` と本前文の 2 箇所である。**「契約 JSON から 1 hop」ではなく「`spec/` ディレクトリから 1 hop」である。**
   - **契約本体に残る経緯マーカーの件数 (29 値、付録 A §A.2c)** を記録する。**本フェーズ後もこの件数は変わらない。**
2. **`conformance-tests/test_contract_history_register.py` (新設)** — **4 項目を固定する** (下記)。**常設スキャナは付録 A のプロトタイプ (`{scratchpad}/r10_marker_inventory.py`) の正規表現を*そのまま*移す** (常設規律 5)。**`@pytest.mark.condition` は付けない。**
3. **`spec/README.md`** — **1 段落**を足す: companion (`spec/CONTRACT_HISTORY.md`) が存在すること、**anchor が JSON パスであること**、**契約 JSON 側には参照キーを置かない方針であること**。
4. **無変更であることを保つファイル**: `spec/data-service-api.v1.json`、両 peer の packaged 複製 2 本、`conformance-tests/test_contract.py`。**PIN も定数も参照先も 1 つも触らない。**

#### 実装の指示

- **WP-7 の規約を再利用する。新方式を作らない** (設計 D-4 決定 1)。**見出しを ID のみに保つ規約は (A) でも維持する** — 理由は「リンクが壊れるから」ではなく (**(A) では contract JSON 側からのリンクが存在しない**)、**anchor の slug が ID から機械的に決まることが register テストの anchor 解決検査を成立させるから**であり、**`conformance-tests/test_conditions_register.py:58` の `_HISTORY_LINK_RE` と `:62-73` の `_github_slug` をそのまま再利用するためである**。
- **anchor の ID は JSON パスである** (例: `## versioning.version_binding`)。`CONDITIONS.md` の C-XX に相当する識別子が契約 JSON には無いので、**記録の対象を一意に指せるのは JSON パスである。**
- **ruling の所在は付録 A §A.3a の対応表 (`spec/CCR_DISPOSITION.md:93` の `### 従属判断 — すべて裁定済み` 配下の番号付き項目) をそのまま使う。**
- **マニフェスト (`spec/CONTRACT_HISTORY_MANIFEST.json`) は作らない。** **deep-equal の意味不変検証も作らない。** **契約 JSON 側に companion への参照キーも置かない。** — いずれも (A) では不要である (設計 D-4 決定 4)。
- **(B) (接頭辞の剥離) には一切手を付けない** — **フェーズ9 (契約 1.7.0) へ送ることが確定している** (U-2 裁定、設計 §10 L8-4)。

#### 完了条件 (assert 水準)

1. **常設スキャナが列挙する「マーカーを 1 つ以上含む JSON パス」の集合が、companion の見出し集合と過不足なく一致する。**
2. **companion の見出しに重複が無い。**
3. **各見出し配下が空でない。**
4. **各 anchor が参照する subordinate ruling が `spec/CCR_DISPOSITION.md` の見出し (番号付き項目) に実在する。**
5. **契約 JSON と両 peer の packaged 複製 2 本が 0 バイト不変である** (既存のバイト一致テスト `r2db-api/tests/test_http.py:286` / `MitateDB-api/tests/test_http.py:155` が緑)。**3 本の sha256 が付録 A §A.0 の値と一致することを実測して報告に書く。**
6. **`conformance-tests/test_contract.py` が無変更である。** — **監査照合**: 監査は `git diff -- conformance-tests/test_contract.py` が空であることを確認する。
7. **`spec/README.md` に到達経路の 1 段落があり、companion の前文に限界 3 点と更新規約がある。** — **監査照合**: 監査は設計 D-4 開示事項の 3 点と 1 対 1 で突き合わせ、**前文の該当箇所を報告に逐語で引く** (設計 §9 の 6)。
8. **人手の突合**: **companion に写した逐語が正しいか、ruling の対応付けが妥当か。** — **監査照合**: 監査は **29 anchor のうち少なくとも `versioning.version_binding` と `audit.query_operation_vocabulary` / `audit.query_target_kind_vocabulary` の 3 件について**、契約 JSON の値と companion の逐語、および `CCR_DISPOSITION.md` の該当 ruling を三者突合し、結果を報告に書く。**機械検査は anchor の在否と非空しか見ない** — この人手の突合を独立項目として持つ。
9. **新しい共通条件を足していない** (`@pytest.mark.condition` 無し、`CONDITIONS.md` 無変更)。 — **監査照合**。
10. **対応表に対応の無い行が無いこと** (メタ条件)。

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 集合一致 | **変異 (i)** + **変異 (ii)** |
| 2 見出し重複無し | **変異 (vi)** |
| 3 anchor 配下が非空 | **変異 (iii)** |
| 4 ruling 実在 | **変異 (iv)** |
| 5 契約 JSON 0 バイト不変 | **変異 (v)** |
| 6 `test_contract.py` 無変更 | **監査照合** |
| 7 README と前文 | **監査照合** (逐語引用。設計 §9 の 6) |
| 8 人手の突合 | **監査照合** (三者突合の結果を報告に書く) |
| 9 新条件を足していない | **監査照合** |
| 10 対応表が全行埋まる | 本表そのもの (メタ条件) |

**変異** (設計 D-4「検査の形」の 5 種 + 重複検査の 1 種)

- **(i)** **`spec/CONTRACT_HISTORY.md` の見出しを 1 つ削除する** → **集合一致テストが赤** (スキャナ側にあって anchor 側に無い)。
- **(ii)** **契約 JSON にマーカー付きの値を 1 つ足す** — **scratchpad の使い捨て複製に対して行い、テストにその複製を読ませる** (**`spec/data-service-api.v1.json` 本体は絶対に書き換えない**) → **集合一致テストが赤** (anchor が足りない)。
- **(iii)** **anchor 1 つの配下を空にする** → **非空検査が赤**。
- **(iv)** **anchor 1 つの ruling 番号を存在しない番号に書き換える** → **ruling 実在検査が赤**。
- **(v)** **両 peer の packaged 複製のうち 1 本だけを 1 バイト書き換える** → **既存のバイト一致テスト (`r2db-api/tests/test_http.py:286` または `MitateDB-api/tests/test_http.py:155`) が赤**。
- **(vi)** **同じ見出しを 2 つ置く** → **見出し重複検査が赤**。

#### 非空振り要件

- **常設スキャナが 0 件を返す形で緑にならないこと** — **スキャナが列挙した JSON パスが 1 件以上 (実測 29 件) であることを assert する。** **0 件同士の一致で vacuous に緑になる形を作らない** (L7-23 と同じ罠を増やさない)。
- **4 項目すべてが実際に走ったことを、収集 id の一覧で示す。**
- **anchor 件数がスキャナの列挙件数と一致することを、報告に数値で書く** (設計 §11.1 の R-10 行に載せる値である)。

#### 確定文言のファイル所在

- **U-2 の依頼者裁定の逐語は設計 §5** (複製が `{scratchpad}/phase8-ruling-verbatim.txt`)。
- **companion に写すマーカーの逐語は、契約 JSON の値そのものが正本である。** **付録 A §A.1 のインベントリ表を参照しつつ、必ず `spec/data-service-api.v1.json` の現物から複製する** — **言い換え・要約・省略記号による短縮を行わない** (常設規律 4)。
- **ruling の所在は付録 A §A.3a の対応表が正本である。**

#### 同型性テストの対象

- **両 peer に同名で置くものは無い。** `spec/` と `conformance-tests/` の新設テストのみである。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_contract_history_register.py
./.venv/bin/python -m pytest -q conformance-tests/test_contract.py
./.venv/bin/python -m pytest -q r2db-api/tests/test_http.py MitateDB-api/tests/test_http.py
```

#### 禁止事項

1. **契約 JSON を 1 バイトも変えない。** packaged 複製 2 本も同じである。**変異 (ii) は scratchpad の使い捨て複製に対してのみ行う。**
2. **`conformance-tests/test_contract.py` を触らない。** **PIN 定数も参照先も動かさない。**
3. **契約 JSON に companion への参照キーを足さない** (設計 §4)。
4. **マニフェストを作らない。deep-equal 検証を作らない。** (A) では不要である。
5. **(B) (接頭辞の剥離) に手を付けない** — フェーズ9 (契約 1.7.0) の範囲である。
6. **companion の見出しにタイトルを付けない** (ID のみ)。**WP-7 の規約を変えない。**
7. **`@pytest.mark.condition` を付けない。`CONDITIONS.md` に行を足さない。**
8. **「経緯を分離した」という主張を、実際より強く書かない** — 限界 3 点を前文に明記する。
9. **設計外の検査・機構を足す前に報告して裁定を待つ** (常設規律 7)。

#### 報告形式

1. 触ったファイルと変更行数。**契約 JSON と複製 2 本の sha256 (付録 A §A.0 との一致)。**
2. **完了条件番号 → 変異の実測**: コマンド、赤になったテスト id、復元の sha256 二重照合。
3. **スキャナが列挙した JSON パス件数 = companion の anchor 件数** (設計 §11.1 の R-10 行に載せる値)。
4. **人手の突合 3 件の結果** (完了条件 8)。
5. **設計との食い違い** (あれば)。

---

### WP-4 R-11 (運用項目)

#### 目的

**配備が「起動できる状態か」「実際に応答するか」「復元できるか」を、起動前・配備後に機械的に確かめる手段を置く。** あわせて **`ps` から secret が見える経路 (実在 6 箇所) を閉じ、再発を静的検査で止める。**

#### 前提として読む箇所 (設計)

**§1.2 (11)**、**§1.3 の 2**、**§3 D-5 全文** (決定 1〜6、実装の形 (a)(b)(c)(d)、検査の形、開示事項)、**§6.5**、**§7 の D-5 行 (SI-02 / SI-10 / SI-14)**、**§10 L8-2**。

#### 成果物 (ファイル単位)

1. **両 peer の `ops.py`** (`r2db-api/src/r2db_api/ops.py` の `_build_parser` `:1620`、`MitateDB-api/src/mitatedb_api/ops.py` の `_build_parser` `:1366`) — **`verify-declarations` サブコマンドを同型で追加する。** `platform_declarations.py` の検査関数を順に呼び、**F 番号ごとに固定の終了コード**を返す。**出力は 1 行 1 検査。**
2. **両 peer の `platform_declarations.py`** — **`PlatformDeclarationError` (r2db `:132-136`、MitateDB は同型) に F 番号の構造化属性 `code` を足す。** **メッセージ文言は変えない。**
3. **`tools/deploy_smoke.py` (新設)** — **標準ライブラリ `urllib` のみ。** **入力は base URL と API key の「環境変数名」であり、引数で secret を取らない。** capabilities → catalog → 1 query を実打ちし、各段の結果を 1 行ずつ出して終了コードで返す。**両 peer 共通のツールでよい** (契約が同じであり、製品コードではない)。
4. **`r2db-api/deploy/scripts/part1_provision_host_and_db.sh`** — **argv に password を渡している 6 箇所 (`:270` / `:279` / `:284` / `:289` / `:334` / `:335`) を `\getenv` 経由へ直す。** **migration ファイル自身は変えない** (`:'control_password'` の参照はそのまま効く)。
5. **`r2db-api/migrations/0001_bootstrap_control_plane.sql`** — **冒頭コメントにある `-v control_password=…` の使用例を、同一コミットで `\getenv` 形へ書き直す** (規則の対象外だが、読み手が古い形を写す事故を防ぐ)。
6. **`conformance-tests/test_deploy_secret_argv_scan.py` (新設)** — 設計 D-5 (c) の規則を対象ファイル群 (`r2db-api/deploy/scripts/` 配下の全ファイルと両 peer の `ops.py`) へ適用し、**flagged 0 件**を assert する。**`@pytest.mark.condition` は付けない。** **docstring に「本規則の緑は『この 3 パターンが現行ツリーに無い』ことしか言わない」という限界を 1 文で書く。**
7. **`docs/ops/BACKUP_RESTORE_R2DB.md` (新設ディレクトリ + ファイル)** — pg_dump (カスタム形式) → 新 DB へ pg_restore → `ops verify-declarations` → `tools/deploy_smoke.py` の順の手順書。**実値は書かない** (`<UPPER_SNAKE>` placeholder と `*.example.invalid` のみ)。
8. **両 peer の `tests/`** — `verify-declarations` の **F 番号ごとに 1 本ずつ**のテスト。**ファイル名は ops 系にする** (WP-1 の limit 系と分ける。§0.0 の 6)。

#### 実装の指示

**(a) `ops verify-declarations` の終了コード表 (両 peer 同一。設計 D-5 実装の形 (a) の逐語転記)**

| 終了コード | 条件 | 何を意味するか |
|---|---|---|
| **0** | 全検査 pass | 宣言はこのプロセスが起動できる状態である |
| **1** | 引数エラー | 使い方の誤り (検査結果ではない) |
| **2** | platform DB へ接続できない | 検査以前の失敗 |
| **3** | **F-3** | `surfaces` 行が無い |
| **4** | **F-3c** | `surfaces.control` が無い (`--control` を指定したときのみ検査) |
| **5** | **F-4** | `audit_coalescing_window_ms` 行が無い |
| **6** | **F-4b** | `audit_writer_roles` の値が不正 |
| **7** | **F-5** | `surfaces` の値が不正 |
| **8** | **F-8** | 宣言表そのものが無い (migration 未適用) |
| **9** | **F-6** | `surfaces.control` の有無と `<PEER>_CONTROL_PLANE_STATUS` が食い違う (env が与えられたときのみ検査) |
| **10** | **F-7 / F-10 / F-11** | 書き手 role の timeout 設定が無い/不正/per-database override |
| **11** | **F-13** | 接続中の role が宣言された書き手 role に含まれない |
| **12** | **F-9** | **接続中の role の実効 timeout 値が、宣言された値と一致しない** (この接続自身の effective setting を読む検査) |

**表の固定点は 0 = 全 pass、F-3 → 3、F-3c → 4、F-4 → 5、F-8 → 8 である。** **F-9 は 10 に畳まず専用コード 12 を与える** — F-9 は「宣言が無い/不正」ではなく「宣言と実効値の食い違い」であり、運用上の手当てが別物 (role 設定の再適用) だからである。

**対象外の 3 条件 (F-1 / F-2 / F-12) を、理由付きで並べて出力の末尾に 1 行で書く**:

| 条件 | 定義位置 (両 peer) | 対象外の理由 |
|---|---|---|
| **F-1** | r2db `platform_declarations.py:193`、MitateDB `:181` | **廃止 env 変数が「定義されているか」はプロセス env の話**であり、provision DSN からは判定できない |
| **F-2** | r2db `:204`、MitateDB `:192` | 同上 (surfaces 側の廃止 env) |
| **F-12** | r2db `:43`、MitateDB `:20` (**cell-open-time, API-facing** と明記) | **cell を開く時点でしか判定できない**条件である |

**出力形式 (1 行 1 検査、先頭に判定。逐語)**:

```
OK   F-8  declaration table present
OK   F-3  surfaces row present
FAIL F-4  audit_coalescing_window_ms row missing -- run `<peer> ops declare-coalescing-window --ms <N>`
```

**(b) `tools/deploy_smoke.py`**

- **引数**: `--base-url-env <NAME>` `--api-key-env <NAME>` (**値ではなく環境変数名**)、`--entity <NAME>` (query 対象、既定は catalog の先頭)。
- **段**: (1) `GET /v1/capabilities` → 200 かつ `contract_version` が読めること、(2) catalog 相当の公開経路 → entity 一覧が読めること、(3) query 1 本 → 200。**各段の結果を 1 行ずつ出す。** 終了コードは 0 / 段ごとの非 0。
- **ローカルでの実証**: conformance HTTP plug が組む ASGI app を `uvicorn` で起動して叩く。**これは実ソケットを通す最初の機会になるが、L7-2 の plug ではない** — **conformance の plug は増やさない。**
- **secret の扱い**: 値は環境から読み、**引数にも出力にも出さない** (SI-10)。

**(c) argv secret 静的規則 (設計 D-5 実装の形 (c) の逐語転記。プロトタイプ済み)**

**規則が主張する命題 (1 文)**: **「配備スクリプトと両 peer の `ops.py` が、secret を子プロセスの argv に載せない」** — `ps` から見える形で secret が渡っていないこと、である。**環境変数経由で渡すことは違反ではない。**

```python
SECRET_WORD = r"(?:password|passwd|pepper|secret|token|api_key|key)"

RULE = re.compile(
    r"(?:^|[\s;|&])-v[\s=][A-Za-z0-9_]*" + SECRET_WORD + r"\s*="   # (a) psql -v <...secret...>=
    r"|--password(?:=\S|[ \t]+[^-\s])"                              # (b) 値を伴う --password のみ
    r"|://[^/\s]*:[^@/\s]+@",                                       # (c) URL の userinfo
    re.IGNORECASE,
)
COMMENT = re.compile(r"^\s*#")
ENV_ASSIGN = re.compile(r"^\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*=")
```

**行頭の env 代入 (`export X=` / `X=`) とコメント行は走査対象から除外する。**

**現行ツリーに対するプロトタイプ出力 (改版した規則で 2026-09-06 に再実行、7 ファイル走査。逐語)**:

```
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:270: -v control_password="${R2DBSVC_CONTROL_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:279: -v api_password="${R2DBSVC_API_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:284: -v controlplane_password="${R2DBSVC_CONTROLPLANE_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:289: -v auditreader_password="${R2DBSVC_AUDITREADER_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:334: -v runtime_password="${R2DB_APP_RUNTIME_PASSWORD}" \
r2db-api/deploy/scripts/part1_provision_host_and_db.sh:335: -v developer_password="${R2DB_APP_DEVELOPER_PASSWORD}" \
files scanned: 7 hits: 6
```

**修正の形 (逐語)**: psql の `-v` を止め、**`\getenv` で環境から読む prelude を psql の標準入力へ渡す**:

```sh
printf '%s\n' \
    "\\getenv control_password R2DBSVC_CONTROL_PASSWORD" \
    "\\i ${R2DBSVC_MIGRATIONS_DIR}/0001_bootstrap_control_plane.sql" \
  | psql "${R2DBSVC_BOOTSTRAP_ADMIN_DSN}"
```

**psql は 14 以降 `\getenv` を持ち、作業機・CI とも PostgreSQL 16 である** (CI は `postgres:16`、`.github/workflows/ci.yml:77-82`)。

**射程外 (テストの docstring に書く開示)**: **(i) 偽陽性の残余** — (b) は `--password` の直後に位置引数が続く形を区別できない。**この形が将来必要になったら、該当行を書き換えるか、規則の allowlist として理由付きで記録する — 規則を緩めない。** **(ii) 取りこぼし** — コマンド置換・変数展開・配列展開・複数行にまたがる引数は検出できない。**本規則は「行の見た目」に対する静的検査であり、実行時の argv を観測するものではない。**

**(d) backup / restore の実証記録の形式 (設計 §11.1 の該当行に逐語で残す)**

**実行したコマンドと集計行を逐語で残す。** 最低限、次の 4 つを含める:

```
$ pg_dump --format=custom --dbname="$<UPPER_SNAKE_SOURCE_DSN_ENV>" --file=<DUMP_PATH>
$ pg_restore --dbname="$<UPPER_SNAKE_TARGET_DSN_ENV>" <DUMP_PATH>
$ <peer> ops verify-declarations            -> exit 0   (OK 行 N 本、対象外 1 行)
$ ./.venv/bin/python tools/deploy_smoke.py --base-url-env <NAME> --api-key-env <NAME>
      stage1 capabilities  200 contract_version=1.6.0
      stage2 catalog       200 entities=<N>
      stage3 query         200 rows=<N>
                                            -> exit 0
```

**あわせて、対象 DB の catalog と 1 query の結果が復元前後で一致したことを 1 行で書く。** **実値 (実ホスト名・実 DSN・実 credential_id) は書かない。**

#### 完了条件 (assert 水準)

1. **`ops verify-declarations` が両 peer に同型で存在し、F 番号ごとに上表の終了コードを返す。** **F 番号ごとに 1 本ずつのテストが「その条件を作って当該終了コードが返る」ことを固定する。**
2. **`PlatformDeclarationError` が F 番号の構造化属性 `code` を持ち、ops 側が prefix 判定に頼らない。** **メッセージ文言は変わっていない。**
3. **出力が 1 行 1 検査の形式であり、末尾に対象外 3 条件 (F-1 / F-2 / F-12) の 1 行がある。** — **監査照合**: 監査は実行出力を上記「出力形式」と 1 対 1 で突き合わせる。
4. **argv secret 静的規則が対象ファイル群に対して flagged 0 件である。**
5. **修正前 6 件 / 修正後 0 件のプロトタイプ出力が、走査コマンドと `files scanned: N hits: M` 行つきで設計 §11.1 に逐語で記録されている。** — **監査照合 (実測記録)**: **片方だけの記録では完了としない** (規則が現に何かを捕まえていたことと、修正がそれを消したことの両方を残すため。常設規律 5)。
6. **`part1_provision_host_and_db.sh` の 6 箇所が `\getenv` 形へ直り、migration 冒頭コメントの使用例も同一コミットで直っている。** **migration ファイル本体 (`:'control_password'` の参照) は無変更である。** — **監査照合**: 監査は `git diff` を読み、`0001_bootstrap_control_plane.sql:88` 近傍の SQL 本体が無変更であることを確認する。
7. **`tools/deploy_smoke.py` が実証されている。** — **監査照合 (実証記録)**: 監査は設計 §11.1 の記録 (段ごとの出力と終了コード) を `docs/ops/BACKUP_RESTORE_R2DB.md` の手順と突き合わせ、**実行したコマンドを報告に逐語で引く** (設計 §9 の 6)。**pytest の完了条件としては扱わない。**
8. **backup / restore が実証されている。** — **監査照合 (実証記録)**: 監査は上記 (d) の形式の記録が設計 §11.1 にあること、**復元前後で catalog と 1 query の結果が一致したこと**を確認し、**実行したコマンドを報告に逐語で引く** (設計 §9 の 6)。
9. **両 peer に同名で置いたヘルパが同型性テストの対応表に載っている。**
10. **`docs/ops/BACKUP_RESTORE_R2DB.md` に実値が 1 件も無い。** — **監査照合**: 監査は `tools/public_value_scan.py` の出力 (total_flagged=0) と目視の両方で確認する。
11. **L7-19 は撤去条件未達であり、据え置く。** `constraints.txt:42` は `starlette==1.6.0` であり上流に修正版が無い。**ファイル変更は行わない。** — **監査照合**: 監査は `constraints.txt:42` と `filterwarnings` の 3 箇所 (`pyproject.toml:5`、`r2db-api/pyproject.toml:94`、`MitateDB-api/pyproject.toml:70`) が無変更であることを確認する。
12. **新しい共通条件を足していない** (`@pytest.mark.condition` 無し、`CONDITIONS.md` 無変更)。 — **監査照合**。
13. **対応表に対応の無い行が無いこと** (メタ条件)。

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 終了コード表 | **変異 1** |
| 2 `code` 属性 | **変異 2** |
| 3 出力形式と対象外 1 行 | **監査照合** |
| 4 argv 規則 flagged 0 件 | **変異 3** |
| 5 修正前 6 / 修正後 0 の記録 | **監査照合** (実測記録。常設規律 5) |
| 6 `\getenv` 化と migration コメント | **監査照合** |
| 7 smoke test の実証 | **監査照合** (実証記録。設計 §9 の 6) |
| 8 backup / restore の実証 | **監査照合** (実証記録。設計 §9 の 6) |
| 9 同型性テストの対応表 | **変異 4** |
| 10 `docs/ops/` に実値なし | **監査照合** |
| 11 L7-19 据え置き | **監査照合** |
| 12 新条件を足していない | **監査照合** |
| 13 対応表が全行埋まる | 本表そのもの (メタ条件) |

**変異**

1. **終了コード表の 1 行を別の値にする** — `ops.py` の F-4 → 5 の対応を 6 に変える 1 行 → **`F-4` の終了コードを固定する peer-local テストが両 peer で赤**。
2. **`platform_declarations.py` の `code` 属性の付与を 1 箇所落とす** (F-9 の raise から `code=` を外す 1 行) → **該当 F の終了コードが既定値になり、`F-9` のテストが赤**。
3. **`r2db-api/deploy/scripts/part1_provision_host_and_db.sh` に `-v x_password="$FOO"` を 1 行足す** → **`conformance-tests/test_deploy_secret_argv_scan.py` が赤** (flagged 1 件)。
4. **両 peer に同名で置いたヘルパの片方を 1 行変える** (空白でなく実体を変える) → **同型性テスト `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` が赤**。

#### 非空振り要件

- **argv 規則のテストは、走査対象ファイルが 1 件以上あることを assert する** — **`files scanned` が 0 のまま「hits 0 で緑」になる形にしない。** 対象は `r2db-api/deploy/scripts/` 配下の全ファイルと両 peer の `ops.py` (**現行 7 ファイル**) である。
- **`verify-declarations` のテストは F 番号ごとに実際に条件を作る** — 「例外が出ないから緑」ではなく、**当該終了コードが返ること**を assert する。
- **修正前の 6 件が現に flagged されていたことを、修正前の逐語出力で示す** (常設規律 5)。

#### 確定文言のファイル所在

- **本 WP に依頼者確定文言は無い。**
- **終了コード表・出力形式・argv 規則の正規表現・`\getenv` の修正形は設計 §3 D-5 が正本である。** **本書の転記と設計が食い違ったら設計が正である。**
- **`PlatformDeclarationError` のメッセージ文言は既存のものが正本であり、変えない。**

#### 同型性テストの対象

- **両 peer に同名で置くもの**: **`ops verify-declarations` のテスト**と、その中で使う**同名ヘルパ**。**対応表 `_ISOMORPHIC_TARGETS` に行を足す。** **行を足す手順は、行数を含む pin テスト名の更新と、表内の自己参照行の更新を踏む。**
- **`platform_declarations.py` の `code` 属性は両 peer に同型で入る** — **同名ヘルパが生じるなら対応表に載せる。**
- **コードは共有しない** (P-6)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_deploy_secret_argv_scan.py
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python tools/public_value_scan.py
```

**`ops verify-declarations` の PG 系テストには `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` が要る。** **smoke test と backup/restore はローカル PG に対する実証であり、pytest の外で実行する。**

#### 禁止事項

1. **ops CLI の引数に secret を取らない。** **値ではなく環境変数名を取る。** 出力にも secret を出さない (SI-10)。
2. **`PlatformDeclarationError` のメッセージ文言を変えない** (`code` 属性の追加のみ)。
3. **migration ファイル本体を変えない** (`:'control_password'` の参照はそのまま)。**冒頭コメントの使用例だけを直す。**
4. **F-1 / F-2 / F-12 を検査対象に入れない** — 判定できない条件である。**出力の末尾に対象外として書く。**
5. **argv 規則を緩めない。** 偽陽性が出たら**該当行を書き換えるか、allowlist として理由付きで記録する。**
6. **conformance の plug を増やさない** — uvicorn 起動は運用道具の実証であり、L7-2 ではない。
7. **L7-19 に手を付けない** — 撤去条件未達である。`constraints.txt` と `filterwarnings` の 3 箇所を触らない。
8. **`docs/ops/` に実値を書かない** (`<UPPER_SNAKE>` placeholder と `*.example.invalid` のみ)。
9. **`@pytest.mark.condition` を付けない。`CONDITIONS.md` に行を足さない。**
10. **`MitateDB-api/tests/` の limit 系ファイル (WP-1 の成果物) に書き込まない。** ops 系のファイル名を使う。
11. **設計外の検査・機構を足す前に報告して裁定を待つ** (常設規律 7)。

#### 報告形式

1. 触ったファイルと変更行数。
2. **完了条件番号 → 変異の実測**: コマンド、赤になったテスト id、**peer 名**、復元の sha256 二重照合。
3. **設計 §11.1 に記録する実測項目**: (i) argv 規則の**修正前 6 件と修正後 0 件**の逐語出力 (走査コマンドと `files scanned: N hits: M` 行つき)、(ii) smoke test の段ごとの出力と終了コード、(iii) backup / restore の実証記録 (上記 (d) の形式)。
4. **同型性テストの対応表に足した行。**
5. **設計との食い違い** (あれば)。

---

### WP-5 R-12 (性能基準値ハーネス)

#### 目的

**両 peer × 4 plug の性能基準値を、使い捨てでない形で取れるようにする。** **閾値は置かない** (P-8)。**以後の完了ゲートに添える集計行の形式を確定する。**

#### 前提として読む箇所 (設計)

**§1.2 (12)**、**§3 D-6 全文** (決定 1〜5、実装の形、検査の形、開示事項)、**§4 の性能ハーネスに関する却下 1 行**、**§11.2 の表と注記 4 点**、**§10 L8-5 / L8-8 の R-12 行**。

#### 成果物 (ファイル単位)

1. **`tools/perf_baseline.py` (新設)** — 4 adapter の `build_adapter()` を import し、各 plug で **3 op** を warmup + N 回実行して **p50 / p95 (ms)** と **1 要求あたりの backend 呼び出し回数 (`backend_calls`)** を出す。
2. **`tools/PERF_BASELINE_README.md` (新設)** — 実行方法、必要な環境変数 (**HTTP plug は実 PG が要る**)、**数値の意味の限界** (in-process であること、`backend_calls` が往復ではなく呼び出し回数であること、閾値が無いこと)。

#### 実装の指示

**3 op + 1 (設計 D-6 決定 1)**

- **`query`** = `select_eq` (述語 1 個)。
- **`mutate`** = `insert` (1 操作)。
- **`batch`** = **単一 entity の atomic mutation batch** (`attempt_batch_with_addresses`、`conformance-tests/adapter.py:2040`。**操作数 5 で固定**)。**両 peer で比較可能な唯一の複数操作単位であるため 3 列目に採る。**
- **`cross_entity`** (`attempt_cross_entity_batch`、`adapter.py:2064`) は **MitateDB 2 plug でのみ測る 4 列目**である。**`r2db-api` は `cross_entity_mutation: unavailable` を宣言しているので測らない** — **拒否の費用は性能の対象外である。** **ハーネスが宣言を読んで行を出さない。**
- **したがって出力は 4 plug × 3 op = 12 行 + MitateDB 2 plug × `cross_entity` = 2 行、計 14 行である。**

**出力形式 (逐語)**:

```
PERF peer=<peer> plug=<plug> transport=<in-process|asgi-inprocess> op=<query|mutate|batch|cross_entity> n=<N> p50_ms=<x.xxx> p95_ms=<x.xxx> backend_calls=<n.nn>
```

**先頭に実行環境の 1 行を出す (逐語)**:

```
PERFRUN host=<uname -s/-m> python=<version> commit=<short sha> date=<YYYY-MM-DD>
```

**実ホスト名は出さない** (公開規律 — OS 名とアーキテクチャのみ)。

**plug 一覧は `conformance-tests/registry.json` を正本として読む。** **ハーネスに plug 名や module 名を手書きしない。** **`build_adapter()` を呼ぶ前に conftest と同じ準備が要る** — registry の各 entry について **`<peer>/conformance` を `sys.path` に足してから import する** (`conformance-tests/conftest.py:32` の `REGISTRY_PATH`、`:100-105` の `_load_registry`、`:107-145` の `_discover_and_build` と同じ手順)。**registry に plug が増えたら、ハーネスは黙って新しい行を出す。**

**`transport`**: in-process plug は `in-process`、HTTP plug は **`asgi-inprocess`**。**実ソケット plug (L7-2) が入ったら `socket` の列が加わる。**

**反復回数と warmup**: **warmup 20、計測 N = 200** を既定とし、`--n` / `--warmup` で上書きできる。**`batch` (操作数 5) と `cross_entity` は 1 要求が重いので、必要なら `--n` で下げた値を設計 §11.2 に記録する** (**回数は出力行に必ず出る**)。

**`backend_calls`**: 各 plug が構築する backend / cell / 接続オブジェクトを、**ハーネス側の proxy で包み**、**backend の `execute` 相当の呼び出し回数** (in-memory / SQLite plug は backend メソッド、PG plug は cursor の実行) を数える。**1 要求あたりの平均を小数 2 桁で出す。** **製品コードにカウンタを足さない。** **近い前例は `MitateDB-api/tests/test_postgres.py:595-607` である。**

**自己検査は非空性に限定する**: **`query` 1 回に対して `backend_calls >= 1` であることを実行時に assert し、満たさなければ非 0 終了する。** **これ以上の主張 (特定の回数であること) は自己検査に持たせない** — 回数は測定対象であって前提ではない。

#### 完了条件 (assert 水準)

1. **ハーネスの自己検査が「`query` 1 回に対して `backend_calls >= 1`」を実行時に assert し、満たさなければ非 0 終了する。**
2. **plug 一覧が `conformance-tests/registry.json` から読まれており、ハーネスに plug 名・module 名の手書きが 0 件である。** — **監査照合**: 監査は `grep -n 'r2db-api\|MitateDB-api\|conformance_adapter_' tools/perf_baseline.py` が **registry の読み取り以外で 0 件**であることを確認する。
3. **出力が上記の PERF 行形式に逐語で一致し、先頭に PERFRUN 行がある。** — **監査照合**: 監査は実行出力を本節の逐語形式と 1 対 1 で突き合わせる。
4. **`r2db-api` / `r2db-api-http` に `op=cross_entity` の行が出ない。** 出力は **14 行**である。 — **監査照合**: 監査は行数と plug × op の組を数える。
5. **`transport` ラベルが plug と整合する** (in-process 2 plug は `in-process`、HTTP 2 plug は `asgi-inprocess`)。 — **監査照合**。
6. **`tools/PERF_BASELINE_README.md` に、実行方法・必要な環境変数・限界 3 点が書かれている。** — **監査照合**: 監査は設計 D-6 実装の形の README 段落および §11.2 の注記 4 点と突き合わせる。
7. **基準値の実測は監督が完了ゲートで行う** (全 WP マージ後の branch に対して単独実行)。**実装担当は形式確認のための小さな `--n` での試走までとする。** — **監査照合**: 監査はゲート時の PERF 14 行が設計 §11.2 の表に記録され、`commit` がゲート時の branch head と一致することを突き合わせる (設計 §9 の 3)。
8. **閾値を置いていない。** — **監査照合**: 監査はハーネスに合否判定の分岐が**自己検査 (完了条件 1) 以外に無い**ことを確認する。
9. **対応表に対応の無い行が無いこと** (メタ条件)。

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 自己検査の非空性 | **変異 1** |
| 2 registry からの plug 一覧 | **監査照合** (`grep` による静的照合) |
| 3 PERF 行の形式 | **監査照合** |
| 4 `cross_entity` は MitateDB 2 plug のみ / 14 行 | **監査照合** |
| 5 `transport` ラベル | **監査照合** |
| 6 README の限界記述 | **監査照合** |
| 7 基準値の実測は監督ゲート | **監査照合** (設計 §11.2 と branch head の突合) |
| 8 閾値を置いていない | **監査照合** |
| 9 対応表が全行埋まる | 本表そのもの (メタ条件) |

**変異**

1. **`tools/perf_baseline.py` の backend proxy を素通し (カウンタを増やさない) にする 1 行** → **自己検査が `backend_calls >= 1` を満たさず、ハーネスが非 0 終了する。** **実測後に必ず戻す。**

**本ハーネスはテストではない** (設計 D-6 検査の形)。**完了条件 2〜8 は「文書・記録・設定」条件であり、常設規律 2 の運用に従って変異を作らず監査照合とする。** **設計 §9 の 6 に従い、監査は照合対象の逐語記録 (実行したコマンドと PERF 行) を報告に引く。**

#### 非空振り要件

- **自己検査は `query` の 1 回に対して実際に観測した `backend_calls` の値を出す** — 「例外が出なかったから緑」にしない。
- **4 plug すべてについて行が出たことを、出力の行数 (14) で示す。** **plug が 1 本でも欠けたら非 0 終了する。**
- **`registry.json` に entry を 1 つ足すと行が増えることを、scratchpad の複製 registry に対して確認して報告に書く** (= plug 選択を手書きしていないことの実測)。**`conformance-tests/registry.json` 本体は書き換えない。**

#### 確定文言のファイル所在

- **本 WP に依頼者確定文言は無い。**
- **PERF 行 / PERFRUN 行の形式は設計 §3 D-6 が正本である** (複製が `{scratchpad}/phase8-ruling-verbatim.txt`)。**言い換えない。**
- **§11.2 の注記 4 点 (batch の操作数 5 / cross_entity は MitateDB 2 plug のみ / HTTP plug は ASGI in-process / `backend_calls` は往復ではない / 閾値は無い) は設計 §11.2 が正本である。**

#### 同型性テストの対象

- **両 peer に同名で置くものは無い。** `tools/` の 2 ファイルのみである。**adapter を import するが変更しない。**

#### テストコマンド

**本 WP に pytest の完了条件は無い。** 形式確認のための試走のみを行う:

```
./.venv/bin/python tools/perf_baseline.py --warmup 2 --n 5
```

**基準値の実測 (`--warmup 20 --n 200`) は監督が完了ゲートで単独実行する** (速度規律 1)。**実装担当は回さない。**

#### 禁止事項

1. **閾値を置かない** (P-8)。**合否判定は自己検査の非空性だけである。**
2. **製品コードにカウンタ・フックを足さない。** proxy はハーネス側に置く。
3. **plug 名・module 名を手書きしない。** `registry.json` を読む。
4. **`r2db-api` の `cross_entity` を測らない** — 拒否の費用は性能の対象外である。
5. **ハーネス自身が新しい外部依存を足さない** (テスト依存は adapter 経由で入る)。
6. **実ホスト名を出さない** (OS 名とアーキテクチャのみ)。
7. **conformance の plug を増やさない。`registry.json` を書き換えない。**
8. **`--n` の既定値を勝手に変えない** — 変えた場合は出力行の `n=` と設計 §11.2 の脚注に必ず書く。
9. **設計外の検査・機構を足す前に報告して裁定を待つ** (常設規律 7)。

#### 報告形式

1. 触ったファイルと変更行数。
2. **完了条件 1 の変異の実測**: コマンド、終了コード、出力、復元の sha256 二重照合。
3. **試走の PERF 出力 (14 行) を逐語で添える** (小さな `--n` での値であることを明記する)。
4. **registry に entry を足すと行が増えることの実測** (scratchpad の複製に対して)。
5. **設計との食い違い** (あれば)。

---

### WP-6 記録・第 15 次引き継ぎ・計画文書の改版

**着手条件: WP-1〜WP-5 の完了後 (monotonic に main へ取り込まれた後)。**

#### 目的

**本フェーズの実測を正本設計 §11 に固定し、台帳の状態を実態に合わせ、計画文書の R-10 行と R-12 行を R-14 に従って改版する。** **次のフェーズの起点 (第 15 次引き継ぎ) を作る。**

#### 前提として読む箇所 (設計)

**§9 (完了ゲート 8 項目)**、**§10 (台帳 L8-1〜L8-9)**、**§11 (実施記録の枠)**、**§6.4**、計画文書 **§1 / §5 / §7 / §8 / §9**、**`docs/work-orders/HANDOVER_20260906_FABLE.md` §4-2** (L7-22 の記述訂正)。

#### 成果物 (ファイル単位)

1. **`docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` §11** — **§11.1 の集計行 8 項目**、**§11.2 の PERF 14 行と PERFRUN 行**、**§11.3 の WP-1〜WP-6 の実測記録**を記入する。
2. **同 §10** — 台帳 **L8-1〜L8-9** の状態を実測結果で確定する (**L8-1 は閉じる**、**L8-2 は開いたまま据え置く**、**L8-3 は `operation_depth` の実測結果**、**L8-4 は (B) をフェーズ9 へ送る日付と理由**、**L8-5 / L8-6 / L8-7 は開示の記録**、**L8-8 は改版の実施**、**L8-9 はフェーズ9 へ保持**)。
3. **`docs/design/ROADMAP_POST_PHASE7_V1.md`**
   - **§5 / §8 の R-10 行を改版する (L8-8)** — 検査文「現行 JSON から経緯マーカーが消えたこと」を、**根拠 (設計付録 A の逐語インベントリ) と日付を添えて**「**provenance companion (契約 JSON 不変) + register テストによる網羅性の固定**」へ改める (R-14)。
   - **同じ改版で §5 / §7 / §8 の R-12 行の op 名を改める (L8-8)** — 「query / mutate / cross-entity」を「**query / mutate / batch (+ `cross_entity` は `cross_entity_mutation` が `unavailable` でない plug のみ)**」へ。**根拠: r2db は `cross_entity_mutation: unavailable` であり、拒否経路の費用は性能基準値の対象ではない (監督裁定 2026-09-06、設計 D-6)。**
   - **§1「現状」を更新する** (計画文書 §9 の 6)。
4. **`docs/work-orders/HANDOVER_20260906_FABLE.md` §4-2** — **L7-22 の「開いている」という記述を実態に合わせて訂正する** (設計 §10 L8-1)。**フェーズ7 設計 §11 の L7-22 の記述も同様に訂正する。**
5. **`docs/work-orders/HANDOVER_2026MMDD_FABLE.md` (第 15 次、新設)** — 前書全項の継承に加え、本フェーズの成果 (実効化した 4 class、port v1.12、`COLLECTION_FLOOR`、companion、`ops verify-declarations`、性能基準値)、運用規律の追加分、次フェーズの候補 (計画文書 §5 フェーズ9 / 10) を書く。
6. **`conformance-tests/COLLECTION_FLOOR`** — **ゲート時の実測値へ更新する (監督のゲート作業)**。**WP の途中では上げない。**
7. **本作業指示書 §5 の訂正註** — 本フェーズ中に判明した本書の誤り・発注後の監督裁定を、**本文を書き換えずに**訂正註として残す (フェーズ6 §11 L6-18 の流儀)。

#### 完了条件 (assert 水準)

1. **設計 §11.1 の 8 行がすべて埋まっている** (完了ゲート集計行 / CI 3.11 の集計行 / ゲート時の collect 件数 / C-05 V3 の `xfailed` 件数と内訳 / R-10 の sha256 と anchor 件数 / argv 規則の修正前後の出力 / backup-restore 実証 / L7-22 の監査照合記録)。 — **監査照合**: 監査は各行の「取得条件」列と記入内容を突き合わせる。
2. **設計 §11.2 に PERF 14 行と PERFRUN 行が記録され、注記 4 点が残っている。** **`commit` がゲート時の branch head と一致する。** — **監査照合**。
3. **設計 §11.3 に WP-1〜WP-5 の実測項目が記録されている** (WP-1 の (i)〜(v)、WP-2 の L7-23 ガードの実測、WP-3 / WP-4 / WP-5 の記録)。 — **監査照合**。
4. **設計 §10 の台帳 9 項目の状態が実測結果で確定している。** — **監査照合**。
5. **計画文書 §5 / §8 の R-10 行が、根拠と日付を添えて改版されている (L8-8、R-14)。** — **監査照合**: 監査は改版後の行が設計 D-4 決定 6 の文言と整合し、**根拠 (付録 A) と日付 (2026-09-06) が添えられている**ことを確認する。
6. **計画文書 §5 / §7 / §8 の R-12 行の op 名が「query / mutate / batch (+ `cross_entity` は条件付き)」へ改版されている (L8-8)。** — **監査照合**。
7. **計画文書 §1「現状」が更新されている。** — **監査照合**。
8. **L7-22 の記述訂正が第 14 次引き継ぎ §4-2 とフェーズ7 設計 §11 の両方に入っている。** — **監査照合**: 監査は訂正後の記述が `security/CONTROL_MAPPING.md:33` / `conformance-tests/CONDITIONS.md:38` の現物と一致することを突き合わせる。
9. **第 15 次引き継ぎが新設され、前書全項の継承が明示されている。** — **監査照合**。
10. **`COLLECTION_FLOOR` がゲート時の実測値へ更新されている** (監督のゲート作業)。 — **監査照合**: 監査は完了ゲートの `--collect-only -q` 件数と `COLLECTION_FLOOR` の値が一致することを確認する。
11. **本書 §5 の訂正註が、本文を書き換えずに置かれている** (誤りがあった場合)。 — **監査照合**。
12. **公開規律**: 本 WP の全成果物に実値が 1 件も無い。`./.venv/bin/python tools/public_value_scan.py` が **total_flagged=0**。 — **監査照合**。
13. **対応表に対応の無い行が無いこと** (メタ条件)。

#### 完了条件 → 変異 の対応表

**本 WP の成果物はすべて文書・記録である。** **常設規律 2 の運用に従い変異を作らず、全項目を監査照合とする。** **設計 §9 の 6 に従い、監査は照合対象の逐語記録 (file:line と引用文) を報告に引く。**

| 完了条件 | 対応 |
|---|---|
| 1〜12 | **監査照合** (各条件の本文に照合対象を明記済み) |
| 13 対応表が全行埋まる | 本表そのもの (メタ条件) |

#### 非空振り要件

- **記録は「未記入」を残さない。** 取得できなかった項目は「取得できなかった理由」を書く — **空欄のまま完了としない。**
- **監査は §11 の記録を逐語で報告に引く** — 変異が無い項目ほど「何を見て緑と言ったか」を残さないと空振り禁止 (常設規律 1) 側が担保できない (設計 §9 の 6)。

#### 確定文言のファイル所在

- **U-1 / U-2 の依頼者裁定の逐語は設計 §5 に既に記録済みである** (計画文書 §9 の 4)。**引き継ぎに書く場合は設計 §5 から複製し、言い換えない。**
- **計画文書の改版文は設計 D-4 決定 6 と §10 L8-8 が正本である。**

#### 同型性テストの対象

- **無い** (文書のみ)。

#### テストコマンド

```
./.venv/bin/python tools/public_value_scan.py
```

#### 禁止事項

1. **実測を推測で埋めない。** 取得できなかった項目は理由を書く。
2. **本書の本文を書き換えない** — 訂正は §5 の訂正註として残す (原文を消さない)。
3. **計画文書の改版で、R-10 / R-12 以外の行を動かさない。**
4. **`COLLECTION_FLOOR` の更新を WP-6 の実装担当が行わない** — 監督のゲート作業である。
5. **実値を書かない** (`<UPPER_SNAKE>` placeholder と `*.example.invalid` のみ)。
6. **第 15 次引き継ぎで前書の全項を複製しない** — 継承を明示し、**本フェーズが足したものだけを書く。**
7. **設計外の決定を足す前に報告して裁定を待つ** (常設規律 7)。

#### 報告形式

1. 触ったファイルと変更行数。
2. **設計 §11.1 / §11.2 / §11.3 の記入内容** (逐語)。
3. **計画文書の改版前後の R-10 行 / R-12 行** (逐語)。
4. **`tools/public_value_scan.py` の出力** (total_flagged=0)。
5. **設計との食い違い** (あれば)。

---

## 3. 完了ゲート (設計 §9 の転記)

**監督が単独で実行する。** **`ps` で他の pytest プロセスが 0 件であることを確認してから、リポジトリルートで実行する。** **ローカル PostgreSQL の `max_connections = 300` が前提である。**

1. **root suite の単独実行**:

   ```
   ./.venv/bin/python -m pytest -q -n 5 --dist loadgroup
   ```

   - **`xfailed` = 0** (U-1 = (A) 確定)。**U-1 の依頼者裁定は「in-process 経路に要求 dict が無い形であれば in-process 側の 1 組だけ `unavailable` を残す」ことを許しており、その場合は 1 である** — **残った組と理由が C-05 行と設計 §10 L8-3 に開示されていること。**
   - **`skipped` = 0**
   - **`failed` = 0**
2. **CI の 3.11 job の集計行が 1 の集計行と一致すること。** **`tally-consistency` job が緑であること** (3.11 / 3.12 の 4 数の一致。**collect 件数は突合対象に足さない**)。**collection floor step が 3.11 / 3.12 の両 job で緑であること。**
3. **`tools/perf_baseline.py` の PERF 行を設計 §11.2 に記録すること** — **4 plug × 3 op (`query` / `mutate` / `batch`) = 12 行 + MitateDB 2 plug × `cross_entity` = 2 行、計 14 行。** 実行は**全 WP マージ後の branch に対して監督が単独で行う。**
4. **`COLLECTION_FLOOR` をゲート時の実測値へ更新すること。**
5. **R-10 の記録**: **契約 JSON と両 peer の packaged 複製 2 本の sha256 が設計付録 A §A.0 の値と一致すること** (= 契約 JSON が 0 バイト不変であること) を設計 §11.1 に記録すること。**常設スキャナが列挙した JSON パス件数 (= companion の anchor 件数) も併せて記録する。**
6. **全 WP が常設規律 1〜7 と速度規律 1〜5 を満たすこと。** **各 WP の「完了条件番号 → 変異」対応表に、対応の無い行が無いこと。**
   - **変異を持たない完了条件については、「照合対象の逐語記録 (実行したコマンドと集計行、または file:line) を設計 §11 に残すこと」自体を完了条件とする。** **受け入れ監査は §11 のその記録を逐語で報告に引く。**
7. **設計レビュー 1 回** (契約を触らないフェーズ。計画文書 §9 の 3)。**設計 v1.1 で反映済みであり、追加の設計レビューは行わない。**
8. **U-1 / U-2 の依頼者裁定が設計 §5 に逐語で記録されていること** (計画文書 §9 の 4)。**記録済みである。**

---

## 4. コミット規約

1. **git commit / push / merge は監督のみが行う。** **実装担当は commit しない** (常設規律 2)。
2. **push 前に identity を確認する。** **確認は commit と同一のコマンドで行う** (SHARED-CHECKOUT RULE、第 14 次 §4-3):

   ```
   git log --format='%an <%ae>' -5
   ```

   **`r2fish` / noreply のみであること。** 実名・Gmail アドレスが 1 件でもあれば push しない。
3. **commit → push → main マージは 1 セットである** (依頼者ルール、2026-08-29 に拡張)。**マージは専用の別 worktree 経由で行う** — **共有ツリーを checkout しない。**
4. **branch の確認は commit と同一のコマンドで行う** (並行チャットとの衝突を避けるため):

   ```
   git -C <worktree> symbolic-ref --short HEAD && git -C <worktree> commit -m "…"
   ```

5. **宣言と挙動は同一コミットである** (P-3、§0.3 の 1) — `cell.py` の `limit_enforcement` の値変更・enforcement の実装・peer-local テストを **class ごとに 1 コミット**に収める。
6. **V3 xfail の撤去は実装と同一コミットである** (§0.3 の 2) — `_V3_KNOWN_UNAVAILABLE` からの組の削除を、その class の実装コミットに含める。
7. **契約 JSON は 1 バイトも変えない** — 変更が入っていないことを、コミット前に `git diff --stat -- spec/ */src/*/data-service-api.v1.json` で確認する。
8. **公開規律**: コミット前に `.pre-commit-config.yaml` の local hook (staged なファイルに対して走る) が緑であること。**実ホスト名・FQDN・cloud project 識別子・実 e-mail・実 credential_id・IAM principal・作業機の絶対パス・実 DSN を 1 件も含めない。**
9. **変異を含むコミットを作らない。** **変異の復元は scratchpad backup からの `cp` + `sleep 3` 後の sha256 二重照合であり、コミット前に変異文字列を全文 grep してゼロを確認する。** **`git checkout --` は使わない。**
10. **`COLLECTION_FLOOR` の更新コミットは完了ゲートの一部である** (監督)。**下げる場合は理由を commit message に書く。**

---

## 5. 訂正註

**(本フェーズの実施中に、本書の誤り・発注後の監督裁定が生じた場合にここへ追記する。本文は書き換えない。)**

1. **【本書の誤り】§2 WP-2「テストコマンド」3 本目の `conformance-tests/test_c00_contract_discovery.py` は実在しない (2026-09-06)。** 実在するファイルは **`conformance-tests/test_c00_application_escape.py`** (C-00 のマーカーを持つ) である。**ただしファイル名を直しても、このコマンドは目的 (「全体 run の内側なら L7-23 のガードが緑」の部分確認) を果たさない** — 実測は **`1 failed, 17 passed`** であり、落ちるのは `test_every_executable_condition_has_a_marked_test` (`C-01`〜`C-19` の 19 件にマーカーテストが見つからない) である。**L7-23 のガードは「観測 0 件」だけを閉じる設計 (D-3) であり、1 件でも収集される部分実行には効かない** — **設計どおりであって実装の逸脱ではない。** **正しい確認は完了ゲート形式 (`-n 5 --dist loadgroup`) の全体 run である** (実測で緑。設計 §11.3 WP-2)。**設計 §10 L8-16 (a)。**
2. **【追認】§2 WP-1b の逐語表が MitateDB の `hold_in_flight` のラップ対象を「`ApplicationCell` の操作メソッド入口」としているのは、実装では成立しない (監督追認 2026-09-07、WP-1 差し戻し 2 の 6)。** **操作メソッド全体をラップすると `_limit_gate` を実行する前 = concurrency カウンタが増える前に停止するので、停止点要件 (カウンタ取得後・DB 実行前) を満たさない。** **実装は `_limit_gate` 自体をラップする形 (`_StalledGateContextManager` を新設し、`_limit_gate.__enter__()` を実行した後に停止する) であり、監督がこれを追認した。** 停止点は `cell.py:536-537` の counter 増分の後、`cell.py:329` の `_lock` 取得の前である。**変異「ラップを gate の外側へ移す」→ `_drive_concurrency` が `DID NOT RAISE` で赤**であり、位置が load-bearing であることを実測した。**r2db 2 plug は本書の表どおり cell オブジェクト (`catalog`) のラップである。** **設計 §3 D-2 訂正註 1 / §10 L8-16 (b)。**
3. **【発注後の監督裁定 R-A、2026-09-06】隔離 profile の `operation_depth` を 4 → 5 にし、V2 のレシピを `update` + `where` に改めた。** **本書 §2 WP-1a / WP-1b が前提にしていた「フラット insert が深さ 4 に座る」レシピは採らない。** 理由: **depth=4 のままでは隔離面で `where` 付き mutation が全て拒否され、MitateDB の唯一の破壊的操作である `delete` を使う C-04 が MitateDB-http で赤になる** (WP-1a rework 3 の実測)。**新レシピは「`update` + `where` (深さ 5) が成功 / `where` の value を dict にして深さ 6 で `LIMIT_EXCEEDED`」であり、4 plug とも隔離 profile は `operation_depth=5` を宣言する** (driver は `bound == 5` を assert する)。**フェーズ7 設計 D-6.2 の `operation_depth` 行にも訂正註を置いた。** **設計 §3 D-2 訂正註 2 / §10 L8-12 / L8-13。**
4. **【発注後のゲート作業】§2 WP-6 成果物 6 の `conformance-tests/COLLECTION_FLOOR` を、完了ゲート時の実測値 **2274 → 2340** へ更新した (監督、2026-09-07)。** 逐語: `collected=2340` / `COLLECTION_FLOOR check OK: measured=2340 floor=2340 diff=0` / `EXIT=0`。**WP-1〜5 が足したテスト分である。** **§0.3 の 6 のとおり WP の途中では上げていない。** **設計 §11.1。**
