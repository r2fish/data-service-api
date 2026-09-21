# 引き継ぎ — 2026-09-22 (R-66 を閉じた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260921_FABLE3.md` で、**同書の §4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。

## 1. 現在地

- ローカルの main は R-66 の統合に本書のコミットを足したもの。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。
- 最後の root gate は R-66 の最終の木で `3844 passed, 2 subtests passed`、`judge=PASS`、実行クラスタ差分 0。`tools/` は触っていない。
- 進行中のサブエージェントは無い。未コミットの作業は無い。`security/CONTROL_MAPPING.md` は版 **2.20**、台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` v1.86。

## 2. 本チャットで閉じたもの

| 項目 | 要点 |
|---|---|
| R-66 (A) r2db-api の配備 script が `0013` を流さない | 台帳の「取りこぼし」より重かった: F-16 は両 process の起動時 fail-fast にも入っており、`0013` 抜きの初期 `CONNECTION LIMIT` は固定の `concurrency` 32 の床を全て下回るので、**script だけで配備した新規ホストは data-plane も control-plane も起動できなかった**。script が `0007` の直後に `0013` を流し、`0002` の直後に新規の `part1a_check_max_connections.sh` が `max_connections − superuser_reserved_connections ≥ 98 + 72 × (登録済み application 数 + 1)` (または `R2DBSVC_EXPECTED_PEAK_CONNECTIONS`) を検証して足りなければ refuse する。静的テストが script の migration 一覧・順序・literal・確認の段の位置を固定する (次の migration の足し忘れで赤) |
| R-66 (B) control / provision 役に role 水準の `statement_timeout` が無い | **置かないと確定した** (長時間の DDL が部分適用で終わる / role 設定はファイルごとにできない / client から到達できない)。有界にするのは呼び出し単位の lock の取得待ちで、取得後の保持は意図して無界。r2db-api の `ops upgrade-applications` に MitateDB と同形の必須 `--lock-timeout` を足した (ヘルパ 3 本を同名で写し、`_ISOMORPHIC_TARGETS` は両 peer 140 → 143)。MitateDB-api のコードは触っていない。版 2.20 が SI-08 の 3 ブロックで開示する |

- 作業指示書 `docs/work-orders/WORK_ORDER_R66_DEPLOY_0013_AND_PROVISION_ROLE_TIMEOUT_V1.md` (§6 に訂正註・監督裁定・実施と受け入れ)。設計レビュー 1、コードレビュー 2、受け入れ監査 1。
- **起票**: R-90 (r2db-api に `ops apply-platform-migration` / `ops deprovision` が無く、手で流す migration の `lock_timeout` を強制するものが無い)、R-91 (`max_connections` を起動時にも verify にも検査しない。両 peer)、R-92 (F-12 の案内文が `--lock-timeout` を含まない。両 peer)、R-93 (`0005` のヘッダの `R2DB_PLATFORM_POOL_SIZE` 既定の陳腐化)。

## 3. 次の一手

1. **R-67**、**R-69**。その後 R-72〜R-74、R-87〜R-93、別チャットの起票 R-75〜R-86 (順序と保留は台帳の各行)。
2. worktree `.claude/worktrees/r66-deploy-0013` (branch `r66-deploy-0013`) は本チャットの開始時に在った中身の無い残骸で、依頼者が「別チャットは無い」と確認した。`tools/dev/fold.py` の次回の畳み込みで `.claude/worktrees/r66` と併せて畳む。
3. push の再開は依頼者の指示による。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(m) R-66 の決定の事後報告と確認。** Class D で、決定 (作業指示書 §1 の D-1〜D-9、§6.2 の裁定、`security/CONTROL_MAPPING.md` 2.20 の確定文) は依頼者指示 2026-09-19 の委任の下で監督が下した。要点は 2 つ: control / provision 役に role 水準の `statement_timeout` を置かないこと、配備 script が `max_connections` の不足で refuse すること (既定の必要数は安全側の代用で、実数は `R2DBSVC_EXPECTED_PEAK_CONNECTIONS` で渡す)。
- **(n) 運用者に見える CLI が 1 点変わった。** r2db-api の `python -m r2db_api.ops upgrade-applications` は `--lock-timeout <value>` が必須になった (`--dry-run` でも。欠くと終了コード 2)。未実施の配備手順 `docs/work-orders/DEPLOY_Q4_20260905.md` の (f) には訂正註を足してある。**本番 (VPS) では変更後の script を流していない。**

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

- **台帳の「取りこぼし」は帰結まで読む。** `0013` の欠落は `ops verify-declarations` の FAIL ではなく起動不能だった。起動時 fail-fast に入っている検査かどうかを composition root で確かめる。
- **shell script を pytest から `bash <script>` で起動すると実行権の欠落が見えない。** 本体と同じ形 (直接起動) で起動する。新規 script は `ls -l` と、commit 後の `git ls-files -s` の mode を見る。
- **`${VAR:-}` は空文字を unset と同一視する。** 「空は拒否」を要件にした変数は `${VAR+x}` で判定する。空の override が既定値に落ちるのは fail-open である。
- **名前に件数を持つテスト (`…_140_rows`) を `security/CONTROL_MAPPING.md` が引いていると、件数が動く変更は必ず Update convention の訂正を伴う。** 着手時に `grep` で引用の有無を見る。
- **監督が WP を直接行うとレビュー 1 段が抜け、監査で証拠不足として出る。** 行うなら、その WP の道具 (split 検査、変異) を自分で回して逐語で残すところまでを同じ手で済ませる。
- **数値の assert は、同じ出力の中の別の数値の部分文字列にならない形で書く** (`"7"` は `72` に一致する)。文脈ごと assert する。
