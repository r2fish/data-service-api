# Q4 フェーズ 作業指示書 — 宣言と適用状態の根拠を DB 側の一次情報へ寄せる

- 版数: **v1.1 (2026-09-05、監督裁定 D-2 (h) — 書き手 role の宣言表化 — の追補を反映)**。v1.0 からの変更点: **WP-1 に完了条件 19〜23 と変異 16〜20、WP-2 に完了条件 21〜22 と変異 18〜23 を追補した** (既存の条件番号・変異番号は変えない)。**起草者疑義 6 点への監督裁定 (2026-09-05) 反映済み** (`{scratchpad}/rulings-q4-workorder.md` が正本)。**D-2 (h) の裁定は `{scratchpad}/rulings-q4-writer-roles.md` が正本**。**同日追補 (版数据え置き、2026-09-05 の WP-1 / WP-2 差し戻し裁定 `{scratchpad}/rulings-q4-wp12-rework.md` と確定文 `{scratchpad}/q4-f3c-and-amendments.md`)**: **§1.2 の D-2 要約に `audit_writer_roles` を加え、§9 の確定文言表に F-3c / F-13 を加え、WP-1 に完了条件 24〜32 / 変異 21〜28、WP-2 に追加条件 23 / 変異 24〜31 を追補した** (既存の条件番号・変異番号は変えない)
- 版数履歴: **v1.0 (2026-09-05、起草)**
- 正本設計: `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` (**v1.3 — 依頼者裁定 U-1/U-2/U-3 と §8 の migration 番号の割当に加え、監督裁定 D-2 (h) (書き手 role を宣言表 `audit_writer_roles` で特定する) を反映した版**)。**本書は WP 分割と発注のみを扱う** — 裁定の根拠・却下案・実装の具体形・fail-fast メッセージの骨子は設計文書が正本であり、本書はそれを重複させない。**設計と本書が食い違ったら設計が正**であり、本書の誤りとして監督へ差し戻すこと
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260904_FABLE2.md` (第13次)。**契約は 1.6.0 のまま (本フェーズは契約無変更、U-1)**。ブランチ `q4-db-single-truth`
- 体制: Fable 監督/判断/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー/受け入れ監査
- 先行作業指示書: `docs/work-orders/WORK_ORDER_PHASE6_CONTRACT_160_V1.md` (v1.3)。**§0.1 の常設規律 7 項目・完了ゲートの実測規律・禁止事項・コミット規律・「完了条件番号 → 変異」対応表の書式を本書がそのまま引き継ぐ**
- **確定文言の所在**: §9 を見よ。**依頼者裁定 (U-1 / U-2 / U-3 と migration 番号の割当) は `{scratchpad}/rulings-q4-requester.md` が正本**であり、実装者はそこから逐語複製する (常設規律 4)。**fail-fast メッセージの文面は設計 §3.8 の一覧が正本**であり、実装はそこから複製する

---

## 0. 問題設定

**「宣言 (または適用状態の判定根拠) を持つプロセスと、値が実際に効いているプロセスが別で、どちらも他方を検証できない」構造を解消する。** 依頼者裁定 (2026-09-05) により次の 3 件を 1 つのフェーズとして扱う。

| 台帳項目 | 内容 | 閉じ方 | WP |
|---|---|---|---|
| **Q4 案 B** (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2) | `visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合 | 書き手 role の PostgreSQL role 設定 (D-1) + platform 宣言表 (D-2) | WP-1 / WP-2 |
| **L6-5a** (`PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11) | `surfaces` の 2 プロセス間ドリフト | platform 宣言表の 1 行に統合 (D-2) | WP-1 / WP-2 |
| **L6-20 (f)** (同 §11) | per-application upgrade script の運用性 (台帳 / 一括適用 / 可視化) | application DB 内の台帳表 (D-3) + `ops upgrade-applications` (D-4) + `ops upgrade-status` (D-5) | WP-3 / WP-4 |

**契約は 1.6.0 のまま変えない** (依頼者裁定 U-1)。設計 §6.2 (契約に載せる場合) は「採用せず」として記録に残す (WP-5)。

---

## 0.1 常設規律 (フェーズ5 §0.1 / フェーズ6 §0.1 を逐語継承。全 WP に適用)

1. **空振り禁止**: 新規テストは観測対象が 1 件以上あることを assert する。「このテストは X を固定する」と書くなら、X を壊す変異を赤にした実測を報告に添える。
2. **変異先行**: 完了条件 1 項目につき、それだけを壊す変異を 1 つ対応付ける。対応する変異の無い完了条件は残さない。
3. **主張は実測の後**: docstring / CONDITIONS / runbook の断言は変異結果を得た後に、その数値・テスト名を引用して書く。
4. **確定文言はファイル経由**: 依頼者裁定文は `{scratchpad}/rulings-q4-requester.md` から、fail-fast メッセージは設計 §3.8 から複製し、言い換えない。**文字列ピンのテストを置く** (§4 各 WP の完了条件)。
5. **静的規則は逐語プロトタイプの後に確定する**: `{scratchpad}/proto_ledger_scan.py` / `proto_ledger_scan.out` が現状のプロトタイプであり、規則 (b) に合わせた改訂と再実測は **WP-0** が行い、結果を設計 §10 へ貼る。
6. **同型性テスト**: 両 peer に同名で置くヘルパは対応表駆動の同型性テスト (両 peer 同名 `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`) で一致を固定する。**peer 間でコードを共有しない** (依頼者裁定 2026-09-03)。
7. **設計外の拡張は実装前に上げる**: 設計に無い検査・機構は実装前に報告し、監督裁定を得てから実装する。**ただし置き場 3 件 (パッケージ定数 / ms ヘルパ / ops テスト) は監督裁定 2026-09-05 で確定済みであり、改めて上げる必要は無い** (§7 の 7)。

**対応表の書き方 (規律 2 の運用)**: 各 WP の末尾に「完了条件番号 → 変異」の対応表を置く。**テストで固定される条件にはそれだけを壊す変異を 1 つ**対応付ける。**文書・記録・設定・無変更の条件には変異を作らず、「監査が何を何と突き合わせるか」を当該条件の本文に「監査照合」として明記する**。各 WP の最後の完了条件は「**対応表に対応の無い行が無いこと**」というメタ条件である。

---

## 0.2 速度規律 (2026-09-04 依頼者承認、本フェーズも継承)

- **実装担当は peer 別 suite だけを回す** — `r2db-api/tests` / `MitateDB-api/tests`、および担当 WP が触る conformance ファイル。**root suite を回さない。**
- **root suite (`./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`) は監督の完了ゲート 1 回のみ。** ローカル PostgreSQL は `max_connections = 300` が前提。
- **変異は実装担当が全変異を実測する。** コードレビュー (Opus) は**実装報告に無い変異 1〜2 種だけ**を自分で試す。受け入れ監査は監督のゲートログを突合し、suite を再実行しない。
- 設計レビューは契約無変更のため **2 本で完了済み**である (依頼者裁定の帰結)。

---

## 1. 本書が発注する確定事項

### 1.1 依頼者裁定 (逐語。`{scratchpad}/rulings-q4-requester.md` が正本)

> U-1: per-application の upgrade 適用状態は **peer-local に留める**。共通契約は無変更 (1.6.0 のまま)。可視化は両 peer の `ops upgrade-status` (provision DSN) のみ。§6.2 (契約に載せる場合) は「採用せず」として記録に残す。
>
> U-2: 台帳表に対する runtime role の権限は **SELECT のみ付与**。data-plane は cell を開く時点で台帳の番号集合をパッケージ定数 (最新 per-app 番号集合) と比べ、未適用があれば最初のリクエストを待たずに `ops upgrade-applications` を示す明示メッセージで SERVICE_UNAVAILABLE を返す。代償 (パッケージ定数と migrations/ の同期義務) は §10 の三者一致静的検査で固定する。
>
> U-3: 宣言 (timeout catalog と宣言表) の読み出しは **起動時スナップショット**。ops で変えたら両プロセス再起動 (縮めるときは data-plane 先、伸ばすときは control 先)。
>
> 帰結 (監督): 契約に触らないので設計レビューは 2 本で完了。作業指示書へ進む。migration 番号は本フェーズ内で r2db 0008 (platform 単発) / 0009 (per-app 台帳 init)、MitateDB 0007 (platform 単発) / 0008 (per-app 台帳 init) を割り当てる (L6-2: 本フェーズが先に出荷する。以後の予約ではなく本フェーズの割当)。

### 1.2 設計 §3 の確定事項 (要約。根拠は設計が正本)

- **D-1**: 書き手 role (`*svc_api` / `*svc_controlplane`) の `statement_timeout` / `idle_in_transaction_session_timeout` を **PostgreSQL の role 設定**に固定し唯一の真実とする。書き手プロセスはセッション `SET` をやめ、起動時に **(i) 宣言の存在と有効性 (ii) 実効値の ms 整数一致**を二重検査する。control は `pg_db_role_setting` から `visibility_lag_ms` を導出する。**timeout の 4 env は廃止**し、定義されていれば値によらず fail-fast する (検査対象は composition root に渡された env mapping)。
- **D-2**: platform 宣言表 `<registry>.platform_declarations` を新設し、`surfaces` と `audit_coalescing_window_ms`、**および `audit_writer_roles` (D-2 (h)) の単一の真実**とする。**`audit_writer_roles` 行は platform 単発 migration だけが書き**、`ALTER ROLE` を発行した role 名と**同じ psql 変数から同じトランザクションで** seed する。**書き手プロセスは起動時に自 `current_user` がこの宣言に含まれることを確認し (F-13)、control は宣言された各 role の catalog から `visibility_lag_ms` を導出する** — **role 名をコード内の命名規則から導出する経路は両 peer から撤去する**。`key` は名前付き CHECK (許容集合に `audit_writer_roles` を含む) で閉じ、値の検証は Python 側に一本化する (書き込み時と読み出し時が同じ関数を通る。`audit_writer_roles` は非空・重複なし・PG 識別子妥当で、落ちれば F-4b)。**`*_DATA_BASE_URL` / `*_CONTROL_BASE_URL` は廃止**し、定義されていれば fail-fast する。**フェーズ6 監督裁定 5 (stale な `*_CONTROL_BASE_URL` を黙って無視する) を上書きする。**
- **D-3**: per-application platform upgrade 台帳 `public._<peer>_platform_upgrades` を各 application DB に置く。**テンプレート `0003` の改訂と per-app upgrade script を対で出す。** 台帳表に RLS は付けず、代わりに **両 peer の backend の bookkeeping 除外集合**と **r2db の `_r2db_missing_rls` の除外名**を同じ WP で拡張する。以後の per-app script の規律 (自番号の台帳 INSERT / 冪等 / `\q` 経路を持たない / 命名) を**静的規則テスト**で固定する。
- **D-4**: `ops upgrade-applications` を両 peer に新設する。**provision DSN のみで動く。** 未適用は**集合差**で定義する。**1 つの DB の失敗で止めず全 DB を回し、失敗した DB を列挙して非 0 で終わる。** 失敗した application ごとに `REVOKE <developer_role> FROM <provision role>;` を出力に含める。
- **D-5**: `ops upgrade-status [--application <id>]` を両 peer に新設する。**既存の application 一覧コマンドは変更しない。**
- **D-6**: `security/CONTROL_MAPPING.md` 3 行、runbook 2 本 + `r2db-api/deploy/env/*.example` 2 本 + `MitateDB-api/docs/cloud-run-cloud-sql.md`、正本 2 文書への閉止注記、設計 §10 / §12 / §13 の確定。

---

## 2. 範囲外 (本書では扱わない)

以下は**列挙のみ**である。本書の WP は一切触れない。

1. **契約への露出** — U-1 で「載せない」が確定した。`spec/` に 1 バイトも触れない。設計 §6.2 は「採用せず」として記録に残すのみ (WP-5)。
2. **監査読み手 role (`*_auditreader`) の timeout** — 宣言は書き手についての主張である (設計 §1.5 の 3)。
3. **provision role (`r2dbsvc_control` / `mitatedbsvc_provision`) への timeout 設定** — 長時間 DDL を流す役であり、置くと migration 自体が止まる (設計 LQ4-6)。
4. **`_r2db_schema_revision` の runtime `UPDATE` 付与と MitateDB 側の非対称** (LQ4-8) — 本設計の対象外。「ついでに」揃えない。
5. **r2db の `_validate_surface_base_url` 2 コピーの統合** (L6-17 / LQ4-7) — 動機は強まるが本フェーズの発注事項ではない。**統合したくなったら実装前に監督へ上げる** (常設規律 7)。 **【監督裁定 2026-09-05 (WP-1 差し戻し) で上書き】: 本フェーズで統合する — `platform_declarations.validate_surfaces_value` に URL 検証の本体を置き、`main.py` / `control_main.py` / `ops.py` の 3 か所はそれを呼ぶ (設計 v1.3 §3.10 同型面、§12 LQ4-23。rulings-q4-wp12-rework.md §2)。**
6. **`pg_advisory_xact_lock` による一括適用の並行実行保護** (LQ4-18) — 本設計では決めない。記録に留める。
7. **一括適用失敗時の membership を「次回実行の先頭で自動的に掃除する」形** (LQ4-14) — 本フェーズは ops 出力に `REVOKE` 文を含める形で扱う。
8. **接続プーラ下での起動時検査の射程** (LQ4-15) — 現配備にプーラがあるかは未確認である。開示のみを行う。
9. **1.4.0 alias の除去 / フェーズ7 (a)-(e) / 実機適用** — 本フェーズの射程外。

---

## 3. WP 分割 (依存順)

| WP | 対象 | 内容 | 依存 | 並行 |
|---|---|---|---|---|
| **WP-0** | **共通 (両 peer 同時 1 コミット)** | 静的規則スキャナの改訂と両 peer への設置 + 同型性対応表への行追加と pin テスト名の改称 + ms 正規化ヘルパ (`ms_from_pg_timeout_text`) の src 引き上げ | — | — |
| **WP-1** | **r2db** | `0008` (platform 単発: `ALTER ROLE` 4 文 + 宣言表 + 窓の seed) + composition root の env 廃止と DB 読み + 書き手の二重検査 + `ops set-platform-timeouts` / `declare-surfaces` / `declare-coalescing-window` / `show-declarations` | WP-0 | **WP-2 と並行 worktree 可** |
| **WP-2** | **MitateDB** | 同 (`0007`) | WP-0 | **WP-1 と並行 worktree 可** |
| **WP-3** | **r2db** | `0003` テンプレート改訂 + `0009` (per-app 台帳 init) + backend 除外集合 + RLS 監視ビュー + runtime `SELECT` + cell open 時検査 + `ops upgrade-applications` / `upgrade-status` | WP-1 | **WP-4 と並行 worktree 可** |
| **WP-4** | **MitateDB** | 同 (`0008`。**`0006` の backfill を含む**) | WP-2 | **WP-3 と並行 worktree 可** |
| **WP-5** | **共通 (文書)** | conformance HTTP adapter の**最終確認のみ** (実体は WP-1 / WP-2 の成果物) + 文書一式 + ハンドオーバー第14次 | WP-0〜4 | — |

**依存関係の根拠 (各 WP 1 行)**

- **WP-0**: WP-1〜WP-4 が新設する同名ヘルパを突き合わせる機構 (対応表) と、WP-3/WP-4 の per-app script が満たすべき静的規則を**先に置く**ため。**ms 正規化ヘルパ (`ms_from_pg_timeout_text`) は WP-1/WP-2 の二重検査が両辺で使う**ので、src への引き上げも先行する。
- **WP-1**: WP-0 が src に置いた ms 正規化ヘルパと対応表の行を消費し、r2db の宣言経路を DB 側へ寄せる。**MitateDB 側と触るファイルが完全に分離する** (`r2db-api/` 配下のみ) ため WP-2 と並行できる。
- **WP-2**: 同 (MitateDB 側、`MitateDB-api/` 配下のみ)。**両 peer の対応表 (`tests/test_audit_query.py::_ISOMORPHIC_TARGETS`) は両 peer に同内容で存在するため、WP-1/WP-2 が同時に行を足すと衝突点になる** — **監督裁定 (2026-09-05)**: **対応表への行追加は「対」の後半 WP のみが行う。WP-2 が WP-1/WP-2 のヘルパ行を、WP-4 が WP-3/WP-4 のヘルパ行を追加し、pin テスト名の行数を改める。WP-1 / WP-3 は対応表を触らない。WP-0 は静的スキャナと ms ヘルパの行だけを追加する。** これで並行 worktree (WP-1‖WP-2、WP-3‖WP-4) の衝突は無い。**マージ順は WP-0 → WP-1 → WP-2 → WP-3 → WP-4 → WP-5。**
- **WP-3**: `0009` は `0008` の次番号であり、台帳 init script は WP-1 が出す platform 単発 migration の後に当たる。cell open 時検査 (U-2) は WP-1 が整えた data-plane の起動経路の上に乗る。
- **WP-4**: 同 (`0008` は `0007` の次番号)。**MitateDB のみ `0006` の backfill を持つ** ため r2db と非対称である。
- **WP-5**: WP-1〜4 の実測 (テスト名・集計行・実際に採った形) を記録するため最後に置く。**conformance HTTP adapter の追随は WP-1 / WP-2 の成果物であり** (設計 §11 WP-B。**監督裁定 2026-09-05**)、**本 WP はそれが最終形であることの確認と記録だけを行う — adapter のコードを本 WP で変更しない。**

**両 peer 同時性**: D-1 / D-2 / D-3 はいずれも「両 peer が同じ安全成果を同じ形で満たす」対象である (設計 §2 制約 4)。**片 peer だけ出荷した中間状態を長く置かない** — WP-1/WP-2 と WP-3/WP-4 は**連続して**回すこと。

各 WP は **Sonnet 実装 → Opus コードレビュー (変異注入必須) → 差し戻し → Opus 受け入れ監査**の順で回す。

---

## 4. 各 WP の発注

### WP-0 共通基盤 (静的規則スキャナ + 同型性対応表 + ms 正規化ヘルパの src 引き上げ)

#### 目的

WP-1〜WP-4 が乗る**共通の型枠**を先に置く — (a) 両 peer の src に ms 正規化ヘルパを 1 定義ずつ置き、(b) per-app upgrade script の規律を静的規則テストとして両 peer に置き、(c) 同型性対応表を本フェーズの対象へ広げる。**製品の挙動は変えない。契約に触れない。**

#### 変更対象

**A. ms 正規化ヘルパの src 引き上げ (設計 D-1 (b)(ii))**

- **現物 (実測)**: 逐語実装は **`MitateDB-api/tests/test_application_audit.py:94`** の `_ms_from_pg_timeout_text` にある。**r2db 側にも独立のコピーが `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py:82` にある** (設計 §3 D-1 (b)(ii) は MitateDB の 1 コピーだけを挙げている)。MitateDB の conformance timeout テストは `:66` で `test_application_audit` から import している。
- **置き場は確定済み (監督裁定 2026-09-05。実装者提案は不要)**: **両 peer とも新規モジュール `<peer_pkg>/pg_timeouts.py`** — `r2db-api/src/r2db_api/pg_timeouts.py` / `MitateDB-api/src/mitatedb_api/pg_timeouts.py`。**関数名は `ms_from_pg_timeout_text`** (src では先頭アンダースコアを付けない)。既存の timeout 既定定数の所在は `r2db-api/src/r2db_api/credential_store.py` / `MitateDB-api/src/mitatedb_api/application_audit.py` である (設計 §3.10) が、**そこには置かない**。
- **扱う単位は設計の規範 (設計 §3 D-1 (b)(ii)) を採る — `{us, ms, s, min, h, d}` と単位無し (= ms)** (**監督裁定 2026-09-05**。WP-0 差し戻し裁定 B で PG 16 の受理集合 (HINT 逐語: Valid units for this parameter are "us", "ms", "s", "min", "h", and "d") に合わせ `us` を加え、端数は PG の rint 相当 (round-half-even) で整数化する)。**現行実装は `ms` / `min` / `s` / 単位無しのみを扱う (実測、`MitateDB-api/tests/test_application_audit.py:100-108`)** — `h` / `d` は本 WP で足す。
- 既存 3 コピー (r2db tests / MitateDB tests / MitateDB conformance test の import) を **src の 1 定義への import に置き換える**。**両 peer の既存テストコピー (`MitateDB-api/tests/test_application_audit.py:94-108` / `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py:82`) は本 WP で撤去し、コピーを 1 つも残さない** (監督裁定 2026-09-05)。

**B. 静的規則スキャナ (設計 D-3 (d) / §8.1 / §10)**

- **両 peer の tests に同名で置く。** 各 peer のテストは**自 peer の `migrations/` だけ**を走査する。
- **検査する規則** (設計 §10 が正本):
  - **(b) 走査規則** — `NNNN_<name>_upgrade.sql` に一致する各 script が、`INSERT INTO public._{r2db,mdb}_platform_upgrades` を含む**1 つの文**の中に、**自番号の整数リテラル (ゼロ埋めを外したもの)** と **`ON CONFLICT`** の両方を含むこと。`VALUES ('0009', …)` のようなゼロ埋め文字列は**不適合**。
  - **(d) 三者一致** — {`*_upgrade.sql` の番号集合} == {テンプレート `0003` の seed 集合} == {パッケージ定数の集合}。
  - **命名規範** — per-app 分類の script がこの命名に一致すること。**platform 単発 migration は `_upgrade.sql` で終わる名前を使わない** (設計 §8.1 の 2)。
  - **許可リストは番号の集合** — MitateDB = `{6}`、r2db = 空。**`0006` は自番号の台帳 INSERT を持たないことと `\q` skip 経路を持つことの両方について免除される** (LQ4-19)。
- **プロトタイプの現状**: `{scratchpad}/proto_ledger_scan.py` は `ON CONFLICT` の検査を持たず、`VALUES` 節の中だけを見ている。**規則 (b) に合わせて改訂し、両 peer に再実測をかけ、出力を設計 §10 へ貼る** (常設規律 5)。現状の出力は `適合 0 / 違反 0 / 免除 1 / 対象外 12` である。
- **非空振りの成立時期** — 本フェーズの新 per-app script は WP-3 / WP-4 で初めて出る。したがって:
  - **実 `migrations/` に対する assert のうち、`違反 0 かつ 免除 = {6}`(MitateDB) / `違反 0 かつ 免除 = 空`(r2db) は本 WP で緑になる。**
  - **`適合 ≥ 1` と三者一致は本 WP では成立しない** — 当該 peer のテストに **`xfail(strict=True)` で登録し、当該 peer の per-app script を出す WP (r2db = WP-3 / MitateDB = WP-4) と同一コミットで撤去する** (フェーズ6 D-5 と同じ版束縛規律)。
  - **合成 fixture (テストが `tmp_path` に組む擬似 `migrations/` ディレクトリ) に対しては、適合 / 違反 / ゼロ埋め不適合 / 三者不一致 / 命名不一致をそれぞれ 1 件以上観測する** — これが本 WP における規律 1 (空振り禁止) の充足手段である。
  - **上の 2 手 ((a) `xfail(strict=True)` と (b) 合成 fixture) は監督裁定 (2026-09-05) で確定である。合成 fixture は静的スキャナのテスト scaffolding であって設計外の機構ではない** — 常設規律 7 の「設計外の拡張」に当たらないので、実装前に改めて上げる必要は無い。

**C. 同型性対応表 (設計 D-3 (d))**

- **現物 (実測)**: 対応表は `r2db-api/tests/test_audit_query.py:2298` / `MitateDB-api/tests/test_audit_query.py:2037` の `_ISOMORPHIC_TARGETS` であり、**現在 18 行**である。内容を pin するテストは `test_isomorphic_target_table_is_pinned_to_its_current_18_rows` (r2db `:2335` / MitateDB `:2074`、`len(...) == 18` は r2db `:2377` / MitateDB `:2116`)。**この pin テストの関数名自身が対応表の 18 行目に載っている** (r2db `:2321` / MitateDB `:2060`) ので、**行を足すたびに関数名の行数部分と当該行の両方を改める**。(着手時 18 行 → WP-0 最終追補後 24 行、監督裁定 2026-09-05 裁定 4。改称後の pin テスト名は `test_isomorphic_target_table_is_pinned_to_its_current_24_rows` (r2db `:2394` / MitateDB `:2133`、`len(...) == 24` は r2db `:2465` / MitateDB `:2204`)。)
- **本 WP で足す行**: `ms_from_pg_timeout_text` (src、両 peer 同名) と、静的規則スキャナの走査ヘルパ (両 peer 同名)。**WP-0 が足すのはこの 2 種だけである** (監督裁定 2026-09-05)。
- **WP-1〜WP-4 で新設する同名ヘルパ** (宣言表の読み出し/検証、台帳の pending 集合計算、ops の psql 実行/集計) は本 WP では足さない。**監督裁定 (2026-09-05) により、対応表への行追加は「対」の後半 WP のみが行う — WP-2 が WP-1/WP-2 のヘルパ行を、WP-4 が WP-3/WP-4 のヘルパ行を追加し、pin テスト名の行数を改める。WP-1 / WP-3 は対応表を触らない。** 後半 WP の時点では両 peer に同名ヘルパが揃っているので、**`xfail(strict=True)` の placeholder は用いない** (フェーズ6 WP-2 の placeholder 運用は本フェーズでは採らない)。
- **既存の性質を弱めない** — 行頭インデントの保存、自己比較の構文的禁止、対象シンボルの不在も内容不一致も赤、ソース取得は左右とも `ast.get_source_segment`。

#### 完了条件 (検証可能な形)

1. **ms 正規化ヘルパが両 peer の `src/<peer_pkg>/pg_timeouts.py` に `ms_from_pg_timeout_text` としてあり、`{us, ms, s, min, h, d}` と単位無しを ms 整数へ正規化する** — **各単位につき個別ケースを両 peer で観測する** (parametrize 可)。
2. **テスト側の重複定義が消えている** — **監査照合 (変異を作らない)**: 監査は `grep -rn "def ms_from_pg_timeout_text" r2db-api MitateDB-api` を実行し、**ヒットが各 peer の `src/<peer_pkg>/pg_timeouts.py` の 1 件ずつ、計 2 件**であること、および `grep -rn "def _ms_from_pg_timeout_text" r2db-api MitateDB-api` が **0 件**であることを確認する。あわせて `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py` / `MitateDB-api/tests/test_application_audit.py` / `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py` の 3 ファイルが src から import していることを確認する。
3. **スキャナが規則 (b) を実装している** — 合成 fixture に対し、`INSERT` と `ON CONFLICT` と自番号整数リテラルが**同一文内**に揃う script を **適合**、`ON CONFLICT` を欠く script を **違反**と判定すること。**両方を 1 件以上観測する。**
4. **ゼロ埋め文字列は不適合** — 合成 fixture の `VALUES ('0009', …)` が **違反**と判定されること。
5. **命名規範の検査** — `NNNN_<name>_upgrade.sql` に一致しないファイルは**対象外**であり、**platform 単発 migration がこの命名を使っていないこと**を検査すること。
6. **許可リストは番号の集合であり、実 `migrations/` に対して 違反 0 かつ 免除 = MitateDB `{6}` / r2db 空** であること。
7. **三者一致の検査が存在する** — 合成 fixture で一致 / 不一致を各 1 件観測すること。**実 `migrations/` に対する三者一致 assert は `xfail(strict=True)` で登録**され、r2db = WP-3 / MitateDB = WP-4 で撤去される旨が docstring に書かれていること。
8. **`適合 ≥ 1` の非空振り guard が `xfail(strict=True)` で登録されている** — **監査照合 (変異を作らない)**: 監査は当該 assert に `strict=True` が付いていること、および撤去先の WP が docstring に名指しされていることを確認する。
9. **同型性対応表に本 WP の行が足され、pin テストの関数名が改称されている** — 対応表の内容を直接 pin するテストが**新しい行数**で緑であること。**既存 18 行が 1 対も落ちていない**こと。
10. **新規行が実際に突き合わされている** — 片 peer の新規ヘルパを 1 箇所変えると同型性テストが赤になること (変異 6 で実測)。
11. **契約不変・製品挙動不変** — **監査照合 (変異を作らない)**: 監査は `git diff -- spec/ r2db-api/src/r2db_api/contract/ MitateDB-api/src/mitatedb_api/contract/` が**空**であること、両 peer の `contract_version` が **1.6.0 のまま**であること、`migrations/` に**新規ファイルが無い**ことを確認する。
12. **プロトタイプ結果の記録** — 改訂したスキャナを両 peer に走らせた出力が `{scratchpad}` に保存され、完了報告に集計行 (適合 / 違反 / 免除 / 対象外) が転記されていること。**監査照合**: 監査は転記値と保存出力を突き合わせる。
13. **対応表に対応の無い行が無いこと** (メタ条件、常設規律 2)。
14. **完了ゲート** — 監督が root suite を単独実行し、`failed` 0 / `skipped` 0、`xfailed` が §5 の期待値と一致すること。

#### 非 vacuity 要件

- ms ヘルパのテストは**単位ごとに個別ケース**を持つ。1 ケースで全単位をまとめて assert しない (どの単位が壊れたか分からない)。
- スキャナのテストは**合成 fixture に対して 適合 / 違反 の両方を 1 件以上観測する**。実 `migrations/` だけを見る形にしない (本 WP 時点では 適合 0 なので空振りになる)。
- 同型性の新規行は**変異 6 で赤を実測**してから「突き合わされている」と書く。

#### 同型性テスト対象

**既存 18 行 + 本 WP の追加行** — `src` の `ms_from_pg_timeout_text` (両 peer 同名) と静的規則スキャナの走査ヘルパ (両 peer 同名)。**本 WP はこの 2 種以外の行を足さない** (監督裁定 2026-09-05)。**追加行数と改称後の pin テスト関数名は実装者が報告し、監督が記録する。**

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

**完了条件 → 変異の対応表**

| 完了条件 | 対応する変異 (それだけを壊すもの) |
|---|---|
| 1 ms ヘルパの単位集合 | **変異 1** (片 peer のヘルパから `h` の分岐を落とす → 当該 peer の `h` ケースが赤、他単位は緑) |
| 2 重複定義の消滅 | **監査照合** |
| 3 規則 (b) の実装 | **変異 2** (スキャナから `ON CONFLICT` の検査を落とす → 合成 fixture の「INSERT はあるが `ON CONFLICT` 無し」ケースが 適合 と判定され赤) |
| 4 ゼロ埋め不適合 | **変異 3** (整数リテラル照合をゼロ埋め文字列も許す形へ緩める → 合成 fixture の `'0009'` ケースが赤) |
| 5 命名規範 | **変異 4** (`NAME_RE` から `_upgrade` を落とす → 対象外だったファイルが走査対象に入り集計が赤) |
| 6 許可リスト | **変異 5** (MitateDB の許可リストから `6` を落とす → 実 `migrations/` 走査が 違反 1 で赤) |
| 7 三者一致 | **変異 6** (合成 fixture の seed リストから 1 番号を落とす → 三者一致が赤) |
| 8 `適合 ≥ 1` の xfail 登録 | **監査照合** |
| 9 対応表の pin | **変異 7** (対応表から新規 1 行を落とす → pin テストが赤) |
| 10 新規行の実効 | **変異 8** (片 peer の新規ヘルパを 1 箇所変える → 同型性テストが赤。正規化がこの差まで吸収していないことの実測) |
| 11 契約不変・製品挙動不変 | **監査照合** |
| 12 プロトタイプ結果の記録 | **監査照合** |
| 13 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 14 完了ゲート | **監査照合** |

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests/test_audit_query.py MitateDB-api/tests/test_audit_query.py
./.venv/bin/python -m pytest -q r2db-api/tests MitateDB-api/tests
```

**前景実行・`timeout` 600000 を明示・`ps` で他の pytest が 0 件であることを確認してから。** root suite は回さない (§0.2)。

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **ヘルパの引き上げで挙動が変わっていないか** — 既存 3 コピーが見ていた単位の解釈が同じか。`0` / 空文字列の扱い (現行は 0 を返す) が変わっていないか。
2. **`h` / `d` の追加が桁を取り違えていないか** (`h` = 3,600,000ms、`d` = 86,400,000ms)。
3. **スキャナが「同一文の中」を見ているか** — ファイル全体に `INSERT` と `ON CONFLICT` が別々にあるだけで 適合 になっていないか。
4. **許可リストが番号の集合か** — ファイル名やパスを鍵にしていないか (LQ4-19)。
5. **`xfail(strict=True)` が本当に strict か** — `xfail` を非 strict にして「いつ緑になっても気付かない」形になっていないか。
6. **対応表の弱化** — 行頭インデントの保存 / 自己比較の構文的禁止 / 不在も内容不一致も赤 / `ast.get_source_segment` への統一が落ちていないか。既存 18 行が 1 対も落ちていないか。
7. **合成 fixture が実 `migrations/` を汚していないか** — `tmp_path` の外にファイルを作っていないか (禁止事項 §7 の 6)。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-1 r2db — 宣言を DB 側の一次情報へ寄せる (`0008` + composition root + 二重検査 + ops 宣言系)

#### 目的

r2db の `visibility_lag_ms` / `coalescing_window_ms` / `surfaces` の根拠を **platform データベース**へ移し、書き手プロセスが**自分の実効値と宣言の一致を起動時に検査する**形にする。**出荷時に挙動は変わらない** (既定値が現行定数と同一)。

#### 変更対象

**A. `r2db-api/migrations/0008_<name>.sql` (新規、platform 単発)**

- **`_upgrade.sql` で終わる名前を使わない** (設計 §8.1 の 2。使うと WP-0 の静的規則が違反として落とす)。
- **D-1 の `ALTER ROLE … SET` 4 文** (`r2dbsvc_api` / `r2dbsvc_controlplane` × 2 設定、既定 `5000ms`)。**冪等** (上書き代入)。
- **D-2 の宣言表** `r2dbsvc_registry.platform_declarations` — 名前付き CHECK `platform_declarations_key_check`、`REVOKE ALL … FROM PUBLIC`、`GRANT SELECT` を `r2dbsvc_api` / `r2dbsvc_controlplane` に、`audit_coalescing_window_ms` の既定行 (`60000`) を `ON CONFLICT DO NOTHING` で seed、**`surfaces` は seed しない**。
- 実行資格は `R2DB_CONTROL_DSN` (`r2db-api/src/r2db_api/ops.py:184` の `_control_dsn`)。

**B. composition root (`r2db-api/src/r2db_api/main.py` / `control_main.py`)**

| 現物 (実測) | 本 WP での扱い |
|---|---|
| `main.py:250` `_surfaces(env, *, control_plane_status)`、`:265-269` が `R2DB_DATA_BASE_URL` / `R2DB_CONTROL_BASE_URL` を読む | 宣言表からの読み出しへ差し替え。**env は F-2 で拒否** |
| `control_main.py:261` `_surfaces(env)`、`:276-280` が同 2 変数を無条件必須で読む | 同 |
| `main.py:208` / `control_main.py:238` の `_validate_surface_base_url` (**2 コピー**) | **統合する** (§2 の 5 の上書き裁定 2026-09-05): 両コピーと `ops.py` の 3 コピー目を `platform_declarations.validate_surfaces_value` の呼び出しに置き換える (L6-17 閉止、設計 §12 LQ4-23) |
| `control_main.py:368-369` の `statement_ms + idle_ms` 導出、`:429-430` の `_optional_int(env, "R2DB_AUDIT_STATEMENT_TIMEOUT_MS"/"R2DB_AUDIT_IDLE_TIMEOUT_MS", …)` | `pg_db_role_setting` からの導出へ差し替え。**env は F-1 で拒否** |
| 監査 sink のセッション `SET` (設計 §1.5 の 1 / D-1 (b)) | **撤去**し、起動時の二重検査へ置き換える |

- **廃止 env の検査対象は composition root に渡された env mapping** であり `os.environ` ではない (設計 D-1 (d))。
- **起動シーケンスは設計 §3.7 の data-plane 1〜8 / control-plane 1〜8 に従う** — 検査順 (F-8 → F-3 / F-4 → F-5 / F-4b / F-6 → F-7 / F-10 / F-11 / F-9) を守る。

**C. `r2db-api/src/r2db_api/ops.py` — 宣言系 4 サブコマンド**

- `set-platform-timeouts --statement-ms <N> --idle-ms <N>` — **2 つのサービス書き手 role に同じ 2 値を置く単一ノブ。`0` と負数を拒否する。role 別の指定は設けない。**
- `declare-surfaces --data-base-url <URL> [--control-base-url <URL> | --no-control]` — **書き込み時に D-2 (d) の検証関数を通す。** **引数の意味は設計 D-2 (e) の直後の段落 (監督裁定訂正 2026-09-05) に従う** — **`--control-base-url` は任意** (省略 = `control` 行なし)、**`--no-control` は省略と等価の明示形**として受け付ける (F-2 / F-3 / F-6 の文面が提示するため)、**両方を同時に渡したら使い方の誤り (終了コード 2)**。**必須の相互排他にはしない。**
- `declare-coalescing-window --ms <N>` — **同じ検証関数を通す。**
- `show-declarations` — 宣言表と role 設定の現状を出す。
- parser 登録は既存の並び (`ops.py:1056` 以降) に足す。**終了コードの既存慣行を守る** — `_die` = 2 (`:179-181`)、`FoundationError` / `psycopg.Error` = 1。
- **r2db 側には `tests/test_ops.py` が存在しない (実測)**。**置き場は確定済み (監督裁定 2026-09-05。実装者提案は不要): WP-1 / WP-2 の宣言系 ops のテストは両 peer とも新規 `tests/test_ops_declarations.py` に、WP-3 / WP-4 の upgrade 系 ops のテストは新規 `tests/test_ops_upgrade.py` に置く** (r2db は `r2db-api/tests/test_ops_declarations.py`。監督追補 2026-09-05: 起草者の疑義に対する回答 — 宣言系と upgrade 系はファイルを分ける)。**r2db に `test_ops.py` が無いのはそのままとし、新設しない。**

**D. HTTP conformance adapter の追随 (`r2db-api/conformance/conformance_adapter_r2db_http.py`)**

- **`:123-124` の `os.environ.setdefault("R2DB_DATA_BASE_URL"/"R2DB_CONTROL_BASE_URL", …)` を撤去する** (設計 §6.1 γ)。
- **`surfaces` は `_SURFACES` (`:730`) の明示注入のままとする** — `:898` の `DataService(…, surfaces=_SURFACES)` と `:1047`/`:1061` の `assemble_control_stack(…, surfaces=_SURFACES)`。**宣言表の行を fixture に seed しない** (何も検証しない飾りになる)。
- **`:892-895` の `PostgresApplicationAuditSink(…, statement_timeout_ms=…, idle_in_transaction_session_timeout_ms=…)` は D-1 (b) の形に追随する** — セッション `SET` を撤去する以上、この構築点の引数も同時に変わる。**変えないと adapter が壊れる。**

**E. 既存テストの追随**

- `r2db-api/tests/test_surfaces_env.py` — env 由来の `surfaces` テストを宣言表由来へ。
- `r2db-api/tests/test_conformance_adapter_r2db_http_audit_writer_timeouts.py:105` — セッション `SET` ではなく **role 設定由来の実効値**を見る形へ。
- `r2db-api/tests/test_application_audit.py` / `test_credential_persistence.py` — timeout env 経路のテスト。

#### 完了条件 (検証可能な形)

1. **`0008` が `ALTER ROLE` 4 文を置き、冪等である** — 2 回適用して `pg_db_role_setting` の終状態が同一であること (実 PG)。
2. **`0008` が宣言表を作る** — 名前付き CHECK `platform_declarations_key_check` が存在し、閉じた集合外の `key` を DB が拒否すること、`SELECT` が 2 role に付与されていること、`audit_coalescing_window_ms` の行が `60000` で seed され `surfaces` の行が**無い**こと (実 PG)。
3. **廃止 env の fail-fast (F-1 / F-2)** — 4 変数のいずれかが **env mapping に定義されていれば値によらず** (空文字列を含む) 起動時に失敗すること。**4 変数 × {空文字列, 実値} の 8 ケースを個別に観測する。**
4. **検査対象が env mapping であって `os.environ` でないこと** — `os.environ` に廃止変数を置いても、composition root へ渡す mapping に無ければ起動すること。
5. **宣言表の読み出し順序 (F-8 → F-3 / F-4)** — 表が無い / `surfaces` 行が無い / `audit_coalescing_window_ms` 行が無い の 3 状態で、**生の psycopg 例外ではなく設計 §3.8 の当該メッセージ**が出ること。
6. **値の検証が書き込み時と読み出し時で同じ関数を通る (F-5 / F-4b)** — 宣言表へ手で不正値を入れた状態で起動すると落ち、同じ値を ops へ渡しても落ちること。**`surfaces` の 4 検査項目** (絶対 URL / `/v1` 接尾辞 / `/control/v1` 接尾辞 / 末尾スラッシュ無し) と **窓の 3 拒否** (文字列 / 負数 / 小数) をそれぞれ観測する。
7. **`control` 行 × `R2DB_CONTROL_PLANE_STATUS` の整合 (F-6)** — **両向き**で落ちること。
8. **書き手の二重検査 (F-7 / F-9 / F-10 / F-11)** — (i) 2 設定の欠落、(ii) ms 値 0 / 負数、(iii) per-database 行 (`setdatabase ≠ 0`) の存在、(iv) 接続時 `options=-c …` による上書きで実効値が catalog 値と食い違う、の 4 状態でそれぞれ当該メッセージが出ること (実 PG)。
9. **セッション `SET` が撤去されている** — 監査書き手 pool の接続の実効値が **role 設定由来**であること (実 PG。`0008` を適用しない platform DB では F-7 で起動しないこと)。
10. **`visibility_lag_ms` が出荷既定で 11000 のままであること** — control 文書が現行と同じ値を返すこと。
11. **ops 4 サブコマンドが provision DSN で動く** — `set-platform-timeouts` が `0` と負数を拒否すること、`declare-surfaces --no-control` が `control` を消すこと、`declare-coalescing-window` が検証関数を通ること、`show-declarations` が宣言表と role 設定を出すこと。**終了コードが既存慣行 (`_die` = 2 / `FoundationError` = 1) に従う**こと。
12. **fail-fast メッセージの文字列ピン** — **設計 §3.8 の F-1 / F-2 / F-3 / F-4 / F-4b / F-5 / F-6 / F-7 / F-9 / F-10 / F-11 の骨子を逐語 assert するテストが存在する**こと (常設規律 4)。**とくに「次に打つ ops コマンド名」が各メッセージに含まれる**こと。
13. **起動時スナップショットであること (U-3)** — 起動後に宣言表を書き換えても、プロセスが返す capability 文書が変わらないこと。
14. **HTTP adapter の追随** — `os.environ.setdefault` の 2 行が消え、`grep -n "R2DB_DATA_BASE_URL\|R2DB_CONTROL_BASE_URL" r2db-api/conformance/conformance_adapter_r2db_http.py` が **0 件**であること。adapter が緑であること。
15. **契約不変** — **監査照合 (変異を作らない)**: 監査は `git diff -- spec/ r2db-api/src/r2db_api/contract/` が**空**、`contract_version` が **1.6.0 のまま**であることを確認する。
16. **MitateDB 側が差分に現れないこと** — **監査照合 (変異を作らない)**: 監査は `git diff --name-only` に `MitateDB-api/` が**1 件も現れない**ことを確認する (並行 worktree の分離)。
17. **対応表に対応の無い行が無いこと** (メタ条件)。
18. **完了ゲート** — 監督が root suite を単独実行する。

**追補 (監督裁定 2026-09-05、設計 v1.3 の D-2 (h) を発注する。既存 1〜18 の番号と内容は変えない)**

19. **`0008` が `audit_writer_roles` 行を seed し、`key` の CHECK がこの key を許すこと** — migration が **role 名を psql 変数で受け** (既存様式)、`ALTER ROLE` 4 文の対象と seed 値が**同じ変数から組まれ、同じトランザクション内**にあること。**throwaway prefix の role 名を変数で渡して流すと、`ALTER ROLE` の対象と `audit_writer_roles` 行の値がその名前で一致する**こと (実 PG)。**2 回適用して終状態が同一である**こと (条件 1 と同じ冪等性を本行についても観測する)。
20. **書き手プロセスの自 role 包含確認 (F-13)** — 宣言された書き手でない role で起動すると、**二重検査 (F-7 / F-9 / F-10 / F-11) より前に** F-13 で止まること。**`audit_writer_roles` 行が無い場合も F-13 である**こと (設計 §3.8 の条件は「行が無い場合を含む」)。**F-13 を条件 12 の文字列ピンに加える** — migration 番号と `ops set-platform-timeouts` が含まれること。
21. **control の導出が宣言表の role 集合から来ること** — **role 名をコード内の命名規則から導出する経路が残っていないこと** (schema 名の `removesuffix` / 接尾辞の書き換えによる導出が**両 composition root と control 側で 0 件**であることを `grep` で示す)。throwaway prefix の 2 role を宣言し**それぞれ異なる timeout** を置くと、`visibility_lag_ms` が**宣言された全 role の `max(statement + idle)` + 1000** になること (実 PG)。
22. **ops `set-platform-timeouts` の対象が宣言表から来ること** — **role 名の引数を持たず**、`audit_writer_roles` の**各 role**に `ALTER ROLE` を発行すること。throwaway prefix で seed した宣言表に対して実行すると、**その 2 role の `pg_db_role_setting` が変わる**こと (実 PG)。
23. **`audit_writer_roles` 行の検証 (F-4b)** — **非空の文字列配列でない / 重複がある / 要素が識別子として妥当でない**の 3 拒否をそれぞれ観測すること。**識別子検証は既存のものを再利用している**こと。検証は**行を読むすべての経路** (両プロセスの起動時、ops `set-platform-timeouts` / `show-declarations`) が**同じ関数**を通ること。

**追補 2 (監督裁定 2026-09-05、WP-1 / WP-2 差し戻し。`{scratchpad}/rulings-q4-wp12-rework.md` §4 の追加テストを発注する。既存 1〜23 の番号と内容は変えない)**

**併せて、本 WP の実装は同裁定 §1 の関数分解 (設計 §3.10「同型性の面」の表) と §2 の r2db 固有裁定に従う** — **control の検査は `build_control_app()` で同期的に行い lifespan へ遅延させない** (設計 §4 の却下案)、**zero-network の既存テストは明示注入の `assemble_control_stack(…)` を使う形に書き換える**、**`service._surfaces` 等の private reach-in は撤去しコンストラクタ引数で渡す**、**control の兄弟 role の catalog 検査は `audit_reader` の有無に依らず無条件**、**adapter の `1000` リテラルは `VISIBILITY_LAG_CLOCK_SKEW_MARGIN_MS` を import する**、**`0008` の docstring / コメントが挙げるテスト名は実在テストを作ってから実名に直す**。

24. **廃止 env の起動経路テスト (裁定 §4 (a))** — **`build_app` / `build_control_*` の実経路**で、**{timeout 2 変数, surfaces 2 変数} × {空文字列, 実値} = 8 ケース**を観測すること (条件 3 を実経路で固定し直すものであり、検査関数の直接呼び出しでは満たさない)。
25. **読み側検証 (裁定 §4 (b))** — **実 PG の宣言表に不正値**を入れて `read_platform_declarations` が F-4b / F-5 を出すこと。**窓**: 文字列 / 負 / 小数 / `true`、**surfaces**: 非絶対 / 接尾辞違い / 末尾スラッシュ、**writer_roles**: 空 / 重複 / 不正識別子。
26. **migration の DDL テスト (裁定 §4 (c))** — **2 回適用の終状態一致** (**間に `ops set-platform-timeouts` で値を変える**)、**名前付き CHECK の存在と語彙外 `key` の DB 拒否**、**2 role への `GRANT SELECT`**、**seed** (窓の既定値、`writer_roles` = 渡した role 名、`surfaces` 行なし) をそれぞれ観測すること。
27. **起動時スナップショット (裁定 §4 (d))** — 起動後に宣言表を書き換えても **capability 文書 (data / control の両方)** が不変であること。
28. **F-9 の実 PG 観測 (裁定 §4 (e))** — 接続に **`options=-c statement_timeout=30000`** を注入して起動が止まること。
29. **F-13 の実 PG 観測 (裁定 §4 (f))** — **`current_user` を含まない `writer_roles`** を seed して起動が止まること。
30. **未適用 platform DB (裁定 §4 (g))** — **migration 未適用**の platform DB で **F-7 (または F-8)** により起動しない実 PG テストがあること。
31. **文字列ピン (裁定 §4 (h))** — **F-1〜F-13 (+ F-3c)** の骨子を**設計 §3.8 から逐語で assert** すること (**部分一致は不可**)。条件 12 / 20 の文字列ピンを **F-3c と F-12 以外の全項目**へ広げるものである。
32. **変異表の全件実施 (裁定 §4 (i))** — **本 WP の変異表 (追補 16〜20 と追補 2 の 21〜28 を含む) を全件実施し、赤の集計行を報告に貼る**こと。**監査照合 (変異を作らない)**: 監査は報告の集計行と変異表の行数を突き合わせる。

#### 非 vacuity 要件

- fail-fast のテストは**実際の起動経路** (`build_app(env)` / `build_control_app(env)` 相当) を通して観測する。検査関数を直接呼ぶだけで済ませる場合は、**その関数が起動経路から実際に呼ばれていること**を別途 assert する。
- 二重検査 (条件 8) の (iv) は**実 PG に上書きを注入して**観測する (設計 §10 の実 PG 確認項目 3)。合成 stub で済ませない。
- 条件 9 は**実 PG で `0008` 未適用の platform DB を作り**、F-7 で起動しないことを観測する。
- **追補**: 条件 19 / 21 / 22 は**実 PG に throwaway prefix の role を作り、その名前を psql 変数で migration へ渡して**観測する。**逐語の本番 role 名 (`r2dbsvc_api` / `r2dbsvc_controlplane`) をテストへ焼き付けない** (設計 D-2 (h) の 5)。合成 stub で済ませない。

#### 同型性テスト対象

**本 WP で新設する同名ヘルパ** — 宣言表の読み出し/検証ヘルパ、`pg_db_role_setting` からの導出ヘルパ、ops の宣言書き込みヘルパ、**`audit_writer_roles` の読み出し/検証/自 role 包含確認のヘルパ (追補、D-2 (h))**。**`platform_declarations.py` の同名ヘルパは名前・シグネチャ・ロジックを WP-2 と揃える** (**監督裁定 2026-09-05**) — 本 WP が先行するので、**WP-2 が採る名前に合わせられるよう完了報告で一覧を引き渡す**。**本 WP は対応表 (`_ISOMORPHIC_TARGETS`) を触らない** (**監督裁定 2026-09-05**) — これらの行は **WP-2 が WP-2 自身のヘルパ行とまとめて追加**し、pin テスト名の行数を改める。**したがって本 WP は `xfail(strict=True)` の placeholder を登録せず、`xfailed` は WP-0 分から増えない。** 実装者は**新設した同名ヘルパの一覧 (関数名とファイル)** を完了報告に列挙し、WP-2 の発注へ引き渡すこと。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

| 完了条件 | 対応する変異 |
|---|---|
| 1 `ALTER ROLE` の冪等 | **変異 1** (`0008` の `ALTER ROLE` を `SET` から条件付き挿入へ変える → 2 回適用テストが赤) |
| 2 宣言表の DDL と権限 | **変異 2** (`platform_declarations_key_check` の名前を外す → 名前付き制約の存在テストが赤) |
| 3 廃止 env の fail-fast | **変異 3** (「空文字列は無視する」分岐を足す → 4 変数 × 空文字列の 4 ケースが赤) |
| 4 検査対象が env mapping | **変異 4** (検査対象を `os.environ` へ変える → 条件 4 のテストが赤) |
| 5 読み出し順序 | **変異 5** (F-8 の存在検査を落とす → 表が無い状態で生の psycopg 例外が出て赤) |
| 6 値の検証の一本化 | **変異 6** (読み出し側の検証呼び出しを落とす → 手で入れた不正値で起動してしまい赤) |
| 7 F-6 の両向き | **変異 7** (逆向き (`control` 行が無いのに status が `enabled`) の枝を落とす → 当該ケースが赤) |
| 8 二重検査 | **変異 8** (実効値の比較を生文字列比較へ戻す → `5000ms` と `5s` が食い違い F-9 が誤爆して赤) + **変異 9** (per-database 行の検査 (F-11) を落とす → 当該ケースが赤) |
| 9 セッション `SET` の撤去 | **変異 10** (sink にセッション `SET` を戻す → `0008` 未適用 DB で起動してしまい条件 9 が赤) |
| 10 `visibility_lag_ms` = 11000 | **変異 11** (導出式の clock skew margin を落とす → 値が 10000 になり赤) |
| 11 ops の 4 サブコマンド | **変異 12** (`set-platform-timeouts` の `0` 拒否を落とす → 当該ケースが赤) |
| 12 文字列ピン | **変異 13** (F-7 のメッセージから ops コマンド名を落とす → 文字列ピンが赤) |
| 13 起動時スナップショット | **変異 14** (capability 文書の組み立て時に宣言表を再読する形へ変える → 条件 13 が赤) |
| 14 HTTP adapter の追随 | **変異 15** (`os.environ.setdefault` の 2 行を戻す → 不在を assert するテストが赤) |
| 15 契約不変 | **監査照合** |
| 16 MitateDB 不干渉 | **監査照合** |
| 17 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 18 完了ゲート | **監査照合** |
| **19** `audit_writer_roles` の seed と CHECK | **変異 16** (`0008` の `key` の CHECK 集合から `audit_writer_roles` を落とす → 同じ migration の seed が制約違反になり、当該 migration テストが赤) |
| **20** 自 role 包含確認 (F-13) | **変異 17** (起動経路から包含確認を外す → 宣言されていない role で起動してしまい F-13 のテストが赤) |
| **21** control の導出が宣言表由来 | **変異 18** (seed の role 名を 1 つ落とす → 導出が宣言された全 role の max を取らなくなり、control の導出テストが赤) |
| **22** ops の対象が宣言表由来 | **変異 19** (`set-platform-timeouts` の対象 role を宣言表からではなく定数から取る形へ戻す → throwaway prefix の宣言に対する条件 22 のテストが赤) |
| **23** 行の検証 (F-4b) | **変異 20** (`audit_writer_roles` の検証から重複検査を落とす → 重複を入れたケースが起動してしまい赤) |
| **24** 廃止 env の起動経路 (§4 (a)) | **変異 21** (composition root の `reject_*` 呼び出しを外す → 8 ケースが赤) |
| **25** 読み側検証 (§4 (b)) | **変異 22** (読み側の `validate_*` を素通しにする → 不正値で起動してしまい赤) |
| **26** migration の DDL (§4 (c)) | **変異 23** (`ALTER ROLE` を条件付きにする → 2 回適用の終状態一致が赤) + **変異 24** (`CHECK` 名を外す → 名前付き制約の存在テストが赤) |
| **27** 起動時スナップショット (§4 (d)) | **変異 25** (文書組み立て時に宣言表を再読する → 条件 27 が赤) |
| **28** F-9 の実 PG 観測 (§4 (e)) | **変異 26** (実効値との比較を落とす → `options=-c` を注入したケースが起動してしまい赤) |
| **29** F-13 の実 PG 観測 (§4 (f)) | **変異 27** (自 role の包含確認を外す → 条件 29 が赤) |
| **30** 未適用 platform DB (§4 (g)) | **既存の変異 10** (sink にセッション `SET` を戻す → migration 未適用 DB で起動してしまい、条件 9 と条件 30 の両方が赤。**裁定 §4 (g) は専用の変異を指定していないため、同一状態を固定する既存変異を対応付ける**) |
| **31** 文字列ピン (§4 (h)) | **変異 28** (F-1〜F-13 / F-3c の**任意の 1 文を言い換える** → 当該文字列ピンが赤) |
| **32** 変異表の全件実施 (§4 (i)) | **監査照合** (メタ条件。報告の集計行と本表の行数を突き合わせる) |

**追補 2 の変異についての運用注記**: **変異 23 / 24 / 25 / 27 は既存の変異 1 / 2 / 14 / 17 と同じ注入である。** 同じ注入で**既存条件と追補 2 の条件の両方**が赤になるので、**注入は 1 回でよいが、赤になったテスト名を両方の行について報告する** (空振り禁止、常設規律 1)。

```
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q conformance-tests -k r2db-api-http
```

**前景実行・`timeout` 600000 を明示・`ps` で他の pytest が 0 件であることを確認してから。** root suite は回さない (§0.2)。

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **fail-fast の射程超過** — `R2DB_CONTROL_PLANE_STATUS` は**本設計が廃止しない** (設計 §3.8 F-6 の注記)。手が伸びていないか。
2. **廃止 env の部分適用** — 「空文字列だけは通す」「値が既定値と同じなら通す」のような**部分的な適用**になっていないか。**定義されていれば値によらず拒否**であること。
3. **生文字列比較の残骸** — `SHOW` / `current_setting` の戻り値をそのまま比較していないか。**両辺 ms 整数**であること。実効値の取得が `pg_settings` であること。
4. **検査を行う接続** — 実効値の検査が**監査書き手が実際に使う pool の接続 (login role = 書き手 role)** で行われているか。`SET ROLE` した接続で読んでいないか (それでは書き手 role の実効値にならない)。
5. **`setdatabase` の扱い** — 宣言とみなすのは `setdatabase = 0` の行だけか。per-database 行を**拾って F-11 で止めている**か (`WHERE setdatabase = 0` で絞ると構造的に見落とす)。
6. **未知キーの扱い** — `setconfig` の `search_path` 等を読み飛ばしているか。無視しないと将来の `ALTER ROLE` 追加で起動が止まる。
7. **メッセージの言い換え** — 設計 §3.8 の文面から**逐語複製**しているか。要約・意訳になっていないか。
8. **秘密の混入** — メッセージ・テスト・migration に実 DSN / 実ホスト名 / 実 credential が無いか。`example.invalid` と合成値のみか。
9. **F-6 の推奨の向き** — 既定の推奨が「`R2DB_CONTROL_PLANE_STATUS` を直す」になっているか (`--no-control` を既定で勧めると control プロセスが F-3 で起動不能になる)。
10. **adapter の壊れ** — `PostgresApplicationAuditSink` の構築点が D-1 (b) に追随しているか。追随漏れは import 時ではなく adapter 構築時に出るので、conformance を実際に回して確認する。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-2 MitateDB — 宣言を DB 側の一次情報へ寄せる (`0007` + composition root + 二重検査 + ops 宣言系)

#### 目的

**WP-1 と同じ安全成果を同じ形で MitateDB に置く** (設計 §2 制約 4)。**WP-1 の裁定・レビュー指摘を発注時点で織り込むこと。** ただし「織り込んだから同じ指摘は出ない」とは限らない — 対称実装の価値は指摘数の減少ではなく**両向きの照合**にある。

#### 変更対象

**A. `MitateDB-api/migrations/0007_<name>.sql` (新規、platform 単発)** — WP-1 の A と同型。role は `mitatedbsvc_api` / `mitatedbsvc_controlplane`、registry スキーマは `mitatedb_registry`、実行資格は `MITATEDB_PROVISION_DSN` (`MitateDB-api/src/mitatedb_api/ops.py:369` の `_provision_dsn`)。**`_upgrade.sql` で終わる名前を使わない。**

**B. composition root**

| 現物 (実測) | 本 WP での扱い |
|---|---|
| `MitateDB-api/src/mitatedb_api/config.py:135-157` が `MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL` を読む (control 側は `control_plane_status` 依存)。`:150-157` に**フェーズ6 監督裁定 5 の「stale な値は決して採用しない」**のコメントがある | 宣言表からの読み出しへ差し替え。**env は F-2 で拒否**。**裁定 5 を上書きする旨を当該箇所に日付付きで記録する** |
| `control_composition.py:187-190` が同 2 変数を無条件必須で読む | 同 |
| `surfaces.py:78` `validate_data_base_url` / `:88` `validate_control_base_url` (**単一モジュール**) | **宣言表の値を検証する形で再利用する** |
| `control_composition.py:147-148` の `_optional_int(env, "MITATEDB_AUDIT_STATEMENT_TIMEOUT_MS"/"…IDLE…", …)`、`main.py:269-270` の同型 | `pg_db_role_setting` からの導出へ差し替え。**env は F-1 で拒否** |
| 監査 sink のセッション `SET` | **撤去**し、起動時の二重検査へ置き換える |

**C. `MitateDB-api/src/mitatedb_api/ops.py` — 宣言系 4 サブコマンド** — WP-1 の C と同名・同引数。**`declare-surfaces` の `--no-control` は廃止しない** (**監督裁定訂正 2026-09-05**) — WP-1 の C と同じく、**`--control-base-url` は任意 (省略 = `control` 行なし)、`--no-control` は省略と等価の明示形、両方同時は使い方の誤り (終了コード 2)** であり、**必須の相互排他にはしない** (設計 D-2 (e) の直後の段落)。parser 登録は既存の並び (`:752` 以降) に足す。終了コードの既存慣行 (`_die` = 2 (`:234-236`)、`FoundationError` / `psycopg.Error` = 1) を守る。**テストの置き場は確定済み (監督裁定 2026-09-05): 宣言系は両 peer とも新規 `tests/test_ops_declarations.py`** であり、MitateDB も既存 `tests/test_ops.py` に足さず `MitateDB-api/tests/test_ops_declarations.py` を新設する。

**D. HTTP conformance adapter の追随 (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`)**

- **本 adapter は control-plane composition root そのもの (`build_control_service(control_env)`、`:715`) を呼ぶ** ので、**宣言表の読み出しが load-bearing になる** (設計 §6.1 α)。
- **`control_env` (`:685` 以降、`:707-708` が 2 つの `*_BASE_URL`) から廃止 env を除く。**
- **fixture の platform DB に宣言表の行 (`surfaces` / `audit_coalescing_window_ms`) と書き手 role の 2 設定を seed する** — `0007` を fixture の migration 列に足すことで満たせる。
- **data-plane 側 (`:847` の `FoundationConfig(…, data_base_url=…, control_base_url=…)`) も追随が要る** — `FoundationConfig` が surfaces を env / 引数から受けなくなる以上、この構築点も変わる。
- **`:122-123` の `_DATA_SURFACE_BASE_URL` / `_CONTROL_SURFACE_BASE_URL` は宣言表 seed の値の出所として残す** — adapter 自身の `BASE_URL` (`:116`) と同じ origin であることが C-19 の同居判定に効く。

**E. 既存テストの追随** — `MitateDB-api/tests/test_config.py` (env 由来の surfaces / control_plane_status)、`tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py:82`、`tests/test_application_audit.py`、`tests/test_main.py` / `test_control_main.py`。

#### 完了条件 (検証可能な形)

**WP-1 の完了条件 1〜18 を MitateDB の名前で読み替えたもの**を用いる。ただし次の 3 点が異なる。

- **条件 7 (F-6)** — 対称性の根拠は `MITATEDB_CONTROL_PLANE_STATUS` である。受理値の集合を実測してから誤爆の余地が無いことを報告する。
- **条件 14 (HTTP adapter の追随)** — **r2db と非対称である**。MitateDB は **`control_env` から廃止 env を除き、fixture の platform DB に宣言表と role 設定を seed する**こと。`grep -n "MITATEDB_DATA_BASE_URL\|MITATEDB_CONTROL_BASE_URL" MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` が **`control_env` の 2 行について 0 件**であること。**adapter が緑であること** — この adapter は composition root を通るので、宣言表の seed が無ければ F-3 で落ちる。
- **条件 16 (不干渉)** — 監査は `git diff --name-only` に **`r2db-api/` が 1 件も現れない**ことを確認する。
- **追加条件 19: フェーズ6 監督裁定 5 の上書きの記録** — **監査照合 (変異を作らない)**: 監査は `MitateDB-api/src/mitatedb_api/config.py:150-157` 相当の箇所と r2db の同型のゲートについて、**「宣言表では行の存在自体を矛盾として拒否する」形へ改まったことが日付付きで記録されている**ことを確認する。
- **追加条件 20: 対応表への行追加 (WP-1 分 + WP-2 分)** — **監督裁定 2026-09-05 により、対「WP-1 / WP-2」のヘルパ行は後半 WP である本 WP がまとめて追加する。** WP-1 が新設した同名ヘルパ (宣言表の読み出し/検証、`pg_db_role_setting` からの導出、ops の宣言書き込み) と本 WP の対応するヘルパの行を `_ISOMORPHIC_TARGETS` へ足し、**pin テスト関数名の行数部分と当該行の両方を改め**、対応表が両 peer で緑になること。**`xfail(strict=True)` の placeholder は用いない** (両 peer に実物が揃っているため)。**既存行が 1 対も落ちていない**こと。
- **追加条件 21 (追補。監督裁定 2026-09-05、設計 v1.3 の D-2 (h))**: **WP-1 の追補条件 19〜23 を MitateDB の名前で読み替えたもの**を用いる — migration は **`0007`**、本番の seed 値は **`["mitatedbsvc_api", "mitatedbsvc_controlplane"]`** (設計 §3.10)、ops は同名の `set-platform-timeouts`。**非 vacuity も WP-1 の追補と同じく、throwaway prefix の role 名を psql 変数で migration へ渡して実 PG で観測する** (逐語の本番 role 名をテストへ焼き付けない)。
- **追加条件 22 (追補)**: **`audit_writer_roles` 系ヘルパの対応表への追加と名前の統一** — 条件 20 で本 WP が足す行に、**`audit_writer_roles` の読み出し / 検証 / 自 role 包含確認のヘルパ**を含めること。**`platform_declarations.py` の同名ヘルパは両 peer で名前・シグネチャ・ロジックが揃っている**こと (**監督裁定 2026-09-05**。**WP-1 側は WP-2 と同名にする** — WP-1 の完了報告が引き渡したヘルパ一覧を出発点にする)。**そのために `r2db-api/` を変更する必要が生じたら条件 16 (不干渉) と衝突するので、実装前に監督へ上げる** (常設規律 7)。
- **追加条件 23 (追補 2。監督裁定 2026-09-05、WP-1 / WP-2 差し戻し `{scratchpad}/rulings-q4-wp12-rework.md` §4)**: **WP-1 の追補 2 条件 24〜32 を MitateDB の名前で読み替えたもの**を用いる — migration は **`0007`**、廃止 env は `MITATEDB_*`、実経路は `build_app` / `build_control_service` (composition root)、文字列ピンは **F-1〜F-13 (+ F-3c)** を設計 §3.8 から**逐語**で (部分一致不可)。**本 WP は同裁定 §1 の関数分解 (設計 §3.10「同型性の面」の表) の参照実装を持つ** — `platform_declarations.py` を表のシンボルどおりに置き、**peer 差を引数 (schema 名、peer 名、ops モジュール名) と呼び出し側だけに閉じる**こと。**対応表 (`_ISOMORPHIC_TARGETS`) の行を §3.10 の表の全シンボル (「載せる」の行) に更新し、pin テスト名を改める** (条件 20 / 22 と同じ編集点)。

#### 非 vacuity 要件

WP-1 と同一。加えて、**MitateDB HTTP plug は composition root を通るので、宣言表 seed を落とすと adapter が起動しないことを変異で実測する** (設計 §6.1 α が「load-bearing になる」と書くことの実測)。

#### 同型性テスト対象

**WP-1 と WP-2 が新設した同名ヘルパの行を、本 WP がまとめて対応表へ足し、pin テスト名を改称する** (**監督裁定 2026-09-05**: 対応表を触るのは対の後半 WP のみ)。**WP-1 は対応表を触っていないので撤去すべき placeholder は無い。**

#### 変異注入 (必須)

**WP-1 の変異 1〜15 を MitateDB の名前で読み替えたもの**に、次の 2 種を足す。

| 完了条件 | 対応する変異 |
|---|---|
| 14 HTTP adapter の追随 | **変異 16** (fixture の宣言表 seed を落とす → adapter が F-3 で起動せず conformance が赤。**宣言表の読み出しが load-bearing であることの実測**) |
| 20 対応表への行追加 (WP-1 分 + WP-2 分) | **変異 17** (**WP-1 由来の新規行**について片 peer のヘルパを 1 箇所変える → 対応表の当該行が赤。**WP-1 のヘルパが本当に突き合わされていることの実測**) |
| 19 裁定 5 の上書きの記録 | **監査照合** |

**追補 (監督裁定 2026-09-05、D-2 (h))。WP-1 の追補変異 16〜20 は本 WP では 18〜22 と番号し直す** — 本 WP の既存 変異 16 / 17 と衝突させないためであり、**既存番号は変えない**。

| 完了条件 | 対応する変異 |
|---|---|
| 21 (WP-1 追補条件 19 の読み替え) | **変異 18** (`0007` の `key` の CHECK 集合から `audit_writer_roles` を落とす → 同じ migration の seed が制約違反になり当該 migration テストが赤) |
| 21 (同 20 の読み替え) | **変異 19** (起動経路から自 role 包含確認を外す → F-13 のテストが赤) |
| 21 (同 21 の読み替え) | **変異 20** (seed の role 名を 1 つ落とす → control の導出テストが赤) |
| 21 (同 22 の読み替え) | **変異 21** (`set-platform-timeouts` の対象 role を定数から取る形へ戻す → throwaway prefix の宣言に対する当該テストが赤) |
| 21 (同 23 の読み替え) | **変異 22** (`audit_writer_roles` の検証から重複検査を落とす → 当該ケースが赤) |
| 22 対応表への `audit_writer_roles` 系ヘルパ行 | **変異 23** (**WP-1 由来の `audit_writer_roles` ヘルパ**について片 peer を 1 箇所変える → 対応表の当該行が赤。**両 peer の同名ヘルパが本当に突き合わされていることの実測**) |

**追補 2 (監督裁定 2026-09-05、WP-1 / WP-2 差し戻し §4)。WP-1 の追補 2 変異 21〜28 は本 WP では 24〜31 と番号し直す** — 本 WP の既存 変異 16〜23 と衝突させないためであり、**既存番号は変えない**。

| 完了条件 | 対応する変異 |
|---|---|
| 23 (WP-1 追補 2 条件 24 の読み替え、§4 (a)) | **変異 24** (composition root の `reject_*` 呼び出しを外す → 8 ケースが赤) |
| 23 (同 25 の読み替え、§4 (b)) | **変異 25** (読み側の `validate_*` を素通しにする → 不正値で起動してしまい赤) |
| 23 (同 26 の読み替え、§4 (c)) | **変異 26** (`ALTER ROLE` を条件付きにする → 2 回適用の終状態一致が赤) + **変異 27** (`CHECK` 名を外す → 名前付き制約の存在テストが赤) |
| 23 (同 27 の読み替え、§4 (d)) | **変異 28** (文書組み立て時に宣言表を再読する → 当該条件が赤) |
| 23 (同 28 の読み替え、§4 (e)) | **変異 29** (実効値との比較を落とす → `options=-c statement_timeout=30000` を注入したケースが起動してしまい赤) |
| 23 (同 29 の読み替え、§4 (f)) | **変異 30** (自 role の包含確認を外す → 当該条件が赤) |
| 23 (同 30 の読み替え、§4 (g)) | **既存の変異 10 の読み替え** (sink にセッション `SET` を戻す → migration 未適用 DB で起動してしまい赤。**裁定 §4 (g) は専用の変異を指定していない**) |
| 23 (同 31 の読み替え、§4 (h)) | **変異 31** (F-1〜F-13 / F-3c の**任意の 1 文を言い換える** → 当該文字列ピンが赤) |
| 23 (同 32 の読み替え、§4 (i)) | **監査照合** (メタ条件。報告の集計行と本表の行数を突き合わせる) |

**運用注記**: **変異 26 / 27 / 28 / 30 は WP-2 の既存変異 (WP-1 の 1 / 2 / 14 / 17 を読み替えたもの) と同じ注入である。注入は 1 回でよいが、赤になったテスト名を両方の行について報告する。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests -k MitateDB-api-http
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

**WP-1 の 1〜10 に加えて:**

11. **裁定 5 の上書きが黙って行われていないか** — 「stale な値は決して採用しない」という明示の裁定を覆す以上、**その旨が記録されている**か。
12. **`surfaces.py` の単一モジュール性が保たれているか** — 宣言表対応で 2 コピーへ分裂していないか (r2db の L6-17 を MitateDB へ持ち込まない)。
13. **adapter の 2 つの構築点** — control 側 (`build_control_service`) と data 側 (`FoundationConfig`) が**同じ 1 つの宣言**から来ているか。独立に設定された 2 コピーへ戻っていないか。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-3 r2db — per-application 台帳と一括適用 (`0003` 改訂 + `0009` + 除外集合 + RLS ビュー + cell open 検査 + ops)

#### 目的

「どの application DB に何番まで当たったか」を**実体と同じデータベースの中に**記録し、一括適用と可視化を provision DSN の中に置く。**あわせて、台帳表を作ったことで既存の catalog / RLS 監視 / 会計が壊れないようにする** (設計 D-3 (e)、レビュー 2 本の重大指摘)。

#### 変更対象

**A. `r2db-api/migrations/0003_provision_application.sql` (テンプレート改訂)**

- 台帳表 `public._r2db_platform_upgrades` を作り、**その時点の全 per-app 番号 (`{9}`) を適用済みとして seed する** (設計 D-3 (b)(i))。**seed の `VALUES` は整数リテラルのタプルのみで書く** (設計 §8.1。関数呼び出し・ドル引用符・入れ子括弧は静的規則の三者一致検査をすり抜けず fail-safe 側で不一致に落ちる)。
- **RLS 監視ビューの除外名に台帳名を足す** — 現物は **`:234-241` の `CREATE VIEW public._r2db_missing_rls`** であり、**`:240` が `_r2db_schema_revision` 1 件だけを名指しで除外している** (実測)。**この `CREATE VIEW` を `CREATE OR REPLACE VIEW` に変える** (**監督裁定 2026-09-05**。テンプレートは改訂してよい = §7 禁止事項 3)。**per-app `0009` も `CREATE OR REPLACE VIEW` で同じ定義を置く** — テンプレートと per-app script が同一の定義に着く。
- **台帳表に RLS を付けない** (監督裁定 2026-09-05。FORCE RLS は所有者にも適用されるため provision → `SET ROLE developer` の書き込みが拒まれる)。

**B. `r2db-api/migrations/0009_<name>_upgrade.sql` (新規、per-app upgrade)**

- **命名は `NNNN_<name>_upgrade.sql`** (WP-0 の静的規則の走査対象)。
- 既存儀式 (設計 §1.5 の 5) に従い、`\c :database_name` → `GRANT :"developer_role" TO CURRENT_USER WITH SET TRUE` → `BEGIN; SET LOCAL ROLE :"developer_role";` → 本体 → `COMMIT;` → `REVOKE …`。
- 台帳表を作り、**自番号 (`9`) を `INSERT … ON CONFLICT DO NOTHING` で記録する**。**DDL と台帳記録を 1 トランザクションで原子にする。** **台帳 INSERT の `VALUES` は整数リテラルのタプルのみで書く** (設計 §8.1。関数呼び出し・ドル引用符・入れ子括弧は静的規則の走査対象外になり fail-safe 側で違反に落ちる)。
- **`_r2db_missing_rls` を `CREATE OR REPLACE VIEW` で更新する** — 既存 application のビューは `0003` 適用時点の定義で固まっているため、**テンプレート改訂と per-app script の両方**が要る (設計 D-3 (e)(ii))。**テンプレート `0003` 側も `CREATE OR REPLACE VIEW` へ改める** (監督裁定 2026-09-05) — **両者は同じ定義**である。
- **`\q` による skip 経路を持たない** (設計 §1.5 の 7a)。**冪等である。**
- 権限: `REVOKE ALL … FROM :"runtime_role"` の後に **`GRANT SELECT … TO :"runtime_role"`** (U-2 逐語)、および **`GRANT SELECT … TO SESSION_USER`** (provision role、設計 D-3 (a))。
- psql 変数名は **`-v app_slug=…`** (r2db の既存慣行、設計 §3.10)。

**C. backend の bookkeeping 除外集合 (`r2db-api/src/r2db_api/postgres.py`)**

- **現物 (実測)**: `:139` の `_REVISION_TABLE = "_r2db_schema_revision"` が**唯一の除外名**であり、**3 か所**で使われている — `:861` (`_load_catalog` の表列挙、`t.table_name <> {revision_table}`)、`:891` (列の収集)、`:1780` (`_rls_offenders`)。
- **除外用の名前の集合を新設し、この 3 か所を集合に対する除外へ改める。** `_REVISION_TABLE` 自体は当該表への実アクセスで名前として使われ続けるため**残す**。
- **放置した場合の帰結** (設計 D-3 (e)(i)): 台帳表が `offenders` に入り、`application_catalog` と catalog を読む**すべての schema operation** が恒久的に 503 になり、**`create_entity` も 503 になる**。**共通 conformance の catalog 系 vector も落ちる。**

**D. cell open 時検査 (U-2 逐語)**

- data-plane が **cell を開く時点で**台帳の番号集合をパッケージ定数 (最新 per-app 番号集合) と比べ、**未適用があれば最初のリクエストを待たずに `ops upgrade-applications` を示す明示メッセージで SERVICE_UNAVAILABLE を返す**。**メッセージは設計 §3.8 の F-12 から逐語複製する** (常設規律 4。設計 §3.7 の 9〜10 / D-3 (f))。**F-12 は API 応答に現れる唯一の項目**であり、DSN・資格情報・内部ホスト名・宣言値を置かない (SI-10)。
- **置き場は確定済み (監督裁定 2026-09-05。実装者提案は不要)**: **パッケージ定数 (最新 per-app 番号集合、台帳表名、pending 集合計算) は両 peer とも新規モジュール `<peer_pkg>/platform_upgrades.py`** — r2db は `r2db-api/src/r2db_api/platform_upgrades.py`。**番号を増やし忘れたときの挙動は WP-0 の三者一致検査が機械的に閉じる** (下記)。
- **同期漏れは WP-0 の三者一致検査が機械的に閉じる** — 本 WP で当該 `xfail` を撤去する。

**E. `r2db-api/src/r2db_api/ops.py` — `upgrade-applications` / `upgrade-status`**

- **`upgrade-applications`**: 引数 `--application <id>` / `--script <NNNN>` / `--dry-run`。**未適用 = {パッケージが持つ per-app 番号の集合} − {台帳に行が存在する番号の集合}** (集合差)。**`enabled` は対象選択に影響しない。** `database_name` が NULL でない行のみ対象。
  - application DB への接続は **`psycopg.conninfo.conninfo_to_dict(provision_dsn)` の `dbname` を差し替える**。
  - **`psql` subprocess を新設する** — r2db には前例が無い (実測: `ops.py` は `subprocess` を import していない)。**呼び出し形は MitateDB の `_run_deprovision_script` (`MitateDB-api/src/mitatedb_api/ops.py:541-550`) を踏襲し、`_die` は使わない** (即時 exit 2 では全 DB を回せない)。
  - **`_migrations_dir()` 相当も新設する** (r2db には無い。MitateDB は `ops.py:373`)。
  - **ops のテストは新規 `r2db-api/tests/test_ops_upgrade.py` に置く** (監督裁定 2026-09-05。WP-1 の宣言系 `test_ops_declarations.py` とは別ファイル)。
  - **1 つの DB の失敗で止めず全 DB を回し、失敗した DB を列挙して非 0 で終わる。**
  - **失敗した application ごとに `REVOKE <developer_role> FROM <provision role>;` を出力に含める** (設計 D-4 (c) / §3.11 の 8)。
  - **出力**: application ごとに `applied = [番号…]` / `pending = [番号…]` と結果を 1 行。**skip した DB は別枠で列挙する。** 末尾に成功数 / 失敗数 / skip 数。
  - **終了コード**: `0` = 未適用なし / `1` = 列挙失敗 / `2` = 使い方の誤り / `3` = 少なくとも 1 DB で適用失敗 / `4` = `--dry-run` で未適用あり。
- **`upgrade-status [--application <id>]`**: provision DSN のみ。`applied` / `pending` / `database_name`。台帳が無い application は `applied = []`。終了コードは同じ割当。
- **既存の `list-apps` (`ops.py:737` の `cmd_list_apps`、parser 登録は `:1104`) を変更しない** (設計 D-5)。

#### 完了条件 (検証可能な形)

1. **`0009` が台帳表を作り自番号を記録する** — 適用後に `SELECT upgrade_number FROM public._r2db_platform_upgrades` が `{9}` を返すこと (実 PG)。
2. **`0009` が冪等である** — 2 回適用して終状態が同一で、終了コードが 0 であること (実 PG)。
3. **`0009` が `\q` 経路を持たない** — **監査照合 (変異を作らない)**: 監査は `grep -n '\\q' r2db-api/migrations/0009_*.sql` が **0 件**であることを確認する。
4. **本体が失敗したとき台帳行が残らない** — 本体に失敗を注入し、psql が非 0 で終わり、**台帳表に行が無い**こと (実 PG。設計 §10 の実 PG 確認項目 4)。
5. **テンプレート `0003` が台帳付きで provision し、`{9}` を seed する** — 新規 provision した DB の台帳が `{9}` であること (実 PG)。**(b)(i) と (b)(ii) が同じ終状態に着く**こと。
6. **runtime role は `SELECT` のみ** — runtime 接続で `SELECT` が通り、`INSERT` / `UPDATE` / `DELETE` が `permission denied` になること (実 PG。U-2 逐語)。
7. **provision role が台帳を読める** — script 終了後の provision DSN から `dbname` を差し替えた接続で `SELECT` が通ること (実 PG。付与が無いと `--dry-run` すら動かない)。
8. **台帳表に RLS が付いていない** — `pg_class.relrowsecurity` / `relforcerowsecurity` がともに false であること (実 PG)。
9. **`_r2db_missing_rls` が空のまま** — テンプレート経由の新規 DB と `0009` 適用済みの既存 DB の**両方**で、`SELECT table_name FROM public._r2db_missing_rls` が `[]` であること (実 PG。現物の clean-state assert は `r2db-api/tests/test_postgres.py:519-520`)。
10. **backend 除外集合が 3 か所に効いている** — 台帳表がある DB で (i) `application_catalog` が 200 を返し台帳表が entities に**現れない**こと、(ii) `create_entity` が 503 にならないこと、(iii) `verify_row_level_security` が通ること (実 PG。設計 §10 の実 PG 確認項目 5)。
11. **cell open 時検査 (U-2)** — 台帳に未適用番号がある DB (**台帳表そのものが無い場合を含む**) で、**最初のリクエストを待たずに** `SERVICE_UNAVAILABLE` が返り、メッセージが**未適用の番号**と `ops upgrade-applications` を示すこと (実 PG)。**設計 §3.8 の F-12 の骨子を逐語 assert する文字列ピンのテストを置く** (常設規律 4)。
12. **三者一致の `xfail` 撤去** — WP-0 が登録した r2db 側の三者一致 assert が本 WP と**同一コミットで**撤去され、緑であること。
13. **静的規則の `適合 ≥ 1` の `xfail` 撤去** — 同上。**改訂後の集計が 適合 1 / 違反 0 / 免除 0 (r2db)** であること。
14. **`upgrade-applications` の未適用が集合差である** — 台帳が `{9}` でパッケージ定数が `{9, 10}` (合成) のとき pending が `{10}` になること。**台帳が `{10}` で 9 が欠けている状態でも 9 が pending として出る**こと (最大番号方式ではないことの実測)。
15. **`upgrade-applications` が冪等で、全 DB を回す** — 2 回目の実行で何も起きず 0 で終わること。**1 DB を失敗させても他 DB が処理され、失敗 DB が列挙され非 0 (3) で終わる**こと。
16. **失敗時に `REVOKE` 文が出力される** — 失敗した application ごとに `REVOKE <developer_role> FROM <provision role>;` が出力に含まれること。
17. **終了コードの 5 値** — `0` / `1` / `2` / `3` / `4` をそれぞれ観測すること。
18. **`--script` が未適用限定である** — 記録済みの DB に `--script` を指定すると `recorded, skipped` と出力し**成功扱い**になること。
19. **`upgrade-status` が provision DSN のみで動く** — `applied` / `pending` / `database_name` を出し、台帳が無い application は `applied = []` になること。終了コードが `0` / `4` を返すこと。
20. **既存 `list-apps` が無変更** — **監査照合 (変異を作らない)**: 監査は `git diff -- r2db-api/src/r2db_api/ops.py` の変更行に `cmd_list_apps` の本文が**1 行も含まれない**ことを確認する。
21. **契約不変** — **監査照合**。`git diff -- spec/` が空。
22. **MitateDB 側が差分に現れないこと** — **監査照合**。
23. **対応表に対応の無い行が無いこと** (メタ条件)。
24. **完了ゲート** — 監督が root suite を単独実行する。

#### 非 vacuity 要件

- 条件 10 は**台帳表が実際に存在する DB** に対して観測する。台帳を作らずに「除外が効いている」と主張しない。
- 条件 14 は**穴のある台帳** (`{10}` で 9 が欠ける) を実際に作って観測する。集合差の意味を固定する唯一の手段である。
- 条件 15 の「1 DB を失敗させる」は**実 PG で本体に失敗を注入して**行う。stub で済ませない。

#### 同型性テスト対象

**本 WP で新設する同名ヘルパ** — 台帳の pending 集合計算、ops の `psql` 実行/集計ヘルパ。**本 WP は対応表 (`_ISOMORPHIC_TARGETS`) を触らない** (**監督裁定 2026-09-05**) — これらの行は **WP-4 が WP-4 自身のヘルパ行とまとめて追加**する。**`xfail(strict=True)` の placeholder は登録しない。** 実装者は**新設した同名ヘルパの一覧 (関数名とファイル)** を完了報告に列挙し、WP-4 の発注へ引き渡すこと。

#### 変異注入 (必須)

| 完了条件 | 対応する変異 |
|---|---|
| 1 台帳作成と自番号記録 | **変異 1** (`0009` から台帳 INSERT を落とす → 条件 1 が赤。**静的規則も違反 1 件を出す**ことを併せて記録する) |
| 2 冪等 | **変異 2** (`CREATE TABLE IF NOT EXISTS` の `IF NOT EXISTS` を外す → 2 回目が赤) |
| 3 `\q` 不在 | **監査照合** |
| 4 失敗時に行が残らない | **変異 3** (台帳 INSERT を `COMMIT` の後へ出す → 失敗注入時に行が残り赤) |
| 5 テンプレートの seed | **変異 4** (`0003` の seed リストを空にする → 条件 5 が赤。**三者一致も赤**になることを併せて記録する) |
| 6 runtime `SELECT` のみ | **変異 5** (`GRANT SELECT … TO :"runtime_role"` を落とす → runtime の `SELECT` が赤) |
| 7 provision の `SELECT` | **変異 6** (`GRANT SELECT … TO SESSION_USER` を落とす → `--dry-run` が `permission denied` で赤) |
| 8 RLS 無し | **変異 7** (台帳表に `ENABLE ROW LEVEL SECURITY` を足す → 条件 8 が赤) |
| 9 RLS 監視ビュー | **変異 8** (`0009` の `CREATE OR REPLACE VIEW` を落とす → 既存 DB 経路で `_r2db_missing_rls` に 1 行残り赤。テンプレート側だけでは既存 DB に遡及しないことの実測) |
| 10 backend 除外集合 | **変異 9** (`postgres.py:1780` の除外だけを元へ戻す → `create_entity` / `verify_row_level_security` が 503 で赤。3 か所が独立に効いていることの実測) |
| 11 cell open 検査 | **変異 10** (検査呼び出しを落とす → 未適用 DB でリクエストが通ってしまい赤) |
| 12 三者一致 | **変異 11** (パッケージ定数から `9` を落とす → 三者一致が赤) |
| 13 静的規則 `適合 ≥ 1` | **変異 1 と同じ差分で観測する** (別の変異を作らない。報告に両方の赤を記録する) |
| 14 集合差 | **変異 12** (未適用の計算を「台帳の最大番号より大きい」へ戻す → 穴のあるケースが赤) |
| 15 全 DB 走査 | **変異 13** (失敗時に `_die` で即時 exit する形へ変える → 他 DB が処理されず赤) |
| 16 `REVOKE` 出力 | **変異 14** (`REVOKE` 行の出力を落とす → 当該テストが赤) |
| 17 終了コード | **変異 15** (`--dry-run` の未適用時の戻り値を 0 へ変える → 条件 17 が赤) |
| 18 `--script` の未適用限定 | **変異 16** (`--script` を記録済み DB にも当てる形へ変える → 条件 18 が赤) |
| 19 `upgrade-status` | **変異 17** (台帳が無い application で例外を投げる形へ変える → `applied = []` が赤) |
| 20 `list-apps` 無変更 | **監査照合** |
| 21 契約不変 | **監査照合** |
| 22 MitateDB 不干渉 | **監査照合** |
| 23 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 24 完了ゲート | **監査照合** |

**migration の適用を伴う変異は、復元後の再構築結果も報告に書くこと** (§6)。

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q conformance-tests -k r2db-api
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **除外集合の漏れ** — `postgres.py` の **3 か所すべて** (`:861` / `:891` / `:1780`) が集合に対する除外へ改まっているか。1 か所でも漏れると catalog か RLS 検査のどちらかが恒久的に壊れる。
2. **ビューの「対」** — テンプレート `0003` と per-app `0009` の**両方**で除外名が足されているか。片方だけでは既存 DB か新規 DB のどちらかに残る。
3. **台帳 INSERT の位置** — `COMMIT` の内側か。静的規則は位置を検査しないので、ここはレビューと実 PG テストが担う。
4. **`_die` の混入** — 一括適用に `_die` が使われていないか (即時 exit では全 DB を回せない)。
5. **psql 変数名** — **r2db は `-v app_slug=…`** である。MitateDB の `app_id` を持ち込んでいないか。
6. **`enabled` による絞り込み** — 無効化中の application が対象から外れていないか (設計 D-4 (a): `enabled` は対象選択に影響しない)。
7. **パッケージ定数の置き場** — **確定済みの `<peer_pkg>/platform_upgrades.py`** に置かれているか (監督裁定 2026-09-05)。定数と `migrations/` の同期が三者一致で閉じているか。
8. **cell open 検査のメッセージ** — 設計 §3.8 の **F-12 から逐語複製**されており、未適用の番号と `ops upgrade-applications` を示しているか。運用者は AI エージェント前提であり、次に打つコマンドが要る。**API 応答に現れる唯一のメッセージ**なので DSN / 内部ホスト名 / 宣言値が混じっていないか (SI-10)。
9. **秘密の混入** — ops の出力例・テスト・migration に実 DSN / 実ホスト名が無いか。
10. **一時 membership** — script 側の `REVOKE` が `COMMIT` の後にある既存形を変えていないか (変えるなら射程外の改変として上げる)。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-4 MitateDB — per-application 台帳と一括適用 (`0003` 改訂 + `0008` + 除外集合 + cell open 検査 + ops)

#### 目的

**WP-3 と同じ安全成果を同じ形で MitateDB に置く。** ただし **MitateDB のみ `0006` の backfill を持ち、RLS 監視ビューを持たない** — この 2 点が非対称である。**WP-3 の裁定・レビュー指摘を発注時点で織り込むこと。**

#### 変更対象

**A. `MitateDB-api/migrations/0003_provision_application.sql` (テンプレート改訂)** — 台帳表 `public._mdb_platform_upgrades` を作り、**その時点の全 per-app 番号 (`{6, 8}`) を適用済みとして seed する**。**seed の `VALUES` は整数リテラルのタプルのみで書く** (設計 §8.1。関数呼び出し・ドル引用符・入れ子括弧は静的規則の三者一致検査をすり抜けず fail-safe 側で不一致に落ちる)。**MitateDB に `_r2db_missing_rls` 相当のビューは無い (実測)** ので、ビューの改訂は無い。

**B. `MitateDB-api/migrations/0008_<name>_upgrade.sql` (新規、per-app upgrade)**

- WP-3 の B と同型。psql 変数名は **`-v app_id=…`**。
- **自番号 (`8`) を記録する。**
- **`0006` の適用済みを backfill する** — 判定は `to_regclass('public._mdb_field_types') IS NOT NULL`。**`_mdb_field_types` が無ければ 6 を記録しない** — 台帳が `{8}` になった DB では 6 が**未適用として残り**、`ops upgrade-applications` が後から `0006` を当てる (設計 D-3 (b)(ii))。
- 権限: `REVOKE ALL … FROM :"runtime_role"` の後に **`GRANT SELECT`** (U-2)、および **`GRANT SELECT … TO SESSION_USER`**。

**C. backend の bookkeeping 除外集合 (`MitateDB-api/src/mitatedb_api/backend_postgres.py`)**

- **現物 (実測)**: `:384-391` の `schema_count()` が `table_name NOT IN (%s, %s)` で `_SCHEMA_REVISION_TABLE` と `_FIELD_TYPES_TABLE` の **2 件**を除いている。**第 3 の名前を足す。**
- **放置すると全 application の `schema_objects` 会計が +1 ずれる** (SI-08 の限度検査に効く)。**catalog 本体は `_mdb_field_types` 由来なので entity 列挙には出ない** — r2db との非対称である (設計 §3.10)。

**D. cell open 時検査 (U-2)** — WP-3 の D と同型。パッケージ定数は `{6, 8}`。**置き場は `MitateDB-api/src/mitatedb_api/platform_upgrades.py`** (監督裁定 2026-09-05)。メッセージは設計 §3.8 の **F-12** から逐語複製する。

**E. `MitateDB-api/src/mitatedb_api/ops.py` — `upgrade-applications` / `upgrade-status`**

- WP-3 の E と同型。**`_migrations_dir()` (`:373`) と `_run_deprovision_script` (`:541-550`) の呼び出し形が既にある** — 呼び出し形だけを踏襲し、**`_die` は使わない**。**ops のテストは新規 `MitateDB-api/tests/test_ops_upgrade.py` に置く** (監督裁定 2026-09-05。既存 `tests/test_ops.py` には足さない)。
- **`--script 0006` の危険 (設計 D-4 (f))**: `0006` の backfill は `information_schema.columns` を走査し、除外は 2 件だけである。**台帳表が既に存在する DB に `--script 0006` を流すと台帳表の 3 列が `_mdb_field_types` に混入する。** `0006` は出荷済みで in-place 改訂できないので、**防御は ops 側の「`--script` は未適用の DB にだけ当てる」に依存する** — この防御が本 WP の完了条件である。
- **既存の `list-applications` (`ops.py:382` の `cmd_list_applications`、parser 登録は `:805`) を変更しない。契約 shape の `ApplicationsResult` のまま**である (設計 D-5)。

#### 完了条件 (検証可能な形)

**WP-3 の完了条件 1〜24 を MitateDB の名前で読み替えたもの**を用いる。ただし次が異なる。

- **条件 5 (テンプレートの seed)** — seed 集合は **`{6, 8}`** である。
- **条件 8 / 9 (RLS)** — **MitateDB に RLS 監視ビューは無い** ので条件 9 は無い。条件 8 (台帳表に RLS を付けない) は残る。
- **条件 10 (backend 除外集合)** — 検査対象は **`schema_count()` の会計** である。台帳表がある DB で **`schema_objects` の値が台帳表を数えない**こと (実 PG)。**catalog の entity 列挙には現れない**ことも併せて観測する (peer 非対称の実測)。
- **追加条件 25: `0006` の backfill** — `_mdb_field_types` がある DB では台帳が **`{6, 8}`**、無い DB では **`{8}`** になること (実 PG。**両方を観測する**)。
- **追加条件 26: `{8}` の DB で 6 が pending として残る** — `ops upgrade-status` が `pending = [6]` を出し、`ops upgrade-applications` が後から `0006` を当てられること (集合差定義の実効の実測)。
- **追加条件 27: `--script 0006` が台帳のある DB を skip する** — 台帳表が既に存在する DB に `--script 0006` を指定しても `0006` が**実行されず** `recorded, skipped` になり、**`_mdb_field_types` に台帳表の 3 列が混入しない**こと (実 PG。設計 D-4 (f))。
- **条件 20 (既存一覧コマンド無変更)** — 監査は `cmd_list_applications` の本文が diff に**1 行も含まれない**こと、**出力が契約 shape の `ApplicationsResult` のまま**であることを確認する。
- **条件 22 (不干渉)** — 監査は `git diff --name-only` に **`r2db-api/` が 1 件も現れない**ことを確認する。
- **追加条件 28: 対応表への行追加 (WP-3 分 + WP-4 分)** — **監督裁定 2026-09-05 により、対「WP-3 / WP-4」のヘルパ行は後半 WP である本 WP がまとめて追加する。** WP-3 が新設した同名ヘルパ (台帳の pending 集合計算、ops の `psql` 実行/集計) と本 WP の対応するヘルパの行を `_ISOMORPHIC_TARGETS` へ足し、**pin テスト関数名の行数部分と当該行の両方を改め**、対応表が両 peer で緑になること。**`xfail(strict=True)` の placeholder は用いない。既存行が 1 対も落ちていない**こと。
- **追加条件 29: MitateDB 側の静的規則の集計** — 改訂後の集計が **適合 1 / 違反 0 / 免除 1 (`0006`) / 対象外 = 残り**であること。**許可リストが `{6}` のまま増えていない**こと (LQ4-10)。

#### 非 vacuity 要件

WP-3 と同一。加えて、**条件 25 は `_mdb_field_types` の有無で分岐する 2 つの DB を実際に作って**観測する。片方だけでは backfill 判定が固定されない。

#### 変異注入 (必須)

**WP-3 の変異 1〜17 を MitateDB の名前で読み替えたもの** (変異 8 = RLS ビューは対象外) に、次を足す。

| 完了条件 | 対応する変異 |
|---|---|
| 25 backfill | **変異 18** (`to_regclass` ガードを外して常に 6 を記録する形へ変える → `_mdb_field_types` が無い DB のケースが赤) |
| 26 `{8}` の DB で 6 が pending | **変異 19** (パッケージ定数から `6` を落とす → 条件 26 と三者一致が赤) |
| 27 `--script 0006` の skip | **変異 20** (`--script` の未適用限定を外す → `_mdb_field_types` に台帳表の 3 列が混入し赤) |
| 28 対応表への行追加 (WP-3 分 + WP-4 分) | **変異 21** (**WP-3 由来の新規行**について片 peer のヘルパを 1 箇所変える → 対応表の当該行が赤) |
| 29 静的規則の集計 | **変異 22** (許可リストに `8` を足す → 免除が 2 件になり集計 assert が赤) |

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests -k MitateDB-api
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

**WP-3 の 1〜10 (2 を除く) に加えて:**

11. **backfill 判定の向き** — `_mdb_field_types` が**無い**とき 6 を記録して**いない**か。記録してしまうと未適用が永久に検出されない。
12. **`--script 0006` の防御** — ops 側にしか置けない防御が実際に効いているか。**この 1 点が壊れると既存 application の `_mdb_field_types` が汚れる。**
13. **`schema_count()` の会計** — 除外が 2 件から 3 件に増えているか。SI-08 の限度検査に直接効く。
14. **`list-applications` の契約 shape** — `ApplicationsResult` に列が足されていないか (U-1 は「載せない」である)。
15. **psql 変数名** — **MitateDB は `-v app_id=…`** である。r2db の `app_slug` を持ち込んでいないか。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-5 記録整理 (conformance adapter の最終形 + 文書 + ハンドオーバー)

#### 目的

WP-0〜4 の実測を正本へ落とし、配備手順と対応表を現在形にし、**ハンドオーバー第14次**を起こす。

#### 変更対象

**1. conformance HTTP adapter の最終確認**

- **MitateDB HTTP plug** — `control_env` から廃止 env が除かれ、fixture の platform DB に宣言表と書き手 role の 2 設定が seed されていること (WP-2 で出荷済み)。**本 WP はその形が最終形であることの確認と、設計 §6.1 α への実測の記録**である。
- **r2db HTTP plug** — `assemble_control_stack(…, surfaces=_SURFACES)` の**明示注入のまま**であること、`os.environ.setdefault` の 2 行が消えていること (WP-1 で出荷済み)。**宣言表の読み出しの検証は r2db peer-local の実 PG テストが単独で担う**ことを記録する。
- **`conformance-tests/` の vector と port は変更しない** (設計 §6.1)。**registry.json の 4 adapter は不変である。**

**2. `security/CONTROL_MAPPING.md` (D-6 の 1) — 3 行**

- **SI-02 行 (`:11`)** — `ops upgrade-applications` が provision DSN のみで動き、API プロセスがその資格を持たないこと。
- **SI-12 行 (`:21`)** — 台帳表と宣言表の権限。**runtime role は `SELECT` のみ** (U-2)。宣言表は application role が接続しない platform DB にあること。
- **SI-14 行 (`:23`) の点 (12)** — 逐語 **"nothing enforces it"** を改める。**置換文言は限定付きである** (設計 D-6 の 1 が正本): 「**同一の platform データベースを前提に**、宣言の根拠と実効値の根拠が**同一の catalog** になった。両プロセスは同じ一次情報から導出し、各プロセスは自身の実効値との一致を起動時に検査する」。**両プロセスが同じ platform DB を指していること自体は本設計が検証しない** (§3.11 の 7) ので、**この限定を落とすと過大主張になる。**
- **evidence テスト名はすべて `grep` で 1 件以上に解決すること。**

**3. runbook と配備設定 (D-6 の 2)**

- **`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`** / **`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md`** — 設計 §9.1 の適用手順 6 段、§9.2 の定常運用 (**再起動順序: 縮めるときは data-plane 先、伸ばすときは control 先**)、§9.3、§9.4、**廃止 env 4 本の一覧**。
- **`MitateDB-api/docs/cloud-run-cloud-sql.md`** — 同。**廃止変数の実値記載は `:843` / `:890` の `--set-env-vars=…` 例**にあり、言及のみの箇所は `:324` / `:343` / `:848-856` / `:893` である (実測)。
- **`r2db-api/deploy/env/api.env.example`** — **実値で設定している行は `:120-121` (timeout 2 本) と `:162` (`R2DB_DATA_BASE_URL`)**、言及のみは `:110` / `:168` / `:175` (実測)。
- **`r2db-api/deploy/env/control.env.example`** — **実値で設定している行は `:72` / `:79` (base URL 2 本) と `:139-140` (timeout 2 本)**、言及のみは `:25-26` / `:77` / `:129` (実測)。
- **MitateDB には `deploy/env/*.example` 相当が無い** (実測) — 上記 runbook 1 本で覆われる。
- **廃止 4 変数を実値で設定したまま残すと、それをコピーした配備は次回起動で必ず F-1 / F-2 で止まる。** 削除し、代わりに打つ ops コマンドを案内する。

**4. DEPLOY 系作業指示書** — `docs/work-orders/DEPLOY_PHASE6_20260904.md` の配備後チェックに、**`ops show-declarations` / `ops upgrade-status` と、両 surface の `/capabilities` が同じ `surfaces` と `visibility_lag_ms` を返すことの突合**を加える。**この突合は本フェーズ後も依然として必要である** — 両プロセスが同じ platform DB を指していること自体は本設計が検証しない (LQ4-16)。

**5. 正本 2 文書への日付付き閉止注記 (D-6 の 3。本文は書き換えない)**

- `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` **§11.2 Q4**
- `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` **§11 L6-5a** と **同 L6-20 (f)**

**6. 設計 `Q4_DB_SIDE_SINGLE_TRUTH_V1.md`**

- **§10** — WP-0 のスキャナ改訂後の実測出力、および実 PG 確認項目 1〜5 の結果を貼る。
- **§12** — LQ4-1 / LQ4-2 / LQ4-3 を裁定済みとして閉じ、残る項目を現在形にする。**新たに見えた項目は LQ4-20 以降として起票する。**
- **§13 実施記録** — 集計行、WP ごとのコミット、受理境界、実測事項。**プレースホルダを 1 つも残さない。**
- **§6.2 (契約に載せる場合) を「採用せず」として記録に残す** (U-1 逐語の指示)。

**7. ハンドオーバー第14次** — `docs/work-orders/HANDOVER_20260904_FABLE2.md` (第13次) の後継。**最終集計行・各 WP のコミット・依頼者の次の判断事項・本フェーズが増やした運用前提**を明記する。運用前提として少なくとも: **宣言の変更は「ops → 両プロセス再起動」の 1 組であること**、**廃止 env 4 本が残っていると起動しないこと**、**新しい per-app upgrade を出すときの規律 (設計 §9.4)**、**接続プーラ下での起動時検査の射程 (LQ4-15、現配備にプーラがあるかは未確認)**。

**8. 本書 §11 (実施記録)** — 各 WP の完了日・コミット (merge)・root suite の集計行・分割の有無。

#### 完了条件 (検証可能な形)

**本 WP は記録整理であり、製品コード・テストを変更しない。したがって変異注入は行わない。** 代わりに全条件へ**監査照合**を明記する。

1. **adapter の最終形** — **監査照合**: 監査は `grep -n "R2DB_DATA_BASE_URL\|R2DB_CONTROL_BASE_URL" r2db-api/conformance/conformance_adapter_r2db_http.py` が 0 件、MitateDB の `control_env` に廃止 env が無いことを確認する。**`conformance-tests/` の `git diff` が空**であること (vector / port / registry.json 不変)。
2. **CONTROL_MAPPING 3 行** — **監査照合**: 監査は SI-02 / SI-12 / SI-14 の各行が**両 peer の cell を対で**書き換えられていること、SI-14 の置換文言が**「同一の platform データベースを前提に」という限定を含む**ことを確認する。**限定を落とした過大主張は差し戻し。** evidence テスト名を 1 件ずつ `grep -rn` し**全件が 1 件以上に解決する**ことを確認する。
3. **runbook / 配備設定の全数更新** — **監査照合**: 監査は `DATA_BASE_URL|CONTROL_BASE_URL|AUDIT_STATEMENT_TIMEOUT_MS|AUDIT_IDLE_TIMEOUT_MS` を repo 全体に grep し、**実値で設定している行が 0 件**であることを確認する。言及のみの行は「廃止された」旨の記述になっていることを確認する。
4. **再起動順序の記録** — **監査照合**: 監査は runbook 3 本に **「縮めるときは data-plane 先、伸ばすときは control 先」**が書かれ、**理由 (C-09 の消費者が見えていない行を見逃す)** が添えられていることを確認する。
5. **DEPLOY 文書の配備後チェック** — **監査照合**: 監査は追加された項目が**実行可能な形** (どのコマンドで何を見るか) で書かれ、**「両プロセスが同じ platform DB を指すことは実装が検証しない」**という限定を含むことを確認する。
6. **日付付き閉止注記 3 件** — **監査照合**: 監査は 3 箇所の `git diff` を読み、**原文の行が削除されていない**ことと、注記が日付付きであることを確認する。
7. **設計 §10 / §12 / §13** — **監査照合**: 監査は §13 に**プレースホルダが 0 件**であること、集計行を `git log --oneline` の merge コミットおよび各 WP の完了報告と突き合わせ**3 者が一致する**ことを確認する。「変異注入の結果」が各 WP の対応表の**変異行の件数**と一致することを確認する。
8. **§6.2 の「採用せず」記録** — **監査照合**: 監査は U-1 の逐語 (「§6.2 (契約に載せる場合) は『採用せず』として記録に残す」) が満たされていることを確認する。
9. **契約不変** — **監査照合**: `git diff -- spec/ r2db-api/src/r2db_api/contract/ MitateDB-api/src/mitatedb_api/contract/` が**空**、両 peer の `contract_version` が **1.6.0 のまま**。
10. **ハンドオーバー第14次** — **監査照合**: 監査は最終集計行を本書 §11 および完了ゲートの実測値と突き合わせ、各 WP のコミットを `git log` と突き合わせ、判断事項を**設計 §12 の残存項目**と突き合わせて**取りこぼしが 0 件**であることを確認する。
11. **正直さの後退がないこと** — **監査照合**: 監査は「閉じた」の主張を**両 peer 分の実装コミット**と突き合わせる。とくに次の 4 つの限界が覆い隠されていないこと: (i) **両プロセスが同じ platform DB を見ていることは検証しない** (LQ4-16)、(ii) **control は `*svc_api` の実効値を検証できない** (LQ4-15 (i))、(iii) **起動時スナップショットであり pool が後から張った接続は検査されない** (LQ4-15 (ii))、(iv) **宣言変更時の過渡的なずれは残る** (LQ4-17)。**範囲外項目が「対応不要」と読める書き方に化けていないこと。**
12. **秘密の非混入** — **監査照合**: 監査は本 WP の `git diff` の追加行全体を `docs/security/public-repository-policy.md` の禁止事項一覧および CLAUDE.md の Public Repository Security Gate と 1 項目ずつ突き合わせる。**すべてが環境変数名・secret-manager 参照・架空ドメイン・合成 fixture のいずれか**であることを確認する。
13. **対応表に対応の無い行が無いこと** (メタ条件)。
14. **root suite の最終実測 (単独実行)** の集計行を本書 §11 に記録すること。**監査照合**: 監査は記録した集計行を**監督が単独実行して得た実測出力そのもの**と突き合わせ、4 数の一致と**出所 (誰がいつ単独実行した値か)** の明記を確認する。

#### 非 vacuity 要件

**本 WP は文書のみであるため、テストの非 vacuity 要件は無い。** 代わりに **evidence テスト名の実在性** (条件 2) がその位置を占める — **1 件でも grep に解決しない名前があれば赤**である。

#### 同型性テスト対象

**変更なし** (テストを触らない)。WP-0〜4 で確定した対象一覧と最終行数を設計 §13 に記録する。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
```

完了ゲート (root suite、件数不変であること) は監督が単独実行する。

#### レビューが必ず探すべき点 (Opus、テンプレ 6 = 受け入れ監査)

1. **SI-14 の置換文言の強さ** — 「解消した」と無限定に書いていないか。**限定 (同一 platform DB 前提) が落ちていないか。**
2. **記録と実装の乖離** — CONTROL_MAPPING / 設計 §13 / 台帳が主張する evidence が、実在し実際に走るテストへ解決するか。**各 WP で採ったテスト名と本書の完了条件に書いた予定名が食い違っていないか** (食い違うなら**記録側を実装に合わせる**)。
3. **廃止 env の掃討漏れ** — 実値で設定した行が 1 つでも残っていないか。**残ると次回配備が必ず止まる。**
4. **範囲外項目の扱い** — LQ4-14 / LQ4-18 / LQ4-8 が「対応不要」ではなく**将来課題 / 依頼者判断待ち**として保たれているか (L6-17 は本フェーズで閉じる — §2 の 5 の上書き裁定)。
5. **代償の記録** — **`ALTER ROLE … SET` の射程が監査書き込みに限られない**こと (LQ4-4: credential store 照会と control-plane registry 操作もこの timeout の下に入る) が、runbook に**運用者責任として**書かれているか。「対称化した」だけの記述に化けていないか。
6. **台帳の性質** — 「台帳は運用の一次記録であって改竄不能な証拠ではない」(設計 §3.9) が保たれているか。過大に「証跡」と書いていないか。

#### 使用テンプレート

起草 = Opus (テンプレ 4 = 文書起草)。受け入れ監査 = Opus (テンプレ 6)。

---

## 5. 期待される実測値

| WP | root suite (passed / failed / skipped / xfailed) | conformance | 期待される変化 |
|---|---|---|---|
| **基準値** | `{監督が着手時に単独実行して記録}` / 0 / 0 / 0 | `{記録}` | フェーズ6 完了時点 (main、契約 1.6.0) |
| **WP-0** | `{実装者が報告し監督が記録}` / 0 / 0 / **`{xfail 登録数}`** | **不変** | ms ヘルパの単位ケース (両 peer)、静的規則スキャナ (合成 fixture + 実 `migrations/`)、対応表の行追加。**`適合 ≥ 1` と三者一致の `xfail(strict=True)` を両 peer 分登録するため `xfailed` が増える** |
| **WP-1** | `{報告}` / 0 / 0 / **`{WP-0 分と同数}`** | `{報告}` | r2db の宣言経路の切り替え。**本 WP は対応表を触らず placeholder も登録しないので `xfailed` は WP-0 分から増えない** (監督裁定 2026-09-05) |
| **WP-2** | `{報告}` / 0 / 0 / **`{WP-0 分と同数}`** | `{報告}` | MitateDB の同。**WP-1/WP-2 のヘルパ行が対応表へまとめて足される (placeholder は無いので `xfailed` は不変)** |
| **WP-3** | `{報告}` / 0 / 0 / **`{MitateDB 分の WP-0 xfail のみ}`** | `{報告}` | r2db の台帳。**r2db 側の `適合 ≥ 1` / 三者一致の `xfail` が撤去される。対応表は触らない** |
| **WP-4** | `{報告}` / 0 / 0 / **0** | `{報告}` | MitateDB の台帳。**MitateDB 側の `xfail` がすべて撤去され `xfailed` が 0 に戻る。WP-3/WP-4 のヘルパ行が対応表へまとめて足される** |
| **WP-5** | `{報告}` (件数不変) / 0 / 0 / **0** | `{報告}` (不変) | 文書のみ |

**本数は「テスト関数数」ではなく「収集された test id 数」で数える。上表の `passed` 欄は見積りを置かない** — 実装者が増減内訳を報告し、監督が記録する。**本フェーズで登録する `xfail` は WP-0 の 2 種 (`適合 ≥ 1` / 三者一致) を両 peer 分だけ**であり (**監督裁定 2026-09-05 により同型性 placeholder は生じない**)、**WP-0 の実測値が確定すれば WP-1〜WP-4 の期待値もそれで決まる。WP-4 完了時に 0。** **実装者は登録した `xfail` の内訳 (どのテストを、どの WP で撤去するか) を完了報告に列挙すること** — 列挙が無い `xfail` は完了と判定しない。

**完了ゲートの判定**: 各 WP で root suite を単独実行し、`failed` / `skipped` が **0**、`xfailed` の内訳が報告と一致し、`passed` の増減内訳が説明されていること。**見積りと実測が食い違ったら実測が正であり、食い違いの理由を完了報告に書くこと。**

---

## 6. 完了ゲートの実測規律 (全 WP 共通。フェーズ6 §6 を継承)

- 完了ゲートの root suite は**リポジトリルートで単独実行する** — `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`。**`ps` で他の pytest プロセスが 0 件であることを確認してから実行する。** ローカル PostgreSQL は `max_connections = 300` が前提。
- **速度規律 (§0.2)**: root suite を回すのは**監督の完了ゲート 1 回のみ**。実装担当は peer 別 suite と担当ファイルの conformance だけを回す。受け入れ監査は監督のゲートログを突合し suite を再実行しない。コードレビューは実装報告に無い変異 1〜2 種だけを自分で試す。
- **テストは前景で実行する。`timeout` を明示すること (600000 ms)。** **サブエージェントはバックグラウンド待ちで止まるので、完了ゲートの実測値は監督が自分で握る。**
- 実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない。**
- 各 WP の完了報告に **集計行 (passed / failed / skipped / xfailed)** を必ず記録し、**増減の内訳**を書く。
- **変異注入は scratchpad へ復元する。`git checkout` は使わない。**
  - **本リポジトリは Google Drive 同期ツリーである。** 変異前に対象ファイルを scratchpad へ backup し、**`sleep 3` の後に `sha256` で二重照合する** (backup と復元後の一致を 2 回確認する)。
  - **コミット前に変異文字列そのものを全文 grep する。**
  - **migration の適用・ファイルの退避を伴う変異は、復元後の再構築結果も報告に書く。**

---

## 7. 禁止事項 (全 WP 共通)

1. **git commit / push は監督のみが行う。** Sonnet も Opus もコミットしない。
2. **出荷済み migration を in-place で編集しない。** r2db の `0001` / `0002` / `0005` / `0006` / `0007`、MitateDB の `0001` / `0002` / `0005` / **`0006`**。**`MitateDB-api/migrations/0006_declared_field_types_upgrade.sql` はとくに触らない** — 許可リストで免除する対象であり、改訂ではなく免除で扱う。
3. **provisioning テンプレート (`0003` / `0004`) は改訂してよい** — 毎回実行されるテンプレートであり一回適用 migration ではない。**テンプレート改訂と per-app upgrade script は対で出す。**
4. **`spec/` を変えない。** 本フェーズは契約無変更である (U-1)。両 peer のパッケージ内コピーも同様。`contract_version` は 1.6.0 のまま。
5. **秘密・実データ・実在ドメインを書かない。** 環境変数名・secret-manager 参照・架空ドメイン (`example.invalid` 等)・合成 fixture のみ。**公開リポジトリである。** とくに ops の出力例・fail-fast メッセージ・runbook の配備手順に注意する。
6. **リポジトリ内に一時物を残さない。** 合成 fixture は `tmp_path` に作る。変異ファイル・変異定義・スキャナの生出力をリポジトリへ置かない (生出力は `{scratchpad}` へ)。
7. **設計に無い機構を無断で足さない** (常設規律 7)。**ただし置き場 3 件は監督裁定 2026-09-05 で確定済みであり、実装者提案は不要である** — パッケージ定数 = `<peer_pkg>/platform_upgrades.py`、ms ヘルパ = `<peer_pkg>/pg_timeouts.py` (`ms_from_pg_timeout_text`)、ops テスト = 宣言系 (WP-1/WP-2) は `tests/test_ops_declarations.py`、upgrade 系 (WP-3/WP-4) は `tests/test_ops_upgrade.py` (いずれも両 peer)。**これ以外の設計外の検査・機構は実装前に上げる。**
8. **互換シムを作らない。二形式受理を置かない。** 廃止 env のフォールバック、宣言表が無いときの env への退避、台帳が無いときの「最大番号」推測を製品コードに置かない。**移行は migration と ops で行う。**
9. **guard を弱めて緑にしない** — `xfail(strict=True)` の `strict` を落とす、静的規則の許可リストを増やして違反を消す、非空振り要件を「1 件でも通れば緑」へ緩める、のいずれも禁じる。**緑にする正しい手段は実装を真にすることだけである。**
10. **peer 間でコードを共有しない。** 同名ヘルパは同型性テストで固定する。共有モジュールを作らない (依頼者裁定 2026-09-03)。
11. **`git checkout` による変異復元を禁じる。**
12. **テストの並行実行を禁じる。** 完了ゲートは単独実行する。`ps` で他の pytest が 0 件であることを確認してから。
13. **範囲外項目に触れない** (§2)。「ついでに」直さない。
14. **制約・制限の追加で問題を回避しない** (依頼者設計原則 3)。**「検証が難しいから任意にする」「壊れやすいから検査を落とす」は回避である。**
15. **fail-fast メッセージを言い換えない。** 設計 §3.8 から逐語複製する。**「次に打つ ops コマンド名」を落とさない** — ゲートではなくガードレールとして成立するのはメッセージが次の一手を示しているからである。
16. **`_die` を一括適用に使わない** (D-4 (b))。即時 exit 2 では「止めずに全 DB を回す」と両立しない。
17. **既存の application 一覧コマンドを変更しない** (D-5)。r2db `list-apps` / MitateDB `list-applications` の**資格要件も出力の shape も**変えない。
18. **変異ファイル・変異定義を残さない。** 復元を **scratchpad backup + sha256 二重照合**で確認し、**コミット前に変異文字列を全文 grep する。**

---

## 8. コミット規律

- **WP ごとに 1 コミット** (WP-0 / WP-1 / WP-2 / WP-3 / WP-4 / WP-5 で計 6 コミット)。それ以外の分割は監督の許可を要する。
- **WP-1 と WP-2、WP-3 と WP-4 は並行 worktree で実装してよいが、コミットは別々**である。**マージ順は WP-0 → WP-1 → WP-2 → WP-3 → WP-4 → WP-5 で確定である** (**監督裁定 2026-09-05**)。
- **対応表 (`_ISOMORPHIC_TARGETS`) を触るのは WP-0 / WP-2 / WP-4 の 3 つだけである** (監督裁定 2026-09-05)。**WP-0** = 静的スキャナと ms ヘルパの行、**WP-2** = WP-1/WP-2 のヘルパ行、**WP-4** = WP-3/WP-4 のヘルパ行。**WP-1 / WP-3 / WP-5 は触らない。** 行を足す WP は pin テスト名の行数部分も同一コミットで改める。これで並行 worktree の衝突点は無い。
- **`xfail(strict=True)` の撤去は WP-0 が登録した 2 種のみである** — **`適合 ≥ 1` / 三者一致の `xfail` は、当該 peer の per-app script を出す WP (r2db = WP-3 / MitateDB = WP-4) と同一コミットで撤去する。** 同型性対応表の placeholder は本フェーズでは用いない。
- **identity は `r2fish` / noreply**。実名・Gmail を使わない。**コミット前に必ず `git log --format='%an <%ae>'` で確認する。**
- **commit → push → main merge (`--no-ff`) は 1 セット**。コミットしたら直ちに push し、main へマージする。**分離しない。**
- コミットメッセージは日本語可。**WP 番号・変更の要旨・完了ゲートの集計行 (`Root suite alone:` 行) を含める。**
- 各コミットの前に、独立レビュー (Opus、変異注入込み) と受け入れ監査の往復が完了していること。

---

## 9. 確定文言の所在

| 対象 | 正本 | 規律 |
|---|---|---|
| **依頼者裁定 U-1 / U-2 / U-3、migration 番号の割当** | **`{scratchpad}/rulings-q4-requester.md`** (設計 §5 / §8 が同文を確定として収載) | **逐語複製。言い換え・要約・語順の入れ替えを禁じる** (常設規律 4)。本書 §1.1 に全文を引いてある |
| **起草者疑義 6 点への監督裁定 (置き場・単位規範・対応表の編集主体とマージ順・`CREATE OR REPLACE VIEW`)** | **`{scratchpad}/rulings-q4-workorder.md`** | 本書は反映済み (v1.0、2026-09-05)。**該当箇所は「監督裁定 2026-09-05」と明記してある** |
| **fail-fast メッセージ (F-1〜F-11)** | **設計 `Q4_DB_SIDE_SINGLE_TRUTH_V1.md` §3.8** | 実装はここから複製する。**文字列ピンのテストを WP-1 / WP-2 の完了条件 12 に置く** |
| **cell open 時メッセージ (F-12)** | **同 §3.8 (F-12 の行と直後の注記)** | **起動時ではなく cell open 時であり API 応答に現れる唯一の項目**である。実装はここから複製し、**文字列ピンのテストを WP-3 / WP-4 の完了条件 11 に置く** |
| **F-13 (自 role が `audit_writer_roles` に含まれない)** | **同 §3.8 (F-13 の行と直前の注記)** | **監督裁定 2026-09-05 (D-2 (h)) による確定文であり、依頼者裁定ではない**。起動時の出力であり API 応答には現れない。**文字列ピンは WP-1 の完了条件 20 / WP-2 の追加条件 21 が課す** (条件 12 の対象へ F-13 を加える) |
| **F-3c (`surfaces` 行はあるが `control` が無く、それが control-plane プロセスである)** | **同 §3.8 (F-3c の行と「F-3c についての注記」)。原文は `{scratchpad}/q4-f3c-and-amendments.md`** | **監督確定文 2026-09-05。逐語複製し、言い換えない** (常設規律 4)。**`<registry>` は実 schema 名、`<peer>` は `r2db_api` / `mitatedb_api` に置換する。両 peer で同じ文面**。**文字列ピンの対象に加える** (WP-1 完了条件 31 / WP-2 追加条件 23) |
| **`ops declare-surfaces` の引数 (`--control-base-url` 任意 / `--no-control` は省略と等価の明示形 / 両方同時は使い方の誤り = 終了コード 2)** | **設計 D-2 (e) の直後の段落 (監督裁定訂正 2026-09-05)** | **必須の相互排他にはしない**。両 peer 同じ |
| **静的規則の規則文と期待集計** | 設計 §10 (規則) / §8.1 (命名規範) | WP-0 が改訂したスキャナの実測出力を §10 へ貼る |
| **SI-14 行の置換文言** | 設計 §3 D-6 の 1 | **限定 (「同一の platform データベースを前提に」) を落とさない** |
| **起動シーケンスと検査順** | 設計 §3.7 | data-plane 1〜8 / control-plane 1〜8 |
| **両 peer の対応表 (role 名・env 名・コマンド名・ファイル)** | 設計 §3.10 | peer を取り違えない (`app_slug` / `app_id` 等) |

**`{scratchpad}` は本フェーズの作業 scratchpad ディレクトリである。実装者への発注時に絶対パスを明示すること。**

---

## 10. 使用テンプレートの対応

| WP | 実装 | レビュー | 監査 |
|---|---|---|---|
| WP-0 | Sonnet テンプレ 2 (実装) | Opus テンプレ 5 (コードレビュー、変異注入必須) | Opus テンプレ 6 (受け入れ監査) |
| WP-1 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-2 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-3 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-4 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-5 | Opus テンプレ 4 (文書起草) | — | Opus テンプレ 6 |

テンプレートの本文は `~/.claude/.../memory/role-prompt-templates.md` が正本。**各発注時に、当該 WP の「レビューが必ず探すべき点」と「変異注入」の節をテンプレートへ差し込むこと。**

**subagent への発注時の規律**: 報告は短く上限を切り、**raw 出力は `{scratchpad}` のファイルへ**書かせる。長時間の suite は前景実行とし、`timeout` を明示する (600000 ms)。**完了ゲートの実測値は監督が自分で握る。** 並行 worktree で回す場合はローカル PostgreSQL の `max_connections = 300` を前提とする。

---

## 11. 実施記録

体裁はフェーズ6 作業指示書 §11 に従う。**集計行はすべて監督が完了ゲートで単独実行して得た実測値**であり、各 WP のコミットメッセージ末尾の `Root suite alone:` 行にも転記する。**実施記録の正本は設計 §13** であり、本節はその要約と監督裁定の一覧だけを置く。

### 11.1 集計行

| WP | 完了日 | 実装コミット | merge | root suite (passed / failed / skipped / xfailed) | conformance | 分割 |
|---|---|---|---|---|---|---|
| 基準値 | | | | | | |
| WP-0 | | | | | | |
| WP-1 | | | | | | |
| WP-2 | | | | | | |
| WP-3 | | | | | | |
| WP-4 | | | | | | |
| WP-5 | | | | | | |

### 11.2 WP ごとの記録

(空欄。WP ごとに、レビュー指摘の内訳・差し戻し回数・監督裁定・実バグの有無を記す。)

- **WP-0**: (空欄)
- **WP-1**: (空欄)
- **WP-2**: (空欄)
- **WP-3**: (空欄)
- **WP-4**: (空欄)
- **WP-5**: (空欄)

### 11.3 変異結果

(空欄。WP ごとに、対応表の変異番号・注入対象・観測された赤・復元の確認 (sha256 二重照合と変異文字列 grep) を記す。)

| WP | 変異番号 | 注入対象 | 観測された赤 | 復元確認 |
|---|---|---|---|---|
| | | | | |

### 11.4 受理境界

(空欄。完了条件のうち「一部未充足」「証拠不足」として受理した項目と、その理由・台帳への起票先を記す。)

| WP | 完了条件 | 判定 | 受理の理由 | 起票先 |
|---|---|---|---|---|
| | | | | |
