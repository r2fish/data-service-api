# 作業指示書 — R-120 r2db の DML 検証と書き込みの間の alter の窓 (実体単位の共有 lock)

## 0. 出所と基点

- **v1.0 (2026-10-03)。** 基点はローカル main `1abd5e8` (作業ツリー `.claude/worktrees/r120`、branch `r120`)。台帳は `RM` §8.1 の R-120 (v1.154 の【追記】を含む)。
- **規模 M** (`OC` §1.13 の 74): 本書 1 節、設計は本書 §1 に内蔵し専用の設計文書は起こさない。実装担当 1 起動 (`ROLES` の 2)、コードレビュー 1 起動 (`ROLES` の 5、Class D)、受け入れ監査 1 起動 (`ROLES` の 6)、完了ゲート。
- **変更クラス B + D** (r2db のコードと tests + `CM` SI-11 r2db 節。`tools/change_class.py` → `D`)。契約・`spec/`・共通条件は変えない。
- **略記**: `OC` = `docs/work-orders/OPERATING_CONDITIONS.md`、`RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、`ROLES` = `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`、`CM` = `security/CONTROL_MAPPING.md`、`RB` = `docs/design/REQUESTER_RULINGS_R30_R118_R120_V0_1.md` (v0.2)、`D3` = `docs/design/MITATEDB_APPLICATION_SERIALIZATION_V0_1.md`、`R` = `r2db-api/src/r2db_api/postgres.py`、`MB` = `MitateDB-api/src/mitatedb_api/backend_postgres.py`、`MC` = `MitateDB-api/src/mitatedb_api/cell.py`、`RT` = `r2db-api/tests`、`$SP` = 監督が発注時に渡す scratchpad、`$WT` = `.claude/worktrees/r120`。行番号は基点の現物。
- 本書ローカルの ID: 決定 D-1〜D-7、完了条件 CC-1〜CC-11、変異 M1〜M4。lock の段 3a / 3b は `D3` の順序表 (`D3`:183-190) の名で呼ぶ。

## 1. 設計 (問題設定と決定)

### 1.1 問題と守る条件

- r2db の DML は enum / nullable を registry から読んで Python で検証し、物理制約は無い (`RB` §4.1)。`transact` (`R`:1586、1 要求 1 entity) は transaction 開始 (`R`:1637) → keyed・非 dry_run のときだけ per-key lock (`R`:1646) → lookup (`R`:1647、replay はここで返る) → count lock (`R`:1668) → reserve (`R`:1669) → `_load_catalog` (`R`:1670) → 最初の write (`R`:1838 の `_insert` 呼び出し) の順で、`_load_catalog` から最初の write まで実体に関する lock を持たない。
- その間に同じ entity の制約を変える schema 操作 (`alter_field`、`add_field` の `nullable: false`) が commit すると、古い宣言で検証済みの値が書かれ、宣言に反する行が残る (構造のみ、未再現)。窓は schema 操作が LOCK TABLE (`R`:2268、`R`:2330) を先に取る場合に限らず、`R`:1670〜`R`:1838 の間に schema 操作が完走すれば同じである (`_load_catalog` は `information_schema` / `pg_catalog` だけを読み実体の表を lock しない、`R`:1128-)。
- 台帳 R-102 の 3a (`R`:1405-1415、`pg_advisory_xact_lock(761761763)`) は `apply_schema` (`R`:2157) だけが取り、schema 操作同士しか直列にしない。MitateDB は 3b (`MB`:259-266、`MB`:609-614。DML は `MC`:1959・:2257・:2378・:2749 で共有、schema 操作は `MC`:1242・:1499・:1746 で排他) で閉じており、両 peer の安全性の結果が食い違う。開示は `CM`:1534。
- **守る条件**: (1) DML と、対象 entity の制約を変える schema 操作は重ならない (MitateDB の 3b と同じ性質)。(2) client に新しい失敗を見せない (CONFLICT の新しい発生条件を作らない)。(3) registry と DDL の二重真実を作らない。(4) 既存の性質 — schema 操作が 3a で待つ間、別 key の keyed DML が通る (`RT/test_schema_serialization_lock.py`:170-236) — を保つ。(5) 輪 (40P01。`R`:1755 / `R`:2449 の `except psycopg.Error` で 503) を作らない。(6) 契約は変えない。

### 1.2 決定

- **D-1** 依頼者裁定 2026-10-03 (逐語)「(i) 着手、案 B 実体単位の共有 lock (推奨)」(`RM` §8.1 の R-120 行 v1.154 の【追記】、`RB` §4.5)。閉じ方は `RB` §4.3 の案 B。
- **D-2** lock の全順序。r2db の全経路で昇順に取り、上位を取った後に下位を取らない: **1 per-key (idempotency) < 2 3a (application schema lock) < 3 entity (実体単位の advisory lock) < 4 count (keyed の count / budget lock) < 5 表 lock / 行 lock**。
  - DML (`transact`): per-key (`R`:1646) → lookup (`R`:1647) → **entity 共有 (sorted)** → count (`R`:1668) → `_load_catalog` (`R`:1670) → write。entity 共有は lookup の後・count の前に置く。per-key・count を取らない DML (unkeyed) も entity 共有を取る (守る条件 (1) の対象)。
  - schema (`apply_schema`): per-key (`R`:2138) → lookup (`R`:2139) → 3a (`R`:2157) → **entity 排他** → count (`R`:2161) → `_load_catalog` (`R`:2163) → 操作。
  - 根拠: entity を `R`:1670 の直前に置くと DML は per-key → count → entity となり、schema 側の 3a → entity 排他 → count と交差して 40P01 を作る (schema が entity 排他を持って count を待ち、DML が count を持って entity を待つ)。全経路で count < entity にすると、keyed DML が entity を待つ間 count を持ち続け、他の keyed 要求が count で止まる (台帳 R-102 の作業指示書 `docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` 訂正註 3 の 1、M-17 が避けた連鎖)。3a < entity なので守る条件 (4) は保たれる (3a を待つ schema 操作は entity 排他をまだ持たない)。count と entity の相対順は MitateDB (`D3`:183-190: per-key → count → 3a → 3b) と逆になる (r2db は既に 3a と count が逆。同 M-17)。
- **D-3** entity 排他を取る schema 操作は r2db の 6 操作全部 (create_entity / drop_entity / add_field / create_index / drop_index / alter_field)。名は要求から決まる対象 entity (`R`:2104 の `bind_schema_operation` が返す `bound.entity`) で取る。理由: drop_entity に無いと drop → create の間に catalog 読み済みの DML が入る窓が残る。schema 操作は稀で費用は無視できる。MitateDB の 3 操作との差は MitateDB に無い操作の分であり性質は同じ。**(監督裁定)**
- **D-4** lock の実体は `pg_advisory_xact_lock_shared(ns, hashtext(entity))` / `pg_advisory_xact_lock(ns, hashtext(entity))` で、MitateDB の `_ENTITY_LOCK_SHARED` / `lock_entities` (`MB`:259-266、`MB`:609-614) と同型で r2db に置く。名前空間の整数は r2db の既存の advisory 名前空間 (per-key `R`:206、count `R`:209、3a `R`:211) と衝突しない新しい値。DML は 1 要求 1 entity (`R`:1586) だが、helper は entity の list を sorted で取る形にする (将来の cross-entity に備え、MitateDB と同型)。`hashtext` の衝突は over-serialize になるだけで安全側。
- **D-5** `_ISOMORPHIC_TARGETS` (`RT/test_audit_query.py`:2425): 同名 helper を両 peer に置くなら `MRA` §6 の規律で登録する (集合の増減は Class D。既に D なので追加費用なし)。正規化 diff が通らない差 (r2db の connection の型・logger 名など) が残るなら、登録せず r2db 側の名前を変える案を報告に書く。**裁定は監督。**
- **D-6** 再現 test (2 cell)。土台は `RT/test_r102_schema_windows.py` の `_pair` (:77-86)・`_Stall` (:89-121)・`_run_window` (:143-182)・`_lock_waiters` (:131-140)。DML (A) を `PostgresCell._insert` の入口 (`R`:1896) で止め、同じ entity に対して (a) `alter_field` (enum の縮小) と (b) `add_field` (`nullable: false`) をそれぞれ B として完走させる形 (MitateDB の window3、`MitateDB-api/tests/test_r102_cross_cell_windows.py`:303-345 と同形)。test は (a)(b) 各 1 本。
  - 修正前: B が完走し、A の commit 後に宣言に反する行が残る (赤)。修正後: B は entity 排他で待ち、A の commit 後に B の走査 (`R`:2332-2352) / 空確認 (`R`:2270) が CONFLICT を返し、宣言に反する行は残らない (緑)。
  - 空振り禁止 (`OC` §1.5 の 32): advisory の waiter の観測件数 ≥ 1 を assert する。観測は `wait_event = 'advisory'` に限る形 (`RT/test_schema_serialization_lock.py`:40-46) による (`_lock_waiters` は lock 待ち全般を数える)。
- **D-7** 主張の書き換え。`R`:1405-1415 の docstring の「輪は無い」の前提を D-2 の全順序に書き換える (旧文は逐語で残さず書き換えてよいが、CH-ID と code-history の規律 (`tools/check_comment_provenance.py --base 1abd5e8`) に従い、訂正記録を `docs/code-history/r2db-api/postgres.md` に置く)。`CM` SI-11 r2db 節: `CM`:1534 の Status の開示を「閉じた」内容に書き換え (旧行は `security/CONTROL_MAPPING_HISTORY.md` の `## SI-11` へ逐語)、Control に entity lock の主張 (`file:line`)、Evidence に D-6 の test 2 本と変異を足す。版数行は監督。共通条件 (`conformance-tests/CONDITIONS.md`) は**今回は足さない (監督裁定)**: transaction 途中の停止は conformance の port から駆動できず、両 peer の peer-local の 2 cell test が対称の証拠になる。この点は観察として引き継ぎ書に残す。

### 1.3 却下した代替案 (`RB` §4.3 の欠点欄から逐語)

- **A 着手しない**: 「宣言に反する行が残りうる。`RM` の G-2/G-3 の「両 peer で conformance に固定」から外れた性質が 1 つ残る。運用開始後に当たると修復費用が上がる」
- **C DML 側の表 lock**: 「未存在 entity の error 経路が変わる (LOCK が先に失敗)。`LOCK TABLE` を `_load_catalog` の前に出すと、catalog で照合する前の識別子で SQL を組むことになり、`CM`:217 の主張 (identifier は `_load_catalog` で live catalog に照合してから SQL を組む) に反する。」
- **D 物理制約**: 「registry と DDL の二重真実。既存 table の migration。error code が VALIDATION でなく SERVICE_UNAVAILABLE に落ちる現状の写像を直す必要。規模 L」
- **E 楽観的再確認**: 「client に新しい CONFLICT が見え、再送の判断を client に負わせる (安全な再送は C-07 系で担保されるが、MitateDB では起きない失敗)。」
- **F application 単位の共有 schema lock**: 「無関係な entity の DML も同 application の schema 操作中は待つ (application 全体で DML と schema 操作が直列)。keyed DML は count lock を保持して 3a を待ち、schema 操作は 3a を保持して count lock を待つので輪の分析が要る (`R`:1410-1412 の前提が崩れる)」

### 1.4 依頼者判断待ち・事後報告・観察

- 依頼者判断待ちの選択肢は無い。監督裁定で置いた D-3 (6 操作) と D-7 (共通条件を足さない) は、引き継ぎ書で依頼者へ事後報告する。
- 観察 (起票しない): plan 付き DML は revision を素の SELECT で読み (`R`:1683)、entity 共有では revision は守られない (`D3` の M-18 (a) と同じ)。本件の範囲外。

## 2. Change Set Manifest

**目的**: r2db の `transact` と `apply_schema` に実体単位の advisory lock を D-2 の順で置き、DML と同じ entity の制約を変える schema 操作の重なりを閉じる。2 cell の再現 test を赤 → 緑で置き、`CM` SI-11 r2db 節の開示を閉じる。

**読む正本**: 本書 §1、`RB` §4、`D3` §2.6・D-8・:183-192、`docs/work-orders/WORK_ORDER_R102_APPLICATION_SERIALIZATION_V1.md` 訂正註 3 (:600-615 付近)、`CM`:1-77 (claim form、Update convention) と SI-11 r2db 節 (`CM`:1508-1534)、`MRA` §6 (D-5 のとき)、`OC` §1.5 (32〜40)。

| 触ってよいファイル | 触らないファイル |
|---|---|
| `R` (lock helper、`transact`、`apply_schema`、`R`:1405-1415 の docstring)、`RT/` (新 test 2〜3 本は `RT/test_r102_schema_windows.py` に足すか、同系統の新ファイル `RT/test_r120_entity_lock.py`)、`RT/test_audit_query.py` (`_ISOMORPHIC_TARGETS`、D-5 で登録する場合のみ)、`docs/code-history/r2db-api/postgres.md` (correction 記録)、`CM` (SI-11 r2db 節のみ。版数行は監督)、`security/CONTROL_MAPPING_HISTORY.md` (`## SI-11`)、本書 | `MitateDB-api/` 全部、`spec/`、`conformance-tests/`、台帳 (`RM`) |

**道具の引数** (Bash の timeout 600000、前景直列。`OC` §1.5 の 39):

- peer suite: `tools/dev/pt.py -C .claude/worktrees/r120 -- r2db-api/tests -q` (前景 1 回)。期待形: `N passed` で failed / error 0。
- `CM` の検査: `tools/dev/pt.py -C .claude/worktrees/r120 -- conformance-tests/test_control_mapping_register.py -q`。
- 変異: `tools/dev/mutate.py "$SP/r120-mutations.json" -C .claude/worktrees/r120` (spec は実装担当が `$SP` に置き、下表の M1〜M4 を各 1 entry、各 entry は対応する test 1 本だけを回す)。
- 静的: `tools/check_doc_refs.py`、`tools/public_value_scan.py`、`tools/change_class.py` (→ `D`)、`tools/check_comment_provenance.py --base 1abd5e8` と `--register`。

**完了条件と照合**

| # | 完了条件 | 照合 |
|---|---|---|
| CC-1 | D-6 (a) の test が緑 | 変異 M1 |
| CC-2 | D-6 (b) の test が緑 | 変異 M2 |
| CC-3 | D-2 の順序を検査する test 1 本が緑。形は実装担当の裁量 (接続の SQL を記録して advisory の呼び出し順を assert する形、または keyed DML と keyed schema 操作を交差させて 40P01 が出ないことを示す形)。決定的でない形は採らない | 変異 M3 |
| CC-4 | 既存の `RT/test_schema_serialization_lock.py` と `RT` 全体が緑 | 道具 (pt。集計行を §3.2 に逐語) |
| CC-5 | `R`:1405-1415 の docstring が D-2 を述べ、`tools/check_comment_provenance.py --base 1abd5e8` と `--register` が緑 | 道具 + 監査照合 (docstring の `file:line` と道具の出力行を §3.2 に逐語) |
| CC-6 | `CM` SI-11 r2db 節の書き換えが D-7 のとおりで、旧 Status 行 (`CM`:1534) が `CONTROL_MAPPING_HISTORY.md` の `## SI-11` に byte 一致で在り (`git show 1abd5e8:security/CONTROL_MAPPING.md` の 1534 行目と比較)、`test_control_mapping_register` が緑 | 変異 M4 + 監査照合 (byte 一致) |
| CC-7 | 性能: 監督が `tools/perf_baseline.py` の `mutate` / `batch` vector (`PERF-README`:138-149) を直前の main の基準と同じ引数で測り、`RM` §0.1.4 の 1 (K=1 の p50 +40% 以内、p95 +50% 以内) の内 | 道具 (perf。監督) |
| CC-8 | コードレビュー (Class D、1 起動) の指摘が残っていない | レビュー |
| CC-9 | 受け入れ監査 (1 起動) 充足 | 監査 |
| CC-10 | 完了ゲート PASS、`COLLECTION_FLOOR` は実測で更新 | 道具 (gate。監督) |
| CC-11 | 本表に照合の無い行が無い | 監査照合 |

**完了条件 → 変異** (`file:操作` → 赤になる test。test id は実装担当が §3.2 に記す)

| 変異 | 操作 | 赤になる test | 完了条件 |
|---|---|---|---|
| M1 | `R`: `transact` の entity 共有 lock の呼び出しを削る | D-6 (a) | CC-1 |
| M2 | `R`: `apply_schema` の entity 排他 lock の呼び出しを削る | D-6 (b) | CC-2 |
| M3 | `R`: `transact` の entity 共有を count (`R`:1668) の後に動かす | CC-3 の test | CC-3 |
| M4 | `CM`: 新しい Control 主張の path を存在しないファイルにする | `conformance-tests/test_control_mapping_register.py` | CC-6 |

CC-4・CC-5・CC-7〜CC-11 は変異を持たず、照合欄の道具・監査照合・レビュー・監査で閉じる (`OC` §1.5 の 40)。

**発注時の注意**: 実装担当は下請けの Agent を使わず (`OC` §1.7 の 47)、git 操作をしない。設計に無い検査・機構は実装前に報告する (`OC` §1.5 の 37)。D-5 の判断と、D-2 と現物の食い違いを見つけたときは実装せず報告する (裁定は監督)。主張 (docstring・`CM`) は変異の結果を得た後に書く (`OC` §1.5 の 34)。

## 3. 実施記録 (監督が書く)

### 3.1 訂正註と監督裁定

- **【訂正註 1 (2026-10-03、起草の報告への監督裁定)】** (a) D-5: `_ISOMORPHIC_TARGETS` には**登録しない** (登録は scanner 支援 helper 等の明示登録であり、未登録の同名 helper は許される — r2db-api/tests/test_audit_query.py:3133 付近の注記。登録すると両 peer の pin test の改名を要し Manifest と衝突する)。r2db の helper は MitateDB と別名にする (例: `_lock_entities` / `_ENTITY_LOCK_NAMESPACE`)。同型性は構造 (sorted、shared/exclusive、catalog 読みの前) で満たし、本書 §1 にその対応を 1 行で書く。(b) 名前空間の衝突: CC-12 を足す — r2db-api/tests/test_schema_serialization_lock.py:138-166 の lock id の test を新しい名前空間を含む形に拡張し (「four」→「five」)、変異 M5 (新しい名前空間の整数を既存の lock id の 1 つと同じ値にする) で赤。この test 名が `CM`:1528 の Evidence に引かれているので、改名するなら CM の主張も同じ変更セットで追随する。(c) `CM`:1520 の Control 主張 (per-key → lookup → schema lock → count lock → `_load_catalog`) は D-2 の順序 (entity 排他を schema lock の後に挿入) に書き換え、旧行は HISTORY `## SI-11` へ逐語 (D-7・CC-6 に含める)。(d) dry_run: schema 操作は dry_run でも entity 排他を取る (3a が R:2157 で dry_run でも取るのと同じ扱い)。DML は dry_run では entity 共有を取らない (write が無く窓が無い。per-key を dry_run で取らないのと同じ扱い)。unkeyed の DML は取る。(e) D-3 の 6 操作は監督裁定 (裁定の案 B の 3 操作を含む上位集合) として引き継ぎ書で依頼者へ事後報告する。(f) 開示を閉じる Status 行の HISTORY への逐語移動は枠どおり行う (form 3.0 §3 の明文は無いが、旧文を残す側に倒す)。

- **【訂正註 2 (2026-10-03、コードレビュー 1 (Class D、1 起動、指摘 5 件) への監督裁定)】** 指摘 1 (`CM` の `postgres.py` 行参照のうち `` `postgres.py`:N `` / `` `postgres.py` `:N `` 形の 12 行が未追随) → 直す: レビュー報告の対応表 (982→986、1006-1010→1010-1014、1128→1132 ×2、2081-2115→2104-2138、234-240→238-244、234→238、1897→1920、1904→1927、1110-1126→1114-1130) どおりに書き換え、3 形の全件を基点と現物で照合して報告する。指摘 2 (CC-5 の `--base` は code を変える WP では §4.1 (1) が必ず赤) → CC-5 の判定基準を「`--register` 緑、`--base 1abd5e8` の赤が §4.1 (1) の 1 行のみ、変更した comment / docstring が CH-0551 の 3 block と逐語一致 (レビュー担当が AST で確認)」に読み替える (監督裁定。道具側の扱いは観察として引き継ぎ書へ)。指摘 3 (docstring :1416・:1418 が lookup の期限切れ記録の `DELETE` (:1441) による行 lock を無視して言い切る) → 直す: :1416 の主張を advisory lock に限り lookup の DELETE を例外として明記、:1418 に「期限切れ記録を削除していない限り」の条件。連鎖そのもの (keyed 要求が lookup の DELETE で transactionid 待ちになる) は以前からあり (読解ノート [I]、MitateDB 設計 K-8 と同型)、R-120 で悪化していないので観察 (起票しない。再起票は自由)。指摘 4 (test (b) の docstring の括弧書きを test が裏付けない: 変異 R1 で緑のまま) → 直す: 「keyed の経路も通すため。順序は順序 test が固定する」に書き換える。指摘 5 (dry_run の DML は entity 共有を取らないことが `CM`:1521・docstring に無く、MitateDB は dry_run でも取る差が `CM`:1538 に無い) → 直す: 3 箇所に 1 句ずつ。CH-0551 の new block は同じ変更セットで逐語一致を保つ。修正の確認は監督が diff で行う。

### 3.2 実施と受け入れ

- **【訂正註 3 (2026-10-03)】** §0 の ID 行「完了条件 CC-1〜CC-11、変異 M1〜M4」は、訂正註 1 (b) で CC-12 と M5 を足したので「CC-1〜CC-12、M1〜M5」と読む (本文は書き換えない)。
- **差分** (commit `5dc2a0a`、main `2fdc894` を merge): `r2db-api/src/r2db_api/postgres.py` (`_lock_entities`、`_ENTITY_LOCK_NAMESPACE` 20261201、`transact` / `apply_schema`、docstring CH-0551)、`r2db-api/tests/test_r120_entity_lock.py` (新 3 本)、`test_schema_serialization_lock.py` (five)、`test_idempotency_records.py` (13→14)、`test_l1_details_vocabulary_ast_scan.py` (pin)、`docs/code-history/r2db-api/postgres.md`、`security/CONTROL_MAPPING.md` (SI-11 r2db 節、行参照 29 件の再引き; 版数行 3.18 は閉止 commit)、`security/CONTROL_MAPPING_HISTORY.md` (`## SI-11` に旧 Status 行と旧 Control 行、基点 :1534・:1520 と byte 一致)。`tools/change_class.py` → class=D。
- **照合 (逐語)**: CC-1 / M1 `M1-transact-no-entity-shared-lock expect=red got=red`、CC-2 / M2 `M2-apply-schema-no-entity-exclusive-lock expect=red got=red`、CC-3 / M3 `M3-entity-shared-after-count-lock expect=red got=red` (`'count' != 'entity-shared:notes'`)、CC-6 / M4 `M4-cm-entity-lock-control-path expect=red got=red` と、訂正註 2 の文面に対する再実行 `M4b-cm-entity-lock-control-path-current-wording expect=red got=red | 1 failed, 38 passed` (監査の観察 1 への処置)、CC-12 / M5 `M5-entity-namespace-equals-per-key-namespace expect=red got=red`; `mutate: 5 mutations, 5 as expected, restores verified 2/2 files (sha256 x2)`。修正前の赤: `pt: 2 failed, 1 deselected in 0.54s` (どちらも「B completed while A was stopped: True」)。CC-4: `pt: 1715 passed in 154.46s (0:02:34)` (r2db-api/tests)、修正後の再実行 `pt: 66 passed in 5.78s` (register + 新 test + lock 名前空間)。CC-5: `comment provenance register OK: 95 files scanned, 415 CH-IDs`、`--base 1abd5e8` の赤は `FAIL (§4.1 (1)) r2db-api/src/r2db_api/postgres.py:212 code changed` の 1 行のみ、CH-0551 の 3 block は監査担当が AST で一致を確認。CC-7: 本節上の性能表 (閾値内)。CC-8: コードレビュー 5 件 (訂正註 2)。CC-9: 受け入れ監査パケット (監督の scratchpad `audit-r120-packet.md`): CC-1〜CC-8・CC-11・CC-12 充足、CC-10 は閉止 commit の `COLLECTION_FLOOR` 5026 → 5029 で充足、証拠不足 0。CC-10: 完了ゲート (監督単独、`--label r120`) `gate: 5029 passed, 2 subtests passed in 469.86s (0:07:49)`、`judge=PASS`、`pg_database/pg_roles diff 0`、直前の main 5026 + 新 test 3 本。CC-11: 対応の無い行なし。
- **監査の観察への処置**: (1) M4 の spec が訂正註 2 の文面に当たらない → 上の M4b で再実測 (赤)。(2) CH-0551 の correction の reason が DML も「after the schema lock」と言い過ぎ → reason を直した (DML は schema lock を取らない)。設計疑義 (dry_run の DML で entity lock を取るかの peer 差) → 観察: 結果の正しさの差ではなく `CM` に開示済み。
- **監督裁定 (依頼者へ事後報告)**: D-3 の 6 操作全部に排他 (裁定の案 B の 3 操作の上位集合)、D-7 の共通条件を足さない、訂正註 1 (a) の `_ISOMORPHIC_TARGETS` 不登録、(d) の dry_run の扱い、訂正註 2 の CC-5 の読み替え。
- **最終判定**: 受け入れ。台帳 R-120 を閉じる (v1.159)。

- **CC-7 性能 (監督、2026-10-03)**: `tools/perf_baseline.py --warmup 20 --n 200` (K=1、6 plug) を main `059957f` (前) と worktree r120 (後。`PYTHONPATH` を worktree の両 `src` に向け、import 先を確認) で連続実行 (排他 suite lock 下、他の pytest 無し)。r2db の `mutate` / `batch` の PERF 行 (p50 / p95 ms、backend_calls):

| plug | op | 前 p50 / p95 / calls | 後 p50 / p95 / calls | Δ p50 / Δ p95 |
|---|---|---|---|---|
| r2db-api (in-process) | mutate | 0.216 / 0.303 / 1.00 | 0.228 / 0.308 / 1.00 | +5.6% / +1.7% |
| r2db-api (in-process) | batch | 0.867 / 1.236 / 1.00 | 0.876 / 1.253 / 1.00 | +1.0% / +1.4% |
| r2db-api-http | mutate | 1.661 / 1.750 / 19 | 1.820 / 2.197 / 20 | +9.6% / +25.5% |
| r2db-api-http | batch | 1.848 / 1.935 / 23 | 1.963 / 2.065 / 24 | +6.2% / +6.7% |
| r2db-api-socket | mutate | 4.949 / 5.128 / 19 | 5.226 / 5.385 / 20 | +5.6% / +5.0% |
| r2db-api-socket | batch | 5.145 / 5.334 / 23 | 5.379 / 5.521 / 24 | +4.5% / +3.5% |

判定: `RM` §0.1.4 の 1 (K=1 の p50 +40% 以内、p95 +50% 以内) の内側 (最大 p50 +9.6%、p95 +25.5%)。`backend_calls` の +1 (§0.1.4 の 4) は D-2 の entity 共有 lock の 1 往復 (設計どおり)。生の出力は監督の scratchpad (`perf-main.txt` / `perf-r120.txt`)、他 plug・`query` は不変の範囲 (query は lock を取らない)。
