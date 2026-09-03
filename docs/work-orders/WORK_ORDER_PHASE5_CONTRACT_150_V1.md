# フェーズ5 作業指示書 — 契約 1.5.0 (監査語彙の宣言化 + 無条件義務 (b) の適用範囲) + request-count limit 受理レンジの対称化

- 版数: **v1.1 (2026-09-03、設計 v1.3 との同期 + 監督裁定 1 件を反映)** — 主要な変更: **D-2 テストの `CONDITIONS.md` 登録先を C-09 行に確定** (監督裁定。v1.0 は「監督確定待ち」として保留していた)、**除外リストの検証条件 (ii) を (ii′) へ差し替え** (設計 N-1 — 「監査 literal を運ぶ定義は除外できない構造」は r2db `DataService.schema` に反証された。v1.0 の当該記述と変異注入 7 を訂正)、**(b‴) の導入に製品変更は不要**と明記し「keyword passthrough が残っていれば dict literal 形へ書き換え」を削除 (設計 N-6、実測 0 件)、**D-2 英文を許容形へ** (設計 N-2 / N-3 — `forwarded` の禁止を作らず、義務 (5) と `deprecation_note` の host scoping を参照)、**従属判断 10 項目 2 の additive 根拠に alias 同一ハンドラの実測を要求** (設計 N-4)、**`event_class` 返却 vector は 1.4.0 条件付き = WP-1 から load-bearing** と統一 (設計 N-7、期待実測値表を更新)。v1.0 = 起草
- 正本設計: `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` (**v1.3、確定**)。**本書は WP 分割と発注のみを扱う** — 裁定の根拠・却下案・実装の具体形・契約英文の骨子は設計文書が正本であり、本書はそれを重複させない。設計と本書が食い違ったら**設計が正**であり、本書の誤りとして監督へ差し戻すこと
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260903_FABLE2.md` (第11次。フェーズ4 + 台帳消化 完了時点、root suite **1545 passed / 0 failed / 0 skipped / 0 xfailed**、conformance **404 passed**)
- 体制: Fable 監督/判断/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー/受け入れ監査
- 先行作業指示書: `docs/work-orders/PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md` (v1.2) / `docs/work-orders/WORK_ORDER_PHASE4_LEDGER_CLOSURE_V1.md` (v1.6)。完了ゲートの実測規律・禁止事項・コミット規律は本書 §6〜§8 が引き継ぐ

---

## 0. 問題設定

フェーズ4 の将来課題台帳 (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2) が「依頼者判断待ち」として集約した Q1〜Q5 のうち、**2026-09-03 に依頼者が裁定した Q1・Q2・Q3** を実施する。

| 台帳項目 | 内容 | 閉じ方 | WP |
|---|---|---|---|
| **L4-1** (Q1) | `operation` / `target_kind` が宣言語彙になっていない | **契約 1.5.0** の条件付き義務 + 共通宣言整合 vector + 両 peer の走査器一般化・宣言 2 キー | WP-1 / WP-2 / WP-3 |
| **L4-2** (Q2) | 契約 1.4.0 無条件義務 (b) の適用範囲が一意に読めない | **1.4.0 の同ラベル補筆** + port v1.9 + 共通無条件テスト | WP-1 |
| **L4-4 / L4-7(iii)** (Q3) | request-count limit の受理レンジが peer 非対称 | **案 A** — MitateDB の `[1, 200]` 上限撤廃 (**契約不変**) | WP-4 |

**契約は 1.4.0 → 1.5.0 へ上がる。** 1.4.0 は main へ merge 済み・公開済みであり、据え置きの余地は無い (設計 §2 の 1)。**契約ファイルを変更するコミット (WP-1) は依頼者確認後に実施する** (設計 §2 の 8 / §5)。

**Q4 (`visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合) は本フェーズに入らない** — 独立の設計フェーズとして残る (設計 §10)。

---

## 1. 本書が発注する確定事項 (設計 §3 の要約。根拠は設計が正本)

本節は**参照の便のための要約**である。各項の根拠・却下案・英文の骨子は設計 §3 / §4 / §5 を読むこと。

- **D-1 (Q1)**: `capabilities().audit_query` に **`operations`** / **`target_kinds`** の 2 キーを追加する。契約に enum は置かない (declare-the-hazard)。義務は**条件付き** — `audit_query` を `unavailable` 以外で宣言する 1.5.0 以上の実装は、返しうる全 event の `operation` / `target_kind` をそれぞれの宣言に含めなければならない。`capability_status.defined.atomic_mutation.operations` との**曖昧解消文は必須**である (設計 §3 D-1)。
- **D-2 (Q2)**: 1.4.0 無条件義務 (b) の適用範囲を、**1.4.0 の義務 (b) 本文そのものへの補筆 (同ラベル改訂)** として一意にする。「Since 1.5.0」の新義務としては置かない。**許容形**であり義務形にしない (`versioning.control_discovery` の co-hosting 容認を狭めない)。**`forwarded` の禁止も作らない** — 転送は 1.4.0 条件付き義務 (5) を分離配備で満たす自然な手段でありうるため、禁止すればその形の 1.4.0 実装が遡って非適合になる (設計 §3 D-2 の N-2)。
- **D-3 (Q3、案 A)**: MitateDB `ControlPlaneLimits.__post_init__` の `[1, 200]` を 4 クラスすべてで撤廃し、**正の整数のみ**の検査にする (r2db と対称)。関係検査 (`control_requests_per_minute > applications + 2 × credentials_per_application + 67`) は独立に残る。**契約は不変**。
- **D-4**: 契約 1.5.0 の公開 (WP-1) では**どちらの peer の `contract_version` も動かさない**。各 peer の flip はその peer が 1.5.0 の挙動を出荷する WP の**同一コミット**に落とす。**全体 vacuity guard を WP-1 で `xfail(strict=True)` 登録し、最後の flip WP (WP-3) と同一コミットで外す**。

---

## 2. 範囲外 (本書では扱わない)

以下は**列挙のみ**である。本書の WP は一切触れない。

1. **Q4** — `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合 (設計 §10。独立フェーズ)。
2. **L4-8 (C-09 vector 4 の据え置き)** — P4-D18 の射程明示のまま。**vector 4 の docstring と CONDITIONS.md の該当開示を書き換えない**。
3. **L4-12 / L4-13** — `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 が引き続き保持する。
4. **1.4.0 alias の除去** — `endpoints.audit_query` (`POST /v1/audit/query`) の alias は**除去しない**。D-2 は alias が data ホスト上にも存在し続けることを前提にしている (設計 §10)。
5. **`request_bytes` の検査ループ位置の非対称** (r2db は共通ループ、MitateDB は別建て) — D-3 の射程外。触らない。
6. **共通 suite の `_MAX_EXERCISABLE_LIMIT`** (`conformance-tests/test_c14_authority_boundary.py:142` の `200`) — これは**共通 suite が conformance build に課す構成上限**であって MitateDB の製品コードの上限とは別物である。D-3 で撤廃するのは後者だけであり、**前者は動かさない**。
7. **conformance adapter の構成値** — `MitateDB-api/conformance/conformance_adapter_mitatedb.py:378` の `applications=100, credentials_per_application=5, control_requests_per_minute=200` は**据え置く** (設計 §6.4)。撤廃は受理域の拡大なので既存構成は影響を受けない。

---

## 3. WP 分割 (依存順)

| WP | 担当 | 内容 | 公開面 (契約) への影響 |
|---|---|---|---|
| **WP-1** | Sonnet 実装 → Opus レビュー → Opus 受け入れ監査 | **契約 1.5.0 単一コミット** — spec 変更 (項目 1 = 1.5.0 段落 / 項目 2 = 1.4.0 義務 (b) の同ラベル補筆) + r2db パッケージ内コピーの byte 同一同期 + `CCR_DISPOSITION` 従属判断 10 + 共通テスト + **port v1.9** + 4 adapter のメソッド実装 + 全体 vacuity guard の `xfail(strict=True)` 登録 + `CONFORMANCE_ADAPTER_V1.md` §19。**peer の版数 flip は含まない** | **あり (契約公開)** |
| **WP-2** | 同上 | **r2db 単一 peer コミット** — keyword-only 化 + 走査器一般化 + 除外リスト + D/N + 宣言 2 キー + 宣言スナップショット 2 本 + **`contract_version` 1.5.0 flip** | あり (宣言拡張 + 版数宣言) |
| **WP-3** | 同上 | **MitateDB 単一 peer コミット** — WP-2 と同型 + `http.py:731` のリネーム + 2 モジュール構成の宣言 + **`contract_version` 1.5.0 flip** + **全体 vacuity guard の `xfail` 撤去** | あり (宣言拡張 + 版数宣言) |
| **WP-4** | 同上 | **Q3 (D-3)** — MitateDB の `[1, 200]` 撤廃 + テスト差し替え + 配備記録 + adapter コメント + 台帳結審 (L4-4 / L4-7(iii) / Q3) | あり (受理域拡大)。**契約不変** |
| **WP-5** | Opus 起草 → 監督 → Opus 受け入れ監査 | **記録整理** — 設計 §10 実装記録、PHASE4 §11.1 / §11.2 の結審、`CONDITIONS.md`、`CONTROL_MAPPING.md`、両 peer runbook / 配備文書の宣言例、ハンドオーバー | なし |

**依存順の根拠**:

- **WP-1 → WP-2 / WP-3** は厳密な依存である。契約 1.5.0 が公開されていない状態で peer が 1.5.0 を宣言するのは `version_binding` 規律違反であり、共通テストの 1.5.0 分岐も存在しない。
- **WP-2 → WP-3** の順序は、全体 vacuity guard の `xfail` を**最後の flip WP と同一コミットで外す**という要求 (設計 §8 の 3) から来る。順序を入れ替えるなら guard 撤去も入れ替わる。
- **WP-4 は独立**である (触るファイルが WP-1〜3 と重ならない: `control_plane.py` の `ControlPlaneLimits` と限界テスト・配備文書のみ)。ただし WP-3 と同じ `MitateDB-api/src/mitatedb_api/control_plane.py` を触るため、**WP-3 の後に置く** (衝突回避)。
- **WP-5 は最後**である。WP-1〜4 の実測結果 (テスト名・集計行・N の確定内容) を記録するため。

各 WP は **Sonnet 実装 → Opus コードレビュー (変異注入必須) → 差し戻し → Opus 受け入れ監査**の順で回す。

---

## 4. 各 WP の発注

### WP-1 契約 1.5.0 + 共通 suite (port v1.9)

#### 目的

契約 1.5.0 を公開し、(i) `operation` / `target_kind` を**宣言語彙**にする条件付き義務を導入し、(ii) 1.4.0 無条件義務 (b) の適用範囲を**同ラベル補筆**で一意にし、(iii) 双方を共通 suite で機械的に固定する。**peer の挙動は一切変えない**。

**この WP のコミットは依頼者確認後に行う** (設計 §2 の 8 / §5)。契約の英文の最終文言は依頼者確定待ちであり、実装者は**監督から確定文言を受け取ってから spec を書く**。確定前に着手してよいのは共通テスト・port・adapter の側だけである。

#### 変更対象

**1. `spec/data-service-api.v1.json`**

- `contract_version` を **`"1.5.0"`** へ (現行 `:6`)。
- `versioning.version_binding` (`:32`) に **1.5.0 段落**を追加する。**項目 1 (D-1) のみ**を条件付き義務として逐条列挙する (`audit_query` が `unavailable` 以外のときのみ)。末尾の「An implementation still declaring X.Y.Z is not held to any later-version obligation retroactively」の列挙にも 1.5.0 を加える。
- **同じ `version_binding` の 1.4.0 無条件義務 (b) の本文を補筆する** (項目 2 = D-2)。**1.5.0 段落へは置かない。** 補筆の根拠は契約本文自身の「added by a later revision of this document still under that same label」条項であり、従属判断 10 の additive 根拠にもこの一文を引く。英文の骨子は設計 §3 D-2 にある (**最終文言は依頼者確定待ち**)。骨子の要点 3 つを外さないこと:
  - **第 1 文は host scoping を既存条項と結ぶ** — 受理対象を control surface の `audit_query` control endpoint (正典 `POST /control/v1/audit/query` と **control ホスト上の** alias) に限り、`endpoints.audit_query.deprecation_note` が既に述べている同じ host scoping と、**1.4.0 条件付き義務 (5)** (canonical path と alias の双方が identical operation として応答すること) を明示的に参照する。義務 (5) は「どちらのホスト上の alias か」を言っておらず、答えは既に `deprecation_note` にある — 補筆はそれを見えるようにする (設計 §3 D-2 の N-3)。
  - **許容形にする** — `may refuse … as an unknown credential (AUTH_INVALID)` + `is not thereby required to accept, verify, or forward it`。義務形 (`never accepted or forwarded`) にしない。
  - **`forwarded` の禁止を作らない** — data ホストの alias が control surface へ転送する実装は義務 (5) を分離配備で満たす自然な手段でありうる。同ラベル改訂で禁止すればその形の 1.4.0 実装が**遡って非適合**になり、additive 主張が崩れる (設計 N-2)。
- `capabilities` / `audit` 節に **`operations`** / **`target_kinds`** の宣言キーの定義を「`Since 1.5.0 (subordinate ruling 10, item 1, conditional on audit_query being provided): ...`」書式で追加する (1.4.0 の `query_event_class_vocabulary` と同じ体裁)。
- **曖昧解消文を必ず置く** — 「これは `audit.fields` の `operation` 列が取りうる値の語彙であって、`capability_status.defined.atomic_mutation` が言う実行語彙ではない」旨。`target_kinds` には同種の衝突は無い。
- `audit` 節に、新 2 キーへの**対応キー** (`event_classes` に対する `query_event_class_vocabulary` と同型の注記) を置く。

**2. `r2db-api/src/r2db_api/contract/data-service-api.v1.json`**

- `spec/data-service-api.v1.json` と**バイト同一**に同期する。既存テスト `r2db-api/tests/test_http.py:286` `test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` がこれを固定している。**このテストを緩めない。**

**3. `spec/CCR_DISPOSITION.md`**

- **従属判断 10** を house style で記録する (従属判断 9 = `:127-148` と同じ構成)。
  - **(a) 各項目の内容と根拠** — 項目 1 = D-1、項目 2 = D-2。
  - **(b) すべて additive である根拠** — 項目 1 は追加キー (キー削除・型変更・enum 縮小なし)、項目 2 は許容形の明確化で既存の co-hosting 容認を狭めず、`forwarded` の禁止も作らない。
  - **項目 2 の additive 根拠には実測を添える** (設計 §8 の N-4) — 補筆の第 1 文は受理対象に「control ホスト上の alias」を明示するため、**文言上は義務 (b) の受理経路が 1 つ増える** (現行の (b) は `audit_query` control endpoint しか名指ししていない)。**両 peer とも control ホストで alias を同一ハンドラへ載せている** — `r2db-api/src/r2db_api/control_http.py:398-399` と `MitateDB-api/src/mitatedb_api/control_http.py:391-392` がいずれも `/control/v1/audit/query` と `/v1/audit/query` を同じ `post_audit_query` へルーティングする。したがって**既存 1.4.0 peer の適合は変わらない**。**この実測を検証可能な根拠として従属判断 10 に記す** (両ファイルの実際の行を確認したうえで書くこと — 行番号がずれていれば実測が正)。
  - **義務の条件付き性を独立した太字段落で書く** — **項目 1 は条件付き** (`audit_query` が `unavailable` 以外のときのみ)、**項目 2 は無条件** (1.4.0 の (b) 自身が無条件であり、その適用範囲の明確化も無条件)。従属判断 9 はこの段落を `version_binding` 本文の (a)(b)(c) / (1)〜(6) と 1 対 1 に対応させている (WP-1 レビュー F-2 で個数表記まで合わせた) — 10 も同じ分割を持つため必要である。
  - **(c) 版数の扱い**、**(d) 依頼者裁定の参照 + 却下側の明記** (設計 §4 の Q1 却下案 2 件 / Q2 却下案 2 件、および Q4 が本束に入らないこと)。
  - **項目ごとの再検討条件**。

**4. `conformance-tests/test_c09_audit_evidence.py`**

- **候補集合の廃止** — `_LIKELY_DESTRUCTIVE_OPERATIONS` (`:143`) / `_LIKELY_DESTRUCTIVE_TARGET_KINDS` (`:161`) の 2 定数と、それを参照する相関条件 (`:372-373`) を**削除**する。廃止の経緯はコメントとして残さず、`CONDITIONS.md` の C-09 行に**置換の事実として**記録する (WP-5)。
- **vector 1 の 1.5.0 分岐** — 1.5.0 以上を宣言し `audit_query` が `unavailable` 以外の peer に対しては、破壊的操作の直後に現れた**新規 durable 行**の `operation` / `target_kind` が**それぞれ宣言に含まれること**を課す。1.4.0 の peer は従来どおりの vector 1 (application_id スコープの破壊的操作イベントが存在すること) だけを課される形へ分岐する。分岐は既存の `_semver_tuple` (`:167`) / `_audit_query_declaration` (`:211`) を使う。
- **宣言整合 vector を 3 フィールド同型で新設する** — `audit_query` が返す**全 event** の当該フィールドが宣言に収まることを見る。
  - `event_class` ⊆ 宣言 `event_classes` — **1.4.0 条件付き** (1.4.0 条件付き義務 (4) が既に `event_classes` の宣言義務を課しているため、**1.4.0 以上を宣言し `audit_query` が `unavailable` 以外**の peer に掛かる)。**したがって本 WP の時点 (両 peer とも 1.4.0) で、この vector は 4 adapter 全数に対して load-bearing であり vacuous ではない** — 「1.5.0 待ちで素通り」する形にしてはならない。
  - `operation` ⊆ 宣言 `operations` — **1.5.0 条件付き**。本 WP の時点では全 adapter が分岐を素通りする (peer が未 flip)。
  - `target_kind` ⊆ 宣言 `target_kinds` — **1.5.0 条件付き**。同上。
  - **(i) と (ii) の関係** (設計 §6.1): vector 1 の (i) は宣言整合 vector (ii) の**部分集合**である。(i) が固有に足すのは検出力ではなく**位置づけ**であり、**(i) を (ii) の重複として削ってはならないし、(i) に (ii) 以上の検出力を期待してもならない**。
- **義務 (b) の data ホスト vector を新設する** — **xfail なしの無条件登録**。port v1.9 の新メソッド経由で data ホストの `/v1/audit/query` alias へ control/audit credential を提示し、期待は「**`AUTH_INVALID` による拒否**」**または**「**control surface と同居するホストでは `audit_query` の提供**」の**いずれか**。**`CAPABILITY_UNSUPPORTED` / `FORBIDDEN` / 5xx は不適合**である。
  - `SurfaceAbsent` を受けた場合は、既存の `_assert_audit_surface_absent_claim` (`:224`) と同じ **3 部構成で claim を独立検証**する (adapter の言い分をそのまま受け取らない)。
  - **拒否コードを検証するヘルパ (`_require_denied_with(code)` 相当) を本 WP で追加する** — 現行ファイルには `_require_provided` (`:294`) しかない。
- **全体 vacuity guard を 1 本追加する** — 「登録済み adapter の全数が 1.5.0 を宣言していること」を要求する。**`@pytest.mark.xfail(strict=True)` 付きで登録**し、reason に「no peer declares 1.5.0 yet; un-xfailed by the last flip WP」旨を書く。**既存の 1.4.0 全体 guard (`test_c09_every_control_surface_adapter_takes_the_provided_branch`, `:636`) と同形である** — すなわち **`adapter` fixture を取らない非 parametrize のテスト関数 1 本**であり、内部で `registered_adapters()` を機械走査して各 adapter の実 `control_plane` status から対象集合を導く。**adapter 名のハードコード列挙にしない。** 収集件数は **1 件**であって 4 件ではない (期待実測値表の前提)。
- **既存の 1.4.0 全体 guard と個別 guard (`:619`) を弱めない**。

**5. `conformance-tests/adapter.py` — port v1.9**

- `ConformanceAdapter` へ**抽象メソッドを 1 本追加**する (名称案 `audit_query_on_data_plane_host(actor)`)。
- **実装方針 — alias ハンドラ自体へ提示する形を要求する** (設計 §6.2): D-2 の契約命題は「**data ホストの `POST /v1/audit/query` alias エンドポイントが control credential を受理しない**」である。したがって本メソッドは、**その alias ハンドラそのもの** — r2db は data-plane の `audit_query` 入口、MitateDB は `http.py:830` の `post_audit_query` 相当 — に control credential を提示する実装を要求する。
- **到達できない plug の扱い**: ハンドラへ到達できない plug についてのみ、data-plane の認証面 (r2db = `DataService` の application authenticate 経路、MitateDB = `auth.CredentialStore.authenticate`) への control secret 提示を代替として許す。ただしこれは**別の命題 (store 分離) を検査している**ので、`CONDITIONS.md` の登録行に「**この plug は alias エンドポイントではなく認証面で観測している**」ことを**限界として開示する** (WP-5)。
- **戻り値の規約**: 成功 (受理されてしまった場合) は `Mapping` を返し、**peer の拒否は `ConformanceDenial(code, …)` を送出する** — 既存の `audit_query()` と同じ慣行。
- **`SurfaceAbsent` の扱い**: `control_plane` を `unavailable` と宣言する peer、または data ホストに `/v1/audit/query` alias を持たない peer に対しては `SurfaceAbsent` を送出する。既存の `SurfaceAbsent` 意味論 (フェーズ4 で拡張済み) を**変えない**。
- **既存メソッドの意味を変えない**。既存の `audit_query()` が「control base URL しか使わない」と明示的に文書化していることはそのまま維持する。

**6. 4 adapter のメソッド実装**

- `r2db-api/conformance/conformance_adapter_r2db.py` / `conformance_adapter_r2db_http.py`
- `MitateDB-api/conformance/conformance_adapter_mitatedb.py` / `conformance_adapter_mitatedb_http.py`
- **HTTP adapter は data base URL へ送ればこれを満たす。** in-process plug は alias ハンドラへ到達できるならそこへ、できないなら上記の代替形 + 限界開示。
- Python の `ABC` により、実装しない plug はそもそも生成できない。**4 本すべてが実装すること**。

**7. `docs/design/CONFORMANCE_ADAPTER_V1.md`**

- **§19 (v1.9) を新設**する。§18 (v1.8) と同じ構成 — 追加メソッドの意味論 / 既存 `SurfaceAbsent` 機構との関係 / **§19.x 末尾に「Compatibility impact」** (§18.7 と同型: ABC への additive 追加であること、既存 `SurfaceAbsent` の raise site / consumer が変わらないこと、既存メソッドの意味が不変であること)。

**8. `conformance-tests/CONDITIONS.md`**

- **C-09 行** — port を **v1.9** へ、1.5.0 分岐と新 vector 群を実在テスト名で逐語に加える。**限界 (b) (手書き候補集合の開示) を置換の記録へ書き換える**。**限界 (a) (P4-D18 による vector 4 の射程開示) はそのまま保つ** (本書 §2 の 2)。
- **義務 (b) の data ホスト vector の登録先は C-09 行である** (**監督裁定、2026-09-03**。設計 §6.3 が「作業指示書で確定する」とした未決事項の結論)。`audit_query` 面の性質であるため C-14 系の認可境界行ではなく C-09 行へ vector を追記する。**C-09 行が長くなる場合は、行内を項目番号で区切ってよい** (既存の限界 (a)(b)(c)(d) と同じ書式感覚)。**この登録先は実装者裁量にしない** — 別の行へ移すのは監督裁定の変更である。
- 当該 vector の登録には、認証面代替を使う plug がある場合の **plug 名と「alias エンドポイントではなく認証面で観測している」旨を限界として開示**する。

#### 完了条件 (検証可能な形)

1. **契約版数** — `spec/data-service-api.v1.json` の `contract_version` が `"1.5.0"` であり、`versioning.version_binding` に **1.5.0 段落**が存在し、末尾の非遡及列挙にも 1.5.0 が加わっていること。
2. **項目 2 の置き場所と形** — D-2 の補筆が **1.4.0 無条件義務 (b) の本文へ**入っており、**1.5.0 段落には入っていない**こと。義務形ではなく**許容形**であること (「拒否してよい」であって「拒否しなければならない」ではない)。**`forwarded` の禁止句が無い**こと (「受理・検証・転送を要求されるものではない」という許容の否定形は可)。**`versioning.control_discovery` の co-hosting 容認の文言が削られていない**こと。補筆の第 1 文が **`endpoints.audit_query.deprecation_note` の host scoping と 1.4.0 条件付き義務 (5)** を参照していること。
3. **曖昧解消文の存在** — `audit_query.operations` が `capability_status.defined.atomic_mutation.operations` と別物であることを述べる文が契約中に存在すること。
4. **additive 性の機械確認** — 1.4.0 → 1.5.0 の再帰比較で **キー削除 0 / 型変更 0 / enum・required・閉鎖宣言の退行 0** であること (従属判断 9 の WP-1 で採った監査手順と同じ形)。**変更されたスカラーとその件数を完了報告に列挙すること**。
5. **packaged copy の byte 同一** — `r2db-api/tests/test_http.py::test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` が緑。**このテストを緩めていない**こと。
6. **従属判断 10** — `spec/CCR_DISPOSITION.md` に従属判断 10 が (a)〜(d) + 項目ごとの再検討条件 + **義務の条件付き性の独立した太字段落**を持って存在すること。条件付き性の段落が `version_binding` の項目分割 (項目 1 = 条件付き / 項目 2 = 無条件) と 1 対 1 で対応していること。**項目 2 の additive 根拠に、両 peer の control ホストが alias を同一ハンドラへ載せている実測 (`r2db-api/src/r2db_api/control_http.py` / `MitateDB-api/src/mitatedb_api/control_http.py` の該当ルーティング) が書かれている**こと — 「受理経路が文言上 1 つ増えるが既存 peer の適合は変わらない」ことの検証可能な根拠である。
7. **候補集合の消滅** — `grep -rn "_LIKELY_DESTRUCTIVE" conformance-tests` が **0 行**であること。
8. **vector 1 の版分岐** — 1.5.0 を宣言する adapter には (i) の宣言整合が課され、1.4.0 の adapter には課されないことが、`_semver_tuple` / `_audit_query_declaration` 経由の分岐として存在すること。**本 WP の時点ではどの adapter も 1.4.0 分岐を通る**こと (peer は flip していない)。
9. **宣言整合 vector 3 本** — `event_class` / `operation` / `target_kind` の 3 フィールドについて、返された全 event の値が宣言に収まることを見る**同型の vector が 3 本**存在すること。`event_class` は 1.4.0 条件付き、他 2 本は 1.5.0 条件付きであること。**`event_class` の vector が本 WP の時点で 4 adapter 全数に対して実際に走り、load-bearing であること** — 「adapter の宣言 `event_classes` から 1 語落とすと赤になる」ことを実測で示す (本 WP で唯一、宣言整合が実観測を伴う vector である)。
10. **義務 (b) vector が無条件登録** — 当該テストに `xfail` が付いていないこと。`AUTH_INVALID` 拒否**または** `audit_query` の提供を受理し、**`CAPABILITY_UNSUPPORTED` / `FORBIDDEN` / 5xx を不適合として赤にする**こと (この 3 分類が実際に赤になることを変異注入 3 で示す)。`SurfaceAbsent` を受けた場合に claim を 3 部構成で独立検証していること。
11. **port v1.9** — `conformance-tests/adapter.py` に新メソッドが抽象メソッドとして存在し、**4 adapter すべてが実装**していること。既存メソッドの意味論が変わっていないこと。
12. **`CONFORMANCE_ADAPTER_V1.md` §19** — 新設され、§18 と同じ構成 (意味論 / `SurfaceAbsent` との関係 / Compatibility impact) を持つこと。
13. **全体 vacuity guard** — 1.5.0 版の guard が `xfail(strict=True)` で登録され、**`registered_adapters()` の機械走査**であること (adapter 名のハードコード列挙でないこと)。既存の 1.4.0 guard 2 本 (個別・全体) が**弱められずに緑のまま**であること。
14. **peer の宣言が動いていないこと** — 両 peer の `contract_version` が **1.4.0 のまま**であること (`r2db-api/src/r2db_api/service.py:881` / `control_plane.py:702`、`MitateDB-api/src/mitatedb_api/cell.py:1275` / `control_plane.py:1346`)。**peer の製品コードを一切変えていない**こと。
15. **CONDITIONS.md** — C-09 行が port v1.9 と新 vector を実在テスト名で述べ、限界 (b) が置換の記録へ書き換わり、**限界 (a) が無傷**であること。**義務 (b) の data ホスト vector が C-09 行に登録されている**こと (C-14 系ではない — 監督裁定)。`./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py` のマーカー/行対応が**双方向で緑**。
16. **変異注入 3 種がすべて赤** — 下記「変異注入」のとおり。
17. **完了ゲート** — root suite を単独実行し、**`failed` 0 / `skipped` 0 / `xfailed` 1**、`passed` が 1545 から増えていること。conformance suite は **404 + 新規分**。**増分の内訳 (どの vector が何本の収集 id を増やしたか) を完了報告に書くこと** — 共通 vector は 4 adapter でパラメータ化されるため、テスト関数 1 本が収集 4 件になる。

#### テストコマンド

```
# 開発中の反復
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q r2db-api/tests/test_http.py

# 完了ゲート (リポジトリルートで単独実行。他の pytest が走っていないことを確認してから)
./.venv/bin/python -m pytest -q
```

実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない**。

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **項目 2 が 1.5.0 段落へ漏れていないか** — D-2 は**1.4.0 の同ラベル補筆**である。1.5.0 段落へ置けば、1.4.0 を宣言し続ける両 peer に対して**契約が要求していない挙動をテストが無条件で要求する**状態が生じる (設計 §3 D-2 が名指しで避けた三すくみ)。
2. **義務形への後退 / 新規禁止の混入** — 補筆が「data ホストは拒否**しなければならない**」形になっていないか。義務形は `versioning.control_discovery` の co-hosting 容認 (「convenience, **not a requirement**」) と衝突し、**1.5.0 束の additive 性を崩す**。あわせて **`forwarded` の禁止が混入していないか** — 転送は義務 (5) を分離配備で満たす自然な手段でありうるため、禁止すればその形の 1.4.0 実装が**遡って非適合**になる (設計 N-2)。「受理・検証・転送を要求されるものではない」という**許容の否定形**と、「転送してはならない」という**禁止**を混同していないか。
3. **実装制約を契約に書いていないか** — 「application-credential store と control-credential store を同一プロセスに置かない」等の**特定 control** が契約本文に入っていないか。CLAUDE.md の「同じ安全結果を与えるなら platform-specific control は peer 間で異なってよい」に反する。実現手段は `CONTROL_MAPPING.md` SI-00 行の管轄である (WP-5)。
4. **義務の条件付き性** — 項目 1 の義務が `audit_query` を `unavailable` と宣言する配備にも掛かる形になっていないか。1.4.0 の条件付き義務 (1)〜(6) と同じ条件付き性であること。
5. **曖昧解消文の実効** — `atomic_mutation.operations` との区別が、AI エージェント統合者が宣言だけを機械的に読んで取り違えない程度に**明示的**か。契約中の他の `operations` 用法を漏れなく確認したか。
6. **候補集合の再混入** — 削除した `_LIKELY_DESTRUCTIVE_*` に相当する**手書きの値集合**が、別名・別形 (ローカル変数、テスト内 literal、docstring 由来) で復活していないか。**宣言参照へ置換することが D-1 の核心**であり、手書きへ戻った時点で L4-1 の元の欠陥に戻る。
7. **vector 1 (i) の位置づけ** — (i) が (ii) の重複として削られていないか、逆に (i) に (ii) 以上の検出力を期待する書き方になっていないか (設計 §6.1)。
7b. **`event_class` vector の vacuity** — 3 本を「同型」に揃えた結果、`event_class` の版分岐まで 1.5.0 条件付きへ引きずられていないか。**1.4.0 条件付きであり、本 WP から 4 adapter 全数で走る**のが正である (設計 N-7)。「3 本とも 1.5.0 待ち」になっていれば、本 WP の宣言整合は全部 vacuous であり、guard 以外に実観測が 1 つも無い状態になる。
7c. **additive 根拠の実測** — 従属判断 10 項目 2 が「受理経路が文言上増える」ことを**認めたうえで**、両 peer の alias 同一ハンドラ実測でそれが既存適合を変えないことを示しているか。実測を省いて「明確化だから additive」とだけ書いていないか (設計 N-4)。
8. **義務 (b) vector の観測対象** — テストが **alias ハンドラそのもの**を観測しているか。認証面代替を使う plug があるなら、その事実が **CONDITIONS.md に限界として開示**されているか。開示が無ければ、alias ハンドラで auth とケイパビリティ判定の順序が入れ替わっても該当 plug は気付かない。
9. **不適合分類の網羅** — `CAPABILITY_UNSUPPORTED` / `FORBIDDEN` / 5xx の 3 つが**すべて**赤になるか。1 つでも「拒否だから緑」と丸められていないか。
10. **`SurfaceAbsent` claim の独立検証** — adapter の言い分をそのまま受け取る形になっていないか。既存の `_assert_audit_surface_absent_claim` と同じ 3 部構成か。
11. **guard の弱化** — 新 guard の `strict=True` が落ちていないか、全数要求が「1 本でも通れば緑」へ緩んでいないか、`registered_adapters()` 走査が名前列挙へ退化していないか。**既存の 1.4.0 guard 2 本**が無傷か。
12. **peer への波及** — peer の製品コード・宣言・版数が 1 バイトでも動いていないか (本 WP の射程外)。
13. **秘密の混入** — 契約・従属判断・§19 の追記に実 DSN / パスワード / 実在ドメインが無いか。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

1. **契約 JSON の byte 不一致** — `r2db-api/src/r2db_api/contract/data-service-api.v1.json` を 1 バイト改変し、`test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` が**赤**になること。
2. **候補集合の復活** — 廃止した候補集合と同型の手書き集合 (`frozenset({"delete", "mutate"})` 相当) を vector 1 の判定へ戻し、**宣言参照の経路が実際に load-bearing であること**を示す — 具体的には、adapter の宣言側から `operations` / `target_kinds` を落としても宣言整合 vector が緑のままにならないことを、宣言側を空集合にする変異で確認する (**宣言を空にすれば返却値との ⊆ が破れて赤**)。
3. **義務 (b) vector の不適合分類** — adapter (in-process 1 本 + HTTP 1 本) の新メソッド実装を、`CAPABILITY_UNSUPPORTED` を返す形・`FORBIDDEN` を返す形・5xx を返す形へ**それぞれ**改変し、**3 形すべてで赤**になること。あわせて「受理されて `Mapping` を返す」形にしたとき、control surface と同居していない plug で**赤**になること。

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-2 r2db-api — 走査器一般化 + 宣言 2 キー + 1.5.0 flip

#### 目的

r2db の `operation` / `target_kind` を**宣言語彙**にし、`event_class` と同じ機械保証 (`U == D ∪ N` かつ `D ∩ N == ∅`) を 3 フィールドで掛ける。あわせて `contract_version` を 1.5.0 へ flip する。**flip と挙動出荷は同一コミット**である。

#### 変更対象

**A. 製品コード — keyword-only 化 (挙動不変)**

`operation` / `target_kind` を `*` の後ろへ移し、位置渡しの呼び出し (計 20 箇所超) をすべてキーワード渡しへ書き換える。**仮引数の順序も既定値も変えず、渡し方だけを変える。**

| 定義 | フィールド |
|---|---|
| `r2db-api/src/r2db_api/control_plane.py:1335` `_authorize_role` | `operation` |
| `r2db-api/src/r2db_api/control_plane.py:1363` `_gate_must_rotate` | `operation` |
| `r2db-api/src/r2db_api/service.py:1383` `_control_event` | `operation` |
| `r2db-api/src/r2db_api/service.py:1139` `_event` | `operation` / `target_kind` |
| `r2db-api/src/r2db_api/service.py:1078` `deny_unsupported` | `operation` |

**B. 除外リスト — `_NON_AUDIT_OPERATION_PARAMETERS` (8 定義)**

規則 (c) は callee 名で絞らない**無差別**規律なので、`operation` という名の仮引数を持つ定義すべてに反応する。監査と無関係な下記 8 定義は**名指しの除外リスト**に載せる。各項目に qualified 名と**根拠**(「この `operation` はクライアント由来の mutation / schema dict であって監査フィールドではない」) を付す。

| 定義 |
|---|
| `backend.py:104` `apply_schema` (抽象基底) |
| `postgres.py:1194` `_apply` |
| `postgres.py:1528` `apply_schema` |
| `service.py:1034` `schema` |
| `structured.py:199` `bind_mutation` |
| `structured.py:569` `bind_schema_operation` |
| `structured.py:1206` `_apply` |
| `structured.py:1376` `apply_schema` |

**除外リスト自体を検証するテスト 2 本**を置く:

- **(i)** 除外リストの**各項目が実在すること** (陳腐化した項目は赤 — 関数が消えた・改名されたときに気付く)。
- **(ii′)** 除外された定義の本体に、**`<field>=<Name>` の形でその定義自身の仮引数 `<field>` を渡す `Call` が無いこと** (= **クライアント由来値が監査 emit 面へ転送されないこと**)。

**(ii) ではなく (ii′) である (設計 v1.3 の N-1)。** v1.2 は (ii) を「本体に `<field>=` を `Constant` で渡す `Call` が無いこと」と書き、あわせて「監査 literal を運ぶ定義は除外できない構造」と主張していた。**この主張は r2db の現行コードに反証されている** — `service.py:1034` `DataService.schema` は (a) 除外が**必要**であり (`operation` はクライアント由来の schema operation dict。keyword-only 化すると `http.py:355` の `service.schema(context, body, request_id=…)` という準公開の位置渡し規約が変わる)、かつ (b) **監査 literal の発生源でもある** (`:1052` が `operation="schema"` を `_make_audit_hook` へ `Constant` キーワードで渡す。keyword-only 化後は `:1054` / `:1057` の `_event` 呼び出しも同形になり、(ii) 違反は 5 → 7 件へ増える)。**(ii) をそのまま実装すると WP-2 が赤で止まる。**

(ii′) は検査の性質を「この定義の本体に監査 literal が無いこと」から「**この定義の仮引数 `<field>` が監査 emit 面へ転送されないこと**」へ移す。除外の目的 (クライアント由来値が監査フィールドへ入らないこと) を過不足なく捉え、かつ (c) が emit 面を keyword-only に固定した後は転送が必ず `<field>=<Name>` 形になるので**抜けが無い**。**U の完全性には影響しない** — 除外が免ずるのは (c) の keyword-only 要求だけであり、`:1052` / `:1054` / `:1057` の `Constant` は (b) 側で従来どおり U に加算される。**実測では 9 定義すべてが (ii′) を CLEAN で満たす。**

**C. 走査器の一般化 — `r2db-api/tests/test_audit_query.py`**

採るのは **P4-D16 v3 (a)〜(e) の大域不変量方式をフィールド名でパラメータ化したもの**である。「呼び出し地点ごとの値解決」方式は**採らない** (設計 §3 D-1 が名指しで却下)。既存の器 (`_iter_src_files` `:882`、`_collect_direct_shadow_names` `:893`、`_scan_event_class_literals` `:1200`) をフィールド名でパラメータ化し、**`event_class` も同じ器へ載せ替える** — 3 フィールドで走査器 1 実装とする。

既存規則 (a)〜(e) をパラメータ化したうえで、**追加・変更する規則**は 3 つ:

- **(b′) `IfExp` の許容** — 両枝がともに許容値であるとき許容し、その `Constant` 枝を U に加算する。キーワード値の位置と代入値の位置の**両方**に適用し、**再帰的に評価する**。これで `ops.py:655` / `:688` の inline 三項演算が閉じる。
- **(b″) 同名変数への Constant 代入の許容** — `<field>` と同名の変数への `Assign` が `Constant` または IfExp-of-Constants であれば許容し、値を U に加算する。その名前の転送は**closure 越しを含めて**仮引数転送と同格に扱う。**ただし同スコープに他の束縛形が 1 つでもあれば違反のまま**である (`_collect_direct_shadow_names` が数える全形 — `for` ターゲット / `with … as` / `except … as` / walrus / `match … as` / `global` / `nonlocal` / 同名の `def`・`class`・import alias)。これで `control_plane.py:846` / `:1070` の closure 捕捉が閉じる。
- **(b‴) 読み出し側 passthrough はキーワード引数値では禁止する** (3 フィールド共通) — `.<field>` の `Attribute` / `["<field>"]` の `Subscript` は、**応答整形の dict literal の値** (`{"operation": row["operation"], …}`)、**添字代入 (`x["<field>"] = …`) の値**、**属性代入 (`obj.<field> = …`) の値**の 3 位置で許容し、**`<field>=` キーワード引数の値としては許容しない**。**禁止するのはキーワード引数値の位置のみである。**
  - **(b‴) の導入に製品変更は不要である (設計 v1.3 の N-6)** — 現行コードの読み出し経路は 3 フィールド × 両 peer とも**すべて dict literal 形**であり (r2db `audit_query.py:150,157,158` / `control_plane.py:1155,1159`)、keyword passthrough 形は**実測 0 件**である。**(b‴) は純粋な締め付けであって書き換え対象を生まない — 探す必要はない。** 見つけたと思ったら、それは (b‴) の読み違いか、実測後にコードが変わったかであり、監督へ報告すること。

**あわせて実装者へ (無用な手入れを防ぐため)**: 転送ラッパ (`<field>=` キーワードを持たない `**fields` 形) は走査対象に入らない。これは穴ではない — そこを流れる literal は外側の呼び出しサイトで U に捕捉される (設計 §3 D-1「大域不変量方式の要点」)。

**D. 宣言と D / N — `r2db-api/src/r2db_api/audit_query.py` / `control_plane.py`**

- `audit_query.py` に **`DECLARED_AUDIT_OPERATIONS`** / **`DECLARED_AUDIT_TARGET_KINDS`** を frozenset として追加する (`DECLARED_AUDIT_EVENT_CLASSES` `:53` と同型の**単一定義**)。`__all__` (`:218` 近傍) にも足す。
- `control_plane.py` の `control_capabilities` 宣言 dict (`:729` の `"event_classes": sorted(self._audit_event_classes)` の位置) に **`"operations"` / `"target_kinds"` の 2 キーを追加**する。`:623` / `:648` と同じ体裁で、コンストラクタ引数と `self._audit_*` フィールドを対に増やす。
- **N の判定基準** (設計 §3 D-1、両 peer 共通): literal `L` が N に属するのは、**`L` を `Constant` として渡す emit サイトが 1 つ残らず非耐久経路で終端すること**を示したときに限る。**durable 経路のサイトが 1 つでもあれば `L` は D である。**
- **N は実行時テストで確定する** — 静的な構造的根拠 (legacy in-memory sink であること) は出発点であって証明ではない。r2db の非耐久経路候補は `ControlAuthority._control_event` (`service.py:1385-1386` → legacy in-memory `self._audit.append`) と `DataService._event` の `event_class="authentication"` 分岐である。**当該経路を通す実行時テストで `application_audit` / `control_audit` に行が立つかを実測し、届かないものだけを根拠コメント付きで N へ置く。**
- **候補 8 語のうち D 側になるものがある** — 設計 §1.4 の 8 が挙げた `authenticate`, `delete_audit`, `disable_application`, `enable_application`, `issue_credential`, `register_application`, `set_authorization_state_available`, `set_credential_state` は「非耐久経路にも現れる」語であって「非耐久経路にしか現れない」語ではない。とくに **`enable_application` / `disable_application` は `control_plane.py:846` の `_write_state_audit` 経路で耐久に現れるため D 側である**。`target_kind` 側の候補は `application_or_credential` (`_control_event` 専用) の 1 語。
- **宣言スナップショットテスト 2 本**を追加する — `test_declared_audit_event_classes_change_only_deliberately` (`tests/test_audit_query.py:1538`) と同型で、`DECLARED_AUDIT_OPERATIONS` / `DECLARED_AUDIT_TARGET_KINDS` の**内容を直接 pin する**。等式 (e) は「D から抜いて同時に N へ足す」縮小を検出できないため、この一回きりの人手固定が要る。

**E. `contract_version` 1.5.0 flip**

- `r2db-api/src/r2db_api/service.py:881` と `r2db-api/src/r2db_api/control_plane.py:702` の 2 箇所。
- **版数を固定しているローカルテストの更新も同一コミット**に入れる。

#### 完了条件 (検証可能な形)

1. **keyword-only 化の網羅** — 上表 5 定義の `operation` (および `_event` の `target_kind`) が `kwonlyargs` にあり、位置渡しの呼び出し残りが**grep でゼロ**であること。**挙動が変わっていないこと** — 既存の emit 行の内容・語彙を固定するテストが**値の変更なしで**緑のまま。
2. **走査器が 3 フィールドで 1 実装** — `event_class` / `operation` / `target_kind` が同じパラメータ化された器で走ること。`event_class` 専用のハードコード走査が残っていないこと。
3. **(a)〜(e) + (b′)(b″)(b‴) の 3 フィールド分の固定** — 各規則のテストが 3 フィールドについて存在し、違反時に file:line を列挙して失敗すること。
4. **`event_class` 側の性質が後退していないこと** — P4-D16 v3 が固定した性質 (無差別 literal 規律 / keyword-only 保証 / dict 密輸禁止 / 語彙関係の厳密一致) が一般化後も同じ強度で掛かっていること。**変異注入で確認する** (下記 1〜5 を `event_class` についても実施する)。
5. **除外リスト** — `_NON_AUDIT_OPERATION_PARAMETERS` が **8 定義**を qualified 名 + 根拠コメント付きで列挙し、検証テスト **2 本** (**(i) 実在性** / **(ii′) 自関数の仮引数 `<field>` を `<field>=<Name>` で渡す `Call` の不在**) が存在すること。**(ii) (「監査 literal の非発生源性」) を実装していないこと** — `DataService.schema` が反証済みであり、実装すれば赤で止まる。**除外リストが `event_class` / `target_kind` には不要である** (該当なし) ことも確認すること。
6. **(e) 語彙関係の厳密一致** — 3 フィールドすべてについて `U == D ∪ N` かつ `D ∩ N == ∅` が固定されていること。**N の各要素に「耐久表へ届かない根拠」がコメントで付いている**こと。
7. **N の実行時実測** — N に置いた各語について、**当該経路を実際に通して耐久表に行が立たないことを実測するテスト**が存在すること。静的コメントだけで N に置いていないこと。**D と重なる語が N に無い**こと。
8. **宣言の真実性** — `DECLARED_AUDIT_OPERATIONS` / `DECLARED_AUDIT_TARGET_KINDS` に、`audit_query` が決して返さない語彙が入っていないこと。**(e) を通すために非耐久語彙を宣言へ足していないこと** (正しい手段は N への名指し列挙のみ)。
9. **宣言キーの露出** — `control_capabilities` の `audit_query` 宣言に `operations` / `target_kinds` の 2 キーが現れ、値が宣言 frozenset の `sorted()` であること。実 HTTP 経路でも観測できること。
10. **宣言スナップショット 2 本** — `DECLARED_AUDIT_OPERATIONS` / `DECLARED_AUDIT_TARGET_KINDS` の内容を直接 pin するテストが存在すること (`event_class` の既存 1 本と同型)。
11. **(b‴) が製品変更を生んでいないこと** — 読み出し経路は現行がすべて dict literal 形であり、**書き換えが 1 件も発生していない**こと。書き換えが入っていれば射程外である (設計 N-6 の実測 0 件と食い違うなら監督へ報告)。規則としての (b‴) は 3 フィールドについて実装され、**キーワード引数値の位置のみ**を禁じ、dict literal 値 / 添字代入値 / 属性代入値の 3 位置は許容していること。
12. **flip** — 両 plane の `contract_version` が `"1.5.0"` であり、**同一コミット**に上記の挙動が入っていること。宣言が先行することも挙動が先行することもないこと。
13. **共通 suite の 1.5.0 分岐が r2db 2 adapter で初実行される** — C-09 vector 1 の (i)、宣言整合 vector 3 本の 1.5.0 条件付き分岐が r2db の 2 plug で実際に走ること。**全体 vacuity guard は MitateDB が未 flip なので `xfail` のまま**であること。
14. **変異注入 8 種がすべて赤** — 下記「変異注入」のとおり。
15. **完了ゲート** — root suite 単独実行で **`failed` 0 / `skipped` 0 / `xfailed` 1**、`passed` が WP-1 の値から増えていること。**増減の内訳 (新規で増えた収集件数 / 削除・統合で減った収集件数 / 差引の純増) を完了報告に必ず書くこと** — 走査器の一般化は既存テストのパラメータ化を伴うため、単純な純増にならない可能性がある。

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **callee 名フィルタの再混入** — 走査が callee 名の集合 (allowlist / denylist / 接頭辞判定) を再導入していないか。**無差別方式を維持することが P4-D16 v3 の核心**である。除外リストは**定義側の名指し**であって callee 名フィルタではない — この 2 つが混同されていないか。
2. **除外リストの膨張** — 8 定義を超えていないか。超えているなら、それは「クライアント由来値を監査面へ転送する定義を逃がした」可能性がある。各項目の根拠が「クライアント由来の mutation / schema dict である」ことを実際に示しているか、「テストを緑にするため」に化していないか。
3. **除外リスト検証テストの実効** — **(ii′)** が「除外された定義の本体に、**自関数の仮引数** `<field>` を `<field>=<Name>` で渡す `Call` が無い」ことを本当に見ているか。**(ii) (Constant 渡しの不在) へ後退していないか** — `DataService.schema` が `operation="schema"` を `Constant` で渡すため、(ii) では緑にできない。逆に (ii′) が「`<field>=<Name>` なら何でも許す」形に緩んで、**自関数の仮引数以外の `Name`** まで見逃していないか。除外リストが空でも緑になる形 (vacuous) になっていないか。
4. **N が逃げ道になっていないか** — N の各要素に**耐久表へ届かない根拠**が書かれ、かつ**実行時実測**で裏付けられているか。`D ∩ N == ∅` が実際に固定されているか。`enable_application` / `disable_application` のように **durable 経路に現れる語が N へ逃げていないか**。
5. **(b′) の再帰性** — `IfExp` の許容が両枝とも許容値であることを要求し、ネストした `IfExp` の内側の `Constant` も U に加算しているか。片枝だけの検査になっていないか。
6. **(b″) の再束縛の抜け道** — 同名変数への Constant 代入の許容が、`_collect_direct_shadow_names` の**全形**による再束縛検査を保っているか。「同スコープに他の束縛形が 1 つでもあれば違反」が緩んでいないか。
7. **(b‴) の適用位置** — `Attribute` / `Subscript` passthrough が **dict literal 値 / 添字代入値 / 属性代入値の 3 位置で許容**され、**キーワード引数値では禁止**されているか。3 位置のいずれかを落として現行の読み出し経路を巻き込んでいないか、逆にキーワード引数値まで許して穴を残していないか。これは `event_class` の走査器には無かった、**一般化によって新設される穴**を構文で閉じるための規則である — 緩めれば将来リクエスト由来値が耐久列へ入っても誰も赤くならない。**製品変更が発生していれば射程外**である (実測 0 件)。
8. **`event_class` 側の回帰** — 一般化前に赤化していた変異が、一般化後も**すべて**赤化するか (完了条件 4)。3 フィールド共通器にしたことで `event_class` の検査が弱まっていないか。
9. **宣言スナップショットの実効** — 2 本が本当に内容を pin しているか (「空でない」等の弱い assert になっていないか)。**D から 1 語抜いて同時に N へ足す縮小**が赤になるか (変異注入 8)。
10. **flip の束縛** — `contract_version` 1.5.0 と、それを真にする挙動 (宣言 2 キー + 走査器 + D/N) が**同一コミット**か。偽の flip (宣言だけ先行) になっていないか。
11. **製品コード変更の射程** — **keyword-only 化 5 定義 + 宣言 2 キーの追加の 2 種のみ**か。(b‴) は製品変更を要さない (実測 0 件) ので、読み出し経路の書き換えが入っていれば射程外である。
12. **既存テストを緩めていないか** — `control_audit` の 13 フィールド完全一致テスト、`DECLARED_AUDIT_EVENT_CLASSES` の内容 (11 語) が**本 WP 前後で同一**であること、両 peer の権限テスト。
13. **変異ファイルの残骸** — 新規ファイル/新規定義を使う変異の後始末。**コミット前に変異文字列そのものを全文 grep すること**。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

**3 フィールド (`event_class` / `operation` / `target_kind`) それぞれについて 1〜5 を実施し、すべて赤になることを実測する** (完了条件 4 の `event_class` 回帰確認を兼ねる)。

1. **未宣言 literal の注入** — 実 emit サイトの literal を宣言外・N 外の値へ書き換え、(e) が**赤**になること。
2. **位置引数定義** — `def probe(operation): ...` のように `<field>` を**位置引数**で受ける新規定義を追加し、(c) が**赤**になること。**この定義は必ず除去する。**
3. **IfExp 片枝に未宣言語** — 既存の三項演算 (`ops.py:655` / `:688` 相当) の片枝を宣言外・N 外の literal へ書き換え、(b′) の U 加算経由で (e) が**赤**になること。**片枝だけの変異が確実に検出される**ことを示す。
4. **同名変数へ Call 束縛** — `operation = some_call()` のように `<field>` と同名の変数へ `Call` を束縛し、(b″) / (d′) が**赤**になること。
5. **keyword passthrough** — `route_denial(..., operation=row["operation"])` 形の keyword passthrough を注入し、(b‴) が**赤**になること。
6. **除外リストの陳腐化** — `_NON_AUDIT_OPERATION_PARAMETERS` に**存在しない定義名**を 1 件足し、検証テスト (i) が**赤**になること。
7. **除外関数に仮引数転送を注入** — 除外リストに載る定義 (例 `structured.py:199` `bind_mutation`) の本体に、**その定義自身の仮引数 `operation` を `operation=operation` の形で渡す `Call`** を 1 件足し、検証テスト **(ii′)** が**赤**になること。**除外がクライアント由来値の監査面への転送を隠せないこと**の証明である。あわせて**対照**として、同じ定義の本体に `operation="mutant"` の `Constant` 渡しを足したときは **(ii′) は緑のまま**であり (これは正しい — `DataService.schema` が現に同じ形を持つ)、代わりに **(e) 等式が `"mutant"` を未宣言 literal として赤にする**ことを確認する。**この対照は (ii) → (ii′) の差し替えが U の完全性を損なわないことの実測**であり、レビュー報告に対照であることを明記する。
8. **D → N 降格** — `DECLARED_AUDIT_OPERATIONS` から 1 語を抜き、同時にその語を N へ足す (等式 (e) は緑のまま通る)。**宣言スナップショットテストが赤**になること。等式だけでは縮小を検出できないという設計の主張を実測で示す。

**復元後、変異文字列 (`probe`、`mutant` 等) を全文 grep してゼロを確認する。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-3 MitateDB-api — 走査器一般化 + 宣言 2 キー + 1.5.0 flip + guard 撤去

#### 目的

WP-2 の対称実装。あわせて `contract_version` を 1.5.0 へ flip し、**全体 vacuity guard の `xfail` を同一コミットで撤去する** — flip 自身が guard を無介助で緑にすることを示す。

**WP-2 の裁定・レビュー指摘を発注時点で織り込むこと。** ただし「織り込んだから同じ指摘は出ない」とは限らない (フェーズ4 の M-1 は対称実装で再発した)。対称実装の価値は指摘数の減少ではなく**両向きの照合**にある。

#### 変更対象

**A. 製品コード — keyword-only 化 (挙動不変、2 定義のみ)**

| 定義 | フィールド |
|---|---|
| `MitateDB-api/src/mitatedb_api/control_plane.py:1204` `_authorize_role` | `operation` |
| `MitateDB-api/src/mitatedb_api/control_plane.py:1250` `_gate_must_rotate` | `operation` |

**emit ヘルパ群は既に対称な規律を持つため対象外である** — `cell.py` の `_make_audit_hook` / `_push_data_operation_event`、`audit_dispatch.py` の `make_pre_commit_hook` / `route_denial` / `push_buffer_event` はいずれも `operation` / `target_kind` を `*` の後ろに置いている。**これらを書き換えないこと。**

**B. 製品コード — `http.py:731` のローカル変数リネーム (挙動不変)**

`operation = body.get("operation")` は「全スコープの `Assign` でターゲットが `Name(id="operation")`、値が `Call`」であり、**(d′) が捕まえる形**である。当該ローカル変数を **`schema_operation` 等へリネーム**する。`_SCHEMA_OPERATIONS` (閉じた 6 要素集合) への所属検査による門番は**そのまま**。

**(d′) に例外を置く形は採らない** — リクエスト由来値の混入を止めるという (d′) の目的そのものを削るためである。

**C. 除外リスト — `_NON_AUDIT_OPERATION_PARAMETERS` (1 定義、検証は (i) + (ii′))**

| 定義 |
|---|
| `cell.py:652` `_plan_operation` |

r2db と**同型**に、qualified 名 + 根拠コメント + 検証テスト 2 本を置く。

**D. 走査器の一般化 — `MitateDB-api/tests/test_audit_query.py`**

r2db と**同型**。既存の器 (`_collect_direct_shadow_names` `:691`、走査部 `:805`/`:828`/`:833` 近傍) をフィールド名でパラメータ化し、`event_class` も同じ器へ載せ替える。(b′)(b″)(b‴) を追加する。

- (b′) は `control_plane.py:1456` (`operation = "enable_application" if enabled else "disable_application"`) / `:1676` (`operation = "enable_credential" if enabled else "disable_credential"`) の**代入形三項演算**を閉じる。
- **(b‴) は製品変更を要さない** — MitateDB の読み出し経路も 3 フィールドすべて dict literal 形であり (`audit_query.py:147-150,161-164,371,373`)、keyword passthrough 形は**実測 0 件**である (設計 N-6)。**探す必要はない。** 見つけたと思ったら監督へ報告すること。
- **`audit_dispatch.py:624-628` の `route_denial` 内 `fields = {...}` literal と `push_buffer_event` (`:641-645`) の `ApplicationAuditEvent(...)` は書き換えない** — いずれも値が囲む keyword-only 関数の仮引数 `Name` であり (d) / (b) に対して合法である (設計 §3 D-1 の実測)。
- **`append_audit(**fields)` / `audit_dispatch.py:538` の `append(count=…, **state["fields"])` は走査対象に入らない** — これは穴ではなく、そこを流れる literal は外側の `route_denial(..., operation="…")` 呼び出しサイトで U に捕捉される。**追跡機構を足さないこと。**

**E. 宣言と D / N — 2 モジュール構成**

`event_classes` と同じく **control 側と application 側の 2 モジュール構成**を採る:

- `MitateDB-api/src/mitatedb_api/application_audit.py` — application 半分 (`DECLARED_AUDIT_EVENT_CLASSES` `:112` と同型の位置)。`__all__` (`:384` 近傍) にも足す。
- `MitateDB-api/src/mitatedb_api/audit_query.py` — control 半分 (`_CONTROL_PLANE_EVENT_CLASSES` `:58` と同型) と、両者の和を作る公開定義 (`DECLARED_AUDIT_EVENT_CLASSES` `:76` と同型)。`__all__` (`:390` 近傍) にも足す。
- `control_plane.py` の `control_capabilities` 宣言 dict (`:1373` の `"event_classes": sorted(self._audit_event_classes)` の位置) に **`"operations"` / `"target_kinds"` の 2 キーを追加**する。`:1067` / `:1090` と同じ体裁でコンストラクタ引数とフィールドを対に増やす。
- **N の初期仮説は「該当なし (N = ∅)」**である。**ただし実行時実測で確定する** — `auth.py:424` / `:431` / `:483` と `credential_store_postgres.py:423` / `:445` / `:478` / `:494` の `operation="authenticate"` / `"assert_active"`・`target_kind="credential"` が耐久表へ届くかを実測する。MitateDB では「非耐久経路が存在しないこと」の確認になる。
- **宣言スナップショットテスト 2 本** — `test_declared_audit_event_classes_change_only_deliberately` (`tests/test_audit_query.py:1328`) と同型。**2 モジュール構成なので、和を作る公開定義の内容を pin すること** (片方だけを pin して他方の変更を見逃さない形にする)。

**F. `contract_version` 1.5.0 flip + guard 撤去**

- `MitateDB-api/src/mitatedb_api/cell.py:1275` と `MitateDB-api/src/mitatedb_api/control_plane.py:1346` の 2 箇所。
- **全体 vacuity guard の `@pytest.mark.xfail(strict=True)` デコレータを削除する** — **同一コミット**で行う。先に外すことも、後から別コミットで外すことも禁じる (WP-3(b) `a3571dc` が 1.4.0 で辿った経路と同型)。

#### 完了条件 (検証可能な形)

1. **keyword-only 化 (2 定義のみ)** — `_authorize_role` / `_gate_must_rotate` の `operation` が `kwonlyargs` にあり、位置渡しの呼び出し残りが grep でゼロ。**emit ヘルパ群 (`cell.py` / `audit_dispatch.py` の 5 定義) が変わっていない**こと。
2. **`http.py:731` のリネーム** — ローカル変数が `operation` でなくなり、`_SCHEMA_OPERATIONS` の門番と dispatch 挙動が**不変**であること。**(d′) に例外を彫り込んでいない**こと。
3. **走査器が r2db と同型** — 3 フィールド 1 実装、(a)〜(e) + (b′)(b″)(b‴)。**peer 間でコードを共有していない**こと (同型の別実装であること)。
4. **`event_class` 側の性質が後退していないこと** — WP-2 完了条件 4 と同じ。変異注入で確認する。
5. **除外リスト (1 定義)** — `cell.py:652` `_plan_operation` が qualified 名 + 根拠付きで列挙され、検証テスト 2 本 (**(i) 実在性 / (ii′) 自関数の仮引数の非転送**) が存在すること。**(ii) (Constant 渡しの不在) を実装していない**こと。
5b. **(b‴) が製品変更を生んでいないこと** — 読み出し経路の書き換えが 1 件も発生していないこと (WP-2 完了条件 11 と同じ)。
6. **(e) 語彙関係の厳密一致** — 3 フィールドすべてについて `U == D ∪ N` かつ `D ∩ N == ∅`。
7. **N の実行時実測** — 上記 7 サイトについて耐久表へ届くかを**実測**し、その結果を根拠コメントに残すこと。**N が空でないなら、各要素に実測に基づく根拠が付いている**こと。空なら「非耐久経路が存在しないことを実測した」ことがテストとして残っていること。
8. **宣言の真実性** — 2 モジュールのいずれにも `audit_query` が決して返さない語彙が入っていないこと。**(e) を通すために宣言へ足していない**こと。
9. **宣言キーの露出** — `control_capabilities` の `audit_query` 宣言に `operations` / `target_kinds` が現れ、**2 モジュールの和**であること。実 HTTP 経路でも観測できること。
10. **宣言スナップショット 2 本** — 和を作る公開定義の内容を直接 pin していること。
11. **flip** — 両 plane の `contract_version` が `"1.5.0"` であり、同一コミットに挙動が入っていること。
12. **全体 vacuity guard の `xfail` 撤去が同一コミット** — `grep -n "xfail" conformance-tests/test_c09_audit_evidence.py` に 1.5.0 guard の行が残っていないこと。**guard が素で緑になる**こと (弱めて緑にしていないこと — `strict=True` の除去・全数要求の緩和・adapter 名の列挙化はいずれも禁止)。
13. **共通 suite の 1.5.0 分岐が 4 adapter 全数で走る** — C-09 vector 1 の (i)、宣言整合 vector 3 本の 1.5.0 条件付き分岐が **4 plug すべて**で実行されること。
14. **義務 (b) vector が引き続き緑** — WP-1 で無条件登録したテストが、両 peer の flip 後も同じ結果を返すこと (D-2 は挙動を変えない明確化である)。
15. **変異注入 8 種がすべて赤** — WP-2 と同じ 8 種を MitateDB で実施する (5 = keyword passthrough の**注入**、6/7 = 除外リスト 1 定義 `_plan_operation` に対して。7 の対照も同じく実施する)。
16. **完了ゲート** — root suite 単独実行で **`failed` 0 / `skipped` 0 / `xfailed` 0**、`passed` が WP-2 の値から増えていること (guard 1 本が xfailed → passed へ移る分を含む)。**増減の内訳を完了報告に書くこと。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

WP-2 の 1〜13 をすべて適用したうえで、MitateDB 固有に:

14. **転送ラッパへの追跡機構の混入** — `append_audit(**fields)` / `append(count=…, **state["fields"])` を追うための dict unpack 追跡・`self` 属性追跡・名前ベースの呼び出し照合が**足されていないか**。設計 §3 D-1 は「呼び出し地点ごとの値解決」方式を名指しで却下している (1190 行規模の解析器になり、それ自体が検証対象になる)。
15. **書き換えてはならない箇所の保全** — `audit_dispatch.py:624-628` / `:641-645`、`cell.py` / `audit_dispatch.py` の emit ヘルパ 5 定義が無傷か。
16. **`http.py:731` の処置** — リネームであってスキップ例外の追加ではないか。`_SCHEMA_OPERATIONS` の門番が無傷か。リネーム後の変数名が他の識別子と衝突していないか。
17. **2 モジュール構成の整合** — control 半分と application 半分の和が公開定義になっているか。**片方の変更が公開定義に反映されない経路**が無いか。スナップショットが和を pin しているか (片方だけを pin していないか)。
18. **N = ∅ の主張の裏付け** — 「該当なし」が実測に基づくか、単に候補を探さなかっただけでないか。7 サイトの実測結果が残っているか。
19. **guard 撤去の作法** — `xfail` の削除が**同一コミット**か。guard を弱めて緑にしていないか (`strict=True` の除去、全数要求の緩和、`registered_adapters()` 走査の名前列挙化)。
20. **peer 間のコード共有** — 走査器が共有モジュール化されていないか。両 peer の器はさらに似るが、**共有しない慣行を維持する** (設計 §10)。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

WP-2 の 1〜8 を MitateDB で実施する (3 フィールドそれぞれについて 1〜5)。加えて:

9. **guard の弱化** — 撤去した `xfail` の代わりに guard を弱める変異 (`strict=True` の除去 / 全数要求を「1 本でも通れば緑」へ / `registered_adapters()` を名前列挙へ) を入れ、**いずれも実装を真にせずに緑を得られてしまう**ことを確認したうえで復元する。**この変異は「赤になること」ではなく「緑になってしまうこと」を確認する対照**であり、レビュー報告に対照であることを明記する。

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-4 Q3 (D-3) — MitateDB の request-count limit 上限撤廃

#### 目的

`ControlPlaneLimits` の受理レンジの peer 非対称 (MitateDB のみ `[1, 200]`) を、**MitateDB 側の上限撤廃**で消す。両 peer とも「窓を広げるのは env var 1 本」になる。**契約は変えない。**

#### 変更対象

**1. `MitateDB-api/src/mitatedb_api/control_plane.py` — `ControlPlaneLimits.__post_init__`**

- `:151` の `not (1 <= value <= 200)` を **正の整数検査のみ**へ (`applications` / `credentials_per_application` / `control_requests_per_minute` / `audit_requests_per_minute` の **4 クラスすべて**)。r2db `limits.py:140-143` と対称。
- **エラー文言を直す** — `:152` の `f"{name} must be an integer in [1, 200]"` が撤廃後も残ると**嘘になる**。読み手 (AI エージェント統合者を含む) に存在しない受理域を教える。**`must be a positive integer` へ書き換える。**
- **クラス docstring (`:124-132`) を書き換える** — 「each capped at 200 (`_MAX_EXERCISABLE_LIMIT`)」「larger byte bound (unrelated to the ≤200 constraint)」の記述は撤廃後は偽になる。
- **`control_requests_per_minute > applications + 2 × credentials_per_application + 67` の関係検査 (`:153-156`) は独立に残す。**
- **`request_bytes` の別建て検査 (`:157-158`) は触らない** (本書 §2 の 5)。

**2. `MitateDB-api/tests/test_control_plane_service.py`**

- `test_limits_reject_out_of_range_values` (`:91`) の parametrize (`:84-89`) から **`201` ケース 3 件を削除**する。**`0` ケース 3 件は下限が残るので緑のまま。**
- **下限テストを 4 クラスへ揃える** — 現行の parametrize は 3 フィールドのみで `audit_requests_per_minute` が載っていない。撤廃後の「正の整数」検査は 4 クラス分あるので、`0` のケースを **4 クラス**に揃える。
- **大値受理テストを追加する** — r2db の `_GENEROUS_LIMITS` (`r2db-api/tests/test_control_http.py:57`、`applications=1_000, credentials_per_application=1_000, control_requests_per_minute=100_000`) と同型。**関係検査を同時に満たす形にする** — 3 値を揃えて上げること。
- `test_limits_reject_control_requests_per_minute_too_close_to_the_margin` (`:98`) が**緑のまま**であること。

**3. `MitateDB-api/conformance/` のコメント 2 箇所**

- `conformance_adapter_mitatedb.py:366` 近傍 — 「each <=200」を前提にした説明を更新する。
- `conformance_adapter_mitatedb_http.py:658` 近傍 — 同上。
- **構成値 `:378` (`applications=100, credentials_per_application=5, control_requests_per_minute=200`) は据え置く** (本書 §2 の 7)。

**4. `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c**

- 「受理レンジは `[1, 200]`」「引き上げは設計変更であって設定変更ではない」「この上限はこの peer 固有」という**現行の枠組みごと書き換える**。
- **運用者責任を明記する** — 「**値は運用者の責任であり、宣言にそのまま反映される**」。上限は誤設定に対する防波堤でもあり、外せばその防波堤は無くなる (`audit_requests_per_minute` に桁違いの値を置いた配備を製品コードは止めない)。これは依頼者設計原則 3「制約・制限で回避しない」に沿って**意図的に引き受ける代償**である。
- **r2db 側 runbook にも同じ運用者責任の記載を置く** (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` / `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` の該当節)。r2db は元から上限が無く、同じ責任が同じように掛かっている。

**5. `security/CONTROL_MAPPING.md` SI-08 行 (`:17`)**

- **r2db 側 cell と MitateDB 側 cell の両方**に非対称の記述があるため、**対で書き換える**。要求される安全結果 (宣言された窓が pre-auth で強制されること・control 窓と別窓であること) は**変わらない** — 変わるのは受理レンジという**実装裁量**の側である。

**6. `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`**

- **§11.1 L4-4 / L4-7(iii)** を **CLOSED** (本フェーズ WP-4、案 A) と記す。
- **§11.2 Q3** を結審 (依頼者裁定 = 案 A、実施 = 本フェーズ WP-4) と記す。

#### 完了条件 (検証可能な形)

1. **上限の消滅** — `grep -n "200" MitateDB-api/src/mitatedb_api/control_plane.py` に受理レンジとしての `200` が残っていないこと (既定値 `control_requests_per_minute: int = 200` は**据え置き**であり別物である — 混同しないこと)。
2. **4 クラスすべて** — `applications` / `credentials_per_application` / `control_requests_per_minute` / `audit_requests_per_minute` の 4 つが「正の整数」検査のみになっていること。
3. **エラー文言** — `must be a positive integer` になっており、存在しない受理域を述べる文言がコード・docstring・配備文書のいずれにも残っていないこと。
4. **関係検査の存続** — `control_requests_per_minute > applications + 2 × credentials_per_application + 67` が残り、`test_limits_reject_control_requests_per_minute_too_close_to_the_margin` が緑のまま。
5. **`201` ケースの削除** — parametrize から 3 件が消え、**`0` ケースが 4 クラスに揃っている**こと。
6. **大値受理テスト** — r2db `_GENEROUS_LIMITS` と同型の構築が実際に成功し、**関係検査を同時に満たしている**こと。
7. **conformance 構成が不変** — `conformance_adapter_mitatedb.py:378` の 3 値が変わっていないこと。**conformance suite が 4 adapter で全緑のまま**であること (C-14 vector 5 の位置算術が現行値のまま成立する)。
8. **共通 suite の `_MAX_EXERCISABLE_LIMIT` が不変** — `conformance-tests/test_c14_authority_boundary.py:142` の `200` が動いていないこと (本書 §2 の 6)。
9. **`request_bytes` に触れていないこと** — 別建て検査 (`:157-158`) と既定値 (65536) が不変。**peer 間の既定値差 (r2db 1_048_576 / MitateDB 65536) を勝手に揃えていない**こと。
10. **契約不変** — `spec/data-service-api.v1.json` が本 WP で 1 バイトも変わっていないこと。`spec/CCR_DISPOSITION.md` に新しい従属判断を起こしていないこと。
11. **配備文書** — `cloud-run-cloud-sql.md` §3.2c が書き換わり、**運用者責任の記載が両 peer の runbook にある**こと。実 DSN / パスワード / 実在ドメインが無いこと。
12. **CONTROL_MAPPING SI-08** — r2db 側・MitateDB 側の**両 cell** が対で書き換わり、要求される安全結果の記述が変わっていないこと。**主張する evidence が実在するテスト名へ解決する**こと (書いた各テスト名を grep して 1 件以上)。
13. **台帳** — PHASE4 §11.1 L4-4 / L4-7(iii) が CLOSED、§11.2 Q3 が結審として記されていること。
14. **変異注入 1 種が赤** — 下記のとおり。
15. **完了ゲート** — root suite 単独実行で **`failed` 0 / `skipped` 0 / `xfailed` 0**。**`201` ケース 3 件の削除と大値受理テスト・下限 1 ケースの追加で件数が変動する** — 増減の内訳を完了報告に書くこと。

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **既定値と受理レンジの混同** — `control_requests_per_minute: int = 200` は**既定値**であって撤廃対象の上限ではない。既定が動いていないか。
2. **関係検査の巻き添え** — 上限撤廃に引きずられて `control_requests_per_minute > applications + 2 × credentials_per_application + 67` が消えたり緩んだりしていないか。
3. **嘘の文言の残存** — 「`[1, 200]`」「capped at 200」「≤200」を述べる箇所を**全数掃討**したか。**grep 語は実表記に合わせること** — コード・docstring・conformance adapter コメント・配備文書・設計文書で表記が違う (`[1, 200]` / `capped at 200` / `≤200` / `<=200` / 日本語の「上限」)。決め打ちの 1 語で走らせない。
4. **大値受理テストの実効** — 構築が実際に成功することを見ているか。`pytest.raises` を外しただけの空振りになっていないか。関係検査を満たしていない値で「受理された」と主張していないか。
5. **下限テストの 4 クラス化** — `audit_requests_per_minute` の `0` ケースが実際に追加され、**赤になる変異で load-bearing であることを確認**したか。
6. **conformance への波及** — 構成値と `_MAX_EXERCISABLE_LIMIT` が無傷か。C-14 vector 5 が緑のままか。
7. **代償の明記** — 配備文書が「誤設定に対する防波堤が無くなる」ことを**運用者責任として正直に書いている**か。「対称化した」だけで代償を書かずに済ませていないか。
8. **契約への波及** — `spec/` が 1 バイトも変わっていないか。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

1. **上限の復活** — `__post_init__` に `[1, 200]` 検査を戻し、**大値受理テストが赤**になること。あわせて `201` を渡す構築が**受理される**ことを撤廃後のコードで確認する (受理域が実際に広がったことの実測)。
2. **下限の消滅** — 正の整数検査を落とし、**`0` ケース 4 件 (4 クラス) がすべて赤**になること。

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-5 記録整理 (最終 WP)

#### 目的

WP-1〜WP-4 で閉じた事実と、閉じないと裁定した事実の**両方**を、正本記録へ反映する。記録が実装より遅れている状態でフェーズを終えない。

#### 変更対象

**1. `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` — §10 実装記録の新設**

- `PHASE4_DURABLE_AUDIT_SINK_V1.md` **§9.4** と同じ体裁で、**§10 (実装記録)** を新設する (現行 §10 = 将来課題は §11 へ繰り下げる)。
  - **集計行の表** — WP / コミット (merge) / 集計行 (root suite、単独実行)。**集計行の出所を明記する** — 監督が単独実行して得た実測値の転記であって、起草時の再実行値ではない。
  - **WP ごとの実装記録** — 実際に採った形 (発注時の予定と食い違ったなら**実装が正**として記録する)、レビュー指摘の件数と内訳、変異注入の結果、**受理境界 (この WP で「固定しない」と決めた点)**。
  - **N の確定内容を両 peer 分記録する** — どの語が D / N のどちらになったか、N の各要素の実測に基づく根拠。設計 §1.4 の 8 の候補表と実際の確定が食い違ったなら、**設計側の候補表に訂正註を置く** (履歴を消さない)。

**2. `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`**

- **§11.1** — **L4-1** と **L4-2** に **CLOSED** (本フェーズ WP-1〜WP-3、契約 1.5.0 / 従属判断 10) を記す。L4-4 / L4-7(iii) は WP-4 が記した状態を**確認するのみ** (二重に書き換えない)。
- **§11.2** — **Q1 / Q2** を結審 (依頼者裁定 + 実施 WP + 結果) と記す。**Q3** は WP-4 が記した結審を**確認するのみ**。
- **Q4 は「本フェーズに入らない、独立の設計フェーズとして残る」と明記する** — 「対応不要」と読める書き方に化けさせない。**依頼者判断待ちの状態を保つ。**
- **L4-8 / L4-12 / L4-13 は無傷**であること (本書 §2)。

**3. `conformance-tests/CONDITIONS.md`**

- **C-09 行** — WP-1 が書いた port v1.9 / 1.5.0 分岐 / 新 vector 群の記述を、**両 peer の flip 後の実態**へ更新する (「as of WP-1 どの adapter も 1.4.0 分岐」→「4 adapter 全数が 1.5.0 分岐」)。
- **§6.1 の射程開示を置く** — 「(i)(ii) はいずれも『返された値 ⊆ 宣言』であり、**宣言の真実性の逆向き半分 — 宣言にあるが `audit_query` が決して返さない語彙 — は共通 suite では検出できない**。この半分は peer-local の (e) 等式 (`U == D ∪ N`) と N の根拠コメントだけが担う」。**限界 (b) (手書き候補集合) を置き換える先として自然である。**
- **義務 (b) vector の限界開示** — 認証面代替を使う plug がある場合、その plug 名と「alias エンドポイントではなく認証面で観測している」旨。**登録先は C-09 行のまま** (監督裁定) — WP-5 で C-14 系へ移さない。
- **限界 (a) (P4-D18 による vector 4 の射程開示) はそのまま保つ。**
- 既存行の体裁 (**実在テスト名を逐語で引く**) を崩さないこと。

**4. `security/CONTROL_MAPPING.md`**

- **SI-14 行 (`:23`)** — 宣言の真実性の機械検証が **2 フィールド分**増えたこと (これまで `event_class` にのみ掛かっていた `U == D ∪ N` / `D ∩ N == ∅` が `operation` / `target_kind` にも掛かり、共通 suite 側でも `audit_query` の返す全 event が宣言に収まることを確認できるようになったこと)。**ただし真実性の逆向き半分は共通 suite の射程外**であることも書く。監査の完全性そのもの (何を耐久記録するか) は**変わっていない**。
- **SI-00 行 (`:9`)** — D-2 の**実現手段**を書く。契約本文には安全結果側 (「data ホストは control/audit credential を認証する義務を負わない」) を書き、**store を同一プロセスに置かないという実現手段は本行の管轄**である (設計 §3 D-2 / §7)。プロセス分離は SI-00 の安全結果を得るための control の 1 つにすぎず、同じ結果を別の control で得る実装を締め出さない。
- **SI-08 行 (`:17`)** — WP-4 が書いた内容を**確認するのみ** (二重に書き換えない)。
- **主張する evidence は必ず実在するテスト名へ解決すること。** テスト名を書いたら、その名前で grep して 1 件以上出ることを確認する。

**5. 両 peer の runbook / 配備文書の宣言例**

- `docs/work-orders/DEPLOY_PHASE4_20260903.md` **§4-1** (`:380-382`) — 合格条件が `capabilities.contract_version == "1.4.0"` と `event_classes` が空でない配列であることを述べている。**1.5.0 と新キー 2 本 (`operations` / `target_kinds` が空でない配列であること) を含む形へ更新する。**
- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` / `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15 / `MitateDB-api/docs/cloud-run-cloud-sql.md` — `audit_query` の宣言例・検証手順に `contract_version` と `event_classes` を書いている箇所を洗い出し、**1.5.0 と新キー 2 本を含む形へ更新する**。
- **grep 語は実表記に合わせること** — 文書によって言語も語彙も違う。担当は**まず grep で実表記を確認**してから掃討対象を確定する。決め打ちの 1 語で走らせない。

**6. ハンドオーバー**

- `docs/work-orders/HANDOVER_20260903_FABLE2.md` (第11次) の後継として**第12次**を起こす。既存ハンドオーバーの体裁に従い、最終集計行・各 WP のコミット・**依頼者の次の判断事項** (Q4、1.5.0 のクライアント通知可否、1.4.0 alias の除去) を明記する。
- **1.4.0 のクライアント通知は送らないと依頼者が決定済み**である (2026-09-03)。**1.5.0 の通知可否は本設計の対象外**であり、依頼者判断事項として残す。

**7. 本書 §10 (実施記録)**

- 各 WP の完了日・コミット (merge)・root suite の集計行 (単独実行の実測値)・分割の有無を表で記録する。先行作業指示書 §9 と同じ体裁。

#### 完了条件 (検証可能な形)

1. **設計 §10 実装記録** — 5 つの WP すべてについて、コミット・集計行・実際に採った形・レビュー指摘の内訳・変異注入の結果・受理境界が記録されていること。**集計行の出所が明記されている**こと。
2. **N の確定内容** — 両 peer の D / N が記録され、N の各要素に**実測に基づく根拠**が付いていること。設計 §1.4 の 8 の候補表と食い違うなら訂正註があること (履歴を消していないこと)。
3. **PHASE4 §11.1 / §11.2** — L4-1 / L4-2 が CLOSED、Q1 / Q2 が結審。**L4-4 / L4-7(iii) / Q3 は WP-4 が記した状態のままで二重書き換えが無い**こと。**Q4 が「依頼者判断待ち / 独立フェーズ」として保たれている**こと。**L4-8 / L4-12 / L4-13 が無傷**であること。
4. **CONDITIONS.md** — C-09 行が 4 adapter 全数の 1.5.0 分岐を述べ、**射程開示 (逆向き半分は共通 suite の射程外)** と **義務 (b) vector の限界開示**があり、**限界 (a) が無傷**であること。`./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py` のマーカー/行対応が**双方向で緑**。
5. **CONTROL_MAPPING** — SI-14 に 2 フィールド分の機械検証と**射程外の半分**が書かれ、SI-00 に D-2 の**実現手段**が書かれていること。SI-08 は WP-4 の内容のまま。**すべての evidence テスト名が grep で 1 件以上に解決する**こと。
6. **宣言例の全数更新** — `contract_version` と `audit_query` の宣言例を持つ配備文書・runbook が**すべて** 1.5.0 と新キー 2 本を含む形になっていること。**grep で実表記を確認したうえでの掃討**であること。
7. **陳腐化した prose の全数掃討** — 以下の主張を述べている箇所を grep で洗い出し、**すべて実態へ更新する**こと。
   - 「`operation` / `target_kind` は宣言語彙ではない」「共通 suite は手書きの候補集合で相関している」
   - 「義務 (b) がどちらのホストに掛かるかは一意に読めない」「この経路を実測するテストは共通・peer とも存在しない」
   - 「MitateDB の受理レンジは `[1, 200]`」「窓の広げ方が peer で違う」
   - 「契約は 1.4.0」(peer の宣言・配備文書の検証手順・ハンドオーバー)
8. **ハンドオーバー第12次** — 最終集計行・各 WP のコミット・依頼者の次の判断事項が明記されていること。
9. **正直さの後退がないこと** — 「CLOSED」の主張が、実際には片方の peer でしか閉じていない状態を覆い隠していないか。範囲外項目が「対応不要」と読める書き方に化けていないか (**依頼者判断待ちである**)。
10. **秘密の非混入** — 追記した全箇所に実値の DSN / パスワード / 実在ドメイン / 実データが無いこと。
11. **root suite の最終実測** (単独実行) の集計行を本書 §10 に記録すること。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 6 = 受け入れ監査)

1. **記録と実装の乖離** — CONTROL_MAPPING / CONDITIONS / 設計 §10 / PHASE4 §11 が主張する evidence が、実在し実際に走るテストへ解決するか。**WP-1〜4 で採ったテスト名と、本書の完了条件に書いた予定名が食い違っていないか** (食い違うなら**記録側を実装に合わせる** — 先行作業指示書 §5 の表が起こした食い違いを繰り返さない)。
2. **正直さの後退** — 「宣言整合を共通 suite が見るようになった」という記述が、**逆向き半分は見ていない**という事実を覆い隠していないか。義務 (b) vector の認証面代替が限界として開示されているか。
3. **射程開示の実効** — CONDITIONS.md の射程開示が、「(e) 等式と N の根拠コメントだけが担う」という**責任の所在**を具体的に (peer-local のどのテストが担うか) 述べているか。
4. **範囲外項目の扱い** — Q4 / L4-8 / L4-12 / L4-13 / 1.4.0 alias の除去が、「対応不要」ではなく**依頼者判断待ち / 将来課題**として保たれているか。
5. **代償の記録** — WP-4 の上限撤廃が引き受けた代償 (誤設定の防波堤が無くなる) が、両 peer の runbook に**運用者責任として**書かれているか。「対称化した」だけの記述に化けていないか。
6. **台帳の取りこぼし** — WP-1〜4 のレビュー・受け入れ監査で「本書では扱わない」と裁定された項目が、すべて PHASE4 §11.1 または設計 §11 (将来課題) へ落ちているか。とくに設計 §10 が挙げた将来課題 (`_NON_AUDIT_<FIELD>_PARAMETERS` の保守、走査器の peer 内コピー、`request_bytes` の検査ループ位置の非対称) が保たれているか。

#### 使用テンプレート

起草 = Opus (テンプレ 4 = 文書起草)。受け入れ監査 = Opus (テンプレ 6)。

---

## 5. 期待される実測値

| WP | 期待される変化 |
|---|---|
| **基準値** | **1545 passed / 0 failed / 0 skipped / 0 xfailed** (2026-09-03、フェーズ4 台帳消化 完了時点)。conformance **404 passed** |
| **WP-1** | 共通 vector の新規分。**共通テストは 4 adapter でパラメータ化される**ため、テスト関数 1 本が収集 4 件になる — 宣言整合 vector 3 本 × 4 = 12、義務 (b) vector 1 本 × 4 = 4 → **+16 passed** が見積り。加えて全体 vacuity guard 1 本 (**非 parametrize の registry 走査**、既存 `test_c09_every_control_surface_adapter_takes_the_provided_branch` と同形) が **xfailed 1** (収集 1 件)。C-09 vector 1 の 1.5.0 分岐は既存テスト内の分岐であり収集件数を増やさない。**期待: 約 1561 passed / 0 / 0 / xfailed 1**、conformance 約 420 passed / xfailed 1。**load-bearing の内訳**: `event_class` の宣言整合 vector (4 件) は **1.4.0 条件付きなので本 WP から実観測を伴う**。`operation` / `target_kind` の 2 本 (8 件) と vector 1 の (i) は 1.5.0 条件付きなので本 WP では分岐を素通りする (WP-2 で r2db 2 plug、WP-3 で 4 plug 全数が通る)。義務 (b) vector (4 件) は無条件なので本 WP から実観測を伴う |
| **WP-2** | r2db の走査器一般化 (3 フィールド化) + 除外リスト検証 2 本 ((i) / (ii′)) + 宣言スナップショット 2 本 + N の実行時実測。**一般化は既存テストのパラメータ化を伴うため単純な純増にならない** — 判定は「`passed` が WP-1 の値から増えていること」+ **増減内訳の報告**による。共通側では `operation` / `target_kind` の宣言整合 vector と vector 1 (i) が **r2db の 2 plug で初めて分岐へ入る** (収集件数は増えないが観測が増える)。**xfailed 1 のまま** |
| **WP-3** | MitateDB について WP-2 と同型。加えて **guard 1 本が xfailed → passed へ移る** (`+1 passed / -1 xfailed`)。**xfailed 0** |
| **WP-4** | `201` ケース **3 件削除**、`0` ケース **1 件追加** (4 クラス化)、大値受理テスト **1 本以上追加** → **差引ほぼ横ばい〜微減もありうる**。判定は増減内訳の報告による。**xfailed 0** |
| **WP-5** | 文書のみ (件数不変) |

**本数は「テスト関数数」ではなく「収集された test id 数」で数える** — 共通 suite は 4 adapter で、r2db の一部テストは `(kind, platform)` でパラメータ化されている。上表の本数は**見積り**であり、集計行との突き合わせは収集件数で行うこと。**見積りと実測が食い違ったら、実測が正であり、食い違いの理由を完了報告に書くこと。**

**完了ゲートの判定**: 各 WP で root suite を単独実行し、`failed` / `skipped` が **0**、`xfailed` が上表の期待値と一致し、`passed` (収集件数) の増減内訳が説明されていること。**xfailed が想定と違う値なら完了と判定しない。**

**conformance suite**: WP-1 で **404 → 約 420 passed / xfailed 1** へ増える (port v1.9 と新 vector)。WP-3 で xfailed が 0 になる。WP-2 / WP-4 では**不変**である。

---

## 6. 完了ゲートの実測規律 (全 WP 共通。先行作業指示書 §4 / §6 を継承)

- 完了ゲートの root suite は**リポジトリルートで単独実行する**。他の pytest プロセスが走っていないことを確認してから実行する — **PG クラスタの並走衝突で偽の赤が出る** (フェーズ3.5 で 2 回発生)。
- **テストは前景で実行する。`timeout` を明示すること (600000 ms)。** root suite は長時間かかる。
- 実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない** — skip が出ていたら環境の問題として解決してから完了と判定する。
- 各 WP の完了報告に **集計行 (passed / failed / skipped / xfailed)** を必ず記録し、**増分の内訳** (どのテストが何本増えたか / 減ったか / 差引) を書く。
- **変異注入は scratchpad へ復元する。`git checkout` は使わない** (フェーズ4 で実装者の変更を一度消した事故がある)。
  - **本リポジトリは Google Drive 同期ツリーである。** 変異前に対象ファイルを scratchpad へ backup し、**復元後に `sha256` で二重照合する** (backup と復元後の一致を 2 回確認する) — 同期が復元を巻き戻す事故を防ぐ。
  - **コミット前に変異文字列そのものを全文 grep する** (差分の一致確認は「消えていないこと」しか保証しない)。

---

## 7. 禁止事項 (全 WP 共通)

1. **git commit / push は監督のみが行う**。Sonnet も Opus もコミットしない。
2. **契約ファイルを変更するコミット (WP-1) は依頼者確認後に行う** (設計 §2 の 8)。契約の英文の**最終文言は依頼者確定待ち**であり、実装者は監督から確定文言を受け取ってから spec を書く。確定前に spec を書いてコミット可能な状態にしない。
3. **WP-1 以外で `spec/` を変えない**。WP-2 / WP-3 は peer の宣言と `contract_version` のみ、WP-4 / WP-5 は契約に触れない。`r2db-api/src/r2db_api/contract/data-service-api.v1.json` (packaged copy) も同様。
4. **peer 間でコードを共有しない**。走査器の一般化は両 peer 同型の**別実装**であり、共有モジュールを作らない (既存の慣行、設計 §2 の 7 / §10)。
5. **偽の flip を行わない** — 宣言を真にする挙動が同一コミットに無いまま `contract_version: 1.5.0` を宣言しない。逆に、1.5.0 の挙動を出荷しながら 1.4.0 を宣言し続けることも禁じる。**過渡期 (WP-1 完了〜各 peer の flip まで) に peer が 1.4.0 を宣言し続けるのは正しい lag であって非適合ではない。**
6. **guard を弱めて緑にしない** — 全体 vacuity guard の `strict=True` を落とす、全数要求を「1 本でも通れば緑」へ緩める、`registered_adapters()` 走査を adapter 名の列挙へ退化させる、個別 guard に xfail を付ける、宣言真実性テストから不適合分類の検査を外す、のいずれも禁じる。**緑にする正しい手段は実装を真にすることだけである。** `xfail` を外すのは **WP-3 の flip コミットのみ**。
7. **宣言に非耐久語彙を足さない** — (e) 等式 `U == D ∪ N` を通すために `DECLARED_AUDIT_OPERATIONS` / `DECLARED_AUDIT_TARGET_KINDS` / `DECLARED_AUDIT_EVENT_CLASSES` へ非耐久語彙を足すことを禁じる。`audit_query` が決して返さない語彙を公開するのは嘘である (P4-D16 v3 (e) / 設計 §2 の 5)。**正しい手段は N への名指しの列挙と実測に基づく根拠コメントである。**
8. **走査に例外を彫り込んで回避しない** (依頼者設計原則 3)。`http.py:731` は (d′) の例外ではなく**リネーム**で閉じる。除外リストは「名前が同じだけの別概念」を外すためのものであり、**除外された定義でも (b) 側の literal 収集 (U への加算) と (ii′) の転送禁止は掛かり続ける**構造を保つ (免ずるのは (c) の keyword-only 要求だけである)。
9. **callee 名フィルタを再導入しない** — 走査が callee 名の集合 (allowlist / denylist / 接頭辞判定) を再導入した時点で、「人が名前集合を維持し続ける」という L4-5 の元の欠陥へ戻る。**定義集合を作って callee 名と突き合わせる形 (P4-D16 v2) は撤回済み**であり、復活させてはならない。
10. **呼び出し地点ごとの値解決方式を採らない** — dict unpack 追跡・`self` 属性追跡・名前ベースの呼び出し照合を足さない。設計 §3 D-1 が「テストに載せて長く保守できる形ではなく、それ自体が検証対象になってしまう」として名指しで却下している。
11. **範囲外項目に触れない** (§2) — Q4 / L4-8 (vector 4 の射程開示) / L4-12 / L4-13 / 1.4.0 alias の除去 / `request_bytes` の検査ループ位置の非対称 / 共通 suite の `_MAX_EXERCISABLE_LIMIT` / conformance adapter の構成値。「ついでに」直さない。
12. **peer 間の既定値を勝手に揃えない** — `request_bytes` の既定 (r2db 1_048_576 / MitateDB 65536) は**据え置くと裁定済み**である。WP-4 が撤廃するのは受理レンジであって既定値ではない。
13. **既存テストを緩めない** — とくに `test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth`、`control_audit` の 13 フィールド完全一致テスト、両 peer の権限テスト、`DECLARED_AUDIT_EVENT_CLASSES` の内容 (r2db 11 語 / MitateDB 12 語) を pin するスナップショット、1.4.0 の guard 2 本。
14. **制約・制限の追加で問題を回避しない** (依頼者設計原則 3)。新しい上限・拒否経路・機能制限を、難所を回避するために足さない。
15. **migration の in-place 編集を禁じる**。本書は migration を一切要求しない。必要に見えたら差し戻す。
16. **秘密・実データ・実在ドメインを書かない**。環境変数名・secret-manager 参照・架空ドメイン・合成 fixture のみ。**公開リポジトリである。**
17. **テストの並行実行を禁じる**。完了ゲートは単独実行する。
18. **変異ファイル・変異定義を残さない**。変異は必ず除去し、**scratchpad backup + sha256 二重照合**で復元を確認し、**コミット前に変異文字列を全文 grep する**。

---

## 8. コミット規律

- **WP ごとに 1 コミット** (WP-1 / WP-2 / WP-3 / WP-4 / WP-5 で計 5 コミット)。それ以外の分割は監督の許可を要する。
- **flip は挙動出荷コミットに束縛する** — `contract_version` 1.5.0 の宣言と、それを真にする挙動 (宣言 2 キー + 走査器 + D/N) は**同一コミット**。版数を固定しているローカルテストの更新、および **WP-3 における全体 vacuity guard の `xfail` 削除**も同一コミット。契約 1.5.0 の公開 (WP-1) と peer の flip (WP-2 / WP-3) が別コミットであることは `version_binding` 規律どおりである。
- **契約変更コミット (WP-1) は依頼者確認後**である。監督が確定文言を依頼者へ明示し、確定を得てからコミットする。
- **identity は `r2fish` / noreply**。実名・Gmail を使わない。**コミット前に必ず `git log --format='%an <%ae>'` で確認する**。
- **commit → push → main merge (`--no-ff`) は 1 セット**。コミットしたら直ちに push し、main へマージする。分離しない。
- コミットメッセージは日本語可。WP 番号・変更の要旨・完了ゲートの集計行を含める。
- 各コミットの前に、独立レビュー (Opus、変異注入込み) と受け入れ監査の往復が完了していること。

---

## 9. 使用テンプレートの対応

| WP | 実装 | レビュー | 監査 |
|---|---|---|---|
| WP-1 | Sonnet テンプレ 2 (実装) | Opus テンプレ 5 (コードレビュー、変異注入必須) | Opus テンプレ 6 (受け入れ監査) |
| WP-2 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-3 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-4 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-5 | Opus テンプレ 4 (文書起草) | — | Opus テンプレ 6 |

テンプレートの本文は `~/.claude/.../memory/role-prompt-templates.md` が正本。各発注時に、当該 WP の「レビューが必ず探すべき点」と「変異注入」の節をテンプレートへ差し込むこと。

**subagent への発注時の規律** (体制メモの load-shift に従う): 報告は短く上限を切り、**raw 出力は scratchpad のファイルへ**書かせる。長時間の suite は前景実行とし、`timeout` を明示する (600000 ms)。

---

## 10. 実施記録

(WP-5 で記入する。体裁は先行作業指示書 §9 / §10 に従う — WP / 完了日 / コミット (merge) / 集計行 (root suite、単独実行) / 分割の有無。)
