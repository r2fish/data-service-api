# 引き継ぎ — 2026-09-29 (R-113 multi-process worker の 3 チャット目: WP-2 (r2db) 完了・`r113` に統合、WP-4 (`--workers`) は差し戻し 1 まで、WP-3 (MitateDB) は依頼者の中止指示で途中停止。Class D、契約 1.11.0 不変、規模 L)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260928_FABLE2.md` (R-113 着手、設計 v0.5、WP-1 完了)。本書は `docs/work-orders/HANDOVER_20260929_FABLE.md`。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、設計 = `docs/design/MULTI_PROCESS_WORKER_V0_1.md`、`WO` = `docs/work-orders/WORK_ORDER_R113_MULTI_PROCESS_WORKER_V1.md` (worktree `r113` にだけ在る。main には未統合)、`CM` = `security/CONTROL_MAPPING.md`。本書で D-N / Q-N と書くときは設計のもの、WP-N / M-N / 完了条件と書くときは `WO` のものを指す (`OC` §1.8 の 59)。裁定の番号は「設計 裁定 N」(設計 §10、1〜42) と「`WO` 裁定 N」(`WO` §6.1。`r113` の木に 1〜42、43〜45 は未転記) で書き分ける。handoff = `.claude/worktrees/r113-handoff/` (git 除外、commit しない。本チャットのレビュー・裁定表・実装報告・変異表を置いた)。

記録: `docs/archive/docs/work-orders/HANDOVER_20260928_FABLE.md` (本変更セットで回転、`OC` §1.16 の 78)

## 1. 現在地

- **main は `1d30732`** (docs-only。設計 v0.5、`RM` v1.130、`HANDOVER_20260928_FABLE2.md`)。本書は worktree `handover-0929` から finalize で main へ (Class A)。
- **worktree `r113`** (branch `r113`) = `18f9c0d`: `WO` v1.0 + §6.1 `WO` 裁定 1〜42 + §6.2 WP-1 / WP-2 の記録 + WP-1 の merge (`060a5d8`) + WP-2 の merge (`ccd9080` = `r113-wp2` の `2d23741`)。`WO` 裁定 43〜45 は §6.1 に未転記 (転記文は handoff の `wo61_rulings_43_44.md`)。
- **WP-2 (r2db) は完了。** コードレビュー 1 回 (F1〜F14) + 再確認 1b (G1〜G8) + 1c (指摘なし、観察 3)。実装担当は差し戻し 1・1b が sonnet (1b は週次上限で報告前に停止し、監督が log から集約報告を作った)、1c が opus。実装報告は handoff の `r113-wp2-report-2.md` / `-3.md` / `-4.md`。
- **WP-3 (MitateDB 移植) は途中 (PARTIAL)。** worktree `r113-wp3` (branch `r113-wp3`、基点 `18f9c0d`)。依頼者の中止指示で監督が実装担当 (opus) を停止し、作業ツリーを WIP `96985e8` に commit した (35 ファイル変更 + 新規 3: `MitateDB-api/migrations/0016_credential_request_rate.sql`、`MitateDB-api/src/mitatedb_api/concurrency_slots.py`、`MitateDB-api/tests/test_r113_multi_process_wiring.py`。両 peer の `_ISOMORPHIC_TARGETS` と `test_r78_pool_wait_stats.py` の登録を含む)。**実装報告なし、変異 run なし、コードレビュー未実施。**
  - 停止直前の pt (実装担当の log。監督は集計行だけ確認): `MitateDB-api/tests` `1597 passed, 2 subtests passed in 149.66s`、c05 / c26 / c32 `-k MitateDB` `67 passed, 73 deselected`、登録後の両 peer の `test_audit_query` + `test_r78` `154 passed`、`tools/tests/test_comment_provenance` `1 failed, 302 passed` (赤 = rev_vs_itself。未 commit 差分に由来し、commit 後に消える見込み)。停止時に走っていた C-26 lifecycle の run は未完。
- **WP-4 (`--workers`) は差し戻し 1 まで完了、再確認 1b 未実施。** worktree `r113-wp4` (branch `r113-wp4`、基点 `18f9c0d`)、WIP `8a54a74`。実装 (opus) → コードレビュー 1 回 (4 件) → `WO` 裁定 43〜45 → 差し戻し 1。pt: `test_perf_baseline` `120 passed`、`tools/tests` `4 failed, 657 passed` (赤 = 既知の共有 pin 4 件)。変異 `mutate: 10 mutations, 10 as expected` (M146〜M150、M149b、M153、M153b、M153c、M153z)。報告は handoff の `r113-wp4-report-1.md` / `-2.md`。
- **WP-5 未着手** (発注文の下書き = handoff の `wp5_prompt_draft.md`。完了条件 168b = `WO` 裁定 41 の runbook の 1 段、169 は WP-3 の完了条件 141 の算術を転記)。**WP-6 未着手** (回す事項は §3 の 4)。
- Class D、契約 1.11.0 不変、規模 L。push は停止中 (GitHub 課金上限)。ローカル commit のみ。
- 役割とモデル: Sonnet は週次上限 (2026-10-03 20:00 JST まで) のため、実装担当は model=opus で起動する。reviewer = opus。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| WP-2 の逸脱と指摘 | 実装報告 1 の逸脱 (a)〜(f)、レビュー 1 (14 件)、差し戻し 1 の逸脱、差し戻し 1 の逸脱 (f)(g)、再確認 1b (8 件)、再確認 1c (指摘なし、観察 3) | `WO` 裁定 22〜27 / 28〜36 / 37〜39 / 40 / 41〜42、本書「裁定」 |
| WP-2 の中身 | 0015 は PL/pgSQL 関数 `credential_request_rate_admit` (`INSERT ... ON CONFLICT DO NOTHING` → `FOR UPDATE`、+1 は `GREATEST(base_s, s) mod 61`)、`concurrency_slots.py`、`resolve_limit_enforcement`、`check_role_connection_limits(process_ceilings=)` で倍率を関数内に、control の F-18 は `role_pool_size(thread limit)`、`limits.thread_limit_from_env` (`main.py` の `_thread_limit_from_env` は同型 helper のまま、70b で同値を pin)、`--preflight` 両 plane、`application_name`、adapter の session / 隔離 surface の mkdtemp + PG rate、launcher の ALTER ROLE (controlplane 32 / auditreader 8)、C-26 の 1 テストの宣言分岐 | `WO` §6.2 |
| WP-2 の最終実測 | `r2db-api/tests` `1 failed, 1609 passed` (赤 = 同型性 3 helper、WP-3 で解消)、c05 / c26 / c32 `-k r2db` `67 passed`、`tools/tests/test_comment_provenance` `303 passed` (commit 後)、変異 69 件 red、provenance `--base 74d90f3` = 29 行 (全部分類済み、(3)(5) は 0)、`HAVE_FLOCK=1` | `WO` §6.2、handoff の `wp2-mutation-table.md` / `provenance-wp2-final.txt` |
| WP-4 の逸脱と指摘 | 実装報告 1 の逸脱 (a)〜(g)、レビュー 1 (4 件)、差し戻し 1 の逸脱 (a)〜(f) | `WO` 裁定 43 / 44 / 45 (転記待ち)、本書「裁定」 |

## 3. 次の一手 (順)

1. **WP-3 の続き。** 新しい実装担当 (opus) を `r113-wp3` の `96985e8` の上で起動し、完了条件 83〜145 (+ 56b / 70b / 71c / 72c / 74b の MitateDB 版) の照合 → 変異 §5.3 全件 (+ M8m〜M18m) → 静的検査 → 報告 (`r113-wp3-report-1.md`) まで (WP-2 の差し戻し 1 と同じ再開の形)。→ コードレビュー (新規 reviewer opus、Class D、`WO` §5.5) → 差し戻し → `r113` に merge。
   - 並行して **WP-4 の再確認 1b** (新規 reviewer。レビュー 1 の指摘 1〜4 が `WO` 裁定 44 のとおり閉じたかと、差し戻し 1 の逸脱 (a)(b)(e) の頑健性) → `r113` に merge。
   - `WO` §6.1 に裁定 43〜45 (handoff の `wo61_rulings_43_44.md` の文) を転記し、§6.2 に WP-3 / WP-4 の記録を足す。
2. **WP-5** (opus、下書き `wp5_prompt_draft.md`) → レビュー → merge。
3. **監督の計測** (`WO` §7.5、設計 §7): 小実験 0.2 ms/文 → N=1 / N=4 × K=1 / K=32 × 2 run、表 7-1〜7-5、判定は `WO` §10 の逐語、R-101 の閉止は Q-5 のとおり。§7.5 の 6 に launcher の nginx の残存 0 の確認を足す (`WO` 裁定 44)。
4. **WP-6 (記録)**: C-26 の `CONDITIONS.md` の文言 (rate の配線で ceiling 2 でも `requests_per_minute` は `enforced`)、`tools/check_comment_provenance.py` の Known gaps に「def の改名で scope key が変わる」の 1 行 (`WO` 裁定 30)、`tools/tests` の共有 pin 4 件 (`concurrency_slots.py` の分類: `test_leaf_import_direction` / `test_sql_statement_safety_scan` / `test_src_import_cycles` / `test_src_import_readers`)、`tools/PERF_BASELINE_README.md` に `REALWORKERS` 行と `non_200`、`RM` の R-113 / R-101 / R-18 行、`CM` 3.7、`conformance-tests/COLLECTION_FLOOR`。→ 受け入れ監査 1 回 → `gate.py -C .claude/worktrees/r113` (`tools/tests` は別に回す) → finalize (Class D、契約ファイル不変)。**WP-1 だけを main に統合しない。**

## 4. 依頼者判断待ち・未決

- **R-114 の直し方。** (i) 契約の文言を「窓の形は定めない」に改める (版上げ)、(ii) 実装を fixed window に改める。監督案 (i)。
- **R-101 の閉止は WP-4 の D-16 次第。**
- R-52 (rollout の重なり) は R-113 の範囲外。
- Sonnet 週次上限 (2026-10-03 20:00 JST まで) の間は実装担当を opus で起動する (費用増)。依頼者の了解を要するなら次チャットで確認。

## 5. 本チャットで足した運用上の教訓

1. Sonnet の週次上限は実装担当の途中で来る。報告前に止まったら、監督が pt / mutate の log と worktree の現物から集約報告を作り (実装担当の自己申告ではないと明記)、reviewer に読ませればよい。以後は opus で起動。
2. 変異の赤は理由まで読む (M71c は `NameError` で赤だった。reviewer も見落とした)。実装報告には赤の理由の 1 行を要求する。
3. 呼び出し元で倍率を掛ける裁定 (`WO` 裁定 23) は関数の中身 (定数の床) を見ずに出して撤回した。裁定の前に該当関数の本体を読む。
4. 登録済みの塊の直後に文を書き足すと同じ塊として読まれる。新しい文は空行か code 行で切り離す。偽になった登録済みの本文は `CODE_COMMENT_PROVENANCE_V1` §9.3 の訂正記録 (`old` は第 1 文だけで足りる)。
5. 代理変異 (宣言を変えて cross-check で赤にする、guard の `ValueError` で赤にする) はレビューで落ちる。変異は機構だけを外す。
6. `ps -e` は macOS の legacy モードで全 process を列挙しない。`ps -A` を使う。
7. 実装担当の「WP-1 由来の既知」という帰属は疑う (C-26 の赤は WP-2 自身の配線が原因だった)。
8. 前チャットの scratchpad は読めないので、レビュー・裁定・報告は handoff ディレクトリに写す (git 除外)。

## 6. 裁定

全件を載せる (`OC` §1.15 の 77)。起票 0 件、既知の穴 0 件。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| WP-2 実装 逸脱 (a): 0015 の rate 加算を PL/pgSQL 関数 `credential_request_rate_admit` で実装 | 受理 (`WO` 裁定 22) | autocommit 1 文の呼び出し・SECURITY INVOKER・`clock_timestamp()` 1 回で「1 文」の性質を保つ。初回 INSERT の競合はレビュー 1 F1 で直した |
| WP-2 実装 逸脱 (b): F-16 の倍率を data 面の `main.py` だけに掛けた | 直した (`WO` 裁定 23、裁定 28 で撤回し改めた) | 倍率は `check_role_connection_limits` の中で data / control それぞれに掛ける |
| WP-2 実装 逸脱 (c): provenance の一括 regex が範囲外の docstring 74 行を書き換え、全復元 | 受理 (`WO` 裁定 24) | レビュー 1 が 65 hunk を囲みの symbol に写し、触った symbol の外の変更 0 件を実測 |
| WP-2 実装 逸脱 (d): `record_rate_and_check` が既存の History 行 (CH-0399) を流用していたのを削除 | 受理 (`WO` 裁定 25) | 新規の塊に History 行は要らない |
| WP-2 実装 逸脱 (e): CH-0322 の訂正記録を全文置換 1 件で追記 | 直した (`WO` 裁定 26・30) | 全文置換の形は受理。`old` が基点と逐語一致せず赤だったので直した |
| WP-2 実装 逸脱 (f): `--base` の §4.1 (1)(2) の残りを Known gaps 相当として打ち切り | 直した (`WO` 裁定 27) | (1) の AST 差分と old 0 / new 1 型は受理。登録済みの塊への書き足し (CH-0137 / CH-0257 / CH-0322) は直した |
| WP-2 レビュー 1 F1 (高): 0015 の初回 INSERT の競合で 503 | 直した (`WO` 裁定 22) | `ON CONFLICT DO NOTHING` の後に `FOR UPDATE` で読み直す。決定的な競合テストと M29b |
| WP-2 レビュー 1 F2 (高): 新規 module `concurrency_slots.py` に他ファイルの CH-0001 を書き `--register` が赤 | 直した | History 行を削除 (`WO` 裁定 25 と同じ扱い) |
| WP-2 レビュー 1 F3 (高): control の F-18 が `concurrency` (32) を基準に数え、裁定 23 の倍率は no-op | 直した (`WO` 裁定 28) | 倍率を関数の中へ、control の F-18 は `role_pool_size(thread limit)`。完了条件 71c / 72c / 74b と同名の変異 |
| WP-2 レビュー 1 F4 (高): `test_c26_ceiling_maps_to_limit_enforcement[r2db-api]` の赤は WP-2 の配線による | 直した (`WO` 裁定 29) | この 1 テストだけ宣言分岐 + 配線 accessor の cross-check に。C-26 の行は WP-6 |
| WP-2 レビュー 1 F5 (中): 完了条件 54 のテストが無く、M8r〜M18r が未実行 | 直した | timeout 付きの SIGKILL / close 後の再取得テスト、M8r〜M18r を実行 |
| WP-2 レビュー 1 F6 (中): 等価変異 (M31) と代理の検査 (M32・M70・M76・M77、条件 35・36・45・64) | 直した (`WO` 裁定 40) | M31 は `NULL;`、M32 は 61 を 60 に揃える、76 / 77 は adapter の session と隔離 surface で直接観測 |
| WP-2 レビュー 1 F7 (中) CH-0322 (a): 訂正記録の `old` がラベル付きで基点と一致しない | 直した (`WO` 裁定 26) | `old` をラベルなしの形に、`new` を直した docstring と逐語一致に |
| WP-2 レビュー 1 F7 (中) CH-0322 (b): 改名 `_declared_concurrency` → `_declared_pool_size` で scope key が変わり `--base` の (2) が赤のまま | 観察 (WP-6 で追記、`WO` 裁定 30) | 名が事実と一致することを優先して改名は残す。検査器の Known gaps への 1 行は監督が WP-6 で足す |
| WP-2 レビュー 1 F7 (中) CH-0137 / CH-0257 / `main.py`:590: 登録済みの塊の直後への書き足し | 直した (`WO` 裁定 27) | 空行で切り離し、偽になった CH-0137 は訂正記録の上で言い換えた |
| WP-2 レビュー 1 F7 (中) CH-0174: 削除した定数を説明する塊が残り、本文も偽 | 直した (`WO` 裁定 31、39・42 で改めた) | 塊は残し、訂正記録 (`old` は第 1 文) の上で `resolve_limit_enforcement` を説明する現在形の文に |
| WP-2 レビュー 1 F7 (中): 事実と食い違うようになった既存の文 (`platform_declarations.py` 2 箇所、`main.py` の `application_name` の文) | 直した | 再確認 1b G5 の閉止で確認 |
| WP-2 レビュー 1 §2: code に追随した CH 無しの塊の書き換え 6 件 | 受理 (`WO` 裁定 32) | code を変える WP に固有 (Known gap 3 と同じ扱い)。「事実で現在形」の条件は 1b G5 で満たした |
| WP-2 レビュー 1 F8 (低〜中): regex 置換の痕 (壊れた文) と経緯の叙述 | 直した (`WO` 裁定 33) | 完了条件 73・80。残りは 1b G5 で直した |
| WP-2 レビュー 1 F8 のうち `docs/code-history/r2db-api/ops.md` の reason 行の「renamed」 | 観察 (`WO` 裁定 33) | 訂正記録は経緯を書く場所 |
| WP-2 レビュー 1 F9 (低): `_declared_pool_size` の docstring が偽で、main と判定がずれる | 直した (`WO` 裁定 28 (ii)) | 読み方を `limits.thread_limit_from_env` (fail-loud) 1 つに置いた |
| WP-2 レビュー 1 F10 (中): 条件 32・33 のテストが秒の境目で落ちる | 直した | DB の秒を前後で読み、同じ秒に収まるまで最大 3 回やり直す |
| WP-2 レビュー 1 F11 (低、不確実): 環で +1 する位置が `WO` 裁定 3 の逐語と違う | 受理 (`WO` 裁定 34) | `GREATEST(base_s, s) mod 61` を採り、裁定 3 を訂正註で改めた |
| WP-2 レビュー 1 F12 (中): `tools/tests` の共有 pin 4 件 (`concurrency_slots.py` の分類) | 観察 (WP-6 で更新) | pin の更新で欠陥ではない。監督が更新する |
| WP-2 レビュー 1 F12 (中): 同型性の赤 3 helper (`_VERIFY_DECLARATIONS_EXIT_CODES` ほか) | 観察 (WP-3 で解消) | WP-2 の本体変更。WP-3 の移植の対象 |
| WP-2 レビュー 1 F12 (中): `real_server_mitatedb.py::stop` の同型性の赤 | 直した (`WO` 裁定 35) | 差は r2db 側のコメント 1 行。1b G4 で改行まで揃えた |
| WP-2 レビュー 1 F13 (低): `DataService` が slot 無しで `concurrency_configured=True` を受ける | 直した (`WO` 裁定 36) | `ValueError`。完了条件 56b と変異 |
| WP-2 レビュー 1 F14 (低): 条件 75 の開示が docstring に無い | 直した (`WO` 裁定 36) | `verify-declarations` の docstring に置いた |
| WP-2 差し戻し 1 逸脱 (a): `main.py` の `_thread_limit_from_env` を共有関数に置き換えなかった | 受理 (`WO` 裁定 37) | 登録済み同型 helper。同値を完了条件 70b / M70b で pin |
| WP-2 差し戻し 1 逸脱 (b): `service.py` の「before this WP」2 文の修正を revert | 観察 (`WO` 裁定 38) | 基点 `74d90f3` に在る文で WP-2 の追加ではない |
| WP-2 差し戻し 1 逸脱 (c): F5 / F6 / F10 の残りのテスト・変異が未着手 | 直した (差し戻し 1b・1c) | M8r〜M18r、M31 / M32 / M70 の差し替え、条件 54・76 / 77・36・35 後半・45・64、秒境目の対策 |
| WP-2 差し戻し 1 逸脱 (d): 既存テストと launcher の provisioning の CONNECTION LIMIT を F-16 の倍率に合わせて引き上げ | 受理 (`WO` 裁定 41) | テスト環境の provisioning。launcher の ALTER ROLE は 1b G3 で受理 |
| WP-2 差し戻し 1 逸脱 (e): `real_server_r2db.py` の `stop()` のコメントを MitateDB に合わせた | 受理 (`WO` 裁定 35) | 差は r2db 側 |
| WP-2 差し戻し 1 逸脱 (f): 条件 76 / 77 の観測を composition root (`build_app()`) で行った | 直した (`WO` 裁定 40) | 76 / 77 は http plug の adapter の session と隔離 surface で観測する。composition root 側は 76a として残す |
| WP-2 差し戻し 1 逸脱 (g): M76b が F13 の guard の `ValueError` 経由で赤 | 直した (`WO` 裁定 40) | 代理の変異。M76b / M77b を削除し M76 / M76i / M77 に |
| WP-2 差し戻し 1 疑義: CH-0174 の `--base` の (3) の残差は基点由来 | 直した (`WO` 裁定 39、42 で撤回) | 1b の clone 実測で、訂正の `old` を第 1 文だけにすれば WP-2 で消えた |
| WP-2 再確認 1b G1 (中): M14r・M16r・M76 が代理の変異、M70 が未差し替え | 直した (`WO` 裁定 42) | どれも宣言を変えず、機構を外して性質そのもので赤 (1c で確認) |
| WP-2 再確認 1b G2 (中): 隔離 surface の rate 配線が未観測 | 直した (`WO` 裁定 42) | hold の後の rate 行を隔離 surface の DSN で観測、M77i |
| WP-2 再確認 1b G3 (中): launcher の ALTER ROLE (controlplane 32 / auditreader 8) が触ってよい範囲の外 | 受理 (`WO` 裁定 41) | control ceiling 2 の lifecycle に要るテスト環境の provisioning。runbook の 1 段を WP-5 (完了条件 168b) に |
| WP-2 再確認 1b G4 (低〜中): `real_server_mitatedb.py::stop` の同型性がまだ赤 | 直した (`WO` 裁定 42) | 改行を揃えた。残る赤は WP-3 対象の 3 helper |
| WP-2 再確認 1b G5 (低〜中): 経緯語・壊れた文・偽の文の残り | 直した (`WO` 裁定 42) | 1c で全箇所を確認 |
| WP-2 再確認 1b G6 (低): 「同じ reader」の文が事実と違う | 直した (`WO` 裁定 42) | control_main と同じ reader、main とは同じ規則 (70b で pin) |
| WP-2 再確認 1b G7 (低): テストの後始末・環境依存・docstring の算術 | 直した (`WO` 裁定 42) | `rolconnlimit` を読んで finally で戻す。M71c のテストは cluster の値から選ぶ |
| WP-2 再確認 1b G8 (低): report-3 の抜けと誤り (条件 54・67・78・80) | 直した (`WO` 裁定 42) | `HAVE_FLOCK = 1`、provenance 29 行、67 の file:line を 1c で照合 |
| WP-2 再確認 1b の観察: C-26 ceiling_maps の `[MitateDB-api]` は WP-3 まで赤 | 観察 (`WO` 裁定 42) | WP-1 の時点では緑。期待される赤の一覧に足した |
| WP-2 再確認 1c 観察 1: `concurrency_slots.py`:164 の「design completion condition 51」は出所の偽の帰属 | 直した | 監督が「design」を削除 |
| WP-2 再確認 1c 観察 2: 付録 E の分類名「削除 (old>new)」は実態が改名の追随 | 観察 | 分類名を「改名 (scope key) の追随」とする |
| WP-2 再確認 1c 観察 3: `test_0f_both_peers_all_src_rev_vs_itself_is_green` の commit 後の緑は未検証 | 観察 | commit 後に `303 passed` を確認 |
| WP-2 差し戻し 1c 逸脱 (a): M71c の spec を literal `32` に | 受理 | 旧 spec の赤は `NameError` (正しくない理由)。直した後は F-18 の下限超過で赤 (1c で確認) |
| WP-2 差し戻し 1c 逸脱 (b): CH-0174 の `new` で `service.py` のパスを現在形の文で残した | 受理 | パスを消すと §9f の path 検査が赤。1c で妥当 |
| WP-2 差し戻し 1c 逸脱 (c): `ops.md` CH-0322 の 2 本目の reason 行の偽を直した | 受理 | 1c で妥当 |
| WP-2 差し戻し 1c 逸脱 (d): ALTER ROLE の後始末を変更前の `rolconnlimit` を読んで戻す形に | 受理 | 1b G7 の直し。1c で確認 |
| WP-2 差し戻し 1c 逸脱 (e): `#:` の修正で provenance の (2) が 1 行増えた | 受理 | 事実への追随。(3) が 1 行減り合計 29 行 (1c で妥当) |
| WP-2 差し戻し 1c 逸脱 (f): 既存テスト `test_role_pool_size_is_thread_limit_plus_two` を残し、docstring を helper の算術の pin に | 受理 | M70 の対象は新テスト |
| WP-2 差し戻し 1c 逸脱 (g): `change_class.py` の出力は `class=C` | 受理 | パスだけで決まる下限で、D の宣言と矛盾しない (1c §4) |
| WP-4 実装 逸脱 (a): 既存 stub launcher テンプレートに `workers=` / access log の accessor を追加 | 受理 (`WO` 裁定 43) | 既存の assert は不変 |
| WP-4 実装 逸脱 (b): `REALWORKERS` の 1 行を REALCPU の直後に | 受理 (`WO` 裁定 43) | REALPERF / REALCPU の書式は不変 |
| WP-4 実装 逸脱 (c): 受付数の窓 = sanity の後〜最後の group、止まった run でも出す | 受理 (`WO` 裁定 43) | 止まった run の N と受付数が残る |
| WP-4 実装 逸脱 (d): process group を `ps` の前後差分で特定、stop 後 10 s、残骸は stderr + 終了コード 1 | 受理 (`WO` 裁定 43) | `ps` の出力形はレビュー 1 の指摘 2・3 で直した |
| WP-4 実装 逸脱 (e): `--workers` < 1 は終了コード 2 | 受理 (`WO` 裁定 43) | `--client-processes` と同じ扱い |
| WP-4 実装 逸脱 (f): 完了条件 146 は stub で観測 | 受理 (`WO` 裁定 43) | 本物の launcher の N 本は WP-1 の観測と §7.5 の表 7-3 |
| WP-4 実装 逸脱 (g): 既存コメントと docstring を workers ベースに直した | 受理 (`WO` 裁定 43) | 現在形、経緯トークンなし |
| WP-4 実装 疑義 1: 子の数を道具が数える案 | 観察 (`WO` 裁定 43) | 設計外 |
| WP-4 実装 疑義 2: 成功時にも残骸 0 の 1 行を出す案 | 観察 (`WO` 裁定 43) | §7.1 の出力の範囲外。§7.5 の 6 の記録は監督が終了コード 0 と `ps` の実測で残す |
| WP-4 レビュー 1 指摘 1 (中): 表 7-4 を道具の出力だけで埋められない (429 の件数、MitateDB は 413) | 直した (`WO` 裁定 44) | `REALWORKERS` に非 200 の status ごとの件数 (完了条件 149b、M149b)。「429」は LIMIT_EXCEEDED の意と読む訂正註 |
| WP-4 レビュー 1 指摘 2 (低〜中): `ps -e` が全 process を列挙しない環境で残骸検査が空振り | 直した (`WO` 裁定 44) | `ps -A` と番兵 (group を観測できなければ終了コード 1。完了条件 153c、M153c) |
| WP-4 レビュー 1 指摘 3 (低、不確実): zombie を live process として数える | 直した (`WO` 裁定 44) | zombie は残骸に数えず件数を情報として出す (M153z) |
| WP-4 レビュー 1 指摘 4 (低): launcher の nginx が残骸検査の外 | 直した (`WO` 裁定 44) | 道具には入れず、§7.5 の 6 に nginx の残存 0 の確認を足す訂正註 (転記待ち) |
| WP-4 差し戻し 1 逸脱 (a): 非 200 の件数を status 100〜599 の順問い合わせで数える | 受理 (`WO` 裁定 45) | launcher の公開 API だけを使う。非 200 の無い run では問わない。頑健性は再確認 1b で確かめる |
| WP-4 差し戻し 1 逸脱 (b): group stub の拡張 (status の上書き、ZOMBIE_ON_STOP、安定待ちの短絡) | 受理 (`WO` 裁定 45) | 頑健性は再確認 1b で確かめる |
| WP-4 差し戻し 1 逸脱 (c): zombie の観測テストと M153z (完了条件 153 の補強) | 受理 (`WO` 裁定 45) | レビュー 1 指摘 3 の観測 |
| WP-4 差し戻し 1 逸脱 (d): 153c を monkeypatch の stub で観測 | 受理 (`WO` 裁定 45) | process を起こさない start で番兵を観測 |
| WP-4 差し戻し 1 逸脱 (e): launcher の group 候補から zombie を除く | 受理 (`WO` 裁定 45) | 前後差分に死んだ子を入れない。頑健性は再確認 1b で確かめる |
| WP-4 差し戻し 1 逸脱 (f): docstring の「live」を削除 | 受理 (`WO` 裁定 45) | 指摘 3 の文言 |
