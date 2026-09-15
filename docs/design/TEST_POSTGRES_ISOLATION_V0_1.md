# テスト用 PostgreSQL の実行ごとの分離 設計メモ（v0.1）

- 状態: **設計メモ案・依頼者判断待ち（§6）**。規律・道具・テストの変更の根拠にはまだならない。台帳は計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-44**。
- 起票: 2026-09-16。契機は §1.1 の 3 件。設計レビュー 1 回（同日、§9）の指摘を反映済み。
- 公開規律: 実 DSN・パスワードを置かない（`docs/work-orders/OPERATING_CONDITIONS.md` §2 の 13）。DSN は形だけを書く。

## 1. 問題

### 1.1 起きたこと（2026-09-16）

1. 完了ゲートが `judge=FAIL (pg_database +0 -7, pg_roles +0 -22)` を出した。実装担当が pytest を途中で止めた後だった。名前が記録されず、何が消えたかは特定できなかった（名前の出力は `tools/dev/gate.py` に追加済み、main `733e621`）。
   - 差分は**削除**だった。途中で止まった実行が残すのは追加であり、削除は、gate 自身の実行の adapter が起動時の掃除（`r2db-api/conformance/conformance_adapter_r2db_http.py` の `_sweep_stale_artifacts`。advisory lock が取れた、所有者のいない接頭辞だけを消す）でその残骸を消した、と読むのが最も自然である（未確定）。そうであれば常駐サービスの損傷ではなく、「前の実行の残骸が次の gate を FAIL にする」事象である。
2. `tools/dev/pt.py` が他チャットの `conformance-tests` 実行を検知して REFUSED（75）を返した。
3. `tools/dev/finalize.py --tools-tests` が commit の直後に始まった他の pytest を検知し、「commit 済み・未マージ」（76）で止まった。

### 1.2 根本原因

- **共有**: 複数チャットのテストが、常駐 MitateDB サービスと同じ 1 つの PostgreSQL（`host=/tmp port=5432`）を使う。ある実行の残骸・掃除・誤りが、他の実行の判定と常駐サービスに届きうる（1.1 の 1）。
- **観測による排他**: 衝突は `ps` で他の pytest を探して拒否することで避けている。確認と実行の間に割り込まれる（1.1 の 3）。
- **排他の単位が粗い**: 止めるのは「PostgreSQL を使う実行」ではなく「あらゆる pytest」。PostgreSQL を使わない `tools/tests` も止まる（1.1 の 2・3）。
- **残骸の帰属が無い**: 途中で止まった実行の残骸が共有クラスタに残る（`OPERATING_CONDITIONS.md` §2 の 5 の `pg_db_role_setting` の汚れも同類）。

## 2. 目標と条件

- 目標 1: テストの接続は、明示の host / port で名指ししない限り、その実行専用のクラスタに届く。共有クラスタを名指しする既定値をコードに置かない。
- 目標 2: PostgreSQL に起因する実行の待ち・拒否をなくす（gate の扱いは §6 Q-2）。
- 目標 3: 残骸を実行単位に閉じ、実行の終了（SIGKILL を含む）で消す。
- 目標 4: CI とできるだけ同じ条件で動く（PostgreSQL 16、`max_connections=300`、scram、superuser 名、TimeZone）。違いが残る点は明記する（§4 D-2）。
- 目標 5: 接続先の設定漏れを黙って共有クラスタに落とさない（fail させる。§1.3 の 26 と同じ考え方）。
- 許容: 並列実行による CPU・メモリの取り合い。依頼者（2026-09-16、逐語）: 「1は気にしなくて良い。それなりのスペックのPCなのはこんな時のためです。」 ただしこれは資源の問いへの答えであり、gate の集計行が負荷で揺れないことまでは含まない（§6 Q-2）。

## 3. 調査結果（2026-09-16、main `a48cfa1` 時点、静的読解と共有クラスタの読み取りのみ）

### 3.1 共有 PostgreSQL への隠れた依存: 無し

- 接続先: 既定値 `host=/tmp port=5432 dbname=postgres` を持つ 23 ファイルは、すべて `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` で上書きできる（監督が再確認）。他の 3 ファイル（`r2db-api/tests/test_surfaces_env.py`、`r2db-api/tests/test_control_http.py`、`MitateDB-api/tests/test_http.py`）は `port=1` の意図的な到達不能値だけを持つ。
- ただし host を書かない接続（例: `MitateDB-api/tests/test_control_credentials.py` の `dbname=unused-placeholder-never-connected`、現状は接続しない）と `tools/dev/gate.py` の `psql`（`PGHOST`、既定 `/tmp`）は libpq の既定値で共有クラスタに届く。
- データベース・ロール: テストは実行ごとの乱数接頭辞で作り、自分の接頭辞を掃除する。加えて HTTP adapter は起動時に「所有者のいない」他の実行の接頭辞を掃除する（advisory lock で生存を確かめる）。常駐サービスの名前（`mitatedb_platform`、`app_*`、`auth_api`、`r2db_control`）を前提にする箇所は無い。要るのは「接続ロールが superuser」だけ。
- 拡張: `CREATE EXTENSION` は 0 件（監督が再確認）。`shared_preload_libraries` 不要。
- 版: マイグレーションは PostgreSQL 16 以上を要する（`GRANT ... WITH SET TRUE` 等）。
- CI: `.github/workflows/ci.yml` は実行ごとに新品の `postgres:16` コンテナを `-c max_connections=300` だけで起動し（TimeZone 指定なし）、`user=postgres` の TCP + パスワードで接続して suite を通している。空のクラスタで動くことの実績である。

### 3.2 固定ポート: 無し

- 数値リテラルのポートで待ち受ける箇所は 0 件。常駐サービスの 8000/8001 を使う箇所も無い。データベース名・ロール名・一時ディレクトリ・ロックファイル名は実行ごとに一意。
- 要対策（確認と使用の間に他の実行が番号を取りうる）:
  - `conformance-tests/socket_harness.py` の `free_port()`（bind して閉じた番号を後で開き直す）。使用箇所は `start_uvicorn_thread()` / `start_uvicorn_subprocess()` の既定経路と、`r2db-api/conformance/real_server_r2db.py`・`MitateDB-api/conformance/real_server_mitatedb.py` の F-15/F-16 系の subprocess 起動（各 3 箇所）。
  - nginx の起動は `reserve_port()` の直後に `.close()` するので同じ隙がある。再試行は「1 回だけ」（2026-09-08 の裁定、同ファイルの docstring）。
  - `reserve_port()` を uvicorn にそのまま渡す経路は安全。

### 3.3 共有クラスタの現状（読み取りのみ）

- サーバー 16.14。手元の `initdb` も 16.14。
- `pg_hba` はローカルソケット・loopback ともすべて `trust`。拡張は `plpgsql` のみ。
- 既定から変えてある設定: `max_connections=300`、`TimeZone=Asia/Tokyo`、ロケール `en_US.UTF-8`・UTF8。
- trust のため、ローカルではパスワードの誤りが検出されない（前例: `r2db-api/tests/test_ops_declarations.py` の `api_password` の註。CI の scram だけが検出した）。
- `r2db-api/tests/test_control_plane_store.py` の `test_audit_report_naive_since_is_interpreted_as_utc` は、セッションの TimeZone が UTC 以外のときだけ誤りを検出できる（UTC の CI では効かない）。
- 残骸の疑いがあるオブジェクト（`wp2e2e99887_*`、`mitatedb_app_phaseb_verify`、`revm1*`）がある。帰属は未判定で、本件の範囲外（§6 Q-5）。

## 4. 設計案

- **D-1 起動の場所**:
  - 起動・停止・掃除は conftest ではない独立したモジュール（以下「起動部品」）に置く。context manager と CLI（`python -m <起動部品> -- <コマンド>`）を持つ。
  - pytest の設定の根（`[tool.pytest.ini_options]` を持つ 3 箇所: リポジトリ直下、`r2db-api/`、`MitateDB-api/`）それぞれの `conftest.py` が、**モジュールの import 時に**起動部品を冪等に呼ぶ。理由:
    - `conformance-tests/conftest.py` は import 時に adapter を作り、adapter はその場で PostgreSQL に接続する。pytest は初期 conftest を `pytest_configure` より前に import するので、hook での起動では遅い。
    - pytest は親ディレクトリの conftest を先に import する。
    - `pytest r2db-api/tests/...` や `cd MitateDB-api && pytest` は peer の設定が根になり、直下の conftest を読まない。
  - 2 つの peer の conftest は同形に保つ（§1.5 の 38、`conformance-tests/test_pytest_config_symmetry.py` との整合を WP-1 で確認）。
  - 二重起動の防止: 起動した controller が `DSA_TEST_PG=owned:<識別子>` を環境変数に置く。xdist の worker（`PYTEST_XDIST_WORKER` あり）と入れ子の pytest はこれを見て起動しない。xdist の worker は controller の `pytest_sessionstart` 以降に起動され、環境変数を継承する（pytest-xdist 3.8.0 / execnet 2.1.2）。
  - PostgreSQL を使わない `tools/tests` には `tools/tests/pytest.ini` を置き、根をそこに移して起動しない。ルートの `filterwarnings` 等で要るものはそこにも置く。
  - 非 pytest の利用者（`tools/perf_baseline.py`、`tools/dev/gate.py`）は起動部品の context manager / CLI を使う。
  - 採らない案: (a) 各 peer の pytest 設定を消して根を 1 つにする（フェーズ7 WP-6 D-4(b)(iii) の取り消しになる）。(b) pytest の entry point plugin として共有 `.venv` に editable install する（`.venv` は main checkout を指し、worktree の変更が反映されない。§2 の 17 と同じ問題。CI への導入手順も増える）。
- **D-2 クラスタの仕様**:
  - 手元の PostgreSQL 16 を使い、メジャー版が 16 でなければ fail。
  - `postgres -D <data>` を起動部品の**直接の子**として起動する（`pg_ctl` は `setsid` で親から離れ、SIGKILL が届かない）。
  - `initdb --auth=scram-sha-256`、superuser 名は §6 Q-7、パスワードは実行ごとに `secrets` で生成。
  - パスワードは DSN に入れず、0600 の `PGPASSFILE`（実行ディレクトリ内、ユーザー名を明記した 1 行）で渡す。DSN はエラーメッセージや `psql` の引数に出るため。
  - `--locale=en_US.UTF-8 --encoding=UTF8`、`max_connections=300`、`TimeZone` は §6 Q-6。
  - TCP を開かない（`listen_addresses=''`）。CI は TCP なので、ここは CI と違うまま残る（TCP にするとポートの割り当てが再び競合点になる）。
  - `unix_socket_directories` とデータディレクトリは、ユーザー単位の固定の基底（`$TMPDIR` 配下。`/tmp` 直下の固定名や CI の残骸検査が見る `conf-socket-*` は使わない）の下の実行ディレクトリ（0700、`unix_socket_permissions=0700`）。socket のパス長が 104 バイトを超えるなら fail。Drive 同期ツリーの外。
  - 子プロセスに渡す環境変数: `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN`（形: `host=<socket dir> port=<port> dbname=postgres user=<superuser>`）、`PGHOST`、`PGPORT`、`PGUSER`、`PGPASSFILE`。これで host を書かない接続もその実行のクラスタに届く（目標 1）。
- **D-3 寿命と後始末**:
  - 起動部品は小さな監視プロセスを持つ。監視プロセスは controller からのパイプの読み端を持ち、EOF（controller の SIGKILL を含む）で postmaster に SIGTERM → 猶予後 SIGQUIT を送り、実行ディレクトリを消す。
  - 正常終了（`pytest_unconfigure`、atexit、SIGINT/SIGTERM）でも同じ停止をする。
  - 予備として、起動時に基底の下を掃除する。実行ディレクトリごとの目印ファイルに `flock` を掛け、取れたものだけを「所有者が死んだ」とみなす（pid の再利用に影響されない）。記録した postmaster の pid と起動時刻が一致すれば停止してから消す。
  - 共有クラスタには一切触れない。取り残しは System V 共有メモリのセグメント上限（`kern.sysv.shmmni=32`）を消費するので、WP-1 で「SIGKILL の後に何も残らない」ことをテストする。
- **D-4 外部クラスタと既定値**:
  - 環境変数 `DSA_TEST_PG=external` のときだけ起動せず、2 つの DSN が両方設定されていることを要求する（CI、D-5 の gate、D-9 の性能計測が使う）。
  - `DSA_TEST_PG` が未設定なのに DSN が設定済みなら fail（どちらを使うか曖昧なため）。`owned:` は D-1 の子孫プロセス用。
  - 23 ファイルの既定値 `host=/tmp port=5432 dbname=postgres` と、既定値を埋め込んだ fail メッセージを削除し、未設定は fail にする（目標 5）。
  - `tools/tests` に、既定値のリテラルが再び入らないことの検査を足す。
- **D-5 gate**:
  - `tools/dev/gate.py` が起動部品でクラスタを起動し、`DSA_TEST_PG=external` で pytest に渡す。
  - 前後の `pg_database` / `pg_roles` の比較はそのクラスタで、停止前に行う（残骸の検出。§1.3 の 23 を置き換え）。`psql` には `PGPASSFILE` を渡す。
  - 共有クラスタの前後比較は §6 Q-3。
- **D-6 排他**:
  - `ps` の観測による排他を廃止する。
  - gate の扱いは §6 Q-2。推奨案（lock）では gate が排他 lock、`pt.py` / `mutate.py` / `finalize.py` が共有 lock を実行の間持つ。gate は着手の意思を印に置き、新しい共有 lock はそれを見て待つ（gate の飢餓防止）。lock なので確認と実行の隙が無い。
- **D-7 待ち受けポート**:
  - uvicorn 0.52.4 の `--fd` と `pass_fds` で、subprocess 起動も `reserve_port()` のソケットを渡す。親は起動後に自分の複製を閉じる。
  - F-16 の「起動失敗を期待する」試行は、事前に listen したソケットでは接続が拒否されず backlog に並ぶ。`wait_until_ready` の意味が保たれるかを WP-3 の spike で確かめる。
  - nginx は開いたソケットを受け取れない。再試行の回数は §6 Q-8。
- **D-8 CI**:
  - workflow 全体の `env:` に `DSA_TEST_PG: external` を足す（`tools-tests` job も DSN を継承するため）。コンテナの起動は Q-6・Q-7 の結論に合わせる。
- **D-9 性能計測**:
  - `tools/perf_baseline.py` は起動部品の context manager で専用クラスタを使う。CPU を測るので単独実行の規則は残す。
  - 基準値を取り直すかは §6 Q-9。

## 5. 変わる規律・文書・コード（案。裁定後に改訂する）

- `docs/work-orders/OPERATING_CONDITIONS.md`:
  - §1.3 の 19〜21・23・24。
  - §1.5 の 39（`ps` の確認）。
  - §1.6 の 41。
  - §1.10 の 64（gate の説明）・66（75 の意味）。
  - §2 の 3〜5・12・13・18、および 19 の理由文（「同一ローカル PostgreSQL クラスタを共有」が偽になる）。
  - §3 の 3・10。
- 文書:
  - `conformance-tests/README.md`（PostgreSQL の節と gate の「run solo」の文）
  - `MitateDB-api/README.md`（実行コマンドと既定値）
  - `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`
  - `tools/PERF_BASELINE_README.md`
  - `tools/dev/README.md`
  - `.github/workflows/ci.yml` の env とコメント
- コード:
  - `tools/dev/_devlib.py`（hold flag・他 pytest の検出）
  - `tools/dev/gate.py` / `pt.py` / `mutate.py` / `finalize.py`
  - `tools/tests/test_dev_tools.py` の該当テスト
  - 23 ファイルの既定値
  - `socket_harness.py` と `real_server_*.py` の起動経路
- 触らないもの: マイグレーションの経緯コメント（checksum 対象）。
- リポジトリ外（監督が更新する）: 「gate は単独」「gate とレビューの並行禁止」を記した運用メモと、subagent への発注テンプレートの `ps` 確認。

## 6. 依頼者に決めていただく点

- **Q-1 認証方式**: 使い捨てクラスタを scram-sha-256 にする（推奨。CI と揃い、ローカルでもパスワードの誤りを検出できる）／ trust のまま。
- **Q-2 gate と他の実行の関係**:
  - (a) 通常の実行は並列に走ってよく、gate の実行中だけ他の実行が lock で待つ（推奨）。roadmap R-42（期限切れの要求の成否が負荷で揺れる）が未修正の間、gate の集計行を負荷から守るため。
  - (b) gate も含めて完全に並列にする。R-42 の修正後に (a) から移る候補。
  - (c) 現行の `ps` による排他を残す。
- **Q-3 共有クラスタの前後比較（gate）**: 情報表示だけにする（推奨。テストは共有クラスタに触れなくなり、変化は常駐サービスや他の利用者のものになる）／ FAIL のまま。
- **Q-4 既定値の削除（D-4）の時期**: 起動の仕組みと同じ一連の作業で行う（推奨）。着手時に進行中の R-37 と対象ファイルが重ならないかを確かめ、重なるなら R-37 の当該 WP のマージ直後に行う。
- **Q-5 共有クラスタの残骸の疑い（§3.3）**: 本件とは別に帰属を調べる／放置する。
- **Q-6 TimeZone**: ローカル・CI とも `Asia/Tokyo` を明示する（推奨。UTC 以外でしか効かないテストが CI でも効くようになり、既定値への依存も消える）／ 両方 UTC ／ 現状どおり（ローカル Tokyo・CI UTC）。
- **Q-7 superuser 名**: ローカルも `postgres` にする（推奨。CI と同じ名前になる）／ OS ユーザー。
- **Q-8 nginx の bind 再試行**: 2026-09-08 の裁定「1 回だけ」を、並列実行の前提で数回（例: 3 回、失敗ごとに error.log を残す）に改める（推奨）／ 1 回のまま。
- **Q-9 性能の基準値**: 専用クラスタで基準値を 1 回取り直し、以後はその値と比べる（推奨）／ 共有クラスタで取った値と比べ続ける。

## 7. 作業の分け方（案）

1. WP-1: 起動部品（起動・監視プロセス・停止・掃除・lock）、3 つの `conftest.py`、`tools/tests/pytest.ini`（D-1〜D-4）。部品のテストと変異。統合テストは次を確かめる。
   - 実クラスタが起動する。
   - host を書かない `psycopg.connect("dbname=postgres")` がその実行のクラスタに届く（`pg_control_system()` の `system_identifier` で比べる）。
   - controller の SIGKILL の後に postmaster とディレクトリが残らない。
   - worker と入れ子の pytest が二重起動しない。
2. WP-2: `gate.py` / `pt.py` / `mutate.py` / `finalize.py` / `perf_baseline.py`（D-5・D-6・D-9）。
3. WP-3: 23 ファイルの既定値の削除と再発防止の検査、待ち受けポートの変更（D-4・D-7）。F-16 の spike を先に行う。
4. WP-4: CI・規律・文書の改訂（D-8、§5）。
5. 完了条件:
   - 専用クラスタ上の完了ゲートの集計行が、直前の main の集計行と一致する。
   - 実行のクラスタの前後差分が 0 で、共有クラスタに変化が無い。
   - 次の起動の形でもそれぞれ専用クラスタが使われる: `pytest`、`pytest r2db-api/tests/...`、`cd MitateDB-api && pytest tests/`、`--collect-only`、`tools/check_collection_floor.py`。
   - `pytest tools/tests` がクラスタを起動しない。
   - suite を 2 本並列に 3 回走らせ、毎回両方の集計行が一致する。

## 8. 未確認の点

- uvicorn の `--fd` に TCP のソケットを渡したときの実際の挙動。
- `initdb` と起動にかかる時間。毎回の `--collect-only` と `tools/check_collection_floor.py` も払うので記録する（roadmap R-20 の「先に測る」）。
- Claude Code の sandbox の下で、subprocess が `$TMPDIR` 配下にディレクトリを作り、postmaster を起動できること。
- `postgres:16` イメージの既定の TimeZone（UTC と見込む）。
- ローカルでだけ trust に依存して通っているテストが無いこと。CI は scram で通っているので少ない見込み。既知の前例は修正済み。
- 専用クラスタで性能の値が変わるか（Q-9 の判断材料）。

## 9. 設計レビューの記録（2026-09-16、1 回目、独立レビュー・静的読解のみ）

判定は BLOCKER 2・MAJOR 7・MINOR 12。すべて本版に反映した。

| 指摘 | 内容 | 反映先 |
|---|---|---|
| B-1 | `pytest_configure` での起動は、import 時に接続する adapter より遅い | D-1（import 時に起動） |
| B-2 | peer の設定が根になる実行では直下の conftest が読まれない | D-1（3 つの根、採らない案 a） |
| M-1 | `tools/tests` がクラスタを起動する。CI の `tools-tests` job が D-4 の規則で壊れる | D-1（`tools/tests/pytest.ini`）、D-8 |
| M-2 | `pg_ctl` の `setsid` で SIGKILL の後に postmaster が残る。掃除に lock が無い | D-2、D-3、§7 WP-1 |
| M-3 | host を書かない接続は libpq の既定値で共有クラスタに届く | 目標 1 の書き直し、D-2（`PGHOST` 等）、§7 WP-1 |
| M-4 | 性能計測に専用クラスタへの経路が無い | D-1、D-9、§6 Q-9 |
| M-5 | §5 の漏れ | §5 |
| M-6 | Q-2 の推奨が負荷で揺れるテスト（R-42）を無視 | §6 Q-2、§7 の完了条件（3 回） |
| M-7 | 黙って決めていた点 | §6 Q-6〜Q-9、D-2（socket と PGPASSFILE の理由）、D-4（`owned:`） |
| m-1 | 26 ではなく 23 ファイル | §3.1、D-4、§7 |
| m-2 | 起動時の掃除の存在と、§1.1 の差分が削除だったこと | §1.1、§3.1 |
| m-3 | パスワードが DSN 経由で出力・引数に出る | D-2（PGPASSFILE、0700） |
| m-4 | nginx は `reserve_port()` → `.close()` | §3.2 |
| m-5 | `--fd` の詳細、F-16 の意味 | D-7、§7 WP-3、§8 |
| m-6 | socket の基底、`/tmp` 直下を避ける | D-2 |
| m-7 | gate の `psql` に認証情報が要る | D-5 |
| m-8 | worker・入れ子での曖昧規則の除外 | D-1、D-4 |
| m-9 | `--collect-only` の起動費用、`--noconftest` | §8（費用）。`--noconftest` は D-4 により fail する（意図どおり） |
| m-10 | roadmap R-44 の記述 | R-44 行を更新 |
| m-11 | trust 依存のテストは低リスク | §8 |
| m-12 | セマフォは問題なし | 対応不要 |
