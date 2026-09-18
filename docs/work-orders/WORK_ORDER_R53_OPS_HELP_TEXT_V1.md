# 作業指示書 — R-53 `ops.py` の help 文 3 点

## 0. 版数・位置づけ

- **v1.0 (2026-09-18)。** 基点 main `3d5b4de`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-53。変更クラスは **Class B** (実装のみ。契約・不変条件・runbook に触れない)。設計文書は持たない (本書 §1 が枠)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit は監督のみ、道具は `tools/dev/`)。

## 1. WP-1 — help 文を現物に合わせる

**目的**: 運用者が `--help` だけを読んでも誤った値を渡さない。help の列挙は定数から導き、次に platform migration が増えても古くならない形にする。

### 1.1 触ってよいパス

- `MitateDB-api/src/mitatedb_api/ops.py` — `_build_parser` の中の help 文 3 箇所だけ (`apply-platform-migration`、`--data-process-count-total`、`--control-process-count-total`)。動作・引数・定数は変えない。
- `MitateDB-api/tests/test_ops_help_text.py` (新規)。
- ファイル名・件数を固定する既存の静的テストが新規ファイルで赤になる場合だけ、その pin (実測して報告に書く)。

### 1.2 確定文言 (言い換えない)

- `apply-platform-migration` の help: 番号の列挙は `_PLATFORM_MIGRATION_FILENAMES` の各要素の先頭 4 桁を `/` で繋いで導く。`Never run against production during this work package -- …come first` の文を消し、次の文に置き換える: `Against production, run it only through the runbook's gated procedure (docs/cloud-run-cloud-sql.md section 10)`。それ以外の語 (bootstrap-only 0001/0002 の括弧書きを含む) は現行のまま。
- `--data-process-count-total` の help: `WORST-CASE Data-plane process count: the sum of the process ceilings of every revision that can serve at the same time, plus the NEW candidate's own ceiling (a positive integer, used for connection demand). Never the number of instances running at the moment of the read -- omit to leave item (8) unknown`
- `--control-process-count-total` の help: `WORST-CASE Control-plane process count: the sum of the process ceilings of every revision that can serve at the same time, plus the NEW candidate's own ceiling. Never the number of instances running at the moment of the read -- omit (with --control-not-deployed absent too) to leave item (8) unknown`

### 1.3 完了条件

1. `apply-platform-migration` の help が `_PLATFORM_MIGRATION_FILENAMES` の全要素の番号を含み、列挙が定数から導かれている (テストは定数に合成の 1 本を足した状態で `_build_parser()` を作り、その番号が help に現れることを見る)。
2. 同 help が `work package` を含まず、§1.2 の置き換え文を逐語で含む。
3. 2 つの `--*-process-count-total` の help が §1.2 の確定文を逐語で持ち、`actually running` を含まない。
4. 下の対応表に対応の無い行が無い。

### 1.4 完了条件 → 変異

| 完了条件 | 変異 |
|---|---|
| 1 | M1: 導出を直書きの `0005/0007/0011/0012/0013` に戻す → 赤 |
| 2 | M2: `this work package` の旧文を戻す → 赤 |
| 3 | M3a: data 側を旧文に戻す → 赤 / M3b: control 側を旧文に戻す → 赤 |
| 4 | 監査照合 (本表) |

### 1.5 道具の引数

- テスト: `tools/dev/pt.py -C .claude/worktrees/r53-ops-help -- MitateDB-api/tests -q`
- 変異: `tools/dev/mutate.py "$SP/r53-mutations.json" -C .claude/worktrees/r53-ops-help`

## 2. 記録 (2026-09-18)

- 実装 1 回、差し戻し無し。`pt.py` (MitateDB-api/tests): `1345 passed, 2 subtests passed`。`mutate.py`: M1・M2・M3a・M3b の 4 件とも `expect=red got=red`、復元は sha256 2 回で照合済み。
- コードレビュー 1 回: 差し戻し無し。低 1 件 (同じファイルのコメントと docstring に旧文言が残る) は監督裁定で別件 R-55 として起票した。
- 完了ゲート (worktree、`gate.py -C`): `3692 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。main `cad71ad` (作業 `7c17a55`)。
- 変異の定義 (scratchpad を手放す前の写し): M1 = help の導出式を直書き `0005/0007/0011/0012/0013` に戻す / M2 = `this work package` の旧文を戻す / M3a = `--data-process-count-total` を旧文に戻す / M3b = `--control-process-count-total` を旧文に戻す。いずれも対象は `MitateDB-api/src/mitatedb_api/ops.py`、観測は `MitateDB-api/tests/test_ops_help_text.py`。
