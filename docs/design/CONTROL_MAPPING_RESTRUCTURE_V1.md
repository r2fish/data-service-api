# CONTROL_MAPPING 再編設計 (R-22 問い 2)

## 0. 版数・位置づけ

- **現行版: v1.1 (2026-09-18)。** R-50 (複数ブロック化) の統合を受けて、§2 の目標形と §5 の表に小ブロックを反映した。既存の行は 1 行も消していない (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。根拠は `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` (v1.0) と `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md`。
- **【訂正 2026-09-18 (v1.1)】直下の「現行版: v1.0」の行は v1.0 時点の記述である (行として残す)。**
- **現行版: v1.0 (2026-09-14)。** WP-3 監査の合格 (3 回目) と root suite ゲート (`3340 passed`) を経て確定した。
- v0.4 (同日): 1 回目の WP-3 監査の不合格を受けた監督裁定により、規則 R0〜R6 を廃止し、軸の割当を割当表 `tools/control_mapping_axes.tsv` へ移した。
- 旧版: v0.3 (同日) は設計レビュー 2 回目の反映。v0.2 は設計レビュー 1 回目と目標形の裁定の反映。v0.1 は初稿。
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

**【追記 2026-09-18 (v1.1)、R-50】小ブロック (`### <peer> -- <主題>`)**: 依頼者裁定「複数ブロックを許す」(2026-09-18) により、1 つの (SI, peer 小節) は**小ブロック**に分かれてよくなった。上の図と §5 の表は小ブロックを含まない v1.0 時点の記述であり、行として残す (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。目標形は次のように拡がる。

```
### MitateDB-api                       <- 既定 (無名) の小ブロック。各 (SI, peer) に必須・ちょうど 1 つ・先頭
#### Control / #### Evidence / #### Status

### MitateDB-api -- ops inventory      <- 名前付きの小ブロック。(SI, peer) あたり 0〜3 つ
#### Control / #### Evidence / #### Status
```

- 同じ peer の小ブロックは連続して並べ、peer の出現順 (`r2db-api` → `MitateDB-api` → `Common`) は保つ。主題は同じ (SI, peer) の中で一意で、本文と同じ英語で書く。各小ブロックは 3 軸をちょうど 1 つずつ持ち、主張の無い軸は `- —` と明示する。
- 上の 52 行目「SI 節の中で空行でない行は、history リンク、固定見出し、`- ` 行の 3 種類だけ」は成り立ち続ける。固定見出しの h3 が小ブロックの見出しを含む形に拡がるだけである。history リンクの行は SI 節の preface にあり、小ブロックの中には入らない。
- 他文書から小ブロックを指す形は `SI-08 / MitateDB-api / ops inventory / Evidence` (SI / peer / 主題 / 軸)。既定の小ブロックを指すときは主題を省く。
- 現物は `security/CONTROL_MAPPING.md` version 2.8 で、名前付きの小ブロックは `SI-08 / MitateDB-api / ops inventory` と `SI-14 / r2db-api / audit query` の 2 つである。見出しの書式と allowlist の逐語は `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §5・§12 Q-1・Q-2。

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

軸の割当は意味の判断であり、規則では決めない。**正本は割当表 `tools/control_mapping_axes.tsv` である。** 全 418 主張の軸を 1 行ずつ明示する。

| 列 | 内容 |
|---|---|
| `si` / `peer` | 主張の属する (SI, peer) |
| `index` | (SI, peer) 内の旧セル順 (0 始まり) |
| `head` | 主張の先頭部分 (逐語) |
| `axis` | `Control` / `Evidence` / `Status` |

**判定基準** (表の作成と監査に共通):
- 軸は主張の意味で決め、小節には依存しない。
- 限界、未実施、配備依存、開示 → Status。
- テスト、conformance 条件、計測を証拠として挙げる → Evidence。
- それ以外 (統制の実現) → Control。
- peer 間で同じ内容の主張は同じ軸にする。
- 1 つの主張に内容が混在するときは、主節の軸にする。
- **優先順位 (監督裁定 2026-09-14、2 回目の WP-3 再監査)**: 上の 2 項目が競合するとき (1 つの主張の中で主節の軸と peer 間一致とが違う軸を指すとき)、主節の軸を優先する。peer 間一致はそもそも内容が同じ場合だけ適用し、内容が違えば peer ごとに独立して判定する。

却下: 規則 (R0〜R6) による推定。1 回目の WP-3 監査で、意味上の誤割当が 38 件、判断を要する群が 13 個出た (§9.5)。

## 4. 生成と照合

**【退役註 2026-09-24 (R-103、形式 3.0)】** 本節が定めた生成器 `tools/restructure_control_mapping.py`・照合器 `tools/check_control_mapping_restructure.py`・割当表 `tools/control_mapping_axes.tsv` とそのテストは、形式 3.0 の移行 (`docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §4 WP-1) で削除した。一度きりの道具であり、旧表形を前提としていたため。本節の記述は当時の記録として残す。

どちらも `tools/` に置き、base rev を引数に取る。照合は生成を import せず、割当表も読まない。§3.1 の分解を独自に実装し、内容不変だけを検査する。新ファイル側は箇条書きの行をそのまま主張として読むので、2 つの実装の分解が食い違えば赤になる。

| script | 役割 |
|---|---|
| `tools/restructure_control_mapping.py --base <rev>` | 旧ファイルを分解し、割当表を引いて新ファイル全体 (preamble の P1〜P4 と P2 の `<N>` を含む) を決定的に出力する。表と主張が 1 対 1 でない場合 (行の欠落・余剰・重複)、`head` が主張の先頭と一致しない場合、`axis` が 3 値以外の場合は赤で止まる。`--log` で (SI, peer, index, axis) を TSV で出す |
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

割当が妥当かは機械では判定しない。割当表を監査が §3.2 の判定基準で突合する (§7)。却下案: script を scratchpad の一時物にする — 前例 (Phase 7 WP-7) と同じく証拠を再現できない。

## 5. 登録テストの改修

**【退役註 2026-09-24 (R-103、形式 3.0)】** 本節の `MAX_BLOCK_LENGTH` / `MAX_LINE_LENGTH` と block 単位の上限検査は形式 3.0 で退役し、上限は主張単位 (`MAX_CLAIM_LENGTH`: Control 250 / Evidence 300 / Status 300) に移った (`docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §2.1・§4)。本節の記述は当時の記録として残す。

新しい登録テストは**新形だけ**を検査する。

| 守る性質 | 新形での検査 |
|---|---|
| 形 | ファイルに `\|` 始まりの行が無い。各 SI 節は、history リンクの行 → `### r2db-api` / `### MitateDB-api` / `### Common` の順、各小節は `#### Control` / `#### Evidence` / `#### Status` の順で並ぶ。各軸には `- ` 行が 1 つ以上ある。`- —` はその軸の唯一の行としてだけ使える。SI 節の中で空行でない行は、history リンク、固定見出し、`- ` 行のどれかに限る (散文行や継続行が cap と主張集合を抜けないように)。**【訂正 2026-09-18 (v1.1)、R-50】** peer 小節は 1 つとは限らない。各 peer は**既定の小ブロック 1 つ (必須・先頭) + 名前付きの小ブロック 0〜3 つ**が連続して並ぶ形になり、`### ` 行は §2 の追記が指す allowlist に完全一致することを要求する (未知の h3 を無視しない)。3 軸の順序と `axis_preface` の検査は peer 単位ではなく小ブロック単位に効く |
| 節の順序 | `## SI-NN` が昇順に並び、その後に `## CCR-14 …`、`## Rule` が来る。他の `## ` 見出しは無い |
| 全 SI が 1 つずつある | SI ID が `security/SECURITY_INVARIANTS_V1.md` の `### SI-NN` と 1 対 1 で一致する。名前は照合しない (SI-03、SI-04 は両文書で名前が違う) |
| SI 重複なし | 節見出しの SI ID に重複が無い |
| history リンク | 節ごとにちょうど 1 つあり、slug が HISTORY の見出しへ解決する |
| HISTORY 見出しの集合一致・節が空でない | 現行と同じ |
| 肥大化の抑止 | 主: (SI, 小節) ごとに、Common も含め、主張を空白 1 つで連結した長さ ≤ `MAX_BLOCK_LENGTH = 15200`。内容不変なので値は旧セル cap を引き継ぐ (SI-14 r2db-api は旧セル・連結後ともに 15,122 字、レビュー実測)。既存の ratchet をそのまま続ける。補助: 物理行の長さ ≤ `MAX_LINE_LENGTH` (P2 の `<N>` と同じ値)。**【訂正 2026-09-18 (v1.1)、R-50】** 上限の対象キーは (SI, 小節) から **(SI, 小節, 小ブロック)** に替わった。値 15,200 は据え置き、由来の記録 (2026-09-06 の 15,065 + 135 字) も残している。分割だけで総量が無制限に開かないよう、`MAX_NAMED_SUBBLOCKS = 3` を足して (SI, peer) あたりの天井を 4 × `MAX_BLOCK_LENGTH` に閉じた (`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §4 の R-a + R-b + R-c)。値を上げる変更は監督裁定を要する |

モジュール docstring と cap のコメントも新形に合わせる。2026-09-06 の測定記録の文は残す (§2)。

**【追記 2026-09-18 (v1.1)、R-50】** 本表の検査は R-50 WP-1 で、`text` を引数に取る純関数 + 合成 fixture のパラメタ化テスト + 現物を読むテストの形に組み替えた (`conformance-tests/test_control_mapping_register.py`)。分割前後の照合は、旧表形を前提とする §4 の `tools/check_control_mapping_restructure.py` ではなく、新設の `tools/check_control_mapping_split.py` が担う。§4 の 2 つの道具は 2026-09-14 の一度限りの生成の記録として触っていない (docstring に註を 1 行足しただけ)。経緯と変異の記録は `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §6・§13。

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
| WP-2 再編本体 | `tools/control_mapping_axes.tsv` (§3.2 の判定基準で全 418 行)、`security/CONTROL_MAPPING.md` (生成 script の出力だけ)、登録テストの `MAX_LINE_LENGTH` (生成器が出す `<N>`)、本書の実施記録 (旧 P1・P2 段落の逐語、軸ごとの件数) | `security/CONTROL_MAPPING_HISTORY.md`、その他全部 |
| WP-3 監査 | なし | 全ファイル |

| WP | 完了条件 | 変異 (対象: 操作) | 赤になるもの |
|---|---|---|---|
| WP-1 | 照合の各検査が働く | fixture の新形で: 主張 1 つを削除 / 1 語を足す / 主張を別の SI へ移す / 同じ軸の 2 主張を入替 / SI 名を 1 字変える / history の fragment を変える / history リンクを 2 つにする / CCR-14 の 1 文字を変える / P1〜P4 以外の preamble 語を変える / 主張の backtick を 1 つ消す / 分解関数を、切れ目の文字を 1 つ落とす版に差し替える | `missing=1` / `missing=1 added=1` / `moved=1` / `reordered=1` / `sections=differs` / `history` 不一致 / `history` 不一致 / `ccr14=differs` / `preamble=differs` / `unbalanced=1` / `chars=differs`。いずれも `tools/tests` の fixture test |
| WP-1 | 生成が §3 どおり | fixture の旧形 (backtick 内の `...`、`vs.`、`. ` の無いリンク直前の主張、`\|` を含む) と fixture の割当表から、期待する新形・ログ・赤停止とバイト一致させる。割当表から 1 行消す / 1 行足す / 行を重複させる / `head` を 1 字変える / `axis` を 3 値以外にする | fixture test (いずれも生成が赤で止まる) |
| WP-1 | 独立コードレビュー | `tools/` の 2 script と登録テストを、実装担当と別の担当がレビューする。報告に無い変異を 1〜2 種、自分で注入する | 指摘の未解消、又は赤にならない変異 |
| WP-1 | ゲート | `pytest tools/tests -q` | 緑でない |
| WP-2 | 生成の出力が新ファイルと一致 | `restructure_control_mapping.py --base 65a9896` の出力と `security/CONTROL_MAPPING.md` をバイト比較する | 不一致 |
| WP-2 | 照合 0 件 | `check_control_mapping_restructure.py --base 65a9896` | §4 の期待集計行でない |
| WP-2 | 登録テストが実ファイルで働く (変異は復元する) | `## SI-07` 節を削除 / SI-03 と SI-04 の節を入替 / history の fragment を実在しない値に / 1 peer の `#### Status` を削除 / 軸の下に散文行を 1 行足す / `\|` 行を足す / (SI, 小節) を 15,201 字に / 1 行を `MAX_LINE_LENGTH` + 1 字に | 1 対 1 一致テストと HISTORY 集合テスト / 順序テスト / リンクテスト / 形テスト / 形テスト / 形テスト / block cap テスト / line cap テスト |
| WP-2 | ゲート | root suite 単独実行、`pytest tools/tests -q`、`tools/check_doc_refs.py` | 集計行が緑でない |
| WP-3 | 意味の突合と独立再現 | 割当表の 418 行すべてを、実装担当の要約を見ずに §3.2 の判定基準で突合する。内容不変は、実装の tools を使わずに独立に再現する。WP-2 の変異を 2 種再現する | 不一致、又は意味上の誤割当が 1 件以上 (割当表を直し、WP-2 からやり直す) |

新しい test 名は WP-1 で確定する。

## 8. 見つけた陳腐化 (非目標。列挙のみ)

- roadmap R-22 行の 1 列目「SI-14 行 26,012 文字、SI-08 行 5,797 文字」は旧値である (同じ行の裁定に 2026-09-14 の実測 27,950 / 20,315 がある)。
- CCR-14 節の「which this row does not restate verbatim」の「row」は、節の中の文なので現行でも不正確である。
- 主張の中の位置語 (row 51 件、above / below 14 件) は書き換えない。新形では「row」が字義どおりには合わなくなる。節の順は保つので「above」は偽にならない。

## 9. 実施記録 (WP-2、2026-09-14)

`tools/restructure_control_mapping.py --base a230c6c` (旧 `security/CONTROL_MAPPING.md` は 65a9896 時点から a230c6c まで無変更 -- `git diff 65a9896 a230c6c -- security/CONTROL_MAPPING.md` は空) の出力を `security/CONTROL_MAPPING.md` へそのまま書いた。`tools/check_control_mapping_restructure.py --base a230c6c` の集計行:

```
sections=16 blocks=48 claims_old=418 claims_new=418 missing=0 added=0 moved=0 reordered=0 unbalanced=0 history=16/16 ccr14=identical rule=identical preamble=identical chars=identical
```

`MAX_LINE_LENGTH` は生成器が実測して `1400` を採った (最長物理行 1,384 字 -- `- ` + SI-08 r2db-api の最長主張 1,382 字 -- を 100 字単位で切り上げ)。`MAX_BLOCK_LENGTH` は旧 `MAX_CELL_LENGTH` の 15200 を無変更で引き継いだ (最長ブロックは SI-14 r2db-api、15,122 字 -- 旧セル長と一致)。

### 9.1 廃止規則 R0〜R6 の履歴 (1 回目の WP-2 の実測。v0.4 でこの規則自体を廃止し、コードからも削除した)

以下は規則が正本だった間 (v0.3 まで) の実測記録であり、現在の割当を主張するものではない。現在の軸の正本は割当表 `tools/control_mapping_axes.tsv` であり、その件数は §9.6 に記録する。

| 規則 | 件数 |
|---|---|
| R0 | 6 |
| R1 | 20 |
| R1b | 15 |
| R2 | 8 |
| R3 | 4 |
| R4 | 16 |
| R5 | 13 |
| R6 | 336 |

この時点の軸ごと件数: Control 304 / Evidence 69 / Status 45。1 回目の WP-3 監査 (§9.5) がこの規則ベースの割当に誤りを見つけ、v0.4 の裁定で規則そのものを廃止した。

### 9.2 旧 P1・P2 段落 (逐語、書き換え前)

P1 が指した旧 "Update convention" 段落 (旧 7〜20 行目):

> **Update convention** (phase 7 WP-7 (i), requester ruling 4 --
> `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5):
> 「訂正は現行行を書き換え、旧文は履歴へ移す」-- a correction rewrites the
> current row below in place, and the superseded text it replaces is moved,
> verbatim and unedited, into the per-ID companion file
> `CONTROL_MAPPING_HISTORY.md` (headings there are the bare ID only, e.g.
> `## SI-14`, so a row's own `[history](CONTROL_MAPPING_HISTORY.md#si-14)`
> link resolves to a real GitHub anchor). Each row keeps only today's control
> and its evidence -- test names, `file:line`, and any disclosed scope limits
> -- plus that one link; it is not a place to re-accumulate the next
> correction's own narrative. This file holds exactly one `|`-started table
> (`conformance-tests/test_control_mapping_register.py` parses on that
> assumption); do not add a second one, and keep every cell as one continuous
> line (no raw `|` or embedded newline inside a cell).

P2 が指した旧 "Cell-length cap measurement" 段落 (旧 22〜29 行目):

> **Cell-length cap measurement** (差し戻し rework round 3, 監督裁定 2026-09-06 item
> C-1/B-2; re-measured 2026-09-10, WP-9): this file's longest cell is still
> SI-14's r2db-api control/evidence cell, now 15,122 characters (15,065 on
> 2026-09-06, the figure `conformance-tests/test_control_mapping_register.py`'s
> own comment records). Its `MAX_CELL_LENGTH = 15200` is that 2026-09-06
> measurement plus a 135-char margin, unchanged (78 left today), set independently
> of `conformance-tests/CONDITIONS.md`'s own cap (per C-1: a shared cap left that
> file's own guard nearly inert; design section 13/WP-8 keeps its own copy).

### 9.3 参照側の影響 (grep 再実行)

`security/CONTROL_MAPPING.md` を "row" / "cell" と絡めて参照する `.py` ファイルを再 grep した。据え置いた 2 件は §2 の記載どおり (`conformance-tests/test_c10_no_bypass_material_on_the_wire.py:29` の「peer-local SI-12 row」、`conformance-tests/test_conditions_register.py:42` の「SI-14's r2db-api cell」)。他に `MitateDB-api/src/mitatedb_api/control_plane.py`/`r2db-api/src/r2db_api/control_plane.py` に `CONTROL_MAPPING.md SI-10/SI-02` を指す 2 件のコメントがあるが、"row"/"cell" 語を伴わない単純な参照でありどちらも変更不要だった。変更が要った参照は 0 件。

### 9.4 完了ゲート (実測、v0.4 最終是正後、2026-09-14)

- 生成器出力と `security/CONTROL_MAPPING.md` はバイト一致。
- `check_control_mapping_restructure.py --base a230c6c`: `sections=16 blocks=48 claims_old=418 claims_new=418 missing=0 added=0 moved=0 reordered=0 unbalanced=0 history=16/16 ccr14=identical rule=identical preamble=identical chars=identical`
- `pytest tools/tests -q`: `107 passed`
- `pytest conformance-tests/test_control_mapping_register.py -q`: `11 passed`
- `tools/check_doc_refs.py`: `check_doc_refs OK: 0 dangling references`
- `tools/public_value_scan.py` (変更ファイル 7 件: `security/CONTROL_MAPPING.md`、`conformance-tests/test_control_mapping_register.py`、`tools/restructure_control_mapping.py`、`tools/check_control_mapping_restructure.py`、`tools/tests/test_restructure_control_mapping.py`、`tools/control_mapping_axes.tsv`、本書): `total_flagged=0`
- `tools/check_collection_floor.py`: `COLLECTION_FLOOR check OK: measured=3340 floor=3326 diff=14`
- root suite (`pytest -q -n 5 --dist loadgroup`) 単独実行は監督ゲート待ち (本実装パスは対象外の pytest を起動しない規律のため)。

### 9.5 1 回目の WP-3 監査 (不合格) と裁定 v0.4

- **内容不変**: 監査は実装の tools を使わずに独立に再現し、一致した (48 ブロック、CCR-14 節・Rule 節・preamble を含む)。
- **割当**: 規則による割当に、意味上の誤割当 38 件 (C→E 26、C→S 8、E→S 3、E→C 1) と、判断を要する群 13 個があった。赤条件に該当するので不合格。
- **原因**: 規則の構造にある。「Exercised … by `test`」型の文が既定値で Control に落ちる、R3 の語彙が狭い、R4 が誤爆する。
- **監督裁定 (v0.4)**: 規則を廃止し、割当表を正本とする (§3.2)。WP-2 は割当表の作成からやり直し、WP-3 は表 418 行の意味の突合と内容不変の独立再現を行う。

### 9.6 割当表 (正本) の軸ごとの件数、是正の経過

| 段階 | Control | Evidence | Status | 備考 |
|---|---|---|---|---|
| 規則ベース (廃止、§9.1) | 304 | 69 | 45 | 1 回目の WP-2 の実測 |
| 1 回目の WP-3 是正後 | 264 | 91 | 63 | 誤割当 38 件 + 判断群 13 個 (§9.5) を反映 |
| 2 回目の WP-3 是正後 (最終、v0.4) | 261 | 93 | 64 | §9.7 の 6 行を反映。総 418 件は不変 |

### 9.7 WP-3 再監査 (2 回目) と裁定

1 回目の不合格 (§9.5) → 割当表を是正 (264/91/63) → 2 回目の WP-3 監査で残り 2 件の誤割当 (SI-11 MitateDB-api [4] は主節がテストの記述で Evidence、SI-14 r2db-api [33] は主節が flush の統制で peer の [16] と揃えて Control) と、判断が割れた 4 件 (SI-02 r2db-api [4] は主節が C-14 の vector で Evidence、[18] は Control のまま、[55] と MitateDB-api [31] は runbook 依存の配備開示で Status) を検出。監督裁定 (2026-09-14) でこの 6 行を確定し、判定基準に優先順位「主節の軸 > peer 間の一致 (内容が同じ場合だけ適用)」を追記した (§3.2)。最終件数は §9.6 のとおり (261/93/64)。
