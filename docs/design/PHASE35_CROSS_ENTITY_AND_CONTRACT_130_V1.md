# フェーズ3.5 実施設計: cross_entity_mutation + 契約 1.3.0 additive 束

- 版数: v1.2 (2026-08-31。v1.1 = WP-0 独立レビュー全数裁定。v1.2 = WP-1 レビュー m-3 の WP-6 スコープ拡張 + WP-2 レビュー裁定反映: R-5 status=partial への訂正・PG 留意の過大主張訂正・台帳追記。§9 参照)
- 位置づけ: `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` §5 D-L の実施設計。**依頼者直接承認 (2026-08-31)**: フェーズ3.5 着手、契約版数は additive 候補束4件 (`docs/design/DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(e)) と**一括で 1.3.0**。クライアント側正式回答 (Mitate repo `docs/work-orders/mitate-application-data-service-client-phase-b-requirements.md` v1.2 §6、v1.3 差分報告 2026-08-31 受領) をスコープ下限とする
- 体制: Fable 監督/設計/コミット、Sonnet 実装 (コミットしない)、Opus 独立レビュー (各 WP)。完了条件・単一コミット規律・identity 確認はフェーズ3 §3 と同一

## 0. スコープと原則

**入るもの**: (i) MitateDB-api の `cross_entity_mutation` 実装と宣言 flip (両 adapter)、(ii) 契約 1.3.0 (additive のみ、下記 §1)、(iii) 共通 suite の C-16 executable 化 + C-11/C-12 の cross-entity 拡張、(iv) 束4件の両 peer 制御面実装、(v) L4 (r2db `request_bytes` control discovery 宣言 flip — 契約変更なし、`DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(d) の再繰延分)。

**入らないもの**: r2db-api の `cross_entity_mutation` (unavailable 継続 — クライアント実需要は MitateDB 側のみ。P35-D1)、upsert / read-your-writes / preconditions / 実行順序観測 / 新エラー語彙 (クライアント回答でスコープ外確定)、idempotency の有効化、`audit` role の in-band 発行 (§9 B-2 裁定で台帳へ)、drop_index C-06 v2 (§8.1(a) は C-06 に触れる WP 待ちのまま)、application-plane 耐久 audit sink (フェーズ4)。

**契約の現状 (WP-0 実測、独立レビュー n-2 で全項再確認済み)**: `cross_entity_mutate` 操作 (`POST /v1/data/mutations`、request `ScopedMutationRequest`、response `MutationResult`)、`ScopedMutation` (= `Mutation` + 必須 `entity`)、`cross_entity_mutation` capability、`batch_entities` limit class は **1.1.0 (CCR-15) から既定義**。wire 形状の新設は不要 — mitate-30 の想定 (ScopedMutationRequest で足りる) は正しい。1.3.0 の cross-entity 分は意味論の明確化のみ (§1-A)。

**実装の現状 (WP-0 独立レビュー B-4 の実測発見)**: MitateDB の `transact()` は operation ごとに `collection` を読み、同一 collection 制約を持たない — **in-process 面では複数 entity の原子バッチが現に実行され、rollback も全無効で働く** (レビュー実測)。HTTP 面のみ URL entity への固定がある。つまり `cross_entity_mutation: unavailable` の宣言は in-process 合成の実挙動に対して既に偽であり、WP-2 の実質は「実行経路の新設」ではなく**「検証先行への並べ替え + `batch_entities` 束縛 + HTTP 実体化 + 宣言の真実化」**である。この偽宣言期間を延ばさないため、共通 suite より先に MitateDB の真実化を行う (WP 順序の根拠、P35-D11)。

## 1. 契約 1.3.0 変更一覧 (WP-1 単一コミット、すべて additive)

**A. cross_entity 意味論の明確化** (`endpoints.cross_entity_mutate.semantics` への追記):
1. `batch_entities` は operations[] が参照する **distinct entity 名の数**を束縛する。同一 entity の複数 operation は許容され、operation 総数は `batch_items` が束縛する (P35-D2)。
2. 各 `ScopedMutation` の per-operation 意味論 (mutation_class・upsert `unique_key`・`expected_revision`・destructive confirmation) は per-entity `Mutation` と同一である旨の明示的相互参照 (destructive_confirmation.applies_to は既に `ScopedMutation.operation == "delete"` を明記済み — 残りを揃える)。

**B. `CredentialsResult.credentials[].must_rotate`** (束1): 閉鎖 schema に **optional** boolean を追加。意味 = 「儀式未完遂 (rotate 前) の credential」。application credential 行では省略可 (概念が存在しない)。閉鎖 schema への optional 追加は `versioning.compatibility` の additive 規則どおり minor 適合。再検討条件: application credential 側に同種の儀式が導入されたら省略規則を再訪。

**C. `audit.fields` へ `target_id` 追加** (束2): 追加とあわせて**任意性を契約本文に明記する** (レビュー M-4): `target_id` は「イベントが単一の対象 credential/application を持つときに設定される optional フィールド」であり、全 event への必須列ではない。`audit.fields` は additive 語彙であって固定列集合ではないことも同文で明確化する — 両 peer が正準列集合として読んでいる現状 (等値テスト・INSERT 列) との整合は §5 WP-1 の B-1 措置で保つ。`forbidden_fields` とは非衝突 (識別子であり秘密でない)。再検討条件: 複数対象イベントが必要になったら配列化を別途裁定。

**D. `audit` role の実効化 — 読み取り権限の付与のみ** (束3、レビュー B-2 裁定で in-band 発行を撤回): `security.roles` / `CapabilityDocument.role` / `CredentialsResult.role` には既に `audit` が先行配置済み (WP-0 実測)。1.3.0 で行うのは: control endpoint のうち**読み取り専用列挙** (`control_capabilities` / `list_applications` / `list_credentials`) の auth を `"control"` → `"control or audit"` へ改め、`control_plane.issuance` に「`audit` credential も `control` と同じく帯域外儀式でのみ発行される」旨を追記する。**`CredentialIssueRequest` / `CredentialIssued` の enum は触らない** — in-band 発行は行わず、従属判断1 (帯域外限定、案B) の裁定はそのまま保持される (転換なし)。他の全 control endpoint は `audit` role に対し fail-closed (SI-15)。趣旨 = R-11「配れる弱い credential を用意し、root (`role=control`) を配る動機を消す」— 読み取りだけで趣旨は満たされる。再検討条件: audit role の書込系需要が実証されたら in-band 発行と併せ別 additive 裁定 (§7 台帳)。

**E. per-application 発行凍結の意味論注記** (束4): `control_endpoints.issue_credential.semantics` へ1文追加 — 「配備は application 単位で発行を凍結でき (out-of-band 操作)、凍結中の application への発行要求は **`FORBIDDEN`** で拒否される」。エラーコードは既存語彙から確定 (レビュー M-8: 既存の application-disabled 拒否経路は存在しない — 両 peer とも disabled app への発行は意図的に許可 — ため揃える先は無く、設計段階で確定する。`FORBIDDEN` = 認証済み actor への政策拒否、`CONFLICT` (状態競合) は登録二状態系と紛れるため不採用)。凍結トグル自体は CLI 限定 (公開 API に凍結操作の endpoint は追加しない、P35-D6)。再検討条件: in-band 凍結操作の需要 (§7 台帳)。

**F. `capability_status.defined.atomic_mutation` の文言明確化** (`DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(b) の解消): `operations` は「バッチ実行面が実行する mutation 語彙」であることを明記。両 peer とも**フェーズ3の** WP-1.5 収束後は両解釈が一致している (レビュー n-1 実測確認) ため実装影響ゼロの純明確化。

**G. 版数・記録**:
- `contract_version` 1.2.0→1.3.0。**両 peer の宣言 flip はここでは行わない** — 実装側の `contract_version` ハードコード 4 箇所 (r2db `service.py` / `control_plane.py`、MitateDB `cell.py` / `control_plane.py`) とそのテスト固定 2 箇所は、当該 peer が 1.3.0 挙動を出荷する WP (r2db = WP-4、MitateDB = WP-5) の同一コミットで flip する (レビュー B-3。契約 `versioning.version_binding` の「宣言は挙動と同一コミット」規律)。過渡期に peer が 1.2.0 を宣言し続けるのは正しい lag であり非適合ではない (1.3.0 挙動を出荷していないため)。
- `spec/CCR_DISPOSITION.md` 従属判断 **8** として本束の裁定を house style で記録。**A〜F の letter ごとに再検討条件を付す** (レビュー指摘 — 束一括で1つではない)。従属判断3 (batch_entities 参照 profile 4) の**再検討トリガー発火と解決**を項目8 に記録し、**項目3 側にも相互参照を追記**する: 実クライアント (mitate-application) が 10 を実証要求 → 解決は「MitateDB 配備宣言 10」で満たし、参照 profile (`limits.example_profile.batch_entities: 4`) は**不変** (profile は非規範の参照例であり、宣言は元々 deployment-declared。P35-D2)。従属判断1 は転換しない (D 裁定) ことを明記。
- r2db packaged copy (`r2db-api/src/r2db_api/contract/`) をバイト同期 (`test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` が固定)。
- **positive control テスト** (レビュー m-1 訂正): additive 束では「旧形状が新契約で不適合」は構成不能 (受理集合は広がるだけ)。構成するのは逆向き — `must_rotate` を持つ `CredentialsResult` が **1.2.0 schema では不適合・1.3.0 で適合**になることの実測固定。
- **B-1 措置 (単一 peer コミット規律の明示的例外、テストのみ)**: MitateDB の `CONTROL_AUDIT_FIELDS` 契約突合テストは len==12 + set 等値で固定されており、契約への `target_id` 追加だけで赤化する。WP-1 で当該テストを「12 コア ⊆ CONTROL_AUDIT_FIELDS ⊆ 契約 fields」の包含形へ緩め (挙動変更なし・テストのみ)、WP-5 で 13 フィールド等値へ復元する。r2db 側の同型ハードコード (INSERT 列 tuple) は契約突合テストが無く赤化しない — WP-4 で列追加と同時に更新。

**契約に足さないもの (台帳へ、§7)**: `idempotency_key` の重複排除名前空間 (per-entity endpoint と cross-entity endpoint の衝突有無) は両 peer とも idempotency unavailable の現在は観測不能 — idempotency 初有効化の WP で規定する (P35-D4)。per-operation 結果配列 (atomic-only では契約が per-item outcome を禁じており不要)。

## 2. MitateDB-api cross_entity 実装 (WP-2 — 共通 suite より先。§0「実装の現状」参照)

- **R-1 二段パス化**: `transact()` を「全 operation 全 entity の検証パス (fully-bound な実行計画リストを構築、副作用なし — `field_domains`/`encode_value`/`_bind_filters`/`_validate_update`/`_validate_delete_confirmation` はすべて読み取りのみ) → 実行パス」へ再構成。単一 entity 経路も同じ choke を通るため二段化される。**外部観測への影響 (レビュー M-7 の訂正)**: 原子的全無効は不変だが、「先行 op が実行時に失敗 + 後続 op が検証で失敗」する混在バッチでは返却エラーが実行時エラー→検証エラーへ変わる (検証先行は契約 `transactions.cross_entity` の要求どおりの優先順位変更)。**影響を受ける既存テストの列挙を WP-2 成果物に含める** (P35-D9 改)。二段パスの構造自体はローカルテストで固定 (黒箱では観測不能 — P35-D10 受理境界)。
- **R-2 `batch_entities`**: `FoundationConfig.max_batch_entities` (既定 **10** = クライアント要求値) + env var。検証パス冒頭で distinct collection 数を数え、超過は `ResourceLimitError(limit_class="batch_entities")`。`capabilities().limits/limit_enforcement` に `batch_entities: enforced` を追加。`test_limit_class_vocabulary.py` の AST 期待件数を同一コミット更新 (完了条件 2b)。
- **R-3 HTTP**: `post_cross_entity_mutate` の CapabilityError raise を実体化 — `_check_object_shape(body, _SCHEMAS["ScopedMutationRequest"])` (読み込み済み・未使用の契約 schema をそのまま使用)、各 operation を `_DEFINITIONS["ScopedMutation"]` で shape 検証し per-op `entity` を collection として cell へ。`idempotency_key` は per-entity 経路と同一の CapabilityError (P35-D3)。**応答は per-entity 経路と同一の `{"committed","affected"}` のみ — `assigned_addresses` は返さない** (レビュー M-6: 当 peer は `row_addressability`/`application_catalog` unavailable であり address キー語彙を宣言できる立場に無い。これはスコープ下限の「実行順序観測は不要」とも整合 — `assigned_identifiers` の "one element per insert in operation order" は順序観測面である)。
- **R-4 delete choke**: `_validate_delete_confirmation` は既に entity 込み句 (`DELETE <collection> @where= @schema_revision=`) の単一 choke であり変更不要。複数 entity の delete は entity ごとに別句。確認不一致の denial は first-mismatch-wins (契約 details_rules が明示的に許容)。
- **R-5 拒否面**: `ScopedMutation.operation == "upsert"` は CapabilityError (per-entity と同一)。`expected_revision` 等の未対応キーは既存 `_TRANSACT_*_KEYS` 余剰キー拒否で CapabilityError (スコープ下限どおり)。宣言 flip (`cross_entity_mutation: {"status": "partial", "operations": ["insert","update","delete"], "unsupported": ["upsert"]}` — **WP-2 レビュー M-1 裁定: atomic_mutation と status も含め完全対称**。v1.1 の「"enabled"」記載は同レビューが指摘した本設計自身の自己矛盾であり、同一 peer の同一語彙・同一拒否には同一 status を宣言する) は実装・テストと単一コミット — これにより §0 の偽宣言状態が解消される。WP-3 の C-16/C-12 availability 判定は `status in ("enabled", "partial")` を provided と扱うこと。
- **R-6 監査**: バッチ内 delete の commit 後発火 (`pending_audit`) 規律を cross-entity にそのまま延長。insert/update の非監査はフェーズ4 (耐久 sink) の既知ギャップのまま — 本フェーズで偽の被覆を作らない。クライアントの「1 状態変更 = 1 audit event」要求は**クライアント自身の audit entity への同一原子単位書込**で満たされる設計であり (本体 entity + audit entity の 2 entity atomic write)、サーバ側 audit sink には依存しない。
- **PG 留意 (v1.2 訂正 — WP-2 レビュー m-6)**: カタログ読取 (`field_domains`/`schema_revision`) は developer 接続で DML tx 外 — 既存 transact と同一の前提であり新規リスクではない。検証パス (pass 1) と実行パス (pass 2) の間に schema 変更が挟まる窓について、v1.1 の「delete 句の `@schema_revision` 指紋が既に閉じている」は過大主張だった: 指紋は pass 1 でのみ検査され pass 2 で再検査されない。実際に安全を保つのは (a) 当 peer の schema 変更は `create_entity`/`add_field` のみで、束縛済み WHERE の一致集合を変えられないこと、(b) pass 2 の PG/SQLite エラーが rollback で全無効になること (WP-2 レビュー B-2 修正後は例外種別によらず無条件)。また二段化により pass 1 は `self._lock` の外で走る (従来は op ごとの検証+実行が単一ロック保持内) — in-process の検証/実行間窓がゼロから「pass 1 残り + ロック取得」へ広がったが、`insert()`/`read()` と同じ形であり帰結は上記 (a)(b) が押さえる。実測固定: begin を wrap して pass 1/pass 2 境界で DROP TABLE を挟む PG テスト (レビュー M-3)。

## 3. 共通 suite (WP-3 — MitateDB flip 後。C-16 の PROVIDED 分岐は本 WP で全 adapter 一斉に初実行される)

- **port v1.7**: `attempt_cross_entity_batch(session, operations: Sequence[ScopedBatchOperation]) -> ...` 新設 (`ScopedBatchOperation` = 既存 `BatchOperation` + entity)。availability は capability_document の `cross_entity_mutation.status` で判定。probe→echo は既存 C-06 機構を再利用。**両 peer ツリー内の adapter 4 ファイルの編集を伴う** (レビュー m-7 — フェーズ3 WP-2.5 と同型のコミット形として明記)。
- **C-16 vectors** (`test_c16_cross_entity_atomicity.py` 新設): V1 正常系 (2 entity insert が単一 unit で両方 commit)、V2 原子性 (先行 entity の有効 op + 後続 entity の無効 op → denial + **両 entity とも無変化**)、V3 `batch_entities` 境界 — **構成可能条件付き** (レビュー m-3): 宣言 `batch_entities < min(100, batch_items)` のときのみ L+1 distinct entity ベクタを構成し (`LIMIT_EXCEEDED`/`limit_class=batch_entities`)、然らざれば skip 理由を明示 (C-14 vector 5 の前提 assertion と同型)。宣言値は数値ハードコードせず capability document から読む (§8 リスク5)。有限 discoverable 性 (limits に batch_entities が載る) は無条件に検査。V4 batch 内 delete の declare-and-echo (entity ごとの句、他 entity の句の流用拒否)、V5 unavailable peer の拒否 — **evidence 形態は adapter 形式で分岐** (レビュー M-5 訂正): HTTP adapter (r2db-http) = 実 mount の present-denial (auth 後 `CAPABILITY_UNSUPPORTED`)、in-process adapter (r2db) = **SurfaceAbsent** (`DataService` に cross-entity 入口が無い — C-17 の in-process/http evidence 形態差の前例と同型)。MitateDB 2 adapter は本 WP 時点で既に enabled のため PROVIDED 分岐 (V1〜V4) を走る。
- **C-12 拡張**: `cross_entity_mutation` の宣言↔実挙動の双方向一致 — 現行 C-12 は cross_entity を一切読まない (WP-0 実測) ため新規ベクタ。enabled 方向 (宣言 operations が実行可能) は全宣言 peer、unavailable 方向 (拒否) は **wire 面を持つ adapter (HTTP) に限定** (in-process の unavailable 面は port 定義依存で form-(b) と同クラスの検証限界 — 受理境界として CONDITIONS.md に開示。なお本フェーズの WP 順序では MitateDB は本 WP 時点で enabled であり、当該限定が実際に効くのは r2db in-process のみ)。
- **C-11 拡張**: `raw_cross_entity_mutation_result` accessor (optional) で実 endpoint の `MutationResult` を逆向き schema 検証 (現行 C-11 は per-entity 経路のみ)。
- **CONDITIONS.md**: C-16 行を executable へ書き換え (V5 の evidence 形態差と V3 の構成可能条件を含めて開示)。

## 4. 制御面束実装 (WP-4 = r2db、WP-5 = MitateDB。各単一 peer コミット、**当該 peer の `contract_version` 1.3.0 flip + 版数テスト固定更新を同一コミットに含める** — レビュー B-3)

- **must_rotate 露出**: `list_credentials` 行に実値を追加 (両 peer とも `control_credentials.must_rotate` 列は既存)。application credential 行は省略。C-11 live 検証は WP-1 の契約 optional 化が先行するため常に緑 (順序保証 — レビューが load-bearing を実測確認)。**帰結の明記 (レビュー m-4)**: §1-D により `list_credentials` は audit role からも読めるため、より弱い credential から儀式未完遂 credential が列挙可能になる。秘密は含まれず (契約 "Never returns secrets or verifiers")、これは意図された運用可視性 — CONTROL_MAPPING SI-10/SI-02 行に意図として記録する。
- **target_id**: `AuditEvent`/`CONTROL_AUDIT_FIELDS` へ 13 番目のフィールド追加 + `control_audit` テーブル列追加 (**nullable** — §1-C の optional 意味論どおり)。migration は **in-place 改訂** (配備実機ゼロ + 全テストが migrations を毎回再実行 — フェーズ3 WP-4 の `control_credentials.revoked` 前例を踏襲し、CONTROL_MAPPING に記録。P35-D5)。credential lifecycle イベントに対象 credential_id を設定。r2db は INSERT 列 tuple (`_CONTROL_AUDIT_COLUMNS`) も同時更新 (B-1 参照)。MitateDB は WP-1 で緩めた契約突合テストを 13 フィールド等値へ復元。`ops.py audit-report` の「target_id 無し」注記を解消。
- **audit role**: `control_credentials` へ `role` 列追加 (`CHECK (role IN ('control','audit'))`、既存行 default 'control'、in-place)。**発行は帯域外 CLI 儀式のみ** (B-2 裁定 — in-band 発行なし、enum も不変。issue 系 CLI に role 指定を追加し、儀式 (issue→rotate) は control と同一の流れで must_rotate を消し込んでから配布する — これによりレビュー M-1 の袋小路は生じない: 配布時点で must_rotate=false。**in-band で must_rotate=true の audit credential が観測された場合の gate は control と同一の allow-list (`control_capabilities` のみ)** とし、self-rotate は加えない — 儀式完遂は CLI の責務)。認可: 読み取り専用 3 endpoint のみ許可、他は fail-closed 拒否 (`FORBIDDEN`、監査対象)。`list_credentials` の role ハードコード ('control') を列読み取りへ。**discovery の `role` ハードコードと拒否監査行の `role="control"` ハードコードも実 role 読み取りへ** (レビュー m-6)。**共通 suite の audit-role fail-closed ベクタは台帳へ** (C-14 v2 候補) — 本フェーズはローカルテスト両 peer で固定 (P35-D5、書込 endpoint 全数列挙の fail-closed テストを完了条件に含める)。
- **発行凍結**: `applications` へ `issuance_frozen boolean NOT NULL DEFAULT false` (in-place)。CLI `freeze-issuance`/`unfreeze-issuance` (非破壊 — disable-app と同格で declare-and-echo 不要、P35-D6)。`issue_credential` は凍結時 `FORBIDDEN` で fail-closed 拒否 + 監査 (§1-E で契約側も同コードを明記 — レビュー M-8 裁定)。in-band の凍結操作 endpoint は作らない。
- **L4 (r2db のみ、WP-4 同乗)**: `ControlPlaneLimits` へ `request_bytes` 追加し、**ソースを一本化** (control_http の `_BYTE_BOUND_LIMITS` は新設フィールドを読む — 現行値 `ResourceLimits().request_bytes` を既定値として引き継ぐ)。**enforcement 宣言は MitateDB と対称の二層形** (レビュー M-3): service 層既定は `"unavailable"` (service 単体は HTTP バイト境界を強制できない)、HTTP mount 側で `"enforced"` に上書き。**r2db ローカルの完全一致固定 2 箇所 (`test_control_http.py` の limits キー集合等値・`test_control_plane_service.py` の辞書等値) を同一コミット更新** (レビュー M-2)。MitateDB は最初から宣言済み (対称性回復)。共通 C-14 vector 5 は 3 クラスの in-検査のみで閉鎖検査なし (WP-0 実測) — 共通側の破壊なし。

## 5. WP 分割

| WP | 内容 | 公開面への影響 |
|---|---|---|
| WP-0 | 本設計の独立レビュー (blocker/major 全消化で確定)。確定後 mitate-30 へ wire 形状一報 (ScopedMutationRequest 現行形で確定、契約変更は意味論明確化のみ。応答は `{"committed","affected"}` のみで assigned_addresses 無し) | なし |
| WP-1 | 契約 1.3.0 単一コミット (§1 A〜G + packaged copy 同期 + positive control + CCR_DISPOSITION 従属判断8 + **B-1 措置: MitateDB 契約突合テストの包含形緩和 — テストのみの明示的例外**)。peer の版数宣言 flip は含まない (B-3) | あり (契約公開) |
| WP-2 | MitateDB cross_entity 単一コミット: 二段パス transact + batch_entities + HTTP 実体化 + 宣言 flip 両 adapter (§0 偽宣言の解消) + エラー優先順位変更の影響テスト列挙 (M-7)。完了証拠はローカルテスト (フェーズ3 WP-1 add_field の前例: 共通 suite 被覆は次 WP) | あり (capability flip) |
| WP-3 | 共通 suite: port v1.7 + C-16 新設 + C-12/C-11 拡張 + CONDITIONS.md + adapter 4 ファイル (m-7)。**C-16 PROVIDED 分岐の初実行は本 WP** (MitateDB 2 adapter)。既存 executable 全条件が 4 adapter で緑 | なし (検証範囲拡大のみ) |
| WP-4 | r2db 制御面束 + L4 + **`contract_version` 1.3.0 flip**: must_rotate 露出・target_id・audit role・発行凍結・request_bytes 宣言・ローカル固定更新 (M-2) | あり (制御面拡張 + 版数宣言) |
| WP-5 | MitateDB 制御面束 + **`contract_version` 1.3.0 flip**: 同4件 + B-1 テスト復元 (13 フィールド等値) | あり (制御面拡張 + 版数宣言) |
| WP-6 | 記録整理: CONTROL_MAPPING (SI-08/SI-11/SI-14/SI-06/SI-07 に加え **SI-02/SI-15/SI-10** — レビュー m-5)・CONDITIONS・README・引き継ぎ・完了報告。**WP-1 独立レビュー m-3 の追加スコープ**: 契約 1.3.0 の `target_id` 追加で「12 フィールド」という記述が字面どおりでは古くなった prose 箇所を record-consolidation の対象に含める — `security/CONTROL_MAPPING.md` の「contract-vocabulary gap」該当行 (SI-14 行の r2db/MitateDB 両列、`target_id` 欠落を明記した箇所)、`r2db-api/docs/CONTROL_PLANE_COMPROMISE_PLAYBOOK.md` (`target_id` 欠落の記述)、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` (`control_audit` 列を「12 named columns」と記す箇所) の計5箇所が、この時点でなお「12 フィールド / target_id 欠落」を未解消のギャップとして記述しており、WP-4/WP-5 の実装反映後に一括更新する対象として WP-6 が引き継ぐ | なし |

完了条件 (全 WP 共通、フェーズ3 §3 継承): テスト追加 + 変異注入 (scratchpad 復元、`git checkout` 不使用)、root suite 完走 (現基準 1161 + 増分)、宣言語彙全数固定の維持 (limit_class AST 件数の同一コミット更新)、独立レビュー往復、commit/push/main merge (`--no-ff`) 1 セット + identity 確認。

## 6. 監督決定一覧 (依頼者が覆せる)

- **P35-D1**: r2db-api の cross_entity_mutation は unavailable 継続。実需要が生じたら別 WP (実装は本フェーズの C-16/port がそのまま受ける)
- **P35-D2**: batch_entities = distinct entity 数 (同一 entity 重複可)。MitateDB 宣言値 10。契約参照 profile 4 は不変 (従属判断3 トリガー発火の解決 = per-deployment 宣言)
- **P35-D3**: ScopedMutation の upsert / idempotency_key / 未対応キーは MitateDB では CapabilityError (per-entity 経路と同一規律)
- **P35-D4**: idempotency 名前空間は契約に規定しない (初有効化 WP へ台帳繰延)
- **P35-D5**: 束実装の migration は in-place 改訂 (配備実機ゼロの前例継続)。audit-role fail-closed の共通ベクタは台帳 (ローカル両 peer で固定)
- **P35-D6**: 発行凍結は CLI 限定・非破壊 (declare-and-echo 不要)。in-band 凍結 endpoint は作らない
- **P35-D7**: must_rotate は optional field。application credential 行では省略
- **P35-D8**: atomic_mutation 文言明確化を 1.3.0 同梱 (§8.1(b) 解消)
- **P35-D9 (v1.1 改)**: 二段パス化は単一 entity 経路にも及ぶ (choke 共有)。原子的全無効は不変だが、混在失敗バッチの返却エラーは検証エラー優先へ変わる — 契約要求どおりの優先順位変更として意図的に採る (M-7)
- **P35-D10 (受理境界)**: 「検証先行」の内部順序は黒箱観測不能 — 共通 suite は無部分効果で検証し、二段パス構造は MitateDB ローカルテストが固定する
- **P35-D11 (v1.1 新設)**: WP 順序は「実装真実化 (WP-2) → 共通 suite (WP-3)」— フェーズ3 の suite-first と逆だが、B-4 (in-process の偽 unavailable 宣言が現存) の是正期間を最短化するため。フェーズ3 WP-1 (add_field: 宣言+実装+ローカルテスト単一コミット、共通被覆は後続) の前例に整合
- **P35-D12 (v1.1 新設)**: audit role の発行は帯域外儀式のみ (B-2)。従属判断1 は転換しない。in-band 発行は台帳
- **P35-D13 (v1.1 新設)**: 発行凍結の拒否コードは `FORBIDDEN` (M-8。CONFLICT は登録二状態系と紛れるため不採用、新語彙はスコープ下限が禁止)
- **P35-D14 (v1.1 新設)**: B-1 措置 — WP-1 が MitateDB の契約突合テスト 1 本を包含形へ緩める (テストのみ・挙動不変の明示的例外)。WP-5 で等値へ復元

## 7. 将来課題台帳 (本フェーズ新設分)

- idempotency_key の重複排除名前空間 (per-entity ↔ cross-entity の衝突規定) — idempotency 初有効化 WP で契約規定 (P35-D4)
- audit role fail-closed の共通 conformance ベクタ (C-14 v2 候補) — 本フェーズはローカルテストのみ (P35-D5)
- **audit role の in-band 発行** (B-2 裁定で撤回した部分): 需要が実証されたら (a) `CredentialIssueRequest.application_id` の任意化 or 別 endpoint、(b) `control_plane.issuance` 改訂、(c) 従属判断1 の明示的転換、の3点セットで別 additive 裁定
- r2db cross_entity_mutation の実装採否 (実需要待ち、P35-D1)
- 発行凍結の in-band 化 — 現時点で需要なし
- in-process adapter の cross_entity unavailable 面の検証限界 (C-12 拡張の wire 限定、§3) — positive-existence check 台帳 (フェーズ3 §7) と同根
- MitateDB PG backend の `_check_domain` float 分岐: 巨大 int → `real` 列で `OverflowError` が未捕捉 (pass 1 で 503)。SQLite 側は M-7 で同型を閉塞済みだが PG 側は未対応 (WP-2 レビュー n-3 の発見、pre-existing)
- `ScopedMutation.entity` は attacker-controlled identifier position の新設だが C-03 の `MUST_COVER_IDENTIFIER_POSITIONS` に未列挙 — capability が executable になった今、injection 被覆の対象化を検討 (WP-3 レビュー n-4)
- r2db conformance-build の `applications` 上限は 115 (WP-3 で 100 から引き上げ)。天井は C-14 の算術で 122 — 次に逼迫したときの正解は再引き上げでなく fixture teardown (`deprovision_application`) の導入 (WP-3 レビュー m-6)
- 継承分: `DESTRUCTIVE_CONFIRMATION_V1.md` §8.1(a) drop_index C-06 v2 / (c) 受理境界一覧 / フェーズ4 耐久 audit sink / `MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` §7 全項

## 8. リスクとレビュー重点

1. 二段パス再構成の退行 — 既存テスト全緑 + M-7 の影響テスト列挙 + 変異で二段構造を固定
2. PG の検証/実行間の schema 変更窓 (§2 PG 留意) — 実 PG テストで drop→recreate 横断を実測
3. audit role の認可漏れ (書込 endpoint への到達) — fail-closed の全 endpoint 列挙テスト (両 peer)
4. 契約 schema/文言変更の取りこぼし — WP-1 完了条件で全数突合 (packaged copy・positive control・B-1 措置)。peer 版数 flip の取りこぼし — WP-4/5 完了条件 (B-3)
5. C-16 V3 の宣言値依存 — 数値ハードコード禁止 (capability document から読む)、構成可能条件ガード (m-3)
6. L4 の enforcement 二層形の取り違え (service 層 enforced と偽らない) — M-3 の対称形をテストで固定

## 9. 訂正記録 (WP-0 独立レビュー、v1.0 → v1.1)

blocker 4 / major 8 / minor 8 / nit 3 — 全数裁定。主要な裁定:

- **B-1** (契約 target_id 追加が WP-1 単独で MitateDB 契約突合テストを赤化) → §1-G B-1 措置 (包含形緩和 + WP-5 復元、P35-D14)
- **B-2** (in-band audit 発行は wire 形状・契約本文・従属判断1 と三重衝突) → 読み取り権限付与のみに縮小 (台帳 (e)3 の原文どおり)。enum 不変、発行は帯域外儀式。in-band 化は台帳へ (P35-D12)。これによりレビュー m-8 (過渡窓の VALIDATION_FAILED/CAPABILITY_UNSUPPORTED 不整合) は消滅
- **B-3** (peer の contract_version flip が設計に無い — version_binding 違反) → WP-4/WP-5 の同一コミットに flip + テスト固定更新 (§1-G/§4/§5)
- **B-4** (MitateDB in-process は既に cross-collection 原子バッチを実行 — unavailable 宣言が偽) → §0「実装の現状」新設、WP 順序を実装先行へ反転 (P35-D11)、C-12 unavailable 方向は wire 面限定 (§3)
- **M-1** (audit role × must_rotate の袋小路) → 儀式が配布前に must_rotate を消し込む。in-band gate は control_capabilities のみ (§4)
- **M-2/M-3** (L4 が r2db ローカル固定 2 箇所を壊す / enforced 偽宣言) → 同一コミット更新列挙 + MitateDB 対称の二層 enforcement (§4)
- **M-4** (audit.fields は開放語彙と固定列集合の二面性) → 契約本文で optional 意味論を明記 (§1-C)、nullable 列 (§4)
- **M-5** (r2db in-process は present-denial でなく SurfaceAbsent) → C-16 V5 の evidence 形態分岐 (§3)
- **M-6** (assigned_addresses は未宣言面の追加) → 返さない (§2 R-3)。n-3 (順序観測) も同時解消
- **M-7** (「外部挙動不変」は不正確 — エラー優先順位が変わる) → P35-D9 改訂 + 影響テスト列挙を WP-2 成果物へ
- **M-8** (揃える先の application-disabled 拒否経路は存在しない) → `FORBIDDEN` を設計段階で確定 (P35-D13、§1-E)
- **m-1** (逆向き検証は additive では構成不能) → positive control へ訂正 / **m-2** (test_contract に版数固定は無い) → B-3 の peer 側 2 箇所に訂正 / **m-3** (V3 は一般に構成不能) → 構成可能条件ガード / **m-4** (must_rotate の可視性拡大) → CONTROL_MAPPING に意図記録 / **m-5** (SI-02/SI-15/SI-10 欠落) → WP-6 列挙へ追加 / **m-6** (role ハードコード 3 箇所) → §4 作業項目 / **m-7** (port 拡張は peer ツリー 4 ファイル編集) → §3/§5 明記 / **m-8** → B-2 で消滅 / **n-1** (WP-1.5 の修飾) → 「フェーズ3の WP-1.5」 / **n-2** (契約現状の実測は全項正確) → 記録として保持 / **n-3** → M-6 で moot、スコープ整合を §2 R-3 に一文

## 10. WP 実装記録

### 10.1 WP-1 (契約 1.3.0)

独立レビュー 0 blocker / 3 major / 5 minor / 3 nit、全数裁定・反映。M-1 = `versioning.version_binding` へ 1.3.0 導入義務の列挙を追記 (audit role 受理 + FORBIDDEN fail-closed、凍結拒否、optional 2 フィールドの「emit したときの意味論」拘束)。M-2 = A/D/E/F への回帰ピン (auth 等値 4 本 + 文言 substring 4 本、`test_contract.py`)。M-3 = 凍結 FORBIDDEN は role=control capability 拒否の後に評価 (C-14 vector 3 の規範読みと整合)。m-1 (§1-D 列挙外の `control_plane.authority` 追記) は監督追認。root suite 1166 passed / 0 failed / 0 skipped。main マージ `e2093c5`。**1.3.0 は公開済み — 以後の契約変更は 1.4.0 以上。**

### 10.2 WP-2 (MitateDB cross_entity)

実装: 二段パス `transact()` (`_plan_operation` + 実行パス、`_*_in_transaction` 3 メソッドは統合)、`batch_entities` (config 既定 10、AST 件数 10→11)、HTTP 実体化 (`ScopedMutationRequest`/`ScopedMutation` shape 検証、`{"committed","affected"}` のみ)、宣言 flip。P35-D9 列挙: 既存 suite に「先行実行時失敗+後続検証失敗」の混在テストは存在せず (全既存 rollback テストは検証 choke で落ちる)、合成 ConflictError で優先順位変更を実測固定。

独立レビュー **2 blocker / 3 major / 6 minor / 3 nit**、全数裁定・反映:

- **B-2 (本 WP 最大の安全発見)**: pass-2 の except tuple が FoundationError 系に限定されており、孤立 UTF-16 サロゲート (`"\ud800"`、合法 JSON) がパラメータ適応の `UnicodeEncodeError` として素通り → **rollback 不発・先行 op の行が永続 (部分効果)** を両バックエンドで実測。pre-existing だが、`cross_entity_mutation` を宣言する本コミットが SI-11 主張を load-bearing にする。修正は二重: rollback の無条件化 (`except Exception` → rollback → 再送出) + `encode_value` の孤立サロゲート決定的拒否 (NUL 拒否と同前例、両バックエンド)。変異 3 本 (except 縮退・両バックエンドのサロゲート検査除去) 全赤化・復元確認
- **B-1**: 非文字列 entity が `_distinct_batch_entities` の set.add で TypeError → 503。isinstance ガードで VALIDATION_FAILED へ
- **M-1**: 宣言 status は `partial` (atomic_mutation と完全対称)。v1.1 設計の「enabled」は自己矛盾として v1.2 で訂正
- **M-2**: 「自然な実行時失敗は無い」という docstring 前提が偽 (サロゲートが該当) — B-2(ii) で検証時へ再分類したことを明記する形へ訂正
- **M-3**: pass 境界の schema 変更窓を begin wrap + DROP TABLE で実測固定 (NotFoundError + 兄弟 entity 無変化)
- m-4 = auth-before-parse のピン (不正 body + 未認証 → AUTH_REQUIRED)、m-5 = CONDITIONS.md C-16 行への 1 行注記 (監督許可の cross-tree 編集、全面書換は WP-3)、m-6 = §2 PG 留意の過大主張を v1.2 で訂正 (指紋は pass 1 のみ・安全は schema 変更の単調性と無条件 rollback が担う)、n-3 = PG `_check_domain` float の OverflowError を §7 台帳へ

発見一覧 (実装者): (1) 旧 insert 分岐の素 KeyError による begin 残骸リスクが二段化で構造的に不活性化 (pass 1 で begin 前に発火)、(2) README の unavailable 記述の陳腐化 → WP-6 へ、(3) HTTP fixture の request_bytes=1024 と境界テストの干渉を実測バイト数で回避。

### 10.3 WP-3 (共通 suite: port v1.7 + C-16)

実装: port v1.7 (`ScopedBatchOperation` + `attempt_cross_entity_batch` — 返値は実 affected 合計、availability = status ∈ {enabled, partial})、adapter 4 ファイル (MitateDB 2 = 実実行、r2db in-process = SurfaceAbsent、r2db http = 実 wire の present-denial)、`test_c16_cross_entity_atomicity.py` (V1〜V5 + vacuity guard 2 本)、C-12 双方向拡張 (負方向は wire 面限定)、C-11 `raw_cross_entity_mutation_result`、CONDITIONS.md C-16 行の executable 化。**C-16 PROVIDED 分岐の初実行は計画どおり本 WP** (MitateDB 2 adapter、V3 の構成可能条件は両者とも実成立 10 < 100)。

独立レビュー **0 blocker / 4 major / 6 minor / 4 nit**、全数裁定・反映:

- **M-2**: V4 の句導出検証は predicate 差で汚染されており entity 寄与を分離できていなかった → 同一 predicate 化。製品コード変異 (句から collection 除去) で赤化を実測してから確定
- **M-4**: V3 に位置算術の受理半面を追加 (宣言値ちょうどは batch_entities で拒否されない) — 宣言 10・実施 3 の peer が通過できた穴を閉塞。adapter 変異で赤化実測
- **M-1/m-6**: 実装者の applications 100→115 引き上げ (WP-3 自身の C-12 拡張 +2 が束縛イベント。C-16 消費は C-14/C-15 より後で無関係 — レビュアーが計測プラグインで実測) を維持しつつ、C-14 行の陳腐値を実測値 (vector-5 87/87/73/75、session-end 186/189/134/145、天井 122) へ更新。次の逼迫時の正解は fixture teardown (§7 台帳)
- **M-3**: C-12 負方向 2 分岐に状態無変化検証を追加
- m-1 = in-process 返値を実 affected 合計へ / m-3 = maxItems を load_contract() から読む / m-4 = SurfaceAbsent 検証に forbidden_vocabulary ピン / m-5 = enabled-無-operations の全語彙写像 / n-4 = `ScopedMutation.entity` の C-03 identifier position 未列挙を台帳へ

受理境界 (CONDITIONS.md 開示): V5 の form-(b) 捏造 (実 wire 要求を送らず CAPABILITY_UNSUPPORTED を偽装する adapter) は検出不能 — C-06/C-14/C-17 と同クラス、positive-existence check 台帳項目に合流。「検証先行」の黒箱観測は無部分効果のみ (P35-D10、二段パス構造は MitateDB ローカルテストが固定)。

conformance 364 passed / peer 861 passed (レビュアー・実装者の二重実測)。
