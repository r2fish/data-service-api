# CONTROL_MAPPING 形式 3.0 設計 v0.4

## 0. 位置づけと台帳の扱い

| 項目 | 内容 |
|---|---|
| 対象 | `security/CONTROL_MAPPING.md` の形式を 2.25 から **3.0** へ替える |
| 台帳 ID | **未起票。起票は `[archive-split]` の merge 後**に監督が行う (`RM` §8)。規模 (S / M / L) は起票時に監督が決める (`docs/work-orders/OPERATING_CONDITIONS.md` §1.13 の 73) |
| 変更クラス | **Class D** (`security/` に触れる。`RM` §9 の 8。宣言前に `tools/change_class.py` で確認する) |
| 実施時期 | `[archive-split]` の merge 後、**単独の変更セット**で行う。終わりの定義・実需の経路・裁定の可視化・archive-split の 4 チャットと重ねない |
| 変更セットの形 | **1 変更セット = 1 commit**。§4 の WP は**作業順**であって commit の単位ではなく、**中間ゲートは走らせない**。完了ゲート (`tools/dev/gate.py`) は最後に 1 回、`tools/tests -q` は根ゲートが集めないので別に走らせ (`tools/dev/gate.py`:50-54)、commit は `tools/dev/finalize.py --tools-tests` で行う (監督のみ) |
| 出所 | 依頼者裁定 2026-09-23 (3 点とも推奨案を採用)。本書 §2・§3 の決定はこの裁定であり、再審議しない |
| 台帳 R-73 | **R-73 (最長 block 長の記録の陳腐化) は本設計の受け入れで閉じる** — 上限が主張単位に移り、記録そのものが消える |
| 本書の役割 | 設計のみ。WP の完了条件↔変異の対応表は作業指示書に置く (`OPERATING_CONDITIONS.md` §1.5 の 40) |

本件は `RM` §0.1 の G-2 / G-3 判定表が `CONTROL_MAPPING` を **未充足**としている行 (`RM`:160 — 版 2.25、SI-07 の r2db-api 節だけテスト名が無い) と同じ問題を、1 節の是正ではなく形式の側で閉じる。

## 1. 実測と診断

### 1.1 実測 (版 2.25、2026-09-23)

| 対象 | 実測 |
|---|---|
| 本体 | 1,430 行 / 192,386 文字 |
| block | **53** (`### ` 単位。既定 48 + 名前付き 5) |
| 主張 | **525** (軸見出し配下の `- ` 行。`- —` の空軸標識 47 を除く)。`## CCR-14` 節の 3 件は軸構造の外にあり **3.0 の対象外** |
| 軸別 | Control **333** 件 120,088 文字 (主張全体の 63%、文字の 70%) / Evidence **119** 件 35,368 文字 / Status **73** 件 15,920 文字 |
| テスト名も file 参照も含まない主張 | **219 件 (42%)** — Control 150 / Status 48 / **Evidence 21** (抽出式は §5 の (E) に逐語で固定する) |
| 前文 | 136 行 10,910 文字。うち **34 行が block 長の再計測ログ** |
| HISTORY | 254,363 バイト |
| 版上げ | 2026-09-21 に 5 回、2026-09-23 に 5 回 |
| 付随する道具 | 登録テスト (`conformance-tests/test_control_mapping_register.py`、`def test_` 56 個)、`tools/restructure_control_mapping.py`・`tools/check_control_mapping_restructure.py`・`tools/check_control_mapping_split.py`・`tools/control_mapping_axes.tsv` とそのテスト 2 ファイル、位置参照検査 (R-88 は登録テスト内、`conformance-tests/test_conformance_docstring_position_refs.py` は R-95) |

主張長の分布 (本書の起草時に実測):

| 軸 | 中央値 | 最長 | 3.0 の上限を超える件数 |
|---|---|---|---|
| Control | 275 | 1,382 | **179 / 333** (上限 250) |
| Evidence | 222 | 1,242 | **45 / 119** (上限 300) |
| Status | 191 | 670 | **19 / 73** (上限 300) |

制御 ID の現況: Control 主張 333 件のうち、ID 形のトークン (`F-`・`C-`・`CCR-`・`D-`・`Z-`・`R-`) を 1 つでも含むのは **59 件**、含まないのは **274 件**。

### 1.2 診断

1. 主張の 7 割 (Control 軸) が散文で、コードの言い直しである。
2. 証明可能性 (G-2) に効くのは **SI → 制御 (施行箇所) → テスト名・`file:line` → 開示された限界**の対応であり、それは主張の 3 割にすぎない。
3. 散文が長いから block 上限に当たり、当たるから named block に分割し (R-50 / R-65)、分割検査器を作り、前文に再計測ログが積もる。前文の 4 分の 1 が長さの話である。
4. 2026-09-14 の表→箇条書き再構成 (R-22) は**形式だけ替えて散文量を替えなかった**ので、9 日で上限に戻った。

## 2. 3.0 の主張文法

### 2.1 軸ごとの形 (依頼者裁定 2026-09-23、決定 1)

| 軸 | 形 | 上限 | 必須 | 禁止 |
|---|---|---|---|---|
| **Control** | **主語 (6 語以内の名詞句)** + 何を bound するか 1 文 + **施行箇所の参照** | **250 文字** (参照込み。字数から参照トークンを除く案は却下 — §7 (f)) | **施行箇所の位置参照**を 1 つ以上 = R-88 の 6 形のいずれかで解決する `path` 又は `path:line`。関数名・クラス名だけの参照は施行箇所と認めない (主語には使ってよい)。既存の `F-NN` / `C-NN` / `CCR-NN` があれば**主語の前**に置く | 限界・未実施の記述 (Status へ)、実装手順の再説明 |
| **Evidence** | 何が観測されたか + その出所 | **300 文字** | **テスト名か `file:line` を 1 つ以上**引く | 引用の無い総称文 (「negative topology and isolation tests」の類) |
| **Status** | 開示された限界・peer 間差 | **300 文字** | — | 制御の再説明、進捗・WP の記録 |

- 上限は **主張単位** (`MAX_CLAIM_LENGTH`、軸ごとの値) とする。**計数単位は先頭の `- ` を含む物理行全体の文字数**である。block 単位の `MAX_BLOCK_LENGTH` と `MAX_NAMED_SUBBLOCKS` の検査は**退役**する。
- named block は**既存の 5 つをそのまま残す**(位置参照が指しているため)。**新規追加は不可**。
- 見出し構造 (`## SI-NN` / `### peer` / `### peer -- topic` / `#### Control|Evidence|Status`)、peer の順、`- —` の空軸標識、`|` 始まり行を置かない規約は**据え置く**。
- 前文の再計測ログ (34 行) は削除する。版上げ記録は **1 行** (版番号、日付、R 番号、触れた block 名のみ) とする。
- **Status 軸の限界文は peer block に残す** (監督裁定 2026-09-23 の確定。Common block へ集約しない)。移動が 0 なので `POSITION_REF_ALLOWLIST` (`conformance-tests/test_control_mapping_register.py`:1616-1634 の (参照文字列, SI, peer) キー) と既存の位置参照を壊さない。
- **`## CCR-14` 節と `## Rule` 節は 3.0 の主張文法の対象外**。軸構造を持たない散文なので、上限も検査 (1)(2)(3) も適用せず、本移行では触らない。
- **分割時の位置参照**: R-88 の shape c (同一**物理行**の先行 backtick パスを継承する形) は行をまたがない (`conformance-tests/test_control_mapping_register.py`:1697)。1 主張を複数に割るときは、**継承していた backtick パスを分割後の各主張に明記して複製する**。
- **既存の参照は形を変えない**。label 形 (`0004:102-113` の類)・peer 相対形・`:line` 継承形をフルパスへ「正規化」しない (shape e / route ii は床すれすれ)。`path:line` に揃えるのは**新規に書く参照だけ**。
- 前文の `CONTROL_MAPPING_HISTORY.md` への backtick 参照 (route i') は**4 件を維持する** (`security/CONTROL_MAPPING.md`:5・:16・:47・:130)。床は他の形と同じく**移行後実測 − 現行 margin** に再固定する (§4 WP-1)。
- 帰結: 参照を引けない Evidence 主張は**最低 21 件**あり、`RM`:160 が指す SI-07 r2db-api 節はそのうちの 1 つにすぎない。実テスト名を引けなければ **Status へ落ちる = 証拠主張の撤回**であり、旧文は HISTORY へ逐語で移す (§3)。

### 2.2 主語と ID の引き方 (監督裁定 2026-09-23)

新しい制御 ID 族は作らない (却下理由は §7)。Control 主張は**主語 + 制御の 1 文 + 施行箇所の参照**で書き、既存の ID があるときだけそれを主語の前に置く。

| 要素 | 規則 |
|---|---|
| 主語 | **6 語以内の名詞句**。実装上の名前 (クラス・関数・ロール・migration ファイル) をそのまま使うのが既定 |
| 既存 ID | `ops verify-declarations` の検査を持つなら **`F-NN`** (両 peer の `ops.py` の登録表が正本。`MitateDB-api/src/mitatedb_api/ops.py:1281-1288` ほか、現在 F-18 まで)。共通 conformance 条件で固定されているなら **`C-NN`** (`conformance-tests/CONDITIONS.md`)。control-plane の条項なら **`CCR-NN`** (`spec/CCR_DISPOSITION.md`)。いずれも**新設しない**。無ければ ID を書かない |
| 施行箇所の参照 | **R-88 の 6 形のいずれかで解決する位置参照** (`path` 又は `path:line`) を 1 つ以上。**必須**。関数名・クラス名は主語に使えるが、これ単独では施行箇所と認めない |
| 書かないもの | `R-NN` (台帳) と `D-N` / `Z-N` (設計文書ローカル) は制御 ID ではない。主語の前に置かない (出所として文中に引くのは可) |
| 数えない参照 | `POSITION_REF_ALLOWLIST` (`conformance-tests/test_control_mapping_register.py`:1616-1634) に載る参照 (`security/CONTROL_MAPPING.md`:626・:740 の peer 間比較) は**施行箇所の参照に数えない** (解決せず許可されている参照であり、その主張の施行箇所を示さない) |

### 2.3 例 (旧→新。旧文は版 2.25 の現物から逐語)

**例 1 — SI-08 / r2db-api / Control (`security/CONTROL_MAPPING.md`:614、240 文字)**

旧:

> - `RequestByteBoundMiddleware` enforces the byte bound in the ASGI receive loop, measured from actual bytes received (not `Content-Length`), before Starlette's parser runs -- the real request path, unexercised on the VPS under real traffic;

新 (Control 1 件 + Status 1 件に分かれる。主語は `RequestByteBoundMiddleware`、施行箇所は `http.py:187`。この制御に既存の F-/C-/CCR- ID は無いので ID は書かない):

> #### Control
> - `RequestByteBoundMiddleware` bounds `request_bytes` in the ASGI receive loop from bytes actually received, not `Content-Length`, before Starlette parses -- `r2db-api/src/r2db_api/http.py:187`.
>
> #### Status
> - **`RequestByteBoundMiddleware` unexercised in production**: the VPS has never run this middleware under real traffic; every measurement is from the test suite.

**例 2 — SI-08 / r2db-api / Evidence (`security/CONTROL_MAPPING.md`:634、1,244 文字)**

旧 (先頭部分を逐語で示す。1 主張が 1 行でテスト名 9 個を抱えている):

> - **R-56, measured on throwaway PostgreSQL clusters**: the effective value a reader connection opened after `0014` carries, the 503 a statement over that ROLE-level bound produces on a pooled reader connection (the scenario shortens the role's own declared value with `ALTER ROLE ... SET` and restores it from `pg_roles.rolconfig`, rather than overriding it per connection), and `0014`'s own re-application -- `r2db-api/tests/test_auditreader_statement_timeout.py::test_reader_connection_effective_statement_timeout_is_5000ms_after_0014` (reads `pg_settings.setting`, the raw ms integer), `::test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection`, `::test_0014_reapplication_is_idempotent`; F-17's own red and green are `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_after_migration_0014`, … (以下 F-17 のテスト名 5 個)

新 (観測 1 つ = 主張 1 つ。いずれも 300 文字以内):

> - reader connection effective `statement_timeout` after `0014`, read from `pg_settings.setting` -- `r2db-api/tests/test_auditreader_statement_timeout.py::test_reader_connection_effective_statement_timeout_is_5000ms_after_0014`.
> - a statement over the ROLE-level bound answers 503 without backend detail and frees the connection -- `::test_slow_audit_query_is_canceled_returns_503_without_backend_detail_and_frees_the_connection`.
> - `0014` re-applies idempotently -- `::test_0014_reapplication_is_idempotent`.
> - F-17 green after `0014`, red when the declared timeout is zero, reset, or overridden per database, and green when the role is absent -- `r2db-api/tests/test_ops_verify_declarations.py::test_verify_declarations_f17_passes_after_migration_0014` ほか 4 件 (各 1 主張)。

「measured on throwaway PostgreSQL clusters」という限界は Status 側の既存主張 (`:639`) が既に持つので重複して書かない。

**例 3 — SI-09 / MitateDB-api / platform upgrade / Status (`security/CONTROL_MAPPING.md`:861、672 文字)**

旧:

> - Section 10's three reviewed subjects stand at these versions -- the 10.6 table at 4, the 10.7 table at 4, the 10.10 procedure at 7 -- and each stays a draft until section 10.8's own row names that same version for it; section 10.8 is the single place that state is read from, and a row naming an earlier version counts as no record at all. As of this version of this file, nothing in section 10 has been run against production, and neither `0014_role_connection_limits_rollout.sql`, the `0004` stages R-54 adds, nor the run/closure behavior R-57 adds has been applied to production either -- every value and every judgment above was measured on a throwaway test cluster.

新 (前半は限界ではなく受理記録なので Evidence へ、後半だけが Status に残る):

> #### Evidence
> - runbook section 10's accepted versions are 10.6 table 4, 10.7 table 4, 10.10 procedure 7, read from the single acceptance row in section 10.8 -- `MitateDB-api/docs/cloud-run-cloud-sql.md:NNN` (行番号は書き換え時に実測する).
>
> #### Status
> - **Production evidence is `absent`**: section 10 has never been run against production, and neither `0014_role_connection_limits_rollout.sql`, the `0004` stages R-54 adds, nor the run/closure behavior R-57 adds is applied there; every value above was measured on a throwaway cluster.

## 3. 更新規約 3.0

依頼者裁定 2026-09-23 (決定 2・3) により、`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5 裁定 4 の更新規約を 3.0 以後は次に緩める。**裁定 4 の行は消さず、本節が上書きする範囲を明示する** (`OPERATING_CONDITIONS.md` §1.8 の 56)。

| 事象 | 2.x (裁定 4) | 3.0 |
|---|---|---|
| 制御の**撤回**、限界の**変更** (安全性の主張が弱くなる方向) | HISTORY へ逐語 | **HISTORY へ逐語** (変更なし) |
| 文言訂正、参照 (テスト名・`file:line`) の更新 | HISTORY へ逐語 | **git の履歴に任せる。HISTORY へ移さない** |
| 3.0 移行で削除する散文 (制御・証拠・限界のどれも主張していない文) | — | **削除する。HISTORY へ逐語で移さない**。前文と HISTORY 冒頭に「版 2.25 の全文は commit `<SHA>` にある」の 1 行を置く |
| 3.0 移行で **Evidence 主張が証拠を引けず Status へ落ちる** (最低 21 件)、又は Control 主張が撤回される | — | **HISTORY へ逐語**。安全性の主張が弱くなる方向であり、1 行目と同じ扱いにする |
| 版上げ記録 | 前文に長文 | **1 行** (版番号、日付、R 番号、触れた block 名) |
| block 長の再計測 | 前文にログを積む | **行わない** (上限は主張単位) |

`<SHA>` は移行直前の main (版 2.25 の最終状態) を指す。HISTORY の見出し集合と 1:1 対応、各節が空でないという既存の契約は 3.0 でも変えない。

その他の据え置き・前提:

- **前文の裁定 4 の逐語文** (`security/CONTROL_MAPPING.md`:13「訂正は現行行を書き換え、旧文は履歴へ移す」) は**残す**。直後に「3.0 以後は `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` §3 が上書きする (2026-09-23)」の 1 文を足す (`OPERATING_CONDITIONS.md` §1.8 の 56)。
- 前文を縮約しても、`CONTROL_MAPPING_HISTORY.md` への backtick 参照は **4 件を維持する** (route i'。床は移行後実測 − 現行 margin に再固定する。§2.1・§4 WP-1)。
- **覆した判断の記録**: 「履歴を捨てる」案は `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md`:521・:543 で一度却下されている。2026-09-23 の依頼者裁定がこれを覆す。根拠は、HISTORY が本体 (192k) を超える **254k** に達し、逐語保存が読み手 0 の面積になったこと。旧の却下行は消さない。
- **`<SHA>` は書き換えの対象**である: `docs/security/public-repository-policy.md`:72-74 の初回公開ゲートで全履歴を書き換えるとき、項目 11 の commit-map で `docs/`・`security/` 中の commit SHA を更新する — この 1 行もその対象に含める。
- **`conformance-tests/CONDITIONS.md`:8 の裁定 4 は据え置く**。2 つの登録簿で更新規約が非対称になることは承知の上で、CONDITIONS.md は上限に当たっていないため今回は揃えない。

## 4. 移行手順 (WP 分割)

**全 WP を 1 commit にまとめる** (§0)。WP は作業順であって commit の単位ではなく、**WP ごとの中間ゲートは走らせない** (WP-1 直後は現物が旧形なので必ず赤になる)。完了ゲートは最後に 1 回、`tools/tests -q` は別に走らせ、commit は `tools/dev/finalize.py --tools-tests`。

WP-2 と WP-3 は**同じファイル** (`security/CONTROL_MAPPING.md`) を書き換えるので**並行にもしない** (`OPERATING_CONDITIONS.md` §1.2 の 16・17)。順序は WP-1 → WP-2 → WP-3 → WP-4 → WP-5 である。どうしても分けるなら唯一安全な切り方は commit A = WP-2 (旧検査のまま緑を保てる)、commit B = WP-1 + WP-3 + WP-5 である。

| WP | 目的 | 触るファイル |
|---|---|---|
| **WP-1** | 登録テストの改訂と道具の退役 | `conformance-tests/test_control_mapping_register.py`、`tools/restructure_control_mapping.py`、`tools/check_control_mapping_restructure.py`、`tools/check_control_mapping_split.py`、`tools/control_mapping_axes.tsv`、`tools/tests/test_restructure_control_mapping.py`、`tools/tests/test_check_control_mapping_split.py`、`tools/dev/README.md` |
| **WP-2** | SI-00〜SI-07 の書き換え | `security/CONTROL_MAPPING.md` |
| **WP-3** | SI-08〜SI-15 の書き換え (`## CCR-14` 節と `## Rule` 節は対象外。§2.1) | `security/CONTROL_MAPPING.md` |
| **WP-4** | 多重集合検査・限界主張の 1 対 1 監査・軸を移した主張を指す参照の洗い出し | scratchpad の script のみ (追跡ファイルは触らない)。結果は本書 §9 に逐語で追記 |
| **WP-5** | 前文・HISTORY 冒頭・**正本文書**の参照更新 (記録文書は触らない。§6.2) | `security/CONTROL_MAPPING.md` (前文)、`security/CONTROL_MAPPING_HISTORY.md` (冒頭 1 行)、`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` (§5 の上書き註)、`docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md`・`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` (退役註 1 行)、`tools/dev/README.md`、`RM` |

### WP-1 の内訳

**外す検査** (現物と合成 fixture の両方):

| 行 | 関数 | 理由 |
|---|---|---|
| :602 | `test_control_mapping_md_named_subblocks_do_not_exceed_max_named_subblocks` | named block の新規追加を禁じるので上限が無意味 |
| :609 | `test_control_mapping_md_blocks_do_not_exceed_the_length_cap` | 上限を主張単位に移す |
| :619 | `test_control_mapping_md_lines_do_not_exceed_the_line_length_cap` | 行長 1,400 は主張上限 300 に包含される (監督裁定 2026-09-23) |
| :633 | `test_control_mapping_md_declares_the_same_max_line_length_as_this_file` | 前文から再計測ログと `MAX_LINE_LENGTH` の宣言ごと消える (「再計測ログ整合の検査」) |
| :901 | `test_fixture_named_subblock_alone_exceeds_the_length_cap` | 上と対 |
| :914 | `test_fixture_four_named_subblocks_exceeds_max_named_subblocks` | 上と対 |

定数 `MAX_BLOCK_LENGTH`・`MAX_NAMED_SUBBLOCKS`・`MAX_LINE_LENGTH` を削り、前文の `MAX_LINE_LENGTH` 宣言も削除する。代わりに `MAX_CLAIM_LENGTH` (軸ごとの値) を置く。

**床の再固定**: 位置参照の形ごとの床 (`conformance-tests/test_control_mapping_register.py`:1640-1649 の `POSITION_REF_SHAPE_*_FLOOR` / `POSITION_REF_ROUTE_*_FLOOR`) は**撤廃しない** (R-88 の設計に触れない)。同ファイル:1637-1639 の元規約どおり **各床 = 移行後の実測 − 現行の margin** (現行 margin をそのまま使う。結果は **≥ 1**) に再固定する。route i' も同じ規則で扱う (前文の参照 4 件は §2.1 のとおり維持)。再固定値と旧値・実測値の対応表は §9 に逐語で残す。`POSITION_REF_ALLOWLIST` (:1616-1634) のキー (参照文字列, SI, peer) は、限界文を peer block に残すので変えない。

**足す検査** (3 件):

| # | 検査 | 想定する変異 |
|---|---|---|
| (1) | 主張長 ≤ `MAX_CLAIM_LENGTH[axis]` (Control **250** / Evidence 300 / Status 300。計数単位は §2.1) | **251 文字**の Control 主張を合成 fixture に置く → 赤 |
| (2) | Control 主張が **R-88 の 6 形のいずれかで解決する位置参照** を 1 つ以上持つ (既存の解決機構を再利用する。単なる backtick トークンは受理しない) | 参照を落とした Control 主張 → 赤。主語が 6 語以内の名詞句かは機械判定せず監査照合 (§5 の 13) |
| (3) | Evidence 主張がテスト名か `file:line` を 1 つ以上持つ | 参照の無い総称文 Evidence 主張 → 赤 |

**据え置く検査**: 形・節順・SI 1:1・history リンク・`|` 始まり行なし・`- —` の扱い・テスト名解決 (R-64 の ast 索引)・位置参照解決 (R-88)。

**退役**: 上表の 4 ファイルとテスト 2 ファイルを削除する。`tools/dev/README.md` の Known gaps 表から該当 2 行を外す (`OPERATING_CONDITIONS.md` §1.12 の 71)。

### WP-2 / WP-3 の書き換え規律

- 1 主張 = 1 観測 / 1 制御。長い主張は分割する (例 2)。
- 既存 ID (`F-NN` / `C-NN` / `CCR-NN`)・テスト名・`file:line`・限界を示す文は**落とさない**。落とす候補が出たら削らずに軸を移す。
- named block は増やさない。既存 5 つの見出し文字列は 1 文字も変えない (他文書がこの見出しを指す。§5 の 7)。
- 主張を分割するときは、継承していた backtick パスを各主張に**明記して複製する** (§2.1)。既存の参照の形は変えない。
- **Evidence が証拠を引けず Status へ落ちた主張と、撤回した Control 主張は HISTORY へ逐語**で移す (§3)。それ以外の削除した散文は HISTORY へ移さない。
- `## CCR-14` 節と `## Rule` 節には触れない。

### WP-4 の検査 (一度きり。`tools/` に道具を増やさない。`OPERATING_CONDITIONS.md` §1.12 の 72)

scratchpad の script (bash 3.2 互換 + `python`) で、旧 (2.25) と新 (3.0) の各 `(SI, peer, block, axis)` について次の多重集合を抽出して比較する。

| 集合 | 抽出 |
|---|---|
| 既存 ID | `F-NN` / `C-NN` / `CCR-NN` / `L{phase}-N` |
| テスト名 | `test_[A-Za-z0-9_]+` |
| `file:line` | R-88 の 6 形に合わせた backtick 付きパス + 行番号 |

条件は **missing = 0**。**「限界を示す文」の多重集合比較は採らない** (全主張を書き換えるので文字列一致が成立せず、常に赤になる)。代わりに次の 2 つを監査照合で行う。

1. **限界主張の 1 対 1 照合**: 母数は「旧 Status 主張 **73 件**全件」+「§2.1 により Status へ移す旧 Control / Evidence 主張」。1 件ごとに新形の**後継主張** (SI, peer, block, 軸, 本文) を evidence-auditor が示し、**後継なし = 0 件**とする。
2. **軸を移した主張を指す参照の洗い出し**: 旧→新の軸対応表を作り、他文書の「軸まで書いた参照」(§6.1 の式 B) と突き合わせ、腐る参照を一覧にする。正本文書の分は WP-5 で直す。

script と出力は本書 §9 に逐語で残す (変異を持たない完了条件のため「監査照合」である)。

## 5. 受け入れ条件

| # | 条件 | 判定 |
|---|---|---|
| 1 | 登録テスト全件 green (新 3 検査を含む) | 完了ゲートの集計行 |
| 2 | 主張長違反 0 (Control 250 / Evidence 300 / Status 300) | 検査 (1) |
| 3 | R-88 の 6 形で解決する位置参照を持たない Control 主張 0 | 検査 (2) |
| 4 | テスト名も file 参照も持たない Evidence 主張 0 | 検査 (3) |
| 5 | 多重集合の `missing = 0` (既存 ID / テスト名 / `file:line` の 3 種のみ) | WP-4 の script。集計行を §9 に逐語 |
| 6 | **限界主張の 1 対 1 照合**: 母数 = 旧 Status 主張 73 件 + Status へ移す旧 Control / Evidence 主張。各件に新形の後継 (SI, peer, block, 軸, 本文) が示され、**後継なし = 0 件** | 監査照合。一覧を §9 に |
| 7 | 位置参照が壊れていない: (i) 登録テストの位置参照検査 (R-88) と `conformance-tests/test_conformance_docstring_position_refs.py` (R-95) が緑、(ii) `##` と `###` の見出し集合が 2.25 と同一 (`git show <SHA>:security/CONTROL_MAPPING.md \| grep -E '^###? '` との diff が空)、(iii) 軸を移した主張を指す参照のうち**正本文書**にあるもの (§6.1) が更新されている | 既存検査 + diff + 監査照合 |
| 8 | 位置参照の形ごとの床が **移行後実測 − 現行 margin** (`conformance-tests/test_control_mapping_register.py`:1637-1639 の元規約。結果は各床 ≥ 1) に再固定され、前文の `CONTROL_MAPPING_HISTORY.md` 参照は 4 件を維持 (route i' も同じ規則で再固定)。再固定値・旧値・実測値の対応表が §9 にある | 登録テスト + §9 |
| 9 | Status へ落ちた Evidence 主張と撤回した Control 主張の旧文が `CONTROL_MAPPING_HISTORY.md` に逐語であり、件数と SI の一覧が §9 にある | 監査照合 |
| 10 | 退役 4 ファイル + テスト 2 ファイルが削除され、**正本からの参照 0** (正本 = `tools/dev/README.md`、`docs/work-orders/OPERATING_CONDITIONS.md`、`CLAUDE.md`、`.github/workflows/*.yml`、テスト、現行の設計文書)。台帳の閉止行・作業指示書・引き継ぎ書は**記録**なので触らない (`OPERATING_CONDITIONS.md` §1.8 の 56・57)。旧設計文書 2 本には退役註 1 行 | `git grep -l` + 監査照合 |
| 11 | 他文書の `CONTROL_MAPPING.md:NNN` 行参照 (24 ファイル、§6.2b) が正本 / 記録に分けて一覧され、**正本の行参照は更新**済み、記録は不変 (`conformance-tests/test_control_mapping_register.py`:1250 は記録。註記 1 行のみ) | 監査照合。一覧を §9 に |
| 12 | 前文: 再計測ログ 0 (`grep -c 'Re-measured' security/CONTROL_MAPPING.md` = 0)、版上げ記録が 1 行、裁定 4 の逐語文 (:13) が残り直後に上書き註が付く | grep + 監査照合 |
| 13 | 監査: Control 主張の**主語が 6 語以内の名詞句**であることを evidence-auditor が block ごとに述べ、その逐語が §9 にある (限界の記述の欠落は条件 6 に一本化) | 監査照合 |
| 14 | 台帳 **R-73 が閉止**されている (最長 block 長の記録が文書からも検査器からも消えたことを台帳行に【追記】) | `RM` の R-73 行 |
| 15 | 完了ゲート (`tools/dev/gate.py`) を**最後に 1 回**走らせて green、`tools/tests -q` も green、commit は `tools/dev/finalize.py --tools-tests` (監督のみ) | 集計行 |
| 16 | 1〜15 のうち変異と対応しない条件は 5・6・7(ii)(iii)・8・9・10・11・12・13・14 だけであり、いずれも「監査照合」と明記されている | 作業指示書の対応表 |

**(E) 抽出式 (逐語で固定する。§1.1 の件数と条件 2・3・4 はこの式で数える)**

- **主張** = `#### Control` / `#### Evidence` / `#### Status` 見出しの配下にある `- ` 行 (`- —` を除く)。`## CCR-14` 節と `## Rule` 節の `- ` 行は数えない (§2.1)。**主張長 = 先頭の `- ` を含む物理行全体の文字数**。
- **file 参照** = 主張行の中の、バッククォートで囲まれた文字列のうち、拡張子 `.py` / `.sql` / `.md` / `.yml` / `.sh` を持つパス (末尾に `:数字` が付いてもよい)。
- **テスト名** = 主張行の中の、バッククォートで囲まれた文字列に現れる `test_[a-z0-9_]+`。
- **施行箇所の位置参照** (条件 3) = 登録テストの R-88 抽出・解決関数が返す位置参照 (6 形のいずれか、`path` 又は `path:line`) で、解決に成功したもの。**単なる backtick トークンは含めない**。
- 「テスト名も file 参照も含まない主張」= 上の 2 つをどちらも持たない主張。版 2.25 での実測は **219 件 (42%)**。

## 6. 影響を受けるファイル (grep 実測、2026-09-23、worktree `cm-form-v3`)

### 6.1 位置参照 (参考実測。受け入れの母数には使わない — §5 の 7)

式 A (`SI-NN / peer` 以降を含む広い網): `git grep -nE 'SI-[0-9]{2} */ *(r2db-api|MitateDB-api|Common)'` (HISTORY を除く) = **145 箇所 / 33 ファイル**。
式 B (軸まで書いた形): 式 A の末尾に「任意の主題 1 段 + `Control` / `Evidence` / `Status` のいずれか」を足し、各要素が backtick で囲まれていてもよいことを許した形 (実行式は WP-4 の script に置く) = **45 箇所 / 16 ファイル**。

式 A の内訳 (件数 ≥ 2 のファイル):

| 件数 | ファイル |
|---|---|
| 17 | `docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md` |
| 15 | `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` |
| 13 | `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md` |
| 13 | `docs/design/ROADMAP_POST_PHASE7_V1.md` |
| 10 | `docs/work-orders/WORK_ORDER_R87_MITATEDB_CATALOG_READ_EXECUTION_MS_V1.md` |
| 8 | `docs/work-orders/WORK_ORDER_R60_R61_CONTROL_MAPPING_WORDING_V1.md` |
| 7 | `docs/work-orders/WORK_ORDER_R62_R2DB_CATALOG_TIMEOUT_V1.md` |
| 7 | `docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md` |
| 6 | `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` |
| 5 | `docs/work-orders/WORK_ORDER_R59_SI09_MITATEDB_BLOCK_SPLIT_V1.md` |
| 5 | `docs/work-orders/WORK_ORDER_R54_DEPROVISION_LIVE_CONNECTIONS_V1.md` |
| 3 | `WORK_ORDER_R72_SI09_STATES_WORDING_V1.md` / `WORK_ORDER_R71_MITATEDB_CATALOG_READ_CANCEL_MAPPING_V1.md` / `WORK_ORDER_R65_SI08_DEFAULT_BLOCK_SPLIT_V1.md` / `WORK_ORDER_R64_CONTROL_MAPPING_TEST_NAME_RESOLUTION_V1.md` (いずれも `docs/work-orders/`) |
| 2 | `security/CONTROL_MAPPING.md` (自己参照) / `docs/work-orders/WORK_ORDER_R70_SI09_RUNBOOK_CLAIM_WORDING_V1.md` / `HANDOVER_20260921_FABLE2.md` / `HANDOVER_20260921_FABLE.md` / `HANDOVER_20260919_FABLE.md` / `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` / `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` / `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` / `docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` |
| 1 | 残り 9 ファイル (`WORK_ORDER_R92_R93_R73_DOC_STALENESS_V1.md`、`WORK_ORDER_R88_CONTROL_MAPPING_POSITION_REFS_V1.md`、`WORK_ORDER_R66_DEPLOY_0013_AND_PROVISION_ROLE_TIMEOUT_V1.md`、`WORK_ORDER_R57_PLATFORM_MIGRATION_RUN_V1.md`、`WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`、`HANDOVER_20260923_FABLE.md`、`HANDOVER_20260921_FABLE3.md`、`HANDOVER_20260920_FABLE3.md`、`HANDOVER_20260920_FABLE.md`) |

**見出しは 1 つも変えない** (§5 の 7 (ii))。ただし**軸間の移動は起きる** (限界は Control / Evidence から Status へ、例 3 のように Status の受理記録は Evidence へ)。したがって**軸まで書いた参照 (式 B) は腐り得る**。

- **正本文書にある分は WP-5 で更新する**: `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` **6 件**、`security/CONTROL_MAPPING.md` 自身の自己参照 **2 件**。
- **記録 (台帳の閉止行・作業指示書・引き継ぎ書) は触らない** (`OPERATING_CONDITIONS.md` §1.8 の 56・57)。
- 旧→新の軸対応表と式 B の突き合わせは WP-4 が行い、結果を §9 に残す。

### 6.2 書き換える / 削除するファイル

| 区分 | ファイル | WP |
|---|---|---|
| 書き換え | `security/CONTROL_MAPPING.md` | WP-2 / WP-3 / WP-5 |
| 書き換え | `conformance-tests/test_control_mapping_register.py` | WP-1 |
| 削除 | `tools/restructure_control_mapping.py` (25,238 B) / `tools/check_control_mapping_restructure.py` (26,131 B) / `tools/check_control_mapping_split.py` (18,832 B) / `tools/control_mapping_axes.tsv` (35,620 B) | WP-1 |
| 削除 | `tools/tests/test_restructure_control_mapping.py` / `tools/tests/test_check_control_mapping_split.py` | WP-1 |
| 註の追記 | `tools/dev/README.md`:58-59 (Known gaps の 2 行を外す)、:73 (登録テストの行を 3.0 に合わせる) | WP-1 / WP-5 |
| 註の追記 | `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5 (裁定 4 の上書き範囲)、`docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md` §4・§5、`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` §5・§6 | WP-5 |
| 1 行追記 | `security/CONTROL_MAPPING_HISTORY.md` 冒頭 | WP-5 |
| 版上げ | `RM` (§8 の台帳行を起票し、閉止を【追記】) | WP-5 |

参考 (§5 の 10 の「正本」判定に使う): 上限定数 (`MAX_BLOCK_LENGTH` / `MAX_NAMED_SUBBLOCKS` / `MAX_LINE_LENGTH` / `MAX_CELL_LENGTH`) を本文で引く文書は 27 ファイル (`git grep -c -E 'MAX_BLOCK_LENGTH|MAX_NAMED_SUBBLOCKS|MAX_LINE_LENGTH|MAX_CELL_LENGTH'`)。うち引き継ぎ書と過去の作業指示書は履歴として据え置き、現行の規約を述べている 4 件 (`security/CONTROL_MAPPING.md`、`conformance-tests/test_control_mapping_register.py`、`docs/design/CONTROL_MAPPING_RESTRUCTURE_V1.md`、`docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md`) だけを WP-1 / WP-5 で直す。

### 6.2b `CONTROL_MAPPING.md:NNN` を引く文書 (行番号が全部ずれる)

`git grep -nE 'CONTROL_MAPPING\.md`?:[0-9]+'` = **24 ファイル**。判定規則: その行が**現行の規約・現行の判断**を述べていれば**正本**なので WP-5 が新しい行番号 (又は `SI-NN / peer / axis` の位置指定) へ直す。**記録** (監査照合記録・閉止記録・作業指示書・引き継ぎ書) は触らず、必要なら訂正註で「版 2.25 の行番号」と明記する。1 件ずつの判定表は WP-5 が作り §9 に残す (§5 の 11)。

| 区分 | ファイル (件数) |
|---|---|
| 正本 (更新する) | **無し** |
| 判定が要る (現行の設計文書。WP-5 が 1 件ずつ判定し §9 に記録) | `docs/design/CODE_COMMENT_PROVENANCE_V1.md` (3)、`docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md` (3)、`docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` (2)、`docs/design/DEPROVISION_FORCED_DROP_V0_1.md` (2)、`docs/design/ROADMAP_POST_PHASE7_V1.md` (2)、`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` (1) |
| 記録 (触らない) | `conformance-tests/test_control_mapping_register.py` (1。:1250 の docstring が引く `security/CONTROL_MAPPING.md:477` は R-88 WP-1 当時の**測定記録**なので行番号は更新せず、WP-5 が「版 2.25 の `:477`」の註記を 1 つ足すだけにする)、旧設計文書 `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` (8) と完了フェーズの監査記録 `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` (5、L7-22 の監査照合)、作業指示書 12 本 (`WORK_ORDER_R91…` 8、`WORK_ORDER_R50…` 8、`WORK_ORDER_R90…` 6、`WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` 5、`WORK_ORDER_R60_R61…` 4、`WORK_ORDER_R87…` 3、`WORK_ORDER_R88…` 2、`WORK_ORDER_R64…` 2、`WORK_ORDER_R62…` 2、`WORK_ORDER_PHASE8…` 2、`WORK_ORDER_R92_R93_R73…` 1、`WORK_ORDER_R52…` 1)、引き継ぎ書 3 本 (`HANDOVER_20260923_FABLE4.md`、`HANDOVER_20260907_FABLE.md`、`HANDOVER_20260906_FABLE.md`) |

### 6.3 触らないもの

`conformance-tests/CONDITIONS.md` とその登録テスト (自前の `MAX_CELL_LENGTH` を持ち、本移行では赤にならない)、両 peer の `src`、`## CCR-14` 節と `## Rule` 節。

`conformance-tests/test_conformance_docstring_position_refs.py` (R-95) は走査対象が `conformance-tests/*.py` だけなのでファイルとしては触らないが、**緑であることは受け入れ条件** (§5 の 7 (i))。ただし同検査は「解決はするが別の文を指す」参照を検出しないと自ら述べている (同ファイル:72-79) ので、§5 の 11 の監査照合で補う。

## 7. 却下した代替案

| 案 | 却下理由 |
|---|---|
| (a) `\|` 表への回帰 | 2026-09-14 (R-22) に表→箇条書きへ替えた経緯がある。問題は表か箇条書きかではなく**散文か参照か**である。登録テストの「`\|` 始まり行を置かない」前提も崩す |
| (b) TSV / YAML を正本にして `.md` を生成 | 生成器と検査器の対を新設し、道具層を増やす (`OPERATING_CONDITIONS.md` §1.12 の 72 に反する)。`tools/control_mapping_axes.tsv` の前例は軸割当の一時的な正本であり、本件の退役対象である |
| (c) 散文を別の非正本文書へ移す | 面積が減らず、読み手 0 の文書が 1 つ増えるだけ |
| (d) 主張は変えず上限だけ上げる | 9 日で上限に戻った実績があり (§1.2 の 3・4)、再発する |
| (e) 制御 ID の新族 `CM-NN` を設けて全 Control 主張に付番する | 登録簿が 1 つ増え (`tools/check_doc_refs.py` の族表と正本ファイル)、ID を持たない 274 件の付番が要る。監督裁定 2026-09-23。代わりに §2.2 の「主語 + 施行箇所の参照」を必須にする |
| (f) 字数から backtick の参照トークンを除いて数える (参照を書く誘因と一致する) | 検査が複雑になり、上限の意味が読み手から見えなくなる。監督裁定 2026-09-23 は代わりに Control の上限を 200 → **250** に上げた |
| (g) Status 軸の限界文を SI ごとの Common block へ集約する | `POSITION_REF_ALLOWLIST` が (参照文字列, SI, peer) で pin されており (`conformance-tests/test_control_mapping_register.py`:1616-1634)、peer が `Common` に変わると当該参照が未解決になり、許可行も死行として赤になる (二重の赤)。監督裁定 2026-09-23 で peer block 据え置きに確定 (§2.1) |

## 8. 依頼者判断待ち

**無し**。v0.1 で両論のまま残していた「Status 軸の限界文を Common に集約するか peer に残すか」は、監督裁定 2026-09-23 で **peer block に残す**に確定した (§2.1。却下理由は §7 (g))。

## 9. 実施記録

### 9.1 実施の枠 (2026-09-24、台帳 R-103、worktree `determined-nightingale-9c442a`、基点 main `94febb3`)

- 作業指示書 `docs/work-orders/WORK_ORDER_CONTROL_MAPPING_FORM_V3.md` v1.0 (訂正註 1〜4)。`<SHA>` = `94febb3`。
- 役割: 実装担当 (Sonnet、WP-1a / WP-1b)、起草担当 (Opus、WP-2 / WP-3 を 2 並列。同一ファイルへの並行書き込みを避けるため各自の SI 範囲を scratchpad の別ファイルに書き、監督が差し込んだ)、監査担当 (Opus、WP-4)、レビュー担当 (Opus、コードレビュー 1 回)。
- 監督裁定 (起草・実施中): (1) 制御を述べていない文 (相互参照・案内・手順の所在) に施行箇所参照を付けて Control に残さない — §3 の「削除する散文」として削除 (WP-2 で 7 行、HISTORY へ移さない)。(2) 旧 :293 (SI-02 r2db-api Evidence、分離ストアの構造説明) は撤回ではなく C-14 の Control へ移す。(3) 証拠を引けず Status へ落ちた Evidence は「**No cited evidence for …**: …; version 2.25's uncited wording is in the history file.」の限界開示の形に揃える。(4) Control が抱えていたテスト名は同 block の Evidence 軸へ移す (§2.1 の軸定義どおり)。

### 9.2 旧 (版 2.25) と新 (3.0) の実測 (`$SP/cm_multiset.py stats`、抽出式は §5 の (E))

```
old (git show 94febb3:security/CONTROL_MAPPING.md): 1430 lines / 192,630 chars
claims=525 blocks=53
Control: n=333 chars=120088 longest=1384 over_cap(250)=181 no_test_or_file=150
Evidence: n=119 chars=35368 longest=1244 over_cap(300)=45 no_test_or_file=21
Status: n=73 chars=15920 longest=672 over_cap(300)=19 no_test_or_file=47
no_test_or_file total = 218
```

```
new (worktree, form 3.0, before the completion gate): 2190 lines / 246,174 chars
claims=1361 blocks=53
Control: n=584 chars=107063 longest=250 over_cap(250)=0 no_test_or_file=8
Evidence: n=642 chars=98118 longest=300 over_cap(300)=0 no_test_or_file=0
Status: n=135 chars=24417 longest=299 over_cap(300)=0 no_test_or_file=104
no_test_or_file total = 112
```

前文: 136 行 / 10,910 文字 → 75 行 / 5,421 文字 (`grep -c 'Re-measured'` = 0、`CONTROL_MAPPING_HISTORY.md` への backtick 参照 4 件)。本体の総文字数は 192,630 → 246,174 (+28%): Control 軸は 120,088 → 107,063 に減り、Evidence 軸が 35,368 → 98,118 に増えた (1 観測 = 1 主張の分割で 119 → 642 件。§2.3 例 2 のとおり)。HISTORY は 13 件 (Status へ落ちた Evidence 主張。撤回した Control 主張は 0 件) を逐語で受けた。

### 9.3 WP-4 多重集合検査 (`$SP/cm_multiset.py compare <old> <new>`、(SI, peer, block) ごとの Counter 比較)

```
ids: old_tokens=83 new_tokens=135 distinct_old=26 distinct_new=26 missing=0 extra=52
tests: old_tokens=755 new_tokens=790 distinct_old=532 distinct_new=545 missing=0 extra=35
files: old_tokens=190 new_tokens=744 distinct_old=114 distinct_new=385 missing=0 extra=554
TOTAL missing=0
```

抽出式 (script 逐語): 既存 ID = `\b(?:F|C|CCR)-\d{2}\b|\bL\d+-\d+\b`、テスト名 = `test_[A-Za-z0-9_]+`、`file:line` = backtick 内の `^([A-Za-z0-9_./\-]+\.(?:py|sql|md|yml|yaml|sh|toml|json|txt|ini|cfg|tsv))(:\d+(?:-\d+)?)?$` と backtick 外の裸の `:\d+(?:-\d+)?`。主張の抽出は §5 の (E) (`#### Control|Evidence|Status` 配下の `- ` 行、`- —` を除き、SI 節外は数えない)。script は scratchpad にのみ置き、`tools/` に増やしていない。

### 9.4 WP-1a / WP-1b の道具の出力 (逐語)

- WP-1a (検査器側の変異、fixture): `pt: 33 passed, 25 deselected in 0.29s` / `mutate: 3 mutations, 3 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged` — M1 `MAX_CLAIM_LENGTH["Control"]` 250→251 → `test_fixture_control_claim_line_length_of_250_is_accepted_and_251_is_rejected` red、M2 解決を常に True → `test_fixture_control_claim_position_reference_requirement` red、M3 Evidence 参照抽出を常に空 → `test_fixture_evidence_claim_reference_requirement` red。
- WP-1b (現物側の変異、`security/CONTROL_MAPPING.md`): `pt: 58 passed in 3.03s` / `mutate: 3 mutations, 3 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged` — 251 文字の Control 主張 / 位置参照を落とした Control 主張 / 参照なしの総称文 Evidence 主張、いずれも expect=red got=red。変異文字列の全文 grep 0 件。

### 9.5 床の再固定 (WP-1b。各床 = 移行後実測 − 現行 margin、規約は `conformance-tests/test_control_mapping_register.py` の床コメント)

| 形/route | 旧実測 | 旧床 | margin | 新実測 | 新床 |
|---|---|---|---|---|---|
| shape a | 3 | 2 | 1 | 399 | 398 |
| shape a' | 2 | 1 | 1 | 19 | 18 |
| shape b | 2 | 1 | 1 | 21 | 20 |
| shape c | 18 | 13 | 5 | 32 | 27 |
| shape d | 168 | 150 | 18 | 280 | 262 |
| shape e | 4 | 3 | 1 | 8 | 7 |
| route i | 112 | 100 | 12 | 656 | 644 |
| route i' | 4 | 3 | 1 | 4 | 3 |
| route ii | 6 | 5 | 1 | 7 | 6 |
| route iii | 69 | 60 | 9 | 82 | 73 |

`POSITION_REF_ALLOWLIST` の 2 行は据え置き (死んだ許可行 0)。

### 9.6 WP-4 監査照合 (evidence-auditor、パケット = scratchpad `wp4-audit.md`。判定の逐語)

- 受入条件 6 (限界主張の 1 対 1 照合): **充足**。母数 105 件 (旧 Status 73 + Status へ移した旧 Control / Evidence 32)、**後継なし 0 件**。弱化 2 件 (W-1 旧 :640 の「(an audit reader whose statements carry no bound of their own)」、W-2 旧 :1188 の minimal event class 5 語の列挙) は監督裁定で復元した (9.7)。
- 受入条件 9 (HISTORY の逐語): **充足**。Form 3.0 追記 13 件、13 件とも旧行と 1 字の差なし (ok 13 / diff 0)。SI 内訳: SI-07・SI-12 各 2、SI-00・02・03・04・08・09・10・11・14 各 1。撤回した Control 主張 0 件。
- 受入条件 7(iii) (軸を移した主張を指す正本参照): **充足**。式 B = 48 行 / 17 ファイル。正本 8 件 (INVENTORY 設計 6 + `CONTROL_MAPPING.md` 自己参照 2) はいずれも腐っていない (指す軸に後継が現存) ので更新しない (作業指示書 訂正註 5)。記録側で実際に軸が動いた 4 行 (R-87:49、R-71:22/:88、R-52:265/:271) は不変。
- 受入条件 13 (Control 主張の主語): 初回 **未充足** — 7 語以上 20 件、bound する主体でない主語 7 件、動詞のない断片 5 件、境界例 12 件 (残り 557 件は充足)。監督裁定で是正し (9.7)、再監査の逐語は 9.8。
- 参考の自測: 見出し集合 diff 空、`- —` と実主張の混在 0、上限違反 0、参照なし Evidence 0、実 credential / 絶対パスの混入 0。

### 9.6b `CONTROL_MAPPING.md:NNN` 行参照の判定 (受入条件 11、設計 §6.2b の「判定が要る」6 文書 15 件)

| ファイル:行 | 判定 | 理由 |
|---|---|---|
| `docs/design/CODE_COMMENT_PROVENANCE_V1.md`:12・:143・:145 | 記録 | 版数ログと訂正註 (2026-09-18 時点の行番号のずれの記録) |
| `docs/design/MITATEDB_PLATFORM_MIGRATION_RUN_V0_1.md`:129・:174・:241 | 記録 | 閉止済み R-57 の設計時分析と受け入れ (:736/:744/:751 は版 2.12〜2.13 の行) |
| `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md`:65・:103 | 記録 | 閉止済み R-52 の設計時分析 (:650/:548 は当時の行) |
| `docs/design/DEPROVISION_FORCED_DROP_V0_1.md`:233・:242 | 記録 | 閉止済み R-54 の監督裁定の記録 (版 2.9 → 2.10) |
| `docs/design/ROADMAP_POST_PHASE7_V1.md`:57 (§0.1.3) | **正本** | 現行の充足判定。本変更セットで再実測して更新 |
| `docs/design/ROADMAP_POST_PHASE7_V1.md`:510 (R-90 行) | 記録 | 閉止行 |
| `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md`:802 | 記録 | L7-22 の閉止記録 |
| `conformance-tests/test_control_mapping_register.py` (docstring の `:477`) | 記録 | R-88 WP-1 当時の測定記録。註記 1 行「(version 2.25's `:477`; the form 3.0 rewrite moved every line)」を足した |

正本で更新した行参照は台帳 §0.1.3 の 1 件のみ。他の 18 ファイル (作業指示書 12・引き継ぎ書 3・旧設計文書・完了フェーズの監査記録・本設計) は記録として不変。

### 9.7 監査・レビュー後の是正 (監督裁定 2026-09-24)

- 是正担当 (drafter、現物を直接編集): 主語 7 語以上 20/20 件、主体でない主語 7 件 + レビュー 3a の :690/:691 (限界を Status へ)、断片 5/5 件、境界例 12 件中 8 件、W-1 (逐語復元)・W-2 (2 主張に分割し 5 区分を逐語復元。主張化のため `That minimal event class is` と最後の項の前の `and` が加わる)、O-1 参照単位 43 件中 33 件を施行する行へ付け替え (10 件は class 全体が施行主体)、`.md` だけを引く Control 26 件のうち 5 件を code/migration へ (21 件 = SI-09 platform upgrade の運用手順 17 + 配備・再起動・再適用順 4 は手順そのものが制御として残置)。
- 再監査 (`$SP/wp4-audit-2.md`): 条件 13 **充足** (53 block、未充足 0)、条件 6 **充足** (母数 107、後継なし 0、削除された Status 主張 0)、条件 9 **充足** (13 件不変、ok 13 / diff 0)、W-1 逐語、W-2 実質充足。観察 N-1〜N-4 と :1301 は監督が直した: N-1 MitateDB の `mitatedbsvc_provision` の `statement_timeout` 限界を r2db と対称に Status へ、N-2 配備の既定に依存する 3 主張 (Cloud Run の IAM 分離・環境変数の不在・`0014` 後の再起動) を「配備の前提」として Status へ、N-3 class 宣言行より範囲の広い 3 主張の参照を module path (行なし) に、N-4 動詞のない 2 主張を 1 文に、:1301 の主語を 6 語以内に。
- 最終実測 (`cm_multiset.py stats`): `claims=1363 blocks=53` / `Control: n=577 chars=106271 longest=250 over_cap(250)=0 no_test_or_file=8` / `Evidence: n=642 chars=98118 longest=300 over_cap(300)=0 no_test_or_file=0` / `Status: n=144 chars=26534 longest=299 over_cap(300)=0 no_test_or_file=105`。本体 2,192 行 / 247,501 字。多重集合 `TOTAL missing=0` (ids 83 → 135、tests 755 → 790、files 190 → 753 tokens)。見出し集合 diff 空。登録テスト + R-95 検査 `pt: 83 passed`。
- 床の最終再固定 (是正後の実測 − 現行 margin。9.5 の表を上書きする): a 400 → 399、a' 19 → 18、b 21 → 20、c 32 → 27、d 288 → 270、e 8 → 7、i 662 → 650、i' 4 → 3、ii 7 → 6、iii 85 → 76。
- コードレビュー (Opus、1 回、`$SP/review-wp1.log`) 7 件: 1 §9 未記入 → 本節、2 床コメントの基点 → 「version 3.0 (the R-103 change set)」、3 `.md` だけの施行箇所参照 → (a) 現物 (b) Known gaps 項目、4 (E) と部分一致の差 (実測 0 件) → docstring、5 主張行以外の行長 → Known gaps 項目、6 空振り assertion 2 つ → 削除、7 Known gaps 項目 3 の caught by → 床コメントを指す形。裁定表は引き継ぎ書。

### 9.8 完了ゲートと commit

- 完了ゲート (`tools/dev/gate.py -C .claude/worktrees/determined-nightingale-9c442a --label cm-form-v3`): `gate: 4018 passed, 2 subtests passed in 504.40s (0:08:24)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0` (2026-09-24, label cm-form-v3)
- `tools/tests -q` (`tools/dev/pt.py`): `pt: 588 passed in 73.71s (0:01:13)`
- commit: `tools/dev/finalize.py --tools-tests` (監督)。版 2.25 の全文は commit `94febb3`。

## 改版履歴

| 版 | 日付 | 変更 | 出所 |
|---|---|---|---|
| **v0.4** | 2026-09-24 | §9 実施記録 (R-103 の実施: 実測、多重集合検査、監査・レビューの逐語、床の再固定表、行参照の判定表、完了ゲート)。§0〜§8 は不変 (§6.1 の「正本 8 件を WP-5 で更新する」は実測で腐りなしと判明、作業指示書 訂正註 5) | 実施 2026-09-24、作業指示書 `docs/work-orders/WORK_ORDER_CONTROL_MAPPING_FORM_V3.md` |
| **v0.3** | 2026-09-23 | 再確認で残った矛盾 7 件を是正: §2.1 の計数単位 (先頭 `- ` 込みの物理行) と route i' の一本化、§2.2 に allowlist 参照を数えない行、§3 の route i' 記述、§4 WP-1 の検査 (1) を 250/251 に訂正・床の再固定を「実測 − 現行 margin」に、§5 の (E)・条件 8・11・13、§6.2b で `test_control_mapping_register.py`:1250 を記録区分へ | 設計レビュー再確認 2026-09-23 + 監督裁定 |
| **v0.2** | 2026-09-23 | 設計レビュー指摘 15 件 + 枠への疑義 3 件への監督裁定を反映: §0 の 1 commit 規律、§1.1 の 525 / 219 / Status 73、§2.1 の Control 上限 250・施行箇所の定義・分割時の参照複製・既存参照の形の据え置き・route i' 維持・CCR-14 対象外・Status は peer block 据え置き・Evidence 21 件の帰結、§2.2、§2.3 例 3 を英語化、§3 に HISTORY 逐語の行と 4 つの前提、§4 の WP 表・床の再固定・検査 (2)・WP-2/3 規律・WP-4 の 1 対 1 照合、§5 を 16 条件に再構成 + (E)、§6.1 の結論・§6.2b の 24 ファイル、§7 に (f)(g)、§8 を空に | 設計レビュー 2026-09-23 + 監督裁定 |
| v0.1 | 2026-09-23 | 初版。形式 3.0 の主張文法、更新規約 3.0、WP-1〜WP-5、受け入れ条件 14 件、影響ファイルの実測 | 依頼者裁定 2026-09-23 (決定 1〜6)、`RM`:160、`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` §5 裁定 4 |
| v0.1 | 2026-09-23 | 起草時の監督裁定 (疑義 9 件) を反映: §0 に R-73 閉止、§1.1 の block 53・抽出式による 221 件・位置参照行の削除、§2.1/§2.2 の Control 文法 (主語 + 施行箇所の参照、新 ID 族なし)、§2.3 例 1、§4 の `MAX_LINE_LENGTH` 退役、§5 の (E) 抽出式・条件 6/11/13/14、§7 に (e)、§8 を 1 件に縮小 | 監督裁定 2026-09-23 |
