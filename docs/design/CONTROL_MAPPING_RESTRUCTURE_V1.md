# CONTROL_MAPPING 再編設計 (R-22 問い 2)

## 0. 版数・位置づけ

- **現行版: v0.3 (2026-09-14)。** 設計レビュー 2 回目 (最終) の指摘を、監督裁定によりすべて反映した。
- 旧版: v0.2 (2026-09-14) は設計レビュー 1 回目と目標形の裁定を反映した版。v0.1 (同日) は初稿。
- 対象は `security/CONTROL_MAPPING.md` の**形だけ**である。主張の文は変えない。`spec/`、`security/SECURITY_INVARIANTS_V1.md`、`security/CONTROL_MAPPING_HISTORY.md`、`conformance-tests/CONDITIONS.md`、両 peer のコードは変えない。
- 変更クラスは全体で Class D (`security/`)。Class C (`conformance-tests/`) と Class B (`tools/`) の変更を含む。
- **非目標**: 内容の訂正・更新。見つけた陳腐化は §8 に列挙だけする。

## 1. 裁定と問題

| 項目 | 内容 |
|---|---|
| 裁定 (R-22 問い 2) | 「全て推奨で進めてください」(依頼者、2026-09-14)。`CONTROL_MAPPING.md` を開発プロセス衛生 v2 を待たず、単独の Class D 変更として早めに再編する。再編前後で文が欠けないことを機械照合する (roadmap §8 R-22 行) |
| 裁定 (証拠要件) | 「(i)で進めてください」(依頼者、2026-09-14)。§6 |
| 裁定 (目標形) | 「推奨で」(依頼者、2026-09-14)。表をやめ、見出しの階層と箇条書きにする (§2) |
| 現状 (base `65a9896`) | 124 行。SI-00〜SI-15 の 16 行・4 列の単一表、`## CCR-14 …` 節、`## Rule` 節 |
| 問題 | diff の単位は物理行である。現行は 1 行 = 1 invariant で、SI-14 行 27,950 字、SI-08 行 20,315 字。1 語の訂正でも数万字の行が diff に出る |

## 2. 目標形

```
## SI-00 Single-Compromise Containment        <- 旧 Invariant セルを逐語で

[history](CONTROL_MAPPING_HISTORY.md#si-00)    <- 旧 Common セルから移す

### r2db-api

#### Control

- <主張>
- <主張>

#### Evidence

- <主張>

#### Status

- —

### MitateDB-api
(同形)

### Common
(同形)
```

- 節の順は SI-00〜SI-15 で、その後に `## CCR-14 …` と `## Rule` を内容不変で置く。
- SI 節の中で空行でない行は、history リンク、固定見出し、`- ` 行の 3 種類だけである (§5 で強制する)。
- 主張 1 つが箇条書きの 1 行になる。軸の中では旧セル内の順序を保つ。主張が無い軸は `- —` と明示する。
- 見出しは英語 (`Control` / `Evidence` / `Status`)。ファイル本文が英語のためである。
- 最長の物理行は約 1,400 字になる (最長の主張は SI-08 r2db-api の 1,382 字。レビュー実測)。

**更新漏れの検出**: 訂正の diff は該当する主張の 1 行に閉じる。漏れは 2 つの読み方で見つける。(1) 全節の `#### Status` を一覧にして読み、開示された限界・未達が今も正しいかを確かめる。(2) 同じ SI の `### r2db-api` と `### MitateDB-api` で同じ `####` 見出しを対比し、片 peer にしか無い主張を点検する。空の軸は `- —` なので、書き忘れと区別できる。

**却下した形**:
- 表 (peer 行・軸列 / 軸行・peer 列): 1 行が (SI, peer) 又は (SI, 軸) の全体になり、最長行は 15,141 字 / 17,526 字である。
- 表 (`Scope | Axis | Text`、1 行 = 1 主張): 最長行は約 1,400 字だが、主張ごとに列の繰返しが付く。依頼者裁定で (b) を採った。

**preamble の変更** (これ以外は変えない。V6 で照合する):

| # | 箇所 | 変更 |
|---|---|---|
| P1 | Update convention (7〜20 行) | 置換対。各旧句は 1 物理行の中に 1 回だけある: L10 `current row below` → `current claim below` / L13 `so a row's own` → `so a section's own` / L14 `Each row keeps` → `Each section keeps` / L17 `holds exactly one` → `holds no` / L19 `do not add a second one, and keep every cell as one continuous` → `do not add one, and keep every claim as one bullet on one` / L20 `` no raw `\|` or embedded newline inside a cell `` → `no embedded newline inside a claim` |
| P2 | Cell-length cap measurement (22〜29 行) | 置換対: L22 `Cell-length cap` → `Length cap` / L23 `longest cell is still` → `longest (SI, subsection) block is still` / L24 `control/evidence cell, now` → `block, now` / L26 `MAX_CELL_LENGTH` → `MAX_BLOCK_LENGTH`。段落末に 2 文を足す: `` A block is one subsection's claims (r2db-api, MitateDB-api or Common) joined by single spaces. Each physical line is also capped at `MAX_LINE_LENGTH = <N>`. ``。`<N>` は生成器が計算する (生成したファイルの最長行を 100 字単位で切り上げる) |
| P3 | 3 行目の直後 | `Version: **2.0** (2026-09-14; structure only, content unchanged -- docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md)` |
| P4 | 5 行目の直後 | `` Each claim is one bullet under its invariant, subsection (r2db-api / MitateDB-api / Common) and axis (Control / Evidence / Status); `- —` marks an axis with no claim. `` |

- 旧 P1・P2 段落は、WP-2 が本書の実施記録へ逐語で残す。HISTORY は見出しが SI ID だけに限られ、登録テストが集合一致を強制するので置けない。
- P2 が指す 2026-09-06 の測定記録 (15,065 字、余裕 135 字) は、登録テストのコメントに残す。WP-1 はコメントを書き直すときにこの記録の文を消さない。

**参照側の影響**: WP-1 で grep を再実行し、変更は 0 件とする。次の 2 件は理由を付けて据え置く。`conformance-tests/test_c10_no_bypass_material_on_the_wire.py:29` の「peer-local SI-12 row」は、SI-12 節の peer 小節を一意に指す。`conformance-tests/test_conditions_register.py:42` の「SI-14's r2db-api cell」は、2026-09-06 の測定の記述 (履歴) である。

## 3. 分解と割当

### 3.1 分解 (旧セル → 主張)

0. base に `\|` 又は `<br` があれば、生成も照合も赤で止まる (GFM は code span 内の `\|` を表の中でだけ解除するので、箇条書きへ移すと描画が変わる)。base `65a9896` にはどちらも 0 件である。
1. Common セルから `\s*\[history\]\(CONTROL_MAPPING_HISTORY\.md#si-\d{2}\)` を除去する。分解はその後に行う。
2. 左から走査し、backtick の開閉と、backtick の外の括弧の深さを追う。切れ目の候補は、backtick の外で深さ 0 の位置だけである。
3. 切れ目は 2 種類ある。(a) `.` 又は `;` の直後に空白が続く位置。句読点は前の主張に残す。ただし直前が `vs.` / `e.g.` / `i.e.` / `...` で終わる場合は切らない。(b) 太字ラベル `\*\*[^*]+?(\*\*:|:\*\*)` の直前。
4. 各主張は前後の空白を除く。中は 1 文字も変えない。空の主張は捨てる。

### 3.2 割当 (主張 → 軸)

用語:
- **本文**: 主張から末尾の `.` `;` `:` を 1 つ除いたもの。
- **語数**: backtick span を 1 語と数え、残りを空白で分けた数。
- **ラベル**: 主張の先頭にある太字ラベル `\*\*([^*]+?)(\*\*:|:\*\*)` の中身 (末尾の `:` を除く)。又は、太字でないラベル `^(Stated limit( \([^)]*\))?|Same stated limit):` の中身。
- R2 以外の正規表現は大小を区別しない。

| 優先 | 条件 | 軸 |
|---|---|---|
| R0 | 下の上書き表の (SI, peer, 主張の先頭句) に一致する | 表の軸 |
| R1 | ラベルが `^(disclosed\|acceptance boundary\|deployment (precondition\|caveat)\|not bound\|two limits\|stated limit\|same stated limit)\b` に一致する | Status |
| R1b | R1 の主張から、`.` で終わる最初の主張 (R1 の主張自身を含む) までの後続の主張 | R1 と同じ軸 |
| R2 | 主張が `^(This\|That\|These\|It\|Its\|Both\|Such\|The same)\b` で始まり (大小区別)、同じ (SI, peer) に直前の主張がある | 直前の主張と同じ軸 |
| R3 | 本文が `\b(TBD\|not yet)\b` を含む。又は `\bgaps?\b` を含み、かつ `\bnot a (\w+ )?gap\b` を含まない | Status |
| R4 | 主張が `Evidence:` で始まる。又は本文が backtick span、`,`、`(`、`)`、`and`、`or`、空白だけでできている | Evidence |
| R5 | 本文が `\b(tests?\|review)$` に一致し、語数が 8 以下 | Evidence |
| R6 | 上のどれにも当たらない | 旧 peer 列は Control、旧 Common 列は Evidence |

**R0 上書き表** (全件。各行はちょうど 1 つの主張に一致しなければならず、一致 0 件又は 2 件以上なら生成は赤で止まる。適用はログに `R0` と出る):

| SI | peer | 主張の先頭句 | 軸 | 理由 |
|---|---|---|---|---|
| SI-00 | Common | `All four registered plugs currently resolve` | Status | 未到達の分岐という残余の限界 |
| SI-01 | MitateDB-api | `Local/test-cluster evidence only` | Status | 本番の証拠が `absent` |
| SI-01 | MitateDB-api | `on the one real deployment made so far` | Status | `has not been re-exercised` |
| SI-05 | r2db-api | `Exercised against a real local PostgreSQL 16 cluster only` | Status | `no production evidence` |
| SI-11 | r2db-api | `no production evidence.` | Status | 同上 |
| SI-14 | r2db-api | `The same measurement technique` | Control | R2 が直前の Status を継承してしまう (AST scanner 側の記述) |

- 割当は主張ごとに行う。太字ブロックでまとめて割り当てると、ブロック内のテスト名が Control に入るためである。
- 却下案: R1 の軸を次のラベルまで継承する。実測では約 45 件が逆に誤る (例: SI-02 r2db-api の role 分離、SI-14 r2db-api の AST scanner)。
- 参考値 (レビュー実装での概算、R0 適用後): 主張 418 件。Control 304 / Evidence 69 / Status 45。
- 例 (SI-07 r2db-api): `Topology deny rules plus per-credential role/scope records;` → Control (R6)。`negative topology and isolation tests;` → Evidence (R5)。`production containment evidence not yet present.` → Status (R3)。

## 4. 生成と照合

どちらも `tools/` に置き、base rev を引数に取る。照合は生成を import せず、§3.1 の分解を独自に実装する。新ファイル側は箇条書きの行をそのまま主張として読む。このため 2 つの実装の分解が食い違えば赤になる。

| script | 役割 |
|---|---|
| `tools/restructure_control_mapping.py --base <rev>` | 旧ファイル → 新ファイル全体 (preamble の P1〜P4 と P2 の `<N>` を含む) を決定的に出力する。`--log` で主張ごとの割当ログ (SI, peer, 主張の番号, 規則#, 軸) を TSV で出す |
| `tools/check_control_mapping_restructure.py --base <rev>` | 下の V1〜V8 を検査し、集計行を出す |

| # | 検査 | 赤の条件 |
|---|---|---|
| V1 | SI の集合・順序・名前 | 旧 Invariant セルと新しい `## SI-NN <名前>` が逐語・同順で一致しない |
| V2 | (SI, peer) ごとの主張の多重集合 | missing / added / moved が 0 でない (集計の定義は下) |
| V3 | (SI, peer, 軸) ごとの順序 | 箇条書きの並びが旧セル内の順序の部分列でない |
| V4 | history リンク | 節ごとにちょうど 1 つでない。又は fragment が旧行と違う |
| V5 | CCR-14 節・Rule 節 | バイト列が一致しない |
| V6 | preamble | 旧 preamble に P1・P2 の置換と P3・P4 の挿入を施した結果が、新 preamble と逐語で一致しない |
| V7 | 釣り合い | backtick の数が奇数の主張がある。又は backtick の外の括弧が釣り合わない主張がある |
| V8 | 文字の保存 | (SI, peer) ごとに、リンク除去後の旧セルから空白を全部除いたものが、ログ順の主張を連結して空白を除いたものと等しくない。分解の仕様自体に欠陥があって文字が落ちる場合を捕まえる |

**集計の定義**:
- (SI, peer) ごとに、旧の主張の多重集合を O、新の主張の多重集合を N とする。O − N を欠落候補、N − O を追加候補とする。
- **moved**: ある (SI, peer) の追加候補と、別の (SI, peer) の欠落候補に同じ主張があれば、1 対ずつ組にして両方から除き、1 と数える。
- **missing** / **added**: 組にした後に残った欠落候補 / 追加候補の総数。
- **reordered**: V3 に違反する (SI, peer, 軸) の数。
- **unbalanced**: V7 に違反する主張の数。
- 例: 主張 1 つを削除 → `missing=1`。1 語を足す → `missing=1 added=1`。主張を別の SI へ移す → `moved=1`。同じ軸の 2 主張を入れ替える → `reordered=1`。

期待する集計行: `sections=16 blocks=48 claims_old=<N> claims_new=<N> missing=0 added=0 moved=0 reordered=0 unbalanced=0 history=16/16 ccr14=identical rule=identical preamble=identical chars=identical`

割当が妥当かは機械では判定しない。割当ログと監査の突合で見る (§7)。却下案: script を scratchpad の一時物にする — 前例 (Phase 7 WP-7) と同じく証拠を再現できない。

## 5. 登録テストの改修

新しい登録テストは**新形だけ**を検査する。

| 守る性質 | 新形での検査 |
|---|---|
| 形 | ファイルに `\|` 始まりの行が無い。各 SI 節は、history リンクの行 → `### r2db-api` / `### MitateDB-api` / `### Common` の順、各小節は `#### Control` / `#### Evidence` / `#### Status` の順で並ぶ。各軸には `- ` 行が 1 つ以上ある。`- —` はその軸の唯一の行としてだけ使える。SI 節の中で空行でない行は、history リンク、固定見出し、`- ` 行のどれかに限る (散文行や継続行が cap と主張集合を抜けないように) |
| 節の順序 | `## SI-NN` が昇順に並び、その後に `## CCR-14 …`、`## Rule` が来る。他の `## ` 見出しは無い |
| 全 SI が 1 つずつある | SI ID が `security/SECURITY_INVARIANTS_V1.md` の `### SI-NN` と 1 対 1 で一致する。名前は照合しない (SI-03、SI-04 は両文書で名前が違う) |
| SI 重複なし | 節見出しの SI ID に重複が無い |
| history リンク | 節ごとにちょうど 1 つあり、slug が HISTORY の見出しへ解決する |
| HISTORY 見出しの集合一致・節が空でない | 現行と同じ |
| 肥大化の抑止 | 主: (SI, 小節) ごとに、Common も含め、主張を空白 1 つで連結した長さ ≤ `MAX_BLOCK_LENGTH = 15200`。内容不変なので値は旧セル cap を引き継ぐ (SI-14 r2db-api は旧セル・連結後ともに 15,122 字、レビュー実測)。既存の ratchet をそのまま続ける。補助: 物理行の長さ ≤ `MAX_LINE_LENGTH` (P2 の `<N>` と同じ値) |

モジュール docstring と cap のコメントも新形に合わせる。2026-09-06 の測定記録の文は残す (§2)。

## 6. 変更クラスと証拠

Class D である (`tools/change_class.py` の `_D_DIR_PREFIXES`)。**案 (i) を採用した (依頼者裁定 2026-09-14)**: 契約版数は据え置き、その旨を記録して、他の証拠は全部満たす。案 (ii) (§9 の 8 の文言どおり契約版数も更新する) は却下した — `spec/` も Security Invariants も変えないので、更新する版数の対象が無い。

| 要件 (roadmap §9 の 8) | 本件での充足 |
|---|---|
| フェーズ設計文書 | 本書 (レビュー 2 回の後に v1.0) |
| 契約版数 | 据え置く (上記) |
| 設計レビュー 2 回 | 本書に対して 2 回 (v0.1、v0.2) |
| 完了ゲート | root suite の単独実行 (`pytest -q -n 5 --dist loadgroup`)、`pytest tools/tests -q`、`tools/check_doc_refs.py`。CI の集計行は push の再開後 |
| 依頼者裁定の逐語記録 | §1 |
| 版付き security-contract 決定 | P3。`CONTROL_MAPPING.md` に初めて版数 2.0 を付け、本書を決定記録として参照する。構造の変更なので主版とする |

## 7. WP と完了条件↔変異

WP-1 と WP-2 は 1 つの merge で入る。新しい登録テストは旧形で赤になるためである。WP-3 は merge 前に行う。`tools/tests` は `pyproject.toml` の testpaths の外にあり、CI も停止中なので、ゲートでは `pytest tools/tests -q` を明示して実行する。

| WP | 触る | 触らない |
|---|---|---|
| WP-1 script と登録テスト | `tools/restructure_control_mapping.py`、`tools/check_control_mapping_restructure.py`、`tools/tests/test_restructure_control_mapping.py`、`conformance-tests/test_control_mapping_register.py` | `security/` 全部 |
| WP-2 再編本体 | `security/CONTROL_MAPPING.md` (生成 script の出力だけ)、登録テストの `MAX_LINE_LENGTH` (生成器が出す `<N>`)、本書の実施記録 (旧 P1・P2 段落の逐語、規則ごとの件数) | `security/CONTROL_MAPPING_HISTORY.md`、その他全部 |
| WP-3 監査 | なし | 全ファイル |

| WP | 完了条件 | 変異 (対象: 操作) | 赤になるもの |
|---|---|---|---|
| WP-1 | 照合の各検査が働く | fixture の新形で: 主張 1 つを削除 / 1 語を足す / 主張を別の SI へ移す / 同じ軸の 2 主張を入替 / SI 名を 1 字変える / history の fragment を変える / history リンクを 2 つにする / CCR-14 の 1 文字を変える / P1〜P4 以外の preamble 語を変える / 主張の backtick を 1 つ消す / 分解関数を、切れ目の文字を 1 つ落とす版に差し替える | `missing=1` / `missing=1 added=1` / `moved=1` / `reordered=1` / `sections=differs` / `history` 不一致 / `history` 不一致 / `ccr14=differs` / `preamble=differs` / `unbalanced=1` / `chars=differs`。いずれも `tools/tests` の fixture test |
| WP-1 | 生成が §3 どおり | fixture の旧形に R0〜R6 の各規則、R1b、`not a disclosure gap`、太字でないラベル、`Evidence:`、backtick 内の `...`、`vs.`、`. ` の無いリンク直前の主張、`\|` を含め、期待する新形・ログ・赤停止とバイト一致させる。規則 1 つの分岐 (例: `not a … gap` の除外) を消す / R0 の先頭句を一致 0 件にする | fixture test |
| WP-1 | 独立コードレビュー | `tools/` の 2 script と登録テストを、実装担当と別の担当がレビューする。報告に無い変異を 1〜2 種、自分で注入する | 指摘の未解消、又は赤にならない変異 |
| WP-1 | ゲート | `pytest tools/tests -q` | 緑でない |
| WP-2 | 生成の出力が新ファイルと一致 | `restructure_control_mapping.py --base 65a9896` の出力と `security/CONTROL_MAPPING.md` をバイト比較する | 不一致 |
| WP-2 | 照合 0 件 | `check_control_mapping_restructure.py --base 65a9896` | §4 の期待集計行でない |
| WP-2 | 登録テストが実ファイルで働く (変異は復元する) | `## SI-07` 節を削除 / SI-03 と SI-04 の節を入替 / history の fragment を実在しない値に / 1 peer の `#### Status` を削除 / 軸の下に散文行を 1 行足す / `\|` 行を足す / (SI, 小節) を 15,201 字に / 1 行を `MAX_LINE_LENGTH` + 1 字に | 1 対 1 一致テストと HISTORY 集合テスト / 順序テスト / リンクテスト / 形テスト / 形テスト / 形テスト / block cap テスト / line cap テスト |
| WP-2 | ゲート | root suite 単独実行、`pytest tools/tests -q`、`tools/check_doc_refs.py` | 集計行が緑でない |
| WP-3 | 独立の再現と突合 | 生成と照合を自分で実行し、出力・ログ・集計行が WP-2 と一致することを確かめる。実装担当の要約を見ずにログを突合する: R0・R1b・R2・R3 の全件、ラベルの後続主張の全件 (次のラベル又はセル末まで)、SI-08・SI-14 の全主張、R6 から無作為に 10 件。WP-2 の変異を 2 種再現する | 不一致、又は意味上の誤割当が 1 件以上 (R0 への追加で是正し、WP-2 からやり直す) |

新しい test 名は WP-1 で確定する。

## 8. 見つけた陳腐化 (非目標。列挙のみ)

- roadmap R-22 行の 1 列目「SI-14 行 26,012 文字、SI-08 行 5,797 文字」は旧値である (同じ行の裁定に 2026-09-14 の実測 27,950 / 20,315 がある)。
- CCR-14 節の「which this row does not restate verbatim」の「row」は、節の中の文なので現行でも不正確である。
- 主張の中の位置語 (row 51 件、above / below 14 件) は書き換えない。新形では「row」が字義どおりには合わなくなる。節の順は保つので「above」は偽にならない。
