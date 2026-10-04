# (D) DB を使わない照合 — 変更セット 8 の下準備 (基点 `092e1a1`)

実行環境: クラウドの checkout (`$SP` = scratchpad)。PostgreSQL を使うテスト、`tools/dev/gate.py`、`tools/dev/mutate.py`、`tools/dev/finalize.py`、pytest は実行していない (pytest は環境に無い)。spec を作業ツリーに当てて下の道具を流し、終わった後に module・受け皿・`security/CONTROL_MAPPING.md` を基点の内容に戻した (`git status` で差分 0 を確かめた)。

## 0. 基点と無変更の照合 (spec を当てる前)

```text
$ git rev-parse --short origin/main
092e1a1
$ git rev-parse origin/main:r2db-api/src/r2db_api/platform_declarations.py origin/main:MitateDB-api/src/mitatedb_api/control_plane.py
590c904f9350eb4e339b7014cf6ab77138fbbff2
89401773874499038c02d7ff292cbbde308950c6
$ git log --oneline 092e1a1..origin/main
(0 commit)
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/platform_declarations.py
comment provenance OK: 67 blocks checked
(exit 0)
$ python3 tools/check_comment_provenance.py --base 092e1a1 MitateDB-api/src/mitatedb_api/control_plane.py
comment provenance OK: 85 blocks checked
(exit 0)
$ python3 tools/check_comment_provenance.py --register
comment provenance register OK: 95 files scanned, 515 CH-IDs
(exit 0)
$ python3 tools/check_doc_refs.py | tail -1
check_doc_refs OK: 0 dangling references
(exit 0)
```

## 1. `cs8_apply.py` (dry-run → 当てる)

```text
$ python3 "$SP/cs8_apply.py" -C . --spec "$SP/cs8-spec-platform_declarations.json" --dry-run
CH-0866 comment base L1093-1101 check_role_connection_limits edits=1
CH-0865 docstring base L1037-1089 check_role_connection_limits edits=3
CH-0864 comment base L909-952 <module> edits=1
CH-0863 docstring base L685-692 _role_setting_rows edits=1
CH-0862 comment base L420-432 <module> edits=1
CH-0861 comment base L75-77 <module> edits=1
CH-0860 docstring base L1-60 <module> edits=3
blocks=7 module_lines 1737 -> 1748
(exit 0)
$ python3 "$SP/cs8_apply.py" -C . --spec "$SP/cs8-spec-control_plane.json" --dry-run
CH-0944 comment base L2195-2204 reset_control_credentials edits=1
CH-0943 comment base L1967-1979 ControlPlaneService.revoke_credential edits=1
CH-0942 comment base L1832-1838 ControlPlaneService.issue_credential edits=1
CH-0941 comment base L1578-1582 ControlPlaneService.control_capabilities edits=1
CH-0940 comment base L1523-1529 ControlPlaneService._validate_application_id edits=1
CH-0939 docstring base L1464-1482 ControlPlaneService._gate_must_rotate edits=1
CH-0938 docstring base L1391-1400 ControlPlaneService._authenticate edits=1
CH-0937 docstring base L1301-1305 ControlPlaneService.limits edits=1
CH-0936 comment base L1288-1296 ControlPlaneService.__init__ edits=1
CH-0935 comment base L1247-1253 ControlPlaneService.__init__ edits=1
CH-0934 docstring base L1158-1161 PostgresControlBackend.authenticate_application edits=1
CH-0933 comment base L1051-1063 PostgresControlBackend edits=1
CH-0932 docstring base L1024-1035 InMemoryControlBackend.authenticate_application edits=1
CH-0931 comment base L984-986 InMemoryControlBackend.credentials_active_count_locked edits=1
CH-0930 comment base L950-958 InMemoryControlBackend.applications_count_locked edits=1
CH-0929 docstring base L868-882 PostgresCredentialRegistry.authenticate edits=1
CH-0928 docstring base L346-369 InMemoryCredentialRegistry.authenticate edits=1
CH-0927 docstring base L128-148 ControlPlaneLimits edits=1
CH-0926 comment base L96-99 <module> edits=1
CH-0925 docstring base L1-37 <module> edits=1
blocks=20 module_lines 2274 -> 2309
(exit 0)
```

(上は最終の spec。最初の spec は r2db 7 塊 11 編集 + 第 1 段落の日付 1 編集、MitateDB 27 塊 27 編集で、次の §2 の赤を受けて縮めた。)

## 2. `check_comment_provenance.py --base 092e1a1 <module>`

最初の spec (r2db 12 編集、MitateDB 27 塊) を当てた作業ツリー:

```text
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/platform_declarations.py
FAIL (§4.1 (3)) r2db-api/src/r2db_api/platform_declarations.py:1 cannot delete a whole sentence carrying a protected reference: 'Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, work order docs/work-orders/WORK_ORDER_Q4_DB_SIDE_SINGLE_TRUTH_V1.md WP-1; rework round, supervisor rulings 2026-09-05 -- rulings-q4-wp12-rework.md sec.1, rulings-q4-writer-roles.md D-2(h), q4-f3c-and-amendments.md; Agent C isomorphism convergence pass, rulings-q4-wp12-rework.md sec.5):'
(exit 1)
$ python3 tools/check_comment_provenance.py --base 092e1a1 MitateDB-api/src/mitatedb_api/control_plane.py
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/control_plane.py:243 retained text has no order-preserving match in the original block for: "follows the SAME `work.on_rollback(...)` undo-log convention `set_enabled` above uses -- this is what structurally closes the in-memory-backend freeze-snapshot gap r2db-api's own WP-4 review (n-2) found in ITS in-memory backend (a snapshot/rollback mechanism that had to be told about every new piece of mutable state by hand): here, `_InMemoryWork` is a shared undo-log any store participates in simply by registering its own undo the same way every other write method in this module already does, so there is no separate snapshot list that could forget this one -- proactively unaffected by that lesson rather than needing a fix for it."
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/control_plane.py:617 retained text has no order-preserving match in the original block for: "`ControlPlaneService.issue_credential`'s own read of this flag, evaluated only after the `role=control` capability refusal and the target-existence check (contract `issue_credential.semantics`'s own precedence sentence)."
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/control_plane.py:643 retained text has no order-preserving match in the original block for: 'CLI-only, non-destructive (mirrors `set_enabled` above -- no declare-and-echo confirmation gate, same class as disable-application).'
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/control_plane.py:1117 retained text has no order-preserving match in the original block for: "forwards to `PostgresApplicationRegistry.count_locked` -- see that method's own docstring for the full rationale (table-scoped constant-key `pg_advisory_xact_lock`, closes the phantom-write window an unlocked `applications_count() >= limit` pre-check cannot)."
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/control_plane.py:1671 retained text has no order-preserving match in the original block for: 'the real, authenticated principal\'s own role -- never a hardcoded `"control"` literal (a `role="audit"` principal reaches this same method).'
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/control_plane.py:1849 retained text has no order-preserving match in the original block for: 'per-application issuance freeze -- an out-of-band (CLI-only) deployer operation.'
FAIL (§4.1 (3)) MitateDB-api/src/mitatedb_api/control_plane.py:1862 retained text has no order-preserving match in the original block for: "the capacity check now runs INSIDE the SAME transaction that performs the write, via `credentials_active_count_locked` -- see `register_application`'s own identical-shaped comment above for the phantom-write window this closes (here: `credentials_active_count() >= limit`)."
(exit 1)
```

拒まれた除去 (spec から外し、塊は基準のまま): r2db L1-60 の第 1 段落の日付 `2026-09-05` (1 編集)、MitateDB の文頭ラベル 7 塊 (基点 L238、L606、L629、L1091、L1627、L1804、L1816。どれも `Phase 3.5 WP-5 (§4/§1-E, …)` / `Phase 10 WP-6b (design D-5 (ii)/(iii))` / `Phase 3.5 WP-5 (design §4, review m-6)` の形)。各塊の判定は `judgement-*.md` の「検査器が拒んだ除去」。

最終の spec を当てた作業ツリー:

```text
$ python3 tools/check_comment_provenance.py --base 092e1a1 r2db-api/src/r2db_api/platform_declarations.py
comment provenance OK: 67 blocks checked
(exit 0)
$ python3 tools/check_comment_provenance.py --base 092e1a1 MitateDB-api/src/mitatedb_api/control_plane.py
comment provenance OK: 85 blocks checked
(exit 0)
```

## 3. `--register`、`check_doc_refs.py`、`public_value_scan.py` (最終の spec を当てた作業ツリー)

```text
$ python3 tools/check_comment_provenance.py --register
comment provenance register OK: 95 files scanned, 542 CH-IDs
(exit 0)
$ python3 tools/check_doc_refs.py | tail -1
check_doc_refs OK: 0 dangling references
(exit 0)
$ python3 tools/public_value_scan.py r2db-api/src/r2db_api/platform_declarations.py MitateDB-api/src/mitatedb_api/control_plane.py docs/code-history/r2db-api/platform_declarations.md docs/code-history/MitateDB-api/control_plane.md | tail -1
# R7 (personal names): NOT CHECKED -- not expressible as a regex; human review only. A clean run above does not mean no personal name is present.
(exit 0。`total_flagged` の行は tail に出なかったが exit 0)
```

登録 515 → 542 (= +27: r2db 7 + MitateDB 20)。

## 4. `cs8_removed_tokens.py -C .` (最終の spec。コミット前 = `--head` 省略)

```text
BASE 092e1a1 HEAD worktree
REMOVED	r2db-api/src/r2db_api/platform_declarations.py	L1-60	CH-0860	id	WP-6a	x1
REMOVED	r2db-api/src/r2db_api/platform_declarations.py	L420-432	CH-0862	id	WP-6a	x1
REMOVED	r2db-api/src/r2db_api/platform_declarations.py	L909-952	CH-0864	id	WP-4f	x1
REMOVED	r2db-api/src/r2db_api/platform_declarations.py	L1037-1089	CH-0865	id	D-3	x1
REMOVED	r2db-api/src/r2db_api/platform_declarations.py	L1037-1089	CH-0865	id	WP-8a	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1-37	CH-0925	id	WP-4	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L96-99	CH-0926	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L96-99	CH-0926	id	WP-3	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L128-148	CH-0927	id	M-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L128-148	CH-0927	id	WP-0	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L128-148	CH-0927	id	WP-4	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L950-958	CH-0930	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L950-958	CH-0930	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L984-986	CH-0931	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1024-1035	CH-0932	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1024-1035	CH-0932	id	WP-3	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1051-1063	CH-0933	id	D-6	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1051-1063	CH-0933	id	N-3	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1158-1161	CH-0934	id	WP-3	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1247-1253	CH-0935	id	D-2	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1247-1253	CH-0935	id	WP-3	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1288-1296	CH-0936	id	D-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1288-1296	CH-0936	id	WP-6b	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1301-1305	CH-0937	id	WP-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1391-1400	CH-0938	id	WP-3	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1464-1482	CH-0939	id	M-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1464-1482	CH-0939	id	WP-5	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1464-1482	CH-0939	id	§4	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1523-1529	CH-0940	id	O-1	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1578-1582	CH-0941	id	D-3	x1
REMOVED	MitateDB-api/src/mitatedb_api/control_plane.py	L1967-1979	CH-0943	id	WP-5	x1
SUMMARY ch_blocks=27 ws_only=0 unpaired=0 removed_rows=31
(exit 0)
```

`WS-ONLY` 0 行、`UNPAIRED` 0 行。日付と裁定の日付句 (`supervisor ruling 2026-09-04` など) は監査スクリプトの `id` / `path` / `wp-locator` のどれにも当たらないので `REMOVED` 行に出ない (CS6・CS7 と同じ)。各行の根拠は `wo-section17.md` 17.4 の「除いた語の一覧」。

## 5. `repull.py --dry-run 092e1a1 security/CONTROL_MAPPING.md -- <module>` (cwd = checkout の根)

```text
$ python3 "$SP/repull.py" --dry-run 092e1a1 security/CONTROL_MAPPING.md -- r2db-api/src/r2db_api/platform_declarations.py
security/CONTROL_MAPPING.md:700: platform_declarations.py :1168 -> :1179
security/CONTROL_MAPPING.md:701: platform_declarations.py :1152 -> :1163
security/CONTROL_MAPPING.md:766: platform_declarations.py :499 -> :502
security/CONTROL_MAPPING.md:773: platform_declarations.py :465 -> :468
security/CONTROL_MAPPING.md:781: platform_declarations.py :1031 -> :1038
security/CONTROL_MAPPING.md:782: platform_declarations.py :1031 -> :1038
security/CONTROL_MAPPING.md:783: platform_declarations.py :1031 -> :1038
security/CONTROL_MAPPING.md:784: platform_declarations.py :1108 -> :1119
security/CONTROL_MAPPING.md:785: platform_declarations.py :1260 -> :1271
security/CONTROL_MAPPING.md:785: platform_declarations.py :1369 -> :1380
security/CONTROL_MAPPING.md:785: platform_declarations.py :1346 -> :1357
security/CONTROL_MAPPING.md:786: platform_declarations.py :1260 -> :1271
security/CONTROL_MAPPING.md:787: platform_declarations.py :1260 -> :1271
security/CONTROL_MAPPING.md:788: platform_declarations.py :1260 -> :1271
security/CONTROL_MAPPING.md:790: platform_declarations.py :1515 -> :1526
security/CONTROL_MAPPING.md:1872: platform_declarations.py :1584 -> :1595
security/CONTROL_MAPPING.md:1874: platform_declarations.py :1584 -> :1595
security/CONTROL_MAPPING.md:1960: platform_declarations.py :748 -> :754
security/CONTROL_MAPPING.md:1961: platform_declarations.py :748 -> :754
security/CONTROL_MAPPING.md:1962: platform_declarations.py :748 -> :754
security/CONTROL_MAPPING.md:1963: platform_declarations.py :748 -> :754
security/CONTROL_MAPPING.md:1964: platform_declarations.py :748 -> :754
security/CONTROL_MAPPING.md: changed 22, unresolved 0, not applied 0
(exit 0)
$ python3 "$SP/repull.py" --dry-run 092e1a1 security/CONTROL_MAPPING.md -- MitateDB-api/src/mitatedb_api/control_plane.py
security/CONTROL_MAPPING.md:328: control_plane.py :1538 -> :1569
security/CONTROL_MAPPING.md:329: control_plane.py :1227 -> :1247
security/CONTROL_MAPPING.md:330: control_plane.py :1777 -> :1809
security/CONTROL_MAPPING.md:331: control_plane.py :1800-1801 -> :1832-1833
security/CONTROL_MAPPING.md:332: control_plane.py :94 -> :96
security/CONTROL_MAPPING.md:332: control_plane.py :1452 -> :1479
security/CONTROL_MAPPING.md:571: control_plane.py :1124 -> :1141
security/CONTROL_MAPPING.md:573: control_plane.py :94 -> :96
security/CONTROL_MAPPING.md:573: control_plane.py :1452 -> :1479
security/CONTROL_MAPPING.md:574: control_plane.py :605 -> :613
security/CONTROL_MAPPING.md:635: control_plane.py :1777 -> :1809
security/CONTROL_MAPPING.md:636: control_plane.py :1921 -> :1954
security/CONTROL_MAPPING.md:638: control_plane.py :1494 -> :1524
security/CONTROL_MAPPING.md:640: control_plane.py :94 -> :96
security/CONTROL_MAPPING.md:641: control_plane.py :1452 -> :1479
security/CONTROL_MAPPING.md:889: control_plane.py :1728 -> :1760
security/CONTROL_MAPPING.md:890: control_plane.py :153 -> :158
security/CONTROL_MAPPING.md:891: control_plane.py :1119 -> :1136
security/CONTROL_MAPPING.md:899: control_plane.py :160 -> :165
security/CONTROL_MAPPING.md:900: control_plane.py :1345 -> :1370
security/CONTROL_MAPPING.md:901: control_plane.py :164 -> :169
security/CONTROL_MAPPING.md:1078: control_plane.py :1584 -> :1616
security/CONTROL_MAPPING.md:1085: control_plane.py :409 -> :417
security/CONTROL_MAPPING.md:1312: control_plane.py :1921 -> :1954
security/CONTROL_MAPPING.md:1731: control_plane.py :990 -> :1003
security/CONTROL_MAPPING.md:1800: control_plane.py :1626 -> :1658
security/CONTROL_MAPPING.md:1802: control_plane.py :999 -> :1012
security/CONTROL_MAPPING.md:1803: control_plane.py :1014 -> :1027
security/CONTROL_MAPPING.md:1991: control_plane.py :1725 -> :1757
security/CONTROL_MAPPING.md:1992: control_plane.py :1735 -> :1767
security/CONTROL_MAPPING.md:1993: control_plane.py :1379 -> :1404
security/CONTROL_MAPPING.md:2134: control_plane.py :1416 -> :1443
security/CONTROL_MAPPING.md:2135: control_plane.py :94 -> :96
security/CONTROL_MAPPING.md: changed 33, unresolved 1, not applied 0
unresolved security/CONTROL_MAPPING.md:574: MitateDB-api/src/mitatedb_api/control_plane.py:1967
(exit 1)
```

**`unresolved` の原因**: `security/CONTROL_MAPPING.md:574` (SI-03 MitateDB-api の主張「Revoke-gate role filter and issuance freeze apply from the start on this peer, symmetric with r2db's own bundle -- `MitateDB-api/src/mitatedb_api/control_plane.py:1967`, `:605`」) が、基点 L1967 = 塊 L1967-1979 の先頭行 `# Phase 3.5 WP-5: filtered to `role == "control"` rows only --` を指している。spec の CH-0943 がこの行のラベル `Phase 3.5 WP-5: ` を除くので、同じ内容の行が作業ツリーに無く対応が取れない (Y7-15 の場合)。除去後の同じコメントの先頭行は作業ツリー L2000 (`# filtered to `role == "control"` rows only --`)。CH-0943 を spec から外せば `changed 34, unresolved 0` になる (別途 dry-run で確認はしていない — 33 件の対応は上のとおり取れている)。裁定は `wo-section17.md` 17.5 Y8-3。

## 6. AST・対象外の塊・改行・バックスラッシュ (最終の spec を当てた作業ツリー。`$SP` の計測 script で基点 blob と比べた)

```text
## r2db-api/src/r2db_api/platform_declarations.py
- lines 1737 -> 1748
- tokens (file) 48 -> 30
- date lines 13 -> 6; dates 13 -> 6
- '#:' lines 70 -> 69
- ast_signature equal: True
- find_broken_line_wrap_joins: 0
- excluded blocks verbatim in new: 35/35
- blocks 67 -> 67; CH blocks 7
- backslashes in new docstring blocks: 0
## MitateDB-api/src/mitatedb_api/control_plane.py
- lines 2274 -> 2309
- tokens (file) 150 -> 114
- date lines 5 -> 0; dates 5 -> 0
- '#:' lines 0 -> 0
- ast_signature equal: True
- find_broken_line_wrap_joins: 0
- excluded blocks verbatim in new: 2/2
- blocks 85 -> 85; CH blocks 21
- backslashes in new docstring blocks: 0
```

- `ast_signature` は検査器の §4.1 (1) と同じ関数 (docstring を除いた `ast.dump`)。
- 「excluded blocks」= 登録 helper の中の塊 (r2db 35、MitateDB 1) と既存の CH-ID の塊 (MitateDB CH-0543) の基点のバイト列が、作業ツリーにそのまま在ること。`_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py`) は触っていない (`git status` に tests/ の差分なし)。
- MitateDB の CH blocks 21 = 既存の CH-0543 + 新規 20。
- r2db の `#:` の行 70 → 69 は CH-0861 (L75-77) が折り返しの 2 行目 (`#: ruling 2026-09-03).`) ごと消えたため。`#:` の行頭記号の規則 (0g) は検査器 `--base` exit 0 で通った。

`git status --short` (spec を当てた時点):

```text
 M MitateDB-api/src/mitatedb_api/control_plane.py
 M docs/code-history/MitateDB-api/control_plane.md
 M r2db-api/src/r2db_api/platform_declarations.py
?? docs/code-history/r2db-api/platform_declarations.md
```

## 7. 位置参照の行の動き (触らない対象。観察)

- `MitateDB-api/tests/test_control_main.py:511` の `control_plane.py:1256-1258` → 作業ツリーでは L1277-1279。基点の時点で既に指す先がずれている (`_authenticate` の denial と書くが、基点 L1256-1258 は `__init__` の `operation_catalog_url` のコメント)。触らない。
- `conformance-tests/test_c14_authority_boundary.py:747` の `MitateDB-api/src/mitatedb_api/control_plane.py:1322` → 作業ツリーでは L1347。行数 2,309 の範囲内。触らない (完了条件 34 相当の変異先)。

## 8. 照合の後の復元

```text
$ git checkout -- r2db-api/src/r2db_api/platform_declarations.py MitateDB-api/src/mitatedb_api/control_plane.py docs/code-history/MitateDB-api/control_plane.md
$ rm docs/code-history/r2db-api/platform_declarations.md
$ git status --short     # cloud-out/cs8/ だけ
```

## 9. 確かめていないこと

- 両 peer の pytest suite、`conformance-tests/`、`tools/tests`、`tools/dev/gate.py`、`tools/dev/mutate.py` (変異 36 項目)、`finalize.py` — PostgreSQL と pytest がこの環境に無い。
- `cs8_cli_red.py` の `25 passed` (pytest が無い。CLI 3 本 (P ×2 module、R、D) が exit 0 であることは §2・§3 で直接確かめた)。
- `repull.py` を書き込みモードで当てた後の `security/CONTROL_MAPPING.md` の `Version:` 行 (版は作業機で決める。版数行は書かない)。
- 変異の対象行 (17.4 の案) が実際に赤になること。
