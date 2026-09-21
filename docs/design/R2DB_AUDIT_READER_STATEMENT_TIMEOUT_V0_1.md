# r2db-api の auditreader に role 水準の `statement_timeout` を置く 設計メモ (v1.0)

- 状態: **監督確定 (2026-09-19)。設計レビュー 1 回を反映済み**。作業指示書は `docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md`。依頼者判断待ちの項目は無い (§11)。
- 台帳: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-56** (`RM`:453)。起票 2026-09-18 (R-51 の調査、`RM`:448)。
- 改版: v0.1 (2026-09-19) 起草。**v0.2 (2026-09-19) 監督裁定 1〜6 を反映**: D-4 を F-17 の両 peer 実装に確定し (裁定 1)、runbook だけの代替を X-4 として却下案へ回した (§8)、D-2 の 2 件の範囲外と台帳での扱いを確定した (裁定 2、§10)、WP の担当と順序を確定した (裁定 4、§9)、`part1_provision_host_and_db.sh` に `0013` と `0014` の両方を足すと決め、意図的な除外の形跡が無いことを現物で確かめた (裁定 5、§5)、完了条件 2 の位置づけと変異の分け方を確定した (裁定 6、§6)。**v0.1 の行は消していない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。 **v1.0 (2026-09-19) 設計レビュー 1 回目 (クラスの引き上げ・高 2・中 6・低 4) と監督裁定を反映**: **変更クラスを C から D に上げ** (§9)、`_ISOMORPHIC_TARGETS` に `_f17_message` を**行として足す**と直し (§4 D-4。v0.2 の「集合を増減させない」は訂正註で撤回)、`ALTER ROLE … SET` が既存の接続に効かない事実と再起動の手順を足し (高 1。§4 D-1・§5・§7)、F-17 を F-11 と同じ形で per-database の上書きも見る二条件にし (高 2・中 3。§4 D-4)、本番が適用まで `FAIL F-17` になることを開示し (中 4。§7・§10)、role の同定が実行 role に依る点を完了条件にし (中 5。§6)、完了条件 2 に自前の締め切りと経過時間の assert を入れ (中 6。§6)、`MIGRATION_NAMES` の挿入位置の問題を足し (中 7。§5)、配備 script は `0014` だけとし `0013` を台帳材料へ戻した (中 8。§5・§10)。低 4 件 (`pg_settings.setting` を読む・件数 pin の扱い・`0008` の psql 変数様式の理由・主張文への限定) も反映した。**v0.1・v0.2 の行は消していない。**
- 公開規律: `docs/work-orders/OPERATING_CONDITIONS.md` §2 の 13、§1.9。本メモは実 DSN・実ホスト名・実ドメイン・作業機のパス・traceback を 1 つも含まない。本番 (VPS) の値は `absent` として扱う (§7)。
- 実測の出所: すべて本リポジトリの現物 (`main` `7ad7588` 時点)。ファイルは相対パス + `:行番号` で引く。

---

## 1. 問題

r2db-api の `r2dbsvc_auditreader` には `statement_timeout` が無く、コード側にも実行中の監査クエリを打ち切る仕組みが無い。

- role の作成は `r2db-api/migrations/0007_application_audit.sql`:194-198 (`CONNECTION LIMIT 5`)。`ALTER ROLE ... SET statement_timeout` を置く行は migration 13 本のどこにも無い (grep 0 件)。
- `PostgresAuditQueryStore` (`r2db-api/src/r2db_api/credential_store.py`:1713 以下) は `_RolePool` (`r2db-api/src/r2db_api/postgres.py`:235) から接続を取る。`_RolePool._connect` (:288-294) が接続時に送るのは `SET search_path` の 1 文だけで、timeout は送らない。`connect_timeout`/`acquire_timeout` は「接続の確立」と「プールの取得待ち」だけを縛り、実行中の文は縛らない。
- クエリ側の上限は SQL の `LIMIT %(row_limit)s` (`credential_store.py`:1704) だけで、実行時間の上限は無い。

結果として、遅い監査クエリは `CONNECTION LIMIT 5` の reader の接続を上限なしに占有しうる。MitateDB-api は同じ役に `MitateDB-api/migrations/0013_role_statement_timeouts.sql`:71 で 5000ms を置いた。

`CLAUDE.md` (Security Invariants / Boundaries の節) は platform 固有の制御の差を許すが、それは**同じ安全上の結果**を別の手段で満たしている場合である。SI-08 (`security/SECURITY_INVARIANTS_V1.md`:226-250) が要求する「執行時間が有界であり、上限を超えたら決定的に終わる」を r2db がこの経路で別の手段で満たしている事実は無い (上の 3 点)。

この差は意図した差ではない。R-45 は MitateDB-api 固有の目的 (`operation_depth` の platform upgrade) で起票され (`RM`:442)、その WP-F が MitateDB にだけ `0013` を入れた。WP-F の枠自身が「対象外: …`idle_in_transaction_session_timeout`、`lock_timeout`、…r2db-api」と明記している (`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`:923、:973)。すなわち r2db を外したのは範囲の切り方であって、安全上の判断ではない。

## 2. 守るべき条件

- (i) 公開契約 `spec/` を変えない。`statement_timeout` は `spec/` にも `conformance-tests/` にも現れない (grep 0 件)。契約が公開するのは `execution_ms` の `reference_wall_clock` であり、本件はその下の platform 制御である。
- (ii) 既存の writer の timeout (`r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql`:127-130) と F-16 (`check_role_connection_limits`、`r2db-api/src/r2db_api/platform_declarations.py`:1020) を変えない。
- (iii) r2db の本番 (VPS) には何も適用しない。手順を書くだけである。
- (iv) peer 間でコードを共有しない (依頼者裁定 2026-09-03)。同名の実装は各 peer が独立に持ち、`_ISOMORPHIC_TARGETS` が正規化差分で固定する。
- (v) fail-closed。migration は失敗したら何も残さない。

## 3. 現物の事実

### 3.1 role 水準の `statement_timeout` の現行

| role | r2db-api | MitateDB-api |
|---|---|---|
| api (writer) | `5000ms` — `0008`:127 | `5000ms` — `0007_platform_declarations.sql`:98-101 |
| controlplane (writer) | `5000ms` — `0008`:129 | 同上 |
| auditreader | **無し** (本件) | `5000ms` — `0013_role_statement_timeouts.sql`:71 |
| application の runtime / developer | **無し** | `5000ms` — 同 :92、:95 (遡及)、:157、:163、:170、:176 (`begin_provision_application`) |
| control / provision (CLI の役) | 無し (`0008` は `:api_role`/`:controlplane_role` しか `ALTER` しない) | 無し |
| `lock_timeout` | role 水準ではどの役にも無い | 同左 |

- 番号の対応: r2db の `0013_role_connection_limits.sql` は MitateDB の `0012_role_connection_limits.sql` と同じ内容で、MitateDB の `0013` とは別物である。migration の番号を peer 間で対応させる対象ではない (`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md`:686 の F-R19)。

### 3.2 監査読み取り経路 (r2db) の現状

- DSN は任意設定の `R2DB_AUDIT_DSN` (`r2db-api/src/r2db_api/control_main.py`:510)。未設定なら `audit_query` は `CAPABILITY_UNSUPPORTED` を返す。
- pool は固定 `pool_size` 4 (`credential_store.py`:1739、`R2DB_PLATFORM_POOL_SIZE` の既定)。`CONNECTION LIMIT 5` は F-16 の床を既に満たしている (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`:339 の表)。
- 例外: `PostgresAuditQueryStore.query` は接続〜fetch を `except psycopg.Error:` で一括して捕らえ、`fail("SERVICE_UNAVAILABLE", "The database could not complete the request.", status=503)` を出す (`credential_store.py`:1772-1779)。メッセージは固定文で、DSN・SQL・PostgreSQL のエラー文を含まない。`QueryCanceled` は `psycopg.Error` の一種なので、この一括で 503 に落ちる。
- 接続は `autocommit=False` (`postgres.py`:299)。`_RolePool.connection()` の `finally` は、返却時に取引が IDLE でなければ `rollback()` する (:399-405)。`query` は接続の取得・実行・`fetchall` を 1 つの `with` の中で完結させる (`credential_store.py`:1773-1777) ので、取引が client の I/O を待って開いたままになる窓は無い。

### 3.3 MitateDB `0013` の作法 (D-1 が倣う先)

- §1 は**存在検査を付けない**素の `ALTER ROLE mitatedbsvc_auditreader SET statement_timeout = '5000ms'` (:71)。role が無い platform (0005 未適用) では undefined-role で失敗し、ファイル全体が巻き戻る — ヘッダの ORDER の条 (:18-29) がその順序を現在形で宣言している。存在検査 (`IF EXISTS`) を使うのは、台帳に載る application の役を回す §2 のループだけ (:91-96)。
- ファイル全体が 1 つのトランザクション (`BEGIN;` :62 / `COMMIT;` :192)。冪等性はヘッダ :51-54 が宣言する (`ALTER ROLE ... SET` は毎回同じ終端状態に収束する)。
- 権限の前提: `ALTER ROLE ... SET` は CREATEROLE かつ対象 role への ADMIN OPTION を持つ役だけが実行できる。PostgreSQL 16 は CREATEROLE の保持者に、自分が作った role への暗黙の ADMIN OPTION だけを与える。したがって auditreader を作ったのと同じ役で繋いだときだけ成功する (ヘッダ :31-44、実測は `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md`:685 の F-R27)。回避しない (SECURITY DEFINER にしない、権限の無い role を飛ばさない) が監督裁定 F-S3 である。
- 値 `5000ms` の根拠 (監督裁定 F-S1、同 :683): writer に置く値・`max_execution_ms` の既定値と同じ数であり、「期限を渡されない文の上限」を platform で 1 つの数にするため。値が効くのは期限を持たない経路だけで、要求の経路は `SET LOCAL` が上書きする。

## 4. 決定

### D-1 新しい platform migration `0014` を足す

- ファイル名の提案: **`0014_auditreader_statement_timeout.sql`**。既存の命名 (`00NN_<主題>.sql`、`_upgrade.sql` で終わらないものが platform 単発) に倣う。peer の `0013_role_statement_timeouts.sql` の名を借りない — D-2 により application の役を含まないので、複数形の名は範囲を過大に主張する。
- 中身は 1 文: `ALTER ROLE r2dbsvc_auditreader SET statement_timeout = '5000ms';`。§3.3 の作法に揃え、存在検査を付けず、`BEGIN;`/`COMMIT;` で囲み、ヘッダに WHO RUNS THIS (`$R2DBSVC_CONTROL_DSN`、`-v ON_ERROR_STOP=1`)・ORDER (`0007` の後)・PERMISSIONS (ADMIN OPTION の前提と、満たされないときは全体が巻き戻ること)・IDEMPOTENCY・既存配備への追加のみである旨を現在形で書く。
- role 名はリテラルで書く。テストは migration の本文に `text.replace("r2dbsvc", prefix)` を掛けて使い捨てクラスタへ流す方式 (`r2db-api/tests/test_audit_query.py`:213-217) なので、リテラルで prefix 置換が効く。`0013_role_connection_limits.sql`:108-109 も同じ形である。
- role 水準に置く理由: クライアントのコードに依らず、reader の DSN で繋ぐ**適用後に開かれる全ての接続** (運用者の手の psql を含む) に効く。X-1 との差は §8。
- **既存の接続には効かない (設計レビュー 高 1、2026-09-19)。** `ALTER ROLE … SET` は role 設定であり、login 時に session へ写る。`_RolePool` は接続を長期保持し (`postgres.py`:235-302)、`_liveness_check` (:351-379) は `SELECT 1` + `rollback` だけで設定を読み直さず、年齢による張り替えも無い。したがって `0014` を適用しても、稼働中の control プロセスが既に握る reader の接続は無期限のまま残る。**`0014` のヘッダに ORDER・PERMISSIONS と並べてこの事実と「適用後に reader の pool を持つ process (control) を再起動する」を現在形で書く。** 作法は `0008` と同じで、writer 側の F-7/F-11 の文言が既に `then restart both processes.` で終わる (`_f7_message` :606-625、`_f10_message` :630-636、`_f11_message` :640-646)。runbook への手順は §5、`CONTROL_MAPPING` の主張文の限定は §7。
- **様式の理由 (設計レビュー 低 11)**: timeout を置く既存の `0008` は role 名を psql 変数 (`:"api_role"`/`:"controlplane_role"`) で受ける。その様式は「`ALTER ROLE` の対象と宣言表へ seed する行を同じ変数・同じトランザクションから作り、独立にずれないようにする」ための監督裁定 D-2(h) 1 に基づく (`0008_platform_declarations_and_writer_timeouts.sql`:18-26)。**`0014` は宣言表へ seed する行を持たないので、この理由が掛からない。** よって `0013_role_connection_limits.sql`:108-109 と同じリテラル表記を採る。
- 値 `5000ms`: MitateDB の reader と同じ数であり、r2db の writer 2 役 (`0008`:127-130) とも揃う。

### D-2 application の runtime / developer role には足さない

根拠は、r2db のデータ面が取引ごとに `execution_ms` を `SET LOCAL statement_timeout`/`lock_timeout` に写していることである (`postgres.py`:2282-2297、値は `_timeout_ms` :2275-2280 が `ResourceLimits.execution_ms` と要求の期限から導く)。

**ただし全ての経路がそこを通るわけではない。現物で確かめた結果は次のとおりで、判定は監督に委ねる。**

| 経路 | `SET LOCAL` を通るか | 出所 |
|---|---|---|
| `PostgresCell.query` | 通る | `postgres.py`:1153 → :1175 |
| `PostgresCell.transact` | 通る | 同 :1232 → :1284 |
| `PostgresCell.apply_schema` (DDL) | 通る | 同 :1715 → :1753 |
| `PostgresCell.catalog` | **通らない** | 同 :803-807。`self._runtime.connection()` + `conn.transaction()` で `_load_catalog` を呼ぶだけで `_set_timeouts` を呼ばない **【追記 2026-09-21】** R-62 (main `3a52296`) で `catalog` も**取引ごとの `SET LOCAL` を通るようになった** — `postgres.py` の `catalog(self, limits=None)` が取引の先頭で `_set_timeouts` を発行し、打ち切りは他の 3 操作と同じ `LIMIT_EXCEEDED` (413) に写る。左の「通らない」は 2026-09-19 時点の実測で、行は消さない。 |
| provisioning / deprovision (`0003`/`0004`) と `ops upgrade-applications` | 通らない | `ops.py`:1484 以下 (:1495 で provision DSN、:1523 で application ごとの DSN)。application database へ **provision 役** (`r2dbsvc_control`) で繋ぐ。その役には role 水準の timeout が無い (§3.1) |

- `catalog` は client が到達できるデータ面の操作である (`r2db-api/src/r2db_api/service.py`:933-948 の `DataService.catalog` が `self._cells[...].catalog()` を呼ぶ)。すなわち runtime role で、上限の無い文が 1 つ、認証済みの client の要求から起きうる。
- 判定材料: (a) R-56 の起票文 (`RM`:453) は auditreader の差だけを問題にしている。(b) MitateDB は `0013` で runtime/developer に role 水準の 5000ms を置いたので、この経路を peer は既に覆っている — r2db で足さないなら peer 間の差として §7 で開示する必要がある。(c) `catalog` を `_set_timeouts` に通す直しは migration ではなくコードの直しで、本件 (Class C、`security/` と migration) とは変更クラスが違う。(d) `r2dbsvc_control` の経路は運用者が 1 回ずつ流すもので、client からは到達できない。
- **監督裁定 2 (2026-09-19)**: application role に role 水準の timeout を足さない、を維持する。`PostgresCell.catalog` が `_set_timeouts` を通らない件と、`r2dbsvc_control` (および MitateDB の provision 役) に role 水準の timeout が無い件は、**どちらも R-56 の範囲外**とし §10 の台帳の材料に残す。前者は監督が次の台帳項目として起票し、migration ではなく**コードで直す**。後者は DDL を流す役であり、`ops` が `--lock-timeout` を要求する経路 (MitateDB の `apply-platform-migration`、`MitateDB-api/src/mitatedb_api/ops.py`:636-643、:740-746。r2db に同等の引数は無い) との関係を含めて別に判断する。

### D-3 `idle_in_transaction_session_timeout` は reader に置かない

- 現物: §3.2 のとおり reader の接続は `autocommit=False` だが、`query` は取引を 1 つの `with` の中で開いて閉じる。返却時に IDLE でなければ `_RolePool.connection()` の `finally` が `rollback()` する (`postgres.py`:399-405)。`_liveness_check` の `SELECT 1` も直後に `rollback()` する (:365-370)。したがって「取引を開いたまま client を待つ」経路が無い。
- MitateDB `0013` も reader に置いていない。その理由は「安全上不要」ではなく**範囲外と定めたから**である — WP-F の枠が「対象外 … `idle_in_transaction_session_timeout`、`lock_timeout`」と書いている (`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`:923、:973)。r2db 側の根拠は上の現物であって、peer の不在ではない。
- したがって `0014` は `statement_timeout` の 1 文だけとする。

### D-4 値が本番に入っているかを運用者が確かめられる形

r2db には MitateDB の `ops inventory` に相当するコマンドが無い (grep 0 件)。既存の読み取り専用の運用コマンド `ops verify-declarations` を現物で評価した。

**性格 (現物)**: `platform_declarations.PROVISION_DSN_ENV` (= `R2DB_CONTROL_DSN`) の 1 本の接続で、宣言表と PostgreSQL のカタログを読むだけの、書き込みの無いコマンドである。失敗は `FAIL <F 番号> <文>` の 1 行と、F 番号ごとの固定の終了コードで表す (`ops.py`:985-1012 の `_VERIFY_DECLARATIONS_EXIT_CODES`、:1035-1041)。F-16 までが埋まっており、終了コードは 15 までが使用済みである。

**適合の判断**: 合う。理由は 3 つ。

1. 読む対象が既にある。`pg_db_role_setting` は誰でも読める共有カタログで、`_role_setting_rows` (`platform_declarations.py`:672-688) がその読みを既に持つ。reader の DSN は要らず、control の DSN だけで判定できる。
2. 値の解釈の道具が既にある。`pg_timeouts.ms_from_pg_timeout_text` (`r2db-api/src/r2db_api/pg_timeouts.py`) は `SHOW` の `5s` と宣言の `5000ms` を同じ ms に正規化する。MitateDB の (6) の値判定もこの関数を使う (`MitateDB-api/src/mitatedb_api/ops.py`:2427)。
3. 役の見つけ方の作法が既にある。F-16 は role を**名前ではなく実際の GRANT** で同定する (`platform_declarations.py`:1035-1045)。同定できない role は黙って飛ばす。新しい検査も同じ作法に従える。

**採用形** (監督裁定 1): `platform_declarations` に新しい検査を足し、`ops verify-declarations` から**だけ**呼ぶ。**同じ枝を両 peer に足す**。

- F 番号は **F-17**、終了コードは次の未使用の **16**。
- 判定 (監督裁定 1、2026-09-19): 実際の GRANT で auditreader と同定できた役について、`setdatabase = 0` の `statement_timeout` を読み、`ms_from_pg_timeout_text` で解釈して**正の値**なら合格。0・負・解釈できない値は F-17 で失敗する (PostgreSQL は `0` を「上限なし」と読むため、「何か宣言されている」を合格にしない)。宣言が無い場合も F-17 で失敗する — MitateDB の `inventory` (6) が `unknown` に落とすのは、あれが**未適用も含めて現状を報告する**棚卸しの道具だからであり、`verify-declarations` は「この配備は起動してよい状態か」の合否を返す道具なので、同じ扱いにはしない。
- **per-database の上書きも見る (設計レビュー 高 2・中 3、2026-09-19)。** F-17 は writer の F-11 と同じ形で 2 つを見る: **(i)** reader の role 単位 (`setdatabase = 0`) の `statement_timeout` が正の値であること、**(ii)** その役に database 単位 (`ALTER ROLE … IN DATABASE … SET`) で `statement_timeout` を上書きする行が**無い**こと (在れば赤)。per-database 行は role 行に優先するので、(i) だけだと `ALTER ROLE … IN DATABASE … SET statement_timeout = 0` が在る platform で実際は無制限なのに `OK F-17` が出る。読みは `_role_setting_rows` (`platform_declarations.py`:672-688) が既に `setdatabase IN (0, 自 DB の oid)` で両方を返す。文言は `_f11_message` (:640-647) の絞り込み方に倣い、「その timeout キーに実際に言及する per-database 行」だけを赤にする (無関係な GUC の per-database 行で起動を止めない、という既存の絞り込み。`read_declared_role_timeouts` :691-699 の註、出所は :599 の `F-11 の絞り込み`)。
- **auditreader の役がそもそも無い platform** (`0007` / MitateDB の `0005` が未適用) は**該当なしとして緑**にする。作法は F-16 と同じで、実際の GRANT でその形に同定できない役は黙って飛ばし、決して flag しない (`platform_declarations.py`:1040-1045「this check only ever verifies roles it can positively identify」)。同定できる役が 1 つも無ければ検査すべき対象が無いので `OK F-17` を出す。
- **これは宣言の検査であって、稼働中の process の実効値の検査ではない (設計レビュー 高 2)。** writer 側は F-9 が `read_effective_timeouts_ms` (`platform_declarations.py`:726-733) で**自分の接続の**実効値と宣言を突き合わせる二段だが、それができるのは writer の process が自分の role で繋いでいるからである。reader の DSN を持つのは control の process だけで、`verify-declarations` は control DSN 1 本の読み取り専用という性格 (§4 冒頭) を保つため、**reader の DSN で接続して実効値を読むことはしない** (監督裁定 2026-09-19)。役割分担はこうである: **宣言が正しいこと**は F-17 が本番でも機械で見る。**その宣言が実際に session へ効くこと**は §6 の完了条件 1 の実 PostgreSQL のテストが持つ (reader の DSN で接続し `pg_settings.setting` を読む)。高 1 の窓 (適用前に開かれた既存の接続) は、どちらでもなく **runbook の再起動の手順**が閉じる。
- 値も、解釈した ms も、raw の文字列も出力に出さない (`ops.py`:1035 の `OK`/`FAIL` の形を崩さない)。
- **起動時検査にはしない** (X-2)。`r2db_api.main`/`r2db_api.control_main` からは呼ばない。既存の配備が migration の適用前に起動できなくなる結合を作らないためである。F-16 が `role_classes` の絞り込みを持つのと同じ理由 (`platform_declarations.py`:1047-1064) で、検査の置き場と呼び出し元は分けられる。

**両 peer に足す理由 (現物)**: `_verify_declarations_checks` と `cmd_verify_declarations`、および `_VERIFY_DECLARATIONS_EXIT_CODES`・`_VERIFY_DECLARATIONS_READ_ORDER`・`_verify_declarations_ok`・`_verify_declarations_fail` は、**peer 間の正規化差分で固定された同型の対象**である (`r2db-api/tests/test_audit_query.py`:2389-2392、:2661-2662。件数 pin は同 :3222 の 138)。r2db の `_verify_declarations_checks` に F-17 の枝を足すなら、同じ枝を MitateDB-api の同名関数にも足さない限りこの pin が赤くなる。

- MitateDB 側は `0013` が既に reader に 5000ms を置いているので、同じ F-17 を足しても**その peer の migration は変えずに緑になる**。足すのは検査と終了コードの表と、peer ごとの `check_*` の本体である (共有せず同名で各 peer に置く、条件 (iv))。
- ~~**同型の pin の扱い** (監督裁定 1): これは**登録済みの同型 helper の本体の変更**であり Class C の契機である。`_ISOMORPHIC_TARGETS` の**集合は増減させない** (増減させれば Class D になる)。件数 pin … と逐語の期待値 … は**実測で更新する**。~~ — **v0.2 のこの判断を設計レビュー 1 回目と監督裁定 (2026-09-19) が覆した。行は消さない。**
- **同型の pin の扱い (v1.0 で確定)**: **`_f17_message` (および F-17 が足す定数が在ればそれ) を `_ISOMORPHIC_TARGETS` の行として足す。** 先例は F-16 で、`_table_owner`・`_roles_with_table_privilege`・`_ROLE_CLASSES`・床 3 定数 (`_API_ROLE_STORE_COUNT`・`_CONTROLPLANE_ROLE_POOL_FLOOR`・`_AUDITREADER_ROLE_POOL_FLOOR`)・`_f16_message` を行として足し、`check_role_connection_limits` 本体だけを除外した (`r2db-api/tests/test_audit_query.py`:2889-2895、除外の理由は :2844-2845)。`_f17_message` は peer 固有のリテラルを持たない同じ種類であり、行にしないと **F-1〜F-16 の中で唯一 pin されない F-message** になって、両 peer が文言と判定で分岐しうる。
- 集合の増減そのものが Class D の契機だが、**本件は既に D である** (§9) ので pin を弱める動機は無い。件数 pin (両 peer の `tests/test_audit_query.py`:3222 / :3000 の **138**) と、そこに並ぶ逐語の期待値 (:2971 以下 / :2749 以下) は、**足した行数だけ実測で更新する** (設計レビュー 低 10。v0.2 の「変わったら止まる」に当たる記述は、集合を増やす裁定に変わったので採らない)。
- したがって変更セットは MitateDB-api にも及ぶ。§9 の WP-2 に含める。runbook には `verify-declarations` を走らせて F-17 の行を読む手順を書く (SQL を手で叩く手順ではない、X-4)。

## 5. 追随する現物 (D-6)

列挙は `git ls-files r2db-api/migrations/` と `Path('r2db-api/migrations').rglob('*.sql')` の両方で行い、**どちらも同じ 13 本**を返すことを確かめた (未追跡の `.sql` は無い)。`0014` を足すと次が追随する。

| 現物 | 追随の中身 |
|---|---|
| `r2db-api/tests/test_audit_query.py`:71-98、:220-227 | `MIGRATION_NAMES` のリテラル列挙 + fixture の `_run_psql` 呼び出し |
| `r2db-api/tests/test_application_audit.py`:74 付近、:215 | 同 |
| `r2db-api/tests/test_credential_persistence.py`:195-201、:222 | 同 |
| `r2db-api/tests/test_process_ceilings_declaration.py`:123-125、:241 | 同 |
| `r2db-api/tests/test_ops_verify_declarations.py`:53-63、:171 | 同。F-17 のテストの置き場でもある。**`MIGRATION_NAMES_WITHOUT_DECLARATIONS = MIGRATION_NAMES[:-2]` (:69) は位置 slice で、同型 pin の対象である** (`test_audit_query.py`:2697) — §5 の「挿入位置」を見よ |
| `r2db-api/tests/test_ops_declarations.py`:66 付近、:167 | 同 |
| `r2db-api/tests/test_control_plane_store.py`:193 付近 | 同 |
| `r2db-api/tests/test_platform_upgrade_ledger_scan.py`:653、:677 | **件数 pin**。`{'適合': 3, '違反': 0, '免除': 0, '対象外': 10}` → `対象外` が 11 になる。`platform_single_shot_migrations` のタプルにも 1 行足す |
| `r2db-api/conformance/conformance_adapter_r2db_http.py`:364、:376 | 列挙と適用 |
| `r2db-api/conformance/real_server_r2db.py`:409、:427 | 同 |
| `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §5 (:384、:409-419 の「`0002` の後に来る platform migration」の段落) と新しい §19 | 適用手順、ADMIN OPTION の前提と満たされないときの直し方、**「`0014` の適用 → reader の pool を持つ process (control) の再起動 → `ops verify-declarations` で F-17 を読む」の順序** (高 1・中 4)、実行する役の明記 (中 5) |
| `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` | migration の一覧を持つ箇所 |
| `security/CONTROL_MAPPING.md` | §7 |

**`MIGRATION_NAMES` への `0014` の挿入位置 (設計レビュー 中 7、2026-09-19)**

- `r2db-api/tests/test_ops_verify_declarations.py`:69 の `MIGRATION_NAMES_WITHOUT_DECLARATIONS = MIGRATION_NAMES[:-2]` は**位置で選ぶ slice** であり、`_ISOMORPHIC_TARGETS` に登録済みである (`r2db-api/tests/test_audit_query.py`:2697)。意図は「`0008` と `0012` を落とす」(同 :65-68 の註) で、**末尾に `0014` を足すと落ちるのが `{0012, 0014}` になり、F-8 の fixture が壊れる**。
- MitateDB は同じ問題を、`0013` を `0007` の**前に**挿し、直後に**空振りしない `assert`** を置くことで処理した (`MitateDB-api/tests/test_ops_verify_declarations.py`:77-85)。r2db に同等の `assert` は無い (現物確認)。
- **直し (監督裁定 2026-09-19)**: 実装担当が**位置 slice に依る箇所を全部実測し、位置ではなく名前で選ぶ形に直す**。同型 pin の対象なら**両 peer を同じ形にする**。`0014` の挿入位置は、その直しの後に「適用順として正しい位置」(`0007` の後) で決める。直しの前に `0014` を足さない。

**`part1_provision_host_and_db.sh` に足すのは `0014` だけ (設計レビュー 中 8、監督裁定 2026-09-19)**

- 現状: この script は `0001`/`0002`/`0005`/`0006`/`0007`/`0008`/`0012`/`0003` を流し、**`0013` を流していない** (grep 0 件、:295-419)。
- **意図的な除外の形跡は無い** (現物で確認した)。script 自身の適用順の見出しコメント (:280-292) は、流さない migration を明示的に名指しする形を取っており、`0004` (「intentionally never invoked by this script -- it is an operator-run teardown path」:285-286) と `0009` (「likewise never run directly here」:287-292) の 2 本を名指しするが、**`0013` には触れていない**。`docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md`:615、:976 の `0013` の記述も、配備 script から外す旨を一言も書いていない。時系列も取りこぼしと整合する: script の最後の変更は `ff229c7` (2026-09-09、WP-6a で `0012` を足した回)、`0013` の最後の変更は `8ea0ff1` (2026-09-10) で、script は `0013` の登場後に一度も更新されていない。
- ~~したがって WP-2 で**両方を足す**~~ — **v0.2 のこの判断を設計レビュー 中 8 と監督裁定 (2026-09-19) が覆した。行は消さない。** 理由: **`0013` は前提を持つ**。自身のヘッダが「`max_connections` must be re-checked against the runbook's own updated worked example before applying this migration」と現在形で要求する (`r2db-api/migrations/0013_role_connection_limits.sql`:95-98)。script に `max_connections` の確認は 1 つも無い (grep 0 件)。新規配備の onboarding に黙って入れると、その前提が消える。
- **確定: `0014` だけを足す。** `0014` は前提を持たない (role 設定を 1 つ置くだけで、接続数にも既存の値にも触れない)。script はこの段より前に同じ実行の中で `0007` を流す (:341-345) ので、`0014` が走る時点で auditreader の役は構成上存在する。位置は `0007` の後 (D-1 の ORDER)、形は既存の `0012` の段と同じ (`log` + `psql ... -v ON_ERROR_STOP=1 -f ...`)。適用順ヘッダ (:280-292) にも 1 行足す。
- `0013` が script に載っていない件は §10 の台帳材料に戻す。

**触らない現物 (測った上で)**:

- ~~`part1_provision_host_and_db.sh` は本件だけで直すと歪むので台帳の材料に上げる~~ — **v0.1 のこの判断を監督裁定 5 (2026-09-19) が覆した。行は消さない。**
- `r2db-api` に Dockerfile は無い (VPS 配備。`r2db-api/deploy/` は systemd と nginx の例のみ)。
- `r2db-api/migrations/0002_provisioning_functions.sql` の `begin_provision_application` (:86-129) は触らない (D-2)。
- `spec/`・`conformance-tests/` は触らない (条件 (i))。

## 6. テストと変異 (D-5)

**1 項目 1 テスト**。変異は `tools/dev/mutate.py` で 1 件ずつ赤にする。

| # | 完了条件 | 変異 |
|---|---|---|
| 1 | 実 PostgreSQL で、`0014` 適用後に **reader の DSN で新しく開いた**接続の実効値が 5000 である。読みは `pg_settings.setting` (生の ms の整数文字列) と `5000` の比較にする — `SHOW`/`current_setting` は割り切れる単位へ丸めるので使わない (`read_effective_timeouts_ms` の docstring `platform_declarations.py`:726-729 が現在形で決めている作法。設計レビュー 低 9) | `0014` の `ALTER ROLE ... SET` の行を外す → 赤 |
| 2 | 実 PostgreSQL で、`0014` が置いた 5000ms を**超える**監査の問い合わせを起こすと、HTTP の応答が 503・code `SERVICE_UNAVAILABLE` になり、body に DSN・SQL・PostgreSQL のエラー文が現れない。**テストは自前の締め切りを持つ**: 経過時間が上限 (例 8 秒) 未満であることを assert する。**`ALTER ROLE … SET` を外す変異では、問い合わせが最後まで走って 200 が返るか、この締め切りを超えるので、止まらずに赤になる** (設計レビュー 中 6・監督裁定 2026-09-19)。遅さは reader の SQL を遅くする方法で作る (ロック待ちに依らない — 依ると変異時に無限待ちになる)。store は scenario の中で**新規に構築**し、最初の問い合わせがその store の最初の使用であることを確かめる (`_RolePool` は接続を長期保持するので、先に開いた接続は旧値のままになる)。接続が pool に戻っていることは、**直後の通常の問い合わせが通ること**で観測する | 既存の `credential_store.py`:1778 の `except psycopg.Error:` を外す → 赤 (完了条件 1 の `ALTER ROLE ... SET` の除去とは**別項目**にする。監督裁定 6) |
| 3 | `0014` を 2 回続けて適用しても終端状態が同じで、2 回目も成功する (冪等) | `ALTER ROLE ... SET` を `ALTER ROLE ... RESET` に変える → 赤 |
| 4 | D-4 の検査の赤緑 (**両 peer**): 宣言が正の値なら `OK F-17` と終了コード 0、値を `0` に変えると `FAIL F-17` と終了コード 16、宣言を `RESET` しても `FAIL F-17`。auditreader の役が無い platform では `OK F-17` と終了コード 0。出力に値も ms も raw の文字列も現れない | 検査の `declared_ms <= 0` の枝を外す → 赤。`_VERIFY_DECLARATIONS_EXIT_CODES` の `F-17` を別の数に変える → 赤。役が無いときに失敗させる (同定できない役を flag する) → 赤 |
| 4b | (i) と (ii) の二条件のうち **(ii)** — `ALTER ROLE <auditreader> IN DATABASE <platform db> SET statement_timeout = 0` を置くと `FAIL F-17` になる (role 単位の宣言は正のまま) | per-database 行を見る枝を外す → 赤 |
| 4c | **役の同定が実際の DSN で成立する (設計レビュー 中 5)。** `verify-declarations` が実際に使う DSN の役 (`R2DB_CONTROL_DSN` = provision/control の役) で走らせたとき、「auditreader は在るが `statement_timeout` の宣言が無い」が**赤になる**こと。同定は F-16 と同じ `information_schema.role_table_grants` 経由 (`platform_declarations.py`:963-975) だが、この view が返す行は実行 role に依りうる。**その DSN で同定が 0 件になるなら、実装せず実測を報告して止まる** (裁定は監督) | 監査照合 + 実測。使い捨てクラスタで 1 件測り、集計と同定できた役の**数**を報告に残す (役名は prefix 置換後の合成値) |
| 5 | §5 の追随の一覧に載る現物がすべて `0014` を含み、`test_platform_upgrade_ledger_scan.py` の集計が `対象外: 11` になる | 一覧の 1 本から `0014` を落とす → その fixture を使うテストが赤 |
| 6 | 両 peer の `_verify_declarations_checks` が正規化差分で一致したままである。`_ISOMORPHIC_TARGETS` に `_f17_message` (と F-17 が足す定数) の**行が足され**、件数 pin (138) と逐語の期待値が**実測で更新**されている | r2db 側の F-17 の枝だけを消す → 同型のテストが赤。`_f17_message` の行を登録から外す → 件数 pin のテストが赤 |
| 7 | 上の対応表に対応の無い完了条件が無い | **監査照合** (本表)。照合対象の逐語記録を本メモの実施記録の節に残す |

- 条件 2 の作り方は R-51 の `MitateDB-api/tests/test_audit_query_reader_errors.py`:127-190 に倣う (sleep の長さに結果が依存しない形)。timeout は `0014` の 5000ms を待たず、テスト内で `ALTER ROLE ... SET statement_timeout` を短い値へ一時的に変え、後で元へ戻す (同 :127-136、:172-189)。
- 条件 2 は**製品コードを伴わないテスト追加でよい** (監督裁定 6)。現状の一括 `except` (§3.2) が既に満たす見込みだが、確かめるまでは見込みであり、赤緑で固定する。満たされないと分かったら報告して止まる (直しは R-56 の枠外。§10 の 4)。

## 7. 証拠の状態と `security/CONTROL_MAPPING.md` (D-7)

- 版を **2.11 → 2.12** に上げる。置き場は **SI-08 / r2db-api** の既定の小ブロック。
- **実測 (2026-09-19)**: SI-08 / r2db-api ブロックは主張 24 本・8,914 字。上限は 15,200 字 (`conformance-tests/test_control_mapping_register.py`:88 の `MAX_BLOCK_LENGTH`)、**残り 6,286 字**。新しい主張 1 本 + 証拠 1 本は余裕で入る。分割は不要である。参考に、同じ SI の MitateDB-api の既定ブロックは 11,858 字 (残り 3,342)、`ops inventory` ブロックは 8,349 字 (残り 6,851)。
- 足す主張 (Control)。**限定を主張文自身に書く (設計レビュー 低 12)**: `0014_auditreader_statement_timeout.sql` が `r2dbsvc_auditreader` に role 設定の `statement_timeout` を置き、**適用後に開かれる** reader の DSN の接続 (運用者の psql を含む) の文を 5000ms で打ち切る。**role 設定は login 時に session へ写るので、適用前から開いている接続には効かない — 適用後に reader の pool を持つ process を再起動する必要がある** (高 1)。上限に達した文は `QueryCanceled` になり、`PostgresAuditQueryStore.query` の `except psycopg.Error` が 503 `SERVICE_UNAVAILABLE` に写し、backend の文面を漏らさず接続を pool に返す。`ops verify-declarations` の **F-17** (終了コード 16) が、role 単位の `statement_timeout` が正の値であることと、それを上書きする per-database 行が無いことを見る。**F-17 は宣言の検査であって、稼働中の process の実効値の検査ではない** (高 2)。実効値の証拠は §6 の完了条件 1 のテストが持つ。
- Evidence: §6 のテスト名を列挙する。
- **peer 間の差の開示 (監督裁定 2。正直に書く)**: 主張に次の 1 文を入れる — 「MitateDB-api は `0013_role_statement_timeouts.sql` で application の runtime/developer role にも role 水準の `statement_timeout` を置くが、**r2db-api は application role に role 水準の timeout を置かず、取引ごとの `SET LOCAL` (`postgres.py`:2282-2297) に依る。`PostgresCell.catalog` の 1 経路はそれを通らない (台帳項目)**」。同じ安全上の結果を別の手段で得ている部分と、まだ得ていない 1 経路を、どちらも隠さずに書く。
- **本番の証拠**: `absent`。本件は本番 (VPS) に何も適用しない (条件 (iii))。Status 軸にその旨を 1 行置く。
- **本番が `FAIL F-17` になることの開示 (設計レビュー 中 4、監督裁定 2026-09-19)**: F-17 が出荷された後、本番 (VPS) で `ops verify-declarations` を走らせると、auditreader は `0007` の GRANT で同定でき、`0014` を適用するまで宣言が無いので **`FAIL F-17` / 終了コード 16** を返す。**これは意図した信号である** — 「この配備には reader の文の上限が無い」という本件そのものの事実を、道具が初めて機械で言うようになった状態である。安全性はそれまでと変わっていない (以前は検査が存在しなかっただけである)。**Status 軸に 1 行、runbook §19 に「`0014` の適用 → control の再起動 → `verify-declarations`」の順序として、引き継ぎ書に 1 行、それぞれ開示する。**

## 8. 却下した代替案

- **X-1 `_RolePool` の接続時に `SET statement_timeout` を送るだけにする** — reader の DSN を使う他のクライアント (運用者の psql、別の道具) に効かない。また MitateDB が `pg_db_role_setting` に置いた証拠と形が揃わず、同じ SI-08 の主張を 2 つの違う証拠で支えることになる。Q4 が writer について同じ判断を既に下している: `_RolePool` は per-connection の SESSION `SET` を「もう受け取らず発行もしない」(`postgres.py`:268-279)。
- **X-2 起動時に reader の timeout を検査して無ければ起動を拒む** — 既存の配備に「migration の適用」と「image/unit の起動」の順序の結合を作る。reader の DSN を持つ配備が `0014` の適用前に再起動すると起動できなくなる。D-4 はこれを避けて out-of-band の `verify-declarations` に置く。
- **X-4 D-4 を機械の検査にせず、runbook に `pg_db_role_setting` を読む SQL の確認手順だけを書く** (**監督裁定 1、2026-09-19 で却下**) — 運用者の手順に依る確認は機械で赤にならない。§6 の完了条件 4 が手順の逐語記録による監査照合にしかならず、値が外れたことを CI もゲートも検出しない。runbook には代わりに `verify-declarations` を走らせて F-17 の行を読む手順を書く (D-4)。
- **X-3 何もしない (差を許容して開示だけ)** — `CLAUDE.md` が許すのは「同じ安全上の結果を別の手段で満たしている」差である。§1 の 3 点のとおり、r2db にはその別の手段が無い。開示だけでは SI-08 の主張が成り立たない。

## 9. 変更クラスと WP の切り方 (D-8)

- ~~**変更クラス C** (`security/` と migration)~~ — **v0.1・v0.2 のこの判定を設計レビュー 1 回目と監督裁定 (2026-09-19) が覆した。行は消さない。**
- **変更クラスは D。** 根拠: WP-3 が触る `security/CONTROL_MAPPING.md` は `docs/design/ROADMAP_POST_PHASE7_V1.md` §9 の 8 の表の **D 行「`security/` 配下」**に当たる。機械判定も D である (`tools/change_class.py` の path 規則)。先例も D である (`docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md`:16 の表「WP-3 | **D** | `security/CONTROL_MAPPING.md` は最重ルール」)。`_ISOMORPHIC_TARGETS` に行を足すこと (§4 D-4) も独立に D の契機である。
- WP ごとのクラス (着手時に `tools/change_class.py` で確定する):

| WP | クラス | 導出 |
|---|---|---|
| WP-1 | **B** | 触る path に `security/`・`spec/`・`conformance-tests/`・`CLAUDE.md` が無く、`.md` 以外 (migration `.sql`・テスト・配備 script) を含む |
| WP-2 | **C** | 登録済みの同型 helper の本体の変更 (`_verify_declarations_checks` ほか) と `_ISOMORPHIC_TARGETS` への行の追加。後者は単独では D の契機だが、全体が既に D なので WP のクラスは C 以上であれば足りる |
| WP-3 | **D** | `security/CONTROL_MAPPING.md` (`security/` 配下) |

- **設計レビューは 1 回** (監督裁定 2026-09-19)。`RM` §9 の 8 の C 行の証拠欄は「設計レビュー 2 回」と書くが、`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 50 は「契約を触らないフェーズは 1 回」と定め、先例の R-52 も D で 1 回だった。本件は `spec/` を触らない (条件 (i))。

### 9.1 変更クラス D が求める追加証拠

- **依頼者裁定の逐語記録** (2026-09-19):

  > その方針で進めてください、完了まで行ってください、判断は推奨で進め後から報告してください。推奨は長期的な視点で製品価値のある判断にしてください。

  本メモの **D-1〜D-4 の決定は、この委任の下で監督が推奨として下したものである。** 依頼者の事前の個別裁定は受けていない。**完了後に依頼者へ報告する。**
- **版付きの security-contract 決定**: `security/CONTROL_MAPPING.md` **版 2.12** (§7)。`security/SECURITY_INVARIANTS_V1.md` の SI の本文は変えない — 本件は既存の SI-08 の下に統制と証拠を足すだけで、新しい invariant を作らない (`CLAUDE.md`「Security Invariants are not a feature gate」の節)。契約版数は据え置く (`spec/` を触らない)。
- WP の案 (並行させない。WP-1 → WP-2 → WP-3 の順):

| WP | 中身 | 触るパス |
|---|---|---|
| WP-1 | `0014` の追加、§6 の完了条件 1・2・3・5、§5 の追随 (位置 slice の直し → migration 一覧・conformance adapter・件数 pin)、配備 script に `0014` の段 | `r2db-api/migrations/0014_auditreader_statement_timeout.sql` (新規)、`r2db-api/tests/` の 7 ファイル、`r2db-api/conformance/` の 2 ファイル、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh` |
| WP-2 | D-4 の検査 (F-17) を**両 peer**に、`_ISOMORPHIC_TARGETS` への行の追加と件数 pin の実測更新、§6 の完了条件 4・4b・4c・6、両 runbook (適用 → 再起動 → `verify-declarations` の順序、実行する役、本番が `FAIL F-17` になることの開示) | 両 peer の `src/.../platform_declarations.py`・`ops.py`、両 peer の `tests/test_ops_verify_declarations.py`、両 peer の `tests/test_audit_query.py`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` |
| WP-3 | `security/CONTROL_MAPPING.md` 2.12、§6 の完了条件 7 の監査照合、本メモの実施記録 | `security/CONTROL_MAPPING.md`、`docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md`、`docs/design/ROADMAP_POST_PHASE7_V1.md` |

- **順次 (監督裁定 4、2026-09-19)。WP-1 と WP-2 は 1 人の実装担当が続けて行い、WP-3 はその後。並行 WP は置かない。** WP-1 と WP-2 は `r2db-api/tests/test_ops_verify_declarations.py` と `r2db-api/tests/test_audit_query.py` で触るファイルが重なり、`docs/work-orders/OPERATING_CONDITIONS.md` §1.2 の 16、17 の「重なり 0」を満たせないので、並行にはできない。
- 変更クラスの内訳は上の表のとおり。`tools/change_class.py`:44-52 が自ら開示するとおり、同型 helper の本体 (C) と `_ISOMORPHIC_TARGETS` の集合の増減 (D) は**内容レベル**の契機で path からは見えないので、機械判定は下限であって上限ではない。**本メモの D は人の判定である。**

## 10. 台帳へ起票する材料

本件の範囲に入れず、監督が `RM` §8 へ起票するかどうかを判定する材料。

1. **`PostgresCell.catalog` に文の上限が無い** (`postgres.py`:803-807)。client が到達できるデータ面の操作で、runtime role の文が 1 つ、`SET LOCAL` を通らずに走る。MitateDB は role 水準の 5000ms でこの経路を覆っている (§3.1)。**監督裁定 2 (2026-09-19): R-56 の範囲外。監督が次の台帳項目として起票し、migration ではなくコードで直す。** **【追記 2026-09-21】`RM` §8 の R-62 として起票し、閉じた。** main `3a52296` で `PostgresCell.catalog` は取引ごとの `SET LOCAL statement_timeout` / `lock_timeout` を通るようになり (上限は `ResourceLimits.execution_ms` から導く)、打ち切りと lock timeout は `LIMIT_EXCEEDED` (413) に写る。`security/CONTROL_MAPPING.md` **版 2.15** が peer 間の差の開示を更新した。記録は `docs/work-orders/WORK_ORDER_R62_R2DB_CATALOG_TIMEOUT_V1.md` §6。
2. **`r2dbsvc_control` (および MitateDB の provision 役) に role 水準の timeout が無い** (§3.1)。`0003`/`0004`/`ops upgrade-applications` が application database へ流す文は上限なしに走る。運用者が 1 回ずつ流すもので client からは到達できない。**監督裁定 2: R-56 の範囲外。DDL を流す役であり、`ops` が `--lock-timeout` を要求する経路 (MitateDB `ops.py`:636-643、:740-746。r2db に同等の引数は無い) との関係を含めて別に判断する。**
3. ~~`part1_provision_host_and_db.sh` が `0013` を流していない件を台帳の材料にする~~ — **監督裁定 5 (2026-09-19) が一度覆した。行は消さない。** → **v1.0 で台帳材料に戻した** (設計レビュー 中 8・監督裁定 2026-09-19)。**`0013` は前提を持つ**: 自身のヘッダが適用前の `max_connections` の再確認を要求するが (`0013_role_connection_limits.sql`:95-98)、script に確認は無い (grep 0 件)。したがって `0013` を script に足すには「`max_connections` の確認の段」を併せて置く必要があり、それは R-56 の範囲ではない。**script に足すのは `0014` だけである** (§5)。意図的な除外の形跡が現物に無いことは確かめてあるので (§5)、台帳には「取りこぼしであって意図ではない」という実測つきで起票する材料とする。
4. **r2db の監査 reader に R-51 相当の 2 段分類が無い** — `credential_store.py`:1778 の `except psycopg.Error` 一括は、MitateDB が R-51 で入れた `InsufficientPrivilege` → `StorageConfigurationError` / それ以外 → `AuditReaderUnavailable` の分類を持たない。**R-56 の範囲には入れない**: 応答は同じ 503 `SERVICE_UNAVAILABLE` で、SI-08 と SI-10 の安全上の結果は同じであり、`RM`:448 も「r2db-api の同じ `query` は `except psycopg.Error` → `SERVICE_UNAVAILABLE` を既に持つ (直す所なし)」と実測で閉じている。差は分類の粒度だけである。

## 11. 依頼者判断待ち

無し。依頼者指示 2026-09-19 (逐語): 「判断は推奨で進め後から報告」。

v0.1 が監督の裁定を要するとした 2 点 (§4 D-2 の末尾 = `catalog` を範囲に入れるか、§4 D-4 の末尾 = F-17 を採るか runbook だけにするか) は、**2026-09-19 の監督裁定 1〜6 で確定した**。未確定の項目は無い。
