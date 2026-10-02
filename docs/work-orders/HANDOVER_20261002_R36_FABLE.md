# 引き継ぎ書 — 2026-10-02 R-36 (オブジェクトストレージ・バイナリ API) 設計レビュー 1 回目

本書は R-36 設計レビュー 1 回目の cloud session の記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、R-36 の正本は設計 `docs/design/OBJECT_STORAGE_BINARY_API_V0_1.md` v0.3 (候補のまま。以下「設計」) である。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`)。前のチャットの記録: `docs/work-orders/HANDOVER_20261001_R108_FABLE.md`。

## 1. 現在地

- session: cloud (claude.ai/code)。branch `claude/sweet-heisenberg-nqoica`。基点 rev は clone した origin/main の先頭 `4241b55` (R-108 の閉止の merge)。
- 変更: 設計を候補 v0.2 → 候補 v0.3 にした。
  - `48470d5`: 設計レビュー 1 回目の反映 (v0.3。213 → 619 行。v0.2 の行は表題以外すべて残存を機械照合)。
  - `dd1bc9a`: 再確認 RC-1〜RC-21 (設計 §12 の「再確認の反映」) の反映 (v0.3 のまま。v0.2 からの通算で 213 → 703 行)。
- push: 本 session は割り当て branch へ push する (指示)。上の 2 commit は push 済み (origin の同名 branch)。main へは merge も送信もしない。workflow を手で起動しない。
- 触っていないもの: `spec/`、`security/`、`conformance-tests/`、両 peer、台帳 `RM`、版数ログ、既存の引き継ぎ書 (archive 移動を含む)。設計の状態は「候補」のまま (未実装・未宣言・非正本)。
- cloud 環境の制約:
  - Mitate の文書は読めない (実需は `RM` §3.2 の記述だけを使った)。
  - provider (Cloudflare R2 / GCS / Cloud Run) と RFC の公式文書は proxy 拒否で読めない (設計では全て「未確認」と明記)。
  - 完了ゲート (`tools/dev/gate.py`) と `tools/dev/finalize.py` (main への merge) は作業機で行う。
  - `.venv` は Python 3.11 で新規に作り、pre-commit を入れて `.venv/bin/pre-commit install` 済み (cloud 環境のみ。作業機の `.venv` とは別)。
- 本書の commit: 本書だけを加える 3 つ目の commit (hash は `git log -1 -- docs/work-orders/HANDOVER_20261002_R36_FABLE.md`)。設計の 2 commit (`48470d5`、`dd1bc9a`) の後に積む

## 2. 本チャットで閉じたもの

- 設計レビュー 1 回目 (`OC` §1.7 の 50 の 2 回のうち 1 回目。規模 L・Class D。1 巡目は reviewer「担当観点: A」「担当観点: B」の並列 2 起動、再確認は「指定なし」1 起動 (`OC` §1.7 の 50a))。
  - 現状との突き合わせ (explorer 3 起動、reader 1 起動): 契約 1.14.0、port v1.21、adapter 6。古くなった前提は設計 §10 の S-1〜S-16。
  - 1 巡目: 観点 A は 14 件 (設計 §12 の表記で A の 1〜14。依頼者決定の A-1 等とは別の番号)、観点 B は 18 件 (F1〜F18)。監督が重なりを設計 §12 の M-1〜M-22 にまとめた (M-17 / M-18 は統合で欠番)。各 M-n の反映 / 依頼者裁定待ちの別は設計 §12 の表。依頼者裁定待ちは設計 §11 の Q-1〜Q-5 と着手条件 (同 Q-0)。
  - 再確認 (指定なし 1 起動): 21 件 (中〜高 2、中 10、中〜低 6、低 3。クラス引き上げなし)。全件を監督が「直した」と裁定し、設計 §12 の RC-1〜RC-21 として v0.3 に反映した (版は v0.3 のまま)。設計 §12 の RC-9 (c) と RC-18 は案・両論として記し、確定は設計レビュー 2 回目。
  - 静的検査: `tools/check_doc_refs.py` 0 dangling、`tools/public_value_scan.py` (ツリーと新規ファイルの明示引数) 検出 0、`tools/dev/ledger.py --check` GREEN、pre-commit hook 緑 (commit 時)。
- 監督が起草後に埋めた箇所 (設計レビュー 2 回目で検証する): 設計 §3.4 の「未定」欄 (監督裁定 2026-10-02 の印)、設計 §11.1 の「監督の見立て」欄。

## 3. 次の一手

作業機で行う。

1. 依頼者裁定 設計 §11 の Q-0〜Q-5 (両論と監督の推奨は本書 §4)。Q-0 (着手条件の充足) が先。
2. worktree の作成: `git fetch origin claude/sweet-heisenberg-nqoica` の後、linked worktree (`.claude/worktrees/r36`) を同 branch から作る (共有ツリーを checkout しない。`OC` §1.2 の 13・14)。
3. 完了ゲート: 文書のみの変更 (本 session の 2 commit はパス上 Class A。設計レビューの発注クラス D は、設計が最終的に触れる `spec/` と `security/` の経路によるもので、§2 の「Class D」はこちら) だが、規模 L の手順として `tools/dev/gate.py --label r36-design-v03` を監督が単独実行し、集計行を記録する (`OC` §1.13 の 74: ゲートは省略しない)。
4. 台帳の版上げと `RM` R-36 行の【追記】: 設計レビュー 1 回目の実施 (2026-10-02、v0.3)、裁定待ち 設計 §11 の Q-0〜Q-5、6 版目の版数ログ行の archive 移動 (`OC` §1.16 の 78)。`tools/dev/ledger.py --check`。
5. 引き継ぎ書の archive 移動: 本書を含めて最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R102_FABLE.md` を `docs/archive/docs/work-orders/` へ `git mv` (`OC` §1.16 の 78)。
6. `tools/dev/finalize.py` で commit と main への `--no-ff` merge (identity r2fish / noreply の確認、`[skip ci]`)。push の入口は従前どおり (`docs/work-orders/HANDOVER_20261001_R108_FABLE.md` §3 の 4: push は Mitate 側の監督セッションが統制)。
7. provider / RFC の未確認事項の確認 (設計 §12.1 の一覧)。網に出られる環境で公式文書を読み、設計 §5 の表の「確認済み / 未確認」列を埋める。
8. 依頼者裁定の反映 (v0.4) の後、設計レビュー 2 回目 (規模 L: 1 巡目は観点 A / B の 2 起動並列、再確認は指定なし 1 起動)。見る箇所: 設計 §2.1 の SI の割り当て、versioning.obligations 案の義務名、設計 §7.1 の変異の候補列、設計 §3.4 の監督裁定の欄、設計 §11.1 の監督の見立ての欄、`{object_id}` の `field` 位置名が `{entity}` の既存の扱いと揃うか。
9. その後に契約 (1.x.0)・conformance (port v1.22 以降)・実装へ進む (CLAUDE.md の開発順序)。本 session では進めていない。

## 4. 依頼者判断待ち・未決

- 着手条件の充足そのものが依頼者裁定である (設計 §11 の Q-0)。
- 関連する台帳の未決: `RM` R-30 (設計 §11 の Q-2 と連動)、`RM` R-42 (設計 §11 の Q-3 と連動)。

以下は設計 v0.3 §11 (Q-0〜Q-5 と §11.1) の逐語の写しである。本小節の中の節番号 (§n)・M-n・RC-n・S-n・O-n・P-n・A-1〜B-12 は設計 v0.3 のもの、R-n・§3.2 等で `RM` を添えたものは台帳のものである。

設計レビュー 1 回目で挙がった、依頼者決定 A-1〜B-12 と現状の食い違い、または決定の確定後に挙がった露出である。決定は再審議しない。各件は両論のまま置き、v0.3 では確定しない。「推奨」は監督の推奨であり、裁定ではない。

### Q-0 着手条件の充足

- 決定: 台帳 `RM` R-36 の着手条件は「設計レビュー。充足は依頼者裁定」。
- 【v0.3 2026-10-02 再確認反映 RC-14】決定 (追記): 台帳 `RM` R-36 の着手条件には「運用開始後 (v1.105 の追記: 運用が始まって data と client が存在しても直す費用は上がらない)」もある (`RM`:459)。
- 現状: 実需は台帳 `RM` §3.2 の突合表で「部分的」(Mitate `docs/remaining-work-index.md` §将来設計・保留「添付ファイル・画像 — F2 とは別工程として保留」、`docs/design/agent-entry-record.md` §6.1。data-service-api への具体的な要件は未確定)。
- 【v0.3 2026-10-02 再確認反映 RC-14】運用開始の現状は本 session では確かめていない (作業機で台帳 `RM` §1 の現状から確認)。
- 食い違い: 設計レビュー 1 回目は 2026-10-02 に行ったが、契約・conformance・実装へ進む着手条件の充足は依頼者裁定である。
- 選択肢 (両論): (a) 充足とみなし、設計レビュー 2 回目へ進む。(b) 実需の記録を待つ (候補のまま保留)。
- 推奨: 監督は判断しない (依頼者事項)。

### Q-1 download 応答の分類

- 決定: §2「`Content-Type` は保存・返却する」、B-4、B-11 (ブラウザ向け attachment)。
- 現状: 契約 1.14.0 は全成功応答の media type を `application/json` に固定し (`spec/data-service-api.v1.json:8`、`:40` の 1.14.0 (a))、client は media type だけで分類する (`:895`、「HTTP status decides neither」)。§10 の S-2。
- 食い違い: (i) bytes の成功応答は現行文言で契約違反であり、かつ「解釈しない失敗」になる。(ii) 送信者が `Content-Type: application/problem+json` と errors.shape を満たす本文の object を upload すると、同 application の agent が download したとき、200 でも偽の失敗 (例: `AUTH_REVOKED`) として読む。`application/json` なら response schema との照合に回る。
- 選択肢 (両論):
  - (甲) 契約の分類規則に download 操作だけの例外を足す。2xx は bytes の成功 (media type を問わず response schema と照合しない)、2xx 以外で errors.content_type なら失敗、それ以外は解釈しない失敗。upload は request media type を operation 別に許す。
  - (乙) 甲に加えて、upload で media type が errors.content_type に一致するものを `VALIDATION_FAILED` で拒否する (problem+json 文書を保存する能力を失う)。
  - (丙) download は常に `application/octet-stream` で返し、保存値は metadata にだけ載せる (§2 の「返却する」と B-11 の想定を変える)。
  - いずれも契約の `media_type_note` / `response_classification` / `external_standards` の改版 (1.x.0、従属判断 19 の例外) になる。
  - 【v0.3 2026-10-02 再確認反映 RC-19】`spec/data-service-api.v1.json:36` では additive な capability は minor。object_storage は common_baseline の外の新 capability で、既存の要求・応答の意味は変えない。media_type_note / response_classification の改版は新しい操作にだけ掛かる例外の追加であり、既存操作の分類は不変。したがって minor (1.x.0) と読む。semantic change と読む余地があれば major であり、その判断は依頼者。
- 推奨 (監督の推奨): (甲) + (乙)。

### Q-2 A-1 の application 専用実行単位への到達経路

- 決定: A-1。
- 現状: object 経路は data surface に属し、client は `surfaces.data.base_url` から URL を組む (`spec/data-service-api.v1.json:35`)。data / control の文書は同じ surfaces を返し、control surface は deployment に 1 つ (`:1410`)。limit_enforcement は base URL 背後の全 process を記述する (`:324`)。base URL を serve する process は 1 host (`MULTI_PROCESS_WORKER_V0_1.md:778`)、concurrency の enforced は 1 host の slot 共有が条件 (同 `:845`)。`conformance-tests/CONDITIONS.md` C-19 は 1 base URL と 1 credential で足りることを要求する。台帳 `RM` R-30 (SI-00 の境界と複数 Application の DSN) は未決。§10 の S-13。
- 食い違い: 1 つの data base URL の背後に application ごとの実行単位を置く経路が設計に無い。v0.2 の §9 の 1 は deployment 設計に回しているが、契約の問題である。
- 選択肢 (両論): §11.1 の表の (i)〜(iii)。
- 推奨 (監督の推奨): (ii) を台帳 `RM` R-30 の裁定と同時に決める。各案の `concurrency` / `object_transfers` の `limit_enforcement` の帰結を表 (§11.1) で併記する。

#### 11.1 到達経路の選択肢

「監督の見立て 2026-10-02」の欄は、v0.3 の材料 (設計レビュー 1 と監督の突合) に無く監督が起草後に埋めたものであり、設計レビュー 2 回目で検証する。裁定は依頼者。

| 案 | 内容 | 改版の要る契約・規則 | `concurrency` の `limit_enforcement` | `object_transfers` の `limit_enforcement` | SI-00 の観点 | O-5 の期待値。【v0.3 2026-10-02 再確認反映 RC-4】他 application の単位 / URL へ誤配されたときの結果 (欠陥の観測。peer-local または deployment evidence の条件であり O-5 ではない) |
| --- | --- | --- | --- | --- | --- | --- |
| (i) | application ごとに別の data base URL (= 別 deployment)。台帳 `RM` R-30 の「serving set を 1 Application に限る」側を全面採用する | control surface と、surfaces 同一の規則 (`spec/data-service-api.v1.json:1410`) | 監督の見立て 2026-10-02: 各 deployment が 1 host なら `enforced` (`MULTI_PROCESS_WORKER_V0_1.md` 裁定 10・27 のまま) | 監督の見立て: 同じく 1 host 内の共有 slot で `enforced` | 監督の見立て: multi-application 部品が無く SI-00 の面では最も単純。費用は application 数に比例する deployment 数 | 監督の見立て: 別 deployment の credential は `AUTH_INVALID` (そもそも base URL が別) |
| (ii) | 1 base URL のまま、前段 router が credential から application を引き、専用単位へ振り分ける。router は bucket 資格情報を持たない。各単位は bearer を自分の 1 application に再認証するので、誤配は `AUTH_INVALID` で閉じる | 監督の見立て 2026-10-02: 契約は変えなくてよい (surfaces は 1 つのまま) | Cloud Run で service が複数 = 複数 host なら `deployment_required` へ後退 (Cloud Run の挙動は未確認)。1 host 内の process 分割なら `enforced` のまま | 監督の見立て: application 単位の枠はその application の単位 (1 host) に閉じるので `enforced`。【v0.3 2026-10-02 再確認反映 RC-15】application の単位が 1 instance (Cloud Run なら最大 instance 1。自動スケールの挙動は未確認) のとき | router は全 application の認証状態と全 bytes を扱う multi-application 部品であり、SI-00 の対象 | `NOT_FOUND` は `AUTH_INVALID` に変わり得る。【v0.3 2026-10-02 再確認反映 RC-4】誤配の結果は `AUTH_INVALID` |
| (iii) | object endpoint を application 専用の path prefix、または新 surface (`surfaces.objects`) に置く | url_composition、`conformance-tests/CONDITIONS.md` C-19 と C-35 | 監督の見立て 2026-10-02: (ii) と同じ (prefix で振り分ける前段が要る) | 監督の見立て: (ii) と同じ | 監督の見立て: 前段は path だけ見るので認証状態を持たないが、application の識別子が URL に出る (非開示の衛生に反する) | 監督の見立て: 他 application の prefix へ送った credential は `AUTH_INVALID` |

### Q-3 転送時間の bound

- 決定: B-5 (4 class)、§2「ストリーム読み書き時間を宣言・強制」。
- 現状: 時間を表す limit class は `execution_ms` だけで、計測開始と待ちの扱いは台帳 `RM` R-42 で未決 (§10 の S-14)。
- 食い違い: §2 の時間の要求を、B-5 の 4 class のどれも表さない。
- 選択肢 (両論):
  - (甲) `execution_ms` を転送全体 (受付から available / 送信完了まで) に掛け、台帳 `RM` R-42 の裁定に従う。class を増やさない。1 byte/秒の upload は宣言時間で `LIMIT_EXCEEDED` になり、枠が解放される。
  - (乙) 転送の全体時間と最低速度 (idle) の class を足す (B-5 を超える)。
- 推奨 (監督の推奨): (甲)。宣言しない運用値の timeout は置かない (台帳 `RM` P-3 / P-5)。

### Q-4 B-7 と両 peer の宣言値 0

- 決定: B-7「authorization propagation bound 以内の周期で再認可し、失効を観測したら転送を中断する」。
- 現状: 両 peer は `authorization_propagation_bound_ms: 0` を宣言する (`r2db-api/src/r2db_api/capabilities_document.py:188`、`MitateDB-api/src/mitatedb_api/capabilities_document.py:452`。schema の最小値は 0)。SI-13 は要求単位の「subsequent authorization」に掛かり、転送途中の再認可を求める文言は無い (`security/SECURITY_INVARIANTS_V1.md:338-351`)。
- 食い違い: 0 を文字どおり守るには chunk ごとの再認可が要る。v0.2 の設計内でも §4 の 4 (転送後 1 回) と §6 の 5 / B-7 (転送中) がずれていた (§4 の 4 は v0.3 の M-11 で「転送の間、周期 P で再認可 + 完了時にも 1 回」に揃えた)。
- 選択肢 (両論):
  - (a) object_storage を提供する deployment は正の bound を宣言し、その値を「失効の伝搬遅延 + 再認可周期 P」を含む値とする (宣言値の変更。台帳 `RM` §9 の 8 でクラス確認)。
  - (b) chunk ごとに再認可し、0 を保つ (認証 DB の負荷)。
  - (c) SI-13 を受付時と available 直前 (commit) に適用し、転送中は再認可しない (B-7 の本文と食い違うため推奨しない。記録のみ)。
- 推奨 (監督の推奨): (a)。どの案でも、再認可で `AUTH_STATE_UNAVAILABLE` なら中断する (fail closed)。download の中断は接続の異常終了で client に伝え、client は「受信長 = `Content-Length` かつ `Content-Digest` 一致」を成功条件とする (§3.3 の M-6 の反映と同じ)。

### Q-5 総保存量・object 数の上限

- 決定: B-5 (rate のみ)。
- 現状: SI-08 (`security/SECURITY_INVARIANTS_V1.md`) は「object creation rate or count」を挙げ、rate (`object_requests_per_minute`) で文言は満たす。台帳 `RM` P-5 は安全上必要な bound だけを置く。provider の課金は application をまたぐ運用者の共通資源である。
- 食い違い: 決定との矛盾ではなく、B-5 の確定後に挙がった露出である。
- 選択肢 (両論):
  - (a) 初版は class を足さず、§8 の運用値に provider 側の quota / 予算 alert を置く。
  - (b) `object_count` / `object_total_bytes` の class を足す (B-5 を超える)。
- 推奨 (監督の推奨): (a)。

## 5. 運用上の教訓

- cloud session では Mitate 文書・provider 公式文書・完了ゲートに到達できない。到達できないものは「未確認」と書き、作業機の次の一手 (本書 §3) に回した。
- 設計の起草後に監督が埋めた欄 (「監督裁定」「監督の見立て」) は印を付け、次のレビューの対象と明記した。
- `conformance-tests/CONDITIONS.md` に未定義の共通条件の番号 (現行の最大 C-35 より上) は `tools/check_doc_refs.py` が赤にするので、候補条件は設計内の局所 ID (設計 §7.1 の O-n) で書いた。

## 6. 裁定

`OC` §1.15 の 77。語は 起票 R-N / 既知の穴 / 観察 / 直した に、本書では「裁定待ち」を足す (77 の 4 語の外。依頼者裁定が未了の件を起票にも観察にもしないため)。「裁定待ち」= 依頼者裁定待ち (設計 v0.3 の独立節 Q-n に両論で置いた。確定は依頼者)。表の M-n・RC-n・Q-n・S-n・O-n・B-n・P-n は設計 v0.3 のもの、「レビュー A・n」「レビュー B・Fn」は 1 巡目の観点 A / B の指摘番号、「再確認・n」は再確認の指摘番号である。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー A・1 / B・F1 (download の Content-Type を送信者が決められ、契約の分類で偽の失敗・成功と読む) | 裁定待ち (Q-1) | 契約 1.14.0 の分類規則 (従属判断 19) に操作別の例外を足す決定で、依頼者事項 |
| レビュー A・2 / B・F3 (A-1 の application 専用実行単位へ要求を届ける経路が無く、1 base URL・surfaces 同一・1 host の規律と衝突) | 裁定待ち (Q-2) | 依頼者決定 A-1 と現状 (契約 :35 / :1410 / :324、`MULTI_PROCESS_WORKER` 裁定 10・27) の食い違い。台帳 `RM` R-30 と連動 |
| レビュー A・3 (host 共有の認証前 concurrency slot を長い転送が占有する。object_transfers の範囲と置き場) | 直した (M-3) + 裁定待ち (Q-3) | slot の持ち替え・application 単位・flock 実現は設計で確定。転送時間の class は B-5 の 4 class を超え得るので依頼者 (R-42 と連動) |
| レビュー A・4 (cleanup worker が SI-00 の confused deputy になり得る) | 直した (M-4) | A-1 の制約を worker にも及ぼし、provider key を再計算して照合にだけ使う |
| レビュー A・5 / B・F15 の一部 (process 喪失で pending が回収されず孤児が残る。未完了 multipart / resumable) | 直した (M-5) | pending の期限回収と cleanup の監査を設計に書いた。provider の abort 操作は未確認と明記 |
| レビュー A・6 / B・F4 後半 (download の途中失敗が短い成功に見える。upload の途中拒否が届かない) | 直した (M-6) | Content-Length 必須・異常終了・client の成功条件・100-continue を設計に書いた |
| レビュー A・7 / B・F12 (idempotency の digest 材料・評価時点・header 構文・直列化の地点・削除の idempotency) | 直した (M-7) | 材料と 2 transaction 構成を設計で確定。B-1 の本文は変えない |
| レビュー A・8 / B・F5 の filename (B-11「正規化」と §3.2「拒否」の食い違い、filename*、非 ASCII) | 直した (M-8) | 置換と拒否の表で固定し §3.2 を B-11 に寄せた |
| レビュー A・9 / B・F2 / B・F11 (削除の 204 は 1.14.0 (a) と :895 で解釈しない失敗。dry_run / budget の無視) | 直した (M-9) | 200 の JSON 結果、成功の定義、閉じた schema、unsupported_field の拒否を設計に書いた |
| レビュー A・10 / B・F10 / B・F15 (provider と前段の上限に依る主張。nginx 1100k、Cloud Run 上限、R2 token 粒度、条件付き PUT、no-transform) | 直した (M-10) + 観察 | 設計の主張を bucket 範囲に改め、§6 の 6 (前段の上限) を足した。provider 挙動は全て未確認 (作業機で確認する。次の一手) |
| レビュー A・11 / B・F4 前半 (再認可の位置の矛盾、周期と bound、AUTH_STATE_UNAVAILABLE、両 peer の bound 0) | 直した (M-11 の反映分) + 裁定待ち (Q-4) | 位置と fail closed は設計で確定。B-7 と宣言値 0 の食い違いは依頼者 |
| レビュー A・12 / B・F8 (§7 の 4 が §4 の順序で満たせない) | 直した (M-12) | Content-Length 付きと chunked に条件を分けた |
| レビュー A・13 / B・F13 の容量 (総保存量・object 数の上限が無い) | 裁定待ち (Q-5) | class の追加は B-5 を超える。推奨は足さない (P-5) |
| レビュー A・14 / B・F6 / B・F7 (操作名の不揃い、metadata の宣言漏れ、roles、object_id 構文違反の code、request_id の意味、keep-alive) | 直した (M-14) | 1 組の名前、roles、IDENTIFIER_INVALID、request_id の規則、Connection: close を設計に書いた。`get_object_metadata` は B-12 の列挙への追加 |
| レビュー B・F5 (object 専用 error 語彙の表が無い。header の違反を details で表せない) | 直した (M-15) | 失敗の表と `header/<名>` の位置表記、violated_declaration の拡張案 |
| レビュー B・F9 (conformance の観測点・port・変異・PROVIDED/ABSENT・実クラウド skip) | 直した (M-16) | §7 を条件表 (O-n 仮) に書き直し、port v1.22 以降の拡張と ABSENT 分岐を明記 |
| レビュー B・F13 の計測対象 (object_metadata_bytes 等の定義、requests_per_minute との関係) | 直した (M-3) | class ごとの定義と境界を書いた |
| レビュー B・F14 (Content-Digest の algorithm・Content-Encoding・canonical string・download の照合) | 直した (M-19) | 4 点の規則を §2 に書いた |
| レビュー B・F16 (§9 の順序が CLAUDE.md の開発順序と逆。CONTROL_MAPPING の段が無い) | 直した (M-20) | 並べ替えた |
| レビュー B・F17 (§2 に SI の ID が無い) | 直した (M-21) | SI 列と条件列を足した。invariant は増やさない |
| レビュー B・F18 (版数表・v0.1 の不在・A-2 の陳腐化・ID 参照・「ブラウザ向け」) | 直した (M-22) + 観察 | 版数表と註を足した。v0.1 の推薦案と却下案は repository に無い (復元しない) |
| 監督 S-1〜S-16 (枠。v0.2 以後に古くなった前提) | 直した | v0.3 の「現状との突き合わせ」節に表で写し、決定行に註 |
| 監督 S-16 / 台帳 R-36 (着手条件の充足) | 裁定待ち (Q-0) | 着手条件の充足そのものが依頼者裁定 (台帳 §3.2・§5 フェーズ11) |
| 再確認・1 (削除の再送の結果が設計内で矛盾) | 直した (RC-1) | key なしは NOT_FOUND、同 key は元の 200 の replay に分けた |
| 再確認・2 (`deleting` のまま SIGKILL で bytes が残る) | 直した (RC-2) | 回収対象に `deleting` を足し、条件 O-19b |
| 再確認・3 (audit を tx2 の中と読める) | 直した (RC-3) | pre_commit (決定 1-A) に揃え、delete も同経路 |
| 再確認・4 (O-5 の期待値が AUTH_INVALID を許す) | 直した (RC-4) | O-5 は NOT_FOUND に固定、誤配の観測は別列 |
| 再確認・5 (filename の文字集合・順序・優先・charset・fallback) | 直した (RC-5) | 表に 5 点を足した |
| 再確認・6 (認証後の枠の対象と rate の鍵) | 直した (RC-6) | 持ち替えは upload / download のみ、鍵は credential_id / application |
| 再確認・7 (cleanup と遅い upload の競合) | 直した (RC-7) | 条件付き更新と worker の先行遷移 |
| 再確認・8 (検査順と欠けた失敗行) | 直した (RC-8) | 検査順の表と 4 行を足した |
| 再確認・9 (`unsupported_field` の誤用、`field` 定義、header の手がかり) | 直した (RC-9。(c) は案として記し確定は設計レビュー 2) | spec :921 の語義に合わせ request_schema、`field` 定義の改版を明記 |
| 再確認・10 (port の注入 method と偽 provider の fail closed) | 直した (RC-10) | :417 に足した |
| 再確認・11 (O-20 の変異が殺せない) | 直した (RC-11) | C-33 の形に |
| 再確認・12 (SI-11 の前提 atomicity、SI-03 の根拠) | 直した (RC-12) | atomicity 案と SI-03 の言い換え |
| 再確認・13 (obligations 案が非網羅) | 直した (RC-13) | 非網羅の例示と明記 |
| 再確認・14 (Q-0 に「運用開始後」が無い) | 直した (RC-14) | 台帳行の着手条件を全部写した |
| 再確認・15 (§11.1 (ii) の 1 instance 条件) | 直した (RC-15) | 条件を付けた |
| 再確認・16 (§4 が Q-4 の (c) を先に閉じる) | 直した (RC-16) | (a)(b) に限定 |
| 再確認・17 (O-4a の Evidence が in-process を含む) | 直した (RC-17) | wire に |
| 再確認・18 (O-11 の part 長。不確実) | 直した (RC-18。両論を註に。確定は設計レビュー 2) | SDK の part 長は未確認 |
| 再確認・19 (Q-1 の 1.x.0 の論証。不確実) | 直した (RC-19) | spec :36 に照らした 1 行。major と読む余地は依頼者 |
| 再確認・20 (:277 の「未定」の説明) | 直した (RC-20) | 経緯の記述に |
| 再確認・21 (O-18 の空振り。観察) | 直した (RC-21) | 監査 event の観測を必須に |
