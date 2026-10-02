# 引き継ぎ書 — 2026-10-01 R-102 (MitateDB のデータ面の application 単位の直列化) 閉止

本書は R-119 と R-102 の実施のチャットの記録である。規律の正本は `docs/work-orders/OPERATING_CONDITIONS.md`、R-102 の正本は設計 `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md` v0.6 (依頼者裁定は同書 §11.1) と作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` (§1 の監督裁定 M-1〜M-16、§5 の記録、§6 の訂正註 1〜8) である。設計のチャットの記録: `docs/archive/docs/work-orders/HANDOVER_20260930_R102_FABLE.md`。

## 1. 現在地

- R-119 は閉止 (local main `ddf9c73`、完了ゲート 4855、台帳 v1.145)。
- R-102 は閉止: local main (merge 候補 `4d7181a` = main `ddf9c73` + branch `r102` を `--no-ff` で merge した候補の上の完了ゲート `gate: 4927 passed, 2 subtests passed in 464.40s (0:07:44)`、judge=PASS、pg_database/pg_roles diff 0 (label r102、2026-10-01 16:27、merge 候補 `4d7181a` = main `ddf9c73` + branch `r102` `22fc73a`)。最終の merge は記録の commit を足した候補で再実行した完了ゲートの後に 1 回)。契約は 1.13.0 のまま (`spec/` 不変)、`CM` 3.14、共通条件 C-34 (port v1.20)、台帳 v1.146、設計 v0.6、R-120 を起票。push は停止中。
- 記録の置き場: 本書を commit する変更セットで、最新 2 通から外れる `docs/work-orders/HANDOVER_20260930_R46_FABLE.md` を `docs/archive/` 配下へ移す (`OC` §1.16 の 78)。

## 2. 本チャットで閉じたもの

レビューの列は 1 巡目の A / B の件数と再確認の件数 (裁定は §6)。変異の列は `expect=red` で赤を実測した件数 (spec ごとの実行数の和)。

| 段 | commit | 内容 | レビュー | 変異 |
|---|---|---|---|---|
| R-119 | `356e3a8` (merge `ddf9c73`) | `read_page` の decode を外側 lock の内側へ (規模 S) | — | 1 |
| WP-1 | `1d24454` → `fd0479d` → `b01ec6e` | 再現テスト 7 本 (MitateDB の開1〜開4 = `MitateDB-api/tests/test_r102_cross_cell_windows.py`、r2db の 3 窓 = `r2db-api/tests/test_r102_schema_windows.py`)。基点の製品コードで 7/7 赤 (§4 の B) → 停止点を文そのものへ、未完了の枝を lock 待ちの観測で裏付け | A 2・B 5 + 観察 1、再確認 1 | 0 (V1〜V5・V9・V10 は WP-4、V6〜V8・V9r・V10r は WP-6 の spec で実行) |
| WP-2 | `9cb6787` → `e205819` → `9957afd` | C-34 + port v1.20 の `hold_after_plan_verification` + 6 adapter。確定文を plan / dry_run 付きに限った (§4 の F) | A 4・B 8、再確認 3 | 7 (V14a・V14b・V15・V15b・V16・V20・RA-1)。V14a は WP-6 の後に監督が再実行: 変異なし `pt: 18 passed in 8.54s` (log pt の log (12:25:44))、変異 `1 failed in 30.76s` 赤 (log mutate の log (12:24:54)) |
| WP-3 | `361f3bd` → `a3c6078` → `610d641` | `BoundedConnectionPool`: 呼び出しごとの acquire timeout、中立の例外、返却時の rollback、全 pool の idle の掃除 | A 3・B 6 + 観察 1、再確認 3 | 12 (V26〜V34 ほか 11 + 監督の V26c) |
| WP-4 | `ff408fa` → `c29eb61` → `0d8ffd0` | cell lock を外し、要求の範囲 (`request_scope`) で role ごとの pool から借り、transaction 単位の advisory lock (per-key・件数・3a・3b) で協調。差し戻し 2 で例外なしの範囲の読み取り transaction を COMMIT (M-19、§4 の A) | A 4・B 8、再確認 (WP-4 / WP-5 合同) 7 | 51 (a 6・b 14・c 14・d 13・e 4。WP-1 の後送り分を含む) |
| WP-5 | `32eefb0` → `4a37988` → `5e0cb08` → `eb97a06` | 計測器: role ごとの pool 行と schema lock 行、adapter の `pool_stats` / `prepared_stats`、`--roundtrip` の matcher を pool の形に | A 4・B 7、再確認は WP-4 と合同 | 9 (V72〜V77・V78a〜V78c) + 再確認の RR-MI1 (監督) |
| WP-6 | `a2f9735` → `3d2656e` → `10f7833` | r2db の `apply_schema` に application 単位の schema lock。順序は per-key → lookup → 3a → 件数 lock (M-17、§4 の A) | A 3 + 観察 1・B 2、再確認 2 | 16 (15 + 監督の RC1) |
| WP-7 | `400f527` → `0cd6fa0`、ops の式 `6116807` | `CM` 3.14、`COND` C-05 / C-27 / C-34 と履歴、port 設計 1.20 §30、設計 v0.6 の註、runbook §6.5 と §10.10 版 12、台帳 v1.146。ops inventory item (8) を pool の式に (訂正註 5) | A 5・B 9、再確認 5 + 観察 2 | V-ops-1・V-ops-2 (log mutate の log (12:36:44))、RB-wp7-1 (監督、`1 failed in 0.50s` 赤、log mutate の log (12:50:49)) |
| 最終一括 | `d4bb075` (+ 指紋の行 `3a03608`、§5.1 / §5.3 `22fc73a`) | 再確認 WP-7 の直し 7 項目 (34b の入力、SI-01 Evidence、main.py / pool.py の語、r87 の test 名、C-34 Status の RB-wp7-1、`CM` の行参照、PERF README の `backend_calls`) | `pt: 325 passed` (test_ops_inventory / CM register / test_perf_baseline)、V-ops-3 赤、CM register 58 passed | V-ops-3 |
| 完了条件 85 | — | `_ISOMORPHIC_TARGETS` の集合 (205 行) は不変: `c29eb61` で `pt: 8 passed, 134 deselected in 4.77s` (log pt の log (12:30:23)) | — | 監査照合 |
| 計測 D-R102 | — | round 1 (参考値): K=4 の判定値は before 37.3% / after 0.0% (2 run とも)。K=1 で MitateDB-http の p50 が +176〜226% の退行 → M-19 で直し全段を取り直した。round 2: 作業指示書 §5.3 の表 A / B / C (round 2: K=4 の判定値は 2 run とも 0 / 4856 = 0.0%、K=1 は全 plug が閾値の内側、real-server は前後で不変) | — | — |
| 完了ゲート (最終候補) | 候補 `5da56d1` (main `ddf9c73` + `r102` `c3e5ca7`) | `gate: 4927 passed, 2 subtests passed in 910.29s (0:15:10)`、judge=PASS、pg_database/pg_roles diff 0 (label r102-final、2026-10-01 16:42)、`tools/tests` `pt: 784 passed in 88.08s (0:01:28)` (tools/tests、候補 `5da56d1`) | — | — |
| 完了ゲート | 候補 `4d7181a` | `gate: 4927 passed, 2 subtests passed in 464.40s (0:07:44)`、judge=PASS、pg_database/pg_roles diff 0 (label r102、2026-10-01 16:27、merge 候補 `4d7181a` = main `ddf9c73` + branch `r102` `22fc73a`)、`COLLECTION_FLOOR` 4855 → 4927 | — | — |
| 受け入れ監査 | — | `evidence-auditor` 1 回 (候補 `4d7181a`、パケット = scratchpad の `acceptance-packet-r102.md`): 充足が主、未充足 / 証拠不足 5 件 (記録の範囲: 完了条件 90 / 97 / 98a の 1 件、K=4 の p50 の前後、`tools/tests` の CH-0547) と観察 5 件 — すべて裁定済み (作業指示書 §5.4、訂正註 8、本書「裁定」節) | — | — |

## 3. 次の一手

1. 依頼者の確認 (§4)。確認の後に §4 の運用の残り: runbook §10.8 の版 12 の受理、M-17 の両 peer の揃え方、M-18 の問い、R-120 の着手判断。
2. R-108 (参照クライアント) は着手可能。R-101 は開いたまま (閾値 2 は real-server の 8 倍で、R-113 の値のまま)。
3. 性能: D-R102 の判定値 = round 2 の 2 run とも 0 / 4856 = 0.0% (基準値 1319 / 3537 = 37.3%)。`RM` §0.1.4 の 3 (Q-2 の読み替え後) は充足。K=1 は全 plug が閾値の内側 (MitateDB-http は −10〜−17%)。K=32 / K=1 の real-server 比は前後で不変 (N=4 で 10.5〜11.0 倍、§0.1.4 の 2 は R-101 の範囲)。

## 4. 依頼者判断待ち・未決

依頼者指示 2026-10-01「裁定は監督の推奨で進めてあとで確認」の下で進めた裁定の一覧 (再審議ではなく確認):

- A. 作業指示書 §1 の M-1〜M-16 (起草時の監督裁定。逐語は作業指示書)、訂正註 3 の M-17 (r2db の lock 順 per-key → lookup → 3a → 件数 lock。MitateDB の設計 D-3 の順 (1 → 2 → 3a) と非対称。両 peer を揃えるか)、訂正註 6 の M-19 (例外なしで抜ける範囲は読み取り transaction を COMMIT して返す。完了条件 57b)。
- B. WP-1 の再現の報告 (設計 Q-4 の (i-a)、M-16): 開1〜開4 と r2db の 3 窓の 7 本とも基点の製品コードで赤 (MitateDB `pt: 4 failed in 1.35s`、log pt の log (07:23:33)。r2db `pt: 3 failed in 1.04s`、log pt の log (07:23:36))。再現は成立した。したがって `schema_objects: enforced` の宣言は、R-102 の前の process 数 > 1 で契約 1.8.0 の義務 (spec :37) に合っていなかった。R-102 で閉じた (宣言は変えていない)。
- C. M-18 の問い (WP-4 の疑義 1): plan を持つ DML (transact の dry-run / plan) は 3a を取らないので、別 entity の schema 操作が revision を進めても plan 付きの DML が通る。
  - (a) 設計どおり (DML の plan の照合は 3b の範囲)。
  - (b) plan 付きの DML も 3a を共有で取る (schema 操作の間は DML が止まる)。
  - 監督の推奨は (a) で、観察として記録した (§6)。
- D. R-120 の起票 (r2db の DML の検証と書き込みの間の alter の窓。規模 M、着手条件は依頼者の着手判断)。
- E. runbook §10.10 の版 12 (pool の式、item (8)) の再受理 (§10.8 は 12 / not accepted)。
- F. 確定文の改訂: C-34 の条件文と hook の文を plan / dry_run 付きの schema 操作に限った (旧版は scratchpad の `*.v1.txt`。作業指示書 訂正註 2 の 2)。
- G. 既知の穴の候補: `tools/check_comment_provenance.py` は、コードごと消える経緯コメントを code-history の fence に逐語で移し参照行を残す形 (WP-4 レビュー B-1 の (ii)) を、保護参照 (test 名) を含む文の削除として companion から導出できず赤にする (設計 §4.1 (3)、常設の rev-vs-itself の検査)。本件は R-115 の先例どおり git に任せた ((i)、訂正註 8)。製品の欠陥は通らないので docstring の Known gaps 行き (`OC` §1.12 の 71) の候補。本変更セットでは書いていない。

## 5. 運用上の教訓

- Sonnet の session limit で実装担当 2 名が途中で落ちた。worktree の編集は残る。同じ agent を SendMessage で再開すれば文脈も残る。
- 並行 worktree (WP-1 / WP-2 / WP-3 / WP-6 を別 worktree) で待ち時間を縮めた。`git add -N` 済みのファイルがある worktree には merge できない (stash が失敗する)。commit してから merge する。
- 群のレビューを WP 単位の A / B 並列に分けた (作業指示書 訂正註 2 の 7)。レビュー担当の変異 spec は、実装担当が編集中の worktree では監督が実行しない (mutate の backup / restore が編集と衝突する)。
- 再現テストの停止点は「メソッドの入口」ではなく「文そのもの」に置くと、実装の構造に左右されない (WP-1 レビュー)。
- 直列化の枝の assert は順序 (A = R+1 かつ B = R+2) で固定する。集合で比べると偽の緑になる (WP-2 レビュー A-1、RA-1 で実証)。
- 計測器が private 属性に依存すると (perf_baseline の `_runtime`)、製品の構造変更で黙って壊れる。本物の object で組む test を置く。

## 6. 裁定

`OC` §1.15 の 77。全 140 行 (受け入れ監査の指摘・観察を含む): 起票 1 件 (R-120)、既知の穴 0 件 (候補 1 件は §4 の G。表では観察)、観察 30 件、直した 109 件。語は `OC` §1.15 の 77 の 4 語 (作業指示書 訂正註 7 の 2)。表の順は時系列で、後の行が前の行の裁定を覆したもの (CH-0547 の (ii) → (i)、訂正註 8) は両方を残す。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 起草・(a)〜(k) (作業指示書の疑義 11 件) | 直した | 訂正註 1 (WO §6) |
| 起草・(k) delete の確認句も revision を読む | 観察 | DML の確認句の窓は設計の 3 窓・D-3 の外 (訂正註 1 の 11)。後日の起票は自由 |
| 実装 WP-3・逸脱 1 (IDLE の接続は rollback を呼ばない) | 直した (受け入れ) | 結果は設計と同じ (V30 で固定)、`txn_count` の計数を汚さない |
| 実装 WP-3・判断 3 (audit sink の写像は `AuthorizationStateUnavailable` のまま) | 直した (受け入れ) | 現行の観測可能な挙動の不変 (M-2) |
| 実装 WP-2・疑義 (r2db の plan 無し schema 操作を止めない) | 直した (WP-6 で lock の後の地点へ移す指示) | hook の文との一致 |
| 実装 WP-2・疑義 (r2db in-process は plan token の計算点で止める) | 観察 | revision の読みの後・lock の内側で同じ観測になる |
| レビュー WP-1 A・1 / B・1-1 (開1・開3・開4 の停止点が backend メソッドの入口) | 直した | 差し戻し 1: `_execute` の文フィルタへ |
| レビュー WP-1 A・2 (未完了の枝が経過時間だけ) | 直した | 差し戻し 2: `pg_stat_activity` の lock 待ち観測 |
| レビュー WP-1 B・1-2 (deferred spec の分割) | 直した | 差し戻し 3 |
| レビュー WP-1 B・1-3 (完了条件 9 が r2db に掛からない) | 直した | V9r を足した |
| レビュー WP-1 B・1-4 (報告と log のずれ、完了フラグ) | 直した | 差し戻し 4 |
| レビュー WP-1 B・1-5 (両 peer の同名 test helper が同型性テスト未登録) | 観察 | test 内部の helper、中身は peer の形の差、未登録の同名 helper は既に 144 件。登録は Class D の集合変更 |
| レビュー WP-1 B・観察 (開4 の現数の数え方が product と別式) | 観察 | 一致しており、ずれれば大きく落ちる |
| レビュー WP-3 A・1 (acquire(timeout) が接続の新設と ping の時間に効かない) | 直した (接続の新設) / 観察 (ping) | 新設は `connect_timeout = min(構築値, max(1, ceil(残り)))` で deadline に従わせる (K-9 の趣旨)。ping の上限は R-115 からの既存の性質で、本件の範囲外 |
| レビュー WP-3 A・2 (掃除の drain 中に同じ pool の acquire から idle が空に見える) | 直した | `_idle.mutex` の下で stale 分だけ queue から除き、close は mutex の外 |
| レビュー WP-3 A・3 (統計の畳み込み元の列挙が古い) | 直した | docstring に `_close_stale_idle` を足す |
| レビュー WP-3 B・1 (INERROR の rollback が未固定、VB1 生き残り) | 直した | 差し戻し 1 (実 PG のテスト + V30b) |
| レビュー WP-3 B・2 (「必ず rollback」との乖離) | 直した (訂正註 2) | IDLE では往復なし、観測は同値 |
| レビュー WP-3 B・3 / A・3 (列挙が古い) | 直した | 差し戻し 4 |
| レビュー WP-3 B・4 (module docstring の不整合) | 直した | 差し戻し 5 |
| レビュー WP-3 B・5 (証跡の置き場所) | 直した | `export SP` |
| レビュー WP-3 B・6 (test 34 の空振り assert) | 直した | 差し戻し 8 |
| レビュー WP-3 B・観察 (他 application の idle を閉じる是非) | 観察 | 設計 L-1 どおり。lookup も返却も無い |
| レビュー WP-2 A・1 (直列化の枝が revision の順序を固定しない、RA-1 で実証) | 直した | A == R+1 かつ B == R+2 |
| レビュー WP-2 A・2 / B・2 (plan 無しの節が未実現・未検証、r2db の停止点は照合の前) | 直した (確定文を改めた) | hook / 条件文を plan / dry_run 付きに限り、停止点を「照合に使う revision の読みの後」に |
| レビュー WP-2 A・3 (r2db の停止点は照合の前、観測上等価) | 観察 → WP-7 で Status に開示 | 照合は純関数で入力は停止点で確定 |
| レビュー WP-2 A・4 / B・6 (実現の表記、HISTORY の引用) | 直した | 差し戻し 6・7 |
| レビュー WP-2 B・1 (CONFORMANCE_ADAPTER_V1.md v1.20 §30 が無い) | 直した (訂正註 2、WP-7) | R-115 の先例 |
| レビュー WP-2 B・3 (完了条件 14 は V14b だけでは担保できない) | 直した | V14a は監査照合、WP-6 後に再実行 |
| レビュー WP-2 B・4 (in-process の停止に変異が無い) | 直した | V15b (赤を実測) |
| レビュー WP-2 B・5 (docstring の出所) | 直した | M-13 が出所 |
| レビュー WP-2 B・7 (M-15 の句) | 直した (訂正註 2) | — |
| レビュー WP-2 B・8 (register の緑は完了ゲート待ち) | 観察 (記録) | §5 に書く |
| 再確認 WP-1・1 (lock 待ち観測の上限が product の lock_timeout より長く診断が出ない) | 直した | `_LOCK_OBSERVE_S` を新設、V10 を後送り spec に |
| 再確認 WP-3・1 (`max(1, …)` の退行が未検出) | 直した (監督) | timeout 0.0 の case + V26c (赤を実測) |
| 再確認 WP-3・2 (実際の下限は psycopg の 2 秒) | 直した (docstring) | 式は変えない ((a)) |
| 再確認 WP-3・3 (上限到達の段で他 thread の close の空きを見直さない) | 観察 | 既存の性質、窓は close 1 回分 |
| 再確認 WP-2・1 (HISTORY の改訂理由が事実と食い違う) | 直した (監督) | — |
| 再確認 WP-2・2 (port docstring 第 3 段落の古い言い回し) | 直した (監督) | — |
| 再確認 WP-2・3 (hook の dry_run だけの操作の hold が未観測) | 観察 → WP-7 の Status cell に開示 | C-34 の命題は plan。hook の文はそのまま |
| 実装 WP-6・判断 1 (replay が lock の背後で止まらない test + Vx1) | 直した (受け入れ) | docstring の断言の裏付け |
| 実装 WP-6・判断 2 (R-35 の test の観測点を advisory lock 待ちに) | 直した (受け入れ) | 最終 assert は不変、Vx2 で固定 |
| 実装 WP-6・副作用 (replay が R-1 の完全性ガードより前に記録から答える) | 観察 → 引き継ぎ書に開示 | 契約 :837 (再送は記録から答える) に合う |
| 実装 WP-6・疑義 (keyed の schema 操作が件数 lock を持ったまま 3a を待つ) | 観察 | 設計 L-6 と同形 (peer 対称)。対案 (3a → 1 → 2) は replay の費用 |
| レビュー WP-6 B・1 (CH-0069 / CH-0071 のコメントが新しい実測と逆、add_field の lock mode の pin が消えた) | 直した | 訂正を code-history に追記、docstring を合わせ、add_field の SQL 文字列 pin を足す (RB1 が緑 = 穴あり) |
| レビュー WP-6 B・2 (advisory lock の 3 定数の区別が未固定、RB2 が緑) | 直した | 3 定数が互いに異なることを pin するテスト |
| レビュー WP-6 A・1 (keyed の要求が無関係な schema 操作の後ろに並ぶ = r2db の退行) | 直した | 順序を per-key → lookup → 3a → 件数 lock に (MitateDB の D-3 順との非対称は依頼者確認 M-17) |
| レビュー WP-6 A・2 (r2db の 開3 相当が開いている、WP-6 前から) | 起票 R-120 | 設計 K-7 (依頼者裁定 Q-5) が r2db の窓を 3 つに限った。利用者が気づく (宣言に反する行) |
| レビュー WP-6 A・3 (dry-run が 3a の下で読むことが未固定、RA1 緑) | 直した | test + RA1 |
| レビュー WP-6 A・観察 (83 の「:2106 より前」と実装) | 観察 (訂正註) | 趣旨を満たす |
| 再確認 WP-6・1 (per-key lock の 2 引数形が未固定、RC1 緑見込み) | 直した (監督) | 文の pin を足し RC1 を赤で実測 |
| 再確認 WP-6・2 (旧形式行 (request_id 無し) の reap と store の行 lock の輪、WP-6 前から) | 観察 | 3a は関与しない。旧形式の行に限る。40P01 は SERVICE_UNAVAILABLE に写る |
| 実装 WP-4・判断 (catalog 読みを kind=schema の scope で / DDL 本体の `_set_timeouts` 打ち直しを削除 / F-12 の接続失敗で起動が止まる (型だけ変わる) / `prepared_stats` は pool から 1 本借りて probe / 構築時の `max_execution_ms` は deadline 無しの scope の timeout / 妥当でない entity 名は lock しない) | 直した (受け入れ) | 設計の枠内の実装詳細 |
| 実装 WP-4・受け皿 (`_CountingRLock` の class docstring を受け皿に移さず git に任せた) | 観察 | 参照を置く場所が無い (register が orphan で赤) |
| 実装 WP-4・疑義 1 (plan 付き DML と別 entity の schema 操作の競合: DML は 3a を取らない) | 観察 → 依頼者確認 (M-18 の問い) | 設計 D-4 / 範囲 (k) と同じ扱い。(b) は schema 操作中に DML が止まる費用 |
| 実装 WP-4・疑義 2 (replay が reap を commit しない) | 観察 (受け入れ (a)) | 設計 K-8 の帰結。次に commit する要求が reap する |
| 実装 WP-5・判断 1・2 (`lock=` の形の削除、README の 2 段落) | 直した (受け入れ) | 出す plug が無い。実測値の系列は註記して残す |
| 実装 WP-5・判断 3 (unreachable DSN の形) | 直した (受け入れ) | tools/tests の literal 走査 |
| 実装 WP-5・判断 4 (`prepared_stats` docstring の書き換えの受け皿) | 直した (追加指示) | 旧文を code-history に CH-ID で逐語登録 |
| 実装 WP-5・tools/tests 2 失敗 (WP-3 の test_r102_pool.py の admin DSN reader と 33 file pin) | 直した (追加指示) | reader を raise 形に、pin 33 → 34 |
| 実装 WP-5・疑義 (D-R102 の分母が単位の違う数の和) | 観察 | D-R102 は計測前に固定した規則 (§8)。開示として記録 |
| レビュー WP-4 B・1 (CH-0547 の参照行が塊の途中、fence が塊全体でない、見出しの change set 7、存在しない `schema`) | 直した ((ii)) | 元の塊 :646-695 全体を fence に、参照行は塊の末尾、新 5 行は別の塊 |
| レビュー WP-4 B・2 (provenance の赤の報告が再実行と合わない、3 file 分が抜け) | 直した | 7 file の出力を逐語で報告 |
| レビュー WP-4 B・3 (http adapter の pool_size=6 に証拠無し) | 直した | test + 変異 V65b |
| レビュー WP-4 B・4 (V48 の赤は stale plan の枝だけ、docstring が実測と食い違う) | 直した | docstring を実測に合わせ、記録に残す |
| レビュー WP-4 B・5 (`_acquire_advisory` の `except psycopg.Error` が VALIDATION_FAILED に写る) | 直した ((b)) | 接続断は `StorageTransientError` (503)。新設箇所は M-1 の凍結の外 |
| レビュー WP-4 B・6 (test のコメントが消えた仕組みを現在形で書く) | 直した | — |
| レビュー WP-4 B・7 (書き直した文頭の古い台帳ラベル、CH-0185 の列挙) | 直した | — |
| レビュー WP-4 B・8 (a) (完了条件 68 の「4 plug」) | 直した (訂正註) | MitateDB は 3 plug。C-34 は 6 adapter |
| レビュー WP-4 B・8 (b)(c) (報告の `4 passed`、R-120 の行は WP-4 で入った、版数は WP-7) | 直した (報告 / 訂正註) | — |
| レビュー WP-4 A・1 (timeout が入口 1 回だけで execution_ms が要求全体の上限にならない) | 直した ((a) の限定形) | 競合した取得の後に残り時間で打ち直す。競合なしでは往復 0 |
| レビュー WP-4 A・2 (perf_baseline の `--roundtrip` が `backend._runtime` を読んで黙って欠落) | 直した (WP-5 担当) | matcher を pool の形に作り直し、test の偽物も |
| レビュー WP-4 A・3 (F-12 の refusing cell の拒否時点が前倒し: 不正な形でも 503) | 観察 → WP-7 の M-12 の註 | どちらも拒否。F-12 状態の application に限る |
| レビュー WP-4 A・4 (capabilities_document.py の docstring が偽) | 直した | — |
| レビュー WP-5 A・1 (`prepared_stats` が 1 本だけ借りて K≥2 で DBTIME が生涯値、acquire の例外が伝わる) | 直した (WP-4 担当) | idle の全接続を acquire 無しで probe (r2db と同形) |
| レビュー WP-5 A・2 (block 形失敗時に waits を数えない) | 直した (WP-4 担当) | waits は block 形に入った回数、acquire は成功のみ |
| レビュー WP-5 A・3 (role 行の acquire に入る probe 以外の借用の開示) | 直した (README) | — |
| レビュー WP-5 A・4 (ROUNDTRIP の xacts に idle ping が入る) | 直した (README の開示) | 判定に使わない行 |
| レビュー WP-5 B・1 (block 形失敗時の waits) | 直した (WP-4 担当、A・2 と同じ) | — |
| レビュー WP-5 B・2 (matcher の test が偽物の属性名に頼る) | 直した (WP-5 担当) | 本物の `PostgresBackend` を接続なしで組む test + `_dsn` を消す変異 |
| レビュー WP-5 B・3 (test_r102_request_scope.py は WP-5 の触ってよいパスの外) | 観察 (訂正註 7) | 監督の発注で許していた (§2.5 の表の外) |
| レビュー WP-5 B・4 (README :438 が R-79 の史実を書き換え) | 直した (WP-5 担当) | — |
| レビュー WP-5 B・5 (matcher の呼び出し時点の docstring) | 直した (WP-5 担当) | — |
| レビュー WP-5 B・6 (schema_lock 形の判定が否定形) | 直した (WP-5 担当) | 4 key が揃う正の条件 |
| レビュー WP-5 B・7 (V74 の「競合なしで増えない」側に変異が無い、V74b) | 直した (WP-4 担当の spec に) | — |
| 起草 WP-7・4 (CM に r2db の schema lock と C-34 の主張が無い) | 直した | 追補で足す |
| 起草 WP-7・5 (runbook §10.10 item (8) の式が永続接続前提) | 直した | pool の形で引き直し (版 12) |
| 起草 WP-7・6 (WO の `CR`:509-531 は 0012 の表) | 観察 (訂正註) | 式は :540 |
| 起草 WP-7・9 (表の外で足した CM_HISTORY 3 件・Status 4 件・CONFORMANCE_ADAPTER §22.1/§25.3 の註) | 直した (受け入れ) | 行を消さず註で覆す規律 |
| 起草 WP-7・10 (C-34 Status: r2db in-process に赤の変異無し、V14a の再実行記録無し) | 直した (監督が WP-6 後に V14a を実行し記録) | — |
| 実装 WP-4 差し戻し後・残る赤 (`--base main cell.py` §4.1 (3) :554「保護参照を持つ文を消せない」、(2) :547 新 5 行の塊) | 観察 (正当な赤) | 消した文は CH-0547 の fence に逐語で残る。検査器が「移動 + 参照保持」を区別しない形は既知の穴の候補 (製品の欠陥は通らない) → 引き継ぎ書に |
| 実装 WP-4 差し戻し後・判断 (per-key / 件数 lock も try → block 形に、`DataError` は `ValidationError` のまま、`map_idle` を pool に追加) | 直した (受け入れ) | 設計の枠内 |
| 起草 WP-7・追補の疑義 (`ops inventory` item (8) の式が runbook の新しい式と食い違う) | 直した | ops.py の application 項を pool の形に (小 WP、訂正註 5) |
| 再確認 WP-4/5・1 (perf docstring の PRE の時点) | 直した (監督) | — |
| 再確認 WP-4/5・2 (`map_idle` の例外時の put-back が未固定、RR-MI1) | 直した (監督) | test + RR-MI1 赤 |
| 再確認 WP-4/5・3 (probe 中に死んだ idle 接続で `prepared_stats` が raise) | 観察 | 製品の経路に無い。r2db も同形 (peer 対称) |
| 再確認 WP-4/5・4 (README の `backend_calls` の 1 文) | 直した (監督) | — |
| 再確認 WP-4/5・5 (R-79 の史実の段落の参照先が消えた) | 観察 | 史実の文は逐語で残す |
| 再確認 WP-4/5・6 (報告に 2 file の provenance 出力が欠けていた) | 直した (記録) | 再確認レビューが再実行: capabilities (2)=1、pool (1)=1 (2)=8 |
| 再確認 WP-4/5・7 (設計 D-3 の timeout の項が「1 回」のまま) | 直した (設計 v0.6 の註 :194 の〈〉を test 名で埋める) | — |
| 実装 WP-7 ops・判断 (test の pin を実測で更新、docstring の書き換え) | 直した (受け入れ) | — |
| レビュー WP-7 B・1 (CM の timeout の主張が打ち直しと食い違う) | 直した | 起草担当が 52a の test 名で書き換え |
| レビュー WP-7 B・2・3・4・9(b) (G-2/G-3 の 35 件、版数行の回転の句、CM 版の行の r2db / Common、語の欠け) | 直した | — |
| レビュー WP-7 B・5 (CM_HISTORY の 2 件が逐語でない) | 直した | 撤回した Control 主張は逐語で移す (形 3.0 §3) |
| レビュー WP-7 B・6 (訂正註 5 が無い) | 直した | r102 の WO に訂正註 5 (HISTORY / config.md / :540 / ops.py を含めて補う) |
| レビュー WP-7 B・7 (platform_declarations.py:1036-1039 と adapter :1133-1135 の「persistent connections」) | 直した | 起草担当 (CH-0550 で登録) |
| レビュー WP-7 B・8 (r2db in-process の実現側を外す変異が無い) | 直した (監督が RB-wp7-1 を計測後に実行し Status に足す) | — |
| レビュー WP-7 B・9(a) (CM:873 の test 名が主張と逆) | 直した (起草担当が c29eb61 の現物で確かめる) | — |
| レビュー WP-7 B・9(c) (完了条件 91 の緑は完了ゲートでしか示せない) | 観察 (記録) | — |
| レビュー WP-7 B・9(d) (`RM` §1 の 1.0j 更新) | 直した | R-113 / R-115 の先例 |
| レビュー WP-7 A・1 (CM の timeout 主張 + 行参照 40 件) | 直した | 差し戻し 1・2 |
| レビュー WP-7 A・2 (r2db の R-120 の窓が CM Status に無い) | 直した | 差し戻し 3 |
| レビュー WP-7 A・3 (F-12 の主張が広すぎる) | 直した | 差し戻し 4 |
| レビュー WP-7 A・4 (CM:1878) | 直した | 差し戻し 2 |
| レビュー WP-7 A・5 (SI-01 の K-10 の主張が無い) | 直した | 差し戻し 5 (Control の code 参照、専用 test は作らない) |
| 計測 D-R102 round 1 (監督): MitateDB-http の K=1 p50 が +176〜226% (psycopg が ROLLBACK で prepared statement を捨てる。範囲の出口の rollback が原因) | 直した (M-19、訂正註 6) | 例外なしの範囲は読み取り transaction を COMMIT して返す。完了条件 57b |
| レビュー WP-7 B・8 (RB-wp7-1 の実測) | 直した | 赤を実測。C-34 Status に監督が追記 |
| 再確認 WP-7・1 (34b の test が「下限を K 倍しない」性質を固定しなくなった、V-ops-3 生存) | 直した | 入力を K≥2 で下限が勝つ形に + V-ops-3 |
| 再確認 WP-7・2 (SI-01 Evidence の文が test の観測を超える) | 直した | 観測した内容に書き換え |
| 再確認 WP-7・3 (main.py 4 箇所と pool.py:119 の「persistent connections」) | 直した | 現在形に (最終一括) |
| 再確認 WP-7・4 (test_ops_inventory の docstring の旧式) | 直した | — |
| 再確認 WP-7・5 (訂正註 5・6 は r102 の未 commit 分) | 直した (記録) | 最終 merge の変更セットで commit |
| 再確認 WP-7・観察 (ops.py の provenance 赤 3 件) | 観察 (正当な赤) | 現在の挙動の言い換え、経緯の記述ではない |
| 再確認 WP-7・観察 (r87 の test 名が現行と逆) | 直した | 改名 (最終一括) |
| 実装 WP-4 差し戻し 2・開示 (replay が reap を commit する — 前の「commit しない」の逆) | 観察 (記録) | 出口 COMMIT の帰結。test を作り替え |
| 実装 最終一括・開示 (test_r87 を test_main の前に回すと test_main の 2 本が 503 — main でも同じ) | 観察 | test の順序依存 (既存)。全体 run では出ない。後日の起票は自由 |
| 実装 最終一括・判断 (`commit()` は backend_calls に数えられないので README は往復の数として書いた、CM の claim を 250 字で 2 分割) | 直した (受け入れ) | — |
| 候補 4d7181a の tools/tests・`test_0f_both_peers_all_src_rev_vs_itself_is_green` (CH-0547 の basis block が companion から導出できない: 保護参照を持つ文の削除) | 直した | WP-4 レビュー B-1 の (i) に戻す: 消えた cell lock の経緯コメントは `_CountingRLock` と同じく git に任せ、CH-0547 の登録と参照行を外した (R-115 訂正註 9 (2) の先例)。`--register` と rev-vs-itself は緑 (c3e5ca7) |
| 監査・完了条件 90 (grep の前後値が材料に無い) | 直した | §5.4 に記録 |
| 監査・完了条件 97 (§5.2 / §5.4 が空) | 直した | §5.2 / §5.4 |
| 監査・完了条件 98a (`CM`:1469 の参照) | 直した | :481-482 |
| 監査・§3 の K=4 の p50 の前後 | 直した | round 2 の値を表 B に |
| 監査・§4 の tools/tests (候補 4d7181a で 1 failed = CH-0547) | 直した | c3e5ca7、最終候補で再実行 |
| 監査・観察 1 (cell.py の参照の 1 行ずれ) | 直した | 17 件を引き直し |
| 監査・観察 2 (引き継ぎ書の語と欠落) | 直した | 「追認」→ 観察、台帳の行を補う、訂正註 1〜8 |
| 監査・観察 3 (計測の木の dirty) | 直した (開示) | §5.3 |
| 監査・観察 4 (変異 id の衝突) | 観察 | 記録から追うときの注意 (訂正註 8) |
| 監査・観察 5 (固定 sleep で待ちの到達を代用) | 観察 | 製品の緑に影響なし |
| 監査・設計疑義 (CH-0547 の (i) / (ii)) | 直した ((i)、訂正註 8) | 常設の検査が緑であることを優先。覆した根拠と日付を訂正註に |
| 監査・開示 (最終の製品コード後に再実行した変異は 4 件、V73 の old が無い) | 観察 | 最終ゲートが全 test を回す。V73 の性質は test が固定 |

## 追記 — 2026-10-01 依頼者の確認

依頼者 (逐語): 「確認事項は了承します」。§4 の A〜G は確定 (M-18 は (a))。runbook §10.8 は 12 / accepted、`CM` 3.15、台帳 v1.147、設計 v0.7 §11.2 (変更セット `r102-accept`、記録のみ)。G (検査器の既知の穴) は次の変更セットで `tools/check_comment_provenance.py` の docstring の Known gaps に書く。§4 の「依頼者判断待ち」は無くなった。
