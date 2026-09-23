# 作業指示書 — `security/CONTROL_MAPPING.md` を形式 3.0 へ移行する (R-103)

## 0. 版数・位置づけ

- **v1.0 (2026-09-24)。** 台帳 ID **R-103** (`docs/design/ROADMAP_POST_PHASE7_V1.md` §8)。**規模 L**、**変更クラス D** (`security/`・`conformance-tests/` に触れる。宣言前に `tools/change_class.py` で確認する)。
- **1 変更セット = 1 commit。** 下の WP は**作業順**であって commit の単位ではなく、**WP ごとの中間ゲートを走らせない** (WP-1a 直後は現物が旧形なので必ず赤になる)。
- **worktree**: `.claude/worktrees/determined-nightingale-9c442a` (branch `claude/determined-nightingale-9c442a`)。以下 `<WT>` と書く。python は `<main checkout>/.venv/bin/python` (worktree に `.venv` は無い)。
- **`<SHA>` = `94febb3`** — 移行直前の main (版 2.25 の最終状態)。本書と移行後の文書が「版 2.25 の全文は commit `<SHA>` にある」と書くときの値であり、`docs/security/public-repository-policy.md`:72-74 の初回公開ゲートで履歴を書き換えるときは commit-map の対象になる (設計 §3)。
- **枠 (問題設定・決定・根拠・却下した代替案・未確定) は設計文書 `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` v0.3 にある。** 本書は再審議せず、節番号で指す。ただし**実装担当・起草担当にそのまま渡す規定** (§4.3 の主張文法、§4.4 の書き換え規律) と**受入条件 16 件** (§9) は逐語で転記する。**未確定で依頼者判断待ちの事項は無い** (設計 §8)。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`tools/dev/gate.py`・`tools/dev/finalize.py` は監督のみ** — §1.1 の 2)。**下請けの Agent を起動しない** (§1.7 の 47)。**設計外の拡張は実装せず報告に上げる** (§1.5 の 37)。本書の訂正は本文を書き換えず §11 に訂正註として追記する (§1.8 の 57)。
- 本書中の「**監査照合**」は、変異を持たない完了条件である (§1.5 の 40)。照合対象の**逐語記録**は設計 §9 に残す (残すこと自体が完了条件)。照合者は WP ごとの担当欄に書く。

## 1. 目的と読むべき正本

`security/CONTROL_MAPPING.md` の主張を散文から参照形へ移し、上限を block 単位から主張単位へ移す。目的・診断・実測は設計 §1、文法は §2、更新規約は §3。

**読むべき正本**: 設計 `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` **全節** / `docs/work-orders/OPERATING_CONDITIONS.md` §1.2・§1.4・§1.5 (とくに 40)・§1.8・§1.9・§1.12・§1.13・§1.15 / `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §9 の 8・9 / `docs/design/DEVELOPMENT_PROCESS_HYGIENE_V1.md`。

## 2. 変更セットの形・作業順・面の重なり

### 2.1 作業順 (中間ゲートなし)

**WP-1a** (検査の差し替え) → **WP-2 ∥ WP-3** (書き換え、起草担当 2 並列 → 監督が現物へ差し込む) → **WP-4** (一度きりの検査と監査) → **WP-5** (前文・HISTORY・正本参照・台帳) → **WP-1b** (床の再固定) → **完了ゲート 1 回 + `tools/tests -q`** → **commit** (監督)。

WP-1b が最後なのは、床が**移行後の現物**の実測から決まり、前文の縮約 (WP-5) が route i' の件数を動かすためである。

| WP | 目的 | 担当 | 設計の該当節 |
|---|---|---|---|
| **WP-1a** | 登録テストの差し替え (6 テスト・定数 3 つの退役、`MAX_CLAIM_LENGTH` と新検査 (1)(2)(3))、道具 4 + テスト 2 の退役 | 実装担当 (Sonnet) | §4「WP-1 の内訳」 |
| **WP-2** | SI-00〜SI-07 の書き換え | 起草担当 (Opus) A | §2.1〜§2.3、§4 |
| **WP-3** | SI-08〜SI-15 の書き換え | 起草担当 (Opus) B | §2.1〜§2.3、§4 |
| **WP-4** | 多重集合検査・限界主張の 1 対 1 照合・軸を移した主張を指す参照の洗い出し | 監督 + 監査担当 (Opus) | §4「WP-4 の検査」 |
| **WP-5** | 前文の縮約・HISTORY 冒頭・版 3.0・正本文書の参照更新・台帳 | 監督 | §3、§6.2、§6.2b |
| **WP-1b** | 位置参照の形ごとの床の再固定 | 実装担当 (Sonnet) | §4「床の再固定」 |

### 2.2 並行するのは WP-2 と WP-3 だけであり、触る面の重なりは 0 である

`OPERATING_CONDITIONS.md` §1.2 の 16・17 のため、**両起草担当は `security/CONTROL_MAPPING.md` を直接編集しない**。各自の出力は scratchpad の別ファイルであり、現物への差し込みは監督が順に行う。

| WP | 書き込むファイル (これ以外に書き込まない) |
|---|---|
| WP-2 | `$SP/cm-v3-si00-07.md`、`$SP/cm-v3-history-si00-07.md` |
| WP-3 | `$SP/cm-v3-si08-15.md`、`$SP/cm-v3-history-si08-15.md` |

実ファイル名で見て重なり **0**。追跡ファイルへの書き込みは両 WP とも **0** 件である。

### 2.3 完了ゲートと commit (監督のみ)

```
tools/dev/gate.py -C <WT> --label cm-form-v3          # 最後に 1 回 (run_in_background)
tools/dev/pt.py  -C <WT> -- tools/tests -q            # 根ゲートは tools/tests を集めない
tools/dev/finalize.py -C <WT> --branch claude/determined-nightingale-9c442a \
    --allow 'security/*' --allow 'conformance-tests/*' --allow 'tools/*' \
    --allow 'docs/*' -m "$SP/msg.txt" --tools-tests
```

## 3. WP-1a — 登録テストの差し替えと道具の退役 (実装担当、Sonnet)

**担当**: 実装担当 (Sonnet)。**git 操作をしない** (削除も `git rm` ではなく作業ツリーからの削除)。**使用テンプレート**: 2 (実装担当)。**変更クラス**: D。

### 3.1 触ってよいパス (肯定列挙。これ以外に書き込まない)

```
conformance-tests/test_control_mapping_register.py
tools/dev/README.md
tools/restructure_control_mapping.py            (削除のみ)
tools/check_control_mapping_restructure.py      (削除のみ)
tools/check_control_mapping_split.py            (削除のみ)
tools/control_mapping_axes.tsv                  (削除のみ)
tools/tests/test_restructure_control_mapping.py (削除のみ)
tools/tests/test_check_control_mapping_split.py (削除のみ)
```

### 3.2 触らないパス

**上記以外のすべて。** とくに `security/CONTROL_MAPPING.md` と `security/CONTROL_MAPPING_HISTORY.md` (WP-2/3/5 が触る)、`conformance-tests/CONDITIONS.md` とその登録テスト、`conformance-tests/test_conformance_docstring_position_refs.py`、両 peer の `src`・`tests`、`spec/`、`docs/`、`.github/`、`tools/` の他の script。**新しいテストファイルを作らない** (既存の登録テストに足す)。**床の定数 (`POSITION_REF_*_FLOOR`) と `POSITION_REF_ALLOWLIST` を本 WP では触らない** (WP-1b が扱う)。

### 3.3 実測した行番号 (基点 `94febb3`。設計が引く行番号は設計起草時のものでずれている — 実装は本表に従う)

| 対象 | 実測 |
|---|---|
| `test_control_mapping_md_named_subblocks_do_not_exceed_max_named_subblocks` | :621 |
| `test_control_mapping_md_blocks_do_not_exceed_the_length_cap` | :628 |
| `test_control_mapping_md_lines_do_not_exceed_the_line_length_cap` | :638 |
| `_DECLARED_MAX_LINE_LENGTH_RE` (直下の検査でしか使わない) | :649 |
| `test_control_mapping_md_declares_the_same_max_line_length_as_this_file` | :652 |
| `test_fixture_named_subblock_alone_exceeds_the_length_cap` | :920 |
| `test_fixture_four_named_subblocks_exceeds_max_named_subblocks` | :933 |
| `MAX_BLOCK_LENGTH` (由来コメント :119-141) | :142 |
| `MAX_LINE_LENGTH` (由来コメント :144-154) | :155 |
| `MAX_NAMED_SUBBLOCKS` (由来コメント :157-162) | :163 |
| module docstring の `Known gaps` 節 (docstring 終端 :108) | :63-107 (項目 2 = :73-80、項目 3 = :81-87、項目 4 = :88-107) |
| `_extract_position_refs` / `_resolve_position_ref` / `_find_unresolved_position_refs` | :1435 / :1535 / :1589 |
| `POSITION_REF_ALLOWLIST` (説明コメント :1622-1634) | :1635-1646 |
| 床の規約コメント / 床の定数 | :1648-1658 / :1659-1668 |
| ファイル総行数 | 1,873 |
| `tools/dev/README.md` の Known gaps 表 | :58 (`check_control_mapping_restructure`)、:59 (`check_control_mapping_split`)、:73 (登録テスト) |

### 3.4 手順

1. **6 テストを削除する** (:621 / :628 / :638 / :652 / :920 / :933 と、:652 でしか使わない `_DECLARED_MAX_LINE_LENGTH_RE` :649)。削除理由は設計 §4「WP-1 の内訳」の表にある。
2. **定数 3 つを由来コメントごと削除する**: `MAX_BLOCK_LENGTH` (:119-141 + :142)、`MAX_LINE_LENGTH` (:144-154 + :155)、`MAX_NAMED_SUBBLOCKS` (:157-162 + :163)。削除したあとに残るヘルパが未使用になったら、それも同じ変更で落とす (未使用の検出結果を報告に出す)。
3. **`MAX_CLAIM_LENGTH` を置く** — 軸ごとの値 `{"Control": 250, "Evidence": 300, "Status": 300}`。直上のコメントに、**計数単位は先頭の `- ` を含む物理行全体の文字数**であること、値の出所が設計 §2.1 (依頼者裁定 2026-09-23、監督裁定 2026-09-23 で Control 200 → 250) であることを書く。
4. **検査 (1) 主張長** を足す。現物に対する検査と、合成 fixture に対する検査の**両方**。
5. **検査 (2) Control 主張の施行箇所参照** を足す。**既存の R-88 の抽出・解決関数 (`_extract_position_refs` :1435 / `_resolve_position_ref` :1535) を再利用する** — 単なる backtick トークンを受理しない。`POSITION_REF_ALLOWLIST` (:1635-1646) に載る参照は**施行箇所の参照に数えない** (設計 §2.2)。現物と合成 fixture の両方。
6. **検査 (3) Evidence 主張の参照** を足す。テスト名か file 参照を 1 つ以上 (定義は設計 §5 の (E) を用いる)。現物と合成 fixture の両方。
7. **退役 6 ファイルを作業ツリーから削除する** (`tools/restructure_control_mapping.py`・`tools/check_control_mapping_restructure.py`・`tools/check_control_mapping_split.py`・`tools/control_mapping_axes.tsv`・`tools/tests/test_restructure_control_mapping.py`・`tools/tests/test_check_control_mapping_split.py`)。**`git rm` を使わない** — git 操作は監督が行う。
8. **`tools/dev/README.md` の Known gaps 表から :58 と :59 の 2 行を外す。** :73 の登録テスト行から **`the current longest sub-block is deliberately unrecorded (ledger R-73)`** の句を外し、件数を実際の項目数に合わせる。
9. **登録テストの module docstring の `Known gaps` 節から項目 2 (:73-80、同じ R-73 の穴) を削り**、残る項目の文面は 1 字も変えずに番号だけ振り直す。
10. 合成 fixture の新テストは既存に倣い **`test_fixture_` で始まる名前**にする (§3.7 の `-k fixture` で選べるようにするため)。fixture に**実 credential・実ホスト名・実ドメイン・作業機の絶対パスを書かない** (§1.9)。

**WP-1a の時点で現物 (`security/CONTROL_MAPPING.md`) はまだ版 2.25 の旧形である。** したがって検査 (1)(2)(3) の**現物側は赤で正常**であり、**現物テストの緑を本 WP の完了条件にしない**。現物側が緑になるのは WP-3 の差し込み後である。

### 3.5 完了条件

| # | 完了条件 |
|---|---|
| (1) | §3.4 の 1・2 が済み、`grep -n 'MAX_BLOCK_LENGTH\|MAX_NAMED_SUBBLOCKS\|MAX_LINE_LENGTH' conformance-tests/test_control_mapping_register.py` が **0 件**。削除した 6 テストの名前が同ファイルから消えている。**監査照合** |
| (2) | `MAX_CLAIM_LENGTH` が Control 250 / Evidence 300 / Status 300 を持ち、計数単位がコメントに書かれている。**監査照合** |
| (3) | 検査 (1): 合成 fixture の **250 文字の Control 主張は緑、251 文字は赤**。同じ検査が現物に対しても走る (結果は本 WP では問わない) |
| (4) | 検査 (2): 合成 fixture の**施行箇所の位置参照を持たない Control 主張が赤**、R-88 の 6 形のいずれかで解決する参照を持つものは緑。`POSITION_REF_ALLOWLIST` の参照だけを持つ主張は**赤** |
| (5) | 検査 (3): 合成 fixture の**参照の無い総称文 Evidence 主張が赤**、テスト名か file 参照を持つものは緑 |
| (6) | 退役 6 ファイルが作業ツリーに無く、`git rm` を使っていない (`git status --short` に 6 件の ` D` が並ぶ)。**監査照合** |
| (7) | `tools/dev/README.md` の :58・:59 が無く、:73 の行から R-73 の句が消えて件数が項目数と一致する。登録テストの docstring の `Known gaps` から項目 2 が消え、残りが振り直されて文面は不変。**監査照合** (照合対象の逐語は設計 §9 に残す) |
| (8) | 触ってよいパス (§3.1) の外を 1 行も変えていない (`git status --short` と `git diff --stat` を報告に貼る。**git の読み取りのみ**) |
| (9) | (1)〜(8) に対応の無い変更行が無い |

### 3.6 完了条件 ↔ 変異の 1 対 1 表

**変異は検査器側に掛ける** (現物は旧形のため)。**1 変異 = 1 entry = 1 test id** (`mutate.py` は `-x` で最初の失敗で止まる。§1.5 の 33・40)。

| 完了条件 | 変異 (`file`: 操作) | 期待 | 赤になる test |
|---|---|---|---|
| (3) | `conformance-tests/test_control_mapping_register.py`: `MAX_CLAIM_LENGTH["Control"]` を **250 → 251** | red | 251 文字の Control 主張を赤にする fixture テスト |
| (4) | 同: 検査 (2) の解決呼び出しの戻りを**常に「解決した」**にする | red | 参照を持たない Control 主張を赤にする fixture テスト |
| (5) | 同: 検査 (3) の参照抽出が**常に空**を返すようにする | red | 参照を持つ Evidence 主張を**緑にする**側の fixture テスト (抽出が空だと受理側が落ちる) |
| (1) | **無し (監査照合)** — 削除の確認であり、機械検査を置けない。grep の 0 件を報告に貼る | — | — |
| (2) | **無し (監査照合)** — 定数値とコメントの照合。逐語は設計 §9 | — | — |
| (6) | **無し (監査照合)** — ファイル削除と `git status --short` の突合 | — | — |
| (7) | **無し (監査照合)** — 散文と索引行。照合対象の逐語は設計 §9 | — | — |
| (8) | **無し (監査照合)** — 触る面の確認 | — | — |
| (9) | **無し (監査照合)** — 対応表そのものの検査 | — | — |

### 3.7 道具の引数と集計行の期待形

```
tools/dev/pt.py -C <WT> -- conformance-tests/test_control_mapping_register.py -q -k fixture
tools/dev/mutate.py "$SP/wp1a-mutations.json" -C <WT>
```

- `$SP/wp1a-mutations.json` は **3 entry**、各 entry に `"tests": ["conformance-tests/test_control_mapping_register.py::<test id>"]` と `"expect": "red"` を持つ。
- `pt.py` の期待形: **failed 0 / error 0**、`passed` は着手時に測った fixture 件数 + 新規 fixture 件数。基点の件数は着手時に 1 回測って報告に書く (主張は実測の後。§1.5 の 34)。
- `mutate.py` の期待形: **3 entry すべて `expect=red` / `got=red`**、復元の sha256 一致 2 回、`git grep -F` の件数一致。**summary 行と `log=` のパスをそのまま報告に貼る** (§1.10 の 65)。
- **現物側の検査を走らせない** (走らせれば赤になるのが正常である)。Bash timeout は 600000 を明示する (§1.5 の 39)。

## 4. WP-2 / WP-3 — SI 節の書き換え (起草担当 Opus、2 並列)

**担当**: 起草担当 (Opus) 2 名。**WP-2 = SI-00〜SI-07** (`security/CONTROL_MAPPING.md`:137-603、主張 148 件 = Control 87 / Evidence 33 / Status 28)、**WP-3 = SI-08〜SI-15** (:604-1355、主張 377 件 = Control 246 / Evidence 86 / Status 45)。件数は基点 `94febb3` の実測 (合計 525、設計 §1.1 と一致)。

### 4.1 触ってよいパス (肯定列挙)

- WP-2: `$SP/cm-v3-si00-07.md` (書き換え済みの節全文)、`$SP/cm-v3-history-si00-07.md` (HISTORY へ逐語で移す旧主張)。
- WP-3: `$SP/cm-v3-si08-15.md`、`$SP/cm-v3-history-si08-15.md`。

**出力ファイルの形**: 節全文は `## SI-NN <name>` から次の `## ` の直前までを、**見出し・空行・`[history](...)` リンクを含めて**そのまま置く (監督がその範囲と差し替えるため)。HISTORY 側は `## SI-NN` ごとに、移す旧主張を**逐語** (1 字も変えない) で並べ、各件に「旧軸 → 新軸 / 撤回」の 1 行を添える。

### 4.2 触らないパス

**追跡ファイルのすべて。** とくに `security/CONTROL_MAPPING.md` と `security/CONTROL_MAPPING_HISTORY.md` を**直接編集しない** (差し込みは監督)。相手側 WP の scratchpad ファイルにも書かない。`## CCR-14` 節 (:1356-1425)、`## Rule` 節 (:1426-) 、前文 (:1-136)、HISTORY 本体は**対象外**である。

### 4.3 主張文法 (設計 §2.1〜§2.3 の逐語転記。起草担当の prompt にそのまま渡す)

**以下は設計 `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §2.1〜§2.3 の逐語である。引用内の `§` 番号は設計文書の節を指す。行番号を伴う参照は設計起草時のものであり、登録テストの現行行番号は本書 §3.3 にある。**

> ### 2.1 軸ごとの形 (依頼者裁定 2026-09-23、決定 1)
>
> | 軸 | 形 | 上限 | 必須 | 禁止 |
> |---|---|---|---|---|
> | **Control** | **主語 (6 語以内の名詞句)** + 何を bound するか 1 文 + **施行箇所の参照** | **250 文字** (参照込み。字数から参照トークンを除く案は却下 — §7 (f)) | **施行箇所の位置参照**を 1 つ以上 = R-88 の 6 形のいずれかで解決する `path` 又は `path:line`。関数名・クラス名だけの参照は施行箇所と認めない (主語には使ってよい)。既存の `F-NN` / `C-NN` / `CCR-NN` があれば**主語の前**に置く | 限界・未実施の記述 (Status へ)、実装手順の再説明 |
> | **Evidence** | 何が観測されたか + その出所 | **300 文字** | **テスト名か `file:line` を 1 つ以上**引く | 引用の無い総称文 (「negative topology and isolation tests」の類) |
> | **Status** | 開示された限界・peer 間差 | **300 文字** | — | 制御の再説明、進捗・WP の記録 |
>
> - 上限は **主張単位** (`MAX_CLAIM_LENGTH`、軸ごとの値) とする。**計数単位は先頭の `- ` を含む物理行全体の文字数**である。block 単位の `MAX_BLOCK_LENGTH` と `MAX_NAMED_SUBBLOCKS` の検査は**退役**する。
> - named block は**既存の 5 つをそのまま残す**(位置参照が指しているため)。**新規追加は不可**。
> - 見出し構造 (`## SI-NN` / `### peer` / `### peer -- topic` / `#### Control|Evidence|Status`)、peer の順、`- —` の空軸標識、`|` 始まり行を置かない規約は**据え置く**。
> - 前文の再計測ログ (34 行) は削除する。版上げ記録は **1 行** (版番号、日付、R 番号、触れた block 名のみ) とする。
> - **Status 軸の限界文は peer block に残す** (監督裁定 2026-09-23 の確定。Common block へ集約しない)。移動が 0 なので `POSITION_REF_ALLOWLIST` (`conformance-tests/test_control_mapping_register.py`:1616-1634 の (参照文字列, SI, peer) キー) と既存の位置参照を壊さない。
> - **`## CCR-14` 節と `## Rule` 節は 3.0 の主張文法の対象外**。軸構造を持たない散文なので、上限も検査 (1)(2)(3) も適用せず、本移行では触らない。
> - **分割時の位置参照**: R-88 の shape c (同一**物理行**の先行 backtick パスを継承する形) は行をまたがない (`conformance-tests/test_control_mapping_register.py`:1697)。1 主張を複数に割るときは、**継承していた backtick パスを分割後の各主張に明記して複製する**。
> - **既存の参照は形を変えない**。label 形 (`0004:102-113` の類)・peer 相対形・`:line` 継承形をフルパスへ「正規化」しない (shape e / route ii は床すれすれ)。`path:line` に揃えるのは**新規に書く参照だけ**。
> - 前文の `CONTROL_MAPPING_HISTORY.md` への backtick 参照 (route i') は**4 件を維持する** (`security/CONTROL_MAPPING.md`:5・:16・:47・:130)。床は他の形と同じく**移行後実測 − 現行 margin** に再固定する (§4 WP-1)。
> - 帰結: 参照を引けない Evidence 主張は**最低 21 件**あり、`RM`:160 が指す SI-07 r2db-api 節はそのうちの 1 つにすぎない。実テスト名を引けなければ **Status へ落ちる = 証拠主張の撤回**であり、旧文は HISTORY へ逐語で移す (§3)。
>
> ### 2.2 主語と ID の引き方 (監督裁定 2026-09-23)
>
> 新しい制御 ID 族は作らない (却下理由は §7)。Control 主張は**主語 + 制御の 1 文 + 施行箇所の参照**で書き、既存の ID があるときだけそれを主語の前に置く。
>
> | 要素 | 規則 |
> |---|---|
> | 主語 | **6 語以内の名詞句**。実装上の名前 (クラス・関数・ロール・migration ファイル) をそのまま使うのが既定 |
> | 既存 ID | `ops verify-declarations` の検査を持つなら **`F-NN`** (両 peer の `ops.py` の登録表が正本。`MitateDB-api/src/mitatedb_api/ops.py:1281-1288` ほか、現在 F-18 まで)。共通 conformance 条件で固定されているなら **`C-NN`** (`conformance-tests/CONDITIONS.md`)。control-plane の条項なら **`CCR-NN`** (`spec/CCR_DISPOSITION.md`)。いずれも**新設しない**。無ければ ID を書かない |
> | 施行箇所の参照 | **R-88 の 6 形のいずれかで解決する位置参照** (`path` 又は `path:line`) を 1 つ以上。**必須**。関数名・クラス名は主語に使えるが、これ単独では施行箇所と認めない |
> | 書かないもの | `R-NN` (台帳) と `D-N` / `Z-N` (設計文書ローカル) は制御 ID ではない。主語の前に置かない (出所として文中に引くのは可) |
> | 数えない参照 | `POSITION_REF_ALLOWLIST` (`conformance-tests/test_control_mapping_register.py`:1616-1634) に載る参照 (`security/CONTROL_MAPPING.md`:626・:740 の peer 間比較) は**施行箇所の参照に数えない** (解決せず許可されている参照であり、その主張の施行箇所を示さない) |
>
> ### 2.3 例 (旧→新。旧文は版 2.25 の現物から逐語)
>
> **例 1 — SI-08 / r2db-api / Control (`security/CONTROL_MAPPING.md`:614、240 文字)**
>
> 旧:
>
> > - `RequestByteBoundMiddleware` enforces the byte bound in the ASGI receive loop, measured from actual bytes received (not `Content-Length`), before Starlette's parser runs -- the real request path, unexercised on the VPS under real traffic;
>
> 新 (Control 1 件 + Status 1 件に分かれる。主語は `RequestByteBoundMiddleware`、施行箇所は `http.py:187`。この制御に既存の F-/C-/CCR- ID は無いので ID は書かない):
>
> > #### Control
> > - `RequestByteBoundMiddleware` bounds `request_bytes` in the ASGI receive loop from bytes actually received, not `Content-Length`, before Starlette parses -- `r2db-api/src/r2db_api/http.py:187`.
> >
> > #### Status
> > - **`RequestByteBoundMiddleware` unexercised in production**: the VPS has never run this middleware under real traffic; every measurement is from the test suite.
>
> **例 2 — SI-08 / r2db-api / Evidence (`security/CONTROL_MAPPING.md`:634、1,244 文字)**
>
> 旧 (先頭部分を逐語で示す。1 主張が 1 行でテスト名 9 個を抱えている):
>
> > - **R-56, measured on throwaway PostgreSQL clusters**: the effective value a reader connection opened after `0014` carries, the 503 a statement over that ROLE-level bound produces on a pooled reader connection (the scenario shortens the role's own declared value with `ALTER ROLE ... SET` and restores it from `pg_roles.rolconfig`, rather than overriding it per connection), and `0014`'s own re-application -- `r2db-api/tests/test_auditreader_statement_timeout.py::test_reader_connection_effective_statement_timeout_is_5000ms_after_0014` (reads `pg_settings.setting`, the raw ms integer), `::test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection`, `::test_0014_reapplication_is_idempotent`; F-17's own red and green are `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_after_migration_0014`, … (以下 F-17 のテスト名 5 個)
>
> 新 (観測 1 つ = 主張 1 つ。いずれも 300 文字以内):
>
> > - reader connection effective `statement_timeout` after `0014`, read from `pg_settings.setting` -- `r2db-api/tests/test_auditreader_statement_timeout.py::test_reader_connection_effective_statement_timeout_is_5000ms_after_0014`.
> > - a statement over the ROLE-level bound answers 503 without backend detail and frees the connection -- `::test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection`.
> > - `0014` re-applies idempotently -- `::test_0014_reapplication_is_idempotent`.
> > - F-17 green after `0014`, red when the declared timeout is zero, reset, or overridden per database, and green when the role is absent -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_after_migration_0014` ほか 4 件 (各 1 主張)。
>
> 「measured on throwaway PostgreSQL clusters」という限界は Status 側の既存主張 (`:639`) が既に持つので重複して書かない。
>
> **例 3 — SI-09 / MitateDB-api / platform upgrade / Status (`security/CONTROL_MAPPING.md`:861、672 文字)**
>
> 旧:
>
> > - Section 10's three reviewed subjects stand at these versions -- the 10.6 table at 4, the 10.7 table at 4, the 10.10 procedure at 7 -- and each stays a draft until section 10.8's own row names that same version for it; section 10.8 is the single place that state is read from, and a row naming an earlier version counts as no record at all. As of this version of this file, nothing in section 10 has been run against production, and neither `0014_role_connection_limits_rollout.sql`, the `0004` stages R-54 adds, nor the run/closure behavior R-57 adds has been applied to production either -- every value and every judgment above was measured on a throwaway test cluster.
>
> 新 (前半は限界ではなく受理記録なので Evidence へ、後半だけが Status に残る):
>
> > #### Evidence
> > - runbook section 10's accepted versions are 10.6 table 4, 10.7 table 4, 10.10 procedure 7, read from the single acceptance row in section 10.8 -- `MitateDB-api/docs/cloud-run-cloud-sql.md:NNN` (行番号は書き換え時に実測する).
> >
> > #### Status
> > - **Production evidence is `absent`**: section 10 has never been run against production, and neither `0014_role_connection_limits_rollout.sql`, the `0004` stages R-54 adds, nor the run/closure behavior R-57 adds is applied there; every value above was measured on a throwaway cluster.

**主張は英語で書く** (現物と同じ)。

### 4.4 書き換え規律 (設計 §4「WP-2 / WP-3 の書き換え規律」の逐語転記)

> - 1 主張 = 1 観測 / 1 制御。長い主張は分割する (例 2)。
> - 既存 ID (`F-NN` / `C-NN` / `CCR-NN`)・テスト名・`file:line`・限界を示す文は**落とさない**。落とす候補が出たら削らずに軸を移す。
> - named block は増やさない。既存 5 つの見出し文字列は 1 文字も変えない (他文書がこの見出しを指す。§5 の 7)。
> - 主張を分割するときは、継承していた backtick パスを各主張に**明記して複製する** (§2.1)。既存の参照の形は変えない。
> - **Evidence が証拠を引けず Status へ落ちた主張と、撤回した Control 主張は HISTORY へ逐語**で移す (§3)。それ以外の削除した散文は HISTORY へ移さない。
> - `## CCR-14` 節と `## Rule` 節には触れない。

### 4.5 完了条件 (WP-2・WP-3 で同じ。担当範囲だけを見る)

| # | 完了条件 |
|---|---|
| (1) | 担当範囲の全主張が §4.3 の軸ごとの形に従い、**上限内** (Control 250 / Evidence 300 / Status 300、計数は先頭 `- ` を含む物理行全体) |
| (2) | 全 **Control 主張**が R-88 の 6 形のいずれかで解決する**施行箇所の位置参照**を 1 つ以上持つ (`POSITION_REF_ALLOWLIST` の 2 件は数えない)。主語は **6 語以内の名詞句** |
| (3) | 全 **Evidence 主張**がテスト名か `file:line` を 1 つ以上引く。引けないものは **Status へ落とし**、旧文を `$SP/cm-v3-history-*.md` へ**逐語**で置く |
| (4) | `##` / `###` / `####` の見出しを **1 文字も変えていない**。named block を増やしていない。peer の順・軸の順・`- —` の扱い・`\|` 始まり行を置かない規約が保たれている |
| (5) | 既存 ID・テスト名・`file:line`・限界を示す文を**落としていない** (落とす候補は軸を移した)。既存の参照の**形**を変えていない。分割した主張には継承 backtick パスを複製した |
| (6) | 出力は §4.1 の 2 ファイルだけであり、**追跡ファイルへの書き込みが 0 件** (`git status --short` が空。git の読み取りのみ)。`## CCR-14`・`## Rule`・前文・HISTORY 本体に触れていない |
| (7) | **旧→新の対応表**を報告に出す: 旧主張 1 件ごとに (SI, peer, block, 旧軸) → (新軸, 新主張の数)、および軸を移した件・Status へ落とした件・撤回した件の一覧。WP-4 の 1 対 1 照合と式 B 突き合わせの入力になる |
| (8) | (1)〜(7) に対応の無い変更行が無い |

### 4.6 完了条件 ↔ 変異の 1 対 1 表

| 完了条件 | 変異 | 期待 | 備考 |
|---|---|---|---|
| (1)(2)(3) | **本 WP に固有の変異は無し** — 機械で受け持つのは WP-1a が足した検査 (1)(2)(3) であり、その変異は §3.6 (検査器側) と §7.5 (移行後の現物側) の表にある | — | 差し込み後に現物テストが緑になることが受入条件 1〜4 |
| (4) | **無し (監査照合)** — `git show <SHA>:security/CONTROL_MAPPING.md \| grep -E '^###? '` との diff が空 (受入条件 7 (ii))。既存の形・節順の検査も据え置きで走る | — | 逐語は設計 §9 |
| (5) | **無し (監査照合)** — WP-4 の多重集合検査 (missing = 0) と 1 対 1 照合が受け持つ | — | 逐語は設計 §9 |
| (6) | **無し (監査照合)** — `git status --short` の突合 | — | — |
| (7) | **無し (監査照合)** — 対応表そのもの。設計 §9 に逐語 | — | — |
| (8) | **無し (監査照合)** — 対応表そのものの検査 | — | — |

### 4.7 道具の引数

- 起草担当は**道具を実行しない** (scratchpad への書き出しのみ)。長い現物は `tools/dev/section.py security/CONTROL_MAPPING.md --list` で見出しを見て、担当範囲の節だけ読む。
- **監督の差し込み手順** (WP-2・WP-3 の受領後、順に 1 回ずつ): `$SP/cm-v3-si00-07.md` を `security/CONTROL_MAPPING.md`:137-603 と、`$SP/cm-v3-si08-15.md` を :604-1355 と差し替える (行番号は基点 `94febb3` の実測。差し込み直前に再実測する)。HISTORY 側は `$SP/cm-v3-history-*.md` の各件を `security/CONTROL_MAPPING_HISTORY.md` の該当 `## SI-NN` へ**逐語**で追記する (見出し集合と 1:1 対応、各節が空でないという既存の契約は変えない。設計 §3)。

## 5. WP-4 — 一度きりの検査と監査 (監督 + 監査担当 Opus)

**担当**: script の実行は監督、監査照合は監査担当 (Opus)。**使用テンプレート**: 6 (受け入れ監査)。

### 5.1 触ってよいパス

**scratchpad のみ** (`$SP/cm-v3-check/` 配下の script と出力)。**追跡ファイルを 1 つも触らない。** `tools/` に道具を増やさない (`OPERATING_CONDITIONS.md` §1.12 の 72)。

### 5.2 触らないパス

追跡ファイルのすべて。とくに `tools/`・`conformance-tests/`・`security/`。

### 5.3 手順 (設計 §4「WP-4 の検査」)

1. scratchpad の script (bash 3.2 互換 + `python`) で、旧 (版 2.25 = `git show <SHA>:security/CONTROL_MAPPING.md`) と新 (作業ツリー) の各 `(SI, peer, block, axis)` について次の多重集合を抽出して比較する。条件は **missing = 0**。

   | 集合 | 抽出 |
   |---|---|
   | 既存 ID | `F-NN` / `C-NN` / `CCR-NN` / `L{phase}-N` |
   | テスト名 | `test_[A-Za-z0-9_]+` |
   | `file:line` | R-88 の 6 形に合わせた backtick 付きパス + 行番号 |

   **「限界を示す文」の多重集合比較は採らない** (全主張を書き換えるので文字列一致が成立せず、常に赤になる)。
2. **限界主張の 1 対 1 照合** (監査担当): 母数は**旧 Status 主張 73 件全件** + **設計 §2.1 により Status へ移した旧 Control / Evidence 主張**。1 件ごとに新形の**後継主張** (SI, peer, block, 軸, 本文) を示し、**後継なし = 0 件**とする。
3. **Control 主張の主語の監査** (監査担当): 主語が **6 語以内の名詞句**であることを **block ごとに**述べる (受入条件 13)。
4. **軸を移した主張を指す参照の洗い出し**: WP-2/3 の旧→新の軸対応表と、他文書の**式 B** (軸まで書いた参照。設計 §6.1。実行式は本 WP の script に置く) を突き合わせ、腐る参照を一覧にする。**正本文書の分は WP-5 が直す**。記録 (台帳の閉止行・作業指示書・引き継ぎ書) は触らない。
5. **Status へ落ちた Evidence 主張と撤回した Control 主張**について、旧文が `security/CONTROL_MAPPING_HISTORY.md` に逐語であることと、件数・SI の一覧 (受入条件 9)。

script・集計行・監査の逐語は**すべて設計 §9 に追記する** (監督が行う)。実 credential・実ホスト名・実ドメイン・作業機の絶対パス・traceback を書かない (§1.9)。

### 5.4 完了条件

| # | 完了条件 |
|---|---|
| (1) | 多重集合 3 種 (既存 ID / テスト名 / `file:line`) の **missing = 0**。script と集計行が設計 §9 に逐語。**監査照合** |
| (2) | 限界主張の 1 対 1 照合: 母数 (旧 Status 73 件 + Status へ移した旧 Control / Evidence 主張) の**各件に後継が示され、後継なし = 0 件**。一覧が設計 §9 に。**監査照合** |
| (3) | Control 主張の主語が 6 語以内の名詞句であることを **block ごとに**述べた逐語が設計 §9 に。**監査照合** |
| (4) | 式 B の突き合わせ一覧 (腐る参照。正本 / 記録の別を付す) が設計 §9 に。**監査照合** |
| (5) | Status へ落ちた Evidence 主張・撤回した Control 主張の旧文が HISTORY に逐語であり、件数と SI の一覧が設計 §9 に。**監査照合** |
| (6) | 追跡ファイルの変更が **0 件** (`git status --short` に本 WP 由来の行が無い)。**監査照合** |
| (7) | (1)〜(6) に対応の無い主張が報告に無い |

### 5.5 完了条件 ↔ 変異の 1 対 1 表

| 完了条件 | 変異 | 備考 |
|---|---|---|
| (1)〜(7) | **全件 無し (監査照合)** — 一度きりの検査と監査であり、`tools/` に道具を増やさない以上、機械検査を残さない (`OPERATING_CONDITIONS.md` §1.12 の 72) | 照合対象の逐語 (実行したコマンドと集計行、監査の全文) を**設計 §9 に残すこと自体が完了条件**である (§1.5 の 40) |

### 5.6 道具の引数

- script は `$SP/cm-v3-check/*.sh` / `*.py`、python は `<main checkout>/.venv/bin/python`。
- 旧版の取得は `git show 94febb3:security/CONTROL_MAPPING.md > "$SP/cm-v3-check/old-2.25.md"` (**読み取りのみ**)。
- 監査担当は `pytest --collect-only -q` と静的照合を主とし、変異を作らない (§1.6 の 43)。

## 6. WP-5 — 前文・HISTORY 冒頭・正本文書の参照・台帳 (監督)

**担当**: 監督。**変更クラス**: D。

### 6.1 触ってよいパス (肯定列挙)

```
security/CONTROL_MAPPING.md                                   (前文と版)
security/CONTROL_MAPPING_HISTORY.md                           (冒頭 1 行)
docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md   (§5 に上書き註)
docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md                 (退役註 1 行)
docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md               (退役註 1 行)
docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md      (式 B 参照 6 件)
docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md                   (§9 実施記録の追記のみ)
docs/design/ROADMAP_POST_PHASE7_V1.md                         (台帳)
tools/dev/README.md                                           (:73 の登録テスト行)
```

設計 §6.2b の「判定が要る」6 文書 (下表) は、**1 件ずつ判定して正本と判定した分だけ**上の列挙に加えて更新する (判定表は設計 §9 に残す)。

| 文書 | `CONTROL_MAPPING.md:NNN` の件数 |
|---|---|
| `docs/design/CODE_COMMENT_PROVENANCE_V1.md` | 3 |
| `docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md` | 3 |
| `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` | 2 |
| `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` | 2 |
| `docs/design/ROADMAP_POST_PHASE7_V1.md` | 2 |
| `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` | 1 |

### 6.2 触らないパス

**記録** (台帳の閉止行・作業指示書・引き継ぎ書・完了フェーズの監査記録・旧設計文書の行参照) は**触らない** (`OPERATING_CONDITIONS.md` §1.8 の 56・57、設計 §6.2b)。`conformance-tests/test_control_mapping_register.py`:1250 の `security/CONTROL_MAPPING.md:477` は**測定記録**なので行番号を更新せず、「版 2.25 の `:477`」の註記を 1 つ足すだけにする。`conformance-tests/CONDITIONS.md` とその登録テスト、両 peer の `src`、`## CCR-14` 節、`## Rule` 節。

### 6.3 手順

1. **前文の縮約** (`security/CONTROL_MAPPING.md`:1-136):
   - **再計測ログを削除する** (現行 `grep -c 'Re-measured' security/CONTROL_MAPPING.md` = **11**。移行後は **0**)。
   - **版上げ記録は 1 行** (版番号、日付、R 番号、触れた block 名のみ。設計 §3)。
   - **`MAX_LINE_LENGTH = 1400` の宣言を削除する** (:33 の文中)。
   - **裁定 4 の逐語文 (:13「訂正は現行行を書き換え、旧文は履歴へ移す」) は残し**、直後に「3.0 以後は `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §3 が上書きする (2026-09-23)」の 1 文を足す (§1.8 の 56)。
   - **`CONTROL_MAPPING_HISTORY.md` への backtick 参照 4 件を維持する** (route i'。現行 :5・:16・:47・:130)。
   - 「版 2.25 の全文は commit `94febb3` にある」の 1 行を置く。
2. **HISTORY 冒頭**: `security/CONTROL_MAPPING_HISTORY.md` の冒頭に「版 2.25 の全文は commit `94febb3` にある」の **1 行**を置く。
3. **版を 3.0 に上げる** (記録は 1 行。`OPERATING_CONDITIONS.md` §1.13 の 75 のとおり変更セットごとに 1 版)。
4. **§6.1 の判定表の 6 文書を 1 件ずつ判定**し、現行の規約・現行の判断を述べている行 (= 正本) だけを新しい行番号か `SI-NN / peer / axis` の位置指定へ直す。記録と判定した行は触らず、必要なら訂正註で「版 2.25 の行番号」と明記する。判定表を設計 §9 に残す。
5. **旧設計文書 2 本に退役註 1 行**: `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` (§4・§5)、`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` (§5・§6)。**本文は書き換えない** (§1.8 の 56)。
6. **`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5 に上書き註**: 裁定 4 の行は消さず、3.0 が上書きする範囲を明示する (設計 §3 の表)。同文書:521・:543 の「履歴を捨てる」案の却下行も**消さない** (設計 §3)。
7. **`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` の式 B 参照 6 件**を、WP-4 の突き合わせ結果に従って更新する。
8. **`tools/dev/README.md`:73** の登録テスト行を 3.0 に合わせる (WP-1a が R-73 の句と退役 2 行を外した**後**に行う。同ファイルを触るのはこの 2 WP だけであり、順序は WP-1a → WP-5 で固定する)。
9. **台帳** (`docs/design/ROADMAP_POST_PHASE7_V1.md`):
   - **R-103 の行に閉止の【追記】** (完了条件・変異・集計行)。
   - **R-73 の行に【追記】** — 最長 block 長の記録が文書からも検査器からも消えたこと (設計 §5 の 14)。
   - **§0.1.3 の G-2 / G-3 (`CONTROL_MAPPING`) 行を再実測**して更新する (SI-07 r2db-api 節の総称 Evidence が解消したか)。
   - 版上げと版数ログの回転は `OPERATING_CONDITIONS.md` §1.13 の 75・§1.16 の 78 に従う。

### 6.4 完了条件

| # | 完了条件 |
|---|---|
| (1) | 前文: `grep -c 'Re-measured' security/CONTROL_MAPPING.md` = **0**、版上げ記録が **1 行**、`MAX_LINE_LENGTH` の宣言が無い、裁定 4 の逐語文が残り直後に上書き註が付く、`CONTROL_MAPPING_HISTORY.md` への backtick 参照が **4 件**。**監査照合** (grep の出力を設計 §9 に) |
| (2) | 前文と HISTORY 冒頭に「版 2.25 の全文は commit `94febb3` にある」の 1 行がある。**監査照合** |
| (3) | 版が **3.0**、記録は 1 行。**監査照合** |
| (4) | §6.1 の 6 文書を 1 件ずつ判定した表が設計 §9 にあり、正本と判定した行だけが更新され、記録と判定した行は**不変** (`git diff` で示す)。**監査照合** |
| (5) | 旧設計文書 2 本に退役註 1 行、`PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5 に上書き註 (裁定 4 の行と :521・:543 の却下行は不変)。**監査照合** |
| (6) | `MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` の式 B 参照 **6 件**が WP-4 の結果どおり更新されている。**監査照合** |
| (7) | `tools/dev/README.md`:73 の登録テスト行が 3.0 の検査を述べている。**監査照合** |
| (8) | 台帳: R-103 に閉止の【追記】、R-73 に【追記】、§0.1.3 の G-2 / G-3 (`CONTROL_MAPPING`) 行が再実測で更新されている。**監査照合** |
| (9) | 退役 6 ファイルへの**正本からの参照が 0** (`git grep -l` で `tools/dev/README.md`・`docs/work-orders/OPERATING_CONDITIONS.md`・`CLAUDE.md`・`.github/workflows/*.yml`・テスト・現行の設計文書を見る。台帳の閉止行・作業指示書・引き継ぎ書は記録なので残ってよい)。**監査照合** |
| (10) | §6.2 の触らないパスを 1 行も変えていない (`git diff --stat` を報告に貼る) |
| (11) | (1)〜(10) に対応の無い変更行が無い |

### 6.5 完了条件 ↔ 変異の 1 対 1 表

| 完了条件 | 変異 | 備考 |
|---|---|---|
| (1)〜(11) | **全件 無し (監査照合)** — 前文・註・参照・台帳の散文であり、機械検査を持たない | 照合対象の逐語 (grep の出力、判定表、`git diff --stat`) を**設計 §9 に残すこと自体が完了条件**である (§1.5 の 40)。ただし (1) の「再計測ログ 0」と (2) は受入条件 12 のとおり grep で機械的に確かめる |

### 6.6 道具の引数

```
tools/dev/section.py security/CONTROL_MAPPING.md --list
git grep -nE 'CONTROL_MAPPING\.md`?:[0-9]+'                   # 6.3 の 4 の母数
git grep -l -e restructure_control_mapping -e check_control_mapping_split \
            -e check_control_mapping_restructure -e control_mapping_axes.tsv   # 完了条件 (9)
git show 94febb3:security/CONTROL_MAPPING.md | grep -E '^###? '   # 受入条件 7 (ii) の突合
```

## 7. WP-1b — 位置参照の形ごとの床の再固定 (実装担当、Sonnet)

**担当**: 実装担当 (Sonnet)。**WP-2 / WP-3 / WP-5 の後に行う** (前文の縮約が route i' の件数を動かすため)。**git 操作をしない。**

### 7.1 触ってよいパス

```
conformance-tests/test_control_mapping_register.py   (:1648-1658 の規約コメントと :1659-1668 の床の定数のみ)
```

### 7.2 触らないパス

**上記以外のすべて。** とくに `security/CONTROL_MAPPING.md` (変異のときだけ `mutate.py` が一時的に触り、復元する)、`POSITION_REF_ALLOWLIST` (:1635-1646。限界文を peer block に残したのでキーは変えない)、R-88 の抽出・解決関数 (:1435 / :1535 / :1589)、WP-1a が足した検査の本体。

### 7.3 手順

1. **移行後の現物を実測する** — 同ファイル自身の `_find_unresolved_position_refs` (:1589) を scratchpad の一度きりの script から呼び、shape a / a' / b / c / d / e と route i / i' / ii / iii の件数を得る。
2. **各床 = 実測 − 現行 margin** とする (:1648-1658 のコメントが定める元規約)。現行 margin は次のとおり (現行の実測コメント値 − 現行床):

   | 形 / route | 現行実測 | 現行床 | margin |
   |---|---|---|---|
   | shape a | 3 | 2 | 1 |
   | shape a' | 2 | 1 | 1 |
   | shape b | 2 | 1 | 1 |
   | shape c | 18 | 13 | 5 |
   | shape d | 168 | 150 | 18 |
   | shape e | 4 | 3 | 1 |
   | route i | 112 | 100 | 12 |
   | route i' | 4 | 3 | 1 |
   | route ii | 6 | 5 | 1 |
   | route iii | 69 | 60 | 9 |

3. **結果は各床 ≥ 1 である。** 1 未満になる形があれば**実装せず止めて監督に上げる** (§1.5 の 37)。
4. :1648-1658 のコメントの実測行 (件数・日付・基点) を**移行後の実測**に書き換える。margin の規約そのものは変えない。
5. **対応表** (形 / route、旧実測、旧床、margin、新実測、新床) を報告に出す。**監督が設計 §9 に逐語で残す。**

### 7.4 完了条件

| # | 完了条件 |
|---|---|
| (1) | 移行後の現物に対し、`_find_unresolved_position_refs` の**未解決が 0** (`POSITION_REF_ALLOWLIST` の 2 件を除く) であり、死んだ許可行も 0 — 既存の位置参照検査が緑 |
| (2) | 10 個の床がすべて **実測 − 現行 margin** であり、**各床 ≥ 1**。床の検査が緑 |
| (3) | 前文の `CONTROL_MAPPING_HISTORY.md` 参照が **4 件** (route i' の実測が 4)。緑 |
| (4) | :1648-1658 のコメントが移行後の実測 (件数・日付・基点 SHA) を述べ、margin の規約は不変。**監査照合** |
| (5) | 対応表 (形 / route、旧実測、旧床、margin、新実測、新床) が報告にあり、設計 §9 に逐語で残る。**監査照合** |
| (6) | 移行後の現物に対する**検査 (1)(2)(3) が緑** (主張長違反 0 / 施行箇所参照の無い Control 主張 0 / 参照の無い Evidence 主張 0) |
| (7) | §7.1 の外を 1 行も変えていない (`git status --short` と `git diff --stat` を報告に貼る) |
| (8) | (1)〜(7) に対応の無い変更行が無い |

### 7.5 完了条件 ↔ 変異の 1 対 1 表

**WP-1b の変異は現物 (`security/CONTROL_MAPPING.md`) に掛ける** (移行後は現物が新形なので、検査が実際に現物を守っていることをここで示す)。**1 変異 = 1 entry = 1 test id**。

| 完了条件 | 変異 (`file`: 操作) | 期待 | 赤になる test |
|---|---|---|---|
| (6) 主張長 | `security/CONTROL_MAPPING.md`: Control 主張 1 件を **251 文字**にする (末尾に文字を足す) | red | 検査 (1) の現物テスト |
| (6) 施行箇所 | 同: Control 主張 1 件から**位置参照を落とす** | red | 検査 (2) の現物テスト |
| (6) Evidence | 同: Evidence 主張 1 件を**参照なしの総称文**にする | red | 検査 (3) の現物テスト |
| (1) | **無し (監査照合)** — 既存の R-88 検査 (据え置き) が緑であること。集計行を報告に | — | — |
| (2) | **無し (監査照合)** — 床の値が実測 − margin であること。対応表を設計 §9 に | — | — |
| (3) | **無し (監査照合)** — route i' の実測 4 件。対応表に含める | — | — |
| (4) | **無し (監査照合)** — コメントの実測行。逐語は設計 §9 | — | — |
| (5) | **無し (監査照合)** — 対応表そのもの | — | — |
| (7) | **無し (監査照合)** — 触る面の確認 | — | — |
| (8) | **無し (監査照合)** — 対応表そのものの検査 | — | — |

### 7.6 道具の引数と集計行の期待形

```
tools/dev/pt.py -C <WT> -- conformance-tests/test_control_mapping_register.py -q
tools/dev/mutate.py "$SP/wp1b-mutations.json" -C <WT>
```

- `$SP/wp1b-mutations.json` は **3 entry**、各 entry の `"file"` は `security/CONTROL_MAPPING.md`、`"tests"` は現物側の 1 test id、`"expect": "red"`。
- `pt.py` の期待形: **登録テスト全件 green** (failed 0 / error 0)。件数は着手時と移行後の両方を報告に書く。
- `mutate.py` の期待形: **3 entry すべて `expect=red` / `got=red`**、復元の sha256 一致 2 回、`git grep -F` の件数一致。**summary 行と `log=` のパスを報告に貼る**。変異文字列の全文 grep 0 件を commit 前に確認する (§1.4 の 31)。
- Bash timeout は 600000 を明示する。

## 8. 役割の起動 (規模 L)

`OPERATING_CONDITIONS.md` §1.13 の 73・74 のとおり規模 **L** = 現行の全手順。設計レビューは実施済み (1 回 + 再確認、設計 v0.2 / v0.3)。本実施で起動するのは、**実装担当** (WP-1a・WP-1b)、**起草担当 2 並列** (WP-2・WP-3)、**レビュー担当** (コードレビュー 1 回、対象は WP-1a・WP-1b の検査器差分)、**監査担当** (WP-4 の受け入れ監査) である。レビュー担当・監査担当の指摘は `OPERATING_CONDITIONS.md` §1.15 の 77 のとおり 1 件ずつ裁定し、引き継ぎ書の「裁定」節に全件を残す。

## 9. 受入条件 (設計 §5 の 16 条件の逐語転記。番号は設計と同じ)

**以下は設計 `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §5 の表の逐語である。引用内の `§` 番号は設計文書の節を指す。**

> | # | 条件 | 判定 |
> |---|---|---|
> | 1 | 登録テスト全件 green (新 3 検査を含む) | 完了ゲートの集計行 |
> | 2 | 主張長違反 0 (Control 250 / Evidence 300 / Status 300) | 検査 (1) |
> | 3 | R-88 の 6 形で解決する位置参照を持たない Control 主張 0 | 検査 (2) |
> | 4 | テスト名も file 参照も持たない Evidence 主張 0 | 検査 (3) |
> | 5 | 多重集合の `missing = 0` (既存 ID / テスト名 / `file:line` の 3 種のみ) | WP-4 の script。集計行を §9 に逐語 |
> | 6 | **限界主張の 1 対 1 照合**: 母数 = 旧 Status 主張 73 件 + Status へ移す旧 Control / Evidence 主張。各件に新形の後継 (SI, peer, block, 軸, 本文) が示され、**後継なし = 0 件** | 監査照合。一覧を §9 に |
> | 7 | 位置参照が壊れていない: (i) 登録テストの位置参照検査 (R-88) と `conformance-tests/test_conformance_docstring_position_refs.py` (R-95) が緑、(ii) `##` と `###` の見出し集合が 2.25 と同一 (`git show <SHA>:security/CONTROL_MAPPING.md \| grep -E '^###? '` との diff が空)、(iii) 軸を移した主張を指す参照のうち**正本文書**にあるもの (§6.1) が更新されている | 既存検査 + diff + 監査照合 |
> | 8 | 位置参照の形ごとの床が **移行後実測 − 現行 margin** (`conformance-tests/test_control_mapping_register.py`:1637-1639 の元規約。結果は各床 ≥ 1) に再固定され、前文の `CONTROL_MAPPING_HISTORY.md` 参照は 4 件を維持 (route i' も同じ規則で再固定)。再固定値・旧値・実測値の対応表が §9 にある | 登録テスト + §9 |
> | 9 | Status へ落ちた Evidence 主張と撤回した Control 主張の旧文が `CONTROL_MAPPING_HISTORY.md` に逐語であり、件数と SI の一覧が §9 にある | 監査照合 |
> | 10 | 退役 4 ファイル + テスト 2 ファイルが削除され、**正本からの参照 0** (正本 = `tools/dev/README.md`、`docs/work-orders/OPERATING_CONDITIONS.md`、`CLAUDE.md`、`.github/workflows/*.yml`、テスト、現行の設計文書)。台帳の閉止行・作業指示書・引き継ぎ書は**記録**なので触らない (`OPERATING_CONDITIONS.md` §1.8 の 56・57)。旧設計文書 2 本には退役註 1 行 | `git grep -l` + 監査照合 |
> | 11 | 他文書の `CONTROL_MAPPING.md:NNN` 行参照 (24 ファイル、§6.2b) が正本 / 記録に分けて一覧され、**正本の行参照は更新**済み、記録は不変 (`conformance-tests/test_control_mapping_register.py`:1250 は記録。註記 1 行のみ) | 監査照合。一覧を §9 に |
> | 12 | 前文: 再計測ログ 0 (`grep -c 'Re-measured' security/CONTROL_MAPPING.md` = 0)、版上げ記録が 1 行、裁定 4 の逐語文 (:13) が残り直後に上書き註が付く | grep + 監査照合 |
> | 13 | 監査: Control 主張の**主語が 6 語以内の名詞句**であることを evidence-auditor が block ごとに述べ、その逐語が §9 にある (限界の記述の欠落は条件 6 に一本化) | 監査照合 |
> | 14 | 台帳 **R-73 が閉止**されている (最長 block 長の記録が文書からも検査器からも消えたことを台帳行に【追記】) | `RM` の R-73 行 |
> | 15 | 完了ゲート (`tools/dev/gate.py`) を**最後に 1 回**走らせて green、`tools/tests -q` も green、commit は `tools/dev/finalize.py --tools-tests` (監督のみ) | 集計行 |
> | 16 | 1〜15 のうち変異と対応しない条件は 5・6・7(ii)(iii)・8・9・10・11・12・13・14 だけであり、いずれも「監査照合」と明記されている | 作業指示書の対応表 |

**条件 16 の対応**: 上の 5・6・7(ii)(iii)・8・9・10・11・12・13・14 は、本書の WP 別対応表 (§3.6・§4.6・§5.5・§6.5・§7.5) ですべて「**無し (監査照合)**」と明記してある。変異と対応するのは条件 2・3・4 (§3.6 の 3 件 = 検査器側、§7.5 の 3 件 = 現物側) と、条件 1・15 (完了ゲートの集計行) である。**(E) 抽出式** (設計 §5 の (E)) は条件 2・3・4 の計数の定義であり、実装・監査ともこれを用いる。

## 10. 本変更セットで実施しないこと

- **`conformance-tests/CONDITIONS.md` とその登録テストを触らない。** 同書:8 の裁定 4 は据え置く (設計 §3)。2 つの登録簿で更新規約が非対称になることは承知の上である。
- **両 peer の `src` を触らない** (`r2db-api/`・`MitateDB-api/`)。
- **`## CCR-14` 節と `## Rule` 節を触らない** (設計 §2.1。軸構造を持たず 3.0 の主張文法の対象外)。
- **記録文書の行参照を直さない** — 台帳の閉止行、作業指示書 12 本、引き継ぎ書 3 本、完了フェーズの監査記録、旧設計文書の行参照 (設計 §6.2b の「記録」区分)。`conformance-tests/test_control_mapping_register.py`:1250 は註記 1 行のみ。
- **named block を増やさない。既存 5 つの見出し文字列を変えない。**
- **新しい検査器・新しい ID 族・`tools/` の新しい道具を作らない** (設計 §7 の (b)(e)、`OPERATING_CONDITIONS.md` §1.12 の 72)。WP-4 の script は scratchpad にとどめる。
- **`docs/work-orders/OPERATING_CONDITIONS.md` §1 の行を変えない** (変更には依頼者確認が要る。`RM` §9 の 8)。

## 11. 訂正註

(訂正は本文を書き換えず本節に追記する — `docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 57。)

1. **【訂正註 1 (2026-09-24、起草時の疑義 3、監督裁定)】** 前文は `MAX_LINE_LENGTH` のほかに `MAX_BLOCK_LENGTH` ("Length cap measurement" 段落 :26-33) と `MAX_NAMED_SUBBLOCKS` ("Blocks per subsection" 段落 :35-) も宣言する。WP-5 (§6) の扱い: "Length cap measurement" 段落は再計測ログと一体なので**段落ごと削除**する。"Blocks per subsection" 段落は残し、「at most 3 named blocks (`MAX_NAMED_SUBBLOCKS = 3` …)」の文を「既存 5 つの named block を据え置き、新規追加は不可 (3.0、設計 §2.1)」に書き換え、末尾の再計測ログ (Re-measured …) は削除する。**【訂正 2026-09-18 (R-50, version 2.7)】** の逐語記録段落は残す (裁定 4 の逐語文と同じく、前文に置かれた記録)。
2. **【訂正註 2 (2026-09-24、起草時の疑義 4、監督裁定)】** 受入条件 10 の「正本からの参照 0」に対し、退役ファイルを引く正本が 2 つある: `docs/design/DEPROVISION_FORCED_DROP_V0_1.md`:243 は WP-5 の触るパスに加え、退役註 1 行 (旧設計文書 2 本と同じ形) を足す。`conformance-tests/test_control_mapping_register.py`:53 の docstring の参照は WP-1a の手順に含め、退役した旨に書き換える (docstring 本文の他の文は変えない)。
3. **【訂正註 3 (2026-09-24、起草時の疑義 5、監督裁定)】** 登録テストの Known gaps 項目 4 (床のピンによる偽の赤) は再固定後も真である (床は移行後の混合比を固定する)。WP-1b (§7) で「本作業指示書が再固定するまで」の時点付き文言を時点なしの形 (「再固定されるまで赤になる」) に改め、項目そのものは残す。番号は WP-1a の振り直しに従う。
4. **【訂正註 4 (2026-09-24、監督裁定)】** 起草担当は §4.7 の「道具を実行しない」にかかわらず、自分の出力ファイルに対する読み取り専用の自己検査 (`$SP/cm_selfcheck.py`: 主張長・Control の施行箇所参照の解決・Evidence の参照の有無・テスト名の解決を、旧ファイルに担当範囲を差し込んだ合成テキストに対して登録テストの既存関数で測る) を走らせてよい。追跡ファイルへの書き込みは引き続き 0 件。
5. **【訂正註 5 (2026-09-24、WP-4 監査の結果、監督裁定)】** 設計 §6.1 が「軸まで書いた参照 (式 B) の正本 8 件 (`docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` 6 件、`security/CONTROL_MAPPING.md` 自己参照 2 件) は WP-5 で更新する」とした前提は実測で成立しなかった — 監査 (`$SP/wp4-audit.md` §4) は式 B 48 行 / 17 ファイルのうち正本 8 件がいずれも腐っていない (指す軸に後継が現存) と判定した。したがって §6.3 の手順のうち INVENTORY の 6 件の更新と自己参照 2 件の更新は**行わない** (触らない)。受入条件 7(iii) は「正本で腐った参照 0 件」の監査照合で充足とする。記録側で軸が動いた 4 行 (作業指示書 R-87:49、R-71:22/:88、R-52:265/:271) は規律どおり不変。
6. **【訂正註 6 (2026-09-24、監督裁定)】** 台帳 R-73 は 2026-09-22 に閉止済み (2026-09-23 に Known gaps へ移管) だったので、受入条件 14 の「R-73 が閉止されている」は、R-73 行への【追記】(Known gaps に残っていた「現行最長 block の実測値を書かない」の性質が、上限の主張単位化で登録テストからも README 索引からも消えた) で満たす。新たな閉止操作は無い。
