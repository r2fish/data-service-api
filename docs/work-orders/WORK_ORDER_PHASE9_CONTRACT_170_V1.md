# フェーズ9 作業指示書 — 契約 1.7.0「宣言と検証」

- 版数: **v1.0 (2026-09-07、起草)**
- **起草時の整合 (2026-09-07)**: **起草者の疑義 4 件に対する監督裁定 T-1〜T-4 が設計 v1.3 として確定したので、本書を設計 v1.3 と突合して整合させた (版数は v1.0 のまま。差し替え箇所は §2 WP-1 の変更一覧 #21・(9)〜(11)・完了条件 25 / 30 と対応する変異・禁止事項 6、各 WP の「同型性テストの対象」、§3 の 9、§4、§5、§6 の訂正註 1 / 2)**
- 正本設計: `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` (**v1.3、確定**)。**§3 の D-1〜D-9 は監督確定、§5 の U-1〜U-8 は依頼者裁定の委任に基づく監督確定であり、いずれも再審議しない** (計画文書 §9 手順 4)。**本書は WP 分割と発注のみを扱う** — 裁定の根拠・却下案・実装の具体形・命題の言葉遣いは設計文書が正本であり、本書はそれを重複させない。**設計と本書が食い違ったら設計が正であり、本書の誤りとして監督へ差し戻すこと** (フェーズ6 §11 L6-18 の流儀。訂正註は本書 §6 に置く)
- 上位計画: `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.2)。**§4 (P-1〜P-9)・§5 フェーズ9 節・§9 (着手手順) が正本**であり、設計 §1.1 / §2.1 がそれを転記済みである。本書は再導出しない
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260907_FABLE.md` (第 15 次)。**§4-5 (運用規律) と §5 (教訓) は全項が本フェーズにも掛かる。** **本フェーズは第 16 次引き継ぎを起こす** (WP-4)
- 先行作業指示書: `docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md` (v1.0)。**§0.1 の常設規律 7 項目・§0.1b の速度規律 5 項目・完了ゲートの実測規律・禁止事項・コミット規約・「完了条件番号 → 変異」対応表の書式を本書がそのまま引き継ぐ**
- 体制: Fable 監督/判断/コミット、Sonnet 実装 (**コミットしない**)、Opus 起草/独立レビュー/受け入れ監査
- 設計レビュー回数: **2 回** (契約を触るフェーズ。計画文書 §9 の 3)。**1 回目は v1.0 に対して実施し v1.1 へ全件反映、2 回目は v1.1 に対して実施し v1.2 へ全件反映済みである。追加の設計レビューは行わない** (**v1.3 はレビューではなく、本書の起草中に生じた疑義 4 件に対する監督裁定 T-1〜T-4 の反映である**)
- **契約は変わる**。本フェーズは **1.6.0 → 1.7.0** であり、`spec/CCR_DISPOSITION.md` に**従属判断 12** を新設する。**契約 JSON の 3 複製は同一コミットで同一バイトに更新する**

---

## 0. 位置づけ

### 0.0 正本と委任

1. **設計 v1.3 が正本である。** §3 D-1〜D-9 が監督確定、§4 A-1〜A-10 が却下確定、§5 U-1〜U-8 が確定、§6 が conformance への影響、§8 が WP 分割の素案、§9 が完了ゲート、§10 が台帳である。**本書はその実施発注のみを書く。** **v1.3 が足したのは監督裁定 T-1〜T-4 である** — **T-1** (result schema の `plan` = U-8 #29)、**T-2** (`_ISOMORPHIC_TARGETS` の行追加は監督の pair-closing commit)、**T-3** (xfail は 8 → 4 → 0)、**T-4** (defined ⊆ declared の逆方向 assert を C-11 に、版ゲート無しで WP-1 が足す)。
2. **依頼者裁定 (2026-09-07、逐語) は設計 §5 冒頭にある。** 依頼者は「判断しなければならないものが出たら監督の推奨で進め、後で報告する」ことを委任した。**その委任のもとで監督が確定した項目 (U-1〜U-8、設計レビュー 1 回目に伴う追補、設計レビュー 2 回目に伴う追補 2) は、いずれも設計 §3 / §5 に逐語で記録されている。** **本書はそこから参照し、複製するときは逐語で複製する** (常設規律 4)。
3. **確定文言は 3 系統ある。** (i) **契約文案 (英語)** = 設計 §3 の各 D の「契約文案」ブロック、(ii) **依頼者裁定の逐語** = 設計 §5 冒頭、(iii) **監督裁定の逐語** = 設計 §5 の各 U の「確定」欄と、追補・追補 2・**追補 3 (T-1〜T-4)** として §3 / §5 / §6 / §8 / §9 に反映された各項。**いずれも確定文ファイル (`{scratchpad}/phase9-rulings.md` と `{scratchpad}/requester-ruling-20260907.md`) から設計へ複製されたものであり、実装は設計から複製する。** **言い換え・要約・語順の入れ替えを行わない。**
4. **本書が設計から委任を受けて確定した事項は 4 件だけである** (設計が明示的に「作業指示書で確定する」と書いた箇所):
   - **(a) `alter_field` の契約文の置き場所** (設計 §5 U-8 #2) → **`structured_operations.alter_field` の独立節に置く。** 根拠: `structured_operations` には `upsert` / `revision_preconditions` という独立節の前例があり、`SchemaOperationRequest.properties.operation` の description に埋めると schema 側の 1 値が肥大する (P-7)。
   - **(b) 新規ファイル名** (設計 §6.5「ファイル名は素案。作業指示書で確定する」) → **本書 §2 の各 WP「対象ファイル」に書いた名前で確定する。**
   - **(c) MitateDB の `alter_field` 用 backend メソッド名** (追補 2 S-g「名は作業指示書で確定」) → **`alter_field_constraints` で確定する。**
   - **(d) peer サブ WP のテストファイル接頭辞** (設計 §8.1) → **本書 §2 の各 WP「対象ファイル」に書いた名前で確定する。**
   - **これ以外に本書は設計外の決定を持たない。** 設計に無い検査・機構・語彙が要ると判断したら、**実装前に監督へ上げる** (常設規律 5)。
   - **起草時に本書が監督へ差し戻した疑義 4 件は、監督裁定 T-1〜T-4 として設計 v1.3 に入った** (§6 訂正註 1 / 2 を参照)。**本書の決定ではなく、設計の確定である。**

### 0.1 常設規律 (フェーズ7 §0.1 / フェーズ8 §0.1 を逐語継承。全 WP に適用)

1. **空振り禁止**: 新規テストは観測対象が 1 件以上あることを assert する (パラメータ化された全 plug/adapter で)。「このテストは X を固定する」と書くなら、X を壊す変異を全 plug で赤にした実測を報告に添える。
2. **変異先行**: 完了条件 1 項目につき、それだけを壊す変異を 1 つ対応付ける。対応する変異の無い完了条件は残さない。
3. **主張は実測の後**: docstring / CONDITIONS / runbook の断言 (「load-bearing」「必ず赤」等) は変異結果を得た後に、その数値・テスト名を引用して書く。レビュー・監査は「主張 vs 実測」を独立項目として突合する。
4. **確定文言はファイル経由**: 依頼者確定の契約文・裁定文は確定文ファイル (本フェーズでは設計 §3 / §5) から複製し、言い換えない。契約側には確定文を逐語 assert する文字列ピンのテストを置く。
5. **設計外の拡張は実装前に上げる**: 設計に無い検査・機構は実装前に報告し、監督裁定を得てから実装する。
6. **同型性テスト**: 両 peer に同名で置くヘルパは、peer 名・パッケージ名・パス・空白を正規化して diff する同型性テスト (両 peer 同名 `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`、対応表は各 peer の `tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS`) で一致を固定する。peer 間でコードを共有しない慣行は維持する (依頼者裁定 2026-09-03、案 (a))。
7. **実行規律**: テストは前景 Bash で直列、timeout パラメータ 600000 を明示、`ps` で他の pytest が無いことを確認してから。変異の復元は scratchpad backup からのコピー (`git checkout` 禁止)、`sleep 3` 後に sha256 を 2 回照合、変異文字列を全文 grep。

**対応表の書き方 (規律 2 の運用)**: 各 WP の末尾に「完了条件番号 → 変異」の対応表を置く。**本フェーズでは、実装を伴う WP (WP-1 / WP-2a〜2e / WP-3a〜3e) の完了条件は 1 項目につき変異 1 つを必ず持つ** — **変異の無い項目は完了条件に書かず、同じ WP の「監査照合項目」に落とす** (照合対象と記録先を明示する)。**WP-4 は成果物がすべて文書・記録であるため全項が監査照合である** (フェーズ8 WP-6 と同じ形)。

### 0.2 速度規律 5 項目 (第 13 次 §2.4 / 第 14 次 §4-3 から転記。全 WP に適用)

1. **完了ゲートは監督が単独実行し、その集計行だけを正本にする。**
2. **subagent には suite 全体を回させず、対象ファイル・対象テストの前景直列実行に限る** (`timeout` 600000 明示)。
3. **レビュー・監査は `--collect-only -q` と静的照合を主とし、変異は自作分のみ最小回数。**
4. **時間を食う vector は「構成値に比例しない形」へ作り替える。**
5. **並列化は集計行が逐次と一致することを実測してから採る。**

### 0.3 使用テンプレート

| 役割 | テンプレート | 適用 WP |
|---|---|---|
| **Sonnet 実装** | **テンプレ 2** | WP-1、WP-2a〜2e、WP-3a〜3e |
| **Opus コードレビュー** | **テンプレ 5** | 同上 (各 WP の実装完了後、独立に 1 回) |
| **Opus 証拠監査** | **テンプレ 6** | 同上 (レビュー後、独立に 1 回) |
| **Opus 起草 → 監督 → Opus 証拠監査** | **テンプレ 4 → テンプレ 6** | WP-4 |

**レビュー・監査は実装担当と別 instance が行う。** **レビュー担当は自分で変異を作る** — 報告された変異だけでは足りない (第 15 次 §5 の 2 番目の教訓)。

### 0.4 本フェーズ固有の規律

1. **宣言と挙動は同一コミットである** (P-3、設計 D-1 (4))。**capability の gate 撤去・status の `enabled` 化・挙動の実装・その peer のローカルテストは、capability ごとに 1 コミットに収める。** **先に宣言だけを上げない。**
2. **版フリップ (`contract_version` 1.6.0 → 1.7.0) は、その peer の無条件義務 (R-3 / R-7) を入れる最後の WP (2e / 3e) と同一コミットである** (設計 D-1 (5)、U-7 = (A))。**peer ごとに独立したコミットを作り、完了ゲート内で連続して main にマージし、フリップ間に他のコミットを挟まない。**
3. **`conformance-tests/` を触るのは WP-1 だけである** (設計 §8)。**peer WP が conformance を直す必要が出たら、直さずに監督裁定を仰ぐ。**
4. **`xfail(strict=True)` の `strict` を落として緑にしない。** **緑にする正しい手段は、その peer が宣言と挙動を揃えることだけである** (第 15 次 §5 の最終項)。**版ゲートの条件はファイル編集で外さない** — 実行時に plug の宣言を読む形である (追補 R-h)。
5. **`skip` を使わない。** `skipped` は 0 のままである。
6. **`COLLECTION_FLOOR` を WP の途中で上げない。** 着手時点の値は **2340** であり、**最終更新は監督が完了ゲートで行う** (設計 §6.7 / §9 の 4)。
7. **新しい共通 Security Invariant を足さない** (設計 §2 C2 / §7)。**新しい limit class は `enum_members` の 1 つだけである** (U-1 = (β))。**新しい共通条件は C-20〜C-25 の 6 つだけである。**
8. **契約 JSON を触るのは WP-1 だけである。** WP-2 / WP-3 は `spec/` にも両 peer の packaged 複製にも 1 バイトも触らない。

---

## 1. 運用の前提 (全 WP 共通。フェーズ8 §0.1b と第 15 次 §4-5 の継承)

1. **共有 `.venv` を使う** (`./.venv/bin/python`、3.11)。**システム python を使わない。** **worktree では `.venv` は共有 `.venv` への symlink である** — worktree ごとに作り直さない。
2. **ローカル PostgreSQL の `max_connections = 300` / `statement_timeout = 0` が前提である。**
3. **テストは前景 Bash で直列に実行する。** `timeout` パラメータ 600000 を明示する。**subagent に root suite を回させない** (速度規律 2)。
4. **変異の復元は scratchpad backup からの `cp` + `sleep 3` 後の sha256 二重照合 + 変異文字列の全文 grep である。** **`git checkout --` は使わない** (本リポジトリは Google Drive 同期ツリーである)。
5. **push 前に identity を確認する。確認は commit と同一のコマンドで行う** (§4)。
6. **`--collect-only` にも PostgreSQL と全 DSN 環境変数が要る** — 収集時に 4 adapter を実構築して接続検証を行うためである。**使い捨て DB は作られない** (`pg_database` / `pg_roles` の差分 0、実測済み)。
7. **register 系テストは conformance 全体 run の内側でのみ評価する** (L7-23、`conformance-tests/README.md`)。**`conformance-tests/test_conditions_register.py` を単独実行しても意味を持たない** — マーカーは他のファイルにあり、単独実行は「0 件観測」で理由付きの赤になる。**部分実行の赤を実装の逸脱と取り違えない。** **`conformance-tests/test_operation_catalog_register.py` (新設) と `test_contract_history_register.py` は契約 JSON だけを読むので単独実行できる。**
8. **`COLLECTION_FLOOR` は完了ゲートでのみ更新する** (§0.4 の 6)。
9. **`tools/public_value_scan.py` は `git ls-files` ベースなので未追跡の新設ファイルを走査しない。** **新設ファイルは明示引数で走査する** (`./.venv/bin/python tools/public_value_scan.py <新設ファイル…>`)。
10. **並行 worktree の着手前に「触るファイルの重なり 0」を実ファイル名で確認する** (設計 §8.1 の表)。**重なりが見つかったら実装に入る前に監督へ上げる。**
11. **GitHub Actions の job ログは run 完了後にしか読めない。** workflow に concurrency の cancel が入っているので「赤」と「cancel」を取り違えない。
12. **代理指標を使わない。** 分岐の条件は、その分岐が実際に依存している性質そのものを読む (宣言された capability / 宣言された `contract_version`)。**別の性質で代用すると、代用元が動いた瞬間に静かに壊れる** (L8-14)。

---

## 2. WP 分割と発注

### 2.0 WP 一覧

| WP | 内容 | worktree / branch | 着手条件 | 並行 | テンプレート |
|---|---|---|---|---|---|
| **WP-0** | 設計 v1.0 → レビュー 1 → v1.1 → レビュー 2 → v1.2 → **裁定 T-1〜T-4 → v1.3**、本作業指示書 (**起草時の整合まで**) | 監督 | — | 最初・単独 | テンプレ 4 |
| **WP-1** | **契約 1.7.0** (契約 JSON・`conformance-tests/` を触る唯一の WP) | `.claude/worktrees/phase9-wp1` / `phase9-contract-170` | WP-0 の完了 | **単独・直列** | 2 → 5 → 6 |
| **WP-2a〜2e** | **r2db 実装** (直列サブ WP) | `.claude/worktrees/phase9-r2db` / `phase9-r2db` | **WP-1 の main マージ後** | WP-3 と並行 | 2 → 5 → 6 |
| **WP-3a〜3e** | **MitateDB 実装** (直列サブ WP) | `.claude/worktrees/phase9-mitatedb` / `phase9-mitatedb` | **WP-1 の main マージ後** | WP-2 と並行 | 2 → 5 → 6 |
| **WP-4** | **完了ゲートと記録** | 監督 | WP-2e / WP-3e の完了 | 最後・単独 | 4 → 6 |

**サブ WP の順序 (同一 worktree で直列)**: **2a (R-2) → 2b (R-4 dry_run) → 2c (R-5 idempotency) → 2d (R-6 budget) → 2e (R-3 + R-7 + 版フリップ)**、**3a → 3b → 3c → 3d → 3e**。**peer 間だけが並行である** (同じ peer の `src` を複数のサブ WP が触るため)。

**各サブ WP は「gate 撤去 + 宣言 `enabled` + 挙動 + その peer のローカルテスト」を同一コミットに収める** (P-3、§0.4 の 1)。**2e / 3e だけは「R-3 + R-7 + limits 宣言の仕上げ + 版フリップ + `ops verify-declarations` 更新」を持つ。** **`idempotency` の limits 宣言 2 class (追補 2 S-f) は 2c / 3c にある** — 2e / 3e ではない。

---

### WP-1 契約 1.7.0 (従属判断 12)

#### 目的

**契約 1.7.0 を公開し、その宣言をすべて検査する共通条件と、宣言が挙動より先に出ることを機構が禁じる形を、同一の WP で置く。** **この WP はどちらの peer の `contract_version` も動かさない** (1.6.0 の `bb86a37` 型)。**両 peer には provisional gate だけを入れ、新 capability を正直に `unavailable` と宣言させる。**

#### 前提として読む箇所 (設計)

**§1.2 全文 (F-1〜F-26)**、**§3 D-1〜D-9 全文** (とくに各 D の「契約文案」ブロック)、**§4 A-1〜A-10**、**§5 U-1〜U-8 の確定欄と追補・追補 2・追補 3 (T-1〜T-4)**、**§6.1〜§6.7**、**§7**、**§8 / §8.1**、**§10 (L9-1〜L9-13)**、**付録 A / 付録 B**。

#### 対象ファイル (実ファイル名)

**契約と仕様**

1. `spec/data-service-api.v1.json` — 1.7.0 本体
2. `r2db-api/src/r2db_api/contract/data-service-api.v1.json` — packaged 複製 (同一バイト)
3. `MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` — packaged 複製 (同一バイト)
4. `spec/CCR_DISPOSITION.md` — 従属判断 12 の新設
5. `spec/CONTRACT_HISTORY.md` — 前文の limitation 1 / 3、29 セクションの Value 見出し定型文、`versioning.version_binding` の `Introduced in`
6. `spec/CONTRACT_HISTORY_MANIFEST.json` (**新設**) — R-10 (B) の剥離マニフェスト
7. `spec/OPERATION_CATALOG.json` (**新設**) — 派生カタログ
8. `spec/README.md` — マニフェストと派生カタログの 1 段落追記
9. `tools/contract_catalog.py` (**新設**、標準ライブラリのみ)

**conformance**

10. `conformance-tests/adapter.py` — port v1.13
11. `conformance-tests/conftest.py` — `assert_no_unsafe_diagnostic_content` の走査対象拡張
12. `conformance-tests/CONDITIONS.md` / `conformance-tests/CONDITIONS_HISTORY.md`
13. `conformance-tests/test_contract.py`
14. `conformance-tests/test_contract_history_register.py`
15. `conformance-tests/test_operation_catalog_register.py` (**新設**)
16. `conformance-tests/test_c20_constraint_declaration_agreement.py` (**新設**)
17. `conformance-tests/test_c21_denial_details_vocabulary.py` (**新設**)
18. `conformance-tests/test_c22_dry_run_and_plan.py` (**新設**)
19. `conformance-tests/test_c23_idempotency_semantics.py` (**新設**)
20. `conformance-tests/test_c24_request_budget.py` (**新設**)
21. `conformance-tests/test_c25_result_request_id.py` (**新設**)
22. `conformance-tests/test_c11_document_conformance.py` — **逆方向 (defined ⊆ declared) の assert を 1 本足す** (**裁定 T-4**。版ゲートは置かない)
23. `conformance-tests/test_c12_capability_agreement.py`
24. 4 adapter: `r2db-api/conformance/conformance_adapter_r2db.py`、`r2db-api/conformance/conformance_adapter_r2db_http.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`
25. `docs/design/CONFORMANCE_ADAPTER_V1.md` — §23 (v1.13) 新設 + 文書情報の版数行

**両 peer の provisional gate (この WP でしか触らない)**

26. `r2db-api/src/r2db_api/http.py` / `structured.py` / `service.py`
27. `MitateDB-api/src/mitatedb_api/http.py` / `cell.py`
28. `r2db-api/tests/test_http.py` / `MitateDB-api/tests/test_http.py` — provisional gate のローカルテスト (**新規テストのみ。既存の packaged copy byte 一致 assert は無改訂で通る**)

#### 実装の指示

##### (1) 契約 JSON の変更一覧 (json_path ごと。3 複製とも同一バイト)

**契約文案 (英語) は設計 §3 の当該ブロックから逐語複製する。言い換えない。** **下表の「出所」は設計 §5 U-8 の項番である。**

| # | json_path | 種別 | 出所 |
|---|---|---|---|
| 1 | `contract_version` | **改訂** `"1.6.0"` → `"1.7.0"` | D-1 |
| 2 | `schemas.SchemaOperationRequest.properties.field_constraints` | 追加 (object) | #1 |
| 3 | `schemas.SchemaOperationRequest.properties.enum` | 追加 (array) | D-2 (1) |
| 4 | `schemas.SchemaOperationRequest.properties.nullable` | 追加 (boolean) | D-2 (1) |
| 5 | `structured_operations.alter_field` | 追加 (**独立節。§0.0 の 4 (a) で確定**) | #2 |
| 6 | `definitions.EntityDescriptor.properties.field_constraints` | 追加 | #3 |
| 7 | `limits.classes` に `enum_members` を追加 (16 → **17 語**) | 追加 | #4 |
| 8 | `limits.example_profile.enum_members` = **64** (15 → **16 値**) | 追加 | #4 |
| 9 | `limits.enum_members` (意味記述) | 追加 | #4 |
| 10 | `errors.details_vocabulary.VALIDATION_FAILED` | 追加 | #5 |
| 11 | `errors.details_vocabulary.IDENTIFIER_INVALID` | 追加 | #6 |
| 12 | `errors.details_vocabulary.CAPABILITY_UNSUPPORTED` | 追加 | #7 |
| 13 | `errors.details_vocabulary.violated_declaration_vocabulary` (**10 語**) | 追加 | #8 |
| 14 | `errors.details_vocabulary.layer_rule` | 追加 | #9 |
| 15 | `schemas.MutationRequest.properties.dry_run` / `.plan` / `.budget` | 追加 | #10〜#12 / #17 |
| 16 | `schemas.ScopedMutationRequest.properties.dry_run` / `.plan` / `.budget` | 追加 | 同上 |
| 17 | `schemas.SchemaOperationRequest.properties.dry_run` / `.plan` / `.budget` | 追加 | 同上 |
| 18 | `schemas.QueryRequest.properties.budget` | 追加 | #17 |
| 19 | `structured_operations.dry_run.decision` / `.external_effects` / `.plan` | 追加 (3 段落) | #10〜#12 |
| 20 | `schemas.SchemaOperationResult.properties.descriptor` | 追加 ($ref EntityDescriptor) | D-4 (3) |
| 21 | `schemas.MutationResult.properties.plan` / `schemas.SchemaOperationResult.properties.plan` (string、optional。**`required` 不変**) | 追加 | **#29** (D-4 (3) / **裁定 T-1**。設計 v1.3 の「実装の形 1」と U-8 の表に確定済み。**§6 訂正註 1 は解決済み**) |
| 22 | `structured_operations.idempotency.record` / `.correlation` / `.key_secrecy` | 追加 (3 段落) | #13〜#15 |
| 23 | `schemas.SchemaOperationRequest.properties.idempotency_key` | 追加 (string, maxLength 128) | #16 |
| 24 | `limits.request_budget` | 追加 | #17 |
| 25 | `schemas.QueryResult.properties.request_id` / `MutationResult` / `SchemaOperationResult` の同名 | 追加 (**`required` 不変**) | #18 |
| 26 | `endpoints.*.roles` / `.requires_capability` / `.atomicity` (7 行) と `control_endpoints.*` の同名 (12 行)、計 **19 行** | 追加 | #19 |
| 27 | `destructive_confirmation.applies_to_structured` | 追加 (**既存 `applies_to` は残す**) | #20 |
| 28 | `versioning.obligations` / `versioning.obligations_note` | 追加 | #21 |
| 29 | `versioning.version_binding` の **1.7.0 段落** (無条件 2 / 条件付き 5、計 7) | 改訂 (追記) | #22 |
| 30 | `versioning.version_binding` の retroactive-denial **4 文**に `1.7.0-only` を足す | 改訂 | #23 |
| 31 | `versioning.version_binding` の 1.6.0 段落最終文を `1.6.0-only or 1.7.0-only` へ | 改訂 | #24 |
| 32 | `schemas.CapabilityDocument.properties.operation_catalog_url` | 追加 (**optional。義務にしない**) | #25 |
| 33 | `capability_status.defined` に `constraint_declarations` / `dry_run` / `request_budget` (11 → **14 語**) | 追加 | D-1 (2) |
| 34 | `definitions.EntityDescriptor.properties.field_types.description` と `schemas.SchemaOperationRequest.properties.field_types.description` の当該 1 文 | **改訂** (2 json_path とも同一文) | #28 |
| 35 | **R-10 (B) の剥離 26 値** (接頭辞 / 挿入句の除去のみ。規範文は 1 語も変えない) | **剥離** | #27 / U-6 |
| 36 | `schemas.AuditResult.properties.events.items.description` の `this ruling closes` → `this contract closes` | **改訂** (剥離 26 値のうち 1 件に対する語改訂) | 追補 2 S-d |

**`endpoints.*.error_codes` は置かない** (U-5 = (B))。**`rows_scanned` / `pattern` / resource cost 概算も置かない** (計画文書 §6 の却下済み)。

**`atomicity` の固定語彙は 3 語 `atomic` / `none` / `atomic_unless_best_effort` である** (追補 2 S-n。**v1.1 の `per_item_when_declared` から改名済み**)。割り付けは設計 D-8 (2) の表のとおりである。

##### (2) `spec/CCR_DISPOSITION.md` 従属判断 12

**「従属判断 — すべて裁定済み」節に見出し番号 12 の 1 節を新設する。** **従属判断 11 (契約 1.6.0) の節構成を踏襲し、次の 12 の節を持たせる**:

1. **本文** (1.7.0 が足す 7 項目 = R-2 / R-3 / R-4 / R-5 / R-6 / R-7 / R-8、および契約文書のみの変更 3 種)
2. **義務の条件付き性** (無条件 2 件 / 条件付き 5 件。`version_binding` の 1.7.0 段落と 1 対 1)
3. **(a) 契約文案の所在** (設計 §3 の各 D)
4. **(b) 依頼者裁定と委任の記録** (設計 §5 冒頭の逐語)
5. **(c) 版数の扱い** (1.6.0 は公開済みであり、7 項目を単一の 1.7.0 束として出荷する)
6. **(d) 依頼者裁定の参照と却下した側** (設計 §4 A-1〜A-10)
7. **項目ごとの再検討条件**
8. **R-10 (B) の剥離** (契約文書のみの変更。実装に義務を課さない)
9. **`versioning.obligations` の追加** (同上)
10. **R-8 の構造化フィールドと派生カタログ** (同上。`operation_catalog_url` は optional で義務にしない)
11. **実施記録 (契約公開、WP-1)** — **この WP は両 peer の `contract_version` を動かさない。各 peer の flip はその peer の無条件義務を出荷する WP (2e / 3e) の同一コミットに落ちる**
12. **U-5 = (B) により `error_codes` を初版から外したこと** (根拠と日付)

##### (3) `spec/CONTRACT_HISTORY.md` と `spec/CONTRACT_HISTORY_MANIFEST.json`

- **前文の limitation 1 (「契約 JSON の長さは 1 文字も縮まない」) と limitation 3 (「29 値は現行規範文と同居しておりマーカーを外せない」) を (B) 実施後の事実へ書き換える。** **旧文は黙って消さず、前文に改版註として残す。**
- **29 セクションの Value 見出し定型文 (「the history marker is embedded in it」) を同様に書き換える。**
- **`versioning.version_binding` セクションの `Introduced in` を `contract 1.2.0 through 1.7.0 (cumulative)` へ更新する** (`_VERSION_RANGE_RE` が parse する形)。
- **29 セクションの Value 本文 (剥離前の原文) は動かさない。** **companion の quote は逆適用後の値と byte 一致する** (追補 R-j)。
- **マニフェストの形** (設計 D-9 実装の形 2 の素案を確定形にする): json_path をキーに `stripped_prefix` / `stripped_insert` / `unstripped` / `reason` / `rewrite` を持つ。**`rewrite` は追補 2 S-d の 1 件だけであり、`{"from": "this ruling closes", "to": "this contract closes"}` である。** **逆適用は「接頭辞 / 挿入句の復元 + `rewrite` の逆適用」で元値と byte 一致する。**
- **剥離は 26 値、`unstripped` は 3 値である** (`versioning.version_binding` / `versioning.compatibility` / `destructive_confirmation.phrase_construction.rules[3]`)。**追加剥離 2 件 (U-6 の (a) `security.schemes.application_credential.description` / `security.schemes.control_credential.description`、(b) `control_endpoints.revoke_credential.semantics`) は既存 26 値の剥離範囲を広げるものであり、件数を増やさない。**

##### (4) 使い捨て deep-equal 検証 (`tools/` に常設しない)

**剥離前の契約 JSON と、剥離後の契約 JSON にマニフェストを逆適用したものを deep-equal 比較する使い捨てスクリプトを scratchpad で実行する。** **差分 0 と走査キー数を記録する。** **`tools/` に置かない** (1 回きりの移行の検証である。フェーズ8 §4 の却下表)。

##### (5) `conformance-tests/test_contract.py`

- **剥離で動く PIN は 1 件だけである** (追補 2 S-e、実測)。**`PIN_1_5_0_SENTENCE_1` を 2 定数に分ける** — `PIN_1_5_0_SENTENCE_1` (接頭辞付き、`versioning.version_binding` の照合に使う) と `PIN_1_5_0_SENTENCE_1_STRIPPED` (接頭辞なし、`audit.query_operation_vocabulary` / `audit.query_target_kind_vocabulary` の照合に使う)。**規範文は同一であり、違いは接頭辞の有無だけである。**
- **1.7.0 で動く PIN の全一覧は 7 件である**: 上記 1 件 + retroactive-denial 4 件 (#23) + `PIN_1_6_0_VERSION_BINDING_PARAGRAPH` (#24) + `PIN_1_6_0_ITEM_3_FIELD_TYPES` (#28)。**この 7 件以外の PIN 定数に手を入れない** — 剥離では動かない (実測)。
- **1.7.0 の新 PIN を足す** (1.7.0 段落、`violated_declaration_vocabulary` の 10 語、`obligations_note`、`limits.request_budget`、`dry_run` 3 段落、`idempotency` 3 段落、`field_constraints` 3 値、#28 の改訂文)。**設計 §3 の当該ブロックから逐語複製する。**
- **`versioning.obligations` ↔ 散文の照合を 2 本新設する**: (i) **版集合の一致**、(ii) **件数語 (`N of those obligations are unconditional`) を持つ版のみの無条件件数一致、かつ対象版数が 3 (1.4.0 / 1.6.0 / 1.7.0) であること** (追補 R-i。**集合が空なら赤にする**)。
- **既存の `test_contract.py` の件数正規表現 (`(\w+) of those obligations are unconditional` を最初の 1 件だけ拾う既存 assert) が、1.7.0 段落の挿入後も 1.4.0 を拾い続けることを実測する** (§9 の 13)。

##### (6) `conformance-tests/test_contract_history_register.py`

- **スキャナとすべての照合を「契約 JSON にマニフェストを逆適用した値」に対して行う** (追補 R-j)。
- **`Since` 照合は逆適用後の値から読み、`assert checked == 17` は無改訂で通る** — 通ることを実測する。
- **新規 assert を 1 本足す: 「剥離後の契約 JSON にスキャナ (`_PATTERNS`) がヒットする値が 0 件である」** (`unstripped: true` の 3 値を除く)。**S-d の語改訂により、この assert に例外リストは要らない。**
- **1.7.0 が新設 / 改訂したすべての契約値に対してスキャナが 0 ヒットであることを実測する** (追補 R-k、§9 の 12)。**ヒットがあれば、その値の文言から経緯語を落とすのが既定である** (P-7)。

##### (7) `tools/contract_catalog.py` と `spec/OPERATION_CATALOG.json`

- **標準ライブラリのみ。契約 JSON を読み、endpoint ごとに `{name, method, path, roles, requires_capability, atomicity, destructive, request_schema, response_schema}` を射影する。** **自然文を解釈しない** (A-7)。
- **出力は決定的である** (キー順固定、インデント固定、末尾改行あり)。
- **`conformance-tests/test_operation_catalog_register.py` が再生成して byte 一致を assert し、あわせて (i) `roles` ↔ `auth` の一致、(ii) `requires_capability` の値が `capability_status.defined` に実在、(iii) `atomicity` が固定 3 語、(iv) `applies_to_structured` ↔ `applies_to` の 1:1、(v) `obligations` の版集合 ↔ 散文の版集合、(vi) 件数語を持つ 3 版の無条件件数一致、の 6 項目を固定する。**
- **`@pytest.mark.condition` は付けない** (リポジトリ衛生であり、peer 実装に対する implementation-independent な要求ではない)。

##### (8) port v1.13 (`conformance-tests/adapter.py`)

**設計 §6.1 の表 8 件を追加のみで入れる。削除は無い。**

1. mutation 系 / schema 系 primitive の **`dry_run: bool = False`** (**request 単位。`BatchOperation` / `ScopedBatchOperation` に置かない**)
2. mutation / schema primitive の **`plan: str | None = None`** と結果側の **`plan`**
3. 4 endpoint 系 primitive の **`budget: Mapping[str, int] | None = None`** (request 単位のみ)
4. schema primitive の **`idempotency_key: str | None = None`**
5. schema primitive の **`enum` / `nullable` / `field_constraints`**
6. 結果側の **`request_id`** の露出
7. schema 結果側の **`descriptor`** の露出
8. **`alter_field`** primitive (新設)

**docstring に書く限界 (逐語規律の対象、設計 §6.1)**: (i) `dry_run` の「外部可視の状態変化 0」は adapter が観測できる範囲 (行・catalog・revision・監査 query) に限られる、(ii) `plan` は opaque であり adapter は等値比較だけを行う、(iii) `dry_run` / `plan` / `budget` は 1 要求に 1 個であり operation ごとに異なる値を持てない、(iv) `budget` は配備値を下回る方向にのみ効き、bound を上げる用途に使ってはならない、(v) **`BatchOperation.idempotency_key` は per-item だが契約の `idempotency_key` は request 単位である — 1 attempt 内の operations は「全 operation が同じ値を持つ」か「全 operation が持たない」のどちらかであり、adapter はその値を request 単位の key として送る。混在は port の誤用として adapter が理由文付きの `AssertionError` で落とす** (追補 2 S-m)。

**`docs/design/CONFORMANCE_ADAPTER_V1.md` に §23 (v1.13) を新設し、文書情報の版数行 (現行 1.12) を更新する。** 構成は §22 (v1.12) と同じ (追加メソッドの意味論 / 既存機構との関係 / 互換性影響)。

##### (9) 両 peer の provisional gate

**契約 schema が 1.7.0 になると `_check_object_shape` が新フィールドを素通しする** (F-17、レビュー 2 で再確認済み)。**したがって、通したうえで無視して実行すれば P-3 違反になる。**

- **新フィールド 7 種を実行前に `CAPABILITY_UNSUPPORTED` で拒否する**: `dry_run` / `plan` / `budget` / `enum` / `nullable` / `field_constraints` / `SchemaOperationRequest.idempotency_key`。
- **雛形は既存の present-denial である** (`r2db-api/src/r2db_api/http.py` の `idempotency_key` 拒否、`r2db-api/src/r2db_api/structured.py`、`MitateDB-api/src/mitatedb_api/http.py` の 2 箇所)。
- **新設 capability 3 語を同じコミットで `unavailable` として宣言に載せる。** **あわせて、両 peer の capability document が `capability_status.defined` の 14 語すべてを名指していることを assert する** (レビュー 2 m7)。**置き場所は裁定 T-4 で確定した** — **`conformance-tests/test_c11_document_conformance.py` に逆方向 (defined ⊆ declared) の assert として足す。版ゲートは置かない** (両 peer は現行 11 語をすべて宣言していることを WP-1 が実測し、新 3 語は provisional gate と同一コミットで `unavailable` を宣言するので緑のまま)。**現行の `test_c11_document_conformance.py:55-56` は「宣言した名前が `defined` に含まれる」という片方向しか見ていない。** **これが「新 capability を正直に `unavailable` と宣言する」ことの検査である。** **`test_operation_catalog_register.py` に置く案は採らない。**
- **`contract_version` は 1.6.0 のままである。** **この WP で peer の版宣言を動かさない。**

##### (10) 新条件 C-20〜C-25

**6 条件すべてを (i) four adapters で executable、(ii) 宣言分岐型、(iii) 非 vacuity 要件つきで置く。** **命題文 (Condition) / Invariants / Evidence / Status / 宣言分岐の内容は設計 §6.2 から逐語複製する。**

- **宣言分岐は `status_enum` の 4 値に対して網羅である** — **`planned` は C-07 (ii) と同じく肯定側として扱う** (`status != "unavailable"`。レビュー 2 m6)。
- **C-21 / C-25 は capability ではなく `contract_version` で分岐する** (無条件義務)。**`< (1,7,0)` 枝は `xfail(strict=True)`** であり、**条件は実行時に plug の宣言 `contract_version` を読む** (追補 R-h)。**文字列比較を使わない** (`_semver_tuple` 前例)。
- **非 vacuity 要件は「宣言ベース」に統一する** (追補 2 S-c): **各 plug は自分の宣言 (capability status / contract_version) から期待枝を導き、`observed_branch` と突合する** (C-07 (ii) 型)。**suite 横断の集約 guard は置かない** — `-n 5 --dist loadgroup` では plug ごとに worker が分かれ、session をまたぐ観測の集約は成立しない (`conformance-tests/test_c07_atomicity_and_retry.py` の docstring が実測の教訓として書いている)。
- **したがって WP-1 完了時点の `xfailed` は 8 本である** — **C-21 と C-25 の版ゲートが 2 条件 × 4 plug で xfail になる。** **C-20 / C-22 / C-23 / C-24 は 4 plug すべてが `unavailable` 枝を通って緑である** (新 capability が `unavailable` と宣言されているため)。**遷移は 8 → 4 (片 peer のフリップ後) → 0 (両 peer のフリップ後) であり、`conformance-tests/` を 1 行も編集せずに動く** (裁定 T-3、設計 §6.6)。**完了ゲートでは 0 になる。**
- **C-22 は plan の digest 領域を固定する 1 本 (10) を持つ**: **`budget` だけを変えた apply が `PRECONDITION_FAILED` になる** (追補 2 S-a)。
- **C-23 は破壊操作の replay leg を持つ** (追補 2 S-b): **`drop_entity` / `delete` を有効な confirmation + key で実行し、同一 key・同一 body を再送すると、`DESTRUCTIVE_CONFIRMATION_REQUIRED` でも `NOT_FOUND` でもなく元の結果が返る。**
- **C-24 の `batch_items` レシピは設計 §6.2 C-24 (1) で確定している** (レビュー 2 m9 の Minor 一括採択): **`budget.batch_items = 2` を置き、2 件の operation を含む要求は成功、3 件の要求は `LIMIT_EXCEEDED(batch_items)`** である。**`MutationRequest.properties.operations` の `maxItems: 100` にも配備 `batch_items` (既定 100) にも当たらない位置で N / N+1 を挟む** — **in-process plug には shape 検査層が無いので、schema 側の件数制約が先に効く経路を避ける必要がある。** **N を実装側で選び直さない。**

##### (11) `CONDITIONS.md` / `CONDITIONS_HISTORY.md` / `conftest.py`

- **C-20〜C-25 の 6 行を追加する。** **C-20 行には「Overlaps C-17 (同じ declaration-agreement の姿勢、異なる宣言)」を 1 文置く。**
- **C-07 行の Status を書き換える** (設計 §6.4 の逐語)。**旧文は `CONDITIONS_HISTORY.md#c-07` へ逐語で移す。**
- **C-05 行には 1 文字も足さない** (設計 §6.4 の断定形。追補 2 の Minor、レビュー 2 m1)。**C-05 の Status セルは上限 `MAX_CELL_LENGTH = 3000` (`conformance-tests/test_conditions_register.py:56`) に対して余裕が数十字しかなく** (実測値は設計 §6.4 / §6.2 C-24 の開示。**セル長は WP-1 が再実測して設計 §11.3 に記録する**)、**overlap 文 (約 150 字) は入らない。** **したがって overlap は C-24 行の側に置く** — 「Overlaps **C-05**: the same limit classes, a different proposition (C-05 fixes the deployment's own declared bound; this row fixes one request's downward narrowing of it)」を **C-24 行に置く。** **C-05 行の開示を `CONDITIONS_HISTORY.md` へ移して余白を作る形は採らない** — **開示を削って辻褄を合わせない。**
- **C-11 行の Status に 1 文を足す** (裁定 T-4): WP-1 が `conformance-tests/test_c11_document_conformance.py` に足す **defined ⊆ declared の逆方向 assert** を書く。**版ゲートは置かない。** **C-11 行のセル長が 3,000 未満であることを実測して記録する。**
- **`conftest.py` の `assert_no_unsafe_diagnostic_content` の走査対象を C-21 の 3 code の details にも広げる。ただし対象は D-3 の 4 key の値に限定する** (追補 R の Minor、レビュー 1 m7) — `details.field` は client 自身が選んだ識別子を要求内パスとして含むので、敵対的 identifier の probe を走査対象にするとテストが自分のエコーで赤になる。**C-21 が使う identifier は `fresh_identifier` の良性の値に限り、敵対的 identifier の probe は C-03 の territory であって C-21 の走査対象にしない。**

##### (12) 変異実測のための一時フリップ手順

**C-21 / C-25 の版ゲートと、それに乗る assert 本体は、両 peer が 1.6.0 を宣言している間は xfail のままで観測できない。** **したがって WP-1 の変異実測は、次の手順で行う。**

1. **一方の peer の宣言 `contract_version` を一時的に 1.7.0 にする** (挙動は 1.6.0 のまま)。
2. **その状態で個々の変異を 1 つずつ入れ、赤になるテスト id を記録する。**
3. **復元は scratchpad backup からの `cp` + `sleep 3` + sha256 二重照合である。** **`git checkout --` を使わない。**
4. **この一時フリップを含むコミットを作らない。** **コミット前に変異文字列と `1.7.0` の宣言差分を全文 grep してゼロを確認する。**

**この手順そのものが「宣言が挙動より先に出れば赤になる」ことの実証である** (D-1 (7))。

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

1. **契約 JSON の 3 複製が `contract_version: "1.7.0"` で同一バイトである。**
2. **上記 (1) の表の追加フィールドがすべて契約 schema に載り、`required` 配列は 1 つも変わっていない。**
3. **`capability_status.defined` が 14 語である** (`constraint_declarations` / `dry_run` / `request_budget` を追加)。
4. **`limits.classes` が 17 語、`limits.example_profile` が 16 値であり、`limits.enum_members` の意味記述がある。**
5. **`limits.request_budget` 節があり、3 class の適用表 (query / mutate / cross_entity_mutate / schema) が文中で確定している。**
6. **`errors.details_vocabulary` に 5 ブロックがあり、`violated_declaration_vocabulary` が 10 語である。**
7. **`structured_operations.dry_run` が 3 段落 (`decision` / `external_effects` / `plan`) を持つ。**
8. **`structured_operations.idempotency` が 3 段落 (`record` / `correlation` / `key_secrecy`) を持ち、`record` に照会位置の 1 文 (S-b) と replay 時の `revision` の 1 文が入っている。**
9. **`structured_operations.alter_field` が独立節として存在する。**
10. **`versioning.version_binding` に 1.7.0 段落があり、件数語が「無条件 2 件」であり、条件付き 5 件が capability 配列 (AND) で結ばれている。**
11. **retroactive-denial が 5 文になっている** (既存 4 文に `1.7.0-only` を足し、1.6.0 段落最終文を `1.6.0-only or 1.7.0-only` に広げ、1.7.0 段落最終文が 1.6.0 に対する新しい行を供給する)。
12. **`versioning.obligations` + `obligations_note` があり、register の (v) 版集合一致と (vi) 件数語を持つ 3 版の無条件件数一致が緑である** (**対象版数 3 も assert される**)。
13. **`endpoints.*` / `control_endpoints.*` の 19 行すべてが `roles` / `requires_capability` / `atomicity` を持ち、`roles` が `auth` と、`requires_capability` が `capability_status.defined` と一致する。**
14. **`atomicity` の値が固定 3 語 (`atomic` / `none` / `atomic_unless_best_effort`) のいずれかである。**
15. **`destructive_confirmation.applies_to_structured` が既存 `applies_to` と 1:1 で対応する** (**既存 `applies_to` は 1 文字も変えない**)。
16. **`tools/contract_catalog.py` が `spec/OPERATION_CATALOG.json` を決定的に再生成し、byte 一致する。**
17. **R-10 (B) の剥離が 26 値に対して行われ、`spec/CONTRACT_HISTORY_MANIFEST.json` の逆適用が剥離前の JSON と deep-equal である** (`unstripped` 3 値、`rewrite` 1 件)。
18. **剥離後の契約 JSON にスキャナ (`_PATTERNS`) がヒットする値が 0 件である** (`unstripped` 3 値を除く) — 新規 assert。
19. **register のスキャナとすべての照合が「逆適用後の値」に対して行われ、`assert checked == 17` が無改訂で通る。**
20. **PIN 7 件が書き換わっている** (`PIN_1_5_0_SENTENCE_1` の 2 分割を含む)。**それ以外の PIN 定数は 1 文字も動いていない。**
21. **1.7.0 の新 PIN が置かれ、契約値と逐語一致する。**
22. **`spec/CCR_DISPOSITION.md` に従属判断 12 が見出し番号 12 で新設され、`version_binding` の 1.7.0 段落が名指す番号と一致する。**
23. **port が v1.13 であり、8 追加がすべて入り、docstring に限界 (i)〜(v) が書かれている。** **adapter が新フィールドを捨てると条件が赤になる** (L8-15)。
24. **両 peer の provisional gate が新フィールド 7 種を実行前に `CAPABILITY_UNSUPPORTED` で拒否し、副作用が 0 である。**
25. **両 peer が新設 3 capability を `unavailable` として宣言し、`capability_status.defined` の 14 語すべてを名指している。** **これを固定するのは `conformance-tests/test_c11_document_conformance.py` に足した逆方向 (defined ⊆ declared) の assert であり、版ゲートを持たない** (裁定 T-4)。
26. **C-20〜C-25 の 6 ファイルが `@pytest.mark.condition` つきで存在し、`CONDITIONS.md` の 6 行が `executable (four adapters)` であり、`test_conditions_register.py` の照合が緑である。**
27. **C-21 / C-25 の版ゲートが実行時に plug の宣言 `contract_version` を読む `xfail(strict=True)` であり、WP-1 完了時点の `xfailed` が 8 本である。**
28. **C-20 / C-22 / C-23 / C-24 が per-plug で `observed_branch` を宣言から導いた期待値と突合し、4 plug すべてが `unavailable` 枝を観測して緑である。**
29. **`assert_no_unsafe_diagnostic_content` の走査対象が C-21 の 3 code の details の 4 key に広がっており、それ以外の値を走査していない。**
30. **`CONDITIONS.md` の C-07 行が書き換わり、旧文が `CONDITIONS_HISTORY.md#c-07` へ逐語で移されており、C-05 overlap の 1 文は C-24 行の側に入っており、C-05 行は 1 文字も変わっていない。** **全行の最大セルが `MAX_CELL_LENGTH = 3000` 未満である** (C-11 行に足す 1 文を含む)。

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 | 変異 1 | 
| 2 | 変異 2 |
| 3 | 変異 3 |
| 4 | 変異 4 |
| 5 | 変異 5 |
| 6 | 変異 6 |
| 7 | 変異 7 |
| 8 | 変異 8 |
| 9 | 変異 9 |
| 10 | 変異 10 |
| 11 | 変異 11 |
| 12 | 変異 12 |
| 13 | 変異 13 |
| 14 | 変異 14 |
| 15 | 変異 15 |
| 16 | 変異 16 |
| 17 | 変異 17 |
| 18 | 変異 18 |
| 19 | 変異 19 |
| 20 | 変異 20 |
| 21 | 変異 21 |
| 22 | 変異 22 |
| 23 | 変異 23 |
| 24 | 変異 24 |
| 25 | 変異 25 |
| 26 | 変異 26 |
| 27 | 変異 27 |
| 28 | 変異 28 |
| 29 | 変異 29 |
| 30 | 変異 30 |

**変異 (「どのファイルのどの行をどう変える → どのテストが赤になる」)**

1. **`r2db-api/src/r2db_api/contract/data-service-api.v1.json` だけを更新せず 1.6.0 のまま残す** → `r2db-api/tests/test_http.py` の packaged copy byte 一致 assert が赤。
2. **`spec/data-service-api.v1.json` から `schemas.SchemaOperationRequest.properties.field_constraints` を削る** → `test_contract.py` の 1.7.0 構造 assert が赤。
3. **`capability_status.defined` から `dry_run` を削る** → `test_operation_catalog_register.py` の (ii) `requires_capability` 実在 assert と `test_c12` の駆動集合 assert が赤。
4. **`limits.classes` から `enum_members` を削る** (`example_profile` は残す) → `test_contract.py` の class 集合 assert と `test_c05` の V1 assert が赤。
5. **`limits.request_budget` の適用表から `schema` の行 (`execution_ms` のみ) を落とす** → `test_contract.py` の `limits.request_budget` PIN が赤。
6. **`violated_declaration_vocabulary` から `plan` を削る (9 語にする)** → `test_contract.py` の 10 語 PIN が赤。
7. **`structured_operations.dry_run.external_effects` を削る** → `test_contract.py` の 3 段落 assert と当該 PIN が赤。
8. **`structured_operations.idempotency.record` から照会位置の 1 文 (S-b) を削る** → 当該 PIN が赤。
9. **`structured_operations.alter_field` を `SchemaOperationRequest.properties.operation.description` へ移す** → `test_contract.py` の json_path assert が赤。
10. **1.7.0 段落の `Two of those obligations are unconditional` を `Three` にする** → `test_contract.py` の新設「obligations ↔ 散文の件数一致」が赤。
11. **1.1.0 行の retroactive denial から `1.7.0-only` を落とす** → `PIN_1_6_0_RETROACTIVE_*` の書き換え後 PIN が赤。
12. **`versioning.obligations` の 1.7.0 エントリの `unconditional` を 1 件にする** → register の (vi) 件数一致が赤。
13. **`endpoints.query.roles` から `developer` を落とす** → register の (i) `roles` ↔ `auth` 一致が赤。
14. **`endpoints.mutate.atomicity` を `per_item_when_declared` (v1.1 の旧名) に戻す** → register の (iii) 固定 3 語 assert が赤。
15. **`applies_to_structured` から 1 要素を削る** → register の (iv) 1:1 assert が赤。
16. **`spec/OPERATION_CATALOG.json` を手で 1 文字編集する** → register の再生成 byte 一致が赤。
17. **`spec/CONTRACT_HISTORY_MANIFEST.json` から 1 エントリを消す** → register の heading 集合一致と quote byte 一致が赤。
18. **`audit.query_cursor` の接頭辞を剥がさずに残す** (マニフェストには載せる) → 新規 assert (剥離後スキャナ 0 ヒット) が赤。
19. **register の照合対象を「逆適用後の値」から「契約 JSON の生値」へ戻す** → quote byte 一致と `assert checked == 17` が赤。
20. **`PIN_1_5_0_SENTENCE_1_STRIPPED` を接頭辞付きの文字列にする** → `audit.query_operation_vocabulary` / `audit.query_target_kind_vocabulary` の 2 照合が赤。
21. **1.7.0 の新 PIN のうち 1 件から 1 語を落とす** → 当該 PIN 照合が赤。
22. **`spec/CCR_DISPOSITION.md` の見出し番号を 12 → 13 にする** → `test_contract.py` の CCR 突合 (`version_binding` の `subordinate ruling 12` ↔ CCR 見出し) が赤。
23. **4 adapter の `dry_run` キーワードを受け取って捨てる (peer へ送らない)** → C-22 の `unavailable` 枝 (「`dry_run: true` を載せた要求が `CAPABILITY_UNSUPPORTED` で拒否される」) が 4 plug で赤。
24. **`r2db-api/src/r2db_api/http.py` の provisional gate 行 1 本 (`budget` の拒否) を削る** → C-24 の `unavailable` 枝が r2db 2 plug で赤。
25. **r2db の capability document から `request_budget` の宣言を落とす** → **`conformance-tests/test_c11_document_conformance.py` に足した逆方向 assert (defined ⊆ declared、14 語の全数宣言) が r2db 2 plug で赤。**
26. **`CONDITIONS.md` から C-23 行を削る** → `test_conditions_register.py` の marker ↔ 登録一致が赤 (**conformance 全体 run の内側で評価する**)。
27. **C-21 の版ゲート条件を反転する (`>= (1,7,0)` で xfail にする)** → 4 plug が非 xfail 側に落ち、必須 key の assert が 4 plug で赤。
28. **C-20 の `observed_branch` 突合を削り、分岐を通ったこと自体を assert しない形にする** → 一時フリップ手順で `constraint_declarations` を `enabled` と偽宣言したときに赤にならなくなる (**変異の実測は、偽宣言を入れた状態で「本来赤になるはずのものが緑になる」ことを示す**)。
29. **`assert_no_unsafe_diagnostic_content` の走査対象を `DESTRUCTIVE_CONFIRMATION_REQUIRED` のみへ戻す** → 一時フリップ状態で details に行値を入れた peer 変異が C-21 で捕まらなくなる (**同上の形で実測する**)。
30. **overlap 文を C-24 行ではなく C-05 行へ足す** (C-05 の Status セルは上限 3,000 に対して余裕が数十字しかない) → `test_conditions_register.py` の `MAX_CELL_LENGTH` assert が赤。**これが「C-05 行には足さず C-24 行から参照する」(設計 §6.4) の load-bearing な実測である。**

#### 監査照合項目 (完了条件とは別に、完了報告と設計 §11 に必須)

1. **1.7.0 が新設 / 改訂したすべての契約値に対する provenance スキャナのヒット数が 0 であること** (§9 の 12)。
2. **既存 `test_contract.py` の件数正規表現が 1.7.0 段落追加後も 1.4.0 を拾い続けること** (§9 の 13)。
3. **`assert checked == 17` が逆適用後の値に対して無改訂で通ること** (§9 の 13)。
4. **`PIN_1_5_0_SENTENCE_1` の 2 分割後、`version_binding` 側の照合が無改訂で通ること** (追補 2 S-e)。
5. **R-10 (B) の deep-equal 検証の結果 (差分 0 と走査キー数) と、剥離による契約 JSON のバイト減少量。**
6. **`schemas.SchemaOperationRequest.properties.enum` が `_check_object_shape` (両 peer) と `conformance-tests/schema_check.py` の 2 検証器と衝突しないことの実測** (レビュー 2 m12 は「読めば結論が出る」としているが、実測を記録に残す)。
7. **C-24 が `result_items` を駆動できるか否かの実測** — **両 peer で同型に駆動できる query の形を選び、選べなければ非 vacuity の対象から外して C-24 行に「駆動せず」として開示する** (設計 D-6 開示事項)。
8. **port v1.13 の 5 つの新フィールド (`dry_run` / `plan` / `budget` / `idempotency_key` / `field_constraints` 系) すべてについて「adapter が捨てる変異が赤になる」ことの実測** (L8-15)。**変異 23 は `dry_run` の 1 件であり、残り 4 件も同様に実測する。**
9. **`test_c12_capability_agreement.py` に語彙のハードコードがあるか否かの実測と、あれば契約から読む形へ直したこと** (設計 §6.3)。
10. **契約 3 複製の新しい sha256** (フェーズ8 の値から必ず動く)。
11. **`unstripped` 件数 (3) とその各々の理由** (L9-5)。

#### 非 vacuity 要件

- **新条件 6 本は per-plug で「2 枝のどちらかを実際に観測したこと」を assert する** (C-07 (ii) / C-17 の型)。**suite 横断の集約 guard を置かない** (追補 2 S-c)。
- **各 plug は自分の宣言 (capability status / `contract_version`) から期待枝を導き、`observed_branch` と突合する。** **観測から宣言を推測しない。**
- **provisional gate は load-bearing である** — 変異 24 が 4 plug で赤になることを class 名つきで報告する。
- **port の新フィールドは「配線されている」ではなく「捨てると赤になる」まで実測する** (監査照合項目 8)。
- **「1 plug で赤になった」で済ませない** — どの plug のどの条件で赤になったかを条件 id つきで報告する。

#### 確定文言の所在

- **契約文案 (英語) は設計 §3 の各 D の「契約文案」ブロックである。** **#1〜#3 / #5〜#10 / #14〜#22 / #25 は D-2 / D-3 / D-4 / D-5 / D-6 / D-7 / D-8 の各ブロック、#4 は D-2 の `enum_members` ブロック、#11 は D-4 の `external_effects`、#12 は D-4 の `plan`、#13 は D-5 の `record`、#24 は D-8 の 1.5.0 行ブロック、#28 は D-2 の当該ブロックである。**
- **plan / idempotency の digest の対象と正規化規則 (追補 2 S-a) は、設計 §3 D-4 (7) / D-5 (1)(i) と契約文案 `structured_operations.dry_run.plan` / `structured_operations.idempotency.record` にある。** **作業指示書で新たに定義しない。**
- **依頼者裁定の逐語は設計 §5 冒頭である。** **監督裁定 (U-1〜U-8、追補 R-a〜R-l、追補 2 S-a〜S-n) の逐語は設計 §5 と §3 / §6 の当該箇所である。**
- **`limit_enforcement` の 4 語 (`enforced` / `reference_wall_clock` / `deployment_required` / `unavailable`) と `capability_status.status_enum` の 4 語は契約の既存語彙である。新語を作らない。**
- **`violated_declaration` の 10 語と `atomicity` の 3 語は本フェーズが新設する閉じた語彙である。** **11 語目・4 語目を作らない。**

#### 同型性テストの対象

- **本 WP は両 peer の `src` に provisional gate を置くが、同名ヘルパを新設しない** — 既存の present-denial と同じ形の 1 行拒否である。
- **同名ヘルパを置く必要が生じたら、実装前に監督へ上げる** (常設規律 5)。**`_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py`、現行 86 行) への行追加は実装担当が行わない** — **capability ごとの pair (WP-2x と WP-3x) が両方 main にマージされた後に、監督が 1 コミット (pair-closing commit) で両 peer 分を足す** (裁定 T-2、設計 §8)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q conformance-tests/test_contract.py conformance-tests/test_contract_history_register.py conformance-tests/test_operation_catalog_register.py
./.venv/bin/python -m pytest -q r2db-api/tests/test_http.py MitateDB-api/tests/test_http.py
./.venv/bin/python tools/public_value_scan.py spec/CONTRACT_HISTORY_MANIFEST.json spec/OPERATION_CATALOG.json tools/contract_catalog.py conformance-tests/test_operation_catalog_register.py conformance-tests/test_c20_constraint_declaration_agreement.py conformance-tests/test_c21_denial_details_vocabulary.py conformance-tests/test_c22_dry_run_and_plan.py conformance-tests/test_c23_idempotency_semantics.py conformance-tests/test_c24_request_budget.py conformance-tests/test_c25_result_request_id.py
```

**register 系の評価は 1 本目 (`conformance-tests` 全体) で行う** (L7-23)。**root suite は回さない** (監督の完了ゲートのみ)。**`timeout` パラメータ 600000 を明示し、前景で直列に実行する。**

#### 使用テンプレート

**Sonnet 実装 = テンプレ 2** → **Opus コードレビュー = テンプレ 5** → **Opus 証拠監査 = テンプレ 6**。

#### 禁止事項

1. **peer の `contract_version` を動かさない** (4 箇所とも 1.6.0 のまま)。**フリップは 2e / 3e の仕事である。**
2. **`endpoints.*.error_codes` を置かない** (U-5 = (B))。**`rows_scanned` / `pattern` / resource cost 概算も置かない。**
3. **`required` 配列を変えない。既存キーを削除しない。型を変えない。enum を縮めない。**
4. **`versioning.version_binding` の散文を配列に置換しない** (A-6)。**既存 `applies_to` / `capability_status.defined` の既存文を消さない。**
5. **剥離で規範文を 1 語も変えない。** **例外は追補 2 S-d の `rewrite` 1 件だけであり、それはマニフェストに記録される。**
6. **1.7.0 で動く 7 件以外の PIN 定数 (8 件) に手を入れない。** **集計軸を取り違えない** — **剥離で動かないのは 15 定数中 14 件**であり (実測で剥離耐性が確認されている)、**そのうち 6 件は 1.7.0 の文言改訂 (#23 / #24 / #28) で動く**ので、**本フェーズで 1 文字も動かないのは 8 件**である。
7. **`tools/` に逆適用検証を常設しない** (使い捨て、scratchpad)。
8. **`tools/rewrite_hash_refs.py` を作りも直しもしない** (§5)。
9. **`ruling` の語を新規契約値に入れない** — provenance スキャナの `_PATTERNS` が裸の `ruling` を拾う (追補 R-k)。
10. **`COLLECTION_FLOOR` を触らない** (完了ゲートのみ)。
11. **`xfail` の `strict=True` を落とさない。`skip` を使わない。**
12. **一時フリップを含むコミットを作らない** ((12) の手順)。
13. **設計外の検査・機構・語彙を足す前に報告して裁定を待つ** (常設規律 5)。

#### 報告形式

1. 触ったファイルと変更行数 (ファイル単位)。
2. **完了条件番号 → 変異の実測**: 変異のコマンド、赤になったテスト id、plug 名と条件 id、復元の sha256 二重照合の結果。
3. **監査照合項目 1〜11 の実測値** (逐語)。
4. **契約 3 複製の sha256 と、`--collect-only -q` の件数 (参考値。`COLLECTION_FLOOR` は更新しない)。**
5. **設計との食い違い** (あれば。**独断で読み替えず監督へ差し戻す**)。

---

### WP-2a r2db — R-2 制約宣言と `alter_field`

**着手条件: WP-1 の main マージ後。worktree `.claude/worktrees/phase9-r2db`、branch `phase9-r2db`。**

#### 目的

**宣言した制約 (`enum` / `nullable`) が値検証境界で強制され、catalog が同じ版で総計として報告する状態にする。** **`alter_field` を新設し、既存行が反する再宣言を同一トランザクション内で全件拒否する。**

#### 前提として読む箇所 (設計)

**§1.2 (a) F-1〜F-5 / (b) F-6**、**§3 D-2 全文** (決定 (1)〜(7)、契約文案、実装の形、検査の形、開示事項)、**§4 A-1 / A-2**、**§5 U-1 の確定**、**§6.2 C-20**、**§6.5**、**§10 L9-1**、**追補 R-b / R-c**、**追補 2 S-k**。

#### 対象ファイル (実ファイル名)

1. `r2db-api/src/r2db_api/structured.py` — `_check_type` のシグネチャ変更と enum / nullable 検査、insert 分岐の欠落検査、in-memory cell のプロセス内制約保持、`bind_schema_operation` の `alter_field` 分岐
2. `r2db-api/src/r2db_api/postgres.py` — side table の読み書き、`apply_schema` への `alter_field` 追加、insert 分岐の欠落検査、`catalog()` の `field_constraints`
3. `r2db-api/src/r2db_api/service.py` — capability 文書の `unsupported` から `alter_field` を外す、`constraint_declarations` を `enabled` にする、`enum_members` の宣言
4. `r2db-api/src/r2db_api/http.py` — provisional gate の該当行の撤去
5. `r2db-api/src/r2db_api/limits.py` — `enum_members` の既定値と検査
6. `r2db-api/src/r2db_api/ops.py` — `upgrade-applications` の対象に新 upgrade を載せる
7. `r2db-api/migrations/0010_field_constraints_upgrade.sql` (**新設**) — side table `_r2db_field_constraints` の per-application upgrade
8. `r2db-api/tests/test_constraints_declaration.py` (**新設**)
9. `r2db-api/conformance/conformance_adapter_r2db.py` / `conformance_adapter_r2db_http.py` — **隔離 profile の `enum_members` の値のみ**

#### 実装の指示

- **choke point は `_check_type` の 1 関数である。** **`constraints=None` の明示キーワード専用引数を足す** — 現行シグネチャは `def _check_type(value, field_type, field_name) -> None:` であり、`*` が無い (レビュー 2 m11)。**新シグネチャは `def _check_type(value, field_type, field_name, *, constraints=None) -> None:` である。**
- **`_check_type` の呼び出しは repo 全体で 8 箇所ある** (追補 2 S-k)。**書き込み側 6 箇所 (in-memory の insert / update / upsert、Postgres の insert / update / upsert) には `constraints` を渡し、predicate 側 2 箇所 (`_validate_predicate_types` 経由) には渡さない。** **file:line は設計 §1.2 / §3 D-2 (3) の実測値に従う。**
- **`nullable: false` の欠落検査は insert にのみ掛ける** — **in-memory の insert 分岐と Postgres の insert 分岐の、値検査の直前**である。**評価するのは `declared_non_nullable - set(values)` であり、検査順序は「欠落検査 → 値検査」である。** **違反時の `observed_type` は `absent` である。**
- **`update` / `upsert` の欠落は違反ではない。** **ただし insert に解決した `upsert` は insert と同じ規則で拒否される。**
- **宣言の正本**: **Postgres は application DB の side table `_r2db_field_constraints`** (per-application upgrade script + `ops upgrade-applications` 経路)、**in-memory 参照 cell はプロセス内構造** (upgrade script は要らない)。**型は引き続き `information_schema` から読み、制約だけを side table から読む。** **catalog はどちらの backend でも「宣言 registry」から報告する** — 物理制約を読み戻さない。
- **backend 層の物理制約 (NOT NULL / CHECK) を足さない** (A-1)。
- **`alter_field` は `apply_schema` の単一トランザクション内**で、DDL / registry 更新の前に違反行の存在を検査し、1 行でもあれば `CONFLICT` で rollback する。**details は `field` と `violated_declaration ∈ {enum, nullable}` であり、行値も件数も載せない。** **拒否時に revision は進まない** (追補 2 S-g)。**成功した `alter_field` は revision を進める。**
- **`alter_field` に `field_type` を載せた要求は `VALIDATION_FAILED` + `violated_declaration = unsupported_field` である。** **現行でも `structured.py` の既存分岐が `VALIDATION_FAILED` を返すが、`violated_declaration` を持たない** (レビュー 2 m5) — **既存分岐を `unsupported_field` に載せ替える。**
- **`SCHEMA_OPERATIONS` (`structured.py`) は repo 全体で参照が無い死んだ定数である** (レビュー 2 m5)。**実際の拒否点は `bind_schema_operation` の分岐と `service.py` の `schema_ops` リテラルである。** **死んだ定数を「更新した」で完了条件を満たさない。**
- **`enum_members` の検査は、entity が作られる / 変更される前の実行前拒否であり、`LIMIT_EXCEEDED` + `details.limit_class: enum_members` である。** **宣言 (`limits.enum_members` と `limit_enforcement.enum_members`) と検査は同一コミットである。**
- **capability `constraint_declarations` を `enabled` にするのと、provisional gate の撤去と、挙動と、peer-local テストは同一コミットである。**

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

1. **`enum` を宣言した field に集合外の非 null 値を書くと、insert / update / upsert の 3 経路すべてで `VALIDATION_FAILED` + `violated_declaration = enum` になる。** **`declared_type` は載り、`observed_type` は載らない。**
2. **集合内の値は 3 経路すべてで書ける** (正の対照)。
3. **query の predicate に集合外の値を置いても拒否されず、0 行が返る。**
4. **`nullable: false` の field に null を書くと `VALIDATION_FAILED` + `violated_declaration = nullable` + `observed_type = null` になる** (update / upsert / insert)。
5. **`nullable: false` の field を insert で省略すると同 code + `observed_type = absent` になり、insert に解決する `upsert` の省略も同じ拒否になり、update に解決する `upsert` は拒否されない。**
6. **catalog の `field_constraints` が宣言と一致し、entity の `fields` 全体に対して総計である** (宣言の無い field は `nullable: true` かつ `enum` 無し)。
7. **既存行が違反する `alter_field` が `CONFLICT` + `violated_declaration ∈ {enum, nullable}` で拒否され、行も catalog も 1 つも変わらず、revision も進まない。**
8. **違反しない `alter_field` は成功し、revision が進む。**
9. **`alter_field` に `field_type` を載せた要求が `VALIDATION_FAILED` + `violated_declaration = unsupported_field` になる。**
10. **side table が per-application upgrade で作られ、`ops upgrade-applications` 未適用の application で `alter_field` が安全に失敗する** (行を変えない)。
11. **`enum_members` を超える `enum` 宣言が、何も作られる前に `LIMIT_EXCEEDED` + `details.limit_class: enum_members` で拒否される。**
12. **capability `constraint_declarations` が `enabled` であり、gate 撤去・挙動・宣言が同一コミットである。** **C-20 の `observed_branch` が宣言から導いた期待値と一致する。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 | 変異 1 |
| 2 | 変異 2 |
| 3 | 変異 3 |
| 4 | 変異 4 |
| 5 | 変異 5 |
| 6 | 変異 6 |
| 7 | 変異 7 |
| 8 | 変異 8 |
| 9 | 変異 9 |
| 10 | 変異 10 |
| 11 | 変異 11 |
| 12 | 変異 12 |

**変異**

1. **`_apply_upsert` の `_check_type` 呼び出し (in-memory と Postgres の 2 箇所) から `constraints` を落とす** → C-20 (1) の upsert 枝が r2db 2 plug で赤。
2. **choke point の enum 検査を「集合内なら拒否」に反転する** → C-20 (2) の正の対照が赤。
3. **`_validate_predicate_types` 経由の 2 呼び出しに `constraints` を渡す** → C-20 (5) が赤。
4. **choke point の null 分岐 (`nullable=false` かつ値が null なら拒否) を削る** → C-20 (3) が赤。
5. **insert 分岐の欠落検査 (`declared_non_nullable - set(values)`) を削る** → C-20 の `absent` 枝が赤。
6. **`catalog()` の `field_constraints` を registry ではなく既定値 (`nullable: true`) から作る** → C-20 (4) の round-trip が赤。
7. **`alter_field` の既存行走査を DDL の後へ移す** → C-20 (6) の「1 行も変わっていない」assert が赤。
8. **`alter_field` 成功時の revision bump を削る** → C-20 (7) が赤。
9. **`field_type` 付き `alter_field` の `violated_declaration` を `request_schema` にする** → `r2db-api/tests/test_constraints_declaration.py` の当該 assert が赤。
10. **`migrations/0010_field_constraints_upgrade.sql` を `ops upgrade-applications` の対象一覧から外す** → peer-local の「未適用 application で安全に失敗する」テストが赤。
11. **`enum_members` の上限検査を削る** → peer-local の `LIMIT_EXCEEDED(enum_members)` テストが赤。
12. **capability を `enabled` にしたまま gate 撤去を戻す (宣言先行)** → C-20 の `observed_branch` 突合が r2db 2 plug で赤。

#### 監査照合項目

1. **`_check_type` の呼び出し 8 箇所の全数を AST 走査で列挙し、`constraints` を渡す 6 箇所 / 渡さない 2 箇所の内訳を記録すること** (grep を根拠にしない。第 15 次 §5 の教訓)。
2. **`SCHEMA_OPERATIONS` が死んだ定数であることの再確認と、実際に触った拒否点の file:line。**
3. **隔離 profile の `enum_members` の確定値** (`_MAX_EXERCISABLE_LIMIT` 以下)。

#### 非 vacuity 要件

- **C-20 の `enforced` 枝を r2db 2 plug で実際に通し、`observed_branch` を記録する。**
- **peer-local テストは観測対象が 1 件以上あることを assert する** — 「既存行が違反する `alter_field`」は、**実際に違反行を 1 行以上入れたこと**を assert してから拒否を測る。
- **変異は r2db 2 plug の両方で赤にした実測を報告する。**

#### 確定文言の所在

- **契約文案は設計 §3 D-2 の「契約文案」ブロック** (`field_constraints` / `alter_field` / `EntityDescriptor.field_constraints` / `enum_members`)。**契約 JSON は WP-1 で確定済みであり、本 WP は契約を 1 バイトも触らない** — **実装は契約の文言に従うだけである。**
- **U-1 = (β) の確定 (新 class `enum_members`、`example_profile` は 64、要素長は `request_bytes` に委ねる) は設計 §5 U-1。**
- **追補 R-b / R-c (choke point の `constraints=None` と欠落検査の位置) と追補 2 S-k (8 呼び出しの内訳) は設計 §3 D-2 (3)。**
- **追補 2 S-g (MitateDB 側の tx 構造と developer role の SELECT 権限) は本 WP の対象外である** (WP-3a)。

#### 同型性テストの対象

- **本 WP が MitateDB と同名で置き得るヘルパ**: **制約の正規化 / 検証ヘルパ** (`enum` 要素が field の宣言型に属することの検査、`nullable` の既定解決)。
- **`_ISOMORPHIC_TARGETS` への行追加は実装担当が行わない (裁定 T-2)。** **pair (WP-2a と WP-3a) が両方 main にマージされた後に、監督が 1 コミット (pair-closing commit) で両 peer 分を足す。** **監督の pair-closing commit は両 peer の isomorphism テストを実行して緑を確認してからマージする。** **実装担当は、自 peer 側の helper 名と対応する相手側の helper 名 (本節の同型性表のとおり) を報告に書く** — それが監督の入力である。**これで WP-2 × WP-3 の重なり 0 が保たれる** (§5)。
- **コードは共有しない** (P-6)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests/test_constraints_declaration.py
./.venv/bin/python -m pytest -q conformance-tests/test_c20_constraint_declaration_agreement.py
./.venv/bin/python -m pytest -q r2db-api/tests
```

#### 使用テンプレート

**Sonnet 実装 = テンプレ 2** → **Opus コードレビュー = テンプレ 5** → **Opus 証拠監査 = テンプレ 6**。

#### 禁止事項

1. **契約を変えない** (`spec/` と packaged 複製に 1 バイトも触らない)。
2. **`conformance-tests/` を触らない** (§0.4 の 3)。**必要が出たら監督裁定を仰ぐ。**
3. **物理制約 (NOT NULL / CHECK) を backend に足さない** (A-1)。
4. **`alter_field` で `field_type` の再宣言を実装しない** (A-2)。
5. **predicate 経路に `constraints` を渡さない。**
6. **新しい limit class を発明しない** — `enum_members` は契約が定めた 1 つだけである。
7. **宣言だけを先に `enabled` にしない。**
8. **MitateDB 側のファイルを 1 つも触らない** (並行 WP)。
9. **設計外の検査・機構を足す前に報告して裁定を待つ。**

#### 報告形式

1. 触ったファイルと変更行数。
2. **完了条件番号 → 変異の実測** (テスト id、plug 名、復元の sha256 二重照合)。
3. **監査照合項目 1〜3 の実測値。**
4. **設計との食い違い** (あれば)。

---

### WP-2b r2db — R-4 dry_run と無状態 plan

**着手条件: WP-2a の完了後 (同一 worktree で直列)。**

#### 目的

**「試したときの判定 = 本番の判定」を、実行して rollback する形で成立させ、外部可視の状態変化を 0 にする。** **plan をサーバ保持なしの決定的トークンとして実装する。**

#### 前提として読む箇所 (設計)

**§1.2 (c) F-12 / F-14 / F-15 / F-16**、**§3 D-4 全文**、**§4 A-3 / A-4 / A-9**、**§5 U-2 / U-4 の確定**、**§6.2 C-22**、**追補 R-e**、**追補 2 S-a / S-j / S-l**。

#### 対象ファイル (実ファイル名)

1. `r2db-api/src/r2db_api/service.py` — `_mutate_outcome` / schema 経路の dry_run 分岐、digest 計算点、plan の照合
2. `r2db-api/src/r2db_api/structured.py` — in-memory `transact` の出口分岐、`apply_schema` 相当の出口分岐
3. `r2db-api/src/r2db_api/postgres.py` — `transact` / `apply_schema` の COMMIT / ROLLBACK 点の分岐
4. `r2db-api/src/r2db_api/http.py` — provisional gate の該当行の撤去 (`dry_run` / `plan`)
5. `r2db-api/tests/test_dry_run_and_plan.py` (**新設**)

#### 実装の指示

- **dry_run は実呼びが通るすべての gate を通る** — 認証、role、rate / concurrency、request_bytes、operation_depth、request shape、capability、検証である。**認可・破壊確認・precondition・limit の拒否は、実呼びと同一の code と details で返す。** **gate の順序は契約に載っていない** — 実装の現順序を変えない (追補 R-e)。
- **commit するか rollback するかを tx の出口 1 点で決める。** **途中で分岐しない** — 途中で分岐すると「実呼びと同じ判定」が崩れる。
- **dry_run では `_make_audit_hook` を組み立てない** (`pre_commit()` を呼ばない)。**監査行を 1 行も書かない** (U-2 = (A))。**実行前の拒否は現行どおり監査される。**
- **dry_run では idempotency 記録を書かず、参照もしない。**
- **dry_run では revision を進めない。**
- **dry_run の応答は実呼びと同じ schema であり、`committed: false`、`affected` は実行したときの件数、`assigned_addresses` は載せない、schema なら `descriptor` を載せる、加えて `plan` を返す。**
- **schema の dry_run が返す `revision` は判定時点の現在 revision である** (追補 2 S-j) — 変更後に立つはずの値ではない。
- **`plan` の digest の対象と正規化規則は契約が定める** (追補 2 S-a、契約 `structured_operations.dry_run.plan`)。**digest の対象は契約レベルの要求オブジェクトであり、raw body ではない。** **`plan` と `dry_run` の 2 key を除く。** **`budget` / `transaction` / `confirmation` / `idempotency_key` は含める。** **計算点は service 層の入口 (要求 object が揃う最初の点) である。**
- **plan の schema 成分は対象 Application の schema revision である** (U-4 = (A))。**entity ごとではない。**
- **plan の照合は `destructive_confirmation.evaluation_order` の precondition 段で行う** (追補 2 S-l) — **confirmation の後、execution の前**である。**不一致は `PRECONDITION_FAILED` + `details.violated_declaration: plan` である。**
- **capability `dry_run` を `enabled` にするのと gate 撤去と挙動は同一コミットである。**

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

1. **拒否側の判定一致** — 認可・破壊確認・precondition・limit のそれぞれで、dry_run と実呼びが同一 code を返す。
2. **成功側の判定一致** — dry_run の `affected` が実呼びの `affected` と一致し、応答が `committed: false` である。
3. **外部可視の状態変化 0** — dry_run の前後で行数・catalog・revision が不変であり、監査行が 1 行も増えていない。
4. **dry_run の mutation 応答に `assigned_addresses` が無い。**
5. **schema の dry_run が `descriptor` (変更後の姿) と `revision` (判定時点の現在値) を返し、`descriptor` が実 apply 後の catalog と一致し、`revision` は apply 後の値と異なる。**
6. **plan が決定的である** — 同一要求の dry_run 2 回で `plan` が一致する。
7. **plan の digest 領域が load-bearing である** — `budget` だけを変えた apply が `PRECONDITION_FAILED` + `violated_declaration = plan` になる。
8. **plan の schema 成分が効く** — 間に同一 Application の schema を変えると apply が `PRECONDITION_FAILED` になる。
9. **plan の照合が precondition 段で行われる** — 失効した plan を持つ未確認の破壊操作は `DESTRUCTIVE_CONFIRMATION_REQUIRED` を返す (confirmation が先)。
10. **capability `dry_run` が `enabled` であり、gate 撤去・挙動・宣言が同一コミットである。** **C-22 の `observed_branch` が宣言から導いた期待値と一致する。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 | 変異 1 |
| 2 | 変異 2 |
| 3 | 変異 3 |
| 4 | 変異 4 |
| 5 | 変異 5 |
| 6 | 変異 6 |
| 7 | 変異 7 |
| 8 | 変異 8 |
| 9 | 変異 9 |
| 10 | 変異 10 |

**変異**

1. **dry_run 経路で認可判定を飛ばす (role 判定の前に dry_run 分岐を置く)** → C-22 (1) の判定一致 (拒否側) が赤。
2. **dry_run を「検証だけして実行しない」形に変える (`affected` を 0 固定にする)** → C-22 (2) が赤。
3. **dry_run でも `_make_audit_hook` を組み立てる** → C-22 (3) の「監査行不変」が赤。
4. **dry_run 応答に `assigned_addresses` を載せる** → C-22 (4) が赤。
5. **schema の dry_run の `revision` を「変更後に立つはずの値」にする** → C-22 (5) が赤。
6. **plan を乱数にする** → C-22 (6) が赤。
7. **digest の対象から `budget` を除く** → C-22 (10) が赤。
8. **digest から schema revision 成分を落とす** → C-22 (8) が赤。
9. **plan の照合を confirmation より前に移す** → C-22 の順序 assert が赤。
10. **capability を `enabled` にしたまま gate 撤去を戻す** → C-22 の `observed_branch` 突合が赤。

#### 監査照合項目

1. **digest 計算点の file:line と、そこで要求オブジェクトの全 key が揃っていることの実測。**
2. **`apply_schema` が `_next_id` を snapshot / restore するため schema の dry_run では採番が消費されないこと** (レビュー 2 の確認事項)。**data mutation 側は消費し得る** — 契約が許容している。
3. **dry_run が rate / concurrency を消費することの実測** (bound を回避できないこと)。

#### 非 vacuity 要件

- **C-22 の `dry_run_enabled` 枝を r2db 2 plug で実際に通す。**
- **判定一致 (拒否側) は「実際に拒否が 1 件以上観測された」ことを assert してから code を比べる。**
- **plan の決定性は「2 回の dry_run が両方成功した」ことを assert してから値を比べる。**

#### 確定文言の所在

- **契約文案は設計 §3 D-4 の 3 ブロック** (`dry_run.decision` / `.external_effects` / `.plan`)。
- **U-2 = (A) (監査行を一切書かない) と U-4 = (A) (per-application revision) の確定は設計 §5。**
- **digest の対象と正規化規則 (追補 2 S-a)、dry_run の `revision` (S-j)、budget / plan の評価順序 (S-l) は設計 §3 D-4 と契約文案。**

#### 同型性テストの対象

- **digest 正規化関数** (要求オブジェクトの正規化 + sha256)。**両 peer に同名で置く。**
- **plan トークンの組み立て / 照合ヘルパ。**
- **`_ISOMORPHIC_TARGETS` への行追加は実装担当が行わない (裁定 T-2)。** **pair (WP-2b と WP-3b) が両方 main にマージされた後に監督が 1 コミット (pair-closing commit) で両 peer 分を足す。** **実装担当は自 peer 側の helper 名と対応する相手側の helper 名を報告に書く** (WP-2a と同じ)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests/test_dry_run_and_plan.py
./.venv/bin/python -m pytest -q conformance-tests/test_c22_dry_run_and_plan.py
./.venv/bin/python -m pytest -q r2db-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

1. **契約を変えない。`conformance-tests/` を触らない。**
2. **dry_run を静的検証にしない** (A-3)。
3. **plan をサーバ保持にしない** (A-4)。**失効・容量・掃除の機構を作らない。**
4. **dry_run で `assigned_addresses` を返さない** (A-9)。
5. **gate の順序を契約に合わせて並べ替えない** — 順序は実装事実であり、契約に載っていない。
6. **dry_run で rate / concurrency の消費を免除しない。**
7. **MitateDB 側のファイルを触らない。**
8. **設計外の検査・機構を足す前に報告して裁定を待つ。**

#### 報告形式

**WP-2a と同一。**

---

### WP-2c r2db — R-5 idempotency

**着手条件: WP-2b の完了後 (同一 worktree で直列)。**

#### 目的

**再送安全性を実装し、「記録あり = commit 済み」が構造で成り立つ形にする。** **L7-8 (C-07 (ii) の肯定枝が未到達) を r2db 側で閉じる。**

#### 前提として読む箇所 (設計)

**§1.2 (e) F-19**、**§3 D-5 全文**、**§4 A-5 / A-10**、**§5 U-3 の確定**、**§6.2 C-23**、**§6.4 (C-07 行)**、**§10 L9-7**、**追補 2 S-a / S-b / S-f**、**レビュー 2 m13 (満杯判定を実行前に行う)**。

#### 対象ファイル (実ファイル名)

1. `r2db-api/src/r2db_api/service.py` — 照会位置、記録の書き込み、capability 宣言、limits 宣言 2 class
2. `r2db-api/src/r2db_api/structured.py` / `postgres.py` — 記録を data tx と同一 tx に置く
3. `r2db-api/src/r2db_api/http.py` — provisional gate の該当行の撤去 (`SchemaOperationRequest.idempotency_key`) と既存 present-denial の撤去
4. `r2db-api/src/r2db_api/limits.py` — `idempotency_entries` / `idempotency_retention_ms` の既定値
5. `r2db-api/migrations/0011_idempotency_records_upgrade.sql` (**新設**)
6. `r2db-api/src/r2db_api/ops.py` — `upgrade-applications` の対象に載せる
7. `r2db-api/tests/test_idempotency_records.py` (**新設**)

#### 実装の指示

- **記録は application DB の side table である** (U-3 = (A))。**per-application upgrade で置き、data tx と同一 tx で書く。** **in-memory 参照 cell はプロセス内 dict である。**
- **記録するのは key と要求 body の正規化 digest である。** **digest の規則は WP-2b の plan と同じ規則であり、除く key は `plan` / `dry_run` / `idempotency_key` の 3 つである** (追補 2 S-a)。
- **照会位置は、認証・認可・bound (rate / concurrency / request_bytes / operation_depth / shape / capability / budget の妥当性) の後、target-existence / confirmation / precondition / execution の前である** (追補 2 S-b)。**記録済み key の再送は target-existence 以降の段を一切実行せずに元の結果を返す** — `drop_entity` の再送は、entity がもう無くても、確認 phrase が無くても、元の結果を返す。
- **同一 key・異 digest は `CONFLICT` + `details.violated_declaration: idempotency_key` である。** **denial は先の要求を開示しない。**
- **失敗した試行は記録を残さない** (同一 tx なので rollback で消える)。
- **key のスコープは Application である** — 同一 Application の別 credential から同じ key を送れば同一要求とみなす (A-5)。
- **満杯の判定は照会段 (実行前) で行う** (レビュー 2 m13、追補 2 の Minor)。**期限切れを遅延回収してもなお満杯なら `LIMIT_EXCEEDED` + `details.limit_class: idempotency_entries` である。** **実行してから rollback しない。** **背景スレッド・定期ジョブを置かない。**
- **capability を `enabled` にする同一コミットで、`limits.idempotency_entries` / `limits.idempotency_retention_ms` と対応する `limit_enforcement` を capability document に足す** (追補 2 S-f) — **C-05 V1 (e) の `_CAPABILITY_CONDITIONED` がこの 2 class を `idempotency` に条件付けており、宣言を欠くと C-05 が赤になる。**
- **replay 応答は `MutationResult` / `SchemaOperationResult` の全体であり、`request_id` を含む** (R-7 は 2e で入るので、2c 時点では両者とも `request_id` を持たない — **2e の後に一致が意味を持つ**)。**replay の `SchemaOperationResult.revision` は元実行時点の値である。**

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

1. **記録が data tx と同一 tx に書かれ、失敗した試行の後の同一 key の再送が新規実行になる。**
2. **同一 key + 同一 body の再送が元の結果を返し、行が 1 つしか増えていない。**
3. **同一 key + 異なる body が `CONFLICT` + `violated_declaration = idempotency_key` になる。**
4. **記録済み key の再送が target-existence / confirmation / precondition を評価せずに答える** — `drop_entity` (または `delete`) の再送が `DESTRUCTIVE_CONFIRMATION_REQUIRED` でも `NOT_FOUND` でもなく元の結果を返す。
5. **key のスコープが Application である** — 同一 Application の別 credential から同じ key を送ると同一要求とみなされる。
6. **`SchemaOperationRequest` と cross-entity にも適用される。**
7. **満杯の拒否が実行前に起き、`LIMIT_EXCEEDED` + `limit_class: idempotency_entries` であり、行が 1 つも増えていない。**
8. **capability を `enabled` にする同一コミットで `limits.idempotency_entries` / `limits.idempotency_retention_ms` と `limit_enforcement` が宣言されている。**
9. **capability `idempotency` が `enabled` であり、gate 撤去・挙動・宣言が同一コミットである。** **C-07 (ii) の `retry_same_result` 枝が r2db 2 plug で load-bearing になる。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 | 変異 1 |
| 2 | 変異 2 |
| 3 | 変異 3 |
| 4 | 変異 4 |
| 5 | 変異 5 |
| 6 | 変異 6 |
| 7 | 変異 7 |
| 8 | 変異 8 |
| 9 | 変異 9 |

**変異**

1. **記録の書き込みを data tx の外 (別コネクション) へ移す** → C-23 (v) の「失敗した試行は記録を残さない」が赤。
2. **再送で再実行する (記録を参照しない)** → C-23 (i) の `affected` / `assigned_addresses` 一致と行数 assert が赤。
3. **digest を key だけにする (body を digest に含めない)** → C-23 (ii) の `CONFLICT` が出ず赤。
4. **照会を confirmation の後へ移す** → C-23 (vii) の破壊操作 replay leg が赤。
5. **key スコープを credential 単位にする** → C-23 (vi) が赤。
6. **schema 経路で `idempotency_key` を無視する** → C-23 (iv) が赤。
7. **満杯判定を記録書き込み時点 (実行後) に移す** → peer-local の「満杯拒否で行が増えない」テストが赤。
8. **`limits.idempotency_entries` の宣言を落とす** → C-05 V1 (e) が r2db 2 plug で赤。
9. **capability を `enabled` にしたまま present-denial を戻す** → C-07 (ii) / C-23 の `observed_branch` 突合が赤。

#### 監査照合項目

1. **記録の読み書きが data tx と同一 tx にあることの file:line。**
2. **期限切れ entry の遅延回収が背景スレッド・定期ジョブを持たないことの確認。**
3. **digest の規則が WP-2b の plan と同一実装から導かれていること** (除く key が 3 つであること)。

#### 非 vacuity 要件

- **C-23 の `retry_same_result` 枝を r2db 2 plug で実際に通す。**
- **C-07 (ii) は 1 文字も変えない** — 宣言が変わることで枝が入れ替わる。**入れ替わったことを `observed_branch` で実測して報告する。**
- **retention の期限切れ検査は行わない** (待ち時間を要する)。**この限界は C-23 行に開示済みである。**

#### 確定文言の所在

- **契約文案は設計 §3 D-5 の 3 ブロック** (`idempotency.record` / `.correlation` / `.key_secrecy`)。
- **U-3 = (A) の確定は設計 §5 U-3** (**v1.1 反映後の訂正文に従う** — SQLite backend はプロセス内である)。
- **照会位置 (S-b)、digest (S-a)、limits 2 class (S-f) は設計 §3 D-5。**

#### 同型性テストの対象

- **idempotency の記録読み書きのテストヘルパ** (記録件数の観測、期限の操作)。
- **digest 正規化関数** (WP-2b と共通の同名ヘルパ)。
- **`_ISOMORPHIC_TARGETS` への行追加は実装担当が行わない (裁定 T-2)。** **pair (WP-2c と WP-3c) が両方 main にマージされた後に監督が 1 コミット (pair-closing commit) で両 peer 分を足す。** **実装担当は自 peer 側の helper 名と対応する相手側の helper 名を報告に書く。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests/test_idempotency_records.py
./.venv/bin/python -m pytest -q conformance-tests/test_c23_idempotency_semantics.py conformance-tests/test_c07_atomicity_and_retry.py conformance-tests/test_c05_limit_declaration_agreement.py
./.venv/bin/python -m pytest -q r2db-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

1. **契約を変えない。`conformance-tests/` を触らない** (C-07 (ii) を 1 文字も変えない)。
2. **記録を platform DB (cross-app) に置かない** (A-10)。
3. **key を監査行に載せない。**
4. **補償 (先に記録し失敗時に消す) を使わない。**
5. **背景スレッド・定期ジョブを置かない。**
6. **満杯を「実行してから rollback」で拒否しない。**
7. **MitateDB 側のファイルを触らない。**
8. **設計外の検査・機構を足す前に報告して裁定を待つ。**

#### 報告形式

**WP-2a と同一。**

---

### WP-2d r2db — R-6 request budget

**着手条件: WP-2c の完了後 (同一 worktree で直列)。**

#### 目的

**1 要求が自ら課した bound が決定的に効く形にする。** **budget は配備値を下回る方向にのみ効く。**

#### 前提として読む箇所 (設計)

**§1.2 (d) F-18**、**§3 D-6 全文**、**§5 U-5 の確定**、**§6.2 C-24**、**§10 L9-3 / L9-11**、**追補 R-g**、**追補 2 S-l**、**レビュー 2 m9**。

#### 対象ファイル (実ファイル名)

1. `r2db-api/src/r2db_api/limits.py` — `effective_limits = deployed.narrowed_by(budget)` の 1 点
2. `r2db-api/src/r2db_api/service.py` — 要求ごとの実効値の生成、budget の妥当性検査の位置
3. `r2db-api/src/r2db_api/structured.py` / `postgres.py` — 既存の検査点が実効値を見る形へ
4. `r2db-api/src/r2db_api/http.py` — provisional gate の該当行の撤去 (`budget`)
5. `r2db-api/tests/test_budget_narrowing.py` (**新設**)

#### 実装の指示

- **配備値を読む 1 点で「実効値」を作る。** **検査点を個別に書き換えない** — 要求ごとに `effective_limits = deployed.narrowed_by(budget)` を作り、既存の検査点はそれを見る。**これにより「budget が効かない検査点が 1 つ残る」形を構造的に排除する。**
- **適用表は設計 D-6 (2) の表である** — `query` は `result_items` / `execution_ms`、`mutate` と `cross_entity_mutate` は `execution_ms` / `batch_items`、`schema` は `execution_ms` のみ。**mutation に `result_items` は適用しない** (追補 R-g、L9-11)。
- **budget の妥当性検査 (適用外 class・配備値超過・非整数) は request の検証段で行う** (追補 2 S-l) — **shape / capability と同じ段、target-existence の前**である。
- **配備値を上回る budget は `VALIDATION_FAILED` + `violated_declaration = budget` + `field = budget/<class>` である。** **黙って clamp しない。**
- **超過は既存どおり `LIMIT_EXCEEDED` + `details.limit_class` であり、budget 由来か配備値由来かを区別しない。**
- **`execution_ms` は駆動しない** (決定的な N+1 を構成できない)。
- **capability `request_budget` を `enabled` にするのと gate 撤去と挙動は同一コミットである。**

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

1. **budget で narrow した bound がその位置ちょうどで効く** — **`budget.batch_items = 2` で 2 件の operation を含む要求は成功、3 件の要求は `LIMIT_EXCEEDED(batch_items)`** (設計 §6.2 C-24 (1) の確定レシピ。**`maxItems: 100` にも配備 `batch_items` にも当たらない位置である**)。
2. **budget を省略した同じ要求は配備値まで通る** (正の対照)。
3. **配備値を上回る budget が `VALIDATION_FAILED` + `violated_declaration = budget` になる。**
4. **適用外 class (query に `batch_items`、mutation に `result_items`) が `VALIDATION_FAILED` + `field = budget/<class>` になり、無視されない。**
5. **超過の `LIMIT_EXCEEDED` の `details.limit_class` が当該 class であり、budget 専用の値ではない。**
6. **budget の妥当性検査が検証段で行われる** — 配備値超過の budget を持つ未確認の破壊操作が `VALIDATION_FAILED` を返す (confirmation より前)。
7. **capability `request_budget` が `enabled` であり、gate 撤去・挙動・宣言が同一コミットである。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 | 変異 1 |
| 2 | 変異 2 |
| 3 | 変異 3 |
| 4 | 変異 4 |
| 5 | 変異 5 |
| 6 | 変異 6 |
| 7 | 変異 7 |

**変異**

1. **`narrowed_by` の `min` を `max` にする** → C-24 (1) が赤。
2. **budget 省略時に既定の budget (小さい値) を当てる** → C-24 (5) の正の対照が赤。
3. **配備値超過を黙って clamp する** → C-24 (3) が赤。
4. **適用外 class を無視する (`budget` から捨てる)** → C-24 (4) が赤。
5. **budget 由来の超過に専用の `limit_class` を返す** → C-24 の code / details assert が赤。
6. **budget の妥当性検査を target-existence の後へ移す** → C-24 の順序 assert が赤。
7. **capability を `enabled` にしたまま gate 撤去を戻す** → C-24 の `observed_branch` 突合が赤。

#### 監査照合項目

1. **実効値を作る 1 点の file:line と、既存の検査点がすべてそれを見ていることの AST 全数走査** (grep を根拠にしない)。
2. **`result_items` を C-24 が駆動できるか否かの実測結果** (WP-1 の実測と突合する)。
3. **r2db が limits の配備時 env override を持たないこと (L9-3) が budget の有効性に影響しないことの確認。**

#### 非 vacuity 要件

- **C-24 の `budget_enforced` 枝を r2db 2 plug で実際に通す。**
- **`batch_items` のレシピは設計 §6.2 C-24 (1) の確定形 (`budget.batch_items = 2`、2 件成功 / 3 件拒否) であり、要求内の operation 件数を budget だけで N / N+1 に分ける** (実行数側に位置決定の余地を残さない。L8-15)。
- **adapter が `budget` を捨てる変異が赤になることを実測する。**

#### 確定文言の所在

- **契約文案は設計 §3 D-6 の `limits.request_budget` ブロック。**
- **適用表 (mutation から `result_items` を外す) は追補 R-g、評価順序は追補 2 S-l。**

#### 同型性テストの対象

- **budget の narrowed 関数** (`narrowed_by` 相当)。**両 peer に同名で置く。**
- **`_ISOMORPHIC_TARGETS` への行追加は実装担当が行わない (裁定 T-2)。** **pair (WP-2d と WP-3d) が両方 main にマージされた後に監督が 1 コミット (pair-closing commit) で両 peer 分を足す。** **実装担当は自 peer 側の helper 名と対応する相手側の helper 名を報告に書く。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests/test_budget_narrowing.py
./.venv/bin/python -m pytest -q conformance-tests/test_c24_request_budget.py conformance-tests/test_c05_limit_declaration_agreement.py
./.venv/bin/python -m pytest -q r2db-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

1. **契約を変えない。`conformance-tests/` を触らない。**
2. **budget が bound を上回る方向に効く経路を作らない。**
3. **`rows_scanned` を budget class に足さない。**
4. **mutation に `result_items` の budget を受け付けない** (新しい強制点を作らない。P-5)。
5. **配備値を露出しない** (`LIMIT_EXCEEDED` で budget 由来か配備値由来かを区別しない)。
6. **MitateDB 側のファイルを触らない。**
7. **設計外の検査・機構を足す前に報告して裁定を待つ。**

#### 報告形式

**WP-2a と同一。**

---

### WP-2e r2db — R-3 details 語彙 + R-7 `request_id` + 版フリップ

**着手条件: WP-2d の完了後 (同一 worktree で直列)。**

#### 目的

**1.7.0 の無条件義務 2 件を入れ、同一コミットで `contract_version` を 1.7.0 へフリップする。**

#### 前提として読む箇所 (設計)

**§1.2 (b) F-7〜F-11 / (f) F-17 / F-25**、**§3 D-3 全文 / D-7 全文 / D-1 (5)**、**§4 A-8**、**§5 U-7 の確定**、**§6.2 C-21 / C-25**、**§6.3 (C-19 行)**、**§10 L9-2 / L9-10**、**追補 R-f**。

#### 対象ファイル (実ファイル名)

1. `r2db-api/src/r2db_api/errors.py` — `fail()` の呼び出し側で 4 key を組み立てる形
2. `r2db-api/src/r2db_api/http.py` — `_check_object_shape` の denial 形、`request_id` を下位が返した値のまま出す
3. `r2db-api/src/r2db_api/structured.py` / `postgres.py` — choke point の `violated_declaration`、`field` の要求内パス化
4. `r2db-api/src/r2db_api/service.py` — `request_id` の生成点を service 層へ下げる、**`contract_version` 1.7.0**
5. `r2db-api/src/r2db_api/control_plane.py` — **`contract_version` 1.7.0**
6. `r2db-api/src/r2db_api/ops.py` / `platform_declarations.py` — `ops verify-declarations` の検査対象に 1.7.0 の新宣言 (新 capability 3 語、`enum_members`、idempotency 2 class) を足す
7. `r2db-api/tests/test_denial_details_and_request_id.py` (**新設**)

#### 実装の指示

- **`violated_declaration` を決めるのは choke point 層と request-shape 層である。** **backend 層の defence-in-depth は残すが 4 key を持たない** — **conformance が 4 key の存在を assert することで「backend 層が先に発火する経路」が赤になる。**
- **必須規則は 3 分岐である** (追補 R-f): **`field_type` / `nullable` → `declared_type` と `observed_type` の両方必須。`enum` → `declared_type` 必須、`observed_type` は載せない。`request_schema` → `field` 必須、`declared_type` / `observed_type` は「値の型に関する違反」のときのみ。**
- **`field` は要求 body の根からの `/` 区切りパスである** (先頭に `/` を置かない)。**entity field 名を裸で置く形は採らない。** **`field` の値を要求内パスへ改める箇所は AST 全数走査で列挙する** (grep では取り逃す。第 15 次 §5 の教訓)。
- **`_check_object_shape` の現行 `details={"fields": sorted(extra)}` (複数形・リスト) を `violated_declaration: request_schema` の形へ改める** — **未知フィールドが 1 個なら `field` にその位置を単数で載せ、複数あるときは `field` を省く。** **実装裁量ではない。**
- **`request_id` の生成点を service 層へ下げ、in-process の戻り値にも載せる。** **HTTP 層は下位が返した値をそのまま出す** (再生成しない)。**要求側に `request_id` を足さない** (client 提供値を受け取らない)。
- **idempotency の replay 応答は記録済みの `request_id` を返す。**
- **`contract_version` の 4 箇所のうち r2db の 2 箇所 (`service.py` / `control_plane.py`) を同一コミットで 1.7.0 にする。** **このコミットが R-3 / R-7 の実装と同一である** (D-1 (5))。
- **`IDENTIFIER_INVALID` は r2db が発行する code なので 4 key の規則が掛かる。**

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

1. **`VALIDATION_FAILED` の必須 key が 3 分岐で正しい** — `enum` 違反に `observed_type` が載らず、`field_type` / `nullable` 違反には両方載る。
2. **`request_schema` の未知フィールド denial に `declared_type` / `observed_type` が載らず、1 個なら `field` が単数で載り、複数なら `field` が省かれる。**
3. **`IDENTIFIER_INVALID` が `field` + `violated_declaration: identifier_syntax` を必ず持つ。**
4. **`CAPABILITY_UNSUPPORTED` が `violated_declaration: capability` を必ず持つ。**
5. **`field` の値が要求内パス (`/` 区切り、先頭に `/` 無し) であり、storage 内の位置ではない。**
6. **backend 層の denial が 4 key を持たず、宣言を読む層が先に発火している。**
7. **details に行値・SQL・内部名・推奨値・修正動作が含まれない。**
8. **`QueryResult` / `MutationResult` / `SchemaOperationResult` のすべてに `request_id` が載り、in-process 経路でも載る。**
9. **`request_id` が実行ごとに異なり、`audit_query` が利用可能な plug では当該監査行の値と一致し、idempotency の replay は元実行の値を返す。**
10. **`contract_version` が data 面と control 面の両方で 1.7.0 であり、C-19 の一致 assert が緑である。**
11. **`ops verify-declarations` が 1.7.0 の新宣言を検査対象に含む。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1 | 変異 1 |
| 2 | 変異 2 |
| 3 | 変異 3 |
| 4 | 変異 4 |
| 5 | 変異 5 |
| 6 | 変異 6 |
| 7 | 変異 7 |
| 8 | 変異 8 |
| 9 | 変異 9 |
| 10 | 変異 10 |
| 11 | 変異 11 |

**変異**

1. **`enum` 違反の details に `observed_type` を載せる** → C-21 の 3 分岐 assert が赤。
2. **`_check_object_shape` の denial を現行の `{"fields": [...]}` に戻す** → C-21 の `request_schema` 枝が赤。
3. **`IDENTIFIER_INVALID` から `violated_declaration` を落とす** → C-21 が赤。
4. **`CAPABILITY_UNSUPPORTED` から `violated_declaration` を落とす** → C-21 が赤。
5. **`field` を entity field 名 (裸) に戻す** → C-21 のパス形式 assert が赤。
6. **backend 層の汎用 `VALIDATION_FAILED` を choke point より先に発火させる** → C-21 の 4 key 存在 assert が赤。
7. **details に行値を 1 つ入れる** → C-21 の unsafe-content 走査が赤。
8. **in-process 経路で `request_id` を載せない** → C-25 (1) が r2db in-process plug で赤。
9. **HTTP 層で `request_id` を再生成する** → C-25 (3) の監査行一致が赤。
10. **`control_plane.py` だけを 1.7.0 にする (data 面は 1.6.0 のまま)** → C-19 の data / control 一致 assert が赤。
11. **`ops verify-declarations` の検査対象から `enum_members` を外す** → `r2db-api/tests/test_ops_verify_declarations.py` の当該 assert が赤。

#### 監査照合項目

1. **`field` の値を要求内パスへ改めた箇所の AST 全数走査の結果** (件数と file:line)。
2. **`request_id` の生成点が service 層へ下がったことの file:line と、HTTP 層が再生成しないことの確認。**
3. **フリップ後に C-21 / C-25 の版ゲートが r2db 2 plug で通常 assert に転じ、`xfailed` が 8 → 4 になったことの実測。**
4. **`IDENTIFIER_INVALID` が r2db では発行され、MitateDB では発行されないという非対称 (L9-2) の C-21 行への開示が実態と一致すること。**

#### 非 vacuity 要件

- **C-21 は「3 code のうち少なくとも 1 つを実際に観測したこと」を per-plug で assert する。** **r2db は 3 code すべてを観測する。**
- **C-25 の (3) 監査照合まで届いた plug を明記する** — 「緑」が「監査照合した」を意味しないことを開示する。
- **版フリップの前後で C-21 / C-25 の枝が入れ替わったことを `observed_branch` で実測する。**

#### 確定文言の所在

- **契約文案は設計 §3 D-3 の 4 ブロック (`VALIDATION_FAILED` / `IDENTIFIER_INVALID` / `CAPABILITY_UNSUPPORTED` / `violated_declaration_vocabulary` / `layer_rule`) と D-7 の `request_id` ブロック。**
- **U-7 = (A) (peer ごとに独立したフリップコミット) の確定は設計 §5 U-7。**
- **必須規則の 3 分岐は追補 R-f。**

#### 同型性テストの対象

- **request path (`details.field`) の組み立てヘルパ。** **両 peer に同名で置く。**
- **`_verify_declarations_checks` / `cmd_verify_declarations` は既に `_ISOMORPHIC_TARGETS` に載っている** — **本 WP が中身を変えるので、両 peer の変更が揃ってから同型性が成立する。** **表の行そのものは既にあるので追加は不要だが、同型性が成立するのは pair (WP-2e と WP-3e) が両方 main にマージされた後であり、その確認は監督の pair-closing commit で行う** (裁定 T-2)。**実装担当は自 peer 側で変えた同名シンボルの一覧を報告に書く。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests/test_denial_details_and_request_id.py
./.venv/bin/python -m pytest -q conformance-tests/test_c21_denial_details_vocabulary.py conformance-tests/test_c25_result_request_id.py conformance-tests/test_c19_client_self_sufficiency.py
./.venv/bin/python -m pytest -q r2db-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

1. **契約を変えない。`conformance-tests/` を触らない。**
2. **`request_id` を client 提供値にしない** (要求側にフィールドを足さない)。
3. **`request_id` を `required` にしない** (契約は optional のままである。義務側で必須にする)。
4. **backend 層に 4 key を足さない。**
5. **`IDENTIFIER_INVALID` の発行を MitateDB に合わせて止めない。**
6. **版フリップを R-3 / R-7 と別のコミットにしない。** **フリップコミットに他の変更を混ぜない** (この WP の R-3 / R-7 実装以外)。
7. **MitateDB 側のファイルを触らない。**
8. **設計外の検査・機構を足す前に報告して裁定を待つ。**

#### 報告形式

**WP-2a と同一。加えて、フリップコミットの内容 (何が同一コミットに入ったか) を逐語で報告する。**

---

### WP-3a MitateDB — R-2 制約宣言と `alter_field`

**着手条件: WP-1 の main マージ後。worktree `.claude/worktrees/phase9-mitatedb`、branch `phase9-mitatedb`。WP-2a と並行。**

#### 目的

**WP-2a と同一の命題を MitateDB で成立させる。** **契約上の意味・強制点・code・details を r2db と一致させ、実現方式は platform に従わせる** (P-6)。

#### 前提として読む箇所 (設計)

**WP-2a と同じ箇所に加えて、追補 R-a (backend ごとの書き分け)、追補 2 S-g (schema 経路の tx 構造と developer role の SELECT 権限)、レビュー 2 m2 / m11 (docstring とシグネチャの実態)。**

#### 対象ファイル (実ファイル名)

1. `MitateDB-api/src/mitatedb_api/field_types.py` — `check_declared_value` のシグネチャ変更と enum / nullable 検査
2. `MitateDB-api/src/mitatedb_api/cell.py` — `_prepare_values` の全経路に `constraints` を渡す、`_bind_filters` には渡さない、`_plan_operation` の insert 分岐に欠落検査、`create_entity` / `add_field` / `alter_field`、`catalog()` の `field_constraints`、capability 宣言
3. `MitateDB-api/src/mitatedb_api/backend_postgres.py` — `_mdb_field_types` への列追加、**`alter_field_constraints` の新設** (§0.0 の 4 (c) で名を確定)
4. `MitateDB-api/src/mitatedb_api/backend_sqlite.py` — `_declared_types` と同じプロセス内構造に制約を持つ
5. `MitateDB-api/src/mitatedb_api/backend.py` — backend 抽象への新メソッド
6. `MitateDB-api/src/mitatedb_api/http.py` — `alter_field` の present-denial 解除、provisional gate の該当行の撤去
7. `MitateDB-api/src/mitatedb_api/config.py` — `enum_members` の既定値と env 名
8. `MitateDB-api/src/mitatedb_api/ops.py` — per-application upgrade の対象に載せる
9. `MitateDB-api/migrations/0009_field_constraints_upgrade.sql` (**新設**、Postgres backend のみ)
10. `MitateDB-api/tests/test_constraints_declaration.py` (**新設**)
11. `MitateDB-api/conformance/conformance_adapter_mitatedb.py` / `conformance_adapter_mitatedb_http.py` — **隔離 profile の `enum_members` の値のみ**

#### 実装の指示 (WP-2a との差分)

- **choke point は `check_declared_value` である。** **現行シグネチャは `def check_declared_value(value, declared_type) -> None:` で `*` が無い** (レビュー 2 m11)。**新シグネチャは `def check_declared_value(value, declared_type, *, constraints=None) -> None:` である。**
- **書き込み側は `_prepare_values` の全経路 (insert / update / upsert / batch) に `constraints` を渡す。** **predicate 側は `_bind_filters` の 2 呼び出しであり、渡さない** (追補 2 S-k。**設計 v1.1 が 1 箇所と数えていたのは実測で 2 呼び出しである**)。
- **欠落検査は `_plan_operation` の insert 分岐に置く** (`_prepare_values` 呼び出しの直前)。**検査順序は「欠落検査 → 値検査」であり r2db と揃える。**
- **宣言の正本**: **Postgres backend は `_mdb_field_types` に列を足す** (per-application upgrade script)、**SQLite backend は `_declared_types` と同じプロセス内構造に持つ** (**upgrade script を持たない** — この backend は `:memory:` のプロセス内 backend である)。
- **`alter_field` は backend に新設する 1 メソッド `alter_field_constraints` が、1 つの tx の中で「違反行の SELECT → registry 更新 → revision bump → commit」を行う形にする** (追補 2 S-g)。**既存の `create_collection` / `add_field` の「読んでから別 tx で DDL」の型に倣わない。** **cell 層の pre-flight 位置に走査を置いてはならない** — その位置は別トランザクションであり commit する。
- **developer role は `public` schema の所有者であり** (`MitateDB-api/migrations/0003_provision_application.sql`)、**application table をすべて自分で作るので所有者として SELECT できる。明示 GRANT は要らない** (追補 2 S-g、F-6 の未確認点は解決済み)。
- **`enum_members` は `config.py` の既定値 + `MITATEDB_MAX_*` env 名の対応表に同型で足す。**

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

**1〜12 は WP-2a の 1〜12 と同一の命題である** (peer が MitateDB であること以外は同じ)。**加えて:**

13. **`alter_field` の違反行走査と registry 更新・revision bump が 1 つのトランザクション内で行われ、走査と更新の間に他 session の書き込みが入れる隙間が無い。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1〜12 | **変異 1〜12** (WP-2a の変異 1〜12 を MitateDB の該当箇所に読み替えたもの。**変異 1 は `_prepare_values` の upsert 経路、変異 3 は `_bind_filters` の 2 呼び出し、変異 5 は `_plan_operation` の insert 分岐、変異 10 は `migrations/0009_field_constraints_upgrade.sql`**) |
| 13 | **変異 13** |

**変異 13**: **既存行走査を `alter_field_constraints` から cell 層の pre-flight 位置 (`field_domains` と同じ場所、別トランザクション) へ移す** → **`MitateDB-api/tests/test_constraints_declaration.py` の「走査と更新の間に commit が挟まらない」テストが赤。** **この命題は共通条件では観測できない** (C-20 (6) は「1 行も変わっていない」しか見ない) — **その限界を C-20 行に開示済みである。**

#### 監査照合項目

1. **`check_declared_value` の呼び出し全数の AST 走査 (書き込み側 / predicate 側の内訳)。**
2. **`alter_field_constraints` が単一 tx であることの file:line と、cell 層 pre-flight が commit することの再確認。**
3. **developer role の SELECT 権限が所有者権限で足りることの実測。**
4. **隔離 profile の `enum_members` の確定値。**

#### 非 vacuity 要件

**WP-2a と同一 (plug は MitateDB 2 plug)。**

#### 確定文言の所在

**WP-2a と同一。加えて追補 R-a (backend ごとの書き分け) と追補 2 S-g。**

#### 同型性テストの対象

**WP-2a と同一。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests/test_constraints_declaration.py
./.venv/bin/python -m pytest -q conformance-tests/test_c20_constraint_declaration_agreement.py
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

**WP-2a の 1〜9 と同一 (「MitateDB 側のファイルを触らない」を「r2db 側のファイルを触らない」に読み替える)。加えて:**

10. **`schema_objects` の数え方を変えない** (L9-1 は本フェーズで解消しない)。**`max_fields` の扱いも変えない。**
11. **既存行走査を cell 層の pre-flight 位置に置かない。**

#### 報告形式

**WP-2a と同一。**

---

### WP-3b MitateDB — R-4 dry_run と無状態 plan

**着手条件: WP-3a の完了後 (同一 worktree で直列)。**

#### 目的

**WP-2b と同一の命題を MitateDB で成立させる。** **あわせて、plan の失効を返すために `PRECONDITION_FAILED` を初めて発行できるようにする。**

#### 前提として読む箇所 (設計)

**WP-2b と同じ箇所に加えて、§1.2 F-13 (訂正後: `_plan_operation` は DML の副作用を持たない。カタログ読み取りは別接続で commit する)、§10 L9-2 (2 分割後)、追補 2 S-h。**

#### 対象ファイル (実ファイル名)

1. `MitateDB-api/src/mitatedb_api/cell.py` — `transact` の COMMIT / ROLLBACK 点の分岐、schema 操作 (`create_entity` / `add_field` / `alter_field`) の出口分岐、digest 計算点、plan の照合
2. `MitateDB-api/src/mitatedb_api/errors.py` — **`PRECONDITION_FAILED` を発行する例外クラスの新設**
3. `MitateDB-api/src/mitatedb_api/http.py` — `_problem_for_exception` に code 別文言を足す、provisional gate の該当行の撤去
4. `MitateDB-api/conformance/conformance_adapter_mitatedb.py` — in-process 経路で同じ details が出ること
5. `MitateDB-api/tests/test_dry_run_and_plan.py` (**新設**)

#### 実装の指示 (WP-2b との差分)

- **`transact` の COMMIT / ROLLBACK 点で分岐する。** **schema 操作は個別に tx を持つので、それぞれに同じ出口分岐を置く。**
- **監査 hook (`_make_audit_hook` → `AuditRouter`) を dry_run では組み立てない。**
- **`PRECONDITION_FAILED` を発行する例外クラスを新設し、`_problem_for_exception` に code 別文言を足す** (追補 2 S-h)。**in-process 経路と HTTP 経路の両方が同じ details を出すことを確認する** (F-10 の 2 経路)。
- **`revision_preconditions` (行単位の precondition) が `unavailable` である事実は変えない** — **本 WP が変えるのは「`PRECONDITION_FAILED` を発行しない実装ではなくなる」ことだけである** (L9-2 の 2 分割)。
- **`PRECONDITION_FAILED` は D-3 の 4 key 必須規則が掛かる 3 code に含まれない** — **`violated_declaration: plan` を任意で載せる側である。**
- **digest / plan の規則は WP-2b と同一である** (契約が定める)。**コードは共有しない。**

#### 完了条件 (assert 水準。1 項目 = 変異 1 つ)

**1〜10 は WP-2b の 1〜10 と同一の命題である。加えて:**

11. **`PRECONDITION_FAILED` が in-process 経路と HTTP 経路の両方で同じ code / details として出る。**

#### 完了条件 → 変異 の対応表

| 完了条件 | 対応する変異 |
|---|---|
| 1〜10 | **変異 1〜10** (WP-2b の変異を MitateDB の該当箇所に読み替えたもの) |
| 11 | **変異 11** |

**変異 11**: **`_problem_for_exception` から `PRECONDITION_FAILED` の行を削る** → **C-22 (8)(9) が MitateDB HTTP plug で赤** (別の code が返る)。

#### 監査照合項目

**WP-2b と同一。加えて: `PRECONDITION_FAILED` の新設が `revision_preconditions` の宣言を変えていないことの確認 (L9-2)。**

#### 非 vacuity 要件

**WP-2b と同一 (plug は MitateDB 2 plug)。**

#### 確定文言の所在

**WP-2b と同一。加えて追補 2 S-h。**

#### 同型性テストの対象

**WP-2b と同一 (digest 正規化関数、plan の組み立て / 照合ヘルパ)。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests/test_dry_run_and_plan.py
./.venv/bin/python -m pytest -q conformance-tests/test_c22_dry_run_and_plan.py
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

**WP-2b の 1〜8 と同一 (peer を読み替える)。加えて:**

9. **`revision_preconditions` を `unavailable` から動かさない** (行単位の precondition は本フェーズの範囲外である)。
10. **`IDENTIFIER_INVALID` を発行するようにしない** (L9-2 の開いたまま側)。

#### 報告形式

**WP-2b と同一。**

---

### WP-3c MitateDB — R-5 idempotency

**着手条件: WP-3b の完了後 (同一 worktree で直列)。**

#### 目的・前提として読む箇所

**WP-2c と同一。加えて追補 R-a (SQLite backend はプロセス内である)。**

#### 対象ファイル (実ファイル名)

1. `MitateDB-api/src/mitatedb_api/cell.py` — 照会位置、記録の読み書き、capability 宣言、limits 宣言 2 class
2. `MitateDB-api/src/mitatedb_api/backend_postgres.py` — 記録テーブルの読み書き (data tx と同一 tx)
3. `MitateDB-api/src/mitatedb_api/backend_sqlite.py` — 同 backend のプロセス内構造
4. `MitateDB-api/src/mitatedb_api/backend.py` — backend 抽象への追加
5. `MitateDB-api/src/mitatedb_api/http.py` — present-denial と provisional gate の該当行の撤去
6. `MitateDB-api/src/mitatedb_api/config.py` — `idempotency_entries` / `idempotency_retention_ms` の既定値と env 名
7. `MitateDB-api/migrations/0010_idempotency_records_upgrade.sql` (**新設**、Postgres backend のみ)
8. `MitateDB-api/src/mitatedb_api/ops.py` — per-application upgrade の対象に載せる
9. `MitateDB-api/tests/test_idempotency_records.py` (**新設**)

#### 実装の指示 (WP-2c との差分)

- **Postgres backend は application DB の side table、SQLite backend は同 backend のプロセス内構造である** (どちらも data tx と同一 tx に書ける)。**SQLite backend は upgrade script を持たない。**
- **照会位置は `_limit_gate` の後、`transact` の pass1 (`_plan_operation`) より前である** (追補 2 S-b の「bound の後、target-existence の前」)。
- **その他の命題・順序・禁止事項は WP-2c と同一である。**

#### 完了条件 / 対応表 / 変異

**WP-2c の 1〜9 と同一の命題・同一の変異を MitateDB の該当箇所に読み替えたもの** (変異 8 は `MitateDB-api/src/mitatedb_api/cell.py` の `limits` ブロック)。**完了条件 9 項目 / 変異 9 件。**

#### 監査照合項目 / 非 vacuity 要件 / 確定文言の所在 / 同型性テストの対象

**WP-2c と同一** (plug は MitateDB 2 plug)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests/test_idempotency_records.py
./.venv/bin/python -m pytest -q conformance-tests/test_c23_idempotency_semantics.py conformance-tests/test_c07_atomicity_and_retry.py conformance-tests/test_c05_limit_declaration_agreement.py
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

**WP-2c の 1〜8 と同一 (peer を読み替える)。**

#### 報告形式

**WP-2a と同一。**

---

### WP-3d MitateDB — R-6 request budget

**着手条件: WP-3c の完了後 (同一 worktree で直列)。**

#### 目的・前提として読む箇所

**WP-2d と同一。**

#### 対象ファイル (実ファイル名)

1. `MitateDB-api/src/mitatedb_api/config.py` — 実効値の生成 (`narrowed_by` 相当)
2. `MitateDB-api/src/mitatedb_api/cell.py` — `_limit_gate` と `transact` / read の参照点が実効値を見る形、budget の妥当性検査の位置
3. `MitateDB-api/src/mitatedb_api/backend_postgres.py` / `backend_sqlite.py` — deadline の逆算に実効値を使う
4. `MitateDB-api/src/mitatedb_api/http.py` — provisional gate の該当行の撤去
5. `MitateDB-api/tests/test_budget_narrowing.py` (**新設**)

#### 実装の指示 (WP-2d との差分)

- **MitateDB は `MITATEDB_MAX_*` env で配備値を上書きできる** (L9-3 の非対称)。**実効値は「配備値 (env 反映後) と budget の小さい方」である。**
- **`result_items` の拒否が「返した行数」ではなく「要求された `limit` の値」で決まる現行を変えない** (L9-11)。**C-24 が `result_items` を駆動するか否かは WP-1 の実測に従う。**
- **その他は WP-2d と同一である。**

#### 完了条件 / 対応表 / 変異

**WP-2d の 1〜7 と同一の命題・同一の変異を MitateDB の該当箇所に読み替えたもの。** **完了条件 7 項目 / 変異 7 件。**

#### 監査照合項目 / 非 vacuity 要件 / 確定文言の所在 / 同型性テストの対象

**WP-2d と同一** (plug は MitateDB 2 plug)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests/test_budget_narrowing.py
./.venv/bin/python -m pytest -q conformance-tests/test_c24_request_budget.py conformance-tests/test_c05_limit_declaration_agreement.py
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

**WP-2d の 1〜7 と同一 (peer を読み替える)。**

#### 報告形式

**WP-2a と同一。**

---

### WP-3e MitateDB — R-3 details 語彙 + R-7 `request_id` + 版フリップ

**着手条件: WP-3d の完了後 (同一 worktree で直列)。**

#### 目的・前提として読む箇所

**WP-2e と同一。加えて §1.2 F-7 / F-10 (MitateDB の `ValidationError` / `CapabilityError` は details 属性そのものを持たない。message は HTTP 層の `_problem_for_exception` が code 別固定文言に置換する)。**

#### 対象ファイル (実ファイル名)

1. `MitateDB-api/src/mitatedb_api/errors.py` — **`ValidationError` / `CapabilityError` に `details` 属性を新設**
2. `MitateDB-api/src/mitatedb_api/cell.py` — choke point / `_plan_operation` の denial に 4 key、`request_id` の生成点を cell 層へ、**`contract_version` 1.7.0**
3. `MitateDB-api/src/mitatedb_api/field_types.py` — choke point の `violated_declaration`
4. `MitateDB-api/src/mitatedb_api/http.py` — `_check_object_shape` の denial 形、整形が details をそのまま出すこと、`request_id` を下位が返した値のまま出す
5. `MitateDB-api/src/mitatedb_api/control_plane.py` — **`contract_version` 1.7.0**
6. `MitateDB-api/src/mitatedb_api/ops.py` / `platform_declarations.py` — `ops verify-declarations` の検査対象に 1.7.0 の新宣言を足す
7. `MitateDB-api/conformance/conformance_adapter_mitatedb.py` — in-process 経路が同じ details を出すこと
8. `MitateDB-api/tests/test_denial_details_and_request_id.py` (**新設**)

#### 実装の指示 (WP-2e との差分)

- **`ValidationError` / `CapabilityError` に `details` 属性を新設する** — **現行は 105 箇所の呼び出しに details 引数が 0 件である。**
- **`http.py` の整形と in-process の整形の両方が同じ details を出すことを確認する** (F-10 の 2 経路)。**message は HTTP 層で code 別固定文言に置換されるので、details に載せる以外に構造化情報を運ぶ経路が無い。**
- **`IDENTIFIER_INVALID` を発行しない現行を変えない** (L9-2 の開いたまま側)。**したがって C-21 の `IDENTIFIER_INVALID` 枝は MitateDB 2 plug で観測されない** — **これは適用範囲の帰結であり空振りではない。**
- **その他は WP-2e と同一である。**

#### 完了条件 / 対応表 / 変異

**WP-2e の 1〜11 と同一の命題・同一の変異を MitateDB の該当箇所に読み替えたもの。ただし完了条件 3 (`IDENTIFIER_INVALID` の必須 key) は MitateDB では発行されないため、次のように読み替える:**

3'. **MitateDB は `IDENTIFIER_INVALID` を発行せず、識別子違反は `VALIDATION_FAILED` + `violated_declaration: identifier_syntax` として 4 key を持つ。**

**変異 3'**: **識別子違反の denial から `violated_declaration` を落とす** → C-21 が MitateDB 2 plug で赤。

**完了条件 11 項目 / 変異 11 件。**

#### 監査照合項目

**WP-2e の 1〜4 と同一。加えて: `ValidationError` / `CapabilityError` の 105 箇所の呼び出しのうち details を持つようになった箇所の全数 (AST 走査)。**

#### 非 vacuity 要件

- **C-21 は per-plug で「3 code のうち少なくとも 1 つを実際に観測したこと」を assert する。** **MitateDB では `VALIDATION_FAILED` と `CAPABILITY_UNSUPPORTED` が観測される。**
- **フリップ後に `xfailed` が 4 → 0 になったことを実測する。**

#### 確定文言の所在 / 同型性テストの対象

**WP-2e と同一。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests/test_denial_details_and_request_id.py
./.venv/bin/python -m pytest -q conformance-tests/test_c21_denial_details_vocabulary.py conformance-tests/test_c25_result_request_id.py conformance-tests/test_c19_client_self_sufficiency.py
./.venv/bin/python -m pytest -q MitateDB-api/tests
```

#### 使用テンプレート

**テンプレ 2 → テンプレ 5 → テンプレ 6。**

#### 禁止事項

**WP-2e の 1〜8 と同一 (peer を読み替える)。加えて:**

9. **`IDENTIFIER_INVALID` を発行するようにしない。**

#### 報告形式

**WP-2e と同一。**

---

### WP-4 完了ゲートと記録

**着手条件: WP-2e / WP-3e の完了後。最後・単独。**

#### 目的

**完了ゲートを取り、実施記録を残し、台帳を締め、計画文書を改版し、第 16 次引き継ぎを起こす。**

#### 対象ファイル (実ファイル名)

1. `conformance-tests/COLLECTION_FLOOR` (**監督のゲート作業**)
2. `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` — §9 / §10 / §11
3. `docs/design/ROADMAP_POST_PHASE7_V1.md` — §1「現状」、§5 フェーズ9 節、**§8 R-8 行 (U-5 = (B) の改版註)**、**§5 R-4 行 (追補 2 S-i の改版註)**
4. `docs/work-orders/WORK_ORDER_PHASE9_CONTRACT_170_V1.md` — §6 訂正註
5. `docs/work-orders/HANDOVER_2026MMDD_FABLE.md` (**第 16 次、新設**)

#### 完了条件 (assert 水準。全項が監査照合)

1. **設計 §11.1 の全項目が埋まっている** (取得条件 / root suite の集計行と EXIT / CI 3.11・3.12 の集計行と run id / `--collect-only -q` の件数と `COLLECTION_FLOOR` 更新 / xfail の残数と内訳 / 契約 3 複製の新 sha256 / R-10 (B) の deep-equal 結果と走査キー数 / 剥離によるバイト減少量 / `unstripped` 件数 / 両 peer の `contract_version` 4 箇所 / provenance スキャナのヒット数 0 / `test_contract.py` の件数正規表現の非破壊 / `assert checked == 17` の非改訂通過)。 — **監査照合**。
2. **設計 §11.2 に性能差分が記録されている** (フェーズ8 §11.2 と同形式の PERFRUN 行 + PERF 表 + 同一 plug の版間差分 p50 / p95 / `backend_calls`)。**plug 間の比較はしない。閾値は置かない。** — **監査照合**。
3. **設計 §11.3 に WP ごとの実測項目が記録されている** (本書の各 WP「監査照合項目」の全数)。 — **監査照合**。
4. **設計 §10 の台帳 (L9-1〜L9-13) の状態が実測結果で確定している。** **L9-7 (L7-8) / L9-8 (L8-4) / L9-9 (L8-9) が閉じ、L9-2 の `PRECONDITION_FAILED` 側が閉じている。** — **監査照合**。
5. **計画文書 §8 の R-8 行に U-5 = (B) の改版註 (R-14 の規約、根拠と日付) が入っている。** — **監査照合**: 設計 §10.1 の文案と逐語一致すること。
6. **計画文書 §5 の R-4 行に追補 2 S-i の改版註 (plan の schema 成分が per-application であること、根拠 F-16、無関係 entity の schema 操作で失効するのは fail-closed 側の誤差であること) が入っている。** — **監査照合**。
7. **計画文書 §1「現状」と §5 フェーズ9 節が更新されている。** — **監査照合**。
8. **`COLLECTION_FLOOR` がゲート時の実測値へ更新されている。** — **監査照合**。
9. **第 16 次引き継ぎが新設され、前書全項の継承が明示されている。** **前書の全項を複製しない。** — **監査照合**。
10. **本書 §6 の訂正註が、本文を書き換えずに置かれている。** — **監査照合**。
11. **依頼者への報告事項がまとまっている** — **委任 (2026-09-07) に基づいて監督が確定した U-1〜U-8・追補・追補 2 の内容と根拠**。 — **監査照合**: 設計 §5 の逐語と一致すること。
12. **公開規律**: 本 WP の全成果物に実値が 1 件も無い。`./.venv/bin/python tools/public_value_scan.py` が **total_flagged=0**。 — **監査照合**。
13. **対応表に対応の無い行が無いこと** (メタ条件)。

#### 完了条件 → 変異 の対応表

**本 WP の成果物はすべて文書・記録である。** **常設規律 2 の運用に従い変異を作らず、全項目を監査照合とする** (フェーズ8 WP-6 と同じ形)。**監査は照合対象の逐語記録 (file:line と引用文) を報告に引く。**

| 完了条件 | 対応 |
|---|---|
| 1〜12 | **監査照合** (各条件の本文に照合対象を明記済み) |
| 13 | 本表そのもの (メタ条件) |

#### 非空振り要件

- **記録は「未記入」を残さない。** 取得できなかった項目は「取得できなかった理由」を書く。
- **監査は §11 の記録を逐語で報告に引く。**

#### 確定文言の所在

- **U-1〜U-8 と追補・追補 2 の逐語は設計 §5 / §3 に記録済みである。** **引き継ぎ・報告に書く場合は設計から複製し、言い換えない。**
- **計画文書の改版文案は設計 §10.1 (R-8) と追補 2 S-i (R-4) が正本である。**

#### 同型性テストの対象

**無い** (文書のみ)。

#### テストコマンド

```
./.venv/bin/python tools/public_value_scan.py
```

#### 使用テンプレート

**Opus 起草 = テンプレ 4** → **監督** → **Opus 証拠監査 = テンプレ 6**。

#### 禁止事項

1. **実測を推測で埋めない。**
2. **本書の本文を書き換えない** — 訂正は §6 の訂正註として残す。
3. **計画文書の改版で、R-4 / R-8 とフェーズ9 節・§1 以外の行を動かさない。**
4. **`COLLECTION_FLOOR` の更新を実装担当が行わない** (監督のゲート作業)。
5. **実値を書かない。**
6. **第 16 次引き継ぎで前書の全項を複製しない。**
7. **設計外の決定を足す前に報告して裁定を待つ。**

#### 報告形式

1. 触ったファイルと変更行数。
2. **設計 §11.1 / §11.2 / §11.3 の記入内容** (逐語)。
3. **計画文書の改版前後の R-4 行 / R-8 行** (逐語)。
4. **`tools/public_value_scan.py` の出力** (total_flagged=0)。
5. **依頼者への報告事項** (委任のもとで確定した内容と根拠)。
6. **設計との食い違い** (あれば)。

---

## 3. 完了ゲート (設計 §9 の転記)

**監督が単独で実行する。** **`ps` で他の pytest プロセスが 0 件であることを確認してから、リポジトリルートで実行する。** **ローカル PostgreSQL の `max_connections = 300` が前提である。**

1. **root suite の単独実行**:

   ```
   ./.venv/bin/python -m pytest -q -n 5 --dist loadgroup
   ```

   - **`failed` = 0**
   - **`xfailed` = 0** (**WP-1 が置く 8 本はすべて 2e / 3e のフリップで外れる。残るなら、その組と理由を台帳と当該条件行に開示する**)
   - **`skipped` = 0**
2. **CI の 3.11 job の集計行が 1 の集計行と一致すること。** **`tally-consistency` job が緑** (3.11 / 3.12 の 4 数の一致)。**collection floor step が 3.11 / 3.12 の両 job で緑であること。**
3. **性能差分を設計 §11.2 に記録すること**:

   ```
   ./.venv/bin/python tools/perf_baseline.py --warmup 20 --n 200
   ```

   **単独実行** (他の pytest が 0 件、`pg_database` の前後差分 0)。**フェーズ8 §11.2 と同形式** (PERFRUN 行 + PERF 表) で記録し、**同一 plug の版間差分 (p50 / p95 / `backend_calls`)** を並記する。**plug 間の比較はしない** (L8-11)。**閾値は無い** (P-8)。**本フェーズは「2 フェーズ安定」の 2 フェーズ目である。**
4. **`COLLECTION_FLOOR` をゲート時の実測値へ更新すること** (着手時点は **2340**)。
5. **契約 1.7.0 の記録**: **契約 JSON と両 peer の packaged 複製 2 本の sha256 が 3 本一致すること**を設計 §11.1 に記録する (**値はフェーズ8 の値から必ず動く**)。**R-10 (B) のマニフェスト逆適用 deep-equal 検証の結果 (差分 0 と走査キー数) も記録する。**
6. **両 peer の `contract_version` が 1.7.0 であること** — 4 箇所 (`r2db-api/src/r2db_api/service.py` / `control_plane.py`、`MitateDB-api/src/mitatedb_api/cell.py` / `control_plane.py`) と、**C-19 の data 面 / control 面一致 assert が緑であること。**
7. **新条件 C-20〜C-25 が four adapters で executable であること** — `CONDITIONS.md` の 6 行が `executable (four adapters)` であり、`test_conditions_register.py` の照合が緑であること。**各条件の per-plug 非 vacuity assert が緑であること。**
8. **両 peer がフリップした後、4 plug すべてが肯定枝であることを、xfail / `observed_branch` の集計行で確認すること** (追補 2 S-c)。
9. **両 peer の capability document が `idempotency_entries` / `idempotency_retention_ms` を宣言していること** (追補 2 S-f)、および **`capability_status.defined` の 14 語すべてを名指していること** (レビュー 2 m7。**固定するのは C-11 の逆方向 assert である。裁定 T-4**)。
10. **全 WP が常設規律 1〜7 と速度規律 1〜5 を満たすこと。** **各 WP の「完了条件番号 → 変異」対応表に、対応の無い行が無いこと。** **監査照合項目については、照合対象の逐語記録 (実行したコマンドと集計行、または file:line) を設計 §11 に残すこと自体を完了条件とする。**
11. **設計レビュー 2 回が実施済みであること** (v1.0 → v1.1 → v1.2)。**v1.3 はレビューではなく、作業指示書起草者の疑義 4 件に対する監督裁定 T-1〜T-4 の反映である。**
12. **§5 U-1〜U-8 の確定が設計 §5 に逐語で記録されていること。** **確定文言が確定文ファイル経由で複製されていること** (常設規律 4)。
13. **`pg_database` の前後差分が 0 であること。他の pytest が 0 件であること。**
14. **provenance スキャナへの 0 ヒット**、**`test_contract.py` の件数正規表現の非破壊**、**`assert checked == 17` の非改訂通過** の 3 実測が設計 §11.1 に記録されていること。

---

## 4. コミット規律

1. **git commit / push / merge は監督のみが行う。** **実装担当は commit しない。**
2. **push 前に identity を確認する。確認は commit と同一のコマンドで行う** (SHARED-CHECKOUT RULE、第 14 次 §4-3):

   ```
   git log --format='%an <%ae>' -5
   ```

   **`r2fish` / noreply のみであること。** 実名・Gmail アドレスが 1 件でもあれば push しない。
3. **branch の確認は commit と同一のコマンドで行う** (並行チャットとの衝突を避けるため):

   ```
   git -C <worktree> symbolic-ref --short HEAD && git -C <worktree> commit -m "…"
   ```

4. **commit → push → main マージは 1 セットである** (依頼者ルール、2026-08-29 に拡張)。**マージは scratchpad 下の一時 worktree 経由で行う** — **共有ツリーを checkout しない。**
5. **契約バージョンに触れるコミット (WP-1 の契約 1.7.0 公開、WP-2e / WP-3e の版フリップ) は、依頼者裁定の委任のもとで監督が実施し、完了報告に記す。**
6. **宣言と挙動は同一コミットである** — capability の gate 撤去・status の `enabled` 化・挙動・その peer のローカルテストを capability ごとに 1 コミットに収める。
7. **版フリップは 2 コミット (peer ごと) であり、完了ゲート内で連続して main にマージする。** **フリップ間に他のコミットを挟まない** (U-7 = (A))。
8. **契約 JSON の 3 複製は同一コミットで同一バイトに更新する。** **コミット前に 3 本の sha256 が一致することを確認する。**
9. **公開規律**: コミット前に `.pre-commit-config.yaml` の local hook (staged なファイルに対して走る) が緑であること。**実ホスト名・FQDN・cloud project 識別子・実 e-mail・実 credential_id・IAM principal・作業機の絶対パス・実 DSN を 1 件も含めない。** **新設ファイルは `tools/public_value_scan.py` に明示引数で渡す。**
10. **変異を含むコミットを作らない。** **変異の復元は scratchpad backup からの `cp` + `sleep 3` 後の sha256 二重照合であり、コミット前に変異文字列を全文 grep してゼロを確認する。** **`git checkout --` は使わない。** **WP-1 の一時フリップ (§2 WP-1 の (12)) も同じ扱いである。**
11. **`COLLECTION_FLOOR` の更新コミットは完了ゲートの一部である** (監督)。**下げる場合は理由を commit message に書く。**
12. **同型性表 `_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py`) への行追加は監督の pair-closing commit である** (裁定 T-2、設計 §8)。**capability ごとの pair (WP-2x と WP-3x) が両方 main にマージされた後に、監督が 1 コミットで両 peer 分を足す。** **監督は両 peer の isomorphism テストを実行して緑を確認してからマージする。** **実装担当はこの行追加を自分のコミットに含めない** — 含めれば並行する 2 WP の唯一の重なりを作る (§5)。**実装担当は自 peer 側の helper 名と対応する相手側の helper 名を報告に書く。**

---

## 5. WP-9 (フェーズ7 公開ゲート) との重なり 0

**設計 §8.1 の最終行を実ファイル名で確認した結果である。**

| 組 | 重なり | 根拠 |
|---|---|---|
| **本フェーズ全 WP × WP-9** | **0** | **WP-9 が触るのは `tools/rewrite_hash_refs.py` と `docs/` 配下の hash 参照の一括更新のみである。** **本フェーズが `tools/` に足すのは `tools/contract_catalog.py` (新設) だけであり、`tools/rewrite_hash_refs.py` を作りも直しもしない。** 本フェーズが新設・改訂する docs (`docs/design/PHASE9_*.md`、`docs/work-orders/WORK_ORDER_PHASE9_*.md`、第 16 次引き継ぎ) に commit hash を書いた場合、**WP-9 の commit-map 適用対象になるだけで衝突しない。** |

- **本フェーズは `tools/rewrite_hash_refs.py` を触らない。** これは全 WP に掛かる禁止事項である。
- **hash を書くこと自体は禁止しない。**
- **WP-9 の着手合図が来たら、進行中の WP は worktree を畳んで待つ** — filter-repo の前に worktree を畳む必要があるためである。**この判断は監督が行う。実装担当は自分で判断しない。**

**本フェーズ内の重なり** (設計 §8.1 の表):

| 組 | 重なり | 根拠 |
|---|---|---|
| **WP-2 × WP-3** | **0** | WP-2 は `r2db-api/` 配下のみ、WP-3 は `MitateDB-api/` 配下のみ。**共有ディレクトリ (`conformance-tests/` / `spec/` / `tools/` / `docs/`) はどちらも触らない。** **唯一の例外候補だった `_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py`) への行追加は、どちらの実装 WP も行わない** — **pair (WP-2x と WP-3x) が両方 main にマージされた後に監督が 1 コミット (pair-closing commit) で両 peer 分を足す** (裁定 T-2、設計 §8 / §8.1、§4 の 12)。**したがって重なりは 0 のままである。** |
| **WP-1 × WP-2 / WP-1 × WP-3** | **重なる (直列で解消する)** | WP-1 は provisional gate のために両 peer の `src` と packaged 複製、4 adapter を触る。**WP-1 → WP-2 / WP-3 の直列である。** |
| **WP-1 × WP-4 / WP-2 × WP-4 / WP-3 × WP-4** | **0** | WP-4 は `COLLECTION_FLOOR` と `docs/` のみ。 |

---

## 6. 訂正註

**(本フェーズの実施中に、本書の誤り・発注後の監督裁定が生じた場合にここへ追記する。本文は書き換えない。)**

1. **【設計への疑義 (起草時、2026-09-07)】設計 §3 D-4 (3) は dry_run が `plan` を返すと定めているが、D-4 の「実装の形 1」(契約 WP の変更一覧) は `schemas.MutationResult.properties.plan` / `schemas.SchemaOperationResult.properties.plan` の追加を挙げていない。** **3 result schema はいずれも `additionalProperties: false` であるから、追加しなければ dry_run 応答が C-11 (response schema conformance) で赤になる。** **本書 §2 WP-1 の変更一覧 #21 はこれを追加として書いた。** **設計 v1.2 が別の形を採っている場合は設計が正であり、本書の誤りとして差し戻すこと。** **【裁定 T-1 で解決 (2026-09-07)】** **監督裁定 T-1 が `schemas.MutationResult.properties.plan` と `schemas.SchemaOperationResult.properties.plan` (string, optional) を契約に足すことを確定し、設計 v1.3 が D-4「実装の形 1」と §5 U-8 の表に #29 として追加した。** **`required` は変えない。** **本書 §2 WP-1 の変更一覧 #21 はそのまま有効である** (出所を #29 に改めた)。
2. **【運用上の裁定待ち (起草時、2026-09-07)】`_ISOMORPHIC_TARGETS` (両 peer の `tests/test_audit_query.py`、現行 86 行) への行追加は、両 peer の同名シンボルが揃ってからでないと成立しない。** **行追加は両 peer のファイルを同時に触るので、WP-2 × WP-3 の「触るファイルの重なり 0」を破る。** **既存の慣行は「pair の後半の WP が両 peer 分の行をまとめて足す」であるが、本フェーズでは WP-2 と WP-3 が最後まで並行するため、その慣行がそのままは使えない。** **実装担当は行追加を自分の判断で行わず、対象シンボルの一覧を添えて監督へ上げること** (常設規律 5)。 **【裁定 T-2 で解決 (2026-09-07)】** **行追加は、capability ごとの pair (WP-2x と WP-3x) が両方 main にマージされた後に、監督が 1 コミット (pair-closing commit) で両 peer 分を足す。** **各 peer の実装担当は、自 peer 側の helper 名と対応する相手側の helper 名 (本書の同型性表のとおり) を報告に書く。** **監督の pair-closing commit は両 peer の isomorphism テストを実行して緑を確認してからマージする。** **WP-2 × WP-3 の重なり 0 はこれで保たれる** (設計 v1.3 §8 / §8.1、本書 §4 の 12 / §5)。
3. **【監督裁定 (WP-1 実装中、2026-09-07)】port v1.13 の `alter_field` primitive は独立 primitive として新設せず、汎用 `schema_operation_with_result` (operation 名を引数に取る) に畳む形を採用した。** 設計 §6.1 項目 8 の「新設」は WP-1b の実装がこの汎用形で満たしており、レビュー (WP-1b 指摘 L) が「改善だが設計外」として上げたものを監督が採った。理由と限界は `docs/design/CONFORMANCE_ADAPTER_V1.md` §23 (v1.13) に記す。**本書 §2 WP-1 の対象・完了条件は書き換えない。**
4. **【監督裁定 (WP-1 実装中、2026-09-07)】`CONDITIONS.md` の C-07 行の Status は WP-1 時点の真実 (両 peer は `idempotency: unavailable`、肯定枝は WP-2c / WP-3c で load-bearing になる) を書く。** 設計 §6.4 の「両 peer が `enabled` を宣言する」文への差し替えは、idempotency の pair-closing commit (両 peer フリップ後、監督のコミット、§4 の 12) で行う。**本書 §2 WP-1 の項目 30 の当該文はこの時点差を明示していなかった。**
5. **【監督裁定 (WP-1 実装中、2026-09-07)】`requires_capability` の意味は「その endpoint が提供されるために `unavailable` 以外で宣言されていなければならない capability」(必須前提) に確定し、契約 JSON にトップレベル key `endpoint_fields_note` (roles / requires_capability / atomicity の 3 値) を新設した。** 設計 v1.4 §5 U-8 #30〜#32 に逐語記録 (WP-1a レビュー M-4 / L-6)。**本書 §2 WP-1 の変更一覧にはこの key が無かった。**
6. **【監督裁定 (WP-1 監査後、2026-09-07)】監督確定文 (設計 v1.4 §5 U-8 #30〜#32 の 5 値: `SchemaOperationResult.descriptor.description`、`CapabilityDocument.operation_catalog_url.description`、`endpoint_fields_note` の 3 値) にも `conformance-tests/test_contract.py` の文字列 PIN を置く。** 常設規律 4 (契約側に確定文をそのまま assert する文字列ピン) の適用であり、本書 §2 WP-1 の新 PIN 一覧に無かったのは訂正註 5 の後発確定によるものである。監査の自前変異 (`requires_capability` 文の `must`→`should` が 3 複製同時でも緑) が根拠。
7. **【監督裁定 (WP-1 監査後、2026-09-07)】C-21 / C-25 の `xfail(strict=True)` は、宣言 `contract_version < 1.7.0` の枝では observed_branch の突合を本体に含めない。** 本体 = 語彙 / request_id の assert のみとし、突合は `>= 1.7.0` の枝でのみ行う。監査の変異 (adapter に request_id を注入しても xfail のまま) が、突合を本体に含める形では「宣言より先に挙動が入った peer」が strict XPASS で赤にならないことを実証した (設計 D-1 (7) の主題が機構として働かない)。追補 2 S-c の宣言ベース非 vacuity は、pre-1.7.0 枝では xfail の実観測そのものが非 vacuity である。
8. **【記述訂正 (WP-1 監査後、2026-09-07)】本書 §2 WP-1 変異 3 の期待「`test_c12` の駆動集合 assert が赤」は誤り。** `test_c12` は `capability_status.defined` を読まない。実際に赤くなるのは `test_c11` の既存順方向 assert (宣言名 ⊆ defined) である。禁止事項 6 の「剥離で動かない PIN 8 件」は、retroactive 4 件を「改名」と数えると 9 件になる (数え方の差であり実質は同じ)。
9. **【監督裁定 (WP-2a / WP-3a レビュー後、2026-09-07)】契約 1.7.0 を公開後 (両 peer のフリップ前) に 3 点補正した。** (i) `SchemaOperationRequest.enum` の型を `["array","null"]` とし、`alter_field` で `enum` 省略 = 変更なし・`enum: null` = 解除・`nullable` 省略 = 変更なし、`add_field` の `enum: null` = 省略と同じ (WP-3a レビュー A、設計 v1.5)。(ii) `add_field` で `nullable: false` を宣言する要求は、その entity に行が 1 行でもあれば `CONFLICT` (WP-2a レビュー M-6、設計 v1.6)。(iii) `violated_declaration` 語彙に 11 語目 `constraint_declaration` (宣言不正: 型が許さない field への enum、空・重複 enum、宣言型外の member、要求が作らない field への宣言) を足す (WP-2a レビュー m-1、設計 v1.6)。**いずれも peer が 1.7.0 を宣言する前の補正であり、契約 JSON 3 複製・PIN・設計は同一コミットで更新した。** port v1.13 には `ENUM_CLEAR` sentinel (省略 / null / 配列の三値) を追補した。本書 §2 WP-1 の変更一覧と WP-2a / WP-3a の完了条件にはこれらが無い — 実装は裁定ファイルどおりに行い、監査は裁定ファイルと突合する。
10. **【監督裁定 (2026-09-07)】両 peer で同名にする helper: `validate_enum_declaration(enum_values, declared_type)` と `enum_member_matches_type(value, declared_type)`。** alter_field / add_field の走査は同一 tx 内で `LOCK TABLE ... IN SHARE MODE` (PostgreSQL backend) を取ってから行う。`details.field` は要求内パス。`field_constraints` entry の未知キーは `VALIDATION_FAILED` + `violated_declaration: request_schema`。`drop_entity` の side table 掃除は table 存在時のみ (未適用 application を 503 にしない)。query 経路は制約を読まない (往復数を増やさない)。
11. **【監督追認 (WP-3a 監査後、2026-09-07)】MitateDB の HTTP `add_field` は `field_type` 省略時に `json` を既定とする (従来は VALIDATION_FAILED)。** 契約 `field_types` の説明「A field created without a declared type has type json」と r2db の既存挙動に整合する変更であり、WP-3a の完了条件には無かったが監督が追認した (WP-3a 実装報告 (C-20 leg 11 の HTTP 経路で判明))。**MitateDB に `upsert` は存在しない** (`unsupported: ["upsert"]`) ので、WP-3a 完了条件の「3 経路」は insert / update / transact insert と読む — テスト docstring に開示する。alter_field の CONFLICT の `details.field` は要求が送った制約 key (`enum` / `nullable`) を指す (違反は要求が宣言した制約についてのみ起きるので要求内パスと一致する)。
12. **【監督裁定 (WP-2b 実装報告後、2026-09-07)】port v1.13 の `attempt_mutation_with_result` (と同型の batch primitive) に `destructive` / `confirmation` の keyword 引数 (既定値で従来挙動) を追補する。** C-22 の確認 probe が要求する引数が WP-1 の port に無く、r2db 2 plug の肯定枝が TypeError で実行不能だった (WP-1 側の欠陥)。**本書 §2 WP-2b 変異 3「dry_run でも監査 hook を組み立てる」は、tx の dry_run 早期 return が pre_commit 到達前に起きる二重防御により赤化不能である** — `_event` 呼び出し側の guard を外す変異で代替することを認める (二重防御は望ましい)。監査は「両層のどちらか一方を外しても監査行 0 が保たれ、両方外すと赤」を実測する。
13. **【監督裁定 (WP-2b / WP-3b レビュー後、2026-09-07)】R-4 の実装規律を固定した。** (i) `request_budget` が `unavailable` の間、`budget` を伴う要求は `plan` の有無に関わらず CAPABILITY_UNSUPPORTED (レビュー WP-2b F-1: plan 同伴で gate を素通りする経路が実在した)。(ii) plan の digest は契約レベルの要求 object をそのまま (解決値・既定値補完をせず、request schema の全 key を受け取ったとおりに) 使い、除くのは `plan` / `dry_run` の 2 key のみ。in-process と HTTP で同じ object (レビュー WP-3b: `field_type` を含めない digest で preview と異なる型が確立し得た)。(iii) token 書式は `"<sha256hex>.<schema_revision>"`、helper 名は `normalize_request_for_plan(request) -> bytes` / `compute_plan_token(request, schema_revision) -> str` で両 peer 同一 (pair-closing の対象)。(iv) S-a の正規化 3 規則それぞれを壊す変異が赤になる peer ローカルテストを置く。(v) dry_run 応答は `assigned_addresses` key を持たない。(vi) plan も dry_run も無い要求では digest 計算と revision の追加読みを行わない (P-8)。C-22 の leg 10 は `transaction` key で digest scope を証明し (budget は宣言されているときだけ)、leg 11 は `drop_entity` を提供しない peer では確認つき `delete` で行う (訂正 5)。
14. **【依頼者承認 (2026-09-07)】残りの WP の進め方を短縮する。** (i) 契約の穴が見えた時点で補正をまとめて 1 コミットにする (peer のフリップ前に限る)。(ii) 実装プロンプトに設計 §3 の該当 D と既知の裁定ファイルを最初から全部渡し、差し戻し 1 回目を省く。(iii) WP ごとのレビュー 2 回目は省き、Opus のレビューと監査を 1 回に統合する (速度規律 3)。あわせて、**同じ worktree で直列だった WP-2c と WP-2d (WP-3c と WP-3d) は触る箇所が別なので 1 つの実装 WP (WP-2cd / WP-3cd) にまとめる。** 完了条件と変異は本書 §2 の 2c + 2d (3c + 3d) の合算のまま。R-5 / R-6 の裁定集約は監督の裁定ファイルにあり、実装プロンプトに渡す。
15. **【監督追認 (WP-2cd 実装報告後、2026-09-07)】** (i) port が per-operation で埋め込む `idempotency_key` と契約の request-level `MutationRequest.idempotency_key` の二重表現は、peer の service 層で request-level に畳む (r2db `fold_operation_idempotency_keys`。全 operation が同値か全て無しのみ許容)。(ii) schema 操作の idempotency 照会は bind 直後 (schema_objects 計算の前) に置く — replay で drop 済み entity の projected_objects が負値になり LIMIT_EXCEEDED を誤爆する経路を実測で確認したため。(iii) conformance の budget probe は固定値を使わず、plug の宣言 `limits` から読んで宣言値以下 / 宣言値 + 1 を送る (隔離 profile の小さな配備値と整合させる)。C-23 に満杯 leg (LIMIT_EXCEEDED idempotency_entries、実行前拒否) を足し、隔離 profile に `idempotency_entries=5` / `idempotency_retention_ms=60000` を置く。
16. **【監督裁定 (WP-2cd / WP-3cd 監査後、2026-09-07)】R-5 / R-6 の実装規律を固定した (裁定 J-1〜J-7、K-1〜K-5)。** (i) plan digest に `idempotency_key` が流れることを実経路のテストで固定する。(ii) 非整数 budget の details は declared_type: integer / observed_type を載せる。(iii) `limit_enforcement.idempotency_retention_ms` は両 peer とも `reference_wall_clock`。(iv) idempotency の replay は監査される (outcome `replayed`、replay 要求の request_id、key は載せない) — 破壊操作の再送が成功応答を返しつつ証拠ゼロにならないため (SI-14)。(v) per-application upgrade 未適用の application で key 付き要求は照会段で SERVICE_UNAVAILABLE (実行前)。(vi) budget の妥当性検査は limit gate の後の検証段 (両 peer 同順)。(vii) 記録し replay で返す応答は契約レベルの result object。(viii) 隔離 profile は `idempotency_entries=20` / `idempotency_retention_ms=60000` (5 では C-23 の先行 leg が先に満杯になる)、C-23 の満杯 leg は宣言値 ≤ 200 のときだけ駆動 (それ以上は「駆動せず」開示)。(ix) conformance の宣言値読みは隔離 application 自身の capability document から (配備全体の document は production profile を宣言する — 訂正 8b)。
17. **【監督裁定 (WP-2e 監査後、2026-09-08)】R-3 / R-7 / フリップの実装規律 (裁定 L-1〜L-8)。** (i) `violated_declaration` は request-shape 層と choke point 層の全発行箇所で必須 (免除は `layer_rule` の backend 層のみ)。AST 全数で「details 無しの 3 code が choke point / request-shape 層に 0 件」を assert する peer ローカルテストを置き、backend 層の allowlist は実コードと双方向に一致することまで assert する。(ii) `ops verify-declarations` の 1.7.0 検査 (F-14) は「宣言が真であること」を配備の実体に対して検査する: 4 capability enabled + 3 limit class + 全 application DB の per-application upgrade 適用済み (未適用が 1 つでもあれば非 0)。(iii) IDENTIFIER_INVALID / CAPABILITY_UNSUPPORTED の `field` は要求内パス (batch index 反映)。(iv) request-shape 層は「存在するが型違反」に型対を載せる。(v) SI-10 の走査テストを peer ローカルに置く。(vi) request_id を持たない idempotency 記録 (フリップ前) は無いものとして扱う (フォールバックしない)。(vii) query / schema 端点でも request_id は再生成しない (3 端点で固定)。(viii) `check_contract_170_declarations` / `ops_module_hint` は pair-closing の対象。**WP-3cd の K-2 (記録する応答の形) は MitateDB では peer 内部形を記録し HTTP 境界で契約形に変換する実現を追認した** (契約上の replay の意味は同じ。台帳 L9 に peer 固有の実現差として記録)。
