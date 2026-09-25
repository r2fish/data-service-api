# 作業指示書 — フェーズ11 keyset ページング (契約 1.8.0 → 1.9.0)

## 0. 版数・位置づけ

- **v1.2 (2026-09-24)。** 基点 local main `0fee6e5`。Change Set Manifest 形式 (`docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §9 の 9)。
- **改版履歴**: **v1.0 (2026-09-24)** 起草。**v1.1 (2026-09-24)** — v1.0 起草担当の疑義 7 件への監督裁定 (直す 5、採用 2) と設計 v0.5 への追随。v1.0 は未コミットの初稿なので、訂正註 (`OC` §1.8 の 57) ではなく本文を直した。直した節: §1.2 (`conformance-tests` 全体の実行時間)、§1.3 (一時フリップの組の採用の記録)、§1.6 の 5、WP-1 (R-107 行、Revision note の置き場)、WP-2 (MitateDB の cursor 付き読み出しの入口)、WP-4 (入口の本体の差し替え)、WP-6 (control 側宣言と 1.8.0 のピン、記録の一覧)。同日、起草担当の疑義 4 件を反映 — conformance の全体を実装担当が回さない形へ §1.2・§1.6 の 1・各 WP の道具の引数と完了条件を改め (前景で peer ごとの部分集合 `-k "not MitateDB"` / `-k "not r2db"` だけ。和が全体を覆うことを WP-1 で 1 回実測)、WP-2 / WP-4 に runtime の入口 → cell の実体を明記し、WP-6 に `test_denial_details_and_request_id.py` の 1.8.0 のピン 2 本を足した。 **v1.2 (2026-09-24)** — 依頼者裁定 Q-3 (見直し 1 点 = `where` の順序に依らない束縛を含む) / Q-5 (a) / Q-4 の反映と設計 v0.6 への追随。本書は未コミットなので、v1.1 と同じく本文を直した。直した節: §0、§1.1 の 4 (Q-4 の形)、§1.4 (確定文ファイル)、WP-1 (Q-5 の分岐を (a) で閉じた)、WP-2 (B の並べ替えの観測と非空振り)、WP-5 (束縛 hash の正規化と helper `canonical_page_binding`、完了条件 9a・9b、変異 M5-9a)、WP-4 (同じ helper、完了条件 9a・9b、変異 M4-9a)、WP-6 (`_ISOMORPHIC_TARGETS` 3 行、件数ピン `..._159_rows`、変異 M6-4b)。
- 正本設計: `docs/design/PHASE11_KEYSET_PAGING_V1.md` **v0.6** (以下「設計」)。問題設定と守るべき条件は設計 §1〜§2、決定と根拠は D-1〜D-9、却下した代替案は §4、依頼者裁定と裁定待ちは §5、C-28 は §6、Security Invariants は §7、WP の骨子・依存・統合 branch は §9、限界は §10。**本書はそれらを写さず節番号で指す。**
- 台帳: `RM` §8 の R-106 (仮)。規模 **L** (`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.13 の 74)、変更クラス **D** (設計 §8)。
- **本書の番号はすべて仮である** — R-106 / R-107 / C-28 / migration 0015 / port v1.16 / 従属判断 14、および契約版数 1.9.0 (設計 §9 の並走の注意、§10 の 8)。**merge 直前に main を読んで振り直す。** 振り直した番号は本書 §9 に訂正註として記し、本文は書き換えない (`OC` §1.8 の 57)。
- 本書も C-28・R-106・R-107 を引くので、設計 §9 末尾の `check_doc_refs` の制約が同じく掛かる。
- 役割: 実装担当 (テンプレ 2) が WP ごとに 1 回、コードレビュー (テンプレ 5) を WP ごとに 1 回、受け入れ監査 (テンプレ 6) を全 WP の後に 1 回 (`docs/work-orders/ROLE_PROMPT_TEMPLATES.md` の Class C・D 手順)。commit・完了ゲート・merge は監督。

## 1. 全 WP 共通

### 1.1 統合 branch と順序

1. 以下 `WT=.claude/worktrees/cranky-visvesvaraya-616e67` (リポジトリ root からの相対)。branch は `claude/cranky-visvesvaraya-616e67`。**全 WP をこの 1 つの worktree で直列に行う。並走しない** (監督裁定 2026-09-24。設計 §9 の「WP-4 と WP-5 だけが並走できる」は構造の事実として残り、本件では使わない)。
2. **順序: WP-1 → WP-2 → WP-5 → WP-3 → WP-4 → WP-6 → WP-7。** WP-5 (r2db) は WP-3 に依存しないので先に置く。WP-4 は WP-3 と WP-5 の両方の後である (codec の本体を WP-5 から写すため。§6.6)。
3. 各 WP の commit は監督が `./.venv/bin/python tools/dev/finalize.py -C $WT --branch claude/cranky-visvesvaraya-616e67 --no-merge --allow '<その WP の触ってよいパス>' -m "$SP/p11-wpN-msg.txt"` で branch に積む。次の WP は前の WP の commit の後に着手する。
4. **main への merge は WP-7 の後の 1 回だけ**である (設計 §9 の統合 branch。`OC` §1.1 の 3 の例外であり、採否は監督裁定)。手順: (1) main を読んで §0 の仮番号を振り直す (2) 振り直しで変わった箇所を直す (3) 完了ゲート `./.venv/bin/python tools/dev/gate.py -C $WT --label p11` を 1 回 (4) **Q-4 の依頼者確認** (設計 §5.1。契約版に触れる main へのコミットはこの merge である。依頼者裁定 2026-09-24 の形: (3) の完了ゲートの集計行と、main に対する branch の `git diff --stat` を添えて確認を取る) (5) `finalize.py` (`--no-merge` を付けない) で merge。
5. **WP-2〜WP-5 の完了判定は、各 WP の期待結果表 (C-28 の 9 node × 6 plug) と `pt.py` の実測の一致で行う。** 完了ゲートと CI の合格条件 (xfailed = 0 かつ xpassed = 0。`OC` §1.3 の 22) を満たすのは WP-6 以降である (設計 D-4 (vii) と §9)。

### 1.2 道具の引数

- 道具はリポジトリ root から root の `.venv` で起動する (worktree に `.venv` は無い)。
  - テスト: `./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- <tests> -q`
  - 変異: `./.venv/bin/python tools/dev/mutate.py "$SP/p11-wpN-mutations.json" -C $WT --wait 300`
- 期待結果表の照合は `-rxX` を付けた `pt.py` の log (`log=` の行) の short test summary で行う。報告には `pt.py` / `mutate.py` の出力行 (集計行・変異表・`log=`) をそのまま貼る (`OC` §1.10 の 65)。
- **`conformance-tests` 全体は前景 1 回 (Bash の timeout パラメータ 600000) に収まらない** (直近の実測 606 s。R-105。C-28 で伸びる)。**実装担当は前景 Bash で peer ごとの部分集合 (`-k "not MitateDB"` / `-k "not r2db"`、各 < 600 s) だけを直列に回す** (`OC` §1.5 の 39)。adapter 名を node ID に含まないテストは 2 本の両方で走る (重複は許容)。**2 本の和が `conformance-tests` 全体を覆うことは、`--collect-only -q` で 2 本の和集合が全体の node 集合と一致することを WP-1 の実装担当が 1 回実測し、報告に件数 (全体・2 本それぞれ・和集合) を貼って示す** (監督裁定 2026-09-24)。**`conformance-tests` 全体は監督の完了ゲート (`tools/dev/gate.py`) でだけ回す** (監督裁定 2026-09-24)。各 WP の完了条件の「部分集合 2 本」はこの 2 本を指す。
- `$SP` は監督が発注時に渡す scratchpad である。一時ファイルはその配下にだけ置く。

### 1.3 版ゲート下の変異 (一時フリップ)

- WP-6 より前は、C-28 の node は xfail か XPASS であり、**xfail と XPASS(non-strict) はどちらも pytest の終了コード 0** である。`mutate.py` の判定 (`red` = 終了コード 1、`green` = 0) では本体の破れが見えない。
- したがって C-28 の本体を壊す変異は、**`edits` にその peer の宣言の一時フリップを含める多点変異**とする: `r2db-api/src/r2db_api/capabilities_document.py` または `MitateDB-api/src/mitatedb_api/capabilities_document.py` の `"contract_version": "1.8.0",` → `"contract_version": "1.9.0",`。フェーズ9 作業指示書 `docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md` WP-1 (12) と同じ趣旨であり、復元と照合は `mutate.py` が行う。
- 各変異ファイルの先頭に**対照** (フリップだけの entry、同じ node id で `expect: "green"`) を置く。対照が緑でなければ、その変異ファイルの赤は変異の証拠にならない — 報告して止まる。
- この組 (宣言の一時フリップ + 本体変異の多点変異と、フリップだけの対照) は監督裁定 2026-09-24 で採用した。理由は上の 1 点目 — WP-6 より前は xfail と XPASS(non-strict) が同じ終了コード 0 であり、フリップを含まない変異では本体の破れが赤にならない。
- 「全 plug で赤」を主張する変異は、plug ごとに entry を分ける (`mutate.py` は `-x` で最初の赤で止まる)。
- フリップを含む状態を commit しない。WP-6 より前の commit の前に、両 peer の `capabilities_document.py` に `"1.9.0"` が 0 件であることを確認する (`OC` §1.4 の 31)。

### 1.4 確定文言の所在

- **契約 1.9.0 の確定文と C-28 の Condition 文は `$SP/verbatim-190.md`** (監督の scratchpad。依頼者確定後に監督が置く)。**Q-3 と Q-5 は依頼者裁定 (2026-09-24。設計 §5.1) で確定した — Q-3 は見直し 1 点 (案文 C-4 の `where` を述語の順序を問わない束縛にする) を含み、Q-5 は (a)。確定文ファイル `$SP/verbatim-190.md` は監督が本改版の後に置く (案文 `verbatim-190-draft.md` は設計 D-1 と同文)。確定文ファイルが置かれる前に WP-1 を始めない。**
- 実装・docstring・文書へは確定文ファイルから逐語で複製し、言い換えない (`OC` §1.5 の 35・36)。
- `security/CONTROL_MAPPING.md` の主張は設計 §7 の**案**であり、実測の後に確定する (`OC` §1.5 の 34)。C-28 行の Evidence 欄・Status 欄は設計 §6.1。

### 1.5 C-28 の node の略記 (期待結果表)

node 名は設計 D-4 の node 表の**案**であり、WP-2 の実測で確定する。

| 略記 | node (案) | 設計 D-4 の観測 |
|---|---|---|
| T | `test_c28_paged_traversal_is_the_unpaged_sequence` | (i) + (vi) + key 集合 (order_by の変種を parametrize) |
| I | `test_c28_concurrent_insert_discriminates_keyset_from_offset` | (ii)。版ゲートは strict |
| B | `test_c28_cursor_binding` | (iii) |
| A | `test_c28_cross_application_cursor_is_refused` | (iv) |
| R | `test_c28_cursor_refusal_details` | 拒否の 2 キー |
| S | `test_c28_cursor_is_stateless` | (v) |
| D | `test_c28_cursor_is_deterministic` | (viii) |
| DP | `test_c28_default_page_is_the_largest_page` | 既定ページ (義務 (7)) |
| PS | `test_c28_page_size_outside_schema_is_refused_at_page_size` | `page.size` = 0 / 1001 |

plug の略記: r = `r2db-api`、rh = `r2db-api-http`、rs = `r2db-api-socket`、m = `MitateDB-api`、mh = `MitateDB-api-http`、ms = `MitateDB-api-socket`。セルの略記: **x** = xfail、**F** = XPASS(strict) → FAILED、**X** = XPASS(non-strict)、**ok** = passed。**\*** = 見込み (実測で確定し報告に表で貼る)。T の parametrize 変種はすべて同じセルに従う。

### 1.6 共通の禁止事項

1. git 操作、`tools/dev/gate.py`、`tools/dev/finalize.py` を実行しない。root suite も `conformance-tests` 全体も回さない (§1.2。全体は監督の完了ゲートでだけ回す)。下請けの Agent を起動しない (`OC` §1.7 の 47、§1.11 の 70)。
2. 各 WP の「触ってよいパス」の外に触る必要が出たら、また設計に無い検査・機構・語彙が要ると分かったら、実装前に監督へ上げる (`OC` §1.5 の 37)。
3. `xfail` の `strict` を緑にするために変えない。`skip` を使わない。`COLLECTION_FLOOR` を触らない (`OC` §1.3 の 25)。
4. 一時フリップ (§1.3) を含む状態を残さない。変異の復元は `mutate.py` に任せ、`git checkout --` を使わない。
5. R-107 を実施しない (台帳行を足すだけ。WP-1)。
6. 実 credential・実ホスト名・作業機の絶対パス・実 DSN・traceback を書かない (`OC` §1.9)。
7. 設計の決定・裁定・却下案を再審議しない。設計との食い違いは読み替えずに報告する。

### 1.7 監査照合の記録

完了条件のうち変異を持たないもの (対応表で「監査照合」) は、照合対象の逐語記録 (実行したコマンドと集計行、または file:line) を設計 §11 に WP ごとに残す。残すこと自体をその完了条件の一部とする (`OC` §1.5 の 40)。 このため、各 WP の触ってよいパスは設計 §11 への記入を含む。

## 2. WP-1 — 契約 1.9.0 の文言と記録

### 目的

契約 1.9.0 (従属判断 14) を契約 JSON と同梱 copy 2 本に置き、逐語ピンと記録を同じ変更セットで揃える。C-28 行を `declared` で、R-106 と R-107 を台帳に置く。**peer の宣言値は上げない。**

### 依存・正本

- 依存: 確定文ファイル `$SP/verbatim-190.md` (Q-3・Q-5 の依頼者裁定)。
- 正本: 設計 D-1 の (A)〜(D) と根拠、D-5 の表、§6.1、§9 の WP-1 行と末尾の `check_doc_refs` の制約。手本は 1.7.0 → 1.8.0 の spec 側 commit `654e23e` (設計 D-5 の「手本」)。

### 触ってよいパス

- `spec/data-service-api.v1.json`、`spec/CONTRACT_HISTORY.md`、`spec/CCR_DISPOSITION.md`、`spec/OPERATION_CATALOG.json`、`spec/README.md` (設計 §9 の `spec/*`。`spec/CONTRACT_HISTORY_MANIFEST.json` は変更が要るときだけ)
- `r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json`
- `conformance-tests/test_contract.py`、`conformance-tests/test_contract_history_register.py`、`conformance-tests/test_operation_catalog_register.py`
- `conformance-tests/CONDITIONS.md` (C-28 行の追加のみ)、`conformance-tests/CONDITIONS_HISTORY.md` (`## C-28` の追加のみ)
- `RM` (§8 に R-106 行と R-107 行を足すのみ)、設計 (D-5 の `spec/CONTRACT_HISTORY.md` 行への実測の追記のみ)

触らない: 両 peer の `src/` (同梱 copy を除く)、`capabilities_document.py`、`conformance-tests/adapter.py`、plug、`security/`。

### タスク

1. 契約 JSON に確定文ファイルの A (位置は設計 D-1 (A))、B、C-1〜C-6 (`structured_operations.paging`。位置は設計 D-1 の「節の名前」)、C-7 (`Page.cursor`)、D (`contract_version`) を逐語で置く。既存の遡及列挙文の機械的な追随は設計 D-1 (A) の直後の段落のとおり。3 複製を同一バイトにする。
   - **Q-5 は (a) で確定した (依頼者裁定 2026-09-24。設計 §5.1)。`Page.cursor` は `{"type": "string"}` である。** v1.1 にあった (b) の分岐は閉じた。
2. `spec/OPERATION_CATALOG.json` を `./.venv/bin/python $WT/tools/contract_catalog.py` で再生成する (出力先が `$WT/spec/` であることを確認する)。
3. `spec/CCR_DISPOSITION.md` に従属判断 14 の節 (設計 D-5 の行)。`spec/CONTRACT_HISTORY.md` に設計 D-5 の行が定める Revision note 3 本 (1.9.0 の追加 / `Page.size` 範囲外の拒否と既定ページ / `Page.cursor` の `maxLength`) を、**すべて既存の `## versioning.version_binding` 節に置く。新しい `## <json_path>` 見出しを作らない** (設計 D-5 の行の v0.5 の改め)。**marker 走査の実測 (見つかった marker の件数と、増えた `## <json_path>` 節の有無) を設計 D-5 の同じ行に追記する。**
4. `conformance-tests/test_contract.py` に 1.9.0 の逐語ピン (1.8.0 のピン `test_contract_pins_the_1_8_0_ruling_sentences_verbatim` と同形)、`versioning.obligations` の版ラベル集合、`Page` / `QueryResult` の schema ピン。register 系 2 本を版に追随させる。
5. `CONDITIONS.md` に C-28 行を 1 行 (Condition 欄は確定文ファイルから逐語、Invariants 欄は設計 §6.1、Status は `declared`)。`CONDITIONS_HISTORY.md` に空でない `## C-28` (設計 D-5 の行)。
6. `RM` §8 に R-106 行を R-105 行の形で起票する (内容は設計 §0 の台帳 ID と §8 の規模・クラスを引く)。同時に R-107 行を設計 §9 の「WP-1 の材料」の案文のとおり置く (実施はしない。設計 §10 の 5)。台帳の版上げと版数ログの回転 (`OC` §1.16 の 78) は main への merge 1 回につき 1 回 (`OC` §1.13 の 75) なので、WP-6 でまとめて行う。

### 完了条件 (assert 水準)

1. 3 複製の `versioning.obligations` に 1.9.0 entry があり、conditional 7 件・unconditional 0 件、obligation 名が確定文ファイルの B と一致する (新しい obligations ピンが緑)。
2. `versioning.version_binding` の 1.9.0 段落が確定文ファイルの A と逐語で一致し、位置が設計 D-1 (A) のとおり (新しい version_binding ピンが緑)。
3. `structured_operations.paging` の 6 文が確定文ファイルの C-1〜C-6 と逐語で一致する (新しい paging ピンが緑)。
4. `Page.cursor` が確定文ファイルの C-7 のとおり (schema ピンが緑。Q-5 = (a) なので `maxLength` が無い)。
5. 既存ピンの変更が、1.9.0 の追随 (遡及列挙・版ラベル・`contract_version`) に限られる。
6. 3 複製が同一バイト (`test_contract_packaged_copies_are_byte_identical` が緑)。
7. `CCR_DISPOSITION.md` に従属判断 14 がある (`test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition` が緑)。
8. `CONTRACT_HISTORY.md` の Revision note 3 本がすべて `## versioning.version_binding` 節にあり (新しい `## <json_path>` 見出しが無い)、register test (`test_contract_history_companion_heading_set_matches_the_scanner` を含む) が緑。marker 走査の実測が設計 D-5 の行に追記されている。
9. `spec/OPERATION_CATALOG.json` が再生成と一致する (`test_operation_catalog_register.py` が緑)。
10. `CONDITIONS.md` の C-28 行 (`declared`) と `CONDITIONS_HISTORY.md` の `## C-28` がそろい、`conformance-tests/test_conditions_register.py` が緑。
11. `RM` §8 に R-106 行と R-107 行があり、`(cd "$WT" && python3 tools/check_doc_refs.py)` が dangling 0。
12. `spec/README.md` の現行版の記述が 1.9.0。
13. 両 peer の宣言 `contract_version` が 1.8.0 のまま (`"contract_version": "1.8.0"` の grep 件数が着手前と同じ)。
14. `conformance-tests` の部分集合 2 本 (§1.2) と両 peer の suite が緑 (failed / xfailed / xpassed = 0)。
15. 下の対応表に、変異も監査照合も持たない行が無い。

### 非空振り要件

新しいピンは、確定文ファイルの文字列を定数として持ち契約 JSON の値と等号で比べる (部分一致にしない)。3 複製すべてに掛かる (同一バイトのピンと合わせて)。

### 同型性テストの対象

なし (本 WP は peer のコードに触れない)。

### 道具の引数

```
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_contract.py conformance-tests/test_contract_history_register.py conformance-tests/test_operation_catalog_register.py conformance-tests/test_conditions_register.py -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not MitateDB" -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not r2db" -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- r2db-api/tests MitateDB-api/tests -q
./.venv/bin/python tools/public_value_scan.py <触ったファイル>
(cd "$WT" && python3 tools/check_doc_refs.py)
./.venv/bin/python tools/dev/mutate.py "$SP/p11-wp1-mutations.json" -C $WT --wait 300
```

### 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (Class C。WP-1 単独の差分として)。

### 禁止事項

§1.6 に加えて: 確定文を言い換えない。provenance marker (`Since 1.x.y` 等) を新しい契約値に入れない (設計 D-5 の `spec/CONTRACT_HISTORY.md` 行)。`spec/CONTRACT_HISTORY.md` に新しい `## <json_path>` 見出しを作らない。`required` 配列・既存キー・既存 enum を変えない。

### 完了条件番号 → 変異

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | M1-1: 3 複製の 1.9.0 entry から conditional の 7 件目を削る | 新しい obligations ピン |
| 2 | M1-2: 3 複製の A の 1 語を変える | 新しい version_binding ピン |
| 3 | M1-3: 3 複製の `paging.refusal` の 1 語を変える | 新しい paging ピン |
| 4 | M1-4: 3 複製の `Page.cursor` に `"maxLength": 512` を戻す | `Page` の schema ピン |
| 5 | 監査照合: `test_contract.py` の差分で、既存ピンの変更行がすべて 1.9.0 の追随であること (差分の行を報告に列挙し設計 §11 に残す) | — |
| 6 | M1-6: `r2db-api/src/r2db_api/contract/data-service-api.v1.json` だけ 1 語変える | `test_contract_packaged_copies_are_byte_identical` |
| 7 | M1-7: `CCR_DISPOSITION.md` の従属判断 14 の見出し番号を変える | `test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition` |
| 8 | M1-8: `spec/CONTRACT_HISTORY.md` に `## definitions.Page.cursor` 見出しを足し、`Page.cursor` の Revision note をそこへ移す。加えて監査照合: register test の集計行と、設計 D-5 の行に追記した marker 走査の実測 | `test_contract_history_companion_heading_set_matches_the_scanner` |
| 9 | M1-9: `spec/OPERATION_CATALOG.json` の `contract_version` を 1.8.0 に戻す | `conformance-tests/test_operation_catalog_register.py` |
| 10 | M1-10: `CONDITIONS_HISTORY.md` の `## C-28` 節を削る | `test_conditions_history_has_exactly_the_main_tables_ids` |
| 11 | 監査照合: `check_doc_refs` の出力行 | — |
| 12 | 監査照合: `spec/README.md` の差分 | — |
| 13 | 監査照合: grep の件数 (着手前と後) | — |
| 14 | 監査照合: `pt.py` の集計行 2 本 | — |
| 15 | 監査照合: 本表 | — |

## 3. WP-2 — port v1.16 と C-28

### 目的

port v1.16 に `query_page` (`budget` 付き) を足して 6 plug に実装し、C-28 の 9 node を版ゲート付きで置く。MitateDB に cursor 付き読み出しの入口を置く (本体は WP-4 まで現行と同じ拒否)。C-28 行の Status を `executable` に上げる。

### 依存・正本

- 依存: WP-1。
- 正本: 設計 D-4 (port の signature と約束、C-28 の観測表、非空振り、node 表、node の遷移)、§6.2、§6.3、D-5 の `CONDITIONS.md` 行、D-2b の 4 (v0.5 の追記)、§9 の WP-2 行。版ゲートの手本は `conformance-tests/test_c25_result_request_id.py`:214-226、`observed_branch` の突合は同:433-450 と `conformance-tests/test_c21_denial_details_vocabulary.py`:366-385、およびフェーズ9 作業指示書 `docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md` §6 の訂正註 7。

### 触ってよいパス

- `conformance-tests/adapter.py`、`conformance-tests/test_c28_keyset_paging.py` (新規)
- `r2db-api/conformance/conformance_adapter_r2db.py`、`conformance_adapter_r2db_http.py`、`conformance_adapter_r2db_socket.py`
- `MitateDB-api/conformance/conformance_adapter_mitatedb.py`、`conformance_adapter_mitatedb_http.py`、`conformance_adapter_mitatedb_socket.py`
- `docs/design/CONFORMANCE_ADAPTER_V1.md` (§4.4 に 1 行)
- `conformance-tests/CONDITIONS.md` (C-28 行の Status のみ)
- `MitateDB-api/src/mitatedb_api/cell.py` (cursor 付き読み出しの runtime の入口と cell の実体の追加のみ)、`MitateDB-api/src/mitatedb_api/http.py` (query endpoint の入口への切り替えと cursor 拒否の除去のみ)
- `MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py` (件数ピンの追随のみ。拒否の call site が移って件数が変わるとき)

触らない: r2db の `src/`、MitateDB の `src/` のうち上の 2 本以外、`spec/`、既存の `select_eq` / `attempt_filter` / `query_with_budget` の signature、他の条件のテスト。

### タスク

1. `adapter.py` に抽象メソッド `query_page` (signature は設計 D-4。docstring に port 版 v1.16・追加理由・引数を peer の実 query 入口へ逐語で渡す原則・`budget` は `None` なら要求に載せない規約)。
2. 6 plug に実装する。返り値は `(items, next_page)` で `next_page` は peer の値をそのまま返す。拒否は `ConformanceDenial`。adapter は拒否を捏造しない。**MitateDB の 3 plug の `query_page` は、タスク 6 の入口へ cursor を逐語で渡すだけである** (in-process plug は runtime の入口を直接、http / socket plug は要求本体で)。
3. `test_c28_keyset_paging.py`: `@pytest.mark.condition("C-28")`、9 node (§1.5)、6 plug で駆動。版ゲートは `adapter.parse_semver` の実行時 xfail で、**I だけ `strict=True`、他の 8 node は `strict=False`**。本体の assert は無条件に実行し、**`observed_branch` の突合は `>= 1.9.0` の分岐でだけ行う** (設計 D-4 の非空振りの段落)。観測の中身は設計 D-4 の (i)〜(viii) と node 表のとおり (I の挿入 2 行は entity の中で一意な order key、後ろに挿入した行の出現は記録のみ。S は同一 Application の別 credential の別セッションで `iso` を使わない。DP は `budget: {result_items: 3}` と 4 行の entity で、`request_budget` を `unavailable` と宣言する plug は宣言 `limits.result_items` + 1 行。R は `conftest.assert_details_vocabulary_values_safe` を掛け、details を 2 キーの等号で比べる。B は設計 D-4 の node 表の v0.6 のとおり、`where` の述語を並べ替えただけの要求で cursor が有効 (拒否されず続きのページを返す) ことも観測する)。`skip` を使わない。
4. `CONDITIONS.md` の C-28 行の Status を `executable (six adapters)` で始まる形に上げる (設計 §6.1 の Status 欄。本文の確定は WP-6)。
5. `CONFORMANCE_ADAPTER_V1.md` §4.4 に `query_page` の 1 行。
6. MitateDB: cursor 付き読み出しの入口を `ApplicationRuntime` (`MitateDB-api/src/mitatedb_api/cell.py`:3648 の `read` と並ぶ位置。`http.py` と in-process adapter が呼ぶ層) に、実体を `ApplicationCell` に置く (runtime の入口 → cell の実体。設計 D-2b の 4 の新メソッド。名は実装で決める)。実体は WP-4 まで、cursor ありなら現行 `MitateDB-api/src/mitatedb_api/http.py`:654-657 と同じ拒否 (`CAPABILITY_UNSUPPORTED` / `violated_declaration: capability` / `field: page/cursor`)、cursor なしなら `(rows, None)` を返す。`http.py` の query endpoint をこの入口を呼ぶ形に切り替え、`http.py` 側の cursor 拒否を消す (拒否の置き場は入口 1 箇所)。L1 走査の件数ピン (`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`:590 `"cell.py"`、:594 `"http.py"`) が変わるなら実測値へ追随させる (`OC` §1.5 の 40b)。

### 期待結果表 (WP-2 の commit の時点)

| node | r | rh | rs | m | mh | ms |
|---|---|---|---|---|---|---|
| T | X\* | X\* | X\* | x | x | x |
| I | x | x | x | x | x | x |
| B | x\* | x\* | x\* | x | x | x |
| A | X\* | X\* | X\* | x | x | x |
| R | x\* | x\* | x\* | x | x | x |
| S | X\* | X\* | X\* | x | x | x |
| D | X\* | X\* | X\* | x | x | x |
| DP | x\* | x\* | x\* | x | x | x |
| PS | x\* | x\* | x\* | x | x | x |

r2db の \* は設計 §9 の見込み (設計レビュー 2 の見込みは (i)(iv)(v)(viii) が X)。**x と X のどちらになるかは実測で確定し、確定した表を報告に貼る。** F は 0 件でなければならない。

### 完了条件 (assert 水準)

1. `adapter.py` に `query_page` の抽象メソッドがあり、6 plug がすべて実装している (6 plug で C-28 の node が収集され、adapter の生成で失敗しない)。
2. `CONDITIONS.md` の C-28 行の Status が `executable` で始まり、`test_every_marked_condition_id_maps_to_an_executable_status` が緑。
3. I の本体が offset 実装で落ちる: r2db を一時フリップすると r / rh / rs の I が赤。
4. `pt.py -rxX` の実測が上の期待結果表と一致し (\* は確定値)、F が 0 件。
5. `conformance-tests` の部分集合 2 本 (§1.2) で failed = 0、xfailed と xpassed はすべて C-28 の node である。
6. `CONFORMANCE_ADAPTER_V1.md` §4.4 に port v1.16 の行がある。
7. MitateDB の cursor 拒否が入口 1 箇所にあり、`http.py` に cursor の拒否が無い。HTTP の cursor 付き要求は入口を通って `CAPABILITY_UNSUPPORTED` になる (`MitateDB-api/tests/test_http.py` の `test_page_cursor_is_deterministically_rejected` が緑)。
8. MitateDB の 3 plug の `query_page` が拒否を組み立てず、cursor を逐語で渡す。
9. `MitateDB-api/tests` 全体が緑。
10. 下の対応表に、変異も監査照合も持たない行が無い。

**本体の性質 (非空振り、strict は I だけ、`observed_branch` の突合位置、`budget` の運搬、details の 2 キー) の変異は、peer が初めて 1.9.0 の挙動を持つ WP-5 (r2db) と WP-4 (MitateDB) の完了条件で掛ける。** WP-2 の時点では両 peer が 1.8.0 を宣言し、本体の破れが xfail に吸われるため (§1.3)。

### 非空振り要件

設計 D-4 の「空振り禁止」の段落のとおり。plug ごとに: T は変種ごとに 2 ページ以上、I は挿入 2 件が実際に入ったこと、S は第 2 セッションが別 credential で認証を通ったこと、DP は `request_budget` を enabled と宣言する plug で `budget` の経路が走ったこと (items が b 件ちょうど)、B は並べ替えの観測で前後の `where` が 2 述語以上かつ並びが異なること (v1.2) を assert する。

### 確定文言の所在

C-28 の Status 欄の文は設計 §6.1。Condition 欄は WP-1 で置いた確定文を変えない。

### 同型性テストの対象

なし (adapter は同型性表の対象外)。

### 道具の引数

```
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_c28_keyset_paging.py conformance-tests/test_conditions_register.py -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not MitateDB" -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not r2db" -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- r2db-api/tests MitateDB-api/tests -q
./.venv/bin/python tools/dev/mutate.py "$SP/p11-wp2-mutations.json" -C $WT --wait 300
```

### 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (Class C)。

### 禁止事項

§1.6 に加えて: 既存の port メソッドの引数を増やさない (設計 D-4)。MitateDB の cell の実体に cursor の受理を入れない (WP-4)。adapter の中で cursor を解釈・生成しない。C-24 の開示と C-05 の経路に触れない (設計 §6.2)。

### 完了条件番号 → 変異

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | M2-1a: `r2db-api/conformance/conformance_adapter_r2db.py` の `query_page` を削る / M2-1b: `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` の `query_page` を削る | その plug の C-28 の node (adapter 生成の失敗) |
| 2 | M2-2: `CONDITIONS.md` の C-28 行の Status を `declared` に戻す | `test_every_marked_condition_id_maps_to_an_executable_status` |
| 3 | M2-3 (r / rh / rs の 3 entry): r2db の一時フリップだけ | I (その plug) |
| 4 | 監査照合: `pt.py -rxX` の log の short test summary と確定した表 | — |
| 5 | 監査照合: `pt.py` の集計行 | — |
| 6 | 監査照合: `CONFORMANCE_ADAPTER_V1.md` の差分 | — |
| 7 | M2-7: `MitateDB-api/src/mitatedb_api/cell.py` の cell の実体から cursor 拒否を外す (cursor を無視して読む)。加えて監査照合: `http.py` の grep で cursor の拒否 0 件 | `MitateDB-api/tests/test_http.py` の `test_page_cursor_is_deterministically_rejected` |
| 8 | 監査照合: 3 adapter の `query_page` の差分と、adapter 内の `CAPABILITY_UNSUPPORTED` の grep | — |
| 9 | 監査照合: `pt.py` の集計行 | — |
| 10 | 監査照合: 本表 | — |

M2-3 はフリップそのものが変異である。対照 (§1.3) は、確定した表で X の node を r2db の plug ごとに 1 つ選び、一時フリップだけで緑になることとする。

## 4. WP-5 — r2db の keyset (順序 3 番目)

**【訂正註 2026-09-25 (WP-2 コードレビュー 2 への監督裁定)】** C-28 の R node は「復号できるが順序値の個数か型が合わない cursor」を観測しない — cursor は契約上 opaque であり、conformance は改変 token を作れず、`order_by` を変える黒箱の脚は束縛違いの拒否と区別がつかない。個数・型検査の証拠は peer の単体テスト (改変 token を知ってよい層) に置く: WP-5 の完了条件 11 と変異 M5-11、WP-4 の完了条件 11 と変異 M4-11 の「赤になる test」は **R ではなく、その WP で置く peer の単体テスト** (r2db は `r2db-api/tests/test_foundation.py`、MitateDB は `MitateDB-api/tests/test_http.py` または cell の単体テスト) と読み替える。C-28 の Status に開示を置く。

### 目的

r2db の cursor を offset から keyset へ置き換え、束縛を `where` (述語の並びに依らない) + `order_by` に狭め、拒否の details と既定ページを 1.9.0 の形にする。宣言は 1.8.0 のまま。

### 依存・正本

- 依存: WP-2。
- 正本: 設計 D-3 の 1〜10 (4 は 4a・4b を含む。3 は v0.6 の束縛 hash の正規化を含む)、D-1 根拠 (2a)・(5)、D-6 (codec と束縛 helper)、§9 の WP-5 行、§10 の 14。

### 触ってよいパス

- `r2db-api/src/r2db_api/paging.py`、`postgres.py`、`postgres_sql.py`、`structured.py`、`inmemory_sort.py`、`service.py`、`request_shape.py`
- `r2db-api/tests/test_foundation.py`、`r2db-api/tests/test_http.py`、`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`

触らない: `capabilities_document.py` (宣言)、`r2db-api/conformance/`、`conformance-tests/`、`spec/`、`r2db-api/tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` は WP-6)。

### タスク

1. `paging.py`: `encode_page_cursor` / `decode_page_cursor` (設計 D-6。本体に comment を置かず、失敗は `ValueError`)。`_shape_hash` を、Application・entity・正規化した `where`・`order_by` の束縛 hash を作る両 peer 同名の helper `canonical_page_binding` に置き換える (`where` の正規化 = 各述語を (field, operator, 値の正規 JSON) の 3 つ組にして整列した list を `sort_keys=True` の JSON にする。helper には素の値を渡す。本体に comment を置かない。設計 D-3 の 3 (v0.6)、D-6)。`MAX_CURSOR_OFFSET` と offset の符号化を消す (D-3 の 1・6)。拒否の `field` を `page/cursor` に (D-3 の 7)。`validate_page_size` の details を `request_schema` / `page/size` に (D-3 の 8)。
2. `postgres_sql.py` / `postgres.py`: `OFFSET` を外し、辞書式の展開形の keyset 述語 (NULL 分岐込み、bind parameter のみ) と `LIMIT size+1` (D-3 の 4)。復号した値は `_check_type(value, field_type, "page/cursor")` で個数と型を検査し (4a)、`_bind_value` でバインドする (4b)。
3. `structured.py` / `inmemory_sort.py`: in-memory cell の keyset (D-3 の 5)。
4. 内部射影: 順序項と tie-break `id` を内部で選び、`items` は `select` の分だけ (D-3 の 10)。
5. 既定ページ: `service.py` の既定 100 を廃し、D-1 根拠 (2a) の最小値 (D-3 の 9)。
6. `request_shape.py`:22 の `field="cursor"` を `page/cursor` に (D-3 の 7)。
7. 既存テストの更新: 設計 D-3 の 8 と §9 の WP-5 行が挙げる箇所 (`test_foundation.py` の page size・束縛・facade identity、`test_http.py` の 1001 → 400、`test_l1_details_vocabulary_ast_scan.py` の `"paging.py"` の件数ピンは実測値へ。`OC` §1.5 の 40b)。`request_shape.py` の是正を固定するテストを `test_http.py` か `test_foundation.py` に置く。

### 期待結果表 (WP-5 の commit の時点。フリップ無し)

| node | r | rh | rs | m | mh | ms |
|---|---|---|---|---|---|---|
| T | X | X | X | x | x | x |
| I | **F** | **F** | **F** | x | x | x |
| B | X | X | X | x | x | x |
| A | X | X | X | x | x | x |
| R | X | X | X | x | x | x |
| S | X | X | X | x | x | x |
| D | X | X | X | x | x | x |
| DP | X | X | X | x | x | x |
| PS | X | X | X | x | x | x |

### 完了条件 (assert 水準)

1. `pt.py -rxX` の実測が上の表と一致する (r2db の F は 3 件、I だけ)。
2. r2db を一時フリップすると、r / rh / rs で 9 node がすべて緑 (WP-6 で r2db が緑になることの先取り)。
3. keyset 述語が tie-break `id` を最終項に持つ。
4. keyset 述語の NULL 分岐が asc → NULLS LAST / desc → NULLS FIRST の規則に合う。
5. 方向混在の `order_by` で述語の不等号が項ごとの方向に従う。
6. 先読み (`LIMIT size+1`) により、最終ページ以外で `next_page` が非 null。
7. in-memory cell の keyset が PostgreSQL cell と同じ行を返す。
8. 束縛に `select` と `page.size` を含まない (変えても cursor が有効)。
9. 束縛に `where` と `order_by` を含む (変えると拒否)。
9a. 束縛の `where` が述語の並びに依らない (同じ述語を並べ替えただけの要求で cursor が有効。設計 D-3 の 3 (v0.6))。
9b. 設計 §10 の 14 の `1` / `1.0` の束縛の実測 (r2db) が設計 §11 にある。
10. 束縛に Application と entity を含む (別 Application・別 entity の cursor を拒否)。
11. 復号した値の個数・型の検査 (`_check_type`) により、合わない cursor が 2 キーの拒否になる。
12. cursor の拒否の details が `violated_declaration: request_schema` と `field: page/cursor` の 2 キーちょうどである。
13. `request_shape.py` の string でない cursor の拒否の `field` が `page/cursor`。
14. `page.size` = 0 / 1001 が `VALIDATION_FAILED` / `request_schema` / `page/size`。
15. `page.size` 省略時の既定が D-1 根拠 (2a) の最小値。
16. `order_by` が `select` に無い field を名指しても走査が成り立ち、`items` の key 集合が `select` と一致する。
17. T の非空振り: 変種ごとに 2 ページ以上を観測する。
18. r2db の plug の `query_page` が `budget` を逐語で運ぶ。
19. I の版ゲートが `strict=True` である (strict でなければ F が消える)。
20. `observed_branch` の突合が `>= 1.9.0` の分岐にだけある (`< 1.9.0` にあれば F が消える。フェーズ9 作業指示書 訂正註 7)。
21. codec と `canonical_page_binding` の本体に comment が無く、`paging.py` に module 水準の可変状態が無い。
22. `MAX_CURSOR_OFFSET` と offset の符号化が消えている。
23. `r2db-api/tests` 全体が緑。
24. `conformance-tests` の部分集合 2 本 (§1.2) で failed は r2db の I の 3 件だけ、xpassed は表の X の数、xfailed は表の x の数。
25. 下の対応表に、変異も監査照合も持たない行が無い。

### 非空振り要件

完了条件 2 の対照が緑であること (§1.3)。T・I・S・DP の非空振りの assert (WP-2 の非空振り要件) が r / rh / rs で実際に通った件数を報告に書く。

### 確定文言の所在

拒否の details の 2 キーと `page/size` の 2 キーは設計 D-1 (5)、D-3 の 7・8。docstring に契約文を写すときは確定文ファイルから逐語 (§1.4)。

### 同型性テストの対象

`encode_page_cursor` / `decode_page_cursor` と `canonical_page_binding` (設計 D-6。helper は v1.2 で足した)。本体は WP-4 が MitateDB 側に同一で写す。**`_ISOMORPHIC_TARGETS` の行は WP-6 の監督の pair-closing で足す。本 WP は表に触れない。**

### 道具の引数

```
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- r2db-api/tests -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_c28_keyset_paging.py -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not MitateDB" -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not r2db" -q -rxX
./.venv/bin/python tools/dev/mutate.py "$SP/p11-wp5-mutations.json" -C $WT --wait 300
```

`-k "not MitateDB"` の部分集合は r2db の I が F なので終了コード 1 で終わる。判定は集計行と short test summary による。

### 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (Class B + 同型性の対象になる helper の新設)。

### 禁止事項

§1.6 に加えて: 宣言 `contract_version` を上げない。offset を併存させない (D-3 の 6)。cursor から復元した値を literal 合成しない。C-05 / C-24 の `result_items` / `budget` の拒否位置を変えない (D-3 の 8)。`test_l1_details_vocabulary_ast_scan.py` の件数ピンは実測値へ合わせるだけで済ませず、走査対象に入ったことを確かめる (`OC` §1.5 の 40b)。

### 完了条件番号 → 変異

変異の「+F」は §1.3 の r2db の一時フリップを同じ entry に含めることを示す。赤の plug は、PostgreSQL cell を通る plug と in-memory cell を通る plug を実測で特定して書く。

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | 監査照合: `pt.py -rxX` の log | — |
| 2 | M5-0 (対照、expect green): 一時フリップだけ | r / rh / rs の 9 node が緑 |
| 3 | M5-3 +F: `postgres_sql.py` の述語から tie-break の項を外す | T (PostgreSQL cell の plug) |
| 4 | M5-4 +F: NULL 分岐を素の `col > %s` にする | T の NULL 変種 |
| 5 | M5-5 +F: desc の項の不等号を asc と同じにする | T の方向混在変種 |
| 6 | M5-6 +F: `LIMIT size+1` を `LIMIT size` にする | T |
| 7 | M5-7 +F: in-memory cell の位置比較を「以上」にする | T または I (in-memory cell の plug) |
| 8 | M5-8 +F: `canonical_page_binding` の束縛に `select` を足す | B |
| 9 | M5-9 +F: `canonical_page_binding` の束縛から `order_by` を外す | B |
| 9a | M5-9a +F: `canonical_page_binding` の `where` の整列を外す (受け取った順で hash する) | B (並べ替えの観測で拒否) |
| 9b | 監査照合: `1` / `1.0` の実測 (設計 §11) | — |
| 10 | M5-10 +F: `canonical_page_binding` の束縛から entity を外す | A |
| 11 | M5-11 +F: 復号値の `_check_type` 検査を外す | R |
| 12 | M5-12 +F: `paging.py` の `field="page/cursor"` を `"cursor"` に戻す | R |
| 13 | M5-13: `request_shape.py`:22 を `field="cursor"` に戻す | タスク 7 で置いた r2db のテスト |
| 14 | M5-14 +F: `validate_page_size` の 1001 の拒否を `violation("budget", field="page_size")` に戻す | PS |
| 15 | M5-15 +F: `service.py` の既定を 100 に戻す | DP |
| 16 | M5-16 +F: 内部射影から順序項を外す | T の `select` 外変種 |
| 17 | M5-17 +F: T の seed の行数を 1 ページに収まる数にする (テスト側) | T (非空振りの assert) |
| 18 | M5-18 +F: `r2db-api/conformance/conformance_adapter_r2db.py` の `query_page` が `budget` を要求に載せない | DP (r) |
| 19 | M5-19 (フリップ無し、expect green): I の版ゲートを `strict=False` にする | I の F が消える (r / rh / rs) |
| 20 | M5-20 (フリップ無し、expect green): `observed_branch` の突合を `< 1.9.0` の分岐にも置く | I の F が消える |
| 21 | 監査照合: `paging.py` の該当 file:line (codec と `canonical_page_binding`) | — |
| 22 | 監査照合: grep 0 件 | — |
| 23 | 監査照合: `pt.py` の集計行 | — |
| 24 | 監査照合: `pt.py` の集計行と short test summary | — |
| 25 | 監査照合: 本表 | — |

## 5. WP-3 — MitateDB の内部行順序列 `_mdb_row` (順序 4 番目)

### 目的

MitateDB の全 collection table に client から見えない `_mdb_row` を足し (新規 provision・per-application upgrade・SQLite)、cell の `field_domains` 経路から除外する。read の挙動 (cursor) は WP-4。

### 依存・正本

- 依存: WP-2 (順序上は WP-5 の後)。
- 正本: 設計 D-2 の表 (列名・型・catalog・select・add_field・PostgreSQL migration・適用・SQLite backend・isolation・`row_addressability`)、§10 の 6・13、§11、§9 の WP-3 行。

### 触ってよいパス

- `MitateDB-api/src/mitatedb_api/backend_postgres.py`、`backend_sqlite.py`、`cell.py`、`platform_upgrades.py`
- `MitateDB-api/migrations/0015_row_order_column_upgrade.sql` (新規)、`MitateDB-api/migrations/0003_provision_application.sql` (seed list のみ)
- `MitateDB-api/README.md` (upgrade 節への開示)
- `MitateDB-api/tests/test_row_order_column.py` (新規。設計 §9 の「MitateDB 側の単体テスト」のファイル名)
- 設計 §11 (実測の記入のみ)

触らない: `http.py`、read の ORDER BY と述語 (WP-4)、`identifiers.py`、`MitateDB-api/conformance/`、`conformance-tests/`。

### タスク

1. `backend_postgres.py` の `create_collection` (設計 D-2 の「PostgreSQL migration」行が挙げる `CREATE TABLE` 経路) と `backend_sqlite.py` の `CREATE TABLE` に `_mdb_row` (型は設計 D-2 の表)。
2. `cell.py`: `self._backend.field_domains(...)` を包む private helper を 1 本置き、`_mdb_row` を除外し、cell 内の呼び出し 6 箇所をすべて通す (設計 D-2 の select 行。backend は触らない)。
3. migration `0015_row_order_column_upgrade.sql` (per-application UPGRADE。列挙元・冪等形は設計 D-2 の「適用」行)。`PLATFORM_UPGRADE_NUMBERS` に 15、`0003` の seed list に 15。
4. `MitateDB-api/README.md` の upgrade 節に、lock の保持がデータ量に比例すること (§10 の 13) と、移行後の既存行の tie-break 順が挿入順とは限らないこと (§10 の 6) を開示する。
5. 設計 §11 に、0015 の列挙元と `_mdb_field_types` の `DISTINCT entity` との一致の実測 (0 field の collection の有無を含む) を記す。
6. `test_row_order_column.py`: 両 backend で列の存在と型、helper の除外、0015 の冪等と列挙の除外、`_mdb_row` の宣言が識別子の構文で拒否されること (設計 D-2 の add_field 行) を固定する。

### 期待結果表 (WP-3 の commit の時点。フリップ無し)

WP-5 の表と同一である (WP-3 の変更では C-28 の結果が変わらない。MitateDB の cursor はまだ受理されない)。

| node | r | rh | rs | m | mh | ms |
|---|---|---|---|---|---|---|
| T | X | X | X | x | x | x |
| I | **F** | **F** | **F** | x | x | x |
| B | X | X | X | x | x | x |
| A | X | X | X | x | x | x |
| R | X | X | X | x | x | x |
| S | X | X | X | x | x | x |
| D | X | X | X | x | x | x |
| DP | X | X | X | x | x | x |
| PS | X | X | X | x | x | x |

### 完了条件 (assert 水準)

1. PostgreSQL backend で新規 collection に `_mdb_row` があり、`GENERATED ALWAYS AS IDENTITY` である。
2. SQLite backend で新規 collection に `_mdb_row` があり、`INTEGER PRIMARY KEY` である。
3. 両 backend で、宣言 field 全部を `select` した read の key 集合が宣言 field と一致し、`_mdb_row` を含まない。
4. cell 内の `self._backend.field_domains(` の呼び出しが helper の中の 1 箇所だけである。
5. 0015・`PLATFORM_UPGRADE_NUMBERS`・`0003` の seed list が一致する (`MitateDB-api/tests/test_platform_upgrade_ledger_scan.py::test_real_migrations_three_way_match` が緑)。
6. 0015 を同じ application DB に 2 回適用しても成功する (冪等)。
7. 0015 の適用後、`_mdb_` で始まる表と予約名 `audit_events` に `_mdb_row` が無く、宣言 collection にはある。
8. `_mdb_row` を field として宣言する要求が識別子の構文で拒否される。
9. README の開示 2 点がある。
10. 設計 §11 にタスク 5 の実測がある (0015 の列挙元と `DISTINCT entity` の一致)。
11. `pt.py -rxX` の実測が上の表と一致する。
12. `MitateDB-api/tests` 全体が緑。
13. 下の対応表に、変異も監査照合も持たない行が無い。

### 非空振り要件

完了条件 3・6・7 のテストは両 backend (6・7 は PostgreSQL) で、宣言 collection 1 件以上と `_mdb_` の表 1 件以上を実際に観測したことを assert する。

### 確定文言の所在

なし (契約文を写さない)。

### 同型性テストの対象

なし。

### 道具の引数

```
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- MitateDB-api/tests/test_row_order_column.py MitateDB-api/tests/test_platform_upgrade_ledger_scan.py -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- MitateDB-api/tests -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not MitateDB" -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not r2db" -q -rxX
./.venv/bin/python tools/dev/mutate.py "$SP/p11-wp3-mutations.json" -C $WT --wait 300
```

### 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (Class B)。

### 禁止事項

§1.6 に加えて: `field_domains` の backend 実装を変えない。`add_field` に追加の拒否経路を書かない (設計 D-2 の add_field 行)。SQLite に `AUTOINCREMENT` を使わない (§10 の 6)。`row_addressability` を変えない。既存の migration を書き換えない (`0003` の seed list を除く)。既存テストが migration の集合や最終番号を固定していて赤になったら、直さずに監督へ上げる。

### 完了条件番号 → 変異

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | M3-1: `backend_postgres.py` の `CREATE TABLE` から `_mdb_row` を外す | `test_row_order_column.py` の PostgreSQL の列テスト |
| 2 | M3-2: `backend_sqlite.py` の `CREATE TABLE` から `_mdb_row` を外す | `test_row_order_column.py` の SQLite の列テスト |
| 3 | M3-3: helper が除外せずに返す | `test_row_order_column.py` の key 集合テスト (両 backend) |
| 4 | 監査照合: grep の件数と helper の file:line | — |
| 5 | M3-5: `PLATFORM_UPGRADE_NUMBERS` から 15 を外す | `test_real_migrations_three_way_match` |
| 6 | M3-6: 0015 の `IF NOT EXISTS` を外す | `test_row_order_column.py` の冪等テスト |
| 7 | M3-7: 0015 の列挙から `_mdb_` の除外を外す | `test_row_order_column.py` の列挙テスト |
| 8 | M3-8: `identifiers.py` の識別子の正規表現の先頭を `[a-z_]` にする | `test_row_order_column.py` の宣言拒否テスト |
| 9 | 監査照合: README の差分 | — |
| 10 | 監査照合: 設計 §11 の記入 | — |
| 11 | 監査照合: `pt.py -rxX` の log | — |
| 12 | 監査照合: `pt.py` の集計行 | — |
| 13 | 監査照合: 本表 | — |

## 6. WP-4 — MitateDB の keyset read と cursor (順序 5 番目)

### 目的

MitateDB で `page.cursor` を受理し、`_mdb_row` を tie-break とする keyset read と `next_page` を両 backend で実装する。NULL の位置を両 backend で揃え、read 入口の検査と既定ページを 1.9.0 の形にする。宣言は 1.8.0 のまま。

### 依存・正本

- 依存: WP-3 と WP-5 (codec の本体を WP-5 から写す)。
- 正本: 設計 D-2 の既定順序・応答の行、D-2a、D-2b の 1〜5 (5 は v0.6 の束縛)、D-6、§10 の 1・11・14、§9 の WP-4 行。

### 触ってよいパス

- `MitateDB-api/src/mitatedb_api/paging.py` (新規)、`http.py`、`cell.py`、`backend_postgres.py`、`backend_sqlite.py`
- `MitateDB-api/conformance/conformance_adapter_mitatedb.py`、`conformance_adapter_mitatedb_http.py`、`conformance_adapter_mitatedb_socket.py` (変更が要るときだけ。入口へ cursor を渡す形は WP-2 で済んでいる)
- `MitateDB-api/tests/test_http.py`、`MitateDB-api/tests/test_l1_details_vocabulary_ast_scan.py`

触らない: `capabilities_document.py` (宣言)、`conformance-tests/`、`spec/`、`r2db-api/`、`MitateDB-api/tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS` は WP-6)。

### タスク

1. `paging.py`: `encode_page_cursor` / `decode_page_cursor` と束縛 helper `canonical_page_binding` (v1.2) の本体を WP-5 の r2db の本体と**同一**にする (docstring だけ peer ごと。本体に comment を置かない。設計 D-6 (b))。
2. `backend_*.read`: ORDER BY の末尾に `_mdb_row ASC`、両 backend に `NULLS` 句を明示し (D-2a)、keyset 述語 (D-3 の 4 と同じ辞書式の展開形と NULL 分岐) を組む。順序項と `_mdb_row` を内部射影に加え、応答の直前に落とす (D-2 の応答行)。
3. `cell.py`: WP-2 が置いた cell の実体を差し替え、cursor を受理して `(rows, next_page)` を返す (runtime の入口 → cell の実体の形は変えない)。既存の `read` はそれに委ねて rows だけを返す (D-2b の 4)。復号値の個数・型を `where` の値と同じ経路で検査し、`check_declared_value` / `encode_value` の `ValidationError` を 2 キー (`request_schema` / `page/cursor`) に写し替える (D-2b の 1)。`ApplicationCell.read` の `limit` 受理の直後、配備 bound の検査より先に `page.size` の 1..1000 を検査する (D-2b の 2)。既定ページ (D-2b の 3)。束縛 hash は `canonical_page_binding` で (Application, entity, 正規化した `where`, `order_by`) から作り、helper には `Filter` 等の peer 固有の型を渡さず素の値に変換して渡す (D-2b の 5。v1.2)。
4. `http.py`: 入口が返す `next_page` を応答に返す (cursor の拒否は WP-2 で cell の実体へ移してあり、本 WP の実体の差し替えで消える)。
5. `test_http.py` の `CAPABILITY_UNSUPPORTED` のピン (設計 §9 の WP-4 行の箇所) を更新する。新しい `paging.py` か呼び出し側に denial を置くなら、`test_l1_details_vocabulary_ast_scan.py` の guard に計上する (理由付き除外集合の変更は監督裁定。`OC` §1.5 の 40b)。
6. SQLite の `NULLS FIRST` / `NULLS LAST` の対応 (3.30 以降) を、CI の Python 3.11 / 3.12 の両 job の `sqlite3.sqlite_version` で確かめてから書く (D-2a の実測の段落)。確かめる手段が手元に無ければ、監督へ上げる。

### 期待結果表 (WP-4 の commit の時点。フリップ無し)

| node | r | rh | rs | m | mh | ms |
|---|---|---|---|---|---|---|
| T | X | X | X | X | X | X |
| I | **F** | **F** | **F** | **F** | **F** | **F** |
| B | X | X | X | X | X | X |
| A | X | X | X | X | X | X |
| R | X | X | X | X | X | X |
| S | X | X | X | X | X | X |
| D | X | X | X | X | X | X |
| DP | X | X | X | X | X | X |
| PS | X | X | X | X | X | X |

### 完了条件 (assert 水準)

1. `pt.py -rxX` の実測が上の表と一致する (F は I の 6 件だけ)。
2. MitateDB を一時フリップすると、m / mh / ms で 9 node がすべて緑。
3. PostgreSQL backend の keyset が `_mdb_row` を最終項に持つ。
4. SQLite backend の keyset が `_mdb_row` を最終項に持つ。
5. SQLite backend の ORDER BY が NULL を asc → 末尾 / desc → 先頭に置く (PostgreSQL 既定と同じ)。
6. 方向混在の `order_by` で述語の不等号が項ごとの方向に従う。
7. 先読みにより、最終ページ以外で `next_page` が非 null。
8. 束縛に `select` と `page.size` を含まない。
9. 束縛に `where` と `order_by` を含む。
9a. 束縛の `where` が述語の並びに依らない (同じ述語を並べ替えただけの要求で cursor が有効。設計 D-2b の 5)。
9b. 設計 §10 の 14 の `1` / `1.0` の束縛の実測 (MitateDB) が設計 §11 にある。
10. 束縛に Application と entity を含む。
11. 復号値の検査と `ValidationError` の写し替えにより、合わない cursor の拒否が 2 キーちょうどになる。
12. `page.size` = 0 / 1001 が `ApplicationCell.read` で `request_schema` / `page/size` になる (in-process の plug を含む)。
13. `page.size` 省略時の既定が D-1 根拠 (2a) の最小値で、先読みで `next_page` を返す。
14. `_mdb_row` と `select` に無い順序項が応答に出ない。
15. HTTP の経路が新しいメソッドの `next_page` を返す (mh / ms)。
16. MitateDB の plug の `query_page` が `budget` を逐語で運ぶ。
17. T の非空振り (変種ごとに 2 ページ以上) が m / mh / ms で通る。
18. codec と `canonical_page_binding` の本体が r2db と同一 (docstring を除く)、本体に comment が無く、`paging.py` に module 水準の可変状態が無い。
19. CI の 2 job の sqlite の版が 3.30 以上である (タスク 6 の実測)。
20. `MitateDB-api/tests` 全体が緑。
21. `conformance-tests` の部分集合 2 本 (§1.2) で failed は I の 6 件だけ、xpassed は表の X の数、xfailed は 0。
22. 下の対応表に、変異も監査照合も持たない行が無い。

### 非空振り要件

完了条件 2 の対照が緑であること (§1.3)。T・I・S・DP の非空振りの assert が m / mh / ms で実際に通った件数を報告に書く。m は SQLite、mh / ms は PostgreSQL を通る (設計 D-2 の SQLite backend 行) ので、両 backend が実際に駆動されたことを plug 名で示す。

### 確定文言の所在

拒否の 2 キーは設計 D-1 (5)、D-2b の 1・2。docstring に契約文を写すときは確定文ファイルから逐語 (§1.4)。

### 同型性テストの対象

`encode_page_cursor` / `decode_page_cursor` と `canonical_page_binding` (v1.2)。本体の同一性は WP-6 で `_ISOMORPHIC_TARGETS` に登録して固定する。本 WP では表に触れない。

### 道具の引数

```
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- MitateDB-api/tests -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_c28_keyset_paging.py -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not MitateDB" -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not r2db" -q -rxX
./.venv/bin/python tools/dev/mutate.py "$SP/p11-wp4-mutations.json" -C $WT --wait 300
```

部分集合 2 本はどちらも I が F なので終了コード 1 で終わる。判定は集計行と short test summary による。

### 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (Class B + 同型性の対象になる helper の新設)。

### 禁止事項

§1.6 に加えて: 宣言 `contract_version` を上げない。`http.py` に `page.size` の検査を置かない (D-2b の 2)。`_check_object_shape` を触らない。既存の `read` の呼び出し側 (`select_eq` ほか) の signature を変えない。codec を r2db と別の形にしない。

### 完了条件番号 → 変異

「+F」は §1.3 の MitateDB の一時フリップを同じ entry に含めることを示す。

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | 監査照合: `pt.py -rxX` の log | — |
| 2 | M4-0 (対照、expect green): 一時フリップだけ | m / mh / ms の 9 node が緑 |
| 3 | M4-3 +F: `backend_postgres.py` の順序と述語から `_mdb_row` を外す | T (mh / ms) |
| 4 | M4-4 +F: `backend_sqlite.py` の順序と述語から `_mdb_row` を外す | T (m) |
| 5 | M4-5 +F: `backend_sqlite.py` の ORDER BY の `NULLS` 句を外す | T の NULL 変種 (m) |
| 6 | M4-6 +F: desc の項の不等号を asc と同じにする | T の方向混在変種 |
| 7 | M4-7 +F: 先読みを外す (`limit` 件だけ読む) | T |
| 8 | M4-8 +F: 束縛に `select` を足す | B |
| 9 | M4-9 +F: 束縛から `order_by` を外す | B |
| 9a | M4-9a +F: MitateDB の `canonical_page_binding` の `where` の整列を外す (受け取った順で hash する) | B (並べ替えの観測で拒否。m / mh / ms) |
| 9b | 監査照合: `1` / `1.0` の実測 (設計 §11) | — |
| 10 | M4-10 +F: 束縛から entity を外す | A |
| 11 | M4-11 +F: `ValidationError` の写し替えを外す | R |
| 12 | M4-12 +F: `ApplicationCell.read` の 1..1000 の検査を外す | PS (m) |
| 13 | M4-13 +F: `limit=None` を配備上限で黙って切り詰める現行の形に戻す | DP |
| 14 | M4-14 +F: 応答の直前で `_mdb_row` を落とさない | T の key 集合 |
| 15 | M4-15 +F: `http.py` が `next_page` に `None` を返す | T (mh / ms) |
| 16 | M4-16 +F: `conformance_adapter_mitatedb.py` の `query_page` が `budget` を運ばない | DP (m) |
| 17 | M4-17 +F: T の seed の行数を 1 ページに収まる数にする (テスト側) | T (非空振りの assert) |
| 18 | 監査照合: 正規化 diff (r2db の本体との比較) と `paging.py` の file:line。本体の同一性の変異は WP-6 の M6-4 / M6-4b | — |
| 19 | 監査照合: CI の 2 job の実測値 | — |
| 20 | 監査照合: `pt.py` の集計行 | — |
| 21 | 監査照合: `pt.py` の集計行と short test summary | — |
| 22 | 監査照合: 本表 | — |

## 7. WP-6 — 版フリップと記録 (順序 6 番目)

### 目的

両 peer の宣言 `contract_version` (data 側と control 側) を実挙動と同一コミットで 1.9.0 にし、C-28 の 9 node を 6 plug で緑にする。codec と束縛 helper を同型性表に登録し、`CONTROL_MAPPING` 3.2 と台帳を更新する。本 WP も main には載せない (§1.1)。

**Q-4 のゲート**: 本 WP の commit は統合 branch に積むだけである。契約版に触れる main へのコミットは §1.1 の 4 の merge 1 回であり、**Q-4 の依頼者確認 (設計 §5.1。完了ゲートの集計行と `git diff --stat` を添える — 依頼者裁定 2026-09-24、§1.1 の 4) は監督がその merge の前に取る。確認が得られるまで merge しない。**

### 依存・正本

- 依存: WP-4 と WP-5。
- 正本: 設計 D-1 (版フリップは実挙動と同一コミット、§2.3)、D-5 の表、D-6 と D-6 (a) (v0.6 で 3 行)、§6.1、§7 の `CONTROL_MAPPING` 3.2 の案、§9 の WP-6 行、§10 の 8。

### 触ってよいパス

- `r2db-api/src/r2db_api/capabilities_document.py`、`MitateDB-api/src/mitatedb_api/capabilities_document.py`
- `r2db-api/src/r2db_api/control_plane.py`、`MitateDB-api/src/mitatedb_api/control_plane.py` (control 側宣言の `contract_version` のみ)
- `r2db-api/tests/test_audit_query.py`、`MitateDB-api/tests/test_audit_query.py`
- 1.8.0 を pin する既存テスト (宣言値の追随のみ): `r2db-api/tests/test_foundation.py` (:244 ほか)、`r2db-api/tests/test_control_plane_service.py` (:1808)、`MitateDB-api/tests/test_http.py` (:382)、`MitateDB-api/tests/test_control_plane_service.py` (:574)、`r2db-api/tests/test_denial_details_and_request_id.py` (:499)、`MitateDB-api/tests/test_denial_details_and_request_id.py` (:522, :536)
- `security/CONTROL_MAPPING.md`、`conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md` (`## C-28` 節の追随のみ)
- `RM`

触らない: `spec/`、両 peer の他の `src/`、`conformance-tests/` の test ファイル。

### タスク

1. 両 peer の `capabilities_document.py` の `contract_version` を 1.9.0 に (両 peer 同一コミット)。control 側宣言 (`r2db-api/src/r2db_api/control_plane.py`:633、`MitateDB-api/src/mitatedb_api/control_plane.py`:1595) も同じコミットで 1.9.0 にする (C-19 が data 側と control 側の一致を assert する。`conformance-tests/test_c19_client_self_sufficiency.py`:258)。1.8.0 を pin する既存テストを同じコミットで追随させる。
2. `_ISOMORPHIC_TARGETS` (両 peer) に codec の 2 行と束縛 helper `canonical_page_binding` の 1 行 (計 3 行。設計 D-6 (v0.6)) を足し、件数ピン test を `..._159_rows` に改名する (数字は表の行数を実測して確定する。現行 156 + 3 の見込み)。表の当該行・test 名・pin 本体の表の逐語コピー・docstring の列を両 peer 同一コミットで改める (設計 D-6 (a))。
3. `CONTROL_MAPPING.md` を 3.1 → 3.2。SI-01 / SI-03 / SI-08 / SI-10 の主張を設計 §7 の案から、確定した node 名で書く (形式 3.0。Control の path は backtick で囲む。長さは register test で測る)。
4. `CONDITIONS.md` の C-28 行: Status 本文を設計 §6.1 の Status 欄で確定する (node 名・駆動条件・非空振りの根拠・開示)。Condition 欄は確定文ファイルのまま。`CONDITIONS_HISTORY.md` の `## C-28` を最終状態に追随させる。
5. `RM`: 下の「記録の一覧」のうち `RM` の行と、版上げ・版数ログの回転 (`OC` §1.16 の 78)。

### 記録の一覧 (変更セット全体。書く WP を併記)

| 記録 | 内容の出所 | 書く WP |
|---|---|---|
| `RM` §0.1.1 の G-2 / G-3 行 | 契約の現行版 1.9.0、全条件 C-00〜C-28 の 29 件。§0.1.3 の充足状況を実測に (設計 D-5) | WP-6 |
| `RM` §8 の R-106 行 | WP-1 で起票、WP-6 で完了の【追記】(完了条件・変異・集計行。WP-7 の数値は merge 前に足す) | WP-1 / WP-6 |
| `RM` §8 の R-107 行 | 設計 §9 の「WP-1 の材料 — R-107 の台帳行」の案文 (実施はしない) | WP-1 |
| `security/CONTROL_MAPPING.md` 3.1 → 3.2 | 設計 §7 | WP-6 |
| `conformance-tests/CONDITIONS.md` の C-28 行 | Condition = 確定文ファイル、Status・Evidence = 設計 §6.1 | WP-1 (`declared`) / WP-2 (`executable`) / WP-6 (本文の確定) |
| `conformance-tests/CONDITIONS_HISTORY.md` の `## C-28` | 設計 D-5 | WP-1 / WP-6 |
| `spec/CCR_DISPOSITION.md` 従属判断 14 | 設計 D-5 (義務 7 件、Q-1 / Q-2 の裁定) | WP-1 |
| `spec/CONTRACT_HISTORY.md` の Revision note 3 本 | 設計 D-5 の行 (1.9.0 の追加、`Page.size` 範囲外の拒否と既定ページ、`Page.cursor`)。3 本とも既存の `## versioning.version_binding` 節 | WP-1 |

WP-1 が書いた `spec/` の記録は WP-6 では変えない。node 名の確定などで追随が要ると分かったら、実装前に監督へ上げる。

### 期待結果表 (WP-6 の commit の時点)

9 node × 6 plug がすべて **ok**。xfailed = 0、xpassed = 0。

### 完了条件 (assert 水準)

1. r2db の宣言が 1.9.0 で、r / rh / rs の 9 node が緑。
2. MitateDB の宣言が 1.9.0 で、m / mh / ms の 9 node が緑。
3. 両 peer の control 側宣言も 1.9.0 で、C-19 が緑 (`conformance-tests/test_c19_client_self_sufficiency.py` の `test_c19_surfaces_present_and_consistent_across_both_documents` が 6 plug で緑)。
4. codec の 2 行と `canonical_page_binding` の 1 行 (計 3 行) が両 peer の `_ISOMORPHIC_TARGETS` にあり、同型性テストが緑。
5. 件数ピン test が `..._159_rows` (実測で確定した数字) で、表の行・pin 本体の逐語コピー・docstring が両 peer で揃っている。
6. `CONTROL_MAPPING.md` が 3.2 で、C-28 の主張のテスト名が解決する (`conformance-tests/test_control_mapping_register.py` が緑)。
7. `CONDITIONS.md` の C-28 行の Condition 欄が確定文ファイルと逐語で一致し、Status 本文が設計 §6.1 を満たし、`conformance-tests/test_conditions_register.py` が緑。
8. `RM` の記録 (上の一覧の WP-6 の行) があり、版上げと版数ログの回転が済み、`check_doc_refs` が dangling 0。
9. 両 peer の `src/` に宣言 1.8.0 が残っていない (data 側と control 側)。
10. `conformance-tests` の部分集合 2 本 (§1.2) で failed / xfailed / xpassed / skipped = 0。
11. 両 peer の suite が緑 (1.8.0 を pin していた既存テストを含む)。
12. 下の対応表に、変異も監査照合も持たない行が無い。

### 非空振り要件

完了条件 1・2 の緑が、`observed_branch` の突合を含む `>= 1.9.0` の分岐で得られたことを、6 plug の node 数 (9 × 6 と T の変種分) で報告する。

### 確定文言の所在

C-28 の Condition 欄は確定文ファイル。`CONTROL_MAPPING` の主張は設計 §7 の案を実測後に確定したもの。

### 同型性テストの対象

`encode_page_cursor` / `decode_page_cursor` / `canonical_page_binding` の 3 行 (両 peer の `tests/test_audit_query.py`)。**行の追加は監督の pair-closing** (設計 D-6)。集合の増加は Class D (`RM` §9 の 8)。

### 道具の引数

```
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- r2db-api/tests/test_audit_query.py MitateDB-api/tests/test_audit_query.py -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests/test_c19_client_self_sufficiency.py -q
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not MitateDB" -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- conformance-tests -k "not r2db" -q -rxX
./.venv/bin/python tools/dev/pt.py -C $WT --wait 300 -- r2db-api/tests MitateDB-api/tests -q
(cd "$WT" && python3 tools/check_doc_refs.py)
./.venv/bin/python tools/dev/mutate.py "$SP/p11-wp6-mutations.json" -C $WT --wait 300
```

### 使用テンプレート

実装 = テンプレ 2 (宣言・記録)、`_ISOMORPHIC_TARGETS` の行は監督。コードレビュー = テンプレ 5 (Class D)。

### 禁止事項

§1.6 に加えて: 片 peer だけフリップした状態を commit しない。`spec/` を変えない。R-107 を実施しない。`CONTROL_MAPPING` に実測前の主張を書かない。

### 完了条件番号 → 変異

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 1 | M6-1 (r / rh / rs の 3 entry): `r2db-api/src/r2db_api/capabilities_document.py` の宣言を 1.8.0 に戻す | I (XPASS(strict) → FAILED) |
| 2 | M6-2 (m / mh / ms の 3 entry): `MitateDB-api/src/mitatedb_api/capabilities_document.py` の宣言を 1.8.0 に戻す | I (XPASS(strict) → FAILED) |
| 3 | M6-3a: `r2db-api/src/r2db_api/control_plane.py` の control 側宣言を 1.8.0 に戻す / M6-3b: `MitateDB-api/src/mitatedb_api/control_plane.py` の control 側宣言を 1.8.0 に戻す (plug ごとに entry を分ける。§1.3) | `test_c19_surfaces_present_and_consistent_across_both_documents` (その peer の plug) |
| 4 | M6-4: `MitateDB-api/src/mitatedb_api/paging.py` の `decode_page_cursor` の本体の 1 token を変える / M6-4b: 同じ file の `canonical_page_binding` の本体の 1 token を変える (entry を分ける) | `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` |
| 5 | M6-5: `r2db-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` から codec の 1 行を外す | `test_isomorphic_target_table_is_pinned_to_its_current_159_rows` (r2db。数字は完了条件 5 で確定したもの) |
| 6 | M6-6: `CONTROL_MAPPING.md` の SI-10 の Evidence 主張の node 名を存在しない名前にする | `conformance-tests/test_control_mapping_register.py` の名前解決テスト |
| 7 | 監査照合: C-28 行の Condition 欄と確定文ファイルの diff (0 行) と register の集計行 | — |
| 8 | 監査照合: `RM` の差分と `check_doc_refs` の出力行 | — |
| 9 | 監査照合: grep 0 件 (data 側と control 側) | — |
| 10 | 監査照合: `pt.py` の集計行 | — |
| 11 | 監査照合: `pt.py` の集計行 | — |
| 12 | 監査照合: 本表 | — |

## 8. WP-7 — 性能の証拠 (順序 7 番目) と merge

### 目的

設計 D-7 の性能の証拠を取り、設計 §11 に記す。その後に §1.1 の 4 の手順で main へ 1 回 merge する。

### 依存・正本

- 依存: WP-6。
- 正本: 設計 D-7、§11、`RM` §0.1.4 の閾値。

### 触ってよいパス

設計 §11 のみ (道具を増やさない。`tools/perf_baseline.py` の操作集合を増やさない)。深いページの比較の script は `$SP` に置き、commit しない。

### タスク

1. `./.venv/bin/python tools/perf_baseline.py --warmup 20 --n 200` を K=1 で取り、直近の基準値との差分を設計 §11 に表で記す。完了ゲートと同時に走らせない (排他は道具が行う)。
2. 深いページの前後比較を 1 回: r2db の PostgreSQL の plug で N 行の entity の末尾ページを、(a) 変更前の offset 方式 (基点 `0fee6e5` の tree)、(b) 変更後の keyset 方式で読み、行数と p50 を設計 §11 に記す。設計 D-1 根拠 (3) から移した内容 (設計 D-7 の 2) は、この計測の記録としてだけ置く。

### 完了条件 (assert 水準)

1. K=1 の p50 が同一 plug・同一 op の直近の基準値の +40% 以内 (`RM` §0.1.4 の 1)、`backend_calls` の増加に理由がある (同 4)。
2. 深いページの (a) / (b) の行数と p50 が設計 §11 にある。
3. `tools/` の差分が 0。
4. 完了ゲート (監督、§1.1 の 4 の (3)) の judge が PASS で、failed / skipped / xfailed / xpassed / deselected = 0、残骸差分 0。
5. 下の対応表に、変異も監査照合も持たない行が無い。

### 非空振り要件

(b) の計測で、末尾ページに実際に到達したこと (返った行が末尾の行であること) を script の出力で示す。

### 確定文言の所在・同型性テストの対象

なし。

### 道具の引数

```
./.venv/bin/python tools/perf_baseline.py --warmup 20 --n 200
./.venv/bin/python tools/dev/gate.py -C $WT --label p11   # 監督のみ
```

### 使用テンプレート

計測は実装担当 (テンプレ 2)。受け入れ監査 (テンプレ 6) は完了ゲートの後に 1 回、全 WP を対象に。

### 禁止事項

§1.6 に加えて: 性能の数値を契約・`CONDITIONS.md`・`CONTROL_MAPPING` に書かない (設計 D-7 の 4)。計測用の op を harness に足さない。

### 完了条件番号 → 変異

| 完了条件 | 変異 | 赤になる test |
|---|---|---|
| 1 | 監査照合: `PERFRUN` 行と PERF 表 (設計 §11) | — |
| 2 | 監査照合: script の出力 (設計 §11) | — |
| 3 | 監査照合: `git diff --stat` の `tools/` 0 行 | — |
| 4 | 監査照合: `gate.py` の集計行と judge 行 | — |
| 5 | 監査照合: 本表 | — |

## 9. 訂正註

(実施中に本書の誤り・発注後の監督裁定・番号の振り直しが生じたらここへ追記する。本文は書き換えない。`OC` §1.8 の 57。)

- **2026-09-25 — 番号の振り直し (main `b283f48` の取り込み)**: 並走した最低共通機能プロファイル (R-29) が main (`b283f48`) へ先に merge し、本件が仮に使っていた番号を消費した。本件の番号を次のとおり振り直す (写像は監督確定)。本文は書き換えず、本文中の仮番号はこの写像で読み替える。
  - 契約 1.9.0 (paging の文言・義務・`version_binding` の段落・Revision note・pin) → **1.10.0**。main の 1.9.0 (`common_baseline` と `operation_catalog`) はそのまま残る。遡及拒否の旧い列挙と 1.9.0 段落の末尾文は main の文面のまま触らない (main の Revision note 3 の方針。監督裁定 2026-09-25)。1.10.0 段落は自身の末尾の遡及文だけを持つ。`spec/CONTRACT_HISTORY.md` の本件の Revision note 3/4/5 は 4/5/6 に繰り下がる (main の note 3 が先)。
  - C-28 (keyset) → **C-30**。main の C-28 は baseline turn、C-29 は operation catalog。conformance の試験ファイルは `conformance-tests/test_c30_keyset_paging.py` に改名する。
  - R-106 (keyset 本体) → **R-109**。main の R-106 は MitateDB `row_addressability`、R-107 は `revision_preconditions`、R-108 は参照クライアント。
  - R-107 (`order_by` 未知 field の拒否コード不一致) → **R-110**。
  - 従属判断 14 (keyset。依頼者裁定 Q-1/Q-2/Q-3/Q-5) → **従属判断 15**。main の従属判断 14 は `common_baseline`。
  - port v1.16 (`query_page`) → **v1.18**。main の v1.16 は `attempt_filter_with_result`、v1.17 は `operation_catalog_document`。
  - 不変: migration 0015、`_ISOMORPHIC_TARGETS` の件数 156→159。

- **2026-09-25 — 受け入れ監査の裁定 (WP-4 完了条件 19)**: CI の 2 job (`actions/setup-python@v5` の 3.11/3.12) の sqlite 版は push 停止中のため実測できない。監督裁定により、完了条件は監査照合ではなく実行可能な pin テスト `MitateDB-api/tests/test_sqlite_version_floor.py::test_sqlite_version_meets_the_nulls_first_last_floor` (sqlite >= 3.30) への置き換えとする。手元 `.venv` (sqlite 3.53.4) では緑。CI runner での実測は push 再開後の課題として未決のまま残す。
- **2026-09-25 — 受け入れ監査の裁定 (WP-4 完了条件 21)**: WP-4 の commit `cb64217` 時点では `test_c28_page_size_outside_schema_is_refused_at_page_size[r2db-api-http]` が "not MitateDB" の部分集合で赤 (httpx `AsyncClient` の closed-client `RuntimeError`) だった。原因は r2db-http adapter の孤立化 copy が親の共有 control client を閉じる欠陥であり、main `f522610` の修正を取り込む merge commit `285cfe4` の時点で解消済み (以後の再実測で非発現)。
- **2026-09-25 — 受け入れ監査の裁定 (WP-6 完了条件 10)**: `test_c27_same_digest_executes_once[MitateDB-api-http]` の断続的な flake (R-111、規模 M) を抱えたまま、完了ゲート (全体実行) は緑で通す。R-111 の頻度の追記は台帳側 (§8) にある。

## 10. 実施記録

(統合時に監督が記す。WP ごとの commit、`pt.py` / `mutate.py` の集計行、確定した期待結果表、完了ゲートの集計行、Q-4 の確認の逐語。)

**受け入れ監査 (2026-09-25、全 WP)**: `$SP/acceptance-packet.md` により WP-1〜WP-7 の完了条件 106 件 (9a・9b 込み) を判定 -- 充足 100・未充足 5 (WP-3 の完了条件 4・9・11 は設計 §11 への監査照合の記録欠落のみで実体は充足、本追記で解消; WP-4 の完了条件 21 は commit 時点の状態を指し main `f522610` の取り込みで解消済み; WP-6 の完了条件 10 は R-111 (flake) を抱えたまま)・証拠不足 1 (WP-4 の完了条件 19、CI の sqlite 版は pin テストへ置換、CI runner の実測は push 再開後)。監査担当の変異 36 件中 35 件が期待どおり、観察 1 (AU-4、`_mdb_row` の cursor 型検査が SQLite plug で固定されていない) は本追記の新テストで赤化し解消した。監査担当が単独実行した完了ゲートの集計行: `gate: 4167 passed, 2 subtests passed in 327.83s (0:05:27)`、`judge=PASS`、pg_database/pg_roles diff 0。本追記 (このドキュメント群の記述訂正 + 新テスト 1 本) を含めた最終の完了ゲートの集計行: `gate: `gate: 4168 passed, 2 subtests passed in 327.60s (0:05:27)`、judge=PASS、pg_database/pg_roles diff 0、label p11b (最終ツリー。SQLite の改変 cursor テスト追加前の ff6ad67 では label p11 `4167 passed in 327.83s`、judge=PASS)`(監督が最終ゲート後に埋める)。
