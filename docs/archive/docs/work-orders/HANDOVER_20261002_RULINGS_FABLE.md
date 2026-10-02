# 引き継ぎ書 — 2026-10-02 台帳 R-118・R-30・R-120 の依頼者裁定資料 v0.1 作成済み・裁定待ち

本書は cloud session (claude.ai の Claude Code、root のコンテナ、PostgreSQL 無し) で作った依頼者裁定資料 1 本の記録であり、依頼者裁定の取得・記録と着手を作業機の監督チャットへ引き継ぐ。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、対象の正本は台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §8.1 の R-118・R-30・R-120 の行 (`RM`:475・:456・:476)。資料は `docs/design/REQUESTER_RULINGS_R30_R118_R120_V0_1.md` v0.1 (以下「資料」)。本書の略記: `CM` = `security/CONTROL_MAPPING.md`、`RC` = `docs/design/REFERENCE_CLIENT_V0_1.md`、`CA` = `docs/design/CONFORMANCE_ADAPTER_V1.md` (資料の冒頭の局所定義と同じ。資料:19)。

## 1. 現在地

- 本 session は資料を 1 本作っただけで、**何も確定していない**。台帳行・`spec/`・`security/`・peer には触れていない。
- 変更は branch `claude/relaxed-pasteur-ogu6ds` (origin に push 済み) の commit `d6d1bcd` (資料本体、181 行、Class A) にあり、本書の commit がその上に乗る。基点 rev は local HEAD `05a60c0` (origin/main `4241b55` より先の、台帳 R-121 の閉止を含む local main 相当)。local main には何も入れていない。cloud session からの push は作業ブランチのみで、CI は走らない (`OC` §3 の 7)。
- 静的検査: pre-commit の 3 hook (public-value-scan / check-doc-refs / ledger-check) は Passed。`tools/check_doc_refs.py` 0 件、`tools/public_value_scan.py` 0 件。
- 記録の置き場: 最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R108_FABLE.md` の archive 移動は本 session では行っていない (§3 の 5)。

## 2. 本チャットで閉じたもの

- 閉じた台帳行はない。閉じたのは資料の作成までの手順である: 探索 (`explorer` 3 起動、model 指定なし)、読解 (`reader` 3 起動)、枠決め、起草 (`drafter` 1 起動 + 差し戻し 1 回)、設計レビュー (`reviewer` 1 起動、モード 設計レビュー、Class D 宣言、担当観点 指定なし、11 件。全件「直す」で反映)、静的検査、commit。
- 台帳行の起票文の検証結果 (詳細は資料の各 §x.6。資料:68-73・:117-120・:165-169):
  - R-118: 起票文の `:432` は現物 `spec/data-service-api.v1.json`:453、契約は 1.12.0 ではなく 1.14.0。期限句は :453 のほか :40 (c)・:636 の 3 箇所。data 面の stub (起票文に無い事実) を補った。台帳の「Class D 見込み」は案 B (撤去) にだけ当たる (案 A は C)。
  - R-30: 起票文の行番号は r2db `main.py` で約 +103、MitateDB `main.py` で約 +50 ずれている。「現行配備は各 1 Application」は文書上の記述で、実配備数は未確認。
  - R-120: 起票文は `alter_field` だけを挙げるが、`add_field` (nullable: false) にも同じ窓がある (資料で補った)。「窓は数 ms」は未計測。
- 本 session で**できなかったこと**: R-120 の窓の再現 (PostgreSQL 無し。構造のみ)、R-30 の実配備数の確認。
- レビュー報告・差し戻し・枠は cloud session の scratchpad にあり持ち越せないので、全件を本書の「裁定」に写した。

## 3. 次の一手 (作業機の監督チャット)

1. `git fetch origin claude/relaxed-pasteur-ogu6ds` → `git worktree add .claude/worktrees/rulings -b rulings origin/claude/relaxed-pasteur-ogu6ds` (共有ツリーを checkout しない。`OC` §1.2 の 14)。
2. 依頼者に資料 §0 の 3 問 (本書 §4 の 1) を提示し、各行の (i)/(ii) の裁定を得る。
3. 裁定を逐語で資料の各「裁定 (逐語):」欄 (資料:66・:115・:163) に記録し、資料を v0.2 に上げる。台帳 §8.1 の R-118・R-30・R-120 の各行に【追記 (v1.151 見込み。番号は main を読んで振る)】として依頼者裁定の逐語と資料のパスを記す (`OC` §1.7 の 51、§1.16 の 79)。台帳の版上げは変更セットごと (`OC` §1.13 の 75)。同じ変更セットで版数ログの 6 版目の行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ回す (`OC` §1.16 の 78)。
4. 完了ゲートは文書だけの変更セット (Class A) には要らないが、台帳の版上げの変更セットは `tools/dev/finalize.py` で commit し、`ledger.py --check` が緑であること。
5. 最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R108_FABLE.md` を `docs/archive/docs/work-orders/` へ `git mv` する (`OC` §1.16 の 78)。本書の commit は cloud session で行い、その変更セットには入れていない (本 session の範囲外) ので、作業機の最初の変更セット (3 の台帳の版上げ) で同時に移す。
6. 裁定後の着手 (いずれも作業機で完了ゲート):
   - R-118 (i) なら: 規模 S・Class C (台帳行が指示書)。1.15.0 の変更セット (期限句 3 箇所、`spec/CONTRACT_HISTORY.md`、pin、両 peer の版文字列・コメント・README)。
   - R-30 (ii) なら: 規模 M・Class D。SI-00 の註と `CM` の SI-00 節、env example、runbook、`docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`:205。
   - R-120 (i) なら: 規模 M・Class B+D。設計 (lock 順序) → 作業指示書 → 2 cell の再現 test (赤→緑) → `CM`:1518-1534。

## 4. 依頼者判断待ち・未決

1. 3 つの裁定の問い (資料 §0 の表の逐語。資料:7-11):

| 行 | 裁定の問い | 推奨 |
|---|---|---|
| R-118 | (i) alias の期限句 3 箇所 (`spec`:453・:40 (c)・:636) を「保持し、撤去は major 版でのみ行う」の文に書き直す minor 版 (1.15.0。alias と両 peer の route・stub は残す) にするか、(ii) 今 alias を撤去する major 版 (2.0.0) にするか | (i) (案 A 書き直し) |
| R-30 | (i) SI-00 の containment を DB 側の境界で満たすものと文書で確定し、1 process が複数 Application の DSN を保持する構成を正式に許すか、(ii) 本番の serving set を 1 process 1 Application に限る配備姿勢を宣言し、SI-00 の文書にその姿勢を本番の既定として記すか | (ii) (案 B 配備姿勢の宣言) |
| R-120 | (i) 着手し、MitateDB の 3b と同型の実体単位の共有 lock (案 B) で設計に進むか、(ii) 着手せず `CM`:1534 の開示のまま置くか | (i) (着手する。閉じ方は案 B) |

2. 資料 §5 の未確認事項 (資料:171-175): R-30 の実配備の Application 数と、複数 Application の serving set を組む test fixture の有無。R-120 の窓の再現、「数 ms」、in-process plug が PostgresCell を使うか、案 B の往復 +1 の実測。R-118 の旧形 (alias を自前で結合する) client の実在。
3. 資料が指摘した陳腐化参照 (`RM`:475、`RC`:296・:351・:352。資料:73) の修正を、裁定後の変更セットに含めるかは監督が決める。本 session では直していない。
4. `OC` §0 の対応表に `CM`・`RC`・`CA` のキーを足すか。資料は冒頭で局所定義している (資料:19)。`docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md`:14 は `RC` を別の意味 (`r2db-api/conformance`) で使う。

## 5. 運用上の教訓

- cloud session で文書だけの変更セット (Class A) は、探索 → 読解 → 枠 → 起草 → レビュー → 反映 → 静的検査 → commit → push まで回せる。
- 台帳行の行番号は起票時点のもので、資料は必ず現物で取り直す。本件では 3 行ともずれていた。
- レビューの指摘を直す前に監督が現物で確かめる。本件では 11 件中 6 件を監督が `file:line` で確認してから差し戻した。

## 6. 裁定

`OC` §1.15 の 77。材料はレビュー担当の報告 1 通 (設計レビュー、Class D 宣言、担当観点 指定なし、11 件)。11 件とも同じ変更セット (commit `d6d1bcd`) で直した。番号はレビュー報告の番号。

レビューの確認範囲: 確認していない観点は、読解ノートとの突き合わせ、`RC` 以外の陳腐化参照の全数、R-120 の窓の実行再現、perf の README (`tools/PERF_BASELINE_README.md`:138-149) と `tools/perf_baseline.py`:1651-1700 の精読 (行の存在のみ確認)。skip / xfail は該当なし。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー 1 (R-118 案 A が期限句を 1 箇所しか直さず、自己矛盾が残る) | 直した | 案 A の対象を期限句 3 箇所 (`spec`:40 (c)・:453・:636) とし、触る経路に `spec/CONTRACT_HISTORY.md` 3 箇所・MANIFEST・両 peer のコメント・README 3 箇所を足し、§0 と問い (i) を合わせた |
| レビュー 2 (R-118 案 B のクラスは C+B でなく D) | 直した | 案 B のクラスを D (`CM` の SI-00 両 peer 節ほかの alias 証拠が消える) + C + B とし、§2.6 を「案 A は C、台帳の Class D 見込みは案 B に当たる」に直した |
| レビュー 3 (R-30 案 B の利得が platform DSN を数えていない) | 直した | 利得を「Application の data (runtime / developer DSN) は 1 Application 分」に限り、platform DSN の到達範囲はどの案でも全 Application に及ぶことを §3.1・§3.2・案 B の欠点・§3.4 に足した |
| レビュー 4 (R-30 案 B の註の「保証の外」と案 C の欠点の非対称) | 直した | 註を「containment は DB 側の境界で満たし、1 process 1 Application は本番の既定」に改め、自由の喪失を案 B の欠点へ移し、opt-in flag は B より強い (fail-closed) と書き直した |
| レビュー 5 (R-120 の窓は add_field (nullable: false) にもある) | 直した | 問題文と所在に `add_field` (`r2db-api/src/r2db_api/postgres.py`:2257-2278) と MitateDB の 3 箇所を足し、案 B の排他の列挙と共通条件を現物に合わせ、§4.6 に補足した |
| レビュー 6 (R-120 の選択肢の漏れと非推奨案の欠点の誤り) | 直した | 案 F (application 単位の共有 schema lock) を足し、案 C の「advisory より重い」を削って `CM`:217 との衝突を足し、案 D の「jsonb 値への enum CHECK」を削った |
| レビュー 7 (R-120 推奨の裏付けの言い過ぎ) | 直した | lock 待ち 0 / 4856 は schema 操作の無い負荷での値で往復 +1 の費用を示さないと書き、「MitateDB は既に緑」を「3b により同じ性質を満たす (共通条件は未作成)」にした |
| レビュー 8 (R-118 の同一 origin の URL 重なりの読みと選択肢の漏れ) | 直した | `spec`:40 の (5) の読みが分かれることと、nginx 雛形で alias を control upstream へ回す配備側の回避 (Class B) を付随作業の候補として §2.3 に足した |
| レビュー 9 (行番号のずれとクラスの書き間違い) | 直した | pin・件数・schema lock・`_insert` の行番号を現物に直し、撤去時の一覧に `conformance-tests/test_contract.py`:2451 を足し、env example を Class B に、§1 のクラス要約に `_ISOMORPHIC_TARGETS` と公開ゲートを足した |
| レビュー 10 (契約版数「無し」と `RM`:600 の証拠列の読みが書かれていない) | 直した | §1 に「契約版数の更新は `spec` を触る案にだけ掛かる」の 1 文を足した |
| レビュー 11 (R-118 案 A の文言が次の major の内容を先に縛る) | 直した | 主案を「major 版でのみ撤去しうる (時期は定めない)」とし、「次の major 版で撤去する」は強い変種として併記した |
