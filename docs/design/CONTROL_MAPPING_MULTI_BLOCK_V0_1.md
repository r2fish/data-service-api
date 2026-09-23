# CONTROL_MAPPING の複数ブロック化 設計メモ v1.0

## 0. 位置づけ

- **状態: 実施済み (2026-09-18)。** WP-1〜WP-3 は main へ統合済みで、実施の記録は §13 にある。WP-4 (記録) が本版である。**受け入れ監査はまだ行っていない。本件は受け入れ監査の後に閉じる。**
- ファイル名は起草時のまま (`CONTROL_MAPPING_MULTI_BLOCK_V0_1.md`) で、版数だけを v1.0 に上げた (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 58 のとおり、他文書からはファイル名で指す)。
- 台帳: `RM:54` (R-50)。前提の再編は `RM:26` (R-22)。`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md:130` の WP-3 は本件の統合後に着手する。
- 本書は設計メモ (v0.1 = 起草、v0.2 = §4 の推奨欄と §12 の監督裁定を記入、v0.3 = 設計レビュー 1 回目の 14 件を反映 (監督裁定 2026-09-18、全件採用)、**v0.4 = 設計レビュー 2 回目の 11 件を反映 (監督裁定 2026-09-18)。設計レビューは 2 回で打ち切り、以後の確認は監督が行う**、**v1.0 = 実施済み。WP-1〜WP-3 の統合の記録と、設計と実施の差の訂正註を足した (2026-09-18、§13)**)。作業指示書は `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md`。契約 (1.8.0) と `security/SECURITY_INVARIANTS_V1.md` には触れない。
- 字数は本書の起草時に `conformance-tests/test_control_mapping_register.py` の `_split_sections` / `_iter_bullets` / `EXPECTED_*` を import して実測した (pytest は実行していない)。
- **基点 (v0.4 時点)**: main `11c98a2` (R-52 の 0014 が入った後)。`security/CONTROL_MAPPING.md` は 8d54b90 と逐語同一 (1,220 行) で、§1・§7〜§9 の実測値と `file:line` の引用はいずれもこの基点で再確認した。着手時の再実測の規律は §10。

## 1. 問題設定 (R-50)

- 上限は `conformance-tests/test_control_mapping_register.py:88` の `MAX_BLOCK_LENGTH = 15200`。ブロック = 1 つの (SI, peer 小節) の 3 軸の `- ` 主張を空白 1 つで連結した長さ (同 `:323-340`)。
- 実測 (上位 2 件のみが残り 200 字未満):

  | ブロック | 長さ | 残り | 軸の内訳 (件数 / 連結長) |
  |---|---|---|---|
  | SI-08 MitateDB-api | 15,194 | 6 | Control 28/10,713、Evidence 11/3,781、Status 3/698 |
  | SI-14 r2db-api | 15,122 | 78 | Control 53/10,496、Evidence 8/1,581、Status 17/3,043 |

- 先例 F-S11 (`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md:1150-1152`) は、SI-08 に入らない証拠のテスト名を SI-09 の Evidence へ 1 行として逃がした個別裁定であり、構造は変えていない。

## 2. 依頼者裁定 (2026-09-18) と却下した 2 案

**採った案 (逐語)**: 「複数ブロックを許す」= 「1 つの不変条件 × peer に小見出しで複数ブロックを許す形に、検査 (conformance-tests) と再編の設計文書・道具を改める」。

**却下**: (1) 現行の主張を詰める (監督の推奨)。(2) 上限の値を上げる。この 3 案の審議は終了しており、本書は再審議しない。

## 3. 守るべき条件

- (i) 上限の目的 (肥大化の抑止、散文行・継続行が上限と主張の集合を抜けないこと。`conformance-tests/test_control_mapping_register.py:49-54`) を弱めない。ブロックを分けるだけで総量が無制限に増える形にしない → §4。
- (ii) 分割は主張の文を 1 字も変えない純粋な移動とし、前後で bullet の多重集合 (SI・peer・axis・本文) の一致を機械的に照合する → §6。
- (iii) 各小ブロックは今のブロックと同じ 3 軸 (Control / Evidence / Status) の形を持つ。
- (iv) `security/SECURITY_INVARIANTS_V1.md` と契約 1.8.0 に触れない。主張の中身を変えない。
- (v) 既存の検査が見ている性質を 1 つも落とさない (`|` 行の不在、節順、SI 集合の 1:1、SI 重複なし、history リンクの解決、HISTORY の集合一致・非空、行長 1,400、preamble の宣言値の一致)。

## 4. 肥大化の抑止の規則 — 候補の比較

| # | 規則 | 抑止力 | 抜け道 | 実装 | 推奨 |
|---|---|---|---|---|---|
| R-a | 小ブロックごとに同じ `MAX_BLOCK_LENGTH` | 1 ブロックの読みにくさは抑えるが、小ブロックを増やせば総量は線形に伸びる | 主題名を付け替えて小ブロックを量産する | 現行の上限検査の対象キーを (SI, peer) から (SI, peer, 小ブロック) に替えるだけ | 採る |
| R-b | 小ブロックに名前 (主題) を必須とし、~~既定の無名ブロックは 1 つまで~~ **【訂正 2026-09-18 (v0.4、監督裁定)】既定 (無名) の小ブロックは各 (SI, peer) に必須で、ちょうど 1 つ、先頭に置く** (名前付きだけの (SI, peer) は赤) | 分割に主題の説明責任を課す。主題に収まらない主張の行き先が常に 1 つ定まる | 名前は自由文字列なので、意味の薄い名前で分けられる | 見出し規則 (§5) と名前の重複禁止・既定の存在の検査 | 採る |
| R-c | 1 つの SI × peer の小ブロック数に上限を置く (例: 既定 1 + 名前付き N) | 総量の上限を「N × `MAX_BLOCK_LENGTH`」に固定する。R-a と組むと天井が閉じる | N を上げる変更自体は検査を通る (値の変更に裁定が要る運用で担保する) | 定数 1 つと件数の検査 | 採る (既定 1 + 名前付き 3 まで) |
| R-d | (SI, peer) 合算の総量上限を `MAX_BLOCK_LENGTH` とは別に置く | 分割しても合算で頭打ちになり、目的 (i) を直接守る | 別の SI へ主張を移せば合算は下がる (F-S11 型の逃がし) | 現行の上限検査を残したまま、per-小ブロックの検査を足す (2 本立て) | 採らない (合算の上限は分割しても頭打ちになり、依頼者裁定の目的を打ち消す) |

- R-a〜R-d は排他ではない。R-a + R-c、または R-a + R-d が天井を閉じる最小の組合せである (事実: R-a 単独では上限が小ブロック数に比例して開く)。
- どの規則を採っても、現行の cap の由来コメント (`conformance-tests/test_control_mapping_register.py:65-87`、2026-09-06 の 15,065 + 135 字の記録) は消さずに残す。

## 5. 小ブロックの見出しの書式

**【退役註 2026-09-24 (R-103、形式 3.0)】** 見出しの書式は据え置きだが、`MAX_NAMED_SUBBLOCKS` (小ブロック数の上限) は形式 3.0 で退役した: 既存の 5 つの named block を据え置き、新規追加は不可とする (`docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §2.1)。

- 事実: peer 小節は h3 (`### r2db-api`)、軸は h4 (`#### Control`)。両者の間に空いている見出しレベルは無い。軸を h5 へ下げると全 16 節 × 3 peer × 3 軸 = 144 見出しを書き換えることになる。
- 事実: `_ANY_H2_RE` / `_HEADING_RE` は `## ` の後に空白を要求するので、h3 を増やしても節の切り出しと history リンクの slug には影響しない。
- **形**: 小ブロックは h3 を重ねて `### <peer> -- <主題>` と書く。例: `### MitateDB-api -- ops inventory`。
  - **既定 (無名) の小ブロックは必須**で、各 (SI, peer) にちょうど 1 つ、その peer の先頭に置く (`### MitateDB-api` の形)。名前付きだけの (SI, peer) は赤。
  - 同じ peer の小ブロックは連続して並べ、peer の出現順は `r2db-api` → `MitateDB-api` → `Common` を保つ。
  - 主題は同じ (SI, peer) の中で一意、主題は本文と同じ英語。
  - 各小ブロックは `#### Control` / `#### Evidence` / `#### Status` を順にちょうど 3 つ持つ (条件 (iii))。空の軸は `- —`。
- **allowlist で検査する (除外フィルタにしない)**: SI 節の中の `### ` 行は次の 2 段を**両方**満たさなければ赤。「既知の形以外を無視する」書き方にすると、未知の h3 が節の中に紛れても緑のまま通る。
  1. `^### (r2db-api|MitateDB-api|Common)( -- \S(?:.*\S)?)?$` に完全一致する (末尾の `\S` が末尾空白を閉じる。`( -- \S.*)?$` の形では `.*` が末尾空白を飲むので閉じない — 実測で確認した)。
  2. 主題 (`--` の後) が `^[\x21-\x7E]+( [\x21-\x7E]+)*$` に一致し、` -- ` を含まない (ASCII の可視文字を半角空白 1 つで区切った語の列。連続空白・全角空白・タブ・2 つ目の ` -- ` を弾く)。
  - 実測 (この 2 段の判定): `### MitateDB-api` = 通る / `### MitateDB-api -- ops inventory` = 通る / 末尾に半角空白 3 つ = 赤 / `### MitateDB-api  -- ops` (空白 2 つ) = 赤 / `### MitateDB-api -- ` (主題が空) = 赤 / `### MitateDB-api -- a -- b` = 赤 / `### MitateDB-api\t` = 赤 / 主題に全角空白 = 赤 / `### Mitatedb-api -- x` (綴り違い) = 赤 / 主題に半角空白 2 つ = 赤。
- 前提: 小ブロックは個別の body として切る。したがって既存の「`### ` と最初の `#### ` の間に空行以外を置けない」検査 (`conformance-tests/test_control_mapping_register.py:265-269` の `axis_preface`) は、そのまま小ブロック単位に効く (現行は peer 単位)。history リンクの行は SI 節の preface にあり、小ブロックの中には入らない (同 `:244-251`)。
- **他文書から小ブロックを指す形**: `SI-08 / MitateDB-api / ops inventory / Evidence` (SI / peer / 主題 / 軸)。既定の小ブロックを指すときは主題を省いて `SI-08 / MitateDB-api / Evidence` と書く。

## 6. 分割の照合 (条件 (ii))

**【退役註 2026-09-24 (R-103、形式 3.0)】** 本節の照合器 `tools/check_control_mapping_split.py` とそのテストは形式 3.0 の移行で削除した (`docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §4 WP-1)。一度きりの道具であり、block 単位の上限とともに退役した。本節の記述は当時の記録として残す。

- 事実: `tools/check_control_mapping_restructure.py` は旧表形を前提とする。`--base <rev>` を `git show` で読み (`:156-164`)、`OldFile` は `|` 始まりの行が無ければ `CheckError("old file has no '|'-started table")` で止まる (`:171-173`)。生成器 `tools/restructure_control_mapping.py:385-387` も同じである。**現行形 → 現行形の照合には、いずれもそのままでは使えない。**
- したがって (ii) の照合は新しく定める。**既存の算法 (`tools/check_control_mapping_restructure.py:410-422`) は踏襲しない** — あれは本文が一致する `missing` と `added` を文書全体で突き合わせて `moved` に畳む global pairing であり、別 SI へ主張が逃げた場合に `missing=0 added=0 moved=1` として緑に見えてしまう。本件で守るのは「どこにも逃げていない」ことなので、次のとおり厳密に突合する。
  1. 分割前 (`git show <base>:security/CONTROL_MAPPING.md`) と分割後 (作業ツリー) の双方から、`- ` で始まる行を (SI, peer, axis, 小ブロック, 本文) の 5 つ組で読む。本文は `- ` の接頭辞を外す以外の正規化をしない (空白だけの差分も `missing`/`added` に出る)。
  2. 多重集合は **(SI, peer, axis, 本文) の 4 つ組**で作り、そのまま突き合わせる。`missing` = 前にあって後に無い、`added` = 後にあって前に無い。**本文一致による global pairing を行わない。** → 別 SI・別 peer への移動は必ず `missing` と `added` の両方に出る。軸の付け替えも 4 つ組が変わるので同じく出る。
  3. `moved` は**小ブロックの付け替えだけ**を数える: 4 つ組が一致し、5 つ目 (小ブロック) だけが変わった bullet の件数。期待値は §7 で列挙した bullet の件数と一致すること (SI-08 = 15 件、SI-14 V2 = 13 件)。列挙に無い bullet が 1 件でも動けば期待値と合わず赤になる。
  4. `- —` は主張ではないので多重集合から除き、**新設・削除を別カウンタ**で出す。WP-2 の期待値は新設 2 (SI-08 名前付きの Status、SI-14 V2 名前付きの Status)、削除 0。
  5. 順序: 各 (SI, peer, axis, 小ブロック) が持つ「元の index の列」が、元の同じ (SI, peer, axis) の列の**部分列**であること。小ブロック間で元 index の区間が重なってよい。例: SI-08 MitateDB-api Evidence は既定 {0, 10}、名前付き {1..9} で、どちらも昇順の部分列である。元に対応の無い bullet (新設・書き換え) は元 index を持たないので、この判定からは除く (`missing`/`added` が既に捕まえる)。
  6. preamble は版数行・書き換えた文・新設の段落と訂正註以外が不変であること、`## CCR-14 …` と `## Rule` の節が逐語で不変であること。
- 期待する集計行:
  - **WP-2 (分割)**: `missing=0 added=0 moved=28 empty_axis_added=2 empty_axis_removed=0 subsequence=ok preamble=as_expected ccr14=identical rule=identical` (`moved` は SI-08 の 15 + SI-14 V2 の 13)。
    - **【訂正 2026-09-18 (v1.0、監督裁定 S-2。作業指示書 §8)】`preamble` は `as_expected` ではなく `identical` / `differs` の 2 値である。** 実装した照合スクリプトは `differs` のときに preamble の unified diff を標準出力へ出し、diff の hunk が確定文言と 1 行ずつ一致することを目視で照合する形にした (集計行だけで「期待どおり」を名乗らせない)。加えて `--expect "<集計行>"` を持ち、集計行が逐語一致しなければ exit 1 になる。**WP-2 の期待語は `preamble=differs`** であり、WP-2 の実測もそのとおりだった (§13.2)。
  - **WP-3 (F-S11 の行を戻す)**: `missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=identical ccr14=identical rule=identical`。本文を書き換えたうえで別の SI へ移すので、4 つ組は一致せず `moved` には入らない (本節の算法 2・3 のとおり)。`missing` の 1 件が SI-09 の旧文、`added` の 1 件が SI-08 の新文であることを目視で照合する。
    - **【訂正 2026-09-18 (v1.0、監督の確定。作業指示書 §7 の 2・§11.4・§12)】WP-3 の実際の期待集計行は `missing=7 added=7 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical` である。** 2 点が変わった。(1) 版を 2.7 のままにせず 2.8 に上げたので `preamble=identical` は成り立たない (`preamble=differs` に訂正)。(2) WP-3 の範囲に (ii) (SI-14 / r2db-api の裸の `::name` の出所の完全形化、7 行の書き換え) が加わったので `missing` / `added` が 1 ずつではなく 7 ずつになる (§8 の訂正註)。実測は §13.3。
- 実装は Q-4 のとおり新規スクリプト。旧表形の 2 つの道具は一度限りの生成の記録として触らない。

## 7. 最初の適用

§1 と本節の字数は、設計レビュー 1 回目が同じ分解で独立に再現した (2026-09-18)。

### 7.1 SI-08 MitateDB-api — `ops inventory` を名前付き小ブロックへ (実測)

- 対象: Control 6 bullet (`security/CONTROL_MAPPING.md:555-560`) = 1,864 字、Evidence 9 bullet (`:565-573`) = 3,138 字。計 15 bullet。
- 分割後 (実測の見込み、連結の空白 1 つを含む):

  | 小ブロック | 内訳 | 長さ | 残り (15,200) |
  |---|---|---|---|
  | `### MitateDB-api` (既定) | Control 22 / Evidence 2 / Status 3 | 10,190 | 5,010 |
  | `### MitateDB-api -- ops inventory` | Control 6 / Evidence 9 / Status 0 (`- —`) | 5,003 | 10,197 |

  合計 15,193 = 現行 15,194 − 1 (連結の空白 1 つが減るため)。主張の文は 1 字も変えない。
- `:565` の「Evidence for the `ops inventory` claims above is …; every name below (`::name` form) is in that ONE file.」は名前付き小ブロックの Evidence の先頭に移る。`above` は同じ小ブロックの Control を指し、`every name below` の及ぶ範囲は `:566-573` に閉じる。別ファイルのテスト名を挙げる `:574` は既定の小ブロックに残るので、この 2 つの指示語は分割後の方が正確になる (文は変えない)。
  - **【訂正 2026-09-18 (v1.0)】本項も §7.2 も、名前付き小ブロックへ**移した側**の指示語しか見ていなかった。**既定の小ブロックに**残った側**が、直前に置かれていた完全形の `<path>::<name>` を失って出所を辿れなくなる形は、起草時の検討に入っていない。SI-08 では実害が無かったが (`:574` は自分でファイル名を名乗る)、SI-14 の r2db-api では既定の小ブロックに裸の `` `::name` `` が 25 出現・24 名残り、実在ファイルは 4 つに分かれていた。WP-3 のコードレビューがこれを見つけ、監督が WP-3 の範囲に足した (§8 の訂正註、§13.3)。
- 残り本体は 10,190 字となり、`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md:77` が挙げる `:548` (SI-08 MitateDB Control、0014 の算式) への追記が可能になる (R-52 WP-3 の前提)。`:548` は既定の小ブロックに入る。

### 7.2 SI-14 r2db-api — 自然な主題の塊は在る (実測)

主題の塊は 4 つある: 制御面の監査 (Control `:932-943`、2,833 字)、`application_audit` (`:944-965`、4,158 字)、`audit_query` の読み取り面 (`:966-976`、2,020 字)、宣言語彙の走査 (`:977-984`、1,482 字)。名前付き小ブロックの案を 2 つ実測した。

| 案 | 小ブロックに移す bullet | 小ブロック長 | 残り本体 |
|---|---|---|---|
| V1 `declared vocabulary` | Control `:977-984`、Evidence `:992-994`、Status `:1014-1015` | 2,561 | 12,560 |
| V2 `audit query` | Control `:966-976` (11 件)、Evidence `:991` `:995` (2 件) | 2,679 | 12,442 |
| V1 + V2 の両方 | 上記の和 | — | 9,880 |

- 採るのは V2 (§12 Q-6)。V1 は Status の帰属に bullet ごとの判断が要るので今回は行わない。
- Evidence `:991` の「The same measurement technique (reading the two `SHOW` timeouts …)」の先行詞は Control `:973` の `visibility_lag_ms` の行であり、V2 では両者が同じ名前付き小ブロックに入る (`:966-976` が Control 側の範囲)。指示語が小ブロックをまたがない。
- **【訂正 2026-09-18 (v1.0)】「指示語が小ブロックをまたがない」は、移した 13 bullet についてだけ成り立つ。** 既定の小ブロックに残った側の裸の `` `::name` `` の出所は見ていなかった (§7.1 の訂正註)。実測 (WP-3): 分割で新たに曖昧になった行は 0 件 (食い違いは分割の前から在った) だが、6 行は直前の完全形が入れ替わった。WP-3 で 6 つの主張 (既定の小ブロック 5 行 + `audit query` の小ブロック 1 行) の出所を完全形に直した (§8 の訂正註、§13.3)。

## 8. F-S11 の 1 行を SI-08 へ戻す (WP-3)

- 対象は `security/CONTROL_MAPPING.md:657` の 1 bullet、実測 **1,074 字** (SI-09 MitateDB-api Evidence)。
- **確定した直し方 (§12 Q-3)**: 括弧書き `(the claim itself is SI-08's MitateDB-api item (6) bullet; its evidence sits here, next to the migration it depends on)` を**直前の半角空白ごと削除するだけ**とし、言い換えない。削除後の bullet は 954 字で、冒頭は「`` `ops inventory` item (6) reads the value 0013 sets: `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_is_confirmed_by_default_bootstrap_alone`, … ``」となり、単独で読める (実測で確認した。`sets` の直後に `:` が続き、以降はテスト名の列挙のみ)。削除後の 1 行の逐語は WP-3 の実施記録に載せる。
- 移送後の実測: SI-08 の `ops inventory` 小ブロックは 5,003 → **5,958** 字 (残り 9,242)、SI-09 MitateDB-api は 12,793 → **11,718** 字。どちらも上限に触れない。
- **戻す論拠**: 主張の本体と証拠が同じ小ブロックに揃い、F-S11 が字数だけを理由に分けた状態が解消する。item (6) の証拠は SI-08 Evidence (`:572`) にも既にあり、現状は同じ item の証拠が 2 節に分かれている。
- **Update convention と HISTORY の掛かり (事実)**: 規約 (`security/CONTROL_MAPPING.md:11-24`) は「訂正は現行行を書き換え、置き換えられた旧文を逐語で HISTORY へ移す」と定める。文言は *書き換え* を対象としており、節をまたぐ *移動* には言及が無い。先例でも HISTORY への追記が生じたのは主張 1 行を**書き換えた**ときであり (`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md:1118` 訂正註 F-4、`:1158` F-CM)、F-S11 の**移動そのもの**では HISTORY に何も足していない。
  - 本 WP は括弧書きの削除を伴うので**訂正**に当たる。旧文 1 行 (1,074 字) を逐語・無編集で `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ移すことを完了条件にする。
- **【訂正 2026-09-18 (v1.0、監督裁定。作業指示書 §10・§11.6 の 2・§12)】WP-3 の範囲は本節の (i) だけではない。** 本節と §12 Q-3 は F-S11 の 1 行を戻すこと (以下 (i)) だけを想定していた。WP-2 のコードレビューが、**既定の小ブロックに残った側**の指示語・出所の問題 (§7.1・§7.2 の訂正註) を見つけたので、監督が次の (ii) を WP-3 の範囲に足した。純粋な移動 (条件 (ii)) の枠では直せず、版 2.8 の訂正として扱う必要があったためである。
  - **(ii)**: SI-14 / r2db-api の 6 つの主張 (既定の小ブロック 5 行 + `audit query` の小ブロック 1 行) で、行の最初の裸の `` `::name` `` の直前に実在ファイルのパスを入れ、その行から出所が辿れる形にした。旧文 6 行は逐語・無編集で `security/CONTROL_MAPPING_HISTORY.md` の **SI-14 節**へ移した。
  - **食い違いは分割の前から在り、分割が新たに曖昧にした行は 0 件である** (WP-3 の起草時の実測。作業指示書 §11.2 の実測 3)。したがって (ii) は分割の後始末ではなく、分割が可視化した既存の陳腐化の訂正である。
  - 監督は案 (ii)-a (例外の一覧を 1 bullet 足す。+1,285 字) を却下し、案 (ii)-b (各主張がその場で自分の出所を持つ。+182 字) を採った (作業指示書 §11.6 の 2)。
- **【訂正 2026-09-18 (v1.0)】** 本節の「item (6) の証拠は SI-08 Evidence (`:572`) にも既にある」以下の実測値と `:657` の位置は起草時 (base `11c98a2`) のものである。統合後の実測は §13.5。

## 9. 追随が要る現物

| 現物 | 触点 | 何が要るか |
|---|---|---|
| `conformance-tests/test_control_mapping_register.py:139-163` | `_split_sections` | 小ブロックの切り出し (h3 の重複を許す) |
| 同 `:224-293` | peer 見出しを 3 個に固定する形状検査 | 「peer ごとに既定 1 つ + 名前付き 0〜3、順序保存、既定が先頭」へ改める。§5 の allowlist で完全一致を要求。軸 3 つと `axis_preface` の検査は小ブロック単位に |
| 同 `:296-320` | `_iter_bullets` | peer 単位から (peer, 小ブロック) 単位へ。**落とし穴**: 現行は peer 名が完全一致しない `### ` を `continue` で読み飛ばし、最初に一致した軸で `return` する。小ブロック対応でこの内側の `return` を残すと、名前付き小ブロックの bullet が丸ごと集計から落ちたまま緑になる (上限検査も多重集合も抜ける)。§10 の必須テスト (a) がこれを捕まえる |
| 同 `:323-340`, `:88`, `:65-87` | 上限検査と `MAX_BLOCK_LENGTH`・由来コメント | §4 の R-a/R-b/R-c の検査を足す。由来の記録は消さない |
| `security/CONTROL_MAPPING.md:9`, `:26-33`, `:5` | preamble の 2 つの文と版数行 | `:9` の「Each claim is one bullet under its invariant, subsection … and axis …」と `:33` の第 2 文「A block is one subsection's claims (r2db-api, MitateDB-api or Common) joined by single spaces.」は分割後に**偽になる**ので書き換える。**旧文は HISTORY へ移さない** — `security/CONTROL_MAPPING_HISTORY.md` は SI ごとの主張の置き場で preamble の置き場が無く、見出しの集合一致を登録テスト (`:422-432`) が強制するため。代わりに preamble の中に日付付きの訂正註として旧文を逐語で残す。書き換えは**同じ行の中**で行い、新設の段落と訂正註は `:33` の**後ろ**に置く (`:33` の行番号を動かさないため。§9.1) |
| 同上 (注意) | `test_control_mapping_md_declares_the_same_max_line_length_as_this_file` (`:357-373`) | `MAX_LINE_LENGTH = (\d+)` を `search` で最初の 1 件だけ読む。訂正註に旧文を逐語で置くと同じ文字列が 2 度現れるが、最初の出現は `:33` のままなので判定は変わらない (事実)。訂正註を `:33` より前に置くと壊れる |
| — (規約の解釈) | Update convention | **同じ (SI, peer) の中の小ブロック間の移動は「訂正」ではない** (主張の文が 1 字も変わらないため)。したがって HISTORY への移送を伴わない。節をまたぐ移動で文を書き換える WP-3 だけが訂正に当たる (§8) |
| `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` §2・§5 | block/axis 形の設計原本 | 目標形の図と §5 の表に小ブロックを反映 (~~v0.5 として~~。既存行は消さない)。**【訂正 2026-09-18 (v1.0)】版数は v0.5 ではなく v1.1 である。** 同書は 2026-09-14 に既に v1.0 (確定) であり、v0.5 は存在しない版であった。WP-4 で v1.1 に上げた |
| `tools/restructure_control_mapping.py:385-387`, `:173-267` | 旧表形からの一度限りの生成器、`AXES_TABLE_REL` | 再実行できない (旧表形の revision が入力)。docstring に「本表は 2026-09-14 の一度限りの生成の入力であり、小ブロックの割当は含まない」の 1 行だけ足す |
| `tools/check_control_mapping_restructure.py:171-173`, `:560` | 旧表形前提の照合 | 触らない (§6)。`:560` は逐語 `blocks_count = len(sections) * len(PEERS)` であり、小ブロックを数えない (ブロック数 = 節数 × peer 数 の固定) |
| `tools/control_mapping_axes.tsv` | 列 `si peer index head axis` (419 行) | 小ブロックの列を持たない。(SI, peer, 旧セル内 index) で軸を pin する表であり、同じ (SI, peer) の中で bullet を並べ替えない限り内容は不変 (事実: 分割は軸と本文を変えない) |
| `tools/tests/test_restructure_control_mapping.py` / `tools/tests/test_comment_provenance.py` | 上記 2 ツールの fixture テスト | どちらも不変。後者は `CONTROL_MAPPING.md` をパス解決の例として使うだけで構造依存なし (`tools/check_comment_provenance.py:360-372`) |
| `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md:77` (§4 の追随一覧) | `security/CONTROL_MAPPING.md` の `:548` `:641` `:647` `:650` `:659` `:5` | 行番号が動く (§9.1)。**R-52 の WP-3 で実測し直して同一覧を更新する。** `:548` は SI-08 の既定の小ブロックに入り、余裕 5,010 字が空くので同 WP の前提は成立する |
| `conformance-tests/test_c10_no_bypass_material_on_the_wire.py:29`、`conformance-tests/test_conditions_register.py:42`、`conformance-tests/CONDITIONS.md:24` | 散文中の「row」「cell」表記 | 機械的依存は無い。R-22 で理由を付けて据え置いた先例に倣う |

- CI ワークフローに `CONTROL_MAPPING` を機械的に読む job は無い (grep 0 件)。

### 9.1 `file:line`・版数・ブロック名で引く既存文書 (WP-2 / WP-3 の完了条件)

事実: `tools/check_doc_refs.py` は ID 族のトークン (`SIMPLE_FAMILIES` `:251`、`EXTERNAL_PREFIXES` `:323`) だけを検査し、`file:line`・版数・ブロック名は一切見ない。ずれは自動検出されないので、下表を完了条件 (監査照合) に入れて実測で確かめる。訂正は引用元の文書に訂正註を足す形で行い、既存の行は書き換えない。

| 引用元 | 引用 | 指す先 | 影響 | 直し方 |
|---|---|---|---|---|
| `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md:802`、`PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md:83,358,374,921,960`、`docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md:479,1043` (8 箇所) | `:33` | Length cap measurement 段落 | **ずれない** (§12 Q-7 のとおり新しい段落と訂正註を `:33` の後ろに置くため。段落の中の文は書き換わるが行番号は同じ) | 不要 |
| `docs/work-orders/HANDOVER_20260906_FABLE.md:108`、`HANDOVER_20260907_FABLE.md:61` (2 箇所) | `:33` | 同上 | **ずれない** | 不要 (引き継ぎ書は履歴として書き換えない。`docs/work-orders/OPERATING_CONDITIONS.md:3`、`RM:464`) |
| `docs/design/CODE_COMMENT_PROVENANCE_V1.md:135` | `:41` | SI-00 r2db-api の `#### Control` | **ずれる** (preamble に足す段落と訂正註の分) | 訂正註 |
| `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md:2033,2471,2594` | `:538` | SI-08 MitateDB Control (`execution_ms`) | **ずれる** (同上。名前付き小ブロックは Status の後に置くので分割自体では動かない)。**【訂正 2026-09-18 (v1.0)、WP-2 のコードレビューの実測】3 つ目に挙げた `:2594` は誤りである。** 同書 `:2594` は `CH-0538` (comment-history の欠番 ID) の行であり、`security/CONTROL_MAPPING.md:538` を引いていない。`:538` を引くのは同書の「## 4. 訂正註」の 2 箇所で、WP-2 はその 2 箇所 (`:2041`・`:2479` が引く `:538`) に訂正註を足した (§13.2) | 訂正註 |
| `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md:65` と §4 の一覧 (`:77`) | `:5` / `:548` / `:641` `:647` `:650` `:659` | 版数行 / SI-08 / SI-09 | `:5` は**ずれない** (挿入位置より上)。`:548` は preamble の分、`:641`〜`:659` は preamble + SI-08 の小ブロックの見出し行 + WP-3 の 1 行の分だけ**ずれる** | R-52 WP-3 で実測し直す |
| `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md:697` | 「`security/CONTROL_MAPPING.md` Version 2.6 の SI-09 の MitateDB-api ブロック」 | 版数 + ブロック | 版 2.7 と WP-3 の移動で**偽になる** | 訂正註 (WP-2 と WP-3 の両方で) |
| 同 `:693` | 「runbook §10.8 の 3 行は … `security/CONTROL_MAPPING.md` の Version 行・Evidence・Status と一致する」 | 版数 + Evidence | 同上 | 訂正註 |
| `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.8 の受理記録 | — | — | **無効化しない** (事実: 受理記録が版を持つのは §10.6/§10.7/§10.10 であり、runbook 内の `CONTROL_MAPPING` への参照 7 箇所はいずれもファイル単位で版も行番号も引かない) | 不要 |
| 本書 §7・§8 の `:555-560` `:565-573` `:657` ほか | — | SI-08・SI-09 の bullet | **ずれる** (分割そのもので動く) | 本書を v1.0 にするときに実測し直す。**【済 2026-09-18 (v1.0)】実測し直した結果は §13.5 の対応表に置いた** (§7・§8 の本文の値は起草時の記録として残す) |

## 10. 変更クラス・レビュー・WP の粗い切り方

- 変更クラス: `security/` 配下と `conformance-tests/` 配下の両方に触れるので、`RM:9` の 8 の表より **D** (重い方を採る)。
- ~~設計レビュー: 契約に触れないので **1 回** (`RM:9` の 3)。~~ **【訂正 2026-09-18 (v0.3、監督裁定)】設計レビューは 2 回とする。** 根拠: `RM:9` の 8 の D 行は「C の全部 + …」であり、C 行が「設計レビュー 2 回」を要求する。契約に触れないので `RM:9` の 3 だけを読むと 1 回になるが、クラスの表の字義を優先する。**【追記 2026-09-18 (v0.4)】2 回とも完了した (1 回目 → v0.3、2 回目 → v0.4)。以後の確認は監督が行う。**
- **D 行に対する明示の例外 (根拠と日付を残す)**: `RM:9` の 8 の D 行が求める「版付きの security-contract 決定」は本件では要らない。主張の中身・Security Invariants・契約のいずれも変えず、文書の構造と検査だけを変えるためである。先例は R-21 (`RM:25`)・R-22 (`RM:26`) で、いずれも D を採りつつ「security-contract の変更ではない」旨をコミットに明記した。裁定は監督、日付は 2026-09-18 (§12 Q-5)。
- `conformance-tests/` を触るので、WP を branch へ取り込む前に**監督の root suite 単独実行**が要る (`RM:9` の 10 の三段の「統合前」)。
- 検査の作り替えでテスト件数を減らすと `conformance-tests/COLLECTION_FLOOR` を割る。件数が減らない形 (既存のテストを置き換えるのではなく、純関数への切り出し + パラメタ化で増やす) にする。`COLLECTION_FLOOR` の更新は完了ゲートで監督のみが行う (`docs/work-orders/OPERATING_CONDITIONS.md` の 25)。
- **着手時に実測し直す (作業指示書の完了条件に入れる)**: 照合の base rev と §7・§8 の字数は、WP に着手した時点の main で測り直す。R-52 の WP が並行で `security/CONTROL_MAPPING.md` を動かすため、本書の数値と食い違うことがある。**食い違ったら期待値を後から合わせず、設計 (本書) へ戻して数値を更新する。**
- WP (4 本、直列):
  - **WP-1 検査と道具の改修**: `conformance-tests/test_control_mapping_register.py` の形状・上限検査を小ブロック単位に改め、§4 の規則を検査に足す。§6 の照合スクリプトを用意する。
    - 検査の本体は `text` を引数に取る**純関数** (節・小ブロックの切り出し、ブロック長、形の違反の列挙) へ切り出す。テストは 2 系統で同じ純関数を呼ぶ: (1) 合成 fixture のパラメタ化テスト、(2) 現物を `_read()` で読んで渡すテスト。
    - **変異は fixture の上で赤を見る** — 現物に名前付き小ブロックが 0 件の時点でも空振りしない。変異の例: 小ブロックの上限検査を外す / 既定の小ブロックが無い形を許す / 無名の小ブロックを 2 つ許す / 小ブロックの 3 軸の欠けを許す / 小ブロック名の重複を許す / 小ブロック数の上限 (`MAX_NAMED_SUBBLOCKS`) を外す / `### ` の allowlist を除外フィルタに変える / 主題の追加検査 (§5 の 2 段目) を外す。fixture の赤の例には、主題の末尾空白・全角空白・` -- ` 2 つを含める。
    - 照合スクリプトの変異: **本文一致の global pairing を復活させる** (別 SI へ 1 件動かした fixture が緑になったら赤) / **部分列の検査を外す** (軸の中で順序を入れ替えた fixture が緑になったら赤)。
      - **【訂正 2026-09-18 (v1.0、監督裁定 S-3。作業指示書 §8)】`moved` の数え方。** §6 の 3 の字義 (「4 つ組が一致し、5 つ目だけが変わった件数」) は、**旧側と新側で 4 つ組の一致する bullet を対応付け、小ブロック名が変わった件数を数える**ことを指す。実装の初版は「新側で名前付き小ブロックに載っている件数」を数えており、分割済みの文書の自己照合で `moved=1`、WP-3 型で `moved=2` になって、WP-3 の期待値 `moved=0` が原理的に出なかった。対応付けの形に直し、変異 `S3-moved-ignores-old-subblock-name` を足した。
    - **必須のテスト**: (a) SI 節の中の `- ` 行の数 = 拾った bullet の数 + `- —` の行の数 (現物の実測は **519 = 476 + 43**。拾い漏れがあれば赤。§9 の `_iter_bullets` の落とし穴を捕まえる)、(b) 名前付き小ブロック単独で `MAX_BLOCK_LENGTH` を超える fixture が赤。
      - **【訂正 2026-09-18 (v1.0、監督裁定 S-1。作業指示書 §8)】(a) の 519 / 476 / 43 を絶対値で pin しない。** 実装の初版は `EXPECTED_TOTAL_DASH_LINES = 519`・`EXPECTED_TOTAL_EM_DASH_LINES = 43`・`EXPECTED_TOTAL_COLLECTED_BULLETS = 476` の 3 定数を置いたが、WP-2 が `- —` を 2 本新設するだけで 521 / 45 になり、主張を 1 件足す将来の変更 (R-52 の WP-3 を含む) のたびに 476 も動く — 登録簿に主張を足すだけの変更が毎回 `conformance-tests/` を触る形になってしまう。**3 つとも置かない。** (a) が守る「拾い漏れ」の性質は、**節ごとの恒等式**「`- ` 行の数 = 拾った bullet + `- —` の行」と、空振りを防ぐ**錨** (SI 節の数 = 16、拾った bullet の合計 > 0) で守る。移動の前後の一致は `tools/check_control_mapping_split.py` が担う。
      - **【訂正 2026-09-18 (v1.0)】変異の件数。** 本節が挙げた例は 8 + 2 の 10 件だが、作業指示書 §2.3 の完了条件に 1 対 1 で対応させると 15 件 (登録テスト側 11 + 照合スクリプト側 4) になる。差し戻しで S-2・S-3 の変異を足した実施の件数は **20 件**で、20 件とも `expect=red got=red` だった (§13.1)。
  - **WP-2 分割の適用**: `security/CONTROL_MAPPING.md` の SI-08 MitateDB-api と SI-14 r2db-api (V2) を分け、preamble の 2 つの文を書き換え、訂正註・新しい段落・版数行を足す。完了条件は §6 の WP-2 の集計行で通ること、分割後の字数が §7 の表と一致すること、§9.1 の該当行に訂正註を足したこと (後 2 者は変異を持たないので**監査照合**とし、照合の出力行・実測値・訂正註の差分を逐語で本書に残す)。
  - **WP-3 F-S11 の行を戻す**: §8 のとおり括弧書きを削除して SI-08 の名前付き小ブロックへ移し、旧文 1 行を `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ逐語で移す。`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` の F-S11 の行に訂正註を足す (§12 Q-3)。完了条件は §6 の WP-3 の集計行、削除後の 1 行の逐語記録、HISTORY への移送、`:693`/`:697` への訂正註。
  - **WP-4 記録**: `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` の目標形の更新、本書の v1.0 化、`RM` の R-50 行の決着と R-52 WP-3 の解除。

## 11. 依頼者・監督に伺う問い

- **Q-1** (§4): 肥大化の抑止の規則は R-a〜R-d のどれを採るか (組合せ可)。R-c を採る場合の小ブロック数の上限値、R-d を採る場合の合算上限値も併せて。
- **Q-2** (§5): 小ブロックの見出しを `### <peer> -- <主題>` とする案でよいか。主題の言語 (英語) と一意性の範囲 ((SI, peer) の中) を含めて。
- **Q-3** (§8): `security/CONTROL_MAPPING.md:657` の 1 行を SI-08 の `ops inventory` 小ブロックへ戻すか。戻す場合、行中の「its evidence sits here」の書き換えを伴うため訂正扱いとし、旧文を `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ逐語で移すという理解でよいか。
- **Q-4** (§6): 照合は新規スクリプト (A) と `tools/check_control_mapping_restructure.py` への新形モード追加 (B) のどちらにするか。
- **Q-5** (§10): 変更クラス D として、R-21・R-22 と同じく「security-contract の変更ではない」旨を明記した 1 コミットで足りるか (版付きの security-contract 決定は不要という理解でよいか)。
- **Q-6** (§7.2): 今回 SI-14 r2db-api も分けるか。分ける場合 V1 / V2 / 両方のどれか。
- **Q-7** (§9): `security/CONTROL_MAPPING.md` の版数は 2.6 → 2.7 でよいか。Update convention 段落へ小ブロックの定義を足す位置は冒頭規約 (`:9`) の直後でよいか。

## 12. 監督裁定 (2026-09-18、v0.2 / v0.3 / v0.4)

依頼者裁定 (複数ブロックを許す) の下で、§11 の問いを次のとおり定める。設計レビュー 2 回 (v0.3・v0.4 が対象) をもって確定とする。

- **Q-1**: R-a + R-b + R-c を採る。1 つの (SI, peer) は既定の小ブロック 1 つ (**必須**) と名前付きの小ブロック **3 つまで** (定数 `MAX_NAMED_SUBBLOCKS = 3`)。天井は 4 × `MAX_BLOCK_LENGTH` で閉じる。値を上げる変更は監督裁定を要する (由来コメントに書く)。R-d は採らない。
- **Q-2**: `### <peer> -- <主題>` の案を採る (主題は英語、(SI, peer) の中で一意、既定の小ブロックが先頭で必須)。allowlist は §5 の 2 段で閉じる。
- **Q-3**: 戻す。主張と証拠を同じ小ブロックに揃える (F-S11 は字数だけを理由にした置き場だった)。純粋な分割 (条件 (ii)) とは**別の WP** (WP-3) にし、分割の照合が通った後に行う。
  - **確定した文言**: 当該行の括弧書き `(the claim itself is SI-08's MitateDB-api item (6) bullet; its evidence sits here, next to the migration it depends on)` を直前の半角空白ごと**削除するだけ**とし、言い換えない。削除後の文が単独で読めない場合だけ、実装担当は止まって報告する (起草時の実測では読める。§8)。
  - 文の書き換えは訂正として扱い、旧文 1 行を `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ逐語で移す。
  - **F-S11 の裁定の行 (`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md:1150-1152`) は消さない。** 同書に訂正註を追記し、「R-50 の複数ブロック化により置き場の前提 (SI-08 に字数が無いこと) が解消したため証拠を SI-08 へ戻した」旨と根拠・日付 (2026-09-18) を添える (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56)。
  - **【追記 2026-09-18 (v1.0、監督裁定)】本項が定めた (i) に加えて、WP-3 は (ii) (SI-14 / r2db-api の裸の `::name` の出所の完全形化、6 つの主張) を範囲に含めた。** 経緯と却下した案は §8 の訂正註、確定文言は作業指示書 §11・§11.6。
- **Q-4**: (A) 新規の照合スクリプト (`tools/check_control_mapping_split.py`、標準ライブラリのみ、`tools/tests` に自己検査)。旧表形の 2 つの道具は一度限りの生成の記録として触らない (docstring への 1 行の註だけ足す)。
- **Q-5**: Class D。主張の中身・Security Invariants・契約を変えないので版付きの security-contract 決定は要らず、R-21・R-22 と同じく「security-contract の変更ではない」旨をコミットに明記する。依頼者の確認は 2026-09-18 の裁定 (本メモ §2) をもって充足。設計レビューは 2 回とする (根拠と例外の記述は §10)。
- **Q-6**: SI-14 の r2db-api も今回分ける。V2 (`audit query`。Control と Evidence だけで帰属が明瞭) を採り、V1 は Status の帰属に bullet ごとの判断が要るので今回は行わない。
- **Q-7**: 版数は 2.6 → 2.7。~~小ブロックの定義は冒頭の規約の直後に置く。~~ **【訂正 2026-09-18 (v0.4、監督裁定。本項が裁定の正本)】** 小ブロックの定義の段落は、冒頭の規約 (`:9`) の直後ではなく preamble の **最後の段落 (`security/CONTROL_MAPPING.md:33`) の直後** に置く。preamble の中の訂正註 (§9 の書き換えた 2 文の旧文) はさらにその後ろに置く。`:33` を `file:line` で引く既存の 10 箇所 (うち引き継ぎ書 2 箇所は書き換えられない) の行番号を動かさないためである (§9.1)。

## 13. 実施の記録 (2026-09-18)

作業指示書は `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md` (WP-1〜WP-4 の直列)。監督の確定と訂正註 1〜5 は同書 §7〜§12 にある。本節はそこからの要約であり、逐語の確定文言・変異の一覧・差し戻しの経過は同書が持つ。

### 13.1 WP-1 — 検査と道具 (main `e0d2cb5`、作業 `885a6aa`)

- 登録テスト `conformance-tests/test_control_mapping_register.py` を `text` を引数に取る純関数 + 合成 fixture のパラメタ化テストの形に組み替え、照合スクリプト `tools/check_control_mapping_split.py` を新設した (Q-4 の案 (A))。
- 経過: 実装 → コードレビュー 1 回目 (重 2・中 3・低 2) → 監督裁定 S-1〜S-3 (作業指示書 §8) → 差し戻し 1 → コードレビュー 2 回目 (差し戻し不要)。
- 実測: `conformance-tests/test_control_mapping_register.py` = `34 passed` (基点 11)、`tools/tests` = `507 passed` (基点 492。照合スクリプトの自己検査 15 件)。**変異 20 件はすべて `expect=red got=red`**、復元は sha256 2 回で照合済み。完了ゲート = `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。
- 設計との差 (訂正註は §6・§10 の該当行に置いた): S-1 (絶対値の pin を置かない)、S-2 (`preamble` は 2 値 + diff + `--expect`)、S-3 (`moved` の数え方)、変異の件数。
- 既知の制約: 現物に名前付き小ブロックが 0 件の間、名前付き小ブロックに関する現物側の検査は fixture の上でだけ赤を示せた (WP-2 の後は現物側も効く)。

### 13.2 WP-2 — 分割の適用、版 2.7 (main `bd17175`、作業 `0b25907`)

- `security/CONTROL_MAPPING.md` の SI-08 / MitateDB-api と SI-14 / r2db-api を、既定の小ブロック + 名前付きの小ブロック 1 つ (`ops inventory` / `audit query`) に分けた。
- 照合 (実装担当とレビュー担当がそれぞれ実行): `missing=0 added=0 moved=28 empty_axis_added=2 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`、exit 0。**純粋な移動 28 件**で、preamble の diff の hunk は版数行・`:9`・`:33`・新しい段落・訂正註だけであり、確定文言と逐語で一致した。道具に頼らない照合 (レビュー): `- ` 行の多重集合の差は `- —` の新設 2 行だけ (522 → 524、削除 0)。
- 字数 (実測、設計 §7 の表と一致): SI-08 / MitateDB-api 既定 **10,190** (残り 5,010) / `ops inventory` **5,003**、SI-14 / r2db-api 既定 **12,442** / `audit query` **2,679**。着手時の実測は設計 §7 の bullet の `file:line`・字数と完全に一致した。
- `:5`・`:9`・`:33` の行番号は不変、最長行 1,384 < 1,400。版 2.6 → **2.7**。
- 引用元への訂正註: `docs/design/CODE_COMMENT_PROVENANCE_V1.md` (v0.20)、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の「## 4. 訂正註」の 2 箇所、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` (v0.13)。**§9.1 の 3 つ目の引用 (`:2594`) は誤りだった** — 訂正註は §9.1 の該当行に置いた。
- `pt.py` = `34 passed` / `507 passed`、`public_value_scan.py` = `total_flagged=0`、`check_doc_refs.py` = `0 dangling references`。完了ゲート = `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。

### 13.3 WP-3 — F-S11 の 1 行を戻す + 出所の完全形化、版 2.8 (main `d2e7333`、作業 `89fcab9`)

- **(i)**: SI-09 / MitateDB-api / Evidence にあった item (6) の証拠の 1 行 (1,074 字) から括弧書きを直前の半角空白ごと削除し、`SI-08 / MitateDB-api / ops inventory / Evidence` の item (6) の証拠の直後へ移した。旧文 1 行は逐語・無編集で `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ移した (同節の流儀に合わせて先頭の `- ` は外した)。
- **(ii)**: SI-14 / r2db-api の 6 つの主張 (既定の小ブロック 5 行 + `audit query` の小ブロック 1 行) で、行の最初の裸の `` `::name` `` の直前に実在ファイルのパスを入れた。旧文 6 行は逐語・無編集で HISTORY の SI-14 節へ移した。案 (ii)-a (例外の一覧を 1 bullet 足す) は却下した (§8 の訂正註)。
- 照合 (実装担当・レビュー担当・監督がそれぞれ実行): `missing=7 added=7 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`、exit 0。preamble の diff は版数行と再実測の 1 文だけ。道具に頼らない照合 (レビュー): `- ` 行の多重集合の差は、括弧書き 120 字 (直前の半角空白を含む) の削除 1 対と、行の最初の `` `:: `` の直前へのパスの挿入 6 対だけ。
- `::name` の総当り (レビュー): SI-14 / r2db-api の既定 34 出現で不一致 0、SI-08 の `ops inventory` 43 出現はすべて `MitateDB-api/tests/test_ops_inventory.py` に実在、移した行の 11 名も実在。
- 字数 (実測): **SI-14 / r2db-api 既定 12,624 (残り 2,576。この文書の最長ブロック)**、SI-08 / `ops inventory` **5,958**、SI-09 / MitateDB-api 既定 **11,718** (設計 §8 の見込みと一致)。SI-08 / MitateDB-api 既定は 10,190 のまま (残り 5,010)。最長行 1,384 < 1,400。`:5`・`:9`・`:33` は不変。版 2.7 → **2.8**。
- 引用元への訂正註: `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` の F-S11 の裁定 (`:1150-1152`。1 字も変えていない) の後、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` の 3 箇所 (v0.14。表題の版を改版履歴に同期)、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` (v0.21。行番号に頼らない所在を併記)。
- `pt.py` = `34 passed` / `507 passed`、`public_value_scan.py` = `total_flagged=0`、`check_doc_refs.py` = `0 dangling references`。完了ゲート = `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。

### 13.4 設計と実施の差 (訂正註の置き場)

| # | 差 | 訂正註の場所 |
|---|---|---|
| 1 | 絶対値の pin (519 / 476 / 43) を置かない | §10 の必須テスト (a) |
| 2 | `preamble` は `as_expected` ではなく `identical` / `differs` の 2 値 + diff + `--expect` | §6 の WP-2 の期待集計行 |
| 3 | `moved` は旧側と新側の対応付けで数える | §10 の照合スクリプトの変異 |
| 4 | 変異の件数 (設計の例 10 件 → 実施 20 件) | §10 の必須テスト (a) |
| 5 | WP-3 は版を 2.8 に上げるので `preamble=differs`、範囲に (ii) が加わるので `missing=7 added=7` | §6 の WP-3 の期待集計行 |
| 6 | WP-3 の範囲に (ii) が加わった (既定の小ブロックに残った側の指示語・出所) | §7.1・§7.2・§8・§12 Q-3 |
| 7 | `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` の版は v0.5 ではなく v1.1 | §9 の該当行 |
| 8 | §9.1 の `WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md:2594` は `security/CONTROL_MAPPING.md:538` を引いていない | §9.1 の該当行 |

### 13.5 §7・§8 の `file:line` の実測し直し (§9.1 の最終行)

起草時 (base `11c98a2`、version 2.6) → 統合後 (main `d2e7333`、version 2.8) の対応。§7・§8 の本文の値は起草時の記録として残す。

| 本書の記述 | 起草時 | 統合後 (実測) |
|---|---|---|
| §7.1 SI-08 / MitateDB-api / `ops inventory` / Control 6 bullet | `:555-560` | `:601-606` |
| §7.1 同 Evidence | `:565-573` (9 件) | `:610-619` (10 件。うち `:618` が WP-3 (i) で SI-09 から戻した行) |
| §7.1 の「Evidence for the `ops inventory` claims above …」の 1 行 | `:565` | `:610` |
| §7.1 の「別ファイルのテスト名を挙げる」1 行 (既定に残る) | `:574` | `:589` (SI-08 / MitateDB-api / 既定 / Evidence) |
| §7.2 SI-14 / r2db-api / `audit query` / Control 11 bullet | `:966-976` | `:1050-1060` |
| §7.2 同 Evidence 2 bullet | `:991`・`:995` | `:1064`・`:1065` |
| §8 の対象 1 bullet (F-S11 が SI-09 へ逃がした行) | `:657` | `:618` (SI-08 / MitateDB-api / `ops inventory` / Evidence) |
| §9.1 の `CODE_COMMENT_PROVENANCE_V1.md:135` が引く先 | `:41` | `:71` (同書 v0.21 が行番号に頼らない所在を併記) |
| §9.1 の `WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` が引く先 | `:538` | `:568` |
| §9.1 の `MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md:77` の一覧 | `:548` `:641` `:647` `:650` `:659` | `:578` `:684` `:690` `:693` `:701` (R-52 の WP-3 で同一覧を更新する) |
| 同上 `:5` (版数行) と preamble の `:9`・`:33` | `:5` `:9` `:33` | 不変 |

### 13.6 残り

- **受け入れ監査 (evidence-auditor) を 1 回行う。** 本件はその後に閉じる。
- R-52 の WP-3 (`security/CONTROL_MAPPING.md` への追記) の前提は解除された。SI-08 / MitateDB-api の既定の小ブロックに 5,010 字の余裕があり、同 WP が追記する `:578` (0014 の算式) は既定の小ブロックに入る。行番号の材料は 13.5 の最終行。
- WP-1 のコードレビューが、本件と無関係な teardown の error を実測した (`tools/dev/pt.py` で `conformance-tests/` のファイルと `tools/tests` を 1 回の pytest に結合した場合)。当面の受けは「2 回に分けて回す」(作業指示書 §8) で、原因は台帳に **R-58** として別件で起票した。

### 13.9 本書が引く登録テストの行番号について (監督の註、2026-09-19)

§1・§3・§4・§5・§6・§9 が引く `conformance-tests/test_control_mapping_register.py:NN` は、**WP-1 の改修の前 (main `f5432e4` の時点、440 行) の行番号**である。WP-1 (`885a6aa`) で同ファイルは 917 行になり、行番号は全部ずれた (例: `MAX_BLOCK_LENGTH` は `:88` → `:97`、`_split_sections` は `:139-163` → `:184`、`_iter_bullets` は `:296-320` → `:478`)。本書は設計時点の記録として行番号を書き換えない。現物を辿るときは**関数名・定数名**で探す。
