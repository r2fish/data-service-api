# 作業指示書 — R-30 SI-00 の本番配備姿勢 (1 serving process = 1 Application) の宣言

## 0. 出所と基点

- **v1.0 (2026-10-03)。** 基点はローカル main `1abd5e8` (作業ツリー `.claude/worktrees/r30`、branch `r30`)。台帳 `RM` §8.1 の R-30 (`RM`:456。v1.152 と v1.154 の【追記】を含む)。
- **規模 M** (`OC` §1.13 の 74)。**変更クラス D** (`security/` に触れる。`RM` §9 の 8) + B (env example) + A (runbook)。手順: 実装担当 1 起動 → コードレビュー (Class D、1 起動) → 受け入れ監査 (Class D、1 起動) → 完了ゲート (監督単独)。commit・完了ゲート・`tools/dev/finalize.py`・台帳と `CM` の版上げは監督が行う。
- 決定の出所: `RR` v0.2 §3.5 (`RR`:111-115) の依頼者裁定 (逐語は §1.2)。根拠は `RR` §3.4 (`RR`:109): 安全第一 (T-13 のコード実行 1 件が届く data は 1 Application 分)、`OS` の A-1 (object-capable 実行単位は 1 application) と同じ姿勢、費用ゼロ、コードの自由は残る。
- **略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`RR` = `docs/design/REQUESTER_RULINGS_R30_R118_R120_V0_1.md`、`SI` = `security/SECURITY_INVARIANTS_V1.md`、`CM` = `security/CONTROL_MAPPING.md`、`ENV` = `r2db-api/deploy/env/api.env.example`、`RB` = `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`、`CR` = `MitateDB-api/docs/cloud-run-cloud-sql.md`、`OS` = `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`、`$SP` = 監督が発注時に渡す scratchpad、`$WT` = `.claude/worktrees/r30`。

## 1. 問題設定と確定文

### 1.1 問題と守るべき条件

両 peer の serving set は `R2DB_SERVE_APPS` / `MITATEDB_SERVE_APPS` の全 slug の runtime / developer DSN を 1 process に保持するが、この構成と SI-00 (`SI`:65-87) の関係は `security/` のどこにも書かれていない (`RR` §3.1)。守る条件:

- SI-00 の Statement / Protected assets / Required property / Implementation freedom / Verification requirement は 1 文字も変えない。containment は DB 側の境界 (application ごとの DB・`CONNECT` grant・role 対、SI-01 の要求ごとの DSN 選択) で満たし、`SI`:84 の「topology を定めない」はそのまま。
- それに加えて本番の配備姿勢を宣言する: 1 serving process = 1 Application (runtime / developer DSN は 1 Application 分)。複数 Application の serving set は試験・開発の構成であり、禁止ではないが本番の既定ではない。
- コードは変えない (両 peer の serving set 構築・下限 1・上限検査なしは不変)。起動時検査は入れない (`RR` §3.3 の案 C は採らない。後から足せる)。
- platform DSN の到達範囲はこの姿勢で変わらない (SI-01 の grant が境界)。

### 1.2 確定文 (`$SP/r30-confirmed-text.md` から逐語。言い換えない。`OC` §1.5 の 35・36)

依頼者裁定 2026-10-03 (逐語): 「(ii) 配備姿勢の宣言 (推奨)」
= 裁定資料 docs/design/REQUESTER_RULINGS_R30_R118_R120_V0_1.md v0.2 §3.5 の問い (ii) (案 B): 本番の serving set を 1 process 1 Application に限る配備姿勢を宣言し (複数は試験・開発の構成、コードは変えない)、SI-00 の文書にはその姿勢を本番の既定として記す。
台帳 v1.154 の R-30 行の【追記 2026-10-03 (v1.154)】に同じ逐語がある。

SI-00 に足す註 (SI-00 の「Verification requirement」の段落 (`SI`:86-87) の直後、`---` (`SI`:89) の前。見出し行末の空白 2 字を含めて確定文ファイルの 9〜10 行目と byte 一致):

```markdown
**Deployment posture (ledger R-30, requester ruling 2026-10-03)**  
Containment under this invariant is satisfied at the database boundary -- one database, one `CONNECT` grant and one role pair per Application, with the DSN chosen per request under SI-01 -- and the statement above sets no process topology (Implementation freedom). In addition, the production posture of both implementations is one Application per serving process: a production process holds the runtime and developer DSNs of exactly one Application, and a deployment that serves several Applications runs one process per Application. A process whose serving set names several Applications is a test or development configuration, not a prohibited one, and it is not the production default. This posture is a deployment declaration, not a startup check: no implementation refuses to start on a multi-Application serving set, and the evidence is each implementation's runbook, environment example and deployment record (`security/CONTROL_MAPPING.md`, SI-00). The platform DSN a process holds is outside this posture; its reach across the registry is bounded by its own grants (SI-01).
```

`CM` に足す主張の骨子 (file:line は実装担当が現物から取り、form 3.0 の claim form (`CM`:13-26) に合わせる):

- SI-00 / Common / Control: 本番の配備姿勢 (1 Application per serving process; 複数は試験・開発の構成) の宣言 -- `security/SECURITY_INVARIANTS_V1.md:<SI-00 の註の行>`。
- SI-00 / r2db-api / Control: `R2DB_SERVE_APPS` の env example と runbook がその姿勢を述べる -- `r2db-api/deploy/env/api.env.example:<行>`、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:<行>`。
- SI-00 / MitateDB-api / Control: `MITATEDB_SERVE_APPS` の runbook がその姿勢を述べる -- `MitateDB-api/docs/cloud-run-cloud-sql.md:<行>`。
- SI-00 / r2db-api / Evidence: 配備記録は 1 slug (`sandbox`) -- `docs/work-orders/DEPLOY_PHASE6_20260904.md:1554`。
- SI-00 / MitateDB-api / Evidence: runbook の配備コマンドは 1 slug -- `MitateDB-api/docs/cloud-run-cloud-sql.md:1251`。
- SI-00 / Common / Status: 起動時検査は無い (裁定資料 §3.3 の案 C は採らず、後から足せる); 実配備の Application 数は本変更セットで再読していない (記録上は各 1); 複数 Application の serving set を組む試験 fixture は `SERVE_APPS` のカンマ区切りの grep では無い (他の経路は未確認); platform DSN の到達範囲はこの姿勢で変わらない; R-36 の router は application-facing 実装ではなく前段と同格の基盤部品で、この姿勢と両立する (`docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md` v0.5 §11 Q-2 (ii)・Q-7)。

### 1.3 却下した代替案 (`RR` §3.3〜§3.4 から逐語)

- **A 境界の文書確定** (`RR`:102、:109): 「SI-00 の "single application-facing implementation defect" を論理欠陥に限る読みを文書で固定する = invariant の弱め方を明文化する。T-13 の 1 件で served 全 Application の DSN が同時に漏れる構成を正式に許す」「A は invariant の弱め方を明文化する決定であり、安全第一の軸に反する。」
- **C 強制 (B + 起動時検査)** (`RR`:109): 「C は B より強いが、両 peer のコードと test・変異の費用がかかり env example と試験構成に手が入る。強制の必要性は、未確認の実配備数を配備記録で確かめてから決められる (後から足せる)。」
- **D 何もしない** (`RR`:105): 「**却下。** `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` の U-13 が「版付きの security-contract 決定」として送った件が未決のまま残る」

### 1.4 依頼者判断待ちと未確認事項

- 依頼者判断待ちの選択肢: 無し (裁定済み)。
- 未確認事項 (`RR` §5、`RR`:174。`CM` SI-00 / Common / Status の開示に写す): 実配備の Application 数 (文書上は各 1)、複数 Application の serving set を組む試験 fixture の有無 (`SERVE_APPS` のカンマ区切りの grep 以外の経路)。

## 2. Change Set Manifest

### 2.1 触ってよいファイル

| # | ファイル | 変更 |
|---|---|---|
| (1) | `SI` | §1.2 の註を SI-00 の Verification requirement の段落の直後に追加する。他の行は不変 |
| (2) | `CM` | SI-00 節 (`CM`:78-204) に追加のみ: Common / Control の `- —` (`CM`:190) を配備姿勢の主張に置き換え、r2db-api / Control と MitateDB-api / Control に runbook・env example の主張、両 peer の Evidence に配備記録の主張、Common / Status に §1.2 の骨子の開示を置く (1 bullet に開示 1 つ)。既存の claim を書き換えないので `security/CONTROL_MAPPING_HISTORY.md` は動かさない。版数行 (3.16 → 3.17。先に 3.17 が使われていれば次の番号) は監督 |
| (3) | `ENV` | `ENV`:59-60 のコメント「a real deployment may serve one slug or many」を、本番の姿勢 (1 slug per process。SI-00 の註、台帳 `RM` R-30) と、複数 slug は試験・開発の構成であることを述べる文に直す。値 `R2DB_SERVE_APPS=alpha,beta` と DSN の例は不変 |
| (4) | `RB`、`CR` | serving set を述べる箇所に本番の姿勢の 1 文ずつ (SI-00 の註を指す)。現物の候補: `RB`:308-315 (起動失敗の段)・`RB`:498-499、`CR` §6.1 の配備コマンド (`CR`:1240-1253) の直後の段・`CR`:2418。位置は実装担当が選び、報告に書く |
| (5) | `OS` | `OS`:28 の註の直後に「【註 2026-10-03】R-30 は (ii) 配備姿勢の宣言で裁定された (台帳 v1.154)。A-1 と同じ姿勢」の 1 行を足す。「既存の複数 application を一 process で serve する配備」を前提とする文が `OS`:700 (§9 実施順序の 1) に在るので、その直後に R-30 の裁定を指す訂正註を足す (旧文は残す。`OC` §1.8 の 56) |
| — | 本書 | §3 は監督が書く |

触らない: 両 peer のコード・tests・src のコメント (`CM` の行参照のため)、`spec/`、`conformance-tests/`、`security/THREAT_MODEL_V1.md`、`security/CONTROL_MAPPING_HISTORY.md`、`RM`、`CM` の版数行。

### 2.2 実装担当への注意

1. 確定文は `$SP/r30-confirmed-text.md` から複製する (§1.2 は写し。照合の正本は同ファイル)。
2. `CM` の主張: Control は主語 (6 語以内) + 何を縛るかの 1 文 + 位置 (`path` / `path:line`)、Evidence は観察 + test 名か `file:line`、Status は開示した限界 (`CM`:13-26)。1 主張 1 物理行、上限 250 / 300 / 300 字 (`MAX_CLAIM_LENGTH`)。新しい named block は足さない (`CM`:57-58)。`SI` の行番号は (1) の追加後の現物から取る。
3. 行参照の追随: `CM` は `RB` に 6 件 (`RB`:889〜:992)、`CR` に 15 件 (`CR`:1141〜:4349) の `path:line` を持つ。(4) で挿入点より後ろに行が増えるとこれらがずれ、R-88 の検査は位置の内容を見ないので赤にならない (`conformance-tests/test_control_mapping_register.py` docstring の Known gaps 1、:69-73)。行数を増やさずに足すか、ずれた参照を追随させる (form 3.0 では参照の更新は履歴へ移さない。`CM`:42-44)。前後の `grep -o '<path>:[0-9-]*' security/CONTROL_MAPPING.md` の出力を報告に逐語で残す。
4. `r2db-api/tests/test_deploy_systemd_workers_static.py` は `ENV` の `R2DB_SERVE_APPS` を読まない。読むのはコメント以外の代入行のうち `R2DB_WORKERS` (`ENV`:107) と `R2DB_SLOT_DIR` (`ENV`:117) だけ (同 test :69-78、:148-154)。M2 の `old` は実装担当がこの 2 行から選び、報告に書く。
5. 公開規律 (`OC` §1.9): 合成値のみ。`docs/work-orders/DEPLOY_PHASE6_20260904.md` の伏字を展開しない。

### 2.3 道具の引数

- `tools/dev/pt.py -C $WT -- conformance-tests/test_control_mapping_register.py -q`
- `tools/dev/pt.py -C $WT -- r2db-api/tests/test_deploy_systemd_workers_static.py -q`
- `tools/dev/mutate.py "$SP/r30-mutations.json" -C $WT` — M1 と M2 は別の entry (各 1 test、`"expect": "red"`)。
- `$WT` で `python3 tools/check_doc_refs.py`、`python3 tools/public_value_scan.py <触った全パス>`、`python3 tools/change_class.py <触った全パス>`。
- 完了ゲート (監督): `tools/dev/gate.py -C $WT --label r30`。

### 2.4 完了条件と照合 (完了条件番号 → 変異の対応表。`OC` §1.5 の 40)

変異を持たない行の照合対象の逐語記録 (コマンドと出力、または file:line) は監督が §3 に残す。

| # | 完了条件 | 照合 | 変異 / 記録 |
|---|---|---|---|
| CC-1 | SI-00 の註が `$SP/r30-confirmed-text.md` の 9〜10 行目と byte 一致で在り、SI-00 の他の段落は不変 | 監査照合 (diff) | `git diff 1abd5e8 -- security/SECURITY_INVARIANTS_V1.md` の削除行 0、追加行と確定文ファイルの比較 |
| CC-2 | `CM` の新しい主張の file:line が R-88 の検査で解決し、`conformance-tests/test_control_mapping_register.py` が緑 | 道具 (pt) | M1: Common / Control の新しい主張の path を存在しないファイル名に変える → 同 test が赤 (expect red) |
| CC-3 | `CM` の版数行が 3.17 (または次の番号) で、SI-00 節の変更は追加と `CM`:190 の `- —` の置換 (と §2.2 の 3 の参照の追随) だけ。既存の claim の文字は不変 | 監査照合 (diff) | `git diff 1abd5e8 -- security/CONTROL_MAPPING.md` の削除行の逐語 |
| CC-4 | `ENV`・`RB`・`CR`・`OS` の文が §2.1 のとおりで、`r2db-api/tests/test_deploy_systemd_workers_static.py` が緑 | 道具 (pt) | M2: `ENV` の §2.2 の 4 で選んだ代入行を削る → 同 test が赤 (expect red) |
| CC-5 | `tools/check_doc_refs.py`・`tools/public_value_scan.py` が緑、`tools/change_class.py` → D | 道具 | 3 つの出力の逐語 |
| CC-6 | コードレビュー (Class D、1 起動) の指摘が残っていない | レビュー | 指摘と処置 |
| CC-7 | 受け入れ監査 (Class D、1 起動) が充足 | 監査 | 監査の判定 |
| CC-8 | 完了ゲート (監督単独) PASS、root 集計行が直前の main と同数 (テストを足さない) | 道具 (gate) | 集計行と judge 行の逐語 |
| CC-9 | 本表に照合の無い行が無い | 監査照合 | 本表 |

## 3. 実施記録 (監督が書く)

### 3.1 訂正註と監督裁定

- **【訂正註 1 (2026-10-03、起草の報告への監督裁定)】** (a) CC-3 の `tools/check_control_mapping_split.py` は R-103 で削除済みで form 3.0 に block 長の実測は無い (`CM`:24-26) ので、CC-3 は §2.4 の表のとおり diff の監査照合とする (承認)。(b) M2 は `R2DB_WORKERS` (`ENV`:107) の代入行を削る変異とする。コメント文 (3) の正しさは CC-4 の監査照合 (diff と §2.1 (3) の文言) とレビューで見る。(c) `RB`・`CR` への追加は**行数を増やさない** (既存の段落の末尾の行に文を足す。コードブロックの中には足さない) — `CM` の `RB` 6 件・`CR` 15 件の行参照を動かさないため。追随は行わない。(d) `CR`:1252-1253 のコメント ("plus one --set-secrets pair per onboarded application's own ...") は姿勢と食い違うので (4) の範囲に含め、**2 行のまま**「served application は 1 つ (SI-00 の Deployment posture); 別の application は別の service として配備する」の趣旨に直す。旧文は本書 §3.2 に逐語で残す (runbook は Class A。`OC` §1.8 の 56 の精神)。(e) `OS`:700 の訂正註の本文は次のとおり (逐語): 「【訂正註 2026-10-03 (R-30)】R-30 は (ii) 配備姿勢の宣言で裁定された (台帳 v1.154、`security/SECURITY_INVARIANTS_V1.md` SI-00 の Deployment posture)。本番の既定は JSON 経路でも 1 serving process = 1 Application であり、本項の「既存の複数 application を一 process で serve する配備」は試験・開発の構成を指すものとして読む。」 `OS`:29・:740・:750 の「未着手・依頼者裁定待ち」は当時の記録として残し、訂正しない (観察)。(f) `SI` の行番号のずれ (:87 より後) は設計文書側の記録として扱い、追随しない (承認)。

- **【訂正註 2 (2026-10-03、コードレビュー 1 (Class D、1 起動、指摘 6 件) への監督裁定)】** 指摘 1 (posture B では共有 OS user の pg_ident map が別 Application の role に届き、姿勢が T-13 を 1 Application に限らない) → 直す: SI-00 の註に「authority は process の OS identity から来る場合も 1 Application の role だけに map する」の 1 文を足す (確定文ファイル v2)、`RB`:315 に posture B の運用 (Application ごとの process は別の OS user、その map 行はその Application の 2 role と `r2dbsvc_api` だけ) を同じ行に足す、`CR`:1253 を「its own runtime service account, which can read only that application's DSN pair」の趣旨に、`CM` r2db Status に共有 OS user では姿勢が T-13 を限らない開示を 1 行。指摘 3 (1 つの data base URL の背後で JSON 要求を Application ごとの process へ届ける部品は無く、`spec`:1410 の surfaces 規則により複数 Application の本番は今日は別 deployment) → 直す: SI-00 の註に「no component today routes … several Applications in production are today several deployments, each with its own surfaces」の 1 文 (確定文 v2)、`RB`:315 と `CR`:1253 を「another application is a separate deployment (its own data and control services)」の趣旨に、`CM` Common/Status に同じ開示 (`spec/data-service-api.v1.json:1410`、R-36 の router が候補) を 1 行。指摘 2 (`CM`:211 の「試験 fixture は無い」は偽: `r2db-api/tests/test_application_audit.py:2958・:3026・:3069`、`MitateDB-api/tests/test_main.py:287` が 2 slug の serving set を組む) → 直す: `CM`:211 を「tests compose a two-Application serving set as a test configuration」の主張に書き換え 4 箇所を引く (枠 §1.2・§1.4 の骨子は誤りであり、本訂正註が上書きする。裁定資料 §5・§3.1 の同じ記述は記録として残し、引き継ぎ書に書く)。指摘 4 (註の第 1 文は問い (i) の前半と同じ) → 観察: 案 B の文面 (`RR`:103) が同じ文を含み、依頼者は案 B を選んだので裁定済み。変更なし。指摘 5 → 直す: `CM` MitateDB Evidence に `docs/work-orders/DEPLOY_PHASE6_20260904.md:528` (`MITATEDB_SERVE_APPS=mitate`) を引く主張を足す。指摘 6 → 直す: `CM`:161 の主語を 6 語以内に、`CM`:206 の「no test is named …」を C-14/C-09 の lateral path に限る文に。レビュー担当の観察 (`WORK_ORDER_R101_…`:599 の `ENV:107` のずれ) は記録として触らない (観察)。修正後の再確認は担当観点を指定しない 1 起動 (`OC` §1.7 の 50a)。

- **【訂正註 3 (2026-10-03、再確認 (1 起動) への監督裁定)】** 前回の指摘 2・3・5 は閉じた、1・6 は一部。新 1 (`RB`:315 が「OS user を分ける」規則を今日は実現できない側 (1 deployment 内の複数 process) にだけ掛け、実現できる側 (別 deployment) に掛けていない) → 直す: `RB`:315 の 2 句を 1 つにまとめ「today (no router; ledger R-36) another application is a separate deployment with its own OS user, unit and pg_ident rows naming only its own 2 roles (and `r2dbsvc_api`); several processes in one deployment await R-36's router」の趣旨に、`ENV`:59-62 も同じ趣旨に (行数不変)。新 2 (`CR`:1252 が縛る向きが逆: 「pair を読める主体」ではなく「service account が読める範囲」) → 直す: 「the runtime service account of each deployment reads only that application's DSN pair; a second deployment uses its own service account」の趣旨に、`CM`:162 を合わせる。新 3 (`CM`:208 が同 block の Evidence `CM`:200・:202 と矛盾) → 直す (文言は監督): 「no test is named here for the cross-Application lateral path on the data surface; the per-peer negatives are each peer's own Evidence」。新 4 (control unit も `User=r2dbsvc` で app の role に peer 認証で届く) → 観察 (起票しない): control process が application の DB に届くのは control plane の provisioning の設計上の到達であり、SI-00 が縛る向き (application → 他 application / control) ではない; `RB` §7 の既存判断の範囲。引き継ぎ書に残す。新 5 (`SI`:90「one Application's roles alone」と `RB` の「(and r2dbsvc_api)」、`CM`:135「does not limit T-13」と `SI`:90「bounds authority」の食い違い) → 直す: `CM`:135 に「… unless the OS user is also per Application (the posture's own precondition)」の趣旨を足す (1 行のまま); `SI` の註は platform DSN の除外文で整合するので変えない。修正の確認は監督が diff で行う (再確認 2 回目は起動しない)。

### 3.2 実施と受け入れ

- **差分**: `security/SECURITY_INVARIANTS_V1.md` (SI-00 に註 2 行、削除 0。確定文 v3 = v2 + 監査の観察 (1) の「environment example (where one exists)」)、`security/CONTROL_MAPPING.md` (SI-00 に claim 11 件、`- —` 1 件と Common/Status の 1 claim を書き換え (旧行は `CONTROL_MAPPING_HISTORY.md` `## SI-00` 末尾へ逐語。設計疑義への監督裁定: 開示済みの限界の変更として移す)、版数行 3.16 → 3.17)、`r2db-api/deploy/env/api.env.example` (コメント 4 行)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`:315、`MitateDB-api/docs/cloud-run-cloud-sql.md`:1252-1253、`docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md`:29・:703、本書。コードは不変。`tools/change_class.py` → class=D。
- **照合**: CC-1 — `git diff 6ba25ba -- security/SECURITY_INVARIANTS_V1.md` 削除 0、追加 2 行は確定文 v3 の 9〜10 行目と `cmp` で byte 一致 (監査担当が v2 で確認、v3 の 1 句の差は監督が確認)。CC-3 — `git diff 6ba25ba -- security/CONTROL_MAPPING.md` の削除行は :190 の `- —` と旧 :202 の Status 行 (訂正註 2 の指摘 6・訂正註 3 の新 3 で裁定済み、HISTORY へ逐語) の 2 行、版数行 3.17。CC-2 — 変異 M1 赤 (`1 failed, 38 passed`)、CC-4 — M2 赤 (`1 failed, 3 passed`)、`pt: 65 passed`。CC-5 — `check_doc_refs OK: 0 dangling references`、`public_value_scan` 7 ファイル flagged 0、class=D。CC-6 — コードレビュー 1 (6 件: 直した 5、観察 1) と再確認 (新 1〜3・5 を直した、新 4 は観察)。CC-7 — 受け入れ監査パケット (監督の scratchpad `audit-r30-packet.md`): CC-1・2・4・5・6・8 充足、CC-3・9 は監督の閉止作業 (本節と版数行) で充足、証拠不足 3 件 (gate の log= は監督が保持、M1 の対象行は訂正註 3 以後不変、件数は pt の log 65 passed)。CC-8 — 完了ゲート (監督単独、`--label r30`): `gate: 5026 passed, 2 subtests passed in 470.64s (0:07:50)`、`judge=PASS`、`pg_database/pg_roles diff 0`、直前の main と同数。性能差分: コード不変のため対象外。CC-9 — 本表に照合の無い行なし。
- **観察 (起票しない)**: ENV の `alpha,beta` は本番の雛形として写される (`docs/work-orders/DEPLOY_PHASE6_20260904.md:1552`) が、コメントが試験・開発の構成と明記する; MitateDB の姿勢の文は runbook のコードブロック内のコメントにしか無い (env example 自体が無い); control unit も `User=r2dbsvc` (再確認の新 4); `CM`:208 の見出しは監査の観察 (2) で data-surface に直した; 本書 §1.2 のコードブロックは確定文 v1 のまま (正本は確定文ファイル v3 と `SI`:89-90。R-14 により書き換えない)。
- **依頼者の事後確認待ち**: SI-00 の註の英文 (監督が裁定 (ii) から組み、レビュー・監査で 3 文を補った)。
- **最終判定**: 受け入れ。台帳 R-30 を閉じる (v1.158)。
