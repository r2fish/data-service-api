# `apply-platform-migration` に再適用の「列」を受け付けさせる 設計メモ (v0.2)

- 状態: **監督確定 (2026-09-20)**。設計レビュー 1 回と監督裁定 (§8.2・§8.3) を反映した v0.2 を確定版として扱う。WP の割り付けの訂正は作業指示書 `docs/work-orders/WORK_ORDER_R57_PLATFORM_MIGRATION_RUN_V1.md` §5.1 の K-1。~~起草 (2026-09-20)。~~§1〜§8 の枠は監督が確定済み。作業指示書は未着手。依頼者判断待ちの項目は無い (§9)。
- 改版: v0.1 (2026-09-20) 起草。**v0.2 (2026-09-20) 設計レビュー 1 回目 (高 3・中 5・低 4。クラス引き上げ無し) と監督裁定 R-1〜R-12 を反映**: G-1 の凍結範囲を実測記録そのもの (:2786-2839) に狭め復旧手順を追随先へ移し (R-1)、D-3 の照合を対象水準の写像の pin にし (R-2)、`docs/code-history/` と `tools/check_comment_provenance.py` を範囲に足し R-63 との順序を定め (R-3)、条件 (i) を「道具が 0 で終わったとき」に限定して失敗窓を D-4 に明記し (R-4)、`--lock-timeout` の値を道具に持たせない裁定を D-4 に書き (R-5)、条件 (iii) の完了条件と変異を足し (R-6)、D-7 の #3 を 3 つに割り (R-7)、WP-3 にテスト名の実在確認を足し (R-8)、§10.6 の 3 行を追随先に足し (R-9)、対象の同一性を定義し (R-10)、#5 の変異を現物の分岐に対応させ (R-11)、`0012`・`0013` の単体 drift-then-restore を psql 直打ちに残した (R-12)。**v0.1 の行は消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。
- 台帳: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-57** (`RM`:455)。起票 2026-09-18 (R-52 WP-1 第 1 段の監督裁定 S-1、`docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md`:205)。
- 公開規律: `docs/work-orders/OPERATING_CONDITIONS.md` §2 の 13、§1.9。本メモは実 DSN・実ホスト名・実ドメイン・作業機のパス・traceback を 1 つも含まない。
- 実測の出所: すべて本リポジトリの現物 (`main` `2172fb0` 時点)。相対パス + `:行番号` で引く。

---

## 1. 問題

`ops apply-platform-migration` は 1 回の呼び出しで 1 ファイルしか流さず (`MitateDB-api/src/mitatedb_api/ops.py`:2743 の `args.file`、:2752 の `-f` は 1 本)、受け付けるファイル名の列挙 (`_PLATFORM_MIGRATION_FILENAMES`、同 :2635-2642) はただの許可リストで順序の制約を持たない。

`0012` と `0013` は、後続のファイルが上書きする対象を持つ。

- `begin_provision_application` を `CREATE OR REPLACE` するのは 3 ファイルである: `MitateDB-api/migrations/0012_role_connection_limits.sql`:154、`0013_role_statement_timeouts.sql`:111、`0014_role_connection_limits_rollout.sql`:132。したがって `0012` 単独再適用は `0013` が足した `statement_timeout` を落とし、`0012`・`0013` 単独再適用は `0014` の `CONNECTION LIMIT` 68 を 36 へ戻す。
- role の `CONNECTION LIMIT` も同じ形である: `0012`:114-115 と `0014`:89-90 が同じ 2 役を、`0012`:135-136 と `0014`:113、:116 が既存 application の役を、それぞれ無条件に自分の値へ設定する。

`ops inventory` の (6) は `CONNECTION LIMIT` が `None`/`-1` でなければ確認とし (`ops.py`:2418-2419)、`statement_timeout` も正の値なら確認とする (同 :2429-2442)。いずれも期待値そのものとは比べない。(8) は operator が渡す process 数から需要を出して比べる (同 :2551-2565)。**`0013` 単独再適用の後に application を 1 件も provision していない間は、どの既存の検査も捕らえない** (監督裁定 S-1、`docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md`:205)。

現状の受けは runbook の手順だけである (`MitateDB-api/docs/cloud-run-cloud-sql.md`:3067-3068「never `0012` or `0013` on its own」)。クラスタ側に platform migration の適用記録は無い — 台帳 `_mdb_platform_upgrades` は `_upgrade.sql` で終わるファイルだけを記録し、`0007`/`0011`/`0012`/`0013`/`0014` は意図的にその名で終わらない (`MitateDB-api/migrations/0011_process_ceilings.sql`:43-47)。

## 2. 守るべき条件

- (i) ~~道具を通る限り、適用の終わりに「複数ファイルが定める対象」は必ず**最も新しいファイルの値**になっている。~~ — **v0.1 のこの書き方を R-4 (2026-09-20) が限定した。行は消さない。** → **道具が 0 で終わったとき、「複数ファイルが定める対象」は必ず最も新しいファイルの値になっている。** 途中で失敗した実行 (非 0 終了) は古い値を残しうる。残りうる状態と受けは D-4 に書く。
- (ii) 新しい migration が既存の対象を上書きしたのに表が追随しない状態を、テストが赤にする。
- (iii) 道具は operator が明示していないファイルを流さない。runbook §10 の gate は手順の実行ごとに掛かるので、黙って後続を足さない。
- (iv) 公開契約 `spec/`・Security Invariants・migration ファイルの中身を変えない。

## 3. 現物の事実

### 3.1 上書き関係 (実測)

| 対象 | 定めるファイル (順) | 再適用で古い値へ戻るか |
|---|---|---|
| `begin_provision_application` の本体 | `0012`:154 → `0013`:111 → `0014`:132 | 戻る |
| `mitatedbsvc_api` / `mitatedbsvc_controlplane` の `CONNECTION LIMIT` | `0012`:114-115 → `0014`:89-90 | 戻る |
| 既存 application の runtime / developer role の `CONNECTION LIMIT` | `0012`:135-136 → `0014`:113、:116 | 戻る |
| `mitatedbsvc_auditreader` の `CONNECTION LIMIT` | `0005`:246-247 (条件付き `CREATE ROLE`) / `0014`:91 | **戻らない** (`0005` は `IF NOT EXISTS` で守られた `CREATE ROLE` の中にしか値を持たない) |
| `platform_declarations` の CHECK 制約 | `0007`:103 (`CREATE TABLE IF NOT EXISTS`) / `0011`:59-63 (`DROP`/`ADD CONSTRAINT`) | **戻らない** (`0007` は表が在れば no-op) |
| `audit_writer_roles` 行・writer 2 役の `ALTER ROLE … SET` ×4 | `0007`:98-101、:124 (`ON CONFLICT … DO UPDATE`) | 後続ファイルによる上書きではない (下の註) |

- 註: `0007` の 4 本の `ALTER ROLE … SET` と `audit_writer_roles` の `DO UPDATE` は、**同じファイルの再適用が値を書き換える**という別の性質であって、後続ファイルによる上書きではない。runbook が「先に記録して直後に戻す」手順 (§10.10 の手順 2・4) で既に受けている (`MitateDB-api/docs/cloud-run-cloud-sql.md`:2455 付近の §10.7 の `0007` 行)。本件はこの性質に触れない。
- `0011` は全文 1 トランザクション (`0011`:56、:65)、`0013` も `0014` も同じ (`0013`:62、:192 / `0014`:82、:213)。`0012` はセクション 1-2 だけが 1 トランザクションで (`0012`:108、:141)、**セクション 3 はその外にある 2 文 (`CREATE OR REPLACE FUNCTION` と `REVOKE … ON FUNCTION`) で、それぞれが自動コミットする** (`0012`:143-151、runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`:2446 の「outside the transaction (two statements, each auto-committing)」)。
- 既存 application の役を回すループは、`0013`:91-96 と `0014`:112-117 が `IF EXISTS (SELECT 1 FROM pg_roles …)` の skip guard を持ち、`0012`:135-136 は持たない。**skip guard は「その役が在れば必ず自分の値に上書きする」ので、再適用で値を戻す側である** (`IF NOT EXISTS` の防御とは向きが逆である。D-3)。

### 3.2 道具と受けの現状

- 受理・解決・変数照合は `ops.py`:2687-2709 (`_resolve_platform_migration_file`)、:2712-2730 (`_platform_migration_variables`)、本体は :2733-2757。psql は 1 回、`PGOPTIONS` に `lock_timeout` を載せ (:2748)、成功時に `applied <file>` を 1 行出す (:2756)。
- `apply-platform-migration` を呼ぶ現物は runbook (`MitateDB-api/docs/cloud-run-cloud-sql.md` の 16 箇所) とテストだけである (grep 実測)。配備 script・bootstrap の経路には無い。
- §10.7 の `--lock-timeout` の表の値は `0005` `3s` / `0007` `3s` / `0011` `2s` / `0012` `3s` / `0013` `3s` / `0014` `3s` である (同 :2411 以下の表)。

## 4. 決定

### D-1 位置引数を 1 個以上の列にする

`apply-platform-migration FILE [FILE ...] --lock-timeout V [--api-role ROLE --controlplane-role ROLE]`。1 ファイルの呼び出しは今の形のまま通る — そのファイルに後続の上書きが無い場合である。

### D-2 上書き関係の表と受け付け条件

`ops.py` に `_PLATFORM_MIGRATION_SUPERSEDED_BY` を置く。現状の値は `0012_role_connection_limits.sql` → (`0013_role_statement_timeouts.sql`, `0014_role_connection_limits_rollout.sql`)、`0013_role_statement_timeouts.sql` → (`0014_role_connection_limits_rollout.sql`,) である。

受け付け条件は 2 つ。

1. 列は `_PLATFORM_MIGRATION_FILENAMES` の順で**昇順・重複なし**である。
2. 列の各ファイルについて、表が挙げる後続が**全部、列のそれより後ろに在る**。

満たさなければ **psql を 1 つも起動せず**、固定文言で拒否する。文言は要る列を示す (例: `0012… 0013… 0014…`)。示すのは表と `_PLATFORM_MIGRATION_FILENAMES` が持つ定数の名であり、**拒否された値そのものは echo しない** (`ops.py`:2696 の既存の規律)。

- この判定は「既に適用済みか」を見ない (適用記録が無いため、§1)。したがって `0013`/`0014` を一度も適用していないクラスタでも `0012` 単独は拒否される。
- ~~runbook の手順 7 は元から 3 本を並べるので、これで塞がれる経路は無い (§3.2)。~~ — **v0.1 のこの判断を R-1 (2026-09-20) が覆した。行は消さない。** 塞がれる経路が 1 つある: runbook の ADMIN OPTION の復旧手順は「apply the numbered set again **from the file that failed**」と書いており (`MitateDB-api/docs/cloud-run-cloud-sql.md`:2772-2775、:2831-2833)、これは「失敗した 1 本だけを流す」とも読める。**D-5 でこの 2 箇所を「そのファイル以降を 1 回の実行の列として流す」に書き換える。** 書き換え後は、`0013` で失敗した復旧が `0013 0014` の列になり、D-2 の受け付け条件を満たす。

### D-3 対象水準の写像を静的テストで固定し、file 水準の表はそこから導く

**固定するのは「対象 → それを定めるファイルの列」の写像である** (R-2)。`_PLATFORM_MIGRATION_SUPERSEDED_BY` (D-2) は、この写像から機械的に導いた結果と等しいことを比べられる側であって、照合の起点ではない。file 水準だけを比べると、抽出規則の取り違え (例: `IF EXISTS` の skip guard を `IF NOT EXISTS` と同じに扱う) が file 水準では同じ表を生むために赤にならない。

**対象の同一性** (R-10): **(役または関数の識別子, 設定の種別またはパラメタ名)** の組とする。

- 役の識別子は、リテラルならその名、psql 変数なら**変数名** (`:"api_role"` → `api_role`)、plpgsql の式なら**式の文字列** (`app.runtime_role`)。
- 設定の種別は `CONNECTION LIMIT` / `SET <パラメタ名>` / 関数本体のいずれか。

**抽出する種別** (対象 → 定めるファイル、という形で集める):

- `CREATE OR REPLACE FUNCTION` の関数名 = (関数の識別子, 関数本体)。`0012`:154 / `0013`:111 / `0014`:132。
- `ALTER ROLE <役> CONNECTION LIMIT` (`0012`:114-115 / `0014`:89-91)。
- `ALTER ROLE <役> SET <パラメタ>` (`0007`:98-101 / `0013`:71)。
- DO ブロック内の `format('ALTER ROLE %I …')` (`0012`:135-136 / `0013`:92、:95 / `0014`:113、:116)。

**走査の規則**:

- `--` 行コメントは先に落とす。既存の `_strip_sql_line_comments` (`ops.py`:2668-2672) を再利用する — 同じ規則が 2 つ在る状態を作らない。
- **`CREATE [OR REPLACE] FUNCTION … AS <dollar quote> … <dollar quote>` の本体は走査しない。** 本体の中の `ALTER ROLE` (`0013`:157、:163 ほか / `0014`:178、:184 ほか) は独立した対象ではなく、**関数本体という 1 つの対象の中身**である。現物では関数本体のタグは `$fn$`、DO ブロックは `$$` だが、規則はタグのリテラルではなく構文 (`CREATE … FUNCTION` の本体か否か) で書く。DO ブロックは走査する。
- **除外は再適用で値を戻さないものに限る** (R-10 により名指しの除外はやめる): `IF NOT EXISTS` で守られた `CREATE ROLE`/`CREATE TABLE` (`0005`:245-247、`0007`:103)、存在しない時だけ行う DO ブロック、`ON CONFLICT DO NOTHING` (`0007`:118)。これにより `0005` の auditreader と `0007`→`0011` の CHECK 制約は写像に入らない (§3.1)。
- **`IF EXISTS` の skip guard の中の `ALTER` は含める** (`0013`:91-96、`0014`:112-117)。在る役には必ず自分の値を書くので、戻す側である (§3.2)。
- ~~`0007` の `ALTER ROLE … SET` ×4 と `audit_writer_roles` の `DO UPDATE` (`0007`:124) は…抽出の規則にこの 2 件を名指しで書き~~ — **v0.1 のこの扱いを R-10 (2026-09-20) が覆した。行は消さない。** 名指しの除外は要らない。`0007` の 4 本は対象として抽出されるが、**定めるファイルが `0007` の 1 本だけ**なので後続関係を生まない。`audit_writer_roles` の `DO UPDATE` は `INSERT` であって上の 4 種別のどれでもないので、そもそも抽出されない。§3.1 の註 (同じファイルの再適用が値を書き換える別の性質であり、runbook の「記録して戻す」手順が受けている) は事実として残す。

導出の結果は §3.1 の実測と一致する: 関数本体の対象が `[0012, 0013, 0014]`、`CONNECTION LIMIT` の 3 対象が `[0012, 0014]` を持ち、file 水準に畳むと `0012` → (`0013`, `0014`) と `0013` → (`0014`,) になる。

### D-4 適用は列の順に 1 ファイル 1 psql

起動形・`PGOPTIONS` の lock_timeout・変数表の照合は今のままである (`ops.py`:2747-2753)。

- `--lock-timeout` は**列全体に 1 つ**である。§10.7 の表で `0012`・`0013`・`0014` は同じ `3s` である (§3.2)。
- **道具は §10.7 の値を持たない** (R-5、裁定 = 案 B)。`lock_timeout` は「安全な値」ではなく**待ちの上限**であり、正本は §10.7 の表である。道具に既定値や file ごとの表を持たせると値の正本が二重化する (X-c と同じ理由)。したがって **§10.7 の値が異なるファイルを 1 つの列に混ぜない責任は operator にある**。D-5 で runbook の §10.7「How the table's values are passed」(:2455) に「列は §10.7 の値が同じファイルで組む」を明記する。現物では `0011` だけが `2s` で、後続を持たないので単独で流せる (§3.2)。
- psql 変数は列の各ファイルの要求の**和集合**と照合し、**要るファイルにだけ**渡す (現状の `_platform_migration_variables` は 1 ファイル分の過不足を見る。同じ判定を列に広げる)。
- 途中で失敗したら**以後を流さず**、適用済み・失敗・未実行のファイル名を出して非 0 で終わる。途中の状態は古い値を持ちうるので、**列全体をやり直す**よう文言で言う (各ファイルは冪等である)。
- 成功時は `applied <file>` を**ファイルごとに**出す (既存の出力形を保つ、`ops.py`:2756)。

**失敗窓に残りうる状態** (R-4、条件 (i) の限定):

- 列 `0012 0013 0014` が `0013` で失敗すると、`0012` は既に成功している。`0012` のセクション 3 は transaction 外の 2 文でそれぞれ自動コミットするので (§3.2)、**`begin_provision_application` は `0012` の値 (`CONNECTION LIMIT` 36、`statement_timeout` 無し) のまま残る**。これは S-1 が「どの検査も捕らえない」と裁定した状態そのものである (§1)。
- `0013` で失敗した場合、`0013` 自身は全文 1 トランザクションなので何も残さない (§3.2)。残るのは `0012` の分だけである。
- したがって **道具は非 0 で終わるときに、この状態が残りうることと「列全体をやり直す」ことを文言で言う**。runbook の手順 7 にも同じ段を置く (D-5)。道具は残った状態を自分で直さない — 直すなら X-c (適用後の検算) と同じ二重化になる。

### D-5 runbook の追随

- §10.10.1 の手順 7 (`MitateDB-api/docs/cloud-run-cloud-sql.md`:3054-3058) を **1 コマンドの列**に書き換える。**失敗窓の段を足す** (D-4。`0013` で失敗すると `0012` のセクション 3 が残る、直しは列全体のやり直し)。
- 「単独では流さない」の段落 (:3067-3068) を「**道具が拒否する**」に合わせて直す。
- **ADMIN OPTION の復旧手順 :2772-2775 と :2831-2833 の「apply the numbered set again from the file that failed」を「そのファイル以降を 1 回の実行の列として流す」に書き換える** (R-1。D-2 の末尾)。
- **S-1 の「捕らえない」限界 (inventory 側) の記述は残す。** 道具の外 (psql 直打ち) には同じ状態を作る経路が残るためである。
- §10.7 の「How the table's values are passed」(:2455) に、値の渡し方に加えて **「列は §10.7 の値が同じファイルで組む」**を明記する (R-5)。
- §10.6 の `0012`・`0013`・`0014` の 3 行 (:2398・:2399・:2400) も追随先に入れる (R-9)。3 行とも単独再適用の帰結を現在形で述べており、**:2400 の文は「道具が列を強制する」に合わせる**。
- 使い方の行 (:1567)、`Applying a platform migration` と numbered set の段落 (:2702-2726。G-2)、help 文言 (`ops.py`:3078-3097) も追随する。

### D-6 既存テストの追随

- 単独で `0012`/`0013` を ops 経由で流しているテストは、**(a)** 拒否を固定するテストに変えるか、**(b)** 状態を作る目的なら psql 直打ちの helper へ移す。対象は §5 の **16 箇所全部**である (G-3)。
- **`0012` と `0013` の単体の drift-then-restore は (b) で残す** (R-12)。`test_apply_platform_migration_0012_restores_a_manually_drifted_function_body` (`MitateDB-api/tests/test_ops_apply_platform_migration.py`:671) と `0013` の同種のテストは、**そのファイル 1 本が自分の対象を復元する**という粒度の性質を持つ。列に畳むと最後のファイルの復元しか見えなくなり、`security/CONTROL_MAPPING.md`:751 の「drift-then-restore for 5 of the 6 accepted files」の主張が弱くなる。粒度を保つために psql 直打ちの helper へ移し、**ops 経由の経路は拒否のテストが持つ**。
- `MitateDB-api/tests/test_platform_migration_reapply.py`:843-849 の再適用のループは、`_REAPPLY_PLATFORM_MIGRATION_FILENAMES` を 1 本ずつ `apply-platform-migration` に渡す (同 :294-298)。**列での再適用 (`0012 0013 0014`) の後に最新値が残ることを固定する**形にする。`0005`/`0007`/`0011` は後続を持たないので単独のままでよく、`0011` の `--lock-timeout` が他と違う `2s` である点とも矛盾しない (D-4 の R-5)。

### D-7 テストと変異 (完了条件 1 つに変異 1 つ)

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | D-3 の**対象水準の写像**が現物からの導出と等しい (静的テスト。空振り防止として、既知の 4 対象 — 関数本体 1 と `CONNECTION LIMIT` 3 — が導出結果に現れることを確かめる) | 写像から `0013` の関数本体の行を外す → 赤 |
| 1b | `_PLATFORM_MIGRATION_SUPERSEDED_BY` が写像から導いた file 水準の表と等しい | 定数から `0013` → (`0014`,) を外す → 赤 |
| 2 | 抽出の除外規則が効く (`0005` の auditreader・`0007`→`0011` の CHECK 制約が写像に**入らない**) | `IF NOT EXISTS` の除外を無効にする → 余分な対象が出て赤 |
| 2b | `IF EXISTS` の skip guard の中の `ALTER` は**含まれる** (`0013`:91-96、`0014`:112-117 が写像に在る) | skip guard の中を `IF NOT EXISTS` と同じに扱って除外する → 赤 (R-2 が狙う取り違え) |
| 2c | `CREATE … FUNCTION` の本体は走査されない (本体の中の `ALTER ROLE` が独立した対象として現れない)、`--` コメントの中の文も拾わない | 関数本体の走査除外を外す → 余分な対象が出て赤 |
| 3a | 後続を欠く列を **psql を 1 つも起動せず**に拒否する | 閉包検査を無効化する → 赤 |
| 3b | 拒否の文言が**要る列**を示す (例: `0012… 0013… 0014…`) | 文言から要る列の列挙を落とす → 赤 |
| 3c | 拒否は入力の値そのものを echo しない | 文言に入力の値を混ぜる → 赤 |
| 4 | 昇順・重複なしの検査 | 昇順検査を無効化する → 赤 |
| 5 | 1 ファイルの呼び出しが今の形のまま通る (`0011` 単独・`0014` 単独) | 閉包検査の「表に後続を持たないファイル」の分岐を外し、一律に 2 本以上を要求する → 赤 (R-11。変異は 1 つの分岐の除去として現物の行に対応する) |
| 6 | 列の各ファイルが順に 1 psql で流れ、`applied <file>` がファイルごとに出る。psql 変数は要るファイルにだけ渡る | 変数の絞り込みを外して全ファイルに渡す → 赤 |
| 6b | **道具は operator が明示していないファイルを流さない** (条件 (iii))。psql に渡る `-f` の集合が、operator が並べた列と**完全に一致**する | 拒否の代わりに、表の後続を自動で足して流す (X-a の形) → 赤 (R-6) |
| 7 | 途中で失敗したら以後を流さず、適用済み・失敗・未実行を出して非 0 で終わり、文言が「列全体をやり直す」と言う | 失敗後に続行する → 赤 |
| 8 | 列での再適用 (`0012 0013 0014`) の後に最新値 (132/36/12/68 と `statement_timeout`) が残る (実 PostgreSQL) | 列の順序の保持を外して逆順に流す → 赤 |
| 9 | 単独で `0012`/`0013` を ops 経由で流していた **16 箇所**が、拒否の固定か psql 直打ちの helper のどちらかに移っている。`0012`・`0013` の単体 drift-then-restore は psql 直打ちで粒度を保つ (D-6) | 移した先の 1 件から拒否の assert を落とす → 赤 |
| 10 | help と runbook の該当箇所が列の形になっている (help は定数由来、`MitateDB-api/tests/test_ops_help_text.py`:52-57 の形を保つ) | help の生成を定数から切り離す → 赤 |
| 10b | `tools/check_comment_provenance.py --base <基点>` が、コード変更に伴う §4.1 (1) 以外を何も出さない。**新設 helper には docstring を書く** (R-3。R-63 の統合後の main を基点にするので書ける) | **監査照合** + 道具の実行。出力の逐語を実施記録に残す |
| 11 | 上の対応表に対応の無い完了条件が無い | **監査照合** (本表)。照合対象の逐語記録を本メモの実施記録の節に残す |

### D-8 r2db-api は対象外

r2db-api の `ops.py` に `apply-platform-migration` に相当する subcommand は無い (grep 0 件)。`begin_provision_application` を `CREATE OR REPLACE` するのは `r2db-api/migrations/0013_role_connection_limits.sql` の 1 ファイルだけで、同じ形の連鎖が現に無い。したがって本件は MitateDB-api だけを変える。

## 5. 追随する現物

| 現物 | 追随の中身 |
|---|---|
| `MitateDB-api/src/mitatedb_api/ops.py`:2623-2757、:3078-3097 | 節見出しのコメント・定数・受理・本体・parser・help |
| `MitateDB-api/tests/test_ops_apply_platform_migration.py` | 単独の `0012` (:689) と `0013` (:729、:754、:854、:882、:897、:930、:938、:950-954、:999、:1022、:1081、:1130) の ops 経由の呼び出し 15 箇所 (D-6)、列の受け付け・拒否の新規テスト |
| `MitateDB-api/tests/test_ops_inventory.py`:1383 | 単独の `0013` の ops 経由の呼び出し 1 箇所 (D-6) |
| `MitateDB-api/tests/test_platform_migration_reapply.py`:294-298、:843-849 | 再適用のループを列に直す (D-6) |
| `MitateDB-api/tests/test_ops_help_text.py`:52-57、:121、:143-158 | help が定数由来であることの pin と、節見出しコメントの逐語 (`applies one platform migration file`) |
| `MitateDB-api/docs/cloud-run-cloud-sql.md`:1567、:2455、:3054-3058、:3067-3068 | D-5 が名指しする 4 箇所 |
| 同 :2702-2726 (`Applying a platform migration` と numbered set の段落) | 現行の使い方の説明。列の形に直す (G-2) |
| 同 :2398・:2399・:2400 (§10.6 の `0012`/`0013`/`0014` の 3 行) | 単独再適用の帰結の記述。:2400 は「道具が列を強制する」に合わせる (R-9) |
| 同 :2772-2775、:2831-2833 (ADMIN OPTION の復旧手順「from the file that failed」) | 「そのファイル以降を 1 回の実行の列として流す」に書き換える (R-1) |
| ~~同 :2767-2830 (ADMIN OPTION の実測記録)~~ → **同 :2786-2839** | **凍結範囲。実測記録そのものであり書き換えない** (G-1 を R-1 が狭めた。v0.1 の範囲 :2767-2830 は両端がずれており、前端が復旧手順を、後端が `0014` の実測の末尾を取りこぼしていた — レビュー実測、現物で確認した)。訂正註を 1 つ添える (G-1) |
| `docs/code-history/MitateDB-api/ops.md` | `ops.py` のコメント・docstring を変えた分の記録 (R-3。`tools/check_comment_provenance.py` の §4.1 の (2)〜(5) が求める) |
| `security/CONTROL_MAPPING.md`:736、:751 | §7 |

**触らない現物 (測った上で)**:

- `spec/`・`conformance-tests/`・`security/SECURITY_INVARIANTS_V1.md` (条件 (iv))。`apply-platform-migration` は `conformance-tests/` に 1 件も現れない。
- migration ファイル `0005`/`0007`/`0011`/`0012`/`0013`/`0014` の中身 (条件 (iv))。
- `_ISOMORPHIC_TARGETS` (`MitateDB-api/tests/test_audit_query.py`:2179-2470)。本件が本体を変える関数・定数はこの登録に **0 件**である (`_PLATFORM_MIGRATION_*`・`_resolve_platform_migration_file`・`_platform_migration_variables`・`cmd_apply_platform_migration`・`_extract_psql_variables` のいずれも現れない。grep 実測)。r2db-api に対応物が無い (D-8) ことと整合する。

## 6. 却下した代替案

- **X-a 後続を道具が自動で足して流す** — operator が明示していないファイルを gate の外で**初回適用**しうる。適用記録が無いので「適用済みの後続」を判別できず (§1)、区別のしようがない。条件 (iii) に反する。
- **X-b 適用記録の ledger を新設する** — 既存クラスタへの遡及、bootstrap 経路 (psql 直) との二重化、適用済み migration の改変が要る。得られる不変量は D-2 と同じである。
- **X-c 適用後に最新値を検算する** — 値の正本が migration と道具に二重化する。
- **X-d runbook だけで受ける現状維持** — S-1 の限界 (§1) が残る。

## 7. 証拠の状態と `security/CONTROL_MAPPING.md`

本変更で不正確になる行を現物で確かめた。**2 行が不正確になる。**

- **:736** — 「applies **one** platform migration file … **FILENAME** is a bare name」。D-1 で 1 個以上の列になり、引数の形も変わる。
- **:751** — `MitateDB-api/tests/test_ops_apply_platform_migration.py` の件数 (`51 tests`) と内訳 (`drift-then-restore for 5 of the 6 accepted files`)。D-6 で件数と内訳が変わる。

他の 6 行 (:612、:654、:739、:742、:744、:747) は本変更では不正確にならない (:739 の「migration を psql に流す subcommand の集合 = `--lock-timeout` 必須の集合」は不変、:742・:747 は migration 自身の性質と numbered set の手順の記述である)。

- **この「不正確にならない」は :744 と :751 が引く計 5 件のテスト名が実在し続けることに依る。** それを見る機械検査は無い — Evidence のテスト名を実在しない名前に書き換えても `conformance-tests/test_control_mapping_register.py` は緑のままである (`RM`:462 の **R-64**、R-56 WP-3 の変異による実測)。したがって **WP-3 の完了条件に「:744・:751 が引くテスト名が現物に在ることの照合」を置く** (R-8、監査照合)。D-6 でテストを移す本件では、この照合が空振りしない。

したがって **`security/CONTROL_MAPPING.md` を触る WP が要り、本件の変更クラスは D になる** (§8)。版数の更新 (2.12 → 2.13) と足す主張・証拠の中身は作業指示書で定める。

## 8. 変更クラスと WP

- **パスの下限は B** (`tools/change_class.py` 実測: `MitateDB-api/src/mitatedb_api/ops.py`・`MitateDB-api/tests/*.py` が `B`、`MitateDB-api/docs/cloud-run-cloud-sql.md` と本メモが `A` で `class=B`)。
- **`security/CONTROL_MAPPING.md` を触るので全体は D** (同ツール実測: `class=D`)。根拠は §7 の 2 行である。`RM` §9 の 8 の表の D 行「`security/` 配下」に当たる。
- `_ISOMORPHIC_TARGETS` の集合にも本体にも触らない (§5)。この経路からの C/D の契機は無い。
- WP の切り方 (§8.2 の G-4 で確定):

| WP | 中身 | 触るパス |
|---|---|---|
| WP-1 | D-2・D-3 の写像と受け付け条件、D-1・D-4 の列の適用、D-7 の完了条件 1〜8 と 10b、D-6 の既存テストの追随 | `MitateDB-api/src/mitatedb_api/ops.py`、`MitateDB-api/tests/test_ops_apply_platform_migration.py`、`MitateDB-api/tests/test_ops_inventory.py`、`MitateDB-api/tests/test_platform_migration_reapply.py`、`MitateDB-api/tests/test_ops_help_text.py`、**`docs/code-history/MitateDB-api/ops.md`** (R-3) |
| WP-2 | D-5 の runbook、D-7 の完了条件 9・10 | `MitateDB-api/docs/cloud-run-cloud-sql.md` |
| WP-3 | §7 の 2 行の更新と :744・:751 のテスト名の実在確認 (R-8)、D-7 の完了条件 11 の監査照合、本メモの実施記録 | `security/CONTROL_MAPPING.md`、`docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md`、`docs/design/ROADMAP_POST_PHASE7_V1.md` |

- 並行させない (WP-1 → WP-2 → WP-3)。WP-1 と WP-2 は触るファイルが重ならないが、runbook の文言は WP-1 が確定させる拒否の形に依るためである (`docs/work-orders/OPERATING_CONDITIONS.md` §1.2 の 16、17)。
- **着手の前提 (R-3)**: 監督は台帳 **R-63** (`RM`:461。`tools/check_comment_provenance.py` の §4.1 の判定が新設関数の docstring を書けなくしている) の直しを **R-57 WP-1 より先に**行う。**WP-1 は R-63 の統合後の main を基点にし、新設する helper には docstring を書く。**

### 8.1 変更クラス D が求める追加証拠

- **依頼者裁定の逐語記録** (2026-09-19): 「その方針で進めてください、完了まで行ってください、判断は推奨で進め後から報告してください。推奨は長期的な視点で製品価値のある判断にしてください。」 本メモの D-1〜D-8 は、この委任の下で監督が推奨として下したものである。**完了後に依頼者へ報告する。**
- **版付きの security-contract 決定**: `security/CONTROL_MAPPING.md` の版を上げる (§7)。`security/SECURITY_INVARIANTS_V1.md` の本文は変えない — 本件は既存の SI の下の統制の記述を現物に合わせるだけで、新しい invariant を作らない (`CLAUDE.md`「Security Invariants are not a feature gate」の節)。契約版数は据え置く (`spec/` を触らない、条件 (iv))。

## 8.2 起草時の監督裁定 (2026-09-20)

- **G-1 runbook の ADMIN OPTION の実測記録 (:2767-2830) は書き換えない。** 過去の実測の逐語である。記録の直後に「R-57 以後、道具は単独の `0013` を拒否する。上の呼び出しは当時の形の記録である」の訂正註を 1 つ添える (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 57 と同じ扱い)。 — **範囲を R-1 (2026-09-20) が `:2786-2839` に改めた。行は消さない。** 凍結するのは実測記録そのものだけで、:2772-2775 と :2831-2833 の復旧手順は生きた手順なので D-5 の追随先に入る。
- **G-2 同 :2702-2726 (`Applying a platform migration` と numbered set の段落) は D-5 の追随先に含める。** 現行の使い方の説明であって記録ではない。
- **G-3 D-6 の対象は §5 の 16 箇所全部** (`MitateDB-api/tests/test_ops_inventory.py`:1383 を含む)。
- **G-4 WP の切り方は §8 の提案のとおり確定する。**

## 8.3 設計レビュー 1 回目への監督裁定 (2026-09-20)

設計レビュー 1 回 (高 3・中 5・低 4、クラス引き上げ無し)。レビューの実測はすべて現物で確かめた。

- **R-1 (高 1 採用)**: G-1 の凍結は **runbook の ADMIN OPTION の実測記録そのもの (:2786-2839) だけ**に改める。:2772-2775 と :2831-2833 の「from the file that failed」の復旧手順は D-5 の追随先に入れ、**「そのファイル以降を 1 回の実行の列として流す」**に書き換える。D-2 の「塞がれる経路は無い」を直す。→ §4 D-2 末尾、D-5、§5、§8.2 の G-1 行。
- **R-2 (高 2 採用)**: D-3 の照合を**対象水準の写像** (対象 → それを定めるファイルの列) の pin にし、file 水準の表はそこから導く。除外は `IF NOT EXISTS` / 存在しない時だけの DO / `ON CONFLICT DO NOTHING` に限り、**`IF EXISTS` の skip guard の中の `ALTER` は含める**。`--` コメントの除去 (`_strip_sql_line_comments` の再利用) と dollar-quote の関数本体の走査除外を規則に書く。→ §4 D-3、D-7 の完了条件 1・1b・2・2b・2c。
- **R-3 (高 3 採用)**: §5 と WP-1 の触るパスに `docs/code-history/MitateDB-api/ops.md` を足し、完了条件に `tools/check_comment_provenance.py --base <基点>` を通すことを入れる。**監督は R-63 (道具の直し) を R-57 WP-1 より先に行う。WP-1 は R-63 の統合後の main を基点にし、新設 helper に docstring を書く。** → §5、D-7 の 10b、§8。
- **R-4 (中 4 採用)**: §2 の (i) を「道具が 0 で終わったとき」に限定し、失敗窓に残りうる状態を D-4 に明記する。runbook の手順 7 に失敗窓の段を足す。`0012` のセクション 3 が transaction 外の 2 文である点も書く。→ §2 (i)、§3.2、§4 D-4・D-5。
- **R-5 (中 5 裁定 = 案 B)**: `--lock-timeout` は安全値ではなく**待ちの上限**なので、**道具は §10.7 の値を持たない** (値の正本を二重化しない)。混在列は operator の責任とし、runbook §10.7「How the table's values are passed」に「列は §10.7 の値が同じファイルで組む」を明記する。→ §4 D-4・D-5・D-6。
- **R-6 (中 6 採用)**: 条件 (iii) の完了条件と変異を D-7 に足す。→ D-7 の 6b。
- **R-7 (中 7 採用)**: D-7 の #3 を 3a / 3b / 3c に割る。→ §4 D-7。
- **R-8 (中 8 採用)**: WP-3 の完了条件に、`security/CONTROL_MAPPING.md`:744・:751 が引くテスト名の実在確認を足す (R-64 が機械検査を持たないため)。→ §7、§8。
- **R-9 (低 9 裁定)**: §10.6 の該当 3 行 (:2398・:2399・:2400) も D-5 の追随先に入れ、**:2400 の文は「道具が列を強制する」に合わせる**。→ §4 D-5、§5。
- **R-10 (低 10 採用)**: **対象の同一性 = (役または関数の識別子, 設定の種別/パラメタ名)** と定義する。`0007` の名指し除外はやめる。psql 変数の役名は**変数名**を識別子として扱う。→ §4 D-3。
- **R-11 (低 11 採用)**: D-7 の #5 の変異を現物の分岐 (閉包検査の「表に後続を持たないファイル」の枝) に対応させる。→ D-7 の 5。
- **R-12 (低 12 採用)**: `0012`・`0013` の単体 drift-then-restore は psql 直打ちの helper に残し、粒度を落とさない。→ §4 D-6、D-7 の 9。

## 9. 依頼者判断待ち

無し。依頼者指示 2026-09-19 (逐語は §8.1): 「判断は推奨で進め後から報告」。
