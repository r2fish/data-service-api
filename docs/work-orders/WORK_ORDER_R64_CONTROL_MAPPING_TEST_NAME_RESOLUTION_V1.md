# 作業指示書 — R-64 `security/CONTROL_MAPPING.md` が引くテスト名を現物に解決する機械検査

## 0. 版数・位置づけ

- **v1.0 (2026-09-21)。** 基点 main `3711a34`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-64。変更クラスは **Class D** (`conformance-tests/` = C と `security/` = D に跨るので重い方)。契約 (`spec/`) は触らない。D が求める依頼者裁定は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) の下で監督が下し、事後確認を引き継ぎ書で伺う。版付きの security-contract 決定は `security/CONTROL_MAPPING.md` の版 **2.18**。
- 設計文書は起こさず、決定は本書 §1 に置く (R-62 の先例)。設計レビュー 1 回を本書に対して行う。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 問題と決定 (監督確定)

**問題**: `security/CONTROL_MAPPING.md` の主張が証拠として引くテスト名を、実在しない名前に書き換えても `conformance-tests/test_control_mapping_register.py` は緑のままである (R-56 の変異 M11、R-57 の変異で実測)。実測 (2026-09-21、基点 `3711a34`、`ast` の索引。監督と設計レビュー 1 の独立の 2 回が一致) では、引き方は 3 形 — 完全形 `path/test_x.py::test_name` 112 件、裸の `::test_name` 320 件、裸の `` `test_name` `` 109 件 — で、**現物に解決できないのは 1 件**: `security/CONTROL_MAPPING.md`:477 (SI-06 / r2db-api / 既定 / Control) の `test_audit_role_http_authorization_matrix_all_11_endpoints` (現物は `r2db-api/tests/test_control_http.py`:972 の `…_all_13_endpoints`。audit_query の 2 path が足されて 11 → 13 に改名された。同じテストを引く `:261` は `_13_` で正しい)。peer の取り違えは 0 件である。

**【撤回の記録】** 本書の起草時の版は「19 件、うち 10 件余りは peer の取り違え」と述べていた。これは調査の索引が正規表現 `def (test_\w+)` で作られ、**`async def` を落としていた**ための誤りで (async の test は `r2db-api/tests` に 95 本、他の 3 directory に 0 本 — r2db-api だけが不可視になった)、設計レビュー 1 の F-1 が見つけた。台帳 R-64 行の「6 件」(R-57 の受け入れ監査の機械照合) も同じ型の誤測定の疑いが強く、現行では 1 件である。D-2 が `ast` と `async def` を名指すのはこのためである。

**決定**:

- **D-1 (解決の規則)。** テスト名の参照は次の 2 規則で解決する。指示語 (「直前の path」) の追跡はしない — 裸の `::name` の 31% は同じ bullet に先行の path を持たず、「直近の完全形」の探索は SI-14 で別ファイルを拾う (調査の実測) ので、追跡は検査を脆くする。
  - (i) **完全形** `<path>.py::<name>`: `<path>` が repository 相対で実在し、そのファイルに `def <name>` (関数またはクラスのメソッド) が在ること。directory を省いた形 (`test_x.py::name`。調査で 4 件) は、**その主張の subsection の peer の test directory** (下の (ii) の集合) の中で basename が一意に決まり、そこに def が在ること。
    - 完全形は subsection を問わず解決する。peer の差を述べる主張や両 peer の adapter を並記する Evidence が相手 peer のテストを完全形で引くのは正当である (現物に 2 件)。
  - (ii) **裸の形** (`::<name>` と `` `<name>` ``。`<name>` は `test_` で始まる識別子の全体): **その主張の subsection の peer に許された test directory** のどこかに `def <name>` が在ること。許された集合は、`r2db-api` の subsection → `r2db-api/tests`・`conformance-tests`、`MitateDB-api` の subsection → `MitateDB-api/tests`・`conformance-tests`、`Common` の subsection と SI 節の外 → `r2db-api/tests`・`MitateDB-api/tests`・`conformance-tests`・`tools/tests` の 4 つ全部 (`tools/tests` を裸で引く peer の主張は現物に 0 件なので peer の集合に入れない。引くなら完全形で書く)。**相手 peer のテストを引きたい主張は完全形で書く** (完全形は subsection を問わず (i) で解決する)。これは「相手 peer にしか無い名前を裸で引く」取り違えを赤にする。**(ii) が固定するのは、名前が peer の範囲に実在することだけである**: 同名の def が両 peer に在る参照 (現物で 124 件) では取り違えを検出せず、ファイルの一致も見ない。docstring と文書の主張はこの範囲に留める。
- **D-2 (索引の作り方)。** def の索引は `ast` で作る (`def test_…` と `async def test_…`、モジュール直下とクラス直下)。pytest の収集は使わない (PostgreSQL と DSN が要る。`OPERATING_CONDITIONS.md` §2 の 12)。
- **D-3 (対象の範囲)。** 対象は `security/CONTROL_MAPPING.md` の全文 (preamble・`## Rule` を含む。現状そこに参照は無いが、足されたら見る)。対象のファイルは定数 1 本で固定し、`security/*.md` の glob にしない。`security/CONTROL_MAPPING_HISTORY.md` は**対象外** — 逐語の旧文の保管場所で、消えたテスト名を含むのが正しい。`conformance-tests/CONDITIONS.md` への同型の検査は本件に入れず、台帳に起票する (§4)。
- **D-4 (空振りの禁止)。** 検査は、**現物の文書に対して**、抽出した参照の件数が形ごとの下限 (完全形 90 / 裸の `::` 280 / 裸の名前 90。2026-09-21 の実測 112 / 320 / 109 から余裕を引いた定数で、由来をコメントに書く) 以上であること、索引が 4 つの directory それぞれで 1 件以上であることを assert する (`OPERATING_CONDITIONS.md` §1.5 の 32)。
- **D-5 (解決できない参照の直し方)。** 各件を現物で読み、次のどれかに裁定する (裁定は監督。WP-2):
  - (a) 改名されただけで、同じ性質を固定するテストが主張の peer に在る → 名前を直す。
  - (b) 主張の peer には無く相手 peer にだけ在り、主張の peer に同じ性質を固定する別名のテストが在る → その名前に直す。
  - (c) 主張の peer に、その性質を固定するテストが**無い** → まず統制そのものの実在を現物 (src / migration / runbook) で確かめ、統制が無ければ Control の主張も同じ変更セットで訂正する。統制は在るが機械の証拠が無い場合だけ、名前を外し、**証拠の欠落を Status に現在形で開示し、台帳に起票する**。検査を緑にするために相手 peer のテスト**だけ**を挙げて済ませない。
  - **本件の 1 件 (`:477`) は (a) である** (監督裁定)。
  - いずれも文の訂正なので Update convention に従う (現行行を in place で直し、旧行を逐語で `security/CONTROL_MAPPING_HISTORY.md` の該当 SI の節へ移す)。
- **D-6 (変更セット)。** 検査と訂正は**同じコミット**に入れる (検査だけを入れると main が赤になる)。

**却下した代替案**: 「直前の path」を追跡して裸の `::name` をファイルまで解決する案 — 31% が bullet を跨ぎ、SI-14 で誤爆する。追跡を通すために文書側へ path の再掲を大量に足すと SI-14 / r2db-api (残り 2,576 字) と SI-09 / MitateDB-api / `platform upgrade` (残り 2,519 字) が上限に当たる。peer の範囲で引く (ii) は、実害の在った取り違えを捕らえつつ文書を膨らませない。

## 2. WP-1 — 検査を足す

### 2.1 タスク

- `conformance-tests/test_control_mapping_register.py` に D-1〜D-4 の検査を足す。既存の parser (`_analyze_shape` 系の (SI, peer, 小ブロック, 軸) の分解) を使い、主張ごとの subsection を取る。テストは少なくとも: (1) 完全形が解決する、(2) 裸の形が peer の範囲で解決する、(3) 空振りでない (D-4)、(4) 合成 fixture で「実在しない名前」「相手 peer にしか無い裸の名前」「directory 省略形が一意でない」がそれぞれ検出される。失敗メッセージは `file:line`・引かれた名前・(SI, peer, 小ブロック, 軸)・規則 (i)/(ii) を 1 件 1 行で全件出す。
- 検査を現行の `security/CONTROL_MAPPING.md` に掛け、赤になる参照が §1 の 1 件と一致することを確かめる。一致したら続けて WP-2 を行う (1 件で確定文も §3 に在るので、監督の再開指示を待たない)。
- コメントと docstring は `tools/check_comment_provenance.py` の規則に掛かる。`tools/dev/pt.py … -- tools/tests -q -k comment_provenance` ではなく、道具そのもの (`./.venv/bin/python tools/check_comment_provenance.py` を worktree の中で。引数は道具の help に従う) を走らせて緑を確かめる。

### 2.2 触ってよいパス

- `conformance-tests/test_control_mapping_register.py`。`COLLECTION_FLOOR` は触らない (監督が完了ゲートで更新する)。
- `conformance-tests/README.md` / `conformance-tests/CONDITIONS.md` に register テストの検査の一覧が在れば、その 1 箇所 (報告に列挙)。

### 2.3 完了条件

1. D-1 (i)・(ii)、D-2、D-3、D-4 の各性質にテストが在り、§2.4 の変異で赤になる。
2. 現行の文書に対して新しい検査が赤にする参照は、**§1 の 1 件 (`:477`) と完全に一致する** (監督の再実測が正本。増減が在れば直さず報告する)。
3. 新しい検査以外の register テストは緑。`tools/tests -k control_mapping` は緑。
4. `tools/check_comment_provenance.py`・`tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。
5. §2.4 の表に対応の無い行が無い。

### 2.4 完了条件 → 変異

検査 (1)(2) は WP-2 の訂正まで現行文書で赤なので、**M1〜M4・M7・M8 は合成 fixture のテスト (および現物の個別の名前を解決する単体のテスト) に対して行い**、現行文書に対する M5・M6 は WP-2 の後に実行する。変異はすべて WP-2 の後にまとめて `tools/dev/mutate.py` で 1 回実行してよい。

| 性質 | 変異 | 期待 |
|---|---|---|
| D-1 (i) | M1: 完全形の解決で def の実在を見ずに path の実在だけで通す | fixture (実在しない名前) のテストが赤 |
| D-1 (ii) peer の範囲 | M2: 裸の形の解決を 4 directory 全部に広げる | fixture (相手 peer にしか無い裸の名前) のテストが赤 |
| D-1 (i) directory 省略 | M3: basename の一意性を見ず最初の一致を採る | fixture (一意でない) のテストが赤 |
| D-4 | M4: 参照の抽出の正規表現を何にも一致しない形にする | 空振りのテストが赤 |
| D-2 | M7: 索引から `ast.AsyncFunctionDef` を外す | async def だけで実在する名前の fixture (または現物の `r2db-api/tests/test_preauth_concurrency_bound.py::test_unauthenticated_flood_is_bounded_by_concurrency`) のテストが赤 — 本件の調査の事故そのものを固定する |
| D-3 | M8: 対象ファイルの定数を `security/CONTROL_MAPPING_HISTORY.md` も含む形に広げる | 範囲のテストが赤 |
| (WP-2 の後) D-1 現行文書 | M5: `security/CONTROL_MAPPING.md` の Evidence の 1 つのテスト名を実在しない名前にする / M6: r2db-api の subsection の裸の名前 1 つを MitateDB-api にしか無い名前にする | 現行文書の検査が赤 |
| 完了条件 2〜5 | 監査照合 | — |

### 2.5 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/<担当 worktree> -- conformance-tests/test_control_mapping_register.py -q`
- `tools/dev/pt.py -C .claude/worktrees/<担当 worktree> -- tools/tests -q -k control_mapping` (別呼び出し)
- `tools/dev/mutate.py "$SP/r64-mutations.json" -C .claude/worktrees/<担当 worktree>`

## 3. WP-2 — 解決できない 1 件を直す (確定文)

- `security/CONTROL_MAPPING.md`:477 の `test_audit_role_http_authorization_matrix_all_11_endpoints` を `test_audit_role_http_authorization_matrix_all_13_endpoints` に in place で直す (D-5 (a)。行の他の部分は 1 字も変えない。スクリプトで置換する)。旧行は逐語で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-06` の節の末尾へ、先例 (`## SI-09` の末尾の R-60 / R-70 の題) の形の題を付けて移す。題の確定文: `*r2db-api Control claim, the audit role's fail-closed write refusals, superseded 2026-09-21 (Version 2.18, R-64 -- the cited test was renamed from `..._all_11_endpoints` to `..._all_13_endpoints` when `audit_query`'s two paths joined the route table, and the claim kept the old name, which resolves to no test), verbatim:*`
- 版数行 2.18 と preamble の `Blocks per subsection` の再実測文は、実装担当が先例 (2.15・2.17 の形) に沿って案を作り、実測値を入れる。版数行には「Evidence / Control が引くテスト名の解決を `conformance-tests/test_control_mapping_register.py` が検査するようになったこと、その範囲 (D-1 の (i)(ii)、(ii) の限界)」を 1〜2 文で述べる。文案は監督が統合前に確定する。最長ブロックが変わらなければ `Length cap measurement` の段は触らない。
- 完了条件: (1) 新しい検査を含む register テストが全部緑、(2) `tools/check_control_mapping_split.py --base 3711a34 --expect "missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` が終了コード 0、(3) 旧行が基点と byte 一致で履歴に在る、(4) ブロック長の実測が preamble と一致し上限内、(5) M5・M6 が赤。
- 触ってよいパス (WP-2): `security/CONTROL_MAPPING.md`、`security/CONTROL_MAPPING_HISTORY.md`。

## 4. 範囲外 (起票のみ)

- `conformance-tests/CONDITIONS.md` が引くテスト名の同型の検査。
- (c) と裁定した件の、欠けているテストそのものの追加。

## 5. レビューと受け入れ

設計レビュー 1 回 (本書 §1 に対して、WP-1 の着手前。**実施済み 2026-09-21**: F-1 (重大、問題設定の誤り) 〜 F-10 を全件採用して本書に反映した。未コミットの起草版への反映なので訂正註ではなく本文を直し、撤回は §1 に記録した)。コードレビュー 1 回 (WP-1 + WP-2 の後)。受け入れ監査 1 回。監督が完了ゲートの集計行・完了条件・監査のパケットを照合して判定する。

## 6. 記録 (統合時に監督が埋める)

### 6.1 訂正註 2026-09-21 (コードレビュー 1 と受け入れ監査への監督裁定。§1〜§3 の本文は書き換えない)

- **D-1 (i) を狭める。** 完全形が解決するのは、4 つの test directory (`r2db-api/tests`・`MitateDB-api/tests`・`conformance-tests`・`tools/tests`) の**再帰**の中の path だけである。その外の path を引く完全形は赤のままでよい (証拠として引けるのは test directory の中のテストだけ)。
- **D-3 の実装形。** SI 節の中は `- ` の bullet 行 (peer は囲む subsection)、SI 節の外は非空の全行 (peer の集合は 4 つ全部) を走査する。起草時の実装は全文を bullet 行だけで見ており、版数行に入った解決しない旧名が検査の外に在った (コードレビュー 1 の F-1)。§2.4 の表に **M9** (SI 節の外の走査を bullet 行だけに戻す → fixture のテストが赤) を足す。SI 節の中の非 bullet 行は既存の形の検査が禁じている。
- **版数行の書き方。** 版数行で消えたテスト名を述べるときは、識別子の全体を backtick に入れず省略形 (`..._all_11_endpoints`) で書く。全体は履歴に在る。
- **§2.1 の comment provenance。** `conformance-tests/` は `tools/check_comment_provenance.py` の走査対象外で、`--base` はコードを足す変更では構造上赤になる。求めるのは `--register` の緑だけである。
- **D-4 の索引の非空。** 「索引が 4 directory それぞれ 1 件以上」を壊す変異は置いていない (監査照合: 索引は r2db-api 1032 / MitateDB-api 1249 / conformance-tests 358 / tools 533)。
- M2・M5〜M8 は差し戻し 1 の前のコードでの実測である。差し戻し 1 で動いたコード (索引の再帰、SI 節の外の走査) に掛かる M1・M3・M4・M9 は再実行して赤。監査は `glob` と `rglob` の索引が現在の木で一致することを確かめた。

### 6.2 実施と受け入れ

- 実施 2026-09-21。`conformance-tests/test_control_mapping_register.py` にテスト名の解決検査 (テスト関数 +9、収集 34 → 43)。現行文書で赤になったのは §1 の 1 件 (`:477`) だけで、監督・設計レビュー・実装・監査の `ast` の再実測が一致した。`:477` を D-5 (a) で直し、旧行は基点と byte 一致で履歴の `## SI-06` に在る。`security/CONTROL_MAPPING.md` 版 2.18。
- 道具: register `43 passed`、`tools/tests -k control_mapping` `58 passed, 510 deselected`、`tools/check_control_mapping_split.py --base 3711a34 --expect "missing=1 added=1 moved=0 …"` 終了コード 0、`check_doc_refs` 0 dangling、`public_value_scan` 0 flagged、comment provenance `--register` 緑。変異 M1〜M9 は全部 `expect=red got=red`、復元は sha256 2 回で照合。
- ブロック長: SI-06 / r2db-api / 既定 2,367 (不変、残り 12,833)。文書の最長は SI-09 / MitateDB-api / `platform upgrade` 12,681 (不変)。
- 設計レビュー 1 回 (F-1 重大: 問題設定の誤り。§1 の撤回の記録)。コードレビュー 1 回 (中 2・低 2、全件を裁定して差し戻し 1)。受け入れ監査 1 回: 未充足 0・証拠不足 0。監査の指摘 (a) (docstring が版数行について現在形で偽を述べる) は統合前に監督が 1 文を直し、register テストを再実行して緑を確かめた (ゲートの後の変更は docstring のこの 1 箇所だけである)。
- 完了ゲート (監督が単独実行): `gate: 3805 passed, 2 subtests passed in 326.14s (0:05:26)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0`。増分 +9 は register テストの増分と一致。`conformance-tests/COLLECTION_FLOOR` は 3326 のまま触っていない。**受け入れる。**
- 起票: `conformance-tests/CONDITIONS.md` のテスト名の同型の検査 (台帳 R-74)。
