# コード内経緯コメントの記録への移動 (R-22 問い 3)

## 0. 版数・位置づけ

- **v0.3 (2026-09-14)**: 作業指示書起草時の疑義 9 件への監督裁定 (同日) を反映した。D-2 の参照行と塊の対応、D-3 / D-4 (検査をツールへ集約)、§3 の ID 分類、§4.1 (2)(4)(5)、§4.2、§6 を改めた。
- **v0.2 (2026-09-14)**: 設計レビュー (M1〜M5、m6〜m11) を反映した。§3 の参照トークン 2 分類、normalizer 不変と登録 helper を最後に回すこと、旧 Q-2〜Q-4 は監督裁定 (同日) による。
- v0.1 (2026-09-14): 起草。
- `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (以下 `MRA`) §9.2 が「後続の設計追補」と呼ぶ詳細設計である。要件の正本は `MRA` §9.2、裁定の逐語は roadmap §8 の R-22 行。
- 契約、Security Invariants、conformance 条件、公開 API の意味、コードの実行時挙動を変えない (§4 で機械照合する)。

## 1. 問題と裁定

| 実測 (2026-09-14、両 peer `src/`) | 値 |
|---|---|
| 総行 / code / comment / docstring | 43,425 / 21,035 / 10,740 / 11,650 |
| 10 行以上のコメント塊 | 355 件 (上位: MitateDB `cell.py` 65 件 1,228 行、MitateDB `http.py` 29 件、`backend_postgres.py` 26 件、r2db `postgres.py` 26 件、`structured.py` 24 件) |
| 経緯トークン | `WP-` 1,581、`Phase` 718、`R-` 509、`review` 441、`round` 199、日付 234 ほか |

コードを読む者 (AI エージェントを含む) は、現在の理由を読むために経緯を読み分けなければならない。

**依頼者裁定 (2026-09-14、逐語「全て推奨で進めてください」、問い 3 = A)**: 経緯は設計書などの記録へ移し、コード内には現在の理由と記録への参照 ID だけを残す。移動は抽出とは別の変更セットで行う。

**目的**: コードには現在の理由だけが残る。経緯は失われず、ID から 1 hop で辿れる。

## 2. 決定事項

### D-1 受け皿

| 案 | 内容 | 評価 |
|---|---|---|
| **(i) 採用** | peer ごとの companion `docs/code-history/<peer>/<module>.md` と、登録 helper 用の `docs/code-history/pair.md`。節見出しは `## CH-NNNN` | 受け皿は 1 種。塊を逐語で丸ごと置けるので照合が単純。移した文の設計書 § / 台帳 ID はそのまま残り、既存記録へも辿れる |
| (ii) 却下 | 既存の設計書 § / 台帳 ID を直接参照する | 経緯の多くは既存記録に逐語で存在せず、1 塊が複数の出所を束ねるので ID が定まらない |
| (iii) 却下 | (i) と (ii) の混合 | 塊ごとに「既存記録に逐語で在るか」の判定と 2 系統の照合が要り、到達性は (i) だけで得られる |

- `<module>` は移動時点のファイル名である。後の R-37 抽出で symbol が移っても節は動かさない。
- **各節は移動変更セットの親コミット時点の写しである。** 後のコード変更に合わせて書き換えない。
- 受け皿の規約は `docs/code-history/README.md` に数行で置く (v0.3)。空ディレクトリや空の `.md` は作らない。

### D-2 参照 ID

| 項目 | 規則 |
|---|---|
| 形 | `CH-NNNN` (4 桁)。両 peer 通しの連番で、再利用しない。module・symbol・peer の名を含めない (抽出・改名で嘘にならず、§5 の文字列検査と normalizer にも干渉しない) |
| 採番 | 変更セットの manifest に、使う番号の範囲を予約として書く。並行 worktree が同じ番号を取った場合は、統合時に §4.2 の 2 が赤になる |
| 塊との対応 | **1 塊 = 1 ID。** 塊とは、同じインデントで連続する `#` 行の最大の並び (空行で切れる)、又は 1 つの docstring である。module 直下の塊も同じ扱い。**新旧の塊の対応は CH-ID で取る** (v0.3) |
| コード側 | `#` 塊では、移した塊があった位置に `# history: CH-NNNN` を 1 塊 1 行。残した文があるときはその塊の末尾行とする。docstring では末尾に行 `History: CH-NNNN` を 1 行 (v0.3) |
| 受け皿の節 | `## CH-NNNN` の下に、移動元 (peer 相対パス、囲む symbol の qualname。登録 helper は登録行のパスの組と symbol)、親コミット、種別 (comment / docstring)、塊全体の fenced block を置く |
| 既存族との衝突 | 実測 0 件 (2026-09-14)。`tools/check_doc_refs.py` の族文法にも一致しない |

### D-3 常設検査の置き場所 (v0.3 で改めた)

| 案 | 評価 |
|---|---|
| **`tools/check_comment_provenance.py --register` と、自己テスト `tools/tests/test_comment_provenance*.py` の 1 か所 (採用)** | 検査本体をツールに集約する。`tools/tests` は root の `testpaths` の外なので、**各変更セットのゲートに `pytest tools/tests -q` を明記する**。CI では常時 job `tools-tests` が走る。Class B |
| 両 peer の `tests/test_code_history_register.py` (v0.2 の採用案) | 却下 (v0.3): 同名ヘルパを両 peer に置くと規律 38 (同型性テストでの固定) と衝突し、`_ISOMORPHIC_TARGETS` に登録すれば集合の増減で Class D になる。 |
| `conformance-tests/` (R-10 の前例) | 却下: 実装非依存の場所から peer の `src/` を読むことになり、Class C にもなる。 |

### D-4 照合スクリプトの置き場所

| 案 | 評価 |
|---|---|
| **`tools/check_comment_provenance.py --base <rev>` (採用)** | 全変更セットで同じ照合を reviewer が再現でき、変異も再現できる。旧版は `git show` で読む。`--base` 照合は CI に入れない (常設の検査は同ツールの `--register`、D-3)。自己テストは合成 fixture で `tools/tests/` に置く |
| 変更セットごとの一時スクリプト | 却下: 照合の中身が揺れても reviewer が同一性を確かめられない。 |

## 3. 判定基準

**範囲**: 両 peer の `src/` だけ。`tests/` と `conformance-tests/` は対象外 (後者に触れると Class C)。

| 区分 | 対象 |
|---|---|
| **残す** | 現在も成立する理由。不変条件。安全上の注意 (lock / transaction / timeout の順序、fail-closed の理由)。外部仕様の挙動。**出所を明示した参照だけ** (v0.3): SI-、C-、spec §、設計ファイル名を付けた § / D- / 局所 ID、`roadmap R-NN` / `roadmap L-NN` の形で書いた台帳 ID |
| **移す** | 経緯の叙述 (「以前は X だった」、却下案の検討、裁定に至る議論)。**経緯のトークン**: WP-、review、round、指摘番号、差し戻し、監督裁定、日付。**出所を持たない裸の局所 ID** (例: r2db `postgres.py` の `R-1`〜`R-7`) (v0.3) |
| **対象外** | 実行時に使われる文字列 (argparse の `help=` など)。`# type: ignore` / `noqa` / `pragma` / shebang / encoding 行。登録 helper (`_ISOMORPHIC_TARGETS` の行) は最後の専用変更セットまで触れない (§6) |

| 境界例 | 扱い |
|---|---|
| 1 文に現在の理由と経緯の叙述が同居する | 残す。塊全体は受け皿にも置く |
| 残す文の括弧内に経緯のトークンだけがある | §4.1 (4) の機械的削除で消す (言い換えではない) |
| 台帳 ID の開閉 | ツールでは判定しない。変更セットの manifest に塊ごとの判定表 (塊 / 判定 / 根拠) を置き、レビューで確認する (v0.3) |
| 判定に迷う | **残し、判定表の根拠欄にその旨を書く** |
| docstring が body の唯一の文 | 削除しない (body が空になり AST が変わる) |

**記録**: 変更セットごとに、触れた module の経緯トークン数の前後を manifest に残す。

**別件 (対象外)**: 他文書が引くコード位置 (`security/CONTROL_MAPPING.md:41`、`conformance-tests/CONDITIONS.md:53`、`spec/CCR_DISPOSITION.md:156`) のずれは既に存在しており、直すと Class C / D になる。

## 4. 照合と常設検査

### 4.1 変更時の照合 (`check_comment_provenance.py --base <rev>`)

| # | 照合 | 方法 |
|---|---|---|
| (1) | コード不変 | docstring (Module / ClassDef / FunctionDef / AsyncFunctionDef 先頭の文字列定数) を除いた `ast.dump(include_attributes=False)` を旧版と新版で比べる。行送りでは赤にならない |
| (2) | 移した塊が逐語で在る | 新版の `CH-NNNN` ごとに、その節の fenced block が旧版の塊 1 つ (dedent 後) と byte 一致する。旧版の塊のうち、新版に同一の塊が無く、どの CH-ID にも対応しないものがあれば赤 (v0.3) |
| (3) | 文区間の削除だけ | 新しい塊の文の列が、旧い塊の文の列から、順序を保って文を削除しただけのものである (参照行と (4) を除く)。**前処理**: コメント塊は各行の `#` と先頭空白を除いて空白 1 つで連結し、docstring は行を連結する。**区切り**: 文末の句読点 (`. ` / `。` / `? ` / `! `) と空行 (段落境界。コメント塊では中身の無い `#` 行) だけ。改行では切らない。コード span の中と略語 (`e.g.` / `i.e.` / `vs.` / `...`) では切らない |
| (4) | 括弧内トークンの機械的削除 | 残した文の中では次の操作だけを許す: `(...)` の中身が消してよい語と区切り (`, ` `/` `;` 空白) だけなら、直前の空白と括弧ごと消す。出所を明示した参照と同居する場合は、消してよい語 1 個とその区切りを消す。**消してよい語** (v0.3): (5) の語、及び同じ括弧に出所語 (ファイル名 / `roadmap` / `spec`) を持たない裸の ID (SI- / C- / CCR- を除く) |
| (5) | 経緯を足していない | 差分で追加された行に、次の明示リストの語が無い (v0.3): `\bWP-[0-9A-Za-z-]+`、`\bPhase \d+`、`\b(review\|reviewer)\b`、`\bround \d+\b`、`\b20\d\d-\d\d-\d\d\b`、`差し戻し`、`監督裁定`、`supervisor ruling`、`\bblocker\b`。R- / L- / D- の類は入れない (§3 の判定表で扱う)。閉じた ID の一覧はツールに渡さない |

### 4.2 常設の検査 (`check_comment_provenance.py --register`、v0.3)

1. 各 peer の `src/` に在る `CH-NNNN` の集合が、受け皿 (その peer の companion と `pair.md`) の見出しの集合と一致する (未解決 0、孤児 0)。
2. **両 peer の companion と `pair.md` をすべて読み、同じ `CH-NNNN` の見出しが全体で 1 回だけであること。**
3. 各節が非空で、移動元・親コミット・種別の行を持つ。各 ID はその peer の `src/` に 1 回だけ現れる。`pair.md` の ID は、登録行の両側に 1 回ずつ現れる。
4. 参照行の書式は D-2 の 2 形だけ。
5. `src/` の `__doc__` / `inspect.getdoc` / `inspect.getsource` の使用箇所の集合が、変更セット 0 の実測で固定した集合 (空集合) と一致する (docstring に依存する実行時挙動の新設を検出する)。
6. 非空虚: 両 peer を通した ID の総数が定数 `MIN_CH_IDS` 件以上。変更セット 0 では 0、**変更セット 1 で 1 に切り替える**。

自己テストは `tools/tests/test_comment_provenance*.py` の 1 か所に置き、実リポジトリへの `--register` を含む (D-3)。

## 5. 既知の障害

**(a) 同型性 normalizer。** 両 peer `tests/test_audit_query.py` の `_normalize` は symbol 先頭の docstring だけを除くので、`#` コメントと入れ子の docstring は比較に残る。**normalizer は変えない** (`MRA` §6 の禁止)。登録 helper は §6 の最後の専用変更セットまで対象外である。実測で経緯コメントを持つ登録 helper は `src/` 8 側 (`tests/` 4 側は §3 の範囲外)。

**(b) ソース文字列の検査。** 着手前に、両 peer の `tests/` と `conformance-tests/` を `read_text|\.count\(|getsource|__doc__` で grep し、一覧を取り直す。`ast.parse` を通すものはコメントに鈍感なので除く。v0.2 時点の一覧:

| 箇所 | 向き | 検査対象 |
|---|---|---|
| `MitateDB-api/tests/test_main.py:688-694` | `not in` | `main.py` の `build_app` の `inspect.getsource` |
| `r2db-api/tests/test_process_ceilings_declaration.py:783` | `not in` | `platform_declarations.py` の 2 関数の `getsource` |
| `MitateDB-api/tests/test_application_audit.py:1064-1065` | `not in` | `audit_dispatch.py` / `application_audit.py` の `read_text` |
| `MitateDB-api/tests/test_application_audit.py:1102-1103` | `count ==` | `cell.py` の `read_text` |
| `MitateDB-api/tests/test_application_audit.py:2551-2552` | `in` | `main.py` の `read_text` |
| `r2db-api/tests/test_audit_query.py:2285` | `in` | `ops.py` の `read_text` (変異 fixture の前提) |
| `conformance-tests/test_c05_limit_declaration_agreement.py:841` | `count >= 1` | adapter の `__doc__` (`src/` 外。触れない) |

| 向き | 整理が壊しうること | 触れた変更セットで行う変異 |
|---|---|---|
| `not in` | 残す文が禁止語を含む | 対象範囲に禁止語を含むコメントを 1 行足す → 赤 |
| `in` | コメントの中の同じ文字列が、コード側の消失を隠す | コード側の文字列だけを消した写しで検査する → 赤 |
| `count` | 移したコメントが件数に含まれていた | 対象文字列を含むコメントを 1 行足す → 赤 |

**(c) 行番号 pin。** 両 peer `tests/test_l1_details_vocabulary_ast_scan.py` の `_BACKEND_LAYER_ALLOWLIST` は `(module, lineno)` を持つので、コメント行を消すと赤になる。40b に従い、同じ変更セットで実測により更新する。§4.1 (1) の AST 一致が「行送りだけ」の証拠になる。

## 6. 変更セットの進め方と完了条件

| 変更セット | 内容 | Class |
|---|---|---|
| 0 | 照合ツール (`--base` と `--register`、`MIN_CH_IDS = 0`) と自己テスト、`docs/code-history/README.md` (v0.3) | B |
| 1〜N | 1 セット = 1 peer の 1 module (登録 helper を除く) | B |
| 最後 | 登録 helper のコメント整理。両 peer 同時・同形。ID は `pair.md` | C (§7) |

| 優先 | 対象 | 根拠 |
|---|---|---|
| 1 | R-37 の抽出対象 module (MitateDB `cell.py`、`backend_postgres.py`、r2db `structured.py`、`postgres.py`、`service.py`)。**この中は 10 行以上の塊の行数が多い順** (v0.3) | 抽出前に整理すれば、40c で逐語移動する量が減る。**抽出 WP と同じ変更セットにせず、同じ module を触る抽出 WP と並行しない** |
| 2 | 残りを塊の行数の多い順 | 読み手の負荷の大きい順 |

**R-37 との接続**: R-37 WP-0 の inventory に「コメント整理の要否」列を 1 列足すことに留める。

**手順**: manifest (作業指示書の変更セット節。塊ごとの判定表 (塊 / 判定 / 根拠)、ID の予約) → 40a に従い両 peer の suite (前) → 整理と受け皿 → §4.1 → 行番号 pin → 両 peer の suite (後)、`pytest tools/tests -q` と `--register` → class に応じたレビュー。

| # | 完了条件 | 変異 | 赤になるもの |
|---|---|---|---|
| 1 | コード不変 | コード 1 行の literal を 1 文字変える | §4.1 (1) |
| 2 | 移した塊が逐語で在る | 受け皿の節から 1 文を消す | §4.1 (2) |
| 3 | 文区間の削除だけ | (a) 残した文から否定語を落とす (b) 残した 2 文を並べ替える (c) 1 語足す (d) 残した文の途中の折返し行を 1 行消す | §4.1 (3) |
| 4 | 括弧内の削除が規則どおり | 括弧内の現行正本の参照 (例: SI-) を消す | §4.1 (4) |
| 5 | 経緯を足していない | 追加行に `WP-` を含める | §4.1 (5) |
| 6 | ID の解決と孤児 | コード側 ID を存在しない番号にする / 参照されない節を足す | §4.2 の 1 |
| 7 | ID の全体一意 | 他 peer の companion に同じ番号の節を足す | §4.2 の 2 |
| 8 | docstring 依存の新設なし | `src/` に `__doc__` の読み出しを 1 行足す | §4.2 の 5 |
| 9 | 行番号 pin が実測と一致 | allowlist を更新前の値に戻す | L1 details AST scan |
| 10 | 文字列検査が効いたまま (該当時) | §5 (b) の向きごとの変異 | 該当 test |
| 11 | 登録 helper が同形 (最後の変更セット) | 一方の peer だけ整理する | `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` |
| 12 | 非空虚 (変更セット 1) | `MIN_CH_IDS` を 0 に戻し、全 ID を消す | 監査照合: 定数の値を差分で確認 |
| 13 | suite 集計と経緯トークン数の前後 | 監査照合 (両 peer の集計行とトークン数を manifest に残す) | — |

`_ISOMORPHIC_TARGETS` 集合の増減は起こさない (起きたら Class D であり、本整理を停止する)。

**非目標**: コメントの全面書き直し。英語 / 日本語の統一。formatter の導入。

## 7. 未確定

| # | 論点 | 確認先と時期 |
|---|---|---|
| Q-1 | 登録 helper の変更セット (Class C) の証拠。roadmap §9 の 8 は C に「契約版数の更新」を求めるが、コメントだけの変更で契約版数を据え置けるか | その変更セットの着手時に依頼者へ確認する |
