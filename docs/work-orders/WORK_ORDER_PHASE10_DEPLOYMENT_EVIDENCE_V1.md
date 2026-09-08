# フェーズ10 作業指示書 — 配備面の証拠 (契約 1.8.0「資源制限の適用単位」)

- 版数: **v1.2 (2026-09-08)**。v1.1 からの変更: **WP-6d-i の manifest に状態・実施の記録・足したテストの完了条件 11〜13 を書き、WP-R35 の manifest (骨子) を新設した** (設計 v1.4 §3 D-15、計画文書 §8 の **R-35**)。**§0.5 / §1.1 / §1.2 の表に WP-R35 の行を足し、§5 に訂正註 3 を置いた。** **既存 manifest の本文は 1 文も書き換えていない** (`OPERATING_CONDITIONS.md` §1.8 の 57)。
- 旧 **v1.1 (2026-09-08)**。v1.0 からの変更: **外部レビュー 2 (2026-09-08、依頼者提示) の監督検証を受けて、WP-1c と WP-6d (6d-i / 6d-ii) の Change Set Manifest を足し、WP-3 に rework 項目、WP-8 に前提条件、WP-5 に追補を足した** (設計 v1.3 §3 D-13 / D-14、§5 U-7〜U-13)。**§0.5 / §1.1 / §1.2 の表に行を足した。** **WP-9 の完了条件に 17〜20 を、§3 に収集数の増分註・CI の `skipped` / `xfailed` 検査の行・§3.3 の 9〜11 を足した** (設計 v1.3 §9 の 14〜17)。**WP-5 の追補は監督が実施済みである** (branch `phase10-wp5` の `73adbda`)。 **既存の manifest 本文は書き換えず、追記と §5 の訂正註 2 で示す** (`OPERATING_CONDITIONS.md` §1.8 の 57)。
- 旧 **v1.0 (2026-09-08、起草)**
- 形式: **WP ごとの Change Set Manifest** (計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §9 の 9。**フェーズ10 がこの形式で書く最初のフェーズである**)
- 正本設計: `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (**v1.4、確定**。**v1.3 が足したのは D-13 / D-14 と U-7〜U-13、v1.4 が足したのは D-15 と実施記録 §11.4〜§11.6 であり、既存の決定・裁定・却下は 1 つも撤回されていない**)

---

## 0. 位置づけ

### 0.0 正本と委任

1. **設計 v1.2 が正本である。** **§3 の D-1〜D-12 が監督確定**、**§4 の A-1〜A-9 が却下確定**、**§5 の U-1〜U-6 が依頼者委任 (2026-09-07) に基づく監督確定**であり、**いずれも再審議しない** (計画文書 §9 の 4、`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 51)。**§6 が conformance への影響、§8 が WP 分割、§9 が完了ゲート、§10 が台帳、§11 が実施記録である。**
2. **本書は実施発注のみを扱う。** **設計の逐語表・裁定文・却下案・背景は本書に写さず、設計文書の節番号で指す** (計画文書 §9 の 9)。**設計と本書が食い違ったら設計が正であり、本書の誤りとして監督へ差し戻す** (フェーズ9 作業指示書 §0 の流儀)。**訂正は本文を書き換えず §5 に訂正註として追記する** (`OPERATING_CONDITIONS.md` §1.8 の 57)。
3. **契約 1.8.0 の確定文言 4 片は、監督保管の確定文ファイルから逐語で複製する。** **本書にも設計にも言い換えた形を置かない** (常設規律 4、`OPERATING_CONDITIONS.md` §1.5 の 35〜36)。**設計 §3 D-5 (i) が確定文ファイルからの複製を既に載せており、実装はそこから複製する。**
4. **本書が設計から委任を受けて確定するのは「設計が名を与えていない新規ファイル名」だけである** (フェーズ9 作業指示書 §0.0 (b) の流儀)。**それ以外に本書は設計外の決定を持たない。設計に無い検査・機構・語彙が要ると判断したら、実装前に監督へ上げる** (常設規律 5)。
5. **依頼者委任の適用範囲**: **U-1〜U-6 は監督の推奨で確定済みであり、フェーズ完了報告で依頼者に報告する** (設計 §5、§9 の 13)。
6. **起草時の指摘 1〜6 への監督裁定 (2026-09-08) を反映済みである。** **裁定 1 (`registry.json` の 1 行ずつの重なり) は §1.2 の重なり表、裁定 2 (C-19 実ダイヤル枝の担当の切り分け) は WP-3 / WP-4a / WP-5 に反映した。** **裁定 3 (WP-1b の命名)、裁定 4 (WP-8 のテスト形)、裁定 5 (Class の切り分け — 登録済み helper の本体変更 = C、集合の増減 = D)、裁定 6 (テンプレート番号) は受理であり、本文がそのままで整合する。**

### 0.1 常設規律・速度規律

- **常設規律 7 項目は `OPERATING_CONDITIONS.md` §1.5 の 32〜40、速度規律 5 項目は同 §1.6 の 41〜45 である。本書は転記しない。全 WP に掛かる。**
- **変異と復元の規律は同 §1.4 の 28〜31**、**完了ゲートの実行法は同 §1.3 の 19〜27**、**発注とレビューの規律は同 §1.7 の 46〜52**、**公開規律は同 §1.9 の 60〜63** である。**着手前に全項を読むこと** (計画文書 §9 の 7)。

### 0.2 使用テンプレート番号

| 番号 | 役割 |
|---|---|
| **2** | Sonnet 実装 (**コミットしない**) |
| **3** | Opus 起草 (設計文書 / 作業指示書 / ハンドオーバー) |
| **5** | Opus コードレビュー |
| **6** | Opus 証拠監査 / 受け入れパケット |

**レビュー・監査は実装担当と別 instance が行う。レビュー担当は自分で変異を作る** (`OPERATING_CONDITIONS.md` §1.7 の 49、同 §1.6 の 43)。**実装担当に下請け Agent を使わせない** (同 §1.7 の 47)。

### 0.3 変更クラス

**変更クラス A / B / C / D の定義と必要な証拠は計画文書 §9 の 8 の表が正本である。本書は転記せず、各 WP でクラス記号だけを書く。** **1 つのコミットが複数のクラスに触れるときは最も重いクラスを採る** (同)。**`_ISOMORPHIC_TARGETS` 集合の増減 (登録 helper の追加・削除) は Class D であり、監督の pair-closing commit で行う** (設計 §2.2、§8)。

### 0.4 本フェーズ固有の規律

1. **skip を使わない。** **nginx が無ければ fail する** (設計 D-3、§4 A-6、`OPERATING_CONDITIONS.md` §1.3 の 26)。**`skipped` は 0 のままである。**
2. **`COLLECTION_FLOOR` を WP の途中で上げない。** **着手時点の値は 2807 であり、更新は監督が完了ゲートで行う** (設計 §6.3、`OPERATING_CONDITIONS.md` §1.3 の 25)。
3. **新しい共通 Security Invariant を足さない** (設計 §7)。**新しい共通条件は C-26 の 1 件だけである** (設計 §6.2)。**新しい limit class を足さない** (設計 §7)。
4. **宣言と挙動は同一コミットである** (P-3、`OPERATING_CONDITIONS.md` §1.1 の 11)。**先に宣言だけを上げない。**
5. **契約版フリップ (`contract_version` 1.7.0 → 1.8.0) は監督の pair-closing commit である** (§4)。
6. **`process_ceilings` の写像 (設計 D-5 (ii) の 3 区分) を弱める側に倒さない。** **区分 (iii) に lock が無ければ足す。先送りしない** (設計 D-5 (ii))。
7. **代理指標を使わない。** **plug の分類は `transport_kind` の宣言を読み、名前の接尾辞や属性形状から推測しない** (設計 D-4 / D-12、`OPERATING_CONDITIONS.md` §1.7 の 52)。
8. **実値を書かない。** **nginx conf は本番 example から写すが実ホスト名・実証明書パスは写さず、traceback を文書に貼らない** (設計 §0、`OPERATING_CONDITIONS.md` §1.9 の 60〜63)。

### 0.5 本書が確定した新規ファイル名 (§0.0 の 4)

| WP | ファイル |
|---|---|
| WP-3 | `conformance-tests/socket_harness.py`、`conformance-tests/test_socket_harness.py` |
| WP-4a / 4b | `r2db-api/conformance/conformance_adapter_r2db_socket.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` |
| WP-6a / 6b | `r2db-api/migrations/0012_process_ceilings.sql`、`MitateDB-api/migrations/0011_process_ceilings.sql`、両 peer の `tests/test_process_ceilings_declaration.py` |
| WP-6c | `r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py`、`conformance-tests/test_c26_composition_root.py` |
| WP-8a / 8b | 両 peer の `tests/test_threadpool_offload.py` |
| **WP-1c** (v1.1) | **新規ファイルは無い** — budget digest のテストは両 peer の既存 `tests/test_idempotency_records.py` に足す |
| **WP-6d-i** (v1.1) | 両 peer の `tests/test_idempotency_concurrency.py` |
| **WP-6d-ii** (v1.1) | `conformance-tests/test_c27_concurrent_same_key.py` |
| **WP-R35** (v1.2) | **未確定** — 2 スレッドテストを両 peer の既存テストに足すか新設するかは実装報告で監督が確定し、新設する場合の名を本表に足す (§0.0 の 4) |

**plug 名は `r2db-api-socket` / `MitateDB-api-socket` である** (設計 §6.1。本書の確定ではなく設計の確定)。

**`conformance-tests/test_c27_concurrent_same_key.py` の名は監督が確定した** (外部レビュー 2 の裁定枠、2026-09-08。**本書の確定ではない**)。**WP-6d-i の peer テスト名 (`tests/test_idempotency_concurrency.py`) は本書の確定である** (§0.0 の 4)。**WP-1c は新規ファイルを作らない** — 既存の `tests/test_idempotency_records.py` に足すので、§1.1 の 5 (同じディレクトリの系統分け) には当たらない。

---

## 1. 運用の前提 (全 WP 共通)

### 1.1 worktree の割当

1. **並行作業は WP ごとの linked worktree `.claude/worktrees/phase10-wp<N>` で行う** (`OPERATING_CONDITIONS.md` §1.2 の 13)。**`<N>` は WP 記号をそのまま使う** (`phase10-wp1c`、`phase10-wp3`、`phase10-wp4a`、`phase10-wp4b`、`phase10-wp5`、`phase10-wp6a`、`phase10-wp6b`、`phase10-wp6c`、`phase10-wp6d`、`phase10-wp7`、`phase10-wp8a`、`phase10-wp8b`、`phase10-wp9`)。 **【追記 2026-09-08 (v1.2)】WP-R35 の worktree / branch は `phase10-r35` である** — **台帳 ID をそのまま使う形であり、`phase10-wp<N>` の例外として監督が確定した (2026-09-08)。** **R-34 の実施に使った `phase10-r34` も同じ形である。**
2. **共有ツリー (リポジトリルートの作業ツリー) を checkout しない。マージは専用の別 worktree 経由で行う** (同 §1.2 の 14〜15)。
3. **worktree の `.venv` は共有 `.venv` への symlink である。worktree ごとに作り直さない** (同 §2 の 1)。
4. **着手前に「触るファイルの重なり 0」を設計 §8.1 の表と実ファイル名で照合し、重なりが見つかったら実装に入る前に監督へ上げる** (同 §1.2 の 16)。**既知の重なりは §1.2 の重なり表の 1 件だけである。それ以外の重なりを見つけたら上げる。**
5. **同じディレクトリにファイルを足す並行 WP はファイル名の系統を分ける** (同 §1.2 の 17)。**本フェーズでは WP-6 (`test_process_ceilings_*.py`) と WP-8 (`test_threadpool_*.py`) が該当する** (設計 §8.1)。

### 1.2 並行可能な組と直列の組 (**設計 §8.1 が正本**)

**並行可**: **WP-4a ∥ WP-4b**、**WP-6a ∥ WP-6b**、**WP-8a ∥ WP-8b**、**WP-7 ∥ (WP-5 / WP-6)**。

**【追記 2026-09-08 (v1.1)】並行可の追加**: **WP-1c ∥ WP-3 以外のすべて** (`.github/workflows/ci.yml` の領域が異なるので WP-3 とだけ直列にする)、**WP-6d-i ∥ WP-3 / WP-4 / WP-5** (**WP-3 に依存しない。今すぐ着手できる**)、**WP-6d-ii ∥ WP-4**。**直列になるのは下表の 5 行である。**

**重なり表 (触るファイルが重なる並行 WP。本フェーズで該当するのは 1 件だけである)**:

| 重なる WP | ファイル | 重なりの中身 | 解消 |
|---|---|---|---|
| **WP-4a × WP-4b** | `conformance-tests/registry.json` | **各 branch が自 peer の socket plug の登録行を 1 行ずつ足す** (WP-4a = `r2db-api-socket`、WP-4b = `MitateDB-api-socket`)。**既存 4 件の登録内容は両 WP とも変えない** | **監督が 4a → 4b の順で merge し、衝突は両行を残す形で解消する。** **実装担当は相手の行を書かない** |

**設計 §8.1 の「重なり 0」は、この `registry.json` の 1 行ずつを除いた記述である** — **設計側の訂正註は WP-9 の記録時に入れる** (WP-9 の完了条件 16)。**本書は §1.2 の本表を重なりの正本とする。**

**直列 (依存順)**:

| 順序 | 理由 (設計 §8.1) |
|---|---|
| WP-0 → 以降すべて | `security/CONTROL_MAPPING.md` の SI-08 行 (**WP-0 は完了済み。以降は現行行の上に足す**) |
| WP-2 → WP-3 | `.github/workflows/ci.yml` |
| WP-3 → WP-4 | 基底 http adapter の hook と `transport_kind` と harness が要る。**加えて WP-4a が非 vacuity guard を足す先は WP-3 が置く C-19 実ダイヤル枝である** |
| WP-3 → WP-7 | `tools/perf_baseline.py` / `tools/PERF_BASELINE_README.md` |
| WP-3 → WP-6b | `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (依存順で既に成立) |
| WP-3 → WP-6c | `conformance-tests/conftest.py` (依存順で既に成立) |
| WP-4 → WP-6b | **6b が seed を足すまで宣言表を通る MitateDB plug は起動時 fail-fast で落ちる** — 6b の seed 追加が 4b の挙動に効く |
| WP-4 → WP-5 | **C-25 (3) の駆動 plug が socket plug を含み、C-19 の `CONDITIONS.md` 行が「実ダイヤルが socket plug で駆動する」状態を記述する** — **WP-5 が持つのは条件行の改訂だけであり、C-19 のテスト実装は WP-3 / WP-4a が持つ** |
| WP-5 → WP-6a / WP-6b | 契約 packaged 複製 (WP-5 が 3 複製を同一バイトに更新し、WP-6 は `contract_version` の宣言値だけを動かす) |
| WP-5 → WP-6c | `conformance-tests/CONDITIONS.md` |
| WP-6 → WP-6c | C-26 は写像と fail-fast が要る |
| WP-7 → WP-8 | 判定規則の結果で実施可否が決まる |
| WP-9 | 最後。単独 |
| **WP-1c → WP-3** (v1.1) | `.github/workflows/ci.yml`。**領域が異なる** (WP-1c は集計 step と比較 job、WP-3 は conformance job の前段) **ので WP-3 が rebase で吸収する** (設計 §3 D-14、§8.1)。**実施の経過 (2026-09-08): WP-3 が先に main `6055c69` へ入り、WP-1c は main の WP-3 の上に載った。領域が分かれているので競合はしていない** |
| **WP-1c → WP-6d-i** (v1.1) | `MitateDB-api/src/mitatedb_api/cell.py` (WP-1c は `digest_request` の `if budget is not None:`、6d-i は idempotency の lock)。**関数は違うが同一ファイルなので直列に取り込む** (設計 §8.1) |
| **WP-6d-i → WP-6a / WP-6b** (v1.1) | 両 peer の `src/` — **`idempotency_entries` の件数 bound は 6a / 6b、同一キーの直列化は 6d-i の担当であり、同じ関数に両者が入る** (設計 D-5 (ii) の追記 (1)、D-13) |
| **WP-3 → WP-6d-ii** (v1.1) | `conformance-tests/adapter.py` と 4 adapter (hook)。**WP-4 とは並行可** (socket adapter は hook を継承する) |
| **WP-6a / 6b → WP-6d-ii** (v1.1 追補) | 版フリップ。C-27 は 1.8.0 の条件付き義務の実行可能条件であり、フリップ前に入れると xfail を要して CI (`xfailed == 0`、WP-1c) が赤になる (設計 D-13、§8.1) |
| **WP-5 / WP-6c → WP-6d-ii** (v1.1) | `conformance-tests/CONDITIONS.md` (C-27 行を `executable` に改める)。**C-26 / C-27 の宣言行そのものは本改版で既に入っている** |
| **WP-6d-i → WP-R35** (v1.2) | 両 peer の backend (`r2db-api/src/r2db_api/postgres.py` / `MitateDB-api/src/mitatedb_api/backend_postgres.py`)。**関数は違う** (6d-i は idempotency の照会・記録、WP-R35 は `add_field` / `alter_field` の走査 lock) **が同一ファイルなので直列に取り込む** (設計 §8.1 の WP-R35 行)。**WP-6a / 6b とも同じ規約に従う** |

**並行 WP の取り込みは監督が 1 本ずつ直列に行う** (commit → push → main マージが 1 単位。`OPERATING_CONDITIONS.md` §1.1 の 3)。

### 1.3 環境条件

1. **共有 `.venv` (`./.venv/bin/python`、3.11) を使う。システム python を使わない** (`OPERATING_CONDITIONS.md` §2 の 1)。
2. **ローカル PostgreSQL の `max_connections = 300` / `statement_timeout = 0` が前提である** (同 §2 の 3〜4)。**完了ゲートが説明のつかない赤を出したら、まず `pg_db_role_setting` を疑う** (同 §2 の 5)。
3. **nginx は必須依存である** (設計 D-3)。**開発機は Homebrew、CI は apt で入る。版が違うので `nginx -t` の判定は一致しない前提で読む** (同 §2 の 8)。**`nginx` は `NGINX_BIN` env か PATH から探す** (設計 D-3)。**無ければ skip せず fail する。**
4. **docker は開発機に無い。** **`image-pins` の証拠は CI にしかない** — **nginx を必須依存とした D-3 との非対称であり、設計 §10.2 の L10-6 に開示済みである** (設計 D-6 の 5)。**開発機では `tools/check_image_pins.py` の self-test のみを回す。**
5. **テストは前景 Bash で直列に実行し、`timeout` パラメータ 600000 を明示する。`ps` で他の pytest が 0 件であることを確認してから実行する** (同 §1.5 の 39)。**subagent に root suite を回させない** (同 §1.6 の 42)。
6. **変異の復元は scratchpad backup からの `cp` で行い、`git checkout --` は使わない。復元後は `sleep 3` を置いてから sha256 を 2 回照合し、コミット前に変異文字列を全文 grep して 0 件を確認する** (同 §1.4 の 29〜31。本リポジトリは Google Drive 同期ツリーである。同 §2 の 10〜11)。
7. **`tools/public_value_scan.py` のツリーモードは `git ls-files` の対象しか見ない。未追跡の新設ファイルは明示引数で走査する** (同 §2 の 7)。
8. **`--collect-only` にも PostgreSQL と全 DSN 環境変数が要る** (同 §2 の 12)。

---

## 2. WP ごとの Change Set Manifest

---

### WP-0 — R-21 の着手前是正 (**完了。main `bce2598`**)

**状態**: **完了 (2026-09-08)。実装 `c3d9fc9`、main へのマージ `bce2598`。別 worktree で設計起草と並行して実施した。照合記録は設計 §11.0 にある。**

**目的**: 正本文書の陳腐化を着手前に是正する — `security/CONTROL_MAPPING.md` の SI-08 行の MitateDB 記述を現行に更新し、両 peer の README を現行コード・migration 一覧・Route 一覧から書き起こす。**本フェーズは SI-08 の統制記述にさらに 1 行足すので、足す先が誤ったままでは足せない。**

**読むべき正本**: 設計 §3 D-9、§11.0、§1.2 の R-21 行。計画文書 §8 の R-21 行。`security/CONTROL_MAPPING_HISTORY.md` の更新規約。

**触るファイル**: `security/CONTROL_MAPPING.md`、`security/CONTROL_MAPPING_HISTORY.md`、`r2db-api/README.md`、`MitateDB-api/README.md`。

**触らないファイル**: 両 peer の `src/` / `tests/` / `migrations/`、`spec/`、`conformance-tests/`、`tools/`、CI 定義。**旧文を消さない** (履歴へ逐語で移す)。

**完了条件 ↔ 変異**: **本 WP は機械検査を持たない。全項が監査照合である** (設計 D-9「壊すとどう見えるか」、`OPERATING_CONDITIONS.md` §1.5 の 40)。**照合対象の逐語記録を設計 §11.0 に残すこと自体が完了条件である。**

| # | 完了条件 | 種別 / 照合対象 |
|---|---|---|
| 1 | `security/CONTROL_MAPPING.md` に旧文「remain unimplemented on this peer」が 0 件 | **監査照合** — `grep -c` の実測値を設計 §11.0 に記録 |
| 2 | SI-08 行の MitateDB 記述が現行の宣言と一致する (`concurrency` / `requests_per_minute` = `enforced`、`execution_ms` = `reference_wall_clock`) | **監査照合** — 照合対象は `MitateDB-api/src/mitatedb_api/cell.py:4051` / `:4055` / `execution_ms` 行の file:line |
| 3 | 旧文が `CONTROL_MAPPING_HISTORY.md` の `## SI-08` に逐語で在る | **監査照合** — 見出しと逐語一致 |
| 4 | 両 peer の README が現行コード・migration 一覧・Route 一覧から書き起こされている (旧文を写していない) | **監査照合** — 照合対象は各 README の記述と `migrations/` の実在ファイル、`control_http.py` の Route 表 |
| 5 | `CONTROL_MAPPING.md` の行数・列数が変わっていない (1 invariant 1 行の形を保つ。再編は R-22 として範囲外) | **監査照合** |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python tools/public_value_scan.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md r2db-api/README.md MitateDB-api/README.md
  → # mode=... total_flagged=0
./.venv/bin/python tools/check_doc_refs.py
  → check_doc_refs OK: 0 dangling references
./.venv/bin/python -m pytest -q conformance-tests/test_control_mapping_register.py
  → 全 passed (failed / skipped / xfailed の語が集計行に現れない)
```

**使用テンプレート**: **2** (実装) → **5** (コードレビュー)。
**変更クラス**: **D** (`security/` 配下) + **A** (README 2 本)。**分けて出す** (設計 §8)。

---

### WP-1 — R-17 の残: 追跡中の `.md` が 0 バイトなら赤 (**空 `.md` 検査は完了。main `7d8bb0f`**)

**状態**: **空 `.md` 検査は完了 (2026-09-08、実装 `f38716b` / マージ `7d8bb0f`)。** **L10 族の登録 (2 つ目のコミット) が残る** (設計 D-7、§11.1)。

#### WP-1a (完了) — 0 バイト検査

**目的**: `tools/check_doc_refs.py` に「0 バイトの追跡 `.md`」検査を足す (計画文書 §8 の R-17 行、設計 D-7)。2026-09-08 に `docs/work-orders/PUBLICATION_GATE_20260906.md` が Drive 同期の巻き添えで空になり commit `4d4f1a5` に入った事象の再発防止。**L10 族の登録は本 WP に含めない** (script 自身の規約により別個の明示コミットで行う)。

**読むべき正本**: 計画文書 §8 の R-17 行、設計 §3 D-7、`tools/check_doc_refs.py` (特に `iter_scan_files` `:97-114`、`read_lines` `:117-126`、fail-loud 分岐 `:244-287`、`main`)、`tools/tests/test_check_doc_refs.py` (既存 14 テストの形: `tmp_path` に文書を置いて `run()` を直接呼ぶ)、`OPERATING_CONDITIONS.md` §2 の 15。

**触るファイル**: `tools/check_doc_refs.py`、`tools/tests/test_check_doc_refs.py`。
**触らないファイル**: 上記以外すべて (特に `.pre-commit-config.yaml`、`.github/workflows/ci.yml` — **既に always-run で同 script を呼ぶので配線変更は不要**)。

**実装の指示**:

- 対象集合は **`git ls-files -z -- '*.md'`** (repo root で実行。git が使えない / git 外なら既存の `iter_scan_files` の rglob 集合にフォールバックし、その旨を 1 行出す)。**既存の参照検査の走査集合 (72 件) は変えない** — 0 バイト検査は独立の集合を持つ。
- size 0 (`st_size == 0`) の `.md` があれば、パスを 1 行ずつ `EMPTY: <path>` で列挙して exit 1。既存の集計行の直前に `empty markdown files: N` を出す。
- 既存の出力形式・終了コードの意味は変えない (dangling 0 かつ empty 0 のときのみ exit 0)。

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | tmp git repo に追跡済みの空 `.md` を置くと exit 1 で `EMPTY: <path>` が出る | `tools/check_doc_refs.py`: size 判定を `> 0` に反転 → `tools/tests/test_check_doc_refs.py::test_empty_tracked_markdown_fails` |
| 2 | 追跡されていない空 `.md` (未 add) は対象外 (`git ls-files` 集合のみ) | `tools/check_doc_refs.py`: `git ls-files` を rglob に置換 → `::test_untracked_empty_markdown_is_ignored` |
| 3 | 空でない追跡 `.md` のみなら exit 0 で `empty markdown files: 0` | `tools/check_doc_refs.py`: 集計行の文言を変える → `::test_no_empty_markdown_reports_zero` |
| 4 | git 外ディレクトリでは rglob にフォールバックし、空 `.md` を検出して exit 1 | `tools/check_doc_refs.py`: フォールバック分岐を削除 → `::test_fallback_outside_git` |
| 5 | 現行リポジトリで exit 0、`empty markdown files: 0`、`check_doc_refs OK: 0 dangling references` | **監査照合** — 集計行の verbatim を報告に添える |
| 6 | 既存 14 テストが全て緑のまま | **監査照合** — `pytest tools/tests/test_check_doc_refs.py -q` の集計行 |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest tools/tests/test_check_doc_refs.py -q   → 18 passed
./.venv/bin/python tools/check_doc_refs.py; echo exit=$?
  → tracked markdown files scanned: <N>
    empty markdown files: 0
    check_doc_refs OK: 0 dangling references
    exit=0
```

**変異 4 種の赤の verbatim を報告に添える** (復元は scratchpad backup からの `cp` + `sleep 3` + sha256 2 回)。

**使用テンプレート**: **2** → **5** → **6**。**変更クラス**: **B**。

#### WP-1b (**残**) — L10 族の登録

**目的**: `tools/check_doc_refs.py` の ID 族表に **L10-N** を登録し、正本ファイルとして本フェーズの設計文書を足す (設計 D-7)。**現行の `L_REF_RE` (`:194`) は `\bL(?:Q4|[4-9])-\d{1,2}[a-z]?\b` であり `L10-1` に一致しない** — **設計が main に入っても `doc-refs` は赤にならないが、それは「検査されていない」ことを意味する。**

**読むべき正本**: 設計 §3 D-7 の後半、`tools/check_doc_refs.py` の docstring `:16-19` (**この表の変更は「別個の明示コミット」と定めている**)、`L_REF_RE` `:194`、`PHASE_CANONICAL` `:208-214`。

**触るファイル**: `tools/check_doc_refs.py` (`L_REF_RE` と `PHASE_CANONICAL` の 2 定数のみ)、`tools/tests/test_check_doc_refs.py`。
**触らないファイル**: 上記以外すべて。**WP-1a で入れた 0 バイト検査の実装に触らない。**

**完了条件 ↔ 変異**:

| # | 完了条件 | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | `L10-<N>` が ID 参照として認識される (`L_REF_RE` が 2 桁フェーズに一致する) | `tools/check_doc_refs.py`: `L_REF_RE` を変更前に戻す → `tools/tests/test_check_doc_refs.py::test_l10_reference_is_recognised` |
| 2 | `PHASE_CANONICAL` が `L10` → `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` を持ち、設計に無い `L10-<N>` を別の docs に書くと dangling として exit 1 になる | `tools/check_doc_refs.py`: `PHASE_CANONICAL` の L10 行を削除 → `::test_dangling_l10_reference_fails` |
| 3 | 既存族 (`L4`〜`L9` / `LQ4`) の判定が変わらない | `tools/check_doc_refs.py`: 正規表現を `L\d+` に広げて `LQ4` を落とす → 既存の族テストが赤 |
| 4 | 本 WP が **WP-1a とは別のコミット**である (script の docstring の規約) | **監査照合** — `git log --oneline` で 2 コミットに分かれていること |
| 5 | 現行リポジトリで `check_doc_refs.py` が exit 0 | **監査照合** — 集計行の verbatim |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest tools/tests/test_check_doc_refs.py -q   → 20 passed 以上
./.venv/bin/python tools/check_doc_refs.py; echo exit=$?
  → empty markdown files: 0 / check_doc_refs OK: 0 dangling references / exit=0
```

**非 vacuity の実測** (完了条件 2): **設計 §10.2 に無い `L10-<N>` を任意の `.md` に一時的に書き、`check_doc_refs.py` が dangling として報告することを確認してから消す。** **報告に verbatim を添える。**

**使用テンプレート**: **2** → **5**。**変更クラス**: **B**。

---

### WP-1c — 外部レビュー 2 の小修正の束 (**新設 v1.1**)

**状態**: **実装済み (2026-09-08)。worktree / branch `phase10-wp1c`、実装 `5944013` (+ main `504c8b2` のマージ)。** **Opus のコードレビューの判定は「accept with fixes」であり、指摘の是正を反映した確定コミットは `2431e93` である。** **main へのマージは次のゲート束で監督が行う (現時点で main 未マージ)。** **発注時の想定より範囲が広い** — **MitateDB の budget 是正は `transact` だけでなく `cell.py` のスキーマ操作 3 箇所 (`create_collection` / `add_field` / `alter_field`) の digest 生成にも要り、`security/CONTROL_MAPPING.md` の SI-00〜SI-03 の受入境界も同じ陳腐化を持っていた** (下記「実施の記録」)。

**目的**: 外部レビュー 2 が挙げた 3 件を 1 つの WP で直す — **MitateDB の digest から `budget: {}` が落ちる不具合** (計画文書 §8 の R-25)、**CI が `skipped` / `xfailed` = 0 を強制していないこと** (同 R-26)、**文書の矛盾 2 件** (同 R-28 の (1) (2))。**WP-3 より先に main へ入れる。**

**読むべき正本**: 設計 §3 **D-14**、§5 **U-11**、§8 の WP-1c 行、§8.1 の WP-1c 行。計画文書 §1.0d と §8 の **R-25** / **R-26** / **R-28**。契約 `spec/data-service-api.v1.json` の `idempotency.record` (budget を含む全フィールドが再送一致の対象である旨)。`docs/work-orders/OPERATING_CONDITIONS.md` §1.3 の 22 と 26。`docs/work-orders/DEPLOY_PHASE6_20260904.md` の項 9〜12。`docs/work-orders/PUBLICATION_GATE_20260906.md` §3.2。

**触るファイル**: `MitateDB-api/src/mitatedb_api/cell.py` (**`digest_request` の 1 行 + スキーマ操作 3 箇所 `create_collection` / `add_field` / `alter_field` の digest 生成**)、両 peer の `tests/test_idempotency_records.py`、`.github/workflows/ci.yml` (**集計 step と比較 job のみ**)、`r2db-api/README.md`、`docs/work-orders/HANDOVER_20260908_FABLE.md` (**追記のみ**)、**`security/CONTROL_MAPPING.md` (SI-00〜SI-03 の受入境界の文のみ。このコミットは変更クラス D)**。

**触らないファイル**: `spec/` 配下と 3 複製の契約 JSON、`conformance-tests/` 配下、`security/` 配下の**他の行と他のファイル** (**`CONTROL_MAPPING.md` の SI-00〜SI-03 の受入境界の文だけが対象であり、統制・証拠の記述と他の invariant 行には触らない**)、`tools/`、`COLLECTION_FLOOR`、`r2db-api/src/` (**r2db の `service.py:1237` は既に `is not None` である**)、`.github/workflows/ci.yml` の **conformance job の前段** (**WP-3 の領域**)、`docs/work-orders/HANDOVER_20260908_FABLE.md` の**既存本文** (**書き換えない。追記だけである**)、`docs/work-orders/PUBLICATION_GATE_20260906.md`。

**実装の指示 (要点)**:

1. **`MitateDB-api/src/mitatedb_api/cell.py:2702` の `if budget:` を `if budget is not None:` にする** (r2db `r2db-api/src/r2db_api/service.py:1237` と同じ形)。**`digest_request` は plan digest も作るので、両方に効く。** **【実施で判明。v1.1 の追記】** **`transact` だけでは足りない** — **スキーマ操作 3 箇所 (`create_collection` / `add_field` / `alter_field`) の digest 生成にも同じ穴がある。** **HTTP 層は既に `digest_extra` で `budget` を渡していたが、in-process の cell 経路は渡していなかったので、同じ要求が経路によって別の digest になり得た。** **両経路の digest が一致することが是正の要件である** (この一般則は計画文書 §8 の **R-33** に起票した)。
2. **両 peer にテストを足す** — **budget を省略した要求と `budget: {}` を付けた要求が異なる要求であること**を、(i) 同一キーでの再送が `CONFLICT` になること、(ii) plan digest が異なること、の 2 つで示す。**両 peer に同じ命題のテストを置く** (r2db 側は回帰、MitateDB 側は是正の証拠)。
3. **`.github/workflows/ci.yml`**: **集計 step と比較 job の両方**に `skipped == 0` / `xfailed == 0` の検査を足す (**3.11 / 3.12 とも**)。**既存の 4 数の記録と 3.11 == 3.12 の一致検査は残す** (足すのであって置き換えではない)。**【監督裁定 2026-09-08 (検査の拡張)】** **`xpassed` と `deselected` も `> 0` を赤にする** — **`xpassed` は宣言が陳腐化した xfail であり、`deselected` は集計行が suite 全体を表していないことを意味するからである** (`OPERATING_CONDITIONS.md` §1.3 の 22 / 26。設計 §3 D-14、§5 U-11)。
4. **`r2db-api/README.md:158`** を `docs/work-orders/DEPLOY_PHASE6_20260904.md` の項 9〜12 に基づいて書き直す — **事実のみ**を書き、**新しい主張を足さない** (「未導入」→ 2026-09-05 に Stage 1 を VPS へ初回導入し外部到達を確認した、という記録どおりの事実)。**旧文を写さない** (R-21 の是正と同じ規律)。
5. **`docs/work-orders/HANDOVER_20260908_FABLE.md` §1 に日付付きの訂正註を追記する** — 「フェーズ7 の残は WP-9 だけ」の記述に対し、**同日後刻の `docs/work-orders/PUBLICATION_GATE_20260906.md` §3.2 (手順 0〜6.5 実施済み、visibility 切替のみ依頼者判断で保留) を指す。** **引き継ぎ書は履歴であり書き換えない — 追記である** (`OPERATING_CONDITIONS.md` §1.8 の 56 / 58)。
6. **【実施で判明。v1.1 の追記】** **`security/CONTROL_MAPPING.md` の SI-00〜SI-03 の受入境界 (acceptance boundary) の文を書き直す** — **4 の README と同じ陳腐化 (「VPS には未導入」の前提) を持っていた。** **2026-09-05 の r2db Stage 1 の記録から書き起こし、旧文を写さない** (WP-0 / R-21 と同じ規律)。**`security/` を触るので、そのコミットは変更クラス D である** (裁定記録を添える。**内容は現状記述の更新であり security-contract の変更ではない**)。**`CONTROL_MAPPING_HISTORY.md` の履歴規約に従う。**

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | MitateDB で **budget 省略と `budget: {}` が異なる要求である** — 同一キーの再送が `CONFLICT` になる | `MitateDB-api/src/mitatedb_api/cell.py`: `is not None` を `if budget:` に戻す → `MitateDB-api/tests/test_idempotency_records.py::test_empty_budget_is_not_the_same_request_as_an_omitted_budget` |
| 2 | MitateDB で **plan digest が省略と `{}` で異なる** | 同上 → `MitateDB-api/tests/test_idempotency_records.py::test_empty_budget_changes_the_plan_digest` |
| 3 | r2db でも同じ 2 命題が成立する (回帰) | `r2db-api/src/r2db_api/service.py`: `is not None` を `if budget:` にする → `r2db-api/tests/test_idempotency_records.py` の同名 2 テスト |
| 4 | CI の**集計 step**が `skipped != 0` / `xfailed != 0` / **`xpassed != 0`** / **`deselected != 0`** で赤になる | `.github/workflows/ci.yml`: 集計 step の検査行を削除 → **合成した集計入力 (`2807 passed, 1 skipped` / `2 xfailed`) を食わせると緑になる** (**非 vacuity の実測。下記**) |
| 5 | CI の**比較 job**が `skipped != 0` / `xfailed != 0` / **`xpassed != 0`** / **`deselected != 0`** で赤になる (**3.11 / 3.12 とも**) | `.github/workflows/ci.yml`: 比較 job の検査行を削除 → 同上 |
| 6 | 既存の 4 数の記録と 3.11 == 3.12 の一致検査が残っている | **監査照合** — 差分の目視 (足すのであって置き換えではない) |
| 7 | `r2db-api/README.md:158` が `DEPLOY_PHASE6_20260904.md` 項 9〜12 の**事実のみ**で書き直されている (新しい主張が無い) | **監査照合** — 照合対象は同 DEPLOY 文書の項 9〜12 の逐語と、書き直し後の README の当該段落 |
| 8 | `HANDOVER_20260908_FABLE.md` §1 に**日付付きの訂正註が追記**されており、**既存本文が 1 文字も変わっていない** | **監査照合** — `git diff` が追加行のみであること (削除行 0) |
| 9 | `check_doc_refs` と `public_value_scan` が緑 | **監査照合** — 集計行の verbatim |
| **10** (**v1.1 の追記。実施で判明**) | MitateDB の**スキーマ操作 3 箇所** (`create_collection` / `add_field` / `alter_field`) でも budget 省略と `budget: {}` が異なる要求である — **in-process の cell 経路と HTTP 経路の digest が一致する** | `MitateDB-api/src/mitatedb_api/cell.py`: いずれかのスキーマ操作の digest から `budget` を落とす → `MitateDB-api/tests/test_idempotency_records.py` の当該テスト |
| **11** (**v1.1 の追記。実施で判明**) | `security/CONTROL_MAPPING.md` の SI-00〜SI-03 の受入境界が **2026-09-05 の Stage 1 の記録に基づく事実のみ**で書き直されている (新しい主張が無い) | **監査照合** — 照合対象は `DEPLOY_PHASE6_20260904.md` 項 9〜12 の逐語と書き直し後の当該文。**旧文は `CONTROL_MAPPING_HISTORY.md` に逐語で在る** |

**非 vacuity の実測 (完了条件 4 / 5)**: **合成した集計入力 (例 `2807 passed, 1 skipped in 300.00s`、および `2 xfailed`) を検査に食わせて赤になることを実測し、verbatim を報告に添える。** **本物の suite を skip させて確かめない。**

**【実施の記録 2026-09-08。branch `phase10-wp1c` の `5944013`、確定コミット `2431e93`】** **実測**: `MitateDB-api/tests` は **`997 passed`**、`r2db-api/tests` は **`1172 passed`**、`tools/tests` は **`58 passed`**、**CI 検査は合成した集計入力 (`2807 passed, 1 skipped` / `2 xfailed`) で赤**である。**触ったファイルは上記「触るファイル」のとおりで、`security/CONTROL_MAPPING.md` の SI-00〜SI-03 を含む。** **main へのマージは次のゲート束で監督が行う。**

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q MitateDB-api/tests/test_idempotency_records.py \
    r2db-api/tests/test_idempotency_records.py                → 全 passed
./.venv/bin/python -m pytest -q <両 peer>/tests                → 全 passed
./.venv/bin/python -m pytest -q conformance-tests/test_c23_idempotency_semantics.py \
    conformance-tests/test_c22_dry_run_and_plan.py             → 全 passed (回帰確認)
./.venv/bin/python tools/check_doc_refs.py
  → empty markdown files: 0 / check_doc_refs OK: 0 dangling references
./.venv/bin/python tools/public_value_scan.py <触った全ファイル> → total_flagged=0
```

**使用テンプレート**: **2** → **5** → **6**。**変更クラス**: **B**。**ただし `security/CONTROL_MAPPING.md` を触るコミットは D である** (裁定記録を添える。内容は現状記述の更新であり security-contract の変更ではない。WP-0 と同じ扱い)。

---
### WP-2 — R-19: 本番 image / 配備手順を `constraints.txt` の exact-pin に揃える (**完了。main `c9a937a`**)

**状態**: **完了 (2026-09-08、実装 `79958a7` / マージ `c9a937a`)。`.github/workflows/ci.yml` の重なりは WP-3 が後続する形で解消済みである** (設計 §8.1)。

**目的**: CI (`pip install -c constraints.txt`) と本番 image / 配備手順の依存解決を一致させ、CI で image の pin を検査する (計画文書 §8 の R-19 行、設計 D-6)。

**読むべき正本**: 計画文書 §8 の R-19 行、設計 §3 D-6、`MitateDB-api/docker/Dockerfile` 全体 (build context が repo root であることの注記 `:25-36`、`:50-51`; `pip install` `:65`; 「no version drift」文 `:61-64`)、`constraints.txt` (冒頭手順の「除外した項目」の記述と 22 エントリ)、`.github/workflows/ci.yml` (job 構造、`doc-refs` job `:315-326` の形、`deploy-assets-lint` job)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:124`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md:606`・`:1567`、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh:425`。

**触るファイル**: `MitateDB-api/docker/Dockerfile`、`.github/workflows/ci.yml` (**新 job `image-pins` の追加のみ。既存 job は触らない**)、新規 `tools/check_image_pins.py`、新規 `tools/tests/test_check_image_pins.py`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh` (**コメント行のみ**)。
**触らないファイル**: `constraints.txt`、両 peer の `pyproject.toml`、`src/`、`tests/`、`conformance-tests/`、他の CI job。

**実装の指示**:

1. **Dockerfile**: builder stage で `COPY constraints.txt ./` を足し (context は repo root)、`RUN pip install --no-cache-dir -c constraints.txt .` にする。`:61-64` のコメントを「`constraints.txt` の exact-pin で CI と同じ解決」に書き直す (**旧文の主張は不成立だった旨を 1 行**)。
2. **r2db の配備文書 3 箇所と script コメント 1 箇所**の `pip install` に `-c constraints.txt` (repo root 相対。`git archive` 配布の展開先を基準に書く) を足す。
3. **`tools/check_image_pins.py`** (標準ライブラリのみ): stdin または `--freeze <file>` で `pip freeze` 出力を読み、`--constraints constraints.txt` と比較する。**除外集合は逐語で定数に列挙**: `pip`、`setuptools`、`wheel`、および image 自身の distribution 名 (`-e` 行 / `@ file://` 行も除外)。それ以外の全 `name==version` 行が constraints に同一 (name 大小・`-`/`_` 正規化のうえ) で存在しなければ `MISMATCH: <name> image=<v> constraints=<v|absent>` を列挙して exit 1。一致なら `image pins OK: N packages checked` で exit 0。
4. **CI job `image-pins`** (ubuntu-latest、常時実行、`needs` なし): image を `docker build` → `docker run --rm --entrypoint /opt/venv/bin/pip <image> freeze` → `tools/check_image_pins.py` で比較。`timeout-minutes: 15`。
5. **開発機に docker は無い。** ローカルでは script の self-test のみ。**job の実証は CI run で行う** (監督が push 後に読む)。

**完了条件 ↔ 変異**:

| # | 完了条件 | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | freeze と constraints が一致する fixture で exit 0、`image pins OK: N packages checked` | `tools/check_image_pins.py`: 比較を常に OK にする → `tools/tests/test_check_image_pins.py::test_mismatch_detected` |
| 2 | version が 1 つ違う fixture で exit 1、`MISMATCH:` 行にその name | `tools/check_image_pins.py`: 比較の等号を外す → `::test_mismatch_detected` |
| 3 | 除外集合 (`pip` / `setuptools` / `wheel` / 自 distribution) は比較対象外 | `tools/check_image_pins.py`: 除外集合を空にする → `::test_exclusions_are_not_compared` |
| 4 | constraints に無い package が image にあれば exit 1 (`constraints=absent`) | `tools/check_image_pins.py`: absent 判定を削除 → `::test_absent_pin_is_mismatch` |
| 5 | 名前正規化 (`Foo_Bar` = `foo-bar`) で一致扱い | `tools/check_image_pins.py`: 正規化を削除 → `::test_name_normalization` |
| 6 | Dockerfile が `constraints.txt` を COPY し `-c constraints.txt` で install する | **監査照合** — `grep -n "constraints" MitateDB-api/docker/Dockerfile` が COPY 行と RUN 行の 2 件以上 |
| 7 | r2db の 3 文書 + script コメントに `-c constraints.txt` (grep で 4 件) | **監査照合** |
| 8 | `ci.yml` が YAML として読め、job `image-pins` が存在する | **監査照合** |
| 9 | CI run で `image-pins` が緑 | **監査照合** — 監督が push 後に job 結果を確認 |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest tools/tests/test_check_image_pins.py -q   → 5 passed 以上
./.venv/bin/python tools/public_value_scan.py <触ったファイル>          → total_flagged=0
bash -n r2db-api/deploy/scripts/part1_provision_host_and_db.sh          → 出力なし (exit 0)
```

**非 vacuity の実測** (設計 D-6「壊すとどう見えるか」): **`constraints.txt` の 1 行の版を image と違う値に変えて `image-pins` が赤になることの実測。**

**使用テンプレート**: **2** → **5** → **6**。**変更クラス**: **B**。

---

### WP-3 — 実 socket の場を作る + 基底 http adapter の hook 抽出 (**完了。main `6055c69`**)

**状態**: **完了 (2026-09-08)。実装 `8d39260`、main へのマージ `6055c69`。別セッションが実施した。** **adapter port は `docs/design/CONFORMANCE_ADAPTER_V1.md` v1.14 に上がり、`.github/workflows/ci.yml` に nginx の導入と socket 残骸検査が入った。** **v1.1 の追記 (実装の指示 11 / 完了条件 18) は、本 WP のマージ後に届いたので rework ではなく main に対する follow-up として実施した — branch `phase10-wp3f` の `ea237e5`、次のゲート束でマージする。**

**目的**: プロセス・port・reverse proxy の面倒を見る共通 harness を置き、`ConformanceAdapter` に `transport_kind` を足し、基底 http adapter に client factory / `surfaces` 値 / 隔離 surface の 3 hook を挙動不変で抽出する。**socket adapter そのものは WP-4 が置く。**

**読むべき正本**: 設計 §3 **D-1 (A) の 4・5・6**、**D-2** (harness の責務 (a)〜(g) と起動予算)、**D-3** (nginx conf の条件)、**D-4** (C-19 実ダイヤル枝の形。**本 WP が枝を置き、非 vacuity assert は WP-4a、条件行の改訂は WP-5**)、**D-11 の (1) (2)** (CI)、**D-12** (`_classify_plug`)、§6.1 の (1) と (3)、§6.3 (adapter port の版数)、§8 の WP-3 行、§8.1。`OPERATING_CONDITIONS.md` §1.3 の 24 / 26、§1.5 の 32〜40、§1.7 の 52。

**触るファイル**:

- `conformance-tests/socket_harness.py` (**新設**)
- `conformance-tests/test_socket_harness.py` (**新設**)
- `conformance-tests/adapter.py` (`transport_kind` の抽象属性の追加)
- `conformance-tests/conftest.py` (遅延起動が `_discover_and_build` と両立することの配線)
- `conformance-tests/test_c19_client_self_sufficiency.py` (**実ダイヤル枝の分岐を `transport_kind == "socket"` で書く。非 vacuity guard は置かない** — 下記「実装の指示」10)
- `conformance-tests/registry.json` (**既存 4 件の登録内容は変えない。socket plug 2 件の登録行は WP-4a / WP-4b が各 1 行ずつ足す** — WP-3 の時点では adapter モジュールが無い)
- `docs/design/CONFORMANCE_ADAPTER_V1.md` (**v1.13 → v1.14。`transport_kind` の節を 1 つ新設。版数の正本は同文書 `:5-11` の文書情報行**)
- `tools/perf_baseline.py` (`_classify_plug` `:158-201` を宣言読みに改める)、`tools/PERF_BASELINE_README.md`
- `.github/workflows/ci.yml` (**nginx 導入 step + service 停止行 + 残骸検査 step**)
- `r2db-api/conformance/conformance_adapter_r2db_http.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (**hook 抽出のみ。挙動不変**)

**触らないファイル**: 両 peer の `src/` / `migrations/` / `tests/`、`spec/` 配下と両 peer の packaged 契約複製、`security/` 配下、`conformance-tests/CONDITIONS.md` (WP-5 / WP-6c が触る)、既存の in-process 2 adapter (`conformance_adapter_r2db.py` / `conformance_adapter_mitatedb.py`) の **`transport_kind` 宣言 1 行以外**、`conformance-tests/COLLECTION_FLOOR`。

**実装の指示 (要点。詳細は設計の該当節)**:

1. **harness** (設計 D-2): 責務 (a) uvicorn (thread 版 / subprocess 版、readiness、停止)、(b) nginx (conf 生成 + `nginx -t` + 起動)、(c) free port、(d) 終了時 kill、(e) `atexit`、(f) 起動時 sweep (自分の prefix 配下の pidfile)、(g) 遅延起動。**subprocess 版は WP-6c が使う** — **本 WP で両方を置く** (設計 D-2)。
2. **起動予算**: **upstream 1 本あたり 30 秒** (設計 D-1 (A) 5)、**surface 1 面 (uvicorn 2 本 + nginx 1 本) 合計 60 秒** (設計 D-2 (a))。**超えたら fail する。skip しない。**
3. **readiness**: **proxy 経由で `GET /v1/capabilities` を Authorization 無しで送り、HTTP 応答 (status < 500。期待は 401) が返った時点で ready。data / control の両 upstream で行う** (設計 D-1 (A) 5)。
4. **nginx conf**: 本番 example (`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`) の proxy 設定を写し、listen / upstream / パスと prefix 系設定だけを差し替える。**`client_max_body_size 0`**、**`proxy_read_timeout` は app の `execution_ms` 上限より長い値を明示**、**prefix 配下に `pid` / `error_log` / `access_log off` / `client_body_temp_path` / `proxy_temp_path` を明示**。**TLS は張らない** (設計 D-3、§4 A-8)。**実ホスト名・実証明書パスは写さない。**
5. **`transport_kind`**: **`"in_process"` / `"asgi"` / `"socket"` の 3 値、既定は無い抽象属性。既存 4 adapter は現状どおりの値を 1 行ずつ宣言する (挙動は変わらない)** (設計 D-1 (A) 4、§6.1 (1))。
6. **hook 抽出** (設計 D-1 (A) 6): **(a) `_build_client(app, base_url) -> httpx.AsyncClient`** (既定は `ASGITransport`)、**(b) `_surfaces_value() -> dict`** (既定はモジュール定数)、**(c) 隔離 surface の構築も同じ hook を通す**。**現物の重複点は `conformance_adapter_r2db_http.py:1060` / `:1127` / `:1532` / `:1970` / `:2075-2110`、`surfaces` の焼き付きは `:1048` / `:1219` / `:2097` である。**
7. **`_classify_plug`**: **`transport_kind` の宣言を読む形に改める。名前と宣言が食い違う plug は従来どおり `UnknownAdapterShape` で非 0 終了する** (`tools/perf_baseline.py:196-201`。設計 D-12)。
8. **CI**: `sudo apt-get install -y nginx` の**直後に** `sudo systemctl disable --now nginx || sudo service nginx stop` を置く。**残骸検査は harness prefix 一致で行う** (prefix でスコープしない `pgrep` は runner の無関係なプロセスに当たる)。**表記は `sudo` 付きで統一する** (設計 D-11)。
9. **起動本数の実測 (10 本か 12 本かは xdist の挙動で変わる) を取り、設計 §11 に記録する** (設計 D-2 (g))。
10. **C-19 の実ダイヤル枝** (設計 D-4): **`test_c19_client_self_sufficiency.py` に `transport_kind == "socket"` で分岐する枝を書き、`surfaces` の宣言値へ実 TCP で data 面・control 面の両方をダイヤルする。** **判定は宣言を読む — plug 名の接尾辞や URL 形から推測しない** (`OPERATING_CONDITIONS.md` §1.7 の 52)。**WP-3 の時点では socket plug が存在しないので、枝は 0 plug で通る。** **「registry に `transport_kind == "socket"` の plug が 1 件以上」という非 vacuity assert は本 WP では置かない** — **socket plug が無い時点で置けば赤になる。この assert は WP-4a が足す** (§1.2 の依存順、WP-4 の完了条件 12)。**C-19 の `CONDITIONS.md` 行の改訂は WP-5 が持つ。本 WP は条件行に触らない。**

**【追記 2026-09-08 (v1.1)。追跡是正 (follow-up) 項目 1 件。設計 D-2 の追記、§5 U-12】** **11. 起動時 sweep (責務 (f)) に `pid <= 0` の明示 guard を置く** — **`pid <= 0` は「自分のものではない」扱いとし、pidfile だけを消して signal しない** (`os.kill(0, …)` はプロセスグループ、`os.kill(-1, …)` は全プロセスを指す)。**所有者検査 (prefix marker 一致) は本 WP の実装に既に在り、marker 検査が先行するので実害経路は無い** — **明示の guard とテスト 1 本を足すのが本項である** (計画文書 §8 の **R-27**)。

**【実施済み 2026-09-08。本 WP は main `6055c69` にマージ済みだったので rework round 2 ではなく main に対する follow-up として実施した。branch `phase10-wp3f` の `ea237e5`】** **`sweep_orphans` は解釈した pid が `0` 以下なら pidfile を消し、`_process_cmdline` を呼ばず、signal しない。** **テストは `conformance-tests/test_socket_harness.py::test_sweep_orphans_never_signals_a_non_positive_pid` である。** **変異の実測: guard を外すと赤になり、`_process_cmdline must never be called with a non-positive pid, got -1` を出す。** **`conformance-tests/test_socket_harness.py` は `30 passed`、`tools/tests` は `61 passed`。** **main へのマージは次のゲート束で監督が行う。**

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | readiness は proxy 経由の HTTP 応答で判定し、app の import が失敗する構成では ready にならず 30 秒で fail する | `conformance-tests/socket_harness.py`: readiness を TCP connect 成功のみにする → `conformance-tests/test_socket_harness.py::test_readiness_rejects_a_failing_app` |
| 2 | surface 1 面の起動が 60 秒を超えたら fail する (skip しない) | `socket_harness.py`: 面あたりの予算を無制限にする → `::test_surface_startup_budget_is_enforced` |
| 3 | nginx conf が prefix 配下の `pid` / `error_log` / `client_body_temp_path` / `proxy_temp_path` を明示し、1 MiB 超の body が 500 にならず app まで届く | `socket_harness.py`: temp path 行を conf 生成から落とす → `::test_large_body_reaches_the_app_through_the_proxy` |
| 4 | `client_max_body_size 0` であり、proxy は app の `request_bytes` を隠さない | `socket_harness.py`: `client_max_body_size` を app の bound より小さい値にする → `::test_proxy_does_not_shadow_the_app_bound` |
| 5 | 起動前に `nginx -t` を通す | `socket_harness.py`: `nginx -t` 呼び出しを削除 → `::test_invalid_conf_fails_before_start` |
| 6 | 正常終了・異常終了 (`atexit`)・起動時 sweep の 3 経路でプロセスと port の残骸が 0 になる | `socket_harness.py`: 終了時 kill を削除 → `::test_no_process_or_port_residue` |
| 7 | 遅延起動 — port を 1 度も呼ばない worker は uvicorn も nginx も起こさない | `socket_harness.py`: 構築時に eager 起動する → `::test_lazy_start_does_not_launch_on_build` |
| 8 | `transport_kind` は既定を持たない抽象属性であり、宣言しない adapter は build 時に落ちる | `conformance-tests/adapter.py`: `transport_kind` に既定値 `"asgi"` を置く → `conformance-tests/test_socket_harness.py::test_every_registered_adapter_declares_transport_kind` |
| 9 | `_classify_plug` が `transport_kind` の宣言を読み、名前接尾辞・属性形状に依らない | `tools/perf_baseline.py`: `_classify_plug` を名前接尾辞判定に戻す → `tools/tests/test_perf_baseline.py::test_classify_plug_reads_the_declaration` |
| 10 | hook 抽出後も既存 4 plug の集計行が抽出前と一致する (**挙動不変**) | **監査照合** — 手順は下記「hook 抽出の挙動不変の検証手順」 |
| 11 | 隔離 surface の構築が (a) (b) の hook を通る (継承先が override 可能である) | `conformance_adapter_r2db_http.py`: `isolated_application_surface` の client 構築を hook を通さない直接構築に戻す → `test_socket_harness.py::test_isolated_surface_goes_through_the_hooks` |
| 12 | CI に nginx 導入 step・service 停止行・prefix スコープの残骸検査 step が在る | **監査照合** — `.github/workflows/ci.yml` の該当 step と、CI run で `conformance` job が緑 |
| 13 | `CONFORMANCE_ADAPTER_V1.md` が v1.14 であり `transport_kind` の節を持つ | **監査照合** — 同文書 `:5-11` の文書情報行 |
| 14 | 起動本数の実測値が記録されている | **監査照合** — 設計 §11 への記録 |
| 15 | C-19 の実ダイヤル枝の判定が **`transport_kind == "socket"` の宣言読み**であり、名前・URL 形から推測していない | `conformance-tests/test_c19_client_self_sufficiency.py`: 判定を plug 名の接尾辞に戻す → `test_c19_client_self_sufficiency.py::test_c19_surfaces_declare_and_echo_on_http_plugs` の判定根拠 assert |
| 16 | 実ダイヤル枝が **data / control の両面**をダイヤルする | `test_c19_client_self_sufficiency.py`: control 面のダイヤルを落とす → 同テストの両面 assert |
| 17 | **本 WP の差分に registry 非 vacuity assert が無い** (socket plug が 0 件の時点では置けない。assert は WP-4a が足す) | **監査照合** — 差分の目視。**枝が 0 plug で通ったことを報告に verbatim で添える** |
| **18** (**v1.1**。**main への follow-up として充足。branch `phase10-wp3f` の `ea237e5`**) | 起動時 sweep が **`pid <= 0` を「自分のものではない」扱い**にする (**pidfile のみ削除、`_process_cmdline` を呼ばない、signal しない**) | `conformance-tests/socket_harness.py`: `pid <= 0` の guard を削除 → `conformance-tests/test_socket_harness.py::test_sweep_orphans_never_signals_a_non_positive_pid` (**実測の赤: `_process_cmdline must never be called with a non-positive pid, got -1`**) |

**hook 抽出の挙動不変の検証手順 (完了条件 10)**:

1. **抽出前の集計行は、main の CI 3.11 job (`conformance (Python 3.11)`) から取る** — **その job が正本である** (`tally-consistency` job が「3.11 tally is authoritative」と定めている。`.github/workflows/ci.yml:277-295`)。**取得元は同 job の `pytest-tally-3.11` artifact の 4 数 (passed / failed / skipped / xfailed) である。**
2. **抽出後は WP-3 の branch で同じ 4 数を得る** — **開発機では `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` を監督が単独実行し** (`OPERATING_CONDITIONS.md` §1.3 の 19〜22)、**CI では WP-3 の push が回す 3.11 job の 4 数を読む。**
3. **4 数が一致することを報告に verbatim で添える。** **warnings の数は一致判定に用いない** (同 §2 の 2)。**socket plug はまだ登録されていないので、collected 数も一致するはずである** — **一致しなければ抽出が挙動を変えている。**

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q conformance-tests/test_socket_harness.py          → 全 passed
./.venv/bin/python -m pytest -q conformance-tests/test_c19_client_self_sufficiency.py
  → 全 passed (**実ダイヤル枝は socket plug 0 件で通る。skip しない**)
./.venv/bin/python -m pytest -q conformance-tests                                  → 全 passed (skipped 0 / xfailed 0)
./.venv/bin/python -m pytest -q tools/tests                                        → 全 passed
./.venv/bin/python tools/perf_baseline.py --n 10 --warmup 2
  → PERFRUN host=... python=... commit=... date=...
    PERF peer=... plug=... transport=<transport_kind の宣言と 1 対 1 のラベル> op=... n=10 p50_ms=... p95_ms=... backend_calls=...
./.venv/bin/python tools/public_value_scan.py <新設・変更した全ファイル>            → total_flagged=0
```

**使用テンプレート**: **2** → **5** → **6**。**変更クラス**: **C** (`conformance-tests/` 配下)。

---

### WP-4a / WP-4b — 各 peer の socket adapter (5・6 番目の plug)

**目的**: 既存 HTTP adapter を継承し、transport 層だけを実 socket + nginx に差し替えた完全 adapter を各 peer に置き、`registry.json` に `required: true` で登録する。**composition は既存 HTTP adapter と同一であり、変わるのは transport だけである** (設計 D-1 (A))。

**読むべき正本**: 設計 §3 **D-1 (A) の 1〜6**、**D-2**、**D-3**、**D-4 の 1**、**D-10 の 3** (control 面の `audit_query` 宣言は継承する)、§6.1 の表、§8 の WP-4 行、§8.1 の WP-4 × WP-6b 行、§10.2 の **L10-7**。`OPERATING_CONDITIONS.md` §1.5 の 32 / 38。

**触るファイル**:

- **WP-4a**: `r2db-api/conformance/conformance_adapter_r2db_socket.py` (**新設**)、`conformance-tests/registry.json` (**`r2db-api-socket` の 1 行の追記のみ。既存 4 件と相手 peer の行に触らない。§1.2 の重なり表を読むこと**)、`conformance-tests/test_c19_client_self_sufficiency.py` (**WP-3 が置いた実ダイヤル枝に非 vacuity guard を 1 件足すだけ。枝の判定そのものに触らない**)
- **WP-4b**: `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` (**新設**)、`conformance-tests/registry.json` (**`MitateDB-api-socket` の 1 行の追記のみ。既存 4 件と相手 peer の行に触らない。§1.2 の重なり表を読むこと**)

**触らないファイル**: 両 peer の `src/` / `migrations/` / `tests/`、`conformance-tests/socket_harness.py` と `adapter.py` (**WP-3 の成果物。足りない機能が出たら実装前に監督へ上げる**)、`conformance-tests/CONDITIONS.md` (**WP-5 / WP-6c が触る**)、`test_c19_client_self_sufficiency.py` **以外の条件テスト** (**WP-5 が触る**)、**WP-4b は `test_c19_client_self_sufficiency.py` にも触らない** (**非 vacuity guard は WP-4a が 1 件だけ置く**)、基底 http adapter (**WP-3 の hook をそのまま使う。基底に手を入れたくなったら上げる**)、`spec/` 配下、`security/` 配下、`COLLECTION_FLOOR`、**相手 peer の一切**。

**実装の指示 (要点)**:

1. **既存 HTTP adapter を継承し、WP-3 の hook (a) `_build_client` と (b) `_surfaces_value` を override する。** **他の port メソッドは継承のままにする** (設計 D-1 (A) 1)。
2. **DB 隔離 (admin DSN / startup sweep / throwaway prefix / advisory lock / migration / 実 CLI による bootstrap・reset) は継承し、prefix だけ socket 用の別系統にする** — **既存 HTTP plug と同時実行しても衝突しない形にする** (設計 D-1 (A) 1)。
3. **`surfaces` の値は既存の注入経路のまま、値を自分の nginx の実 loopback URL にする** (`.../v1` と `.../control/v1`。設計 D-1 (A) 2、D-4 の 1)。
4. **隔離 surface は自分専用の uvicorn thread + nginx instance を持つ** (port 別、遅延起動、`with` 終了で停止)。**親の handle を共有しない** — **`copy.copy(self)` の上書きが漏れると隔離面が親の共有 app を serve したまま緑で通り、C-05 の隔離駆動が無音で誤る** (設計 D-1 (A) 6)。
5. **隔離 profile の bound 値は既存 HTTP plug と同じにする** (`conformance_adapter_r2db_http.py:856`)。**socket plug のためだけに bound を動かさない** (設計 D-1 (A) 3。L8-12)。
6. **`transport_kind = "socket"` を宣言する** (設計 D-1 (A) 4)。
7. **WP-4a のみ — C-19 実ダイヤル枝の非 vacuity guard**: **WP-3 が置いた枝に「registry に `transport_kind == "socket"` の plug が 1 件以上ある」ことを `registry.json` から読む形で assert する guard を 1 件足す** (`--dist loadgroup` では plug ごとに worker が分かれるので、suite 内の集約に依存しない形にする)。**4a の merge 時点で `r2db-api-socket` が存在するので guard は成立する。** **枝の判定そのもの (`transport_kind` 読み) には触らない — WP-3 の成果物である。** **WP-4b はこの guard に触らない** (4b が入れば socket plug は 2 件になるが、guard の閾値は 1 件以上のままである)。
8. **WP-4b の注意**: **MitateDB plug は宣言表を通る。** **WP-6b が `process_ceilings` の seed を足すまでは `process_ceilings` の行が無く、WP-6 完了後は seed が無いと起動時 fail-fast で落ちる** — **WP-4b は WP-6b より先に入り、seed の追加は WP-6b が行う** (設計 §8.1 の WP-4 × WP-6b 行)。

**完了条件 ↔ 変異 (1 対 1。各 peer で同じ表を持つ)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | plug が `required: true` で登録され、**全条件が緑** (skip 0 / xfail 0) | `conformance-tests/registry.json`: 当該行の `required` を `false` にする → `conformance-tests/test_c05_limit_declaration_agreement.py::test_c05_all_plug_names_match_the_registry` (registry と plug 名の突合) |
| 2 | `transport_kind == "socket"` を宣言する | `conformance_adapter_<peer>_socket.py`: 宣言を `"asgi"` にする → `conformance-tests/test_socket_harness.py::test_every_registered_adapter_declares_transport_kind` の値域 assert (WP-3 の成果物) |
| 3 | client が実 TCP で nginx を叩く (`base_url` が自分の nginx の port である) | `conformance_adapter_<peer>_socket.py`: `_build_client` の override を外す (親の `ASGITransport` に戻る) → `conformance-tests/test_c19_client_self_sufficiency.py::test_c19_surfaces_declare_and_echo_on_http_plugs` の実ダイヤル枝 (**WP-3 が置いた枝。本 WP は枝に触らず、駆動される側として赤にする**) |
| 4 | **非 vacuity**: 隔離 surface の `base_url` が親の `base_url` と異なる (自分専用の uvicorn + nginx を持つ) | `conformance_adapter_<peer>_socket.py`: 隔離 surface の handle 上書きを落として親の handle を共有する → `conformance-tests/test_socket_harness.py::test_isolated_socket_surface_has_its_own_base_url` |
| 5 | `surfaces` の値が自分の nginx の実 URL であり、data / control の両面が到達可能である | `conformance_adapter_<peer>_socket.py`: `_surfaces_value` の port を実 port と違う値にする → `test_c19_client_self_sufficiency.py` の実ダイヤル枝 (**WP-3 が置いた枝**) が接続失敗で赤 |
| 6 | C-05 の `request_bytes` 枝が **app の構造化拒否** (`LIMIT_EXCEEDED` + `limit_class`) を観測する (proxy の 413 ではない) | `conformance-tests/socket_harness.py`: 当該 plug の conf で `client_max_body_size` を app の bound 未満にする → `test_c05_limit_declaration_agreement.py::test_c05_v2_declaration_and_position_agree` の `request_bytes` 枝 |
| 7 | DB 隔離の prefix が既存 HTTP plug と別系統であり、同時実行しても衝突しない | `conformance_adapter_<peer>_socket.py`: prefix を http plug と同じにする → 並行実行で C-15 系 (bootstrap/reset) が赤 |
| 8 | 隔離 profile の bound 値が既存 HTTP plug と同一である | `conformance_adapter_<peer>_socket.py`: 隔離 profile の 1 値を動かす → `test_c05_limit_declaration_agreement.py::test_c05_v3_fixed_nine_are_not_unavailable` 系の宣言・位置突合 |
| 9 | control 面が `audit_query: enabled` を宣言する (継承。**製品コードにも既存 4 plug の宣言にも触っていない**) | `conformance_adapter_<peer>_socket.py`: control composition から audit reader DSN を落とす → `conformance-tests/test_c09_audit_evidence.py` の全レジストリ guard |
| 10 | 終了時にプロセス・port の残骸が 0 である | `conformance_adapter_<peer>_socket.py`: `close` から harness の停止呼び出しを外す → `test_socket_harness.py::test_no_process_or_port_residue` |
| 11 | 既存 4 plug の集計行が本 WP の前後で変わらない (足したぶんだけ増える) | **監査照合** — collected 数の差分が socket plug 1 件ぶんであること |
| 12 | **(4a のみ) 非 vacuity**: C-19 実ダイヤル枝に「registry に `transport_kind == "socket"` の plug が 1 件以上ある」を **`registry.json` から読む形で** assert する guard が在る (`--dist loadgroup` で suite 内集約に依存しない) | `conformance-tests/test_c19_client_self_sufficiency.py`: guard を suite 内の集約 assert に戻す → registry guard テスト。**併せて `registry.json` から socket plug の行を一時的に外すと guard が赤になることを実測する** |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q conformance-tests                → 全 passed (skipped 0 / xfailed 0)
./.venv/bin/python -m pytest -q conformance-tests/test_c19_client_self_sufficiency.py \
    conformance-tests/test_c05_limit_declaration_agreement.py \
    conformance-tests/test_c09_audit_evidence.py                 → 全 passed
./.venv/bin/python -m pytest -q <自 peer>/tests                  → 全 passed
./.venv/bin/python tools/public_value_scan.py <新設ファイル>      → total_flagged=0
```

**報告に添える実測**: **完了条件 4 の非 vacuity** (隔離 surface の `base_url` と親の `base_url` を並べた 2 値)、**C-19 実ダイヤル枝が data / control の両面で駆動したことの verbatim**、**(4a のみ) 完了条件 12 の guard が registry から socket plug を外すと赤になることの verbatim** (変異は復元し、コミットに含めない)。

**使用テンプレート**: **2** → **5** → **6**。
**変更クラス**: **C** — **宣言値 (`transport_kind` / `audit_query`) に触り、peer の `conformance/` は共通 suite の実現部だからである** (設計 §8)。**同名 helper が生じたら `_ISOMORPHIC_TARGETS` への行追加は監督の pair-closing commit (Class D) である。**

---

### WP-5 — 契約 1.8.0 + CONDITIONS 4 行の改訂 + C-25 (3) の駆動条件の付け替え

**目的**: 適用単位を定義する契約 1.8.0 の 4 片を入れ、C-05 / C-09 / C-19 / C-25 の 4 行を改訂し、**C-25 (3) の駆動条件を data 面の capability 文書から control 面 discovery の `audit_query` 宣言に付け替える** (設計 D-5 (i)(v)、D-3、D-4、**D-10**)。

**読むべき正本**: 設計 §3 **D-5 (i)** (**確定文 4 片。監督保管の確定文ファイルからの逐語**)、**D-5 (v)** (版の手順と義務件数)、**D-10** (付け替えの形 (1)〜(5))、**D-4** (C-19 の改訂。**本 WP が持つのは `CONDITIONS.md` の C-19 行の改訂だけであり、実ダイヤル枝は WP-3、非 vacuity guard は WP-4a が持つ**)、**D-3** (C-05 (3) の開示)、§6.2 の表と `CONDITIONS.md` 更新規約、§6.1、§9 の 4 / 9、§10.0 の L9-15 行、§11 (実測の記録先)。フェーズ9 の版上げ手順 (`docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md`)。

**触るファイル**:

- `spec/data-service-api.v1.json`、`r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` (**3 複製を同一コミットで同一バイトに**)
- `spec/CONTRACT_HISTORY.md`、`spec/CONTRACT_HISTORY_MANIFEST.json`、`spec/CCR_DISPOSITION.md` (**従属判断 13**)、`spec/OPERATION_CATALOG.json` (**再生成**)
- `conformance-tests/CONDITIONS.md` (**C-05 / C-09 / C-19 / C-25 の 4 行 + 改訂**)、`conformance-tests/CONDITIONS_HISTORY.md` (**旧文を逐語で移送**)
- `conformance-tests/test_c25_result_request_id.py` (**`_audit_query_status` を control 面読みに改める**)、`conformance-tests/test_c09_audit_evidence.py` (**駆動 plug の記述のみ**)、`conformance-tests/test_c05_limit_declaration_agreement.py` (**honest limits の開示**)
- `conformance-tests/test_contract.py` (**確定文の逐語 PIN**)、`conformance-tests/test_contract_history_register.py`、`conformance-tests/test_operation_catalog_register.py`、`conformance-tests/test_conditions_register.py`

**触らないファイル**: 両 peer の `src/` / `migrations/` / `tests/` (**製品コードにも既存 4 plug の宣言にも触らない**。設計 D-10 の 5)、`conformance/` 配下の adapter 一式、`conformance-tests/test_c19_client_self_sufficiency.py` (**実ダイヤル枝は WP-3、非 vacuity guard は WP-4a の成果物である。本 WP が C-19 について持つのは `CONDITIONS.md` の条件行の改訂だけである**)、`conformance-tests/socket_harness.py`、`security/` 配下、`.github/workflows/ci.yml`、`tools/`、`COLLECTION_FLOOR`。

**実装の指示 (要点)**:

1. **契約 4 片は設計 §3 D-5 (i) の (1)〜(4) から逐語で複製する。言い換え・要約・語順の入れ替えを行わない。** **挿入先は同節が指定している** ((1) は `capability_status.rules` 配列末尾、(2) は **`limits.profile` の文字列の末尾** — **新しいキーを作らない**、(3) は `versioning.obligations` の 1.8.0 entry (**既存 entry と同じ 4 キー**)、(4) は `spec/CONTRACT_HISTORY.md` の anchor 文)。**契約側に確定文を逐語 assert する文字列ピンのテストを置く** (常設規律 4)。
2. **義務件数は設計 D-5 (v) の実測値を使う** — **1.8.0 = 無条件 1 / 条件付き 0、無条件義務の総数 14 → 15、L9-10 が数える 1.6.0 以降の累計は 5 件である。2 つの数え方を混ぜない。**
3. **C-25 の `_audit_query_status` を、C-09 の `_audit_query_declaration` と同じ形 (control credential での `control_capabilities()` 読み) に改める** (設計 D-10 (1))。**port に新しい primitive を足さない** (`conformance-tests/adapter.py:1231`、`:1431` が既存)。
4. **`CONDITIONS.md` の更新規約に従う** — **訂正は現行行を書き換え、旧文は `CONDITIONS_HISTORY.md` の当該 ID 見出しへ逐語で移す** (同 `:5-19`)。**セル長は `test_conditions_register.py:56` の `MAX_CELL_LENGTH = 3000` 以内** (現行実測は C-05 が 2,962 字、C-09 が 2,950 字、C-19 が 2,944 字)。**移送は長さ対策ではなく更新規約そのものの履行である。**
5. **駆動 plug の実測を設計 §11 に記録する** — **裁定の見込みは「既存 http 2 plug + socket 2 plug」であり、実際の集合は宣言の実測で決まる。主張と実測を混ぜない** (設計 D-10 (3))。
6. **C-19 について本 WP が持つのは `CONDITIONS.md` の条件行の改訂だけである。** **実ダイヤル枝の実装は WP-3、registry 非 vacuity guard は WP-4a が既に入れている** — **本 WP の着手時点で両方が main に在る** (§1.2 の依存順)。**条件行は「実ダイヤルが `transport_kind == "socket"` の plug で data / control 両面について駆動する」という、その時点の実装のとおりに書く。** **テストに手を入れたくなったら実装前に監督へ上げる** (常設規律 5)。
7. **`C-26` の行は本 WP では入れない** (WP-6c が入れる)。**本書と設計の `C-26` 参照は、その行が入るまで `check_doc_refs` が dangling として報告する — フェーズ9 の C-20〜C-25 と同じ経過である** (設計 §6.2)。

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | 契約 4 片が確定文と逐語一致する | `spec/data-service-api.v1.json`: (1) の 1 語を言い換える → `conformance-tests/test_contract.py::test_contract_pins_the_1_8_0_ruling_sentences_verbatim` |
| 2 | (2) が `limits.profile` の**文字列**に入っており新しいキーを作っていない | `spec/data-service-api.v1.json`: (2) を新キーとして置く → `test_contract.py` の `limits` 構造 assert |
| 3 | `versioning.obligations` に 1.8.0 entry (4 キー、無条件 1 / 条件付き 0) が在る | `spec/data-service-api.v1.json`: `unconditional` を空にする → `test_contract.py` の obligations 件数 assert |
| 4 | 契約 3 複製の sha256 が一致する | `r2db-api/src/r2db_api/contract/data-service-api.v1.json`: 1 バイト変える → `conformance-tests/test_contract.py` の 3 複製一致 assert |
| 5 | `spec/CONTRACT_HISTORY.md` の anchor 文が逐語であり manifest と整合する | `spec/CONTRACT_HISTORY.md`: anchor 文を要約する → `conformance-tests/test_contract_history_register.py` |
| 6 | `spec/CCR_DISPOSITION.md` に従属判断 13 が在る | `spec/CCR_DISPOSITION.md`: 13 を落とす → `test_contract.py` の従属判断突合 |
| 7 | `spec/OPERATION_CATALOG.json` が再生成一致する | `spec/OPERATION_CATALOG.json`: 1 値を手で書き換える → `conformance-tests/test_operation_catalog_register.py` |
| 8 | C-25 (3) の駆動条件が **control 面 discovery の `audit_query` 宣言**であり、**駆動 plug が 1 件以上ある** (非 vacuity) | `conformance-tests/test_c25_result_request_id.py`: `_audit_query_status` を data 面読みに戻す → `test_c25_result_request_id.py` の非 vacuity guard (駆動 plug 0 件で赤) |
| 9 | C-25 (3) の `observed_branch` が **その plug 自身の control 面の宣言が含意する枝**と一致する | `test_c25_result_request_id.py`: `observed_branch` の突合を落とす → 同ファイルの個別 guard |
| 10 | `CONDITIONS.md` の C-19 行が **その時点の実装のとおり**に改訂されている (実ダイヤルは `transport_kind == "socket"` の宣言で分岐し、data / control 両面で駆動する)。**テストには触っていない** | **監査照合** — 設計 §6.2 の C-19 行との逐語突合と、差分に `test_c19_client_self_sufficiency.py` が含まれないこと |
| 11 | `CONDITIONS.md` の改訂 4 行の旧文が `CONDITIONS_HISTORY.md` に逐語で在る | `conformance-tests/CONDITIONS_HISTORY.md`: 1 行を要約に置き換える → `conformance-tests/test_conditions_register.py` の履歴突合 |
| 12 | `CONDITIONS.md` の全 Status セルが 3000 字以内である | `conformance-tests/CONDITIONS.md`: 移送せずに追記する → `test_conditions_register.py`(`MAX_CELL_LENGTH`) |
| 13 | C-05 の honest limits に「プロセス横断の同時性は peer-local pin と配備規律と C-26 (4) が担う」と、proxy が bound を隠していないことの開示が在る | **監査照合** — 設計 §6.2 の C-05 行と逐語突合 |
| 14 | C-25 (3) を駆動した plug 名と件数が設計 §11 に記録されている | **監査照合** — 集計行または `observed_branch` の実測 |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q conformance-tests/test_contract.py \
    conformance-tests/test_contract_history_register.py \
    conformance-tests/test_operation_catalog_register.py \
    conformance-tests/test_conditions_register.py                → 全 passed
./.venv/bin/python -m pytest -q conformance-tests/test_c25_result_request_id.py \
    conformance-tests/test_c09_audit_evidence.py \
    conformance-tests/test_c19_client_self_sufficiency.py \
    conformance-tests/test_c05_limit_declaration_agreement.py    → 全 passed
    (test_c19 は回帰確認である。本 WP は同ファイルに触らない)
shasum -a 256 spec/data-service-api.v1.json \
  r2db-api/src/r2db_api/contract/data-service-api.v1.json \
  MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json → 3 本とも同一値
./.venv/bin/python -m pytest -q conformance-tests                → 全 passed (skipped 0 / xfailed 0)
```

**【追記 2026-09-08 (v1.1)。追補 1 件。設計 §5 U-9 / D-13】** **契約 1.8.0 の `idempotency.record` に、同時送信の直列化義務を 1 文足す** — 「同時に到着した同一キーの要求も直列化され、高々 1 件が実行される。他方は先着の commit の後に再送として答えられる (replay または `CONFLICT`)。先着が失敗したなら新規要求として扱われる」の趣旨である。**1.8.0 は未公開 (裁定の時点では branch `phase10-wp5` の `654e23e`) なので版は動かさない。** **packaged 複製 3 つを同一バイトに保つ。** **本追補は WP-5a の branch に足す追補コミットとして監督が実施する** — **実装担当の発注範囲ではない。** **確定文言は監督保管の確定文ファイルから逐語で複製する** (常設規律 4)。

**【完了 2026-09-08。branch `phase10-wp5` の `73adbda`「Phase 10 WP-5a addendum (U-9)」。WP-5a 本体は `654e23e` の時点で main `3d7f823` にマージ済みであり、本追補はそこに含まれない — 次のゲート束で監督がマージする (現時点で main 未マージ)】** **義務 id は `idempotency_concurrent_same_key_sends_serialized` (capability `idempotency`) であり、1.8.0 の `conditional` の (1) として `versioning.obligations` に入れた。** **`structured_operations.idempotency.record` と `versioning.version_binding` の 1.8.0 段落、`spec/CONTRACT_HISTORY.md` (改版註 2)、`spec/CCR_DISPOSITION.md` の従属判断 13 (小項目 (c))、`spec/README.md` (marker の無い 4 値)、`conformance-tests/test_contract.py` (PIN と新規テスト 1 本) を追随させた。** **`conformance-tests` は `652 passed`、packaged 複製 3 つは同一バイト、版は 1.8.0 のままである。** **実装担当は本項に対して行うことが無い** — **WP-6d-i / 6d-ii は契約 JSON を触らない。**

**使用テンプレート**: **2** → **5** → **6**。**変更クラス**: **C**。

---

### WP-6a / WP-6b — 配備者宣言 `process_ceilings` (両 peer 同型) + 版フリップ

**目的**: 配備者宣言 `process_ceilings` を宣言表に 1 行足し、`limit_enforcement` の写像 (設計 D-5 (ii) の 3 区分) を成立させ、`contract_version` を 1.8.0 にフリップする。**機構は Q4 D-2 と同じ — 表が唯一の出所、`ops declare-process-ceilings` で書く、`ops verify-declarations` に F-15 を足す、行が無ければ起動時 fail-fast。**

**読むべき正本**: 設計 §3 **D-5 (ii)** (機構と 3 区分の表と実装点)、**D-5 (iii)** (配備側と upgrade 順序)、**D-5 (iv)** (peer-local と共通 suite の分担)、**D-5 (v)** (版)、§6.1 の (2)、§7 の SI-08 / SI-10 行、§8 の WP-6 行、§8.1、§10.0 の LQ4-24 行、§10.2 の **L10-2**。`OPERATING_CONDITIONS.md` §1.1 の 11、§1.5 の 38。**Q4 設計 `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` の D-2 (a) / D-2 (d) / D-3 (d)。**

**触るファイル**:

- **WP-6a (r2db)**: `r2db-api/migrations/0012_process_ceilings.sql` (**新設**)、`r2db-api/src/r2db_api/platform_declarations.py`、`ops.py` (**`declare-process-ceilings` サブコマンド、`verify-declarations` の F-15、`_VERIFY_DECLARATIONS_EXIT_CODES` に exit code 14**)、`main.py` / `control_main.py` (**起動時 fail-fast**)、`service.py` / `control_plane.py` (**写像と区分 (iii) の lock**)、`postgres.py` (**`idempotency_entries` の check-then-write**)、`r2db-api/tests/test_process_ceilings_declaration.py` (**新設**) と既存 peer-local テスト、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` / `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` / `r2db-api/deploy/scripts/` (**宣言 step と upgrade 順序。LQ4-24 を参照**)、`r2db-api/src/r2db_api/` の `contract_version` 宣言 (**版フリップ**)
- **WP-6b (MitateDB)**: `MitateDB-api/migrations/0011_process_ceilings.sql` (**新設。`_upgrade.sql` で終わらせない**)、同型の `src/mitatedb_api/` 一式 (`platform_declarations` 相当 / `ops.py` / composition root / `cell.py` / `control_plane.py` / `pool.py`)、`MitateDB-api/tests/test_process_ceilings_declaration.py` (**新設**)、`MitateDB-api/docs/cloud-run-cloud-sql.md` (**Invariant 1 の一般化**)、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (**seed 1 行 + migration 一覧に `0011`**)、`contract_version` 宣言 (**版フリップ**)

**触らないファイル**: `spec/` 配下と 3 複製の契約 JSON (**WP-5 が同一バイトに更新済み。本 WP は `contract_version` の宣言値だけを動かす**)、`conformance-tests/` 配下 (**`CONDITIONS.md` と条件テストは WP-5 / WP-6c**)、`security/` 配下、`tools/`、`COLLECTION_FLOOR`、**相手 peer の一切**、`r2db-api/conformance/conformance_adapter_r2db_http.py` (**r2db HTTP plug は宣言表を読まない**。`:1030-1033`)。

**実装の指示 (要点)**:

1. **形は `surfaces` を写す**: `{"data": <int >= 1>, "control": <int >= 1>}`。**新しい形を発明しない** (設計 U-5)。
2. **表の `key` は `CHECK` で閉じた集合なので platform 単発 migration を要する** (`r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql:136-139`、`MitateDB-api/migrations/0007_platform_declarations.sql:103-106`)。**番号は r2db `0012` / MitateDB `0011`。値側の CHECK は置かない** (検証は Python 側に一本化)。
3. **`verify-declarations` に足す番号は F-15、exit code は次の未使用値 14 である** (現行最大は `"F-14": 13`。`r2db-api/src/r2db_api/ops.py:1333-1352`)。**`_VERIFY_DECLARATIONS_EXIT_CODES` は両 peer で逐語同一の `_ISOMORPHIC_TARGETS` 登録対象なので、両 peer に同じ行を足す** (同 `:1314-1328`)。
4. **写像は設計 D-5 (ii) の 3 区分の表そのものである。** **区分 (iii) の各 class・各 peer で lock の有無を確認し、無ければ足す** — **写像を弱める側には倒さない。前例はフェーズ9 R-2 の `LOCK TABLE ... IN SHARE MODE` である。** **現行の read-then-write の位置は `r2db-api/src/r2db_api/control_plane.py:847` / `:944`、`MitateDB-api/src/mitatedb_api/control_plane.py:1513` / `:1600`、`idempotency_entries` は `r2db-api/src/r2db_api/postgres.py:1213-1221` である。**
5. **宣言表を通る全経路で、宣言を先に書く** (設計 D-5 (ii) 末尾): **MitateDB HTTP plug の fixture seed** (`conformance_adapter_mitatedb_http.py:334-347` の隣。migration 一覧 `:292-305` に `0011`)、**その継承先である MitateDB socket plug** (継承で足りる)、**両 peer の provision script / runbook**。
6. **配備側**: **r2db は `{"data": 1, "control": 1}` を宣言し、`part1c_declare_surfaces.sh` と同系統の step を配備手順に足す。** **MitateDB は runbook の Invariant 1 を「`--max-instances` は宣言した ceiling と一致させる (data / control 両方)」に一般化する** (`MitateDB-api/docs/cloud-run-cloud-sql.md:1117-1130`、`:549-552`)。
7. **upgrade 順序を明文化する**: **migration → `ops declare-process-ceilings` → 再起動** (起動時スナップショットのため)。**必須キーが 2 つになるので LQ4-24 のままでは script 製ホストは落ちる — runbook 項で LQ4-24 を参照する** (設計 D-5 (iii))。
8. **版フリップは pair-closing である** (§4)。**宣言と挙動は同一コミットに収める。**

**完了条件 ↔ 変異 (1 対 1。各 peer で同じ表を持つ)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | 宣言表に `process_ceilings` 行が無ければ **起動時 fail-fast** する (stderr に F-15 相当の文言) | `<peer>/src/.../main.py`: 起動時の必須キー検査から `process_ceilings` を外す → `<peer>/tests/test_process_ceilings_declaration.py::test_missing_row_fails_fast_at_startup` |
| 2 | 区分 (ii) の 4 class が **ceiling 1 → `enforced` / ceiling 2 → `deployment_required`** に写る | `<peer>/src/.../<写像関数>`: 写像を常に `enforced` に固定する → `::test_ceiling_two_maps_in_memory_classes_to_deployment_required` |
| 3 | 区分 (i) の 9 class は **ceiling に依らず不変**である | 同上: 区分 (i) を写像対象に含める → `::test_request_scoped_classes_are_unaffected_by_ceiling` |
| 4 | 区分 (iii) の 3 class は **ceiling に依らず `enforced`** であり、それを支える lock が在る | `<peer>/src/.../control_plane.py`: `applications` / `credentials_per_application` の check-then-write から lock を外す → `::test_db_side_bounds_hold_under_concurrent_writers` |
| 5 | `idempotency_entries` の count → store が同一 tx 内の lock 付きである | `<peer>/src/.../postgres.py` (MitateDB は同等物): lock を外して別トランザクションの count に戻す → `::test_idempotency_entries_bound_holds_under_concurrency` |
| 6 | `ops declare-process-ceilings` が表に書き、**表が唯一の出所**である (env fallback を持たない) | `<peer>/src/.../platform_declarations.py`: env fallback を足す → `::test_declaration_table_is_the_only_source` |
| 7 | `ops verify-declarations` が **F-15 / exit code 14** を返す | `<peer>/src/.../ops.py`: F-15 の exit code を既存値に重ねる → `::test_verify_declarations_f15_exit_code` と、両 peer 逐語同一の `_VERIFY_DECLARATIONS_EXIT_CODES` 同型性テスト |
| 8 | migration が **platform 単発**である (MitateDB `0011` は `_upgrade.sql` で終わらない) | `MitateDB-api/migrations/0011_process_ceilings.sql`: ファイル名を `*_upgrade.sql` にする → Q4 D-3 (d) の静的走査テスト (per-application upgrade 一覧の命名分類) |
| 9 | **(6b のみ)** MitateDB HTTP plug の fixture seed に `process_ceilings` があり、migration 一覧に `0011` が在る | `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`: seed 行を削除 → **同 plug が構築時 fail-fast で落ち、同 plug の全条件が赤** |
| 10 | `contract_version` が **4 箇所すべてで 1.8.0** である | `<peer>/src/.../<宣言箇所>`: 1 箇所だけ 1.7.0 に戻す → `conformance-tests/test_c19_client_self_sufficiency.py` の data 面 / control 面一致 assert と契約版 assert |
| 11 | 配備手順に **migration → declare → 再起動**の順序と **LQ4-24 への参照**が在る | **監査照合** — 該当 runbook の逐語記録 (設計 §11) |
| 12 | **(6b のみ)** runbook の Invariant 1 が data / control 両方について一般化されている | **監査照合** — `MitateDB-api/docs/cloud-run-cloud-sql.md` の該当行 |
| 13 | 宣言と挙動が同一コミットであり、宣言だけが先行していない | **監査照合** — `git show --stat` の突合 (監督) |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q <peer>/tests/test_process_ceilings_declaration.py  → 全 passed
./.venv/bin/python -m pytest -q <peer>/tests                                        → 全 passed
./.venv/bin/python -m pytest -q conformance-tests/test_c05_limit_declaration_agreement.py \
    conformance-tests/test_c12_capability_agreement.py                              → 全 passed
./.venv/bin/python -m pytest -q conformance-tests                                    → 全 passed (skipped 0 / xfailed 0)
./.venv/bin/python tools/public_value_scan.py <触った全ファイル>                     → total_flagged=0
```

**使用テンプレート**: **2** → **5** → **6**。
**変更クラス**: **C**。**`_ISOMORPHIC_TARGETS` 集合の増減を伴う pair-closing commit は D** (§4)。

---

### WP-6c — 新条件 C-26「配備 composition の証拠」

**目的**: **文書化された composition root を、文書化された env だけで実起動する launcher** を両 peer に置き、`registry.json` の新節 `composition_roots` に登録し、共通テストが launcher ごとに設計 D-1 (B) の 1〜6 を観測する。**LQ4-11 を閉じるのは本 WP である。**

**読むべき正本**: 設計 §3 **D-1 (B) の 1〜9** (観測項目・xdist group・非 vacuity)、**D-2** (subprocess 版の起動関数)、**D-4 の 2** (本番経路)、**D-5 (iv)** (C-26 (4) の射程)、§6.1 の `composition_roots` 節、§6.2 の C-26 行、§7 の SI-08 / SI-14 行、§8 の WP-6c 行、§9 の 3 / 8 (d)(e)、§10.0 の LQ4-11 行、§10.2 の **L10-1** / **L10-2**。**Q4 設計 §12 の LQ4-11 / LQ4-15。**

**触るファイル**: `r2db-api/conformance/real_server_r2db.py` (**新設**)、`MitateDB-api/conformance/real_server_mitatedb.py` (**新設**)、`conformance-tests/test_c26_composition_root.py` (**新設**)、`conformance-tests/registry.json` (**`composition_roots` 節**)、`conformance-tests/CONDITIONS.md` (**C-26 行の追加**)、`conformance-tests/socket_harness.py` (**subprocess 起動関数の利用。足りなければ最小限の追補**)、`conformance-tests/conftest.py` (**C-26 の item を launcher ごとの `xdist_group` に置く**)。

**触らないファイル**: 両 peer の `src/` / `migrations/` (**WP-6a / 6b の成果物をそのまま起動する。launcher のために製品コードを曲げない**)、`spec/` 配下、`security/` 配下、既存 6 plug の adapter、`CONDITIONS_HISTORY.md` の既存行、`COLLECTION_FLOOR`、`tools/deploy_smoke.py` (**実行するだけ**)。

**実装の指示 (要点)**:

1. **launcher は文書化された composition root (`<peer>.main:app` / `<peer>.control_main:app`) を、文書化された env だけで起動する。** **adapter 側の composition を起動しない** (設計 D-1 (B) 「壊すとどう見えるか」)。
2. **順序は「free port 予約 → `ops declare-surfaces` と `ops declare-process-ceilings` を実 CLI で書く → uvicorn を subprocess で起動 → nginx → readiness」** — **`cmd_declare_surfaces` 自身が「新しい値を効かせるには両プロセスを再起動せよ (起動時スナップショット)」と出力する** (`r2db-api/src/r2db_api/ops.py:1231`)。
3. **観測項目は設計 D-1 (B) の 1〜6 である。** **(4) は `process_ceilings` を 1 で宣言した起動と 2 で宣言した起動 (再起動 1 回) で `limit_enforcement` の写像を観測する。** **実プロセス数そのものは観測しない** — **launcher が起動するのは 1 プロセスであり、`process_ceilings: 2` はその起動については偽の宣言である。topology と宣言の一致は runbook 規律 + 配備後チェックが担う** (L10-2)。
4. **xdist group を launcher ごとに分ける** (例 `c26-<peer>`)。**`conformance-tests/conftest.py:95-97` は `adapter` param を持たない item をすべて `registry-guards` group に入れるので、そのままでは registry 横断 guard 群と同居して 1 worker に直列化される。** **7 の registry-guard は対象外である** (adapter を起動しない)。
5. **peer 側の launcher に生じる同名 helper は同型性テストに載せる** — **`_ISOMORPHIC_TARGETS` への行追加は監督の pair-closing commit (Class D) である** (設計 §8、U-4)。

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | launcher が **文書化された env だけ**で composition root を起動し、順序が「declare → uvicorn → nginx → readiness」である | `<peer>/conformance/real_server_<peer>.py`: declare を uvicorn 起動の後に移す → `conformance-tests/test_c26_composition_root.py::test_c26_declared_surfaces_are_served` (起動時スナップショットにより古い値が serve される) |
| 2 | **宣言表由来の `surfaces.data` / `surfaces.control` に実 TCP で GET すると同じ文書が返る** (両面) | `real_server_<peer>.py`: `declare-surfaces` を打たない → composition root が起動しない → `::test_c26_declared_surfaces_are_served` |
| 3 | `tools/deploy_smoke.py` を subprocess で実行して緑である | `real_server_<peer>.py`: launcher が adapter 側 composition を起動する形に変える → `::test_c26_deploy_smoke_is_green` |
| 4 | **ceiling 1 と ceiling 2 の 2 通りの実起動で、宣言値 → `limit_enforcement` の写像が成立する** | `<peer>/src/.../<写像関数>`: 写像を常に `enforced` に固定する → `::test_c26_ceiling_maps_to_limit_enforcement` |
| 5 | 宣言表の `process_ceilings` 行が無ければ起動が **fail-fast** し、stderr に F-15 相当の文言が出る | `real_server_<peer>.py`: 行が無い場合の期待を「起動する」に変える / `<peer>/src` 側の fail-fast を外す → `::test_c26_missing_declaration_fails_fast` |
| 6 | 終了時のプロセス・port 残骸が 0 である | `conformance-tests/socket_harness.py`: subprocess 版の SIGTERM → SIGKILL 段を外す → `::test_c26_no_residue_after_shutdown` |
| 7 | **非 vacuity**: `composition_roots` が **2 件以上**である (registry-guards で assert) | `conformance-tests/registry.json`: `composition_roots` を 1 件にする → `::test_c26_composition_roots_registry_has_at_least_two` |
| 8 | C-26 の item が **launcher ごとの `xdist_group`** に置かれ、`registry-guards` group に入らない | `conformance-tests/conftest.py`: C-26 の group 割当を削除する → `conformance-tests/test_c26_composition_root.py::test_c26_items_are_grouped_per_launcher` |
| 9 | `CONDITIONS.md` に C-26 の行が在り、SI-08 / SI-14 に紐づき、Status セルが 3000 字以内である | `conformance-tests/CONDITIONS.md`: C-26 行を落とす → `conformance-tests/test_conditions_register.py` (条件 ID と test ファイルの突合) |
| 10 | 本書と設計の `C-26` 参照が dangling でなくなる | **監査照合** — `./.venv/bin/python tools/check_doc_refs.py` が `0 dangling references` |
| 11 | `conformance` job の所要が `timeout-minutes: 30` 内に収まる | **監査照合** — CI run の所要時間を設計 §11 と L10-1 に記録。**収まらなければ本フェーズ内で並列度か plug 起動の共有を再設計する。先送りしない** |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q conformance-tests/test_c26_composition_root.py   → 全 passed
./.venv/bin/python -m pytest -q -n 5 --dist loadgroup conformance-tests           → 全 passed (skipped 0 / xfailed 0)
./.venv/bin/python -m pytest -q --collect-only conformance-tests/test_c26_composition_root.py
  → collected <N> items (launcher 2 本ぶん)
./.venv/bin/python tools/check_doc_refs.py                                        → check_doc_refs OK: 0 dangling references
./.venv/bin/python tools/public_value_scan.py <新設ファイル>                      → total_flagged=0
```

**使用テンプレート**: **2** → **5** → **6**。
**変更クラス**: **C**。**launcher の同名 helper を同型性表に載せる pair-closing commit は D。**

---

### WP-6d-i / WP-6d-ii — 同一 idempotency key の同時送信の直列化 (**新設 v1.1**)

**目的**: 同一 idempotency key の同時要求を、**効果と同じトランザクション・同じ接続**で直列化し (**6d-i**)、それを**新条件 C-27** と adapter hook で共通 suite から決定的に駆動する (**6d-ii**)。**フェーズ9 が示したのは逐次経路の再送安全性であり、本 WP が示すのは同時送信の再送安全性である** (計画文書 §1.0d、§8 の **R-24**)。

**読むべき正本**: 設計 §3 **D-13** (決定・根拠・実装の形 (6d-i) の 1〜6・実装の形 (6d-ii)・壊すとどう見えるか)、**D-5 (ii) の区分 (iii) と v1.3 の追記 (1) (2)**、§5 **U-7** / **U-8** / **U-9**、§6.2 の **C-27** 行、§8 の WP-6d 行、§8.1。計画文書 §8 の **R-24**。契約 `spec/data-service-api.v1.json` の `idempotency.record`。`conformance-tests/CONDITIONS.md` の **C-23** 行と **C-27** 行。**port の `hold_in_flight` (C-05、port v1.12) の実装と使われ方。**

---

#### WP-6d-i — 両 peer の lock (**WP-3 に依存しない。今すぐ着手できる**)

**状態 (v1.2)**: **実装済み (2026-09-08)。worktree / branch `phase10-wp6d`、実装 `21cc8fb`。** **Opus のコードレビュー 1 巡目の判定は「accept with fixes」であり、指摘 F1〜F8 の是正コミットは `6a3453d`、R-34 の branch `phase10-r34` との統合は `685ebfa` である (再レビュー実施中)。** **main へのマージは `<hash>` であり、次のゲート束で監督が行う。** **発注時の想定と実現の形が peer で分かれた** — **MitateDB は catalog 読みが同じ接続の途中で自己 commit するので transaction-scoped lock が早期に解放され、SESSION advisory lock + 明示解放になった** (下記「実施の記録」、設計 §3 D-13 の実施註)。

**触るファイル**: `r2db-api/src/r2db_api/postgres.py` (**`_idempotency_lookup` の直前に key lock**)、`r2db-api/src/r2db_api/structured.py` (**in-memory cell の `threading.Lock`**)、`MitateDB-api/src/mitatedb_api/backend_postgres.py` (**照会を書く側の接続の同一トランザクションへ移し、その前に lock**)、`MitateDB-api/src/mitatedb_api/cell.py` (**in-memory 経路の `threading.Lock`**)、両 peer の `tests/test_idempotency_concurrency.py` (**新設**)。

**触らないファイル**: `conformance-tests/` 配下 (**C-27 と hook は 6d-ii**)、`spec/` 配下と 3 複製の契約 JSON (**U-9 の追補は監督が WP-5a の branch で行う**)、`security/` 配下、`tools/`、`.github/workflows/ci.yml`、`COLLECTION_FLOOR`、両 peer の `migrations/` (**新しい表も列も要らない**)、`r2db-api/conformance/` と `MitateDB-api/conformance/`、**`process_ceilings` の宣言機構一式** (**WP-6a / 6b の担当**)。

**実装の指示 (要点)**:

1. **順序は「lock → 照会 → (replay / `CONFLICT` / 続行) → 実行 → 記録 → commit」** である (設計 D-13)。**lock は key 単位の transaction-scoped advisory lock (`pg_advisory_xact_lock(hashtext(<key>))`)** であり、**key は Application ごとの DB に閉じるので Application 内一意で足りる。**
2. **r2db**: `transact` / `apply_schema` の**既存トランザクション内**、**`_idempotency_lookup` (`r2db-api/src/r2db_api/postgres.py:1188`) の直前**に取る。**新しいトランザクションを開かない。**
3. **MitateDB (制約)**: **lock と照会を、書く側の接続の同一トランザクションで行う** (`transact` は `_runtime`、DDL 経路は `_developer`)。**接続が 2 本ある構造そのものは変えない** — 変えるのは「照会がどの接続のどのトランザクションで走るか」だけである。**照会を自己 commit の別トランザクションのまま残さない** (残すと後着が先着の commit を待たずに読む)。
4. **in-memory cell** (r2db の `InMemoryCell`、MitateDB の `ApplicationCell` の dict): **key 単位または cell 単位の `threading.Lock` で「照会 → 実行 → 記録」を囲む。**
5. **`ON CONFLICT DO UPDATE` の上書きは残す** — **期限切れの未回収行のためだけである** (設計 D-13 の 1)。
6. **異キーの `idempotency_entries` 件数 bound には表単位の定数 key の `pg_advisory_xact_lock` を件数検査の前に取る** (`r2db-api/src/r2db_api/ops.py:149` の `_RITUAL_ADVISORY_LOCK_KEY` と同系)。**`LOCK TABLE ... IN SHARE MODE` は採らない** — **SHARE 同士は衝突しないので両者が INSERT で待ち合って deadlock する。** **実装担当はフェーズ9 R-2 の前例 (`r2db-api/src/r2db_api/postgres.py:2292`、`:2373` の `alter_field` / `add_field`) の lock mode を現物で確認し、同じ誤りが無いことを報告する。** **この項は WP-6a / 6b と同じ関数に入るので、取り込み順は 6d-i → 6a / 6b である** (設計 §8.1)。
7. **性能**: **Application ごとの keyed write が表 lock で直列化される。** **回避しない** — **完了ゲートの性能差分 (`OPERATING_CONDITIONS.md` §1.3 の 27) で計測して記録する。**

**完了条件 ↔ 変異 (1 対 1。各 peer で同じ表を持つ)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | 同一キー・**同一 digest** の 2 要求を実 PG で同時に走らせると **実行は 1 回**であり (効果行 1、実行の監査 event 1)、後着は**先着と同じ `request_id`** を返す | `<peer>/src/.../<照会の直前>`: key の advisory lock を外す → `<peer>/tests/test_idempotency_concurrency.py::test_same_key_same_digest_executes_once` |
| 2 | 同一キー・**異 digest** の 2 要求では **実行 1 回**、後着は `CONFLICT` + `violated_declaration: idempotency_key` | 同上 → `::test_same_key_different_digest_conflicts` |
| 3 | **先着が失敗 (rollback) したときは、後着が新規要求として実行される** (記録が残らない) | `<peer>/src/...`: 失敗時にも記録を残す形にする → `::test_failed_first_attempt_leaves_no_record_under_concurrency` |
| 4 | **照会が「書く側の接続の同一トランザクション」で走る** (MitateDB: 自己 commit の別トランザクションではない。**接続 2 本の構造は変わっていない**) | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: 照会を自己 commit の別トランザクションに戻す → `::test_lookup_runs_on_the_writing_connection` と完了条件 1 の同時テスト |
| 5 | **in-memory 経路**でも 2 スレッド同時で実行が 1 回である | `<peer>/src/...`: `threading.Lock` を外す → `::test_in_memory_same_key_executes_once` |
| 6 | 異キー 2 件を `idempotency_entries` 上限 −1 の状態で同時に走らせると、**件数 bound が保たれ 1 件が `LIMIT_EXCEEDED`** になる | `<peer>/src/...`: 表単位の advisory lock を外す → `::test_entries_bound_holds_under_concurrent_distinct_keys` |
| 7 | **deadlock 検査** — 完了条件 1 / 2 / 6 の同時テストを繰り返し実行しても deadlock も lock 待ちタイムアウトも発生しない (**`LOCK TABLE ... IN SHARE MODE` を採らない根拠の実測**) | `<peer>/src/...`: 表単位 lock を `LOCK TABLE ... IN SHARE MODE` に置き換える → 完了条件 6 のテストが deadlock (または待ち) で赤になることを実測し **verbatim を報告に添える** (**変異は復元し、コミットに含めない**) |
| 8 | フェーズ9 R-2 の前例 (`alter_field` / `add_field` の `LOCK TABLE ... IN SHARE MODE`) の lock mode を現物で確認し、**同じ誤りが無い**ことを報告した | **監査照合** — 確認した file:line と判断を報告に書く |
| 9 | 既存の C-23 / C-07 (ii) と両 peer の `tests/test_idempotency_records.py` が緑のまま (**逐次経路の意味は変わらない**) | **監査照合** — 集計行の 4 数 |
| 10 | **性能差分**: 本 WP の前後で `tools/perf_baseline.py` の `mutate` / `batch` の p50 / p95 を測り、**差分を報告に添える** (**閾値は無い。回避もしない**) | **監査照合** — `PERFRUN` + `PERF` 行の verbatim (完了ゲートでの記録は WP-9) |
| **11** (**v1.2 の追記。レビュー指摘 F3 の是正で足した**) | **lock を取った接続が `finally` で必ず解放される** (MitateDB。**pass 1 が失敗しても advisory lock が残らない**) | `MitateDB-api/src/mitatedb_api/cell.py`: `idempotency_unlock` の呼び出しを `finally` の外へ出す → `MitateDB-api/tests/test_idempotency_concurrency.py` の当該テスト (**実測の赤は `still holds 2 advisory lock(s)`**) |
| **12** (**v1.2 の追記。レビュー指摘 F1 の是正で足した**) | **期限切れ行の回収 (reap) が永続化する** (MitateDB。**`idempotency_begin` の commit が回収の DELETE を確定させる**) | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: `idempotency_begin` / `idempotency_reserve` の commit を外す → 回収の回帰テストが赤 |
| **13** (**v1.2 の追記。レビュー指摘 F2 の是正で足した**) | **lock 待ちが要求 deadline を超えたら `LIMIT_EXCEEDED` (`execution_ms`) になる** (MitateDB。**`lock_timeout` / `statement_timeout` を lock の前に要求 deadline から設定する**) | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: lock の前の `lock_timeout` 設定を外す → lock 待ちタイムアウトのテストが赤 |

**【実施の記録 2026-09-08 (v1.2)。branch `phase10-wp6d` の `21cc8fb` + `6a3453d`、統合 `685ebfa`】**

- **実現の形 (peer ごとの違いと、その理由)** は設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §3 **D-13 の実施註**が正本である。**本書は再掲しない** (§0.0 の 2)。要点だけ: **r2db は発注どおり `pg_advisory_xact_lock` (key 単位 / 表単位) を効果の外側トランザクションで取り、in-memory は per-cell の `threading.Lock`。MitateDB は SESSION advisory lock を書く側の接続で取り、`finally` で解放する。**
- **足したテスト** (両 peer `tests/test_idempotency_concurrency.py`。**実 PG と in-memory の双方**): **同一 digest → 実行 1 回 + 元の `request_id` での replay**、**異 digest → 実行 1 回 + `CONFLICT`**、**上限直下の異キー 2 件 → 1 件が `LIMIT_EXCEEDED`**、**先着が失敗 → 後着は新規要求として実行**。**MitateDB は加えて回収の永続化・lock 待ちタイムアウト・pass 1 失敗時の unlock (完了条件 11〜13)。**
- **変異の実測**: **key lock 除去 → 両 peer `2 failed`**、**件数 lock 除去 → 両 peer `1 failed`**、**in-memory lock 除去 → 両 peer `3 failed`**、**unlock を `finally` の外 → `still holds 2 advisory lock(s)`**、**MitateDB の 2 つの commit 除去 → 回収の回帰が赤**。**監督の raw-SQL 競合スクリプトを新しい SQL で再実行し 25 反復で二重実行 0 件。**
- **peer suite (是正前)**: **r2db `1175 passed`、MitateDB `998 passed`。**
- **完了条件 8 (フェーズ9 R-2 の前例の lock mode 確認) の報告**: **同じ誤りが在った。** **`LOCK TABLE ... IN SHARE MODE` の後に同一トランザクションで `ALTER TABLE` を打つので、キー無しの同時スキーマ変更 2 件が相互に待つ。** **起票は計画文書 §8 の R-35、設計 §3 D-15、発注は本書の WP-R35 である。**

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q <peer>/tests/test_idempotency_concurrency.py   → 全 passed
./.venv/bin/python -m pytest -q <peer>/tests                                    → 全 passed
./.venv/bin/python -m pytest -q conformance-tests/test_c23_idempotency_semantics.py \
    conformance-tests/test_c07_atomicity_and_retry.py                           → 全 passed
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10
  → PERFRUN 1 行 + PERF 表 (本 WP の前後で 2 回。差分を報告に添える)
./.venv/bin/python tools/public_value_scan.py <触った全ファイル>                 → total_flagged=0
```

**使用テンプレート**: **2** → **5** → **6**。
**変更クラス**: **C** — **共通契約の意味 (`idempotency.record`) を実効化する変更であり、同名 helper が生じ得る。** **`_ISOMORPHIC_TARGETS` への行追加は監督の pair-closing commit (Class D) である。**

---

#### WP-6d-ii — 新条件 C-27 と adapter hook (**WP-3 の hook 抽出と WP-6a / 6b の版フリップの後。WP-4 と並行可**)

**触るファイル**: `conformance-tests/test_c27_concurrent_same_key.py` (**新設**)、`conformance-tests/adapter.py` (**hook の抽象メソッド 1 つ**)、既存 4 adapter (`r2db-api/conformance/conformance_adapter_r2db.py` / `_r2db_http.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py` / `_mitatedb_http.py`。**hook の実装**)、`conformance-tests/CONDITIONS.md` (**C-27 行を `executable` に改める。旧文は `CONDITIONS_HISTORY.md` の `## C-27` へ逐語で移す**)、`docs/design/CONFORMANCE_ADAPTER_V1.md` (**port の版数を 1 つ上げ、hook の節を新設する**)。

**触らないファイル**: 両 peer の `src/` / `migrations/` (**6d-i の成果物をそのまま駆動する**)、`spec/` 配下、`security/` 配下、`conformance-tests/registry.json`、**socket adapter 2 本** (**hook は継承する。WP-4 の成果物に触らない**)、`CONDITIONS.md` の **C-27 以外の行** (**WP-5 / WP-6c の担当**)、`COLLECTION_FLOOR`、`tools/`。

**実装の指示 (要点)**:

1. **hook の名と形は `hold_in_flight` (C-05、port v1.12) に倣う** — **先着を「照会の直後・実行の前」で保持し、後着を送り、先着を解放する。** **待ち上限を持ち、超えたら fail する (skip しない)。**
2. **観測項目は 3 つである** (設計 D-13 の「実装の形 (6d-ii)」): **(i)** 同一 digest — **実行 1 回** (効果行 1、実行の監査 event 1)、後着は先着と同じ `request_id` の replay。**(ii)** 異 digest — 実行 1 回、後着は `CONFLICT` + `violated_declaration: idempotency_key`。**(iii)** 異キー 2 件を `idempotency_entries` 上限 −1 の状態で同時送信 — 1 件が `LIMIT_EXCEEDED` + `limit_class`。
3. **4 plug すべてで駆動する** — **http adapter の app は同一プロセスの uvicorn なので monkeypatch が届く** (C-05 の実例)。**socket adapter (WP-4) は継承する。**
4. **`CONDITIONS.md` の C-27 行は既に在る** (宣言のみ)。**本 WP はそれを `executable` に改め、旧文を `CONDITIONS_HISTORY.md` の `## C-27` へ逐語で移す** (更新規約。**セル長は `MAX_CELL_LENGTH = 3000` 以内**)。
5. **C-23 の条件文を書き換えない** — **C-23 は逐次経路の意味、C-27 は同時送信の直列化である** (設計 §6.2 の追記)。

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | (i) 同一 digest で **実行 1 回**・後着は同じ `request_id` の replay | `<peer>/src/.../<照会の直前>`: key の advisory lock を外す (6d-i の成果物) → `conformance-tests/test_c27_concurrent_same_key.py::test_c27_same_digest_executes_once` |
| 2 | (ii) 異 digest で **実行 1 回**・後着は `CONFLICT` + `violated_declaration: idempotency_key` | 同上 → `::test_c27_different_digest_conflicts` |
| 3 | (iii) 異キー 2 件で件数 bound が保たれ 1 件が `LIMIT_EXCEEDED` + `limit_class` | `<peer>/src/...`: 表単位の advisory lock を外す → `::test_c27_entries_bound_holds_under_concurrency` |
| 4 | hook が **照会の直後・実行の前**で保持する (保持点がずれていない) | `<peer>/conformance/...`: 保持点を実行の後に移す → `::test_c27_same_digest_executes_once` (**先着が実行を終えてしまい後着が replay ではなく 2 回目の実行になる**) |
| 5 | **非 vacuity**: 各 plug の run 内で 3 観測が**実際に駆動した**ことを、その plug 自身の `idempotency` 宣言が含意する枝と突き合わせて assert する | `conformance-tests/test_c27_concurrent_same_key.py`: 駆動観測の assert を落とす → 同ファイルの個別 guard |
| 6 | **4 plug すべてで駆動する** (skip 0 / xfail 0) | `conformance-tests/test_c27_concurrent_same_key.py`: 特定 plug を除外する分岐を入れる → 駆動 plug 数の guard |
| 7 | hook の待ち上限を超えたら **fail する (skip しない)** | `conformance-tests/adapter.py` または hook 実装: 上限超過を skip にする → `::test_c27_hold_timeout_fails_loudly` |
| 8 | `CONDITIONS.md` の C-27 行が `executable` に改まり、**旧文が `CONDITIONS_HISTORY.md` の `## C-27` に逐語で在る**。**Status セルは 3000 字以内** | `conformance-tests/CONDITIONS.md`: 移送せずに追記する → `conformance-tests/test_conditions_register.py` (`MAX_CELL_LENGTH` と履歴突合) |
| 9 | **C-23 の条件文と駆動集合が変わっていない** | **監査照合** — 差分の目視 (C-23 行に触れていないこと) |
| 10 | `CONFORMANCE_ADAPTER_V1.md` の版数が 1 つ上がり hook の節が在る | **監査照合** — 同文書 `:5-11` の文書情報行 |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q conformance-tests/test_c27_concurrent_same_key.py   → 全 passed (4 plug)
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py        → 全 passed
./.venv/bin/python -m pytest -q -n 5 --dist loadgroup conformance-tests              → 全 passed (skipped 0 / xfailed 0)
./.venv/bin/python tools/check_doc_refs.py                                           → check_doc_refs OK: 0 dangling references
./.venv/bin/python tools/public_value_scan.py <新設・変更した全ファイル>              → total_flagged=0
```

**使用テンプレート**: **2** → **5** → **6**。
**変更クラス**: **C** (`conformance-tests/` 配下 + 条件行)。**同名 helper の pair-closing commit は D。**

---

### WP-R35 — フェーズ9 R-2 の走査 lock mode の是正 (**新設 v1.2。骨子**)

**状態**: **実施中 (2026-09-08)。worktree / branch `phase10-r35`。コミットは `<hash>` である。** **出所は WP-6d-i のコードレビュー (本書 WP-6d-i の完了条件 8 の報告) であり、本フェーズの新規変更が作った欠陥ではない。**

**目的**: **両 peer の nullable 違反走査の `LOCK TABLE ... IN SHARE MODE` を `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE` に改め、キー無しの同時スキーマ変更 2 件が deadlock detector でしか解けない相互待ちに入らないようにする** (設計 §3 **D-15**、計画文書 §8 の **R-35**)。**R-2 の走査が依拠する性質 (行の書き手を排除する) は保つ。**

**読むべき正本**: 設計 §3 **D-15** (決定・根拠・D-13 との関係・壊すとどう見えるか)、§8 の WP-R35 行、§8.1 の WP-R35 × WP-6d-i 行。計画文書 §8 の **R-2** (フェーズ9 の完了内容) と **R-35**。本書 WP-6d-i の完了条件 8。

**触るファイル**: `r2db-api/src/r2db_api/postgres.py` (`add_field` / `alter_field` の走査 lock)、`MitateDB-api/src/mitatedb_api/backend_postgres.py` (同)、両 peer の `tests/` (**決定的な 2 スレッドテスト。置き場は §0.5 のとおり実装報告で確定する**)。
**触らないファイル**: `spec/` 配下と 3 複製の契約 JSON、`conformance-tests/` 配下、`security/` 配下、`tools/`、`.github/workflows/ci.yml`、`COLLECTION_FLOOR`、両 peer の `migrations/`、**idempotency の照会・記録の経路** (**WP-6d-i の担当**)、**`process_ceilings` の宣言機構一式** (**WP-6a / 6b の担当**)。

**実装の指示 (要点)**:

1. **lock mode を `SHARE ROW EXCLUSIVE` に改める** — **自己衝突するので後着は `LOCK TABLE` の時点で待ち、先着の commit の後に進む** (設計 D-15)。**走査そのものと `ALTER TABLE` の順序は変えない。**
2. **両 peer に同じ命題のテストを置く** — **同じ表に対するキー無しのスキーマ変更 2 件を 2 スレッドで走らせ、`deadlock detected` が起きず両方が順に完了することを決定的に示す** (**実時間の `sleep` に依存しない同期。R-34 の是正と同じ規律**)。
3. **`SHARE` に戻す変異で赤になることを実測し、verbatim を報告に添える** (`OPERATING_CONDITIONS.md` §1.4 の 28〜31。**変異は復元し、コミットに含めない**)。

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | **r2db**: 同一表へのキー無しスキーマ変更 2 件が同時でも deadlock せず順に完了する | `r2db-api/src/r2db_api/postgres.py`: mode を `SHARE` に戻す → 当該 2 スレッドテスト |
| 2 | **MitateDB**: 同じ命題が成立する | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: 同上 → 当該 2 スレッドテスト |
| 3 | **R-2 の走査の性質が保たれている** — nullable 違反行が在れば `CONFLICT` になる既存テストが緑のまま | **監査照合** — 両 peer の既存 `alter_field` / `add_field` テストの集計行 |
| 4 | **`SHARE` に戻す変異の赤を実測した** | **監査照合** — 変異時の出力の verbatim (`deadlock detected` または待ち) |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q <peer>/tests                 → 全 passed
./.venv/bin/python tools/public_value_scan.py <触った全ファイル> → total_flagged=0
```

**使用テンプレート**: **2** → **5**。
**変更クラス**: **B** (**両 peer の `src/` の内部統制の是正であり、宣言・契約・共通条件に触らない**)。

---
### WP-7 — R-20 の計測と判定 (同時要求下の tail latency)

**目的**: `tools/perf_baseline.py` に `--concurrency K` を足し、K = {1, 3} を **同じ gather 経路**で測り、**先に置いた判定規則**で WP-8 の実施可否を決める (設計 D-8 (1)(2))。

**読むべき正本**: 設計 §3 **D-8 の (1)(2)(3)** と根拠・却下、**D-12** (PERF 行と `_classify_plug`)、§2.1 の **P-8**、§5 **U-2**、§8 の WP-7 行、§8.1 の WP-3 × WP-7 行、§9 の 6、§10.2 の **L10-4**、§11 (記録先)。`tools/PERF_BASELINE_README.md` の出力形式節。

**触るファイル**: `tools/perf_baseline.py`、`tools/PERF_BASELINE_README.md`、`tools/tests/test_perf_baseline.py`。
**触らないファイル**: 両 peer の `src/` / `tests/` (**方式の変更は WP-8。実測前に直さない**)、`conformance-tests/` 配下、`spec/` 配下、`.github/workflows/ci.yml`、`COLLECTION_FLOOR`。

**実装の指示 (要点)**:

1. **`--concurrency K`**: **スレッドではなく adapter 自身の loop 上で K 本の coroutine を `asyncio.gather` で同時発行する。** **K = 1 も同じ gather 経路で測る** (経路の違う 2 点を比べない)。**スレッドを採らないのは、測りたいのが server 側の event loop 直列化であり、client 側の GIL を混ぜないためである。**
2. **測る K は {1, 3}、既定は `--n 100 --warmup 10`。** **`--n 200 --warmup 20` × K=3 では単一 credential で 660 要求となり `LIMIT_EXCEEDED` に入る** (既定 profile の `requests_per_minute` は credential あたり 600。`r2db-api/src/r2db_api/limits.py:18`)。**効いている bound は共有 surface の既定 `concurrency=32` (`:17`) であり隔離 profile の値ではない。**
3. **既存の逐次計測と PERF 行形式は変えない (列を足す)。**
4. **判定規則を先に置く**: **K=3 の p50 が K=1 の p50 の 2 倍を超える → WP-8 を本フェーズで実施する。超えなければ記録のみで閉じる。** **規則は計測の前に確定している (設計 U-2)。数値を見てから基準を作らない。**

**PERF 行の期待形**:

```
PERFRUN host=<OS/arch> python=<version> commit=<short sha> date=<YYYY-MM-DD>
PERF peer=<peer> plug=<plug> transport=<transport_kind の宣言と 1 対 1 のラベル> op=<query|mutate|batch|cross_entity> n=<N> p50_ms=<x.xxx> p95_ms=<x.xxx> backend_calls=<n.nn> concurrency=<K>
```

**行数**: **6 plug × 3 op + `cross_entity` を宣言する 3 plug × 1 op = 21 行** (`tools/PERF_BASELINE_README.md` の規則による。**`r2db-api` 系 3 plug は `cross_entity_mutation: unavailable` なので `cross_entity` 行を持たない**)。**K を 2 通り測ればその 2 倍である。**

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | `--concurrency K` が **`asyncio.gather` で K 本を同時発行**する (順に `await` しない) | `tools/perf_baseline.py`: `gather` を逐次 `await` に置き換える → `tools/tests/test_perf_baseline.py::test_concurrency_issues_requests_simultaneously` |
| 2 | **K = 1 も同じ gather 経路**を通る (経路の違う 2 点を比べない) | `tools/perf_baseline.py`: K == 1 を旧逐次経路に分岐する → `::test_k1_uses_the_same_path_as_kn` |
| 3 | 既定が `--n 100 --warmup 10` である (`LIMIT_EXCEEDED` に入らない) | `tools/perf_baseline.py`: 既定を 200 / 20 に戻す → `::test_default_n_stays_under_the_rate_bound` |
| 4 | PERF 行の既存列が 1 つも変わらず、`concurrency` 列が末尾に足されている | `tools/perf_baseline.py`: `_format_row` の既存列名を変える → `::test_perf_row_format_is_stable` |
| 5 | `transport` ラベルが `transport_kind` の宣言と 1 対 1 であり、名前と宣言が食い違う plug は `UnknownAdapterShape` で非 0 終了する | `tools/perf_baseline.py`: `_classify_plug` の fallback を広げる → `::test_classify_plug_reads_the_declaration` (WP-3 で置いたもの) |
| 6 | 判定規則 (**K=3 p50 > 2 × K=1 p50**) が **script かドキュメントに先に書かれている**こと | **監査照合** — `tools/PERF_BASELINE_README.md` の該当節と、計測前のコミット順 (`git log`) |
| 7 | K = {1, 3} の実測が 6 plug すべてについて設計 §11 に記録され、判定結果 (実施 / 記録のみ) が書かれていること | **監査照合** — `PERFRUN` + `PERF` 行の verbatim |
| 8 | **非 vacuity**: app 側に人工的な待ちを入れると、K=3 の総所要が K=1 の 3 倍ではなく **1 倍に近づく** | **監査照合** — 一時変異での 2 値の実測を報告に添える (**変異は復元し、コミットに含めない**) |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q tools/tests/test_perf_baseline.py   → 全 passed
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 1
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 3
  → 各回 PERFRUN 1 行 + PERF 21 行
```

**判定の報告**: **K=3 の p50 と K=1 の p50 を plug × op ごとに並べ、`K=3 p50 / K=1 p50` の比を添える。2 倍を超える行が 1 つでもあれば WP-8 を実施する** (設計 D-8 (2))。**判定は監督が行う。**

**使用テンプレート**: **2** → **5** → **6**。**変更クラス**: **B**。

---

### WP-8a / WP-8b — threadpool 委譲 (**条件付き。WP-7 の判定が「超える」ときのみ**)

**目的**: 両 peer の handler で「body 読み (async) の後の同期部分」を `starlette.concurrency.run_in_threadpool` に委譲する (同型)。**前提の監査を実装前に行い、lock / thread-safety が無ければ足す** (設計 D-8 (3))。

**実施条件**: **WP-7 の判定が「K=3 の p50 が K=1 の p50 の 2 倍を超える」であること。** **超えなければ本 WP は実施せず、「判定規則に従って記録のみで閉じた」ことを設計 §11 に記録する** (**その記録自体が R-20 の閉止条件である**。設計 §10.0 の R-20 行)。

**読むべき正本**: 設計 §3 **D-8 の (3)** と却下 (**uvicorn `--workers N` / async psycopg**)、§5 **U-2**、§8 の WP-8 行、§8.1、§10.2 の **L10-4**、§11 (再計測の記録先)。

**【追記 2026-09-08 (v1.1)。前提条件。設計 D-8 (3) の追記、§5 U-10】** **threadpool 委譲は「1 要求 1 接続 (または pool からの貸出) であり、cell が接続を跨いで共有しない」ことを先に満たす。** **MitateDB は cell ごとに `_runtime` / `_developer` の接続を 1 本ずつ保持して共有しており、そのままでは threadpool 化できない。** **WP-7 の判定が「超える」であっても、この前提を満たす変更を本 WP に含めるかフェーズ11 (計画文書 §8 の R-31) へ送るかは、WP-7 の結果を見て監督が裁定する。** **実装担当は「実装前の監査」(下記) にこの前提の充足状況を含めて報告し、裁定を得てから実装に入る。**

**触るファイル**: **WP-8a** = `r2db-api/src/r2db_api/http.py` / `control_http.py` (+ 必要なら `postgres.py` / `service.py`)、`r2db-api/tests/test_threadpool_offload.py` (**新設**)。**WP-8b** = `MitateDB-api/src/mitatedb_api/http.py` / `control_http.py` (+ 必要なら `pool.py` / `cell.py`)、`MitateDB-api/tests/test_threadpool_offload.py` (**新設**)。
**触らないファイル**: `conformance-tests/` 配下、`spec/` 配下、`security/` 配下、`tools/` (**再計測は WP-7 の script をそのまま使う**)、`COLLECTION_FLOOR`、**相手 peer の一切**。

**実装前の監査 (実装より先に報告する)**: **`_LimitStateHolder` (`MitateDB-api/src/mitatedb_api/cell.py:744-780`) と r2db の同等物 (`service.py` の `_acquire_rate` / `_slot`) の lock、connection pool (`r2db-api/src/r2db_api/postgres.py:333` / `:586`、`MitateDB-api/src/mitatedb_api/pool.py:51`) の thread-safety を確認し、無ければ足す** (設計 D-8 (3))。**監査結果を報告し、監督裁定を得てから実装に入る。**

**完了条件 ↔ 変異 (1 対 1)**:

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 1 | handler の同期部分が **event loop の thread ではない thread** で走る | `<peer>/src/.../http.py`: `run_in_threadpool` 委譲を外す → `<peer>/tests/test_threadpool_offload.py::test_sync_section_runs_off_the_event_loop` |
| 2 | control 面の handler も同じ形で委譲する (両面同型) | `<peer>/src/.../control_http.py`: 委譲を外す → `::test_control_sync_section_runs_off_the_event_loop` |
| 3 | body 読みは **async のまま**であり、委譲は body 読みの後から始まる | `<peer>/src/.../http.py`: body 読みを threadpool 側に移す → `::test_body_read_stays_on_the_loop` |
| 4 | rate / concurrency の in-memory 状態が **複数 thread からの同時取得で壊れない** (lock がある) | `<peer>/src/.../<limiter>`: lock を外す → `::test_limiter_state_is_thread_safe` |
| 5 | connection pool が複数 thread からの同時取得で壊れない | `<peer>/src/.../<pool>`: lock を外す → `::test_pool_acquire_is_thread_safe` |
| 6 | 委譲後も既存の peer-local suite と共通 suite が緑である (**挙動不変**) | **監査照合** — 集計行の 4 数 |
| 7 | 再計測の差分 (K=1 / K=3 の p50・p95) が設計 §11 に記録されている | **監査照合** — `PERFRUN` + `PERF` 行の verbatim |
| 8 | **却下案を採っていない** — uvicorn `--workers N` を使わず、async psycopg への書き換えを行っていない | **監査照合** — 差分の目視 (設計 D-8 却下、L10-4) |

**検証コマンドと集計行の期待形**:

```
./.venv/bin/python -m pytest -q <peer>/tests/test_threadpool_offload.py   → 全 passed
./.venv/bin/python -m pytest -q <peer>/tests                              → 全 passed
./.venv/bin/python -m pytest -q conformance-tests                         → 全 passed (skipped 0 / xfailed 0)
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 3
  → PERFRUN 1 行 + PERF 21 行 (WP-7 の値と並記する)
```

**使用テンプレート**: **2** → **5** → **6**。
**変更クラス**: **B**。**`_ISOMORPHIC_TARGETS` に登録された helper の本体に触れば C** (計画文書 §9 の 8)。

---

### WP-9 — 完了ゲート + 記録

**目的**: 完了ゲート (§3) を実行し、`COLLECTION_FLOOR` を実測値に更新し、性能差分・非 vacuity の実測・台帳の閉止を記録し、計画文書に訂正註 2 件を入れ、第 17 次ハンドオーバーを置く。

**読むべき正本**: 設計 **§9 の 1〜17** (完了ゲート。**14〜17 は v1.3 の追記であり、本 WP の完了条件 17〜20 に対応する**)、**§10.0** (閉止条件の表)、**§10.1** (**訂正註 2 件の確定文**)、**§10.2** (L10-1〜L10-7)、**§11** (実施記録の置き場)、§6.3 (`COLLECTION_FLOOR`)、§1.2 (**R-22 の問い**)、§5 (U-1〜U-6)。計画文書 §9 の 5 / 6、`OPERATING_CONDITIONS.md` §1.3 の 19〜27、§1.8 の 55〜58。

**触るファイル**: `conformance-tests/COLLECTION_FLOOR` (**監督のみ**)、`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` (**§9〜§11 の実施記録**)、`docs/design/ROADMAP_POST_PHASE7_V1.md` (**§1「現状」・§5 の訂正註 2 件・§8 の行き先**)、本書 (**§5 訂正註**)、`docs/work-orders/HANDOVER_20260908_FABLE2.md` 相当の**第 17 次ハンドオーバー** (ファイル名は監督が確定する)。
**触らないファイル**: `spec/` 配下、`security/` 配下、両 peer の `src/` / `tests/` / `migrations/`、`conformance-tests/` の **`COLLECTION_FLOOR` 以外**、`tools/`、`.github/workflows/ci.yml`。

**完了条件 (全項 監査照合。本 WP の成果物はすべて文書・記録である)**:

| # | 完了条件 | 照合対象 |
|---|---|---|
| 1 | 完了ゲート §3 の全コマンドの集計行が期待形と一致する | 集計行の verbatim を設計 §11 に記録 |
| 2 | **`COLLECTION_FLOOR` をゲート時の実測値へ更新した** (着手時点 2807。**更新は監督のみ**) | `conformance-tests/COLLECTION_FLOOR` の値と、更新コミットが単独であること |
| 3 | **性能差分を記録した** — フェーズ9 §11.2 と同形式 (`PERFRUN` 行 + `PERF` 表)、**socket 2 plug は初回値、K=1 / K=3 の行を添え、閾値は置かず、plug 間の比較をしない** | 設計 §11 の該当節 |
| 4 | **非 vacuity の実測 (a)〜(e) を記録した** — (a) C-19 実ダイヤル枝が socket 2 plug の data / control 両面、(b) **C-25 (3) を駆動した plug 名と件数**、(c) C-05 concurrency 枝が socket 2 plug、(d) C-26 の 6 項目が両 launcher、(e) `composition_roots` が 2 件以上 | 設計 §11 の該当節 (設計 §9 の 8) |
| 5 | **プロセス・port の残骸 0** をゲート前後で確認した (**harness prefix 一致で照合**) | 実行したコマンドと出力 (設計 §9 の 2) |
| 6 | **`conformance` job の所要時間**を記録し、`timeout-minutes: 30` に収まったことを確認した | 設計 §11 と **L10-1** への記録。**収まらなければ本フェーズ内で再設計する** |
| 7 | **台帳の閉止**: 設計 §10.0 の各行を閉止条件と実測で突合し、**閉じた / 開いたままを確定した** | 設計 §10.0 の状態欄の更新 |
| 8 | **L9-10 の記録更新** (1.8.0 の無条件義務 1 件で **1.6.0 以降の累計 5 件、総数 15 件**)、**LQ4-24 は閉じず WP-6 の runbook 項からの参照で足りる** | 設計 §10.0 の該当行 |
| 9 | **L10-1〜L10-7 の状態を確定した** (L10-1 は実測値を記入。残りは記録として開いたまま) | 設計 §10.2 |
| 10 | **計画文書 §5 に訂正註 2 件を逐語で挿入した** (設計 §10.1 の (1) (2)。**原文は消さない**) | `docs/design/ROADMAP_POST_PHASE7_V1.md` §5 と設計 §10.1 の逐語一致 |
| 11 | **計画文書 §1「現状」と §8 の行き先を更新した** | 同文書 §1 / §8 (計画文書 §9 の 6) |
| 12 | **`CONDITIONS.md` の全 Status セルが 3000 字以内**であり、改訂 4 行 + C-26 行の旧文が `CONDITIONS_HISTORY.md` に逐語で在る | `conformance-tests/test_conditions_register.py` の緑と目視 |
| 13 | **全 WP の「完了条件番号 → 変異」対応表に対応の無い行が無い**こと。**変異を持たない完了条件は照合対象の逐語記録が設計 §11 に在る**こと | 本書 §2 の各表と設計 §11 |
| 14 | **第 17 次ハンドオーバーを置いた** (フェーズ固有の差分のみ。累積継承文を書かない) | `docs/work-orders/` の当該ファイル |
| 15 | **フェーズ完了報告で依頼者に問うた** — **U-1〜U-6 の列挙**と、**R-22 (`CONTROL_MAPPING.md` の再編を R-21 の是正と同時に行うか) の問い** | 報告本文 (設計 §9 の 13、§1.2) |
| 16 | **設計 §8.1 の「重なり 0」に訂正註を入れた** — 「**`conformance-tests/registry.json` の 1 行ずつを除く**」(WP-4a × WP-4b。本書 §1.2 の重なり表が実際の運用である)。**原文は消さない** | `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §8.1 と本書 §1.2 の突合 |
| **17** (**新設 v1.1**) | **C-27 が条件の集計に現れた** — WP-6d-ii の後の集計で C-27 が `executable` として数えられ、**4 plug で駆動し socket 2 plug が継承し、どの plug でも skip されないこと。** **非 vacuity の変異 (照会の前の key 単位 advisory lock を外すと C-27 の (i) (ii) と両 peer の `tests/test_idempotency_concurrency.py` が赤になる) を実際に注入して赤を観測した** | 設計 §11 の該当節 (**設計 §9 の 14**)。**駆動した plug 名と件数を逐語で記録する。** **本フェーズの新条件は C-26 と C-27 の 2 件である** |
| **18** (**新設 v1.1**) | **WP-6d の性能差分を記録した** — **表単位の件数 lock の下で Application ごとの keyed write が直列化される影響を、完了条件 3 の R-20 の計測の隣に同じ形式で置いた** (`PERFRUN` 行 + `PERF` 表、同じ `--warmup` / `--n`、K=1 / K=3、閾値なし、plug 間の比較なし)。**どちらが lock 導入前後のどちらであるかを明記した** | 設計 §11 の該当節 (**設計 §9 の 15**、`OPERATING_CONDITIONS.md` §1.3 の 27) |
| **19** (**新設 v1.1**) | **CI の `skipped == 0` / `xfailed == 0` / `xpassed == 0` / `deselected == 0` の強制が緑で見えた** — WP-1c が集計 step と比較 job の両方に置いた検査が **`conformance (Python 3.11)` と `conformance (Python 3.12)` の両方で緑**であること。**合成した集計入力 (`<N> passed, 1 skipped` / `2 xfailed`) で赤になることを WP-1c で実測済みである旨を記録した** | CI の当該 job の出力と設計 §11 (**設計 §9 の 16**、`OPERATING_CONDITIONS.md` §1.3 の 22 / 26) |
| **20** (**新設 v1.1**) | **外部レビュー 2 の台帳を閉止・持ち越しに仕分けた** — **計画文書 §8 の R-24 / R-25 / R-26 / R-27 / R-28 (1) (2) の閉止行を書き**、**R-28 (3) と R-29 / R-30 / R-31 / R-32 / R-33 はフェーズ11 へ開いたまま送ることを第 17 次ハンドオーバーに書いた。** **「閉じた」と書けるのは閉止条件を実測で突合した行だけである** | `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 と第 17 次ハンドオーバー (**設計 §9 の 17**、§5 U-13) |

**使用テンプレート**: **3** (Opus 起草) → **6** (Opus 証拠監査)。**判定とコミットは監督。**
**変更クラス**: **C**。

---

## 3. 完了ゲート (**実行するコマンドの列と集計行の期待形**)

**設計 §9 の 1〜17 が正本である。本節はそれを転記せず、実行するコマンドの列と集計行の期待形だけを置く。** **監督がリポジトリルートで単独実行する** (`OPERATING_CONDITIONS.md` §1.3 の 19)。

**【追記 2026-09-08 (v1.1)。収集数の増分について】** **本フェーズの収集数は、外部レビュー 2 の取り込みで更に増える** — **`conformance-tests/test_c27_concurrent_same_key.py` (C-27。4 plug で駆動し socket 2 plug が継承するので plug 数だけ倍化する)** と、**両 peer の `tests/test_idempotency_concurrency.py` (WP-6d-i)** の分である。**増分の具体的な数は WP-6d 完了時に確定する** — 本書では数を置かない。**`COLLECTION_FLOOR` は着手時点 2807 であり、更新は完了ゲートで監督のみが行う** (`OPERATING_CONDITIONS.md` §1.3 の 25)。

### 3.1 実行の順序

```
# 0. 前提の確認
ps ax | grep -c "[p]ytest"                       → 0 (他の pytest が 0 件)
psql -Atc "select datname from pg_database order by 1" > <before>

# 1. 収集数の下限
./.venv/bin/python tools/check_collection_floor.py
    → exit 0 (collected 数が COLLECTION_FLOOR 以上である旨の 1 行)

# 2. root suite の単独実行
./.venv/bin/python -m pytest -q -n 5 --dist loadgroup
    → 集計行: "<N> passed in <t>s"
    → failed / skipped / xfailed の語が集計行に 1 つも現れないこと
    → <N> は C-27 (conformance-tests/test_c27_concurrent_same_key.py、
      plug 数だけ倍化) と両 peer の tests/test_idempotency_concurrency.py の
      分だけ増える。増分は WP-6d 完了時に確定 (本書では数を置かない)

# 3. DB 残骸
psql -Atc "select datname from pg_database order by 1" > <after>; diff <before> <after>
    → 差分 0

# 4. プロセス・port 残骸 (本フェーズで新設する検査項目)
pgrep -fl "<harness prefix>"                     → 0 件 (uvicorn / nginx とも。
      照合は harness prefix 一致で行う。設計 D-2 (f) / D-11 の 2)

# 5. 文書と公開規律
./.venv/bin/python tools/check_doc_refs.py
    → tracked markdown files scanned: <N>
      empty markdown files: 0
      check_doc_refs OK: 0 dangling references
./.venv/bin/python tools/public_value_scan.py
    → # mode=tree ... total_flagged=0
./.venv/bin/python -m pytest -q tools/tests      → 全 passed

# 6. 契約 1.8.0 の記録
shasum -a 256 spec/data-service-api.v1.json \
  r2db-api/src/r2db_api/contract/data-service-api.v1.json \
  MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json
    → 3 本とも同一値 (値はフェーズ9 から必ず動く)。値を設計 §11 に記録

# 7. 性能差分 (単独実行)
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 1
./.venv/bin/python tools/perf_baseline.py --n 100 --warmup 10 --concurrency 3
    → 各回 PERFRUN 1 行 + PERF 21 行
```

### 3.2 CI 側で確認する集計行

| job | 期待 |
|---|---|
| `conformance (Python 3.11)` | **§3.1 の 2 の 4 数と一致**。**所要が `timeout-minutes: 30` 内**であり所要時間を設計 §11 と L10-1 に記録 |
| `tally-consistency` | **緑** (3.11 が authoritative、3.12 が再現) |
| `image-pins` | **緑** (設計 D-6) |
| `doc-refs` | **緑** (**空 `.md` 検査と L10 登録が入った後の版で**。設計 D-7) |
| `change-class` / `scanner` / `tools-tests` / `deploy-assets-lint` | **緑** |
| **`conformance (Python 3.11)` / `conformance (Python 3.12)` の `skipped == 0` / `xfailed == 0` / `xpassed == 0` / `deselected == 0` 検査** (**新設 v1.1。WP-1c。`xpassed` / `deselected` は監督裁定 2026-09-08 の拡張**) | **両方の matrix で緑であることを目視で確認する** — 集計 step の検査と比較 job の検査の**両方**である (設計 §9 の 16、`OPERATING_CONDITIONS.md` §1.3 の 22 / 26)。**集計の `<N> passed` は §3.1 の 2 と一致し、その `<N>` は WP-6d 完了時に確定する** |

### 3.3 実測で確認し §11 に記録する項目

1. **6 plug すべてで全条件が緑**であり、registry 6 件が `required: true` で **どの plug も skip されないこと** (設計 §9 の 7)。
2. **非 vacuity (a)〜(e)** (設計 §9 の 8)。**`--dist loadgroup` では plug ごとに worker が分かれるので、registry を読む guard と実測記録を併用する。**
3. **両 peer の `contract_version` が 1.8.0 (4 箇所)** と **C-19 の data 面 / control 面一致 assert が緑** (設計 §9 の 4)。
4. **`spec/OPERATION_CATALOG.json` の再生成一致テストが緑** (同)。
5. **`CONDITIONS.md` のセル長と履歴の逐語** (設計 §9 の 9)。
6. **既存配備の upgrade 手順** (migration → `ops declare-process-ceilings` → 再起動、LQ4-24 への参照) が両 peer の配備文書に在ること (設計 §9 の 10)。
7. **全 WP が常設規律 7 項目と速度規律 5 項目を満たすこと** (設計 §9 の 11)。
8. **設計レビュー 2 回**が済んでいること (設計 §9 の 12。**設計 v1.1 / v1.2 がその反映版である**)。
9. **C-27 が条件の集計に現れ、4 plug で駆動し socket 2 plug が継承していること** (設計 §9 の 14)。**非 vacuity の変異 (key 単位 advisory lock を外す) を注入して赤を観測し、駆動した plug 名と件数を記録する。** **条件は C-26 と C-27 の 2 件増える。**
10. **WP-6d の性能差分**を R-20 の計測の隣に同形式で置いたこと (設計 §9 の 15、`OPERATING_CONDITIONS.md` §1.3 の 27)。**lock 導入前後のどちらであるかを明記する。**
11. **外部レビュー 2 の台帳の仕分け** — **R-24 / R-25 / R-26 / R-27 / R-28 (1) (2) を閉止し、R-28 (3) と R-29〜R-33 をフェーズ11 へ開いたまま送る**ことを計画文書 §8 と第 17 次ハンドオーバーに書いたこと (設計 §9 の 17)。

---

## 4. コミット規律

1. **役割・コミット規律の正本は `OPERATING_CONDITIONS.md` §1.1 の 1〜12 である。本書は転記しない。** **git commit / push / merge は監督のみが行い、実装担当はコミットしない** (同 §1.1 の 2)。**commit → push → main マージまでを 1 単位とする** (同 3)。**main へのマージは `--no-ff`** (同 4)。
2. **push 前に `git log --format='%an <%ae>' -5` で `r2fish` / noreply のみを確認する。実名・Gmail アドレスが 1 件でもあれば push しない。確認は merge commit にも掛け、commit と同一のコマンドで行う** (同 §1.1 の 5〜7)。**branch の確認も commit と同一のコマンドで行う** (同 8)。
3. **契約ファイルを触るコミットは root suite 完走を完了条件にする** (同 §1.1 の 10)。**申告と実挙動は単一コミットでしか同時に動かさない** (同 11)。
4. **契約版フリップは pair-closing commit である** — **`contract_version` 1.7.0 → 1.8.0 は peer ごとに独立したコミットを作り、完了ゲート内で連続して main にマージし、フリップ間に他のコミットを挟まない** (設計 §8 の WP-6 行、フェーズ9 の運用)。
5. **`_ISOMORPHIC_TARGETS` の増減 (登録 helper の追加・削除) は Class D であり、監督の pair-closing commit で行う** (計画文書 §9 の 8、設計 §2.2 / §8)。**本フェーズで該当し得るのは WP-4 (socket adapter の同名 helper)、WP-6 (`_VERIFY_DECLARATIONS_EXIT_CODES` などの宣言機構 helper)、WP-6c (launcher の同名 helper)、WP-8 (委譲 helper) である。**
6. **`tools/check_doc_refs.py` の ID 族表 (`L_REF_RE` / `PHASE_CANONICAL`) の変更は別個の明示コミットで行う** (script 冒頭の docstring `:16-19`。WP-1b)。**`COLLECTION_FLOOR` の更新も同じ規約で単独コミットである** (`OPERATING_CONDITIONS.md` §1.3 の 25)。
7. **コミット前に変異文字列そのものを全文 grep して 0 件を確認する。変異を含むコミットを作らない** (同 §1.4 の 31)。

---

## 5. 訂正註

本書の訂正は本文を書き換えず本節に追記する (`OPERATING_CONDITIONS.md` §1.8 の 57)。

1. **【訂正註 2026-09-08 (監督裁定)】WP-5 を WP-5a / WP-5b に分けて発注した。** **WP-5a** = 完了条件 1〜9 と 14 に相当する「契約 1.8.0 の公開 (確定文 4 片、`versioning.obligations`、`CONTRACT_HISTORY.md`、`CCR_DISPOSITION.md` 従属判断 13、catalog 再生成、複製 3 本の byte 一致) と C-25 (3) の駆動条件の付け替え」であり、**WP-3 と触るファイルが重ならない**ので WP-3 と並行に着手した (worktree `phase10-wp5`)。**WP-5b** = `CONDITIONS.md` の改訂行 (C-05 honest limits、C-19 の socket 実ダイヤル、C-09 / C-25 の駆動 plug) と `CONDITIONS_HISTORY.md` への旧文移送であり、**socket plug が存在してから** (WP-4a / 4b の後) 行う — 「主張は実測の後」(`OPERATING_CONDITIONS.md` §1.5 の 34) のため。本文 WP-5 節の完了条件番号はそのまま有効で、5a / 5b は担当範囲の分割にすぎない。


2. **【訂正註 2026-09-08 (v1.1。外部レビュー 2 の監督検証を受けた改版)】** **依頼者が提示した 2 本目の外部レビュー (2026-09-08、基準 main `b16afdd`) を監督が現物で検証し、依頼者裁定 (逐語:「フェーズ 10 に組み込めるのであれば組み込んでください。」) に基づいて本フェーズに 5 項目を足した。** **正本設計は v1.3 であり、足された確定は §3 D-13 (同一 idempotency key の同時送信の直列化 = WP-6d と新条件 C-27)、§3 D-14 (小修正の束 = WP-1c)、§5 U-7〜U-13 である。** **本書の改版内容は次のとおりで、既存 manifest の本文は 1 文も書き換えていない**: **(a)** WP-1c の manifest を新設した (§2。**worktree `phase10-wp1c`、Class B、WP-3 より先に main へ入れる**)。**(b)** WP-6d-i / WP-6d-ii の manifest を新設した (§2。**worktree `phase10-wp6d`、Class C。6d-i は WP-3 に依存せず今すぐ着手でき、6d-ii は WP-3 の hook 抽出の後である**)。**(c)** WP-3 の manifest に追跡是正 (follow-up) 項目 (実装の指示 11 と完了条件 18。`sweep_orphans` の `pid <= 0` guard) を足した。**WP-3 は本改版の前に main `6055c69` へマージされていたので、本項は rework ではなく main に対する follow-up として実施した** — **branch `phase10-wp3f` の `ea237e5`**。**(d)** WP-5 の manifest に追補 (契約 1.8.0 の `idempotency.record` への 1 文。**監督が WP-5a の branch で実施する**) を足した。**本追補は実施済みである** — **branch `phase10-wp5` の `73adbda`**、義務 id `idempotency_concurrent_same_key_sends_serialized` (1.8.0 の `conditional` の (1))、**版は 1.8.0 のまま、packaged 複製 3 つは同一バイト**である。**WP-5a 本体は `654e23e` の時点で main `3d7f823` にマージ済みであり、本追補はそこに含まれない — 次のゲート束でマージする。****(e)** WP-8 の manifest に前提条件 (1 要求 1 接続、cell が接続を跨いで共有しない) を足した。**(f)** §0.5 の新規ファイル名表、§1.1 の worktree 名、§1.2 の並行可・直列表に行を足した。**(g)** **WP-9 の manifest に完了条件 17〜20 を足し** (C-27 が集計に現れること、WP-6d の性能差分、CI の `skipped` / `xfailed` 検査が両 matrix で緑であること、R-24〜R-28 の閉止と R-29〜R-32 の持ち越し)、**§3 に収集数の増分註 (C-27 と両 peer の `tests/test_idempotency_concurrency.py`。数は WP-6d 完了時に確定)、§3.2 の CI 検査行、§3.3 の 9〜11 を足した** (設計 §9 の 14〜17)。**計画文書側の起票は `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.8) §1.0d と §8 の R-24〜R-33 である** (**R-33 は WP-1c のコードレビューが見つけた MitateDB の死んだ `destructive` 引数であり、フェーズ11 送りである**)。 **フェーズ9 の完了は取り消していない** — 完了が覆うのは逐次経路の再送安全性であり、同時送信の再送安全性を示すのが WP-6d である。


3. **【訂正註 2026-09-08 (v1.2。実施の反映)】** **WP-6d-i の実装とそのコードレビューを受けて、本書に 3 点を足した。既存 manifest の本文は 1 文も書き換えていない。** **(a)** **WP-6d-i の manifest に「状態」「実施の記録」と完了条件 **11〜13** を足した** — **11 は `finally` での unlock、12 は回収 (reap) の永続化、13 は lock 待ちタイムアウトの `LIMIT_EXCEEDED` 写像であり、いずれも Opus のコードレビュー (F1 / F2 / F3) の是正で足したテストである。** **実現の形が peer で分かれた理由 (MitateDB の catalog 読みが同一接続の途中で自己 commit するため transaction-scoped lock が早期解放される) は設計 §3 D-13 の実施註が正本であり、本書は指すだけである** (§0.0 の 2)。**(b)** **WP-R35 の manifest (骨子) を新設した** — **フェーズ9 R-2 の走査 lock mode (`LOCK TABLE ... IN SHARE MODE`) を `SHARE ROW EXCLUSIVE` に改める Class B の小 WP であり、出所は WP-6d-i の完了条件 8 の報告である** (設計 §3 **D-15**、計画文書 §8 の **R-35**。**worktree `phase10-r35`、実施中**)。**(c)** **§0.5 に WP-R35 のテスト置き場の行 (未確定)、§1.1 に `phase10-r35` / `phase10-r34` の worktree 命名の例外、§1.2 に `WP-6d-i → WP-R35` の直列行を足した。** **WP-9 の完了条件 20 (台帳の閉止と持ち越し) は、**R-34** (完了ゲートの timing テストの同期化。branch `phase10-r34` の `12a7bd7` / `5a59002`) と **R-35** の閉止行も対象に含める** — **本文の列挙は v1.1 時点のものであり、書き換えずに本註で補う。**
