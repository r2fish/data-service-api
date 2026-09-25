# 引き継ぎ — 2026-09-24 (フェーズ11 最低共通機能プロファイル R-29 / R-23 / R-16。設計 v1.0 と作業指示書まで。実装は未着手)

**ファイル名の衝突に注意**: 本書は 2026-09-24 の 7 本目の `FABLE` 系ファイル名を取った。同日に並走チャット (keyset ページング) が同名 `HANDOVER_20260924_FABLE7.md` を作った可能性がある — merge 前に main の `docs/work-orders/` を読み、衝突していれば本書の名前をずらす (中身の突き合わせではなく、ファイル名で指す。`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 58)。

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `HANDOVER_20260924_FABLE6.md`。**本書はチャット切替のための中間引き継ぎであり、項目は閉じていない。**

**次のチャットが読む材料は worktree 内の `.r29-scratch/` にある** (git の `info/exclude` で除外済み、コミットしない)。以下、ファイル名は同ディレクトリからの相対で指す: `resume-notes.md` (現在地と次の手順)、`requester-rulings-20260924.md` (依頼者裁定 4 件の逐語)、`frame-r29.md` (監督が確定した枠)、`design-review-1.md` / `rulings-review-1.md`、`design-review-2.md` / `rulings-review-2.md`、`rulings-v03-and-wp-frame.md`、探索ノート `explore-caps.md` / `explore-r23-r16.md`、実需の逐語 `mitate-demand-verbatim.md`。

## 1. 現在地

- worktree `.claude/worktrees/laughing-feistel-31c19a` (branch `claude/laughing-feistel-31c19a`)。**local main `0fee6e5` と同一で、コミットは 1 件も無い。**
- 未追跡ファイル 3 件: `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` (v1.0)、`docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` (v1.0)、本書。これに `.r29-scratch/` (除外済み、コミットしない) が加わる。
- **契約は 1.8.0 のまま。** 文書中の **1.9.0 / C-28 / C-29 / 従属判断 14 / 起票 3 件の番号はすべて仮**であり、**merge 直前に main を読んで振り直す** (設計 D-7、作業指示書 §0)。
- push は停止中 (GitHub 課金上限、2026-09-09 以来)。完了ゲートの前値は `4022 passed, 2 subtests passed in 486.51s` (label r105b)。
- **並走**: keyset ページング (別チャット) は 2026-09-24 時点で main に未 merge。先に merge した側が 1.9.0 を取る (設計 §9)。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 探索 (3 体) | 両 peer の宣言値 14 キー、現物の交差、R-23 / R-16 の現物を実測 | 設計 §1.3〜§1.5、`.r29-scratch/explore-caps.md`・`explore-r23-r16.md` |
| 枠の確定 | D-1〜D-8、X-1〜X-5、U-1〜U-5 | `.r29-scratch/frame-r29.md`、設計 §3〜§5 |
| 設計 v0.1 → v0.2 | 設計レビュー 1 の 11 件 (採用 10 / 観察 1) を反映 | 設計 §13、`.r29-scratch/rulings-review-1.md` |
| 設計 v0.2 → v0.3 | 設計レビュー 2 の 12 件 + 回答項 (全件採用) を反映。却下 X-6 / X-7 を新設 | 設計 §14、`.r29-scratch/rulings-review-2.md` |
| 依頼者裁定 (4 件) | U-1 / U-4 = (α) 契約の義務、U-2 = (i) 現物の交差 + 床上げは別起票、U-3 = (a) 最小形 + (c) 参照クライアントは別起票、U-5 = Class D の裁定文 | 設計 §5 の【裁定】欄 (逐語)、`.r29-scratch/requester-rulings-20260924.md` |
| 設計 v1.0 | 確定版。§15 (v0.3 の疑義と裁定)、§16 (起票する項目 3 件、規模 L)、§17 (実施記録、空欄) を新設 | 設計 §0 改版履歴 |
| 作業指示書 v1.0 | Change Set Manifest、WP-1〜WP-4 (直列)。各 WP に 完了条件 ↔ 変異 の対応表 (候補。実測して確定するのは実装担当) | `docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` |

**実装は未着手である** (WP-1 も起動していない)。設計レビューは 2 回で終わり (契約を触る項目、計画文書 §9 の 3)。

## 3. 次の一手

`.r29-scratch/resume-notes.md` の手順がそのまま生きている。

1. **最初に「control plane の宣言版を WP-3 で 1.9.0 (仮) に上げるか」を `explorer` (sonnet) で実測する** — `r2db-api` の `control_plane.py`:633 = 1.8.0、`MitateDB-api` の `control_plane.py`:1595 = 1.7.0。見るのは control 面の版フリップに条件付き義務 (C-25 (3) 等) が掛かるかである。**実測の後に監督が裁定し、作業指示書に訂正註を足す** (本文は書き換えない。§1.8 の 57)。
2. WP-1 を `implementer` (テンプレート 2) に発注 → `reviewer` (テンプレート 5) → WP-2 → WP-3 → **完了ゲート** `tools/dev/gate.py -C .claude/worktrees/laughing-feistel-31c19a --label p11` (監督が単独で 1 回、`-C` を必ず渡す) → WP-4 → `evidence-auditor` (テンプレート 6) → `tools/dev/finalize.py`。
3. **設計文書と作業指示書は WP-1 と同一変更セットでコミットする** — 設計が C-28 / C-29 (仮) を参照するため、`tools/check_doc_refs.py` が単独コミットを dangling で止める (設計 §12 の裁定 4)。
4. merge 直前に監督が main を読み、**契約版・条件番号・従属判断番号・起票 3 件の番号**を振り直す (設計 D-7)。keyset が先なら 1.10.0 / 番号を繰り下げ。
5. WP-4 で計画文書の **R-29 / R-16 / R-23 行の閉止**、**§0.1.1 の G-2 / G-3 行** (契約版・条件数)、**§0.1.3 の再実測**、**新規起票 3 件** (設計 §16)、**版数ログの回転** (§1.16 の 78) を同一変更セットで行う。

## 4. 依頼者判断待ち・未決

- **依頼者判断待ちは無い。** U-1〜U-5 は 2026-09-24 に裁定済み (設計 §5、逐語は `.r29-scratch/requester-rulings-20260924.md`)。
- **監督裁定待ち**: v1.0 起草時の疑義のうち 5 番目 (control plane の宣言版) の 1 件 (最終節の裁定表の末尾行。1〜4 は観察 / 直した)。これは上の §3 の 1 の実測が前提である。
- **本項目が満たさないもの** (honest scope、設計 §11): Mitate の実需 (solutionName の一意性 / `revision_preconditions` / `append_only`) は baseline では満たされない。引き取り先は設計 §16 の新規起票 (1)(2) と既存 R-49。`spec/README.md`:5-9 の目標は §16 の (3) 参照クライアントが着地するまで実行可能な形で証明されない。

## 5. 本チャットで足した運用上の教訓

1. **`opus` 別名は Opus 5.5 (`claude-opus-5-5`) に解決される** (依頼者確認、並走チャットの記録)。**サブエージェントの自己申告 (`claude-opus-5[1m]` 等) は判別材料にならない。** agent frontmatter にモデル ID を書き込む変更は取り消した (別名のままにする)。
2. **チャットの scratchpad は次のチャットから読めない。** 引き継ぐ材料は worktree 内の除外ディレクトリ (本件は `.r29-scratch/`) に写し、引き継ぎ書からは相対パスで指す。
3. **設計文書が未作成の条件 ID (C-28 等) を参照すると `tools/check_doc_refs.py` が dangling を出し、設計を単独でコミットできない。** `conformance-tests/CONDITIONS.md` の行追加と同一変更セットにする。
4. **台帳の版数・契約版・C 番号は並走チャットと衝突する。** 文書には仮番号で書き、merge 直前に main を読んで振る。
5. **設計レビューの指摘は「裁定表を作ってから本文へ反映する」と、v0.1 の判定を消さずに版を重ねられる** (§1.8 の 56)。反映しなかった提案は §13 末尾のように開示して次のレビューに送る。

## 追記 — 2026-09-24 再開チャット (依頼者指示で中断。WP-1 途中)

- §3 の 1 (control plane の宣言版) は**裁定済み**: WP-3 で両 peer の control plane も同一コミットで 1.9.0 (仮) に上げ、`operation_catalog_url` を両面に載せる。根拠と帰結は作業指示書 §7.1 の訂正註と `.r29-scratch/ruling-control-plane.md` (実測 `.r29-scratch/explore-control-plane-flip.md`)。**§3 の「MitateDB `control_plane.py`:1595 = 1.7.0」は誤記であり、両 peer とも 1.8.0 である。**
- WP-1 は実装担当が §2.4 の 1〜7 を実装した状態で中断 (報告 `.r29-scratch/wp1-report.md`、pt `3 failed, 85 passed`、mutate 未実行)。3 赤は監督が裁定済み (作業指示書 §7.1 の訂正註 1〜3 と観察): `test_contract.py`:1103 の裸 assert は 1.6.0 段落限定に改める / declared 期の Evidence 欄にはテストファイル名を書かない (現行検査器は両書式とも赤、先例は検査器導入前) / 7(A) 列挙は機械検査が無く監査照合。現在地と手順は `.r29-scratch/resume-notes.md` (第 2 版)。
- 引き継ぎ書の裁定表 (本節の 4 件 = 直した 3 件 + 観察 1 件) は WP-4 で書く次の引き継ぎ書に載せる。

## 裁定

設計レビュー 1 (11 件)、設計レビュー 2 (12 件 + 回答項)、起草担当の疑義 (v0.1 8 件 / v0.2 6 件 / v0.3 5 件 / v1.0 5 件) を全件載せる (§1.15 の 77)。「直した」は**同じ変更セット** (未コミットの設計文書 v0.2〜v1.0 と作業指示書 v1.0) で反映済みの意である。出所: `.r29-scratch/rulings-review-1.md` / `rulings-review-2.md` / `rulings-v03-and-wp-frame.md` / `resume-notes.md`、設計 §12〜§15。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 設計レビュー 1-1 [高]: 床に `page` を丸ごと入れると MitateDB は 1.9.0 宣言と同時に義務違反 | 直した | 床の paging を `page.size` のみにし、`cursor` / `next_page` は `outside` へ (設計 D-1 (e)、§6.1、§7 段 (9)、§9) |
| 設計レビュー 1-2 [高]: 床の update / delete が `mutation_classes.rule` と `upsert` 規則に衝突 | 直した | §6.1 rule の末尾にレビューの但し書きを逐語で追加、§11 に R-49 が契約上実装可能なままである旨 |
| 設計レビュー 1-3 [高]: C-29 の「byte 一致で配る」を peer が実行する手段が設計に無い | 直した | 派生カタログを契約 JSON と同じ 3 複製にし、再生成一致テストを 3 複製比較に拡張 (設計 D-5、§6.5、§10)。peer ごと派生器は X-6 として却下 |
| 設計レビュー 1-4 [中]: §6.3 の書き換えが `test_contract.py` の 1.7.0 逐語 pin に当たる | 直した | (α) は pin を 1.9.0 の文言へ差し替える (版の改訂は U-4 の依頼者裁定そのもの)。§6.5 に対象行を追加 |
| 設計レビュー 1-5 [中]: 床は既存の conditional obligation 8 件を実質無条件化するが §6 が述べない | 直した | §6.2 (1) にレビューの 1 文を逐語で追加、§6.1 に `capabilities` 配列 (8 名)、(k)(l) は rule 側の 1 文で受ける |
| 設計レビュー 1-6 [中]: C-28 の 12 段に `request_budget` の段が無い | 直した | 段 (9) の query に `budget` を付け、受理されて行が返ることを床 (i) の観測に (設計 D-2、§7)。狭める意味は C-24 に委ねる |
| 設計レビュー 1-7 [中]: 段 (6) → (7) の plan の受け渡しが契約規則で必ず失敗する形 | 直した | 段 (6) の dry_run にも同じ `idempotency_key` を付け (契約 :710)、段 (7) で段 (6) の `plan` を提示する (設計 D-2、§7) |
| 設計レビュー 1-8 [中]: C-29 (i) が契約の要求しない性質を検査する / 配る path の位置が未決 | 直した | `base_url` 配下の制約を外し、契約 `endpoints` に `operation_catalog` を新設。socket plug で実 dial、in-process は port method (設計 D-5、§6.3、§6.4、§8.2、§12 裁定 3 の註) |
| 設計レビュー 1-9 [低]: §8.1 の SI-14 の根拠文が C-28 の観測範囲を超える | 直した | C-25 行と同じ限定文言 (request_id の存在と相関、監査証跡は対象外) に置換 |
| 設計レビュー 1-10 [低]: 段 (9) の順序期待が tie で両 peer 不一致になりうる | 直した | §7 段 (9) に「sort key は一意」を追加 (r2db は id tie-break、MitateDB は無し) |
| 設計レビュー 1-11 [低]: `CONDITIONS.md` の adapter 数表記が実収集と食い違う | 観察 | 本項目では直さない。C-28 / C-29 行は凡例どおり `six adapters` と書く (凡例の `four adapters` = 全 registered adapter の議論は別件) |
| 設計レビュー 2-1 [高]: version_binding に 1.9.0 段落を足すと `spec/CONTRACT_HISTORY.md` の逐語 quote が赤 | 直した | 全文引用・従属判断 14・`Introduced in:` 行を WP-1 の同一変更セットで更新 (設計 §6.5、§10) |
| 設計レビュー 2-2 [高]: §6.2 の件数文が register の「ちょうど 3 版」pin を赤にする | 直した | 1.8.0 の先例どおり count 文を書かず (a)(b) の列挙だけで述べる。pin 拡張案は X-7 として却下 |
| 設計レビュー 2-3 [高]: WP-1 が `executable` 始まりの行を先に置くと register が 3 か所で赤 | 直した | WP-1 は `declared` で置き history リンクと `CONDITIONS_HISTORY.md` の節を同時に足す。`executable` への書き換えは WP-2 / WP-3 |
| 設計レビュー 2-4 [中]: 段 (9) が `page.size` と `budget.result_items` を 1 要求で運ぶと MitateDB だけ LIMIT_EXCEEDED | 直した | 不等式 R ≤ `page.size` ≤ `budget.result_items` ≤ 宣言 `limits.result_items` を D-2・§7・§6.4 に固定 |
| 設計レビュー 2-5 [中]: `definitions.OperationCatalog` では配る文書を記述できない | 直した | `schemas.OperationCatalogDocument` と `definitions.OperationCatalogEntry` に分割。C-11 の手書き列挙には載せず §11 に開示 |
| 設計レビュー 2-6 [中]: 「endpoint は無条件」は 1.8.0 宣言 peer を遡及的に非準拠にする | 直した | endpoint entry の `semantics` に版ゲート 1 文を追加 (設計 §6.6) |
| 設計レビュー 2-7 [中]: 新 endpoint entry の必須キーが足りない (`auth` / `atomicity` / `request` / `response`) | 直した | レビュー全文 §7 の entry JSON 案を設計 §6.6 に逐語で配置 |
| 設計レビュー 2-8 [中]: 変異 12 件のうち C-28 固有の受け渡しを隔離するのは 1 件 / 継ぎ目は C-22 が固定済み | 直した | 段 (7) の変異を差し替え、§7 に「この段だけが赤か」列を追加。継ぎ目の主張を (4)→(5) の診断による修正と (5)→(8) の同一要求体に弱めた |
| 設計レビュー 2-9 [中]: §6.1 rule の partial 節が runtime credential の宣言と矛盾して読める | 直した | rule の partial 節に credential 句を追加、§7 段 (1) に「`operations` の非空を assert しない」註 |
| 設計レビュー 2-10 [低]: WP-3 の触るファイルに port が無い / port 版数が WP-2 と重複 | 直した | WP-3 に `conformance-tests/adapter.py` と両 peer の adapter を追加、port を WP-2 = v1.16 / WP-3 = v1.17 に分離 |
| 設計レビュー 2-11 [低]: §8.3 の CONTROL_MAPPING 追記の形が形式 3.0 の規約より粗い | 直した | 先例どおり Common 節、Version 3.1 → 3.2、`test_control_mapping_register.py` 緑を WP-4 の完了条件に |
| 設計レビュー 2-12 [低]: §13.1 裁定 1 の句が §6.1 本文に入っていない | 直した | 裁定の句を §6.1 本文に反映 (v0.2 は裁定だけがあり本文は旧句のままだった) |
| 設計レビュー 2 回答項: C-29 条件文の言い換え / rule の 3 文目 / `capability_status.rules` の 6 番目 | 直した | 言い換えは採用 (版別保管が無い)、3 文目は足さない、6 番目の規則を追加し `len(rules)` の pin を 6 へ (設計 §6.1、§6.4、§6.5) |
| 起草 v0.1-1: capability キーは 13 ではなく 14 (`control_plane` を含む) | 直した | 14 が正 (枠の 13 は誤記)。設計 §1.3 は 14 キーで確定 |
| 起草 v0.1-2: `order_by` を運ぶ port method が無い | 直した | baseline に `order_by` を残し、WP-2 で port v1.16 として新 method を 1 つ足す (設計内と裁定。設計 §7.1、§10) |
| 起草 v0.1-3: in-process plug に HTTP 面が無く C-29 の「配る」が定まらない | 直した | C-19 の D-4 と同じ二段形 (port method + socket plug の実 dial)。後に設計レビュー 1-8 で (i) を書き換え、行は消さず註を残した |
| 起草 v0.1-4: `check_doc_refs.py` が C-28 / C-29 を dangling と判定し設計を単独コミットできない | 直した | 設計は WP-1 と同一変更セットでコミットする (§3 の 3)。レビューと依頼者裁定は未コミットの worktree 上で実施した |
| 起草 v0.1-5: C-29 の declare-first と U-4 (α) の義務化は両立しない | 直した | 両案を書き分けたままレビューに出し、依頼者裁定 U-4 = (α) で分岐なしに確定 (設計 §5、§6.3) |
| 起草 v0.1-6: SI 列の具体値は起草担当の案 | 直した | 案のままレビュー対象とし、依頼者裁定 U-5 (CONTROL_MAPPING への追記) と同時に確定 (設計 §8) |
| 起草 v0.1-7: X-4 は却下ではなく U-2 送り | 直した | X-4 は「却下案の節に置いた U-2 の参照」として残す (設計 §4)。U-2 は (i) で裁定 |
| 起草 v0.1-8: `CCR_DISPOSITION.md` の従属判断 14 の新設 | 直した | 1.8.0 = 13 の慣行どおり新設する (機械的帰結)。文言は WP-1 |
| 起草 v0.2-1: §6.1 の `capabilities` 配列に意味を結ぶ文が無い | 直した | 3 文目は足さず、rule の既存句を `common_baseline.capabilities` を主語にする句へ書き換え (v0.3 で §6.1 本文に反映) |
| 起草 v0.2-2: 裁定 5 の逐語文は 8 capability を名指すが既存 conditional 行の条件は 6 名 | 直した | 8 名のまま (床が unavailable を禁じる一覧であり既存行の条件の一覧ではない)。§6.2 の実測註は残す |
| 起草 v0.2-3: `operation_catalog` endpoint の `response` に指すスキーマが無い | 直した | `definitions.OperationCatalog` 新設で裁定 → 実測により設計レビュー 2-5 で `schemas.OperationCatalogDocument` + `definitions.OperationCatalogEntry` に書き換え、裁定文は消していない |
| 起草 v0.2-4: 裁定 11 の「凡例が `four adapters` = 全 adapter」の出所 | 直した | 計画文書 §0.1.3 の G-2 / G-3 行と `CONDITIONS.md` の C-27 行直後の凡例段落。結論は裁定どおり |
| 起草 v0.2-5: 3 複製の新ファイルが package data / 配布設定に触れる要否 | 直した | WP-3 で実測する (契約 JSON の複製の設定を流用できるかを見る)。設計はこれ以上決めない |
| 起草 v0.2-6: U-4 (β) のとき endpoint と宣言 optional の併存 | 直した | 併存する旨を U-4 の表に 1 行追加。v0.3 で「endpoint は無条件」を版ゲート付きの意味に限定 (設計レビュー 2-6) |
| 起草 v0.3-1: v0.3 起草報告で上げた根拠の訂正 | 観察 | 採用 (根拠の訂正のとおり)。設計本文の操作面は変わらず、反映箇所は無い |
| 起草 v0.3-2: `rules` 6 番目の追加が `rules[-1]` の末尾比較 pin に当たる | 直した | 6 番目は末尾に追加 (時系列順)、pin を `rules[4]` の index 固定に改め、1.8.0 の確定文は 1 文字も変えない。`len(rules) == 6` (設計 §6.1、§6.5) |
| 起草 v0.3-3: `CONDITIONS.md` の Evidence 欄に未作成のテストファイル名を書けるか | 直した | C-27 の declared 期の先例どおり `(not yet created)` 付きで書き、参照解決の検査が緑であることを WP-1 の完了条件に (設計 §6.4、作業指示書 §2) |
| 起草 v0.3-4: 新設 2 schema が 1.2.0 の closed 列挙に載る必要があるか | 直した | 閉じた形 (`additionalProperties: false`) で書き closed 列挙に載せる。列挙の検査テストの緑を WP-1 の完了条件に (設計 §6.6、作業指示書 §2) |
| 起草 v0.3-5: §6 の条件付き註 (U-1 が (β) なら…) の扱い | 直した | U-1 = (α) で確定。条件付き註を「(α) で確定」に書き換え、(β) の分岐文は §5 の表にだけ残した |
| 起草 v1.0-1: A-1 の疑義本文 — 設計 §15 は索引のままでよいか | 観察 | 設計 §15 は索引のままでよい (裁定文は逐語で入っている) |
| 起草 v1.0-2: `test_contract.py` の行番号ずれ (:165 / :168 と裁定文の :167) | 観察 | 着手時に再実測する。裁定の内容 (index 固定、1.8.0 の確定文は不変、`len(rules) == 6`) は動かさない |
| 起草 v1.0-3: 1.2.0 の closed 列挙に機械検査が無い可能性 | 直した | WP-1 の完了条件に「実測して報告、無ければ監督へ」を置いた (作業指示書に記載済み) |
| 起草 v1.0-4: `assert n == 19` (`test_contract.py`:1414) の更新漏れ | 直した | 設計 §6.5 と作業指示書 WP-1 に追加済み |
| 起草 v1.0-5: control plane の宣言版を WP-3 で 1.9.0 (仮) に上げるか | 監督裁定待ち | 記載の監督裁定候補は「上げる」(`operation_catalog_url` は capability document 全体の宣言で、C-19 は data / control で同一文書を要求する)。**条件付き義務 (C-25 (3) 等) への影響を explorer で実測してから裁定する** (§3 の 1) |
