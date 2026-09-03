# フェーズ5 実施設計: 契約 1.5.0 (監査語彙の宣言化 + 無条件義務 (b) の適用範囲) + request-count limit 受理レンジの対称化

- 版数: **v1.3 (2026-09-03、再レビュー N-1〜N-7 反映)** — 2 回目の独立レビュー (`scratchpad/review-design-150-r2.md`) の新規指摘 7 件を全件裁定・反映。主要な変更: **除外リストの検証条件 (ii) を (ii′) へ差し替えた** (N-1 — r2db `DataService.schema` は**除外必須でありながら監査 literal を運ぶ**ため、v1.2 の「監査 literal を運ぶ定義は除外できない構造」は現行コードに反証された)、**起草英文の `never accepted or forwarded` を許容形へ** (N-2 — `forwarded` の禁止は 1.4.0 条件付き義務 (5) を分離配備で満たす転送実装を遡って非適合にする)、**補筆第 1 文に `endpoints.audit_query.deprecation_note` の host scoping と義務 (5) への参照を追加** (N-3)、**従属判断 10 の additive 根拠に両 peer の control ホスト alias 同一ハンドラの実測を追加** (N-4)、(b‴) の許容位置を添字代入・属性代入まで明記 (N-5)、**(b‴) の導入に製品変更は不要** (実測 0 件、N-6)、**`event_class` の返却 vector は 1.4.0 条件付き**で §6.1 と §9 を統一 (N-7)
- 旧 v1.2 (2026-09-03、独立レビュー全件反映) — レビュー (`scratchpad/review-design-150.md`、重大 6 / 中 8 / 小 5) を全件裁定・反映。主要な変更: **(c) を「無差別 + 名指し除外リスト」形へ改めた** (A-1 — 規則 (c) は名前ベースなので、監査と無関係な `operation` 仮引数 9 定義を巻き込む。「keyword-only 化の対象が全数」は誤りだった)、**`http.py:731` は (d′) 違反として実際に検出される** ため変数リネームを WP-3 の製品変更として明記 (A-2)、**`Subscript` passthrough をキーワード引数値では禁止** しリクエスト由来値の逃げ道を構文で閉じた (A-3)、**D-2 を「1.4.0 の同ラベル改訂」へ変更**し起草英文を許容形へ落とした (B-1 / B-2 / B-3 — 義務形の `AUTH_INVALID` は `control_discovery` の co-hosting 容認を狭め additive 性を崩す)、**N の判定基準を両 peer 共通で静的に定義** (A-6)、**port v1.9 は data ホストの alias ハンドラ自体へ提示する形を要求** し到達できない plug は限界開示 (C-1 / C-2 / C-3)、**「conformance は小さい値」は事実誤り**を訂正 (D-1)、その他 A-4 / A-5 / B-4 / B-5 / D-2 / E-1 / E-2 / C-4 をレビューの修正提案どおり反映
- 旧 v1.1 (2026-09-03、監督裁定を反映) — 走査器プロトタイプ (`scratchpad/vocab_scanner_proto.py`、出力 `vocab_scan_r2db.out` / `vocab_scan_mitate.out`) の実測を踏まえ、**D-1 の走査器の方式を確定** (「呼び出し地点ごとの値解決」方式は採らず、**P4-D16 v3 (a)〜(e) の大域不変量方式をフィールド名でパラメータ化**し 2 規則だけ足す)。keyword-only 化の対象を実測で名指し (§3 D-1)、語彙規模の実測を記録 (§1.4 の 8)、`event_class` にも同じ共通宣言整合 vector を足すことを明記 (§6.1)、port v1.9 の in-process 実装方針を明記 (§6.2)、`request_bytes` の検査ループ位置の非対称を将来課題へ追加 (§10)
- 旧 v1.0 (2026-09-03、初版)
- 位置づけ: `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 が「依頼者判断待ち」として集約した Q1〜Q5 のうち、**2026-09-03 に依頼者が裁定した Q1・Q2・Q3 の実施設計**である。Q1 (台帳 L4-1) と Q2 (台帳 L4-2) は**一括で契約 1.5.0** として出荷し (Q5 = 一括、従属判断 8 → 9 の前例踏襲)、Q3 (台帳 L4-4 / L4-7(iii)) は**案 A (MitateDB の上限撤廃)** を採る。Q4 (`visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合) は本フェーズに**入らない** — §11.2 Q4 の監督推奨どおり独立の設計フェーズとして残る
- 契約版の前提: **契約 1.4.0 は公開済み**であり (`spec/CCR_DISPOSITION.md` 従属判断 9、両 peer とも `contract_version` 1.4.0 を宣言済み)、契約に手を入れる以上は版を上げる。本フェーズの契約版は **1.5.0**。**1.4.0 のクライアント通知は送らないと依頼者が決定済み** (2026-09-03) であり、1.5.0 の通知可否は本設計の対象外
- 体制: Fable 監督/設計/コミット、Opus 起草/独立レビュー/受け入れ監査、Sonnet 実装 (コミットしない)。完了条件・単一コミット規律・identity 確認は既存フェーズと同一
- 本文書の性格: **監督が確定した枠の実施設計**である。§3 の D-1〜D-4 は依頼者裁定 (Q1・Q2・Q3) を受けた確定であり、§5 に挙げるもの (**契約の英文の最終文言**) のみが依頼者確定待ちである。WP 分割は §9 に概略のみを置き、作業指示書は別途起こす

---

## 1. 問題設定

### 1.1 `operation` / `target_kind` が宣言語彙になっていない (Q1 / 台帳 L4-1)

契約 `audit.fields` は `operation` と `target_kind` を監査イベントのフィールドとして 1.3.0 以前から列挙しているが、**その値の語彙は契約にも宣言にも存在しない**。`event_class` は 1.4.0 (従属判断 9 項目 4、設計 D-7) で「各実装が `capabilities().audit_query.event_classes` に宣言する語彙」になったのに対し、`operation` / `target_kind` は宣言キーを持たない。

帰結は共通 suite に直接現れている。C-09 vector 1 (`conformance-tests/test_c09_audit_evidence.py::test_c09_v1_fail_closed_events_are_observable_through_audit_query`) は、破壊的操作の耐久行を同定するために候補集合を**手で列挙**している:

- `_LIKELY_DESTRUCTIVE_OPERATIONS = frozenset({"delete", "mutate"})` (同ファイル L143)
- `_LIKELY_DESTRUCTIVE_TARGET_KINDS = frozenset({"entity", "collection"})` (同 L161)

いずれも「明示的に不確実性を開示した候補集合」としてコメントと `conformance-tests/CONDITIONS.md` の C-09 行 (限界 (b)) に開示済みだが、**宣言と機械的に結ばれていない**以上、peer が自分の語彙の綴りを変えても共通 suite は気付かない。両 peer の実語彙は実際に食い違っている — r2db はあらゆるデータ変更を `mutate` / `entity` の 1 組へ畳み、MitateDB は個々の操作名を出し target を `collection` と呼ぶ (`security/CONTROL_MAPPING.md` SI-14 行の点 (13) に両者の全語彙を併記済み)。

### 1.2 契約 1.4.0 無条件義務 (b) の適用範囲が一意に読めない (Q2 / 台帳 L4-2)

契約 `versioning.version_binding` の 1.4.0 無条件義務 (b) は「control surface が提供されている限り (`control_plane` が `unavailable` でない限り)、audit role の credential が `audit_query` control endpoint でも受理される」と書く。ところが両 peer の **data-plane ホストは `control_plane: enabled` を宣言しつつ control credential store を構造的に持たない** (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §1.5 — data-plane プロセスは control credential を検証できない)。そのため data ホストの `/v1/audit/query` alias に control/audit credential を提示すると `AUTH_INVALID` になる。

義務 (b) を「**control surface の control endpoint に掛かる**」と読めば両 peer は適合、「**capabilities 文書を出すそのホストに掛かる**」と読めば不適合である。**現在は前者の読みで両 peer とも受理されている**が、契約文言はそれを一意に言っていない。加えて、この経路 (control credential × data ホスト) を実測するテストは**共通・peer とも存在しない** — 現行の近縁テストはいずれも application credential を data ホストへ提示する形であり、別種の検証である。

### 1.3 request-count limit の受理レンジが peer 非対称 (Q3 / 台帳 L4-4 / L4-7(iii))

`ControlPlaneLimits` の受理レンジが peer で違う。

- **MitateDB**: `ControlPlaneLimits.__post_init__` (`MitateDB-api/src/mitatedb_api/control_plane.py`) が `applications` / `credentials_per_application` / `control_requests_per_minute` / `audit_requests_per_minute` の **4 クラスすべてに `[1, 200]`** を課す。
- **r2db**: `ControlPlaneLimits.__post_init__` (`r2db-api/src/r2db_api/limits.py:140-143`) は全フィールドについて「正の整数であること」しか検査せず、**上限を持たない**。

契約は本クラスに数値レンジを宣言していない (`spec/data-service-api.v1.json:254-255` — `audit_requests_per_minute_note` が定めるのは pre-auth であること・`control_requests_per_minute` と別窓であることだけ) ので**双方適合**であり、CLAUDE.md の「同じ安全結果を与えるなら platform-specific control は peer 間で異なってよい」に該当する開示済み非対称である。だが運用者から見ると、監査エージェント増加や障害復旧後の cursor 追い付きで窓を広げる必要が生じたとき、**r2db は設定変更 (env var) で済み、MitateDB はコード変更になる**。

### 1.4 起草時に実測した前提 (探索結果 + 走査器プロトタイプ)

本設計は下記の実測に立つ。1〜7 は本フェーズ着手前の読み取り、8 は走査器プロトタイプ (`scratchpad/vocab_scanner_proto.py`) を両 peer に掛けた結果である。実装時に食い違えば設計側を訂正する。

1. **走査器の構造的盲点 (r2db に多い)**。`event_class` の AST 走査 (P4-D16 v3) が無矛盾に閉じるのは、両 peer のあらゆる audit emit 署名が `event_class` を **keyword-only** で宣言しているからである。`operation` / `target_kind` にはこの保証が無い — 代表例が `r2db-api/src/r2db_api/service.py:1139` の `_event` と `:1383` の `_control_event` で、両フィールドを positional-or-keyword で取り、**全呼び出し (計 20 箇所超) が位置渡し**である。keyword-only 前提の走査器をそのまま流用すると、この 20 箇所超が**すべて不可視**になる。実測した対象の全数は §3 D-1 に列挙する (r2db 5 定義 + MitateDB 2 定義)。
2. **MitateDB の emit ヘルパは既に対称な規律を持つ**。`cell.py` の `_make_audit_hook` / `_push_data_operation_event`、`audit_dispatch.py` の `make_pre_commit_hook` / `route_denial` / `push_buffer_event` はいずれも `operation` / `target_kind` を `*` の後ろに置いている。残る 2 定義 (`control_plane.py` の `_authorize_role` / `_gate_must_rotate`) だけが positional-or-keyword である。
3. **走査器の表現力不足 (両 peer 共通)**。現行の転送解決器は「**直近の**囲む関数の仮引数である `Name`」しか安全な転送と認めず、また `IfExp` を literal 寄与として認識しない。現実に当たる箇所は r2db `control_plane.py:846` / `:1070` (closure 捕捉)、r2db `ops.py:655` / `:688` (キーワード値そのものが inline の三項演算)、MitateDB `control_plane.py:1456` / `:1676` (三項演算をローカルへ代入してから転送) である。
4. **語彙はすべて静的に閉じる (安全性の側)**。上記 4 種の非 literal 経路を人手で追跡した結果、**両 peer の `operation` / `target_kind` の emit site は keyword 渡し・位置渡しを問わず、すべて有限の literal 集合へ閉じる**。リクエスト由来の文字列が耐久列へ未検証で到達する経路は無い。唯一の候補である MitateDB `http.py:731` の `body.get("operation")` は閉じた 6 要素集合 `_SCHEMA_OPERATIONS` への所属検査で門番され、かつ **audit 呼び出しへ転送されない** (Python レベルの dispatch キーにしか使われない)。**これは安全性の話であって、走査器がその行に反応するかどうかとは別の論点である** — 走査器の側では `http.py:731` は (d′) 違反として実際に検出される (§3 D-1)。
5. **`200` の由来は本番の安全性質ではない**。MitateDB の `[1, 200]` は `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` R-6 が **conformance C-14 vector 5 の位置算術が成り立つ範囲として逆算した** sanity bound であり、Cloud Run / Cloud SQL 側の資源制約に由来しない。現に MitateDB の conformance adapter 構成は `control_requests_per_minute=200` と**この天井ちょうど**を使っている (§6.4)。
6. **赤化するテストは 1 本 3 ケースのみ**。上限撤廃で赤くなるのは `MitateDB-api/tests/test_control_plane_service.py` の `test_limits_reject_out_of_range_values` の `201` ケース 3 件だけである (`0` ケース 3 件は下限が残るので緑のまま)。`control_requests_per_minute > applications + 2 × credentials_per_application + 67` の関係検査とその専用テストは上限とは無関係に残る。
7. **port は D-1 のためには変更不要**。`conformance-tests/adapter.py` の `ConformanceAdapter.control_capabilities(actor)` (:852) が既に capability document を返し、C-09 の `_audit_query_declaration` (`test_c09_audit_evidence.py:211`) が `event_classes` と同じ経路で `audit_query` の宣言を読んでいる。新しい宣言キーはこの既存経路にそのまま乗る。一方 D-2 は port に新メソッドを要する (§6.2)。
8. **語彙の規模 (プロトタイプ実測、D の初期値の根拠)**。フィールド名をパラメータ化した走査器を両 peer に掛けた結果:

   | peer | フィールド | 検出 site 数 | 語彙 U | N 候補 |
   |---|---|---|---|---|
   | r2db | `operation` | 89 | **31 語** | **8 語** (`_control_event` / `_event("authenticate")` 経由: `authenticate`, `delete_audit`, `disable_application`, `enable_application`, `issue_credential`, `register_application`, `set_authorization_state_available`, `set_credential_state`) |
   | r2db | `target_kind` | 53 | **6 語** | `application_or_credential` (`_control_event` 専用) |
   | MitateDB | `operation` | 81 | **30 語** | 現時点で候補なし |
   | MitateDB | `target_kind` | 46 | **5 語** | 現時点で候補なし |

   r2db の N 候補 8 語は「非耐久経路にも現れる」語であって「非耐久経路にしか現れない」語ではない — **同じ語が durable 経路にも現れるものは D に入り、N からは外れる** (`D ∩ N == ∅` の規則が両立を許さない)。とくに `enable_application` / `disable_application` は `control_plane.py:846` の `_write_state_audit` 経路で**耐久**に現れるため **D 側である**。N の確定基準は §3 D-1 に両 peer 共通で定義する。

   **`unresolved` について (根拠の訂正)**: プロトタイプ (呼び出し地点解決方式) は MitateDB について `audit_dispatch.py:538` の `**state["fields"]` を **3 フィールドとも `unresolved` として報告する**。ただし**採用する大域不変量方式ではこの転送は走査対象外**であり、そこを流れる literal は外側の `route_denial(..., operation=…)` 呼び出しサイトで U に捕捉される (§3 D-1「大域不変量方式の要点」)。したがって結論 (未解決の非 literal 経路は残らない) は変わらないが、その根拠は「`unresolved` が 0 件だから」ではない。

---

## 2. 制約 (守るべき条件)

1. **契約変更は必ず版を上げる**。1.4.0 は main へ merge 済み・公開済みであり、据え置きの余地は無い。本フェーズの契約版は 1.5.0 である。
2. **`versioning.version_binding` の版束縛規律**。peer の `contract_version` flip は、それが主張する挙動変更と**同一コミット**に落ちる。宣言が先行することも、挙動が先行することも非適合である。
3. **1.4.0 を宣言し続ける実装に 1.5.0 の義務を遡及させない**。1.5.0 が導入する義務は 1.5.0 以上を宣言する実装にのみ掛かる (「Since X.Y.Z」の逐条積み上げ書式)。
4. **D-7 を保つ — 共通語彙へ統一しない**。`event_class` と同じく、`operation` / `target_kind` も**各実装が宣言する語彙**とし、契約に enum を作らない (declare-the-hazard)。両 peer の出荷済み語彙と `control_audit` / `application_audit` に既に入っている行を「契約不適合な過去の証拠」にしない。
5. **宣言の真実性 — 非耐久語彙を宣言へ足さない**。P4-D16 v3 (e) の禁止条件はそのまま新 2 フィールドにも掛かる。`audit_query` が決して返さない語彙を公開するのは嘘である。
6. **SI-00 の分離を保つ**。application credential の store と control credential の store を同一プロセスに置かない。data-plane プロセスが control credential を検証できないという構造は前提であって欠陥ではない。
7. **peer 間でコードを共有しない**。走査器の一般化は両 peer 同型の**別実装**であり、共有モジュールを作らない (既存の慣行)。
8. **契約ファイルを変更するコミットの直前に監督が依頼者へ再度明示する** (P4-D4 の手続き上の注意を踏襲)。
9. **公開リポジトリ規律**。実 credential・実 DSN・実ホスト名を文書にもテストにも置かない。

---

## 3. 決定と根拠

### D-1 (Q1) `operation` / `target_kind` を宣言語彙にする — 契約 1.5.0、条件付き義務

**決定**: `capabilities().audit_query` に **`operations`** と **`target_kinds`** の 2 キーを追加する。命名は既存の `event_classes` に揃える (複数形の裸の配列)。値は**その実装が宣言する語彙**であり、**契約は enum を持たない** — `event_class` と同じ declare-the-hazard の姿勢である。

**キー名の曖昧解消 (必須、v1.2)**: 契約は既に `capability_status.defined.atomic_mutation` で **`operations`** を「その capability の batch 実行面が実行する mutation 語彙」の意味で使っている。同じ綴りのキーが `capabilities().<cap>` の位置に 2 つの意味で現れるため、宣言を機械的に読む AI エージェントが `audit_query.operations` を「audit_query が実行する操作の一覧」と読む危険がある。**キー名は親 `audit_query` でスコープされるので `operations` / `target_kinds` を維持する**が、契約文に**明示的な曖昧解消文**を置く — 「これは `audit.fields` の `operation` 列が取りうる値の語彙であって、`capability_status.defined.atomic_mutation` が言う実行語彙ではない」。`target_kinds` には同種の衝突は無い (契約中に他の用法なし)。

**義務の形 (条件付き)**: `audit_query` を `unavailable` **以外**で宣言する 1.5.0 以上の実装は、**その `audit_query` が返しうるすべての event の `operation` / `target_kind` を、それぞれの宣言に含めなければならない**。`event_classes` と同じ ⊇ 関係であり、契約が特定のメンバを要求することはない。`audit_query` が `unavailable` の実装 (監査データストアが構成されていない配備) は 1.5.0 を宣言したまま本義務を負わない — 1.4.0 の条件付き義務 (1)〜(6) と同じ条件付き性である。

**なぜ宣言化か**: `event_class` が D-7 で宣言語彙になった理由がそのまま当てはまる。契約に固定 enum を置けば両 peer の出荷済み語彙と既存の耐久行が不適合になり、証拠の連続性が切れる。一方で宣言化しなければ、C-09 vector 1 の相関条件は永久に手書きの候補集合のままであり、綴りの変更を共通 suite が検出できない (§1.1)。宣言化は「共通 suite が読める真実」を増やす方向であって、peer の語彙を狭める方向ではない。

**共通テストへの影響**: C-09 vector 1 の手書き候補集合 (`_LIKELY_DESTRUCTIVE_OPERATIONS` / `_LIKELY_DESTRUCTIVE_TARGET_KINDS`) を**廃止**し、1.5.0 以上を宣言する peer に対しては次の 2 条件へ置換する。

- (i) 破壊的操作の直後に現れた**新規 durable 行**の `operation` / `target_kind` が、それぞれ宣言に含まれること。
- (ii) `audit_query` が返す**全 event** の両フィールドが、それぞれ宣言に含まれること (宣言整合)。

(ii) は**共通 suite 初の宣言整合 vector** である — `event_class` の宣言整合はこれまで peer-local の AST 走査だけが担っており、共通 suite に「返された event の値が宣言に収まる」ことを見るテストは無かった。**この機会に `event_class` にも同じ vector を足す** (返された全 event の `event_class` ⊆ 宣言)。3 フィールドとも同型のテストになる。

1.4.0 を宣言する peer には課さない。分岐は既存の `_semver_tuple` / `_audit_query_declaration` (`test_c09_audit_evidence.py:167` / `:211`) による declare-first 分岐をそのまま使う。**port は D-1 のためには変更不要**である — 宣言は既存の `control_capabilities()` 経路で読める (§1.4 の 7)。

**peer 側の実現 (両 peer 同型、P4-D16 v3 の構造をそのまま流用)**:

- 宣言集合を frozenset として持つ: **`DECLARED_AUDIT_OPERATIONS`** / **`DECLARED_AUDIT_TARGET_KINDS`**。MitateDB は `event_classes` と同じく **control 側と application 側の 2 モジュール構成** (`audit_query.py` の control 半分 + `application_audit.py` の application 半分) を採り、r2db は `audit_query.py` の単一定義とする。
- AST 走査で **`U == D ∪ N` かつ `D ∩ N == ∅`** を固定する (P4-D16 v3 (e) と同じ等式)。**U** = ソース中の全 literal 集合、**D** = 宣言、**N** = 耐久表へ届かない非耐久語彙をテスト内に名指しで列挙した除外集合 (各要素に「耐久表へ届かない根拠」をコメントで付す)。
- **宣言スナップショットテスト**を 2 フィールド分追加する (L4-11 で `event_class` に置いた `test_declared_audit_event_classes_change_only_deliberately` と同型)。等式 (e) は「D から抜いて同時に N へ足す」縮小を検出できないため、宣言の縮小には別途この一回きりの人手固定が要る。

**前提となる製品変更 (keyword-only 化、挙動不変)**: 走査器の盲点 (§1.4 の 1) は、**位置渡しの emit 面を構文的に消す**ことでしか閉じない (P4-D16 (c) と同一の理由)。**audit emit 面の定義**で keyword-only 化するのは次のとおりである。

| peer | 定義 | フィールド |
|---|---|---|
| r2db | `control_plane.py:1335` `_authorize_role` / `control_plane.py:1363` `_gate_must_rotate` / `service.py:1383` `_control_event` / `service.py:1139` `_event` / `service.py:1078` `deny_unsupported` | `operation` |
| r2db | `service.py:1139` `_event` | `target_kind` |
| MitateDB | `control_plane.py:1204` `_authorize_role` / `control_plane.py:1250` `_gate_must_rotate` | `operation` |

各定義の `operation` / `target_kind` を `*` の後ろへ移し、位置渡しの呼び出しをすべてキーワード渡しへ書き換える。**挙動は変わらない** (仮引数の順序も既定値も変えず、渡し方だけを変える)。MitateDB の emit ヘルパ群は既に規律を満たしており対象外である (§1.4 の 2)。

**これは規則 (c) が反応する定義の全数ではない (v1.2 訂正)**。規則 (c) は P4-D16 (c) の**無差別性**を核とするため callee 名で絞らず、`<field>` という名の仮引数を持つ定義に**すべて**反応する。`event_class` は監査専用語だが `operation` は違う — 識別子の出現数で r2db は `event_class` 117 / `operation` 335 / `target_kind` 83、MitateDB は 90 / 280 / 79 である。実際に (c) が拾う**監査と無関係な定義**は下記 9 件で、いずれの `operation` も**クライアント由来の mutation / schema operation dict** であって監査フィールドではない。これらを keyword-only 化すると、`StorageBackend.apply_schema` という**抽象基底の署名変更**や `DataService.schema(context, operation)` という**準公開面の呼び出し規約変更**を伴い、「挙動不変・渡し方だけ」という約束の範囲を超える。

| peer | 定義 |
|---|---|
| r2db (8) | `backend.py:104` `apply_schema` (抽象基底) / `postgres.py:1194` `_apply` / `postgres.py:1528` `apply_schema` / `service.py:1034` `schema` / `structured.py:199` `bind_mutation` / `structured.py:569` `bind_schema_operation` / `structured.py:1206` `_apply` / `structured.py:1376` `apply_schema` |
| MitateDB (1) | `cell.py:652` `_plan_operation` |

**決定 — 規則 (c) の最終形**: (c) は「`<field>` 仮引数を持つ**全定義**は keyword-only。ただし各 peer が**名指しで列挙する除外リスト** `_NON_AUDIT_<FIELD>_PARAMETERS` (関数の qualified 名、および根拠 = 「この `<field>` はクライアント由来の mutation / schema dict であって監査フィールドではない」) に載る定義は除く」とする。除外リストは**それ自体をテストが検証する**:

- (i) 除外リストの**各項目が実在すること** (陳腐化した項目は赤 — 関数が消えた・改名されたときに気付く)。
- **(ii′)** 除外された定義の本体に、**`<field>=<Name>` の形でその定義自身の仮引数 `<field>` を渡す `Call` が無いこと** (= クライアント由来値が監査フィールドへ転送されないこと)。

**(ii) から (ii′) への差し替え (v1.3)**: v1.2 は (ii) を「除外定義の本体に `<field>=` を `Constant` で渡す `Call` が無いこと」と書き、あわせて「監査 literal を運ぶ定義は除外できない構造にしてある」と主張していた。**この主張は r2db の現行コードに反証される** — `service.py:1034` の `DataService.schema(self, context, operation, *, request_id=None)` は (a) 除外が**必要**であり (`operation` はクライアント由来の schema operation dict で、keyword-only 化すると `http.py:355` の `service.schema(context, body, request_id=…)` という準公開の位置渡し規約が変わる)、かつ (b) **監査 literal の発生源でもある** (`:1052` が `operation="schema"` を `_make_audit_hook` へ Constant キーワードで渡す。keyword-only 化後は `:1054` / `:1057` の `_event` 呼び出しも同形になり、(ii) 違反は 5 → 7 件へ増える)。(ii) をそのまま実装すると WP-2 が赤で止まる。

(ii′) は検査の性質を「この定義の本体に監査 literal が無いこと」から「**この定義の仮引数 `<field>` が監査 emit 面へ転送されないこと**」へ移す。除外の目的 (クライアント由来値が監査フィールドへ入らないこと) を過不足なく捉え、かつ (c) が emit 面を keyword-only に固定した後は転送が必ず `<field>=<Name>` 形になるので抜けが無い。**U の完全性には影響しない** — 除外が免ずるのは (c) の keyword-only 要求だけであり、`:1052` / `:1054` / `:1057` の `Constant` は (b) 側で従来どおり U に加算される。**実測では 9 定義すべてが (ii′) を CLEAN で満たす**。

代替案として `DataService.schema` の仮引数を `schema_operation` へリネームする手もある (MitateDB `http.py:731` と同じ処置。`http.py:355` は位置渡しなので呼び出し側は不変) が、残り 8 定義には同じ問題が無く r2db 1 箇所だけの非対称な処置になるため採らない。

除外は「名前が同じだけの別概念」を (c) の要求から外すためのものであり、無差別性を弱めるのではなく、**適用先を明示的に絞ってその絞り込み自体を機械検証する**形である。

**走査器の一般化 (両 peer) — 方式の確定 (v1.1)**: 採るのは **P4-D16 v3 (a)〜(e) の大域不変量方式を、フィールド名でパラメータ化したもの**である。すなわち「呼び出し地点ごとに値を解決する」方式は**採らない** — プロトタイプで実装したところ dict unpack の追跡・`self` 属性の追跡・名前ベースの呼び出し照合が必要になり、1190 行規模の解析器になった。**テストに載せて長く保守できる形ではなく、それ自体が検証対象になってしまう**。大域不変量方式は逆に「ソース全体でこの形しか許さない」と言い切るので、器が小さいまま結論が強い。

パラメータ化する既存規則 (`<field>` を `event_class` / `operation` / `target_kind` に置換して読む):

- **(a)** 走査対象は `src/<pkg>` 配下の全 `.py` の `rglob` 再帰列挙。
- **(b)** 全 `Call` の `<field>=` キーワード値は、文字列 `Constant` / 束縛検証済みの仮引数転送のみ許容。それ以外 (`JoinedStr`、`BinOp`、`Call`、再束縛由来の `Name`、**および読み出し側 passthrough**) は違反。
- **(c)** 全 `FunctionDef` / `AsyncFunctionDef` の仮引数 `<field>` は **keyword-only** でなければ違反 (`self` は判定から除く)。**ただし `_NON_AUDIT_<FIELD>_PARAMETERS` の名指し除外リストに載る定義は除く** (上記の決定)。
- **(d)(d′)** キー literal `"<field>"` を持つ `Dict` literal・`x["<field>"] = ...` の添字代入・**全スコープ**の `Assign` / `AnnAssign` / `AugAssign` (ターゲットが `Name(id="<field>")` / `Attribute(attr="<field>")`、分解後を含む) に、転送規則を満たさない値を置かない。
- **(e)** literal の全集合 **U** について **`U == D ∪ N` かつ `D ∩ N == ∅`**。**D** = 宣言、**N** = 耐久表へ届かない語彙をテスト内に根拠コメント付きで名指し列挙した除外集合。

**追加・変更する規則**:

- **(b′) `IfExp` の許容**: `IfExp` は**両枝がともに許容値**であるとき許容し、その `Constant` 枝を U に加算する。キーワード値の位置と代入値の位置の**両方**に適用し、**再帰的に評価する** (`"a" if x else ("b" if y else "c")` の内側 `IfExp` も許容値として扱い、3 語すべてを U に加算する)。これで r2db `ops.py:655` / `:688` の inline 三項演算と、MitateDB `control_plane.py:1456` / `:1676` の代入形三項演算が閉じる。
- **(b″) 同名変数への Constant 代入の許容**: `<field>` と**同名の変数**への `Assign` が `Constant` または IfExp-of-Constants であれば許容し、値を U に加算する。その名前の転送は、**closure 越しを含めて**仮引数転送と同格に扱う。ただし**同スコープに他の束縛形が 1 つでもあれば違反のまま**である (再束縛の抜け道を作らない)。ここで言う「**他の束縛形**」とは、現行の `_collect_direct_shadow_names` が数える**全形** — `for` ターゲット / `with … as` / `except … as` / walrus / `match … as` / `global` / `nonlocal` / 同名の `def`・`class`・import alias — を指す。これで r2db `control_plane.py:846` / `:1070` の closure 捕捉が閉じる。
- **(b‴) 読み出し側 passthrough はキーワード引数値では禁止し、dict literal の値としてのみ許す (3 フィールド共通、v1.2 の変更点)**: `.<field>` の `Attribute` / `["<field>"]` の `Subscript` は、**応答整形の dict literal の値** (`{"operation": row["operation"], …}`) としてのみ許容し、**`<field>=` キーワード引数の値としては許容しない**。理由は `operation` に固有の穴にある — **MitateDB のリクエストボディ自体が `"operation"` キーを持つ** (`http.py:730` の `_check_object_shape(body, _SCHEMAS["SchemaOperationRequest"])`)。passthrough をキーワード値で許すと、将来 `route_denial(..., operation=body["operation"], …)` と書かれたとき **`Subscript` として合法に通過し、U にも加算されない** — クライアントが綴った任意文字列が耐久列に入っても、走査器も宣言スナップショットも (e) 等式も赤くならない。これは `event_class` の走査器には無かった**一般化によって新設される穴**であり、構文で閉じる。**許容位置の明示 (N-5)**: dict literal の値に加え、**添字代入 (`x["<field>"] = …`) と属性代入 (`obj.<field> = …`) の値位置でも同格に許容する** — これらも応答整形の一部である。**禁止するのは `<field>=` キーワード引数値の位置のみ**である。**(b‴) の導入に製品変更は不要 (N-6)**: 現行コードの読み出し経路は 3 フィールド × 両 peer とも**すべて dict literal 形**であり (r2db `audit_query.py:150,157,158` / `control_plane.py:1155,1159`、MitateDB `audit_query.py:147-150,161-164,371,373`)、keyword passthrough 形は**実測 0 件**である。(b‴) は純粋な締め付けであって書き換え対象を生まない — 作業指示書には「探す必要はない」と明記する。

**大域不変量方式の要点 (MitateDB の転送ラッパについて)**: MitateDB の `append_audit(**fields)` や `audit_dispatch.py:538` の `append(count=…, **state["fields"])` は `<field>=` キーワードを持たないため、**走査対象に入らない**。これは穴ではない — これらのラッパが運ぶ literal は、**外側の `route_denial(..., operation="…")` 等の呼び出しサイトで捕捉される**。転送の中間を追わなくても、literal がソースに現れる場所を漏れなく押さえれば U は完全になる。これが「呼び出し地点ごとの値解決」を要さない理由である。

**あわせて実装者へ (無用な手入れを防ぐため)**: `audit_dispatch.py:624-628` の `route_denial` 内 `fields = {...}` literal は、`operation` / `target_kind` の値が**囲む keyword-only 関数の仮引数 `Name`** であるため **(d) に対して仮引数転送として合法**である (レビュー実測で違反 0 件)。`push_buffer_event` (:641-645) の `ApplicationAuditEvent(...)` も同じ理由で (b) 合法である。これらは書き換えない。

**MitateDB `http.py:731` は (d′) 違反として実際に検出される (v1.2 訂正)**: `operation = body.get("operation")` は「全スコープの `Assign` でターゲットが `Name(id="operation")`、値が `Call`」であり、まさに (d′) が捕まえる形である。v1.1 の「U に入らない」は**誤読**だった。処置は **WP-3 の製品変更として当該ローカル変数を `schema_operation` 等へリネームする** (挙動不変、`_SCHEMA_OPERATIONS` の門番はそのまま)。(d′) に例外を置く形は採らない — リクエスト由来値の混入を止めるという (d′) の目的そのものを削るためである。

**N の判定基準 (両 peer 共通、v1.2 新設)**: literal `L` が **N** に属するのは、**`L` を `Constant` として渡す emit サイトが 1 つ残らず非耐久経路で終端すること**を示したときに限る。durable 経路のサイトが 1 つでもあれば `L` は **D** である。r2db の非耐久経路は `ControlAuthority._control_event` (`service.py:1385-1386` → legacy in-memory `self._audit.append`) と `DataService._event` の `event_class="authentication"` 分岐 (耐久経路は `event_class != "data_operation"` で早期 return する) であり、MitateDB は**該当なしが初期仮説**である。この基準により、§1.4 の 8 の r2db 候補 8 語のうち `enable_application` / `disable_application` のように `control_plane.py:846` の `_write_state_audit` (耐久) にも現れる語は **D** 側になる — 候補をそのまま N へ置くと `D ∩ N == ∅` が破れるか、宣言が実 emit の上位集合でなくなり **SI-14 の真実性が逆向きに破れる**。

**両 peer とも N は実行時テストで確定する**: 静的な構造的根拠 (legacy in-memory sink であること) は出発点であって証明ではない。**r2db・MitateDB の双方**について、当該経路を通す**実行時テスト**で `application_audit` / `control_audit` に行が立つかを確定し、届かないものだけを根拠付きで N へ置く。MitateDB では「非耐久経路が存在しないこと」の確認になる — 具体的には `auth.py:424` / `:431` / `:483` と `credential_store_postgres.py:423` / `:445` / `:478` / `:494` の `operation="authenticate"` / `"assert_active"`・`target_kind="credential"` が耐久表へ届くかを実測する。

**`event_class` の走査もこの一般化器へ載せ替える** — 3 フィールドで走査器 1 実装とする。既存の `event_class` 側の性質 (P4-D16 v3 (a)〜(e)) が一般化で後退しないことは、WP-2 / WP-3 の変異注入で確認する (§10)。

### D-2 (Q2) 無条件義務 (b) の適用範囲を明示する — **契約 1.4.0 の同ラベル改訂** (v1.2 で位置づけを変更)

**決定**: 1.4.0 無条件義務 (b) が**どのホストに掛かるか**を、**1.4.0 の義務 (b) 本文そのものを補筆する形で**一意にする。「Since 1.5.0」の新義務としては置かない。

**なぜ同ラベル改訂か (v1.1 からの変更)**: v1.1 は「1.4.0 以上の全 peer に効く明確化」と書きながら「Since 1.5.0」段落へ置き、かつ共通テストを WP-1 で無条件登録するとしていた。これは三すくみの矛盾である — WP-1 の時点で両 peer は 1.4.0 を宣言しており、そこへ 1.5.0 の義務を無条件テストで掛けることになる。契約 `version_binding` 自身の「An implementation still declaring 1.3.0 is not held to any 1.4.0-only obligation retroactively」の規律 (本設計 §2 の制約 3) に反し、**契約が 1.4.0 の実装に要求していない挙動をテストが要求する**状態を作る — D-2 自身が避けようとした状態と同型である。

同ラベル改訂は契約本文が明示的に許す形である: `versioning.version_binding` は「Every obligation introduced under a given version label — whether enumerated above or **added by a later revision of this document still under that same label** — follows this same general rule」と書く。義務 (b) の**適用範囲の明確化**はまさにこれに当たり、従属判断 10 の additive 根拠にもこの一文を引く。これにより共通テストの**無条件登録**が規律と整合する。

**文言の骨子** (英語化は起草者、最終確定は依頼者。§5):

> 義務 (b) が要求する control/audit credential の認証は、**control surface の `audit_query` control endpoint** (正典 `POST /control/v1/audit/query` と control ホスト上の alias) に掛かる。`control_plane: enabled` を宣言する **data-plane ホストは control/audit credential を認証する義務を負わない**。**control-credential store を持たないホストは**、提示された control/audit credential を未知の credential として **`AUTH_INVALID` で拒否してよい**。同一ホストで両 surface を提供する配備 (`versioning.control_discovery` の co-hosting) は妨げない。

起草した英文 (依頼者確定待ち。1.4.0 無条件義務 (b) の文へ続ける補筆として):

> This acceptance is scoped to the **control surface's** `audit_query` control endpoint (the canonical `POST /control/v1/audit/query`, and its alias as served on the control host — the same host scoping `endpoints.audit_query.deprecation_note` already states, and the alias conditional obligation (5) above refers to). A data-plane host is not thereby obliged to authenticate control or audit credentials merely because it declares `control_plane` as something other than `unavailable`; where such a host holds no control-credential store, it **may** refuse a control or audit credential presented on its own `POST /v1/audit/query` alias as an unknown credential (`AUTH_INVALID`); it is not thereby required to accept, verify, or forward it. Co-hosting both surfaces in one process remains permitted (`versioning.control_discovery`) and is not what this scoping addresses.

**義務 (5) との関係 (N-3)**: 1.4.0 条件付き義務 (5) は「canonical path と `/v1/audit/query` alias の**双方**が identical operation として実際に応答すること」を要求するが、**どちらのホスト上の alias かを言っていない**。契約内に答えは既にあり、`endpoints.audit_query.deprecation_note` が「resolving to the identical operation **on the control surface's own host**, not this section's application surface」と書いている。補筆の第 1 文はこの既存文と義務 (5) を明示的に参照し、両者が衝突しないことを読み手に見えるようにする。

**`forwarded` の禁止を作らない理由 (N-2)**: v1.2 の英文は `never accepted or forwarded` という禁止句だった。とくに転送の禁止は**新規**である — data ホストの alias が control surface へリクエストを転送する実装は、義務 (5) を分離配備で満たす自然な手段でありうる。同ラベル改訂でそれを禁止すると、その形の 1.4.0 実装が**遡って非適合**になり、§8-4 の additive 主張が崩れる。許容形 (`may` + `is not thereby required to`) に落とす。

**義務形にしない理由 (v1.2)**: v1.1 の英文後半は「data ホストは `AUTH_INVALID` で拒否**する**」という義務形だった。これは既存契約 `versioning.control_discovery` の「co-hosting convenience, **not a requirement**」— control 面と data 面を同一ホストに載せる配備を明示的に容認する条項 — と衝突する。そのような配備では `/v1/audit/query` に control credential を出せば**正当に受理される**ため、義務形は (i) 既に許されていた挙動を禁止することで **1.5.0 束の additive 性を崩し**、(ii) 将来の単一プロセス配備プロファイルを契約違反にし、(iii) 「auth がケイパビリティ判定より先に走る」という順序の帰結にすぎないものを契約義務として読ませる。許容形 (「store を持たないホストは拒否してよい」) に落とす。

**実装制約を契約に書かない理由 (v1.2)**: v1.1 の英文末尾は「application-credential store と control-credential store を同一プロセスに置かない」と書いていた。SI-00 の statement は「単一 Application の侵害がそれ自体で他 Application や Control Plane を侵害しうるものであってはならない」であり、**プロセス分離はその安全結果を得るための control の 1 つ**にすぎない。CLAUDE.md は「同じ安全結果を与えるなら platform-specific control は peer 間で異なってよい」と定めるため、共通契約に特定 control を書くと、同じ結果を別の control (プロセス内の鍵材分離、別 DB ロール等) で得る実装を締め出す。**実現手段は `security/CONTROL_MAPPING.md` の SI-00 行に書く**。

**共通テスト**: port を **v1.9** へ上げ、**1 メソッドを追加**する (`audit_query_on_data_plane_host(actor)`、詳細は §6.2)。**xfail を付けず無条件で登録する** — 同ラベル改訂であり、両 peer とも現行実装で緑である。期待する結果は「**`AUTH_INVALID` による拒否**、または **control surface と同居するホストでは `audit_query` の提供**」の**いずれか**であり、`CAPABILITY_UNSUPPORTED` / `FORBIDDEN` / 5xx は不適合とする。`docs/design/CONFORMANCE_ADAPTER_V1.md` に **§19 (v1.9)** を新設して記録する。

**なぜ contract 側で締めるか**: 「どちらの読みも成り立つ」状態を残したまま実装だけを固定すると、**契約が要求していない挙動をテストが要求する**ことになる。逆に読み 2 を採れば data-plane プロセスに control credential store を持たせることになり、SI-00 / SI-02 の分離と正面から衝突する (§4)。

### D-3 (Q3、案 A) MitateDB の request-count limit 上限を撤廃する — 契約不変

**決定**: `ControlPlaneLimits.__post_init__` の `[1, 200]` を**4 クラスすべてで撤廃**し、**正の整数のみ**の検査にする (r2db `limits.py:140-143` と対称)。`control_requests_per_minute > applications + 2 × credentials_per_application + 67` の関係検査は**独立に残る**。

**根拠**: `200` の由来は conformance C-14 vector 5 の位置算術に余裕を持たせるための sanity bound (`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` R-6) であって、**本番配備の安全性質ではない** (§1.4 の 5)。安全結果 (窓が pre-auth であること・control 窓と別であること) は上限とは無関係に保たれる。撤廃により「同じ窓の広げ方が peer で違う」という運用者から見た非対称が消え、両 peer とも env var 1 本で済むようになる。**conformance 構成は現行の値のまま変えない** — `MitateDB-api/conformance/conformance_adapter_mitatedb.py:378` の `applications=100, credentials_per_application=5, control_requests_per_minute=200` はそのまま据え置く。撤廃は受理域の**拡大**なので既存構成は影響を受けない。ただし `:366` と `conformance_adapter_mitatedb_http.py:658` のコメントは**上限の存在を前提にした説明**を持つため、更新対象に含める (v1.1 の「conformance 用の構成は小さい値を使い続ける」は事実誤りだった — `200` は撤廃対象の上限そのものである)。

**受け入れた代償 (明記する)**: 上限は**誤設定に対する防波堤**でもあり、外せばその防波堤は無くなる。`audit_requests_per_minute` に桁違いの値を置いた配備を製品コードは止めない。これは依頼者設計原則 3「制約・制限で回避しない」に沿って**意図的に引き受ける代償**であり、両 peer の runbook に「**値は運用者の責任であり、宣言にそのまま反映される**」と書く。

**赤化するテストの扱い**: `MitateDB-api/tests/test_control_plane_service.py::test_limits_reject_out_of_range_values` の `201` ケース 3 件を**削除**し、代わりに r2db の `_GENEROUS_LIMITS` (100_000 スケールの構築) と同型の**大値受理テスト**を追加する。あわせて 3 点:

- **エラー文言を直す**: `__post_init__` の `f"{name} must be an integer in [1, 200]"` が撤廃後も残ると**嘘になる** — 読み手 (AI エージェント統合者を含む) に存在しない受理域を教える。`must be a positive integer` へ書き換える。
- **大値受理テストは関係検査を同時に満たす形にする**: `control_requests_per_minute > applications + 2 × credentials_per_application + 67` は残るので、r2db の `_GENEROUS_LIMITS` と同型にするなら 3 値を揃えて上げる。
- **下限テストを 4 クラスへ揃える**: 現行の parametrize は 3 フィールドのみで、`audit_requests_per_minute` は載っていない。撤廃後の「正の整数」検査は 4 クラス分あるので、下限 (`0` 拒否) のケースを 4 クラスに揃える。

**更新する文書**: `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c (「受理レンジは `[1, 200]`、引き上げは設計変更であって設定変更ではない」「この上限はこの peer 固有」という現行の枠組みごと書き換える)、`security/CONTROL_MAPPING.md` SI-08 行 (r2db 側・MitateDB 側**両方の cell** に非対称の記述があり、対で書き換える)、`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 L4-4 / L4-7(iii) / §11.2 Q3 の結審。**契約は不変である** — 契約は本クラスに数値レンジを宣言していない (§1.3)。

### D-4 版束縛と移行 — 1.4.0 の前例を踏襲する

**決定**: 契約 1.5.0 の公開と両 peer の宣言 flip を、1.4.0 と同じ形で分離する。詳細は §8、WP 対応は §9。要点のみ:

- 契約 1.5.0 の公開 (WP-1) では**どちらの peer の `contract_version` も動かさない**。過渡期に peer が 1.4.0 を宣言し続けるのは**正しい lag** であって非適合ではない (1.5.0 の挙動を出荷していないため)。
- 各 peer の flip は、その peer が 1.5.0 の挙動 (宣言キー 2 本 + 走査器 + D/N) を出荷する WP の**同一コミット**に落とす。
- WP-1 では D-1 の共通テストのうち「全 peer が 1.5.0 を宣言していること」を要求する**全体 vacuity guard を `xfail(strict=True)` で登録**し、**最後の flip WP と同一コミットで `xfail` を外す** (C-09 全体 guard が WP-1 → WP-3(b) で辿った経路と同型)。

---

## 4. 却下した代替案

### Q1 (D-1) について

- **共通語彙への統一 (`entity` に寄せる等)**: 両 peer の既存 `control_audit` / `application_audit` 行と出荷済み語彙を破る。D-7 (各 peer が宣言する) と正面から衝突し、過去の証拠を「契約不適合な行」に変えてしまう。**採れない。**
- **現状維持 (手書き候補集合のまま)**: 契約を触らずに済むが、§1.1 の検出不能がそのまま残る。CONDITIONS.md への開示は「気付けない」ことを正直に書くだけで、気付けるようにはしない。設計原則 1 (先送りしない) に反する。

### Q2 (D-2) について

- **読み 2 を採る (data ホストが control credential を受理する)**: data-plane プロセスに control credential store を持たせることになり、**SI-00 / SI-02 の分離と正面から衝突する**。選ぶなら分離側の再設計が先に要る。
- **peer-local テストだけを足す**: 契約上の義務の適用範囲という**共通の論点**に対して共通テストが無い状態が残る。両 peer が同じ読みを出荷していることを共通 suite が確認しないまま、peer それぞれが自分の読みを自分で確認することになる。

### Q3 (D-3) について

- **案 B (r2db 側に `[1, 200]` を入れて揃える)**: r2db 自身の既存テストが `100_000` スケールの limits を構築・宣言しているため**単独では通らない**。テストの書き換えを伴い、かつ「既に配備で使える範囲を狭める」方向の変更になる。
- **案 C (契約 1.5.0 でレンジを宣言する)**: 非対称そのものは契約レベルで消えるが、**契約が数値ポリシーを持つ**ことになる。契約はこれまで limit class の**存在と意味論**を定め、値は deployment-declared としてきた (`limits.example_profile` は非規範の参照例である)。その姿勢を 1 クラスのために崩す。

---

## 5. 未確定の選択肢 (依頼者確定待ち)

本設計で未確定なのは**契約の英文の最終文言**のみである。両論を残している箇所は無い。

1. **D-1 の宣言キーを説明する `audit` 節の注記の英文**。**キー名 `operations` / `target_kinds` 自体は監督裁定済みで両論を残さない** (親 `audit_query` でスコープされるため) — ただし `capability_status.defined.atomic_mutation.operations` との意味衝突を打ち消す**曖昧解消文は必須**である (§3 D-1)。
2. **D-2 の義務 (b) の適用範囲を締める英文** (§3 D-2 に起草した骨子。1.4.0 の**同ラベル改訂**として置く)。

いずれも**契約ファイルを変更するコミットの直前に監督が依頼者へ明示し、確定を得てから WP-1 を確定させる**。文言以外の設計判断 (キーを足すこと自体・義務の条件付き性・適用範囲の読み・Q3 案 A) は依頼者裁定済みであり、本節の対象ではない。

---

## 6. conformance への影響

### 6.1 C-09 vector 1 の置換 (D-1)

`conformance-tests/test_c09_audit_evidence.py`:

- `_LIKELY_DESTRUCTIVE_OPERATIONS` / `_LIKELY_DESTRUCTIVE_TARGET_KINDS` の 2 定数と、それを参照する相関条件を**廃止**する。廃止の経緯 (WP-3(b) の `"transact"` 追加と再削除まで含む) はコメントとして残さず、`conformance-tests/CONDITIONS.md` の C-09 行に**置換の事実として**記録する — 現行の限界 (b) の開示は役目を終える。
- 1.5.0 以上を宣言し `audit_query` が `unavailable` 以外の peer に対して、§3 D-1 の (i)(ii) 2 条件を課す。1.4.0 の peer は従来どおりの vector 1 (application_id スコープの破壊的操作イベントが存在すること) だけを課される形へ分岐する。分岐は既存の `_semver_tuple` / `_audit_query_declaration` を使う。
- **宣言整合 vector は 3 フィールド同型で置く** — `operation` / `target_kind` に加えて **`event_class`** も、返された全 event の値が宣言 (`event_classes`) に収まることを共通 suite で確認する。`event_class` の宣言整合はこれまで peer-local の AST 走査だけが担っており、共通 suite 側には無かった。**`event_class` の vector だけは 1.4.0 条件付きとする (監督裁定、v1.3)** — 1.4.0 条件付き義務 (4) が既に `event_classes` の宣言義務を課しているため、**1.4.0 以上を宣言し `audit_query` が `unavailable` 以外の peer に掛かる**。したがって WP-1 の時点 (両 peer とも 1.4.0) で**この vector は load-bearing であり、vacuous ではない**。`operation` / `target_kind` の 2 本は 1.5.0 条件付きのままである。
- **全体 vacuity guard** を 1 本追加し、WP-1 で `xfail(strict=True)` として登録、最後の flip WP と同一コミットで外す (§8)。

**(i) と (ii) の関係 (実装者向けの整理)**: (ii) は「`audit_query` が返す全 event」を見るので、**(i) は (ii) の部分集合**である。(i) が固有に足すのは検出力ではなく**位置づけ** — (i) は既存 vector 1 の存在条件 (破壊的操作の直後に新規 durable 行が現れること) をそのまま残し、**そこに現れた行についてのみ**宣言整合を追加で見る形である。宣言整合そのものの網羅は (ii) が担う。(i) を (ii) の重複として削ってはならないし、(i) に (ii) 以上の検出力を期待してもならない。

**共通 suite の射程外にあるもの (開示)**: (i)(ii) はいずれも「返された値 ⊆ 宣言」であり、**宣言の真実性の逆向き半分 — 宣言にあるが `audit_query` が決して返さない語彙 — は共通 suite では検出できない**。宣言に余分な語があっても vector は赤くならない。この半分は peer-local の (e) 等式 (`U == D ∪ N`) と N の根拠コメントだけが担う。この射程を `CONDITIONS.md` の C-09 行に開示する — 現行の限界 (b) (手書き候補集合) を置き換える先として自然である。

**port 変更は D-1 には不要**である (§1.4 の 7)。

### 6.2 port v1.9 と新メソッド (D-2)

- `conformance-tests/adapter.py` の `ConformanceAdapter` へ抽象メソッドを 1 本追加する (名称案 `audit_query_on_data_plane_host(actor)`)。**data ホストの `/v1/audit/query` に control/audit credential を提示する**。
- **実装方針 — alias ハンドラ自体へ提示することを要求する (v1.2)**: D-2 の契約命題は「**data ホストの `POST /v1/audit/query` alias エンドポイントが control credential を受理しない**」である。したがって本メソッドは、**その alias ハンドラそのもの** — r2db は data-plane の `audit_query` 入口、MitateDB は `http.py:830` の `post_audit_query` 相当 — に control credential を提示する実装を要求する。**HTTP adapter** は data base URL へ送ればこれを満たす (既存の `audit_query()` は control base URL しか使わないことを明示的に文書化しているため、この経路は現在の port に無い)。
- **到達できない plug の扱い**: ハンドラへ到達できない plug についてのみ、data-plane の認証面 — r2db は `DataService` の application authenticate 経路、MitateDB は `auth.CredentialStore.authenticate` — への control secret 提示を代替として許す。ただしこれは**別の命題 (store 分離) を検査している**ので、`CONDITIONS.md` の登録行に「**この plug は alias エンドポイントではなく認証面で観測している**」ことを**限界として開示する** (C-09 の限界開示と同じ書式)。開示しないと、alias ハンドラで auth とケイパビリティ判定の順序が入れ替わっても該当 plug は気付かない。
- **戻り値の規約 (port 慣行に合わせる)**: 成功 (受理されてしまった場合) は `Mapping` を返し、**peer の拒否は `ConformanceDenial(code, …)` を送出する** — 既存の `audit_query()` と同じ慣行である。「エラーを返す」形では `_dispatch_audit_query` と同型のヘルパが書けない。`test_c09_audit_evidence.py` には拒否コードを検証するヘルパ (`_require_denied_with(code)` 相当) が**まだ無い**ので、WP-1 で追加する。
- **`SurfaceAbsent` の扱い**: `control_plane` を `unavailable` と宣言する peer (control credential がそもそも存在しない)、または data ホストに `/v1/audit/query` alias を持たない peer に対しては、本メソッドは **`SurfaceAbsent` を送出する**。共通テストは既存の `_assert_*_surface_absent_claim` と同じ 3 部構成で claim を独立検証する (adapter の言い分をそのまま受け取らない)。これにより、テストの適用範囲が 1.4.0 義務 (b) の条件付き前提 (`control_plane` が `unavailable` でないこと) と一致する。同じ意味論を `CONFORMANCE_ADAPTER_V1.md` §19 にも書く。
- **4 adapter すべてが実装する** (Python の `ABC` により、実装しない plug はそもそも生成できない)。両 peer ツリー内の adapter 4 ファイルを編集するコミットになる (フェーズ3.5 WP-3 / フェーズ4 WP-1 と同型)。
- 対応する共通テストは **xfail なしの無条件登録**である (§3 D-2)。期待は「`AUTH_INVALID` による拒否、または control surface と同居するホストでは `audit_query` の提供」のいずれかであり、`CAPABILITY_UNSUPPORTED` / `FORBIDDEN` / 5xx は不適合である。
- `docs/design/CONFORMANCE_ADAPTER_V1.md` に **§19 (v1.9)** を新設し、§18 と同じ構成 (追加メソッドの意味論 / 既存 `SurfaceAbsent` 機構との関係 / 互換性影響) で記録する。既存メソッドの意味は変えない。

### 6.3 CONDITIONS.md

- **C-09 行**: 限界 (b) (手書き候補集合の開示) を置換の記録へ書き換え、port v1.9 と 1.5.0 分岐を明記する。あわせて **§6.1 の射程開示** (宣言の真実性の逆向き半分は共通 suite の射程外であり peer-local の (e) 等式が担う) を、限界 (b) を置き換える先として書く。P4-D18 による vector 4 の射程開示は**そのまま保つ**。
- **D-2 のテストの限界開示**: 認証面代替を使う plug がある場合、その plug 名と「alias エンドポイントではなく認証面で観測している」旨を登録行に書く (§6.2)。
- **D-2 のテストの登録先**: 認可境界の条件行 (C-14 系) と C-09 のどちらへ登録するかは作業指示書で確定する — 本設計は「共通 suite に無条件で 1 本存在すること」までを決める。

### 6.4 conformance 構成への非影響 (D-3)

Q3 の上限撤廃は adapter 構成を変えない。**MitateDB の conformance 構成は現行値 (`applications=100, credentials_per_application=5, control_requests_per_minute=200`、`conformance_adapter_mitatedb.py:378`) のまま据え置く** — 撤廃は受理域の拡大なので既存構成は影響を受けず、C-14 vector 5 の位置算術も現行値のまま成立する。変えるのは `conformance_adapter_mitatedb.py:366` と `conformance_adapter_mitatedb_http.py:658` の**コメント**だけである (現行は上限の存在を前提にした説明を持つ)。

---

## 7. Security Invariants との関係

**新しい invariant は不要である。** 本フェーズは既存の担保を機械検証で厚くするものであって、新しい共通安全性質を導入しない。

- **SI-14 (Security-Relevant Auditability)**: 宣言の真実性の機械検証が **2 フィールド分**増える。これまで `event_class` にのみ掛かっていた「宣言 ⊇ 実 emit」の等式 (`U == D ∪ N` かつ `D ∩ N == ∅`) が `operation` / `target_kind` にも掛かり、共通 suite 側でも `audit_query` の返す全 event が宣言に収まることを確認できるようになる。**ただし真実性の逆向き半分 (宣言にあるが決して返らない語彙) は共通 suite の射程外**であり、peer-local の (e) 等式と N の根拠コメントだけが担う (§6.1 で開示する)。監査の完全性そのもの (何を耐久記録するか) は変わらない。
- **SI-00 (Single-Compromise Containment)**: D-2 は「**data ホストが control/audit credential を認証する義務を負わない**」ことを契約の読みとして一意にし、共通テストで固定する。SI-00 の安全結果は「application 面の侵害がそれ自体で control 権限へ届かないこと」であり、**プロセス分離はそれを得るための control の 1 つ**にすぎない — 契約文には安全結果側を書き、実現手段 (store を同一プロセスに置かない) は `security/CONTROL_MAPPING.md` の SI-00 行に置く (§3 D-2)。分離の強度は変わらない。
  - **in-process plug についての注記 (誤読防止)**: conformance の in-process plug が 1 プロセス内で control secret と data 面ハンドルの両方を持つのは**試験合成**であって配備形ではない。SI-00 は product の配備構造に掛かる invariant なので矛盾しない (ただし §6.2 のとおり証拠力は下がるため、限界を開示する)。
- **SI-08 (Bounded Resource Consumption)**: D-3 は宣言された窓が pre-auth で強制されるという要求される安全結果を変えない。変わるのは受理レンジという**実装裁量**の側であり、上限撤廃の代償 (誤設定の防波堤が無くなる) は §3 D-3 のとおり引き受け、`security/CONTROL_MAPPING.md` SI-08 行と両 peer の runbook に運用者責任として記録する。

---

## 8. 版束縛と移行

契約 1.4.0 の出荷 (従属判断 9、WP-1 `09233dd` → r2db `a1a1409` → MitateDB `a3571dc`) と同じ形を踏襲する。

1. **契約 1.5.0 の公開 (WP-1、単一コミット)**
   - `spec/data-service-api.v1.json`: `contract_version` を 1.5.0 へ。**項目 1 (D-1)** の宣言キー 2 本 (`operations` / `target_kinds`) を `audit` 節の注記として「Since 1.5.0 (subordinate ruling 10, item 1, conditional on audit_query being provided)」書式で追加し、`versioning.version_binding` の **1.5.0 段落**に条件付き義務として逐条列挙する。末尾の「An implementation still declaring X.Y.Z is not held to any later-version obligation retroactively」の列挙にも 1.5.0 を加える。
   - **項目 2 (D-2) は 1.5.0 段落へは置かない** — **1.4.0 無条件義務 (b) の文そのものを補筆する** (同ラベル改訂、§3 D-2)。契約本文の「added by a later revision of this document still under that same label」条項がこれを許す。
   - **r2db パッケージ内コピー** (`r2db-api/src/r2db_api/contract/data-service-api.v1.json`) を**バイト同一**に同期する (`test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` が固定)。
   - `spec/CCR_DISPOSITION.md` に**従属判断 10** を house style で記録する: **(a) 各項目の内容と根拠**、**(b) すべて additive である根拠**、**(c) 版数の扱い**、**(d) 依頼者裁定の参照**、および**項目ごとの再検討条件**。項目 1 = D-1 (`operation` / `target_kind` の宣言語彙化)、項目 2 = D-2 (1.4.0 無条件義務 (b) の適用範囲の同ラベル補筆)。
   - **項目 2 の additive 根拠には実測を添える (N-4)**: 補筆の第 1 文は受理対象に「control ホスト上の alias」を明示するため、**文言上は義務 (b) の受理経路が 1 つ増える** (現行の (b) は `audit_query` control endpoint しか名指ししていない)。**両 peer とも control ホストで alias を同一ハンドラへ載せている** — `r2db-api/src/r2db_api/control_http.py:398-399` と `MitateDB-api/src/mitatedb_api/control_http.py:391-392` がいずれも `/control/v1/audit/query` と `/v1/audit/query` を同じ `post_audit_query` へルーティングする。したがって**既存 1.4.0 peer の適合は変わらない**。この実測を additive 主張の検証可能な根拠として記す。
   - **従属判断 9 の house style に倣い、「義務の条件付き性」を独立した太字段落で書く** — **項目 1 は条件付き** (`audit_query` が `unavailable` 以外のときのみ)、**項目 2 は無条件** (1.4.0 の (b) 自身が無条件であり、その適用範囲の明確化も無条件)。従属判断 9 はこの段落を `version_binding` 本文の (a)(b)(c) / (1)〜(6) と 1 対 1 に対応させており (WP-1 レビュー F-2 で個数表記まで合わせた)、10 も同じ分割を持つため必要である。
   - 共通テスト (§6.1 の分岐と全体 guard、§6.2 の D-2 テスト) + **port v1.9** + **4 adapter のメソッド実装**。
   - **全体 vacuity guard を `xfail(strict=True)` で登録**する — 本 WP の時点でどちらの peer も 1.5.0 を宣言していないため。
2. **r2db の 1.5.0 出荷 (WP-2、単一 peer コミット)**: keyword-only 化 + 走査器一般化 + D/N + 宣言キー 2 本 + **`contract_version` 1.5.0 flip** + 版数のテスト固定更新 (宣言箇所は `service.py` / `control_plane.py` の 2 箇所)。
3. **MitateDB の 1.5.0 出荷 (WP-3、単一 peer コミット)**: 走査器一般化 + D/N + 宣言キー 2 本 (control / application の 2 モジュール) + **`contract_version` 1.5.0 flip** (`cell.py` / `control_plane.py` の 2 箇所) + **全体 vacuity guard の `xfail` 撤去を同一コミットで行う** — flip 自身が guard を無介助で緑にすることを示す。
4. **移行の非破壊性**: D-1 は追加キーであり、既存キーの削除・意味変更・enum 縮小を伴わない。D-2 は現行の実装挙動を変えない文言の明確化であり、かつ**許容形に落としてあるので既存の co-hosting 容認 (`versioning.control_discovery` の「co-hosting convenience, not a requirement」) を狭めない** — 義務形にすると既に許されていた配備を禁止することになり additive でなくなる (§3 D-2)。D-3 は契約を触らない。したがって 1.5.0 は **additive** である。
5. **1.4.0 に留まる実装**: 1.5.0 の**項目 1** の義務を遡及して負わない。C-09 の 1.4.0 分岐は残す。**項目 2 は 1.4.0 の義務の明確化**なので 1.4.0 を宣言する実装にも掛かる — これは遡及ではなく、同ラベルの義務の適用範囲を一意にしたものである (§3 D-2)。

---

## 9. WP 分割の概略 (作業指示書は別途)

| WP | 内容 | 公開面への影響 |
|---|---|---|
| **WP-1** | **契約 1.5.0 単一コミット**: spec 変更 (項目 1 = 1.5.0 段落 / **項目 2 = 1.4.0 義務 (b) の同ラベル補筆**) + r2db パッケージ内コピーのバイト同一同期 + `CCR_DISPOSITION` 従属判断 10 (a)〜(d) + **義務の条件付き性の独立段落** + 共通テスト (C-09 の 1.5.0 分岐 / 宣言整合 vector 3 本 = `event_class` は **1.4.0 条件付きで本 WP から load-bearing**・`operation` / `target_kind` は 1.5.0 条件付き / D-2 の無条件テスト / `_require_denied_with` 相当ヘルパの追加) + **port v1.9** + 4 adapter のメソッド実装 + 全体 vacuity guard の `xfail(strict=True)` 登録 + `CONFORMANCE_ADAPTER_V1.md` §19。**peer の版数 flip は含まない** | あり (契約公開) |
| **WP-2** | **r2db 単一 peer コミット**: audit emit 面の keyword-only 化 (`_authorize_role` / `_gate_must_rotate` / `_control_event` / `_event` / `deny_unsupported` の `operation`、`_event` の `target_kind` — 位置渡し 20 箇所超のキーワード化、挙動不変) + **`_NON_AUDIT_<FIELD>_PARAMETERS` 除外リスト (r2db 8 定義) とその検証テスト 2 本 ((i) 実在性 / (ii′) 仮引数の非転送)** + 走査器の一般化 (P4-D16 v3 (a)〜(e) のパラメータ化 + (b′)(b″)(b‴)、`event_class` も同じ器へ載せ替え) + `DECLARED_AUDIT_OPERATIONS` / `DECLARED_AUDIT_TARGET_KINDS` + **N の実行時実測** (`_control_event` / `_event("authenticate")` 経路が耐久表へ届かないことを実測し、D と重なる語を N から外す) + 宣言キー 2 本 + 宣言スナップショットテスト 2 本 + **`contract_version` 1.5.0 flip** | あり (宣言拡張 + 版数宣言) |
| **WP-3** | **MitateDB 単一 peer コミット**: WP-2 と同型 (keyword-only 化は `control_plane.py` の `_authorize_role` / `_gate_must_rotate` の `operation` の 2 定義のみ、除外リストは `cell.py:652` `_plan_operation` の 1 定義) + **`http.py:731` のローカル変数を `schema_operation` 等へリネーム** (製品変更、挙動不変 — (d′) 違反の解消) + 2 モジュール構成の宣言 + **N の実行時実測** (`auth.py` / `credential_store_postgres.py` の `authenticate` / `assert_active` 経路が耐久表へ届くかを確定。初期仮説は「非耐久経路なし = N は空」) + **`contract_version` 1.5.0 flip** + **全体 vacuity guard の `xfail` 撤去** | あり (宣言拡張 + 版数宣言) |
| **WP-4** | **Q3 (D-3)**: MitateDB の `[1, 200]` 撤廃 (4 クラス) + **エラー文言を `must be a positive integer` へ** + `201` ケース 3 件の削除 + 大値受理テストの追加 (関係検査を満たす 3 値) + 下限テストの 4 クラス化 + `cloud-run-cloud-sql.md` §3.2c 書き換え + runbook への運用者責任の記載 + **conformance adapter 2 ファイルのコメント更新** (`conformance_adapter_mitatedb.py:366` / `conformance_adapter_mitatedb_http.py:658` — 構成値 `:378` は据え置き) | あり (受理域拡大) |
| **WP-5** | **記録整理**: `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 (L4-1 / L4-2 / L4-4 / L4-7(iii)) と §11.2 (Q1 / Q2 / Q3) の結審、`CONDITIONS.md` C-09 行 (射程開示 + 認証面代替の限界開示)、`CONTROL_MAPPING.md` (SI-00 / SI-08 / SI-14)、両 peer の runbook、両 peer の配備文書の宣言例 (新キー 2 本を含む形へ)、**従属判断 10 への「実施記録」追記** (従属判断 9 と同じ運用) | なし |

**実装上の申し送り 2 点**: (1) **全体 vacuity guard は既存の `test_c09_every_control_surface_adapter_takes_the_provided_branch` と同形で書く** — 非 parametrize の関数 1 本が `registered_adapters()` を自前で走査する形であり、adapter fixture で parametrize しない (`xfail(strict=True)` を最後の flip で外す運用がこの形を前提にしている)。(2) **(b‴) の導入に製品変更は不要である** — keyword passthrough は 3 フィールド × 両 peer で実測 0 件であり、WP-2 / WP-3 の実装者は書き換え対象を探す必要がない (§3 D-1)。

**契約変更コミット (WP-1) は依頼者確認後に実施する** (§2 の 8)。完了条件は既存フェーズを継承する — テスト追加 + 変異注入 (scratchpad 復元、`git checkout` 不使用)、root suite 完走 (現基準 1545 + 増分)、宣言語彙の全数固定の維持、独立レビュー往復、commit / push / main merge (`--no-ff`) 1 セット + identity 確認。

---

## 10. 将来課題

- **走査器一般化に伴う `event_class` 側の回帰**: 3 フィールドを 1 実装で扱う一般化は、`event_class` について P4-D16 v3 が固定した性質 (無差別 literal 規律 / keyword-only 保証 / dict 密輸禁止 / 語彙関係の厳密一致) を後退させ得る。WP-2 / WP-3 の**変異注入**で、一般化前に赤化していた変異がすべて一般化後も赤化することを確認する。
- **`_NON_AUDIT_<FIELD>_PARAMETERS` 除外リストの保守**: `operation` は監査専用語ではない (r2db 335 出現 / MitateDB 280 出現) ため、非監査の `operation` 仮引数を持つ定義が今後増えれば除外リストも増える。リストの検証テスト (実在性 + (ii′) = 本体で自関数の仮引数 `<field>` を `<field>=<Name>` で渡す Call が無いこと) がこれを機械的に見張るが、**リストが伸び続けること自体が「(c) の無差別性が `operation` については素直に効かない」という構造の表れ**である。伸びが目立つようなら、監査フィールドを別名 (`audit_operation` 等) にする案を再検討する材料になる。
- **走査器の実装は peer 内コピーである**。両 peer に同型の器を置くが、**peer 間でコードを共有しない**慣行を維持する。一般化によって両者の器はさらに似るため、片方だけの修正が他方へ伝わらない危険は増す — 変更時は必ず両 peer 同時に扱う。
- **`audit_requests_per_minute` の上限は元々テストされていなかった**: MitateDB の `201` 拒否テストは 3 クラス分しか無く、4 番目のクラスの上限は一度も直接テストされていない (§1.4 の 6 の裏返し)。D-3 で上限自体が消えるため実害は無くなるが、「クラスを増やしたときに既存の検査へ載せ忘れる」という形の欠落は他所でも起こり得る。
- **`request_bytes` の検査ループ位置の非対称 (D-3 で触れない第 2 の小非対称)**: r2db は `request_bytes` を他の 4 クラスと同じ「正の整数」検査ループに畳んでいるが、MitateDB は `__post_init__` の中で別建てに検査している。D-3 で数値レンジの非対称は消えるが、この構造の非対称は残る。実害は見えていない。
- **Q4 は本フェーズに入らない**: `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合 (宣言は control プロセス、実効値は data-plane プロセス) は、`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4 の監督推奨どおり**独立の設計フェーズ**として残る (両 peer 同時、設計文書 + migration)。
- **L4-8 (C-09 vector 4 の据え置き)** と **L4-12 / L4-13** は本フェーズの対象外であり、`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 が引き続き保持する。
- **1.4.0 alias の除去**: 従属判断 9 項目 7 の再検討条件 — `endpoints.audit_query` (`POST /v1/audit/query`) の alias を 1.5.0 以降に除去するかどうかは別途裁定する。**本フェーズでは除去しない** (D-2 は alias が data ホスト上にも存在し続けることを前提に、そこでの credential の扱いを定めている)。
