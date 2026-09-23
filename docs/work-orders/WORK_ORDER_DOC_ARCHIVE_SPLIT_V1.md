# 作業指示書 — 正本と記録を分け、記録を検査器の走査対象から外す (archive-split)

## 0. 版数・位置づけ

- **v1.0 (2026-09-23)。** 基点 main `59facc2`、worktree `.claude/worktrees/distracted-galileo-6027de` (branch `claude/distracted-galileo-6027de`)。**台帳 ID は無い** (依頼者指示 2026-09-23)。commit 件名の token は **`[archive-split]`**。
- **枠 (問題設定・決定 D-1〜D-10・却下案・未確定) は設計文書 `docs/design/DOC_ARCHIVE_SPLIT_V1.md` にある。** 本書は写さず節番号で指す (`RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §9 の 9、`RM`:658)。
- **変更クラスは全体 B** — `tools/*.py` に触る (`RM`:645)。**文書の移動自体は A**。CI は tools-tests job が常時、conformance job が B で回る。
- **規模**: 依頼者指定の手順 — **設計レビュー 1 回、コードレビュー 1 回、監査担当は起動しない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.13 の 74 の表より依頼者指示が優先)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`tools/dev/gate.py`・`tools/dev/finalize.py` は監督のみ**。道具は `tools/dev/`)。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。本書の訂正は本文を書き換えず訂正註として追記する (§1.8 の 57)。
- **本件は 1 つの変更セットである。** 順序は **WP-3 の移動前の計数 → WP-1 → WP-2 → WP-3 の移動後の計数** (設計 §7)。**並行 WP は無い**。触る面の重なりが 0 であることは設計 §7 の表が実ファイル名で示す。
- python は `<main checkout>/.venv/bin/python` (worktree に `.venv` は無い)。

## 1. 目的

記録 (時点付きの履歴) を `docs/archive/` に移し、参照走査と provenance の走査対象から外す。記録は消さず書き換えない。公開ゲートと空 `.md` ガードは緩めない。詳細は設計 §1・§3。

**読むべき正本**: 設計 `docs/design/DOC_ARCHIVE_SPLIT_V1.md` §1〜§4 と §7 / `docs/work-orders/OPERATING_CONDITIONS.md` §1.4・§1.5・§1.8・§1.9・§1.12 / `RM` §9 の 8・9 / `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md`:215・:264。

---

## 2. WP-1 — 検査器 (実装担当、Sonnet。`git` 操作なし)

**目的**: 設計 §3 の D-3 の (i)(ii)(iii)(vi) を実装し、(v) のテストと変異を足す。**文書は 1 つも動かさない** (移動は WP-2)。

**使用テンプレート**: 2 (実装担当)。**変更クラス**: B。

### 2.1 触るファイル (肯定列挙。これ以外に書き込まない)

```
tools/check_doc_refs.py
tools/check_comment_provenance.py
tools/change_class.py
tools/tests/test_check_doc_refs.py
tools/tests/test_comment_provenance.py
tools/tests/test_change_class.py
tools/dev/README.md
```

### 2.2 触らないファイル

**上記 7 ファイル以外のすべて。** とくに `docs/` (本書と設計文書を含む)、`spec/`、`security/`、`conformance-tests/`、`r2db-api/`、`MitateDB-api/`、`.github/`、`.pre-commit-config.yaml`、`tools/` の他の script (`public_value_scan.py`・`rewrite_hash_refs.py` は**変えない** — 設計 D-3 の (iv))。**新しいテストファイルを作らない** (既存の 3 ファイルに足す)。**`docs/archive/` を作らない**。

### 2.3 実装

1. `tools/check_doc_refs.py` の `iter_scan_files` (:160-177) が **`docs/archive/` 配下を走査対象に入れない**。定義の読み取り (定数表のパスから直接) は**変えない**。
2. 同ファイルの `iter_tracked_markdown_files` (:210) の空 `.md` ガードは**全 repo のまま**。archive を除かない。
3. 同ファイルの docstring: 走査範囲の段落 (:57-63) に **archive の除外**と、「除外リストを持たない (設計 D-2)」が **archive に限り `docs/design/DOC_ARCHIVE_SPLIT_V1.md` に上書きされた**旨を書く。`Known gaps` に 1 項目 (3 要素) を足す (設計 §4.2)。`KNOWN_NON_IDS` は変えない。
4. `tools/change_class.py`: **`docs/archive/` 配下は拡張子を問わず Class A**。評価順は **D → C → archive → `.md` → B** (`classify_path`、:148-159)。module docstring の path 規則の段落 (:25-40) に 1 文 (設計 §4.2)。
5. `tools/check_comment_provenance.py`: 走査を広げない (archive は元から対象外)。`Known gaps` に 1 項目 (設計 §4.2)。
6. `tools/dev/README.md` の「Known gaps (all checkers)」表の索引行を件数と要約ごと更新する (設計 §4.2)。

### 2.4 完了条件

| # | 完了条件 |
|---|---|
| (1) | `docs/archive/` 配下の `.md` に置いた宙づり参照が**報告されず**、`check_doc_refs` が 0 で終わる。同じ参照を `docs/` 直下に置けば従来どおり赤になる (positive control) |
| (2) | `docs/archive/` 配下の **tracked な 0 バイト `.md` は依然として検出され**、非 0 終了する |
| (3) | `change_class`: `docs/archive/x.txt` (非 `.md`) が **A**。`security/X.md` と `docs/archive/security/X.md` の組は**全体 D** (移動元は元のクラスで評価される) |
| (4) | `check_comment_provenance`: `docs/archive/docs/code-history/r2db-api/x.md` が **companion の列挙に入らない** |
| (5) | `tools/check_doc_refs.py` と `tools/check_comment_provenance.py` の docstring `Known gaps` に **1 項目ずつ** (3 要素)、`tools/change_class.py` の path 規則の段落に 1 文、`tools/dev/README.md` の索引行の件数と要約が揃っている。**監査照合** (変異なし)。照合対象の逐語は設計 §4.2 にある。報告に **`file:line`** を出す |
| (6) | (1)〜(5) に対応の無い変更行が無い。本表の外の変更を 1 行も入れていない (`git status --short` と `git diff` を報告に貼る。`git` の**読み取りのみ**) |

### 2.5 完了条件 ↔ 変異の 1 対 1 表

| 完了条件 | 変異 (`file`: 操作) | 期待 | 赤になる test |
|---|---|---|---|
| (1) | `tools/check_doc_refs.py`: `iter_scan_files` の archive 除外を外す | red | (1) の新テスト |
| (2) | `tools/check_doc_refs.py`: `iter_tracked_markdown_files` の対象から `docs/archive/` を除く | red | (2) の新テスト |
| (3) | `tools/change_class.py`: `classify_path` の archive 規則を外す | red | (3) の新テスト |
| (4) | `tools/check_comment_provenance.py`: `_companion_files` の `peer_dir` を `docs/` 起点に広げ、`glob` を `rglob` にする (**同一 entry の 2 edit**) | red | (4) の新テスト |
| (5) | **無し (監査照合)** — 散文と索引行であり機械検査を持たない。設計 §4.2 の逐語と現物を監督が突き合わせる | — | — |
| (6) | **無し (監査照合)** — 対応表そのものの検査 | — | — |

**1 変異 = 1 entry = 1 test id** (`mutate.py` は `-x` で最初の失敗で止まるため。`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 33・40)。

### 2.6 検証コマンドと集計行の期待形

```
tools/dev/pt.py -C .claude/worktrees/distracted-galileo-6027de -- tools/tests -q
tools/dev/mutate.py "$SP/wp1-mutations.json" -C .claude/worktrees/distracted-galileo-6027de -- tools/tests -q
```

- **`tools/tests` は root 完了ゲートに含まれない** (`tools/dev/README.md` の `gate.py` の Known gaps)。本 WP の証拠は上の 2 本である。
- 期待形: `pt.py` は `<基点の件数 + 新規テスト数> passed` で **failed 0 / error 0**。基点の件数は着手時に 1 回測って報告に書く (主張は実測の後。§1.5 の 34)。
- `mutate.py` は 4 entry すべて `expect=red` / `got=red`、復元の sha256 一致 2 回、`git grep -F` の件数一致。**summary 行と `log=` のパスをそのまま報告に貼る** (§1.10 の 65)。
- テストは既存 3 ファイルの fixture の形に倣う (`tools/tests/test_check_doc_refs.py` の `_build_minimal_tree` / `_git_init_and_add` / `_write`)。**実 credential・実ホスト名・作業機の絶対パスを fixture に書かない** (§1.9)。

---

## 3. WP-2 — 移動と正本側の 1 行 (監督)

**目的**: 設計 D-5 の第 1 段を行う。**変更クラス**: A (文書のみ)。**`git mv` を使う** — `git log --follow` で履歴が繋がることが完了条件だからである。

### 3.1 触るファイル

- 移動: `docs/work-orders/HANDOVER_*.md` のうち **最新 2 通 (`HANDOVER_20260923_FABLE5.md` / `HANDOVER_20260923_FABLE4.md`) を除く 38 通** → `docs/archive/docs/work-orders/<同名>`。対象は `ls docs/work-orders/HANDOVER_*.md` の出力からこの 2 通を除いたもの (実測 40 通)。
- 抽出: `docs/design/ROADMAP_POST_PHASE7_V1.md` の版数ログのうち **`v1.104` 行から「旧 **v1.0**」行まで** を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ**逐語で**移す。先頭 3 行は 出所ファイル / 抜き出した時点 (元文書の版数 `v1.109` と commit) / 「逐語。書き換えない」(設計 D-2)。**最新 5 版 (v1.109〜v1.105) は正本に残す。**
- 正本側の 1 行: 台帳は版数ログの直後に **「記録: `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md`」**。`docs/work-orders/OPERATING_CONDITIONS.md` §0 の表に**注記 1 行** (archive にある引き継ぎ書のキーの解決先)。
- 新規: `docs/archive/README.md` (本変更セットで先に作る)。
- 正本の更新 (設計 D-9): `OPERATING_CONDITIONS.md` **§1.16 (78)** = 設計 §4.1 の逐語 + **§5 の対応行** + **改版履歴 1 行**。`RM` **v1.110** = 版数ログ先頭に 1 行 + **§9 の 8 の A 行に「`docs/archive/` 配下の全ファイル」**。

### 3.2 触らないファイル

**既存文書の中の `docs/work-orders/HANDOVER_*.md` への path 参照を 1 箇所も書き換えない** (設計 D-4。行番号付き 42 箇所を含む)。`docs/code-history/`、設計 §6 に列挙した「迷う文書」、`spec/`、`security/`、`conformance-tests/`、両 peer、`tools/`。

### 3.3 完了条件

| # | 完了条件 |
|---|---|
| (1) | 移動 **38 件** + 抽出 **1 件**。`docs/work-orders/HANDOVER_*.md` に残るのは FABLE5・FABLE4 の **2 通**。**監査照合** |
| (2) | 移動した 38 通と抽出先について **`git log --follow <新 path>` が移動前の commit まで遡れる**。**監査照合** |
| (3) | **0 バイトの tracked `.md` が 0 件** (`check_doc_refs` の空 `.md` ガードが緑)。Drive の 0 バイト化を `git status --short` と **`git diff --cached --stat` で全行削除の行が無いこと**で確認する。**監査照合** |
| (4) | 台帳の版数ログの残りが **v1.109〜v1.105 の 5 版**、抽出先の先頭 3 行が設計 D-2 の形、抽出した行が**逐語で 1 行も欠けていない** (移動前後の行数の和が一致)。**監査照合** |
| (5) | `OPERATING_CONDITIONS.md` §1.16 (78) が設計 §4.1 の逐語と一致し、§5 と改版履歴に各 1 行。`RM` が v1.110 で §9 の 8 の A 行に archive が入っている。**監査照合** |
| (6) | (1)〜(5) に対応の無い変更行が無い (`git diff --stat` を報告に貼る) |

**変異は無い** — 文書の移動と逐語の転記であり、`tools/*.py` の挙動側は WP-1 の変異が受け持つ。照合対象の逐語は設計 §4.1 (§1.16 の条文) と抽出元の版数ログ本体である。

---

## 4. WP-3 — 実測 (監督)

**目的**: 設計 D-8 の WP-3。**移動前**と**移動後**に同じ計数を取り、差が説明できることを示す。**書き込みは無い。**

### 4.1 取る計数 (移動前 = WP-1 の前、移動後 = WP-2 の後)

| # | 計数 | 期待 |
|---|---|---|
| (1) | `check_doc_refs.iter_scan_files` の**走査対象 `.md` 件数と総行数** | 移動前 163 / 69,071 (実測) → 移動後は 38 通 + 抽出分だけ減る |
| (2) | 族ごとの **def 件数** (G / P / R / L) | **不変** (定義は正本ファイルから直接読む。設計 D-3 の (i)) |
| (3) | 族ごとの **ref 件数** | **移動したファイル群が持っていた参照数だけ減る**。移動前に当該 38 通 + 抽出範囲の参照数を数え、**差が一致する**こと |
| (4) | **dangling** | 前後とも **0** |
| (5) | **tracked md 件数** と **empty** | 件数は不変 (移動なので)、empty は前後とも **0** |

### 4.2 完了条件

| # | 完了条件 |
|---|---|
| (1) | (1)〜(5) の前後の値を表で報告し、(2) が不変・(3) の差が一致・(4)(5) が期待どおりであること。**監査照合** |
| (2) | 一致しない項目があれば**進めず監督が止める** (主張は実測の後。§1.5 の 34) |
| (3) | (1)(2) に対応の無い主張が報告に無い |

**変異は無い** (計数のみ)。照合対象は道具の出力そのもの (報告に逐語で貼る)。

---

## 5. 本変更セットで実施しないこと

- **第 2 段** (設計 D-5): 台帳 `RM` §1.0〜§1.0g の更新層を「現在の状態」1 節に畳み、層を `docs/archive/` へ移す。**本チャットでは実施しない** — 畳んだ後の §1 の形が**未確定 (依頼者判断待ち。設計 §6 の 1)** だからである。
- **第 3 段** (設計 D-5): 各設計文書の改版履歴を `docs/archive/` へ移す。**本チャットでは実施しない。**
- **設計 §6 の 2 に列挙した「迷う文書」は 1 件も動かさない** (依頼者指示 2026-09-23)。完了報告で列挙する (設計 D-10)。

---

## 6. 訂正註 (2026-09-23、設計レビュー 1 回の監督裁定)

**本文は書き換えない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 57)。以下は上の本文に対する訂正であり、**衝突する箇所は本節が優先する**。設計は同日 **v1.1** に上がった (`docs/design/DOC_ARCHIVE_SPLIT_V1.md` の改版行)。

1. **【§0 に 1 行】(裁定 3)** 本書の「**監査照合**」の照合者は**監督**である (`docs/work-orders/OPERATING_CONDITIONS.md` §1.13 の 74 の表の S 列「主張 vs 実測は監督が道具の出力と突合する」を準用)。本件は監査担当を起動しない。

2. **【§2.3 の 1・§2.4 の (2)・§2.5】(裁定 1)** `iter_tracked_markdown_files` の **fallback 経路** (git 不在・`git ls-files` 失敗時) は **archive を含む独自の rglob 集合**を使う (`iter_scan_files(repo_root, include_archive=True)`)。参照走査の除外がこの経路へ漏れると archive の 0 バイト化が見えなくなる。完了条件 (2) を次の 2 つに分け、**変異も 2 件**にする。

   | # | 完了条件 | 変異 | 期待 |
   |---|---|---|---|
   | (2a) | **git 経路**: `docs/archive/` 配下の tracked な 0 バイト `.md` が検出され非 0 終了する | `tools/check_doc_refs.py`: 空 `.md` ガードの対象から `docs/archive/` を除く | red |
   | (2b) | **fallback 経路**: `git ls-files` が使えない条件でも `docs/archive/` 配下の 0 バイト `.md` が検出される | `tools/check_doc_refs.py`: fallback の `include_archive=True` を外す | red |

3. **【§2.4 の (4)・§2.5】(裁定 7)** companion の列挙は 3 経路あるので、そのうち **glob 経路**と **tree 経路**を 1 件ずつ固定する。完了条件 (4) を次の 2 つに分け、**変異も 2 件**にする。

   | # | 完了条件 | 変異 | 期待 |
   |---|---|---|---|
   | (4a) | `_companion_files` が `docs/archive/docs/code-history/r2db-api/x.md` を列挙しない | `tools/check_comment_provenance.py`: `_companion_files` の `peer_dir` を `docs/` 起点に広げ `glob` を `rglob` にする (同一 entry の 2 edit) | red |
   | (4b) | `_companion_rel_paths_from_tree` が同じ path を列挙しない | `tools/check_comment_provenance.py`: `peer_prefix` を `docs/` 起点に広げ、直下のみの条件を外す (同一 entry の 2 edit) | red |

4. **【§2.3 の 3・5・6 と §2.4 の (5)】(裁定 6・8、および「読めない `.md`」の指摘)** `Known gaps` の内訳を次に改める。逐語の案は設計 §4.2。
   - `tools/check_doc_refs.py`: **2 項目** — (a) archive の除外 (「何を検出しないか」に **`check_scan_readability` (読めない `.md`) からも外れる**ことを含める)、(b) **最新 2 通を超えて `docs/work-orders/` に残った引き継ぎ書を検出しない** (設計 D-6 の回転は手順の規律であり、**機械検査は足さない** — 監督裁定 β)。
   - `tools/check_comment_provenance.py`: 1 項目 (本文どおり)。
   - `tools/change_class.py`: path 規則の段落の 1 文に**加えて `Known gaps` 1 項目** (archive 配下への**新規作成**を A から上げない)。
   - `tools/dev/README.md` の索引行: `check_doc_refs` **3 → 5**、`check_comment_provenance` **4 → 5**、`change_class` **2 → 3**。

5. **【§2.5・§2.6】** 上記 2・3 により **変異は 4 件 → 6 件**。`mutate.py` の期待形は「**6 entry すべて `expect=red` / `got=red`**」に読み替える。

6. **【§3.3 の (2)】(裁定 2)** `git log --follow` の完了条件は**移動した 38 通に限る**。**節を抜いた抽出ファイル** (`docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md`) は `git mv` ではないので履歴は繋がらない — 出所の担保は**先頭 3 行のヘッダ** (出所ファイル / 抜き出した時点 = 元文書の版数と commit / 「逐語。書き換えない」) が負う (完了条件 (4) が既に見ている)。

7. **【§3.1 の「正本側の 1 行」】(裁定 5)** `OPERATING_CONDITIONS.md` §0 の注記は**キーを 1 件ずつ列挙せず規則形で書く** — 「引き継ぎ書は最新 2 通を除き `docs/archive/docs/work-orders/` 配下 (§1.16 の 78)」。

8. **【§3.3 の (5)】(クラスの但し書き)** `OPERATING_CONDITIONS.md` §1 への条項追加に要る**依頼者確認** (`RM` §9 の 8 の但し書き) は、**依頼者指示 2026-09-23 をもって充足**とし、その旨を**改版履歴の根拠欄**に書く。完了条件 (5) はこの記載の有無も見る。

9. **【§4.1 の (5)】(誤りの訂正)** 「tracked md 件数は**不変**」は**誤りである**。移動 (`git mv`) では不変だが、本変更セットは新規ファイルを **4 件** (設計 `DOC_ARCHIVE_SPLIT_V1.md`、本書、`docs/archive/README.md`、抽出ファイル) 足すので、**188 → 192** が期待値である。empty は前後とも 0 のまま。

10. **【§1 の「目的」】(裁定 10、参考値)** 第 1 段の期待削減は**約 3,239 行** (38 通 3,056 行 + 版数ログ 105 行 ≒ 走査面の 4.7%)。**目的は面積そのものより走査面と記録の分離**であり、面積の主因は第 2 段・第 3 段と別件である (設計 §1 末尾・§2 の (3))。

11. **【§2.4 の (5)、§2.5 の (4b)】(コードレビュー 1 の反映、監督裁定 2026-09-23)** コードレビュー (4 件) の裁定: (1) `tools/check_doc_refs.py` の R-17 節の断言「fallback は参照走査と同じ scope」は本変更で偽になっていたので、fallback が `include_archive=True` で `docs/archive/` を含む旨に書き換えた (直した)。(2) `docs/archive/README.md` は archive 内で唯一の正本だが置き場基準の除外に入る — **除外から外さず Known gaps 4 に例外として記録する** (既知の穴。同ファイルは設計の版上げと同時にしか直さない)。(3) 変異 4b「2 edit のうち非再帰条件は寄与しない」は**実測で否定された** — prefix 緩和だけの 1 edit では `p[len(peer_prefix):]` の固定幅スライスが archive の path に「/」を残すため test_4b は緑のまま (`got=green`)。archive の排除は exact-prefix と非再帰条件の**組**で成り立っており、2 edit の変異 (設計レビュー 7 の指定どおり) が正しい。変異表の読みを「4b は両条件の組を固定する」に改める。(4) `test_fallback_zero_scan_does_not_force_failure` の monkeypatch を `lambda repo_root, *, include_archive=False: []` に厳密化した (直した)。再実行: `pt: 617 passed` / `mutate: 6 mutations, 6 as expected`。

12. **【§2.1 の触るファイル、§3 の WP-2】(監督の追加 2026-09-23)** `tools/dev/finalize.py` は staged 済みの削除 (`git mv` の移動元) を `git add -- <path>` に渡して `pathspec did not match` で止まった (終了 78)。移動元は index に既に反映されているので、作業ツリーにも index にも無い path を `git add` から除く形に直し、`tools/tests/test_dev_tools.py::test_finalize_commits_a_staged_rename` (staged rename を commit できる) を足した。変異 (除外を外し全 path を add) は赤。触るファイルに `tools/dev/finalize.py`・`tools/tests/test_dev_tools.py` を足す。
