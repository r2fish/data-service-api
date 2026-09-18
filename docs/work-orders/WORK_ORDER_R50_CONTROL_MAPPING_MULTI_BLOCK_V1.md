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
