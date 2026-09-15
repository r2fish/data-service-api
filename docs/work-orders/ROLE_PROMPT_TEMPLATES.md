# 役割 agent と発注の雛形 (ROLE_PROMPT_TEMPLATES)

監督 (メインセッション) がサブエージェントへ仕事を渡すための、役割の分担・クラス別の監督手順・起動プロンプトの雛形。

**規律の正本は `OPERATING_CONDITIONS.md` であり、本書はその実行手順を持つだけである** (`tools/dev/README.md` と道具の関係と同じ)。本書の記述が `OPERATING_CONDITIONS.md` と食い違ったら、`OPERATING_CONDITIONS.md` が正しい。条項は `§1.5 の 33` の形で指す。

## 分担

| 置き場 | 持つもの |
|---|---|
| `.claude/agents/*.md` | **固定部分**: 役割、前提として読むもの、禁止事項、報告形式、起動プロンプトで受け取る項目 |
| 本書 | **手順とタスク固有部分**: 共通運用ルール、クラス別の監督手順、起動プロンプトの雛形 (`{ }` の穴) |

| 役割 | agent (`subagent_type`) | model | 監督が自分で行わない理由 |
|---|---|---|---|
| 監督 | メインセッション | opus | — (枠決め・裁定・完了ゲート・受け入れ判定・commit を行う) |
| 1 調査 | `explorer` | haiku (読解が要るときは起動時に `model: "sonnet"`) | 監督の文脈を小さく保つ／利用枠 |
| 2 実装 | `implementer` | sonnet | 役割分離／利用枠 |
| 3 起草 | `drafter` | opus | 監督の文脈を小さく保つ |
| 4 設計文書レビュー | `reviewer` (モード: 設計レビュー) | opus | 独立性 |
| 5 コードレビュー | `reviewer` (モード: コードレビュー) | opus | 独立性 |
| 6 受け入れ監査 | `evidence-auditor` | opus | 独立性 |

- agent 名は役割名であり、モデル名を含めない。割り当てを変えるときは frontmatter の `model:` と上表の両方を直す。
- 起動時の `model` 指定は frontmatter より優先される。
- テンプレ 4 と 5 は 1 体の agent のモードで分ける。**独立性は定義ではなく起動で保つ**: 起草者とレビュー担当、設計レビューとコードレビュー、レビュー担当と監査担当は、必ず別に起動する (`§1.11 の 69`)。
- サブエージェントのプロンプトは常に自己完結させる (会話の文脈は渡らない)。

## 共通運用ルール

1. **報告は短く固定する。** 結論＋指摘/変更一覧＋道具の出力行 (集計行・変異表・`log=` のパス) のみ。生出力は道具のログに残るので、パスだけ報告させる (`§1.10 の 65`)。
2. **調査は `explorer` に任せる。** 所在特定は haiku、意味の読解は sonnet で起動する。長い文書は監督も役割 agent も全文を読まず、`tools/dev/section.py` で見出し一覧 → 必要な節だけを読む。
3. **subagent に suite 全体を回させない。** peer 別 suite と担当ファイルの conformance だけを `tools/dev/pt.py` で (`§1.6 の 42`)。レビュー・監査は `--collect-only -q` と静的照合を主とし、変異は自作分のみ最小回数 (`§1.6 の 43`)。
4. **完了ゲートは監督が単独で実行する。** `tools/dev/gate.py` を subagent に実行させない。集計行だけが正本である (`§1.3 の 19`)。
5. **実装担当の報告も、レビュー担当の結論も、受け入れの証拠にしない。** 監査は道具の出力と差分だけを見る。
6. **commit / merge は監督のみ。** `tools/dev/finalize.py` を subagent に実行させない (`§1.1 の 2`、`§1.11 の 70`)。
7. **差し戻しは会話ではなくファイルで渡す。** 各件に原文・現行がどう止まっているか・実測・壊れるシナリオを並べ、重大度を付け、裁定を要する項目は「裁定は監督」と明記する (`§1.7 の 49`)。
8. **実装担当に下請け Agent を使わせない** (発注時に明記する。`§1.7 の 47`)。長時間の検証をさせるときは同期実行を指示する (`§1.7 の 48`)。
9. **道具が REFUSED (終了コード 75) を返したら迂回しない** (`§1.10 の 66`)。
10. **監督チャットはモデル呼び出し 300 回を超えたら次の区切りで移る** (`§1.10 の 67`)。区切りの判定は `tools/dev/handover_ready.py`。
11. 報告・文書は日本語。

## クラス別の監督手順

変更クラスの正本は `RM` §9 の 8 の表である。`tools/change_class.py` は**パスだけで決まる下限**を機械判定する道具であり、パスに現れない契機 (catalog 宣言値と登録済み同型 helper の本体 = C、`_ISOMORPHIC_TARGETS` 集合の増減と `CLAUDE.md` の境界節 = D) は表を読んで判定する。複数に跨れば最も重いクラスに従う。レビュー担当はクラスを上げられるが下げられない。

### 全クラス共通

1. **クラスを宣言する。** 下限は `git diff --name-only --no-renames origin/main...HEAD | ./.venv/bin/python tools/change_class.py` が出す。最終判定は `RM` §9 の 8 の表で行う。
2. **worktree を用意する。** 並行作業は WP ごとの linked worktree (`.claude/worktrees/<name>`) で行い、共有ツリーを checkout しない (`§1.2 の 13`、`14`)。並行 WP は触るファイルの重なりが 0 であることを着手前に照合する (`§1.2 の 16`)。
3. **探索**: `explorer` (テンプレ 1)。
4. **枠決め**: 問題設定、守るべき条件、決定軸、候補案と却下理由。開発順序は `CLAUDE.md` の Development order 節を読む (本書に写さない。`CLAUDE.md` は Class D であり、写しは無検査で乖離する)。
5. **依頼者確認**: 契約・不変条件・`OPERATING_CONDITIONS.md` §1 に触れる決定は依頼者の確認を得る (`RM` §9 の 8)。
6. **commit**: `tools/dev/finalize.py` で worktree の branch から commit し、main へ `--no-ff` でマージする。件名は `type(scope): …` 形式、文書だけの変更には `[skip ci]` を付ける (`§2 の 20`)。

### Class A (文書のみ)

1. 監督が起草する (長文なら `drafter`、テンプレ 3)。
2. 監督が自分で確認する。`OPERATING_CONDITIONS.md` §1 や `.claude/agents/` のように運用そのものを変える文書では、`reviewer` (テンプレ 4) を 1 回入れる。
3. conformance は要らない (`change_class.py` が `conformance_required=false` を返す)。`finalize.py` の doc-refs・public-value スキャンは走る。
4. commit。

### Class B (実装のみ。契約・不変条件に触れない)

1. **作業指示書**: Change Set Manifest の形で、各 WP に 完了条件 / 触ってよいパス / 道具の引数 / 完了条件番号 → 変異の対応表を持つ (`§1.5 の 40`)。
2. **WP ごと**: `implementer` (テンプレ 2) → `reviewer` (テンプレ 5、モード: コードレビュー) → 指摘があれば差し戻し指示をそのまま `implementer` に渡して修正し、同じ観点で再確認する。
3. **完了ゲート**: 監督がリポジトリルートで `tools/dev/gate.py --label <名前>` を単独実行する。合格条件は `§1.3 の 22`、`xpassed` と `deselected` の扱いは `§1.3 の 26` を読む。
4. **受け入れ**: 監督がゲートの集計行と WP の対応表を照合して判定する。機械判定の証拠が多いときは `evidence-auditor` (テンプレ 6) を 1 回入れてよい。
5. 引き継ぎ書を書き、commit。

### Class C・D (`spec/`・`conformance-tests/`・`security/`・`CLAUDE.md`・公開方針)

1. **設計文書**: `drafter` (テンプレ 3) が `docs/design/PHASE<n>_<name>_V1.md` に起草する。
2. **設計レビュー**: 別に起動した `reviewer` (テンプレ 4)。**契約を触るフェーズは 2 回、触らないフェーズは 1 回** (`§1.7 の 50`)。
3. **依頼者裁定** → 設計文書に逐語で記録し、再審議しない (`§1.7 の 51`)。
4. **作業指示書**: `drafter` (テンプレ 3)。契約・conformance の WP を実装 WP より先に置く。
5. **実装 WP ごと**: Class B の手順 2 と同じ。
6. **完了ゲート**: 監督が単独実行。契約ファイルを触るコミットは root suite 完走を完了条件にする (`§1.1 の 10`)。性能差分を添える (`§1.3 の 27`)。
7. **受け入れ監査**: 全 WP のレビュー完了後に、レビュー担当とは別に起動した `evidence-auditor` (テンプレ 6) を **1 回**。
8. **受け入れ**: 監督がパケットの判定を確認し、裁定と最終判定を書き足して引き継ぎ書にする。
9. 計画文書 (`RM`) の §1 と §8 を更新し、commit (`§1.8 の 55`)。

---

## 1. 調査 (`explorer`)

所在特定は既定 (haiku) のまま、読解が要る調査は Agent ツールの `model` に `"sonnet"` を指定し、「調査の種類」を `読解` にして起動する。

```text
対象: {main checkout | worktree} ({絶対パス})
scratchpad: {scratchpad}

調査の種類: {所在特定 | 読解}
調査目的: {設計判断に必要な問い}
```

## 2. 実装 (`implementer`)

```text
担当 worktree: {repo}/.claude/worktrees/{name}（branch: {branch}）
scratchpad: {scratchpad}

作業指示書: docs/work-orders/{WORK_ORDER_…}.md の {WP 番号}
正本設計: {設計文書パスと参照節}
タスク: {WP の内容・完了条件・完了条件ごとの変異}
テスト: tools/dev/pt.py -C .claude/worktrees/{name} -- {peer 別 suite と担当 conformance のパス} -q
変異: tools/dev/mutate.py "{scratchpad}/{name}-mutations.json" -C .claude/worktrees/{name}
gate-hold flag: {--hold のパス | 「--hold -」（監督ゲート無し）}
注意: suite 全体を回さない。commit / merge / gate.py / finalize.py は監督が行う。下請け Agent を使わない。
```

## 3. 起草 (`drafter`)

```text
起草するもの: {設計文書 | 作業指示書 | 引き継ぎ書}
出力先: {パス}
対象: {フェーズ番号 | 台帳 ID（`RM` の R-N 等）}
scratchpad: {scratchpad}
追加で読むもの: {spec/・security/・既存設計文書・計画文書の該当節}

枠（監督が確定済み — 変更しない）:
- 問題設定と守るべき条件: {…}
- 決定と根拠: {…}
- 却下した代替案と理由: {…}
- 未確定で依頼者判断待ちの選択肢: {…}（両論のまま文書に残す）
```

## 4. 設計文書レビュー (`reviewer`)

```text
モード: 設計レビュー
変更クラス: {C | D}
scratchpad: {scratchpad}

レビュー対象: {設計文書パス}
追加で読むもの: {spec/・security/ の関連節、既存設計文書}
問題設定と制約: {この設計が解く問題、守るべき条件}
検討済みで却下した代替案: {あれば列挙}
```

## 5. コードレビュー (`reviewer`)

```text
モード: コードレビュー
変更クラス: {A | B | C | D}
対象 worktree: {repo}/.claude/worktrees/{name}（branch: {branch}）
scratchpad: {scratchpad}

レビュー範囲: {差分の範囲}
準拠すべき設計: {設計文書パスと節}
作業指示書: docs/work-orders/{WORK_ORDER_…}.md の {WP 番号}
実装担当の報告: {scratchpad}/{…}（pt.py の集計行と log=、mutate.py の変異表）
ログの保存先: {scratchpad}/review-{WP}.log
変異を足すなら: tools/dev/mutate.py "{scratchpad}/review-{WP}-mutations.json" -C .claude/worktrees/{name}
注意: テストは再実行しない（自作の変異のみ最小回数）。完了ゲートは監督が単独実行する。
```

## 6. 受け入れ監査 (`evidence-auditor`)

```text
対象 worktree: {repo}/.claude/worktrees/{name}（branch: {branch}）
scratchpad: {scratchpad}

監査対象: docs/work-orders/{WORK_ORDER_…}.md の {全 WP | 対象 WP} の完了条件と受入条件
材料: 実装報告 {scratchpad}/…、pt.py / mutate.py のログ {…}、コードレビュー結果 {scratchpad}/review-{WP}.log、差分の範囲 {…}
完了ゲート（監督が単独実行）: {集計行を verbatim で貼る} / log={パス}
引き継ぎ書の保存予定: docs/work-orders/HANDOVER_{…}.md
節構成の参考: docs/work-orders/{既存 HANDOVER}.md
パケットの出力先: {scratchpad}/acceptance-packet.md
```
