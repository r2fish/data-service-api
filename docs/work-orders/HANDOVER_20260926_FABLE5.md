# 引き継ぎ — 2026-09-27 (R-101: 1 process 内の直列化の主体の切り分け。WP-1 (計測器) と WP-2 (実測と判定) を完了、R-101 は閉じない。Class D、規模 M)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260926_FABLE4.md` (R-101 の前チャット)。本書は `docs/work-orders/HANDOVER_20260926_FABLE5.md` (チャットは 2026-09-26 開始・2026-09-27 終了)。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、作業指示書 = `docs/work-orders/WORK_ORDER_R101_SERIALIZATION_ATTRIBUTION_V1.md` (以下 `WO`)、設計メモ = `docs/design/PERF_SERIALIZATION_MEASUREMENT_V0_1.md`。本書で D-N / J-N / M-N / 完了条件と書くときは `WO` のものを指す (`OC` §1.8 の 59)。

記録: `docs/archive/docs/work-orders/HANDOVER_20260926_FABLE2.md` (R-41)・`docs/archive/docs/work-orders/HANDOVER_20260926_FABLE3.md` (R-38 / R-112) (本変更セットで回転、`OC` §1.16 の 78)

## 1. 現在地

- **R-101 の WP-1 (計測器) と WP-2 (実測と判定) を本チャットで完了した。** worktree `.claude/worktrees/r101`、branch `r101`、基点 local main `a1c1ee3`。本チャットで main を 2 回 merge した (`0d7065c` → `8c56e13`、`31f981d` (R-112) → `f1fa20d`)。
- 最終 code tree は `3d10d7d`。記録 (`RM` v1.128・`WO` §6.1 訂正註 9〜10 / 裁定 5〜8 / §6.2・設計メモ v0.2・本書) は本書起草時点で未 commit で、`tools/dev/finalize.py --tools-tests` で main へ merge する予定。
- **Class D** (依頼者裁定「D で進める」、`WO` §6.1 に逐語)、規模 M。契約 1.11.0 不変、`security/CONTROL_MAPPING.md` 3.5 (参照追随のみ。`_ISOMORPHIC_TARGETS` の件数 pin 167 = 159 + R-112 の 2 + 本件 6)。
- `conformance-tests/COLLECTION_FLOOR` は本変更セットで 4262 → 4314 (`WO` §6.1 訂正註 11。最終ゲートの実測値)。
- push は停止中 (GitHub 課金上限)。ローカル commit のみ。
- 役割とモデル: implementer (sonnet、段ごとに別起動 ×3: 条件 26 / 差し戻し 3 / 差し戻し 4)、reviewer (opus、transcript の `"model"` 欄 = `claude-opus-5-5`)、evidence-auditor (opus)、drafter (opus)。
- **WP-2 の判定** (設計メモ §4 の判断からの逐語):
  - 「4 plug とも J-2 が成立し、主体は **Python の CPU (GIL)** である。」(判断 1。r = cpu_total_ms / wall_ms = **2.206 / 1.429 / 6.530 / 4.479**、設計メモ §3 の 6)
  - 「MitateDB の 2 plug は J-5 も成立し (K=32 で acquire の 47% が待ち、待ち合計 10〜13 s)、**cell lock の待ちが主体** (R-102) と規則どおり併記する。J-3 (DB 往復の待ち) はどの plug でも成立しない。」(判断 1)
  - 「**判定不能の plug**: 無し (4 plug とも J-2 が成立する)。」
  - 「limit 4 は既定 40 より p50 で 30〜49%、p95 で 28〜44% 速い (r2db-socket を除く 3 plug)。これは J-1 (i) の場合分けの外で、規則は動かさず事実として記す。」(判断 2)
  - 「**R-101 は閉じない**: `RM` §0.1.4 の 2 (8 倍以内) はどの plug も満たさない (29.5〜33.3 倍。thread limit 4 でも 15.2〜32.9 倍)。」(判断 4)
  - 「R-84 の再検討条件 (「threadpool の混雑が tail latency を決めている」) は、規則の定義どおり **3 plug (r2db-http / MitateDB-http / MitateDB-socket) で充足、r2db-socket で不充足**。」(判断 3)

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| 木の状態の確定 | 再開直後の 3 suite: `pt: 611 passed` (tools/tests) / `pt: 1502 passed` (r2db-api) / `pt: 1493 passed, 2 subtests passed` (MitateDB-api) | `WO` §6.2 |
| 条件 26 | AST pin を 3 箇所に (M64 / M64b / M64c)、helper 3 つを r2db に同名で置き同型性登録 | `WO` §6.1 裁定 5 |
| コードレビュー 2 (opus) | 指摘 10 + 観察 4。差し戻し 3 で指摘 1〜9 と観察 (a)〜(c) を反映 (M107〜M112)、指摘 10 と観察 (d) は観察 | `WO` §6.1 裁定 7、「裁定」節 |
| 完了ゲート 1 回目 | tree `8c56e13`: `gate: 4291 passed, 2 subtests passed in 424.12s`、judge=PASS | `WO` §6.2 |
| 受け入れ監査 (opus) | 充足 77 / 未充足 0 / 証拠不足 0、観察 5 | `WO` §6.1 裁定 8 |
| 差し戻し 4 | 監査 O-2 (完了条件 66・67 の live adapter テスト、AU-66 赤) と O-4 (M45 / M46 の docstring) | `WO` §6.1 裁定 8 |
| 完了ゲート 2 回目 | 最終 tree `3d10d7d`: `label r101b gate: 4314 passed, 2 subtests passed in 334.79s (0:05:34)`、judge=PASS、pg_database/pg_roles diff 0。tools/tests `pt: 613 passed` | `WO` §6.2 |
| WP-2 | 非退行 K=1 3 組 + K=3 1 組、sweep 10 run、ε ≤ 2.9%、δ = 10%。判定は §1 | 設計メモ v0.2 §2〜§4、`WO` §6.1 訂正註 9・10 |
| 記録 | `RM` v1.128 (R-101 / R-84 / G-4 行)、設計メモ v0.2 §2〜§4、`WO` §6.1 / §6.2、`HANDOVER_20260926_FABLE2.md` / `HANDOVER_20260926_FABLE3.md` を archive へ回転、CM 3.5 | 本書冒頭 |

## 3. 次の一手

1. finalize (本チャット) → main。push 再開後に CI を 1 回。
2. **是正 WP を `WO` v1.1 で足す** — 是正の形は依頼者確認。候補は設計メモ §4 の判断 5: (a) composition root の limiter 縮小 (P-8 / R-20 の別変更セット)、(b) multi-process worker、(c) R-102、(d) R-84。
3. R-84 の着手 (規模 L、設計レビューが着手条件) は依頼者判断。
4. 監査 O-3 (`MitateDB-api/src/mitatedb_api/cell.py` の `prepared_stats` docstring の呼び出し回数) は R-102 の変更セットで直す。
5. 判定規則の次版への申し送り (設計メモ §4 の判断 6: r > 1、limit 4 が速い場合、J-2 と J-5 の同時成立)。

## 4. 依頼者判断待ち・未決

- 是正の形 (§3 の 2)。
- R-84 の着手 (§3 の 3)。
- 裁定 5 の読み: Class D の依頼者裁定はクラス宣言への裁定で、同一変更セット内の登録行の増加 3 → 6 はクラスを変えない、と監督が読んだ。異論があれば `WO` §6.1 裁定 5 を見直す。

## 5. 本チャットで足した運用上の教訓

1. implementer に「X は監督だけが触る」と書くと、監督の未 commit の X の編集を「原因不明の変更」として `git checkout --` で戻す — 監督の編集は implementer 起動前に WIP commit する。
2. 統合前に main を取り込む (今回 2 回。R-112 が同じ件数 pin を 161 に上げていて 167 に合算)。CM の版行に両 peer に同名で在るファイル名を裸で書くと register テストが「ambiguous」で赤 (`platform_declarations.py`)。
3. Bash の background 実行は 10 分で切れるので、ゲート + 性能計測の連鎖は端末タブ (`run_in_terminal`) で回す。他チャットのゲートが走っていると `gate.py` は exit 75 (intent は flock で生存判定。PID の終了を待って再実行)。
4. API の session 上限 (429、1am JST リセット) で殺された subagent は編集も journal も残さない — 再起動でよい。
5. 性能計測は 14 run で 7 分 (1 run 15〜60 s)。完了ゲート直後の最初の run は雑音が大きい (+11.7%) — 非退行は同条件 3 組で見る。
6. 判定規則は計測前に固定しても場合分けの外の結果が出る (limit 4 が速い、r > 1) — 規則は動かさず「場合分けの外」と事実で記し、次版への申し送りにする。
7. 前チャットの scratchpad は見えない — 変異 JSON は監査で `WO` §2.3 の表から作り直せた (77 件充足)。

## 6. 裁定

全件を載せる (`OC` §1.15 の 77)。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| コードレビュー 2 指摘 1 (中): `--roundtrip` の `db=app xacts=` に DBTIME の PRE probe の commit が入り、補正が POST 側だけ | 直した (案 (a)、`WO` 裁定 7) | 既存行の値の意味が変わる。M107 |
| コードレビュー 2 指摘 2 (中): 経緯語の残り (両 `psycopg_counting.py`:169、`tools/perf_baseline.py` 4 箇所、r2db adapter :4229 の R 番号) | 直した (差し戻し 3) | 裁定 1・6 の受理条件 |
| コードレビュー 2 指摘 3 (中): 完了条件 42 の `cpu_main_ms` = `thread_time` 差分が未固定 (RV2-T2 生存) | 直した (テスト + M108) | J-2 の入力 |
| コードレビュー 2 指摘 4: F8 の exit 側の加算・伝播にテスト無し (RV2-R1 生存) | 直した (テスト 2 本 + M109/M110) | — |
| コードレビュー 2 指摘 5: MitateDB 条件 55 の socket 側が同語反復 (RV2-M1 生存) | 直した (観測を差し替え + M111) | 空振り禁止 |
| コードレビュー 2 指摘 6: README の参照先と「次の op」の誤記 | 直した | 条件 51・73 |
| コードレビュー 2 指摘 7: M100 の docstring が赤になる assert を取り違え | 直した (M100 再実行で行番号を実測) | §1.5 の 34 |
| コードレビュー 2 指摘 8: liveness 失敗経路の畳み込みにテスト無し (RV2-R2 生存) | 直した (テスト + M112) | D-2 は閉じる側すべて |
| コードレビュー 2 指摘 9: MitateDB 条件 59 の否定側が未観測 | 直した | r2db 側と揃える |
| コードレビュー 2 指摘 10 (不確実): 依頼者裁定の逐語が登録 3 → 6 行を覆うか | 観察 (`WO` 裁定 5 に記録) | 裁定はクラス宣言への裁定。異論は §4 で受け付ける |
| コードレビュー 2 観察 (a): "(see report)" が失われた報告を指す | 直した | — |
| コードレビュー 2 観察 (b): docstring に psycopg private 名 `_exec_command` (完了条件 19 の字義) | 直した | 字義どおり 0 件に |
| コードレビュー 2 観察 (c): 件数 pin の docstring が AST helper 3 行に触れない | 直した | — |
| コードレビュー 2 観察 (d): conformance-tests が差し戻し 2 の後に未実行 | 観察 | 完了ゲートで判定 |
| 監査 O-1 (高): main が R-112 まで進み件数 pin が衝突 (161 vs 165)、gate は merge 前の木 | 直した (merge、167、CM 追随、gate 再実行) | 統合前に main を取り込む |
| 監査 O-2: 完了条件 66・67 が stand-in で accessor を読むだけ (AU-66 生存) | 直した (差し戻し 4、テスト + AU-66 ×2) | 空振り禁止 |
| 監査 O-3: `cell.py` の `prepared_stats` docstring の呼び出し回数が古い | 観察 | §2.1 の範囲外。既存 docstring の変更は来歴登録を要する。R-102 の変更セットで直す |
| 監査 O-4: M45・M46 の docstring が赤になる assert を取り違え | 直した (差し戻し 4、M45/M46 再実行) | §1.5 の 34 |
| 監査 O-5: 設計メモ §1 の 2 箇所 (最初の op の例外、崩れた文) | 直した (WP-2 §1 の確定時) | — |
| 監査 注記: 完了条件 76 は最終 tree の gate + tools/tests で代替 | 観察 (`WO` 裁定 8 に読み替えを記録) | 実装担当の suite 別集計は木の状態の確定で代替 |
| 監督裁定 5: 条件 26 の AST pin の helper 3 つを r2db に同名・本体同一で置き `_ISOMORPHIC_TARGETS` に登録 (本変更セットで計 6 行) | D のまま (`WO` §6.1 裁定 5) | `OC` §1.5 の 38。依頼者裁定はクラス宣言への裁定と読む (§4) |
| 監督裁定 6: 来歴検査 §4.1 (2) の、裁定 1 の 11 行の範囲外の 7 行 | 受理 (`WO` §6.1 裁定 6) | 今回分の comment block で削除行 0。現在形・経緯語なしはコードレビュー 2 で確認 |
| 監督裁定 7: コードレビュー 2 指摘 1 の直し方 | 案 (a) (`WO` §6.1 裁定 7) | PRE snapshot の probe 済み本数も補正で引く。D-2 の穴の訂正註を兼ねる |
| 監督裁定 8: 受け入れ監査の観察 5 件と注記 | O-1 直した、O-2・O-4 差し戻し 4、O-3 観察、O-5 WP-2 で直した、完了条件 76 は読み替え (`WO` §6.1 裁定 8) | 上の監査の行のとおり |
