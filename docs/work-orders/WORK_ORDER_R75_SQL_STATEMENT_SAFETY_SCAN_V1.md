# 作業指示書 — R-75 両 peer の `src/` の SQL 構築形を見る静的走査

## 0. 出所と基点

- **v1.0 (2026-09-22)。** 基点は**ローカル main `aac5e76`** (作業ツリー `.claude/worktrees/r75` は同一)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-75。
- **変更クラスは Class B** (新規 `tools/tests/` 1 ファイルだけ。src は変異の一時編集を除いて触らない)。実装担当は着手手順 (§3.3) で `tools/change_class.py` の実測により確かめ、判定行を報告に貼る。
- **設計の正本**は `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46 の **(1) SQL 安全性の静的走査**と、そこに写された裁定 **Z5-3・Z5-8〜Z5-11・Z5-15〜Z5-19** である (§5.46 は独立設計レビュー反映済み)。設計文書は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §3 の **D-4** (`:88`)。**本書は §5.46 の (1) をそのまま実施するものであり、新しい決定を足さない。**
- §5.46 の完了条件表のうち本書に掛かるのは **1〜12 と 23** だけである。(2)〜(6) は掛からない — (3)(4)(6) は R-37 の閉止時に実施済み、(2) は R-76、(5) は R-77。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`。§1.5 の 32〜40、§1.10)。

## 1. 問題設定と守るべき条件 (監督確定)

**問題**: 両 peer の `src/` で SQL の構築形を見る静的走査が無い (R-37 閉止後の残余 (1))。両 choke point (`r2db_api.postgres._run`・`mitatedb_api.backend_postgres._execute`) の `isinstance(statement, (sql.SQL, sql.Composed))` は**実行時ガード**であり、choke point を通らない直接の `.execute(` と `sql.SQL(<f-string>)` には掛からない。

**守るべき性質**: 設計 D-4 の「実行は各 peer の既存 `sql.SQL` / `Composed` 専用 choke point だけに残し、**client-influenced statement が plain `str` で到達できない性質を新 module を含む走査で確認する**」。本 WP はこの走査そのものを新設する。

## 2. 決定 (§5.46 の (1) と Z5-3・Z5-8〜Z5-11・Z5-15〜Z5-19 の実施形)

- **D-1 (形)。** AST で SQL の構築形を見る。**SQL キーワードの文字列一致で作らない** (Z5-3)。**データの流れは追わない** (Z5-16)。
- **D-2 (走査対象)。** 両 peer の `src/` 配下の**全 module を AST で発見**し、発見した集合を pin する。psycopg を import するかで絞らない (Z5-18)。`MitateDB-api/src/mitatedb_api/backend_sqlite.py` だけを、理由 (PostgreSQL ではない) を書いて名指しで除外する。**走査の根は両 peer の `src/` に明示的に限る** (Z5-8。`MitateDB-api/` を `rglob` すると `MitateDB-api/docs/f9-execution-assets-v1/` の `.py` 3 件が混ざる)。
- **D-3 (規則 1)。** 走査 module 内の**すべての `sql.SQL(...)` の引数は、静的に文字列リテラルへ畳める式に限る** — 文字列リテラル、リテラル同士の `+`、同じ関数内または module 内の全代入がそれ自体静的に畳める名前。**呼出し位置を問わない** (Z5-16)。
- **D-4 (規則 2)。** **すべての実行呼出しの第 1 引数に、f-string・`%` 書式・`str` の `+` 連結・`.format()` を直接置かない** (`sql.SQL` / `sql.Composed` の `.format()` / `.join()` は除く) (Z5-16)。
- **D-5 (実行呼出しの定義)。** `.execute(` / `.executemany(` と、次の 6 関数の呼出しを指す。いずれも**修飾名で引く** (Z5-15。裸の関数名で引かない)。choke point 2 つ: `r2db_api.postgres._run`・`mitatedb_api.backend_postgres._execute`。同名の wrapper 4 つ: `mitatedb_api.control_plane._execute`・`mitatedb_api.credential_store_postgres._execute`・`mitatedb_api.control_credential_store_postgres._execute`・`r2db_api.credential_store._execute` (Z5-17)。規則 2 は呼出し側に掛かる。
- **D-6 (明示許可表)。** 規則で畳めない既存箇所は、**理由付きの明示許可表 + 件数 pin** に置く。**実装担当は許可表の件数と各行の理由を報告し、採否は監督が裁定する** (Z5-16)。
- **D-7 (空振り禁止)。** 各 peer について、`sql.SQL(...)` と各実行呼出し (6 関数と `.execute(` / `.executemany(`) を **1 件以上観測した**ことを assert する (§1.5 の 32)。
- **D-8 (変異は実行時ガードと重ねない)。** 両 choke point は `isinstance(statement, (sql.SQL, sql.Composed))` の実行時ガードを持つので、**plain `str` の変異だけでは足りない**。`sql.SQL(<f-string>)`・`.format()` の引数の中の `sql.SQL(<f-string>)`・直接 `.execute(` の変異を併せて置く (Z5-11、Z5-19)。
- **D-9 (範囲)。** 新規ファイルは `tools/tests/test_sql_statement_safety_scan.py` **1 本のみ**。`tools/tests` は root suite の `testpaths` の外であり、**`gate.py` では 1 本も走らない** (§5.46 の訂正註 8-7)。**root collection の増分は 0** で、完了ゲートの期待値は直前の main の root 集計行と同数である。`tools/tests` の増分は実装担当が実際に足した node id の数であり、監督が統合の直前に collect-only で確かめる。

## 3. WP-1 — SQL 安全性の静的走査を新設する (Change Set Manifest)

### 3.1 触ってよいパス / 触らないパス

| 触ってよいファイル | 触らないファイル |
|---|---|
| **新規 `tools/tests/test_sql_statement_safety_scan.py`** (これ 1 本だけ)。§3.6 の表の**変異の一時編集**で src を触るのは `tools/dev/mutate.py` の復元付き実行の中だけである | `spec/`、`security/`、`conformance-tests/`、両 peer の `src/` (変異の一時編集を除く)、両 peer の `tests/` (`_ISOMORPHIC_TARGETS` を含む)、`MitateDB-api/docs/f9-execution-assets-v1/`、`tools/tests/test_leaf_import_direction.py` ほか既存の `tools/tests/`、`docs/code-history/`、`docs/design/`、台帳 (記録は監督) |

- src の恒久の変更は 0 なので、位置参照の括弧書きと `docs/code-history/` の訂正の記録は生じない。新規テストに経緯トークン (`WP-`・日付・`review`・`supervisor ruling`) を書かない。

### 3.2 監督実測 (2026-09-22、ローカル main `aac5e76`)

| 対象 | 実測 |
|---|---|
| D-5 の 6 関数の定義行 | `r2db-api/src/r2db_api/postgres.py`:225、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:242、`MitateDB-api/src/mitatedb_api/control_plane.py`:396、`MitateDB-api/src/mitatedb_api/credential_store_postgres.py`:210、`MitateDB-api/src/mitatedb_api/control_credential_store_postgres.py`:53、`r2db-api/src/r2db_api/credential_store.py`:160 |
| `src/` の `.py` | 両 peer 合わせて **87** (`find` で数えた)。peer ごとの内訳は着手手順 (§3.3 の 3) で数え直す |
| 走査外の `.py` | `MitateDB-api/docs/f9-execution-assets-v1/` に **3 件** |
| `sql.SQL(base_statement + "…")` | 両 peer の `platform_declarations.py` に**各 2 件** (r2db `:1101`・`:1104`、MitateDB `:1075`・`:1078`) |
| `sql.SQL(<module 定数>)` | §5.46 起草時の「3 件」から**増えている** — r2db `credential_store.py` の `_SELECT_BY_ID`・`_COLUMNS`・`_CONTROL_SELECT_BY_ID`・`_CONTROL_AUDIT_INSERT`・`_APPLICATION_AUDIT_INSERT`・`_AUDIT_QUERY_UNION_SQL`、`r2db-api/src/r2db_api/ops.py`:238、MitateDB `application_audit.py`:345、`audit_query.py`:404 |

### 3.3 着手手順 (現物照合。台帳 R-75 行の「着手時に現物で照合し直す」)

1. `tools/change_class.py` を実測で走らせ、判定が **Class B** であることを確かめる (判定行を報告に貼る)。
2. **D-5 の 6 関数を現物で照合する** — 修飾名 (module + 関数名) と定義行が §3.2 の表と一致するか。1 件でも食い違えば**そこで止まって監督へ上げる**。
3. **走査対象の集合を現物で列挙する** — 両 peer の `src/` の全 module、peer ごとの件数、`backend_sqlite.py` の名指し除外。**列挙方法の実測** (§5.46 の訂正註 8-7): 実装したコードが `rglob` / `glob` 系か `git ls-files` 系かを、該当行 (`file:line`) で報告に書く。完了条件 12 の変異の赤が作業ツリーで見えるかどうかはこの実測で決まる。
4. **`sql.SQL(...)` の全出現を現物で数え直す** — §3.2 の `sql.SQL(base_statement + "…")` 4 件と `sql.SQL(<module 定数>)` の候補が**規則 1 (D-3) で畳めるか**を実測する。§5.46 は `sql.SQL(<module 定数>)` を「3 件」としているが、監督実測ではそれより多い。件数は現物が正本である。
5. **明示許可表 (D-6) の件数と各行の理由を報告する。採否は監督が裁定する** (§6.1 に空欄を置く)。許可表の裁定を待つ間も実装は止めない (実装担当は案を置き、監督の裁定で増減する)。

### 3.4 実装の形

- 既存の `tools/tests/` の書き方に倣う (手本: `tools/tests/test_leaf_import_direction.py` の docstring と冒頭) — `REPO_ROOT = Path(__file__).resolve().parents[2]`、AST で両 peer の `src` を列挙、集合を pin、**1 テストで全 module を走査して node id を増やさない** (module ごとのパラメータ化をしない)。
- node id は 2 種に分ける。**「構築形テスト」** = 規則 1・2 (D-3・D-4) を assert する node id **1 本**。**「pin テスト」** = 発見集合・名指し除外・許可表の件数・空振り禁止の観測件数を assert するテスト。
- 失敗メッセージは `file:line`・構築形・破れた規則 (規則 1 / 規則 2) を 1 件 1 行で全件出す。
- docstring に次を書く: 規則 1・2、実行呼出しの 6 つの修飾名、走査の根が `src/` に限られること、`backend_sqlite.py` を名指し除外する理由、**データの流れは追わないこと** (この走査が保証しない範囲)、許可表の各行の理由。断言は変異の実測を得た後に書く (§1.5 の 34)。

### 3.5 道具の引数

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r75 -- tools/tests/test_sql_statement_safety_scan.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r75 -- tools/tests -q
tools/dev/mutate.py "$SP/r75-mutations.json" -C .claude/worktrees/r75 --wait 1800
tools/dev/gate.py -C .claude/worktrees/r75 --label r75      # 監督のみ
```

- 実装担当は **suite 全体・`conformance-tests`・`gate.py` を回さない**。変異の spec は完了条件表の変異 1 行につき 1 件。
- root collection の増分は 0 である (`tools/tests` は root の `testpaths` の外で、`gate.py` では走らない)。

spec の形の例 (完了条件 3。§5.46 からの逐語。`old` は着手時に対象ファイルで 1 件一致する行を選ぶ):

```json
{"pytest": ["-q", "tools/tests/test_sql_statement_safety_scan.py"],
 "mutations": [
  {"id": "M3", "expect": "red",
   "file": "MitateDB-api/src/mitatedb_api/backend_postgres.py",
   "old": "<1 件一致する既存行>",
   "new": "<既存行>\ndef _wp5_mutant(cursor, table):\n    _execute(cursor, f\"SELECT * FROM {table}\")\n",
   "tests": ["tools/tests/test_sql_statement_safety_scan.py"]}]}
```

### 3.6 完了条件 → 変異 → 赤になる test id

§5.46 の完了条件表の 1〜12 と 23 を逐語で写し、番号を振り直した (1〜12 は同じ番号、**23 → 13**)。「構築形テスト」「pin テスト」は §3.4 の定義である。

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) | 実施 |
|---|---|---|---|---|
| 1 | 実行呼出しを修飾名で引き (Z5-15、Z5-17)、各 peer で `sql.SQL(...)` と実行呼出しを 1 件以上観測する (空振り禁止) | `tools/tests/test_sql_statement_safety_scan.py`: 修飾名 `r2db_api.postgres._run` を存在しない名前に差し替える | 同ファイルの観測件数の assert (新規) | 実装担当 |
| 2 | 規則 2: r2db の choke point に f-string を直接渡したら赤 | `r2db-api/src/r2db_api/postgres.py`: `_run(cursor, f"SELECT … {x}")` を行う一時関数を 1 つ足す | 構築形テスト | 実装担当 |
| 3 | 規則 2: MitateDB の choke point に f-string を直接渡したら赤 | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: `_execute(cursor, f"SELECT … {x}")` を行う一時関数を 1 つ足す (spec の例は上) | 構築形テスト | 実装担当 |
| 4 | 規則 1: `sql.SQL(...)` の引数は静的に畳める式に限る (Z5-16) | 3 件。`r2db-api/src/r2db_api/postgres.py`・`MitateDB-api/src/mitatedb_api/backend_postgres.py`: それぞれ `sql.SQL(f"SELECT … {x}")` を choke point に渡す一時関数を足す。`r2db-api/src/r2db_api/postgres.py`: 一時関数の中で `q = "SELECT 1"` の後に `q = f"SELECT {x}"` と再代入し、`sql.SQL(q)` を作る (全代入が静的でない名前) | 構築形テスト | 実装担当 |
| 5 | 規則 1 は呼出し位置を問わない: `.format()` の引数の中の `sql.SQL(<f-string>)` も赤 (Z5-19) | `MitateDB-api/src/mitatedb_api/backend_postgres.py`: `sql.SQL("SELECT {} FROM t").format(sql.SQL(f"{x}"))` を choke point に渡す一時関数を足す | 構築形テスト | 実装担当 |
| 6 | 規則 2: choke point を通らない直接の `.execute(` に f-string が渡ったら赤 (Z5-17) | 2 件。`r2db-api/src/r2db_api/ops.py`・`MitateDB-api/src/mitatedb_api/ops.py`: それぞれ `cursor.execute(f"SELECT … {x}")` を行う一時関数を足す | 構築形テスト | 実装担当 |
| 7 | 規則 2 は同名の wrapper 4 つの呼出しにも掛かる (Z5-17) | `r2db-api/src/r2db_api/credential_store.py`: `_execute(cursor, f"SELECT … {x}")` を行う一時関数を足す | 構築形テスト | 実装担当 |
| 8 | SQL キーワードの文字列一致で作らない (Z5-3。実行呼出しに渡らない SQL 風の f-string は赤にしない) | `r2db-api/src/r2db_api/ops.py` (psycopg を import する module): どの実行呼出しにも渡らない f-string の SQL 風文字列 (`f"SELECT … FROM {x}"`) を 1 つ足す。**`expect: green`** (Z5-19。2〜7 の赤と対にして、判定が構築形で決まることを示す) | 構築形テストが緑のまま | 実装担当 |
| 9 | 走査の根は両 peer の `src/` に限る (Z5-8) | `tools/tests/test_sql_statement_safety_scan.py`: MitateDB の走査の根を `MitateDB-api/src` から `MitateDB-api` に広げる (`MitateDB-api/docs/f9-execution-assets-v1/` の `.py` 3 件が混ざる) | pin テスト | 実装担当 |
| 10 | `src/` の全 module を AST で発見し、`backend_sqlite.py` だけを理由付きで除外した集合が pin されている (Z5-18) | 2 件。`tools/tests/test_sql_statement_safety_scan.py`: 発見の結果から 1 module を落とす。名指し除外から `backend_sqlite.py` を外す | pin テスト | 実装担当 |
| 11 | 規則で畳めない既存箇所の明示許可表が理由付きで件数 pin されている (Z5-16) | `tools/tests/test_sql_statement_safety_scan.py`: 許可表から 1 行を外す (許可表が 0 件なら、存在しない箇所を指す行を 1 つ足す) | pin テストまたは構築形テスト | 実装担当 |
| 12 | 新しい module を、psycopg を import しなくても走査する (設計 D-4「新 module を含む走査」、Z5-18、訂正註 8-7) | 両 peer のいずれかの `src/` に **psycopg を import しない**新規 module を 1 つ足し、引数の cursor へ f-string を渡す実行呼出し (`cursor.execute(f"SELECT … {x}")`) を置く | **構築形テストの node id 1 本だけを tests に指定する** (Z5-19)。列挙が `git ls-files` 系なら作業ツリーでは見えないので、実測した列挙方法を報告に書き、監督が §5.45 の訂正註 7 の手順 (記録した HEAD の上の捨てコミット) で赤を確かめる | 実装担当 (列挙が `git ls-files` 系なら監督) |
| 13 | 上の表に、変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜22 の各行に「変異」または「監査照合」が入っていることを照合し、結果を報告に貼る | — | 実装担当 |

- **完了条件 13 の中の「1〜22」は §5.46 の表の番号である** (完了条件の文言は逐語のまま残す)。本書では **1〜13** に当たる (振り直しの対応: §5.46 の 1〜12 → 本書 1〜12、§5.46 の 23 → 本書 13)。
- **件数 (下限)**: 完了条件 13 件 = 変異を持つ行 12 件 (1〜12。変異は **16 件** — 4 は 3 件、6・10 は各 2 件、8 は `expect: green`) + 監査照合 1 件 (13)。§5.45 の訂正註 6 のとおり、実装担当は変異が素通りする場面を見つけたら足す。

### 3.7 報告に貼るもの

- `tools/dev/pt.py` の集計行 2 本 (新規ファイル単体と `tools/tests` 全体)、`tools/dev/mutate.py` の変異表の全行 (`expect` / `got`、復元の sha256 照合)、`log=` のパス。
- 着手手順 (§3.3) の各出力: `tools/change_class.py` の判定行、6 関数の照合結果 (`file:line`)、走査集合の件数 (peer ごと) と列挙方法の `file:line`、`backend_sqlite.py` の名指し除外の `file:line`。
- **明示許可表の件数と各行の理由** (D-6。**監督の裁定待ち**として報告する) と、`sql.SQL(base_statement + "…")` 4 件・`sql.SQL(<module 定数>)` の実測件数と規則 1 での判定。
- 空振り禁止の観測件数 (D-7。peer ごとの `sql.SQL(...)` と各実行呼出し)。
- 完了条件 13 の照合結果。`tools/tests` の node id の増分と、root collection の増分が 0 である根拠。
- 新規ファイルを足すので、`tools/check_comment_provenance.py` (`--register`)・`tools/check_doc_refs.py`・`tools/public_value_scan.py` を worktree の中で走らせた結果。

## 4. 却下した代替案 (§5.46 からの逐語)

- **Z5-3 — SQL キーワードの文字列一致**: 「**SQL 安全性の走査は SQL キーワードの文字列一致で作らない。**AST で「execute の choke point に到達する値がどう構築されたか」を見る形にする」。根拠 (監督実測): 「キーワード一致だと `r2db-api/src/r2db_api/delete_confirmation.py`:127・138・163・243 の削除確認の句 (利用者が打ち込む文字列で SQL ではない) と `MitateDB-api/src/mitatedb_api/ops.py`:798 のエラーメッセージが偽陽性になる」。
- **Z5-10 の (a)〜(d) のデータフロー規則** (Z5-16 が覆した): Z5-10 は実行呼出しの第 1 引数が「(a) 文字列リテラル (静的 SQL)、(b) `sql.SQL(<文字列リテラル>)`・`sql.Identifier` / `sql.Literal` / `sql.Placeholder` と、それらの `.format()` / `.join()` / `+` による合成、(c) 上の (a)(b) だけから作られた module 定数、(d) choke point の引数 (呼び出し元で同じ規則が掛かる)」のいずれかなら許可する形だった。Z5-16 はこれを「**データの流れを追わない 2 本立て**に置き換える (Z5-10 の本文は残し、本項で覆す)」とした (本書 D-3・D-4)。
- **psycopg を import する module に絞る走査** (Z5-18 が覆した): Z5-10 は走査を「**psycopg を import する両 peer `src/` module の全 `.execute(` / `.executemany(` 呼び出し**」に絞っていた。Z5-18 は「走査対象は両 peer の `src/` 配下の**全 module を AST で発見**し、`backend_sqlite.py` だけを理由付きで名指し除外する (psycopg を import するかで絞らない)」とした (本書 D-2)。Z5-10 の `backend_sqlite.py` の走査外と、明示許可表 + 件数 pin は Z5-16・Z5-18 で引き継がれる。

## 5. レビューと監査

- **設計レビューは行わない。**§5.46 は独立設計レビュー反映済みであり、R-75 はその (1) をそのまま実施する。設計に無い検査・機構を足す必要が生じたら、実装前に報告して監督裁定を得る (§1.5 の 37)。
- **コードレビュー 1 回** (WP-1 の実装の後、別に起動した reviewer)。
- **受け入れ監査 1 回**。受け入れは監督が完了ゲートの集計行・§3.6 の対応表・監査のパケットを照合して判定する (Class B)。

## 6. 実施記録 (統合時に監督が埋める)

### 6.1 明示許可表の採否 (監督裁定)

実装担当の報告 (2026-09-22): 許可表は **3 件**。`sql.SQL(base_statement + "…")` 4 件と `sql.SQL(<module 定数>)` 16 件 (r2db `credential_store.py` 13、`ops.py` 1、MitateDB `application_audit.py` 1、`audit_query.py` 1) は規則 1 で畳めたので許可表に無い。

| # | 箇所 | 理由 (実装担当) | 採否 |
|---|---|---|---|
| 1 | `r2db-api/src/r2db_api/postgres_sql.py:71` | `sql.SQL("ASC" if direction == "asc" else "DESC")` — 三項式 (`IfExp`)。規則 1 が列挙する形 (リテラル、リテラル同士の `+`、静的に畳める名前) の外 | **採用**。両分岐ともリテラルで client の値は入らないが、`IfExp` を規則 1 に足すのは設計外の拡張 (§1.5 の 37) なので許可表に置く |
| 2 | `MitateDB-api/src/mitatedb_api/postgres_sql.py:23` | `_OPERATOR_SQL = {…: sql.SQL(token) for … in SQL_OPERATOR_TOKENS.items()}` — `token` は dict 内包の for-target で `name = expr` の代入ではない。`SQL_OPERATOR_TOKENS` は import 元のリテラル dict だが、import 越えの解決はデータの流れの追跡になる (Z5-16) | **採用** |
| 3 | `MitateDB-api/src/mitatedb_api/postgres_types.py:25` | `_TYPE_SQL = {…: sql.SQL(native) for … in _TYPES.items()}` — 同じく for-target。`_TYPES` は同 module のリテラル dict | **採用** |

### 6.2 訂正註と監督裁定 (§0〜§5 の本文は書き換えない)

- **【訂正註 1 (2026-09-22)】D-4 (規則 2) の「第 1 引数」の読み。** D-5 の 6 関数のシグネチャは `(cursor, statement, params=())` なので、6 関数の呼出しでは規則 2 が掛かるのは **statement 引数 (第 2 位置引数、`args[1]`)** であり、`.execute(` / `.executemany(` の呼出しでは第 1 引数である (§3.5 の spec 例 `_execute(cursor, f"…")` が示す形)。実装担当の解釈を監督が追認する。§5.46 の「第 1 引数」の文言は変えない。
- **【訂正註 2 (2026-09-22)】完了条件 12 の実施法。** `tools/dev/mutate.py` は新規ファイルの作成を扱えないので、完了条件 12 (新規 module の走査) は spec に載せず、実装担当が `tools/dev/pt.py` で手動実施し (probe を置く → 構築形テストの node id 1 本が赤 → 削除 → 緑、`git status --short` クリーン)、コードレビューが再現する。列挙は `rglob` 系 (`tools/tests/test_sql_statement_safety_scan.py` の `_discover` 相当の行) なので作業ツリーで赤が見える。

### 6.3 実施と受け入れ

- **差分**: 新規 `tools/tests/test_sql_statement_safety_scan.py` 1 本 (node id 5: 構築形テスト 1 + pin テスト 4)。src・spec・security・conformance-tests は不変。`tools/change_class.py` (パス指定) → `class=B`。
- **実測 (2026-09-22、ローカル main 4b738f4 の上)**: 走査集合 r2db 41 / MitateDB 45 (`backend_sqlite.py` 名指し除外、peer ごとの逐語一覧で pin)、列挙 `rglob("*.py")`。観測: 6 関数の呼出し 42/42/17/9/9/37 (定義 module 内の裸名だけで解決。`._run(`/`._execute(` の属性呼出しは両 peer 0)、`sql.SQL(...)` r2db 173 / MitateDB 141、属性 `.execute(` 26 / 41、`.executemany(` 0 / 0 (peer 別に pin)。`from psycopg import sql` を持つ module 21、import 形・構築子別名の違反 0 (注釈と `isinstance` の型引数は除外 — 除外なしでは 35 件 / 8 module の偽陽性)。規則 1 の違反は許可表の 3 件と完全一致 (`old` は `ast.get_source_segment` との完全一致、死行 0・未被覆 0)。
- **道具の出力行**: `pt: 5 passed`、`pt: 582 passed` (`tools/tests`、基準 577 + 5)。`mutate: 28 mutations, 28 as expected, restores verified 7/7 files (sha256 x2), grep counts unchanged` — C1〜C11 の 16 件 (C8 は expect green、C10a は一覧から 1 件落とす形に置換し旧形は C10a2) + 差し戻しで足した R1〜R12。完了条件 12 は手動 (`r2db-api/src/r2db_api/_wp_r75_m12_probe.py` 相当の probe を置いて構築形テストの node id 1 本が赤、削除して緑) をコードレビューが 4 巡とも再現。
- **§3.6 の表への追記 (差し戻しで足した変異の対応)**: R1 (引数が module 定数を shadow)・R5 (`+=`)・R7 (`global`)・R8 (入れ子 def のクロージャ)・R10 (`nonlocal`)・R12 (class 本体の束縛は method の chain に積まない) → 完了条件 4 (規則 1 の名前解決)。R3 (同一行の外側 `sql.SQL` を f-string 化) → 完了条件 11 (許可表の完全一致)。R6 (`cursor.execute(query=f"…")`) → 完了条件 6 (規則 2 の keyword 形)。R2 (`from psycopg.sql import SQL`)・R9 (`SQL = sql.SQL`)・R11 (`_H = {"s": sql.SQL}`) → 完了条件 1 の前提 (`sql.SQL` の綴りを pin する import 形・別名の検査)。R4 (属性 `.execute` の認識を壊す) → 完了条件 1 (空振り禁止)。
- **コードレビュー 4 巡** (1 巡目 高 2・中 7・低 5 → 差し戻し 1; 2 巡目 中 4・低 2 → 差し戻し 2; 3 巡目 中 2・低 2 → 差し戻し 3; 4 巡目 全件閉)。監督裁定の要点: 局所束縛は module へ fallback しない (scope chain、`global`/`nonlocal` は汚染)、`psycopg.sql` の import 形と構築子別名を pin、許可表は `old` の完全一致 + 違反集合との等価、走査集合は逐語一覧で pin、`sql.SQL(_A) + sql.SQL(_B)` は赤のまま (Z5-16 の除外は `.format()`/`.join()` のみ)、経緯トークンは冒頭の `R-75:` と文書パスだけ許す。残した低 1 件: 除外 2 形は部分木全体 (内部に値を作る式を書く形は現物 0 件)。
- **受け入れ監査**: 完了条件 1〜13 全て充足、未充足 0。証拠不足は完了ゲート (監査時点で実行中) と `mutate.py`・`--register` の stdout 集計行 (per-mutation ログ 28 本と clean な作業ツリーで代替)。所見: `sql.Composed(` は現物 0 件で pin が無い → D-3 の範囲 (`sql.SQL(...)`) どおりとし pin しない (`sql.Composed(str)` は psycopg の実行時 TypeError で止まる)。docstring の「type-tuple」は実装 (`isinstance` の第 2 引数全般) より狭い文言 — 安全側、据え置き。
- **完了ゲート** (監督単独、`tools/dev/gate.py -C .claude/worktrees/r75 --label r75`): `gate: 3844 passed, 2 subtests passed in 340.18s`、`judge=PASS`、実行クラスタの `pg_database`/`pg_roles` 差分 0。root collection の増分 0。
- **最終判定**: 受け入れ。台帳 R-75 は閉じる (v1.90)。
