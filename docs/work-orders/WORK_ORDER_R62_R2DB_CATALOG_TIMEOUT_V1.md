# 作業指示書 — R-62 r2db-api の `PostgresCell.catalog` に取引ごとの文の上限を通す (`CONTROL_MAPPING` 版 2.15)

## 0. 版数・位置づけ

- **v1.1 (2026-09-21)。** v1.0 からの変更: **設計レビュー 1 の裁定 R1-1〜R1-11 を反映し、D-1・D-2 の `deadline` / `clock` を撤回した** (§1.7)。完了条件は **15 件**、変異は **8 件**になった。**直下の v1.0 の行と、覆した D-1・D-2・D-3・D-5・§1.4 の本文は消さずに残し、覆した根拠と日付を各行に置いた** (§1.8 の 56)。
- **v1.0 (2026-09-21)。** 基点 main `24df696`。台帳は `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の **R-62** 行 (`RM`:465)。
- **変更クラスは D** (`tools/change_class.py` の実測: WP-1 + WP-2 の 10 パスで `class=D`、`conformance_required=true`。`security/` の 2 ファイルが D、`r2db-api/src`・`r2db-api/tests` の 8 ファイルが B。§1.6 の J-1・J-2 で足した 3 ファイルも B なので `class=D` は変わらない — 着手時に全パスで実測し直す)。台帳の起票文は「B の見込み」と書いているが、**実測は D** である — 理由は §1.2 の D-0。**契約は 1.8.0 のまま**で `spec/` を触らない。`spec/`・`conformance-tests/`・migration・runbook・`MitateDB-api/src` の差分は **0** (`MitateDB-api/tests` は J-1 の 1 ファイルだけ、`MitateDB-api/migrations` は変異での一時編集だけ)。
- **D が求める依頼者裁定の逐語記録**は依頼者指示 2026-09-19 の委任 (引き継ぎ書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2 に逐語) であり、本件の決定はその委任の下で**監督が推奨として下した**。完了後に引き継ぎ書で**事後報告**する (R-57・R-59・R-60/R-61 と同じ扱い)。版付きの security-contract 決定に当たるのは `security/CONTROL_MAPPING.md` の**版 2.15** である。
- **設計文書は新しく起こさない。** 枠 (D-0〜D-9 と却下案) は §1.2 にあり、これが監督の確定した決定である。方法の正本は `security/CONTROL_MAPPING.md` 冒頭の **Update convention** (:11-:23) と `security/CONTROL_MAPPING_HISTORY.md` 冒頭 (見出しは SI の ID のみ)。先行する形は `docs/work-orders/WORK_ORDER_R60_R61_CONTROL_MAPPING_WORDING_V1.md` と `docs/work-orders/WORK_ORDER_R68_PROVENANCE_SAME_CHANGESET_REWORD_V1.md`。
- 規律は `docs/work-orders/OPERATING_CONDITIONS.md` に従う (**commit・merge・`gate.py`・`finalize.py` は監督のみ**、道具は `tools/dev/`)。本書は条項を複製せず番号で指す。**下請けの Agent を起動しない** (§1.7 の 47)。**疑義は実装せず報告に書く** (§1.5 の 37)。
- **WP-1 (コードとテスト) と WP-2 (`security/`) は 1 つのコミットに入れる** — 申告と実挙動は単一コミットである (§1.1 の 11)。したがって**並行 WP は無く**、触るファイルの重なりの表は置かない (§1.2 の 16・17 は該当しない)。**WP-2 の確定文は WP-1 の実測 (テスト名・行番号・ブロック長) の後に監督が確定する。** §3.2 は確定文の**形**と**埋める穴**だけを与える。

## 1. 枠

### 1.1 問題設定と守るべき条件

**本書が述べるのは「client が到達する 4 経路」だけである** (R1-11。「この cell が開くすべての取引」とは書かない — `PostgresCell.verify_row_level_security` (`r2db-api/src/r2db_api/postgres.py`:2183) も上限の無い取引を開くが、`src` に呼び出し元が無く ops / テストからしか呼ばれない。本件の射程外)。

`r2db-api` の `PostgresCell` が client から到達できる取引を開く 4 経路 (`query`・`transact`・`apply_schema`・`catalog`) のうち、`catalog` だけが `_set_timeouts` を通らない。r2db-api は application の runtime / developer role に role 水準の timeout を置かない方針なので (R-56 設計 `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` D-2)、**client が到達できるデータ面の操作のうちこの 1 経路だけが実行時間の上限を持たない**。

守る条件:

- (a) 上限を持つことが**呼び出し側の正しさに依らない**こと。
- (b) 契約 1.8.0 を動かさないこと (`spec/`・`conformance-tests/` の差分 0)。
- (c) 契約の error 語彙の外の結果を作らないこと。
- (d) 既存の `.catalog()` 直呼び (`r2db-api/tests` に 100 箇所) を機械的に書き換えないこと。

### 1.2 決定 (監督確定 2026-09-21。D-0〜D-9)

- **D-0 (変更クラス)** 台帳は B の見込みとしていたが、**D** である: `security/CONTROL_MAPPING.md`:592 (SI-08 / r2db-api / default block) が「`PostgresCell.catalog` は `_set_timeouts` を通らず、その 1 経路は自前の文の上限を持たない -- an open ledger item」と現在形で開示しており、直すとこの主張が偽になる。コードと同じ変更セットで現行行を書き換え、旧文を履歴へ移し、版を **2.15** にする。
- **D-1** `PostgresCell.catalog` は取引を開いた直後に必ず `_set_timeouts` を通す。**上限を持つことが呼び出し側に依らない形**にする: signature は `catalog(self, limits: ResourceLimits | None = None, *, deadline: float | None = None, clock: Callable[[], float] | None = None)`。`limits` が無ければ `ResourceLimits()` (既定 `execution_ms` = 5000) を使う。値は既存の `_timeout_ms(limits, deadline, clock)` で求める。他の 3 操作と同じく、取引に入る前に `limits.check_deadline(deadline, clock)` を行う (両方が在るとき)。
  - **【裁定 2026-09-21 (設計レビュー 1、R1-2)。上の行は消さない】** **`catalog` は `deadline` と `clock` を取らない。** signature は **`catalog(self, limits: ResourceLimits | None = None)`**、上限は **`_timeout_ms(limits, None, None)`** (= `limits.execution_ms`) を取引の開始から掛ける。**取引前の `check_deadline` は行わない。** 根拠: (i) 守る性質は「取引が上限を持つこと」であり、catalog は budget も多段の処理も持たない。(ii) C-05 の `hold_in_flight` は cell の `catalog` を差し替えて停止させるので、`DataService` で作った deadline は**停止を跨ぐ** — 保持が `execution_ms` を超えると port 契約「解放後、保持していた n 個はすべて正常に完了する」に反して間欠的に赤くなる (§1.3 の (6))。(iii) シンプルであること。
- **D-2** `DataService.catalog` は `self.limits` と `deadline = self._clock() + self.limits.execution_ms / 1000`、`clock=self._clock` を渡す (budget による絞り込みは無い — 契約が catalog に budget を定めていない。`spec/CCR_DISPOSITION.md`:202)。
  - **【裁定 2026-09-21 (設計レビュー 1、R1-2)。上の行は消さない】** **`DataService.catalog` は `self.limits` だけを渡す** (`deadline` / `clock` は渡さない)。budget を取らない点は変わらない。
- **D-3** `StorageBackend.catalog` の protocol、`structured.py`、`_RefusingPlatformUpgradeCell`、テストの stub は同じ signature に揃える (DB を使わない実装は引数を受けて無視する。deadline の確認だけは他の操作の流儀に合わせるかを起草時に現物で見て、合わせる/合わせないを理由つきで書く → **§1.4**)。既存のテストの `.catalog()` 直呼びは変えない。
  - **【裁定 2026-09-21 (設計レビュー 1、R1-2)。上の行は消さない】** deadline を取らないので**期限の確認は置かない**。`StorageBackend.catalog` の protocol・`structured.ApplicationCell.catalog`・テストの stub は **`limits` を受けて無視する**形に揃える。`_RefusingPlatformUpgradeCell.catalog` は既に `(*args, **kwargs)` なので変更不要 (§1.3 の (9))。**§1.4 の判断 (deadline の確認を DB を使わない実装にも置く) は撤回した。**
- **D-4** timeout に掛かったときの client への結果は、他の 3 操作が `QueryCanceled` / lock timeout をどう写像しているかに揃える (catalog の取引に同じ写像が掛かっているかを現物で確かめ、掛かっていなければ同じ写像を通す → **§1.3 の (2)**)。契約の error 語彙に無い結果を作らない。
- **D-5** テスト (`r2db-api/tests`、実 PostgreSQL): (a) `catalog` の取引の中で `statement_timeout` と `lock_timeout` が `limits.execution_ms` から求めた値になっている (発行された SQL ではなく、取引の中の `SHOW` / `current_setting` か、実際に遅い catalog 読みが打ち切られることで観測する。代理指標を使わない)、(b) `limits` を渡さない直呼びでも上限が掛かる、(c) deadline が残り時間で上限を絞る、(d) `SET LOCAL` が取引の外へ漏れない (次の取引で既定に戻る)、(e) `DataService.catalog` が `self.limits` と deadline を渡す、(f) timeout の結果の写像 (D-4)。完了条件 1 項目 = 変異 1 つ (expect=red)。
  - **【裁定 2026-09-21 (設計レビュー 1、R1-2・R1-4・R1-7・R1-8)。上の行は消さない】** **(c) は削る** (deadline を取らないため)。**(a) の観測方法を確定する** (R1-4): テスト側で `_load_catalog` を差し替え、**同じ接続・同じ取引の中で** (i) `pg_sleep` を走らせて実際に打ち切らせ、(ii) timeout の値は `pg_settings.setting` の**生 ms** を読む (`SHOW` は使わない)。**(f) は `psycopg.errors.LockNotAvailable` を送り込んで写像だけを見る**経路も併せて観測する (R1-4)。**(d) は同じ接続を固定して観測する** (pool を 1 接続に構成するか、同じ接続オブジェクトであることを確かめる。R1-8)。**deny の監査事象** (`operation="catalog"`、`reason_code=LIMIT_EXCEEDED`) の観測を 1 件足す (R1-7)。MitateDB 側は「role 水準の 5000ms が catalog の経路を覆う」ことを固定する既存テストが在るかを見て、無ければ 1 件足すかを起草時に提案する (足す場合も MitateDB のコードは変えない → **§1.3 の (3)**、**§5 の (5-1)**)。
- **D-6** `security/CONTROL_MAPPING.md`:592 の訂正 (版 2.15、Update convention、旧文は逐語で `CONTROL_MAPPING_HISTORY.md` の `## SI-08` へ): 「disclosed difference between the peers」の主張は残す (r2db は role 水準の timeout を application role に置かず、取引ごとの `SET LOCAL` に依る) が、末尾の「`PostgresCell.catalog` … carries no statement bound … an open ledger item」を、catalog も `_set_timeouts` を通ることと、それを固定するテスト名に替える。**確定文は実装とテスト名が決まった後に書く** (主張は実測の後 — §1.5 の 34)。SI-08 / r2db-api / default block は残り 2,272 字 (上限 15,200) なので、ブロック長を実測して上限内に収める。preamble の再実測文と Version 行は R-60/R-61 の先例どおり。行番号参照 (`:803-807`、`:2282-2297`) はコードの変更でずれるので実測で直す。
- **D-7** R-56 の設計メモ `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` の D-2 の経路表・§10 の 1 には、行を消さず【追記】で R-62 の解消を記す (**監督が記録のコミットで行う。WP の範囲外**)。
- **D-8** 性能: catalog 1 回につき `SET LOCAL` が 2 文増える。`tools/perf_baseline.py` が catalog を測っているかを起草時に確かめ、測っていれば完了ゲートの後に監督が基準値と同じ引数で差分を取る (§1.3 の 27)。測っていなければその旨を書く → **§1.3 の (4)**。
- **D-9** コメント: 新しい・変えた関数には docstring を書く (経緯語を入れない)。`catalog` の周辺に CH-ID つきの塊が在って言い換えが要るなら、R-68 の経路 (受け皿に `### correction` を追記、`check_comment_provenance.py --base 24df696 <path>` が FAIL 行 0・exit 0) を使う。コードを変える差分では §4.1 (1) が出るので、合格条件は「(1) 以外が 0 行」。

**却下** (監督確定、蒸し返さない):

- r2db の application role に role 水準の timeout を置く (migration) — R-56 設計 D-2 と同設計の監督裁定 2 で「コードで直す」と決定済み。
- `limits` を必須引数にする — 上限の有無が呼び出し側の正しさに依る形になり、約 100 箇所のテストの直呼びを機械的に書き換えるだけの差分が増える。
- catalog に契約の `budget` を足す — 契約変更であり本件の範囲外。

### 1.3 起草時の実測 (基点 `24df696` の現物。起草者が実施)

| # | 観測 | 出所 |
|---|---|---|
| (1) | `catalog` は `self._runtime.connection()` の取引を開いて `_load_catalog` を呼ぶだけで、`_set_timeouts` を呼ばない。他の 3 経路は取引に入った直後に呼ぶ | `r2db-api/src/r2db_api/postgres.py`:803-807 / :1175・:1284・:1753 |
| (2) | **D-4 の答: catalog の取引には例外の写像が 1 つも掛かっていない。** 他の 3 経路は `except psycopg.errors.QueryCanceled` と `except psycopg.errors.LockNotAvailable` を `LIMIT_EXCEEDED` (413、`details` = `resource`/`limit_class` = `execution_ms`、`limit` = `limits.execution_ms`) に写す。catalog には `try` が無いので、今日 `QueryCanceled` が起きれば `_endpoint` の `except Exception` に落ちて一律 503 になる | 同 :1204-1206・:1381-1383・:2065-2067、`r2db-api/src/r2db_api/http.py`:315-316 |
| (3) | **D-5 の答 (MitateDB 側): 「role 水準の 5000ms が catalog の経路を覆う」ことを固定する既存テストは無い。** `0013_role_statement_timeouts.sql` は runtime / developer role にも 5000ms を置き、`MitateDB-api/tests` はその適用 (provision harness) と **auditreader** の経路 (`test_audit_query_reader_errors.py`:162-189) を固定しているが、catalog の経路 (`ApplicationCell.catalog` → `all_field_types()` / `all_field_constraints()`) で有効値を読むテストは 1 件も無い | `MitateDB-api/migrations/0013_role_statement_timeouts.sql`:1-7、`MitateDB-api/tests/control_plane_harness.py`:144-147・:193、`MitateDB-api/tests/test_audit_query_reader_errors.py`:127-189 |
| (4) | **D-8 の答: `tools/perf_baseline.py` は catalog を測っていない。** 測るのは `query` (`select_eq`) / `mutate` (`insert`) / `batch`、加えて宣言した plug だけ `cross_entity` である。したがって**本件に性能差分の対象は無い** (§1.3 の 27 の対象外)。op 語彙を増やすのは本書の範囲外 | `tools/perf_baseline.py`:37-45、`PERF-README`:115・:123-124 |
| (5) | **行番号 pin は 1 件ある。** `_BACKEND_LAYER_ALLOWLIST` の `("postgres.py", 1439)` は `postgres.py` の `catalog` (:803) より下の行を指すので、catalog が行数を増やすと必ずずれる。allowlist と実在の bare site は `test_allowlist_entries_match_real_bare_call_sites` が両方向で照合する | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:149・:498-518 |
| (6) | **conformance の plug は `catalog` の signature に依らない。** 共通 suite は `.catalog(` を 1 件も呼ばず、port は `catalog_document(session)` である。r2db の 2 plug は `hold_in_flight` の停止点として cell の `catalog` を差し替えるが、差し替える proxy は `def _stalled(*args, **kwargs)` で原本へそのまま委譲するので、**signature は通る**。ただし**停止は原本を呼ぶ前に起きる**ので、`DataService` が作った期限は停止を跨ぐ — **だから deadline は渡さない** (R1-2。port 契約は「解放後、保持していた n 個はすべて正常に完了する」)。この 2 plug の `_ISOLATED_APPLICATION_LIMITS` は `execution_ms=5_000` である | `conformance-tests/adapter.py`:2229、`r2db-api/conformance/conformance_adapter_r2db.py`:160・:237-242・:873-875、`同 _http.py`:947・:2419-2427 |
| (7) | 同型性 pin の対象外: `_ISOMORPHIC_TARGETS` に `postgres.py` / `catalog` / `_set_timeouts` は 1 件も無い (R-56 が足したのは `_f17_message` と `check_auditreader_statement_timeout` だけ) | `r2db-api/tests/test_audit_query.py`:2990-3242 |
| (8) | `LIMIT_EXCEEDED` の call site 数は下限 (`>= 15`、実測基準 19) でしか固定されていないので、2 箇所増えても pin は動かない | `r2db-api/tests/test_limit_class_vocabulary.py`:154-155 |
| (9) | `_RefusingPlatformUpgradeCell.catalog` は既に `(*args, **kwargs)` で受ける (常に `_refuse()`)。**D-3 のうちこの 1 件は変更不要** | `r2db-api/src/r2db_api/postgres.py`:2341-2342 |
| (10) | `security/CONTROL_MAPPING.md` の SI-08 / r2db-api / default block は **12,928 字** (上限 15,200、残り **2,272**)。文書の最長ブロックは SI-08 / MitateDB-api / default の **13,023**。`:592` は 570 字、文書の最長物理行は 1,384 (上限 1,400)。`## SI-08` の履歴節は `security/CONTROL_MAPPING_HISTORY.md`:131 に始まり :200 の `---` で終わる | 実測 (`conformance-tests/test_control_mapping_register.py` の `_split_sections` / `_iter_section_subblocks` / `_subblock_block_text` を直接呼んだ値) |
| (11) | 旧 `:592` を引いている他文書は**すべて過去形の記録**である (R-56 の設計メモと作業指示書、台帳 R-62 行、引き継ぎ書)。**同じ変更セットに入る他文書は 0 件** (D-7 の【追記】は監督の記録コミット) | `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md`:85・:90・:194・:242、`docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md`:272・:374・:529、`RM`:465 |

### 1.4 D-3 の判断 (deadline の確認を DB を使わない実装にも置く) — **【撤回 2026-09-21 (設計レビュー 1、R1-2)。本文は消さない】**

**撤回の理由**: R1-2 で `catalog` が `deadline` / `clock` を取らないと決めたので、確認する対象が無くなった。`structured.ApplicationCell.catalog` は `limits` を受けて無視する。以下は撤回前の判断である。

**合わせる。** 理由は現物である: `structured.ApplicationCell` の `query` (`r2db-api/src/r2db_api/structured.py`:875-876)・`transact` (:1057)・`apply_schema` (:1553) は、いずれも本体の先頭で `if deadline is not None and clock is not None: limits.check_deadline(deadline, clock)` を行う。これがこの cell の流儀であり、`catalog` だけ確認しない形にすると「同じ face を持つ 2 つの実装が、同じ引数を受けて片方だけ期限を見る」差が新しく生まれる。**両方が `None` のときは何もしない**ので、既存の 100 箇所の `.catalog()` 直呼びの挙動は 1 件も変わらない。

### 1.5 未確定

- **無し。**

### 1.6 監督裁定 (2026-09-21、起草時の報告への回答。全件採用し、本文へ反映した)

本書はまだ実装に渡っていない v1.0 の確定前なので、裁定は本文へ反映してある (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 57 が言う「実装に渡った後の訂正註」の場面ではない。R-60/R-61 の先例と同じ扱い)。

- **J-1 (MitateDB のテスト 1 件。採用)** §1.3 の (3) の提案を採る。**MitateDB-api に「application の runtime / developer role の role 水準 `statement_timeout` が catalog の経路を覆う」ことを固定するテストを 1 件足す** — 実 PostgreSQL、**catalog の経路の接続**で観測する。**MitateDB の製品コードは変えない。** WP-1 の触ってよいパスに `MitateDB-api/tests` のファイルを 1 つ足し (§2.1)、完了条件 14 と変異 **M8** を 1 組立てる (v1.1 で番号を振り直した。R1-3 により観測は **developer 接続**に限る)。変異は fixture 側ではなく**実物の性質**を壊す形にする (`0013_role_statement_timeouts.sql` の該当 `ALTER ROLE` を落とす。migration への変異は `mutate.py` が復元するので可)。
- **J-2 (plug のコメント 2 件。採用)** §1.3 の (6) で古くなる 2 つのコメントを**同じ変更セットで事実に合わせて直す** (**コメントだけ**。挙動・テストは変えない)。触ってよいパスに 2 ファイルを足し (§2.1)、完了条件 15 は**監査照合**とする (v1.1 で番号を振り直し、R1-5 で docstring 1 箇所を足した) (新しい文が実装と合うこと、`git diff` がコメント行だけであること)。変更クラスは既に D で、root ゲートが覆う。**実測の訂正**: この 2 ファイルは `conformance-tests/` 配下ではなく peer 自身の plug (`r2db-api/conformance/`) である。共通 suite (`conformance-tests/`) の差分は 0 のまま。
- **J-3 (完了条件 12。現状維持)** 「(2) が出たら止めて報告」の形でよい。**docstring は書く** (D-9)。
- **J-4 (`python3` への置き換え。現状維持)** §3.5 のとおりでよい。
- **J-1 の連鎖**: MitateDB 側の断言の証拠として、この新しいテスト名を WP-2 の確定文の穴に足す (§3.2 の穴 D)。

### 1.7 設計レビュー 1 の反映 (2026-09-21、監督裁定として全件採用。R1-1〜R1-11)

本書はまだ実装に渡っていない (v1.0 の確定前) ので、裁定は本文へ反映してある (§1.6 と同じ扱い)。**覆した判定の行は消さず、覆した根拠と日付をその行に置き、版を v1.1 に上げた** (§1.8 の 56)。

| # | 指摘 | 反映 |
|---|---|---|
| R1-1 | deadline を渡すと、`hold_in_flight` の停止を跨いだ残り時間で上限が 1ms まで絞られうる | **R1-2 で deadline 自体を撤回したので、対象ごと消えた** |
| R1-2 | **(監督裁定。D-1・D-2 を改める)** `catalog` は `deadline` / `clock` を取らない。signature は `catalog(self, limits: ResourceLimits \| None = None)`、上限は `_timeout_ms(limits, None, None)` = `limits.execution_ms` を取引の開始から掛ける。`DataService.catalog` は `self.limits` だけを渡す | D-1・D-2・D-3・D-5 に裁定行を追記 (本文は残す)、§1.4 を撤回、§2.2 の完了条件と §2.3 の変異を振り直した (取引前の `check_deadline`、deadline による絞り込み、DB を使わない実装の期限確認、それらの変異を**削除**)。§1.3 の (6) に停止を跨ぐ旨を追記 |
| R1-3 | J-1 のテストは「runtime / developer」と広く書くと、観測しない role まで主張することになる | §2.2 の完了条件 14 と §3.2 の穴 D を **developer 接続** (catalog の経路が実際に使う接続) に限定した |
| R1-4 | 観測方法が「または」で開いており、実装担当ごとに強さが変わる | §2.2 の完了条件 1・4 に確定した観測方法を書いた: `_load_catalog` をテスト側で差し替え、(i) 同じ接続・同じ取引で `pg_sleep` を走らせて実際に打ち切らせる、(ii) `psycopg.errors.LockNotAvailable` を送り込んで写像だけを見る。値は取引の中で `pg_settings.setting` の**生 ms** を読む (`SHOW` は使わない) |
| R1-5 | J-2 の対象が 2 箇所では足りない (`_hold_in_flight_via_stalled_cell_method` の docstring が `self._cells[app_id].catalog()` を逐語で引いている)。`_http.py` の「needs no live connection」は基点で既に偽である | §2.1 と完了条件 15 に `r2db-api/conformance/conformance_adapter_r2db.py`:205-225 の docstring を足した。`_http.py`:2409-2410 は**基点で既に偽**である旨を註記し、「R-62 が偽にした」とは書かない |
| R1-6 | WP-2 の確定文が peer 間の「同じ結果」を述べると偽になりうる (MitateDB の catalog の打ち切りは別の code に写る)。`lock_timeout` の対称性も無い | §3.2 の制約に 2 行足した: **peer 間で client に見える結果の一致を述べない**、**`lock_timeout` は r2db の取引ごとの設定だけで、MitateDB の role 水準の設定は `statement_timeout` だけ**。MitateDB の写像の件は**監督が台帳に別件で起票**する (§5 の (5-5)) |
| R1-7 | timeout の denial が監査に残ることを誰も観測していない | 完了条件 5 (`operation="catalog"`、`reason_code=LIMIT_EXCEEDED` の deny 事象) と変異 M5 を足した |
| R1-8 | `SET LOCAL` の非漏洩は、次の取引が**同じ接続**で走らないと空振りする | 完了条件 3 に「同じ接続を固定して観測する (pool を 1 接続に構成するか、同じ接続オブジェクトであることを確かめる)」を足した |
| R1-9 | M8 (旧 M10) の `old` が一意にならない (`ALTER ROLE … statement_timeout` は 4 箇所に同形で在る)。J-1 のテストが backend を閉じないと接続が残る | §2.3 の M8 を「直前の `CREATE ROLE` 行を含めて一意化、**developer 側の 1 本**」にした。完了条件 14 に backend を確実に閉じること (`timeout_probe_app` の利用を検討) を足した |
| R1-10 | 新しい `:592` が 1 物理行の上限 (1,400) に近づく | §3.2 に「上限に近づいたら **2 本目の `- ` 主張行へ分ける**」を明記した |
| R1-11 | 「この cell が開くすべての取引」と読める書き方は偽になる (`verify_row_level_security` は上限の無い取引を開く) | §1.1 と §3.2 の確定文の形を**「client が到達する 4 経路」**に限定した。`verify_row_level_security` は `src` に呼び出し元が無い ops / テスト専用であることを §1.1 に実測として書いた |

## 2. WP-1 — `catalog` に取引ごとの上限を通し、写像を揃え、テストで固定する

**目的**: client が到達できるデータ面の 4 経路すべてが、呼び出し側に依らず実行時間の上限を持つようにする。

**読むべき正本**: §1.2 (枠、D-1〜D-3・D-5 の裁定行を含む) / §1.3 (実測) / §1.7 (設計レビュー 1 の反映)。**§1.4 は撤回済みである。**コード側は `r2db-api/src/r2db_api/postgres.py` の `query` (:1152-1206) を上限と写像の手本にする。規律は `docs/work-orders/OPERATING_CONDITIONS.md` §1.4〜§1.6。

### 2.1 触ってよいパス

- `r2db-api/src/r2db_api/postgres.py` — `PostgresCell.catalog` (:803-807) の signature・`_set_timeouts`・例外の写像のみ (R1-2 により期限の確認は**置かない**)。`_timeout_ms` / `_set_timeouts` 自体 (:2275-2297) と `_load_catalog` 以下の本体、`_RefusingPlatformUpgradeCell` (§1.3 の (9))、`verify_row_level_security` (:2183、§1.1) は触らない。
- `r2db-api/src/r2db_api/service.py` — `DataService.catalog` (:933-942) の cell 呼び出しのみ (D-2 + R1-2。`self.limits` だけを渡す)。deny の事象を出す `except FoundationError` の行 (:947-949) は**変えない** (完了条件 5 はこの既存の経路を観測する)。
- `r2db-api/src/r2db_api/backend.py` — `StorageBackend.catalog` (:176-178) の signature のみ。docstring の本文は**言い換えない** (§1.5 の 40c と D-9)。
- `r2db-api/src/r2db_api/structured.py` — `ApplicationCell.catalog` (:978-979) の signature のみ (`limits` を受けて無視する。R1-2)。
- `r2db-api/tests/test_postgres.py` — 完了条件 1・2・3・4 の新規テスト。置き場所は既存の `test_statement_timeout_is_wired_to_resource_limits` (:1241) と catalog 群 (:1257〜) の間。
- `r2db-api/tests/test_foundation.py` — 完了条件 5・6 の新規テスト (DB を使わない)。
- `r2db-api/tests/test_threadpool_offload.py` — :713 の stub の signature のみ。
- `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` — :149 の `("postgres.py", 1439)` の**行番号だけ**を実測値へ更新 (§1.5 の 40b)。allowlist の集合を増減させない。
- `MitateDB-api/tests/test_application_audit.py` — **J-1 の新規テスト 1 件だけ**。このファイルを選ぶ根拠は現物である: module scope の `platform` fixture が `0013_role_statement_timeouts.sql` を実際に流し (:299)、application を provision して runtime / developer の DSN を持ち (:340-341)、catalog の経路が使う `PostgresBackend(app.runtime_dsn, app.developer_dsn)` を組み立てる (:384)。`MitateDB-api/tests/test_postgres.py` は **0013 を意図的に流さない** (:194 の註) ので使えない。別のファイルの方が良いと判断したら**実測の根拠を添えて報告する** (§1.5 の 37)。既存のテスト・fixture・helper は書き換えない。
- `r2db-api/conformance/conformance_adapter_r2db.py` — **J-2 + R1-5。:862-864 のコメント** (`catalog()` is the stalled method: parameter-less …) **と :205-225 の docstring** (`self._cells[app_id].catalog()` を逐語で引いている箇所) **だけ**。
- `r2db-api/conformance/conformance_adapter_r2db_http.py` — **J-2。:2409-2410 のコメントだけ** (`catalog()` needs no live connection at all on this backend either …)。**この文は基点で既に偽である** (`PostgresCell.catalog` は元から接続を開いて取引を張る) ので、直すときに「R-62 が偽にした」とは書かない (R1-5)。

**これ以外は 0 件。** とくに `spec/`・`conformance-tests/`・`security/` (WP-2 が触る)・`MitateDB-api/src`・`MitateDB-api/migrations` (変異での一時編集は別。`mutate.py` が復元する)・`r2db-api/migrations`・`tools/`・`docs/` を触らない。**J-2 の 2 ファイルはコメント行以外を 1 行も変えない** (挙動・テスト・docstring の外形を変えない)。既存の検査が新しいコードで赤になったら**直さず報告する** (§1.5 の 37)。

### 2.2 完了条件 (15 件)

| # | 完了条件 |
|---|---|
| 1 | `PostgresCell.catalog` の signature が **`catalog(self, limits: ResourceLimits \| None = None)`** (R1-2) で、取引を開いた直後に `_set_timeouts(conn, self._timeout_ms(limits, None, None))` を通す。**実 PostgreSQL のテスト**が、テスト側で `_load_catalog` を差し替えて**同じ接続・同じ取引の中で** `statement_timeout` と `lock_timeout` の有効値を `pg_settings.setting` の**生 ms** で読み、`limits.execution_ms` から導いた値と一致することを assert する (`SHOW` は使わない。発行 SQL 文字列の照合や `_set_timeouts` の直呼びで代替しない。R1-4、§1.6 の 52) |
| 2 | `limits` を渡さない直呼び (`cell.catalog()`) でも、既定 `ResourceLimits()` の `execution_ms` から導いた上限が同じ経路で掛かる (観測方法は完了条件 1 と同じ) |
| 3 | `SET LOCAL` が取引の外へ漏れない — **同じ接続を固定して** (pool を 1 接続に構成するか、同じ接続オブジェクトであることを確かめる。R1-8)、catalog の**次の**取引で既定値に戻っていることを観測する |
| 4 | catalog の取引が `psycopg.errors.QueryCanceled` と `psycopg.errors.LockNotAvailable` を、他の 3 操作と**同じ** `LIMIT_EXCEEDED` (413、`details` は `resource`/`limit_class` = `execution_ms`、`limit` = `limits.execution_ms`) に写す。観測は 2 経路 (R1-4): (i) 差し替えた `_load_catalog` が同じ取引の中で `pg_sleep` を走らせ、**実際に**打ち切られること、(ii) `LockNotAvailable` を送り込んで写像だけを見ること。契約の error 語彙の外の結果 (今日の一律 503) を返さない |
| 5 | 打ち切りの denial が監査に残る (R1-7): `DataService.catalog` 経由で完了条件 4 の `LIMIT_EXCEEDED` が起きたとき、`operation="catalog"`・`outcome="deny"`・`reason_code="LIMIT_EXCEEDED"` の事象が記録される (既存の `except FoundationError` の経路。DB を要しない形で観測してよい) |
| 6 | `DataService.catalog` が **`self.limits` だけ**を渡す (`deadline` / `clock` を渡さない。R1-2)。引数を記録する cell で観測する (実 DB を要しない) |
| 7 | **監査照合**: `StorageBackend.catalog` の protocol・`structured.ApplicationCell.catalog`・`test_threadpool_offload.py`:713 の stub が `limits` を受けて無視する形に揃っている。`_RefusingPlatformUpgradeCell.catalog` は変えていない (§1.3 の (9))。既存の `.catalog()` 直呼び **100 箇所**を 1 件も書き換えていない (`git diff` で示す) |
| 8 | `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py`:149 の行番号を**実測**で更新し、allowlist と実在の bare site が両方向で一致する (件数を合わせるだけで済ませない。§1.5 の 40b) |
| 9 | **監査照合**: `r2db-api/tests` の suite、`MitateDB-api/tests/test_application_audit.py` (J-1)、該当する conformance 3 ファイル (`conformance-tests/test_c00_application_escape.py`・`test_c12_capability_agreement.py`・`test_c05_limit_declaration_agreement.py`) が緑。集計行を逐語で報告に残す (§9 の 10 の「開発中」の段。完了ゲートは監督) |
| 10 | **監査照合**: `python3 tools/check_comment_provenance.py --base 24df696 <触った src の 4 パス>` の FAIL 行が **§4.1 (1) だけ**で、(2)・(3)・(5)・§9e・`#:` の行が **0 行** (D-9)。出力を逐語で報告に残す。(2) が出たら**止めて報告する** — 実測上、既存 scope に CH-ID の無い塊を足す形は赤になりうる (`tools/tests/test_comment_provenance.py::test_r63_new_block_before_existing_statement_is_red`)。判定を緩めない (§1.5 の 37) |
| 11 | **監査照合**: `python3 tools/change_class.py <触った全パス>` が `class=D`、`python3 tools/check_doc_refs.py` が 0 dangling、`python3 tools/public_value_scan.py <触った全パス>` が 0 flagged |
| 12 | §2.3 の変異 **8 件**が全件 `expect=red got=red` で、復元が sha256 2 回で照合済み (§1.4 の 29〜31) |
| 13 | §2.3 の対応表に**対応の無い行が無い** |
| 14 | **(J-1 + R1-3)** `MitateDB-api/tests/test_application_audit.py` に新規テストが 1 件在り、**実 PostgreSQL**で、catalog の経路が実際に使う **developer 接続**の**有効値**を読んで role 水準の `statement_timeout` = 5000ms を観測する。`pg_roles.rolconfig` / `pg_db_role_setting` だけを読む形 (宣言の照合) にしない — 見るのは catalog の経路が実際に開く session である (§1.6 の 52)。**backend を確実に閉じる** (既存の `timeout_probe_app` の利用を検討。R1-9)。**`MitateDB-api/src` と `MitateDB-api/migrations` の差分は 0** (変異での一時編集を除く) |
| 15 | **(J-2 + R1-5) 監査照合**: `r2db-api/conformance/conformance_adapter_r2db.py` の :862-864 のコメントと :205-225 の docstring、`同 _http.py`:2409-2410 のコメントが、WP-1 後の実装と合っている (`catalog` が `limits` を取ること、`_http.py` の文は**基点で既に偽**であり「R-62 が偽にした」とは書かないこと)。`git diff` がこの 2 ファイルで**コメント / docstring 行だけ**であることを示す。文面は実測の後に書き (§1.5 の 34)、経緯語を入れず (§4.1 (5))、`hold_in_flight` の停止点の説明としての意味を落とさない |

### 2.3 完了条件 → 変異 (8 件。1 項目 1 テスト、`expect=red`)

| 完了条件 | 変異 (`tools/dev/mutate.py`。`old` はファイル内に 1 回だけ現れる文字列にする) |
|---|---|
| 1 | **M1**: `catalog` から `self._set_timeouts(conn, timeout_ms)` の行を削る |
| 2 | **M2**: `limits` が無いときの既定を `ResourceLimits()` から `ResourceLimits(execution_ms=3_600_000)` に差し替える (明示 `limits` の経路は緑のまま) |
| 3 | **M3**: `catalog` の上限設定を、取引に入る**前**の session 水準 `SET`(= `LOCAL` 無し) の発行に差し替える (`_set_timeouts` 自体は触らない) |
| 4 | **M4**: `catalog` の `except psycopg.errors.QueryCanceled` / `except psycopg.errors.LockNotAvailable` の 2 節を外す (一律 `psycopg.Error` の 503 に落ちる) |
| 5 | **M5**: `DataService.catalog` の `except FoundationError` の `self._event(...)` を削る (raise はそのまま) |
| 6 | **M6**: `service.py` の呼び出しを引数無しの `.catalog()` に戻す |
| 8 | **M7**: `("postgres.py", <更新後の行>)` の行番号を 1 ずらす → **赤**: `r2db-api/tests/test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` |
| 14 | **M8 (J-1 + R1-9)**: `MitateDB-api/migrations/0013_role_statement_timeouts.sql` の `begin_provision_application` (セクション 3) から、**developer role 側の `ALTER ROLE … SET statement_timeout` 1 本**を落とす。`old` は**直前の `CREATE ROLE` 行を含めて一意化する** (同形の `ALTER ROLE` が 4 箇所在るため)。テストの application が通る分岐を実測で確かめ、:170 (CREATE ROLE 分岐) と :176 (`duplicate_object` fallback) のどちらかを選ぶ → **赤**: 完了条件 14 の新規テスト |
| 7・9・10・11・12・13・15 | **監査照合** (照合対象は各行の本文のとおり。コマンドと集計行、`file:line`、`git diff` を逐語で報告に残す) |

- M1〜M6 と M8 が赤にする test id は**新規テストの名前**なので、実装担当が §2.2 の各行に対応するテストを 1 件ずつ作り、その id を `mutations` の `tests` に**1 件だけ**書く (`mutate.py` は最初の失敗で止まる)。
- **M8 の註**: migration ファイルへの変異は `mutate.py` が backup → 復元 → sha256 2 回で戻すので可 (§1.4 の 29〜31)。変異の対象は fixture ではなく**実物の migration** であり、「テスト用クラスタで role の設定を外す」形にはしない。
- **M3 の註**: 完了条件 3 の観測は「次の取引で既定値に戻っている」ことであり、M3 はその性質だけを壊す (M1 と違い、当該取引の中では上限が掛かったままになる)。
- **M2 の註**: 完了条件 2 のテストは、観測した有効値が `ResourceLimits().execution_ms` から導いた値であることを assert する (「上限が 0 でない」等の代理指標にしない。§1.6 の 52)。
- **M5 の註**: 完了条件 5 は既存の deny の経路を観測する。M5 はその 1 行だけを壊し、`LIMIT_EXCEEDED` が client に返ること自体 (完了条件 4) は緑のまま残る。

### 2.4 道具の引数

worktree は `.claude/worktrees/jovial-almeida-97c9fb` (基点 main `24df696`)。`pt.py` / `mutate.py` は main checkout を cwd にして走らせ、`$SP` (自分の scratchpad) を export しておく。

```bash
tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- r2db-api/tests -q
tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- MitateDB-api/tests/test_application_audit.py -q
tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- conformance-tests/test_c00_application_escape.py conformance-tests/test_c12_capability_agreement.py conformance-tests/test_c05_limit_declaration_agreement.py -q
tools/dev/mutate.py "$SP/r62-mutations.json" -C .claude/worktrees/jovial-almeida-97c9fb
```

worktree を cwd にして走らせるもの:

```bash
python3 tools/check_comment_provenance.py --base 24df696 r2db-api/src/r2db_api/postgres.py r2db-api/src/r2db_api/service.py r2db-api/src/r2db_api/backend.py r2db-api/src/r2db_api/structured.py
python3 tools/change_class.py <触った全パス>
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py <触った全パス>
```

**`pytest` の直接実行・`gate.py` / `finalize.py` の実行・commit・merge は行わない** (監督)。`gate.py` は他の pytest と同時に走らせると落ちるので、レビュー担当と同時刻に走らせない (§1.3)。一時ファイルは `$SP` 配下だけに置く。報告は `$SP/r62-report.md` に書く。

### 2.5 レビュー

- **コードレビュー 1 回** (実装担当とは別の起動)。観点: (i) 上限が呼び出し側に依らないこと (直呼びの経路も含む)、(ii) 新規テストの空振り (§1.5 の 32) と代理指標 (§1.6 の 52)、(iii) 写像が他の 3 操作と同一であること (`details` の 3 キーを逐語で突合)、(iv) 行番号 pin の実測、(v) レビュー担当自身の変異 1〜2 件 (報告に無いもの)、(vi) J-1 のテストが**経路の session** を見ていること (宣言の照合で済ませていないこと) と、J-2 の 2 つのコメントの新しい文が実装と合い、コメント行以外に差分が無いこと。
- **受け入れ監査 1 回** (レビュー担当とも別の起動)。**Class D の手順が求めるもので省かない** (R-59 の訂正註の記録、`RM` §9 の 8)。

## 3. WP-2 — `security/CONTROL_MAPPING.md` を版 2.15 に上げ、旧文を履歴へ移す

**目的**: 正本順位 5 の文書が現在形で述べている「catalog は文の上限を持たない — 開いた台帳項目」という主張を、WP-1 の実挙動に合わせる。**WP-1 と同じコミットに入る。**

### 3.1 触ってよいパス

- `security/CONTROL_MAPPING.md`
- `security/CONTROL_MAPPING_HISTORY.md`

これ以外は 0 件 (台帳 `RM` の R-62 行の追記、D-7 の設計メモへの【追記】、引き継ぎ書は**統合時に監督が行う**)。

### 3.2 確定文の「形」と埋める穴 (**確定文は監督が WP-1 の実測の後に確定する**)

編集は **(1) → (2) → (3) → (4) の順**で行う。行番号は基点 `24df696` の現物で、(4) の preamble への追記で以後の行番号は下へずれるので、対象は行番号ではなく**文の中身**で同定する。

#### (1) 新しい `:592` (SI-08 / r2db-api / default block / Control)

**形**: `- **<太字の導入>**: …` の既存の形を保つ。前半 (peer 間の差の開示) は**残す**、後半 (`PostgresCell.catalog` … `an open ledger item`) を**置き換える**。**1 物理行が上限 (1,400 字) に近づいたら、2 本目の `- ` 主張行へ分ける** (R1-10。ブロック長の実測は完了条件 6 で取り直す)。

```
- **disclosed difference between the peers**: 〈MitateDB は 0013 で application の runtime/developer role にも role 水準の statement_timeout を置き、r2db はそれを置かず取引ごとの `SET LOCAL` (`r2db-api/src/r2db_api/postgres.py:〈穴 A〉`) に依る、という現行どおりの主張〉; 〈`PostgresCell.catalog` (`:〈穴 B〉`) も同じ呼び出しを自分の取引の中で発行し、`limits` を渡さない呼び出しでも既定の `execution_ms` から導いた上限が掛かり、打ち切りは他の 3 操作と同じ `LIMIT_EXCEEDED` に写る、という現在形の 1 主張〉 -- 〈穴 C: それを固定するテスト名〉〈穴 D: MitateDB 側の証拠のテスト名〉.
```

**埋める穴**:

| 穴 | 埋めるもの | 出どころ |
|---|---|---|
| A | `_set_timeouts` の**新しい**行範囲 (現行 `:2282-2297`) | WP-1 後の実測 |
| B | `catalog` の**新しい**行範囲 (現行 `:803-807`) | WP-1 後の実測 |
| C | WP-1 の完了条件 1・2・3・4 を固定する `r2db-api/tests/test_postgres.py::<テスト名>` (先例どおり `::` 区切りで列挙し、実在を確かめる) | WP-1 の新規テスト名 |
| D | **MitateDB 側の断言の証拠** (J-1 + R1-3): `MitateDB-api/tests/test_application_audit.py::<テスト名>` — 主張の前半が述べる MitateDB の role 水準の `statement_timeout` を、**catalog の経路の developer 接続**で固定するテスト | WP-1 の完了条件 14 の新規テスト名 |

**確定文の制約** (R1-6・R1-11):

- **peer 間で client に見える結果の一致を述べない** — 同じ安全上の結果 (取引に上限が掛かる) までを述べ、打ち切りがどの error code に写るかを両 peer 共通の事実として書かない。
- **`lock_timeout` は r2db の取引ごとの設定だけである** — MitateDB の role 水準の設定は `statement_timeout` だけなので、`lock_timeout` を peer 間の対称な事実として書かない。
- **射程は「client が到達する 4 経路」に限る** — 「この cell が開くすべての取引」とは書かない (§1.1、`verify_row_level_security`)。

**満たす不変量** (`conformance-tests/test_control_mapping_register.py`): 1 主張 1 行 / `|` 表なし / 物理行 ≤ 1,400 字 / ブロック ≤ 15,200 字 (訂正前 12,928、残り 2,272。§1.3 の (10)) / 名前付き小ブロックは増やさない。

#### (2) `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` への追記 (1 件)

`## SI-08` 節の**末尾**に足す。節は `:200` の `---` で終わっているので、**その既存の `---` に続けて preface 行から始める** (`---` を新しく足さない)。**旧 `:592` は現物から切り出してそのまま移し、再入力しない。**

```
*r2db-api Control claim, 〈この主張の呼び名 — 取引ごとの `SET LOCAL` と `PostgresCell.catalog` の文の上限〉, superseded 2026-09-〈日〉 (Version 2.15, R-62 -- 〈覆した根拠: catalog が取引の中で同じ `SET LOCAL` を発行するようになり、開いた台帳項目が閉じた〉), verbatim:*

<ここに旧 :592 の行をそのまま 1 行で置く>

---
```

#### (3) 新しい Version 行 (`:5` を置き換える。**1 物理行のまま**にする)

**形** (R-60/R-61 の `:5` と同じ組み立て): `Version: **2.15** (2026-09-〈日〉; R-62 -- 〈どの (SI, peer, block) の Control 主張を in place で直したか、ブロック間の移動は無いこと〉: 〈何が偽になったので直したか〉. No new invariant or control. The superseded line verbatim in `CONTROL_MAPPING_HISTORY.md`'s SI-08 section. -- docs/design/ROADMAP_POST_PHASE7_V1.md R-62)`

#### (4) `Blocks per subsection` 段への再実測の追記

段の**末尾** (版 2.14 の再実測文の後ろ) に、先例 3 文と同じ書き方で 1 文足す。**数値は自分で実測した値**を入れる。段は 63〜81 桁で折られているので同じ幅で折る。

```
Re-measured 2026-09-〈日〉 (version 2.15, after R-62 corrected one Control
claim in `SI-08`'s `r2db-api` `default block` in place and moved
nothing): that block is now `〈実測〉` characters (`〈残り〉` left, against
the `12,928` version 2.12 measured); the longest block stays `SI-08`'s
`MitateDB-api` `default block` at `13,023`, unchanged this change set.
```

### 3.3 完了条件

| # | 完了条件 |
|---|---|
| 1 | §3.2 (1) の確定文 (監督が確定したもの) が `security/CONTROL_MAPPING.md` に**逐語で**入り、旧 `:592` は現行の位置から消えている |
| 2 | 旧 `:592` が §3.2 (2) の形で `## SI-08` 節に**逐語で**移っている。`git show 24df696:security/CONTROL_MAPPING.md` から切り出した 1 行と履歴の行の完全一致を機械的に照合し、出力を報告に残す |
| 3 | Version 行が §3.2 (3) の確定文で **1 物理行**。`Blocks per subsection` 段の末尾に §3.2 (4) の再実測の文が在り、**自分で実測した値**が入っている |
| 4 | `conformance-tests/test_control_mapping_register.py` が緑 |
| 5 | `python3 tools/check_control_mapping_split.py --base 24df696` の集計行が `missing=1 added=1 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical` である。**まず `--expect` 無しで走らせて出力を逐語で記録し、予測と一致したら同じ行を `--expect "<その行>"` に渡して終了コード 0 を取る**。一致しなければ止めて報告する |
| 6 | ブロック長の実測を報告する: SI-08 / r2db-api / default の訂正前後、文書の最長ブロック、上限までの残り、新しい `:592` の字数と Version 行の字数 (どちらも 1 物理行、≤ 1,400) |
| 7 | **監査照合**: 差分が `security/` の 2 ファイルと WP-1 の `r2db-api/` のパスだけである (`git status --short`)。`docs/`・runbook・`MitateDB-api/`・`spec/`・`conformance-tests/` に 1 行も作らない (§1.3 の (11)) |
| 8 | §3.4 の変異 3 件が全部 `expect=red got=red` で、復元が sha256 2 回で照合済み |
| 9 | §3.4 の対応表に**対応の無い行が無い** |

### 3.4 完了条件 → 変異

| 完了条件 | 変異 | 期待 |
|---|---|---|
| 4 (1 主張 1 行) | **M11**: 新しい `:592` の途中に改行を入れ、後半を `- ` で始まらない物理行にする | **赤**: `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` |
| 4 (ブロック長) | **M12**: 新しい `:592` の**直後**に `- ` で始まる詰め物の主張を足して SI-08 / r2db-api / default を上限超にする (各物理行 < 1,400 字、合計で完了条件 6 の残り +1 字以上)。詰め物は合成文字列だけで、実 DSN・実ホスト名・絶対パスを書かない | **赤**: `::test_control_mapping_md_blocks_do_not_exceed_the_length_cap` |
| 4 (履歴リンク) | **M13**: `security/CONTROL_MAPPING_HISTORY.md` の `## SI-08` の見出しに題を足す (アンカーが変わる) | **赤**: `::test_every_control_mapping_section_has_a_resolving_history_link` |
| 1・2・3・5・6・7・8・9 | **監査照合** (照合対象は各行の本文のとおり。`git diff`・機械照合の出力・道具の集計行・実測値の表を逐語で報告に残す) | — |

- **M12 の註**: 詰め物は行長の検査も同時に満たしうるので、`tests` には**ブロック長の 1 件だけ**を置く。新しい本文が測られる側に入っている直接の証拠は完了条件 6 の実測 (訂正前後の差) である。
- **M13 の註**: M13 は**基点でも赤になる**変異であり、本変更セットが足した文言そのものは観測しない — 旧文を置いた節の**履歴リンクの不変量が生きていること**の生存確認である。逐語の照合は完了条件 2 (機械照合) が担う。`::test_control_mapping_history_has_exactly_the_main_sections_ids` も同時に赤になりうるので、`tests` には上の 1 件だけを置く。

### 3.5 道具の引数

```bash
tools/dev/pt.py -C .claude/worktrees/jovial-almeida-97c9fb -- conformance-tests/test_control_mapping_register.py -q
tools/dev/mutate.py "$SP/r62-cm-mutations.json" -C .claude/worktrees/jovial-almeida-97c9fb
```

worktree を cwd にして:

```bash
python3 tools/check_control_mapping_split.py --base 24df696
python3 tools/check_doc_refs.py
python3 tools/public_value_scan.py security/CONTROL_MAPPING.md security/CONTROL_MAPPING_HISTORY.md
```

(この worktree に `.venv` は無いので、先例の `./.venv/bin/python` ではなく `python3` で走らせる。`check_control_mapping_split.py` は標準ライブラリだけで動くことを起草時に実測した。)

## 4. 受け入れ

監督が完了ゲート (`tools/dev/gate.py -C .claude/worktrees/jovial-almeida-97c9fb`) の集計行と §2.2・§3.3 を照合して判定する。**Class D なので受け入れ監査を入れる** (§2.5)。受理したら、台帳 `RM` §8 の R-62 行に追記して閉じ (行は消さない)、D-7 の【追記】を記録のコミットで入れ、引き継ぎ書で依頼者へ**事後報告**する (§0)。

**監督の判定 (2026-09-21): 受け入れ。** 根拠は 4 つ。(a) 受け入れ監査 1 回が独立に照合し、**WP-1 の完了条件 15 件・WP-2 の 9 件をすべて充足**、未充足 0・証拠不足 0 と判定した (§6)。(b) 最終の木の完了ゲートが `3796 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0、共有クラスタ差分 0 (info) で、`docs/work-orders/OPERATING_CONDITIONS.md` §1.3 の 22・26 の合格条件 (failed = 0 / skipped = 0 / xfailed = 0 / xpassed = 0 / deselected = 0) を満たす。(c) 変異 11 件が全部 `expect=red got=red` で、§2.3・§3.4 の対応表に対応の無い行は 0 件。(d) 本書の確定文・範囲からの逸脱は §6.1 の訂正註 1〜9 の 9 件だけで、いずれも監督裁定として記録した。統合は main `3a52296` (作業 `250cf95`)、push は無し。台帳の追記と R-71 の起票は `RM` **v1.78**。

## 5. 本書の範囲外 (申し送り。列挙のみで、本書の WP では行わない)

- **(5-1) MitateDB 側の 1 件 → 範囲内になった。** 起草時に提案したもの (§1.3 の (3)) は **§1.6 の J-1 で採用**され、WP-1 の完了条件 16・変異 M10 になった。本節には残件として残らない。**引き続き範囲外なのは `MitateDB-api/src` と `MitateDB-api/migrations` の恒久の差分** (変異での一時編集を除く)。
- **(5-2) r2db の plug の 2 つのコメント → 範囲内になった。** 起草時に挙げたもの (§1.3 の (6)) は **§1.6 の J-2 で採用**され、WP-1 の完了条件 17 (監査照合) になった。**コメント行以外は触らない**ので、plug の挙動・停止点・テストは本変更セットで 1 つも変わらない。
- **(5-3) D-7 の【追記】**: `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` の D-2 の経路表 (:85) と §10 の 1 (:242) への【追記】は**監督が記録のコミットで行う**。行は消さない。
- **(5-4) `r2dbsvc_control` / provision 役の role 水準 timeout** (R-56 設計 §10 の 2、台帳 R-66) と、`tools/perf_baseline.py` の op 語彙に catalog を足すこと (§1.3 の (4)) は、どちらも本件の範囲外である。
- **(5-5) MitateDB の catalog の打ち切りが写る error code (R1-6)**: MitateDB 側で role 水準の `statement_timeout` が catalog の経路を打ち切ったとき、client に見える結果が r2db と同じ `LIMIT_EXCEEDED` になるとは限らない。**監督が台帳に別件として起票する。** 本書では両 peer の結果の一致を主張しない (§3.2 の制約)。

## 6. 記録 (2026-09-21、統合時に監督が埋めた。§1〜§5 の本文は書き換えない)

- **実施 2026-09-21。** 基点 main `24df696`。本書自体は先行して main `56b3d5b` (作業 `6a934dd`) に入り、コードと `security/` の変更セットは **1 コミット**で main `3a52296` (作業 `250cf95`)。**push は無し**。`security/CONTROL_MAPPING.md` **版 2.15**。**変更クラス D** (§0 のとおり。台帳の起票文の「B の見込み」は誤りで、理由は §1.2 の D-0)。**契約 1.8.0 のまま**、`spec/`・`conformance-tests/`・migration・`MitateDB-api/src`・`MitateDB-api/migrations`・`tools/` の差分 **0** (`MitateDB-api/tests` は J-1 の 1 ファイル)。触ったのは 13 パス。
- **採用形**: `PostgresCell.catalog(self, limits: ResourceLimits | None = None)` が、取引の中の先頭で `_set_timeouts(conn, self._timeout_ms(limits, None, None))` を発行する (`limits` が無ければ `ResourceLimits()`)。`DataService.catalog` は `self.limits` **だけ**を渡す。`QueryCanceled` / `LockNotAvailable` → `LIMIT_EXCEEDED` 413 (`details` の 3 キー)、それ以外の `psycopg.Error` → 503 の 4 行は `query` と**逐語で同一**。これに伴い catalog の deny の監査事象 (`reason_code="LIMIT_EXCEEDED"`) が立つ。**`deadline` は渡さない** (§1.7 の R1-2)。protocol・`structured.py`・`test_threadpool_offload.py` の stub は同じ signature で、`_RefusingPlatformUpgradeCell.catalog` は基点のまま。MitateDB-api はコードを変えず、catalog の経路が使う developer 接続がrole 水準の `statement_timeout` (5000ms) を持つことをテスト 1 件で固定した。r2db の conformance plug 2 ファイルはコメント / docstring 行だけを事実に合わせた (実行コードは AST 同一。範囲は §6.1 の訂正註 3)。
- **完了ゲート (監督が単独実行。最終の製品の木)**: `3796 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0、共有クラスタ差分 0 (info)。差し戻し前の木で取った 1 回目も同じ集計行で PASS だったが、**正本は最終の木の測定**である。前回 `3789` からの **+7** は新規テスト (r2db 6、MitateDB 1)。
- **peer 別の集計行 (逐語)**: `r2db-api/tests` `1351 passed`、`MitateDB-api/tests/test_application_audit.py` `73 passed`、conformance 3 ファイル (c00・c12・c05) `134 passed`、`conformance-tests/test_control_mapping_register.py` `34 passed`。
- **変異**: **11 件すべて赤**。`tools/dev/mutate.py` の要約行 = WP-1 (M1〜M8) `8 mutations, 8 as expected, restores verified 4/4 files (sha256 x2)`、WP-2 (M11〜M13) `3 mutations, 3 as expected, restores verified 2/2 files (sha256 x2)`。
- **道具の出力 (逐語)**: `tools/check_control_mapping_split.py --base 24df696 --expect "missing=1 added=2 moved=0 empty_axis_added=0 empty_axis_removed=0 subsequence=ok preamble=differs ccr14=identical rule=identical"` = **exit 0** (期待行の差し替えは §6.1 の訂正註 1)。`tools/check_comment_provenance.py --base 24df696 <触った src の 4 パス>` の FAIL は **§4.1 (1) の 4 行だけ**で、(2)・(3)・(5)・§9e・`#:` は **0 行**。`tools/change_class.py <触った 13 パス>` = `class=D`、`tools/check_doc_refs.py` = **0 dangling**、`tools/public_value_scan.py <同 13 パス>` = `files_scanned=13 total_flagged=0`。`r2db-api/tests/test_l1_details_vocabulary_ast_scan.py` の pin は `("postgres.py", 1439)` → **`1451`** (実測で更新。:1451 は `_fail_client_value` の bare site)。
- **ブロック長の実測** (実装担当・コードレビュー担当・受け入れ監査担当の 3 者が独立に一致): SI-08 / r2db-api / default block **12,928 → 14,105** 字 (上限 15,200 まで残り **1,095**)。**文書の最長ブロックになった** — 次は SI-08 / MitateDB-api の既定 **13,023** で不変。新しい主張 2 行は **737** 字と **1,011** 字、Version 行は **897** 字 (いずれも 1 物理行、≤ 1,400)。履歴へ移した旧文は基点 `24df696` と**逐語一致**で、`security/` の触っていない行は 1 行も動いていない。
- **性能差分**: `tools/perf_baseline.py` の op 語彙に `catalog` が無く、本件は計測対象を持たない (§1.3 の (4)、§5 の (5-4))。
- **体制**: 設計レビュー **1 回** (11 件、全件裁定。反映は §1.7)。コードレビュー **1 回** (中 1・軽微 2・懸念 1、全件採用、差し戻し **1 回**)。受け入れ監査 **1 回** (WP-1 の完了条件 **15 件**・WP-2 の **9 件**とも充足、未充足 **0**)。
- **決定の出所**: 依頼者指示 2026-09-19 の委任の下で**監督が推奨として下した** (§0)。引き継ぎ書で**事後報告**する。
- **起票**: MitateDB-api の catalog の打ち切りが写る error code の件 (§5 の (5-5)、設計レビュー 1 の指摘 6) を `RM` (= `docs/design/ROADMAP_POST_PHASE7_V1.md`) §8 の **R-71** に起票した。`RM` は **v1.78** (R-62 行を閉じ、R-65 行を更新した)。
- **D-7 の【追記】** (§5 の (5-3)): `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` の D-2 の経路表の `catalog` の行と §10 の 1 に【追記 2026-09-21】を置いた。行は消していない。
- **完了条件 → 変異 → test id (WP-1)** (`r2db-api/tests/` を省く): 1 ← M1 → `test_postgres.py::test_catalog_wires_statement_and_lock_timeout_to_the_passed_resource_limits` / 2 ← M2 → `::test_catalog_without_an_explicit_limits_argument_uses_default_resource_limits` / 3 ← M3 → `::test_catalog_set_local_timeouts_do_not_leak_to_the_next_transaction` / 4 ← M4 → `::test_catalog_maps_timeout_and_lock_conflicts_to_limit_exceeded` / 5 ← M5 → `test_foundation.py::test_data_service_catalog_denial_is_audited_with_the_limit_exceeded_reason` / 6 ← M6 → `::test_data_service_catalog_passes_only_its_own_limits_to_the_cell` / 8 ← M7 → `test_l1_details_vocabulary_ast_scan.py::test_allowlist_entries_match_real_bare_call_sites` / 14 ← M8 → `MitateDB-api/tests/test_application_audit.py::test_developer_connection_used_by_the_catalog_path_carries_the_role_level_statement_timeout`。**7・9・10・11・12・13・15 は監査照合**で、照合対象は §2.2 の各行の本文のとおり (コマンドと集計行、`file:line`、`git diff`)。受け入れ監査が独立に再実行・再測して確認した。**対応の無い行は 0 件** (完了条件 13)。
- **完了条件 → 変異 → test id (WP-2)**: 4 ← M11 → `conformance-tests/test_control_mapping_register.py::test_control_mapping_md_every_subblock_has_the_fixed_axis_shape` / 4 ← M12 → `::test_control_mapping_md_blocks_do_not_exceed_the_length_cap` / 4 ← M13 → `::test_every_control_mapping_section_has_a_resolving_history_link`。**1・2・3・5・6・7・8・9 は監査照合**で、照合対象は §3.3 の各行の本文のとおり。**対応の無い行は 0 件** (完了条件 9)。

### 6.1 訂正註 (2026-09-21 追記。§1〜§5 の本文は書き換えない)

- **訂正註 1 (§3.3 の完了条件 5 の期待行)**: 予測した `added=1` は誤りで、**実測の `added=2` を正とする**。R1-10 で 1 本の主張行を 2 本に分けたためで、集計行の他の語は予測どおりだった。`--expect` を渡した再実行も exit 0。
- **訂正註 2 (§3.2 の確定文)**: WP-2 の確定文は、§0 の定めどおり**監督が WP-1 の実測の後に確定した**。(4) の再実測文は「r2db 側の 14,105 が文書の最長で、分割は台帳 R-65」という形で確定している — 起草時の形は「最長は MitateDB 側のまま」を前提にしていた。
- **訂正註 3 (§2.1 の触ってよいパスの範囲、監督の指示)**: コードレビューの差し戻しで、plug の `service.py` 行番号の訂正を J-2 が挙げた範囲 (`conformance_adapter_r2db.py`:205-225・:862-864、`_http.py`:2409-2410) の**外**の hunk (`conformance_adapter_r2db.py` の :370・:1090・:1117 付近) にも広げた。いずれも**基点で既にずれていた参照** (R-37 の module 分割で動いたもの) で、R-62 が偽にしたものではない。**コメント / docstring 行のみ**で、訂正後の値が現物と一致することを受け入れ監査が確認した。
- **訂正註 4 (実装担当の逸脱 4 点、監督受理)**: (i) M3 に `conn.commit()` を足した (session 水準の `SET` を取引の外で効かせるため)。(ii) `structured.py` は **signature のみ**変更した — 既存関数への docstring の追加はコメント検査の §4.1 (2) で赤になる。(iii) 完了条件 11 の `class=D` は**触った 13 パス全件**を 1 回の呼び出しで測る。(iv) `change_class.py` の初回の測定は誤り (zsh が変数を語分割しないため引数が 1 個になった)。stdin で渡して再実行した値を正とする。
- **訂正註 5 (完了条件 3 の観測形、コードレビューの懸念を採用)**: 漏れのテストは、次の取引の値を `"0"` の直書きと比べる形ではなく、**catalog の前に同じ接続で読んだ baseline** と比べる形にした (クラスタ既定値を前提にしない)。同じ接続であることは `id(conn)` の 3 点固定で確かめる。
- **訂正註 6 (本書の内部不整合 2 件。変更セットの瑕疵ではない)**: ① §3.3 の完了条件 7 の「`MitateDB-api/` に 1 行も作らない」は、§1.6 の J-1 (`MitateDB-api/tests/test_application_audit.py` に新規テスト 1 件) と食い違う。**J-1 が現行**で、§3.3 の 7 は v1.1 で J-1 を取り込んだときの更新漏れである。② §5 の (5-1)・(5-2) が書く旧番号「完了条件 16・変異 M10」「完了条件 17」は、v1.1 の番号 **完了条件 14・M8・完了条件 15** に読み替える。
- **訂正註 7 (§2.5 の (v) は実施していない)**: コードレビュー担当自身の変異 1〜2 件は**行っていない**。監督が、完了ゲートと並行させるためにレビュー担当へ pytest と `mutate.py` の実行を禁じたためで、静的照合と実装担当の変異のログの照合で代えた。
- **訂正註 8 (`catalog` の docstring の読み)**: 「exactly like `query`/`transact`/`apply_schema`」は、**`limits` から導いた `statement_timeout`/`lock_timeout` で取引に上限を掛ける**点を指す。他の 3 操作が `deadline` でさらに絞る点は catalog には無い (§1.7 の R1-2)。`security/CONTROL_MAPPING.md` の確定文はこの差を主張していないので、文書側に誤りは無い。
- **訂正註 9 (決定の出所)**: 本件の決定は、依頼者指示 2026-09-19 の委任の下で**監督が推奨として下した**ものである (§0)。引き継ぎ書で**事後報告**する。
