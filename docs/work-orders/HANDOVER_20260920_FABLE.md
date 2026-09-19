# 引き継ぎ — 2026-09-20 (R-59・R-55・R-56 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260919_FABLE2.md` で、**同書の §4 (依頼者判断待ち・未決) と §5 (worktree) は引き続き有効**であり、さらにその前書 `docs/work-orders/HANDOVER_20260919_FABLE.md` の **§4 も引き続き有効**である (本書の §4・§5 はそこへの追加のみを書く)。前のチャットの scratchpad は読めないので、要るものは本書とリポジトリにだけある。監督のモデルは Fable (`OPERATING_CONDITIONS.md` §1.1 の 1)。

## 1. 現在地

- ローカルの main は `623d47c` に docstring の 1 語の修正と本書・記録のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-56 の最終の木 (main へ早送り済み) で `3763 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` は `528 passed`。
- 進行中のサブエージェントは無い。未コミットの作業は無い。

## 2. 本チャットで閉じたもの (前書の後)

| 項目 | main | 要点 |
|---|---|---|
| R-59 (`security/CONTROL_MAPPING.md` の SI-09 / MitateDB-api の分割) | `44c2688` | SI-09 / MitateDB-api の既定の小ブロックから platform upgrade の主題を名前付き小ブロック `### MitateDB-api -- platform upgrade` へ**純粋な移動**で分けた (主張の文は 1 字も変えない)。`security/CONTROL_MAPPING.md` **版 2.11**。作業指示書 `docs/work-orders/WORK_ORDER_R59_SI09_MITATEDB_BLOCK_SPLIT_V1.md`。方法は `docs/design/CONTROL_MAPPING_MULTI_BLOCK_V0_1.md` v1.0 の 3 回目の適用。台帳の R-59 行は**閉じた** |
| R-55 (`MitateDB-api/src/mitatedb_api/ops.py` のコメント・docstring の旧文言) | `7ad7588` | 節見出しコメントと `cmd_apply_platform_migration` の docstring の該当の文を、help (R-53) と同じく「本番には runbook の gated な手順 (`docs/cloud-run-cloud-sql.md` §10) を通してのみ流す」を指す形に置き換えた。**3 条件 (isolated proof・independent audit・requester approval) は失効していない** — runbook §10.10.1 が stage 2 の gate として今も挙げており、コードはそれを言い直すのをやめて**定める場所を指す**形にした (起票時の「作業期の文言」という捉え方が不正確だった。コードレビューの指摘)。旧文は `docs/code-history/MitateDB-api/ops.md` の CH-0538・CH-0539 へ訂正記録つきで移した。台帳の R-55 行は**閉じた** |
| R-56 (r2db-api の auditreader に `statement_timeout` が無い) | `623d47c` (作業 `bb0caa3`・`b10f4a0`)、記録は本書のコミット | 実測では**取り残しであって意図した差ではなかった** (r2db-api は同じ安全上の結果を別の手段で満たしていない)。新しい platform migration `r2db-api/migrations/0014_auditreader_statement_timeout.sql` が `r2dbsvc_auditreader` に **role 水準の `statement_timeout = 5000ms`** を置く。role 設定は login 時に session へ複写されるので**適用の後に開いた接続から効く** (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §19 が「適用 → control process の再起動 → `ops verify-declarations`」の順序を定める)。宣言の有無は **`ops verify-declarations` の F-17 を両 peer に**置いて確かめ、**起動時検査にはしない**。`_ISOMORPHIC_TARGETS` 138 → 140、`security/CONTROL_MAPPING.md` **版 2.12**、**変更クラス D**。完了ゲート `3763 passed, 2 subtests passed`。設計メモ `docs/design/R2DB_AUDIT_READER_STATEMENT_TIMEOUT_V0_1.md` v1.0、作業指示書 `docs/work-orders/WORK_ORDER_R56_R2DB_AUDIT_READER_TIMEOUT_V1.md` (§5 に受け入れ監査・監督裁定 A-1〜A-11・最終判定)。**本番 (VPS) には何も適用していない** — 適用するまで `verify-declarations` は `FAIL F-17` (終了コード 16) を返すが、これは意図した信号である。台帳の R-56 行は**閉じた** |

- **起票**: 前書の期間の R-60・R-61 に加えて、本チャットで **R-62〜R-66** を起票した (台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.72 の §8。いずれも起票のみ)。R-62 = `PostgresCell.catalog` が取引ごとの timeout を通らない、R-63 = `tools/check_comment_provenance.py` が新しい関数の docstring を書けなくしている、R-64 = `CONTROL_MAPPING` の Evidence のテスト名を解決する機械検査が無い、R-65 = SI-08 の両既定ブロックの残り 2,272 / 2,177 字、R-66 = 配備 script が `0013` を流していない件と control / provision role の role 水準 timeout。

## 3. 次の一手

1. **台帳の順**: R-57 (`apply-platform-migration` の単独再適用の順序)、R-58 (`tools/testpg/dsa_testpg.py` が `PGPASSWORD` を消す)。
2. その後は **R-60 + R-61** (どちらも `security/CONTROL_MAPPING.md` の文の訂正で、**同じ変更セットにできる**)、**R-62** (小さいコード修正)、**R-65** (純粋な移動)、**R-63・R-64** (道具)、**R-66**。
3. **依頼者の指示を待つもの**は前書 (`docs/work-orders/HANDOVER_20260919_FABLE2.md` §3 の 2) と同じ。
4. push の再開は依頼者の指示による。再開したら main の先頭で CI の run を 1 回取る (`OPERATING_CONDITIONS.md` §2 の 20)。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(a) 変更クラスの事後確認。** R-54・R-59・R-56 はいずれも `security/` を触るので **Class D** であった。うち **R-54 と R-59 は監督が Class C と誤って宣言した** (両作業指示書 §0 に訂正註を足した。本文は書き換えていない)。**依頼者指示 2026-09-19 の委任** (逐語は前書 `docs/work-orders/HANDOVER_20260919_FABLE2.md` §2) が **Class D の決定にも及ぶことの事後確認**を伺う。及ばない場合は、3 件の決定 (各設計メモと作業指示書の監督裁定) を**依頼者裁定として改めて伺う**。
- **(b) r2db-api の本番 (VPS) への `0014` の適用と control process の再起動。** 手順は `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` §19 と `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`。**operator の作業なので依頼者の指示を待つ。** 適用するまで本番の `ops verify-declarations` は `FAIL F-17` (終了コード 16) を返す。

## 5. worktree (前書 §5 に足すもの)

- 本チャットが作り、統合済みで未コミット 0 の worktree は 4 本: `r54-signal-backend`・`r59-si09-split`・`r55-ops-comments`・`r56-r2db-reader-timeout`。前書までの分と合わせ、**削除は依頼者が行う** (区切りで扱いを聞く)。

## 6. 本チャットで足した運用上の教訓

- **`security/` を触る変更は Class D。** クラスを宣言する前に、触るパスを `tools/change_class.py` に流す (監督が 2 件で誤った)。
- **新しいファイルを足す WP は、`git add -N` した状態で `tools/tests` を回させる。** 未追跡の間は `git ls-files` の列挙に入らないので、件数 pin が統合の時まで赤にならない (R-56 で `finalize.py` が終了コード 76 で止めた)。
- **「役が無ければ該当なしで緑」の検査は、役の有無を観測できる DSN で試す。** レビューの「役は残して設定だけ消す」変異が、本番と別の DSN を使ったテストの空振りを見つけた。
- **実装報告の「設計が許容する形」という言い換えは、設計の確定文言と突き合わせる。** 確定文言を落とした言い換えが 1 件あった。
- **台帳の起票文の枠も現物で確かめる。** R-55 の「作業期の文言」という捉え方は不正確で、3 条件は失効していなかった。
- **純粋な移動でも、残った側の指示語と他文書の所在の註を見る** (R-59)。
