# 作業指示書 — R-76 両 peer の `src/` の循環 import を検査するテスト

## 0. 出所と基点

- **v1.0 (2026-09-22)。** 基点 main `aac5e76`。作業 worktree は `.claude/worktrees/r76` (基点と同一)。
- 台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-76**。設計の正本は作業指示書 `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46 の **(2) 循環 import の静的検査** (独立設計レビュー反映済み) と、そこが引く裁定 **Z5-1 (2)・Z5-8・Z5-12・Z5-20**。設計文書は `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §4 の WP-5 節・§5.1 の 1。
- 変更クラスは **Class B** (`tools/tests/` のみ。`src` は変異の一時編集を除いて触らない)。設計文書は起こさず、決定は本書 §2 に置く (§5.46 の (2) を写すだけで、新しい決定は無い)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. 問題設定と守るべき条件

**問題**: 両 peer の `src/` の循環 import を検査するテストが無い (R-37 閉止後の残余 (2))。設計 `MRA` §5.1 の 1 は全 WP に「循環 import がない静的照合」を求めたが、R-37 の閉止後にそれを保つ仕組みは無い。

**守るべき条件**: `MRA` §4 の WP-5 節の閉止条件 (「line count は成果指標ではなく、責務・依存方向・回帰証拠が閉止条件である」) のうち**依存方向**を、持続的に保つ。検査は両 peer の `src/` だけを見る (Z5-8)。`spec/`・`security/`・`conformance-tests/` に触れない。

## 2. 決定 (監督確定。§5.46 の (2) から)

- **D-1 (形)。** 両 peer の `src/` の import graph を AST で組み、**関数内 import と `TYPE_CHECKING` 下の import を含む全辺**で循環が 0 であることを assert する (Z5-12)。
- **D-2 (空振り禁止)。** 観測した module 数と edge 数が 1 以上であることも assert する (`OPERATING_CONDITIONS.md` §1.5 の 32)。
- **D-3 (走査の根)。** 走査の根は両 peer の `src/` に明示的に限る (Z5-8)。peer のディレクトリ全体を `rglob` しない。
- **D-4 (graph の作り方、Z5-20)。** `from . import X` は submodule X に解決する。**親 package の暗黙の import は辺に数えない** (両 peer の `__init__.py` は submodule を import するので、数えると現状の src で循環が出る — §5.46 起草時の実測)。関数内・`TYPE_CHECKING` 下の import も辺に数える。絶対 import (`from r2db_api.x import y`、`import mitatedb_api.x`) も自 package 内なら辺に数える。外部 package (`psycopg` 等) は辺にしない。
- **D-5 (将来の例外)。** **将来の意図的な例外 (循環を許す辺) は監督裁定を要する** (Z5-12)。テストの docstring にもその旨を書く。
- **D-6 (範囲)。** 新規ファイルは `tools/tests/test_src_import_cycles.py` **1 本のみ**。既存のテストを変えない。
- **D-7 (設計の範囲)。** §5.46 の (2) が独立設計レビューに掛けた論点 (設計 §4 の「import graph を確認する」の範囲に収まるか、§1.5 の 37 の設計外の拡張に当たらないか) について、**監督の見立ては次のとおり (§5.46 から逐語)**: 「**(2) の循環 import 検査が、設計 §4 の「import graph を確認する」の範囲に収まるか** (§1.5 の 37 の設計外の拡張に当たらないか)。監督の見立ては「範囲内」 — 一度きりの手作業の確認は変異を対応付けられず (§1.5 の 33)、閉止条件の「依存方向」を持続的に保てるのはテストの形だけであるため。」 §5.46 は「独立設計レビュー反映済み」であり、第 3 次裁定 Z5-15〜Z5-21 にこの論点の差し戻しは無い (**設計レビューでの差し戻し無し**)。

## 3. WP-1 Change Set Manifest — `tools/tests/test_src_import_cycles.py` の新設

### 3.1 触ってよい・触らないパス

| 触ってよい | 触らない |
|---|---|
| `tools/tests/test_src_import_cycles.py` (新規。本 WP の変更セットはこの 1 ファイルだけ) | `spec/`、`security/`、`conformance-tests/`、`tools/tests/test_leaf_import_direction.py`、`tools/tests/test_sql_statement_safety_scan.py` (R-75)、両 peer の `src/` と `tests/` (**変異の一時編集を除く**)、`docs/`、台帳 (記録は監督) |

- **変異の一時編集**は §3.6 の表の `file` 欄のとおり。`mutate.py` が原状復帰と sha256 照合を行う。
- **並行 WP との重なり (`OPERATING_CONDITIONS.md` §1.2 の 16・17)**: R-75 が `.claude/worktrees/r75` で `tools/tests/test_sql_statement_safety_scan.py` を新設している。本 WP の作業ツリーは `.claude/worktrees/r76`、変更セットは `tools/tests/test_src_import_cycles.py` の 1 ファイルで、**重なりは 0**。変異の一時編集は各 worktree の中で閉じ、復元される。
- root collection の増分は **0** (`tools/tests` は root の `testpaths` の外で、`gate.py` では 1 本も走らない)。`tools/tests` の増分は実装担当が実際に足した node id の数であり、報告に書く。

### 3.2 監督実測 (2026-09-22、ローカル main `aac5e76`)

1. `r2db-api/src/r2db_api/ops.py`:36-37 に `from . import platform_declarations` / `from . import platform_upgrades` が在る (完了条件 4 の変異の前提)。
2. `r2db-api/src/r2db_api/postgres_sql.py`・`MitateDB-api/src/mitatedb_api/postgres_sql.py` は在る。
3. 両 peer の `src/` で `TYPE_CHECKING` の出現は計 3 件 (grep)、`MitateDB-api/src/mitatedb_api/postgres_sql.py` には無い。したがって**完了条件 3 の MitateDB 側の変異は、`from typing import TYPE_CHECKING` と `if TYPE_CHECKING:` ブロックごと足す形**にし、**変異 1 entry の `new` の中で完結させる**。
4. `src/` の `.py` は両 peer 合わせて **87**。

### 3.3 着手手順

1. 作業 worktree `.claude/worktrees/r76` が基点 `aac5e76` と同一であることを確かめる。
2. §3.2 の 1〜4 を自分で再照合する (食い違いが 1 件でもあれば、そこで止まって監督へ上げる)。
3. `tools/tests/test_leaf_import_direction.py` の書き方 (`REPO_ROOT = Path(__file__).resolve().parents[2]`、`SRC_ROOTS`、import 名の正規化、**1 テストで全 module を走査して node id を増やさない**形) に倣って実装する。
4. `pt.py` で新規ファイル単体 → `tools/tests` 全体の順に緑を確かめる。
5. `mutate.py` を §3.6 の 8 件で回す。**1 変異 = 1 entry** (`mutate.py` は最初の不一致で止まる)。
6. §3.7 を報告に貼る。suite 全体・`conformance-tests`・`gate.py` は回さない。

### 3.4 実装の形

- module の集合: `SRC_ROOTS` (`r2db-api/src/r2db_api`、`MitateDB-api/src/mitatedb_api`) の再帰の `.py` を列挙し、package 相対のドット名 (`__init__.py` は package 名) を node とする。**列挙方法 (`rglob` / `glob` 系か `git ls-files` 系か) は実装した該当行を `file:line` で報告に書く** (§5.46 の訂正註 8-7 の形)。
- 辺: 各 module の AST を `ast.walk` で走査し、`ast.Import` / `ast.ImportFrom` を**位置を問わず**拾う (module 直下・関数内・`if TYPE_CHECKING:` 下を区別しない。D-1)。
- 解決 (D-4): 相対 import は `level` と `module` で自 package 内の module に解決し、**実在する module に解決したものだけ**を辺にする。`from . import X` (module 無し) は alias ごとに submodule X として解決する。属性など module に解決しない名前は辺にしない。絶対 import は自 package を頭に持つものだけを同じ規則で解決する。**親 package (`__init__`) への暗黙の辺は作らない。**
- 循環: 有向 graph の強連結成分または DFS で循環を検出し、**循環が 1 つでもあれば、循環の経路を module 名で全件並べて失敗**する。
- pin と空振り禁止 (D-2・D-3): module 数と edge 数が 1 以上であること、走査の根が両 peer の `src/` であることを assert する。
- docstring に D-5 (将来の意図的な例外は監督裁定を要する) を書く。経緯トークン (`WP-`、日付、`review`、`supervisor ruling`) は入れない。

### 3.5 道具の引数

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r76 -- tools/tests/test_src_import_cycles.py -q
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r76 -- tools/tests -q
tools/dev/mutate.py "$SP/r76-mutations.json" -C .claude/worktrees/r76 --wait 1800
tools/dev/gate.py -C .claude/worktrees/r76 --label r76        # 監督のみ
```

spec の形の例 (完了条件 3 の MitateDB 側。§3.2 の 3 のとおり `new` の中で `TYPE_CHECKING` の import ごと足す。`old` は着手時に対象ファイルで 1 件一致する行を選ぶ):

```json
{"pytest": ["-q", "tools/tests/test_src_import_cycles.py"],
 "mutations": [
  {"id": "M3b", "expect": "red",
   "file": "MitateDB-api/src/mitatedb_api/postgres_sql.py",
   "old": "from psycopg import sql",
   "new": "from typing import TYPE_CHECKING\n\nfrom psycopg import sql\n\nif TYPE_CHECKING:\n    from .backend_postgres import _execute\n",
   "tests": ["tools/tests/test_src_import_cycles.py"]}]}
```

- python は main checkout の `.venv/bin/python`。Bash timeout は 600000。終了コードは pipe の外で取る。

### 3.6 完了条件 → 変異 → 赤になる test id

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) | 実施 |
|---|---|---|---|---|
| 1 | r2db の `src/` に循環 import が無い (module 先頭の import) | `r2db-api/src/r2db_api/postgres_sql.py`: 先頭に `from .postgres import _run` を 1 行足す | `tools/tests/test_src_import_cycles.py` の循環 0 の assert (新規) | 実装担当 |
| 2 | MitateDB の `src/` に循環 import が無い (module 先頭の import) | `MitateDB-api/src/mitatedb_api/postgres_sql.py`: 先頭に `from .backend_postgres import _execute` を 1 行足す | 13 と同じ | 実装担当 |
| 3 | 関数内 import と `TYPE_CHECKING` 下の import も辺に数える (Z5-12) | 2 件。`r2db-api/src/r2db_api/postgres_sql.py`: 既存の関数の本体の先頭に `from .postgres import _run` を足す。`MitateDB-api/src/mitatedb_api/postgres_sql.py`: `if TYPE_CHECKING:` の下に `from .backend_postgres import _execute` を足す (`TYPE_CHECKING` の import を含む) | 13 と同じ | 実装担当 |
| 4 | `from . import X` は submodule X に解決し、親 package の暗黙の import は辺に数えない (Z5-20) | 2 件。`r2db-api/src/r2db_api/platform_upgrades.py`: `from . import ops` を 1 行足す (`ops.py` は `from . import platform_upgrades` を持つ) → 赤。`tools/tests/test_src_import_cycles.py`: 各 module から親 package (`__init__`) への辺を足す形に変える → 現状の src で赤 | 13 と同じ | 実装担当 |
| 5 | 走査対象は両 peer の `src/` に限り、module 数・edge 数を 1 以上観測する (Z5-8、空振り禁止) | 2 件。`tools/tests/test_src_import_cycles.py`: 列挙から 1 module を外す。MitateDB の根を `MitateDB-api` に広げる | `tools/tests/test_src_import_cycles.py` の集合または件数の pin (新規) | 実装担当 |
| 6 | 上の表に、変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜22 の各行に「変異」または「監査照合」が入っていることを照合し、結果を報告に貼る | — | 実装担当 |

**番号の振り直しの対応註**: 上の 6 行は `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46 の完了条件表からの**逐語**で、`#` 欄だけを振り直した — 同表の **13〜17 が本書の 1〜5**、**23 が本書の 6** である。したがって行の本文に残る同表の番号は次のように読む: 2〜4 の「13 と同じ」は**本書の 1 と同じ**、6 の「1〜22 の各行」は**本書の 1〜5 の各行**。「(2)」の枠欄 (§5.46 の (2) 循環 import の静的検査) は全行に掛かるので列ごと落とした。

**件数 (下限)**: 完了条件 6 件 = 変異を持つ行 5 件 (1〜5。変異は **8 件** — 3・4・5 は各 2 件) + 監査照合 1 件 (6)。§5.45 の訂正註 6 のとおり、実装担当は変異が素通りする場面を見つけたら足す。

### 3.7 報告に貼るもの

1. §3.2 の 1〜4 の再照合の結果 (食い違いの有無)。
2. module の列挙方法の該当行 (`file:line`) と、観測した **module 数・edge 数**の実測値。
3. `pt.py` の 2 本の集計行 (新規ファイル単体、`tools/tests` 全体) と、`tools/tests` の node id の増分。
4. `mutate.py` の全 8 件の `expect=` / `got=` の行と、復元の sha256 照合の結果。
5. 完了条件 6 の監査照合の結果 (1〜5 の各行に変異が在ること)。
6. docstring に書いた D-5 の一文。

## 4. 却下した代替案

- **一度きりの手作業の import graph 確認** — 変異を対応付けられない (`OPERATING_CONDITIONS.md` §1.5 の 33)。閉止条件の「依存方向」を持続的に保てない。
- **親 package の暗黙の import を辺に数える形** — 両 peer の `__init__.py` は submodule を import するので、数えると現状の src で循環が出る (D-4、Z5-20)。
- **peer ディレクトリ全体の `rglob`** — `MitateDB-api/docs/f9-execution-assets-v1/` のレビューされていない参照用 `.py` 3 件が判定に混ざる (Z5-8)。

## 5. レビューと監査

- **設計レビューは行わない** (§5.46 は独立設計レビュー反映済みで、(2) に差し戻しは無い。D-7)。
- コードレビュー 1 回 (別に起動した reviewer)。受け入れ監査 1 回。受け入れは監督がゲートの集計行と §3.6 の対応表を照合して行う (Class B)。

## 6. 実施記録 (統合時に監督が埋める)

### 6.1 訂正註と監督裁定 (§1〜§5 の本文は書き換えない)

- **【監督裁定 2026-09-22 (起草時の指摘 1・2)】走査集合の pin の形**: 発見した module の集合を peer ごとの **dotted name の逐語の一覧** (例 `mitatedb_api.backend_postgres`) として pin し、`set(発見) == set(pin)` を assert する (件数だけの pin にしない)。これにより完了条件 5 の 2 件 (列挙から 1 module を外す / MitateDB の根を `MitateDB-api` に広げる) は集合の不一致で赤になる。新 module を足す変更はこの一覧を同じ変更セットで更新する (`OPERATING_CONDITIONS.md` §1.5 の 40b と同じ扱い)。

### 6.2 実施と受け入れ

- **差分**: 新規 `tools/tests/test_src_import_cycles.py` 1 本 (node id 2: `test_src_modules_match_pinned_set`、`test_src_import_graph_has_no_cycles`)。src・spec・security・conformance-tests は不変。`tools/change_class.py` (パス指定) → `class=B`。
- **実測 (2026-09-22、ローカル main aac5e76 の上)**: module 87 (r2db 41 / mitatedb 46、`rglob("*.py")` で列挙)、辺 238 (r2db 104 / mitatedb 134)、非自明 SCC 0。`__init__` を終点とする辺 0。絶対 intra-peer import は現状 0 件 (該当分岐は変異でのみ観測)。
- **道具の出力行**: `pt: 2 passed` (単体)、`pt: 577 passed` (`tools/tests`、基準 575 + 2)。`mutate: 11 mutations, 11 as expected, restores verified 5/5 files (sha256 x2), grep counts unchanged` — M1 r2db 先頭 import / M2 MitateDB 先頭 import / M3a r2db 関数内 / M3b MitateDB `TYPE_CHECKING` (ブロックごと追加) / M4a `from . import ops` の submodule 解決 / M4b 親 package 辺を数える形 / M5a 一覧から 1 module 除外 / M5b MitateDB の根を `MitateDB-api` に拡大 (失敗文に `docs/f9-execution-assets-v1` の 3 件が現れる) / M6a `import r2db_api.postgres` / M6b `from r2db_api import postgres` (修正前は緑を実測) / M6c `from r2db_api import DataService` (非 module 属性 → package への辺、SCC `{r2db_api, r2db_api.service}`)。全て red。
- **コードレビュー 1** (中 3・低 5): 絶対 `from <pkg> import <submodule>` が package への辺に解決され循環を見逃す (偽陰性) / 絶対 import の分岐に観測 0・変異 0 / `_find_cycles` が back edge 単位で全循環を出さない / 経緯トークン / peer 別辺下限なし / pin 更新規則の未明記。**監督裁定**: submodule 解決を足し M6a・M6b を追加、Tarjan の SCC 列挙に置換 (SCC ごとに module と内部辺を全件)、冒頭の出所行 `R-76:` と文書パスの参照は許し `WP-1`・`supervisor ruling` は削除、peer 別辺下限、pin 直前に更新規則の 1 文。再確認で全件閉、新規は低 1 (docstring の fallback の説明) → 反映。
- **受け入れ監査**: 完了条件 1〜6 全て充足、未充足 0。証拠不足は完了ゲート (未実施時点) と `mutate.py` の stdout 集計行の正本の無さ (per-mutation ログ 10 件と backups の sha256 一致で代替)。所見: D-5 の「監督裁定を要する」の語が docstring に無い → 1 文追加、`from <pkg> import <非 module 属性>` の分岐が観測 0 → M6c 追加。
- **完了ゲート** (監督単独、`tools/dev/gate.py -C .claude/worktrees/r76 --label r76`): `gate: 3844 passed, 2 subtests passed in 328.39s`、`judge=PASS`、実行クラスタの `pg_database`/`pg_roles` 差分 0。root collection の増分 0 (直前の main と同数)。ゲートは M6c・docstring 追記の前に走ったが、その後の変更は `tools/tests` (root の `testpaths` 外) のみで、`finalize.py --tools-tests` が新 HEAD で `tools/tests` を回す。
- **最終判定**: 受け入れ。台帳 R-76 は閉じる (v1.89)。R-76 行の「独立設計レビューの論点は未決」は、§5.46 が反映済みで差し戻しが無かったことを D-7 に記して更新した。
