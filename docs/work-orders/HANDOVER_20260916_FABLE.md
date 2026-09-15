# 引き継ぎ — 2026-09-16 (R-37 WP-3 の完了、R-22 変更セット 0i、U-10 の揺れの原因特定。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` を読む。

## 1. 現在地

- ローカルの main は `c208089`。
- push は GitHub の請求上限のため停止中で (`docs/work-orders/OPERATING_CONDITIONS.md` §2 の 20)、ローカルの main だけを進めている。何も push していない。
- 最後の root gate は R-37 WP-3i の branch 上で `3406 passed, 2 subtests passed`、`judge=PASS`、pg_database / pg_roles の差分 0。以後 main に入れたのは文書だけである。
- 本チャットは main の checkout と WP ごとの worktree で作業した。引き継ぎ時点で残る作業ツリーは `ccp-cs0`、`r37-wp0`、`vigilant-knuth-82b8f3`、`role-agents`、`mitatedb-operation-depth-platform-plan`、`charming-liskov-ff9a96`、`clever-tereshkova-48b412`。後の 2 つは別セッションのものである。`ccp-cs0`、`r37-wp0`、`vigilant-knuth-82b8f3` は前のチャットのもので、触っていない。

## 2. 本チャットで閉じたもの

- **U-10 の揺れ** (前書 `docs/work-orders/HANDOVER_20260915_FABLE2.md` の次の一手 1。U-10 はフェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §5 の項目)。race ではない。原因を特定した。
  - `ApplicationCell._limit_gate` は、`read` が cell の lock を取る前に 5000 ms の期限を開始する。テストは要求 B をその lock の後ろで約 10 s 待たせていたので、`backend_postgres.py::_timeout_ms` が B を 1 ms の statement timeout に丸めていた。B が 200 を返すのは、文が 1 ms 以内に終わったときだけだった。
  - テストを直した (窓を予算の 1/5 にし、B が gate を通ったことを確かめてから開始し、monotonic clock で区切り、前提条件の assert を足した)。merge `f0637d9`。記録は設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.5 の【追記】。
- **R-42 の起票と依頼者裁定**。両 peer とも、予算を使い切った要求に対して 1 ms の timeout で文を発行するので、結果が機械の負荷で決まる。依頼者裁定 (逐語):「R-42はフェーズ11で」。roadmap v1.37、merge `bf2cc41`。
- **R-39 への追記** (前書の次の一手 4)。merge `d9bc30e`。
- **R-22 変更セット 0i**。チェッカーの保護参照の拡張と、統合済み 52 塊の戻し。`d9191fe` (merge `ffd6493`)、記録 `e93f527` (設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` v0.19 §10.6、作業指示書 `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` v1.13 §15、roadmap v1.40)。裁定 Z0i-1〜Z0i-7 と Z0i-4a〜Z0i-4h は同作業指示書 §15.5。
- **R-37 WP-3e / 3f / 3g / 3h / 3i**。これで WP-3 (3a〜3i) は完了した。
  - 3e `request_vocabulary.py` (`b4aac70`)
  - 3f `mutation_binding.py` (`6708ad9`)
  - 3g `schema_binding.py` (`8fa8884`)
  - 3h `capabilities_document.py` (`cab0ee9`)
  - 3i `request_binding.py` (`51718b9`)
  - 裁定 W3-15〜W3-23 は作業指示書 `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.39。記録は設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (v1.18) §10.11〜§10.15。
  - W3-18 で `tools/tests/test_comment_provenance.py::test_q4_real_repo_postgres_unchanged_is_green` を退役させた。同じ範囲は 0f が覆う。

## 3. 次の一手 (優先順。監督の見立てであり、新しいチャットが判断し直してよい)

1. **R-37 WP-4** (PG1〜PG4、BP3)。作業指示書 `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` に manifest がまだ無いので、§5.3x の形の manifest の起草から始める。設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §4 では、その後が WP-5 (facade 縮小と閉止) である。CE6 の残り 7 method は範囲外のままとする (W3-11)。
2. **R-22 の次**。R6-4 で残した日付の除去 (作業指示書 `docs/work-orders/WORK_ORDER_CODE_COMMENT_PROVENANCE_CS1.md` §14.5) と、変更セット 7 の選定 (設計 `docs/design/CODE_COMMENT_PROVENANCE_V1.md` §10.6 の「次の候補」)。0i で F-ID、peer 相対パス、basename、条項 ID を保護したので、チェッカーで確かめられる。
3. **R-39**。WP-3e〜3i のレビューで溜まった既知の穴は roadmap の R-39 行に列挙してある。いずれも未着手。

## 4. 依頼者判断待ち

前書 `docs/work-orders/HANDOVER_20260915_FABLE2.md` §4-5 から変更なし。R-42 は決着した (フェーズ11)。

## 5. 並行セッションとの調整 (重要。本チャットで始めた運用)

- 別セッション (charming-liskov) が R-44「テスト用 PostgreSQL の実行ごとの分離」を実装している (作業指示書 `docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md`、設計メモ `docs/design/TEST_POSTGRES_ISOLATION_V0_1.md`)。引き継ぎ時点で WP-1 は未統合である。
- `tools/dev/gate.py` は machine 全体の pytest を数えるので、相手の実行があると gate が無効になる。うまくいった手順は、gate の時間帯の前後で相手にメッセージを送り、相手がその間だけ実装担当を止めることである。
- 相手の permission 設定が kill を拒む場合、相手は自分の実行を止められない。**本チャットが相手のプロセスを代わりに kill してはならない** — 相手の permission の判断を迂回することになる。
- 他の pytest が動いている最中に**開始した** gate は、PASS と出ても破棄する。gate.py の並行判定は標本であり、短い実行を取りこぼす。gate の前に必ず pytest の件数を記録する。
- **R-44 WP-1 が統合された後** (相手が知らせる): pytest は使い捨ての PostgreSQL クラスタを自分で起動するので、gate.py の `pg_database` / `pg_roles` の差分 0 は、R-44 WP-2 がその検査を移すまで、きれいな実行の証拠ではなくなる。新しい根の `conftest.py` が `R2DB_TEST_ADMIN_DSN`、`MITATEDB_TEST_ADMIN_DSN`、`PGHOST`、`PGPASSFILE` を設定し、DSN があるのに `DSA_TEST_PG` が無い場合は明示的に失敗する。

## 6. 本チャットで足した運用上の教訓

- **STOP 条件は守らせる**。WP-3i で実装担当は、分類の無い参照 2 件で止まらず自己判定した。独立レビューはそのうち 1 件を誤りと判定した (W3-23)。WP-3e〜3i の manifest はいずれも参照を取りこぼしており、独立レビューだけが見つけた件数は順に 3、8、1、5、2 である。
- **R-37 の移動の来歴の証拠**。`check_comment_provenance.py --base <親>` は、既に CH-ID を持つ塊に括弧書きを入れる再編集の branch では、設計どおり赤になる。証拠は使い捨ての clone の、コミットした HEAD での `tools/tests` 0f である。CH-ID より古い `--base` は何も証明しない。設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §10.11 にこの訂正を記録した。
- **pytest の実行を止めない**。途中で殺すと PostgreSQL の残骸が残り、次の gate が負の catalog 差分で落ちる。
- **`conformance-tests` は約 9 分**で、前景の Bash 呼び出し 1 回 (timeout 600000) に収まる。実装担当が 3 回これを背景に回して止まった。発注時に明示する。
- **gate と finalize を 1 本の pipe でつながない** (前書から継続)。
