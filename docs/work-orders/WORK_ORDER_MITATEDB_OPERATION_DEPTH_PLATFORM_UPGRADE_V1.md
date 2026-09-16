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
| WP-A | (着手時に記入) | (着手時に記入) | (着手時に記入) |
| WP-B | (着手時に記入) | (着手時に記入) | (着手時に記入) |
| WP-C | (着手時に記入) | (着手時に記入) | (着手時に記入) |
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

## 7. 本書の範囲外の後続 (列挙のみ。本書の WP では行わない)

次は本書の全 WP の受け入れ後に、それぞれ別の設計・作業指示書で扱う。順序は起票原文と `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-45 行に従う。

1. WP-D の runbook による Gate-0 の本番の読み取り (接頭辞 N の記録を含む。W-3) と、isolated での `--quiet` の既定応答の確認 (W-6) (設計の経路が受け入れられた後に operator が実行する。取り込み時の註の制約)。
2. isolated での、同一の候補 digest による `operation_depth=13` の公開・13 の受理・14 の拒否の証明 (起票原文の手順 3)。
3. 本番 Data / Control の更新 (起票原文の手順 4。変更クラスは後続の設計で改めて判定する。設計 D-7)。
4. 独立監査と、その後の Mitate 側の F9 の再判定 (起票原文の手順 4)。
