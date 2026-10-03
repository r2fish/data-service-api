# 引き継ぎ書 — 2026-10-03〜04 main の CI の是正と送信、送信まわりの運用条件の改訂、R-17 の閉止、runner の固定

本書は作業機の監督チャット (Fable) の記録である。依頼は「main の CI の赤を是正し、手元で確認してから、CI を 1 回だけ走らせる」(依頼者 2026-10-03、Mitate 側のセッションが失敗の内訳をまとめたもの) と、それに続く依頼者の指示 (worktree の畳み込み、`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) の送信まわりの条項の改訂、台帳 R-17 の閉止、CI の runner の固定、本書) である。規律の正本は `OC`、台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 (以下 `RM`) である。CI の是正そのものは台帳の行を持たない (依頼者の直接の指示による)。`$SP` は本チャットの scratchpad で、次のチャットからは読めない。

**本書は 2026-10-04 に全体を更新した** (初版は 2026-10-03、main `767064b`。その後の追記を本文へ畳んだ)。§1 の値は記載の日付・commit の時点の記録であり、現在地は `OC` §1.8 の 55a の出所から読む。

## 1. 現在地 (2026-10-04、local main `01efa56` の時点の記録)

- GitHub 側の main は `a5e994b` (2026-10-03 に 1 回送信、`05a60c0` から 75 commit)。CI run 37126080963 は全 9 job 成功。
- local main は `01efa56` で、GitHub 側より 25 commit 先 (merge commit を含む)。未送信。文書以外の変更は `.github/workflows/ci.yml` の runner の固定だけである。**先頭 commit の件名に `[skip ci]` は付いていない。** この 25 commit には、並行した別チャットの R-28 の閉止 (文書だけ、台帳 v1.164・v1.165、`OC` §1.8 の 55a) が含まれる。
- 契約は 1.16.0。`security/CONTROL_MAPPING.md` は 3.20、`conformance-tests/COLLECTION_FLOOR` は 5232。台帳は本チャットが v1.163 (R-17 の閉止) を作り、その後別チャットが v1.165 まで進めた。
- 完了ゲート (監督): CI の是正の変更セットの上で gate: 5232 passed, 2 subtests passed in 528.46s (0:08:48), judge=PASS, label cifix, pg_database/pg_roles diff 0 (5231 + 新規テスト 1 件)。runner の固定の変更セットの上 (main `a51b58a` の上) で gate: 5232 passed, 2 subtests passed in 738.70s (0:12:18), judge=PASS, label pin。その後 main が別チャットの文書だけの merge で `2a3b65a` に進み、その上に載せ直した分はゲートを測り直していない。
- CI の集計 (run 37126080963): conformance 3.11 = `5232 passed, 2 subtests passed in 1216.67s`、3.12 = `5232 passed, 2 subtests passed in 1500.19s`、tools-tests = `790 passed`。所要は run 全体で約 27 分。課金の分数は GitHub の timing API が 0 を返しており未確認 (job ごとに分単位へ切り上げた試算は 57 分)。runner の image は `ubuntu-24.04`。
- worktree: 本チャットが作ったもの (`cifix`、`oc20`、`oc3`、`ho`、`oc113`、`oc115`、`oc115c`、`oc221`、`oc221c`、`r17close`、`pin`) は統合して畳んだ。依頼により `r121` (worktree) と `r116` (branch) も `tools/dev/fold.py --apply` で畳んだ。残りは `git worktree list` で見る (他チャットのもの、lock 中の `r45-wpd` を含む)。

## 2. 本チャットで閉じたもの

### 2.1 CI の是正 (main `a5e994b`、commit `8f92078`)

失敗した run は 36997700111 (commit `05a60c0`)。原因と是正は次のとおり。「確認済み」は手元で是正前の赤を再現したもの。

| # | 失敗 | 原因 | 是正 |
|---|---|---|---|
| 1 | `MitateDB-api/tests/test_ops_inventory.py` 3 件 | 確認済み。製品は TCP の DSN を仕様どおり `unknown` と判定する。テストが unix socket の DSN を前提にしていた | テストに `_socket_shaped_provision_dsn` を足した (TCP のときは `host` = 合成の socket ディレクトリ、`hostaddr` = 実アドレス)。期待値は変えていない |
| 2 | `MitateDB-api/tests/test_ops_apply_platform_migration.py` teardown の error 1 件 | 確認済み。`PGSSLMODE=verify-full` が `platform` fixture の後始末の接続まで残っていた (1 とは別の原因) | `monkeypatch.context()` で 1 回の `ops.main` 呼び出しに閉じた |
| 3 | `test_c05_v2_declaration_and_position_agree[r2db-api-socket]` (3.12 だけ) | 推定。r2db の `RequestByteBoundMiddleware` が超過した body の残りを読まずに 413 を返しており、nginx 経由で nginx 自身の応答に化け得る。MitateDB は読み捨て済み。macOS で 15 回実行して再現 0 回 | `r2db-api/src/r2db_api/http.py` に読み捨てを足した。テスト 1 件 |
| 4 | 集計 step | 1〜3 の結果 (error を数えない集計) | 変更なし |
| 5 | `tools/tests/test_perf_baseline.py` 3 件 | 確認済み。tools-tests の job に psycopg が無かった | job に pin 済みの `psycopg[binary]` を足した |
| 6 | `test_r89_real_commit_0d0f8c9_reproduction` | 確認済み。job の checkout が深さ 1 だった (commit は main の祖先) | job を `fetch-depth: 0` にした |
| 7 | `tools/tests/test_testpg.py` 2 件 | 未測定。Linux の `ps -o args=` による判定が、生きている process を「自分のものではない」と返した (80 桁の切り詰めが有力だが確かめていない) | `tools/testpg/dsa_testpg.py` の `_ps_args` を、`/proc` があればそれを読む形にした (それ以外は `ps -ww`)。テスト 1 件 |

- 変異: `M1-no-drain` (読み捨てを無効化 → 新テストが赤)、`M2-proc-cut` (`/proc` の argv を 80 文字で切る → 新テストが赤)。2 件とも expect=red / got=red、復元の照合 ok。1・2・5・6 は是正前の赤の再現が証拠である。
- 手元の確認 (送信前): 完了ゲート (§1)、CI と同じ接続条件の全体実行 `5232 passed, 2 subtests passed in 542.68s` (TCP・TLS なし・password の PostgreSQL 16、`DSA_TEST_PG=external`、Python 3.11)、tools-tests の再現 `790 passed` (クリーンな 3.11 の venv、job と同じ pip 行、新しい完全な clone)。
- 手元で検証できなかった条件: Python 3.12 (未導入)、Linux (docker が無い。`ps`、nginx と uvicorn の接続切断)、PostgreSQL の port (手元 54329、CI 5432)。
- 3 と 7 は CI で緑になったが原因は確定していない。3 は前回も 2 job 中 1 job でしか落ちておらず、1 回の緑は是正が効いた証明ではない。
- `security/CONTROL_MAPPING.md` 3.20: SI-08 r2db-api Control に読み捨ての主張 1 行 (proxy の `client_max_body_size` が読む量の上限であることの開示)、挿入した 4 行に伴う r2db `http.py` への位置参照 5 か所の付け替え (SI-00、SI-08、SI-10)。
- レビュー: コードレビュー 1 回 + 再確認 1 回。変更クラスは経路で B、`security/` に触れたので D。規模 S。監査担当は起動していない (`OC` §1.13 の 74)。

### 2.2 送信 (依頼者の指示 2026-10-03)

- Mitate の送信用スクリプトで `--dry-run` の後に 1 回送った。送信前に、identity が全 commit で r2fish の noreply であること、先頭 commit の件名に `[skip ci]` が無いことを確かめた。CI の起動は 1 回、再実行なし。

### 2.3 運用条件の改訂 (local main、未送信)

いずれも依頼者の指示による。旧条項は `OC` §4 へ逐語で移し、改版履歴に行を足した。

| 条項 | 内容 | 指示・確認 (逐語) | commit |
|---|---|---|---|
| §2 の 20 | 送信は Mitate リポジトリの送信用スクリプトだけを通し、依頼者の明示の指示があるときに監督が行う。`main` だけ、`--dry-run` を先に、`--use-reserve` は明示の指示があるときだけ、先頭 commit の件名に `[skip ci]` が無いことを確かめる、1 日 1 回を基本。旧条項は §4 の 13 | 「§2 の 20 を現行の送信ルールに書き換えてください」 | `970444a` |
| §3 の 1〜5・8・9・11・12、§5 の 2 行 | 出所 `CI`:行番号を現行の `ci.yml` に付け替えた。条件の本文は変えていない | 「§3 の CI 行番号の出所も直してください」 | `49e97bb` |
| §1.1 の 3 | commit → main へのマージまでを 1 単位とする。送信はこの単位に含めず §2 の 20 に従う。旧条項は §4 の 14 | 「§1.1 の 3 の文面も現状に修正」 | `d3349c7` |
| §1.1 の 5 | 送信前の identity 確認の範囲を、先頭 5 件から送信する全 commit (`origin/main..main`、merge commit を含む) に改めた。監督裁定で、committer も対象にし、コマンドの失敗と行数の不一致では送らず、確認の後に main が動いたら確認し直す、を足した。旧条項は §4 の 15 | 「§1.1 の 5 も送信する全 commit に修正」、監督裁定の 3 点は「3 点とも了承します」 | `c02fb86`、`e2d7a8c` |
| §2 の 21 (新設) | 送信の前に手元で緑にするもの: (a) 完了ゲート、(b) CI と同じ接続条件の全体実行、(c) `tools-tests` job の再現。(a)(b) は送信する範囲に Class A 以外の変更があるとき、(c) は常に。寄せられなかった条件は「手元では未検証」と報告に書く。CI が赤でも再送信・再実行しない | 「送信前の手元確認も常設の条項にしてください」、(a)(b) の限定は「限定はそのままで了承します」 | `e86a155` (確認の記録は main `c471cc5`) |
| §3 の 13 (新設) | 全 job の runner は `ubuntu-24.04` に固定 (§2.5) | 「1 で進めてください」 | `1c0be51` |

- §1 に触れた 2 件 (§1.1 の 3、§1.1 の 5) は、それぞれ設計レビューを 1 回起動した (`OC` §1.13 の 74)。指摘と裁定は「裁定」節にある。

### 2.4 台帳 R-17 の閉止 (台帳 v1.163、commit `8913f19`、依頼者指示 2026-10-04)

- 残っていたのは「送信の再開後に main の先頭で CI run を 1 回取って記録する」だけだった。run 37126080963 の `doc-refs` job の出力 (`empty markdown files: 0`、`check_doc_refs OK: 0 dangling references`) を証拠に閉止した。機械検査を入れた commit `7d8bb0f` は送信した main の祖先である。
- 文書だけ (Class A)。完了ゲートは実行していない。`tools/dev/ledger.py --check` は緑、`tools/tests` は 790 passed。

### 2.5 CI の runner の固定 (commit `1c0be51`、main `01efa56`、依頼者指示 2026-10-04)

- `ubuntu-latest` は 2026-10-19 から Ubuntu 26 へ移る (run 37126080963 の runner の通知)。`conformance` job は OS の apt から `postgresql-16` と nginx を入れ、`DSA_TEST_PG_BINDIR` でその版の path を名指ししている。Ubuntu 26 の apt に `postgresql-16` が在るかは確かめていない。
- `.github/workflows/ci.yml` の `runs-on:` 8 行を `ubuntu-24.04` に、その場で書き換えた (行の追加は無く、`OC` §3 の `CI`:行番号は変わらない)。理由は行末コメントにある。
- 完了条件: `ubuntu-latest` で動く job が無い (8 行の現物と YAML の読み込みで確認)。**固定の効果は未検証であり、次の送信の CI run で初めて確かめられる。**

## 3. 次の一手

1. 次に送るときは `OC` §1.1 の 5、§2 の 20・21 に従う。2026-10-04 の時点の未送信分には `ci.yml` の変更 (Class A 以外) があるので、§2 の 21 の (a)(b)(c) が全部要る。手順の実例は §5 の 1。**本書のこの更新の commit は文書だけなので `[skip ci]` 付きで main の先頭になる。そのまま送ると CI が起動せず、`ci.yml` の変更が確かめられない。送る前に先頭の件名を確かめ、付いていれば送らずに依頼者へ報告する** (`OC` §2 の 20)。
2. 次の CI run で、runner の固定 (`ubuntu-24.04`) の下で全 job が緑であることを確かめる。
3. Ubuntu 26 への移行 (apt に頼らない形で PostgreSQL 16 を入れる等) は、凍結期間 (2026-10-15 23:59 〜 2026-12-02) の後に検討する。固定した版はいずれ GitHub 側で廃止される。
4. CI の是正のうち 3 (r2db の読み捨て) と 7 (Linux の argv の読み方) は原因が確定していない (§2.1)。3 が再発したら、nginx の error log を CI に出して測る。

## 4. 依頼者判断待ち・未決

2026-10-04 の時点で、本チャットから残る依頼者判断待ちは無い。初版に挙げた 3 件は同じチャットで決着した。

1. 送信前の手元確認を常設の条項にするか → `OC` §2 の 21 として足した。(a)(b) の限定は依頼者確認済み。
2. `OC` §1.1 の 3 の文面が現状と合っていない → 依頼者の指示で改めた。
3. `OC` §1.1 の 5 の確認の範囲が先頭 5 件のままである → 依頼者の指示で送信する全 commit に改めた。監督裁定で足した 3 点は依頼者確認済み。

## 5. 運用上の教訓

1. **CI と手元のゲートは接続条件が違う。** CI は docker の PostgreSQL に TCP・TLS なし・password で繋ぐ (`DSA_TEST_PG=external`)。手元のゲートは unix socket の使い捨てクラスタである。2026-09-09 以降に足したテストは CI で一度も走っておらず、赤 7 種のうち 3 種はこの差が原因だった。手元の再現: scratchpad に `initdb --auth=scram-sha-256 --pwfile` で cluster を作り、`listen_addresses=127.0.0.1`・別 port・`max_connections=300`・`unix_socket_directories=''` で起動し、両方の `*_TEST_ADMIN_DSN` を TCP の DSN、`DSA_TEST_PG=external`、`PYTHONPATH` を worktree の両 `src` にして CI と同じコマンドを走らせる。tools-tests はクリーンな venv に job と同じ pip 行を入れ、新しい clone で走らせる (clone の深さが結果を変える)。
2. **この機械に Linux は無い。** docker は無く、`isolation: remote` の agent もこの Mac で動いた。Linux だけの挙動は CI が走るまで「手元では未検証」と書く。
3. **`check_comment_provenance.py` は worktree の中のコピーで実行する。** main checkout のコピーに worktree の path を渡すと main を検査して緑を返す (同検査器の Known gaps に既出)。本チャットでも一度これで偽の緑を見た。
4. **peer の `src` に block comment や docstring を足すと `--base` の (2) が赤になる。** 説明は行末コメントとテストの docstring に置き、文を足す位置は既存の塊の鍵を動かさない所にする。
5. **r2db `http.py` に行を足すと `security/CONTROL_MAPPING.md` の位置参照がずれる。** R-88 の検査は範囲しか見ないのでゲートは緑のままである。同じ変更セットで現物と突き合わせて付け替える。
6. **`tools/dev/fold.py` は作ったばかりの worktree を対象外にする。** 猶予を 0 にすると他チャットの worktree も対象になるので、自分の 1 本だけを畳むときは `git worktree remove` と `git branch -d` を使った。
7. **並行するチャットが main を動かす。** runner の固定の最中に、別チャットの完了ゲートが走っていてこちらのゲートは REFUSED (終了コード 75) になり、その後 main に 2 回統合が入った。REFUSED は迂回せず相手の終了を待つ (`OC` §1.10 の 66)。統合の前に `git log -1 main` を見て、動いていたら取り込んでから測る。未コミットの編集を script で再生成できる形にしておくと、取り込み直しが速い。
8. **`ci.yml` に行を足すと `OC` §3 の `CI`:行番号がずれる。** ずれを検出する機械検査は無い。足さずに済むなら行末コメントで書き、足したら同じ変更セットで付け替える。

## 6. 裁定

`OC` §1.15 の 77。レビュー = コードレビュー 1 巡目、再確認 = 修正後の再確認。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー F1: r2db `http.py` を指す `CONTROL_MAPPING` の位置参照が別の行を指すようになる | 直した | 同じ変更セットで 5 か所を付け替え、再確認が 10 参照を現物と照合した |
| レビュー F2: 新しいコメントとテストの docstring が測っていない因果を断言している | 直した | block comment をやめ、docstring を可能性の言い方と観測事実に直した |
| レビュー F3: 読み捨てに app 層の上限が無い | 直した (開示) | MitateDB と同じ挙動で、SI-08 は proxy による制限を認める。`CONTROL_MAPPING` に上限の所在を 1 行で開示した |
| レビュー F4: `dsa_testpg` の docstring が Linux でも「`ps` の argv」と書いている | 直した | 4 か所を言い直した |
| レビュー O1: comment provenance の (1) と (2) | 直した ((2))、観察 ((1)) | (2) は文の位置を変えて消した。(1) は実際のコード変更で必ず出る |
| 再確認 1: nginx の `.example` への位置参照は機械検査の対象外 | 観察 | 検査器の穴だが製品の欠陥は通らない。現物とは一致している。DB の利用者は気づかない |
| 監督: 7 の原因 (Linux の `ps`) が未測定 | 観察 | 検査の道具の中の話で、DB の利用者は気づかない。CI は緑 |
| 監督: 3 の原因が推定のまま | 観察 | 是正は MitateDB と同じ形に揃えるもので、推定が外れても害が無い。再発したら nginx の error log を CI に出して測る |
| 設計レビュー (§1.1 の 3 の改訂) 1-1: 送信の範囲と §1.1 の 5 の `-5` の窓がずれる | 直した (改版履歴の断言を外した)、残りは依頼者判断待ち (§4 の 3) → 【追記 2026-10-03】依頼者の指示で §1.1 の 5 の範囲を送信する全 commit に改めた (`OC` §4 の 15) | 窓を改めるのは §1 の変更で依頼者確認を要する。`finalize.py` が commit ごとに identity を確かめるので、手で作った commit だけが穴になる。決着後: 確認の範囲は送信範囲と一致した |
| 設計レビュー 1-2: `OC` §5 の §1.1-3 の行が表の定義から外れる | 直した | 行の鍵を §4-14 (旧 §1.1-3) に付け替え、正本と重複出所は旧条項のまま残した |
| 設計レビュー 1-3: `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md` と過去の作業指示書に旧文言が残る | 観察 | 当時の記録であり書き換えない (`OC` §4 の 14 の末文)。DB の利用者は気づかない |
| 設計レビュー (§1.1 の 5 の改訂) 1: 新しいコマンドが author しか見ず committer を見ない | 直した | committer を足した。`finalize.py` の検査と同じ範囲になる。依頼者の逐語指示を越えるので事後確認の対象 (§4 の 3) |
| 設計レビュー 2: コマンドが失敗して出力が空でも合格と読める | 直した | 失敗と行数の不一致では送らないと書いた |
| 設計レビュー 3: 確認から送信までの間に main が進むと増えた commit が確認されない | 直した | 確認の後に main が動いたら確認し直すと書いた |
| 設計レビュー 4: 「裁定」の行で前の判定を上書きして消している | 直した | 前の判定を残し、追記の形にした (`OC` §1.8 の 56) |
