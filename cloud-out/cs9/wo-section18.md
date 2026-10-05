# 作業指示書 §18 の草案 — 変更セット 9 (wo-section18.md)

**版数行に足す行** (`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の先頭の箇条書きに足す 1 行。日付は作業機で確定する):

- **v1.15 (2026-10-0X)**: §18 に変更セット 9 (r2db `structured.py` と MitateDB `platform_declarations.py`。WP の分け方は §18.5) の manifest と、監督裁定 Y9-1〜Y9-N (§18.5) を追記した。既存の節は書き換えていない。

以下が本文の草案。基点は `092e1a1` (このセッションの checkout の `origin/main`、fetch 後)。作業機の local main が先に進んでいれば §18.1 の着手条件 2 で取り直す。設計の規則は言い換えず節番号で指す。裁定は決めず §18.5 に選択肢と実測を並べた。

---

## 18. 変更セット 9 — r2db `structured.py` と MitateDB `platform_declarations.py`

正本設計は v0.29 (§3、§4、§5、§6、§8、§9 (0d〜0h)、§9.2、§9.3、§10.4〜§10.9)。行番号と実測は `092e1a1` の値 (2 module の blob は `<BASE>` と同じであることを着手条件 2 で確かめる)。共通の規則は §13.3・§14.3・§16.3 を指し、ここには差分だけを書く。設計 §6 の優先 1 (R-37 の抽出対象 module) の残りである r2db `structured.py` と、優先 2 のうち既存の受け皿を持ち `security/CONTROL_MAPPING.md` の位置参照が多い MitateDB `platform_declarations.py` を 1 つの変更セットにする (WP の分け方は Y9-1)。

### 18.1 着手条件

| # | 条件 |
|---|---|
| 1 | 変更セット 7 の WP-7b (設計 §10.9 の次の候補) が main に統合されている (`092e1a1` で統合済み)。その main の先頭を基点 `<BASE>` とする |
| 2 | `r2db-api/src/r2db_api/structured.py` と `MitateDB-api/src/mitatedb_api/platform_declarations.py` の blob が `092e1a1` と `<BASE>` で同じ (`git rev-parse 092e1a1:<path> <BASE>:<path>`)。違えば §18.2 の実測、spec の `line`・`line_range`、`cs9_cli_red.py` の `BASE`、`cs9_removed_tokens.py` の `--base` の既定を `<BASE>` で取り直す (内容の一致する行の対応で機械的に) |
| 3 | 着手時に、並行 branch・worktree (`git worktree list`、`tools/dev/ledger.py --open` の進行中の行) と台帳 R-37 の残件が、本節の触るファイル (2 module、`docs/code-history/r2db-api/structured.md`、`docs/code-history/MitateDB-api/platform_declarations.md`、`security/CONTROL_MAPPING.md`) に触れないことを取り直す。重なりがあれば実装前に監督へ上げる (§1.2 の 16)。CH-ID と `security/CONTROL_MAPPING.md` の版は各 worktree の未コミットの差分まで見て重ならない番号を取る (設計 §10.8 の教訓) |
| 4 | 着手時に設計 §5 (b) の grep と §18.2 の静的テストの注記を取り直す |
| 5 | WP を分ける場合 (Y9-1)、後の WP は前の WP の commit・完了ゲート・main への merge の後に着手し、基点を統合後の main で取り直す |

### 18.2 選定と実測 (`092e1a1`)

数え方は §13.2・§14.2・§16.2 と同じ。計測は `$SP/cs9_measure.py` (`check_comment_provenance` を import して `092e1a1` の blob に当てた。登録 helper の表は ast で読んだ)。全文と塊ごとの値は `cloud-out/cs9/measure.md`・`judgement-*.md` (本草案の付属) にある。

| 項目 | r2db `structured.py` | MitateDB `platform_declarations.py` | 計 |
|---|---|---|---|
| 行数 | 1,867 | 1,713 | 3,580 |
| 塊 (`extract_all_blocks`) | 122 (docstring 17 / comment 105) | 67 (docstring 38 / comment 29) | 189 |
| 対象外: 登録 helper の中 | 6 (L114-123、L136-163、L589-604、L610-631、L647-661、L695-702。すべて docstring。symbol 6 = `enum_member_matches_type`、`validate_enum_declaration`、`normalize_request_for_plan`、`compute_plan_token`、`normalize_request_for_idempotency`、`idempotency_digest`) | 35 (symbol 60 のうち中に塊を持つ node 34。docstring 34 + comment 1 (L503-509)) | 41 |
| 対象外: 既存の CH-ID | 13 (CH-0552〜CH-0564、L1603-1840。台帳 R-42) | 1 (CH-0550、L1011-1064) | 14 |
| **対象の塊** | **103** (docstring 11 / comment 92、653 行) | **31** (docstring 3 / comment 28、319 行) | **134** |
| 経緯トークン (module 全文 / 対象の塊の中) | 112 / 94 | 42 / 24 | 154 / 118 |
| うちトークンを含む対象の塊 | 60 塊 (457 行) | 9 塊 (175 行) | 69 |
| 日付を含む行 (全文 / 対象の塊) | 3 / 3 (L310、L584、L641) | 15 / 8 (L23、L44、L72、L529、L661、L888、L917、L1068) | 18 / 11 |
| 目印一覧に当たる文 / 塊 (対象の塊だけ) | 17 / 17 | 8 / 6 | 25 / 23 |
| 塊をまたぐ参照の語を含む文 | 63 | 12 | 75 |
| 経緯トークンを含む文のうち 安全 / 保護参照 / 位置 | 17 / 37 / 34 文 (安全の塊 17) | 5 / 6 / 3 文 (安全の塊 4) | — |
| `#:` の行 | 0 | 103 (対象の塊に 18 塊) | 103 |
| 10 行以上の塊 (CH なし、対象の塊) | 18 塊 / 253 行 | 6 塊 / 189 行 | 24 / 442 |

- `--register` (基点): `comment provenance register OK: 95 files scanned, 515 CH-IDs`。`--base 092e1a1 <2 module>` (無変更): `comment provenance OK: 189 blocks checked` (exit 0)。
- 受け皿は既存の `docs/code-history/r2db-api/structured.md` (13 節、訂正 4 件) と `docs/code-history/MitateDB-api/platform_declarations.md` (1 節、訂正 1 件) に追記する。

**10 行以上の塊**・**目印一覧に当たる文を持つ塊**・**経緯と同じ文にある安全上の理由**: `measure.md` §1 の一覧 (本文には写さない。実装担当は判定表 B・C に展開する)。

**塊をまたぐ参照先**: `judgement-*.md` の「塊をまたぐ参照先一覧」に全件 (module の中、両 peer の `src/`・`tests/`・`conformance/`、`conformance-tests/`、`security/`。§13.2 の正規表現に `'s identical comment`・`<名前> below|above`・`own (comment|docstring|paragraph)` を足して grep した)。要点: r2db `postgres.py:1765`・`:1783`・`:2273` が `ApplicationCell.transact`/`apply_schema`'s identical comment で L1129-1135・L1077-1085・L1505-1514 を指す。r2db `tests/test_dry_run_and_plan.py:332` が L1039-1069 の第 2 段落 (`A plain apply pays no …`) を指す。`structured.py` L906・L1277 の `module docstring's own documented divergence` の指す先は module docstring (1 行) に**無い** (移動前からの穴)。MitateDB では L60-65・L887-920・L941-945 が `this module's own docstring/header` で L1-47 を指す。登録 helper の中から対象の塊を指す文: `structured.py` 0、`platform_declarations.py` は `_table_owner`・`check_contract_170_declarations`・`check_control_surface_consistency` の docstring が対象の塊の周辺 (M-1、L758-797、L525-530) を指す (除去で指す先を失わない)。

**静的テストの注記** (Y7-10 と同じ手順)

| 箇所 | 扱い |
|---|---|
| 行番号 pin (L1 scan) | r2db `tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` は `("postgres.py", 1948)` の 1 行で、`test_backend_layer_allowlist_is_confined_to_postgres_py` が module を `postgres.py` に固定する。`structured.py` の `(module, lineno)` pin は 0 件。件数 pin `"structured.py": 48` は `_fail_call_sites` (ast) の数でコメントに依らない。MitateDB の `_BACKEND_LAYER_ALLOWLIST` は `backend_postgres.py` だけ (17 行)、`platform_declarations.py` の pin は 0 件。40b は非該当 (`pins.md`) |
| 文字列の検査 (設計 §5 (b)) | 2 module を文字列として読む検査は 0 件。`ast.parse`・`compile` を通すものを除いた: `MitateDB-api/tests/test_ops_startup_checks.py::_load_module` (L304、`<ref>:platform_declarations.py` を `compile`+`exec`。`_f16_agrees_on_row`・`_f18_agrees_on_row` が呼ぶ)、`r2db-api/tests/test_process_ceilings_declaration.py:839` (`getsource` を **r2db の** `platform_declarations.py` に `not in`。`test_declaration_table_is_the_only_source_no_env_fallback`。本変更セットの module ではない)、`MitateDB-api/tests/test_r113_multi_process_wiring.py:435` (`getsource(ApplicationCell._limit_gate)`、cell.py)、`tools/tests/test_sql_statement_safety_scan.py`・`test_leaf_import_direction.py` (module 名の集合だけ) |
| 同型性の表 | 登録 helper 6 + 60 個の node の中の塊 41 は対象外 (Y7-5 と同じ)。`_ISOMORPHIC_TARGETS` に触れない |

**2 module を指す位置参照の所在** (`092e1a1`。全件は `measure.md` §3 と `tools/posrefs.txt`)

| 所在 | 件数 | 扱い |
|---|---|---|
| `security/CONTROL_MAPPING.md` → `structured.py` | 12 (パス付き 11 + 続きの形 `` `:1599` `` 1。指す行: 178-179、884、1145、1599、1796、568、1807、22、1784、995)。**指す行がコメント・docstring の行であるもの 1**: `:1246` の `structured.py:1807` (comment L1803-1812) | 引き直す。L1803-1812 の塊は (iv) で基準のまま残す (`repull.py` の `unresolved` を出さない) |
| `security/CONTROL_MAPPING.md` → MitateDB `platform_declarations.py` | 15 (パス付き 13 + 続きの形 `` `:1348` ``・`` `:1325` `` 2。指す行: 1145×2、474、440、1005×2、1239×4、1348、1325、1493、1562、719)。コメント・docstring の行を指すもの 0。r2db の同名ファイルへの 22 件はすべてパス付きで、`repull.py` は書き換えない (basename だけの形 0) | 引き直す |
| `conformance-tests/` → `structured.py` | 3 (`test_c20_constraint_declaration_agreement.py:154`・`test_c22_dry_run_and_plan.py:186` の `:1821` (comment L1820-1827 の行)、`test_c05_limit_declaration_agreement.py:555` の折返し `structured.py:` + `923`) | 触らない。範囲内に留まることを完了条件 34 で確かめる (`test_conformance_docstring_position_refs.py`) |
| README (root・両 peer)、両 peer の `docs/` | 0 | — |
| r2db `tests/` 4、MitateDB `tests/` 1、r2db `conformance/` 3 行 (すべて basename だけ `structured.py:N`。うち `conformance_adapter_r2db.py:319`・`:1031` の `:2269`/`:2294`/`:2697`/`:2718` は行数 1,867 を超え移動前から古い) | 8 行 | 触らない |
| `docs/` (記録) 187 出現、`security/CONTROL_MAPPING_HISTORY.md` 0 | — | 触らない (記録) |

**起草時の確認**: §16.3 の 4 本から基点・module・CH-ID の範囲だけ置き換えた道具を基点の作業ツリーに当て、`cs9_removed_tokens.py` は `SUMMARY ch_blocks=0 ws_only=0 unpaired=0 removed_rows=0` (exit 0。既存の CH-0552〜CH-0564・CH-0550 は Y7-12 の 2 行で読み飛ばす)。spec を当てた照合の値は `checks.md`。

### 18.3 Manifest

**目的**: §13.3 と同じ (2 module の経緯を受け皿へ移し、コードに現在の理由と `CH-NNNN` を残す)。範囲は Y7-3、対象外は Y7-5 を 2 module に当てる。

**module ごとの違い** (同じ内容は下に 1 回だけ書く)

| 項目 | r2db `structured.py` | MitateDB `platform_declarations.py` |
|---|---|---|
| 基点 (`--base`、spec の `base`/`parent`、`cs9_cli_red.py` の `BASE`、`cs9_removed_tokens.py` の `--base`) | `<BASE>` | `<BASE>` (WP を分けるなら前の WP 統合後の main) |
| 範囲 (spec の `line_range`) | `[1, 1867]` (module 全体) | `[1, 1713]` (module 全体) |
| 対象の塊 / 判定表が最低限覆う範囲 | 103 / 目印 17 文 + 安全 17 塊 | 31 / 目印 8 文 + 安全 4 塊 |
| 登録 helper (spec の `excluded_symbols`) | 6 (上の表) | 60 (`_ISOMORPHIC_TARGETS` の `src/mitatedb_api/platform_declarations.py` の行の symbol。ast で読む) |
| CH-ID 予約 (spec の `ch_range`) | `CH-0990`〜`CH-1059` | `CH-1060`〜`CH-1129` |
| spec / 変異 spec | `$SP/cs9-spec-structured.json` / `$SP/cs9a-mutations.json` | `$SP/cs9-spec-platform_declarations.json` / `$SP/cs9b-mutations.json` |
| 受け皿 | `docs/code-history/r2db-api/structured.md` (追記) | `docs/code-history/MitateDB-api/platform_declarations.md` (追記) |
| 完了ゲート | `tools/dev/gate.py --label cs9a -C "$WT"` | `--label cs9b` (1 WP なら `cs9`) |
| `security/CONTROL_MAPPING.md` | 版を 1 つ上げる (主張の文は変えない。版数は finalize の直前に main の版数行を見て決める。Y7-13) | 同じ (別 WP なら次の版) |

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/structured.py`、`MitateDB-api/src/mitatedb_api/platform_declarations.py` (**コメントと docstring だけ**。対象の塊だけ)、`docs/code-history/r2db-api/structured.md`、`docs/code-history/MitateDB-api/platform_declarations.md` (追記だけ)、`security/CONTROL_MAPPING.md` (2 module への位置参照の行番号と先頭の `Version:` の行だけ)、本書 §18.4 | 他の `src/` 全部、`tools/`、`tools/tests/`、両 peer の `tests/` (L1 scan を含む。pin 0 件)、両 peer の `conformance/`、`conformance-tests/`、README・両 peer の `docs/`、`security/` の他のファイル、他の受け皿、`docs/code-history/pair.md`、`docs/design/`、台帳、`_ISOMORPHIC_TARGETS`、r2db の `platform_declarations.py` (同名の相手 peer) |

| 項目 | 内容 |
|---|---|
| 変更クラス・規模 | 2 module の整理は Class B。`security/CONTROL_MAPPING.md` の位置参照を引き直すので経路により **Class D** (Y7-2 と同じ)。規模 **L** (§1.13 の 74)。Class D の証拠の扱いは §16.3 と同じ (設計 = `docs/design/CODE_COMMENT_PROVENANCE_V1.md` v0.29、契約版数 据え置き、設計レビュー = 規模 L の 1 回、完了ゲート = WP ごとに全部、依頼者裁定の逐語 = 台帳 R-22 行の事後確認、版付きの決定 = `security/CONTROL_MAPPING.md` の `Version:` の行) |
| 必須の規律 | §13.3 の「必須の規律」「保護文 (0d) と訂正 (0g)」「改行」と、§14.3 の「判定表の置き場所」「復元・欠番の裁定の後」「内容の除去が 0 の塊」「意味や出所を落とす除去」と同じ。範囲・除去の条件は Y7-3、折り返しは Y7-4。加えて、レビューが戻した型 (i)〜(iv) を除去のたびに確かめる: (i) 同じ塊に残る文が、除くラベル・括弧の名指す設計・WP に寄りかかっていないか (設計名の無い `design §n`、裸の `D-n`、`this WP`、`same commit`、`finding n`)、(ii) 文頭でない位置のラベルを除くと、後ろの文が前に残ったラベル・見出しの段落の続きに読めないか、(iii) ラベルの中に内容語が無いか (現行の区分名・規則名は残す)、(iv) `security/CONTROL_MAPPING.md` が指すコメント・docstring の行そのものを変えない (`structured.py` L1803-1812) |
| 編集の道具 (Y7-7) | `$SP/cs9_apply.py -C "$WT" --spec <spec>` (§16.3 の `cs7_apply.py` の本文のまま。置き換え表は下)。spec の 1 塊と §18.4 の判定表の 1 行を対応させる |
| 位置参照の引き直し (Y7-2) | `cs9_apply.py` を当てた後、worktree の根を cwd にして `python3 "$SP/repull.py" <基点> security/CONTROL_MAPPING.md -- r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py` (§16.3 の `repull.py` の本文のまま)。出力を §18.4 に逐語で貼る。`unresolved` が出たら書き換えずに止める (Y7-15)。相手 peer の同名ファイル `r2db-api/src/r2db_api/platform_declarations.py` への参照が 1 件も書き換わらないことを出力で確かめる |
| 統合 | §16.3 と同じ |
| 手順 | 設計 §6「手順」。40a は両 peer の suite と conformance 2 ファイルを前後 2 回 (実装担当)。`conformance-tests/` の全体は監督の完了ゲート (Y7-14) |

**完了条件 ↔ 変異** (P = `check_comment_provenance.py --base <基点> r2db-api/src/r2db_api/structured.py MitateDB-api/src/mitatedb_api/platform_declarations.py`、R = `--register`、D = `check_doc_refs.py`。変異は `tools/dev/mutate.py` で実コードに当てる (設計 §10.2)。変異の対象行は着手時に選び §18.4 に記録する (Y7-8。下の「変異の対象の案」が草案)。赤が P・R・D の行は wrapper `$SP/cs9_cli_red.py` の node `test_cli_red[c<行><枝>]` を mutate の `tests` に書く。1 項目に test は 1 つ。1〜13 は設計 §6 の表の逐語)

| # | 完了条件 | 変異 (`file:操作`) | 赤になるもの |
|---|---|---|---|
| 1 | コード不変 | コード 1 行の literal を 1 文字変える | §4.1 (1) — `c1` |
| 2 | 移した塊が逐語で在る | 受け皿の節から 1 文を消す | §4.1 (2) — `c2` |
| 3 | 文区間の削除だけ | (a) 残した文から否定語を落とす (b) 残した 2 文を並べ替える (c) 1 語足す (d) 残した文の途中の折返し行を 1 行消す | §4.1 (3) — `c3a`〜`c3d` |
| 4 | 括弧内の削除が規則どおり | 括弧内の現行正本の参照 (例: SI-) を消す | §4.1 (4) — `c4` (checker は (4) の違反を (3) の行で出す) |
| 5 | 経緯を足していない | 追加行に `WP-` を含める | §4.1 (5) — `c5` |
| 6 | ID の解決と孤児 | コード側 ID を存在しない番号にする / 参照されない節を足す | §4.2 の 1 — `c6a`・`c6b` (孤児の節の番号は両 module の予約範囲の外から取る。例 `CH-1997`。手本の `CH-0997` は r2db の範囲の中) |
| 7 | ID の全体一意 | 他 peer の companion に同じ番号の節を足す | §4.2 の 2 — `c7` |
| 8 | docstring 依存の新設なし | `src/` に `__doc__` の読み出しを 1 行足す | §4.2 の 5 — `c8` |
| 9 | 行番号 pin が実測と一致 | allowlist を更新前の値に戻す | L1 details AST scan — **非該当** (2 module の `(module, lineno)` pin は 0 件。`pins.md`)。**監査照合**: HEAD で両 peer の allowlist に 2 module の行が無く、`"structured.py": 48` が不変 |
| 10 | 文字列検査が効いたまま (該当時) | §5 (b) の向きごとの変異 | 該当 test — **非該当** (2 module を文字列として読む検査 0 件。§18.2 の注記)。**監査照合**: 着手時の grep の取り直し |
| 11 | 登録 helper が同形 (最後の変更セット) | 一方の peer だけ整理する | `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` — 非該当 (「最後の変更セット」限り) |
| 12 | 非空虚 (変更セット 1) | `MIN_CH_IDS` を 0 に戻し、全 ID を消す | 監査照合: 定数の値を差分で確認 — 非該当 (「変更セット 1」限り) |
| 13 | suite 集計と経緯トークン数の前後 | 監査照合 (両 peer の集計行とトークン数を manifest に残す) | — |
| 14 | 対象外の塊に触れていない (登録 helper 6 + 35、既存 CH-ID 13 + 1。Y7-5) | **監査照合**: `git diff <基点> -- <2 module>` に 55 塊の行が無く、`_ISOMORPHIC_TARGETS` の差分 0 | — |
| 15 | CH の無い塊を変えていない | 2 module のどちらか: CH を付けずに 1 塊から 1 文消す | P exit 1 (§4.1 (2)) — `c15` |
| 16 | 保護参照を含む文は丸ごと消せない (0d) | CH-ID を付けた塊にある保護参照を含む文を 1 つ丸ごと消す (文は §18.4 に記録) | P exit 1 (§4.1 (3)) — `c16` |
| 17 | ラベル削除が規則どおり (§8) | ラベルを消し、区切りの後ろの先頭文字を小文字化する (区切りの後ろが文字で始まる塊で大小を変える) | P exit 1 (§4.1 (3)) — `c17` |
| 18 | 版数付き文書名は残る | CH-ID を付けた塊から版数付き文書名の版数を消す (文は §18.4 に記録) | P exit 1 (§4.1 (3)) — `c18` |
| 19 | 訂正の記録が規則どおり (0g) | (a) 記録の旧文を基準に無い文にする (b) 新文から保護参照を 1 つ消す | (a)(b) P exit 1 — `c19a`・`c19b`。受け皿に既存の記録が在る (structured.md 4、platform_declarations.md 1)。基点の記録を変える変異 (a) の赤は `FAIL (§9.3 (2))` (checks.md で実測)。作業ツリーにだけ在る pending の記録なら `FAIL (§9f)`。wrapper の CASES の接頭辞は変異の対象に合わせる (Y9-N) |
| 20 | `#:` の行を保つ (0g) | CH-ID を付けた `#:` の塊の `#:` を `#` にする | P exit 1 (§9f) — `c20`。該当 (MitateDB の CH の `#:` 塊 L77-82、L862-883。checks.md で実測) |
| 21 | 改行の壊れが 0 件 | `find_broken_line_wrap_joins` を流す。変異: (a) `id ASC` 型をつなぐ (b) `/` の直後の改行を空白 1 つでつなぐ (c) backtick の span の中の折返しを空白 1 つでつなぐ | 0 件であること。(a) P exit 1 (§4.1 (3)) — `c21a`、(b)(c) P exit 1 (§9e) — `c21b`・`c21c` |
| 22 | 受け皿が原文の写しとして完全 | (a) 受け皿の fenced block の末尾を 1 語切り詰める (b) 折り返しで割れた実在パスを含むラベルを、パスの後半ごと削る | (a) P exit 1 (§4.1 (2)) — `c22a`、(b) **非該当** (spec で CH-ID の付く塊のラベルに折り返しで割れた実在パスは 0。本文中の CH-1034 の `` `test_constraints_declaration.py` `` はラベルではない。checks.md) — **監査照合**: 最後の spec で取り直す |
| 23 | 受け皿の ID が `check_doc_refs` で解決 | 受け皿の fenced block に台帳に無い R 番号を 1 つ足す (3 桁。番号は本書に書かない) | D exit 1 — `c23` |
| 24 | 指示語・定冠詞・副詞の参照先を消していない | 残す文の点検語が参照する文を削除する | 機械では赤にならない — **監査照合**: §18.4 の候補一覧とコードレビュー |
| 25 | 安全上の理由と同居する文を残している | §18.2 (measure.md) の一覧の文を文ごと削除する | 機械では赤にならない — **監査照合**: 判定表の根拠とレビュー |
| 26 | 塊をまたぐ参照先の文を残している | §18.2 の参照先 (例: L1039-1069 の `A plain apply pays no …`、L788-798) の文を削除する | 機械では赤にならない — **監査照合**: grep の結果と §18.4 の参照先一覧 |
| 27 | 判定表が対象を覆い、本書の本文にある (§10.4) | **監査照合**: 対象の塊の全件 (103 + 31) が §18.4 の判定表に 1 塊 1 行であり、目印一覧に当たる文 (17 / 8) と安全上の理由の塊 (17 / 4) が根拠・点検語の欄に空欄なく載る。表が本書の外にしか無ければ未達 | — |
| 28 | 内容の除去が 0 の塊に CH-ID が無い (§10.4) | この変更セットで CH-ID を付けた塊の 1 つを空白だけの差にする (基点が既に持つ CH-ID の塊は監査スクリプトが読み飛ばすので対象にしない。Y7-12) (P は緑) | **監査照合 (固定スクリプト)**: `cs9_removed_tokens.py` の出力に `WS-ONLY` 行が 1 行でもある、又は exit 1 なら赤。出力は §18.4 に逐語で貼る |
| 29 | 復元・欠番の裁定の後に範囲を走査した (§10.4) | 1 塊で戻した除去と同じ種類の除去を、範囲の別の塊に 1 つ残す | **監査照合 (固定スクリプト)**: 裁定のたびに `cs9_removed_tokens.py` を再実行した出力が §18.4 にあり、残した除去が `REMOVED` 行として出て判定表で扱われている。再実行の出力が無い裁定は赤 |
| 30 | 意味や出所を落とす除去が無い (A5・B5) | 実在ファイル名又は WP の位置指定を括弧から除く (許可に当たれば P は緑) | **監査照合 (固定スクリプト)**: 最後の `cs9_removed_tokens.py` の出力の `REMOVED` 行と §18.4 の除いた語の一覧が 1 行ずつ一致し (不一致は赤)、各行に意味と出所が残る根拠がある |
| 31 | HTTP の status・error code を含む削除文 | 3 桁のステータス番号又はエラーコード語彙を含む文を 1 つ消す | **監査照合**: §18.4 の監査一覧の各行が判定表で根拠付きで「経緯だけの文」と判定されている |
| 32 | 変えた docstring の backslash (§10.2) | 非該当 (spec で変えた docstring に `\` は 0。checks.md) — **監査照合**: 変えた docstring に `\` が無いことを HEAD で確かめる | — |
| 33 | `security/CONTROL_MAPPING.md` の 2 module への位置参照を引き直した (Y7-2) | 引き直した 1 件を基準の値に戻す | 機械では赤にならない — **監査照合**: `repull.py` の出力 (`unresolved 0`、exit 0) を §18.4 に逐語で貼り、引き直した各行について基準の行と HEAD の行の内容が一致し、主張の文の差分が 0 で、版が 1 つ上がっている。r2db の `platform_declarations.py` への参照の差分 0 |
| 34 | conformance の docstring の `structured.py` 参照が行数の範囲内 (Y7-2) | `conformance-tests/test_c20_constraint_declaration_agreement.py` の `structured.py:1821` を行数の外 (例: `structured.py:9821`) にする | `conformance-tests/test_conformance_docstring_position_refs.py::test_every_real_conformance_tests_position_reference_resolves_or_is_allowlisted` (L766。折返しの `:923` は同ファイルの `test_pin_the_one_remaining_line_wrapped_position_reference_in_the_real_corpus` L789) |
| 35 | root gate を通過し、コミット後の HEAD で `tools/tests` が緑 | **監査照合**: `gate.py` と `finalize.py --tools-tests` の出力の行、コミット後の `pt.py … tools/tests` の集計行 | — |
| 36 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

**道具 (置き換え表)** — 4 本の本文は §16.3 のまま使い、全文は写さない。`cloud-out/cs9/tools/` に置き換え後の写しがある (`cs9_build_spec.py`・`cs9_dbless_checks*.py`・`cs9_gen_docs.py` は本草案の作業用で、作業指示書の道具ではない)。

| 道具 | §16.3 の名 → 本節の名 | 置き換えた箇所 (それ以外は変えない) |
|---|---|---|
| 編集の道具 | `cs7_apply.py` → `cs9_apply.py` | docstring の名と使用例 (module `r2db-api/src/r2db_api/structured.py`、companion `docs/code-history/r2db-api/structured.md`、`excluded_symbols` の例、`ch_range` `["CH-0990", "CH-1059"]`、例の `CH-0990`)、`_die` の接頭辞 `cs9_apply:`。spec は module ごとに 1 つ (`module`・`companion`・`excluded_symbols`・`line_range`・`ch_range` を module の値に) |
| 位置参照の引き直し | `repull.py` | 置き換え 0 (引数で 2 module を渡す) |
| CLI の赤の wrapper | `cs7_cli_red.py` → `cs9_cli_red.py` | docstring、`BASE = "<BASE>"`、`MODULES` を 2 module の list。CASES は手本のまま (c19a の接頭辞は Y9-N) |
| 監査スクリプト | `cs7_removed_tokens.py` → `cs9_removed_tokens.py` | docstring、`DEFAULT_PATHS` を 2 module の list、`--base` の既定 `<BASE>` |

**変異の対象の案** (着手時に実装担当が確定して §18.4 に記録する。CLI で赤を確かめたものは checks.md に出力が在る。2 module を 1 つの P で検査するので、変異は spec を当てた状態の作業ツリーに当てる)

| 変異 (完了条件) | ファイル / 塊 (基点の行) | CH-ID | 当てる文字列 (先頭の数語) | CLI 確認 |
|---|---|---|---|---|
| c17 (17) | `structured.py` / L246-253 (ラベル除去後の先頭) | CH-0995 | `# symmetric with `bind_mutation`'s identical` → `# Symmetric …` | `FAIL (§4.1 (3))` 赤、別の FAIL 0 |
| c21a (21) | `structured.py` / L246-253 | CH-0995 | `This is a shape check (contract` → `shapecheck` | `FAIL (§4.1 (3))` 赤 |
| c21b (21) | `structured.py` / L1039-1069 (`` `transaction`/ `` の直後の改行) | CH-1014 | `(`entity`/`operations`/`transaction`/` + 改行 + `` `budget` `` を空白 1 つでつなぐ | `FAIL (§9e)` 赤 |
| c21c (21) | `structured.py` / L470-484 (`` `alter_ `` + 改行 + `` field` ``) | CH-1002 | `` `alter_ field` `` | `FAIL (§9e)` 赤 |
| c29 (29) | `structured.py` / L579-585 の見出しの `(D-4)` (A) 又は L1146-1152 の `, D-3 (2)` (B) — 基準のまま残した「裸 ID だけの括弧」と同じ種類の除去を 1 つ残す向き | CH-1004 / CH-1019 | `# --- contract 1.7.0 dry_run/plan (D-4) ---` → `(D-4)` を除く | 検査器は緑のまま、`removed_rows=50` → `51` |
| c20 (20) | `platform_declarations.py` / L77-82 (`#:` 塊) の 1 行目 | CH-1062 | `#: the platform single-shot migration` → `# the …` | `FAIL (§9f)` 赤 |
| c19a (19) | `docs/code-history/r2db-api/structured.md` / CH-0552 の訂正 1 の `old` | CH-0552 (既存) | `(only the LATER deadline-check/audit-hook points below restore `before_*`)` → `` `after_*` `` | `FAIL (§9.3 (2))` 赤 (手本の `§9f` ではない) |
| c23 (23) | `structured.md` の fenced block (CH-0552 の節) | — | 3 桁の R 番号を足す (本書に書かない) | `check_doc_refs FAILED: 1 dangling reference(s)` |
| c15 (15) | `structured.py` / L306 (CH なしの 1 行の塊) | なし | `# (a) a name field_types declares that `fields` never named.` を消す | `FAIL (§4.1 (2))` 赤 |
| c22b (22) | 非該当 (実測: ラベルに折り返しで割れた実在パスを持つ CH 塊 0) | — | — | — |
| c1〜c8、c16、c18、c22a、c28、c30、c34 | 手本と同じ形で着手時に選ぶ (c16・c18 は CH-1014 の第 1 文 `` `dry_run`/`plan`/`plan_request` (contract 1.7.0, D-4): `` が候補。c34 は `conformance-tests/test_c20_constraint_declaration_agreement.py:154` の `structured.py:1821`) | — | — | 未実測 |

**検証コマンドと期待形**: §16.3 と同じ。`cs7` を `cs9` に、module を 2 つに、`--allow` に 2 module・2 受け皿・`security/CONTROL_MAPPING.md`・本書を置く。`cs9_cli_red.py` は変異の前に `25 passed`。

**実装担当への注意**: §16.3 と同じ。加えて: `#:` の塊は行頭記号を保つ (0g 6。`cs9_apply.py` は `# history:` 行を足す)。spec の `old` に日本語を含む行を書くときは、検査器の CJK 連結の正規化 (§9 0h 条件 9) で `依頼者裁定 案(a)` が `依頼者裁定案(a)` になり、日付だけの除去は基準から導けない (checks.md の拒否 2 件)。版数付きの括弧に `/` (`(2)/(4)`、`S-a/S-j`) や `=` (`U-3 = (A)`) が在ると、検査器は括弧内の 1 語の除去を受け付けない (同 7 件)。

### 18.4 候補一覧・判定表・記録 (実装担当が埋め、監督がコミット前に確定する)

範囲・数え方・区分・「HEAD の状態」の書き方は §16.4 と同じ。各表の「module」列に `structured` / `platform_declarations` を書く。**本草案では枠だけを置き、照合の値は埋めない** (草案の照合の値は `cloud-out/cs9/checks.md`・`judgement-*.md` に在り、作業機が取り直す)。

**変異の対象** (着手時に選ぶ。Y7-8): §16.4 と同じ列 (`| module | 変異 (完了条件) | ファイル / 塊 (基点の行) | CH-ID | 当てる文字列 (先頭の数語) |`)。

**監査スクリプトの出力** (`cs9_removed_tokens.py`。実行ごとに「実行 N (最初 / 裁定 #n の後、実行時刻、`--head`)」の 1 行と、出力全体を逐語で入れたコードブロック)。

**位置参照の引き直しの出力** (`repull.py`。出力全体を逐語で。続けて引き直した各行の「基点の行の内容 = HEAD の行の内容」の照合と、r2db の `platform_declarations.py` への参照の差分 0 の確認)。

**指示語チェックの候補一覧** (削除した文 1 つにつき 1 行): `| # | module | 塊 (基点の行) | 削除した文 (先頭の数語) | 直後の残す文 1 | 直後の残す文 2 | 点検語の参照 | 結果 |`

**塊をまたぐ参照先一覧** (行番号は基点。「残っているか」は HEAD の実物。§18.2 の参照表の全行と、「確定」の行の確定先): `| # | module | 参照元 (`file:line`) | 参照の語 | 参照先 (`file:line`) | 参照先の文 (先頭の数語) | 残っているか |`

**HTTP の status・error code を含む削除文の監査一覧**: `| # | module | 塊 | 削除した文 (先頭の数語) | 含む語 | 判定表の根拠 |`

**0d の保護参照があるために残った、経緯だけの文**: `| # | module | 塊 (行) | 文 (先頭の数語) | 保護参照 | HEAD の状態 |`

**訂正の記録 (0g)**: `| # | module | ファイル:行 (CH-ID) | 旧文 (先頭の数語) | 新文 (先頭の数語) | 今のコードとの食い違い (根拠 `file:line`) |`

**除いた参照** (位置参照と塊をまたぐ参照のうち、除去で指す先が変わったもの。無ければ「該当なし」): `| # | module | 参照元 | 除いた語 | 指していた先 | 扱い |`

**除いた語の一覧** (完了条件 30。最後の監査スクリプトの出力の `REMOVED` 行と同じ順で 1 行ずつ一致させる): `| # | module | 塊 (基点の行) | CH-ID | 種類 | 除いた語 | 回数 | 意味と出所が残る根拠 |`

**判定表** (A. 全塊。対象の塊 1 つにつき 1 行。spec の `blocks` の各項目が 1 行に対応し、spec に無い行は「基準のまま」。CH-ID の無い塊も「基準のまま」で載せる): `| # | module | 塊 (基点の行) | qualname | 種別 | 拾った理由 (目印 / 安全 / 保護参照 / 位置 / 参照先) | spec の CH-ID | 除いた語句 (spec の `old` → `new`) | HEAD の状態 | 判定 (§3) | 根拠 | 削除前の確認 (指示語・副詞・直後の 2 文。設計 §3) | 除去後の文を読んだ判定 | 点検語 |`

B. 目印一覧に当たる文 (structured 17 文、platform_declarations 8 文。完了条件 27): `| # | module | 塊 (基点の行) | CH-ID | 目印 | 文 (先頭の数語) | HEAD の状態 | 判定 (§3) | 根拠 | 点検語 | A の行 |`

C. 経緯と同じ文にある安全上の理由・保護参照・位置 (§18.2 の 17 + 4 塊と、保護参照・位置だけの塊): `| # | module | 塊 | CH-ID | 種別 | HEAD の状態 | 判定 (§3) | 根拠 (その塊の安全上の理由・保護参照が残ること) | 点検語 | A の行 |`

D. 復元・欠番にした塊 (CH-ID を外し、受け皿の節を消した。番号は詰めない): `| # | module | 塊 (基点の行) | 旧 CH-ID | 前回の除去 | 戻した根拠 | HEAD の状態 |`

**復元・欠番の裁定と範囲の再走査** (完了条件 29): `| # | module | 裁定 (塊、内容) | 走査の基準 | 走査した範囲 | 結果 | 再実行の `SUMMARY` 行 (逐語) |`

**文頭でない位置のラベル除去の全件** (完了条件 29 の (ii)。塊の基準の本文で除去の位置の前を手で読む): `| # | module | 塊 (CH-ID、基点の行) | 除去したラベル | 除去の位置 | 直前に残る段落・文のラベル・見出し | 判定 |`

**ラベルの中の内容語の走査** ((iii)。ラベルを除いた全編集): `| # | module | 塊 (CH-ID、基点の行) | 除いたラベル | 内容語 | module 内の他の出現 (現行の区分名・規則名か) | 判定 |`

**作業ノートの参照の残し** (`{scratchpad}/…`・`scratchpad/…` で HEAD に残る行): `| # | module | 行 (基点) | 置き場 (対象の塊 / 登録 helper) | 残した理由 |`

**内容の除去が 0 の塊の検査** (完了条件 28): `| module | CH-ID の塊 (`ch_blocks`) | `WS-ONLY` 行の数 | `SUMMARY` 行 (逐語) |`

**変異の記録** (`tools/dev/mutate.py`。実行時刻とログのファイル名で書く): `| # | module | 変異 (完了条件) | 期待 | ログ (実行時刻 / ファイル) | ログの行 (逐語) |`

**記録**: §16.4 と同じ 2 表 (CH-ID を付けた塊 / 対象の塊、使った CH-ID と欠番、経緯トークンの前後、削除した文、行数の前後、`CONTROL_MAPPING.md` の版と引き直した参照の数; 照合コマンド / suite の出力行)。

**完了条件ごとの結果** (36 項目。変異の行は上の変異の記録): `| # | 変異 | 結果 |`

### 18.5 監督裁定の欄 (起草時の論点。決めない — 選択肢と実測を並べる)

| # | 論点 | 選択肢と実測 |
|---|---|---|
| Y9-1 | WP の分け方 (対象の塊 134 > 130) | (a) module で分ける (WP-9a = `structured.py` 103、WP-9b = `platform_declarations.py` 31。spec・受け皿・`repull.py` の対象が 1 ファイルずつ。版上げ 2 回)。(b) 1 WP (CS5・CS6 の前例 113〜123 塊。編集した塊は 42 = 36 + 6 で CS7 の 1 WP と同じ規模)。(c) `structured.py` を `ApplicationCell` の `def` 行 (L746) で割る + MitateDB (58 / 45 / 31、3 WP)。measure.md §5 |
| Y9-2 | 裸の ID だけのラベル・括弧 (経緯トークン 0) の扱い | 草案は全部を基準のまま残した (`structured.py` 20 塊: `Ruling N-1: ` L272・L549、`R-5: ` L532・L1364、`(R-5)` L754、`m-9: ` L821、`Ruling I-6…: ` L830・L844・L1115、`R-7, corrigendum M-9: ` L898・L1357、`L-6/M-6: ` L1093・L1522、`Ruling I-3/I-8…: ` L1102・L1531、`D-4 (4)/(6): ` L1172、`m-5: ` L1290、`R-4, corrigendum M-2: ` L1403、`M-6: ` L1538、`D-4 (3)/(4): ` L1820、見出しの `(D-4)` L579、`(D-3 (2))` L1146)。検査器は `(D-4)` の括弧ごとと `, D-3 (2)` の除去を受け付ける (c29 の実測、checks.md)。選択肢: (a) 残す (設計の決定を指す唯一の手掛かり)、(b) 依頼の文言どおり `design D-n (m): `・`追補 n X-m: ` の形だけ除く (該当 0。`D-4 (4)/(6): `・`D-4 (3)/(4): ` は "design" の語を持たない)、(c) 残る文が寄りかからない裸 ID のラベル・括弧を全部除く (約 20 塊、CH-ID が増える) |
| Y9-3 | 第 2 段落のラベル `Review round F-5 (`{scratchpad}/rulings-r4.md`): ` (L1039-1069、CH-1014) と、同じ段落の第 2 文の `Review round F-5: ` (L1573-1580) | 草案は (ii) で見送った (直前の段落 / 文のラベル `(contract 1.7.0, D-4):` が残り、F-5 の文が D-4 の記述の続きに読める)。作業ノートの参照 L1063 がこのため残る。検査器は許す (checks.md 実行 5: `comment provenance OK: 189 blocks checked`)。選択肢: (a) 見送り (草案)、(b) 除く ((ii) を受け入れ、残る文は現在の最適化の説明として読める、`tests/test_dry_run_and_plan.py:332` が指す文は残る) |
| Y9-4 | 版数付き括弧に `/`・`=` を含む 7 塊 (L779、L1159、L1195、L1505、L1557、L1573、L1848) の WP 位置指定 | 検査器が (4) の 1 語の除去を受け付けない (`(2)/(4)`・`S-a/S-j`・`(8)/(9)`・`(1)(i)/(3)`・`U-3 = (A)`・`U-1 = (β)`)。同形で `/`・`=` の無い 13 塊は受け付けた。選択肢: (a) 基準のまま残す (草案。CH-1008・CH-1021・CH-1028・CH-1030〜CH-1032・CH-1035 は欠番)、(b) 検査器の `_paren_words_removable` の `/`・`=` の扱いを変更セット 0 系で直してから除く (設計外の拡張。§1.5 の 37 により実装前に上げる)、(c) 台帳の既知の穴として起票し残す |
| Y9-5 | 日付だけの除去を検査器が拒む 4 件 | `(依頼者裁定 2026-09-03 案(a))` ×2 (L584・L641。CJK 連結の正規化で `依頼者裁定 案(a)` が基準から導けない)、`, requester ruling 2026-09-05:` (MitateDB L71-72。括弧の中で `: ` が続く形)、`-- design D-2(f), monitor ruling 2026-09-05.` (MitateDB L529。括弧でもラベルでもない文末)。選択肢: (a) 残す (草案。R6-3 の `(design amendment 2026-09-05, N-7)` と同じ扱い)、(b) `依頼者裁定` を §9 規則 1 の複数語トークンに足す拡張を 0 系で行う |
| Y9-6 | 内容を持つ括弧からの部分除去 4 件 (検査器が受け付けた) | `(coordinator F2, 2026-09-04 review)` → `(coordinator F2)` (L310、CH-0996)、`(no cross-peer sharing, requester ruling 2026-09-03)` → `(no cross-peer sharing)` (MitateDB L43-44、CH-1060)、`(design D-1(c) amendment 2026-09-05)` → `(design D-1(c) amendment)` (L661、CH-1064)、`(Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric …)` → `(peer-symmetric …)` (L888、CH-1066)。設計 §4.1 (4) の本文は「括弧ごと」か「出所と同居なら 1 語」を書き、§9 の一般則 (部位ごとの部分集合) が検査器の受理の根拠。選択肢: (a) 受け入れる (草案。Y7-3 (a) の裁定の日付句)、(b) (4) の本文に合わせて戻す (CH-1060・CH-1064・CH-1066 は欠番になり MitateDB は 3 塊) |
| Y9-7 | 完了条件 19 (a) の接頭辞 | 既存の記録 (基点) の `old` を変える変異は `FAIL (§9.3 (2))`、手本の wrapper は `FAIL (§9f)`。選択肢: (a) wrapper の `c19a` を `FAIL (§9.3 (2))` にする、(b) 作業ツリーにだけ在る pending の記録を足す変異にして `§9f` のまま (記録を足す必要が本変更セットに無い) |
| Y9-8 | 変異 c6b の孤児の節の番号 | 手本の `CH-0997` は r2db の予約範囲の中。範囲外 (例 `CH-1997`) を使う |
| Y9-9 | `security/CONTROL_MAPPING.md` の位置参照 `structured.py:1807` (行 1246) が comment L1803-1812 を指す | 草案は (iv) で塊を基準のまま残した (その塊の `(D-4 (2)/(4), WP-2b)` は Y9-4 の形でもある)。選択肢: (a) 残す、(b) 主張が指すべき行を監督が決めて引き直す (Y7-15) |
| Y9-10 | `conformance-tests/` の `structured.py:1821` ×2 が comment L1820-1827 を指す | 塊は基準のまま (除くものが無い) だが、上の塊の編集で行番号は 1821 → 約 1858 に動く。設計 §3「別件」のとおり触らない (触ると Class C)。範囲内 (1821 ≤ 1906) は完了条件 34 で確かめる |
| Y9-11 | `module docstring's own documented divergence` (L906・L1277) の指す先が無い | 移動前からの穴 (module docstring は 1 行)。本変更セットでは触らない (記録のみ)。選択肢: 0g の訂正記録で指す先 (`inmemory_predicate.py:106` 付近) を書くか、別件で起票 |

**却下した代替案** (起草時): §16.5 と同じ 4 件に加え、(1) 「2 module の対象 134 塊を 130 以下にするため MitateDB を外す」 — 2 module とも既存の受け皿と `security/CONTROL_MAPPING.md` の位置参照 (12 + 15) を持ち、同じ道具で 1 回に扱える。(2) 「ID-only のラベルを機械的に全部除く」 — 設計 §3 の v0.14 (許可であって義務ではない) と依頼の文言 (唯一の手掛かりなら残す) に反する。
