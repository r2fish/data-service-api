# 作業指示書 — コード内経緯コメントの移動 変更セット 0 / 1

- 版数: **v1.0 (2026-09-14)**。起草 v0.1 の疑義 9 件への監督裁定 (同日) を反映した。基点 main `016a0f3`。
- 正本設計: `docs/design/CODE_COMMENT_PROVENANCE_V1.md` (**v0.3**)。以下「設計」。形式は roadmap §9 の 9 の Change Set Manifest。
- 設計の表・裁定・却下案は写さず、節番号で指す。**設計と食い違ったら設計が正。** 訂正は本文を書き換えず §4 に訂正註として追記する (`OPERATING_CONDITIONS.md` §1.8 の 57)。

## 0. 共通

| 項目 | 内容 |
|---|---|
| 規律 | `OPERATING_CONDITIONS.md` §1.3 (19〜27)、§1.4 (28〜31)、§1.5 (32〜40c)、§1.6 (41〜45)、§1.7 (46〜52)。転記しない |
| テンプレート | **2** Sonnet 実装 (コミットしない、git 操作禁止、下請け Agent 禁止) → **5** Opus コードレビュー (報告に無い変異 1〜2 種を自作) → **6** Opus 証拠監査 |
| 変更クラス | 両変更セットとも **B** (roadmap §9 の 8)。`_ISOMORPHIC_TARGETS` の増減が起きたら停止 (設計 §6 末尾) |
| 範囲 | 両 peer の `src/` だけ (設計 §3)。`conformance-tests/` に触れない |
| `tools/tests` | root の `testpaths` の外。**各変更セットのゲートで `pytest tools/tests -q` を明示実行する** (CI は常時 job `tools-tests`) |
| `.md` の事故 | コミット前に `git diff --cached --stat` で追跡 `.md` が 0 バイトでないことを見る |

## 1. 変更セット 0 — 照合ツールと受け皿の規約

**目的**: 設計 §4.1 の差分照合と §4.2 の常設検査を 1 本のツールにし、自己テストを `tools/tests` に置く。`src/` は触らない。

**読む正本**: 設計 §2 D-2〜D-4、§3、§4、§5 (a)(c)、§6。先例: `conformance-tests/test_contract_history_register.py` (companion の見出し集合照合)。

| 触るファイル (新規) | 触らないファイル |
|---|---|
| `tools/check_comment_provenance.py` (標準ライブラリのみ)、`tools/tests/test_comment_provenance.py`、`docs/code-history/README.md` (受け皿の規約を数行: 置き場所・節の形・CH-ID の規則。設計 D-1 / D-2 を指す) | 両 peer の `src/` と `tests/`、`conformance-tests/`、`tools/check_doc_refs.py`、`.github/`、`_ISOMORPHIC_TARGETS` |

**実装の指示**

| # | 内容 |
|---|---|
| 1 | `--base <rev> <src path>...`: 設計 §4.1 (1)〜(5)。旧版は `git show <rev>:<path>`。新旧の塊の対応は CH-ID で取る。合格 `comment provenance OK: N blocks checked` / exit 0、不合格は `FAIL (§4.1 (n)) <path>:<line> ...` を列挙し exit 1 |
| 2 | `--register`: 設計 §4.2 の 1〜6 を作業ツリーに対して行う。不合格は `FAIL (§4.2 n) ...` で exit 1 |
| 3 | 照合 (5) の語は設計 §4.1 (5) の明示リストだけ。R- / L- / D- を入れない。閉じた ID の一覧は受け取らない |
| 4 | `__doc__` / `inspect.getdoc` / `inspect.getsource` の固定集合は **空集合** (実測 2026-09-14、両 peer `src/` で 0 件)。`MIN_CH_IDS = 0` (両 peer 通しの総数) |
| 5 | 自己テストは `tmp_path` に合成リポジトリ (git init、旧版 commit、新版書込み) を作って CLI を呼ぶ。加えて実リポジトリに `--register` を 1 回かけ、走査ファイル数 ≥ 1 を assert する (§1.5 の 32) |
| 6 | `docs/code-history/README.md` は受け皿の走査対象外 (走査は `docs/code-history/<peer>/*.md` と `pair.md`) |

**完了条件 ↔ 変異** (T = `tools/tests/test_comment_provenance.py`。変異はすべて `tools/check_comment_provenance.py` への操作、fixture は設計 §6 の変異)

| # | 完了条件 | 変異 | 赤になる test id |
|---|---|---|---|
| 1 | §4.1 (1) コード行 1 行の変更を検出 | AST 比較を省く | `T::test_code_line_change_is_red` |
| 2 | §4.1 (1) 行送りだけは緑 | `include_attributes=True` にする | `T::test_line_shift_only_is_green` |
| 3 | §4.1 (2) 受け皿から 1 文削除を検出 | byte 比較を省く | `T::test_companion_sentence_deleted_is_red` |
| 4 | §4.1 (2) CH-ID の無い塊の変更を検出 | 対応の無い旧塊の検出を省く | `T::test_changed_block_without_id_is_red` |
| 5 | §4.1 (3) 否定語を落とすと赤 | 比較前に `not` / `never` / `no` を除く | `T::test_negation_dropped_is_red` |
| 6 | §4.1 (3) 文の並べ替えで赤 | 順序保持の判定を集合包含に変える | `T::test_sentence_reorder_is_red` |
| 7 | §4.1 (3) 1 語足すと赤 | 新しい文が旧い文を部分文字列として含めば一致とする | `T::test_word_added_is_red` |
| 8 | §4.1 (3) 折返し行 1 行削除で赤 | 改行でも文を区切る | `T::test_wrapped_line_deleted_is_red` |
| 9 | §4.1 (3) 文単位の削除は緑 | 削除を 1 件でも赤にする | `T::test_sentence_deletion_is_green` |
| 10 | §4.1 (4) 括弧内の SI- の削除で赤 | 括弧内トークンの種別を無視する | `T::test_current_ref_removed_in_parens_is_red` |
| 11 | §4.1 (4) 経緯トークンだけの括弧の削除は緑 | (4) の許可を外す | `T::test_history_only_parens_removed_is_green` |
| 12 | §4.1 (5) 追加行の `WP-` を検出 | (5) を省く | `T::test_added_history_token_is_red` |
| 13 | §4.1 (5) `round trip` は対象外 | `\bround \d+\b` を `\bround\b` にする | `T::test_round_trip_is_not_a_history_token` |
| 14 | §4.2-1 未解決 ID で赤 | 未解決の検出を省く | `T::test_register_unresolved_id_is_red` |
| 15 | §4.2-1 孤児で赤 | 孤児の検出を省く | `T::test_register_orphan_section_is_red` |
| 16 | §4.2-2 両 peer 通しの重複で赤 | 見出しの重複検査を peer ごとにする | `T::test_register_duplicate_across_peers_is_red` |
| 17 | §4.2-3 必須行の欠けで赤 | 必須行の検査を省く | `T::test_register_missing_required_line_is_red` |
| 18 | §4.2-4 参照行の書式外で赤 | 書式の正規表現を大小文字無視にする | `T::test_register_bad_reference_format_is_red` |
| 19 | §4.2-5 docstring 依存の新設で赤 | 固定集合の比較を省く | `T::test_register_new_doc_access_is_red` |
| 20 | §4.2-6 `MIN_CH_IDS` は両 peer 通し | 件数を peer ごとに数える | `T::test_min_ch_ids_counts_across_peers` |
| 21 | 実リポジトリで緑、走査は非空虚 | `src/` ルート定数を空ディレクトリに向ける | `T::test_repository_register_passes` |
| 22 | `MIN_CH_IDS = 0` | **監査照合** — 定数行を grep | — |
| 23 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

**検証コマンドと期待形**

```
./.venv/bin/python -m pytest -q tools/tests          → failed 0 (T は 21 passed 以上)
python3 tools/check_comment_provenance.py --register → exit 0
./.venv/bin/python -m pytest -q r2db-api/tests       → failed/skipped/xfailed 0
./.venv/bin/python -m pytest -q MitateDB-api/tests   → 同上
python3 tools/check_doc_refs.py                      → exit 0
python3 tools/public_value_scan.py <触ったファイル>    → total_flagged=0
監督: root suite 単独 `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` (§1.3 の 19〜23)
```

## 2. 変更セット 1 — r2db `postgres.py` (監督承認 2026-09-14)

### 2.1 選定 (実測 2026-09-14、main `016a0f3`)

設計 §6 の優先 1 から登録 helper を含む module を除き、10 行以上の塊の行数が多い順に並べた。

| 候補 | 経緯トークン | 10 行以上の塊 (件 / 行) | 登録 helper | §5(b) 検査 | 行番号 pin | R-37 の予定 | 判定 |
|---|---|---|---|---|---|---|---|
| MitateDB `cell.py` | 656 | 105 / 2,441 | 4 件 | あり (`test_application_audit.py:1102-1103`) | 0 | WP-3 | 除外 |
| r2db `structured.py` | 270 | 57 / 899 | 6 件 | なし | 0 | WP-3 | 除外 |
| **r2db `postgres.py`** | 182 | **57 / 1,079** | **なし** | なし | 1 (`1706`) | WP-4 (WP-1 抽出済み) | **選定** |
| MitateDB `backend_postgres.py` | 211 | 36 / 829 | なし | なし | 20 | WP-4 (WP-1 抽出済み) | 次点 |
| r2db `service.py` | 185 | 35 / 779 | なし | なし | 0 | WP-3 (WP-1 抽出済み) | — |

- 並行の抽出 branch は無い (起草時)。着手時に再確認する (設計 §6 優先 1 の並行禁止)。
- 注釈・docstring の ID を `check_doc_refs` の族文法で当てた未解決は 0 件 (両 peer `src/` 全体)。

### 2.2 Manifest

**目的**: `r2db-api/src/r2db_api/postgres.py` の経緯を `docs/code-history/r2db-api/postgres.md` へ移し、コードに現在の理由と `CH-NNNN` を残す。

**読む正本**: 設計 §2〜§6。

| 触るファイル | 触らないファイル |
|---|---|
| `r2db-api/src/r2db_api/postgres.py` (**コメントと docstring だけ**)、新規 `docs/code-history/r2db-api/postgres.md`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` (`_BACKEND_LAYER_ALLOWLIST` の行番号の数値だけ。註は足さない)、`tools/check_comment_provenance.py` (`MIN_CH_IDS` を 1 にする行だけ)、本書 §2.3 (判定表) | 他の `src/` 全部 (`postgres_types.py`、`postgres_like.py` を含む)、両 peer の他の `tests/`、`conformance-tests/`、`docs/code-history/pair.md`、`_ISOMORPHIC_TARGETS` |

| 項目 | 内容 |
|---|---|
| CH-ID 予約 | **`CH-0001`〜`CH-0160`** (塊の総数 156 = `#` 塊 117 + docstring 39 が上限)。未使用番号も再利用しない |
| ID の扱い | 設計 §3。出所の無い `R-1`〜`R-7` (`:276`、`:285`、`:290` ほか)、`R-35`、`L-6` は移す側 |
| 参照行 | `#` 塊は移した塊の位置に `# history: CH-NNNN` を 1 行。docstring は末尾に `History: CH-NNNN` を 1 行 (設計 D-2) |
| 手順 | 設計 §6「手順」。行番号 pin は §1.5 の 40b (`_fail_client_value` の `fail()` 行を実測) |

**完了条件 ↔ 変異** (P = `check_comment_provenance.py --base <親コミット> r2db-api/src/r2db_api/postgres.py`、R = `check_comment_provenance.py --register`)

| # | 完了条件 (設計 §6) | 変異 (`file:操作`) | 赤になるもの |
|---|---|---|---|
| 1 | コード不変 | `postgres.py`: コード行の literal を 1 文字変える | P exit 1 (1) |
| 2 | 移した塊が逐語 | `postgres.md`: 1 節から 1 文消す | P exit 1 (2) |
| 3 | 文区間の削除だけ | `postgres.py`: (a) 否定語を落とす (b) 2 文を並べ替える (c) 1 語足す (d) 折返し行を 1 行消す | P exit 1 (3)、4 種それぞれ |
| 4 | 括弧内の削除が規則どおり | `postgres.py`: `SI-08/R-5` の括弧から `SI-08` を消す | P exit 1 (4) |
| 5 | 経緯を足していない | `postgres.py`: 追加行に `WP-` を含める | P exit 1 (5) |
| 6 | ID の解決と孤児 | コード側 1 件を `CH-0999` にする / 参照されない節を足す | R exit 1 (§4.2-1)、`T::test_repository_register_passes` |
| 7 | ID の全体一意 | `docs/code-history/MitateDB-api/x.md` に同番号の節を足す | R exit 1 (§4.2-2) |
| 8 | docstring 依存の新設なし | `postgres.py` に `__doc__` の読出しを 1 行 | R exit 1 (§4.2-5) |
| 9 | 行番号 pin が実測と一致 | allowlist を `1706` に戻す | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 10 | 文字列検査 | 非該当 — **監査照合**: 設計 §5(b) の grep を着手時に取り直し、`postgres.py` を読む検査 0 件を記録 | — |
| 11 | 非空虚 | `MIN_CH_IDS` を 1 のまま全参照行と全節を消す | R exit 1 (§4.2-6) |
| 12 | 受け皿の ID が `check_doc_refs` で解決 | `postgres.md` の fenced block に roadmap に無い 2 桁の R 番号を 1 つ足す | `check_doc_refs.py` exit 1 |
| 13 | 判定表が全塊を覆う | **監査照合** — §2.3 の行数 = 変更した塊の数、根拠欄に空欄なし | — |
| 14 | 集計行と経緯トークン数の前後 | **監査照合** (§2.3 の記録と実行ログを突合) | — |
| 15 | 対応の無い行が無い | **監査照合** (§1.5 の 40) | — |

**検証コマンドと期待形** (40a: 前後の 2 回、前景直列、`timeout` 600000)

```
./.venv/bin/python -m pytest -q r2db-api/tests       → failed/skipped/xfailed 0、前後で passed 数一致
./.venv/bin/python -m pytest -q MitateDB-api/tests   → 同上
./.venv/bin/python -m pytest -q conformance-tests    → 同上 (r2db plug が postgres.py を使う)
./.venv/bin/python -m pytest -q tools/tests          → failed 0
python3 tools/check_comment_provenance.py --base <親コミット> r2db-api/src/r2db_api/postgres.py → exit 0
python3 tools/check_comment_provenance.py --register → exit 0
python3 tools/check_doc_refs.py                      → exit 0
python3 tools/public_value_scan.py <触ったファイル>    → total_flagged=0
監督: root suite 単独 (§1.3 の 19〜23)。前後の集計差分は 0
```

### 2.3 塊ごとの判定表 (実装担当が埋め、監督がコミット前に確定する)

| 塊 (`postgres.py` の旧行範囲 / qualname) | 判定 (残す / 移す `CH-NNNN` / 対象外) | 根拠 (設計 §3 の行、迷って残した場合はその旨) |
|---|---|---|

| 記録 | 前 | 後 |
|---|---|---|
| 経緯トークン数 (設計 §4.1 (5) の語) | | |
| r2db / MitateDB / conformance の集計行 | | |

## 3. 残る疑義

| # | 論点 |
|---|---|
| Q-1 | 設計ファイル名付きの R- (`postgres.py:41`、`:216` の `docs/design/R2DB_CCR13_STORAGE_V1.md R-1/R-2/R-4/R-7`) を、裁定 1 の「設計ファイル名付きの § や D-」と同じく残すか。設計 v0.3 §3 は残す側で書いた |
| Q-2 | 設計 v0.3 §4.1 (4) で括弧内から消してよい語を「(5) の語 + 同じ括弧に出所語 (ファイル名 / `roadmap` / `spec`) を持たない裸の ID (SI- / C- / CCR- を除く)」とした。ツールは開閉を判定しないが、出所の有無は機械的に見る |
| Q-3 | 残した文がある `#` 塊では、`# history:` 行を塊の末尾 (同インデント・連続) に置くとした (docstring 末尾と揃えた) |

## 4. 訂正註

(なし)
