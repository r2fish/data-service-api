# 変更セット 9 — 行番号 pin (pins.md)

基点 `092e1a1`。両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` の `(module, lineno)` pin を ast で読んだ (`_BACKEND_LAYER_ALLOWLIST` は `frozenset({...})` の Call node なので中の set を `ast.literal_eval` した)。

| peer / 表 | 行 | 要素 | module の集合 | 本変更セットの module の pin |
|---|---|---|---|---|
| r2db `_BACKEND_LAYER_ALLOWLIST` | L140-299 | 1 (`("postgres.py", 1948)`) | `{postgres.py}` | **0** (`test_backend_layer_allowlist_is_confined_to_postgres_py` L702 が全要素を `postgres.py` に固定する) |
| r2db `SCANNED_MODULES` | L107 | 16 の module 名 | 名前だけ | `structured.py` は在るが行番号を持たない |
| r2db 件数 pin | L574 | `"structured.py": 48` ほか | — | `_fail_call_sites` (ast) の数でコメントに依らない (`test_ast_full_count_matches_the_audit_site_count`) |
| MitateDB `_BACKEND_LAYER_ALLOWLIST` | L306-376 | 17 | `{backend_postgres.py}` | **0** |
| MitateDB `_CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST` | L399 | 0 (空) | — | **0** |

- `("structured.py", N)` / `("platform_declarations.py", N)` の grep: 両ファイルで 0 件 (checks.md の実行 1 末尾、exit 1)。
- したがって「基点の行 → 新しい行」の一覧は該当する module が無い。完了条件 9 は両 module とも非該当で、監査照合 (HEAD で pin 0 件と件数 pin 48 の不変を確認) にする。
- 依頼の予想 (「r2db の structured.py は載っている可能性が高い」) と違う結果なので、作業機で `python3 -c "import ast; ..."` か上の test 名で取り直すこと。
- 参考: 位置参照 (pin ではない) で `structured.py:N` を basename だけで持つテスト・conformance の行は measure.md §3 (r2db `tests/test_foundation.py` 3、両 peer の L1 scan 各 1、r2db `conformance/conformance_adapter_r2db.py` 3 行)。触らない対象。
