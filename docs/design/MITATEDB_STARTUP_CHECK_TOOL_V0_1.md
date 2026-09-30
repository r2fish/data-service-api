# MitateDB の起動時の検査 (F-16 / F-18) の検算を道具に移す 設計メモ（v0.5）

## 0. 版数と依頼者裁定

- **v0.1 (2026-09-30)** 起票。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-116** (`RM`:466。v0.2 までの `:467` は `f7dc503` の木の行)。Class D、規模 M、設計レビュー 1 回 (`OC` §1.7 の 50)。
- **v0.2 (2026-09-30)** 設計レビュー 1 の指摘 F1〜F14 への監督裁定 (全件「直す」) と v0.1 §12 の監督裁定 1〜7 を §3〜§10 に織り込む。D-4 を書き直し、§9 を作り直す。記録は §12。
- **v0.3 (2026-09-30)** 再確認レビュー (設計 v0.2、担当観点 A・B) の指摘 1〜12 への監督裁定 (11 件「直す」、指摘 12 は両論の (甲) を採る) と §12.3 の監督裁定 1〜3 を §0、§2、§3.2、D-1、D-4〜D-10、§5、§6、§8、§9、§10 に織り込む。§9 に 46a〜46d を足し、#22 の変異を替える。記録は §12.4。
- **v0.4 (2026-09-30)** 実装時の監督裁定を織り込む: コードレビュー 1 (D-1・D-4 の lazy fetch・§5 の `control-revisions-missing`・§9 #6 M6b・#46e)、WP-2 の疑義 (D-6 の `declaration.current` の 3 値・§9 #46f・§10 (9) の clean checkout)、§10.10 版 10 の受理レビュー (§9 #46g)、§9 #26 の註。§13 に監査照合の逐語。裁定の出所は作業指示書 §7.3〜§7.8。
- **v0.5 (2026-09-30)** §11 の依頼者判断が出た。依頼者裁定 2026-09-30 (逐語): 「版 10 を受理する。(ii) で進めてください」。§10.8 の §10.10 の行だけを「10 / accepted / 10 / 作業指示書 §6.1 / 2026-09-30」に書き換えた ((ii))。条件 7 の byte 基準は更新: `### 10.6`〜`### 10.9` 直前の sha256 は `3058f81b4190eb89bd80969bd7c85a7b1f5b135f670068adc603957b0793e0fc` (旧 `b44422ecdd46923c26931afb8a67c4b4ee1fa0d7bac2d73a365317c9d1529279`。変わった行は §10.8 の表の 1 行だけ)。
- 依頼者裁定 (逐語。再審議しない、`OC` §1.7 の 51):
  - 2026-09-29「本番の値は分からないので、確かめる手順の形で進めてください」
  - 2026-09-30「推奨の (1) と (3) の組み合わせで進めてください」((1) = 起動を拒む検査の検算を道具に移す項目を起票し、§10.10 の受理はその後)
  - 2026-09-30 監督の問い 1「着手条件に『本番の image の source ref と max_connections が分かること』を含めるか」、問い 2「Class D で進めてよいか」に対し:「1は含めない、2はDで進めてください」
- 行番号の木: src・tests・migrations・runbook・台帳は worktree `r116` (local main `ab20f4e`、契約 1.12.0) の木。設計が行番号を引く `PD`・`CFG`・`MAIN`・`CC`・`http.py`・`OPS`・`CR`・migrations は `f7dc503..ab20f4e` で不変 (v0.2 までの木 `f7dc503` の行番号がそのまま成り立つ)。古い世代は `git show <sha>:<path>` の行。
- 公開規律: 数値は本リポジトリの現物の値と合成値だけ。本番の値を含まない (`OC` §1.9)。

**略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`H0929F2` = `docs/archive/docs/work-orders/HANDOVER_20260929_FABLE2.md`、`CR` = `MitateDB-api/docs/cloud-run-cloud-sql.md`、`PD` = `MitateDB-api/src/mitatedb_api/platform_declarations.py`、`CFG` = `.../config.py`、`MAIN` = `.../main.py`、`CC` = `.../control_composition.py`、`OPS` = `.../ops.py`、`TINV` = `MitateDB-api/tests/test_ops_inventory.py`、`M0012` / `M0014` = `MitateDB-api/migrations/0012_role_connection_limits.sql` / `0014_role_connection_limits_rollout.sql`。

## 1. 問題

- `CR` §10.10.1 step 6 は、`process_ceilings` を宣言する前に、その宣言の下で起動しうる全 revision の起動時の検査 F-16 / F-18 を紙で 2 回検算させる (`CR`:3738-3812)。世代の判別は grep の件数を人が読む (`CR`:2662-2704)。
- 受理レビュー 3 回と確認レビュー 1 回が毎回違う穴を見つけた (`H0929F2`:335-389、教訓 (ix) `H0929F2`:93)。文を直し続けても収束しない。検算を道具の実行に置き換える。

## 2. 守るべき条件

1. 契約 (1.12.0。v0.2 の 1.11.0 は `f7dc503` の版)・conformance・Security Invariants・data plane の挙動を変えない。`PD` の F-16 / F-18 の関数の挙動を変えない。
2. 道具は DB を読むだけ (inventory と同じ read-only の接続と確認)。書き込まない。本番の値を前提にしない。
3. 需要を小さく数えない。決められないときは `unknown`、足りないときは `blocked`。`confirmed` 以外が 1 つでもあれば非 0 で終了し、stdout に明示の総合判定を出す。失敗した読み (git、DB、入力) が「確認できた」と同じ出力にならない。
4. 入力は運用者が明示で宣言する。省略を既定値で黙って埋めない (env の「未設定」も明示で宣言させる)。
5. 範囲外の code の世代を推測で通さない。世代を positively に同定できない source ref は `unknown`。
6. 現行の code (G3) の式は `PD` の実物の関数・定数を呼ぶか境界一致のテストで固定し、道具と起動時の検査が同じ revision に違う答えを言わない。
7. `CR` の `### 10.6` から `### 10.9` の直前まで (`CR`:2861-3000) は 1 byte も変えない (§10.8 の受理記録の表を含む)。
8. `inventory` の既存の出力・終了コード・項目 (8) の挙動を変えない (`TINV` の 140 件が固定)。
9. r2db は対象外。peer の同型性テストの対象集合を変えない。
10. 実 SHA 以外の本番の値を書かない。リポジトリ自身の commit SHA は可。

## 3. 現物の事実

### 3.1 現行 (G3) の検査と呼び出し元

| 事実 | 出所 |
|---|---|
| 定数: `_API_ROLE_STORE_COUNT` 2、`_CONTROLPLANE_ROLE_POOL_FLOOR` 16、`_AUDITREADER_ROLE_POOL_FLOOR` 4。`_POOL_SIZE_HEADROOM` 2、`DEFAULT_THREAD_LIMIT` 4 | `PD`:923、:933、:940、`CFG`:304、`http.py`:252 |
| F-16 の床: api = 2 × p × D、controlplane = 16 × C、auditreader = 4 × C (class 間は max)、application の runtime / developer = p × D (`=` で代入)。role は grant で同定し表の owner を除く | `PD`:1066-1103 |
| F-16 の比較: `pg_roles` に無い role と `-1` は通す。名前順で最初に床を下回った role で `code="F-16"` を投げる。床を返す関数は無い | `PD`:1105-1117 |
| F-18: 下限 = D × (2p + (登録 ≥ 1 なら 2p)) + C × 16 (`headroom_lower_bound`、純関数)。登録は `applications` の `count(*)` (role が NULL の行も数える)。`max_connections` ほか 3 設定を `pg_settings` から読み、3 行未満は F-18 の失敗。下限 + 2 つの予約 > `max_connections` で失敗 (等号は通す) | `PD`:1230-1255、:1258-1268、:1274-1300、:1361-1390 |
| Data: p = `role_pool_size(thread_limit)`、thread_limit は `MITATEDB_THREAD_LIMIT` (未設定・空は 4、正の整数でなければ起動失敗)。F-16 は `role_classes={"api"}`、`application_ids` = `MITATEDB_SERVE_APPS` | `MAIN`:313、:339、:388、:482-490、`CFG`:307-332、:368-370 |
| Control: p は同じ読み方。F-16 は controlplane、`MITATEDB_AUDIT_DSN` が truthy なら auditreader も。application role は見ない | `CC`:212-235 |
| `process_ceilings` は DB の宣言の行から読む (env ではない)。`MITATEDB_PLATFORM_POOL_SIZE` は F-16 / F-18 の入力にならない | `MAIN`:388-389、`PD`:433-464 |
| inventory の接続: autocommit、`default_transaction_read_only = on`、lock / statement timeout、`SHOW transaction_read_only` の読み返し。role の class の発見は `_inventory_role_classes` | `OPS`:2208-2245、:2280-2306 |
| inventory の終了コード: 全 confirmed = 0、判定が出て confirmed でない = 2、判定の前の失敗と入力の拒否 = 1 (DB 接続の前)。argparse の usage error と未知の引数を 1 にするのは inventory だけ | `OPS`:2756-2769、:3009-3057、:3060-3091、:3442-3468 |

### 3.2 世代の表

| 世代 | first-parent の範囲 (代表 ref) | F-16 の床 | F-18 の下限 | pool の入力 x と env の読み方 |
|---|---|---|---|---|
| G0 | `9361f1b` より前 | 無し | 無し | — (D-4 の G0 の規則で同定。`9361f1b^1` = `c387b32`、`1f1ef2b^1` = `448c660` (`PD` が無い)) |
| G1 | `9361f1b` 〜 `da8d807` の前 | api 2x、app x、controlplane 16、auditreader 4 (process の倍率なし)、`-1` は通す | 無し | x = `MITATEDB_MAX_CONCURRENCY`。未設定・空・非整数は既定 32、0 と負は拒まない (`da8d807:MitateDB-api/src/mitatedb_api/main.py`:159-170、`da8d807:.../config.py`:77、`9361f1b:.../control_composition.py`:176-180) |
| G2 | `da8d807` 〜 `41b9fa6` の前 (`da8d807`、`443a79a`) | G1 と同じ | D × (2x + [2x]) + C × 16 | G1 と同じ (`443a79a:.../main.py`:345、:411-418)。`443a79a` 以降は `MITATEDB_THREAD_LIMIT` が在るが F-16 / F-18 は読まない |
| G3 | `41b9fa6` 〜 HEAD (branch の `96985e80` から) | §3.1 | §3.1 | x = p = `MITATEDB_THREAD_LIMIT` + 2 (§3.1) |

- G1 / G2 の Control は Control 自身の `MITATEDB_MAX_CONCURRENCY` を同じ規則で読み、F-18 は D・C を変えずに同じ下限を計算する (`CR`:3754-3763)。
- `41b9fa6..HEAD` に指紋の組 (i)〜(v) を変える変更は無い (基点 `ab20f4e` で再実測: `9361f1b^1..ab20f4e` の first-parent 284 commit、Data 12 / Control 11)。v0.2 の「`MitateDB-api/src` の変更は無い」は、台帳 R-114 の `ab20f4e` が src の 5 file (指紋の file ではない) を変えたので偽 (再確認 11、v0.3 で訂正)。branch の `5e1eeac` は F-16 を `verify-declarations` にだけ持ち、起動時の呼び出しは無い (first-parent には現れない)。
- `PD` が first-parent に入ったのは `1f1ef2b`、`CC` は `26dff2a` (`26dff2a^1` = `785b23e` に `CC` は無い)。
- runbook §10.4.3 の「OLD basis」の形の確認が通るのは G2 のうち `443a79a` 以降だけ (`CR`:2497-2556)。これは inventory 項目 (8) の入力の条件で、本道具の世代とは別物である。

### 3.3 migration が置く `CONNECTION LIMIT`

| role | `0012` | `0014` | 出所 |
|---|---|---|---|
| `mitatedbsvc_api` | 68 | 132 | `M0012`:114、`M0014`:89 |
| `mitatedbsvc_controlplane` | 20 | 36 | `M0012`:115、`M0014`:90 |
| `mitatedbsvc_auditreader` | (触らない) | 12 | `M0014`:91 |
| 既存の application の runtime / developer (role が NOT NULL の行) | 36 | 68 (`pg_roles` に在るものだけ) | `M0012`:126-137、`M0014`:103-118 |

- step 7 は `0012` `0013` `0014` を 1 回で当て、`0012` の後で止まると 68 / 20 / 36 のまま残る (`CR`:3872-3904)。

## 4. 決定

### D-1 subcommand `ops startup-checks`
- `inventory` の項目にしない (項目 (8) は rollout の最悪の合計という別の計算、`OPS`:2544-2753)。
- 判定の本体は新しい module `MitateDB-api/src/mitatedb_api/startup_checks.py`。`OPS` は subparser の登録・`cmd_startup_checks`・`main()` の未知の引数の分岐だけ。却下: `OPS` の中に置く (3,501 行の module をさらに伸ばし、`security/CONTROL_MAPPING.md` の `OPS` の行参照を動かす範囲が広がる)。新しい module が L1 語彙の走査の除外集合の guard (`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`:870-875) に当たらないことを WP-1 で実測する。
- import の向き (再確認 8): 接続 (`_inventory_connect`・`_inventory_confirmed_read_only`) と role の class の読み (`_inventory_role_classes`) は `OPS` の `cmd_startup_checks` が行い、`startup_checks` は `ops` を import しない (接続と class の表を関数の引数で受ける)。`startup_checks` は `.platform_declarations`・`.config` を import してよい (どちらも `ops` を import しない)。

### D-2 入力
- 引数: `--data D` `--control C` (正の整数)、`--revisions FILE` (§5)、`--repository PATH` (git の checkout)。DSN は inventory と同じ `MITATEDB_PROVISION_DSN`。`MITATEDB_SERVE_APPS` は入力にしない (D-6)。
- revision ごと: `name`、`plane` (`data` / `control`)、`kinds` (`serving` / `rollback_target` / `env_only_revision` / `candidate` / `other` の空でない集合。`other` = 上の種別に入らないが起動しうる revision。例: tag で届く revision、`minScale` ≥ 1 の revision)、`source_ref` (40 桁の小文字 hex)、`env` の `MITATEDB_MAX_CONCURRENCY` と `MITATEDB_THREAD_LIMIT` (生の文字列か、未設定を示す `null`。key の欠落は拒否)、control は `audit_dsn_configured` (= その revision の env の `MITATEDB_AUDIT_DSN` が空でない文字列。値そのものは書かせない)。

### D-3 種別の網羅 (plane ごと)
- `declared_absent` の語彙: `data.serving`・`data.rollback_target`・`data.env_only_revision`・`data.other`・`control` (plane 全体が未配備)・`control.serving`・`control.rollback_target`・`control.env_only_revision`・`control.candidate`・`control.other`。
- 語彙の各項は、一覧に在るか `declared_absent` に在るかのどちらか一方でなければ入力の拒否 (終了コード 1、DB 接続の前。`--control-not-deployed` と同じ考え方)。`data.candidate` は語彙に無い: Data の `candidate` が一覧に 1 件以上なければ拒否 (step 6 は候補の ceiling を宣言する step)。`revisions` が空も拒否。
- `control` を宣言したら Control の revision は一覧に置けず、`control.*` も書けない。宣言しなければ `control.*` の各項を上の規則で要求する。
- 一覧が完全であることは運用者の宣言である (§10 Known gaps (1))。

### D-4 世代の同定 (git の object を読む)
- v0.1 の採る案 (甲) (式の切片の `ast.dump` の sha256) は設計レビュー 1 の F1 (dump が Python の版で違う) と F2 (切片が式の全部を運ばない) で覆した (2026-09-30、v0.2)。v0.1 の却下 (乙) (file 全体の hash) の却下理由は F2 で取り下げ、下の指紋の組の (i)〜(iii) として採る。
- 読み方: `git -C PATH cat-file -e <ref>^{commit}`、`git ls-tree -r <ref> -- MitateDB-api/src` (blob の SHA と `.py` の列挙)、`git cat-file -p` で `http.py` と src の全 `.py` を読む。fetch も checkout もしない (作業木と `.git` を書かない)。 partial clone の lazy fetch は git の env `GIT_NO_LAZY_FETCH=1` で止める (git 2.44 以降で有効。古い git では無視され、partial clone では欠けた object の読みが fetch になりうる。docstring に前提として書く。コードレビュー 1 の裁定 6)。ref 不在と git の非 0 終了は `unknown` (理由 `ref-not-found` / `git-failed`、D-8)。
- **指紋の組** (plane ごと): (i) `PD` の全文、(ii) `CFG` の全文、(iii) plane の起動 module (Data = `MAIN`、Control = `CC`) の全文、(iv) `http.py` の `DEFAULT_THREAD_LIMIT` の代入文 (在れば。無ければ「無し」)、(v) `MitateDB-api/src` の全 `.py` で 2 つの検査の関数名 (`check_role_connection_limits`・`check_max_connections_headroom`) を参照する箇所 (Name・Attribute・import の alias。Call の関数はこのどれかとして数える) の (file、囲む最も内側の def の名前 (無ければ `<module>`)、件数) の整列した一覧。
- Python の版に依らない (F1): (i)〜(iii) は git の blob の SHA (`git rev-parse <ref>:<path>`)。(iv) は `ast` を代入文の範囲 (行・桁) を得るためだけに使い、切り出した source の bytes の sha256。(v) は名前と件数だけ。`ast.dump` は使わない。src の `.py` のどれかが parse できなければ `unknown` (`source-unparseable`)。
- **既知の表**: 行 = (plane、指紋の組、世代、代表 ref (本リポジトリの SHA。省略可 = `None`、§12.3 の 1))。module の定数 (literal) に持つ。表に無い組は `unknown` (`fingerprint-not-in-table`)。first-parent に無い ref (branch の commit) の行も持てる (F4)。代表 ref の無い行は作業木の組の行だけ (再確認 1 (c))。(i)〜(iii) の file を変える commit は、作業木から計算した組を代表 ref 無しで表に足し (テスト (2) を同じ commit で緑にする)、次にその表を触る変更セットでその組を持つ commit の SHA を埋める。機械検査は置かず、コードレビューの照合事項とする (§12.3 の 1)。
- 表の行数の実測 (起草時、`9361f1b^1..HEAD` の first-parent 283 commit、HEAD = `f7dc503`): 相異なる組は **Data 12 (G1 7・G2 4・G3 1)、Control 11 (G1 6・G2 4・G3 1)**。2 つの世代にまたがる組は無い。branch の `5e1eeac` の組は表に無い。基点 `ab20f4e` (first-parent 284 commit) で再実測して同じ (再確認 11)。
- 運用の事実 (Known gaps ではない。module docstring に書く): (i)〜(iii) の file を変える commit は表に行を足す。テスト (2) が赤で知らせる。「推測で通さない」(条件 5) の代価として受け入れる。足す行の世代 (再確認 1 (a)): (i)〜(iii) を変える commit は、式が既存の G3 の行と同じときだけ新しい行を G3 にする。式が変わるときは新しい世代 (G4) を足し、既存の G3 の行はその行の代表 ref の `PD`・`CFG` の式を持つ凍結した世代として道具に残す (G1 / G2 と同じ扱い)。
- **G0** は表でなく性質で positively に同定する (F9): plane の起動 module が ref に在り、src の全 `.py` が parse でき、(v) が空。`PD`・`CFG`・`http.py` の不在は G0 の妨げにしない。起動 module が無い ref は `unknown` (`startup-module-missing`。その ref からは service の image を作れない)。部分文字列では数えない (`9361f1b^1` の src には `UTF-16` の部分一致が 5 件ある)。加えて、src の全 `.py` に `"F-16"`・`"F-18"`・2 つの関数名のどれかに等しい文字列定数 (`ast.Constant` の str) が無いこと (再確認 3)。判定の順は、表を先に引き、一致が無いときだけ G0 の性質を見る。
- **テスト**: (1) 表の代表 ref を持つ各行について、代表 ref から組を再計算し、表の literal と一致。CI の 3.11 と 3.12 の両 leg (`.github/workflows/ci.yml`:174) で同じ literal に一致することで、Python の版に依らないことを持つ。(2) 作業木の file (import される `mitatedb_api` の file。blob の SHA は `git hash-object` と同じ計算で、書き込まない) から plane ごとの組を計算し、表の G3 の行と一致 (F5)。道具の実行時は ref の object だけを読む。(3) `9361f1b^1..HEAD` の first-parent を歩いた相異なる組 ⊆ 表の行 (F4)。CI の root suite の job は `fetch-depth: 0` (`ci.yml`:178)。履歴が読めない環境では skip せず fail させる (`OC` §1.3 の 26)。
- 帰結: WP-1 は (i)〜(iii) の file と `http.py` を触らず、src で 2 つの検査の関数名を参照しない (参照すると (v) が変わり、テスト (2) が赤になる)。
- 却下: (甲) v0.1 の切片の `ast.dump` (上記 F1・F2)。推移閉包の切片 / 起動関数全体 (設計レビュー 1 の両論): 「全文」の方が単純で漏れが無い (F2)。(丙) grep の件数 (現 runbook): 受理 3 必須 3・確認 1 の穴をそのまま持つ。(丁) 祖先関係・日付: 代理指標 (`OC` §1.7 の 52)、branch の commit から作った image を誤判定する。(戊) 古い code を道具の実行時に checkout して実行: 作業木を書き換え、依存の版が違う。

### D-5 世代ごとの式と env
- 世代の表 (§3.2) を道具が持つ。G3 は `CFG.thread_limit_from_env` と `CFG.role_pool_size` を実物で呼ぶ。未設定 (`null`) は世代の既定 (G1 / G2 = 32、G3 = 4) を当て、出力に「宣言値」と「当てた値」を並べる。G1 / G2 は `int()` による寛容な parse (失敗 → 32、0・負はそのまま) を再現する。テストは代表 ref の `_optional_int` ほかの読み手を git の object から取り出してテストの中で実行し、入力 `"1_000"`・`" 7"`・`""`・`"0"`・`"-3"`・`"abc"` で道具と一致を固定する (F12)。
- 読み手の取り出し方 (再確認 10): Control の G1 / G2 の読み手は `build_control_service` の中の inline の文 (`9361f1b:MitateDB-api/src/mitatedb_api/control_composition.py`:176-180) なので、テストは `_raw_declared_concurrency` の代入から `except ValueError` の節までを `ast` で切り出して `exec` する (`FoundationConfig.max_concurrency` = 32 を与える)。Data の G1 / G2 は `_optional_int` を同じ方法で切り出す。
- Data の G3 の起動 module の読み手は `MAIN._thread_limit_from_env` (`MAIN`:214、:313) であり、`CFG.thread_limit_from_env` との一致は `MitateDB-api/tests/test_threadpool_offload.py::test_thread_limit_from_env_agrees_with_the_shared_config_reader` が固定している。道具は `CFG` の読み手を呼び、この試験を前提にする (再確認 10)。
- G3 の不正値は起動失敗なので、その revision の両検査を `blocked` (理由 `startup-fails-on-env`)。`-1` は全世代で F-16 を通す。
- `CR`:2461 の「古い基準の revision の `concurrency` を既定値から宣言してよい例外」(R-113 WP-7 設計 `docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md`:277 の裁定 20) は、step 6 については「未設定を宣言し、道具がその世代の既定値を当てる」入力の規則に置き換わる。image の `ENV` と container の command / args は道具が読めないので、運用者が確かめて `env` に反映する事項として残り、`CR` §10.4.4 の確認を指す。

### D-6 DB から読む値と判定
- 実物の読み手を呼ぶ: `PD` の `_read_connection_headroom_settings` (3 設定)・`_count_registered_applications` (NULL の行も数える)・宣言の表の `process_ceilings` の 1 row の読み + `validate_process_ceilings_value` (現在の `process_ceilings`。報告用、判定に使わない。行が無ければ `not-declared`、読みか検証の失敗は `unreadable`。`read_platform_declarations` は全 row を読み `surfaces` 未宣言の step 6 では必ず失敗するので使わない。WP-2 の疑義 4 への監督裁定 2026-09-30、§9 #46f)、`OPS` の `_inventory_role_classes` (grant による class)。加えて `runtime_role IS NOT NULL AND developer_role IS NOT NULL` の行と `pg_roles.rolconnlimit` を読む。接続は `OPS` の `_inventory_connect` と `_inventory_confirmed_read_only` (`OPS` 側で呼ぶ。D-1 の import の向き)。読み返しが `on` でなければ終了コード 1。v0.2 は `_inventory_role_classes` を `PD` の読み手と書いた (実物は `OPS`:2280。再確認 8、v0.3 で訂正)。
- Data の F-16 は登録済みの全 application の role を見る (`MITATEDB_SERVE_APPS` で絞らない。起動時の検査は serve する application だけ、`MAIN`:339、:482-486)。Known gaps (4)。
- F-18 は実際の登録数に依らず「登録 ≥ 1」の下限で判定し、実際の登録数と登録 0 の下限を併記する (F3)。Known gaps (6)。
- 3 設定が揃わないときは、F-18 を持つ revision (G2 / G3) の `f18` を `blocked` (理由 `headroom-settings-missing`) とし、F-16 の判定は続ける (F13)。
- 対象 class に role が 1 つも無い (Data の api、Control の controlplane、`audit_dsn_configured: true` の Control の auditreader) ときは、その F-16 を `unknown` (理由 `no-role-of-class`)。起動時の検査はこの場合通る。Known gaps (5)。

### D-7 migration を当て直す窓
- F-16 は role ごとに「窓の値」= min(現在値、`0012` の値、`0014` の値) に対して判定する (`-1` は無制限として min から外す。migration が触らない role は現在値だけ)。
- `0012` / `0014` の値は grant で同定した class に当てる (F6): api = 68 / 132、controlplane = 20 / 36、auditreader = (触らない) / 12、application の role = 36 / 68。migration は literal の名前に当てるので、名前の違う role には道具の方が厳しい。Known gaps (7)。
- 窓を見ない判定 (現在値だけ) も併記し、総合は窓の判定を使う。
- 値の出所: **採る案 (b)** 定数を module に持ち、テストで `M0012`・`M0014` の `ALTER ROLE` の行から抜いた値と一致を固定する。却下 (a) 実行時に migration の file を parse する: 道具の失敗の経路が増え、運用者の checkout と道具の版は同じなので得るものが無い。却下 (c) migration を transaction の中で当てて rollback: 書き込み (条件 2)。
- 却下 (d) (再確認 12 の (乙)) migration の台帳から `0014` の適用を読み、窓を閉じる入力を足す: `0012` / `0014` は platform の migration で自身の適用を記録しない (`_mdb_platform_upgrades` は application の upgrade の台帳) ので、適用の有無を DB から positively に読めない。窓は step 6 の時点の判定とする (D-9)。

### D-8 出力と終了コード
- §6。revision × 検査ごとに `judgment` と計算に使った数。`checks_evaluated: ["F-16", "F-18"]` を出し、他の起動時の検査は見ていない旨を `known_gaps` に置く (F14)。総合 `overall` = `blocked` が 1 つでもあれば `blocked`、無くて `unknown` があれば `unknown`、他は `confirmed`。終了コードは inventory と同じ規則 (0 / 2 / 1)。stdout は JSON 1 個 (sort_keys)、終了コード 1 のときは stdout に何も出さず stderr に固定文言。
- argparse の usage error と未知の引数は終了コード 1、DB 接続の前 (inventory の `p.error` の上書きと `main()` の分岐と同じ形、`OPS`:3442-3468) (F8)。
- 閉じた語彙 (再確認 5):
  - revision の `reason` (世代の同定の理由): `ref-not-found` / `git-failed` / `startup-module-missing` / `source-unparseable` / `fingerprint-not-in-table` / `null` (同定できた)。
  - 検査 (`f16` / `f18`) の `reason`: `startup-fails-on-env` / `headroom-settings-missing` / `no-role-of-class` / `check-not-in-generation` / `generation-unknown` / `null`。
  - `coverage` の key = D-3 の語彙 10 項 + `data.candidate` の 11 項。値 = `listed` / `declared-absent` / `plane-declared-absent` (`control` を宣言したときの `control.*` の 5 項)。
  - 入力の key `declared_absent` (snake) と出力の値 `declared-absent` (kebab) の綴りの違いは規約による: key は snake、値は kebab (`known_gaps` の値と同じ)。

### D-9 runbook
- `CR` §10.10.1 step 6 の F-18 と F-16 の段 (`CR`:3738-3812) を道具の実行に置き換える。step 6 は、道具に渡した D / C と `declare-process-ceilings` に渡す値が同じであることを、道具の出力の `declaration.proposed` と突き合わせる手順を持つ (F14)。§10.10 の他の言及 (版の説明 `CR`:3078-3091、Preconditions `CR`:3274-3284、findings の表、step 7 の窓 `CR`:3898-3904、step 11、step 13、Rollback `CR`:4238-4247、2 段の rollout `CR`:3814-3871) は道具の実行を指す形に直す。§10.10 の版 9 → 10。
- `CR` §10.4.4 step 7 の F-16 / F-18 の出現の数えの段 (`CR`:2689-2704) を、道具の `generation` / `present` を指す形に直す (F10)。基準の grep と Dockerfile の確認は残す。条件 7 の範囲の外。
- コマンドは書く前に実行して出力を確かめる (`H0929F2`:95)。語の機械的な置き換えをしない (`H0929F2`:94)。文面の起草は WP-1 の後。
- 窓の時点 (再確認 12、(甲)): step 7 以降の言及 (step 11、step 13、Rollback、2 段の rollout) は step 6 の道具の実行の出力を指し、道具を再実行しない。道具の窓は step 6 の時点の判定である。(乙) の却下は D-7。

### D-10 テスト
- 新しいファイル `MitateDB-api/tests/test_ops_startup_checks.py` (`TINV` と名前の系統を分ける)。完了条件 1 つに変異 1 つ (`OC` §1.5 の 33、40)。DB は `TINV` と同じ実 PostgreSQL の使い捨て prefix の形。境界の試験の入力は D ≥ 2、C ≥ 2、D ≠ C (F11)。
- G3 の境界一致は実物の `check_role_connection_limits` / `check_max_connections_headroom` と、床 と 床 − 1 (F-18 は等号 と +1) で判定が一致することで固定する (`TINV`:2806 の `_f16_and_inventory_agree_at_boundary` の形)。G1 / G2 は代表 ref の `PD` を git の object から読みテストの中で module として読み込み、同じ境界で一致を固定する (古い `PD` の import は `.identifiers` と `.pg_timeouts` だけ)。これは D-4 の却下 (戊) (道具の実行時の checkout) に当たらない。履歴が読めない環境では skip せず fail させる。
- G3 の境界一致の比べ方 (再確認 4): #1〜#5 は、実物の側の `pool_size` を、試験が同じ env から `CFG.thread_limit_from_env` と `CFG.role_pool_size` で独立に計算して渡す。比べるのは道具の `current_judgment` (窓を見ない判定)。role の現在値 (`rolconnlimit`) を床 / 床 − 1 に置く。
- 世代の式の一致は代表 ref を持つ表の全行に広げる (§9 #46a、再確認 1 (b))。

## 5. 入力ファイルの形 (合成値)

```json
{
  "format": "mitatedb-startup-checks/1",
  "declared_absent": ["data.env_only_revision", "data.other", "control.env_only_revision", "control.other"],
  "revisions": [
    {"name": "data-rev-a", "plane": "data", "kinds": ["serving", "rollback_target"],
     "source_ref": "1111111111111111111111111111111111111111",
     "env": {"MITATEDB_MAX_CONCURRENCY": null, "MITATEDB_THREAD_LIMIT": null}},
    {"name": "data-rev-b", "plane": "data", "kinds": ["candidate"],
     "source_ref": "2222222222222222222222222222222222222222",
     "env": {"MITATEDB_MAX_CONCURRENCY": "32", "MITATEDB_THREAD_LIMIT": "4"}},
    {"name": "control-rev-a", "plane": "control", "kinds": ["serving", "rollback_target", "candidate"],
     "source_ref": "3333333333333333333333333333333333333333",
     "env": {"MITATEDB_MAX_CONCURRENCY": null, "MITATEDB_THREAD_LIMIT": null},
     "audit_dsn_configured": true}
  ]
}
```

- 拒否 (終了コード 1、DB 接続の前。コードレビュー 1 の裁定 5 で `control` を宣言せず Control の revision が 0 件の入力 (`control-revisions-missing`) を足した): JSON として読めない、`format` 違い、未知の key、`env` の key の欠落、`source_ref` が 40 桁の小文字 hex でない、`name` の重複、`plane` / `kinds` / `declared_absent` の未知の値、`revisions` が空、Data の `candidate` が 0 件、D-3 の網羅の欠け、一覧と `declared_absent` の両方に在る種別、`control` の宣言と Control の revision または `control.*` の併記、Data に `audit_dsn_configured`、Control に無い、`kinds` が空または重複、`env` の値が文字列でも `null` でもない、`audit_dsn_configured` が bool でない (再確認 10)、`--data` / `--control` が正の整数でない、argparse の usage error と未知の引数。

## 6. 出力の形と終了コード

```json
{"overall": "blocked",
 "checks_evaluated": ["F-16", "F-18"],
 "declaration": {"current": {"control": 1, "data": 1}, "proposed": {"control": 1, "data": 4}},
 "database": {"max_connections": 200, "registered_applications": 0,
              "reserved_connections": 0, "superuser_reserved_connections": 3},
 "coverage": {"control": "listed", "control.candidate": "listed", "control.env_only_revision": "declared-absent",
              "control.other": "declared-absent", "control.rollback_target": "listed", "control.serving": "listed",
              "data.candidate": "listed", "data.env_only_revision": "declared-absent", "data.other": "declared-absent",
              "data.rollback_target": "listed", "data.serving": "listed"},
 "known_gaps": ["revision-list-is-declared", "image-env-and-command-are-declared", "inputs-outside-fingerprint",
                "serve-apps-not-read", "no-role-of-class-is-unknown", "f18-judged-at-one-registration",
                "window-applied-by-class", "other-startup-checks-not-judged",
                "uncommitted-checkout-not-detected"],
 "revisions": [
  {"name": "data-rev-a", "plane": "data", "generation": "G2", "reason": null,
   "pool_input": {"env": "MITATEDB_MAX_CONCURRENCY", "declared": null, "applied": 32, "x": 32},
   "f16": {"present": true, "judgment": "confirmed", "reason": null,
           "window_judgment": "confirmed", "current_judgment": "confirmed",
           "roles": [{"role": "mitatedbsvc_api", "class": "api", "floor": 64, "current_limit": 132, "window_limit": 68}]},
   "f18": {"present": true, "judgment": "blocked", "reason": null, "registered_applications_judged": 1,
           "lower_bound": 528, "lower_bound_without_registrations": 272,
           "reserved_total": 3, "required": 531, "max_connections": 200}}]}
```

- `present: false` は、世代を同定し (表の行か G0 の性質)、その世代がその検査を持たないときだけ (G0 の両検査、G1 の F-18)。そのときの `judgment` は `confirmed`、`reason` は `check-not-in-generation`。世代が `unknown` の revision は `generation: null`、両検査 `present: null`・`judgment: "unknown"` (`reason` は `generation-unknown`)。v0.2 の「G0 を positively に同定したときだけ」は G1 の F-18 と矛盾した (再確認 5、v0.3 で訂正)。
- 例の `revisions[0]` は G2 (x = 32) なので、f16 の床は D を掛けない 64 (窓 68 で `confirmed`)。`overall` は f18 の `blocked`。v0.2 の例の床 256 は G3 の式だった (再確認 5、v0.3 で訂正)。
- 宣言を下げる方向は判定しない (`declaration` に並べるだけ)。
- 終了コード: 全部 `confirmed` = 0、判定が出て `confirmed` でないものがある = 2、入力の拒否 (§5)・DSN 無し・read-only の読み返しの失敗・DB の失敗・`--repository` が git の checkout でない = 1。git の読みの失敗は revision 単位の `unknown` (= 2)。

## 7. 受理レビューの指摘と道具の対応

「道具」= 本道具が受け止める。「文」= runbook の文に残る。出所は `H0929F2`:341-388。

| 指摘 | 対応 |
|---|---|
| 受理 1 必須 1 古い revision の F-18 | 道具 (全 revision の F-18) |
| 受理 1 必須 2 古い基準の式が成り立つ ref | 道具 (F-16 / F-18 の世代を D-4 で同定)。項目 (8) の形の確認 (`CR`:2497-2556) は文 |
| 受理 1 必須 3 (env の許可表と基準の規則)・5 (step 13 の Control の env)、受理 2 必須 4 (「直し方が無い」理由の手段)・任意 a〜h・観察 i、受理 3 必須 1 (2 段目の入口の括弧書き)・4 (step 10 の legacy の名)・8 (空の射影)・任意 a〜k (g を除く)、実装報告 4 疑義 (b)・確認 疑義 2 (legacy の名の確認の単位)、確認 4 (2 段の rollout が F-16 も解くと読める)・5・6・7・10 | 文 |
| 受理 1 必須 4 古くなった数と文 | 文 (step 6 の数は道具の出力に置き換わる) |
| 受理 1 必須 6 digest の基準の確認 | 道具 (F-16 / F-18 の世代)。項目 (8)・(9) の基準の列は文 |
| 受理 1 任意 (`0016` の行 / step 10 の env / 「rejects three」) | 文 (§10.6 は条件 7 で不変) |
| 受理 1 論点 既定値の宣言の例外 | 道具 (step 6 は D-5 の入力の規則)。項目 (8) の `--concurrency` の例外は文 |
| 受理 2 必須 1 新しい code の F-18 | 道具 (G3 を含む全 revision) |
| 受理 2 必須 2 古い code の F-18 の Control と `concurrency` | 道具 (Control の revision、世代の既定値) |
| 受理 2 必須 3 2 段の rollout の入口・範囲・前提 | 文 (範囲外) |
| 受理 2 必須 5 形の確認の 3 本目 | 文 (§10.4.3、項目 (8)) |
| 受理 2 必須 6 読まない入力 (command / args、image の `ENV`) | 文 (D-5。運用者が確かめて `env` に反映) |
| 受理 2 必須 7 版 9 の説明 | 文 (版 10 で書き直す) |
| 受理 2 必須 8・9 項目 (8) の例と K = 0 | 文。step 6 の登録の数は道具が `count(*)` で読む |
| 受理 2・3 両論 (既定値の例外 / 2 段の rollout) | 依頼者 (§10.10 の受理のとき) |
| 受理 3 必須 2 step 7 の間の F-16 | 道具 (D-7 の窓) |
| 受理 3 必須 3 失敗した `git show` が確認と同じ出力 | 道具 (git の失敗は `unknown`、条件 3)。但し: argparse の失敗が判定と同じ終了コード 2 になる穴 (設計レビュー 1 F8) は D-8 で 1 にして塞ぐ |
| 受理 3 必須 5 `x` と「登録」の読み方 | 道具 (世代の表と `count(*)`)。但し: 登録 0 行のときの穴 (設計レビュー 1 F3) は D-6 の「登録 ≥ 1」の判定で塞ぐ |
| 受理 3 必須 6 Dockerfile の事実の使い方 | 文 (項目 (8) の引数、image の `ENV` の確認) |
| 受理 3 必須 7 改行を含む inline code | 道具 (step 6 の分)。§10.4.3 の分は文 |
| 受理 3 任意 g §10.6 の `0015` の行 | 文 (条件 7 で本作業では変えない) |
| 実装報告 4 疑義 (a)・実装担当の追記 許可表の Control の床 | 文。道具は Control の固定の床を世代の表で持つ |
| 確認 1 F-16 だけ持つ ref | 道具 (G1 の表の行で同定)。但し: 設計レビュー 1 F1・F2 を直した D-4 の指紋が前提 |
| 確認 2 `control_composition.py` の実在の確認 | 道具 (Control は `CC` を読む。無い ref は `unknown`)。項目 (9) の分は文 |
| 確認 3・8 fenced でない期待出力・inline code | step 6 の分は道具、他は文 |
| 確認 9 F-16 の精度 (`c`、role の分け方、`-1`) | 道具 |
| 確認 疑義 1 c > 34 の例 | 道具 (数値は出力で見る。文の例は WP-2 で扱いを決める) |

## 8. WP の分け方の案

WP は直列 (WP-2 は WP-1 の実物の出力を要する)。並行が無いので重なりの表は置かない。

| WP | 内容 | 触ってよいパス |
|---|---|---|
| WP-1 道具とテスト | D-1〜D-8、D-10。Known gaps と D-4 の運用の事実を docstring に | `MitateDB-api/src/mitatedb_api/startup_checks.py` (新規)、`MitateDB-api/src/mitatedb_api/ops.py` (subparser・dispatch・`main()` の未知の引数の分岐だけ)、`MitateDB-api/tests/test_ops_startup_checks.py` (新規)、`tools/tests/test_sql_statement_safety_scan.py` (`_EXPECTED_DISCOVERED_MODULES["mitatedb"]` の 1 entry)、`tools/tests/test_leaf_import_direction.py` (`NON_LEAF_MODULE_ENTRIES` の mitatedb に `startup_checks.py` の 1 entry と理由 1 行。`ops` 以外の `platform_declarations` / `config` を import するので non-leaf) |
| WP-2 runbook | D-9。コマンドは合成の local cluster で実行してから書く | `MitateDB-api/docs/cloud-run-cloud-sql.md` の §10.10 (`CR`:3076-) と §10.4.4 step 7 の F-16 / F-18 の段 (`CR`:2689-2704) だけ |
| WP-3 記録 | `security/CONTROL_MAPPING.md` の行参照の追随と主張、台帳 R-116、作業指示書の受理の記録 (§11 (i)) | `security/CONTROL_MAPPING.md`、`docs/design/ROADMAP_POST_PHASE7_V1.md`、作業指示書 |

- 道具の引数の例: `tools/dev/pt.py -C <WT> -- MitateDB-api/tests/test_ops_startup_checks.py MitateDB-api/tests/test_ops_inventory.py -q`、`tools/dev/pt.py -C <WT> -- tools/tests/test_sql_statement_safety_scan.py tools/tests/test_leaf_import_direction.py -q` (新規 file を `git add -N` した後。根の gate は `tools/tests` を含まないので、監督は `finalize.py --tools-tests` を使う。再確認 2)、`tools/dev/mutate.py "$SP/r116-wp1-mutations.json" -C <WT>` (1 変異 1 entry)。
- WP-3 の完了条件 61a (再確認 7。監査照合 `git diff`): `CM`:1072 の「checks that on paper」の主張を道具の実行を指す形に、`CM`:1294 の「not accepted at 9」を版 10 の受理の状態に直し、`CM` の版の行を 3.8 → 3.9 にする (`CM` = `security/CONTROL_MAPPING.md`)。

## 9. 完了条件と変異の対応の案 (WP-1)

境界の試験は D = 3、C = 2。試験の ref: G0 = `c387b32` (`9361f1b^1`)・`448c660` (`1f1ef2b^1`、`PD` 無し)、表に無い組 = `5e1eeac`、起動 module 無し = `785b23e` (`26dff2a^1`、Control)。

- #16〜#19 は、各 class の role の現在値 (`rolconnlimit`) を `0012` の値より上 (`0014` の値、#18 は `-1`) に置いてから判定する。#19 は 現在値 ≥ 床 > 窓 となる role (C = 2 の controlplane: 現在 36、床 32、窓 20) で総合が `blocked` になることを見る (再確認 9)。
- 合成の git repo は試験の `tmp_path` に `git init` して作る (#28・#46c が同じ fixture を使う。再確認 3・10)。
- #12〜#15・#25〜#28・#46c の試験は `reason` の語 (D-8) を assert する (再確認 5)。#1〜#5 の比べ方は D-10 (再確認 4)。

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | G3 の api の床が実物の F-16 と床 / 床 − 1 で一致 | 道具の api の床から D を外す |
| 2 | G3 の application の role の床が同上 | application の床から D を外す |
| 3 | G3 の controlplane の床が同上 | controlplane の床から C を外す |
| 4 | G3 の auditreader の床が同上 | auditreader の床から C を外す |
| 5 | G3 の F-18 が実物と等号 / +1 で一致 | 道具の比較の `>` を `>=` に |
| 6 | G1 / G2 の F-16 が代表 ref の `PD` と境界で一致 (api と application の role。コードレビュー 1 の裁定 1) | G1 の api の床に D を掛ける (M6)、application の床を 0 に (M6b) |
| 7 | G2 の F-18 が代表 ref の `PD` と等号 / +1 で一致 | G2 の下限から登録の項 [2x] を落とす |
| 8 | 登録 0 行でも F-18 は「登録 ≥ 1」の下限で判定し、登録 0 の下限を併記 | `max(count, 1)` を `count` に |
| 9 | 出力の登録数は role が NULL の行も数える | 数えを NOT NULL の行に絞る |
| 10 | G1 / G2 の parse が代表 ref の読み手と 6 入力で一致 | 空白を含む値を非整数とみなす |
| 11 | 未設定は世代の既定 (G1 / G2 = 32、G3 = 4) | G2 の既定を 4 に |
| 12 | G3 の env の不正値は両検査 `blocked` (`startup-fails-on-env`) | 不正値を既定 4 に落とす |
| 13 | Data の api の role が 0 件なら F-16 は `unknown` (`no-role-of-class`) | 0 件を `confirmed` に |
| 14 | `audit_dsn_configured: true` で auditreader の role が 0 件なら `unknown` (`no-role-of-class`) | auditreader の 0 件の検査を外す |
| 15 | 3 設定が揃わないとき F-18 を持つ revision は `blocked` (`headroom-settings-missing`)、F-16 は判定され、終了コード 2 | 欠けで例外を投げる (終了コード 1) |
| 16 | 窓 = min(現在、`0012`、`0014`)。api・controlplane・auditreader・application の窓を各々 assert | 窓から `0012` を外す |
| 17 | 窓の値は grant の class で当てる (prefix 付きの fixture の role に当たる) | 窓を `mitatedbsvc_*` の名前で当てる |
| 18 | `-1` は窓の min から外す | `-1` を min に含める |
| 19 | 総合は窓の判定 | 総合に `current_judgment` を使う |
| 20 | `0012` / `0014` の定数が migration の行と一致 | 定数 68 を 69 に |
| 21 | テスト (1): 代表 ref を持つ各行の再計算 = 表の literal | (iv) の切り出しを代入の値の式だけに狭める |
| 22 | テスト (2) Data: 作業木の組 = G3 の行 | `MAIN` にコメント行を 1 行足す (blob の SHA が変わり、テスト (2) Data だけが赤。v0.2 の変異「`CFG` の `_POOL_SIZE_HEADROOM` を 3 に」は M46a と重なるので替えた。再確認 1) |
| 23 | テスト (2) Control: 作業木の組 = G3 の行 | `CC` の `if env.get("MITATEDB_AUDIT_DSN"):` を `if True:` に |
| 24 | テスト (3): first-parent の相異なる組 ⊆ 表の行 | 表から 1 行を消す |
| 25 | 不在の ref は `unknown` (`ref-not-found`) | `cat-file -e` の失敗を G0 として扱う |
| 26 | `5e1eeac` は G0 にならず `unknown` (`fingerprint-not-in-table`)。試験は、起動 module 以外の file だけが検査関数を参照し文字列定数を持たない合成 ref も持つ (`5e1eeac` 単独では G0 の文字列定数の検査 (再確認 3) が先に `unknown` にするため、変異は合成 ref で赤になる。実装時の監督裁定 2026-09-30) | (v) の走査を起動 module だけに狭める |
| 27 | 起動 module の無い ref (`785b23e` の Control) は `unknown` (`startup-module-missing`) | 起動 module の不在を G0 として扱う |
| 28 | 合成の git repo (#46c と同じ fixture) に parse できない `.py` を置いた ref は `unknown` (`source-unparseable`) | parse できない file を参照 0 として扱う |
| 29 | `PD` の無い `448c660` は G0 (`present: false`) | G0 の条件に `PD` の存在を足す |
| 30 | `c387b32` は G0 (ast で数える) | 数えを部分文字列 `F-16` に |
| 31 | D-3 の網羅の欠けは終了コード 1 | 網羅の検査を外す |
| 32 | `control` と `control.*` の併記は終了コード 1 | 併記の検査を外す |
| 33 | `revisions` が空は終了コード 1 | 空の検査を外す |
| 34 | Data の `candidate` 0 件は終了コード 1 (`data.candidate` は語彙に無い) | `data.candidate` を語彙に足す |
| 35 | `env` の key の欠落は終了コード 1 | 欠落を `null` として扱う |
| 36 | 入力の拒否は DB に接続しない | 入力の検査を接続の後に移す |
| 37 | argparse の usage error (必須の引数の欠落) は終了コード 1 | usage error の上書きを外す |
| 38 | 未知の引数は終了コード 1 | `main()` の分岐から `startup-checks` を外す |
| 39 | `unknown` を含めば終了コード 2・`overall` = `unknown` | `unknown` のとき 0 を返す |
| 40 | read-only の接続と読み返し | 読み返しを省く |
| 41 | 出力に `checks_evaluated` と `known_gaps` の 9 項 | `checks_evaluated` を出さない |
| 42 | §5 の残りの拒否の項と `--repository` が git の checkout でないときの終了コード 1 が各 1 件の試験を持つ | 監査照合 (試験名の一覧の逐語を設計に残す) |
| 43 | CI の 3.11 と 3.12 の両 leg でテスト (1)〜(3) が緑。3.12 の leg は push の再開後に main の run で照合する (§12.3 の 3、`OC` §2 の 20) | 監査照合 (両 leg の集計行の逐語を設計に残す) |
| 44 | 新しい試験に skip / xfail が無い | 監査照合 (`git grep` の出力の逐語を設計に残す) |
| 45 | `TINV` 140 件が不変で緑 | 監査照合 (`pt.py` の集計行の逐語を設計に残す) |
| 46 | `PD` の F-16 / F-18 の関数、同型性の対象集合、(i)〜(iii) の file と `http.py` が不変 | 監査照合 (`git diff --stat` の逐語を設計に残す) |
| 46a | 代表 ref を持つ表の全行について、その ref の `PD` (G3 は `CFG` も) を git の object から読み込み、その行の世代の道具の式と、床 / 床 − 1 (F-18 は等号 / +1) で判定が一致する (#6・#7 を全行に広げる) | 作業木の `CFG` の `_POOL_SIZE_HEADROOM` を 2 → 3 (旧 G3 の行の ref は 2 のままなので赤) |
| 46b | `tools/dev/pt.py -C <WT> -- tools/tests/test_sql_statement_safety_scan.py tools/tests/test_leaf_import_direction.py -q` が failed 0・skipped 0 (新規 file を `git add -N` した後) | 監査照合 (`pt.py` の集計行の逐語を設計に残す) |
| 46c | 合成の git repo (起動 module と、改名した関数で `code="F-16"` を投げる `PD` を持つ) の ref は G0 にならず `unknown` (`reason` = `fingerprint-not-in-table`) | 文字列定数の検査を外す |
| 46d | G3 の `pool_input.x` = `role_pool_size(thread_limit)` | x から `role_pool_size` を外す (x = thread_limit) |
| 46e | git の呼び出しの env に `GIT_NO_LAZY_FETCH=1` が在る (コードレビュー 1 の裁定 6) | env の設定を外す |
| 46f | `declaration.current` は `process_ceilings` の 1 row の読みで `not-declared` / 数値 / `unreadable` の 3 値 (WP-2 の疑義 4 への裁定) | `not-declared` の分岐を `unreadable` に |
| 46g | git の呼び出しの env に `GIT_NO_REPLACE_OBJECTS=1` が在る (運用者の clone の `refs/replace` を無効にする。受理レビューの道具側 10 への裁定) | env の設定を外す |
| 47 | 本表に対応の無い行が無い | 監査照合 |

WP-2 の完了条件は変異を持たない監査照合を主とする: `CR` の `### 10.6` から `### 10.9` の直前までの sha256 の前後一致の逐語、runbook に書いた各コマンドの実行出力の逐語。

## 10. 範囲外と Known gaps

- 範囲外 (文に残す): 宣言を下げる方向 (step 6 の「downward direction」、`CR`:3730-3736)、2 段の rollout を正式の進め方とするかの採否、`max_connections` をいくつにするか、worker 数と宣言の比較 (step 6 の worker-count の検査)、項目 (8) の形の確認 (`CR`:2497-2556)。r2db。
- Known gaps (module docstring と出力の `known_gaps`。(4)〜(7) は起動時の検査より厳しい向きのずれ):
  - (1) revision の一覧の完全さは運用者の宣言 (道具は platform 層を読めない。受け止めるのは runbook §10.4 の読みと D-3 の網羅)。
  - (2) image の `ENV` と command / args は読めない (受け止めるのは §10.4.4)。
  - (3) 指紋の組の外の module の変更で、(i)〜(iii) の file も (v) の一覧も変えずに検査の入力を変えるものは指紋に現れない (受け止めるのは変更時のレビュー)。
  - (4) Data の F-16 は `MITATEDB_SERVE_APPS` で絞らず、登録済みの全 application の role を見る。
  - (5) 対象 class の role が 0 件の F-16 は `unknown` (起動時の検査は通す)。
  - (6) F-18 は実際の登録数に依らず「登録 ≥ 1」の下限で判定する。
  - (7) 窓の値は名前でなく class で当てる。
  - (8) F-16 / F-18 以外の起動時の検査 (例: worker 数の検査) は見ていない。
  - (9) 運用者の checkout の未 commit の変更 (道具が実行する G3 の実物を含む) は検出しない。道具は ref の object だけを読む (受け止めるのは runbook の「source ref は attested の digest から取る」の手順。§12.3 の 2)。 runbook step 6 は `git status --porcelain` が空の checkout から実行することを要求する (WP-2 の疑義 6 への裁定 2026-09-30)。

## 11. 未確定で依頼者判断待ち

- **解決 2026-09-30 (v0.5)**: 依頼者裁定 「版 10 を受理する。(ii) で進めてください」 により (ii) を採り、§10.8 の §10.10 の行だけを書き換えた。以下は判断前の両論 (履歴)。
- §10.10 を版 10 にすると、`CR` §10.8 の表の §10.10 の行 (`CR`:2999、「Current version 9」) が現物と合わなくなる。§10.8 は条件 7 の範囲の中で変えられない。(i) §10.8 を変えず、受理の記録は作業指示書に置く / (ii) §10.8 のその 1 行だけ変える (§10.6・§10.7 の表の受理を無効にしない、と依頼者が裁定する)。本作業は (i) で進め、(ii) は完了時に依頼者に挙げる。

## 12. 設計レビュー 1 の記録

v0.1 への設計レビュー 1 (2026-09-30) の指摘と監督裁定。全件「直す」。本文は v0.2 で反映済み。

| ID | 指摘の要旨 | 裁定 | 反映した節 |
|---|---|---|---|
| F1 | `ast.dump` の出力が Python の版で違い、指紋の表が 1 つの版でしか合わない | `ast.dump` を使わない。source の bytes の sha256。literal の固定を CI 3.11 / 3.12 の両方で。parse できない source は `unknown` | D-4、§9 #21・#28・#43 |
| F2 | 切片が式の全部を運ばず、式が変わっても指紋が同じになる | 指紋の組 = `PD`・`CFG`・起動 module の全文 (blob の SHA)、`DEFAULT_THREAD_LIMIT` の代入文、src 全体の検査関数名の参照の一覧。表の行が増えるのは運用の事実として docstring に | D-4、§9 #22・#23・#26、§10 (3) |
| F3 | 登録 0 行のとき登録 0 の下限で判定し、最初の登録で全 revision が起動を拒む | 「登録 ≥ 1」の下限で判定し、登録 0 の下限を併記。厳しい向きのずれとして開示 | D-6、§6、§9 #8、§10 (6) |
| F4 | テスト (3) の等号が branch と main で違う集合になり、branch の image を表に足せない | テスト (3) は ⊆。表は first-parent に無い ref の行も持てる | D-4、§9 #24 |
| F5 | テスト (2) が HEAD の object を読むと、作業木の変異が見えない | テスト (2) は作業木の file から計算。道具の実行時は ref の object だけ | D-4、§9 #22・#23 |
| F6 | 窓を名前で当てると prefix 付きの fixture で platform role に当たらない | 窓は grant で同定した class に当てる。厳しい向きのずれとして開示 | D-7、§9 #16・#17、§10 (7) |
| F7 | Data の candidate を absent と宣言でき、空の一覧が `confirmed`。tag / minScale の revision が種別に無い | 空は拒否。`data.candidate` は absent にできない。種別 `other` と `data.other` / `control.other` | D-2、D-3、§5、§9 #33・#34 |
| F8 | argparse の usage error と未知の引数が終了コード 2 | 終了コード 1 (inventory と同じ形) | D-1、D-8、§8、§9 #37・#38 |
| F9 | G0 の同定が path 不在の規則と食い違い、部分一致の `F-16` が `UTF-16` に当たる | ast で数える。起動 module が無ければ `unknown`。`5e1eeac` で固定 | D-4、§9 #26〜#30 |
| F10 | runbook §10.4.4 step 7 の F-16 / F-18 の数えが第 2 の判定経路として残る | WP-2 の範囲に足し、道具を指す形に | D-9、§8 |
| F11 | §9 の完了条件と変異の対応の抜け | 各床・G2 の F-18・寛容な parse・NULL の行・no-role-of-class・窓の `-1`・plane の制約・終了コード 1 に変異 | D-10、§9 |
| F12 | 寛容な parse の再実装が `int()` と食い違いうる | 代表 ref の読み手をテストの中で実行し 6 入力で一致を固定 | D-5、§9 #10 |
| F13 | `pg_settings` が 3 行でないと道具全体が終了コード 1 | F-18 を持つ revision ごとに `blocked`、F-16 は続ける | D-6、§9 #15 |
| F14 | 対象の検査の名が出力に無い。宣言値との突き合わせが無い。`audit_dsn_configured` の意味が未定義 | `checks_evaluated` と `known_gaps`。step 6 で `declaration.proposed` と突き合わせる。`audit_dsn_configured` = 空でない文字列、auditreader 0 件は `unknown` | D-2、D-6、D-8、D-9、§6、§9 #14・#41、§10 (8) |
| §7 | 受理 3 必須 3・5、確認 1 の 3 行に但し書きが要る | reviewer の文面のとおり足す | §7 |

v0.1 §12 の監督裁定 (2026-09-30):

| # | 裁定 | 反映した節 |
|---|---|---|
| 1 | `MITATEDB_SERVE_APPS` は入力にしない (道具は登録済みの全 application の role を見る。厳しい向き) | D-2、D-6、§10 (4) |
| 2 | 網羅は plane ごと (`declared_absent` の語彙、`control` と `control.*` の制約) | D-3、§5、§6 |
| 3 | `kinds` は集合 | D-2 |
| 4 | 対象 class に role が 0 件の F-16 は `unknown` (厳しい向き) | D-6、§10 (5) |
| 5 | 判定の本体は新しい module `startup_checks.py` | D-1 |
| 6 | G1 / G2 の境界一致のテストは代表 ref の `PD` を git の object から読む。却下 (戊) は道具の実行時の checkout を指す。履歴が読めなければ fail | D-10、§9 #44 |
| 7 | G3 の env の不正値は `blocked`、git の読みの失敗は revision 単位の `unknown`、`--repository` が git の checkout でないときは終了コード 1 | D-5、§6、§9 #12・#42 |

### 12.3 v0.2 の起草報告への監督裁定 (2026-09-30)

1. **表の行の代表 ref は省略できる (`None`)。** (i)〜(iii) の file を変える commit は、作業木から計算した組を代表 ref 無しで表に足す (テスト (2) を同じ commit で緑にする)。テスト (1) は代表 ref を持つ行だけを再計算する。代表 ref の無い行は、次にその表を触る変更セットで、その組を持つ commit の SHA を埋める (`tools/dev/ledger.py --check` のような機械検査は置かず、コードレビューの照合事項とする)。テスト (3) は変わらない (⊆)。
2. 道具は運用者の checkout の未 commit の変更を検出しない (道具は ref の object だけを読む)。Known gaps に 1 行足す (受け止めるのは runbook の「source ref は attested の digest から取る」の手順)。
3. 起草報告の 3〜6 はそのままでよい。#43 (3.12 の leg) は push の再開後に main の run で照合する (`OC` §2 の 20)。

### 12.4 再確認レビュー (2026-09-30) の記録

設計 v0.2 への再確認レビュー (担当観点 A・B) の指摘と監督裁定。指摘の全文と裁定の文面は監督の scratchpad に保管 (追跡外)。裁定の内容は下表と本文が正本。本文は v0.3 で反映済み。

| ID | 要旨 | 裁定 | 反映した節 |
|---|---|---|---|
| 1 | G3 の行の世代が式の同一性で固定されず、式を変える将来の commit で古い G3 の revision を新しい式で判定する | 直す。式が同じときだけ G3 の行、変わるときは G4 を足し旧 G3 の行を凍結した世代に。代表 ref を持つ全行の式の一致 (#46a)。#22 の変異を替える。代表 ref の無い行は作業木の組の行だけ (機械検査は置かない) | D-4、D-10、§9 #22・#46a |
| 2 | 新しい src module で赤になる `tools/tests` の 2 つの固定が WP-1 のパスに無い | 直す。2 file を WP-1 のパスに。#46b (監査照合)。監督は `finalize.py --tools-tests` | §8、§9 #46b |
| 3 | G0 の性質が関数名の参照 0 だけで、改名・文字列での参照を持つ ref が偽の G0 になる。表と G0 の順が無い | 直す。文字列定数の検査を足し、表を先に引く。#46c | D-4、§9 #46c |
| 4 | #1〜#5 の比べ方が未定。env → p の誤りが見えず、#3 は窓のせいで一致しない | 直す。実物の側の p を試験が独立に計算し、`current_judgment` で比べる。#46d | D-10、§9 #46d |
| 5 | §6 の例 (G2 の f16 の床) と `present: false` の文が本文と食い違う。`reason`・`coverage` の語彙が無い | 直す。例と文を訂正。閉じた語彙を D-8 に。試験は `reason` の語を assert | D-4、D-8、§6、§9 #12〜#15・#25〜#28 |
| 6 | §12.3 の 1・2 が本文に織り込まれていない | 直す。代表 ref は省略可、#21 は代表 ref を持つ行、Known gaps (9) | D-4、§6、§9 #21・#41、§10 (9) |
| 7 | WP-3 に `CM` の主張の更新と版の行の完了条件が無い | 直す。61a (監査照合 `git diff`) | §8 |
| 8 | D-6 の `_inventory_role_classes` の所在の誤り。`startup_checks` と `ops` の import の向きが未定 | 直す | D-1、D-6 |
| 9 | #16〜#19 の変異が赤になるための fixture の現在値が書かれていない | 直す | §9 |
| 10 | 入力の型の拒否の欠け、#28 の合成 repo、G1 / G2 の読み手の取り出し方、G3 の読み手の前提 | 直す | D-5、§5、§9 #28 |
| 11 | §3.2 の「src の変更は無い」が基点 `ab20f4e` で偽。行番号の木 | 直す | §0、§2、§3.2、D-4 |
| 12 | (不確実) step 7 の後に道具を再実行すると、窓で controlplane が `blocked` のまま残る | 裁定 (甲): step 7 以降の言及は step 6 の出力を指し、再実行しない。(乙) は却下 (理由は D-7)。観察として引き継ぎ書にも残す | D-7、D-9 |

§12.3 の監督裁定 1〜3 も v0.3 で本文に織り込んだ: 1 → D-4・§9 #21、2 → §6・§9 #41・§10 (9)、3 → §9 #43。

## 13. 監査照合の逐語 (WP-1 の 42〜46・46b、2026-09-30、`OC` §1.5 の 40)

- #42 試験名の一覧 (76 id、`--collect-only -q`):

```
test_ops_startup_checks.py::test_current_generation_api_floor_agrees_with_the_real_check_at_the_boundary
test_ops_startup_checks.py::test_current_generation_application_floor_agrees_with_the_real_check_at_the_boundary
test_ops_startup_checks.py::test_current_generation_controlplane_floor_agrees_with_the_real_check_at_the_boundary
test_ops_startup_checks.py::test_current_generation_auditreader_floor_agrees_with_the_real_check_at_the_boundary
test_ops_startup_checks.py::test_current_generation_headroom_agrees_with_the_real_check_at_equality_and_one_over
test_ops_startup_checks.py::test_frozen_generation_role_floors_agree_with_the_check_of_a_representative_ref
test_ops_startup_checks.py::test_frozen_generation_headroom_agrees_with_the_check_of_a_representative_ref
test_ops_startup_checks.py::test_every_row_with_a_representative_ref_agrees_with_that_refs_check_functions
test_ops_startup_checks.py::test_headroom_with_no_registration_is_judged_at_one_and_shows_the_zero_bound
test_ops_startup_checks.py::test_registered_applications_count_includes_a_row_whose_roles_are_null
test_ops_startup_checks.py::test_frozen_generation_parse_agrees_with_the_readers_of_a_representative_ref
test_ops_startup_checks.py::test_an_unset_env_gets_the_default_of_the_generation
test_ops_startup_checks.py::test_current_generation_pool_size_is_the_shared_reader_result
test_ops_startup_checks.py::test_an_invalid_current_generation_env_blocks_both_checks[abc]
test_ops_startup_checks.py::test_an_invalid_current_generation_env_blocks_both_checks[0]
test_ops_startup_checks.py::test_an_invalid_current_generation_env_blocks_both_checks[-1]
test_ops_startup_checks.py::test_no_api_role_makes_the_data_f16_unknown
test_ops_startup_checks.py::test_no_auditreader_role_makes_an_audit_configured_control_f16_unknown
test_ops_startup_checks.py::test_no_controlplane_role_makes_the_control_f16_unknown
test_ops_startup_checks.py::test_the_current_declaration_is_read_from_its_one_row_in_three_states
test_ops_startup_checks.py::test_missing_headroom_settings_block_f18_and_still_judge_f16_with_exit_2
test_ops_startup_checks.py::test_window_is_the_minimum_of_current_and_both_migration_values_per_class
test_ops_startup_checks.py::test_window_is_applied_by_the_class_of_the_grant_not_the_name_of_the_role
test_ops_startup_checks.py::test_minus_one_is_left_out_of_the_window_minimum
test_ops_startup_checks.py::test_overall_judgment_is_the_window_judgment
test_ops_startup_checks.py::test_migration_constants_equal_the_values_in_the_migrations
test_ops_startup_checks.py::test_every_row_with_a_representative_ref_is_recomputed_from_that_ref
test_ops_startup_checks.py::test_working_tree_data_fingerprint_is_the_current_generation_row
test_ops_startup_checks.py::test_working_tree_control_fingerprint_is_the_current_generation_row
test_ops_startup_checks.py::test_every_first_parent_fingerprint_is_in_the_table
test_ops_startup_checks.py::test_a_ref_that_does_not_exist_is_unknown_with_ref_not_found
test_ops_startup_checks.py::test_git_is_run_with_lazy_fetch_disabled
test_ops_startup_checks.py::test_a_failed_git_read_is_unknown_with_git_failed
test_ops_startup_checks.py::test_a_ref_not_in_the_table_is_not_generation_zero
test_ops_startup_checks.py::test_a_ref_without_the_startup_module_is_unknown
test_ops_startup_checks.py::test_an_unparseable_source_file_makes_the_ref_unknown
test_ops_startup_checks.py::test_a_ref_without_platform_declarations_is_generation_zero
test_ops_startup_checks.py::test_generation_zero_counts_names_in_the_syntax_tree_not_substrings
test_ops_startup_checks.py::test_a_renamed_check_that_raises_the_code_label_is_not_generation_zero
test_ops_startup_checks.py::test_the_known_table_has_one_row_per_plane_and_fingerprint
test_ops_startup_checks.py::test_a_gap_in_the_kind_coverage_is_rejected
test_ops_startup_checks.py::test_control_and_its_items_declared_absent_together_are_rejected
test_ops_startup_checks.py::test_an_empty_revision_list_is_rejected
test_ops_startup_checks.py::test_a_data_candidate_is_required_and_cannot_be_declared_absent
test_ops_startup_checks.py::test_a_missing_env_key_is_rejected
test_ops_startup_checks.py::test_a_rejected_input_never_opens_a_database_connection
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[not-json]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[top-level-not-an-object]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[unknown-top-level-key]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[unknown-revision-key]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[missing-revision-key]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[unknown-env-key]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[source-ref-uppercase]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[source-ref-short]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[duplicate-name]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[unknown-plane]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[unknown-kind]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[empty-kinds]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[duplicate-kinds]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[unknown-declared-absent]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[env-value-not-a-string]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[audit-dsn-not-a-bool]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[control-without-audit-flag]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[data-with-audit-flag]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[listed-and-declared-absent]
test_ops_startup_checks.py::test_the_remaining_rejections_exit_1_before_any_connection[control-revisions-missing]
test_ops_startup_checks.py::test_a_proposed_ceiling_that_is_not_a_positive_integer_exits_1
test_ops_startup_checks.py::test_an_unreadable_revisions_file_exits_1
test_ops_startup_checks.py::test_a_repository_that_is_not_a_git_checkout_exits_1
test_ops_startup_checks.py::test_a_missing_required_argument_is_a_usage_error_with_exit_1
test_ops_startup_checks.py::test_an_unrecognised_argument_exits_1
test_ops_startup_checks.py::test_a_report_with_an_unknown_revision_exits_2_and_is_unknown_overall
test_ops_startup_checks.py::test_all_confirmed_exits_0
test_ops_startup_checks.py::test_the_connection_is_read_only_and_a_failed_read_back_exits_1
test_ops_startup_checks.py::test_the_report_names_the_checks_and_nine_known_gaps_in_the_documented_order
test_ops_startup_checks.py::test_a_control_plane_declared_absent_is_reported_as_plane_declared_absent
```

- #44 `git grep -n 'skip\|xfail' -- MitateDB-api/tests/test_ops_startup_checks.py`: 出力なし (終了コード 1)。
- #45 `pt: 216 passed in 33.89s` (`test_ops_startup_checks.py` 76 + `TINV` 140。`TINV` は `git diff --stat ab20f4e` で不変)。
- #46 `git diff --stat ab20f4e -- MitateDB-api/src/mitatedb_api/platform_declarations.py MitateDB-api/src/mitatedb_api/config.py MitateDB-api/src/mitatedb_api/main.py MitateDB-api/src/mitatedb_api/control_composition.py MitateDB-api/src/mitatedb_api/http.py MitateDB-api/tests/test_ops_inventory.py MitateDB-api/tests/test_audit_query.py r2db-api spec conformance-tests MitateDB-api/migrations`: 出力なし (不変)。変更セットの `git diff --stat -- . ':!docs'`: `MitateDB-api/docs/cloud-run-cloud-sql.md` 671、`MitateDB-api/src/mitatedb_api/ops.py` 104、`MitateDB-api/src/mitatedb_api/startup_checks.py` 1175、`MitateDB-api/tests/test_ops_startup_checks.py` 1382、`security/CONTROL_MAPPING.md` 204、`tools/tests` の 4 file 各 1 (9 files changed, 3266 insertions(+), 274 deletions(-))。
- #46b `pt: 12 passed in 2.18s` (`tools/tests/test_sql_statement_safety_scan.py tools/tests/test_leaf_import_direction.py tools/tests/test_src_import_readers.py tools/tests/test_src_import_cycles.py`、新規 file を `git add -N` した後)。
- 変異: `mutate: 48 mutations, 48 as expected, restores verified 6/6 files (sha256 x2)` (M1〜M41、M6b、M46a、M46c〜M46g)。
- #43 (CI 3.12 の leg): push 再開後に main の run で照合 (§12.3 の 3)。手元は 3.11.15 だけ。

