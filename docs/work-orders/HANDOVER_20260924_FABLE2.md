# 引き継ぎ — 2026-09-24 (正本と記録を分けた: docs/archive/ と検査器の走査範囲。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260924_FABLE.md` (R-79 閉止・R-80 計測。別チャット、本チャットと同日に並走) で、**同書の §3・§4・§5 と、そこが引く前々書 (`docs/archive/docs/work-orders/HANDOVER_20260923_FABLE5.md`。本書の変更セットで archive へ回転した) までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。

## 1. 現在地

- ローカルの main は **`9c30e32`** (前書のチャットの merge)。本チャットの merge は **`c71fa73`** (commit `fe849f5` + 統合解消 `2ce0941`)。本書の変更セットは `[archive-split]` token を持つ。
- 完了ゲート: worktree `distracted-galileo-6027de` で 2 回。統合前 `4012 passed, 2 subtests passed`、統合後 (main `c589785` を取り込んだ状態) **`4018 passed, 2 subtests passed`**、どちらも `judge=PASS`、実行クラスタ差分 0。`tools/tests` は **618 passed** (`finalize.py --tools-tests`)。変異 7/7 red。
- `security/CONTROL_MAPPING.md` は版 **2.25** (不変)。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` は本チャットで **v1.111**、前書のチャットが **v1.112** (回転で v1.107 の行が archive へ移っている。規則どおり)。
- 本チャットの worktree `.claude/worktrees/distracted-galileo-6027de` (branch `claude/distracted-galileo-6027de`) は本書のコミット後に `fold.py` で畳める (統合済み)。

## 2. 本チャットで閉じたもの

| 項目 | 要点 |
|---|---|
| 正本と記録の分離、第 1 段 (Class B: `tools/*.py` に触る。文書移動は A) | 依頼者指示 2026-09-23。設計 `docs/design/DOC_ARCHIVE_SPLIT_V1.md` **v1.2** (設計レビュー 1 回・10 件)、作業指示書 `docs/work-orders/WORK_ORDER_DOC_ARCHIVE_SPLIT_V1.md` (訂正註 13 件)、`docs/archive/README.md` (archive 内で唯一の正本)。**`OPERATING_CONDITIONS.md` §1.16 (78)**: 記録 (引き継ぎ書のうち最新 2 通以外、台帳の版数ログのうち最新 5 版以外) は `docs/archive/<元 path>` に `git mv`、`check_doc_refs` の参照走査と `check_comment_provenance` は走査しない、`change_class` は `docs/archive/` 配下を Class A、空 `.md` ガードと公開値スキャンは archive にも掛かる、正本から記録へは「記録: `docs/archive/...`」の 1 行、回転規則 (新しい引き継ぎ書の変更セットで最新 2 通から外れる分を、台帳の版上げで 6 版目の行を、同時に移す)、既存文書の path 参照は書き換えない (`HANDOVER_X.md:NN` は `git mv` で行番号が変わらない) |
| 移動 | 引き継ぎ書 **38 通** (`git log --follow` 38/38 で移動前の履歴に到達) と台帳の版数ログ **107 行** (v1.106〜「旧 v1.0」。逐語、抽出先は `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md`、先頭 3 行がヘッダ)。走査対象 `.md` は **163 ファイル / 69,071 行 → 127 / 66,230** (main `59facc2` 基準)。族ごとの定義数は不変、参照数は移動ファイル内の参照数 + 新規文書分だけ減り、dangling 0、空 `.md` 0 |
| 検査器 (コードレビュー 1 回・4 件) | `tools/check_doc_refs.py`: `iter_scan_files(include_archive=False)` が参照走査、fallback は `include_archive=True` (空 `.md` ガードは archive を含む)。`tools/change_class.py`: D → C → `docs/archive/` (拡張子を問わず A) → `.md` → B。`tools/check_comment_provenance.py`: glob 経路と tree 経路の非再帰列挙をテストで固定。Known gaps: `check_doc_refs` 4・5、provenance 5、`change_class` 3 (README 索引 5 / 5 / 3) |
| `tools/dev/finalize.py` の欠陥 (指示外、訂正註 12) | staged 済みの削除 (`git mv` の移動元) を `git add -- <path>` に渡して exit 78 で止まった。作業ツリーにも index にも無い path を add から除く形に直し、`tools/tests/test_dev_tools.py::test_finalize_commits_a_staged_rename` + 変異 1 件 |

- 統合時の台帳の版数衝突: 別チャットの R-79 閉止が v1.110 を取っていたので本チャットは **v1.111** に振り直し、D-6 の回転で v1.106・v1.105 の行も archive へ (訂正註 13)。
- 本書の変更セットで `docs/work-orders/HANDOVER_20260923_FABLE5.md` を `docs/archive/docs/work-orders/` へ回転した (D-6。残るのは `HANDOVER_20260924_FABLE.md` と本書)。

## 3. 次の一手

1. **第 2 段** (台帳 §1.0〜§1.0g の更新層を「現在の状態」1 節に畳み、層を archive へ) と **第 3 段** (各設計文書の改版履歴) は指示書 §5 に書いただけで未実施。第 2 段は畳んだ後の §1 の形が依頼者判断待ち (設計 §6 の 1)。
2. 引き継ぎ書は走査面積の 4.5% (3,134 / 69,071 行) にすぎない。面積の主因は `WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1` 3,654 行・`CONFORMANCE_ADAPTER_V1` 3,567 行・`WORK_ORDER_R37_WP0_INVENTORY` 2,328 行であり、面積を減らすには §4 の (g) の裁定と第 2・3 段が要る。
3. 台帳の着手順は前書 §3 のとおり (印なし > 運用開始後)。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(g) 記録と見なすか迷い、動かさなかった文書** (依頼者指示「判断はしない」。設計 §6 の 2): `docs/work-orders/DEPLOY_*.md`、`docs/work-orders/PUBLICATION_GATE_20260906.md`、`docs/work-orders/CCR14_DESIGN_PHASE_RECORD_20260829.md`、`docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md`、閉止済み項目の `docs/work-orders/WORK_ORDER_*.md`、台帳 §8 末尾「R-23 着手前調査資料 (非正本)」、`OPERATING_CONDITIONS.md` 自身の改版履歴。`docs/code-history/` は provenance の登録簿 = 正本で、動かさない。
- **(h) 第 2 段の「現在の状態 1 節」の形** (設計 §6 の 1)。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

1. **`git mv` の移動元は staged 済みの削除で、作業ツリーにも index にも無い。** `git add -- <path>` は `pathspec did not match` で失敗する (finalize は直した。手で add するときも同じ)。
2. **`git log --follow` は commit 後にしか繋がらない。** stage 中は `git diff --cached -M --summary` の `rename (100%)` で確かめ、`--follow` は commit 後に取る。節の抽出は rename ではないので `--follow` は繋がらず、出所はヘッダ 3 行が担う。
3. **同日の並走チャットは台帳の版数で衝突する** (前書 §5 の 1 と同じ事象、本チャットは統合時に発覚 = `finalize` exit 76)。統合直前に `git log -1 main` と台帳の先頭行を読み、衝突したら `git merge main` で解消して版数を振り直し、回転規則を再適用する。
4. **変異の 2 edit のうち片方が「寄与しない」という指摘は実測で確かめる。** provenance の非再帰条件 `"/" not in p[len(peer_prefix):]` は固定幅スライスのため archive の path を弾いており、1 edit に減らすと緑のままだった (コードレビュー 3)。
5. **zsh では `$VAR` が語分割されない。** 複数 path をコマンドに渡すときは `$(cat file)` か配列で渡す。1 引数に潰れると `read_lines` が None を返して「参照 0 件」に見える (本チャットの前計測で一度起きた)。

## 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 設計レビュー 1: 空 `.md` ガードの fallback が `iter_scan_files` を共有し archive 除外が漏れる | 直した | fallback は `include_archive=True`。完了条件 2a/2b + 変異 2 件 |
| 設計レビュー 2: 抽出ファイルは `git log --follow` が繋がらない | 直した | 完了条件 (2) を移動 38 通に限定、抽出はヘッダ 3 行で担保 |
| 設計レビュー 3: 監査照合の照合者が不在 | 直した | 照合者は監督 (§1.13 の 74 の S 列を準用) |
| 設計レビュー 4: `docs/archive/README.md` は正本なのに記録規則の内側 | 直した | README を唯一の正本と明記、書き換え規則の対象外 |
| 設計レビュー 5: OC §0 の「`docs/work-orders/` 配下」が引き継ぎ書で偽になる | 直した | 注記を規則形 (最新 2 通を除き archive) にした |
| 設計レビュー 6: 回転規則 D-6 に機械検査が無い | 既知の穴 (§1.12 の 71) | `check_doc_refs` Known gaps 5。製品の欠陥は通らない (置き場の手順)。前々書の指し方は D-6 に足した |
| 設計レビュー 7: provenance の列挙 3 経路のうち 1 経路しか固定しない | 直した | glob 経路と tree 経路を 4a/4b で固定 |
| 設計レビュー 8: archive への新規作成が A になる | 既知の穴 (§1.12 の 71) | `change_class` Known gaps 3。移動元は `--no-renames` で元クラス、新規作成は監督の `git status` と `--allow` が受け止める |
| 設計レビュー 9: `RM`:NNN 引用 97 件のずれ | 観察 | 以前から陳腐化 (P-6 は :133 でなく :386)。D-6 で版数ログが定数長になり以後の累積ずれは止まる。利用者は気づかず、§0.1 も破らない |
| 設計レビュー 10: 期待削減が目的節に無い | 直した | 設計 §1 に 3,239 行 (4.7%) と「目的は面積より分離」 |
| 設計レビュー (クラス註): OC §1 追加に依頼者確認の記載が無い | 直した | 改版履歴の根拠欄に「依頼者指示 2026-09-23 をもって充足」 |
| 設計レビュー (補足): archive の `.md` は `check_scan_readability` からも外れる | 直した | Known gaps 4 に明記 |
| コードレビュー 1: R-17 節の断言「fallback は参照走査と同じ scope」が偽 | 直した | docstring 2 箇所を書き換え |
| コードレビュー 2: `docs/archive/README.md` の ID 参照が解決されない (直せる正本なのに) | 既知の穴 (§1.12 の 71) | Known gaps 4 に例外として記録。同ファイルは設計の版上げと同時にしか直さない |
| コードレビュー 3: 変異 4b の 2 edit のうち非再帰条件は寄与しない | 観察 (指摘は実測で否定) | 1 edit では test_4b が緑のまま (`got=green`)。2 edit が正しい。訂正註 11 |
| コードレビュー 4: monkeypatch の `**kwargs` が緩い | 直した | `lambda repo_root, *, include_archive=False: []` |
