# 作業指示書 — R-60 + R-61 `security/CONTROL_MAPPING.md` の 2 つの主張の訂正 (版 2.14)

## 0. 版数・位置づけ

- **v1.0 (2026-09-20)。** 基点 main `3965fe4`。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-60** と **R-61** の 2 行 (同じ変更セットにまとめる — R-61 の行が自らそう述べている)。
- **変更クラスは D** (`security/` 配下を触る。`docs/design/ROADMAP_POST_PHASE7_V1.md` §9 の 8 の表、`tools/change_class.py` で実測する)。**契約は 1.8.0 のまま**で `spec/` を触らない。`conformance-tests/`・製品コード・migration・runbook の差分は **0** (例外は §1.6 の完了条件 8 を見よ)。
- **D が求める依頼者裁定の逐語記録**は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) であり、本件の決定はその委任の下で**監督が推奨として下した**。完了後に引き継ぎ書で**事後報告**する (R-57・R-59 と同じ扱い)。版付きの security-contract 決定に当たるのは `security/CONTROL_MAPPING.md` の**版 2.14** である。
- **設計文書は新しく起こさない。** 枠 (D-1〜D-6 と却下案) は §1.1 にあり、これが監督の確定した決定である。方法の正本は `security/CONTROL_MAPPING.md` 冒頭の **Update convention** (現行行を書き換え、旧文は逐語で履歴へ) と `security/CONTROL_MAPPING_HISTORY.md` 冒頭 (見出しは SI の ID のみ。題を足すとアンカーが壊れる)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`gate.py`・`finalize.py` は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。
- **WP は 1 本だけで並行は無い** ので、触るファイルの重なりの表は置かない (§1.2 の 16・17 は該当しない)。

## 1. WP-1 — 2 つの Control の主張を訂正し、版を 2.14 に上げる

**目的**: 正本順位 5 の文書に残る (a) 一意でない block の指し方 (R-60) と (b) 失効した作業期の本番制限 (R-61) を、現物と現在の条件に合わせる。

### 1.1 枠 (監督確定)

- **D-1 (R-60)** `SI-09 / MitateDB-api / platform upgrade / Control` の `0014_role_connection_limits_rollout.sql` の主張が持つ `SI-08's own MitateDB-api block` という指し方を、**ファイル自身の語彙**で一意にする (冒頭 `Blocks per subsection` 段の :51〜:75 の書き方 = `` `SI-08`'s `MitateDB-api` `default block` ``)。引き上げた ceiling を述べているのは SI-08 の**既定の小ブロック**である (:620 の `0014_role_connection_limits_rollout.sql` の主張)。`### MitateDB-api -- ops inventory` (:640〜) は その ceiling に対する算術と検出を述べる側であり、指す先ではない。
- **D-2 (R-60 の洗い出し)** 同ファイルの中で他の (SI, peer) を「block」で指す文を全部洗い、**複数ブロックを持つ subsection を一意に指していないもの**は同じ変更セットで直す。一意なもの・自ブロックを指す `this block's own` は触らない。洗い出しの結果は **§1.3** (実物)。
- **D-3 (R-61)** 同じ小ブロックの `- never run against production during WP-E/WP-D …` の主張を**現在の条件**に直す: 本番では runbook の gated procedure (`MitateDB-api/docs/cloud-run-cloud-sql.md` section 10) を通してだけ実行する、という**現在形の 1 主張**にする。後半の `every test targets a throwaway PostgreSQL cluster only (MITATEDB_TEST_ADMIN_DSN)` は事実のままなので残す (実測: `MitateDB-api/tests/test_ops_apply_platform_migration.py`:44・49-58 の `ADMIN_DSN_ENV` と `_admin_dsn`、既定値は無く未設定は `RuntimeError`)。**失効した WP 名・work order section への参照は現行行から外す**。文言は help の確定文と食い違わせない (逐語の複製は求めない)。
  - **重複の判定 (起草時に現物で行い、設計レビュー 1 の指摘 (i) で直した。§1.11)**: 3 条件 (isolated proof / independent audit / requester approval) を新しい行に**書き写さない**。同じ小ブロックの Platform-upgrade runbook の主張 (:756〜:758) が現在形で既にそれを述べており (`the remediation stage is gated instead by the isolated proof, the independent audit and the requester's approval`)、書き写すと同じ小ブロックに二重に立つ。**新しい行はその主張を同じ小ブロックの中で名指す** — 「this file は restate しない」とは書かない (同じファイルの同じ小ブロックが現に述べているので偽になる)。`MitateDB-api/tests/test_ops_help_text.py`:104-116 の `CONFIRMED_PRODUCTION_SENTENCE` と `RESTATED_PRECONDITION_PHRASES` の註が、コード側で同じ判断 (前提を書き写さず section 10 を名指す) を既に固定している。R-57 が足した `apply-platform-migration` の Control (:745〜:750) は本番の条件を 1 つも述べていないので、そちらとの重複は無い。
- **D-4 (作法)** Update convention のとおり、**現行行を書き換え、旧文は逐語で** `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` へ移す。版は **2.13 → 2.14**。Version 行・`Blocks per subsection` 段の実測の記述・`conformance-tests/test_control_mapping_register.py` が見る不変量 (1 主張 1 行、`|` 表なし、ブロック長と行長の上限、名前付き 3 本まで、履歴リンクの解決) は R-59・R-57 の先例どおりに扱う。**ブロック長を実測して記録する**。
- **D-5 (連鎖の洗い出し)** runbook・`docs/` で `security/CONTROL_MAPPING.md` の版数・当該主張を引く行が連鎖して動くかを洗う。結果は **§1.4** (実物)。
- **D-6 (変異)** 文の訂正なので、register テストが**新しい行に掛かっている**ことを示す変異を最小限 (§1.7 の 3 件)。変異を持たない完了条件は**監査照合**とし、照合対象 (コマンドと出力、`file:line`) を報告に逐語で残す。
- **却下** (監督確定、蒸し返さない): 純粋な移動で直す (文の訂正なので不可。`tools/check_control_mapping_split.py` の `moved` にはならない) / :751 を単に削除する (本番の条件の主張が正本順位 5 から消える。runbook :2692-2697 が `security/CONTROL_MAPPING.md` にその記録が在ることを現在形で述べている)。

### 1.2 確定文 (逐語。**複製するだけ**で、言い換え・再入力をしない)

行番号は基点 `3965fe4` の現物。**(5) の preamble への追記で以後の行番号は下へずれる**ので、対象は行番号ではなく**文の中身**で同定し、最終の行番号は統合直前に実測して報告に書く。編集は **(1) → (2) → (3) → (4) → (5) の順**で行う。

#### (1) 新しい `:754` (SI-09 / MitateDB-api / platform upgrade / Control、D-1)

置換は 1 箇所だけ — `SI-08's own MitateDB-api block` を `` `SI-08`'s `MitateDB-api` `default block` `` にする。他は 1 字も変えない。確定文の全体:

```
- **`0014_role_connection_limits_rollout.sql`**: applies the raised ceilings `SI-08`'s `MitateDB-api` `default block` states, retroactively (already-provisioned runtime/developer roles, a registry row whose role `pg_roles` no longer carries skipped rather than aborting the file) and going forward (`begin_provision_application`'s own `CREATE OR REPLACE`, both the `CREATE ROLE` branch and its `duplicate_object` fallback), the WHOLE file inside one transaction so a permission failure partway leaves nothing changed rather than a half-applied state;
```

#### (2) 新しい `:751` (同じ小ブロックの Control、D-3)

行全体を次で置き換える (1 物理行。末尾は `.`、文頭は小文字 — :745 から続く `;` 連結の群の最後の行だから)。

```
- against production, `apply-platform-migration` is run only through the runbook's gated procedure (`MitateDB-api/docs/cloud-run-cloud-sql.md` section 10), whose stage 2 and stage 4 preconditions this block's own Platform-upgrade runbook claim below states rather than this claim restating a subset of them -- the subcommand's own help text, section-heading comment and docstring name that same section too, pinned by `MitateDB-api/tests/test_ops_help_text.py`; every test targets a throwaway PostgreSQL cluster only (`MITATEDB_TEST_ADMIN_DSN`).
```

`this block's own Platform-upgrade runbook claim below` が指すのは、**同じ小ブロックの同じ Control 軸の** `- **Platform-upgrade runbook (R-45 WP-D)**: …` (:756、3 条件は :756 の後半と :758)。指示語 `below` の指す先が同じ小ブロックの中に在ることを確認してから置く (R-59 の分割で立てた規律。`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §7)。

起草時の裏取り (報告で再実測する): runbook の stage 2 / stage 4 は `MitateDB-api/docs/cloud-run-cloud-sql.md`:1799-1802 と :2692-2697。help は `MitateDB-api/src/mitatedb_api/ops.py`:3183-3184、節見出しコメントは同 :2627-2628、docstring は同 :2819-2820。pin は `MitateDB-api/tests/test_ops_help_text.py::test_apply_platform_migration_help_never_mentions_work_package_and_has_the_confirmed_sentence`・`::test_section_comment_and_docstring_carry_the_confirmed_production_sentence`・`::test_ops_source_no_longer_restates_the_runbook_preconditions`。

#### (3) `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` への追記 (2 件、D-4)

`## SI-09` 節の**末尾**に 2 件を**この順**で足す。節は既に `---` で終わっている (`:303`、`## SI-10` の直前) ので、**1 件目はその既存の `---` に続けて preface 行から始める** — `---` を新しく足さない (足すと空の区切りが 2 本続き、版 2.9 の追記が残した `:265`-`:267` の二重 `---` と同じ形になる)。**旧文は現物から切り出してそのまま移し、再入力しない** (1 字でも変わったら逐語でなくなる)。

1 件目 — 旧 `:751` (現在形の本番制限に置き換わった側):

```
*MitateDB-api Control claim, the restriction on running `apply-platform-migration` against production, superseded 2026-09-20 (Version 2.14, R-61 -- the WP-E/WP-D work period it names ended when R-45 was accepted on 2026-09-18; the restriction in force is the runbook's own gated procedure (section 10), which the help text and the source text have named since R-53 and R-55), verbatim:*

<ここに旧 :751 の行をそのまま 1 行で置く>

---
```

2 件目 — 旧 `:754` (指し方を直した側):

```
*MitateDB-api Control claim, the block `0014_role_connection_limits_rollout.sql` takes the raised ceilings from, superseded 2026-09-20 (Version 2.14, R-60 -- `SI-08's own MitateDB-api block` stopped being unique once SI-08's MitateDB-api subsection gained its `ops inventory` named block; the claim now names the `default block`, the term R-50 itself defined for the mandatory first block of a subsection and this file's own re-measurement sentences use), verbatim:*

<ここに旧 :754 の行をそのまま 1 行で置く>

---
```

#### (4) 新しい Version 行 (`:5` を置き換える。**1 物理行のまま**にする — 折ると以後の行番号がずれる)

```
Version: **2.14** (2026-09-20; R-60 + R-61 -- SI-09's MitateDB-api `platform upgrade` named block, two Control claims corrected in place, no claim moved between blocks: the `0014_role_connection_limits_rollout.sql` claim now names `SI-08`'s `MitateDB-api` `default block` -- `default block` being the term R-50 itself defined for the mandatory first block of a subsection, the one this file's own re-measurement sentences use -- instead of the `SI-08's own MitateDB-api block` form that stopped being unique once that subsection gained its `ops inventory` named block (R-60); the production-restriction claim now states the restriction in force -- against production the subcommand is run only through the runbook's gated procedure (section 10), whose preconditions this same block's Platform-upgrade runbook claim states -- instead of R-45's expired WP-E/WP-D work-period restriction, matching the help text and the source text R-53 and R-55 already put in that same form (R-61). No new invariant or control. The 2 superseded lines verbatim in `CONTROL_MAPPING_HISTORY.md`'s SI-09 section. -- docs/design/ROADMAP_POST_PHASE7_V1.md R-60/R-61)
```

#### (5) `Blocks per subsection` 段への再実測の追記 (段の末尾、:76 の `unchanged this change set.` の後ろ。D-4)

先例 (版 2.11・2.12・2.13 の 3 文) と同じ書き方。**数値は自分で実測した値に置き換える** — 下は起草時の実測で、一致するはずだが、一致しなければ実測値を正として報告に理由を書く。段は 70 桁前後で折られているので、同じ幅で折る (物理行の上限 1,400 は満たすが、体裁を揃える)。

```
Re-measured 2026-09-20 (version 2.14, after R-60/R-61 corrected two Control claims in SI-09's `MitateDB-api` `platform upgrade` block in place and moved nothing): that block is now `12,528` characters (`2,672` left, against the `12,200` version 2.13 measured); the longest block stays `SI-08`'s `MitateDB-api` `default block` at `13,023`, unchanged this change set.
```

起草時の実測 (設計レビュー 1 の指摘 (i) を反映した後の再計算。`conformance-tests/test_control_mapping_register.py` の `_subblock_block_text` を直接呼んだ値。`MAX_BLOCK_LENGTH = 15200`): 対象ブロック 12,200 → **12,528** (残り **2,672**)、最長は `SI-08` / `MitateDB-api` / 既定 **13,023** で不変、新しい物理行の最大長は **1,384** (上限 1,400、これは本件が増やした行ではない既存行)。新 `:751` は **545** 字 (旧 227)、新 `:754` は 550 字 (旧 540)、新しい Version 行は **1,142** 字 (旧 1,088)。

### 1.3 D-2 の洗い出し (基点 `3965fe4` の実物。監督が起草時に実施)

**方法**: `security/CONTROL_MAPPING.md` の本文 (`:88` 以降 = SI 節の中) で `block` / `blocks` を含む行を機械的に全件列挙し (9 行)、この文書の構造上の「block」の語義で使っている行だけを残した (4 行)。preamble (`:1`-`:87`) は別枠で 31 行を列挙し、§1.3.3 に判定を書いた。

**複数の小ブロックを持つ subsection は 3 つだけ** (同じ実測): `SI-08` / `MitateDB-api` (既定 + `ops inventory`)、`SI-09` / `MitateDB-api` (既定 + `platform upgrade`)、`SI-14` / `r2db-api` (既定 + `audit query`)。ほかはすべて既定の 1 本なので、`block` で指しても一意である。

**`block` 以外の指し方も全件見た** (設計レビュー 1 の指摘 (v)。§1.11): 本文の主張行のうち `SI-NN` を引くか `row` / `cell` / `column` の語を使う行は **111 行**あり、そのうち**上の 3 つの (SI, peer) の組を peer 名つきで指している文は `:754` だけ**である (`:163` は共通 suite の adapter 名として `MitateDB-api` を挙げているだけで (SI, peer) を指していない。`:619` の `r2db-api's own SI-08 row` は既定 1 本の subsection なので一意)。`row` / `cell` は分割前の表の語彙の名残だが、非一意になっている行は無い。

#### 1.3.1 本文で構造上の「block」を使う 4 行

| file:line | その行が居る小ブロック | 指す先 | 判定 |
|---|---|---|---|
| `security/CONTROL_MAPPING.md`:120 | SI-00 / r2db-api / 既定 | `this block's own acceptance boundary above` = **自ブロック** | **触らない** (D-2 の「自ブロックを指す `this block's own`」) |
| `security/CONTROL_MAPPING.md`:134 | SI-00 / MitateDB-api / 既定 | `the r2db-api block above` = SI-00 / r2db-api。この subsection は**既定 1 本**だけ | **触らない** (一意) |
| `security/CONTROL_MAPPING.md`:152 | SI-00 / MitateDB-api / 既定 | `this block's own acceptance boundary above` = **自ブロック** | **触らない** (同上) |
| `security/CONTROL_MAPPING.md`:754 | SI-09 / MitateDB-api / `platform upgrade` | `SI-08's own MitateDB-api block` = SI-08 / MitateDB-api。この subsection は**2 本**持つ | **直す** (D-1。§1.2 (1)) |

#### 1.3.2 語義が違うため対象外の 5 行 (列挙の非空振りの記録)

`:649`・`:650` は `ops inventory` の判定語 `blocks` (confirmed / blocked / unknown の `blocked`)、`:871` は `conn.transaction()` block、`:1061` は `never blocks a fail-closed operation`、`:1152` は `the classified block` (`try` の中の分類ブロック)。いずれもこの文書の小ブロックを指していない。

#### 1.3.3 preamble の 31 行 (判定と、監督への申し送り)

preamble の `block` はすべて**規約そのものの説明**か**実測の記録**であって、ある小ブロックから他の (SI, peer) を指す主張ではない。`:49`-`:76` の再実測の 3 文は既に `` `SI-14`'s `r2db-api` `default block` `` の一意な書き方を使っている。**例外は `:28`** — `this file's longest (SI, subsection) block is still SI-14's r2db-api block, now 15,122 characters` の `SI-14's r2db-api block` は、今日の目で読むと `SI-14` / `r2db-api` の 2 本のどちらとも読める。ただし (a) 同じ段の `:57`-`:58` が `the 15,122-character figure above describes the file before the first split` と時点を限定しており、(b) この段は版 2.7 で一度 in place に訂正され旧文は `:78`-`:86` に保存されている。**監督裁定 (a) (2026-09-20) で確定: 本作業では触らない** (D-2 の対象は「他の (SI, peer) を block で指す**主張**」であり、preamble の時点限定つきの実測記録はそれに当たらない)。直すのは **R-65 (SI-08 の既定の小ブロックの分割) の変更セットで preamble を再実測するとき**に in place で行う (§3)。

### 1.4 D-5 の連鎖の洗い出し (基点 `3965fe4` の実物。監督が起草時に実施)

**方法**: (a) `security/` の外で `CONTROL_MAPPING` を引く全件 (`*.md` / `*.py`)、(b) `version 2.1x` を引く全件、(c) 旧 `:751` の文面 (`never run against production` / `records the same limit`) を引く全件を機械的に列挙した。

| 引いている場所 | 何を引いているか | 判定 |
|---|---|---|
| `MitateDB-api/docs/cloud-run-cloud-sql.md`:2692-2697 | 3 条件を述べた後の `(security/CONTROL_MAPPING.md records the same limit on apply-platform-migration itself)` | **runbook は直さない (監督裁定 (b)、2026-09-20 確定。§1.11 の (i))。** 新しい `:751` も同じ制限を記録し続け (本番は section 10 の gated procedure を通してだけ)、3 条件そのものは同じ小ブロックの :756〜:758 が現在形で述べていて、新しい `:751` がそれを**同じ小ブロックの中で名指す**ので、runbook の `records the same limit on apply-platform-migration itself` はファイルの中で解決する。**表の行も手順も変えないので §10.6 / §10.7 / §10.10 の版は据え置き、§10.8 の受理記録も足さない** (版数規則の主語は表本体と手順である。先例 = R-57 の §10.7 据え置きの裁定)。**完了条件 6 の監査照合の対象**とし、実装担当は runbook のこの段を読んで、新しい `:751` と矛盾しないことを逐語で報告する |
| `docs/design/ROADMAP_POST_PHASE7_V1.md`:456・458・459・461・467 ほか、`docs/work-orders/HANDOVER_*.md`、`docs/work-orders/WORK_ORDER_R5*.md`、`docs/design/MITATEDB_*_V0_1.md`、`docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` | 版 2.9〜2.13 の**過去の**実施記録 | **触らない** (記録文書。過去形の実施記録であり、版 2.14 で偽にならない) |
| `CLAUDE.md`:13・`AGENTS.md`:13・`README.md`:30・`SECURITY.md`:11・各 peer の `README.md`・runbook・`docs/design/` の設計文書 | ファイルの役割・`SI-NN 行`への参照 (版数は引いていない) | **触らない** (版数にも本件の 2 行にも依存しない) |
| `conformance-tests/test_control_mapping_register.py` | `MAX_BLOCK_LENGTH` / `MAX_LINE_LENGTH` / `MAX_NAMED_SUBBLOCKS` の定数と、preamble が宣言する `MAX_LINE_LENGTH` の一致 | **触らない。** 本件は定数を動かさない (新しい最長ブロックも生まれない)。**もし動かす必要が出たら実装せず監督へ報告する** (§0 の例外) |
| `tools/check_control_mapping_split.py` / `tools/check_control_mapping_restructure.py` | ファイル名だけ | **触らない** |

**結論: 同じ変更セットに入る他文書は 0 件。** 触るのは `security/` の 2 ファイルだけである。

### 1.5 触ってよいパス

- `security/CONTROL_MAPPING.md`
- `security/CONTROL_MAPPING_HISTORY.md`

これ以外は **0 件**。とくに `spec/`・`conformance-tests/`・`security/SECURITY_INVARIANTS_V1.md`・`MitateDB-api/`・`r2db-api/`・`tools/`・`docs/design/`・`.github/` を触らない (台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` の R-60 / R-61 行の更新と記録の追記は**統合時に監督が行う**)。既存の検査が新しい行で赤になったら**直さず報告する**。

### 1.6 完了条件

| # | 完了条件 |
|---|---|
| 1 | §1.2 の (1)(2) の確定文が `security/CONTROL_MAPPING.md` に**逐語で**入っている (1 字も違わない)。旧 2 行は現行の位置から消えている |
| 2 | 旧 2 行が §1.2 (3) の形で `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` 節に**逐語で**移っている (見出しは `## SI-09` のまま。題を足さない)。`git show 3965fe4:security/CONTROL_MAPPING.md` から切り出した 2 行と、履歴に置いた 2 行が完全一致することを機械的に照合し、出力を報告に残す |
| 3 | Version 行が §1.2 (4) の確定文で、**1 物理行**である。`Blocks per subsection` 段の末尾に §1.2 (5) の再実測の文が在り、**自分で実測した値**が入っている |
| 4 | `conformance-tests/test_control_mapping_register.py` が**緑** |
| 5 | `./.venv/bin/python tools/check_control_mapping_split.py --base 3965fe4` の集計行が `missing=2 added=2 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical` である。**まず `--expect` 無しで走らせて出力を逐語で記録し、予測と一致したら同じ行を `--expect "<その行>"` に渡して終了コード 0 を取る**。一致しなければ止めて報告する (差分は本件の 2 行と preamble だけのはず) |
| 6 | **D-5 の監査照合**: `MitateDB-api/docs/cloud-run-cloud-sql.md` の :2692-2697 と :1799-1802 を読み、新しい `:751` と矛盾しないことを逐語で報告する。runbook・`docs/` に差分を 1 行も作らない (`git status --short` で `security/` の 2 ファイルだけであることを示す) |
| 7 | ブロック長の実測を報告する: 対象ブロックの訂正前後、文書の最長ブロック、`MAX_BLOCK_LENGTH` までの残り。§1.2 (5) の起草時の実測値と一致するか、ずれるならその理由 |
| 8 | `python3 tools/check_doc_refs.py` が 0 dangling、`python3 tools/public_value_scan.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md` が 0 flagged、`python3 tools/change_class.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md` が `class=D` |
| 9 | §1.7 の変異 3 件が全部 `expect=red got=red` で、復元が sha256 2 回で照合済み |
| 10 | 下の対応表に**対応の無い行が無い** |

### 1.7 完了条件 → 変異

| # | 変異 (`tools/dev/mutate.py`。`old` は各ファイルに 1 回だけ現れる文字列にする) | 期待 |
|---|---|---|
| 1・3 | **監査照合**: 新しい 2 行と Version 行・再実測の文の `file:line` と、`git diff` の逐語。確定文との完全一致は `diff` で示す | — |
| 2 | **監査照合**: 完了条件 2 の機械照合 (基点から切り出した旧 2 行と履歴の 2 行の完全一致) の出力を逐語で | — |
| 4 (1 主張 1 行) | **M1**: 新しい `:751` の途中 (`section 10), which names` の直前) に改行を入れ、後半を `- ` で始まらない物理行にする | **赤**: `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` |
| 4 (ブロック長) | **M2**: 新しい `:751` の**直後**に、`- ` で始まる詰め物の主張を 4 行足して対象ブロックを上限超にする (各物理行は 1,400 字未満、合計で残り = 完了条件 7 の実測値 +1 字以上)。詰め物の中身は合成文字列だけで、実 DSN・実ホスト名・絶対パスを書かない | **赤**: `::test_control_mapping_md_blocks_do_not_exceed_the_length_cap` |
| 4 (履歴リンク) | **M3**: `security/CONTROL_MAPPING_HISTORY.md` の `## SI-09` の見出しに題を足して `## SI-09 Controlled Destructive Operations` にする (アンカーが変わる) | **赤**: `::test_every_control_mapping_section_has_a_resolving_history_link` |

**M3 の註** (設計レビュー 1 の指摘 (ii)。§1.11): M3 は**基点でも赤になる**変異であり、**本変更セットが足した文言そのものは観測しない** — 旧文を置いた節の**履歴リンクの不変量が生きていること**の生存確認である。旧文が逐語で正しい節に在ることの照合は完了条件 2 (機械照合) が担い、M3 はそれを置き換えない。`::test_control_mapping_history_has_exactly_the_main_sections_ids` も同時に赤になりうるので、`tests` には上の 1 件だけを置く。
| 5・6・7・8 | **監査照合**: 各道具の出力行と、runbook の 2 段の逐語、実測値の表 | — |
| 9 | **監査照合**: `mutate.py` の 1 行ずつの出力と summary 行 | — |
| 10 | **監査照合** (本表) | — |

**M2 の註**: 詰め物を入れると行長の検査も同時に条件を満たしうるので、`mutations` の `tests` には**ブロック長の 1 件だけ**を置く (§1.5 の 40 の「1 項目 1 テスト」。`mutate.py` は `expect=red` に `-x` を付ける)。新しい本文が測られる側に入っていることの直接の証拠は完了条件 7 の実測 (訂正前後の差) である。

### 1.8 道具の引数

worktree は `.claude/worktrees/jovial-almeida-97c9fb` (基点 main `3965fe4`)。コマンドは main checkout を cwd にして走らせ、`$SP` (自分の scratchpad) を export しておく。

```bash
tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- conformance-tests/test_control_mapping_register.py -q
tools/dev/mutate.py "$SP/r60-mutations.json" -C .claude/worktrees/jovial-almeida-97c9fb
```

worktree の中で走らせるもの (`security/` の 2 ファイルしか触らないので peer suite も `tools/tests` も要らない):

```bash
./.venv/bin/python tools/check_control_mapping_split.py --base 3965fe4
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md
python3 tools/change_class.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md
```

**`pytest` の直接実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。一時ファイルは `$SP` 配下だけに置く。報告は `$SP/r60-report.md` に書く。

### 1.9 レビュー

**文のレビュー 1 回** (実装担当・起草者とは別の起動)。観点: (i) 新しい 2 行が言い過ぎ・言い足りずになっていないか (runbook §10 と `ops.py` の help / コメント / docstring の現物と突き合わせる)、(ii) 3 条件を二重に立てていないか、(iii) 旧 2 行が逐語で履歴に在るか、(iv) §1.3 の洗い出しに漏れが無いか (自分で列挙し直す)、(v) 実測値の独立再測。結果はファイルに書かせる。

**受け入れ監査 1 回** (レビュー担当とも別の起動)。Class D の手順が求めるもので、省かない (R-59 の訂正註が「D の手順は受け入れ監査を求める」と記録している)。

### 1.10 記録 (統合時に監督が埋める)

- 実施日・作業コミット・main SHA:
- 道具の出力 (逐語):
- ブロック長の実測:
- 完了条件 → 変異 → 結果:
- 監督裁定:
- 文のレビュー / 受け入れ監査:
- 完了ゲート (監督が単独実行):

### 1.11 設計レビュー 1 の反映 (2026-09-20、監督裁定として全件採用)

本書 v1.0 の起草に対する設計レビュー 1 回の指摘を、監督が**全件採用**して本節のとおり本文へ反映した (本文は書き換えている — 本書はまだ実装に渡っていない v1.0 の確定前であり、`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 57 が言う「実装に渡った後の訂正註」の場面ではない)。

| # | 指摘 | 反映 |
|---|---|---|
| (i) | 新 `:751` の `rather than this file restating a subset of them` は**偽**である — 同じ小ブロックの :756〜:758 が 3 条件を現在形で述べており、「this file は restate しない」とは言えない | §1.2 (2) の該当句を `whose stage 2 and stage 4 preconditions this block's own Platform-upgrade runbook claim below states rather than this claim restating a subset of them` に差し替えた。runbook :2692-2697 の `records the same limit on apply-platform-migration itself` は**この形でファイルの中で解決する** (同じ小ブロックの中で指し先が辿れる)。**runbook は差分 0** — 監督裁定 (b) として確定 (§1.4)。字数を再計算して §1.2 (5) と実測の段を書き直した |
| (ii) | M3 は基点でも赤になり、本変更セットの新文言を観測しない | §1.7 に M3 の註を足した (生存確認であること、完了条件 2 が照合を担うこと、同時に赤になりうるテスト) |
| (iii) | 履歴への 1 件目の追記が `---` から始まると、既存の節末の `---` と二重になる | §1.2 (3) を「既存の `---` に続けて preface 行から始める」形に直した |
| (iv) | 版行の `the form that stayed unique after R-50` は経緯が逆に読める。`in this file's own block vocabulary` は :48-49 の**他文書向けの slash 形** (`SI-08 / MitateDB-api / ops inventory / Evidence`) と取り違えられる | §1.2 (4) を `` `default block` being the term R-50 itself defined for the mandatory first block of a subsection, the one this file's own re-measurement sentences use `` の形に直した。履歴の 2 件目の preface 行も同じ趣旨に直した |
| (v) | 洗い出しが `block` の語だけでは足りない (`row` / `cell` / `column` / `SI-NN above` の指し方も見るべき) | §1.3 に実測 1 行を足した (主張行 111 行を全件見て、複数ブロックを持つ (SI, peer) を peer 名つきで指すのは `:754` のみ) |
| (vi) | preamble `:28` の扱いを本書の中で確定させる | **監督裁定 (a) で確定: 触らない。** R-65 の変更セットで preamble を再実測するときに in place で直す (§1.3.3、§3) |

## 2. 受け入れ

監督が完了ゲート (`tools/dev/gate.py -C .claude/worktrees/jovial-almeida-97c9fb`) の集計行と §1.6 を照合して判定する。**Class D なので受け入れ監査を入れる** (§1.9)。受理したら、台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-60 行・R-61 行に追記して閉じ (行は消さない)、引き継ぎ書で依頼者へ**事後報告**する (§0)。

## 3. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **preamble `:28` の `SI-14's r2db-api block`** (§1.3.3): 監督裁定 (a) で本書では触らない。**R-65 (SI-08 の既定の小ブロックの分割) の変更セットで preamble を再実測するときに、同じ段の in place の訂正として直す** (旧文の保存は `:78` の訂正註と同じ形で preamble の中に置く — `security/CONTROL_MAPPING_HISTORY.md` は SI の ID しか見出しを持たず、preamble の旧文はそちらへ移せない)。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` の R-65 行へのこの申し送りの追記は、**監督が記録のコミットで行う**。
