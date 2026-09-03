# フェーズ4 台帳消化 作業指示書 — 契約非変更で閉じられる項目の両 peer 対称化

- 版数: v1.5 (2026-09-03。v1.0 = 起草。v1.1 = 疑義 3 件への監督裁定を反映。v1.2 = **独立レビュー round1 の実測を受けた監督裁定を反映** — P4-D16 の「三方向一致」を**撤回**し v3 (無差別 literal 規律 + 定義側 keyword-only 保証 + dict 密輸禁止 + `U == D ∪ N`) へ差し替え、P4-D15 に「変わるもの (N-2 バックオフ)」と旧根拠コメントの書き換えを追加、WP-B3 の WP-A1 依存を明記、WP-B4 の変更対象を拡張、本数勘定を「収集件数」へ)。v1.3 = **WP-B1 レビュー M3/M6 反映** — P4-D16 v3 (b)/(d) の転送除外規則を「`ast.Name` で `id == "event_class"`」から「囲む関数定義の仮引数束縛を検証した転送のみ」へ厳格化し、それ以外の値ノード (ローカル変数/global/for ターゲット/walrus 由来の同名 `Name`、`JoinedStr`、`BinOp`、`Call` 等) をすべて違反とした。 v1.4 = **受け入れ監査 M7 反映** — P4-D16 v3 (d) に、全スコープ (モジュール/クラス/関数本体いずれも) の `event_class` への `Assign`/`AnnAssign`/`AugAssign` を対象とする走査を追加し、`class _Cfg: event_class = "zz"` からの `Attribute` 転送のような未検査の書き込みを塞いだ。 v1.5 = **受け入れ監査 M8 反映** — `_collect_direct_shadow_names` (両 peer) を個別統語形の列挙から「関数本体内で `event_class` という名前を束縛するあらゆる形 (ctx=Store/Del の `Name` 全件、`alias.asname`、`ExceptHandler.name`、`MatchAs`/`MatchStar`/`MatchMapping` の capture、ネスト `def`/`class` の名前、`Global`/`Nonlocal`)」への一般原則へ再設計し、`with ... as event_class:` / `except ... as event_class:` を含む未検出の再束縛経路を塞いだ。
- 正本設計: `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (v1.5。本書の WP-B4 で v1.6 へ)。**本書は WP 分割と発注のみを扱う** — 裁定の根拠・却下案・実装の具体形は設計文書が正本であり、本書はそれを重複させない
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260903_FABLE.md` (第10次。フェーズ4 完了時点、root suite **1526 passed / 0 failed / 0 skipped / 0 xfailed**)
- 体制: Fable 監督/判断/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー/証拠監査
- 先行作業指示書: `docs/work-orders/PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md` (v1.2)。§4 (完了ゲートの実測規律)・§6 (禁止事項)・§7 (コミット規律) は本書 §6〜§8 が引き継ぐ

---

## 0. 問題設定

フェーズ4 は WP-0〜WP-4 まで完了し、将来課題台帳 (設計 §11.1) に **L4-1〜L4-9** が起票された。本書はそのうち **共通契約 (`spec/`) を一切変えずに、実装・テスト・記録だけで閉じられる項目**を、**両 peer 対称に**閉じる。

**契約は変えない。** したがって `spec/data-service-api.v1.json` の `contract_version` は **1.4.0 のまま**であり、`spec/CCR_DISPOSITION.md` に新しい従属判断を起こさない。契約変更を要する項目は本書 §2 のとおり範囲外である。

本書が閉じるのは以下である。

| 台帳項目 | 内容 | 閉じ方 | WP |
|---|---|---|---|
| **L4-3** | `failing` フラグの貼り付き (両 peer 同型) | 製品コード 1 箇所 × 2 peer + テスト | WP-B2 |
| **L4-5** | 宣言語彙 AST 走査のファイル列挙漏れ・callee 名キーを機械検出できない (両 peer 同型) | 無差別 literal 規律 + 定義側 keyword-only 保証 + dict 密輸禁止 + `U == D ∪ N` (テスト + r2db の呼び出し規約 keyword-only 化) | WP-B1 |
| **L4-6** | HTTP conformance adapter の書き手 timeout 設定漏れを検出できない | peer-local テストのみ (port は変えない) | WP-B3 |
| **L4-7 (i)(ii)** | peer 間のテスト名レベル非対称 2 件 | MitateDB にテスト追加 | WP-B3 |
| **L4-8** | C-09 vector 4 の射程が未決 | **据え置き** — 射程を「共通 port の構造保証」と明示 (記録のみ) | WP-B4 |
| **L4-9** | vector 1 の同定キーが `event_id` 単独 | **既に解消済み** (WP-1 `09233dd`)。RESOLVED と記す | WP-B4 |
| **L4-10** (新規) | r2db `control_main` が `request_bytes` を env から配線していない (peer 非対称) | r2db に env 配線を追加 + テスト + 配備記録 | WP-B3 |

---

## 1. 監督裁定 (確定。設計 §5.1 へ P4-D15〜P4-D18 として追記する)

### P4-D15 (L4-3) `failing` フラグは「最後に**完了した** flush 試行の結果」を表す

現行の解除条件は「flush 成功 **かつ** buffer が完全に排出された」であり (設計 P4-D12 の後半)、継続負荷下では buffer が空にならないため sink が実際に回復した後もフラグが立ち続ける。**裁定**: flush 成功時は buffer の残量に関係なく `_flush_currently_failing = False` にする。

**並行 flush の懸念への回答** (WP-3(a) レビュー m-1 = 「別 batch の失敗中 flush のバックオフが、成功側の race で床に戻る」): これは**完了順序の意味論**で吸収する — 後から完了した失敗 flush が再度 `True` にする。一瞬 `False` になる窓で `_retry_alert` が走っても、alert 試行は `alert_min_interval_s` (flush 間隔) に律速されたままであり、**alert 行の上限「flush 間隔あたり最大 1 行」は破れない**。

**変わらないもの**: 証拠 (`count` への欠落数の累積 — `_dropped_total` の減算は `_flush_currently_failing` を一切参照しない)。alert 行の上限「flush 間隔あたり最大 1 行」(`_retry_alert` の `alert_next_retry_at` の床は独立に効く)。runbook の「回復は当該ペアの回復メッセージで読む」という指示も**据え置く** — 回復メッセージがより早く出るようになるだけである。

**変わるもの (意図した代償)**: **N-2 の指数バックオフは、成功 flush が挟まるたびに床へ戻る。** sink が**フラッピング**している場合 (成功と失敗が交互に完了する)、alert 行のレートは「60s に 1 行」(バックオフ上限に張り付いた現行) から「`alert_min_interval_s` = flush 間隔に 1 行」(r2db 既定 2s) へ**上がり得る**。**これは P4-D15 が意図して受け入れる代償である** — 部分的に書ける sink には証拠 (`count`) を早く書くほうがよく、宣言上の上限「flush 間隔あたり最大 1 行」は破れない (実測値が上限に張り付くだけで、容量算式は安全側のまま)。WP-B2 完了条件 1 は、この床への復帰を**明示的に要求している**。

両 peer 同型の変更である (r2db `service.py` `_AuditBuffer.flush` の成功分岐、MitateDB `audit_dispatch.py` の同分岐)。

### P4-D16 v3 (L4-5) 宣言語彙走査は「無差別 literal 規律 + 定義側 keyword-only 保証 + dict 密輸禁止 + 語彙関係の厳密一致」で閉じる

**v2 (「三方向一致」) は撤回する。** 独立レビュー round1 が現行コードに対して実測し、緑にできないことが判明したためである — (i) 定義集合に `append` が入り、パッケージ内のあらゆる `list.append()` が違反になる (r2db 36 件 / MitateDB 46 件)、(ii) MitateDB の `control_audit` 書込みは `append_audit(**fields)` / `audit_append` という**転送ラッパ**を通るため定義集合に入らず、実 emit サイト 13 件が「未知の emit 面」として違反になる、(iii) r2db `_control_event` の語彙 `control_failure` / `control_state` は**レガシーの in-memory sink 専用**で耐久表へ届かないため、宣言へ足せば `audit_query` が決して返さない語彙を公開する嘘になる (同型の非耐久語彙が `_event` の `authentication` にもある)。

**診断で判明した事実 (v1 から継続)**: MitateDB には**同名の走査テストが 2 本**あり、`MitateDB-api/tests/test_application_audit.py:872` 側は手書きの 4 ファイル列挙 (`_SOURCE_FILES_WITH_EMIT_SITES`、同ファイル :838) で走るため `src/mitatedb_api/http.py:418-419` の実 emit サイトを見ていない。r2db 側は `glob("*.py")` の**非再帰**かつ **callee 名キー付き** (`_EVENT_CLASS_CALL_SPECS`) である。

**裁定**: 両 peer で以下 (a)〜(f) を満たす形へ揃える。**callee 名フィルタは使わない。**

- **(a) 走査対象** — `src/<pkg>` 配下の全 `.py` を **`rglob` で再帰列挙**する。**手書きファイル列挙は廃止**する。**callee 名フィルタは使わない。**
- **(b) literal 規律 (無差別)** — パッケージ内の**全 `Call`** について、キーワード引数 `event_class` の実引数は**文字列 `Constant`、または囲む関数定義の仮引数束縛を検証した転送のみ許容**し、それ以外はすべて失敗とする (v1.3、WP-B1 レビュー M3/M6)。転送として許容されるのは以下のみである。
  - `Name(id="event_class")` であり、**その名前が囲むいずれかの関数定義の `posonlyargs + args + kwonlyargs` に実在する仮引数として束縛されている**もの。ローカル変数代入・`global`/`nonlocal` 宣言・`for` ターゲット・walrus (`:=`) で同名を作った場合は、たとえ同じ関数が `event_class` を仮引数に持っていても**転送とは認めず違反**とする (Python 自身のスコープ規則 — 関数本体のどこかで代入/for/walrus/global 宣言された名前は関数全体でローカルになる — に倣う)。
  - `Attribute(attr="event_class")` (例 `event.event_class`) および `Subscript` で添字が文字列 literal `"event_class"` であるもの (例 `row["event_class"]`) — これは READ 側 (D-6/D-7 の `audit_query` 応答整形、r2db `audit_query.py`/`control_plane.py`、MitateDB `audit_query.py`) が、すでに耐久書込み時に検証済みの値をそのまま読み戻す形であり、新しい literal を生成し得ないため転送と同格に扱う。
  旧規則 (`ast.Name` で `id == "event_class"` であれば無条件に転送とみなす) は、囲む関数の仮引数束縛を検証していなかったため、`event_class = "<未宣言語>"` のようなローカル変数代入からの転送を誤って許容していた (WP-B1 レビュー M3)。**現行の違反はゼロ**である (両 peer とも本規則に違反する `event_class=` は 0 件)。
- **(c) 定義側 keyword-only 保証** — パッケージ内の**全 `FunctionDef` / `AsyncFunctionDef`** について、仮引数 `event_class` を持つものは、それを **keyword-only (`*` の後) で宣言していなければ失敗**とする (メソッドの `self` は判定から除く)。これにより **位置渡しの emit 面は構文的に存在し得なくなる** — 「走査が見ていない emit サイト」の主要形が構造的に消える。定義集合を作らないので、(v2 で破綻した) `list.append` や転送ラッパの誤検出も起きない。
- **(d) dict 密輸禁止** — パッケージ内の**全 `Dict` literal (キー literal `"event_class"` を持つもの) と全 `Subscript` 代入 (`x["event_class"] = ...`)** について、値は**(b) と同じ転送規則を満たす場合のみ許容**し、それ以外 (文字列 `Constant`、`JoinedStr` = f-string、`BinOp`、`Call` の戻り値、束縛を満たさない `Name`、`event_class` 以外を指す `Attribute`/`Subscript` 等) は**すべて失敗**とする (v1.3、WP-B1 レビュー M3/M6 — 「値が文字列 `Constant` のときのみ失敗」という旧規則を反転した)。走査対象 (`Dict` literal と `Subscript` 代入) 自体は変えない。これは `**{"event_class": "..."}` で (b) の走査を迂回する経路、および f-string 等の非 literal・非転送値が dict 経由で紛れ込む経路の両方を閉じるためである。**現行の違反はゼロ**である (両 peer の該当サイトはすべて (b) と同じ転送規則を満たす)。
  - **(d′) 代入走査 (v1.4、受け入れ監査 M7)** — 上記に加え、パッケージ内の**全スコープ (モジュール直下・クラス本体・関数本体のいずれも区別しない、単純な無条件 `ast.walk`)** にある**全 `Assign`/`AnnAssign`/`AugAssign`** について、ターゲットが (タプル/リスト/starred 分解後に) `Name(id="event_class")` (モジュール/クラスレベルの `event_class = "..."` を含む) または `Attribute(attr="event_class")` (`self.event_class = "..."` を含む) であれば、その**値も (b) と同じ転送規則を満たす場合のみ許容**し、それ以外は失敗とする。**動機**: `Attribute(attr="event_class")` の READ 側転送は無条件に許容されるため (上記 (b) の第二項)、`class _Cfg: event_class = "zz"` のように未宣言 literal を**書き込む側**が無検査のままだと、`event_class=_Cfg.event_class` という呼び出しが (b)(c)(d)(e) すべてを緑のまま通過してしまう (受け入れ監査 M7 で実測)。**現行の違反はゼロ**である (両 peer とも `event_class` への Assign/AnnAssign/AugAssign は仮引数束縛済み転送形のみ)。
- **(e) 語彙関係の厳密一致** — (b)(c)(d) により、literal の全集合 **U** は (b) の走査で**完全に列挙できる** ((c) が位置渡しを、(d) が dict 密輸を塞いだため、literal の逃げ道が残らない)。テストは各 peer で U を求め、**`U == D ∪ N` かつ `D ∩ N == ∅`** を厳密に固定する。
  - **D** = 宣言 `event_classes` — r2db は `r2db-api/src/r2db_api/audit_query.py:53` `DECLARED_AUDIT_EVENT_CLASSES`、MitateDB は `MitateDB-api/src/mitatedb_api/audit_query.py:76` `DECLARED_AUDIT_EVENT_CLASSES` (`_CONTROL_PLANE_EVENT_CLASSES` と `application_audit.DECLARED_AUDIT_EVENT_CLASSES` の和)。
  - **N** = **明示の非耐久除外集合**。テスト内に**列挙し、各要素に「耐久表へ届かない根拠」をコメントで付す**。
    - **r2db N = `{"authentication", "control_failure", "control_state"}`** — `control_failure` / `control_state` は `_control_event` (`service.py:1356`) が legacy in-memory sink `self._service._audit` にのみ書く語彙であり耐久表へ届かない。`authentication` は `_event` (`service.py:819`) の同型の非耐久語彙である。根拠は `_event` 自身のコメントと `audit_query.py:50-52` の `DECLARED_AUDIT_EVENT_CLASSES` 注記。
    - **MitateDB N = ∅** — 診断ノートどおり全 emit が耐久経路に載る。
  - 新しい literal が現れたら、実装者は「**宣言する (D へ足す) か、N に名指しで足すか**」を強制される。**黙って見えなくなる経路は無い** — これが L4-5 の閉じ方である。
- **(f) 両 peer の同型化** — MitateDB の同名 2 本は **1 本に統合**する (どちらへ残すかは実装裁量)。r2db の `_EVENT_CLASS_CALL_SPECS` 方式は**廃止**し (a)〜(e) へ置換する。両 peer の走査ヘルパは**同型**にする。

**唯一の製品コード変更 = `event_class` を受ける関数の keyword-only 化 (挙動不変)**。(c) に現行で違反するのは **r2db のみ 2 面**である (MitateDB は違反ゼロ):

| 定義 | 呼び出しサイト | 語彙 |
|---|---|---|
| `r2db-api/src/r2db_api/service.py:1356` `_control_event(self, event_class: str, ...)` | **11 件** (`:1269` `:1271` `:1279` `:1281` `:1313` `:1315` `:1330` `:1332` `:1343` `:1351` `:1353`) | `application_lifecycle` / `credential_lifecycle` / `control_failure` / `control_state` |
| `r2db-api/src/r2db_api/service.py:1112` `_event(self, context, event_class: str, ...)` | **10 件** (`:819` `:952` `:955` `:1001` `:1004` `:1027` `:1030` `:1045` `:1048` `:1076`) | `authentication` / `data_operation` / `authorization_denial` / `operation_denial` / `privilege_sensitive` / `privilege_denial` |

いずれも `*` を入れて keyword-only へ変え、呼び出し **計 21 件**をキーワード渡しへ揃える。**走査に例外を彫り込んで回避しない** (依頼者設計原則 3)。

**(e) が現行コードで成立することの実測**: 上記 keyword-only 化の後、r2db の U は 14 語、D は 11 語、N は 3 語で **`U == D ∪ N` / `D ∩ N == ∅` が成立する**。MitateDB は U = D = 12 語、N = ∅ で成立する。**したがって (e) は宣言側を一切変えずに緑にできる** — 宣言に非耐久語彙を足す必要は無い (v2 が破綻した点)。

### P4-D17 (L4-6) HTTP conformance adapter の書き手 timeout は **peer-local テスト**で固定する

**port には足さない** — 共通契約に無関係な試験用途で port version を上げることになり、得るものが無い。

両 peer で、adapter が構築する `PostgresApplicationAuditSink` の書き手接続について、**既存の composition-root テストと同じ手法** (sink 自身の pool から接続を借り、`SHOW statement_timeout` / `SHOW idle_in_transaction_session_timeout` を実測する) で、`statement_timeout` と `idle_in_transaction_session_timeout` の**両方**が設定されていることを実測する。

参照する既存テスト: r2db `tests/test_application_audit.py:499` / `:563`、MitateDB `tests/test_application_audit.py:491` / `:667`。

### P4-D18 (L4-8) C-09 vector 4 の射程は「共通 port の構造保証」と明示して**据え置く**

peer 側に監査変更面が無いことは **DB 権限**で担保されている (書き手 INSERT のみ、reader SELECT のみ) — 両 peer に権限テストが実在する (設計 §9.2 性質 2)。vector 4 を peer 観測形へ作り直しても**新しい安全結果は得られない**。

`conformance-tests/CONDITIONS.md` の C-09 行と、vector 4 の docstring に**射程を明記する**。

### L4-7 (i)(ii) — MitateDB に対応テストを追加して対称化する

- **(i)** `control_main.build_control_app(env)` (実 entry point。`MitateDB-api/src/mitatedb_api/control_main.py:59`。低層の `control_composition.build_control_service` ではない) 経由で、`MITATEDB_AUDIT_DSN` 未設定 → `audit_query: {"status": "unavailable"}`、設定時 → `unavailable` 以外、を固定する。r2db の `test_build_control_app_declares_audit_query_status_from_r2db_audit_dsn_env` (`r2db-api/tests/test_audit_query.py:1398`) と同形。
- **(ii)** `MitateDB-api/src/mitatedb_api/main.py` の**ソーステキスト**に `control_credential` / `ControlCredentialStore` / `ControlPlaneService` / `PostgresControlCredentialStore` が現れないことを固定する。r2db の `test_data_plane_composition_root_does_not_import_the_control_credential_store` (`r2db-api/tests/test_audit_query.py:1373`) と**同名・同形**。ソーステキストを読むのは、`main.py` が module-level で `app = build_app()` を実行するため import できないからである (MitateDB も `main.py:400` に同じパターンがある)。

### L4-9 は既に解消済みである

WP-1 (`09233dd`) の `_event_identity` は cursor → `(plane, event_id)` を使用している。台帳 L4-9 の記述は **WP-1 受け入れ監査時点の指摘が残ったもの**であり、現物とは合っていない。§11.1 に **RESOLVED** と記す (WP-B4)。

### L4-10 (新規起票、**非対称**) — r2db `control_main` の `request_bytes` env 配線

**確認済みの事実 (監督)**:

- **MitateDB は配線済み** — `MitateDB-api/src/mitatedb_api/control_composition.py:85` (docstring の env 一覧) / `:128` (`request_bytes=_limit("MITATEDB_CONTROL_REQUEST_BYTES_LIMIT", defaults.request_bytes)`)。既定は `control_plane.py:138` の 65536、`__post_init__` で正の整数検査。固定テストも実在する (`MitateDB-api/tests/test_control_main.py:165` `test_build_control_app_request_bytes_limit_matches_the_declared_one`)。
- **r2db は未配線** — `r2db-api/src/r2db_api/control_main.py:315-322` は `applications` / `credentials_per_application` / `control_requests_per_minute` / `audit_requests_per_minute` の 4 つだけを env から読み、`request_bytes` は `ControlPlaneLimits` の dataclass 既定 (1_048_576) 固定である。

**裁定**: 記録のみに留めず、**WP-B3 で r2db 側の配線追加によって閉じる**。env 名は既存の `R2DB_CONTROL_LIMIT_*` 命名に揃えて **`R2DB_CONTROL_LIMIT_REQUEST_BYTES`** とする。**既定は現行の 1_048_576 を維持する** — 挙動不変であり、既定値の peer 差 (65536 / 1_048_576) は既存の開示済み差として据え置く。

---

## 2. 範囲外 (本書では扱わない。依頼者判断待ち)

以下は**列挙のみ**である。本書の WP は一切触れない。

1. **L4-1 `operation` / `target_kind` の語彙宣言化** — 契約 1.5.0 候補。
2. **L4-2 契約 1.4.0 無条件義務 (b) の適用範囲** — 契約文言の解釈問題。契約 1.5.0 候補。
3. **L4-4 `audit_requests_per_minute` の既定 60 と受理レンジの peer 非対称** — 挙動非対称の設計判断。
4. **L4-7 (iii) `audit_requests_per_minute` の受理レンジ非対称** (MitateDB `[1, 200]` / r2db 上限なし) — L4-4 と同一の設計判断。
5. **`visibility_lag_ms` の 2 プロセス整合の構造化** — 宣言側 (control プロセス) と書き手 (data-plane プロセス) が同名 env を独立に読む構造の機構的強制。設計 §11 の記録項目。

**L4-1 / L4-2 が契約変更を要する以上、本書の全 WP は契約ファイルに触れない。** 触れる必要が生じたら、それは設計の見直し要求として監督へ差し戻すこと (§7 禁止事項 2)。

---

## 3. WP 分割 (依存順)

| WP | 担当 | 内容 | 公開面 (契約) への影響 |
|---|---|---|---|
| **WP-B1** | Sonnet 実装 → Opus レビュー → Opus 証拠監査 | **L4-5** 宣言語彙走査の再構成 (両 peer。テスト + r2db `_event` / `_control_event` の keyword-only 化) | なし |
| **WP-B2** | 同上 | **L4-3** `failing` フラグの意味論変更 (両 peer、製品コード + テスト) | なし |
| **WP-B3** | 同上 | **L4-6** adapter 書き手 timeout (両 peer) + **L4-7(i)(ii)** (MitateDB) + **L4-10** r2db `request_bytes` env 配線 | なし |
| **WP-B4** | Opus 起草 → 監督 → Opus 証拠監査 | 記録: 設計 v1.6 (§5.1 / §11.1)、CONDITIONS.md、CONTROL_MAPPING.md、両 peer runbook | なし |

**依存順の根拠**: WP-B1〜WP-B3 は互いに独立である (触るファイルが重ならない — B1 = テストの走査部 + `service.py` の `_event` / `_control_event` の呼び出し規約、B2 = `service.py` の flush 成功分岐と `audit_dispatch.py`、B3 = adapter / composition root)。したがって**同一実装者が順に行う**。B4 は B1〜B3 の実測結果 (テスト名・集計行) を記録するため最後に置く。

**WP-B3 の外部依存 (本セッションの WP-A1)**: WP-B3 の L4-10 が触る `r2db-api/deploy/env/control.env.example` と `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7 の env 表には、**本セッションの WP-A1 で追加された行が作業ツリーにあり、まだコミットされていない**。本書が示す行番号は **WP-A1 適用後の値**である。WP-B3 の着手前に WP-A1 の差分が作業ツリーに存在することを確認し、無ければ監督へ差し戻すこと (行番号がずれる)。

各 WP は **Sonnet 実装 → Opus コードレビュー (変異注入必須) → Opus 証拠監査**の順で回す。

---

## 4. 各 WP の発注

### WP-B1 L4-5 宣言語彙 AST 走査の再構成 (両 peer)

#### 目的

`event_class` の「宣言 ⊇ 実 emit」を固定する走査が、**走査自身の見落とし** (手書きファイル列挙・非再帰 glob・callee 名キー・位置渡し・dict 密輸) によって偽の緑を返す状態を、両 peer で同時に閉じる (**P4-D16 v3**)。

#### 変更対象

**r2db-api**

- `r2db-api/tests/test_audit_query.py` — `_iter_src_files` (:841)、`_EVENT_CLASS_CALL_SPECS` (:864)、`_scan_event_class_literals` (:917)、`test_declared_event_classes_cover_every_emittable_class` (:993)。
  - `_iter_src_files` を `src/r2db_api/**/*.py` の**再帰列挙 (`rglob`)** へ。
  - **`_EVENT_CLASS_CALL_SPECS` (callee 名キー) を廃止**し、(b) の無差別 literal 規律へ置換する。
  - (c) 定義側 keyword-only 保証、(d) dict 密輸禁止、(e) `U == D ∪ N` を新設する。
- **製品コード (本 WP における唯一の製品コード変更。挙動不変)** — `r2db-api/src/r2db_api/service.py` の **`_control_event` (:1356、呼び出し 11 件) と `_event` (:1112、呼び出し 10 件)** を **keyword-only 化**する (`*` を入れ、計 21 件の呼び出しを `event_class=` のキーワード渡しへ揃える)。**走査側に例外を彫り込んで回避しない。**
  - **宣言 `DECLARED_AUDIT_EVENT_CLASSES` (`audit_query.py:53`) は変えない** — 非耐久語彙 (`authentication` / `control_failure` / `control_state`) は N へ入れるのであって、宣言へ足してはならない。足せば `audit_query` が決して返さない語彙を公開する嘘になる。

**MitateDB-api (テストのみ、製品コード無変更)**

- `MitateDB-api/tests/test_audit_query.py:625` `test_declared_event_classes_cover_every_emittable_class` — 上記と同じ形へ。`src_dir.glob("*.py")` を `rglob` へ。呼び出し側は現行どおり**無差別**のまま維持し、(c)(d)(e) を追加する。
- `MitateDB-api/tests/test_application_audit.py:872` の**同名テスト**と `_SOURCE_FILES_WITH_EMIT_SITES` (:838) — **削除して 1 本へ統合する** (残す側のファイルは実装裁量。手書きファイル列挙の定数は両ファイルから消えること)。
- **MitateDB は (c) の違反ゼロ・N = ∅** である。製品コードを変えてはならない。

#### 完了条件 (検証可能な形)

1. **手書きファイル列挙と callee 名キーがゼロ** — 両 peer のテストツリー全体で `_SOURCE_FILES_WITH_EMIT_SITES` / `_EVENT_CLASS_CALL_SPECS` に相当する固定列挙 (ファイル名タプル・callee 名キー付き spec) が grep で 1 件も出ないこと。走査対象は `rglob` によるパッケージ全体の再帰列挙のみであること。
2. **同名テストが 1 本に統合されている** — `grep -rn "def test_declared_event_classes_cover_every_emittable_class" MitateDB-api/tests` の結果が **1 行**であること (r2db 側も 1 行)。
3. **(b) literal 規律 (v1.3 の規則で固定)** — 両 peer 同名のテスト `test_every_event_class_keyword_argument_is_a_string_literal` が、パッケージ内の全 `Call` の `event_class=` 実引数が、文字列 `Constant`、または**囲む関数定義の仮引数束縛を検証した転送 (`Name`)**、または READ 側の `Attribute(attr="event_class")`/`Subscript["event_class"]` 転送、のいずれかであることを固定し、それ以外 (ローカル変数/global/for ターゲット/walrus 由来の同名 `Name`、`JoinedStr`、`BinOp`、`Call` の戻り値等) なら file:line を列挙して失敗すること。
4. **(c) 定義側 keyword-only 保証** — 両 peer 同名のテスト `test_every_definition_taking_event_class_declares_it_keyword_only` が、パッケージ内の全 `FunctionDef` / `AsyncFunctionDef` について、仮引数 `event_class` を持つものが `kwonlyargs` にあることを固定すること (`self` は判定から除く)。違反時は file:line と関数名を列挙すること。
5. **(d) dict 密輸禁止 + 代入走査 (v1.4 の反転規則・Assign 走査で固定)** — 両 peer 同名のテスト `test_no_event_class_string_literal_is_smuggled_through_a_dict` が、キー literal `"event_class"` の `Dict` literal / `x["event_class"] = ...` の `Subscript` 代入について、**値が (b) と同じ転送規則 (仮引数束縛済み `Name` / `Attribute` 読み出し / `Subscript` 読み出しのいずれか) を満たす場合のみ許容**し、それ以外 (文字列 `Constant` を含む) はすべて失敗とすることを固定すること (「値が文字列 `Constant` のときのみ失敗」という旧規則の反転)。加えて、両 peer 同名の `test_no_event_class_string_literal_is_smuggled_through_an_assignment` が、全スコープの `Assign`/`AnnAssign`/`AugAssign` (ターゲットが `Name(id="event_class")` または `Attribute(attr="event_class")`、タプル分解後も含む) について同じ転送規則を固定すること。**両 peer の現行サイトはすべて転送形であり、緑のまま通ること**。
6. **(e) 語彙関係の厳密一致** — 両 peer 同名のテスト `test_declared_event_classes_cover_every_emittable_class` が、`U == D ∪ N` **かつ** `D ∩ N == ∅` を固定すること。**N はテスト内に明示列挙され、各要素に「耐久表へ届かない根拠」のコメントが付いている**こと (r2db N = 3 語、MitateDB N = ∅)。
7. **宣言側が変わっていないこと** — 両 peer の `DECLARED_AUDIT_EVENT_CLASSES` の内容が**本 WP 前後で同一**であること (r2db 11 語 / MitateDB 12 語)。宣言へ非耐久語彙を足して (e) を通していないこと。
8. **keyword-only 化が挙動を変えていない** — r2db の `event_class` 語彙・emit された行の内容を固定する既存テスト (設計 §9.2 性質 5 / 性質 8 の対応テスト) が**値の変更なしで**緑のまま。位置引数渡しの残りが grep でゼロ。
9. **既存の同種走査が緑のまま** — `MitateDB-api/tests/test_control_plane_credential_store_reconciliation.py::test_credential_store_peek_has_no_caller_inside_src_mitatedb_api` (P4-D14) が緑のまま。
10. **変異注入 5 種がすべて赤** — 下記「変異注入」の 5 件が、両 peer で赤になることを実測すること。
11. **完了ゲート (本 WP 固有、v1.5 実績)** — 新規テスト名が**すべて suite の収集結果に現れる**こと、`failed` が **0** であること。実績: **新規 10 本** — 両 peer 同名の `test_every_event_class_keyword_argument_is_a_string_literal` / `test_every_definition_taking_event_class_declares_it_keyword_only` / `test_no_event_class_string_literal_is_smuggled_through_a_dict` の 3 関数 × 2 peer = 6 本、受け入れ監査ラウンド 1 (M3/M6) の `test_event_class_forward_exclusion_requires_genuine_parameter_binding` × 2 peer = 2 本、受け入れ監査ラウンド 2 (M7) の `test_no_event_class_string_literal_is_smuggled_through_an_assignment` × 2 peer = 2 本、計 10 本。**削除 2 本** (MitateDB の同名重複 1 + r2db `test_every_known_emission_method_name_is_still_called` 1) → **純増 8** (収集件数、実測 r2db 667→671 / MitateDB 455→459)。受け入れ監査ラウンド 3 (M8、`_collect_direct_shadow_names` の再設計と `with`/`except` の合成ソース 2 件追加) は既存 `test_event_class_forward_exclusion_requires_genuine_parameter_binding` 本体への assert 追加のみで、新規 test id は増やしていない。**本数は「テスト関数数」ではなく「収集された test id 数」で数える** — r2db の `test_declared_event_classes_cover_every_emittable_class` は `(kind, platform)` でパラメータ化されている (`r2db-api/tests/test_audit_query.py:993`)。**増減の内訳 (新規で増えた収集件数 / 削除で減った収集件数 / 差引の純増) を完了報告に必ず書く**こと。

#### テストコマンド

```
# 開発中の反復 (peer 単位)
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests

# 完了ゲート (リポジトリルートで単独実行。他の pytest が走っていないことを確認してから)
./.venv/bin/python -m pytest -q
```

実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない**。

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **callee 名フィルタの再混入** — 走査が、実装の都合で callee 名の集合 (allowlist / denylist / 接頭辞判定) を再導入していないか。**無差別方式を維持することが P4-D16 v3 の核心**であり、名前で絞った時点で「人が名前集合を維持し続ける」という L4-5 の元の欠陥へ戻る。**定義集合を作って callee 名と突き合わせる形 (v2) は撤回済み**であり、復活させてはならない。
2. **N が逃げ道になっていないか** — N の各要素に**耐久表へ届かない根拠**が書かれているか。根拠が「テストを緑にするため」に化していないか。N に**新しい語彙が足されていない**か (r2db は 3 語、MitateDB は ∅ のはず)。`D ∩ N == ∅` が実際に固定されているか (重なりを許すと、宣言済み語彙を N へ逃がして (e) を骨抜きにできる)。
3. **Attribute/Subscript passthrough は読み出し形に限られているか、かつ全スコープの `event_class` 代入が (d) の判定を受けているか** — `Attribute(attr="event_class")`/`Subscript["event_class"]` の転送許容は READ (値として読み出す) 形のみに限定され、書き込み側 (`Assign`/`AnnAssign`/`AugAssign`、モジュール/クラス/関数のいずれのスコープでも) が (d′) の代入走査を漏れなく受けているか (受け入れ監査 M7: `class _Cfg: event_class = "zz"` のような未検査の書き込みが残っていないか)。三項演算等の別形まで「転送」と見なして広げていないか (広げれば literal が走査から消える)。
4. **(c) の `self` 判定** — `self` / `cls` の扱いが、`posonlyargs` / `args` / `kwonlyargs` の区別を崩していないか。デコレータ付き・`@staticmethod` の定義で誤検出/見逃しが出ていないか。
5. **(d)/(d′) の値判定 (v1.3 の反転規則で固定)** — 文字列 `Constant`、`JoinedStr` (f-string)、`BinOp` (暗黙連結)、`Call` の戻り値、束縛を満たさない `Name` はすべて失敗とし、**仮引数束縛を検証した `Name` 転送、または READ 側の `Attribute(attr="event_class")`/`Subscript["event_class"]` 転送のみ**を許容しているか (§1 (d)/(d′))。旧規則 (「文字列 `Constant` のみ失敗」) への後退がないか。(d′) の代入走査 (全スコープの `Assign`/`AnnAssign`/`AugAssign`) が dict/subscript の判定と同じ転送規則を使っているか。
6. **keyword-only 化の網羅** — r2db の呼び出し 21 件がすべてキーワード渡しへ揃っているか。シグネチャ変更で既存テストが引数順に依存して壊れていないか。**製品コード変更がこの 2 面に限られること** — ほかに製品コードが変わっていれば射程外である。とくに**宣言 `DECLARED_AUDIT_EVENT_CLASSES` が変わっていないこと**を確認する。
7. **統合で失われた検査** — MitateDB の 2 本を 1 本にした際、application-plane 限定で見ていた性質 (6 フィールド sink の丸め再混入に対する回帰ガード、設計 §9.2 性質 5) が落ちていないか。落ちているなら残す側へ移すこと。
8. **走査範囲** — 走査対象が `src/<pkg>` に限定され、テスト・conformance adapter を巻き込んでいないか (巻き込めば adapter の literal が U に入り (e) が壊れる)。`contract/` サブパッケージの扱いが将来の実 emit サイトを隠す形になっていないか。
9. **変異ファイルの残骸** — 新規ファイル/新規定義を使う変異 (下記 3・4・5 件目) の後始末。**コミット前に変異文字列そのものを全文 grep すること** (フェーズ4 の教訓)。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

両 peer それぞれで実施し、**すべて赤になること**を実測する。

1. **未宣言 literal の注入** — `http.py` 相当の実 emit サイト (MitateDB は `src/mitatedb_api/http.py:419` の `event_class="authentication_denied"`、r2db は同種の emit サイト 1 箇所) の literal を宣言外・N 外の値へ書き換え、(e) が**赤**になること。
2. **非 literal 化** — 同じサイトの `event_class=` を変数経由へ書き換え、(b) が**赤**になること。
3. **新規ファイルへの emit** — `src/<pkg>/_mutant_probe.py` を新設して emit 呼び出し (宣言外の `event_class` literal つき) を置き、(e) が**赤**になること。**この変異ファイルは必ず除去する**。
4. **位置引数で受ける新規定義** — `def probe(event_class): ...` のように `event_class` を**位置引数**で受ける新規定義を追加し、(c) が**赤**になること。
5. **dict literal による密輸** — `{"event_class": "mutant"}` の dict literal を追加し、(d) が**赤**になること。

**復元後、変異文字列 (`_mutant_probe`、`mutant`、`def probe` 等) を全文 grep してゼロを確認する。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。証拠監査 = Opus (テンプレ 6)。

---

### WP-B2 L4-3 `failing` フラグの意味論変更 (両 peer、製品コード + テスト)

#### 目的

`failing` を「最後に**完了した** flush 試行の結果」にし、継続負荷下で sink 回復後もフラグが貼り付く状態を両 peer で同時に閉じる (P4-D15)。

#### 変更対象

**製品コード (両 peer 同型、各 1 箇所)**

- `r2db-api/src/r2db_api/service.py` — `_AuditBuffer.flush` (クラス :224-442、`flush` は :339) の**成功分岐**。`if not self._events: self._flush_currently_failing = False` を、**buffer の残量に関係なく** `self._flush_currently_failing = False` にする。
- `MitateDB-api/src/mitatedb_api/audit_dispatch.py` — `_AuditBuffer.flush` (クラス :131、`flush` は :194-320) の**同じ成功分岐**を同じ形へ。
- **同分岐の直上のコメントブロックを両 peer 同型に書き換える** — r2db `service.py:429-440` (12 行。WP-3(a) review m-1 を名指しで引き、「blindly forcing it to False and letting a genuinely-failing concurrent flush's backoff get reset to the floor by a race」= **まさに P4-D15 が容認する race** を避ける根拠を述べている)、MitateDB `audit_dispatch.py:296-303` 近傍の対応記述。**旧 WP-3(a) review m-1 の根拠をそのまま残さない** — P4-D15 の根拠 (完了順序の意味論 + `alert_min_interval_s` の床 + フラッピング時の代償) を述べる文へ差し替える。放置すればコードと真逆のコメントが残る。

**触ってはならない箇所** (P4-D15 の射程外):

- 失敗分岐 (復元 → 容量切り詰め → `_dropped_total` / `_alert_pending` 加算 → `_flush_currently_failing = True`) は**そのまま**。P4-D12 の swap-out・切り詰めは維持する。
- `_retry_alert` の**コードは変えない** (バックオフ算式、`alert_min_interval_s` による律速、5 種の固定メッセージ、状態遷移でのみ発火する規律)。**ただし N-2 分岐が観測する入力 (`flush_failing`) は変わる** — §1 P4-D15 の「変わるもの」を見よ。コードを変えずに挙動が変わることを、レビューで「変えてしまった」と誤認しないこと。
- 証拠側 (`count` への累積) は**変えない**。

**テスト**

- `r2db-api/tests/test_application_audit.py` / `MitateDB-api/tests/test_application_audit.py` — 下記 2 本を**両 peer 同名**で新設する。

#### 完了条件 (検証可能な形)

1. **回復の即時反映** — 両 peer 同名の新規テスト `test_a_successful_flush_clears_the_failing_flag_even_when_the_buffer_is_not_empty`: buffer が空にならない**継続 push 下**で sink を失敗させ、その後回復させたとき、**回復後最初の成功 flush** で `_flush_currently_failing` が解除され、alert のバックオフ間隔が**床 (`alert_min_interval_s`) に戻る**こと。**現行コードでは赤になること**を実測で示す (変異注入 1 に対応)。
2. **完了順序の意味論 (回帰ガード。現行コードでも緑)** — 両 peer 同名の新規テスト `test_a_failing_flush_that_completes_after_a_successful_one_sets_the_flag_again`: 成功 flush の**後に完了した**並行の失敗 flush が `_flush_currently_failing` を `True` に戻すこと。**このテストは P4-D15 の変更前後で同じく緑である** — 失敗分岐が無条件に `True` を立てるのは現行の挙動 (r2db `service.py:403` / MitateDB `audit_dispatch.py:273`) だからである。**load-bearing なのは完了条件 1 のみ**であり、本条件は「完了順序の意味論を将来壊さない」ための回帰ガードとして置く。
3. **alert 行の上限が破れないこと** — 既存 `test_alert_row_rate_is_bounded_to_at_most_one_per_flush_interval` (r2db `:2017` / MitateDB `:1183`) が**緑のまま**。P4-D15 が race 窓を許容する根拠はこの上限であり、ここが赤くなれば裁定の前提が崩れる。
4. **既存の 2 本が緑のまま** — `test_concurrent_push_during_a_failing_flush_never_grows_the_buffer_past_capacity` (r2db `:1814` / MitateDB `:1223`)、`test_alert_insert_failure_is_sticky_with_exponential_backoff_and_does_not_block_operations` (r2db `:2056` / MitateDB `:1399`)。
5. **証拠が変わっていないこと** — `test_buffer_overflow_alert_row_with_exactly_one_drop_writes_no_literal_count_of_one` (r2db `:1985` / MitateDB `:1382`) をはじめ、`count` の意味論 (P4-D8) を固定する既存テストが緑のまま。
6. **両 peer 同型であること** — 変更が両 peer で同じ形 (成功分岐の条件除去) であり、片方だけが別の手当て (フラグの追加、別変数の導入等) を採っていないこと。

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **新規テストが本当に load-bearing か** — 完了条件 1 のテストが、現行コード (`if not self._events`) で確かに赤くなるか。「buffer が空にならない」条件がテスト内で本当に成立しているか (flush の swap-out と並行 push のタイミングで、たまたま空になる経路が無いか)。
2. **完了順序のテストが順序を固定しているか** — 完了条件 2 が、単に「失敗すれば `True`」を見ているだけになっていないか。**成功が先に完了し、失敗が後に完了する**順序を実際に強制しているか。
3. **失敗分岐への波及** — 復元・切り詰め・`dropped` 計上のいずれかが、成功分岐の変更に引きずられて変わっていないか (bounded buffer の上限そのものが破れる形は follow-up 1 で 1 度起きている)。
4. **alert の発火頻度** — 回復が早く出るようになった結果、状態遷移でのみ発火する規律 (失敗↔健全の遷移のみ) が壊れて、flush ごとに回復メッセージが出る形になっていないか。完了条件 3 が守っているが、遷移判定のコード自体も読むこと。
5. **runbook との整合** — 製品コードの挙動変更が、両 peer runbook の「Known sharpness」段落と矛盾する状態でコミットされていないか (記録の更新は WP-B4 だが、**矛盾の存在は本 WP のレビューで検出して WP-B4 の対象に載せる**)。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

両 peer それぞれで実施する。

1. **成功分岐を現行へ戻す** — 成功分岐を `if not self._events: self._flush_currently_failing = False` へ戻し、完了条件 1 のテストが**赤**になること。
2. **完了順序の破壊** — 失敗分岐から `_flush_currently_failing = True` を落とし、完了条件 2 のテストが**赤**になること。
3. **律速の破壊** — `_retry_alert` の `alert_min_interval_s` による律速を外し、完了条件 3 の既存テストが**赤**になること (P4-D15 の前提が実際にテストで守られていることの確認)。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。証拠監査 = Opus (テンプレ 6)。

---

### WP-B3 L4-6 + L4-7(i)(ii) + L4-10

#### 目的

3 つの独立した穴を 1 コミットで閉じる — (a) conformance adapter の書き手 timeout が無テストであること (両 peer)、(b) peer 間のテスト名レベル非対称 2 件 (MitateDB 側の欠落)、(c) r2db `control_main` の `request_bytes` env 未配線。

#### 変更対象

**(a) L4-6 — adapter 書き手 timeout の実測テスト (両 peer、テストのみ、adapter 無変更)**

- `r2db-api/tests/` — 新規テスト。対象は `r2db-api/conformance/conformance_adapter_r2db_http.py:862-865` が構築する `PostgresApplicationAuditSink`。
- `MitateDB-api/tests/` — 同名の新規テスト。対象は `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:613-616`。
- **手法は既存 composition-root テストと同じ**: sink 自身の pool から接続を借り、`SHOW statement_timeout` / `SHOW idle_in_transaction_session_timeout` を読む (r2db `tests/test_application_audit.py:499`/`:563`、MitateDB `tests/test_application_audit.py:491`/`:667` と同型)。
- **port (`conformance-tests/adapter.py`) は変えない** — port version は v1.8 のまま (P4-D17)。in-process adapter (`conformance_adapter_r2db.py` / `conformance_adapter_mitatedb.py`) は in-memory sink であり DSN も pool も持たないため、**対象外**である。

**(b) L4-7(i)(ii) — MitateDB へのテスト追加 (テストのみ)**

- `MitateDB-api/tests/` — (i) `control_main.build_control_app(env)` (`src/mitatedb_api/control_main.py:59`) を実際に構築し、`MITATEDB_AUDIT_DSN` の有無で `audit_query` の宣言が切り替わることを固定する。
- `MitateDB-api/tests/` — (ii) `MitateDB-api/src/mitatedb_api/main.py` の**ソーステキスト**を読み (import しない。`main.py:400` に module-level `app = build_app()` がある)、4 つの識別子が現れないことを固定する。

**(c) L4-10 — r2db `request_bytes` の env 配線 (製品コード + テスト + 配備記録)**

- `r2db-api/src/r2db_api/control_main.py` — `:315-322` の `ControlPlaneLimits(...)` 構築に `request_bytes=_optional_int(env, "R2DB_CONTROL_LIMIT_REQUEST_BYTES", _DEFAULT_LIMITS.request_bytes)` を追加する。**既定は現行の 1_048_576 を維持**する (挙動不変)。`:45-57` の docstring の env 一覧にも同じ体裁で追記する。
- `r2db-api/tests/test_control_http.py` — MitateDB と**同名**のテストを追加する (r2db に `test_control_main.py` は無く、`build_control_app` を実際に構築するテストは同ファイルに集まっている。配置ファイルは実装裁量だが、テスト名は MitateDB と一致させること)。
- `r2db-api/deploy/env/control.env.example` — `R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE` (`:83`) と同じ体裁で `R2DB_CONTROL_LIMIT_REQUEST_BYTES=1048576` を追記する。**行番号は本セッションの WP-A1 適用後の値である** (§3 の外部依存を見よ)。
- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7 (`## 7. Control-plane deployment (CCR-14)`) の env 表 — `R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE` の行 (`:512` 近傍、**WP-A1 適用後の値**) と同じ体裁で 1 行追加する。

#### 完了条件 (検証可能な形)

1. **adapter 書き手 timeout (r2db)** — 新規テスト `test_http_conformance_adapter_audit_writer_connection_has_statement_and_idle_timeouts_set` が、`conformance_adapter_r2db_http.py` の構築した sink の接続で `statement_timeout` と `idle_in_transaction_session_timeout` の**両方**が既定値でないこと (adapter が渡した値であること) を `SHOW` で実測して固定すること。
2. **adapter 書き手 timeout (MitateDB)** — **同名**のテストが `conformance_adapter_mitatedb_http.py` について同じことを固定すること。
3. **port が変わっていないこと** — `conformance-tests/adapter.py` の port version が **v1.8 のまま**であり、`docs/design/CONFORMANCE_ADAPTER_V1.md` にも変更が無いこと。conformance suite が 4 adapter で全緑のまま (**404 passed**、C-09/C-11 は全 adapter で PROVIDED 分岐)。
4. **L4-7(i)** — MitateDB の新規テスト `test_build_control_app_declares_audit_query_status_from_mitatedb_audit_dsn_env` が、`build_control_app` 経由で「`MITATEDB_AUDIT_DSN` 未設定 → `audit_query.status == "unavailable"`」「設定時 → `"unavailable"` 以外」の両方を固定すること。低層の `build_control_service` ではなく **`control_main.build_control_app` を呼ぶ**こと。
5. **L4-7(ii)** — MitateDB の新規テスト `test_data_plane_composition_root_does_not_import_the_control_credential_store` (r2db と**同名**) が、`src/mitatedb_api/main.py` のソーステキストに `control_credential` (小文字化して検査) / `ControlCredentialStore` / `ControlPlaneService` / `PostgresControlCredentialStore` が現れないことを固定すること。**module を import しない**こと。
6. **同名テストの peer 対称** — `grep -rn "def test_data_plane_composition_root_does_not_import_the_control_credential_store" r2db-api/tests MitateDB-api/tests` が**両 peer で 1 行ずつ**、計 2 行になること。完了条件 1/2 のテスト名についても同じく 2 行。
7. **L4-10 配線** — r2db の新規テスト `test_build_control_app_request_bytes_limit_matches_the_declared_one` (MitateDB `tests/test_control_main.py:165` と**同名・同形**) が、`R2DB_CONTROL_LIMIT_REQUEST_BYTES` を設定したとき (i) `control_capabilities` の宣言 `limits.request_bytes` が変わること、(ii) 実際に ASGI 側が enforce する上限も変わること (超過要求が `LIMIT_EXCEEDED` / 413) の**両方**を固定すること。
8. **L4-10 の既定が不変** — env 未設定時に `request_bytes` が **1_048_576** のままであること。既存の r2db 側 limits 宣言テストが値の変更なしで緑のまま。
9. **配備記録** — `r2db-api/deploy/env/control.env.example` と `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` §7 に `R2DB_CONTROL_LIMIT_REQUEST_BYTES` が既存 `R2DB_CONTROL_LIMIT_*` と同じ体裁で載っていること。**実値の DSN / パスワード / 実在ドメインを書かないこと**。
10. **変異注入 4 種がすべて赤** — 下記「変異注入」のとおり。

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **観測対象の取り違え** — 完了条件 1/2 のテストが、adapter が構築した sink **そのもの**を見ているか。`main.build_app` 経由の composition-root sink を見ていれば、既存テストの重複であり L4-6 は閉じない (これが L4-6 の元の欠陥そのものである)。
2. **`SHOW` の読み値が既定と区別できるか** — adapter が渡す値が偶然サーバ既定と一致していると、kwargs を落とす変異が検出できない。テストが「既定でないこと」を実際に区別できているか。
3. **L4-7(ii) が import していないこと** — MitateDB の `main.py` は module-level で `app = build_app()` を実行する。テストが import 経路に落ちていれば、実 DB 接続や副作用で偽の赤/緑を生む。r2db 側が**なぜソーステキストを読むのか**という理由が docstring に残っているか。
4. **L4-7(i) の呼び出し先** — `build_control_service` (低層) ではなく `build_control_app` (実 entry point) を呼んでいるか。低層で緑にしても、entry point の配線漏れは検出できない。
5. **L4-10 の宣言と enforce の同一ソース性** — 完了条件 7 の (i) と (ii) が**両方**あるか。宣言だけを見るテストは「宣言値と enforce 値が同一ソースから出る」ことを固定しない (MitateDB 側テストの docstring が引く R-7 の要求そのもの)。
6. **既定値の peer 差を勝手に揃えていないか** — r2db 1_048_576 / MitateDB 65536 の差は**据え置く**と裁定済み。実装が「対称化」を理由に既定を動かしていれば、それは挙動変更であり本 WP の射程外である。
7. **秘密の混入** — 配備記録の追記に実値の DSN / パスワード / 実在ドメインが入っていないか (公開リポジトリ規律)。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

1. **adapter kwargs の除去 (両 peer)** — `conformance_adapter_r2db_http.py:862-865` / `conformance_adapter_mitatedb_http.py:613-616` の `statement_timeout_ms=` と `idle_in_transaction_session_timeout_ms=` を落とし、完了条件 1/2 のテストが**赤**になること。**片方ずつ落として、両方が独立に検出される**ことを確認する。
2. **L4-7(i) の破壊** — MitateDB の control composition から `MITATEDB_AUDIT_DSN` の読み取りを外し (`control_composition.py:169` 相当)、完了条件 4 のテストが**赤**になること。
3. **L4-7(ii) の破壊** — `src/mitatedb_api/main.py` に `ControlPlaneService` の import を 1 行足し、完了条件 5 のテストが**赤**になること。
4. **L4-10 の破壊** — r2db `control_main.py` から `request_bytes=` の env 配線を落とし、完了条件 7 のテストが**赤**になること。さらに宣言側だけを配線して enforce 側を配線しない形にし、完了条件 7 の (ii) が**赤**になること。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。証拠監査 = Opus (テンプレ 6)。

---

### WP-B4 記録整理 (設計 v1.6 / CONDITIONS / CONTROL_MAPPING / 両 peer runbook)

#### 目的

WP-B1〜WP-B3 で閉じた事実と、閉じないと裁定した事実の**両方**を、正本記録へ反映する。記録が実装より遅れている状態でフェーズを終えない。

#### 変更対象

**1. `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (v1.5 → v1.6)**

- **§5.1 の裁定表に P4-D15〜P4-D18 を追記する**。既存表と同じ 4 列 (記号 / 裁定 / 由来 / 本文の該当箇所) を維持し、由来列には本書 §1 の実測事実 (診断で判明した MitateDB の同名 2 本、r2db の非再帰 glob、adapter の該当行番号、DB 権限による担保) を書く。
- **§11.1 の各項目に状態を追記する**:

  | 項目 | 記す状態 |
  |---|---|
  | L4-1 | **範囲外** (契約 1.5.0 候補。依頼者判断待ち) |
  | L4-2 | **範囲外** (契約 1.5.0 候補。依頼者判断待ち) |
  | L4-3 | **CLOSED** (P4-D15、WP-B2)。解除条件を「最後に完了した flush 試行の結果」へ変更 |
  | L4-4 | **範囲外** (挙動非対称の設計判断。依頼者判断待ち) |
  | L4-5 | **CLOSED** (P4-D16 v3、WP-B1)。再帰列挙 + 無差別 literal 規律 + 定義側 keyword-only 保証 + dict 密輸禁止 + `U == D ∪ N` (`D ∩ N == ∅`)。非耐久語彙は宣言ではなく **N に名指しで列挙**した |
  | L4-6 | **CLOSED** (P4-D17、WP-B3)。peer-local テストで固定、port は据え置き |
  | L4-7 | **(i)(ii) CLOSED** (WP-B3)。**(iii) 範囲外** (L4-4 と同一の判断) |
  | L4-8 | **据え置き (射程明示、2026-09-03)** (P4-D18)。射程を「共通 port の構造保証」と明示した。**CLOSED とは書かない** — 新しい安全結果は生じておらず、peer 観測形への作り直しは将来の判断に残る |
  | L4-9 | **RESOLVED** — WP-1 (`09233dd`) の `_event_identity` が既に `(plane, event_id)` を使用しており、台帳の記述は WP-1 受け入れ監査時点の指摘が残ったものだった |
  | **L4-10** (新規) | **起票 → WP-B3 で CLOSED**。r2db `control_main` の `request_bytes` env 未配線は **peer 非対称**であった (MitateDB は `control_composition.py:85`/`:128` で配線済み、固定テストも実在)。r2db に `R2DB_CONTROL_LIMIT_REQUEST_BYTES` を追加して閉じた。**既定値の差 (r2db 1_048_576 / MitateDB 65536) は既存の開示済み差として据え置く** |

- **§11 の記録のみ項目**に、`visibility_lag_ms` の 2 プロセス整合の構造化が**本書の範囲外**である旨を 1 行追記する (依頼者判断待ち)。

**2. `conformance-tests/CONDITIONS.md`**

- **C-09 行** (`:17`) に、vector 4 の**射程**を明記する (P4-D18) — 「共通 port の ABC に監査変更面が無いことの構造保証であり、adapter ごとに分岐しない。peer 側の監査変更面の不在は DB 権限 (書き手 INSERT のみ / reader SELECT のみ) と両 peer の権限テストが担保する」。既存行の体裁 (実在テスト名を逐語で引く) を崩さないこと。
- `conformance-tests/test_c09_audit_evidence.py` の `test_c09_v4_no_audit_mutation_or_deletion_surface_exists` の **docstring に同じ射程を書く**。CONDITIONS.md と docstring の文言が食い違わないこと。

**3. `security/CONTROL_MAPPING.md`**

- **SI-14 行** (`:23`) の該当点を更新する — (i) L4-6 が閉じたこと (adapter の書き手 timeout が peer-local テストで実測固定されたこと)、(ii) L4-5 が閉じたこと (宣言語彙走査が無差別 literal 規律・定義側 keyword-only 保証・dict 密輸禁止により literal を完全列挙し、`U == D ∪ N` で網羅性を機械保証すること)。
- **主張する evidence は必ず実在するテスト名へ解決すること**。テスト名を書いたら、その名前で grep して 1 件以上出ることを確認する。

**4. 両 peer runbook の L4-3 記述**

- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15.2 末尾の **"Known sharpness, both peers"** 段落 (`:1164-1172`)。
- `MitateDB-api/docs/cloud-run-cloud-sql.md` の**同内容の段落** (`:483-484` 近傍)。
- **書き換えの方針**: 「buffer が完全に排出されるまでフラグが残る」という記述は**もはや真ではない**ので削除する。**「回復は当該ペアの回復メッセージで読む」という運用指示は据え置く** (buffer/overflow チャネルは 3 番目、coalescing チャネルは 5 番目の固定メッセージ) — 回復メッセージがより早く出るようになっただけであり、「メッセージが途切れた = 回復した」と読んではならないという規律自体は変わらない。5 種の固定メッセージ表、状態遷移でのみ発火する規律、容量算式 (§15.1 の `2 × 窓数 × M` / `buffer 容量 × M`) は**変えない**。

**4b. 設計本文と配備文書の整合 (P4-D15 による上書き)**

- `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` **D-4 本文** (`:215` 付近) と **§5.1 の P4-D12 行** (`:412` 付近) — いずれも「`failing` フラグの解除は buffer が完全に排出されたときのみ」を述べている。**P4-D15 による上書きを注記する** (P4-D12 を削除するのではなく、「この後半部は P4-D15 が上書きした」と読める形にする — 裁定の履歴を消さない)。
- `docs/work-orders/DEPLOY_PHASE4_20260903.md` **§5** — 別途「`failing` の内部機序の記述を落とす」修正が入る予定である。**本 WP では整合確認のみ**を行い、二重に書き換えない。

**5. 本書 §10 (実施記録)**

- 各 WP の完了日・コミット (merge)・root suite の集計行 (単独実行の実測値)・分割の有無を表で記録する。先行作業指示書 §9 と同じ体裁。

#### 完了条件 (検証可能な形)

1. **設計 v1.6 の §5.1 に P4-D15〜P4-D18 が存在**し (P4-D16 は **v3** の内容であること — 撤回した v2 の「三方向一致」を書かない)、既存表と同じ 4 列で書かれていること。§11.1 の **L4-1〜L4-10 の全 10 項目に状態が付いている**こと (状態の無い項目がゼロ)。
2. **L4-9 が RESOLVED として書かれ、その根拠 (WP-1 `09233dd` の `_event_identity`) が明記されている**こと。
3. **L4-8 が「CLOSED」ではなく「据え置き (射程明示、2026-09-03)」と表記されている**こと。**CLOSED と書かない** — 新しい安全結果は生じていない。
4. **L4-10 が新規項目として §11.1 に存在し、非対称であったこと・WP-B3 で CLOSED したこと・既定値の差を据え置いたことの 3 点が書かれている**こと。
5. **範囲外 5 件が §11.1 / §11 で「依頼者判断待ち」と明示されている**こと (L4-1 / L4-2 / L4-4 / L4-7(iii) / `visibility_lag_ms` の 2 プロセス整合)。
6. **CONDITIONS.md の C-09 行と vector 4 の docstring が同じ射程を述べている**こと。`./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py` のマーカー/行対応が**双方向で緑**。
7. **CONTROL_MAPPING.md SI-14 行が主張する evidence がすべて実在するテスト名へ解決する**こと (書いた各テスト名を grep して 1 件以上)。
8. **陳腐化した prose の全数掃討** — 以下 4 つの主張を述べている箇所を grep で洗い出し、**すべて実態へ更新する**こと (両 peer runbook・設計・CONTROL_MAPPING・配備文書・引き継ぎを含む)。
   - 「`failing` フラグは buffer が完全に排出されたときのみ解除される」
   - 「走査が見ていない emit サイトを検出する手段は無い」
   - 「adapter の書き手 timeout は無テスト」
   - 「r2db は `request_bytes` を env から配線していない」

   **grep 語は実表記に合わせること** — 文書によって言語も語彙も違う (英語 runbook は `the buffer fully drains`、日本語の設計・台帳は「buffer が空になったとき」「完全に排出」など)。担当は**まず grep で実表記を確認**してから掃討対象を確定すること。決め打ちの 1 語で走らせない。
9. **秘密の非混入** — 追記した全箇所に実値の DSN / パスワード / 実在ドメイン / 実データが無いこと。
10. **root suite の最終実測** (単独実行) の集計行を本書 §10 に記録すること。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 6 = 証拠監査)

1. **記録と実装の乖離** — CONTROL_MAPPING / CONDITIONS / 設計 §11.1 が主張する evidence が、実在し実際に走るテストへ解決するか。WP-B1〜B3 で採ったテスト名と、本書の完了条件に書いた予定名が食い違っていないか (食い違うなら記録側を実装に合わせる — 先行作業指示書 §5 の表が起こした食い違いを繰り返さない)。
2. **正直さの後退** — 「CLOSED」の主張が、実際には片方の peer でしか閉じていない状態を覆い隠していないか。範囲外項目が「対応不要」と読める書き方に化けていないか (**依頼者判断待ちである**)。
3. **runbook の実行可能性** — L4-3 の記述変更が、運用者の読み方 (「メッセージが途切れた = 回復した」と読んではならない) を弱めていないか。5 種の固定メッセージ表と容量算式が無傷か。
4. **射程明示のトートロジー化** — P4-D18 の「射程は port の構造保証」という記述が、vector 4 を実質的に無意味と認める形になっていないか。**DB 権限による担保 (書き手 INSERT のみ / reader SELECT のみ) と、それを固定する両 peer の実在テスト名**が併記されているか。
5. **台帳の取りこぼし** — WP-B1〜B3 のレビュー・証拠監査で「本書では扱わない」と裁定された項目が、すべて §11.1 へ落ちているか。

#### 使用テンプレート

起草 = Opus (テンプレ 4 = 文書起草)。証拠監査 = Opus (テンプレ 6)。

---

## 5. 期待される実測値

| WP | 期待される変化 |
|---|---|
| 基準値 | **1526 passed / 0 failed / 0 skipped / 0 xfailed** (2026-09-03、フェーズ4 完了時点) |
| WP-B1 | 実績: 新規 **10 本** ((b)(c)(d) の 3 本 × 2 peer = 6 本 + 束縛検証の回帰テスト (M3/M6) × 2 peer = 2 本 + 代入密輸テスト (M7) × 2 peer = 2 本。(e) は既存の同名テストを統合したもので新規ではない) + MitateDB の同名重複 **1 本削除** + r2db `test_every_known_emission_method_name_is_still_called` **1 本削除** → **純増 8** (収集件数実測。受け入れ監査ラウンド 3 = M8 は既存 test id 数を変えない) (WP-B1 完了条件 11) |
| WP-B2 | 新規 4 本 (両 peer × 2 本) → **件数は増える** |

| WP-B3 | 新規 5 本以上 (adapter timeout × 2、L4-7(i)(ii) × 2、L4-10 × 1) → **件数は増える** |
| WP-B4 | 文書のみ (件数不変) |

**本数は「テスト関数数」ではなく「収集された test id 数」で数える** — 両 peer にパラメータ化されたテストがある (r2db `test_audit_query.py:993` は `(kind, platform)`)。上表の本数はテスト関数の見積りであり、集計行との突き合わせは収集件数で行うこと。

**完了ゲートの判定**: 各 WP で root suite を単独実行し、`failed` / `skipped` / `xfailed` がすべて **0** であり、`passed` (収集件数) が**直前 WP の値から増えている**こと。WP-B1 は重複削除で相殺されうるため、判定は完了条件 11 (純増 ≥ 1 + 増減内訳の報告) による。

`conformance` は **404 passed** (4 adapter) が基準値であり、本書の全 WP で**不変**である (port を変えないため)。

---

## 6. 完了ゲートの実測規律 (全 WP 共通。先行作業指示書 §4 を継承)

- 完了ゲートの root suite は**リポジトリルートで単独実行する**。他の pytest プロセスが走っていないことを確認してから実行する — **PG クラスタの並走衝突で偽の赤が出る** (フェーズ3.5 で 2 回発生)。
- 実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない** — skip が出ていたら環境の問題として解決してから完了と判定する。
- 各 WP の完了報告に **集計行 (passed / failed / skipped / xfailed)** を必ず記録し、増分の内訳 (どのテストが何本増えたか) を書く。
- **変異注入は scratchpad へ復元する** (`git checkout` は使わない)。**コミット前に変異文字列そのものを全文 grep する** (フェーズ4 の教訓: 差分の一致確認は「消えていないこと」しか保証しない)。

---

## 7. 禁止事項 (全 WP 共通)

1. **git commit / push は監督のみが行う**。Sonnet も Opus もコミットしない。
2. **契約 (`spec/`) を変えない**。`spec/data-service-api.v1.json` は `contract_version` 1.4.0 のまま、`spec/CCR_DISPOSITION.md` に新しい従属判断を起こさない。`r2db-api/src/r2db_api/contract/data-service-api.v1.json` (packaged copy) も変えない。契約変更が必要に見えたら、それは**設計の見直し要求として監督へ差し戻す** — 契約 1.5.0 候補は本書 §2 のとおり範囲外である。
3. **共通 port を変えない** — `conformance-tests/adapter.py` は **v1.8 のまま**。`docs/design/CONFORMANCE_ADAPTER_V1.md` も変えない (P4-D17)。
4. **範囲外項目に触れない** (§2) — L4-1 / L4-2 / L4-4 / L4-7(iii) / `visibility_lag_ms` の 2 プロセス整合。「ついでに」直さない。
5. **migration の in-place 編集を禁じる**。本書は migration を一切要求しない。必要に見えたら差し戻す。
6. **秘密・実データ・実在ドメインを書かない**。環境変数名・secret-manager 参照・架空ドメイン・合成 fixture のみ。公開リポジトリである。
7. **テストの並行実行を禁じる**。完了ゲートは単独実行する。
8. **制約・制限の追加で問題を回避しない** (依頼者設計原則 3)。新しい上限・拒否経路・機能制限を、難所を回避するために足さない。
9. **既存テストを緩めない** — とくに `control_audit` の 13 フィールド完全一致テスト、`test_alert_row_rate_is_bounded_to_at_most_one_per_flush_interval`、`test_concurrent_push_during_a_failing_flush_never_grows_the_buffer_past_capacity`、`test_credential_store_peek_has_no_caller_inside_src_mitatedb_api`、両 peer の権限テスト。**緑にする正しい手段は実装を真にすることだけである。**
9b. **宣言 `event_classes` に非耐久語彙を足さない** — WP-B1 の (e) を通すために `DECLARED_AUDIT_EVENT_CLASSES` へ `authentication` / `control_failure` / `control_state` を足すことを禁じる。`audit_query` が決して返さない語彙を公開する嘘になる。正しい手段は **N への名指しの列挙と根拠コメント**である。
10. **peer 間の既定値を勝手に揃えない** — `request_bytes` の既定 (r2db 1_048_576 / MitateDB 65536) と `audit_requests_per_minute` の受理レンジは、いずれも**据え置くと裁定済み**である。
11. **変異ファイルを残さない** — WP-B1 の `_mutant_probe.py` / `def probe(event_class)` / `{"event_class": "mutant"}` を含め、変異は必ず除去し、コミット前に変異文字列を全文 grep する。

---

## 8. コミット規律

- **WP ごとに 1 コミット** (WP-B1 / WP-B2 / WP-B3 / WP-B4 で計 4 コミット)。それ以外の分割は監督の許可を要する。
- **identity は `r2fish` / noreply**。実名・Gmail を使わない。**コミット前に必ず `git log --format='%an <%ae>'` で確認する**。
- **commit → push → main merge (`--no-ff`) は 1 セット**。コミットしたら直ちに push し、main へマージする。分離しない。
- コミットメッセージは日本語可。WP 番号・変更の要旨・完了ゲートの集計行を含める。
- 各コミットの前に、独立レビュー (Opus、変異注入込み) と証拠監査の往復が完了していること。

---

## 9. 使用テンプレートの対応

| WP | 実装 | レビュー | 監査 |
|---|---|---|---|
| WP-B1 | Sonnet テンプレ 2 (実装) | Opus テンプレ 5 (コードレビュー、変異注入必須) | Opus テンプレ 6 (証拠監査) |
| WP-B2 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-B3 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-B4 | Opus テンプレ 4 (文書起草) | — | Opus テンプレ 6 |

テンプレートの本文は `~/.claude/.../memory/role-prompt-templates.md` が正本。各発注時に、当該 WP の「レビューが必ず探すべき点」と「変異注入」の節をテンプレートへ差し込むこと。

---

## 10. 実施記録

(WP-B4 で記入する。体裁は先行作業指示書 §9 に従う — WP / 完了日 / コミット (merge) / 集計行 (root suite、単独実行) / 分割の有無。)
