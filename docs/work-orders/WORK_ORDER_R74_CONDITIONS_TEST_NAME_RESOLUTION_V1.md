# 作業指示書 — R-74 `conformance-tests/CONDITIONS.md` が引くテスト名を現物に解決する機械検査

## 0. 版数・位置づけ

- **v1.0 (2026-09-22)。** 基点 ローカル main `4b738f4` (worktree `.claude/worktrees/r74`)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-74。変更クラスは **Class C** (`tools/change_class.py conformance-tests/CONDITIONS.md conformance-tests/test_conditions_register.py` → `class=C` / `conformance_required=true`、2026-09-22 実測)。`spec/` と `security/` は触らない。
- 設計文書は起こさず、決定は本書 §1 に置く (R-64 の先例。`docs/work-orders/WORK_ORDER_R64_CONTROL_MAPPING_TEST_NAME_RESOLUTION_V1.md` §0)。設計レビュー 1 回を本書 §1〜§2 に対して行う (実施済み。§1 末尾)。
- WP は 1 本である。R-64 の §3 (WP-2、現物の訂正) に当たるものは D-6 の条件付きで WP-1 の中に入る。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 問題と決定 (監督確定)

**問題**: `conformance-tests/CONDITIONS.md` が証拠として引くテスト名・テストファイル名を、実在しない名前に書き換えても `conformance-tests/test_conditions_register.py` は緑のままである。同ファイルが検査するのは `@pytest.mark.condition(...)` と行の対応の 2 方向 (`:203`・`:217`) だけで、Evidence / Status の散文が引く名前の実在は見ない。R-64 は同型の検査を `security/CONTROL_MAPPING.md` にだけ入れ、CONDITIONS.md を明示的に範囲外として台帳に起票した (R-64 の作業指示書 §4・§6.2)。

**実測** (2026-09-22、基点 `4b738f4`、`ast` の索引。監督の探索と起草時の再測定が一致。件数は延べ):

- CONDITIONS.md は 165 行。`|` で始まる表は **`:27`-`:56` の 30 行だけ**で、`:1`-`:26` の前書きと `:57`-`:165` の散文は表の外に在る。表の外にもテストファイル名の参照が `:16`・`:22`・`:61` の 3 箇所在る (いずれも `test_conditions_register.py`)。**探索の材料 (`r74-facts.md` §2) が「`:27`-`:165` が表」と述べたのは誤りで、起草時の再測定で訂正した。** D-2 の「非空の全行を走査」はこの事実に掛かる。
- R-64 の 3 形 (完全形 `path::name` / 裸 `::name` / 裸 `` `name` ``) に一致する参照は 31 件 (6 / 1 / 24)。うち `cell.py::_where` (`:41`) は**テストではなく実装コードへの参照**で、R-64 の完全形正規表現が name に `test_` を求めないための偽陽性である (D-3 (e))。
- R-64 の 3 形に一致せず `test_` を含む backtick 参照は延べ 47・相異なり 42。内訳は裸のファイル名 44 (相異なり 39、うち path 無しは 13 種)、`path::Class::method` の 3 階層形 2 (`:31`・`:36`)、hook 名 `pytest_collection_modifyitems` 1 (`:55`)。
- D-3 の規則で拾うと **完全形 5 / 3 階層 2 / 裸 `::` 1 / 裸名 24 / 裸ファイル名 44 (計 76)** で、**現物に解決できない参照は 0 件**である。4 形に一致せず `test_` を含む span は `:55` の 1 件だけである (D-3 (f) の allowlist)。
- 3 階層形の 2 件が引く method (`test_developer_schema_and_runtime_crud`・`test_transaction_rolls_back`) は class の中にしか無く、平らな名前集合の索引では (b) を判定できない。
- 引かれている名前のうち `async def` だけで実在するものは 0 件である (4 directory の索引の中に `async def` だけの def は 93 件在る)。よって async を索引に含めることは合成 fixture で固定する (完了条件 5)。
- **`conformance-tests/CONDITIONS_HISTORY.md` の実測** (D-2 が対象外とする根拠の確認): 同じ規則で拾うと参照は延べ 146 件。索引の中で解決しないものは 0 件で、**今日は「現物に無い旧テスト名」に当たるものは無い**。4 directory の外を指す参照が 3 件 (`:303`・`:307`・`:314` の `tests/test_http.py`) 在り、これは D-5 の `not indexed` に当たる。いずれにせよ履歴は逐語の旧文の保管場所で、消えたテスト名を含むのが正しいので対象に入れない。

**決定**:

- **D-1 (置き場所と索引)。** 検査は `conformance-tests/test_conditions_register.py` に足す (CONDITIONS.md の検査はこのファイルに集める。R-64 が CONTROL_MAPPING の検査を `test_control_mapping_register.py` に置いたのと同じ対応)。**R-64 のファイルからは何も import しない** — 兄弟 module の import は pytest の既定 (prepend) と現物の先例 (`conformance-tests/test_c06_present_denial_stub_regression.py`:22) では通るが、R-64 側の私的関数の形 (床・peer 範囲・平らな名前集合) に本件が縛られ、あちらの改修で本件が壊れる。
  - 索引は `test_conditions_register.py` の中に自前で持つ。形は `{dir_key: {repository 相対 path: {class 名 または None: {def 名}}}}`。`ast` の `FunctionDef`/`AsyncFunctionDef` を集め、module 直下の def は `None` の側へ、**module 直下の class の直下の method は `Class::method` として引けるように** class 名の側へ入れる (入れ子の関数は入れない)。4 directory (`r2db-api/tests`・`MitateDB-api/tests`・`conformance-tests`・`tools/tests`) の定数も自前で持つ。R-64 との小さな重複は許す (責務が違う)。pytest の収集は使わない (PostgreSQL と DSN が要る。`OPERATING_CONDITIONS.md` §2 の 12)。
- **D-2 (対象と走査)。** 対象は `conformance-tests/CONDITIONS.md` の全文。対象ファイルは**定数 1 本**で固定し、glob にしない (R-64 D-3 と同じ)。定数が CONDITIONS.md を指すこと自体を assert する (定数の等価)。`conformance-tests/CONDITIONS_HISTORY.md` は対象に入れない。走査は表の行だけでなく**非空の全行**を見る (R-64 §6.1 の教訓。現物では `:16`・`:22`・`:61` が表の外に在る)。
- **D-3 (参照の形と解決)。** backtick の span 単位で抽出し、次の形だけを見る。抽出は **name または path の basename が `test_` で始まる**形に限る (完全形・3 階層形の name も `test_` 始まりを要求する)。
  - (a) **完全形** `<path>::<test_name>`: path が 4 directory のいずれかの中の相対パスとして実在し、そのファイルに def `<test_name>` (module 直下または class の method) が在ること。directory を省いた形 (現物 2 件、`:29`) は 4 directory の中で basename が**一意**に決まり、そこに def が在ること。
  - (b) **3 階層形** `<path>::<Class>::<test_method>`: そのファイルの **module 直下の** class `<Class>` の直下に def `<test_method>` が在ること。directory 省略は (a) と同じ basename 一意規則。
  - (c) **裸の形** `::<test_name>` と `` `<test_name>` ``: 索引のどこかに同名の def が在ること。**どのファイルかは見ない** (R-64 D-1 (ii) と同じ限界。CONDITIONS.md の行は peer で区切られていないので peer の範囲も見ない)。
  - (d) **裸のファイル名** `` `test_<x>.py` `` (`::` なし): directory を伴う形はそのパスが実在すること、path を省いた形 (現物 13 種。うち 1 件は表の外の `:61`) は 4 directory のいずれかに basename が実在すること (一意性は見ない。13 種はいずれも今日は一意である)。
  - (e) **実装コードの参照は対象外**: name も path の basename も `test_` で始まらない span (現物では `cell.py::_where`、`:41`) は抽出しない。
  - (f) **上の 4 形に一致せず `test_` を含む span の集合**は、既知の allowlist と一致すること (今日は `:55` の `pytest_collection_modifyitems` 1 件)。新しい引き方が文書に入れば赤になり、規則を更新するか allowlist に足すかの判断を促す。
- **D-4 (床と空振り禁止)。** 形ごとの観測件数を pin ではなく**下限**で assert する。床は **5 本**に分ける (完全形 / 3 階層 / 裸 `::` / 裸名 / 裸ファイル名)。値と余裕の取り方は実装担当が実測して決め、由来 (実測値・日付・基点) をコメントに書く (R-64 D-4 の形。2026-09-22 の実測は 5 / 2 / 1 / 24 / 44)。索引は 4 directory それぞれで 1 件以上であることも assert する (`OPERATING_CONDITIONS.md` §1.5 の 32)。
- **D-5 (失敗の形)。** 解決しない参照は 1 件 1 行で全件出す: `CONDITIONS.md:<行>: <参照> (<理由>)`。理由は `file not found` / `def not found` / `class not found` / `ambiguous basename` / `not indexed (outside the 4 test directories)` のいずれか。最後の 1 つは 4 directory の外を指す path を別立てにするためである (「現物に無い」と「索引の外」は別の話である)。
- **D-6 (現物の不整合)。** 実測で解決しない参照が出たら、**本 WP で** CONDITIONS.md の当該参照を現物に直す (同じ変更セット。Class C のまま)。ただし引き先のテスト名が改名されていて**主張の内容が変わる**場合は直さず監督へ上げる。2026-09-22 の実測は 0 件なので、通常は CONDITIONS.md を触らずに終わる。監督の再実測が正本で、増減が在れば直さず報告する。

**却下した代替案**:

- R-64 のテストファイル (`test_control_mapping_register.py`) に CONDITIONS.md を 2 本目の対象として足す — CONTROL_MAPPING の検査と CONDITIONS の検査の責務が混ざる。R-64 D-3 は対象を 1 本に固定しており、その固定を崩す。
- R-64 の索引・解決の関数を import して使う — 上の D-1 の理由 (あちらの私的関数の形に縛られる)。
- 正規表現 `def test_` で索引を作る — `async def` を落とす (R-64 §1 の撤回の記録。r2db-api だけが不可視になった)。
- 参照の形を R-64 の 3 形に限る — 3 形に一致しない `test_` 参照が 42 種 (延べ 47) 残り、CONDITIONS.md の主体である裸のファイル名が無検査のままになる。

**未確定で依頼者判断待ち**: 無し。

**設計レビュー 1 の反映 (2026-09-22)**: 起草版に対する設計レビュー 1 回を実施し、監督裁定で全件を本文に反映した (未コミットの起草版への反映なので訂正註ではなく本文を直した)。反映した箇所: H-1・H-2 → §2.1 の単独実行時の既知の赤と `conformance-tests/` 全体の 1 回の実行、§2.4 の `tests` の node id、§2.5 の node id 列挙。H-3・L-1 → **D-1 を「import しない・自前の索引」に書き替えた** (起草版は `from test_control_mapping_register import …` を採っていた)。M-1 → D-3 (d) の path 無しは 13 種。M-2 → D-2 の定数の等価と完了条件 9・M9、§1 の HISTORY の実測。M-3 → D-3 (f) の allowlist。M-4 → M4b・M11。M-5 → D-4 の床 5 本。M-6 → D-3 (a) の「name が `test_` で始まらなくてもよい」拡張を**落とした** (起草版は fixture / helper を完全形で引ける形にしていた)。L-2 → D-3 (b) の module 直下の class と basename 一意。L-3 → D-5 の `not indexed`。L-4 → M8 の 2 つの node id。完了条件は番号を振り直した。

## 2. WP-1 — 検査を足す

### 2.1 タスク

- `conformance-tests/test_conditions_register.py` に D-1〜D-5 の検査を足す。抽出と解決は「文書のテキスト → 未解決一覧」の純関数にし、**現物と合成 fixture の断片の両方**に同じ関数を掛けられる形にする (R-64 も合成 fixture を使った)。テストは少なくとも: (1) 現物で (a)〜(d) が全件解決する、(2) 空振りでない (D-4)、(3) allowlist が一致する (D-3 (f))、(4) fixture で「実在しないファイル」「実在しない def」「実在しない class」「4 directory の外の path」「(e) の実装コード参照は拾わない」「`async def` だけで実在する名前が解決する」「表の外の行の参照を拾う」がそれぞれ固定される。
- 失敗メッセージは D-5 の形で全件出す (最初の 1 件で止めない)。
- **register ファイル単独の実行では `_collect_marked_condition_ids` (`:187`) の assert により marker を使う 3 本が仕様どおり赤になる** (marker は同 directory の他のファイルに在る)。この guard を緩めない・skip しない。新しい検査は marker に依らないので単独で緑になる。
- 検証は §2.5 の順で行う: 新しい検査の node id を列挙した `pt.py` を回しながら実装し、**報告の前に 1 回だけ `conformance-tests/` 全体**を回して緑を確かめる (約 9 分。前景 1 回で収まる。`timeout` パラメータ 600000)。
- 経緯トークンをテスト本体に足さない。ファイル冒頭か関数の docstring に `R-74:` と本書のパスを書くのは可。コメントと docstring は `tools/check_comment_provenance.py` の規則に掛かるが、`conformance-tests/` は同道具の走査対象外で、求めるのは `--register` の緑だけである (R-64 §6.1)。
- `tools/check_doc_refs.py`・`tools/public_value_scan.py`・comment provenance `--register` の出力行をそのまま報告に貼る (`OPERATING_CONDITIONS.md` §1.10 の 65)。

### 2.2 触ってよいパス

- `conformance-tests/test_conditions_register.py`。
- `conformance-tests/CONDITIONS.md` — **D-6 が発動したときだけ**。発動しなければ 1 字も触らない。
- `conformance-tests/COLLECTION_FLOOR` は触らない (監督が完了ゲートで更新する)。

### 2.3 完了条件

1. 完全形 (D-3 (a)) が現物で解決する。
2. 3 階層形 (D-3 (b)) が現物で解決する (class を保つ索引、D-1)。
3. 裸の形 (D-3 (c)、`::` と裸名の両方) が現物で解決する。
4. 裸のファイル名 (D-3 (d)) が、directory を伴う形と path 無しの形の両方で現物で解決する。
5. 索引が `async def` を含む (D-1)。
6. 実装コードの参照 (D-3 (e)) は抽出されない。
7. 4 形に一致せず `test_` を含む span の集合が allowlist と一致する (D-3 (f))。
8. 非空の全行を走査する (D-2) — fixture に加えて、現物でも表の外の参照が 1 件以上在ることを assert する (2026-09-22 実測 3 件: `:16`・`:22`・`:61`)。
9. 対象の定数が `conformance-tests/CONDITIONS.md` に固定されている (D-2)。
10. 5 本の床が在り、空振りしない (D-4)。
11. 失敗メッセージが D-5 の形で、解決しない参照を全件出す。
12. 索引が 4 directory それぞれで 1 件以上 (D-4)。
13. 現物に解決しない参照が 0 件である、または D-6 に従って直してある。
14. §2.4 の表に対応の無い行が無い。

### 2.4 完了条件 → 変異

変異は `tools/dev/mutate.py` で 1 回にまとめて実行してよい。**各エントリの `tests` には、赤 (または緑) を判定する node id を書く**。1 つのエントリが赤にするテストは 1 本にする (`mutate.py` は最初の失敗で止まるため。R-58 の教訓)。

| 完了条件 | 変異 | `tests` の node id | 期待 |
|---|---|---|---|
| 1 | M1: CONDITIONS.md の完全形 1 件 (`:33` の `r2db-api/tests/test_foundation.py::test_malformed_inputs_fail_with_safe_foundation_errors`) の name を架空の名前にする | 現物の完全形を固定するテスト | 赤 (`def not found`) |
| 2 | M2a: 3 階層形 1 件 (`:31`) の method を架空の名前にする | 現物の 3 階層形を固定するテスト | 赤 (`def not found`) |
| 2 | M2b: 自前の索引から class の中の def を外す (module 直下の def だけにする) | 同上 | 赤 (`class not found`) |
| 3 | M3a: 裸 `::` 形 1 件 (`:29` の `::test_cross_application_denial_does_not_disclose_existence`) を架空の名前にする | 現物の裸の形を固定するテスト | 赤 |
| 3 | M3b: 裸名 1 件 (`:44` の `test_c15_no_default_credential`) を架空の名前にする | 同上 | 赤 |
| 4 | M4a: directory を伴う裸ファイル名 1 件 (`:42` の `conformance-tests/test_c13_revocation_terminality.py`) を架空の basename にする | 現物の裸ファイル名を固定するテスト | 赤 (`file not found`) |
| 4 | M4b: path 無しの裸ファイル名 1 件 (`:44` の `test_control_ceremony.py`) を架空の basename にする | 同上 | 赤 (`file not found`) |
| 5 | M5: 自前の索引から `ast.AsyncFunctionDef` を外す | fixture の async を固定するテスト | 赤 — fixture の断片が引く `r2db-api/tests/test_preauth_concurrency_bound.py::test_unauthenticated_flood_is_bounded_by_concurrency` (`:81` の `async def`) が解決しなくなる |
| 6 | M6: `:41` の `cell.py::_where` を `cell.py::_nope` に変える | 現物の解決を固定するテスト | **緑のまま** (expect green) |
| 7 | M7: allowlist から `pytest_collection_modifyitems` を外す | allowlist のテスト | 赤 |
| 8 | M8: 走査を `|` で始まる行だけに戻す | fixture 側と現物側の**両方**の node id | 赤 |
| 9 | M9: 対象の定数を `conformance-tests/CONDITIONS_HISTORY.md` に変える | 定数の等価のテスト | 赤 |
| 10 | M10a〜M10e: 5 本の床をそれぞれ観測数 + 1 にする (1 形につき 1 エントリ) | 各形の床のテスト | 各 赤 |
| 11 | M11: 解決する参照 2 件を同時に架空の名前にする | 失敗メッセージのテスト | 赤 — メッセージに D-5 の形の行が **2 行**出る |
| 12 | 監査照合 | — | 索引の 4 directory の件数 (実行したコマンドと出力行) を報告に逐語で残す |
| 13 | 監査照合 | — | 実装前後の未解決一覧 (D-5 の出力そのもの) を報告に逐語で残す |
| 14 | 監査照合 | — | 本表と §2.3 の突合 |

### 2.5 道具の引数

- 実装中: `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r74 -- 'conformance-tests/test_conditions_register.py::<新テスト名 1>' 'conformance-tests/test_conditions_register.py::<新テスト名 2>' … -q` (**新しい検査の node id を列挙する**。ファイル全体を指すと §2.1 の既知の赤 3 本が混ざる)。
- 報告の前に 1 回だけ: `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r74 -- conformance-tests -q` (約 9 分、前景 1 回、`timeout` パラメータ 600000)。
- `tools/dev/mutate.py "$SP/r74-mutations.json" -C .claude/worktrees/r74 --wait 1800`
- `tools/dev/gate.py -C .claude/worktrees/r74 --label r74` (**監督のみ**。root の集計は 3844 + 追加した node id の数)。
- 着手手順として `tools/change_class.py <触った全パス>` を実行し、`class=C` を報告に貼る (`RM` §9)。

## 3. 範囲外

- CONDITIONS.md の Evidence / Status の主張の**内容** (引かれたテストが本当にその条件を固定するか) の監査。本件が見るのは名前が現物に解決することだけである。
- `conformance-tests/CONDITIONS_HISTORY.md` (D-2)。
- `conformance-tests/test_control_mapping_register.py` の改修 (class を保つ索引の共通化を含む。D-1)。

## 4. レビューと受け入れ

設計レビュー 1 回 (本書 §1〜§2 に対して、WP-1 の着手前。**実施済み 2026-09-22**。§1 末尾に反映を記録した)。コードレビュー 1 回 (WP-1 の後)。受け入れ監査 1 回。監督が完了ゲートの集計行・完了条件・監査のパケットを照合して判定する。

## 5. 記録 (統合時に監督が埋める)

### 5.1 訂正註

- **【訂正註 1 (2026-09-23)】完了条件 15 と変異の追加。** コードレビュー 1・2 の反映で、完了条件 15「`CONDITIONS.md` の backtick の外に `test_[a-z0-9_]+` が現れない」(左の語境界つき。テスト名は snake_case の前提) を足し (M13 fixture / M14 文書側)、完了条件 12 の変異 M12 は「索引処理本体を空にする」形 (class 側だけ外す形は module 直下の def が残り赤にならない — 実測)、M8 は fixture 側 M8a / 現物側 M8b に分割した。床のコメントは日付・基点を書かず測り方 (`_find_references` を `CONDITIONS.md` に掛けて形ごとに数える) を書く形 (R-73 と同じ)。失敗行の先頭は `CONDITIONS.md:<行>` (fixture は `fixture:<行>`)。

### 5.2 実施と受け入れ

- **差分**: `conformance-tests/test_conditions_register.py` への追記のみ (新テスト 15 本: 5 形の解決・床 5 本・対象定数 pin・全行走査・allowlist・索引の非空・naked token、fixture テストを含む)。`CONDITIONS.md` は不変 (D-6 不発動: 現物の未解決 0)。`tools/change_class.py` → `class=C`。
- **実測 (2026-09-22/23、main adea2b5 → 7452b5b の上)**: 5 形の観測 完全形 5 / 3 階層 2 / `::` 1 / 裸名 24 / 裸ファイル名 44 (床 4/1/1/20/40)、allowlist 1 (`pytest_collection_modifyitems`)、表外参照 3 (`:16`/`:22`/`:61`)、path 無し裸ファイル名 13 種 (曖昧 0)、索引 r2db 32 / MitateDB 49 / conformance 48 / tools 15 ファイル (def 1441/1680/821/688)、backtick 外の `test_` token 0。
- **道具の出力行**: `pt: 15 passed` (node id 列挙)、`pt: 1064 passed` (`conformance-tests` 全体、差し戻し 1 後)。`mutate: 22 mutations, 22 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged` (M1〜M14、M6 は expect green)。`check_doc_refs` 0、`public_value_scan` 0。
- **設計レビュー 1** (高 3・中 6・低 4、全件反映: R-64 からの import 廃止と自前索引、pt は node id 列挙 + 全体 1 回、5 本の床、対象定数 pin、allowlist、(a) 拡張の削除)。**コードレビュー 2 巡** (1 巡目 中 2・低 5 → 差し戻し 1; 2 巡目 低 3 → 差し戻し 2; 全件閉)。**受け入れ監査**: 完了条件 1〜14 全て充足、未充足 0 (留保 2 件 = M8 の分割・失敗行の絶対パス → 差し戻しで解消)。
- **完了ゲート** (監督単独、最終の木、`--label r74c`): `3859 passed, 2 subtests passed in 370.61s (0:06:10)`、`judge=PASS`、実行クラスタ差分 0 (直前の main 3844 + 15。差し戻し 2 前の木でも `3859 passed`、PASS)。`COLLECTION_FLOOR` は下限のため未更新 (更新はフェーズ完了時)。
- **最終判定**: 受け入れ。台帳 R-74 を閉じる (v1.94)。

(空欄)
