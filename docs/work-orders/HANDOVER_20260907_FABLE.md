# 引き継ぎ — 2026-09-07 (第15次。フェーズ8 — 実効 bound と基盤衛生。契約は 1.6.0 のまま無変更)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/受け入れ監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: **第14次 `HANDOVER_20260906_FABLE.md` (フェーズ7 側) と `HANDOVER_20260905_FABLE.md` (Q4 側) の約束事は全て継続**する。**そのさらに前の引き継ぎも全て継続。現在地のみ本書が上書きする**
- 本書は**フェーズ8 (実効 bound と基盤衛生) の WP-1〜WP-6 を完了したセッションの記録**である。**契約 `1.6.0` は 1 バイトも変えていない** (設計 §2 の C1、3 複製の sha256 で示した)。**新しい Security Invariant も足していない** (C2)。**新しい共通条件 (C-20 以降) も足していない** (設計 §6.6)。**実機適用は未実施であり、クライアント一報も送っていない** (方針不変)
- **前書全項の複製はしない** — 継承を明示し、**本フェーズが足したものだけを書く** (作業指示書 §2 WP-6 禁止事項 6)

## 1. 現在地 (main)

**フェーズ8 は WP-6 (記録) をもって閉じた。フェーズ7 の残は依然として WP-9 (公開ゲート) だけであり、着手条件は依頼者の実行合図である。**

| コミット (merge) | WP | 内容 | root suite / CI |
|---|---|---|---|
| `69c9e7a` / `845d0a1` | WP-0(docs) | 設計 v1.1 / v1.2 (U-1・U-2 の依頼者裁定) | 文書のみ |
| `d2de484` | WP-0(発注) | 作業指示書 v1.0 | 文書のみ |
| `d91dba4` → `264cc9f` | WP-3 | **R-10 (A) provenance companion** (`spec/CONTRACT_HISTORY.md` 29 anchor + register 7 本 + `spec/README.md`)。契約 JSON は 0 バイト不変 | — |
| `b1984bb` → `4d2a6d2` / `56ff04c` | WP-2 | **R-9 + L7-23 + L7-22 注記** (`COLLECTION_FLOOR` / `tools/check_collection_floor.py` / CI step / 収集 0 件ガード) | CI run **34034469614** (main `56ff04c`): 3.11 `2272 passed, 9 xfailed in 427.86s (0:07:07)`、3.12 `2272 passed, 9 xfailed in 369.68s (0:06:09)`、floor step OK (2281 / 2274) |
| `02afb01` → `23bc88c` | WP-5 | **R-12 性能ハーネス** (`tools/perf_baseline.py` + README) | — |
| `277603f` → `f21d763` / `76d260c` | WP-4 | **R-11 運用項目** (両 peer の `ops verify-declarations` / `tools/deploy_smoke.py` / `docs/ops/BACKUP_RESTORE_R2DB.md` / argv secret 検査 / provision script の `\getenv` + `ON_ERROR_STOP`) | CI run **34038494519** (main `f21d763` = WP-2/3/4/5): 3.11 `2312 passed, 9 xfailed in 464.96s (0:07:44)`、3.12 `2312 passed, 9 xfailed in 443.99s (0:07:23)`、両 job `COLLECTION_FLOOR check OK: measured=2321 floor=2274 diff=47`、**全 job success** |
| `f4c2590` | (レビュー由来) | **CI の `conformance` job に `timeout-minutes: 30`** (WP-1 レビュー指摘 3 — 壊れた in-flight 前提は runner の上限まで待たず赤として出るべき) | — |
| `72df9d6` → `3c85e96` / **`f4635ed`** | WP-1 | **L7-1 + port v1.12 + L7-21** (MitateDB application plane の 4 class + in-process `request_bytes`、`hold_in_flight`、`_drive_concurrency`、`result_items` 両側化、peer 名分岐の撤去、C-05 行の書き換え、V3 xfail 9 → 0) | **完了ゲート (監督単独実行): `2340 passed, 5 warnings in 349.31s (0:05:49)` / EXIT=0、failed 0 / xfailed 0 / skipped 0** |
| `(本記録の merge。ハッシュは次回引き継ぎ §1 に記載)` | WP-6 | 記録 (設計 v1.3 §9〜§11)、計画文書 v1.2、フェーズ7 設計 §11 の状態注記、作業指示書 §5 訂正註、本書 | 文書のみ |

**集計行の出所**: **完了ゲートは監督がローカルで単独実行したものが正本である** (`{scratchpad}/gate-record.md`)。worktree `.claude/worktrees/phase8` = branch `phase8-effective-bounds` **`3c85e96`**、`ps` で他の pytest が 0 件、ローカル PG の `max_connections = 300` / `statement_timeout = 0`、`pg_database` は前後とも **21 → 21** (残留なし)。

**`5 warnings` は共有 `.venv` に `httpx2` を入れていないことによる `StarletteDeprecationWarning` であり、CI 側は 0 である** (第 14 次 §1 / §4-3 と同じ。**warnings の数は一致判定に用いない**)。

**CI の WP-1 入り run (main `f4635ed`、run 34047745958) は監督が 2026-09-07 に確認済み**: 3.11 `2340 passed in 433.13s (0:07:13)`、3.12 `2340 passed in 456.24s (0:07:36)`、両 job floor step 緑、`tally-consistency` success。ローカル root suite `2340 passed` と 4 数一致 (L7-6 の突合済み)。**main の run は docs-only push のたびに `concurrency` の cancel-in-progress で消えるので、ゲートは最終 push の run で読む。**

**集計行の推移**: `2265` (フェーズ7 完了時) → `2272` (WP-2) → `2281` (WP-3) → `2321` (WP-4/5 込みの CI 実測) → **`2340`** (WP-1 込みの完了ゲート)。

正本の所在 (第 14 次から更新された箇所のみ):

- **本フェーズの実施設計** = `docs/design/PHASE8_EFFECTIVE_BOUNDS_AND_HYGIENE_V1.md` (**v1.3**)。**§3 の D-1〜D-6 が確定事項** (各 D の末尾に「**訂正註 (実装で確定した差)**」がある)、**§5 が U-1 / U-2 の依頼者裁定の逐語**、**§9 が完了ゲートとその結果**、**§10 が台帳 (L8-1〜L8-16)**、**§11 が実施記録 (11.1 集計行 / 11.2 性能基準値 / 11.3 WP ごとの記録)**、**付録 A が R-10 の逐語インベントリ**
- **発注と WP 分割** = `docs/work-orders/WORK_ORDER_PHASE8_EFFECTIVE_BOUNDS_V1.md` (v1.0)。**§5 に訂正註 4 件**を置いた (本文の発注内容は書き換えていない)
- **計画文書** = `docs/design/ROADMAP_POST_PHASE7_V1.md` (**v1.2**)。**§1.0 が現在形の「現状」**、§5 のフェーズ8 節に完了と完了条件の充足、**§5 / §8 の R-10 行と §5 / §7 / §8 の R-12 行が R-14 に従って改版済み** (行は 1 つも消していない)
- **conformance の port は v1.12** (`docs/design/CONFORMANCE_ADAPTER_V1.md` §22)。**`hold_in_flight` と要求側 optional フィールド (`limit` / `extra_predicates`) が追加され、削除は無い**
- **契約の provenance companion** = `spec/CONTRACT_HISTORY.md` (**29 anchor**、register は `conformance-tests/test_contract_history_register.py` の 7 本)
- **テスト総数の下限** = `conformance-tests/COLLECTION_FLOOR` (**2340**)。検査は `tools/check_collection_floor.py`、運用規約は `conformance-tests/README.md`
- **性能基準値** = フェーズ8 設計 **§11.2** (PERFRUN 行 + PERF 14 行)。ハーネスは `tools/perf_baseline.py`、限界は `tools/PERF_BASELINE_README.md`
- **運用** = `docs/ops/BACKUP_RESTORE_R2DB.md`、`tools/deploy_smoke.py`、両 peer の `ops verify-declarations`

## 2. 到達した状態

### 2.1 宣言した bound が、全 peer で実効になった (L7-1 / L7-21 が閉じた)

- **MitateDB の application plane が 4 class を実際に強制するようになった。** `requests_per_minute` (credential 単位の 60 秒窓)、`concurrency` (プロセス = 配備単位の in-flight カウンタ)、`execution_ms` (app 側 deadline + PG の `SET LOCAL statement_timeout` / `lock_timeout`。宣言は r2db と同じ **`reference_wall_clock`**)、`operation_depth` (r2db `check_depth` 同型の汎用再帰深さ)、および副項目の in-process `request_bytes` (構造推定)。**宣言と実装は同一コミットである** (P-3)。**gate の実順序は r2db の実順序に一致する** — `rate → concurrency → request_bytes → operation_depth → deadline`。
- **`operation_depth` は両面 `enforced` になり、C-05 V3 の xfail は 9 → 0 になった。** 依頼者裁定 (A) が許した逃げ枝 (「in-process に要求 dict が無ければ 1 組残す」) は**条件が成立しなかった** — in-process の `values` 自体が要求構造であり、既定 depth 8 の下で 7 段ネストの `session.insert()` が `LIMIT_EXCEEDED` になる。**非対称は 1 つも残っていない。**
- **限度状態は「1 プロセス 1 個」のホルダに置いた。** `ApplicationRuntime` は要求ごとに新規構築され `__slots__` も持つので、session に窓やカウンタを置けば「宣言だけ `enforced`・実挙動は無制限」(P-3 違反) になる。**合成根が 1 個だけ構築して全 `ApplicationCell` に注入する** — `audit_dispatch.AuditRouter` と同じ配線の再利用である。
- **`concurrency` が共通 suite で初めて駆動されるようになった (port v1.12)。** `hold_in_flight(n)` を 4 plug すべてが実装する。**停止点は「カウンタ取得後・DB 実行前」**であり、**製品コードにテスト用フックは 1 つも足していない** (adapter 側のラップだけ)。**これが入ったことで、r2db 2 plug の差集合 (「`enforced` と宣言されているが検査形が無い」) も同時に閉じた。**
- **V2 の除外判定が peer 名から能力判定になった (L7-21)。** **`test_c05` の `adapter.name` 読みは allowlist 3 行だけ**であり、(i)「driver 本体が peer 名で駆動可否を決めない」(ii)「allowlist 以外 0 件」を **AST 走査**が固定する (allowlist 3 行は実コードとして一致することまで assert する)。**`result_items` は両側化し、port の `limit` が 4 plug すべてで load-bearing である。**
- **限界は開示した** (`CONDITIONS.md` C-05 行、port docstring、設計 §10 L8-6): **`hold_in_flight` が作るのは in-process の並行性である** (実ソケット越しは L7-2 まで射程外)、**MitateDB は 1 cell あたり同時 1 操作なので宣言する `concurrency` は「拒否の閾値」であって並列実行能力ではない**、**カウンタのスコープ (配備単位 / credential 単位) の一致は共通 suite では観測できない** (隔離 surface の application が 1 個だから)。

### 2.2 証拠が消えることを機械が検知するようになった (R-9 / L7-23 / L7-22)

- **CI にテスト総数の下限が入った。** `conformance-tests/COLLECTION_FLOOR` の値を `tools/check_collection_floor.py` が `--collect-only` の実測と比べ、**下回れば非 0 終了**する。**3.11 / 3.12 の両 job が pytest の前に走らせる。** **更新は明示コミットのみ** — 下げるには当該ファイルを編集するコミットが要り、理由を commit message に書く。
- **これが守るのは「静かな証拠消失」である。** 受け入れ監査が独立に作った変異 (`collect_ignore_glob` で 238 件を落とす — **終了コード 0・エラー無し**) が **`measured=2036 floor=2274 diff=-238` / EXIT=1** で捕まった。**「読めなかったので緑にしない」側も持つ** (収集エラー / 部分収集 / 行が読めない場合は非 0)。
- **残余リスクは開示済みである** (設計 §6.4): **`COLLECTION_FLOOR` を実測値へ締める経路は完全に人手** (完了ゲート) なので、**ゲートとゲートの間は「(実測 − 下限) 本まで」の削除が検知されない**。**下限が守るのは「大きく減ったこと」であって「1 本も減っていないこと」ではない。**
- **register テストの収集 0 件ガードが入った (L7-23)。** 単独実行が「収集 0 件」を明示した理由付きの赤になり、**それまで空集合同士で静かに緑になっていた 2 本が赤に転じた** — 誰も見ていなかった側が可視になった。**ただしガードが閉じるのは 0 件だけであり、1 件でも収集される部分実行は救えない** (設計どおり)。
- **L7-22 は「開いている」という記述自体が実態と食い違っていた。** 未閉止の 2 件はどちらも現行行に台帳 ID を持っていた (`CONTROL_MAPPING.md:33` の `L4-13, still open`、`CONDITIONS.md:38` の `L4-8, still open`)。**手当てはファイル変更ではなく記述訂正であり、ファイルは 1 バイトも変えていない。**

### 2.3 契約の経緯に 1 hop で辿れるようになった (R-10 (A))

- **`spec/CONTRACT_HISTORY.md` が 29 個の JSON パス anchor を持つ。** 各 anchor は**値の全文の逐語複製**・該当する subordinate ruling の見出し番号・導入版を記録する。**契約 JSON は 0 バイト動いていない** (3 複製の sha256 が付録 A §A.0 と一致)。**PIN も 1 つも触っていない。**
- **常設スキャナが核である。** 付録 A のプロトタイプの正規表現をそのまま移し、契約 JSON を走査して「マーカーを 1 つ以上含む JSON パスの集合」を列挙する。**この集合と companion の anchor 集合の一致**に加え、**引用が契約値と byte 一致すること**、**導入版が `Since X.Y.Z` と一致すること (対象 17 件)**、**ruling が `CCR_DISPOSITION.md` に実在すること**、**重複なし・配下が非空**を register テスト 7 本が固定する。
- **効きの限界は前文と README に明記した。** **契約 JSON の長さは 1 文字も減らない。** **効きは「`spec/` ディレクトリから 1 hop で一次資料へ辿れる」ことに留まる** — 契約 JSON の中から companion への in-band の参照は 1 つも無い (「契約 JSON から 1 hop」ではない)。**本フェーズ後も契約本体に経緯マーカー付きの値が 29 件残る。**
- **機械検査が見ないものも監査が変異で実測した**: **`Since` を持たない 12 節の導入版は無検査**、**ruling 帰属の「正しさ」は無検査で在否のみ**。**どちらも設計 D-4 が明言した範囲であり、だからこそ人手の突合 (全 29 anchor + 指定 3 件の帰属確認) が完了条件に入っている。**
- **(B) (接頭辞の剥離) はフェーズ9 (契約 1.7.0) へ送った** — 18 件の PIN = 依頼者確定文言の再確定が要るので、版が上がるフェーズで扱えば再確定が 1 回で済む (依頼者裁定 2026-09-06)。

### 2.4 配備を起動前に確かめる手段が揃った (R-11。L7-18 が閉じた)

- **両 peer に同型の `ops verify-declarations` が入った。** F 番号ごとの固定終了コード (0 / 1 / 2 / 3〜12) を返し、**1 行 1 検査 + 対象外 3 条件 (F-1 / F-2 / F-12) の 1 行を全経路で出す**。`PlatformDeclarationError` に F 番号の構造化属性 `code` を足した (メッセージ文言は無変更)。**書き手 role 検査は writer role の DSN で実行しないと常に F-13 / exit 11 になる** — この運用要件は手順書に明記した。
- **`tools/deploy_smoke.py` (標準ライブラリのみ) が capabilities → catalog → 1 query を実打ちする。** **引数は環境変数「名」であり、値を取らない。** 終了コードは **1/2/3 = 段ごとの失敗、4 = 段 3 未実施 (空 catalog)、5 = usage**、`--allow-empty-catalog` を明示したときだけ空 catalog が 0 になる。**「空だから 0」で復元検証が緑になる形は採らなかった。**
- **`docs/ops/BACKUP_RESTORE_R2DB.md` と実証記録がある。** platform DB / application DB の両方で pg_dump → pg_restore → `verify-declarations` → smoke を実測し、**復元前後で catalog と 1 query の結果が完全一致**することを確認した (設計 §11.1 に逐語。dump パスは `<DUMP_PATH>` へ置換)。
- **provision script の psql argv から secret が消えた。** 6 箇所を `\getenv` へ移し、**`\set ON_ERROR_STOP on` / `-v ON_ERROR_STOP=1`** を置いた (これが無いと不在ファイルの `\i` も未定義 env の `\getenv` も psql が exit 0 で終わる)。**静的規則は常設テストになり、修正前 6 件 → 修正後 0 件を両方記録した。**
- **L7-19 だけは撤去条件未達のまま据え置きである** — 上流の Starlette に `anyio.abc.BlockingPortal` 参照を直した版が無い。**こちら側の遅れではない。**

### 2.5 性能の基準値ができた (R-12。G-4 の土台)

- **`tools/perf_baseline.py` は使い捨てでないハーネスである。** **plug 一覧は `conformance-tests/registry.json` を正本として読み、plug 名も module 名も手書きしない** (registry に plug が増えれば黙って行が増える — 実測で 14 → 17 行)。**製品コードにカウンタは足していない。**
- **§11.2 に PERFRUN 行 + PERF 14 行を記録した** (`--warmup 20 --n 200`)。**閾値は置いていない** (P-8)。**`op=batch` は単一 entity の atomic mutation batch (操作数 5)、`op=cross_entity` は MitateDB 2 plug のみ** (r2db は `cross_entity_mutation: unavailable` であり、拒否の費用は性能の対象外)。
- **数値の限界は表の注記と README にある**: **HTTP plug の値は ASGI in-process** (実ネットワーク・reverse proxy・TLS を含まない)、**`backend_calls` は往復ではなく呼び出し回数であり、しかも 4 plug で粒度が揃わないので plug 間で比較してはならない** (比較の意味を持つのは同一 plug の版間の差分だけ)、**`--warmup` は出力に残らないので実行コマンド行が記録である**、**計測窓に `BatchOperation` 生成が 2.4〜4.7% 残る**。
- **この基準値が「2 フェーズ安定」の起点である** (計画文書 §7 の 3)。**フェーズ9 と フェーズ10 の完了ゲートが同じ形で差分を添えた後に、退行のゲート化を審議する。**

## 3. クライアント連携状態

**変更なし。一報は送らない** (依頼者判断 2026-09-03 以降不変)。**本フェーズは契約に一切触れておらず、契約 JSON は 3 複製とも sha256 が動いていない。**

**ただし第 14 次から 1 点だけ性質が変わった** — **wire に現れる「値」は変わらないが、MitateDB の application plane が実際に bound を強制するようになったので、宣言された上限を超える要求の「挙動」は変わる** (以前は宣言が `unavailable` で無制限、現在は `LIMIT_EXCEEDED` + `details.limit_class`)。**これは宣言が正直になった結果であり、契約違反ではない** — **宣言 (`/v1/capabilities` の `limits` と `limit_enforcement`) を読む消費者には以前から見えていた情報である。** **実配備は未実施なので、現に影響を受けるクライアントは存在しない。**

**公開 (WP-9) を実行した場合にクライアント側へ影響し得る唯一の項目**は第 14 次 §3 のまま — **有効 credential 2 件 (r2db control / runtime) の revoke + 再発行**である (**rotate は id を保持するため不可**)。**依頼者の実行合図の後にしか起きない。**

## 4. 次の一手 (優先順)

### 4-1. WP-9 公開ゲート (フェーズ7 で唯一残っている WP。着手条件 = 依頼者の実行合図)

**第 14 次 §4-1 の手順 (0〜7) と担当がそのまま有効である。** 正本は フェーズ7 設計 §9 の手順表と作業指示書 §2 WP-9 のチェックリストであり、**本書は複製しない。**

**フェーズ8 が足した前提は 2 つだけである。**

- **畳む worktree が増えた。** フェーズ8 側だけで **`phase8` / `phase8-wp2` / `phase8-wp3` / `phase8-wp4` / `phase8-wp5` / `phase8-wp7`** がある (WP-1 の worktree を含む)。**手順 0.5 (filter-repo の前に全 linked worktree を畳む) の実行時は `git worktree list` で実数を確認すること** — この列挙は 2026-09-07 時点の記録であって網羅リストではない。
- **本フェーズが新設した文書には commit hash が入っている** (本書 §1、設計 §11)。**手順 2 (commit-map による hash 参照の一括更新) の対象になるだけであり、衝突はしない** (設計 §0 最終箇条)。**フェーズ8 は `tools/rewrite_hash_refs.py` を作っていない。**

**フェーズ8 と WP-9 は並行できた** (触るファイルの重なり 0)。**次フェーズも同じ確認を設計段階で行うこと。**

### 4-2. 台帳の開いている項目

**フェーズ7 側 (フェーズ7 設計 §11 が現在形の正本。第 14 次 §4-2 からの差分のみ)**

- **L7-1 — 閉じた** (フェーズ8 WP-1)。C-05 V3 の xfail は 9 → 0。
- **L7-18 — 閉じた** (フェーズ8 WP-4)。両 peer に `ops verify-declarations`。
- **L7-21 — 閉じた** (フェーズ8 WP-1b)。port v1.12 の能力判定化。
- **L7-22 — 閉じた** (実態訂正)。起票時点で既に充足していた。
- **L7-23 — 閉じた** (フェーズ8 WP-2)。収集 0 件ガード。
- **L7-2 (実 socket HTTP plug) — 開いている。フェーズ10。** **フェーズ8 でこの項の重みが増した** — `concurrency` の駆動も性能基準値の HTTP 2 plug も**すべて in-process (ASGITransport) の値**であり、**実ソケット・reverse proxy 越しの並行性と費用は依然として 1 度も測られていない**。L7-2 が入った時点で、C-05 の `concurrency` 開示と §11.2 の表の両方に実 socket 列が加わる。
- **L7-19 — 開いている (据え置き)。** 上流の Starlette 待ち。**こちら側の遅れではない。**
- **L7-20 / L7-3〜L7-17 — 第 14 次 §4-2 のまま。** 変化なし。

**フェーズ8 側 (フェーズ8 設計 §10 が正本)**

- **L8-2 (= L7-19)** 開いている (上流待ち)。**L8-1 / L8-3 / L8-7 / L8-8 / L8-14 / L8-15 / L8-16 は閉じた。** **L8-4 / L8-9 はフェーズ9 の着手材料として保持する。**
- **L8-5 HTTP plug の性能値は ASGI in-process の値である** — 開いている (L7-2 待ち)。
- **L8-6 `concurrency` の駆動は in-process の並行性であり、宣言値は拒否の閾値である** — 開いている (L7-2 待ち)。
- **L8-10 MitateDB の `_measure_request_bytes` は r2db の `check_request` と 2 点異なる** (循環検出が祖先パス限定、未知型を `+8` で受ける) — **開いている (記録)**。契約上の意味には影響しないが同型性の差である。
- **L8-11 `backend_calls` の粒度は 4 plug で揃わない** — **開いている (記録)**。**plug 間で比較してはならない指標である。**
- **L8-12 隔離 profile の bound は、駆動レシピだけでなく他条件の隔離面利用を許す値にする** — **開いている (規律)**。R-A の教訓。
- **L8-13 隔離 profile の `operation_depth` の下で `expected_revision` / `unique_key` は深さを 1 段消費する** — **開いている (記録)**。L8-12 の具体例。

**依頼者判断待ちの新規項目は本フェーズでは増えていない。**

### 4-3. フェーズ9 (契約 1.7.0「宣言と検証」) の着手

**着手条件は 2 つとも満たされた** — **(i) フェーズ8 完了** (「実効 bound の無い peer に新しい要求形を足さない」という条件。**現在は 4 class とも両 peer で実効である**)、**(ii) 依頼者の着手裁定** (これだけが残っている)。

**着手手順は計画文書 §9 のとおりである。** 本フェーズが確かめた進め方をそのまま踏襲する:

1. **計画文書 §5 のフェーズ9 節を設計文書 v1.0 の §1〜§2 に転記する (再導出しない)。** 範囲は **R-2 / R-3 / R-4 / R-5 / R-6 / R-7 / R-8 の一括出荷**である (分けると P-4 に反する)。
2. **設計文書は `docs/design/PHASE9_<name>_V1.md`、作業指示書は `docs/work-orders/WORK_ORDER_PHASE9_<name>_V1.md`。**
3. **契約を触るフェーズなので設計レビューは 2 回である** (計画文書 §9 の 3)。**フェーズ8 は 1 回だった** — 回数を取り違えないこと。
4. **依頼者裁定は設計文書に逐語で記録し、再審議しない。** 逐語は scratchpad の確定文ファイル経由で複製する (常設規律 4)。**フェーズ8 では、この逐語規律の違反を受け入れ監査が 1 件検出した** (port docstring の言い換え) — **「確定文言をファイル経由で複製する」は、docstring や文書に写すときにも掛かる。**
5. **完了ゲートに性能差分を添える** (P-8)。**§11.2 の基準値と同じ形式・同じ `--warmup` / `--n` で取る。**

**フェーズ9 で先に片付くもの (フェーズ8 からの送り)**:

- **R-10 (B) — 29 値の "Since 1.x.0 (subordinate ruling N, …): " 接頭辞 / 挿入句を剥がして companion へ移す** (フェーズ8 設計 §10 L8-4)。**手順が決まっている**: **(i) 対象文の before/after 一覧を依頼者に提示して再確定を得る** (常設規律 4。**18 件の PIN が依頼者確定文言である**)、(ii) `spec/CONTRACT_HISTORY_MANIFEST.json` を置く、(iii) 分離前後の JSON をマニフェストの逆適用後に deep-equal 比較する使い捨て検証 (`tools/` に常設しない)、(iv) 契約 JSON と両 peer の packaged 複製 2 本を同一コミットで同一バイトに更新する、(v) PIN 定数 18 件の書き換え。**1.7.0 に載せれば再確定が 1 回で済む** — これが送りの理由である。
- **R-8 と L8-9 (`versioning.version_binding` の機械可読化) は同じ問題である** (フェーズ8 設計 §10 L8-9)。**10,269 字の単一文字列を版ごとの義務の配列に組み替える案は、`test_contract.py` が「N of those obligations are unconditional」の件数まで assert しているので、再生成一致テストと同時にしか行えない。**

### 4-4. フェーズ10 (配備面の証拠。フェーズ9 と並行可)

**L7-2 (実 socket HTTP plug) と L6-5a (`surfaces` の DB 側単一真実)。** **着手条件だった CI はフェーズ7 で成立済みである。** **フェーズ8 が L7-2 の価値を 2 つ増やした** — (i) `concurrency` の駆動が実ソケット越しにも成立するか、(ii) 性能基準値に実 socket 列が加わるか。**`tools/perf_baseline.py` は名前接尾辞と属性形状が食い違う adapter に対して非 0 終了するので、L7-2 を入れるときはハーネス側のラベル分岐を明示的に足す必要がある** (黙って `asgi-inprocess` とラベルしない設計である)。

## 4-5. 運用規律 (第14次 §4-3 を継承。本フェーズが足したもの)

**第14次 §4-3 の全項 (共有 `.venv` / pre-commit hook / shellcheck・nginx の版差 / ローカル PG の role 設定汚染 / `gh` CLI と job ログ / concurrency の cancel / 並行 worktree の重なり 0 / 完了ゲートは監督単独 / 変異の復元手順 / identity 確認) はそのまま有効である。** 以下は本フェーズが足した分だけである。

- **並行 worktree は 5 本まで実際に回した** (`phase8-wp2` 〜 `phase8-wp5` + `phase8-wp1`)。**設計 §8.1 の「触るファイルの重なり 0」表を実ファイル名で照合してから着手する。** **1 点だけ運用で守ったもの**: WP-1 と WP-4 はともに `MitateDB-api/tests/` にファイルを足すので、**WP-1 は limit 系・WP-4 は ops 系とファイル名を分けた。**
- **`--collect-only` にも PostgreSQL と全 DSN 環境変数が要る。** 収集時に 4 adapter を実構築して接続検証を行うためである。**CI ではこの step を PG 起動 step の後ろに置く。** **なお「使い捨て DB の provisioning が 2 倍になる」という設計初稿の費用開示は誤りだった** — 実測で `pg_database` / `pg_roles` の差分は 0 である。
- **`COLLECTION_FLOOR` の更新規約**: **値は前回 main の実測値であり、監督が完了ゲートで更新する。** **WP の途中で上げない** (他 WP のマージが赤くなる)。**下げるコミットには理由を commit message に書く。** **上げるのも完了ゲートの一部である。**
- **perf harness の実行規約**: **完了ゲート (root suite 終了後) に監督が単独で実行する。** **他の pytest が 0 件であることと、`pg_database` の前後差分が 0 であることを確認する。** **基準値は同じ `--warmup` / `--n` で取る** (op 順で同一 entity の状態が育つので、`--n` が異なる実行同士は比較できない)。**異常時の traceback には作業機の絶対パスが出るので文書に貼らない。**
- **`hold_in_flight` の待ち上限は 30 秒である。** **停止点に到達しない回帰はハングではなく理由文付きの `AssertionError` になる。** **CI の `conformance` job にも `timeout-minutes: 30` が入った** — 壊れた前提は runner の上限まで待つのではなく赤として出るべきである。
- **代理指標を使わない。** **分岐の条件は、その分岐が実際に依存している性質そのものを読む** (宣言された能力を読む、など)。**別の性質で代用すると、代用元が動いた瞬間に静かに壊れる。** 本フェーズでは `test_c04` の `_operation_depth_enforced()` がこれに当たり、MitateDB が `operation_depth: enforced` になった瞬間に壊れた (設計 §10 L8-14)。
- **`pg_database` の前後差分をゲートで取る。** 並行実行中は他 WP 由来の DB が出現して帰属できなくなるためである (WP-5 のレビュー中に実例が出た)。
- **`public_value_scan.py` は `git ls-files` ベースなので未追跡の新設ファイルを走査しない。** **新設ファイルは明示引数で走査する** (pre-commit hook は staged なファイルを見るので commit 経路は塞がっている)。

## 5. 教訓の追加 (前書全項継承に追加)

- **実装報告の「grep で確認した」は、複数行の呼び出しに対しては信用できない。** WP-1b の報告は「`update` + `filters` を `transact` 経路へ回す変更の影響は 0 箇所」と書いたが、**単一行の正規表現が本リポジトリの主流の書式 (複数行の呼び出し) を検出できていなかった** — **AST 全数走査による実測は 4 ファイル 12 箇所**である。**結論そのもの (影響ゼロ) は変わらなかったが、根拠の手順が誤っていた。** **「grep で 0 件だった」を根拠として受け取るときは、その grep が何を見落とし得るかを聞く。** 同種のものは WP-2 の「代替コマンドで実行した」(実行結果が報告本文に無かった) と WP-5 の「復元 sha が納品物と不一致」(差分は docstring のみだった) であり、**3 件とも実装物の欠陥ではなく報告の事実誤認である。** **レビューと監査が「主張 vs 実測」を独立項目として突合する形 (常設規律 3) が、この 3 件すべてを拾った。**
- **レビュー・監査が自前で作る変異が、報告の変異では見えないものを出す。** 本フェーズで最も重い発見は 3 件とも自前変異である: **(i) 監査の変異 B / B2** — `result_items` の初稿レシピでは **r2db 2 plug で port の `limit` を捨てても suite が全緑**だった (是正してレシピを改めた)。**(ii) 監査の変異 B (WP-4)** — `_verify_declarations_checks` が「pinned」と名指しされているのに同型性表に行が無く、**MitateDB 側のループ変数名を改名しても全緑**だった。**(iii) 監査の変異 B (WP-2)** — `collect_ignore_glob` による**終了コード 0・エラー無しの静かな証拠消失**を floor 検査が捕まえることの独立実証。**「完了条件が満たされている」ことと「その完了条件を壊す変異が実際に赤になる」ことは別の命題であり、後者は報告された変異だけでは確かめきれない。**
- **port に optional フィールドを足したら、「配線されている」ではなく「捨てると赤になる」まで実測する。** 上の (i) がその例である — **4 plug すべてで N 成功 / N+1 拒否を観測していても、新フィールドが位置を決めていなければ、そのフィールドは load-bearing ではない。** **L7-21 の趣旨 (「偽の宣言が赤になる形にする」) は、除外リストを消すだけでは達成されない。** 是正後のレシピ (表に bound+1 行を 1 度だけ入れ、`limit=bound` / `limit=bound+1` で分ける) は**実行数側に位置決定の余地を残さない**形である。**設計 §10 L8-15。**
- **隔離 profile の bound は「駆動レシピが通る値」では足りない。** R-A がその実例である — `operation_depth=4` は駆動レシピには十分だったが、**同じ隔離面を使う他の条件 (C-04 の `delete` probe) の要求構造が通らず、MitateDB-http が赤になった**。**bound を選ぶときは「この bound の下で、隔離面を使う (あるいは将来使う) 他の条件の要求構造が通るか」を先に確認する。** **設計 §10 L8-12 / L8-13。**
- **停止点の位置は、指示書の言葉ではなく実装の構造が決める。** 作業指示書の逐語表は MitateDB の `hold_in_flight` のラップ対象を「操作メソッド入口」としたが、**その形では gate を実行する前に止まり、カウンタが増えていない** — 停止点要件を満たさない。**実装は `_limit_gate` 自体のラップになり、監督が追認した。** **「カウンタの内側で止まる」という要件は逐語表よりも上位である** — **要件を満たす形が指示書の記述と違ったら、指示書を訂正註で直す** (本文は書き換えない)。
- **「宣言だけ先に `enforced` にする」を禁じる規律 (P-3) は、`xfail(strict=True)` が機構として担保する。** 実装が先なら XPASS で赤、削除が先なら通常の assert が赤になる。**この赤を「順序の合図」として使い、`strict=True` を落として回避しない** — 本フェーズは 9 組すべてをこの形で撤去した。**「機構が順序を強制する」形は、規律を文章で書くより強い。**
