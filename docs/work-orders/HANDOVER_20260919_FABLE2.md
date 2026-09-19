# 引き継ぎ — 2026-09-19 その 2 (R-54 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260919_FABLE.md` で、**同書の §4 (依頼者判断待ち・未決) と §5 (並行セッションと worktree) は引き続き有効**である (本書の §4・§5 はそこへの追加のみを書く)。前のチャットの scratchpad は読めないので、要るものは本書とリポジトリにだけある。監督のモデルは Fable (`OPERATING_CONDITIONS.md` §1.1 の 1)。

## 1. 現在地

- ローカルの main は `a586a17` に本書と記録のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-54 の木 (main へ早送り済み) で `3745 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/tests` は `507 passed`。
- 進行中のサブエージェントは無い。未コミットの作業は無い。

## 2. 本チャットで閉じたもの

| 項目 | main | 要点 |
|---|---|---|
| R-54 (生きた接続の前の deprovision) | `a586a17` (作業 `42ebc2c`)、記録は本書のコミット | 起票は「runbook §9 の `GRANT pg_signal_backend` の出所が読めない」だったが、実測で**それより深い問題**だった: 自己付与は ADMIN option が無く拒否 (M-1)、他者が素の GRANT をしても `NOINHERIT` で効かない (M-3)、効かせても `backend_type` が見えず `0004` の terminate は **0 行**に一致 (M-5)、結果として生きた接続が 1 本あると deprovision は落ちる (M-6)。テストはリトライで通っていただけだった。**`0004` 自体を直した** (設計 D-2R): 事前検査 → その application の role への一時付与 (`WITH INHERIT TRUE, SET FALSE`) → `ALLOW_CONNECTIONS false` → 既存の terminate → 素の `DROP`。cluster 全体の predefined role は使わない。設計メモ `docs/design/DEPROVISION_FORCED_DROP_V0_1.md` v1.0、作業指示書 `docs/work-orders/WORK_ORDER_R54_DEPROVISION_LIVE_CONNECTIONS_V1.md` (§5 に受け入れ監査・監督裁定 A-1〜A-8・最終判定)。`security/CONTROL_MAPPING.md` 版 2.10。**本番には何も適用していない。Cloud SQL での証拠は `absent`。** 台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.69 の R-54 行は**閉じた** |

- **依頼者の指示 (2026-09-19、逐語)**:「その方針で進めてください、完了まで行ってください、判断は推奨で進め後から報告してください。推奨は長期的な視点で製品価値のある判断にしてください。」この下で監督が推奨として裁定した主なものは次のとおり (根拠は設計メモと作業指示書 §5)。
  - **runbook の文言だけを直さず、`0004` 自体を直した。** 起票の範囲 (手順の文言) に留めると、本番の deprovision が生きた接続の前で落ちる欠陥がそのまま残るため。
  - **採用形は D-2R** (事前検査 + 一時付与 + `ALLOW_CONNECTIONS false`)。**`DROP DATABASE … WITH (FORCE)` は不採用** (M-11: autovacuum worker の前で止まり database が残る)。**`pg_signal_backend` / `pg_read_all_stats` を常設で持たせる案も不採用** (cluster 全体に効く権限を常設にしないため。設計 §8 の X-1)。
  - **変更クラスは C**、両 peer に同名の共有テストヘルパを置かず peer ごとに直書き (`_ISOMORPHIC_TARGETS` を増減しない)。**独立設計レビューは 2 回**。
  - **`security/CONTROL_MAPPING.md` の主張は SI-00 の両 peer の既定の小ブロック**に置き、証拠は `absent` と正直に書いた。
  - **runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §10.7 の表は版 4 のまま再受理した** (版 4 は未コミットのまま差し戻し 1 回を経て確定したので、往復を 1 回の変更として扱う)。受理記録の本文は作業指示書 §5.8.1。
  - **事前検査の例外はリトライしない** (「持ち主が閉じてから再実行する」という指示が通じる失敗なので、リトライで隠さない)。

## 3. 次の一手

1. **台帳の順**: R-55 (`ops.py` のコメント・docstring の旧文言)、R-56 (r2db-api の auditreader に `statement_timeout` が無い)、R-57 (`apply-platform-migration` の単独再適用の順序)、R-58 (`tools/testpg/dsa_testpg.py` が `PGPASSWORD` を消す)、R-59 (`security/CONTROL_MAPPING.md` の分割)。**どれも小さい。R-59 は残り 971 字になったので優先を上げてよい** (次に同ブロックへ追記する WP が入らない)。
2. **依頼者の指示を待つもの** (前書 §3 の 2 と同じ): R-49 の着手 (mutation class)、本番を読む経路の受け入れ、`0014` の本番への適用 (runbook §10 の手順)。本番の読み取りの後に R-52 の Q-4 を伺う。
3. push の再開は依頼者の指示による。再開したら main の先頭で CI の run を 1 回取る (`OPERATING_CONDITIONS.md` §2 の 20)。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **本番の Cloud SQL で runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` §9 の新しい項目 3 を実測する機会** — 使い捨ての application に対して、接続を開けたまま deprovision して `0004` が 1 回で通ることを確かめる。Cloud SQL 自身の管理接続が事前検査に掛かるかもここで分かる (現状 `absent`)。**operator の作業なので依頼者の指示を待つ。**
- **2026-09-01 に付与された `pg_signal_backend` の membership は不要で、`REVOKE` してよい** (M-3 のとおり効果を持たず、D-2R はこれを使わない)。実行するのは bootstrap の `postgres` である (runbook §9.1 の訂正註)。**operator の作業なので依頼者の指示を待つ。**
- **Mitate への報告 (R-52 と R-54)** は依頼者に確認してから送る。

## 5. worktree (前書 §5 に足すもの)

- 本チャットが作り、統合済みで未コミット 0 の worktree は 1 本: `r54-signal-backend`。前書の 13 本、およびその前の 6 本と合わせ、**削除は依頼者が行う** (区切りで扱いを聞く)。

## 6. 本チャットで足した運用上の教訓

- **台帳の「小さい」は現物の実測で確かめる。** R-54 は runbook の文言の件として起票されたが、実測すると `0004` が本番の role では黙って無効だった。
- **PostgreSQL の権限は、role の `NOINHERIT` と `pg_stat_activity` の可視性まで実測する。** 付与が「成功」しても効かないことがある。
- **テストのリトライは欠陥を隠す。** 直す変更セットには「リトライなしで 1 回」のテストを必ず置く。
- **レビュー担当への発注に「結果をファイルに書く」を必ず明記し、差し戻しの前に監督がファイルの存在を確かめる。** 本チャットではこれを欠いて実装担当が 50 分待った。
- **同じ worktree で文書 WP とコード WP を並行させるときは、触るファイルを名指しで分け、commit は全員の完了後に 1 回。**
- **runbook の表が自分自身の版上げ規約を持つとき、未コミットの往復は 1 回の変更として扱い、その旨を受理記録に書く** (版を上げるのはコミットされた内容に対してだけ)。
- **出現箇所を数える文 (「この repository に X は 0 件」) は、自分自身で偽になる。** 数えない形 (「X に依存する手順・コード・設定は無い」) で書く。
