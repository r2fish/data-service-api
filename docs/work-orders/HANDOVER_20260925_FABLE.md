# 引き継ぎ — 2026-09-25 (フェーズ11 最低共通機能プロファイル R-29 / R-23 / R-16 の閉止。契約 1.9.0、C-28 / C-29)

**ファイル名の衝突に注意**: 本書は 2026-09-25 の最初の `FABLE` 系ファイル名を取った。同日に並走チャットが同名のファイルを作った可能性がある — merge 直前に main の `docs/work-orders/` を読み、衝突していれば本書の名前をずらす (`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 58)。

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `HANDOVER_20260924_FABLE7.md`。

## 1. 現在地

- **WP-3 変異の最終コードでの再実測 (受け入れ監査 観察 1 の対応、2026-09-25)**: `mutate: 16 mutations, 16 as expected, restores verified 14/14 files (sha256 x2)` (WP-3 の全 spec を G-1〜G-3 反映後の最終コード f522610 で監督が再実行、2026-09-25。O1a/O1b/O1c/O2/O3a/O3b/O4/O5a/O5b/O6/O6b/O7 (error)/O8a/O8b/G2/F2)

- worktree `.claude/worktrees/laughing-feistel-31c19a` (branch `claude/laughing-feistel-31c19a`)。基点は local main `0fee6e5`。**main には未 merge** である。keyset ページング (並走) は main に未 merge のままなので、**契約 1.9.0 / C-28 / C-29 / 従属判断 14 / R-106〜R-108 はこの番号で確定**した (設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` D-7)。
- commit 済み: WP-1 `c10fa63` (契約 1.9.0 の公表)、WP-2 `d635e70` (C-28)、WP-3 `f522610` (両 peer の 1.9.0 宣言と派生カタログの配布)。**WP-4 (本書を含む記録、Class D) は未 commit** — 監督が `tools/dev/finalize.py` で commit と merge を行う。
- 両 peer は data 面・control 面とも **1.9.0** を宣言し、両面で同じ `operation_catalog_url` を宣言する。
- 完了ゲート (label p11): `gate: 4056 passed, 2 subtests passed in 330.43s (0:05:30)`、judge=PASS、pg_database/pg_roles diff 0 (label p11、2026-09-25、log は監督チャットの scratchpad `dev-logs/`)。前 = `4022 passed, 2 subtests passed in 486.51s` (label r105b)。
- 台帳 v1.120。`security/CONTROL_MAPPING.md` は 3.2 (監督が完了ゲート後に適用済み。検証 = `pt: 58 passed` (`conformance-tests/test_control_mapping_register.py`、3.2 適用後、監督実測 2026-09-25)、変異 P1 (C-28 の Evidence 行から citation を落とす) 赤、P2 (Version 行を 3.1 に戻す) 緑 = 監査照合 (§5.6 のとおり Version 規約は登録テストが見ない)、`tools/check_doc_refs.py` 0 件、`tools/public_value_scan.py` 0 件)。
- push は停止中 (GitHub 課金上限、2026-09-09 以来)。
- worktree 内の `.r29-scratch/` (git 非追跡) に本項目の材料 (実装報告・変異表・レビュー本文・裁定表) がある。**worktree を畳むと消える。**

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| WP-1 (契約 1.9.0) | `common_baseline` (床: 10 operations、8 capabilities)、`capability_status.rules` の 6 番目、`version_binding` の 1.9.0 段落と obligations entry (無条件 2 件)、`endpoints.operation_catalog` と 2 schema (閉じた形)、従属判断 14、`spec/OPERATION_CATALOG.json` 20 operations | commit `c10fa63`、設計 §17 |
| WP-2 (C-28) | 12 段 1 本の scenario、6 adapter、宣言分岐なし。port v1.16 `attempt_filter_with_result` | commit `d635e70`、設計 §17 |
| WP-3 (両 peer 1.9.0、C-29) | 両面 1.9.0、`operation_catalog_url` の base 相対の導出 + env var 上書き、`GET /v1/operation-catalog` (runtime / developer 認証、無認証の面なし)、派生カタログ 3 複製 byte 一致、C-29 は 4 関数、port v1.17 | commit `f522610`、設計 §17 |
| WP-4 (記録) | 台帳 R-29 / R-16 / R-23 の閉止、R-106 / R-107 / R-108 の起票、§0.1.1 / §0.1.3、版数ログと引き継ぎ書の回転、設計 §17、作業指示書 §7.2、`security/CONTROL_MAPPING.md` 3.2 | 本変更セット |

**変異表の要約** (本体は `.r29-scratch/wp1-report.md`・`wp2-report.md`・`wp3-report.md`、非追跡):

- WP-1 (15 件、すべて赤): M1〜M9、M11、M12〜M12e (1.9.0 の確定文の逐語 pin)。M10 は監査照合 (7(A) の closed 列挙に機械検査が無い)。
- WP-2 (34 件、すべて期待どおり): 段ごとの N1〜N13 と両 peer 版 (N4b / N4c / N5c / N9b / N11b / S1 など)、隔離の実測 (N5_isolation は C-21 も赤、N5c_isolation と N9_isolation は緑 = C-28 だけが赤)、N14 は収集全体の error。
- WP-3 (15 件 + 再確認 5 件、すべて期待どおり): O1a〜O1c、O2、O3a / O3b、O4、O5a / O5b、O6、O6b、O7 (error)、O8a / O8b、F2 (隔離した surface が共有 control stack を作り直す欠陥の回帰)、G2 (MitateDB socket の隔離 surface の URL)。

**依頼者裁定 5 件 (2026-09-24。設計 §5 の【裁定】欄から逐語で複製)**:

- **U-1**: **依頼者裁定 (2026-09-24)。逐語**: 「U-1 / U-4 (連動): 「(α) 契約の義務にする」 — baseline と operation_catalog_url を契約 1.9.0 (仮) の無条件義務にする。」
- **U-2**: **依頼者裁定 (2026-09-24)。逐語**: 「U-2: 「(i) 現物の交差 + 床上げは別起票」 — baseline は両 peer が今日実行できる操作の交差。Mitate の実需 (solutionName の一意性、revision_preconditions、append_only) は 本項目では満たされず、MitateDB に row_addressability / revision_preconditions を足す新規起票 2 件 + 既存 R-49 に付け替える。」
- **U-3**: **依頼者裁定 (2026-09-24)。逐語**: 「U-3: 「(a) 最小形 + (c) を別起票」 — 本項目は両 peer が operation_catalog_url を宣言し byte 一致で配る (C-29) まで。参照クライアント (spec + base URL + key だけから要求を組み立てる共通コードで C-28 を wire plug に回す) は次の項目として起票。」
- **U-4**: **依頼者裁定 (2026-09-24)。逐語**: 「U-1 / U-4 (連動): 「(α) 契約の義務にする」 — baseline と operation_catalog_url を契約 1.9.0 (仮) の無条件義務にする。」
- **U-5**: **依頼者裁定 (2026-09-24)。逐語**: 「U-5: 「この文で裁定する」 — 裁定文 (逐語): 「C-28 / C-29 の証拠を security/CONTROL_MAPPING.md (形式 3.0) の既存 SI の Common 節に足し、版を 3.1 → 3.2 に上げる。新しい Security Invariant は足さない。本項目は Class D として扱う。」」

(U-1 と U-4 は 1 件の裁定である。)

## 3. 次の一手

作業指示書 `docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` §0・§6 の手順の残り。

1. (済) 監督が `security/CONTROL_MAPPING.md` に 3.2 を適用し、作業指示書 §5.7 の検証を行った (上記)。
2. 完了ゲートの集計行は本書・設計 §17・作業指示書 §7.2・台帳に記入済み (`gate: 4056 passed, 2 subtests passed in 330.43s`、judge=PASS、pg diff 0、label p11)。
3. (済) `evidence-auditor` (テンプレート 6) の受け入れ監査 1 回: 完了条件 38 件 = 充足 37 / 未充足 0 / 証拠不足 1 (U-2 の空白 1 文字。観察)。観察 3 件は同じ変更セットで直した (裁定表末尾)。
4. merge 直前に main を読み、契約版・条件番号・従属判断番号・起票番号 (R-106〜R-108)・台帳の版 (v1.120)・本書のファイル名が衝突していないことを確かめる (設計 D-7)。
5. `tools/dev/finalize.py` で WP-4 を commit し、main へ merge する。

## 4. 依頼者判断待ち・未決

- **依頼者判断待ちは無い。** U-1〜U-5 は 2026-09-24 に裁定済み (上の §2 と設計 §5)。
- **C-27 の HTTP 413** (`test_c27_same_digest_executes_once[MitateDB-api-http]`、WP-2 の conformance 全体実行で 1 回赤、単体は緑): 完了ゲートの結果 `gate: 4056 passed, 2 subtests passed in 330.43s (0:05:30)`、judge=PASS、pg_database/pg_roles diff 0 (label p11、2026-09-25、log は監督チャットの scratchpad `dev-logs/`) で判定した — failed 0 で再現せず、**観察** (起票しない。直列の全体実行でのみ起きる harness の rate window 密度の事象)として本書に残す (「裁定」節の WP-2 の行)。
- **道具の観察**: `tools/dev/pt.py` は `$SP` が未設定だと system temp にログを出す (監査の材料が scratchpad の外に出る)。§1.12 の 71 の 1 問はいいえ (製品の欠陥は抜けない) — 起票しない。
- **語の衝突の観察**: 候補文書 `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`:178 が「port v1.16」の語を使っており、WP-2 の port v1.16 と衝突する。その文書の所有者が改番する (本項目では触らない)。
- **起票 3 件**: 設計 §16 の (1)(2)(3) を台帳に **R-106** (MitateDB-api の `row_addressability`)、**R-107** (MitateDB-api の `revision_preconditions`)、**R-108** (参照クライアント) として載せた (3 件とも規模 L、起票のみ)。Mitate の実需は R-106 / R-107 と既存 R-49 が引き取り、`spec/README.md`:5-9 の目標の実行可能な証明は R-108 が引き取る。
- **push は停止中** (GitHub 課金上限)。

## 5. 本チャットで足した運用上の教訓

1. **引き継ぎ書の実測値を着手前に確かめる。** `HANDOVER_20260924_FABLE7.md` §3 は MitateDB の control plane を 1.7.0 と書いていたが、実測では両 peer とも 1.8.0 だった (作業指示書 §7.1 の訂正註)。
2. **declared 期の `CONDITIONS.md` の Evidence 欄にはテストファイル名を書けない。** 参照解決の検査 (main `2365955`) が入った後は、backtick 付きの未作成ファイル名が `file not found`、backtick 無しが naked token で赤になる。C-26 / C-27 の `(not yet created)` の先例は検査の導入前のもの。declared 期は証拠の形を散文で書き、ファイル名は `executable` にするときに書く。
3. **差し戻しは、監督の裁定を 1 件ずつ付けたファイルで渡すと 1 往復で済む** (`.r29-scratch/wp1-returns.md`・`wp2-returns.md`・`wp3-returns.md` の形)。
4. **`tools/check_comment_provenance.py --base` はレビュー用の手動の読みであり、CI は `--register` だけを掛ける。** 新しいコメントに履歴語 (review、R-N 等) を書かず、`docs/code-history/<peer>/` の CH-ID で指す。
5. **harness の不一致をキャッシュで隠さない。** r2db socket adapter の宣言 URL の食い違いは、隔離 surface の shallow copy が共有 control stack を自分の data port で作り直す欠陥だった (コードレビューが `_CONTROL_REBUILD_THRESHOLD = 1` の変異で実測)。原因を実測してから直す。
6. **実装担当のプロンプトで `$SP` を export させる。** 渡し忘れると `tools/dev/pt.py` のログが system temp に出る。

## 裁定

全件を載せる (`docs/work-orders/OPERATING_CONDITIONS.md` §1.15 の 77)。「直した」は同じ変更セット (WP-1〜WP-3 の各 commit) で反映済みの意である。出所: `.r29-scratch/rulings-wp1-review.md` (WP-1〜WP-3 のレビュー・再確認・疑義の裁定表をそのまま転記)、`HANDOVER_20260924_FABLE7.md` の「追記」節 (4 件)、commit `c10fa63` のメッセージ (WP-1 の再確認)、作業指示書 §5.4 の 6 (設計 §6.4 の v0.2 註の観察)。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 起草 v1.0-5 (`HANDOVER_20260924_FABLE7.md` の裁定表で「監督裁定待ち」): control plane の宣言版を WP-3 で 1.9.0 に上げるか | 直した | WP-3 (`f522610`) で両 peer の control plane も同じ commit で 1.9.0 にし、`operation_catalog_url` を両面に載せた。C-19 (`test_c19_client_self_sufficiency.py`:258) が両面の版の一致を要求する (作業指示書 §7.1 の訂正註) |
| WP-1 中断時の赤 1: `test_contract.py`:1103 の裸 assert (`atomic_mutation` not in `version_binding`) | 直した | 1.6.0 段落に限定した (作業指示書 §7.1 の訂正註 1) |
| WP-1 中断時の赤 2: C-28 / C-29 の declared 期の Evidence 欄のファイル名 (`test_conditions_register.py` の参照解決 / naked token) | 直した | declared 期は散文で書き、ファイル名は executable にするときに書く。検査器は変えない (§1.12 の 72。作業指示書 §7.1 の訂正註 2) |
| WP-1 中断時の赤 3: `test_every_executable_condition_has_a_marked_test` が 5 ファイルの収集で赤 | 観察 | `conformance-tests/` 全体の収集以外では意味を持たない見かけ赤 (作業指示書 §7.1 の観察の訂正註) |
| コードレビュー WP-1-1 [高]: 1.9.0 の依頼者確定文 (common_baseline / rules[5] / 1.9.0 段落 / obligations entry) に逐語 pin が無く、自作変異 R1〜R3 が緑のまま | 直した | §1.5 の 35: 確定文は契約側に逐語 pin を置く。`test_contract_pins_the_1_9_0_texts_verbatim` を足し M12〜M12e で赤を実測 |
| コードレビュー WP-1-2 [中]: CONTRACT_HISTORY Revision note 3 が行っていない契約編集 (1.8.0 列挙の延長) を記す | 直した | 記録を事実に合わせる。1.8.0 以前の確定文は動かさない |
| コードレビュー WP-1-3 [中〜低]: 設計 v1.0 の :707 / :790 / :997 / :998 が訂正註 2・3 と逆のまま | 直した | §1.8 の 56: 覆した根拠と日付を該当行に残し設計を v1.1 に |
| コードレビュー WP-1-4 [低] (a): obligations[-1] → 版検索で 1.8.0 entry の位置固定が消えた | 直した | §15 裁定 2 (rules[4]) と同じ index 固定 (obligations[6]) |
| コードレビュー WP-1-4 [低] (b): C-29 Status が設計 §6.4 の置換指示と字句で違う | 直した | 確定文言は逐語 (§1.5 の 36) |
| コードレビュー WP-1-4 [低] (c): CCR 7(A) 追補が存在しない (D) を名乗り「次項」が誤り、従属判断 14 に 2 schema の記録が無い | 直した | 記録の正確さ |
| コードレビュー WP-1-5 [低]: CCR_DISPOSITION:241 に「1.9.0 (仮)」が残る | 直した | 恒久記録 (spec/・conformance-tests/) に「(仮)」を置かない。番号自体は merge 直前に監督が振り直す |
| コードレビュー WP-1-6 [低]: test_contract.py:1217 / :93 のコメント字句誤り | 直した | — |
| コードレビュー WP-1 観察 1: 訂正註が `$SP` 配下の実測ファイルを根拠にし、:366/:367 の空行が無い | 直した | 監督が訂正註を書き換えた (explorer の要点を註に記載) |
| コードレビュー WP-1 観察 2: spec/README.md に 1.9.0 の段落が無い | 直した | 1.8.0 段落と同じ形で WP-1 に含める (§2.3 の「触らない」を差し戻しで上書き) |
| コードレビュー WP-1 観察 3: 報告に pt 件数の基点からの増減が無い | 直した | 差分から数えて報告に書く |
| コードレビュー WP-1 再確認-1 [低]: C-29 の Status 欄に裁定 R4(b) の逐語置換と違う字句 (`C-20..C-2N` の範囲と小文字で始まる文) が残る | 直した | 監督が字句を整えた (commit `c10fa63` のメッセージ「re-review: no return, 3 low wording items fixed by the supervisor」) |
| コードレビュー WP-1 再確認-2 [低]: `spec/CONTRACT_HISTORY.md` の Revision note 3 に意味の通らない句 ("stays unmoved, 1 character") | 直した | 同上 (`c10fa63`) |
| コードレビュー WP-1 再確認-3 [低]: 設計 v1.1 の改版履歴の行番号が 1 行ずれ、v1.1 の行の位置が昇順に合わない | 直した | 同上 (`c10fa63`。設計の v1.1 行は :708 / :791 / :998 / :999 を指し v1.0 の後に置かれている) |
| コードレビュー WP-2-1 [中〜高]: SI-10 を観測する assert が無い | 直した | 段 (4) に非開示 assert + 変異 N4b (§1.5 の 34。SI 列は設計どおり残す) |
| コードレビュー WP-2-2 [中]: 段 (4)→(5) が同一要求体を運ばない | 直した | 設計 §7 段 (5) の期待どおりに修復 (details.field を解決して同じ dict を直す) |
| コードレビュー WP-2-3 [中]: 段 (9) が演算子ごとの部分集合を見ない | 直した | 期待集合の等価 assert + 変異 N9b |
| コードレビュー WP-2-4 [中]: 変異表が完了条件 3 を満たさない (段だけ赤の未実測、N11、N9' 欠落、MitateDB 側なし) | 直した | 別 entry で実測、N11b・N9'・MitateDB 版を追加 |
| コードレビュー WP-2-5 [低〜中]: nullable:false を作るが観測しない | 直した | 段 (4) に null 拒否の観測 + 変異 N4c (床 operations 10 番目) |
| コードレビュー WP-2-6 [低]: lte/gte で R == page.size (設計 D-6) | 直した | page.size > 挿入行数に組み直す |
| コードレビュー WP-2-7 [低]: 軽微な省略 5 点 | 直した | — |
| コードレビュー WP-2-8 [低]: N14 は conftest 全体が壊れ、完了条件 4 の文言と違う | 観察 (訂正註) | より安全側。作業指示書 §7.1 に訂正註、実装は変えない |
| コードレビュー WP-2-9 観察: CONFORMANCE_ADAPTER_V1.md が 1.15 のまま / 「port v1.16」の語が候補文書と衝突 | 直した / 観察 | v1.16 の行を足す。候補文書 OBJECT_STORAGE_BINARY_API_V0_1.md:178 は触らない (その文書の所有者が改番) |
| コードレビュー WP-2 C-27 413 分析: WP-2 が原因ではない (control rate window の session 間共有、R-105 の高速化) | 観察 | 完了ゲート (failed 0) で再現せず。直列の全体実行でのみ起きる harness の事象 |
| コードレビュー WP-2 再確認-1 [低〜中]: SI-10 assert の message 側が常に空振り (ConformanceDenial は message を持たない) | 直した | native cause の文字列を検査する形に直し変異 S1 で実測 (露出が無ければ句を消して主張を details のみに) |
| コードレビュー WP-2 再確認-2 [低〜中]: 「段 (5) は C-21 とも赤」の訂正が強すぎる (形を保った N5c では C-28 だけ赤) | 直した | N5c / N5c_isolation を表に足し備考を直す。設計 §11 の見込みは N5c で成立 |
| コードレビュー WP-2 再確認-3 [低]: CONFORMANCE_ADAPTER_V1.md の版数行が 1.15 のまま、§26 の見出し書式 | 直した | — |
| コードレビュー WP-2 再確認-4 [低]: 段 (5) の path 解決失敗が素の KeyError | 直した | 段名入り assert に |
| コードレビュー WP-2 再確認 撤回: 前回指摘 7 の行番号 :1672 はレビューの数え誤り | 観察 (撤回) | 実装担当が正しかった |
| WP-3 疑義 1: `operation_catalog_url` の本番配線 (env var vs platform_declarations 統合) | 直した (訂正註) | 既定値を surfaces.data.base_url + 契約 path から導出、env var は上書き。DB 統合は起票しない |
| WP-3 疑義 2: C-29 を 4 関数に分割 (26 passed) | 直した (訂正註) | 二段構造は保たれる。期待形を実測値に読み替え |
| WP-3 疑義 3: O6 は byte 比較が先に発火し schema_check 単独の赤を分離できない | 直した | O6b (3 複製に同じ余分キー) を追加 |
| WP-3 逸脱 4: socket adapter の原因未特定キャッシュ化 | 直した | レビューが原因を実測で確定 (iso の shallow copy が共有 control stack を自分の port で再構築)。iso の control send を親に束ね、両 socket adapter のキャッシュを削除 (F-2) |
| WP-3 逸脱 5: 新規コメントに履歴語、CH-ID 登録なし (監督実測 provenance 44 FAIL) | 直した | 履歴語を消し docs/code-history/<peer>/ に CH-ID を登録 (--base の (2)(3)(5) は 0 件、--register OK) |
| WP-3 監督実測: conformance 全体に skipped 1 | 直した | test_c29 の `pytest.skip` 経路を assert に置換 (C-19 と同じく 6 plug 全部に control 面がある)。完了ゲートは skipped 0 |
| WP-3 逸脱 3: peer-local の両面一致テストの非対称 | 観察 | 同名 helper ではなく同型性規律の対象外 |
| コードレビュー WP-3 F-1 [高]: 導出 URL が `/v1/v1/operation-catalog` (404) | 直した | 導出関数を 1 つにし origin + 契約 path。利用者が気づく欠陥 |
| コードレビュー WP-3 F-2 [高]: socket adapter のキャッシュは iso の shallow copy が共有 control stack を自分の port で再構築する不一致を隠すだけ (実測で確定) | 直した | iso の control send を親に束ね、キャッシュ削除 (レビューの R1/R2 で実測) |
| コードレビュー WP-3 F-3 [中]: composition root を通る両面一致テストが無い (あれば F-1 を検出した) | 直した | 各 peer 2 件 |
| コードレビュー WP-3 F-4 [中]: runbook / env example / README 未記載 | 直した | 裁定 (C) の未了分 |
| コードレビュー WP-3 F-5 [中]: 無認証面が無いことを固定するテストが無い | 直した | 設計 §8.2 の主張を実測にする + 変異 O8 |
| コードレビュー WP-3 F-6 [低〜中]: 変異表の穴 (O1 の -x、O3 欠落) | 直した | — |
| コードレビュー WP-3 F-7 [低]: 主張と実測の食い違い (CONFORMANCE_ADAPTER_V1 §27、キャッシュ docstring、報告) | 直した | — |
| コードレビュー WP-3 F-8 [低]: route path がリテラル | 直した | 同梱契約から読む |
| コードレビュー WP-3 確認: provenance の残 FAIL は §4.1 (1) code changed 12 件 + 新規 2 ファイル (CI は --register のみ、緑) | 観察 | `--base` はレビュー担当の手動読み (設計 D-4) |
| コードレビュー WP-3 再確認 G-1 [低〜中]: 導出の意味が裁定・文書 (origin + path) と実装 (base 相対) で食い違う | 直した | 実装の意味を採り文言・期待値を揃える (prefix 配備でも到達)。訂正註で前裁定を上書き |
| コードレビュー WP-3 再確認 G-2 [低]: MitateDB socket の iso が operation_catalog_url を渡さず docstring が偽 | 直した | r2db と同じく渡す |
| コードレビュー WP-3 再確認 G-3 [低]: O8a の形が無認証配布を模していない / O3 の「C-29 (ii) も赤」は構造上成立しない | 直した / 観察 (訂正註) | O8a を 200 配布形に。O3 の備考と訂正註 |
| 設計 §6.4 の v0.2 註が残した観察 (既存行の `four adapters` の表記の陳腐化、設計レビュー 1-11。作業指示書 §5.4 の 6) | 観察 | `HANDOVER_20260924_FABLE7.md` の裁定のまま。`conformance-tests/CONDITIONS.md`:60 の凡例により `four adapters` は全 registered adapter (現在 6) を指す。C-28 / C-29 行は `six adapters` と書いた |
| コードレビュー WP-1 再確認 (4): `spec/` / `conformance-tests/` に「(仮)」「provisional」が 5 件残る | 観察 | 5 件とも main に以前からある既存文 (`provisional gate`、CCR_DISPOSITION:227)。WP-1 が持ち込んだものは 0 件で、既存文は消さない |
| コードレビュー WP-1 再確認 (4'): 報告の残存件数 (4 件) が実測 (5 件) と食い違う | 観察 | 記録の数え違い。判定に影響しない |
| コードレビュー WP-4-1 [中]: 完了ゲート (f522610、3.1) の集計行が 3.2 適用後の証拠として記録されていた | 直した | 記録を「ゲートの対象は f522610、3.2 の検証は §5.7 (register 58 passed、P1 赤、P2 緑 = 監査照合)」に改めた |
| コードレビュー WP-4-2 [低]: SI-05 の Evidence 行が assert していない観測 (catalog だけから組む) を主張 | 直した | 実在 assert (enum / nullable の拒否) だけを書く |
| コードレビュー WP-4-3 [低]: 裁定表に「差し戻し」の値、C-27 が判定待ちのまま | 直した | 「直した」に統一、C-27 は観察 |
| コードレビュー WP-4-4 [低]: 台帳 §0.1.1 から旧 Evidence 13 件の 1 文が消えた | 直した | 前回実測の括弧に復元 |
| コードレビュー WP-4-5 [低・不確実]: U-2 の逐語が設計 §5 と `.r29-scratch` の記録で空白 1 文字違う | 観察 | 原文 (依頼者の回答) は再取得できない。設計 §5 (c10fa63 で commit 済み) を正とし、両者の差は空白 1 文字 |
| コードレビュー WP-4-6 [低]: 「触らない」の外の変更 (test_c28 docstring、CONFORMANCE_ADAPTER の「(仮)」) に訂正註が無い | 直した | 作業指示書 §7.1 に訂正註 |
| コードレビュー WP-4-7 [低]: 台帳 v1.120 の版数行が §0.1.2 と R-49 の変更を挙げていない | 直した | 版数行に追記 |
| 受け入れ監査 観察 1 [低]: WP-3 の変異 11 件が G-1〜G-3 後の最終コードで再実測されていない | 直した | 監督が全 spec を最終コードで再実行 (結果は設計 §17 / 本書「現在地」に記載) |
| 受け入れ監査 観察 2 [低]: SI-09 の C-28 行「echoed in full」が C-28 の観測を超える (全文一致の固定は C-06 v3) | 直した | 行を実在の観測 (確認なし拒否 → 句の提示で実行 → 該当行だけ削除) に改め、全文一致は C-06 と明記 |
| 受け入れ監査 観察 3 [低]: 裁定表 3 行の理由欄が差し戻し時の要求文のまま | 直した | 何で直ったかに書き換え |
| 受け入れ監査 証拠不足 1 件: WP-4 完了条件 6 の U-2 逐語 (設計 §5 と記録ファイルで空白 1 文字差) | 観察 | WP-4-5 と同じ。設計 §5 を正とする |

受け入れ監査の指摘: 監査担当のパケット (後記)。
