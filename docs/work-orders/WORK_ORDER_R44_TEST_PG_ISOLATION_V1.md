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

## 3. WP-2 — 道具 (枠。着手時に manifest を追記する)

- `tools/dev/gate.py`: `dsa_testpg.cluster()` でクラスタを起動し、`DSA_TEST_PG=external` と `Cluster.env()` で pytest を実行する。`pg_database` / `pg_roles` の前後比較はそのクラスタで停止前に行い、FAIL の判定に使う。共有クラスタの前後比較は情報表示だけにする (Q-3)。
- 排他 (Q-2 の (a)): `dsa_testpg` に lock を置く。gate は着手の印を置いて排他 lock を取り、`ensure_for_pytest()` (controller) は印があれば待ってから共有 lock を実行の間持つ。`tools/dev/_devlib.py` の `ps` による検出と hold flag を廃止し、`pt.py` / `mutate.py` / `finalize.py` から外す。
- `tools/perf_baseline.py`: 起動部品で専用クラスタを使い、排他 lock を取る (単独実行)。
- テスト: `tools/tests/test_dev_tools.py` の hold flag・他 pytest の検出のテストを置き換える。

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
