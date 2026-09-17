# Work Order: MitateDB operation_depth platform upgrade

- 台帳: `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-45** (v1.50、2026-09-16)。
- 状態: **起票のみ。設計・レビュー前であり、本書の手順はまだ実行してよい手順ではない。**
- 来歴: 2026-09-14 に worktree `.claude/worktrees/mitatedb-operation-depth-platform-plan` で未コミットのまま起票された版を、2026-09-16 に監督が取り込んだ。起票時の台帳番号 R-37 は main の R-37 (モジュール分割のリファクタ) と衝突したので R-45 に当て直した。下の「起票原文」の番号付き手順 1〜4 は語句を変えていない。依頼の経路と制約は引き継ぎ書 `docs/work-orders/HANDOVER_20260916_FABLE2.md` 付録 C。
- Mitate 側の正本 (読み取り専用): `../Mitate/decisions/DM-0052-data-service-platform-upgrade-for-operation-depth.json`、`../Mitate/docs/design/data-service-operation-depth-platform-upgrade.md` v1.2、`../Mitate/docs/work-orders/data-service-operation-depth-platform-upgrade.md` v1.2。

## 起票原文 (2026-09-14)

- 変更クラス: D
- 対象: MitateDB-apiのCloud SQL/Cloud Run Data・Control運用。共通API、Application、validation Job/bridge/credentialは対象外。
- 目的: product reassessment F9の`operation_depth`を安全に公開・強制する。

1. DSN、credential、tokenを出さないread-only経路でdeclarations、migration、per-application upgrade、isolated/prod tuple、rollback、DDL lock/停止条件を確認する。状態不明はblocked。
2. `MitateDB-api/docs/cloud-run-cloud-sql.md`へ、0007、0011、独立した0012、per-application upgrade、declaration、legacy env除去、Data/Control restart、health、traffic、rollbackのreview済み手順を置く。
3. isolatedで同一candidate digestの`operation_depth=13`、13受理、14拒否を証明する。
4. Sol受理後だけproduction Data/Controlを更新し、独立監査後にMitate側F9を再判定する。

## 取り込み時の註 (監督、2026-09-16)

- 手順 4 の「Sol受理」は起票原文の語である。本リポジトリでの受理者 (独立レビュー・依頼者裁定のどちらか、または両方) は設計で確定する。
- 依頼で指定された制約 (いずれも厳守): 本番を変えない (migration・declaration・restart・candidate・traffic・Job・bridge・probe・fixture・promotion をしない、secret の rotate / revoke / delete をしない、Cloud SQL のリソースを消さない)。**credential の値を出力しない経路が設計とレビューで受け入れられるまでは、本番を読むこともしない。** DSN・credential・token・credential を含む URL を出力・ログ・文書・コミットに置かない。共通の Data Service API の spec、Mitate の契約、mitate-application の F9 ゲートを変えない。`MitateDB-api/docs/f9-execution-assets-v1/` は参照用に限り証拠にしない。依頼者が言うまで push しない。
- 順序: 手順 1 の経路の**設計**は文書のみなので先行できる。実装・テスト・runbook の変更は R-37 WP-5 (MitateDB-api の `backend_postgres.py` と `config.py` の import を削る) の統合後に始める。
- Gate-0 の確認項目には、上の 6 状態に加えて**旧式の base URL 設定 (`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`) の有無**を含める。各項目は confirmed / blocked / unknown で報告し、unknown は blocked と同じく先へ進まない。
- 変更クラスの最終判定は `docs/design/ROADMAP_POST_PHASE7_V1.md` §9 の 8 の表で行う。

---

## 1. 版数と位置づけ (2026-09-16 追記。上の冒頭・起票原文・取り込み時の註は書き換えない)

- **v1.0 (2026-09-16)。** 本節以降を Change Set Manifest として追記した。
- **v1.1 (2026-09-16)。** 起草時の疑義 1〜6 への監督裁定 W-1〜W-6 と、反映時の疑義への監督裁定 W-7・W-8 を §2.8 に逐語で置き、§2.3〜§2.6 と各 WP に反映した (v1.0 は未コミットの起草版であり、受け入れ前なので本文に反映した)。
- **v1.2 (2026-09-17)。** 台帳 R-45 の WP-E (依頼者裁定 2026-09-17 の (a)〜(e) による 4 件と、起草時の疑義・独立設計レビューの指摘への監督裁定 E-R1〜E-R20) を §6A に、WP-D の訂正註を §6.1 に追記した。§7 の番号を保つため WP-E の節は §6A とした。§1〜§6 と §7 の既存の本文は書き換えていない。
- **v1.3 (2026-09-17)。** WP-E の統合時の訂正註 E-1〜E-5、監督裁定 E-S1〜E-S11、監査照合の逐語記録 5 件を §6A.11 に、依頼者の回答 (R-48・R-47・条件 (d)) を §6A.12 に追記した。§6A の本文と §1〜§7 の既存の本文は書き換えていない。R-48 は本書の WP-F (WP-E の次の 1 本) で解消する (§6A.12。枠決めは別途 §6B)。
- **v1.4 (2026-09-17)。** 台帳 R-48 を解消する WP-F (依頼者裁定 2026-09-17 の「migration 0013 の形」と監督裁定 F-R1〜F-R33) の manifest を §6B に、WP-D の訂正註 WPD-4 を §6.1 に追記し、§6A.11 の E1-6 の監査照合の記録を統合コミットの実測で埋めた。§7 の番号を保つため WP-F の節は §6B とした。§6A の本文と §1〜§7 の既存の本文は書き換えていない。
- **v1.5 (2026-09-18)。** WP-F の統合時の訂正註 F-1〜F-5、監督裁定 F-S1〜F-S10・F-S11、コードレビュー (独立 1 回) の指摘と差し戻し 1 の裁定 R1-1〜R1-10、監査照合の逐語記録 6 件、完了ゲートを §6B.11 に、WP-D の訂正註 WPD-5 (0013 の適用の前提と依頼者裁定による直し方) を §6.1 に追記した。§6B の本文と §1〜§7 の既存の本文は書き換えていない。
- **v1.6 (2026-09-18)。** WP-D の実施記録と監督裁定 (経過、依頼者裁定 (Gate-0 の入口、案 A) の逐語、差し戻し 1〜4 とレビュー 5 の指摘への裁定の一覧、受理の記録 (W1-D1 版 2・W1-D2 版 2・W1-D3 版 5)、完了条件 19 件の監査照合の表、触るファイルの訂正註、統合コミットの欄) を §6.2 に追記した。§6・§6.1 と §1〜§7 の既存の本文は書き換えていない。
- **v1.7 (2026-09-18)。** §6.3 (R-45 の受け入れ監査と監督の受け入れ判定、証拠不足 6 件への裁定 A-1〜A-6、記録の食い違い 3 件の訂正) を足した。§3〜§6B の本文は書き換えていない。
- 設計: `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` v0.5 (以下「設計」。設計レビュー 2 回反映済み、依頼者裁定 Q-1〜Q-7 はすべて推奨を採用、設計 §6 冒頭の表)。本書は設計の決定 D-1〜D-11、裁定 Z-1〜Z-36、依頼者裁定 Q-1〜Q-7 と、本書 §2.8 の監督裁定 W-1〜W-8 を WP に割り付ける。裁定文・却下案・背景は写さず設計の節番号で指す (`RM` §9 の 9)。
- 台帳: `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-45 (v1.52)。
- 本書で条項番号だけを書くとき (「§1.5 の 40」等) は `docs/work-orders/OPERATING_CONDITIONS.md` の条項を指す。
- **本書の範囲は、起票原文の手順 1 の読み取り経路 (設計 §1.1 の Gate-0 の 10 項目) の実装・テスト・runbook と、起票原文の手順 2 の runbook の手順 (W-1) までである。** 本番を読む手順・更新する手順は runbook に書くが、本書の WP の中では実行しない (§7)。

## 2. 共通の枠

### 2.1 着手条件と基点

- **全 WP は、R-37 WP-5 (`docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.46) の main 統合後に、その時点の main で基点を取り直して着手する** (取り込み時の註の「順序」、設計 D-6。WP-5 が MitateDB-api の `backend_postgres.py` と `config.py` を動かすため)。
- 着手時に、設計 §3・§3.1 が引くファイル名・関数名・サブコマンド名が基点に実在することを `grep` で再照合し、1 件でも無ければ止まって監督へ上げる (設計 D-6 は行番号でなく名前で引く)。
- 基点の記録欄 (監督が着手時に記入する。記入するまで着手しない):

| WP | R-37 WP-5 の統合コミット | 基点 main | 名前の再照合の結果 |
|---|---|---|---|
| WP-A | `0fa4648` (縮小版 WP-5。依頼者指示 `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md`) | `0fa4648` | 全件実在 (設計 §3・§3.1 の名前、欠落 0) |
| WP-B | `0fa4648` | `8a2fe41` (WP-A・WP-C 統合後) | 全件実在 (欠落 0) |
| WP-C | `0fa4648` | `9dd7e02` (WP-A 統合後。WP-B より先に着手 — 監督が規模の小さい WP-C を先にした) | 全件実在 (欠落 0) |
| WP-D | (着手時に記入) | (着手時に記入) | (着手時に記入) |

### 2.2 全 WP に掛かる規律

- **触らないパス (全 WP)**: `spec/`、`conformance-tests/`、`security/CONTROL_MAPPING_HISTORY.md` (追加だけで旧文の移動は生じない)、`MitateDB-api/docs/f9-execution-assets-v1/` (参照用に限り証拠にしない。取り込み時の註)、`security/SECURITY_INVARIANTS_V1.md`、`security/THREAT_MODEL_V1.md` (設計 §4 の Security Invariants の扱い)、`docs/work-orders/OPERATING_CONDITIONS.md`、`CLAUDE.md`、`tools/public_value_scan.py`、`docs/design/` (記録は監督)。
- **本番へのアクセスをしない (全 WP)。** 本番を読むことも含む (取り込み時の註の制約)。テスト・変異・runbook の検証は使い捨てのクラスタと合成値だけで行う。
- **実値を書かない**: ホスト名・プロジェクト ID・インスタンス名・digest の実値・DSN・credential を、コード・テスト・fixture・runbook・報告に置かない (設計 C5、§1.9)。runbook の値は形 (`<service>`・`<region>`・`<revision>` 等) で書く (設計 D-1 platform 層)。
- **実装担当は root suite・`conformance-tests`・`tools/dev/gate.py` を回さない。** 回してよいのは各 WP の「実行するコマンド」に列挙したものだけである (`ROLES` の共通運用ルール 3)。完了ゲートは監督が単独で実行する (§1.3)。
- 設計に無い検査・機構が要ると分かったら、実装前に監督へ上げる (§1.5 の 37)。
- 変異は 1 行 1 件以上とし、変異定義では変異ごとに赤になる test id を 1 つずつ名指しする (設計 §7 の前文、`RM` §9 の 9)。表の test id の名前は予想であり、実装担当が実名に置き換えて報告する。
- 監査照合の行は、照合対象の逐語記録 (実行したコマンドと集計行、または `file:line`) を設計に残すこと自体を完了条件とする (§1.5 の 40)。記録先は設計の実施記録 (監督が追記する)。本番の実行結果は記録しない (設計 D-11)。
- 各 WP の完了条件 47 (公開値) と 50 (対応表の漏れ 0) は設計 §7 の同番号の行を WP ごとに適用したものである (設計 §11)。

### 2.3 変更クラス

変更セット全体は **Class D** (設計 D-7、依頼者裁定 Q-6 (a))。**契約版数は 1.8.0 のまま据え置く** (Q-6 (a))。WP ごとのクラスは `RM` §9 の 8 の表と W-5 により次のとおり。**全 WP が `security/CONTROL_MAPPING.md` に対応行を足すので、全 WP が Class D である** (W-5)。

| WP | 触れる対象 | クラス | 理由 |
|---|---|---|---|
| WP-A | 両 peer の `ops.py` (登録済み helper `cmd_verify_declarations` の本体)、`_ISOMORPHIC_TARGETS` への行の追加、`security/CONTROL_MAPPING.md` | **D** | 集合の増減と `security/` 配下 (`RM` §9 の 8) |
| WP-B | `MitateDB-api/src/mitatedb_api/ops.py` (登録済み helper の本体に触れない)、新規テスト、`security/CONTROL_MAPPING.md` | **D** | `security/` 配下 (W-5)。登録済み helper の本体に触れる必要が出たら両 peer の変更になるので、止まって監督へ上げる (§1.5 の 37、設計 D-9) |
| WP-C | `MitateDB-api/src/mitatedb_api/ops.py` の `_run_upgrade_script` / `_run_deprovision_script` (W-1)、`MitateDB-api/tests/` の新規テスト、`security/CONTROL_MAPPING.md` | **D** | `security/` 配下 (W-5)。登録済みのテスト helper (`tests/test_ops_verify_declarations.py` の `_run_psql` 等) の本体に触れない |
| WP-D | `MitateDB-api/docs/cloud-run-cloud-sql.md`、`security/CONTROL_MAPPING.md` (runbook の受理記録の対応行) | **D** | `security/` 配下 (W-5) |

手順は `ROLES` の「Class C・D」節の 4〜9 に従う (設計文書・設計レビュー 2 回・依頼者裁定は済み)。実装 WP (A〜C) は `implementer` (テンプレ 2) → `reviewer` (テンプレ 5) → 監督の統合前ゲート。WP-D は `drafter` (テンプレ 3) → `reviewer` (テンプレ 4、設計レビューのモード。W-1 の受理)。全 WP のレビュー完了後に `evidence-auditor` (テンプレ 6) を 1 回。

### 2.4 `_ISOMORPHIC_TARGETS` への登録と `security/CONTROL_MAPPING.md` の対応行を扱う WP と、その位置

- **`_ISOMORPHIC_TARGETS` への登録は WP-A だけが扱う** (設計 §11 の WP-A、§7 の 48)。WP-B〜WP-D は `_ISOMORPHIC_TARGETS` に触れない (設計 D-9: `inventory` は MitateDB-api のみで登録しない)。
- **登録を実装 WP の先に独立の WP として置かず、WP-A の中で、登録対象の同名テストと同じ変更セットで行う。** 根拠:
  1. §1.5 の 40b が、件数・名前で固定する静的テスト (`_ISOMORPHIC_TARGETS` を名指し) を対象の変更と同じ変更セットで実測により更新することを求める。
  2. 登録行は両 peer に実在する同名のテストを指す。テストより先に登録すると同型性テストが存在しない名前を比べることになり、テストより後の別の変更セットにすると、その間の main に未登録の同名テストが残る (§1.5 の 38)。
- **`security/CONTROL_MAPPING.md` の対応行は、各 WP が自分のテスト (WP-D は runbook の受理記録) と同じ変更セットで足す** (W-5)。Q-6 (a) の「本設計の受理時に」はこの意味に解する (W-5)。根拠: 同ファイルの更新規約 (冒頭の Update convention) は各節に現在の統制とその証拠 (テスト名・`file:line`) を持たせるので、証拠の無い時点では行を書けない。各 WP は同ファイル冒頭の Version 行の minor を 1 つ上げる (W-5)。文字数上限 (`MAX_BLOCK_LENGTH` / `MAX_LINE_LENGTH`) を超えそうなら詰めずに監督へ上げる (W-5)。実装担当は `conformance-tests` を回さないので、追加後の該当ブロックの文字数を scratchpad のスクリプトで測って報告し、監督がゲートで `conformance-tests/test_control_mapping_register.py` を確かめる。
- `ROLES` の Class C・D の 4 の「契約・conformance の WP を実装 WP より先に置く」は、本変更セットが `spec/`・`conformance-tests/` に触れない (設計 C4、D-7) ので掛からない。
- WP-A を WP-B より先に置く根拠: 両 WP は `MitateDB-api/src/mitatedb_api/ops.py` を共に触るので直列にする (設計 §11)。WP-A の例外出力の方針 (設計 D-2) を既存経路で先に確立し、WP-B の `inventory` が同じ方針の上に載る。

### 2.5 順序と触るファイルの重なり

順序: **R-37 WP-5 の統合 → WP-A → WP-B と WP-C (直列。どちらを先にするかは監督が着手時に決め、§2.1 の表に記録する) → WP-D (WP-B と WP-C の統合後)**。v1.0 の「WP-B と WP-C は並行してよい」は W-1・W-5 で両 WP が `ops.py` と `security/CONTROL_MAPPING.md` を触ることになったので成り立たない。

| WP | 触るファイル (実ファイル名) |
|---|---|
| WP-A | `r2db-api/src/r2db_api/ops.py`、`MitateDB-api/src/mitatedb_api/ops.py`、`r2db-api/tests/test_ops_verify_declarations.py`、`MitateDB-api/tests/test_ops_verify_declarations.py`、`r2db-api/tests/test_audit_query.py`、`MitateDB-api/tests/test_audit_query.py`、`security/CONTROL_MAPPING.md`、完了条件 19 の棚卸しで修正する経路のテストを置く両 peer の既存 ops テストファイル (着手時の棚卸しで確定し、訂正註で本表に足す) |
| WP-B | `MitateDB-api/src/mitatedb_api/ops.py`、`MitateDB-api/tests/test_ops_inventory.py` (新規)、`security/CONTROL_MAPPING.md` |
| WP-C | `MitateDB-api/src/mitatedb_api/ops.py` (`_run_upgrade_script` / `_run_deprovision_script` と、それらに `lock_timeout` の引数を渡す CLI の引数定義だけ。W-1・W-7)、`MitateDB-api/tests/test_platform_migration_reapply.py` (新規。名前は案)、`security/CONTROL_MAPPING.md` |
| WP-D | `MitateDB-api/docs/cloud-run-cloud-sql.md`、`security/CONTROL_MAPPING.md` |

| 組 | 重なり | 扱い |
|---|---|---|
| WP-A と WP-B | `MitateDB-api/src/mitatedb_api/ops.py`、`security/CONTROL_MAPPING.md` | **直列** (設計 §11) |
| WP-A と WP-C | `MitateDB-api/src/mitatedb_api/ops.py`、`security/CONTROL_MAPPING.md`。加えて WP-A の完了条件 19 は `_run_upgrade_script` の argv (DSN を渡す箇所、設計 §3.1) を修正しうる | **WP-C は WP-A の統合後** |
| WP-B と WP-C | `MitateDB-api/src/mitatedb_api/ops.py`、`security/CONTROL_MAPPING.md` | **直列** |
| WP-B・WP-C と WP-D | `security/CONTROL_MAPPING.md`。加えて WP-D の runbook は WP-B の `inventory` の引数・終了コード・出力と、WP-C の適用時の `lock_timeout` の渡し方を手順に書く | **WP-D は WP-B と WP-C の統合後** |

### 2.6 設計 §7 の行と監督裁定の割り付け (設計 §11、W-1〜W-8)

取り消し線の行 (8、9、10、25〜27、29、31、33、旧 35、45、45a) は割り付けない。本書で足した行は裁定の番号で呼ぶ (例: W2-1)。

| WP | 設計 §7 の行 | 裁定で足した行 | 件数 |
|---|---|---|---|
| WP-A | 16、17、18、19、48、49、47、50 | — (W-5 は 49 に反映) | 8 |
| WP-B | 1、2、2a、4、5、6、7、8a、8b、8c、10a、10b、10c、11、11a、11b、12、13、14、15、20、22、23、23a、25a、25b、25c、27a、27b、27c、29a、29b、30、31a、32、32a、33a、33b、34、34a、34b、34c、35、35a、35b、35c、36、37、47、50 | W2-1、W2-2、W4-1、W4-2、W4-3、W4-4、W5-B | 57 |
| WP-C | 39、40、41、42、43、44、45a′、45b、45c、46、47、50 | W3-1、W1-C1、W1-C2、W7-C1、W7-C2、W5-C | 18 |
| WP-D | 3、3a、9a、9b、21、24、28、38、38a、38b、47、50 | W1-D1、W1-D2、W1-D3、W7-D1、W3-2、W5-D、W6-1 | 19 |

### 2.7 実行するコマンドの形

`WT` は監督が割り当てる worktree、`SP` は scratchpad。変異定義は `$SP/r45-wp<x>-mutations.json` に 1 変異 1 件で置く (§1.10 の 64・65)。

```json
{"pytest": ["-q", "MitateDB-api/tests/test_ops_verify_declarations.py"],
 "mutations": [
  {"id": "A16", "expect": "red",
   "file": "MitateDB-api/src/mitatedb_api/ops.py",
   "old": "<cmd_verify_declarations の接続失敗経路で 1 件一致する行>",
   "new": "<生の例外文字列を出力する形>",
   "tests": ["MitateDB-api/tests/test_ops_verify_declarations.py::<16 の新規テスト>"]}]}
```

### 2.8 監督裁定 (W-1〜W-8、2026-09-16。W-1〜W-6 は起草時の疑義 1〜6、W-7・W-8 は v1.1 反映時の疑義 1・2 への裁定。逐語)

| 裁定 | 本文 (逐語) |
|---|---|
| W-1 | (疑義 1) WP-D (runbook) に次を足す: Q-1 (c) の migration ごとの互換性の表、Q-2 (c) のロック種別・停止時間の上限・適用時 `lock_timeout` の表、起票原文の手順 2 (0007 / 0011 / 0012 の適用、per-application upgrade、declaration、legacy env の除去、Data / Control restart、health、traffic、rollback)。完了条件は「独立レビュー (reviewer、設計レビューのモード) が表と手順を受理した記録」を監査照合とする。**適用時の `lock_timeout` を実際に渡すコード** (`ops.py` の `_run_upgrade_script` / `_run_deprovision_script` の psql 実行) は WP-C に置き、静的 pin テストと変異 (渡さない形 → 赤) を付ける。 |
| W-2 | (疑義 2) WP-B に JSON 出力の形の固定を足す: トップレベルと項目ごとのキー集合、判定語の閉じた語彙 (confirmed / blocked / unknown と `remediation-required` 注記) を pin。変異 = キーの改名・語彙外の判定語 → 赤。 |
| W-3 | (疑義 3) WP-C の再実行性テストは、稼働中 revision の source ref を特定する代わりに、**migration 列のすべての接頭辞 N (0..最新) を起点**として parametrize する (起点 N まで適用 → 候補 HEAD まで適用 → もう一度適用して差分 0 と終了コード 0)。どの ref が稼働中でも覆うので Q-5 (b) を満たす。本番の Gate-0 では (9) で attest した ref の N を記録するだけにする。 |
| W-4 | (疑義 4) `inventory` の終了コード: 0 = DB 層の全項目 confirmed、2 = いずれかが blocked / unknown、1 = ツール自身の失敗 (出力は固定文言のみ)。inventory の読み取りは接続ごとに `lock_timeout` と `statement_timeout` を短い固定値 (定数、静的 pin) で掛け、超過はその項目 unknown。具体値は WP-B の実装担当が定数として提案し監督が採否を決める。migration 適用時の `lock_timeout` の値は W-1 の runbook の表で migration ごとに決める。 |
| W-5 | (疑義 5) CONTROL_MAPPING の対応行は、**各 WP が自分のテストと同じ変更セットで**足す (証拠のテスト名が存在する時点で書ける)。Q-6 (a) の「受理時に」はこの意味に解する。対応行を足す WP は Class D (WP-A〜C。WP-D は runbook の受理記録を対応行に足すので D)。ファイルの Version 行は、その WP の変更で minor を 1 つ上げる。文字数上限を超えそうなら詰めずに監督へ上げる。 |
| W-6 | (疑義 6) WP-D に「production の手順より前に、isolated で `--quiet` のときの API 有効化プロンプトの既定応答を確かめ記録する」ゲート手順を置き、runbook にその手順があることを監査照合の完了条件にする。 |
| W-7 | (疑義 1) `_run_upgrade_script` / `_run_deprovision_script` は `lock_timeout` の値を**既定値の無い必須の CLI 引数**で受け取り、psql に渡す。値の出所は runbook の表の「per-application upgrade」「deprovision」の行 (WP-D に行を足す)。0007 / 0011 / 0012 は runbook で psql に `PGOPTIONS` 経由で表の値を渡す。WP-C の静的 pin は「値を psql に渡すこと」と「引数が無ければ CLI が拒否すること」を固定し、値そのものは固定しない。変異 = 渡さない形 → 赤、引数に既定値を与える形 → 赤。 |
| W-8 | (疑義 2) 接頭辞 N は migration 列を番号順に先頭から N 個適用したものであり、依存先を欠く起点は生じない (0011 を含む接頭辞は必ず 0007 を含む)。飛び飛びの起点は parametrize に含めない。 |

## 3. WP-A — 両 peer の例外出力の修正 (Class D)

**目的**: 両 peer の `cmd_verify_declarations` と棚卸しで見つかった ops の経路から、例外文字列・DSN の出力を除く。同名テストを `_ISOMORPHIC_TARGETS` に登録し、統制を `security/CONTROL_MAPPING.md` に版付きで対応付ける。

**読む正本**: 設計 §2 (C1)、§3.1、D-2、D-7、D-9、§6 Q-6、§7 の 16〜19・47〜50、§9.1 の Z-1・Z-4、§9.2 の Z-7・Z-16、§9.3 の Z-24・Z-30。§1.5 の 32・38・40・40b。`security/CONTROL_MAPPING.md` 冒頭の Update convention と Length cap measurement。

**使用テンプレート**: 2 (実装) → 5 (コードレビュー)。

| 触るファイル | 触らないファイル |
|---|---|
| §2.5 の WP-A の行 | §2.2 の全 WP 共通、`MitateDB-api/tests/test_ops_inventory.py`、`MitateDB-api/docs/cloud-run-cloud-sql.md`、`MitateDB-api/migrations/`、`r2db-api/migrations/` |

**着手時の手順**:

1. §2.1 の再照合。
2. **完了条件 19 の棚卸しを実装より先に行い、監督へ報告する。** 対象は両 peer の ops で、設計 §3.1 の表の経路 (両 peer の `main()` の `except psycopg.Error`、psycopg 以外の例外、`_upgrade_one_application` の `failure_detail`、`_run_upgrade_script` の psql 出力、psql の argv に DSN を渡す箇所) を名指しで含める (Z-1・Z-7)。報告は経路・`file:line`・修正の要否の一覧とする。
3. 設計 D-2 の方針 (例外文字列を出さず、型名と固定文言だけを出す) で直せない経路 (例: argv に DSN を渡す箇所) の直し方は、実装前に監督へ上げる (§1.5 の 37)。
4. 修正する経路ごとに、完了条件 11 と同じ形 (設計 D-2 の 3 段の assert) のテストと変異を 19-1、19-2、… の行として本節の表に訂正註で足す (設計 §7 の 19)。

**規則 (設計の指示の所在だけを示す)**:

- 番兵は DSN の user・password・host・dbname に別々の合成値で置き、assert の順序は設計 D-2 の 1〜3 (経路を通ったこと → 生の例外文字列に番兵があること → stdout / stderr に番兵が無いこと) に従う (Z-4・Z-7・Z-24)。
- 修正は両 peer に同じ形で入れる (Z-1)。両 peer に同名で足すテストは `_ISOMORPHIC_TARGETS` に登録し、件数の pin (`test_isomorphic_target_table_is_pinned_to_its_current_136_rows`、基点の件数) を実測で更新する (§1.5 の 38・40b、Z-16)。
- `security/CONTROL_MAPPING.md` の行は Q-6 (a) の「版付きの security-contract 決定」として、本 WP のテストと同じ変更セットで置き、Version 行の minor を 1 つ上げる (W-5)。1 行 1 主張・表を置かない・文字数上限は同ファイル冒頭の規約に従い、上限を超えそうなら詰めずに監督へ上げる (W-5、§2.4)。

**実行するコマンド**:

```bash
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_ops_verify_declarations.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- r2db-api/tests/test_ops_verify_declarations.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_audit_query.py -q -k isomorphic
tools/dev/pt.py --wait 1800 -C "$WT" -- r2db-api/tests/test_audit_query.py -q -k isomorphic
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests -q    # 修正後の回帰
tools/dev/pt.py --wait 1800 -C "$WT" -- r2db-api/tests -q        # 修正後の回帰
tools/dev/mutate.py "$SP/r45-wpa-mutations.json" -C "$WT" --wait 1800
python3 tools/public_value_scan.py <変更したファイル>
```

**完了条件 → 変異 → 赤になる test id** (番号は設計 §7 の行番号)

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 16 | MitateDB-api の `verify-declarations` の接続失敗経路で、設計 D-2 の 3 段の assert が成り立つ | `MitateDB-api/src/mitatedb_api/ops.py`: `cmd_verify_declarations` の接続失敗経路を生の例外文字列を出力する形に戻す | `MitateDB-api/tests/test_ops_verify_declarations.py` の接続失敗経路の新規テスト |
| 17 | r2db-api の `verify-declarations` で同じ assert が成り立つ (Z-1) | `r2db-api/src/r2db_api/ops.py`: 同じ箇所を同じ形に戻す | `r2db-api/tests/test_ops_verify_declarations.py` の同名の新規テスト |
| 18 | 両 peer の `cmd_verify_declarations` が同型のまま | 16 と同じ変異 (MitateDB-api 側だけを戻す) | `MitateDB-api/tests/test_audit_query.py::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` |
| 19 | 両 peer の ops の漏洩経路を実装前に棚卸しし、見つかった経路を同じ方針で直す (Z-1・Z-7) | **監査照合**: 着手時の手順 2 の棚卸しの一覧 (経路・`file:line`・修正の有無) を逐語で設計に残す。修正した経路は 19-n の行として変異を持つ | — |
| 48 | 両 peer に同名で足したテストを `_ISOMORPHIC_TARGETS` に登録し、件数の pin を実測で更新する (§1.5 の 38・40b、Z-16) | 2 件。(i) `r2db-api/tests/test_ops_verify_declarations.py`: 16/17 の新規テストの片 peer 側だけ本体を書き換える。(ii) `MitateDB-api/tests/test_audit_query.py`: 追加した登録行を 1 行外す | (i) `r2db-api/tests/test_audit_query.py::test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`、(ii) `MitateDB-api/tests/test_audit_query.py` の件数 pin のテスト |
| 49 | 新しい統制を `security/CONTROL_MAPPING.md` に版付きで対応付け、Version 行の minor を 1 つ上げる (Z-16、Q-6 (a)、W-5) | **監査照合**: 追加した行と Version 行の前後を逐語で設計に残す。あわせて該当ブロックの文字数の実測と、監督のゲートでの `conformance-tests/test_control_mapping_register.py` の結果行を残す | — |
| 47 | 追加・変更したテストと fixture に実値が無い (C5) | **監査照合**: `python3 tools/public_value_scan.py <変更ファイル>` の集計行を逐語で残す | — |
| 50 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表 (19-n を含む) の行数と対応数を残す | — |

**件数 (下限)**: 完了条件 8 件 (19-n を除く) = 変異を持つ行 4 件 (16・17・18・48。変異 5 件) + 監査照合 4 件 (19・49・47・50)。19-n は棚卸しの結果で増える。

### 3.1 WP-A の訂正註と監督裁定 (2026-09-16、統合時に監督が追記。§3 の本文は書き換えない)

**訂正註 A-1 (触ったファイル)**: §2.5 の WP-A の行に加え、次を触った。`MitateDB-api/tests/test_ops_upgrade.py`・`r2db-api/tests/test_ops_upgrade.py` (19-4〜19-6 と A-13・A-14 のテスト)、`MitateDB-api/tests/test_ops.py`・`MitateDB-api/tests/test_main.py`・`r2db-api/tests/test_application_audit.py`・`r2db-api/tests/test_constraints_declaration.py` (A-13 がテスト基盤 `tools/testpg/dsa_testpg.py` のプロセス全体への `PG*` の export と衝突したため、ops の subprocess 起動・`ops.main` 直接呼出しの箇所だけで `PG*` を除く。接続先・認証は DSN に明記された値のままであることを独立レビューが確認)。`_ISOMORPHIC_TARGETS` 登録済みの helper の本体には触れていない。

**訂正註 A-2 (19-n の行)**: 棚卸し (経路 1〜8) の結果、次を足す。経路 1 は 16・17 に統合、経路 7・8 は修正不要。

| # | 完了条件 | 変異 | 赤になる test id |
|---|---|---|---|
| 19-2 | 両 peer の `main()` の psycopg.Error は型名と固定文言だけ | 生の例外文字列に戻す | `test_main_psycopg_error_handler_never_prints_the_raw_exception_text` |
| 19-3 | 両 peer の `main()` は psycopg 以外の例外も traceback なしで固定文言 | `except Exception` を狭める | `test_main_catches_non_psycopg_exceptions_without_a_traceback` |
| 19-4 | psql 出力・`str(exc)` は実際の接続値を長い順・カンマ分割で伏せてから出す (MitateDB `_run_upgrade_script`・`_upgrade_one_application`、r2db `cmd_upgrade_applications`) | 伏せる呼出しを外す / 長い順を外す / カンマ分割を外す | `test_*_redacts_*` 系 |
| 19-5 | psql の argv に接続情報を置かず libpq の環境変数で渡す (3 箇所)。環境変数形の無い conninfo キーは拒否、親の `PG*` は除き、DSN が上書きしない接続設定変数が親にあれば拒否、psql 16 未満・不在は拒否 | argv に DSN を戻す / 拒否を外す / `PG*` 除去を外す / 版確認を外す 等 | `test_*_passes_connection_params_via_env_never_argv` ほか |
| 19-6 | MitateDB `_run_deprovision_script` の `_die` も伏せてから出す | 伏せる呼出しを外す | `test_run_deprovision_script_redacts_connection_values_before_dying` |

変異は最終 39 件すべて期待どおり (`restores verified 3/3 files (sha256 x2)`)。RV2 (`env.setdefault`) は A-9 の `PG*` 除去で等価変異になったので spec から外した。

**訂正註 A-3 (設計 §3.1 の例示)**: 「psycopg 以外の例外」の例に挙げた `_app_dsn` の `conninfo_to_dict` の解析失敗は、実測では `psycopg.ProgrammingError` (psycopg.Error の派生) であり経路 2 に落ちる。結論 (出力に漏れる経路であり同じ修正で塞がる) は変わらない。

**監督裁定 A-1〜A-20 (逐語)**

- A-1 (経路 1・2・3、19-2・19-3) 棚卸しのとおり直す。両 peer の `main()` は psycopg.Error とそれ以外の全例外を捕まえ、例外の型名と固定文言だけを stderr に出して非 0 で終わる (traceback を出さない)。経路 1 は完了条件 16・17 に統合する。
- A-2 (経路 4・6、19-4・19-6) psql の出力と `str(exc)` を**捨てずに、実際に渡した接続パラメータの値を完全一致で伏せてから**出す。伏せる対象は、ツールが psql / psycopg に渡した接続情報を `conninfo_to_dict` で分解した user・password・host・hostaddr・port・dbname の各値 (空でないもの) で、出力中の出現をすべて固定の伏字 (`<redacted>`) に置き換える。推測のマスク (正規表現で DSN らしきものを探す) はしない。SQL のエラー (制約違反・構文エラー等) の診断は残る。テストは設計 D-2 の 3 段 (経路を通った → 生の出力に番兵がある → 出力に番兵が無い) で、番兵を 4 要素それぞれに置く。変異 = 伏せる処理を外す → 赤。伏せる helper は両 peer に同名で置き (r2db は `cmd_upgrade_applications` の `failure_detail` に掛ける。r2db に deprovision の psql 呼出しは無いのでその経路は MitateDB のみ)、`_ISOMORPHIC_TARGETS` に登録する。
- A-3 (経路 5、19-5) psql の argv に DSN を置かない。接続パラメータは `subprocess.run(..., env=...)` で libpq の環境変数 (`PGHOST`・`PGPORT`・`PGUSER`・`PGPASSWORD`・`PGDATABASE`・必要なら `PGSSLMODE` 等、`conninfo_to_dict` の結果から) として渡し、argv には接続情報を含めない。根拠: argv は同じホストの他ユーザーからプロセス一覧で見えるが、環境変数は同じユーザーと root に限られる。`conninfo_to_dict` のキーのうち libpq の環境変数に対応しないものがあれば、その DSN は拒否して固定文言で終わる (黙って落とさない)。テスト: 番兵入りの DSN で、subprocess に渡る argv に 4 要素の番兵がどれも無いこと (subprocess.run を spy)、かつ env に正しく渡ること。変異 = DSN を argv に戻す → 赤。**MitateDB の `_run_upgrade_script`・`_run_deprovision_script`、r2db の `_run_upgrade_script` の全部に掛ける。**これらは WP-C (lock_timeout を渡す) と同じ関数だが、WP-C は WP-A の統合後なので重ならない。
- A-4 (経路 7・8) 修正しない。経路 8 (設計 §3.1 の「psycopg 以外の例外」の例示が実際は psycopg.ProgrammingError) は、監督が WP-A の実施記録で設計に訂正として記録する。
- A-5 (CONTROL_MAPPING) 対応行は **SI-10 (Error and Information Non-Disclosure) の両 peer のブロック**に足す。SI-14 の r2db ブロック (残り 78 文字) には足さない。Version 行を 2.0 → 2.1 にする。
- A-6 (19-n の表) 修正した経路ごとに 19-2・19-3・19-4・19-5・19-6 の行 (完了条件・変異・赤になる test id) を報告に書く。作業指示書への訂正註は監督が統合時に書く (実装担当は docs/ を触らない)。

- A-7 (指摘 1・2) レビューの修正案のとおり: host・hostaddr・port はカンマで要素に分け、対象値は空を除き重複を除いて**長い順**に並べ、`re.escape` した値を `|` でつないだ 1 つの正規表現で一度に置換する。両 peer 同じ形。
- A-8 (指摘 3) 許可表は、`conninfo_to_dict` が返しうるキーのうち **libpq (PostgreSQL 16) の文書に環境変数形があるキーをすべて**含める (host・hostaddr・port・dbname・user・password・passfile・channel_binding・service・options・application_name・connect_timeout・client_encoding・sslmode・sslcompression・sslcert・sslkey・sslrootcert・sslcrl・sslcrldir・sslsni・requirepeer・ssl_min_protocol_version・ssl_max_protocol_version・gssencmode・krbsrvname・gsslib・gssdelegation・target_session_attrs・load_balance_hosts・require_auth — 実装担当が文書と照合し、表とその出所を報告する)。環境変数形の無いキーは、**キー名を含む固定文言**で拒否し、既存の ops の設定エラーと同じ終了経路 (`_die` 等) で終える。キー名は秘密ではないので出してよい。値は出さない。エラー文を事実に合わせる。
- A-9 (指摘 5) 子プロセスの env は、親の env から **`PG` で始まる変数をすべて除いた**うえで DSN 由来の値を入れる (DSN に無い接続設定が親の `PGPASSWORD`・`PGSERVICE` 等で黙って補われないようにする)。テストは `monkeypatch.setenv` で親に `PGUSER`・`PGPASSWORD`・`PGSERVICE` を置き、子の env にそれらが残らない / DSN の値が入ることを確かめる。
- A-10 (指摘 6) src の新規コメント・docstring から経緯トークンを除き、CH-ID を採番して両 peer の `docs/code-history/<peer>/ops.md` に登録する (触ってよいパスに追加)。§4.1(2) の 21 件は 1 件ずつ分類して報告する: 位置ずれ (作業指示書 `WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.45 の訂正註 5 の類型) なら理由を書き、それ以外は直す。
- A-11 (指摘 8・既決) 両 peer に同名で置いた `_psql_connection_env` と `_LIBPQ_ENV_VAR_FOR_CONNINFO_KEY` を `_ISOMORPHIC_TARGETS` に登録する。表の仕組みが module 定数を扱えなければ、登録せずにその旨を報告する (その場合は監督が扱いを決める)。件数 pin を実測で更新する。
- A-12 (指摘 7) 修正後の実測に合わせて CONTROL_MAPPING.md SI-10 の文言を直す (主張は実測の後、§1.5 の 34)。

- A-13 (指摘 1。A-9 を補う) 子の env からの `PG*` 除去は維持する。加えて、**親の env にある接続設定の変数のうち DSN が上書きしないもの** (許可表の全環境変数と `PGSERVICEFILE`・`PGSYSCONFDIR`) が 1 つでもあれば、実行前に**変数名だけを含む固定文言**で `_die` する (値は出さない)。psycopg の接続と psql の接続の設定が食い違う状態を作らず、運用者に DSN への明記を求める (fail-closed)。テスト: 親に `PGSSLMODE` を置き DSN に sslmode が無ければ拒否、DSN に sslmode があれば受理。変異: 拒否を外す → 赤。このテストは RV3 (`k != "PGSERVICE"` への弱め) も赤にする形にする。
- A-14 (指摘 2) psql を起動する前に `psql --version` を読み、メジャー版が 16 未満、または版を読めなければ固定文言で `_die` する。テストは subprocess を spy して 15 と読めない出力で拒否、16 で受理。変異: 版の確認を外す → 赤。
- A-15 (指摘 3) provenance は判定 (b)。CH-0538〜0545 と両 peer の companion の 8 節を撤回し、新規のコメント・docstring は CH-ID を付けず経緯トークンを持たない形で残す。`--base 0fa4648` の結果を再取得し、残る赤を類型ごとに報告する (新しい塊の「CH-ID の無い塊の追加」、位置ずれ 21 件)。
- A-16 (指摘 4・5・6) RV2 2 件は spec から外し、等価変異として報告に 1 行残す。CONTROL_MAPPING.md は Version 行と主張行から経緯の叙述 (「rework 1」「差し戻し」「rulings A-…」) を除き、今日の統制と証拠だけにする。A-13・A-14 を主張に反映する (実測の後に書く)。

- A-17 (指摘 1) 両 peer の test_ops_upgrade.py に、親に `PGSERVICEFILE` だけ / `PGSYSCONFDIR` だけを置いた場合に拒否され、変数名だけが出て値が出ないテストを足す。変異 RV4 を両 peer 分 spec に加え、赤を確認。
- A-18 (指摘 2) `_require_psql_16_or_newer` は psql が無い (`FileNotFoundError` / `OSError`) ときも固定文言で `_die` する (両 peer 同じ形)。テストと変異 (捕捉を外す → 赤) を足し、CONTROL_MAPPING の主張を実動作に合わせる。
- A-19 (指摘 3) CONTROL_MAPPING.md の Version は main から見た次の版 **2.1** にする。
- A-20 (指摘 4) テストのコメントから経緯語を除き、何を確かめるかだけを書く。

## 4. WP-B — MitateDB-api の `inventory` (DB 層、Class D)

**目的**: MitateDB-api の ops CLI に読み取り専用のサブコマンド `inventory` を新設し、Gate-0 の DB 層の判定だけを出す (設計 D-1)。

**読む正本**: 設計 §1.2、§2、§3、§3.1、D-1 (DB 層、(8) の式は Z-27 の版)、D-2、D-3、D-4、D-5、D-9、D-10、D-11、§6 の Q-3 (a)・Q-4 (a)、§7 の該当行、§8、§9.2 の Z-13・Z-19・Z-23、§9.3 の Z-24〜Z-28・Z-30・Z-33・Z-36。本書 §2.8 の W-2・W-4・W-5。§1.5 の 32。

**使用テンプレート**: 2 (実装) → 5 (コードレビュー)。

**基点**: WP-A の統合後の main。WP-C を先にした場合は WP-C の統合後 (§2.5)。

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/ops.py` (`inventory` の新設。既存サブコマンドの振る舞いは変えない。設計 D-1)、`MitateDB-api/tests/test_ops_inventory.py` (新規)、`security/CONTROL_MAPPING.md` (W-5) | §2.2 の全 WP 共通、`r2db-api/` 全部、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS`。設計 D-9)、`_ISOMORPHIC_TARGETS` 登録済みの helper の本体、`MitateDB-api/src/mitatedb_api/platform_declarations.py`・`platform_upgrades.py`・`config.py` (読むだけ)、`MitateDB-api/migrations/`、`MitateDB-api/docs/`、`_run_upgrade_script` / `_run_deprovision_script` とその CLI の引数定義 (WP-C) |

**着手時の手順**:

1. §2.1 の再照合。
2. 設計 §8 のうち実装で確かめる点を実測して報告する: `mitatedbsvc_auditreader` を使う process を関数名で確定する (Z-36。確定するまでは Data と Control の両方で数える)、`role_pool_size`・`check_role_connection_limits` が role の種類ごとの process あたり接続数を全部与えるか、provision ロールが registry の credential の表を読めるか (合成クラスタで。Q-4 (a))。
3. 読み取りの接続ごとに掛ける `lock_timeout` / `statement_timeout` の値を定数として提案し、監督の採否を得てから pin する (W-4)。
4. 設計 §3 が引く既存の読み取り関数を呼ぶ形で足りない (登録済み helper の本体を変える必要がある) と分かったら、止まって監督へ上げる (§2.3)。

**実行するコマンド**:

```bash
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_ops_inventory.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests -q     # 回帰
tools/dev/mutate.py "$SP/r45-wpb-mutations.json" -C "$WT" --wait 1800
python3 tools/public_value_scan.py MitateDB-api/src/mitatedb_api/ops.py MitateDB-api/tests/test_ops_inventory.py security/CONTROL_MAPPING.md
```

**完了条件 → 変異 → 赤になる test id** (番号は設計 §7 の行番号。変異の `file` は、特記の無い行はすべて `MitateDB-api/src/mitatedb_api/ops.py` の `inventory` の実装。赤になるテストはすべて `MitateDB-api/tests/test_ops_inventory.py` の新規テストで、名前は予想)

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| 1 | DB 層の各項目を判定つきで出す (合成の platform DB で 1 件以上観測) | 1 項目の判定を出力から落とす | 全項目の判定の存在を assert するテスト |
| 2 | Gate-0 全体の ready を出さない (Z-15) | 全体の ready を出力に足す | 全体判定の不在のテスト |
| 2a | 終了コードは DB 層の全項目が confirmed のときだけ 0 (Z-33・Z-35。値は W4-1・W4-2) | unknown があっても 0 を返す | unknown を含む場合の終了コードのテスト |
| 4 | (3) の未適用の migration・upgrade は confirmed + `remediation-required` (Z-14) | 未適用を blocked にする | (3) の未適用のテスト |
| 5 | (3) でアプリケーション DB への接続失敗は unknown (C3) | 接続失敗を pending / confirmed に丸める | (3) の接続失敗のテスト |
| 6 | (3) で `read_applied_upgrade_numbers` が `UndefinedTable` 以外の `psycopg.Error` を送出すると unknown | その例外を空の台帳として扱う | (3) の読み取り失敗のテスト |
| 7 | (3) は登録のみの application を件数と状態で出す | 登録のみの application を集計から除く | (3) の登録のみのテスト |
| 8a | (1) で接続名と DSN の unix socket の path を比べ、`match` / `mismatch` / `unknown` だけを出す (Z-26) | 比較を外して常に `match` を返す | (1) の `mismatch` のテスト |
| 8b | (1) で比べられない形の DSN は unknown (Z-26・Z-34) | 比べられない形を `match` に丸める | (1) の TCP 形 DSN のテスト |
| 8c | (1) の出力に接続先そのものが出ない (Z-26) | 出力に接続先を足す | (1) の出力に接続名・path が無いことのテスト |
| 10a | 成功経路で user / password の番兵が stdout / stderr に出ない (Z-24) | 出力に user または password を足す | 成功経路の番兵のテスト |
| 10b | 成功経路で dbname の番兵が (1) の識別フィールド以外に出ない (Z-24) | DB 名を識別フィールド以外にも出す | 成功経路の dbname のテスト |
| 10c | 出力は stdout の 1 経路に限り、証跡ファイルを自分で書かない (Z-24、D-11) | 判定の一部を stderr またはファイルに書く | 出力経路のテスト |
| 11 | 接続失敗 (接続できない host) で設計 D-2 の 3 段の assert | 生の例外文字列を出力する形に戻す | host の経路のテスト |
| 11a | 接続失敗 (存在しない role)、前提 2 は user の番兵 (Z-30) | 同上 (経路ごとに 1 件) | role の経路のテスト |
| 11b | 接続失敗 (存在しない database)、前提 2 は dbname の番兵 (Z-30・Z-24) | 同上 | database の経路のテスト |
| 12 | DSN 解析失敗 (接続前)、前提 2 は password の番兵 | 同上 | 解析失敗の経路のテスト |
| 13 | 接続後の psycopg 例外 (`cursor.execute` を差し替え) で出力に番兵が無い | 例外処理で生の例外文字列を出す | 接続後の例外のテスト |
| 14 | psycopg 以外の例外は最上位で捕まえ、型名と固定文言だけを出す | 最上位の捕捉を外す | psycopg 以外の例外のテスト |
| 15 | 4 要素それぞれに、番兵が生の例外文字列に現れる経路が 1 つ以上ある (Z-7) | **監査照合**: 要素 → 経路 (テスト名) の表と、経路が作れなかった要素の実測記録を逐語で残す | — |
| 20 | DSN を argv で受け取らない (静的テスト、Z-8) | DSN を受け取る引数を足す | argv の静的テスト |
| 22 | (4) の出力の key と `cursor.description` の列名が許可リストに一致し、`credential_id`・`digest` が出ない (Z-9) | 出力に `credential_id` を足す | (4) の許可リストのテスト |
| 23 | 同上 | 読み取りを `SELECT *` にする | (4) の列名のテスト |
| 23a | (4) を読む権限が無ければ unknown (Z-6・Z-33) | 権限エラーを confirmed に丸める | (4) の権限不足のテスト |
| 25a | spy で捕まえた全接続で、明示トランザクションの外からの書き込みが拒否される (Z-28) | セッションの読み取り専用の設定を外す | 全接続の書き込み拒否のテスト |
| 25b | 各接続の `transaction_read_only` を確かめ、確かめられない接続では読まず unknown (Z-28) | 確かめる処理を外す | 読み取り専用の確認のテスト |
| 25c | 台帳の表が無いアプリケーション DB でも `rollback()` と両立し confirmed + `remediation-required` (Z-28) | 読み取りを明示の `transaction()` で包む | 台帳の表が無い DB のテスト |
| 27a | spy が捕まえた接続がすべて factory 経由 (件数一致、Z-28) | アプリケーション DB の接続を factory を通さずに開く | factory 経由の件数のテスト |
| 27b | factory 以外に `psycopg.connect` が無い (静的検査) | factory の外に `psycopg.connect` を足す | factory の静的テスト |
| 27c | 項目ごとの短いトランザクションで読み、接続ごとに `lock_timeout` / `statement_timeout` を設定する (W-4) | セッションの `lock_timeout` の設定を外す | セッション設定のテスト |
| 29a | env と手元のコードに依存する検査の結果を confirmed の根拠にしない (Z-13) | F-16 の結果を (8) の confirmed の根拠に使う | (8) の根拠のテスト |
| 29b | 入力が引数で与えられなければ unknown (Z-13) | 入力が無いとき既定値に戻す | 入力欠落のテスト |
| 30 | (8) で `max_connections` が読めなければ unknown | 読めないときに余力を計算する | `max_connections` 欠落のテスト |
| 31a | (8) で `max-instances` が引数で与えられなければ unknown (Z-27) | `process_ceilings` の宣言値で補う | `max-instances` 欠落のテスト |
| 32 | (8) で対象 role のどれかが `CONNECTION LIMIT = -1` なら unknown (Z-27) | -1 を数として足す | 対象 role の -1 のテスト |
| 32a | 対象 role 以外の -1 は unknown の理由にしない (Z-27) | -1 の検査を全 role に広げる | 対象外 role の -1 のテスト |
| 33a | (8) の process 数は新旧 revision の `max-instances` の合計 (Z-27) | 1 revision 分だけ数える | 新旧合計のテスト |
| 33b | 宣言と実際の `max-instances` が食い違えば blocked (Z-27) | 食い違いを無視する | 食い違いのテスト |
| 34 | 条件 1: role ごとの需要が `CONNECTION LIMIT` 以下でなければ confirmed にしない | 条件 1 の比較を外す | 条件 1 のテスト |
| 34a | process あたり接続数を role の種類ごとに設計 D-1 の関数名で引く定数から取る (Z-27) | `mitatedbsvc_api` を 1 × concurrency で数える | role 種類ごとの係数のテスト |
| 34b | 条件 2 で共有のアプリケーション role を 1 回だけ数える (Z-27) | アプリケーションごとに数える | 共有単位のテスト |
| 34c | `mitatedbsvc_provision` を含めず、`mitatedbsvc_auditreader` は確定まで Data と Control の両方で数える (Z-36) | `mitatedbsvc_auditreader` を片方の process だけで数える | 対象 role の列挙のテスト |
| 35 | `inventory` が同時に開く接続の最大数を定数で固定し静的テストで pin し、予約枠に含める (Z-23) | 定数を実際に開く接続数より小さくする | 定数の pin のテスト |
| 35a | 条件 2: 需要の和 + 予約枠が `max_connections` 以下でなければ confirmed にしない | 条件 2 から予約枠を外す | 条件 2 のテスト |
| 35b | 予約枠・process あたり接続数の出所が確定しなければ unknown | 出所の無い値を既定値で補う | 出所欠落のテスト |
| 35c | spy で実測した同時接続数の最大が 35 の定数以下 (Z-28) | アプリケーション DB の接続を最後まで閉じない | 同時接続数の実測のテスト |
| 36 | (5) は互換性の根拠が宣言されていなければ unknown (D-4) | (5) の判定関数の既定を confirmed にする | (5) のテスト |
| 37 | (6) は機械可読なロック・maintenance の宣言が無ければ unknown (D-5) | (6) の判定関数の既定を confirmed にする | (6) のテスト |
| W2-1 | JSON 出力のトップレベルと項目ごとのキー集合を pin する (Q-3 (a)、W-2) | キーを 1 つ改名する | キー集合の pin のテスト |
| W2-2 | 判定語を閉じた語彙 (confirmed / blocked / unknown と `remediation-required` 注記) に pin する (W-2) | 語彙外の判定語を 1 項目に出す | 判定語の語彙の pin のテスト |
| W4-1 | いずれかの項目が blocked / unknown なら終了コード 2 (W-4) | 2 の代わりに 1 を返す | blocked / unknown の終了コードのテスト |
| W4-2 | ツール自身の失敗は終了コード 1 で、出力は固定文言のみ (W-4) | ツール自身の失敗で 2 を返す | ツール失敗の終了コードと固定文言のテスト |
| W4-3 | 接続ごとの `lock_timeout` / `statement_timeout` の値を定数として静的に pin する (W-4。値は監督の採否を経たもの) | 定数の値を変える | 定数の静的 pin のテスト |
| W4-4 | `lock_timeout` / `statement_timeout` の超過はその項目の unknown (W-4) | 超過を confirmed に丸める | 超過の項目判定のテスト |
| W5-B | 本 WP の統制を `security/CONTROL_MAPPING.md` に本 WP のテストと同じ変更セットで対応付け、Version 行の minor を 1 つ上げる (W-5) | **監査照合**: 追加した行と Version 行の前後、該当ブロックの文字数の実測を逐語で設計に残す | — |
| 47 | 追加・変更したテストと fixture に実値が無い (C5) | **監査照合**: `public_value_scan.py` の集計行を逐語で残す | — |
| 50 | 本表に変異も監査照合も持たない行が無い | **監査照合**: 本表の行数と対応数を残す | — |

**件数 (下限)**: 完了条件 57 件 = 変異を持つ行 53 件 + 監査照合 4 件 (15・W5-B・47・50)。変異は 1 行 1 件 (53 件)。

### 4.1 WP-B の訂正註と監督裁定 (2026-09-17、統合時に監督が追記。§4 の本文は書き換えない)

**訂正註 B-1 (完了条件の移動)**: 33a (新旧 revision の process 数の合計の正しさ) は、operator が platform 層で読んで引数で渡す形になったので WP-D の runbook の監査照合へ移す (B-7)。

**訂正註 B-2 (DB 層の出力)**: (5) は DB 層の出力に含めず、(6) は実行時設定の部分だけを判定する。判定していない部分は `unjudged_items` に `runbook-acceptance` として並べる (B-8・B-12)。終了コード 0 は DB 層が判定する全項目が confirmed のとき。DB 層では (5) と (6) のロック・停止時間の部分が常に判定外なので、全体の ready は WP-D の runbook の手順で受理記録と合わせて出す。

**訂正註 B-3 (WP-D への引き継ぎ)**: WP-D は `security/CONTROL_MAPPING.md` の SI-08 に行を足さない (B-19)。

**監督裁定 B-1〜B-19 (実装担当への裁定の本文。再実行の手順と報告の形の指示は省いた)**

- B-1 inventory の読み取りの各接続に `lock_timeout=3000ms`・`statement_timeout=5000ms` をモジュール定数で掛け、静的に pin する。超過はその項目 unknown。
- B-2 `mitatedbsvc_auditreader` は Control の process だけが使う (`control_composition.py`、`main.py` は除外) と実測で確定したので、(8) では Control 側だけで数える。Z-36 の「両方で数える」は確定までの暫定だった。将来 Data 側が使い始めたら赤になるテストで固定する。
- B-3 `platform_declarations.py` の private 定数を `inventory` から import して使ってよい (読むだけ)。値を複製しない。同じオブジェクトを使うことを identity で確かめる。
- B-4 (3) の台帳の読み取りは application ごとに `InsufficientPrivilege` を捕まえ、その application の (3) を blocked (固定の理由語、例外文字列を出さない) にし、全体も blocked。他の application の判定は続ける。R-47 の状態の application でテストする。秘密の列を SELECT しないことを静的に固定する。
- B-5 (指摘 6) 設計 D-1 と Z-9 のとおり実装する: (6) の実行時設定の部分 (対象 role の CONNECTION LIMIT と `pg_db_role_setting` の `lock_timeout` / `statement_timeout`) を DB 層で読む。(4) は総件数に加えて状態 (enabled / revoked / must_rotate) ごとの件数を出す (credential_id は出さない)。inventory のクエリが返す列名 (`cursor.description`) を許可リストと照合するテストを置き、秘密の列が 1 つでも返れば赤。
- B-6 (疑義 ii) `PlatformDeclarationError` を分ける: 未適用・未宣言 (表や行が無い = F-8 / F-3 / F-4 / F-15 の欠落) は confirmed + `remediation-required` の注記。値が不正 (F-5 / F-4b / F-15 の形の違反) は **blocked** (理由は固定の語)。どちらもテストと変異を置く。
- B-7 (疑義 iii) CLI の数値引数は正の整数だけを受け付け (0・負を固定文言で拒否)、テストと変異を置く。新旧 revision の process 数の合計は operator が platform 層で読んで引数で渡す形のままとし、その読み方と合計の正しさは WP-D の runbook の監査照合で扱う (33a を WP-D へ移す。統合時に作業指示書へ訂正註)。
- B-8 (疑義 iv) Q-1 (c)・Q-2 (c) により、(5) rollback の可逆性と、(6) のうちロック種別・停止時間の上限の部分は、runbook の表の独立レビューの受理記録で判定する (DB 層では判定しない)。したがって DB 層の出力は、DB 層が判定する項目だけを持つ: (5) は出力に含めない。(6) は実行時設定の部分だけを判定する。JSON に「DB 層で判定していない項目」のリスト (項目番号と固定の理由語 `runbook-acceptance` だけ) を置き、W-2 の判定語の語彙は変えない。終了コード 0 は DB 層が判定する全項目 confirmed を意味する。全体の ready は runbook の手順で両層と受理記録を合わせて出す (WP-D)。キー集合の pin を更新し、判定していない項目のリストの pin と変異を置く。
- B-9 (軽微 8) すべて直す: 11 / 11a / 11b / 12 の第 1 段で固定文言を assert、W4-4 と R30 は赤 (exit 1) になる形に直す (error 化させない)、`_inventory_connect` で `SET` が失敗したら接続を閉じる (テスト付き)、`reason` の語彙を pin する。
- B-10 process 数と concurrency 系の引数は正の整数、`--reserved-connections` は 0 以上の整数。
- B-11 (6) の実行時設定で読む role は (8) と同じ集合 (auditreader を含む)。
- B-12 `unjudged_items` には (5) と、(6) のロック種別・停止時間の上限の部分 (`part` = `lock-and-downtime`) を入れる。`part` の語彙を pin。`ddl_lock` の判定は実行時設定の部分だけ。
- B-13 (1) `connection` にも `judgment` を持たせ、match / mismatch / unknown を confirmed / blocked / unknown に対応付ける。終了コードは全項目の `judgment` から計算する。
- B-14 (8) の宣言読み取り: `psycopg.Error` → unknown、宣言の欠落 → unknown + `remediation-required`、値の不正 → blocked。
- B-15 B-11 のとおり、(6) の対象 role はアプリケーションの `_rt` / `_dv` を含む (8) と同じ集合。
- B-16 `security/CONTROL_MAPPING.md` の Version は main から 1 つ上げる。経緯語を除き、主張を実装に合わせる。CONNECTION LIMIT は値まで確かめる実装にする。
- B-17 SI-08 の文字数 (上限まで残り 16 字になった件): 既存の行は変えず、本 WP が足した行だけを簡潔に書き直す。主張は落とさない。
- B-18 B-17 の書き直しで抜けた主張 3 つ ((a) -1 を unknown にするのは対象 role の集合の中だけ、(b) auditreader の接続を pool するのは `control_composition.build_control_service` だけ、(c) 宣言の欠落と値の不正の区別) を戻し、証拠のテスト名をファイルのパスを 1 回だけ書いて個別に列挙する。
- B-19 (統合時) SI-08 の MitateDB ブロックは 14,809 字 (上限 15,200) で受け入れる。B-17・B-18 で置いた目安 14,500 字は、主張と証拠を落とさないことを優先して外す。**後続の WP-D は SI-08 に行を足さず、runbook の受理記録を適切な別の SI に置く。**

## 5. WP-C — (10) の migration 再実行性テストと適用時の `lock_timeout` (Class D)

**目的**: Gate-0 の (10) を本番を読まずに confirmed にするリポジトリ側の証拠 (再実行性・冪等性・順序、`ON_ERROR_STOP` の 2 層) をテストで固定する (設計 D-1 のリポジトリ側の証拠、Z-3)。運用の適用経路が psql に適用時の `lock_timeout` を渡すようにし、静的に pin する (W-1)。

**読む正本**: 設計 §1.1 の (10)、D-1 のリポジトリ側の証拠、D-8 の blocker 2・3、§6 Q-5 (b)、§7 の 39〜46、§8 の最後の項、§9.2 の Z-15・Z-18・Z-22、§9.3 の Z-33・Z-35。本書 §2.8 の W-1・W-3・W-4・W-5・W-7・W-8。§1.5 の 32。

**使用テンプレート**: 2 (実装) → 5 (コードレビュー)。

**基点**: WP-A の統合後の main。WP-B を先にした場合は WP-B の統合後 (§2.5)。

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/ops.py` の `_run_upgrade_script` と `_run_deprovision_script` の psql 実行と、それらを呼ぶサブコマンドの `lock_timeout` の引数定義だけ (W-1・W-7)、`MitateDB-api/tests/test_platform_migration_reapply.py` (新規。名前は案。変えるなら着手時に報告し、§2.5 の重なり表を訂正註で直す)、`security/CONTROL_MAPPING.md` (W-5) | §2.2 の全 WP 共通、`MitateDB-api/migrations/` (変異の一時編集を除く)、`MitateDB-api/src/` の上記以外 (変異の一時編集を除く)、`MitateDB-api/tests/test_migration_0007_ddl.py`、`MitateDB-api/tests/test_ops_verify_declarations.py` (登録済みのテスト helper を持つ)、`MitateDB-api/tests/test_ops_inventory.py`、両 peer の `tests/test_audit_query.py`、`r2db-api/` 全部、`MitateDB-api/docs/` |

**着手時の手順**:

1. §2.1 の再照合。
2. 設計 §8 の最後の項を実測して報告する: 0011 / 0012 と `declare-*`・per-application upgrade の既存の再適用テストの有無。44 の変異 (台帳の記録を外す) が「2 回目の適用件数 0」の assert で赤になるか。素通りするなら監督へ上げる。

**規則 (所在だけを示す)**: 2 回適用の比較から `updated_at` を除き、2 回目の終了コード 0 を見る (Z-33)。順序はカタログの不変でなく終了コードで固定する。`ON_ERROR_STOP` は argv 側 (運用の適用経路) とファイル側を別々に固定する (Z-18・Z-33・Z-35)。証拠の起点は Q-5 (b) を W-3 のとおり満たす: migration 列のすべての接頭辞 N (0..最新) を起点に parametrize し (接頭辞 N は番号順に先頭から N 個。飛び飛びの起点は含めない。W-8)、起点 N まで適用 → 候補 HEAD まで適用 → もう一度適用して差分 0 と終了コード 0 を見る。以下 39〜44 の「2 回適用」はこの形を指す。適用時の `lock_timeout` の値は WP-D の runbook の表で決める (W-4・W-7) ので、本 WP は、2 関数が値を既定値の無い必須の CLI 引数で受け取って psql に渡すことと、引数が無ければ CLI が拒否することを固定し、値そのものは固定しない (W-1・W-7)。

**実行するコマンド**:

```bash
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_platform_migration_reapply.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_migration_0007_ddl.py -q
tools/dev/mutate.py "$SP/r45-wpc-mutations.json" -C "$WT" --wait 1800
python3 tools/public_value_scan.py MitateDB-api/src/mitatedb_api/ops.py MitateDB-api/tests/test_platform_migration_reapply.py security/CONTROL_MAPPING.md
```

**完了条件 → 変異 → 赤になる test id** (番号は設計 §7 の行番号。赤になるテストは、特記の無い行は新規ファイルのテストで名前は予想)

| # | 完了条件 | 変異 (`file:操作`) | 赤になる test id (予想) |
|---|---|---|---|
| 39 | 0007 を 2 回適用し、2 回目の終了コード 0、`updated_at` を除いて差分 0 | `MitateDB-api/migrations/0007_platform_declarations.sql`: `CREATE TABLE IF NOT EXISTS` を `CREATE TABLE` にする | 接頭辞で parametrize した再適用のテストのうち 0007 を含む起点の id |
| 40 | 0011 を 2 回適用し、同じ条件 | `MitateDB-api/migrations/0011_process_ceilings.sql`: `DROP CONSTRAINT platform_declarations_key_check` の文を外す | 0011 の再適用のテスト |
| 41 | 0012 を 2 回適用し、同じ条件 | `MitateDB-api/migrations/0012_role_connection_limits.sql`: `CREATE OR REPLACE FUNCTION` を `CREATE FUNCTION` にする | 0012 の再適用のテスト |
| 42 | `declare-surfaces` を 2 回適用し、2 回目の終了コード 0、`updated_at` を除いて宣言の値の差分 0 | `MitateDB-api/src/mitatedb_api/ops.py`: `cmd_declare_surfaces` の書き込む値を 2 回目で変わる形にする | `declare-surfaces` の再適用のテスト |
| 43 | `declare-process-ceilings` を 2 回適用し、同じ条件 | `MitateDB-api/src/mitatedb_api/ops.py`: `cmd_declare_process_ceilings` の書き込む値を 2 回目で変わる形にする | `declare-process-ceilings` の再適用のテスト |
| 44 | per-application upgrade を 2 回適用し、2 回目の終了コード 0・適用件数 0・差分 0 | `MitateDB-api/src/mitatedb_api/ops.py`: upgrade の台帳への記録を外す (着手時の手順 2 で赤を実測) | per-application upgrade の再適用のテスト |
| 45a′ | 運用の適用経路が psql の argv に `ON_ERROR_STOP` を渡すことを静的テストが固定する (`_run_upgrade_script` と `_run_deprovision_script`) | 2 件。`MitateDB-api/src/mitatedb_api/ops.py`: `_run_upgrade_script` の argv から `ON_ERROR_STOP` を外す。`_run_deprovision_script` の argv から同じく外す | argv の静的テスト |
| W3-1 | 再実行性テストの起点が migration 列のすべての接頭辞 N (0..最新) を覆う (W-3・W-8。空振り禁止として起点の件数 = migration ファイル数 + 1 を assert し、各起点が番号順の先頭からの連続であることを assert) | テストの parametrize から接頭辞を 1 つ落とす | 起点の集合と migration ファイルの列挙の一致を assert するテスト |
| W1-C1 | `_run_upgrade_script` の psql 実行が適用時の `lock_timeout` を渡すことを静的テストが固定する (W-1) | `MitateDB-api/src/mitatedb_api/ops.py`: `_run_upgrade_script` で `lock_timeout` を渡さない形にする | `lock_timeout` の静的 pin のテスト |
| W1-C2 | `_run_deprovision_script` の psql 実行が同じく渡す (W-1) | `MitateDB-api/src/mitatedb_api/ops.py`: `_run_deprovision_script` で渡さない形にする | 同上 |
| W7-C1 | `_run_upgrade_script` を呼ぶサブコマンドは `lock_timeout` の引数が無ければ拒否する (既定値を持たない。W-7) | 引数に既定値を与える | 引数欠落の拒否のテスト (upgrade) |
| W7-C2 | `_run_deprovision_script` を呼ぶサブコマンドも同じく拒否する (W-7) | 引数に既定値を与える | 引数欠落の拒否のテスト (deprovision) |
| W5-C | 本 WP の統制を `security/CONTROL_MAPPING.md` に本 WP のテストと同じ変更セットで対応付け、Version 行の minor を 1 つ上げる (W-5) | **監査照合**: 追加した行と Version 行の前後、該当ブロックの文字数の実測を逐語で設計に残す | — |
| 45b | migration ファイルに `\set ON_ERROR_STOP on` があることを静的テストが固定する | `MitateDB-api/migrations/0011_process_ceilings.sql`: `\set ON_ERROR_STOP on` を外す | ファイル側の静的テスト |
| 45c | 依存先 (0007) を欠いた 0011 の適用がエラーで止まる (終了コードで判定) | argv 側とファイル側の `ON_ERROR_STOP` を同時に外す (着手時に赤を実測) | 順序のテスト |
| 46 | (10) の証拠が候補 HEAD の SHA に結び付いて記録される | **監査照合**: 記録の形 (SHA と集計行) を逐語で設計に残す | — |
| 47 | 追加したテストと fixture に実値が無い (C5) | **監査照合**: `public_value_scan.py` の集計行を逐語で残す | — |
| 50 | 本表に変異も監査照合も持たない行が無い | **監査照合**: 本表の行数と対応数を残す | — |

**件数 (下限)**: 完了条件 18 件 = 変異を持つ行 14 件 (変異 15 件。45a′ は 2 件) + 監査照合 4 件 (W5-C・46・47・50)。

### 5.1 WP-C の訂正註と監督裁定 (2026-09-16〜17、統合時に監督が追記。§5 の本文は書き換えない)

**依頼者裁定 (逐語、2026-09-17)**: 「台帳に 1 行起票するだけにする」 — `b87d1c85` より前の 0003 で provision された application を現行の `upgrade-applications` が台帳を読む段階で `InsufficientPrivilege` により upgrade できない欠陥 (WP-C の起点のテストが発見。監督が「R-45 の中で直す」を推奨し、依頼者が起票のみを選んだ) は、`docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-47 に起票し、本書では直さない。

**訂正註 C-1 (触ったファイル)**: §5 の表に加え、`MitateDB-api/tests/test_ops_upgrade.py`・`MitateDB-api/tests/test_ops.py`・`MitateDB-api/tests/test_main.py` (`--lock-timeout` の追加。C-1) と `.github/workflows/ci.yml` (`conformance` job の checkout に `fetch-depth: 0`。C-12) を触った。新規ファイル名は `MitateDB-api/tests/test_platform_migration_reapply.py` のまま。

**訂正註 C-2 (完了条件の読み替え)**: 44 の変異先は `ops.py` ではなく `0008_platform_upgrades_upgrade.sql` の台帳 INSERT (C-2)。45c の変異はファイル側だけ (C-5)。W3-1 の件数は「起点の列の長さ + 1 − 対象外の数」(C-8・C-11)。起点の列は 0004 を除く 11 ファイル、parametrize される起点は `[0, 1, 2, 7, 8, 9, 10, 11]`、対象外 `{3, 4, 5, 6}` (C-11)。

**監督裁定 C-1〜C-12 (実装担当への裁定の本文。再実行の手順と報告の形の指示は省いた。C-1〜C-3 は着手時の停止報告への裁定、C-4〜C-12 は差し戻しとレビューへの裁定)**

- C-1 `--lock-timeout` は `upgrade-applications` と `deprovision` の CLI で既定値の無い必須引数にし、`_run_upgrade_script` / `_run_deprovision_script` の Python 引数も既定値を持たせない (W-7 のとおり)。既存テストの呼出し箇所を直すため、触るファイルに `MitateDB-api/tests/test_ops_upgrade.py`・`MitateDB-api/tests/test_ops.py`・`MitateDB-api/tests/test_main.py` を足す。直し方は呼出し箇所に合成値の `--lock-timeout` を明示で足す。共通のテスト helper (`_run_ops` 等) に既定で注入する形は、その helper が `_ISOMORPHIC_TARGETS` に登録されていない場合に限り許す。W7-C1 / W7-C2 のテストは引数なしで CLI を呼び、使用法エラーで止まり psql を起動しないことを確かめる。
- C-2 完了条件 44 の変異先を読み替える: 「`ops.py`: 台帳への記録を外す」→「`upgrade-applications` の経路で実際に流れる per-application upgrade スクリプトのうち 1 つ (`MitateDB-api/migrations/0008_platform_upgrades_upgrade.sql` を第一候補) の台帳への INSERT を外す」。赤になることを実測する。
- C-3 `lock_timeout` の渡し方は、`_psql_connection_env` が返した env に `PGOPTIONS` の `-c lock_timeout=<値>` を足す形でよい。DSN の `options` と両方ある場合は連結して両方を効かせる。値は CLI で検証し、不正なら固定文言で拒否する。値の検証のテストと変異を足す。r2db-api には本 WP で手を入れない。
- C-4 W-3 は裁定済みの完了条件であり、見送れない。migration 列のすべての接頭辞 N を parametrize し、各 N について適用 → 全部適用 → もう一度適用し、2 回目の終了コード 0 と `updated_at` を除いた差分 0 を assert する。39〜41 はこの接頭辞テストの中で満たす。W3-1 の静的テストは残す。42〜44 は代表起点のままでよい。
- C-5 45c は 0011 が `_run_upgrade_script` を経由しないので、変異はファイル側だけを外す形に直す。
- C-6 起点の列は `MitateDB-api/migrations/*.sql` を番号順に並べたもののうち、`0004` (deprovision の雛形) だけを除いた列とする。接頭辞 N は、この列の先頭 N 個を実際の運用の形で適用した状態: platform 用のファイルは platform DB に、`:app_id` を取る per-application のファイルは `0003` で provision した 1 件の application に当てる。
- C-7 再適用するのはアップグレードの手順で再実行されるもの: platform migration の 0007 / 0011 / 0012 と、per-application upgrade (0006・0008〜0010 を `upgrade-applications` の経路で、`--lock-timeout` を付けて)。bootstrap (0001・0002)・provisioning (0003) は対象外、種別の実測で 0005 が platform migration と分かれば再適用に含める。
- C-8 起点の列をモジュール定数にまとめ、parametrize と W3-1 が同じ定数を使う。
- C-9 起点 N (N < 列の長さ) では、列の (N+1) 番目のファイルを追加したコミットの親の時点のファイル内容で、列の先頭 N 個を適用する。N = 列の長さでは HEAD の内容を使う。その後 HEAD の内容で列の全部を適用し、C-7 の対象をもう一度適用する。少なくとも 1 つの起点で使った過去の内容が HEAD と異なることを assert する。git の履歴が読めないときは skip せず fail する。
- C-10 起点の適用後に per-application の番号 (6・8・9・10) の台帳の行を消してから `upgrade-applications` を流し、実際に本文が実行されることを assert する。
- C-11 (依頼者裁定「台帳に 1 行起票するだけにする」を受けて) `b87d1c85` より前の 0003 で provision された application を現行の ops が upgrade できない欠陥は台帳 R-47 に起票のみとし、該当する起点は skip ではなく parametrize に含めない。判定は機械的に行う: 起点で使う過去の 0003 に public schema の USAGE の provision role への付与が無く、かつその起点の列に 0008 が含まれない。対象外の集合を pin し、現在 {3, 4, 5, 6} であることを assert する。
- C-12 `.github/workflows/ci.yml` の、MitateDB-api/tests を走らせる job (`conformance`) の `actions/checkout` に `fetch-depth: 0` を足す。

## 6. WP-D — runbook の platform 層と upgrade の手順 (Class D)

**目的**: Gate-0 の platform 層の読み取り (射影、許可表、DSN の受け渡し、全体判定と Mitate への報告の書式) を operator 手順として runbook に置く (設計 D-1 の platform 層、D-10、D-11)。あわせて Q-1 (c) の互換性の表、Q-2 (c) のロックの表、起票原文の手順 2 の手順を置き、独立レビューの受理を得る (W-1)。**本番を読む手順・更新する手順を書くが、本 WP の中では実行しない** (§7)。

**読む正本**: 設計 §1.2、§2、D-1 (platform 層と全体判定)、D-8、D-10、D-11、§5 の却下案 1・2、§6 の Q-3 (a)・Q-7 (a)、§7 の該当行、§8 の platform 層の項、§9.2 の Z-8〜Z-10・Z-12〜Z-14・Z-19、§9.3 の Z-24〜Z-26・Z-29・Z-34。設計 D-4・D-5、§6 の Q-1 (c)・Q-2 (c)・Q-5 (b)。本書 §2.8 の W-1・W-3・W-4・W-5・W-6。WP-C で統合された適用時の `lock_timeout` の渡し方。WP-B で統合された `inventory` の引数・終了コード・出力 (統合後の main の `MitateDB-api/src/mitatedb_api/ops.py`)。

**使用テンプレート**: 3 (起草) → 4 (`reviewer`、設計レビューのモード。W-1 の受理)。

**基点**: WP-B と WP-C の統合後の main (§2.5)。

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/docs/cloud-run-cloud-sql.md`、`security/CONTROL_MAPPING.md` (runbook の受理記録の対応行。W-5) | §2.2 の全 WP 共通、`MitateDB-api/src/`、`MitateDB-api/tests/`、`MitateDB-api/migrations/`、`r2db-api/` 全部、`MitateDB-api/docs/` の他のファイル |

**規則 (所在だけを示す)**:

- 値はすべて形で書く (設計 D-1 platform 層、C5)。gcloud はプロンプトを無効化して実行し、API を有効化しない (Z-12、Q-7 (a))。production の手順より前に、isolated で `--quiet` のときの API 有効化プロンプトの既定応答を確かめ記録するゲート手順を置く (W-6)。
- DSN は環境変数だけで渡し、`inventory` はサブシェルで実行する (D-10)。Cloud SQL Auth Proxy の unix socket モードを前提にし、TCP 経由では (1) が unknown のままである理由を書く (Z-34)。
- 証跡は stdout のリダイレクトでどの git リポジトリの外にも置き、形式は JSON (Q-3 (a))。報告は判定・`remediation-required`・識別子を含まない件数だけ (D-11、Z-25)。
- (10) について、本番の Gate-0 では (9) で attest した ref に当たる migration 列の接頭辞 N を記録するだけにする (W-3)。
- migration 適用時の `lock_timeout` の値は、Q-2 (c) の表で migration ごとに決める (W-4)。表には「per-application upgrade」「deprovision」の行を足し、その値を CLI の必須引数に渡す手順を書く。0007 / 0011 / 0012 は psql に `PGOPTIONS` 経由で表の値を渡す (W-7)。
- 起票原文の手順 2 の手順 (0007 / 0011 / 0012 の適用、per-application upgrade、declaration、legacy env の除去、Data / Control restart、health、traffic、rollback) は W-1 のとおり runbook に置く。
- runbook の検証は文書の照合と独立レビューだけで行い、gcloud・psql を本番に対して実行しない。

**実行するコマンド**:

```bash
python3 tools/check_doc_refs.py                                   # WT で実行。dangling 0
python3 tools/public_value_scan.py MitateDB-api/docs/cloud-run-cloud-sql.md security/CONTROL_MAPPING.md   # flagged 0
```

**完了条件 → 照合** (番号は設計 §7 の行番号と本書 §2.6 の裁定の行。いずれも変異を持たず、照合対象を逐語で設計に残す)

| # | 完了条件 | 監査照合の対象 |
|---|---|---|
| 3 | Gate-0 全体の ready は 10 項目すべてが confirmed のときだけ出す (§1.2) | 全体判定の手順の節名と手順文 |
| 3a | Mitate への報告で unknown と blocked をどちらも `blocked—platform remediation required` に写し、内訳を併記する (Z-25) | 報告の書式 |
| 9a | revision から読んだ Cloud SQL の接続名を `inventory` に渡し、`mismatch` / `unknown` で先へ進まない (Z-26) | (1) の手順の節名と手順文 |
| 9b | Cloud SQL Auth Proxy の unix socket モードを前提とし、TCP 経由で (1) が unknown のままである理由を書く (Z-34) | 前提の節名と本文 |
| 21 | DSN の取得と受け渡しが `set -x`・HTTP ログ・シェル履歴・argv への展開を禁じ、画面に出さない形だけを書き、`inventory` をサブシェルで実行する (D-10) | DSN の受け渡しの節名と手順文 |
| 24 | 証跡をどの git リポジトリの外にも置き、報告は判定と識別子を含まない件数だけ (D-11) | 証跡と報告の節名と手順文 |
| 28 | gcloud をプロンプト無効で実行し、API 無効・権限不足・対話は unknown とし、API を有効化しない (Z-12) | 節名とコマンドの形 |
| 38 | 射影された項目だけを出し、すべての container を見て、射影が空・必ずある env 名が無いときは unknown とし、(7)・(9) の判定規則を持つ | 節名と射影の式 |
| 38a | 許可表に無い env の値を読まず、許可表の env が未設定なら unknown (Z-19) | 許可表 (env 名の列挙) と射影の式 |
| 38b | (7) で deploy が env を引き継ぐ形なら、現行 revision の env 名に変更を適用した結果で判定し、旧 env の明示の削除が無ければ blocked (Z-29) | 判定手順の節名と手順文 |
| W1-D1 | Q-1 (c) の migration ごとの互換性の表を runbook に置き、独立レビュー (`reviewer`、設計レビューのモード) が受理した (W-1) | 表の節名と、受理の記録 (レビューの結論と対象の版) |
| W1-D2 | Q-2 (c) のロック種別・停止時間の上限・適用時 `lock_timeout` の表を runbook に置き、独立レビューが受理した (W-1、W-4) | 表の節名と、受理の記録 |
| W1-D3 | 起票原文の手順 2 の手順 (0007 / 0011 / 0012 の適用、per-application upgrade、declaration、legacy env の除去、Data / Control restart、health、traffic、rollback) を runbook に置き、独立レビューが受理した (W-1) | 手順の節名と、受理の記録 |
| W7-D1 | Q-2 (c) の表に「per-application upgrade」「deprovision」の行があり、その値を CLI の必須引数に渡し、0007 / 0011 / 0012 は `PGOPTIONS` 経由で表の値を渡す手順がある (W-7) | 表の該当行と手順文 |
| W3-2 | (10) について、本番の Gate-0 では (9) で attest した ref に当たる接頭辞 N を記録するだけにする (W-3) | 該当手順の節名と手順文 |
| W6-1 | production の手順より前に、isolated で `--quiet` のときの API 有効化プロンプトの既定応答を確かめ記録するゲート手順がある (W-6) | ゲート手順の節名と手順文 |
| W5-D | runbook の受理記録を `security/CONTROL_MAPPING.md` の対応行に足し、Version 行の minor を 1 つ上げる (W-5) | 追加した行と Version 行の前後、該当ブロックの文字数の実測 |
| 47 | 追加した runbook の本文と対応行に実値が無い (C5) | `public_value_scan.py` の集計行 |
| 50 | 本表に監査照合を持たない行が無い | 本表の行数と対応数 |

**件数**: 完了条件 19 件 = 監査照合 19 件 (変異 0 件。runbook は実行コードを持たず、設計 §7 と W-1・W-6 がこれらの行を監査照合と定める)。

### 6.1 WP-D の訂正註 (2026-09-17、v1.2 で追記。§6 の本文は書き換えない)

**訂正註 WPD-1 (順序と仕上げ)**: WP-D は §6A の WP-E の統合後に仕上げる。仕上げには、runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` の既存の古い手順 (`--lock-timeout` の欠落、DSN を argv に置く psql の呼出し、TCP の Cloud SQL Auth Proxy) の書き直しを含め、英語で書く (§6A 冒頭の依頼者裁定の (f))。

**訂正註 WPD-2 (未コミットの起草)**: WP-D の未コミットの起草 (runbook の §10 と `security/CONTROL_MAPPING.md` の変更) は worktree `.claude/worktrees/r45-wpd` に残っている。WP-E の統合後の main で基点を取り直してから扱う。

**訂正註 WPD-3 (W7-D1 の読み替え、§6A.2 の E-R8)**: §6 の W7-D1 と規則のうち「0007 / 0011 / 0012 は psql に `PGOPTIONS` 経由で表の値を渡す」は、「0005 / 0007 / 0011 / 0012 の適用は WP-E の E4 のサブコマンドに `--lock-timeout` と表の値を渡す」と読み替える (0005 は E4 が受け付ける集合に含まれるので、runbook の表にも行を置く。§6A.2 の E-R12・E-R20 の L6)。runbook に手で `PGOPTIONS` を組む手順は書かない。本番での実行の範囲は §6A.2 の E-R18 に従う。

**訂正註 WPD-4 (WP-F との順序、v1.4 で追記)**: WP-D は §6B の WP-F の統合後に基点を取り直し、runbook に 0013 (`0013_role_statement_timeouts.sql`) の適用手順 (`apply-platform-migration`) を足す。さらに、runbook は platform migration を常に番号順に一式 (0005・0007・0011・0012・0013) で適用し、1 本だけを順序を外して適用しないと書く (§6B.2 の F-R22 の (ii)。0012 と 0013 は同じ関数を `CREATE OR REPLACE` する)。

**訂正註 WPD-5 (0013 の適用の前提と、満たさないときの直し方、v1.5 で追記。§6B.2 の F-R27 と §6B.11 の監督裁定 F-S3)**: runbook に、0013 を適用する前提と、満たさないときの直し方を書く。

- 前提: 0013 を適用する role が、`mitatedbsvc_auditreader` と各 application の runtime / developer role への ADMIN OPTION を持つ。0005 と `begin_provision_application` を同じ role で実行していれば満たされる (PostgreSQL 16 は CREATEROLE の保持者に、自分が作成した role への暗黙の ADMIN OPTION だけを与える)。満たさないときの 0013 は、回避せずに失敗し、1 つのトランザクションごと巻き戻って `apply-platform-migration` が 0 以外で終わる。
- 直し方は次の依頼者裁定のとおり (1) だけを書く。

> 依頼者裁定 (2026-09-17、WPD-5。逐語)
>
> 監督の提示 (要旨): 0013 は、適用する role が auditreader への ADMIN OPTION を持たない環境では失敗する。runbook (WP-D) に書く直し方は (1) `GRANT mitatedbsvc_auditreader TO <provision role> WITH ADMIN TRUE, INHERIT FALSE, SET FALSE` で通常の環境と同じ状態にする、(2) auditreader を作った role で 0013 を適用する、のどちらか。監督の推奨は (1) だけを書く ((2) は application role への ADMIN と関数の所有者の 2 点で別の失敗を生みやすい)。(1) の未確認点 (provision role が membership を持つことを既存の検査が異常と見ないか) は WP-D で使い捨てクラスタで実測する。
>
> 依頼者:「1 で進めてください」

- WP-D は使い捨てクラスタで次の 2 点を実測する: (a) 上の GRANT の後に 0013 を適用できること、(b) provision role が membership を持つ状態を、0005 の `assert_role_has_no_memberships` と `inventory` の role の判定が異常と見ないこと。

### 6.2 WP-D の実施記録と監督裁定 (2026-09-18、統合時に監督が追記。§6・§6.1 の本文は書き換えない)

**(a) 経過**

- 基点は WP-F 統合後の main。訂正註 WPD-2 の古い worktree (`r45-wpd`) に残っていた日本語の未コミットの起草は diff として材料にするだけにし、新しい worktree で英語で書き直した (訂正註 WPD-1)。
- 独立設計レビューは計 3 起動・6 回 (1 回目が別起動、2 回目が別起動、3〜6 回目は 3 回目の起動の継続)。監督の差し戻しは 4 回。
- §10.10 の手順の版は 1 → 5。§10.6・§10.7 の表の版は 1 → 2 で、版 2 の本文は以後 1 字も変えていない。§10.8 の受理記録の版の表記 (2 / 2 / 5) と `security/CONTROL_MAPPING.md` の Version 行・Evidence・Status は互いに一致する。

**(b) 依頼者裁定 (2026-09-18、Gate-0 の入口。逐語)**

> 監督の提示 (要旨): 設計 §1.2 は「unknown は先へ進まない。10 項目すべてが confirmed のときだけ ready」と定める。0013 未適用の本番では (6) が unknown になり (WP-F の枠決めの裁定「設定が無いときは従来どおり unknown」)、runbook の初稿は「unknown が 1 つでもあれば upgrade の手順を始めない」と書くので、0013 を適用できず堂々巡りになる。(8) にも同じ形が 3 つある (`MITATEDB_MAX_CONCURRENCY` が未設定、予約接続数が未確定、`process_ceilings` の宣言の更新が手順の中にある)。案 A (推奨): runbook を 2 段にする — 最初の読み取りで unknown / blocked を `blocked—platform remediation required` と報告 → 直しの段 (platform migration の一式適用、env だけの変更、予約接続数の確定、`process_ceilings` の再宣言。ここを縛るのは Gate-0 ではなく、isolated での証明・独立監査・依頼者の承認) → 再読み取りで 10 項目すべてが confirmed になってから candidate の deploy と traffic の切り替えに進む。コードは変えない。設計 §1.2 の「先へ進まない」の「先」は candidate の deploy と traffic を指す、と設計メモに訂正を 1 つ足す。案 B: `inventory` を変えて設定なしを confirmed + remediation-required にする ((6) を緩めることになり、先の裁定を覆す。コード変更の WP が 1 本増える)。
>
> 依頼者:「案 A で進めてください」

- 設計メモ側の訂正は `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §1.2 の【訂正 2026-09-18】に置いた (行は消していない)。コードは変えていない。
- WPD-5 の依頼者裁定 (2026-09-17) は §6.1 に逐語で記録済みで、本 WP はそれに従って直し方を 1 つだけ書き、使い捨てクラスタで実測した (実測の要点は設計メモ §12.6)。

**(c) 監督裁定の一覧 (差し戻し 1〜4 と、レビュー 5 の指摘への裁定。1 件 1 行)**

差し戻し 1 (出所: 設計レビュー 1 回目)

- **D1-1 (高。Gate-0 の堂々巡り)** — 上の依頼者裁定 (案 A) のとおり §10 を 4 段 (最初の読み取り → 直しの段 → 再読み取り → candidate) に組み替える。**現行**: 設計 §1.2 は unknown で先へ進まないと定め、初稿は「unknown が 1 つでもあれば upgrade の手順を始めない」と書いていた。**シナリオ**: 0013 未適用の環境では (6) が unknown になり、0013 を適用する手順に入れないまま止まる ((8) にも同形が 3 つ)。**直し方**: ready が gate するのは candidate の deploy と traffic の切り替えだけとし、直しの段を縛るのは isolated での証明・独立監査・依頼者の承認とする。「直しの段で解消できる原因」を項目・原因・対応する手順の表で列挙し、表に無い原因の unknown / blocked は止まる。再読み取りで残った unknown を warning として続行しないことは保つ。手順の版を 2 に上げる。
- **D1-2 (中)** 0007 の再適用は値に中立でない: 0007 は api / controlplane role の timeout を無条件に既定値へ戻し、`audit_writer_roles` の宣言を `ON CONFLICT DO UPDATE` で置き換える。一式適用は毎回これを起こすので、適用の前に現在の宣言と `set-platform-timeouts` で変えた値を控え、0007 の直後・restart の前に再宣言・再設定する。控えは証跡と同じ置き場 (git リポジトリの外) に置く。
- **D1-3 (中)** ADMIN OPTION の前提は 0013 に固有でない: 一式適用が `ALTER ROLE` を掛ける全 role (0007・0012 の api / controlplane role、0012・0013 の application role、0013 の auditreader) について、適用する role が ADMIN OPTION を持つことを前提として一般形で書く。直し方は `GRANT <the role> TO <provision role> WITH ADMIN TRUE, INHERIT FALSE, SET FALSE` の 1 形だけ。**実測は auditreader についてのものであり、api / controlplane / application role については同じ PostgreSQL 16 の規則からの推論で未実測である旨を明記する。**
- **D1-4 (中)** 段の組み替えで手順番号が変わるので、§10 の中の手順の相互参照を全件付け直す。
- **D1-5 (中)** 直しの段と candidate の段を本番に対して実行してよいのは、isolated の組で同じ手順を証明し、独立監査を受け、依頼者の承認を得た後だけであると §10 の冒頭と直しの段の冒頭に書く。
- **D1-6 (中)** 報告語を設計 §1.2 の逐語 (em dash、U+2014) に全件そろえ、受け手が literal で照合する語である旨を 1 文添える。
- **D1-7 (中)** 表の根拠にした source ref の範囲 (rollback target がその範囲の外なら (5) を confirmed にしない)、(8) の出力は 3 キーだけなので「現行値を読め」を実際に値を読める経路に直す、(8) に渡す process 数の説明を算法 (各 service の `maxScale` の合計 + candidate の上限) に合わせる、`git fetch origin <ref>` の後は `FETCH_HEAD` を読む、§3 の新しい前文に既存の bootstrap に残る `-v …password=` / `-c "ALTER ROLE … PASSWORD"` が初回限りの例外である旨を 1 文で書く。
- **D1-8 (低・佐)** レビュー全文の案のとおり直す。annotation の射影に operator の email が入りうるので、射影から annotation を外すか必要な annotation だけを名指しで射影する。provision role 自身に `GRANT pg_signal_backend` を実行させる既存の形は触らない (台帳へ起票した。下の (i)〜(iii) の (iii))。
- **`security/CONTROL_MAPPING.md`** SI-09 の MitateDB-api ブロックの 3 bullet を 2 段の流れと版に合わせ、Version 行の要約も合わせる。SI-08 は 1 字も変えない。

差し戻し 2 (出所: 設計レビュー 2 回目。手順の版 3。§10.6・§10.7 の表は据え置き)

- **D2-1 (高。(8) の検算を状態変更の前に)** — **現行**: (8) の需要は process 数の合計に比例する (controlplane = 合計 × 16、auditreader = 合計 × 4、api = 合計 × 2 × concurrency、application role = 合計 × concurrency)。0012 の `CONNECTION LIMIT` は 68 / 20 / 36、auditreader は 0005 の 5 のままで、どれも 1 plane 1 process・concurrency 32 の前提の値である。**シナリオ**: candidate と traffic を持つ revision が並ぶと合計が 2 以上になり (8) は blocked になるが、最初の読み取りでは (8) が別の原因で unknown になりうるので、本番を変え終えた再読み取りで初めて分かる。**直し方**: §10.10 の Preconditions (直しの段より前) に、状態を 1 つも変える前に需要の算術を、再読み取りで渡す予定の入力と catalog から読んだ各 role の `CONNECTION LIMIT`・`max_connections` とで検算する手順を置く。1 つでも収まらなければ直しの段を始めず `blocked—platform remediation required` として報告して止まる (この runbook に直し方は無い。上限の変更は新しい platform migration を要する)。「直しの段で解消できる原因」の表の (8) の行に、上限が需要に足りないことはこの表で解消できない原因である旨と、0012 が auditreader と provision role の上限を変えない旨を書く。**runbook に「現在の値では 2 process が収まらない」という評価は書かない** (値と入力は環境ごとに読むもの)。この件は台帳に起票した (下の (i))。
- **D2-2 (高。concurrency の env と traffic)** — **現行**: `--set-env-vars` は env を全置換する。**シナリオ**: env だけを変える revision が別の digest や欠けた env で作られる、traffic が revision に pin された service では新しい revision に traffic が向かない、candidate の deploy に concurrency の env を含め忘れると (8) を判定した値と違う値で走る。**直し方**: env だけの変更は traffic を持つ revision と同じ image digest・同じ env に `MITATEDB_MAX_CONCURRENCY` を足した (および legacy env を除いた) 形で作る。traffic が pin されている service では、新しい revision に traffic を明示的に移す手順 (health の確認と前の revision へ戻す rollback を含む) を同じ手順の中に書き、これは本番の traffic の変更なので直しの段の開始条件の対象に含まれると明記する。candidate の deploy の env に同じ concurrency の値を必ず含める。§10.4.3 の concurrency の規則が読む対象は traffic を受けうる revision (traffic を持つもの、tag で到達できるもの、candidate) とし、不一致・未設定は unknown。
- **D2-3 (中)** 再読み取りの所見が表にある行なら、その行の手順だけをやり直して再読み取りしてよい ((8) は 1 回に 1 つの原因しか返さない) / `export PGPASSWORD=<DSN の password 欄>` の形をやめる (DSN を表示させることになる) / SI-09 の「and restores them」を事実に合わせる (戻すのは timeout と `audit_writer_roles` で、`CONNECTION LIMIT` は控えるだけ) / libpq 環境変数の拒否の説明を現物に合わせて一般化する (拒否が掛かるのは psql を起動する経路だけである)。
- **D2-4 (低)** `set-platform-timeouts` に渡すのはミリ秒の整数だけ / 表に「(8) の宣言が壊れている」「(2) の宣言の表自体が無い」の行を対応する手順とともに足す / 宣言を先に変えてから deploy する順序が安全なのは宣言する上限を上げる向きだけである / Rollback の節に §10.6 の未検証の範囲を再掲する。

差し戻し 3 (出所: 設計レビュー 3 回目。手順の版 4)

- **D3-1 (高。検算の上限は再読み取り時点の値)** — **現行**: 0012 は自分が名指す role の上限を自分の値にそろえ (低い値を上げ、高い値を下げる)、0012 が名指さない role (auditreader = 0005 の値、provision) は触らない。**シナリオ**: 検算が catalog の現在値だけを見ると、0012 未適用の deployment では解消できる不足で直しの段が始まれず、逆に段 2 で変わる値を見落とす。**直し方**: 検算が比べる上限は「再読み取りの時点で各 role が持つ上限」とし、0012 が名指す role は 0012 自身の値、それ以外は手順 2 の catalog の値を代入する。`-1` は、0012 が名指す role なら 0012 の値を代入し、名指さない role なら止まる。表の該当セルを 0012 が実際にすることに合わせ、`-1` の行との矛盾を無くす。**0012 の値そのものや数え方の当否は runbook に書かない。**
- **D3-2 (中)** libpq 環境変数の拒否の説明を現物に合わせる: 拒否されるのは DSN が上書きしない変数だけで、ここで export する変数には掛からない。別のサブシェルで実行する理由は psycopg で直結する経路が環境変数を黙って読むことである。
- **D3-3 (中)** tag だけで到達できる revision の出口を 1 句足す: tag を外す (`gcloud run services update-traffic … --remove-tags`) のが唯一の出口で、それ自体が traffic の変更なので env だけの変更と同じ開始条件 (isolated での証明・独立監査・依頼者の承認) に従う。candidate の検証が tag URL を使うなら candidate を tag 付きで deploy することと手順の終わりでの tag の扱いを書き、使わないなら health の確認を現物の形に直す。
- **D3-4 (中)** 手順の参照語を「§10.4.3 の `--concurrency` の規則が読む revision」に直し、traffic を受けられない warm revision (`minScale` ≥ 1 だけ) は値の一致の対象外だが process 数の合計には入ることを足す。
- **D3-5 (低)** application 0 件の枝、auditreader の需要の枝、`2 stores`、passfile の mode 0600、§10.1 の DSN の形と手順 2 の前提のそろえ、env だけの変更の対象 service の区別、表のセルの「(no step to re-run)」、rollback の戻し先の記録を traffic の移動より前に固定する。

差し戻し 4 (出所: 設計レビュー 4 回目。手順の版 5)

- **M4-1 (中)** tag の除去を直しの段の「状態を変える」ものの列挙に入れ、段の表・「この段が動かす traffic」の文・SI-09 の bullet の 4 箇所を互いに矛盾しない形にそろえる (割合は動かないが同じ traffic の射影であり、同じ 3 つの開始条件が掛かる)。
- **M4-2 (中。passfile の出所 = 案 (a))** secret は §5 の `password=` の形を保ち、§10.1 が節の頭で一度だけ passfile の形に変換する (`umask` と `mktemp -d` の私有ディレクトリ、psycopg の `conninfo_to_dict` / `make_conninfo` を使う変換スクリプト、mode 0600、`password=` を `passfile=` に置き換えた同じ DSN を command substitution で受け取る、節の終わり (完走でも中断でも) に passfile とディレクトリを消す)。password は 1 ファイルにだけ入り、画面・argv・シェル履歴・`set -x` に出ない。
- **M4-3 (中)** `security/CONTROL_MAPPING.md` の Version 行・Evidence・Status の版の表記を手順の版 5 にそろえる。
- **N4-1 (低)** 検算の段落から provision role を落とす ((8) は両監査表の所有者を対象にしない)。
- **N4-2 (低)** (6) の `-1` の行は、0012 が名指す role の `-1` だけがこの表で解消することを書く。

レビュー 5 の指摘への裁定 (手順の版は 5 のまま。§10.1 は手順の節ではないため版を上げない)

- **M5-1 (中。passfile の第 1 列)** passfile の host と port を wildcard (`*`) にする。**理由**: libpq が unix-socket 接続の照合でホスト名を既定のホスト名に置き換える読みが正しければ、socket のパスを第 1 列に書いた行は当たらず、passfile 形に切り替えた直後に §10 の全 DSN 経路が認証で失敗する。この作業機では libpq の照合を実測できず (PostgreSQL 16 の libpq の文書・ソースが無く、共有ローカル PostgreSQL への接続は禁止)、**どちらの読みでも通る形を採る**。あわせて escape の説明を password の中の `:` と `\` に直し、「両方の接続経路が受け付ける」の断定に、本番の前に isolated の組で確かめる 1 句を添える。**残余 (受理の条件には数えない)**: `*:*` なので、同じ dbname + user で別の instance に繋げば password が渡る。範囲は mode 0600・`mktemp -d` の 0700・`~/.pgpass` ではないこと・節の終わりの削除で閉じている。
- **N5-1・N5-2 (低)** 2 度目の実行は「同じパラメータで素通しするので安全」と書く (文字列の並び順は変わる) / DSN を書き出す禁止の bullet に、converter が書くのは password だけで DSN ではない旨の 1 句を添える。
- **N5-3 (低)** 起草の報告の file:line が現物と 6 行ずれていた (内容は正しい)。記録の訂正だけで文書の変更は無い。

**(d) 受理の記録**

- 対象と版: **W1-D1 = §10.6 の版 2**、**W1-D2 = §10.7 の版 2**、**W1-D3 = §10.10 の版 5**。いずれも独立設計レビュー (`reviewer`、設計レビューのモード) が「受理できる」とした。**受理日 2026-09-18**。runbook §10.8 の 3 行に記入済み (現行の版 = レビューした版 = 2 / 2 / 5、結論 = accepted、レビューの所在 = 設計メモ §12.6)。
- 設計レビュー 6 回目の最終の所見 (逐語):

> - **W1-D1 — §10.6 per-migration compatibility table、版 2: 受理できる** (`:2276`、行数 11・第 6 列付き、本文はレビュー 2 以降 1 字も変わっていない)。
> - **W1-D2 — §10.7 lock / stop time / `lock_timeout` table、版 2: 受理できる** (`:2325`、8 行、本文不変)。
> - **W1-D3 — §10.10 platform upgrade procedure (stages 2-4)、版 5: 受理できる** (レビュー 3〜5 の高 1 件・中 6 件・低 11 件はすべて現物と食い違わずに解消。0012 未適用の deployment でも段 2 が始まれる形になり、本番を変えた後に初めて分かる停止・unknown の抜け道・堂々巡りは残っていない。`security/CONTROL_MAPPING.md` の Version 行・Evidence・Status・SI-09 の bullet と §10.8 の 3 行 (2 / 2 / 5) は互いに一致)。
> - 変更クラスは宣言どおり **Class D** (`tools/change_class.py` = `class=D`)。引き上げは無い。

**(e) 完了条件 19 件 → 監査照合 (版 5 の現物の見出しで照合)**

§6 の完了条件はいずれも変異を持たない監査照合である。照合先は runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` の §10 (4 段構成、手順 1〜17) と `security/CONTROL_MAPPING.md`。

| # | 監査照合の対象 (版 5 の現物) |
|---|---|
| 3 | §10.9「Overall judgment」の表と、その直後の「Gate-0 is ready only when all 10 items are confirmed AND §10.8's …」の箇条 (§10.9 の前文は、この節を最初の読み取りと再読み取りの両方で同じに使うと述べる) |
| 3a | §10.9「Report」の第 1 箇条と書式ブロック (unknown と blocked をともに `blocked—platform remediation required` に写し、内訳を併記する) |
| 9a | §10.4.1 Item (1) isolated/production pair |
| 9b | §10.1「Run the Cloud SQL Auth Proxy in unix-socket mode for this section」(TCP では (1) が unknown のままである理由)。§2・§4・§7 の整合の註 |
| 21 | §10.3 Passing the DSN 全体 (環境変数だけ、`set -x` / HTTP ログ / 履歴 / argv 展開の禁止、サブシェル) と §10.1「Where that passfile comes from.」 |
| 24 | §10.1「Where the evidence goes」(どの git work tree の外にも置く) と §10.9「Report」(識別子を含まない件数だけ) |
| 28 | §10.1「gcloud」(プロンプト無効、API 無効・権限不足・対話は unknown、API を有効化しない) |
| 38 | §10.4 の前文「Write only the projected fields into the evidence.」・「Projection table」・「Env names that must be present」・「What makes an item `unknown` (all items)」と、§10.4.2・§10.4.4 の判定規則 |
| 38a | §10.4「Env-value allow-table」 |
| 38b | §10.4.2 Item (7) legacy base-URL env vars (env を引き継ぐ deploy は現行 env に変更を適用した結果で判定し、旧 env の明示の削除が無ければ blocked) |
| W1-D1 | §10.6 Per-migration compatibility table (item (5))、版 2 と §10.8 の第 1 行 |
| W1-D2 | §10.7 Lock type, stop-time limit, and applied `lock_timeout` table (item (6))、版 2 と §10.8 の第 2 行 |
| W1-D3 | §10.10 Platform upgrade procedure (stages 2-4)、版 5 = Preconditions ((8) の需要の検算を含む)・Stop conditions・「Applying a platform migration」・§10.10.1 Stage 2 (手順 1〜11 と「Findings from the first read that this stage resolves.」の表)・§10.10.2 Stage 3 (手順 12)・§10.10.3 Stage 4 (手順 13〜17 と「Rollback」) と §10.8 の第 3 行 |
| W7-D1 | §10.7「How the table's values are passed」(0005・0007・0011・0012・0013 は `apply-platform-migration` に `--lock-timeout` と表の値を渡す。per-application upgrade と deprovision の行あり) と §10.10「Applying a platform migration」。**手で `PGOPTIONS` を組む手順は書いていない** (訂正註 WPD-3) |
| W3-2 | §10.4.5 Item (10) starting prefix N |
| W6-1 | §10.2 Isolated check of `--quiet`'s own default answer (gate before production) |
| W5-D | `security/CONTROL_MAPPING.md` の SI-09 MitateDB-api ブロック (Control・Evidence・Status の各 bullet) と Version 行 **2.5 → 2.6**。実測: SI-09 の MitateDB ブロック **8,993 → 12,793 字** / 上限 15,200、SI-08 の MitateDB ブロック **15,194 字で不変**、最長行 **1,384 字** / 上限 1,400 (基点と同じ行)。`conformance-tests/test_control_mapping_register.py` **11 passed** |
| 47 | `python3 tools/public_value_scan.py` の集計行 `# mode=tree files_scanned=2 total_flagged=0` |
| 50 | 本表は 19 行で、19 行すべてに監査照合の対象がある。対応の無い行は 0 |

**(f) 触るファイルの訂正註 (WPD-1 の既存の手順の書き直し)**

- WP-D は §6 の表の「触るファイル」の範囲で、`MitateDB-api/docs/cloud-run-cloud-sql.md` の **§10 の新設だけでなく、既存の節の古い手順も直した**: §3 の前文に接続設定を libpq の環境変数で渡す規約を置いて §3・§3.1・§3.2・§3.2b・§3.2e・§3.4・§3.4a・§9 の psql の呼出しから argv の conninfo を外し、§3.4b と §7 の `upgrade-applications` / `deprovision` に必須の `--lock-timeout` を入れ、§7 の一覧に `apply-platform-migration` と `inventory` の行を足し、§2・§4・§7 に Cloud SQL Auth Proxy のモードの註を足した。§4 の provision DSN の欄には passfile 形との関係を 1 句足した。
- 触らないと定めた §0.1・§9.1 の operator-reported の記録と SI-08 のブロックは 1 字も変えていない (実測)。
- 直さずに残した箇所と理由 (報告のみ): psql 変数 (`-v`) と `-c` の SQL literal に secret が乗る既存の bootstrap の形 (argv 以外に渡す道が無く、手順の機構そのものの変更になる。§3 の前文に初回限りの例外として明示した)、`ALTER ROLE … PASSWORD '$(openssl rand -base64 32)'` が生成値をどこにも捕まえない既存の欠陥、§2・§3 の TCP 前提そのもの。§9 の `psql "$MITATEDBSVC_PROVISION_DSN" …` (実装の env 名は `MITATEDB_PROVISION_DSN`) は、DSN を argv に置く形の訂正 (WPD-1) で libpq の環境変数の形に直り、その env 名の言及は無くなった (§9.1 の記録は無改変)。

**(g) 本番に対して何も実行していない**

- 本 WP では gcloud・psql・`ops` のいずれも本番に対して実行していない。§10 は本番を読む手順と更新する手順を書くが、本 WP の中では実行しない (§6 の規則、§7)。
- 実測は使い捨てクラスタ (WPD-5 の 5 項目) と、passfile の変換スクリプトの合成値での実行 (作業用の一時ディレクトリ内、実行後に削除) だけである。runbook の検証は文書の照合と独立設計レビューで行った。
- 実行した道具: `python3 tools/check_doc_refs.py` (dangling 0、tracked markdown 130 / empty 0)、`python3 tools/public_value_scan.py` (`files_scanned=2 total_flagged=0`)、`tools/change_class.py` (`class=D`)。Class D の文書変更のため root gate は回していない。W5-D の照合として `conformance-tests/test_control_mapping_register.py` を実行した実測は **11 passed** である。

**(h) 統合コミット**

- 作業コミット `40cdbd0`、main へのマージ `b484bd4` (2026-09-18)。統合後の木に対する監督の完了ゲート: `3688 passed, 2 subtests passed`、`judge=PASS`、実行クラスタの `pg_database` / `pg_roles` の差分 0。`tools/tests` は `492 passed`

### 6.3 R-45 の受け入れ監査と監督の受け入れ判定 (2026-09-18。§3〜§6B の本文は書き換えない)

**受け入れ監査** (`evidence-auditor` 1 回、全 WP のレビュー完了後。対象は main `2cc260f`): 完了条件ごとの判定は、WP-A 13 行 = 充足 10・証拠不足 3、WP-B = 証拠不足 1、WP-C = 証拠不足 2、WP-E 42 行 = 充足 42、WP-F 39 行 = 充足 39、WP-D 19 行 = 充足 19。**未充足は 0 件。** 完了ゲートの集計行は 2 本とも `3688 passed, 2 subtests passed`・`judge=PASS`・実行クラスタの差分 0 (WP-F の統合前の branch と、WP-D の統合後の木)、`tools/tests` は `492 passed`。ログの進捗行に skipped / xfailed / xpassed は 0 件で、§1.3 の 22・26 の合格条件を満たす。

**証拠不足の各件への監督裁定 (A-1〜A-6)**

| 裁定 | 本文 |
|---|---|
| A-1 | (WP-A 条件 49。ブロックの文字数の逐語記録が無い) 監査の実測を記録とする: WP-A の統合コミット `b41a377` で SI-10 の MitateDB-api ブロック 5,917 字・r2db-api ブロック 5,308 字、いずれも上限 15,200 の内。充足とする。 |
| A-2 | (WP-A・WP-C 条件 47。`public_value_scan.py` の集計行が要旨だけ) 当時の道具の出力は残っていない。現物の main に対する統合時の `finalize.py` の走査 (WP-F・WP-D の 2 回とも flagged 0) と、監査が差分に実値・絶対パス・credential を 0 件と確かめたことをもって充足とする。以後の WP は集計行を逐語で残す (WP-E 以降はそうしている)。 |
| A-3 | (WP-A・WP-C 条件 50。行数と対応数の逐語記録が無い) 監査の独立の検算を記録とする: WP-A = 13 行 = 変異を持つ 9 行 + 監査照合 4 行、対応の無い行 0。WP-C は監督が §5 の表を数え直し、18 行 = 変異を持つ 14 行 + 監査照合 4 行 (W5-C・46・47・50) で §5 の件数の記載と一致、対応の無い行 0。充足とする。 |
| A-4 | (WP-B。完了条件 → 変異 → 実テスト名の行ごとの対応表が記録に残っていない) 当時の変異定義と変異表は前のチャットの scratchpad にあり、引き継がれていない。名指しのテストは main に実在し (監査の `--collect-only`)、WP-B のゲート (§4.1) と以後の 3 本のゲートは緑である。変異の再実行はしない (変異定義が失われており、再作成は新しい証拠であって当時の証拠の復元ではない)。**受け入れるが、記録の欠落として残す。** 以後は WP-E・WP-F と同じく、対応表を作業指示書の訂正註に写してから scratchpad を手放す。 |
| A-5 | (WP-F・WP-D。§1.3 の 27 の性能差分の記録が無い) R-45 の全 WP は要求の経路のコード (`backend_postgres.py`・`cell.py`・HTTP 層) を変えていない (変更は `ops` の CLI・migration・テスト・文書)。0013 が置く role の既定値は、要求の経路では `SET LOCAL` が上書きする (WP-F 第 1 段の実測 (a))。性能差分は取らない。 |
| A-6 | (`public_value_scan.py` の R7 = 人名は道具が検査しない) 道具自身の註記のとおり人の目の確認に委ねる項目であり、監査は差分に人名・e-mail を見つけていない。commit identity は全コミット `r2fish` の noreply である。 |

**記録と現物の食い違い (監査の X-1〜X-3) の訂正**: 設計メモ §12.5 と roadmap の R-45・R-48 の行の「完了条件 38 件」を 39 件に訂正した (訂正註 F-1 のとおり)。roadmap R-53 の引用を現物の語 (`actually running right now`) に直した。設計メモ §12.6 の `inventory` の引数の数え方を現物の 8 本に直した。

**監査が両論で挙げた設計疑義への監督の見解**: (1) ADMIN OPTION の前提の実測が auditreader だけである点 — runbook は未実測と明記し、直しの段の開始条件が isolated の組での証明なので、api / controlplane / application role はそこで実測される。追加の WP にしない。(2) passfile の host・port の wildcard — runbook は isolated の組で認証を確かめてから本番で使うと定め、passfile は一時ディレクトリの 1 行・mode 0600・作業の終わりに削除。isolated で socket パスの形が通ると分かれば狭めてよい (runbook の版を上げて受理を取り直す)。(3) roadmap R-52 ((8) の容量) — 本番の読み取りより前に着手するかは依頼者の指示を待つ。Mitate への報告に含める。

**受け入れ判定 (監督)**: **R-45 の WP-A〜WP-F を受け入れる。** 未充足 0 件。証拠不足 6 件は A-1〜A-6 のとおり (A-4 は記録の欠落として残す)。本番に対しては、読むことを含めて何も実行していない。残りは Mitate への報告と、本番を読む経路の受け入れ後の Gate-0 の読み取りである (§7)。

## 6A. WP-E — `inventory` の (6)・(8) の判定の直しと platform migration の適用サブコマンド (Class D)

### 6A.1 依頼者裁定 (逐語)

> 依頼者の回答 (2026-09-17。Mitate の監督セッションが中継し、本チャットで依頼者が「はい」と確認した。逐語):
>
> 1 を選びます。条件:
> (a) WP-E は 1 本・manifest 1 本、範囲は提示の 4 件だけ。他の発見は台帳 1 行のみ(依頼者指示 REQUESTER_DIRECTIVE_20260916 §3.3)。
> (b) role の lock_timeout を判定から外すのは、DDL を流す全経路(platform migration・アプリ単位 upgrade・deprovision)で --lock-timeout が必須であることをテストで固定したうえで。4 件目(platform migration の公開サブコマンド)と対で受け入れる。
> (c) Control 未配備の 0 は、操作者が明示の引数で未配備を宣言した場合だけ受け付ける。読めない・不明は blocked のまま(不明を未配備と読み替えない)。
> (d) 新サブコマンドは本番に対して実行しない。試験は使い捨て PostgreSQL のみ。HANDOVER_20260916_FABLE2 付録 C の制約は継続。
> (e) クラス D の独立設計レビュー・コードレビュー・監査は省かない。記録は WP ごと 1 回。
> (f) runbook と security/CONTROL_MAPPING.md の英語は了承。引き継ぎ書に依頼者向けの日本語要約(手順の流れと Gate-0 各項目の読み方)を 1 節入れる。
> (g) WP-E の枠決めまでをこのチャットで行い、引き継ぎ書を書いて次のチャットへ移る。次の監督チャットは Fable で開く(OPERATING_CONDITIONS §1.1 の 1 と ROLES の役割表は main 4410c72 で更新済み)。
>
> 契約版数 1.8.0 据え置き(spec を変えない)とクラス D は提示のとおりで了承です。

(裁定中の依頼者指示は `docs/work-orders/REQUESTER_DIRECTIVE_20260916_R37_CLOSURE_R45_PRIORITY.md`、引き継ぎ書は `docs/work-orders/HANDOVER_20260916_FABLE2.md` を指す。)

### 6A.2 監督裁定 (E-R1〜E-R20、2026-09-17。v1.2 の起草時の疑義・確認事項と、manifest の独立設計レビューの指摘への裁定。逐語)

| 裁定 | 本文 (逐語) |
|---|---|
| E-R1 | (0007 の psql 変数) E4 のサブコマンドは、migration ファイルごとに必要な psql 変数を静的な表で持ち (例 0007 → `api_role`・`controlplane_role`)、対応する引数 (`--api-role`・`--controlplane-role`。role 名は秘密ではない) を受け取る。表にある変数の引数が欠けていれば固定文言で拒否、表に無い引数を渡しても拒否。表と各ファイルが実際に参照する `:変数` の集合が一致することをテストで固定する。 |
| E-R2 | (`MITATEDB_MIGRATIONS_DIR`) 既存の設定としてディレクトリの解決に使ってよい (使い捨てのディレクトリでの試験のため)。「任意パスを受け付けない」は、引数を**ファイル名**に限り (パス区切りを含めば拒否)、既知の platform migration の名前の列挙に一致し、解決したパスがそのディレクトリの中にあることで満たす。 |
| E-R3 | (「DDL を流す」の範囲) 依頼者裁定 (b) が列挙した 3 経路 — platform migration (E4)・per-application upgrade・deprovision — を「psql でファイルを流すサブコマンド」として定義し、その集合と `--lock-timeout` 必須の集合の一致を固定する。psycopg で設定を書く `set-platform-timeouts`・`declare-*` はファイルを流さない設定操作として集合の外とし、その理由を本文に書く (台帳は起こさない)。 |
| E-R4 | (E2 の入力) 合計 (新旧の合計) が単体の上限より小さい入力は矛盾として固定文言で拒否する (終了コード 1)。 |
| E-R5 | (E3 と宣言表) `--control-not-deployed` のとき、Control の宣言値は「許される上限」を表すので未配備との食い違いにしない。Control 側の宣言との比較は行わず、余力の計算で Control の process 数と auditreader の接続を 0 とする。出力に `control_deployed: false` を持たせ (キー集合の pin を更新)、判定語は変えない。 |
| E-R6 | (CONTROL_MAPPING) E1〜E3 で事実でなくなる SI-08 の既存の (6)・(8) の主張は、同じ行を事実に合わせて直す (新しい行は足さない。ブロック長 15,200 以内を実測)。E4 の新しい統制の行は SI-09 に置く。英語。 |
| E-R7 | (設計レビュー) 手順に「manifest の独立設計レビュー 1 回」を実装の前に置く (本チャットで監督が実施する。依頼者裁定 (e))。 |
| E-R8 | (WP-D の W7-D1) 0007 / 0011 / 0012 の適用は E4 のサブコマンドに `--lock-timeout` と表の値を渡す形に読み替える (手で `PGOPTIONS` を組む手順は書かない)。§6.1 の訂正註に書く。 |
| E-R9 | (名前) 起草案の名前 (サブコマンド名・引数名) をそのまま採る。 |
| E-R10 | (`control_deployed`) (8) の項目の中に置き、常に出す (宣言が無ければ `true`、`--control-not-deployed` のとき `false`)。両方を完了条件と変異で固定し、キー集合の pin を更新する。 |
| E-R11 | (E3-6) 未配備を宣言したとき、Control が使う role (controlplane・auditreader) は (8) の -1 の検査と余力の計算の対象から外す。(6) の実行時設定では、role が存在する限り従来どおり読む。 |
| E-R12 | (E4 の受け付けるファイルと WP-C のテスト) E4 が受け付けるのは、`:app_id` を取らずアップグレードで再実行される platform migration の 0005・0007・0011・0012 だけ (bootstrap の 0001・0002 は初回構築の手順であり受け付けない)。この集合を定数で pin し、ディレクトリの `:app_id` を取らないファイルとの差が bootstrap の 2 件だけであることを assert する。WP-C の再実行性テストのうち、0005・0007・0011・0012 の「もう一度適用」は E4 のサブコマンド経由に置き換える (同じ変更セット。起点までの過去の内容の適用は psql の直接実行のまま)。 |
| E-R13 | (H1) E4 経由の再適用テストは、適用の直前に対象オブジェクトの状態を手でずらし (ACL・関数本体・ロール設定・宣言の制約など、その migration が作るもの)、E4 のサブコマンドで元に戻ることを assert する形にする。変異「psql を起動せず 0 を返す」を赤で固定する。WP-C の証拠を弱めない。 |
| E-R14 | (H2) E1 の行に、本番では E1 の後も (6) が unknown のままであること (auditreader と application の runtime / developer role に `statement_timeout` を設定する経路が無い) と、role の `lock_timeout` はもともと DDL を流す provision role の歯止めではなかったことを書く。(6) を confirmed にする作業は範囲 (a) の外なので、監督が台帳に **R-48** として 1 行起票する (本 manifest のコミットで roadmap に足す。文面は監督が書くので本文には「R-48」の参照だけ置く)。 |
| E-R15 | (M1) (b) の集合は「psql の起動」または「`_migrations_dir()`・`discover_upgrade_scripts` の呼出し」に到達するサブコマンドの和として AST で導き、`--lock-timeout` 必須の集合と一致させる。加えて psql を起動する全関数が `_with_lock_timeout_option` を通ることを静的に assert する。E1-5 の本文とテスト名を「3 つを含み、`set-platform-timeouts`・`declare-*` を含まない」に揃える。 |
| E-R16 | (M2) E3-8 (iv) は `--control-not-deployed` の有無の両方で回すと明記する。 |
| E-R17 | (M3) §6A.4 の手順に、統合時に監督が設計メモの D-1 (6)・(8)、§7 の 33b、§12.3 の該当記述に打ち消し線と註を入れる記録手順を足す。 |
| E-R18 | (M4) E4 行に (d) の範囲を書く: WP-E・WP-D の作業では E4 を本番に対して実行しない。本番での適用は本書 §7 の後続 (isolated での証明 → 独立監査 → 本番更新) で、依頼者の承認の後にだけ行う。 |
| E-R19 | (M5) CONTROL_MAPPING: E1-4 の網羅の主張は SI-09 に置く。SI-08 は (6)・(8) の既存の主張と証拠のテスト名を**置き換え**で直し (追記しない)、ブロック長を実測する。15,200 を超えるならその時点で止まって監督へ上げる。 |
| E-R20 | (L1〜L7) すべて反映する。L1: `inventory` の入力の検証による拒否 (E-R4、E3-2・E3-3、argparse の使用法エラーを含む) は終了コード 1 (判定の 2 と区別する)。E4 の拒否は ops の既存の `_die` の規約に従い、その値を本文に書く。L2: `--` コメントと `::` キャストを除いて `:変数` を抽出する規則。L3: 両側を resolve して比べ、`MITATEDB_MIGRATIONS_DIR` が信頼境界であることを書く。L4: 件数を数え直す。L5: `check_comment_provenance.py --base` と `docs/code-history/MitateDB-api/` を手順と触るファイルに足す (新規コメントに CH-ID は付けない)。L6: WPD-3 に 0005 を足す。L7: role は付与から見つける実装に合わせて書き、Control の role が 1 つも無い場合は除外対象が空になるだけ、と書く。 |

### 6A.3 目的と範囲

**目的**: WP-B で統合された `inventory` の (6)・(8) の判定を次の E1〜E3 のとおり直し、platform migration を適用する公開サブコマンド E4 を足す。範囲はこの 4 件だけとし (裁定 (a))、作業中の他の発見は台帳に 1 行起票するだけにして本 WP では直さない。

| # | 内容 |
|---|---|
| E1 | (6) の実行時設定の判定から role の `lock_timeout` を外す (`statement_timeout` と CONNECTION LIMIT は残す)。**条件 (裁定 (b))**: DDL を流す全経路 (E4 の新サブコマンド・`upgrade-applications`・`deprovision`) で `--lock-timeout` が既定値の無い必須引数であることを 1 つのテストで網羅的に固定する。**E1 と E4 は同じ変更セットで入れる**。**本番での帰結 (E-R14)**: E1 の後も本番の (6) は unknown のままである。`mitatedbsvc_auditreader` と application の runtime / developer role に `statement_timeout` を設定する経路が無いためである。また (6) の対象 role に DDL を流す provision role は含まれず、role の `lock_timeout` はもともと DDL の経路の歯止めではなかった (DDL の経路の歯止めは (b) の必須の `--lock-timeout` である)。(6) を confirmed にする作業は範囲 (a) の外であり、台帳の R-48 で扱う |
| E2 | (8) の「宣言との比較」と「余力の計算」を分ける (合計が上限より小さい入力は拒否。E-R4)。宣言 (`process_ceilings`) との食い違いは各 revision 単体の上限 (新 candidate の Data / Control の上限) で判定し、余力は traffic 移行中に同時に動きうる新旧 revision の合計で計算する。引数を分け、旧来の 1 つの引数 (`--data-process-count` / `--control-process-count`) で両方を兼ねる形は残さない |
| E3 | Control 未配備: 操作者が明示の引数で未配備を宣言したときだけ Control の process 数 0 を受け付ける (裁定 (c)。宣言表との扱いは E-R5)。この引数と Control の数の引数の同時指定は拒否する。どちらも無ければ従来どおり (読めない・不明は blocked / unknown のまま。未配備と読み替えない) |
| E4 | platform migration (`:app_id` を取らないもの) を適用する公開サブコマンド。DSN は環境変数だけ、`ON_ERROR_STOP=1`、既定値の無い必須の `--lock-timeout`、出力は伏字。適用対象は migration ディレクトリの既知のファイル名に限り (E-R2)、ファイルごとの psql 変数は静的な表と対応する引数で渡す (E-R1)。**(d) の範囲 (E-R18)**: WP-E・WP-D の作業では E4 を本番に対して実行しない。試験は使い捨ての PostgreSQL だけで行う。本番での適用は本書 §7 の後続 (isolated での証明 → 独立監査 → 本番更新) で、依頼者の承認の後にだけ行う |

**名前** (E-R9・E-R1・E-R10 で確定。`--api-role`・`--controlplane-role`、(8) の項目のキー `control_deployed` を含む): サブコマンド `apply-platform-migration`、引数 `--data-process-ceiling` / `--data-process-count-total` / `--control-process-ceiling` / `--control-process-count-total` / `--control-not-deployed`、新規テストファイル `MitateDB-api/tests/test_ops_apply_platform_migration.py`。以下の表はこの名前で書く。

**E1 の「DDL を流すサブコマンド」の範囲 (E-R3・E-R15)**: 依頼者裁定 (b) の 3 経路 (E4 のサブコマンド・`upgrade-applications`・`deprovision`) を「psql で migration ファイルを流すサブコマンド」と定義する。テストでは、この集合を、処理関数からモジュール内の呼出しを AST で静的にたどって (i) psql の subprocess の起動、(ii) `_migrations_dir()` または `platform_upgrades.discover_upgrade_scripts` の呼出し、のどちらかに到達するサブコマンドの和として導く。あわせて、psql を起動する全関数が `_with_lock_timeout_option` を通して `PGOPTIONS` を組むことを静的に assert する。`set-platform-timeouts` と `declare-*` は psycopg で設定の値を書く操作であり、migration ファイルを流さないので集合の外とする。これらはファイルに書かれた DDL を流さず、ツール自身が組んだ文 (`ALTER ROLE ... SET` 1 組、宣言の行の upsert) だけを実行するためである。

### 6A.4 変更クラス・契約版数・手順

- **Class D** (`security/CONTROL_MAPPING.md` に触れる。§2.3 の W-5 と同じ理由)。**契約版数は 1.8.0 のまま据え置く** (`spec/` に触れない)。
- 手順: 本 manifest の独立設計レビュー 1 回 (実装の前。監督が実施する。E-R7) → `implementer` (テンプレ 2) → `reviewer` (テンプレ 5、コードレビュー) → 監督の統合前ゲート → (WP-D の仕上げの後) `evidence-auditor` (テンプレ 6) を 1 回 (裁定 (e))。記録は WP ごとに 1 回。
- **記録 (E-R17)**: 統合時に監督が、設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` の D-1 の (6) (role 設定の `statement_timeout` / `lock_timeout` の有無を読む記述。E1 で覆る)・(8) (Z-27 の「process 数は新旧 revision の合計、宣言と食い違えば blocked」。E2 で覆る)、§7 の 33b、§12.3 の該当記述に打ち消し線と註 (覆した根拠と日付) を入れ、版数を上げる (§1.8 の 56)。実装担当は `docs/design/` に触れない。
- MitateDB-api のみの変更であり、`_ISOMORPHIC_TARGETS` に触れない想定である。触れる必要が出たら止まって監督へ上げる (着手時の手順 2)。

### 6A.5 基点と重なり

**基点**: 本書 v1.2 を含む main。WP-D の仕上げより前に着手し、WP-D は WP-E の統合後に基点を取り直す (§6.1 の訂正註 WPD-1)。

基点の記録欄 (監督が着手時に記入する。記入するまで着手しない):

| WP | 基点 main | 名前の再照合の結果 | `_ISOMORPHIC_TARGETS` の照合の結果 |
|---|---|---|---|
| WP-E | `ea316b1` | 全件実在 (§6A.7 の 1 の名前 17 件、欠落 0) | 本 WP で本体を変える関数は未登録 (`ops.py` の登録は `_upsert_declaration`・`_VERIFY_DECLARATIONS_*`・`_verify_declarations_*`・`cmd_verify_declarations`・`_redact_connection_values`・`_psql_connection_env` の 9 件で、いずれも呼ぶだけ) |

| 組 | 重なり (実ファイル名) | 扱い |
|---|---|---|
| WP-E と WP-D | `security/CONTROL_MAPPING.md` (`.claude/worktrees/r45-wpd` の未コミットの起草が変更している)。加えて WP-D の runbook は WP-E で変わる `inventory` の引数と E4 のサブコマンドを手順に書く | **直列。WP-D は WP-E の統合後** |
| WP-E と WP-A〜WP-C | なし (いずれも統合済み) | — |

### 6A.6 触るファイル・触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/ops.py` (`_inventory_ddl_lock_declaration`・`_inventory_connection_headroom`・`inventory` の引数定義 (E1〜E3)、E4 の新サブコマンドとその関数)、`MitateDB-api/tests/test_ops_inventory.py` (E1〜E3 に合わせた既存テストの更新と新規テスト)、`MitateDB-api/tests/test_ops_apply_platform_migration.py` (新規。E1 の網羅テストと E4)、`MitateDB-api/tests/test_platform_migration_reapply.py` (0005・0007・0011・0012 の「もう一度適用」の E4 経由への置き換え。E-R12)、`security/CONTROL_MAPPING.md` (英語。SI-08 は既存の (6)・(8) の主張と証拠のテスト名を置き換えで直すだけで追記しない — §4.1 の B-19、E-R6・E-R19。E4 と E1-4 の網羅の主張は SI-09)、`docs/code-history/MitateDB-api/` (`check_comment_provenance.py` の結果で登録の更新が要る場合だけ。新規のコメント・docstring に CH-ID は付けない。§3.1 の A-15、E-R20 の L5)、`tools/tests/test_no_shared_cluster_defaults.py` の件数 pin (実測で変わる場合だけ。§1.5 の 40b) | §2.2 の全 WP 共通、`r2db-api/` 全部、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS`)、`_ISOMORPHIC_TARGETS` 登録済みの helper の本体 (`_psql_connection_env`・`_redact_connection_values` ほか。呼ぶのはよい)、`_run_upgrade_script`・`_run_deprovision_script`・`_require_psql_16_or_newer`・`_with_lock_timeout_option`・`_validate_lock_timeout_value` の振る舞い (呼ぶのはよい)、`MitateDB-api/src/mitatedb_api/platform_declarations.py`・`platform_upgrades.py`・`config.py` (読むだけ)、`MitateDB-api/migrations/` (変異の一時編集を除く)、`MitateDB-api/docs/` (runbook は WP-D が扱う)、`MitateDB-api/tests/test_ops_verify_declarations.py`、`.github/` |

### 6A.7 着手時の手順

1. §2.1 と同じ要領で、本節が引く名前 (`_inventory_ddl_lock_declaration`・`_inventory_connection_headroom`・`_inventory_positive_int`・`cmd_inventory`・`_build_parser`・`cmd_upgrade_applications`・`cmd_deprovision`・`_run_upgrade_script`・`_run_deprovision_script`・`_psql_connection_env`・`_require_psql_16_or_newer`・`_with_lock_timeout_option`・`_validate_lock_timeout_value`・`_redact_connection_values`・`_migrations_dir`、`test_platform_migration_reapply.py` の `test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix`・`_REAPPLY_PLATFORM_MIGRATION_FILENAMES`) が基点に実在することを `grep` で再照合する。1 件でも無ければ止まって監督へ上げる。
2. `MitateDB-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` を読み、本 WP で本体を変える関数が 1 つも登録されていないことを確かめて報告する。登録済みの本体を変える必要が出たら止まって監督へ上げる (§1.5 の 37)。
3. E4 について実測して報告し、監督の裁定を得てから実装する: (i) E-R12 の集合 (0005・0007・0011・0012) の各ファイルが参照する `:変数` の集合 (E-R1 の表の元になる。`--` コメントと `::` キャストを除いて抽出する。E-R20 の L2)、(ii) 各ファイルを `MITATEDB_PROVISION_DSN` の role で使い捨てクラスタに適用できるか、(iii) E4-10・E4-12 で適用の直前にずらす対象 (各ファイルが作る ACL・関数本体・ロール設定・宣言の制約など。E-R13) のファイルごとの一覧。
4. E1 の網羅テストについて、§6A.3 の E-R15 の導き方 (AST で (i) psql の起動、(ii) `_migrations_dir()`・`discover_upgrade_scripts` の呼出しに到達するサブコマンドの和) で得た基点の集合と、psql を起動する関数の一覧を報告する。集合が `upgrade-applications`・`deprovision` 以外を含んだら止まって監督へ上げる。
5. E2 で引数名を変えることで直す既存テスト・`security/CONTROL_MAPPING.md` の行を列挙して報告する。
6. `security/CONTROL_MAPPING.md` の SI-08 の MitateDB ブロックのうち E1〜E3 で事実でなくなる (6)・(8) の行を列挙して報告する (E-R6)。置き換えで直した後のブロック長を実測し、15,200 を超えるならその時点で止まって監督へ上げる (E-R19)。
7. `tools/tests/test_no_shared_cluster_defaults.py` の件数 pin が新規テストファイルで変わるかを実測して報告する。

### 6A.8 実行するコマンド

実装担当は `MitateDB-api/tests` 全体・root suite・`conformance-tests`・`tools/dev/gate.py` を回さない (§2.2)。次だけを回す。

```bash
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_ops_inventory.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_ops_apply_platform_migration.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_platform_migration_reapply.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- tools/tests/test_no_shared_cluster_defaults.py -q
tools/dev/mutate.py "$SP/r45-wpe-mutations.json" -C "$WT" --wait 1800
python3 tools/public_value_scan.py MitateDB-api/src/mitatedb_api/ops.py MitateDB-api/tests/test_ops_inventory.py MitateDB-api/tests/test_ops_apply_platform_migration.py MitateDB-api/tests/test_platform_migration_reapply.py security/CONTROL_MAPPING.md
python3 tools/check_comment_provenance.py --base "<基点 main>" MitateDB-api/src/mitatedb_api/ops.py
python3 tools/check_comment_provenance.py --register
```

`test_platform_migration_reapply.py` は E-R12 の置き換えがあるので回す。変異定義は §2.7 の形で 1 変異 1 件、変異ごとに赤になる test id を名指しする。`security/CONTROL_MAPPING.md` の該当ブロックの文字数は scratchpad のスクリプトで測って報告する (§2.4)。E4 のテストの接続先は使い捨ての PostgreSQL (テスト基盤の管理 DSN) だけとする (裁定 (d))。

### 6A.9 完了条件 → 変異 → 赤になる test id

変異の `file` は、特記の無い行は `MitateDB-api/src/mitatedb_api/ops.py`。赤になるテストの名前は予想であり、実装担当が実名に置き換えて報告する。「inv」は `MitateDB-api/tests/test_ops_inventory.py`、「apm」は `MitateDB-api/tests/test_ops_apply_platform_migration.py`。

**E1 — (6) から role の `lock_timeout` を外す (E4 と同じ変更セット)**

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| E1-1 | 対象 role の全部に `statement_timeout` が (`setdatabase = 0` で) あり CONNECTION LIMIT が有効なら、`lock_timeout` が無くても (6) は confirmed | `_inventory_ddl_lock_declaration` の必須キーに `lock_timeout` を戻す | inv: role に `lock_timeout` が無くても confirmed になるテスト (既存の `test_inventory_ddl_lock_is_unknown_when_lock_timeout_not_declared` はこのテストに置き換える) |
| E1-2 | 対象 role のどれかに `statement_timeout` が無ければ (6) は unknown のまま | 必須キーから `statement_timeout` を外す | inv: `statement_timeout` 欠落で unknown のテスト |
| E1-3 | 対象 role のどれかの CONNECTION LIMIT が -1 または読めなければ (6) は unknown のまま | `_inventory_ddl_lock_declaration` の -1 の検査を外す | inv: `test_inventory_ddl_lock_minus_one_connection_limit_is_unknown` |
| E1-4 | `_build_parser()` のサブコマンドを列挙し、「psql で migration ファイルを流すサブコマンド」(E-R3) の集合と「`--lock-timeout` が既定値の無い必須引数であるサブコマンド」の集合が一致することを 1 つのテストで assert する。前者は手で列挙した定数でなく、AST で (i) psql の起動、(ii) `_migrations_dir()`・`discover_upgrade_scripts` の呼出しに到達するサブコマンドの和として導く (E-R15) | 5 件。(i) E4 のサブコマンドの `--lock-timeout` を必須でなくする。(ii) `upgrade-applications` の `--lock-timeout` に既定値を与え必須を外す。(iii) E4 の適用関数を呼ぶサブコマンドを `--lock-timeout` なしで 1 つ足す。(iv) DDL を流さないサブコマンド (例 `list-applications`) に必須の `--lock-timeout` を足す。(v) `_migrations_dir()` を呼ぶが psql を直接起動しないサブコマンドを `--lock-timeout` なしで 1 つ足す | apm: 集合の一致のテスト (5 件とも同じテスト) |
| E1-5 | 導いた集合が `upgrade-applications`・`deprovision`・E4 のサブコマンドの 3 つを含み、`set-platform-timeouts`・`declare-*` を含まない (空振り禁止、E-R3・E-R15) | 導く処理が間接呼出しをたどらない形にする (直接呼出しだけを見る) | apm: 導いた集合が 3 つを含み `set-platform-timeouts`・`declare-*` を含まないテスト |
| E1-7 | psql を起動する全関数 (`_run_upgrade_script`・`_run_deprovision_script`・E4 の適用関数) が `_with_lock_timeout_option` を通して `PGOPTIONS` を組む (AST の静的テスト。E-R15) | `_run_deprovision_script` から `_with_lock_timeout_option` の呼出しを外す | apm: psql を起動する全関数が `_with_lock_timeout_option` を通る静的テスト |
| E1-6 | E1 と E4 が同じ変更セット (同じ統合コミット) に入っている (裁定 (b)) | **監査照合**: 統合コミットの `git show --stat` の該当行 (E1 と E4 の変更ファイル) を逐語で設計に残す | — |

**E2 — (8) の宣言との比較と余力の計算を分ける**

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| E2-1 | `inventory` の (8) の process 数の引数は `--data-process-ceiling`・`--data-process-count-total`・`--control-process-ceiling`・`--control-process-count-total` だけで、いずれも正の整数 (B-7・B-10)。`--data-process-count`・`--control-process-count` は存在しない | `--data-process-count` を引数定義に戻す | inv: 引数の集合を pin するテスト |
| E2-2 | 宣言との比較は各 revision 単体の上限で行う: 上限 = 宣言、合計 > 宣言 のとき比較では blocked にしない | 宣言を合計と比べる形にする | inv: 合計が宣言を超えても上限が一致すれば比較で blocked にならないテスト |
| E2-3 | Data の上限と宣言の `data` が食い違えば blocked | Data の比較を外す | inv: Data の上限の食い違いのテスト |
| E2-4 | Control の上限と宣言の `control` が食い違えば blocked | Control の比較を外す | inv: Control の上限の食い違いのテスト |
| E2-5 | 条件 1 (role ごと) の需要は合計から計算する: 上限では収まり合計では CONNECTION LIMIT を超える場合 blocked | 条件 1 の需要を上限から計算する | inv: 条件 1 が合計で超えるテスト |
| E2-6 | 条件 2 (全体) の需要は合計から計算する: 上限では収まり合計では `max_connections` を超える場合 blocked | 条件 2 の需要を上限から計算する | inv: 条件 2 が合計で超えるテスト |
| E2-7 | 4 つの引数のどれかが無ければ (8) は unknown (E3 の未配備の宣言を除く)。欠けた値を他の引数で補わない | 合計が無いとき上限で補う | inv: 合計の欠落で unknown のテスト |
| E2-8 | 合計が単体の上限より小さい入力 (Data・Control のどちらでも) は矛盾として固定文言で拒否し、終了コード 1 (入力値を出さない。E-R4) | 2 件。(i) Data 側の検査を外す。(ii) Control 側の検査を外す | inv: Data の合計 < 上限の拒否のテスト、Control の合計 < 上限の拒否のテスト |
| E2-9 | `inventory` の入力の検証による拒否 (E2-8、E3-2・E3-3、argparse の使用法エラー。例: 0 や負の process 数) はすべて終了コード 1 で、判定の終了コード 2 と区別する (E-R20 の L1。この値に合わせて WP-B の既存の拒否のテストを更新する) | `inventory` の argparse の使用法エラーを既定の終了コード 2 に戻す | inv: `--concurrency 0` の拒否が終了コード 1 のテスト |

**E3 — Control 未配備の明示の宣言**

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| E3-1 | `--control-not-deployed` を指定し Control の数の引数を指定しないとき、Control の process 数と auditreader の接続を 0 として (8) の余力を計算する (Control の数の欠落を理由に unknown にしない。E-R5) | 未配備の宣言を無視して従来の欠落扱い (unknown) にする | inv: 未配備の宣言で (8) が計算されるテスト |
| E3-2 | `--control-not-deployed` と `--control-process-ceiling` の同時指定は固定文言で拒否し、終了コード 1 (DB に接続しない。E-R20 の L1) | 同時指定の拒否を外す (上限の側) | inv: 上限との同時指定の拒否のテスト |
| E3-3 | `--control-not-deployed` と `--control-process-count-total` の同時指定は固定文言で拒否し、終了コード 1 (DB に接続しない。E-R20 の L1) | 同時指定の拒否を外す (合計の側) | inv: 合計との同時指定の拒否のテスト |
| E3-4 | 未配備の宣言も Control の数も無ければ (8) は unknown のまま (不明を未配備と読み替えない) | Control の数が無いとき 0 で補う | inv: どちらも無いときの unknown のテスト |
| E3-5 | 未配備の宣言時は Control 側の宣言 (`process_ceilings` の `control`) との比較を行わない。宣言値は許される上限を表すので、未配備との食い違いにしない (E-R5) | 未配備の宣言時に Control の宣言を 0 と比べて blocked にする | inv: 未配備の宣言時に Control の宣言値があっても比較で blocked にならないテスト |
| E3-6 | 未配備の宣言時、Control が使う role (`_inventory_role_classes` が表への付与から見つけた controlplane と auditreader の role) を (8) の -1 の検査と余力の計算の対象から外す: これらの role が -1 でも (8) を unknown にしない。Control の role が 1 つも見つからなければ除外の対象が空になるだけで、そのことを理由に unknown にしない (E-R11、E-R20 の L7) | 2 件。(i) 未配備の宣言時も Control の role を (8) の -1 の検査に残す。(ii) 未配備の宣言時も Control の role が 0 件なら unknown にする | (i) inv: 未配備の宣言時に auditreader の role が -1 でも (8) が unknown にならないテスト、(ii) inv: 未配備の宣言時に Control の role が付与から見つからなくても unknown にならないテスト |
| E3-9 | 未配備の宣言時も (6) の実行時設定は、付与から見つけた Control の role が存在する限り従来どおり対象に含めて読む (E-R11) | `--control-not-deployed` のとき (6) の対象から Control の role を外す | inv: 未配備の宣言時に controlplane の role の -1 で (6) が unknown のテスト |
| E3-7 | 未配備の宣言時も Data の上限と宣言の比較 (E2-3) は行う | 未配備の宣言時に宣言との比較を丸ごと飛ばす | inv: 未配備の宣言時の Data の食い違いで blocked のテスト |
| E3-8 | (8) の項目は `control_deployed` を常に持つ: `--control-not-deployed` が無ければ `true`、あれば `false`。判定語は W-2 の語彙のまま。キー集合の pin (W2-1 の `test_inventory_top_level_and_item_keys_are_pinned`) をこのキーに合わせて更新する (E-R5・E-R10) | 4 件。(i) `control_deployed` を (8) の項目から落とす。(ii) 常に `true` を出す。(iii) 常に `false` を出す。(iv) 未配備の宣言時に語彙外の判定語を出す | (i) inv: `test_inventory_top_level_and_item_keys_are_pinned`、(ii) inv: 未配備の宣言時の `false` のテスト、(iii) inv: 宣言が無いときの `true` のテスト、(iv) inv: `test_inventory_judgment_vocabulary_is_closed` (`--control-not-deployed` の有無の両方で回す。E-R16) |

**E4 — platform migration の適用サブコマンド (WP-E・WP-D の作業では本番に対して実行しない。試験は使い捨ての PostgreSQL だけ。E-R18)**

E4 の拒否は ops の既存の `_die` の規約に従い、stderr に固定文言を出して終了コード 2 で終わる (E-R20 の L1。`--lock-timeout` の欠落は argparse の使用法エラーで同じく 2)。

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| E4-1 | 引数はファイル名に限り、既知の platform migration の名前の列挙 (モジュール定数) に一致し、`_migrations_dir()` (`MITATEDB_MIGRATIONS_DIR` を含む) のディレクトリとファイルの両方を resolve して比べ、ファイルがそのディレクトリの中にあるときだけ受け付ける。`MITATEDB_MIGRATIONS_DIR` は operator が設定する信頼境界であり、検査はそのディレクトリの外へ出ることを防ぐ (E-R20 の L3)。パス区切りを含む値・列挙に無い名前・per-application のファイル・ディレクトリの外に解決されるもの (例: 外を指す symlink) は、psql を起動せず `_die` の固定文言 (終了コード 2) で拒否する (入力値を出さない。E-R2) | 5 件。(i) 列挙の照合を外しディレクトリの任意のファイルを受け付ける。(ii) パス区切りの拒否を外す。(iii) 解決したパスがディレクトリの中にあることの検査を外す。(iv) 拒否文言に入力値を含める。(v) ファイルの側だけを resolve し、ディレクトリの側を resolve しない | (i) apm: 列挙に無い名前の拒否のテスト、(ii) apm: パス区切りの拒否のテスト、(iii) apm: 外を指す symlink の拒否のテスト、(iv) apm: 拒否文言に入力値が無いテスト (いずれも subprocess を spy し起動 0 件)、(v) apm: `MITATEDB_MIGRATIONS_DIR` 自体が symlink を経由するパスでも既知のファイルを受け付けるテスト |
| E4-2 | 受け付けるファイルの定数を `0005_application_audit.sql`・`0007_platform_declarations.sql`・`0011_process_ceilings.sql`・`0012_role_connection_limits.sql` に pin し、各ファイルが実在して psql 変数 `app_id` を参照しないこと、ディレクトリの `app_id` を参照しないファイルとの差がちょうど `0001_bootstrap_platform.sql`・`0002_registry_and_functions.sql` の 2 件であることを assert する (静的テスト。E-R12) | 2 件。(i) 定数に `0008_platform_upgrades_upgrade.sql` を足す。(ii) 定数に `0002_registry_and_functions.sql` を足す | apm: 定数の pin と差の静的テスト (2 件とも) |
| E4-3 | DSN は環境変数だけで受け取り、DSN を受け取る引数を持たない (静的テスト。設計 Z-8) | DSN を受け取る引数を足す | apm: 引数の静的テスト |
| E4-4 | psql の接続情報は `_psql_connection_env` で環境変数として渡し、argv に DSN の 4 要素の番兵が無い。親の環境に DSN が上書きしない接続設定変数があれば変数名だけの固定文言で拒否する (§3.1 の A-9・A-13) | 2 件。(i) argv に DSN を置く。(ii) `_psql_connection_env` を呼ばず親の環境をそのまま psql に渡す | (i) apm: argv に番兵が無いテスト (subprocess を spy)。(ii) apm: 親に `PGSSLMODE` を置いたときの拒否のテスト |
| E4-5 | psql を起動する前に `_require_psql_16_or_newer` を呼ぶ | その呼出しを外す | apm: psql 15 の版表示で拒否されるテスト |
| E4-6 | psql の argv に `ON_ERROR_STOP=1` を渡す (静的テスト) | argv から外す | apm: argv の `ON_ERROR_STOP` のテスト |
| E4-7 | `--lock-timeout` の値を `_validate_lock_timeout_value` で検証し、`_with_lock_timeout_option` で DSN の `options` に連結して `PGOPTIONS` で渡す (必須・既定値なしは E1-4) | 2 件。(i) `PGOPTIONS` に渡さない。(ii) 値の検証を外す | apm: `PGOPTIONS` のテスト、不正値の拒否のテスト |
| E4-8 | psql の出力と失敗時の文言は `_redact_connection_values` で伏せてから出す (設計 D-2 の 3 段の assert、番兵は 4 要素) | 伏せる呼出しを外す | apm: 伏字のテスト |
| E4-9 | psql が非 0 で終わればサブコマンドも非 0 で終わる。使い捨てクラスタで 0007 を欠いた 0011 の適用が非 0 になる | psql の終了コードを無視して 0 を返す | apm: 依存先の欠落で非 0 のテスト |
| E4-10 | 使い捨てクラスタで 0005 / 0007 / 0011 / 0012 のそれぞれについて、適用済みの状態から、そのファイルが作るオブジェクト (ACL・関数本体・ロール設定・宣言の制約など) を手でずらし、サブコマンド経由 (0007 は `--api-role`・`--controlplane-role` を付けて) で適用して終了コード 0 と元の状態に戻ったことを assert する。続けてもう一度適用し、終了コード 0、`updated_at` を除いて差分 0 (WP-C の比較の形。E-R13) | psql を起動せずに 0 を返す | apm: ずらした状態をサブコマンド経由の適用が戻すテスト |
| E4-13 | ファイルごとに必要な psql 変数を静的な表で持ち、対応する引数 (`--api-role`・`--controlplane-role`) で受け取って psql に `-v` で渡す。表にある変数の引数が欠ければ、表に無い引数を渡せば、いずれも psql を起動せず固定文言で拒否する。表と各ファイルが実際に参照する `:変数` の集合が一致する (静的テスト。E-R1)。`:変数` は `--` コメントを除き、`::` キャストを除いて抽出し、この抽出規則を合成の SQL 文字列で確かめる (E-R20 の L2)。拒否は `_die` の固定文言 (終了コード 2) | 5 件。(i) 欠けた引数の拒否を外す。(ii) 表に無い引数の拒否を外す。(iii) 表から 0007 の `controlplane_role` を外す。(iv) 抽出で `--` コメントを除かない。(v) 抽出で `::` キャストを除かない | (i) apm: 0007 に `--controlplane-role` が無いときの拒否のテスト、(ii) apm: 0011 に `--api-role` を渡したときの拒否のテスト、(iii) apm: 表とファイルの `:変数` の一致のテスト、(iv)(v) apm: コメント中の `:変数` とキャストを拾わない抽出規則のテスト (合成の SQL) |
| E4-11 | E4 の試験の接続先は使い捨ての PostgreSQL だけで、本番の接続先・runbook の実行手順を置かない (裁定 (d)) | **監査照合**: 新規テストファイルの接続先の出所 (テスト基盤の管理 DSN の環境変数名) の `file:line` と、`public_value_scan.py` の集計行を逐語で設計に残す | — |
| E4-12 | `test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix` のうち 0005・0007・0011・0012 の「もう一度適用」を E4 のサブコマンド経由 (`--lock-timeout` と 0007 の role の引数を付けて) に置き換える。起点までの過去の内容の適用は psql の直接実行のまま。E4 による適用の直前に、そのファイルが作るオブジェクトの状態を手でずらし、E4 の適用で元に戻ることを assert したうえで、WP-C の比較 (終了コード 0、`updated_at` を除く差分 0) を保つ。WP-C の証拠を弱めない。置き換えは本 WP の変更セットで行う (E-R12・E-R13) | E4-10 と同じ操作 (psql を起動せずに 0 を返す) を別の変異 id で定義する | `MitateDB-api/tests/test_platform_migration_reapply.py::test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix` |

**共通**

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| E-40b | 新規テストファイルで件数 pin の対象が増減したら、`tools/tests/test_no_shared_cluster_defaults.py` の pin を実測で同じ変更セットで更新する (§1.5 の 40b) | pin を基点の件数に戻す (増減が無い場合は **監査照合**: 実測のコマンドと件数を逐語で残す) | `tools/tests/test_no_shared_cluster_defaults.py::test_admin_dsn_env_definitions_are_pinned_to_25_files` (件数は基点の名前) |
| E-CM | 本 WP のテストと同じ変更セットで `security/CONTROL_MAPPING.md` (英語) を更新する: SI-08 の MitateDB ブロックは E1〜E3 で事実でなくなる (6)・(8) の既存の主張と証拠のテスト名を置き換えで直し (追記しない)、ブロック長を実測する (15,200 を超えるならその時点で止まって監督へ上げる)。E4 の統制と E1-4・E1-7 の網羅の主張は SI-09 の MitateDB ブロックに置く。Version 行の minor を main から 1 つ上げる (E-R6・E-R19) | **監査照合**: 置き換えた行と足した行、Version 行の前後、SI-08・SI-09 の MitateDB ブロックの文字数の実測を逐語で設計に残す | — |
| E-47 | 追加・変更したコード・テスト・fixture に実値が無い (C5) | **監査照合**: `public_value_scan.py` の集計行を逐語で残す | — |
| E-50 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す | — |

**件数 (下限)**: 完了条件 42 件 = 変異を持つ行 37 件 (E1-1〜E1-5、E1-7、E2-1〜E2-9、E3-1〜E3-9、E4-1〜E4-10、E4-12、E4-13、E-40b) + 監査照合 5 件 (E1-6・E4-11・E-CM・E-47・E-50)。変異は 57 件 (E1-4・E4-1・E4-13 の各 5 件、E3-8 の 4 件、E2-8・E3-6・E4-2・E4-4・E4-7 の各 2 件、他の 28 行の各 1 件。E-R20 の L4 で数え直した)。E-40b は件数 pin に増減が無ければ監査照合の行に変わる。

### 6A.10 監督の確認事項

なし (起草案の確認事項と設計レビューの指摘はすべて §6A.2 の E-R1〜E-R20 で決まった)。

### 6A.11 WP-E の訂正註と監督裁定 (2026-09-17、統合時に監督が追記。§6A の本文は書き換えない)

**訂正註 E-1 (変異の件数)**: §6A.9 の 57 件は **66 件**になった。manifest の 57 件に、差し戻しで足した 6 件 (E2 の需要の Control 軸・application role 軸・全体の 3 件、`-f` を渡す psql 起動関数を `_with_lock_timeout_option` なしで足す 1 件、`inventory` の未知の引数の分岐を外す 1 件、裸の psql 変数の検出を外す 1 件) と、E4-10 の 0007・0011・0012 を個別に壊す 3 件を足した。

**訂正註 E-2 (E3-9 の変異、E-S7)**: E3-9 の変異は「`--control-not-deployed` のとき (6) の対象から Control の role を外す」ではなく、「`--control-not-deployed` のとき (6) を読まずに confirmed を返す」とする。(6) の関数は `args` を受け取らず、flag が (6) に届きうる唯一の箇所が呼出し側であるため、これをこの性質を壊す最小の形として受容した。変異のためだけの引数を製品コードに足さない。

**訂正註 E-3 (E2-9 の範囲、E-S8)**: E2-9 の「すべて」には `inventory` に対する未知の引数・余分な位置引数を含める (終了コード 1、入力値を出さない)。他のサブコマンドは argparse 既定の終了コード 2 のまま変えない。

**訂正註 E-4 (E-40b、E-S11)**: `tools/tests/test_no_shared_cluster_defaults.py` の件数 pin は 25 → 26 に変わったので、E-40b は変異を持つ行のままとする (監査照合の行には変わらない)。

**訂正註 E-5 (psql 変数の引用、E-S9)**: `--api-role`・`--controlplane-role` の値の検証は足さない。代わりに、E4 が受け付ける 4 ファイルが psql 変数を引用付きの形だけで参照する (裸の `:name` が 0 件) ことを静的テストで固定する (変異 1 件を E-1 の 66 件に含む)。

**監督裁定 E-S1〜E-S11 (実装中。実装担当への裁定の本文。再実行の手順と報告の形の指示は省いた。逐語)**

- E-S1 (E-R1 の表) 0005→なし、0007→`api_role`・`controlplane_role`、0011→なし、0012→なし。
- E-S2 各ファイルを provision role で使い捨てクラスタに適用できることは、既存の `test_platform_migration_reapply.py` の適用を証拠として受理する。
- E-S3 ずらす対象: 0005 = application_audit の ACL、0007 = role 設定、0011 = CHECK 制約、0012 = 関数本体。
- E-S4 0005 の「戻り」は application_audit の relacl を読む assert で証明する。`_snapshot()` の既存の比較項目を 1 つも減らさない。
- E-S5 SI-08 は既存の行の中で置き換える。行を増やさない。
- E-S6 件数 pin は新規ファイルを intent-to-add にしてから実測し、25→26 を同じ変更セットで直す。
- E-S7 E3-9 の変異: (6) の関数は `args` を受け取らず、flag が (6) に届きうる唯一の箇所は呼出し側なので、「`--control-not-deployed` のとき (6) を読まずに confirmed を返す」変異を、この性質を壊す最小の形として受容する。変異のためだけの引数を製品コードに足さない。
- E-S8 E2-9 の「すべて」に `inventory` に対する未知の引数・余分な位置引数を含める (終了コード 1、入力値を出さない)。他のサブコマンドは変えない。
- E-S9 `--api-role`・`--controlplane-role` の値の検証は足さない (psql の `:"x"`・`:'x'` の補間が引用を担う)。代わりに、受け付ける 4 ファイルが psql 変数を引用付きの形だけで参照する (裸の `:name` が 0 件) ことを静的テストで固定する。
- E-S10 E1-5 の変異先は、テスト側の AST 走査 (間接呼出しをたどる処理) とする。
- E-S11 E-40b は件数 pin が変わったので変異のまま (監査照合にしない)。

**監査照合の逐語記録 (§6A.9 の 5 件。§1.5 の 40)**

- **E1-6** (E1 と E4 が同じ統合コミット): 統合コミット `6dea423` (main へのマージ `d13b2bb`) の `git show --stat`: `MitateDB-api/src/mitatedb_api/ops.py | 429`、`MitateDB-api/tests/test_ops_apply_platform_migration.py | 917`、`MitateDB-api/tests/test_ops_inventory.py | 616`、`MitateDB-api/tests/test_platform_migration_reapply.py | 74`、`security/CONTROL_MAPPING.md | 22`、`tools/tests/test_no_shared_cluster_defaults.py | 8` (E1 と E4 の変更は同じコミットに入っている)。集計行は `9 files changed, 1983 insertions(+), 160 deletions(-)`。上は E1・E4 に当たる該当行。ほかに `docs/` の 3 ファイル。
- **E4-11** (試験の接続先): 新規テストファイル `MitateDB-api/tests/test_ops_apply_platform_migration.py` の `ADMIN_DSN_ENV = "MITATEDB_TEST_ADMIN_DSN"` と、それだけを読む `_admin_dsn()` が接続先の出所である。本番の接続先・runbook の実行手順は置いていない。`python3 tools/public_value_scan.py` の集計行は `files_scanned=6 total_flagged=0`。
- **E-CM** (`security/CONTROL_MAPPING.md`): Version 行は 2.3 → 2.4。SI-08 の MitateDB ブロックは (6)・(8) の主張と証拠のテスト名の**置き換えのみ**で行数の増減 0、ブロック長 15,187 字 / 上限 15,200 (**残り 13 字。後続の WP-D・WP-F は SI-08 に文字を足せない**)。SI-09 の MitateDB ブロックは 6,867 字 (`apply-platform-migration` の統制と、DDL を流すサブコマンドの集合 = `--lock-timeout` 必須の集合の主張を追加)。最長行 1,384 字 / 上限 1,400。
- **E-47** (実値が無い): `python3 tools/public_value_scan.py` の集計行は `files_scanned=6 total_flagged=0`。
- **E-50** (対応の無い行が無い): §6A.9 の完了条件は 42 行 = 変異を持つ 37 行 (変異 66 件。訂正註 E-1) + 監査照合 5 行 (E1-6・E4-11・E-CM・E-47・E-50)。変異も監査照合も持たない行は 0。

### 6A.12 依頼者の回答 (2026-09-17、R-48・R-47・条件 (d))

> 依頼者の回答 (2026-09-17。Mitate の監督セッション「残件・予定リスト」が中継し、本チャットで依頼者が 3 件とも「はい」と確認した。逐語):
>
> 1. R-48 は R-45 の中で解消する。WP-E の次に WP-F を 1 本足す。(6) の要求は緩めず、auditreader と application ごとの runtime / developer role に statement_timeout を設定する経路を足す(既存の set-platform-timeouts の拡張を第一候補。別の形が良ければ枠決めで両論を示す)。条件は WP-E の (a)(d)(e) と同じ: 1 本・manifest 1 本・範囲はこの 1 件だけ、本番に実行しない、クラス D の独立設計レビュー・コードレビュー・監査は省かない。
> 2. R-47 は起票のまま。WP-E・WP-D(・WP-F)の受け入れ後に inventory で本番を読み、(3) が blocked なら R-47 を 1 本の WP として開く。該当の数と状態を見てから直し方を決める。
> 3. 条件 (d) は前監督の読みのとおり。恒久の禁止ではない。WP-E・WP-D の作業中は本番に実行しない。本番での適用は後続の手順で、依頼者の明示の承認の後だけ。

- 帰結 1 (回答 1): R-48 は本書の **WP-F** (WP-E の次の 1 本) で解消する。WP-F の枠決めは別途 §6B に置く。
- 帰結 2 (回答 2): R-47 は起票のままとし、本書では直さない。
- 帰結 3 (回答 3): §6A.2 の E-R18 の読みは確定である (条件 (d) は恒久の禁止ではない)。

## 6B. WP-F — auditreader と application role の `statement_timeout` を設定する platform migration と (6) の値の検査 (Class D)

### 6B.1 依頼者裁定 (逐語)

§6A.12 の依頼者の回答の 1 が本 WP の条件である (同節の逐語。ここに回答 1 の段落を再掲する):

> 1. R-48 は R-45 の中で解消する。WP-E の次に WP-F を 1 本足す。(6) の要求は緩めず、auditreader と application ごとの runtime / developer role に statement_timeout を設定する経路を足す(既存の set-platform-timeouts の拡張を第一候補。別の形が良ければ枠決めで両論を示す)。条件は WP-E の (a)(d)(e) と同じ: 1 本・manifest 1 本・範囲はこの 1 件だけ、本番に実行しない、クラス D の独立設計レビュー・コードレビュー・監査は省かない。

上の「別の形が良ければ枠決めで両論を示す」に対する枠決めの依頼者裁定 (2026-09-17、本チャット。逐語):

> 監督の提示 (要旨): WP-F の形は (A) platform migration 0013 (auditreader と既存の全 application の runtime / developer role に ALTER ROLE ... SET statement_timeout を掛け、begin_provision_application を置き換えて新規 role にも作成時に掛ける。適用は apply-platform-migration。set-platform-timeouts は触らない。値は manifest の着手時に実測して裁定)、(B) set-platform-timeouts の拡張、(C) 両方、のどれか。監督の推奨は (A)。
> 依頼者:「推奨は、将来においてベストなものですか」
> 監督の回答 (要旨): はい。正しさが運用の記憶に頼らない / 値の正本が 1 か所 / set-platform-timeouts の意味を壊さない。未確定は値そのもの (着手時に実測して裁定) と、(6) が設定の有無しか見ない点。
> 依頼者:「migration 0013 の形 で枠決め。
> (6) の値の検査の扱いはあなたはどう考えます？」
> 監督の回答 (要旨): WP-F に含めるべき。検査は「正の値であること」だけ (0013 の定数との一致は見ない)。値が 0 または解釈できないときは blocked、設定が無いときは従来どおり unknown。
> 依頼者:「はい」

### 6B.2 監督裁定 (F-R1〜F-R33、2026-09-17。F-R1〜F-R12 は依頼者裁定を受けた枠、F-R13〜F-R19 は起草時の疑義 1〜7、F-R20〜F-R33 は独立設計レビュー 1 回の指摘への裁定。逐語)

| 裁定 | 本文 (逐語) |
|---|---|
| F-R1 | (形) platform migration `MitateDB-api/migrations/0013_role_statement_timeouts.sql` を 1 本足す。`:app_id` を取らない。内容は (1) `mitatedbsvc_auditreader` に `ALTER ROLE ... SET statement_timeout`、(2) `applications` 表の既存の全 application の runtime / developer role に同じ設定 (0012 の CONNECTION LIMIT のループと同じ型)、(3) `begin_provision_application` を `CREATE OR REPLACE` し、role の新規作成の枝と既存 role の枝の両方で `ALTER ROLE ... SET statement_timeout` を掛ける。0012 の関数本体から変えるのはこの追加だけ (CONNECTION LIMIT ほかの振る舞いを変えない)。 |
| F-R2 | (対象外) api・controlplane role (0007 と `set-platform-timeouts` が扱う)、`idle_in_transaction_session_timeout`、`lock_timeout`、`set-platform-timeouts`・`declare-*`・`verify-declarations` の振る舞い、r2db-api。値を後から変える ops の道具は足さない (値の正本は migration。変えるときは新しい migration)。 |
| F-R3 | (値) 値は着手時の実測の後に監督が裁定する。実測するもの: 対象 role (auditreader、runtime、developer) の接続で、アプリケーションが `SET LOCAL statement_timeout` を掛けずに実行する文 (`backend_postgres.py` の `deadline is None` の経路、auditreader の監査クエリ、pool の接続確立時の文、developer role の DDL の経路) の一覧と、それぞれに既存の上限があるか。候補値と根拠を報告する。裁定までは定数を仮置きし、裁定後に 1 か所 (migration) だけを直す形にする。 |
| F-R4 | (再実行性) 0013 は何度適用しても同じ状態になる。`apply-platform-migration` が受け付ける名前の定数 (WP-E の E4-2 の pin、psql 変数の表) に 0013 を足し、`test_platform_migration_reapply.py` の再適用と「手でずらして戻る」の対象に 0013 を足す (ずらす対象: auditreader の設定を外す、既存 application の role の設定を外す、関数本体)。WP-C・WP-E の証拠を弱めない。 |
| F-R5 | ((6) の値の検査) `_inventory_ddl_lock_declaration` は、対象 role の `statement_timeout` の設定値を既存の `pg_timeouts` の正規化で解釈し、正の値のときだけ条件を満たすとする。値が 0 (無制限) または解釈できないときは **blocked**、設定が無いときは従来どおり **unknown**。0013 の定数との一致は見ない。blocked と unknown が混在するときの優先は既存の判定の規約 (`_inventory_exit_code` ほか) を読んで manifest に書き、疑義があれば報告で上げる。出力に設定値そのものは出さない (判定語だけ。既存のキー集合の pin を変えない方向で。変える必要があれば報告で上げる)。 |
| F-R6 | (migration の追加の波及) 新しい migration 番号の追加は、migration を列挙する全箇所に波及する。着手時に `git grep -l 0012_role_connection_limits` (基点で 18 ファイル、44 箇所) を実測し、0013 を足す箇所・足さない箇所を file:line で列挙して報告し、監督の裁定の後に実装する。`MitateDB-api/conformance/` と tests の bootstrap helper のうち `_ISOMORPHIC_TARGETS` 登録済みの本体に触る必要が出たら止まって上げる。`conformance-tests/`・`spec/` には触れない。`tools/control_mapping_axes.tsv` と `MitateDB-api/docs/` (runbook) の扱い: runbook は WP-D が扱うので触らない (WP-D の訂正註に「0013 の適用手順を足す」を 1 行足す — §6.1 に WPD-n として)。 |
| F-R7 | (権限) 0013 を provision role (`MITATEDB_PROVISION_DSN` 相当) で使い捨てクラスタに適用できることを、着手時に実測する (PostgreSQL 16 の CREATEROLE と ADMIN OPTION。auditreader は 0005 が、application role は `begin_provision_application` が作る)。できない場合は止まって上げる。 |
| F-R8 | (upgrade との関係) 0013 は platform migration であり per-application upgrade (`*_upgrade.sql`、台帳) ではない。`inventory` の (3) の「未適用の platform migration」の検出が 0013 を数えるか、`platform_declarations.MIGRATION_NUMBER` などの定数に波及があるかは F-R6 の実測に含める。 |
| F-R9 | (CONTROL_MAPPING) 英語。SI-08 の MitateDB ブロックは 15,187 / 15,200 字で **文字を足せない**。(6) の既存の主張が F-R5 で変わる部分は同じ行の中の置き換えで直し、置き換え後の長さを実測する (超えるなら止まって上げる)。0013 の新しい統制 (role は作成時に statement_timeout を持つ、既存にも掛ける) は SI-09 か、内容に合う別の SI の MitateDB ブロックに置き、どこに置くかを着手時に提案して監督が裁定する。Version の minor を +1。 |
| F-R10 | (条件) 依頼者の条件 (a)(d)(e): WP-F は 1 本・manifest 1 本・範囲はこの 1 件 (0013 と (6) の値の検査) だけ。他の発見は台帳 1 行。0013 と `apply-platform-migration` を本番に対して実行しない。試験は使い捨ての PostgreSQL だけ。Class D の独立設計レビュー (manifest に 1 回、実装の前)・コードレビュー・受け入れ監査は省かない。記録は WP ごとに 1 回。 |
| F-R11 | (コメントの規律) 新規のコメント・docstring・SQL のコメントに CH-ID・WP 名・裁定番号・manifest の番号・差し戻しの番号・経緯語を書かない (英語、現在形の事実だけ)。変異を成立させるためだけのコードを製品コードに足さない (変異は「足す」形でも書ける)。 |
| F-R12 | (契約とクラス) `spec/` に触れない。契約版数 1.8.0 据え置き。Class D (`security/CONTROL_MAPPING.md`)。 |
| F-R13 | (疑義 1) (6) の blocked は既存の規約に合わせて `reason` を持つ。`_INVENTORY_REASONS` に固定語 `statement-timeout-unbounded` を 1 つ足し (語彙の pin を更新)、(6) の項目のキーの形は既存の blocked の項目と同じにする (blocked のときだけ `reason` を持つのか常に持つのかは、(2)・(3) の既存の形に合わせる。着手時に実測して報告)。キー集合の pin はこれに合わせて更新する。F-R5 の「pin を変えない方向」はこの点で上書きする。設定値そのものは出さない。 |
| F-R14 | (疑義 2) 「値が 0」は使い捨てクラスタの実 role で観測する。「解釈できない値」は PostgreSQL が `ALTER ROLE ... SET` の時点で拒否して作れない場合に限り、設定を読む関数 (`platform_declarations._role_setting_rows`) をテストで差し替えて観測してよい。作れるかどうかを着手時に実測して報告する。 |
| F-R15 | (疑義 3) (6) の blocked の `remediation_required` は False のまま。 |
| F-R16 | (疑義 4) テストは新規ファイルを作らず既存の 3 ファイルに足す (起草の提案どおり)。件数 pin は変わらない見込みなので F-40b は監査照合とし、実測のコマンドと件数を残す。 |
| F-R17 | (疑義 5) F-R3 (値) と F-R6 (波及) は着手時の 1 回の報告にまとめ、監督が同時に裁定する。報告には、候補値のもとで `MitateDB-api/tests` 全体が緑になるかの見込み (期限なしで走る文のうち候補値を超えうるもの) を含める。 |
| F-R18 | (疑義 6) 0013 は 0005 が作る role を 0005 と同じ literal で名指す (形を変えない)。付与から見つかる auditreader が literal と違う環境では、その role は 0013 の対象にならず (6) が unknown / blocked として見える — これを §6B.3 に 1 文で書く。 |
| F-R19 | (疑義 7) migration の番号は peer 間で対応させる対象ではない (MitateDB の 0012 と r2db-api の 0013 が既に同じ内容で番号が違う)。非対称は統合時に監督が設計メモの実施記録に 1 行で記録する。`security/CONTROL_MAPPING.md` には書かない。 |
| F-R20 | (高1) テストの既定の bootstrap は本番と同じく 0013 まで適用する (F-R6 の原則)。0013 より前の状態や「設定の無い role」に依存するテスト (`test_ops_inventory.py` の `..._is_unknown_when_statement_timeout_not_declared`・`..._target_roles_include_auditreader`・終了コード 2 の 2 件ほか) は、その状態をテストの中で明示的に作る (0012 までで止める bootstrap の引数、または対象 role の `ALTER ROLE ... RESET statement_timeout`)。どちらを使うかは実装担当がテストごとに選び報告する。F2-9 は「0012 までの platform で (6) が unknown → `apply-platform-migration` で 0013 を適用 → confirmed」を 1 つのテストで観測する。F-C1 の変異は「既定の bootstrap の列から 0013 を外す」で、赤になるのは「既定の platform で (6) が confirmed」のテストとする。F2-4・F2-5・F2-8 の「赤になる test id」をこの形に合わせて直す。 |
| F-R21 | (高2) migration を列挙する各箇所では、0012 を足したときの位置の前例に従う。`MitateDB-api/tests/test_ops_verify_declarations.py` の `MIGRATION_NAMES` は末尾 2 件を slice で落とす定数 (`_ISOMORPHIC_TARGETS` 登録済み) に効くので、0013 は 0012 の直後 (0007 の前) に置き、slice が落とす 2 件が変わらないことを assert で確かめて報告する。登録済みの定数・helper の式は変えない。 |
| F-R22 | (高3) 0012 と 0013 は同じ関数を `CREATE OR REPLACE` するので、0013 の後に 0012 だけを再適用すると新規 role への設定が消える。扱い: (i) 0013 のヘッダのコメントに順序の依存を現在形で書く。(ii) WPD-4 を広げる: runbook は platform migration を常に番号順に一式 (0005・0007・0011・0012・0013) で適用し、1 本だけを順序を外して適用しないと書く。(iii) 完了条件を 1 件足す: 0013 → 0012 → 0013 の順で適用した後に provision した application の両 role に設定が付く。変異: 0013 の関数の置き換えを外す。(iv) §6B.3 に 1 文: 順序を外した場合の補償は、次の `inventory` で新規 application の (6) が unknown になることだけである。 |
| F-R23 | (中4) SI-08 の (6) の主張は同じ行の中の最小の置き換えで直す。上限を超える場合は、WP-B・WP-E が書いた SI-08 の MitateDB の行の言い回しを詰めて収める (主張と証拠のテスト名を 1 つも落とさない。§4.1 の B-17・B-18 の前例)。それでも超えるなら止まって上げる。文字数は `conformance-tests/test_control_mapping_register.py` と同じ分解 (claims を単一空白で join) で測る — 素朴な計測は 147 字ずれる。 |
| F-R24 | (中5) F-CM に SI-09 の MitateDB ブロックの実測更新を足す: テスト件数、受け付けるファイルの数 (4→5)、再適用テストの名前。既存のテスト `test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix` は改名しない (docstring に対象ファイルを書く)。 |
| F-R25 | (中6) 既存の早期 return は変えない: CONNECTION LIMIT が -1 / 読めない role があれば、値を判定する前に unknown。`psycopg.Error` も unknown。「blocked が unknown より強い」は statement_timeout の値の判定どうしの間だけに当てはまる、と §6B.3 に書く。F2-6 に「CONNECTION LIMIT -1 の role と値 0 の role の混在は unknown」を足し、変異 (早期 return を値の判定の後ろへ動かす) を対応させる。どちらも終了コードは 2。 |
| F-R26 | (中7) 負の値も blocked。F2-2 に負値を足し、変異を「`> 0` を `!= 0` にする」にする。負値を実 role に設定できない場合の観測は F-R14 の差し替えでよい。 |
| F-R27 | (中8 前半) F-R7 の実測に「auditreader を provision role 以外 (使い捨てクラスタの管理 role) が先に作った状態で、provision role が 0013 を適用できるか」を足す。0013 は 1 つのトランザクションで走り、途中で失敗したら何も残らないことを完了条件にする (変異: トランザクションの囲みを外す、または観測できる形で)。適用できない場合の運用上の扱いは、実測の報告の後に監督が裁定する (F-R17 と同じ報告に含める)。 |
| F-R28 | (中8 後半) 0013 の既存 application のループは、`pg_roles` に無い role 名の行を飛ばす (deprovision の途中で落ちた行で migration 全体が落ちないように)。完了条件と変異を 1 件足す。飛ばした行は (6) の側で confirmed にならないことも同じテストで観測する。 |
| F-R29 | (中9) F-R3 の実測項目に足す: (a) role の既定値と `SET LOCAL` の優先関係 (要求の経路は `SET LOCAL` が上書きする)、(b) 接続の `options` / `PGOPTIONS` で statement_timeout を渡す経路が無いこと、(c) 起動時の application ごとの台帳の読みと `main.build_app` の eager なループ、`deadline` が None の DDL の経路、(d) conformance の bootstrap (レビューが挙げた 5 箇所) に 0013 を足すと suite 全体が role の既定値の下で走ること。実装担当は conformance を回さない — conformance を含む root suite は監督の完了ゲートが証拠になる。報告には緑の見込みだけを書く。 |
| F-R30 | (佐10) E1-6 の記入に、集計行 `9 files changed, 1983 insertions(+), 160 deletions(-)` と「上は E1・E4 に当たる該当行。ほかに `docs/` の 3 ファイル」を添える。 |
| F-R31 | (佐11) `_PLATFORM_MIGRATION_VARIABLE_TABLE` のキー集合が `_PLATFORM_MIGRATION_FILENAMES` と一致する静的テストを完了条件に 1 件足す (変異: 表から 0013 のキーを外す)。 |
| F-R32 | (佐12) 0013 の末尾に 0012 と同じ `REVOKE ALL ON FUNCTION ... FROM PUBLIC` を置き、関数の ACL が 0012 の適用後と同じであることを F1 の完了条件に含める。 |
| F-R33 | (佐13・14) `MitateDB-api/tests` 全体は `tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests -q -n 5 --dist loadgroup` で 1 回 (Bash timeout 600000。超える場合はディレクトリを 2 分割)。`tools/control_mapping_axes.tsv` は一回限りの入力で live な検査が無いので触らない、と §6B.6 に書く。 |

### 6B.3 目的と範囲

**目的**: 台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-48** (auditreader と application ごとの runtime / developer role に `statement_timeout` を設定する経路が無い) を解消し、あわせて (6) の実行時設定の判定を「設定の有無」から「値が正であること」に進める。範囲は次の F1・F2 (0013 と (6) の値の検査の 1 件) だけとし (依頼者の条件 (a)、F-R10)、作業中の他の発見は台帳に 1 行起票するだけにして本 WP では直さない。

| # | 内容 |
|---|---|
| F1 | platform migration `MitateDB-api/migrations/0013_role_statement_timeouts.sql` を 1 本足す (F-R1)。(1) `mitatedbsvc_auditreader` に `ALTER ROLE ... SET statement_timeout`、(2) `mitatedb_registry.applications` の既存の全 application の runtime / developer role に同じ設定 (`0012_role_connection_limits.sql` の第 2 節の CONNECTION LIMIT のループと同じ型。`runtime_role`・`developer_role` が NULL でない行だけを対象にする同じ絞りを含む)、(3) `begin_provision_application` の `CREATE OR REPLACE` で、role の新規作成の枝と既存 role の枝 (`duplicate_object` の fallback) の両方に同じ設定を足す。0012 の関数本体から変えるのはこの追加だけ。`:app_id` を取らず psql 変数を 1 つも参照しない。適用は WP-E の `apply-platform-migration` (F-R4) |
| F2 | (6) の実行時設定の半分 (`_inventory_ddl_lock_declaration`) が、対象 role の `statement_timeout` の設定値を既存の正規化 (`mitatedb_api.pg_timeouts.ms_from_pg_timeout_text`) で解釈し、**正の値のときだけ**条件を満たすとする (F-R5)。正でない値 (0 = 無制限、および負の値。F-R26) と解釈できない値は blocked、設定が無いときは従来どおり unknown。0013 の定数との一致は見ない。blocked のときは既存の blocked の項目と同じ形で `reason` に固定語 `statement-timeout-unbounded` を持ち (F-R13)、`remediation_required` は False のままとする (F-R15)。対象 role の集合 (`_inventory_role_classes` が表への付与から見つける api / control / auditreader の role と、provision 済みの全 application の runtime / developer role) と CONNECTION LIMIT の判定は変えない |

**名前** (F-R1 で確定。着手時に再照合する): migration `0013_role_statement_timeouts.sql`。**テストの置き場**は既存の 3 ファイル (`MitateDB-api/tests/test_ops_apply_platform_migration.py`・`MitateDB-api/tests/test_platform_migration_reapply.py`・`MitateDB-api/tests/test_ops_inventory.py`) に足す (F-R16 で確定。新規テストファイルを作らない)。以下の表はこの置き場で書く。

**blocked と unknown の混在の優先 (F-R5 の指示に対する既存の規約の読み)**: 既存の (3) の判定は、role / application をまたぐ判定を 1 つにまとめるとき `blocked` を上書きしない形 (`if judgment != "blocked": judgment = "unknown"`) を採っており、**blocked が unknown より強い**。(6) も同じ規約に従い、対象 role のどれかが blocked なら項目全体を blocked、blocked が無く unknown があれば unknown とする。終了コードは `_inventory_exit_code` の規約のまま (confirmed 以外はすべて 2。1 は項目の判定が 1 つも無いまま失敗したときだけ) で、blocked と unknown を終了コードで区別しない。**この「blocked が unknown より強い」は `statement_timeout` の値の判定どうしの間だけに当てはまる (F-R25)。** 既存の早期 return は変えない: CONNECTION LIMIT が -1 または読めない role があれば値を判定する前に unknown、`psycopg.Error` も unknown である。

**0013 が名指す role と (6) が role を見つける方法の差 (F-R18)**: 0013 は 0005 が作る role を 0005 と同じ literal (`mitatedbsvc_auditreader`) で名指すので、付与から見つかる auditreader がこの literal と違う環境では、その role は 0013 の対象にならず (6) が unknown / blocked として見える。

**適用の順序 (F-R22)**: 0012 と 0013 は同じ関数を `CREATE OR REPLACE` するので、0013 の後に 0012 だけを再適用すると新規 role への設定が消える。順序を外した場合の補償は、次の `inventory` で新規 application の (6) が unknown になることだけである。

**対象外** (F-R2): api・controlplane role の設定 (0007 と `set-platform-timeouts` が扱う)、`idle_in_transaction_session_timeout`、`lock_timeout`、`set-platform-timeouts`・`declare-*`・`verify-declarations` の振る舞い、r2db-api、値を後から変える ops の道具 (値の正本は migration。変えるときは新しい migration)、(8) の余力の計算。

### 6B.4 変更クラス・契約版数・手順

- **Class D** (`security/CONTROL_MAPPING.md` に触れる。§2.3 の W-5 と同じ理由、F-R12)。**契約版数は 1.8.0 のまま据え置く** (`spec/` に触れない)。
- 手順: 本 manifest の独立設計レビュー 1 回 (実装の前。監督が実施する。**実施済み (2026-09-17)。指摘は F-R20〜F-R33 で反映**) → `implementer` (テンプレ 2) → `reviewer` (テンプレ 5、コードレビュー) → 監督の統合前ゲート → `evidence-auditor` (テンプレ 6) を 1 回 (F-R10、依頼者の条件 (e))。記録は WP ごとに 1 回。
- **記録 (統合時に監督が行う)**: 設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` に §12.5 を足し、D-1 の (6) の「role 設定の `statement_timeout` の有無を読む」記述を F2 が覆した根拠と日付で訂正して版数を上げる (§1.8 の 56。行を消さない)。`docs/design/ROADMAP_POST_PHASE7_V1.md` の R-48 の行に解消を追記する。実装担当は `docs/design/` に触れない。
- MitateDB-api のみの変更であり、`_ISOMORPHIC_TARGETS` に触れない想定である。触れる必要が出たら止まって監督へ上げる (§6B.7 の 2、F-R6)。

### 6B.5 基点と重なり

**基点**: 本書 v1.4 を含む main (WP-E の統合後)。

基点の記録欄 (監督が着手時に記入する。記入するまで着手しない):

| WP | 基点 main | 名前の再照合の結果 | `_ISOMORPHIC_TARGETS` の照合の結果 |
|---|---|---|---|
| WP-F | `80d1495` (2026-09-17、worktree `r45-wpf`) | §6B.7 の 1 の全名が基点に実在 (監督が grep で照合、欠落 0)。`git grep 0012_role_connection_limits` は 18 ファイル・48 箇所 (manifest 起草時の 44 箇所との差は、その後に main へ入った文書の分。`docs/` を除くと 16 ファイル・39 箇所) | 本 WP が本体を変える関数・定数は 1 つも登録されていない。関係する登録は `tests/test_ops_verify_declarations.py` の `MIGRATION_NAMES_WITHOUT_DECLARATIONS` だけで、式は変えない (F-R21) |

| 組 | 重なり (実ファイル名) | 扱い |
|---|---|---|
| WP-F と WP-D | `security/CONTROL_MAPPING.md`。加えて WP-D の runbook は 0013 の適用手順を書く | **直列。WP-F → WP-D** (WP-D は WP-F の統合後に基点を取り直す。§6.1 の訂正註 WPD-4) |
| WP-F と WP-A〜WP-C・WP-E | なし (いずれも統合済み) | — |

並行して動かす WP は無い (§1.2 の 16・17 の照合の対象になる組は WP-D だけで、その組は重なりが 0 でないので直列にする)。

### 6B.6 触るファイル・触らないファイル

| 触るファイル | 触らないファイル |
|---|---|
| `MitateDB-api/migrations/0013_role_statement_timeouts.sql` (新規。F1)、`MitateDB-api/src/mitatedb_api/ops.py` (`_inventory_ddl_lock_declaration` の値の解釈 (F2)、`_INVENTORY_REASONS` への固定語 `statement-timeout-unbounded` の追加 (F-R13)、そして`_PLATFORM_MIGRATION_FILENAMES`・`_PLATFORM_MIGRATION_VARIABLE_TABLE` への 0013 の追加 (F-R4))、`MitateDB-api/tests/test_ops_inventory.py`、`MitateDB-api/tests/test_ops_apply_platform_migration.py`、`MitateDB-api/tests/test_platform_migration_reapply.py`、migration を列挙する箇所のうち F-R6 の裁定で 0013 を足すもの (位置は 0012 の直後。F-R21。着手時の実測と監督の裁定で確定し、訂正註で本表に足す)、`security/CONTROL_MAPPING.md` (英語。SI-08 は置き換えのみで文字を足さない。0013 の統制の置き場は F-R9 の裁定)、`docs/code-history/MitateDB-api/` (`check_comment_provenance.py` の結果で登録の更新が要る場合だけ。新規のコメント・docstring に CH-ID は付けない。F-R11)、`tools/tests/test_no_shared_cluster_defaults.py` の件数 pin (F-R16: 変わらない見込み。実測で変わったら止まって監督へ上げる。§1.5 の 40b) | §2.2 の全 WP 共通、`r2db-api/` 全部、`MitateDB-api/migrations/` の既存の 12 本 (変異の一時編集を除く)、両 peer の `tests/test_audit_query.py` (`_ISOMORPHIC_TARGETS`)、`_ISOMORPHIC_TARGETS` 登録済みの本体 (`MitateDB-api/conformance/` と tests の bootstrap helper を含む。呼ぶのはよい。触る必要が出たら止まって上げる)、`cmd_set_platform_timeouts`・`cmd_declare_*`・`cmd_verify_declarations`・`_inventory_connection_headroom` ((8)) の振る舞い (読む・呼ぶのはよい)、`MitateDB-api/src/mitatedb_api/pg_timeouts.py`・`platform_declarations.py`・`platform_upgrades.py`・`backend_postgres.py` (読むだけ)、`MitateDB-api/docs/` (runbook は WP-D が扱う)、`tools/control_mapping_axes.tsv` (一回限りの入力で live な検査が無い。F-R33)、`.github/` |

### 6B.7 着手時の手順

1. §2.1 と同じ要領で、本節が引く名前が基点に実在することを `grep` で再照合する: `_inventory_ddl_lock_declaration`・`_inventory_role_classes`・`_inventory_exit_code`・`_INVENTORY_JUDGMENTS`・`_INVENTORY_REASONS`・`_PLATFORM_MIGRATION_FILENAMES`・`_PLATFORM_MIGRATION_VARIABLE_TABLE`・`cmd_apply_platform_migration`・`_migrations_dir`、`platform_declarations._role_setting_rows`・`platform_declarations.MIGRATION_NUMBER`・`pg_timeouts.ms_from_pg_timeout_text`、`mitatedb_registry.begin_provision_application`、`MitateDB-api/tests/test_ops_inventory.py` の `test_inventory_ddl_lock_is_confirmed_when_role_settings_are_declared`・`test_inventory_ddl_lock_is_unknown_when_statement_timeout_not_declared`・`test_inventory_ddl_lock_is_confirmed_without_lock_timeout_declared`・`test_inventory_ddl_lock_target_roles_include_auditreader`・`test_inventory_ddl_lock_target_roles_include_application_roles`・`test_inventory_ddl_lock_ignores_a_per_database_scoped_setting`・`test_inventory_ddl_lock_minus_one_connection_limit_is_unknown`・`test_inventory_top_level_and_item_keys_are_pinned`・`test_inventory_judgment_vocabulary_is_closed`・`test_inventory_reason_vocabulary_is_pinned`・`test_inventory_exit_code_is_2_when_any_item_is_not_confirmed`・`_bootstrap`、`MitateDB-api/tests/test_ops_apply_platform_migration.py` の `test_apply_platform_migration_accepted_filenames_are_pinned_and_exist_without_app_id`・`test_apply_platform_migration_variable_table_matches_each_files_own_references`・`test_apply_platform_migration_variables_are_referenced_only_in_quoted_form`・`test_apply_platform_migration_0012_restores_a_manually_drifted_function_body`、`MitateDB-api/tests/test_platform_migration_reapply.py` の `_REAPPLY_PLATFORM_MIGRATION_FILENAMES`・`_REAPPLY_MIGRATION_SEQUENCE`・`_drift_platform_objects_before_reapplication`・`test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix`・`test_reapply_starting_points_cover_every_migration_file_as_a_contiguous_prefix`・`test_excluded_starting_points_are_pinned`・`test_platform_migrations_declare_on_error_stop_in_the_file`、`tools/tests/test_no_shared_cluster_defaults.py` の `test_admin_dsn_env_definitions_are_pinned_to_26_files`。1 件でも無ければ止まって監督へ上げる。
2. `MitateDB-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` を読み、本 WP で本体を変える関数・定数が 1 つも登録されていないことを確かめて報告する。登録済みの本体を変える必要が出たら止まって監督へ上げる (§1.5 の 37、F-R6)。
3. **F-R3 の実測 (値)**: 対象 role (auditreader、application の runtime、developer) の接続で `SET LOCAL statement_timeout` を掛けずに実行する文の一覧 (`backend_postgres.py` の `deadline is None` の経路、auditreader の監査クエリ、pool の接続確立時の文、developer role の DDL の経路) と、それぞれに既存の上限があるかを実測し、候補値と根拠を報告する。さらに次を実測する (F-R29): (a) role の既定値と `SET LOCAL` の優先関係 (要求の経路は `SET LOCAL` が上書きする)、(b) 接続の `options` / `PGOPTIONS` で `statement_timeout` を渡す経路が無いこと、(c) 起動時の application ごとの台帳の読みと `main.build_app` の eager なループ、`deadline` が None の DDL の経路、(d) conformance の bootstrap (レビューが挙げた 5 箇所) に 0013 を足すと suite 全体が role の既定値の下で走ること。実装担当は conformance を回さない (conformance を含む root suite は監督の完了ゲートが証拠になる) ので、報告には緑の見込みだけを書く。報告には、候補値のもとで `MitateDB-api/tests` 全体が緑になるかの見込み (期限なしで走る文のうち候補値を超えうるもの) を含める (F-R17)。**この実測は次の 4 (F-R6) と 1 回の報告にまとめ、監督が同時に裁定する (F-R17)。** 裁定までは 0013 の中で定数を仮置きし、裁定後に migration の 1 か所だけを直す。
4. **F-R6 の実測 (波及)**: `git grep -l 0012_role_connection_limits` (基点で 18 ファイル・44 箇所) を実測し、0013 を足す箇所・足さない箇所を `file:line` で列挙して報告する。`tools/control_mapping_axes.tsv` の扱いも報告に含める (F-R33 で触らないと決まっている)。0013 を足す位置は 0012 を足したときの前例に従い、0012 の直後とする。`MitateDB-api/tests/test_ops_verify_declarations.py` の `MIGRATION_NAMES` は末尾 2 件を slice で落とす定数 (`_ISOMORPHIC_TARGETS` 登録済み) に効くので、0013 は 0012 の直後 (0007 の前) に置き、`MIGRATION_NAMES_WITHOUT_DECLARATIONS` の slice が落とす 2 件が `{0007, 0011}` のままであることを assert で確かめて報告する。登録済みの定数・helper の式は変えない (F-R21)。**上の 3 (F-R3) と 1 回の報告にまとめ、監督の同時の裁定の後に実装する (F-R17)。** `MitateDB-api/conformance/` と tests の bootstrap helper のうち `_ISOMORPHIC_TARGETS` 登録済みの本体に触る必要が出たら止まって上げる。`conformance-tests/`・`spec/` には触れない。runbook は WP-D が扱うので触らない。
5. **F-R7 の実測 (権限)**: 0013 を provision role (`MITATEDB_PROVISION_DSN` 相当) で使い捨てクラスタに適用できることを実測して報告する (PostgreSQL 16 の CREATEROLE と ADMIN OPTION。auditreader は 0005 が、application role は `begin_provision_application` が作る)。あわせて「auditreader を provision role 以外 (使い捨てクラスタの管理 role) が先に作った状態で、provision role が 0013 を適用できるか」を実測する (F-R27)。できない場合は止まって上げる。適用できない場合の運用上の扱いは、この実測の報告 (F-R17 と同じ 1 回の報告) の後に監督が裁定する。
6. **F-R8 の実測 (upgrade との関係)**: `inventory` の (3) の「未適用の platform migration」の検出が 0013 を数えるか、`platform_declarations.MIGRATION_NUMBER`・`PROCESS_CEILINGS_MIGRATION_NUMBER`・`platform_upgrades.PLATFORM_UPGRADE_NUMBERS` などの定数に波及があるかを実測して報告する。
7. **F-R9 の実測 (CONTROL_MAPPING)**: SI-08 の MitateDB ブロックのうち F2 で事実でなくなる (6) の行を列挙し、同じ行の中の置き換えで直した後のブロック長を実測して報告する (基点 15,187 / 上限 15,200 = 残り 13 字)。文字数は `conformance-tests/test_control_mapping_register.py` と同じ分解 (claims を単一空白で join) で測る — 素朴な計測は 147 字ずれる。上限を超える場合は WP-B・WP-E が書いた SI-08 の MitateDB の行の言い回しを詰めて収め (主張と証拠のテスト名を 1 つも落とさない。§4.1 の B-17・B-18 の前例)、それでも超えるなら止まって監督へ上げる (F-R23)。0013 の新しい統制をどの SI の MitateDB ブロックに置くかを提案し、監督の裁定を得る。
8. `tools/tests/test_no_shared_cluster_defaults.py` の件数 pin が変わらないことを実測し、コマンドと件数を F-40b の監査照合の記録として残す (F-R16。テストの置き場は F-R16 で確定しているので、新規テストファイルを作らない)。
9. F-R3 の裁定値を入れた状態で `MitateDB-api/tests` 全体を 1 回回し (§6B.8)、0013 を足した bootstrap の下で既存のテストが赤にならないことを集計行で報告する。赤が出たら、値 (F-R3) と波及 (F-R6) の両方に関わるので止まって監督へ上げる。
10. **F-R13 の形の実測**: 既存の (2)・(3) の項目が `reason` を blocked のときだけ持つのか常に持つのかを実測して報告し、(6) の項目のキーの形をその形に合わせる。キー集合の pin (`test_inventory_top_level_and_item_keys_are_pinned`) と語彙の pin (`test_inventory_reason_vocabulary_is_pinned`) を実測で更新する。
11. **F-R14 の実測**: `ALTER ROLE ... SET statement_timeout` で `ms_from_pg_timeout_text` が解釈できない値を実 role に設定できるかを実測して報告する。できない場合に限り、F2-3 と F2-2 の負値の観測は `platform_declarations._role_setting_rows` をテストで差し替えて行う (F-R14・F-R26)。
12. **F-R20 のテストの作り方**: テストの既定の bootstrap は本番と同じく 0013 まで適用する。0013 より前の状態や「設定の無い role」に依存するテスト (`test_inventory_ddl_lock_is_unknown_when_statement_timeout_not_declared`・`test_inventory_ddl_lock_target_roles_include_auditreader`・終了コード 2 の 2 件ほか) は、その状態をテストの中で明示的に作る (0012 までで止める bootstrap の引数、または対象 role の `ALTER ROLE ... RESET statement_timeout`)。どちらを使うかをテストごとに選んで報告する。

### 6B.8 実行するコマンド

実装担当は root suite・`conformance-tests`・`tools/dev/gate.py` を回さない (§2.2)。次だけを回す。`WT` は監督が割り当てる worktree、`SP` は scratchpad (§2.7)。

```bash
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_ops_inventory.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests/test_ops_apply_platform_migration.py -q
tools/dev/pt.py --wait 3600 -C "$WT" -- MitateDB-api/tests/test_platform_migration_reapply.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- tools/tests/test_no_shared_cluster_defaults.py -q
tools/dev/pt.py --wait 1800 -C "$WT" -- <F-R6 の裁定で触ったテストファイル> -q
tools/dev/pt.py --wait 1800 -C "$WT" -- MitateDB-api/tests -q -n 5 --dist loadgroup
tools/dev/mutate.py "$SP/r45-wpf-mutations.json" -C "$WT" --wait 3600
python3 tools/public_value_scan.py MitateDB-api/migrations/0013_role_statement_timeouts.sql MitateDB-api/src/mitatedb_api/ops.py MitateDB-api/tests/test_ops_inventory.py MitateDB-api/tests/test_ops_apply_platform_migration.py MitateDB-api/tests/test_platform_migration_reapply.py security/CONTROL_MAPPING.md
python3 tools/check_comment_provenance.py --base "<基点 main>" MitateDB-api/src/mitatedb_api/ops.py
python3 tools/check_comment_provenance.py --register
```

- **`MitateDB-api/tests` 全体を 1 回**回すのは、migration を 1 本足すことで tests / conformance の bootstrap helper の列挙に波及するためである (§1.5 の 40a に準じ、波及を peer suite で確かめる)。回すのは F-R6 の裁定を反映した後と、仕上げの 1 回 (Bash の timeout は 600000。超える場合はディレクトリを 2 分割して回す。F-R33)。`conformance-tests` と root suite は回さない (§2.2。conformance を含む root suite は監督の完了ゲートが証拠になる。F-R29)。
- 変異定義は §2.7 の形で 1 変異 1 件、変異ごとに赤になる test id を名指しする。migration ファイルを変異の対象にするときも同じ形で、変異は一時編集として `mutate.py` が戻す。
- `security/CONTROL_MAPPING.md` の該当ブロックの文字数は scratchpad のスクリプトで測って報告する (§2.4)。
- 0013 と `apply-platform-migration` の試験の接続先は使い捨ての PostgreSQL (テスト基盤の管理 DSN) だけとする。本番に対しては実行しない (F-R10、依頼者の条件 (d)、§6A.2 の E-R18)。

### 6B.9 完了条件 → 変異 → 赤になる test id

変異の `file` は、特記の無い行は `MitateDB-api/migrations/0013_role_statement_timeouts.sql`。赤になるテストの名前は予想であり、実装担当が実名に置き換えて報告する。「inv」は `MitateDB-api/tests/test_ops_inventory.py`、「apm」は `MitateDB-api/tests/test_ops_apply_platform_migration.py`、「reapp」は `MitateDB-api/tests/test_platform_migration_reapply.py`。

**F1 — platform migration 0013 (本番に対して実行しない。試験は使い捨ての PostgreSQL だけ。F-R10)**

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| F1-1 | 0013 の適用後、`mitatedbsvc_auditreader` に `statement_timeout` の設定が付く (使い捨てクラスタで `pg_db_role_setting` を読む) | 0013 の auditreader への `ALTER ROLE ... SET` を外す | apm: 0013 適用後に auditreader の設定を読むテスト |
| F1-2 | 0013 の適用前に provision 済みだった application の runtime role と developer role の**両方**に同じ設定が付く。**application 2 本以上で観測する** (1 本だけの空振りを防ぐ) | 2 件。(i) ループから `runtime_role` の `ALTER ROLE` を外す。(ii) ループから `developer_role` の `ALTER ROLE` を外す | (i) apm: 既存 2 application の runtime role の設定のテスト、(ii) 同じテストの developer role 側 |
| F1-3 | ループの対象は `runtime_role`・`developer_role` がどちらも NULL でない行だけで (0012 の第 2 節と同じ絞り)、登録のみで未 provision の行があるクラスタでも 0013 は終了コード 0 で終わる | ループの `WHERE` の絞りを外す | apm: 登録のみの行がある状態で 0013 が成功するテスト |
| F1-4 | 0013 の後に provision した application の runtime role と developer role の両方に、role の**新規作成の枝**で同じ設定が付く | 2 件。(i) 新規作成の枝の runtime role の設定を外す。(ii) 同じ枝の developer role の設定を外す | (i)(ii) apm: 0013 適用後に provision した application の両 role の設定のテスト |
| F1-5 | role が既に存在する枝 (`duplicate_object` の fallback) を通ったときも、両 role に同じ設定が付く | 2 件。(i) fallback の枝の runtime role の設定を外す。(ii) 同じ枝の developer role の設定を外す | (i)(ii) apm: role が先に存在する状態で `begin_provision_application` を呼ぶテスト |
| F1-6 | `begin_provision_application` の 0012 からの差分は `statement_timeout` の追加行だけである (静的照合: 0012 と 0013 の関数本体を比べ、追加行以外の差が 0)。CONNECTION LIMIT 36、`application_id` の正規表現、NAMEDATALEN の検査、password の長さの検査、二重 provision の例外、`assert_role_has_no_memberships`、戻り値が変わらない | 2 件。(i) 0013 の関数の CONNECTION LIMIT の値を 36 以外にする。(ii) 0013 の関数から `assert_role_has_no_memberships` の `PERFORM` を落とす | (i) apm: 関数本体の静的照合のテスト (と既存の CONNECTION LIMIT の検査)、(ii) apm: 同じ静的照合のテスト |
| F1-7 | 付く設定は database 非依存である (`pg_db_role_setting.setdatabase = 0`)。(6) が読むのはこの行である | 0013 の `ALTER ROLE ... SET` に `IN DATABASE` を付ける | apm: `setdatabase = 0` を確かめるテスト (既存の `test_inventory_ddl_lock_ignores_a_per_database_scoped_setting` と同じ観点) |
| F1-8 | 0013 は psql 変数を 1 つも参照せず (`:app_id` を含む)、`_PLATFORM_MIGRATION_VARIABLE_TABLE` の 0013 の欄が空で、実際の `:変数` の集合と一致する | 0013 に `:app_id` の参照を 1 箇所足す | apm: `test_apply_platform_migration_variable_table_matches_each_files_own_references`・`test_apply_platform_migration_accepted_filenames_are_pinned_and_exist_without_app_id` |
| F1-9 | `apply-platform-migration` が 0013 を受け付ける: `_PLATFORM_MIGRATION_FILENAMES` に 0013 を足し、E4-2 の pin の静的テスト (実在・`app_id` 非参照・`app_id` を参照しないファイルとの差が `0001`・`0002` の 2 件) を実測で更新する | `_PLATFORM_MIGRATION_FILENAMES` から 0013 を外す (`file` は `MitateDB-api/src/mitatedb_api/ops.py`) | apm: `test_apply_platform_migration_accepted_filenames_are_pinned_and_exist_without_app_id` と、0013 をサブコマンド経由で適用するテスト |
| F1-10 | 0013 は自分自身で `\set ON_ERROR_STOP on` を持つ (既存の静的テストの対象に 0013 を足す) | 0013 から `\set ON_ERROR_STOP on` を消す | reapp: `test_platform_migrations_declare_on_error_stop_in_the_file` |
| F1-11 | 使い捨てクラスタで、0013 の適用済みの状態から F-R4 の 3 対象 (auditreader の設定を外す・既存 application の role の設定を外す・関数本体をずらす) を手でずらし、`apply-platform-migration` 経由の適用で終了コード 0 かつ 3 対象が元に戻る。続けてもう一度適用して終了コード 0、`updated_at` を除いて差分 0 (WP-C・E4-10 の比較の形) | 0013 の `CREATE OR REPLACE FUNCTION` のブロックを丸ごと外す | apm: ずらした 3 対象が 0013 の適用で戻るテスト |
| F1-12 | `_REAPPLY_PLATFORM_MIGRATION_FILENAMES` に 0013 を足し、`_drift_platform_objects_before_reapplication` に F-R4 の 3 対象のずらしを、`_snapshot()` に auditreader と application の runtime / developer role の設定を足す (`_snapshot()` の既存の比較項目を 1 つも減らさない)。起点の列は `migrations/*.sql` の走査から導かれるので 0013 の追加で自動的に伸びる — `test_reapply_starting_points_cover_every_migration_file_as_a_contiguous_prefix` と `test_excluded_starting_points_are_pinned` が実測で通ることを確かめ、通らなければ止まって監督へ上げる。WP-C・WP-E の証拠を弱めない | `_REAPPLY_PLATFORM_MIGRATION_FILENAMES` から 0013 を外す (`file` は `MitateDB-api/tests/test_platform_migration_reapply.py`) | reapp: `test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix` |
| F1-13 | 0013 → 0012 → 0013 の順で適用した後に provision した application の両 role に設定が付く (0012 と 0013 は同じ関数を `CREATE OR REPLACE` する。F-R22 の (iii)) | 0013 の関数の置き換えを外す | apm: 0013 → 0012 → 0013 の順の後の provision のテスト |
| F1-14 | 0013 は 1 つのトランザクションで走り、途中で失敗したら何も残らない (F-R27) | トランザクションの囲みを外す | apm: ループの途中で失敗する状態を作り、auditreader の設定も残らないことを確かめるテスト |
| F1-15 | 既存 application のループは `pg_roles` に無い role 名の行を飛ばす (deprovision の途中で落ちた行で migration 全体が落ちない)。飛ばした行は (6) の側で confirmed にならないことを同じテストで観測する (F-R28) | 飛ばす条件を外す | apm: role が無い行を持つ台帳で 0013 が終了コード 0 で終わるテスト |
| F1-16 | `_PLATFORM_MIGRATION_VARIABLE_TABLE` のキー集合が `_PLATFORM_MIGRATION_FILENAMES` と一致する (静的テスト。F-R31) | 表から 0013 のキーを外す (`file` は `MitateDB-api/src/mitatedb_api/ops.py`) | apm: 表のキー集合とファイル名の定数の一致の静的テスト |
| F1-17 | 0013 の末尾に 0012 と同じ `REVOKE ALL ON FUNCTION ... FROM PUBLIC` を置き、関数の ACL が 0012 の適用後と同じである (F-R32) | 0013 から `REVOKE ALL ON FUNCTION` を外す | apm: 関数の ACL を読むテスト (reapp の `_function_def_and_acl` と同じ観点) |

**F2 — (6) の実行時設定の値の検査 (F-R5)**

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| F2-1 | 対象 role の全部の `statement_timeout` が正の値 (`setdatabase = 0` の行を `ms_from_pg_timeout_text` で解釈) で CONNECTION LIMIT が有効なら (6) は confirmed | 値を読むキーを `statement_timeout` から別のキー (例 `idle_in_transaction_session_timeout`) に変える (`file` は `MitateDB-api/src/mitatedb_api/ops.py`。以下 F2-8 まで同じ) | inv: 正の値で confirmed になるテスト (既存の `test_inventory_ddl_lock_is_confirmed_when_role_settings_are_declared`) |
| F2-2 | 対象 role のどれかの値が `0` (無制限) または負の値なら (6) は **blocked** (F-R26。負値を実 role に設定できない場合の観測は F-R14 の差し替えでよい) | 2 件。(i) 値の検査を外し、キーの存在だけで満たしたことにする。(ii) `> 0` を `!= 0` にする | (i) inv: 値 0 で blocked のテスト、(ii) inv: 負値で blocked のテスト |
| F2-3 | 対象 role のどれかの値が解釈できない (`ms_from_pg_timeout_text` が `ValueError`) なら (6) は **blocked** (例外を外へ漏らさず、値そのものを出さない) | `ValueError` を捕らえて従来どおりの判定 (confirmed / unknown) にする | inv: 解釈できない値で blocked のテスト (観測の形は F-R14: 実 role に設定できない場合に限り `platform_declarations._role_setting_rows` を差し替える) |
| F2-4 | 対象 role のどれかに `statement_timeout` の設定が無ければ (6) は **unknown** のまま (blocked にしない) | 設定が無いときに blocked を返す | inv: `test_inventory_ddl_lock_is_unknown_when_statement_timeout_not_declared` (既定の bootstrap は 0013 まで適用するので、設定の無い状態はテストの中で明示的に作る。F-R20) |
| F2-5 | 対象 role のどれか 1 つでも条件を満たさなければ (6) 全体がそうなる。application の runtime role だけが 0、developer role だけが 0、auditreader だけが 0 の 3 通りを個別に観測する (空振り禁止) | 3 件。対象 role の集合から (i) application の `runtime_role`、(ii) `developer_role`、(iii) `auditreader_roles` を外す | (i)(ii) inv: `test_inventory_ddl_lock_target_roles_include_application_roles` と runtime / developer だけ 0 のテスト、(iii) inv: `test_inventory_ddl_lock_target_roles_include_auditreader` と auditreader だけ 0 のテスト (各 role を 0 にする状態はテストの中で明示的に作る。F-R20) |
| F2-6 | 値の判定どうしの間では blocked が unknown より強い (既存の (3) と同じ規約。§6B.3)。一方で CONNECTION LIMIT が -1 の role と値 0 の role の混在は **unknown** である (既存の早期 return を変えない。F-R25)。いずれも終了コードは 2 | 2 件。(i) 混在時に後から見つかった unknown で blocked を上書きする。(ii) CONNECTION LIMIT の早期 return を値の判定の後ろへ動かす | (i) inv: 一方の role が 0、他方の role が設定なしのときに blocked のテスト、(ii) inv: CONNECTION LIMIT -1 の role と値 0 の role の混在で unknown のテスト |
| F2-7 | (6) の出力に設定値そのもの (および解釈した ms 値) を出さない。判定語は `_INVENTORY_JUDGMENTS` の語彙のまま (F-R13。キー集合は F2-10 で `reason` の分だけ実測で更新する) | 2 件。(i) (6) の項目に設定値を持つキーを足す。(ii) 値の解釈の経路で語彙外の判定語を返す | (i) inv: `test_inventory_top_level_and_item_keys_are_pinned`、(ii) inv: `test_inventory_judgment_vocabulary_is_closed` |
| F2-8 | 終了コードの規約が変わらない: (6) が blocked でも `inventory` の終了コードは 2 で、判定の前の失敗の 1 と区別される (`_inventory_exit_code` の規約) | (6) が blocked のとき終了コードを 1 に写す | inv: `test_inventory_exit_code_is_2_when_any_item_is_not_confirmed`・`test_inventory_tool_failure_exit_code_is_1_with_fixed_text_only` (confirmed 以外の状態はテストの中で明示的に作る。F-R20) |
| F2-9 | **R-48 の解消そのもの**: 1 つのテストで「0012 までの platform で (6) が unknown → `apply-platform-migration` で 0013 を適用 → confirmed」を観測する (空振り禁止。F-R20) | 0013 の auditreader への `ALTER ROLE ... SET` を外す (F1-1 と同じ操作を別の変異 id で定義する。`file` は 0013) | inv: 0013 適用前 unknown・適用後 confirmed のテスト |
| F2-10 | (6) の blocked は既存の blocked の項目と同じ形で `reason` に固定語 `statement-timeout-unbounded` を持つ。`_INVENTORY_REASONS` にこの語を足し、語彙の pin と (6) のキー集合の pin を実測で更新する (F-R13。blocked のときだけ持つのか常に持つのかは §6B.7 の 10 の実測に合わせる)。語彙外の reason を返さない | 2 件。(i) blocked のとき `reason` を返さない (キーを落とす)。(ii) `_INVENTORY_REASONS` に足した固定語を外し、語彙外の reason を返す形にする | (i) inv: `test_inventory_top_level_and_item_keys_are_pinned`、(ii) inv: `test_inventory_reason_vocabulary_is_pinned` |
| F2-11 | (6) の blocked の `remediation_required` は False のまま (F-R15) | blocked のとき `remediation_required` を True にする | inv: 値 0 で blocked のときの項目の値を pin するテスト (F2-2 のテストに含める) |

**共通**

| # | 完了条件 | 変異 (操作) | 赤になる test id (予想) |
|---|---|---|---|
| F-C1 | migration を列挙する箇所のうち F-R6・F-R21 の裁定で 0013 を足すと決めたものを、同じ変更セットで更新する (位置は 0012 の直後。テストの既定の bootstrap は 0013 まで適用する) | 既定の bootstrap の列から 0013 を外す (`file` は `MitateDB-api/tests/test_ops_inventory.py`) | inv: 既定の platform で (6) が confirmed のテスト (F-R20) |
| F-C2 | 0013 を足さないと裁定した箇所には足さない (`conformance-tests/`・`spec/`・runbook を含む) | **監査照合**: `git grep -n 0012_role_connection_limits` の実測 (基点 18 ファイル・44 箇所) と、足した箇所・足さない箇所の `file:line` の一覧を逐語で設計に残す | — |
| F-40b | 新規テストファイルを作らないので (F-R16)、`tools/tests/test_no_shared_cluster_defaults.py` の件数 pin は変わらない (§1.5 の 40b)。実測で変わったら止まって監督へ上げる | **監査照合**: 実測のコマンドと件数 (基点と同じこと) を逐語で設計に残す | — |
| F-CM | 本 WP のテストと同じ変更セットで `security/CONTROL_MAPPING.md` (英語) を更新する: SI-08 の MitateDB ブロックは F2 で事実でなくなる (6) の主張と証拠のテスト名を同じ行の中の置き換えで直し (文字を足さない)、0013 の統制は F-R9 の裁定の節に置く。あわせて SI-09 の MitateDB ブロックの実測値を更新する: テスト件数、受け付けるファイルの数 (4→5)、再適用テストの名前 (既存の `test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix` は改名せず、docstring に対象ファイルを書く。F-R24)。Version 行の minor を main から 1 つ上げる (F-R9) | **監査照合**: 置き換えた行と足した行、Version 行の前後、SI-08 と追記先の節の MitateDB ブロックの文字数・最長行の実測 (`conformance-tests/test_control_mapping_register.py` と同じ分解。F-R23) を逐語で設計に残す | — |
| F-47 | 追加・変更した migration・コード・テスト・fixture に実値が無い (C5) | **監査照合**: `public_value_scan.py` の集計行を逐語で残す | — |
| F-PROD | 0013 と `apply-platform-migration` を本番に対して実行していない。試験の接続先は使い捨ての PostgreSQL だけである (F-R10) | **監査照合**: 0013 を適用するテストの接続先の出所 (テスト基盤の管理 DSN の環境変数名) の `file:line` を逐語で設計に残す | — |
| F-50 | 本表に変異も監査照合も持たない行が無い (§1.5 の 40) | **監査照合**: 本表の行数と対応数を残す | — |

**件数 (下限)**: 完了条件 35 件 = 変異を持つ行 29 件 (F1-1〜F1-17、F2-1〜F2-11、F-C1) + 監査照合 6 件 (F-C2・F-40b・F-CM・F-47・F-PROD・F-50)。変異は 39 件 (F1-2・F1-4・F1-5・F1-6・F2-2・F2-6・F2-7・F2-10 の各 2 件、F2-5 の 3 件、他の 20 行の各 1 件)。

### 6B.10 監督の確認事項

なし (起草時の疑義 7 件は §6B.2 の F-R13〜F-R19 で決まった)。

### 6B.11 WP-F の訂正註と監督裁定 (2026-09-17〜18、統合時に監督が追記。§6B の本文は書き換えない)

**訂正註 F-1 (件数)**: §6B.9 の件数は、完了条件 35 件 → **39 件** (= 変異を持つ行 33 件 + 監査照合 6 件)、変異 39 件 → **43 件**になった (F-S9 の 36 件・40 件に、差し戻し 1 が 3 行・3 件を足した。差し戻し 1 の文書が書いた「38 件 (32 + 6)」は監督の数え間違いである)。足した行は次のとおり。

- **F1-18** (監督裁定 F-S3): auditreader を適用 role 以外が作った使い捨てクラスタで、`apply-platform-migration` 経由の 0013 が 0 以外で終わり、application role の設定も関数本体の置き換えも残らない。変異は auditreader への `ALTER ROLE` を権限不足を握りつぶす例外処理で包む「足す」形。
- **F1-19** (差し戻し 1 の R1-1): 0013 の関数の置き換えが失敗する状態 (使い捨てクラスタで関数の所有者を適用 role 以外に変える) で `apply-platform-migration` 経由の 0013 が 0 以外で終わり、auditreader と application role の設定が残らない。変異は `COMMIT;` を元の位置 (関数の前) へ戻す。
- **値の literal の静的テストの行** (差し戻し 1 の R1-4、監督裁定 F-S1 の後半): 0013 のコメントを除いた本文から `statement_timeout` に値を置く全出現を走査し、1 件以上・現在の件数の pin・値の集合が 1 要素・その値が `pg_timeouts.ms_from_pg_timeout_text` で正、を固定する。変異はループの 1 箇所だけを別の正の値にする。
- **`reason` キーの全経路の行** (差し戻し 1 の R1-7、監督裁定 F-S6): (6) が返しうる全部の return の経路 (`psycopg.Error`、CONNECTION LIMIT -1、設定なし、confirmed、blocked) でキー集合が同じである。変異は `psycopg.Error` の経路の return から `reason` を落とす。

**訂正註 F-2 (§6B.6 の触るファイル)**: §6B.6 が「着手時の実測と監督の裁定で確定し、訂正註で本表に足す」とした「migration を列挙する箇所」は、監督裁定 F-S2 と第 2 段・差し戻し 1 の実測で次に確定した。**触るファイルに足すもの**: `MitateDB-api/conformance/real_server_mitatedb.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`、`MitateDB-api/tests/control_plane_harness.py`、`MitateDB-api/tests/test_application_audit.py` (以上 bootstrap の 4 ファイル)、`MitateDB-api/tests/test_ops_verify_declarations.py` (`MIGRATION_NAMES` と `_bootstrap`)、`MitateDB-api/tests/test_postgres.py` (コメント 1 行だけ)。

- `MitateDB-api/tests/test_postgres.py` には **0013 を足さない**。この fixture は 0005 を適用せず `mitatedbsvc_auditreader` が存在しないため、0013 を足すと `ALTER ROLE` が対象の role を見つけられずこのファイルの全テストが失敗する (第 2 段の実測。一度足して確認した後に戻した)。足したのは、0012 の隣にその理由を書いた英語のコメント 1 行だけである (差し戻し 1 の R1-5)。
- `MitateDB-api/tests/test_application_audit.py` の 0013 の位置は「0012 の直後」ではなく **0005 の後ろ**である。このファイルの bootstrap は 0005 を最後に適用する順序で、auditreader はその後にしか存在しない (第 2 段の実測)。

**訂正註 F-3 (F2-10 の読み替え、F-S6)**: (6) の項目は (2)・(3) と同じく**常に** `reason` キーを持つ (blocked 以外は `None`)。キー集合の pin は `{"judgment", "remediation_required", "reason"}` に更新する。§6B.9 の F2-10 の変異 (i)「blocked のとき `reason` を返さない (キーを落とす)」は「**blocked のとき `reason` を `None` にする**」と読み替え、赤になるのは値 0 で blocked のテスト (`reason` の値を pin する) とする。

**訂正註 F-4 (`security/CONTROL_MAPPING_HISTORY.md`)**: §2.2 は同ファイルを触らないパス (「追加だけで旧文の移動は生じない」) としている。本 WP は SI-08 の (6) の主張そのものの**訂正**であり、`security/CONTROL_MAPPING.md` 冒頭の Update convention が「訂正は現行行を書き換え、旧文は逐語・無編集で `CONTROL_MAPPING_HISTORY.md` へ移す」と定めるため、統合時に監督が同ファイルの SI-08 の節へ旧文 1 行 (基点の (6) の Control の bullet) を逐語で足した。実装担当は同ファイルに触れていない。足した内容は監査照合 F-CM に記録する。

**訂正註 F-5 (`_added_commit` の未追跡ファイルの扱い、差し戻し 1 の R1-3)**: `MitateDB-api/tests/test_platform_migration_reapply.py` の `_added_commit` は、**未追跡のときだけ** `None` を返す (`git ls-files --error-unmatch` が失敗した場合)。追跡済みで `git log --diff-filter=A` が空なら従来どおり `RuntimeError` を出す。0013 は統合の前は未追跡であり、統合によって追跡済みに変わるため、統合後に監督が `MitateDB-api/tests/test_platform_migration_reapply.py::test_0007_0011_0012_reapplication_is_idempotent_from_every_starting_prefix` を再実行して、追跡済みの経路でも緑であることを確かめる。**結果: 統合後 (0013 が追跡済みの状態) に `MitateDB-api/tests/test_platform_migration_reapply.py` を再実行し `32 passed`。追跡済みの経路で起点 `[11]` が緑である**

**監督裁定 F-S1〜F-S10 (第 1 段の実測への裁定。2026-09-17。逐語)**

- **F-S1** (値。F-R3) 0013 が設定する値は `5000ms` とする。0007 が api / controlplane role に置く値、`config.py` の `max_execution_ms` の既定値、`inventory` 自身の上限と同じ数で、platform の「期限を渡されない文の上限」が 1 つの数になる。要求の経路は `SET LOCAL` が上書きするので (第 1 段の実測 (a))、この値が効くのは期限を持たない経路 (catalog / schema_revision の読み、起動時の台帳の読み、auditreader の監査クエリ、`deadline=None` の DDL) だけである。値は migration の中の 1 か所 (psql 変数でも関数引数でもない SQL の literal。ループ・関数の両枝・auditreader で同じ literal を使うなら、その対応を静的テストで固定する) に置く。`MitateDB-api/tests` 全体がこの値で赤になったら、値を変えずに止まって監督へ上げる。
- **F-S2** (波及。F-R6・F-R21) 0013 を足す: `ops.py` の 2 定数、`test_ops_apply_platform_migration.py`・`test_ops_inventory.py`・`test_platform_migration_reapply.py`、bootstrap の 5 箇所 (`conformance/real_server_mitatedb.py`・`conformance/conformance_adapter_mitatedb_http.py`・`tests/control_plane_harness.py`・`tests/test_postgres.py`・`tests/test_application_audit.py`)、`tests/test_ops_verify_declarations.py` の `MIGRATION_NAMES` (0012 の直後・0007 の前) と同ファイルの `_bootstrap` (0012 の直後に無条件で適用。0012 と同じ形)、`security/CONTROL_MAPPING.md`。位置はどこも 0012 の直後。足さない: runbook、0012 自身、`platform_declarations.py` と `test_control_main.py` の散文、`test_ops_verify_declarations.py` の散文 3 箇所、`tools/control_mapping_axes.tsv`、`docs/`。`MIGRATION_NAMES_WITHOUT_DECLARATIONS` の式は変えず、slice が落とす 2 件が {0007, 0011} であることをそのファイルの中の assert (または既存テスト) で固定する。§6B.6 の触るファイルにこの 6 ファイルを足す (訂正註は監督が統合時に書く)。
- **F-S3** (権限。F-R7・F-R27) 0013 は、適用する role が対象 role への ADMIN OPTION を持たないとき失敗する (PostgreSQL 16)。これは 0012 が application role に対して既に持つ前提と同じで、auditreader について新しく加わる。扱い: 0013 は回避しない (SECURITY DEFINER にしない、権限の無い role を飛ばさない)。失敗したら 1 つのトランザクションごと巻き戻り、`apply-platform-migration` は 0 以外で終わる。0013 のヘッダのコメントに前提を現在形で書く (適用する role は auditreader と各 application role への ADMIN OPTION を持つ。0005 と `begin_provision_application` を同じ role で実行していれば満たされる)。runbook への記載 (前提と、満たさないときの直し方) は WP-D が扱う (監督が §6.1 に WPD-5 として足す)。完了条件を 1 件足す — **F1-18**: auditreader を適用 role 以外が作った使い捨てクラスタで、`apply-platform-migration` 経由の 0013 が 0 以外で終わり、application role の設定も関数本体の置き換えも残らない。変異: auditreader への `ALTER ROLE` を、権限不足を握りつぶす例外処理で包む (「足す」形の変異)。F1-14 の「途中で失敗する状態」は、台帳の application role の 1 つを適用 role 以外が作った状態で作ってよい (auditreader の設定が残らないことを見る)。
- **F-S4** (F-R8) 定数への波及なしを受理。0013 は (3) に現れない。
- **F-S5** (CONTROL_MAPPING。F-R9・F-R23・F-R24) 置き場は 2 つに分ける。SI-08 の MitateDB ブロック: (6) の行を同じ行の中で置き換え、「正の値で confirmed / 0 と解釈できない値は blocked (`statement-timeout-unbounded`) / 設定なしは unknown」と、値の出所が 0013 であること (短い相互参照) を書く。超過分は同ブロックの WP-B・WP-E の行の言い回しを詰めて収める (主張と証拠のテスト名を 1 つも落とさない)。SI-09 の MitateDB ブロック: 0013 の仕組み (既存の全 application role と auditreader、新規作成の枝と既存 role の枝、1 トランザクション、再適用で同じ状態、0012 との適用順の依存、ADMIN OPTION の前提) と F-R24 の実測値。SI-08 のブロックが 15,200 字に収まらないなら止まって監督へ上げる (主張を落とさない)。Version 2.4 → 2.5。
- **F-S6** (F-R13) (6) の項目は常に `reason` キーを持つ ((2)・(3) と同じ形。blocked 以外は `None`)。キー集合の pin を `{"judgment", "remediation_required", "reason"}` に更新する。F2-10 の変異 (i) は「blocked のとき `reason` を `None` にする」に読み替え、赤になるのは値 0 で blocked のテスト (reason の値を pin する) とする。
- **F-S7** (F-R14・F-R26) 負の値と解釈できない値は実 role に設定できない (PostgreSQL が拒否する) ので、F2-2 (ii) と F2-3 の観測は `platform_declarations._role_setting_rows` の差し替えで行う。値 0 は実 role で観測する。差し替えは読む関数だけに限り、判定の関数は本物を通す。
- **F-S8** (F-R20) 既存の 4 件 (`..._is_unknown_when_statement_timeout_not_declared`・`..._target_roles_include_auditreader`・`test_inventory_exit_code_is_2_when_any_item_is_not_confirmed`・`..._target_roles_include_application_roles`) は対象 role への `ALTER ROLE ... RESET statement_timeout` で状態を明示的に作る。F2-9 だけは `_bootstrap` の「0012 までで止める」引数を使う。`MitateDB-api/tests` 全体で他に赤が出たテストは、そのテストが「設定の無い role」に依存しているだけなら同じく RESET で直して報告に名指しし、assert の意味を変える必要があるなら止まって上げる。
- **F-S9** (件数) 完了条件は 36 件 (変異を持つ行 30 件 + 監査照合 6 件)、変異は 40 件 (F1-18 の 1 件を足す) を下限とする。
- **F-S10** (台帳の候補。本 WP では直さない) `control_plane.audit_query` は `_audit_reader.query` の `psycopg.Error` を捕らえない。0013 の後は遅い監査クエリが `QueryCanceled` になる。統合時に監督が台帳に 1 行起票する。

**コードレビュー (独立 1 回) の指摘と差し戻し 1 の裁定**

独立コードレビュー 1 回の指摘は 13 件 (高 2・中 5・低 4・佐 2)。監督の検分を加えて差し戻し 1 (R1-1〜R1-10) とし、各件の裁定と直し方を渡した。実装担当は R1-2 を除く 9 件を直し、R1-2 は実測を添えて止まった (裁定は下の F-S11)。

- **R1-1 (高) 0013 が 1 つのトランザクションになっていない。** 現行: `MitateDB-api/migrations/0013_role_statement_timeouts.sql` の `COMMIT;` が `CREATE OR REPLACE FUNCTION` と `REVOKE` の前にある。壊れるシナリオ: 関数の所有者が適用 role と違うクラスタで関数の置き換えだけが失敗し、終了コードは 0 以外なのに auditreader と application role の設定は残る (ヘッダと SI-09 は「何も残らない」と書いている。運用者が復旧手順を誤る)。直し方: `COMMIT;` を `REVOKE` の後ろ (ファイルの末尾) へ移してファイル全体を 1 つの `BEGIN; … COMMIT;` にし、「0002/0012 の慣習」に触れるヘッダの記述を現在の構造の事実に直す。完了条件 **F1-19** を 1 件足し、変異は `COMMIT;` を元の位置へ戻す形とし、F1-11・F1-12・F1-13 が緑のままであることを確かめる。
- **R1-2 (高) SI-08 の (6) の証拠のテスト名が基点のまま。** 現行: `security/CONTROL_MAPPING.md` の SI-08 MitateDB Evidence の item (6) の行が基点と逐語同一で、値 0 / 負 / 解釈不能 = blocked を裏付けるテスト名が無い (ブロックは 15,194 / 15,200)。壊れるシナリオ: SI-08 を読む監査で、blocked 判定の主張に対応する証拠が辿れない。直し方: その行に新しい判定を裏付けるテスト名を足し、入らない分は同じ MitateDB ブロックの中の言い回しを詰めて空ける (主張と証拠のテスト名を 1 つも落とさない)。どうしても 15,200 に収まらなければ、不足の字数の実測を添えて止まって報告する (監督が置き場を裁定する) → 実装担当は実測 (+473 字に対し安全な詰め代は +55 字、412 字超過) を添えて止まり、下の F-S11 で裁定した。
- **R1-3 (中)** `_added_commit` の `None` の分岐が広すぎる。`git ls-files --error-unmatch` が失敗した (未追跡) ときだけ `None` とし、追跡済みで履歴が空なら従来どおり `RuntimeError` にする (訂正註 F-5)。
- **R1-4 (中)** 値の literal の一致を固定する静的テストが無い。`test_ops_apply_platform_migration.py` に静的テストを 1 件足し、変異を 1 件足す (訂正註 F-1)。
- **R1-5 (中)** 実測と食い違う docstring 4 件 (`test_ops_inventory.py` の fixture の列挙と auditreader の記述、`test_ops_apply_platform_migration.py` の同記述と「4 accepted files」) を現在の事実に直し、`test_postgres.py` の 0012 の箇所に 0013 を適用しない理由を 1 行の英語コメントで足す (訂正註 F-2)。
- **R1-6 (中)** `test_platform_migrations_declare_on_error_stop_in_the_file` が手書きの列挙。対象を `ops._PLATFORM_MIGRATION_FILENAMES` から導き、非空と現在の件数を assert し、docstring を直す (F1-10 の変異が引き続き赤になることを確かめる)。
- **R1-7 (中)** `psycopg.Error` ほかの経路の `reason` キーが未観測。全部の return の経路でキー集合が同じであることを見るテストと変異を足す (訂正註 F-1・F-3)。
- **R1-8 (低)** 0013 のヘッダに、適用の順序の段の 0005 への依存 (auditreader が存在すること) と、権限の段の application role への ADMIN OPTION の前提を現在形で足す。
- **R1-9 (低)** `security/CONTROL_MAPPING.md` の SI-09 の既存の bullet から消した `(R-45 WP-E)` を基点の逐語に戻し、足した bullet と Version 行には既存の行と同じ書き方で `R-45 WP-F` を付ける (文書の出所表記は、コードのコメントの規律の対象ではない)。既存の文を書き換えるのは R1-2 の詰めと (6) の行だけにする。
- **R1-10 (佐)** テストの `PASSWORD 'x'` を他所と同じ `secrets.token_urlsafe(24)` の形にし、F1-6 の静的照合 (0012 と 0013 の関数本体) を多重集合でなく順序つきの比較にする。

**監督裁定 F-S11 (R1-2 の置き場。2026-09-18。逐語)**

> SI-08 の MitateDB ブロックは 15,194 / 15,200 字で、値の検査の証拠のテスト名 6 件 (+473 字) は言い回しを詰めても (実測 +55 字) 入らない。証拠のテスト名は SI-09 の MitateDB ブロックの Evidence に、0013 の統制の隣の 1 行として置く (主張の本体が SI-08 の (6) の行であることをその行に書く)。SI-08 のブロックには足さない。ブロックの上限に張り付いている件は台帳に起票する。

**監査照合の逐語記録 (§6B.9 の 6 件。§1.5 の 40)**

- **F-C2** (足さないと裁定した箇所に足していない): `git grep -c 0012_role_connection_limits -- . ':!docs'` → **16 ファイル・42 箇所** (統合前の再実測。基点 16 ファイル・39 箇所。増分は 0012 に言及する新しいコメントの分)。`git grep -c 0013_role_statement_timeouts -- . ':!docs'` → **10 ファイル・40 箇所**: `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` 2、`MitateDB-api/conformance/real_server_mitatedb.py` 2、`MitateDB-api/src/mitatedb_api/ops.py` 2、`MitateDB-api/tests/control_plane_harness.py` 2、`MitateDB-api/tests/test_application_audit.py` 2、`MitateDB-api/tests/test_ops_apply_platform_migration.py` 19、`MitateDB-api/tests/test_ops_inventory.py` 3、`MitateDB-api/tests/test_ops_verify_declarations.py` 2、`MitateDB-api/tests/test_platform_migration_reapply.py` 4、`security/CONTROL_MAPPING.md` 2 (本体の `MitateDB-api/migrations/0013_role_statement_timeouts.sql` は別)。**足さないと裁定した箇所は 0 件のまま**: runbook `MitateDB-api/docs/cloud-run-cloud-sql.md` (WP-D が扱う)、`MitateDB-api/migrations/0012_role_connection_limits.sql`、`MitateDB-api/src/mitatedb_api/platform_declarations.py`、`MitateDB-api/tests/test_control_main.py`、`MitateDB-api/tests/test_ops_verify_declarations.py` の散文 3 箇所、`tools/control_mapping_axes.tsv`、`conformance-tests/`、`spec/`、`docs/` (本書と設計メモへの監督の追記を除く)。`MitateDB-api/tests/test_postgres.py` もファイル名としては 0 件である (訂正註 F-2)。
- **F-40b** (件数 pin が変わらない): `tools/dev/pt.py --wait 1800 -- tools/tests/test_no_shared_cluster_defaults.py -q` → `pt: 6 passed in 2.40s`。基点と同数で、`test_admin_dsn_env_definitions_are_pinned_to_26_files` の 26 は不変である (新規テストファイルを作らない F-R16 と整合)。
- **F-CM** (`security/CONTROL_MAPPING.md`): Version 行は **2.4 → 2.5 (2026-09-18)**。SI-08 の MitateDB ブロックは (6) の Control の主張 1 行の**置き換えのみ**で **15,187 → 15,194 字** / 上限 15,200 (残り 6 字)。SI-09 の MitateDB ブロックは **6,867 → 8,993 字** / 上限 15,200 (0013 の統制の 2 bullet、`apply-platform-migration` の受け付けるファイル数 4 → 5、テスト件数の実測、および F-S11 により移した (6) の証拠のテスト名 1 行)。最長行は 1,384 字 / 上限 1,400 (統合前の実測)。`conformance-tests/test_control_mapping_register.py` は **`11 passed`**。`security/CONTROL_MAPPING_HISTORY.md` の SI-08 の節へ、置き換えた旧文 1 行を逐語・無編集で足した (訂正註 F-4)。
- **F-47** (実値が無い): `python3 tools/public_value_scan.py` の集計行は、第 2 段 (レビューの再実行を含む) が `# mode=tree files_scanned=11 total_flagged=0`、差し戻し 1 の後の再実行が `# mode=tree files_scanned=6 total_flagged=0`。
- **F-PROD** (本番に実行していない): 0013 と `apply-platform-migration` を適用する全テストは、テスト基盤 (`tools/testpg/dsa_testpg.py`) が使い捨てクラスタごとに設定する環境変数 `MITATEDB_TEST_ADMIN_DSN` だけを接続先の出所とする。`file:line` (統合前の再実測): `MitateDB-api/tests/test_ops_apply_platform_migration.py:47` (`_admin_dsn`)、`MitateDB-api/tests/test_ops_inventory.py:50` (`_admin_dsn`)、`MitateDB-api/tests/test_platform_migration_reapply.py:47` (`_admin_dsn`)。本番の DSN・実ホスト名への参照は 0 件で、F-47 の `total_flagged=0` と一致する。
- **F-50** (対応の無い行が無い): §6B.9 の完了条件は 39 行 = 変異を持つ 33 行 + 監査照合 6 行 (F-C2・F-40b・F-CM・F-47・F-PROD・F-50)。変異は 43 件で、すべて期待どおり赤になった (第 2 段 40 件 + 差し戻し 1 の新規 3 件 R1-1・R1-4・R1-7。差し戻し 1 では F1-12・F1-10・F1-6 の 2 件を再実行し、いずれも赤のまま)。変異も監査照合も持たない行は 0。

**完了ゲート (監督が単独で実行。逐語)**

```
gate: 3688 passed, 2 subtests passed in 299.61s (0:04:59)
gate: judge=PASS
```

**統合コミット**: 作業コミット `467b932`、main へのマージ `1620563` (2026-09-18)

## 7. 本書の範囲外の後続 (列挙のみ。本書の WP では行わない)

次は本書の全 WP の受け入れ後に、それぞれ別の設計・作業指示書で扱う。順序は起票原文と `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-45 行に従う。

1. WP-D の runbook による Gate-0 の本番の読み取り (接頭辞 N の記録を含む。W-3) と、isolated での `--quiet` の既定応答の確認 (W-6) (設計の経路が受け入れられた後に operator が実行する。取り込み時の註の制約)。
2. isolated での、同一の候補 digest による `operation_depth=13` の公開・13 の受理・14 の拒否の証明 (起票原文の手順 3)。
3. 本番 Data / Control の更新 (起票原文の手順 4。変更クラスは後続の設計で改めて判定する。設計 D-7)。
4. 独立監査と、その後の Mitate 側の F9 の再判定 (起票原文の手順 4)。
