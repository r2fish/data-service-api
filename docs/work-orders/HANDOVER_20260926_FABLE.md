# 引き継ぎ — 2026-09-26 (R-111: MitateDB http conformance adapter の制御 credential 修復経路の修正。Class B、規模 M、1 WP)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`)。前書は `HANDOVER_20260925_FABLE2.md`。本書は `docs/work-orders/HANDOVER_20260926_FABLE.md`。以下 `RM` = `docs/design/ROADMAP_POST_PHASE7_V1.md`、作業指示書 = `docs/work-orders/WORK_ORDER_R111_CONTROL_ACTOR_REPAIR_V1.md`。

記録: `docs/archive/docs/work-orders/HANDOVER_20260925_FABLE.md`

## 1. 現在地

- 本チャット (2026-09-26) は `RM` の R-111 だけを扱った。worktree r111、branch r111、基点 local main `ffb0943`。作業指示書 v1.0、1 WP (作業指示書の WP-1)、**Class B・規模 M** (監査担当は起動しない。`OC` §1.13 の 74)。
- 役割とモデル: explorer (sonnet、`claude-sonnet-5`)、drafter / reviewer (opus、transcript の `"model"` 欄は `claude-opus-5-5`)、implementer (sonnet)。commit・完了ゲート・merge は監督。
- 直したもの: MitateDB http conformance adapter (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`。socket adapter は継承し未変更) の 3 点 (作業指示書 §1.5 の決定 1〜3)。新規 peer 単体テスト 5 件 (`MitateDB-api/tests/test_conformance_adapter_mitatedb_http_control_actor.py` の T1〜T5)、変異 6 件 (M1〜M5 + M4b) すべて期待どおり。
- 集計行:
  - `MitateDB-api/tests`: `pt: 1480 passed, 2 subtests passed in 142.28s (0:02:22)` (基点 1475 + 5)
  - 部分集合 `-k "not r2db" -n 5 --dist loadgroup`: 実装担当 3 回 `pt: 775 passed` (126.96 s / 135.61 s / 129.90 s)、6a の計測 2 回 (1 回目 `pt: 775 passed in 130.48s (0:02:10)`、再計測 `pt: 775 passed in 129.41s (0:02:09)`)、監督 1 回 `pt: 775 passed in 130.84s (0:02:10)` — 計 6 回すべて failed 0
  - `-k "not MitateDB"`: `pt: 776 passed in 136.72s (0:02:16)` (基点と同数)
  - 完了ゲート (監督、solo、使い捨てクラスタ): `gate: 4203 passed, 2 subtests passed in 393.93s (0:06:33), judge=PASS, pg_database/pg_roles diff 0, label r111 (基点 main ffb0943 の 4198 + 新規 5; `conformance-tests/COLLECTION_FLOOR` は 4198 のまま据え置き -- bump は `conformance-tests/` のパスで本変更セットを Class C に上げるため (`tools/change_class.py`)、次の Class C / D の変更セットで 4203 に上げる)`
- 台帳 `RM` **v1.123** (R-111 閉止)。`security/CONTROL_MAPPING.md` は **3.4 のまま** (制御は変わらない)。契約 **1.11.0 のまま**。
- 本書は merge 前に起草した。main への merge は §4 の報告の後 (作業指示書 §3)。
- push は停止中 (GitHub 課金上限)。ローカル commit と main への merge のみ。
- 本チャットの裁定の材料は監督チャットの scratchpad の `rulings-r111.md` (「裁定」節に逐語で転記済み)。

## 2. 本チャットで閉じたもの

| 件 | 結果 | 記録 |
|---|---|---|
| R-111 の診断 | 呼び出し連鎖と原因 (probe が制御面の 413 `LIMIT_EXCEEDED` を受ける → `_control_actor_is_live` が「死んだ credential」と読む → 破壊的 `ops reset` → 呼び出し側の handle が失効 → 401 `AUTH_INVALID`) | 作業指示書 §1.2・§1.3、§5 完了条件 0 |
| 決定 3 点 | (1) probe の拒否分類 (auth 系 4 code だけ修復)、(2) 内部経路は probe せず auth 系拒否でだけ修復して 1 回再送、(3) 隔離 copy と親の cache を 1 object に | 作業指示書 §1.5 |
| 却下 4 案 | (a) test 側の再試行、(b) 上限 200 の引き上げ、(c) sleep で待つ、(d) server 側の窓を per-credential に | 作業指示書 §1.6 |
| 監督の追加 | 変異 M4b (完了条件 4 の `AUTH_INVALID` 脚。1 条件 2 変異) と完了条件 6a (実装後の 60 秒窓の最大要求数、合否条件ではない) | 作業指示書 §2.14、§5 |
| 6a の再計測 | 制御面の窓 (`control_requests_per_minute`) に課金される送信だけの worker 別最大: gw0 17 / gw1 4 / gw2 176 / gw3 163 (上限 200)。1 回目の計数 (gw2 204 / gw3 174) は別窓の `/v1/audit/query` を含む上界で、レビュー F1 により無効 | 作業指示書 §5 完了条件 6a |
| 既存 docstring の 2 行 | adapter `:18` の一般語 decision と `:1796` の `WP-1 M-4` (`docs/design/CONFORMANCE_ADAPTER_V1.md` の M-4) は本 WP で書いた文ではないので現状維持 (監督裁定) | — |
| 作業指示書 §1.3 F3 の r2db の記述 | 誤り (r2db の内部 3 系統も公開 probe を通る)。訂正註を追記 | 作業指示書 §4 |

## 3. 次の一手

R-111 閉止までの残り手順は作業指示書 §3 (完了ゲート → `RM` v1.123 の【追記】 → `tools/dev/finalize.py --tools-tests` で main へ merge)。本書は監督が `docs/work-orders/` へ置く。前々書の `docs/archive/docs/work-orders/` への回転は本変更セットで済 (`OC` §1.16 の 78)。

R-111 閉止後の残件 (前書 §3 の「merge 後の残件」から R-110・R-111 を除いたもの):

- **CI の sqlite 版の実測**: push 再開後。pin テストは `MitateDB-api/tests/test_sqlite_version_floor.py` (>= 3.30)。
- **レビュー観察 2 件** (起票しない。前書の「裁定」節): cursor 付き要求 1 回ごとに catalog を 2 回余分に読む / `tools/contract_catalog.py --help` が書き込む。
- **push は停止中** (GitHub 課金上限)。
- **`conformance-tests/COLLECTION_FLOOR` の 4198 → 4203**: 次の Class C / D の変更セットで上げる (本セットは Class B に留めるため据え置き。完了ゲートは 4203 ≥ 4198 で有効)。
- **R-110 由来の観察 2 件** (起票しない。前書の「裁定」節): F9 = 欠陥が 2 つある要求で拒否コードの判定順が両 peer で違う (契約は複数欠陥の優先順位を定めない) / schema 操作 (`alter_field` / `create_index`) の未知 field / index の拒否コードが両 peer で不一致 (1.11.0 の規則の範囲外)。

台帳 `RM` §8 の未着手項目の着手順は依頼者裁定。本チャットの観察 2 件 (r2db の制御 stack 作り直し、enable の path 文字列の複製) は起票せず「裁定」節にだけ残す。

## 4. 依頼者判断待ち・未決

- **R-111 の merge 前の報告**: 契約に触れないので Q-4 の形は不要。監督が完了ゲートの集計行と diff stat を添えて報告する。**本書起草時点では報告前。**
- 役割定義の `model:` の変更は不要 (本チャットでも `opus` 別名は `claude-opus-5-5` に解決)。毎チャットの最初の Opus 起動で transcript の `"model"` 欄を実測して報告する (前書 §4)。

## 5. 本チャットで足した運用上の教訓

1. **部分集合の flake は「誰の credential が誰の操作で失効したか」を traceback の呼び出し連鎖で辿ると 1 回の読解で原因に届く** (probe → 413 → 破壊的 reset → 401)。
2. **監督の枠に書く peer の記述は起草者に実測させる。** 枠 F3 の「r2db は公開 `control_credential()` だけが probe する」は誤りだった (起草者の疑義とレビュー F2 が両方で正した。作業指示書 §4)。
3. **一時計測の計数は「どの窓に課金される要求か」を分けて数える。** `audit_query` は別窓 (`audit_requests_per_minute`)。全体計数 204 は上界、絞った計数 176。
4. **上限 200 の制御面窓に対し、MitateDB-http 群の worker は部分集合で最大 176 送信/60 s (制御面の窓に課金される送信のみ。worker 単位の計数と server の窓の 1:1 は未検証なので余裕は主張しない — 作業指示書 §5 の 6a)。** 再発時は要求の内訳 (path 別) を先に測る。
5. **explorer は pytest を回さない** (役割定義)。再現実行は監督が背景で回し、log を渡す形で足りた。

## 裁定

全件を載せる (`OC` §1.15 の 77)。出所は監督チャットの scratchpad の `rulings-r111.md` (監督、2026-09-26) の逐語である。

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 探索担当 (sonnet): 原因を断定する一次資料なし、構造的欠陥 2 点 (shallow copy の制御面共有、グローバル rate 窓) | 採用 (監督が直読みで連鎖を確定: `_control_actor_is_live` が全拒否を「死亡」と読む F1) | 探索は所在の材料。判断は監督 |
| 起草担当 疑義 1: 枠の行番号 3 箇所がずれ | 直した (起草者が実測値を記載) | — |
| 起草担当 疑義 2: F3 の「provision/issue 等」は MitateDB では制御面を通らない。内部利用は 3 箇所 (`_audit_query_status` / `audit_visibility_lag_ms` / tamper vector) | 直した (決定 2 の適用先を 3 箇所に確定。:3056 の tamper vector も含める) | 内部で `self.control_credential()` を呼ぶ箇所 0 件を完了条件 3 に |
| 起草担当 疑義 3: 決定 2 は r2db の現状を超える (r2db は内部 3 系統でも公開 probe を使う)。定期再構築は採らない | 採用 (r2db の不足は写さない。「§1 に無い機構を足さない」を禁止事項に) | 依頼者原則 (制約で回避しない) |
| 起草担当 疑義 4: F4 の「r2db は cache が親 1 箇所」は一部のみ成立 | 直した (完了条件 5 を「読む箇所と書く箇所の両方」に) | — |
| 起草担当 疑義 5: 完了条件 6 の「774 passed」は 775 node の誤り、完了条件 7 の「件数不変」は新規 5 件と矛盾 | 直した (failed 0・着手時実測、基点 + 5) | — |
| 起草担当 疑義 6: 完了条件 4 は M4 (LIMIT_EXCEEDED の脚) のみ | 直した (監督が M4b を追加。1 条件 2 変異) | 非空振り |
| 起草担当 疑義 7: `__init__` を通さない単体テストの前例なし、T5 が PostgreSQL 無しで組めない可能性 | 採用 (`object.__new__` の形を指示、組めなければ上げる) → 実装で組めた | — |
| 起草担当 疑義 8: `_ISOMORPHIC_TARGETS` の 4 hook に触れると Class C | 採用 (禁止事項に明記) → 実装は触れていない (レビュー確認 3) | — |
| 実装担当 判断 1: 決定 3 を holder object 方式で実装 | 採用 | 指示書の裁量内。レビュー確認 3 で親と iso が同一 object を見ることを確認。r2db の bound-method 束縛より強い |
| 実装担当 判断 2: tamper vector の in-band enable を `_privileged_control_send` 直接に置換 | 採用 | レビュー確認 2: 同じ HTTP 要求 (POST .../enable、body なし)。消費者は C-13。path 文字列の 2 箇所目は観察 |
| 実装担当 判断 3: `_control_actor_is_live` を残す | 採用 | 決定 1 が method 名を明示 |
| 実装担当 判断 4: 6a は worker 別の観測値 | 直した (レビュー F1 と併せ再計測) | — |
| コードレビュー F1: §5 6a の記録が計測より強い (audit_query を含む上界、worker 単位) | 直した (記録を書き直し、制御面の窓に課金される送信だけで 1 回再計測) | 余裕の実測を台帳に残す |
| コードレビュー F2: `_audit_query_status` の comment「identical」と作業指示書 F3 の r2db の記述が誤り | 直した (comment 修正 + §4 訂正註) | 監督の枠 F3 が誤りだった (教訓) |
| コードレビュー F3: docstring の経緯語「WP-1 M-4's contract」 | 直した | §2.13 |
| コードレビュー F4: テスト comment の「decision-3」 | 直した | — |
| コードレビュー 観察 (確認 1・7): r2db は `_CONTROL_REBUILD_THRESHOLD = 40` で制御 stack を作り直して窓を空にする。MitateDB には無く、窓が詰まれば `LIMIT_EXCEEDED` のまま表に出る | **観察** (起票しない): 2 問 = (a) 検査器の穴ではない、(b) 利用者は気づかず §0.1 も破らない。r2db 側の作り直しは制約の回避に当たる既存機構だが、部分集合 3/3 と全体ゲートが緑である現状で起票の実益なし。再発時に再起票 | 依頼者原則 (制約で回避しない) と整合するのは MitateDB 側の形 |
| コードレビュー 観察 (確認 2): enable の path 文字列が 2 箇所に複製 | **観察** (起票しない) | 保守上の点。利用者は気づかない |
