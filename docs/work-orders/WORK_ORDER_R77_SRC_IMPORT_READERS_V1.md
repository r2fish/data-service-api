# 作業指示書 — R-77 両 peer の `src/` の import に読み手が在ることを検査するテスト

## 0. 出所と基点

- **v1.0 (2026-09-22)。** 基点はローカル main `4b738f4`。作業 worktree は `.claude/worktrees/r77` (基点と同一)。
- 台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-77**。設計の正本は作業指示書 `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46 の **(5) 読み手検査の偽陰性 (文字列注釈) の手当て** と、そこが引く裁定 **Z5-1 (5)・Z5-5・Z5-13**、同書 §5.45 の**訂正註 4** (読み手を失ったものの検査) と**訂正註 8-4** (その適用範囲) および**訂正註 8-7** (新規ファイルを足す WP は列挙方法を実測する)。設計文書は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §4 の WP-5 節と §10.19 の (4)。
- 変更クラスは **Class B** (`tools/tests/` のみ。`src` は変異の一時編集を除いて触らない)。設計文書は起こさず、決定は本書 §2 に置く。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`、§1.5 の 32〜40、§1.10)。

## 1. 問題設定と守るべき条件

**問題**: 「読み手 0」を数える AST 検査は、**文字列注釈だけが読む名前** (`ast.Name` に現れない) を読み手 0 と誤判定し得る (R-37 閉止後の残余 (5))。§5.46 の (5) は scratchpad の一回限りのスクリプトで手当てする第一案を採った (Z5-13) が、WP-5 が閉止のみに縮小されたので実施されず、**repo に恒久の読み手検査は無い**。

**守るべき条件**: `MRA` §4 の WP-5 節の閉止条件「責務・依存方向・回帰証拠」のうち**依存方向** — 「import は読み手を持つか、意図的な facade 再 export として記録されている」— を持続的に保つ。検査は両 peer の `src/` だけを見る。`spec/`・`security/`・`conformance-tests/` に触れない。

## 2. 決定 (監督裁定 2026-09-22)

**恒久のテストにする。** Z5-13 の「恒久テストにはせず」は WP-5 の範囲縮小の下での判断であり、台帳 R-77 行は「恒久の検査にするか、import を削るときの手順に留めるかは着手時に決める」と開いている。新規 `tools/tests/test_src_import_readers.py` **1 本**。

- **D-1 (走査対象)。** 両 peer の `src/` の全 module を `rglob("*.py")` で発見し、`tools/tests/test_src_import_cycles.py` と**同じ peer ごとの dotted name の逐語一覧で pin する** (`set(発見) == set(pin)`)。同じ一覧を**複製する** — `tools/tests` 間で import せず、共有 helper を作らない。除外なし。
- **D-2 (「読み手」の定義)。** module 内で import した名前 (`import a.b` は `a`、`from x import y as z` は `z`) について、読み手は次のいずれか。
  - (a) その module の中の `ast.Name` (Load) の出現。属性参照 `a.b` は `a` の `ast.Name` としてここに含まれる。
  - (b) `__all__` のリテラル要素。
  - (c) **文字列注釈** — 引数・戻り値・`AnnAssign` の annotation にある `ast.Constant` の `str` を `ast.parse(mode="eval")` し、現れる `ast.Name`。入れ子 (`"list[Foo]"` の `Foo`) も含む。parse できない文字列は読み手にしない。
  - (d) `from __future__ import annotations` は副作用 import なので**常に読み手ありとみなす**。
- **D-3 (判定)。** 読み手 0 の import は、**理由付きの明示許可表** (peer, module, 名前, 理由) に在るときだけ許す。理由は `MRA` §10.19 の (4) の「意図的な facade 互換」の記録、または facade identity test の `file:line`。許可表は**件数ではなく行の集合で pin** し、「許可表 == 許可なしで走査した違反集合」の等式を assert する。したがって**現物に読み手が現れた許可行 (死んだ許可行) も赤**になる。
- **D-4 (空振り禁止、`OPERATING_CONDITIONS.md` §1.5 の 32)。** 文字列注釈だけが読む名前が両 peer 合わせて 1 件以上観測されること。**件数ではなく (peer, module, 名前) の集合で pin する** (監督実測は §3.2 の 1)。
- **D-5 (追わないもの)。** データの流れは追わない。動的 import (`importlib`・`__import__`) と `getattr` による参照は読み手にしない。**この限界を docstring に書く。**
- **D-6 (範囲)。** 新規ファイルは `tools/tests/test_src_import_readers.py` 1 本のみ。既存のテストを変えない。src の import を削る・足す変更は本 WP では行わない (変異の一時編集を除く)。

## 3. WP-1 Change Set Manifest — `tools/tests/test_src_import_readers.py` の新設

### 3.1 触ってよい・触らないパス

| 触ってよい | 触らない |
|---|---|
| `tools/tests/test_src_import_readers.py` (新規。本 WP の変更セットはこの 1 ファイルだけ) | `spec/`、`security/`、`conformance-tests/`、`tools/tests/test_src_import_cycles.py`、`tools/tests/test_leaf_import_direction.py`、`tools/tests/test_sql_statement_safety_scan.py` (R-75)、両 peer の `src/` と `tests/` (**変異の一時編集を除く**)、`docs/`、台帳 (記録は監督) |

- **変異の一時編集**は §3.6 の表の `file` 欄のとおり。`mutate.py` が原状復帰と sha256 照合を行う。
- **並行 WP との重なり (`OPERATING_CONDITIONS.md` §1.2 の 16・17)**: R-75 が `.claude/worktrees/r75` で `tools/tests/test_sql_statement_safety_scan.py` を新設している。本 WP の作業ツリーは `.claude/worktrees/r77`、変更セットは `tools/tests/test_src_import_readers.py` の 1 ファイルで、**重なりは 0**。変異の一時編集は各 worktree の中で閉じ、復元される。
- root collection の増分は **0** (`tools/tests` は root の `testpaths` の外で、`gate.py` では 1 本も走らない。§5.45 の訂正註 8-7)。`tools/tests` の増分は実装担当が実際に足した node id の数であり、報告に書く。

### 3.2 監督実測 (2026-09-22、ローカル main `4b738f4`。scratchpad の一回限りのスクリプト)

1. **文字列注釈だけが読む名前は 3 件**: r2db `src/r2db_api/postgres.py`:118 の `BoundMutation`、MitateDB `src/mitatedb_api/audit_query.py`:32 の `Sequence`、同 `src/mitatedb_api/http.py`:17 の `Iterator`。
2. **`from __future__ import annotations` を除く読み手 0 の import**: r2db **44 件** — `postgres.py`:113・117・117・118 の `_escape_like_literal`・`_FIELD_TYPE_SQL`・`_JSONB_SQL`・`ConstraintPatch`、`structured.py` の 39 件 (facade)、`structured.py`:10 の `Decimal`。MitateDB **8 件** — `backend_postgres.py`:99-100 の `_INT_DOMAIN_RANGES`・`_check_domain`・`_RESERVED_EXACT`・`_RESERVED_PREFIX`、`cell.py`:41・52・55 の `_canonical_where_json`・`_deny_provisional_field`・`_as_traversable`、`control_http.py`:49 の `_CredentialMissing`、`main.py`:598 の `build_control_service`。
3. `r2db-api/src/r2db_api/ops.py` は `from .errors import FoundationError, fail` を持ち、`errors.py` の `violation`・`observed_type_of` を**参照しない** (完了条件 3 の変異の前提)。
4. `__all__` を持つ src の module は両 peer に複数在る (例 `r2db-api/src/r2db_api/__init__.py`:15)。

### 3.3 着手手順

1. 作業 worktree `.claude/worktrees/r77` が基点 `4b738f4` と同一であることを確かめる。
2. §3.2 の 1〜4 を自分で再照合する (**食い違いが 1 件でもあれば、そこで止まって監督へ上げる**)。
3. `tools/tests/test_src_import_cycles.py` の書き方 (`REPO_ROOT = Path(__file__).resolve().parents[2]`、`SRC_ROOTS`、`PINNED_MODULES` の逐語一覧、**1 テストで全 module を走査して node id を増やさない**形) に倣って実装する。
4. §3.2 の 2 の読み手 0 の import が `MRA` §10.19 の (4) の記録と一致するかを**現物で照合する**。記録に無いもの (例 `structured.py`:10 の `Decimal`、`main.py`:598 の `build_control_service`) は**削らず**、許可表に理由「記録なし・R-77 起草時の現状」で置き、**報告に一覧を貼る** (扱いは監督裁定。§6.1)。
5. `pt.py` で新規ファイル単体 → `tools/tests` 全体の順に緑を確かめる。
6. `mutate.py` を §3.6 の変異で回す。**1 変異 = 1 entry** (`mutate.py` は最初の不一致で止まる)。
7. §3.7 を報告に貼る。suite 全体・`conformance-tests`・`gate.py` は回さない。

### 3.4 実装の形

- module の集合 (D-1): `SRC_ROOTS` の再帰の `.py` を `rglob("*.py")` で列挙し、package 相対のドット名を node とする。`PINNED_MODULES` と peer ごとに集合等式で照合する。**列挙方法の該当行を `file:line` で報告に書く** (§5.45 の訂正註 8-7)。
- import した名前の取り出し (D-2 の頭): 各 module の AST を `ast.walk` し、`ast.Import` / `ast.ImportFrom` の alias から**束縛される名前**を取る (`import a.b` → `a`、`import a.b as c` → `c`、`from x import y as z` → `z`)。`from x import *` は名前を束縛しないので対象にしない。
- 読み手 (D-2 の (a)〜(d)): (a) `ast.Name` の Load 出現を集める (import 文自身が作る名前は読み手に数えない)。(b) `__all__` の代入のリテラル要素の文字列。(c) 注釈位置 (`arg.annotation`、`FunctionDef`/`AsyncFunctionDef` の `returns`、`AnnAssign.annotation`) にある `ast.Constant` の `str` を `ast.parse(mode="eval")` して `ast.walk` し、現れる `ast.Name` を集める (parse 失敗は無視)。(d) `from __future__ import annotations` はその module で常に読み手ありとする。
- 判定 (D-3): 読み手 0 の import を `(peer, module, 名前)` の集合として作り、**許可表の集合と一致する**ことを assert する。不一致は両向き (許可に無い違反 / 現物に無い許可行 = 死んだ許可行) を全件並べて失敗する。許可表は各行に理由の文字列を持ち、行の集合で pin する。
- 空振り禁止 (D-4): 文字列注釈でだけ読まれる `(peer, module, 名前)` の集合を別に求め、§3.2 の 1 の 3 件と一致することを assert する。
- docstring に D-5 の限界 (動的 import・`getattr` は追わない。データの流れは追わない) と、許可表を増やすときは `MRA` §10.19 の (4) の記録か facade identity test の `file:line` を理由に要することを書く。
- **経緯トークンを入れない**: 冒頭の出所行 `R-77: …` と文書パスの参照だけを許し、`WP-`・日付・`review`・`supervisor ruling` は書かない。

### 3.5 道具の引数

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r77 -- tools/tests/test_src_import_readers.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r77 -- tools/tests -q      # 基準 577 + 増分
tools/dev/mutate.py "$SP/r77-mutations.json" -C .claude/worktrees/r77 --wait 1800
tools/dev/gate.py -C .claude/worktrees/r77 --label r77        # 監督のみ
```

spec の形の例 (完了条件 3。`old` は着手時に対象ファイルで 1 件一致する行を選ぶ):

```json
{"pytest": ["-q", "tools/tests/test_src_import_readers.py"],
 "mutations": [
  {"id": "M3", "expect": "red",
   "file": "r2db-api/src/r2db_api/ops.py",
   "old": "from .errors import FoundationError, fail",
   "new": "from .errors import FoundationError, fail\nfrom .errors import violation",
   "tests": ["tools/tests/test_src_import_readers.py"]}]}
```

- python は main checkout の `.venv/bin/python`。Bash timeout は 600000。終了コードは pipe の外で取る。

### 3.6 完了条件 → 変異 → 赤になる test id

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) | 実施 |
|---|---|---|---|---|
| 1 | 文字列注釈だけが読む名前 3 件 (§3.2 の 1) が読み手として観測される (D-4、空振り禁止) | `tools/tests/test_src_import_readers.py`: 読み手検査から文字列注釈の parse (D-2 (c)) を外す → 3 件が読み手 0 になり赤 | 文字列注釈の読み手の集合 pin (新規) | 実装担当 |
| 2 | 文字列注釈の**入れ子** (`"list[Foo]"` の `Foo`) も読み手に数える (D-2 (c)) | `tools/tests/test_src_import_readers.py`: 入れ子を辿らず最外の名前だけ取る形に変える。**§3.2 の 1 の 3 件に入れ子が無ければ**、入れ子を持つ src の注釈を実測して選び、その名前に対する変異に置き換える (実測を報告に貼る) | 1 と同じ | 実装担当 |
| 3 | 読み手 0 の import が赤になる (D-3) | `r2db-api/src/r2db_api/ops.py`: `from .errors import violation` を 1 行足す (§3.2 の 3) | 許可表 == 違反集合 の assert (新規) | 実装担当 |
| 4 | `__all__` のリテラル要素は読み手である (D-2 (b)) | `tools/tests/test_src_import_readers.py`: `__all__` の扱いを外す → 現状の src で赤になるかを**実装担当が実測**する。赤にならなければ、`__all__` に名前を持つ module (例 `r2db-api/src/r2db_api/__init__.py`) の `__all__` からその名前を 1 つ外す変異に置き換える | 3 と同じ | 実装担当 |
| 5 | 許可表は行の集合で pin される (D-3) | 2 件。`tools/tests/test_src_import_readers.py`: 許可表から 1 行外す → 赤。現物に無い行を 1 行足す → 赤 | 3 と同じ | 実装担当 |
| 6 | 死んだ許可行 (現物に読み手が現れた許可行) が赤になる (D-3) | 許可表の 1 行の名前に読み手を足す一時編集 (該当 src の module 内にその名前の参照を 1 つ足す) → 赤 | 3 と同じ | 実装担当 |
| 7 | 走査集合が pin される (D-1) | `tools/tests/test_src_import_readers.py`: `PINNED_MODULES` の一覧から 1 module 落とす → 赤 | 走査集合の集合等式 (新規) | 実装担当 |
| 8 | 上の表に、変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜7 の各行に「変異」または「監査照合」が入っていることを照合し、結果を報告に貼る | — | 実装担当 |

**件数 (下限)**: 完了条件 8 件 = 変異を持つ行 7 件 (1〜7。変異は **8 件** — 5 が 2 件) + 監査照合 1 件 (8)。§5.45 の訂正註 6 のとおり、実装担当は変異が素通りする場面を見つけたら足す。

### 3.7 報告に貼るもの

1. §3.2 の 1〜4 の再照合の結果 (食い違いの有無)。
2. module の列挙方法の該当行 (`file:line`) と、観測した module 数・import した名前の総数・読み手 0 の件数 (peer 別)。
3. §3.3 の 4 の照合結果 — `MRA` §10.19 の (4) と一致した許可行、および**記録に無い読み手 0 の import の一覧** (`file:line` と理由欄の文言)。
4. `pt.py` の 2 本の集計行 (新規ファイル単体、`tools/tests` 全体) と、`tools/tests` の node id の増分。
5. `mutate.py` の全件の `expect=` / `got=` の行と、復元の sha256 照合の結果。完了条件 4 の実測 (`__all__` の扱いを外して赤になったか) を明示する。
6. 完了条件 8 の監査照合の結果 (1〜7 の各行に変異が在ること)。
7. docstring に書いた D-5 の限界の文。

## 4. 却下した代替案

- **Z5-13 の第一案 (scratchpad の一回限りのスクリプト)** — 変異を対応付けられず (`OPERATING_CONDITIONS.md` §1.5 の 33)、持続しない。WP-5 の縮小で実際に実施されないまま残った。
- **手順として文書に書く形 (import を削るときの手順に留める)** — `OPERATING_CONDITIONS.md` §1 の変更は依頼者確認を要し (`RM` §9 の 8)、機械検査でないので閉止条件の「依存方向」を保てない。
- **外部 linter (ruff / pyflakes の F401) の導入** — repo に linter は無く、導入は本 WP の範囲を超える。加えて F401 は**理由付きの許可表**を持てないので、facade 再 export (`MRA` §10.19 の (4)) を「記録された例外」として扱えない。

## 5. レビューと監査

- **設計レビューは行わない** (§5.46 の (5) は独立設計レビュー反映済みで、判断は §2 の監督裁定で閉じた)。
- コードレビュー 1 回 (別に起動した reviewer)。受け入れ監査 1 回。受け入れは監督がゲートの集計行と §3.6 の対応表を照合して行う (Class B)。

## 6. 実施記録 (統合時に監督が埋める)

### 6.1 訂正註と監督裁定 (§1〜§5 の本文は書き換えない)

- **【訂正註 1 (2026-09-22)】§3.2 の監督実測の件数を訂正する。** 実装担当の着手手順 2 の再照合 (D-2 の規則をそのまま実装したスクリプト、`grep -c -w` による出現数の裏付け) で、`from __future__ import annotations` を除く読み手 0 の import は r2db **32 件** (`postgres.py` 4、`structured.py` 27 + `Decimal` 1) 、MitateDB **9 件** (`backend_postgres.py` 4、`cell.py` 3、`control_http.py` 1、`main.py` 1) であった。§3.2 の「39 件」「8 件」は監督の集計の誤り (facade 保存テストが確認する名前の総数と読み手 0 の import を混同)。**現物が正本**であり、実装担当は実測の集合で進める。`main.py:598` の `build_control_service` は import 元 (`control_composition.py`) の `__all__` に在るが D-2 (b) は import した module 自身の `__all__` を指すので読み手 0 のままで正しい — 許可表に「記録なし (R-77 起草時の現状)」で置く。

- **【監督裁定 1 (2026-09-22)】許可表 41 行の採否。** 全行を採用する。理由欄の根拠は次のとおり: `MRA` §10.19 (4) の記録 (r2db `postgres.py` 3 件、MitateDB `backend_postgres.py` 4 件)、facade identity test の `file:line` (r2db `structured.py` 27 件 → `r2db-api/tests/test_foundation.py` の `test_<leaf>_leaf_preserves_structured_facade*`、`ConstraintPatch` → 同 `:3265`、MitateDB `cell.py` 3 件 → 各テスト)、`main.py:598` `build_control_service` → `main.py:593` の再 export コメントと `MitateDB-api/tests/test_control_main.py:6` (意図的な facade 互換。理由欄を「記録なし」からこれに直す)。**記録なしのまま採用する 2 件**: `r2db_api.structured.Decimal` (repo 内に読み手 0)、`mitatedb_api.control_http._CredentialMissing` (同 module `:71` のコメントが「inline で扱う」と述べ、読み手 0)。この 2 件は R-77 では削らない (src の import 削除は §1.5 の 40a の準用 (Z5-14) で両 peer の suite を要し、本 WP の範囲外)。**残余として台帳に起票する** (R-94: 読み手 0 で記録も無い import 2 件を削るか記録するか)。

### 6.2 実施と受け入れ

- **差分**: 新規 `tools/tests/test_src_import_readers.py` 1 本 (node id 3: `test_src_modules_match_pinned_set`、`test_string_annotation_only_readers_match_pin`、`test_reader_zero_imports_match_allow_table`)。src は不変。台帳 v1.91 (R-94 起票)。`tools/change_class.py` (パス指定) → `class=B`。コード commit `239c944` (main `f4d4fd8`)。本節と台帳 R-77 行の追記は同日の記録 commit。
- **実測 (2026-09-22、ローカル main f2517ed の上)**: module 87 (pin 一覧は `test_src_import_cycles.py` と byte 同一)、import 名 1164、読み手 0 の import 41 (r2db 32 = `postgres.py` 4 + `structured.py` 27 + `Decimal`; MitateDB 9) = 許可表 41 行 (§6.1 裁定 1 の理由、`_NO_RECORD_KEYS` で「記録なし」2 件を pin し許可表側と等価)。文字列注釈だけが読む名前 3 件 (集合 pin)。入れ子の文字列注釈 (現物 16 箇所) を parse、`Literal[...]` の slice と `Annotated[...]` の第 2 要素以降は parse しない。
- **道具の出力行**: `pt: 3 passed`、`pt: 585 passed` (`tools/tests`、基準 582 + 3)。`mutate: 14 mutations, 14 as expected, restores verified 4/4 files (sha256 x2), grep counts unchanged` — M1〜M7 (§3.6 の 1〜7) + M8a/M8b/M8c/M8d (理由欄の検査と `no record` の pin) + M9 (green) / M9b (red) (複合注釈の入れ子)。
- **§3.6 の表への追記**: 完了条件 9「許可表の理由欄は検査可能な引用を持ち、『記録なし』は `_NO_RECORD_KEYS` の 2 キーだけで、pin と許可表は等価」→ M8a・M8b・M8c・M8d。完了条件 10「複合注釈 (`dict[str, "Foo"]`) の中の文字列も読み手」→ M9 (green) / M9b (red)。
- **コードレビュー 3 巡** (1 巡目 中 3・低 5 → 差し戻し 1: 理由欄の裁定反映、`:1665`→`:1661`、入れ子注釈の parse、`__all__` の AugAssign/AnnAssign、理由欄の検査、失敗行の `file:line`、Limits; 2 巡目 中 1・低 2 → 差し戻し 2: M5b の理由を well-formed に、`Literal`/`Annotated` の除外、`_NO_RECORD_KEYS`; 3 巡目 低 2 → 差し戻し 3: pin と許可表の等式、別名 import の限界)。F7 (pin 不一致メッセージの形) は姉妹テストとの複製を保つため据え置き。
- **受け入れ監査**: 完了条件 1〜8 全て充足、未充足 0 (独立再走査で pin と完全一致)。証拠不足だった完了ゲートと ff 後の `tools/tests` は下記と `585 passed` で充足。所見: 表への追記 (上記 9・10)、`rulings` の語 (:5、文書参照なので残す)、`cast("Foo", x)` は読み手にしない (偽陽性方向、現物 0 件、据え置き)。
- **完了ゲート** (監督単独、`tools/dev/gate.py -C .claude/worktrees/r77 --label r77`): `gate: 3844 passed, 2 subtests passed in 348.84s`、`judge=PASS`、実行クラスタの `pg_database`/`pg_roles` 差分 0。root collection の増分 0。
- **最終判定**: 受け入れ。台帳 R-77 は閉じる (v1.91)。R-94 を起票 (「記録なし」2 件の処置)。
