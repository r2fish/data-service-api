# 引き継ぎ — 2026-09-23 (検査器の既知の穴の運用を入れ、`check_doc_refs` の R 族を 3 桁に広げた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260923_FABLE2.md` で、**同書の §4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。

## 1. 現在地

- ローカルの main は **`25bacda`**。
- 最後の root gate は本チャットの木 (`--label docrefs-r3`) で `3987 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` は **603 本**。
- `security/CONTROL_MAPPING.md` は版 **2.25** (不変)、台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` は **v1.104**。
- **進行中: 無し。** 本チャットの worktree は `claude/peaceful-mclean-c8e870` (session worktree。`fold.py` の既定除外 `claude/*` に当たるので、畳むなら `--include 'claude/peaceful-mclean-*'`)。

## 2. 本チャットで閉じたもの

| 項目 | 要点 |
|---|---|
| 検査器の既知の穴の運用 (Class D by path) | main `2fe980d` (commit `a609198`)。`OPERATING_CONDITIONS.md` **§1.12 (71・72)**: 検査器の不完全さは「この穴を通って製品の欠陥 (契約違反・Security Invariant の破れ) が完了ゲートを抜けられるか」の 1 問で判定し、はいなら台帳に起票、いいえなら当該検査器の docstring 末尾の `Known gaps` 節 (not detected / why / caught by) に書いて起票しない。全検査器に節が揃った時点で道具層は完成 (72)。検査器 **22 本** (指定 20 + `test_conditions_register.py` + `test_conformance_docstring_position_refs.py`) の docstring に節、`tools/dev/README.md` に一覧節 (表 22 行 + tools/ 外の R-98)。台帳 **v1.104**: R-96・R-98・R-100 を閉止 (Known gaps へ)、R-73・R-74・R-77 は移管の追記のみ (既に閉止済み)、**R-46 は「はい」で open のまま** (公開化前に直す)。変更クラスは `change_class.py` の機械判定で **D** (`tools/public_value_scan.py` の docstring) であり「A 相当」ではなかった。ゲート `3987`、`tools/tests` 601 |
| `check_doc_refs` の R 族 3 桁化 (Class B) | main `25bacda` (commit `f1f289a`)。R 族だけ `\d{1,2}` → `\d{1,3}` (参照・定義)。定義 99 → **102**、参照 4564 → **4595** (R-100〜R-102 への参照 31 件が検査に入った)、dangling 0。G/P/L は 1〜2 桁、SI/C/CCR は 2 桁のまま。テスト 2 本、変異 3 件赤。Known gaps 項目 1 を「族の桁幅を超える ID は見ない」に書き換え。台帳は 71 に従い起票せず。ゲート `3987`、`tools/tests` 603 |

- R-100 は監督の再現で **道具の盲点ではなかった** (`change_class.py` は当該 path に `A` を出す。呼び手の列挙に無かった path)。
- 判定「いいえ」で閉じた穴のうち、次に触るときの手がかり: R-96 の実測の腐り 1 件 (`MitateDB-api/src/mitatedb_api/backend_postgres.py:1496-1503` が引く r2db の `:1936-1959` は現物では `:2280-2308`) は R-96 行に残してあり、当該塊を次に触る変更セットで来歴検査の経路 (R-68) を通して直す。

## 3. 次の一手

1. **R-79** (prepared statement が効いているかの実測)。**前書 §3 の 1 が「台帳の R-79 行に書き足せ」とした探索ノート (`explore-r78-r79.md`) は、前チャットの scratchpad にしか無く、R-79 行に【追記】は無い (本チャットで確認)。事実は失われたので R-79 は探索からやり直す。**
2. 続いて **R-80**、**R-81**、**R-82**、**R-85**、**R-86**、その後 **R-97**、**R-99**。**R-83**・**R-84** は R-78〜R-82 の結果次第、**R-101**・**R-102** は R-79〜R-82 の後に着手可否を決める (台帳の各行の保留条件を読む)。R-96・R-98・R-100 は閉じたので候補から外れた。
3. 新しい検査器の不完全さが見つかったら、起票の前に `OPERATING_CONDITIONS.md` §1.12 の 71 の 1 問を立てる。「いいえ」なら当該 docstring の `Known gaps` に 3 行を足し、`tools/dev/README.md` の表の件数と要約を直す。
4. fold は `tools/dev/fold.py --min-age-hours 0 --apply` (他チャットの worktree は先に `git worktree lock`)。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(t) R-46 の着手時期。** 判定「はい」で open。公開化 (public flip) の前に必ず直す。Class D (`tools/public_value_scan.py`)。
- **(u) 72 の「全検査器」の外延。** 本チャットは `tools/*.py`・`tools/dev/*.py`・登録テスト 3 本・`tools/tests/test_src_import_readers.py` を対象にした。`tools/tests/` の他のテスト (件数 pin、同型 pin 等) や両 peer の `tests/` の静的検査 (AST scan) には `Known gaps` 節が無い。71 の対象に含めるかは依頼者判断。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

1. **変更クラスは宣言する前に `tools/change_class.py` に通す。** docstring だけの変更でも `tools/public_value_scan.py` に触れば D、`conformance-tests/` に触れば C になる (本チャットの 1 件目)。
2. **台帳の行に追記する前に、引く先の行の現状を読む。** R-77 の残余 R-94 は前日に閉止済みで、監督の初稿 (「R-94 は open」) は drafter の照合で誤りと分かった。
3. **docstring を Python heredoc で書き換えるときは raw string を使う。** `\\d+` のような綴りは通常の文字列では 1 本の backslash になり、`count()==1` の assert で止まる (止まったので被害は無し)。
4. **gate 開始後に 1 ファイルでも触ったら、そのファイルを `pt.py` で別に回す。** 本チャットは R-95 テストの docstring を gate 中に直し、`25 passed` を別途取った。
5. **`tools/` と `conformance-tests/` の docstring は来歴検査の走査外** (`check_comment_provenance.py` の scope は両 peer の `src/` だけ)。同じ変更セットの言い換え規則 (設計 v0.24〜) は掛からない。
6. **drafter が「枠の疑義」を報告したら、文書に書かせず監督が一次資料で裁く。** 本チャットの 6 件の疑義のうち 2 件 (R-94・R-98 の位置) が監督の枠の誤りだった。

- 監督チャットはモデル呼び出しの区切りに達したので、**次は新しいチャットで本書から始める** (`OPERATING_CONDITIONS.md` §1.10 の 67)。
