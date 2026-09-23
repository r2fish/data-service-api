# 引き継ぎ — 2026-09-24 (R-79 を閉じ、R-80 の計測器と実測を入れた。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/work-orders/HANDOVER_20260923_FABLE5.md` で、**同書の §3・§4・§5 と、そこが引く前々書までの §4・§5 は引き続き有効**である (本書の §4・§5 は追加だけを書く)。前々書は本書の変更セットで記録へ移したので `docs/archive/docs/work-orders/HANDOVER_20260923_FABLE4.md` で読む (`OPERATING_CONDITIONS.md` §1.16 の 78、`docs/archive/README.md`)。前のチャットの scratchpad は読めない。監督のモデルは Fable。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。

## 1. 現在地

- ローカルの main は **`d718100`** (R-80 の merge)。本チャットの merge は **`fc891cb`** (R-79 WP-1、計測器)、**`c589785`** (R-79 WP-3 + 閉止、台帳 v1.110)、**`d718100`** (R-80 WP-1+WP-2、台帳 v1.112) で、いずれも main の祖先。間の `v1.111` は別チャット (正本と記録の分離) である。
- 最後の root gate は R-80 の木で `4018 passed, 2 subtests passed in 438.42s`、**`judge=PASS`**、`pg_database` / `pg_roles` の差分 0。`tools/tests` は **638 本** (root suite は `tools/tests` を含まないので、R-79 WP-3 の 4018 と同数である)。
- `security/CONTROL_MAPPING.md` は版 **2.25** (本チャットは触っていない)、台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` は **v1.112**。
- **進行中: 無し。** branch `r79` (統合済み) と `r80` (統合済み) は本チャットのセッション worktree の上で checkout して使ったもので、別 worktree は作っていない。畳む対象はローカルブランチだけである。
- 本書の変更セットでは、規律 78 の同時移動として (1) 最新 2 通から外れる前々書を `docs/archive/docs/work-orders/` へ、(2) 版数ログの 6 版目 (`v1.107`) を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ、それぞれ `git mv` / 逐語の移動で行った。**台帳の版数は上げていない** (記録の移動だけ)。

## 2. 本チャットで閉じたもの

| 項目 | 要点 |
|---|---|
| **R-79 prepared statement が効いているかの実測 (Class B、閉止)** | **WP-1 (計測器)**: 両 peer に byte 一致の `psycopg_counting.py` (`CountingCursor` / `CountingConnection` / probe) と `prepared_stats()`、harness に `PREPARED` / `PREPSTMT` 行と `--prepared-detail` (main `fc891cb`、gate `4012 passed, 2 subtests passed` / `judge=PASS`)。**WP-2 (実測)**: **r2db は全接続・全 op で `prepared=0`** — `_RolePool._liveness_check` が貸し出しのたびに `SELECT 1` を開いた transaction を `rollback()` で閉じ、psycopg がそこで client 側の prepared 表を消していた。**MitateDB は持続接続 2 本で `share` 0.91〜0.998** で効いており、deadline 由来の `SET LOCAL` の値も K=1 で 3 種・K=4 で 12 種に収まって自身が prepared になる (起草時の F1 の「毎回新しい鍵」は成立しない)。**WP-3 (採用形 (D))**: r2db の liveness ping を `autocommit=True` の下で 1 往復にし (非 IDLE なら事前 `rollback()`、`finally` で戻す)、来歴 CH-0541 (main `c589785`、gate **`4018 passed, 2 subtests passed`** / `judge=PASS`)。再計測で r2db の runtime 接続は `prepared` 6〜8・`share` 0.95〜0.98 になり、基点の道具と交互に取った非退行で **r2db-http の p50 が K=1 で −49〜−52% (3.44 → 1.66 ms)**、r2db-socket −26〜−44%。変異 M1〜M32 全件 `expect=red got=red`。設計レビュー 1 回・コードレビュー 2 回 (WP-1 で差し戻し 1)・受け入れ監査 2 回。記録は `docs/design/PERF_PREPARED_STATEMENT_MEASUREMENT_V0_1.md` v0.3 と作業指示書 §6、台帳 **v1.110** |
| **R-80 1 要求あたりの DB 往復の実測 (Class B、open)** | **WP-1 (計測器)**: harness の `--roundtrip` と `ROUNDTRIP` 行 (接続ごとの文/要求、DB ごとの transaction/要求と session/要求)。`pg_stat_database` は idle backend の統計を約 10 秒遅れて flush するので、**最短 12 秒待ってから 1 秒ごとに 3 回連続不動で確定 (上限 30 秒、超えたら `stale=1`)** とした。変異 M1〜M27 全件赤、`tools/tests` 638 本、設計レビュー 1 回・コードレビュー 1 回 (差し戻し 1)、受け入れ監査は省略 (Class B・規模 M、`OPERATING_CONDITIONS.md` §1.13 の 74)。gate `4018 passed, 2 subtests passed in 438.42s` / `judge=PASS`。**WP-2 (実測、K=1)**: r2db runtime = **6 / 7 / 11 文/要求** (query / mutate / batch)、app DB **2 transaction**、**platform DB 8 transaction** (pool 経由、session 0)。MitateDB developer = **16 / 8 / 40 文** (catalog 読みが 5 / 2 / 10 transaction)、app DB 5 / 3 / 11 transaction、platform DB 4 transaction + **session 2 本/要求** — 後者は harness の plug が認証 store に pool を渡さない配線 (`pool=None`) によるもので **production の値ではない**。**判断**: pipeline 化 (WP-2 修正) は R-82 の後に残る独立区間に対して行う (r2db の独立区間 5〜8 往復のうち catalog 2 文、MitateDB の 25 往復はいずれも R-82 が消す対象で、先に pipeline を入れると作り直しになる)。**行は open のまま**追記した。記録は `docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` v0.2 と作業指示書 §6、台帳 **v1.112** |

## 3. 次の一手

1. **依頼者裁定を待つ (§4 の (t))。** 台帳は着手順を R-80 → R-81 → R-82 で固定しているが、監督の推奨は **R-82 先行**で、その後に R-80 の pipeline WP と R-79 の申し送り (B) (`SET LOCAL` 2 文 → `set_config` 1 文) を置く。**裁定が出るまで R-81 / R-82 に着手しない** — R-81 は harness の mutate に idempotency key を送る op を足すのが先であり、R-82 が先なら順序が変わる。
2. 裁定の後: R-82 (または R-81) → R-80 WP-2 (pipeline) → R-85 → R-86 → R-96〜R-102。**R-83** (API キー検証結果のキャッシュ) は、R-80 が測った platform DB の transaction/要求 (r2db 8、MitateDB 4) が判断材料になる。
3. **fold**: `tools/dev/fold.py --min-age-hours 0` を dry-run で走らせ、`r79` / `r80` の**ローカルブランチ**が対象に出ることを見てから `--apply`。他チャットの worktree は lock で保護される。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- **(t) 着手順。** R-82 を R-80 の pipeline WP より先に置くか。両論 ((甲) 台帳の順のまま / (乙) R-82 先行) は `docs/design/PERF_ROUNDTRIP_MEASUREMENT_V0_1.md` §4 に在る。監督の推奨は (乙)。
- **(u) harness の代表性。** conformance / perf の plug は認証 store に pool を渡さず (`pool=None`)、production の composition root とは接続の持ち方が違う (MitateDB で要求ごとに session 2 本)。計測の代表性の問題として、plug の配線を production に寄せるかどうか。寄せるときは `pool=None` にした理由 (R-78 §1.3 の (5) = 逐次 adapter で idle 接続が cluster の `max_connections` を圧迫した) と釣り合わせる必要がある。
- **(v) R-79 の Class B の決定の事後確認。** r2db の liveness ping を transaction の外に出した。挙動の変化: 非 IDLE で戻ってきた接続は ping の前に `rollback()` し、基点では捨てていた **INERROR の接続も再利用する**。
- **(w) R-79 の申し送り。** 例外で終わる要求の接続は `conn.transaction()` 自身の rollback で prepared を失う (psycopg の機構)。エラー率が高い運用では再 prepare のコストが残るが、本件では扱っていない。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

1. **性能の非退行は、基点の道具と本 worktree の道具を交互に取る。** 別々の時刻に取った run は別チャットの負荷で一様に +30〜77% ずれ、psycopg に触れない in-process の行まで遅くなった。また **K=3 はこの環境では ±10% に収束しない** (同じ行の符号が run ごとに反転し、基点同士でも 8〜10% 動く) ので、判定は **K=1** で行う。
2. **`pg_stat_database` は idle backend の統計を約 10 秒遅れて flush する。** 「値が動かない」は確定の証拠にならない (20 秒不動の後に +102 が現れた実測がある)。最短待ちを置いてから不動を数える。
3. **stub の名前は実物と同じ形にする。** poll が実 DB 名で返し emit が論理名で引く不整合を、両方に同じ名前 (`"app"`) を使い回した stub が隠し、単体テストは緑のまま `db=` 行が 1 本も出なかった。実機確認で見つかった。
4. **サブエージェントの worktree 割り当て。** 監督が `git worktree add` で作った別 worktree への Write はフックで拒まれる。WP のブランチはセッションの worktree で checkout し、プロンプトに「Primary working directory がその worktree である」と書く。
5. **台帳の版数行は他チャットと衝突する** (本チャットで 2 回)。マージのときは自分の行を +1 して**両方残す**。
6. **来歴検査の対象は両 peer の `src/` だけである** (`docs/design/CODE_COMMENT_PROVENANCE_V1.md` §3)。`tools/` に出る §4.1 (2) の行は対象外で、CH-ID も登録しない。
7. **新規テストファイルの `tools/tests` の件数 pin と、`_BACKEND_LAYER_ALLOWLIST` / `test_l1_details_vocabulary_ast_scan.py` の行番号 pin は、監督の最終修正 (コメント削除・docstring 追加) でもずれる。** finalize の前に該当テストを回す (R-79 の完了ゲート 1 回目が赤 3 件)。
8. **psycopg の `Connection.rollback()` と `Transaction` の rollback は prepared 表を消す** (`DEALLOCATE ALL` を送る)。成功経路に rollback を置かない。
9. **`tools/perf_baseline.py` は gate intent が在る間 exit 75 で拒む。** 背景ジョブで intent の消滅を待ってから回す (迂回しない)。
10. **起草時に枠の事実を現物で測り直したこと (`OPERATING_CONDITIONS.md` §1.5 の 34) が、枠の誤りを 2 度捕まえた** (F1 の MitateDB 部分、統計の flush の遅れ)。枠に書いた事実には「起草者が現物で確かめる」を必ず付ける。

## 6. 裁定 (`OPERATING_CONDITIONS.md` §1.15 の 77)

- 本チャットの指摘・観察の裁定は、`docs/work-orders/WORK_ORDER_R79_PREPARED_STATEMENT_MEASUREMENT_V1.md` §6.1 と `docs/work-orders/WORK_ORDER_R80_ROUNDTRIP_MEASUREMENT_V1.md` §6.1 に逐語で在る (起草時・設計レビュー・実装中・受け入れ監査の別で全件)。大半は同じ変更セットで直した。
- 同じ変更セットで直さずに残したもの: (1) R-79 の受け入れ監査の設計疑義 — 例外で終わる要求の接続は `conn.transaction()` の rollback で prepared を失う。WP-3 の範囲外の事実として設計メモ §3 の (ix) と本書 §4 の (w) に置いた。 **裁定: 観察 (起票しない)** — psycopg の機構であり両 peer の設計判断ではない。エラー率の高い運用で再 prepare のコストが問題になったときに R-83 系の計測で拾う。(2) R-80 の設計レビューの観察 (`backend_postgres.py` の行番号) — 起草者が現物で数え直し、指摘の行番号は当たらないので本文は変えていない。 **裁定: 観察 (起票しない)** — 指摘が当たらないことを現物で確認済み。

- 監督チャットは区切りに達したので、次は新しいチャットで本書から始める (`OPERATING_CONDITIONS.md` §1.10 の 67)。
