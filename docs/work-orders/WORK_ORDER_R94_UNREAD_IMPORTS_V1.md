# 作業指示書 — R-94 読み手 0 で記録の無い import 2 件の削除

## 0. 出所と基点

- **v1.0 (2026-09-22)。** 基点はローカル main `adea2b5` (作業ツリー `.claude/worktrees/r94`)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-94 (R-77 の許可表で「記録なし」のまま採用した 2 件)。
- **変更クラスは Class B** (両 peer の `src/` の import 行 2 件と `tools/tests/test_src_import_readers.py`)。実装担当が `tools/change_class.py` (パス指定) で確かめる。
- 規律: `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 32〜40。**src の import 削除には §1.5 の 40a を準用する** (R-37 WP-5 の Z5-14): 削除の前後で両 peer の suite の集計行を記録する。commit は監督のみ。

## 1. 問題設定と決定 (監督確定)

R-77 の読み手検査は、読み手 0 で設計の記録 (`docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10.19 (4)) にも facade identity test にも当たらない import を 2 件、「記録なし」として許可表に置いた:

- `r2db-api/src/r2db_api/structured.py:10` の `from decimal import Decimal` — repo 内に読み手 0 (監督実測 2026-09-22: `structured.py` 内の出現は import 行のみ、tests・設計文書に `structured` 経由の参照無し)。
- `MitateDB-api/src/mitatedb_api/control_http.py:50` の `_CredentialMissing` (`from .http import (…)` の 1 名) — 同 module 内の出現は import 行と `:71` のコメント (「`http.py` の `_CredentialMissing` は inline で map される」という説明。名前は `http.py` の class を指しており、この module が使うとは述べていない) だけ。tests は `http._CredentialMissing` を直接引く (`MitateDB-api/tests/test_application_audit.py:2670` のコメント) が `control_http` 経由ではない。

**D-1**: 2 件とも import から名前を削る (`_CredentialMissing` は `from .http import (…)` の 1 名だけ外す。`Decimal` は行ごと削る)。コメント・docstring は変えない (`:71` のコメントは `http.py` の class についての記述なので真のまま)。
**D-2**: `tools/tests/test_src_import_readers.py` の許可表から当該 2 行を外し、`_NO_RECORD_KEYS` を空の `frozenset()` にする (機構は残す: 将来の「記録なし」行は pin への同時追加を要する)。docstring の「2 件」の記述を実装どおりに直す。変異 M8c (3 件目の `no record` 行) / M8d (pin に 3 件目) は「1 件目」になるが形は同じ。
**D-3**: 削除の前後で両 peer の suite と `tools/tests` を `tools/dev/pt.py` で回し、集計行 (前後 × 2 peer + tools/tests) を報告に貼る (40a の準用)。

## 2. WP-1 Change Set Manifest

| 触ってよいファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py` (`:10` の 1 行)、`MitateDB-api/src/mitatedb_api/control_http.py` (`:50` の 1 名)、`tools/tests/test_src_import_readers.py` | それ以外の全部 (`spec/`・`security/`・`conformance-tests/`・両 peer の tests・`docs/`・台帳 (記録は監督)) |

着手手順: (1) `tools/change_class.py` → B を貼る。(2) 2 件の読み手 0 を現物で再照合 (`grep -n -w` を両 peer の `src/`・`tests/`・`conformance-tests/`・`tools/`・`docs/` で。1 件でも読み手が見つかれば止めて監督へ)。(3) 削除**前**の集計行: `tools/dev/pt.py --wait 1800 -C .claude/worktrees/r94 -- r2db-api/tests -q`、`… -- MitateDB-api/tests -q`、`… -- tools/tests -q`。(4) 削除と許可表の更新。(5) 削除**後**の同じ 3 本。(6) 変異。(7) `tools/check_comment_provenance.py --register` と `--base adea2b5 <両ファイル>` (§4.1 (1) はコード変更で赤 = 受理、(5) 経緯トークンが 0 件であることを貼る)、`check_doc_refs.py`、`public_value_scan.py`。

| # | 完了条件 | 変異 | 赤になる test id |
|---|---|---|---|
| 1 | 2 件の import が無く、読み手検査が緑 | `r2db-api/src/r2db_api/structured.py` に `from decimal import Decimal` を戻す → 赤 | `tools/tests/test_src_import_readers.py::test_reader_zero_imports_match_allow_table` |
| 2 | `_NO_RECORD_KEYS` は空で、許可表の `no record` 行 0 と等価 | 既存の M8c (許可行 1 件を `no record …` にする) → 赤; M8d (pin に 1 件足す) → 赤 | 同上 |
| 3 | 削除前後で両 peer の suite と `tools/tests` の集計行が同数 (削除 0) | 監査照合: 3 本 × 前後の集計行 | — |
| 4 | 許可表 39 行の集合 pin は保たれる | 既存の M5a (1 行外す) → 赤 | 同上 |
| 5 | 上の表に変異も監査照合も無い行が無い | 監査照合 | — |

道具: `tools/dev/mutate.py "$SP/r94-mutations.json" -C .claude/worktrees/r94 --wait 1800` (1 変異 1 entry、`tests` に node id)。`tools/dev/gate.py -C .claude/worktrees/r94 --label r94` (監督のみ。root は 3844 が期待値)。

## 3. レビューと監査

設計レビュー無し。コードレビュー 1 (短)。受け入れは監督が対応表と集計行で判定する。

## 4. 実施記録 (監督が書く)

### 4.1 訂正註と監督裁定

- **【訂正註 1 (2026-09-22)】** コードレビュー 1 の指摘で、完了条件 1 の変異を両 peer に置いた (M5: MitateDB 側の `_CredentialMissing` を戻す → 赤)。`control_http.py` の import ブロックは 1 名を外した後に整形した (名前の集合は不変)。レビューが見つけた範囲外の陳腐化 (`conformance-tests/test_c20_constraint_declaration_agreement.py:154`・`test_c22_dry_run_and_plan.py:186` の docstring が `r2db-api/src/r2db_api/structured.py:1583` を `self.schema_revision += 1` として引くが現物は `:1821`) は本 WP では直さず、台帳 R-95 として起票した。

### 4.2 実施と受け入れ

- **差分**: `r2db-api/src/r2db_api/structured.py` (`from decimal import Decimal` 削除)、`MitateDB-api/src/mitatedb_api/control_http.py` (`from .http import (…)` から `_CredentialMissing` を外し整形)、`tools/tests/test_src_import_readers.py` (許可表 41 → 39 行、`_NO_RECORD_KEYS = frozenset()`、コメント)。`tools/change_class.py` → `class=B`。
- **40a の準用 (削除前 → 後)**: r2db-api/tests `1373 passed` → `1373 passed`、MitateDB-api/tests `1422 passed, 2 subtests passed` → 同、tools/tests `585 passed` → 同 (整形後も MitateDB 1422 / tools 585)。読み手 0 の再照合: 2 名とも repo 全域で import 行 (と `control_http.py:71` のコメント) 以外に出現 0。
- **変異**: `mutate: 5 mutations, 5 as expected, restores verified 3/3 files (sha256 x2), grep counts unchanged` (M1 `Decimal` を戻す / M2 `no record` 行を足す / M3 pin に 1 件足す / M4 許可行 1 件外す / M5 `_CredentialMissing` を戻す)。`check_comment_provenance.py --base adea2b5` は両 src で §4.1 (1) 赤 (import 行のコード変更 = 受理)、(5) 経緯トークン 0。`--register` OK 87/430。`check_doc_refs` 0、`public_value_scan` 0。
- **コードレビュー 1** (中 2・低 1、範囲外 1): 許可表ヘッダの取り残し、変異の片側性、import 整形 → 全件反映。
- **完了ゲート** (監督単独、整形後の最終の木、`--label r94b`): `3844 passed, 2 subtests passed in 344.90s (0:05:44)`、`judge=PASS`、実行クラスタ差分 0 (整形前の木でも `3844 passed`、PASS)。root collection の増分 0。
- **最終判定**: 受け入れ。台帳 R-94 を閉じ、R-95 を起票 (v1.93)。
