# 開発プロセス衛生 v1 作業指示書 — Change Set Manifest

**設計文書 `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md` (v1.1) が唯一の正本である。本書は manifest のみを持ち、裁定・根拠・却下案・実装の具体形を複製しない — 食い違ったら設計が正であり、本書の誤りとして監督へ差し戻す。**

- 版数: **v1.1 (2026-09-07、改稿 1)**。変更は末尾の**改版履歴**にある。上位計画: `docs/design/ROADMAP_POST_PHASE7_V1.md` (§4・§8・§9)
- 前提となる main: **`124ffa7`**。作業 branch **`process-hygiene-id-refs`**、worktree `{repo}/.claude/worktrees/process-hygiene`
- 体制: Fable 監督/判断/コミット、Opus 起草/レビュー/監査、Sonnet 実装 (**コミットしない**)
- **本書の形式は設計 §3 D-3 の Change Set Manifest そのものである。本作業がその実証を兼ねる。**
- **未確定**: 設計 §5 の **U-1 / U-3 / U-4 / U-5 は依頼者判断待ち**である (**U-2 は監督裁定 2026-09-07 で解消済み** — 実施形は設計 §3 D-2)。**U-3 は WP-2 の範囲**、**U-4 は WP-3 の着手条件**、**U-5 は WP-1 のパス**に効く。裁定前に着手する場合は監督推奨案を仮採用し、裁定が異なったときは**本文を書き換えず §4 の訂正註で直す**
- 順序 (**改稿 1 で固定**): **WP-1 (Class A) → 依頼者採否 → WP-3 (計画文書への適用) → WP-2 (検査の実装と配線)**。**WP-2 の CI / pre-commit 配線は WP-3 が main に入った後にのみマージする** — 本 3 文書が言及する計画文書の新規 ID は WP-3 が定義を入れるまで宙づりであり、先に検査を CI へ入れると両 job が pytest に到達する前に赤になる (設計 §3 D-3 / §8)
- 完了ゲート (全 WP): pre-commit 全ファイル + `tools/tests` + `tools/check_doc_refs.py` が実 repo で 0 件 + **WP-2 マージ時に監督が root suite を単独実行** (Class B)
- **共通の禁止**: 契約 JSON・`spec/`・`security/`・`conformance-tests/`・両 peer のコード・`conformance-tests/COLLECTION_FLOOR`・フェーズ9 の設計文書と作業指示書・`docs/work-orders/HANDOVER_*.md`・`CLAUDE.md` に**どの WP も触らない**。以下の各 WP の「触らないファイル」はこれに加わる固有分だけを挙げる

---

## WP-1 現行運用条件ファイル

### 目的
16 冊の引き継ぎ書に散在する運用条件を単一正本 `docs/work-orders/OPERATING_CONDITIONS.md` に集約する。第 16 次以降の引き継ぎ書はフェーズ固有の差分のみを持つ。

### 読むべき正本
- `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md` **§1.1**、**§2**、**§3 D-1** (節構成・書式・更新規約・矛盾の裁定 4 件)、**§5 U-5**
- 条項の一次資料: **`docs/work-orders/HANDOVER_*.md` の原文である。** 調査出力 (2026-09-07、監督保管) の引き継ぎ書棚卸しは**索引としてのみ使い、各条項は原文の `file:line` を開いて確認する** (調査出力には誤りが実在した — 設計 §1.1 (5) の訂正を見よ)

### 触るファイル
- `docs/work-orders/OPERATING_CONDITIONS.md` (**新設**。U-5 の裁定が (B)(C) ならパスを変える)

### 触らないファイル (共通の禁止に加えて)
- `docs/work-orders/HANDOVER_*.md` (**16 冊すべて。履歴であり書き換えない**)
- `docs/design/ROADMAP_POST_PHASE7_V1.md` (WP-3 の対象)

### 完了条件 ↔ 検査の 1 対 1 表

**本 WP は文書のみの変更 (Class A) であり、テストによる変異を持たない。各条件には「監督・監査が何を何と突き合わせるか」を検査の出力として対応付ける。**

| # | 完了条件 | 対応する検査の出力 |
|---|---|---|
| 1-1 | §1〜§5 の 5 節がすべて存在する | 節見出しの `grep -c` → **5** |
| 1-2 | 全条項が「1 行 = 1 条件、末尾に出所 `file:line` と最終確認日」の形である | 出所欄の無い条項行を拾う grep → **0 行**。監査照合 |
| 1-3 | §1〜§3 の条項が設計 §3 D-1 の列挙を漏れなく含む | **引き継ぎ書の原文 (`file:line`) を開いての照合**。調査出力の分類 (i) 18 件・(ii) 9 件・(iii) 8 件は**索引としてのみ使う**。監査照合 |
| 1-4 | §4 に失効条項が入る — migration 番号、L7-19 の予定文、常駐 pytest プロセス、調査出力の (iv) 該当分 | 設計 §3 D-1 の裁定 1〜3 との突合に加え、**各出所の原文 (`file:line`) を開いての照合**。監査照合 |
| 1-5 | §5 が第 14 次の 2 冊を**ファイル名で**指す | ファイル名を伴わない「第 14 次」の grep → **0 行** |
| 1-6 | §5 末尾に**註**が 1 件ある — CLAUDE.md の VPS 正本記述と配備実態は共存設計のもとで**照合済み・矛盾なし** (2026-09-07)。**「未裁定」節は持たない** | 設計 §3 D-1 裁定 4 との逐語突合。監査照合 |
| 1-7 | ファイル末尾に改版履歴 (日付・変更・根拠コミット) がある。**版数は持たない** | 末尾表の存在と `版数:` 行が無いことの grep |
| 1-8 | 実 PID の数字・作業機の絶対パス・実ホスト名・個人名を含まない | 下記の検証コマンド → **終了コード 0**、findings **0 件** |
| 1-9 | 上記 1-1〜1-8 に対応の無い行が本表に無い (メタ条件) | 監査照合 |

### 検証コマンドと集計行の期待形
```
python3 tools/public_value_scan.py docs/work-orders/OPERATING_CONDITIONS.md
```
**期待**: 終了コード **0**、findings **0 件**。未追跡ファイルは `git ls-files` に載らないため、**明示引数で走査する**。

### 使用テンプレート番号
**3 (Opus 起草)**。監督確認をもって完了とする。

### 変更クラス
**A** (文書のみ)。

---

## WP-2 文書 ID 参照検査

### 目的
全域一意な ID 族について「参照は必ず正本ファイルに定義を持つ」ことを機械的に固定する。現状は 0 件であり、検査は将来の参照腐敗の予防である。

### 読むべき正本
- `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md` **§1.2** (実測)、**§3 D-2** (対象族と正本の表、トークン文法、走査対象、判定、赤が出たときの一般規則、除外規則 (a)、位置、テスト項目 T-1〜T-6、開示事項)、**§5 U-2 / U-3**
- 流儀の手本: `tools/check_collection_floor.py` の module docstring、`tools/public_value_scan.py` (標準ライブラリのみ)、`tools/tests/test_rewrite_hash_refs.py` (置き場と、root suite に収集されないこと)
- 逐語プロトタイプ: **調査出力 (2026-09-07、監督保管) の `scan_doc_refs.py` / `scan_doc_refs.out`**

### 触るファイル
- `tools/check_doc_refs.py` (**新設**)
- `tools/tests/test_check_doc_refs.py` (**新設**)
- `.github/workflows/ci.yml` (**1 step 追加のみ**。`Check COLLECTION_FLOOR` step の直後、`Run the common conformance gate` step の前。**step 名で位置を指す — 行番号で指さない**)
- `.pre-commit-config.yaml` (**1 hook 追加のみ**。U-3 = (A) の場合)
- `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` の **22 行目の表記修正 1 箇所のみ** (**Class A**) — `AuditSink` のフィールドを指す**ソース行範囲表記** (`L` に続けて `9-16` と書かれている箇所) を **`行 9〜16`** に直す。**L 族の ID ではなく行範囲であり、これを直さないと実 repo が 0 件にならない** (設計 §1.2 (3) / §5 U-2)。**同ファイルの他の行に触れない。フェーズ9 の文書ではなく、決定を覆すものでもないので R-14 に反しない**

### 触らないファイル (共通の禁止に加えて)
- `pyproject.toml` (**`testpaths` に `tools` を足さない** — `COLLECTION_FLOOR` を動かさないため。設計外の拡張であり、必要と判断したら実装前に監督へ上げる)
- `tools/` の既存 script (`check_collection_floor.py`・`public_value_scan.py`・`rewrite_hash_refs.py` ほか)
- `docs/` の既存文書 (**赤を消すために既存文書を書き換えない** — 赤が出たら監督へ上げる)。**例外は 2 つだけである**: (i) 上に明記した `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` の 22 行目の表記修正、(ii) 完了条件 2-5 の変異 (**恒久の変更として残さない** — 直後に scratchpad backup から `cp` で復元し、`sleep 3` の後に sha256 を 2 回照合する。`git checkout` は使わない)

### 完了条件 ↔ 変異の 1 対 1 表

**設計 §3 D-2 のテスト項目 T-1〜T-6 を assert 水準で書く。各項目にはそれだけを壊す変異を 1 つ対応付ける。変異の無い完了条件は書かない。**

**合成ツリーの共通前提 (2-1 / 2-2 / 2-3)**: **全族の正本ファイルを最小形で置く** — 正本が 1 つでも欠けると T-4 の判定 (読めない正本は非 0) が先に発火し、期待する終了コードが出ないからである。**2-4 だけが正本を欠いたツリーを使う。**

| # | 完了条件 (assert 水準) | 変異 (`file:操作`) → 赤になる test id |
|---|---|---|
| 2-1 (T-1) | 合成ツリー (`tmp_path`) に正本の無い参照を 1 件置くと、**終了コードが非 0** であり、標準出力に `file:line: FAMILY-ID has no definition in <正本>` 形の行が**その 1 件だけ**出る (**置く前のツリーで同形の行が 0 件であることを先に確認してから、1 件だけ出ることを assert する**) | `check_doc_refs.py`: 未定義参照検出後の `sys.exit(1)` を `sys.exit(0)` に変える → `test_dangling_reference_exits_nonzero` が赤 |
| 2-2 (T-2) | 非正本ファイルにだけ `**P-9**` 形の行を置いた合成ツリーで、`P-9` は**定義ありと判定されず非 0** になる | `check_doc_refs.py`: 定義収集を正本に限る条件を外し全走査対象から集める → `test_bold_row_outside_canonical_file_is_not_a_definition` が赤 |
| 2-3 (T-3) | **全族の正本を最小形で置いた合成ツリー**に `DM-NNNN` を 1 行足すと、**終了コード 0 のまま**、出力に外部 ID として列挙される | `check_doc_refs.py`: 外部接頭辞テーブルから `DM-` を削る → `test_external_prefix_is_reported_not_failed` が赤 |
| 2-4 (T-4) | 族の正本ファイルが**存在しない**合成ツリーで**非 0** であり、出力が「読めなかった」ことを述べる | `check_doc_refs.py`: 正本不在時に当該族を空集合として続行する (握りつぶす) → `test_missing_canonical_file_is_never_clean` が赤 |
| 2-5 (T-5) | **実 repo に対して終了コード 0** である (**変異前に同形の行が 0 件であることを確認してから、変異後に 1 件だけ出ることを assert する**) | `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md`: **存在しない 2 桁番号の SI 参照を 1 行足す** → `test_real_repository_has_no_dangling_reference` が赤。**変異トークンは指示書にも test source にも逐語で書かない — test 内で `"SI-" + "99"` のように連結して組み立てる** (逐語で書くと、その文書自身が宙づり参照を持ち、変異前の 0 件が成立しない)。**変異は直後に backup から `cp` で復元し、`sleep 3` 後に sha256 を 2 回照合する。`git checkout` は使わない** |
| 2-6 (T-6) | **空振り禁止**: 実 repo に対し、**対象族それぞれについて定義数 ≥ 1 かつ参照数 ≥ 1** を assert する | `check_doc_refs.py`: **SI 族の正規表現の桁指定を変える** (`\bSI-\d+[a-z]?\b` → `\bSI-\d{4}\b`) → 参照数が 0 になり `test_every_family_has_definitions_and_references` が赤。**走査対象を削る変異は使わない** — 定義は定数表のパスから直接読むので定義数が減らず、変異が空振りするからである (設計 §3 D-2 の判定) |
| 2-7 | CI の**両 job** (3.11 / 3.12) で、pytest step の**前**に `python3 tools/check_doc_refs.py` が走る | `.github/workflows/ci.yml`: 追加 step を pytest step の後ろへ移す → **監査照合** (step 順の diff と CI の run) |
| 2-8 | U-3 = (A) の場合、新 hook が **`pass_filenames: false`** かつ **`entry: python3 tools/check_doc_refs.py`** である | `.pre-commit-config.yaml`: `pass_filenames` を `true` にする → `pre-commit run --all-files` が引数過多で非 0。**監査照合** |
| 2-9 | `tools/check_doc_refs.py` が**標準ライブラリのみ**を import し、族と正本の対応表・除外規則が**script 内の定数**である (環境変数・設定ファイルから読まない) | import 行と `os.environ` の grep。**監査照合** |
| 2-10 | `pyproject.toml` の `testpaths` と `conformance-tests/COLLECTION_FLOOR` が**無変更**である | `git diff --stat` に両ファイルが**現れない**。**監査照合** |
| 2-11 | 上記 2-1〜2-10 に対応の無い行が本表に無い (メタ条件) | 監査照合 |

### 着手条件

1. **CI (`.github/workflows/ci.yml`) と pre-commit (`.pre-commit-config.yaml`) への配線は、WP-3 が main に入った後にのみマージする。** 本 3 文書が言及する計画文書の新規 ID は WP-3 が定義を入れるまで宙づりであり、先に配線を入れると CI の両 job が pytest に到達する前に赤になる。**script とテストの実装・レビューは先に進めてよい** (配線のマージだけを待つ)。
2. **U-2 の実施形は監督裁定 2026-09-07 で決着している** (設計 §3 D-2 / §5 U-2 — 接頭辞を既知フェーズ集合に限る + `**…**` スパンの初出 + `PHASE4_DURABLE_AUDIT_SINK_V1.md:22` の表記修正)。**実装担当はプロトタイプで実 repo 0 件を再実測してから 2-5 を主張する。0 件に到達しない場合は実装を進めず監督へ上げる** (常設規律「設計外の拡張は実装前に上げる」「主張は実測の後」)。

### 検証コマンドと集計行の期待形
```
./.venv/bin/python -m pytest -q tools/tests/test_check_doc_refs.py
```
**期待集計行**: `<N> passed in <T>s` — **N は本表の 2-1〜2-6 に対応するテスト関数の実数**であり、**failed / error / xfailed / skipped は 0** である。

```
python3 tools/check_doc_refs.py
python3 tools/check_collection_floor.py
./.venv/bin/pre-commit run --all-files
```
**期待**: `check_doc_refs.py` は終了コード **0**、標準出力は空または外部 ID (`DM-0018` × 3 箇所) の報告行のみ。`check_collection_floor.py` は終了コード **0** (収集数を動かしていないことの確認)。pre-commit は全 hook が `Passed`。

**root suite は回さない。** Class B の統合前検査として、**WP-2 のマージ時に監督が単独実行する** (`pytest -q -n 5 --dist loadgroup`)。実装担当・レビュー担当は回さない。

### 使用テンプレート番号
**2 (Sonnet 実装)** → **5 (Opus コードレビュー。報告に無い変異 1〜2 種を自分で試す)** → **6 (Opus 受け入れ監査)**。

### 変更クラス
**B** (コード変更。契約 JSON・`spec/` 配下・`security/` 配下・`conformance-tests/` 配下・登録済み同型 helper の本体・catalog 宣言値のいずれにも触れない)。**`PHASE4_DURABLE_AUDIT_SINK_V1.md` の表記修正 1 行だけを見れば A だが、1 コミットが複数のクラスに触れるときは最も重いクラスを採るので、本 WP 全体は B である** (設計 §7 の §9-8)。

---

## WP-3 計画文書への追記 (依頼者採否の後)

### 目的
設計 §7 の逐語案を `docs/design/ROADMAP_POST_PHASE7_V1.md` に適用し、**版数を適用時点の現行版の次の版へ上げる** (着手時に同ファイル `:3` の版数行を読んで決める。**1 行目の見出しの `v1` は文書名であり版数ではない**)。

### 読むべき正本
- `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md` **§7** (**貼る本文の逐語。言い換え・要約・語順の入れ替えを行わない**)、**§2.2 の 3** (追記は §9 と §8 の新規行のみ)、**§5 U-4** (適用時期)
- `docs/design/ROADMAP_POST_PHASE7_V1.md` **§8** (既存表の書式)、**§9** (既存 6 項目)

### 触るファイル
- `docs/design/ROADMAP_POST_PHASE7_V1.md` (**§9 に 7〜11 を追加、§8 の表末尾に 2 行を追加、冒頭の版数行を適用時点の次の版へ更新。それ以外の行に触れない**)

### 触らないファイル (共通の禁止に加えて)
- 同ファイルの **§1「現状」と §8 の既存行** (フェーズ9 完了時に更新される。衝突回避)
- `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md`、`docs/work-orders/OPERATING_CONDITIONS.md`

### 完了条件 ↔ 検査の 1 対 1 表

| # | 完了条件 | 対応する検査の出力 |
|---|---|---|
| 3-1 | §9 に 7〜11 の 5 項目と、§8 の表末尾に **R-15 / R-16** の 2 行が、設計 §7 の逐語と**文字単位で一致**して入る | 設計 §7 の fenced block と該当範囲の **diff → 0 行** |
| 3-2 | 冒頭の版数が**適用直前の版数より 1 段上がって**おり、`:3` と同じ書式で「**v1.N からの変更**」を述べる 1 行が足される (R-14) | 適用前後の版数行の diff。**監査照合** |
| 3-3 | §1「現状」と §8 の**既存行**が無変更である | `git diff` の該当範囲に変更が**現れない**。**監査照合** |
| 3-4 | §8 に追加した 2 行が、本書と設計文書から参照されている ID の**定義**になっている (参照検査が緑になる前提が満たされる) | **実施順により `tools/check_doc_refs.py` は WP-2 で入る。** 本 WP では**表の先頭セルが正本の定義書式 (太字) である**ことを監査照合し、**参照検査の実行は WP-2 の完了条件 2-5 で行う** |
| 3-5 | 上記 3-1〜3-4 に対応の無い行が本表に無い (メタ条件) | 監査照合 |

### 検証コマンドと集計行の期待形
```
python3 tools/public_value_scan.py docs/design/ROADMAP_POST_PHASE7_V1.md
```
**期待**: 終了コード **0**。**`tools/check_doc_refs.py` は WP-2 で入るので本 WP では走らせない** (実施順。設計 §3 D-3)。

### 使用テンプレート番号
**3 (Opus 起草)**。**監督確認をもって完了とする。**

### 変更クラス
**A** (文書のみ)。**着手条件は依頼者の採否と U-4 の裁定である。**

---

## §4 訂正註

**本フェーズ中に判明した本書の誤り・発注後の監督裁定を、本文を書き換えずにここへ追記する** (フェーズ6 §11 L6-18 の流儀)。

(現時点で該当なし)

---

## 改版履歴

| 版 | 日付 | 変更 | 根拠 |
|---|---|---|---|
| **v1.1** | 2026-09-07 | 改稿 1。**M-1** — WP の実施順を **WP-1 → 依頼者採否 → WP-3 → WP-2** に直し、WP-2 の**着手条件**に「CI / pre-commit 配線のマージは WP-3 が main に入った後」を置いた。完了条件 2-5 の変異トークンを**逐語で書かず test 内で連結生成する**形に改め、2-1 / 2-5 に「変異前 0 件の確認」を足した (裁定 M-1)。**M-4** — WP-2 の触るファイルに `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` の 22 行目の**行範囲表記の修正** (Class A) を加え、「触らないファイル」の例外 2 件を明記した (裁定 a + M-4、m-10)。**M-6** — 2-6 の変異を「走査対象から `security/` を削る」(定義を定数表から直接読むので空振りする) から「**SI 族の正規表現の桁指定を変える**」へ差し替えた (裁定 M-6)。**M-9 / m-16** — WP-1 の一次資料を「`HANDOVER_*.md` の原文。調査出力は索引としてのみ」に改め、完了条件 1-3 / 1-4 の検査を**原文 `file:line` を開いての照合**に変えた (裁定 M-7/M-8/M-9/小)。**M-2** — WP-3 の版数指定を「適用時点の現行版の次の版」に改め、完了条件 3-2 を「適用直前より 1 段上がり、`:3` と同じ書式で変更を述べる 1 行が足される」に書き換えた (裁定 M-2)。**m-1** — CI への挿入位置を step 名で指すようにした。**m-11** — 合成ツリーの共通前提 (全族の正本を最小形で置く) を明記し、2-3 を書き換えた。**裁定 c** — WP-3 の使用テンプレートを **3 (Opus 起草) + 監督確認**に確定し、両論併記を削った。**裁定 e** — 完了条件 1-6 を「未裁定 1 行」から「照合済み・矛盾なしの註」に改めた。**実施順の変更に伴う整合**: WP-3 の完了条件 3-4 と検証コマンドから `tools/check_doc_refs.py` の実行を外し、参照検査の実行を WP-2 の 2-5 に寄せた | 設計 `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md` v1.1 §9、設計レビュー 1 (2026-09-07、監督保管)、監督裁定 2026-09-07 |
| **v1.0** | 2026-09-07 | 起草初稿 (manifest 形式)。 | 設計 `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md` v1.0 |
