# 引き継ぎ — 2026-09-03 (第10次。フェーズ4 完了時点)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/受け入れ監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: 過去引き継ぎの約束事 (`HANDOVER_20260829_FABLE.md` §3/§4/§5、FABLE3 §4、FABLE4 §4、`HANDOVER_20260830_FABLE.md` §4、`HANDOVER_20260831_FABLE.md` §4、`HANDOVER_20260901_FABLE.md` §3-4/§4) は**全て継続**。現在地のみ本書が上書きする

## 1. 現在地 (main)

**フェーズ4 (application-plane 耐久 audit sink + `audit_query` + 契約 1.4.0、`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` v1.5) は WP-0〜WP-4 まで全 WP 完了し、全て main マージ済み・push 済み。** 依頼者裁定 P4-D1〜P4-D5 (2026-09-02、直接回答) に基づく。

| コミット (merge) | WP | 内容 | root suite (単独実行) |
|---|---|---|---|
| `fcb2c4b` | WP-0 | 設計 v1.4 + 作業指示書 v1.2 (依頼者裁定 5 件を確定形へ反映) | 1292 / 0 / 0 (基準値確認) |
| `1ef89c0` | WP-1 | **契約 1.4.0 公開** (従属判断 9 = 8 項目の一括束) + C-09/C-11 executable 化 + port v1.8。**以後の契約変更は 1.5.0** | **1331** passed / 0 / 0 / xfailed 1 |
| `5e9d6ed` | WP-2(a) | r2db 耐久 sink (migration 0007、pre-commit hook、合体 denial、bounded buffer + alert)。宣言不変 | **1370** / 0 / 0 / xfailed 1 |
| `ea4b8b5` | WP-2(b) | r2db `audit_query` (control ホスト 2 パス・reader role・不透明 cursor・専用 rate 窓) + **1.4.0 flip** | **1419** / 0 / 0 / xfailed 1 |
| `b651324` | WP-3(a) | MitateDB 耐久 sink (migration 0005、13 列 emitter、P4-D5 の emit サイト新設、`request_id` 縦断)。宣言不変 | **1485** / 0 / 0 / xfailed 1 |
| `c77fa56` | follow-up 1 | r2db flush の swap-out 化 + 失敗復元時の容量切り詰め (`a2a88e5`。MitateDB レビュー発見の対称適用) | **1487** / 0 / 0 / xfailed 1 |
| `54b6bf3` | WP-3(b) | MitateDB `audit_query` + **1.4.0 flip** + 全体 vacuity guard の `xfail` 削除 (`009ca42`)。**r2db テスト補強 follow-up 2 (`8473011`) を同一 merge に含む** | **1526** passed / 0 failed / 0 skipped / **xfailed 0** |
| `4dc4868` | WP-4 | 記録整理 (設計 v1.5 §5.1/§9.4/§11.1、作業指示書 §9、CONTROL_MAPPING、CONDITIONS、両 peer runbook・配備文書、CCR_DISPOSITION) | 文書のみ |

**最終実測 (単独実行、2026-09-03): root suite 1526 passed / 0 failed / 0 skipped / 0 xfailed** (フェーズ開始時 1292 から +234)。**conformance 404** (4 adapter、C-09/C-11 が全 adapter で PROVIDED 分岐)。xfailed は WP-1 で登録した全体 vacuity guard 1 本であり、最後の flip コミット `009ca42` が `xfail(strict=True)` を外して 0 に戻した (作業指示書 §4 の想定どおり)。skipped は全 WP で 0 — 未接続 PostgreSQL による skip は 1 件も無い。

正本の所在:

- **依頼者裁定 P4-D1〜P4-D5** (置き場所 / N-1 の記録方式 / denial 合体 / 契約 1.4.0 一括 8 件 / 通常成功 event の両 peer 記録) = 設計 **§5**。各項に「却下した側とその理由」があり、再検討はそこが出発点
- **監督裁定 P4-D6〜P4-D14** (WP 実施中に確定。合体 2 行 / 包含列挙 / `count` の NULL 規則 / flush 失敗も alert / `audit_events` の実装義務 / キー単位 lock / swap-out + 切り詰め / フィルタ非依存 cursor / `peek()` の adapter 限定) = 設計 **§5.1**。番号は WP-4 で新規に振ったもので、当時のレビュー記号を併記してある
- **各 WP の実装記録・レビュー裁定・変異注入・受理境界** = 設計 **§9.4** (9.4.1〜9.4.7)。11 性質 × 実在テスト名の対応表は **§9.2.1** が最終形 (作業指示書 §5 の表は発注時点の予定名を含み、一部食い違う)
- **将来課題台帳** = 設計 **§11 / §11.1** (WP-4 起票の L4-1〜L4-9)
- **発注の記録** (完了日・分割・follow-up の経緯・成果物 6 項の充足) = 作業指示書 **§9**

## 2. 到達した安全状態の要約 (両 peer)

- **`application_audit`**: platform DB の registry schema に 13 契約フィールド + `count` + `recorded_at DEFAULT clock_timestamp()` + `audit_seq`、全 text 列に長さ CHECK。書き手 (`r2dbsvc_api` / `mitatedbsvc_api`) は **INSERT のみ** — append-only は DB 権限で担保され、アプリコードの規律に依存しない
- **fail-closed by construction**: destructive/schema/lifecycle/security-control-failure と耐久対象 denial は**データ commit 前**に耐久 INSERT + commit し、失敗すれば `SERVICE_UNAVAILABLE` でデータ側に痕跡を残さない。commit がプロセス生存下で失敗すれば同一 `request_id` の `outcome="error"` 行を書く
- **包含列挙 denial の合体**: 耐久対象は設計 D-3 表の 6 項目のみ (P4-D7)、合体キー単位で窓 W=60s、**1 プロセス・1 窓・1 キーあたり最大 2 行** (初回同期行 + 窓末集約行、P4-D6)。未認証の client 申告 `credential_id` は行にも合体キーにも入らない (WP-3(a) B-1)
- **buffer + alert の律速**: 通常 data-operation 成功のみ bounded buffer (既定 1000)。overflow / flush 失敗はいずれも `dropped` に計上し、`security_control_failure` 行 + 固定メッセージ `logging.error`。alert 行自体の emit は **flush 間隔あたり最大 1 行**。flush は swap-out、失敗復元では容量まで切り詰め、切り詰め分も `dropped` に載る (P4-D12)
- **`audit_query` の両パス**: control ホストで `POST /control/v1/audit/query` と `POST /v1/audit/query` alias が同一ハンドラ。reader role (`r2dbsvc_auditreader` / `mitatedbsvc_auditreader`、SELECT のみ) が `control_audit` UNION `application_audit` を読む。全順序 `(recorded_at, plane, event_id)`、**不透明・フィルタ非依存の keyset cursor** (P4-D13)、`plane` は行の出所テーブルからの導出値で書き手は指定できない。専用 pre-auth 窓 `audit_requests_per_minute` (control 窓を消費しない)
- **契約 1.4.0 宣言**: 両 peer・両 plane。宣言キーは `status` / `authority` / `event_classes` / `default_limit` / `max_limit` / `visibility_lag_ms` / `coalescing_window_ms` / `completeness_note` / `outcome_note` / `count_note` / `cursor_note`。`event_classes` は AST 走査でパッケージ全体の実 emit 語彙と突合されている
- **共通 suite**: 登録済み **4 adapter すべて**が C-09 (4 ベクタ + 宣言整合 3 本) と C-11 (`AuditResult` 逆検証 + `AuditQueryRequest` 閉鎖) の **PROVIDED 分岐**を実行する。C-11 の zero-coverage は解消

### 運用前提 (配備前に必ず読むこと)

1. **`visibility_lag_ms` の 2 プロセス整合は機構的に強制されていない** — lag は control プロセスの env (`*_AUDIT_STATEMENT_TIMEOUT_MS` / `*_AUDIT_IDLE_TIMEOUT_MS`、既定 5000ms/5000ms) から導出されるが、`application_audit` の書き手は別プロセスで同名 env を独立に読む。両プロセスが同じ env 名・同じ既定を読む構造で運用上は一致するが、宣言側の検証は無い (設計 §11、WP-2(b) 受理境界 (ii)、両 peer runbook に前提として記載済み)。同型の未強制が `coalescing_window_ms` にもある — `DataService(denial_coalesce_window_s=...)` の配備上書きは宣言に反映されない
2. **容量算式には最大インスタンス数 M を織り込む** — 合体も buffer もプロセスローカルなので、配備全体の実効上限は `2 × 窓数 × M` (denial) および `buffer 容量 × M` (未 flush event)。算式は `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §15.1 と `MitateDB-api/docs/cloud-run-cloud-sql.md` §3.2d に記載済み
3. **`audit_requests_per_minute` は既定 60 で両 peer 同一だが、上限の扱いが peer 非対称である** — MitateDB は `ControlPlaneLimits.__post_init__` が `[1, 200]` を強制する (`MitateDB-api/src/mitatedb_api/control_plane.py:148-152`) 一方、r2db は `value <= 0` のみ検査で**上限が無い** (`r2db-api/src/r2db_api/limits.py:140-143`。テストは 100_000 を構築し、env `R2DB_CONTROL_LIMIT_AUDIT_REQUESTS_PER_MINUTE` で変更可)。既定 60 は「宣言 `visibility_lag_ms` 以上の間隔でポーリングする」前提で監査エージェント約 10 体分。エージェント増や障害復旧後の cursor 追い付き (ページングであってポーリングではない) では、**MitateDB 側でのみ**既定より先にレンジ上限 200 が効く。**MitateDB の上限引き上げは設定変更ではなく設計変更**である (台帳 L4-4)。この非対称は台帳 **L4-7 の 3 件目**として WP-4 で記録した
4. **reader DSN 未設定なら `audit_query` は `unavailable` 宣言のまま** — `R2DB_AUDIT_DSN` / `MITATEDB_AUDIT_DSN` が無ければ宣言は `{"status": "unavailable"}` に据え置かれ、ルートは登録されたまま認証後に `CAPABILITY_UNSUPPORTED` を返す (素の 404 にはしない)。**この状態でも契約 1.4.0 宣言は完全に適合である** — 1.4.0 の条件付き義務は `audit_query` が `unavailable` 以外を宣言する場合にのみ拘束する (`versioning.version_binding`)。無条件義務 (a)(b)(c) は宣言だけで拘束するので、DSN 未設定でも満たさねばならない

## 3. クライアント連携状態

**フェーズ4 の一報は送らない (依頼者判断 2026-09-03)。** mitate-30 / mitate-cd は既に終了しており、依頼者が「送らなくて良い」と裁定した。以下は、将来クライアント側が 1.4.0 を取り込む際に伝えるべき事項の記録である (フェーズ3.5 の最終一報は 2026-09-01 セッションで送信済み)。

一報すべき事項:

- **契約 1.4.0 公開** (従属判断 9、`spec/CCR_DISPOSITION.md`)。8 項目 = (1) `after` は不透明 cursor (decode 不能/未解決は `VALIDATION_FAILED`) / (2) 全順序 `(recorded_at, plane, event_id)` / (3) 各 event の `plane` フィールド / (4) `event_class` は実装が宣言する語彙 (契約 enum ではない) / (5) audit role の `audit_query` 許可と `control_plane.authority` の文言整合 / (6) `audit_events` 予約名の文書化 / (7) `audit_query` の正典分類を `control_endpoints` (`POST /control/v1/audit/query`) へ、`/v1/audit/query` は alias / (8) `audit_requests_per_minute` limit class の新設
- **`audit_query` は control ホストにある** — data-plane ホストの `/v1/audit/query` は application credential を認証した後に `CAPABILITY_UNSUPPORTED` を返す既存スタブのままであり、変わっていない。監査を取るなら control ホストへ
- **`/v1/audit/query` alias の寿命は 1 minor** — 正典は `/control/v1/audit/query`。新規実装はこちらを使うこと
- **`audit_events` は予約名** — 文書化に留まらず、契約 1.4.0 の**無条件義務 (a)** として `create_entity` だけでなく entity 識別子を受け取るあらゆる位置で予約が効く (P4-D10)
- **`audit_query` 消費者向けの宣言キー**を必ず読むこと。とくに:
  - `completeness_note` — `len(events) < limit` は終端を意味しない。`visibility_lag_ms` 内の行はまだ返らないので、**空ページが返るまで最後の event の `cursor` でポーリングし続ける**
  - `cursor_note` — cursor はフィルタ非依存の keyset である (P4-D13。起草時の「同一フィルタ条件下でのみ有効」より強い性質を出荷した)
  - `count_note` — `count` は「この 1 行が代表する発生回数」で、0 と 1 は決して現れない (合体集約行と overflow alert 行のみが持ち、他は NULL)
  - `outcome_note` — `outcome="allow"` は「認可され実行に投入された」であって commit 成功を主張しない。同一 `request_id` の `outcome="error"` 行があれば commit していない。**`allow` 単独行は「成立した」か「記録後にプロセスが消失した」かのいずれかで、監査面だけからは区別できない**

## 4. 次の一手 (優先順)

1. **配備実機への適用** (フェーズ4 の成果は実配備にまだ乗っていない)
   - migration の適用: r2db = `0007_application_audit.sql` (VPS)、MitateDB = `0005_application_audit.sql` (Cloud SQL。ヘッダに逐条の互換性論証あり)。適用順・実行 role・環境変数名は両 peer の runbook
   - **reader role の DSN 配線** (`R2DB_AUDIT_DSN` / `MITATEDB_AUDIT_DSN`)。配線するまで `audit_query` は `unavailable` 宣言のまま (§2 運用前提 4)
   - **logs-based alert の設定** — 固定メッセージ 5 種を運用側の alert に結線する。「回復は 3 番目の固定メッセージで読む」(台帳 L4-3 の貼り付き対策)
   - **platform DB の容量閾値** — §2 運用前提 2 の算式 (`2 × 窓数 × M` / `buffer 容量 × M`) と 1 行サイズ上限から閾値を置く
   - 監査書込み接続の `statement_timeout` / `idle_in_transaction_session_timeout` を配備値で確定し、**変えたら宣言 `visibility_lag_ms` も変わる**ことを運用手順に落とす
2. **クライアントへの 1.4.0 一報** (§3 の 8 項目 + 4 つの `*_note`)
3. **台帳消化** (設計 §11.1 の L4-1〜L4-9 + 継承分)。契約 1.5.0 候補が溜まったら**一括判断の前例 (従属判断 8 → 9)** を踏襲する
   - **L4-1 `operation` / `target_kind` の語彙宣言化 (1.5.0 候補)** — 共通 C-09 vector 1 が候補集合を手で列挙しており、宣言と機械的に結ばれていない。`event_class` と同じ扱いを与えれば C-17 系で固定できるが契約変更を要する
   - **L4-2 data ホストの alias パスに対する契約無条件義務 (b) の解釈** — 現在は「control surface の `audit_query` control endpoint に掛かる」読みで両 peer とも受理。文言を締めるかテストを足すかは次回の契約見直し
   - **L4-3 `failing` フラグの貼り付き** — 解除が「buffer が空になったとき」限定のため、継続負荷下で sink 回復後もフラグが立ち alert 間隔が最大 60s まで開く。証拠は `count` に保全される
   - **L4-4 `audit_requests_per_minute` の既定 60 (両 peer) と上限の peer 非対称** — MitateDB は `[1, 200]` を強制、r2db は下限 (正の整数) のみで上限なし。MitateDB 側の上限引き上げは設定変更ではなく設計変更
   - **L4-5 宣言語彙 AST 走査のファイル列挙漏れを機械検出できない** (両 peer 同型)。閉じるなら両 peer 同時が筋
   - **L4-6 HTTP conformance adapter の書き手 timeout 設定漏れを検出する共通テストが無い**
   - **L4-7 両 peer 間に残る非対称 3 件** — (i) AUDIT DSN 未設定時の `unavailable` 宣言を固定する composition root テストが MitateDB に無い、(ii) `..._does_not_import_the_control_credential_store` の同名対応物が MitateDB に無い、(iii) **`audit_requests_per_minute` の上限検査が MitateDB のみ `[1, 200]`、r2db は上限なし** (WP-4 起票)
   - **L4-8 C-09 vector 4 の射程** — port ABC の構造検査であり adapter ごとに分岐しない。作り直すか射程を明示するかは未決
   - **L4-9 vector 1 の新規 event 同定キーが `event_id` 単独** — 本フェーズの契約自身が UNION での一意性を否定しているので、`(plane, event_id)` か `cursor` が整合する
   - 設計 §11 の記録のみ項目: `audit_query` の application credential probe オラクル (失効済みは FORBIDDEN でなく AUTH_INVALID)、in-memory / Postgres 読み手の collation 依存、`CredentialStore.peek()` という非監査の認証面 (P4-D14 で adapter 限定を AST 走査で強制済み)
4. **運用規律の継続**
   - **完了ゲートの実測は suite を単独実行する** — 本フェーズは全 WP で守り、フェーズ3.5 で 2 回起きた PG クラスタ並走衝突による偽の赤は 1 度も発生しなかった
   - **push 前に `git log --format='%an <%ae>'` で r2fish noreply のみを確認する**
   - **コミットは push とセット、さらに main へマージまでを 1 単位とする**
   - **変異注入の復元は scratchpad 経由**。`git checkout` は使わない

## 5. 教訓の追加 (前書全項継承に追加)

- **対称実装の発注書に前 WP の欠陥一覧を織り込むと、対称側のレビューは「テスト側の空振り」へ収束する**: WP-3(b) の 4 major は**全てテストの空振り**だった (順序・cursor の `plane` を固定しているはずのテストが実際には固定していない / `visibility_lag_ms` の適用を固定するテストが 1 本も無い / 共通テストへの不要かつ未開示の語彙追加)。実装は正しく、テストが嘘をついていた。**織り込みが効くほど、残る欠陥は製品コードから証拠側へ移る** — 対称 2 週目のレビューは実装より先にテストを疑うこと。ただし織り込みは「同じ指摘を出さない」ことを保証しない (WP-2(a) の M-1 = timeout 配線の無テストは WP-3(a) で**再発**した)。対称実装の価値は指摘数の減少ではなく**両向きの照合**にある — WP-3(a) の B-2 (並行 flush の二重書込み) は後発 peer のレビューが先行 peer の潜在欠陥を見つけ、follow-up `a2a88e5` を生んだ
- **受け入れ監査は実装ラウンドより多く回り、欠陥は「失敗経路の第 2 段」に集中する**: WP-2(a) はレビュー後さらに**受け入れ監査 3 ラウンド**を要した。そこで閉じたのは二重計上・alert 行の無制限化・requeue/overwrite 経路であり、いずれも「1 回目の失敗をどう受け止めるか」の側にあった。同じ形が follow-up 1 (**flush 失敗時の復元で容量を超える** = bounded buffer の上限そのものが破れる) と WP-2(a) B-1 (**監査パイプライン自身の失敗が生む `SERVICE_UNAVAILABLE` が新規 denial として再入**し 1 操作が耐久 3 行を生む) にも現れた。**復元・切り詰め・再入を、正常系と同じ密度で設計し検証すること** — B-1 は P4-D7 (包含列挙) の決定根拠そのものになった
- **変異注入の復元は、ハッシュ照合だけでは製品コードへの残骸混入を防げない**: WP-2(a) では変異復元時に backup を取り忘れ、fallback の `git checkout` が実装者の変更を一度消した (レビュー開始時の `git diff` 全文から逐語復元し `git diff --stat` の完全一致で復旧)。WP-3(b) では受け入れ監査が **`cell.py` に残っていた変異残骸 1 行を除去**している。差分の一致確認は「消えていないこと」しか保証しない — **コミット前に変異文字列そのものを全文 grep すること**を手順に加える
- **「両論併記の候補集合」は、共通テストに peer 固有語彙が漏れ込んでいる兆候である**: 共通 C-09 vector 1 が `operation` を `{delete, mutate}`、`target_kind` を `{entity, collection}` と手で列挙しているのは、両 peer の実語彙を暫定的に吸収した形にすぎない。**候補集合を書きたくなったら、それは宣言化すべき語彙が宣言されていないという事実の現れ**であり、テストで丸めずに台帳へ起票する (→ L4-1、1.5.0 候補)
- **依頼者原則は採否の既定重み付けを変えた**: 「先送りしない / シンプルに / 制約で回避しない / 誇れる成果物」の 4 原則により、(i) **U-5 は監督推奨の「非対称を許容する」から「両 peer で記録する」へ覆り** (P4-D5)、その結果 MitateDB でも buffer overflow を実 emit 経路から検証できるようになった、(ii) **B-2 (`audit_events` 予約) は文書化義務から実装義務へ格上げ**され (P4-D10)、entity 識別子を受け取る全位置で効くことがテストで固定された、(iii) 契約 1.4.0 の**任意項目 7・8 が必須化**され、endpoint 分類の説明しづらい状態と「監査ポーリングが break-glass を締め出す」相互作用が、runbook の注意書きではなく構造で解消された。**「今は runbook に書いておく」で通そうとした項目こそ、原則 3 に照らして再検討する価値がある**
