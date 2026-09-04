# フェーズ5 実施設計: 契約 1.5.0 (監査語彙の宣言化 + 無条件義務 (b) の適用範囲) + request-count limit 受理レンジの対称化

- 版数: **v1.5 (2026-09-04、WP-5 記録整理 part 2 + 監督裁定による WP-5 追補)** — **v1.4 が残した `{WP-4 後に確定}` プレースホルダを全数解消**した。§10.1 の集計行表を WP-3 (`3f2da59` → merge `98d2010`、**1612 passed / 0 / 0 / 0**) と WP-4 (**1611 passed / 0 / 0 / 0**) の実測で埋め、**§10.4 (WP-3) を「進行中」から確定記録へ書き換え** (レビュー 7 件の閉じ方・変異実測・受理境界)、**§10.5 (WP-4) を新規に記述**した (上限撤廃 4 クラス・テスト差し替え・adapter 構成据え置き・**変異 6/7 が未実測である事実**)。§11 に将来課題 **L5-5 (同型性テストが兄弟ファイル外の同名ヘルパを対象にできない)** / **L5-6 (同型性テストのソース取得方式の左右非対称)** / **L5-7 (WP-4 変異 6/7 の実測コストが禁止的)** / **L5-8 (下限検査の peer 非対称 — MitateDB は `bool` を拒否、r2db は受理)** を追加した。**監督裁定による追補 (同日)**: D-3 で偽になった先行文書の記述 2 箇所に日付付きの否定注記を置いた — `spec/CCR_DISPOSITION.md` 従属判断 9 の実施記録 (受理レンジの非対称は解消済み。契約 JSON は不変) と `docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` R-6 (製品側上限は撤廃、`_MAX_EXERCISABLE_LIMIT` は conformance 構成の上限としてのみ残る)。どちらも原文は当時の記述として残してある。**残るプレースホルダは WP-4 / WP-5 のコミットハッシュ (`d11c86f` / `(本記録コミット。ハッシュは HANDOVER_20260904_FABLE.md §1 に記載)`) のみ**であり、監督がコミット後に埋める
- 旧 v1.4 (2026-09-04、WP-5 記録整理 part 1) — **§10 「実施記録」を新設**し (旧 §10 = 将来課題は **§11** へ繰り下げ)、WP-1 (契約 1.5.0 公開) と WP-2 (r2db の 1.5.0 出荷) の実装記録・レビュー往復・変異注入結果・**受理境界**、および WP-3 (MitateDB) の現況を記録した。§1.4 の 8 の候補表に**訂正註**を置き (実際の N は候補表と食い違う)、§11 にフェーズ5 起票の将来課題 **L5-1〜L5-4** を追加した
- 旧 v1.3 (2026-09-03、再レビュー N-1〜N-7 反映) — 2 回目の独立レビュー (`scratchpad/review-design-150-r2.md`) の新規指摘 7 件を全件裁定・反映。主要な変更: **除外リストの検証条件 (ii) を (ii′) へ差し替えた** (N-1 — r2db `DataService.schema` は**除外必須でありながら監査 literal を運ぶ**ため、v1.2 の「監査 literal を運ぶ定義は除外できない構造」は現行コードに反証された)、**起草英文の `never accepted or forwarded` を許容形へ** (N-2 — `forwarded` の禁止は 1.4.0 条件付き義務 (5) を分離配備で満たす転送実装を遡って非適合にする)、**補筆第 1 文に `endpoints.audit_query.deprecation_note` の host scoping と義務 (5) への参照を追加** (N-3)、**従属判断 10 の additive 根拠に両 peer の control ホスト alias 同一ハンドラの実測を追加** (N-4)、(b‴) の許容位置を添字代入・属性代入まで明記 (N-5)、**(b‴) の導入に製品変更は不要** (実測 0 件、N-6)、**`event_class` の返却 vector は 1.4.0 条件付き**で §6.1 と §9 を統一 (N-7)
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

   **訂正註 (v1.4、WP-5 記録整理。上の候補表は起草時の記述として残す)**: 実装 (WP-2 / WP-3) が確定させた D / N は上表の候補と食い違う。**語彙 U の規模は 4 行とも実測どおり**だったが、**N の中身は 2 点で違った** — 確定値の全体は §10.4 に置く。
   - **r2db `operation`**: 候補 8 語のうち **5 語 (`authenticate` / `disable_application` / `enable_application` / `issue_credential` / `register_application`) は D 側**になった。`disable_application` / `enable_application` は上表自身が予告していたが、**`authenticate` は予告できていなかった** — WP-2 の実行時実測で、失敗 authenticate の `AUTH_INVALID` 拒否が `_DURABLE_DENIAL_CODES` 経由で耐久化することが分かったためである。逆に**候補表に無かった `control_capabilities` が N 側**になった (deny 分岐に到達する経路が構造的に存在しない。WP-2 レビュー M-1)。確定 N は 4 語。
   - **MitateDB `operation`**: 上表は「現時点で候補なし」と書いたが、確定 N は **`control_capabilities` の 1 語**である (r2db と同型の到達不能性)。他方、§3 D-1 が名指しで実測を求めた `auth.py` / `credential_store_postgres.py` の `authenticate` / `assert_active` は**耐久であると実測**され、初期仮説どおり N には入らなかった。
   - **`target_kind` は両 peer とも候補表どおり** — r2db は `application_or_credential` の 1 語が N、MitateDB は N = ∅ である。

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

**`event_class` の走査もこの一般化器へ載せ替える** — 3 フィールドで走査器 1 実装とする。既存の `event_class` 側の性質 (P4-D16 v3 (a)〜(e)) が一般化で後退しないことは、WP-2 / WP-3 の変異注入で確認する (§11)。

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

## 10. 実施記録 (WP-5 記録整理、2026-09-04)

**本節の完成度 (v1.5)**: v1.4 が留保した `{WP-4 後に確定}` は**全数解消済み**である。**Q1 (WP-1 / WP-2 / WP-3)・Q2 (WP-1)・Q3 (WP-4) のすべてについて、実装記録・レビュー往復・変異注入結果・受理境界を書いた。** 残るプレースホルダは **WP-4 / WP-5 のコミットハッシュ (`d11c86f` / `(本記録コミット。ハッシュは HANDOVER_20260904_FABLE.md §1 に記載)`) だけ**であり、これは監督がコミット後に埋める欄である — **本文中の事実に未確定は無い**。

### 10.1 集計行

**集計行の出所**: 下表の集計行は、**監督が完了ゲートで単独実行して得た実測値**を、当該 WP のコミットメッセージ末尾の `Root suite alone:` 行から転記したものである (`git log` で確認できる)。**本節の起草者が再実行した値ではない** — 起草担当はテストを実行していない。

| WP | 内容 | 実装コミット | merge コミット | root suite (単独実行) |
|---|---|---|---|---|
| **WP-0** | 設計 v1.3 + 作業指示書 v1.1 | `809a113` | `e26e794` | 文書のみ (基準 **1545 passed / 0 failed / 0 skipped / 0 xfailed** のまま) |
| **WP-1** | 契約 1.5.0 公開 + port v1.9 + 共通 vector | `6e38ef8` | `d7a5ffd` | **1562 passed / 0 failed / 0 skipped / 1 xfailed** |
| **WP-2** | r2db の 1.5.0 出荷 | `ed4394a` | `3fd72ad` | **1586 passed / 0 failed / 0 skipped / 2 xfailed** |
| **WP-3** | MitateDB の 1.5.0 出荷 | `3f2da59` | `98d2010` | **1612 passed / 0 failed / 0 skipped / 0 xfailed** |
| **WP-4** | Q3 (MitateDB の上限撤廃) | `d11c86f` | `d11c86f` の merge | **1611 passed / 0 failed / 0 skipped / 0 xfailed** |
| **WP-5** | 記録整理 | `(本記録コミット。ハッシュは HANDOVER_20260904_FABLE.md §1 に記載)` | `(本記録コミット。ハッシュは HANDOVER_20260904_FABLE.md §1 に記載)` の merge | 文書のみ (**1611** のまま) |

**`xfailed` の推移**: WP-1 で 1 (全体 vacuity guard)、WP-2 で 2 (guard + 同型性 placeholder)、**WP-3 で 0** (同一差分で 2 本とも撤去)、WP-4 で 0。**WP-3 以降 `xfailed` は 0 であり、フェーズ5 は xfail を 1 本も残していない。**

**WP-3 → WP-4 の増減内訳**: 1612 − 3 (`201` 拒否ケース 3 件の削除) + 1 (下限 `0` ケースの 4 クラス化による 1 件増) + 1 (`test_limits_accept_generous_values_beyond_the_former_ceiling` の新設) = **1611**。ディレクトリ別では MitateDB 489 → 488、r2db 701 → 701、conformance 422 → 422 であり、**conformance は WP-4 で不変** (設計 §6.4 の非影響判断どおり)。

**起草時に見つけた照合上の食い違い (監督裁定事項)**: `docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md` §10 (実施記録) は WP-1 の root suite を **1561 passed** と記録しているが、WP-1 の最終ログ (`scratchpad/wp1-150-fix3-test.log`) とコミット `6e38ef8` のメッセージはいずれも **1562 passed / 1 xfailed** である (1561 は fix3 前の値。WP-2 受け入れ監査 §6-3 の指摘)。本表は **1562** を採る。作業指示書側の訂正は本書の管轄外であり、監督へ差し戻す。

### 10.2 WP-1 — 契約 1.5.0 の公開 (`6e38ef8` → merge `d7a5ffd`)

**実際に採った形** (発注時の予定と食い違った点は**実装が正**として記す):

- **契約**: `contract_version` 1.5.0。`versioning.version_binding` に **1.5.0 段落** (項目 1、`audit_query` が提供されていることを条件とする条件付き義務)、`audit` 節に **`query_operation_vocabulary` / `query_target_kind_vocabulary`** の 2 エントリ (`capability_status.defined.atomic_mutation.operations` との**曖昧解消文**を含む)、**1.4.0 無条件義務 (b) への同ラベル補筆** (項目 2、許容形。`forwarded` の禁止は作っていない)。`spec/CCR_DISPOSITION.md` に**従属判断 10** (a)〜(d) + 義務の条件付き性の独立段落。r2db パッケージ内コピーは byte 同一 (`cmp` exit 0)。
- **additive 性の機械確認**: 1.4.0 との再帰 diff で **削除キー 0 / 型変更 0 / enum・required・additionalProperties の狭化 0**、追加キー 2、変更スカラー 2 (`contract_version` と `versioning.version_binding`)。従属判断 10 項目 2 の additive 根拠として要求した alias 同一ハンドラの実測 (`r2db-api/src/r2db_api/control_http.py:398-399` / `MitateDB-api/src/mitatedb_api/control_http.py:391-392`) は**行番号ぴったりで一致**した。
- **port v1.9 の抽象メソッドは 1 本ではなく 2 本になった**。発注は `audit_query_on_data_plane_host` の 1 本だったが、レビュー F-2 / F-3 の裁定を受けて **`control_surface_cohosted_with_data_plane` を併せて追加**した — 同居の有無を「返却内容の突き合わせ」で推定する形をやめ、**adapter の宣言トポロジで判定する形**へ置き換えたためである。`docs/design/CONFORMANCE_ADAPTER_V1.md` §19 の見出しも "Two new abstract methods"。4 plug すべてが両メソッドを実装し、**同居宣言は 4 plug とも `False`** である。
- **共通 vector**: C-09 vector 1 の手書き候補集合 2 定数を廃止 (`grep -rn "_LIKELY_DESTRUCTIVE" conformance-tests` = 0 行)。宣言整合 vector 3 本 (`event_class` は 1.4.0 条件付き、`operation` / `target_kind` は 1.5.0 条件付き)、義務 (b) vector 1 本 (**無条件登録**、`test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted`)、全体 vacuity guard 1 本 (`test_c09_every_control_surface_adapter_declares_1_5_0`、`xfail(strict=True)`)。増分は **+17 収集** (parametrize 4 本 × 4 plug + 非 parametrize 1 本)。
- **依頼者確定文言の文字列ピンを追加した** (`test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose`)。発注時には無く、差し戻し 3 回目で入った項目である (常設規律 4 の機械化)。

**レビューと差し戻し**: 独立レビューの指摘 **9 件 (F-1〜F-9)**、差し戻しは **3 回**。

1. **F-1〜F-9 (レビュー本体)**。成果物に痕跡が残るのは F-1 (`event_class` vector の検出力の主張訂正)、F-2 / F-3 (同居フラグ機構への置換)、F-4 (`CONDITIONS.md` / §19 の限界開示を実装と一致させる)、F-6 (欠落・`None`・非 Mapping を違反として扱う)。**F-5 / F-7 / F-8 / F-9 の本文は失われている** — `scratchpad/review-wp1-150.log` が pytest 出力で上書きされており、受け入れ監査は反映可否を**判定不能**とした (監査 証拠不足 E-1)。**記録として残す欠落であり、隠さない。**
2. **U-1 / U-2 (受け入れ監査 1 回目の未充足 2 件)**。**U-1 (重)** = 宣言整合 vector が **4 adapter 中 2 つで vacuous** だった — HTTP 形の 2 plug では `audit_query` の返却 `events` が 0 件で、部分集合検査が空 list に対して自明に通っていた。修正は `_require_nonvacuous_provided` の新設 (既知の耐久イベントを 1 件起こし、宣言 lag 内でポーリングし、**非空を precondition として assert** する) であり、修正後は宣言語彙を空集合にする変異が **4 plug 全数で赤**になることを実測した。**U-2 (中)** = 依頼者確定文 4 文のうち 2 文が逐語でなかった。
3. **文字列ピン**。U-2 の再発防止として、依頼者確定文を逐語 assert するテストを置いた (監査の観察 O-3「補筆・曖昧解消文に機械 pin が無い」への対処でもある)。最終ラウンドの機械照合では、残った文 1 の不一致は**照合スクリプト側の正規化が ASCII 二重ハイフン `--` を扱わないこと**に起因する見かけの差であり、実文は確定文と一致することを確認した。

**変異注入の結果**: (i) data ホスト alias を control 経路へ委譲する変異 = **赤**、(ii) (i) を保ったまま同居宣言を `True` にすると **緑 (仕様どおり。下記の受理境界)**、(iii) 宣言語彙から 1 語を落とす変異 = **赤**、(iv) packaged copy の 1 バイト改変 = **赤**、(v) 全体 guard は **XFAIL のまま**。修正後の再検証では (iii) が 4 plug 全数、宣言語彙を空集合にする変異も 4 plug 全数で赤になった。

**受理境界 (この WP で「固定しない」と決めた点)**:

- **D-2 vector は「同居しているか」を adapter の申告で信じる**。`control_surface_cohosted_with_data_plane()` が `True` を返す plug では、data ホストの alias が `audit_query` を提供しても適合と判定される。**申告そのものを独立に検証する機構は無い** — 変異 (ii) がこれを実測している。現時点では 4 plug とも `False` を返すため、実際には常に `AUTH_INVALID` 側で判定されている。`conformance-tests/CONDITIONS.md` の C-09 行に開示済み。
- **宣言整合 vector が見るのは「そのセッションが実際に観測した値」だけ**である。宣言語彙全体の固定点検査ではない — `_require_nonvacuous_provided` が保証するのは「観測が 1 件以上あること」であって「宣言の全語を観測すること」ではない。**宣言の真実性の逆向き半分 (宣言にあるが `audit_query` が決して返さない語彙) は共通 suite の射程外**であり、peer-local の (e) 等式と N の根拠だけが担う (§6.1)。
- **到達できない plug の認証面代替**は、**現時点で使っている plug が無い**ことを確認したうえで機構だけ残してある。将来使う plug が現れたら `CONDITIONS.md` にその plug 名と「alias エンドポイントではなく認証面で観測している」旨を開示する必要がある。

### 10.3 WP-2 — r2db の 1.5.0 出荷 (`ed4394a` → merge `3fd72ad`)

**実際に採った形**:

- **製品変更 (挙動不変)**: `_authorize_role` / `_gate_must_rotate` / `_control_event` / `_event` / `deny_unsupported` の 5 定義で `operation` (と `_event` の `target_kind`) を keyword-only 化し、位置渡しの呼び出しを全数キーワード化した (`_event` 10 / `_control_event` 11 / `_authorize_role` 10 / `_gate_must_rotate` 10 / `deny_unsupported` 4)。**位置渡しの残り 0、引数の取り違え 0** をレビューが全件照合。
- **発注を超えた点 (レビュー M-3、常設規律 5)**: 設計の表が名指ししたのは `operation` / `target_kind` だけだが、実装は同じ定義の**残余引数 (`message` / `outcome` / `target` / `reason_code`) も keyword-only 化**した。理由は「2 フィールドだけを `*` の後ろへ移すと**残る位置引数の順序が変わり**、『仮引数の順序も既定値も変えない』という約束と両立しない」ためである。**監督はこれを採り**、コミットメッセージに "with the trailing parameters keyword-only too so argument order is preserved" と明記した。**実装が正**として記録する。
- **走査器**: `_FIELDS = ("event_class", "operation", "target_kind")` の 1 実装へ統合し、**走査対象フィールド集合そのものを pin するテスト** (`test_scanner_is_parameterized_over_exactly_these_three_fields`) を置いた。(a)〜(e) に加えて (b′) `IfExp` の再帰許容、(b″) 同名変数への Constant 代入 (closure 越しを含む)、(b‴) 読み出し passthrough を dict literal / 添字代入 / 属性代入の値位置に限定 (keyword 値位置では禁止) を実装。**(b‴) は製品変更を 1 行も生んでいない** — 設計 N-6 が挙げた読み出し経路は `git diff -U0` のどの hunk にも入っていないことを監査が確認した。
- **除外リスト**: `_NON_AUDIT_OPERATION_PARAMETERS` が **8 定義ちょうど**で設計の表と 1:1。検証テストは (i) 実在性と **(ii′) 自関数の仮引数を `<field>=<Name>` で emit 面へ転送しないこと**の 2 本 (撤回された (ii) は実装されていない)。`event_class` / `target_kind` の除外リストが**空であること自体**も直接 pin した (レビュー M-4)。
- **宣言**: control plane が `capabilities().audit_query.operations` (**27 語**) と `.target_kinds` (**5 語**) を `sorted()` で公開。**data plane は 2 キーを持たない** — この host は `audit_query` を提供しないので、語彙を宣言すれば declare-the-hazard に反するためである。両 plane の `contract_version` が `1.5.0`。
- **同型性テストは placeholder として `xfail(strict=True)` で登録**した (WP-3 追随待ち)。レビュー M-2 を受けて、`importlib` ではなく **sibling peer のテストファイルをパス指定で読む**形へ改め、`"MitateDB-api" in parts` / `"r2db-api" not in parts` を assert して**自己比較で緑になる形を構文で禁止**した。

**レビューと差し戻し**: 独立レビューの指摘 **5 件 (M-1〜M-5、中 1 / 低 4)**、差し戻し **1 回**。

- **M-1 (中)** — `DECLARED_AUDIT_OPERATIONS` に **`audit_query` が決して返さない語 `control_capabilities`** が入っていた。2 つの emit サイト (`_authorize_role` / `_gate_must_rotate`) はいずれも deny 分岐へ**構造的に到達できない** (前者は許可リストの恒久メンバ、後者は無条件の早期 return)。**D → N へ移し**、N の根拠コメントを既存の「legacy in-memory sink にのみ届く」とは**別文型** (「deny 分岐に到達する経路が構造的に存在しない」) で書き、専用テスト `test_control_capabilities_operation_has_no_reachable_deny_branch` を新設した。受け入れ監査は**残り 27 語すべてに到達可能な耐久 emit サイトが 1 つ以上ある**ことを全数確認し、到達不能のみの語が **0 件**であることを実行時実測 (`must_rotate=True` での `list_applications` / `list_credentials` は耐久行が立ち、`control_capabilities` は立たない) で裏取りした。
- **M-2 / M-4 / M-5 (低)** — 同型性 placeholder の解決経路、除外リストの空集合 2 つの pin、docstring の数え方 (「候補 8 − 3」→「U 31 − N 4 = D 27」) をそれぞれ修正した。
- **M-3 (低)** — 上記の keyword-only 化の拡張。手続き上の指摘であり、監督裁定で実装どおりとした。

**変異注入の結果**: 未宣言 literal の注入 = (e) 赤 / 位置渡し定義の追加 = (c) が **3 フィールドとも赤** (`event_class` の非後退を兼ねる) / 除外リストへの実在しない項目 = (i) 赤 / 除外定義からの自仮引数転送 = (ii′) 赤 / **D→N 降格 = 等式は緑のままスナップショットのみ赤** (設計の主張どおり) / legacy sink を耐久 sink へ差し替え = N の実行時テスト赤 / D への架空語追加 = (e) 赤 / 宣言 dict からのキー削除 = **in-process と実 HTTP の双方で赤** / peer の宣言版数を 1.4.0 へ戻す = 版数テスト赤 / in-process adapter の返す `operations` から 1 語落とす = **共通 1.5.0 条件付き vector が赤** (r2db 2 plug で非 vacuous であることの証明)。レビューは加えて (b′) の片枝変異、(b″) の再束縛、(b‴) の keyword passthrough 合成、除外リストを「監査面へ転送する定義の逃がし口」として使う変異を自作し、いずれも設計どおりの赤/緑になることを実測した。

**受理境界**:

- **走査器の N は「名指し除外」である**。(e) 等式 `U == D ∪ N` は、**D から抜いて同時に N へ足す縮小を検出できない** — 検出するのは宣言スナップショットテストだけであり、これは**一回きりの人手固定**である (変異で実測済み)。同型の限界がフェーズ4 の L4-11 で `event_class` について既に記録されており、本フェーズはそれを 2 フィールドへ**拡大した**ことになる (§11 L5-1)。
- **除外リストは「(c) の無差別性を名指しで緩める」機構である**。緩めた範囲そのものを (i)(ii′) が機械検証するが、**リストが伸び続けること自体が構造の表れ**である (§11 L5-2)。
- **`control_capabilities` の到達不能性の主張は半分だけが pin されている** — 構造側 (許可リストのメンバシップ) は assert されるが、`_authorize_role` の audit-role 分岐を実際に通す挙動側の裏打ちは無い。WP-3 も同型であり、両 peer 共通の既知の限界として受理した。

### 10.4 WP-3 — MitateDB の 1.5.0 出荷 (`3f2da59` → merge `98d2010`)

**状態**: **完了**。独立コードレビューの指摘 **7 件 (M-1〜M-3 = 中 3、L-4〜L-7 = 小 4)** を受けて**差し戻し 1 回**、その後 受け入れ監査を経てコミットした。root suite (単独実行) **1612 passed / 0 failed / 0 skipped / 0 xfailed**。ディレクトリ別内訳は MitateDB **489** / r2db **701** / conformance **422** = **1612**。

**増減内訳 (完了条件 16)**: WP-2 の収集 1588 (1586 passed + 2 xfailed) から **+24**。内訳は `MitateDB-api/tests/test_audit_query.py` の**削除 5 本** (`test_control_capabilities_declares_contract_version_1_4_0` と `event_class` 専用の走査規則テスト 4 本 — 後者は 3 フィールド parametrize 版へ吸収された) で **−5**、**追加 21 本**のうち 4 本が `_FIELDS` (3 語) で parametrize されるため **+29**、差引 **+24**。r2db 側と conformance 側の収集件数は不変である。**`xfailed` 2 → 0** の 2 本は `conformance-tests/test_c09_audit_evidence.py::test_c09_every_control_surface_adapter_declares_1_5_0` (WP-1 登録の全体 vacuity guard) と `r2db-api/tests/test_audit_query.py::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` (WP-2 登録の追随待ち placeholder) であり、**どちらも WP-3 の同一差分でデコレータのみを削除**し、本文は 1 行も弱めていない。**作業指示書 WP-3 完了条件 16 の本文は v1.7 で「xfailed 2 本 — 全体 vacuity guard と同型性 placeholder — が passed へ移る分を含む」へ訂正済み**であり、実態と一致する。**ただし同条件末尾の「監査照合」節 (指示書 v1.7 の 475 行) だけは依然「`xfailed` が 1 → 0 へ移った 1 本が…全体 vacuity guard と同名であること」と書いており、訂正が届いていない** — 実装側の欠陥ではなく指示書内の取り残しである (監督へ報告済み。本書では修正しない)。

**実際に採った形**:

- **語彙**: `operation` は **U 30 = D 29 + N 1**、N = **{`control_capabilities`}** (r2db の M-1 と同型の到達不能性)。`target_kind` は **U = D = 5、N = ∅**。`event_class` は D 12、N = ∅。宣言は `event_classes` と同じく **control 半分 (`audit_query.py`) + application 半分 (`application_audit.py`) の 2 モジュールの和**であり、変異はどちらの半分からも赤になることを実測済みである。
- **設計 §3 D-1 が名指しで求めた実測**: `auth.py` / `credential_store_postgres.py` の `operation="authenticate"` / `"assert_active"`・`target_kind="credential"` は**耐久表へ届く**と実測された (実 Postgres での観測を含む)。初期仮説「MitateDB に非耐久経路は無い」は `control_capabilities` の 1 語を除いて維持された。
- **製品変更**: `control_plane.py` の `_authorize_role` / `_gate_must_rotate` の `operation` を keyword-only 化 (**呼び出し 20 箇所**、レビュー L-7 の訂正値)。`http.py` のローカル変数 `operation` → `schema_operation` のリネーム ((d′) 違反の解消、挙動不変)。**emit ヘルパ 5 定義は無傷**であり、`audit_dispatch.py` は 1 行も変更されていない。除外リストは `cell.ApplicationCell._plan_operation` の **1 定義**。
- **flip と guard 撤去**: `cell.py` (data plane) / `control_plane.py` (control plane) の 2 箇所が `"1.5.0"`。全体 vacuity guard の `xfail` は**同一差分で撤去**され、**guard 本体は無改変** (`registered_adapters()` 走査 / 非空虚 assert / 全数要求は原形) のまま素で緑になった。宣言整合 vector は **4 plug 全数 (`r2db-api` / `r2db-api-http` / `MitateDB-api` / `MitateDB-api-http`) で 1.5.0 分岐に入り、各 plug で `events` = 3 件 (≥ 1) を観測**することを直接実測した。

**レビュー指摘 7 件の閉じ方 (差し戻し 1 回)**:

- **M-1 (中)** = 完了条件 7 が**語単位では満たされているがサイト単位では満たされていない** — `auth.py` の `authenticated=True` 分岐の耐久 write を落としても両 suite が全緑だった。**閉じ方**: `test_authenticate_and_assert_active_denials_are_durable_not_excluded` を新設し、**実在する資格情報を issue → disable → authenticate** して当該分岐を実際に通し、`actor_id` / `application_id` / `operation="authenticate"` を伴う耐久行を要求する形にした。Postgres 版は `credential_store_postgres.py:445` の `if not valid:` 側を同形で通す。**変異 12 (`auth.py:424` の `route_denial` ブロック除去) で赤**になることを監査が再現した。
- **M-2 (中)** = 同型性テストの正規化が**行頭インデントまで潰す** (`re.sub(r"[ \t]+", " ")`) ため、トークン列が同じでインデントだけが違う意味差 (走査規則の到達不能化) を検出できなかった。**閉じ方**: `_normalize` を行頭インデント保存形へ改めた。**変異 19** (MitateDB `_is_field_assignment_target` の `Attribute` 分岐をインデントだけで到達不能化) と、監査が独立に作った **追加変異 E** (`_collect_direct_shadow_names` の `return shadowed` をインデントだけで for ループ内へ移動) の**両方で両 peer 赤**。
- **M-3 (中)** = 実在しないテスト名を N の根拠に挙げていた (常設規律 3) + N の「観測的不在」テストが無い。**閉じ方**: 名前を実在するものへ訂正し、観測的不在のテストを置いた。
- **L-4 (小)** = 同型性の対象ヘルパ列挙に除外リスト検証器が入っていない。**閉じ方**: `_iter_field_definitions` / `_field_positional_definitions` / `_excluded_definition_forwards_its_own_parameter` の 3 本を追加し、**対象ヘルパは 11 個**になった (両 peer で正規化後 diff 空)。**ただしレビューが併せて名指しした `_ms_from_pg_timeout_text` は対象に入っていない** — 下記の受理境界と §11 L5-5 を見よ。
- **L-5 (小)** = `control_capabilities` 到達不能の主張が半分しか pin されていない。**閉じ方**: r2db と同型の既知の限界として**許容**し、両 peer のテストに「`role="audit"` 経路は構造的 pin のみで挙動は行使していない」旨の限界開示を入れた (常設規律 3 に適合)。
- **L-6 (小)** = 未使用 import。**閉じ方**: 削除。in-memory 側の局所 import から `PostgresApplicationAuditSink` が消え、Postgres 側テストでのみ import・実使用される形になった。
- **L-7 (小)** = keyword-only 化の報告値 18 → 20 の訂正。**閉じ方**: 監査が `self._authorize_role(` / `self._gate_must_rotate(` の呼び出しを全数数え、**20 件ちょうど・位置渡し 0** を実測した。

**M-2 / L-4 の是正は両 peer 同時に行った** — 同型性テストの対象そのものを触るためである。変異 18(a)/(b) (MitateDB 側 / r2db 側のどちらか一方だけを 1 箇所変える) で**どちら向きでも両 peer 赤**になることを実測した。

**変異注入の結果**: 対応表 18 行のうち、受け入れ監査が独立に再現したのは **10 行** (変異 1 の `operation` 版と `event_class` 版、10、12、14、15(a)、15(b)、18(a)、18(b)、追加 E) であり、いずれも期待どおりの赤/緑だった。**残り 12 行 (2〜9、11、13、16、17) はレビューと実装報告の実測に依拠しており、監査としての独立再現はない** — 証拠の由来を隠さずに記録する。特筆すべき実測は、**変異 15(a)** (`cell.py` の data plane だけを `1.4.0` へ戻す) が**ローカル pin だけを赤にし全体 guard は緑のまま**であること (作業指示書 v1.6 の訂正どおり、guard は control plane の宣言のみを見る) と、**変異 15(b)** (`control_plane.py` の control plane を戻す) が**ローカル 3 本 + 全体 guard を赤**にすること — 撤去後の guard が素で load-bearing であることの実測である。

**受理境界 (この WP で「固定しない」と決めた点)**:

- WP-2 と同じ 3 点 (**N は名指し除外** / **除外リストの保守** / **`control_capabilities` の到達不能性は半分だけ pin**) がそのまま当てはまる。3 点目は L-5 の裁定として明示的に受理した。
- **同型性テストの対象範囲は「兄弟 peer の `test_audit_query.py` を読む」形に閉じている**。作業指示書 (WP-2 条件 16 / WP-3 条件 17) が名指しした `_ms_from_pg_timeout_text` は、実測では **MitateDB `tests/test_application_audit.py:88` にのみ存在し、r2db には同名の定義が無い** (r2db 側は adapter timeout テスト内の複製である)。レビュー L-4 の「両 peer に存在しない」という認識は不正確で、正しくは「**片 peer にのみ存在し、かつ同型性テストが読む `test_audit_query.py` とは別モジュールにある**」。現行実装 (`this_module` の `getattr` + 兄弟の `test_audit_query.py` 只読み) では**構造的に対象にできない**ため、条件 17 は字義どおりには満たされていない。§11 **L5-5** として起票し、監督裁定 (指示書の文言の誤りか、走査範囲を広げるか) を仰ぐ。
- **同型性テストのソース取得方式が左右非対称である**。MitateDB 側は `inspect.getsource` (デコレータを含む)、r2db 側は `ast.get_source_segment` (`FunctionDef.lineno` 起点でデコレータを**含まない**)。対象 11 ヘルパは現在いずれも無デコレータのため実害はないが、将来どちらかにデコレータが付くと**実装差ではなく取得方式差で赤/緑がぶれる**。§11 **L5-6**。
- **完了条件 15 (対応表 18 行全数) の証拠は一様ではない** — 上記のとおり監査が独立再現したのは 10 行である。とくに**対照行 2 本** (変異 7 の `Constant` 対照 / 変異 9 の guard 弱化) が「緑になってしまうこと」の実測は実装報告側にのみ存在する。

### 10.5 WP-4 — Q3 (MitateDB の request-count limit 上限撤廃、`d11c86f`)

**状態**: **完了**。契約は 1 バイトも変わっていない (`spec/` 配下は差分に 1 件も含まれない)。root suite (単独実行) **1611 passed / 0 failed / 0 skipped / 0 xfailed**。

**実際に採った形**:

- **上限撤廃 (4 クラス)**: `MitateDB-api/src/mitatedb_api/control_plane.py::ControlPlaneLimits.__post_init__` から `[1, 200]` の受理レンジを撤廃し、`applications` / `credentials_per_application` / `control_requests_per_minute` / `audit_requests_per_minute` の **4 クラスすべてを「正の整数であること」だけの検査**へ揃えた (r2db `ControlPlaneLimits.__post_init__`、`r2db-api/src/r2db_api/limits.py` と対称)。**エラー文言は `must be a positive integer`** — r2db と同一文言であり、存在しない受理域を述べる文言をコード・docstring・配備文書から掃討した。
- **据え置いたもの**: 既定値 `control_requests_per_minute: int = 200` は**受理レンジではなく既定値**であり据え置き。**関係検査** `control_requests_per_minute > applications + 2 × credentials_per_application + 67` は独立に残る。`request_bytes` の別建て検査と既定値 (MitateDB 65536 / r2db 1_048_576) も不変 — **peer 間の既定値差は据え置くと裁定済み**である。
- **テストの差し替え**: `201` を渡す拒否ケース **3 件を削除**、下限 `0` ケースを **4 クラスに parametrize** (従来は 3 クラス分しか無く、4 番目のクラスの下限は一度も直接テストされていなかった — §11 の該当項目の裏返し)、**`test_limits_accept_generous_values_beyond_the_former_ceiling` を新設** (r2db `_GENEROUS_LIMITS` と同型。`control_requests_per_minute=100_000` を実際に構築し、**関係検査を同時に満たす**値で受理されることを見る)。`test_limits_reject_control_requests_per_minute_too_close_to_the_margin` は緑のまま。
- **conformance への非影響**: `MitateDB-api/conformance/conformance_adapter_mitatedb.py:378` の構成 3 値は**据え置き**、更新したのは `:366` と `conformance_adapter_mitatedb_http.py:658` の**コメントのみ**である。共通 suite の `_MAX_EXERCISABLE_LIMIT` (`conformance-tests/test_c14_authority_boundary.py:142` の `200`) も不変。**conformance の収集件数は 422 のまま**であり、設計 §6.4 の非影響判断が実測で裏づけられた。
- **文書**: `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2c を撤廃後の実コードに合わせて書き換え、**運用者責任 (上限は誤設定に対する防波堤でもあり、外せばその防波堤は無くなる)** を `MitateDB-api/docs/cloud-run-cloud-sql.md` / `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15 / `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` の **3 文書**に記載。`security/CONTROL_MAPPING.md` SI-08 行は**両 cell を対で**書き換え、「要求される安全結果」を述べる部分は変更していない。

**変異注入の結果 (対応表 7 種のうち 5 種が実測済み)**:

- **変異 1** (上限の復活) = **赤** (`test_limits_accept_generous_values_beyond_the_former_ceiling`)。あわせて撤廃後のコードで `201` を渡す構築が**受理される**ことを確認した — 受理域が実際に広がったことの実測である。
- **変異 2** (正の整数検査の消滅) = **`0` ケース 4 件すべて赤**。
- **変異 3** (エラー文言を `[1, 200]` を述べる旧表記へ巻き戻す。検査そのものは正の整数のまま) = **赤** — 下限テストが `match=` で文言を逐語に見ていることの実測。
- **変異 4** (関係検査の除去) = **赤** (`test_limits_reject_control_requests_per_minute_too_close_to_the_margin`) — 上限撤廃が関係検査を巻き添えにしていないことの実測。
- **変異 5** (`audit_requests_per_minute` の 1 クラスだけ検査を外す) = **`0` ケース 4 件のうち当該 1 件だけが赤**、他 3 件は緑 — 4 クラス化した下限ケースが load-bearing であることの実測。
- **変異 6 / 変異 7 は未実測である (隠さずに記録する)**。**変異 6** = adapter 構成値 (`conformance_adapter_mitatedb.py:378`) の 1 箇所改変、**変異 7** = 共通 suite の `_MAX_EXERCISABLE_LIMIT` の改変。どちらも**赤化が観測できるのは C-14 vector 5 経由だけ**であり、**その駆動コストが構成値に比例して伸びる**ため、実行は 1 時間を超えた時点で打ち切った (参考実測: 現行の構成値のままでも `conformance-tests/test_c14_authority_boundary.py` の 4 件だけで **248.68 秒**を要する)。**これは設計 §6.4 が「adapter 構成値を据え置く」と決めた根拠そのもの**である — 構成値を上げれば C-14 vector 5 の駆動が実用外になる。対応する**完了条件 7 / 8 (構成値と `_MAX_EXERCISABLE_LIMIT` が不変であること) は、変異ではなく diff / grep 照合で担保した**。§11 **L5-7** として起票する。

**受理境界 (この WP で「固定しない」と決めた点)**:

- **上限という防波堤を意図的に外した**。`audit_requests_per_minute` に桁違いの値を置いた配備を製品コードは止めない。依頼者設計原則 3「制約で回避しない」に沿って**代償を承知のうえで引き受けた**ものであり、「対応不要」ではない — 手当ては runbook 3 文書と `CONTROL_MAPPING.md` SI-08 行の**運用者責任の記載だけ**である。
- **完了条件 7 / 8 は変異で load-bearing を実測していない** (上記 変異 6/7)。据え置きの事実は照合で確かめたが、「据え置いた値が実際に効いている」ことの実測は本 WP には無い。
- **`request_bytes` の検査ループ位置の非対称は残る** (r2db は共通ループ、MitateDB は `__post_init__` 内の別建て)。D-3 で数値レンジの非対称は消えたが、この構造の非対称は本 WP の射程外である (§11)。

---

## 11. 将来課題

**フェーズ5 で新たに起票した項目 (L5-1〜L5-7)**

- **L5-1 宣言の D→N 降格はスナップショットテストだけが検出する (両 peer、`operation` / `target_kind` の 2 フィールド分)**。(e) 等式 `U == D ∪ N` は「D から抜いて同時に N へ足す」縮小に対して緑のままである。検出するのは宣言スナップショットテスト (`test_declared_audit_operations_change_only_deliberately` 等) だけであり、これは**テスト側に写した集合との一回きりの人手固定**である。フェーズ4 の **L4-11** が `event_class` について記録した限界と**同型**であり、本フェーズはそれを 2 フィールドへ拡大した。L4-11 と同じ手当て (スナップショット) を置いてあるので新しい穴ではないが、**手当ての性質が「人手で写した集合」である**ことは変わらない。
- **L5-2 `_NON_AUDIT_<FIELD>_PARAMETERS` 除外リストの保守**: `operation` は監査専用語ではない (識別子出現数 r2db 335 / MitateDB 280) ため、非監査の `operation` 仮引数を持つ定義が今後増えれば除外リストも増える。**現況は r2db 8 定義 / MitateDB 1 定義**である。リストの検証テスト ((i) 実在性 + (ii′) 自関数仮引数の非転送) がこれを機械的に見張り、**除外を「監査面へ転送する定義の逃がし口」として使えないこと**も変異で実測済みだが、**リストが伸び続けること自体が「(c) の無差別性が `operation` については素直に効かない」という構造の表れ**である。伸びが目立つようなら、監査フィールドを別名 (`audit_operation` 等) にする案を再検討する材料になる。
- **L5-3 契約内の第 3 の `operations` 用法は曖昧解消文の射程外**: 依頼者確定の曖昧解消文は `capabilities().audit_query.operations` の衝突相手として `capability_status.defined.atomic_mutation.operations` **のみ**を名指す。契約内には**第 3 の用法**として `schemas.MutationRequest.properties.operations` と `schemas.ScopedMutationRequest.properties.operations` (どちらも mutation 配列のリクエストボディ) が実在する。**確定文は逐語で入っており文字列ピンで固定されているので本フェーズでは変更しない**。宣言を機械的に読む AI エージェント統合者が `audit_query.operations` をリクエストボディの `operations` と取り違える危険は、親キー `audit_query` によるスコープと曖昧解消文の 1 文で実際には十分に小さいと判断したが、**次に契約文を触るときに射程を広げるかどうか**の判断材料として記録する (WP-1 受け入れ監査 観察 O-1)。
- **L5-4 D-2 vector の `provided` 分岐は同居宣言を adapter の申告で信じる**: `control_surface_cohosted_with_data_plane()` が `True` を返す plug では、data ホストの alias が `audit_query` を提供しても適合と判定される。**申告を独立に検証する機構は無い**。現時点では 4 plug とも `False` を返すため実害は無く (常に `AUTH_INVALID` 側で判定されている)、`CONDITIONS.md` の C-09 行に開示済みだが、**将来 co-hosting 配備の plug が登録されたときに初めて load-bearing になる**分岐である。そのとき申告の独立検証をどう置くかは未決である。
- **L5-5 同型性テストの対象に、兄弟ファイルの外にある同名ヘルパが入らない**。`test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` は **`this_module` の `getattr` + 兄弟 peer の `tests/test_audit_query.py` の只読み**という形であり、対象は現在 **11 ヘルパ**である。作業指示書 (WP-2 完了条件 16 / WP-3 完了条件 17) が名指しした **`_ms_from_pg_timeout_text` はこの形では構造的に対象にできない** — 当該ヘルパは **`MitateDB-api/tests/test_application_audit.py:88` にのみ存在し、r2db 側には同名の定義が無い** (r2db では adapter timeout テストの中に複製がある)。WP-3 レビュー L-4 の「両 peer に存在しない」という認識は不正確であり、正しくは「**片 peer にのみ存在し、かつ同型性テストが読むファイルとは別モジュールにある**」。したがって **WP-3 完了条件 17 は字義どおりには満たされていない**。取りうる手当ては (i) 指示書の文言の誤りとして条件から外す、(ii) 同型性テストの走査範囲を `test_audit_query.py` 以外のテストモジュールへ広げる、(iii) 複製を解消して片方へ寄せる、のいずれかであり、**監督裁定待ち**である。走査範囲を広げる場合、「兄弟 peer に対応物が無いヘルパをどう扱うか」(欠落を赤とするか、対象から外すか) を先に決める必要がある。(WP-3 受け入れ監査 §5-1)
- **L5-6 同型性テストのソース取得方式が左右非対称である**。MitateDB 側は `inspect.getsource` (デコレータを**含む**)、r2db 側は `ast.get_source_segment` (`FunctionDef.lineno` 起点なのでデコレータを**含まない**) で本文を取得している。対象 11 ヘルパは現在いずれも無デコレータのため**実害はない**が、将来どちらか一方にデコレータが付くと、**実装の差ではなく取得方式の差で赤/緑がぶれる** — 同型性テストが守ろうとしている性質 (両 peer の器が同じ形であること) とは無関係な理由で偽の赤が出る形である。両 peer で取得方式を揃える (どちらかへ寄せる) のが手当てだが、**M-2 / L-4 と同じく両 peer 同時に触る必要がある**ため、単独の小修正としては起こさず記録に留める。(WP-3 受け入れ監査 §5-5)
- **L5-7 WP-4 の変異 6 / 7 は実測コストが禁止的であり、対応する完了条件は照合で担保している**。**変異 6** (conformance adapter の構成値 `conformance_adapter_mitatedb.py:378` の 1 箇所改変) と **変異 7** (共通 suite の `_MAX_EXERCISABLE_LIMIT`、`conformance-tests/test_c14_authority_boundary.py:142` の `200` の改変) は、**赤化を観測できる経路が C-14 vector 5 しかなく、その駆動コストが構成値に比例して伸びる**。実行は 1 時間を超えた時点で打ち切っており、**両変異とも未実測である** (参考: 現行の構成値のままでも当該ファイルの 4 件で 248.68 秒)。**これは設計 §6.4 が adapter 構成値を据え置くと決めた根拠そのもの**であり、欠落というより構造の表れである — 構成値を上げれば C-14 vector 5 の駆動が実用外になる。対応する **WP-4 完了条件 7 / 8 は「値が動いていないこと」の diff / grep 照合で担保**しており、「据え置いた値が実際に効いている」ことの実測は本フェーズには無い。次に C-14 vector 5 に触るときは、**位置算術を構成値に比例しない形へ作り替える** (例: 上限そのものではなく、上限に対する相対位置だけを駆動する) かどうかが判断事項になる。それができれば変異 6 / 7 が実用時間で実測できるようになる。
- **L5-8 下限検査の peer 非対称 — MitateDB は `bool` を拒否し、r2db は受理する**。WP-4 レビュー F-5 の実測: 上限撤廃後の MitateDB `ControlPlaneLimits.__post_init__` は `applications=True` のような `bool` を拒否するが、**r2db `r2db-api/src/r2db_api/limits.py:141` は `True` を「正の整数 1」として受理する** (`bool` は Python では `int` の subclass であり、`isinstance(v, int) and v > 0` を素通りする)。D-3 が消したのは**数値レンジ**の非対称であって型検査の厳しさの非対称ではなく、**上限撤廃によってかえって表に出た**形である。契約は request-count limit のレンジも受理型も宣言していないため**双方適合**であり、実害としては「設定を `true` と書き間違えた配備が r2db では上限 1 として黙って起動する」程度だが、**同じ設定ミスが peer で違う結果になる**ことは運用者から見て素直ではない。対称化するなら r2db 側に `type(v) is int` 相当の検査を足す形になるが、**既存の設定経路で `bool` を渡している配備が無いことを先に確かめる必要がある** (後方非互換になりうる)。本フェーズの射程外として次回へ送る。

**フェーズ5 起草時から持ち越している項目**

- **走査器一般化に伴う `event_class` 側の回帰**: 3 フィールドを 1 実装で扱う一般化は、`event_class` について P4-D16 v3 が固定した性質 (無差別 literal 規律 / keyword-only 保証 / dict 密輸禁止 / 語彙関係の厳密一致) を後退させ得る。WP-2 / WP-3 の**変異注入**で、一般化前に赤化していた変異がすべて一般化後も赤化することを確認する。 **WP-2 の実測 (v1.4)**: 位置渡し定義の追加変異と代入密輸の変異はいずれも **3 フィールドとも赤**であり、WP-B1 の synthetic 回帰 4 種も現存・同内容で残っていることをレビューが確認した。唯一の意図的緩和は (b″) の「ローカル変数への 1 回きりの Constant 束縛」であり、U 帰属が転送元へ移っても literal が漏れないことを変異で実測してある。 **WP-3 の実測 (v1.5)**: `event_class` 専用だった走査規則テスト 4 本は `_FIELDS` (3 語) の parametrize 版へ**吸収**され、消えていない (収集は −5 本 / +29 本の内訳で説明済み)。**変異 1 を `event_class` に対して実施** (`auth.py` の `event_class="authentication_denied"` を未宣言語へ) すると `test_declared_event_classes_cover_every_emittable_class` が**赤**であり、一般化後も `event_class` の (e) 等式が load-bearing であることを実測した。`test_event_class_forward_exclusion_requires_genuine_parameter_binding` のような `event_class` 固有のテストは parametrize 版とは別に**存置**されている。**走査対象フィールド集合そのものを pin するテスト** (`test_scanner_is_parameterized_over_exactly_these_three_fields`) は MitateDB 側にも置かれ、`_FIELDS` から `target_kind` を落とす変異 10 で**赤 + 収集 60 → 56** (parametrize 4 本 × 1 減) になることを実測した。**したがって本項目 (一般化による `event_class` 側の回帰) は両 peer で確認済みであり、閉じている。**
- **`_NON_AUDIT_<FIELD>_PARAMETERS` 除外リストの保守** — **本項は上の L5-1〜L5-4 の L5-2 へ引き継いだ** (v1.4)。実測値 (r2db 8 定義 / MitateDB 1 定義) と、除外を逃がし口として使えないことの変異実測を L5-2 に記す。
- **走査器の実装は peer 内コピーである**。両 peer に同型の器を置くが、**peer 間でコードを共有しない**慣行を維持する。一般化によって両者の器はさらに似るため、片方だけの修正が他方へ伝わらない危険は増す — 変更時は必ず両 peer 同時に扱う。
- **`audit_requests_per_minute` の上限は元々テストされていなかった**: MitateDB の `201` 拒否テストは 3 クラス分しか無く、4 番目のクラスの上限は一度も直接テストされていない (§1.4 の 6 の裏返し)。D-3 で上限自体が消えるため実害は無くなるが、「クラスを増やしたときに既存の検査へ載せ忘れる」という形の欠落は他所でも起こり得る。
- **`request_bytes` の検査ループ位置の非対称 (D-3 で触れない第 2 の小非対称)**: r2db は `request_bytes` を他の 4 クラスと同じ「正の整数」検査ループに畳んでいるが、MitateDB は `__post_init__` の中で別建てに検査している。D-3 で数値レンジの非対称は消えるが、この構造の非対称は残る。実害は見えていない。
- **Q4 は本フェーズに入らない**: `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合 (宣言は control プロセス、実効値は data-plane プロセス) は、`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4 の監督推奨どおり**独立の設計フェーズ**として残る (両 peer 同時、設計文書 + migration)。
- **L4-8 (C-09 vector 4 の据え置き)** と **L4-12 / L4-13** は本フェーズの対象外であり、`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 が引き続き保持する。
- **1.4.0 alias の除去**: 従属判断 9 項目 7 の再検討条件 — `endpoints.audit_query` (`POST /v1/audit/query`) の alias を 1.5.0 以降に除去するかどうかは別途裁定する。**本フェーズでは除去しない** (D-2 は alias が data ホスト上にも存在し続けることを前提に、そこでの credential の扱いを定めている)。
