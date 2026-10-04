**版数行に足す行** (作業指示書の先頭の版数一覧に足す 1 行。日付は作業機で確定する日に替える):

- **v1.15 (2026-10-04)**: §17 に変更セット 8 (r2db `platform_declarations.py` と MitateDB `control_plane.py`) の manifest の草案 (着手条件、`092e1a1` の実測、完了条件 ↔ 変異、記録の枠) と、裁定を求める点 Y8-1〜Y8-13 (§17.5。選択肢と実測だけ) を追記した。既存の節は書き換えていない。

---

## 17. 変更セット 8 — r2db `platform_declarations.py` と MitateDB `control_plane.py`

正本設計は v0.29 (§3、§4、§5、§6、§8、§9 (0d〜0h)、§9.2、§10.1、§10.4〜§10.9)。行番号と実測は `092e1a1` の値 (変更セット 7 WP-7b の merge。2 module の blob が `<BASE>` と同じであることを着手条件 2 で確かめる)。共通の規則は §13.3・§14.3・§16.3 を指し、ここには差分だけを書く。WP の分け方は §17.5 Y8-1 で決める (この草案は 1 WP・2 module の形で書き、分けるときの置き換えを括弧で示す)。本節の草案はクラウドのセッションで書き (`cloud-out/cs8/`)、PostgreSQL を使うテスト・変異・完了ゲートは流していない。

### 17.1 着手条件

| # | 条件 |
|---|---|
| 1 | 変更セット 7 の WP-7b (設計 §10.9 の次の候補の前段) が main に統合されている (`092e1a1` がその merge)。着手時の main の先頭を基点 `<BASE>` とする |
| 2 | 2 module の blob が `092e1a1` と `<BASE>` で同じ (`git rev-parse 092e1a1:<path> <BASE>:<path>`。`092e1a1` では `590c904f9350eb4e339b7014cf6ab77138fbbff2` と `89401773874499038c02d7ff292cbbde308950c6`)。違えば §17.2 の実測、spec の `base`・`parent`・`line`・`line_range`、`cs8_cli_red.py` の `BASE`、`cs8_removed_tokens.py` の `--base` の既定を `<BASE>` で取り直す (Y7-13 の手順) |
| 3 | 着手時に、並行 branch・worktree (`git worktree list`、各 worktree の未コミットの差分、`tools/dev/ledger.py --open` の進行中の行) と台帳 R-37 の残件が、本節の触るファイル (2 module、`docs/code-history/r2db-api/platform_declarations.md`、`docs/code-history/MitateDB-api/control_plane.md`、`security/CONTROL_MAPPING.md`) と CH-0860〜CH-0989 に触れないことを取り直す。重なりがあれば実装前に監督へ上げる (§1.2 の 16)。草案時 (クラウドの checkout、worktree 1 つ、`092e1a1..origin/main` 0 commit) の `ledger.py --open` の進行中の行は R-22・R-52・R-80・R-101・R-11・R-31・R-36・R-39 で、台帳の本文に 2 module の名は無い |
| 4 | 着手時に設計 §5 (b) の grep と §17.2 の静的テストの注記を取り直す |
| 5 | WP を分けるとき (Y8-1 の (B))、後の WP は前の WP の commit・完了ゲート・main への merge の後に着手し、基点はその統合後の main (§16.1 の 5 と同じ) |

### 17.2 選定と実測 (`092e1a1`)

選定は監督の指示 (台帳 R-22 問い 3 の次の変更セット。設計 §10.9 の次の候補「台帳 R-37 で `cell.py` から出たファイルと、§6 の優先 1 の残り (r2db `structured.py`)」とは別に、2 module を指定)。数え方は §13.2・§14.2・§16.2 と同じ (経緯トークンは §2.3 末尾、目印は設計 §3 の叙述の目印、参照の語は §13.2 の正規表現に `'s identical comment`・`<名前> below`/`above`・`own (comment|docstring|paragraph)` を足したもの、安全 / 保護参照 / 位置は §14.2 の正規表現と母集団)。計測は `cloud-out/cs8/cs8_measure.py`・`cs8_extscan.py` (`check_comment_provenance` を import して `092e1a1` の blob に当てた)。登録 helper は両 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` の行で、同型性テストと同じ探し方 (module 直下の def / class / Assign、次に class の中の def) で node を見つけ、その行範囲に収まる塊を対象外にした。

| 項目 | r2db `platform_declarations.py` | MitateDB `control_plane.py` | 計 |
|---|---|---|---|
| 行数 | 1,737 | 2,274 | 4,011 |
| 塊 (`extract_all_blocks`) | 67 (docstring 38 / comment 29)、723 行 | 85 (docstring 35 / comment 50)、758 行 | 152 |
| 対象外: 登録 helper の中 | 35 (59 symbol のうち塊を持つもの。docstring 34 / comment 1、347 行。一覧は `cloud-out/cs8/measure.md` §6) | 1 (L410-440 `_take_bound_advisory_lock` の docstring) | 36 |
| 対象外: 既存の CH-ID | 0 | 1 (L1586-1616 CH-0543) | 1 |
| **対象の塊** | **32** (docstring 4 / comment 28、376 行) | **83** (docstring 34 / comment 49、696 行) | **115** |
| 経緯トークン (全文) | 48 | 150 | 198 |
| うち対象の塊の中 / トークンを含む対象の塊 | 35 / 10 塊 (247 行) | 133 / 52 塊 (551 行) | 168 / 62 塊 |
| 日付を含む行 | 13 (L3、L14、L57、L77、L254、L279、L690、L709、L910、L950、L997、L1073、L1093) | 5 (L363、L878、L1391、L1832、L2195) | 18 |
| 目印一覧に当たる文 / 塊 (対象の塊だけ) | 7 / 5 | 16 / 15 | 23 / 20 |
| 塊をまたぐ参照の語を含む文 | 17 | 44 | 61 |
| 経緯トークンを含む文のうち 安全 / 保護参照 / 位置 | 7 / 8 / 6 文 (塊 5 / 7 / 6) | 35 / 24 / 31 文 (塊 30 / 21 / 30) | — |
| `#:` の行 | 70 (L75-148 の定数の塊、L900-905、L954-970、L1025-1027、L1547-1550) | 0 | 70 |
| 10 行以上の塊 (CH なし、対象。設計 §10.3 の数え方) | 6 塊 / 250 行 (最長 60) | 26 塊 / 412 行 (最長 37) | 32 / 662 (登録 helper を含む全塊で 45) |

- `--register` (基点): `comment provenance register OK: 95 files scanned, 515 CH-IDs`。
- `--base 092e1a1 <module>` (無変更): `comment provenance OK: 67 blocks checked` / `comment provenance OK: 85 blocks checked` (exit 0)。
- 受け皿: r2db は新規 `docs/code-history/r2db-api/platform_declarations.md` (cs8_apply.py は見出し行を書かない。Y8-8)、MitateDB は既存の `docs/code-history/MitateDB-api/control_plane.md` (`092e1a1` で CH-0543 の 1 節) に追記。

**10 行以上の塊 (対象、CH なし)**

- r2db: L1-60、L420-432、L790-835、L909-952、L1037-1089、L1224-1257
- MitateDB: L1-37、L82-93、L128-148、L238-248、L346-369、L502-523、L711-727、L868-882、L1024-1035、L1051-1063、L1189-1198、L1225-1234、L1266-1277、L1311-1320、L1367-1377、L1391-1400、L1418-1451、L1464-1482、L1564-1576、L1709-1724、L1856-1868、L1885-1894、L1967-1979、L2052-2062、L2195-2204、L2219-2244

**目印一覧に当たる文を持つ塊** (塊: 目印。同じ文の 2 つは `+`。文ごとの展開は `cloud-out/cs8/judgement-*.md` の B 表)

- r2db (7 文 / 5 塊): L1-60: `supervisor ruling`、`was rejected`、`requester ruling`。L75-77: `requester ruling`。L123-129: `previously`。L909-952: `supervisor ruling`。L1037-1089: `this WP`+`supervisor ruling`
- MitateDB (16 文 / 15 塊): L1-37: `this WP`。L346-369: `supervisor ruling`+`差し戻し`。L502-523: `was replaced`+`pre-WP`。L711-727: `was replaced`。L868-882: `supervisor ruling`+`差し戻し`。L1051-1063: `used to`。L1179-1183: `previously`。L1189-1198: `no longer`+`this WP`。L1391-1400: `supervisor ruling`+`差し戻し`。L1506-1512: `was rejected`。L1709-1724: `this WP`。L1832-1838: `supervisor ruling`。L1856-1868: `no longer`。L2195-2204: `supervisor ruling`、`Before this fix`+`this WP`。L2219-2244: `this WP`

**経緯と同じ文にある安全上の理由 (先に一覧にする)**: 経緯トークンを含む文のうち §14.2 の安全の語に当たる文を持つ塊。文は消さない (Y7-3 (c))。経緯トークンだけの除去は Y7-3 (b) の条件で許す。保護参照・位置の語だけの塊は `judgement-*.md` の C 表に展開した。

**r2db** (経緯トークンを含む文のうち安全 / 保護参照 / 位置に当たる塊):

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

**MitateDB**:

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

(`—` 無し。種別が位置・保護参照だけの塊は、文は消さないが安全の語は無い。)

**塊をまたぐ参照先** (両 peer の `src/`・`tests/`・`conformance/`、`conformance-tests/`、`security/`、README を grep し、手で選別した。参照先の文は「残す」と固定し、§17.4 の参照先一覧に載せる)

| 参照元 | 参照の語 | 参照先の塊 |
|---|---|---|
| `r2db-api/conformance/real_server_r2db.py:528` | below `check_role_connection_limits`'s own floor of 64 | r2db L1037-1089 |
| `r2db-api/tests/test_application_audit.py:2848` | claim `check_writer_role_timeouts`'s own docstring makes (design D-1(c)) | r2db L761-777 (登録 helper。対象外) |
| r2db L80-84、L960-964、L1037-1089 (逆向き) | `r2db_api.control_main`'s own `R2DB_PLATFORM_SCHEMA` / `build_control_app`'s own comment / `control_main`'s own startup fail-fast calls | `r2db-api/src/r2db_api/control_main.py` (CS6 §14.2 の参照表の L1-194、L442-483、L561-573) |
| r2db L1037-1089 の `(added this WP)`、L1093-1101 の `see the module header above` | 同じ塊のラベル WP-4g / module header の L909-952 | r2db L1037-1089 (第 4 段落のラベル)、L909-952 |
| MitateDB L984-986 | same reasoning as `applications_count_locked` above | MitateDB L950-958 |
| MitateDB L1158-1161 | identical rationale to `InMemoryControlBackend.authenticate_application` above | MitateDB L1024-1035 |
| MitateDB L1091-1095、L711-727、L502-523 | see that method's / function's own docstring | MitateDB L502-523、L410-440 (`_take_bound_advisory_lock`。登録 helper) |
| MitateDB L1816-1820 | see `register_application`'s own identical-shaped comment above | MitateDB L1709-1724 |
| MitateDB L1907-1908 | `Phase 6 WP-3 追補 (brief item A): composed HERE, same single-point discipline `issue_credential` above follows` | MitateDB L1832-1838 (同じラベル) |
| MitateDB L2097-2102、L2052-2062 | see `audit_query`'s own docstring / `_deny_application_credential_on_audit_query`'s own docstring | MitateDB L2052-2062 / L2097-2102 |
| MitateDB L2219-2244、L1464-1482 | `_gate_must_rotate`'s own allow-list / `issue_audit_credential_ceremony` below | MitateDB L1464-1482 / L2219-2244 |
| MitateDB L185-189、L346-369、L391-395 | this module's own header | MitateDB L1-37 |
| MitateDB L1051-1063、L1288-1296 (逆向き) | `platform_declarations.check_writer_role_timeouts` / `derive_visibility_lag_ms` / `read_platform_declarations` | `MitateDB-api/src/mitatedb_api/platform_declarations.py` の関数 (コメントではない) |
| `MitateDB-api/tests/test_control_main.py:511` | `control_plane.py:1256-1258` (位置参照) | MitateDB L1255-1260 (基点の時点で既に別の行を指す。観察。触らない) |
| `conformance-tests/test_c14_authority_boundary.py:747` | `MitateDB-api/src/mitatedb_api/control_plane.py:1322` (コメントの中の位置参照) | コード行 (触らない。行数の範囲内を確かめる) |
| `MitateDB-api/conformance/conformance_adapter_mitatedb.py:214`、r2db `control_http.py:54`・`ops.py:743`・`service.py:532` | `control_plane.InMemoryControlBackend`'s / `control_plane.py` の docstring | 該当なし (クラスの振る舞い / r2db 側の同名 module) |

**静的テストの注記** (Y7-10 相当)

| 箇所 | 扱い |
|---|---|
| 行番号 pin (L1 scan) | 両 peer の `tests/test_l1_details_vocabulary_ast_scan.py` に 2 module の `(module, lineno)` pin は 0 件 (r2db `_BACKEND_LAYER_ALLOWLIST` は `postgres.py` だけ、MitateDB `_BACKEND_LAYER_ALLOWLIST` は `backend_postgres.py`・`backend_sqlite.py`、`_CONTROL_PLANE_NO_VOCABULARY_ALLOWLIST` は `frozenset()`)。件数 pin `"control_plane.py": 11` (MitateDB) は `_fail_call_sites` の AST 走査でコメントに依らない。40b は非該当 |
| 文字列の検査 (設計 §5 (b)) | r2db: `r2db-api/tests/test_process_ceilings_declaration.py:839-840` が `inspect.getsource(getattr(pd, name))` (`validate_process_ceilings_value`、`read_platform_declarations`。どちらも登録 helper) に `"os.environ" not in` / `"getenv" not in` を掛ける (`not in` の向き。基準のコメントに当たる文字列は無い)。MitateDB: `tests/test_control_plane_store.py:128`・`tests/test_control_plane_credential_store_reconciliation.py:120` は `read_text` を `ast.parse` に通すので除く。ほかに 2 module を文字列として読む検査は 0 件 |
| 同型性の表 | r2db の登録 helper 59 symbol (塊 35) と MitateDB の `_take_bound_advisory_lock` (塊 1) は対象外。`_ISOMORPHIC_TARGETS` に触れない。`check_role_connection_limits` (r2db) は表に無く対象 (`r2db-api/tests/test_audit_query.py:2942` の註) |

**2 module を指す位置参照の所在** (`092e1a1`。パス又はファイル名の直後にコロンと行番号が続く形)

| 所在 | r2db | MitateDB | 扱い |
|---|---|---|---|
| `security/CONTROL_MAPPING.md` | 20 + 続きの形 2 (`:1369`・`:1346`、行 785) = 22 (指す行: 1168、1152、499、465、1031×3、1108、1260×4、1369、1346、1515、1584×2、748×5) | 31 + 続きの形 3 (`:1452`×2 (行 332・573)、`:605` (行 574)) = 34 (指す行: 1538、1227、1777×2、1800-1801、94×4、1452×3、1124、605、1967、1921×2、1494、1728、153、1119、160、1345、164、1584、409、990、1626、999、1014、1725、1735、1379、1416) | 引き直す (Y7-2 相当。L1967 はコメント行 → Y8-3) |
| `conformance-tests/` | 0 | 1 (`test_c14_authority_boundary.py:747`、`:1322`。コメントの中) | 触らない。行数の範囲内に留まることを完了条件 34 で確かめる |
| README / peer の `docs/` | 0 / 0 | 0 / 0 | — |
| peer の `tests/` / `conformance/` | 0 / 0 | 1 (`tests/test_control_main.py:511`、`:1256-1258`。基点で既にずれ) / 0 | 触らない |
| module 自身 | 0 | 0 | — |
| `docs/` (記録) / `security/CONTROL_MAPPING_HISTORY.md` | 完全パス 28 (続きを含む)、ファイル名だけ 74 (出現数) | 完全パス 37、ファイル名だけ 112 (peer の区別なし) | 触らない (記録) |

**起草時の確認**: §16.3 の `cs7_apply.py`・`repull.py`・`cs7_cli_red.py`・`cs7_removed_tokens.py` の本文を、名前 (`cs8_`)、基点 (`092e1a1`)、module (2 本) だけ置き換えて `cloud-out/cs8/` に置いた。spec を当てた作業ツリーで `--base 092e1a1` は 2 module とも exit 0、`--register` は `95 files scanned, 542 CH-IDs`、`cs8_removed_tokens.py` は `SUMMARY ch_blocks=27 ws_only=0 unpaired=0 removed_rows=31` (exit 0)、`repull.py --dry-run` は r2db `changed 22, unresolved 0, not applied 0`、MitateDB `changed 33, unresolved 1, not applied 0` (`unresolved security/CONTROL_MAPPING.md:574: MitateDB-api/src/mitatedb_api/control_plane.py:1967`。Y8-3)。出力の逐語は `cloud-out/cs8/checks.md`。

### 17.3 Manifest

**目的**: §13.3 と同じ (2 module の経緯を受け皿へ移し、コードに現在の理由と `CH-NNNN` を残す)。範囲は Y7-3、対象外は Y7-5 と Y8-9。

| 項目 | 内容 (1 WP の形。Y8-1 で分けるときは module ごとに読み替える) |
|---|---|
| 基点 (`--base`、spec の `base`/`parent`、`cs8_cli_red.py` の `BASE`、`cs8_removed_tokens.py` の `--base` の既定) | `<BASE>` (着手条件 1。草案は `092e1a1`) |
| 範囲 (spec の `line_range`) | r2db `[1, 1737]`、MitateDB `[1, 2274]` (`<BASE>` の末尾行) |
| 対象の塊 / 判定表が最低限覆う範囲 | r2db 32 / 目印 7 文 + 安全 5 塊、MitateDB 83 / 目印 16 文 + 安全 30 塊 (§17.2) |
| CH-ID 予約 (spec の `ch_range`) | r2db `CH-0860`〜`CH-0924`、MitateDB `CH-0925`〜`CH-0989` (監督の指示 CH-0860〜 / CH-0925〜 を 65 ずつに切った草案。草案の spec は CH-0860〜CH-0866 と CH-0925〜CH-0944 を使う。Y8-7) |
| spec / 変異 spec | `$SP/cs8-spec-platform_declarations.json`、`$SP/cs8-spec-control_plane.json` (草案は `cloud-out/cs8/` の同名ファイル) / `$SP/cs8-mutations.json` |
| 完了ゲート | `tools/dev/gate.py --label cs8 -C "$WT"` (分けるときは `cs8a` / `cs8b`) |
| `security/CONTROL_MAPPING.md` | 版を 1 つ上げる (主張の文は変えない。版数行は監督が finalize の直前に main の版数行を見て足す) |
| 受け入れ監査 | 規模 L の現行どおり、レビュー完了後に `evidence-auditor` 1 回。監査担当は `cs8_removed_tokens.py -C "$WT"` を 1 回 (分けたときは WP ごとに `--base`・`--head` を替えて 1 回ずつ。§16.3 の WP-7b の註と同じ) |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/platform_declarations.py`、`MitateDB-api/src/mitatedb_api/control_plane.py` (**コメントと docstring だけ**。対象の塊だけ)、`docs/code-history/r2db-api/platform_declarations.md` (新規)、`docs/code-history/MitateDB-api/control_plane.md` (追記だけ)、`security/CONTROL_MAPPING.md` (2 module への位置参照の行番号と先頭の `Version:` の行だけ)、本書 §17.4 | 他の `src/` 全部、`tools/`、`tools/tests/`、両 peer の `tests/` (L1 scan、`test_audit_query.py`、`test_process_ceilings_declaration.py`、`test_control_main.py` を含む)、両 peer の `conformance/`、`conformance-tests/` (`test_c14_authority_boundary.py:747` を含む)、README・両 peer の `docs/`、`security/` の他のファイル、他の受け皿、`docs/code-history/pair.md`、`docs/design/`、台帳、`_ISOMORPHIC_TARGETS` |

| 項目 | 内容 |
|---|---|
| 変更クラス・規模 | 2 module の整理は Class B。`security/CONTROL_MAPPING.md` の位置参照 (r2db 22 件、MitateDB 34 件) を引き直すので経路により **Class D** (Y7-2 と同じ。Y8-2)。規模 **L** (§1.13 の 74)。Class D の証拠は §16.3 と同じ扱い: 設計文書 = 設計 v0.28 の §3 訂正註と §6 の註、契約版数 = 据え置き、設計レビュー = 規模 L の 1 回、完了ゲート = 全部、依頼者裁定の逐語 = 台帳 R-22 行の事後確認、版付きの決定 = `security/CONTROL_MAPPING.md` の `Version:` の行 |
| 必須の規律 | §13.3 の「必須の規律」「保護文 (0d) と訂正 (0g)」「改行」と、§14.3 の「判定表の置き場所」「復元・欠番の裁定の後」「内容の除去が 0 の塊」「意味や出所を落とす除去」と同じ。範囲・除去の条件は Y7-3、折り返しは Y7-4。加えて設計 §10.9 の教訓 (i)〜(iii) を除去のたびに確かめる: (i) 同じ塊に残る文が、除くラベルの名指す設計・WP に寄りかかっていないか (設計名の無い `design §n`、裸の `D-n`・`I-n`、`Code review §n`、`監督裁定 X`、`this WP`、`same commit`、`finding n`)、(ii) 文頭でない位置のラベルを除くと、後ろの文が前に残ったラベル・見出しの段落の続きに読めないか、(iii) ラベルの中に内容語 (規則の名前など) が無いか |
| 編集の道具 | `$SP/cs8_apply.py -C "$WT" --spec <spec>` = §16.3 の `cs7_apply.py` の本文のまま (名前を `cs8_apply` に替えただけ。`excluded_symbols` は r2db が `_ISOMORPHIC_TARGETS` の 59 symbol、MitateDB が `_take_bound_advisory_lock`)。spec の 1 塊と §17.4 の判定表の 1 行を対応させる。module ごとに spec を分け、2 回当てる |
| 位置参照の引き直し | `$SP/repull.py` = §16.3 の本文のまま。worktree の根を cwd にして `python3 "$SP/repull.py" <基点> security/CONTROL_MAPPING.md -- r2db-api/src/r2db_api/platform_declarations.py MitateDB-api/src/mitatedb_api/control_plane.py` (2 module を 1 回で)。出力を §17.4 に逐語で貼る。`unresolved` が出たら書き換えずに止めて報告 (Y7-15。草案の実測で `security/CONTROL_MAPPING.md:574` の `control_plane.py:1967` が 1 件。Y8-3) |
| 統合 | root gate を通し、コミットした後の HEAD で `tools/tests` を流してから統合する (設計 §10.2) |
| 手順 | 設計 §6「手順」。40a は両 peer の suite と下の conformance 2 ファイルを前後 2 回 (実装担当)。`conformance-tests/` の全体は監督の完了ゲートが回す (Y7-14) |

**完了条件 ↔ 変異** (P = `check_comment_provenance.py --base <基点> r2db-api/src/r2db_api/platform_declarations.py MitateDB-api/src/mitatedb_api/control_plane.py`、R = `--register`、D = `check_doc_refs.py`。変異は `tools/dev/mutate.py` で実コードに当てる (設計 §10.2)。変異の対象行は着手時に選び §17.4 に記録する (Y7-8。草案の案は §17.4)。赤が P・R・D の行は wrapper `$SP/cs8_cli_red.py` の node `test_cli_red[c<行><枝>]` を mutate の `tests` に書く。1 項目に test は 1 つ。1〜13 は設計 §6 の表の逐語)

| # | 完了条件 | 変異 (`file:操作`) | 赤になるもの |
|---|---|---|---|
| 1 | コード不変 | コード 1 行の literal を 1 文字変える | §4.1 (1) — `c1` |
| 2 | 移した塊が逐語で在る | 受け皿の節から 1 文を消す | §4.1 (2) — `c2` |
| 3 | 文区間の削除だけ | (a) 残した文から否定語を落とす (b) 残した 2 文を並べ替える (c) 1 語足す (d) 残した文の途中の折返し行を 1 行消す | §4.1 (3) — `c3a`〜`c3d` (4 種それぞれ) |
| 4 | 括弧内の削除が規則どおり | 括弧内の現行正本の参照 (例: SI-) を消す | §4.1 (4) — `c4` (checker は (4) の違反を (3) の行で出す) |
| 5 | 経緯を足していない | 追加行に `WP-` を含める | §4.1 (5) — `c5` |
| 6 | ID の解決と孤児 | コード側 ID を存在しない番号にする / 参照されない節を足す | §4.2 の 1 — `c6a`・`c6b` |
| 7 | ID の全体一意 | 他 peer の companion に同じ番号の節を足す | §4.2 の 2 — `c7` |
| 8 | docstring 依存の新設なし | `src/` に `__doc__` の読み出しを 1 行足す | §4.2 の 5 — `c8` |
| 9 | 行番号 pin が実測と一致 | allowlist を更新前の値に戻す | L1 details AST scan — **非該当** (2 module の `(module, lineno)` pin は 0 件。§17.2)。**監査照合**: L1 scan の 2 module の pin 0 件と、件数 pin `"control_plane.py": 11` (MitateDB) の不変を HEAD で確認 |
| 10 | 文字列検査が効いたまま (該当時) | §5 (b) の向きごとの変異 — (a) `not in` の向き (r2db): `read_platform_declarations` の中 (基点 L500-535。登録 helper の中だが変異先としてだけ使う) に `os.environ` を含むコメントを 1 行足す。MitateDB は非該当 (`read_text` は `ast.parse` に通す) | (a) `r2db-api/tests/test_process_ceilings_declaration.py::test_platform_declarations_readers_never_consult_the_process_environment` (当該 test の正式名は着手時に `:826` 付近で取る) |
| 11 | 登録 helper が同形 (最後の変更セット) | 一方の peer だけ整理する | 非該当 (「最後の変更セット」限り) |
| 12 | 非空虚 (変更セット 1) | `MIN_CH_IDS` を 0 に戻し、全 ID を消す | 非該当 (「変更セット 1」限り) |
| 13 | suite 集計と経緯トークン数の前後 | 監査照合 (両 peer の集計行とトークン数を manifest に残す) | — |
| 14 | 対象外の塊に触れていない (登録 helper の中 r2db 35・MitateDB 1、既存 CH-0543。Y8-9) | **監査照合**: `git diff <基点> -- <2 module>` に 37 塊の行が無く、`_ISOMORPHIC_TARGETS` の差分 0 | — |
| 15 | CH の無い塊を変えていない | CH を付けずに 1 塊から 1 文消す | P exit 1 (§4.1 (2)) — `c15` |
| 16 | 保護参照を含む文は丸ごと消せない (0d) | CH-ID を付けた塊にある保護参照を含む文を 1 つ丸ごと消す (文は §17.4 に記録) | P exit 1 (§4.1 (3)) — `c16` |
| 17 | ラベル削除が規則どおり (§8) | ラベルを消し、区切りの後ろの先頭文字を小文字化する | P exit 1 (§4.1 (3)) — `c17` |
| 18 | 版数付き文書名は残る | CH-ID を付けた塊から版数付き文書名の版数を消す (文は §17.4 に記録) | P exit 1 (§4.1 (3)) — `c18` |
| 19 | 訂正の記録が規則どおり (0g) | (a) 記録の旧文を基準に無い文にする (b) 新文から保護参照を 1 つ消す | (a)(b) P exit 1 (§9f) — `c19a`・`c19b`。記録が無ければ該当なしを監査照合で記録する (草案は訂正を足していない) |
| 20 | `#:` の行を保つ (0g) | CH-ID を付けた `#:` の塊の `#:` を `#` にする (r2db L75-77、CH-0860 の次の塊) | P exit 1 (§9f) — `c20`。**監査照合**: HEAD の `#:` の行 69 (基点 70。CH-0861 の折り返し 2 行目が除去で消える。Y8-11) |
| 21 | 改行の壊れが 0 件 | `find_broken_line_wrap_joins` を 2 module に流す。変異: (a) `id ASC` 型をつなぐ (b) `/` の直後の改行を空白 1 つでつなぐ (c) backtick の span の中の折返しを空白 1 つでつなぐ | 0 件であること。(a) P exit 1 (§4.1 (3)) — `c21a`、(b)(c) P exit 1 (§9e) — `c21b`・`c21c` |
| 22 | 受け皿が原文の写しとして完全 | (a) 受け皿の fenced block の末尾を 1 語切り詰める (b) 折り返しで割れた実在パスを含むラベルを、パスの後半ごと削る (r2db L790-791 の `docs/design/` + `PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` は CH なしの塊なので、CH を付けた塊では MitateDB L82-83 の `PHASE35_CROSS_ENTITY_AND_CONTRACT_130_` + `V1.md` も CH なし。該当する CH 塊が無ければ (b) は非該当とし監査照合で記録) | (a) P exit 1 (§4.1 (2)) — `c22a`、(b) P exit 1 (§4.1 (3)) — `c22b` |
| 23 | 受け皿の ID が `check_doc_refs` で解決 | 受け皿の fenced block に台帳に無い R 番号を 1 つ足す (3 桁で選ぶ。番号は本書に書かない) | D exit 1 — `c23` |
| 24 | 指示語・定冠詞・副詞の参照先を消していない | 残す文の点検語が参照する文を削除する | 機械では赤にならない — **監査照合**: §17.4 の候補一覧とコードレビュー |
| 25 | 安全上の理由と同居する文を残している | §17.2 の一覧の文を文ごと削除する | 機械では赤にならない — **監査照合**: 判定表の根拠とレビュー |
| 26 | 塊をまたぐ参照先の文を残している | §17.2 の参照先 (例: r2db L1037-1089、MitateDB L950-958、L1832-1838) の文を削除する | 機械では赤にならない — **監査照合**: grep の結果と §17.4 の参照先一覧 |
| 27 | 判定表が対象を覆い、本書の本文にある (§10.4) | **監査照合**: 対象の塊の全件 (32 + 83) が §17.4 の判定表に 1 塊 1 行であり、目印一覧に当たる文 (7 + 16) と §17.2 の安全上の理由の塊 (5 + 30) が根拠・点検語の欄に空欄なく載る。表が本書の外にしか無ければ未達 | — |
| 28 | 内容の除去が 0 の塊に CH-ID が無い (§10.4) | CH-ID を付けた塊の 1 つを空白だけの差にする (P は緑) | **監査照合 (固定スクリプト)**: `cs8_removed_tokens.py` の出力に `WS-ONLY` 行が 1 行でもある、又は exit 1 なら赤。出力は §17.4 に逐語で貼る |
| 29 | 復元・欠番の裁定の後に 2 module を走査した (§10.4) | 1 塊で戻した除去と同じ種類の除去を、もう一方の module の塊に 1 つ残す | **監査照合 (固定スクリプト)**: 裁定のたびに `cs8_removed_tokens.py` を再実行した出力が §17.4 にあり、残した除去が `REMOVED` 行として出て判定表で扱われている |
| 30 | 意味や出所を落とす除去が無い (A5・B5) | 実在ファイル名又は WP の位置指定を括弧から除く (許可に当たれば P は緑) | **監査照合 (固定スクリプト)**: 最後の `cs8_removed_tokens.py` の出力の `REMOVED` 行と §17.4 の除いた語の一覧が 1 行ずつ一致し、各行に意味と出所が残る根拠がある |
| 31 | HTTP の status・error code を含む削除文 | 3 桁のステータス番号又はエラーコード語彙を含む文を 1 つ消す | **監査照合**: §17.4 の監査一覧 (草案では削除文 0) |
| 32 | 変えた docstring の backslash (§10.2) | 非該当 (`092e1a1` の 2 module の docstring に `\` は 0 件) — **監査照合**: 変えた docstring に `\` が無いことを HEAD で確かめる | — |
| 33 | `security/CONTROL_MAPPING.md` の 2 module への位置参照を引き直した | 引き直した 1 件を基準の値に戻す | 機械では赤にならない — **監査照合**: `repull.py` の出力 (`unresolved 0`、exit 0。Y8-3 の裁定を反映した後) を §17.4 に逐語で貼り、引き直した各行について基準の行と HEAD の行の内容が一致し、主張の文の差分が 0 で、版が 1 つ上がっている |
| 34 | conformance の `control_plane.py` への位置参照が行数の範囲内 | `conformance-tests/test_c14_authority_boundary.py:747` の `MitateDB-api/src/mitatedb_api/control_plane.py:1322` を行数の外 (例: `:9322`) にする | `conformance-tests/test_conformance_docstring_position_refs.py::test_every_real_conformance_tests_position_reference_resolves_or_is_allowlisted` |
| 35 | root gate を通過し、コミット後の HEAD で `tools/tests` が緑 | **監査照合**: `gate.py` と `finalize.py --tools-tests` の出力の行、コミット後の `pt.py … tools/tests` の集計行 | — |
| 36 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

**道具 4 本** (§16.3 の本文をそのまま使う。`cloud-out/cs8/` に置いたファイルは §16.3 の fenced block から取り出し、次の置き換えだけをした。中身の規則は変えていない)

| ファイル | §16.3 からの置き換え |
|---|---|
| `cs8_apply.py` | docstring と `_die` の接頭辞の `cs7_apply` → `cs8_apply`、`change set 7` → `change set 8` |
| `repull.py` | 置き換えなし (2 module を `--` の後に並べて渡す) |
| `cs8_cli_red.py` | `BASE = "<BASE>"` → `"092e1a1"` (着手時に `<BASE>`)、`MODULES` を 2 module に、名前 `cs7_cli_red` → `cs8_cli_red`、`change set 7` → `change set 8` |
| `cs8_removed_tokens.py` | `--base` の既定 `"<BASE>"` → `"092e1a1"` (着手時に `<BASE>`)、`DEFAULT_PATHS` を 2 module に、名前と `change set` の表記 |

(§16.3 のとおり全文を本節に写すか、`cloud-out/cs8/` のファイルを `$SP` に置いて本節は置き換え表だけにするかは、監督が決める。)

**検証コマンドと期待形** (`WT` は監督が割り当てる worktree、`<基点>` は `<BASE>`。Bash の timeout 600000、前景で直列)

```bash
tools/dev/pt.py -C "$WT" -- r2db-api/tests -q              # 前と後 (40a)。failed/skipped/xfailed 0、前後で passed 数一致
tools/dev/pt.py -C "$WT" -- MitateDB-api/tests -q          # 前と後 (40a)。同上
tools/dev/pt.py -C "$WT" -- conformance-tests/test_control_mapping_register.py conformance-tests/test_conformance_docstring_position_refs.py -q   # 前と後
tools/dev/pt.py -C "$WT" -- tools/tests -q                 # failed 0
python3 "$SP/cs8_apply.py" -C "$WT" --spec "$SP/cs8-spec-platform_declarations.json"
python3 "$SP/cs8_apply.py" -C "$WT" --spec "$SP/cs8-spec-control_plane.json"
python3 "$SP/repull.py" <基点> security/CONTROL_MAPPING.md -- r2db-api/src/r2db_api/platform_declarations.py MitateDB-api/src/mitatedb_api/control_plane.py   # cwd = $WT。exit 0、unresolved 0 (Y8-3 の後)
tools/dev/pt.py -C "$WT" -- "$SP/cs8_cli_red.py" -q        # apply と repull の後、変異の前: 25 passed
tools/dev/mutate.py "$SP/cs8-mutations.json" -C "$WT"      # 変異 1 項目に test 1 つ、expect: red
python3 "$SP/cs8_removed_tokens.py" -C "$WT"               # exit 0、WS-ONLY・UNPAIRED 0 行。出力を §17.4 に逐語で貼る
python3 tools/check_comment_provenance.py --base <基点> r2db-api/src/r2db_api/platform_declarations.py MitateDB-api/src/mitatedb_api/control_plane.py   # exit 0
python3 tools/check_comment_provenance.py --register       # exit 0
python3 tools/check_doc_refs.py                            # exit 0
python3 tools/public_value_scan.py <触ったファイル>         # total_flagged=0
tools/dev/gate.py --label cs8 -C "$WT"                     # 監督。run_in_background
tools/dev/finalize.py -C "$WT" --branch <branch> --allow 'r2db-api/src/r2db_api/platform_declarations.py' --allow 'MitateDB-api/src/mitatedb_api/control_plane.py' --allow 'docs/code-history/r2db-api/platform_declarations.md' --allow 'docs/code-history/MitateDB-api/control_plane.md' --allow 'security/CONTROL_MAPPING.md' --allow 'docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md' -m "$SP/msg-cs8.txt" --tools-tests   # 監督。gate の通過後
tools/dev/pt.py -C <統合後の main の worktree> -- tools/tests -q   # 監督。コミット後の HEAD
```

**実装担当への注意**: §16.3 と同じ (下請けの Agent を使わない、Edit / Write が拒否されたら Bash の python heredoc、折り返しを付け直さない、`cs8_apply.py` を当て直すたびに `repull.py` を続けて実行、spec は JSON なので `\` は `\\`、迷った塊は基準のまま残し根拠欄に書く、報告には道具の出力行をそのまま貼る)。加えて、本草案の spec を基点 `<BASE>` でそのまま当て直し、判定表 (`cloud-out/cs8/judgement-*.md`) を §17.4 の本文に写してから、Y8-3〜Y8-6・Y8-13 の裁定を spec に反映する。

**使用テンプレート**: **2** → **5** → **6**。**変更クラス**: **D** (2 module の整理は B、`security/CONTROL_MAPPING.md` の経路で D)。**規模**: **L** (コードレビューは 1 巡目を観点 A / B の 2 起動並列。§1.7 の 50a)。

### 17.4 候補一覧・判定表・記録 (実装担当が埋め、監督がコミット前に確定する)

範囲・数え方・区分・「HEAD の状態」の書き方は §13.4・§14.4・§16.4 と同じ。各表の「WP」列は `8` (Y8-1 で分けたときは `8a` (r2db) / `8b` (MitateDB))。**草案の中身は `cloud-out/cs8/judgement-platform_declarations.md`・`judgement-control_plane.md` (判定表 A・B・C、参照先一覧、検査器が拒んだ除去、見送った除去、指示語チェックの候補一覧、HTTP の監査一覧、0d で残った文、訂正の記録) にあり、実装担当が本節に写して、基点 `<BASE>` の実測で「HEAD の状態」の行番号を取り直す。**

**変異の対象** (着手時に選ぶ。Y7-8。下は草案の案。CH-ID と行は草案の spec のもの)

| WP | 変異 (完了条件) | ファイル / 塊 (基点の行) | CH-ID | 当てる文字列 (先頭の数語) |
|---|---|---|---|---|
| 8 | c1 (1) | `MitateDB-api/src/mitatedb_api/control_plane.py` / `_check_rate` のコード (塊の外) | — | `raise LimitError(` 相当の literal 1 文字 (着手時に行を取る) |
| 8 | c2 (2) | `docs/code-history/MitateDB-api/control_plane.md` / CH-0926 の節 | CH-0926 | `# Phase 4 WP-3(b) (design D-5): `audit_query`'s own default/maximum page` |
| 8 | c3a (3) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L1301-1305 | CH-0937 | `never a second, independently-configured copy` の `never` |
| 8 | c3b (3) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L1464-1482 の第 2 段落 (保護参照を含まない残した 2 文を入れ替える) | CH-0939 | `This is not a dead end: …` / `self-rotate is deliberately NOT extended …` |
| 8 | c3c (3) | `r2db-api/src/r2db_api/platform_declarations.py` / L685-692 | CH-0863 | `never every database on the cluster` |
| 8 | c3d (3) | `r2db-api/src/r2db_api/platform_declarations.py` / L909-952 | CH-0864 | `# PostgreSQL role this deployment's own processes pool connections against` |
| 8 | c4 (4) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L1523-1529 | CH-0940 | `(SI-10)` |
| 8 | c5 (5) | `r2db-api/src/r2db_api/platform_declarations.py` / L75-77 | CH-0861 | `# history: CH-0861` |
| 8 | c6a (6) | `r2db-api/src/r2db_api/platform_declarations.py` / L75-77 | CH-0861 | `# history: CH-0861` |
| 8 | c6b (6) | `docs/code-history/r2db-api/platform_declarations.md` / CH-0866 の節の前 (孤児の節を足す) | CH-0997 (足す) | `## CH-0866` |
| 8 | c7 (7) | `docs/code-history/r2db-api/control_main.md` / r2db の受け皿 (CH-0504 の節の前に CH-0925 を足す) | CH-0925 (重複) | `## CH-0504` |
| 8 | c8 (8) | `MitateDB-api/src/mitatedb_api/control_plane.py` / モジュール先頭 (import の後) | — | 着手時に行を取る |
| 8 | c10a (10) | `r2db-api/src/r2db_api/platform_declarations.py` / `read_platform_declarations` の中 (L500-535。登録 helper だが変異先としてだけ) | — | `os.environ` を含むコメント 1 行 |
| 8 | c15 (15) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L1311-1320 (`check_rate` の docstring。CH なし) | なし | `Public wrapper around `_check_rate` …` |
| 8 | c16 (16) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L128-148 の `(`docs/design/PHASE5_…_V1.md` §3 D-3, …)` を含む文 | CH-0927 | `The accepted value is an operator responsibility, …` |
| 8 | c17 (17) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L96-99 (ラベル削除後の先頭) | CH-0926 | `# `audit_query`'s own default/maximum page` |
| 8 | c18 (18) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L1-37 の第 1 文 | CH-0925 | `(design v1.2 R-6/R-7)` |
| 8 | c20 (20) | `r2db-api/src/r2db_api/platform_declarations.py` / L75-77 | CH-0861 | `#: This peer's own module path` → `# This peer's …` |
| 8 | c21a (21) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L128-148 | CH-0927 | `control_` + 改行 + `requests_per_minute` (基準の折返し) |
| 8 | c21b (21) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L1024-1035 | CH-0932 | `control_endpoints.audit_query.` + 改行 + `semantics` |
| 8 | c21c (21) | `r2db-api/src/r2db_api/platform_declarations.py` / L1037-1089 | CH-0865 | `` `<...>_api`/`<...>_controlplane`/`<...>_ `` + 改行 + `` auditreader` `` |
| 8 | c22a (22) | `docs/code-history/MitateDB-api/control_plane.md` / CH-0944 の節の fenced block の末尾 | CH-0944 | `this WP closes.` |
| 8 | c22b (22) | 非該当の見込み (CH を付けた塊に、折り返しで割れた実在パスを含むラベルが無い。着手時に確認) | — | — |
| 8 | c23 (23) | `docs/code-history/r2db-api/platform_declarations.md` / CH-0860 の節の fenced block | CH-0860 | 3 桁の R 番号 (本書に書かない) |
| 8 | c28 (28) | `MitateDB-api/src/mitatedb_api/control_plane.py` / L984-986 | CH-0931 | `# same reasoning as `applications_count_locked`` |
| 8 | c29 (29) | `r2db-api/src/r2db_api/platform_declarations.py` / L1037-1089 の第 2 段落 (ラベル `design D-3 (5): ` を戻した後、同じ形の除去 = MitateDB L1578-1582 の `design D-3 (4): `) | CH-0865 / CH-0941 | `design D-3 (5): ` |
| 8 | c30 (30) | `r2db-api/src/r2db_api/platform_declarations.py` / L909-952 の括弧 (WP の位置指定 `WP-4e` を括弧から除く) | CH-0864 | `(following the WP-4e conformance investigation's own finding` |
| 8 | c34 (34) | `conformance-tests/test_c14_authority_boundary.py` / L747 | — | `control_plane.py:1322` → `:9322` |

**監査スクリプトの出力** (`cs8_removed_tokens.py`。実行ごとに 1 行の見出しと出力全体を逐語で。草案の実行 1 は `cloud-out/cs8/checks.md` §4 — 最終の spec、基点 `092e1a1`、`--head` 省略、`SUMMARY ch_blocks=27 ws_only=0 unpaired=0 removed_rows=31`)

**位置参照の引き直しの出力** (`repull.py`。草案の dry-run は `cloud-out/cs8/checks.md` §5 — r2db `changed 22, unresolved 0, not applied 0`、MitateDB `changed 33, unresolved 1, not applied 0`。続けて引き直した各行の「基点の行の内容 = HEAD の行の内容」の確認を書く)

**指示語チェックの候補一覧 / 塊をまたぐ参照先一覧 / HTTP の監査一覧 / 0d で残った文 / 訂正の記録**: `cloud-out/cs8/judgement-*.md` の同名の表を写す (草案: 削除した文 0、訂正の記録 0)。

**除いた語の一覧** (完了条件 30。草案の `cs8_removed_tokens.py` の `REMOVED` 31 行と同じ順)

| # | 塊 (基点の行) | CH-ID | 種類 | 除いた語 | 回数 | 意味と出所が残る根拠 |
|---|---|---|---|---|---|---|
| 1 | L1-60 (r2db) | CH-0860 | id | `WP-6a` | 1 | `process_ceilings` の括弧の追加時期。残る文は WP-6a を指さず、L94-99 の塊が自分で `Phase 10 WP-6a` を持つ。保護参照 (実在パス 2 本、SI-10、F-12) は不変 |
| 2 | L420-432 (r2db) | CH-0862 | id | `WP-6a` | 1 | F-15 のラベルの括弧 `(Phase 10 WP-6a, design D-5(ii))` の追加時期。残る文の `work order WP-6a's own §3 D-5(ii)` が自分で位置を指す。F-15・`design D-5(ii)` は残る |
| 3 | L909-952 (r2db) | CH-0864 | id | `WP-4f` | 1 | F-16 のラベルの括弧の追加時の WP。残る `WP-4e`・`see that WP's report` は WP-4e を指す。F-16 と `0007/0006` は残る |
| 4 | L1037-1089 (r2db) | CH-0865 | id | `D-3` | 1 | 設計名の無い裸の ID のラベル `design D-3 (5): `。残る段落は乗算の理由を自分で述べる。`0013_role_connection_limits.sql`・F-16 は残る |
| 5 | L1037-1089 (r2db) | CH-0865 | id | `WP-8a` | 1 | floor の括弧の追加時期 `, Phase 10 WP-8a`。意味 (floor の式) は残る |
| 6 | L1-37 (MitateDB) | CH-0925 | id | `WP-4` | 1 | 版数付き文書名の括弧 `(design v1.2 R-6/R-7, WP-4)` の枝番付き経緯トークン。R-6/R-7 は保護で残る |
| 7 | L96-99 (MitateDB) | CH-0926 | id | `D-5` | 1 | ラベル `Phase 4 WP-3(b) (design D-5): ` の裸の ID。残る文は契約 `AuditQueryRequest.limit` を出所にする |
| 8 | L96-99 (MitateDB) | CH-0926 | id | `WP-3` | 1 | 同じラベルの経緯トークン |
| 9 | L128-148 (MitateDB) | CH-0927 | id | `M-5` | 1 | `(WP-0 M-5; …)` の裸の ID。残る文は M-5 を名指ししない。`docs/design/PHASE5_…_V1.md` §3 D-3 (実在パス) は残る |
| 10 | L128-148 (MitateDB) | CH-0927 | id | `WP-0` | 1 | 同じ括弧の経緯トークン |
| 11 | L128-148 (MitateDB) | CH-0927 | id | `WP-4` | 1 | 同じ括弧の末尾の経緯トークン |
| 12 | L950-958 (MitateDB) | CH-0930 | id | `D-5` | 1 | ラベル `Phase 10 WP-6b (design D-5 (ii) region (iii)): ` の裸の ID。残る文は in-memory backend に lock が要らない理由を自分で述べる |
| 13 | L950-958 (MitateDB) | CH-0930 | id | `WP-6b` | 1 | 同じラベルの経緯トークン |
| 14 | L984-986 (MitateDB) | CH-0931 | id | `WP-6b` | 1 | ラベル `Phase 10 WP-6b: `。残る文は L950-958 の理由を `above` で指す |
| 15 | L1024-1035 (MitateDB) | CH-0932 | id | `D-5` | 1 | ラベル `Phase 4 WP-3(b) (design D-5): `。残る文は契約 `control_endpoints.audit_query.semantics` を出所にする |
| 16 | L1024-1035 (MitateDB) | CH-0932 | id | `WP-3` | 1 | 同じラベルの経緯トークン |
| 17 | L1051-1063 (MitateDB) | CH-0933 | id | `D-6` | 1 | 括弧 `(Phase 4 D-6/N-3)` (`/` 結合の裸 ID)。文は `used to … are now …` で現在の仕組みを述べ、`0007_platform_declarations.sql` は残る |
| 18 | L1051-1063 (MitateDB) | CH-0933 | id | `N-3` | 1 | 同じ括弧 |
| 19 | L1158-1161 (MitateDB) | CH-0934 | id | `WP-3` | 1 | ラベル `Phase 4 WP-3(b): `。残る文は L1024-1035 を `above` で指す |
| 20 | L1247-1253 (MitateDB) | CH-0935 | id | `D-2` | 1 | ラベル `Phase 6 WP-3 (design D-2): `。残る文は composition root からの注入を自分で述べる |
| 21 | L1247-1253 (MitateDB) | CH-0935 | id | `WP-3` | 1 | 同じラベル |
| 22 | L1288-1296 (MitateDB) | CH-0936 | id | `D-5` | 1 | ラベル `Phase 10 WP-6b (design D-5 (ii)): `。残る文は既定 1 と実呼出し元を述べる |
| 23 | L1288-1296 (MitateDB) | CH-0936 | id | `WP-6b` | 1 | 同じラベル |
| 24 | L1301-1305 (MitateDB) | CH-0937 | id | `WP-5` | 1 | ラベル `WP-5: `。残る文は accessor の理由を述べる |
| 25 | L1391-1400 (MitateDB) | CH-0938 | id | `WP-3` | 1 | ラベル `Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 1): ` (丸ごと。17.5 Y8-4)。残る文は bearer の境界を述べる |
| 26 | L1464-1482 (MitateDB) | CH-0939 | id | `M-1` | 1 | 第 2 段落のラベル `Phase 3.5 WP-5 (design §4 M-1): ` (17.5 Y8-5)。C-15 と allow-list の文は残る |
| 27 | L1464-1482 (MitateDB) | CH-0939 | id | `WP-5` | 1 | 同じラベル |
| 28 | L1464-1482 (MitateDB) | CH-0939 | id | `§4` | 1 | 同じラベル (設計の節番号。設計名は基準から無い) |
| 29 | L1523-1529 (MitateDB) | CH-0940 | id | `O-1` | 1 | ラベル `追補 4 O-1: `。残る文は SI-10 を自分で持つ |
| 30 | L1578-1582 (MitateDB) | CH-0941 | id | `D-3` | 1 | ラベル `design D-3 (4): `。残る文は `ceiling <= 1` の規則を述べる |
| 31 | L1967-1979 (MitateDB) | CH-0943 | id | `WP-5` | 1 | ラベル `Phase 3.5 WP-5: ` (17.5 Y8-3: CONTROL_MAPPING.md:574 が先頭行を指す)。gate の理由は残る |

**判定表** (A. 全塊、B. 目印一覧に当たる文、C. 安全上の理由・保護参照・位置): `cloud-out/cs8/judgement-platform_declarations.md` (A 32 行、B 7 行、C 10 行) と `judgement-control_plane.md` (A 83 行、B 16 行、C 39 行) を写す。

**復元・欠番の裁定と範囲の再走査** (完了条件 29): 草案では、検査器が拒んだ 8 除去 (r2db 1 編集、MitateDB 7 塊) を spec から外して CH-ID を詰め直した (まだ commit 前なので欠番にしていない。Y8-7)。着手後の裁定ごとにここへ足す。

**内容の除去が 0 の塊の検査** (完了条件 28): 草案 `WS-ONLY` 0 行 (`SUMMARY ch_blocks=27 ws_only=0 unpaired=0 removed_rows=31`)。

**変異の記録** (`tools/dev/mutate.py`): 未実行 (クラウドでは流さない)。

**記録** (草案の値。「後」は spec を当てた作業ツリーの実測、基点 `092e1a1`)

| 項目 | r2db `platform_declarations.py` | MitateDB `control_plane.py` |
|---|---|---|
| CH-ID を付けた塊 / 対象の塊 | 7 / 32 | 20 / 83 |
| 使った CH-ID | `CH-0860`〜`CH-0866` (欠番なし。`CH-0867`〜`CH-0924` は未使用の予約) | `CH-0925`〜`CH-0944` (欠番なし。`CH-0945`〜`CH-0989` は未使用の予約) |
| 経緯トークン (前 → 後、`_HISTORY_TOKEN_PATTERNS` を全文に当てた数) | 48 → 30 | 150 → 114 |
| 日付を含む行 (前 → 後) | 13 → 6 (残る 6 行: 第 1 段落の `2026-09-05` (検査器が拒んだ)、登録 helper の中 L254・L279・L709、L950 の `measured 2026-09-10`、L997 (登録 helper)) | 5 → 0 |
| 削除した文 | 0 (除いたのは括弧内の経緯トークン 3 か所、裁定の日付句 2 か所、純粋な日付 2 か所、ラベル 1 か所、括弧ごと 1 か所、計 11 編集) | 0 (除いたのは文頭ラベル 13 (丸ごと)、括弧内の経緯トークン 3、括弧ごと 1、裁定の日付句 5、計 20 編集 (CH-0929 の 1 編集は日付句)) |
| 行数 (前 → 後) | 1,737 → 1,748 (+11: 参照 7 本 = コメント 5 (`# history:` 1 行) + docstring 2 (3 行) で +11、除去に接する行の切り直しで ±0 (CH-0861 で −1、CH-0860 で ±0)) — 着手時に取り直す | 2,274 → 2,309 (+35: コメント 12 (1 行) + docstring 8 (3 行) = +36、切り直しで −1) — 着手時に取り直す |
| `#:` の行 (前 → 後) | 70 → 69 (Y8-11) | 0 → 0 |
| `security/CONTROL_MAPPING.md` の位置参照 | 22 件 (`changed 22, unresolved 0`) | 34 件 (`changed 33, unresolved 1` — L1967、Y8-3) |

| 照合コマンド / suite | 草案 (クラウド。出力の行を逐語) |
|---|---|
| `pt.py … r2db-api/tests -q` 前 / 後 | 未実行 |
| `pt.py … MitateDB-api/tests -q` 前 / 後 | 未実行 |
| `pt.py … conformance-tests/test_control_mapping_register.py conformance-tests/test_conformance_docstring_position_refs.py -q` 前 / 後 | 未実行 |
| `pt.py … tools/tests -q` | 未実行 |
| `pt.py … cs8_cli_red.py -q` (変異の前) | 未実行 (pytest なし。CLI 3 本の exit 0 は直接確認) |
| `tools/dev/mutate.py …` | 未実行 |
| `check_comment_provenance.py --base 092e1a1 …` | `comment provenance OK: 67 blocks checked` / `comment provenance OK: 85 blocks checked` (exit 0) |
| `check_comment_provenance.py --register` | `comment provenance register OK: 95 files scanned, 542 CH-IDs` (exit 0) |
| `check_doc_refs.py` | `check_doc_refs OK: 0 dangling references` (exit 0) |
| `public_value_scan.py <触ったファイル>` | exit 0 (`checks.md` §3) |
| `gate.py --label cs8` | 未実行 |

**完了条件ごとの結果**: 実装担当が §16.4 の表と同じ形で埋める (草案では機械照合の 1〜8・15〜23・33 の変異を流していない)。

### 17.5 監督裁定の欄 (草案は決めず、選択肢と根拠の実測を並べる)

| # | 論点 | 選択肢と実測 |
|---|---|---|
| Y8-1 | WP の分け方 | 対象 115 塊 (r2db 32 / MitateDB 83)、spec の CH 塊 27 (7 / 20)、編集 31。(A) 1 WP で 2 module (変更セット 5 は 123 塊 / 40 CH、変更セット 6 は 113 塊 / 9 CH を 1 WP で行い、変更セット 7 は 205 塊を 2 WP に分けた (Y7-1 の閾値は「変更セット 3〜5 の平均 117 塊の 1.8 倍」))。(B) module ごとに 2 WP (8a = r2db、8b = MitateDB。基点の取り直しと `security/CONTROL_MAPPING.md` の版上げが 2 回になる。レビューの戻しが module の中に留まる)。(C) 1 WP だが受け皿・spec は module ごと (草案の形。spec と受け皿は既に module ごとに分かれている) |
| Y8-2 | 変更クラス | 2 module の整理は Class B。`security/CONTROL_MAPPING.md` の位置参照を引き直す (r2db 22、MitateDB 34) ので Y7-2 のとおり経路により Class D。前例は §14.5 R6-4 の残り、変更セット 7 |
| Y8-3 | `repull.py` の `unresolved` (`security/CONTROL_MAPPING.md:574`) | SI-03 MitateDB-api の主張「Revoke-gate role filter and issuance freeze apply from the start on this peer …」が `control_plane.py:1967` (基点。塊 L1967-1979 の先頭行 `# Phase 3.5 WP-5: filtered to `role == "control"` rows only --`) と `:605` を指す。草案の CH-0943 がこの行のラベルを除くので対応が取れない (Y7-15)。(A) 除去を残し、主張の参照を除去後の同じコメントの先頭行 (作業ツリー L2000 `# filtered to `role == "control"` rows only --`) に監督が手で引き直す (主張の文は変えない)。(B) 除去を残し、参照をコメントの次のコードの行 (`active_ids = [...]` の行) に引き直す。(C) CH-0943 を spec から外し、塊を基準のまま残す (`unresolved 0` になる。経緯トークン 1 が残る) |
| Y8-4 | 文頭の `Phase 6 WP-3 差し戻し 最終ラウンド (supervisor ruling 2026-09-04, 裁定 1): ` (MitateDB L1391-1400、CH-0938) | 草案はラベルごと除いた (条件 1〜3 を満たし、残る文は bearer の境界を自分で述べる。検査器は許した)。同じ日付句を持つ L346-369 (CH-0928)・L868-882 (CH-0929) は文頭でない (第 1 段落のラベルが残る。(ii)) ので `supervisor ruling 2026-09-04, ` だけを除いた。(A) 草案のまま (3 塊で除去の形が違う)。(B) 3 塊とも日付句だけ (CS6 R6-1 と同じ縮小。L1391 のラベルに経緯トークン 3 が残る) |
| Y8-5 | 文頭でない位置のラベル `Phase 3.5 WP-5 (design §4 M-1): ` (MitateDB L1464-1482 の第 2 段落、CH-0939) | 第 1 段落は `Allow-list (never a deny-list, design's own explicit warning): ` で始まる主題文で、WP・設計のラベルではないと判定した (変更セット 7 差し戻し 2 の `Pass 1:` と同じ扱い)。(ii) の境界例。(A) 草案のまま。(B) 除去を外す (経緯トークン 2 と裸の ID 1 が残る) |
| Y8-6 | r2db L1037-1089 (CH-0865) の第 2 段落のラベル `design D-3 (5): ` | 設計名の無い裸の ID のラベルで、CS7 CH-0600 (`design D-3 (1): `) と同形。ただし MitateDB の対の docstring (CH-0550、`docs/code-history/MitateDB-api/platform_declarations.md`) は `design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5):` と設計名付きで残っている (実在パスで保護)。(A) 草案のまま除く (r2db 側には設計名が基準から無い)。(B) 除去を外し、peer 間で同じ段落の形を保つ |
| Y8-7 | CH-ID の予約と欠番 | 監督の指示は r2db CH-0860〜、MitateDB CH-0925〜。草案は 65 ずつ (`CH-0860`〜`CH-0924`、`CH-0925`〜`CH-0989`) に切り、CH-0860〜CH-0866 と CH-0925〜CH-0944 を使った。検査器が拒んだ 7 塊を外したときは commit 前なので番号を詰め直した (Y7-16 は commit 後の戻しに欠番を使う)。着手後にレビューで戻した塊は欠番にし詰めない。並行 worktree が CH-0860〜CH-0989 を使っていないことは着手条件 3 で取り直す (草案時は `git worktree list` に worktree 1 つ) |
| Y8-8 | 新規の受け皿 `docs/code-history/r2db-api/platform_declarations.md` の見出し行 | `cs8_apply.py` (= `cs7_apply.py`) は新規の受け皿を `## CH-0860` から書き始め、見出し行を書かない。変更セット 5・6 の新規の受け皿は `# src/… -- code-comment history (change set N)` と `Companion for … per docs/code-history/README.md.` の 2 行を持ち、変更セット 6 で作られた `docs/code-history/MitateDB-api/control_plane.md` は持たない。`--register` はどちらでも通る。(A) 見出し 2 行を監督が手で足す (道具は変えない)。(B) 無しのまま |
| Y8-9 | 対象外の線引き | r2db: `_ISOMORPHIC_TARGETS` の 59 symbol の node の中の塊 35 (docstring 34 / comment 1 (L529-535、`read_platform_declarations` の中)) を対象外にした。symbol の直前のコメント塊 (`#:` の定数のコメントなど、node の外) は対象 (同型性テストは `ast.get_source_segment(node)` を比べるのでコメントは比較に入らない)。`check_role_connection_limits` (L1037-1089、L1093-1101) は表に無く対象。MitateDB: `_take_bound_advisory_lock` の docstring 1 塊と CH-0543 (L1586-1616。変更セット 6 の塊。0j の経路) を対象外にした。(A) このまま。(B) `#:` の定数のコメント (r2db L75-148、L900-905、L954-970、L1025-1027、L1547-1550。登録 symbol の直前に付く) も対象外にする (草案は L75-77 を CH-0861 として除去した) |
| Y8-10 | 完了条件 10 (文字列検査) | r2db は `r2db-api/tests/test_process_ceilings_declaration.py:839-840` の `not in` (`validate_process_ceilings_value`・`read_platform_declarations` の `getsource`) が該当。2 関数は登録 helper で本件は塊を触らないが、module を文字列として読むので変異 (a) (`os.environ` を含むコメントを 1 行足す) を対応させる案。MitateDB は非該当 (`read_text` は `ast.parse` に通す)。(A) 該当とし変異 1 つ。(B) 非該当 (触らない関数の中なので) とし監査照合だけ |
| Y8-11 | 完了条件 20 (`#:` の行) | CH-0861 (r2db L75-77) は `#:` の折り返し 2 行目 `#: ruling 2026-09-03).` ごと消え、`#:` の行は 70 → 69。検査器 (0g の `#:` の規則) は通った。(A) このまま (`#:` の行頭記号は残り、行が減るだけ)。(B) 除去を外す |
| Y8-12 | 経緯トークン 0 で裸の ID だけのラベル・括弧 (`D-6:`、`D-5 M-4:`、`R-6:`、`R-2 choke point`、`(P35-D7, …)` など。MitateDB に多い) | 設計 §3 は「出所を持たない裸の局所 ID」を「移す」に分類するが、草案はこれらを基準のまま残した: 設計の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓 (i) の精神)。また経緯トークン 0 の塊に CH-ID を付けると「内容の除去」が ID だけになる。(A) 草案のまま残す。(B) 裸の ID のラベルも (6) で除く (塊数が増える。判定表 A の既定の根拠を書き換える) |
| Y8-13 | r2db L909-952 (CH-0864) の `Phase 10 WP-4f, ` | 草案は裁定の日付句 `supervisor ruling 2026-09-09, ` と一緒に `Phase 10 WP-4f, ` (F-16 を足した WP) も除いた。CS6 CH-0512 の同形の括弧では日付句だけを除いた (R6-1 の縮小の時期)。残る `WP-4e` は `see that WP's report` が指すので残す。(A) 草案のまま。(B) `Phase 10 WP-4f` を残す |

**却下した代替案** (草案)

| 案 | 却下の理由 |
|---|---|
| 検査器が拒んだ 7 塊のラベルを、括弧の中の語だけ除く形に直す | `§4/§1-E`・`P35-D6`・`(ii)/(iii)`・`review m-6` は (4) の消してよい語に当たらず、残る形が種類語や断片になる |
| `Phase 3.5` を含む括弧 (L1225 など) から `WP-5` だけ除く | `(Phase 3.5, §1-D/§4)` が残り、意味が薄れる。`Phase 3.5` は `Phase 3` + `.5` に割れて消せない |
| 経緯だけの文 (`Phase 4 WP-3(b) (design D-5/D-6).` L2052、`Phase 4 WP-3(b) (design D-5's own JSON shape, …).` L1634) を (3) で削除する | 残る文の `(D-5 M-4)` が裸の `D-5` で寄りかかる (i) |
| `cs8_apply.py` に新規の受け皿の見出し行を書かせる | 道具は §16.3 の本文のまま使う (変えたい点は報告に書く)。Y8-8 |
