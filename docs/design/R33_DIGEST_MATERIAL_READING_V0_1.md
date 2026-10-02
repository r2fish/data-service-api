# R-33 digest の材料の静的読解 (v0.1)

- 版数: **v0.1 (2026-10-02)**。読解報告であり、裁定・実装・台帳更新を含まない。裁定と実装は作業機 (監督) が行う。
- 対象: branch `claude/funny-johnson-sw4fn4`、HEAD `05a60c0` (main と同じ内容)。file:line はすべてこの HEAD のものであり、台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 R-33 行の file:line (2026-09-08 時点) はその後の module 分割で動いているので本書で取り直した。
- 起票元: 台帳 R-33 (関連 R-25 閉止 2026-09-10、R-32 閉止 2026-09-14)、フェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §5 U-13 の (4)。
- 環境の制約: 本読解を行った環境では PostgreSQL が動かない (initdb 不可)。完了ゲート (`tools/dev/gate.py`)、変異 (`tools/dev/mutate.py`)、wire 実測はいずれも実行していない。したがって §4 以降の「見込み」は読んで導いたものであり、作業機でテストか変異で確かめる前提である。§2・§3 は読んで確認した事実だけを書く。
- 探索は explorer 2 体 (所在特定) に出し、意味の読解と表の照合は監督 (本セッション) が一次資料を直読して行った。

## 1. 結論

1. **台帳 R-33 の主張は現物と一致する。** `ApplicationCell.create_collection` (`MitateDB-api/src/mitatedb_api/cell.py:990`) は 4 番目の位置引数 `destructive=False` を受け取るが、本体 (`cell.py:990-1315`) のどこでも読まない。HTTP 層は body の `destructive` を `digest_extra` に畳んで同じメソッドへ渡す (`MitateDB-api/src/mitatedb_api/http.py:1058-1061`、呼び出し `http.py:1156-1161`)。
2. **`destructive` を `create_collection` に渡す呼び出し元は今も 0 件である** (§2.2。検索範囲は `git ls-files` の全追跡ファイル)。
3. **一般則「cell 経路の digest と HTTP 経路の `digest_extra` は一致していなければならない」の全数照合では、スキーマ操作 3 つの材料は `destructive` の死んだ引数を除いて一致している** (§3)。ただし **mutation 経路 (`transact`) に同じ種類の不一致が 1 件ある** — in-process 呼び出しが digest の per-operation 要素を内部語彙から再構築する (`cell.py:200-276`) ため、HTTP 経路 (`http.py:768-774`) と同じ論理要求でも digest が一致しないことを、コード自身の docstring (`cell.py:236-243`) が開示している。**不一致は合計 2 件** (§3 の表の行 1 と行 4)。
4. **r2db-api には同じ種類の構造が無い。** digest の材料 (`plan_request`) を組む箇所は mutation 1 箇所 (`r2db-api/src/r2db_api/service.py:385-393`)・schema 1 箇所 (`service.py:458`) であり、HTTP 層も in-process adapter も契約形の要求 dict をそのまま渡す (§2.3)。
5. **spec は digest の材料を「endpoint の request schema が名付ける要求オブジェクトの全フィールド (plan / dry_run、idempotency では idempotency_key も除く)」と定める** (`spec/data-service-api.v1.json:848`、`:851`)。`SchemaOperationRequest` は `destructive` を property に持つ (`:1241-1243`)。したがって **HTTP 経路が `destructive` を digest に入れるのは spec どおり**であり、問題は cell 側の引数が死んでいる (in-process から同じ要求を表現する経路が無い) 非対称そのものである。
6. 選択肢 (a) 死んだ引数を除く / (b) cell 自身の digest に畳む、の帰結は §5 に並べた。どちらにも寄せていない。

## 2. 事実 (file:line 付き)

### 2.1 台帳の主張の現物確認

| 主張 | 現物 | file:line |
|---|---|---|
| `create_collection` が `destructive=False` を受け取る | 署名 `def create_collection(self, principal, name, fields, destructive=False, *, request_id=None, field_types=None, field_constraints=None, dry_run=False, plan=None, digest_extra=None, operation="create_entity", idempotency_key=None, budget=None)` | `MitateDB-api/src/mitatedb_api/cell.py:990-993` |
| 本体がそれを読まない | 本体は `cell.py:990-1315` (次の `def` は `create_entity` の `:1316`)。この範囲で `destructive` という語が現れるのは署名行 `:990` だけ (`awk 'NR>=990 && NR<=1316 && /destructive/'` で確認) | `cell.py:990` のみ |
| digest の材料 | `digest_request = {"operation", "entity", "fields"}` に `field_types` / `field_constraints` / `budget` (いずれも `is not None` のとき) を足し、`digest_extra` で `update` し、`idempotency_key` を足す。`destructive` は入らない | `cell.py:1186-1207` (`if digest_extra:` は `:1204-1205`) |
| HTTP 層が body の `destructive` を `digest_extra` に畳む | `digest_extra = {key: body[key] for key in ("destructive", "confirmation", "revision", "index", "unique", "budget") if key in body}` | `MitateDB-api/src/mitatedb_api/http.py:1058-1061` (理由コメント `:1041-1057`) |
| その `digest_extra` が `create_collection` に届く | `session.create_entity(..., digest_extra=digest_extra, ...)` → `ApplicationDeveloper.create_entity` (`cell.py:3814-3838`) → `ApplicationCell.create_entity` (`cell.py:1316`) → `self.create_collection(...)` (`cell.py:1364-1367`)。この連鎖のどこも `destructive` を引数としては渡さない | `http.py:1156-1161`、`cell.py:3835-3838`、`cell.py:1364-1367` |
| in-process の公開入口は `destructive` を表現できない | `ApplicationDeveloper.create_collection(self, name, fields, *, request_id=None, field_types=None)` と `ApplicationDeveloper.create_entity(...)` の署名に `destructive` が無い | `cell.py:3809-3811`、`:3814-3816` |

補足: `digest_extra` の 6 キーのうち `budget` は cell 側も `budget is not None` で自前で畳む (`cell.py:1194-1203`。R-25 の是正 WP-1c) ので、HTTP 経路では同じ値で上書きされる。残り 5 キー (`destructive` / `confirmation` / `revision` / `index` / `unique`) は cell 側のどのスキーマ操作も自前の digest に入れず、in-process の公開入口 (`ApplicationDeveloper.*`) にも対応する引数が無い。**このうち `destructive` だけが `ApplicationCell.create_collection` に (死んだ) 引数を持つ**。これが台帳 R-33 の指摘した非対称の正確な形である。

### 2.2 `destructive` を `create_collection` に渡す呼び出し元 — 0 件

- 検索範囲と方法: 追跡ファイル全体 (`git ls-files -z | xargs -0 grep -n "create_collection("`、`docs/` を除く)。ヒットは `MitateDB-api/src/` 4 箇所 (定義 `cell.py:990`、backend の同名メソッド `backend.py:204` / `backend_postgres.py:1118` / `backend_sqlite.py:179`、呼び出し `cell.py:1304` / `:1364` / `:3811`)、`MitateDB-api/conformance/conformance_adapter_mitatedb.py` 5 箇所 (`:1443`、`:1629`、`:2901`、`:3024`、`:3029`)、`MitateDB-api/tests/` 多数 (`test_application_audit.py`、`test_application_plane_limits.py`、`test_budget_narrowing.py`、`test_denial_details_and_request_id.py`、`test_dry_run_and_plan.py`、`test_foundation.py` ほか)。
- 判定: **位置引数を 4 つ以上渡す呼び出し、`destructive=` キーワードを渡す呼び出しは 0 件**。`ApplicationCell.create_collection` を直接呼ぶテストは `cell.create_collection(dev, "t", {...})` の 3 位置引数の形 (例 `MitateDB-api/tests/test_application_plane_limits.py:79`)。`ApplicationDeveloper` 経由の呼び出しは署名上 `destructive` を持たない (§2.1)。
- `destructive=` キーワードの全追跡ファイル検索 (`grep -n "destructive="`) のヒットは `delete` / `revoke_credential` / `reset_control_credentials` / `drop_entity` の probe に限られ、`create_collection` / `create_entity` / `add_field` / `alter_field` へ渡すものは無い。
- conformance-tests: 共通 port `conformance-tests/adapter.py` の `schema_operation_with_result(..., destructive: bool = False, ...)` は MitateDB in-process plug (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:1641-1660`) で `create_entity` 分岐 (`:1731-1741`) が `field_types` / `field_constraints` / `dry_run` / `plan` / `budget` / `idempotency_key` だけを kwargs に詰めて `session.create_entity(entity, full_fields, **kwargs)` を呼び、`destructive` を渡さない。HTTP plug (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:2730-2748`) は `if destructive: body["destructive"] = True` で wire に乗せる (`destructive=True` を使う共通テストは `drop_entity` / `delete` のみ。`conformance-tests/test_c22_dry_run_and_plan.py:589-598`、`test_c06_destructive_confirmation.py`)。
- したがって **in-process で `create_entity` の digest に `destructive` が入る経路は現在存在せず、HTTP では body が `destructive` を運べば入る**。この非対称が到達可能になるのは `ApplicationCell.create_collection` を 4 位置引数で直接呼ぶ新しいコードが書かれたときだけである。

### 2.3 r2db-api — digest の材料を組む箇所は操作種別ごとに 1 つ

| 経路 | 所在 | 内容 |
|---|---|---|
| 正規化 helper | `r2db-api/src/r2db_api/structured.py:588` (`normalize_request_for_plan`)、`:609` (`compute_plan_token`)、`:646` (`normalize_request_for_idempotency`)、`:694` (`idempotency_digest`) | MitateDB の同名 helper (`cell.py:82` / `:121` / `:139` / `:168`) と同型 (R-32 の同型性 pin の対象) |
| mutation の材料 | `r2db-api/src/r2db_api/service.py:385-393` (`_mutate_outcome` 内の `plan_request = {"entity", "operations"}` + `transaction` / `budget` / `idempotency_key` を `is not None` で) | HTTP (`r2db-api/src/r2db_api/http.py:570-597`) は body から `operations` / `transaction` (key が在るときだけ) / `dry_run` / `plan` / `budget` / `idempotency_key` を取り出して `service.mutate_result` に渡す。in-process adapter も同じ service メソッドを契約形の `operations` で呼ぶ。材料を組むのは service の 1 箇所 |
| schema の材料 | `service.py:458` (`plan_request = {k: v for k, v in operation.items() if k not in ("plan", "dry_run")}`) | HTTP (`http.py:647-655`、`post_schema`) は shape 検査後の `body` をそのまま `service.schema(context, body, ...)` へ渡す。in-process adapter (`r2db-api/conformance/conformance_adapter_r2db.py:1372-1398`) は契約形の `op` dict (`destructive` は `if destructive: op["destructive"] = True`) を組んで `self._service.schema(session, op)` を呼ぶ。**要求オブジェクトそのものが材料**であり、HTTP と in-process で別々に組む箇所は無い |
| 受け付けるキーの集合 | `r2db-api/src/r2db_api/schema_binding.py:60` `_SCHEMA_KEYS` (`destructive` / `confirmation` / `revision` / `index` / `unique` を含む 18 キー)、pin `r2db-api/tests/test_foundation.py:3509` | `SchemaOperationRequest` の property 集合と一致 |

結論: r2db-api に R-33 と同じ種類の構造 (in-process 経路と HTTP 経路で digest の材料が別々に組まれる箇所) は無い。

### 2.4 spec が digest の材料について定めていること

- `spec/data-service-api.v1.json:848` `structured_operations.dry_run.plan`: 「The token is computed over this request as this contract defines it -- the request object this endpoint's own request schema names, not the bytes a particular transport delivered it in -- taking every field of that object except plan itself ... and dry_run ... Every other field, including budget, transaction, confirmation and idempotency_key, is part of what the token commits to」。直列化は「keys in lexicographic order, without insignificant whitespace, and without escaping non-ASCII characters, as UTF-8」。
- `spec/data-service-api.v1.json:851` `structured_operations.idempotency.record`: 「The digest is taken over the request object this endpoint's own request schema names, excluding idempotency_key itself, plan and dry_run, and is otherwise computed exactly as structured_operations.dry_run.plan describes: every other field, including budget, transaction and confirmation, is part of what a resend must match」。
- `spec/data-service-api.v1.json:1173-` `SchemaOperationRequest`: `additionalProperties: false` (`:1175`)、property に `destructive` (`boolean`、`:1241-1243`) と `confirmation` (`string`、`maxLength: 256`、`:1244-1247`) を持つ。`operation` ごとの `if`/`then` による絞り込みは無い (`:1173-1420` に `if` / `allOf` / `oneOf` 無し) ので、`create_entity` 要求が `destructive` を運ぶことは shape 上は許される。
- spec は「HTTP と in-process の一致」を直接には述べない。述べているのは「transport の byte ではなく契約上の要求オブジェクト」が材料であることで、台帳の一般則 (cell 経路と HTTP 経路の digest の一致) はこの文からの帰結である — 同じ契約上の要求を別の入口から出したとき digest が違うなら、材料が「契約上の要求オブジェクト」になっていない。
- conformance-tests: C-22 (`conformance-tests/test_c22_dry_run_and_plan.py`) と C-23 (`test_c23_idempotency_semantics.py:82-`) は決定性・再送・衝突を検査するが、**材料に特定のキー (`destructive` を含む) が入っているかを plug 間で突き合わせる vector は無い** (grep `digest|budget|differ|material` で該当テスト名なし)。`security/SECURITY_INVARIANTS_V1.md` と `security/CONTROL_MAPPING.md` には digest / idempotency / plan の語での直接の言及が無い (explorer の grep。監督は未直読)。

## 3. 照合表 — MitateDB-api、操作ごとの digest の材料

凡例: [ ] は条件付きで入るキー。「HTTP 側の材料」は `http.py` が渡すもの、「cell 側の材料」は `cell.py` が `digest_request` に自前で組むもの。`idempotency_key` はどの操作でも `is not None` で入る (`compute_plan_token` はそれを含め、`idempotency_digest` は除く) ので表から省く。

| # | 操作 | HTTP 側の材料 | cell 側の材料 | 一致/不一致 | file:line |
|---|---|---|---|---|---|
| 1 | `create_entity` (schema) | `fields` / `field_types` (raw、部分 map) / `field_constraints` / `budget` を個別引数で、加えて `digest_extra` = body の [`destructive`] [`confirmation`] [`revision`] [`index`] [`unique`] [`budget`] | `operation` (引数既定 `"create_entity"`)、`entity`、`fields`、[`field_types`]、[`field_constraints`]、[`budget`]、+ `digest_extra` の全キー | **不一致** — cell は引数 `destructive` を受け取るが digest にも実行にも使わない。HTTP は body の `destructive` を digest に入れる。`confirmation` / `revision` / `index` / `unique` は cell に引数が無く、in-process から表現できない (非対称ではなく「HTTP だけが運べる」) | HTTP `http.py:1058-1061`、`:1156-1161`; cell `cell.py:990`、`:1186-1207` |
| 2 | `add_field` (schema) | `field_type` の raw 値を `contract_type=` で、`enum` / `nullable` / `budget` を個別引数で、+ 同じ `digest_extra` | `operation="add_field"`、`entity`、`field`、[`field_type`←`contract_type`]、[`enum`]、[`nullable`]、[`budget`]、+ `digest_extra` の全キー | 一致 (cell に死んだ引数は無い。HTTP だけが運べる 5 キーは行 1 と同じ) | HTTP `http.py:1205-1212`; cell `cell.py:1369`、`:1451-1475` |
| 3 | `alter_field` (schema) | `enum` (`body.get("enum", UNCHANGED)`) / `nullable` / `field_type` / `budget` を個別引数で、+ 同じ `digest_extra` | `operation="alter_field"`、`entity`、`field`、[`nullable`]、[`enum` (`UNCHANGED` でないとき)]、[`budget`]、+ `digest_extra` の全キー。`field_type` は digest に入らないが、`is not None` なら digest の前 (`:1667-1671`) で `ValidationError` で拒否されるので材料に影響しない | 一致 | HTTP `http.py:1240-1244`; cell `cell.py:1606`、`:1699-1721` |
| 4 | `transact` (`POST /v1/data/{entity}/mutations`、`POST /v1/data/mutations`) | `digest_operations` = 契約形の各 operation の浅いコピー (`_mutation_digest_item` = `dict(raw)`)、`entity` (単一 entity endpoint だけ、top level)、`transaction` (body が運んだ raw 値)、`budget` | `{"operations": digest_operations または 内部語彙からの再構築 (`_reconstruct_digest_operation`)}`、[`entity`]、[`budget`]、[`transaction`] | **不一致 (同種、既知・開示済み)** — in-process 呼び出し (conformance plug、テスト) は `digest_operations` を渡さず、cell が内部 item (`type` / `collection` / `filters` / `confirm`、`values` は常に在る) から契約形を再構築する。再構築は `entity` を各 operation に置く (HTTP の単一 entity 要求は top level に置く)、`values` は item に在れば常に入る (HTTP は省略された `values` を入れない)。`cell.py:236-243` の docstring がこの「byte-identical でない」ことを開示し、閉じるには port file を触る必要があると書く | HTTP `http.py:768-774`、`:854-866`、`:942-947`; cell `cell.py:200-276`、`:2580-2581`、`:2700-2716`; in-process plug `MitateDB-api/conformance/conformance_adapter_mitatedb.py:2394-2400` |
| 5 | `delete` (in-process `ApplicationRuntime.delete`) | HTTP に単独の delete endpoint は無く、`transact` の `delete` operation として行 4 に含まれる | `ApplicationCell.delete` (`cell.py:2363`) は `idempotency_key` / `plan` を受け取らず digest を組まない (確認フレーズ用の `request` dict `:2373` は digest ではない) | 対象外 (digest を組まない) | `cell.py:2363-2373`、`:3709-3712` |

不一致の件数: **2 件** (行 1 = R-33 の起票内容、行 4 = 同種の既知の構造)。`destructive` 以外でスキーマ操作 3 つに食い違いは無い。R-25 (`budget: {}`) は 3 操作とも `is not None` で畳む形に是正済みであることを `cell.py:1194-1203` / `:1466-1470` / `:1712-1716` で確認した (`transact` も `:2711-2712`)。

## 4. 見込みと作業機での確かめ方

以下は読んで導いた見込みであり、本環境では 1 つも実行していない。各項に作業機で確かめるテスト名 (新規に書くもの) または変異 spec の案を添える。テストの置き場は既存の WP-1c のテスト (`MitateDB-api/tests/test_idempotency_records.py:372-410`、`test_dry_run_and_plan.py:332`、`test_http.py:1454` / `:1540`) に倣う。

| # | 見込み | 確かめ方 (テスト名 / 変異 spec の案) | 期待 |
|---|---|---|---|
| E-1 | `ApplicationCell.create_collection(principal, "t", {...}, True, dry_run=True)["plan"]` は `destructive` を渡さない同じ呼び出しと**同じ** token を返す (死んだ引数) | 特性化テスト `test_create_collection_destructive_argument_does_not_reach_the_plan_digest` (`MitateDB-api/tests/test_dry_run_and_plan.py`、cell を直接呼ぶ) | 現行コードで green = 欠陥の記録。選択肢 (b) を採れば red になる (そのときは名前を反転させて完了条件にする) |
| E-2 | HTTP `POST /v1/schema/operations` の `create_entity` に `destructive: true, dry_run: true` を付けると、付けない場合と**別の** token になる | `test_http_create_entity_plan_digest_commits_to_destructive` (`MitateDB-api/tests/test_http.py`) | green (spec `:848` どおり) |
| E-3 | HTTP で `destructive: false` を明示した body と省略した body は**別の** token になる (`digest_extra` は raw 値を入れ、省略は key ごと無し) | `test_http_create_entity_plan_digest_differs_between_omitted_and_explicit_false_destructive` | green。選択肢 (b) の実装がこの区別を壊さないかの監視点 (§5) |
| E-4 | HTTP で `create_entity` に `destructive: true` を付けた実要求は拒否されず、`committed: true` で実行される (shape は通り、cell は読まない) | `test_http_create_entity_accepts_and_ignores_destructive` | green。`revision` / `index` / `unique` / `confirmation` も同じ形と見込む (§6) |
| E-5 | 同じ論理の単一 entity batch を in-process plug と HTTP plug から dry_run すると token が**一致しない** (行 4) | 共通 suite ではなく peer-local: `test_in_process_and_http_plan_tokens_differ_for_the_same_single_entity_batch` (`MitateDB-api/tests/test_dry_run_and_plan.py`、`sessions` と `app_a_stack` の両 fixture) | 現行コードで「不一致」が実測されれば行 4 の見込みが事実に昇格する。一致したら本書の行 4 を訂正する |
| E-6 | 変異 M-1 (現状の非対称を赤で示す): `cell.py:1204` の `if digest_extra:` を `if False:` に変える | `tools/dev/mutate.py` spec `{"id": "M1", "file": "MitateDB-api/src/mitatedb_api/cell.py", "old": "                    if digest_extra:\n                        digest_request.update(digest_extra)\n                    if idempotency_key is not None:\n                        digest_request[\"idempotency_key\"] = idempotency_key\n                idempotency_response_digest = None\n                idempotency_now_ms = None\n                if idempotency_key is not None and not dry_run:\n                    # Phase 9 WP-3c (design D-5, I-3/I-7): checked here --", "new": (同文で `if digest_extra:` → `if False:`), "tests": ["MitateDB-api/tests/test_http.py::test_http_create_entity_plan_digest_commits_to_destructive"], "expect": "red"}` (`old` は 3 操作に同じ 2 行があるので、`create_collection` 固有の後続行まで含めて一意にする) | red。E-2 が非空であることの証拠 |
| E-7 | 変異 M-2: `http.py:1059` のタプルから `"destructive"` を落とす | `{"id": "M2", "file": "MitateDB-api/src/mitatedb_api/http.py", "old": "(\"destructive\", \"confirmation\", \"revision\", \"index\", \"unique\", \"budget\")", "new": "(\"confirmation\", \"revision\", \"index\", \"unique\", \"budget\")", "tests": [E-2 のテスト], "expect": "red"}` | red |

E-1〜E-5 は現行コードに対する特性化、E-6 / E-7 はそのテストの非空性の確認であり、いずれも選択肢の裁定前に作業機で回せる。

## 5. 選択肢の帰結 (どちらにも寄せない)

### (a) 死んだ引数を除く

| 観点 | 帰結 |
|---|---|
| 触るファイル | `MitateDB-api/src/mitatedb_api/cell.py:990` (署名から `destructive=False` を除く。docstring `:994-` に `destructive` の記述は無い)。呼び出し元の変更は不要 (§2.2、4 位置引数の呼び出し 0 件)。`MitateDB-api/tests/test_conformance_public_surface_coverage.py` が pin するのは `ApplicationRuntime` / `ApplicationDeveloper` のメソッド集合であり、`ApplicationCell` の署名ではないので影響しない (読解。未実行) |
| 変更クラス | **B** (挙動不変。digest の材料・記録形式・再送の意味に触れない) |
| 既存の記録済み digest との互換 | 変わらない (どの経路の digest も 1 byte も変わらない) |
| 一般則への答え | 「in-process から `destructive` を表現する経路は無い」という現状を署名で正直にする。HTTP だけが運べる 5 キー (`confirmation` / `revision` / `index` / `unique` / `destructive`) の扱いは行 1 の他 4 キーと同じになる (非対称が「死んだ引数」から「引数が無い」へ揃う) |
| 必要なテスト | 署名 pin: `test_create_collection_has_no_destructive_parameter` (`inspect.signature(ApplicationCell.create_collection).parameters` に `destructive` が無い)。E-1 は不要になる (引数が無いので 4 位置引数は `TypeError`) |
| 変異の案 | M-a1: `cell.py:990` に `destructive=False` を戻す → 署名 pin が red。M-a2: 4 位置引数の呼び出しを 1 つテストに足す (`cell.create_collection(dev, "t", {...}, True)`) → `TypeError` で red (非空性) |
| 残るもの | 行 4 (`transact` の再構築) はこの選択肢の範囲外。別途、台帳で扱うか R-33 の閉止註に「同種・既知・開示済み」として残すかは監督の裁定 |

### (b) cell 自身の digest に畳み込む

| 観点 | 帰結 |
|---|---|
| 触るファイル | `cell.py:1186-1207` (`destructive` を `digest_request` に入れる条件と位置。`budget` と同じく `digest_extra` の `update` の**前**に置けば HTTP 経路は同じ値で上書きされる)。`cell.py:3809-3811` / `:3814-3838` (`ApplicationDeveloper.create_collection` / `create_entity` に `destructive` を通す。通さなければ in-process の公開入口からは依然表現できず、畳み込みは `ApplicationCell` 直呼びにだけ効く)。整合のため `add_field` / `alter_field` (`:1369`、`:1606`) にも同じ引数を足すかは別の裁定 (足さなければ 3 操作の形が揃わない)。`MitateDB-api/conformance/conformance_adapter_mitatedb.py:1731-1741` (plug が `destructive` を kwargs に詰めるか) |
| 「省略」と「明示 False」の区別 | 契約の「省略された optional は key ごと無し」(`http.py:1052-1057` の G-1、`cell.py:236-243` の H-2) を in-process でも守るには、既定値 `False` では区別できない。既定を `None` にして `is not None` で畳む (`budget` と同型) か、`if destructive:` で `True` のときだけ畳むか。後者は HTTP の `destructive: false` 明示 (E-3) と in-process の明示 `False` で digest が食い違う新しい非対称を作る |
| 変更クラス | **C 以上**。in-process 経路の digest の材料が変わる (= 再送一致・plan 一致の意味に触れる)。`digest_extra` を残して cell 側を足すだけなら HTTP 経路の byte は変わらない (C)。`digest_extra` から `destructive` を外して cell 引数に一本化する形にすると、HTTP の `destructive: false` 明示 body の digest が変わり得る (上の区別の裁定次第) — 記録形式の意味に触れるので **D 相当の裁定** が要る |
| 既存の記録済み digest との互換 | cell 側に足すだけ: 既存の HTTP 由来の記録は不変 (`digest_extra` が同じ値で上書き)。in-process 由来の記録は `destructive` を渡した呼び出しが 0 件なので不変。`digest_extra` から外す形: `destructive: false` を明示して記録された key は `idempotency_retention_ms` 内の再送が `CONFLICT` に、その dry_run の plan は `PRECONDITION_FAILED` になり得る (plan は revision にも依存するので実害は小さいが 0 ではない) |
| spec との関係 | spec `:848` / `:851` は「要求オブジェクトの全フィールド」と言うだけで、in-process の引数が digest に入るべきかは言わない。(b) は「in-process の引数も契約上の要求フィールドの表現である」と読む立場であり、その読みを R-32 の同型性 pin (`normalize_request_for_plan` の同型) の外で peer ごとに実現する形になる。r2db は要求 dict そのものを材料にするので (b) に相当する変更は不要 (§2.3) |
| 必要なテスト | E-1 を反転した `test_create_collection_destructive_argument_reaches_the_plan_digest` (`True` と省略で token が違う)、`..._reaches_the_idempotency_digest` (`True` と省略で `CONFLICT`)、E-3 (HTTP の明示 False と省略の区別が壊れていない)、`ApplicationDeveloper` 経由の同型テスト (入口に通すなら)。既存 `test_http.py:1454` / `:1540` の budget のテストに倣う |
| 変異の案 | M-b1: 畳み込みの行を削る → 反転 E-1 が red。M-b2: `if destructive is not None` を `if destructive:` に変える (既定 `None` を採る場合) → 明示 False の区別テストが red。M-b3: `digest_extra` の `update` を畳み込みの**前**に動かす → HTTP で `destructive` の値が cell 引数に負ける形になり、E-2 または E-3 が red (順序の非空性) |
| 残るもの | 行 4 は同じく範囲外。`confirmation` / `revision` / `index` / `unique` を同じ扱いにするかは (b) を広げる裁定であり、本書は求めない |

### 共通の注意

- `MitateDB-api/tests/test_audit_query.py` の走査器 (P4-D16 v3) は `operation=` キーワードと `{"operation": ...}` dict の値の形を pin する (`cell.py:1455-1459` のコメント、`test_audit_query.py:1337-1343`)。`destructive` キーの追加・削除はこの走査の対象外と読むが、未実行。
- 本環境では両 peer の suite を回していないので、上の「影響しない」「不変」はいずれも読解であり、作業機の完了ゲートで確かめる。

## 6. 確認していない観点

1. `confirmation` / `revision` / `index` / `unique` を `create_entity` / `add_field` / `alter_field` の body に付けたときの挙動 (E-4 の見込み: 受理して無視し、digest にだけ入る)。spec の `SchemaOperationRequest` が操作ごとの絞り込みを持たないので shape では通る。これが「受理した要求を honor しない」(`http.py:1063-1070` の M-3 が `field_type` について拒否した同じ形) に当たるかは R-33 の外であり、本書は起票を求めない。
2. 行 4 (`transact` の再構築) の実測 (E-5)。コードの docstring の開示を事実として引用したが、token の不一致そのものは本環境で測っていない。
3. `security/SECURITY_INVARIANTS_V1.md` と `security/CONTROL_MAPPING.md` に digest / idempotency / plan の言及が無いことは explorer の grep によるもので、監督は両ファイルを直読していない。
4. 選択肢 (a) で `inspect.signature` を pin する既存テストが `ApplicationCell.create_collection` に無いことは grep (`signature|inspect|getsource` × `create_collection`) によるもので、AST pin の全数は見ていない。
5. 作業機の記録済み idempotency 記録 (`idempotency_record` テーブル) に `destructive` を含む digest が実在するかは見ていない (本環境に DB が無い)。(b) の互換の議論は構造からの導出である。
