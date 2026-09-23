# 正本と記録の分離 (archive-split) 設計 v1.2

- 改版: **v1.2 (2026-09-23)** 実装後の確定 — §4.2 の Known gaps の案は現物 (`tools/check_doc_refs.py` 4・5、`tools/check_comment_provenance.py` 5、`tools/change_class.py` 3、`tools/dev/README.md` 索引 5 / 5 / 3) を正とし、コードレビュー 1 回 (4 件、監督裁定は作業指示書 §6 の 11) を反映した。Known gaps 4 に `docs/archive/README.md` (唯一の正本だが除外に入る) の例外を足した。**v1.0 (2026-09-23)** 起票。**v1.1 (2026-09-23)** 設計レビュー 1 回 (10 件) の**監督裁定**を反映した — D-2 (README は正本)、D-3 (i) の fallback 経路、D-3 (ii) の 3 経路、D-4 (§0 の注記は規則形)、D-6 (前々書以前の指し方)、D-9 (依頼者確認の充足)、§1 の期待削減、§2 の (8) の実測 97 件、§4.2 の追加 2 項目。**行は消していない** (§1.8 の 56)。
- 状態: **監督が枠を確定済み (2026-09-23)**。決定は §3 の D-1〜D-10 であり、本書は再導出しない。作業は作業指示書 `docs/work-orders/WORK_ORDER_DOC_ARCHIVE_SPLIT_V1.md` で行う。
- 契機: **依頼者指示 2026-09-23** — 正本 (現在の状態を決める文書) と記録 (履歴) を分け、記録を検査器の走査対象から外して面積を減らす。**判断はしない**: 何を記録と見なすかで迷う文書は動かさず完了報告で列挙する (§6)。
- 台帳 ID は無い。commit 件名の token は `[archive-split]`。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う。本書は条項を複製せず番号で指す。
- 公開規律: archive も含め全ファイルに公開ゲートが掛かる (`CLAUDE.md` Public Repository Security Gate 節、同 §1.9)。実 DSN・実ホスト名・作業機の絶対パスを置かない。

---

## 1. 問題設定と守るべき条件

1. 文書が「現在の状態を決める文」と「時点付きの履歴」を同じ面に混ぜて持っており、検査器の走査面積と読み手の負荷が履歴の量に比例して増える。
2. **記録は消さない。** 出所追跡、R-17 のゲート記録、監査の証拠がそこにある。
3. **記録は書き換えない** (R-14、`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56・57)。移動は内容を変えない操作なので許される。
4. **公開ゲート (`tools/public_value_scan.py`、pre-commit) と空 `.md` ガードは緩めない** — 置き場を変えても公開リポジトリの条件は 1 ミリも変わらない。
5. 引き継ぎ書は次数で呼ばずファイル名で指す (同 §1.8 の 58)。既存文書からの参照を壊さない。

**第 1 段の期待削減は約 3,239 行** (引き継ぎ書 38 通 3,056 行 + 版数ログ 105 行 ≒ 走査面の **4.7%**)。**目的は面積そのものより走査面と記録の分離**であり、面積の主因 (§2 の (3)) は第 2 段・第 3 段と別件である。(v1.1、設計レビュー 10)

## 2. 起草時の実測 (2026-09-23、main `59facc2`)

| # | 観測 | 出所 |
|---|---|---|
| (1) | `check_doc_refs.iter_scan_files` の走査対象は **163 ファイル / 69,071 行**。うち `docs/work-orders/HANDOVER_*.md` が **40 通 / 3,134 行** (面積の 4.5%) | `tools/check_doc_refs.py`:160-177 |
| (2) | `check_doc_refs` の現状: G def=4 ref=126 / P def=9 ref=332 / R def=102 ref=4829 / L def=145 ref=2081、**dangling 0**、tracked md **188**、empty **0** | 実測 |
| (3) | 最大の `.md` は `WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1` 3,654 行 / `CONFORMANCE_ADAPTER_V1` 3,567 行 / `WORK_ORDER_R37_WP0_INVENTORY` 2,328 行。**面積の主因は引き継ぎ書ではない** | 実測 |
| (4) | 台帳 `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) v1.109 の版数ログは **3 行目から「旧 **v1.0**」行まで**で、その後の「起草:」「位置づけ:」「前提となる main:」の 3 行は前書きであり版数ログではない。§1.0g〜§1.0 の更新層と §1.1 が続く | `RM`:3-115 |
| (5) | 最新 2 通の引き継ぎ書 = `HANDOVER_20260923_FABLE5.md` (`d93e4f7`)、`HANDOVER_20260923_FABLE4.md` (`91214c4`)。FABLE5 は FABLE4 を「前書」、FABLE3 を「前々書」と **path で**指す | 実測 |
| (6) | 引き継ぎ書への path 参照: `docs/` 配下の非 HANDOVER 文書 **30 件超**が `docs/work-orders/HANDOVER_*.md` を path で指し、うち**行番号付き (`HANDOVER_X.md:NN`) 42 箇所**。コード・テスト・道具は HANDOVER の path を glob しない (`handover_ready.py` は明示引数、`check_doc_refs` は docstring で言及するだけ) | 実測 |
| (7) | `OPERATING_CONDITIONS.md` §0 は出所キー (`H0828` 等) → ファイル名の表を持ち「パスの無いものは `docs/work-orders/` 配下」と書く。各条項が `H0907F:25` 形式で引く | `docs/work-orders/OPERATING_CONDITIONS.md` §0 |
| (8) | `RM` の行番号引用 (`RM`:133 = P-6 等) は**既に陳腐化している** (P-6 は現在 386 行目)。本件の抽出で更にずれるが、**新種の問題ではない**。**【v1.1 追記 (設計レビュー 9、監督裁定: 両論のまま残し、本件では動かさない)】実測 97 件** (`RM`:NNN 形が 93 件 + フルパス形が 4 件。`docs/` 配下のみ)。**D-6 で版数ログが定数長 (5 版) になれば、以後の累積ずれは止まる** | 実測 |
| (9) | `check_doc_refs` の docstring は「`HANDOVER_*.md` を含む、除外リストを意図的に持たない (設計 D-2)」と書く。R-17 の空 `.md` ガード (`iter_tracked_markdown_files`、`git ls-files` 全 repo) は archive も見る。`KNOWN_NON_IDS` は空 | `tools/check_doc_refs.py`:57-63・:210、`docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md`:215・:264 |
| (10) | `check_comment_provenance` の走査は両 peer の `src/*.py` と `docs/code-history/<peer>/*.md` (非再帰) + `pair.md`。`docs/` 一般は見ない → **archive は元から対象外** | `tools/check_comment_provenance.py`:1984-1992・:1997-2010 |
| (11) | `change_class` は D (`security/`, `CLAUDE.md`, 公開方針, `public_value_scan.py`) → C (`spec/`, `conformance-tests/`, 契約 JSON の複製 2) → `.md` なら A → B の順。`docs/archive/` の `.md` は既に A、**非 `.md` は B**。CI は `--no-renames` なので**移動元 path は元のクラスで評価される** | `tools/change_class.py`:25-40・:148-159 |
| (12) | `tools/public_value_scan.py` (pre-commit、staged files) と `tools/rewrite_hash_refs.py` (`git ls-files *.md` 全体) は archive も対象。`tools/dev/README.md` の「Known gaps (all checkers)」表に `check_doc_refs` 3 件 / provenance 4 件 / `change_class` 2 件の索引行がある | `tools/dev/README.md`:49-80 |
| (13) | `OPERATING_CONDITIONS.md` §1 の最後は §1.15 (77)。次は **§1.16 (78)**。§5 に対応行、末尾の改版履歴に 1 行 | 同 §1.15・§5 |

## 3. 決定 (D-1〜D-10)

- **D-1 (定義)** **正本** = 現在の状態 (規律・設計・契約・台帳の行の現在値) を決める文。**記録** = 時点付きの履歴 (引き継ぎ書、版数ログ、改版履歴、「更新 (日付)」層、監査記録)。記録は**消さない** (§1 の 2)。記録は**書き換えない** (§1 の 3)。
- **D-2 (置き場)** ファイル全体は **`docs/archive/<元 path>`** へ **`git mv`** (履歴保持)。例: `docs/work-orders/HANDOVER_20260828.md` → `docs/archive/docs/work-orders/HANDOVER_20260828.md`。ファイルの**一部 (節)** を抜く場合は **`docs/archive/<元 dir>/<元 stem>__<部分名>.md`** (例 `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md`) とし、**先頭 3 行**に 出所ファイル / 抜き出した時点 (元文書の版数と commit) / 「逐語。書き換えない」を置く。`docs/archive/README.md` (短い) に この定義・path 規則・検査器の扱い・公開ゲートは変わらないこと を書く。**【v1.1 (設計レビュー 4)】`docs/archive/README.md` は `docs/archive/` の中で唯一の正本であり、「書き換えない」規則の対象外である。** 規則を変えるときは本設計の版上げと同時に直す。**【v1.1 (設計レビュー 2)】節を抜いた抽出ファイルは `git mv` ではないので `git log --follow` は繋がらない** — 出所の担保は先頭 3 行のヘッダ (出所ファイル / 抜き出した時点 = 元文書の版数と commit / 「逐語。書き換えない」) が負う。
- **D-3 (検査器)**
  - (i) **`check_doc_refs`**: `iter_scan_files` は `docs/archive/` を**走査しない** (参照側)。**定義は正本ファイルから読むので不変**。R-17 の空 `.md` ガードは**全 repo のまま**で archive も見る。docstring の「除外リストを持たない (D-2)」の文は **archive に限り本設計が上書きし**、その旨を docstring に書く (上書き対象は `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md`:215 の「赤が出たときの一般規則」と :264)。**【v1.1 (設計レビュー 1)】`iter_tracked_markdown_files` の fallback (git 不在・`git ls-files` 失敗時) は archive を含む独自の rglob 集合を使う** (`iter_scan_files(repo_root, include_archive=True)`) — 参照走査の除外が空 `.md` ガードの fallback 経路へ漏れると、archive の 0 バイト化が見えなくなるためである。`KNOWN_NON_IDS` の用途 (残る 2 通の引き継ぎ書) は変えない。**archive 内の ID 参照は解決しない** = 記録の中の参照が正本の変更で赤になることは無い。
  - (ii) **`check_comment_provenance`**: 走査対象外 (元から。§2 の (10))。**テストで固定する**。**【v1.1 (設計レビュー 7)】companion の列挙は 3 経路あるので、そのうち glob 経路 (`_companion_files`) と tree 経路 (`_companion_rel_paths_from_tree`) を 1 件ずつ固定する。**
  - (iii) **`change_class`**: **`docs/archive/` 配下は拡張子を問わず Class A** (D・C の後、`.md` 規則の前に評価)。移動元 path は `--no-renames` により元のクラスで評価される。
  - (iv) **`public_value_scan` / pre-commit / `rewrite_hash_refs`**: 変えない (archive も対象)。
  - (v) `tools/tests` に (i)(ii)(iii) のテストと変異。**【v1.1 (設計レビュー 1・7)】空 `.md` ガードは git 経路と fallback 経路で 2 件、provenance は glob 経路と tree 経路で 2 件**とする (合計 6 件)。
  - (vi) `check_doc_refs` と `check_comment_provenance` の docstring `Known gaps` に項目を足し、`tools/dev/README.md` の索引行を更新。`change_class` は **path 規則の段落**に足す (規則そのものは穴ではない)。**【v1.1 (設計レビュー 6・8)】内訳は `check_doc_refs` 2 項目 (archive の除外 / D-6 の回転の取りこぼし)、`check_comment_provenance` 1 項目、`change_class` は path 規則の 1 文に加えて `Known gaps` 1 項目** (archive への新規作成)。逐語の案は §4.2。
- **D-4 (正本→記録の参照)** 記録を抜いた場所に **「記録: `docs/archive/...`」の 1 行だけ**を置く。`OPERATING_CONDITIONS.md` §0 の表には**注記 1 行**。**【v1.1 (設計レビュー 5)】注記はキーを 1 件ずつ列挙せず規則形で書く** — 「引き継ぎ書は最新 2 通を除き `docs/archive/docs/work-orders/` 配下 (§1.16 の 78)」。**既存文書の中の `docs/work-orders/HANDOVER_*.md` path 参照 (§2 の (6)) は書き換えない** — 引き継ぎ書は `git mv` で行番号を保つので `HANDOVER_X.md:NN` はそのまま読める。解決規則は `docs/archive/README.md` の 1 行 (`<元 path>` → `docs/archive/<元 path>`)。
- **D-5 (段階)** **第 1 段 (本件)** = `HANDOVER_*.md` のうち**最新 2 通 (FABLE5・FABLE4) 以外の 38 通**と、台帳の版数ログのうち**最新 5 版 (v1.109〜v1.105) 以外** (v1.104 行から「旧 **v1.0**」行まで) の抽出。**第 2 段** = 台帳 §1.0〜§1.0g の更新層を「現在の状態」1 節に畳み、層は archive へ。**第 3 段** = 各設計文書の改版履歴 (同)。第 2 段・第 3 段は**本件では実施しない**。
- **D-6 (回転規則)** **新しい引き継ぎ書を commit する変更セットで、最新 2 通から外れる引き継ぎ書を同時に `git mv` する。** 台帳は**版上げの変更セットで 6 版目の行を** archive ファイルの先頭 (ヘッダ直後) へ移す (降順を保つ)。**【v1.1 (設計レビュー 6、監督裁定 β: 機械検査は足さない)】新しく書く文書が前々書以前を指すときは archive 側の path で書く** (同じ変更セットで移す前々書も archive 側の path で書く)。**執行は手順の規律であり、`check_doc_refs` に検査を足さない** (受け止めは §4.2 の 4 項目目)。条項は §4 に置く。
- **D-7 (迷う文書は動かさない)** 依頼者指示による。候補は §6 に**列挙だけ**する。
- **D-8 (WP 構成)** **WP-1** = 検査器 (実装担当。`git` 操作なし)、**WP-2** = 移動と正本側 1 行 (監督)、**WP-3** = 実測 (監督)。詳細と完了条件は作業指示書。
- **D-9 (正本の更新)** `OPERATING_CONDITIONS.md` **§1.16 (78) 1 条** (§4 の逐語) + **§5 の行** + **改版履歴 1 行**。`RM` **v1.110** (【v1.2】統合時に main が R-79 で v1.110 を使っていたため **v1.111**): 版数ログ先頭に 1 行 (変更内容と版数ログの移動先)、**§9 の 8 の A 行に「`docs/archive/` 配下の全ファイル」を足す** (`RM`:645)。**【v1.1 (設計レビュー、クラスの但し書き)】`OPERATING_CONDITIONS.md` §1 への条項追加に要る依頼者確認 (`RM` §9 の 8 の但し書き) は、依頼者指示 2026-09-23 をもって充足**とし、その旨を改版履歴の根拠欄に書く。
- **D-10 (完了報告に載せるもの)** 設計・指示書の path、移動件数、走査対象 `.md` 行数の前後、`check_doc_refs` の件数の前後、台帳の新版数、完了ゲートと `tools/tests` の集計行、§6 の列挙。

## 4. 正本に入れる逐語

### 4.1 `OPERATING_CONDITIONS.md` §1.16 (78) — 監督が本節から写す

> 78. 記録 (時点付きの履歴: 引き継ぎ書のうち最新 2 通以外、台帳の版数ログのうち最新 5 版以外、以後の段で定める改版履歴・更新層) は `docs/archive/<元 path>` に `git mv` で置き、検査器 (`tools/check_doc_refs.py` の参照走査、`tools/check_comment_provenance.py`) は走査しない。`tools/change_class.py` は `docs/archive/` 配下を Class A とする。空 `.md` ガードと公開値スキャンは archive にも掛かる。正本から記録へは「記録: `docs/archive/...`」の 1 行で指す。新しい引き継ぎ書を commit する変更セットで最新 2 通から外れる引き継ぎ書を、台帳の版上げの変更セットで 6 版目の行を、それぞれ同時に移す。既存文書の path 参照は書き換えない (解決規則は `docs/archive/README.md`)。設計 `docs/design/DOC_ARCHIVE_SPLIT_V1.md`。(依頼者指示 2026-09-23)

### 4.2 監査照合の対象 (変異を持たない完了条件の照合先)

D-3 の (vi) が足す文は、機械検査を持たない (docstring の散文と README の索引行である)。**【v1.1 (設計レビュー 3)】監査照合の照合者は監督である** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.13 の 74 の表の S 列「主張 vs 実測は監督が道具の出力と突合する」を準用。本件は監査担当を起動しない)。したがって作業指示書の当該完了条件は**監査照合**とし、照合対象の逐語を本節に置く。**下記は案であり、実装後に監督が確定して本節を版上げする** (§1.5 の 34: 主張は実測の後)。 **【v1.2】確定済み — 現物の docstring と索引行が正であり、下記の案と実質同内容である (コードレビュー 1 (f) で照合)。`check_doc_refs` の Known gaps 4 には `docs/archive/README.md` の例外 (唯一の正本だが置き場基準の除外に入り、参照は解決されない。設計の版上げと同時にしか直さない) を足した。**

- `tools/check_doc_refs.py` の `Known gaps` に足す 1 項目 (3 要素: 何を検出しないか / 理由 / 代わりに何が受け止めるか)
  - 何を検出しないか (案): `docs/archive/` 配下の `.md` の中の宙づり参照。**同じ除外により `check_scan_readability` (読めない `.md` の検出) からも外れる。**
  - 理由 (案): 記録は書き換えないので、そこに残る参照を赤にしても直す手が無い (D-1・D-3 (i))。定義は正本ファイルから直接読むので定義数には影響しない。
  - 代わりに何が受け止めるか (案): 空 `.md` ガードと公開値スキャンは archive にも掛かり (D-3 (iv))、正本側の参照は従来どおり走査される。
- `tools/check_comment_provenance.py` の `Known gaps` に足す 1 項目
  - 何を検出しないか (案): `docs/archive/docs/code-history/<peer>/*.md` に置かれた companion の複製。
  - 理由 (案): companion の列挙は `docs/code-history/<peer>/` 直下の非再帰 glob であり、archive はその外にある (§2 の (10))。
  - 代わりに何が受け止めるか (案): 登録簿の正本 `docs/code-history/` は動かさない (§6)。
- `tools/change_class.py` の path 規則の段落に足す文 (案): 「`docs/archive/`  (任意の深さ) は拡張子を問わず A。D・C の後、`.md` 規則の前に評価する。」
- **【v1.1 (設計レビュー 6 の裁定 β)】`tools/check_doc_refs.py` の `Known gaps` に足す 2 項目目**
  - 何を検出しないか (案): 最新 2 通を超えて `docs/work-orders/` に残った引き継ぎ書 (D-6 の回転の取りこぼし)。
  - 理由 (案): 回転は手順の規律であり (D-6)、走査側に「最新 2 通」を数える検査を足さない。
  - 代わりに何が受け止めるか (案): 監督の `ls docs/work-orders/HANDOVER_*.md` と、新しい引き継ぎ書の冒頭 (前書・前々書の path) の確認。
- **【v1.1 (設計レビュー 8)】`tools/change_class.py` の `Known gaps` に足す 3 項目目**
  - 何を検出しないか (案): `docs/archive/` 配下に**新規作成**されたファイル (記録の移動ではなく、そこで書き起こされたもの) を A から重いクラスへ上げない。
  - 理由 (案): 分類は path だけで行い、その path が移動先か新規作成かを見ない。
  - 代わりに何が受け止めるか (案): D-2 の path 規則 (archive には `<元 path>` の写しか節の抽出しか置かない) と、変更セットごとの監督の `git status --short` の確認。
- `tools/dev/README.md` の索引行: `check_doc_refs` 3 → **5**、`check_comment_provenance` 4 → 5、`change_class` 2 → **3**。

## 5. 却下した代替案

| # | 案 | 却下の理由 |
|---|---|---|
| 1 | 引き継ぎ書を削除する / squash する | 記録の消失 (R-17 のゲート記録、監査証拠)。§1 の 2 に反する |
| 2 | 検査器の除外を「`HANDOVER_*.md`」という**名前**で行う | 記録の種類が増えるたびに除外規則が増える。**置き場**で決めれば 1 規則で済む |
| 3 | 既存文書の path 参照を一括書き換え | 記録の書き換え (R-14)。30 文書超の変更で参照が揺れる (D-4) |
| 4 | `docs/archive` を `git ls-files` の空 `.md` ガードからも外す | Drive の 0 バイト化は archive でも起きる |
| 5 | `change_class` で archive を「変更なし」扱い (クラス無し) にする | 空集合は unknown = 全部回すため逆効果。A が正しい |

## 6. 未確定 (依頼者判断待ち。両論のまま残す)

1. **第 2 段の「現在の状態 1 節」の書き方** (台帳 §1.0〜§1.0g の層を畳んだ後の §1 の形)。**どちらにも寄せない。**
2. **D-7 の候補のうちどれを記録と見なすか。** 下記はいずれも**本件では動かさない**。記録と見なす / 正本のまま残す の両論を残す。
   - `docs/work-orders/DEPLOY_*.md`
   - `docs/work-orders/PUBLICATION_GATE_20260906.md`
   - `docs/work-orders/CCR14_DESIGN_PHASE_RECORD_20260829.md`
   - `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md`
   - 閉止済み項目の `docs/work-orders/WORK_ORDER_*.md`
   - `RM` §8 末尾「R-23 着手前調査資料 (非正本)」
   - `OPERATING_CONDITIONS.md` 自身の改版履歴
   - `docs/code-history/` — **provenance の登録簿であり正本。動かさない** (両論の対象ではない)

## 7. 作業

作業指示書 `docs/work-orders/WORK_ORDER_DOC_ARCHIVE_SPLIT_V1.md` (WP-1 検査器 / WP-2 移動と正本側 1 行 / WP-3 実測)。**変更クラスは全体 B** (`tools/*.py` に触る)、**文書の移動自体は A** (`RM`:645)。**規模は依頼者指定の手順に従う** — 設計レビュー 1 回、コードレビュー 1 回、監査担当は起動しない (`docs/work-orders/OPERATING_CONDITIONS.md` §1.13 の 74 の表より依頼者指示が優先)。

**順序**: WP-3 の**移動前**の計数 → WP-1 → WP-2 → WP-3 の**移動後**の計数。移動前後の差を比べる計数 (D-8) があるので、WP-2 を挟む形に分かれる。**並行では走らせない**ので §1.2 の 16・17 の重なり表は本来不要だが、触る面が分かれていることを実ファイル名で示す。

| WP | 触るファイル (実名) | 重なり |
|---|---|---|
| WP-1 | `tools/check_doc_refs.py`、`tools/check_comment_provenance.py`、`tools/change_class.py`、`tools/tests/test_check_doc_refs.py`、`tools/tests/test_comment_provenance.py`、`tools/tests/test_change_class.py`、`tools/dev/README.md` | — |
| WP-2 | `docs/work-orders/HANDOVER_*.md` 38 通 (移動)、`docs/design/ROADMAP_POST_PHASE7_V1.md`、`docs/archive/README.md` (新規)、`docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` (新規)、`docs/work-orders/OPERATING_CONDITIONS.md` | WP-1 と **0** |
| WP-3 | 書き込み無し (計数のみ) | WP-1・WP-2 と **0** |
