# 引き継ぎ書 — 2026-10-01 R-108 (契約文書だけで要求を組む参照クライアント) 閉止

本書は R-102 / R-119 の後片付け、既知の穴 G、CI の起動条件、R-108 の実施のチャットの記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)、R-108 の正本は設計 `docs/design/REFERENCE_CLIENT_V0_1.md` v0.7 (依頼者裁定は同書 §9) と作業指示書 `docs/work-orders/WORK_ORDER_R108_REFERENCE_CLIENT_V1.md` (§1 の監督裁定 M-1〜M-10、§5 の記録、§6 の訂正註 1〜6) である。前のチャットの記録: `docs/work-orders/HANDOVER_20261001_R102_FABLE.md`。

## 1. 現在地

- local main `9be46b7` (CI の起動条件の変更の merge)。R-108 の WP-1〜WP-4 は branch `r108` (worktree `.claude/worktrees/r108`) にあり、WP-4 のレビュー修正 (差し戻し 1) は〈監督が埋める: WP-4 のレビュー後の commit と再確認の結果〉。WP-5 (本書を含む記録) は worktree `.claude/worktrees/r108-wp5` (branch `r108-wp5`、`a9202f0` から) で起草した。
- R-108 の閉止: 〈監督が埋める: main の merge commit、完了ゲートの正本の集計行・judge・label・merge 候補〉。番号は契約 1.14.0 (従属判断 19)、共通条件 C-35、port v1.21、`security/CONTROL_MAPPING.md` 3.16、台帳 v1.148、設計 v0.7。R-121 を起票。push は停止中。
- 記録の置き場: 本書を commit する変更セットで、最新 2 通から外れる `docs/work-orders/HANDOVER_20261001_R115_FABLE.md` を `docs/archive/` 配下へ移す (`OC` §1.16 の 78)。

## 2. 本チャットで閉じたもの

- (i) R-102 / R-119 の worktree 10 個を畳み込んだ。`tools/dev/fold.py` が SKIP した detached の 1 個と、未 merge の merge commit を持つ 2 個は、親がすべて main にあることを確かめて手で外した。
- (ii) 既知の穴 G: `tools/check_comment_provenance.py` の Known gaps 8 番 (main `b656dbf`、commit `73985f8`)。完了ゲート 4927 passed (label known-gap-g)、`tools/tests` 786 passed、変異 G8-1 / G8-2 赤。
- (iii) CI の起動条件を `main` への push と `workflow_dispatch` に絞った (依頼者裁定 2026-10-01、main `9be46b7`、commit `31037d5`)。完了ゲート 4927 passed (label ci-main-only)。
- (iv) R-108。レビューの列は 1 巡目の A / B の件数と再確認の件数 (裁定は §6)。変異の列は `expect=red` / `expect=error` で期待どおりを実測した件数 (作業指示書 §2 と各報告の `mutate:` 行から)。

| 段 | commit | 内容 | レビュー | 変異 |
|---|---|---|---|---|
| WP-1 | `a77131d` → `3bd670b` → `cb6e295` | 契約 1.14.0 (設計 §9.1 の 12 文と obligations の entry)、両 peer の宣言、C-35 を declared で開く。レビューで `tools/deploy_smoke.py` を redirect を追わない形に直した | A 5・B 5、再確認 4 | 26 (V2〜V24 の 23、R1-4、RV-1・RV-2) |
| 訂正註 4・5 | `4a8a6a8` | WP-2・WP-3 のレビューの裁定の記録 | — | — |
| WP-2 | `51c770d` → `03b43ba` → `4f32224` (`r108` への merge `7aea515`) | port v1.21 の `wire_entry` (wire の 4 plug、in-process は `AssertionError`)。送信関数は正規形でない method / URL、fragment、userinfo を運ばず拒む。`_ISOMORPHIC_TARGETS` 205 → 208、`docs/design/CONFORMANCE_ADAPTER_V1.md` §31 | A 3・B 7、再確認 1 | 18 (V31〜V40c の 15 (V38a は error)、V34c・V36b、V34d)。レビューの RB-1・RB-3 も赤 |
| WP-3 | `7970d0f` → `b820658` → `cc6f9d6` (`r108` への merge `789e3ea`・`a9202f0`) | 参照クライアント `conformance-tests/reference_client.py` と単体テスト・静的 pin、`conformance-tests/schema_check.py` に `maxLength`・`maxProperties` | A 6・B 9、再確認 2 | 59 (37、差し戻し 1 の 16 (レビューの RA-1〜RA-3・RB1a〜RB5 を含む)、差し戻し 2 の 6) |
| WP-4 | `e5d0e0a` → 〈監督が埋める: レビュー後の commit〉 | C-35 を `executable (four wire adapters)`、C-19 に義務 (b) の test、test module の pin、`conformance-tests/CONDITIONS.md` の凡例の 1 文、`security/CONTROL_MAPPING.md` 3.16、両 peer の runbook に義務 (c) の 1 文 | A 2・B 7、再確認〈監督が埋める: 件数〉 | 28 (V79 は error) + 〈監督が埋める: 差し戻し 1 の変異 (RA4-1〜3・RB4-1〜3 ほか) の結果〉 |
| WP-5 | 〈監督が埋める: commit〉 | 設計 v0.7 の註、台帳 v1.148 (閉止・R-118 への追記・R-121 の起票)、本書、作業指示書 §5 | — | — (監査照合) |
| 予備ゲート | `a9202f0` | `gate: 5014 passed, 2 subtests passed in 711.50s (0:11:51)`、judge=PASS、pg_database/pg_roles diff 0 (label r108-pre) | — | — |
| 完了ゲート | 〈監督が埋める: merge 候補〉 | 〈監督が埋める: 集計行・judge・pg の差分・label・日時、`COLLECTION_FLOOR` 4927 → 後の値、`tools/tests` の集計行〉 | — | — |
| 計測 | — | 〈監督が埋める: 作業指示書 §5.3 の要約〉 | — | — |
| 受け入れ監査 | — | 〈監督が埋める: パケットの判定の集計と扱い〉 | — | — |

## 3. 次の一手

1. R-121 (socket 経路の redirect の `Location` が宣言の port を持たない、規模 S) は着手可能。
2. R-120 は依頼者の着手判断待ち。R-118 は依頼者裁定待ち (契約 1.14.0 の alias の句の扱いを v1.148 で追記した)。
3. worktree の畳み込み: `known-gap-g`、`ci-main-only`、`r108` 系 (`r108`・`r108-wp2`・`r108-wp3`・`r108-wp5`) は merge の後に `tools/dev/fold.py`。
4. push は停止中。push の入口は Mitate 側の監督セッションが統制する (このセッションからは push しない)。提出の締切 2026-10-15 23:59 JST より前に main が push される予定で、以後 2026-12-01 まで main は動かさない、との連絡を受けている。

## 4. 依頼者判断待ち・未決

依頼者指示「裁定は監督の推奨で進め、最後にまとめて確認」の下で進めた裁定の一覧 (再審議ではなく確認。逐語は作業指示書):

- A. 作業指示書 §1 の監督裁定:
  - M-1: port に `wire_entry` を足し、同期の送信関数 `send(method, url, headers, body)` は渡されたものを運ぶだけで redirect を追わない。in-process の 2 plug は `AssertionError`。
  - M-2: クライアント module の文字列定数は (i) 契約の key、(ii) 散文由来リテラルの表、(iii) 例外の文、(iv) 設計 §4.1 の表だけを許し、operation 名・path・schema 名等の禁止集合と一致すれば赤。
  - M-3: C-35 の Status 表記は `executable (four wire adapters)`、凡例に 1 文を足す。
  - M-4: 義務 (b) の常設の証拠は C-19 に test 1 本 (6 adapter の data 面の文書)。
  - M-5: C-35 の行を WP-1 で declared として先に開く。
  - M-6: 契約に足す key は関係する key の直後に置く。
  - M-7: C-35 と `conformance-tests/test_wire_entry.py` の test が自分の xdist group 名を assert する。
  - M-8: 「運ぶだけ」は transport の受け渡し点の spy で照合し、socket の nginx より先は確かめない。
  - M-9: `_ISOMORPHIC_TARGETS` に `wire_entry` と hook の既定の行を足し、件数 pin の名と `security/CONTROL_MAPPING.md` の参照を同じ WP で追随させる。
  - M-10: 確定文ファイル (port の docstring の最初の段落、C-35 の 3 cell と凡例の文)。
- B. 作業指示書 §6 の訂正註の監督裁定:
  - 訂正註 1: WP-1 の触ってよいパスに `conformance-tests/test_operation_catalog_register.py` を足した。declared の C-35 の Evidence は file 名を持たない散文にした。marker 系 3 本の部分収集での赤は構造的とした。義務 (a)(b) の実測と、control credential の経路が 401 で文書を返さないことを記録した。
  - 訂正註 2: 義務 (c) を「既に満たす」と言い切らない形に直した。runbook 2 文書に義務 (c) の確定文を足す (WP-4)。`tools/deploy_smoke.py` を redirect を追わない形に直す (本項目の範囲に足した)。起動時に別綴りの上書きを拒む検査は足さない (観察)。
  - 訂正註 3: `tools/deploy_smoke.py` の test の 4 件を監督が直した。
  - 訂正註 4: 送信関数は正規形でない method / URL を拒む ((a))。件数 assert を 208 に。secret の欄は比較からも外す。圧縮応答の食い違いは開示。socket plug の 307 の `Location` は起票 (R-121)。
  - 訂正註 5: WP-3 のレビューの 10 項目 (base URL を URI として読む、`code` を文に入れる条件、`Content-Type` が複数の応答、NaN、`localhost` を外す、keyword ガードを全項に広げて完了条件 73 を読み替える、`ContractMismatch` を解釈しない失敗の側に受け入れる ほか)。
  - 訂正註 6: 送信関数は fragment と userinfo も拒む。静的 pin の import を閉じた表にし、(iii) の免除の規則を絞った。WP-4 のレビューの 7 項目 (test module の pin の 6 形、#12 (b) の Evidence を SI-06 に置く、ほか)。予備の完了ゲートの記録。
- C. R-121 の起票 (規模 S、着手条件なし)。
- D. 設計 v0.7 の §7 の註: 表の「SI-03・SI-06: 本項目は新たに検証しない」を、C-19 に足した test が 6 adapter で data 面の文書の `role` を見る、と読み替えた。
- E. 〈監督が埋める: 依頼者確認の結果 (逐語)〉

## 5. 運用上の教訓

- レビュー担当の変異 spec は生き残ることが多い (WP-2 は 3 件中 1 件、WP-3 は 9 件中 8 件、WP-4 は 6 件すべてが緑)。差し戻しの前に監督が実行し、穴の実証として差し戻しに貼った。
- ゲートの排他 lock の間は `pt.py --wait` と `mutate.py --wait` で待たせる。
- 並行 worktree が同じ test ファイル (`conformance-tests/test_reference_client.py`。WP-3 の再確認と WP-4) に触れると merge で衝突する。docstring 1 か所で、両側を残して解決した。
- 件数を名指す assert は別ファイルにも残る (`r2db-api/tests/test_r78_pool_wait_stats.py` の `_ISOMORPHIC_TARGETS` の件数。作業指示書 訂正註 4 の 1)。`git grep` で実測する。
- 作業指示書が参照する条件 ID は、`conformance-tests/CONDITIONS.md` に declared の行を先に開かないと doc 参照検査が赤になる (M-5)。declared の行が未作成の test file を名指すと `conformance-tests/test_conditions_register.py` が赤になる (訂正註 1 の 2)。
- 別セッション経由で届いた依頼者裁定 (CI の起動条件) は、このセッションで依頼者に確認してから main に入れた。

## 6. 裁定

`OC` §1.15 の 77。語は 起票 R-N / 既知の穴 / 観察 / 直した の 4 語。材料はレビュー報告 11 通 (WP-1〜WP-4 の観点 A / B と WP-1〜WP-3 の再確認)、差し戻し 5 通、作業指示書の訂正註 1〜6。表の順は時系列。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 実装 WP-1・逸脱 1 (`conformance-tests/test_operation_catalog_register.py` の key 集合のピンが赤、触ってよいパスの外) | 直した (受け入れ) | 集合を 4 つに。触ってよいパスに足した (訂正註 1 の 1) |
| 実装 WP-1・逸脱 2 (declared の C-35 の Evidence が未作成の test file を名指して赤) | 直した | Evidence を散文に、file 名は WP-4 で Status に (訂正註 1 の 2) |
| 実装 WP-1・逸脱 3 (marker 系 3 本が部分収集で赤) | 観察 | 構造的な赤。判定は suite 全体を収集する完了ゲート (訂正註 1 の 3) |
| 実装 WP-1・疑義 (control credential で data 面の capabilities を読む経路が 401) | 観察 (記録) | 義務 (b) は返す文書に掛かるので破れない。設計 v0.7 の §11 の註 (訂正註 1 の 4) |
| 実装 WP-1・判断 (宣言 4 か所の `check_comment_provenance` §4.1 (1) の赤) | 観察 (正当な赤) | 版の literal の変更 (訂正註 1 の 5) |
| レビュー WP-1 A・1 / B・1 (義務 (c) まで「既に満たす」と言い切る) | 直した | (a)(b) の実測と (c) の掛かる URL を宣言する plug が無いことに限った (差し戻し 1 の 1) |
| レビュー WP-1 A・3 / B・3 (test のコメントの「of another origin」) | 直した | 組む URL 以外という表現に (差し戻し 1 の 2) |
| レビュー WP-1 B・4 ((c) の要約に要約である旨の断り書きが無い) | 直した | 差し戻し 1 の 3 |
| レビュー WP-1 A・2 / B・2 (配備者向けの文書に義務 (c) が無い) | 直した (WP-4) | 両 peer の runbook に確定文、`security/CONTROL_MAPPING.md` の行参照を引き直した (訂正註 2 の 4) |
| レビュー WP-1 A・2 / B・2 の派生 (起動時に別綴りの上書きを拒む検査) | 観察 | 同じ endpoint の別綴りは一般に機械判定できず、(c) を満たすかは配備の性質。設計 §11 の v0.6 の項が開示済み (訂正註 2 の 4) |
| レビュー WP-1 A・4 / B・5 (`spec/CCR_DISPOSITION.md` の 19 が引く §5.5 の表 1 が空) | 直した (WP-5) | 作業指示書 §5.5 の表 1 を埋めた (訂正註 2 の 5) |
| レビュー WP-1 A・5 (`tools/deploy_smoke.py` が bearer を付けたまま redirect を追う) | 直した | redirect を追わない opener と `tools/tests/test_deploy_smoke.py`、R1-4 赤 (差し戻し 1 の 4) |
| 再確認 WP-1・1 (3xx の本文を読まない分岐が未固定、RV-1 生存) | 直した (監督) | JSON でない 302 本文と stage の失敗文の assert、RV-1 赤 (訂正註 3 の 1) |
| 再確認 WP-1・2 (sentinel の完了条件に変異が無い) | 直した (監督) | RV-2 を変異表に、赤 (訂正註 3 の 2) |
| 再確認 WP-1・3 (`_NoRedirect` の docstring の契約の写しの欠落) | 直した (監督) | 逐語に戻した (訂正註 3 の 3) |
| 再確認 WP-1・4 (R1-4 の赤が status の assert で止まり漏洩を観測しない) | 直した (監督) | 転送先が要求を受けていない assert を先に (訂正註 3 の 4) |
| 実装 WP-2・判断 (hook は factory、同型性の行 3 本で 208、3xx の URL は全 plug で末尾 slash の 307) | 直した (受け入れ) | 訂正註 4 の前文 |
| レビュー WP-2 B・1 (`r2db-api/tests/test_r78_pool_wait_stats.py` の件数 assert が 205) | 直した | 208 に。触ってよいパスに足した (訂正註 4 の 1) |
| レビュー WP-2 A・1 / B・2 (送信関数が正規形でない method / URL を黙って直して運ぶ) | 直した ((a)) | 両 peer で送らずに例外、完了条件 34c、V34c 赤 (訂正註 4 の 2) |
| レビュー WP-2 A・2 (空の secret のとき他方の secret が失敗文に出る) | 直した | 添字だけを出す (訂正註 4 の 3) |
| レビュー WP-2 B・3 (`repr=False` は `==` の失敗文を防がない) | 直した | `compare=False` と欄の構造の assert、V36b 赤 (RB-2 は `-q` で緑。訂正註 4 の 4) |
| レビュー WP-2 B・4 (完了条件 36 の失敗文の脚) | 観察 (対応不要) | RB-3 で単独の赤を実測 (訂正註 4 の 5) |
| レビュー WP-2 A・3 (圧縮された応答で header と本文が食い違う) | 直した (開示) | `docs/design/CONFORMANCE_ADAPTER_V1.md` §31.3。いまの 4 plug では届かない (訂正註 4 の 6) |
| 実装 WP-2・判断 5 (接続失敗の例外が未固定) | 直した | socket の 2 plug の test 1 本 (訂正註 4 の 7) |
| レビュー WP-2 B・5 (`check_comment_provenance` の対象外の出力) | 直した (記録) | 報告に注記 (訂正註 4 の 8) |
| レビュー WP-2 B・6 (socket plug の 307 の `Location` が宣言の port を持たない) | 起票 R-121 | DB の利用者が redirect の宛先の違いに気づく。`docs/design/CONFORMANCE_ADAPTER_V1.md` §31.2 に実測の 1 文 (訂正註 4 の 9) |
| レビュー WP-2 B・7 (V34a を URL だけを書き換える transport の派生で測った) | 観察 (受け入れ) | client 層の header で先に赤になる紛れが無い (訂正註 4 の 10) |
| 再確認 WP-2・1 (拒否の検査が fragment と userinfo を素通し) | 直した (監督) | 両 peer で同じ文、V34d 赤 (訂正註 6 の 1) |
| 実装 WP-3・判断 (公開 API は `fetch_capabilities` と `call`、例外 class の構成、violation の path だけを文に、surface の判定、base URL の一致を client に持たせない) | 直した (受け入れ) | 訂正註 5 の前文 |
| レビュー WP-3 A・1 (失敗の種類を入れ替える変異 RA-1・RA-2 が生き残る) | 直した | problem 形の本文の場面、RA-1・RA-2 赤 (訂正註 5 の 1) |
| レビュー WP-3 A・2 / B・9 (base URL の末尾判定が文字列の `endswith`) | 直した | URI として読み query か fragment を持つものを拒む、M2-query 赤 (訂正註 5 の 2) |
| レビュー WP-3 A・3 / B・8 (`ProblemResponse` の文に応答の `code` がそのまま入る) | 直した ((b)) | `errors.codes` が列挙するときだけ文に、M3 赤 (訂正註 5 の 3) |
| レビュー WP-3 A・4 / B・2 (静的 pin の (iii) と docstring の免除が位置だけで効く) | 直した | 文の部品に限り `.args`・`.__doc__` を赤、RA-3・RB1a・RB1b 赤 (訂正註 5 の 4) |
| レビュー WP-3 A・5 / B・7 (`Content-Type` が複数の応答) | 直した (fail closed) | 解釈しない失敗、RB5・M5-first 赤 (訂正註 5 の 5) |
| レビュー WP-3 A・6 (JSON の端: NaN / Infinity、深いネスト) | 直した | M6-request・M6-constant・M6-recursion 赤 (訂正註 5 の 6) |
| レビュー WP-3 B・1 (完了条件 73 のガードが control.* を除く) | 直した (案 1) | 全項 (alias を除く) に広げ、完了条件 73 を読み替えた。control 側だけの keyword は 0 件で変異は作れない (訂正註 5 の 7) |
| レビュー WP-3 B・3 (4xx の `media_type` の応答を成功として読む場面が無い) | 直した | RB2 赤 (訂正註 5 の 8) |
| レビュー WP-3 B・4 (N-15 の `localhost`) | 直した (外す) | 設計 §4.1 の N-15 に無い、M9 赤 (訂正註 5 の 9) |
| レビュー WP-3 B・5・B・6 (段 (1) の応答検証、`ContractMismatch` の扱い) | 直した | RB3 は赤で固定済み。`ContractMismatch` を解釈しない失敗の側として受け入れ、`role` の無い文書の場面、RB4 赤。設計 v0.7 の D-7 の註 (訂正註 5 の 10) |
| 再確認 WP-3・1 (`str(e)`・名前の `__doc__`・`inspect` の持ち出し経路) | 直した ((a)) | import の閉じた表、例外の束縛と名前の `__doc__` を赤、R2-1-* 赤 (訂正註 6 の 2) |
| 再確認 WP-3・2 ((iii) の免除が構築の全位置引数に掛かる) | 直した | 位置引数 1 つか `message=` だけ、R2-2-* 赤 (訂正註 6 の 2) |
| レビュー WP-4 A・1 / B・1 (test module の pin が port の他の操作の経路と `adapter_name` の分岐を取りこぼす、RA4-1〜3・RB4-1〜3 緑) | 直した (差し戻し 1) | 6 形を赤にし planted と変異で固定 (訂正註 6 の 3) |
| レビュー WP-4 A・2 / B・6 (段 (11) が復唱句の key を位置で引く) | 直した (差し戻し 1) | `required_confirmation` の名前で引く (訂正註 6 の 3) |
| レビュー WP-4 B・2 (C-35 の Status の変異の要約が実測より広い) | 直した (差し戻し 1) | 測った plug を名指す (訂正註 6 の 3) |
| レビュー WP-4 B・3 (C-19 の Status から削った 2 句の記録先) | 直した (差し戻し 1) | `conformance-tests/CONDITIONS_HISTORY.md` の `## C-19` へ (訂正註 6 の 3) |
| レビュー WP-4 B・4 (#12 (b) の Evidence の置き場、実装は SI-03) | 直した (裁定 = SI-06) | `security/CONTROL_MAPPING.md` の SI-06 Common。設計 v0.7 の §7 の註 (訂正註 6 の 3) |
| レビュー WP-4 B・5 (改名後の test 名が見る範囲より広い) | 直した (差し戻し 1) | `test_c19_data_documents_declare_a_role` (訂正註 6 の 3) |
| レビュー WP-4 B・7 (観察: turn 末尾の media type の比較が送信ごとの検査と重複) | 直した (差し戻し 1) | 外し、段ごとの成功応答 1 件以上の assert を残す (訂正註 6 の 3) |
| 再確認 WP-4 | 〈監督が埋める: 再確認の指摘と裁定 (1 件 1 行)〉 | 〈監督が埋める〉 |
| 受け入れ監査 | 〈監督が埋める: 監査の指摘・観察と裁定 (1 件 1 行)〉 | 〈監督が埋める〉 |
