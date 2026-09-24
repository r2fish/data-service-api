# 作業指示書 — フェーズ11 最低共通機能プロファイル (R-29 / R-23 / R-16)

## 0. 版数・位置づけ

- **v1.0 (2026-09-24)。** 基点 local main `0fee6e5`。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の **R-29 / R-23 / R-16** (規模 **L**、3 行を 1 つの変更セットで閉じる)。設計は `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` **v1.0** (決定 D-1〜D-8、却下 X-1〜X-7、依頼者裁定 §5 U-1〜U-5)。
- **変更クラス**: WP-1 / WP-2 / WP-3 = **Class C**、WP-4 = **Class D**。**項目全体は Class D** である (設計 §5 U-5 の依頼者裁定、§3 D-8、計画文書 §9 の 8)。着手時に `tools/change_class.py` を実行し、実測の分類行を報告に貼る。
- **担当 worktree**: `.claude/worktrees/laughing-feistel-31c19a` (branch `claude/laughing-feistel-31c19a`)。**他の worktree と main checkout には書かない。** Python は main checkout の `.venv` を使う。プロンプトで `export SP=<本チャットの scratchpad>` を渡す。
- **WP は直列**: WP-1 → WP-2 → WP-3 → WP-4。**各 WP は 1 commit** (監督が `tools/dev/finalize.py --no-merge --leave`)。**完了ゲート (`tools/dev/gate.py`) は WP-3 の後に監督が 1 回**、**main への merge は WP-4 の後に 1 回**。
- **契約版と条件番号は仮である** — 本書は **1.9.0 (仮)** / **C-28 (仮)** / **C-29 (仮)** / **従属判断 14 (仮)** と書く。**merge 直前に監督が main を読んで振り直す** (設計 D-7、§9)。keyset ページングの並走チャットが先に merge していれば **1.10.0 / 条件番号を 1 つずつ繰り下げた組 / 従属判断 15** へずらす (具体の番号は監督が main を読んで決める)。**実装担当は仮番号のまま実装し、自分で振り直さない。**
- **役割**: 実装担当 (`implementer`、テンプレート **2**) を WP ごとに 1 起動、**各 WP の後にコードレビュー** (`reviewer`、テンプレート **5**) 1 回、**全 WP の後に受け入れ監査** (`evidence-auditor`、テンプレート **6**) 1 回。雛形は `docs/work-orders/ROLE_PROMPT_TEMPLATES.md`。
- **実装担当への禁止** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.7 の 46・47、§1.11 の 70): git 操作 (commit / push / merge / stash)、`tools/dev/gate.py` と `tools/dev/finalize.py` の実行、root suite の実行、下請け Agent の起動、実 credential・実ホスト名・実ドメイン・実 DSN・作業機の絶対パス・traceback の記載。

## 1. 監督確定事項 (設計の写しではなく、実装に効く事実だけ)

1. **依頼者裁定 (設計 §5)**: U-1 / U-4 = **(α)**、U-2 = **(i)**、U-3 = **(a)**、U-5 = Class D の裁定文。**§6 の (β) 側の文案は採らない** (設計に記録として残っているだけである)。
2. **契約に入る英文は設計 §6 の該当 code block から逐語で複製する。言い換えない** (`docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 35・36)。**1.8.0 以前の確定文は 1 文字も動かさない。**
3. **契約 JSON は 3 複製** (`spec/data-service-api.v1.json`、`r2db-api/src/r2db_api/contract/data-service-api.v1.json`、`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json`)。**同一コミットで同一バイト。**
4. **宣言と挙動は同一コミット** (版フリップの規律、`docs/work-orders/OPERATING_CONDITIONS.md` §1.1 の 11)。**両 peer の宣言は WP-3 でだけ動かす** — WP-1 は契約側だけを動かす。
5. **設計外の拡張は実装前に監督へ上げる** (§1.5 の 37)。port の形 (WP-2 / WP-3)、契約文の変更、条件文の変更はすべてこれに当たる。**自分で決めない。**
6. **空振り禁止と変異先行** (§1.5 の 32・33・40): 完了条件 1 行につき変異 1 件。**本書の変異はすべて「候補」であり、実測して表を確定するのは実装担当である。** 赤になった test id を表に書き戻して報告する。
7. **テストの実行**は `tools/dev/pt.py` だけで行う (§1.10 の 64)。**前景・直列・`timeout` 600000 明示。** REFUSED (終了コード 75) は待つか監督へ上げる (§1.10 の 66)。
8. **新規テストファイルは `git add -N` してから** `tools/dev/pt.py` に渡す (root gate の対象外の穴を避ける既知の手順)。

---

## 2. WP-1 — 契約 1.9.0 (仮) の公表 (Class C)

### 2.1 目的

契約 1.9.0 (仮) に **common_baseline** (床) と **operation_catalog** (派生カタログの配布先) を載せ、**C-28 / C-29 (仮) の行を `declared` で置く。** 挙動は 1 行も動かさない (両 peer は 1.8.0 を宣言したままである)。

### 2.2 読むべき正本

設計 `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` の **§3 D-1 / D-4 / D-5 / D-7 / D-8**、**§6.1 / §6.2 / §6.3 (α) / §6.4 / §6.5 / §6.6**、**§15 の裁定 2・3・4**。計画文書 §9 の 8 (変更クラス)。

### 2.3 触ってよいパス

- 契約 JSON 3 複製 (§1 の 3)
- `spec/OPERATION_CATALOG.json` (**生成物。手で編集せず `tools/contract_catalog.py` で再生成する**)
- `spec/CCR_DISPOSITION.md`、`spec/CONTRACT_HISTORY.md`
- `conformance-tests/CONDITIONS.md`、`conformance-tests/CONDITIONS_HISTORY.md`
- `conformance-tests/test_contract.py`、`conformance-tests/test_operation_catalog_register.py` (**pin の更新のみ**)
- `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md`、`docs/work-orders/WORK_ORDER_PHASE11_MIN_COMMON_PROFILE_V1.md` (訂正註のみ)

**触らない**: 両 peer の `src/` (とくに `capabilities_document.py`)、両 peer の `tests/`、`conformance-tests/adapter.py`、`conformance-tests/` の C-NN テスト本体、`security/`、`tools/contract_catalog.py` (生成器の正本は動かさない。設計 X-6)、`spec/README.md`。

### 2.4 タスク

1. **契約 JSON に足す** (3 複製すべて、同一バイト): (a) `common_baseline` 節 (設計 §6.1 の JSON)。(b) `capability_status.rules` の **6 番目の要素を末尾に追加** (設計 §6.1 の text block。**1.8.0 の 5 番目は 1 文字も動かさない**)。(c) `versioning.version_binding` の 1.9.0 段落 (設計 §6.2 (1)。**角括弧を外して (b) を置く**。**件数文を書かない** — 設計 X-7)。(d) `versioning.obligations` の 1.9.0 entry (設計 §6.2 (2)、`unconditional` 2 件・`conditional` 空)。(e) `endpoints.operation_catalog` entry (設計 §6.6 の全文案。**`path` は案の `/v1/operation-catalog` をそのまま採る**。変える必要が出たら §1 の 5)。(f) `schemas.OperationCatalogDocument` と `definitions.OperationCatalogEntry` (設計 §6.6。**どちらも `additionalProperties: false`**)。(g) `capabilities` の `operation_catalog_url` の `description` を設計 §6.3 **(α) 案**に差し替える。(h) 契約自身の `contract_version` を **1.9.0 (仮)** にする。
2. **`spec/CCR_DISPOSITION.md`**: **従属判断 14 (仮)** を 1 節新設する (直前は 13 = 契約 1.8.0)。**設計 §3 の D-1 / D-4 / D-5 を指し、経緯を写さない** (設計 §6.2 (3))。あわせて **従属判断 7(A) の closed 列挙に新設 2 schema を載せる** (設計 §6.6 の v1.0 確定、§15 の裁定 4)。
3. **`spec/CONTRACT_HISTORY.md`** の `## versioning.version_binding` 節を同一変更セットで更新する (設計 §6.5 の行: Value の逐語 quote を追記後の値に差し替え / `- 従属判断 14` を足す / `Introduced in:` を累積形にする / 1.8.0 の Revision note の直後に 1.9.0 の Revision note を同じ形で書く)。**この entry は manifest で `unstripped: true` であり、live 値との完全一致が要る。**
4. **`conformance-tests/CONDITIONS.md`** に C-28 / C-29 (仮) の行を **declared** で足す (設計 §6.4 の暫定 `Status` 文案)。**`Status` を `executable` で始めない。** **Evidence 欄にはテストファイル名を `(not yet created)` 付きで書く** (設計 §15 の裁定 3。先例は `conformance-tests/CONDITIONS_HISTORY.md` の C-26 / C-27 の declared 期)。**`CONDITIONS_HISTORY.md` に `## C-28` / `## C-29` の節を同じコミットで新設する。**
5. **pin の更新** (同一変更セット): `conformance-tests/test_contract.py` の **:95** (契約版)、**:165** (`len(rules)` → 6)、**:168** (`rules[-1]` → **`rules[4]`** の index 固定。設計 §15 の裁定 2)、**:1189 / :1301** (`operation_catalog_url` の 1.7.0 逐語 pin を 1.9.0 の文言へ差し替える)、**:1414** (`assert n == 19` → **20**)。`conformance-tests/test_operation_catalog_register.py` の **:117** (19 → **20**、註の「7 + 12」も **8 + 12** にする)。**行番号は着手時に再実測する。**
6. **`spec/OPERATION_CATALOG.json` を再生成する**: `./.venv/bin/python tools/contract_catalog.py` (20 operation、`contract_version` が 1.9.0 になる)。**手で編集しない。**
7. **設計文書 v1.0 と本作業指示書を同じ変更セットに入れる** (設計 §12 の裁定 4。`tools/check_doc_refs.py` が C-28 / C-29 を dangling と判定するため)。

### 2.5 完了条件

1. 契約 JSON **3 複製が同一バイト**で、2.4 の (a)〜(h) をすべて含む。
2. `spec/OPERATION_CATALOG.json` が再生成と byte 一致し、**operation が 20 件**である。
3. `versioning.obligations` の 1.9.0 entry と `version_binding` の 1.9.0 段落が**対で存在する** (片方だけにしない)。
4. `spec/CCR_DISPOSITION.md` に**従属判断 14 (仮)** が実在し、obligations entry の `subordinate_ruling` がそれを指す。
5. `spec/CONTRACT_HISTORY.md` の `## versioning.version_binding` 節が **live 値と完全一致**する。
6. `CONDITIONS.md` の C-28 / C-29 行が **declared** で置かれ、`[history]` リンクと `CONDITIONS_HISTORY.md` の見出し集合が**過不足なく一致**する。
7. **Evidence 欄の `(not yet created)` 付きファイル名で、参照解決の検査 (`conformance-tests/test_conditions_register.py`、設計が指す :702-717 付近) が緑**である (§15 の裁定 3)。**実測した検査の test id を報告に書く。**
8. **新設 2 schema が 1.2.0 の closed 列挙に載り、列挙の検査が緑**である (§15 の裁定 4)。**検査テストの所在 (あるいは機械検査が無いこと) を実測して報告する** — 無ければその旨を監督へ上げる (§1 の 5)。
9. §2.7 の 5 ファイルの pytest が**緑**。
10. `tools/check_doc_refs.py` が **0 件** (設計文書と本書を同じ変更セットに入れた状態で)。
11. `tools/change_class.py` の実測分類行を報告に貼る。
12. **完了条件 1〜11 のうち、対応する変異または監査照合の無い行が 1 つも無い** (§1.5 の 40)。

### 2.6 完了条件 ↔ 変異 (**候補。実装担当が実測して表を確定する**)

| 完了条件 | 変異 (`file:操作`) | 赤になる test id (候補) |
|---|---|---|
| 1 | M1: `r2db-api/src/r2db_api/contract/data-service-api.v1.json` の `common_baseline.purpose` を 1 文字変える | `conformance-tests/test_contract.py::test_contract_packaged_copies_are_byte_identical` |
| 1 (h) | M2: 契約 3 複製の `contract_version` を `1.8.0` に戻す | `conformance-tests/test_contract.py::test_contract_declares_1_8_0` (1.9.0 用に改名・更新した後のもの) |
| 2 | M3: `spec/OPERATION_CATALOG.json` の 1 バイトを変える | `conformance-tests/test_operation_catalog_register.py::test_operation_catalog_regenerates_byte_identical` |
| 2 | M4: `endpoints.operation_catalog` entry を落とす (3 複製) | 同 `::test_scanner_finds_at_least_one_endpoint` (20 件 assert) と `::test_operation_catalog_regenerates_byte_identical` |
| 3 | M5: `versioning.obligations` の 1.9.0 entry を落とす (3 複製) | `conformance-tests/test_operation_catalog_register.py::test_obligations_version_set_matches_the_prose` |
| 4 | M6: obligations entry の `subordinate_ruling` を 14 → 99 にする | `conformance-tests/test_contract.py::test_versioning_obligations_subordinate_rulings_exist_in_ccr_disposition` |
| 5 | M7: `spec/CONTRACT_HISTORY.md` の `## versioning.version_binding` の Value から 1.9.0 段落を落とす | `conformance-tests/test_contract_history_register.py` の固定事項 (5) のテスト |
| 6 | M8: `CONDITIONS.md` の C-28 行から `[history](CONDITIONS_HISTORY.md#c-28)` を落とす | `conformance-tests/test_conditions_register.py` の history リンク / 見出し一致のテスト |
| 7 | M9: C-29 行の Evidence から `(not yet created)` を外す (ファイル名は未作成のまま) | 同ファイルの参照解決テスト (**実測**。赤にならなければ「(not yet created) は load-bearing でない」ことの実測として報告し、監督へ上げる) |
| 8 | M10: `definitions.OperationCatalogEntry` から `"additionalProperties": false` を外す (3 複製) | closed 列挙の検査テスト (**実測**) |
| 2.4 の 1 (b) / 5 | M11: `capability_status.rules` の 6 番目を **5 番目の前**に挿す (3 複製) | `conformance-tests/test_contract.py` の `rules[4]` index 固定 assert |
| 9 | M12: `common_baseline.rule` の credential 句を落とす (3 複製) | `conformance-tests/test_contract.py` の 1.9.0 逐語 pin (WP-1 が置く pin。**pin を置かない設計判断なら、この行は M11 に統合して報告する**) |
| 10・11 | **監査照合** — `tools/check_doc_refs.py` の出力行と `tools/change_class.py` の分類行を報告に貼り、設計 §17 に写す (§1.5 の 40) | — |
| 12 | **監査照合** — 上の表に対応の無い完了条件が 0 件であることを報告に書く | — |

### 2.7 検証コマンドと集計行の期待形

```
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- conformance-tests/test_contract.py conformance-tests/test_operation_catalog_register.py conformance-tests/test_contract_history_register.py conformance-tests/test_conditions_register.py conformance-tests/test_c11_document_conformance.py -q
tools/dev/mutate.py "$SP/p11-wp1-mutations.json" -C .claude/worktrees/laughing-feistel-31c19a
./.venv/bin/python tools/contract_catalog.py --check
./.venv/bin/python tools/check_doc_refs.py
./.venv/bin/python tools/change_class.py
```

- pt の期待形: `N passed in X.XXs` (赤 0、skip 0)。**`N` は基点からの増減を報告に書く。**
- mutate の期待形: `mutate: 12 mutations, 12 as expected, restores verified K/K files (sha256 x2), grep counts unchanged`。
- `tools/contract_catalog.py --check` は差分 0 で終了する。
- `tools/check_doc_refs.py` は `0 dangling reference(s)` で終わる。

**註**: `conformance-tests/` の C-11 系は `test_c11_document_conformance.py` と `test_c11_response_schema_conformance.py` の 2 本である (起草時の実測)。**後者は新設 schema を手書き列挙に載せない** (設計 §6.6 の裁定 5、§11)。

### 2.8 使用テンプレートと変更クラス

テンプレート **2** (実装)、レビューは **5**。**Class C。**

---

## 3. WP-2 — C-28 (仮) の scenario (Class C)

### 3.1 目的

**baseline を宣言分岐なしで 1 本で通す 12 段の scenario** を 6 adapter で緑にし、`CONDITIONS.md` の C-28 行を **executable** にする。

### 3.2 読むべき正本

設計 **§3 D-2 / D-3 / D-6**、**§7 の段の表**、**§7.1 の 1・3・4** (port の不足)、**§6.4 の C-28 行 (最終形)**、**§8.1** (SI 列)、**§11** (honest scope)。

### 3.3 触ってよいパス

- `conformance-tests/test_c28_baseline_turn.py` (**新規**)
- `conformance-tests/adapter.py` (**port v1.16 の追加のみ**)
- `r2db-api/conformance/` と `MitateDB-api/conformance/` の adapter (v1.16 の実装)
- `conformance-tests/CONDITIONS.md` (C-28 行の `Status` / `Evidence` のみ)、`conformance-tests/CONDITIONS_HISTORY.md` (`## C-28` に旧文を逐語で残す)
- 同型性表 (`_ISOMORPHIC_TARGETS`) — **対象になるかを実測してから触る** (§1.5 の 40b)

**触らない**: 契約 JSON と `spec/` (WP-1 で確定済み)、両 peer の `src/`、両 peer の `capabilities_document.py`、C-29 側のファイル、`security/`、既存 C-NN テストの本体。

### 3.4 タスク

1. **`test_c28_baseline_turn.py` を書く** — 設計 §7 の 12 段を**この順で 1 つのテスト関数**に置き、`@pytest.mark.condition("C-28")` を付け、`conftest.py` の `adapter` fixture で **6 adapter に parametrize** する。**どの段にも宣言分岐を置かない** (設計 X-2)。**`CAPABILITY_UNSUPPORTED` が返ったら赤**である。
2. **段 (6) → (7) は同じ `idempotency_key` と、段 (6) が返した `plan` をそのまま運ぶ** (設計 §7 の段 (6)(7))。**段 (8) は同 key 同 body の再送で、同じ `request_id` と行数不変**を見る。
3. **段 (9) の不等式を守る**: 返る行数 R ≤ `page.size` S ≤ `budget.result_items` B ≤ **配備が宣言する `limits.result_items`** (capability document から読む。**固定リテラルを書かない**)。**sort key は entity 内で一意**にする (tie を作らない。設計 §7 段 (9))。
4. **port v1.16 を 1 method 足す** — `order_by` と `page.size` と `budget` を **1 つの query 要求で運ぶ**新 method (既存 `select_eq` / `attempt_filter` / `query_with_budget` を置き換えない。設計 §7.1 の 1・4)。**形は実装前に監督へ上げる** (§1 の 5)。docstring に `port v1.16` と設計の節番号を書く (既存の port 註の形に倣う)。
5. **段 (1) の版 assert はまだ置かない** — 両 peer は WP-2 の時点でまだ 1.8.0 を宣言している。**版の assert (`>= 1.9.0`) は WP-3 で足す** (設計 D-2 と §7 段 (1))。baseline の実行そのものは版に依らず通る (現物の交差である。設計 D-1)。
6. **C-28 行を最終形に書き換える** (設計 §6.4 の C-28 行案)。**旧 (declared) の文は `CONDITIONS_HISTORY.md` の `## C-28` に逐語で残す** (§1.8 の 56、C-27 の先例)。
7. **SI 列は実測で確定する** — 設計 §8.1 の 5 件 (SI-05 / SI-09 / SI-10 / SI-11 / SI-14) のうち、**実在する assert が観測しているものだけ**を残す。差が出たら監督へ上げる (§1.5 の 34)。

### 3.5 完了条件

1. `test_c28_baseline_turn.py` が **6 adapter すべてで緑** (`skip` / `xfail` を使わない)。
2. **12 段すべてが観測対象を 1 件以上持つ** (空振り禁止、§1.5 の 32)。
3. **§7 の 12 変異が赤**であり、**「この段だけが赤か」を実測して表に書き戻した** (設計 §7 の最終列、§11 の 見込み 2 件の検証)。
4. port v1.16 の method が 6 adapter で実装され、**同名 helper の同型性の扱いを実測して報告した** (§1.5 の 38・40b)。
5. `CONDITIONS.md` の C-28 行が最終形で、**旧文が `CONDITIONS_HISTORY.md` に逐語で残っている**。
6. C-28 行の **SI 列が実在の assert と一致**する (§1.5 の 34)。
7. 両 peer の suite と §3.7 の conformance が緑。
8. **完了条件 1〜7 のうち、対応する変異または監査照合の無い行が 1 つも無い。**

### 3.6 完了条件 ↔ 変異 (**候補。各段 1 件。実装担当が実測して確定する**)

| 完了条件 | 変異 (peer 側を壊す。`file:操作`) | 赤になる test id (候補) / 見込み |
|---|---|---|
| 1・3 段 (1) | N1: 片 peer の `capabilities_document.py` の baseline 対象 capability を 1 つ `unavailable` にする | C-28 赤 (**C-12 / C-19 と同時**) |
| 1・3 段 (2) | N2: developer でも `create_entity` を `CAPABILITY_UNSUPPORTED` にする | C-28 赤 (C-20 と同時) |
| 1・3 段 (3) | N3: catalog の `EntityDescriptor` から `field_constraints` を落とす | C-28 赤 (C-11 / C-17 / C-20 と同時) |
| 1・3 段 (4) | N4: enum 外の値を受理して書き込む | C-28 赤 (C-20 / C-21 と同時) |
| 1・3 段 (5) | N5: 拒否の `details.field` が指す位置を 1 段ずらす | **C-28 だけが赤** (設計 §11 の見込み) |
| 1・3 段 (6) | N6: `dry_run` 分岐を外して実行する | C-28 赤 (C-22 と同時) |
| 1・3 段 (7) | N7: `plan` の digest に `dry_run` を含める | C-28 赤 (C-22 と同時) |
| 1・3 段 (8) | N8: 再送時に idempotency の記録を無視して再実行する | C-28 赤 (C-23 と同時) |
| 1・3 段 (9) | N9: `order_by` を無視する / N9': `budget` を `CAPABILITY_UNSUPPORTED` で拒否する | N9 は **C-28 だけが赤** (見込み)、N9' は C-24 と同時 |
| 1・3 段 (10) | N10: `where` を無視して全件を更新する | C-28 赤 (C-12 / C-17 と同時) |
| 1・3 段 (11) | N11: 確認句の全文一致を存在チェックに緩める | C-28 赤 (C-06 と同時) |
| 1・3 段 (12) | N12: `delete` が `affected` を返すのに行を消さない | C-28 赤 (C-12 と同時) |
| 2 | N13: 段 (9) の演算子ループの入力を空集合にする (テスト側) | C-28 が**緑のまま**なら空振り。赤になることを確認する |
| 4 | N14: 片 peer の adapter から v1.16 method を落とす | 当該 peer の plug で C-28 赤 (収集時 `AttributeError` にしない) |
| 5・6 | **監査照合** — `CONDITIONS.md` の差分と `CONDITIONS_HISTORY.md` の旧文、SI 列と assert の対応表を報告に貼り、設計 §17 に写す | — |
| 7・8 | **監査照合** — pt の集計行と、対応の無い完了条件 0 件の確認 | — |

**註**: peer を緩める変異では赤にならない段がある (段 (7) の期待は「plan 不一致が起きない」という否定形である。設計 §7)。**その段は厳しくする変異で赤にする。**

### 3.7 検証コマンドと集計行の期待形

```
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- conformance-tests/test_c28_baseline_turn.py -q
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- conformance-tests/test_c28_baseline_turn.py conformance-tests/test_c22_dry_run_and_plan.py conformance-tests/test_c23_idempotency_semantics.py conformance-tests/test_c24_request_budget.py conformance-tests/test_conditions_register.py -q
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- r2db-api/tests MitateDB-api/tests -q
tools/dev/mutate.py "$SP/p11-wp2-mutations.json" -C .claude/worktrees/laughing-feistel-31c19a
```

- C-28 単体の期待形: `6 passed in X.XXs` (6 adapter)。**1 件でも `skipped` なら完了条件 1 を満たさない。**
- mutate の期待形: `mutate: 14 mutations, 14 as expected, restores verified K/K files (sha256 x2), grep counts unchanged`。
- **`conformance-tests` 全体 (約 9 分) は 1 回だけ前景で回してよい** (`timeout` 600000)。root suite は回さない (§1.6 の 42)。
- **`conformance-tests/README.md` の `COLLECTION_FLOOR` は監督が完了ゲートで更新する** — 実装担当は触らない。

### 3.8 使用テンプレートと変更クラス

テンプレート **2**、レビューは **5**。**Class C。**

---

## 4. WP-3 — 両 peer の 1.9.0 (仮) 宣言と派生カタログの配布 (Class C)

### 4.1 目的

**両 peer が 1.9.0 (仮) を宣言し、`operation_catalog_url` を宣言し、その URL で契約の派生カタログを byte 一致で配る。** C-29 (仮) を executable にし、C-28 の段 (1) に版の assert を足す。**宣言と挙動は同一コミットである。**

### 4.2 読むべき正本

設計 **§3 D-4 / D-5**、**§6.3 (α)**、**§6.4 の C-29 行 (最終形と honest limits)**、**§6.5 の表**、**§6.6**、**§7.1 の 2**、**§8.2**、**§11**。

### 4.3 触ってよいパス

- `r2db-api/src/r2db_api/capabilities_document.py`、`MitateDB-api/src/mitatedb_api/capabilities_document.py` (**data 面の宣言のみ**)
- 両 peer の HTTP 面 (`http.py` 等) — `GET /v1/operation-catalog` の実装
- `r2db-api/src/r2db_api/contract/OPERATION_CATALOG.json`、`MitateDB-api/src/mitatedb_api/contract/OPERATION_CATALOG.json` (**新規。`spec/` の複製**)
- `conformance-tests/test_c29_operation_catalog_url.py` (**新規**)、`conformance-tests/adapter.py` (**port v1.17**)、両 peer の `conformance/` adapter
- `conformance-tests/test_operation_catalog_register.py` (再生成一致を **3 複製比較**に拡張)
- `conformance-tests/test_c28_baseline_turn.py` (段 (1) の版 assert の追加のみ)
- `conformance-tests/CONDITIONS.md` / `CONDITIONS_HISTORY.md` (C-29 行と `## C-29`)
- 両 peer の `tests/` のうち **data 面の契約版 pin** (実測して列挙する)

**触らない**: 契約 JSON と `spec/` (WP-1 で確定済み)、**両 peer の control plane の宣言値** (`control_plane.py`。本設計は触れていない。必要と判断したら §1 の 5 で監督へ上げる)、`security/`、`tools/contract_catalog.py`。

### 4.4 タスク

1. **両 peer の data 面の `contract_version` を 1.9.0 (仮) にする。** **baseline のための status 変更は 1 つも無い** (現物の交差である。設計 §6.5)。
2. **`operation_catalog_url` を宣言に足す。** **値は配備側 (config / composition root) から入れる** — **コードに実ホスト名・実ドメインを書かない。** conformance adapter では**合成 URL** を与える (設計 §6.4 の honest limit)。
3. **`GET /v1/operation-catalog` を両 peer に実装する** — **path は契約 `endpoints.operation_catalog` の値に従う。** 認証は `GET /v1/capabilities` と同じ (runtime / developer)。**無認証の面を作らない** (設計 §8.2)。
4. **`contract/OPERATION_CATALOG.json` を両 peer に同梱**し、**3 複製を同一バイト**にする。`conformance-tests/test_operation_catalog_register.py` の**再生成一致テストを 3 複製比較に拡張する** (設計 D-5)。**package data の設定 (`pyproject.toml` の `contract/*.json`) が新ファイルを拾うかを実測して報告する** (設計 §13.1 の疑義 5)。
5. **`test_c29_operation_catalog_url.py` を書く** — 二段 (設計 §6.4 / §7.1 の 2): **(i) 6 plug すべて**で、peer 自身が `operation_catalog` operation に対して返す本文を **port v1.17 `operation_catalog_document()`** で取り、同梱カタログと **byte 一致**すること、および `conformance-tests/schema_check.py` の `assert_valid` で `schemas.OperationCatalogDocument` に適合すること。**(ii) `transport_kind == "socket"` の plug** では、**宣言された `operation_catalog_url` を実際に dial** して同じ本文を得ること (**非空: socket plug ≥ 1**)。**宣言 URL が `surfaces.data.base_url` 配下であることは検査しない** (設計 D-5)。
6. **C-28 の段 (1) に版の assert を足す** (`contract_version` が 1.9.0 (仮) 以上)。**`operations` の非空は assert しない** (設計 §7 段 (1))。
7. **C-29 行を最終形に書き換え**、旧 (declared) 文を `CONDITIONS_HISTORY.md` の `## C-29` に逐語で残す。
8. **両 peer の data 面の 1.8.0 pin を実測で列挙して更新する** (起草時の実測では r2db `tests/test_audit_query.py` / `test_denial_details_and_request_id.py` / `test_foundation.py`、MitateDB `tests/test_audit_query.py` / `test_http.py` / `test_denial_details_and_request_id.py`:522 等。**着手時に再実測する**)。**control plane の pin は動かさない** (§4.3)。

### 4.5 完了条件

1. 両 peer が **1.9.0 (仮)** を data 面で宣言し、**両 peer の suite が緑**。
2. `operation_catalog_url` が両 peer の capability document に載り、**その値が指す operation が実際に配る**。
3. `test_c29_operation_catalog_url.py` が **6 adapter すべてで緑**、**(ii) の socket 段が 1 plug 以上で実走**する (空振り禁止)。
4. 配られた本文が `schemas.OperationCatalogDocument` に適合する。
5. `OPERATION_CATALOG.json` **3 複製が同一バイト**で、再生成一致テストが 3 複製を比較する。
6. C-28 が段 (1) の版 assert 付きで **6 adapter 緑**。
7. C-29 行が最終形で、旧文が `CONDITIONS_HISTORY.md` に逐語で残っている。
8. package data の実測結果を報告した (監査照合)。
9. **完了条件 1〜8 のうち、対応する変異または監査照合の無い行が 1 つも無い。**

### 4.6 完了条件 ↔ 変異 (**候補。実装担当が実測して確定する**)

| 完了条件 | 変異 (`file:操作`) | 赤になる test id (候補) |
|---|---|---|
| 5・3 (i) | O1: `r2db-api/src/r2db_api/contract/OPERATION_CATALOG.json` の 1 バイトを変える | C-29 の (i) が **in-process plug と socket plug の両方**で赤、3 複製一致テストも赤 |
| 3 (ii) | O2: socket plug が dial する経路の本文を 1 バイト変える (片 peer の HTTP 応答側) | C-29 の (ii) が socket plug で赤 (**(i) が赤にならない形で実測する**) |
| 2 | O3: 宣言 `operation_catalog_url` を別 path に向ける | C-29 の (ii) 赤 |
| 2 | O4: `operation_catalog_url` の宣言を落とす | C-29 赤 (**分岐が空を通って緑にならないことの確認**) |
| 6・1 | O5: 片 peer の宣言版を 1.8.0 に戻す | C-28 の段 (1) 赤 (+ 版 pin のテスト赤) |
| 4 | O6: 配る本文の top-level に余分なキーを 1 つ足す | C-29 の `schema_check` 赤 (closed schema) |
| 3 (非空) | O7: `transport_kind == "socket"` の plug を 0 件に見せる (テスト側の抽出条件を壊す) | 非空 assert が赤 |
| 8 | **監査照合** — `pyproject.toml` の package data の実測 (`contract/*.json` が新ファイルを含むか) を報告に貼り、設計 §17 に写す | — |
| 9 | **監査照合** — 対応の無い完了条件 0 件の確認 | — |

### 4.7 検証コマンドと集計行の期待形

```
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- conformance-tests/test_c29_operation_catalog_url.py conformance-tests/test_c28_baseline_turn.py -q
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- conformance-tests/test_operation_catalog_register.py conformance-tests/test_contract.py conformance-tests/test_conditions_register.py -q
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- r2db-api/tests MitateDB-api/tests -q
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- conformance-tests -q
tools/dev/mutate.py "$SP/p11-wp3-mutations.json" -C .claude/worktrees/laughing-feistel-31c19a
```

- C-29 の期待形: `6 passed in X.XXs`、C-28 と合わせて `12 passed`。
- 両 peer suite の期待形: `N passed in X.XXs` (**赤 0**。基点からの増減を報告に書く)。
- `conformance-tests` 全体は **1 回だけ**前景で回す (約 9〜10 分、`timeout` 600000)。
- mutate の期待形: `mutate: 7 mutations, 7 as expected, restores verified K/K files (sha256 x2), grep counts unchanged`。

### 4.8 使用テンプレートと変更クラス

テンプレート **2**、レビューは **5**。**Class C。** **宣言と挙動が同一コミットであること**を commit 前に監督が確認する (§1 の 4)。

---

## 5. WP-4 — 記録 (Class D)

### 5.1 目的

**証拠と台帳と引き継ぎを閉じる。** コードと契約は 1 バイトも動かさない。

### 5.2 読むべき正本

設計 **§5 U-5 の裁定 (逐語)**、**§8.1 / §8.2 / §8.3**、**§16**、**§17**。`security/CONTROL_MAPPING.md` 冒頭の形式 3.0 の Claim form。計画文書 §0.1.1 / §0.1.3 / §8、`docs/work-orders/OPERATING_CONDITIONS.md` §1.16 の 78 (記録の置き場と回転)。

### 5.3 触ってよいパス

- `security/CONTROL_MAPPING.md`
- `docs/design/ROADMAP_POST_PHASE7_V1.md` (§0.1.1 / §0.1.3 / §8 / 版数ログ)
- `docs/design/PHASE11_MIN_COMMON_PROFILE_V1.md` (**§17 の実施記録のみ**。本文の決定は動かさない)
- `docs/work-orders/HANDOVER_<日付>*.md` (**新規**)
- `docs/archive/` (版数ログと引き継ぎ書の回転、§1.16 の 78)

**触らない**: `spec/`、契約 JSON、`conformance-tests/`、両 peer の `src/` と `tests/`。

### 5.4 タスク

1. **`security/CONTROL_MAPPING.md`**: 設計 §8.1 / §8.2 が挙げる **既存 SI の Common 節の Evidence** に、**テスト名を citation とする 1 行 (300 文字以内)** を足す (C-28 = SI-05 / SI-09 / SI-10 / SI-11 / SI-14 のうち**実測で確定した列**、C-29 = SI-10)。**Control 主張は足さない。** **Version 行を 3.1 → 3.2 に上げる。** **新しい Security Invariant を足さない** (依頼者裁定 U-5)。
2. **計画文書 §8** の **R-29 / R-16 / R-23** 行に**閉止の追記**を書く (日付・契約版・条件番号・行は消さない。§1.8 の 56)。
3. **計画文書 §0.1.1 の G-2 / G-3 行**の契約版 (→ 1.9.0 仮) と条件数 (28 → **30**) を更新し、**§0.1.3 を再実測**する。
4. **設計 §16 の 3 件を新規起票する** — 番号は **merge 直前に main の台帳を読んで振る**。各行に**規模 L とその理由・着手条件**を書く (設計 §16 の表から複製する)。
5. **版数ログの回転** (§1.16 の 78): 台帳の版数行は 5 行を残し、6 行目以降を `docs/archive/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ移す。**引き継ぎ書も最新 2 件を超えた分を `docs/archive/` へ回す。**
6. **引き継ぎ書を書く** (`docs/work-orders/HANDOVER_<日付>_<名>.md`、雛形は `ROLE_PROMPT_TEMPLATES.md` §7)。**依頼者裁定 5 件と、レビュー・監査の指摘の裁定表を全件載せる** (§1.15 の 77、計画文書 §9 の 14)。**設計 §6.4 の v0.2 註が残した観察 (既存行の `four adapters` の陳腐化) を裁定表に載せる。**
7. **設計 §17 に完了ゲートの集計行と各 WP の commit・集計行・変異表の所在を写す** (§1.5 の 40 の照合対象の逐語記録)。

### 5.5 完了条件

1. `CONTROL_MAPPING.md` の Version が **3.2** で、C-28 / C-29 の Evidence 行が Common 節にあり、**`conformance-tests/test_control_mapping_register.py` が緑**。
2. 台帳の R-29 / R-16 / R-23 行に閉止の追記があり、**行を 1 つも消していない**。
3. G-2 / G-3 行の契約版と条件数が更新され、§0.1.3 が再実測されている。
4. 新規起票 3 件が台帳に載り、**規模 L と理由と着手条件**を持つ。
5. 版数ログと引き継ぎ書の回転が済んでいる (§1.16 の 78)。
6. 引き継ぎ書に**依頼者裁定 5 件の逐語**と**指摘の裁定表 (全件)** がある。
7. 設計 §17 が埋まっている (完了ゲートの集計行を含む)。
8. `tools/check_doc_refs.py` が **0 件**。
9. **完了条件 1〜8 のうち、対応する変異または監査照合の無い行が 1 つも無い。**

### 5.6 完了条件 ↔ 変異 (**候補**)

| 完了条件 | 変異 (`file:操作`) / 照合 | 赤になる test id (候補) |
|---|---|---|
| 1 | P1: C-28 の Evidence 行から citation (テスト名) を落とす | `conformance-tests/test_control_mapping_register.py` の citation 要求 |
| 1 | P2: Version 行を 3.1 に戻す | 同 register の Version 規約のテスト (**実測**。赤にならなければ監査照合に落とし、その旨を報告する) |
| 2・3・4・5・6・7 | **監査照合** — 差分と、引き継ぎ書・設計 §17 の該当節を報告に貼る | — |
| 8 | **監査照合** — `tools/check_doc_refs.py` の出力行 | — |
| 9 | **監査照合** — 対応の無い完了条件 0 件の確認 | — |

### 5.7 検証コマンドと集計行の期待形

```
tools/dev/pt.py -C .claude/worktrees/laughing-feistel-31c19a -- conformance-tests/test_control_mapping_register.py conformance-tests/test_conditions_register.py -q
tools/dev/mutate.py "$SP/p11-wp4-mutations.json" -C .claude/worktrees/laughing-feistel-31c19a
./.venv/bin/python tools/check_doc_refs.py
```

- pt の期待形: `N passed in X.XXs`。mutate の期待形: `mutate: 2 mutations, 2 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged`。

### 5.8 使用テンプレートと変更クラス

テンプレート **2**、レビューは **5**、受け入れ監査は **6**。**Class D** (依頼者裁定の逐語記録を含む。設計 §5 U-5)。

---

## 6. レビューと受け入れ

- **コードレビュー** (テンプレート **5**) を **各 WP の後に 1 回**。準拠: 設計 §3・§6・§7・§8 と本書 §1。**指摘は 1 件ずつ 起票 / 既知の穴 / 観察 に監督が裁定し、引き継ぎ書の裁定表に全件残す** (§1.15 の 77)。
- **受け入れ監査** (テンプレート **6**) を **全 WP の後に 1 回**。材料: 各 WP の実装報告、`pt` / `mutate` の log、コードレビュー結果、完了ゲートの集計行。**「主張 vs 実測」を独立項目として突合する** (§1.5 の 34)。
- **完了ゲート**: `tools/dev/gate.py -C .claude/worktrees/laughing-feistel-31c19a --label p11` を **WP-3 の後に監督が単独で 1 回**。**前 = `4022 passed, 2 subtests passed in 486.51s` (label r105b)。** 壁時計の増分を設計 §17 に記録する (P-8。**目標値は置かない**)。
- **merge** は WP-4 の後に 1 回。**merge 直前に監督が main を読み、契約版・条件番号・従属判断番号・起票番号を振り直す** (設計 D-7、§9)。

## 7. 記録 (統合時に監督が埋める)

### 7.1 訂正註と監督裁定

(本文は書き換えず、ここに訂正註を追記する。§1.8 の 57)

**【訂正註 2026-09-24 (監督裁定 1、WP-1 着手時の実測)】 `conformance-tests/test_contract.py`:1103 の裸 `assert "atomic_mutation" not in version_binding` は 1.6.0 段落に限定する。** 実測: 1.9.0 (仮) の `version_binding` 段落 (設計 §6.2 (1)、設計レビュー 1 指摘 5 の逐語文) は `atomic_mutation` を正当に名指すので、この裸 assert が赤になる (`test_contract_pins_the_requester_finalized_1_6_0_prose`)。assert の本来の意図は直前のコメントどおり「D-3(vii) の upsert 追補を 1.6.0 の `version_binding` 段落へ重複挿入しない」ことである。**裁定**: `version_binding` から 1.6.0 の段落 (`Only an implementation declaring 1.6.0` で始まり次の `Only an implementation declaring` の直前まで) を切り出し、その部分文字列に対して `"atomic_mutation" not in` を assert する形に改め、失敗メッセージと「1.9.0 の段落は `common_baseline.capabilities` の列挙として `atomic_mutation` を正当に含む」旨のコメントを付ける。:1098 の `row_addressability` の assert は 1.9.0 段落がその語を含まないので触らない。1.6.0 の pin 文字列 (`PIN_1_6_0_*`) は 1 文字も変えない。§2.3 の「pin の更新のみ」の範囲内。

**【訂正註 2026-09-24 (監督裁定 2、設計 §15 裁定 3 の前提の実測結果)】 declared 期の C-28 / C-29 (仮) 行の Evidence 欄には未作成のテストファイル名を書かない。** 実測 (実装担当): `conformance-tests/test_conditions_register.py` は backtick 付きの `test_*.py` 参照を実ファイルへ解決し (未作成なら `file not found` で赤)、backtick 無しの `test_` 語を naked token として赤にする (`test_conditions_md_has_no_test_name_token_outside_backticks`)。C-26 / C-27 の declared 期の先例 (`(not yet created)` 付き) は参照解決の検査 (main `2365955`) が入る前のものであり、現行の検査器には両立する書式が無い。**裁定**: 検査器は変えない (§1.12 の 72。製品欠陥が抜けた実例が無い)。declared 期の Evidence 欄は証拠の形 (C-28 = 12 段の scenario、6 adapter、C-29 = port `operation_catalog_document()` の byte 一致 + socket plug の実 dial) を散文で書き、テストファイル名は WP-2 / WP-3 で `executable` にするときに backtick 付きで書く。`CONDITIONS_HISTORY.md` の `## C-28` / `## C-29` も同じ書式にする。§2.5 の完了条件 7 は「Evidence 欄にファイル名が無く、`test_conditions_register.py` の全検査が緑」に読み替え、§2.6 の M9 は「C-28 行の Evidence に backtick 無しの `test_c28_baseline_turn.py` を書き込む → `test_conditions_md_has_no_test_name_token_outside_backticks` が赤」に差し替える。

**【訂正註 2026-09-24 (監督裁定 3、§2.5 の完了条件 8)】 従属判断 7(A) の closed 列挙に機械検査は無い (実装担当の実測: `test_c11_response_schema_conformance.py` の手書き列挙のみで、`spec/CCR_DISPOSITION.md` の 7(A) 散文を読むテストは無い)。** **裁定**: 新しい検査器は足さない (§1.12 の 72)。完了条件 8 は監査照合に落とし、7(A) の追記行の `file:line` と、新設 2 schema が `additionalProperties: false` である `spec/data-service-api.v1.json` の行を報告に貼って設計 §17 に写す。§2.6 の M10 は監査照合に変え、`additionalProperties: false` の動的な効力は WP-3 の O6 (余分なキーで `schema_check` が赤) が持つ旨を表に註記する。

**【訂正註 2026-09-24 (監督、観察)】 `tools/dev/pt.py` に §2.7 の 5 ファイルだけを渡すと `test_conditions_register.py::test_every_executable_condition_has_a_marked_test` が赤になる。** 同テストの docstring どおり `conformance-tests/` 全体の収集以外では意味を持たない見かけ赤であり、回帰ではない。WP-1 の判定は同テストを除いた集計行で行い、実物は WP-2 の `conformance-tests` 全体の 1 回 (§3.7) と完了ゲートで確認する。

**【訂正註 2026-09-24 (監督裁定、着手時の実測)】 control plane の宣言版 — WP-3 で両 peer の control plane も同一コミットで 1.9.0 (仮) に上げる。** 実測 (explorer の読解調査。要点は本註に記す): (1) 両 peer の control plane は **すでに 1.8.0** を宣言している (`r2db-api/src/r2db_api/control_plane.py`:633、`MitateDB-api/src/mitatedb_api/control_plane.py`:1595。引き継ぎ書 `HANDOVER_20260924_FABLE7.md` §3 の「MitateDB = 1.7.0」は誤記)。(2) `conformance-tests/test_c19_client_self_sufficiency.py`:258 は data 面と control 面の `contract_version` の一致を 6 plug 全部で assert する — data 面だけを 1.9.0 にすると C-19 が赤になる。1.7.0 / 1.8.0 の先例も両面を同一コミットで上げている (両 `control_plane.py` の経緯コメント)。(3) control 面の `contract_version` で分岐する conformance は `test_c09_audit_evidence.py`:206-216 の下限判定 (`< 1.5.0` 系) のみで、1.9.0 で新たに掛かる検査は無い。C-25 (3) / C-06 の版分岐は data 面の文書だけを読む。(4) 1.9.0 の義務 (a) (設計 §6.2 (1)) は**配備 (implementation) が data 面で提供する操作の床**であり、control 面の文書 (`capabilities` = `control_plane` / `audit_query` の 2 キー) は 1.6.0〜1.8.0 の conditional 義務と同じく対象外 — 「宣言していない」は「`unavailable`」ではない。control 面の `capabilities` は変えない。(5) 義務 (b) の `operation_catalog_url` は **配備単位の宣言** (`surfaces` と同じ性質) であり、`CapabilityDocument` schema は両面共通なので、**control 面の文書にも同じ値を載せる** (`surfaces` と同じ経路で composition root から与える。C-19 が両面に `surfaces` を要求するのと同じ形。control credential の保持者にとって discovery であり access ではない — `surfaces.data` と同じ姿勢)。C-29 (仮) の検査対象は設計どおり data 面のまま (両面の値の一致は peer 側 tests に 1 assert ずつ置く)。(6) 帰結として WP-3 の「触ってよいパス」に両 peer の `control_plane.py` (宣言値と `operation_catalog_url`)、control 面の composition root (config 配線)、control 面の 1.8.0 pin (r2db `tests/test_control_plane_service.py`:1808、`tests/test_audit_query.py`:1968・:3783、MitateDB `tests/test_control_plane_service.py`:574、`tests/test_audit_query.py`:1709・:1739・:1751、`tests/test_denial_details_and_request_id.py`:536。着手時に再実測) を加え、§4.3 の「触らない: 両 peer の control plane の宣言値」と §4.4 の 8 の「control plane の pin は動かさない」は本註で上書きする。変異 O5 は data 面・control 面のどちらを戻しても赤 (C-19:258 または C-28 段 (1)) になることを実測する。

### 7.2 実施と受け入れ

| | 記録 |
|---|---|
| WP-1 | |
| WP-2 | |
| WP-3 | |
| WP-4 | |
| 完了ゲート | |
| コードレビュー / 受け入れ監査 | |
