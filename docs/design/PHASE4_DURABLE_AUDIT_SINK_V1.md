# フェーズ4 実施設計: application-plane 耐久 audit sink + audit_query

- 版数: v1.4 (2026-09-02。v1.0 = 初版。v1.1 = 起草時の疑義 7 件への監督裁定 R1〜R7 を反映。v1.2 = 独立レビュー (blocker 3 / major 11 / minor 8) 全件採用の監督裁定を反映 — D-1〜D-6・D-10 / §4 R-B / §5 U-1〜U-5 / §6 / §7 全節 / §8 / §9.2・9.3 / §10)
- v1.4 (2026-09-02): **依頼者裁定 (直接回答) を反映し §5 を確定形へ** — P4-D1〜P4-D5 を確定、§2 末尾に依頼者の設計原則を記録、本文の「U-x の決着待ち」を全て確定形へ。P4-D5 は監督推奨 (a) から (b) へ変更
- v1.3 (2026-09-02): 再確認レビューの新規 major 4 件 (N-1〜N-4) 全件採用の監督裁定を反映 — D-2 の allow 単独行の読み / D-3 バッファ類 4 種の非耐久化 / D-6 lag 導出式と両接続への timeout 強制 / 合体・buffer のプロセスローカル性 (§6.1・6.2 / §7.2・7.3 / §9.2 / §9.3)
- 位置づけ: `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §0「入らないもの」が明示的に繰延べた最後の項目 (application-plane 耐久 audit sink) の実施設計。`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-6 が control-plane についてのみ先行実施した規律を、application-plane へ持ち込む
- 直接の申し送り: `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` L303-305 の N-1 (バッチ監査の commit 後遅延発火と R-6 同一 tx 規律の整合)
- 体制: Fable 監督/設計/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー。完了条件・単一コミット規律・identity 確認は既存フェーズと同一
- 本文書の性格: **監督が確定した枠の実施設計**である。§3 の決定は監督確定、§5 は**依頼者が確定**した裁定 (P4-D1〜P4-D5)、§4 は却下済み。WP 分割は本文書に含めず別途作業指示書で行う

---

## 1. 問題設定と現状

### 1.1 application-plane の監査は両 peer とも揮発性である

- r2db-api: `r2db-api/src/r2db_api/audit.py` の `AuditSink` (L44-61) は純 in-memory list。`delete()` は L60-61 で常に `PermissionError` を送出する append-only だが、プロセス再起動で全消滅する。`DataService.__init__` (`r2db-api/src/r2db_api/service.py` L96) が既定生成する。**`AuditSink.append` は `AuditEvent` を 12 個の位置引数で構築しており `target_id` を渡さない** (`audit.py` L52。`_event` (`service.py` L354-355) も `target_id` 引数を持たない) — application-plane の `target_id` は現状すべて既定値のままである (§6.1 に実装要件として再掲)。
- MitateDB-api: `MitateDB-api/src/mitatedb_api/audit.py` の `AuditSink` (L19-62) も in-memory only。フィールドは 6 個 (`event_type`/`application_id`/`credential_id`/`outcome`/`detail`/`occurred_at`、L9-16) で、control-plane 側の 13 フィールドとは別形状 (`MitateDB-api/src/mitatedb_api/control_audit.py` L4-6 が意図的な区別として明記)。`_SAFE_EVENTS`/`_SAFE_DETAILS` の許可語彙外は `"unclassified"`/`"unspecified"` へ**黙って丸められる** (L24-37)。
- 契約 `audit.sink_failure_policy` (`spec/data-service-api.v1.json` L261) は、authentication/authorization denial・credential/Application lifecycle 変更・destructive/privilege-sensitive 操作・security-control failure の**耐久記録失敗を fail-closed** と定める。application-plane にはそもそも耐久記録が無いため、この条項は現状未実現である。
- `security/CONTROL_MAPPING.md` の SI-14 行がこれを一次記録として持つ: application-plane については「external append-only sink と sink-failure policy が未配備・未 evidenced (phase 3, still outstanding)」であり、CCR-14 は**control plane についてのみ**このギャップを閉じた。

### 1.2 発火位置はすべて「操作成功後」である

r2db-api (`r2db-api/src/r2db_api/service.py`):

| L | event_class | operation | outcome | 発火位置 |
|---|---|---|---|---|
| 112 | authentication | authenticate | allow | 認証成功後 |
| 115 | authentication_denial | authenticate | deny | 認証失敗時 (`_audit.append` 直呼び) |
| 222 | data_operation | query | allow | `cell.query()` 成功後 |
| 225 | authorization_denial | query | deny | except 節 |
| 257 | data_operation | mutate | allow | `cell.transact()` 成功後 |
| 260 | operation_denial | mutate | deny | except 節 |
| 278 | privilege_sensitive | schema | allow | `apply_schema()` 成功後 |
| 281 | privilege_denial | schema | deny | except 節 |
| 293 | data_operation | catalog | allow | 読み取り後 |
| 296 | authorization_denial | catalog | deny | except 節 |
| 317 | operation_denial | (呼出元 operation) | deny | `deny_unsupported` 経由 |

query 成功も記録している (L222) 点が MitateDB との非対称の起点である (この非対称は依頼者裁定 **P4-D5** により、MitateDB 側に emit サイトを追加して解消する)。

MitateDB-api: 記録対象は `create_collection` (`cell.py` L336-339)・`add_field` (L389-392)・単発 `delete` (L546-549)・バッチ内 delete (L757-765, L826-827)・auth 系 (`auth.py` L122-422) のみで、**query/insert/update の成功は一切記録しない** (`__record` の全 call site を実測)。

単発操作も post-commit 窓を持つ: `backend_postgres.py` の `create_collection` は L422 で `self._developer.commit()`、`add_field` は L444、`delete` は L684 で `self._runtime.commit()` を実行してから戻り、呼び出し元 `cell.py` がその後に record する。バッチは `pending_audit` を no-arg callable として積み (L757-765)、`self._backend.commit()` 成功後 (L766) にのみ発火する (L826-827)。**commit 済み・監査未記録**の窓が構造的に存在する。これが N-1 の実体であり、現状は sink が揮発性なので「実害が顕在化していないだけ」である。

### 1.3 同一 tx に載せる経路が application-plane には無い

- r2db-api: `StorageBackend.transact` / `apply_schema` (`r2db-api/src/r2db_api/backend.py` L39-100) は tx を内部でカプセル化し、呼び出し元 `DataService` に work ハンドルを露出しない。control-plane 側にはある `unit_of_work()` 抽象 (`credential_store.py` L201/L586/L914、in-memory は `auth.py` L103/L135) が application-plane には存在しない。
- MitateDB-api: backend 内で commit する (上記 L422/L444/L684/`cell.py` L766)。
- control-plane の同一 tx 書込みパターンは既にある: `r2db-api/src/r2db_api/credential_store.py` の `PostgresControlAuditSink.append` (L1086-1123) は `work` が渡されれば呼び出し元の tx 上で INSERT し、`work=None` なら単独 tx で commit する (denial 経路専用)。MitateDB は `control_audit.py` の `insert_control_audit_row` (L156-193) が呼び出し元の conn にそのまま INSERT し commit/rollback を呼ばない。

### 1.4 database 構成と権限の現状

- 両 peer とも **database-per-application**。platform registry (r2db: `r2dbsvc_platform` / `r2dbsvc_registry`、MitateDB: `mitatedb_platform` / `mitatedb_registry`) は各 application DB とは**別 database** であり、PostgreSQL に cross-database transaction は存在しない。
- data-plane プロセスは platform DB へ api role (`r2dbsvc_api` / `mitatedbsvc_api`) で接続し credential を SELECT する (r2db: `main.py` L17-18 の `R2DB_PLATFORM_DSN`、L242 で `PostgresCredentialStore`。MitateDB: `main.py` L179-180、`credential_store_postgres.py` L69-70/L350/L402/L436)。**`control_audit` への INSERT 権限は持たない** — MitateDB は `migrations/0002_registry_and_functions.sql` L253-254 が `applications`/`credentials` の SELECT のみを付与し、`control_audit` 関連の GRANT は `mitatedbsvc_api` にどこにも無い。r2db も 0006 の GRANT 一覧に `r2dbsvc_api` を名指す行が無い (`security/CONTROL_MAPPING.md` SI-00 行の (b) がこれを evidence として引用している)。
- `control_audit` は r2db `migrations/0006_control_plane_http.sql` L431-445 (13 列 + `recorded_at`)、MitateDB `migrations/0002_registry_and_functions.sql` L200-215 (13 列 + `recorded_at` + `audit_seq bigserial UNIQUE`)。control-plane process role は **INSERT のみ** (r2db 0006 L501、MitateDB 0002 L266 + sequence USAGE L271) — append-only は DB 権限で担保されており、アプリコードの規律に依存しない。SELECT は schema owner の暗黙特権のみで、**専用 reader role は存在しない** (r2db `credential_store.py` L1126-1130、MitateDB `control_audit.py` L196-206 が明記)。

### 1.5 audit_query は両 peer ともスタブである

- 宣言: r2db `service.py` L142、MitateDB `cell.py` L1075 — いずれも `{"status": "unavailable", "authority": "control_or_audit"}`。control-plane 側も unavailable (r2db `control_plane.py` L607、MitateDB `control_plane.py` L1159)。
- 実装: r2db `http.py` L397-419 の `post_audit_query`、MitateDB `http.py` L781-807 の同名ハンドラ。いずれも**data-plane app 上**にあり、application credential の通常認証経路 (`_authenticate`) を通した**後**に `CAPABILITY_UNSUPPORTED` を返すだけである。
- data-plane プロセスは control/audit credential を**構造的に検証できない**: r2db の `PostgresControlCredentialStore` は `control_main.py` L138/L215 でのみ構築され `main.py` は import すらしない。MitateDB も同様 (`http.py` L783-788 のコメントが R-4 の process-role 分離として明記)。control HTTP app は別 ASGI app である (r2db `control_http.py` L337-347 の `_ROUTES` 11 本、MitateDB `control_http.py` L327-338)。
- 共通 suite での被覆はゼロ: `conformance-tests/test_c11_response_schema_conformance.py` L101-111 が `AuditResult` / `AuditQueryRequest` の zero-coverage を「現時点で埋めようのない真のギャップ」として明記し、解消を「audit sink/query surface を実装するフェーズ」へ委ねている。C-09 も `conformance-tests/CONDITIONS.md` L17 で「not yet executable (common suite) — peer-local evidence only」である。

### 1.6 契約が定めていない部分

- `event_class` の**値**の語彙は契約に無い (`spec/data-service-api.v1.json` L262 はフィールド名 13 個の列挙のみ)。`data_operation` 等の具体値は各実装が自由に定義したものである。
- `AuditQueryRequest.after` (L278) の意味論は無い。`AuditResult` (L279) は `events` のみで閉鎖されており **next cursor が無い**。ただし `events[]` の各要素は意図的に開放されている (subordinate ruling 7(A))。
- `audit_query` の auth は "control or audit" (L98-105)。一方 `control_plane.authority` は audit credential を 3 つの読み取り endpoint に限定すると書き、実装も `_AUDIT_ROLE_ALLOWED_OPERATIONS` (r2db `control_plane.py` L182、MitateDB `control_plane.py` L80) を `control_capabilities`/`list_applications`/`list_credentials` に固定している。**この 2 箇所の整合は要注記**である (§5 U-4)。

### 1.7 その他の前提

- alert/metric/structured logging 機構は**両 peer に存在しない** (r2db: `logging.getLogger`/`import logging`/`"alert"` すべて 0 件。MitateDB: `logging` 0 件、`alert` の唯一の一致は `errors.py` L128 のコメント語)。
- MitateDB は 2026-09-01 に最初の実配備 (Cloud SQL PostgreSQL 16.14 + Cloud Run) が行われ、「配備実機ゼロ」前提が失効した (`docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` L115)。migration の in-place 編集は禁止、新番号のみ + 互換性論証必須。r2db は VPS 既存で 0001-0006。
- `audit_events` は両 MitateDB backend で collection 名として防御的に予約済み・契約未文書 (`backend_sqlite.py` L26 `_RESERVED`、`backend_postgres.py` L98 `_RESERVED_EXACT`。台帳項目)。app DB 内に platform 管理テーブルを置く前例は `_mdb_schema_revision` (`migrations/0003_provision_application.sql` L137-142) がある。

---

## 2. 守るべき条件

1. **SI-14 の最小 event class を耐久記録する**。契約 `sink_failure_policy` の fail-closed 類 (denial / lifecycle / destructive / privilege-sensitive / security-control failure) は「耐久記録できなければ操作を成立させない」。
2. **append-only を DB 権限で担保する**。書き手 role は INSERT のみを持つ。application authority は監査を author/update/delete できない (契約 `audit.immutability`)。`forbidden_fields` (credential/token/password/secret/private_key/sql/row_value) を載せない。
3. **通常 data-operation event は bounded buffer で吸収してよいが、黙って捨てない**。捨てるときは明示的 alert を伴う (契約 `sink_failure_policy` 後段)。
4. **監査増幅 DoS を作らない**。未認証 denial が無制限に耐久 INSERT を誘発する経路を残さない。
5. **既存 `control_audit` の挙動・テストを壊さない**。migration は新番号のみ。実配備インスタンスへの互換性論証を各 migration に書く。
6. **公開リポジトリ規律**を守る (秘密・実データ・実在ドメインなし)。共通契約を r2db/MitateDB のどちらかに暗黙所有させない。
7. **ガードレールでありゲートではない**。監査は操作の自由を狭めない (記録するだけ)。fail-closed は sink 障害時の安全側倒れに限る。

### 設計原則 (依頼者、2026-09-02)

1. **今やれることは今のうちにやる** — 先送りしない。
2. **設計・実装はシンプルに** — 目先の問題解決だけの措置を行わない。
3. **制約・制限で回避しない** — 難所を機能の制限で迂回しない。
4. **誇れる成果物であること**。

この 4 原則が §5 の裁定 (とくに P4-D5) の根拠であり、以後の WP でも判断基準として参照する。

---

## 3. 決定と根拠 (監督確定)

### D-1 置き場所 = platform DB の registry schema に新テーブル `application_audit`

`control_audit` と同一の 13 列 + `recorded_at` に、`audit_seq bigserial` と `count integer NULL` (「この行が代表する発生回数、NULL = 1」。D-4 の overflow alert 行と D-3 の合体 denial 行が使う) を加えた形とする (両 peer)。

根拠:
- (a) cross-database transaction が無い以上、app DB 側に置かない限り「データ変更と同一 tx」は原理的に不可能である。そして app DB 側に置くと、(i) deprovision (`DROP DATABASE`) で証拠が消える、(ii) `audit_query` が N database への fan-out になる、(iii) developer role が `public` schema の所有者である位置 (`0003_provision_application.sql` L144) に証拠を置くことになる。
- (b) `control_audit` と同居 (同一 schema) させれば、`audit_query` が単一 DB 接続で control 面と application 面の両方を読める。
- (c) 書き手 = data-plane プロセスが**既に保持している** platform 接続 (api role) に INSERT のみを新規 GRANT すればよく、control-plane で確立した「append-only by grant」をそのまま踏襲できる。

**容量側の新規露出とその有界化 (レビュー M-5)**: 本フェーズは data-plane の api role に platform DB への **INSERT 権限を新設する**。現状この role は `applications`/`credentials` の SELECT のみであり (§1.4)、書き込み経路そのものが存在しない。侵害された (あるいは暴走した) application-plane プロセスは、platform DB — **全 application の credential store と同居する DB** — のストレージを消費できるようになる。ディスク枯渇は全 application の認証停止に直結するため、これは SI-00 の "Application A compromise ≠ Application B compromise" の**可用性側**の露出である。有界化は 3 段構えで行う:

1. **1 行のサイズを有界化する** — 全 text 列に `CHECK (length(col) <= N)` を課す (§6.1/§6.2)。
2. **1 操作あたりの行数を有界化する** — 1 利用者操作 = 最大 1 行 (D-10)、denial は合体で窓あたり 1 行 (D-3)、通常 event は bounded buffer (D-4)。
3. **運用で監視する** — platform DB の容量監視を runbook 項目にする (§9.3)。

**可用性の依存関係 (レビュー m-6)**: platform DB は**既に** data-plane の認証の単一依存である (両 peer とも credential store がここにある。r2db `main.py` L242、MitateDB `credential_store_postgres.py`)。platform DB が落ちれば data-plane は認証段階で全面停止するため、本フェーズはその依存を耐久監査へ広げるだけで、**新たな単一障害点を作るわけではない**。ただし `audit_query` も同じ DB に依存するため、障害時の独立した読み取り路は帯域外 CLI (r2db `ops.py cmd_audit_report` L747-816 / MitateDB の対応コマンド) のみである。この点を runbook に書く (§9.3)。

- **壊れるシナリオ**: (i) app DB 側に置くと、調査が必要になる典型ケース (問題ある application の deprovision 直後) でその application の監査証拠だけが消えている。(ii) platform DB 側に置いた上で行サイズと行数を有界化しないと、1 application の侵害が platform DB を肥大させ、全 application の認証を巻き添えで止められる。
- **検証方法**: provision → 監査対象操作 → deprovision の順に実行し、platform DB 側に当該 application_id の行が残存することを実 PostgreSQL テストで実測する。加えて、api role が長さ制約を超える値を INSERT できないことを生の接続で実測する。

> 「app DB 内 (同一 tx で厳密)」案は依頼者裁定 **P4-D1** で却下された (§5 に却下理由を記録)。

### D-2 N-1 の解 = 「commit 前 durable 記録」+ outcome 語彙の精密化

fail-closed 類 (destructive / privilege-sensitive) の data-plane event は、データ tx を **commit する前**に platform 接続で耐久 INSERT + commit する。INSERT が失敗したらデータ tx を rollback し `SERVICE_UNAVAILABLE` を返す (fail-closed by construction)。

監査 commit とデータ commit の間のクラッシュ窓は「記録あり・データ未 commit」= **過剰記録側**に倒れる。したがって監査の `outcome` は「**認可され実行に投入された** (allow)」を意味し、commit 成功を主張しない。過少記録 (記録なし・データ commit 済み) は SI-14 の害そのものだが、過剰記録は以下の規則により調査で識別できる。

**未 commit の識別規則 (レビュー M-6、確定)**: 「過剰記録は調査で識別可能」は主張ではなく**規則**である。

> 同一 `request_id` に `outcome="allow"` の行と、その後の `outcome="error"` (`reason_code="commit_failed"`) の行が**両方**存在するとき、その操作は「投入されたが成立しなかった」と読む。`allow` 行**のみ**が存在するときは、「成立した」か「記録後にプロセスが消失した」かの**いずれか**であり、**監査面だけからは区別できない**。

`error` 行が覆うのは**プロセス生存下のクリーンな commit 失敗**のみである (レビュー N-1)。監査 commit とデータ commit の間でプロセスごと消失した場合、`error` 行を書く主体がもう居ないため `allow` 行が単独で残る — これは D-2 が意図した「過剰記録側に倒れる」挙動そのものであり、欠陥ではないが、**識別規則は 100% ではない**。調査者は `allow` 単独行をデータ面の実状態と突き合わせて判定する必要がある。この読みを設計と宣言の両方に残す。

したがって**データ commit が失敗した場合 (プロセスが生存している限り)、実装は必ず耐久 error 行を書かねばならない**。これは best-effort ではなく **fail-closed 類**であり、error 行が書けなければ応答は `SERVICE_UNAVAILABLE` になる。この規則は `audit_query` 利用者向けの宣言 (D-5 の `outcome_note`) にも明記する — AI エージェントの消費者が `allow` 行を単独で「削除が確実に実行された」と読むことを防ぐため。

**fail-closed 類とバッファ類の振り分け規則 (レビュー B-2、規範。実装裁量ではない)**: 振り分けは `event_class` では判定しない — r2db は delete を含む mutate と含まない mutate を同一の `data_operation` として発火し (`service.py` L257)、かつ `event_class` の語彙は D-7 で各 peer の宣言に委ねられているため、共通契約レベルの義務の判定子には使えない (循環する)。**リクエストの構造で判定する**:

**fail-closed 類**
1. `DESTRUCTIVE_CONFIRMATION_V1` の確認 choke を通る操作 — 単発/バッチの delete 等。両 peer とも `_validate_delete_confirmation` 相当の**単一の判定点**を既に持つ (フェーズ3 WP-1.5 で choke を一本化済み) ので、そこが振り分けの判定点になる。
2. **すべての** schema operation。
3. **すべての** lifecycle event (credential / Application)。
4. `security_control_failure`。
5. D-3 が耐久対象と定める denial。

**バッファ類** (bounded buffer 経由で耐久化)
query / catalog / **delete を含まない** mutate — すなわち通常の data-operation 成功 event のみ。

**非耐久** (耐久面にも buffer にも載せない、レビュー N-2)
D-3 が非耐久と定める 4 種の denial (`VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND`)。既存の in-memory sink にのみ残る。

両 peer で**判定点が同じ関数である**ことをテストで固定する (§9.2 の検証可能性質)。D-7 の宣言語彙は、この振り分けを表現できる粒度を持たねばならない (destructive を非 destructive と同じ class に畳む宣言は不可)。

実装上は backend の tx 境界に pre-commit hook (work ないしコールバック) を露出する必要がある (r2db `StorageBackend`、MitateDB `backend_postgres` の両方)。in-memory backend は同じ hook を擬似 tx で実装し、parity テストの対象とする。

- **壊れるシナリオ**: post-commit 記録のままだと、commit 直後のプロセス消失で「データは残り監査は無い」状態が生じ、destructive 操作の実行者が事後に特定できない。振り分けを `event_class` に委ねると、r2db 実装者が「`data_operation` はバッファ類」と読んで delete を含む mutate の行が overflow で捨てられ、契約 `sink_failure_policy` に不適合になる (宣言からは検出できない)。
- **検証方法**: sink 故障注入 (INSERT を例外化) で destructive mutate が `SERVICE_UNAVAILABLE` となりデータ側の行数が不変であることを実測する。データ commit 側に故障を注入し、同一 `request_id` の `allow` 行の後に `error` 行が耐久記録されることを実測する。delete を含む mutate が buffer 経路に載らないことを実測する。

> 「attempted 行 + committed 行の二行方式」は依頼者裁定 **P4-D2** で却下された (§5 に却下理由を記録)。

### D-3 denial の耐久記録 — 範囲を限定し、合体 (coalescing) で流量を有界化する

denial は状態変更を伴わないため**独立 tx** で INSERT する (同一 tx を要さない)。INSERT に失敗した場合は当該応答を `SERVICE_UNAVAILABLE` にする。これは control-plane R-6 の denial 規律と同型である。ただし v1.1 の「全 denial を無条件に同期耐久記録する」形は、行数の観点で無界であり成立しない (レビュー B-1 / M-2)。以下 2 点で限定する。

#### (1) 耐久対象とする denial の範囲

data-plane の denial 語彙は広い — 両 peer とも `except FoundationError` を丸ごと denial event へ変換しており (r2db `service.py` L219-225 / L258-260 / L280-281 / L295-296)、`VALIDATION_FAILED` も `LIMIT_EXCEEDED` も `CAPABILITY_UNSUPPORTED` も同じ経路に落ちる。SI-14 の最小 event class は「authentication/authorization denial」であって「あらゆる要求失敗」ではないので、次の線を引く。

| 分類 | 耐久面 | 対象 |
|---|---|---|
| **fail-closed 類** | **耐久記録する** (合体つき) | 認証系 (`AUTH_REQUIRED` / `AUTH_INVALID` 相当)、`FORBIDDEN`、`APPLICATION_DISABLED`、credential の disabled / revoked / must_rotate、`DESTRUCTIVE_CONFIRMATION_REQUIRED`、privilege denial |
| **非耐久** | **耐久面に載せない** | `VALIDATION_FAILED`、`LIMIT_EXCEEDED` (rate / concurrency)、`CAPABILITY_UNSUPPORTED`、`NOT_FOUND` |

**非耐久の 4 種は bounded buffer にも載せない (レビュー N-2)**。これらは既存の in-memory sink にのみ残り、`application_audit` には一切現れない。bounded buffer (D-4) は**通常の data-operation 成功 event 専用**である — buffer に入れてしまうと結局は耐久 INSERT されることになり、「耐久面に載せない」という判断が実現しない (かつ D-3 が防ごうとしている流量問題が buffer 経由で戻ってくる)。

この 4 種は SI-14 の最小 event class の外にある。契約 `sink_failure_policy` をより広く読むことも可能だが、**決めた線を `security/CONTROL_MAPPING.md` の SI-14 行に理由つきで書く** (§9.3)。なお **CCR-14 との関係は「非対称の解消」ではない** — control 面は rate 拒否を記録せず、data 面はこの 4 種を非耐久とする。**線引きは異なるが、いずれも SI-14 の最小 class の外**という同じ根拠に立つ。この点も SI-14 行への記載事項に含める。

#### (2) 合体 (coalescing) による流量の有界化

耐久対象の denial であっても、1 リクエスト = 1 INSERT では流量が無界である。**一度漏洩して revoke 済みの secret を 1 本持つ攻撃者がそれを毎秒 1 万回提示すれば、すべてが fail-closed 類として platform DB に落ちる** — 有界なのは拒否の*種類*であって*行数*ではない。よって合体する。

- **合体キー**: `(application_id, actor_id または "unknown", operation, reason_code)`
- **窓 W**: 60 秒 (実装裁量で可変。宣言で公開する)
- **窓内の初回**: 同期の耐久 INSERT + commit。失敗すれば当該応答を `SERVICE_UNAVAILABLE` (fail-closed)。
- **窓内の 2 回目以降**: メモリで計数のみ。窓終了時に **1 行**として flush し、発生回数を 14 列目 `count` に載せる。
- **クラッシュ時に失うのは窓内の計数のみ**で、初回行は既に耐久化されている。
- **合体カウンタはプロセスローカルである (レビュー N-4)**。共有ストアを介さないため、同一の合体キーでも**プロセス (インスタンス) ごとに 1 行**が出る。

これにより、未知 secret の連打も revoke 済み secret の連打も **プロセスあたり 1 行/窓**に有界化される。配備全体の実効上限は **窓数 × 最大インスタンス数 M** であり、「1 行/分」ではない — M は水平スケール設定 (Cloud Run の最大インスタンス数等) で決まるので、runbook の容量閾値算出にこの M を織り込む (§9.3)。新しい拒否経路 (= 正規テナントへの巻き添え面) を作らずに増幅を止められる点が、pre-auth rate window の追加より優れている。この形は依頼者裁定 **P4-D3** で確定した (§5 に却下した 3 案とその理由を記録)。

- **壊れるシナリオ**: 合体も範囲限定もしないと、(i) 漏洩済み secret 1 本の連打で監査テーブルが無制限に膨張し、platform DB 同居の credential store ごと全 application の認証を止められる (SI-00 の可用性側の破れ)、(ii) 壊れたクライアントの `VALIDATION_FAILED` 連発が、データ DB に触らない検証エラーを platform DB への同期ラウンドトリップに化けさせ、データ面のレイテンシに恒常的に上乗せされる。
- **検証方法**: 同一の無効 secret を N 回 (N ≫ 1) 提示し、窓内に増える耐久行がちょうど 1 行で `count = N` になることを実測する。`VALIDATION_FAILED` の連発では耐久行が増えないことを実測する。初回 INSERT に故障を注入すると応答が `SERVICE_UNAVAILABLE` になることを実測する。

### D-4 通常 data-operation event = bounded buffer + overflow の in-band alert

query/mutate の成功、catalog といった**通常の data-operation 成功 event** は、**bounded in-memory buffer (既定 1000、実装裁量で設定可)** に積み、定期または閾値でバッチ INSERT する。buffer の対象はこれのみである — D-3 が非耐久と定めた 4 種の denial は buffer にも載せない (レビュー N-2)。

**buffer はプロセスローカルである (レビュー N-4)**: 容量 1000 は**1 プロセスあたり**であり、配備全体では **1000 × 最大インスタンス数 M** の未 flush event が同時に存在し得る。同様に overflow alert も**プロセスごとに**発生する。runbook の容量閾値算出にこの M を織り込む (§9.3)。

**flush は常に別トランザクション・別接続で行う (レビュー M-1、確定)**。fail-closed 書込みの tx に**相乗りさせない** — 相乗りすると、契約がバッファで吸収してよいと定めた通常 event の書込み失敗 (例えば長さ制約違反の 1 行) が、利用者の destructive 操作を `SERVICE_UNAVAILABLE` で止めてしまい、`sink_failure_policy` が 2 類を分けた意図が逆転する。加えて条件7「監査はガードレールでありゲートではない」(§2) にも反する。fail-closed 行の commit 成否は buffer 行の成否に依存してはならない。

overflow 時は最古から捨て、同時に:
1. stdlib `logging.error` の**固定メッセージ**を発火する (可変部に application 識別子等の実データを載せない)。
2. `security_control_failure` event (`reason_code="audit_buffer_overflow"`, `operation="audit_buffer"`, `target_kind="audit_sink"`) を**耐久 INSERT** する。

この 2 番目が契約の言う「explicit operational alert」の in-band 実現である。運用側の logs-based alert 設定は runbook の管轄とする。捨てられた件数は、新設する 14 番目の列 **`count`** (「この行が代表する発生回数。NULL = 1」) に載せる (契約 `audit.fields_note` が `audit.fields` を additive 語彙と明記しているため適合)。`count` は overflow alert 行と D-3 の合体 denial 行の 2 用途が共有し、それ以外の event では NULL である。

- **壊れるシナリオ**: overflow を黙って捨てると、契約 `sink_failure_policy` 後段の「alert なしの silent discard」に不適合となり、監査に穴があること自体が観測不能になる。
- **検証方法**: buffer 容量を小さく設定して意図的に溢れさせ、`logging.error` の発火と `security_control_failure` 行がちょうど 1 件耐久記録されることを実測する。

### D-5 audit_query は control HTTP app のホスト上で、契約パスを逐語で提供する

data-plane プロセスは control/audit credential を検証できない (§1.5) ため、`audit_query` の実体は control HTTP app 側に置く。**ただし契約を変えない** — 契約は `audit_query` を `endpoints` (application surface) の `POST /v1/audit/query` に置いており、本フェーズではこの**パス文字列を逐語のまま** control surface のホスト上に提供する。契約は「どのホストがそのパスを提供するか」を規定しておらず、separability 条項は別配備を前提としているため、これは契約からの逸脱ではない (監督裁定 R1)。

- **control ホスト — 2 パスを両建てする (レビュー M-3)**: `POST /control/v1/audit/query` を**必ず**提供し、契約現行分類に追随するため `POST /v1/audit/query` を**同じハンドラの alias として併せて**提供する。片方だけにしない理由は配備の境界防御にある — 単一 ingress でパス前置詞ルーティング (`/v1/*` → data-plane、`/control/v1/*` → control-plane) をしている配備では `/v1/audit/query` が data-plane に届いてしまい監査取得が不能になる。逆に「`/control/v1` は管理ネットワークからのみ」というエッジポリシー (LB の path matcher 等) を敷いている配備では、control ホストの `/v1/audit/query` だけがそのポリシーの**外**に落ち、SI-02 が守る control-plane データへの経路がパス前置詞ベースの既存運用境界の外側に新設されてしまう。両建てにすれば、どちらの配備形態でも `/control/v1/audit/query` が正解の経路になる。認証は control/audit credential。
- **data-plane ホスト**: `POST /v1/audit/query` の既存スタブ挙動 (application credential を認証した後に `CAPABILITY_UNSUPPORTED`) は**不変**とする。data-plane の `/v1/capabilities` も `audit_query: unavailable` のまま — ホストごとに真実の宣言を出す (declaration = real behavior)。
- **宣言の置き場所**: control ホストは application surface の `/v1/capabilities` を提供しないため、`audit_query` の宣言は **`control_capabilities` 文書**に載せる。`control_capabilities` の応答も同じ `CapabilityDocument` であり、その `capabilities` は key space・各 entry の値 schema とも**開放**されている (subordinate ruling 7(A)) ため、**契約変更なしで載せられる** (監督が spec で確認済み)。形は次のとおりとし、visibility lag と D-2 の未 commit 識別規則もここで公開する。`status` の語彙は契約 enum の 4 値 (`enabled` / `partial` / `unavailable` / `planned`) — `"available"` という語は存在しないので使わない。

```
audit_query: {
  status: "enabled",
  authority: "control_or_audit",
  event_classes: [...],           // D-7 の宣言語彙
  default_limit: 100,
  visibility_lag_ms: <D-6 の導出値>,
  coalescing_window_ms: <D-3 の窓 W>,
  completeness_note: "A page shorter than limit does not mean the log is exhausted;
                      rows within visibility_lag_ms are not yet returned. Keep polling
                      with the cursor of the last event received until a page is empty.",
  outcome_note: "outcome=allow means the operation was authorized and submitted; an
                 outcome=error row with the same request_id means it did not commit."
}
```

`completeness_note` は AI エージェント消費者が最も踏みやすい罠 (`len(events) < limit` を終端と誤読する) を宣言側で塞ぐためのものである (レビュー m-3)。`CapabilityDocument.capabilities` の entry は開放されているのでキー追加に契約変更は要らない。
- **読み手**: **新規 reader role** (`r2dbsvc_auditreader` / `mitatedbsvc_auditreader`、SELECT のみ、`control_audit` + `application_audit`) を、control HTTP app が**任意の AUDIT DSN** で保持する。
- **AUDIT DSN 未設定時 (レビュー M-4)**: 宣言は `{"status": "unavailable"}` のまま据え置くが、**ルートは常に登録する**。未設定時は認証後に `CAPABILITY_UNSUPPORTED` の error envelope を返す (data-plane ホストの既存スタブと同型)。ルートを登録しないと Starlette が素の 404 を返し、契約 `control_plane.provision` の「unprovided operations fail with `CAPABILITY_UNSUPPORTED`」に反する — AI エージェントの消費者は 404 を「このホストは監査面を持たない」ではなく「URL 違い / サービス障害」と解釈してリトライやパス探索に走るし、conformance 側でも `absence.py` の「一様に refuse される」検査が成立しない (404 は refusal の語彙ではない)。
- **認可**: audit role credential については `_AUDIT_ROLE_ALLOWED_OPERATIONS` に `audit_query` を追加する。
- **rate 窓の扱い (レビュー M-8)**: `audit_query` は control ホストの**既存 global pre-auth window** (`control_requests_per_minute`。r2db `control_plane.py` L1225-1252、MitateDB `control_plane.py` L964-974 — いずれも per-credential ではない単一の窓) を消費する。監査エージェントが visibility lag を跨いで全件を追うために高頻度ポーリングすると窓を食い潰し、その瞬間に侵害対応で `revoke_credential` を打とうとした運用者が `LIMIT_EXCEEDED` で締め出され得る (しかも rate 拒否は CCR-14 の除外により耐久監査されないので、締め出しの記録も残らない)。**「証拠を読む」行為が「侵害を止める」行為を締め出す**この相互作用を、リスクとして runbook に明記し、窓サイズの設計に監査ポーリング分を織り込む (§9.3 / §10)。`audit_query` 専用の別窓 (`audit_requests_per_minute`) の新設は **P4-D4 の項目 8** として本フェーズ内で出荷する — これによりこの相互作用は構造的に解消される (runbook の記述は、窓が分離されるまでの過渡期と窓サイズ設計のために残す)。

> 契約側の整理 (`audit_query` を `control_endpoints` の `/control/v1/audit/query` へ移し、`/v1/audit/query` を 1 minor の間 alias とする) は **P4-D4 の項目 7** として本フェーズ内で出荷する。実装は先に両パスを両建てするため、契約側の分類が実装に追いつく形になる。

- **壊れるシナリオ**: (i) data-plane に control/audit credential store を持ち込むと、data-plane プロセス 1 つの侵害で control 面の verifier まで到達され、SI-00 の単一侵害封じ込めが崩れる。(ii) control ホストに `/v1/audit/query` しか置かないと、`/control/v1/*` を管理ネットワークに限定しているエッジポリシーの外側に control-plane データへの経路が新設される。
- **検証方法**: control ホストの両パス (`/control/v1/audit/query` と `/v1/audit/query`) が同一のハンドラに解決すること、application credential の提示が `FORBIDDEN` であること、control/audit credential の提示が成功すること、AUDIT DSN 未設定時に 404 ではなく `CAPABILITY_UNSUPPORTED` が返ること、data-plane ホストの同パスは既存どおり `CAPABILITY_UNSUPPORTED` であること、data-plane composition root が control credential store を import しないことの 6 点を実測する。

### D-6 audit_query の意味論 — 契約が未定義の部分を実装で先に確定する

契約が定めていない部分 (§1.6) を以下で確定する。契約側の明確化は **P4-D4** により本フェーズ内で 1.4.0 として出荷する。

- **順序**: `(recorded_at, plane, event_id)` の全順序。`control_audit` と `application_audit` の UNION を跨ぐため、`plane` を第 2 キーに入れて**両表の event_id が衝突しても全順序が壊れない**ようにする (レビュー M-10(b): `event_id` の一意性は各表の PK でしか保証されず、UNION 全体では制約が無い。MitateDB は `text` 型なので型でも防げない)。
- **`after` = 不透明 cursor (レビュー B-3/M-10)**: `after` は event_id ではなく、`(recorded_at, plane, event_id)` を encode した**不透明トークン**とする。契約 `AuditQueryRequest.after` は `{"type": "string"}` のままなので契約変更を要さない。各 event には `cursor` フィールドを載せ (`events[]` は開放)、消費者は**最後に受け取った event の `cursor` をそのまま次の `after` に渡す**。これにより (i) サーバが cursor を位置づけるために元の行を引き直す必要がなくなり (行が消えていても位置づけが可能)、(ii) 跨表の event_id 衝突で cursor が進まなくなる無限ループが構造的に起きなくなる。**decode 不能または不正な cursor は `VALIDATION_FAILED`**。cursor は同一のフィルタ条件下でのみ有効である旨を宣言に書く。
- **`event_classes`**: フィルタである。未知の class を渡しても `VALIDATION_FAILED` にはせず**空結果**を返す (語彙検証ではない — 語彙は宣言で示す、D-7)。
- **`limit`**: 既定 100 (契約の上限は 1000)。
- **各 event**: 13 フィールド + `recorded_at` + `plane` (`"control"` | `"application"`) + `cursor`、および overflow alert 行と合体 denial 行のみ `count` (D-3 / D-4)。`events[]` 要素は契約上開放されているため additive で問題ない。**`plane` は行の出所テーブルから導出する。書き手が指定できる列にしてはならない** (レビュー m-2 — data-plane の api role は `application_audit` に任意の値を INSERT できるので、`plane` を実列にすると侵害されたプロセスが `plane="control"` の行を書いて control 面の証拠を偽造できる)。
- **取りこぼしの防止 (レビュー B-3、v1.1 の「2 秒」を撤回)**: PostgreSQL の `now()` は `transaction_timestamp()` = **トランザクション開始時刻**であって commit 時刻ではない。`recorded_at DEFAULT now()` のまま裸の 2 秒 lag を置くと、長く滞留した書き手 tx の行が cursor に追い越されて**二度と返らない**。よって:
  1. **新テーブルの `recorded_at` は `DEFAULT clock_timestamp()`** とする (INSERT 実行時刻。§6.1/§6.2 の DDL)。
  2. **監査行を書く接続に `statement_timeout` と `idle_in_transaction_session_timeout` の両方を課す** — 前者だけでは「文は速いが tx が開いたまま放置される」滞留を止められない。**この強制は `application_audit` を書く接続と `control_audit` を書く control-plane 接続の両方に掛ける** (レビュー N-3) — control 側の tx が長く滞留すれば同じ取りこぼしが UNION 越しに起きるため、片側だけでは lag の根拠が成立しない。設定は各 peer の composition root で**接続オプションとして固定する** (アプリコードの規律に委ねない)。値は実装裁量、既定は 5s / 5s。
  3. **visibility lag = `statement_timeout` + `idle_in_transaction_session_timeout` + 1s** (クロックスキュー余裕) として**導出する**。裸の数値を書かない。既定値では **11s** になる。導出値は宣言 (`visibility_lag_ms`) で公開する。
  4. 既存 `control_audit` の `recorded_at DEFAULT now()` は据え置く (in-place 編集禁止、D-9)。control-plane の状態変更 tx は短く、かつ上記 2 の timeout が control 側接続にも掛かるため、導出した lag に吸収される — この根拠を注記として残す。
- **in-memory 側にも同じ意味論を実装する**: 順序・`after`/`cursor`・visibility lag・`limit` の意味論は in-memory 実装と Postgres 実装の**両方**が持ち、同一の parity テストで固定する (D-10、レビュー M-9)。

- **壊れるシナリオ**: 順序と cursor が未定義のままだと、client がページングで取りこぼし・重複を起こし、「監査証拠を全件取得した」という主張自体が成立しなくなる。とくに `recorded_at DEFAULT now()` + 裸の lag では、ロック待ちで 3 秒滞留した書き手 tx の行が cursor に追い越され、恒久的に失われる。
- **検証方法**: **書き手 tx を人工的に lag 近くまで引き延ばして commit した行が、次ページで確かに返ること**を実 PostgreSQL テストで実測する (書き手 tx が短いテストは偶然通るのでこの欠陥を検出しない)。**application 側だけでなく control 側でも同じベクタを実測する** — control-plane の状態変更 tx (例: `rotate`) を lag 近くまで遅延させて commit し、その `control_audit` 行が次ページで返ることを確認する (レビュー N-3)。あわせて、並行書込みを続けながら cursor を辿る反復取得が全行を重複なく網羅すること、不正 cursor が `VALIDATION_FAILED` になること、両接続に実際に timeout が設定されていること (`SHOW statement_timeout` 等で実測) を確認する。

### D-7 event_class 語彙 = 契約 enum を作らず、各 peer が宣言する

契約に `event_class` の enum は**作らない**。各 peer が `capabilities().audit_query.event_classes` に自分の語彙を宣言する (declare-the-hazard。client integrator が AI agent であるという前提のもと、宣言は確実に読まれる)。

SI-14 由来の共通最小集合は本文書 §9 の表で示すが、両 peer は**既存の class 名を変えない** (`control_audit` の既存行との整合を壊さないため)。契約 1.4.0 で「これは宣言される語彙である」ことを文言化する (P4-D4 の項目 4)。

- **壊れるシナリオ**: 契約に enum を固定すると、両 peer の既存 class 名と `control_audit` に既に入っている行が「契約不適合な過去の証拠」になり、証拠の連続性が切れる。
- **検証方法**: 宣言された `event_classes` 集合が、当該 peer が実際に発火し得る class 集合と一致することを declaration-agreement 型のテスト (C-17 系) で実測する。

### D-8 conformance — C-11 と C-09 を executable にする

- **C-11**: `AuditResult` / `AuditQueryRequest` の zero-coverage (`test_c11_response_schema_conformance.py` L101-111) を解消する。control/audit credential で `audit_query` に到達する adapter 経路を新設し、実応答を閉鎖 schema へ reverse-validate する。
- **C-09**: 以下 4 点が `audit_query` 越しに観測可能であることを固定する — (i) destructive 操作と denial が観測できる、(ii) `forbidden_fields` が不在である、(iii) application credential は `FORBIDDEN` である、(iv) 削除面が存在しない。
- control surface を持たない adapter は **C-14 型の `SurfaceAbsent` 分岐**を取る (`conformance-tests/absence.py` の既存機構)。
- 既存 port の `control_audit_events()` 特権 hook (`conformance-tests/adapter.py` L1017) は**維持する** — 耐久 sink を直接読む観測路と、`audit_query` endpoint 越しの観測路は別物であり、前者は C-15 vector 4 が依存している。

- **壊れるシナリオ**: C-09/C-11 が zero-coverage のままだと、「監査は不可変・秘密なし・authority 分離」という主張が peer-local な evidence に留まり、共通契約として検証されない。
- **検証方法**: 登録済み 4 adapter それぞれが C-09/C-11 の PROVIDED か SurfaceAbsent のいずれかの分岐を実際に実行し、全 adapter が absent に落ちていないことを vacuity guard で固定する。

### D-9 migration = 新番号のみ

- r2db-api: `r2db-api/migrations/0007_application_audit.sql`
- MitateDB-api: `MitateDB-api/migrations/0005_application_audit.sql`

既存 migration の in-place 編集は行わない。各ファイル冒頭に **WHO RUNS THIS** と、既存インスタンス (r2db = VPS、MitateDB = Cloud SQL 実配備) への**互換性論証** (追加のみ・既存 GRANT 不変) を書く。雛形は §6.3。

- **壊れるシナリオ**: 既存 migration を編集すると、既に適用済みの実配備インスタンスには新列が入らず、ファイルの内容と実インスタンスの schema が静かに乖離する。
- **検証方法**: 0001..N-1 まで適用済みの状態に新 migration のみを適用して成功すること、および既存 GRANT が変化しないことを実 PostgreSQL テストで実測する。

### D-10 in-memory / Postgres のペア構造

`ApplicationAuditSink` (in-memory、故障注入可) と `PostgresApplicationAuditSink` を、control 側の既存ペア (`ControlAuditSink` ↔ `PostgresControlAuditSink`) の型に倣って新設する。

**読み手のペアも必須である (レビュー M-9)**: 書き手だけでなく**読み手**も in-memory / Postgres のペアで用意する — `InMemoryApplicationAuditStore` (in-memory の application 側と control 側を UNION して読む。append と query の両方を持つ) ↔ `auditreader` role による Postgres reader。in-memory 側に読み取りが無いと、登録済み 4 adapter のうち in-process 2 本が恒久的に `SurfaceAbsent` に落ち、C-09/C-11 の PROVIDED 分岐が実 PostgreSQL を要する HTTP 2 本でしか走らなくなる (PG クラスタ衝突による偽の赤に晒される)。D-6 の意味論 (順序・cursor・visibility lag・`limit`) は**両実装が同一の parity テストで固定する**。

**1 操作 = 最大 1 耐久行 (レビュー M-7、禁止条件)**: 1 つの利用者操作が生む耐久監査行は**最大 1 行**である (D-2 の commit 失敗時の `error` 行は、その 1 行に対する後続の別行として例外的に許される)。pre-commit で耐久記録した event については、**post-commit 側の発火を抑止する** — in-memory sink へ反映する場合も、耐久面へは二度書かない。control 面には `test_each_state_change_adds_exactly_one_audit_row` という対応する固定があるが、application 面には無いので新設する。

既存の in-memory `AuditSink` (r2db 13 フィールド、MitateDB 6 フィールド) は、**D-3 が非耐久と定めた 4 種の denial の唯一の記録先**になるため、単純撤去はできない (レビュー N-2)。耐久 sink の前段 (buffer) に統合するか併存させるかは実装裁量だが、以下 2 つは**禁止条件**である: (i) 記録先が二重になって片方が黙って落ちる構造、(ii) 1 操作が 2 行の耐久行を生む構造。

- **壊れるシナリオ**: (i) 記録先が 2 つあり片方が沈黙すると、片方だけを読むテストや運用が「記録されている」と誤認し、耐久化したはずの穴に気付けない。(ii) pre-commit hook を足したまま既存の post-commit `_event` を残すと、destructive mutate 1 回で耐久行が 2 行入り、`audit_query` の消費者 (AI エージェント) が同一操作を 2 回として数える。
- **検証方法**: in-memory と Postgres の両実装に同一の parity テストを流し、耐久 sink に故障を注入したときに in-memory 側だけが成功して操作が通る経路が存在しないことを実測する。destructive mutate 1 回で `application_audit` の行数がちょうど +1 になることを実測する。

### D-11 スコープ外 (本フェーズで扱わない)

保持期間・剪定 (externally governed。runbook に操作手順のみ記す)、外部 SIEM 転送、business audit、`control_audit` の改名/統合、既存 control-plane 経路の変更 (`audit_query` 追加を除く)。詳細は §10。

- **壊れるシナリオ**: 保持期間や SIEM 転送を本フェーズに取り込むと、耐久化そのものの検証が終わらないまま範囲が発散し、fail-closed の実測という本フェーズの核心が後回しになる。
- **検証方法**: 本設計文書の §10 と作業指示書の WP 完了条件が一致していることを、レビュー時に突合する。

---

## 4. 却下した代替案

| 記号 | 案 | 却下理由 |
|---|---|---|
| R-A | 契約に `event_class` enum を新設する | 両 peer の既存 class 名と `control_audit` の既存行を破る。共通語彙は宣言で足りる (D-7) |
| R-B | `AuditResult` の**封筒**に `next_cursor` を追加する | 封筒 (`AuditResult`) は閉鎖 schema なので、キー追加は契約 1.4.0 が必須になる。**次ページ cursor は封筒ではなく各 event に載せる** — `events[]` の要素は契約上開放されているため、`cursor` フィールドの追加は additive で契約変更を要さない。消費者は最後の event の `cursor` を次の `after` に渡す (D-6) |
| R-C | `control_audit` テーブルに application-plane 行を同居させる | テーブル名が偽になる。加えて data-plane の api role に `control_audit` INSERT を与えることになり、control-plane の権限境界 (`security/CONTROL_MAPPING.md` SI-00 行 (b) の evidence) を曖昧にする |
| R-D | 非同期 (commit 後) の耐久書込みのみとする | fail-closed 類で契約違反 (sink 失敗が操作を止めない)。N-1 の窓が「記録なし・データ commit 済み」= **過少記録側**に倒れる |
| R-E | data-plane app で `audit_query` を提供する | control/audit credential store を data-plane に持ち込むことになり SI-00 の分離が崩れる (§1.5) |
| R-F | 全 event を同期耐久化する | query 成功ごとの INSERT は、契約が明示的に許す buffer 緩和を捨てることになり、コストに見合わない (SI-14 の "Does not require" が「全 successful read を無制限の粒度で記録すること」を明示的に不要としている) |

---

## 5. 依頼者裁定 (確定)

以下 5 件は **2026-09-02 に依頼者が直接回答して確定した**。判断根拠は §2 末尾の設計原則である。**依頼者は後日の見直しを妨げないと明言している** — 再検討する場合は本節の「却下した側とその理由」を出発点にすること。

### P4-D1 監査行の置き場所 = platform DB の `application_audit` (旧 U-1(a))

**確定**: D-1 のとおり platform DB の registry schema に置く。cross-database tx が無い制約を「commit 前記録 + outcome 意味論」(P4-D2) で受け止め、deprovision 後も証拠が残り、`audit_query` が単一 DB で完結する。厳密な同一 tx は諦める。

**却下した側 (app DB 内の platform 所有 schema) とその理由**: 同一 tx で厳密に書ける利点はあるが、(i) deprovision (`DROP DATABASE`) 時の証拠喪失に別途の退避手順が要る、(ii) `audit_query` が N database fan-out になり、fan-out 先の 1 つが応答しないとき「全件を返した」と言えなくなる、(iii) D-6 の全順序が複数 DB を跨いでクロックスキューの影響を直接受ける (単一 DB なら受けない) ため visibility lag の議論が N 倍複雑になる、(iv) developer role が `public` schema owner である環境で監査テーブルを守れることの実証が要る (`_mdb_schema_revision` (`0003_provision_application.sql` L137-142) の「アンダースコア始まり名 + runtime role 未 GRANT」が構造的先例だが、DROP SCHEMA CASCADE のロールまたぎ検証テストはどちらの peer にも存在しない)。

### P4-D2 N-1 の記録方式 = commit 前 1 行 + outcome 意味論 + error 行規則 (旧 U-2(a))

**確定**: D-2 のとおり。commit 前に 1 行を耐久記録し、`outcome="allow"` は「認可され実行に投入された」を意味する。データ commit がプロセス生存下で失敗した場合は同一 `request_id` の `outcome="error"` (`reason_code="commit_failed"`) 行を耐久記録する (これも fail-closed 類)。

**識別規則の限界を併せて確定する (N-1 の但し書き)**: `allow` 行**のみ**が存在するときは「成立した」か「記録後にプロセスが消失した」かのいずれかであり、**監査面だけからは区別できない**。`error` 行が覆うのはプロセス生存下のクリーンな commit 失敗のみである。調査者は `allow` 単独行をデータ面の実状態と突き合わせて判定する。この限界は宣言 (`outcome_note`) と CONTROL_MAPPING に明記する。

**却下した側 (attempted 行 + committed 行の 2 行方式) とその理由**: 行数が倍増する。後行 (committed) は commit の**後**に書くため fail-closed にできず (止めるべき操作がもう終わっている)、必然的にバッファ類となって D-4 の overflow で捨てられ得る — 「commit の成否まで証拠に残る」という利点が overflow を考慮すると弱まる。加えて後行の書込み失敗が「未確定」状態の記録を残し、その解釈規則を別途定める必要がある。採用側でも `error` 行規則により commit 失敗は耐久記録されるため、両案の差は「成功を明示するか、失敗を明示するか」に縮む。

### P4-D3 denial の耐久記録 = 合体 (coalescing) 方式 (旧 U-3(c'))

**確定**: D-3 のとおり。耐久対象の denial を範囲限定した上で `(application_id, actor_id または "unknown", operation, reason_code)` を鍵に窓 W=60s で合体し、**プロセスあたり窓あたり 1 行** (`count` 列に発生回数) に有界化する。data-plane に新しい pre-auth 拒否経路は追加しない。

**前提事実 (監督実測)**: **両 peer とも data-plane に pre-auth rate limit は存在しない** — r2db の rate limit は post-auth の credential 単位のみで (`service.py` L345-350 `_acquire_rate`)、無効 credential は `_authenticate` (`http.py` L268-269 → `service.py` L106-115) で即座に raise され window に触れない。MitateDB は data-plane の `requests_per_minute` 自体が未実装・未宣言 (`cell.py` L1122-1134)。一方 control-plane には pre-auth の global window が両 peer に存在する (r2db `control_plane.py` L1192-1252 + `control_http.py` L44-70、MitateDB `control_plane.py` L951-974)。

**却下した側とその理由**:
- **data-plane への global pre-auth window の追加**: 未認証の試行もすべて証拠に残るが、global window が**正規テナントへの巻き添え DoS 面**を新設する。data-plane は control-plane と違って multi-tenant であり呼び手は運用者ではないため、これは SI-00 の "Application A compromise ≠ Application B compromise" の**可用性側の直接的な後退**である (control-plane に同じ窓があることは先例にならない)。設計原則 3「制約・制限で回避しない」にも反する。
- **control-plane と同じ線引き (未認証拒否は非耐久)**: 「存在しない secret での試行」が耐久証拠に一切残らない。加えて data-plane にはこの線引きが前提とする pre-auth window 自体が無いため、同じ線引きだと言えない。
- **「既知 credential に解決する拒否のみ耐久記録」**: 漏洩済み secret 1 本の連打がすべて fail-closed 類に落ちるため、有界なのは拒否の*種類*であって*行数*ではなく、global window 案と同じ無界性を持つ。

### P4-D4 契約 1.4.0 候補 8 件を本フェーズで一括出荷する (旧 U-4(a))

**確定**: 下記 8 件を **1.4.0 として本フェーズ内で一括出荷する**。従属判断8 (束 4 件を一括で 1.3.0) の前例に倣い、**従属判断 9** として `spec/CCR_DISPOSITION.md` に house style で記録する (各項目に再検討条件を付す)。実装と宣言は当該 peer が 1.4.0 挙動を出荷する WP の同一コミットで揃える (契約 `versioning.version_binding`)。

1. `after` の意味論 — **不透明 cursor** (`recorded_at`/`plane`/`event_id` を encode) とし、各 event の `cursor` フィールドで受け渡す。不正 cursor は `VALIDATION_FAILED`
2. 順序 (`recorded_at`, `plane`, `event_id` の全順序)
3. `plane` フィールドの追加 (`events[]` は開放済みなので additive)
4. 「`event_class` は宣言される語彙である」旨の文言化
5. audit role の `audit_query` 許可と `control_plane.authority` の 3 endpoint 限定記述との文言整合 (§1.6)
6. `audit_events` 予約名の文書化 (台帳の既存項目)
7. **`audit_query` の endpoint 分類の整理** — `endpoints` から `control_endpoints` へ移し、パスを `/control/v1/audit/query` とする。移行期として `/v1/audit/query` を **1 minor の間 alias** として残す (D-5 が実装側で既に両パスを両建てするため、契約側の分類が実装に追いつく形)
8. **`audit_requests_per_minute` limit class の新設** — `audit_query` を control 面の global window から分離する。これにより D-5 の「監査ポーリングが break-glass を締め出す」相互作用 (M-8) が構造的に解消される

**手続き上の注意**: 契約に触れる変更は依頼者確認済みだが、**契約ファイルを変更するコミットの直前に監督が再度明示する**。

**却下した側 (次の束まで繰延べ) とその理由**: 設計原則 1「今やれることは今のうちに」に反する。加えて項目 7 を繰延べると「契約上は application endpoint なのに control ホストにある」という説明しづらい状態が 1 minor 以上続き、項目 8 を繰延べると監査ポーリングと break-glass の相互作用が runbook の注意書きだけで運用されることになる (原則 3 に抵触)。

### P4-D5 通常 data-operation 成功 event は**両 peer で記録する** (旧 U-5(b) の「両方記録する」)

**確定**: r2db は現状どおり query 成功等を buffer 経由で耐久記録し (`service.py` L222)、**MitateDB も query/insert/update の成功を記録する emit サイトを追加する**。両 peer とも bounded buffer 経由で耐久化する (D-4)。

**監督推奨からの変更**: 監督の当初推奨は「非対称を許容する」であった。依頼者の設計原則 (先送りしない / シンプルに / 制約で回避しない / **peer 非対称を目先の最小変更で残さない**) により (b) へ変更した。

**理由**:
- **AI エージェント消費者が両 peer から同じ event stream を得る** — 消費者側に peer 別の分岐を持ち込まない。これは本リポジトリの前提 (client integrator は AI エージェント) と整合する。
- **overflow alert の性質を両 peer で実挙動から検証できる** — 非対称を残すと MitateDB には buffer に載る event が実質存在せず、§9.2 の性質 3 が buffer 実装の単体テストでしか固定できない (実挙動の証拠にならない)。

**代償として引き受けるもの**: MitateDB 側の emit コストと buffer 圧が増える。visibility lag 下での `audit_query` 全件取得において通常 read が証拠を希釈する。SI-14 の "Does not require" は全 successful read の記録を**不要**としているだけで**禁じてはいない**ため、契約適合性の問題は生じない。

**却下した側とその理由**: 「非対称を許容する」は上記 2 点を失う。「両方記録しない」は r2db の既存挙動と既存テストを後退させる方向であり、証拠の量を減らす変更を「揃える」ためだけに行うことになる。

---

## 6. テーブル・GRANT・migration の具体形

### 6.1 r2db-api

**テーブル** (`r2dbsvc_registry.application_audit`。既存 `control_audit` (`0006_control_plane_http.sql` L431-445) と同一の 13 列 + `recorded_at`、加えて `audit_seq` と `count`):

```sql
CREATE TABLE IF NOT EXISTS r2dbsvc_registry.application_audit (
    audit_seq      bigserial UNIQUE,
    event_id       uuid PRIMARY KEY,
    event_class    text NOT NULL,
    occurred_at    timestamptz NOT NULL,
    request_id     text NOT NULL,
    application_id text,
    actor_type     text NOT NULL,
    actor_id       text,
    role           text,
    operation      text NOT NULL,
    target_kind    text,
    outcome        text NOT NULL,
    reason_code    text,
    target_id      text,
    count          integer,
    recorded_at    timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT application_audit_len_event_class    CHECK (length(event_class)    <= 64),
    CONSTRAINT application_audit_len_request_id     CHECK (length(request_id)     <= 256),
    CONSTRAINT application_audit_len_application_id CHECK (length(application_id) <= 256),
    CONSTRAINT application_audit_len_actor_type     CHECK (length(actor_type)     <= 64),
    CONSTRAINT application_audit_len_actor_id       CHECK (length(actor_id)       <= 256),
    CONSTRAINT application_audit_len_role           CHECK (length(role)           <= 64),
    CONSTRAINT application_audit_len_operation      CHECK (length(operation)      <= 64),
    CONSTRAINT application_audit_len_target_kind    CHECK (length(target_kind)    <= 64),
    CONSTRAINT application_audit_len_outcome        CHECK (length(outcome)        <= 32),
    CONSTRAINT application_audit_len_reason_code    CHECK (length(reason_code)    <= 128),
    CONSTRAINT application_audit_len_target_id      CHECK (length(target_id)      <= 256),
    CONSTRAINT application_audit_count_positive     CHECK (count IS NULL OR count > 0)
);
```

**長さ制約 (レビュー M-5)**: 全 text 列に `CHECK (length(col) <= N)` を課す。これは D-1 が新設する「data-plane role が platform DB に書ける」露出に対する 1 行サイズの上限であり、有界化の第 1 段である (第 2 段 = 1 操作 1 行 + 合体 + buffer、第 3 段 = 容量監視の runbook 化)。上限値は語彙が有限な列ほど短くしてよい (上記は目安、実装裁量で調整可)。**`recorded_at` の既定値は `clock_timestamp()`** — `now()` (= `transaction_timestamp()`) ではない (D-6 の取りこぼし防止)。

`count` は本フェーズで新設する 14 番目の列であり、「この行が代表する発生回数 (NULL = 1)」を意味する。契約 `audit.fields_note` が `audit.fields` を「additive な語彙であって必須の列集合ではない」と明記しているため、この追加は契約適合の範囲にある。設定されるのは **D-4 の buffer overflow alert 行**と **D-3 の合体 denial 行**の 2 用途のみで、他の全 event では NULL である。既存 `control_audit` には**追加しない** (control-plane に buffer 経路も合体も無く、MitateDB の 13 フィールド完全一致テストを緑のまま保つため)。

`event_id` はアプリ側 `uuid.uuid4()` 生成を維持する (`control_audit` と同じ理由: 再送時にサーバ生成 id が 2 つ割り当たることを防ぐ、0006 L414-419)。NULL 許容は既存 `AuditEvent` dataclass (`audit.py` L14-41) の型に一対一で従う。`audit_seq` は既存 `control_audit` には無い列であり、この非対称は `audit_query` の UNION 順序が `(recorded_at, plane, event_id)` に依るため実害を持たない (実装裁量: `audit_seq` は単一テーブル内の挿入順デバッグ用)。

**`target_id` は当面すべて NULL になる (レビュー m-5)**: application-plane の既存 emit 経路は `target_id` を渡さない (`audit.py` L52 の `AuditSink.append` が 12 位置引数で `AuditEvent` を構築し、`service.py` L354-355 の `_event` も引数を持たない)。契約 `fields_note` が `target_id` を OPTIONAL としているため不適合ではないが、「列だけあって常に空」の理由が後から読めないので明記する。本フェーズでは **13 列 emitter の新設にあわせて `target_id` を渡せる形にする**ことを実装要件とし (値の充足は emit サイトごとに自然に決まるものだけでよい)、値を持たない emit サイトは NULL のままとする。

**書き手接続の設定 (D-6 / レビュー N-3)**: 監査行を書く platform 接続には `statement_timeout` (既定 5s) と `idle_in_transaction_session_timeout` (既定 5s) の**両方**を composition root で接続オプションとして固定する。これは `application_audit` を書く data-plane の接続だけでなく、**`control_audit` を書く control-plane の接続にも同じく掛ける** — 片側だけでは visibility lag の根拠が成立しない。visibility lag はこの 2 値の和 + 1s として導出する (既定値では 11s)。

**role と GRANT の骨子**:

```sql
-- 書き手: data-plane プロセスの既存 role。INSERT のみ (append-only by grant)。
GRANT INSERT ON r2dbsvc_registry.application_audit TO r2dbsvc_api;
GRANT USAGE ON SEQUENCE r2dbsvc_registry.application_audit_audit_seq_seq TO r2dbsvc_api;

-- 読み手: 新設の SELECT 専用 role。control 面と application 面の両方を読む。
CREATE ROLE r2dbsvc_auditreader LOGIN PASSWORD NULL
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 5;  -- 冪等 DO ブロック内
GRANT CONNECT ON DATABASE r2dbsvc_platform TO r2dbsvc_auditreader;
GRANT USAGE ON SCHEMA r2dbsvc_registry TO r2dbsvc_auditreader;
GRANT SELECT ON r2dbsvc_registry.control_audit      TO r2dbsvc_auditreader;
GRANT SELECT ON r2dbsvc_registry.application_audit  TO r2dbsvc_auditreader;

-- 帯域外 CLI 用に明示 INSERT (owner 特権に暗黙依存しない。0006 L515 と同じ理由)。
GRANT INSERT ON r2dbsvc_registry.application_audit TO r2dbsvc_control;
```

`r2dbsvc_api` に UPDATE/DELETE/SELECT を与えない — data-plane プロセスは監査行を書けるが、読み出すことも書き換えることも消すこともできない。INSERT を新設したことによる容量側の含意は上記の長さ制約と D-1 の 3 段構えで有界化し、platform DB の容量監視を runbook 項目とする (§9.3)。`r2dbsvc_controlplane` (control HTTP プロセス role) には `application_audit` への GRANT を**一切与えない** — 読み取りは別 DSN の `r2dbsvc_auditreader` が担う (D-5)。パスワードは環境変数名 (`R2DBSVC_AUDITREADER_PASSWORD`) と `psql -v` 経由で渡し、SQL ファイルに実値を書かない。

**環境変数** (実装裁量、composition root):
`R2DB_AUDIT_DSN` (control HTTP app が任意で保持。未設定なら `audit_query` は `unavailable` 宣言のまま)。

### 6.2 MitateDB-api

**テーブル** (`mitatedb_registry.application_audit`。既存 `control_audit` (`0002_registry_and_functions.sql` L200-215) と同形):

```sql
CREATE TABLE IF NOT EXISTS mitatedb_registry.application_audit (
    audit_seq      bigserial UNIQUE,
    event_id       text PRIMARY KEY,
    event_class    text NOT NULL,
    occurred_at    timestamptz NOT NULL,
    request_id     text,
    application_id text,
    actor_type     text,
    actor_id       text,
    role           text,
    operation      text NOT NULL,
    target_kind    text,
    outcome        text NOT NULL,
    reason_code    text,
    target_id      text,
    count          integer,
    recorded_at    timestamptz NOT NULL DEFAULT clock_timestamp(),

    -- 長さ制約は §6.1 と同一の設計 (列名・上限値をそのまま踏襲)
    CONSTRAINT application_audit_len_event_class CHECK (length(event_class) <= 64),
    -- ... 以下 §6.1 と同じ列について同じ形で ...
    CONSTRAINT application_audit_count_positive  CHECK (count IS NULL OR count > 0)
);

REVOKE ALL ON mitatedb_registry.application_audit FROM PUBLIC;
```

`event_id` の型は既存 `control_audit` に合わせて `text` とする (peer 間で型が違うのは既存の非対称であり、本フェーズで揃えない)。`count` は §6.1 と同じ 14 番目の列である。

**書き手接続の設定 (D-6 / レビュー N-3)**: §6.1 と同一の要件が MitateDB にも掛かる — 監査行を書く platform 接続に `statement_timeout` (既定 5s) と `idle_in_transaction_session_timeout` (既定 5s) の**両方**を composition root で接続オプションとして固定し、これを `application_audit` を書く data-plane 接続と `control_audit` を書く control-plane 接続の**両方**に適用する。visibility lag は 2 値の和 + 1s (既定 11s)。**この peer は Cloud SQL 実配備があるため**、設定は migration ではなくアプリケーション側の接続オプションで行い (実インスタンスの `ALTER ROLE`/`ALTER DATABASE` に依存しない)、`docs/cloud-run-cloud-sql.md` に実測確認手順を書く (§9.3)。

**6 フィールド sink を通さない (監督裁定 R6)**: MitateDB の application-plane `AuditSink` は 6 フィールドで、`_SAFE_EVENTS`/`_SAFE_DETAILS` の許可語彙外を `"unclassified"`/`"unspecified"` へ**黙って丸める** (`audit.py` L24-37)。丸めた結果を耐久記録すると、`event_class` 宣言 (D-7) と実際に記録される値が食い違う。したがって**耐久経路はこの 6 フィールド sink を通さない** — emit サイト (`cell.py` L336-339 / L389-392 / L546-549 / L757-765、`auth.py` L355-422 ほか) で、D-7 の宣言語彙の定数を直接使う **13 列 (+`count`) emitter を新設**する。既存 6 フィールド sink を残置するか撤去するかは実装裁量だが、D-10 の禁止条件 (記録先が二重になって片方が黙って落ちる構造を作らない) と、D-3 の非耐久 4 種の唯一の記録先であるという役割 (§3 D-10) の下で判断すること。

**新設する emit サイト (P4-D5)**: MitateDB は現状 query / insert / update の成功を記録しない (`cell.py` の read 経路 L416 / L1022 に `__record` 呼び出しが無く、insert/update も同様)。依頼者裁定 P4-D5 により、これらに **13 列 emitter への emit サイトを新設する** — 両 peer が同じ event stream を出し、overflow alert の性質を両 peer で実挙動から検証できるようにするためである。バッファ類として bounded buffer に積む (§7.3)。

**role と GRANT の骨子**:

```sql
GRANT INSERT ON mitatedb_registry.application_audit TO mitatedbsvc_api;
GRANT USAGE ON SEQUENCE mitatedb_registry.application_audit_audit_seq_seq TO mitatedbsvc_api;

-- 新設 reader role (0002 の CREATE ROLE 冪等 DO ブロックと同じ形)
CREATE ROLE mitatedbsvc_auditreader LOGIN PASSWORD NULL
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 5;
GRANT CONNECT ON DATABASE mitatedb_platform TO mitatedbsvc_auditreader;
GRANT USAGE ON SCHEMA mitatedb_registry TO mitatedbsvc_auditreader;
GRANT SELECT ON mitatedb_registry.control_audit     TO mitatedbsvc_auditreader;
GRANT SELECT ON mitatedb_registry.application_audit TO mitatedbsvc_auditreader;
```

`mitatedbsvc_api` の既存 GRANT (`applications`/`credentials` の SELECT、0002 L253-254) は**変更しない**。`mitatedbsvc_controlplane` には `application_audit` への GRANT を与えない。

**Cloud SQL 固有の注意**: 新設 role は必ずこの migration SQL の `CREATE ROLE` で作る。Cloud SQL の Users API/Console で作ると `cloudsqlsuperuser` メンバとなり `REVOKE CONNECT ... FROM PUBLIC` を迂回する (`MitateDB-api/docs/cloud-run-cloud-sql.md` §3.3 の既存ルール)。`mitatedb_registry.assert_role_has_no_memberships` (0002) の fail-closed backstop を新 role にも適用する (実装裁量: migration 末尾で assert する)。

**環境変数**: `MITATEDB_AUDIT_DSN` (同上、任意)。

### 6.3 migration 冒頭の互換性論証 — 雛形

両 peer の新 migration の冒頭に、既存ファイルの体裁 (`0006_control_plane_http.sql` L1-20、`0002_registry_and_functions.sql` L1-18) に倣って以下を書く。

```
-- <peer> PostgreSQL provisioning -- 000N: application-plane durable audit
-- sink (phase 4)
--
-- WHO RUNS THIS: <operator>, connected to the `<platform database>` database
-- (created by 0001) AS the `<schema owner role>` role -- the same
-- role/connection 000M already runs as. Run once, after 000M:
--
--   psql "$<OWNER_DSN_ENV_NAME>" -v auditreader_password="$<READER_PASSWORD_ENV_NAME>" \
--     -f 000N_application_audit.sql
--
-- `<READER_PASSWORD_ENV_NAME>` is an environment-variable *name*; see
-- <peer>/docs/<runbook>. This file never contains a real credential.
--
-- WHAT THIS FILE DOES (design docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md
-- D-1/D-9): creates `<schema>.application_audit`, grants INSERT-only on it to
-- the data-plane process role, and creates a SELECT-only reader role for the
-- audit_query surface.
--
-- COMPATIBILITY WITH ALREADY-DEPLOYED INSTANCES (D-9; the "no deployed
-- instance" premise expired for this peer on <date>, see
-- docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md):
--   * ADDITIVE ONLY. This file creates one new table, one new role, and new
--     GRANTs. It ALTERs no existing table, DROPs nothing, and REVOKEs nothing.
--   * No existing GRANT changes. `<controlplane role>`'s INSERT-only posture on
--     `control_audit` is untouched; `<api role>` keeps its existing SELECT
--     grants on `applications`/`credentials` and gains INSERT on the new table
--     only.
--   * Idempotent: `CREATE TABLE IF NOT EXISTS`, `CREATE ROLE` guarded by a
--     `pg_roles` existence check, `GRANT` statements are idempotent by nature.
--     Re-running this file against an instance that already has it applied is
--     a no-op.
--   * Rollback: dropping the new table and role restores the prior state
--     exactly; no data written by earlier migrations depends on either.
```

各 peer の実際の role 名・DSN 環境変数名・runbook パスを埋めること。**互換性論証は「追加のみ」という主張ではなく、追加のみであることの逐条確認**として書く (どの既存オブジェクトに触れていないかを名指しする)。

---

## 7. 実行時の流れ

以下は各 peer の**既存関数名で位置を示す**。関数の新設・改修の具体形は作業指示書の管轄である。

### 7.1 fail-closed 類の pre-commit 経路 (D-2)

**r2db-api** — destructive / privilege-sensitive の data-plane 操作:

```
DataService._mutate_outcome (service.py L245-261)
  → cell.transact(...) を呼ぶ (現状 L256)
     ├ backend が tx を開き operation を実行 (StorageBackend.transact, backend.py L64-93)
     ├ [新] pre-commit hook: PostgresApplicationAuditSink.append(...) を
     │      platform 接続 (r2dbsvc_api) で INSERT + commit
     │      (fail-closed 行は単独の tx で commit する。buffer 行を相乗りさせない — D-4/M-1)
     │      ├ 成功 → backend が data tx を commit
     │      │        ├ commit 成功 → 完了
     │      │        └ commit 失敗 → 同一 request_id で outcome="error"
     │      │                        (reason_code="commit_failed") を耐久 INSERT。
     │      │                        これも fail-closed 類 — 書けなければ 503 (D-2)
     │      └ 失敗 → backend が data tx を rollback → SERVICE_UNAVAILABLE
     └ 戻り
  → 現状 L257 の _event(...) は、この経路では耐久面へ二度書かない (D-10: 1 操作 = 最大 1 行)。
    in-memory sink へ反映する場合も、post-commit の耐久発火は抑止する
```

`schema` 経路 (`DataService._schema` service.py L263-282 → `apply_schema` backend.py L64-93) も同型である。`StorageBackend` Protocol (backend.py L39-100) に pre-commit hook を露出することが本フェーズの構造変更の核心であり、in-memory の `ApplicationCell` (structured.py) も同じ hook を擬似 tx で実装して parity テストの対象とする (D-10)。

**MitateDB-api** — バッチ (N-1 の本体):

```
cell.transact (cell.py L669-828)
  ├ pending_audit に callable を積む (現状 L757-765)
  ├ [新] self._backend.commit() の呼び出し (現状 L766) の直前で
  │      pending_audit を耐久 sink へ flush + commit
  │      ├ 成功 → self._backend.commit()
  │      └ 失敗 → self._backend.rollback() (現状 L821-825 の経路) → SERVICE_UNAVAILABLE
  └ 現状 L826-827 の「commit 後に record()」は、耐久記録済みの in-memory 反映のみになる
```

```
  ├ (バッチも同様に) commit 失敗時は outcome="error" の耐久行を書く (D-2)
  └ 現状 L826-827 の post-commit record は耐久面へ二度書かない (D-10)
```

単発操作も同型: `cell.create_collection` (L336-339) / `cell.add_field` (L389-392) / `cell.delete` (L546-549) は、それぞれ `backend_postgres.py` の `create_collection` (L402-422、commit は L422) / `add_field` (L424-444、commit は L444) / `delete` (L669-685、commit は L684) が**既に commit してから戻る**ため、backend 側に commit 前の hook を設けなければ post-commit 窓が残る。

**commit が try の外にある問題 (レビュー M-6)**: この 3 箇所の `commit()` は `try` の**外** (`else:` 節) で呼ばれており、**commit 自体が raise した場合は分類済みの `FoundationError` にならずに素通りする** — つまり現状の構造のままでは「監査 `allow` のあと、対応する耐久 `error` 行が出ない」経路が実在する。hook 化にあたっては、**`commit()` を try の内側へ移し、その失敗を D-2 の `error` 行発火に接続する**ことを実装要件とする。これがないと D-2 の未 commit 識別規則が成立せず、C-09 のベクタ (存在方向の検査) は幻の行も緑にしてしまう。

### 7.2 denial 経路 (D-3)

denial には状態変更が無いため、独立 tx で INSERT し、失敗したら当該応答を `SERVICE_UNAVAILABLE` にする。既存の `PostgresControlAuditSink.append(work=None)` (`credential_store.py` L1116-1123) が control 面で採っているのと同じ形である。

**まず D-3 の範囲判定を行う** — `VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND` は**非耐久**であり、耐久経路にも buffer にも入れない (既存の in-memory sink にのみ残る、レビュー N-2)。両 peer とも `except FoundationError` を丸ごと denial event に変換しているため (r2db `service.py` L219-225 / L258-260 / L280-281 / L295-296)、**この分岐を except 節の中に明示的に置く**必要がある。

次に **D-3 の合体**を適用する: 合体キーが窓 W 内で既出なら計数のみ (同期 INSERT なし)、初出なら同期 INSERT + commit、失敗時は `SERVICE_UNAVAILABLE`。窓終了時に合体行を `count` つきで flush する。

- r2db-api: `service.py` L115 (authentication_denial、`_audit.append` 直呼び) / L225 / L260 / L281 / L296、および `deny_unsupported` (L299-318、L317 で発火)。**L115 の経路は `_slot`/`_acquire_rate` (L321-350) を一切通らない** — つまり rate window の外側にあり、無効 secret の連打が何のカウンタにも当たらないまま監査面に到達する。合体 (D-3) はここに掛ける。なお `deny_unsupported` は「レート/同時実行の課金を先に消費させる」設計 (L299-305 のコメント) だが、`CAPABILITY_UNSUPPORTED` 自体はバッファ類である。
- MitateDB-api: `auth.py` L355-422 (`authorization_state_failure` / `authentication_denied`) と `cell.py` L991-993 (`authorization_denied`)。data-plane に rate window が無い点は r2db L115 と同じ。

未認証 `authentication_denial` の扱いは **P4-D3 (合体方式)** で確定している — data-plane に pre-auth window は追加せず、合体で流量を有界化する。

### 7.3 buffer 経路 (D-4)

通常の data-operation event は bounded buffer へ積む:

振り分けは **D-2 の規範的規則**による — `event_class` では判定しない。判定点は `DESTRUCTIVE_CONFIRMATION_V1` の確認 choke (両 peer の `_validate_delete_confirmation` 相当) であり、両 peer で同じ関数がこの役目を負うことをテストで固定する (§9.2)。

buffer に載るのは**通常の data-operation 成功 event のみ**である (D-3 の非耐久 4 種はここにも来ない)。

- r2db-api: `service.py` L222 (`query` allow) / L293 (`catalog` allow) はバッファ類。L257 (`mutate` allow) は**確認 choke を通ったかどうかで分岐する** — delete を含むバッチは §7.1 の pre-commit 経路、含まないバッチはバッファ類。
- MitateDB-api: **P4-D5 により query / insert / update の成功を記録する emit サイトを新設する** (現状 `cell.py` の read 経路 L416 / L1022 および insert/update 経路には `__record` 呼び出しが無い)。これらはバッファ類として buffer に積む。delete と schema 変更は従来どおり §7.1 の pre-commit 経路。

flush 契機は (i) 定期、(ii) 閾値、の 2 つ。**常に別 tx・別接続**で行い、fail-closed 書込みの tx には相乗りさせない (D-4 / レビュー M-1)。fail-closed 行の commit 完了後に起動してよいが、その場合も tx は分ける。バッチ INSERT で書く。

### 7.4 overflow alert 経路 (D-4)

```
buffer が満杯 & 新 event 到着
  ├ 最古の event を捨てて drop カウンタを +1
  ├ logging.error(<固定メッセージ>) を発火 (両 peer とも logging 機構が現存しないため新規導入)
  └ alert を pending にする
       次の flush で security_control_failure event を耐久 INSERT
       (operation="audit_buffer", target_kind="audit_sink",
        reason_code="audit_buffer_overflow", count=<累積 drop 数>)
       ├ 成功 → drop カウンタと pending をクリア (log は状態変化として 1 回出す)
       └ 失敗 → pending を維持したままカウンタは累積を続け、
                 指数バックオフ (上限 60s) で再試行 (sticky)。
                 logging.error の再発火は最初の 1 回とバックオフ間隔ごとに抑制する
```

**alert 行の INSERT 自体が失敗した場合の扱い (監督裁定 R4、確定)**: この失敗には「fail-closed で止めるべき利用者操作」が対応しないため、**利用者操作は一切ブロックしない**。代わりに (i) `logging.error` を必ず発火させ、(ii) drop カウンタは累積を続け、(iii) alert は耐久記録に成功するまで **pending のまま再試行する (sticky)**。これにより、alert が沈黙したまま消えることも、alert 失敗が可用性を落とすこともない。`count` は「その alert 行が代表する累積の欠落数」であり、成功時にのみリセットされる。

**再試行は指数バックオフを伴う (レビュー m-4)**: alert 行の INSERT が**決定的に**失敗する種類の失敗 (長さ制約違反、`count` の範囲超過、列不整合) を踏むと、等間隔の sticky 再試行は毎 flush ごとに `logging.error` を吐き、それ自体がログ基盤への DoS になって本物のインシデントを埋める (D-3 が懸念する証拠希釈がログ側で起きる)。よって再試行間隔は指数バックオフ (上限 60s) とし、`logging.error` の再発火は**最初の 1 回と、以後はバックオフ間隔ごと**、および**状態が変化したとき**に限る。決定的失敗と一時的失敗を区別する必要はないが、無制限の等間隔再試行は禁じる。

### 7.5 audit_query 経路 (D-5, D-6)

**data-plane ホスト** (**不変**、監督裁定 R1(ii)):

- r2db-api: `http.py` L397-419 `post_audit_query` — `_authenticate` (L411) の後に `deny_unsupported` 経由で `CAPABILITY_UNSUPPORTED` を返す挙動をそのまま維持する。
- MitateDB-api: `http.py` L781-807 `post_audit_query` — 同様に維持 (現状 L789 で `CapabilityError`)。
- data-plane の `/v1/capabilities` も `audit_query: {"status": "unavailable"}` のまま。**このホストでは実際に提供していない**ので、宣言は真である。

**control ホスト** (実体。2 パスを両建てする):

```
control HTTP app (_ROUTES: r2db control_http.py L337-347 / MitateDB control_http.py L327-338)
  → [新] POST /control/v1/audit/query          ← 配備上の正解の経路
     [新] POST /v1/audit/query                 ← 契約現行分類への追随 (同一ハンドラの alias)
     ├ global pre-auth window を消費 (既存 _check_rate。M-8 のリスクは runbook へ)
     ├ control/audit credential を認証 (既存 ControlPlaneService の認証経路)
     │  application credential は control_credentials に verifier が存在しないため
     │  認証段階で落ちる → FORBIDDEN (契約 semantics「Application credentials are denied」)
     ├ 認可: role="audit" は _AUDIT_ROLE_ALLOWED_OPERATIONS
     │        (r2db control_plane.py L182 / MitateDB control_plane.py L80) に
     │        audit_query を追加した集合で許可
     ├ AUDIT DSN 未設定 → CAPABILITY_UNSUPPORTED (404 にしない。M-4)
     ├ AUDIT DSN (auditreader role) で control_audit ∪ application_audit を
     │  SELECT — 順序 (recorded_at, plane, event_id)、after は不透明 cursor (exclusive)、
     │  recorded_at < now() - <導出した visibility lag> の行のみ
     └ AuditResult を返す (events[] の各要素 = 13 フィールド + recorded_at + plane + cursor、
        alert 行と合体 denial 行のみ count を伴う)
```

宣言は `control_capabilities` 文書の `capabilities.audit_query` に載せる (D-5)。AUDIT DSN が未設定なら宣言は `{"status": "unavailable"}` のままとするが、**ルートは常に登録し**、認証後に `CAPABILITY_UNSUPPORTED` を返す。宣言と実挙動を一致させること (declaration = real behavior の既存規律)。

読み取り経路は既存の `ops.py cmd_audit_report` (r2db L747-816、`R2DB_CONTROL_DSN` で直接 SELECT) と**別物**であり、そちらは変更しない。

**可用性の共有 (レビュー m-6)**: reader は platform DB への別 DSN であり、`audit_query` の可用性は platform DB と共有される。platform DB が落ちれば data-plane は認証段階で全面停止し、同時に `audit_query` も読めなくなる — **証拠が最も必要な瞬間に読めない**。この状況での独立した読み取り路は帯域外 CLI (`cmd_audit_report` 相当) のみであり、その旨を runbook に書く (§9.3 / §10)。

---

## 8. conformance への影響

### 8.1 C-09 の executable 化

`conformance-tests/CONDITIONS.md` L17 の C-09 は現在「not yet executable (common suite) — peer-local evidence only」である。executable 化に要する検証ベクタ:

1. **観測可能性**: destructive 操作 (delete / drop_entity 系) と D-3 の耐久対象 denial を実行した後、control/audit credential での `audit_query` にそれらが現れる。**ベクタ 1 の対象は fail-closed 類に限定する** (レビュー M-11) — fail-closed 類は buffer を経由しないので `flush_audit_buffer()` を待たずに (visibility lag のみで) 可視になる。バッファ類の event を検査する場合は flush hook を明示的に呼ぶ。固定 sleep は書かない (`audit_visibility_lag_ms()` から待ち時間を取る)。
2. **秘密不在**: 返された event に契約 `forbidden_fields` (`credential`/`token`/`password`/`secret`/`private_key`/`sql`/`row_value`) の語が**キーとして**現れず、かつ**再利用可能な秘密** (secret / verifier / pepper)・SQL テキスト・行の値が**値として**現れない。**credential / application の識別子は禁止対象ではない** (レビュー m-1) — `actor_id` は credential_id であり (`service.py` L355 の `_event` が `actor_id=canonical.credential_id`)、`target_id` も credential/application の識別子である。これらは SI-14 が要求する帰属情報そのものであって、禁じられているのは再利用可能な秘密である。
3. **authority 分離**: **control base URL に対する** `POST /v1/audit/query` へ application credential を提示すると `FORBIDDEN` である (契約 semantics の直接検証)。data-plane base URL の同パスは `CAPABILITY_UNSUPPORTED` を返す (このホストは当該 capability を提供していないという真の宣言に一致する挙動) — 2 つのホストで応答コードが異なることは、両者が異なる主張をしているためであり、矛盾ではない。この区別を test の docstring に明記する。
4. **削除面不在**: application authority から監査を author/update/delete する面が存在しない (契約 `audit.immutability`)。

### 8.2 C-11 の executable 化

`test_c11_response_schema_conformance.py` L101-111 が記録する `AuditResult` / `AuditQueryRequest` の zero-coverage を解消する。実応答を閉鎖 `AuditResult` schema へ reverse-validate し、`AuditQueryRequest` は positive control (閉鎖 schema が余分キーを拒否すること) を含める。`events[]` の各要素は契約上開放されているため、`plane` / `recorded_at` / `count` / `cursor` の追加フィールドは適合を壊さない。

### 8.3 port への追加

`conformance-tests/adapter.py` に以下を加える (port 版数の繰り上げを伴う。番号は実装裁量):

- `audit_query(actor, request) -> Mapping` — 正本名は `audit_query` (監督裁定4。旧稿の `attempt_audit_query` は誤記であり本節で訂正する)。control/audit credential で `audit_query` に到達し、生の `AuditResult` 文書を返す。到達面が無い peer、または宣言が unavailable の peer (WP-1 補則1の declare-first) は `SurfaceAbsent` を送出する。
- application credential での `audit_query` 拒否を観測する経路 (既存の denial 表現 `ConformanceDenial` を使う)。
- `audit_visibility_lag_ms()` (レビュー M-11) — peer が宣言している visibility lag を port から読む。テストはこの値を待つ。**固定 sleep をテストに書かせないための port である** — 実 PG 環境の負荷で sleep が足りずに時々赤くなる (完了ゲート suite の偽の赤を悪化させる) 事態を構造的に防ぐ。
- `flush_audit_buffer()` (レビュー M-11) — buffer の同期 flush を peer 自身に実行させる adapter 特権 hook。`control_audit_events()` と同格の位置づけ (adapter が組み立てるのではなく peer に実行させる) であり、これが無いとバッファ類 event の可視性が時間依存になる。

**HTTP adapter の宛先 (監督裁定 R1)**: HTTP adapter は `/v1/audit/query` を **control base URL に対して**発行する (data-plane base URL ではない)。契約パスは逐語で同じだがホストが異なるという D-5 の構造がそのまま port に現れるため、adapter の当該メソッドにこの根拠をコメントとして残すこと (`SurfaceAbsent` の主張と同じく、後から読む者が「なぜ control ホストなのか」を検証できるようにする)。in-process adapter は control 側 service オブジェクトの対応メソッドを直接呼ぶ。

**既存の `control_audit_events()` (adapter.py L1017) は維持する** — これは耐久 sink を直接読む adapter 特権 hook であり、C-15 vector 4 が依存している。`audit_query` endpoint 越しの観測とは別物として併存させる (「adapter が他の呼び出しの副作用から組み立てた列」であってはならない、という同 docstring の規律はそのまま適用される)。

### 8.4 SurfaceAbsent 分岐

**`SurfaceAbsent` は control surface そのものが無い adapter に限定する** (レビュー M-4)。`SurfaceAbsent` を送出する adapter は C-14 が確立した形式に従い、`surface` と `forbidden_parameters` を伴わせる — `conformance-tests/absence.py` の `assert_control_operation_absent_or_uniformly_refused` が主張の真偽を検査する。~~**「control surface はあるが AUDIT DSN 未設定」は `SurfaceAbsent` ではなく `ConformanceDenial` (`CAPABILITY_UNSUPPORTED`) 側に落ちる** — ルートは常に登録されており、実際にリクエストを受けて一様に拒否するからである (D-5)。~~ MitateDB の in-process adapter は control surface が無ければ `SurfaceAbsent` のままでよい。

**訂正 (2026-09-02、WP-1 実装時の監督裁定により上書き — 作業指示書補則1 = 監督裁定2)**: 上記取消線の文は本節の v1.4 起草時点の記述であり、**出荷された挙動と反対である**。実際に出荷された declare-first 規律では、`audit_query` が未宣言または `unavailable` (AUDIT DSN 未設定を含む) の場合、port の `audit_query()`/`flush_audit_buffer()`/`audit_visibility_lag_ms()` は要求を送らずに **`SurfaceAbsent`** を送出する — 「control surface はあるが AUDIT DSN 未設定」であってもポート層は宣言のみを見て判断し、実際のルートには到達しない。ルートが常に登録されており実際にリクエストを受ければ一様に `CAPABILITY_UNSUPPORTED` で拒否する、という D-5 の主張自体は実装として真のままだが、それは port を介さず直接 HTTP を叩いた場合の話であり、**共通 conformance port からの観測としては到達しない** (`SurfaceAbsent` の意味拡張、本節末尾および `docs/design/CONFORMANCE_ADAPTER_V1.md` §18.3)。`conformance-tests/absence.py` の `assert_control_operation_absent_or_uniformly_refused` (2形式モデル) は `audit_query` には適用されない — 同モジュールの docstring に明記済み。

注意点 2 つ:
- **vacuity guard を強化する (レビュー M-9)**。~~「1 本でも PROVIDED なら緑」では、in-process 2 本が恒久的に absent へ落ちても検出できない。guard は **in-process 形態から 1 本以上、HTTP 形態から 1 本以上**が PROVIDED 分岐を取ることを要求する。これが D-10 の「in-memory 側にも読み手を必須化する」判断と対になっている (in-memory reader が無ければ in-process は絶対に PROVIDED になれない)。`test_c16_cross_entity_atomicity.py` の `test_at_least_one_available_adapter_can_construct_the_v3_boundary_vector` を形態別に分けた形。~~
  **訂正 (2026-09-02、WP-1 実装時の監督裁定により上書き — 作業指示書補則2 = 監督裁定 v1.2-1)**: 上記取消線の「形態ごとに1本以上」案は、実際に出荷された guard 要求よりも弱い。出荷された全体 guard `test_c09_every_control_surface_adapter_takes_the_provided_branch` (`conformance-tests/test_c09_audit_evidence.py`) は「control surface を持つ登録済み adapter の**全数**が PROVIDED 分岐を取ること」を要求する (`registered_adapters()` と各 adapter 自身の実 `control_plane` status から機械導出、ハードコード列挙なし)。WP-1 時点では全 adapter が `audit_query: unavailable` のため常に赤であり、`@pytest.mark.xfail(strict=True, reason="no peer declares 1.4.0 yet; un-xfailed by the last flip WP")` を付けて登録済み — xfail 解除は最後の flip WP (WP-3(b)) の責務。個別 guard `test_c09_declared_capability_implies_provided_branch` は xfail なしで常時有効。
- **form-(b) の真正性限界は本条件にも及ぶ**。`ConformanceDenial` は `SurfaceAbsent` と違って provenance の証拠を持たないため、present-denial 分岐は「adapter が実際にリクエストを送ったか」を port レベルで判別できない。これは C-06/C-14/C-16/C-17 で既に開示済みの同一の限界であり、本フェーズで新たな検出ハックを発明しない (既存の wire-level positive-existence check の台帳項目が本件も覆う)。

---

## 9. Security Invariants との関係

### 9.1 新 invariant は不要である

本フェーズの安全性は既存の invariant で表現できる。CLAUDE.md の「Security Invariants は feature gate ではない」に従い、新機能ごとに invariant を足さない。

| Invariant | 本フェーズでの関わり |
|---|---|
| **SI-14** (Security-Relevant Auditability) | 本フェーズの主対象。最小 event class (authentication/authorization denial、credential lifecycle change、destructive schema/data operation、privilege-sensitive operation、Control Plane administrative change、security-control failure) のうち、application-plane に該当するものを耐久化する。"Does not require" 条項 (全 successful read の無制限記録は不要) が D-4 の buffer 緩和の根拠である。なお同条項は記録を**禁じてはいない**ため、両 peer で通常成功 event を記録する P4-D5 も適合である |
| **SI-10** (非開示) | `forbidden_fields` が耐久面にも載らないこと。r2db の FORBIDDEN tuple (`audit.py` L11, L51) は既存で拒否側、MitateDB は allowlist で丸める側 — 耐久化にあたって両者とも秘密が列に入らないことを実測する |
| **SI-00 / SI-02** (control/application 分離) | `audit_query` の置き場所 (D-5)。data-plane に control/audit credential store を持ち込まない。reader role を control-plane process role とも分ける |
| **SI-11** (Atomic Integrity) | N-1 (D-2)。監査記録とデータ commit の順序が、原子性の主張と矛盾しないこと |

### 9.2 新たに検証可能にすべき 11 性質

CLAUDE.md の「If a new capability cannot yet demonstrate an applicable invariant, make the security property testable」に従い、以下を**実測可能な形**にする。

1. **fail-closed by construction** — 耐久 sink に故障を注入すると、fail-closed 類の操作および denial 応答が成立しない (`SERVICE_UNAVAILABLE` になり、データ側に痕跡が残らない)。control-plane の既存テスト (`r2db-api/tests/test_control_plane_service.py` の sink 故障注入系) と同型を application-plane に置く。
2. **append-only by grant** — data-plane の api role (`r2dbsvc_api` / `mitatedbsvc_api`) で `application_audit` への UPDATE / DELETE / SELECT が**実際に拒否される**ことを、facade を介さない生の接続で実測する。control-plane の既存実測 (`r2db-api/tests/test_control_plane_store.py` L1725-1738、`MitateDB-api/tests/test_control_plane_postgres.py::test_control_plane_role_cannot_select_its_own_audit_table`) と同型。
3. **buffer overflow が alert event として耐久記録される** — 溢れが `security_control_failure` 行として残り、かつ `logging.error` が発火する。**P4-D5 により両 peer とも実 emit 経路 (query/insert/update 成功の連打) から buffer を溢れさせて検証できる** — 非対称を残した場合に MitateDB 側でこの性質が buffer 実装の単体テストでしか固定できなくなる問題 (レビュー m-7) は、P4-D5 の採用理由の 1 つであり、確定により解消した。
4. **application credential が `audit_query` で FORBIDDEN** — 契約 semantics の直接検証 (C-09 ベクタ 3 と同一。宛先は control ホスト、§8.1)。
5. **emit された `event_class` ⊆ 宣言語彙** — 両 peer で、実際に耐久記録され得る `event_class` の集合が `capabilities.audit_query.event_classes` の宣言集合に**含まれる**ことをテストで固定する。MitateDB は 6 フィールド sink の丸め (§6.2) を耐久経路から外すため、この性質が丸めの再混入に対する回帰ガードにもなる。
6. **fail-closed 類の event は buffer 経路に載らない** (レビュー B-2) — delete を含む mutate で sink 故障を注入すると `SERVICE_UNAVAILABLE` になりデータが不変であること。さらに、**両 peer で振り分けの判定点が同じ関数 (`_validate_delete_confirmation` 相当の確認 choke) である**ことをテストで固定する。
7. **buffer 行の書込み失敗が fail-closed 操作を止めない** (レビュー M-1) — buffer 行に故障を注入しても destructive 操作は成功し、その fail-closed 行は耐久化されている。
8. **1 操作 = 耐久 1 行** (レビュー M-7) — destructive mutate 1 回で `application_audit` の行数がちょうど +1 になる (control 面の `test_each_state_change_adds_exactly_one_audit_row` と同型)。
9. **データ commit 失敗が耐久 `error` 行を生む** (レビュー M-6) — データ commit に故障を注入すると、同一 `request_id` の `allow` 行の後に `outcome="error"` 行が耐久記録される。error 行の書込みにも故障を注入すると応答が `SERVICE_UNAVAILABLE` になる。**但し書き (レビュー N-1)**: この性質が覆うのは**プロセス生存下のクリーンな commit 失敗**のみである。プロセス消失を模擬した場合 (`error` 行を書く主体が居ない場合) に `allow` 行が単独で残るのは**仕様どおり**であり、テストはそれを失敗として扱わない — 逆に「プロセス消失模擬では allow 単独が残る」ことを明示的に固定する。
10. **1 application の侵害が platform DB を無制限に肥大させられない** (レビュー M-5) — (i) api role が長さ制約を超える値を INSERT できない (生の接続で実測)、(ii) 同一の無効 secret の N 連打で増える耐久行が**プロセスあたり**窓あたり 1 行に留まる (D-3 の合体。配備全体の上限は窓数 × 最大インスタンス数 M であり、テストは単一プロセスでこの性質を固定した上で、M の織り込みを runbook 側の責務とする — レビュー N-4)、(iii) buffer が上限を超えて成長しない (これも 1 プロセスあたり)。行サイズ × 行数の両方が有界であることをもって、SI-00 の可用性側の露出が閉じていることを示す。
11. **`plane` は書き手が指定できない** (レビュー m-2) — api role が `application_audit` に INSERT した行は、どのような値を書こうとしても `audit_query` からは必ず `plane="application"` として読み出される (`plane` は行の出所テーブルからの導出値であり、実列ではない)。

### 9.3 更新対象の既存記録 (スコープ内、監督裁定 R7)

以下は本フェーズの**記録 WP のスコープ内**であり、実装と同じフェーズで更新する。

- **`security/CONTROL_MAPPING.md` SI-14 行**: application-plane について「no external durable sink for this plane yet (phase 4, unchanged)」と書いている箇所を、本フェーズの成果 (テーブル・GRANT・fail-closed 経路・実測テスト) に置き換える。加えて次の 3 点をこの行に明記する: (i) **P4-D3 の線引き (未認証 denial は pre-auth window を追加せず合体で有界化する)** を control-plane について既にそうしているのと同じ形で、(ii) **非耐久とした 4 種** (`VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND`) とその理由 (SI-14 の最小 class 外)、(iii) **control 面の線引き (rate 拒否を記録しない) との関係** — 線引きの内容は異なるが、いずれも「SI-14 の最小 class の外」という同じ根拠に立つのであって、一方が他方の非対称を解消したわけではない (レビュー N-2)。
- **`security/CONTROL_MAPPING.md` SI-00 行 (b)**: 「the application-plane role (`r2dbsvc_api`) has no grant at all on `control_credentials`/`control_audit`」という主張は本フェーズ後も**真のまま**である (D-1 は新テーブルにのみ INSERT を足し、`control_audit` には触れない) が、「registry schema 全体に一切の書込権限を持たない」という含意で読まれ得るため、`application_audit` への INSERT-only を明示的に併記する。MitateDB 側の対応テスト (`test_application_plane_role_has_no_privilege_on_control_audit`) は**そのまま緑であり続ける**べきで、緩めてはならない。
- **`conformance-tests/CONDITIONS.md` の C-09 行と C-11 行**: C-09 の「not yet executable (common suite) — peer-local evidence only」を executable 化後の実態へ、C-11 の `AuditResult`/`AuditQueryRequest` zero-coverage 記述を実被覆へ更新する。既存行の書式 (どの adapter が PROVIDED でどれが absent かを正直に列挙する) を踏襲する。
- **配備ドキュメントの構成図とパス一覧** (レビュー m-8): `MitateDB-api/docs/cloud-run-cloud-sql.md` の構成図は control サービスを `main:app /control/v1/*` と記述しており、D-5 で `/v1/audit/query` が加わると陳腐化する。r2db 側の対応する配備ドキュメントも同様。あわせて「control ホストのエッジポリシーは `/control/v1/*` だけでなく `/v1/audit/query` も覆わねばならない」を明記する。
- **両 peer の runbook**: (i) 新 migration の適用手順 (適用順・実行 role・環境変数名)、(ii) reader role の DSN 設定 (`R2DB_AUDIT_DSN` / `MITATEDB_AUDIT_DSN`) と未設定時に `audit_query` が `unavailable` 宣言のままになること、(iii) **platform DB の容量監視** (M-5 の第 3 段。1 行サイズ上限 × 行数上限を根拠にした閾値設計。**行数上限の算出には最大インスタンス数 M を織り込む** — 合体も buffer もプロセスローカルなので、実効上限は「窓数 × M」および「buffer 容量 × M」である、レビュー N-4)、(iii-b) **監査書込み接続の `statement_timeout` / `idle_in_transaction_session_timeout` の設定値と、そこから導出される `visibility_lag_ms` の関係** (N-3。値を変えたら宣言も変わる)、(iv) **監査ポーリングと rate window の関係** (M-8 / P4-D4 項目 8。窓は `audit_requests_per_minute` として分離されるため break-glass との競合は構造的に解消されるが、推奨ポーリング間隔 = 宣言された `visibility_lag_ms` 以上、および両窓のサイズ設計は runbook の管轄)、(v) **platform DB 障害時の独立した読み取り路は帯域外 CLI のみ**であること (m-6)、(vi) D-11 の保持期間・剪定の操作手順。

---

## 10. スコープ外 (D-11)

**入らないもの**:

- **保持期間・剪定の自動化** — externally governed とする (契約 `audit.immutability` の "externally governed where required by the deployment")。**runbook への操作手順の記載は §9.3 のとおりスコープ内**だが、自動剪定機構は実装しない。
- **外部 SIEM / ログ基盤への転送** — 本フェーズは DB 内の耐久化までとする。
- **business audit** (application 自身のドメイン監査) — 本契約の対象外。
- **`control_audit` の改名・`application_audit` との統合** — R-C で却下済み。
- **既存 control-plane 経路の変更** — control-plane の endpoint・認可・監査の挙動は変えない。例外は 3 点のみで、いずれも本設計が明示的に要求するものである: (i) `audit_query` の追加 (D-5)、(ii) `_AUDIT_ROLE_ALLOWED_OPERATIONS` への `audit_query` 追加 (D-5)、(iii) **`control_audit` を書く接続への `statement_timeout` / `idle_in_transaction_session_timeout` の固定** (D-6 / N-3 — visibility lag の根拠として両接続に必要)。(iii) は挙動の変更ではなく上限の明示的な強制だが、既存 control-plane 接続に触れるため WP 完了条件で既存テスト全緑を確認する。
- **r2db-api の `cross_entity_mutation`** — フェーズ3.5 P35-D1 のまま unavailable 継続。
- **`audit` role の in-band 発行** — フェーズ3.5 §9 B-2 裁定で台帳へ送られた項目のまま。
- **WP 分割・作業指示** — 別文書。

---

## 11. 将来課題台帳 (本フェーズ新設分)

本設計時点で新設項目なし。WP 実施中に発生した項目をここへ追記する。

継承分は `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §7 を参照 (`audit_events` 予約名の未文書化、識別子受理域の開示ギャップ、json 列の write/read 非対称、wire-level positive-existence check、ほか)。このうち **`audit_events` 予約名の文書化**は P4-D4 の項目 6 として本フェーズで解消される。
