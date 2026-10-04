# (A) 実測 — 変更セット 8 (r2db `platform_declarations.py`、MitateDB `control_plane.py`)

- **基点**: `092e1a1` (このセッションの checkout の `origin/main`。着手時に `git rev-parse --short origin/main` で取った。`092e1a1..origin/main` は 0 commit。作業機の local main はこれより先に進んでいる可能性があるので、着手時に blob を照合する: `590c904f9350eb4e339b7014cf6ab77138fbbff2` = `r2db-api/src/r2db_api/platform_declarations.py`、`89401773874499038c02d7ff292cbbde308950c6` = `MitateDB-api/src/mitatedb_api/control_plane.py`)。
- **数え方**: 作業指示書 §16.2 と同じ (§13.2・§14.2 の正規表現、§2.3 末尾の経緯トークンの数え方 = `tools/check_comment_provenance.py` の `_HISTORY_TOKEN_PATTERNS` を全文に当てた `findall` の合計。目印は設計 §3 の叙述の目印。安全 / 保護参照 / 位置は §14.2 の正規表現と母集団 (経緯トークンを含む文))。塊は `extract_all_blocks` を基点の blob に当てた。登録 helper は両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` の行のうち、その module のパスを持つ行の symbol (r2db 59、MitateDB 1) を同型性テストと同じ探し方 (module 直下の def / class / Assign、次に class の中の def) で見つけ、その node の行範囲に収まる塊を「登録 helper の中」とした。
- **計測 script**: `cloud-out/cs8/cs8_measure.py` (塊・トークン・目印・安全 / 保護参照 / 位置・参照の語)、`cloud-out/cs8/cs8_extscan.py` (module の外からの参照、位置参照、行番号 pin、設計 §5 (b) の grep。基点の tree を `git show` で読む)、`cloud-out/cs8/cs8_dump_blocks.py` (対象の塊の全文を行番号付きで出す。判定に使った)。出力の生データは `measure.json` (同じ場所)。

## 1. 塊の数と対象

| 項目 | r2db `platform_declarations.py` | MitateDB `control_plane.py` | 計 |
|---|---|---|---|
| 行数 (基点) | 1,737 | 2,274 | 4,011 |
| 塊 (`extract_all_blocks`) | 67 (docstring 38 / comment 29)、723 行 | 85 (docstring 35 / comment 50)、758 行 | 152 |
| 対象外: 登録 helper の中 | 35 (docstring 34 / comment 1、347 行。59 symbol のうち塊を持つもの) | 1 (L410-440 `_take_bound_advisory_lock` の docstring、31 行) | 36 |
| 対象外: 既存の CH-ID | 0 | 1 (L1586-1616 `CH-0543`) | 1 |
| **対象の塊** | **32** (docstring 4 / comment 28、376 行) | **83** (docstring 34 / comment 49、696 行) | **115** |
| 経緯トークン (module 全文) | 48 | 150 | 198 |
| うち対象の塊の中 / トークンを含む対象の塊 | 35 / 10 塊 (247 行) | 133 / 52 塊 (551 行) | 168 / 62 塊 |
| 日付を含む行 (全文) | 13 | 5 | 18 |
| `#:` の行 | 70 (L75〜L148 の定数の塊、L900-905、L954-970、L1025-1027、L1547-1550) | 0 | 70 |
| 10 行以上の塊 (CH なし、対象) | 6 塊 / 250 行 (最長 60) | 26 塊 / 412 行 (最長 37) | 32 / 662 |
| 10 行以上の塊 (CH なし、登録 helper を含む全塊) | 18 | 27 (CH-0543 の L1586-1616 を除く) | 45 |
| 目印一覧に当たる文 / 塊 (対象の塊だけ) | 7 / 5 | 16 / 15 | 23 / 20 |
| 塊をまたぐ参照の語を含む文 (§13.2 の正規表現 + 追加 3 形) | 17 | 44 | 61 |
| 経緯トークンを含む文 | 15 | 61 | 76 |
| うち 安全 / 保護参照 / 位置 (文) | 7 / 8 / 6 | 35 / 24 / 31 | — |
| 同 (塊) | 5 / 7 / 6 | 30 / 21 / 30 | — |

- 対象の塊の合計 **115** は 130 を超えないので WP の分け方の案は必須ではないが、17.5 Y8-1 に選択肢を置いた (module ごと = 32 / 83)。
- 既存の受け皿: `docs/code-history/MitateDB-api/control_plane.md` (CH-0543 の 1 節。見出し行なし)。r2db の `docs/code-history/r2db-api/platform_declarations.md` は無い (新規)。
- `--register` (基点): `comment provenance register OK: 95 files scanned, 515 CH-IDs`。`--base 092e1a1 <module>` (無変更): `comment provenance OK: 67 blocks checked` / `comment provenance OK: 85 blocks checked`。
- 登録 helper の中の塊 (r2db 35) の内訳と、`#:` の行、日付の行、10 行以上の塊、目印の塊の一覧は下の §4。

## 2. 塊をまたぐ参照先 (module の外から。両 peer の `src/`・`tests/`・`conformance/`、`conformance-tests/`、`security/`、README を基点の tree で grep。§13.2 の正規表現に `'s identical comment`・`<名前> below`/`above`・`own (comment|docstring|paragraph)`・`identical(-purpose) comment` を足した。機械の候補は r2db 28 行 / MitateDB 120 行 (`cs8_extscan.py` の A。symbol 名だけで引いた `__init__` などの雑音を含む) で、手で選別した結果が下)

| 参照元 | 参照の語 | 参照先の塊 | 扱い |
|---|---|---|---|
| `r2db-api/conformance/real_server_r2db.py:528` | below `check_role_connection_limits`'s own floor of 64 | r2db L1037-1089 (`check_role_connection_limits` の docstring。spec CH-0865) | floor の文は残す (ラベル・括弧・日付句の除去のみ) |
| `r2db-api/tests/test_application_audit.py:2848` | claim `check_writer_role_timeouts`'s own docstring makes (design D-1(c)) | r2db L761-777 (登録 helper の中。対象外) | 触らない |
| `r2db-api/tests/test_process_ceilings_declaration.py:839-840` | `inspect.getsource(getattr(pd, name))` に `"os.environ" not in` / `"getenv" not in` (`validate_process_ceilings_value`、`read_platform_declarations`) | r2db L466-485、L500-535 (登録 helper の中) | 文字列検査 (設計 §5 (b) `not in`)。完了条件 10 (a) |
| `security/CONTROL_MAPPING.md` 700/701/766/773/781-788/790/1872/1874/1960-1964 | 位置参照 `r2db-api/src/r2db_api/platform_declarations.py:N` 20 + 続きの形 2 (`:1369`、`:1346`) | コード行 (L1168、L1152、L499、L465、L1031、L1108、L1260、L1369、L1346、L1515、L1584、L748) | 引き直す (repull.py: `changed 22, unresolved 0`) |
| r2db L80-84・L960-964・L1037-1089 → `r2db-api/src/r2db_api/control_main.py` | `r2db_api.control_main`'s own `R2DB_PLATFORM_SCHEMA`、`build_control_app`'s own comment、`control_main`'s own startup fail-fast calls (CS6 §14.2 の参照表の逆向き) | control_main.py の CH-0509・CH-0512 ほか | 本 module から出る参照。文は残す |
| `MitateDB-api/tests/test_control_main.py:511` | `control_plane.py:1256-1258` (位置参照) | MitateDB L1255-1260 (`__init__` のコメント。基点の時点で既に別の行を指す: 文は `_authenticate` の denial と書く) | 触らない (観察。作業ツリーでは L1277-1279) |
| `conformance-tests/test_c14_authority_boundary.py:747` | `MitateDB-api/src/mitatedb_api/control_plane.py:1322` (コメントの中の位置参照) | コード行 (L1322) | 触らない。行数の範囲内に留まることを確かめる (作業ツリー L1347 / 2,309 行) |
| `security/CONTROL_MAPPING.md` 328-332/571/573/574/635-641/889-891/899-901/1078/1085/1312/1731/1800-1803/1991-1993/2134-2135 | 位置参照 `MitateDB-api/src/mitatedb_api/control_plane.py:N` 31 + 続きの形 3 (`:1452` ×2、`:605`) | コード行 25 種 + **コメント行 L1967** (塊 L1967-1979 の先頭。spec CH-0943) | 引き直す (repull.py: `changed 33, unresolved 1` — L1967 は Y7-15、17.5 Y8-3) |
| `MitateDB-api/conformance/conformance_adapter_mitatedb.py:214` | `above (unlike `control_plane.InMemoryControlBackend`'s) takes NO` | クラスの振る舞い (コメントの参照ではない) | 該当なし |
| `r2db-api/src/r2db_api/control_http.py:54`、`ops.py:743`、`service.py:532` | `that method's own docstring, `control_plane.py`` | r2db-api 側の同名 module | 該当なし (本 module ではない) |
| MitateDB L1051-1063・L1288-1296 → `MitateDB-api/src/mitatedb_api/platform_declarations.py` | `platform_declarations.check_writer_role_timeouts` / `derive_visibility_lag_ms` / `read_platform_declarations` | 関数 | 本 module から出る参照。文は残す |

module の中の塊をまたぐ参照 (`above` / `below` / `own docstring` …) は `judgement-*.md` の「参照先一覧」(r2db 17 文、MitateDB 44 文。同じ塊の中を指す文も含む)。

## 3. 位置参照の所在 (`ファイル名:行`。同じ行の直前のパスを継ぐ続きの形 `` `:N` `` を含む。基点の tree)

| 所在 | r2db `platform_declarations.py` | MitateDB `control_plane.py` | 扱い |
|---|---|---|---|
| `security/CONTROL_MAPPING.md` | 20 + 続き 2 = 22 (`:700`、`:701`、`:766`、`:773`、`:781`〜`:788`、`:790`、`:1872`、`:1874`、`:1960`〜`:1964`) | 31 + 続き 3 = 34 (`:328`〜`:332`、`:571`、`:573`、`:574`、`:635`、`:636`、`:638`、`:640`、`:641`、`:889`〜`:891`、`:899`〜`:901`、`:1078`、`:1085`、`:1312`、`:1731`、`:1800`、`:1802`、`:1803`、`:1991`〜`:1993`、`:2134`、`:2135`) | 引き直す (Y7-2 相当) |
| `conformance-tests/` | 0 | 1 (`test_c14_authority_boundary.py:747`、`control_plane.py:1322`。コメントの中) | 触らない。行数の範囲内を確かめる |
| README (root、peer) | 0 | 0 | — |
| peer の `docs/` | 0 | 0 | — |
| peer の `tests/` | 0 | 1 (`MitateDB-api/tests/test_control_main.py:511`、`control_plane.py:1256-1258`。基点で既にずれ) | 触らない |
| peer の `conformance/` | 0 | 0 | — |
| module 自身 | 0 | 0 | — |
| `docs/` (設計・作業指示書・archive の記録) | 完全パス 16 + 続き 12、peer 相対・ファイル名だけ 30 + 続き 44 (出現数。peer の区別なし) | 完全パス 25 + 続き 12、peer 相対・ファイル名だけ 77 + 続き 35 (同) | 触らない (記録) |
| 他 (`r2db-api/tests/test_control_plane_service.py:1137` の `control_plane.py:515-525`、`tools/check_comment_provenance.py:1099` の `control_plane.py:1380`) | — | r2db 側の同名 module を指す | 該当なし |

## 4. 行番号 pin と文字列検査 (設計 §5 (b)(c))

| 箇所 | 扱い |
|---|---|
| 行番号 pin (L1 scan) | 両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` に 2 module の `(module, lineno)` pin は 0 件 (r2db `_BACKEND_LAYER_ALLOWLIST` は `postgres.py` だけ、MitateDB `_BACKEND_LAYER_ALLOWLIST` は backend 2 module、`_CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST` は `frozenset()`)。件数 pin `"control_plane.py": 11` (MitateDB) と `"control_plane.py": 13` (r2db。r2db 側の同名 module) は `_fail_call_sites` の AST 走査でコメントに依らない。40b は非該当 |
| 文字列の検査 (設計 §5 (b)) — r2db | `r2db-api/tests/test_process_ceilings_declaration.py:839-840`: `inspect.getsource(getattr(pd, name))` (`validate_process_ceilings_value`、`read_platform_declarations`) に `"os.environ" not in source and "getenv" not in source` (`not in` の向き。基準のコメントに当たる文字列は無い。2 関数は登録 helper で本件は触らないが、module を文字列として読むので完了条件 10 (a) は該当) |
| 文字列の検査 — MitateDB | `MitateDB-api/tests/test_control_plane_store.py:128`・`:2544` (r2db 側も同じ形) と `MitateDB-api/tests/test_control_plane_credential_store_reconciliation.py:120` は `read_text` を `ast.parse` に通すのでコメントに鈍感 (除く)。`MitateDB-api/tests/test_control_plane_service.py:31` は spec JSON の `read_text`。ほかに 2 module を文字列として読む検査は 0 件 (`getsource`・`__doc__`・`.count(` の grep は両 peer の `tests/`・`conformance/`、`conformance-tests/`、`tools/tests/`。`getsource` の他の当たりは別 module か `ast.parse` 経由) |
| 同型性の表 | r2db の登録 helper 59 symbol (塊を持つもの 35)、MitateDB の `_take_bound_advisory_lock` (塊 1) は対象外。`_ISOMORPHIC_TARGETS` に触れない。`check_role_connection_limits` (r2db L1037-1089、L1093-1101) は表に無い (`test_audit_query.py:2942` の註) ので対象 |

## 5. spec を当てた後 (参考。詳細は `checks.md`)

| 項目 | r2db | MitateDB |
|---|---|---|
| spec に入れた塊 / 対象の塊 | 7 / 32 (CH-0860〜CH-0866) | 20 / 83 (CH-0925〜CH-0944) |
| 編集 / 削除した文 | 11 / 0 | 20 / 0 |
| 経緯トークン (全文、前 → 後) | 48 → 30 | 150 → 114 |
| 日付を含む行 (前 → 後) | 13 → 6 | 5 → 0 |
| 行数 (前 → 後) | 1,737 → 1,748 | 2,274 → 2,309 |
| `#:` の行 (前 → 後) | 70 → 69 | 0 → 0 |
| 検査器が拒んだ除去 | 1 (L1-60 第 1 段落の日付) | 7 塊 (文頭ラベル) |
| 登録 | 515 → 542 | |

## 6. 一覧 (計測の生データから。行番号は基点)

### r2db `platform_declarations.py` の一覧

- **10 行以上の塊 (対象、CH なし)**: L1-60、L420-432、L790-835、L909-952、L1037-1089、L1224-1257 (6 塊 / 250 行、最長 60)
- **10 行以上の塊 (登録 helper を含む全塊、CH なし)**: L1-60、L153-164、L420-432、L466-485、L500-513、L761-777、L790-835、L841-867、L909-952、L990-1007、L1037-1089、L1169-1194、L1224-1257、L1269-1283、L1373-1391、L1460-1483、L1516-1525、L1585-1606 (18 塊)
- **目印一覧に当たる文を持つ塊** (塊: 目印。同じ文の 2 つは `+`): L1-60: `supervisor ruling`、`was rejected`、`requester ruling`。L75-77: `requester ruling`。L123-129: `previously`。L909-952: `supervisor ruling`。L1037-1089: `this WP`+`supervisor ruling`
- **経緯トークンを含む対象の塊** (塊 (トークン数)): L1-60 (7)、L75-77 (1)、L94-99 (2)、L420-432 (3)、L685-692 (1)、L790-835 (2)、L909-952 (9)、L960-964 (1)、L1037-1089 (6)、L1093-1101 (3)
- **日付を含む行**: L3、L14、L57、L77、L254、L279、L690、L709、L910、L950、L997、L1073、L1093
- **`#:` の行**: 70 行 (L75〜L1550: 75, 76, 77, 80, 81, 82, 83, 84, 88, 89, 90, 94, 95, 96, 97, 98, 99, 103, 104, 105, 108, 109, 110, 111, 114, 115, 118, 119, 120, 123, 124, 125, 126, 127, 128, 129, 132, 133, 134, 135, 136, 137, 145, 146, 147, 148, 900, 901, 904, 905, 954, 955, 956, 957, 960, 961, 962, 963, 964, 967, 968, 969, 970, 1025, 1026, 1027, 1547, 1548, 1549, 1550)
- **登録 helper の中の塊 (対象外)**: L153-164 (docstring, `PlatformDeclarationError`)、L173-173 (docstring, `Surfaces`)、L180-188 (docstring, `ProcessCeilings`)、L195-196 (docstring, `PlatformDeclarations`)、L205-207 (docstring, `RoleTimeoutCatalog`)、L242-246 (docstring, `reject_removed_timeout_env`)、L253-256 (docstring, `reject_removed_surface_env`)、L279-284 (docstring, `_f3c_message`)、L365-370 (docstring, `validate_surfaces_value`)、L386-392 (docstring, `validate_coalescing_window_value`)、L399-407 (docstring, `validate_audit_writer_roles_value`)、L466-485 (docstring, `validate_process_ceilings_value`)、L500-513 (docstring, `read_platform_declarations`)、L529-535 (comment, `read_platform_declarations`)、L552-556 (docstring, `require_control_surface_declared`)、L596-599 (docstring, `check_control_surface_consistency`)、L704-710 (docstring, `read_declared_role_timeouts`)、L738-741 (docstring, `read_effective_timeouts_ms`)、L749-754 (docstring, `derive_visibility_lag_ms`)、L761-777 (docstring, `check_writer_role_timeouts`)、L841-867 (docstring, `check_contract_170_declarations`)、L975-979 (docstring, `_roles_with_table_privilege`)、L990-1007 (docstring, `_table_owner`)、L1169-1194 (docstring, `check_auditreader_statement_timeout`)、L1269-1283 (docstring, `headroom_lower_bound`)、L1289-1294 (docstring, `_count_registered_applications`)、L1305-1312 (docstring, `_read_connection_headroom_settings`)、L1335-1338 (docstring, `HeadroomReport`)、L1355-1359 (docstring, `_f18_message`)、L1373-1391 (docstring, `check_max_connections_headroom`)、L1460-1483 (docstring, `check_application_collations`)、L1516-1525 (docstring, `check_request_rate_function`)、L1568-1572 (docstring, `_f21_acl_holders`)、L1585-1606 (docstring, `check_denial_window_function`)、L1688-1692 (docstring, `ops_module_hint`) — 35 塊 / 347 行
- **既存の CH-ID**: 0

**経緯と同じ文にある安全上の理由・保護参照・位置** (経緯トークンを含む文のうち §14.2 の正規表現に当たるもの。文は消さない)

| 塊 | 種別 | 語 |
|---|---|---|
| L1-60 | 安全、保護参照、位置 | 安全: role, timeout; 保護参照 2 文; 位置: below |
| L94-99 | 保護参照、位置 | 保護参照 1 文; 位置: above |
| L420-432 | 保護参照 | 保護参照 1 文 |
| L685-692 | 保護参照 | 保護参照 1 文 |
| L790-835 | 保護参照 | 保護参照 1 文 |
| L909-952 | 安全、保護参照、位置 | 安全: role; 保護参照 1 文; 位置: below |
| L960-964 | 安全、位置 | 安全: credentials; 位置: above |
| L1037-1089 | 安全、保護参照、位置 | 安全: role; 保護参照 1 文; 位置: above |
| L1093-1101 | 安全、位置 | 安全: role; 位置: below |

### MitateDB `control_plane.py` の一覧

- **10 行以上の塊 (対象、CH なし)**: L1-37、L82-93、L128-148、L238-248、L346-369、L502-523、L711-727、L868-882、L1024-1035、L1051-1063、L1189-1198、L1225-1234、L1266-1277、L1311-1320、L1367-1377、L1391-1400、L1418-1451、L1464-1482、L1564-1576、L1709-1724、L1856-1868、L1885-1894、L1967-1979、L2052-2062、L2195-2204、L2219-2244 (26 塊 / 412 行、最長 37)
- **10 行以上の塊 (登録 helper を含む全塊、CH なし)**: L1-37、L82-93、L128-148、L238-248、L346-369、L410-440、L502-523、L711-727、L868-882、L1024-1035、L1051-1063、L1189-1198、L1225-1234、L1266-1277、L1311-1320、L1367-1377、L1391-1400、L1418-1451、L1464-1482、L1564-1576、L1709-1724、L1856-1868、L1885-1894、L1967-1979、L2052-2062、L2195-2204、L2219-2244 (27 塊)
- **目印一覧に当たる文を持つ塊** (塊: 目印。同じ文の 2 つは `+`): L1-37: `this WP`。L346-369: `supervisor ruling`+`差し戻し`。L502-523: `was replaced`+`pre-WP`。L711-727: `was replaced`。L868-882: `supervisor ruling`+`差し戻し`。L1051-1063: `used to`。L1179-1183: `previously`。L1189-1198: `no longer`+`this WP`。L1391-1400: `supervisor ruling`+`差し戻し`。L1506-1512: `was rejected`。L1709-1724: `this WP`。L1832-1838: `supervisor ruling`。L1856-1868: `no longer`。L2195-2204: `supervisor ruling`、`Before this fix`+`this WP`。L2219-2244: `this WP`
- **経緯トークンを含む対象の塊** (塊 (トークン数)): L1-37 (6)、L82-93 (4)、L96-99 (2)、L117-123 (2)、L128-148 (3)、L154-159 (3)、L195-200 (2)、L238-248 (4)、L269-275 (3)、L346-369 (7)、L383-387 (1)、L502-523 (4)、L606-611 (2)、L629-632 (2)、L711-727 (3)、L868-882 (7)、L950-958 (2)、L984-986 (2)、L1024-1035 (2)、L1051-1063 (2)、L1091-1095 (2)、L1158-1161 (2)、L1189-1198 (3)、L1225-1234 (2)、L1247-1253 (2)、L1266-1277 (2)、L1288-1296 (2)、L1301-1305 (1)、L1336-1342 (2)、L1367-1377 (2)、L1391-1400 (5)、L1418-1451 (2)、L1464-1482 (3)、L1506-1512 (2)、L1560-1562 (1)、L1564-1576 (2)、L1627-1629 (3)、L1634-1640 (2)、L1647-1653 (2)、L1709-1724 (2)、L1794-1799 (1)、L1804-1810 (2)、L1816-1820 (2)、L1832-1838 (4)、L1856-1868 (2)、L1907-1908 (2)、L1967-1979 (2)、L2052-2062 (2)、L2130-2135 (2)、L2195-2204 (4)、L2219-2244 (2)、L2268-2272 (1)
- **日付を含む行**: L363、L878、L1391、L1832、L2195
- **`#:` の行**: 0
- **登録 helper の中の塊 (対象外)**: L410-440 (docstring, `_take_bound_advisory_lock`) — 1 塊 / 31 行
- **既存の CH-ID**: L1586-1616 CH-0543

**経緯と同じ文にある安全上の理由・保護参照・位置** (経緯トークンを含む文のうち §14.2 の正規表現に当たるもの。文は消さない)

| 塊 | 種別 | 語 |
|---|---|---|
| L1-37 | 安全、保護参照、位置 | 安全: CredentialStore, credential, credential_store_postgres, credentials, transaction; 保護参照 3 文; 位置: `control_http.py`'s, below |
| L82-93 | 安全、保護参照 | 安全: credential, role; 保護参照 2 文 |
| L117-123 | 安全 | 安全: commit |
| L128-148 | 安全、保護参照、位置 | 安全: credentials_per_application; 保護参照 1 文; 位置: here |
| L154-159 | 保護参照、位置 | 保護参照 1 文; 位置: above |
| L195-200 | 保護参照 | 保護参照 1 文 |
| L238-248 | 安全、位置 | 安全: rollback; 位置: above, here |
| L269-275 | 安全、位置 | 安全: CredentialStore, credential; 位置: here |
| L346-369 | 安全、位置 | 安全: CredentialStore, credential, secret; 位置: above |
| L383-387 | 安全、位置 | 安全: compare_digest, credential, credential_id; 位置: above |
| L502-523 | 安全、保護参照、位置 | 安全: LOCK, TOCTOU, commits, committed, locking, transaction; 保護参照 1 文; 位置: above |
| L606-611 | 安全 | 安全: role |
| L629-632 | 位置 | 位置: above |
| L711-727 | 安全、保護参照、位置 | 安全: LOCK, commits, credentials_per_application, locking, transaction; 保護参照 1 文; 位置: above |
| L868-882 | 安全、位置 | 安全: CredentialRegistry, role, secret; 位置: above |
| L950-958 | 安全、位置 | 安全: TOCTOU, advisory, lock; 位置: above, below, here |
| L984-986 | 安全、位置 | 安全: lock; 位置: above |
| L1024-1035 | 安全 | 安全: credential, credential_id, credentials, secret |
| L1051-1063 | 安全、保護参照、位置 | 安全: ROLE, role, timeouts, transaction; 保護参照 1 文; 位置: below |
| L1158-1161 | 位置 | 位置: above |
| L1189-1198 | 安全、保護参照 | 安全: credential, credentials, revoke, role; 保護参照 1 文 |
| L1225-1234 | 安全、位置 | 安全: credential, revoke_credential, role, transaction; 位置: below |
| L1247-1253 | 位置 | 位置: here |
| L1336-1342 | 保護参照、位置 | 保護参照 1 文; 位置: above |
| L1367-1377 | 安全 | 安全: credential_id |
| L1391-1400 | 安全、保護参照、位置 | 安全: secret; 保護参照 1 文; 位置: below, here |
| L1418-1451 | 安全、保護参照、位置 | 安全: role; 保護参照 1 文; 位置: below |
| L1464-1482 | 安全、保護参照、位置 | 安全: credential, role; 保護参照 1 文; 位置: above |
| L1560-1562 | 保護参照 | 保護参照 1 文 |
| L1564-1576 | 位置 | 位置: above |
| L1627-1629 | 安全 | 安全: role |
| L1647-1653 | 安全、保護参照、位置 | 安全: atomic_mutation; 保護参照 1 文; 位置: above |
| L1709-1724 | 安全 | 安全: commits, transaction |
| L1794-1799 | 安全、保護参照、位置 | 安全: credential, role; 保護参照 1 文; 位置: below |
| L1816-1820 | 安全、位置 | 安全: credentials_active_count, credentials_active_count_locked, transaction; 位置: above, here |
| L1832-1838 | 保護参照、位置 | 保護参照 1 文; 位置: `control_http.py`'s |
| L1856-1868 | 保護参照、位置 | 保護参照 1 文; 位置: here |
| L1907-1908 | 位置 | 位置: above |
| L1967-1979 | 安全 | 安全: credential, role |
| L2195-2204 | 安全、保護参照、位置 | 安全: credential_id, secret; 保護参照 1 文; 位置: `ops.py`'s, below, here |
| L2219-2244 | 安全、保護参照 | 安全: credential; 保護参照 1 文 |
| L2268-2272 | 保護参照、位置 | 保護参照 1 文; 位置: `ops.py`'s |

