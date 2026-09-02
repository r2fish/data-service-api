# フェーズ4 作業指示書 — application-plane 耐久 audit sink + audit_query

- 版数: v1.2 (2026-09-02。v1.0 = 起草。v1.1 = 起草時の疑義 8 件への監督裁定を反映。v1.2 = 追加裁定 2 件を反映 — 全体 vacuity guard の要求を「control surface を持つ登録済み adapter の全数 PROVIDED」へ強化 (xfail 解除が最後の flip に束縛される)、`CONTROL_MAPPING.md` SI-08 行の `audit_requests_per_minute` 追記を WP-4 スコープへ追加)。旧 v1.1 註 = 起草時の疑義 8 件への監督裁定を反映 — vacuity guard の 2 段構え + xfail(strict) / adapter の declare-first 規律と `SurfaceAbsent` の意味拡張 / `audit_requests_per_minute` 専用窓の本フェーズ実装 / port メソッド名 `audit_query` の確定 / `CONFORMANCE_ADAPTER_V1.md` の port v1.8 追随 / MitateDB runbook 宛先の確定 / version_binding 義務の条件付き化)
- 正本設計: `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (v1.4)。**本書は WP 分割と発注のみを扱う** — 決定 (D-1〜D-11 / P4-D1〜P4-D5) の根拠・却下案・具体 DDL は設計文書が正本であり、本書はそれを重複させない
- 体制: Fable 監督/設計/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー/証拠監査
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260901_FABLE.md` (第9次。フェーズ3.5 完了時点、root suite 1292 passed / 0 failed / 0 skipped)

---

## 1. 前提と裁定要約

### 1.1 依頼者裁定 (2026-09-02、確定。設計 §5 の U-1〜U-5 に対応)

| 記号 | 決着 | 実装上の帰結 |
|---|---|---|
| **P4-D1** | 監査行の置き場所 = **platform DB の `application_audit`** (U-1(a)) | cross-database tx を諦め、D-2 の「commit 前 1 行 + outcome 意味論」で受ける。deprovision 後も証拠が残り、`audit_query` は単一 DB で完結する |
| **P4-D2** | N-1 の記録方式 = **commit 前 1 行 + outcome 意味論 + commit 失敗時の `error` 行** (U-2(a)) | fail-closed 類はデータ commit の**前**に耐久 INSERT + commit。データ commit が失敗したら (プロセス生存下では必ず) 同一 `request_id` の `outcome="error"` 行を耐久記録する。これも fail-closed 類 |
| **P4-D3** | denial = **合体 (coalescing) 方式** (U-3(c')) | 耐久対象 denial を範囲限定した上で `(application_id, actor_id or "unknown", operation, reason_code)` を鍵に窓 W=60s で合体、窓あたり 1 行 (`count` 列に発生回数)。data-plane に新しい pre-auth rate window は**作らない** |
| **P4-D4** | 契約 **1.4.0 を本フェーズで一括出荷** (U-4(a)) | 候補 8 件を単一の 1.4.0 束として WP-1 で出荷し、`spec/CCR_DISPOSITION.md` に**従属判断 9** として記録する。前例は従属判断 8 (1.3.0 の 4 件一括) |
| **P4-D5** | ordinary data-operation 成功 event = **両 peer で揃える (記録する)** (U-5(b) の「両方記録する」) | MitateDB に query/insert/update 成功の emit サイトを新設する。r2db は現行の query/mutate/catalog allow 記録を buffer 経由の耐久化へ接続する。これにより設計 §9.2 の性質 3 (overflow alert) が**両 peer とも実 emit 経路から検証可能**になる |

### 1.2 依頼者の設計原則 (設計 §2 末尾、判断基準)

1. **今やれることは今のうちにやる** — 先送りしない。
2. **設計・実装はシンプルに** — 目先の問題解決だけの措置を行わない。
3. **制約・制限で回避しない** — 難所を機能の制限で迂回しない。
4. **誇れる成果物であること**。

この 4 原則は各 WP のレビュー基準でもある。とくに原則 3 は本書 §6 の禁止事項「制約・制限の追加で問題を回避しない」と対になっている — 必要な bound は設計に書かれたもの (行長 CHECK、1 操作 1 行、合体窓 W、buffer 容量、timeout) のみであり、実装が困難を回避するために新しい上限・拒否経路・機能制限を足すことは禁じる。

### 1.3 本フェーズの成果物 (全 WP 完了時点で真になること)

- 両 peer の application-plane で、fail-closed 類の event が platform DB へ**耐久記録**され、記録できなければ操作が成立しない。
- 通常 data-operation 成功 event が bounded buffer 経由で耐久記録され、溢れは黙って捨てられず alert 行になる。
- `audit_query` が control ホスト上で**実際に動く** (2 パス両建て、control/audit credential 認証、不透明 cursor による全順序ページング)。
- 共通 suite で **C-09 と C-11 が executable** になり、`AuditResult`/`AuditQueryRequest` の zero-coverage が解消する。
- 契約 **1.4.0** が公開され、両 peer が同一コミットで `contract_version` を 1.4.0 へ flip する。
- 設計 §9.2 の **11 性質**が、本書 §5 の対応表どおりに実測で固定される。

---

## 2. WP 分割 (依存順)

| WP | 担当 | 内容 | 公開面への影響 |
|---|---|---|---|
| **WP-0** | 監督 | 設計 v1.4 (P4-D1〜D5 反映) と本作業指示書のコミット | なし |
| **WP-1** | Sonnet 実装 → Opus レビュー | 契約 **1.4.0** (候補 8 件 + `versioning.version_binding` 追記 + 従属判断 9) + 共通 suite (C-11 の `AuditResult`/`AuditQueryRequest` executable 化、C-09 executable 化、port **v1.8**) | **あり** (契約公開) |
| **WP-2** | Sonnet 実装 → Opus レビュー | **r2db-api**: migration 0007 + 耐久 sink/読み手ペア + pre-commit hook + 振り分け + 合体 denial + buffer/alert + `audit_query` + 宣言 + **`contract_version` 1.4.0 flip** | **あり** (capability flip + 版数宣言) |
| **WP-3** | Sonnet 実装 → Opus レビュー | **MitateDB-api**: migration 0005 + 13 列 emitter 新設 + commit の try 内移設 + P4-D5 の emit 追加 + 同上一式 + **`contract_version` 1.4.0 flip** | **あり** (capability flip + 版数宣言) |
| **WP-4** | Opus 起草 → 監督 | 記録整理: CONTROL_MAPPING / CONDITIONS / 両 peer runbook / 配備構成図 / 台帳 / 設計文書の記録節 / ハンドオーバー | なし |

**依存順の根拠**: 契約と共通 suite を先に置く (WP-1) → 各 peer が「宣言が真になる」形で実装と flip を行う (WP-2 → WP-3) → 記録を最後に整える (WP-4)。WP-3 は WP-2 の対称実装であり、**WP-2 のレビュー裁定を発注時点で織り込む** (フェーズ3.5 の教訓: 対称実装は前週レビューの裁定を最初から要求すると指摘が縮む)。

### 2.1 分割の許可 (監督の許可なく行ってよい唯一の分割)

WP-2 / WP-3 が単一コミットとして大きすぎる場合、以下の 2 分割のみ許可する。それ以外の分割は監督の許可を要する。

- **(a) 耐久 sink + hook + 振り分け + denial/buffer/alert** — migration、sink ペア、pre-commit hook、振り分け規則、合体 denial、bounded buffer + overflow alert、書き手接続の timeout 強制まで。**この時点では宣言を変えない** (`audit_query` は `unavailable` 宣言のまま、`contract_version` は 1.3.0 のまま)。
- **(b) `audit_query` + 宣言 + flip** — 読み手ペア、control_http の 2 パス、audit role 許可、`control_capabilities` 宣言、`contract_version` 1.4.0 flip。

**flip は必ず (b) の単一コミットに含める** — 宣言が真になる挙動と宣言を同一コミットに束ねる version_binding 規律 (フェーズ3.5 WP-4/WP-5 の前例) を崩さない。(a) を先に出す場合、(a) のコミット時点で「宣言 unavailable ↔ 実挙動」が矛盾しないこと (= (a) は公開面の宣言を一切変えないこと) を完了条件に含める。**最後の flip = WP-3(b) には、全体 vacuity guard の `xfail` 削除を同一コミットで含める** (WP-1 補則 2 / 監督裁定 1)。

---

## 3. 各 WP の発注

### WP-0 契約・設計の確定 (監督が実施。記載のみ)

- **目的**: 依頼者裁定 P4-D1〜P4-D5 を設計 v1.4 として確定し、本作業指示書とあわせて main へ入れる。
- **変更対象**: `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` (§5 を確定形へ、§2 末尾に設計原則を記録)、`docs/work-orders/PHASE4_DURABLE_AUDIT_SINK_WORK_ORDER.md` (本書)。
- **完了条件**: 設計文書に「U-x 決着待ち」の記述が残っていないこと。本書の WP 構成と設計 §10 (スコープ外) が矛盾しないこと。
- **テストコマンド**: 文書のみのため root suite の基準値確認のみ (`./.venv/bin/python -m pytest -q`、1292 passed / 0 failed / 0 skipped)。
- **使用テンプレート**: なし (監督実施)。

---

### WP-1 契約 1.4.0 + 共通 suite (C-09 / C-11 executable 化、port v1.8)

#### 目的

契約側の未定義部分を 1.4.0 として一括確定し、共通 suite に `audit_query` を観測する経路を作る。**この WP は peer の挙動を変えない** — 全 adapter は「audit_query を提供していない」という現状の真の宣言のまま、C-09/C-11 の分岐を実行する。

#### 変更対象

**契約 (単一コミット内、候補 8 件)**

- `spec/data-service-api.v1.json` — `contract_version` を **1.4.0** へ。8 件は設計 §5 U-4 の列挙どおり:
  1. `AuditQueryRequest.after` の意味論 = **不透明 cursor** (`recorded_at`/`plane`/`event_id` を encode)。各 event の `cursor` フィールドで受け渡す。decode 不能・不正な cursor は `VALIDATION_FAILED`。cursor は同一フィルタ条件下でのみ有効。
  2. 順序 = `(recorded_at, plane, event_id)` の全順序。
  3. `plane` フィールド (`"control"` | `"application"`) の追加 (`events[]` は開放済みのため additive)。
  4. 「`event_class` は各実装が宣言する語彙である」旨の文言化 (契約に enum を作らない — D-7)。
  5. audit role の `audit_query` 許可と `control_plane.authority` の 3 endpoint 限定記述との文言整合。
  6. `audit_events` 予約 collection 名の文書化 (台帳の既存項目)。
  7. `audit_query` の endpoint 分類の整理 — `endpoints` から `control_endpoints` へ移し、パスを `/control/v1/audit/query` とする。移行期として `/v1/audit/query` を **1 minor の間 alias** として残す旨を明記。
  8. `audit_requests_per_minute` limit class の新設 (`limits.classes` の共通語彙への追加)。**繰延べない** — 実体は WP-2(b) / WP-3(b) で `audit_query` 両パス専用の pre-auth 固定窓として実装・宣言される (監督裁定 3)。
- `spec/data-service-api.v1.json` の **`versioning.version_binding`** — 「1.4.0 以上を宣言する実装のみが 1.4.0 が導入した義務 (従属判断 9) に適合を主張する」旨を、1.2.0 / 1.3.0 の既存記述と同じ形式で**逐条列挙**して追記する。**義務範囲は条件付きである (監督裁定 8)**: 1.4.0 を宣言する peer は「**`audit_query` を提供する場合に**」1.4.0 の意味論 — 不透明 cursor、`(recorded_at, plane, event_id)` の全順序、`plane`、宣言される `event_class` 語彙、2 パス両建て、`audit_requests_per_minute` — に従う義務を負う。**提供そのものは capability 宣言事項である** (`control_plane.provision` と同型)。したがって **AUDIT DSN 未設定の配備は `audit_query` を `unavailable` と宣言したまま 1.4.0 を宣言できる**。この条件付き性を逐条の中に明記すること (無条件の提供義務と読めてはならない)。
- `r2db-api/src/r2db_api/contract/data-service-api.v1.json` — packaged copy を同期 (byte-identical 固定テストが既存)。
- `spec/CCR_DISPOSITION.md` — **従属判断 9** を新設。従属判断 8 (1.3.0 の 4 件一括) と同じ体裁で、(a) 8 件それぞれの内容と根拠、(b) すべて additive である根拠、(c) 版数の扱い (1.3.0 は公開済みのため個別据え置きの余地はなく単一 1.4.0 束として出荷)、(d) 依頼者裁定 P4-D4 の参照を書く。

**共通 suite**

- `conformance-tests/adapter.py` — **port v1.8**。追加する 3 つ:
  - `audit_query(actor, request) -> Mapping` — control/audit credential で `audit_query` の**クライアント経路**に到達し、生の `AuditResult` 文書を返す。HTTP adapter は **control base URL に対して** `/v1/audit/query` を発行する (設計 R1。この根拠を adapter 側にコメントで残させる)。**宣言を先に読む (declare-first、監督裁定 2)** — 下記「WP-1 補則 1」。
  - `flush_audit_buffer()` — buffer の同期 flush を peer 自身に実行させる adapter 特権 hook (`control_audit_events()` と同格)。
  - `audit_visibility_lag_ms()` — peer が宣言する visibility lag を port から読む。**テストに固定 sleep を書かせないための port である**。
  - 既存の `control_audit_events()` (L1017) は**維持する** (C-15 vector 4 が依存)。
- `docs/design/CONFORMANCE_ADAPTER_V1.md` — **port v1.8 の追随 (監督裁定 5)**。`adapter.py` 冒頭が NORMATIVE SURFACE の正本としてこの文書を指すため、3 メソッドの節を追加し、`SurfaceAbsent` の意味拡張 (WP-1 補則 1) を明記する。
- `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §8.3 — **port メソッド名の訂正 (監督裁定 4)**。同節の `attempt_audit_query` を `audit_query` へ改める (正本名は `audit_query`)。
- `conformance-tests/test_c09_audit_evidence.py` (新設) — 設計 §8.1 の 4 ベクタ + WP-1 補則 1 の宣言真実性テスト + guard 2 本。
- `conformance-tests/test_c11_response_schema_conformance.py` — `AuditResult` の reverse-validation と `AuditQueryRequest` の positive control を追加し、L101-111 の zero-coverage 記述を実被覆へ差し替える。
- `conformance-tests/absence.py` — WP-1 補則 1 の 2 形式を扱う。
- `conformance-tests/CONDITIONS.md` — C-09 / C-11 行の更新は **WP-4 の管轄**。本 WP では `test_conditions_register.py` のマーカー対応が通る最小限の追記に留める。
- 4 adapter ファイル (`r2db-api/conformance/conformance_adapter_r2db.py` / `_http.py`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py` / `_http.py`) — 新 port メソッドの実装。**この時点では 4 adapter とも宣言が `unavailable` なので WP-1 補則 1 により `SurfaceAbsent` に落ちる**。

#### 補則 1: declare-first 規律と absent 分岐の形式 (監督裁定 2)

`audit_query()` は**要求を送る前に宣言を読む**。C-14 が確立した「capability refusal precedes every other check」と同型の declare-first である。

1. `control_capabilities` 文書で `audit_query` が**未宣言または `unavailable`** → **要求を送らずに `SurfaceAbsent`** を送出する。`SurfaceAbsent` の意味をここで拡張する: 「この配備は audit surface を提供しない」— `absence.py` と port の docstring を**この拡張に合わせて更新すること** (従来の「Python 呼び出し面が構造的に存在しない」だけではなくなる)。AUDIT DSN 未設定の配備は「宣言 `unavailable` + ルートは登録済みで認証後 `CAPABILITY_UNSUPPORTED`」の両建て (設計 D-5 / M-4) だが、**port からは宣言側で `SurfaceAbsent` に落ちる**。
2. `audit_query` が **`enabled` 宣言** → 実際に要求を送り、**PROVIDED (生の `AuditResult`) か `ConformanceDenial` (契約 `errors.codes` の member による拒否) のみ**を許容する。**404 / 405 / 未分類応答は宣言が偽であるとして赤**にする — これが宣言の真実性テストである (`test_c09_declared_enabled_audit_query_actually_answers`)。

#### 補則 2: vacuity guard の 2 段構え (監督裁定 1)

- **全体 guard** `test_c09_every_control_surface_adapter_takes_the_provided_branch` — **control surface を持つ登録済み adapter が「全数」PROVIDED 分岐を取ること**を要求する (監督裁定 v1.2-1。現状は登録済み 4 adapter すべてが control_plane: enabled であるため 4 本全数が対象)。「1 本でも PROVIDED なら緑」も「形態ごとに 1 本ずつあれば緑」も禁じる — 全数要求であるため、**片方の peer だけが flip した中間状態では条件が満たされず、XPASS は最後の flip (WP-3(b)) でのみ起きる**。本 WP で**登録するが `@pytest.mark.xfail(strict=True, reason="no peer declares 1.4.0 yet; un-xfailed by the last flip WP")` を付ける**。`strict=True` であるため、全数 PROVIDED が成立した瞬間に「予期せず緑」= 赤になり、放置できない。**xfail を外すのは最後の flip WP = WP-3(b)** であり、これにより flip コミット自身が guard の緑化を自己証明する。
- **個別 guard** `test_c09_declared_capability_implies_provided_branch` — **WP-1 から常時有効 (xfail なし)**。capability 文書が `contract_version >= 1.4.0` (semver タプル比較。文字列比較にしない) **かつ** `audit_query: enabled` を宣言する adapter は、**必ず** PROVIDED 分岐を取らねばならない。宣言していない adapter については何も要求しない。これにより WP-1 時点 (全 adapter が 1.3.0 / unavailable) は真空で緑、flip 後は即座に load-bearing になる。

#### 完了条件 (検証可能な形)

1. `spec/data-service-api.v1.json` の `contract_version` が `1.4.0` であり、`versioning.version_binding` に 1.4.0 節が逐条で存在する — `conformance-tests/test_contract.py` の版数・schema 突合テストが緑。
2. packaged copy が byte-identical — `r2db-api/tests/test_http.py::test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` が緑。
3. 8 件の各項目に対応する契約文言が存在することを、契約文書を読む positive control で固定する (`conformance-tests/test_contract.py` に `test_audit_query_after_is_an_opaque_cursor`、`test_audit_result_event_carries_plane_and_cursor`、`test_event_class_is_a_declared_vocabulary`、`test_audit_requests_per_minute_is_a_declared_limit_class`、`test_audit_events_is_a_documented_reserved_name` 等)。
4. `AuditQueryRequest` の閉鎖 schema が余分キーを拒否する positive control が緑 — `test_c11_response_schema_conformance.py::test_audit_query_request_closed_schema_rejects_an_excess_key`。
5. `versioning.version_binding` の 1.4.0 節が**条件付き義務**として書かれている (「`audit_query` を提供する場合に」の限定と、`unavailable` 宣言のまま 1.4.0 を宣言できる旨) — `test_contract.py::test_version_binding_1_4_0_obligations_are_conditional_on_providing_audit_query`。
6. port v1.8 の 3 メソッドが `ConformanceAdapter` ABC に abstract として存在し、4 adapter すべてが実装している — `MitateDB-api/tests/test_conformance_public_surface_coverage.py` 相当の既存被覆テストが緑。
7. **`docs/design/CONFORMANCE_ADAPTER_V1.md` が port v1.8 の 3 メソッドと `SurfaceAbsent` の意味拡張を記述している**。`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §8.3 の `attempt_audit_query` が `audit_query` へ訂正されている (正本名と文書名の不一致がゼロ)。
8. C-09 の 4 ベクタと C-11 の `AuditResult` 検証が、登録済み 4 adapter それぞれで **WP-1 補則 1 の declare-first 規律に従って分岐 (PROVIDED / `SurfaceAbsent` / `ConformanceDenial`) のいずれかを実際に実行**すること。本 WP 時点では 4 adapter とも宣言が `unavailable` のため 4 本とも `SurfaceAbsent` に落ちる。
9. **宣言の真実性**: `test_c09_declared_enabled_audit_query_actually_answers` — `enabled` 宣言の adapter が 404 / 405 / 未分類応答を返したら赤。本 WP では宣言者がいないため真空で緑。
10. **個別 guard が常時有効**: `test_c09_declared_capability_implies_provided_branch` (xfail なし)。
11. **全体 guard が xfail(strict) で登録済み**: `test_c09_every_control_surface_adapter_takes_the_provided_branch` に `@pytest.mark.xfail(strict=True, reason="no peer declares 1.4.0 yet; un-xfailed by the last flip WP")` が付いており、集計行に xfailed 1 として現れる。非 PROVIDED の adapter については各自の理由を失敗メッセージに載せる (`test_c16_cross_entity_atomicity.py` の vacuity guard の体裁)。
12. 既存 executable 条件 (C-01/C-03/C-06/C-08/C-11/C-12/C-13/C-14/C-15/C-16/C-17/C-18) が 4 adapter で全緑のまま。
13. root suite の集計行 (passed/failed/skipped/**xfailed**) を記録する。基準値は 1292 passed / 0 failed / 0 skipped。本 WP 以降 WP-3(b) まで **xfailed 1** が正常値である。

#### テストコマンド

```
# 共通のみ (開発中の反復)
./.venv/bin/python -m pytest -q conformance-tests

# 完了ゲート (単独実行。他の pytest が走っていないことを確認してから)
./.venv/bin/python -m pytest -q
```

実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない**。

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **契約 8 件の取りこぼしと非 additive 化** — 8 件すべてが本当に additive か (既存 schema のキー削除・意味変更・enum 縮小が紛れていないか)。とくに項目 7 (endpoint 分類の移動) が `/v1/audit/query` の alias 記述を伴わずに移動していないか。項目 8 の limit class 追加が `capability_status.rules` の語彙制限規則と整合するか。
2. **`version_binding` の条件付き性と逐条性** — 1.4.0 節が義務を漏れなく列挙し、かつ**「`audit_query` を提供する場合に」という条件が明示されている**か。無条件の提供義務と読める書き方になっていれば、AUDIT DSN 未設定配備が 1.4.0 を宣言できなくなり裁定 8 に反する。
3. **declare-first の順序** — `audit_query()` が宣言を読む**前**に要求を送っていないか。`unavailable` 宣言なのに要求を送って 404 を `SurfaceAbsent` へ翻訳している adapter がないか (これは宣言の真実性テストを無力化する)。
4. **guard 2 段構えの実効性** — 全体 guard が `xfail(strict=True)` であること (`strict` を落とすと flip 後の緑化が検出できない)。全体 guard の対象集合が **control surface を持つ adapter の全数**から機械的に導出されているか (adapter 名のハードコード列挙になっていないか — 将来 peer が増えたときに黙って抜ける)。個別 guard が xfail されておらず、semver タプル比較 (文字列比較でない) で版数を読んでいるか。全 adapter が absent へ落ちた状態と、偽 enabled 宣言の状態の両方を変異注入で確認したか。
5. **固定 sleep の混入** — C-09 のテストに固定 `sleep` が書かれていないか (`audit_visibility_lag_ms()` から待ち時間を取ること)。完了ゲートの偽赤を構造的に生む。

#### 変異注入 (必須、scratchpad へ復元。`git checkout` 不使用)

- 全体 guard の `strict=True` を外し、flip 相当の状態で緑化が検出されなくなることを確認する。
- 個別 guard の版数比較を文字列比較へ落とし、`1.10.0` 相当の値で誤判定することを確認する。
- adapter 1 本に偽の `enabled` 宣言を持たせ、`test_c09_declared_capability_implies_provided_branch` と宣言真実性テストが赤くなることを確認する。
- 全体 guard を「1 本でも PROVIDED なら緑」へ弱めて (xfail を外した状態で) 赤くなることを確認する。
- `AuditResult` の reverse-validation から閉鎖検査を外して赤くなることを確認する。
- packaged copy を 1 バイト変えて byte-identical テストが赤くなることを確認する。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。

---

### WP-2 r2db-api — 耐久 sink + audit_query + 1.4.0 flip

#### 目的

r2db-api の application-plane に耐久監査を実装し、`audit_query` を control ホスト上で実際に動かし、`contract_version` 1.4.0 を宣言する。

#### 変更対象 (ファイル / モジュール)

**(a) 耐久 sink + hook + 振り分け + denial/buffer/alert**

- `r2db-api/migrations/0007_application_audit.sql` (**新設**) — 設計 §6.1 の DDL。`r2dbsvc_registry.application_audit` (14 列 = 既存 `control_audit` の 13 列 + `count`、加えて `audit_seq bigserial UNIQUE` と `recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()`)、全 text 列の `CHECK (length(col) <= N)`、`count` の `CHECK (count IS NULL OR count > 0)`。GRANT: `r2dbsvc_api` に **INSERT のみ** + sequence USAGE、`r2dbsvc_control` に INSERT (帯域外 CLI 用)、新設 `r2dbsvc_auditreader` (LOGIN / NOSUPERUSER / NOCREATEDB / NOCREATEROLE / NOINHERIT / CONNECTION LIMIT 5) に `control_audit` + `application_audit` の **SELECT のみ**。`r2dbsvc_controlplane` には `application_audit` への GRANT を一切与えない。冒頭に **WHO RUNS THIS** と互換性論証 (設計 §6.3 の雛形。VPS 既存インスタンスに対する逐条確認)。パスワードは環境変数名 (`R2DBSVC_AUDITREADER_PASSWORD`) + `psql -v` 経由。
- `r2db-api/src/r2db_api/audit.py` — `ApplicationAuditSink` (in-memory、**故障注入可**) を新設。既存 in-memory `AuditSink` は D-3 の非耐久 4 種の唯一の記録先として扱う (残置/統合は実装裁量、ただし D-10 の禁止条件下)。`AuditEvent` 構築が `target_id` を渡せる形にする (現状 12 位置引数で `target_id` が常に既定値)。
- `r2db-api/src/r2db_api/credential_store.py` または新規モジュール — `PostgresApplicationAuditSink` (書き手) と `PostgresApplicationAuditStore` (読み手、`auditreader` role)、および `InMemoryApplicationAuditStore` (in-memory の application 面と control 面を UNION して読む。append と query の両方を持つ)。既存ペア `ControlAuditSink` ↔ `PostgresControlAuditSink` の型に倣う。
- `r2db-api/src/r2db_api/backend.py` — `StorageBackend` Protocol の `transact` / `apply_schema` に **pre-commit hook** を露出する。**本フェーズの構造変更の核心**。
- `r2db-api/src/r2db_api/structured.py` — in-memory `ApplicationCell` が同じ hook を擬似 tx で実装する (parity テストの対象)。
- `r2db-api/src/r2db_api/postgres.py` — `PostgresCell` 側の hook 実装。
- `r2db-api/src/r2db_api/service.py` — 振り分け規則の実装。**`event_class` では判定しない** — `DESTRUCTIVE_CONFIRMATION_V1` の確認 choke (`_validate_delete_confirmation` 相当の単一判定点) が振り分けの判定点になる。fail-closed 類 = 確認 choke を通る操作 / すべての schema operation / すべての lifecycle event / `security_control_failure` / D-3 の耐久対象 denial。バッファ類 = query / catalog / delete を含まない mutate。非耐久 = `VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND` (buffer にも載せない)。denial 経路 (L115 / L225 / L260 / L281 / L296 / `deny_unsupported`) の except 節に**この分岐を明示的に置く**。合体 (窓 W=60s、キー = `(application_id, actor_id or "unknown", operation, reason_code)`、初回は同期 INSERT + commit、2 回目以降はメモリ計数、窓終了で `count` つき 1 行を flush)。D-10 の「1 操作 = 最大 1 耐久行」— pre-commit で耐久記録した event は post-commit 側の耐久発火を抑止する。
- bounded buffer (既定 1000、設定可) + overflow alert — 最古から捨て、`logging.error` の**固定メッセージ** (可変部に実データを載せない) と `security_control_failure` 行 (`reason_code="audit_buffer_overflow"`, `operation="audit_buffer"`, `target_kind="audit_sink"`, `count=<累積 drop 数>`) を耐久 INSERT。alert 行の INSERT 失敗は**利用者操作をブロックしない** — sticky に pending を維持し、指数バックオフ (上限 60s) で再試行、`logging.error` の再発火は初回とバックオフ間隔ごと・状態変化時のみ。flush は**常に別 tx・別接続**で行い、fail-closed 書込みの tx に相乗りさせない。
- `r2db-api/src/r2db_api/main.py` (composition root) — 監査行を書く platform 接続に `statement_timeout` (既定 5s) と `idle_in_transaction_session_timeout` (既定 5s) の**両方**を接続オプションとして固定する。
- `r2db-api/src/r2db_api/control_main.py` — `control_audit` を書く control-plane 接続にも**同じ 2 つの timeout** を掛ける (片側だけでは visibility lag の根拠が成立しない)。

**(b) `audit_query` + 宣言 + flip**

- `r2db-api/src/r2db_api/control_http.py` — `_ROUTES` に `POST /control/v1/audit/query` と `POST /v1/audit/query` を**同一ハンドラの alias として両建て**する。AUDIT DSN 未設定でも**ルートは常に登録し**、認証後に `CAPABILITY_UNSUPPORTED` を返す (404 にしない)。
- **`audit_requests_per_minute` 専用窓 (監督裁定 3)** — `audit_query` の**両パス専用の pre-auth 固定窓**を、既存の `control_requests_per_minute` (`control_plane.py` L1225-1252) とは**別のカウンタ**として実装する。既存 global window と同系の固定窓カウンタでよい (新機構を発明しない)。`audit_query` の要求はこの新窓のみを消費し、**control 窓を消費しない** — これにより「証拠を読む」高頻度ポーリングが「侵害を止める」`revoke_credential` を締め出す相互作用 (設計 M-8) が構造的に消える。窓超過は `LIMIT_EXCEEDED` + `details.limit_class == "audit_requests_per_minute"` (契約 1.2.0 の `errors.details_vocabulary` 規則)。`control_capabilities` の `limits` / `limit_enforcement` に新クラスを宣言する (`enforced`)。
- `r2db-api/src/r2db_api/control_plane.py` — `_AUDIT_ROLE_ALLOWED_OPERATIONS` (L182) に `audit_query` を追加。`audit_query` の実装 (順序 `(recorded_at, plane, event_id)`、`after` = 不透明 cursor (exclusive)、`recorded_at < now() - <導出 lag>` の行のみ、`limit` 既定 100、`event_classes` は未知値でも `VALIDATION_FAILED` にせず空結果)。**`plane` は行の出所テーブルから導出する — 実列にしてはならない**。
- `control_capabilities` 文書に `audit_query` 宣言を載せる (設計 D-5 の形。`status`/`authority`/`event_classes`/`default_limit`/`visibility_lag_ms` (= `statement_timeout` + `idle_in_transaction_session_timeout` + 1s の**導出値**)/`coalescing_window_ms`/`completeness_note`/`outcome_note`)。`status` の語彙は契約 enum の 4 値のみ (`"available"` という語は存在しない)。AUDIT DSN 未設定時は `{"status": "unavailable"}` 据え置き。
- data-plane ホスト (`r2db-api/src/r2db_api/http.py` L397-419 `post_audit_query`) は**不変**。data-plane の `/v1/capabilities` も `audit_query: unavailable` のまま。
- **`contract_version` 1.4.0 flip** — `capabilities()` の宣言と、版数を固定しているローカルテストを**同一コミットで**更新する。
- `r2db-api/conformance/conformance_adapter_r2db.py` / `conformance_adapter_r2db_http.py` — port v1.8 の 3 メソッドを PROVIDED 分岐へ切り替える。
- `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` — 最小追随 (migration 0007 の適用手順、reader role DSN)。本格的な runbook 整備は WP-4。

#### 完了条件 (検証可能な形。テスト名レベル)

**(a) 側**

1. `r2db-api/tests/test_application_audit.py` (新設) — 耐久 sink 故障注入で fail-closed:
   - `test_destructive_mutate_is_service_unavailable_when_the_durable_sink_fails` (データ側の行数が不変であることを併せて実測)
   - `test_schema_operation_is_service_unavailable_when_the_durable_sink_fails`
   - `test_denial_response_is_service_unavailable_when_the_first_coalesced_insert_fails`
2. `test_failed_data_commit_writes_an_error_row_for_the_same_request_id` / `test_error_row_write_failure_makes_the_response_service_unavailable` / `test_simulated_process_loss_leaves_the_allow_row_alone` (プロセス消失模擬では `allow` 単独が残ることを**仕様として固定する** — 失敗扱いにしない)
3. `r2db-api/tests/test_postgres.py` (または新設) — 生の接続による GRANT 実測:
   - `test_api_role_cannot_select_update_or_delete_application_audit`
   - `test_api_role_cannot_insert_a_value_longer_than_the_length_check`
   - `test_controlplane_role_has_no_privilege_on_application_audit`
   - `test_auditreader_role_can_select_both_audit_tables_and_nothing_else`
4. `test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n` / `test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry`
5. `test_buffer_overflow_emits_logging_error_and_exactly_one_security_control_failure_row` / `test_alert_insert_failure_is_sticky_with_exponential_backoff_and_does_not_block_operations` / `test_buffer_does_not_grow_past_its_configured_bound`
6. `test_buffer_row_failure_does_not_block_a_fail_closed_operation`
7. `test_each_data_operation_adds_exactly_one_application_audit_row` (control 面の `test_each_state_change_adds_exactly_one_audit_row` と同型) / `test_delete_bearing_mutate_never_enters_the_buffer_path` / `test_dispatch_point_is_the_destructive_confirmation_choke`
8. `test_audit_write_connections_have_statement_and_idle_in_transaction_timeouts_set` (`SHOW statement_timeout` 等で実測。application 側と control 側の**両方**)
9. `test_migration_0007_applies_after_0006_and_changes_no_existing_grant` (0001..0006 適用済み状態に 0007 のみ適用して成功。既存 GRANT の不変を実測)
10. `test_in_memory_and_postgres_application_audit_sinks_have_parity` (D-10 の parity)
11. **既存の control-plane テストが全て緑のまま** (`r2db-api/tests/test_control_plane_store.py` / `test_control_plane_service.py` / `test_control_http.py`)。とくに `control_audit` の 13 フィールド系テストを緩めていないこと。

**(b) 側**

12. `test_control_host_serves_both_audit_query_paths_with_one_handler` (`/control/v1/audit/query` と `/v1/audit/query` が同一ハンドラに解決)
13. `test_audit_query_without_audit_dsn_refuses_with_capability_unsupported_not_404`
14. `test_application_credential_is_forbidden_on_the_control_host_audit_query` / `test_control_and_audit_credentials_are_accepted_on_audit_query`
15. `test_data_plane_host_audit_query_still_refuses_with_capability_unsupported` / `test_data_plane_composition_root_does_not_import_the_control_credential_store`
16. `test_application_audit_rows_always_read_back_as_plane_application` (書き手がどんな値を書いても `plane` は導出値)
17. `test_writer_tx_held_near_the_lag_still_returns_on_the_next_page` (書き手 tx を人工的に lag 近くまで引き延ばして commit) / `test_control_audit_row_from_a_delayed_control_tx_returns_on_the_next_page` (control 側でも同じベクタ) / `test_cursor_paging_covers_every_row_without_duplicates_under_concurrent_writes` / `test_invalid_cursor_is_validation_failed`
18. `test_in_memory_and_postgres_audit_query_semantics_have_parity` (順序・cursor・visibility lag・limit の意味論を両実装で同一 parity テストに掛ける)
19. `test_declared_event_classes_cover_every_emittable_class` (宣言語彙 ⊇ 実際に耐久記録され得る class 集合)
20. `test_declared_visibility_lag_ms_is_derived_from_the_two_timeouts` (裸の数値を宣言していないこと)
21. **`audit_requests_per_minute` 専用窓** — `test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute` / `test_audit_query_does_not_consume_the_control_requests_per_minute_window` (`audit_query` を宣言値まで連打した直後に `revoke_credential` が通ることを実測する) / `test_audit_requests_per_minute_is_declared_enforced_in_control_capabilities`。既存の `r2db-api/tests/test_limit_class_vocabulary.py` の語彙全数固定 (AST 件数) を同一コミットで更新する。
22. **`contract_version` が 1.4.0** — 版数を固定している既存ローカルテストが同一コミットで更新され緑。
23. 共通 suite で **r2db-api / r2db-api-http の 2 adapter が C-09 / C-11 の PROVIDED 分岐を実行する**。個別 guard `test_c09_declared_capability_implies_provided_branch` が本 WP で**初めて load-bearing になる** — 1.4.0 + `enabled` を宣言した 2 adapter が PROVIDED を取らねば赤。全体 guard は**全数要求**であるため MitateDB 側が未 flip の本 WP では条件を満たさず、xfail のまま (XPASS しない)。解除は **WP-3(b) の責務**であり、本 WP では外さない。
24. root suite の集計行 (passed/failed/skipped/xfailed) を記録する。xfailed 1 が正常値。

#### テストコマンド

```
# peer 単体 (開発中の反復)
./.venv/bin/python -m pytest -q r2db-api/tests

# 共通
./.venv/bin/python -m pytest -q conformance-tests

# 完了ゲート (単独実行)
./.venv/bin/python -m pytest -q
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **flip の瞬間に昇格する既存欠陥** — `audit_query: enabled` と `contract_version: 1.4.0` を宣言した瞬間に load-bearing になる pre-existing の穴を明示的に探す (フェーズ3.5 WP-2 B-2 の教訓)。とくに `target_id` が常に NULL であること、既存 denial 経路の分類漏れ、`event_class` 語彙の実値と宣言のずれ。
2. **宣言と実挙動の一致** — `visibility_lag_ms` が実際の 2 つの timeout から導出されているか (裸の定数でないか)。`coalescing_window_ms` が実装の窓 W と同一か。AUDIT DSN 未設定時に宣言が `unavailable` のままでルートは登録されているか。data-plane ホストの宣言が `unavailable` のまま (= このホストでは提供していないという真の宣言) か。
3. **1 操作 = 最大 1 耐久行の破れ** — pre-commit hook を足したまま post-commit の `_event` が耐久面へ二度書く経路が残っていないか。in-memory sink と耐久 sink で記録先が二重になり片方が黙って落ちる構造 (D-10 禁止条件 (i)) が無いか。
4. **振り分けが `event_class` に退行していないか** — 判定点が確認 choke の単一関数であること。delete を含む mutate が buffer 経路に落ちる経路が一つも無いこと。非耐久 4 種が buffer にも入らないこと。
5. **fail-closed 行と buffer 行の tx 分離** — buffer flush が fail-closed 書込みの tx に相乗りしていないか (相乗りすると buffer 行 1 件の失敗が destructive 操作を止め、`sink_failure_policy` が 2 類を分けた意図が逆転する)。

#### 変異注入 (必須)

- pre-commit hook を post-commit へ戻し、fail-closed テストが赤くなることを確認する。
- 振り分けを `event_class` ベースへ書き換え、`test_delete_bearing_mutate_never_enters_the_buffer_path` が赤くなることを確認する。
- `plane` を実列にして書き手が指定できるようにし、`test_application_audit_rows_always_read_back_as_plane_application` が赤くなることを確認する。
- `statement_timeout` の片方を外し、lag 導出テストと遅延 tx テストが赤くなることを確認する。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。

---

### WP-3 MitateDB-api — 耐久 sink + 13 列 emitter + audit_query + 1.4.0 flip

#### 目的

WP-2 の対称実装。加えて MitateDB 固有の 3 点を解消する: (i) 6 フィールド sink の丸めを耐久経路に通さない、(ii) `backend_postgres` の `commit()` が `try` の外にある構造を直す、(iii) P4-D5 に従い query/insert/update 成功の emit サイトを新設する。

**WP-2 のレビュー裁定を発注時点で織り込むこと** — WP-2 で出た blocker/major の裁定は、本 WP では最初から要求事項として扱う。

#### 変更対象 (ファイル / モジュール)

- `MitateDB-api/migrations/0005_application_audit.sql` (**新設**) — 設計 §6.2 の DDL。`mitatedb_registry.application_audit` (`event_id` は既存 `control_audit` に合わせて `text` PRIMARY KEY、以下 §6.1 と同形の 14 列 + `audit_seq` + `recorded_at DEFAULT clock_timestamp()`、同一の長さ CHECK)。`REVOKE ALL ... FROM PUBLIC`。GRANT: `mitatedbsvc_api` に INSERT + sequence USAGE、新設 `mitatedbsvc_auditreader` に 2 表の SELECT のみ。`mitatedbsvc_controlplane` には与えない。既存 GRANT (`applications`/`credentials` の SELECT、0002 L253-254) は変更しない。新 role は必ずこの SQL の `CREATE ROLE` で作る (Cloud SQL の Users API/Console で作ると `cloudsqlsuperuser` メンバとなり `REVOKE CONNECT ... FROM PUBLIC` を迂回する)。`mitatedb_registry.assert_role_has_no_memberships` の fail-closed backstop を新 role にも適用する。
  - **冒頭に Cloud SQL 実配備 (PostgreSQL 16.14、2026-09-01 配備) への互換性論証を必須とする** — 設計 §6.3 の雛形に沿い、「追加のみ」という主張ではなく**どの既存オブジェクトに触れていないかを名指しする逐条確認**として書く。in-place 編集は禁止。
- `MitateDB-api/src/mitatedb_api/audit.py` — **13 列 (+`count`) emitter を新設**する。既存 6 フィールド `AuditSink` (`_SAFE_EVENTS`/`_SAFE_DETAILS` が許可語彙外を `"unclassified"`/`"unspecified"` へ黙って丸める) を**耐久経路に通さない** — 丸めた値を耐久記録すると `event_class` 宣言と実記録が食い違う。既存 sink の残置/撤去は実装裁量だが D-10 の禁止条件下で判断する。
- `MitateDB-api/src/mitatedb_api/control_audit.py` 近傍または新規モジュール — `PostgresApplicationAuditSink` (書き手)、読み手 (`auditreader` role)、`InMemoryApplicationAuditStore` (in-memory の UNION 読み)。
- `MitateDB-api/src/mitatedb_api/backend_postgres.py` — **`commit()` を `try` の内側へ移す** (現状 `create_collection` L422 / `add_field` L444 / `delete` L684 が `else:` 節で commit しており、commit 自体の raise が分類済み `FoundationError` にならずに素通りする)。その失敗を D-2 の `error` 行発火へ接続する。あわせて **pre-commit hook** を露出する。
- `MitateDB-api/src/mitatedb_api/backend_sqlite.py` / `backend.py` — 同じ hook を擬似 tx で実装 (parity テスト対象)。
- `MitateDB-api/src/mitatedb_api/cell.py` — バッチ経路 (`transact` L669-828) で `pending_audit` を `self._backend.commit()` の**直前**に耐久 sink へ flush + commit し、失敗時は rollback → `SERVICE_UNAVAILABLE`。post-commit の `record()` (L826-827) は耐久面へ二度書かない。単発経路 (`create_collection` L336-339 / `add_field` L389-392 / `delete` L546-549) も同型。**P4-D5: query / insert / update 成功の emit を新設する** (現状これらは一切記録されない)。振り分け規則・合体 denial・buffer/alert は WP-2 と同一設計。
- `MitateDB-api/src/mitatedb_api/auth.py` — denial 経路 (L355-422) に D-3 の範囲判定と合体を掛ける。
- `MitateDB-api/src/mitatedb_api/main.py` / `control_main.py` / `control_composition.py` — 監査書込み接続の `statement_timeout` / `idle_in_transaction_session_timeout` の**両方**を接続オプションとして固定する (application 側と control 側の両方)。**Cloud SQL 実配備があるため、migration の `ALTER ROLE`/`ALTER DATABASE` ではなくアプリケーション側の接続オプションで行う**。
- `MitateDB-api/src/mitatedb_api/control_http.py` — `_ROUTES` (L327-338) に 2 パスを両建て。
- `MitateDB-api/src/mitatedb_api/control_plane.py` — `_AUDIT_ROLE_ALLOWED_OPERATIONS` (L80) に `audit_query` を追加。`audit_query` 実装 (WP-2 と同一意味論)。**`audit_requests_per_minute` 専用窓** (既存 global window L964-974 とは別カウンタ。`audit_query` 両パス専用の pre-auth 固定窓。control 窓を消費しない。超過は `LIMIT_EXCEEDED` + `limit_class == "audit_requests_per_minute"`)。`control_capabilities` 宣言 (`limits` / `limit_enforcement` に新クラスを `enforced` で追加)。`MitateDB-api/tests/test_limit_class_vocabulary.py` の語彙全数固定を同一コミットで更新。
- data-plane ホスト (`MitateDB-api/src/mitatedb_api/http.py` L781-807) は**不変**。
- **`contract_version` 1.4.0 flip** — 宣言とローカル版数固定テストを同一コミットで更新。
- `MitateDB-api/conformance/conformance_adapter_mitatedb.py` / `_mitatedb_http.py` — port v1.8 を PROVIDED 分岐へ。
- `MitateDB-api/docs/cloud-run-cloud-sql.md` — 最小追随 (migration 0005 の適用手順、reader role DSN、timeout の実測確認手順)。本格整備は WP-4。

#### 完了条件 (検証可能な形。テスト名レベル)

WP-2 の完了条件 1〜23 と**同一の性質**を `MitateDB-api/tests/test_application_audit.py` ほかで満たす。加えて MitateDB 固有:

24. `test_durable_path_never_passes_through_the_six_field_rounding_sink` (許可語彙外の値が `"unclassified"`/`"unspecified"` へ丸められた形で `application_audit` に現れないこと)
25. `test_backend_commit_failure_is_classified_and_produces_an_error_row` (`commit()` が `try` の内側に移り、raise が素通りしないこと)
26. `test_query_insert_and_update_success_events_are_durably_recorded` (P4-D5 の emit サイト新設)
27. `test_buffer_overflow_is_reachable_from_the_real_emit_path` (P4-D5 により通常 event が buffer に載るため、設計 §9.2 性質 3 が**実 emit 経路から**検証できる)
28. `test_migration_0005_applies_after_0004_and_changes_no_existing_grant` / `test_new_auditreader_role_has_no_memberships` (`assert_role_has_no_memberships` backstop)
29. 既存の `MitateDB-api/tests/test_control_plane_postgres.py::test_application_plane_role_has_no_privilege_on_control_audit` が**そのまま緑であり続ける** (緩めてはならない)。既存 13 フィールド完全一致テストも緑のまま。
30. `test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute` / `test_audit_query_does_not_consume_the_control_requests_per_minute_window` / `test_audit_requests_per_minute_is_declared_enforced_in_control_capabilities` (WP-2 完了条件 21 と同一の性質)。
31. 共通 suite で **MitateDB-api / MitateDB-api-http の 2 adapter が C-09 / C-11 の PROVIDED 分岐を実行する** — 登録済み 4 adapter すべてが PROVIDED になる。
32. **全体 guard の `xfail` を本 WP で外す (監督裁定 1)** — `test_c09_every_control_surface_adapter_takes_the_provided_branch` から `@pytest.mark.xfail(strict=True, ...)` を削除し、**素で緑になる**ことを同一コミットで示す。**xfail の削除は本 flip コミットに含める** — これにより flip コミット自身が guard の緑化を自己証明する。xfail を先に外すことも、flip 後に別コミットで外すことも禁じる。
33. root suite の集計行 (passed/failed/skipped/xfailed) を記録する。**本 WP 完了時点で xfailed は 0 に戻る**。

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **WP-2 裁定の織り込み漏れ** — WP-2 のレビューで出た blocker/major が本 WP で最初から満たされているか。対称実装で同じ指摘が再発したら、それは発注書の伝搬失敗として記録する。
2. **6 フィールド sink の再混入** — 耐久経路のどこか (emit サイト、buffer、alert 行) で丸め語彙が経由していないか。`test_declared_event_classes_cover_every_emittable_class` がこの回帰ガードとして本当に効いているか (変異で確認)。
3. **`commit()` の try 移設による副作用** — 既存の rollback 経路・エラー分類・既存テストの前提を壊していないか。移設が単発 3 経路とバッチ経路のすべてに及んでいるか。
4. **flip の瞬間に昇格する既存欠陥と guard の緑化** — `audit_query: enabled` / `contract_version: 1.4.0` 宣言で load-bearing になる pre-existing の穴。とくに P4-D5 で新設した emit サイトが `forbidden_fields` (行の値・SQL) を載せていないか。**全体 guard の xfail 削除が本 flip コミットに含まれ、素で緑になっているか** — xfail を残したまま完了と主張していないか、逆に guard 自体を弱めて緑にしていないか (変異注入で確認)。`audit_requests_per_minute` 窓が control 窓と本当に別カウンタか (同一カウンタを名前だけ変えていないか)。
5. **Cloud SQL 実配備への互換性論証** — migration 冒頭の論証が「追加のみ」の主張で終わっていないか。触れていない既存オブジェクトを名指しで逐条確認しているか。新 role が Cloud SQL Users API 経由で作られる余地を残していないか。

#### 変異注入 (必須)

- 耐久経路を 6 フィールド sink 経由へ戻し、`test_durable_path_never_passes_through_the_six_field_rounding_sink` と `test_declared_event_classes_cover_every_emittable_class` が赤くなることを確認する。
- `commit()` を `else:` 節へ戻し、`test_backend_commit_failure_is_classified_and_produces_an_error_row` が赤くなることを確認する。
- P4-D5 の emit サイトを 1 つ外し、対応するテストが赤くなることを確認する。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。

---

### WP-4 記録整理 (最終 WP)

#### 目的

実装と同じフェーズ内で、記録を実態へ追いつかせる。設計 §9.3 の「更新対象の既存記録」が正本のスコープ定義である。

#### 変更対象

- **`security/CONTROL_MAPPING.md` SI-14 行** — application-plane の「no external durable sink for this plane yet (phase 4, unchanged)」を本フェーズの成果 (テーブル・GRANT・fail-closed 経路・実測テスト名) に置き換える。加えて 3 点を明記: (i) **P4-D3 の線引き** (denial の耐久対象範囲と合体方式)、(ii) **非耐久とした 4 種** (`VALIDATION_FAILED` / `LIMIT_EXCEEDED` / `CAPABILITY_UNSUPPORTED` / `NOT_FOUND`) とその理由 (SI-14 の最小 class 外)、(iii) **control 面の線引き (rate 拒否を記録しない) との関係** — 線引きの内容は異なるが、いずれも「SI-14 の最小 class の外」という同じ根拠に立つのであって、一方が他方の非対称を解消したわけではない。
- **`security/CONTROL_MAPPING.md` SI-08 行 (監督裁定 v1.2-2)** — 両 peer の `limit_enforcement` evidence に **`audit_requests_per_minute`** を追記する。既存行の書式 (クラスごとに宣言値・enforcement 状態・それを実測するテスト名を挙げる) を踏襲し、`audit_query` 専用窓が control 面の `control_requests_per_minute` とは別カウンタであること、および根拠テスト (`test_audit_query_over_its_own_window_is_limit_exceeded_with_limit_class_audit_requests_per_minute` / `test_audit_query_does_not_consume_the_control_requests_per_minute_window`) を明記する。
- **`security/CONTROL_MAPPING.md` SI-00 行 (b)** — 「application-plane role は `control_credentials`/`control_audit` に一切の GRANT を持たない」は本フェーズ後も真のままだが、「registry schema 全体に一切の書込権限を持たない」と読まれ得るため、**`application_audit` への INSERT-only を明示的に併記**する。MitateDB 側の対応テストは緩めていないことを併記する。
- **`conformance-tests/CONDITIONS.md`** — C-09 行を「not yet executable (common suite) — peer-local evidence only」から executable 化後の実態へ、C-11 行の `AuditResult`/`AuditQueryRequest` zero-coverage 記述を実被覆へ更新する。既存行の書式 (どの adapter が PROVIDED でどれが absent か、vacuity guard が何を機械的に固定しているかを正直に列挙する) を踏襲する。
- **両 peer の runbook** (`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`、`MitateDB-api/docs/cloud-run-cloud-sql.md`。**MitateDB 側の宛先はこのファイルで確定 — 新規 runbook ファイルは作らない**) — 手動手順として以下 6 項:
  1. 新 migration の適用手順 (適用順・実行 role・環境変数名。SQL に実値を書かないこと)。
  2. reader role の DSN 設定 (`R2DB_AUDIT_DSN` / `MITATEDB_AUDIT_DSN`)。未設定時は `audit_query` が `unavailable` 宣言のままになること。
  3. **platform DB の容量監視** — 1 行サイズ上限 × 行数上限を根拠にした閾値設計。**行数上限の算出に最大インスタンス数 M を織り込む** (合体も buffer もプロセスローカルなので実効上限は「窓数 × M」および「buffer 容量 × M」)。
  4. **監査書込み接続の `statement_timeout` / `idle_in_transaction_session_timeout` の設定値**と、そこから導出される `visibility_lag_ms` の関係 (値を変えたら宣言も変わる)。実測確認手順を含む。
  5. **`audit_requests_per_minute` 専用窓の設定** — 推奨ポーリング間隔 = 宣言された `visibility_lag_ms` 以上。窓値の設計指針 (監査エージェント数 × ポーリング頻度) を書く。**設計 M-8 の「証拠を読む行為が侵害を止める行為を締め出す」相互作用は、専用窓の新設 (監督裁定 3) により構造的に解消済み**である旨と、その根拠テスト名 (`test_audit_query_does_not_consume_the_control_requests_per_minute_window`) を記す — 運用回避策としてではなく、閉じた事実として記録する。
  6. **保持期間・剪定の手動操作手順** (自動剪定は実装しない — 設計 §10)。あわせて **platform DB 障害時の独立した読み取り路は帯域外 CLI のみ**であることを書く。
- **配備構成図とパス一覧** — `MitateDB-api/docs/cloud-run-cloud-sql.md` の構成図 (control サービスを `main:app /control/v1/*` と記述) に `/v1/audit/query` を反映する。r2db 側の対応記述も同様。あわせて「control ホストのエッジポリシーは `/control/v1/*` だけでなく `/v1/audit/query` も覆わねばならない」を明記する。
- **台帳** (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11) — WP 実施中に発生した項目を追記する。継承分のうち **`audit_events` 予約名の文書化**は契約 1.4.0 候補 6 で解消されるため RESOLVED として追記する。
- **設計文書の記録節** — 各 WP の実装記録・レビュー裁定・変異注入ログ・受理境界を `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` へ節として追加する (フェーズ3.5 §10.1〜10.6 の体裁)。
- **ハンドオーバー** `docs/work-orders/HANDOVER_20260902_FABLE.md` (第10次) — 現在地、各 WP のコミット表、最終実測の集計行、次の一手、教訓。

#### 完了条件

1. 設計 §9.3 の 6 項目 (SI-14 行 / SI-00 行 (b) / CONDITIONS 2 行 / 配備構成図 / runbook 6 項 / 台帳) がすべて更新済みであること。
1b. **`security/CONTROL_MAPPING.md` SI-08 行に両 peer の `audit_requests_per_minute` が追記済み**であり、宣言値・`enforced` 状態・根拠テスト名が実在するテストへ解決すること (監督裁定 v1.2-2)。
2. 設計 §9.2 の 11 性質すべてについて、本書 §5 の対応表が指す**実在するテスト名**へ解決すること (存在しないテスト名を書かない)。
3. 陳腐化した prose の全数掃討 — 「application-plane に耐久 sink は無い」「`AuditResult` は zero-coverage」「`audit_query` はスタブ」「全 adapter が `audit_query` を unavailable と宣言」と書いている箇所を grep で洗い出し、すべて実態へ更新する。
4. root suite の最終実測 (単独実行) の集計行を記録し、ハンドオーバーに載せる。
5. `test_conditions_register.py` のマーカー/行対応が双方向で緑。

#### テストコマンド

```
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 6 = 証拠監査)

1. **記録と実装の乖離** — CONTROL_MAPPING / CONDITIONS が主張する evidence が、実在し実際に走るテストへ解決するか。テスト名が改名・削除されていないか。
2. **正直さの後退** — 「executable (four adapters)」の主張が、実際には一部 adapter が absent 分岐に落ちている状態を覆い隠していないか。vacuity guard が何を機械的に固定しているかが行に書かれているか。
3. **runbook の実行可能性** — 6 項が手順として実行可能な粒度か。とくに容量閾値の算出に M が入っているか、`visibility_lag_ms` の導出関係が値と結び付いているか。
4. **秘密の混入** — runbook・構成図・migration に実値の DSN / パスワード / 実在ドメイン / 実データが混入していないか (公開リポジトリ規律)。
5. **台帳の取りこぼし** — WP-1〜WP-3 のレビューで「本フェーズでは扱わない」と裁定された項目が、すべて台帳へ落ちているか。

#### 使用テンプレート

起草 = Opus (テンプレ 4 = 文書起草)。証拠監査 = Opus (テンプレ 6)。

---

## 4. 完了ゲートの実測規律 (全 WP 共通)

- 完了ゲートの root suite は**リポジトリルートで単独実行する**。他の pytest プロセスが走っていないことを確認してから実行する — **PG クラスタの並走衝突で偽の赤が出る** (フェーズ3.5 で 2 回発生)。
- 実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない** — skip が出ていたら、それは環境の問題として解決してから完了と判定する。
- 各 WP の完了報告に **集計行 (passed / failed / skipped / xfailed)** を必ず記録する。基準値は **1292 passed / 0 failed / 0 skipped** (2026-09-01)。増分の内訳 (どの WP で何本増えたか) を書く。**WP-1 から WP-3(b) の直前までは `xfailed 1` が正常値**であり (WP-1 補則 2 の全体 guard)、WP-3(b) 完了時点で 0 に戻る。xfailed が想定と違う値なら完了と判定しない。
- 変異注入は scratchpad へ復元する (`git checkout` は使わない)。

---

## 5. 性質対応表 (設計 §9.2 の 11 性質 × WP × テスト)

| # | 性質 (設計 §9.2) | 固定する WP | テスト (r2db) | テスト (MitateDB) |
|---|---|---|---|---|
| 1 | **fail-closed by construction** — 耐久 sink 故障注入で fail-closed 類の操作・denial 応答が成立しない (`SERVICE_UNAVAILABLE`、データ側に痕跡なし) | WP-2(a) / WP-3(a) | `test_destructive_mutate_is_service_unavailable_when_the_durable_sink_fails`、`test_schema_operation_is_service_unavailable_when_the_durable_sink_fails`、`test_denial_response_is_service_unavailable_when_the_first_coalesced_insert_fails` | 同名 (`MitateDB-api/tests/test_application_audit.py`) |
| 2 | **append-only by grant** — api role の UPDATE/DELETE/SELECT が生の接続で実際に拒否される | WP-2(a) / WP-3(a) | `test_api_role_cannot_select_update_or_delete_application_audit`、`test_controlplane_role_has_no_privilege_on_application_audit`、`test_auditreader_role_can_select_both_audit_tables_and_nothing_else` | 同名 + 既存 `test_application_plane_role_has_no_privilege_on_control_audit` が緑のまま |
| 3 | **buffer overflow が alert event として耐久記録される** — `security_control_failure` 行 + `logging.error` | WP-2(a) / WP-3(a) | `test_buffer_overflow_emits_logging_error_and_exactly_one_security_control_failure_row`、`test_alert_insert_failure_is_sticky_with_exponential_backoff_and_does_not_block_operations` | 同名 + `test_buffer_overflow_is_reachable_from_the_real_emit_path` (P4-D5 により実 emit 経路から検証可能) |
| 4 | **application credential が `audit_query` で FORBIDDEN** | 固定 = WP-1 (共通テスト新設) / 初実行 = WP-2(b)・WP-3(b) | 共通: `test_c09_v3_application_credential_is_forbidden_on_the_control_host_audit_query`。peer: `test_application_credential_is_forbidden_on_the_control_host_audit_query` | 同上 (同一の共通テストが 4 adapter で走る) |
| 5 | **emit された `event_class` ⊆ 宣言語彙** | WP-2(b) / WP-3(b) | `test_declared_event_classes_cover_every_emittable_class` | 同名 (6 フィールド sink の丸め再混入に対する回帰ガードを兼ねる) |
| 6 | **fail-closed 類の event は buffer 経路に載らない**。振り分けの判定点が両 peer で同じ関数 (確認 choke) である | WP-2(a) / WP-3(a) | `test_delete_bearing_mutate_never_enters_the_buffer_path`、`test_dispatch_point_is_the_destructive_confirmation_choke` | 同名 |
| 7 | **buffer 行の書込み失敗が fail-closed 操作を止めない** | WP-2(a) / WP-3(a) | `test_buffer_row_failure_does_not_block_a_fail_closed_operation` | 同名 |
| 8 | **1 操作 = 耐久 1 行** | WP-2(a) / WP-3(a) | `test_each_data_operation_adds_exactly_one_application_audit_row` | 同名 |
| 9 | **データ commit 失敗が耐久 `error` 行を生む**。プロセス消失模擬では `allow` 単独が残るのが仕様 | WP-2(a) / WP-3(a) | `test_failed_data_commit_writes_an_error_row_for_the_same_request_id`、`test_error_row_write_failure_makes_the_response_service_unavailable`、`test_simulated_process_loss_leaves_the_allow_row_alone` | 同名 + `test_backend_commit_failure_is_classified_and_produces_an_error_row` (commit の try 移設) |
| 10 | **1 application の侵害が platform DB を無制限に肥大させられない** — (i) 行長 CHECK、(ii) 合体 (プロセスあたり窓あたり 1 行)、(iii) buffer が上限を超えない | WP-2(a) / WP-3(a) | (i) `test_api_role_cannot_insert_a_value_longer_than_the_length_check` / (ii) `test_repeated_invalid_secret_adds_exactly_one_coalesced_row_with_count_n`、`test_validation_failed_denials_add_no_durable_row_and_no_buffer_entry` / (iii) `test_buffer_does_not_grow_past_its_configured_bound`。M の織り込みは WP-4 の runbook 責務 | 同名 |
| 11 | **`plane` は書き手が指定できない** (行の出所テーブルからの導出値) | WP-2(b) / WP-3(b) | `test_application_audit_rows_always_read_back_as_plane_application` | 同名 |

**共通 suite 側の対応** (WP-1 で新設、WP-2(b)/WP-3(b) で PROVIDED 分岐が初実行される):

| 共通テスト | 覆う性質 |
|---|---|
| `test_c09_v1_fail_closed_events_are_observable_through_audit_query` | 1 (観測側)。**対象は fail-closed 類に限定する** — buffer を経由しないので `flush_audit_buffer()` を待たずに visibility lag のみで可視になる。バッファ類を検査する場合は flush hook を明示的に呼ぶ。**固定 sleep を書かない** (`audit_visibility_lag_ms()` から待つ) |
| `test_c09_v2_no_forbidden_field_key_or_reusable_secret_value_appears` | SI-10。`forbidden_fields` の語がキーとして現れず、再利用可能な秘密 (secret / verifier / pepper)・SQL テキスト・行の値が値として現れない。**credential / application の識別子は禁止対象ではない** (`actor_id` = credential_id は SI-14 が要求する帰属情報そのもの) |
| `test_c09_v3_application_credential_is_forbidden_on_the_control_host_audit_query` | 4。data-plane base URL の同パスは `CAPABILITY_UNSUPPORTED` であり、2 ホストで応答コードが異なることは矛盾ではない旨を docstring に明記する |
| `test_c09_v4_no_audit_mutation_or_deletion_surface_exists` | 契約 `audit.immutability` |
| `test_c09_declared_enabled_audit_query_actually_answers` | 宣言の真実性 (WP-1 補則 1)。`enabled` 宣言で 404 / 405 / 未分類応答なら赤 |
| `test_c09_declared_capability_implies_provided_branch` | 個別 guard。**WP-1 から常時有効** (xfail なし)。1.4.0 + `enabled` 宣言の adapter は必ず PROVIDED |
| `test_c09_every_control_surface_adapter_takes_the_provided_branch` | 全体 vacuity guard。**control surface を持つ登録済み adapter の全数**が PROVIDED であることを要求する (現状 4 本全数)。**WP-1 で `xfail(strict=True)` 付きで登録し、WP-3(b) の flip コミットが xfail を外して素で緑にする** |
| `test_c11_audit_result_reverse_validates_against_the_closed_schema` / `test_c11_audit_query_request_closed_schema_rejects_an_excess_key` | C-11 zero-coverage の解消。`events[]` は開放されているため `plane`/`recorded_at`/`count`/`cursor` の追加は適合を壊さない |

---

## 6. 禁止事項 (全 WP 共通)

1. **git commit / push は監督のみが行う**。Sonnet も Opus もコミットしない。
2. **migration の in-place 編集を禁じる**。新番号のみ (`r2db-api/migrations/0007_*.sql`、`MitateDB-api/migrations/0005_*.sql`)。既存 migration の編集が必要に見えたら、それは設計の見直し要求として監督へ差し戻す。
3. **秘密・実データ・実在ドメインを書かない**。環境変数名・secret-manager 参照・架空ドメイン・合成 fixture のみ。実 API key / パスワード / DSN / 本番ログ / DB ダンプ / 個人情報は一切コミットしない。公開リポジトリである。
4. **テストの並行実行を禁じる**。完了ゲートは単独実行する (PG クラスタ衝突で偽赤)。
5. **制約・制限の追加で問題を回避しない** (依頼者設計原則 3)。必要な bound は**設計に書かれたものだけ** — 行長 CHECK、1 操作 1 行、合体窓 W、buffer 容量、2 つの timeout。難所を回避するために新しい上限・拒否経路・pre-auth window・機能制限を足すことは禁じる (とくに data-plane への global pre-auth window の新設は U-3(a) として明示的に不採用である)。
6. **スコープ外に触れない** (設計 §10) — 保持期間・剪定の自動化、外部 SIEM 転送、business audit、`control_audit` の改名/統合、`audit_query` 追加以外の control-plane 経路の変更、r2db の `cross_entity_mutation`、`audit` role の in-band 発行。
7. **既存の control-plane テストを緩めない**。とくに `control_audit` の 13 フィールド完全一致テスト、`test_application_plane_role_has_no_privilege_on_control_audit`、`test_each_state_change_adds_exactly_one_audit_row`。
8. **偽の flip を行わない** — 宣言を真にする挙動が同一コミットに無いまま `audit_query: enabled` や `contract_version: 1.4.0` を宣言しない。逆に、提供しているのに `unavailable` と宣言し続けることも禁じる。
8b. **guard を弱めて緑にしない** — 全体 guard の `strict=True` を落とす、全数要求を「1 本でも PROVIDED なら緑」「形態ごとに 1 本」へ緩める、個別 guard に xfail を付ける、宣言真実性テストから 404/未分類応答の検査を外す、のいずれも禁じる。緑にする正しい手段は実装を真にすることだけである。`xfail` を外すのは **WP-3(b) の flip コミットのみ**。
9. **テストに固定 sleep を書かない** — `audit_visibility_lag_ms()` から待ち時間を取る。
10. **`plane` を実列にしない**。書き手が指定できる値にした時点で、侵害されたプロセスが control 面の証拠を偽造できる。

---

## 7. コミット規律

- **WP ごとに 1 コミット**。WP-2 / WP-3 を §2.1 の許可に従って (a)/(b) に分割した場合は 2 コミット。それ以外の分割は監督の許可を要する。
- **flip は挙動出荷コミットに束縛する** — `contract_version` 1.4.0 の宣言と、その宣言を真にする挙動 (`audit_query` の実体、耐久 sink) は**同一コミット**に入れる。版数を固定しているローカルテストの更新、`limit_class` 語彙の全数固定の更新、および **WP-3(b) における全体 guard の `xfail` 削除**も同一コミット。契約 1.4.0 の公開 (WP-1) と peer の版数宣言 flip (WP-2 / WP-3) が別コミットであることは version_binding 規律どおりであり、その間 peer は 1.3.0 を宣言したまま挙動を先行させない (WP-1 は peer の挙動を変えない)。
- **identity は `r2fish` / noreply**。実名・Gmail を使わない。**コミット前に必ず identity を確認する**。
- **commit → push → main merge (`--no-ff`) は 1 セット**。コミットしたら直ちに push し、main へマージする。分離しない。
- コミットメッセージは日本語可。WP 番号・変更の要旨・完了ゲートの集計行を含める。
- 各コミットの前に、独立レビュー (Opus、変異注入込み) の往復が完了していること。

---

## 8. 使用テンプレートの対応

| WP | 実装 | レビュー | 監査 |
|---|---|---|---|
| WP-0 | — (監督) | — | — |
| WP-1 | Sonnet テンプレ 2 (実装) | Opus テンプレ 5 (コードレビュー、変異注入必須) | — |
| WP-2 | Sonnet テンプレ 2 | Opus テンプレ 5 | — |
| WP-3 | Sonnet テンプレ 2 | Opus テンプレ 5 | — |
| WP-4 | Opus テンプレ 4 (文書起草) | — | Opus テンプレ 6 (証拠監査) |

テンプレートの本文は `~/.claude/.../memory/role-prompt-templates.md` が正本。各発注時に、当該 WP の「レビューが必ず探すべき点」と「変異注入」の節をテンプレートへ差し込むこと。

---

## 9. 実施記録 (2026-09-03、WP-4 起草)

本節は**発注の記録**である。実装内容・レビュー裁定・変異注入・受理境界の記録は正本設計 `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` **§9.4** が持ち、本書はそれを重複させない (§0 の分担どおり)。

**集計行の出所**: 下表の集計行はすべて**監督が §4 の規律どおり単独実行して得た実測値**であり、各コミット本文に記載されている。本節はその転記であって、記録整理時の再実行値ではない。

| WP | 完了日 | コミット (merge) | 集計行 (root suite、単独実行) | §2.1 の (a)/(b) 分割 |
|---|---|---|---|---|
| WP-0 | 2026-09-02 | `3ec95cf` (`b99368d`) | 1292 passed / 0 failed / 0 skipped (基準値確認のみ) | — |
| WP-1 | 2026-09-02 | `09233dd` (`a107f6b`) | 1331 passed / 0 / 0 / xfailed 1 | 対象外 |
| WP-2(a) | 2026-09-02 | `2c5288a` (`1e643e9`) | 1370 passed / 0 / 0 / xfailed 1 | **実施した** |
| WP-2(b) | 2026-09-03 | `a1a1409` (`13c899a`) | 1419 passed / 0 / 0 / xfailed 1 | **実施した** (flip は (b) に束縛) |
| WP-3(a) | 2026-09-03 | `54318c6` (`6df2713`) | 1485 passed / 0 / 0 / xfailed 1 | **実施した** |
| follow-up 1 | 2026-09-03 | `411c034` (`afd24ef`) | 1487 passed / 0 / 0 / xfailed 1 | — |
| WP-3(b) | 2026-09-03 | `a3571dc` (`e60eb1e`) | — (follow-up 2 と同一 merge で計測) | **実施した** (flip + `xfail` 削除を (b) に束縛) |
| follow-up 2 | 2026-09-03 | `cb9f7a3` (`e60eb1e`) | **1526 passed / 0 failed / 0 skipped / xfailed 0** | — |
| WP-4 | 2026-09-03 | (本コミット) | 文書のみ | — |

**分割**: WP-2 / WP-3 はいずれも §2.1 の許可どおり (a)/(b) の 2 コミットに分割した。それ以外の分割は行っていない。`contract_version` 1.4.0 flip はどちらも (b) の単一コミットに含まれ、(a) の時点では公開面の宣言を一切変えていない (`audit_query` は `unavailable`、`contract_version` は 1.3.0 のまま)。全体 vacuity guard の `xfail(strict=True)` 削除は **WP-3(b) = 最後の flip コミット `a3571dc` に含まれる** (§2.1 / §6-8b の要求どおり。先に外すことも、後から別コミットで外すこともしていない)。

**follow-up 2 件 (発注書に無い追加コミット)**: どちらも「一方の peer のレビュー/監査で見つかった欠陥を、対称な他方へ適用する」ためのものであり、監督の許可を得て単独コミットとした。
- `411c034` (WP-2(a) follow-up、製品コード + テスト) — MitateDB WP-3(a) レビューが発見した並行 flush の二重書込みを r2db にも適用 (swap-out 化 + 失敗復元時の容量切り詰め)。
- `cb9f7a3` (WP-2(b) follow-up、**テストのみ**) — MitateDB WP-3(b) 受け入れ監査の指摘を r2db へ対称適用 (宣言語彙 AST 走査のパッケージ全体化、`audit_query` 宣言と `R2DB_AUDIT_DSN` の実 HTTP 固定)。

**§1.3 の成果物 6 項の充足**: 全項充足。(i) 両 peer の fail-closed 耐久記録、(ii) buffer + alert、(iii) control ホスト上で実際に動く `audit_query` (2 パス・control/audit 認証・不透明 cursor)、(iv) C-09/C-11 の executable 化と zero-coverage 解消、(v) 契約 1.4.0 の公開と両 peer の同一コミット flip、(vi) §5 の 11 性質の実測固定 — (vi) の最終対応表は設計 §9.2.1 が正本であり、**本書 §5 の表は発注時点の予定テスト名を含む** (実装が採った名前と一部食い違う。設計 §9.2.1 を参照すること)。

**完了ゲートの実測規律 (§4) の実績**: 全 WP で単独実行を守り、フェーズ3.5 で 2 回起きた PG クラスタ並走衝突による偽の赤は本フェーズでは発生しなかった。skipped は全 WP で 0 (未接続 PostgreSQL による skip 無し)。xfailed は WP-1〜WP-3(a) で 1、WP-3(b) 完了時点で 0 — §4 の想定と完全に一致する。
