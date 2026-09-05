# 引き継ぎ — 2026-09-05 (第14次。Q4 フェーズ — 宣言と適用状態の根拠を DB 側の一次情報へ寄せる。契約は 1.6.0 のまま無変更)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/受け入れ監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: **第13次 `HANDOVER_20260904_FABLE2.md` の約束事は全て継続**する (§2 到達した状態、§3 クライアント連携、§4 の次の一手と運用規律、§5 教訓)。そのさらに前の引き継ぎも全て継続。**現在地のみ本書が上書きする**
- 本書は第13次の直後のセッション記録である。**Q4 フェーズ (3 件: Q4 案 B / L6-5a / L6-20 (f)) を WP-0〜WP-5 で完了した。契約は 1.6.0 のまま 1 文字も変えていない** (依頼者裁定 U-1)。**実機適用は未実施であり、クライアント一報も送っていない** (方針不変)

## 1. 現在地 (main)

**Q4 フェーズは WP-5 (記録整理) をもって閉じている。** 契約無変更なので `spec/` も `conformance-tests/` の vector / port / `registry.json` も 1 行も動いていない。

| コミット (merge) | WP | 内容 | root suite (単独実行) |
|---|---|---|---|
| `6ddcd19` | WP-0 | 共通基盤 (静的規則スキャナ / ms 正規化ヘルパの src 引き上げ / 対応表 18 → 24 行) | **1868 / 0 / 0 / 4 xfailed** |
| `a01bdf0` | WP-1 (r2db `9ae8ea6`) + WP-2 (MitateDB `0379827`) | 宣言を DB 側の一次情報へ (`0008` / `0007` + composition root + 二重検査 + ops 宣言系) | **2077 / 0 / 0 / 4 xfailed** |
| `0301c10` | WP-3 (r2db `55998b2`) + WP-4 (MitateDB `370fe33`) | per-application 台帳と一括適用 (`0003` 改訂 + `0009` / `0008` + cell open 検査 + ops) | **2165 / 0 / 0 / 0** |
| `(本記録の merge。ハッシュは次回引き継ぎ §1 に記載)` | WP-5 | 記録整理 (`CONTROL_MAPPING.md` / runbook 3 本 / DEPLOY_Q4 / 閉止注記 / 設計 §10・§12・§13 / 作業指示書 §11 / 本書) | 文書のみ (**2165** のまま) |

**集計行の出所**: 各 WP のコミットメッセージ末尾の `Root suite alone:` 行 (`git log` で確認できる)。いずれも**監督が完了ゲートで単独実行して得た実測値**であり、ゲートログは `{scratchpad}/wp0-gate2.log` / `wp12-gate.log` / `wp34-gate2.log` に残っている。**最終形のディレクトリ別内訳は `r2db-api/tests` 934 / `MitateDB-api/tests` 756 / `conformance-tests` 475 = 2165**。conformance は**本フェーズを通じて 475 のまま不変**である。

**`xfail` は 1 本も残っていない** — WP-0 が両 peer に 2 本ずつ登録した「適合 ≥ 1」「三者一致」の `xfail(strict=True)` は、**当該 peer の per-app script を出す WP (r2db = WP-3 / MitateDB = WP-4) と同一コミットで撤去**した。

正本の所在 (第13次から更新された箇所のみ):

- **本フェーズの実施設計** = `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` (**v1.4**)。§3 の D-1〜D-6 が確定事項、**§10 が静的規則と実 PG 確認の実測**、**§12 が台帳 (12.1 が各項目の現在形、LQ4-24〜LQ4-27 が本フェーズで新たに見えた項目)**、**§13 が実施記録**
- **発注と WP 分割** = `docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md` (**v1.2**、§11 に実施記録の要約)
- **配備手順** = `docs/work-orders/DEPLOY_Q4_20260905.md` (**新規、未実施**)。`DEPLOY_PHASE6_20260904.md` は撤回されず、§1.5 / §4 / §5 / §6 / §7 は本書からも参照する正本である
- **運用の正本 (両 peer)** = `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` **§16 / §17 (新設)**、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §1 / §2 / §7、`MitateDB-api/docs/cloud-run-cloud-sql.md` **§3.2b / §3.4b**
- **対応表** = `security/CONTROL_MAPPING.md` の **SI-02 / SI-10 / SI-12 / SI-14**。**SI-14 の点 (12) の "nothing enforces it" は置換した** (限定付き — 下記 §2 の残る限界を読むこと)

## 2. 到達した状態

### 2.1 「宣言の根拠」と「実際に効いている値」が同じ一次情報になった

**3 つの宣言が DB 側へ移った。**

1. **`visibility_lag_ms` (Q4 案 B、D-1)** — 書き手 role の `statement_timeout` / `idle_in_transaction_session_timeout` が **PostgreSQL の role 設定** (`ALTER ROLE … SET`) になった。control は宣言された各書き手 role の `pg_db_role_setting` から `max(statement + idle) + 1000` を導出し、**書き手プロセスは起動時に自 role の実効値が catalog 値と ms 整数で一致することを検査**して、食い違えば起動しない (F-9)。セッション `SET` は両 peer から撤去した。
2. **`coalescing_window_ms` と `surfaces` (D-2)** — platform 宣言表 `<registry>.platform_declarations` の行になり、**両プロセスが同じ 1 行を起動時に読む**。`surfaces` は 1 行なので「2 プロセスが別々の env を読んで食い違う」構造そのものが消えた (L6-5a)。
3. **書き手 role の特定 (D-2 (h))** — `audit_writer_roles` 行を platform 単発 migration が **`ALTER ROLE` と同じ psql 変数から同じトランザクションで** seed する。コード内の命名規則 (schema 名からの導出・接尾辞の書き換え) は両 peer から撤去した (F-13 が自 role の包含を検査する)。

**廃止 env 4 本** (`*_AUDIT_STATEMENT_TIMEOUT_MS` / `*_AUDIT_IDLE_TIMEOUT_MS` / `*_DATA_BASE_URL` / `*_CONTROL_BASE_URL`) は、**定義されているだけで (値によらず、空文字列を含む) 起動を拒否する** (F-1 / F-2)。互換シムもフォールバックも置いていない。

### 2.2 per-application upgrade の運用性 (L6-20 (f)、D-3〜D-5)

- **台帳**: 各 application DB の `public._<peer>_platform_upgrades`。所有は developer role、**runtime role は `SELECT` のみ** (依頼者裁定 U-2)、書きは provision DSN。`0003` テンプレートが新規 application に全番号を seed し、既存 DB は per-app upgrade script (r2db `0009` / MitateDB `0008`) が retrofit する。
- **一括適用**: `ops upgrade-applications` (provision DSN のみ、`--dry-run` / `--application` / `--script`、1 DB の失敗で止まらない、失敗 DB ごとに `REVOKE` の掃除文と psql stderr の tail、終了コード 0/1/2/3/4)。
- **可視化**: `ops upgrade-status` **のみ** (依頼者裁定 U-1。契約には載せない)。
- **検出時点**: 最初のリクエストではなく **cell open 時**。未適用の application の cell だけが **F-12** (`SERVICE_UNAVAILABLE`、未適用番号と `ops upgrade-applications` を明示) を返し、**プロセスは起動し、他の application は通常どおり serve する** (監督裁定 H-1)。
- **同期義務は静的検査が閉じる**: `{*_upgrade.sql の番号}` == `{0003 の seed}` == `{パッケージ定数}` の三者一致 (実測は r2db `{9}` / MitateDB `{6, 8}`)。

### 2.3 残る限界 4 点 (覆い隠さないこと)

1. **両プロセスが同じ platform データベースを見ていることは検証しない** (設計 §3.11 の 7、LQ4-16)。control にだけ古い platform DSN を渡す配備では L6-5a のドリフトが同じ形で再発する。**検出は配備後の `/capabilities` 突合のまま** (`DEPLOY_Q4_20260905.md` §4-1)。
2. **各プロセスが実効値を検査できるのは自 role についてだけである** (同 9、LQ4-15 (i))。control は `*svc_api` の catalog を読むが実効値は検証できない。
3. **検査は起動時スナップショットであり、pool が後から張った接続は検査されない** (同、LQ4-15 (ii))。**現配備に接続プーラがあるかは未確認**である。
4. **宣言変更時の過渡的なずれは残る** (同 10、LQ4-17)。危険な向きは再起動順序 (**縮めるときは data-plane 先、伸ばすときは control 先**) で避けるが、ずれ自体は消えない。

**台帳は運用の一次記録であって改竄不能な証拠ではない** (設計 §3.9) — 射程は既存 bookkeeping 表と同一である。

## 3. クライアント連携状態

**変更なし。一報は送らない** (依頼者判断 2026-09-03 以降不変)。**本フェーズは契約無変更であり、wire に現れる値も形も変わらない** — 変わったのは「その値がどこから来るか」と「食い違ったときに何が起きるか」だけである。第10次〜第13次 §3 がそのまま有効。

## 4. 次の一手 (優先順)

### 4-1. 本番適用 (運用者。監督は `gcloud` の秘密を扱わない操作のみ)

**正本は `docs/work-orders/DEPLOY_Q4_20260905.md`。** 順序が固定である — **migration → `ops` で宣言 → 廃止 env の除去 → 新コードで再起動 → `ops upgrade-applications` → `upgrade-status`**。飛ばすと「動くが宣言が嘘」ではなく**上がらない** (F-8 / F-3 / F-1 / F-2)。既定のまま適用すれば宣言値は現行と同一 (`visibility_lag_ms` = 11000、`coalescing_window_ms` = 60000、`surfaces` は現行の 2 本) であり、**挙動は変わらない**。

**運用者への申し送り 2 件**:

- **`r2db-api/deploy/scripts/part1_provision_host_and_db.sh` は Q4 に追随していない** — `0008` を当てず `ops declare-surfaces` も打たないので、この script だけで作った新規ホストは両プロセスとも起動しない。**当面は手順書 (`POSTGRES_PROVISIONING_RUNBOOK.md` §16) で手当てする** (設計 §12 LQ4-24)。
- **接続プーラの有無を実測して記録に足すこと** (LQ4-15 (ii))。

### 4-2. フェーズ7 (並行して進んでいる。main の履歴で確認できる範囲)

- **7-A は完了済み** — WP-3 (r2db 配備資産) `df35451`、WP-1 (公開規律とスキャナ) `393b9f1`、WP-2 (constraints と CI) `e1d33c3`、7-A の記録 `79ed0c9`。**CI (GitHub Actions、PostgreSQL 16 コンテナ、Python 3.11 / 3.12 の 2 job が required) が成立している。**
- **7-B (WP-4〜WP-8) の着手条件は「Q4 の main マージ後」であり、本フェーズの完了でその条件は満たされる。**
- **公開ゲート (WP-9)** の着手条件は **(g)(b) の完了**であり、残るのは **WP-6 ((b)(iii) `DeprecationWarning` の error 化と `httpx2` 移行)** だけである。すなわち **WP-9 は「Q4 マージ → WP-6 完了 → 依頼者の実行合図」で着手可能になる。**
- **フェーズ7 候補として残るのは (a)〜(e)** である。**(d) (r2db の `surfaces` 検証ヘルパの重複解消) は本フェーズ WP-1 で閉じた** ので、実質は (a)(b)(c)(e)。
- **依頼者確定待ちの 3 点 (α)(β)(γ)** は第13次 §4-2 のまま。**(γ) が確定するまで visibility の切替へ進めない。**
- **CI の集計行は Q4 で動く** — 7-A 時点の正本は `1868 passed, 4 xfailed` であり、Q4 マージ後は **2165 passed, 0 xfailed** になる。**`tally-consistency` job と 7-A の記録 (L7-17) の数値を、Q4 マージ後に現在形へ直す必要がある** (フェーズ7 側の作業)。

### 4-3. 台帳 (Q4 の未閉止項目)

**設計 §12.1 が各項目の現在形である。** 閉じたのは LQ4-1 / LQ4-2 / LQ4-3 / LQ4-5 / LQ4-7 / LQ4-10 / LQ4-12 / LQ4-13 / LQ4-19 / LQ4-22 / LQ4-23。**記録のまま残るのは** LQ4-4 (`ALTER ROLE … SET` の射程は監査書き込みに限られない = 運用者責任)、LQ4-6、LQ4-8、LQ4-9、LQ4-11 (本機構は共通 conformance では検証されない — HTTP plug の非対称)、LQ4-14 (失敗時に残る developer role membership)、**LQ4-15 / LQ4-16 / LQ4-17 (§2.3 の限界そのもの)**、LQ4-18 (一括適用の並行実行は保護されていない)、LQ4-20 (U-1「載せる」案の再検討前提)、LQ4-21。**本フェーズで新たに起票したのは LQ4-24 (配備 script の追随)、LQ4-25 / LQ4-26 / LQ4-27 (peer 非対称とテストの形)** である。

**依頼者判断待ちの項目は本フェーズでは増えていない。**

## 5. 本フェーズの裁定 (再審議しない)

**依頼者裁定 (2026-09-05、逐語は設計 §5)**

- **U-1**: per-application の upgrade 適用状態は **peer-local に留める**。共通契約は無変更 (1.6.0 のまま)。可視化は `ops upgrade-status` のみ。§6.2 は「採用せず」として記録に残す。
- **U-2**: 台帳表の runtime role 権限は **`SELECT` のみ**。data-plane は cell を開く時点で集合検査を行い、未適用があれば `ops upgrade-applications` を示して `SERVICE_UNAVAILABLE`。
- **U-3**: 宣言の読みは**起動時スナップショット**。ops で変えたら両プロセス再起動 (縮めるときは data-plane 先、伸ばすときは control 先)。

**監督裁定 (2026-09-05)**

- **D-2 (h)** — 書き手 role は宣言表 `audit_writer_roles` が特定する。**却下**: 命名規則依存 (本番で規則を外れた瞬間に無音で壊れる) / env で role 名を渡す (env 廃止の趣旨に反し真実が 2 つになる)。
- **F-3c の新設** — 「`surfaces` 行はあるが `control` が無く、それが control-plane プロセスである」は F-3 (行不在) とは別の状況であり、次に打つコマンドも違う。**確定文言は逐語で複製する。**
- **F-11 の絞り込み** — per-database 行のうち **timeout キーを含む行だけ**を対象にする。無関係な `ALTER ROLE … IN DATABASE … SET` で起動を止めない。
- **L6-17 を本フェーズで閉じる** — URL 形式検証の本体は `platform_declarations.validate_surfaces_value` 1 本。`main.py` / `control_main.py` / `ops.py` はこれを呼ぶ。
- **lifespan 遅延は不採用** — control の起動時検査を ASGI lifespan へ遅らせると **`--lifespan off` で丸ごと飛ばせる**。fail-fast は「配る前に止まる」ことが要点であり、起動オプション 1 つで無効化できる置き場は要件を満たさない。
- **H-1 (a)** — 未適用の application があっても**プロセスは起動する**。当該 application の cell だけが F-12 で refuse し、他の application は通常どおり serve する (`capabilities` も 200)。

## 6. 運用規律 (第13次 §4-3 を継承。本フェーズが足したもの)

- **完了ゲートは監督が単独実行し、その集計行だけを正本にする** (`ps` で他の pytest が 0 件であることを確認してから)。subagent には peer 別 suite と担当ファイルの conformance だけを回させる。
- **並行 worktree は「対」で使う** — 本フェーズは WP-1 / WP-2 と WP-3 / WP-4 をそれぞれ別 worktree で並行させた。**ローカル PostgreSQL の `max_connections = 300` が前提**である。
- **並行実装の同型性は「参照実装 → 整合パス」で担保する (本フェーズで確立)** — 並行させると本体は必ず食い違う。**MitateDB を参照実装として先に本体を固め、r2db は名前・シグネチャだけ先に合わせて動作を作り、統合パス (監督が取り込んだ後の 1 エージェント) で本体を MitateDB へ揃える。** 対応表 (`_ISOMORPHIC_TARGETS`) を触るのは**対の後半 WP だけ**とし、行数 pin も同一コミットで改める。これで並行 worktree の衝突点が無くなる。
- **subagent の書き込み制約を発注時に明示する** — 「変更してよいのは次のファイルだけ」「コード・テスト・migration・spec は触らない」「git 操作禁止」を毎回書く。**コミットは監督のみ。**
- **変異の復元は scratchpad backup + `sleep 3` 後の sha256 二重照合 + コミット前の変異文字列 grep** (Google Drive 同期ツリーのため)。`git checkout` は使わない。
- **push 前に `git log --format='%an <%ae>'` で `r2fish` / noreply のみを確認する。commit → push → main merge は 1 セット。**
- **`{scratchpad}` への参照を製品コード・テストに残さない** — 本フェーズは WP-3 / WP-4 の新規ファイルに 7 件残っていたのを完了前に除去した (公開リポジトリの宙づり参照)。**文書側の既存参照は対象外**である。

## 7. 教訓の追加 (前書全項継承に追加)

- **「宣言を DB へ移す」変更の本体は、移すことではなく『食い違ったら止まる』ことである。** 本フェーズが env を表へ移しただけなら、真実の置き場が変わっただけで嘘の宣言は同じように出せた。効いているのは **F-7 / F-9 / F-10 / F-11 / F-13 の起動時検査**であり、その検査を**起動オプション 1 つ (`--lifespan off`) で飛ばせる置き場に置く案を却下した**ことがこの設計の要である。**fail-fast は「どこに置くか」で強さが決まる。**
- **並行実装は「同じ設計」からでも必ず食い違う。** WP-1 / WP-2 は同じ設計文書から出発して、**書き手 role 名の導出をそれぞれ別の命名規則で実装した** (schema 名からの導出 / `current_user` の接尾辞書き換え)。どちらも動くが同型ではなく、しかも**両方とも本番で規則を外れた瞬間に無音で壊れる**形だった。裁定は「どちらかに揃える」ではなく **「導出をやめて宣言表から読む」** ことであり、これは同型性の問題としてではなく**設計の問題として**現れた。**並行実装の食い違いは、しばしば設計の穴を指している。**
- **限定を落とすと記録が過大主張になる。** SI-14 の点 (12) は「解消した」と書けば嘘になる — 閉じたのは 2 プロセスの env 不一致であって、**両プロセスが同じ platform DB を見ていること自体は今も検証していない**。WP-5 の完了条件は「置換文言が『同一の platform データベースを前提に』という限定を含むこと」を**差し戻し条件として明記**していた。**「閉じた」と書くときは、閉じていない部分を同じ段落に書く。**
- **配備資産は文書と別の速度で古くなる。** フェーズ7 WP-3 が作った `part1_provision_host_and_db.sh` は、その 1 日後に出た Q4 の `0008` を知らない。**runbook を直しても script は直らない** — 配備資産は「文書の一部」ではなく**追随を要する成果物**として台帳に載せた (LQ4-24)。
