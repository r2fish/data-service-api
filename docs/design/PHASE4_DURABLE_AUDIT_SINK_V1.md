# フェーズ4 実施設計: application-plane 耐久 audit sink + audit_query

- 版数: **v1.6 (2026-09-03、フェーズ4 台帳消化 WP-B4 記録整理)** — `docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md` (v1.5) の WP-B1〜WP-B3 で閉じた事実と、閉じないと裁定した事実の**両方**を反映。§5.1 に監督裁定 **P4-D15〜P4-D18** を追記、D-4 本文と P4-D12 行に P4-D15 による上書きを注記、§11.1 の全項目に状態を付与し **L4-10〜L4-12** を新設、**§11.2 = 契約 1.5.0 候補束と依頼者判断待ち事項**を新設
- 旧 v1.5 (2026-09-03、WP-4 記録整理) — 実装完了後の記録を反映。§3 D-4 に buffer flush 失敗時の復元切り詰めの計上規則を追記、§5 に WP 実施中の監督裁定を **P4-D6〜P4-D14** として番号付きで記録、**§9.4 = 各 WP の実装記録・レビュー裁定・変異注入・受理境界**を新設、§9.2 の 11 性質に実在テスト名の対応表を確定、§11 台帳に未解決項目を起票。本文の実装前の言い回し (「新設する」「実装要件とする」) は**当時の設計文として保存**し、実態は §9.4 が記録する
- 旧 v1.4 (2026-09-02。v1.0 = 初版。v1.1 = 起草時の疑義 7 件への監督裁定 R1〜R7 を反映。v1.2 = 独立レビュー (blocker 3 / major 11 / minor 8) 全件採用の監督裁定を反映 — D-1〜D-6・D-10 / §4 R-B / §5 U-1〜U-5 / §6 / §7 全節 / §8 / §9.2・9.3 / §10)
- v1.4 (2026-09-02): **依頼者裁定 (直接回答) を反映し §5 を確定形へ** — P4-D1〜P4-D5 を確定、§2 末尾に依頼者の設計原則を記録、本文の「U-x の決着待ち」を全て確定形へ。P4-D5 は監督推奨 (a) から (b) へ変更
- v1.3 (2026-09-02): 再確認レビューの新規 major 4 件 (N-1〜N-4) 全件採用の監督裁定を反映 — D-2 の allow 単独行の読み / D-3 バッファ類 4 種の非耐久化 / D-6 lag 導出式と両接続への timeout 強制 / 合体・buffer のプロセスローカル性 (§6.1・6.2 / §7.2・7.3 / §9.2 / §9.3)
- 位置づけ: `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §0「入らないもの」が明示的に繰延べた最後の項目 (application-plane 耐久 audit sink) の実施設計。`docs/design/R2DB_CCR14_CONTROL_PLANE_V1.md` R-6 が control-plane についてのみ先行実施した規律を、application-plane へ持ち込む
- 直接の申し送り: `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` L303-305 の N-1 (バッチ監査の commit 後遅延発火と R-6 同一 tx 規律の整合)
- 体制: Fable 監督/設計/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー。完了条件・単一コミット規律・identity 確認は既存フェーズと同一
- 本文書の性格: **監督が確定した枠の実施設計**である。§3 の決定は監督確定、§5 は**依頼者が確定**した裁定 (P4-D1〜P4-D5)、§4 は却下済み。WP 分割は本文書に含めず別途作業指示書で行う

---

## 1. 問題設定と現状

> **v1.5 註 (2026-09-03)**: 本節と §7 が記述する「現状」は**フェーズ4 着手前 (2026-09-02 時点) の状態**であり、当時の問題設定の記録として逐語のまま保存する。実装後の実態は §9.4 (WP 実装記録)、`security/CONTROL_MAPPING.md` の SI-14 行、および両 peer の runbook が正本である。とくに §1.1 の「両 peer とも揮発性である」と §1.5 の「`audit_query` は両 peer ともスタブである」は**現在は真ではない**。

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
2. **1 操作あたりの行数を有界化する** — 1 利用者操作 = 最大 1 行 (D-10)、denial は合体で窓あたり最大 2 行 (初回行 + 集約行、D-3、監督裁定 J-1)、通常 event は bounded buffer (D-4、overflow alert 行は N-2 によりさらに flush 間隔あたり最大 1 行に律速される)。
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
D-3 が非耐久と定める denial (耐久対象は D-3 表の 6 項目のみの包含列挙であり、それ以外は `VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND` に限らず全て非耐久 — 監督裁定 2026-09-02、WP-2(a) レビュー J-2)。既存の in-memory sink にのみ残る。

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

**耐久対象は包含列挙であり、表にないコードは全て非耐久 (監督裁定 2026-09-02、WP-2(a) レビュー J-2)。** 上表の「fail-closed 類」欄に列挙した 6 項目 (認証系 2 コード相当、`FORBIDDEN`、`APPLICATION_DISABLED`、credential の revoked 相当、`DESTRUCTIVE_CONFIRMATION_REQUIRED`) だけが耐久記録の対象であり、それ以外の denial reason_code は、この表が明示的に挙げる `VALIDATION_FAILED`/`LIMIT_EXCEEDED`/`CAPABILITY_UNSUPPORTED`/`NOT_FOUND` の 4 種に限らず**すべて**非耐久として扱う (`SERVICE_UNAVAILABLE`/`AUTH_STATE_UNAVAILABLE`、`CONFLICT`、`PRECONDITION_FAILED` を含む)。除外列挙 (この 4 種だけが非耐久で、それ以外は耐久) の読みは WP-2(a) 実装レビューで、監査パイプライン自身の失敗が生む `SERVICE_UNAVAILABLE` を新規の denial として再度耐久ルートへ通してしまい、1 操作が耐久 3 行を生む (D-10 禁止条件 (ii) の破れ) ことが確認されたため、この一言で確定する。

**非耐久の全コードは bounded buffer にも載せない (レビュー N-2)**。これらは既存の in-memory sink にのみ残り、`application_audit` には一切現れない。bounded buffer (D-4) は**通常の data-operation 成功 event 専用**である — buffer に入れてしまうと結局は耐久 INSERT されることになり、「耐久面に載せない」という判断が実現しない (かつ D-3 が防ごうとしている流量問題が buffer 経由で戻ってくる)。

これら非耐久のコード (この 4 種に限らず、D-3 表の 6 項目に含まれない全て) は SI-14 の最小 event class の外にある。契約 `sink_failure_policy` をより広く読むことも可能だが、**決めた線を `security/CONTROL_MAPPING.md` の SI-14 行に理由つきで書く** (§9.3)。なお **CCR-14 との関係は「非対称の解消」ではない** — control 面は rate 拒否を記録せず、data 面はこれらのコードを非耐久とする。**線引きは異なるが、いずれも SI-14 の最小 class の外**という同じ根拠に立つ。この点も SI-14 行への記載事項に含める。

#### (2) 合体 (coalescing) による流量の有界化

耐久対象の denial であっても、1 リクエスト = 1 INSERT では流量が無界である。**一度漏洩して revoke 済みの secret を 1 本持つ攻撃者がそれを毎秒 1 万回提示すれば、すべてが fail-closed 類として platform DB に落ちる** — 有界なのは拒否の*種類*であって*行数*ではない。よって合体する。

- **合体キー**: `(application_id, actor_id または "unknown", operation, reason_code)`
- **窓 W**: 60 秒 (実装裁量で可変。宣言で公開する)
- **窓内の初回**: 同期の耐久 INSERT + commit。失敗すれば当該応答を `SERVICE_UNAVAILABLE` (fail-closed)。
- **窓内の 2 回目以降**: メモリで計数のみ。窓終了時に、2 回目以降が 1 件でもあれば**別の 1 行**として flush し、その繰り返し回数 (初回を含まない) を 14 列目 `count` に載せる。2 回目以降が無かった窓は、この flush 行自体を出さない。 **窓内で 2 回目がちょうど 1 回だけ起きた場合 (繰り返し回数 = 1) は、この flush 行の `count` を NULL のまま書く** (WP-2(b) レビュー B-1、監督裁定 2026-09-03) — `count` は「この 1 行が代表する発生回数」であり、1 のときは他の通常行と同じく列を省略する (契約 `audit.query_event_fields_note` の "never zero or one")。
- **窓あたり最大 2 行/プロセス (監督裁定 2026-09-02、レビュー J-1)**: 初回の同期行と、窓末の集約行 (2 回目以降が存在する場合のみ) の**合計 2 行**が、1 プロセス・1 窓の実効上限である。「1 行」という記述は窓末 flush が書く行数を指すのであって、窓全体の総行数ではない — `application_audit` の api role 権限が INSERT のみ (UPDATE 不可、§6.1/§9.2 性質 2) である以上、初回行の `count` を後から改訂して単一行に集約することはできない。この 2 行という上限は §9.3 の runbook 容量算出 (窓数 × 最大インスタンス数 M) に「2 ×」として織り込むこと。
- **クラッシュ時に失うのは窓内の計数のみ**で、初回行は既に耐久化されている。
- **合体カウンタはプロセスローカルである (レビュー N-4)**。共有ストアを介さないため、同一の合体キーでも**プロセス (インスタンス) ごとに** 初回行 + (該当すれば) 集約行が出る。

これにより、未知 secret の連打も revoke 済み secret の連打も **プロセスあたり窓あたり最大 2 行 (初回行 + 集約行)** に有界化される。配備全体の実効上限は **窓数 × 最大インスタンス数 M** であり、「1 行/分」ではない — M は水平スケール設定 (Cloud Run の最大インスタンス数等) で決まるので、runbook の容量閾値算出にこの M を織り込む (§9.3)。新しい拒否経路 (= 正規テナントへの巻き添え面) を作らずに増幅を止められる点が、pre-auth rate window の追加より優れている。この形は依頼者裁定 **P4-D3** で確定した (§5 に却下した 3 案とその理由を記録)。

- **壊れるシナリオ**: 合体も範囲限定もしないと、(i) 漏洩済み secret 1 本の連打で監査テーブルが無制限に膨張し、platform DB 同居の credential store ごと全 application の認証を止められる (SI-00 の可用性側の破れ)、(ii) 壊れたクライアントの `VALIDATION_FAILED` 連発が、データ DB に触らない検証エラーを platform DB への同期ラウンドトリップに化けさせ、データ面のレイテンシに恒常的に上乗せされる。
- **検証方法**: 同一の無効 secret を N 回 (N ≫ 1) 提示し、窓内に増える耐久行が (初回の同期行を除いて) ちょうど 1 行の**集約行**として追加され、その `count` が繰り返し回数 (N − 1) になることを実測する (上記「窓あたり最大 2 行/プロセス」参照)。`VALIDATION_FAILED` の連発では耐久行が増えないことを実測する。初回 INSERT に故障を注入すると応答が `SERVICE_UNAVAILABLE` になることを実測する。

### D-4 通常 data-operation event = bounded buffer + overflow の in-band alert

query/mutate の成功、catalog といった**通常の data-operation 成功 event** は、**bounded in-memory buffer (既定 1000、実装裁量で設定可)** に積み、定期または閾値でバッチ INSERT する。buffer の対象はこれのみである — D-3 が非耐久と定めた denial (4 種に限らず耐久対象外の全て) は buffer にも載せない (レビュー N-2)。overflow alert 行自体の emit 頻度も **flush 間隔あたり最大 1 行** に律速される (WP-2(a) fix round 2 review N-2 — eviction/flush 失敗の頻度から独立に有界)。

**buffer はプロセスローカルである (レビュー N-4)**: 容量 1000 は**1 プロセスあたり**であり、配備全体では **1000 × 最大インスタンス数 M** の未 flush event が同時に存在し得る。同様に overflow alert も**プロセスごとに**発生する。runbook の容量閾値算出にこの M を織り込む (§9.3)。

**flush は常に別トランザクション・別接続で行う (レビュー M-1、確定)**。fail-closed 書込みの tx に**相乗りさせない** — 相乗りすると、契約がバッファで吸収してよいと定めた通常 event の書込み失敗 (例えば長さ制約違反の 1 行) が、利用者の destructive 操作を `SERVICE_UNAVAILABLE` で止めてしまい、`sink_failure_policy` が 2 類を分けた意図が逆転する。加えて条件7「監査はガードレールでありゲートではない」(§2) にも反する。fail-closed 行の commit 成否は buffer 行の成否に依存してはならない。

overflow 時は最古から捨て、同時に:
1. stdlib `logging.error` の**固定メッセージ**を発火する (可変部に application 識別子等の実データを載せない)。
2. `security_control_failure` event (`reason_code="audit_buffer_overflow"`, `operation="audit_buffer"`, `target_kind="audit_sink"`) を**耐久 INSERT** する。

この 2 番目が契約の言う「explicit operational alert」の in-band 実現である。運用側の logs-based alert 設定は runbook の管轄とする。捨てられた件数は、新設する 14 番目の列 **`count`** (「この行が代表する発生回数。NULL = 1」) に載せる (契約 `audit.fields_note` が `audit.fields` を additive 語彙と明記しているため適合)。 **累積の欠落数がちょうど 1 件だった alert 行も同じ規則に従い、`count` は NULL のまま書く** (WP-2(b) レビュー B-1、監督裁定 2026-09-03)。`count` は overflow alert 行と D-3 の合体 denial 行の 2 用途が共有し、それ以外の event では NULL である。

**flush は swap-out であり、失敗時の復元でも容量を超えない (v1.5 追記、WP-2(a) follow-up `411c034` / WP-3(a) `54318c6`)**: flush は lock 下で pending list を**丸ごと swap-out** する (snapshot して後から前置分を削る形では、定期 flush と閾値 flush が重なったときに同じ event を二重に耐久記録する)。書込みが失敗したら、保持していたバッチを先頭へ戻した上で **buffer を容量まで最古から切り詰める** — さもなければ「復元で容量を超える」経路が bounded buffer の上限そのものを破る。**このとき切り詰められた分は overflow と同じ扱いで `dropped` に計上する** (alert 行の `count` に乗り、固定メッセージの `logging.error` を伴う) — 復元は捨てた事実を消さない。~~`failing` フラグは buffer が完全に排出されたときにのみ解除する。~~ **← この一文は P4-D15 が上書きした (下記 v1.6 注記)。**

**`failing` フラグの解除条件は「成功 flush の完了」である (v1.6 追記、P4-D15 により変更、2026-09-03、WP-B2)**: 上の取り消し線の一文 (v1.5 時点の記述、P4-D12 の後半) は**もはや真ではない**。現行は、flush が成功したら **buffer の残量に関係なく** `failing` を解除する — `failing` は「最後に**完了した** flush 試行の結果」を表す。継続負荷下では buffer が空にならないため、旧条件では sink が実際に回復した後もフラグが立ち続け、alert 行の再発火間隔がバックオフ上限 (最大 60s) まで開いたままになっていた (台帳 L4-3)。並行 flush で成功と失敗が競合する窓は**完了順序の意味論**で吸収する — 後から完了した失敗 flush が再度 `True` を立てる。切り詰め・`dropped` 計上・`count` への累積 (証拠側) と、alert 行の上限「flush 間隔あたり最大 1 行」は**いずれも変わらない**。裁定の全文と意図した代償 (フラッピング時の alert レート上昇) は §5.1 P4-D15 を見よ。

- **壊れるシナリオ**: overflow を黙って捨てると、契約 `sink_failure_policy` 後段の「alert なしの silent discard」に不適合となり、監査に穴があること自体が観測不能になる。復元時の切り詰めを `dropped` に計上しないと、同じ穴が「復元」という名前で無音のまま開く。
- **検証方法**: buffer 容量を小さく設定して意図的に溢れさせ、`logging.error` の発火と `security_control_failure` 行がちょうど 1 件耐久記録されることを実測する。失敗中の flush と並行して push を続け、buffer が容量を超えないことと、切り詰め分が drop として計上されることを実測する。

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

既存の in-memory `AuditSink` (r2db 13 フィールド、MitateDB 6 フィールド) は、**D-3 の耐久対象外の全コード (包含列挙の外側すべて) の denial の唯一の記録先**になるため、単純撤去はできない (レビュー N-2)。耐久 sink の前段 (buffer) に統合するか併存させるかは実装裁量だが、以下 2 つは**禁止条件**である: (i) 記録先が二重になって片方が黙って落ちる構造、(ii) 1 操作が 2 行の耐久行を生む構造。

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

**確定**: D-3 のとおり。耐久対象の denial を範囲限定した上で `(application_id, actor_id または "unknown", operation, reason_code)` を鍵に窓 W=60s で合体し、**プロセスあたり窓あたり最大 2 行 (初回行 + 集約行)** (`count` 列に発生回数) に有界化する。data-plane に新しい pre-auth 拒否経路は追加しない。

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

### 5.1 WP 実施中の監督裁定 (v1.5 追記 P4-D6〜P4-D14、v1.6 追記 P4-D15〜P4-D18)

P4-D1〜P4-D5 は依頼者裁定である。以下は **WP-1〜WP-3 の実装・レビュー・受け入れ監査の過程で監督が確定した裁定**であり、いずれも設計本文 (§3/§6/§7) の該当箇所に既に反映済みだが、番号のない裁定が本文に溶けている状態を避けるためここに列挙する。番号は本節で新規に振ったものであり、当時のレビュー記号 (J-1 等) を併記する。

| 記号 | 裁定 | 由来 | 本文の該当箇所 |
|---|---|---|---|
| **P4-D6** | 合体 denial は「窓内初回の同期行 + 窓末の集約行」の **2 行**であり、「窓あたり 1 行」ではない。`application_audit` は書き手に INSERT しか与えないので初回行の `count` を後から改訂できない以上、2 行が 1 プロセス・1 窓・1 キーの実効上限である | WP-2(a) レビュー **J-1** (実装者の裁量判断を追認)、2026-09-02 | D-1 有界化 2 / D-3(2) / §9.2 性質 10(ii)。runbook の容量算式は `2 × 窓数 × M` |
| **P4-D7** | 耐久対象 denial は **包含列挙**である — D-3 表が挙げる 6 コードだけが耐久であり、それ以外は表が名指しした 4 種に限らず**すべて**非耐久 (`CONFLICT`/`PRECONDITION_FAILED`/`SERVICE_UNAVAILABLE`/`AUTH_STATE_UNAVAILABLE` を含む) | WP-2(a) レビュー **J-2**、2026-09-02。除外列挙の読みでは、監査パイプライン自身の失敗が生む `SERVICE_UNAVAILABLE` が新規 denial として再入し 1 操作が耐久 3 行を生む (D-10 禁止条件 (ii) の破れ) ことが実測された | D-2 の「非耐久」/ D-3(1) / §7.2 |
| **P4-D8** | `count` は「この 1 行が代表する発生回数」であり、契約の "never zero or one" に従う — **繰り返しがちょうど 1 回の集約行も、累積欠落がちょうど 1 件の alert 行も `count` を NULL のまま書く** | WP-2(b) レビュー **B-1**、2026-09-03 | D-3(2) / D-4 |
| **P4-D9** | buffer の **flush 失敗も alert 対象**とする (eviction による欠落と同格に `dropped` へ計上する) — 「捨てた」のが容量超過か書込み失敗かは、証拠が失われた事実を変えない | WP-2(a) レビュー **J-3** (実装者の裁量判断を追認)、2026-09-02 | D-4 / §7.4 |
| **P4-D10** | `audit_events` 予約名は**文書化だけでなく実装義務**である (契約 1.4.0 の無条件義務 (a))。予約は `create_entity` だけでなく、**entity 識別子を受け取るあらゆる位置**で効かねばならない | WP-2(b) 受け入れ監査 **C**、2026-09-03 | §1.7 / P4-D4 項目 6。台帳の継承項目はこれで RESOLVED |
| **P4-D11** | 合体の排他は**キー単位の lock** とし、耐久 I/O を lock 保持のまま行わない。異なる合体キーの denial が互いに待たないことをテストで固定する | WP-2(a) レビュー m-2、2026-09-02 | D-3(2) / §7.2 |
| **P4-D12** | buffer の flush は **swap-out** で行い、失敗時の復元では **buffer を容量まで切り詰め、切り詰めた分を `dropped` に計上する**。~~`failing` フラグの解除は buffer が完全に排出されたときのみ~~ **← この後半は P4-D15 が上書きした (2026-09-03、WP-B2)。現行の解除条件は「成功 flush の完了」であり buffer の残量を参照しない。swap-out と切り詰めを定める前半は有効なまま** | WP-2(a) follow-up (`411c034`) / WP-3(a) レビュー B-2、2026-09-03。snapshot + 後置削除の形は定期 flush と閾値 flush の重なりで同一 event を二重に耐久記録していた (両 peer 共通の欠陥として MitateDB 側レビューで発見され、r2db へ対称に適用) | D-4 (v1.5 追記) |
| **P4-D13** | `after` cursor は**フィルタ非依存の keyset** とし、その旨を宣言 (`cursor_note`) で公開する。両 peer で同一意味論に揃える | WP-2(b) 受け入れ監査 **F/E**、2026-09-03 | D-6。「同一フィルタ条件下でのみ有効」という v1.1 起草時の表現より強い性質を出荷している |
| **P4-D14** | 非監査の認証面 (`auth.CredentialStore.peek()`) は **conformance adapter 専用**に限定し、`src/mitatedb_api` パッケージ内部からの呼び出しが一切無いことを AST 走査で機械的に固定する | WP-3(b) レビュー **G**、2026-09-03 | §11 台帳 (経緯と副作用点検) |

これらはいずれも「設計の変更」ではなく、**設計が一段粗く書いていた箇所を実装が踏んで判明した確定**である。再検討する場合は上表の「由来」列の実測事実を出発点にすること。

**v1.6 追記 (フェーズ4 台帳消化、`docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md` v1.5 §1)**。以下の 4 件は、フェーズ4 完了後に §11.1 の台帳を消化する過程で監督が確定した裁定である。P4-D15 は P4-D12 の後半を**上書きする**唯一の裁定であり、それ以外は既存裁定と衝突しない。

| 記号 | 裁定 | 由来 | 本文の該当箇所 |
|---|---|---|---|
| **P4-D15** | `failing` フラグは「最後に**完了した** flush 試行の結果」を表す。flush 成功時は **buffer の残量に関係なく** 解除する (旧: 「flush 成功 **かつ** buffer が完全に排出された」)。並行 flush で成功と失敗が競合する窓は**完了順序の意味論**で吸収する — 後から完了した失敗 flush が再度 `True` を立てる。**変わらないもの**: 証拠 (`count` への欠落数の累積。`_dropped_total` の減算は `_flush_currently_failing` を参照しない)、alert 行の上限「flush 間隔あたり最大 1 行」(`_retry_alert` の `alert_min_interval_s` の床が独立に効く)、runbook の「回復は当該ペアの回復メッセージで読む」という運用指示。**変わるもの (意図した代償)**: N-2 の指数バックオフが成功 flush ごとに床へ戻るため、sink が**フラッピング**しているときの alert 行レートが「60s に 1 行」(バックオフ上限)から「`alert_min_interval_s` に 1 行」(r2db 既定 2s) へ**上がり得る** — 部分的に書ける sink には証拠を早く書くほうがよく、宣言上の上限は破れない | L4-3 (両 peer 同型)。WP-3(a) レビュー **m-1** が「別 batch の失敗中 flush のバックオフが、成功側の race で床に戻る」ことを理由に現行形を選んでいたが、その代償として継続負荷下で sink 回復後もフラグが貼り付く。WP-B2 で両 peer 同型に閉じた (r2db `service.py` `_AuditBuffer.flush` の成功分岐、MitateDB `audit_dispatch.py` の同分岐、各 1 行) | D-4 (v1.5 追記の末尾、v1.6 注記) / P4-D12 の後半を**上書き** / §11.1 L4-3 |
| **P4-D16 v3** | 宣言語彙 (`event_class`) の走査は「**無差別 literal 規律 + 定義側 keyword-only 保証 + dict 密輸禁止 + 語彙関係の厳密一致**」で閉じる。**callee 名フィルタは使わない**。(a) 走査対象は `src/<pkg>` 配下の全 `.py` の `rglob` 再帰列挙 (手書きファイル列挙は廃止)。(b) 全 `Call` の `event_class=` 実引数は、文字列 `Constant`、**囲む関数定義の仮引数束縛を検証した転送**、または READ 側の `Attribute(attr="event_class")`/`Subscript["event_class"]` のみ許容し、それ以外 (ローカル変数代入・`global`/`nonlocal`・`for` ターゲット・walrus・`with…as`/`except…as`/`match…as` 等の再束縛由来の同名 `Name`、`JoinedStr`、`BinOp`、`Call`) はすべて違反。(c) 全 `FunctionDef`/`AsyncFunctionDef` について、仮引数 `event_class` は **keyword-only** でなければ違反 (`self` は判定から除く) — 位置渡しの emit 面が構文的に存在し得なくなる。(d) キー literal `"event_class"` を持つ `Dict` literal と `x["event_class"] = ...` の `Subscript` 代入は、値が (b) と同じ転送規則を満たす場合**のみ**許容 (「文字列 `Constant` のときのみ失敗」という旧規則の**反転**)。(d′) 加えて**全スコープ** (モジュール直下・クラス本体・関数本体を区別しない無条件 `ast.walk`) の `Assign`/`AnnAssign`/`AugAssign` のうち、ターゲットが `Name(id="event_class")` / `Attribute(attr="event_class")` (タプル・リスト・starred 分解後を含む) のものにも同じ転送規則を掛ける。(e) これらにより literal の全集合 **U** が完全に列挙できるので、**`U == D ∪ N` かつ `D ∩ N == ∅`** を厳密に固定する — **D** = 宣言 `DECLARED_AUDIT_EVENT_CLASSES`、**N** = テスト内に明示列挙し各要素に「耐久表へ届かない根拠」をコメントで付した非耐久除外集合 (**r2db N = 3 語** `authentication` / `control_failure` / `control_state`、**MitateDB N = ∅**)。(f) MitateDB の同名 2 本は 1 本へ統合、r2db の `_EVENT_CLASS_CALL_SPECS` 方式は廃止し、両 peer の走査ヘルパを同型にする。**宣言に非耐久語彙を足して (e) を通すことは禁じる** — `audit_query` が決して返さない語彙を公開する嘘になる | L4-5 (両 peer 同型)。**v2 (「三方向一致」= 定義集合と呼び出し集合と宣言の突き合わせ) は撤回した** — 下記「P4-D16 の経緯」を見よ。診断で判明した実測: MitateDB には同名の走査テストが 2 本あり、`tests/test_application_audit.py` 側は手書きの 4 ファイル列挙で走るため `src/mitatedb_api/http.py` の実 emit サイトを見ていなかった。r2db 側は `glob("*.py")` の非再帰かつ callee 名キー付きだった。v3 は独立レビュー round1 (M3/M6) と受け入れ監査 3 ラウンド (M7 = class/instance 属性 literal の `Attribute` 密輸、M8 = `with…as`/`except…as` 等の再束縛) を経て (b)(d)(d′) を厳格化した。WP-B1 で両 peer に実装 | D-7 / §9.2 性質 5 / §11.1 L4-5。唯一の製品コード変更は r2db `service.py` の `_event` / `_control_event` の keyword-only 化 (呼び出し計 21 件のキーワード渡し化、挙動不変) |
| **P4-D17** | HTTP conformance adapter が構築する書き手接続の `statement_timeout` / `idle_in_transaction_session_timeout` は、**peer-local テスト**で固定する。**共通 port (`conformance-tests/adapter.py`) には足さない** — 共通契約に無関係な試験用途で port version を上げることになり、得るものが無い。手法は既存 composition-root テストと同じ (**sink 自身が作る書き手接続を取り、`SHOW` で実効値を実測する**。接続の取り方は peer の sink 構造に従う — r2db は `_pool.connection()` で pool から借り、MitateDB の `PostgresApplicationAuditSink` は **pool を持たず** `_connect()` (`MitateDB-api/src/mitatedb_api/application_audit.py:295`) が呼ばれるたびに新しい接続を張る) | L4-6 (両 peer共通、WP-3(b) レビュー **D6**)。adapter 側の書き手接続から timeout 配線を落とす変異が緑で生存していた。peer 本体の composition root については両 peer とも実測テストが既にある (SI-14 行の点 (12)) ため、宣言の真実性そのものは保たれていた。WP-B3 で両 peer に peer-local テストを追加 | §11.1 L4-6。port version は **v1.8 のまま**、`docs/design/CONFORMANCE_ADAPTER_V1.md` は無変更 |
| **P4-D18** | C-09 vector 4 は**射程を明示して据え置く** — **CLOSED とはしない**。peer 側に監査変更面が無いことは **DB 権限**で担保されている (書き手は `application_audit` に INSERT のみ、reader は両 audit 表に SELECT のみ) — 両 peer に権限テストが実在する (§9.2 性質 2)。vector 4 を peer 観測形へ作り直しても**新しい安全結果は得られない**。`conformance-tests/CONDITIONS.md` の C-09 行と vector 4 の docstring に射程を明記する | L4-8。新しい安全結果が生じないため据え置き、peer 観測形への作り直しは将来の判断に残る | §11.1 L4-8 / `conformance-tests/CONDITIONS.md` C-09 行 / `conformance-tests/test_c09_audit_evidence.py::test_c09_v4_no_audit_mutation_or_deletion_surface_exists` |

**P4-D16 の経緯 (v2 の撤回理由)**。v2 は「パッケージ内の `event_class` を受ける**定義**の集合と、`event_class=` を渡す**呼び出し**の集合と、宣言 **D** の三方向を一致させる」形だった。独立レビュー round1 が現行コードに対して実測したところ緑にできないことが判明したため撤回した — (i) 定義集合に `append` が入り、パッケージ内のあらゆる `list.append()` が違反になる (r2db 36 件 / MitateDB 46 件)、(ii) MitateDB の `control_audit` 書込みは `append_audit(**fields)` / `audit_append` という**転送ラッパ**を通るため定義集合に入らず、実 emit サイト 13 件が「未知の emit 面」として違反になる、(iii) r2db `_control_event` の語彙 `control_failure` / `control_state` は**レガシーの in-memory sink 専用**で耐久表へ届かないため、宣言へ足せば `audit_query` が決して返さない語彙を公開する嘘になる (同型の非耐久語彙が `_event` の `authentication` にもある)。(iii) が v3 の **N** (非耐久除外集合を宣言ではなくテスト内に名指しで列挙する) を生んだ。

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

**まず D-3 の範囲判定を行う** — D-3 の表が挙げる 6 項目 (認証系相当、`FORBIDDEN`、`APPLICATION_DISABLED`、credential の revoked 相当、`DESTRUCTIVE_CONFIRMATION_REQUIRED`) だけが**耐久**であり、それ以外の reason_code (`VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND` に限らず、**耐久対象外の全コード**) は非耐久として耐久経路にも buffer にも入れない (既存の in-memory sink にのみ残る、レビュー N-2)。両 peer とも `except FoundationError` を丸ごと denial event に変換しているため (r2db `service.py` L219-225 / L258-260 / L280-281 / L295-296)、**この分岐を except 節の中に明示的に置く**必要がある。

次に **D-3 の合体**を適用する: 合体キーが窓 W 内で既出なら計数のみ (同期 INSERT なし)、初出なら同期 INSERT + commit、失敗時は `SERVICE_UNAVAILABLE`。窓終了時に合体行を `count` つきで flush する。

- r2db-api: `service.py` L115 (authentication_denial、`_audit.append` 直呼び) / L225 / L260 / L281 / L296、および `deny_unsupported` (L299-318、L317 で発火)。**L115 の経路は `_slot`/`_acquire_rate` (L321-350) を一切通らない** — つまり rate window の外側にあり、無効 secret の連打が何のカウンタにも当たらないまま監査面に到達する。合体 (D-3) はここに掛ける。なお `deny_unsupported` は「レート/同時実行の課金を先に消費させる」設計 (L299-305 のコメント) だが、`CAPABILITY_UNSUPPORTED` 自体はバッファ類である。
- MitateDB-api: `auth.py` L355-422 (`authorization_state_failure` / `authentication_denied`) と `cell.py` L991-993 (`authorization_denied`)。data-plane に rate window が無い点は r2db L115 と同じ。

未認証 `authentication_denial` の扱いは **P4-D3 (合体方式)** で確定している — data-plane に pre-auth window は追加せず、合体で流量を有界化する。

### 7.3 buffer 経路 (D-4)

通常の data-operation event は bounded buffer へ積む:

振り分けは **D-2 の規範的規則**による — `event_class` では判定しない。判定点は `DESTRUCTIVE_CONFIRMATION_V1` の確認 choke (両 peer の `_validate_delete_confirmation` 相当) であり、両 peer で同じ関数がこの役目を負うことをテストで固定する (§9.2)。

buffer に載るのは**通常の data-operation 成功 event のみ**である (D-3 の非耐久コード — 4 種に限らず耐久対象外の全て — はここにも来ない)。

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
10. **1 application の侵害が platform DB を無制限に肥大させられない** (レビュー M-5) — (i) api role が長さ制約を超える値を INSERT できない (生の接続で実測)、(ii) 同一の無効 secret の N 連打で増える耐久行が**プロセスあたり**窓あたり最大 2 行 (初回行 + 集約行) に留まる (D-3 の合体。配備全体の上限は窓数 × 最大インスタンス数 M であり、テストは単一プロセスでこの性質を固定した上で、M の織り込みを runbook 側の責務とする — レビュー N-4)、(iii) buffer が上限を超えて成長しない (これも 1 プロセスあたり)、(iv) buffer overflow alert 行自体の emit 頻度が flush 間隔あたり最大 1 行に律速され、eviction/flush 失敗の発生頻度に比例して増えない (WP-2(a) fix round 2 review N-2)。行サイズ × 行数の両方が有界であることをもって、SI-00 の可用性側の露出が閉じていることを示す。
11. **`plane` は書き手が指定できない** (レビュー m-2) — api role が `application_audit` に INSERT した行は、どのような値を書こうとしても `audit_query` からは必ず `plane="application"` として読み出される (`plane` は行の出所テーブルからの導出値であり、実列ではない)。

#### 9.2.1 11 性質 × 実在テスト (v1.5 確定。作業指示書 §5 の対応表の最終形)

以下のテスト名は**すべて実在を確認済み**である (WP-4 起草時に全数 grep)。作業指示書 §5 の表は発注時点の**予定**名であり、実装が採った名前と食い違う箇所がある — その差分は本表が正本である。とくに `test_migration_0007_applies_after_0006_and_changes_no_existing_grant` は発注書の予定名であり、実装は初回適用と再適用を 2 本に分けた。

| # | 性質 | r2db-api | MitateDB-api |
|---|---|---|---|
| 1 | fail-closed by construction | `tests/test_application_audit.py::test_destructive_mutate_is_service_unavailable_when_the_durable_sink_fails`、`::test_schema_operation_is_service_unavailable_when_the_durable_sink_fails`、`::test_denial_response_is_service_unavailable_when_the_first_coalesced_insert_fails` | `tests/test_application_audit.py::test_destructive_delete_is_service_unavailable_when_the_durable_sink_fails_sqlite` / `_postgres`、`::test_schema_operation_is_service_unavailable_when_the_durable_sink_fails_sqlite` / `_postgres`、`::test_denial_response_is_service_unavailable_when_the_first_coalesced_insert_fails_sqlite` (**backend ごとに分割**されている点が r2db との命名差) |
| 2 | append-only by grant | `::test_api_role_cannot_select_update_or_delete_application_audit`、`::test_api_role_cannot_insert_a_value_longer_than_the_length_check`、`::test_controlplane_role_has_no_privilege_on_application_audit`、`::test_auditreader_role_can_select_both_audit_tables_and_nothing_else`、`::test_migration_0007_applied_for_the_first_time_changes_no_0001_through_0006_grant`、`::test_migration_0007_reapplication_is_idempotent_and_changes_no_existing_grant` | 同名 4 本 + `::test_api_role_can_insert_but_not_read_it_back`、`::test_migration_0005_applies_after_0004_and_changes_no_existing_grant`、`::test_migration_0005_reapplication_is_idempotent`、`::test_new_auditreader_role_has_no_memberships`。既存 `tests/test_control_plane_postgres.py::test_application_plane_role_has_no_privilege_on_control_audit` は**緩めずそのまま緑** |
| 3 | overflow が alert 行として耐久記録される | `::test_buffer_overflow_emits_logging_error_and_exactly_one_security_control_failure_row`、`::test_buffer_overflow_alert_row_with_exactly_one_drop_writes_no_literal_count_of_one`、`::test_alert_row_rate_is_bounded_to_at_most_one_per_flush_interval`、`::test_alert_insert_failure_is_sticky_with_exponential_backoff_and_does_not_block_operations` | 同名 4 本 + `::test_buffer_overflow_is_reachable_from_the_real_emit_path` (P4-D5 により実 emit 経路から到達可能) |
| 4 | application credential が `audit_query` で FORBIDDEN | 共通 `conformance-tests/test_c09_audit_evidence.py::test_c09_v3_application_credential_is_forbidden_on_the_control_host_audit_query` (4 adapter)。peer: `tests/test_audit_query.py::test_application_credential_is_forbidden_on_the_control_host_audit_query` | 同じ共通テスト + `tests/test_audit_query.py::test_application_credential_is_forbidden_on_the_control_host_audit_query`、`::test_application_credential_is_forbidden_on_the_control_host_audit_query_over_http` |
| 5 | emit された `event_class` ⊆ 宣言語彙 (**v1.6: P4-D16 v3 により `U == D ∪ N` かつ `D ∩ N == ∅` という等式へ強化された**。下の 6 本は両 peer 同名で、WP-B1 で置き換えた現存形である) | `tests/test_audit_query.py::test_declared_event_classes_cover_every_emittable_class` (e)、`::test_every_event_class_keyword_argument_is_a_string_literal` (b)、`::test_every_definition_taking_event_class_declares_it_keyword_only` (c)、`::test_no_event_class_string_literal_is_smuggled_through_a_dict` (d)、`::test_no_event_class_string_literal_is_smuggled_through_an_assignment` (d′)、`::test_event_class_forward_exclusion_requires_genuine_parameter_binding` (転送規則の回帰ガード)、加えて宣言の縮小を止める `::test_declared_audit_event_classes_change_only_deliberately` (L4-11)。**`::test_every_known_emission_method_name_is_still_called` は WP-B1 で削除済みであり、v1.5 までここに載っていた引用は解決しない** — callee 名キー (`_EVENT_CLASS_CALL_SPECS`) の廃止に伴う。`::test_ast_scan_now_covers_files_the_old_hardcoded_enumeration_missed`、`::test_mutating_an_ops_py_event_class_literal_to_an_undeclared_value_turns_the_declared_vocabulary_check_red` は現存 | **`tests/test_audit_query.py`** の上記 7 本と**同名・同形** (**v1.6: WP-B1 で同名 2 本を 1 本へ統合したため、`tests/test_application_audit.py` 側の `::test_declared_event_classes_cover_every_emittable_class` は存在しない**) + `tests/test_application_audit.py::test_durable_path_never_passes_through_the_six_field_rounding_sink`、`::test_declared_event_class_values_are_disjoint_from_the_six_field_sink_rounding_fallbacks` (丸め再混入の回帰ガード) |
| 6 | fail-closed 類は buffer に載らない / 判定点が確認 choke | `::test_delete_bearing_mutate_never_enters_the_buffer_path`、`::test_dispatch_point_is_the_destructive_confirmation_choke` | 同名 2 本 |
| 7 | buffer 行の失敗が fail-closed 操作を止めない | `::test_buffer_row_failure_does_not_block_a_fail_closed_operation` | 同名 |
| 8 | 1 操作 = 耐久 1 行 | `::test_each_data_operation_adds_exactly_one_application_audit_row` | 同名 + `::test_each_data_operation_adds_exactly_one_application_audit_row_for_every_operation_kind` |
| 9 | commit 失敗が `error` 行を生む / プロセス消失は `allow` 単独 | `::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`、`::test_failed_data_commit_through_dataservice_writes_exactly_two_durable_rows`、`::test_error_row_write_failure_makes_the_response_service_unavailable`、`::test_simulated_process_loss_leaves_the_allow_row_alone` | 同名 3 本 (`through_dataservice` を除く) + `::test_backend_commit_failure_is_classified_and_produces_an_error_row` (commit の try 移設) |
| 10 | 無制限肥大化の防止 | (i) `::test_api_role_cannot_insert_a_value_longer_than_the_length_check` / (ii) `::test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n`、`::test_coalesced_summary_row_with_exactly_one_repeat_writes_no_literal_count_of_one`、`::test_different_denial_keys_do_not_coalesce_together`、`::test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry`、`::test_capability_unsupported_and_not_found_denials_add_no_durable_row`、`::test_durable_denial_codes_match_the_design_d3_table` / (iii) `::test_buffer_does_not_grow_past_its_configured_bound`、`::test_concurrent_push_during_a_failing_flush_never_grows_the_buffer_past_capacity` / (iv) `::test_alert_row_rate_is_bounded_to_at_most_one_per_flush_interval` | 同名 (ただし (ii) の 5 本目は `::test_capability_unsupported_and_not_found_and_service_unavailable_denials_add_no_durable_row`)。**M (最大インスタンス数) の織り込みは runbook 側の責務**であり、両 peer の runbook で算式として書かれた (`POSTGRES_PROVISIONING_RUNBOOK.md` §15.1 / `cloud-run-cloud-sql.md` §3.2d) |
| 11 | `plane` は書き手が指定できない | `tests/test_audit_query.py::test_application_audit_rows_always_read_back_as_plane_application`、`::test_ordering_uses_plane_as_a_tiebreaker_not_event_id_alone`、`::test_cursor_boundary_on_identical_cross_table_event_id_has_no_loss_stall_or_duplicate` | 同名 3 本 |

**共通 suite 側** (`conformance-tests/`、全 4 adapter が PROVIDED 分岐): `test_c09_audit_evidence.py::test_c09_v1_fail_closed_events_are_observable_through_audit_query` / `::test_c09_v2_no_forbidden_field_key_or_reusable_secret_value_appears` / `::test_c09_v3_application_credential_is_forbidden_on_the_control_host_audit_query` / `::test_c09_v4_no_audit_mutation_or_deletion_surface_exists` / `::test_c09_declared_enabled_audit_query_actually_answers` / `::test_c09_declared_capability_implies_provided_branch` / `::test_c09_every_control_surface_adapter_takes_the_provided_branch`、`test_c11_response_schema_conformance.py::test_c11_audit_result_reverse_validates_against_the_closed_schema` / `::test_audit_query_request_closed_schema_rejects_an_excess_key` (**後者に `c11_` 接頭辞は無い** — 発注書の予定名との差)。

### 9.3 更新対象の既存記録 (スコープ内、監督裁定 R7)

以下は本フェーズの**記録 WP のスコープ内**であり、実装と同じフェーズで更新する。

- **`security/CONTROL_MAPPING.md` SI-14 行**: application-plane について「no external durable sink for this plane yet (phase 4, unchanged)」と書いている箇所を、本フェーズの成果 (テーブル・GRANT・fail-closed 経路・実測テスト) に置き換える。加えて次の 3 点をこの行に明記する: (i) **P4-D3 の線引き (未認証 denial は pre-auth window を追加せず合体で有界化する)** を control-plane について既にそうしているのと同じ形で、(ii) **非耐久とした 4 種** (`VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND`) とその理由 (SI-14 の最小 class 外)、(iii) **control 面の線引き (rate 拒否を記録しない) との関係** — 線引きの内容は異なるが、いずれも「SI-14 の最小 class の外」という同じ根拠に立つのであって、一方が他方の非対称を解消したわけではない (レビュー N-2)。
- **`security/CONTROL_MAPPING.md` SI-00 行 (b)**: 「the application-plane role (`r2dbsvc_api`) has no grant at all on `control_credentials`/`control_audit`」という主張は本フェーズ後も**真のまま**である (D-1 は新テーブルにのみ INSERT を足し、`control_audit` には触れない) が、「registry schema 全体に一切の書込権限を持たない」という含意で読まれ得るため、`application_audit` への INSERT-only を明示的に併記する。MitateDB 側の対応テスト (`test_application_plane_role_has_no_privilege_on_control_audit`) は**そのまま緑であり続ける**べきで、緩めてはならない。
- **`conformance-tests/CONDITIONS.md` の C-09 行と C-11 行**: C-09 の「not yet executable (common suite) — peer-local evidence only」を executable 化後の実態へ、C-11 の `AuditResult`/`AuditQueryRequest` zero-coverage 記述を実被覆へ更新する。既存行の書式 (どの adapter が PROVIDED でどれが absent かを正直に列挙する) を踏襲する。
- **配備ドキュメントの構成図とパス一覧** (レビュー m-8): `MitateDB-api/docs/cloud-run-cloud-sql.md` の構成図は control サービスを `main:app /control/v1/*` と記述しており、D-5 で `/v1/audit/query` が加わると陳腐化する。r2db 側の対応する配備ドキュメントも同様。あわせて「control ホストのエッジポリシーは `/control/v1/*` だけでなく `/v1/audit/query` も覆わねばならない」を明記する。
- **両 peer の runbook**: (i) 新 migration の適用手順 (適用順・実行 role・環境変数名)、(ii) reader role の DSN 設定 (`R2DB_AUDIT_DSN` / `MITATEDB_AUDIT_DSN`) と未設定時に `audit_query` が `unavailable` 宣言のままになること、(iii) **platform DB の容量監視** (M-5 の第 3 段。1 行サイズ上限 × 行数上限を根拠にした閾値設計。**行数上限の算出には最大インスタンス数 M を織り込む** — 合体も buffer もプロセスローカルなので、実効上限は「窓数 × M」および「buffer 容量 × M」である、レビュー N-4)、(iii-b) **監査書込み接続の `statement_timeout` / `idle_in_transaction_session_timeout` の設定値と、そこから導出される `visibility_lag_ms` の関係** (N-3。値を変えたら宣言も変わる)、(iv) **監査ポーリングと rate window の関係** (M-8 / P4-D4 項目 8。窓は `audit_requests_per_minute` として分離されるため break-glass との競合は構造的に解消されるが、推奨ポーリング間隔 = 宣言された `visibility_lag_ms` 以上、および両窓のサイズ設計は runbook の管轄)、(v) **platform DB 障害時の独立した読み取り路は帯域外 CLI のみ**であること (m-6)、(vi) D-11 の保持期間・剪定の操作手順。

### 9.4 WP 実装記録 (v1.5、WP-4 起草)

体裁は `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §10 に倣う。基準値はフェーズ3.5 完了時点の **1292 passed / 0 failed / 0 skipped**。

**集計行の出所 (記録)**: 下表の集計行はすべて**監督がリポジトリルートで単独実行して得た実測値**であり (作業指示書 §4 の完了ゲート規律)、各コミット本文に記載されている。本記録 (WP-4) はそれを転記したものであって、起草時に再実行して得た値ではない — 再現するには同じ単独実行手順を踏む必要がある。

| WP | コミット | 集計行 (単独実行) |
|---|---|---|
| WP-0 (設計 v1.4 + 作業指示書 v1.2) | `3ec95cf` (merge `b99368d`) | 1292 passed / 0 failed / 0 skipped (基準値確認のみ) |
| WP-1 (契約 1.4.0 + C-09/C-11 + port v1.8) | `09233dd` (merge `a107f6b`) | **1331** passed / 0 / 0 / **xfailed 1** |
| WP-2(a) (r2db 耐久 sink) | `2c5288a` (merge `1e643e9`) | **1370** passed / 0 / 0 / xfailed 1 |
| WP-2(b) (r2db `audit_query` + 1.4.0 flip) | `a1a1409` (merge `13c899a`) | **1419** passed / 0 / 0 / xfailed 1 |
| WP-3(a) (MitateDB 耐久 sink) | `54318c6` (merge `6df2713`) | **1485** passed / 0 / 0 / xfailed 1 |
| follow-up 1 (r2db flush swap-out) | `411c034` (merge `afd24ef`) | **1487** passed / 0 / 0 / xfailed 1 |
| WP-3(b) (MitateDB `audit_query` + 1.4.0 flip + guard 解除) + follow-up 2 (r2db テスト補強 `cb9f7a3`) | `a3571dc` / `cb9f7a3` (merge `e60eb1e`) | **1526** passed / 0 failed / 0 skipped / **xfailed 0** |

xfailed は WP-1 で登録した全体 vacuity guard 1 本であり、WP-3(b) の flip コミットが `xfail(strict=True)` を外して 0 に戻した (作業指示書 §4 の想定どおり)。

#### 9.4.1 WP-1 — 契約 1.4.0 + 共通 suite (`09233dd`)

契約 8 件を単一 1.4.0 束として出荷し、`spec/CCR_DISPOSITION.md` に従属判断 9 を記録。項目 7 (endpoint 分類) は**移動ではなく `endpoints.audit_query` 保持 + `deprecation_note` + `control_endpoints.audit_query` 新設**として実装され、監査の再帰 additive 比較 (キー削除 0 / 型変更 0 / enum・required・閉鎖宣言の退行 0、スカラー変更 3 件のみ) で additive 性を機械確認。port v1.8 (`audit_query` / `flush_audit_buffer` / `audit_visibility_lag_ms`) と `SurfaceAbsent` の意味拡張。

レビュー **0 blocker / 1 major / 3 medium / 3 low**、全数反映: F-1 (major) = C-09 vector 1 の相関キーが契約・設計・両 peer の実 emitter のいずれとも矛盾 / F-2 = `version_binding` 1.4.0 節の「Two」が自身の 3 項目と矛盾 / F-3 = 正本設計 §8.4 が出荷挙動と反対の記述のまま (→ 本文書 §8.4 に訂正註を追加) / F-4 = `AuditResult` の閉鎖を固定する positive control 欠落。変異 6 本 (guard の `strict` 除去・版数の文字列比較化・偽 `enabled` 宣言・全体 guard の弱化・閉鎖検査除去・packaged copy 1 バイト改変) すべて期待どおり。受け入れ監査 13/13 充足。

**受理境界 (この WP で「固定しない」と決めた点)**: C-09 vector 4 は共通 port ABC の**自己言及的な構造検査**であり、adapter ごとに分岐しない — 「peer 側に監査変更面が無い」ことの証拠ではない。共通 suite に置ける形の限界として開示し、peer 観測は各 peer の suite の管轄とした (`conformance-tests/CONDITIONS.md` C-09 行に明記)。

#### 9.4.2 WP-2(a) — r2db 耐久 sink (`2c5288a`)

migration 0007、`ApplicationAuditHook` を `StorageBackend.transact`/`apply_schema` の commit 前に露出、リクエスト構造による振り分け、合体 denial、bounded buffer + alert、両 composition root の timeout 配線。宣言は不変 (1.3.0 / `audit_query` unavailable)。

レビュー **1 blocker / 3 major / 3 minor**、全数反映。B-1 (blocker) = 1 操作が耐久 3 行を生む (D-10 禁止条件 (ii) の破れ) — 監査パイプライン自身の失敗が生む `SERVICE_UNAVAILABLE` が新規 denial として再入していた。**これが P4-D7 (包含列挙) の決定根拠**である。B-2 = 合体初回 INSERT が並行時に fail-closed でない / M-1 = composition root の timeout 配線が無テスト (変異 2 本が生存) / M-2 = buffer に閾値 flush 契機が無い。実装者の裁量判断 3 件 (J-1 = 合体 2 行、J-2 = 除外列挙の読み、J-3 = flush 失敗も alert) はレビューで設計原文と突き合わされ、**J-1/J-3 は追認、J-2 は包含列挙へ是正**された (→ P4-D6/D7/D9)。変異 8 本中 6 本が期待どおり赤、2 本 (timeout 配線削除) が生存し M-1 の根拠となった。受け入れ監査はさらに 3 ラウンド回り、major 2 件 (二重計上・alert 行の無制限化) と requeue/overwrite 経路を閉じた。

**運用上の事故 (記録)**: 変異復元時に backup を取り忘れ、fallback の `git checkout` が実装者の変更を一度消した。レビュー開始時に採取した `git diff` 全文から逐語復元し `git diff --stat` の完全一致を確認して復旧。作業指示書 §6-10 の「変異注入は scratchpad へ復元する (`git checkout` は使わない)」はこの事故の後、以後の全 WP で例外なく守られている。

#### 9.4.3 WP-2(b) — r2db `audit_query` + 1.4.0 flip (`a1a1409`)

control ホストの 2 パス、`r2dbsvc_auditreader` による UNION 読み、不透明 keyset cursor、`audit_requests_per_minute` 専用窓、`control_capabilities.audit_query` 宣言、両 plane の `contract_version` 1.4.0 flip。

レビュー **7 major / 7 minor**、全数反映: B-1 = 合体集約行が `count = 1` を出す (→ **P4-D8**) / B-2 = 1.4.0 宣言に対し `audit_events` 予約が不足 (→ **P4-D10**) / M-3 = 宣言語彙の AST 走査が 6 emit サイトを見ていない / M-4 = 「control 窓を消費しない」が HTTP 層で無固定 / M-5 = audit 窓の pre-auth 性が無固定 / M-6 = 全順序キーの `plane` が無固定 / M-7 = HTTP conformance adapter の書き手に timeout が無い。変異 11 本中 7 本が赤、**4 本の生存がそのまま M-3〜M-6 の 4 major になった** (変異注入が指摘を生成した唯一の WP)。受け入れ監査 2 ラウンドで 3 件の証拠ギャップ (遅延 tx テストの load-bearing 化、AST の append 形、予約の全位置化) を閉塞。

**発注書スコープ外だが完了条件に必須だった作業 (記録)**: HTTP conformance adapter への migration 0007 bootstrap と実 PostgreSQL の durable_audit 配線は「変更対象」に列挙されていなかったが、完了条件 23 (2 adapter が C-09/C-11 の PROVIDED 分岐を実行する) を満たすには不可欠だった。発注書の変更対象一覧は完了条件の閉包になっていない、という一般的教訓として記録する。

**受理境界**: (i) `coalescing_window_ms` の宣言は control プロセスの単一定数から作られ、data-plane 側の `DataService(denial_coalesce_window_s=...)` 上書きとは機械的に結ばれていない (runbook に「変えるなら宣言も変わる」として記載) / (ii) `visibility_lag_ms` の 2 プロセス整合も同型に無強制 (§11 台帳 + CONTROL_MAPPING SI-14 点 12) / (iii) M-6 の実ベクタは「跨表**同一** event_id」ではない (順序キーの `plane` は固定されたが、衝突そのものは合成していない) / (iv) 契約無条件義務 (b) の「unavailable × audit role」組合せの直接テストは無い。

#### 9.4.4 WP-3(a) — MitateDB 耐久 sink (`54318c6`)

migration 0005 (Cloud SQL 実配備への逐条互換性論証つき)、13 列 emitter の新設 (6 フィールド sink の丸めを耐久経路から排除)、`commit()` の try 内移設 (SQLite は DDL を明示的擬似 tx 化)、P4-D5 の emit サイト新設、`request_id` の HTTP → auth/cell/backend 縦断、swap-out flush。

レビュー **1 blocker / 4 major / 3 minor**、全数反映: B-1 (blocker) = 未認証の client 申告 `credential_id` が耐久行と合体キーに入る (**攻撃者が合体キーを自由に散らせる = 有界化の破れ**) / B-2 = 並行 flush が buffer 類の耐久行を二重に書く — **両 peer 共通の欠陥として発見され、r2db へ対称に適用されたのが follow-up `411c034`** (→ P4-D12) / M-1 = WP-2(a) の M-1 (timeout 配線の無テスト) が対称実装で**再発** / M-2 = 耐久行の `request_id` が全件 `None` で D-2 の識別規則が成立しない / M-3 = `_require_data` の `FORBIDDEN` が D-3 経路に載っていない。変異 17 本中 15 本が赤、2 本が対照・生存。

**「対称実装は前 WP の裁定を発注時点で織り込む」の効き方 (記録)**: 発注書 §2 の教訓どおり WP-2 の裁定は発注に織り込まれたが、**M-1 は再発した** — 織り込みは「同じ指摘を出さない」ことを保証しない。一方 B-2 は逆向きに働き、後発 peer のレビューが先行 peer の潜在欠陥を見つけて follow-up を生んだ。対称実装の価値は指摘数の減少ではなく**両向きの照合**にある。

#### 9.4.5 follow-up 1 — r2db flush swap-out (`411c034`)

`_AuditBuffer.flush()` の snapshot + 後置削除を swap-out へ。失敗時は保持バッチを先頭へ戻した上で容量まで切り詰め、**切り詰め分のみを dropped / alert / 固定ログ行に計上**し、`failing` フラグは buffer が排出されたときのみ解除 (→ P4-D12、本文書 D-4 に v1.5 で追記)。決定的な並行テスト 2 本 (二重書込み / 失敗 flush 下の容量)。読み取り専用レビュー 1 往復 (blocker 1 件をパッチ内で修正)。

#### 9.4.6 WP-3(b) — MitateDB `audit_query` + 1.4.0 flip + guard 解除 (`a3571dc`)

WP-2(b) の対称実装 + 全体 vacuity guard の `xfail` 削除。application credential の副作用なし probe (`CredentialStore.peek`、→ P4-D14)、HTTP adapter の bearer 二重前置バグの修正、共通 vector 1 の `target_kind` 候補集合の開示的拡張。

レビュー **0 blocker / 4 major / 5 minor**、全数反映。**4 major はすべて「テストの空振り」** — A/B = 順序・cursor の `plane` を固定しているはずのテストが実際には固定していない (probe で「素で緑・変異で赤」を作って実装は正・テストが空振りと確定) / C = `visibility_lag_ms` の**適用**を固定するテストが 1 本も無い / D = 共通テストの `_LIKELY_DESTRUCTIVE_OPERATIONS` への `"transact"` 追加が不要かつ未開示。変異 29 本 (うち無効変異 2 本、probe 4 本) を実行し、生存 7 本がそのまま指摘 A/B/C/D/E/G/I になった。受け入れ監査は独立に 9 本の変異を実行し 8 本赤、1 本 (`http.py` の `event_class` literal) が緑のまま残り、下記の受理境界となった。

**受理境界 (WP-3(b) の受け入れ監査が「未充足/部分充足」として明示したもの)**:
1. **`event_class` AST 走査のファイル列挙漏れを機械検出する手段が無い** — `ops.py` は閉じたが、`http.py` の実 emit サイトは走査の外で変異が生存する。現時点の宣言は真 (union は実 literal と一致) なので契約義務違反ではないが、性質 5 の回帰ガードとしては片肺である。**r2db 側も同型**であり、閉じるなら両 peer 同時が筋。
2. **`peek()` の非監査性は変異で固定されたが、呼び出し元の限定は台帳記録のみ** — 監査時点では機械的固定が無かった。P4-D14 として裁定され、AST 走査テストで固定された。
3. **composition root が AUDIT DSN 未設定時に `unavailable` を宣言することの peer-local テスト**が MitateDB に無い (service 層のみ固定)。r2db は follow-up `cb9f7a3` でこれを閉じたため、**現時点では非対称**である。
4. WP-2(b) 完了条件 15 後半 (`..._does_not_import_the_control_credential_store`) の同名対応物が MitateDB に無い (別形の `test_main.py` のテストが同じ分離を固定している)。

#### 9.4.7 follow-up 2 — r2db テスト補強 (`cb9f7a3`)

WP-3(b) 受け入れ監査の対称適用 (テストのみ、製品コード無変更): `event_class` の AST 走査を `src/r2db_api/*.py` 全体へ (手書きファイル列挙を廃止、`ops.py` の直接 `control_audit` 書込みと bare-name 呼び出しを包含)、プロセス内変異による load-bearing 証明と構造被覆テスト、`build_control_app` が `R2DB_AUDIT_DSN` の有無で `audit_query` の宣言を切り替えることを実 HTTP + 実 platform DB で固定。上記受理境界 1 の残余 (`http.py` 相当の emit サイト) は**両 peer とも未閉塞**であり §11 台帳へ起票した。

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

- **`audit_query` の application credential probe が既存/失効済みの識別 oracle になっている** (WP-2(b) レビュー m-3、供覧裁定 2026-09-03、台帳記録)。`ControlPlaneService.audit_query` は D-5 の要求どおり application credential を FORBIDDEN で拒否するため、secret を先に `authenticate_application` で照合する (D-5 実装ノート参照)。この照合自体は SI-00 の分離を壊さない (control プロセスは元々 `ControlAuthority` 経由でアプリ credential store を保持している) が、control ホストに新しい pre-auth の検証面ができたことは事実である: 「この secret は実在する有効な application credential か」を 403 (FORBIDDEN・実在) と 401 (AUTH_INVALID・不在または失効) の応答差で答えられるようになり、`audit_requests_per_minute` の枠内 (既定 60/min) で連打可能。失敗側 (401) は `control_audit` に `AUTH_INVALID` 行が残るため沈黙はしない。加えて、**失効済み/無効化済みの application credential は FORBIDDEN ではなく AUTH_INVALID (401) になる** — `authenticate_application` は `FoundationError` (revoked/disabled 含む) を一律 `None` に潰して通常の control 認証へフォールスルーするため、「application credential は FORBIDDEN」という宣言は有効な credential にしか成り立たない。契約上はどちらも denial であり違反ではないが、運用上の含意 (secret 存在の外部可観測性がわずかに増える) を記録する。対応不要 (WP-2(b) レビューの結論)、次回見直し時の参照用。
- **in-memory 読み手と Postgres 読み手の全順序は collation 依存である** (WP-2(b) レビュー m-6、記録のみ)。`InMemoryAuditQueryStore` は Python の codepoint 順、`PostgresAuditQueryStore` は DB の collation 順で `plane`/`event_id::text` を比較する。`plane` の 2 値 (`"application"`/`"control"`) と uuid hex 表記の `event_id` の範囲では両者は一致するが、この一致は本フェーズで明示的に検証・記録されたものであり、将来 `event_id` の文字種が広がった場合は再検証を要する。

- **`visibility_lag_ms` は control プロセスの env のみから導出され、application-plane 書き手は別プロセスである** (WP-2(b) レビュー §4-D、記録のみ)。`control_main.assemble_control_stack` は自プロセスの `R2DB_AUDIT_STATEMENT_TIMEOUT_MS`/`R2DB_AUDIT_IDLE_TIMEOUT_MS` から lag を導出するが、`application_audit` の書き手接続は `r2db_api.main` という別プロセスで、同名の env 変数を独立に読む。両プロセスが同じ env 名・同じ既定定数 (両方 5000ms) を読む構造で運用上は一致するが、機構的な強制も宣言側での検証も無い。runbook §15 に前提として明記済み。CONTROL_MAPPING への正式反映は WP-4 スコープ。**(v1.6 追記) この 2 プロセス整合を機構的に強制する案は、フェーズ4 台帳消化 (`docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md`) の範囲外であり、依頼者判断待ちである — 選択肢と監督推奨は §11.2 Q4 に整理した。**

- **`auth.CredentialStore.peek()` は「認証はするが監査を出さない」公開メソッドである** (WP-3(b)
  レビュー指摘 G、供覧裁定 2026-09-03、台帳記録)。MitateDB の in-process conformance adapter
  (`_ReconciledControlBackend.authenticate_application`) は control-plane 専用の
  `InMemoryCredentialRegistry`/`PostgresCredentialRegistry` を持たず、application-plane の実
  `auth.CredentialStore` を再利用する既存アーキテクチャのため、`audit_query` の application
  credential probe をここに実装するには非監査の読み取り専用メソッドが必要だった (`authenticate()`
  を再利用すると、control credential で `audit_query` を呼ぶたびに application-plane 側へ
  スプリアスな `AUTH_INVALID` denial 行が durably 記録される — 実測済み、
  `test_inprocess_audit_query_control_credential_probe_never_durably_records_a_spurious_denial`)。
  副作用点検: 監査を一切書かない・`_lock` 内読み取りのみ・戻り値は `Principal` か `None` の 2 値の
  み・例外を投げない・タイミング差を `_DUMMY_DIGEST` で潰している。SI-10 のオラクル性は
  `authenticate()` を超えて増えていない (成否 2 値のみを返す点は同じ、WP-2(b) 台帳が既に記録済みの
  application credential probe オラクルより強いものは足していない)。懸念として残るのは、
  製品コード `auth.py` に「非監査の認証面」が増えたこと自体であり、現在の呼び出し元は
  conformance adapter 1 箇所のみ (grep 確認済み) だが、将来の誤用が SI-14 の「denial は必ず
  耐久記録」を静かに破りうる。**監督裁定 (2026-09-03)**: 非監査の認証面は adapter 専用に限定し、
  呼び出し元をテストで固定する — `src/mitatedb_api` パッケージ自身 (`peek()` の定義箇所である
  `auth.py` 自体を含む) の内部から `.peek(` を呼ぶ箇所が一切無いことを AST 走査で固定する
  (`test_credential_store_peek_has_no_caller_inside_src_mitatedb_api`,
  `MitateDB-api/tests/test_control_plane_credential_store_reconciliation.py`) — 唯一の正当な
  呼び出し元は conformance adapter (`src/mitatedb_api` の外) のみである、という設計上の境界を
  機械的に強制する。

### 11.1 WP-4 起票分 (2026-09-03。起票時点では「すべて本フェーズでは扱わない」と裁定済み)

**v1.6 追記 (2026-09-03、フェーズ4 台帳消化 `docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md` v1.5)**。起票後、**共通契約 (`spec/`) を一切変えずに実装・テスト・記録だけで閉じられる項目**を両 peer 対称に消化した。各項目の**先頭に現在の状態を付す** — 状態の無い項目は無い。**契約変更を要する項目・挙動非対称の設計判断は範囲外**であり、依頼者判断待ちとして **§11.2** に整理した (「範囲外」は「対応不要」ではない)。起票文そのものは**当時の記述として保存**し、実態と食い違う部分は各項目内で名指しして訂正する。

| 項目 | 状態 |
|---|---|
| L4-1 | **CLOSED** (2026-09-04、フェーズ5 WP-1〜WP-3、契約 1.5.0 / 従属判断 10 項目 1) — **両 peer 分が揃って初めて CLOSED である**。r2db 側 = WP-2 `3fd72ad`、MitateDB 側 = WP-3 `98d2010` (実装 `3f2da59`) で両 peer が揃った |
| L4-2 | **CLOSED** (2026-09-04、フェーズ5 WP-1 `d7a5ffd`、契約 1.4.0 義務 (b) の同ラベル補筆 / 従属判断 10 項目 2) |
| L4-3 | **CLOSED** (2026-09-03、P4-D15、WP-B2) |
| L4-4 | **CLOSED** (2026-09-04、フェーズ5 WP-4、Q3 = 案 A、MitateDB の受理レンジ上限撤廃。契約不変) |
| L4-5 | **CLOSED** (2026-09-03、P4-D16 v3、WP-B1) |
| L4-6 | **CLOSED** (2026-09-03、P4-D17、WP-B3) |
| L4-7 | **(i)(ii) CLOSED** (2026-09-03、WP-B3) / **(iii) CLOSED** (2026-09-04、フェーズ5 WP-4、L4-4 と同一の判断) |
| L4-8 | **据え置き (射程明示、2026-09-03、P4-D18)** — **CLOSED ではない** |
| L4-9 | **RESOLVED** — 起票時点で既に解消済みだった (WP-1 `09233dd`) |
| L4-10 (新規) | **起票 → CLOSED** (2026-09-03、WP-B3) |
| L4-11 (新規) | **起票 → CLOSED** (2026-09-03、WP-B3 追加項目) |
| L4-12 (新規) | **記録のみ** (実機未検証) |
| L4-13 (新規) | **OPEN (記録のみ)** — data-plane 環境の control-credential pepper 参照が peer 非対称。判断は次回 |

- **L4-1 `operation` / `target_kind` の語彙が宣言されていない (契約 1.5.0 候補)**。**状態: CLOSED (2026-09-04、フェーズ5 WP-1〜WP-3、契約 1.5.0 / 従属判断 10 項目 1)。閉じ方 (現在の実態)**: 依頼者が 2026-09-03 に Q1 を**案 A (宣言化)** で裁定し、Q2 と**一括で契約 1.5.0** として出荷した (実施設計 `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md`、実施記録は同 §10)。**したがって「どちらのフィールドも `capabilities.audit_query` の宣言キー集合に含まれない」「この相関は宣言と機械的に結ばれていない」という起票時の記述はもはや真ではない。** 契約 1.5.0 は `capabilities().audit_query` に **`operations` / `target_kinds`** の 2 キーを条件付き義務 (`audit_query` が `unavailable` 以外のときのみ) として導入し、契約に enum は置かない (D-7 と同じ declare-the-hazard)。両 peer は自分の語彙を宣言する — **r2db は `operations` 27 語 / `target_kinds` 5 語** (WP-2 `3fd72ad`)、**MitateDB は `operations` 29 語 / `target_kinds` 5 語** (WP-3 `98d2010`)。MitateDB 側の宣言は **control 半分 (`audit_query.py`) + application 半分 (`application_audit.py`) の 2 モジュールの和**であり、スナップショットテストは片半分ではなく公開和を pin する。**両 peer が 1.5.0 を宣言したことにより、共通 suite の全体 vacuity guard `test_c09_every_control_surface_adapter_declares_1_5_0` の `xfail` は WP-3 の同一差分で撤去され** (guard 本体は無改変)、**1.5.0 条件付きの宣言整合 vector 3 本は 4 plug 全数で分岐に入り、各 plug で観測イベント 1 件以上を伴って load-bearing になった**。**共通 suite の手書き候補集合は廃止した** (`_LIKELY_DESTRUCTIVE_OPERATIONS` / `_LIKELY_DESTRUCTIVE_TARGET_KINDS` は `grep -rn conformance-tests` で 0 行)。**証拠**: 共通 = `conformance-tests/test_c09_audit_evidence.py::test_c09_declaration_agreement_operation`、`::test_c09_declaration_agreement_target_kind`、`::test_c09_declaration_agreement_event_class` (3 フィールド同型。いずれも `_require_nonvacuous_provided` で観測 1 件以上を precondition にする)、`::test_c09_every_control_surface_adapter_declares_1_5_0` (全体 vacuity guard)。peer-local = 両 peer 同名の `test_declared_operations_cover_every_emittable_operation` / `test_declared_target_kinds_cover_every_emittable_target_kind` ((e) 等式 `U == D ∪ N` かつ `D ∩ N == ∅`)、`test_declared_audit_operations_change_only_deliberately` / `test_declared_audit_target_kinds_change_only_deliberately` (宣言スナップショット)、`test_scanner_is_parameterized_over_exactly_these_three_fields` (走査対象フィールド集合の pin)、いずれも `r2db-api/tests/test_audit_query.py` / `MitateDB-api/tests/test_audit_query.py`。**残る限界 (閉じていない部分、明示)**: 共通 suite が見るのは「返された値 ⊆ 宣言」だけであり、**宣言の真実性の逆向き半分 (宣言にあるが `audit_query` が決して返さない語彙) は共通 suite の射程外**である — peer-local の (e) 等式と N の根拠だけが担う (`conformance-tests/CONDITIONS.md` C-09 行に開示)。**D→N 降格をスナップショットだけが検出する**という L4-11 と同型の限界が 2 フィールドへ拡大したことは、フェーズ5 設計 §11 の **L5-1** として起票した。以下は起票時の記述である。共通テスト C-09 vector 1 は、耐久行を「破壊的操作の行」と同定するために `operation` の候補集合 `{delete, mutate}` と `target_kind` の候補集合 `{entity, collection}` を**手で列挙**している。どちらのフィールドも `capabilities.audit_query` の宣言キー集合に含まれないため、この相関は宣言と機械的に結ばれておらず、peer が語彙を変えても共通 suite は気付かない。`event_class` が D-7 で「宣言される語彙」になったのと同じ扱いを `operation`/`target_kind` にも与えれば C-17 系で機械固定できるが、契約変更 (1.5.0) を要する。共通語彙へ統一する案 (`entity` に寄せる) は両 peer の既存 `control_audit` 行と出荷済み語彙を破るため D-7 と衝突し、採れない。(WP-1 受け入れ監査 疑義 3/4、WP-3(b) 受け入れ監査 疑義 2)
- **L4-2 契約 1.4.0 無条件義務 (b) の適用範囲 (両 peer 同型、契約文言の解釈問題)**。**状態: CLOSED (2026-09-04、フェーズ5 WP-1 `d7a5ffd`、契約 1.4.0 義務 (b) の同ラベル補筆 / 従属判断 10 項目 2)。閉じ方 (現在の実態)**: 依頼者が 2026-09-03 に Q2 を**案 A (文言を締める)** で裁定し、Q1 と一括で契約 1.5.0 の束として出荷した。ただし**置き方は「Since 1.5.0」の新義務ではなく、1.4.0 無条件義務 (b) 本文への同ラベル補筆**である (契約自身の「added by a later revision of this document still under that same label」条項に依る。設計 `PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §3 D-2)。補筆は義務 (b) の受理対象を **control surface の `audit_query` control endpoint (正典パスと control ホスト上の alias)** に scoping し、**control-credential store を持たないホストは提示された control/audit credential を未知の credential として `AUTH_INVALID` で拒否してよい**とする — **許容形であり義務形ではなく、`forwarded` の禁止も作っていない**ため、`versioning.control_discovery` の co-hosting 容認を狭めず、転送で条件付き義務 (5) を満たす分離配備を遡って非適合にしない。**したがって「義務 (b) をどちらに読むかで適否が分かれる」「この経路を実測するテストは共通・peer とも存在しない」という起票時の記述はもはや真ではない。** **証拠**: 共通 = `conformance-tests/test_c09_audit_evidence.py::test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted` (**xfail なしの無条件登録**、4 plug 全数。期待は「`AUTH_INVALID` による拒否」または「control surface と同居するホストでは `audit_query` の提供」のいずれかであり、`CAPABILITY_UNSUPPORTED` / `FORBIDDEN` / 5xx は不適合)、`conformance-tests/test_contract.py::test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose` (依頼者確定文の逐語ピン)。port は **v1.9** へ上がり、`audit_query_on_data_plane_host` と `control_surface_cohosted_with_data_plane` の**2 本**が抽象メソッドとして加わった (`docs/design/CONFORMANCE_ADAPTER_V1.md` §19)。**残る限界 (閉じていない部分、明示)**: この vector の `provided` 分岐は**同居しているかどうかを adapter の申告で信じる** — 申告を独立に検証する機構は無い (現時点では 4 plug とも同居を `False` と宣言するため、実際には常に `AUTH_INVALID` 側で判定されている)。`CONDITIONS.md` C-09 行に開示済みで、フェーズ5 設計 §11 の **L5-4** として起票した。以下は起票時の記述である。 data-plane ホストは `control_plane: enabled` を宣言しつつ control credential store を持たないため、そのホストの `/v1/audit/query` alias に control/audit credential を出すと `AUTH_INVALID` になる。義務 (b) を「control surface の `audit_query` control endpoint に掛かる」と読めば適合、「capabilities 文書を出すそのホストに掛かる」と読めば不適合。**現在は前者の読みで両 peer とも受理されている**。この経路 (control credential × data ホスト) を実測する共通/peer テストは両 peer とも存在しない。次回の契約見直しで文言を締めるか、テストを足すかを決める。(WP-3(b) 受け入れ監査 疑義 1。`security/CONTROL_MAPPING.md` の SI-00/SI-14 行にも記録済み)
- **L4-3 `failing` フラグの貼り付き (両 peer、minor)**。**状態: CLOSED (2026-09-03、P4-D15、WP-B2、両 peer 同型)。**
  - **起票時の記述 (当時の記録として保存)**: buffer flush の成功時に `failing` を解除する条件が「buffer が空になったとき」限定であるため、継続負荷下では sink が実際に回復した後もフラグが立ったままになり、alert 行の再発火間隔が最大 60s のバックオフ上限まで開き得る。**証拠は失われない** (欠落数は累積し、最終的な alert 行の `count` に載る) が、運用者が「メッセージが途切れた = 回復した」と読む危険がある。「構造的に直すなら解除条件を『flush が 1 回成功したとき』へ変える案があるが、それは alert の発火頻度を上げる方向であり本フェーズでは触らない」と書いていた。
  - **閉じ方 (現在の実態)**: 起票文が挙げていたその案を **P4-D15 として採った**。解除条件は「**成功 flush の完了**」であり、**buffer の残量を一切参照しない** — `failing` は「最後に完了した flush 試行の結果」を表す。したがって**「buffer が空になったとき」「buffer が完全に排出されるまでフラグが残る」という記述はもはや真ではない**。並行 flush の競合は完了順序の意味論で吸収する (後から完了した失敗 flush が再度 `True` を立てる)。起票文が懸念した「alert の発火頻度が上がる」は**意図した代償として受け入れた** — フラッピング時の alert レートが「60s に 1 行」から「`alert_min_interval_s` に 1 行」(r2db 既定 2s) へ上がり得るが、宣言上の上限「flush 間隔あたり最大 1 行」は破れない。
  - **証拠**: 両 peer 同名の `test_a_successful_flush_clears_the_failing_flag_even_when_the_buffer_is_not_empty` (フラグ解除と alert バックオフの床への復帰の両方を固定。変更前のコードでは赤になることを実測済み) と `test_a_failing_flush_that_completes_after_a_successful_one_sets_the_flag_again` (完了順序の回帰ガード。成功が先に完了し失敗が後に完了する順序を実際に強制する)、いずれも `r2db-api/tests/test_application_audit.py` / `MitateDB-api/tests/test_application_audit.py`。既存の `test_alert_row_rate_is_bounded_to_at_most_one_per_flush_interval` は緑のまま (この上限が P4-D15 の前提である)。
  - **運用側**: 両 peer の runbook の "Known sharpness" 段落は WP-B2 で書き換え済み。**「回復は当該ペアの回復メッセージで読む」という運用指示は据え置く** — 回復メッセージがより早く出るようになっただけであり、「メッセージが途切れた = 回復した」と読んではならないという規律自体は変わらない。5 種の固定メッセージ表・状態遷移でのみ発火する規律・容量算式は無変更。
  - **他文書の旧記述について**: `docs/work-orders/HANDOVER_20260903_FABLE.md` §4-3 の L4-3 記述 (解除条件が「buffer が空になったとき」限定である旨) は**起票時点のもの**であり、日付付きの引き継ぎ記録として**編集しない** (監督裁定 2026-09-03)。現在の意味論は本項目と §5.1 P4-D15 が正本である。
- **L4-4 `audit_requests_per_minute` の既定 60、および受理レンジの peer 非対称**。**状態: CLOSED (2026-09-04、フェーズ5 WP-4、Q3 = 案 A)。L4-7(iii) と同一の設計判断である。閉じ方 (現在の実態)**: 依頼者が 2026-09-03 に Q3 を**案 A (MitateDB 側の上限撤廃)** で裁定した。実施設計は `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` **§3 D-3** (確定形・却下案はここが正本)、実施は **WP-4** (契約は不変、`spec/` 配下は 1 バイトも変更していない)。**したがって「MitateDB は既存 3 クラスと同じ `[1, 200]` を全 request-count クラスに掛けているため、200 超はコード変更になる」という起票時の記述はもはや真ではない** — `MitateDB-api/src/mitatedb_api/control_plane.py` の `ControlPlaneLimits.__post_init__` は 4 クラスすべてで「正の整数であること」しか検査せず**上限を持たない** (r2db `ControlPlaneLimits.__post_init__`、`r2db-api/src/r2db_api/limits.py` と対称)。**受け入れた代償**: 上限は誤設定に対する防波堤でもあり、外せばその防波堤は無くなる (`audit_requests_per_minute` に桁違いの値を置いた配備を製品コードは止めない) — 依頼者設計原則 3「制約で回避しない」に沿って意図的に引き受けた代償であり、両 peer の runbook (`MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15) と `security/CONTROL_MAPPING.md` SI-08 行に運用者責任として記録した。関係検査 (`control_requests_per_minute > applications + 2 × credentials_per_application + 67`) は独立に残る。**証拠**: `MitateDB-api/tests/test_control_plane_service.py::test_limits_reject_out_of_range_values` (4 クラスの下限のみ、`match=` でエラー文言 `must be a positive integer` を逐語に見る)、`::test_limits_accept_generous_values_beyond_the_former_ceiling` (r2db `_GENEROUS_LIMITS` と同型、`control_requests_per_minute=100_000` の構築・宣言)、`::test_limits_reject_control_requests_per_minute_too_close_to_the_margin` (関係検査が緑のまま)。**残る非対称 (実害なしとして受け入れる)**: `request_bytes` の検査ループ位置 (r2db は共通ループ、MitateDB は別建て) は本 WP の射程外であり、そのまま残る (`docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §1.4 の該当注記)。以下は起票時の記述である。既定 60 は両 peer 共通で、「宣言 `visibility_lag_ms` 以上の間隔でポーリングする」前提の監査エージェント約 10 体分に相当する。エージェント数の増加、または障害復旧後の cursor 追い付き (ポーリングではなくページングなので所要リクエストが桁違いに増える) で足りなくなる。**このとき取れる手当てが peer で異なる**: r2db の `ControlPlaneLimits.__post_init__` (`r2db-api/src/r2db_api/limits.py`) は「正の整数であること」しか検査せず**上限を持たない**ため、`R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE` を上げる**設定変更**で済む (peer 自身のテストが 100_000 を構築・宣言している)。MitateDB は既存 3 クラスと同じ `[1, 200]` を全 request-count クラスに掛けているため、200 超は**コード変更**になる。契約は本クラスに数値レンジを宣言していないので双方適合であり、CLAUDE.md の「同じ安全結果を与えるなら platform-specific control は peer 間で異なってよい」に該当する開示済み非対称である (要求される結果 = 窓が pre-auth かつ control 窓と別であること — これは両 peer が満たす)。窓を広げても監査行は増えない (pre-auth のため無認証 flood は行を生まない)。両 peer の runbook に算式と、この非対称を記載済み。(WP-3(b) 受け入れ監査 疑義 3、WP-4 記録レビュー Blocker)
- **L4-5 宣言語彙 AST 走査のファイル列挙漏れ・callee 名キーを機械検出できない (両 peer 同型)**。**状態: CLOSED (2026-09-03、P4-D16 v3、WP-B1、両 peer 同型)。**
  - **起票時の記述 (当時の記録として保存)**: `event_class` の宣言 ⊇ 実 emit を固定する AST 走査は、r2db は follow-up `cb9f7a3` で `src/r2db_api/*.py` 全体へ、MitateDB は WP-3(b) で `src/mitatedb_api` 全体へ広げたが、走査が見ていない emit サイトが将来生じたことを検出する手段が無く (MitateDB の受け入れ監査では `http.py` の実 emit サイトに未宣言 literal を注入する変異が緑で生存した)、性質 5 の回帰ガードとしては片肺だった。
  - **閉じ方 (現在の実態)**: **「走査が見ていない emit サイトを検出する手段は無い」という記述はもはや真ではない。** P4-D16 v3 が両 peer に (a)〜(f) を課した — `rglob` による `src/<pkg>` 全体の再帰列挙 (手書きファイル列挙と callee 名キーの廃止)、全 `Call` に対する**無差別**の literal 規律 (b)、定義側 keyword-only 保証 (c) による位置渡し emit 面の構文的消去、`Dict`/`Subscript` 密輸禁止 (d) と全スコープの `Assign`/`AnnAssign`/`AugAssign` 走査 (d′)、これらで完全列挙できるようになった literal 全集合 **U** に対する **`U == D ∪ N` かつ `D ∩ N == ∅`** の厳密固定 (e)。新しい literal が現れたら実装者は「**宣言する (D へ足す) か、N に名指しで足すか**」を強制される — **黙って見えなくなる経路は無い**。非耐久語彙は**宣言ではなく N に名指しで列挙**した (r2db N = 3 語 `authentication` / `control_failure` / `control_state`、各要素に「耐久表へ届かない根拠」のコメント付き。MitateDB N = ∅)。宣言 `DECLARED_AUDIT_EVENT_CLASSES` は本 WP の前後で不変 (r2db 11 語 / MitateDB 12 語)。
  - **証拠**: 両 peer 同名の 6 本 — `test_every_event_class_keyword_argument_is_a_string_literal` (b)、`test_every_definition_taking_event_class_declares_it_keyword_only` (c)、`test_no_event_class_string_literal_is_smuggled_through_a_dict` (d)、`test_no_event_class_string_literal_is_smuggled_through_an_assignment` (d′)、`test_event_class_forward_exclusion_requires_genuine_parameter_binding` (転送許容が仮引数束縛の実在を要求することの回帰ガード。`with…as`/`except…as`/`match…as`/`import…as`/ネスト定義名/`del`/内包表記/タプル分解といった再束縛形の合成ソースを含む)、`test_declared_event_classes_cover_every_emittable_class` (e)。いずれも `r2db-api/tests/test_audit_query.py` / `MitateDB-api/tests/test_audit_query.py` (MitateDB の同名重複 1 本と r2db の callee 名キー依存テスト 1 本は削除し、走査は 1 本へ統合した)。受け入れ監査は 3 ラウンドを要し、`Attribute` 経由の class/instance 属性 literal 密輸 (M7) と `with…as` 等の再束縛 (M8) がそれぞれ生存 → 修正 → 赤へ反転することを実測している。
  - **残る限界 (閉じていない部分、明示)**: **宣言 D の縮小 (耐久語彙を D から抜いて N へ降格する) は (e) 単体では検出できない** — 下記 **L4-11** として起票した。
- **L4-6 HTTP conformance adapter の書き手 timeout 設定漏れを検出するテストが無い** (両 peer 共通、WP-3(b) レビュー D6)。**状態: CLOSED (2026-09-03、P4-D17、WP-B3、両 peer 同型)。**
  - **起票時の記述 (当時の記録として保存)**: adapter 側の書き手接続から timeout 配線を落とす変異が緑で生存する。peer 本体の composition root については両 peer とも実測テストがある (`security/CONTROL_MAPPING.md` SI-14 行の点 (12) 参照) ので、宣言の真実性は保たれている。
  - **閉じ方 (現在の実態)**: **「adapter の書き手 timeout は無テスト」という記述はもはや真ではない。** P4-D17 のとおり **peer-local テスト**で固定した — HTTP conformance adapter (`r2db-api/conformance/conformance_adapter_r2db_http.py` / `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`) が構築する `PostgresApplicationAuditSink` の書き手接続について、**sink 自身が作る書き手接続**を取り `SHOW statement_timeout` / `SHOW idle_in_transaction_session_timeout` を読む既存 composition-root テストと同じ手法で、**両方**が既定値でない (adapter が渡した値である) ことを実測する。**接続の取り方は peer の sink 構造に従うので同一ではない** — r2db の sink は pool を持ち `_pool.connection()` で借りるが、**MitateDB の `PostgresApplicationAuditSink` は pool を持たず**、`_connect()` (`MitateDB-api/src/mitatedb_api/application_audit.py:295`) が呼ばれるたびに `psycopg.connect(...)` で新しい接続を張り、その場で session timeout を適用する。実測する性質 (両 timeout が adapter の渡した値で効いていること) は同一である。**共通 port には足していない** — `conformance-tests/adapter.py` の port version は **v1.8 のまま**、`docs/design/CONFORMANCE_ADAPTER_V1.md` も無変更である。in-process adapter は in-memory sink であり DSN も接続も持たないため対象外。
  - **証拠**: 両 peer 同名の新規テスト `test_http_conformance_adapter_audit_writer_connection_has_statement_and_idle_timeouts_set` — r2db は `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py`、MitateDB は `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`。adapter の `statement_timeout_ms=` / `idle_in_transaction_session_timeout_ms=` を**片方ずつ**落とす変異で、両方が独立に赤になることを実測済み。
- **L4-7 両 peer 間に残る非対称 3 件**。**状態: (i)(ii) CLOSED (2026-09-03、WP-B3、MitateDB にテストを追加して対称化) / (iii) CLOSED (2026-09-04、フェーズ5 WP-4、Q3 = 案 A。L4-4 と同一の判断。実施設計 `PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §3 D-3、証拠は L4-4 が保持)。** (i)(ii) の閉じ方: (i) `control_main.build_control_app(env)` (実 entry point。低層の `build_control_service` ではない) 経由で「`MITATEDB_AUDIT_DSN` 未設定 → `audit_query.status == "unavailable"`」「設定時 → `unavailable` 以外」の両方を固定する MitateDB 側テストを追加し、r2db の `test_build_control_app_declares_audit_query_status_from_r2db_audit_dsn_env` と対称にした。(ii) data-plane composition root (`MitateDB-api/src/mitatedb_api/main.py`) が control-credential store / control-plane service を**構築も import もしない**ことを固定するテストを、r2db と**同名**で追加した (`test_data_plane_composition_root_does_not_import_the_control_credential_store`)。**判定方式の最終形 = 両 peer とも AST ベース** (監督採用のレビュー差し戻し **M4**、2026-09-03): 起草時の「ソーステキストに禁止識別子が substring として現れないこと」という検査は**上書きされた**。現行は `ast.parse` でソースを解析し、(1) `Import` / `ImportFrom` の module パスと alias 名、(2) `Name.id` / `Attribute.attr` を、peer ごとの**禁止語彙**と突き合わせる — r2db は module `control_plane` + 対応クラス名、MitateDB は module `control_auth` / `control_credential_store_postgres` / `control_plane` + 対応クラス名。module を **import しない**点は変わらない (両 peer とも `main.py` が module-level で `app = build_app()` を実行するため、import 経路に落とすと実 DB 接続や副作用で偽の赤/緑を生む)。**文字列リテラル・コメント中の出現は判定対象外である** — substring 検査からの実質的な変更点はここであり、`ast` の走査対象に入らないためである。**したがって、data-plane が control-credential pepper の env を読んでいる事実 (MitateDB のみ) は本テストでは捕まらない** — その事実は **L4-13** が別途保持する。**証拠**: (i) `MitateDB-api/tests/test_control_main.py::test_build_control_app_declares_audit_query_status_from_mitatedb_audit_dsn_env`、(ii) `MitateDB-api/tests/test_main.py::test_data_plane_composition_root_does_not_import_the_control_credential_store` (r2db 側と同名で計 2 件になる)。**起票文の (i)(ii) の記述 (「r2db にはあるが MitateDB には無い」) はもはや真ではない。** 以下は起票時の記述である。(i) composition root が AUDIT DSN 未設定時に `audit_query: unavailable` を宣言することを固定する peer-local テストは r2db にはある (`test_build_control_app_declares_audit_query_status_from_r2db_audit_dsn_env`) が MitateDB には無い (service 層のみ)。(ii) WP-2(b) 完了条件 15 後半の `..._does_not_import_the_control_credential_store` と同名の対応物が MitateDB に無い (別形のテストが同じ分離を固定してはいる)。(iii) **`audit_requests_per_minute` の受理レンジ** — MitateDB は `[1, 200]`、r2db は上限なし (L4-4)。(i)(ii) はテスト名レベルの非対称にとどまり実害は見えていない。(iii) は挙動の非対称であり、契約が範囲を宣言していない以上どちらも適合だが、運用者から見ると「同じ窓の広げ方が peer で違う」ことになるので、対称化するか (r2db に上限を入れる案は peer 自身の既存テストが 100_000 を構築しているため単独では通らない)、契約側でレンジを宣言するかは次フェーズの判断事項。
- **L4-8 C-09 vector 4 の射程**。**状態: 据え置き (射程明示、2026-09-03、P4-D18)。CLOSED ではない。**
  - **起票時の記述 (当時の記録として保存)**: 「共通 port の ABC に監査変更面が無いことの構造検査であり、**adapter ごとに分岐しない**。port にメソッドを足さない限り恒久的に緑なので、peer 側に監査変更面が生えたときにこの vector は反応しない。`conformance-tests/CONDITIONS.md` の C-09 行に開示済み。peer 観測形へ作り直すか、射程を port 構造保証に限定すると明示するかは未決。」
  - **裁定 (P4-D18)**: **射程を明示して据え置く。** peer 側に監査変更面が無いことは **DB 権限**で担保されている — 書き手 role は `application_audit` に INSERT のみ、reader role は両 audit 表に SELECT のみであり、両 peer に**生の接続 (bare connection) で実測する権限テストが実在する** (§9.2 性質 2、`security/CONTROL_MAPPING.md` SI-14 行)。したがって vector 4 を peer 観測形へ作り直しても**新しい安全結果は得られない**。**CLOSED とは書かない** — 新しい安全結果は生じておらず、peer 観測形への作り直しは将来の判断に残る。
  - **起票文の「adapter ごとに分岐しない」は現物と合っていない (2026-09-03、WP-B4 記録整理時に実測)**: `test_c09_v4_no_audit_mutation_or_deletion_surface_exists` は、adapter 非依存の port-ABC 構造検査 (`_assert_port_abc_has_no_audit_mutation_surface`) を**必ず**通したうえで、**さらに adapter ごとに分岐する** — HTTP 形の adapter (`_control_send` を持つもの) には control ホストの `/v1/audit/query` と `/control/v1/audit/query` の両パスへ `DELETE`/`PUT`/`PATCH` を**実際にワイヤで送って** 2xx が返らないことを確認し、in-process adapter には `control_audit_events()` が実際に読む実オブジェクト (耐久 sink facade / control-plane service facade) を introspect して mutating な名前の公開 callable が無いことを確認する。port-ABC 検査自身の docstring も「necessary but NOT sufficient on its own … this structural check is never the sole basis for that test's own green」と述べている。**それでも P4-D18 の据え置き判断は変わらない** — これらの peer 観測は adapter から見える面 (ワイヤの動詞、Python の公開 callable 名) までしか届かず、**DB レベルの監査変更面には届かない**。そこを担保しているのは上記の DB 権限と両 peer の権限テストであり、vector 4 を作り直しても新しい安全結果が出ないという裁定の根拠はこの事実に依る。
  - **記録**: `conformance-tests/CONDITIONS.md` の C-09 行と `conformance-tests/test_c09_audit_evidence.py::test_c09_v4_no_audit_mutation_or_deletion_surface_exists` の docstring に、同じ射程を記した (両者の文言は食い違わない)。
- **L4-9 vector 1 の新規 event 同定キーが `event_id` 単独**。**状態: RESOLVED — 起票時点で既に解消済みだった。** `conformance-tests/test_c09_audit_evidence.py` の `_event_identity` は **WP-1 (`09233dd`) の時点で cursor → `(plane, event_id)`** を使用しており、下記の起票文は **WP-1 受け入れ監査時点の指摘がそのまま台帳へ残ったもの**で、現物とは合っていなかった。以下は起票時の記述である。本フェーズが出荷した契約自身が「`event_id` は `control_audit`/`application_audit` の UNION では一意でない (だから順序キーに `plane` を入れる)」と述べているのに、共通テストの baseline 差分は `event_id` 単独で新規判定している。実運用の `event_id` 空間 (uuid) では衝突しないため現在は偽陰性を生まないが、契約が明文で否定した一意性に依存している点は `(plane, event_id)` または `cursor` を同定キーにする方が整合する。(WP-1 受け入れ監査 疑義 3)
- **L4-10 `control_main` の `request_bytes` env 未配線 (r2db のみ、peer 非対称)** (新規起票、2026-09-03、フェーズ4 台帳消化)。**状態: 起票 → CLOSED (2026-09-03、WP-B3)。**
  - **起票文**: r2db の `control_main` は control-plane の `request_bytes` 上限を env から配線しておらず、`ControlPlaneLimits` の dataclass 既定 (1_048_576) 固定だった (`r2db-api/src/r2db_api/control_main.py` は `applications` / `credentials_per_application` / `control_requests_per_minute` / `audit_requests_per_minute` の 4 つだけを env から読んでいた)。**MitateDB は `MITATEDB_CONTROL_REQUEST_BYTES_LIMIT` で配線済み**であり (`control_composition.py`、既定 65536、`__post_init__` で正の整数検査、固定テスト `test_build_control_app_request_bytes_limit_matches_the_declared_one` も実在)、これは**開示されていなかった peer 非対称**である。
  - **閉じ方**: **記録のみに留めず r2db 側の配線追加で閉じた。** env 名は既存の `R2DB_CONTROL_LIMIT_*` 命名に揃えて **`R2DB_CONTROL_LIMIT_REQUEST_BYTES`** とし、**既定は現行の 1_048_576 を維持**した (挙動不変)。**したがって「r2db は `request_bytes` を env から配線していない」という記述はもはや真ではない。** 配備記録 (`r2db-api/deploy/env/control.env.example`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7 の env 表) にも既存 `R2DB_CONTROL_LIMIT_*` と同じ体裁で載せた。
  - **据え置いたもの**: **既定値の peer 差 (r2db 1_048_576 / MitateDB 65536) は既存の開示済み差として据え置く。** 「対称化」を理由に既定を動かせばそれは挙動変更である。
  - **証拠**: MitateDB と**同名**の r2db 側テスト `r2db-api/tests/test_audit_query.py::test_build_control_app_request_bytes_limit_matches_the_declared_one` (MitateDB は `tests/test_control_main.py` の同名テスト) が、`R2DB_CONTROL_LIMIT_REQUEST_BYTES` を設定したとき (i) `control_capabilities` の宣言 `limits.request_bytes` が変わること、(ii) 実際に ASGI 側が enforce する上限も変わること (超過要求が `LIMIT_EXCEEDED` / 413) の**両方**を固定する — 宣言値と enforce 値が同一ソースから出ることを固定するためであり、宣言だけを見るテストでは足りない。
- **L4-11 宣言 D の縮小 (D→N 降格) は (e) 単体では検出できない (両 peer 同型)** (新規起票、2026-09-03、WP-B1 レビュー M5b / 受け入れ監査の継続指摘)。**状態: 起票 → CLOSED (2026-09-03、WP-B3 追加項目)。** P4-D16 v3 (e) は `U == D ∪ N` かつ `D ∩ N == ∅` を固定するが、**耐久語彙を D から抜いて同時に N へ足す**変更はこの等式を保ったまま通る — 宣言が縮んだこと自体は (e) では赤にならない (実測済み)。現状は WP-B1 完了条件 7 の「宣言が本 WP の前後で不変であること」という**一回限りの人手確認**に依存しており、機械的な回帰ガードが無い。**閉じ方**: WP-B3 の追加項目 (e) として、両 peer に**宣言スナップショットテスト** `test_declared_audit_event_classes_change_only_deliberately` を置いた (両 peer 同名、`r2db-api/tests/test_audit_query.py` / `MitateDB-api/tests/test_audit_query.py`)。`DECLARED_AUDIT_EVENT_CLASSES` の内容がテスト内に固定した `frozenset` (**r2db 11 語 / MitateDB 12 語**) と一致することを要求する — 宣言を縮める変更は必ずこのテストを赤にし、実装者に「意図した縮小である」ことをテスト側でも宣言させる。N への降格が黙って通る経路がこれで閉じた。
- **L4-12 MitateDB `mitatedb-ctrl` 呼び出し経路の ID トークン発行が実機未検証** (新規起票、2026-09-03、記録のみ)。**状態: 記録のみ (実機未検証)。** `MitateDB-api/docs/cloud-run-cloud-sql.md` §6.3 が示す control service 呼び出し手順は `gcloud auth print-identity-token --audiences=<mitatedb-ctrl Cloud Run URL>` で `X-Serverless-Authorization` 用の ID トークンを得る形だが、**この呼び出しはユーザーアカウント principal に対しては拒否され得る** (サービスアカウントでのみ成功するという報告がある)。同 runbook はこの点を**両論のまま記載済み**であり (拒否された場合は principal 種別に応じた別の方法でトークンを発行するか `gcloud run services proxy` 経路へ退避する、と併記)、**実機に対して検証していない**。本項目は実測の欠落そのものを台帳へ残すためのものであり、対応は実配備時に行う。
- **L4-13 data-plane プロセスの環境に control-credential pepper が存在するのは MitateDB のみ (peer 非対称)** (新規起票、2026-09-03、記録のみ)。**状態: OPEN (記録のみ)。本セッションでは変更していない — フェーズ4 以前 (WP-4/WP-5) からの既存構造である。判断は次回。**
  - **確認済みの事実**: MitateDB の data-plane composition root `MitateDB-api/src/mitatedb_api/main.py` (`:213` 付近) は `MITATEDB_CONTROL_CREDENTIAL_PEPPER` を**実際に env から読む**。用途は `assert_pepper_separation(app_pepper, control_pepper)` による **2 つの pepper の同値比較のみ**であり、control credential store / control-plane service の**構築も import も無い** (R-7: control-plane プロセスがまだ無い配備でも、運用者が両 pepper を同一に構成できてしまう状態を起動時に止めるための検査である)。**r2db の data-plane `main.py` に対応物は無い** — 同等の関数 `validate_control_pepper_separation` は存在するが、呼び出しは `ops.py` (provisioning CLI) と `control_main.py` (control プロセス) の 2 箇所のみで、data-plane composition root は control pepper を読まない。
  - **意味**: 「control credential の秘密は control プロセスにだけ置く」という **SI-00 の分離**に照らすと、data-plane プロセスの環境に control-credential pepper が存在するのは MitateDB のみであり、**peer 非対称**である。比較にしか使わない (store を作らない・秘密を保持し続けない) ため現時点で認証面が増えているわけではないが、**data-plane プロセスの環境変数に control 側の秘密が置かれること自体**が分離の面積を広げている。
  - **候補 (両論。いずれも未採用)**: **(a)** 比較を pepper そのものではなく**フィンガープリント (片方向ハッシュ) 同士**で行い、data-plane 環境から**生の pepper を外す** — 検査の目的 (同値の禁止) は保ったまま秘密を移せる。**(b)** 分離検査を **provisioning 手順側 (runbook / CLI)** へ移し、data-plane 起動時の検査をやめる — r2db が既に採っている形に近い。**(c)** r2db にも同じ検査を data-plane へ入れて対称化する — **非推奨**。対称にはなるが、r2db の data-plane 環境にも control pepper を置くことになり**分離を弱める方向**である。
  - **L4-7(ii) のテストとの関係 (併記)**: L4-7(ii) の `test_data_plane_composition_root_does_not_import_the_control_credential_store` は、**両 peer とも AST ベース**が最終形である (レビュー差し戻し M4、2026-09-03) — `ast.parse` 後に `Import`/`ImportFrom` の module パスと alias 名、および `Name.id` / `Attribute.attr` を peer ごとの禁止語彙 (r2db = module `control_plane` + クラス名、MitateDB = module `control_auth` / `control_credential_store_postgres` / `control_plane` + クラス名) と突き合わせる。判定対象は control credential store / service の**構築・import** である。**本項目の env 参照 (`env.get("MITATEDB_CONTROL_CREDENTIAL_PEPPER")` と `assert_pepper_separation` の呼び出し) はそのテストの判定対象ではない** — 前者は文字列リテラルであり `ast` の識別子走査に入らず、後者は control-credential 語彙ではない。**L4-7(ii) が緑であることは本項目が閉じていることを意味しない。**

**継承分の解消**: `docs/design/PHASE35_CROSS_ENTITY_AND_CONTRACT_130_V1.md` §7 の **`audit_events` 予約名の未文書化は RESOLVED (2026-09-02/09-03)** — 契約 1.4.0 の項目 6 として文書化され、さらに監督裁定 **P4-D10** により「entity 識別子を受け取るあらゆる位置で予約が効く」実装義務 (無条件義務 (a)) としてテストで固定された。文書化だけでなく実装義務まで進んだ点が当初の台帳項目より強い。

その他の継承分 (識別子受理域の開示ギャップ、json 列の write/read 非対称、wire-level positive-existence check、C-03 の `ScopedMutation.entity` 未列挙、ほか) は同 §7 のまま未解消であり、本フェーズは触れていない。

---

### 11.2 契約 1.5.0 候補束と依頼者判断待ち事項 (2026-09-03)

§11.1 のうち、**共通契約 (`spec/`) の変更を要するもの**、または**挙動の非対称をどちらへ寄せるかという設計判断を要するもの**は、フェーズ4 台帳消化 (`docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md`) の範囲外とし、**依頼者判断待ち**としてここへ集約する。

**本節の性格**: 各項目は**両論のまま**記す — どちらの案にも寄せない。監督が推奨を持つものは「**監督推奨**」と明記して**併記**するが、それは判断ではなく材料である。**「範囲外」は「対応不要」ではない。** 契約 1.4.0 は既に出荷済みであり (`contract_version` 1.4.0、`spec/CCR_DISPOSITION.md` の従属判断 9 まで確定)、契約に手を入れるなら次は **1.5.0** である。

---

#### Q1 (台帳 L4-1) `operation` / `target_kind` の語彙宣言化

**結審 (2026-09-04)**: **依頼者裁定 2026-09-03 = 案 A (宣言化)**、Q2 と**一括で契約 1.5.0** (Q5 = 案 A、従属判断 8 → 9 の前例踏襲)。実施設計は `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` **§3 D-1** (確定文言・却下案・走査器の形はここが正本)、実施は **WP-1 `d7a5ffd` (契約公開) / WP-2 `3fd72ad` (r2db) / WP-3 `98d2010` (MitateDB、実装 `3f2da59`)**、実施記録は同設計 **§10** (WP-1 = §10.2、WP-2 = §10.3、WP-3 = §10.4)。台帳 **L4-1 は CLOSED** (§11.1、残る限界と新規起票 L5-1 を含めてそこに記す)。**本節の両論併記は裁定前の材料として保存する** — 以下は 2026-09-03 時点の記述である。

**問題**: 共通テスト C-09 vector 1 は、耐久行を「破壊的操作の行」と同定するために `operation` の候補集合 `{delete, mutate}` と `target_kind` の候補集合 `{entity, collection}` を**手で列挙**している。どちらのフィールドも `capabilities.audit_query` の宣言キー集合に含まれないため、この相関は宣言と機械的に結ばれておらず、**peer が自分の語彙の綴りを変えても共通 suite は気付かない**。両 peer の実語彙は実際に食い違っている (r2db はあらゆるデータ変更を `mutate`/`entity` の 1 組へ畳み、MitateDB は個々の操作名を出し target を `collection` と呼ぶ — `security/CONTROL_MAPPING.md` SI-14 行の点 (13) に両者の全語彙を併記済み)。

- **案 A (宣言化、契約 1.5.0)**: `capabilities.audit_query` に `operation_vocabulary` / `target_kind_vocabulary` を追加し、各 peer が自分の語彙を宣言する。C-09 vector 1 の手書き候補集合を**宣言参照へ置換**し、C-17 系 (宣言と挙動の一致) の宣言整合テストを追加する。`event_class` が D-7 で「宣言される語彙」になったのと**同じ扱い**を 2 フィールドへ与えることになる。得られるもの: 綴りの変更が共通 suite で赤になる。代償: 契約変更 (1.5.0) が要る。**共通語彙へ統一する案 (`entity` に寄せる) は採れない** — 両 peer の既存 `control_audit` 行と出荷済み語彙を破り、D-7 (各 peer が宣言する) と衝突する。
- **案 B (現状維持)**: 宣言化せず、非対称と手書き候補集合を **CONDITIONS.md の C-09 行に開示済みである**という現状に留める。得られるもの: 契約を触らない。代償: 上記の検出不能が残る。
- **監督推奨**: **案 A を Q2 と束ねて契約 1.5.0 として出す。** 単独で 1 回版を上げるほどではないが、Q2 が同じ版で片付くなら追加コストは小さい。

#### Q2 (台帳 L4-2) 契約 1.4.0 無条件義務 (b) の適用範囲

**結審 (2026-09-04)**: **依頼者裁定 2026-09-03 = 案 A (文言を締める)**、Q1 と一括で契約 1.5.0 の束として出荷。**ただし置き方は「Since 1.5.0」の新義務ではなく、1.4.0 無条件義務 (b) 本文への同ラベル補筆**であり、かつ**許容形**である (義務形にすると `versioning.control_discovery` の co-hosting 容認を狭め additive 性が崩れるため)。確定文言は `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` **§3 D-2** が正本、実施は **WP-1 `d7a5ffd`** (契約補筆 + port v1.9 + 共通無条件 vector)、実施記録は同設計 **§10.2**。台帳 **L4-2 は CLOSED** (§11.1、残る限界と新規起票 L5-4 を含めてそこに記す)。**本節の両論併記は裁定前の材料として保存する** — 以下は 2026-09-03 時点の記述である。

**問題**: data-plane ホストは `control_plane: enabled` を宣言しつつ (配備が control plane を持つのは事実である) control credential store を持たないため、そのホストの `/v1/audit/query` alias に control/audit credential を出すと `AUTH_INVALID` になる。無条件義務 (b) (「audit role の credential は `audit_query` で受理され、提供されていない場合は素の 404 ではなく `CAPABILITY_UNSUPPORTED` で拒否される」) を**どちらに掛かると読むか**で適否が分かれる。**現在は前者 (control surface 側) の読みで両 peer とも受理されている。** この経路 (control credential × data ホスト) を実測するテストは共通・peer とも**存在しない**。r2db と MitateDB はこの点で構造的に同一である。

- **案 A (文言を締める、契約 1.5.0。文言のみ・非破壊)**: 義務 (b) は「**control surface の `audit_query` control endpoint に掛かる**」と契約文言で明示し、control surface を提供しないホストが出す alias パスには掛からないことを確定する。あわせて「control credential × data ホスト → `AUTH_INVALID`」を固定する共通テストを追加する。**現在の実装挙動を変えないので非破壊**であり、変わるのは契約の読みが一意になることと、テストが実在するようになることである。
- **案 B (もう一方の読みを採る)**: 「**capabilities 文書を出すそのホストに掛かる**」と読む。この場合 **data ホストが control credential を受け付ける必要が生じる** — data-plane プロセスに control credential store を持たせることになり、`topology` の分離 (SI-00 / SI-02、data plane は control credential を検証できないという §1.5 の前提そのもの) と正面から衝突する。**監督は非推奨**である。
- **監督推奨**: **案 A を Q1 と束ねて契約 1.5.0。** 案 B は分離の設計前提を壊すため、選ぶなら分離側の再設計が先に要る。

#### Q3 (台帳 L4-4 / L4-7(iii)) request-count limit の受理レンジ非対称

**結審 (2026-09-04)**: **依頼者裁定 2026-09-03 = 案 A (MitateDB の上限を外す)**。**契約は触らない** (案 C は不採用) ため Q1・Q2 の契約 1.5.0 束には入らず、独立の WP として実施した。実施設計は `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` **§3 D-3** (確定形・却下案 (案 B / 案 C) はここが正本)、実施は **WP-4** (`MitateDB-api/src/mitatedb_api/control_plane.py::ControlPlaneLimits.__post_init__` の 4 クラス一律上限撤廃 + エラー文言修正 + テスト差し替え + `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c / `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15 / `security/CONTROL_MAPPING.md` SI-08 行の更新)、実施記録は `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` §10。台帳 **L4-4 / L4-7(iii) は CLOSED** (§11.1 に記す)。**併記した代償 (上限は誤設定の防波堤でもある) は却下せず、意図的に引き受ける代償として runbook / SI-08 行に運用者責任の記載で残した** — 「対応不要」ではなく「代償を承知のうえで撤廃した」ことが正確な記述である。**本節の両論併記は裁定前の材料として保存する** — 以下は 2026-09-03 時点の記述である。

**問題**: `audit_requests_per_minute` をはじめとする request-count クラスの**受理レンジ**が peer で違う。**MitateDB** は `ControlPlaneLimits.__post_init__` が `applications` / `credentials_per_application` / `control_requests_per_minute` / `audit_requests_per_minute` の **4 クラスすべてに `[1, 200]`** を課す。**r2db** は `ControlPlaneLimits`(`r2db-api/src/r2db_api/limits.py`) が「正の整数であること」しか検査せず**上限を持たない**。契約は本クラスに数値レンジを宣言していないので**双方適合**であり、CLAUDE.md の「同じ安全結果を与えるなら platform-specific control は peer 間で異なってよい」に該当する開示済み非対称である (要求される結果 = 窓が pre-auth かつ control 窓と別であること — 両 peer が満たす)。だが運用者から見ると、監査エージェント増加や障害復旧後の cursor 追い付きで窓を広げる必要が生じたとき、**r2db は設定変更で済み MitateDB はコード変更になる**。

- **案 A (MitateDB の上限を外す)**: MitateDB の `[1, 200]` を **4 クラスすべてで撤廃**し、r2db と同じく**正の整数のみ**の検査にする。r2db と対称になり、窓の広げ方が peer で同じになる。上限をどこに置くかは**運用者の責任**へ移る (依頼者設計原則 3「制約で回避しない」に沿う)。**併記すべき代償**: 上限は誤設定に対する防波堤でもあり、外せばその防波堤が無くなる (例えば `audit_requests_per_minute` に桁違いの値を置いた配備を製品コードは止めない)。ただし `control_requests_per_minute > applications + 2 × credentials_per_application + 67` という既存の関係検査は独立に残る。
- **案 B (r2db に上限を入れる)**: r2db 側へ `[1, 200]` を入れて MitateDB に揃える。**peer 自身の既存テストが `100_000` を構築・宣言しているため単独では通らない** — テストの書き換えを伴い、かつ「既に配備で使える範囲を狭める」方向の変更になる。
- **案 C (契約 1.5.0 でレンジを宣言する)**: 契約が本クラスの受理レンジを宣言し、両 peer がそれに従う。非対称そのものが契約レベルで消える代わりに、契約変更 (1.5.0) が要る。
- **監督推奨**: **案 A (+ 両 peer runbook に上限撤廃と運用者責任を記載)。** ただし上記の「防波堤を外す側面」は判断材料として併記する。案 C を採る場合は Q1・Q2 と同じ 1.5.0 に束ねられる。

#### Q4 (§11 記録項目) `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合の構造化

**問題**: 宣言 `visibility_lag_ms` は **control プロセス**が自分の env (`R2DB_AUDIT_STATEMENT_TIMEOUT_MS` / `R2DB_AUDIT_IDLE_TIMEOUT_MS`、MitateDB も同型) から導出するが、その値は**両方の書き手接続**についての主張である。ところが `application_audit` の書き手は **data-plane プロセス**という別プロセスで、**同名の env を独立に読む**。両プロセスが同じ env 名・同じ既定定数を読む構造なので運用上は一致するが、**機構的な強制も宣言側での検証も無く**、per-process の食い違いを**どちらのプロセスも検出しない**。runbook に前提として明記し、`security/CONTROL_MAPPING.md` SI-14 行の点 (12) に「nothing enforces it」と記録しているのが現状である。

- **案 A (現状)**: runbook の規律 (両プロセスを同一に構成せよ) に依存する。得られるもの: 変更なし。代償: 食い違いが無音のまま宣言を嘘にする。
- **案 B (DB 側を単一の真実にする)**: 書き手 role の timeout を **`ALTER ROLE ... SET statement_timeout` / `... SET idle_in_transaction_session_timeout`** で DB 側に固定する (r2db は migration **0008**、MitateDB は migration **0006** — いずれも新番号。既存 migration の in-place 編集はしない)。書き手はセッションでの timeout 設定を止めるか、起動時に実効値が role 設定と一致することを検証して不一致なら起動を止める。control は **reader 経由で `pg_db_role_setting` を読み**、そこから lag を導出する。これにより「宣言の根拠」と「実際に書き手へ効いている値」が**同一の一次情報**になり、2 プロセスの env 一致という前提そのものが不要になる。代償: migration とプロセス起動シーケンスに触る変更であり、両 peer 同時に行う必要がある。
- **案 C (書き手が実効値を記録し control が読む)**: 書き手が起動時に自分の実効 timeout を小さな設定表へ書き、control がそれを読んで lag を導出する。案 B より軽いが、**新しい書き込み面と新しい表**が増え、書き手が死んでいるときの古い値の扱いを決める必要がある。
- **監督推奨**: **案 B を独立の設計フェーズとして起票する** (両 peer 同時、設計文書 + migration)。台帳項目として抱え続ける形ではなく、正面から設計する対象である。
- **【注記 2026-09-04 (フェーズ6 WP-4)】 案 B の migration 番号は上記の「r2db 0008 / MitateDB 0006」から動く — 予約は割当ではない。** 監督裁定 (2026-09-04、フェーズ6 設計 §8 の 5 / §11 L6-2) のとおり、**文書上の予約は番号の割当てではなく、先に出荷したフェーズが次の空き番号を取る**。フェーズ6 WP-3 が MitateDB の宣言型 registry のために **per-application upgrade script `0006_declared_field_types_upgrade.sql`** を出荷したので、**Q4 (案 B) の MitateDB 側は `0007`** になる。**r2db 側は `0008` のままである** — フェーズ6 の r2db 出荷 (WP-2) は credential の wire 形を変えただけで DDL を要さず、番号を取っていない (`git diff -- r2db-api/migrations/` が空であることを受け入れ監査が照合済み)。本節の上記本文は**当時の記述として残す** (出荷済み・公開済みの記述を遡って書き換えない既存規律)。
- **同型の問題を同じフェーズで扱う**: **`coalescing_window_ms`** も同型である — 宣言は control プロセスが出すが、実際の窓は data-plane 側の `DataService(denial_coalesce_window_s=...)` (MitateDB は `audit_dispatch` の同名引数) で決まり、**配備がこの引数を上書きしても宣言には反映されない**。「宣言の根拠と実際に効いている値が別プロセスにある」という構造が `visibility_lag_ms` と同一なので、**同じフェーズで一緒に扱う**。
- **【注記 2026-09-05】同一フェーズへの同梱候補 (フェーズ6 設計 §11 L6-20 (f))**: **per-application upgrade script の運用性** (適用台帳 / `ops` からの一括適用 / 適用状態の可視化、両 peer 共通設計) は、案 B と同じく両 peer の migration と起動時検証に触るため、**案 B と同一の設計フェーズで扱うのを第一案**として起票した。案 B の migration (r2db `0008` / MitateDB `0007`) と (f) の台帳表の番号は L6-2 の規則 (先に出荷した方が次の空き番号を取る) に従い、本注記は割当ではない。`surfaces` の 2 プロセス間ドリフト (フェーズ6 設計 §11 L6-5a) も同族として既に本節へ寄せられている。

#### Q5 契約 1.5.0 の束ね方

**結審 (2026-09-04)**: **依頼者裁定 2026-09-03 = 案 A (一括)**。**Q1 + Q2 を 1 回の版上げ (契約 1.5.0) で出した** (WP-1 `d7a5ffd`、`spec/CCR_DISPOSITION.md` 従属判断 10 の項目 1 = Q1 / 項目 2 = Q2)。**Q3 は契約を触らないため束に入らない** — 依頼者は Q3 について案 A (MitateDB の上限撤廃、契約不変) を選んでおり、案 C (契約でレンジを宣言する) は採らなかった。**1.5.0 のクライアント通知の可否は本裁定に含まれず、依頼者判断事項として残る** (1.4.0 の通知は送らないと 2026-09-03 に決定済み)。以下は 2026-09-03 時点の記述である。

**問題**: 上記のうち Q1・Q2 は契約変更を要し、Q3 も案 C を採るなら契約変更になる。**どの単位で版を上げるか**が判断事項である。

- **案 A (一括)**: 従属判断 **8 → 9** で採った**一括判断の前例を踏襲**し、Q1 + Q2 (+ Q3 で案 C を採る場合はそれも) を **1 回の版上げ (1.5.0)** で出す。得られるもの: 版が増えず、クライアント (AI エージェント統合者) が読む差分が 1 回で済む。代償: 束ねた分だけ 1 回の判断が重くなる。
- **案 B (Q1 先行)**: Q1 のみを先に 1.5.0 として出し、Q2 は文言の詰めを待って後続の版に回す。得られるもの: 各版の判断が軽い。代償: 版が増え、同種の監査宣言まわりの変更が 2 回に分かれる。
- **監督推奨**: なし (束ね方は依頼者の判断領域である)。判断材料として、**契約 1.4.0 は既に merge 済み・出荷済みであり、契約変更は必ず版を上げる**こと、および **1.4.0 のクライアント通知は依頼者判断により送らないと決定済み** (2026-09-03) であることを付す。
