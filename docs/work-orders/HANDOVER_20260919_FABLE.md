# 引き継ぎ — 2026-09-19 (R-53・R-51・R-50 を閉じ、R-52 の実装 WP を受け入れた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260918_FABLE.md` (同書の §5 の 1 項目め、および `docs/work-orders/HANDOVER_20260917_FABLE.md` の §5・§6 は引き続き有効)。前のチャットの scratchpad は読めないので、要るものは本書とリポジトリにだけある。監督のモデルは Fable (`OPERATING_CONDITIONS.md` §1.1 の 1)。

## 1. 現在地

- **リポジトリは作業機の `~/dev/data-service-api` に在る** (2026-09-18 に Google Drive の同期フォルダから移した。旧パスは無い)。移転後に初めて pytest を回す worktree は、先に `__pycache__` を消す (古い `.pyc` が旧パスを持ち、`inspect.getsource` を使うテストが落ちる)。本チャットが作った worktree は移転後のものなので該当しない。
- ローカルの main は `a661370` に本書のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-52 WP-3 の木 (main へ早送り済み) で `3733 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。以後 main に入ったのは文書だけ。`tools/tests` は `507 passed`。
- 進行中のサブエージェントは無い。未コミットの作業は無い。

## 2. 本チャットで閉じたもの

| 項目 | main | 要点 |
|---|---|---|
| R-53 (`ops.py` の help 文 3 点) | `cad71ad`、記録 `04c62b4` | help の列挙を `_PLATFORM_MIGRATION_FILENAMES` から導く形にした。`docs/work-orders/WORK_ORDER_R53_OPS_HELP_TEXT_V1.md`。残りは R-55 (同じファイルのコメント・docstring の旧文言) |
| R-51 (MitateDB の監査クエリの reader 例外) | `c041438`、記録 `8d54b90` | 台帳の「汎用の 500」は不正確だった (応答は元から 503 `SERVICE_UNAVAILABLE`)。`AuditReaderUnavailable` を足し、reader を 2 段の分類にした。実 PostgreSQL で `QueryCanceled` を起こすテスト。`docs/work-orders/WORK_ORDER_R51_AUDIT_QUERY_READER_ERRORS_V1.md` |
| R-52 (rollout 中の role `CONNECTION LIMIT`) の WP-1〜WP-4 | `11c98a2` (0014)・`da75ee2` (runbook)・`96fda8c` (§10.8 の再受理)・`dccceeb` (`security/CONTROL_MAPPING.md` 版 2.9)、受け入れ `a661370` | 依頼者裁定 (2026-09-18、逐語は `docs/design/MITATEDB_ROLLOUT_CONNECTION_LIMITS_V0_1.md` §10.1): 新しい migration `0014` で 132 / 36 / 68 / 12 (api / controlplane / application role / auditreader)、並走は 2 に固定、F-16 の床は 1 process 分のまま、`max_connections` が足りない場合の方針は本番の読み取りの後。runbook §10 は版 3 / 3 / 6 で再受理 (机上通し 10 状態、テストは実行していない)。受け入れ監査 1 回、監督裁定 A-1〜A-5 (`docs/work-orders/WORK_ORDER_R52_ROLLOUT_CONNECTION_LIMITS_V1.md` §11)。**本番には何も適用していない。台帳の R-52 行は閉じていない** (§4) |
| R-50 (`security/CONTROL_MAPPING.md` の複数ブロック化) | `e0d2cb5` (検査と照合スクリプト)・`bd17175` (版 2.7)・`d2e7333` (版 2.8)・`06b8871` (記録)、受け入れ `4fbc746` | 依頼者裁定 (2026-09-18、選択肢の逐語):「複数ブロックを許す」。1 つの (SI, peer) は既定の小ブロック 1 つ + 名前付き 3 つまで。`tools/check_control_mapping_split.py` が版をまたぐ移動を 4 つ組で照合する。設計 `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` v1.0、作業指示書 `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md` (§13 に受け入れ監査と裁定)。閉じた |
| 起票 | 同上 | roadmap `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.68 の R-55 (`ops.py` のコメントの旧文言)、R-56 (r2db-api の auditreader に `statement_timeout` が無い)、R-57 (`apply-platform-migration` が単独再適用の順序を守らせない。`0012` に「存在しない role を飛ばす」防御が無い件もここ)、R-58 (`tools/testpg/dsa_testpg.py` が同じ process の `PGPASSWORD` を消し、conformance と `tools/tests` の結合実行が teardown で 1 error)、R-59 (SI-09 / MitateDB-api の既定の小ブロックが 13,745 / 15,200 字)。いずれも起票のみ |

## 3. 次の一手

1. **台帳の順**: R-54 (runbook §9 の `GRANT pg_signal_backend` の出所) が次。小さい。その後は R-55〜R-59 のどれも小さく、R-59 は R-50 の道具 (`tools/check_control_mapping_split.py`、純粋な移動) でそのまま解ける。
2. **依頼者の指示を待つもの**: R-49 の着手 (mutation class)、本番を読む経路の受け入れ、`0014` の本番への適用 (runbook §10 の手順)。本番の読み取りの後に R-52 の Q-4 を伺う。
3. push の再開は依頼者の指示による。再開したら main の先頭で CI の run を 1 回取る (`OPERATING_CONDITIONS.md` §2 の 20)。docs-only でないコミットが多数たまっているので、最初の run の結果を必ず読む。

## 4. 依頼者判断待ち・未決

- **R-52 の残り 2 件 (行を開けてある理由)**: (i) r2db-api の配備が 2 つの process を並走させうるかは未確認 (`security/CONTROL_MAPPING.md` の SI-08 / MitateDB-api が「ledger item R-52, still open」と開示)。読み取りだけで確かめられるので、次のチャットで explorer に調べさせてよい。(ii) Q-4: `max_connections` が条件 2 (rollout 時の合計 234 + reserved) に足りない場合の方針。**この合計は application の件数と runtime / developer の別に比例する物理的な worst case を数えない** (R-45 の裁定 Z-27 の下の計算値)。application が複数ある本番では実需要がこれより大きい — Q-4 を伺うときに必ず添える。
- **R-45 から続くもの**: 本番を読む経路の受け入れ。`0014` を当てる前の本番の Gate-0 の初回の読みは (8) が blocked になる (api 68 < 128)。runbook §10.10.1 は、これを step 7 が直すと明示している。

## 5. 並行セッションと worktree

- Mitate の監督セッションの中継は依頼者の回答として扱わない (前書のとおり)。R-52 の完了 (F9 の阻害要因だった `operation_depth` の platform upgrade の前提が 1 つ進んだ) は Mitate 側へまだ報告していない — 依頼者に確認してから送る。
- 本チャットが作り、統合済みで未コミット 0 の worktree (13 本): `r53-ops-help`・`r51-audit-query`・`r52-design`・`r52-wp1`・`r52-wp2`・`r52-wp3`・`r52-wp4`・`r50-design`・`r50-wp1`・`r50-wp2`・`r50-wp3`・`r50-wp4`・`r50-accept`。前書の 6 本と合わせ、削除は依頼者が行う (区切りで扱いを聞く)。

## 6. 本チャットで足した運用上の教訓

- **`tools/dev/mutate.py` は expect=red の実行に `-x` を付ける。** 1 つの変異の `tests` に複数のテストを並べると先頭の失敗で打ち切られ、後ろのテストは一度も走らないまま「as expected」になる (R-51 で実 PostgreSQL のテストが空振りしていた)。示したいテストごとに変異の項目を分ける。発注に必ず書く。
- **応答の面で区別できない性質は、変異を 2 edit にして示す。** R-51 の HTTP の no-leak テストは、message が定数から組まれるのでどの単独の変異でも赤にならなかった。
- **監督の枠の誤りは実装担当の疑義で見つかる。** R-51 で監督が指定した例外の型は現物の docstring と合わなかった。発注に「疑義は実装せず報告に書く」を入れ、疑義は裁定の材料として読む。
- **基点の古い worktree は、統合の前に main へ早送りする。** 記録が引く台帳の ID がその worktree の roadmap にまだ無く、`check_doc_refs` が赤になった (R-52 WP-1)。`git merge --ff-only main` は未コミットの変更が重ならなければそのまま通る。
- **他文書を `file:line` で引く訂正註は、註自身の挿入で行番号がずれる。** R-50 で 3 回起きた。引用先が動く文書 (`security/CONTROL_MAPPING.md`) を引くときは、行番号に加えて**行番号に頼らない所在** (節 → 小節 → 軸 → 書き出し) を 1 回書き、以後ずれのたびに註を足さない。
- **受け入れ監査のパケットを作業指示書へ写すとき、作業機の一時ディレクトリ名 (`dev-logs-xxxx`) が公開値スキャンの project id の規則に掛かる。** 監査の発注に「絶対パスと一時ディレクトリ名を書かない」を入れる。
- **受け入れ監査で毎回出る記録の欠落は「完了条件 → 変異 → 赤になった test id」の対応表。** 変異の id の写しだけでは足りない。統合の記録に、実装報告の対応表をそのまま写す。
- **`pt.py` で `conformance-tests/` のファイルと `tools/tests` を 1 回に結合しない** (R-58)。2 回に分ける。
- **`security/CONTROL_MAPPING.md` に主張を足す WP は、足した後の各ブロックの字数を測り、残りが 2,000 字を切ったら同じ変更の中で報告させる** (R-59 はこうして見つかった)。
- **登録簿に書く断言は「名指しの role・ファイル・件数」まで現物に当てる。** 「every existing role」のような全称は、`0012` が auditreader を触らないような例外で偽になる。レビューの発注に「全称の語を現物で 1 つずつ確かめる」を入れると効く。
