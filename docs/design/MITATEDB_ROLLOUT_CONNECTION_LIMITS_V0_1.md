# MitateDB の rollout 中の role `CONNECTION LIMIT` 設計メモ（v0.4）

- 状態: **依頼者裁定済み (2026-09-18)**。Q-1〜Q-4 はすべて監督の推奨どおり (§10.1)。Q-4 の中身は本番の読み取りの後に裁定する。
- 台帳: 計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-52**（`RM`:439）。
- 起票: 2026-09-18。R-45 WP-D の設計レビュー 2 回目の高 1 件と監督の現物確認（`RM`:439）。依頼者の回答（2026-09-18、逐語）「本番の読み取りより前に着手」により、本番の Gate-0 読み取りに先立つ比較資料として起こした。
- 改版: v0.1（2026-09-18）起票。v0.2（2026-09-18）依頼者裁定を §10.1 に逐語で記録し、Q-3 の推奨欄を監督が記入した。v0.3（2026-09-18）設計レビュー 1 回目の 8 件を反映（監督裁定 2026-09-18、すべて採用）: 0013 の再適用と適用順の不変量、`0014` の性質（1 トランザクション・ADMIN OPTION・auditreader のヘッダ上書き）、runbook §10.8 の再受理の WP、条件 2 の合計の言い換えと物理的 worst case、R-50 を WP-3 の前提条件へ、追随先とテストの行番号の実測。本文の行は消していない（`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56）。v0.4（2026-09-19）§4 の行番号に実測の訂正註を足した。本文の決定は変えていない。
- 公開規律: `docs/work-orders/OPERATING_CONDITIONS.md` §2 の 13、§1.9。本メモの数値はすべて本リポジトリの現物から読んだ値と算式であり、本番の読み取り値・DSN・ホスト名は 1 つも含まない。

## 1. 問題

- `MitateDB-api/migrations/0012_role_connection_limits.sql` の 68 / 20 / 36 と `MitateDB-api/migrations/0005_application_audit.sql`:247 の auditreader 5 は、いずれも **1 plane 1 process・concurrency 32** の前提で導いた値である（導出式は 0012:70-73、`MitateDB-api/src/mitatedb_api/config.py`:77 の既定 32）。
- 一方 `ops inventory` の項目 (8) の需要は **process 数の合計に比例**する（`MitateDB-api/src/mitatedb_api/ops.py`:2532-2557）。合計は Cloud Run の worst-case（traffic > 0 の revision ＋ tag 付き ＋ `minScale` ≥ 1 ＋ candidate 自身の上限）である（runbook `MitateDB-api/docs/cloud-run-cloud-sql.md`:2082-2134）。
- Cloud Run の rollout は candidate を `--no-traffic` で作り、health を見てから traffic を移す形なので（runbook:3019 以下の §10.10.3 の手順 13・16）、旧 revision と candidate が並ぶ。**合計は最低 2 になる。**
- したがって Control を配備した本番の Gate-0 では (8) が blocked になる見込みである。runbook §10.10 の前提条件は、本番の状態を 1 つも変える前に紙の上で検算し、収まらなければ直しの段を始めず `blocked—platform remediation required` で止まる手順として閉じている（runbook:2526-2532「この節に直し方は無い。上限を上げるには新しい platform migration が要り、合計の数え方を変えるのは別の決定」）。

## 2. 守るべき条件

- (i) (8) の需要は worst-case で数える。R-45 WP-E の裁定（作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`:687 の E-R4、:712 の E2、:799-800 の E2-5・E2-6）と runbook:2082-2134 を覆さない。
- (ii) `0012` は書き換えない。適用済みの migration は不変とし、新しい番号で足す。
- (iii) 契約 1.8.0 と `security/SECURITY_INVARIANTS_V1.md` に触れない。
- (iv) r2db-api の `0013_role_connection_limits.sql` との peer 対称は「同じ安全上の結果」で足りる。配備形態の違い（VPS の単一 process の再起動 vs Cloud Run の revision 並走）による platform 固有の差は `CLAUDE.md`（Security Invariants / Boundaries の節）が許す。ただし **r2db-api 側に同じ問題が無いことの確認は残課題**（§9）。
- (v) 依頼者の設計原則: 先送りしない・シンプル・制約で回避しない。

## 3. 現物の事実

### 3.1 上限と需要

| role | 現行の `CONNECTION LIMIT` | 出所 | (8) の需要（合計を N とする） | F-16 の床（1 process 分） |
|---|---|---|---|---|
| `mitatedbsvc_api` | 68 | 0012:114 | N × 2 × concurrency（ops.py:2532、2536） | 2 × concurrency（`platform_declarations.py`:917、1052） |
| `mitatedbsvc_controlplane` | 20 | 0012:115 | N × 16（ops.py:2533、2541） | 16（platform_declarations.py:927、1057） |
| `<id>_rt` / `<id>_dv` | 36 | 0012:135-136（既存分）、0012:197・202・208・213（`begin_provision_application` 内、将来分） | N × concurrency（ops.py:2555） | concurrency（platform_declarations.py:1082-1083） |
| `mitatedbsvc_auditreader` | 5 | 0005:247（0012 は触らない。0012:78-79）。`CREATE ROLE` は `IF NOT EXISTS` の中にあり（0005:244-250）、0005 の再適用は上限を変えない | N × 4（ops.py:2534、2542） | 4（platform_declarations.py:934、1064） |

- 判定条件 1（role ごとに 上限 ≥ 需要）は ops.py:2544-2558、条件 2（total demand ＋ reserved ≤ `max_connections`）は ops.py:2589・2594。`max_connections` は読み取り時に `SHOW max_connections` で読む（ops.py:2488）。
- 「+4」は 0012 が入れた固定の operator-headroom margin（0012:65-68。r2db-api の 0013 と同じ）。F-16 はこの +4 を含まない素の pool 床を見る、**弱い**（強くはならない）下限である（0012:83-94）。
- 宣言 `process_ceilings` との比較は **各 revision 単体の上限**で行い、余力の計算は合計で行う（ops.py:2577-2583、WP-E の E2）。現行の宣言例は `--data 1 --control 1`（runbook:1206）。

### 3.2 検算（concurrency = 32、application 1 件以上が登録済みの前提）

| role | 現行上限 | 定常（合計 1）の需要 | rollout（合計 2）の需要 | 判定 |
|---|---|---|---|---|
| `mitatedbsvc_api` | 68 | 1 × 2 × 32 = 64 | 2 × 2 × 32 = 128 | 128 > 68 → blocked |
| `mitatedbsvc_controlplane` | 20 | 1 × 16 = 16 | 2 × 16 = 32 | 32 > 20 → blocked |
| `<id>_rt` / `<id>_dv` | 36 | 1 × 32 = 32 | 2 × 32 = 64 | 64 > 36 → blocked |
| `mitatedbsvc_auditreader` | 5 | 1 × 4 = 4 | 2 × 4 = 8 | 8 > 5 → blocked |

- **条件 2 が裁定 Z-27 の下で計算する合計**（ops.py:2588-2589 の式。application の需要は件数によらず 1 回だけ加える = 完了条件 34b、作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`:320、式は設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md`:141。末尾の +2 は読み取り自身の接続、ops.py:2018）: 定常 64+16+4+32+2 = **118**、rollout 128+32+8+64+2 = **234**（いずれも reserved を除く）。物理的な同時接続数そのものではない（§7）。
- 4 つの role すべてが rollout で上限を超える。R-52 の見込みのとおりである。

## 4. 候補 (a): 新しい platform migration `0014` で上限を並走分に合わせる（**監督の推奨**）

- 各 role の上限を「rollout 中の process 合計 ＝ 2 × 1 process 分の pool」に合わせる。margin の +4 は 1 つのまま（2 倍にしない）。

| role | 現行 | (a) の値 | 算式 |
|---|---|---|---|
| `mitatedbsvc_api` | 68 | **132** | 2 × (2 × 32) + 4 |
| `mitatedbsvc_controlplane` | 20 | **36** | 2 × 16 + 4 |
| `<id>_rt` / `<id>_dv` | 36 | **68** | 2 × 32 + 4 |
| `mitatedbsvc_auditreader` | 5 | **12** | 2 × 4 + 4 |

- 根拠: 需要の数え方（条件 (i)）と 0012 の導出式（pool 合計 + 固定 margin、0012:65-68）を両方そのまま使い、変えるのは「1 process 分」を「並走する process 合計」に置き換える 1 点だけである。条件 (ii) を満たし（0012 は不変、新番号で追加）、契約にも Security Invariants にも触れない。手順で並走を避ける（候補 (c)）のではなく、実際に起きる並走を上限が受け止める形なので条件 (v) の「制約で回避しない」に沿う。
- application role は既存分（0012:135-136 に相当する `DO` ブロック）と `begin_provision_application` の両方を直す必要がある（将来の application が 68 で作られるため）。
- **付随して要る事実**（いずれも現物から導かれる。決定ではない）:
  - `0012` を `0014` の後に再適用すると、0012 は自分の値（68 / 20 / 36）へ**下げ直す**（runbook:2310 の §10.6 の 0012 行、CONTROL_MAPPING.md:650）。
  - `0013` も `begin_provision_application` を `CONNECTION LIMIT 36` ＋ `statement_timeout` の形で置き換えている（0013:154・160・167・173 と 157・163・170・176）。したがって `0014` の後に **`0013` を単独で再適用すると、将来の application の上限が 36 に戻る**（既存 role の上限は 0013 が触らないので変わらない）。0012 と同列の性質である。
  - **適用順の不変量: `0014` は `0012` と `0013` の両方の後**。numbered set の順序は `0012` → `0013` → `0014` になる（現行の step 7 は「`0012`、次に `0013`」、runbook:2866-2872）。`0014` が `begin_provision_application` を置き換えるなら、0013 の `statement_timeout` を**落とさない**形で書く（0013:22-30 が 0012 について述べているのと同じ関係）。
- **`0014` の性質**（現物の形に合わせる。決定ではない）:
  - ファイル全体を 1 つの `BEGIN … COMMIT` とし、途中で失敗したら何も残さない。`0013` がこの形である（runbook:2358 の §10.7 の 0013 行「the whole file is one `BEGIN`/`COMMIT`」）。`0012` の section 3 がトランザクションの外にある形（runbook:2357）は真似ない。根拠は R-45 の差し戻し 1 の R1-1（作業指示書:1139。完了条件 F1-19 は同:1107）。
  - 適用 role は `mitatedbsvc_api` / `mitatedbsvc_controlplane` / `mitatedbsvc_auditreader` と各 application の runtime / developer role への **ADMIN OPTION** を前提とする（`ALTER ROLE` の PostgreSQL 16 の規則。0013:32-40 と同じ前提）。
  - ヘッダで **0012:78-79 の「auditreader は触らない」を明示的に上書きする**。覆した記述は消さず、覆した根拠と日付を添えて参照する（`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56）。
- 追随が要る現物:
  - `apply-platform-migration` の受け付け定数と変数表（ops.py:2627-2633、2641-2647）。help の列挙は定数から導出されるので文面の手直しは要らない（`MitateDB-api/tests/test_ops_help_text.py`:38-50 が定数由来であることを pin。ops.py:3066 以下の help は定数を読む）。
  - テスト: `MitateDB-api/tests/test_ops_apply_platform_migration.py`:329（受け付け定数のタプル一致 pin）・:339（`:app_id` を取らないファイルの補集合が bootstrap 2 本だけ）・:849（変数表の key 集合の一致）。`MitateDB-api/tests/test_platform_migration_reapply.py`:293-296（再適用する platform migration の列）・:829-835（適用の列）・:842（1 回目と 2 回目の一致）・:1039（`len(_PLATFORM_MIGRATION_FILENAMES) == 5` の件数 pin）。`MitateDB-api/tests/test_ops_inventory.py`:1653-1664（合計 20 で blocked）・:1700-1710（`concurrency=35` で api の需要 70 > 68 として blocked）は上限の値に依存するので、上限を上げると blocked にならなくなる。入力の見直しが要る。
  - runbook: §10.6 の 0012 行（:2310）と 0013 行（:2311「additive; it drops and revokes nothing」）と新しい 0014 行、§10.7 の 0012 / 0013 の行（:2356-2358）と **0014 の行および `lock_timeout` の値**、§10.10 の前提条件の算式（:2495-2532）、§10.10.1 の (8) の行（:2701）、§10.10.1 の step 7（:2866-2872。`0012` → `0013` → `0014`）。
  - runbook §10.8 の受理記録（:2380-2392）。**表や手順の版が上がると「版が一致しない記録は記録が無いのと同じ」**（:2384-2385）なので、受理は無効に戻る。現行の受理は §10.6 版 2 / §10.7 版 2 / §10.10 版 5 で、記録先は設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12.6（同:689）。新しい受理はその次の番号の節に置く。→ §11 の WP-4。
  - `security/CONTROL_MAPPING.md`: :548（「r2db-api と同じ算式」の主張）、:641（受け付けファイルの列挙）、:647（「0012 alone afterward … corrected by the next `apply-platform-migration 0013`」— 0014 を含む順序に直す）、:650（numbered set と再適用が value-neutral でない旨）、:659（§10.8 の受理と版数の対応）、:5（版数の記述「tables at version 2, the procedure at version 5, … 0005/0007/0011/0012/0013」）。
- 注意（事実）: `0012:68` は「MitateDB の runbook の "role CONNECTION LIMIT" 表」に全算術があると書いているが、MitateDB の runbook にその表は無い（実測。同名の表があるのは `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`:333）。MitateDB 側で値を持つのは runbook:2310 の §10.6 の行と :2701 の §10.10.1 の行である。
- **訂正註（2026-09-19、WP-3 着手時の実測）**: 上の `security/CONTROL_MAPPING.md` の行番号は起票時（v0.1、2026-09-18、`security/CONTROL_MAPPING.md` 版 2.6）の実測値である。上の行は消さない（`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 56）。roadmap R-50（作業指示書 `docs/work-orders/WORK_ORDER_R50_CONTROL_MAPPING_MULTI_BLOCK_V1.md`、版 2.7・2.8）が SI-08 / MitateDB-api を既定ブロックと `ops inventory` ブロックに分け、SI-09 の Evidence 1 行を SI-08 へ移した結果、同じ主張は R-50 統合後（main `d2e7333`）に :578（同じ算式）・:641→:684（受け付けファイルの列挙）・:647→:690（`0012` alone afterward …）・:650→:693（numbered set）・:659→:701（§10.8 の受理と版数）へ動いた。さらに WP-3 自身の書き換えの後は :580・:691・:697・:702・:710 である。:5（版数行）は行番号こそ動いていないが、そこが名指していた文面「tables at version 2, the procedure at version 5, … 0005/0007/0011/0012/0013」は版 2.7・2.8 の版数行に丸ごと置き換わっており、現行の版数行は 10.6/10.7/10.10 の版も migration の列挙も持たない（版数行はその版の変更を述べる行で、累積しない）。同じ内容を持つのは SI-09 / MitateDB-api の Evidence と Status、および SI-09 / MitateDB-api の Control の numbered set の行である。行番号で名指す先を読むときは、着手時に現物で実測し直す。
- **訂正註（2026-09-19、R-59）**: 上の註が挙げる SI-09 / MitateDB-api の行番号は R-52 WP-3 の時点の実測値である。R-59（`security/CONTROL_MAPPING.md` 版 2.11、作業指示書 `docs/work-orders/WORK_ORDER_R59_SI09_MITATEDB_BLOCK_SPLIT_V1.md`）で、受け付けファイルの列挙・`0012` alone afterward・numbered set・§10.8 の受理と版数の主張は、文を変えずに名前付き小ブロック `SI-09 / MitateDB-api / platform upgrade`（Control・Evidence・Status の各軸）へ移った。以後は行番号でなくこの所在で辿る。SI-08 側の算式の行は動いていない。

## 5. 却下の見立て (b): 数え方の見直し（`--no-traffic` の間は candidate を数えない等）

- traffic を切り替える瞬間には新旧の両 revision が同時に要求を受けうるので、過小評価になる。runbook:2119-2120 が「今この瞬間の実行インスタンス数ではなく worst-case」と明記し、過小評価は「PostgreSQL 自身の `CONNECTION LIMIT` 拒否に当たる DB で (8) が confirmed になる」と述べている。
- WP-E の裁定（E-R4・E2・E2-5・E2-6）を覆すことになり、条件 (i) に反する。**却下の見立て。**

## 6. 却下の見立て (c): 旧 revision を先に止める手順

- Cloud Run は traffic 0 になった revision の instance を即時には消さない（idle で縮退する。時点が決定的でない）。「先に止めた」ことを手順で確定できない。
- 確定させるには旧 revision を明示的に落とすことになり、切り替えの間に停止時間が生じる。条件 (v) の「制約で回避しない」に反する。**却下の見立て。**

## 7. 従属する条件 — 条件 2 と `max_connections`

- (a) は条件 1（role ごと）を解く。条件 2（合計 ＋ reserved ≤ `max_connections`、ops.py:2594）は **`CONNECTION LIMIT` を上げても変わらない**。rollout 時に**条件 2 が裁定 Z-27 の下で計算する合計**は §3.2 の **234**（＋ reserved）である。
- **この合計は物理的な worst case ではない。** Z-27 の式は application role の需要を件数によらず 1 回だけ数える（作業指示書 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md`:316・320、設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md`:141）。物理的な worst case は application の件数 N と runtime / developer の別に比例する: `合計(data) × 2 × concurrency ＋ 合計(control) × 16 ＋ 合計(control) × 4 ＋ 合計(data) × concurrency × 2 × N ＋ 2`（rt と dv はそれぞれ concurrency 分の pool を持つ。platform_declarations.py:1082-1083）。**Z-27 自体は覆さない**（条件 (i)）。Q-4 の裁定はこの差を承知の上で行う。
- 本番の Cloud SQL の `max_connections` の値は本リポジトリに無く、本番の読み取りで初めて分かる（runbook は値を書かず、実行時に読む形にしている）。
- 234 ＋ reserved（あるいは上の物理式の値）が `max_connections` を超える場合、直し方は Cloud SQL 側の flag 変更か concurrency の引き下げであり、**migration では直らない**。→ Q-4。

## 8. F-16 の床の扱い（事実のみ。判断は §10 の Q-3）

- F-16（`platform_declarations.check_role_connection_limits`）は各 composition root の起動時と `ops verify-declarations` で、その process 自身が接続する role の床を見る（platform_declarations.py:993-1035）。床は §3.1 の右端の列、すなわち **1 process 分**である。
- F-16 は「その process 自身の pool が上限に収まるか」を見る検査であり、他の revision が同時に何本持つかはその process から観測できない。
- 3 つの床定数と `_f16_message` は peer 対称の正規化差分テストに **pin** されている（`MitateDB-api/tests/test_audit_query.py`:2671-2674）。`check_role_connection_limits` 本体は行に無い（同:2623）。MitateDB 側だけ床を 2 倍にすると、この pin と `security/CONTROL_MAPPING.md`:548 の「r2db-api と同じ算式」という主張の両方に手当てが要る。
- 逆に床を 1 process 分のままにすると、(a) で上限を 132 / 36 / 68 / 12 に上げた後、誤って 64 / 16 / 32 / 4 まで下げられても F-16 は通る（(8) の読み取りだけが捕らえる）。

## 9. 残課題

- **r2db-api 側に同じ問題が無いことの確認**（条件 (iv)）。現時点の実測: r2db-api は VPS 配備で（`CLAUDE.md` Boundaries、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`:5）、`ops inventory` 相当の Gate-0 検算を持たない（grep 0 件）。Cloud Run のような revision 並走の配備形態かどうかは未確認であり、「同じ問題が無い」は**まだ推測**である。着手時に r2db 側の配備手順（同時に走る process 数）を読んで確かめる。
- （R-50 の字数上限は v0.3 で §11 の WP-3 の前提条件へ移した。行は消していない。`OPERATING_CONDITIONS.md` §1.8 の 56）

## 10. 依頼者に伺う点

| # | 問い | 監督の推奨 |
|---|---|---|
| **Q-1** | 候補 (a)（新しい platform migration `0014` で上限を 132 / 36 / 68 / 12 に上げる）でよいか。(b)(c) は §5・§6 のとおり却下の見立て。 | (a) を採る |
| **Q-2** | 並走する process 数の上限を **2** に固定してよいか。`process_ceilings` の `data`（現行の宣言例は 1、runbook:1206）を将来 2 以上に上げるときは、同じ算式で **再び新しい migration が要る**（上限は宣言値に比例しないため）。 | 2 に固定し、ceiling を上げるときに同じ算式で新しい migration を足す |
| **Q-3** | F-16 の床を 1 process 分のままにするか、合計 2 の床に上げるか（§8 の事実を参照。上げる場合は peer 対称の pin と CONTROL_MAPPING の「同じ算式」の主張に手当てが要る）。 | 1 process 分のままにする。F-16 が守る性質は「その process 自身の pool が上限に収まる」ことで、並走分の余力は `ops inventory` の (8) が守る性質である。peer 対称の pin と「同じ算式」の主張も変えずに済む。§8 の末尾の穴 (64 まで下げても F-16 は通る) は (8) の読み取りと runbook の適用順 (`0014` が最後) で受ける |
| **Q-4** | 本番の `max_connections` が 234 ＋ reserved に足りない場合の方針（Cloud SQL の flag 変更 / concurrency の引き下げ / その他）。 | 本番の読み取りの後に裁定する |

### 10.1 依頼者裁定 (2026-09-18、逐語)

「Q-1〜Q-4 はすべて推奨どおりで進めてください」

- 帰結: (a) を採る。値は 132 / 36 / 68 / 12。並走は 2 に固定する。F-16 の床は 1 process 分のまま。`max_connections` が足りない場合の方針は本番の読み取りの後に裁定する。再審議しない (`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 51)。

## 11. 変更クラスの見込みと WP の粗い切り方

- 変更クラスの見込み: **Class D**（契約版数は 1.8.0 のまま、公開契約・Security Invariants に触れない）。判定は着手時に `tools/change_class.py` と `RM` §9 で確定する。
- WP の粗い切り方（順序あり。重なりの 0 は作業指示書で実ファイル名の表として示す）:
  1. **WP-1**: migration `0014` ＋ `apply-platform-migration` の受け付け定数・変数表（ops.py:2627-2647）＋ 再適用テスト・適用テスト・(8) のテストの入力（§4 の追随一覧の行）。
  2. **WP-2**: runbook（§10.6 の 0014 行・**§10.7 の 0014 の行と `lock_timeout` の値**・§10.10 の前提条件の算式・§10.10.1 の step 7 と (8) の行）。
  3. **WP-3**: `security/CONTROL_MAPPING.md` の該当行（§4 の追随一覧）。**前提条件: R-50 の統合後に着手する。** 監督裁定 (2026-09-18):「R-50 を先に解く。台帳の順を R-51 → R-50 → R-54 に入れ替え、WP-3 は R-50 の統合後に着手する。WP-1・WP-2 は R-50 に依存しない」。R-50 は SI-08 の MitateDB ブロックが 1 ブロックの上限 15,200 字に張り付いている件（`RM`:437、実測 15,194 字。上限は `conformance-tests/test_control_mapping_register.py`:88）。
  4. **WP-4**（最終）: runbook §10.8 の**再受理**。版が上がると受理は無効に戻る（runbook:2384-2385）ので、独立の設計レビュー → §10.6 / §10.7 / §10.10 の新しい版の記入（runbook:2277、2326、2469 の版数の行を含む）→ 設計メモ `docs/design/MITATEDB_PLATFORM_READONLY_INVENTORY_V0_1.md` §12（現行の記録先は §12.6、同:689。新しい記録はその次の番号の節）への逐語記録、の順に行う。
- Q-3 が「床を上げる」になった場合は、`platform_declarations.py` の床定数と peer 対称の pin を扱う WP を WP-1 とは別に立てる（両 peer に跨るため）。→ 依頼者裁定（§10.1）により Q-3 は「1 process 分のまま」で決着したので、この WP は起こさない。

**【訂正註 2026-09-29】** `ops inventory` の項目 (8) の需要の基準は `docs/design/MITATEDB_INVENTORY_DEMAND_BASIS_V0_1.md` (v0.3) で改めた: 需要は revision の基準ごとに数えて足し (古い code は `concurrency` 基準、新しい code は起動時の検査と同じ thread limit 基準)、合計の application の項は永続接続の数を下回らない。本メモ §3 の検算 (`concurrency` = 32 の 1 基準) は、全 revision が古い code の場合の値として読む。上限の値 (`0014`) は変えていない。
