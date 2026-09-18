# 作業指示書 — R-50 `security/CONTROL_MAPPING.md` の複数ブロック化

## 0. 版数と位置づけ

- **v1.0 (2026-09-18)。** 基点 main `1e11959`。台帳は計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-50**。
- **正本の設計は `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` v0.4** である。本書は枠・裁定・却下案を写さず節番号で指す (`RM` §9 の 9)。依頼者裁定は同 §2、守るべき条件は同 §3、規則は同 §4、見出しの書式は同 §5、照合は同 §6、適用先と字数は同 §7・§8、追随は同 §9・§9.1、WP の切り方とレビューは同 §10、監督裁定は同 §12。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (commit とマージは監督のみ、完了ゲートは監督のみ、道具は `tools/dev/`)。手順: WP-1 → WP-2 → WP-3 → WP-4 の **直列**。コードレビュー (テンプレ 5) は **WP-1・WP-2・WP-3 のそれぞれに 1 回**。受け入れ監査 (テンプレ 6) は**全 WP の後に 1 回**。
- **WP-1・WP-2・WP-3 は、それぞれの統合前に監督が root suite の `tools/dev/gate.py` を単独実行する** (`conformance-tests/` と `security/` に触れるため。設計 §10)。**`conformance-tests/COLLECTION_FLOOR` は触らない** (テストを減らさない限り更新は不要。更新は完了ゲートで監督のみが行う。`docs/work-orders/OPERATING_CONDITIONS.md` の 25)。

### 0.1 変更クラス (`tools/change_class.py` の path 規則と `RM` §9 の 8)

| WP | 機械判定 (下限) | 導出 |
|---|---|---|
| WP-1 | **C** | `conformance-tests/` (C) と `tools/` 配下の `.py` (B) に触り、`security/` に触れない |
| WP-2 | **D** | `security/CONTROL_MAPPING.md` が最重ルール (`security/` 配下) |
| WP-3 | **D** | 同上 (`security/CONTROL_MAPPING.md` と `security/CONTROL_MAPPING_HISTORY.md`) |
| WP-4 | **A** | 触る path が `.md` 3 本だけで、`spec/`・`security/`・`conformance-tests/` の外 |

- **本件全体は Class D** (設計 §10。`security/` と `conformance-tests/` の両方に触れるので重い方を採る)。機械判定は**下限**であり、本表と設計 §10 が正本である。
- 設計 §10・§12 Q-5 のとおり、**版付きの security-contract 決定は要らない**。主張の中身・`security/SECURITY_INVARIANTS_V1.md`・契約 1.8.0 を変えないためである。**各コミットに「security-contract の変更ではない」旨を明記する** (先例 R-21・R-22)。契約版数は **1.8.0 のまま据え置く** (`spec/` に触れない)。

## 1. 共通の枠

### 1.1 読むべき正本

- 設計メモ `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §3〜§10 と §12。**再説明も再審議もしない。**
- `docs/work-orders/OPERATING_CONDITIONS.md` §1.4・§1.5 (特に 32・33・34・35・40)・§1.6・§1.9・§1.10。前例としての manifest は `docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md` (**粒度の手本としてのみ読む**)。

### 1.2 全 WP 共通の触らないファイル

`spec/` 全部、`security/SECURITY_INVARIANTS_V1.md`、`r2db-api/`・`MitateDB-api/` のコード・テスト・migration・runbook、`conformance-tests/` のうち `test_control_mapping_register.py` 以外 (`CONDITIONS.md` を含む。読むだけ)、`conformance-tests/COLLECTION_FLOOR` (§0)、`tools/check_control_mapping_restructure.py` と `tools/restructure_control_mapping.py` の**本体** (WP-1 の docstring の 1 行の註だけが例外。設計 §6・§9)、`tools/control_mapping_axes.tsv` (設計 §9 のとおり内容不変)、`tools/tests/test_restructure_control_mapping.py`・`tools/tests/test_comment_provenance.py`、`.github/`、`CLAUDE.md`、`docs/work-orders/OPERATING_CONDITIONS.md`、引き継ぎ書 (`HANDOVER_*.md`)。

### 1.3 順序と触るファイルの重なり (§1.2 の 16・17)

| 組 | 重なり (実ファイル名) | 扱い |
|---|---|---|
| WP-1 と WP-2 | なし (WP-1 = `conformance-tests/test_control_mapping_register.py`・`tools/check_control_mapping_split.py`・`tools/tests/test_check_control_mapping_split.py`・旧 2 道具の docstring、WP-2 = `security/CONTROL_MAPPING.md` ほか文書) | **直列。WP-2 は WP-1 の統合後**に基点を取り直す |
| WP-2 と WP-3 | `security/CONTROL_MAPPING.md`、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` | **直列。WP-2 → WP-3** (分割の照合が通った後に移送する。設計 §12 Q-3) |
| WP-3 と WP-4 | なし (WP-4 = `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md`・`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md`・`docs/design/ROADMAP_POST_PHASE7_V1.md`) | 直列 |

並行して動かす WP は無い。4 本とも直列である。

**WP-1 と WP-2 の関係 (枠)**: WP-1 の統合時点で現物に名前付き小ブロックは **0 件**である。WP-1 の検査は**その現物 (小ブロック無し) でも緑でなければならない** — 後方互換のためではなく、既定の小ブロックだけの形が §5 の規則の部分集合であるためである。名前付き小ブロックに関する赤は**合成 fixture の上で**見る。

### 1.4 worktree と道具の引数

| WP | worktree | `pt.py` | `mutate.py` |
|---|---|---|---|
| WP-1 | `r50-wp1` | `tools/dev/pt.py -C .claude/worktrees/r50-wp1 -- conformance-tests/test_control_mapping_register.py tools/tests -q` | `tools/dev/mutate.py "$SP/r50-wp1-mutations.json" -C .claude/worktrees/r50-wp1` |
| WP-2 | `r50-wp2` | `tools/dev/pt.py -C .claude/worktrees/r50-wp2 -- conformance-tests/test_control_mapping_register.py tools/tests -q` | (変異なし。§3.4 は全件 監査照合) |
| WP-3 | `r50-wp3` | `tools/dev/pt.py -C .claude/worktrees/r50-wp3 -- conformance-tests/test_control_mapping_register.py tools/tests -q` | (変異なし。§4.3 は全件 監査照合) |
| WP-4 | `r50-wp4` | — (文書のみ) | — |

- `SP` は担当 subagent の scratchpad。実装担当は **root suite・`tools/dev/gate.py`・`tools/dev/finalize.py` を回さない** (§1.10 の 70)。回すのは上表の `pt.py` の対象 (担当ファイルの conformance と `tools/tests`) だけである。道具が REFUSED (75) を返したら待つか監督に上げる (§1.10 の 66)。**`mutate.py` は `expect=red` の実行に `-x` を付ける。** したがって、赤を示したいテストが複数あるときは**変異の項目を分け**、1 変異につき 1 つの test id を名指しする (§1.5 の 33)。

### 1.5 記録の規律

**変異の定義は scratchpad を手放す前に本書の訂正註へ写す** (§1.8 の 57)。監査照合の逐語記録 (実行したコマンド・集計行・`file:line`) の置き場は各 WP の末尾の「記録」の小節とする (§1.5 の 40)。

## 2. WP-1 — 検査と道具 (機械判定 C。本件全体は D)

### 2.1 目的と範囲

設計 §4 (R-a / R-b / R-c)・§5 (見出しの allowlist)・§6 (分割の照合) を現物にする。`conformance-tests/test_control_mapping_register.py` の形状検査と上限検査を **(SI, peer) 単位から (SI, peer, 小ブロック) 単位**へ改め、§6 の照合スクリプトを新設する。**現物の分割は行わない** (WP-2)。検査の本体は `text` を引数に取る**純関数**へ切り出し、テストは 2 系統で同じ純関数を呼ぶ: (1) 合成 fixture のパラメタ化テスト、(2) 現物を `_read()` で読んで渡すテスト (設計 §10)。**テスト件数を減らさない** (既存テストの置き換えではなく、純関数への切り出し + パラメタ化で増やす。§0)。照合スクリプトは `tools/check_control_mapping_split.py` (標準ライブラリのみ、設計 §12 Q-4)、自己検査は `tools/tests/test_check_control_mapping_split.py`。引数の形は設計 §6 の 1 のとおり `--base <rev>` を取り、`git show <base>:security/CONTROL_MAPPING.md` と作業ツリーの現物を突き合わせる。集計行の書式は設計 §6 の「期待する集計行」に一致させる。

### 2.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `conformance-tests/test_control_mapping_register.py`、`tools/check_control_mapping_split.py` (新規)、`tools/tests/test_check_control_mapping_split.py` (新規)、`tools/check_control_mapping_restructure.py` と `tools/restructure_control_mapping.py` の **docstring の 1 行の註だけ** | §1.2 の全 WP 共通、`security/` 全部 (**読むだけ**)、`docs/design/` (記録は WP-4)、`conformance-tests/` の他のファイル |

### 2.3 完了条件 → 変異

変異の `file` は、特記の無い行は `conformance-tests/test_control_mapping_register.py`。「split」は `tools/check_control_mapping_split.py`。赤になる test id は予想であり、実装担当が実名に置き換えて報告する。**赤は合成 fixture の上で見る** (§1.3)。

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| W1-1 | 検査の本体が `text` を取る純関数で、(1) 合成 fixture のパラメタ化テストと (2) 現物を渡すテストの**両系統**が同じ純関数を呼ぶ | **監査照合**: 純関数の名前と 2 系統の呼び出し箇所を `file:line` で逐語記録に残す | — |
| W1-2 | SI 節の中の `### ` 行を設計 §5 の 1 段目の正規表現に**完全一致**で受ける **allowlist** である (既知の形以外を無視する除外フィルタではない)。節の中の未知の h3 は赤 | allowlist を除外フィルタに変える (既知の形に一致しない `### ` を読み飛ばす) | 未知の h3 を含む fixture が赤になるテスト |
| W1-3 | 主題が設計 §5 の 2 段目に一致する (ASCII の可視文字を半角空白 1 つで区切った語の列、` -- ` を 2 つ含まない)。fixture の赤の例に**主題の末尾空白・全角空白・` -- ` 2 つ**を含める | 主題の 2 段目の検査を外す (1 段目だけにする) | 主題の不正形 fixture のパラメタ化テスト (代表 1 件を名指し) |
| W1-4 | 既定 (無名) の小ブロックが各 (SI, peer) に**必須**で、**ちょうど 1 つ**、その peer の**先頭**にある (R-b) | 3 件。(i) 既定が無い形を許す。(ii) 無名を 2 つ許す。(iii) 先頭でない形を許す | (i) 名前付きだけの fixture / (ii) 無名 2 つの fixture / (iii) 既定が 2 番目の fixture |
| W1-5 | 主題が同じ (SI, peer) の中で一意である | 主題の重複の検査を外す | 同じ主題を 2 つ持つ fixture |
| W1-6 | 同じ peer の小ブロックが連続して並び、peer の出現順が `r2db-api` → `MitateDB-api` → `Common` である | 小ブロックの並びの検査を外す (peer が飛び飛びに現れる形を許す) | peer が交互に現れる fixture |
| W1-7 | 各小ブロックが `#### Control` / `#### Evidence` / `#### Status` を順にちょうど 3 つ持ち、`### ` と最初の `#### ` の間に空行以外が無く、`- —` は軸の単独行としてのみ現れる (条件 (iii)。現行の `axis_preface` と `- —` の規則が**小ブロック単位**に効く) | 小ブロックの 3 軸の欠けを許す | 軸が 2 つの名前付き小ブロックを持つ fixture |
| W1-8 | 上限検査の対象キーが **(SI, peer, 小ブロック)** である (R-a)。**必須テスト (b)**: 名前付き小ブロック単独で `MAX_BLOCK_LENGTH` を超える fixture が赤 | 小ブロック単位の上限検査を外す ((SI, peer) 合算に戻す) | 上限超えの名前付き小ブロックの fixture |
| W1-9 | `MAX_NAMED_SUBBLOCKS = 3` を定数として持ち、名前付きが 4 つ以上の (SI, peer) は赤 (R-c)。定数のコメントに**値を上げる変更は監督裁定を要する**旨を書く | 件数の上限検査を外す | 名前付き 4 つの fixture |
| W1-10 | **必須テスト (a)**: SI 節の中の `- ` 行の数 = 拾った bullet の数 + `- —` の行の数。現物で観測する (設計 §10 の実測は **519 = 476 + 43**。着手時に実測し直す) | `_iter_bullets` 相当の純関数で、名前付き小ブロックを走査せず最初の一致で返す形に戻す (設計 §9 の落とし穴) | 必須テスト (a) の現物テスト |
| W1-11 | 既存の検査が見ている性質を 1 つも落とさない (設計 §3 の (v) の列挙: `\|` 行の不在、節順、SI 集合の 1:1、SI 重複なし、history リンクの解決、HISTORY の集合一致・非空、行長 1,400、preamble の宣言値の一致) | **監査照合**: 改修前後のテスト関数の一覧と件数を `--collect-only -q` の出力で対照し、(v) の 8 項目それぞれの担当テスト名を逐語記録に残す | — |
| W1-12 | `tools/check_control_mapping_split.py` が設計 §6 の 2 のとおり **(SI, peer, axis, 本文) の 4 つ組**で厳密に突き合わせ、**本文一致の global pairing を行わない** | 本文一致の global pairing を復活させる (`file` は split) | 別 SI へ 1 件動かした fixture が赤になる自己検査 |
| W1-13 | `- —` を多重集合から除き、**新設・削除を別カウンタ**で出す (設計 §6 の 4) | `- —` を主張と同じ多重集合に入れる (`file` は split) | `- —` の新設を数える自己検査 |
| W1-14 | 各 (SI, peer, axis, 小ブロック) の元 index の列が、元の同じ (SI, peer, axis) の列の**部分列**である (設計 §6 の 5) | 部分列の検査を外す (`file` は split) | 軸の中で順序を入れ替えた fixture の自己検査 |
| W1-15 | preamble・`## CCR-14 …`・`## Rule` の不変の判定を持ち、集計行が設計 §6 の書式 (`missing=… added=… moved=… empty_axis_added=… empty_axis_removed=… subsequence=… preamble=… ccr14=… rule=…`) で出る | `## Rule` 節の不変の判定を外す (`file` は split) | `## Rule` を 1 字変えた fixture の自己検査 |
| W1-16 | `tools/tests/test_check_control_mapping_split.py` が合成 fixture だけで閉じ、現物のリポジトリ状態や `git` の履歴に依存しない (`--base` の入力は fixture の一時ディレクトリで与える) | **監査照合**: 自己検査が使う fixture の作り方と、現物を読まないことを `file:line` で逐語記録に残す | — |
| W1-17 | 現行の cap の由来コメント (`conformance-tests/test_control_mapping_register.py:65-87` の 2026-09-06 の 15,065 + 135 字の記録) を**消さない** (設計 §4) | **監査照合**: 改修後の当該コメントを逐語で残し、改修前と同一であることを示す | — |
| W1-18 | 旧 2 道具の docstring に「本表は 2026-09-14 の一度限りの生成の入力であり、小ブロックの割当は含まない」旨の **1 行だけ**を足す。本体は 1 字も変えない (設計 §9) | **監査照合**: 足した 1 行と、本体が不変であることを `git diff --stat` の行数で逐語記録に残す | — |
| W1-19 | **現物 (名前付き小ブロック 0 件) で `pt.py` の対象が全部緑**である (§1.3)。テスト件数が基点より減らない | **監査照合**: 基点と改修後の `--collect-only -q` の件数と `pt.py` の集計行を逐語記録に残す | — |
| W1-20 | 追加・変更したコード・テストに実値が無い (§1.9) | **監査照合**: `python3 tools/public_value_scan.py <触ったファイル>` の集計行を逐語記録に残す | — |
| W1-21 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す | — |

### 2.4 実行するコマンド

```bash
tools/dev/pt.py -C .claude/worktrees/r50-wp1 -- conformance-tests/test_control_mapping_register.py tools/tests -q
tools/dev/mutate.py "$SP/r50-wp1-mutations.json" -C .claude/worktrees/r50-wp1
python3 tools/public_value_scan.py conformance-tests/test_control_mapping_register.py tools/check_control_mapping_split.py tools/tests/test_check_control_mapping_split.py
```

### 2.5 記録 (統合時に監督が埋める)

- 実装・レビューの回数と差し戻し、`pt.py` の集計行 (改修前後の件数)、`mutate.py` の変異表 (全件 `expect=red got=red` と復元の照合)、監査照合 W1-1・W1-11・W1-16〜W1-21 の逐語記録、完了ゲートの集計行、統合先の main SHA。**変異の定義は scratchpad を手放す前にこの節へ写す** (§1.5)。

## 3. WP-2 — 分割の適用 (Class D)

### 3.1 目的と範囲

設計 §7 のとおり **SI-08 の MitateDB-api** (`ops inventory`) と **SI-14 の r2db-api** (V2 `audit query`) を名前付き小ブロックへ分け、preamble の 2 つの文を書き換え、新しい段落・訂正註・版数を足す。**主張の文を 1 字も変えない純粋な移動である** (設計 §3 の (ii))。

**担当は implementer** (機械的な移動 + 道具での照合)。文面の起草は含まない — preamble の書き換え文と訂正註は §3.2 の確定文言を**逐語で**使う (§1.5 の 35・36。言い換えない)。移す bullet は設計 §7.1 (`security/CONTROL_MAPPING.md:555-560` の Control 6 件、`:565-573` の Evidence 9 件) と §7.2 の V2 (Control `:966-976` の 11 件、Evidence `:991`・`:995` の 2 件)。**行番号は着手時に実測し直す** (W2-1)。名前付き小ブロックは当該 peer の**既定の小ブロックの後ろ**に置き、Status は `- —` とする。

### 3.2 確定文言 (逐語。言い換えない)

改行位置は既存の段落の折り返しに倣ってよいが、**語・記号を変えない**。置き場は設計 §12 Q-7 のとおり (新しい段落と訂正註は `security/CONTROL_MAPPING.md:33` の**後ろ**。`:9` と `:33` の行番号を動かさない)。行頭の `>` は本書の引用記号であり、現物に写さない。1 行が `MAX_LINE_LENGTH = 1400` を超える場合は既存の段落と同じく折り返す。

**(A) `:9` の置き換え (同じ行の中で書き換える)**

> Each claim is one bullet under its invariant, subsection (r2db-api / MitateDB-api / Common), block (the subsection's default block, or a named one written `### <subsection> -- <topic>`) and axis (Control / Evidence / Status); `- —` marks an axis with no claim.

**(B) `:33` の第 2 文の置き換え (同じ行の中で、前後の文はそのまま)**

> A block is one subsection's default block or one of its named blocks, that block's claims joined by single spaces.

**(C) `:33` の直後に置く新しい段落**

> **Blocks per subsection** (R-50, requester ruling 2026-09-18 -- `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md`): a subsection may hold more than one block. Each `### ` heading inside an invariant section is either that subsection's default block (`### MitateDB-api`) or one of its named blocks (`### MitateDB-api -- ops inventory`; the topic is English and unique within the subsection). The default block is mandatory, appears exactly once and comes first; a subsection may add at most 3 named blocks (`MAX_NAMED_SUBBLOCKS = 3` in `conformance-tests/test_control_mapping_register.py`, raised only by a supervisor ruling). A subsection's blocks stand together, the subsection order (r2db-api, MitateDB-api, Common) is unchanged, and every block holds the same 3 axes in the same order (`- —` for an axis with no claim). Moving claims between blocks of the SAME subsection changes no character of any claim, so it is not a correction and moves nothing into `CONTROL_MAPPING_HISTORY.md`. Other documents point at a named block as `SI-08 / MitateDB-api / ops inventory / Evidence`, and at a default block as `SI-08 / MitateDB-api / Evidence`.

**(D) (C) の直後に置く preamble の訂正註**

> **【訂正 2026-09-18 (R-50, version 2.7)】** The two sentences rewritten in place above each described a block as one whole subsection, which is false once a subsection holds several blocks. The superseded text is kept here verbatim -- not in `CONTROL_MAPPING_HISTORY.md`, whose headings are bare invariant IDs and hold no place for this preamble: (1) "Each claim is one bullet under its invariant, subsection (r2db-api / MitateDB-api / Common) and axis (Control / Evidence / Status); `- —` marks an axis with no claim." (2) "A block is one subsection's claims (r2db-api, MitateDB-api or Common) joined by single spaces."

**(E) 版数行 `:5` の置き換え**

> Version: **2.7** (2026-09-18; R-50 -- a subsection may hold several blocks, the default block plus up to 3 named ones (`### <subsection> -- <topic>`) -- SI-08's MitateDB-api subsection split into its default block and `ops inventory`, SI-14's r2db-api subsection into its default block and `audit query`; a pure move, no claim text changed -- docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md)

### 3.3 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `security/CONTROL_MAPPING.md`、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` (訂正註)、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` (訂正註)、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` (訂正註) | §1.2 の全 WP 共通、`security/CONTROL_MAPPING_HISTORY.md` (**WP-2 では何も足さない**。W2-9)、`conformance-tests/test_control_mapping_register.py` (WP-1 で確定。読むだけ)、`security/CONTROL_MAPPING.md:657` の F-S11 の行 (WP-3)、`docs/design/` の記録 (WP-4) |

### 3.4 完了条件 → 変異

**本 WP は監査照合と道具の出力だけで構成される** (文面を機械的に固定するテストは無く、主張の文を 1 字も変えないため。§1.5 の 40)。逐語記録の置き場は §3.5。

| # | 完了条件 | 変異 (操作) |
|---|---|---|
| W2-1 | **着手時に実測し直す**: 照合の base rev (着手時の main SHA) と、設計 §7 の bullet の `file:line`・字数。**食い違ったら期待値を後から合わせず、設計 (`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md`) へ戻して数値を更新する** (設計 §10) | **監査照合**: base rev と実測値、設計の値との一致 / 不一致を逐語記録に残す |
| W2-2 | SI-08 の MitateDB-api を `### MitateDB-api` (既定) と `### MitateDB-api -- ops inventory` に分ける (設計 §7.1 の Control 6 件・Evidence 9 件を名前付きへ、Status は `- —`) | **監査照合**: 移した bullet の件数と `file:line` を逐語記録に残す |
| W2-3 | SI-14 の r2db-api を `### r2db-api` (既定) と `### r2db-api -- audit query` に分ける (設計 §7.2 の V2。Control 11 件・Evidence 2 件、Status は `- —`)。**V1 (`declared vocabulary`) は行わない** | **監査照合**: 同上 |
| W2-4 | `tools/check_control_mapping_split.py --base <W2-1 の rev>` の集計行が **`missing=0 added=0 moved=28 empty_axis_added=2 empty_axis_removed=0 subsequence=ok preamble=as_expected ccr14=identical rule=identical`** に一致する (設計 §6) | **監査照合**: 集計行をそのまま逐語記録に残す |
| W2-5 | 分割後の各ブロックの字数が設計 §7 の表に一致する (SI-08 既定 **10,190** / `ops inventory` **5,003**、SI-14 既定 **12,442** / `audit query` **2,679**) | **監査照合**: 実測した 4 つの字数を逐語記録に残す。一致しなければ W2-1 のとおり設計へ戻す |
| W2-6 | preamble の書き換えと追記が §3.2 の (A)〜(D) の確定文言と**逐語で一致**し、(C)(D) が `:33` の**後ろ**にある。`:9` と `:33` の行番号が動かない | **監査照合**: 差分と、`:9`・`:33` の行番号が不変であることを逐語記録に残す |
| W2-7 | 版数行が §3.2 の (E) と逐語で一致する (2.6 → **2.7**) | **監査照合**: 差分を逐語記録に残す |
| W2-8 | 設計 §9.1 の「ずれる」行の引用元に**訂正註**を足す (`docs/design/CODE_COMMENT_PROVENANCE_V1.md:135`、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md:2033,2471,2594`、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md:693,697`)。**既存の行は書き換えず、根拠と日付を添える** (§1.8 の 56・57)。「ずれない」行 (`:33` を引く 10 箇所、`:5`) は**実測で不変を確かめ、触らない** | **監査照合**: 新旧の行番号の実測、足した訂正註の `file:line`、触らなかった行の実測を逐語記録に残す |
| W2-9 | `security/CONTROL_MAPPING_HISTORY.md` に**何も足さない** (同じ (SI, peer) の中の移動は訂正ではない。設計 §9) | **監査照合**: 同ファイルの差分 0 を逐語記録に残す |
| W2-10 | §1.4 の `pt.py` の対象が全部緑である (WP-1 の検査が分割後の現物を受ける) | **監査照合**: `pt.py` の集計行を逐語記録に残す |
| W2-11 | 実 credential・実ホスト名・実ドメイン・実 DSN を 1 件も足さない。文書参照が壊れていない | **監査照合**: `python3 tools/public_value_scan.py security/CONTROL_MAPPING.md` と `python3 tools/check_doc_refs.py` の集計行を逐語記録に残す |
| W2-12 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す |

### 3.5 記録 (統合時に監督が埋める)

- 実装・レビューの回数と差し戻し、W2-1 の再実測、`check_control_mapping_split.py` の集計行、分割後の 4 つの字数、preamble の差分、訂正註の `file:line`、`pt.py`・`public_value_scan.py`・`check_doc_refs.py` の集計行、完了ゲートの集計行、統合先の main SHA。

## 4. WP-3 — F-S11 の 1 行を SI-08 へ戻す (Class D)

### 4.1 目的と範囲

設計 §8 と §12 Q-3 のとおり、`security/CONTROL_MAPPING.md:657` の 1 bullet を **SI-08 の `ops inventory` 小ブロックの Evidence** へ移す。文の直しは**次の確定文言の削除だけ**とする。

**確定文言 (逐語。言い換えない)** — 当該 bullet から、次の括弧書きを**直前の半角空白 1 つごと削除する**:

> `(the claim itself is SI-08's MitateDB-api item (6) bullet; its evidence sits here, next to the migration it depends on)`

削除以外の言い換えを行わない。**削除後の文が単独で読めないと判断した場合は、直さずに止まって監督へ報告する** (設計 §12 Q-3)。
### 4.2 触るファイル / 触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `security/CONTROL_MAPPING.md` (SI-09 MitateDB-api Evidence の当該 1 行と SI-08 の `ops inventory` Evidence)、`security/CONTROL_MAPPING_HISTORY.md` の SI-09 節、`docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` (訂正註)、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` (訂正註) | §1.2 の全 WP 共通、WP-2 が分割した他の bullet (**1 件も動かさない**)、preamble と版数行 (§6 の 2)、`conformance-tests/` |

### 4.3 完了条件 → 変異

| # | 完了条件 | 変異 (操作) |
|---|---|---|
| W3-1 | **着手時に実測し直す**: 照合の base rev (着手時の main SHA) と、設計 §8 の字数 (当該 bullet **1,074** 字、削除後 **954** 字、移送後の `ops inventory` **5,958** 字、SI-09 MitateDB-api **11,718** 字)。**食い違ったら期待値を合わせず設計へ戻す** (設計 §10) | **監査照合**: base rev と実測値、設計の値との一致 / 不一致を逐語記録に残す |
| W3-2 | §4.1 の確定文言を直前の半角空白ごと削除し、それ以外を 1 字も変えない | **監査照合**: 削除後の 1 行を**逐語**で記録に残す (設計 §8) |
| W3-3 | 当該 bullet を SI-08 の `ops inventory` 小ブロックの Evidence へ移す (SI-09 MitateDB-api Evidence からは消える) | **監査照合**: 移動前後の `file:line` を逐語記録に残す |
| W3-4 | 旧文 1 行 (1,074 字) を**逐語・無編集**で `security/CONTROL_MAPPING_HISTORY.md` の **SI-09 節**へ移す (設計 §8。文を書き換えたので訂正に当たる) | **監査照合**: 追記した行と、`CONTROL_MAPPING.md` の旧文との逐語一致を逐語記録に残す |
| W3-5 | `tools/check_control_mapping_split.py --base <W3-1 の rev>` の集計行が **`missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=identical ccr14=identical rule=identical`** に一致する (設計 §6) | **監査照合**: 集計行をそのまま逐語記録に残す |
| W3-6 | `missing` の 1 件が SI-09 の旧文、`added` の 1 件が SI-08 の新文であることを目視で照合する (設計 §6) | **監査照合**: 2 件の中身と照合の結論を逐語記録に残す |
| W3-7 | 移送後の字数が設計 §8 と一致する (`ops inventory` 5,958、SI-09 MitateDB-api 11,718。どちらも上限 15,200 に触れない) | **監査照合**: 実測した 2 つの字数を逐語記録に残す |
| W3-8 | `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` の **F-S11 の裁定 (`:1150-1152`) を消さず**、同書に訂正註を追記して「R-50 の複数ブロック化により置き場の前提 (SI-08 に字数が無いこと) が解消したため証拠を SI-08 へ戻した」旨と根拠・日付 (2026-09-18) を添える (§1.8 の 56・57、設計 §12 Q-3) | **監査照合**: 追記した訂正註の `file:line` と、F-S11 の行が不変であることを逐語記録に残す |
| W3-9 | `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md:693,697` に**本 WP の分の訂正註**を足す (SI-09 の MitateDB-api ブロックの中身が変わるため。設計 §9.1) | **監査照合**: 追記した訂正註の `file:line` を逐語記録に残す |
| W3-10 | §1.4 の `pt.py` の対象が全部緑である | **監査照合**: `pt.py` の集計行を逐語記録に残す |
| W3-11 | 実値を 1 件も足さない。文書参照が壊れていない | **監査照合**: `python3 tools/public_value_scan.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md` と `python3 tools/check_doc_refs.py` の集計行を逐語記録に残す |
| W3-12 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す |

### 4.4 記録 (統合時に監督が埋める)

- 実装・レビューの回数と差し戻し、W3-1 の再実測、削除後の 1 行の逐語、HISTORY へ移した旧文の逐語、照合の集計行と W3-6 の目視照合、訂正註の `file:line`、`pt.py` ほかの集計行、完了ゲートの集計行、統合先の main SHA。

## 5. WP-4 — 記録 (Class A。最終)

| # | 完了条件 | 変異 (操作) |
|---|---|---|
| W4-1 | `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` の **§2 の目標形と §5 の表**に小ブロックを反映し、版を上げる (**既存の行は消さない**。§1.8 の 56、設計 §9) | **監査照合**: 追記した節と版数を `file:line` で逐語記録に残す |
| W4-2 | `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` を **v1.0** にし、§7・§8・§9.1 の `file:line` と字数を**実測し直して**更新する (設計 §9.1 の最終行) | **監査照合**: 更新した `file:line` と実測値を逐語記録に残す |
| W4-3 | 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` の **R-50 の行に決着を追記**し、**R-52 の行に WP-3 の解除** (「`security/CONTROL_MAPPING.md` の WP は R-50 の統合後」の前提が満たされたこと) を追記する。版数を上げ、直前の版の行は当時のまま残す | **監査照合**: 追記した行と版数を `file:line` で逐語記録に残す |
| W4-4 | 文書参照が壊れていない | **監査照合**: `python3 tools/check_doc_refs.py` の集計行を逐語記録に残す |
| W4-5 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す |

### 5.1 記録 (統合時に監督が埋める)

- 監査照合 W4-1〜W4-5 の逐語記録 (更新した節・版数・`file:line`)、統合先の main SHA。

## 6. 監督の確定待ちの項目 (実装に入る前に決まる)

1. **§3.2 の確定文言 (A)〜(E) の確認**。本節の英文は設計 §9・§12 Q-7 を基に本書の起草者が起こした案であり、監督の確認をもって確定文言とする (§1.5 の 35)。
2. **WP-3 の版数の扱い**。設計は WP-2 の版 2.7 だけを定め、WP-3 (SI-09 → SI-08 の移動と訂正) の版数に触れていない。2.7 の版数行へ追記するか、2.8 に上げるか。
3. **WP-1 の変異の件数**。設計 §10 は登録テスト側の変異の例を 8 件挙げる (§2.3 の W1-2〜W1-9 に 1 対 1 で対応、うち W1-4 は 3 件に分かれる)。起草の枠は「登録テスト側 6 件」であり、件数が食い違う。

## 7. 監督の確定 (2026-09-18) — §6 の 3 項目

1. **§3.2 の (A)〜(E) を確定文言とする。** 加えて **(F)** を足す: preamble の「Length cap measurement」の段落は「this file's longest (SI, subsection) block is still SI-14's r2db-api block, now 15,122 characters … (78 left today)」と述べており、分割後に偽になる。この段落の既存の文は書き換えず (`:33` の行番号を動かさない)、(C) の段落の末尾に次の 1 文を足す。`<…>` は WP-2 の担当が分割後の現物を `conformance-tests/test_control_mapping_register.py` の関数で実測して埋める (数値は確定文言ではなく実測値):
   > Re-measured 2026-09-18 (version 2.7, after the split): the longest block is now `<SI-nn>`'s `<subsection>` `<default block | named block "topic">` at `<n>` characters (`<15200 - n>` left); the 15,122-character figure above describes the file before the split.
2. **WP-3 は版を 2.8 に上げる。** 訂正 (HISTORY への移送を伴う書き換え) は純粋な移動と別の変更であり、版数行も分ける。版数行の文は WP-3 の着手時に本書へ訂正註で確定文言を足す。
3. **WP-1 の変異は登録テスト側 8 件 (W1-4 は 3 項目に分ける) + 照合スクリプト側 3 件とする** (本書 §2.3 のとおり。起草の枠の「6 件 + 2 件」は設計 §10 の数え違い)。

## 8. 訂正註 1 (2026-09-18) — WP-1 のコードレビュー 1 回目への監督裁定

- **S-1 (絶対値の pin)**: `conformance-tests/test_control_mapping_register.py` に足された `EXPECTED_TOTAL_DASH_LINES = 519`・`EXPECTED_TOTAL_EM_DASH_LINES = 43`・`EXPECTED_TOTAL_COLLECTED_BULLETS = 476` の**絶対値の pin は 3 つとも置かない**。WP-2 が `- —` を 2 本新設すると 521 / 45 になり、主張を 1 件足す将来の変更 (R-52 の WP-3 を含む) のたびに 476 も動く — 登録簿に主張を足す変更が毎回 `conformance-tests/` を触る形になる。bullet の脱落を捕らえる性質は、節ごとの恒等式 `- ` 行の数 = 拾った bullet + `- —` と、空振りを防ぐ錨 (SI 節の数 = 16、拾った bullet の合計 > 0) で守る。移動の前後の一致は `tools/check_control_mapping_split.py` が担う。
- **S-2 (`preamble` と終了コード)**: `preamble` は `identical` / `differs` の 2 値のままとし、`differs` のときは preamble の unified diff を標準出力に出す。`--expect "<集計行>"` を足し、集計行が一致しなければ exit 1 にする (`missing` / `added` が終了コードを左右しない現状を直す)。**W2-4 の期待語 `preamble=as_expected` は `preamble=differs` と読み替え**、出力された preamble の diff を §3.2 の確定文言 (A)〜(F) と 1 行ずつ突き合わせることを W2-4 の監査照合とする (設計 §6 の 6 の「それ以外が不変」は、この diff に確定文言以外の hunk が無いことで確かめる)。
- **S-3 (`moved`)**: 設計 §6 の 3 のとおり、4 つ組が一致する bullet を旧側と新側で対応付け、小ブロック名が変わった件数を数える。現行の実装 (新側で名前付きに載っている件数) は、分割済みの文書の自己照合で `moved=1`、WP-3 型で `moved=2` になり、W3-5 の `moved=0` が原理的に出ない。
- **変異の件数**: 作業指示書 §7 の 3 の「8 + 3」は数え漏れで、§2.3 の字義どおりの 15 件 (11 + 4) が正しい (レビューが確認)。差し戻しで足す変異を含めた件数を記録に書く。
- **道具の引数の訂正**: §1.4 / §2.4 の `pt.py … -- conformance-tests/test_control_mapping_register.py tools/tests -q` の結合実行は、WP と無関係に teardown の error を 1 件出す (`tools/testpg/dsa_testpg.py` が同じ process の `PGPASSWORD` を消し、conformance の session 終了時の adapter の close が再接続に失敗する。完了ゲートは worker の process が分かれるので出ない)。**2 回に分けて回す**: `pt.py … -- conformance-tests/test_control_mapping_register.py -q` と `pt.py … -- tools/tests -q`。原因は台帳に別件で起票する。

## 9. 訂正註 2 (2026-09-18) — WP-1 の記録

- **経過**: 実装 → コードレビュー 1 回目 (重 2・中 3・低 2) → §8 訂正註 1 の監督裁定 S-1〜S-3 → 差し戻し 1 (新しい起動) → コードレビュー 2 回目 (差し戻し不要。低 1 件 = 旧道具の docstring の参照先の誤りは監督が 1 行直した。低 1 件 = `--base` に存在しない rev を渡すと traceback になる、は受理)。
- **`pt.py`** (2 回に分けて実行): `conformance-tests/test_control_mapping_register.py` = `34 passed` (基点 11)、`tools/tests` = `507 passed` (基点 492。照合スクリプトの自己検査 15 件)。**`mutate.py`**: 20 件とも `expect=red got=red`、復元は sha256 2 回で照合済み。
- **完了ゲート** (worktree を main `96fda8c` へ早送りした木、`gate.py -C`): `3733 passed, 2 subtests passed` (3710 + 23)、`judge=PASS`、実行クラスタ差分 0。`COLLECTION_FLOOR` は触っていない (テストは増えただけ)。
- **照合スクリプトの実測** (レビュー 2 回目が合成文書で確認): 分割済みの文書の自己照合 = `moved=0` / WP-3 型 = `missing=1 added=1 moved=0` / 名前付き → 既定の戻し = `moved=1` / WP-2 型 (既定 → 名前付きへ n 件) = `moved=n`。現物の自己照合: `missing=0 added=0 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=identical ccr14=identical rule=identical`、exit 0。
- **WP-2・WP-3 への注意**: `--expect` は集計行の逐語一致で判定する (空白・語順の正規化は無い)。期待行は本書からシングルクォートで逐語に渡す。
- **変異の定義 (scratchpad を手放す前の写し。id は `r50-wp1-mutations.json` のもの)**: W1-2-allowlist-exclusion-filter W1-3-subject-stage2-removed W1-3-subject-stage2-removed-double-separator-alone W1-4i-missing-default-allowed W1-4ii-duplicate-default-allowed W1-4iii-default-not-first-allowed W1-5-duplicate-subject-check-removed W1-6-peer-order-check-removed W1-7-axis-count-check-removed W1-7-prose-continuation-line-check-removed W1-7-em-dash-mixed-with-bullet-check-removed W1-8-per-subblock-cap-check-removed W1-9-max-named-subblocks-check-removed W1-10-iter-bullets-first-match-return W1-12-global-pairing-restored S3-moved-ignores-old-subblock-name W1-13-em-dash-folded-into-main-multiset W1-14-subsequence-check-removed W1-15-rule-invariance-check-removed S2-expect-comparison-disabled 
- **既知の制約**: 現物に名前付き小ブロックが 0 件の間、名前付き小ブロックに関する現物側の検査は fixture の上でだけ赤を示せる (WP-2 の後は現物側も効く)。

## 10. 訂正註 3 (2026-09-18) — WP-2 の記録 (§3.5 の中身) と WP-3 の範囲の追加

- **経過**: 実装 → コードレビュー 1 回目 (`security/CONTROL_MAPPING.md` の分割そのものは合格。中 2 件は引用元に足した訂正註の誤り) → 差し戻し 1 (同じ起動) → 監督が現物で確認。
- **W2-1**: base = main `e0d2cb5`。設計 §7 の bullet の `file:line`・字数は着手時の実測と完全に一致 (SI-08 Control `:555-560` 6 件 1,864 字 / Evidence `:565-573` 9 件 3,138 字、SI-14 V2 Control `:966-976` 11 件 2,020 字 / Evidence `:991`・`:995` 2 件 657 字)。
- **W2-4** (実装担当とレビュー担当がそれぞれ実行): `python3 tools/check_control_mapping_split.py --base e0d2cb5 --expect '…'` → `missing=0 added=0 moved=28 empty_axis_added=2 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`、exit 0。preamble の diff の hunk は版数行・`:9`・`:33`・新しい段落・訂正註だけで、確定文言 (A)〜(F) と逐語で一致 (レビューが 1 字ずつ照合)。**道具に頼らない照合** (レビュー): `- ` 行の多重集合の差は `- —` の新設 2 行だけ (522 → 524、削除 0)、見出しの増分は `### MitateDB-api -- ops inventory`・`### r2db-api -- audit query` と各 3 軸の `#### ` だけ。
- **W2-5** (実装担当とレビュー担当がそれぞれ実測): 10,190 / 5,003 / 12,442 / 2,679。設計 §7 の表と一致。(F) の実測値: 分割後の最長ブロックは SI-09 の MitateDB-api の既定の小ブロックで 12,793 字 (残り 2,407)。
- **W2-6・W2-7**: `:5`・`:9`・`:33` の行番号は不変、(C)(D) は `:33` の後ろ、最長行 1,384 < 1,400。版 2.6 → 2.7。
- **W2-8**: 訂正註を足した引用元 — `docs/design/CODE_COMMENT_PROVENANCE_V1.md` (`:41` → `:70`。同書 v0.20)、`docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` の「## 4. 訂正註」(`:2041`・`:2479` が引く `:538` → `:567`)、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` (v0.13)。**設計 §9.1 の誤り**: 同表が 3 つ目に挙げた `WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md:2594` は `CH-0538` (comment-history の欠番 ID) の行で、`security/CONTROL_MAPPING.md:538` を引いていない (レビューの実測)。設計メモ側の訂正は WP-4 で行う。「ずれない」10 箇所と `:5` は抜き取り 3 件で不変を確認。
- **W2-9**: `security/CONTROL_MAPPING_HISTORY.md`・`conformance-tests/`・`tools/` の差分 0。**W2-10**: `pt.py` = `34 passed` / `507 passed`。**W2-11**: `public_value_scan.py` = `total_flagged=0`、`check_doc_refs.py` = `0 dangling references`。**W2-12**: 12 行すべてに監査照合が対応。
- **完了ゲート** (worktree、`gate.py -C`): `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。
- **R-52 の WP-3 の材料** (レビューの実測。旧 → 新): `security/CONTROL_MAPPING.md` の `:548` → `:577`、`:641` → `:682`、`:647` → `:688`、`:650` → `:691`、`:659` → `:700`、`:5` は不変。F-S11 の行は `:657` → `:698`。
- **WP-3 の範囲の追加 (監督裁定)**: SI-14 の r2db-api の**既定**の小ブロックに、ファイル名を伴わない `` `::name` `` の形のテスト名が 24 件残り、同じファイル (`r2db-api/tests/test_audit_query.py`) を名指す 2 箇所はどちらも `audit query` の小ブロックへ移った (設計 §7.2 は移した側の指示語しか見ていなかった)。純粋な移動の枠では直せないので、**WP-3 (版 2.8 の訂正) に入れる**。確定文言は WP-3 の着手時に本書へ訂正註で足す。

## 11. 訂正註 4 (2026-09-18) — WP-3 の確定文言

本節の英文と `file:line`・字数は本書の起草者が起こした**案と起草時の実測**であり、**監督の確認をもって確定文言とする** (§1.5 の 35)。base は main `bd17175` (§10 の WP-2 統合後)。値は着手時に W3-1 として取り直す。

### 11.1 変更 (i) — F-S11 の 1 行を SI-08 へ戻す

- **対象 (実測)**: `security/CONTROL_MAPPING.md:698` = SI-09 / MitateDB-api / 既定の小ブロック / Evidence の 1 bullet、1,074 字 (設計 §8 の `:657` の WP-2 後の位置。§10 の「R-52 の WP-3 の材料」の実測と一致)。削除は §4.1 の確定文言のとおり (括弧書きを直前の半角空白 1 つごと)。削除後は 954 字 (設計 §8 と一致)。
- **削除後の 1 行 (現物から起こした逐語。確定文言)**:

> - `ops inventory` item (6) reads the value 0013 sets: `MitateDB-api/tests/test_ops_inventory.py::test_inventory_ddl_lock_is_confirmed_by_default_bootstrap_alone`, `::test_inventory_ddl_lock_confirmed_after_apply_platform_migration_0013`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_zero`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_negative`, `::test_inventory_ddl_lock_is_blocked_when_statement_timeout_is_unparseable`, `::test_inventory_ddl_lock_is_blocked_when_only_the_application_runtime_role_is_unbounded`, `::test_inventory_ddl_lock_is_blocked_when_only_the_application_developer_role_is_unbounded`, `::test_inventory_ddl_lock_blocked_outranks_unknown_when_mixed_with_an_undeclared_role`, `::test_inventory_ddl_lock_minus_one_and_zero_statement_timeout_mixture_is_unknown`, `::test_inventory_exit_code_is_2_when_ddl_lock_is_blocked`, `::test_inventory_ddl_lock_key_set_is_the_same_on_the_psycopg_error_path`.

- **単独で読めるか (§4.1 の停止条件の判断材料)**: 読める。`sets` の直後にそのまま `:` が続き、以降はテスト名の列挙だけである。削除は直前の半角空白ごとなので `sets` と `:` の間に空白は残らない。**最小の直しの案は要らない**。
- **移す先 (実測)**: `security/CONTROL_MAPPING.md:616` = SI-08 / MitateDB-api / `ops inventory` / Evidence の item (6) の既存の証拠の bullet。**その直後**、現行 `:617` (「the CLI/key-set/`unjudged_items` static pins: …」) の前に置く。同小ブロック Evidence の先頭 `:609` は「every name below (`::name` form) is in that ONE file」と述べるが、移す 1 行は先頭が `MitateDB-api/tests/test_ops_inventory.py::…` の完全形で、残りも同じ 1 ファイルなので矛盾しない。

### 11.2 変更 (ii) — SI-14 / r2db-api の既定の小ブロックの `::name` の出所

- **実測 1 (実在ファイル)**: 既定の小ブロック (`:969-1044`) の、ファイル名を伴わない `` `::name` `` は 25 出現・24 名。実在ファイルは 4 つで、すべて `r2db-api/tests/` 配下 — `test_application_audit.py` 13 名、`test_audit_query.py` 7 名、`test_control_plane_service.py` 3 名、`test_control_plane_store.py` 1 名。**1 ファイルに閉じない**ので、SI-08 の名前付き小ブロックが使う「every name below (`::name` form) is in that ONE file」の形はそのままでは使えない。
- **実測 2 (直前の完全形との一致)**: 25 出現のうち 11 は同じ小ブロック内の直前の `<path>::<name>` と実在ファイルが一致する (`:977`・`:978`・`:980`・`:983`・`:985`・`:987` 2 件・`:988`・`:989`・`:992` 2 件)。残り 14 出現 = 10 行 (`:994` 2 件・`:1002`・`:1003`・`:1004`・`:1011`・`:1021`・`:1022` 2 件・`:1023`・`:1033` 2 件・`:1043` 2 件) は食い違う。**実測 3 (base との差)**: その 10 行は分割前 (base `e0d2cb5`) でも同じく食い違っていた (base の `:953` 2 件・`:961`・`:962`・`:963`・`:981`・`:992`・`:993` 2 件・`:994`・`:1005` 2 件・`:1015` 2 件)。**分割で新たに曖昧になった行は 0 件**。ただし 6 行 (`:1011`・`:1021`・`:1022`・`:1023`・`:1033`・`:1043`) は分割で直前の完全形が入れ替わった (base では `r2db-api/tests/test_ops_declarations.py` と `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`、現行では `src/r2db_api/service.py` と `r2db-api/tests/test_preauth_concurrency_bound.py`)。
- **案 (ii)-a (追加だけ。既存の bullet を 1 字も変えない)**: SI-14 / r2db-api / 既定 / Evidence の**先頭** (現行 `:1018` の前) に次の 1 bullet を足す。本文 1,285 字 / 行 1,287 字。既存の文を書き換えないので HISTORY への移送は生じない。

> - A test name written `::name` in this default block carries no file of its own: it is in the nearest qualified `<path>::<name>` earlier in this SAME block, except these fourteen, which follow no such path -- `::test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry`, `::test_capability_unsupported_and_not_found_denials_add_no_durable_row`, `::test_each_data_operation_adds_exactly_one_application_audit_row`, `::test_dispatch_point_is_the_destructive_confirmation_choke`, `::test_failed_data_commit_writes_an_error_row_for_the_same_request_id`, `::test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n` and `::test_different_denial_keys_do_not_coalesce_together` are in `r2db-api/tests/test_application_audit.py`, and `::test_control_capabilities_operation_has_no_reachable_deny_branch`, `::test_operation_and_target_kind_non_durable_exclusions_never_reach_the_durable_tables`, `::test_declared_event_classes_cover_every_emittable_class`, `::test_every_field_keyword_argument_is_a_string_literal_ifexp_or_forward`, `::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`, `::test_declared_audit_event_classes_change_only_deliberately` and `::test_declared_audit_operations_change_only_deliberately` are in `r2db-api/tests/test_audit_query.py`.

- **案 (ii)-b (点ごとに補う。書き換えなので訂正に当たる)**: 食い違う 10 行のうち**最小の 5 行**で、その行の最初の `` `:: `` を `` `r2db-api/tests/test_application_audit.py:: `` (`:994`・`:1033`) / `` `r2db-api/tests/test_audit_query.py:: `` (`:1011`・`:1021`・`:1043`) に替える。この 5 行だけで残り 9 出現の直前の完全形も正しくなる (実測で確認)。Update convention により、次の**旧文 5 行**が逐語・無編集で `security/CONTROL_MAPPING_HISTORY.md` の **SI-14 節**へ移す対象になる (移すのは先頭の `- ` を外した本文で、下の `(`:994`)` 等は本註での位置の註記であり移送する文に含めない)。案 (ii)-a と (ii)-b のどちらを採るかは監督が決める。どちらも 11.4 の上限の検査を通る。

> - (`:994`) every other reason code is non-durable and does not enter the bounded buffer -- `::test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry`, `::test_capability_unsupported_and_not_found_denials_add_no_durable_row`.
> - (`:1011`) `operation` U 31 = D 27 + N 4 (`delete_audit`/`set_authorization_state_available`/`set_credential_state`, plus `control_capabilities` (its 2 emit sites can never reach a deny branch) -- `::test_control_capabilities_operation_has_no_reachable_deny_branch`);
> - (`:1021`) Non-durability is measured, not assumed: `::test_operation_and_target_kind_non_durable_exclusions_never_reach_the_durable_tables` drives each excluded word through its real path and asserts no durable row appears.
> - (`:1033`) folding M into the capacity thresholds is runbook work (`POSTGRES_PROVISIONING_RUNBOOK.md` §15) -- `::test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n`, `::test_different_denial_keys_do_not_coalesce_together` (1 more concurrency pin: companion history).
> - (`:1043`) the only detector is a per-field snapshot test pinning `DECLARED_AUDIT_OPERATIONS`/`DECLARED_AUDIT_TARGET_KINDS`/`DECLARED_AUDIT_EVENT_CLASSES` against a fixture `frozenset` -- `::test_declared_audit_event_classes_change_only_deliberately`, `::test_declared_audit_operations_change_only_deliberately` (1 more snapshot pin: companion history).

### 11.3 版数行 2.7 → 2.8

- **流儀 (現物と `git log` で確認)**: `security/CONTROL_MAPPING.md:5` は 1 行で、版が上がるたびに丸ごと置き換わってきた (2.0 `de0202d` / 2.4 `6dea423` / 2.5 `467b932` / 2.6 `40cdbd0` / 2.7 `0b25907`)。`security/CONTROL_MAPPING_HISTORY.md` に `Version:` 行は 0 件。したがって**2.7 の行は HISTORY へ移す対象ではない** (旧文は git 履歴が持つ)。
- **確定文言の案 ((i) + 案 (ii)-a。2.7 の行と同じ形で、(i) と (ii) を 1 文ずつ)**:

> Version: **2.8** (2026-09-18; R-50 WP-3 -- the SI-09 MitateDB-api Evidence bullet listing the tests that read the value migration 0013 sets moves to SI-08's `ops inventory` named block, beside the item (6) claim it evidences, with only its parenthetical about where that claim lives deleted, the superseded line verbatim in `CONTROL_MAPPING_HISTORY.md`'s SI-09 section. SI-14's r2db-api default block gains one Evidence bullet naming the test file each bare `::name` in that block belongs to -- docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md)

- **案 (ii)-b を採るときの 2 文目の差し替え**:

> SI-14's r2db-api default block now spells out the test file the `::name` list of five of its claims continues from, the five superseded lines verbatim in `CONTROL_MAPPING_HISTORY.md`'s SI-14 section.

### 11.4 期待集計行・字数・§4.3 への訂正

- **算法 (設計 §6 の 2・3・5)**: (i) は SI をまたぐので 4 つ組が一致せず `missing=1 added=1`、`moved` には入らない。(ii)-a は bullet の新設なので `added` が 1 増える。(ii)-b は 5 行の書き換えなので `missing`/`added` が 5 ずつ増える。`- —` は増減しないので `empty_axis_*` は 0。新設・書き換えの bullet は §6 の 5 の判定から除かれるので `subsequence=ok`。**`preamble` への訂正**: §4.3 の W3-5 は `preamble=identical` を期待するが、§7 の 2 の裁定 (版を 2.8 に上げる) と両立しない。**期待語を `preamble=differs` に訂正する**。出力される preamble の diff の hunk が版数行と 11.3 の確定文言だけであることを目視で照合する (§8 訂正註 1 の S-2 と同じ扱い)。
- **`--expect` に渡す期待行 ((i) + 案 (ii)-a)**: `missing=1 added=2 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`
- **`--expect` に渡す期待行 ((i) + 案 (ii)-b)**: `missing=6 added=6 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`
- 起草時の確認: 現物から合成した候補 2 本に `tools/check_control_mapping_split.py --base bd17175 --new <候補>` を掛け、上の 2 行と逐語一致した (候補は scratchpad にのみ置き、`security/` は触っていない)。着手時に実物で取り直す。
- **字数** (`conformance-tests/test_control_mapping_register.py` の `_subblock_block_text` を import して実測): SI-08 `ops inventory` 5,003 → **5,958** (残り 9,242)、SI-09 MitateDB-api 既定 12,793 → **11,718** (残り 3,482) — どちらも設計 §8 の値と一致。SI-14 r2db-api 既定 12,442 → **13,728** (案 a、残り 1,472) / **12,624** (案 b、残り 2,576)。上限 15,200 に触れない。行長は案 a の新設行が 1,287 字、現物の最長 1,384 字は不変で、いずれも 1,400 未満。**W3-7 への訂正**: (ii) を入れるので、W3-7 の実測の対象に **SI-14 / r2db-api の既定の小ブロックの字数**を足す。
- **事実の指摘 (本註では文言を起こさない)**: (i) と (ii) の後、この文書の最長ブロックは SI-14 の r2db-api の既定 (案 a 13,728 / 案 b 12,624) になり、preamble `:50-52` の (F) の文が述べる「the longest block is now `SI-09`'s `MitateDB-api` `default block` at `12,793` characters (`2,407` left)」は偽になる。

### 11.5 引用元への訂正註 (W3-8・W3-9)

- **R-45 の作業指示書** `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`: F-S11 の裁定は `:1150-1152` にあり (W3-8 の値と一致)、**1 行も消さない**。`:1152` の引用の直後、`:1154` の「監査照合の逐語記録」の前に、空行 1 行を置いて次を足す:

> **訂正註 (2026-09-18、R-50 WP-3、本文は書き換えない)**: 上の F-S11 は「SI-08 の MitateDB ブロックが 15,194 / 15,200 字で入らない」ことを根拠に、item (6) の証拠のテスト名 1 行を SI-09 の MitateDB ブロックの Evidence に置いた。R-50 で 1 つの subsection が複数の小ブロックを持てるようになり (`security/CONTROL_MAPPING.md` version 2.7)、SI-08 の MitateDB-api は既定 10,190 字と名前付き `ops inventory` 5,003 字に分かれて、字数だけを根拠にした前提が解消した。よって version 2.8 でその 1 行を `SI-08 / MitateDB-api / ops inventory / Evidence` へ戻し、行中の括弧書き 1 つだけを削除した (旧文 1,074 字は `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ逐語で移した)。根拠は設計 `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §8・§12 Q-3。F-S11 の行は当時の判断の記録として残す。

- **設計メモ** `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md`: W3-9 が挙げる `:693,697` は、WP-2 が訂正註 2 本を足した後の現物では本文が **`:695`・`:700`**、WP-2 の訂正註が `:696`・`:701` である。**W3-9 の `file:line` をこの値に訂正する**。WP-2 の訂正註と重ならないよう、版数の古さは繰り返さず、移動の事実だけを `:696` の直後と `:701` の直後に同じ字下げで足す (2 箇所とも同じ文で足りる):

> - **訂正註 (2026-09-18、R-50 WP-3、本文は書き換えない)**: 直前の WP-2 の訂正註が予告したとおり、SI-09 の MitateDB-api の Evidence から item (6) の証拠の 1 行が `SI-08 / MitateDB-api / ops inventory / Evidence` へ移り、Version 行は 2.8 になった。runbook §10.8 の受理記録に対応する SI-09 の Evidence・Status の 2 行は動いていない。

### 11.6 監督の確定 (2026-09-18)

1. **11.1 の (i) を確定文言とする** (括弧書きの削除だけ。移す先は 11.1 のとおり)。
2. **(ii) は案 (ii)-b を採る。** 理由: 出所の食い違いは分割の前から在り (11.2 の実測 3。分割が新たに曖昧にした行は 0 件)、直すなら各主張がその場で自分の出所を持つ形が読み手に確実で、字数も小さい (+182 字)。案 (ii)-a は 1,285 字の例外の一覧を登録簿に足す形で、主張が増えるたびに一覧の保守が要る。§10 訂正註 3 の「同じファイル (`r2db-api/tests/test_audit_query.py`) を名指す 2 箇所」は不正確だった (実在ファイルは 4 つ。11.2 の実測 1) — 本項で訂正する。5 行の旧文は `security/CONTROL_MAPPING_HISTORY.md` の SI-14 節へ逐語で移す (W3-4 の射程に SI-14 節を足す)。
3. **版数行は 11.3 の確定文言の案の 1 文目 + 「案 (ii)-b を採るときの 2 文目」とする。**
4. **期待行は `missing=6 added=6 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`。** preamble の diff の hunk は版数行と下の 5 だけであること。
5. **preamble の (F) の 1 文 (版 2.7 で足した再実測の文) は、その場で版 2.8 の実測に置き換える**: 「Re-measured 2026-09-18 (version 2.8, after the split and the SI-09 -> SI-08 move): the longest block is now `<SI-nn>`'s `<subsection>` `<default block | named block "topic">` at `<n>` characters (`<15200 - n>` left); the 15,122-character figure above describes the file before the split.」 `<…>` は担当が WP-3 の後の現物を実測して埋める (11.4 の見込みでは SI-14 の r2db-api の既定、12,624)。(F) は今日の版 2.7 で足した実測の文で、旧文は git 履歴 (`0b25907`) が持つので preamble の訂正註は足さない。`:5`・`:9`・`:33` の行番号は動かさない。
6. **W3-7 の実測の対象に SI-14 / r2db-api の既定の小ブロックの字数を足す** (見込み 12,624)。W3-9 の `file:line` は 11.5 のとおり `:695`・`:700` (訂正註は `:696`・`:701` の直後)。
7. **WP-2 の取りこぼし 2 件を本 WP で直す**: `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` の表題の版 (`:1` が v0.12 のまま、改版履歴は v0.13) を改版履歴の最新の版に合わせ (本 WP で版を上げるならその版)、同書 `:687` 付近の「SI-09 の Evidence へ 1 行として置いた」の記述の直後にも 11.5 と同じ訂正註を足す。

## 12. 訂正註 5 (2026-09-18) — WP-3 の記録

- **経過**: 確定文言の起草 (§11) → 監督の確定 (§11.6) → 実装 → コードレビュー 1 回目 (本体の (i)(ii) は全点で実測一致。中 1・低 2・佐 2) → 差し戻し 1 (同じ起動) → 監督が現物で確認 (照合スクリプトの再実行と 7 対目の差分)。
- **差し戻し 1 の監督裁定**: (a) SI-14 / r2db-api / `audit query` の小ブロックにも、直前の完全形と実在ファイルが食い違う裸の `::name` が 1 件あった (分割の前から。`::test_data_plane_capabilities_declares_contract_version_1_5_0_and_audit_query_unavailable`、実在は `r2db-api/tests/test_audit_query.py`)。**本 WP に足した** — (ii)-b と同じ形。これにより §11.6 の 4 の期待行は **`missing=7 added=7 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical`**、版数行の 2 文目は「SI-14's r2db-api default block now spells out the test file the `::name` list of five of its claims continues from, and its `audit query` block does the same for one claim, the six superseded lines verbatim in `CONTROL_MAPPING_HISTORY.md`'s SI-14 section.」に差し替えた。(b) WP-2 が `docs/design/CODE_COMMENT_PROVENANCE_V1.md` に足した訂正註の行番号 (`:70`) が、本 WP の (F) の 1 行増で `:71` に動いた。同書 v0.21 の訂正註で直し、**行番号に頼らない所在** (節 → 小節 → 最初の `#### Control`) を併記した。(c) `security/CONTROL_MAPPING_HISTORY.md` の SI-09 節へ移した 1 行は、同節の流儀に合わせて先頭の `- ` を外した。
- **照合** (実装担当・レビュー担当・監督がそれぞれ実行): `python3 tools/check_control_mapping_split.py --base bd17175 --expect '…'` → 上の期待行と一致、exit 0。preamble の diff は版数行と (F) の文だけ。**道具に頼らない照合** (レビュー、差し戻しの前の 6 対): `- ` 行の多重集合の差は、括弧書き 120 字 (直前の半角空白を含む) の削除 1 対と、行の最初の `` `:: `` の直前へのパスの挿入 5 対だけ。7 対目は監督が差分で確認 (パスの挿入だけ)。
- **`::name` の総当り** (レビュー): SI-14 / r2db-api の既定 34 出現で不一致 0、SI-08 の `ops inventory` 43 出現はすべて `MitateDB-api/tests/test_ops_inventory.py` に実在、移した行の 11 名も実在。`audit query` の残り 2 件は実装担当が grep で一致を確認。
- **字数** (実測): SI-14 / r2db-api の既定 **12,624** (残り 2,576。文書の最長)、SI-08 の `ops inventory` **5,958**、SI-09 の MitateDB-api の既定 **11,718**。最長行 1,384 < 1,400。`:5`・`:9`・`:33` の行番号は不変。版 2.7 → **2.8**。
- **HISTORY**: SI-09 節へ旧文 1 行、SI-14 節へ旧文 6 行を逐語で移した。節見出しの増減なし。
- **引用元への訂正註**: `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` の F-S11 の裁定 (`:1150-1152`。1 字も変えていない) の後、`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` の 3 箇所 (v0.14。表題の版を改版履歴に同期)、`docs/design/CODE_COMMENT_PROVENANCE_V1.md` (v0.21)。
- **`pt.py`**: `34 passed` / `507 passed`。`public_value_scan.py` = `total_flagged=0`、`check_doc_refs.py` = `0 dangling references`。**完了ゲート** (worktree、`gate.py -C`): `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。
- **R-52 の WP-3 の材料** (レビューの実測。WP-2 の後 → 本 WP の後。差し戻し 1 は行数を変えていない): `security/CONTROL_MAPPING.md` の `:577` → `:578`、`:682` → `:684`、`:688` → `:690`、`:691` → `:693`、`:700` → `:701`。F-S11 の行は `:618` (SI-08 / MitateDB-api / ops inventory / Evidence)。


## 13. 訂正註 6 (2026-09-19) — 受け入れ監査と監督の受け入れ

- **受け入れ監査** (`evidence-auditor` 1 回、レビュー担当とは別の起動、main `06b8871`): 全 50 条件 (W1 21 + W2 12 + W3 12 + W4 5) のうち **充足 44、未充足 6 (いずれも記録の欠落で、実体は監査が現物で確認済み)、証拠不足 0**。「完了条件 → 変異」の対応表に対応の無い行は 0 件。監査は WP-2・WP-3 の照合の集計行を版をまたいで再現し (WP-2 = `missing=0 added=0 moved=28 empty_axis_added=2 …`、WP-3 = `missing=7 added=7 moved=0 …`、どちらも exit 0)、字数 7 値・`:5`・`:9`・`:33` の不変・確定文言の逐語一致・HISTORY の 7 行の逐語一致・`spec/` と `security/SECURITY_INVARIANTS_V1.md` と `conformance-tests/` の差分 0 (WP-2・WP-3) を確かめた。変異 20 件は mutate の log を 1 本ずつ読み、赤になった test id の実名が現行の収集 id に実在することを確かめた。
- **監督裁定 (記録の欠落 6 件)**: **A-1** W1-1・W1-11・W1-16〜W1-21 の逐語記録と「完了条件 → 変異 → 赤になった test id」の対応表が §9 に無かった → 下の 13.1・13.2 に監査の写しを置いて充足とする。**A-2** W4-1〜W4-3・W4-5 の §5.1 の記録が空だった → 実体は `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` v1.1、`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` v1.0 (§13)、roadmap v1.66 (main `06b8871`、作業 `a7f7bba`) であり、本項をもって記録とする。**A-3** W3-12: §4.3 の表は 12 行で、全行が監査照合である (本項をもって記録とする)。
- **監督裁定 (設計疑義)**: **A-4** WP-4 のコミット `a7f7bba` に「security-contract の変更ではない」の明記が無い → WP-4 は Class A (`security/`・`spec/` の差分 0) で、宣言の対象は `security/` か `conformance-tests/` に触れるコミット (WP-1〜WP-3。3 本とも明記済み) と読む。コミットは書き換えない。**A-5** 軽微 3 件: §10 の「SI-14 V2 Evidence 657 字」は他の値と同じ数え方なら 658 (分割後の 2,679 は一致) / WP-3 で `audit query` の小ブロックは 2,679 → **2,713** 字になった (パスの挿入 34 字。上限に影響なし) / `tools/check_control_mapping_split.py` ほかの docstring が設計を `v0.4` と引いている (現行 v1.0。設計時点の版の引用として据え置く)。
- **完了ゲート** (3 本とも監督が単独実行): `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。直前の main の 3710 との差 +23 は登録テストの増分 (34 − 11) と一致。`COLLECTION_FLOOR` は不変。
- **受け入れ (監督、2026-09-19)**: **R-50 の WP-1〜WP-4 を受け入れる。**

### 13.1 WP-1 の完了条件の判定 (受け入れ監査の写し) (W1-1〜W1-21)

| # | 判定 | 証拠 / 不足しているもの |
|---|---|---|
| W1-1 | 充足 (記録は scratchpad のみ) | 純関数 `_analyze_shape` = `conformance-tests/test_control_mapping_register.py:428`。現物系統 `:532`・`:542`・`:549`・`:558`・`:565`・`:572`・`:579`・`:586` (いずれも `_read()` 経由)、fixture 系統 `:758` 以降が同じ関数を呼ぶ。逐語記録は実装報告にあるが指示書 §9 に無い |
| W1-2〜W1-10 | 充足 | 変異 14 件が `expect=red got=red`。赤の test id は §4 の変異表のとおり現物の収集 id に実在 |
| W1-11 | 充足 (記録は scratchpad のみ) | (v) の 9 テスト名はいずれも基点 `96fda8c` に `def` が在り、改修後も収集される (監査で 1 件ずつ照合)。逐語記録は実装報告 §4 のみ |
| W1-12〜W1-15 | 充足 | 変異 4 件 + S3・S2 の計 6 件が赤 (§4) |
| W1-16 | 充足 (記録は scratchpad のみ) | `tools/tests/test_check_control_mapping_split.py` は `security/CONTROL_MAPPING.md`・`git` を読まず、fixture は文字列組み立てのみ (docstring `:7-11` が同旨を宣言、grep で確認) |
| W1-17 | 充足 | 基点 `96fda8c` の `:65-87` (cap の由来コメント、先頭「Design section 5, "肥大化の抑止"…」/ 末尾「to this restructure's own WP-2 pass).」) が現物に**逐語で残存** |
| W1-18 | 充足 (文言は監督裁定で変更) | `git diff` は両ファイルとも docstring への **+2/-0** のみで本体不変。`restructure_control_mapping.py` は指示書の文言どおり、`check_control_mapping_restructure.py` は差し戻し 5 の裁定により「この道具は表を持たない」旨の別文になった (指示書 §9 は「旧道具の docstring の参照先の誤りを監督が 1 行直した」とのみ記す) |
| W1-19 | 充足 | `--collect-only -q` の実測: 現行 34 (register) / 507 (tools/tests)、基点の register は `def test_` 11 個 (報告の「基点 11」と一致)。減少なし。緑であることは完了ゲート 3733 passed が担保 |
| W1-20 | 充足 | 監査で再実行: `mode=tree files_scanned=5 total_flagged=0` |
| W1-21 | 充足 | §2.3 は 21 行。変異を持つ 15 行 (実施は 20 件) と監査照合 6 行で、対応の無い行は **0** (監査で 1 行ずつ確認) |

### 13.2 変異表 (`tools/dev/mutate.py`。20 件、verbatim)

実装報告 `r50-wp1-impl-report-2.md` §3 の写し。集計行:

```
mutate: 20 mutations, 20 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged (n/a for 4 edits whose lines all exist in the pristine file) | logs=(作業機の一時ディレクトリ。記録には残さない)
```

監査は当該 log ディレクトリ (20 本) を読み、各変異が落とした test id を 1 件ずつ確認した。**完了条件 → 変異 id → 赤になった test id (監査が log で確認した実名)**:

| 完了条件 | 変異 id | 赤になった test id | expect/got |
|---|---|---|---|
| W1-2 | `W1-2-allowlist-exclusion-filter` | `…register.py::test_fixture_unknown_subblock_heading_is_rejected_not_skipped` | red/red |
| W1-3 | `W1-3-subject-stage2-removed` | `…::test_fixture_subblock_subject_with_bad_form_is_rejected[full_width_space]` | red/red |
| W1-3 | `W1-3-subject-stage2-removed-double-separator-alone` | `…::test_fixture_subblock_subject_with_bad_form_is_rejected[double_separator]` | red/red |
| W1-4(i) | `W1-4i-missing-default-allowed` | `…::test_fixture_default_subblock_missing_is_rejected` | red/red |
| W1-4(ii) | `W1-4ii-duplicate-default-allowed` | `…::test_fixture_default_subblock_duplicated_is_rejected` | red/red |
| W1-4(iii) | `W1-4iii-default-not-first-allowed` | `…::test_fixture_default_subblock_not_first_is_rejected` | red/red |
| W1-5 | `W1-5-duplicate-subject-check-removed` | `…::test_fixture_duplicate_subject_within_peer_is_rejected` | red/red |
| W1-6 | `W1-6-peer-order-check-removed` | `…::test_fixture_subblocks_interleaved_across_peers_is_rejected` | red/red |
| W1-7 | `W1-7-axis-count-check-removed` | `…::test_fixture_named_subblock_missing_an_axis_is_rejected` | red/red |
| W1-7 | `W1-7-prose-continuation-line-check-removed` | `…::test_fixture_named_subblock_axis_with_a_prose_continuation_line_is_rejected` | red/red |
| W1-7 | `W1-7-em-dash-mixed-with-bullet-check-removed` | `…::test_fixture_named_subblock_axis_mixes_em_dash_placeholder_with_a_real_bullet_is_rejected` | red/red |
| W1-8 | `W1-8-per-subblock-cap-check-removed` | `…::test_fixture_named_subblock_alone_exceeds_the_length_cap` | red/red |
| W1-9 | `W1-9-max-named-subblocks-check-removed` | `…::test_fixture_four_named_subblocks_exceeds_max_named_subblocks` | red/red |
| W1-10 | `W1-10-iter-bullets-first-match-return` | `…::test_fixture_bullet_accounting_catches_dropped_named_subblock_bullets` | red/red |
| W1-12 | `W1-12-global-pairing-restored` | `tools/tests/test_check_control_mapping_split.py::test_move_to_a_different_si_is_missing_and_added_not_moved` | red/red |
| S-3 | `S3-moved-ignores-old-subblock-name` | `…split.py::test_moved_is_zero_when_an_already_split_document_is_compared_to_itself` | red/red |
| W1-13 | `W1-13-em-dash-folded-into-main-multiset` | `…split.py::test_new_empty_axis_placeholder_is_counted_separately_from_the_main_multiset` | red/red |
| W1-14 | `W1-14-subsequence-check-removed` | `…split.py::test_subsequence_violation_when_a_subblock_reorders_its_bullets` | red/red |
| W1-15 | `W1-15-rule-invariance-check-removed` | `…split.py::test_rule_difference_fails_the_check` | red/red |
| S-2 | `S2-expect-comparison-disabled` | `…split.py::test_expect_mismatch_when_a_bullet_is_lost_exits_1` | red/red |

- 監査の独立確認: 20 件の `tests` に挙がる test id は**全件**現行の収集 id (register 34・tools/tests 507) に実在し、20 件の変異の `old` のスニペットは**全件**現行のファイルに実在する (= 変異が現行コードの実在の分岐を消す形になっている)。
- W1-3 は `-x` のため 1 変異 1 赤の原則に沿って項目を分けてある (`trailing_space` は 1 段目で既に赤のため 2 段目の変異では動かない — 実装報告 §4 の註)。
- 指示書 §9 は**変異 id 20 件を逐語で写している**が、「赤になった test id」の列と mutate の集計行は写していない (§5 の未解決 1)。
