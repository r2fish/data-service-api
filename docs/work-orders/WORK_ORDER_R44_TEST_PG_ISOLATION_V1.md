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

## 5. WP-4 — 規律・文書・CI の改訂 (枠)

- 設計 §5 の一覧を改訂する。TimeZone を CI にも明示し (Q-6)、superuser 名は既に `postgres` で揃う (Q-7)。
- 性能の基準値を専用クラスタで取り直す (Q-9)。
- 設計 §7 の完了条件 (起動の形 5 種、`tools/tests`、並列 2 本 × 3 回) を満たしたことを記録する。

## 6. 未確認 (push 停止中)

- CI の `conformance` job で `postgresql-16` のバイナリと `LC_ALL=en_US.UTF-8` が使えること、`tools-tests` job が `tools/tests/pytest.ini` の下で通ること。push の再開後に最初の run で確かめる。
