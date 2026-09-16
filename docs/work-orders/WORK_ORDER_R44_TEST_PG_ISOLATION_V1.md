# 作業指示書 — R-44 テスト用 PostgreSQL の実行ごとの分離

## 0. 版数・位置づけ

- **v1.0 (2026-09-16)。** 基点 main `41a7363`。設計は `docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` (v0.2、依頼者裁定済み: Q-1〜Q-9 すべて推奨)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-44。
- WP-1 の manifest を §2 に固定する。WP-2〜WP-4 は §3〜§5 に枠を置き、各 WP の着手時に manifest を追記する (既存の行は書き換えない)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、`--no-ff`、r2fish noreply、道具は `tools/dev/`)。WP-4 で規律を改訂するまでは現行の規律のまま進める。

## 1. 共通の枠

- **順序**: WP-1 → WP-2 → WP-3 → WP-4 の直列。各 WP は監督の完了ゲートを通してから main に統合する。
- **公開規律**: 実 DSN・パスワードをファイル・ログ・stdout に置かない。パスワードは実行ごとの生成値で、`PGPASSFILE` (0600) でだけ渡す。
- **共有クラスタ**: 実装・テストのどの段階でも共有クラスタ (`host=/tmp port=5432`) に接続しない。例外は WP-2 の gate の情報表示 (読み取りのみ) だけ。
- **skip 禁止**: 検証できない条件は fail させる (§1.3 の 26)。
- **変異**: 新しいテストは manifest の変異で赤になることを `tools/dev/mutate.py` で示す。
- **R-37 との重なり**: 着手時に `git worktree list` と R-37 の進行中 WP の触るファイルを見て、重なるファイルがあれば監督に上げる (設計 §6 Q-4)。

## 2. WP-1 — 起動部品、3 つの conftest、CI の整合

**目的**: pytest の実行ごとに使い捨ての PostgreSQL 16 クラスタを起動し、その実行 (xdist の worker と子プロセスを含む) の接続先にする。設計 D-1〜D-4、D-8 の一部。

### 2.1 起動部品 `tools/testpg/dsa_testpg.py` (新規、標準ライブラリのみ)

- **クラスタの起動** (`start()` → `Cluster`、context manager `cluster()`):
  - バイナリ: `DSA_TEST_PG_BINDIR` があればそこ、なければ `pg_config --bindir`、なければ `PATH`。`postgres --version` のメジャー版が 16 でなければ `TestPgError`。
  - 基底: `<tempfile.gettempdir()>/dsa-testpg-<uid>` (0700)。既存なら、所有者が自分で symlink でないことを確かめる。実行ディレクトリは基底の下に `mkdtemp(prefix="run-")`。
  - 実行ディレクトリの中身: `owner.lock` (起動した process が `flock` を掛けたまま持つ)、`data/`、`s/` (socket、0700)、`pgpass` (0600)、`postgres.log`、`meta.json` (postmaster の pid)。
  - socket のパス (`<s>/.s.PGSQL.5432`) が 103 バイトを超えたら `TestPgError`。
  - `initdb -D data -U postgres --auth=scram-sha-256 --pwfile=<一時ファイル> --locale=en_US.UTF-8 --encoding=UTF8`。pwfile は initdb の直後に消す。パスワードは `secrets.token_urlsafe(32)`。
  - `postgres -D data -c listen_addresses= -c unix_socket_directories=<s> -c unix_socket_permissions=0700 -c port=5432 -c max_connections=300 -c TimeZone=Asia/Tokyo`。`start_new_session=True`、出力は `postgres.log`。
  - `initdb` と `postgres` の環境: 呼び出し元の環境から `PG` で始まる変数を除き、`LC_ALL=en_US.UTF-8` を置く (設計 §3.4)。
  - 準備完了: `pg_isready -h <s> -p 5432 -d postgres` が 0 を返すまで待つ (上限 30 秒)。postgres が先に終了したら `postgres.log` の末尾を添えて `TestPgError`。
  - `pgpass` の 1 行: `<s>:5432:*:postgres:<password>`。
- **監視プロセス** (`--watchdog <run dir>` で自分自身を起動、`start_new_session=True`):
  - 起動した process とのパイプの読み端を stdin に持ち、EOF まで読む。EOF は起動した process の正常終了・SIGKILL のどちらでも来る。
  - EOF で postmaster に SIGTERM → 10 秒待つ → SIGQUIT → 5 秒待つ → SIGKILL。送る前に `ps -o args= -p <pid>` が実行ディレクトリの `data` を含むことを確かめる (pid 再利用の防止)。
  - 停止後に実行ディレクトリを消す。
  - `Cluster.stop()` はパイプを閉じ、監視プロセスの終了を待つ (上限 30 秒)。停止の経路は監視プロセスの 1 つだけにする。
- **掃除** (`sweep()`、`start()` の最初に呼ぶ。CLI `sweep` もある):
  - 基底の下の `run-*` ごとに `owner.lock` へ `flock(LOCK_EX | LOCK_NB)` を試す。取れなければ生きている実行なので触らない。
  - 取れたら所有者は死んでいる。`meta.json` の pid が生きていて、上と同じ確認に合えば SIGQUIT → SIGKILL。その後ディレクトリを消す。
- **接続情報** (`Cluster.env()` が返す dict):
  - `R2DB_TEST_ADMIN_DSN` と `MITATEDB_TEST_ADMIN_DSN` = `host=<s> port=5432 dbname=postgres user=postgres` (パスワードを含めない)
  - `PGHOST=<s>`、`PGPORT=5432`、`PGUSER=postgres`、`PGPASSFILE=<run>/pgpass`
  - 環境に反映するときは `PGPASSWORD` を消す。
- **pytest からの呼び出し** (`ensure_for_pytest()`、冪等):
  - 判定表:

    | 条件 | 動作 |
    |---|---|
    | `DSA_TEST_PG` が `external` | 2 つの DSN が両方あることを確かめる。無ければ `TestPgError` |
    | `DSA_TEST_PG` が `owned:` で始まる | 2 つの DSN と `PGPASSFILE` があることを確かめる。起動しない |
    | `PYTEST_XDIST_WORKER` があり、`DSA_TEST_PG` が上の 2 つでない | `TestPgError` |
    | `DSA_TEST_PG` が未設定で、DSN のどちらかがある | `TestPgError` (曖昧) |
    | `DSA_TEST_PG` が未設定で、DSN が無い | 起動し、`os.environ` に `Cluster.env()` と `DSA_TEST_PG=owned:<実行ディレクトリ名>` を置く。atexit で停止する |
    | `DSA_TEST_PG` がその他の値 | `TestPgError` |

  - `stop_owned()`: この process が起動したクラスタだけを止める (冪等)。
  - `DSA_TEST_PG_REPORT=<path>` があれば、起動した実行ディレクトリのパスをそのファイルに書く (テスト用)。
- **CLI**: `python tools/testpg/dsa_testpg.py run -- <コマンド...>` はクラスタを起動し、`Cluster.env()` と `DSA_TEST_PG=external` を足した環境でコマンドを実行し、終了コードを返して停止する。`sweep` は掃除だけを行う。
- DSN・パスワードを例外メッセージ・stdout に出さない (出してよいのは socket ディレクトリのパスと `postgres.log` の末尾)。

### 2.2 3 つの conftest (新規、バイト単位で同一)

- 置き場所: リポジトリ直下 `conftest.py`、`r2db-api/conftest.py`、`MitateDB-api/conftest.py`。
- 内容: 自分の位置から親をたどって `tools/testpg/dsa_testpg.py` を見つけ、そのディレクトリを `sys.path` の先頭に足して `import dsa_testpg`、import 時に `dsa_testpg.ensure_for_pytest()` を呼ぶ。`pytest_unconfigure` で `dsa_testpg.stop_owned()` を呼ぶ。
- 親をたどって見つからなければ `ImportError` (fail)。

### 2.3 その他

- `tools/tests/pytest.ini` (新規): `[pytest]` にルートの `filterwarnings` と同じ 2 項目を置く。`pytest tools/tests` の根をここにして、3 つの conftest を読ませない。
- `conformance-tests/test_pytest_config_symmetry.py`: 3 つの conftest がバイト単位で同一であることのテストを足す。
- `.github/workflows/ci.yml`: workflow の `env:` に `DSA_TEST_PG: external` を足す。`conformance` job に PostgreSQL 16 のサーバーバイナリの導入 (`postgresql-16`) と `DSA_TEST_PG_BINDIR` を足す (2.4 の統合テスト用)。push 停止中は CI で確かめられないので、§6 に未確認として残す。

### 2.4 テスト

- **単体** `tools/tests/test_testpg.py` (PostgreSQL を使わない): 判定表の全行、`Cluster.env()` の形 (DSN にパスワードが無い)、`pgpass` の中身と 0600、socket パス長の上限、基底の所有者・symlink の検査、`sweep()` (lock が掛かっていれば残す、外れていれば消す、pid の確認に合わなければ signal を送らない)、版の判定 (`postgres (PostgreSQL) 16.14` は可、15 は不可)。
- **統合** `conformance-tests/test_testpg_cluster.py` (実クラスタを起動する。suite 自身のクラスタに頼らず、起動部品で入れ子のクラスタを起動するので、owned / external のどちらの suite でも同じに動く):
  1. `run -- <python>` の子で、host を書かない `psycopg.connect("dbname=postgres")` がそのクラスタに届く (`current_setting('unix_socket_directories')` が `PGHOST` と一致)。`max_connections=300`、`TimeZone=Asia/Tokyo`、`password_encryption=scram-sha-256`、`listen_addresses` が空。
  2. 誤ったパスワード (`PGPASSFILE=/dev/null` と `password=` の誤値) で接続が拒否される。
  3. `cluster()` を抜けると postmaster が終了し、実行ディレクトリが消える。`system_identifier` が suite のクラスタと異なる。
  4. `run -- <長く眠る python>` の CLI process を SIGKILL すると、上限時間内に postmaster が終了し、実行ディレクトリが消える。
  5. 入れ子の pytest: `DSA_TEST_PG` を消し DSN を残した環境で `python -m pytest` を起動すると非 0 で終わり、曖昧の旨を出す。`owned:` の環境では新しいクラスタを起動しない (`DSA_TEST_PG_REPORT` が書かれない)。
  6. peer の根: DSN と `DSA_TEST_PG` を消した環境で `python -m pytest --collect-only -q r2db-api/tests/test_foundation.py` を起動すると、`DSA_TEST_PG_REPORT` に実行ディレクトリが書かれ、終了後にそのディレクトリが消えている。MitateDB-api も同じ。
  7. `pytest tools/tests` の根では起動しない (`DSA_TEST_PG_REPORT` が書かれない)。

### 2.5 manifest

| 触るファイル | 触らないファイル |
|---|---|
| 新規 `tools/testpg/dsa_testpg.py`、新規 `conftest.py`・`r2db-api/conftest.py`・`MitateDB-api/conftest.py`、新規 `tools/tests/pytest.ini`、新規 `tools/tests/test_testpg.py`、新規 `conformance-tests/test_testpg_cluster.py`、`conformance-tests/test_pytest_config_symmetry.py`、`.github/workflows/ci.yml` | adapter・`real_server_*.py`・23 ファイルの既定値 (WP-3)、`tools/dev/` と `tools/perf_baseline.py` (WP-2)、`conformance-tests/socket_harness.py` (WP-3)、`docs/work-orders/OPERATING_CONDITIONS.md` と README 類 (WP-4)、`conformance-tests/COLLECTION_FLOOR` (監督が完了ゲートで更新) |

| # | 完了条件 | 変異 (`file:操作`) | 赤になるテスト (予想) |
|---|---|---|---|
| 1 | host を書かない接続が実行のクラスタに届く | `dsa_testpg.py`: `Cluster.env()` から `PGHOST` を消す | 統合 1 |
| 2 | scram で誤ったパスワードを拒否する | `dsa_testpg.py`: `--auth=scram-sha-256` を `--auth=trust` にする | 統合 2 |
| 3 | 設定値 | `dsa_testpg.py`: `-c TimeZone=Asia/Tokyo` を消す | 統合 1 |
| 4 | 起動した process の SIGKILL で後始末される | 監視プロセス: EOF の後の停止処理を呼ばない | 統合 4 |
| 5 | 正常停止で後始末される | `Cluster.stop()`: パイプを閉じない | 統合 3 |
| 6 | 曖昧な環境は fail | `ensure_for_pytest()`: 曖昧の行の raise を消す | 単体 (判定表)、統合 5 |
| 7 | worker は起動しない | `ensure_for_pytest()`: `PYTEST_XDIST_WORKER` の行を消す | 単体 (判定表) |
| 8 | 生きている実行を掃除しない | `sweep()`: lock が取れないときも消す | 単体 (sweep) |
| 9 | DSN にパスワードを入れない | `Cluster.env()`: DSN に `password=` を足す | 単体 (env の形) |
| 10 | `pgpass` は 0600 | `dsa_testpg.py`: `pgpass` を 0644 で作る | 単体 (pgpass) |
| 11 | peer の根でも起動する | `r2db-api/conftest.py`: `ensure_for_pytest()` の呼び出しを消す | 統合 6、symmetry |
| 12 | `tools/tests` の根では起動しない | `tools/tests/pytest.ini` を消す | 統合 7 |
| 13 | macOS で起動できる | `dsa_testpg.py`: `LC_ALL` を置かない | 統合 1〜4 (起動失敗) |

- **完了ゲート**: 監督が `tools/dev/gate.py` で root suite を通す。集計行は直前の main (`3402 passed, 2 subtests passed`) に新規テストの数を足したものと一致し、共有クラスタの差分は 0 であること。`tools/tests` の集計行も添える。

### 2.6 訂正註 (2026-09-16、独立レビュー 1 回目の後。本文は書き換えない)

- **(a) §2.5 の 12 行目の変異は `mutate.py` では表現できない。** 対応する変異は `tools/tests/pytest.ini` の削除だが、`mutate.py` は文字列の置換しか行わず、`pytest.ini` は中身が空でも根として数えられる。よって 12 行目は **監督の監査照合**で確かめる: ファイルを一時的に改名 → 統合テスト 7 を実行 → 戻す → sha256 を 2 回照合 (§1.4 の 28〜31 と同じ形)。結果を §2.6 に記録する。
- **(a-1) 12 行目の監査照合の結果 (2026-09-16、監督)。** `tools/tests/pytest.ini` を scratchpad へ退避すると `conformance-tests/test_testpg_cluster.py::test_tools_tests_root_does_not_start_a_cluster` が赤 (`1 failed, 8 deselected`)、戻すと緑 (`1 passed, 8 deselected`)。復元は sha256 を 3 秒あけて 2 回照合し、退避前と一致した (`7b4c0cc3…bbc1`)。よって 12 行目の完了条件は満たされている。
- **(b) §2.5 の 3 行目 (TimeZone) の変異は、最初の実行で緑になった。** `-c TimeZone=Asia/Tokyo` を消しても、`initdb` が焼いた既定値で同じ値になるためである。固定を 2 つに分ける: `pg_settings` の `source` が `command line` であること (統合) と、`postgres` の引数に `-c` の設定が並ぶこと (単体)。
- **(c) §2.2 に追記**: 3 つの conftest は、pytest が非 package の `conftest` を複数読み込めるように `sys.modules` の後始末を行う。この処理も 1 つのテストと変異で固定する。
- **(d) WP-1 の間の gate の限界**: `tools/dev/gate.py` は共有クラスタを見続けるが、テストはもう共有クラスタに触れないので、その前後差分 0 は「残骸なし」の証拠にならない。実行のクラスタを見る判定は WP-2 で入れる。それまでの gate の `pg_database / pg_roles` の行は情報として読む。
- **(f) 並列実行でだけ出た不具合 (2026-09-16、監督の完了ゲート 1 回目、`3 failed, 3414 passed`)。** `-n 5 --dist loadgroup` では、テストが worker の中で動き、そこから起動する入れ子の pytest が `PYTEST_XDIST_WORKER` を引き継ぐ。起動部品はそれを見て「worker なのに mode が無い」と判定し、新しい controller であるにもかかわらず起動を拒む (`test_nested_pytest_with_a_dsn_but_no_mode_is_ambiguous_and_fails`、`test_peer_root_starts_and_cleans_up_its_own_cluster` の 2 件)。直列の実行では再現しない。対処は 2 段: 起動部品は、環境変数だけでなく process が本当に worker であること (`xdist.remote` が `sys.modules` にあること) を確かめる。テストは入れ子の pytest に渡す環境から `PYTEST_*` を除く。単体テストと変異を足す。
- **(e) レビューの主な指摘**: 統合テストが実行中の環境変数を読むと CI で壊れ、外部モードの指す先が共有クラスタなら接続してしまう (§1 違反)。`sweep()` の基底ディレクトリの安全確認漏れ。実行ディレクトリの作成から `flock` までの隙。失敗経路での postmaster と fd の取り残し。いずれも実装で直す。全文は独立レビューの報告 (`$SP` の scratchpad、非追跡) にある。

## 3. WP-2 — 道具 (枠。着手時に manifest を追記する)

- `tools/dev/gate.py`: `dsa_testpg.cluster()` でクラスタを起動し、`DSA_TEST_PG=external` と `Cluster.env()` で pytest を実行する。`pg_database` / `pg_roles` の前後比較はそのクラスタで停止前に行い、FAIL の判定に使う。共有クラスタの前後比較は情報表示だけにする (Q-3)。
- 排他 (Q-2 の (a)): `dsa_testpg` に lock を置く。gate は着手の印を置いて排他 lock を取り、`ensure_for_pytest()` (controller) は印があれば待ってから共有 lock を実行の間持つ。`tools/dev/_devlib.py` の `ps` による検出と hold flag を廃止し、`pt.py` / `mutate.py` / `finalize.py` から外す。
- `tools/perf_baseline.py`: 起動部品で専用クラスタを使い、排他 lock を取る (単独実行)。
- テスト: `tools/tests/test_dev_tools.py` の hold flag・他 pytest の検出のテストを置き換える。

### 3.1 WP-2 manifest (v1.1、2026-09-16 追記。§3 の枠は書き換えない)

**目的**: 道具を新方式へ移す。gate は実行のクラスタを見て判定し、`ps` の観測による排他を実ロックに置き換え、hold flag を廃止する。設計 D-5・D-6・D-9、裁定 Q-2 (a)・Q-3。基点は WP-1 統合後の main (`41e1beb`)。

**(a) ロック (`tools/testpg/dsa_testpg.py` に足す)**

- 基底ディレクトリ直下に `suite.lock` と `gate.intent` を置く (実行ディレクトリの外。掃除の対象にしない)。
- `suite_lock(exclusive: bool, wait: float)`: `flock` の context manager。排他は gate と性能計測、共有はそれ以外の pytest。
- gate は `gate.intent` を書いてから排他ロックを取り、解放時に消す。共有ロックを取る側は、`gate.intent` があれば消えるまで待ってから取りに行く (gate の飢餓防止)。ロックなので、確認と取得の間に隙が無い。
- `ensure_for_pytest()` は **owned のときだけ**共有ロックを実行の間持つ (`stop_owned()` で解放)。`external` では取らない — gate 自身が起動する pytest が、gate の排他ロックと自分で競合しないため。
- 待ち時間を超えたら `TestPgError` (道具側は REFUSED 75 に変換する)。

**(b) `tools/dev/gate.py`**

- `dsa_testpg` で自分のクラスタを起動し、`DSA_TEST_PG=external` と `Cluster.env()` を渡して root suite を実行する。
- `pg_database` / `pg_roles` の前後比較は**そのクラスタ**で、停止前に行う。差分があれば FAIL (名前の出力は現行のまま)。
- 共有クラスタの前後比較は `info=` の 1 行として残す。判定には使わない (Q-3)。
- 排他ロックを取る。`--hold` と gate-hold flag、`ps` による他 pytest の監視 (`run_watched` の poll) を廃止する。
- 出力は現行の形を保つ (集計行、`judge=`、名前の行、`log=`)。

**(c) `tools/dev/pt.py` / `mutate.py` / `finalize.py` / `handover_ready.py` / `_devlib.py`**

- `hold_flag` / `blockers` / `wait_clear` / `other_pytest` / `current_other_pytest` / `parse_ps` と `--hold` を削除する。`blockers` の役割のうち**変異 journal の検査だけ**を残す (`journal_blocker()` に改名)。
- `pt.py` / `mutate.py`: `--wait` は「gate の排他ロックが解けるまでの待ち」に意味を変える。実行は conftest 経由で共有ロックを取るので、道具側での二重取得はしない。
- `finalize.py --tools-tests`: `tools/tests` は conftest を読まない (根が `tools/tests/pytest.ini`) ので、ロックも PostgreSQL も要らない。journal の検査だけを残す。
- `handover_ready.py`: 「他の pytest が 0 件」「gate-hold flag が無い」の 2 条件を廃止し、「gate が走っていない (`gate.intent` が無く排他ロックが空いている)」「変異 journal が無い」「担当 worktree がクリーン」に置き換える。

**(d) `tools/perf_baseline.py`**

- `dsa_testpg.cluster()` で専用クラスタを使い、排他ロックを取る (単独実行を維持、§2 の 19・§3 の 10)。
- 基準値の取り直しは WP-4 (Q-9)。

| 触るファイル | 触らないファイル |
|---|---|
| `tools/testpg/dsa_testpg.py`、`tools/dev/gate.py`・`pt.py`・`mutate.py`・`finalize.py`・`handover_ready.py`・`_devlib.py`、`tools/perf_baseline.py`、`tools/tests/test_dev_tools.py`、`tools/tests/test_testpg.py`、`tools/dev/README.md` (道具の説明は道具と同じコミットで直す) | 23 ファイルの既定値と `socket_harness.py` (WP-3)、`docs/work-orders/OPERATING_CONDITIONS.md` と他の README (WP-4)、`conftest.py` 3 つ、`.github/workflows/ci.yml`、`conformance-tests/` のテスト |

| # | 完了条件 | 変異 (`file:操作`) | 赤になるテスト (予想) |
|---|---|---|---|
| 1 | gate は実行のクラスタの差分で FAIL する | `gate.py`: 判定から実行クラスタの差分を外す | `test_dev_tools.py::test_gate_fails_on_run_cluster_diff` (新規、`snapshot` を注入) |
| 2 | gate は共有クラスタの差分では FAIL しない | `gate.py`: 共有クラスタの差分を判定に足す | `::test_gate_shared_cluster_diff_is_info_only` (新規) |
| 3 | gate は pytest に external と接続情報を渡す | `gate.py`: `DSA_TEST_PG` を渡さない | `::test_gate_passes_external_env_to_pytest` (新規) |
| 4 | gate は排他ロックを取る | `gate.py`: ロックを取らない | `::test_gate_holds_the_exclusive_lock` (新規、別 process から共有ロックを試す) |
| 5 | 共有ロックは gate の intent を待つ | `dsa_testpg.py`: intent の確認を消す | `test_testpg.py::test_shared_lock_waits_for_gate_intent` (新規) |
| 6 | external では共有ロックを取らない | `dsa_testpg.py`: external でも取る | `test_testpg.py::test_external_mode_takes_no_lock` (新規。取ると gate 自身が止まる) |
| 7 | 変異 journal の検査は残る | `_devlib.py`: `journal_blocker()` を無効にする | `test_dev_tools.py` の既存の journal テスト |
| 8 | 性能計測は排他ロックと専用クラスタを使う | `perf_baseline.py`: ロックを取らない | `test_perf_baseline.py::test_perf_baseline_takes_the_exclusive_lock` (新規) |
| 9 | `handover_ready` は gate 中に READY を出さない | `handover_ready.py`: gate の確認を消す | `test_dev_tools.py::test_handover_not_ready_while_gate_runs` (新規) |

- **完了ゲート**: 新しい `gate.py` 自身で root suite を通す。集計行は WP-1 統合後の main (`3417 passed, 2 subtests passed`) に新規テストの数を足した値と一致し、実行クラスタの差分 0、共有クラスタの情報行も 0 であること。
- **並列の確認 (設計 §7 の完了条件)**: suite を 2 本並列に 3 回走らせ、毎回両方の集計行が一致することを WP-2 の報告に添える。

### 3.2 WP-2 の訂正註 (2026-09-16、実装中。§3.1 の本文は書き換えない)

- **(a) 触るファイルの欠け。** §3.1 の表の 8 行目は `tools/perf_baseline.py` のテストを求めているが、その置き場所 `tools/tests/test_perf_baseline.py` を「触るファイル」に入れ忘れていた。1 道具 1 テストファイルの慣行どおり、同ファイルを触ることを許可する (実装担当の申告により監督が追認)。
- **(b) `gate.py` の `--wait-max` を `--wait` に改名する。** `pt.py` / `mutate.py` と同じ名前にする。意味は「gate の排他ロックが取れるまで待つ上限」。
- **(c) 終了コードの切り分け。** ロックの待ちが尽きたときだけ REFUSED (75)。クラスタの起動失敗は前提条件の誤りなので ERROR (78)。§3.1 (a) の「REFUSED 75 に変換する」はロックの待ちについての記述である。
- **(d) `mutate.py` の判定語彙に `error` を足す。** 現行は「赤 = pytest の終了コード 1」しかない。収集より前に実行そのものが壊れる変異 (WP-1 の `M13-no-lc-all`: `LC_ALL` を外すと、その実行自身の conftest がクラスタを起動できない) は終了コード 4 になり、意図どおりの理由で落ちているのに不一致として扱われ、変異実行全体が 1 で終わっていた。`expect: "error"` を足して 2〜5 に対応させ、`red` は 1、`green` は 0 のままとする。`mutate.py` の docstring と `tools/dev/README.md` にも書き、三値を固定するテストと、その判定を壊す変異を 1 件足す。WP-1 の spec の `M13` は履歴としてそのまま残す。

- **(e) 触るファイルの追加 (2 件)。** `docs/work-orders/ROLE_PROMPT_TEMPLATES.md` と `.claude/agents/implementer.md` は subagent に `--hold` を渡すよう書いており、WP-2 の統合と同時に argparse のエラーで止まる。規律の正本 (`OPERATING_CONDITIONS.md`) は WP-4 のままとし、この 2 件だけ WP-2 で直す。
- **(f) 独立レビューの重大な指摘 (2026-09-16)。** gate が排他ロックを保持したまま root suite を流すと、suite に含まれる WP-1 のテスト (peer の根で入れ子の owned の pytest を起動する 2 件) が同じロックを待ち、時間切れになる。gate が自分の pytest に「ロックは自分が持っている」ことを環境変数で伝え、owned の分岐はそれを見てロックを取らない形にする。テストと変異を足す。あわせて: `gate.intent` が kill -9 の後に残ると機械全体が止まるので、intent 自身に `flock` を掛けて古いものを消す。共有クラスタの読み取りが失敗しても gate の判定・出力を止めない。ロックの待ちの時間切れを REFUSED (75) に変換する。

- **(g) 規律の正本への訂正註 (2026-09-16、後任監督 cranky-curie の指摘により採用)。** WP-2 の統合から WP-4 の改訂までの間、`OPERATING_CONDITIONS.md` §1.10 の 64 と、実行手順を持つ雛形・agent 定義が食い違う。そこで §1.10 に 1 行の訂正註 (「hold flag・`--hold`・`ps` の確認は R-44 WP-2 で廃止。正式な改訂は WP-4」) を WP-2 で入れる。本文は書き換えない (§1.8 の 56・57)。触るファイルに `docs/work-orders/OPERATING_CONDITIONS.md` を訂正註 1 件の範囲で加える。
  - 【追記 2026-09-16】後任監督の再指摘により、訂正註に **§1.3 の 23** を加えた。WP-1 の統合以降、共有クラスタの差分 0 は残骸なしの証拠ではない。WP-1 と WP-2 の間に gate を掛ける読み手が、差分 0 を証拠と読む穴を塞ぐ。

- **(h) WP-2 の完了ゲート (2026-09-16)。** 1 回目 (`10:08:44` 開始) は、後任監督の実装担当の `conformance-tests` (約 13 分) と重なっていたため**破棄**した (引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE.md` §5: 他の pytest が動いている最中に開始した gate は PASS でも破棄する。新しい gate が `ps` を数えなくなったのは判定の話で、負荷の理由は消えていない)。新しい `gate.py` の動作確認としては読み、出力の 4 行の形を確認した。正本は 2 回目 (`10:16:58` 開始、マシン上の pytest はこの 1 本のみ): `3417 passed, 2 subtests passed`、judge=PASS、実行クラスタの差分 0、`info=shared … 0`、残骸は `suite.lock` のみ。root suite の集計行は WP-1 統合後と同じ (WP-2 の新規テストはすべて `tools/tests` にあり `testpaths` の外)。`tools/tests` は 453 → 486。
- **(i) 直さずに残した軽微な指摘 (実装担当の申告、監督が追認)。** 基底ディレクトリの検査失敗の終了コードの区分、`perf_baseline` のクラスタ起動失敗が 78 でなく 1 になること、`expect: "error"` が終了コード 5 も受けること。いずれも判定の正しさに関わらないので WP-4 以降で扱う。

## 4. WP-3 — 既定値の削除と待ち受けポート (枠)

- 23 ファイルの `host=/tmp port=5432 dbname=postgres` の既定値と、それを埋め込んだ fail メッセージを削除し、未設定は fail にする。`tools/tests` に既定値のリテラルが再び入らないことの検査を足す。
- `conformance-tests/socket_harness.py` と `real_server_*.py`: subprocess の uvicorn に `reserve_port()` のソケットを `pass_fds` と `--fd` で渡す。先に F-16 の spike を行う (設計 D-7)。
- nginx の bind 再試行を 3 回にし、失敗ごとに `error.log` を残す (Q-8)。docstring の「1 回だけ」には裁定の変更を註で残す。

### 4.1 WP-4 で直す積み残し (2026-09-16 追記)

- **`handover_ready.py` の「gate が走っていない」判定が広すぎる。** 実装は排他ロックを試すので、gate ではない普通の pytest が共有ロックを持っているだけでも NOT READY になる (2026-09-16 実測: 他セッションの suite が走っている間、引き継ぎの判定が通らなかった)。判定は `gate.intent` の有無 (と生存) で行い、共有ロックの保持者がいることは NOT READY の理由にしない。テストと変異を足す。
- WP-2 で直さずに残した軽微な 3 件 (§3.2 (i)) もここで扱う。
- **【追記 2026-09-16、WP-3 の設計レビュー裁定 R-7】nginx の bind 再試行が 4 経路に掛かっていない。** 並列 2 本を常態にする R-44 の下で、この 4 経路 (`r2db-api/conformance/real_server_r2db.py:656`、`MitateDB-api/conformance/real_server_mitatedb.py:595`、`r2db-api/conformance/conformance_adapter_r2db_socket.py:289`、`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py:222`) は bind 競争に負けると `HarnessStartupError` で落ちる。設計判断 (再試行時に `declare-surfaces` をやり直すか) を要する。
- **【追記 2026-09-16、WP-3 の設計レビュー裁定 R-10】`external` 分岐 (`tools/testpg/dsa_testpg.py`) は DSN 2 本しか要求せず `PGHOST` を要求しない。** host を書かない接続は external では共有クラスタへ届く。`PGHOST` / `PGPORT` も要求させるかを WP-4 で決める。§4.2 (d-2) の 3 の走査が、該当箇所を allowlist として可視化する。

### 4.2 WP-3 manifest (v1.3、2026-09-16 改訂。§4 の枠は書き換えない)

- v1.2 (2026-09-16) を、設計レビュー 2 回の裁定 R-1〜R-21 (監督、2026-09-16) により改訂した。v1.2 の判定のうち覆したものは本文の該当箇所に理由と日付を添えてある。

**目的**: 共有クラスタを指す既定値 `ADMIN_DSN_DEFAULT` を追跡 .py から消し、未設定を fail にする。subprocess と thread の uvicorn を予約済みソケットで起動し、nginx の bind 再試行を 3 回にする。設計 D-4・D-7、裁定 Q-8。基点は main `acb257e`。

**変更クラス**: **D**(監督裁定 W44-3-1)。機械判定の下限は C(`tools/change_class.py` は `conformance-tests/socket_harness.py` により `class=C`)。内容判定で D に上がる: 既定値の削除により、両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` から `("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "ADMIN_DSN_DEFAULT")` の行が消える。集合の減少は Class D である(`RM` §9 の 8 の表、`MRA` §6、`OPERATING_CONDITIONS` §1.5 の 40b)。`tools/change_class.py` はパスだけで判定するのでこの契機を検出しない(同ツール docstring の "Disclosed limitation")。

**依頼者裁定 (2026-09-16、逐語)**: 「R-21/R-28 と同じ形で D として進める (推奨)」。選択肢の本文 (逐語): 「Class D として扱い、この裁定を逐語で記録し、「契約 1.8.0 据え置き・Security Invariants と公開契約は不変・内容は開発基盤の変更である」ことを明記して 1 変更セットで閉じる。roadmap R-21/R-28 が既に使った discharge の形。設計レビュー 2 回 + 完了ゲート全部も掛ける。」

帰結: 契約版数は **1.8.0 据え置き**、`spec/` と `security/` は触らない。「版付きの security-contract 決定」は `RM` の R-21 / R-28 と同じ形で discharge する — すなわち **内容は開発基盤 (テスト用 PostgreSQL の分離) の変更であり security-contract の変更ではない**。この文を commit message にも書く。設計レビューは **2 回**(1 回目は本 manifest、2 回目は実装差分)。

**【追記 2026-09-16、R-12】** `RM` の R-21 / R-28 の D の契機は `security/` を触ったことであり、今回の契機は集合の減少である。集合の減少は同型性保証の弱体化ではない。登録対象 `ADMIN_DSN_DEFAULT` そのものが両 peer で同じ変更セットの中から消えるためであり、登録した helper を残したまま登録を外すのではない。`_admin_dsn` の 2 組は登録したまま残し、(c) で正規化後の一致を保つ。R-6 (登録済み同型 helper の本体) と R-20 (`.github/workflows/ci.yml` = B) を足しても最重クラスは **D** のままであり、引き上げは無い。

**読むべき正本**:

- `docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` の D-4・D-7、§2、§3.1・§3.2、§5、§6 の Q-8、§7、§8。
- 本作業指示書 §1(共通の枠)、§4(WP-3 の枠)、§4.1(WP-4 で直す積み残し)、§6(未確認)。
- `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 32〜40c、§1.7 の 52、§1.8 の 56・57、§1.9 の 60〜63、§1.10。
- `docs/design/ROADMAP_POST_PHASE7_V1.md` §9 の 8・9、§8 の R-44。
- `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §6(pair-closing change set)。

**道具**: テストの実行は `tools/dev/pt.py -C <担当 worktree> --wait 1800 -- <pytest args>`。変異は `tools/dev/mutate.py $SP/wp3-mutations.json -C <担当 worktree> --wait 1800`(spec は下の変異表と 1 対 1、`expect` は `red` / `green` / `error` の三値。§3.2 (d))。`tools/dev/gate.py` と `tools/dev/finalize.py` は実装担当が実行しない。

#### (a) 既定値の削除 (W44-3-2)

`ADMIN_DSN_DEFAULT = "host=/tmp port=5432 dbname=postgres"` を持つ追跡 .py は **23 ファイル**である(設計 §3.1 の 23 と一致)。内訳:

- MitateDB-api (10 件): `conformance/conformance_adapter_mitatedb_http.py`、`conformance/real_server_mitatedb.py`、`tests/control_plane_harness.py`、`tests/test_application_audit.py`、`tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`、`tests/test_constraints_declaration.py`、`tests/test_ops_upgrade.py`、`tests/test_ops_verify_declarations.py`、`tests/test_platform_upgrades.py`、`tests/test_postgres.py`
- r2db-api (13 件): `conformance/conformance_adapter_r2db_http.py`、`conformance/real_server_r2db.py`、`tests/test_application_audit.py`、`tests/test_audit_query.py`、`tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py`、`tests/test_control_plane_service.py`、`tests/test_control_plane_store.py`、`tests/test_credential_persistence.py`、`tests/test_ops_declarations.py`、`tests/test_ops_upgrade.py`、`tests/test_ops_verify_declarations.py`、`tests/test_postgres.py`、`tests/test_process_ceilings_declaration.py`

この 23 ファイルは、**`ADMIN_DSN_ENV` を module 先頭で定義する追跡 .py の集合と同じ**である(監督実測: `git ls-files '*.py' | xargs grep -ln '^ADMIN_DSN_ENV = ' | wc -l` = 23)。

23 ファイルすべてから定数 `ADMIN_DSN_DEFAULT` を削除する。読み手は次の 3 通りである。

1. 22 ファイルの `def _admin_dsn() -> str: return os.environ.get(ADMIN_DSN_ENV, ADMIN_DSN_DEFAULT)`。
2. うち 5 ファイルは本体の先頭に `import os` を挟む変種である(両 peer の `tests/test_ops_verify_declarations.py`、r2db の `tests/test_ops_declarations.py`・`tests/test_ops_upgrade.py`・`tests/test_process_ceilings_declaration.py`)。この `import os` は残す。
3. `MitateDB-api/tests/control_plane_harness.py` だけは名前が `admin_dsn()`(前置の `_` が無い、:42)。

いずれも、環境変数が **未設定または空文字**のときに例外を送出する形にする。既定値を別名で残す案・値だけ差し替える案は採らない(名前と中身が食い違う。依頼者裁定 2026-09-16 で選択肢として提示し、採られなかった)。例外の文言は `ADMIN_DSN_ENV` を参照する形にし、DSN リテラルを書かない(§1.9 の 60・61)。

- **完了条件 7〜9 は 1 テストの中で未設定と空文字の 2 つを assert する**(R-15)。表に現れない新規テストは作らない(完了条件 32)。
- 完了条件 9 の新規テスト(`MitateDB-api/tests/test_control_plane_postgres.py`)は、環境変数を `monkeypatch.delenv` で外して例外を確かめるだけの形にし、**PostgreSQL への接続を要しない**((d) と同じ趣旨)。同ファイルの他のテストは接続を要するので、新規分だけが独立していることを明示する。

`conformance-tests/test_c26_composition_root.py` は :336 と :472 で `os.environ.get(module.ADMIN_DSN_ENV, module.ADMIN_DSN_DEFAULT)` と、**他 module の属性として**読む。この 2 行も直す。このファイルはリテラルを持たないので上の 23 には含まれない。

同型性の表に登録された `_admin_dsn` 2 組(下の (c))は、**両 peer で本文が正規化後に一致する形**にする。

#### (b) fail メッセージ (W44-3-3)

1. 既定値リテラルを埋め込んだ fail メッセージは **2 件だけ**である: `r2db-api/tests/test_postgres.py:91`、`MitateDB-api/tests/test_postgres.py:100`(いずれも `_require_admin_connection()` の `pytest.fail` の中の "(e.g. 'host=/tmp port=5432 dbname=postgres' …)")。この 2 件から既定値リテラルを消す。置き換えの文には DSN リテラルを書かず、環境変数名と「`tools/testpg/dsa_testpg.py` が実行ごとに設定する」旨だけを書く(§1.9 の 60・61)。
2. 他のファイルの fail メッセージは `ADMIN_DSN_ENV={dsn!r}` の形で既定値リテラルを持たない。**【R-17、範囲外】** この形(`MitateDB-api/tests/test_control_plane_credential_store_reconciliation.py:132-133` ほか多数)は実行時の出力に DSN を出すが、§1.9 の 60・61 はファイルの内容を縛る規則であり、実行時のテスト出力は対象ではない。WP-3 の前から在り(いまは共有クラスタの DSN が出る)、WP-3 が作る問題ではない。**漏れではなく範囲外である。**
3. **【R-1】既定値でも fail メッセージでもない 3 行**: `MitateDB-api/tests/test_postgres.py:2586,2588,2593` の `PostgresCredentialStore("host=/tmp port=5432 dbname=postgres", ...)` は接続しない構築引数である。**allowlist を広げて逃がさない。** 設計 §3.1 が挙げる「意図的な到達不能値」の前例(`port=1` を使う 3 ファイル)と同じ形へ置き換える。r2db 側に対応する行は無いので同型性の表への影響は無い(監督確認)。

#### (c) 同型性の表 (`_ISOMORPHIC_TARGETS`)

両 peer の `tests/test_audit_query.py` に、この件に関わる行が 3 つある(r2db 側の行番号):

- L2628 `("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "_admin_dsn")`
- L2670 `("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "ADMIN_DSN_DEFAULT")`
- L2845 `("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_admin_dsn")`

表は各 peer のファイルの中に **3 箇所**現れる(表そのもの、full-content pin、row-count pin。r2db 側は L2628 付近 / L3066 付近)。`MRA` §6 により、表・full-content pin・row-count pin を **同じ pair-closing change set** に入れる。

- `ADMIN_DSN_DEFAULT` の行を、両 peer の 3 箇所すべてから消す。行数の pin は 137 → 136 になる。
- **W44-3-11(監督裁定 2026-09-16)**: 行数 pin のテスト名 `test_isomorphic_target_table_is_pinned_to_its_current_137_rows` を `..._136_rows` に改める。**監督実測: 両 peer それぞれ 3 箇所**、計 6 箇所である(r2db `tests/test_audit_query.py` L2405 / L2876 / L2951、MitateDB 同 L2202 / L2661 / L2736)。表の行・関数定義・full-content pin の写しの 3 つであり、`MRA` §6 の「表・full-content pin・row-count pin を同じ pair-closing change set に入れる」に正面から当たる。この pin テスト自身が表に登録された同型性の対象なので、3 箇所が食い違えば片側だけで解決できず赤になる。
- **【R-6】**`r2db-api/tests/test_audit_query.py:2858`・`:2859` に `("conformance/real_server_r2db.py", "conformance/real_server_mitatedb.py", "_best_effort_stop_processes")` と同 `"stop"` が登録済みである。(e) がこの 2 つの本体を変えるので、**(c) の対象に加える**。両 peer で正規化後に一致させる(完了条件 11)。`RM` §9 の 8 の C 行の契機でもある(クラスは既に D なので引き上げは無い)。
- `_admin_dsn` の 2 組は登録したまま残すので、(a) の書き換え後も両 peer で正規化後に一致させる。
- L2660 付近に、`ADMIN_DSN_DEFAULT` がなぜ登録されたかの経緯コメント(「after normalization but never added …」)がある。**この文は行の削除にあわせて書き換えるのではなく、削除の理由を日付付きで追記する**(§1.8 の 56)。MitateDB 側の同じコメントにも同じ追記をする。

#### (d) 再発防止の検査 (W44-3-4)

`tools/tests/` に 1 ファイル追加する(新規 `tools/tests/test_no_shared_cluster_defaults.py`)。検査は **本文検査**と**リテラルの走査**の 2 本立てである。

**(d-1) 本文検査 (R-2。WP-3 で最も重要な追加)**

現行案は「リテラルが無い」「名前が無い」しか見ない。1 ファイルで `os.environ.get(ADMIN_DSN_ENV, "")` と書けば、走査も同型性も suite もすべて緑のまま `psycopg.connect("")` が libpq 既定で共有クラスタへ落ちる。**設計 §2 の目標 1 と 5 が緑のまま破れる。** `T-scan` に次を足す。

- 追跡 .py のうち `ADMIN_DSN_ENV` を module 先頭で定義するものが **ちょうど 23 件**であること(件数を pin する。完了条件 5)。件数 pin を動かすときは、動かす変更セットが理由を書く。
- その 23 件すべてが、`ADMIN_DSN_ENV` を読む関数の中に **空判定と `raise`** を持つこと(完了条件 6)。判定は AST で行う(文字列の有無ではなく、その関数が実際に依存している性質を読む。§1.7 の 52)。

**(d-2) リテラルの走査 (R-9)**

前置き `host=/tmp port=5432` だけでは、実際にリポジトリの語彙に在る次の書き方をすり抜ける。走査を 3 種にする。

1. `host=/tmp`(port の有無を問わない)。
2. `postgresql://` で host 部が空・`localhost`・`127.0.0.1` のもの。
3. `dbname=` を含む DSN リテラルで、`host=` も URL の host も持たないもの(libpq 既定で共有クラスタへ届く形)。

**W44-3-8(監督裁定 2026-09-16)**: 走査するリテラルは前置きの `host=/tmp port=5432` とし、`dbname=postgres` まで含む完全一致にしない。理由: 共有クラスタを指すのは socket ディレクトリとポートの組であり、`dbname` は危険の構成要素ではない。前置きで走査すると allowlist の項目が自己検査の対象に入り、除外の陳腐化を同じテストで検出できる。R-9 の 1 はこの前置きをさらに緩め、port の有無を問わない形にしたものである。

**(d-3) 名前の走査 (R-13)**

`ADMIN_DSN_DEFAULT` という名前の再導入を赤にする。ただし (c) が残せと言う経緯コメントの本文に同じ名前が現れるので、走査は `^ADMIN_DSN_DEFAULT\s*[:=]` の **定義**に限る。テスト名もそれが分かる名前にする。

**(d-4) allowlist (R-3・R-9)**

除外は **理由付きの allowlist** とし、**各項目に期待出現数を持たせる**。`tools/dev/gate.py` はリテラルを 2 箇所(`:10`、`:97`)持つので、「ファイルがまだ持つ」だけの自己検査は片方を潰しても緑になる。

| ファイル | 期待出現数 | 理由 |
|---|---|---|
| `tools/dev/gate.py` | 2 | docstring の散文 (共有クラスタの説明)。接続先の既定値ではない |
| `tools/testpg/dsa_testpg.py` | 1 | 同上 |
| `tools/tests/test_no_shared_cluster_defaults.py` | — (固定しない) | 走査する側のリテラルそのもの。出現数の期待値が自己言及になるので、**このファイルはパスで除外し出現数を持たせない** (監督裁定 2026-09-16、起草者の指摘による) |

R-9 の 3 に当たる意図的な既存箇所も、設計 §3.1 の逐語を理由に引いて allowlist に入れる: `conformance-tests/test_testpg_cluster.py:96`(WP-1 が「host を書かない接続が実行のクラスタに届く」ことを確かめる本体)、`MitateDB-api/tests/test_control_credentials.py:244`・`:248`(設計 §3.1 が「現状は接続しない」と記す placeholder)。

**allowlist の各項目がいまも期待どおりの出現数を持つことを同じテストで確かめる**(陳腐化した除外を残さない)。走査した対象が 1 件以上あることも assert する(§1.5 の 32、空振り禁止)。

**(d-5) 限界 (R-9)**

文字列の連結・f-string・libpq の順不同(`port=5432 host=/tmp`)はこの静的走査では閉じない。既定値の再導入を止める主たる保証は (d-1) の本文検査(23 件すべてが未設定で raise すること)であり、リテラルの走査は副次である。D-4 の「再導入されない検査」を全称の主張として読まない。

**(d-6) 範囲と前提**

走査は追跡 .py に限る。`.md` と `MitateDB-api/migrations/0001_bootstrap_platform.sql` のリテラルは文書・移行の経緯であり範囲外である(migration の経緯コメントは checksum 対象。設計 §5「触らないもの」)。この検査は `tools/tests` の根(`tools/tests/pytest.ini`)の下に置くので、PostgreSQL を要求してはならない。

#### (e) 予約ソケット (W44-3-5、W44-3-9、W44-3-10、R-8)

**F-16 spike は監督が実施済みである**(2026-09-16、`uvicorn 0.52.4`、Python は `./.venv/bin/python`)。設計 D-7 と §8 の「uvicorn の `--fd` に TCP のソケットを渡したときの実際の挙動」の実測は次の 4 点である。

1. `socket.bind()`+`listen()` した親のソケットを `subprocess.Popen(..., pass_fds=(fd,))` と `python -m uvicorn <app> --fd <fd>` で子へ渡すと、子はそのソケットで **実際に serve する**(HTTP 401 を受け取った)。
2. 子から見える fd 番号は **親の `fileno()` と同じ**である(実測 `fd=3`)。`pass_fds` は番号を振り直さない。
3. 子が死んだ後、**親がまだ listening ソケットを持っている状態**で: 素の TCP `connect()` は **成功する**(kernel が親の backlog に入れる)。実際の HTTP GET は **1.00 秒で `TimeoutError`** になり、応答を得られない。
4. 親が自分の複製を閉じた後は `ConnectionRefusedError` になる。

帰結: `wait_until_ready` は素の TCP connect ではなく **本物の HTTP GET で status < 500 を要求する**ので、事前 listen したソケットを渡しても「起動失敗を期待する」試行の意味は **保たれる**。3 の 1 点目により、素の connect を成否の判定に使う経路を新設してはならない。

**W44-3-5 所有権**(設計 D-7 からの逸脱。監督裁定 2026-09-16): 設計 D-7 は「親は起動後に自分の複製を閉じる」と書くが、**採らない**。`start_uvicorn_subprocess(reserved=...)` は `--fd` + `pass_fds` で渡すだけとし、**予約の所有権は呼び出し側に残す**(`start_uvicorn_thread(reserved=...)` と同じ約束)。理由は 2 つある。

1. `real_server_*.py` の `restart_with_ceilings` は uvicorn を止めて **同じポートで** 起動し直す(nginx の conf が upstream ポートを固定しており、nginx は再読込しない)。親が複製を閉じると、その間にポートを奪われる隙が戻る。予約を surface の寿命の間持てば隙は消える。
2. `conformance-tests/test_c26_composition_root.py:347` は `launcher.stop()` の後に `not sh._port_has_listener(port)` を全ポートで要求する。呼び出し側が `stop()` で予約を閉じれば満たされ、閉じ忘れれば **既存のテストが赤くなる**。所有権を呼び出し側に置くことがこのテストで守られる。

**【註 2026-09-16、R-14】** 上の理由 1 の `restart_with_ceilings` の実体は `r2db-api/conformance/real_server_r2db.py:672` / `MitateDB-api/conformance/real_server_mitatedb.py:611` の `restart(self, *, ceilings=...)` である。以下の本文はこの名前を使う。

**【追記 2026-09-16、W44-3-9】** W44-3-5 の本文は据え置く。上の理由 1 は、launcher の upstream 起動経路を予約に移さないと実際には成り立たない(現行の `restart` は `port=<整数>` で同じポートに再 bind する)。監督裁定により **適用範囲を W44-3-7 の 6 経路から各 peer 7 件・計 14 件へ広げる**。

`reserve_port()` へ移す経路は **各 peer 7 件**(計 14 件)である。

- start: `real_server_r2db.py:631` / `:636`、`real_server_mitatedb.py:570` / `:575`(data / control の upstream)
- restart (`restart(*, ceilings=...)`): `real_server_r2db.py:702` / `:707`、`real_server_mitatedb.py:632` / `:637`
- F-15: `real_server_r2db.py:821` / `real_server_mitatedb.py:733`(blocking `subprocess.run`)
- F-16 lowered: `real_server_r2db.py:906` / `real_server_mitatedb.py:814`(blocking `subprocess.run`)
- F-16 restored: `real_server_r2db.py:921` / `real_server_mitatedb.py:829`

**launcher は data / control の 2 つの予約を surface の寿命の間保持し、自分の `stop()` で閉じる。** start と restart の両方で同じ予約を `reserved=` で渡す。これで restart の隙が実際に消え、W44-3-5 の理由 1 が成り立つ。`port=<整数>` で同じポートに再 bind する現行の経路は使わなくなる。

F-15 / F-16 の blocking な `subprocess.run` の経路は `returncode != 0` と stderr の "F-15" / "F-16" を見るので、予約にしても意味は変わらない — 変わるのは **bind 競争に負けて別の理由で落ちる偽陰性が消える**ことである。この 4 経路(各 peer 2 件)と F-16 restored では、`--port` を `--fd` に替え、`pass_fds` で予約のソケットを渡し、`finally` で呼び出し側が予約を閉じる。

**W44-3-10 `start_uvicorn_subprocess` の署名**(監督裁定 2026-09-16):

- `reserved: Optional[ReservedPort] = None` を足す。
- `reserved` が渡されたとき: `--fd <reserved のソケットの fileno()>` と `pass_fds` で子へ渡す。**予約の所有権は呼び出し側に残り、`UvicornSubprocessHandle.stop()` は閉じない**(`start_uvicorn_thread(reserved=...)` と同じ約束)。
- `reserved` が省かれたとき: **関数自身が `reserve_port()` を呼び**、同じ形で渡す。この予約は **handle が所有し、`stop()` で閉じる**。
- **`port: Optional[int]` 引数は削除する。** 裁定の理由: W44-3-9 の後、リポジトリ内にこの引数の利用者は 1 件も残らず、残せば「予約を伴わずに番号だけで再 bind する」競合のある経路を将来また選べてしまう。削除の理由を docstring に 1 行残す。

**【R-8、範囲を広げる】`start_uvicorn_thread()` の既定経路も WP-3 で直す**: 設計 §3.2 が要対策に名指しした経路であり、`RealSocketSurface`(`socket_harness.py:960`・`:968`)という **最頻経路**である。ここを残すと R-44 の目的がいちばん通る道で達成されない。W44-3-10 と同じ形にする。

- `start_uvicorn_thread` の `reserved` が省かれたとき、**関数自身が `reserve_port()` を呼ぶ**(現行は `free_port()`)。
- thread 版では uvicorn 自身が `Server.run(sockets=[...])` のソケットを shutdown 時に閉じるので、**handle は二重に閉じない**(close は冪等にする)。この点を docstring に 1 行残す。
- `free_port()` 自体は残す(`conformance-tests/test_socket_harness.py:1134` の健全性テスト)。

#### (f) nginx の bind 再試行 (W44-3-6、裁定 Q-8)

- 試行を **3 回** にし、失敗した試行ごとに `error.log` を残す(上書きしない)。現行は各試行の先頭で `error_log.write_text("")` により前の試行の内容が消えるので、消す前に試行番号の分かる名前で `prefix` の中へ退避し、3 回目の失敗で送出する `HarnessStartupError` に全試行分を添える。
- `socket_harness.py` の `start_nginx_with_bind_retry` の docstring にある 2026-09-08 の裁定「EXACTLY ONCE」の文は **書き換えず**、直後に日付付きの註で「R-44 Q-8(依頼者裁定 2026-09-16)により 3 回へ改めた」と残す(§1.8 の 56・57)。
- 既存テスト `conformance-tests/test_socket_harness.py::test_start_nginx_with_bind_retry_moves_to_a_different_port_when_the_first_bind_fails` の `assert call_count["n"] == 2, "exactly one retry"` は新しい裁定に合わせて直し、**3 回使い切って失敗する経路のテストを 1 本足す**。このテストの docstring の 2026-09-08 の文も書き換えず、日付付きの註を添える(§1.8 の 56)。
- **【R-7、範囲は広げない】** 再試行が掛かるのは `start_nginx_with_bind_retry` の 1 経路だけである。他の 4 経路(`r2db-api/conformance/real_server_r2db.py:656`、`MitateDB-api/conformance/real_server_mitatedb.py:595`、`r2db-api/conformance/conformance_adapter_r2db_socket.py:289`、`MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py:222`)は listen ポートを宣言済み URL に焼いてから起動するので、別ポートでの再試行には `declare-surfaces` のやり直しが要る。WP-3 の範囲外とする。**行き先は §4.1 の積み残しに書いた(先送りではなく、行き先を明示した送りである)。**

#### (g) 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| (a) の 23 ファイル、`conformance-tests/test_c26_composition_root.py`、両 peer の `tests/test_audit_query.py`、`conformance-tests/socket_harness.py`、`conformance-tests/test_socket_harness.py`、`r2db-api/conformance/real_server_r2db.py`、`MitateDB-api/conformance/real_server_mitatedb.py`、`MitateDB-api/tests/test_control_plane_postgres.py`(`admin_dsn()` の新規テストの置き場)、新規 `tools/tests/test_no_shared_cluster_defaults.py`、`.github/workflows/ci.yml`(**R-20。範囲は `:78-79` のコメント 1 件のみ**。本文を書き換えず日付付きの註として「R-44 WP-3 により既定値は無くなり、未設定は fail になる」を残す。**CI の挙動 (env の値、job の構成) は 1 文字も変えない。** 正式な改訂は WP-4) | `socket_harness.free_port()` 自身(`test_socket_harness.py:1134` の健全性テストは現行のまま)、**意図的な到達不能値 `port=1` を使う箇所**(R-18。`r2db-api/tests/test_surfaces_env.py:260`、`r2db-api/tests/test_control_http.py:714`、`MitateDB-api/tests/test_http.py:275`、両 peer の `tests/test_ops_verify_declarations.py:427`・`:461`、`r2db-api/conformance/conformance_adapter_r2db_http.py:121`、`r2db-api/tests/test_audit_query.py:51`。走査に当たらず意図どおり範囲外。巻き込み削除の事故を防ぐために明記する)、`spec/` と `security/`(契約 1.8.0 据え置き)、`tools/dev/` と `tools/testpg/`(WP-2 で閉じた)、3 つの `conftest.py` と `tools/tests/pytest.ini`(WP-1)、`docs/work-orders/OPERATING_CONDITIONS.md`・README 類(WP-4)、`MitateDB-api/migrations/0001_bootstrap_platform.sql`(移行の経緯コメント、checksum 対象)、`.md` の既定値リテラル(WP-4)、`conformance-tests/COLLECTION_FLOOR`(監督が完了ゲートで更新)、`docs/design/TEST_POSTGRES_ISOLATION_V0_1.md`(監督が記録を追記)、R-37 WP-4b〜4d の対象ファイル((k) を見る) |

#### (h) 完了条件 → 変異 → 赤になるテスト (予想)

新規テストの略記: `T-scan` = `tools/tests/test_no_shared_cluster_defaults.py`、`T-sock` = `conformance-tests/test_socket_harness.py`、`T-c26` = `conformance-tests/test_c26_composition_root.py`。

完了条件は **33 件**、うち変異を持つものが **29 件**、監査照合が **4 件**(29〜32)である。**【追記 2026-09-16、コードレビュー 1 回目の後】** 完了条件 33 を末尾に足した (§4.4 の (b))。

**「赤になるテスト」の欄は予想である。実装担当が実測で埋め、予想と実測が食い違ったら報告に書く(§1.5 の 34、R-21)。**

| # | 完了条件 | 変異 (`file:操作`) | 期待 | 赤になるテスト (予想。実測で改める) |
|---|---|---|---|---|
| 1 | 追跡 .py に共有クラスタへ届くリテラルが残らない(3 種の走査。allowlist を除く) | `r2db-api/tests/test_postgres.py`: (b) の置き換え後の文に `host=/tmp port=5432 dbname=postgres` を戻す | red | `T-scan::test_no_tracked_py_carries_a_shared_cluster_dsn_literal` |
| 2 | `ADMIN_DSN_DEFAULT` の **定義**が再導入されない(R-13) | `r2db-api/tests/test_postgres.py`: `ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"` を同じ行 + 改行 + `ADMIN_DSN_DEFAULT = ADMIN_DSN_ENV` に置き換える | red | `T-scan::test_no_tracked_py_defines_admin_dsn_default` |
| 3 | allowlist の各項目がいまも期待出現数を持つ(R-3) | `tools/dev/gate.py`: :10 の散文の中の `host=/tmp port=5432` を `共有クラスタ` に置き換える(出現数が 2 → 1 になる) | red | `T-scan::test_allowlist_entries_still_carry_their_expected_counts` |
| 4 | リテラルの走査が空振りしない | `T-scan`: 走査対象の収集の `'*.py'` を `'*.nosuchsuffix'` に置き換える | red | `T-scan::test_scan_covers_at_least_one_file` |
| 5 | `ADMIN_DSN_ENV` を module 先頭で定義する追跡 .py がちょうど 23 件である(R-2) | `conformance-tests/test_c26_composition_root.py`: module 先頭に `ADMIN_DSN_ENV = "R2DB_TEST_ADMIN_DSN"` の 1 行を足す(24 件になる) | red | `T-scan::test_admin_dsn_env_definitions_are_pinned_to_23_files` |
| 6 | 23 件すべてが、`ADMIN_DSN_ENV` を読む関数の中に空判定と `raise` を持つ(AST、R-2) | `r2db-api/tests/test_ops_upgrade.py`: `_admin_dsn()` の `raise` の文を `return dsn` に置き換える | red | `T-scan::test_every_admin_dsn_reader_raises_when_the_environment_variable_is_unset` |
| 7 | 未設定・空文字で `_admin_dsn()` が例外(r2db) | `r2db-api/tests/test_postgres.py`: `_admin_dsn()` の `if not dsn:` を `if False:` に置き換える | red | `r2db-api/tests/test_postgres.py::test_admin_dsn_requires_the_environment_variable` |
| 8 | 未設定・空文字で `_admin_dsn()` が例外(MitateDB) | `MitateDB-api/tests/test_postgres.py`: 同じ置き換え | red | `MitateDB-api/tests/test_postgres.py::test_admin_dsn_requires_the_environment_variable` |
| 9 | 未設定・空文字で `control_plane_harness.admin_dsn()` が例外 | `MitateDB-api/tests/control_plane_harness.py`: `admin_dsn()` の `if not dsn:` を `if False:` に置き換える | red | `MitateDB-api/tests/test_control_plane_postgres.py::test_admin_dsn_requires_the_environment_variable` |
| 10 | 両 peer の `_admin_dsn` が正規化後に一致する | `MitateDB-api/tests/test_ops_verify_declarations.py`: `_admin_dsn()` の例外型を片側だけ変える(`RuntimeError(` → `AssertionError(`) | red | 両 peer の `tests/test_audit_query.py::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` |
| 11 | 両 peer の `stop` / `_best_effort_stop_processes` が正規化後に一致する(R-6) | `MitateDB-api/conformance/real_server_mitatedb.py`: `stop()` の中で予約を閉じる順序を片側だけ変える | red | 同上 |
| 12 | 表と full-content pin から `ADMIN_DSN_DEFAULT` の行が消える | 両 peer の `tests/test_audit_query.py`(`edits` 2 件): full-content pin に `("tests/test_ops_verify_declarations.py", "tests/test_ops_verify_declarations.py", "ADMIN_DSN_DEFAULT"),` の 1 行を戻す | red | 両 peer の `::test_isomorphic_target_table_is_pinned_to_its_current_136_rows` |
| 13 | 行数の pin が 136 である | 両 peer の `tests/test_audit_query.py`(`edits` 2 件): `assert len(_ISOMORPHIC_TARGETS) == 136` を `== 137` に置き換える | red | 同上 |
| 14 | pin テストの名前が両 peer の 3 箇所すべてで `..._136_rows` に揃う(W44-3-11) | 両 peer の `tests/test_audit_query.py`(`edits` 2 件): 表の行(r2db L2405 / MitateDB L2202 に当たる行)の名前だけを `..._137_rows` に戻す | red | 両 peer の `::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` と `::test_isomorphic_target_table_is_pinned_to_its_current_136_rows` |
| 15 | `T-c26` が既定値の属性を読まない | `conformance-tests/test_c26_composition_root.py`: :336 に当たる置き換え後の行を `os.environ.get(module.ADMIN_DSN_ENV, module.ADMIN_DSN_DEFAULT)` に戻す(アンカーは前後の行を含めて一意にする) | red | `T-c26`(テスト本体の `AttributeError`) |
| 16 | 既定経路の subprocess が予約済みソケットで serve する | `conformance-tests/socket_harness.py`: `start_uvicorn_subprocess` の argv の `"--fd", str(<予約の fileno>)` を `"--port", str(<予約の port>)` に置き換える | red | `T-sock::test_uvicorn_subprocess_serves_on_the_reserved_socket` |
| 17 | `reserved=` で渡した予約を関数も handle も閉じない(W44-3-10) | `conformance-tests/socket_harness.py`: `start_uvicorn_subprocess` の所有権の判定(`reserved is None`)を `True` に置き換える | red | `T-sock::test_start_uvicorn_subprocess_never_closes_a_caller_supplied_reservation` |
| 18 | 既定経路の予約は handle が `stop()` で閉じる(W44-3-10) | `conformance-tests/socket_harness.py`: 同じ判定を `False` に置き換える | red | `T-c26`(:347 の `_port_has_listener`)、`T-sock::test_uvicorn_subprocess_releases_its_own_reservation_on_stop` |
| 19 | `start_uvicorn_subprocess` に `port: Optional[int]` 引数が無い(W44-3-10) | `conformance-tests/socket_harness.py`: 署名の `reserved: Optional[ReservedPort] = None,` を同じ行 + `port: Optional[int] = None,` に置き換える | red | `T-sock::test_start_uvicorn_subprocess_has_no_port_argument`(署名の pin) |
| 20 | `start_uvicorn_thread` の既定経路が `reserve_port()` を使い、close は冪等である(R-8) | `conformance-tests/socket_harness.py`: `start_uvicorn_thread` の既定経路の `reserve_port()` を `free_port()` に戻す | red | `T-sock::test_start_uvicorn_thread_serves_on_a_port_it_reserved_itself` |
| 21 | launcher は data / control の予約を surface の寿命の間保持し、start と restart の両方で同じ予約を渡す(W44-3-9) | 両 `real_server_*.py`(`edits` 2 件): restart 経路の `reserved=<保持した予約>` を `reserved=sh.reserve_port()` に置き換える | red | `T-c26::test_c26_ceiling_maps_to_limit_enforcement`(restart 後の upstream ポートが nginx の conf と食い違い `wait_until_ready` が失敗する) |
| 22 | launcher は自分の `stop()` で 2 つの予約を閉じる(W44-3-9) | 両 `real_server_*.py`(`edits` 2 件): `stop()` の予約を閉じる行を `pass` に置き換える | red | `T-c26::test_c26_no_residue_after_shutdown`(:347 の `_port_has_listener`) |
| 23 | F-15 / F-16 の各経路が組み立てた argv に `--fd` があり、`pass_fds` が予約のソケットの `fileno()` を含む(R-19) | `r2db-api/conformance/real_server_r2db.py`: F-16 lowered の argv の `"--fd"` を `"--port"` に置き換える | red | `T-sock::test_f15_and_f16_paths_hand_their_reserved_socket_to_uvicorn`(`subprocess.run` / `subprocess.Popen` を monkeypatch して argv と `pass_fds` を読む) |
| 24 | `_capturing_reserve_port` が全予約を記録し、件数を assert し、nginx の listen ポートを名指しで検査する(R-5) | `conformance-tests/test_c26_composition_root.py`: 予約の記録を list への追加から最後の 1 件の上書きに戻す | red | `T-c26::test_c26_start_failure_leaves_no_residue` |
| 25 | nginx は 3 回目の試行まで行う | `conformance-tests/socket_harness.py`: `for attempt in (1, 2, 3):` を `for attempt in (1, 2):` に置き換える | red | `T-sock::test_start_nginx_with_bind_retry_succeeds_on_the_third_port` |
| 26 | 4 回目の試行は無い(3 回で `HarnessStartupError`) | `conformance-tests/socket_harness.py`: `for attempt in (1, 2, 3):` を `for attempt in (1, 2, 3, 4):` に置き換える | red | `T-sock::test_start_nginx_with_bind_retry_gives_up_after_three_attempts` |
| 27 | 失敗した試行の `error.log` が上書きされずに残る | `conformance-tests/socket_harness.py`: 退避の行を `pass` に置き換える | red | `T-sock::test_failed_nginx_attempts_keep_their_error_logs` |
| 28 | (b) 3 の 3 行が意図的な到達不能値の形になる(R-1) | `MitateDB-api/tests/test_postgres.py`: 置き換え後の 3 行のうち 1 行を `"host=/tmp port=5432 dbname=postgres"` に戻す | red | `T-scan::test_no_tracked_py_carries_a_shared_cluster_dsn_literal` |
| 29 | 覆した判定の旧文を消さずに註を足した(3 箇所) | **監査照合**(変異なし) | — | — |
| 30 | Class D の discharge 文言が manifest と commit message にある | **監査照合**(変異なし) | — | — |
| 31 | suite を 2 本並列に 3 回走らせ、毎回両方の集計行が一致する(R-11) | **監査照合**(変異なし) | — | — |
| 32 | 上の 1〜31 のすべてに変異または監査照合が対応し、対応の無い行が無い。表に現れない新規テストを作らない(R-15) | **監査照合**(変異なし) | — | — |
| 33 | `start_uvicorn_subprocess` / `start_uvicorn_thread` の例外経路で、自分が採番した予約を閉じてから送出する(§4.4 の (b)) | `conformance-tests/socket_harness.py`: 例外経路の `close()` を `pass` に置き換える | red | `T-sock`(例外経路の新規テスト。実測で埋める) |

**変異のアンカーの一意性 (R-4)**

> 変異のアンカーは、実装後の本文で **一意であることを実装担当が `grep -c` で確かめてから** spec に書く。
> 一意にできない文字列は、前後の行を含めて一意にするか `edits` を 2 件に分ける。
> 一意性の確認結果 (ファイルと出現数) を実装報告に添える。

この規則は変異 10・14・15・17・18 に強く掛かる。とくに `conformance-tests/test_c26_composition_root.py:336` と `:472` は現状バイト単位で同一であり、修正後も同一になる見込みである。`mutate.py` は exactly-once を要求するので、行だけをアンカーにすると exit 78 になる。

**監査照合の手順**(変異で表現できない完了条件。§2.6 (a) と同じ形):

- **29**: 対象は 3 箇所である。(i) `conformance-tests/socket_harness.py` の `start_nginx_with_bind_retry` の docstring の「EXACTLY ONCE」/「1 回だけ」の文、(ii) 同じ趣旨を書く `T-sock` の既存テストの docstring、(iii) 両 peer の `tests/test_audit_query.py` の `ADMIN_DSN_DEFAULT` 登録の経緯コメント(r2db 側 L2660 付近)。手順: 監督が `git diff acb257e -- <各ファイル>` を取り、(i)〜(iii) の旧文の行が削除側にも書き換え側にも現れず、直後に日付付きの註が **追加**されていることだけを確認する。追加した註の逐語と、確認した diff の該当行を `docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` の WP-3 の記録に残す。
- **30**: 監督が本 §4.2 の「変更クラス」の段落と、commit 直前の commit message の下書きを並べ、依頼者裁定の逐語と「内容は開発基盤の変更であり security-contract の変更ではない」の文が両方にあることを確認する。確認した逐語を同じ設計文書の WP-3 の記録に残す。
- **31 (R-11)**: gate は排他ロックを取るので **gate を 2 本並列に走らせるのではない**。比較の対象は **通常の実行 2 本どうしの集計行**である。完了ゲートの **後**に、監督が 2 つの worktree で `tools/dev/pt.py -C <worktree> --wait 1800 -- -q -n 5 --dist loadgroup` を同時に開始する。これを 3 回。毎回、2 本の集計行が互いに一致することを確かめる。6 行を実装報告に verbatim で貼り、同じ設計文書の WP-3 の記録に残す。2 本目の worktree は監督が実測時に作る。
- **32 (R-16)**: 監督が本表の 1〜33 を上から読み、変異の列が空の行が 29〜32 の 4 行だけであり、その 4 行に監査照合の手順があること、および WP-3 が足した新規テストが全て本表のいずれかの行に現れることを確認する。確認した結果を同じ設計文書の WP-3 の記録に残す(報告 1 行では足りない。§1.5 の 40)。

#### (i) 完了ゲート

- 完了ゲートは監督が `tools/dev/gate.py` で単独実行する。**基点 `acb257e` の実測**は root suite が `3422 passed, 2 subtests passed`、`tools/tests` が 486 である。基準はこれに WP-3 の新規テスト数を足した値。
- 見積り(レビュー 2 の機械的な見積り): `testpaths` 内 **+11 → `3433`**、`tools/tests` **+4 → `490`**。R-2・R-5・R-6・R-8・R-11 で完了条件が増えるので、**見積りは実装時に改める。正本は完了ゲートの実測である。**
- 実行クラスタの前後差分は 0、共有クラスタは `info=` 行として読む(Q-3)。
- `conformance-tests/COLLECTION_FLOOR` は監督が完了ゲートで更新する。
- **【R-12】** CI (3.11 job) の集計行は push 停止中のため取れない。**§6 (未確認) へ送る**(WP-1 が §2.3・§6 で同じ扱いをした)。性能差分は裁定 Q-9 により WP-4 で取り直すので WP-3 では添えない。

#### (j) 設計 §7 の完了条件の分担

**WP-3 で満たす項目**(3 件)

1. 「専用クラスタ上の完了ゲートの集計行が、直前の main の集計行と一致する」 — WP-3 の完了ゲートで満たす。WP-3 は新規テストを足すので、一致の基準は (i) のとおり「直前の main + 新規テスト数」である。全 WP を通した最終の記録は WP-4。
2. 「実行のクラスタの前後差分が 0 で、共有クラスタに変化が無い」 — WP-3 の完了ゲートで満たす。実行クラスタの差分 0 は gate の判定、共有クラスタは Q-3 の裁定により `info=` 行で 0 を読む(判定には使わない)。
3. 「suite を 2 本並列に 3 回走らせ、毎回両方の集計行が一致する」 — 実測は WP-2 で行われなかった(引き継ぎ書 `docs/work-orders/HANDOVER_20260916_R44_FABLE.md` §3 の 3)。**監督裁定 W44-3-12(2026-09-16)**により WP-3 の完了ゲートの後に監督が実測する。WP-3 が待ち受けポートの扱いを変えるので、並列実行が最も強く当たる WP である。手順と記録先は完了条件 31 のとおり。記録は §5 の枠のとおり WP-4。

**WP-4 に残る項目**(2 件)

4. 「次の起動の形でもそれぞれ専用クラスタが使われる: `pytest`、`pytest r2db-api/tests/...`、`cd MitateDB-api && pytest tests/`、`--collect-only`、`tools/check_collection_floor.py`」 — 仕組みは WP-1 が入れた。5 種を通した確認と記録は §5 の枠のとおり WP-4。
5. 「`pytest tools/tests` がクラスタを起動しない」 — WP-1 で満たし、§2.6 (a-1) の監査照合で確かめてある。記録は §5 の枠のとおり WP-4。WP-3 は `tools/tests` に 1 ファイル足すので、そのファイルが PostgreSQL を要求しないことだけを守る((d-6))。

#### (k) 並行作業

R-37 WP-4b〜4d(セッション `cranky-curie-ac6645-18`)との触るファイルの重なりは **0** である(監督実測 + 相手セッションの回答 2026-09-16)。相手の manifest(`docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.42〜§5.44)は 3 件とも `r2db-api/tests/test_postgres.py` と `r2db-api/tests/test_audit_query.py` を「触らないファイル」に明記しており、`_ISOMORPHIC_TARGETS` は 3 件とも差分 0 を完了条件にしている。唯一の含み: 位置参照の走査で `r2db-api/tests/test_postgres.py` に括弧書き 1 箇所が要る可能性があり、その場合は相手が着手前に連絡する。連絡があれば実装担当は監督に上げ、自分では調整しない。

### 4.3 WP-3 の訂正註 (2026-09-16、実装中。§4.2 の本文は書き換えない)

- **(a) (d-2) の 1 と R-18 の食い違いの裁定 (監督裁定 W44-3-13)。** (d-2) の 1 は走査を `host=/tmp` (port の有無を問わない) に広げたが、(g) は R-18 の「意図的な到達不能値は走査に当たらず範囲外」と書いており、文面上は両立しない。実装担当の申告により監督が裁定する。**`host=/tmp` の直後が `port=1` (単語境界) のときだけ除外する形を採る。** 理由は 2 つある。(i) 危険は「共有クラスタに届くこと」であり、`port=1` は socket ファイル `.s.PGSQL.1` が存在しないので届かない。除外はファイル名の allowlist ではなく、**その分岐が実際に依存している性質そのもの**を読む形になる (§1.7 の 52)。(ii) 監督実測 (2026-09-16、worktree `r44-wp3`) により、リポジトリ内の意図的な到達不能値は **11 箇所すべてが `host=/tmp port=1 dbname=<説明的な名前>` の形**で揃っている (`MitateDB-api/tests/test_application_audit.py:619`・`:624`、`MitateDB-api/tests/test_http.py:275`、両 peer の `tests/test_ops_verify_declarations.py:467`・`:433`、`MitateDB-api/tests/test_postgres.py:2605`・`:2607`・`:2612`、`r2db-api/conformance/conformance_adapter_r2db_http.py:121`、`r2db-api/tests/test_audit_query.py:51`、`r2db-api/tests/test_control_http.py:714`、`r2db-api/tests/test_surfaces_env.py:260`)。ファイル名の allowlist にすると 11 件が陳腐化の対象になる。採らなかった案: 一般規定どおり port を問わず一致させ、11 件を allowlist に足す。

- **(b) §4.2 (b) の 3 項の対象が 2 行足りなかった (監督が追認)。** (b) の 3 項は `MitateDB-api/tests/test_postgres.py` の 3 行だけを挙げていたが、`MitateDB-api/tests/test_application_audit.py` の `PostgresApplicationAuditSink("host=/tmp dbname=...", ...)` 2 行 (現 `:619`・`:624`) も (d-2) の 1 の真陽性である。設計レビュー 2 回目の M-1 の (i) が予告していた形である。同ファイルは (a) の 23 ファイルの 1 つで触ってよいので、実装担当が既存の `port=1` の慣行へ書き換えた。監督が追認する。

- **(c) (d-2) の 3 の偽陽性を 2 条件で絞った (監督が追認)。** 「`dbname=` を含み `host=` も URL の host も持たない DSN リテラル」を文字どおり実装すると、f-string の断片 (`tools/testpg/dsa_testpg.py`、`tools/tests/test_testpg.py`) と、SI-10 の leak-scan が使う裸のトークン `"dbname="` (`r2db-api/tests/test_l5_si10_details_leak_scan.py`、`MitateDB-api/tests/test_denial_details_and_request_id.py`) に当たる。実装担当が (i) `dbname=` の直後に 1 文字以上を要求する、(ii) 3 は f-string の断片には適用しない (1 と 2 は適用する)、の 2 条件を足した。**絞り込みの理由は検査ファイル自身の docstring ((d-5) の限界の記述) に残す。**

- **(d) allowlist は実測 4 件になった (監督が追認)。** (d-4) の表の 2 件 (`tools/dev/gate.py` = 2、`tools/testpg/dsa_testpg.py` = 1) に加え、(d-2) の 3 に当たる意図的な既存箇所として `conformance-tests/test_testpg_cluster.py` と `MitateDB-api/tests/test_control_credentials.py` が入る。**`conformance-tests/test_testpg_cluster.py` の実測は 2 件**であり、(d-4) が挙げた `:96` の 1 箇所だけではない (もう 1 件は f-string の実行スクリプトの中)。**実測を正とする。**

### 4.4 WP-3 のコードレビュー 1 回目の裁定 (2026-09-16。§4.2・§4.3 の本文は書き換えない)

独立コードレビュー 1 回目 (Class D。MAJOR 1 / MINOR 4 / 改善案 2) に監督が裁定を出した。差し戻しの正本は
$SP の `wp3-rework-1.md` (非追跡) であり、本節はその結論だけを残す。

- **(a) 完了条件 29 の監査対象は 3 箇所ではなく 5 箇所である (監督裁定)。** §4.2 (h) の 29 は (i) `start_nginx_with_bind_retry` の docstring、(ii) `T-sock` の既存テストの docstring、(iii) 両 peer の `tests/test_audit_query.py` の経緯コメント の 3 つを挙げていたが、実装で註を足した箇所は 5 つになった。加わるのは (iv) `conformance-tests/socket_harness.py` の module docstring (h) の項 (実装担当が同一ファイル内の重複記述の整合のために追記。監督が追認)、(v) 同ファイルの `RealSocketSurface._start` の呼び出し元コメント (`:1085-1089`。レビュー MAJOR-1。旧文「exactly ONE retry」が無註で残り、参照先の docstring の「3 回」と矛盾していた) である。29 の監査手順はこの 5 箇所に掛ける。

- **(b) 完了条件 33 を足した (監督裁定)。** `start_uvicorn_subprocess` (`:774-793`) と `start_uvicorn_thread` (`:679-694`) は、`reserve_port()` で採番した直後の `subprocess.Popen` / `pidfile.write_text` / `uvicorn.Config` / `thread.start()` が送出すると、handle が返らないので**自分が採番した予約を閉じる先が無い**。消えた tmpdir 配下の `pidfile` で `FileNotFoundError` が出ると、そのポートが process の寿命の間 listen し続け、後続の `_port_has_listener` による残渣検査が持ち主不明の listener を見る。R-44 が常態化させる並列 2 本では、もう一方の実行の残渣検査にも当たる。採番から `return` までを `try` で囲み、`except BaseException:` で自分の予約だけを閉じてから `raise` する。変異 1 件を対応させる。

- **(c) W44-3-14 (監督裁定 2026-09-16)。** `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py:186-188` の「`start_uvicorn_thread` 自身の `free_port()` fallback」の記述は、R-8 (既定経路の `reserve_port()` 化) により偽になる。同ファイルは §4.2 (g) の触るファイル一覧に無いが、**`.github/workflows/ci.yml` のコメントを WP-3 で直したのと同じ理由 — WP-3 の統合と同時に偽になる文は WP-3 が直す — により、このコメント 1 件だけを直す。** 素の `start_nginx()` 直呼び (再試行 0 回) は §4.1 の積み残しのままであり、触らない。r2db 側に対応する文が無いので同型性テストでは捕まらない (実装担当が `grep` で確かめて報告する)。

- **(d) `_assert_last_call_uses_fd` を順序依存から外す (監督裁定)。** レビューの判定は「順序依存だが脆くはない」だったが、「最後の `subprocess.run` が uvicorn である」は、その分岐が実際に依存している性質 (「uvicorn を `--fd` で起動した」) の**代理**である (§1.7 の 52)。`"uvicorn" in argv` で絞って `len == 1` を assert する形へ直す。

- **(e) 監督が追認したもの (直さない)。** `NGINX_BIND_MAX_ATTEMPTS` の新設 (レビューが挙動不変を確認。完了条件 26 を意味のあるものにするために必須)、予約の close を `_best_effort_stop_processes()` に置いたこと (唯一の呼び出し元が `stop()`。検査は GC 任せではないとレビューが判定)、完了条件 23 を両 peer のパラメータ化 1 本にしたこと。

- **(f) `tools/tests/test_no_shared_cluster_defaults.py` の実測は追跡後に取り直す (レビュー MINOR-5)。** 同ファイルは未追跡のうちは `git ls-files` に載らず、allowlist の自己参照項目が死んでいる。**監督は完了ゲートの前に同ファイルを `git add` し、追跡された状態で `tools/tests` を回した集計行を正本とする。**

- **(g) §4.2 (h) の 18 行の「赤になるテスト」欄は予想が外れた (§1.5 の 34)。** C-26 の実 launcher は `reserved=` を常に明示で渡すので既定オウン経路を通らず、`T-c26` は無関係である。実測では `T-sock::test_uvicorn_subprocess_releases_its_own_reservation_on_stop` の 1 本だけが赤になる。予想欄は本註で訂正し、表の本文は書き換えない (§1.8 の 57)。

## 5. WP-4 — 規律・文書・CI の改訂 (枠)

- 設計 §5 の一覧を改訂する。TimeZone を CI にも明示し (Q-6)、superuser 名は既に `postgres` で揃う (Q-7)。
- 性能の基準値を専用クラスタで取り直す (Q-9)。
- 設計 §7 の完了条件 (起動の形 5 種、`tools/tests`、並列 2 本 × 3 回) を満たしたことを記録する。

## 6. 未確認 (push 停止中)

- CI の `conformance` job で `postgresql-16` のバイナリと `LC_ALL=en_US.UTF-8` が使えること、`tools-tests` job が `tools/tests/pytest.ini` の下で通ること。push の再開後に最初の run で確かめる。
