# 作業指示書 — R-92・R-93・R-73 文言の陳腐化 3 件

## 0. 出所と基点

- **v1.0 (2026-09-22)。** 基点はローカル main `4b738f4`。作業 worktree は `.claude/worktrees/r92` (基点と同一)。
- 台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-92 (`:509`)・R-93 (`:510`)・R-73 (`:490`)**。3 件とも「文書・文言の陳腐化」で、設計判断を含まないので設計文書は起こさない。決定は本書 §2 に置く。
- **1 つの指示書・1 つの worktree・1 つのコミットで行う** (依頼者の統合の方針)。変更クラスは 3 WP のうち最も重い **WP-3 の Class C** (`conformance-tests/` を触る) を全体に適用する (着手時に `tools/change_class.py` を変更パスに対して実測し、報告に貼る)。規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit とゲートは監督のみ、§1.1 の 2・§1.11 の 70。道具は §1.10 の 64)。
- **経緯トークンの禁止** (src・tests・`.sql` のコメントと文字列): `WP-`、日付、`review`、`supervisor ruling` を足さない。

## 1. 問題設定と守るべき条件

**問題**: 3 箇所の文言が現物から離れている。(a) R-92 — F-12 の案内文が示すコマンドは、そのとおり叩くと終了コード 2 になる (両 peer で `--lock-timeout` が必須)。(b) R-93 — `0005` のヘッダが `R2DB_PLATFORM_POOL_SIZE` の既定を「4」と書く。(c) R-73 — `MAX_BLOCK_LENGTH` の上のコメントが時点つきの古い実測 (`15,122` / `78 left`) を現在形に近い書き方で残す。

**守るべき条件**:

1. **両 peer の逐語同一** — F-12 の案内文は両 peer で同一である (§1.5 の 38 の同型性規律)。直すなら同時・同文で直す。
2. **引用の真正** — `security/CONTROL_MAPPING.md` の preamble (`:29-30`) は `conformance-tests/test_control_mapping_register.py` のコメントが `15,065` を記録していることを引く。この引用を偽にしない。
3. **不変部** — `MAX_BLOCK_LENGTH = 15200` の値と `.sql` の実行部分 (`--` で始まらない行) には触れない。置き換えた文に、また腐る数値・日付を入れない。

## 2. 決定 (監督確定)

- **D-1 (R-92 の直し方)。** 両 peer の案内文を**逐語同一**に、次の形へ直す (`{ops_module}` は既存の f-string の変数のまま):

  `Run 'python -m {ops_module}.ops upgrade-applications --lock-timeout <value>' (its '--dry-run' shows applied and pending per application; the same '--lock-timeout' is required there), then retry.`

  同じ変更セットで、この文を逐語で pin する両 peer のテストを同じ文に更新する。**docstring は変えない** (文字列リテラルの変更だけ)。
- **D-2 (R-93 の直し方)。** `r2db-api/migrations/0005_credential_store.sql` のヘッダの当該 1 文を、現行の既定の記述 (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §4 の文言) に合わせて直す。**SQL 本文は 1 文字も変えない。**
- **D-3 (R-73 の直し方)。** `15,065` と 135 文字の余白の由来を述べる段落は**残す** (守るべき条件 2)。「Re-measured 2026-09-14 … 78 left」の段落を、**現在形で腐らない書き方**に置き換える: 現在の最長ブロックは分割後に変わっており、現行値は道具で測る (どの道具・引数で測れるかは実装担当が実測して書く)。cap は由来の測定値 + 余白であり、最長ブロックの現行値に追随させない。**コメントに数値を書かない。**
- **D-4 (範囲)。** 3 WP が触るのは §3.0 の 3 群のファイルだけで、互いに重ならない。台帳・設計文書・`CONTROL_MAPPING.md` は更新しない (記録は監督)。

## 3. Change Set Manifest

### 3.0 3 つの WP の重なり (§1.2 の 16・17)

| WP | 触るファイル (実ファイル名) | 他 WP との重なり |
|---|---|---|
| WP-1 (R-92) | 両 peer の `src/*/platform_upgrades.py` と、案内文を逐語で pin する両 peer の `tests/*.py` | 0 |
| WP-2 (R-93) | `r2db-api/migrations/0005_credential_store.sql` | 0 |
| WP-3 (R-73) | `conformance-tests/test_control_mapping_register.py` | 0 |

- 3 WP は同一 worktree `.claude/worktrees/r92` で順に行い、1 コミットにまとめる。変異の一時編集は `mutate.py` が原状復帰と sha256 照合を行う。python は main チェックアウトの `.venv/bin/python`、Bash の timeout パラメータは 600000 を明示し、終了コードは pipe の外で取る。`gate.py` と `finalize.py` は回さない (§1.11 の 70)。
- テストの増減は **0** (新規テストを足さず、既存の逐語 pin の文字列だけを直す)。したがってゲートの root 集計行は直前の main と同数 **3844** が期待値である。

### 3.1 WP-1 (R-92) — F-12 の案内文に `--lock-timeout` を足す (両 peer)

#### 3.1.1 触ってよい・触らないパス

- **触ってよい**: `r2db-api/src/r2db_api/platform_upgrades.py` と `MitateDB-api/src/mitatedb_api/platform_upgrades.py` の **`_f12_message` の文字列リテラル**、およびその文を逐語で pin する両 peer の tests の**文字列リテラル**だけ。
- **触らない**: 同 module の docstring と関数の構造、両 peer の `ops.py`、`spec/`、`security/`、`conformance-tests/`、`docs/`、台帳 (**変異の一時編集を除く**)。

#### 3.1.2 監督実測 (2026-09-22、ローカル main `4b738f4`)

1. 文は `r2db-api/src/r2db_api/platform_upgrades.py:180` と `MitateDB-api/src/mitatedb_api/platform_upgrades.py:168` で同一。
2. 逐語で pin するテスト: `r2db-api/tests/test_platform_upgrade_ledger_scan.py:782`、`MitateDB-api/tests/test_platform_upgrades.py:344`。`MitateDB-api/tests/test_platform_upgrades.py:634` は部分文字列 `"ops upgrade-applications"` のみ。
3. `security/CONTROL_MAPPING.md` はこの案内文を引用していない (`upgrade-applications` の語は `:280`・`:301`・`:620` に在るが案内文ではない)。`spec/`・`conformance-tests/` にこの文の pin は無い (grep 0 件)。
4. docstring を変えないので `tools/check_comment_provenance.py --register` は緑のままである。

#### 3.1.3 起草時実測 (2026-09-22、起草担当。着手時に再照合する)

5. 案内文を**逐語で pin する箇所は §3.1.2 の 2 の他に 3 件**在る: `r2db-api/tests/test_postgres.py:3868`、`r2db-api/tests/test_application_audit.py:3194` (定数 `_F12_MESSAGE_UPGRADE_9`)、`MitateDB-api/tests/test_main.py:305` (定数 `_F12_MESSAGE_UPGRADE_8`)。いずれも実 PostgreSQL を使うテストである。
6. `_f12_message` は同型性対応表 (`r2db-api/tests/test_audit_query.py:2582` の `_ISOMORPHIC_TARGETS`) に載っており、**両 peer の差は同型性テストが赤にする** (完了条件 1 の変異先)。
7. 設計 `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §3.8 の F-12 行 (`:519`) が同じ文を逐語で持ち、両 peer の docstring は「設計の文言を逐語で写した」と述べる。**この影響の扱いは監督裁定を要する** — 着手時に再照合し、§6.1 に裁定が無ければそこで止まって監督へ上げる (§1.5 の 37)。

#### 3.1.4 着手手順

1. worktree `.claude/worktrees/r92` が基点 `4b738f4` と同一であることを確かめ、§3.1.2 の 1〜4 と §3.1.3 の 5〜7 を自分で再照合する (**食い違いが 1 件でもあれば、そこで止まって監督へ上げる**)。
2. 両 peer の `ops.py` の argparse で `upgrade-applications` の `--lock-timeout` が `required=True` であることを `file:line` で確かめ、`--help` の出力を取る (完了条件 3)。
3. D-1 の文へ両 peer 同時に直し、§3.1.2 の 2 と §3.1.3 の 5 の pin を同じ文に更新する。**pytest の対象に §3.1.3 の 5・6 のファイルを足すかどうかは監督の指示による** (§1.10 の 65) — 必要と判断したら報告で上げ、自分で `pt.py` の引数を広げない。
4. `tools/check_comment_provenance.py --register` を回し、緑であることを報告に貼る。

#### 3.1.5 実装の形

- 変更は `_f12_message` の `return` の f-string と pin テストの期待文字列だけ。改行位置は既存の折り返しに合わせる (連結した結果が D-1 の文と逐語一致すること)。文中の `<value>` は**そのままの literal** にする (実値を埋めない。`--help` の `metavar` と同じ語)。

#### 3.1.6 道具の引数

```bash
tools/dev/pt.py --wait 1800 -C .claude/worktrees/r92 -- r2db-api/tests/test_platform_upgrade_ledger_scan.py MitateDB-api/tests/test_platform_upgrades.py conformance-tests/test_control_mapping_register.py -q
tools/dev/mutate.py "$SP/r92-mutations.json" -C .claude/worktrees/r92 --wait 1800
```

変異 spec の形 (`old` は着手時に対象ファイルで 1 件一致する行を選ぶ。**1 変異 = 1 entry**、`mutate.py` は最初の不一致で止まる):

```json
{"pytest": ["-q", "r2db-api/tests/test_platform_upgrade_ledger_scan.py"],
 "mutations": [{"id": "M1", "expect": "red", "file": "r2db-api/src/r2db_api/platform_upgrades.py",
   "old": "upgrade-applications --lock-timeout <value>' ", "new": "upgrade-applications' ",
   "tests": ["r2db-api/tests/test_platform_upgrade_ledger_scan.py"]}]}
```

#### 3.1.7 完了条件 → 変異 → 赤になる test id

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) | 実施 |
|---|---|---|---|---|
| 1 | 両 peer の案内文が逐語同一である | `MitateDB-api/src/mitatedb_api/platform_upgrades.py`: 案内文から ` <value>` だけを落とす (r2db は直さない) | `r2db-api/tests/test_audit_query.py` の `_f12_message` の同型性テスト | 実装担当 |
| 2 | 案内文が `--lock-timeout <value>` を含む | 2 件。両 peer の `platform_upgrades.py` から ` --lock-timeout <value>` を 1 peer ずつ落とす | 各 peer の逐語 pin (`test_platform_upgrade_ledger_scan.py` / `test_platform_upgrades.py`、加えて §3.1.3 の 5 の pin) | 実装担当 |
| 3 | 案内文のコマンドがそのまま叩ける (`--lock-timeout` が必須の引数として存在する) | **監査照合**: 両 peer の `ops.py` の `required=True` の行 (`file:line`) と `upgrade-applications --help` の `--lock-timeout` の行を報告に貼る | — | 実装担当 |
| 4 | 上の表に、変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜3 の各行に「変異」または「監査照合」が入っていることを照合し、結果を報告に貼る | — | 実装担当 |

### 3.2 WP-2 (R-93) — `0005` ヘッダの `R2DB_PLATFORM_POOL_SIZE` の既定

#### 3.2.1 触ってよい・触らないパス

- **触ってよい**: `r2db-api/migrations/0005_credential_store.sql` の **`--` で始まるコメント行の当該 1 文**だけ。
- **触らない**: 同ファイルの SQL 本文、他の migration、`src/`、`tests/`、`docs/`、`deploy/`。

#### 3.2.2 監督実測 (2026-09-22)

1. `r2db-api/migrations/0005_credential_store.sql:106` に「pool per API process (`R2DB_PLATFORM_POOL_SIZE`, default 4 --」。
2. 既定は Phase 10 WP-4e 以後 `concurrency` に由来する (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §4)。
3. migration ファイルの hash は platform-upgrade の台帳に記録されない (r2db の `platform_upgrades.py`・`ops.py` に digest/sha256 は 0 件)。`tools/check_comment_provenance.py` は `.sql` を見ない。
4. `security/CONTROL_MAPPING.md`・両 peer の tests・`conformance-tests/` は `0005` のヘッダ文言を引用しない (テストは `0005_credential_store.sql` をファイルとして流すだけ)。

#### 3.2.3 着手手順

1. §3.2.2 の 1〜4 を自分で再照合する (**食い違いが 1 件でもあれば止まって監督へ上げる**)。
2. runbook §4 の該当行で現行の既定の記述を確かめ、**その文言で**ヘッダの 1 文を直す (runbook の記述と呼び出し側の実測が食い違う場合は直さず、両方を報告に貼って監督へ上げる)。`git diff -- r2db-api/migrations/0005_credential_store.sql` を取り、変更行が `--` で始まる行だけであることを確かめる。

#### 3.2.4 完了条件 → 変異 → 赤になる test id

| # | 完了条件 | 変異 / 監査照合 | 赤になる test id | 実施 |
|---|---|---|---|---|
| 1 | 当該文が現行の既定と runbook §4 に一致する | **監査照合**: `grep -n R2DB_PLATFORM_POOL_SIZE r2db-api/migrations/0005_credential_store.sql` の出力と runbook の該当行を並べて報告に貼る | — | 実装担当 |
| 2 | diff がコメント行のみ (SQL 本文は不変) | **監査照合**: `git diff` の該当ファイルの出力 (変更行が全て `--` で始まること) を報告に貼る | — | 実装担当 |
| 3 | 上の表に、変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜2 の各行の照合結果を報告に貼る | — | 実装担当 |

- **変異が無い理由**: 対象は実行されないコメントで、どのテストも文言を引用しない (§3.2.2 の 4)。§1.5 の 40 に従い、照合対象の逐語記録 (実行したコマンドと出力行) を報告に残すこと自体を完了条件とする。

### 3.3 WP-3 (R-73) — `MAX_BLOCK_LENGTH` の上のコメントの書き換え

#### 3.3.1 触ってよい・触らないパス

- **触ってよい**: `conformance-tests/test_control_mapping_register.py` の **`:88`-`:96` のコメント段落**だけ。
- **触らない**: 同ファイルの `MAX_BLOCK_LENGTH = 15200` の値、`:84`-`:87` の `15,065` の段落、コード全般、`security/CONTROL_MAPPING.md`、`tools/`、`spec/`。

#### 3.3.2 監督実測 (2026-09-22)

1. `:84`-`:96` は 2 段落: (a) 「this file's own longest cell is SI-14's r2db-api … 15,065 characters. MAX_CELL_LENGTH = 15,200 is that measurement plus a 135-character margin.」、(b) 「Re-measured 2026-09-14 (WP-2 …) … 15,122 … 78 left …」。
2. `security/CONTROL_MAPPING.md` の preamble (`:29-30`) は、**このファイルのコメントが `15,065` を記録していること**を引く。
3. `conformance-tests/` は `tools/check_comment_provenance.py` の走査外である。

#### 3.3.3 着手手順

1. §3.3.2 の 1〜3 を自分で再照合する (**食い違いが 1 件でもあれば止まって監督へ上げる**)。
2. **現行の最長ブロックを実測する**: どの道具にどの引数を渡せば block 長が得られるかを実測する (`tools/check_control_mapping_restructure.py` は `--base <rev>` を要する対応検査であり、block 長を出さない可能性がある。出さないなら、このファイル自身の分解ヘルパ (`_iter_section_subblocks` / `_subblock_block_text`) を使う経路など、**実際に動く経路**を確かめる)。実測した道具名・引数・出力行を報告に貼る。**どの経路も無い場合は、コメントに道具名を書かず、そこで止まって監督へ上げる。**
3. (b) の段落を D-3 の現在形の書き方に置き換える。**数値・日付を書かない** (「現行値は次の手順で測る」「cap は由来の測定値 + 余白であり、最長ブロックの現行値に追随させない」)。(a) の段落は 1 文字も変えない。最後に `pt.py` (§3.1.6 の 1 本目) で `conformance-tests/test_control_mapping_register.py` が緑であることを確かめる。

#### 3.3.4 完了条件 → 変異 → 赤になる test id

| # | 完了条件 | 変異 / 監査照合 | 赤になる test id | 実施 |
|---|---|---|---|---|
| 1 | コメントに時点つきの記述が無い | **監査照合**: `grep -n '15,122\|78 left\|2026-09-14' conformance-tests/test_control_mapping_register.py` が 0 件であることを報告に貼る | — | 実装担当 |
| 2 | `15,065` と 135 文字の余白の由来の段落が残り、preamble (`:29-30`) の引用が真のままである | **監査照合**: `grep -n '15,065'` が 1 件以上であることと、preamble の該当行を並べて報告に貼る | — | 実装担当 |
| 3 | `MAX_BLOCK_LENGTH = 15200` が不変で、diff がコメント行のみである | **監査照合**: `git diff` の該当ファイルの出力 (変更行が全て `#` で始まること) を報告に貼る | — | 実装担当 |
| 4 | 現行の最長ブロックを実測した (道具名・引数・出力行) | **監査照合**: §3.3.3 の 2 の実測を報告に貼る | — | 実装担当 |
| 5 | 上の表に、変異も監査照合も無い完了条件の行が 1 つも無い | **監査照合**: 1〜4 の各行の照合結果を報告に貼る | — | 実装担当 |

- **変異が無い理由**: 変更対象はコメントだけで、値もコードも変えない (完了条件 3)。§1.5 の 40 に従い、照合対象の逐語記録 (実行したコマンドと出力行) を報告に残すこと自体を完了条件とする。

### 3.4 報告に貼るもの (3 WP 共通)

各 WP の再照合の結果と、各完了条件の監査照合の出力行 (コマンドと出力をそのまま) / WP-1 は `ops.py` の `required=True` の `file:line`・`--help` の該当行・更新した pin の `file:line` の全件・`mutate.py` の各変異の `expect=` / `got=` と復元の sha256 照合・`check_comment_provenance.py --register` の結果 / `pt.py` の集計行 / `tools/change_class.py` を 3 WP の変更パスに対して回した結果。

## 4. 却下した代替案

- **R-92 で片方の peer だけ直す** — 両 peer 同一文の規律 (§1.5 の 38) に反する。同型性テストも赤になる。
- **R-73 でコメントに現行値 (12,624 等) を書く** — また腐る。本件はその腐りを直す作業である。
- **R-73 で `15,065` の段落も消す** — `security/CONTROL_MAPPING.md` preamble の引用が偽になり、その訂正は Class D になる。
- **R-93 でヘッダ全体を書き直す** — SQL 本文に触れる危険がある。陳腐化した 1 文だけを直す。

## 5. レビューと監査

- **設計レビューは行わない** (3 件とも設計判断を含まない文言の陳腐化)。**コードレビュー 1 回** (別に起動した reviewer)。
- **受け入れ監査は監督が §3.1.7・§3.2.4・§3.3.4 の対応表とゲートの集計行を照合して行う** (evidence-auditor は起動しない — Class B/C の軽微な変更)。
- **完了ゲート**は監督単独: `tools/dev/gate.py -C .claude/worktrees/r92 --label r92`。root 集計行は直前の main と同数 **3844** が期待値 (テストの増減 0)。

## 6. 実施記録 (統合時に監督が埋める)

### 6.1 訂正註と監督裁定 (§1〜§5 の本文は書き換えない)

- **【訂正註 1 (2026-09-22)】WP-1 の文言と pin の件数。** 案内文は指示書 §2 D-1 の案ではなく監督裁定の文 `… Run 'python -m {ops_module}.ops upgrade-applications --lock-timeout <value>' (its '--dry-run' shows applied and pending per application and requires the same '--lock-timeout'), then retry.` を採った。逐語の pin は起草時の 2 件ではなく **5 件** (`r2db-api/tests/test_platform_upgrade_ledger_scan.py`、`test_postgres.py`、`test_application_audit.py`、`MitateDB-api/tests/test_platform_upgrades.py`、`test_main.py`) で、同型 helper `_f12_message` は `r2db-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` に載る。設計 `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §3.8 F-12 は本文を変えず訂正註を足した (v1.5、placeholder は `:520` の行と同じ `<peer>` / `<未適用の番号…>` の記法)。
- **【訂正註 2 (2026-09-22)】WP-2 (R-93) の前提の検証。** `0005` のヘッダの pool は data-plane の platform pool (`r2db_api.main` が `ResourceLimits.concurrency` から寸法を導く) であり台帳の前提は正しかった。ただし数値だけを直すと周囲の文 (「1 process 1 pool」「CONNECTION LIMIT 10 で足りる」) が現物 (同 role で credential store + audit sink の 2 pool、上限は `0013` が引き上げる) と矛盾するので、段落全体をコメント行だけで書き直した (SQL 本文は不変。数値 68 は書かず `0013` を指す。`R2DB_PLATFORM_POOL_SIZE` の明示指定が既定に優先する旨を再確認の低 1 件として足した)。
- **【訂正註 3 (2026-09-22)】WP-3 (R-73) の測り方。** block 長を出す道具は無く、当該テスト自身の `_split_sections` → `_iter_section_subblocks` → `_subblock_block_text` で測る。現行最長は SI-09 / MitateDB-api / platform upgrade の 12,681 字 (preamble の記録と一致。コメントには書かない)。`:102` の「measured 2026-09-14」(MAX_LINE_LENGTH の由来) は cap の由来の記述なので据え置き。
- **`tools/check_comment_provenance.py --base 4b738f4` の §4.1 (1) の赤は受理** (案内文の文字列リテラルを変えたのでコードは変わる)。(5) 経緯トークンは 0 件。

### 6.2 実施と受け入れ

- **差分**: 両 peer の `platform_upgrades.py` (案内文の文字列のみ)、pin テスト 5 本、`conformance-tests/test_control_mapping_register.py` (コメント)、`r2db-api/migrations/0005_credential_store.sql` (コメント段落)、`docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` (v1.5、訂正註)。`tools/change_class.py` → `class=C`。
- **道具の出力行**: `pt: 467 passed` (pin 5 ファイル + `test_audit_query.py` + `test_control_mapping_register.py`)。`mutate: 3 mutations, 3 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged` (M1 同型性 → `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` 赤、M2/M3 各 peer の pin 赤)。両 peer の `ops.py` で `--lock-timeout` は `required=True` (r2db `:1883`、MitateDB `:3160`)、`--help` の usage に `--lock-timeout VALUE` が必須引数として出る。`--register` OK 87/430、`check_doc_refs` 0、`public_value_scan` 0。
- **監査照合 (WP-2/WP-3)**: `git diff` の変更行は `0005` が `--` 行のみ、`test_control_mapping_register.py` が `#` 行のみ。`grep -n '15,065'` 1 件 (`:85`)、preamble `security/CONTROL_MAPPING.md:29-30` の引用は真のまま。`MAX_BLOCK_LENGTH = 15200` 不変。
- **コードレビュー 1** (中 4・低 2 → 差し戻し 1: `0005` 段落の全文書き直し、設計文書の版数註と旧版見出し、訂正註の placeholder 記法、測り方に `_split_sections`) → 再確認で全件閉 (新 `0005` 段落の 4 主張を現物で照合: `0013:108` は `r2dbsvc_api`、`main.py:432`/`:441` の 2 pool は同じ `R2DB_PLATFORM_DSN`、`control_main.py` は `R2DB_CONTROLPLANE_DSN` のみ)、新規 低 1 (`R2DB_PLATFORM_POOL_SIZE` の明示指定) を監督が反映。
- **完了ゲート** (監督単独、`tools/dev/gate.py -C .claude/worktrees/r92 --label r92`、低 1 の反映前の木): `gate: 3844 passed, 2 subtests passed in 363.08s`、`judge=PASS`、実行クラスタ差分 0。低 1 の反映は `0005` のコメント 2 行 (SQL 本文不変) のみで、テストが流す SQL に影響しない。
- **最終判定**: 受け入れ (Class C、監督が対応表とレビュー結果で判定)。台帳 R-92・R-93・R-73 を閉じる (v1.92)。
