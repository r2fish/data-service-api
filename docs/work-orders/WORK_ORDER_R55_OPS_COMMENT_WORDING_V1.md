# 作業指示書 — R-55 `ops.py` のコメントと docstring に残る作業期の文言

## 0. 版数・位置づけ

- **v1.0 (2026-09-19)。** 基点 main `44c2688`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-55。変更クラスは **Class B** (実装のみ。動作・契約・不変条件・runbook に触れない)。設計文書は持たない (本書 §1 が枠)。先行は R-53 (`docs/work-orders/WORK_ORDER_R53_OPS_HELP_TEXT_V1.md`)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。コメント・docstring の変更なので `docs/design/CODE_COMMENT_PROVENANCE_V1.md` と `docs/code-history/README.md` の作法が掛かる。

## 1. WP-1 — 2 箇所の文を help と同じ指示に揃える

**目的**: `apply-platform-migration` について、コードの中の指示と help の指示を 1 つにする。R-53 は help から作業期の条件 (`Never run against production … come first`) を消し runbook §10 の手順を指す文に置き換えたが、同じファイルの節見出しコメントと `cmd_apply_platform_migration` の docstring に旧い条件が残り、2 つの指示が読める。

### 1.1 触ってよいパス

- `MitateDB-api/src/mitatedb_api/ops.py` — 次の 2 箇所の該当の文だけ。動作・引数・定数・他のコメントは変えない。
  1. `# `apply-platform-migration` -- applies one platform migration file` で始まる節見出しコメントの `Never run against production before an isolated proof, an independent audit, and requester approval.`
  2. `cmd_apply_platform_migration` の docstring の `Never run against production before an isolated proof, an independent audit, and requester approval come first.`
- `MitateDB-api/tests/test_ops_help_text.py` (R-53 のテストファイルに足す)。
- `docs/code-history/MitateDB-api/` の companion — `tools/check_comment_provenance.py --base` が register を求めた場合だけ、`docs/code-history/README.md` の形で。求めなければ触らない。
- 行番号・件数を固定する既存の静的テストがこの変更で赤になる場合だけ、その pin (実測して報告に書く)。

### 1.2 確定文言 (言い換えない)

- 置き換え後の文は、help と同じ指示にする: `Against production, run it only through the runbook's gated procedure (docs/cloud-run-cloud-sql.md section 10).`
- 節見出しコメントでは `# ` の行に収め、既存の折り返し幅に合わせて**その文の範囲だけ**を折り返す (ブロック全体を整形し直さない)。docstring も同じ。前後の文 (`… against a running cluster.` と `DSN comes from …`) は 1 字も変えない。

### 1.3 完了条件

1. `ops.py` のどこにも `isolated proof` も `requester approval` も残らない (テストは `inspect.getsource` でなくファイルの本文を読み、観測対象 = 置き換え後の文が 2 回以上現れることも assert する — 空振り禁止)。
2. 節見出しコメントと docstring の両方が §1.2 の確定文を持つ (空白と `# ` を正規化して比較)。help の文 (R-53) と同じ指示であること = 3 箇所が同じ runbook の節を指すことを 1 つのテストで見る。
3. `tools/check_comment_provenance.py --base 44c2688 MitateDB-api/src/mitatedb_api/ops.py` が 0 で終わる。register を求められたら作法どおりに足し、`--register` も 0。
4. 両 peer の L1 details 語彙の走査など、`ops.py` の行番号・件数を固定する静的テストが緑 (MitateDB-api の peer suite を 1 回)。
5. 下の対応表に対応の無い行が無い。

### 1.4 完了条件 → 変異 (1 項目 1 テスト、expect=red)

| 完了条件 | 変異 |
|---|---|
| 1 | M1: docstring の旧文を戻す → 赤 |
| 2 | M2a: 節見出しコメントの確定文を消す → 赤 / M2b: docstring の確定文の `section 10` を `section 9` にする → 赤 |
| 3・4 | 監査照合 (道具の出力行と集計行) |
| 5 | 監査照合 (本表) |

### 1.5 道具の引数

- `tools/dev/pt.py -C .claude/worktrees/r55-ops-comments -- MitateDB-api/tests/test_ops_help_text.py -q`
- `tools/dev/pt.py -C .claude/worktrees/r55-ops-comments -- MitateDB-api/tests -q` (peer suite、前景 1 回、timeout 600000)
- `tools/dev/pt.py -C .claude/worktrees/r55-ops-comments -- tools/tests/test_comment_provenance.py -q` (peer のテストと 1 回に結合しない)
- `tools/dev/mutate.py "$SP/r55-mutations.json" -C .claude/worktrees/r55-ops-comments`

### 1.6 範囲外 (報告だけ)

`ops.py` (両 peer) の他のコメント・docstring・help に、同じ種類の作業期の文言 (`this work package`、`during this work`、特定の WP の完了を条件にする文) が残っていないかを grep し、所在を報告する。直さない。

### 1.7 記録 (統合時に監督が埋める)

- 実施 2026-09-19。変更は `MitateDB-api/src/mitatedb_api/ops.py` (2 箇所の文と、その塊の `history` 参照行)、`MitateDB-api/tests/test_ops_help_text.py` (テスト 3 件)、`docs/code-history/MitateDB-api/ops.md` (CH-0538・CH-0539、`parent commit` は基点 `44c2688`、各節に訂正記録 1 件)。
- 道具: `tools/check_comment_provenance.py --base 44c2688 …` は `comment provenance OK: 110 blocks checked`、`--register` は `comment provenance register OK: 87 files scanned, 429 CH-IDs`。`pt: 7 passed` (担当ファイル)、`pt: 1372 passed, 2 subtests passed` (MitateDB-api の peer suite、1 巡目。2 巡目は `src/` を変えていない)、`pt: 246 passed` (`tools/tests/test_comment_provenance.py`、別呼び出し)。行番号・件数の pin の更新は不要だった。
- 完了条件 → 変異 → 赤になった test id (`MitateDB-api/tests/test_ops_help_text.py::` を省く): 1 ← M1 (docstring の旧文を戻す)・M1b (旧文を行をまたぐ形で別の docstring に戻す。生テキストの判定では素通りし、正規化後の判定で赤) → `test_ops_source_no_longer_restates_the_runbook_preconditions` / 2 前半 ← M2a (節見出しコメントの確定文を消す) → `test_section_comment_and_docstring_carry_the_confirmed_production_sentence` / 2 後半 ← M2b (`section 10` → `section 9`) → `test_help_comment_and_docstring_name_one_and_the_same_runbook_section` / 3・4 ← 監査照合 (上の道具の出力行) / 5 ← 本表。4 変異とも `expect=red got=red`、復元は sha256 2 回で照合。
- コードレビュー 1 回 (中 2・低 2、全件反映)。監督裁定: (1) `parent commit` は変更セットの基点 `44c2688` (先例どおり)。(2) 訂正記録の `reason` は「3 条件は失効していない。コードは言い直すのをやめ、定める場所 = runbook section 10 を指す」に書き直した — **本書 §1 の「作業期の条件」「旧い条件」という枠の言い方は不正確だった** (3 条件は runbook §10.10.1 の stage 2 の gate として現行である。本文は書き換えず、本項を訂正註とする)。(3) 文の置換を CH-ID の登録 + 訂正記録で表す形は、道具の判定と先例の形に合うので採る。(4) テスト名と定数名の改名 (`RESTATED_PRECONDITION_PHRASES` など) は (2) に合わせたもので採る。
- §1.6 の範囲外の grep: 両 peer の `ops.py` に 10 箇所 (MitateDB-api 3、r2db-api 7)。レビューの見立てはいずれも由来の叙述で運用者への指示ではなく、起票しない。範囲外でより重い 1 件 (`security/CONTROL_MAPPING.md` の失効した作業期の本番制限) を台帳 R-61 に起票した。
- 完了ゲート (監督が単独実行、コミット前の同じ木): `gate: 3748 passed, 2 subtests passed in 350.89s (0:05:50)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0`。前回 3745 + 新しいテスト 3。受け入れる。
