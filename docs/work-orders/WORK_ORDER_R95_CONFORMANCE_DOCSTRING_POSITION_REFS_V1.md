# 作業指示書 — R-95 `conformance-tests/` の `.py` の docstring・コメントが引く `file:line` 位置参照を現物に解決する機械検査

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点 local main `dd12657`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-95。変更クラスは **Class C** (`conformance-tests/` のみ。契約 `spec/` は触らない、両 peer の `src/` も触らない)。
- 設計文書は起こさず、決定は本書 §1 (と WP の §2・§3) に置く (R-88・R-64・R-62 の先例)。設計レビュー 1 回を本書 §1〜§2 に対して行う。
- 本件は位置参照の機械検査の第 3 系列である。R-74 = `conformance-tests/CONDITIONS.md`、R-88 = `security/CONTROL_MAPPING.md` (`docs/work-orders/WORK_ORDER_R88_CONTROL_MAPPING_POSITION_REFS_V1.md`)、本件 = `conformance-tests/` の `.py` 自身の docstring・コメント。
- `tools/check_comment_provenance.py` の範囲は両 peer の `src/` だけである (`docs/design/CODE_COMMENT_PROVENANCE_V1.md`:93)。したがって本書 WP-2 の conformance の docstring・コメントの訂正に来歴検査は掛からない。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit・完了ゲート・`finalize.py` は監督のみ。道具は `tools/dev/`)。実装担当の裁量は**実装詳細のみ**で、本書の決定 (D-1〜D-9) と訂正の範囲は変えない。

## 1. 問題と決定 (監督確定)

**問題**: `conformance-tests/` の `.py` の docstring・コメントが引く `file:line` の**位置参照**は、path が実在するかも、行番号がそのファイルの範囲に収まるかも検査されない。R-88 が `security/CONTROL_MAPPING.md` に入れた検査と同型の穴が、conformance のテスト自身の散文に残っている。確定した腐り 3 件 (基点 `dd12657`、実測):

- (1) `conformance-tests/test_c20_constraint_declaration_agreement.py`:154 と (2) `conformance-tests/test_c22_dry_run_and_plan.py`:186 の docstring が `r2db-api/src/r2db_api/structured.py:1583` を `self.schema_revision += 1` の行として引く。現物のその行は無関係の分岐で、`self.schema_revision += 1` は `:1821` である (grep で 1 箇所のみ)。行数の範囲内なので R-88 型の範囲検査では素通りする。
- 同じ 2 箇所が続けて引く `MitateDB-api/src/mitatedb_api/backend_sqlite.py:207`/`:250` (`self._schema_revision += 1`) も腐りである。現物は `:198`・`:294`・`:434` の 3 箇所である (grep 実測)。どの関数に属するかは実装担当が現物で確かめる。文が「schema 操作ごとに 1 ずつ増える」と述べる以上、現行の**全箇所**を引く。
- (3) `conformance-tests/test_c14_authority_boundary.py`:746 のコメントが引く `r2db-api/src/r2db_api/control_plane.py:1574` は、現物 1,527 行の末尾を超える。訂正先は実装担当が現物で特定し、周辺 ±10 行を報告する。

この 2 箇所 (1)(2) の `MitateDB-api/src/mitatedb_api/backend_sqlite.py:207` は 1 つの backtick span が 2 物理行にまたがって書かれており (`test_c20_constraint_declaration_agreement.py`:155-156)、R-88 の行単位の抽出では参照として拾えない。行またぎの扱いが本件の検査の設計上の要である (D-2)。

**行番号の読み方**: 本節と §3.1 が挙げる行番号は、断りのない限り**物理行**である。検査の出力 (D-8) は**単位の開始行**なので、同じ参照でも数値が異なることがある。

**D-2 の連結後に機械で赤になる残件 (設計レビュー 1 の実測、基点 `dd12657`)**: 本書の抽出形で数えると **11 件**である — `ambiguous` 2 件 (`service.py:914`・`service.py:877`)、EOF 超 1 件 (`control_plane.py:1574`)、`no preceding path` 8 件 (`conformance-tests/test_conditions_register.py`:617 と :765 の `:16`/`:22`/`:61` の計 6 件、`conformance-tests/test_contract.py`:456 の `:29`/`:57-59` の計 2 件)。この 8 件の訂正も本書で確定する (§3.1 の 7・8)。上の腐り (1)(2) の `structured.py:1583` 系は行数の範囲内なので機械では赤にならず、WP-2 の**全数照合**で直す (D-6)。

**守る条件**: 変更クラス **C**。触るのは `conformance-tests/` だけで、契約 (`spec/`) にも両 peer の `src/` にも触らない。検査 (WP-1) を先に単独で入れると現行の木が赤になるので、検査と訂正 (WP-2) は**同じ変更セット・同じ worktree・同じ実装担当**とする。

**決定**:

- **D-1 (置き場所)。** 検査は新規ファイル `conformance-tests/test_conformance_docstring_position_refs.py` に置く。**静的読みだけで単独実行できる形**とする (`request.session.items` や marker guard に依存しない。`conformance-tests/test_conditions_register.py`:167-198 の `_collect_marked_condition_ids` の型に**しない** — あれは実収集セッションに依存し、単独実行では意味を失う)。`conformance-tests/test_control_mapping_register.py` からは **import しない** — 姉妹テストの間で pin や関数を import しない (引き継ぎ書 `docs/work-orders/HANDOVER_20260923_FABLE.md` §5 の教訓)。抽出・解決の関数は本ファイルが自前で持つ。
- **D-2 (対象と単位)。** 対象は `conformance-tests/` 配下の全 `.py` (再帰、`sorted(Path.rglob("*.py"))`、基点で 48 本。走査本数の床を持つ、D-7)。文字列の単位は 2 種である。
  - (α) 全 docstring。`ast` で Module / ClassDef / FunctionDef / AsyncFunctionDef の本体先頭の文字列定数を取る。
  - (β) コメント塊。`tokenize` で、**行頭から始まる (同じ開始 column の)、行番号が連続する `#` 行の最大の並び**を 1 単位とする。行末コメント (コードと同じ行に在る `#`) は 1 行 1 単位とする。
  - **単位の中で行を連結してから抽出する。** **単位の先頭から当該の改行までの backtick の累積個数**が奇数なら (backtick の span が開いている)、次行の先頭空白を落として**空文字で**連結する。偶数なら 1 個の空白で連結する。根拠: 現物は `` `MitateDB-api/src/mitatedb_api/ `` + 改行 + `` backtick_sqlite.py:207` `` のように path を行またぎで書いており (`conformance-tests/test_c20_constraint_declaration_agreement.py`:155-156)、行単位の抽出 (R-88 の `` [^`\n] ``) では拾えず、かつ未閉の backtick が同一行の後続の正しい参照を bare `:NNN` に誤分類する (調査ノート item 3 の 1・2)。
  - 失敗の報告に使う行番号は**単位の開始行**とする。
  - `rglob` は git に未追跡の `.py` も見る。これは fail-closed 側の性質 (手元にだけ在るファイルへの参照は CI で赤になる) なので据え置く (R-88 の監督裁定 2 と同じ)。
- **D-3 (拾う形)。** 次を位置参照として拾う。
  - (a) `` `path:N` ``、(b) `` `path:N-M` `` (colon と行番号が backtick の**中**)。
  - (a') `` `path`:N `` / `` `path`:N-M `` (colon と行番号が backtick の**外**)。検査は (a)/(b) と同じである。**現物は 0 件である** (設計レビュー 1 の実測)。床は置かず、合成 fixture の判定列に (a') を含めて固定する (D-7)。
  - (c) 直前の path を継ぐ `` `:N` `` / `` `:N-M` `` と bare `:N` / `:N-M` (**backtick の内外を問わない**)。
  - **(c) の抽出条件**: `:` の直前の 1 字が英数字でないこと**だけ**である (`1:1` のような比率・`12:30` を除く。調査ノート item 3 の 3)。**「前に path が在ること」は抽出条件にしない** (監督裁定 2026-09-23)。
  - **(c) の解決**: 同じ単位の中でそれより前に在る backtick の path (形 (a)(a')(b)(d) の path 部分) のうち、**最も近い前の path** を継ぐ。前に path が無い bare `:N` は `no preceding path` の**失敗**として出す (path を書き足す訂正で運用する。R-88 の D-9 (3) と同じ)。調査ノートが既存抽出形で数えた `no preceding path` 群は、D-2 の連結規則・単位内の carry-forward・上の英数字条件で大半が解消する見込みである。残件は実装担当が全件報告し、監督が 1 件ごとに裁定する (D-5・§3.2)。
  - `path` は R-88 と同じ拡張子ホワイトリストを持つものだけを path とみなす: `.py`・`.sql`・`.md`・`.sh`・`.yml`・`.yaml`・`.toml`・`.txt`・`.json`・`.ini`。**照合は大小を区別する**。
  - `path::test_name` (pytest の node id) は位置参照ではないので拾わない。
  - **(d) 行番号の無い bare path と (e) 短い数字ラベルは本検査の対象外**である。根拠: (d) はテストの散文が仮の名前・実行時生成ファイル・架空 fixture 名を意図して書くもので、基点の実測 327 件のうち 30 件が理由付き許可表になる。本件の欠陥の型は**行番号の陳腐化**であり、(d) は範囲外として台帳に残す (§4)。
  - (d) 自体は検査しないが、**架空の (d) の直後に在る (c) はその架空 path を継ぐので `file not found` になる** (現物 0 件。合成 fixture で固定する)。
- **D-4 (解決)。** 順に試す。
  - (i) repository ルートからの相対 path として実在すれば解決。
  - (ii) 囲む peer は無い (conformance のテストは SI 節のような peer の入れ子を持たない)。したがって R-88 の (ii) peer 前置に当たる経路は本件には無い。
  - (iii) **末尾一致** (basename、または `pkg/file.py` のような相対 suffix) で探す。探索範囲は、両 peer の `src/<pkg>/`・`migrations/`・`docs/`・`tests/`・`conformance/`・`deploy/`・`config/`・`docker/` と、共有の `conformance-tests/`・`tools/`・`security/`・`spec/`・repository 直下の `docs/` とする。一意なら解決、複数なら `ambiguous`、0 なら `file not found`。`conformance/` を含めるのは、基点で `conformance_adapter_mitatedb.py` 等が peer の `conformance/` に在るためである (R-88 の allowlist には無い)。**R-88 の basename だけの実装を流用せず、path 成分の suffix 一致を実装する** — `r2db_api/service.py` は `r2db-api/src/r2db_api/service.py` に一意に解決し、basename だけの照合 (両 peer の `service.py` に当たる) では `ambiguous` になってしまう。
  - (iv) 行番号は `1 <= N <= そのファイルの行数`、範囲は `N <= M` かつ `M` も範囲内である。
  - 基点の実測で `service.py:914` (`conformance-tests/test_c04_unsupported_and_safe_errors.py`:157) と `service.py:877` (`conformance-tests/test_c05_limit_declaration_agreement.py`:430) が `ambiguous` になる (両 peer に `service.py` が在るため)。これは腐りではなく**書き方の曖昧さ**であり、許可表には置かず、**WP-2 で path を peer 付きに書き足して解決させる**。
- **D-5 (許可表)。** 機械的に解決できないが正当な参照は、理由付きの許可表に置いて通す。鍵は (source file の repository 相対 path, 囲む scope の dotted name または `<module>`, 参照文字列) とする (単位の行番号は編集で動くので鍵にしない)。表は**集合として pin する**: 行が 1 つ欠けても赤、今は解決するようになった参照が表に残っていても (死んだ許可行) 赤。
  - **起草時点で必要な行は 0 件の見込み**である。実装担当は D-3 の形で**再測**し、赤の全件を報告し、腐り (WP-2 の訂正対象) と許可表候補を分けて出す。
  - **許可表に置くかは 1 件ごとに監督裁定**とする。実装担当は勝手に置かない。
- **D-6 (訂正、WP-2)。** WP-2 で**触る単位の位置参照を全数現物照合して直す** (設計レビュー 1 の F-1)。腐りは §1 に挙げた 3 件に留まらない — 同じ docstring・コメント塊の中の隣接する参照も同時に腐っている (§3.1 の確定分)。訂正は**位置参照の部分だけ**で、文の言い換えはしない (`backend_sqlite.py` の 3 箇所化で文の列挙が増えるのは可)。**行またぎの折り返しは保ち、訂正で 1 行に詰めない** (§2.3 の 6 の正の pin を壊さないため)。各件の訂正後の `file:line` と周辺 ±10 行を報告に貼り、コードレビューが照合する。
- **D-7 (床・空振り禁止)。** 走査した `.py` の本数、単位の数、形 (a)(b)(c) ごとの件数、経路 (i)(iii) ごとの件数に下限を置く (`OPERATING_CONDITIONS.md` §1.5 の 32)。下限は**実装担当の再測から余裕を引いた定数**とし、由来 (実測日・基点・実測値) をコメントに書く (R-88 の D-7 の形)。
  - **形 (a') は現物 0 件なので床を置かない** (合成 fixture で固定する。F-3)。
  - **形 (a) の床は実測からの余裕を 4 以下に固定する** — 連結規則を壊す変異 (§2.4 の M5) が (a) の床を確実に赤にするためである (F-4)。
  - **参考実測** (既存抽出形での基点 `dd12657` の実測): 行番号付き 51 件 (ok 19 / EOF 超 1 / not found 29 / ambiguous 2)。ただし D-2 の連結で `not found` の大半が解消し件数も変わる。**参考値であり、実装担当の再測が正本**である。
- **D-8 (失敗の形)。** 1 件 1 行で全件出す。折り畳まない。形: `<repository 相対 path>:<単位の開始行>: <参照> (<file not found | ambiguous | no preceding path | line N beyond EOF M | bad range>)`。`conformance-tests/` 直下のファイルでは `conformance-tests/<file>:<開始行>: …` と同じ表記になる (基点の 48 本は全て直下である)。
- **D-9 (限界)。** 次の 5 点を、検査の docstring と台帳 R-95 行の両方に**現在形**で書く。
  1. 行数の範囲内で**別の箇所**を指す腐りは検出しない (本件の `structured.py:1583` がその型で、人が読んで見つけた)。
  2. 経路 (iii) は directory を固定しない — 末尾一致の候補が repository のどこかに生き残り行番号が範囲内であれば、module がほかの directory へ移っても検出しない。
  3. (d) の行番号を持たない bare path は検査しない。
  4. 対象は `conformance-tests/` の `.py` だけで、両 peer の `src/`・`tests/` の docstring は対象外である。
  5. backtick の**外**に裸で書かれた `path:N` (例 `CONDITIONS.md:41`) と、ID を接頭に持つ `C-14:476` の形は検査しない。前者は path が backtick に入っていないので path として拾わず、後者は `:` の直前が英数字なので (c) の抽出条件で落ちる。

**却下した代替案**:

1. `conformance-tests/test_control_mapping_register.py` の抽出・解決の関数を import して流用する — 姉妹テストの間の import は依存を作る (R-76/R-77 の規律)。かつ行単位の抽出は docstring の行またぎに合わない。
2. R-88 の検査の対象を `.py` に広げる — `security/CONTROL_MAPPING.md` 用の検査に別の入力形 (docstring の連結) を混ぜると、両方が読みにくくなる。
3. 行またぎを許可表で通す — 腐りを見逃す側に倒れる。
4. (d) の bare path も検査する — 30 件の理由付き許可表が要り、本件の欠陥の型 (行番号の陳腐化) ではない。範囲外として台帳に残す。
5. 両 peer の `src/` の docstring まで対象にする — Class B の別件で規模が違う。範囲外とする。

**未確定で依頼者判断待ち**: 無し (Class C、監督の裁定で進める)。

**設計レビュー 1 の反映 (2026-09-23)**: F-1〜F-13 を**全件採用**し、未コミットの起草版なので本文を直した (訂正註ではない)。F-1 = D-6/§3.1 を「触る単位の位置参照の**全数**現物照合」に広げ、レビューの実測 (`test_c14_authority_boundary.py`:722 の MitateDB `control_plane.py:1146`、`test_c04_unsupported_and_safe_errors.py`:121 の単位の 6 件、`test_c05_limit_declaration_agreement.py`:411 の `service.py:877`) を §3.1 の確定分に加えた。F-2 = D-2 の連結後も残る未解決 11 件を §1 に明記し、`no preceding path` 8 件の訂正を確定して WP-2 の触ってよいパスを **7 本**にした。F-3 = 形 (a') は現物 0 件なので床を置かず合成 fixture で固定し、M2 を fixture 対象にした。F-4 = M5 の期待を「形 (a) の床が赤」に直し、(a) の床の余裕を 4 以下に固定し、唯一残る行またぎ参照 (`test_c05_limit_declaration_agreement.py`:546 の `structured.py:1198`) を現物依存の**正の pin** として完了条件に足した。F-5 = 連結規則を「単位の先頭からの累積 backtick が奇数」と明記。F-6 = コメント塊の単位を「同じ開始 column の連続する `#` 行」に直した。F-7 = D-9 に限界 (5) を足した。F-8 = D-4 (iii) を basename ではなく path 成分の suffix 一致と明記。F-9 = 検査自身の docstring に行番号付きの実参照を書かない規則を §2.1 に足した。F-10 = M4 の例示は実装担当の再測に合わせる (`OPERATING_CONDITIONS.md` §1.5 の 34)。F-11 = 架空の (d) の直後の (c) は `file not found` になる旨を D-3 に足した。F-12 = §1・§3.1 の物理行と D-8 の単位開始行の違いを注記した。F-13 = `rglob` が未追跡 `.py` も見る旨を D-2 に足した。

## 2. WP-1 — 位置参照の検査を足す

### 2.1 タスク

- `conformance-tests/test_conformance_docstring_position_refs.py` を新設し、D-1〜D-9 の検査を置く。抽出・解決の関数は自前で持つ (D-1: 姉妹テストから import しない)。
- テストは少なくとも: (1) 現物の全参照が解決する、(2) 合成 fixture で `bad range`・`ambiguous`・`no preceding path`・`file not found` の 4 判定が出る、(3) 形と経路と走査量の床 (D-7)、(4) 許可表の集合 pin (D-5)、(5) 走査対象が `conformance-tests/` 配下の全 `.py` であること (D-2)。
- 検査を現行の木に掛け、赤になる参照の**全件**を報告する。§3.1 の確定分以外が出たら、**直さず監督の裁定を待つ** (D-5)。
- 経緯トークンを tests に足さない (docstring に `R-95:` と文書パスを書くのは可)。
- **本ファイルの docstring・コメントには行番号付きの実参照を書かない** (形の説明は `path:N` のようなメタ表記にする)。自分自身が走査対象なので、実参照を書くと検査が自分の散文の陳腐化で赤になる (F-9)。
- 本ファイルは両 peer の `src/` の外なので `tools/check_comment_provenance.py` の対象外である (§0)。

### 2.2 触ってよいパス

- `conformance-tests/test_conformance_docstring_position_refs.py` (新規 1 本) のみ。
- `conformance-tests/COLLECTION_FLOOR` は触らない (監督が完了ゲートで更新する)。
- `conformance-tests/README.md` / `CONDITIONS.md` に register 系テストの一覧は無い (R-88 §2.2 の実測)。新設しない。

### 2.3 完了条件

1. **(a)(b) の解決**: `` `path:N` `` / `` `path:N-M` `` が実在の path と範囲内の行に解決する (D-3・D-4)。
2. **(a') の固定**: `` `path`:N `` / `` `path`:N-M `` が (a)/(b) と同じ検査に掛かる。現物 0 件なので**合成 fixture の判定列に (a') を含めて**固定する (D-3・D-7)。
3. **(c) の carry-forward**: 同じ単位の中で**最も近い前の** backtick path を継ぐ。前に path が無い bare `:N` も**抽出はされ**、`no preceding path` で赤になる (抽出条件に「前に path が在ること」を置かない)。
4. **(c) の除外**: `:` の直前の 1 字が英数字のもの (`1:1`・`C-14:476` 等) は位置参照として拾わない (抽出条件はこれだけである)。
5. **単位内の連結** (D-2): 単位の先頭から当該の改行までの backtick の**累積**個数が奇数なら次行の先頭空白を落として空文字で、偶数なら空白 1 個で連結する。行またぎで書かれた path が 1 つの参照として解決する。
6. **行またぎの正の pin** (現物依存): `conformance-tests/test_c05_limit_declaration_agreement.py`:546 の `` `…/structured.py:1198` `` (訂正対象のほかに唯一残る行またぎ参照) が抽出集合に在り、解決することを逐語で pin する。
7. **単位の取り方** (D-2): (α) docstring を `ast` で、(β) コメント塊を `tokenize` で、同じ開始 column の連続する `#` 行の最大の並びとして取る。行末コメントは 1 行 1 単位。失敗の行番号は単位の開始行である。
8. **走査対象** (D-2): `sorted(Path.rglob("*.py"))` で `conformance-tests/` 配下の全 `.py` を走査する。
9. **経路 (i)**: repository ルート相対で実在する path が解決する。
10. **経路 (iii)**: D-4 (iii) の探索範囲で**path 成分の suffix 一致**が一意なときだけ解決し、複数なら `ambiguous`、0 なら `file not found` になる。`r2db_api/service.py` が一意に解決する (basename だけの照合では `ambiguous` になる)。peer の `conformance/` が探索範囲に入っている。
11. **行番号の範囲** (D-4 (iv)): `M < N` は `bad range`、範囲外は `line N beyond EOF M` で赤になる。
12. **拡張子ホワイトリストと node id** (D-3): 大小を区別し、ドット付き識別子を path として拾わない。`path::test_name` を拾わない。
13. **対象外の形** (D-3): 行番号の無い bare path (d) と短い数字ラベル (e) は拾わない。架空の (d) の直後の (c) はその path を継いで `file not found` になる (合成 fixture)。
14. **許可表の集合 pin** (D-5): 表の行の欠落も、死んだ許可行も赤。
15. **床** (D-7): 走査本数・単位の数・形 (a)(b)(c) の 3 種・経路 (i)(iii) の 2 種にそれぞれ下限が在り、各定数に由来 (実測日・基点・実測値) のコメントが在る。**形 (a) の床の余裕は 4 以下**である。形 (a') には床を置かない。
16. **単独実行** (D-1): 本ファイルは単独の `pytest` 呼び出しで意味を持つ (収集セッションに依存しない)。`conformance-tests/test_control_mapping_register.py` から import しない。
17. **(監査照合)** 失敗メッセージが D-8 の形で 1 件 1 行・全件出る。赤の実行の出力をそのまま報告に貼る。
18. **(監査照合)** 現行の木に対して赤になる参照の**全件**を報告し、§3.1 の確定分と、それ以外 (許可表候補) を分けて出す。**確定分以外が出たら直さず監督の裁定を待つ** (D-5。監督の再測が正本)。
19. **(監査照合)** D-9 の 5 つの限界が検査の docstring に現在形で在る (台帳 R-95 行への同じ記載は監督が統合時に行い、§6 で照合する)。
20. **(監査照合)** 床の各定数の実測値 (走査本数・単位数・形 3 種・経路 2 種) を報告に数値で貼り、下限との差を示す ((a) は 4 以下であること。`OPERATING_CONDITIONS.md` §1.5 の 34)。
21. **(監査照合)** 本ファイルの docstring・コメントに行番号付きの実参照が無い (F-9)。`conformance-tests` 全体が緑で、収集の増分 (基点との node id 差) を報告する。`tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑。各コマンドと集計行を報告に逐語で貼る。
22. §2.4 の表に対応の無い行が無い。

### 2.4 完了条件 → 変異

現物に掛ける変異は、現行の木が WP-2 の訂正まで赤なので **WP-2 の後にまとめて 1 回** `tools/dev/mutate.py` で実行してよい。合成 fixture に掛かる変異は WP-1 の時点で実行できる。1 つの変異が赤にするテストは 1 本にする (`tools/dev/mutate.py` は最初の失敗で止まる)。現物を引く例示は、**実装担当の再測に合わせて差し替えてよい** (`OPERATING_CONDITIONS.md` §1.5 の 34)。

| 完了条件 | 変異 | 期待 |
|---|---|---|
| (基準) | M0: 変異なし (訂正後の木そのまま) | `expect: green` |
| 1 | M1: 訂正対象の外の照合済みの参照 1 件 (例 `conformance-tests/test_c27_concurrent_same_key.py`:152 の `` `conformance-tests/conftest.py:96` ``) の行番号を `99999` にする | 現物の検査が `line N beyond EOF M` で赤 |
| 2 | M2: (a') の抽出 (backtick の外の colon) を外す | 合成 fixture の (a') の判定が赤 (現物 0 件なので現物側は動かない) |
| 3 | M3: carry-forward を外し、直前の path を継がない形にする | 現物の (c) が `no preceding path` で赤 |
| 4 | M4: (c) の「`:` の直前が英数字でない」条件を外す | 比率・ID 接頭の語法が参照として拾われ赤 (基点の例 `conformance-tests/test_control_mapping_register.py`:10・:253、`conformance-tests/test_operation_catalog_register.py`:18・:33。例示は再測に合わせる) |
| 5, 6 | M5: 単位内の連結を「常に空白 1 個」に変える | 形 (a) の床が赤 (床の余裕は 4 以下)。同じ変異で §2.3 の 6 の行またぎ pin も赤になる |
| 7 | M6a: コメント塊の単位取りを 1 行 1 単位に変える / M6b: docstring の収集を Module だけに狭める | M6a は (c) の carry-forward が切れて赤、M6b は単位数の床が赤 |
| 8 | M7: 走査対象を `conformance-tests/test_control_mapping_register.py` 1 本に狭める | 走査本数の床が赤 |
| 9 | M8: 経路 (i) の repository ルート相対の判定を外す | 現物の (i) の件数が落ち、経路 (i) の床が赤 |
| 10 | M9a: suffix 一致の一意性を見ず最初の候補を採る / M9b: 探索範囲から peer の `conformance/` を外す / M9c: suffix 一致を basename だけの照合に落とす | M9a は合成 fixture の `ambiguous` が赤、M9b は現物の `conformance_adapter_*` が `file not found` で赤、M9c は `r2db_api/service.py` 形が `ambiguous` で赤 |
| 11 | M10a: `M < N` の判定 (`bad range`) を外す / M10b: 行数の上限判定を外す | それぞれ合成 fixture が赤 |
| 12 | M11a: 拡張子ホワイトリストを外し、ドット付き識別子も path として拾う / M11b: `path::test_name` の除外を外す | それぞれ現物の検査が赤 |
| 13 | M12a: 行番号の無い bare path (d) も参照として拾う / M12b: 架空の (d) の直後の (c) が path を継がない形にする | M12a は現物の検査が赤 (範囲外の 30 件が未解決で出る)、M12b は合成 fixture が赤 |
| 14 | M13a: 許可表から 1 行外す / M13b: 許可表に架空の参照行を足す | M13a は許可表が 1 行以上のときに現物の検査が赤 (0 行で確定した場合は合成 fixture の許可表で同じ 2 方向を示す)、M13b は死んだ許可行の検査が赤 |
| 15 | M14a〜M14c: 形 (a)(b)(c) の床定数を 1 つずつ実測 +1 にする / M14d〜M14e: 経路 (i)(iii) の床定数を 1 つずつ実測 +1 にする / M14f: 走査本数の床を +1 / M14g: 単位数の床を +1 | それぞれ床のテストが赤 (7 entry) |
| 16〜21 | 監査照合 (逐語記録は §2.3 のとおり報告に貼る。16 は単独呼び出し (§2.5 の 1 本目) の集計行と、`grep` で `test_control_mapping_register` の import が 0 件であることを貼る) | — |
| 22 | 本表そのもの | — |

### 2.5 道具の引数

- `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r95 -- conformance-tests/test_conformance_docstring_position_refs.py -q` (このファイルは単独で走る)。
- 報告の前に `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r95 -- conformance-tests -q` を 1 回 (収集の増分を報告する)。
- `tools/dev/mutate.py "$SP/r95-mutations.json" -C .claude/worktrees/r95 --wait 1800`。`tools/dev/mutate.py` は**新規ファイルの作成を扱えない**ので、「走査対象が増える」型の条件は §2.3 に置かない (引き継ぎ書 `docs/work-orders/HANDOVER_20260923_FABLE.md` §5)。
- `tools/check_doc_refs.py`・`tools/public_value_scan.py` を各 1 回。
- 完了ゲート `tools/dev/gate.py` は**監督のみ**。実装担当は走らせない (`OPERATING_CONDITIONS.md` §1.11 の 70)。

## 3. WP-2 — 位置参照の訂正

WP-1 と**同じ変更セット・同じ worktree・同じ実装担当**で、WP-1 → WP-2 の順に行う (検査だけを入れると木が赤のまま統合されるため)。並行 WP は無い。

### 3.1 タスク

- **触る単位の位置参照は全数照合する** (D-6)。下の確定分を直し、**同じ docstring・コメント塊の中に在る他の位置参照も全て**現物照合して、合わないものを同じ変更セットで直す。訂正は位置参照の部分だけで、文は言い換えない。
- **行またぎの折り返しは保つ** (訂正で 1 行に詰めない)。`conformance-tests/test_c05_limit_declaration_agreement.py`:546 の `` `…/structured.py:1198` `` は §2.3 の 6 の正の pin なので、書き方を変えない。
- 確定分 (設計レビュー 1 の実測。**現物が正本**で、訂正先は実装担当が現物で特定し、各件の周辺 ±10 行を報告に貼る。行番号は物理行):
  1. `conformance-tests/test_c20_constraint_declaration_agreement.py`:154 と `conformance-tests/test_c22_dry_run_and_plan.py`:186 の `` `r2db-api/src/r2db_api/structured.py:1583` `` → `self.schema_revision += 1` の現行の行 (実測は `:1821`)。
  2. 同じ 2 つの docstring が引く `` `MitateDB-api/src/mitatedb_api/backend_sqlite.py:207` ``/`` `:250` `` → 現行の 3 か所、`:198` (`create_collection`)・`:294` (`add_field`)・`:434` (`alter_field_constraints`)。**`:458` は roll back の `-= 1` で別物なので引かない。**
  3. `conformance-tests/test_c14_authority_boundary.py`:746 の `` `r2db-api/src/r2db_api/control_plane.py:1574` `` (EOF 1,527 超) → `limit_class="control_requests_per_minute"` を発行する現行の行 (実測は `:1390`)。
  4. 同じコメント塊の `conformance-tests/test_c14_authority_boundary.py`:722 が引く `` `MitateDB-api/src/mitatedb_api/control_plane.py:1146` `` → 同じ発行の現行の行 (実測は `:1322`)。範囲内の指し先違いなので機械では赤にならない。
  5. `conformance-tests/test_c04_unsupported_and_safe_errors.py`:121 から始まる単位の位置参照 — `` `mitatedb_api/cell.py:1751` `` (主張は `is_developer` gate)、`` `conformance_adapter_r2db.py:328` `` (主張は capability probe)、`` `conformance_adapter_r2db_http.py:1605` ``、`` `conformance_adapter_mitatedb.py:487` ``、`` `spec/data-service-api.v1.json:40` ``・`` `:283` `` は、いずれも現物が主張と一致しない。`` `service.py:914` `` (`ambiguous`) は peer 付きの path を書き足した上で、行番号も現物に直す。
  6. `conformance-tests/test_c05_limit_declaration_agreement.py`:411 から始まる単位の `` `service.py:877` `` (主張は「`capabilities()` が `_slot` の中」) も現物と一致しない。peer 付きの path を書き足し、行番号を現行に直す。
  7. `conformance-tests/test_conditions_register.py`:617 と :765 の `` `:16` ``/`` `:22` ``/`` `:61` `` (`no preceding path` 各 3 件) — 指しているのは `conformance-tests/CONDITIONS.md` の行なので、その直後に `:16`, `:22`, `:61` が続く形になるよう直前に `` `conformance-tests/CONDITIONS.md` `` を書き足し、形 (c) で解決させる。**3 つの行が今もそのテスト名参照を持つか**を現物で確かめ、ずれていれば行番号も直す。
  8. `conformance-tests/test_contract.py`:456 の `` `:29` ``/`` `:57-59` `` (`no preceding path` 2 件) — 同ファイル自身の行なので直前に `` `conformance-tests/test_contract.py` `` を書き足し、引いている 2 つのテストの現行の位置に行番号を直す。
- 上記の単位以外が WP-1 の検査で赤になったら、**直さず監督の裁定を待つ** (D-5)。訂正の追加も許可表への追加も実装担当は行わない。

### 3.2 触ってよいパス

- `conformance-tests/test_c20_constraint_declaration_agreement.py`
- `conformance-tests/test_c22_dry_run_and_plan.py`
- `conformance-tests/test_c14_authority_boundary.py`
- `conformance-tests/test_c04_unsupported_and_safe_errors.py`
- `conformance-tests/test_c05_limit_declaration_agreement.py`
- `conformance-tests/test_conditions_register.py`
- `conformance-tests/test_contract.py`

上の **7 本**が確定分である (設計レビュー 1 の F-2)。実装担当が §2.3 の 18 で報告した `no preceding path` / `ambiguous` / `file not found` の**残件**については、**監督が 1 件ごとに裁定し、裁定の記録 (§6.1) をもって当該の `conformance-tests/` 配下の `.py` を触ってよいパスに加える**。裁定前に触らない (D-5)。

### 3.3 完了条件

23. WP-1 の検査が**現行の木に対して緑**になる (許可表は 0 行。監督裁定で行が置かれた場合はその行を除いて未解決が 0)。
24. **(監査照合)** 訂正した**全件** (§3.1 の確定分と、同じ単位の全数照合で見つかった分) の訂正後の `file:line` と周辺 ±10 行を報告に貼り、引用元の文の主張と一致することを示す。照合したが訂正不要だった参照も件数で報告する。
25. **(監査照合)** 訂正した 7 本のファイルの `git diff` が**位置参照の部分だけ**であることを示す (文の言い換えが無い、行またぎの折り返しを変えていない。`backend_sqlite.py` の 3 箇所化で列挙が増える分は除く)。差分を報告に貼る。
26. **(監査照合)** 訂正した 7 本が属する conformance が緑である (§2.5 の `conformance-tests` 全体の呼び出しで足りる。集計行を貼る)。
27. §3.4 の表に対応の無い行が無い。

### 3.4 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 23 | M0〜M14 (§2.4。訂正後の木に掛ける) | M0 は `expect: green`、他は全件 `expect=red got=red` |
| 24 | 監査照合 (訂正後の `file:line` と ±10 行、照合件数を逐語で報告) | — |
| 25 | 監査照合 (`git diff` を逐語で報告) | — |
| 26 | 監査照合 (`conformance-tests` の集計行) | — |
| 27 | 本表そのもの | — |

## 4. 範囲外 (起票のみ)

- 行数の範囲内で**別の箇所**を指す腐りの機械検出 (D-9 (1))。本件の `structured.py:1583` がその型である。
- 経路 (iii) が directory を固定しない件 (D-9 (2))。
- 行番号を持たない bare path (d) の検査 (D-9 (3)、却下 4)。基点の実測で 30 件が未解決になり、理由付き許可表が要る。
- 両 peer の `src/`・`tests/` の docstring・コメントへの同型の検査 (D-9 (4)、却下 5)。Class B の別件である。
- backtick の外に裸で書かれた `path:N` と、ID を接頭に持つ `C-14:476` の形の検査 (D-9 (5))。

## 5. レビューと受け入れ

- 設計レビュー 1 回 (本書 §1〜§2 に対して、WP-1 の着手前。契約を触らないので 1 回である。`OPERATING_CONDITIONS.md` §1.7 の 50)。**実施済み 2026-09-23**: F-1〜F-13 を全件採用して本文に反映した。反映の要約は §1 末尾。
- コードレビュー 1 回 (WP-1 + WP-2 の後。D-6 の**全数照合**の ±10 行の照合を含む)。
- 受け入れ監査 1 回。監督が完了ゲートの集計行・完了条件・監査のパケットを照合して判定する。
- 完了ゲート (`tools/dev/gate.py`) と commit・マージ (`tools/dev/finalize.py`) は監督が行う (`OPERATING_CONDITIONS.md` §1.1 の 2、§1.3 の 19、§1.11 の 70)。
- Class C なので依頼者裁定は要さない。統合後、引き継ぎ書で報告する。

## 6. 記録 (統合時に監督が埋める)

### 6.1 訂正註と監督裁定


- **【訂正註 1 (2026-09-23)】完了条件 12 の node id 側と M11b。** コードレビュー 1 の実測で `::` 除外の分岐は到達不能 (`_INNER_RE`/`_BARE_WHOLE_RE`/`_PATH_TOKEN_RE` のいずれも `:` を含む内容に一致しない) と分かり、監督裁定で死にコードを削除した。`test_pytest_node_id_double_colon_is_not_extracted` は性質のテストとして残るが、これを赤にできる変異は存在しない — **完了条件 12 の node id 側は監査照合** (レビューと監査の実測: 除外を消しても抽出集合は同一)。§2.4 の M11b は実行しない。
- **【訂正註 2 (2026-09-23)】完了条件 6 の pin の値。** `test_c05_limit_declaration_agreement.py:552-554` の `structured.py:1198`/`postgres.py:1069` 自体が腐りだった (現物は `r2db-api/src/r2db_api/structured.py:923` と `postgres.py:1224`)。監督裁定で本件で訂正し (折り返しは保つ)、pin は `:923` で固定した。
- **【訂正註 3 (2026-09-23)】WP-2 の照合範囲。** コードレビュー 1 の指摘で `test_c04_unsupported_and_safe_errors.py:146・:157-160` の引用内容 (`canonical.role`、`unsupported` の列挙 2 件) が現物と不一致だったので、位置参照に加えて**引用内容の事実訂正**を同じ変更セットで行った (言い換えではない。conformance の docstring は来歴検査の対象外)。
- **【監督裁定 1 (2026-09-23)】** 訂正で 109〜115 桁になった 3 行 (`test_contract.py:457-458`、`test_conditions_register.py:766`) は再折り返ししない (D-6 は位置参照の部分だけを許す)。
- **【監督裁定 2 (2026-09-23)】** 単位数の実測は 1452 (報告の 1453 は M14g の変異値)。床 1420 のまま。

### 6.2 実施と受け入れ

- **差分**: 新規 `conformance-tests/test_conformance_docstring_position_refs.py` (node id 25: 単位の連結 (α docstring / β コメント塊 / 行末コメント、累積 backtick が奇数なら空文字連結)、形 (a)(a')(b)(c) の抽出 ((c) は `:` の直前が英数字でない)、経路 (i)(iii、suffix 一致) の解決、行番号の範囲 (`1 <= N`、`N <= M`、EOF)、許可表 0 行の集合 pin、床 (files 49 / units 1452 / a 26 / b 3 / c 17 / i 26 / iii 20 から余裕を引く、(a) の余裕 4)、現物依存の正の pin (`test_c05_limit_declaration_agreement.py:546` の行またぎ参照 `structured.py:923`)、D-9 の限界 5 点を docstring に)。訂正 7 本 30 件 (`$SP/r95-wp2-collation.md` を監査が全件現物照合): `test_c20`/`test_c22` の `structured.py:1583`→`:1821`・`backend_sqlite.py:207/:250`→`:198/:294/:434`、`test_c14` の `control_plane.py:1574`→`:1390` と MitateDB `:1146`→`:1322`、`test_c04` の `service.py:914` → `capabilities_document.py:31` ほか path 訂正と引用内容、`test_c05` の `service.py:877` の peer 付与と `:552-554` の `:923`/`:1224`、`test_conditions_register.py:617・:765` に `conformance-tests/CONDITIONS.md` の path、`test_contract.py:456` に自ファイルの path と `:28`/`:57-59`。`tools/change_class.py` → `class=C`。
- **道具の出力行**: `pt: 25 passed` (単独)、`pt: 1104 passed in 525.28s (0:08:45)` (`conformance-tests`、基点 1079 + 25)。`mutate: 29 mutations, 29 as expected` (M0 green、M1〜M14g、M5a/M5b、M10c; 監査が 29 本の個別ログと sha256 ×2、変異文字列 grep 0 件で再構成)。`check_doc_refs` 0 dangling、`public_value_scan` 0 flagged。
- **設計レビュー 1** (高 4・中 6・低 3、全件反映)、**コードレビュー 1** (中 2・低 4 → 差し戻し 1 `$SP/r95-return-1.md`、全件反映)、**受け入れ監査 1** (未充足 0。要記載 = 訂正註 1、証拠不足 = 単位数・収集増分・変異集計行は監査が独立に再構成して充足)。
- **完了ゲート** (監督単独、最終の木、`--label r95`): `gate: 3899 passed, 2 subtests passed in 325.61s (0:05:25)`、`judge=PASS`、実行クラスタ差分 0 (直前の main 3874 + 25)。`COLLECTION_FLOOR` (3326) は未更新 (下限、更新はフェーズ完了時)。
- **最終判定**: 受け入れ。Class C。台帳 R-95 を閉じ (v1.98)、残余の R-96 (両 peer の `src/`・`tests/` の位置参照) を起票した。

**訂正註 (2026-10-05、R-39 変更セット 2、本文は書き換えない)**: R-39 変更セット 2 (作業指示書 `docs/work-orders/WORK_ORDER_R39_TEST_GAPS_V1.md` §9) が、conformance-tests と両 peer の tests / conformance / README にある「現在の所在の主張」の行番号形の位置参照を `file.py::symbol` 形へ置き換えたため、本書 WP-1 の検査 `conformance-tests/test_conformance_docstring_position_refs.py` が実コーパスの形の数で固定していた床は実測へ下がった (経緯と最終値: SHAPE_A 22 → 4 → 2、SHAPE_B 2 → 0、SHAPE_C 15 → 12 → 10 → 2、ROUTE_I 22 → 12 → 10 → 2、ROUTE_III 17 → 9 → 2。途中の値は置換の範囲を広げるたびに再実測した値で、最終値は R-39 変更セット 2 の差し戻し 3 の後の実測である。SCAN_FILES_FLOOR 47 と SCAN_UNITS_FLOOR 1420 は実測 61 / 1833 のまま変えない)。実コーパスに行をまたぐ位置参照が残らなくなったので、`test_pin_the_one_remaining_line_wrapped_position_reference_in_the_real_corpus` は合成 fixture で同じ連結規則を検査する `test_fixture_line_wrapped_position_reference_is_joined_and_resolved` に置き換えた。本書の変異表は床を下げた後に再実行し 29 件すべて期待どおり (M5a の期待テストは新しい fixture テスト)。床は走査が各 shape を通ることの保証であり、参照を行番号形で残す装置ではない (R-39 監督裁定 Y-9、事後確認待ち)。本検査は、R-39 のガード `tools/tests/test_no_line_number_position_refs.py` の allowlist に残る「時点の記録」の参照に対して引き続き働く。
