# フェーズ11 実施設計: keyset ページング (契約 1.8.0 → 1.9.0)

## 0. 版数・位置づけ

- **版数: v0.6 (2026-09-24)。依頼者裁定 Q-3 (見直し 1 点 = `where` の順序に依らない束縛を含む) / Q-5 (a) / Q-4 の逐語記録と反映である。** (v0.5 の版数行: 作業指示書起草時の疑義 7 件と v0.4 起草担当の疑義 (並走しない) の反映。)
- **改版履歴**: **v0.1 (2026-09-24)** 起草初稿。**v0.2 (2026-09-24)** — **起草担当が挙げた疑義 9 件への監督裁定の反映である。足したのは C-28 の観測 (v) の置き換えと (viii) 決定性 (裁定 1)、依頼者裁定待ち **Q-5** (`Page.cursor` の `maxLength`。裁定 2)、MitateDB の両 backend への NULLS 句明示 (裁定 3)、**R-107** の起票 (`order_by` 未知 field の拒否コード不一致。裁定 4)、r2db `validate_page_size` の details 是正 (裁定 7)、および §9 / §10 の追随である。既存の決定・裁定・却下は 1 つも撤回していない。** **v0.3 (2026-09-24)** — **設計レビュー 1 の 18 件への監督裁定の反映。直した 17 件、観察 1 件 (SQLite の rowid 再利用。§10 の 6 に開示)。** 撤回した決定は D-3 (4) の「Python 側で型を判定しない」1 件であり、該当行に根拠と日付を残した。改めた決定 (D-2 の select 行、D-4 の (ii)・(vii)) も旧文を残して改めた。 **v0.4 (2026-09-24)** — **設計レビュー 2 の 16 件 (全件直す) と v0.3 起草担当の疑義 7 件 (直す 4、採用 3) の反映。** 覆した決定は D-1 根拠 (1) の r2db の tie-break、D-2a の「peer の中では順序が 1 つ」、D-3 (4a) の型検査の関数、案文 C-6 第 3 文、D-2b の `page.size` 検査位置であり、いずれも該当行に旧文と根拠と日付を残した。枠の訂正は §2.3 の 1 行 (「形の上で」)。足したものは統合 branch (§9)、義務 (7) (既定ページ)、port `query_page` の `budget`、案文 C-3 の「cursor を運ぶ要求が返す行」の文、§11 (実施記録の置き場) である。 **v0.5 (2026-09-24)** — **作業指示書起草時の疑義 7 件と v0.4 起草担当の疑義 (並走しない) の反映。** 改めた決定は D-5 の `Page.cursor` の Revision note の置き場、R-107 の台帳行を置く WP (WP-6 → WP-1)、MitateDB の cursor 拒否の置き場 (WP-2 で cell の入口へ移す) であり、いずれも該当行に旧文と根拠と日付を残した。足したものは WP-6 の control 側宣言と 1.8.0 のピンの追随、§9 の「本件では並走させない」である。同日、起草担当の疑義 4 件を反映 (cursor 入口は runtime の入口 → cell の実体、WP-6 に `test_denial_details_and_request_id.py` の 1.8.0 のピン 2 本、WP-2 の L1 件数ピンの条件付き追随を確定)。 **v0.6 (2026-09-24)** — **依頼者裁定 Q-3 (見直し 1 点 = `where` の順序に依らない束縛を含む) / Q-5 (a) / Q-4 の逐語記録と反映。** §5.1 に裁定の逐語と監督の提示 (見直し 1 点) を記し、§5.2 の Q-3 / Q-4 / Q-5 を §5.1 へ移した (両論の記録は残した)。覆した決定は案文 C-4 の「the same where predicates in the same order」(→ in any order)、D-3 の 3 の束縛 hash (述語の並びを含む → 正規化した `where`)、§10 の 10 の開示 (取り下げ) であり、いずれも該当行に旧文と根拠と日付を残した。足したものは両 peer 同名の束縛 helper `canonical_page_binding` と `_ISOMORPHIC_TARGETS` の 3 行目 (D-6)、MitateDB の束縛 (D-2b の 5)、`test_c28_cursor_binding` の並べ替えの観測 (D-4、§6.1)、§10 の 14 (束縛の値の同一性は JSON の等価性に依る) である。D-1 (D) と §10 の 4 は Q-5 = (a) に確定させた。
- 位置づけ: **監督が確定した枠 (2026-09-24) の実施設計**である。計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.119、以下 `RM`) の **§5 フェーズ11 節**・**§4**・**§3.2**・**§8**・**§9** が**正本**であり、本書 §1.1 / §2.1 / §2.2 はそれを**逐語で転記する** (`RM` §9 の 1、`docs/work-orders/OPERATING_CONDITIONS.md` 以下 `OC` の §1.8 の 53)。**§3 の D-1〜D-9 と §4 は監督確定の枠の展開であり、§5 の Q-1 / Q-2 (v0.6: と Q-3 / Q-4 / Q-5) は依頼者裁定の逐語である。**
- 台帳 ID: **R-106 (仮番号)**。`RM` §8 の最終使用済みは R-105 である。**merge 直前に main の台帳を読んで振り直す** — 本件と並走する R-29 が同じ台帳・`spec/`・`CONDITIONS.md`・`CONTROL_MAPPING.md` に触れるため、番号の衝突は最後に解決する (§9 の並走の注意)。
- テーマ: **「ページの続きを読めること、そして読み終えたと言えること」**。契約は `Page.cursor` と `QueryResult.next_page` を **schema としてだけ**持ち、意味の文言を 1 件も持たない。消費者 (Mitate) は完全性を証明できず、上限に達したら正直に拒否するしかない縮退を入れている。本フェーズはこの空白を契約 1.9.0 (従属判断 14) で埋め、両 peer に keyset ページングを実装し、共通条件 C-28 で固定する。
- **契約は変わる** (1.8.0 → **1.9.0**)。したがって**設計レビューは 2 回**である (`RM` §9 の 3)。規模は **L**、変更クラスは **D** である (§8)。
- 作業指示書は `docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md` であり、**`RM` §9 の 9 に従い WP ごとの Change Set Manifest 形式で書く**。**設計の逐語表・裁定文・却下案・背景は manifest に写さず本書の節番号で指す。**
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。**既定の重み付けは「最小変更」ではなく「長期に正しい形」。利用設計者は AI エージェントであり、宣言は確実に読まれる。**
- **公開規律**: 実ホスト名・cloud project 識別子・実 credential・作業機の絶対パス・実 DSN・traceback を書かない (`OC` §1.9 の 60〜63)。**file:line はすべてリポジトリ相対パスである。契約 1.9.0 の確定文言は、依頼者確定後に監督保管の確定文ファイルから逐語で複製する** (`OC` §1.5 の 35・36)。本書 §3 D-1 の案文は**未確定の案**であり、同じ案文を scratchpad の `verbatim-190-draft.md` に置いた。**【v0.6 (2026-09-24)】 案文は依頼者裁定 Q-3 (§5.1) で見直し 1 点を含めて確定した。確定文ファイル `verbatim-190.md` は監督が本改版の後に置く。**

- **訂正註 (2026-09-25、番号の振り直し)**: 並走した最低共通機能プロファイル (R-29) が main (`b283f48`) へ先に merge し、本件が仮に使っていた番号を消費した。本件の番号を次のとおり振り直す (写像は監督確定)。本文は書き換えず、本文中の仮番号はこの写像で読み替える。
  - 契約 1.9.0 (paging の文言・義務・`version_binding` の段落・Revision note・pin) → **1.10.0**。main の 1.9.0 (`common_baseline` と `operation_catalog`) はそのまま残る。遡及拒否の旧い列挙と 1.9.0 段落の末尾文は main の文面のまま触らない (main の Revision note 3 の方針。監督裁定 2026-09-25)。1.10.0 段落は自身の末尾の遡及文だけを持つ。`spec/CONTRACT_HISTORY.md` の本件の Revision note 3/4/5 は 4/5/6 に繰り下がる (main の note 3 が先)。
  - C-28 (keyset) → **C-30**。main の C-28 は baseline turn、C-29 は operation catalog。conformance の試験ファイルは `conformance-tests/test_c30_keyset_paging.py` に改名する。
  - R-106 (keyset 本体) → **R-109**。main の R-106 は MitateDB `row_addressability`、R-107 は `revision_preconditions`、R-108 は参照クライアント。
  - R-107 (`order_by` 未知 field の拒否コード不一致) → **R-110**。
  - 従属判断 14 (keyset。依頼者裁定 Q-1/Q-2/Q-3/Q-5) → **従属判断 15**。main の従属判断 14 は `common_baseline`。
  - port v1.16 (`query_page`) → **v1.18**。main の v1.16 は `attempt_filter_with_result`、v1.17 は `operation_catalog_document`。
  - 不変: migration 0015、`_ISOMORPHIC_TARGETS` の件数 156→159。

---

## 1. 問題設定と実需

### 1.1 実需 — Mitate 正本の逐語

`RM` §3.2 の実需の定義 (v1.108) の **(a)** に当たる記録である。Mitate リポジトリの正本文書から**逐語**で引く。**本書の変更で Mitate 側の文書は編集しない** (同節)。

**(a-1)** `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3「offset の扱い (契約ギャップの client 側方針)」の 2:

> 2. **将来要求として登録済み**: cursor pagination のサーバ側実装 (サーバ側台帳へ)。成立したら client を cursor 走査へ切替え、offset 上限を実質撤廃

**(a-2)** 同書 §12 (f):

> | f | cursor 走査（MitateDB の `next_page` は常に null。成立時に指示書 §1 D4 の「ちょうど B 件も拒否」縮退を撤廃） | **未着手** — サーバ側 cursor 実装待ち |

**(a-3)** `docs/work-orders/mitate-application-data-service-client-phase-b.md` §1 D4 の「完全性の正直拒否」:

> - **完全性の正直拒否（新設・重要)**: MitateDB は `next_page` を常に `null` で返し（cursor 未実装）、`result_items=500` が結果件数上限。つまり**取得結果が上限に達したとき「全件取れた」ことを証明できない**。規律: 有効上限 B = capability 宣言の `limits.result_items`（page.size 上限 1000 との小さい方）とし、`page.size = B` で取得して `items.length >= B` なら **`operation_failed` で正直拒否**する（黙った欠落・黙った打切りでの query/readAudit/一意性判定/集計を行わない）。ちょうど B 件のデータ集合も拒否される — これは既知の正直な縮退として文書化する（cursor 成立時に撤廃）。この規律は query だけでなく、**一意性判定・集計・readAudit・参照整合など「母集合の完全性」を前提とするすべての読出**に適用する。

**(a-4)** `docs/design/contract-v0.21.0-audit-deepening.md` §12 の review trigger (長い `/` 区切り列挙の一部):

> … / **`data-service-api` 側の cursor 語彙との整合**（§10-A Q2 が (B) で決した場合、および data-service-api が監査向けの keyset 契約を持つ場合）/ …

**(a-5)** client の現物 (`mitate-application` リポジトリ、読み取りのみ。`src/application/data-service-store.ts`):

- `queryEntity` は `request["page"] = { size: pageSize }` で 1 ページだけ読み、`result.items.length >= pageSize` なら例外を投げる (:1422-1447)。`next_page` は型として受け取るが使わない (:1435)。直後のコメントが「completeness cannot be proven (MitateDB's `next_page` is always null; there is no cursor to keep reading with)」と書く (:1437-1440)。
- `pageSize` は常に `resultItemsCap = Math.min(resultItems, 1000)` (:380, :529)。
- `order_by` は呼び出し元が指定し、`seq asc` (:712) と `solutionId asc` (:793)、監査系は `seq desc` + `seq lt <before>` (:1246, :1283, :1311, :1337, :1461) を使う。**`seq` は Mitate が `create_entity` で宣言した typed field であり、data-service-api 側に `seq` の実体は無い** (本リポジトリ全体の grep で entity 行の `seq` 列は 0 件)。

**実需の判定**: `RM` §3.2 の突合表 (:249) は (高速化案 7) keyset ページングを **充足** と判定し、§5 (:382) も **着手条件充足** とする。本書はこの判定を再導出しない。

### 1.2 現物の実測 (2026-09-24)

**(1) 契約 `spec/data-service-api.v1.json` (1.8.0)**

- `Page` は `{size: integer 1..1000, cursor: string maxLength 512}` であり、どちらも required ではない (:1687-1701)。`QueryResult.next_page` は `type: [string, null]` の 1 行で、description を持たない (:1282-1293)。`Order` は `{field, direction: asc|desc}` (:1667-1679)。`QueryRequest` の required は `select` だけ (:875-923)。
- **順序の保証・cursor の不透明性・失効時の応答・`next_page` が null になる条件のいずれについても、契約は 1 文も持たない。**
- 対照的に、監査側には明文がある。`audit.query_ordering` (:867) が `(recorded_at, plane, event_id)` の全順序を、`audit.query_cursor` (:868) が「opaque cursor であって event_id でも数値 offset でもない / 復号できない、または request 自身の filter で解決しなくなった cursor は VALIDATION_FAILED / ある filter 集合で得た cursor は同じ filter 集合でのみ有効」を定める。**本件はこの語彙を entity query に移す作業である** (D-9)。

**(2) r2db-api — offset cursor**

- `page.cursor` は base64url(JSON `{"o": <offset>, "q": <shape hash>}`) (`r2db-api/src/r2db_api/paging.py`:88-120)。`_shape_hash` は (application_id, entity, select, where, order_by, size) を束ねる (:88-104)。
- `_resolve_order_by` は order_by を検証し、`id` が含まれなければ末尾に `("id","asc")` を足して全順序にする (:56-84)。
- 実行は in-memory cell が `rows[offset : offset+size+1]` (`structured.py`:925-931)、PostgreSQL cell が `OFFSET {offset} LIMIT {size+1}` (`postgres_sql.py`:66、`postgres.py`:1361-1390)。**深いページの費用は offset に比例する。**
- NULL の位置と型跨ぎの順序は PostgreSQL 既定 (asc → NULLS LAST、desc → NULLS FIRST。untyped 列は jsonb の型順) に揃えてあり、in-memory 側は `inmemory_sort.py`:24-40 の `_sort_key` が同じ規則を再現する。
- 設計の出所は `docs/design/R2DB_CCR13_STORAGE_V1.md` §R-6 (:107-111)。形状ハッシュと offset 上限 10^9 は訂正記録 **m-3** (:243)「cursor が query 形状を束ねない / offset 上限なし → 形状ハッシュ + 上限 10^9」に由来する。
- 拒否の details は `violation("request_schema", field="cursor")` (`paging.py`:110-120) — **契約の path 規則 (`errors.details_vocabulary.VALIDATION_FAILED.field`「request body root からの '/' 区切り、先頭の区切りなし」) では `page/cursor` であるべき位置である。**

**(3) MitateDB-api — cursor 非実装**

- `page.cursor` を提示されたら `CAPABILITY_UNSUPPORTED` で拒否する (`MitateDB-api/src/mitatedb_api/http.py`:634-657)。同箇所のコメントは「Left to a future capability-envelope decision whether to implement cursor pagination at all」と書く。
- 応答は `{"items": rows, "next_page": None, ...}` であり、**`next_page` は常に null** (:675)。
- `read` は `order_by` が None のとき ORDER BY 節を付けず、tie-break 列も持たない (`backend_postgres.py`:1397-1465、`backend_sqlite.py`:553-)。
- collection table は**宣言フィールドの列だけ**で作られ、サーバ採番の列を 1 つも持たない (`backend_postgres.py`:939 の `create_collection`)。`insert` が返す `ctid` は PostgreSQL の物理位置であり、**UPDATE / VACUUM で変わる** (:1236-1259 のコメントに明記)。`row_addressability: unavailable` (`capabilities_document.py`:115)。
- `_select_fields` は `select` 未指定時に `field_domains(collection)` をそのまま返す (`cell.py`:3066-3069)。`field_domains` は `information_schema.columns` を**無フィルタで**列挙する (`backend_postgres.py`:426-492)。**つまり collection table に列を足すと、既存コードのままでは既定 select-all に漏れる** (D-2 の主要な障害点)。`field_types` は自前カタログ表 `_mdb_field_types` の行だけを返すので、隠し列はそちらには出ない (:504-539)。
- client が `_` で始まる識別子を宣言する経路は無い — `identifiers.py`:19 の `^[a-z][a-z0-9_]{0,62}$` が先頭 `[a-z]` を要求する。`postgres_reserved_names.py`:14-15 の予約は `audit_events` と `pg_` 接頭辞だけで、`_` 始まりの一般規則はそこには無い (構文側で落ちる)。
- isolation は **database-per-application** (`backend_postgres.py`:79)。SQLite backend は「a local, deterministic test double, never a deployment target」(`MitateDB-api/README.md`:52-54, :258-259)、本番経路は PostgresBackend だけ (`main.py`:127, :463)。ただし **conformance の非 HTTP plug (`MitateDB-api`) は in-process cell = SQLiteBackend を通る**。
- `structured_query` は `partial` (`capabilities_document.py`:80。`unsupported: contains / matches / is_null`)。

**(4) conformance**

- port は `select_eq` (`conformance-tests/adapter.py`:2091-2108) と `attempt_filter` (:2110-2160) を持つが、**どちらも `order_by` / `cursor` を引数に持たない**。`select_eq` は `limit`(= page size) だけを持つ (port v1.12、L7-21)。port の現行最大版は **v1.15** (:999)。
- `next_page` に触れるのは `test_contract.py`:1368 の必須キーのピンだけで、**ページングを主題にする共通条件は存在しない**。`CONDITIONS.md` の現行は C-00〜C-27 の 28 件 (`RM` §0.1.1 の G-2 / G-3 行)。
- 版ゲートの手本は C-21 / C-25 の `adapter.parse_semver` + 実行時 `xfail(strict=True)` (`test_c25_result_request_id.py`:214-226)。

### 1.3 解く問題

契約が `next_page` の意味を定めていないので、**MitateDB の「常に null」は今の契約では違反ではない**。その結果、消費者は「全件読めた」ことを証明できず、上限に達したら拒否する縮退を自前で持っている (§1.1 (a-3))。解く問題は次の 2 つであり、どちらも契約の空白に起因する。

1. **完全性が言えない** — `next_page: null` が「末尾に達した」を意味すると契約が言っていない。
2. **深いページが高い、かつ並行変更下で正しくない** — offset は位置ではなく件数を数えるので、走査中の挿入・削除で同じ行を 2 回返し、返さない行を作る。r2db の現行方式がこれに当たる。

---

## 2. 守るべき条件

### 2.1 計画文書 §5 「フェーズ11 以降」節の転記

`RM` §5 (`:364-388`) を以下に**転記する** (再導出しない)。

> ### フェーズ11 以降 — 実需駆動 (§3.2 の保留項目)
>
> 着手順は実需の記録順とし、本書では固定しない。ただし依存関係は次のとおり。
>
> - 非同期 job (CCR-09) → bulk ingest/export の chunk 原子性 → aggregation。
> - change feed は idempotency (R-5) と audit cursor の語彙を前提とする。
> - credential 委任 (CCR-11) は R-4 の認可 dry_run を前提とする。
> - 関係モデルは 2.0 級として独立審議。関係に依存する機能 (subgraph fetch、relationship-aware plan) はその後。
> - snapshot は control plane の application lifecycle としてのみ再考する。
> - **【追記 2026-09-23 (v1.108)】実需の突合 (§3.2 の実需の定義と突合表による。2026-09-23 時点)。** 上の依存関係は書き換えていない。どれから着手するかは依頼者の裁定事項であり、本追記は判断しない。
>   - (中略)
>   - keyset ページング (高速化案 7): **着手条件充足** (Mitate `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` §3 の 2・§12 (f)、2026-09-23)。

`RM` §3.2 の保留項目表 (`:229`) の当該行も転記する。

> | (高速化案 7) keyset ページング (依頼者指示 2026-09-21 の高速化案の検討) | entity query の paging の意味 (現行の方式は着手時に確認する) | 深いページの速度のための変更でも、cursor の意味と順序の保証は共通契約の変更になる (版数の更新) |

### 2.2 計画文書 §4 の該当 P の転記

`RM` §4 (`:277-285`) から、本フェーズに効く行を**転記する** (再導出しない)。

> | **P-1** | **1 要求 = 1 原子単位。往復をまたぐサーバ保持状態を持ち込まない。** plan・sandbox・resumable upload・保持 lock はすべてこれに当たる。無状態化 (決定的トークン、実行して rollback) で同じ目的を満たす | 契約 `transactions.interactive`、SI-08、両 peer の同型性 (状態は同型性を「持ち方」と「失効」の 2 回壊す) |
> | **P-3** | **宣言は真であり、検査される。** 新しい宣言 (制約・能力・limit) は、宣言と実挙動の一致を共通条件として同時に追加する。advisory な宣言 (強制されない説明文) を catalog に載せない | C-05 / C-17、L6-6 |
> | **P-5** | **bound は安全上必要なものだけ。** 機能の問題を TTL・件数上限・除外リストで消さない。要求単位 budget は配備上限を下回る方向にのみ効く | 設計原則 3、SI-08 |
> | **P-6** | **peer 同型性を維持する。** 同名 helper は正規化 diff で固定し、コードは共有しない。platform 固有の実現 (PostgreSQL / SQLite / in-memory) が異なっても、契約上の意味は一致させる | peer-symmetry 規約 (2026-09-03) |
> | **P-7** | **契約はエージェントが読める長さと形を保つ。** 経緯文は companion へ、現行の意味だけを契約本体に置く。派生の機械可読 artifact は再生成一致テストで正本に縛る | G-1、R-8 / R-10 |
> | **P-8** | **各フェーズは性能の差分を記録する。** 基準値 (R-12) 確定後、完了ゲートに p50 / p95 の記録を添える。退行は初期は記録のみ、基準値が 2 フェーズ安定した後にゲート化を審議する | G-4 |

### 2.3 本フェーズで特に効く条件 (枠 §2)

- **P-1 が中心である。** cursor は**無状態・決定的トークン**であり、サーバは往復をまたぐ状態を持たない (失効も掃除も上限も無い)。これは `dry_run.plan` が既に取っている形と同じである (契約 `structured_operations.dry_run.plan`「opaque but deterministic token … holds no server-side state」)。
- **P-3**: 1.9.0 の義務は版に束ね、共通条件 **C-28** を同じ変更セットで置く。6 plug で executable かつ緑。
- **P-5**: cursor に TTL も件数上限も足さない。`page.size` (契約固定 1..1000) と `result_items` (配備 bound、1 ページあたり) は現行のままである。
- **P-6**: cursor codec を両 peer に**同名**で置き `_ISOMORPHIC_TARGETS` に登録する (集合の増加 = **Class D**)。
- **P-7**: 契約本体には現行の意味だけを置き、経緯は `spec/CONTRACT_HISTORY.md` へ。
- **SI-01 / SI-03**: cursor は権限を運ばず、Application と entity に束縛される。tie-break の値は **Application-scoped** であること (`structured_operations.addressability.assigned_identifiers` の「他 Application の存在や活動を推測させない」と同じ性質)。MitateDB は database-per-application なので、table ごとの採番は Application-scoped である。
- **SI-10**: 拒否の details は宣言事実だけ (`violated_declaration: request_schema`、`field: page/cursor`)。cursor の中身は client が既に受け取った**自分の行**の値であり、他 Application の値ではない。
- **1.9.0 は client に何も要求しない** (`page.cursor` は optional のまま。1.8.0 で有効な要求は有効のまま)。**【枠の訂正 2026-09-24 (v0.4)。監督裁定】 括弧内の後半を「1.8.0 で有効な要求は**形の上で**有効のまま (版フリップ前に発行した cursor は跨いで使えなくてよい)」に改める。** 根拠: 旧 offset cursor を移行しない (D-3 の 6) ので、版フリップ前に発行した cursor を運ぶ要求は拒否される。案文 A と D-1 根拠 (8) は v0.3 で既にこの形であり、枠の文だけが残っていた。
- **版フリップは実挙動と同一コミット** (`versioning.version_binding` の末尾の規則)。
- 運転条件: `OC` §1.5 の 32 (空振り禁止)・33 / 40 (完了条件 1 項目につき変異 1 つ、対応表)・34 (主張は実測の後)・35 / 36 (確定文言はファイル経由)・38 (同型性テスト)、§1.13 の 74 (規模 L は現行の全手順)、§1.15 の 77 (指摘の裁定)。

---

## 3. 決定と根拠 (D-1〜D-9)

### D-1. 契約 1.9.0 (従属判断 14) — ページングの意味を定める

**決定**: `structured_operations` に **`paging`** 節を新設し、`versioning.version_binding` に 1.9.0 の段落を、`versioning.obligations` に 1.9.0 entry を足す。**義務はすべて conditional** であり、`capabilities()` が `structured_query` を `unavailable` 以外で宣言する実装にのみ束縛する。

**節の名前**: `paging` とする。`structured_operations` の既存キーはいずれも短い名詞 (`scope`・`addressability`・`upsert`・`dry_run`・`idempotency`・`alter_field`) であり、`query_paging` は同じ object の中で `query` を重ねて冗長である。位置は `upsert` と `revision_preconditions` の間 (query 系の語が並ぶ位置)。

**案文 (英語、spec の文体。未確定。同じ文を scratchpad の `verbatim-190-draft.md` に置いた)** **【v0.6 (2026-09-24)】 依頼者裁定 Q-3 (§5.1) で、C-4 の見直し 1 点を反映した形で確定した (「未確定」は v0.5 までの状態)。確定文ファイルは監督が `verbatim-190.md` に置く。**

**(A) `versioning.version_binding` の末尾に足す段落** — 既存の遡及文 `An implementation still declaring 1.7.0 is not held to any 1.8.0-only obligation retroactively.` の**直後**、末尾の version-flip の 1 文 (`A peer's version-flip -- ...`) の**直前**。段落末の新しい遡及文 (1.8.0 について) は、既存の遡及文 (1.6.0・1.7.0 について) の後ろに続く並びになる (v0.3。設計レビュー 1 の指摘 14 への裁定)。

> Only an implementation declaring 1.9.0 or higher additionally claims conformance to the obligations 1.9.0 introduces (subordinate ruling 14). Every 1.9.0 obligation is conditional, in the same sense 1.4.0's, 1.6.0's, 1.7.0's and 1.8.0's own conditional lists are: each binds only insofar as the implementation's own capabilities() declares structured_query as something other than unavailable: (1) the items a query returns are totally ordered, in the order structured_operations.paging.ordering defines -- the request's own order_by, completed by a tie-break of the implementation's own choosing, which this contract does not name -- so that two identical requests decided against unchanged stored content return the identical sequence; (2) QueryResult.next_page is non-null exactly when at least one further row follows this page's last item in that order, and null exactly when none does; (3) where it is non-null, it is a keyset cursor as structured_operations.paging.cursor defines it -- an opaque token encoding that last item's own position in that order, never an offset or a count, holding no server-side state, and a request carrying it returns the rows that follow that position; (4) a cursor is bound to the Application, the entity, the request's where and the request's order_by, and stays valid across a change of select or page.size (structured_operations.paging.binding); (5) a cursor that fails to decode, whose ordering values do not match, in number or in type, the terms of that order, or whose recorded binding names a different Application, entity, where or order_by than the request presenting it, is refused with VALIDATION_FAILED, details.violated_declaration: request_schema and details.field: page/cursor; (6) across the pages of one traversal, a row that exists throughout it and whose ordering-term values do not change during it is returned exactly once; and (7) a request that carries no page.size is answered as though it carried the page.size equal to the least of 1000 (Page.size's own maximum), the implementation's declared limits.result_items, and the request's own budget.result_items where it carries one, and its page holds at most that many items (structured_operations.paging.next_page). 1.9.0 introduces no obligation on what a client must send: page.cursor remains optional wherever it appears, and a request valid under 1.8.0 stays valid in shape. A cursor an implementation issued before its own version-flip need not remain usable across it; such a request is refused as structured_operations.paging.refusal describes, and the client restarts the traversal. An implementation still declaring 1.8.0 is not held to any 1.9.0-only obligation retroactively.

既存の遡及列挙文 (1.5.0・1.6.0・1.7.0 について) の列挙を `1.7.0-only, 1.8.0-only or 1.9.0-only` の形へ伸ばすのは、1.8.0 が 1.7.0 に対して行ったのと同じ**機械的な追随**であり、新しい判断ではない。

**(B) `versioning.obligations` の 1.9.0 entry** — obligation 名は snake_case、conditional の capability は `structured_query`。

```json
{
  "version": "1.9.0",
  "subordinate_ruling": 14,
  "unconditional": [],
  "conditional": [
    {"obligation": "query_results_are_totally_ordered", "capability": ["structured_query"]},
    {"obligation": "next_page_is_non_null_exactly_when_more_rows_follow", "capability": ["structured_query"]},
    {"obligation": "next_page_is_a_stateless_keyset_cursor", "capability": ["structured_query"]},
    {"obligation": "query_cursor_is_bound_to_application_entity_where_and_order_by", "capability": ["structured_query"]},
    {"obligation": "unusable_query_cursor_refused_as_a_request_schema_violation", "capability": ["structured_query"]},
    {"obligation": "unchanged_row_returned_exactly_once_across_a_traversal", "capability": ["structured_query"]},
    {"obligation": "omitted_page_size_defaults_to_the_least_of_1000_and_the_result_items_bounds", "capability": ["structured_query"]}
  ]
}
```

`unconditional` が空である版には前例がある (1.5.0 entry)。`obligations_note` が言う「prose と index の版ラベル集合の一致」と「unconditional の件数の一致」は、この形で保たれる。**【v0.4 (2026-09-24) で足した】** 7 件目 (既定ページ) は案文 A の (7) に対応する。既定ページは C-28 で検査する宣言なので版に束ねる (P-3。v0.3 起草担当の疑義 2 への監督裁定)。名前は「least of 1000 と result_items の bound 群」を言い、「could / may carry」を名前に入れない (設計レビュー 2 の指摘 6 への監督裁定。bound は宣言 `limits.result_items` と `budget.result_items` の 2 つなので複数形)。

**(C) `structured_operations.paging` の各文**

- **`paging.ordering`**

> The items QueryResult returns are totally ordered. The request's own order_by names the leading terms of that order, and where order_by is absent the implementation's own default leads; in either case the implementation completes the order with a tie-break of its own, so that no two rows of an entity ever compare equal. That tie-break is the implementation's own and this contract does not name it: a client does not rely on which it is, and where it is not one of the entity's declared fields, it is never returned as a field of an item and cannot be selected, filtered or ordered on. Two identical requests decided against unchanged stored content return the identical sequence of items. How strings compare (collation), where an ordering term's values include null, and how values that are not a string, number or boolean -- including an untyped field's values of differing JSON type -- compare, are the implementation's own; this version does not require two implementations to place them alike, and a client that needs a placement it can rely on orders by a field whose values it controls.

- **`paging.next_page`**

> QueryResult.next_page is non-null exactly when at least one further row follows this page's last item in the order paging.ordering defines, and null exactly when none does. A null next_page is therefore the service's statement that this page ends the result -- what lets a client know it has read the whole of it, rather than inferring completeness from a page that came back shorter than page.size. An implementation may decide this by reading one row beyond the requested page.size and returning only page.size items. A client never constructs a next_page value itself; it only echoes the value it received back as Page.cursor on a later request. Where a request carries no page.size, it is answered as though it carried the page.size equal to the least of 1000 (Page.size's own maximum), the implementation's declared limits.result_items, and the request's own budget.result_items where it carries one; its page holds at most that many items, and next_page reports, in the same terms, whether any row follows the page it returned.

- **`paging.cursor`**

> The value next_page carries is a keyset cursor: an opaque token encoding the position of this page's last item in the order paging.ordering defines -- that row's own ordering values together with the implementation's tie-break -- and never an offset, a row count, or an index a client could compute for itself. A request that carries a cursor returns, in the order paging.ordering defines, the rows that follow the position it encodes, under that request's own where and order_by as they stand when the request is decided. It holds no server-side state: nothing on the service expires, is evicted, or must be cleaned up, there is no bound on how many cursors may exist, and a cursor is not attached to a session, a connection or a credential. Its internal structure is opaque; an implementation may change that structure without a contract change, and no client may depend on it. This contract states no performance figure and none is claimed here. A cursor is neither signed nor encrypted: it is a recoverable encoding of the ordering values of a row the client has already received -- its own data, never another Application's -- and a client that stores or forwards a cursor forwards those values with it. An implementation is not required to detect a well-formed token it did not itself issue; the binding paging.binding defines is what keeps such a token inside the Application, entity, where and order_by it names, and a client that alters one receives an arbitrary position within its own result or a refusal, never another Application's rows.

- **`paging.binding`**

> A cursor is bound to the Application it was issued under, the entity it was issued against, and that request's own where and order_by; it is valid on a later request that repeats all four -- the same where predicates, in any order, and the same order_by -- and is refused under any other, as paging.refusal describes. select and page.size are deliberately outside that binding: neither changes where a row sits in the order, so a client may narrow or widen its projection between pages, and may continue from the cursor it already holds with a smaller page.size after a LIMIT_EXCEEDED refusal, without restarting the traversal.

- **`paging.refusal`**

> A cursor that fails to decode, whose ordering values do not match, in number or in type, the terms of this request's own order as paging.ordering defines it, or whose recorded binding names a different Application, entity, where or order_by than the request presenting it, is refused with VALIDATION_FAILED, details.violated_declaration: request_schema and details.field: page/cursor. The refusal names that position in the request and nothing else: not what the token decoded to, not what it was bound to, and not whether the Application or entity it names exists. A client that receives it restarts the traversal rather than adjusting the token.

- **`paging.traversal`**

> A traversal is a first request together with the successive requests that each echo back the next_page they received. Across the pages of one traversal, a row that exists throughout it and whose values for the ordering terms do not change during it is returned exactly once. A row inserted or deleted while the traversal is in progress is returned once or not at all; a row whose values for the ordering terms change during it may be returned twice, once, or not at all, since each page is decided against the order as it then stands. No further statement is made about concurrent change: this version defines paging, not a snapshot, and a client needing a stable point in time obtains it some other way.

**【v0.4 (2026-09-24) で改めた案文 — 設計レビュー 2 への監督裁定】**

- **C-6 第 3 文 (決定を覆した)**: 旧文「A row inserted, deleted, or moved in the order while the traversal is in progress is returned once or not at all.」を上の文に差し替えた。根拠: 順序項の値が走査中に変わった行 (例: `score asc` で既出の行の score を cursor 位置より後ろへ更新) は、次のページの keyset 述語に再び入るので 2 回返る。どの keyset 実装でも旧文は守れず、C-28 は移動を観測しないので検査でも見つからない (指摘 2)。案文 A の (6)「値が変わらない行はちょうど 1 回」は真なので変えない。
- **C-1 第 3 文**: r2db の tie-break `id` は宣言 field であり select・filter・order できるので、旧文「a client does not name it, does not receive it as a field of an item, and cannot select or filter on it」は r2db で偽だった。契約は tie-break を名指さず、宣言 field でない tie-break に限って item に出ず select・filter・order できない、と改めた (指摘 3。A (1) も同じ)。
- **C-1 最終文**: 実装任意の範囲に文字列の照合順序と、string / number / boolean 以外の値の比較を足した (指摘 11)。
- **C-2 末尾**: 「その要求が運べる最大の page.size」は、返す行数で判定する r2db では 1000、要求値で判定する MitateDB では min(1000, bound) となり二義だった。「least of … を運んだものとして答える」と「at most that many items」に改めた (指摘 6。A (7) も同じ語)。
- **C-3 第 2 文 (新設)**: cursor を運ぶ要求が返す行 (位置に続く行) を言う文が無く、C-28 (ii) の assert に対応する義務が無かった (指摘 7。A (3) の末尾も同じ)。
- **C-4・C-5**: 鍵の無い token について「発行時と違う」は検出できないので、「recorded binding が request と違う」に改めた。C-4 の「他では意味を定めない」は C-5 の拒否と矛盾していたので「拒否」に改め、where は述語の並びまで含めて同じであることを明記した (指摘 9。A (5) も同じ)。

**【v0.6 (2026-09-24) で改めた案文 — 依頼者裁定 Q-3 の見直し 1 点 (§5.1)】**

- **C-4 (決定を覆した)**: 旧句「the same where predicates in the same order and the same order_by」を「the same where predicates, in any order, and the same order_by」に差し替えた。根拠: 述語の順序は位置を変えないので、順序違いの拒否は守るものの無い gate である (P-5)。AI エージェントは要求を再生成するとき述語の順を保つとは限らない。両 peer の束縛 hash を述語の順序に依らない形にする (D-3 の 3、D-2b の 5、D-6)。上の v0.4 の註の「where は述語の並びまで含めて同じであることを明記した」はこの改めで覆った。
- **A (4)・C-5 は変えない**: recorded binding が `where` を名指す形は、述語の並びに依らない束縛でもそのまま正しい。

**(D) `Page.cursor` の `maxLength` を外す (依頼者裁定 Q-5 = (a)、2026-09-24。§5.1)** (v0.5 までの見出しの括弧: 「案。依頼者裁定 Q-5 の対象。§5.2」)

> "cursor": {"type": "string"}

keyset cursor は**順序キーの値そのもの**を運ぶ (最大 10 項 + tie-break) ので、長い text 値を `order_by` に含めれば現行の `maxLength: 512` を超えうる。`maxLength` を外す形を案文とする根拠: (i) cursor は**サーバが発行してクライアントがそのまま返す値**であり、クライアントが長さを選ばない — 契約自身が `limits.enum_members` で「the length of any single member is bounded by request_bytes on the schema operation that declares it, as every other request-carried string is」(`spec/data-service-api.v1.json`:828) と述べるとおり、要求が運ぶ文字列の長さは `request_bytes` が bound する。(ii) P-5 — 守るものが無い bound を置かない。**両論と代替 (b) は §5.2 Q-5 に残す。** **【v0.6 (2026-09-24)】 依頼者裁定 (a) で確定した。両論と代替 (b) の記録は §5.1 の Q-5 へ移して残した。**

**根拠**

- **(1) 全順序**: 「決定的」を言うには全順序が要る。契約は tie-break の中身を言わない — r2db は `id`、MitateDB は D-2 の内部列であり、どちらも client の語彙に無い。`audit.query_ordering` が `(recorded_at, plane, event_id)` を**名指しできた**のは、監査 event が契約上の field を持つからである。entity query の行は Application が宣言した field しか持たず、一意な field を宣言する義務は無いので、同じ書き方はできない。**【v0.4 (2026-09-24) で改めた】 旧文「r2db は `id`、MitateDB は D-2 の内部列であり、どちらも client の語彙に無い」は r2db について偽である** — r2db の `id` は catalog の `fields` に出る宣言 field であり (`r2db-api/src/r2db_api/structured.py`:750-753)、select・where・order_by で名指せる。**改めた文: r2db は宣言 field `id` (catalog に出る)、MitateDB は client の語彙に無い内部列 `_mdb_row`。契約はどちらとも言わない** (設計レビュー 2 の指摘 3 への監督裁定。案文 A (1) と C-1 第 3 文を同じ趣旨に改めた)。§2.3 の「tie-break の値は Application-scoped」はどちらの peer でも真なので保つ。
- **(2) `next_page`**: 「非 null ⟺ 続きがある」が実需 (§1.1 (a-3)) の答えである。null が「末尾」を意味して初めて、消費者は完全性を証明でき、正直拒否の縮退を外せる。LIMIT size+1 の先読みは実装の自由として明示する (両 peer の現行手段である)。
- **(2a) 既定ページ (v0.3 (2026-09-24)。設計レビュー 1 の指摘 9 への裁定。Q-3 に含める)**: `page.size` を省いた要求のページは、**その要求が運べる最大の `page.size` と同じ** — 契約上限 1000・宣言 `limits.result_items`・要求の `budget.result_items` (あれば) の最小 — とし、`next_page` は同じ意味で続きの有無を告げる (案文 C-2 の末尾)。根拠: 1.9.0 は「null = 末尾」を約束するので、既定を実装任意にすると同じ要求が r2db (既定 100、`r2db-api/src/r2db_api/service.py`:719) では「続きがある」、MitateDB (`limit=None` → 黙った切り詰め、`MitateDB-api/src/mitatedb_api/cell.py`:2134-2137) では「全件読めた」になり、完全性の判定が両 peer で割れる。消費者は既に `min(limits.result_items, 1000)` を自分で計算して送っている (§1.1 (a-5)) — 欲しいのは最大のページである。**bound ではなく既定**なので P-5 に反しない。両 peer とも現行の既定を改める (r2db は D-3 の 9、MitateDB は D-2b)。**【v0.4 (2026-09-24) で改めた】** 「その要求が運べる最大の `page.size`」という言い方をやめ、「最小値 (1000・宣言 `limits.result_items`・要求の `budget.result_items`) の `page.size` を運んだものとして答え、ページはその件数**以下**」とする。根拠: r2db は `result_items` を返す行数で判定する (`r2db-api/src/r2db_api/structured.py`:923) ので、budget 3 の要求も `page.size` 1000 を「運べる」。定義が 2 つ並ぶと AI 読者が r2db で 1000 を計算しうる。どちらの peer の判定でも、既定 = 最小値なら `LIMIT_EXCEEDED` は起きない (設計レビュー 2 の指摘 6 への監督裁定)。この既定は義務 (7) として版に束ねる (v0.3 起草担当の疑義 2 への監督裁定)。既定ページの変更は client に見えるので D-5 の Revision note に書く (指摘 16)。
- **(3) keyset**: offset では (6) が言えない。offset は件数を数えるので、走査中に前方へ 1 行挿入されると既出の行をもう一度返し、末尾の 1 行を返さない。位置を符号化すれば、その行の順序キーが変わらない限り「ちょうど 1 回」が成り立つ。**性能は契約に書かない** (P-8 は計測の記録であり、契約の約束ではない)。文は「位置を符号化した」で止め、費用がページの深さに比例しないことだけを述べる。**【v0.3 (2026-09-24) で改めた】** 「費用がページの深さに比例しない」の 1 文も案文 C-3 から削った。根拠: 直後の「This contract states no performance figure」と同じ段落で読者にどちらが約束かを決めさせない、かつ義務にも C-28 にも無い強制されない説明文になる (P-3 / P-7。設計レビュー 1 の指摘 8 への裁定)。削った内容は D-7 の計測記録の項に置く。**【v0.4 (2026-09-24) で足した】** 案文 C-3 の第 2 文と A (3) の末尾に「cursor を運ぶ要求は、その位置に続く行を、その要求の `where` / `order_by` の下で返す」を置いた。位置の符号化だけでは返す範囲が決まらず、C-28 (ii) の「cursor 位置より前に挿入した行は返らない」の根拠が契約に無かった (設計レビュー 2 の指摘 7 への監督裁定)。
- **(4) 束縛**: 位置を決めるのは `where` と `order_by` だけである。`select` と `page.size` は位置を動かさない。依頼者裁定 Q-2 = **A** (§5)。**【v0.6 (2026-09-24)】** `where` の述語の順序も位置を動かさないので、束縛は述語の並びに依らない (依頼者裁定 Q-3 の見直し 1 点。§5.1、D-3 の 3)。
- **(5) 拒否**: `audit.query_cursor` と同じ判定 (復号できない / 束縛が一致しない) に、`errors.details_vocabulary` の 2 キーを与える。**`request_schema` を採るのは、cursor が「この endpoint の request schema が定める形の値でない」ためであり、`field` は path 規則どおり `page/cursor`** である。r2db の現行 `field: cursor` は path 規則に合っていないので 1.9.0 で直す (D-3)。MitateDB は既に `page/cursor` を使う (`http.py`:656)。**【v0.3 (2026-09-24)】** 拒否条件は 3 つ — (a) 復号できない、(b) 復号した順序値の個数か型がこの要求の順序 (`order_by` + tie-break) と合わない、(c) 束縛 (Application・entity・`where`・`order_by`) が発行時と違う。v0.2 の案文にあった「この実装が発行したものでない」は削った。根拠: cursor は鍵なし・署名なしであり (D-6、§4.1 の HMAC 却下)、サーバは自分が発行したかを判定する材料を持たないので、どの実装も満たせず C-28 でも検査できない義務になる (P-3。設計レビュー 1 の指摘 1 への裁定)。代わりに C-3 に「署名も暗号化も無い / 発行の有無は検出しない / 束縛が自 Application・entity・`where`・`order_by` の内側に留める」と、cursor が自分の行の順序値の復元可能な符号化であること (指摘 5 への裁定。declare-the-hazard) を書いた。obligation 名 `unusable_query_cursor_refused_as_a_request_schema_violation` は変えない。**【v0.4 (2026-09-24) で改めた】** (c) を「cursor が記録している束縛 (Application・entity・`where`・`order_by`) が、それを提示した要求と違う」に改める。根拠: 鍵の無い token を client が書き換えれば、実装は発行時の束縛を知る手段を持たないので、「発行時と違う」は字義どおりには守れず C-3 の「改変した token は自分の結果の中の任意の位置か拒否」と衝突する。C-4 の「他の組では意味を定めない」も C-5 の拒否と矛盾していたので「拒否」に改め、`where` は同じ述語を同じ順で、と明記した (設計レビュー 2 の指摘 9 への監督裁定。§10 の 10)。拒否条件の数は A (5) と C-5 で揃える (v0.3 起草担当の疑義 4、採用)。**【v0.6 (2026-09-24) で改めた】** 上の v0.4 の「`where` は同じ述語を同じ順で、と明記した」を「同じ述語を、順序を問わず」に改める (依頼者裁定 Q-3 の見直し 1 点。§5.1)。(c) の「束縛が要求と違う」は、述語の並びに依らない束縛どうしの比較として読む。
- **(6) 並行変更下の保証**: 実装が言える最大のことを言う。snapshot は約束しない (transaction を跨ぐ読み取り一貫性は本版の範囲外であり、P-1 に反する保持状態を要する)。**【v0.4 (2026-09-24)】** 順序項の値が走査中に変わった行は 2 回・1 回・0 回のいずれもありうる、と C-6 に書く (旧文の「once or not at all」は keyset では偽。§3 D-1 (C) の後の註、§10 の 7)。
- **(7) 失効が無いこと**: 無状態だから失効しない。`order_by` の field が schema 操作で消えれば、その要求自体が `NOT_FOUND` になる (現行どおり) のであって、cursor の失効ではない。
- **(8)** 1.9.0 は client に何も要求しない。**【v0.3 (2026-09-24)】** 案文 A は「1.8.0 で有効だった要求は**形の上で**有効のまま」と言い、版フリップ前に発行した cursor は跨いで使えなくてよい (paging.refusal のとおり拒否され、client は走査をやり直す) と明記する。旧 offset cursor を移行しない (D-3 の 6) ので、走査の途中で版フリップを跨いだ client の次の要求が拒否されるからである (設計レビュー 1 の指摘 13 への裁定。§10 の 9)。

### D-2. MitateDB の内部行順序列 (依頼者裁定 Q-1 = D-2)

**決定**: MitateDB の全 collection table に、**client に露出しない列**を 1 本足し、read の ORDER BY 末尾に `asc` で補い、cursor の tie-break にする。

| 項目 | 決定 |
|---|---|
| 列名 | **`_mdb_row`**。先頭 `_` は `identifiers.py`:19 の `^[a-z][a-z0-9_]{0,62}$` が構文で落とすので、client はこの名前を宣言も参照もできない。`_mdb_` 接頭辞は既存の内部表 `_mdb_schema_revision` / `_mdb_field_types` / `_mdb_idempotency` と同じ族である |
| 型 (PostgreSQL) | `BIGINT GENERATED ALWAYS AS IDENTITY`。`ALWAYS` なので insert 経路が値を与えることはできない |
| 型 (SQLite) | `INTEGER PRIMARY KEY` (SQLite の rowid alias。単調に増える) |
| 既定順序 | read の ORDER BY の末尾に `_mdb_row ASC` を常に補う (`order_by` が None のときは単独で `ORDER BY _mdb_row ASC`) |
| catalog | `field_types` は `_mdb_field_types` の行だけを返すので、隠し列は**既に**出ない (`backend_postgres.py`:504-539)。変更不要 |
| select | (v0.2 の決定) `cell.py::_select_fields` (:3066-3069) が `field_domains` をそのまま既定 select-all に使うので、**`field_domains` から `_mdb_row` を除外する**。これが唯一の除外点であり、`select` 明示指定・`where`・`order_by` はすべて `field_domains` を `available` として引くので (`_bind_order_by`:3173、`_bind_filters`)、1 箇所の除外で 4 経路が閉じる。**【v0.3 (2026-09-24) で改めた】 除外は `ApplicationCell` 側に 1 箇所置く** — `self._backend.field_domains(...)` を包む private helper を 1 本作り、cell 内の `field_domains` 呼び出し 6 箇所 (`MitateDB-api/src/mitatedb_api/cell.py`:1583, 1838, 3067, 3172, 3262, 3424。2026-09-24 の実測。指摘 18 が挙げた :2321 は comment 行) を全部そこへ通す。**backend 実装は触らない**。根拠: `field_domains` は backend ごとに 2 実装 (PostgreSQL は `information_schema`、SQLite は `PRAGMA table_info`) あり、v0.2 の書き方では除外をどちらに置くかが決まらず、片 backend だけ直すと SQLite を通る非 HTTP plug で `_mdb_row` が select-all に出る (設計レビュー 1 の指摘 18 への裁定)。C-28 の `test_c28_paged_traversal_is_the_unpaged_sequence` が select 未指定の走査で `items` の key 集合 = 宣言 field を観測する (D-4)。**【v0.4 (2026-09-24) で改めた】 「select 未指定の走査」は契約上送れない** (`QueryRequest.select` は required + `minItems: 1`、port `query_page` も `select` 必須)。観測を「`select` = 宣言 field 全部 → `items` の key 集合が宣言 field と完全一致 (`_mdb_row` も `id` 以外の未宣言列も出ない)」に置き換える。helper による除外の決定は変えない — 除外が要るのは cell 内部の `field_domains` 呼び出し 6 箇所のためである。**helper の除外は MitateDB 側の単体テストで固定する (WP-3)** (v0.3 起草担当の疑義 1 への監督裁定。:3424 の実測は疑義 6 として採用) |
| add_field | 同名の宣言は `identifiers` の構文で落ちる (先頭 `_`)。**追加の拒否経路は書かない** — 二重の防御を足すより、構文 1 点で落ちることをテストで固定する方が形が小さい |
| 応答 | `read` が返す dict は `selected` の列だけなので、除外の結果として応答に出ない。**【v0.3 (2026-09-24) で足した】 順序項と tie-break の列は、`select` に無くても内部射影に加え、応答を組む直前に落とす** — `read` の `selected` に `order_by` の列と `_mdb_row` を内部で足し (cursor を作るには最終行の順序値と tie-break が要る)、cell が `select` の分だけを返す。根拠: 束縛から `select` を外した (Q-2 = A) ので `order_by` が `select` に無い field を名指す要求は正当であり、`SELECT {selected}` (`MitateDB-api/src/mitatedb_api/backend_postgres.py`:1398-1399) のままでは `next_page` を作れない。「order_by の field を select に足す」対処は未宣言の列と `_mdb_row` を応答に出す (設計レビュー 1 の指摘 2 への裁定。r2db 側は D-3 の 10) |
| PostgreSQL migration | 新規 `migrations/0015_row_order_column_upgrade.sql` (**per-application UPGRADE script**)。`platform_upgrades.py` の `PLATFORM_UPGRADE_NUMBERS` に `15` を足し、`0003_provision_application.sql` の seed list (:267 の `INSERT INTO public._mdb_platform_upgrades ... VALUES`) にも足す。三方一致テスト `tests/test_platform_upgrade_ledger_scan.py::test_real_migrations_three_way_match` がこの 3 箇所を機械照合する。新規 provision の `CREATE TABLE` 経路 (`backend_postgres.py`:939) にも同じ列を足す |
| 適用 | `python -m mitatedb_api.ops upgrade-applications --lock-timeout <v>` (`ops.py`:1680-1711)。script は application DB 内の**宣言 collection table を列挙して各々に `ALTER TABLE ... ADD COLUMN`** する。既存行への採番は PostgreSQL が行う (table rewrite + ACCESS EXCLUSIVE lock。`--lock-timeout` が必須引数であることは R-45 で既に効いている)。**【v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 15 への監督裁定】 列挙元**は `information_schema.tables` の `public` の `BASE TABLE` から、`_mdb_` で始まる表と `audit_events` を除いた集合とする。application DB に宣言 collection 以外の表を作る経路は無いので、collection の superset として安全である (`_mdb_schema_revision` / `_mdb_field_types` / `_mdb_platform_upgrades` / `_mdb_idempotency` は除外される。`audit_events` は予約名、`MitateDB-api/src/mitatedb_api/postgres_reserved_names.py`:14)。**冪等**: `ALTER TABLE … ADD COLUMN IF NOT EXISTS _mdb_row BIGINT GENERATED ALWAYS AS IDENTITY` (per-application upgrade の既存の慣例 `MitateDB-api/migrations/0010_idempotency_records_upgrade.sql` と同じ形)。`_mdb_field_types` の `DISTINCT entity` との一致 (0 field の collection の有無を含む) は**実装担当が実測して §11 に記す**。全 collection を 1 transaction で書き換えるので、**lock の保持時間はデータ量に比例する** (`--lock-timeout` が縛るのは取得だけ)。これを MitateDB README の upgrade 節と §10 の 13 に開示する |
| SQLite backend | 本番経路ではない (`README.md`:52-54「never a deployment target」、`main.py`:127/:463 は PostgresBackend だけ)。migration 機構も無い (`backend_sqlite.py` に `migrat` 文字列 0 件)。したがって**移行は無く、`CREATE TABLE` に列を足すだけ**である。ただし conformance の `MitateDB-api` plug は in-process = SQLite を通るので、**C-28 は SQLite backend でも駆動する** |
| isolation | database-per-application (`backend_postgres.py`:79) なので `_mdb_row` の値は Application-scoped であり、他 Application の存在・活動を推測させない (SI-01。`addressability.assigned_identifiers` と同じ性質) |
| `row_addressability` | **`unavailable` のまま**。`_mdb_row` は address ではない — 宣言されず (catalog に出ない)、可視でなく (select できない)、targetable でなく (where に書けない)。契約 `structured_operations.addressability.properties` の 4 性質のいずれも主張しない |

**根拠**: MitateDB の行は現状「何をもって 2 行を区別するか」を持たない。全順序を持たない以上、(1) も (6) も言えない。保存形を変えるのが唯一、保証を完全にする道である (依頼者裁定 Q-1、§5)。代替案は §4 に残す。

#### D-2a. MitateDB の両 backend で NULL の位置を揃える (監督裁定 2026-09-24。WP-4 の内容)

**問題 (実測)**: `backend_postgres.py`:1397-1442 と `backend_sqlite.py`:553- はどちらも `ASC` / `DESC` しか組み立てず、`NULLS` 句を 1 箇所も持たない (grep 実測で `NULLS` 不出現)。既定は PostgreSQL が **asc → NULLS LAST / desc → NULLS FIRST**、SQLite が **asc → NULL が先頭 / desc → NULL が末尾**で、**逆である**。conformance は非 HTTP plug (`MitateDB-api`) を SQLite で、`MitateDB-api-http` / `-socket` を PostgreSQL で駆動するので、**同じ peer の plug どうしで NULL を含む列の順序が食い違う**。

**決定**: **両 backend の ORDER BY に `NULLS` 句を明示し、PostgreSQL 既定に揃える** — `asc` → `NULLS LAST`、`desc` → `NULLS FIRST`。keyset 述語の NULL 分岐も同じ規則で書く (D-3 の 4 が r2db について書くのと同じ形)。これで **peer の中では順序が 1 つ**になり、C-28 (vi) が同じ peer の全 plug で同じ順序を観測する。**契約は peer 間の NULL 位置を揃えない** (D-1 (C-1) の文は現行どおり) — 揃うのは MitateDB の内部の話である。**【v0.4 (2026-09-24) で改めた。設計レビュー 2 の指摘 11 への監督裁定】 上の「これで peer の中では順序が 1 つになり」を「NULL の位置は peer の中で 1 つになる。文字列の照合順序は backend と配備の既定による (SQLite は BINARY、PostgreSQL は DB の既定)」に改める。** 根拠: MitateDB の application DB は照合順序を指定せずに作られ cluster の既定を継ぐ (`MitateDB-api/migrations/0003_provision_application.sql`:63)。SQLite backend は BINARY 照合である。object / array / json は正規化 JSON の TEXT として保存されテキスト順に並ぶ (`MitateDB-api/src/mitatedb_api/postgres_types.py`)。したがって text 列の並びは PostgreSQL の plug と SQLite の plug で割れうる。C-28 は plug ごとの自己一致しか見ないので赤にはならず、偽だったのは設計の主張である。案文 C-1 の最終文は照合順序と string / number / boolean 以外の値の比較を実装任意に含めた (§10 の 1)。

**実測 (2026-09-24)**: SQLite が `NULLS FIRST` / `NULLS LAST` を解するのは **3.30 以降**である。本リポジトリの `.venv` の Python が抱える sqlite は `sqlite_version` **3.53.4** (`.venv/bin/python -c "import sqlite3; print(sqlite3.sqlite_version)"` の実測) であり、条件を満たす。**実装担当は同じ計測を CI の Python (3.11 / 3.12 の両 job) でも行い、下回る環境が無いことを確認してから書く** (`OC` §1.5 の 34)。下回る環境があれば、SQLite 側は `CASE WHEN <col> IS NULL THEN 1 ELSE 0 END` を先行項に置く形へ落とす。

#### D-2b. MitateDB の read 入口 — cursor 値の検査、`page.size` の契約範囲、既定ページ (v0.3 (2026-09-24)。WP-4 の内容)

1. **復号した順序値の検査** (設計レビュー 1 の指摘 3 への裁定。r2db 側は D-3 の 4): 述語を組む前に、(a) 値の個数が order_spec (`_mdb_row` 込み) と一致すること、(b) 各値が当該列の宣言型に適合すること を、**`where` 値の型検査と同じ経路**で検査する。外れたら D-1 (5) の拒否 (`VALIDATION_FAILED` / `request_schema` / `page/cursor`)。**PostgreSQL と SQLite の両 backend で同じ検査を Python 側で行う** — SQLite は型親和性で黙って通るので、DB の型エラーに任せると同じ peer の plug どうしで同じ不正 cursor の結果が割れる。**【v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 14 への監督裁定】 この経路で `check_declared_value` (`MitateDB-api/src/mitatedb_api/field_types.py`:143) と backend の `encode_value` (`backend_postgres.py`:1227、`backend_sqlite.py`:464) が送出する `ValidationError` は、すべて `VALIDATION_FAILED` / `violated_declaration: request_schema` / `field: page/cursor` の 2 キーに写し替え、元の details は捨てる** — 写し替えを忘れると details.field が request に存在しない位置 (`where/<i>/value`) を指し、C-5 の「names that position … and nothing else」に反する。NUL を含む値は PostgreSQL の plug だけで拒否され SQLite の plug は受理する (改変 token についての差であり C-3 が許す範囲。§10 の 11)。
2. **`page.size` の契約範囲** (指摘 12 への裁定 (b)): `http.py` の Page 受理の直後に、契約 `Page.size` の下限 1 と上限 1000 の検査を足し、外れたら `VALIDATION_FAILED` / `violated_declaration: request_schema` / `field: page/size` にする。**配備 bound の検査より先に、配備値に依らず**行う。`_check_object_shape` (`MitateDB-api/src/mitatedb_api/http.py`:282-330) は `minimum` / `maximum` を検査しないが、**触らない**。現行は 0 も 1001 も `cell.py`:2136-2137 の `LIMIT_EXCEEDED` / `result_items` に落ち、`max_result_rows` ≥ 1001 の配備では 1001 が無検査で通る (固定テスト 0 件。2026-09-24 の実測)。配備 bound (`result_items`) 超過は現行どおり `LIMIT_EXCEEDED` のままである (C-05 の領域)。**【v0.4 (2026-09-24) で検査位置を改めた。設計レビュー 2 の指摘 4 への監督裁定】 検査は `http.py` には置かず、`ApplicationCell.read` (`MitateDB-api/src/mitatedb_api/cell.py`:2103。HTTP と in-process の共通入口) の `limit` 受理の直後、配備 bound の検査 (:2136) より先に置く。`limit` が与えられたときだけ 1..1000 を検査し、外れたら上と同じ拒否にする。** 根拠: in-process の conformance adapter は `session.read(..., limit=limit)` を直接呼び `http.py` を通らない (`MitateDB-api/conformance/conformance_adapter_mitatedb.py`:1354) ので、`http.py` に置くと `MitateDB-api` plug で `test_c28_page_size_outside_schema_is_refused_at_page_size` が `LIMIT_EXCEEDED` のまま残り、WP-6 の版フリップで初めて赤になる。二重にしないため `http.py` には置かない。
3. **既定ページ** (指摘 9 への裁定。D-1 根拠 (2a)): `limit=None` のとき、`limit` を D-1 (2a) の最小値 (契約上限 1000・`max_result_rows`・`budget.result_items`) にし、**先読み (size + 1) で `next_page` を返す**。現行の「`limit = limits.max_result_rows` で黙って切り詰める」(`cell.py`:2134-2135) が消える。
4. **cursor 付き読み出しの口 (v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 4 への監督裁定)**: `cell.read` は rows だけを返し `next_page` を返す口が無い (`MitateDB-api/src/mitatedb_api/http.py`:670 のコメント、:675)。**cursor 付きの読み出しは `(rows, next_page)` を返す新しい cell メソッドとし (名前は実装で決める)、既存の `read` は rows だけを返す現行の形のまま、そのメソッドに委ねる。** 既存の呼び出し側 (`select_eq` ほか) は触らない。`http.py` と in-process adapter の `query_page` は新メソッドを呼ぶ。 **【v0.5 (2026-09-24) で足した。作業指示書起草時の疑義 4 への監督裁定】 この新メソッドは WP-2 で置く。入口は `ApplicationRuntime` (`MitateDB-api/src/mitatedb_api/cell.py`:3648 の `read` と並ぶ位置。`http.py` と in-process adapter が呼ぶ層)、実体は `ApplicationCell` に置く (runtime の入口 → cell の実体。同日、起草担当の疑義への監督裁定)。上の「新しい cell メソッド」はこの形で読む。WP-4 までの本体は、cursor ありなら現行 `http.py` (`MitateDB-api/src/mitatedb_api/http.py`:654-657) と同じ拒否 (`CAPABILITY_UNSUPPORTED` / `violated_declaration: capability` / `field: page/cursor`) を、cursor なしなら `(rows, None)` を返す。`http.py` の query endpoint は同じ WP-2 でこの入口を呼ぶ形に切り替え、`http.py` 側の拒否を消して拒否の置き場を 1 箇所にする。adapter は cursor を逐語で渡すだけになり、拒否を捏造しない (D-4)。WP-4 は cell の実体を差し替える。** 根拠: in-process の conformance adapter は `http.py` を通らない (`MitateDB-api/conformance/conformance_adapter_mitatedb.py`:1354) ので、WP-2 の時点で in-process plug の `query_page` が cursor を peer へ運ぶ口が無かった。
5. **束縛 (v0.6 (2026-09-24)。依頼者裁定 Q-3 の見直し 1 点 (§5.1)。WP-4 の内容)**: MitateDB の cursor の束縛 hash も (Application, entity, 正規化した `where`, `order_by`) とし、r2db と同じ helper `canonical_page_binding` (D-6。両 peer 同名・同一本体) で作る。`where` の正規化は D-3 の 3 と同じである。helper には peer 固有の型 (`Filter` 等) を渡さず、呼び出し側が素の値に変換してから渡す (`normalize_request_for_plan` の既存の形。`MitateDB-api/src/mitatedb_api/cell.py`:67-103 の docstring)。codec は束縛の hash を引数で受ける形のまま (D-6)。

### D-3. r2db の cursor を offset から keyset へ置換

**決定**

1. `paging.py` の `_encode_cursor` / `_decode_cursor` / `_shape_hash` / `MAX_CURSOR_OFFSET` を keyset 形へ置き換える。codec は D-6 の同名 helper とする。`MAX_CURSOR_OFFSET` は**消える** (offset が無いので上限も無い。P-5)。
2. `_resolve_order_by` の暗黙 tie-break `("id","asc")` は**現行どおり**。これが keyset の最終項になる。
3. **shape hash を `where` + `order_by` に狭める** (application_id と entity は引き続き含む。`select` と `size` を外す)。依頼者裁定 Q-2 = A の帰結であり、訂正記録 m-3 (`R2DB_CCR13_STORAGE_V1.md`:243) の網が「位置を決める field と決めない field」を区別しなかったことの是正として記録する (D-5)。**【v0.6 (2026-09-24) で改めた。依頼者裁定 Q-3 の見直し 1 点 (§5.1)】 束縛 hash は (application_id, entity, 正規化した `where`, `order_by`) とする。`where` の正規化 = 各述語を (field, operator, 値の正規 JSON) の 3 つ組にし、整列した list を `sort_keys=True` の JSON にする。** これで同じ述語を並べ替えただけの要求は同じ束縛になる (v0.5 までは順序つきの list を hash する現行の形のままだった。`r2db-api/src/r2db_api/paging.py`:99)。`order_by` は並びが順序を決めるので正規化しない。hash は両 peer 同名の helper `canonical_page_binding` で作り (D-6)、MitateDB も同じ helper で同じ正規化をする (D-2b の 5)。値の同一性の扱いは §10 の 14。
4. **SQL の形**。`postgres_sql.py::_select_statement` から `OFFSET` を外し、`where_sql` に keyset 述語を AND で足して `LIMIT size+1` だけを残す。order_spec が `(f1,d1), (f2,d2), ..., (id,asc)` のとき、述語は**辞書式の展開形**とする。

   ```
   (f1 >op1> v1)
   OR (f1 =eq= v1 AND f2 >op2> v2)
   OR (f1 =eq= v1 AND f2 =eq= v2 AND ... AND id > vid)
   ```

   - `>op>` は `asc` なら `>`、`desc` なら `<`。
   - **row-value 比較 (`(a,b) > (x,y)`) は方向が全項で揃うときだけ使える**ので、混在を許す以上は展開形を正本とする (方向が揃う場合だけ別経路を作らない — 1 つの形で両方を賄う。シンプルさの原則)。
   - **NULL の位置**: 現行の意味 (asc → NULLS LAST、desc → NULLS FIRST。PostgreSQL 既定であり `inmemory_sort.py`:24-26 の `_sort_key` が同じ規則) を保つ。したがって等号・不等号は NULL を「最大値」として扱う形に書く必要がある — 具体的には、各項の比較を「値が NULL か否か」で分岐した述語として組む (`col IS NOT NULL` / `col IS NULL` を含む形)。素の `col > %s` は NULL 行を落とすので使えない。
   - **型跨ぎ (untyped/JSONB 列)**: (v0.2 の決定) 比較演算子はそのまま jsonb の順序 (String < Number < Boolean < Array < Object) に従う。バインドする cursor 側の値も jsonb として渡し、Python 側で型を判定しない。**【v0.3 (2026-09-24) で撤回】「Python 側で型を判定しない」を撤回し、この項を次のとおり改める。** 根拠: cursor は client が書き換えられる。個数か型が合わない値をそのまま述語にバインドすると、PostgreSQL は型エラーを投げ、r2db は `SERVICE_UNAVAILABLE` (503。`r2db-api/src/r2db_api/postgres.py`:1372-1373)、MitateDB は `ValidationError` に落ち、SQLite は型親和性で黙って通る — **同じ不正 cursor が 503 / 400 / 200 に割れ**、D-1 (5) の「VALIDATION_FAILED」に反する。typed 列のバインド方法も v0.2 は決めていなかった (設計レビュー 1 の指摘 3・10 への裁定)。
     - **(4a) 検査**: 復号した順序値は、述語を組む前に (a) 個数が order_spec (tie-break `id` 込み) と一致すること、(b) 各値が当該列の宣言型に適合すること (**`_validate_predicate_types` と同じ判定**。`r2db-api/src/r2db_api/value_types.py`:177) を検査し、外れたら D-1 (5) の拒否 (`VALIDATION_FAILED` / `request_schema` / `page/cursor`) にする。**PostgreSQL cell と in-memory cell で同じ検査を Python 側で行う** (backend で挙動を割らない)。MitateDB 側は D-2b の 1。**【v0.4 (2026-09-24) で改めた。設計レビュー 2 の指摘 14 への監督裁定】 上の (b) の「`_validate_predicate_types` と同じ判定」を「各値を `_check_type(value, field_type, "page/cursor")` (`r2db-api/src/r2db_api/value_types.py`:54。`constraints=None`、null は常に受理) で検査する。`_validate_predicate_types` は使わない」に改める。** 根拠: `_validate_predicate_types` は `eq` / `ne` の None を `nullable` の details (`where/<i>/value`) で拒否する (`value_types.py`:215)。keyset の等号項を `Predicate(..., "eq", None)` として流用すると、最終行の順序項が null のページの次が必ず拒否され、C-28 の NULL 変種は WP-6 まで non-strict に隠れる。
     - **(4b) バインド**: cursor 側の値は既存の **`_bind_value(value, table_info.columns[col])`** (`r2db-api/src/r2db_api/postgres_sql.py`:77) を通してバインドする — typed 列は native、untyped / object / array は `Jsonb`。untyped 列の跨型比較は PostgreSQL の jsonb 順序 (String < Number < Boolean < Array < Object) にそのまま従う。
   - `sql.Literal` を使う既存の作法 (`postgres_sql.py`:60-66 の comment) に倣い、cursor から復元した値は**必ず bind parameter** で渡す (client 由来の値であり、literal 合成しない)。
5. **in-memory cell** (`structured.py::ApplicationCell.query`): `rows` を `_sort_rows` した後、`offset` の代わりに **`_sort_key` を使った位置比較**で cursor 位置の直後から窓を取る。`inmemory_sort.py::_sort_key` が既に NULL と型跨ぎの全順序を与えているので、keyset 述語は「order_spec の各項の `_sort_key` を direction ごとに比較する辞書式比較」1 つで書ける。SQL 側と同じ規則である (両 cell が同じ結果を返すことは既存の要求。`postgres.py`:1340 のコメント)。
6. **旧 offset cursor は移行しない**。復号に失敗して `VALIDATION_FAILED` になる (D-1 (5))。cursor は 1 回の走査の間だけ生きる値であり、版フリップと同一コミットで切り替わる。**offset を併存させない** — 1 つのフィールドに 2 つの意味を持たせない (P-6 / P-7)。
7. `violation("request_schema", field="cursor")` を **`field="page/cursor"`** に直す (`paging.py`:110-120)。契約の path 規則に合わせる是正であり、D-1 (5) の文と一致させる。**【v0.4 (2026-09-24) で足した】** `r2db-api/src/r2db_api/request_shape.py`:22 (cursor が string でないときの `field="cursor"`) も同じく `page/cursor` に直す (設計レビュー 2 の指摘 13 への監督裁定)。
8. **`validate_page_size` の details を直す (監督裁定 2026-09-24)。** 現行は `page.size` が契約上限 1000 を超えたとき `violation("budget", field="page_size")` を、0 以下のとき `LIMIT_EXCEEDED` + `limit_class: result_items` を返す (`paging.py`:44-48)。**どちらも `VALIDATION_FAILED` / `violated_declaration: request_schema` / `field: page/size` に揃える** — 契約 `Page.size` は `{minimum: 1, maximum: 1000}` の schema であり、その外側の値は**この contract 自身の request schema に合わない要求**だからである (`errors.details_vocabulary.violated_declaration_vocabulary` の `request_schema` の定義そのもの)。`page_size` という path も request body の位置ではない。**実装担当は C-05 / C-24 の既存の期待 (`result_items` / `budget` の refusal 位置) を壊さないことを `tools/dev/pt.py` で確認してから直す** — `result_items` は配備 bound であって契約 schema の上限ではなく、こちらは現行どおり `LIMIT_EXCEEDED` のままである。**【v0.3 (2026-09-24) で足した】** この是正は 1.9.0 の 6 義務 (v0.4 で 7 義務) に入らないので、client が拒否コードの変化を知れるよう `spec/CONTRACT_HISTORY.md` の Revision note に「1.9.0 で `Page.size` 範囲外の拒否を `request_schema` / `page/size` に揃えた」と明記し (D-5)、C-28 に node `test_c28_page_size_outside_schema_is_refused_at_page_size` を置く (D-4)。MitateDB 側も同じ拒否に揃える (D-2b の 2)。r2db の旧 details を固定する既存テスト 4 箇所 — `r2db-api/tests/test_foundation.py`:363-365 (0)、:2879-2891 (1001 / 1000 の境界)、:2895-2903 (`validate_page_size` 直接)、`r2db-api/tests/test_http.py`:368-375 (HTTP 1001 → 400) — を WP-5 で新しい details に更新する (設計レビュー 1 の指摘 12 への裁定 (b))。
9. **既定ページ (v0.3 (2026-09-24)。D-1 根拠 (2a))**: `page.size` 省略時の既定 100 (`r2db-api/src/r2db_api/service.py`:719, :726 の `page_size: int = 100`) を廃し、D-1 (2a) の最小値 (契約上限 1000・`limits.result_items`・`budget.result_items`) にする。先読み (size + 1) と `next_page` の返却は通常のページと同じ経路である。
10. **内部射影 (v0.3 (2026-09-24)。設計レビュー 1 の指摘 2 への裁定)**: **順序項と tie-break の列は、`select` に無くても内部射影に加え、応答を組む直前に落とす**。`_select_statement` の columns を `select` ∪ order_spec の列 (tie-break `id` 込み) とし、`items` は `select` の分だけを組む。in-memory cell も同じ (cursor は order_spec の全列の値から作り、`items` は `select` の分だけ)。MitateDB 側は D-2 の「応答」行。

### D-4. conformance port と新条件 C-28

**決定 (port、v1.16)**: `ConformanceAdapter` に query 1 本を足す。既存の `select_eq` / `attempt_filter` は `order_by` も `cursor` も持たないので、それらの引数を増やすのではなく**独立の抽象メソッド**として置く (既存 20 数本の呼び出し側を触らない)。

```python
@abstractmethod
def query_page(
    self,
    session,
    entity: str,
    select: Sequence[str],
    *,
    where: Sequence[tuple[str, str, Any]] | None = None,
    order_by: Sequence[tuple[str, str]] | None = None,
    page_size: int | None = None,
    cursor: str | None = None,
    budget: Mapping[str, int] | None = None,
) -> tuple[list[dict], str | None]: ...
```

- **【v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 5 への監督裁定】** `budget` (keyword-only) を足した。`None` は要求に載せない (`query_with_budget` と同じ規約。`conformance-tests/adapter.py`:2874-2883)。docstring の約束に「`budget` は要求の `budget` として逐語で運ぶ」を 1 行加える。既存の `query_with_budget` は order_by も cursor も page_size も持たないので、既定ページの node を表せる port メソッドが v0.3 には無かった。

- 返り値は `(items, next_page)` の 2 つ組。`next_page` は peer が返した値をそのまま返す (adapter が解釈も生成もしない)。
- `where` は `attempt_filter` の `extra_predicates` と同じ `(field, operator, value)` の並び。`order_by` は `(field, direction)` の並び。**adapter は peer の実 query 入口へ逐語で渡す** (`select_eq` の docstring が既に述べる原則)。
- 拒否は既存の `ConformanceDenial` で表す (code + details)。**adapter 自身が拒否を捏造しない。**
- 6 plug 全部に実装する (`r2db-api` / `MitateDB-api` の in-process・http・socket)。`docs/design/CONFORMANCE_ADAPTER_V1.md` §4.4 の port 定義に 1 行足す。

**決定 (共通条件 C-28)**: `conformance-tests/test_c28_keyset_paging.py`、`@pytest.mark.condition("C-28")`。1.9.0 の 6 義務を観測する (**v0.4 (2026-09-24): 義務は 7 件。(7) 既定ページは `test_c28_default_page_is_the_largest_page` が観測する**)。

| # | 観測 | 何が赤になるか |
|---|---|---|
| (i) | ページを連結した列 = 1 回の全件読み (同じ `where`/`order_by`、`page.size` を全件より大きく) の列。**要素の重複も欠落も 0**。`next_page` は最終ページだけ null、それ以外は非 null。**【v0.3 (2026-09-24) で足した】 `order_by` が `select` に無い field を名指す走査でも成り立ち、`items` の key 集合が `select` と完全一致する。`select` 未指定の走査では `items` の key 集合が宣言 field と完全一致する** (設計レビュー 1 の指摘 2・18 への裁定)。**【v0.4 (2026-09-24) で改めた】 後段を「`select` = 宣言 field 全部の走査で `items` の key 集合が宣言 field と完全一致する (`_mdb_row` も `id` 以外の未宣言列も出ない)」に置き換える** (`select` 未指定は契約上送れない。v0.3 起草担当の疑義 1 への監督裁定) | 全順序の欠落 (tie-break を外す)、`next_page` の恒常 null、先読みの off-by-one、順序項・tie-break・`_mdb_row` の応答への漏れ、片 backend だけの除外 |
| (ii) | 走査の途中で、cursor 位置より**前**に並ぶ行と**後**に並ぶ行を 1 件ずつ挿入 → 前の行は現れず、後の行は現れ、既出の行は依然ちょうど 1 回。**挿入する 2 行の order key は、その entity の中で一意になる値を選ぶ** — 既存行と同値の群に入れると、前後どちらに並ぶかが実装の tie-break の値で決まり、観測が実装依存になる (監督の追加 2026-09-24)。**【v0.3 (2026-09-24) で改めた】 assert は「既出の行はちょうど 1 回」と「cursor 位置より前に挿入した行は返らない」(後者は D-1 (3) の位置の意味から導ける) の 2 つに絞る。「後に挿入した行が現れる」は記録のみで assert しない** — 契約 C-6 は走査中に挿入した行を「once or not at all」としか言わないので、それを assert すると契約が開けた自由度を条件が塞ぐ (設計レビュー 1 の指摘 6 への裁定 (a)。C-6 は変えない)。**【v0.4 (2026-09-24) で根拠を付け替えた】 「cursor 位置より前に挿入した行は返らない」の根拠は、案文 C-3 第 2 文 (cursor を運ぶ要求は位置に続く行を返す) である** — D-1 (3) の位置の符号化は返す範囲を言わない (設計レビュー 2 の指摘 7 への監督裁定)。C-6 第 3 文は v0.4 で改めたが、挿入行についての文 (once or not at all) は変わらない | **offset 方式との判別**。offset なら既出行が重複する |
| (iii) | 同じ `where`/`order_by` のまま `select` と `page.size` を変えても cursor は有効。`where` か `order_by` を変えると `VALIDATION_FAILED` / `request_schema` / `page/cursor`。復号不能な文字列も同じ。**【v0.3 (2026-09-24) で足した】 復号できるが順序値の個数か型が合わない cursor も同じ拒否** (設計レビュー 1 の指摘 3 への裁定)。**【v0.6 (2026-09-24) で足した。依頼者裁定 Q-3 の見直し 1 点 (§5.1)】 同じ `where` の述語を並べ替えただけの要求でも cursor は有効 (拒否されず、続きのページを返す)。上の「`where` を変える」は述語の集合を変えることを指す** | 束縛範囲 (Q-2 = A)。型の合わない値を DB にバインドして 503 / 200 に割れる実装。**v0.6: `where` を順序つきで hash する実装 (並べ替えで拒否)** |
| (iv) | 別 Application (および別 entity) で発行した cursor は `VALIDATION_FAILED` — 越境しない、かつ details に他 Application の事実が出ない | SI-01 / SI-10 |
| (v) | **無状態 (セッションに依らないこと)**: 同一 Application の**別 credential で認証し直した別セッション**で、先のセッションが受け取った cursor から続行でき、(i) の連結が成り立つ。HTTP / socket plug では**新しい client 接続**を張る。**`iso` (`isolated_application_surface()`) は使わない**。**【v0.4 (2026-09-24) で消した】 「HTTP / socket plug では新しい client 接続を張る」は消す** — port v1.16 には新しい接続を張らせる手段が無く (HTTP plug は 1 本の httpx client を共有し、既定では ASGI transport で実 socket を持たない。`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`:899, :909)、port は増やさない。接続の独立は port から観測しないことを C-28 の Status に開示する (設計レビュー 2 の指摘 12 への監督裁定) | cursor をセッション・接続・credential に紐づける実装が赤になる (**v0.4: 「接続」は観測しない。赤になるのはセッション・credential に紐づける実装**)。**枠の原文は C-25 と同じ `iso` surface で発行した cursor をセッション surface で使う形だったが、実測 (`adapter.py`:1629-1656) では `isolated_application_surface()` は「a FRESH, throwaway data-plane instance」であり、in-process plug では別 composition・別 Application になるので、(iv) の束縛により必ず拒否される。監督裁定 (2026-09-24) により本行の形に置き換えた** |
| (vi) | `order_by` に **NULL を含む field** と **方向混在 (`desc` + `asc`)** を含めても (i) が成り立つ | keyset 述語の NULL 分岐と展開形 |
| (vii) | 版ゲート: C-21 / C-25 と同じ `adapter.parse_semver` 機構。`< 1.9.0` は `xfail(strict=True)`、本体の assert はそのまま実行する。**【v0.3 (2026-09-24) で改めた】 (ii) の node だけ `xfail(strict=True)`、他の node は `< 1.9.0` で `xfail(strict=False)`** (本体は実行する)。根拠: r2db は現行でも shape hash に application_id / entity を含み、cursor は session に紐づかず決定的なので、(i)(iv)(v)(viii) は 1.8.0 宣言のまま通る。全 node を strict にすると WP-2 のコミットで XPASS = 赤になり、offset 実装でも通る義務 (1)(2)(4)(5) を 1.8.0 宣言下で「落ちるべき」と主張することになる。offset との黒箱判別は (ii) だけなので、版フリップと実挙動の同一コミット規則の施行装置は (ii) に置く (設計レビュー 1 の指摘 4 への監督裁定)。**【v0.4 (2026-09-24) で改めた。設計レビュー 2 の指摘 1 への監督裁定】 上の「全 node を strict にすると WP-2 のコミットで XPASS = 赤になり」を次に改める: 完了ゲートと CI は xfailed と xpassed の両方を 0 でなければ赤とする (`OC` §1.3 の 22、`tools/dev/gate.py`:88)。したがって strict / non-strict の区別が意味を持つのは統合 branch の途中の状態に限る (§9 の統合 branch)。main では全 plug が 1.9.0 を宣言するので、`< 1.9.0` の分岐は実行されない。** non-strict を選ぶ理由は「branch の途中で、offset でも通る義務を『落ちるべき』と主張しない」だけに縮める | 宣言と実挙動の乖離 ((ii) は strict で。keyset を実装した peer が 1.9.0 を宣言するまで XPASS で赤) |
| (viii) | **決定性**: 保存内容を変えずに同一要求を 2 回送ると、返る `next_page` の値が**一致する** (`dry_run.plan` の「opaque but deterministic token」と同じ性質)。**(v) と合わせて、cursor がサーバ側の採番・時刻・乱数・セッション識別子を含まないことの証拠になる** (監督裁定 2026-09-24)。**【v0.4 (2026-09-24) で縮めた】 観測できるのは「同一要求で同一 token」までである** — 秒や日の単位の時刻を混ぜた token は連続 2 要求で一致して通るので、時刻を含まないことは port から観測しない (設計レビュー 2 の指摘 12 への監督裁定の追随。C-28 の Status に開示) | cursor に nonce・発行時刻・連番を混ぜた実装が赤になる (**v0.4: 要求ごとに変わる値を混ぜた実装が赤になる。粗い時刻は赤にならない**) |

- **空振り禁止** (`OC` §1.5 の 32): 各 plug で (i) の観測件数 ≥ 1 (= 少なくとも 2 ページに分かれた)、(ii) の挿入 2 件、(v) の別セッションが実際に別の認証を通ったことを assert する。`observed_branch` を plug 自身の宣言版と突合する (C-21 / C-25 と同じ形)。**【v0.3 (2026-09-24)】 strict の node ((ii)) と non-strict の node (他のすべて) の両方で `observed_branch` を plug の宣言版と突合する。** **【v0.4 (2026-09-24) で改めた。設計レビュー 2 の指摘 10 への監督裁定】 `observed_branch` の突合は、C-21 / C-25 と同じく `>= 1.9.0` の分岐でだけ行う** (フェーズ9 作業指示書 訂正註 7、監査変異 E3/E2。`conformance-tests/test_c25_result_request_id.py`:433-450、`conformance-tests/test_c21_denial_details_vocabulary.py`:366-385)。**`< 1.9.0` の分岐では、本体の無条件 assert (非空振りの件数 assert を含む) が検出の全部である。** `< 1.9.0` でも突合すると、hardcode された `observed_branch` と `expected_branch` が常に食い違って本体が通っても落ち、strict の XPASS が構造的に起きない。**【v0.4 で足した】 既定ページの node は、`request_budget` を enabled と宣言する plug では `budget` の経路が実際に走ったことを assert する (現行 6 plug はすべて enabled なので、この経路が非空振りの証拠になる)。**

**node の分割 (v0.3 (2026-09-24)。設計レビュー 1 の指摘 4 への監督裁定)**: 上の観測を次の 9 node に分ける。**node 名は案であり、実測の後に確定する** (`OC` §1.5 の 34)。6 plug で駆動する。

| node (案) | 観測 | 版ゲート (`< 1.9.0`) |
|---|---|---|
| `test_c28_paged_traversal_is_the_unpaged_sequence` | (i) + (vi) + `items` の key 集合 (`order_by` が `select` に無い field を名指す走査で key 集合 = `select`、`select` 未指定の走査で key 集合 = 宣言 field。**v0.4: 後者は `select` = 宣言 field 全部の走査で key 集合 = 宣言 field に置き換えた**)。`order_by` の変種 (NULL を含む field、方向混在、`select` に無い field) を parametrize する | `xfail(strict=False)` |
| `test_c28_concurrent_insert_discriminates_keyset_from_offset` | (ii)。assert は「既出の行はちょうど 1 回」と「cursor 位置より前に挿入した行は返らない」。後に挿入した行の出現は記録のみ | **`xfail(strict=True)`** |
| `test_c28_cursor_binding` | (iii) のうち `select` / `page.size` の変更で有効、`where` / `order_by` の変更で拒否。**v0.6: `where` の述語を並べ替えただけの要求で有効 (並べ替え前後の `where` は 2 述語以上で並びが異なること — 非空振り)** | `xfail(strict=False)` |
| `test_c28_cross_application_cursor_is_refused` | (iv) 別 Application と別 entity で発行した cursor の拒否 | `xfail(strict=False)` |
| `test_c28_cursor_refusal_details` | 復号不能・個数不一致・型不一致・別 Application の cursor が**同一の 2 キー拒否** (`VALIDATION_FAILED` / `request_schema` / `page/cursor`)。`conftest.assert_details_vocabulary_values_safe` を掛ける | `xfail(strict=False)` |
| `test_c28_cursor_is_stateless` | (v) | `xfail(strict=False)` |
| `test_c28_cursor_is_deterministic` | (viii) | `xfail(strict=False)` |
| `test_c28_default_page_is_the_largest_page` | 既定ページ (D-1 根拠 (2a))。`budget: {result_items: b}` (b = 3) を付け、b + 1 行の entity を `page.size` 省略で読む → `items` が b 件・`next_page` 非 null。その cursor で続きを `page.size` 省略のまま読む → 残り 1 件・`next_page` null。**この node に限り budget を使う** (§6.2 の C-24 行の例外)。通常 surface の `limits.result_items` は r2db 3 plug で 1000、MitateDB 3 plug で 500 であり、既定 + 1 行を作る観測は重いので budget で既定を小さくする。**v0.4: budget は port `query_page` の `budget` で運ぶ。`request_budget` を `unavailable` と宣言する plug では `budget` を使わず、宣言 `limits.result_items` + 1 行で観測する — 宣言で分岐し、skip しない** (現行は 6 plug とも enabled。`r2db-api/src/r2db_api/capabilities_document.py`:101、`MitateDB-api/src/mitatedb_api/capabilities_document.py`:190。設計レビュー 2 の指摘 5 への監督裁定)。node 名の「largest page」は案であり、義務 (7) の語 (least of …) に合わせて実測後に確定する | `xfail(strict=False)` |
| `test_c28_page_size_outside_schema_is_refused_at_page_size` | `page.size` = 0 と 1001 の両方が `VALIDATION_FAILED` / `request_schema` / `page/size` (D-3 の 8、D-2b の 2) | `xfail(strict=False)` |

- **(ii) node の遷移**: offset 実装または非対応の 1.8.0 peer では (ii) が必ず落ちる (xfail)。keyset を実装した peer は 1.9.0 を宣言するまで XPASS = strict で赤になる。したがって **WP-5 の完了時点で r2db 3 plug の (ii) node は XPASS (strict → FAILED) であり、WP-6 の版フリップで緑になる** (§9)。
- non-strict の node は offset 実装でも通る義務を 1.8.0 宣言下で「落ちるべき」と主張しない。本体は実行するので、実装が進むにつれて XPASS (non-strict、赤ではない) になる。
- **【v0.4 (2026-09-24) で改めた。設計レビュー 2 の指摘 1 への監督裁定】 上の 2 項の「XPASS = strict で赤」「赤ではない」は、統合 branch の途中の状態についての記述に限る。** 完了ゲートと CI は xfailed と xpassed の両方を 0 でなければ赤とする (`OC` §1.3 の 22、`tools/dev/gate.py`:88、`.github/workflows/ci.yml`:385-386) ので、xfail も non-strict XPASS も main では赤である。strict / non-strict の区別が意味を持つのは統合 branch の途中だけであり、WP-2〜WP-5 の完了は §9 の期待結果表との一致で判定する。main へは WP-7 の後に 1 回だけ merge し、その時点では全 plug が 1.9.0 を宣言するので `< 1.9.0` の分岐は実行されない。**MitateDB 3 plug の (ii) node も WP-4 の完了時点で XPASS (strict → FAILED) であり、WP-6 の版フリップで 6 plug すべて緑になる** (v0.3 起草担当の疑義 3 への監督裁定)。

### D-5. 記録 (同じ変更セットで動かす文書)

| 文書 | 変更 |
|---|---|
| `conformance-tests/CONDITIONS.md` | **C-28 行**を 1 行足す (§6.1 に案文)。Invariants 欄は `SI-01, SI-08, SI-10`。**この file は 1 つの `|` 表だけを持ち、cell に改行も生の `|` も入れない** (同 file 冒頭の更新規約)。Cell 長の上限 3,000 文字。**【v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 13 への監督裁定】 WP-1 で `declared` として置き、WP-2 で Status を `executable (six adapters) …` に上げる** — WP-2 の `@pytest.mark.condition("C-28")` は、C-28 行の Status が `executable` で始まることを要求される (`conformance-tests/test_conditions_register.py`:260-288)。WP-6 は Status 本文の確定に留める |
| `conformance-tests/CONDITIONS_HISTORY.md` | **【v0.4 (2026-09-24) で足した。指摘 13】 WP-1 で空でない `## C-28` 節を足す** — 本表と同じ ID 集合であること・history link が解決することを register test が検査する (`conformance-tests/test_conditions_register.py`:345, :371) |
| `RM` §0.1.1 の **G-2 / G-3 行** | 「契約の現行版 (現在 1.8.0 …)」→ **1.9.0**、「全条件 (現在 C-00〜C-27 の 28 件)」→ **C-00〜C-28 の 29 件**。§0.1.3 の充足状況の行も同じ変更セットで実測に更新する |
| `security/CONTROL_MAPPING.md` | 版 **3.1 → 3.2**。SI-01 / SI-03 / SI-08 / SI-10 に形式 3.0 の主張を足す (§7 に案) |
| `spec/CONTRACT_HISTORY.md` | **新しい `## <json_path>` 節は増えない見込みである** — 1.7.0 の R-10 (B) 以降、新しい契約値に provenance marker (`Since 1.x.y` 等) を埋め込まないのが現行の形であり、1.8.0 も 3 値すべて marker 0 件で通した (同 file の `versioning.version_binding` 節の Revision note、:400)。1.9.0 も同じ形とし、**`versioning.version_binding` 節に Revision note を 1 本足す**。marker 走査 (`test_contract_history_register.py`) の実測で 0 件を確認してから書く (`OC` §1.5 の 34)。**WP-1 の実装担当が実測し、結果 (走査で見つかった marker の件数と、増えた `## <json_path>` 節の有無) を本節に追記する** (監督裁定 2026-09-24)。**【v0.3 (2026-09-24) で足した】** (a) `versioning.version_binding` 節の Revision note に「1.9.0 で `Page.size` 範囲外の拒否を `request_schema` / `page/size` に揃えた」を明記する (D-3 の 8、D-2b の 2。設計レビュー 1 の指摘 12 への裁定 (b))。(b) `definitions.Page.cursor` 節に Revision note を 1 本足す — Q-5 (a) のときは `maxLength: 512` の除去と、長さは `request_bytes` が bound する旨、(b) のときは値の変更 (指摘 15 への裁定)。 **【v0.5 (2026-09-24) で改めた。作業指示書起草時の疑義 3 への監督裁定】 上の (b) の「`definitions.Page.cursor` 節に Revision note を 1 本足す」を改め、新しい `## <json_path>` 見出しを作らない。** 現行 file に `definitions.Page.cursor` の見出しは無く、足すと `test_contract_history_companion_heading_set_matches_the_scanner` (`conformance-tests/test_contract_history_register.py`:246。見出し集合 = marker 走査の結果) と両立しない (本件の方針は marker 0 件)。**Revision note は 3 本 (1.9.0 の追加 / `Page.size` 範囲外の拒否と既定ページ / `Page.cursor` の `maxLength`) とも既存の `## versioning.version_binding` 節 (`spec/CONTRACT_HISTORY.md`:383) に置く。** WP-1 の実装担当は register test の実測で確認する。**【v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 16 への監督裁定】** (a) の Revision note に「1.9.0 で `page.size` 省略時のページを定めた (両 peer の従前の既定 = r2db 100 件・MitateDB 配備上限で黙って切り詰め、を改めた)」を足す — `page.size` を省く既存 client は、r2db で 1 ページの件数が最大 10 倍になり、MitateDB では同じ件数のまま `next_page` が非 null で返り始める。**【WP-1 実測 (2026-09-24)】** `test_contract_history_register.py` の scanner (`_PATTERNS`) を編集後の契約 JSON に対して実行した結果: RAW 契約 JSON 全体の marker hit は 3 path のみ (`destructive_confirmation.phrase_construction.rules[3]`、`versioning.compatibility`、`versioning.version_binding` — いずれも既存の `unstripped: true` path で、1.9.0 前と同一集合)。新設した `structured_operations.paging` の 6 値 (`ordering`/`next_page`/`cursor`/`binding`/`refusal`/`traversal`) と `versioning.obligations` の 1.9.0 entry は、いずれも marker hit 0 件。増えた `## <json_path>` 節は無し (companion の見出し集合は 1.8.0 以前と同一 29 見出しのまま、新規見出し 0)。したがって Revision note 3 本はすべて既存 `## versioning.version_binding` 節に追記した (`spec/CONTRACT_HISTORY.md`「Revision note 3」「Revision note 4」「Revision note 5」)。 |
| `spec/CCR_DISPOSITION.md` | **従属判断 14** の節。1.9.0 が足す 6 義務と、Q-1 / Q-2 の裁定を引く (**v0.4: 義務は 7 件**。案文 A (7)) |
| `spec/OPERATION_CATALOG.json` | 再生成 (`contract_version` の pass-through) |
| `spec/README.md` | 現行版の記述を 1.9.0 に更新 |
| 両 peer 同梱 copy | `r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` (byte 一致ピン `test_contract.py`:361) |
| `conformance-tests/test_contract.py` | 1.9.0 の文言の逐語ピン (1.8.0 のピン `test_contract_pins_the_1_8_0_ruling_sentences_verbatim`:153 と同形)、`versioning.obligations` の版ラベル集合、`Page`/`QueryResult` の schema ピン |
| `conformance-tests/test_contract_history_register.py` / `test_operation_catalog_register.py` | 版に追随 |
| 両 peer `capabilities_document.py` | `contract_version` を **1.9.0** へ。**実挙動と同一コミット** |

**手本**: 1.7.0 → 1.8.0 のフリップ commit `654e23e` の 11 ファイル。ただし同 commit は spec 側だけを動かし、peer の宣言は後続の pair-closing で上げた。**本件は D-1 の「版フリップは実挙動と同一コミット」に従い、両 peer の宣言と実挙動を同じコミットで上げる** (§9 WP-6)。

### D-6. 同型性 — cursor codec を両 peer に同名で置く

**決定**: `encode_page_cursor` / `decode_page_cursor` を両 peer に**同名**で置き、`MitateDB-api/tests/test_audit_query.py`:2188 の `_ISOMORPHIC_TARGETS` に登録する (集合の増加 = **Class D**。`RM` §9 の 8、`OC` §1.5 の 40b)。**【v0.6 (2026-09-24) で足した。依頼者裁定 Q-3 の見直し 1 点 (§5.1)】 束縛の hash を作る helper `canonical_page_binding` も両 peer に同名で置き、同じ表に登録する (表に足す行は codec の 2 行と合わせて 3 行)。** 引数は (application_id, entity, `where` の (field, operator, value) の並び, `order_by` の (field, direction) の並び) の素の値、返り値は codec が引数で受ける束縛の hash である。`where` の正規化は D-3 の 3、本体に comment を置かないのは下の (b) と同じ。hash の算法は実装で決め、両 peer の本体の一致は同型性テストが固定する。

- 形式は base64url(JSON、`sort_keys=True`)、**鍵なし・署名なし・暗号化なし**。audit cursor (`r2db-api/src/r2db_api/audit_query.py`:208-217、`MitateDB-api/src/mitatedb_api/audit_query.py`:190-199) と同じ作り。
- **符号化する中身は引数で渡す** — r2db は `{order_spec の各値, id}`、MitateDB は `{order_spec の各値, _mdb_row}` であり、**codec 本体はどちらも知らない** (values の list と binding の hash を受け取り、base64url(JSON) にするだけ)。これで本体が両 peer で 1 文字も違わない。
- **audit の `encode_cursor` / `decode_cursor` は流用しない** (順序 key が違う。名前の衝突も避ける)。
- 置き場は r2db が `paging.py`、MitateDB が新規 `paging.py` (現状 MitateDB に paging module は無い)。**`_ISOMORPHIC_TARGETS` の行は監督の pair-closing commit で足す。**
- **【v0.3 (2026-09-24) で足した。設計レビュー 1 の指摘 11 への裁定】 (a) 件数ピンの改名**: 表に 2 行足すので、件数ピン test `test_isomorphic_target_table_is_pinned_to_its_current_156_rows` (`r2db-api/tests/test_audit_query.py`:2942、`MitateDB-api/tests/test_audit_query.py`:2725) を `..._158_rows` に改名する。この test 自身が `_ISOMORPHIC_TARGETS` の行である (`MitateDB-api/tests/test_audit_query.py`:2211、`r2db-api/tests/test_audit_query.py`:2416) ので、**表の当該行と test 名の両方を、両 peer 同一コミットで**改める。**【v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 13 への監督裁定】 pin 本体が持つ表の逐語コピー** (`MitateDB-api/tests/test_audit_query.py`:2794 付近からの `assert _ISOMORPHIC_TARGETS == (...)`、`r2db-api/tests/test_audit_query.py`:3012 付近からの同じ assert) **にも codec の 2 行と改名後の test 名を足し、同 test の docstring の「widened … time」の列にも 1 節を足す**。**【v0.6 (2026-09-24) で改めた】 表に足す行は 3 行 (codec 2 行 + `canonical_page_binding`) になるので、改名先は `..._159_rows` (現行 156 + 3) とする (v0.5 までは `..._158_rows`)。数字は WP-6 で表の行数を実測して確定する。**
- **(b) codec 本体に comment を置かない**: 同型性テストの正規化 `_normalize` (`MitateDB-api/tests/test_audit_query.py`:3199-3247) は docstring・package 名・行末空白・空行を吸収するが **in-body comment は吸収しない**。`encode_page_cursor` / `decode_page_cursor` の本体には comment を置かず、docstring だけ peer ごとに書く (`compose_bearer_locator` の既存の形)。**拒否は codec の中で起こさず、`ValueError` を投げて呼び出し側が peer 固有の拒否に写す** (audit の `decode_cursor` の既存の形)。

### D-7. 性能の証拠 (P-8)

**決定**

1. 完了ゲートに通常の `tools/perf_baseline.py` の差分を添える (K=1、`RM` §0.1.4 の閾値の内側であること)。
2. **加えて、深いページの前後比較を 1 回だけ ad-hoc script で取る** — r2db の PostgreSQL plug で N 行の entity の末尾ページを、(a) 変更前の offset 方式、(b) 変更後の keyset 方式で読み、**行数と p50** を §11 (実施記録) に書く。**【v0.3 (2026-09-24)】** 案文 C-3 から削った内容 — 「token は件数ではなく位置を名指すので、cursor を運ぶ要求に答える仕事は先行するページ数に応じて増えない」 — はこの計測の記録として置く (契約の主張ではない。D-1 根拠 (3)、設計レビュー 1 の指摘 8 への裁定)。
3. **harness に op を足さない** (`tools/perf_baseline.py` の操作集合を増やさない)。道具を増やすこと自体が台帳を増やす原因である、という診断に従う。
4. **契約には性能を書かない** (D-1 (3))。

### D-8. capability 宣言は増やさない

**決定**: `structured_query.paging` のような新しい capability key を足さない。

- 両 peer が実装し、義務は版 (1.9.0) に束ねる。**1.9.0 を宣言できない実装は 1.8.0 に留まる**というのが既存の仕組みであり、これで足りる。
- 新しい key を足すと、宣言 1 つにつき一致条件 1 つ (P-3) が要り、`capability_status` の語彙も増える。得るものが無い。
- MitateDB の `structured_query: partial` (`unsupported: contains / matches / is_null`) は**変わらない**。partial は「演算子の一部が無い」の意味であり、`unavailable` ではないので 1.9.0 の conditional 義務は束縛する。

### D-9. change feed (II-7) との整合

**決定**: 語彙 (opaque / echo back / `VALIDATION_FAILED` / filter 束縛) を `audit.query_cursor` と揃えるが、**codec は共有しない**。

- Mitate の review trigger (§1.1 (a-4)「data-service-api 側の cursor 語彙との整合」) はこれで満たされる — entity query の cursor が audit cursor と同じ語で定義される。
- **II-7 change feed は本件では触らない**。将来起こすなら audit cursor をそのまま使う (`RM` §3.2 の II-7 行「1.4.0 の audit cursor と同じ語彙」)。
- Mitate 自身の `readAudit` cursor (AES-256-GCM で暗号化、triple 束縛、再起動非安全) は **Agent–Application 契約の層**であり、本件の層ではない。本書はそちらに何も要求しない。

---

## 4. 却下した代替案 (再提案には新しい論拠が要る)

### 4.1 ページング方式そのもの

| 案 | 採らない理由 |
|---|---|
| **offset を契約に明文化して残す** (深いページ O(offset)、並行挿入で重複、MitateDB の実装は簡単) | 実需は「完全性の証明」であり、並行変更下の「ちょうど 1 回」は keyset でしか言えない (D-1 (6))。offset を契約に書けば、その弱さを契約が保証することになる |
| **cursor に HMAC 署名 / 暗号化を掛ける** | 鍵管理 (プロセス跨ぎ・再起動) が要り **P-1 に反する** (サーバ側状態)。中身は自 Application の自分の行の値だけであり、改竄しても自分のページがずれるか `VALIDATION_FAILED` になるだけで越境しない (`R2DB_CCR13_STORAGE_V1.md` §R-6 の論拠を継承) |
| **cursor を `select` / `page.size` にも束縛する** (r2db の現行) | 位置は select と size に依存しない。守るものが無い拒否を置かない (P-5)。**両論は §5 Q-2 に残る** |
| **新しい capability key を足す** | D-8 |

### 4.2 MitateDB の tie-break — Q-1 で提示した代替案の表

**依頼者裁定は D-2 (保存形の変更) である** (§5)。以下は却下した案であり、**(1) は唯一の現実的な代替として両論を残す**。

| # | 案 | 保証 | 費用 | 採らない理由 |
|---|---|---|---|---|
| **(1)** | **order key + 同値群内 offset** — cursor に「最後の行の order key 値」と「その同値群の中で何件返したか」を入れる。保存形を変えない | **不完全**。order key が全順序でないので、同値群 (同じ order key 値を持つ行の集まり) の中の順序が DB 任せであり、群内での「ちょうど 1 回」が言えない。群内に並行挿入が起きると重複・欠落が出る | **小**。migration 無し、既存 table のまま | **両論**: 保存形を触らない唯一の案であり、費用は最小である。「同値群の中では offset と同じ弱さに縮退する」という**縮退を契約に宣言**すれば、宣言は真のままにできる (declare-the-hazard)。**採らない理由**: 弱さを宣言で回避するのは「制約・制限で回避しない」という依頼者の設計原則に反し、消費者 (Mitate) が求めたのは完全性の証明そのものである。依頼者裁定 Q-1 = D-2 |
| (2) | `ctid` を tie-break にする | **成り立たない** | 小 | `ctid` は物理位置であり **UPDATE / VACUUM で変わる** (`backend_postgres.py`:1236-1254 のコメントが明記)。走査中に更新された行が別位置へ跳ぶので、重複・欠落が構造的に出る。SQLite の `rowid` とも非対称である |
| (3) | 全列を tie-break にする (または全列の hash) | **不完全** | 中 (述語が列数に比例して長くなる) | **完全重複行を区別できない**。MitateDB は一意制約を要求しないので、全列が同値の 2 行は普通に存在しうる。そこで「ちょうど 1 回」が破れる。hash も同じ (衝突以前に、同値行が同じ hash を持つ) |
| (4) | `order_by` に一意 field を要求する | **要求を満たせない** | 小 (実装)、大 (消費者) | MitateDB は一意 key を宣言する仕組みを持たず (`row_addressability: unavailable`)、Mitate の `seq` が一意である保証も契約上は無い。client に「一意 field を用意せよ」と要求するのは 1.9.0 の「client に何も要求しない」に反する |
| (5) | サーバ側 cursor (走査状態をサーバが保持する) | 完全 | 大 | **P-1 に正面から反する**。失効・掃除・上限が要り (P-5 にも反する)、両 peer の同型性を「状態の持ち方」と「失効」の 2 回壊す (`RM` §4 P-1 の根拠欄) |
| (6) | MitateDB だけ cursor 非対応のまま (r2db だけ keyset) | — | 小 | **実需が MitateDB 側にある** (Mitate は MitateDB の消費者。§1.1)。片 peer だけ実装すれば 1.9.0 は片側しか宣言できず、共通契約の意味が割れる |

---

## 5. 依頼者裁定と裁定待ち

### 5.1 裁定済み (2026-09-24。逐語。再審議しない — `RM` §9 の 4)

**Q-1 — MitateDB の保存形を変えるか**

> D-2 (保存形の変更、保証は完全)で。

監督が提示した代替案の表 (order key + 同値群内 offset / ctid / 全列・hash / 一意 field 要求 / サーバ側 cursor / MitateDB 非対応) は §4.2 に残す。代替 (1) は唯一の現実的な代替として両論の記録を残した。

**Q-2 — cursor の束縛範囲**

> select/size の変更は取り違えではなく正当な意図でありうるなら束縛してはいけないように思う

裁定は **A** (Application, entity, `where`, `order_by` のみ。`select` と `page.size` は自由)。根拠 (監督):

- 位置を決めるのは `where` と `order_by` だけである。
- 守るものが無い拒否を置かない (P-5)。
- P-2 の「安全に再送する」— `LIMIT_EXCEEDED` の後に `page.size` を小さくして同じ cursor から続行できる。
- `audit.query_cursor` の「同じ filter の集合でのみ有効」と同形である。
- r2db が `select` / `size` を束ねていたのは `docs/design/R2DB_CCR13_STORAGE_V1.md`:243 の訂正 m-3 (「cursor が query 形状を束ねない → 形状ハッシュ」) の網が、**位置を決める field と決めない field を区別しなかった**ためであり、`select` / `size` 固有の理由は記録に無い。1.9.0 で r2db の shape hash を `where` + `order_by` に狭めるのは、この網の是正として記録する (D-3 の 3)。

**Q-3 / Q-5 / Q-4 (2026-09-24)**

> Q-3 は見直し 1 点を含めて確定、Q-5 は (a)、Q-4 はその形で。

- **見直し 1 点 (監督の提示。要旨)**: 案文 C-4 の「同じ where 述語を同じ順序で」は、位置が変わらないのに拒否する守るものの無い gate である。AI エージェントは要求を再生成するとき述語の順を保つとは限らない。両 peer の束縛 hash を、述語を正規化して順序に依らない形 (field・演算子・値で整列した正規 JSON) にし、契約は「the same where predicates, in any order」と書く。反映先: D-1 (C-4 と v0.6 の註、根拠 (4)・(5))、D-2b の 5、D-3 の 3、D-4 の (iii) と node 表、D-6、§6.1、§7、§10 の 10・14。
- **Q-3**: 契約文 (D-1 の案文 A〜D) と C-28 の Condition 文 (§6.1) を、上の見直し 1 点を反映した形で確定した。確定文ファイル `verbatim-190.md` は監督が本改版の後に置く。
- **Q-5 = (a)**: `Page.cursor` の `maxLength` を外す (D-1 (D) の案文どおり)。
- **Q-4 の「その形」**: main への 1 回の merge (§9 の統合 branch。WP-7 の後) の直前に、完了ゲートの集計行と `git diff --stat` を添えて依頼者確認を取る。

以下は v0.5 まで §5.2 にあった裁定待ちの記録である (v0.6 で本節へ移した。両論の記録を含めて文は変えていない)。

- **Q-3 — 契約文と C-28 の Condition 文の逐語。** (v0.3 (2026-09-24)) 既定ページの文 (案文 C-2 の末尾。D-1 根拠 (2a)) は契約の変更なので Q-3 に含む。本書 §3 D-1 の案文と §6.1 の Condition 文案を、設計レビュー 2 回の後に scratchpad の確定文ファイル (`verbatim-190.md`) で提示する。**実装は確定文ファイルから逐語で複製し、言い換えない** (`OC` §1.5 の 35・36)。起草段階の案文は `verbatim-190-draft.md` に同一文で置いた。**(v0.4 (2026-09-24)) 義務 (7) (既定ページ。案文 A の (7) と B の 7 件目) と、設計レビュー 2 への裁定で改めた A・C-1〜C-6 の文を含む。**
- **Q-5 — `Page.cursor` の `maxLength` をどうするか (両論)。** keyset cursor は順序キーの値を運ぶので、現行の `maxLength: 512` を超えうる (offset cursor は常に短かった)。
  - **(a) `maxLength` を外す (D-1 (D) の案文はこちらで書いた)**。cursor はサーバが発行しクライアントがそのまま返す値であり、クライアントが長さを選ばない。要求が運ぶ文字列の長さは `request_bytes` が bound する — 契約自身が `limits.enum_members` でその形を述べている (`spec/data-service-api.v1.json`:828)。P-5 (守るものが無い bound を置かない) はこちらを支持する。
  - **(b) 上限を残して引き上げる (例 4096)**。「すべての string に `maxLength` を置く」という見た目の一貫性は保てる。ただし値は根拠なく任意であり、**超えたときに何が起きるか (サーバが cursor を発行できない)** を別に定義する必要が残る。
  - **Q-3 (契約文の確定) と同時に裁定する。**
- **Q-4 — 契約版に触れるコミットの事前確認** (`RM` §9 の手順 8 = 変更クラス D の「依頼者裁定の逐語記録と版付きの security-contract 決定」)。**WP-6 (版フリップ) の前に確認を取る。** **【v0.4 (2026-09-24) で改めた】 本件で契約版に触れる main へのコミットは、WP-7 の後の main への 1 回の merge である (§9 の統合 branch)。確認の対象はこの merge であり、その前に取る。**

### 5.2 裁定待ち

**【v0.6 (2026-09-24)】 裁定待ちは 0 件。** Q-3 / Q-5 / Q-4 は依頼者裁定 (2026-09-24) により §5.1 へ移した。

---

## 6. conformance への影響

### 6.1 C-28 の Condition 文 (Q-3 で確定。v0.6 で見直し 1 点を反映)

`CONDITIONS.md` の表に足す 1 行の Condition 欄 (英語、既存行と同じ文体):

> A peer declaring contract 1.9.0 returns query results in a total order and pages them with a stateless keyset cursor: the pages of a traversal, concatenated, are the same sequence -- each row exactly once -- as one unpaged read of the same request, with `next_page` non-null on every page but the last and null on it, including when `order_by` names a field holding nulls, mixes directions, or names a field outside `select`, and each item carries exactly the fields `select` names and nothing else, including when `select` names every declared field; a row inserted before the cursor's position in the order mid-traversal is not returned, while every row already returned whose ordering values have not changed is still returned exactly once; a cursor stays valid when `select` or `page.size` changes or when the same `where` predicates are reordered, and is refused with one identical denial -- `VALIDATION_FAILED`, `violated_declaration: request_schema` and `field: page/cursor` -- when its recorded binding names a different Application, entity, `where` or `order_by` than the request presenting it, when it does not decode, or when its ordering values do not match the request's order in number or in type; the cursor stays valid in a second session authenticated with a different credential of the same Application, and two identical requests return the identical `next_page` value; a request without `page.size` is answered as though it carried the least of 1000, the declared `limits.result_items` and its own `budget.result_items`, so that under a `budget.result_items` of 3 a four-row entity comes back as three items with a non-null `next_page` and then one item with a null one (a peer declaring `request_budget` unavailable is read instead with an entity of its declared `limits.result_items` plus one rows); and a `page.size` of 0 or 1001 is refused with `VALIDATION_FAILED`, `violated_declaration: request_schema` and `field: page/size`.

- **Invariants 欄**: `SI-01, SI-08, SI-10`
v0.3 (2026-09-24) で上の文を設計レビュー 1 への裁定 (指摘 1・3・6・9・12・18、および 2・7) に合わせて書き直した。cell 長は 1,684 文字 (上限 3,000)、改行と生の `|` を含まない。 **v0.4 (2026-09-24) で上の文を設計レビュー 2 への裁定 (指摘 2・6・7・9・12) と v0.3 起草担当の疑義 1 への裁定に合わせて書き直した** — 挿入位置は「順序で前」(before … in the order)、既出の行は順序値が変わらないものに限る、束縛違いは recorded binding の語、「tied to no session, connection or credential」「carries no nonce, time or counter」を消して別 credential の第 2 セッションと決定性の 2 観測だけを残した、既定ページは「least of … を運んだものとして答える」と `request_budget` が unavailable の plug の観測、item の key 集合は `select` = 宣言 field 全部の走査。cell 長は 1,902 文字 (上限 3,000)、改行と生の `|` を含まない。 **v0.6 (2026-09-24) で上の文を依頼者裁定 Q-3 の見直し 1 点 (§5.1) に合わせて改めた** — 「a cursor stays valid when `select` or `page.size` changes」に「or when the same `where` predicates are reordered」を足した。cell 長は 1,952 文字 (上限 3,000)、改行と生の `|` を含まない。

- **Evidence 欄**: `paged-traversal equivalence test (null, mixed-direction and outside-select orderings; item keys equal select), concurrent-insert discrimination test (offset would repeat a row), cursor-binding, cross-application and refusal-details tests, cross-session and determinism tests, default-page and page-size refusal tests` (v0.3 で 9 node に合わせた)
- **Status 欄**: `executable (six adapters)` + 駆動条件 (`adapter.parse_semver` による版ゲート。**`< 1.9.0` で (ii) の node だけ `xfail(strict=True)`、他の node は `xfail(strict=False)`**。v0.3 で改めた。D-4)、port v1.16、plug ごとの非空振りの根拠、開示 (§10)。**開示に次を含める (v0.3)**: 無状態性そのものは port から反証できない — plug はプロセスを跨がないので、決定的な token を鍵にしたサーバ側 cursor 表は `test_c28_cursor_is_stateless` / `test_c28_cursor_is_deterministic` を通る。施行は両 peer の `paging.py` に状態が無いことによる (設計レビュー 1 の指摘 7 への裁定)。既定ページの node だけが `budget.result_items` を使う (§6.2)。**開示に次を足す (v0.4 (2026-09-24)。設計レビュー 2 の指摘 12 への監督裁定)**: 接続の独立と、cursor が時刻を含まないことは port から観測しない (port は新しい接続を張らせる手段を持たず、粗い時刻を混ぜた token は連続 2 要求で一致する)。**駆動条件に次を足す (v0.4。指摘 10)**: `observed_branch` の突合は `>= 1.9.0` の分岐でだけ行い、`< 1.9.0` の分岐では本体の無条件 assert が検出の全部である。**Status が `executable` になるのは WP-2 である** (D-5 の `CONDITIONS.md` 行。WP-6 は本文の確定のみ)。

### 6.2 既存条件との関係

| 条件 | 関係 |
|---|---|
| **C-05** (宣言した bound の一致) | `result_items` は **1 ページあたりの行数**に掛かる bound であり、本件で意味は変わらない。C-05 の V2 drive は `select_eq(..., limit=bound)` を使う (`test_c05_limit_declaration_agreement.py`:608) — **この経路は触らない** (D-4 は新メソッドを足す形なので `select_eq` の signature が変わらない) |
| **C-24** (`budget` の下方向の絞り込み) | `budget.result_items` は query に効く。C-24 の開示「`result_items` は N/N+1 境界で駆動していない」は本件でも変わらない。**C-28 は budget を使わない** (別の命題であり、混ぜない)。**【v0.3 (2026-09-24)】 例外は `test_c28_default_page_is_the_largest_page` の 1 node だけ** — `budget.result_items` = 3 で既定ページを小さくして「既定 = 要求が運べる最大の `page.size`」を観測する (**v0.4: 「既定 = 最小値 (1000・宣言 `limits.result_items`・`budget.result_items`) の `page.size` を運んだものとして答える」を観測する。`request_budget` が `unavailable` の plug では budget を使わず宣言 `limits.result_items` + 1 行で観測する。D-4**)。通常 surface の `limits.result_items` (r2db 1000 / MitateDB 500) で既定 + 1 行を作るのは重いためである (設計レビュー 1 の指摘 9 への裁定)。C-24 の N/N+1 境界の開示には触れない |
| **C-12** (演算子の宣言と一致) | `where` を使うが、C-28 が使うのは宣言済み演算子だけ (`eq` / `gt` / `lt`)。重ならない |
| **C-25** (`request_id`) | 版ゲートの機構 (`parse_semver` + 実行時 `xfail(strict=True)`) を C-28 が借りる (`test_c25_result_request_id.py`:214-226)。**v0.3 (2026-09-24)**: strict は (ii) の node だけで、他の node は `xfail(strict=False)` (D-4)。**`iso` (`isolated_application_surface()`) は借りない** — それは「a FRESH, throwaway data-plane instance」であり (`adapter.py`:1629-1656)、そこで発行した cursor はセッション surface では別 Application の cursor になって (iv) の拒否に落ちる。C-28 (v) は同一 Application の別 credential・別セッションで観測する (監督裁定 2026-09-24) |
| **C-27** (同一 idempotency key の同時送信) | 観測の形 (peer ごとに違う変異、開示) の手本。重ならない |

### 6.3 port の版

- port **v1.15 → v1.16**。`adapter.py` に `query_page` の抽象メソッドと docstring (port 版・追加理由・引数を逐語で渡す原則) を足す。
- 6 plug 全部に実装を足す (`{r2db-api,MitateDB-api}/conformance/conformance_adapter_*.py` の 6 ファイル)。
- `docs/design/CONFORMANCE_ADAPTER_V1.md` §4.4 の port 定義に 1 行足す。

---

## 7. Security Invariants との関係

**新しい invariant は足さない** (`CLAUDE.md`「Security Invariants are not a feature gate」/ `SECURITY_INVARIANTS_V1.md` §8)。既存の SI で表現できる。

| SI | 既存で担保されるか | 新たに検査可能にする性質 | C-28 のどの観測が証拠か |
|---|---|---|---|
| **SI-01 (Application Isolation)** | **一部は既存** — scope は認証済み credential からサーバ側で解決される (C-00 / C-01) ので、cursor が Application を名乗っても scope は動かない。**新たに検査可能にすべき性質**: cursor が **Application と entity に束縛**され、他 Application で発行された cursor が実行前に拒否されること。tie-break の値 (`id` / `_mdb_row`) が **Application-scoped** であり、他 Application の存在・活動を推測させないこと (`addressability.assigned_identifiers` と同じ性質。MitateDB は database-per-application、r2db は `id` が Application 内採番) | **(iv)** 別 Application / 別 entity の cursor が `VALIDATION_FAILED`。**(iii)** 束縛違いの拒否 |
| **SI-03 (Runtime / Developer 分離)** | **既存で足りる。** cursor は権限を運ばない — 復号しても得られるのは自分が既に受け取った行の順序値だけであり、role も authority も含まない。paging は runtime 権限の読み取り経路にしかなく、schema 操作の権限に触れない。**新しい検査は置かない** (`CONTROL_MAPPING` には「cursor は authority を運ばない」を Status として開示する) | 直接の観測は置かない。(iv) が「cursor は scope を動かさない」を間接に示す |
| **SI-08 (Bounded Resource Consumption)** | **一部は既存** — `result_items` / `query_complexity` / `execution_ms` は C-05 / C-24 が固定する。**新たに検査可能にすべき性質**: paging が**サーバ側資源を一切消費しない**こと。cursor 表も、TTL も、掃除も、件数上限も無い。これは「上限が必要な資源を作らない」という形の SI-08 への応答であり、P-1 / P-5 と同じ主張である。加えて、深いページの費用が offset に比例しない (= 1 client が深いページで CPU を線形に消費できない)。**【v0.3 (2026-09-24) で縮めた】 新たに検査可能にする性質は「cursor が session・connection・credential に紐づかない、かつ nonce・時刻・連番を含まない」までとする。** 根拠: プロセス内に cursor 表を持ち token を決定的に採番する実装は (v)(viii) を通り、plug はプロセスを跨がないので、port から無状態性そのものを反証する観測は無い (`OC` §1.5 の 34。設計レビュー 1 の指摘 7 への裁定)。**無状態性そのものは C-28 の Status と CONTROL_MAPPING SI-08 の Status に開示する** (施行は両 peer の `paging.py` に状態が無いこと)。**【v0.4 (2026-09-24) でさらに縮めた。設計レビュー 2 の指摘 12 への監督裁定】 新たに検査可能にする性質は「cursor が session・credential に紐づかない、同一要求で同一 token」までとする。** 「connection」と「nonce・時刻・連番を含まない」は port から観測しない (新しい接続を張る手段が port に無く、粗い時刻を混ぜた token は (viii) を通る) | **(v)** 別セッション・別 credential での有効性 (`test_c28_cursor_is_stateless`)。**(viii)** 同一要求 2 回で `next_page` が一致 (`test_c28_cursor_is_deterministic`。nonce・時刻・連番を含まない。**v0.4: 同一要求で同一 token まで**)。**(i)** 全ページ走査が `result_items` の範囲内で完結する。性能面は D-7 の実測 (契約の主張ではない) |
| **SI-10 (Error and Information Non-Disclosure)** | **一部は既存** — C-21 が `VALIDATION_FAILED` の details 語彙と非開示を固定する。**新たに検査可能にすべき性質**: cursor の拒否が **`violated_declaration: request_schema` と `field: page/cursor` の 2 キーだけ**を返し、復号結果・束縛内容・対象 Application/entity の存在有無を漏らさないこと。「別 Application の cursor」と「復号できない文字列」が**区別のつかない同じ拒否**になること (存在推測を許さない)。**【v0.3 (2026-09-24) で足した】** cursor は行の順序値の復元可能な符号化なので、`audit.forbidden_fields` の `row_value` の趣旨により (`spec/data-service-api.v1.json`:856-864)、**監査 event のどのフィールドにも cursor を載せない**。両 peer の event フィールド集合は固定なので新しい検査は置かず、CONTROL_MAPPING の Status に開示する (設計レビュー 1 の指摘 17 への裁定) | **(iii)** 復号不能と束縛違いが同じ拒否。**(iv)** 別 Application の cursor が同じ拒否。`conftest.assert_details_vocabulary_values_safe` を C-21 と同じ形で掛ける |

**`security/CONTROL_MAPPING.md` 3.2 に足す主張 (形式 3.0。案)**

- **SI-01 / Common / Control**: `` - C-28 query cursor binding -- a cursor whose recorded Application, entity, where or order_by differs from the request presenting it is refused before execution (`r2db-api/src/r2db_api/paging.py`, `MitateDB-api/src/mitatedb_api/paging.py`). ``
- **SI-01 / Common / Evidence**: `` - A cursor issued for one Application or entity is refused for another with no existence signal, and one reused under a different where or order_by is refused: `test_c28_keyset_paging.py::test_c28_cross_application_cursor_is_refused`, `::test_c28_cursor_binding`. ``
- **SI-08 / Common / Control**: `` - C-28 stateless paging -- a traversal's whole position lives in the token the client echoes back; the service keeps no cursor table, timer or ceiling (`r2db-api/src/r2db_api/paging.py`, `MitateDB-api/src/mitatedb_api/paging.py`). ``
- **SI-08 / Common / Evidence**: `` - A cursor is honored in a second session under a different credential, and two identical requests return the identical token: `test_c28_keyset_paging.py::test_c28_cursor_is_stateless`, `::test_c28_cursor_is_deterministic`. ``
- **SI-08 / Common / Status**: `- Statelessness itself is not observable from the port: no plug crosses a process, so a server-side cursor table keyed by a deterministic token would pass both tests above; it is enforced by both peers' paging.py holding no state.`
- **SI-10 / Common / Control**: `` - C-28 cursor refusal details -- an unusable cursor is refused with only request_schema and page/cursor, alike when malformed, mismatched in number or type, or foreign (`r2db-api/src/r2db_api/paging.py`, `MitateDB-api/src/mitatedb_api/paging.py`). ``
- **SI-10 / Common / Evidence**: `` - Undecodable, wrong-count, wrong-type and foreign cursors produce the identical 2-key denial: `test_c28_keyset_paging.py::test_c28_cursor_refusal_details`. ``
- **SI-10 / Common / Status**: `- A page cursor is a recoverable encoding of a row's ordering values, so, as audit.forbidden_fields excludes row_value, no audit event field carries it; both peers' event field sets are fixed, so no further check is added.`
- **SI-03 / Common / Status**: `- A page cursor carries no authority: it encodes only ordering values of rows the client already received, and never role, credential or scope.`

**主張は実測の後に書く** (`OC` §1.5 の 34)。上はテスト名と施行箇所を先に決めた**案**であり、実測後に確定する。**v0.3 (2026-09-24)**: テスト名を D-4 の 9 node の案に合わせ、SI-08 の Evidence を観測できる幅 (session・connection・credential に紐づかない / nonce・時刻・連番を含まない) に縮め、SI-08 と SI-10 に Status を 1 本ずつ足した (設計レビュー 1 の指摘 4・7・17 への裁定)。**node 名は案であり、実測の後に確定する。** **v0.4 (2026-09-24)**: 設計レビュー 2 の指摘 8 への監督裁定により、SI-01 Control を「recorded binding が要求と違えば実行前に拒否」の形に改め (旧案「it was issued under」は、改変 token を受理しうる C-3 と矛盾し、実測前の主張でもあった)、SI-08 Evidence を 300 文字以内 (223 文字) に縮め、SI-10 Control の「(paths as above)」を 2 つの backtick path に置き換えた (Control 上限 250 に対し 247 文字)。**各 Control 主張の path は backtick で囲む (register の抽出規則。`conformance-tests/test_control_mapping_register.py`:1274)。長さは写した後に register test で測る。** **v0.6 (2026-09-24) の確認 (依頼者裁定 Q-3 の見直し 1 点。§5.1)**: SI-01 の Control 案「a cursor whose recorded Application, entity, where or order_by differs from the request presenting it is refused」と Evidence 案「one reused under a different where or order_by is refused」は、束縛が述語の並びに依らない形 (D-3 の 3) でもそのまま成り立つ — 並べ替えただけの `where` は「違う where」に当たらない。したがって案は変えない。束縛 helper `canonical_page_binding` の置き場 (両 peer の `paging.py`) は Control 案の施行箇所に既に含まれている。

---

## 8. 変更クラスと規模

**変更クラス: D** (`RM` §9 の 8。1 コミットが複数クラスに触れるときは最も重いクラスを採る)。

| 触れる対象 | クラス |
|---|---|
| `spec/` (契約 JSON、`CONTRACT_HISTORY.md`、`CCR_DISPOSITION.md`、`OPERATION_CATALOG.json`、`README.md`) | C |
| `conformance-tests/` (`adapter.py`、新規 `test_c28_*.py`、`CONDITIONS.md`、`test_contract.py`) | C |
| catalog 宣言値 (両 peer の `capabilities_document.contract_version`) | C |
| **`_ISOMORPHIC_TARGETS` 集合の増加** (cursor codec の登録。v0.6: 束縛 helper `canonical_page_binding` を含む 3 行) | **D** |
| **`security/CONTROL_MAPPING.md`** | **D** |
| 両 peer の実装コード、migration、`platform_upgrades.py` | B |

したがって **D**。必要な証拠は「C の全部 + 依頼者裁定の逐語記録 + 版付きの security-contract 決定」である。前者は §5.1、後者は契約 1.9.0 の従属判断 14 (D-1) が担う。

**規模: L** (`OC` §1.13 の 74)。理由: 契約変更 (1.8.0 → 1.9.0、両 peer の版フリップ)、共通条件の追加、**MitateDB の保存形の変更**を含む。手順は現行の全手順 — **設計レビュー 2 回** (契約変更。`RM` §9 の 3)、実装担当、レビュー担当、**監査担当**、完了ゲート、記録 (台帳 + `CONTROL_MAPPING`)。

**着手順の印**: 本件は「運用が始まって data と client が存在すると直す費用が上がる」項目である (契約と保存形の両方に触れる)。**印なし = 運用前に済ませる** (`RM` §9 の 12)。

---

## 9. WP 分割の骨子

**作業指示書は別文書である** (`docs/work-orders/WORK_ORDER_PHASE11_KEYSET_PAGING_V1.md`。Change Set Manifest 形式、`RM` §9 の 9)。本節は**依存順と触るファイルの重なり**だけを決める。完了条件と変異の 1 対 1 表は manifest 側で確定する。

**統合 branch (v0.4 (2026-09-24)。設計レビュー 2 の指摘 1 への監督裁定)**: **WP-1〜WP-7 はすべて本 worktree の branch `claude/cranky-visvesvaraya-616e67` に積み、main への merge は WP-7 (性能記録) まで終えた後の 1 回だけとする。** WP-1 も単独では main に載せない — 契約 JSON が 1.9.0 になる一方で peer が 1.8.0 を宣言する中間状態を main に置かないためである。WP ごとの commit は `tools/dev/finalize.py --no-merge` で branch に積む。**完了ゲート (`tools/dev/gate.py`) は merge 直前の 1 回である。** 完了ゲートと CI は xfailed と xpassed の両方を 0 でなければ赤とする (`OC` §1.3 の 22、`tools/dev/gate.py`:88、`.github/workflows/ci.yml`:385-386) ので、C-28 の node が xfail か XPASS である WP-2〜WP-5 の状態は main の合格条件を満たさない。**WP-2〜WP-5 の完了判定は、`tools/dev/pt.py` で回した C-28 の node × plug の期待結果表 (xfail / XPASS(strict → FAILED) / XPASS(non-strict)) との一致で行う** (下表。完了条件の確定は作業指示書)。strict / non-strict の区別はこの branch の途中でだけ意味を持つ (D-4 の (vii))。**これは `OC` §1.1 の 3 (commit → main マージを 1 単位) の例外であり、採否は監督の裁定である** (前例: フェーズ9 の phase branch `phase9-contract-170`、merge `85e99fa`。ただし同前例は xpassed の規則 (2026-09-08、フェーズ10 WP-1c) より前であり、xpassed を想定していない)。

| WP | 内容 | 依存 | 主に触るファイル |
|---|---|---|---|
| **WP-1** | 契約 1.9.0 の文言と記録 (spec 本体・同梱 copy 2 本・`CONTRACT_HISTORY`・`CCR_DISPOSITION`・`OPERATION_CATALOG`・`README`・`test_contract.py` の逐語ピン)。**本書・台帳行 (R-106 の起票) ・`CONDITIONS.md` の C-28 行 (`declared`) を同じ変更セットに置く** (`check_doc_refs` は例外表を持たない。本節末の註)。**peer の宣言値は上げない**。**v0.4 で足した: `CONDITIONS_HISTORY.md` に空でない `## C-28` を置く (D-5。指摘 13)。本 WP も単独では main に載せない (統合 branch)**。**【v0.5 (2026-09-24) で足した。作業指示書起草時の疑義 2 への監督裁定】 R-107 の台帳行 (本節の「WP-1 の材料」の案文) も R-106 行と同時に置く** — 本書と作業指示書が R-107 を引くので、WP-6 まで待つと WP-1 の変更セットで dangling になる (9 件) | Q-3 の確定文 | `spec/*`、両 peer `contract/*.json`、`conformance-tests/test_contract*.py`、**v0.4: `conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md`、`RM`、本書** |
| **WP-2** | port v1.16 (`query_page`) を `adapter.py` と 6 plug に足し、**C-28 を両 peer で赤になる状態で置く** (この時点では両 peer が 1.8.0 宣言なので `xfail(strict=True)` で赤ではなく xfail。中身の assert は実行される)。**【v0.3 (2026-09-24) で改めた】 版ゲートは D-4 の node ごとの 2 種 — (ii) の node だけ `xfail(strict=True)`、他の 8 node は `xfail(strict=False)`。** r2db は現行でも一部の node を通すので、全 node を strict にすると本 WP のコミットで XPASS = 赤になる (設計レビュー 1 の指摘 4)。本 WP の完了時点で 6 plug の全 node が xfail または non-strict XPASS であり、赤は 0。**【v0.4 (2026-09-24) で改めた】 上の「赤は 0」を消す** — xfail も XPASS も main の合格条件では赤である (統合 branch の段落)。本 WP の完了は期待結果表との一致で判定する。**v0.4 で足した: port `query_page` の `budget` (D-4)。`CONDITIONS.md` の C-28 行の Status を `executable (six adapters) …` に上げる (register test の都合。D-5)。期待結果 (branch 上)**: MitateDB 3 plug — 9 node すべて xfail (cursor は `CAPABILITY_UNSUPPORTED`、`next_page` は常に null)。r2db 3 plug — (ii) は xfail、他の 8 node は xfail か XPASS(non-strict) で、どちらかは実測で表を確定する (設計レビュー 2 の見込みは (i)(iv)(v)(viii) が XPASS(non-strict))。**【v0.5 (2026-09-24) で足した。作業指示書起草時の疑義 4 への監督裁定】 MitateDB の cursor 付き読み出しの入口を `ApplicationRuntime` に、実体を `ApplicationCell` に置き (runtime の入口 → cell の実体。D-2b の 4 の新メソッド。実体は WP-4 まで現行と同じ拒否か `(rows, None)`)、`http.py` の query endpoint をこの入口を呼ぶ形に切り替えて `http.py` 側の cursor 拒否を消す。MitateDB の plug の `query_page` は cursor を逐語で渡すだけである。拒否の call site が `http.py` から `cell.py` へ移るので、L1 走査の件数ピン (`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`:590 `"cell.py": 42`、:594 `"http.py": 27`) が変わるときは実測値へ追随させる (`OC` §1.5 の 40b)。期待結果は上と変わらない** | WP-1 | `conformance-tests/adapter.py`、`conformance-tests/test_c28_keyset_paging.py`、6 plug、`CONFORMANCE_ADAPTER_V1.md`、**v0.4: `conformance-tests/CONDITIONS.md`**、**v0.5: `MitateDB-api/src/mitatedb_api/{cell,http}.py`、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`** |
| **WP-3** | MitateDB の隠し列 `_mdb_row` — `CREATE TABLE` 経路、`field_domains` からの除外 (**v0.3: `ApplicationCell` の private helper 1 本に 6 箇所の呼び出しを通す。backend は触らない。D-2 の select 行**)、migration `0015_*_upgrade.sql`、`PLATFORM_UPGRADE_NUMBERS` と `0003` の seed list、SQLite backend の `CREATE TABLE`。**v0.4 で足した: migration 0015 の列挙元・冪等形と、lock 保持がデータ量に比例することの README upgrade 節への開示 (D-2 の適用行。指摘 15)、`_mdb_field_types` の `DISTINCT entity` との一致の実測を §11 へ、helper による `_mdb_row` の除外を MitateDB 側の単体テストで固定 (D-2 の select 行。v0.3 起草担当の疑義 1)。期待結果 (branch 上)**: C-28 は WP-2 の後と同じ (MitateDB 3 plug は 9 node すべて xfail — cursor がまだ受理されない) | WP-2 | `MitateDB-api/src/mitatedb_api/{backend_postgres,backend_sqlite,cell,platform_upgrades}.py`、`MitateDB-api/migrations/*`、**v0.4: `MitateDB-api/README.md`、MitateDB 側の単体テスト (ファイル名は作業指示書で確定。`MitateDB-api/tests/**`)** |
| **WP-4** | MitateDB の keyset read と cursor — `paging.py` (codec)、`http.py` の `page.cursor` 受理 (CAPABILITY_UNSUPPORTED を外す)、`cell.read` の cursor 引数、`backend_*.read` の keyset 述語と ORDER BY 末尾、**両 backend への `NULLS` 句の明示 (D-2a)**、`next_page` の返却。**v0.3 で足した: 順序項と `_mdb_row` の内部射影と応答直前の除去 (D-2 の応答行)、復号値の個数・型の検査 (D-2b の 1)、`http.py` の Page 受理直後の `page.size` 契約範囲 (1..1000) の検査 (D-2b の 2)、既定ページ = D-1 (2a) の最小値 + 先読み (D-2b の 3)**。**【v0.4 (2026-09-24) で改めた】 `page.size` 契約範囲の検査位置は `http.py` ではなく `ApplicationCell.read` の `limit` 受理直後 (D-2b の 2。指摘 4)。v0.4 で足した: `(rows, next_page)` を返す新しい cell メソッドと、既存 `read` のそれへの委譲 (D-2b の 4)、`check_declared_value` / `encode_value` の `ValidationError` の `page/cursor` への写し替え (D-2b の 1。指摘 14)、in-process / http / socket の 3 adapter の `query_page` を新メソッドへ、`MitateDB-api/tests/test_http.py`:798-803 (`CAPABILITY_UNSUPPORTED` のピン) の更新、新しい `paging.py` か呼び出し側に denial を置くときの L1 走査 guard (`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`:840 `test_every_module_with_a_vocabulary_denial_is_accounted_for`) への計上。期待結果 (branch 上)**: MitateDB 3 plug — (ii) は **XPASS (strict → FAILED)** (v0.3 起草担当の疑義 3 への監督裁定)、他の 8 node は XPASS(non-strict)。r2db 3 plug は WP-2 の後と同じ。**【v0.5 (2026-09-24) で改めた。作業指示書起草時の疑義 4 への監督裁定】 上の「`http.py` の `page.cursor` 受理 (CAPABILITY_UNSUPPORTED を外す)」「`(rows, next_page)` を返す新しい cell メソッド」「3 adapter の `query_page` を新メソッドへ」は WP-2 に移った (入口の設置、`http.py` の切り替え、adapter から入口への cursor の逐語の運搬)。本 WP は WP-2 が置いた cell の実体を差し替える (cursor の受理と `next_page` の返却。D-2b の 1〜4)。3 adapter は変更が要るときだけ触る** **【v0.6 (2026-09-24) で足した】 束縛 hash を両 peer 同名の helper `canonical_page_binding` で作る (`where` の述語の並びに依らない。D-2b の 5)。期待結果は変わらない** | WP-3 | `MitateDB-api/src/mitatedb_api/{paging,http,cell,backend_postgres,backend_sqlite}.py`、**v0.4: `MitateDB-api/conformance/conformance_adapter_mitatedb*.py`、`MitateDB-api/tests/test_http.py`、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`** |
| **WP-5** | r2db の keyset — `paging.py` の codec 差し替えと shape hash の縮小、`postgres_sql.py` の述語、`postgres.py` / `structured.py` の実行、`field: page/cursor` の是正、**`validate_page_size` の details 是正 (D-3 の 8)**。**v0.3 で足した: 復号値の個数・型の検査と `_bind_value` によるバインド (D-3 の 4a・4b)、既定ページ = D-1 (2a) の最小値 (D-3 の 9)、内部射影 (D-3 の 10)、r2db の旧 details を固定する既存テスト 4 箇所の更新 (D-3 の 8)。完了条件の骨子: r2db 3 plug で `test_c28_concurrent_insert_discriminates_keyset_from_offset` が XPASS (strict → FAILED) になること — keyset が offset 判別を通し、かつ宣言がまだ 1.8.0 であることの証拠であり、この赤は WP-6 で緑になる**。**v0.4 で足した (指摘 13・14): (4a) の検査は `_check_type(value, field_type, "page/cursor")` (D-3 の 4a)、`request_shape.py`:22 の `field="cursor"` の是正 (D-3 の 7)、壊れる既存 r2db test の更新 — `r2db-api/tests/test_foundation.py`:2813-2821 (select を変えた cursor の拒否)、:2837-2846 (page_size を変えた cursor の拒否。Q-2 = A で反転する)、:2273-2292 (facade identity。`MAX_CURSOR_OFFSET` / `_shape_hash` / `_encode_cursor` / `_decode_cursor`)、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:490 の `"paging.py": 10` (fail call site 数のピン。`OC` §1.5 の 40b)。期待結果 (branch 上)**: r2db 3 plug — (ii) は **XPASS (strict → FAILED)**、他の 8 node は XPASS(non-strict)。MitateDB 3 plug の期待は WP-4 の行による **【v0.6 (2026-09-24) で改めた】 上の「shape hash の縮小」は束縛 hash の正規化を含む — (Application, entity, 正規化した `where`, `order_by`) を両 peer 同名の helper `canonical_page_binding` で作る (D-3 の 3、D-6)** | WP-2 | `r2db-api/src/r2db_api/{paging,postgres,postgres_sql,structured,inmemory_sort,service}.py`、`r2db-api/tests/{test_foundation,test_http}.py`、**v0.4: `r2db-api/src/r2db_api/request_shape.py`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`** |
| **WP-6** | **版フリップ (両 peer 同一コミット)** — `capabilities_document.contract_version` 1.9.0、`_ISOMORPHIC_TARGETS` への codec 登録 (監督の pair-closing)、`CONTROL_MAPPING.md` 3.2、`CONDITIONS.md` の C-28 行、台帳 (`RM` §0.1.1 の G-2/G-3 と §8 の行)。**v0.3 で足した: 件数ピン test の `..._158_rows` への改名 (表の行と test 名、両 peer 同一コミット。D-6 (a))。完了条件の骨子: 版フリップの同一コミットで、WP-5 の時点で XPASS (strict → FAILED) だった r2db 3 plug の `test_c28_concurrent_insert_discriminates_keyset_from_offset` が緑になること**。**v0.4 で改めた・足した: `CONDITIONS.md` の C-28 行は Status 本文の確定に留める (`executable` への変更は WP-2。D-5)。件数ピンの改名は pin 本体の表の逐語コピーと docstring にも追随する (D-6 (a))。完了条件の骨子: 6 plug で C-28 の 9 node がすべて passed (MitateDB 3 plug の (ii) も、WP-4 の時点の XPASS (strict → FAILED) から緑になる)。本 WP も main には載せない (統合 branch)**。**【v0.5 (2026-09-24) で足した。作業指示書起草時の疑義 1 への監督裁定】 両 peer の control 側宣言 (`r2db-api/src/r2db_api/control_plane.py`:633、`MitateDB-api/src/mitatedb_api/control_plane.py`:1595) も同じコミットで 1.9.0 にする** — C-19 が data 側と control 側の版の一致を assert する (`conformance-tests/test_c19_client_self_sufficiency.py`:258)。1.8.0 を pin する既存テストも同じコミットで追随させる。**完了条件の骨子に「両 peer の control 側宣言も 1.9.0 (C-19 緑)」を足す。【v0.5 で改めた。疑義 2】 §8 の R-107 行は WP-1 で置く — 本 WP の台帳の行は R-106 の完了の追記である** **【v0.6 (2026-09-24) で改めた】 `_ISOMORPHIC_TARGETS` に足す行は 3 行 (codec 2 行 + `canonical_page_binding`)、件数ピンの改名先は `..._159_rows` (WP-6 で実測して確定。D-6 (a))** | WP-4 + WP-5 | 両 peer `capabilities_document.py`、`MitateDB-api/tests/test_audit_query.py`、`r2db-api/tests/test_audit_query.py`、`security/CONTROL_MAPPING.md`、`conformance-tests/CONDITIONS.md`、`RM`、**v0.5: `r2db-api/src/r2db_api/control_plane.py`、`MitateDB-api/src/mitatedb_api/control_plane.py`、`r2db-api/tests/test_foundation.py` (:244 ほか)、`r2db-api/tests/test_control_plane_service.py` (:1808)、`MitateDB-api/tests/test_http.py` (:382)、`MitateDB-api/tests/test_control_plane_service.py` (:574)、`r2db-api/tests/test_denial_details_and_request_id.py` (:499)、`MitateDB-api/tests/test_denial_details_and_request_id.py` (:522, :536)** |
| **WP-7** | 性能の証拠 (D-7) — `tools/perf_baseline.py` の差分 (K=1) と、深いページの offset / keyset 比較 1 回。§11 に記録。**v0.4: 本 WP の後に完了ゲート (`tools/dev/gate.py`) を 1 回回し、main へ 1 回だけ merge する (統合 branch。Q-4 の確認はこの merge の前)** | WP-6 | 設計文書 §11 のみ (道具は増やさない) |

**C-28 の期待結果表の骨子 (v0.4 (2026-09-24)。統合 branch 上の状態。node × plug の完全な表と完了条件は作業指示書で `tools/dev/pt.py` の実測により確定する)**

| 時点 | r2db 3 plug の (ii) | r2db 3 plug の他 8 node | MitateDB 3 plug の (ii) | MitateDB 3 plug の他 8 node |
|---|---|---|---|---|
| WP-2 完了 | xfail | xfail か XPASS(non-strict) (node ごとに実測で確定) | xfail | xfail |
| WP-3 完了 | WP-3 の変更では変わらない | WP-3 の変更では変わらない | xfail | xfail |
| WP-4 完了 | WP-4 の変更では変わらない | WP-4 の変更では変わらない | **XPASS (strict → FAILED)** | XPASS(non-strict) |
| WP-5 完了 | **XPASS (strict → FAILED)** | XPASS(non-strict) | WP-5 の変更では変わらない | WP-5 の変更では変わらない |
| WP-6 完了 | passed | passed | passed | passed |

**WP-1 の材料 — R-107 の台帳行 (案文。実施はしない。§10 (5))**

**【v0.5 (2026-09-24) で改めた。作業指示書起草時の疑義 2 への監督裁定】 v0.4 までの見出しは「WP-6 の材料」であった。** R-106 行と同時に WP-1 で置く — WP-6 まで待つと、本書と作業指示書が引く R-107 が WP-1 の変更セットで dangling になる (9 件)。

`RM` §8 の表 (3 列: ID | 内容 | 行き先) に 1 行足す。R-105 行の形に合わせた案文である。**番号は merge 直前に main で振り直す。**

> | **R-107** | **規模 S — 片方の拒否コードを直す 1 箇所の変更 (実装担当 1、レビュー担当。Class C = 契約の意味の決定と `conformance-tests/`)。着手条件: 印なし (契約の意味に触れるので運用前)。** **`order_by` に未知の field を指定したときの拒否コードが両 peer で違う。** r2db-api は `NOT_FOUND` (`r2db-api/src/r2db_api/paging.py`:71-72。`docs/design/R2DB_CCR13_STORAGE_V1.md` の訂正記録 m-6 による)、MitateDB-api は `VALIDATION_FAILED` / `violated_declaration: request_schema` / `field: order_by/<i>/field` (`MitateDB-api/src/mitatedb_api/cell.py`:3186-3189)。**同じ誤りに別のコードが返るので、共通契約を読んで書いた client が片方でしか通らない分岐を持つ。** 契約 `errors.codes` はどちらを採るとも書いておらず、`select` / `where` の未知 field の扱い (両 peer とも `NOT_FOUND` / `request_schema` のどちらか) との整合も同時に決める必要がある。**守るべき条件: どちらに揃えるかは契約側の決定であり、先に `spec/` の文を決めてから両 peer を合わせる** (開発順序。`CLAUDE.md`)。フェーズ11 (keyset ページング) の設計 `docs/design/PHASE11_KEYSET_PAGING_V1.md` §10 (5) で発見し、範囲外として起票した (監督裁定 2026-09-24) | **未着手** |

**並走 (触るファイルの重なり 0)**: **WP-4 (MitateDB) と WP-5 (r2db) だけが並走できる**。上の表のファイル列に重なりが無い (`MitateDB-api/src/**` と `r2db-api/src/**`)。他はすべて直列である — WP-1 → WP-2 → {WP-3 → WP-4, WP-5} → WP-6 → WP-7。**v0.4 (2026-09-24) で足したファイルでも重なりは 0 である** — WP-4 は `MitateDB-api/conformance/conformance_adapter_mitatedb.py`・`conformance_adapter_mitatedb_http.py`・`conformance_adapter_mitatedb_socket.py`、`MitateDB-api/tests/test_http.py`、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`、WP-5 は `r2db-api/src/r2db_api/request_shape.py`、`r2db-api/tests/test_foundation.py`、`r2db-api/tests/test_http.py`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` であり、同名の test file は peer ごとに別のパスである。どちらも `conformance-tests/` と `spec/` に触れない。**本件では並走させない (統合 branch のため。v0.5 (2026-09-24)、v0.4 起草担当の疑義 1 への監督裁定。順序は作業指示書 §1.1)。**

**並走の注意 (別チャットの R-29)**: R-29 (最低共通機能プロファイル) が**同じ `spec/`・`conformance-tests/CONDITIONS.md`・`RM`・`security/CONTROL_MAPPING.md`** に触れる。したがって:

- **契約版数 (1.9.0) と C 番号 (C-28) と台帳 ID (R-106) は、merge 直前に main を読んで振る。** 本書の番号は仮である。
- `RM` の版数ログは 1 merge に 1 版であり、5 版を超えた行は `docs/archive/` へ回す (`OC` §1.16 の 78)。並走で版数が衝突したら merge 側で振り直す。
- `CONDITIONS.md` は 1 つの表しか持てないので、行の追加は最後にまとめる。

**`check_doc_refs` の制約 (実測 2026-09-24)**: `tools/check_doc_refs.py` は例外表を持たない (同 script の冒頭「no exemption list, on purpose」)。したがって本書が引く **C-28** と **R-106** は、**本書を commit する変更セットの時点で** `conformance-tests/CONDITIONS.md` と `RM` §8 に行として存在していなければならない (本書単体では 27 件の dangling reference で赤になる。実測: `python3 tools/check_doc_refs.py`)。C-26 / C-27 が `declared` 行を先に置いた前例に倣い、**WP-1 で台帳行 (R-106 の起票) と C-28 の `declared` 行を同じ変更セットに置く** (監督裁定 2026-09-24)。**【v0.5 (2026-09-24) で足した。作業指示書起草時の疑義 2 への監督裁定】 R-107 も同じ制約に入る — WP-1 で R-106 行と同時に R-107 行 (上の「WP-1 の材料」) を置く。****設計文書を単独で commit しない。** 番号の確定は merge 直前である (本節の番号は仮である)。

---

## 10. 未確定事項と限界

1. **NULL の位置と型跨ぎの順序を peer 間で揃えない。** 契約 (D-1 (C-1)) は「実装が自分で固定する」とだけ言う。r2db は PostgreSQL 既定 (asc → NULLS LAST / desc → NULLS FIRST) に揃っており、**MitateDB は D-2a で両 backend を同じ規則に揃える** (監督裁定 2026-09-24)。したがって **peer の中では 1 つの順序**だが、**peer 間では揃わない**ことを契約が許す — 2 つの実装に同じ `order_by` を出したクライアントは、NULL を含む列や型が混在する untyped 列について、同じ並びを期待してはならない。**依存しない書き方 (クライアントが値を管理する field で order する) を契約文が案内する** (D-1 (C-1) の末尾)。**【v0.4 (2026-09-24) で改めた。設計レビュー 2 の指摘 11 への監督裁定】 上の「peer の中では 1 つの順序」を「NULL の位置は peer の中で 1 つ。文字列の照合順序は backend と配備の既定による (SQLite は BINARY、PostgreSQL は DB の既定)」に改める。** MitateDB は object / array / json を正規化 JSON の TEXT として並べ、r2db は jsonb の順序で並べる。案文 C-1 の最終文は、照合順序・null の位置・string / number / boolean 以外の値の比較を実装任意とする。
2. **cursor に署名しない。** 改竄した cursor は自分のページがずれるか `VALIDATION_FAILED` になるだけで、他 Application へは届かない (束縛の application と entity は復号後に照合される)。鍵を持てば P-1 に反する。**限界**: client が自分の cursor を復号すれば、自分が受け取った行の順序値が読める。これは自分のデータであり、非開示の対象ではない。(v0.3 (2026-09-24)) 案文 C-3 がこれを hazard として明記する — cursor は署名も暗号化も無い、自分の行の順序値の復元可能な符号化であり、保存・転送すればその値も一緒に運ぶ。発行の有無は検出しない (D-1 根拠 (5))。
3. **性能を契約に書かない。** 「費用がページの深さに比例しない」までが契約の文であり、数値は D-7 の計測記録にしか無い。閾値は `RM` §0.1.4 のものを使う。**【v0.3 (2026-09-24)】 「費用がページの深さに比例しない」の文も案文 C-3 から削った** (D-1 根拠 (3))。契約の文は「位置を符号化した」と「This contract states no performance figure」までであり、深さに比例しないことは D-7 の計測記録にだけ置く。
4. **cursor の符号化長は依頼者裁定 Q-5 待ちである** (§5.2)。D-1 (D) の案文は (a) `Page.cursor` の `maxLength` を外す形で書いた。(b) (上限を残して引き上げる) を採る場合は、**上限を超えて cursor を発行できないときの挙動**を契約に定義する必要が残る — 本書はそれを書いていない。**【v0.6 (2026-09-24)】 依頼者裁定 Q-5 = (a) で確定した (§5.1)。(b) についての上の文は両論の記録として残す。**
5. **`order_by` に未知の field を指定したときの拒否コードが両 peer で違う → 起票する (仮 **R-107**、規模 S、Class C。監督裁定 2026-09-24)。** r2db は `NOT_FOUND` (`paging.py`:71-72、訂正記録 m-6 による)、MitateDB は `VALIDATION_FAILED` / `request_schema` / `order_by/<i>/field` (`cell.py`:3186-3189)。同じ誤りに別のコードが返るので **DB の利用者が気づく** (`OC` §1.15 の 77 の 2 問目)。**本件の範囲外** (paging の意味ではなく既存の不一致) であり、**本変更セットで行うのは台帳行の追加だけで、実施はしない** (§9 WP-6 に行の案文)。**【v0.5 (2026-09-24) で改めた。作業指示書起草時の疑義 2】 行の追加は WP-1 である (§9 の「WP-1 の材料」)。**D-1 の案文はこの点に触れていない。
6. **既存行への `_mdb_row` の採番順は任意である。** migration が既存 table に列を足すとき、PostgreSQL が採番する順序は物理順であり、論理的な「挿入順」ではない。**移行後の既存行の tie-break 順は安定だが、挿入順とは限らない**。契約は tie-break の中身を約束しないので違反ではないが、開示として `CONDITIONS.md` の C-28 行 Status と MitateDB 側 README に書く。**【v0.3 (2026-09-24) で足した。設計レビュー 1 の指摘 16 = 観察】 SQLite backend の `_mdb_row` は rowid の別名であり、最大行の削除後に値が再利用されうる (PostgreSQL の identity は再利用しない)。** 契約は tie-break の中身を約束しないので適合上の差は無い。**`AUTOINCREMENT` は採らない** — SQLite は test double であり、`sqlite_sequence` 表の混入という新しい経路を作らない。探索 (2026-09-24) で `sqlite_sequence` は既に `_RESERVED` にあり (`MitateDB-api/src/mitatedb_api/backend_sqlite.py`:28-30)、`schema_count()` が `sqlite_%` を除外する (:92-96) と分かったが、形を増やさないという判断は変わらない。
7. **走査中の snapshot は約束しない** (D-1 (C-6))。読み取り一貫性を要求する消費者は別の手段を使う。本版はページングを定義するのであって、一貫した読み取り点を定義しない。**【v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 2 への監督裁定】 順序項が変わる行は 2 回返りうる。重複しないことを要する消費者は、順序項に更新されない field (例: 採番済みの seq) を使う。**
8. **本書の番号はすべて仮である** — 台帳 ID (R-106 / R-107)、条件番号 (C-28)、port 版 (v1.16)、migration 番号 (0015)、従属判断番号 (14)。**merge 直前に main の実測で振り直す** (§9 の並走の注意)。
9. **版フリップを跨ぐ走査は 1 回やり直しになる (v0.3 (2026-09-24) で足した。設計レビュー 1 の指摘 13 への裁定)。** 旧 offset cursor は移行しない (D-3 の 6) ので、版フリップの時点で走査の途中にいた client の次の要求は、1.8.0 で有効だった要求であっても paging.refusal のとおり拒否され、client は走査をやり直す。案文 A はこれを「a request valid under 1.8.0 stays valid in shape」と「A cursor an implementation issued before its own version-flip need not remain usable across it」で明記する。
10. **【v0.6 (2026-09-24) でこの開示を取り下げた。依頼者裁定 Q-3 の見直し 1 点 (§5.1)】** 束縛は `where` を述語の並びに依らない形で hash する (D-3 の 3、D-2b の 5) ので、同じ述語を並べ替えただけの要求でも cursor は有効であり、案文 C-4 は「the same where predicates, in any order」と書く。代わりに値の同一性の開示を 14 に足した。以下は v0.4 の旧文である (記録として残す)。旧: **`where` の並べ替えは別の束縛として拒否される (v0.4 (2026-09-24) で足した。設計レビュー 2 の指摘 9 への監督裁定)。** 両 peer とも `where` を並びを含めて hash する (r2db は順序つきの list を hash する。`r2db-api/src/r2db_api/paging.py`:99) ので、同じ述語の集合を並べ替えただけの要求でも cursor は拒否される。案文 C-4 は「the same where predicates in the same order」と明記する。
11. **NUL を含む cursor 値の扱いは backend で割れる (v0.4。指摘 14)。** 改変した cursor に NUL を含む文字列値を入れると、MitateDB の PostgreSQL の plug は `encode_value` で拒否し (`page/cursor` に写し替える。D-2b の 1)、SQLite の plug は受理する。改変 token についての差であり、C-3 の「a client that alters one receives an arbitrary position within its own result or a refusal」の範囲である。
12. **接続の独立と、cursor が時刻を含まないことは port から観測しない (v0.4。指摘 12)。** port は新しい接続を張らせる手段を持たず、粗い単位の時刻を混ぜた token は連続 2 要求で一致する。C-28 が観測するのは「別 credential の第 2 セッションで有効」と「同一要求で同一 token」までであり、C-28 の Status に開示する。
13. **migration 0015 の lock 保持はデータ量に比例する (v0.4。指摘 15)。** 1 transaction で Application の全 collection に列を足すので、ACCESS EXCLUSIVE の保持時間はデータ量に比例し、upgrade 中はその Application の全 collection への読み書きが待たされる。`--lock-timeout` が縛るのは取得だけである。MitateDB README の upgrade 節に開示する (D-2 の適用行)。
14. **束縛の `where` の値の同一性は JSON の等価性に依る (v0.6 (2026-09-24)。依頼者裁定 Q-3 の見直し 1 点の反映)。** `canonical_page_binding` は各述語の値を正規 JSON に直して整列し比べる (D-3 の 3) ので、2 つの要求の値が同じかどうかは値の JSON 表現で決まる。**`1` と `1.0` の扱いは各 peer の JSON 正規化に従う。** 起草時の読み取り (実測ではない): 両 peer の既存の正規 JSON (`normalize_request_for_plan`。`r2db-api/src/r2db_api/structured.py`:589-607、`MitateDB-api/src/mitatedb_api/cell.py`:67-103) は数値を型変換せずに Python の `json.dumps` へ渡すので、`1` と `1.0` は別の文字列 (`1` / `1.0`) になる。同じ作りを束縛に使えば、`where` の値 `1` で得た cursor は値 `1.0` の要求では束縛違いとして拒否される見込みである。**実装担当が両 peer で実測して §11 に記す** (WP-5・WP-4)。

---

## 11. 実施記録

(v0.4 (2026-09-24) で置き場として足した。実装担当が記入する。) 記入する項目: (v0.6) §10 の 14 の `1` / `1.0` の束縛の実測 (両 peer。WP-5・WP-4)、D-2 の適用行の列挙元と `_mdb_field_types` の `DISTINCT entity` との一致の実測 (0 field の collection の有無を含む。WP-3)、D-7 の性能の証拠 (WP-7)。D-5 の marker 走査の実測は D-5 の `spec/CONTRACT_HISTORY.md` 行に追記する (v0.3 の決定のまま)。

### WP-1 監査照合の記録 (2026-09-24。コードレビュー差し戻し反映 2026-09-25)

作業指示書 §2 WP-1 の完了条件番号 → 変異表 (§2) の「監査照合」5 件 (完了条件 5・11・12・13・14) の逐語記録。

**遡及列挙文の serial comma について (事実の記録。コードレビュー指摘 4)**: 遡及列挙文 (`versioning.version_binding` の「is not held to any …-only … obligation retroactively」型の各文) を 3 項目以上へ伸ばす際の区切りは、設計 D-1 (A) 直後の註が示した案文の形「`1.7.0-only, 1.8.0-only or 1.9.0-only`」(最後の項目の前にコンマを置かない) ではなく、契約 JSON の既存の列挙がすでに使っている形 (最後の項目の前にもコンマを置く。例: 既存の 1.5.0 宣言文の遡及列挙「1.6.0-only, 1.7.0-only, or 1.8.0-only」) と、契約 1.7.0→1.8.0 フリップ commit `654e23e` が同じ形でこの列挙を伸ばした実例に合わせた。実装はこの既存の形を採用した。

- **完了条件 5 (既存ピンの変更が 1.9.0 の追随に限られること)**: `conformance-tests/test_contract.py` への変更は (a) `test_contract_declares_1_8_0` → `test_contract_declares_1_9_0` への改名 + assert 値の版数追随、(b) `test_contract_pins_the_1_8_0_ruling_sentences_verbatim` の `obligations[-1]` 参照を `obligations_by_version["1.8.0"]` 参照に変更 (1.9.0 entry が末尾に追加されたための機械的追随。値そのものの比較対象 `FIXED_1_8_0_OBLIGATIONS_ENTRY` は無変更)、(c) `PIN_1_8_0_RETROACTIVE_DENIAL_ROW_1_7_0` を `"is not held to any 1.8.0-only obligation retroactively"` から `"is not held to any 1.8.0-only or 1.9.0-only obligation retroactively"` へ (契約 1.8.0 導入時に `PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_6_0` が受けたのと同じ機械的拡張)、(d) `PIN_1_6_0_VERSION_BINDING_PARAGRAPH` 末尾の遡及文と `PIN_1_7_0_RETROACTIVE_DENIAL_ROW_1_1_0`〜`_1_4_0`・`_1_6_0` の列挙にそれぞれ `1.9.0-only` を追加 (既存の `1.8.0-only` 追加と同じ形)。新規追加は 1.9.0 の pin 一式 (`FIXED_1_9_0_OBLIGATIONS_ENTRY`、`PIN_1_9_0_VERSION_BINDING_PARAGRAPH`、`PIN_1_9_0_PAGING_*`、`test_contract_pins_the_1_9_0_page_cursor_schema` 等) のみ。既存ピンの「値」自体 (1.2.0〜1.8.0 の文言) は 1 文字も変えていない — 変更は版ラベル列挙・参照方法・新規 pin の追加に限られる。実測 (コードレビュー差し戻し後の最終状態): `./.venv/bin/python tools/dev/pt.py -C <WT> --wait 300 -- conformance-tests/test_contract.py -q` → `pt: 34 passed in 0.26s`。
- **完了条件 11 (RM §8 の R-106/R-107 行、check_doc_refs 0 dangling)**: `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 に R-106 行 (規模 L・Class D) と R-107 行 (設計 §9「WP-1 の材料」の案文を逐語、行き先「未着手」) を R-105 行の直後に追加。実測: `(cd <WT> && python3 tools/check_doc_refs.py)` → `check_doc_refs OK: 0 dangling references` (SI/C/CCR/G/P/R/L の全 family で dangling 0、R: definitions=107 references=4095)。
- **完了条件 12 (spec/README.md の現行版の記述が 1.9.0)**: 1.7.0/1.8.0 の既存段落 (§ marker/anchor 状況の説明) と同形の段落を追加し、「Contract **1.9.0** (subordinate ruling 14, keyset paging) likewise adds no new `## <json_path>` anchor: ...」で始まる文を置いた (marker hit 0 件・新規見出し 0 の実測を含む)。
- **完了条件 13 (両 peer の宣言 contract_version が 1.8.0 のまま)**: 着手前 `grep -c '"contract_version": "1.8.0"'` は両 peer の `capabilities_document.py` でそれぞれ 件数 1 (WP-1 着手前の既存宣言)。WP-1 完了時点で同じ実測 (`r2db-api/src/r2db_api/capabilities_document.py` 件数 1、`MitateDB-api/src/mitatedb_api/capabilities_document.py` 件数 1) — 件数不変。`git status --short` で両 `capabilities_document.py` と両 `control_plane.py` が無変更であることも確認した (出力 0 行)。
- **完了条件 14 (conformance-tests の部分集合 2 本と両 peer suite が緑)**: `-- conformance-tests -k "not MitateDB" -q` → `pt: 701 passed, 407 deselected in 212.28s`。`-- conformance-tests -k "not r2db" -q` (既定の並列度、直列に近い) を 2 回実測するとどちらも `1 failed, 699 passed, 408 deselected` (`test_c27_concurrent_same_key.py::test_c27_same_digest_executes_once[MitateDB-api-http]`、HTTP 413 `LIMIT_EXCEEDED`)。同テストを単独再実行すると `5 passed`。**コードレビュー差し戻しの指示により、完了ゲートと同じ並列度 `-n 5 --dist loadgroup` を付けて再実測した**: `./.venv/bin/python tools/dev/pt.py -C <WT> --wait 300 -- conformance-tests -k "not r2db" -q -n 5 --dist loadgroup` → `pt: 700 passed in 125.57s` — 413 は消えた (xdist 5 並列では MitateDB-api-http 1 本あたりの呼び出し密度が下がり、レート制限に当たらなくなったとみられる)。**WP-1 が触れていない C-27/idempotency/rate-limit 関連ファイルに起因する既定並列度 (直列に近い) 固有の flake であり、WP-1 の変更によるものではないと判断する。直さない (WP-1 の範囲外、監督裁定)。** `-- r2db-api/tests MitateDB-api/tests -q` → `pt: 2918 passed, 2 subtests passed in 256.47s`。**`test_conditions_register.py` を除いた 3 file 実行** (register 3 件の failed が部分実行の性質 `test_conditions_register.py`:199-225 によるものであることを 4 file 実行時に確認済みのため): `-- conformance-tests/test_contract.py conformance-tests/test_contract_history_register.py conformance-tests/test_operation_catalog_register.py -q` → `pt: 54 passed in 0.22s`。**`--collect-only` の最終実測 (レビュー後)**: 全体 1108 件 (`test_contract.py` に完了条件 1・2 の 2 test を復元したぶん、コードレビュー前の 1106 件から +2)、`-k "not MitateDB"` 701/1108、`-k "not r2db"` 700/1108、和集合 1108 件 (全体と完全一致)。

### WP-2 監査照合の記録 (2026-09-25)

作業指示書 §3 WP-2 の完了条件番号 → 変異表 (§3) の「監査照合」5 件 (完了条件 4・5・6・8・9) の逐語記録。

- **完了条件 4 (`pt.py -rxX` の実測が期待結果表と一致し、F が 0 件)**: `./.venv/bin/python tools/dev/pt.py -C <WT> --wait 300 -- conformance-tests/test_c28_keyset_paging.py -q -rxX` → コードレビュー差し戻し反映後の最終実測 `pt: 57 xfailed, 21 xpassed in 32.05s`。57 + 21 = 78 = 13 node（T の 5 variant + 8 node）× 6 plug。**FAILED は 0 件**（I node は 6 plug すべて xfail のままで strict XPASS を起こしていない）。確定した表:

  | node | r | rh | rs | m | mh | ms |
  |---|---|---|---|---|---|---|
  | T | X | X | X | x | x | x |
  | I | x | x | x | x | x | x |
  | B | x | x | x | x | x | x |
  | A | x | x | x | x | x | x |
  | R | x | x | x | x | x | x |
  | S | X | X | X | x | x | x |
  | D | X | X | X | x | x | x |
  | DP | x | x | x | x | x | x |
  | PS | x | x | x | x | x | x |

  **コードレビュー差し戻し (2026-09-25)**: I の続きのページ読みと S・B の select 脚が `page_size` を同時に動かしていたため、S が見込み外の x になっていた。差し戻し反映後の実測は設計 §9 の見込み（(i)(iv)(v)(viii) が X = T, S, D, A）と比べ **T・S・D は見込みどおり X、A のみ x**。r2db 3 plug 共通で A（別 Application/別 entity の cursor 拒否）が x になる原因を実測した: r2db の現行 cursor 拒否は `details.field` に `"cursor"` を返す（1.9.0 の `page/cursor` ではない）ため、本 node の `details.get("field") == "page/cursor"` assert に落ちる — 束縛判定そのものは効いている（拒否は起きる）が、details のフィールド名が旧形のままという既知の是正対象（design D-3 の 7、WP-5 で `page/cursor` に直す）が原因であり、C-28 の観測は正しく機能している。
- **完了条件 5 (部分集合 2 本で failed=0、xfailed/xpassed が全て C-28 の node)**: `-- conformance-tests -k "not MitateDB" -q -rxX -n 5 --dist loadgroup` → `pt: 701 passed, 18 xfailed, 21 xpassed in 127.42s`。`-- conformance-tests -k "not r2db" -q -rxX -n 5 --dist loadgroup` → `pt: 700 passed, 39 xfailed in 139.70s`。両者とも failed=0。18 + 21 = 39（r2db 側、C-28 の 13 node × 3 plug）、39（MitateDB 側、13 node × 3 plug）で、他条件の xfail/xpass は 0 件。差し戻し対応の途中で 1 回 `conformance-tests/test_conformance_docstring_position_refs.py::test_every_real_conformance_tests_position_reference_resolves_or_is_allowlisted` が赤くなった（I node の追随コメントに前置パスの無い `(:234)` を書いたため）。該当箇所を書き直し、再実測で解消（下記完了条件番号外の逸脱に記録）。1 回だけ `test_c27_concurrent_same_key.py::test_c27_same_digest_executes_once[MitateDB-api-http]` が `not r2db` 側で単発 FAILED になったことも WP-1 の記録にある同一 subset の既知 flake と同種、本 diff と無関係。
- **完了条件 6 (`CONFORMANCE_ADAPTER_V1.md` §4.4 に port v1.16 の行がある)**: `git diff docs/design/CONFORMANCE_ADAPTER_V1.md` — §4.4 のコードブロックに `def query_page(...) -> tuple[list[dict], str | None]: ...  # port v1.16, C-28` の 1 行を `select_eq` の直後に追加（他は無変更）。
- **完了条件 8 (MitateDB の 3 plug の `query_page` が拒否を組み立てず、cursor を逐語で渡す)**: `grep -n "CAPABILITY_UNSUPPORTED\|ConformanceDenial(" MitateDB-api/conformance/conformance_adapter_mitatedb.py MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` の `query_page` メソッド本体（in-process 1736 行台・http 2786 行台）に該当行 0 件（3 plug の `query_page` はどちらも `where`/`order_by`/`cursor`/`budget` を wire 形へ写すだけで、denial の生成は `session.read_page` / 実サーバ応答に一任している）。socket plug は http plug の `query_page` をクラス継承でそのまま使う（独自コードなし、既存の select_eq 等と同じ形）。
- **完了条件 9 (`MitateDB-api/tests` 全体が緑)**: 差し戻し反映後の再実測 `-- MitateDB-api/tests -q` → `pt: 1459 passed, 2 subtests passed in 132.37s`（failed 0）。

**M2-1a/M2-1b の実測（完了条件番号→変異表の訂正）**: 作業指示書は「赤になる test: その plug の C-28 の node（adapter 生成の失敗）」と書くが、実測では `conformance-tests/conftest.py` が起動時に全 adapter を eager に構築するため（design section 3 principle 4「the suite fails rather than skips」）、`query_page` を削ると対象 plug の 1 node だけでなく **conftest 自体の import が `RuntimeError` で失敗し、pytest はそのファイル全体を収集できずに exit code 4（usage error 相当）で終わる**。`mutate.py` の `expect: "red"`（exit code 厳密に 1）ではなく `expect: "error"`（exit code 2-5 のいずれか）で判定し直した。ログ: `M2-1a.log`/`M2-1b.log` に `TypeError("Can't instantiate abstract class R2DBConformanceAdapter with abstract method query_page")` を記録。

### WP-2 コードレビュー差し戻し対応の記録 (2026-09-25)

監督裁定済みの差し戻し 5 件への対応。

1. **I node の続きページ読みを `page_size=2` に統一** (`conformance-tests/test_c28_keyset_paging.py`): 100 から 2 へ。M2-3a/b/c の実測ログがいずれも `AssertionError: ...: row(s) already returned on page 1 reappeared in the continuation ...` (`test_c28_keyset_paging.py:239`、`assert not repeats` の行) で落ちることを確認した。
2. **S node (:486 相当) と B node の select 脚 (:272-274 相当) を `page_size` 固定に修正**: S は session/credential だけを変え、B の select 脚は select だけを変える（`page_size=2` を維持）。再実測は完了条件 4 の表のとおり — S は X (見込みどおり)、A の x は `details.field` が `"cursor"`（1.9.0 の `page/cursor` でない）ことが原因と判明、design §11 に記録した。
3. **R node の個数・型不一致の脚を削除**: 「復号不能な文字列 / 別 Application / 別 entity / where 束縛違い / order_by 束縛違い」の 5 causes → 同一の 2 キー拒否、に作り直した。docstring と `CONDITIONS.md` の C-28 行 Status に「the number-and-type check on decoded ordering values is not driven through the port ...; it is pinned by each peer's own tests with tampered tokens」の開示を足し、「executable in this WP」等の時点依存の文は削った。個数・型検査の証拠は WP-5 (r2db)・WP-4 (MitateDB) の単体テストで足す（本 WP の範囲外）。
4. **comment provenance**: `http.py:653` の CH-0210 行と、その直前の "WP-8b: everything below..." 行は元の文言（`session.read`/`ApplicationRuntime.read` 参照）に戻した — レビュー実測により、`post_query`/`_sync` はどちらも with-block の内側にあるため AST descent が `_sync` の中まで潜らず、この 2 行を含む 3 個の CH-ID なし block が `post_query` scope の同一 anchor (`stmt#2`) に束ねられる；旧 `page.cursor` 拒否コメント塊 (`CAPABILITY_UNSUPPORTED` を選ぶ理由) は `ApplicationCell.read_page` の docstring へ逐語で移し、先頭の「WP-3 design decision」の「WP-3」だけを外して「Design decision」にした（§4.1 (5) の history token 検出を避けるため。本文は 1 字も変えていない）。新規に足した他の comment/docstring（`ApplicationRuntime.read_page`、http.py の cursor 読み出しコメント、`Phase 9 WP-3e` 以降の応答コメント）からも WP-n を除いた。**`python3 tools/check_comment_provenance.py --base HEAD MitateDB-api/src/mitatedb_api/cell.py MitateDB-api/src/mitatedb_api/http.py` の最終実測**:
   ```
   FAIL (§4.1 (1)) MitateDB-api/src/mitatedb_api/http.py:620 code changed (AST differs, docstrings excluded)
   FAIL (§4.1 (2)) MitateDB-api/src/mitatedb_api/http.py:616 scope/anchor ('post_query', 'stmt#2'): the sequence of CH-ID-less blocks changed (old 3, new 2) -- a block was added, removed, or moved to a different statement without a CH-ID reference
   FAIL (§4.1 (1)) MitateDB-api/src/mitatedb_api/cell.py:2149 code changed (AST differs, docstrings excluded)
   ```
   cell.py は指示どおり §4.1 (1) の 1 件のみ（実コード変更）に収まった。http.py は §4.1 (1) に加え **§4.1 (2) が 1 件残る** — 「WP-3 design decision」の comment 塊 (旧 `page.cursor` 拒否の理由) を `http.py` から丸ごと削って `cell.py` へ移したことで、`post_query` scope の CH-ID なし block 列が old 3 → new 2 になったため。

   **監督裁定 (2026-09-25、2 回目) への対応と実測**: `docs/code-history/MitateDB-api/http.md` に `CH-0542`（両 peer 通しの連番で既存最大 `CH-0541` の次。`moved from: src/mitatedb_api/http.py (post_query)`、`parent commit: 3af11b3`、`kind: comment`、fenced block は移動元の塊全体を dedent 後 byte 一致で登録）を追加し、`ApplicationCell.read_page` の docstring 末尾に `History: CH-0542` を足して実測したところ、**別の FAIL が新たに出た**: `FAIL (§4.1 (2)) MitateDB-api/src/mitatedb_api/cell.py:2151 companion CH-0542 does not byte-match any (remaining) original block in the same scope ('ApplicationCell.read_page')`。読解: `check_provenance_semantics` は `rel_path` 単位（`run_base` の `for rel_path in rel_paths` ループ）で呼ばれ、`old_blocks`/`old_positions` はその**同じファイルの** `--base` 版から作った木に限られる — CH-ID の companion 照合 (:3147-3153) も「同一 scope の unconsumed old block」だけを対象とし、コード上の注記どおり **cross-scope フォールバックが無い** (:3154-3159 "NO cross-scope fallback")。`read_page` は `cell.py` の新規メソッドで、`cell.py` の `--base` 版には対応する old block が存在しないため、companion 登録があっても `cell.py` 側では「一致する old block が無い」で必ず FAIL する。一方 `http.py` 側は「old block が新しい block で消費されない」ままなので、登録前と同じ `old 3, new 2` が residual する。**つまり `--base` モードはファイルを跨ぐ CH-ID の「moved from」を検証できない構造であり（`--register` モードが登録側の書式のみを見る別チェック）、登録によって `http.py`/`cell.py` いずれの FAIL も消えないことを実測で確認した。** 登録 (`docs/code-history/MitateDB-api/http.md` への追記、`cell.py` の `History: CH-0542` 行) は追加の FAIL しか生まなかったため、**両方とも元に戻した**（`docs/code-history/` は無変更、`cell.py` は `History:` 行なしの状態に復元）。`--base` の最終実測は登録前と同一 (下記)。**この 1 件 (http.py の §4.1 (2)) は実コード変更 2 件と同種の、正当な理由のある残留 FAIL として報告する** — 4.1(1) の 2 件だけには収まらなかった。

### WP-5 監査照合の記録 (2026-09-25)

作業指示書 §4 WP-5 の完了条件番号→変異表の「監査照合」6 件 (完了条件 1・9b・21・22・23・24) の逐語記録。

- **完了条件 1 (`pt.py -rxX` の実測が期待結果表と一致し、r2db の F が I だけ 3 件)**: `./.venv/bin/python tools/dev/pt.py -C <WT> --wait 300 -- conformance-tests/test_c28_keyset_paging.py -q -rxX -n 2` → `pt: 3 failed, 42 xfailed, 39 xpassed in 22.20s`。FAILED の 3 件は `test_c28_concurrent_insert_discriminates_keyset_from_offset[r2db-api]` / `[r2db-api-http]` / `[r2db-api-socket]`（I node、r2db 3 plug）のみ、他は全て `[XPASS(strict)]` の同一理由。確定した表 (コードレビュー差し戻し対応 B で T に変種 `tied_order_key` を追加し、9 node → 9 node のまま、T の variant 数だけ 5 → 6 になった。node 数の勘定は「T の 6 変種 + 他 8 node」= 14 id):

  | node | r | rh | rs | m | mh | ms |
  |---|---|---|---|---|---|---|
  | T (6 変種) | X | X | X | x | x | x |
  | I | **F** | **F** | **F** | x | x | x |
  | B | X | X | X | x | x | x |
  | A | X | X | X | x | x | x |
  | R | X | X | X | x | x | x |
  | S | X | X | X | x | x | x |
  | D | X | X | X | x | x | x |
  | DP | X | X | X | x | x | x |
  | PS | X | X | X | x | x | x |

  設計 §9 の見込み表 (WP-5 完了時点: r2db 3 plug の (ii) が XPASS(strict→FAILED)、他 8 node が XPASS(non-strict)) と完全一致。**既知の穴 (標準実行時の観察)**: この file を **並列度指定なしで単独実行**すると (`-n` を付けない場合)、r2db-api-http 側で `httpx.AsyncClient` が「Cannot send a request, as the client has been closed」を投げ、無関係な後続 node (例: PS) が FAILED になることを実測した (`tied_order_key` 追加後の 84 node で発現、5 変種времени の 78 node では未発現)。実測で切り分けた原因は **content ではなく総 node 数**（`-k` で任意の 3 node を追加で除外しても解消し、`tied_order_key` を並べ替えても位置に依らず再現する）——単独直列実行の httpx クライアント寿命に関わる資源上限で、`-n 2` 以上の並列度、または完了ゲートと同じ `-n 5 --dist loadgroup` では 3 回中 3 回とも発現しない (下記完了条件 24 の実測)。`conftest.py`/adapter 層はこの WP の触ってよいパス外であり、原因の切り分けのみ記録し実装しない。
- **完了条件 9b (`1`/`1.0` の束縛の実測、r2db)**: `PYTHONPATH=r2db-api/src python3 -c "from r2db_api.paging import canonical_page_binding; ..."` → `canonical_page_binding('app-x', 'items', [('n', 'eq', 1)], [('id', 'asc')])` = `ea9471961335d955`、`canonical_page_binding('app-x', 'items', [('n', 'eq', 1.0)], [('id', 'asc')])` = `03f384074928d02a`。**`1` と `1.0` は異なる束縛になる**（設計 §10 の 14 の起草時見込みどおり — `json.dumps` は型変換せず、Python の `1`/`1.0` はそれぞれ `"1"`/`"1.0"` という別のテキストになる）。MitateDB 側の実測は WP-4 で行う。
- **完了条件 21 (codec と `canonical_page_binding` の本体に comment が無く、`paging.py` に module 水準の可変状態が無い)**: `r2db-api/src/r2db_api/paging.py` の `canonical_page_binding`、`encode_page_cursor`、`decode_page_cursor` の本体を目視 — いずれも docstring のみで in-body `#` comment は 0 件。module 水準の代入は `MAX_PAGE_SIZE = 1000` と `MAX_ORDER_BY_FIELDS = 10` の 2 定数のみ（いずれも不変の int リテラルで、可変コンテナ・カウンタは無い）。
- **完了条件 22 (`MAX_CURSOR_OFFSET` と offset の符号化が消えている)**: `grep -rn "MAX_CURSOR_OFFSET" r2db-api/src/r2db_api/*.py` → 0 件。`grep -rn "_shape_hash\|_encode_cursor\b\|_decode_cursor\b" r2db-api/src/r2db_api/*.py` → 実装側 0 件（コードレビュー差し戻し対応 E で `http.py:466` の comment も新名 `decode_and_check_page_cursor` に直し、旧名の残存は 0 件になった）。
- **完了条件 23 (`r2db-api/tests` 全体が緑)**: `-- r2db-api/tests -q` → `pt: 1467 passed in 107.47s`（コードレビュー差し戻し対応 B/C/F の新設テスト 5 本、リネーム 1 本を含む。failed 0）。
- **完了条件 24 (部分集合 2 本、failed は r2db の I の 3 件だけ)**: `-- conformance-tests -k "not MitateDB" -q -rxX -n 5 --dist loadgroup` → `pt: 3 failed, 701 passed, 39 xpassed in 124.73s`（failed 3 件は全て I node、xpassed 39 = 13 id (T の 6 変種 + 他 7 node) × 3 plug の non-strict XPASS、xfailed 0）。`-- conformance-tests -k "not r2db" -q -rxX -n 5 --dist loadgroup` → 4 回実測: 2 回は `1 failed, 699/699 passed, 39/42 xfailed`（`test_c27_same_digest_executes_once[MitateDB-api-http]`、`AUTH_INVALID` — WP-1/WP-2 の記録にある既知の flake と同種）、2 回は `700 passed, 42 xfailed`（failed 0、うち直近 1 回は連続 2 回赤の直後の再実測）。本 WP が触れていない `test_c27_concurrent_same_key.py`/MitateDB 側ファイルに起因し、WP-5 の変更によるものではないと判断する。

### WP-5 コードレビュー差し戻し対応の記録 (2026-09-25)

監督裁定済みの差し戻し指摘 A〜F への対応。

- **A (comment provenance、指摘 1)**: `docs/code-history/r2db-api/{postgres,service}.md` の CH-0024・CH-0026・CH-0135 に `### correction: 2026-09-25` を追記 (`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §9.3、先例 CH-0541)。CH-0024 は新しい塊の末尾に `# history: CH-0024` を復元。実測: `python3 tools/check_comment_provenance.py --register` → `comment provenance register OK: 89 files scanned, 431 CH-IDs`。`--base HEAD <src 9 本 (旧 7 本 + http.py + value_types.py)>` → §4.1 (1) 8 件 (実コード変更) + (2) 15 件、(3) は 0 件 (旧 postgres_sql.py:55/service.py:721 の 2 件は解消)。`pt.py -- tools/tests/test_comment_provenance.py -q` → `pt: 303 passed in 31.77s`。
- **B (tie-break の固定、指摘 3)**: `test_foundation.py`/`test_postgres.py` に `test_cursor_pagination_uses_the_id_tie_break_when_the_order_by_field_ties` を追加 (3 行同値群が page_size=1 の境界を必ずまたぐ seed、asc/desc 両方)。C-28 の T に変種 `tied_order_key` を追加 (5 行、bucket が "x"×3/"y"×2 の 2 値のみ、order_by 1 項)。変異 4 本 (`postgres_sql.py`/`inmemory_sort.py` の tie-break 方向反転 × 新設単体テスト/C-28 新変種) を `mutate.py` で expect=red、全 4 件的中。
- **C (改変 cursor の 503、指摘 2)**: `value_types._check_type` に number (有限 float64) と string (lone surrogate 拒否) の定義域検査を追加 (`where`/`page/cursor` 共通)。`test_foundation.py`/`test_postgres.py` に `test_domain_out_of_range_values_are_validation_failed_*` を追加 (401 桁整数・`"\ud800"` が `where` と改変 `page/cursor` の両方で同一の 2 キー拒否)。既存の `test_postgres_data_error_from_an_out_of_range_number_value_is_validation_failed` は新しい早期拒否を反映して `test_postgres_write_of_an_out_of_range_number_value_is_validation_failed` に改名・assert 更新 (バックエンド層 `_fail_client_value` の no-details 経路はこの入力ではもう届かないことをdocstringに明記。**指示書外の判断**: この trigger の完了条件6 pin 自体の代替トリガは本 WP の範囲外として棚上げ)。変異 M5-11b (定義域検査を外す→ PostgreSQL の新設テストが 503 で赤) 的中。
- **D (`sort_keys=True`、指摘 4)**: `paging.py::encode_page_cursor` に追加。
- **E (指摘 5・6・7)**: `test_foundation.py` の SI-08 誤帰属 2 件を SI-01 に修正。`paging.py`/`postgres_sql.py` の経緯文 (WP-4/review 由来の語) を現在の規則だけの文に整理。`http.py:466` の旧名 `_decode_cursor` を `decode_and_check_page_cursor` に修正。本節末尾を「5 件」→「6 件」に修正 (本節冒頭)。
- **F (in-memory `result_items`、指摘 8)**: `structured.py` の `limits.check("result_items", ...)` を keyset 絞り込み (旧 :932) の後に移動。`test_foundation.py` に `test_cursor_continuation_result_items_check_counts_the_returned_rows_not_the_full_match_set` (10 行、`result_items=3` へ狭めた continuation、`page.size=5`、残り 2 行) を追加。変異 M5-F1 (検査位置を戻す→赤) 的中。

再実測 (全対応後): `-- r2db-api/tests -q` → `pt: 1467 passed in 107.47s`。`-- conformance-tests/test_c28_keyset_paging.py -q -rxX -n 2` → `pt: 3 failed, 42 xfailed, 39 xpassed in 22.20s` (期待結果表と一致)。`-- conformance-tests -k "not MitateDB" -q -rxX -n 5 --dist loadgroup` → `pt: 3 failed, 701 passed, 39 xpassed in 124.73s`。`-- conformance-tests -k "not r2db" -q -rxX -n 5 --dist loadgroup` → `pt: 700 passed, 42 xfailed in 127.38s` (直近の clean run)。`tools/public_value_scan.py` (差分 17 ファイル) → `total_flagged=0`。両 peer `capabilities_document.py` の `"1.9.0"` 残留 0。

### WP-3 実施記録 (2026-09-25)

D-2 の適用行 (migration 0015) の列挙元 (`information_schema.tables` の `public` の `BASE TABLE`、`_mdb_` で始まる表と `audit_events` を除いた集合) と `_mdb_field_types` の `DISTINCT entity` との一致の実測 (0 field の collection の有無を含む)。

- **通常経路 (`cell.py::ApplicationCell.create_collection`) は 0 field の collection を作れない**: `fields` が空/未指定だと `ValidationError` で拒否される (既存挙動、`tests/test_postgres.py::test_create_entity_defaults_to_a_base_id_field_when_fields_omitted` の docstring 「`create_collection` 自体は…still rejects an empty/missing fields」に既に固定されている)。したがって client 経由で宣言された collection は必ず 1 件以上のフィールドを持ち、`_mdb_field_types` に少なくとも 1 行を持つ — 通常経路だけを見る限り、テーブル列挙元と `_mdb_field_types` の `DISTINCT entity` は一致する。
- **しかし列挙元をテーブルスキャンにした理由が実測で裏付けられる**: developer 接続で raw DDL を発行すれば、`_mdb_field_types` に 1 行も書かれない collection (0 field 含む) が作れる (`PostgresBackend.create_collection` を `fields={}` で直接呼んだ場合も同様に 0 行になる — `backend_postgres.py`:970-972 の fallback は `fields` の各 field について registry 行を書くので、`fields` が空でない限り 0 行にはならない)。`MitateDB-api/tests/test_row_order_column.py::test_migration_0015_is_idempotent_and_enumerates_by_table_scan` で実測 (raw DDL のみ): raw DDL で作った `widgets` (2 列, 0 field 相当) と `emptycol` (0 列) はどちらも `_mdb_field_types` に対応する行を持たない (`SELECT DISTINCT entity FROM public._mdb_field_types` に現れない) が、migration 0015 適用後は両方とも `_mdb_row BIGINT GENERATED ALWAYS AS IDENTITY` を得た — 列挙元がテーブルスキャンだからであり、もし `_mdb_field_types` の `DISTINCT entity` を列挙元にしていたら、この 2 件は 0015 の対象から漏れていた。
- **結論**: 設計 D-2 の「列挙元は `information_schema.tables`…この enumeration は collection の superset として安全である」という判断は、0 field の collection (および cell 層を経由しない raw DDL 由来の collection) を安全側に含めるという点で、`_mdb_field_types` 起点の列挙より広く、実測もそれを裏付ける。同じテストで、この 2 件と対照的に、この package 自身の bookkeeping 表 (`_mdb_field_types` 自身) と予約名 `audit_events` は列挙から除外され、`_mdb_row` を得ないことも実測した。

**監督裁定 (2026-09-25) による migration 集合のピン追随**: `PLATFORM_UPGRADE_NUMBERS`/`0003` seed list への 15 の追加が、触ってよいパス外の 5 file・31 test を赤化させた (`pt: 31 failed, 1435 passed` → 対応後 `pt: 1466 passed, 2 subtests passed`)。監督裁定により当該 5 file を触ってよいパスに追加し、以下のとおり「現在の集合を固定するだけのピン」を 15 へ追随させた (意味の主張を伴う docstring は文言も直した)。

- `MitateDB-api/tests/test_platform_upgrade_ledger_scan.py:635-649` (`test_naming_convention_excludes_every_current_platform_single_shot_migration`): per-application upgrade script の件数を「4 件」から「5 件」に直し (意味の主張)、set に `0015_row_order_column_upgrade.sql` を追加。
- `MitateDB-api/tests/test_ops_upgrade.py:277-279, 295, 299-300, 340, 354, 374, 393, 397, 405, 442, 473-474, 502, 556, 601, 727, 748`: `{6, 8, 9, 10}` → `{6, 8, 9, 10, 15}`(または部分集合)の literal・CLI 出力文字列 (`applied=`/`pending=`) をすべて追随。
- `MitateDB-api/tests/test_platform_migration_reapply.py:284, 369-374, 605-609, 727, 748, 878, 1104-1110` (`_REAPPLY_PER_APPLICATION_UPGRADE_NUMBER_BY_FILENAME` に `"0015_row_order_column_upgrade.sql": 15` を追加。これが無いと `_apply_one` が 0015 を「変数不要な platform migration」枝に誤って落とし `-v app_id=...` を渡さず実 psql が構文エラーになる、**構造的な bug** であって単なる集合ピンではなかった。classification comment table にも 0015 の行を追加): `{6, 8, 9, 10}` → `{6, 8, 9, 10, 15}` の追随、および「6/8/9/10 を全部落として実適用させる」ループに 15 を追加 (意味を保つための追随)。
- `MitateDB-api/tests/test_platform_upgrades.py:216, 342-346, 390, 409-413, 422, 444, 605-609`: `{6, 8, 9, 10}` → `{6, 8, 9, 10, 15}`、F-12 の逐語メッセージに `15` を追加、`_FakeConnMissingLedger`/`_EmptyPendingConn` の fake fetchall に `(15,)` を追加。
- `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py:300-345` (`_BACKEND_LAYER_ALLOWLIST`、20 件): `backend_postgres.py` への行追加 (module 定数 +11 行、`create_collection` の列追加 +10 行) による line-number shift (前半 9 件 +12、後半 11 件 +22) を実測で追随。件数・対象site の同一性は不変。

再実測: `-- MitateDB-api/tests -q` → `pt: 1466 passed, 2 subtests passed in 133.39s`(対応前 1435 passed, 31 failed)。`-- MitateDB-api/tests/test_platform_upgrade_ledger_scan.py MitateDB-api/tests/test_ops_upgrade.py MitateDB-api/tests/test_platform_migration_reapply.py MitateDB-api/tests/test_platform_upgrades.py -q` → `pt: 123 passed in 28.33s`。`-- MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py -q` → `pt: 12 passed in 0.33s`。

**M3-5 (`PLATFORM_UPGRADE_NUMBERS` から 15 を外す)、`mutate.py` による実測のみ**: `M3-5    expect=red   got=red       OK  | 1 failed in 0.07s | restore=ok`(対象 `test_platform_upgrade_ledger_scan.py::test_real_migrations_three_way_match`、単一)。**コードレビュー差し戻し (指摘 1・6)**: 完了条件 3 の M3-3 は SQLite/PostgreSQL 2 test を 1 entry にまとめていたため、`mutate.py` の `-x` が SQLite 側の赤で止まり、PostgreSQL 側 (`test_visible_field_domains_excludes_the_row_order_column_on_postgres`) が本当に除外を観測しているかは実測されていなかった (`fields=["name","score"]` の明示 read だけでは除外の有無に関わらず `_mdb_row` は出ない)。両 test に select-all (`fields` 省略) の読み出しと assert を足し、PostgreSQL 側には `cell._visible_field_domains("widgets") == {"name": "string", "score": "int64"}` の等値 assert (ドメイン値は実測) を追加。M3-3 を M3-3a (SQLite) / M3-3b (PostgreSQL) の 2 entry に分けて `mutate.py` を再実行し、両方 `got=red` を確認した: `M3-3a    expect=red   got=red       OK  | 1 failed in 0.09s | restore=ok` / `M3-3b    expect=red   got=red       OK  | 1 failed in 0.30s | restore=ok`。以後、変異は `mutate.py` 経由のみで測る。

### WP-4 実施記録 (2026-09-25)

**完了条件 9b (`1`/`1.0` の束縛の実測、MitateDB)**: `paging.canonical_page_binding("app_a", "widgets", [("rank", "eq", 1)], order_spec)` と同じ引数を値だけ `1.0` に変えた呼び出しを比較すると、2 つの hash は一致しない (`2d54e1f4758cac51` != `db98cd8339664684`) — MitateDB の `normalize_request_for_plan` と同じく、`canonical_page_binding` も数値を型変換せず `json.dumps` へ渡すため `1` と `1.0` が別の JSON 表現になる。r2db 側は WP-5 で同じ結果を実測済み (D-3 の 3)。

**完了条件 18 (正規化 diff と `paging.py` の file:line)**: `r2db-api/src/r2db_api/paging.py` と `MitateDB-api/src/mitatedb_api/paging.py` の `encode_page_cursor`/`decode_page_cursor`/`canonical_page_binding` の 3 関数を、`tests/test_audit_query.py::_normalize` と同じ手順 (`_strip_leading_docstring` → パッケージ名 2 通りの置換 → 行末空白除去 → 連続空行の圧縮) で比較した結果、3 関数とも **MATCH**(1 文字も違わない)。`MitateDB-api/src/mitatedb_api/paging.py` は新規ファイルで module 水準の可変状態を持たない (import と 3 関数のみ)。本体に in-body comment は 0 件 (docstring のみ)。`_ISOMORPHIC_TARGETS` への登録は WP-6 の pair-closing commit (本 WP では表に触れていない)。

**完了条件 19 (SQLite の版)**: 監督裁定により、監査照合ではなく実行可能な pin に変えた -- 新規 `MitateDB-api/tests/test_sqlite_version_floor.py::test_sqlite_version_meets_the_nulls_first_last_floor` が `sqlite3.sqlite_version_info >= (3, 30, 0)` を assert する。実測: 本リポジトリ `.venv` の Python の `sqlite_version` は **3.53.4**(D-2a の実測と同じ)。実際の CI runner (`actions/setup-python@v5` が取得する 3.11/3.12 のビルド) での実測は依然未確認のまま -- push 再開後の課題として引き継ぎ書に残す。

**完了条件 1・20・21 (`pt.py` の実測、コードレビュー差し戻し対応後の再実測)**:
- `-- MitateDB-api/tests -q` → `pt: 1468 passed, 2 subtests passed in 156.38s`
- `-- conformance-tests/test_c28_keyset_paging.py -q -rxX -n 2` → `pt: 6 failed, 84 xpassed in 39.80s`(期待結果表と一致: I の 6 件だけ FAILED、xfailed 0。T は新変種 `null_valued_field_desc` を含む 7 変種 × 6 plug)
- `-- conformance-tests -k "not MitateDB" -q -rxX -n 5 --dist loadgroup` → `pt: 4 failed, 701 passed, 41 xpassed in 120.09s`(r2db の I 3 件 + 新たな flake 1 件、下記)。3 回とも同じ結果を再現した。
- `-- conformance-tests -k "not r2db" -q -rxX -n 5 --dist loadgroup` を 2 回: 1 回目 `pt: 4 failed, 699 passed, 42 xpassed in 131.66s`(MitateDB の I 3 件 + `test_c27_same_digest_executes_once[MitateDB-api-http]` の既知 flake 1 件)、2 回目 `pt: 3 failed, 700 passed, 42 xpassed in 132.38s`(同 flake は再現せず、I の 3 件のみ)。**本セッションでの頻度は 2 回中 1 回** -- 前回チャットの 3/3 より低い(fixture を HEAD の 5/50 へ差し戻した効果の可能性はあるが、試行数が小さく断定はできない)。

**新たな flake (`test_c28_page_size_outside_schema_is_refused_at_page_size[r2db-api-http]`、"not MitateDB" 部分集合のみ)**: T に変種を 1 つ足したことで `--dist loadgroup` の item 配分が変わり、単独実行では通る (`pt: 1 xpassed`) この node が、`-n 5 --dist loadgroup` の下では 3/3 回とも `RuntimeError: Cannot send a request, as the client has been closed.`(httpx `AsyncClient`)で失敗することを実測した。新変種を一時的に外して同じコマンドを再実測すると 3 failed に戻り(この flake が消える)、戻すと 4 failed に戻ることを確認した(診断用の一時変更で、直後に元へ戻した。差分は変更前後で 0)。原因は `conformance-tests/conftest.py` または r2db-http adapter 側の fixture 有効期間の競合と見られ、本 WP の touchable path (MitateDB 側 + `test_c28_keyset_paging.py` 自身の variant 定義のみ) の外にある。報告に記載し、起票判断は監督に委ねる。

`tools/public_value_scan.py`(差分 14 ファイル)→ `total_flagged=0`。両 peer `capabilities_document.py` の `"1.9.0"` 残留 0。`mutate.py` は 19/19 が期待どおり(対照 M4-0、M4-3〜M4-17 に加え、コードレビュー差し戻しで足した M4-5b/M4-5c を含む)。

**コードレビュー差し戻し対応の記録**:
1. [高] 孤立化 fixture (`max_result_rows`/`max_requests_per_minute`)の値と comment を HEAD `1c362fc` の 5/50 に戻した(下記「指示書外の判断」参照)。count() (bare/http adapter とも) を、既定ページ(D-2b の 3、`limit`/`page_size` 省略)を `next_page` で辿る形に改め、数えた行数 + 1 を超えるページ数で `AssertionError` になる終了ガードを足した -- `limit=1`/`page_size=1` の 1 行 1 要求では、fixture を差し戻した後の C-23 `full` 分岐が rate limit で赤になっていた(コードレビュー RV-1 の実測どおり)。
2. `backend_sqlite.py` の `NULLS` 句 comment から「measured against both CI Python jobs」の主張を削り、`test_sqlite_version_floor.py` が下限を固定している旨(実際の CI runner は未実測のまま)に置き換えた。
3. `_mdb_row` の cursor 値を `_decode_and_check_page_cursor` で `check_declared_value(value, "integer")` により明示検査するようにした -- `_mdb_field_types` に登録が無いため素通しの `declared_type=None` のままでは、SQLite plug が非整数の改変 tie-break 値(例 `"x"`)を受理してしまい、PostgreSQL plug (物理 `bigint` domain で拒否)と結果が割れる(D-2b の 1 に反する)。`MitateDB-api/tests/test_http.py` の tamper test に tie-break `"x"` の脚を 1 本足した。
4. 基点 `1c362fc` の `cell.py:2126-2132` の request_id comment(Phase 9 WP-3e、request_id の解決)を、現在の `read_page` の該当箇所(request_id 解決の直前)へ逐語で戻し、Phase 4 comment の「(`read`, internally)」も元の文へ戻して位置の補足を括弧で足した。`check_comment_provenance.py --base 1c362fc MitateDB-api/src/mitatedb_api/cell.py` を対応前後で比較すると、`ApplicationCell.read` stmt#0 の赤はこの対応で消える。同じ実行は今もほかに 3 件(`ApplicationCell` の 1 件、`_visible_field_domains` の 1 件、`ApplicationRuntime.read_page` の 1 件)の §4.1(2) を報告するが、この対応の適用有無に関わらず同一(実測比較済み)であり、WP-2/WP-3 で新設した class member の挿入が CH-ID を持たない既存 comment block の「次の statement」対応をずらした構造的な副作用である。解消には移動元・移動先へ CH-ID を新設する記録作業が要り、本 WP の touchable path の外にある。両論を報告に記す。
5. C-28 の T に変種 `null_valued_field_desc` を追加した(監督裁定。desc の NULL 分岐 -- PostgreSQL `_NULLS_SQL["desc"]`(`NULLS FIRST`)/ SQLite `_NULLS_TOKENS["desc"]` -- を観測する node がそれまで無かった)。コードレビュー RV-2 と同形の述語 FALSE 分岐破壊(変異 M4-5b)、RV-3 と同形の SQLite `NULLS LAST` 破壊(変異 M4-5c)がどちらもこの変種で赤になることを確認した。

**D-2b への訂正註(監督裁定。本文は書き換えない)**:
- (D-2b の 2 について)検査位置の file:line (`cell.py:2103` / `:2136`) は、WP-4 で `ApplicationCell.read` の実体を `read_page` に一本化した後は陳腐化している -- `page.size` の 1..1000 検査は現在 `ApplicationCell.read_page` 内、`limit` 受理の直後にあり、`read` はそこへ委譲するだけの薄い口になった。単一 choke point・`http.py` に置かないという設計の意図そのものは変わらない。
- (D-2b の 3 について)cursor の復号・束縛検査(D-2b の 1)は、配備 bound (`result_items`) 検査(D-2b の 2)より先に実行される。cursor は要求の「形」の検査であり、配備 bound は「結果の資源」の検査である -- 前者を先に評価することで、孤立化 surface の小さい `max_result_rows` が cursor 由来の拒否を隠さない(C-28 の cross-application/cross-entity ノードが `page_size=100` を使う点で特に効く)。

**指示書外の判断(孤立化 fixture、監督裁定により差し戻し)**: WP-4 実装担当は当初、C-28 の B/A/S ノードの `page_size=100` 継続要求を通すため、孤立化 `FoundationConfig` の `max_result_rows`/`max_requests_per_minute` を上げていた。監督裁定により、誤りは C-28 側(継続要求が発行時の宣言値を無視して `page_size=100` を固定していた)にあると判断され、`conformance-tests/test_c28_keyset_paging.py` の該当 5 箇所(B ノード 3 箇所 → 2、A ノード 2 箇所 → 1)を発行時と同じ page_size に直し(監督実施)、fixture の値と comment は HEAD `1c362fc` の 5/50 へ差し戻した。count() の既定ページ走査化(上記コードレビュー対応 1)と組み合わせても、C-23 の `full` 分岐(rate limit)を含む C-05/C-23/C-24/C-27 の MitateDB 部分集合が緑であることを再実測した(上記集計行)。

