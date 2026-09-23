# 引き継ぎ — 2026-09-16 (2) (R-37 WP-4 の完了。WP-5 と公開値スキャナの許可追加は枠を確定済み。契約は 1.8.0 のまま)

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md` を読む。前書は `docs/work-orders/HANDOVER_20260916_FABLE.md`。

## 1. 現在地

- ローカルの main は `7cd1d80`。push は GitHub の請求上限のため停止中で (`OPERATING_CONDITIONS.md` §2 の 20)、ローカルの main だけを進めている。
- 最後の root gate は R-37 WP-4c の branch 上で `3451 passed, 2 subtests passed`、`judge=PASS`、実行クラスタの `pg_database` / `pg_roles` 差分 0。以後 main に入ったのは文書と、別セッションの参照用ファイル (`7cd1d80`) だけである。`tools/tests` は main で `492 passed`、`tools/check_doc_refs.py` は dangling 0。
- 本チャットはモデル呼び出し 300 回に達したので §1.10 の 67 に従って移る。**進行中のサブエージェントは無い。作業中の worktree も無い。**

## 2. 本チャットで閉じたもの

- **R-37 WP-4 (backend 内の SQL assembly 分離) が完了した。**記録は設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` v1.21 の §10.16〜§10.18、作業指示書 `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` v1.21 の §5.40〜§5.45 (訂正註 1〜8)、roadmap v1.49 の R-37 行。

  | WP | 対象 | merge | root gate |
  |---|---|---|---|
  | 4a | MitateDB BP3 → `mitatedb_api/postgres_sql.py` | `acb257e` (記録 `bec2eeb`) | `3422` |
  | 4b | r2db PG1 → 既存 `r2db_api/postgres_types.py` | `2e94bbf` (記録 `b6c78ab`) | `3425` |
  | 4c | r2db PG3 + PG2 + `_bind_value` → `r2db_api/postgres_sql.py` | `fdaf9e8` (記録 `2ed3a3d`) | `3451` |

  - **PG4 (`apply_schema` 内の DDL 組立) は実測で範囲外** (裁定 Z4-1。SQL の組立が 1〜2 行の単発で直後に同じ分岐の `_run()` と `LOCK TABLE` に地続き)。
  - **依頼者裁定 (逐語)「4c・4dをまとめてください。」**により旧 4c と旧 4d を 1 つの WP-4c にした (作業指示書 §5.45 の訂正註)。
- **R-44 WP-3 の開始プロンプトを出し、別セッションが WP-3 を統合した** (main `f051f99`、root `3439`)。本チャットの WP-4c のゲート期待値は、その基準に合わせて `3439 + 12 = 3451` に更新し、一致した。

## 3. 次の一手 (優先順)

1. **公開値スキャナの許可ホスト追加 (Class D、依頼者指示)。**枠は付録 A に逐語で置いた。**実装はまだ始めていない。**worktree を作り、実装担当 → 独立レビュー (狭さの実測を主眼) → root gate (`conformance_required=true`) → 統合、の順。設計 `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` D-2 への【追記】は監督が書く。
2. **R-37 WP-5 (facade 縮小と閉止)。R-37 の最後の WP。**枠は付録 B に逐語で置いた (裁定 Z5-1〜Z5-8)。**manifest はまだ無い。**作業指示書 §5.46 以降として manifest を起草し、独立設計レビューを 1 回掛けてから実装に入る。
3. **R-44 WP-4 (規律・文書・CI の正式改訂) を引き取る。依頼者指示 (逐語)「-37 WP-4 を終えてから R-44 WP-4（文書の正式改訂）を引き取ってください。」**R-37 WP-4 は完了したので着手可能だが、依頼者の指示の順は R-37 の後であり、本書は WP-5 の後に置く (WP-5 を先に閉じるほうが R-37 の閉止記録が一度で済む)。前提は別セッションの引き継ぎ書 `docs/work-orders/HANDOVER_20260916_R44_FABLE.md`、設計メモ `docs/design/TEST_POSTGRES_ISOLATION_V0_1.md` v0.3 §10、作業指示書 `docs/work-orders/WORK_ORDER_R44_TEST_PG_ISOLATION_V1.md` §4.1〜§4.5。**設計 §7 の完了条件のうち WP-4 に残るのは 3 (起動の形 5 種の確認と記録) と 4 (`pytest tools/tests` がクラスタを起動しないことの記録)。**積み残し 2 件 (nginx の bind 再試行が掛かっていない 4 経路、`tools/testpg/dsa_testpg.py` の external 分岐が `PGHOST` を要求しない) が作業指示書 §4.1 にある。**後者は「CI で露見するだけでは足りない、手元で黙るのが問題」という前提で扱う。**
4. 前書 `docs/work-orders/HANDOVER_20260916_FABLE.md` §3 の 2・3 (R-22 の次、R-39) は変わらず未着手。

## 4. 依頼者判断待ち

無し。前書 §4 から変更なし。

## 5. 並行セッションとの調整

- **R-44 の別セッションは WP-3 を統合して終わった**。R-44 WP-4 は付録ではなく §3 の 3 のとおり本系列が引き取る。
- **別セッション (Mitate リポジトリ側) が `7cd1d80` を main へ直接コミットした** — `MitateDB-api/docs/f9-execution-assets-v1/` に v1.x の F9 実行資産 11 件 (Python 3 件・shell・Dockerfile・README・SHA256SUMS)。**参照用で、ビルド・CI・テスト・配備に接続されておらず、本リポジトリの手順でレビューされていない。**`finalize.py` を経ていない (親 1 の直接コミットで、§1.1 の 4 の `--no-ff` の形でもない)。監督が後から検査した結果: `tools/tests` 492 passed、doc-refs dangling 0、**公開値スキャンが 2 件を検出** → 付録 A。
- **R-44 WP-2 以降、gate の排他は道具が自動で取る。**`--hold` と `GATE_HOLD_FLAG` と `ps` による他 pytest の検出は廃止された。`--wait` は「監督のゲートが持つ排他ロックが解けるまで待つ」の意味。gate の出力は 4 行で、**3 行目 (gate 自身の使い捨てクラスタの差分) が判定、4 行目 (`info=shared`) は情報**。

## 6. 本チャットで足した運用上の教訓

- **`gate.py` に `-C <worktree>` を必ず渡す。**既定はカレントなので、渡し忘れると main を測って `judge=PASS` を出す (別セッションが実際に踏んだ)。**ゲートの集計行が「直前の main の集計行 + その WP の新規テスト数」で内訳つきに説明できるかを確かめてから受け取る。差分を説明できないゲートは、測れていないゲートである。**
- **記録を要する証拠は監督が取る** (裁定 W4-4)。`finalize.py --no-merge` で WP branch に記録してから、その HEAD で `tools/tests` を回して 0f の来歴証拠を取り、緑を確かめてから main へ `--no-ff` で統合する。**使い捨て clone は使わない。**
- **0f は src を記録済みのツリーから、companion (`docs/code-history/`) を作業ツリーから読む** (訂正註 7)。src 側の来歴の変異 (history ID の差し替え) は作業ツリーでは 0f に見えないので、**捨てコミットの上で回して赤を確認し `reset --hard` で戻す** (§1.4 の 30 の照合を行う)。companion 側の変異は作業ツリーのままで赤になる。
- **閉語彙外・例外経路の完了条件は assertion を足すだけでは満たせない** (訂正註 6)。WP-4a・4b・4c と **3 回続けて**、足したテストが同種の別形の変異 (`.get(op, default)`・`.get(op) or default`) を素通りした。**断言が及ぶ経路を実際に実行する。AST 固定はそれが難しい場合に限る。**実装担当はその変異を当てて赤になった実測を報告に添える。
- **訂正の記録の `old:` / `new:` はコメント記号を落とし折り返しを連結した 1 行で書く** (訂正註 2)。チェッカーは `_flatten` した本文に対して 1 件一致を要求する。書いた後に `--base` を走らせ §9f が 0 件であることを確かめる。**§4.1 の赤のうち (5) (追加行の経緯トークン) は位置ずれではない** (訂正註 8-1)。**§4.1 の赤をすべて位置ずれと読まない。**
- **読み手 0 の検査は scope-aware に数え、その module を facade として読む外部のファイル (テストを含む) まで見る** (訂正註 4・8-4)。**`ast.Name` の数え上げは文字列注釈を見ないので偽陰性になりうる** (WP-5 の実測。付録 B の Z5-5)。
- **新規ファイルを足す WP では、走査の列挙方法を実測する** (訂正註 8-7)。`rglob` / `glob` 系は未追跡も見る (「コードの依存」を見る検査)、`git ls-files` 系は追跡されるまで見ない (「公開されるもの」を見る検査)。**`tools/tests` は root suite の `testpaths` の外なので `gate.py` では走らない。**
- **実装担当に `conformance-tests` を回させない。**約 9 分で前景 1 回に収まると明示しても、WP-4a・4b で 3 回続けて背景実行して待機状態で止まった。WP-4c からは実装担当に peer 別 suite と `tools/tests` だけを任せ、全体は監督の root gate が覆う形にし、止まらなくなった。

---

## 付録 A. 公開値スキャナの許可ホスト追加の枠 (監督が確定。逐語)

### 依頼者裁定 (逐語。§1.7 の 51 のとおり再審議しない)

> スキャナの除外リストに理由付きで足してください。

経緯: 別セッションのコミット `7cd1d80` が `finalize.py` を経ずに main へ入り、監督が後から走らせた `tools/public_value_scan.py` が 2 件を検出した。監督が「どちらも Google の公開インフラの定数で秘密ではない」と判断し、(1) 除外リストへ理由付きで足す / (2) このまま受け入れる、の 2 案を示したことへの回答である。

### 変更クラス

**Class D。**`tools/change_class.py` が `tools/public_value_scan.py` を `class=D conformance_required=true` と判定する (監督実測)。スキャナは公開リポジトリの規律 (`CLAUDE.md` の Public Repository Security Gate、`docs/security/public-repository-policy.md`) を実行する境界である。契約 (`spec/`)・不変条件 (`security/`) は変えない。

### 検出された 2 件 (監督実測。**具体のホスト名は本書に書かない** — 書くと許可を足すまで本書自体が検出される。対象ファイルを直接読むこと)

| ファイル:行 | 規則 | 中身 |
|---|---|---|
| `MitateDB-api/docs/f9-execution-assets-v1/Dockerfile`:3 | R2_fqdn | `FROM` 行のイメージ名の中にある **GCR 上の名前空間** (Google の企業ドメインの裸 FQDN)。Google が公開する Cloud SDK の公式ベースイメージである。**レジストリのホスト自体は既に許可済み**で、引っかかったのはパス中の名前空間のほう |
| `MitateDB-api/docs/f9-execution-assets-v1/f9-revision-proxy.py`:22 | R2_url | **GCE メタデータサーバーの標準エンドポイントのホスト**。全 GCP VM で共通の、文書化された固定 URL。audience の値は変数から連結され、ファイルに埋め込まれていない |

### 監督裁定

| # | 裁定 | 根拠 |
|---|---|---|
| S-1 | **2 件とも `R2_ALLOW_HOST_EXACT` (完全一致) に足す。`R2_ALLOW_HOST_SUFFIXES` (サフィックス一致) には足さない** | サフィックス許可は、企業ドメインのサブドメイン形や、メタデータサーバーのホストに接頭・接尾ラベルを足した形を将来黙って通す余地を作る。**許可を緩める変更は、狭さを実測で示せる形に限る。**`R2_ALLOW_HOST_EXACT` は R2_url と R2_fqdn の両方で、deny suffix の後・generic allow の前に参照される (`tools/public_value_scan.py`:306・369) |
| S-2 | **各エントリに理由のコメントを付ける。**既存の `sqlite.org` と `gcr.io` の行 (`tools/public_value_scan.py`:248-249) が書式の前例。理由には「何の公開定数か」「プロジェクト固有の値を含まないこと」「完全一致に限る理由」を書く | 依頼者の指示「理由付きで」 |
| S-3 | **設計 `docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` の D-2 の許可表 (L147) は本文を書き換えず、日付付きの【追記】で 2 件の追加と理由を記録する** (§1.8 の 56・57)。**【追記】にも具体のホスト名を書くかは、許可を足した後なら書けるので実装の後に書く** | D-2 が許可リストの正本。コードだけを変えると設計と乖離する |
| S-4 | **狭さを実測で示す** (同設計 L7-4 の趣旨)。次の探針を**一時ファイルにのみ**置いて実測し、復元する。**探針の具体値は設計・作業指示書・コミットのいずれにも書かない** (同設計 L172 の規律)。(a) 許可したい 2 件が**許可される**、(b) 企業ドメインの**サブドメイン形**が **flag される**、(c) メタデータサーバーのホストに**接頭ラベルを足した形**と**接尾ラベルを足した形**がいずれも **flag される**、(d) deny suffix (`run.app` / `cloudfunctions.net` / `gserviceaccount.com`) の判定が**変わらない** | 完全一致に限ったことを、主張ではなく実測で示す |
| S-5 | **ツリー全体の走査で flagged 0 件**に戻ることを確かめる (`python3 tools/public_value_scan.py` のツリーモード)。**集計行は pipe の終了コードで読まない** — ファイルへ落として `total_flagged=` を読む。`--history` は走らせなくてよい | 現在は 2 件、変更後は 0 件のはず |

### 触ってよいファイル

`tools/public_value_scan.py` (許可エントリ 2 行とそのコメントのみ)、`docs/design/PHASE7_EVIDENCE_REPRODUCIBILITY_AND_PUBLICATION_V1.md` (D-2 への【追記】のみ。監督が書く)

### 触らないファイル

`MitateDB-api/docs/f9-execution-assets-v1/` (別セッションの成果物。値を placeholder に置き換える案は依頼者が選ばなかった)、`CLAUDE.md`、`docs/security/public-repository-policy.md`、`spec/`、`security/`、`conformance-tests/`、両 peer の `src/`・`tests/`、`.pre-commit-config.yaml`

---

## 付録 B. R-37 WP-5 (facade 縮小と閉止) の枠 (監督が確定。逐語)

正本設計: `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §1.1・§1.2・§3.2・**§4 の WP-5 節**・§5・§6・§7。規律: 作業指示書 `docs/work-orders/WORK_ORDER_R37_WP0_INVENTORY_V1.md` §5.45 の**訂正註 1〜8 すべて**。

### 問題設定と守るべき条件

設計 §4 の WP-5 は R-37 の**最後の WP** であり、「各 WP の import graph、残る facade、dead private symbol、テストの重複を確認する。export を消す、path を public にする、同型性対象を減らす、テストを削除する場合は個別に根拠と回帰証拠を添え、通常の変更クラス判定を再実施する。**line count は成果指標ではなく、責務・依存方向・回帰証拠が閉止条件である。**」と定める。公開意味と Security Invariants の安全結果を変えない。

### 実測 (main `2ed3a3d`。Sonnet の explorer が取り、決定的な点は監督が再照合した)

- **A. 読み手 0 の棚卸し** (scope-aware な AST 走査、両 peer 全 87 module): module 内部で読み手 0 の import / 定数は多数あるが、**大半は外部テストの facade identity test (`assert X is leaf_X`) が能動的に読む**。module 内・外部とも真に読み手 0 で facade 明記コメントも無いのは **2 件だけ**: `MitateDB-api/src/mitatedb_api/backend_postgres.py`:95 の `CONTRACT_TYPES` と `MitateDB-api/src/mitatedb_api/config.py`:8 の `build_surfaces` (監督が再照合: `CONTRACT_TYPES` の他の出現はすべて docstring 内の修飾名 `field_types.CONTRACT_TYPES`、`build_surfaces` を使う `control_composition.py` と `capabilities_document.py` はどちらも `.surfaces` から直接 import しており `config` 経由ではない)。`_RESERVED_EXACT`/`_RESERVED_PREFIX` (`backend_postgres.py`:100) は `MitateDB-api/tests/test_postgres.py`:1666-1670 の identity test が読む。`_INT_DOMAIN_RANGES`/`_check_domain` (`backend_postgres.py`:96-97) は「re-exported for facade compatibility」と明記がある。**手法の既知の限界**: 文字列注釈は `ast.Name` に現れず偽陰性になる (該当: `MitateDB-api/src/mitatedb_api/http.py`:17・486、`audit_query.py`:32・228・280・391)。
- **B. SQL 安全性**: `psycopg.sql` を import する module は r2db 8・MitateDB 13。両 peer の choke point (`r2db-api/src/r2db_api/postgres.py`:225 `_run`、`MitateDB-api/src/mitatedb_api/backend_postgres.py`:242 `_execute`) はどちらも `isinstance(statement, (sql.SQL, sql.Composed))` の**実行時ガード**を持つ。**repo 横断の静的走査は両 peer 0 件。**`MitateDB-api/tests/test_order_by_direction_hardening.py` は SQLiteBackend だけを見る。**src に f-string で SQL 片を組む箇所は 0 件** (監督実測。キーワードに当たる 5 件はいずれも SQL ではない)。
- **C. 委譲属性**: `staticmethod` 委譲は r2db `postgres.py` 7・MitateDB `backend_postgres.py` 1・`cell.py` 3。
- **D. テストの重複**: 候補 1 件 (`_escape_like_literal` を `r2db-api/tests/test_postgres.py`:1193-1198 と `r2db-api/tests/test_foundation.py`:3631-3645 が部分的に重ねて固定)。全数比較は未実施。
- **E. import graph**: leaf 登録 r2db 18・MitateDB 12 (計 30)、非 leaf r2db 23・MitateDB 34。**循環 import を検知する静的テストは存在しない。**
- **F. `COLLECTION_FLOOR`**: 現在値 3326、WP-4 完了時の root gate 3451。下限チェックのみ。**node-id 一覧の前後 diff を取る道具は存在せず、削除の検出は手作業のみ。**

### 監督裁定

| # | 裁定 | 根拠 |
|---|---|---|
| Z5-1 | **WP-5 の範囲は次の 6 つ。**(1) **SQL 安全性の静的走査の新設** (設計 D-4 が要求し、W4-3 が WP-5 へ送ったもの)、(2) **循環 import の静的検査の新設**、(3) **真に読み手 0 の import 2 件の削除**、(4) **残る再 export を「意図的な facade 互換」として記録**、(5) **読み手検査の偽陰性 (文字列注釈) の手当て**、(6) **R-37 の閉止記録** | (1) は設計 D-4 の「client-influenced statement が plain `str` で到達できない性質を新 module を含む走査で確認する」に対応する機構が 0 件。(2) は設計 §4 WP-5 の「import graph を確認する」の機械化された形で、現在は静的テストが無い |
| Z5-2 | **テストの削除は行わない。**重複候補 1 件は **R-39 候補として記録** | 設計 §5.3 は `COLLECTION_FLOOR` が「大幅な収集減の検知器であって、テストを削除していない証明ではない」と述べ、実測では削除を検出する道具が無い。**削除の根拠より、削除を検出する手段が無いことのほうが重い** |
| Z5-3 | **SQL 安全性の走査は SQL キーワードの文字列一致で作らない。**AST で「execute の choke point に到達する値がどう構築されたか」を見る形にする | 監督実測: キーワード一致だと `r2db-api/src/r2db_api/delete_confirmation.py`:127・138・163・243 の削除確認の句 (利用者が打ち込む文字列で SQL ではない) と `MitateDB-api/src/mitatedb_api/ops.py`:798 のエラーメッセージが偽陽性になる |
| Z5-4 | **削除する読み手 0 の import は 2 件だけ** (`CONTRACT_TYPES`、`config.py` の `build_surfaces`)。**他の候補は削らない** | 上の A の再照合。facade identity test が読むもの・facade 明記があるものは削れない |
| Z5-5 | **読み手検査 (訂正註 4) の偽陰性を手当てする。**文字列注釈を扱うか、扱えないことを明記して手作業の照合を完了条件にする | WP-4 が確立した検査手法そのものの穴であり、WP-5 の削除判断がこの手法に依存する |
| Z5-6 | **Class B。**`_ISOMORPHIC_TARGETS` に触れない (差分 0 を完了条件にする)。`spec/`・`security/`・`conformance-tests/` に触れない | 削除は peer の private な import 2 件、新設は `tools/tests/` のテスト |
| Z5-7 | **1 つの WP として行う** (依頼者の統合の方針に沿う)。**完了条件は (1)〜(6) ごとに分ける** | 依頼者裁定「4c・4dをまとめてください。」の方針。規模は WP-4c より小さい |
| Z5-8 | **新設する 2 つの走査は走査対象を両 peer の `src/` に明示的に限る。**peer のディレクトリ全体を `rglob` しない | `7cd1d80` が `MitateDB-api/docs/f9-execution-assets-v1/` に `.py` 3 件を置いた。レビューされていない参照用コードで、`MitateDB-api/` を `rglob` すると判定に混ざる |

### 却下した代替案

- テストの重複を削る (Z5-2)。
- SQL 走査をキーワード一致で作る (Z5-3)。
- 読み手 0 の候補をすべて削る (Z5-4。大半は facade identity test が読み、削ると赤になる)。

### 独立設計レビューで見てもらう点

**(2) の循環 import 検査が、設計 §4 の「import graph を確認する」の範囲に収まるか** (§1.5 の 37 の設計外の拡張に当たらないか)。監督の見立ては「範囲内」 — 一度きりの手作業の確認は変異を対応付けられず (§1.5 の 33)、閉止条件の「依存方向」を持続的に保てるのはテストの形だけであるため。

---

## 付録 C. 追加の依頼 — MitateDB の platform upgrade (Mitate F9 の阻害要因) の起票と、読み取り専用の運用経路の設計 (2026-09-16、本書の統合後に受領)

**受領の経路**: 依頼者の依頼を、Mitate の監督セッションが本チャットへ中継した。本チャットはモデル呼び出しの上限を超えて引き継ぎ済みだったので、§1.10 の 67 に従い**着手せず、本付録に記録して次のチャットへ渡す。**

### 順序 (依頼の指定)

- **現在の R-37 の WP を中断しない。**次の区切り (WP と WP の間) で起票と設計に着手する。
- **実装・テスト・runbook の変更は、R-37 が MitateDB-api のコードを動かし終えるまで始めない** (R-37 WP-5 は `MitateDB-api/src/mitatedb_api/backend_postgres.py` と `config.py` の import を削る)。
- **本書 §3 との関係 (監督の見立て。次のチャットが判断し直してよい)**: 起票 (下の 1) と設計 (下の 2) は文書だけなので、§3 の 1 (スキャナ) と 2 (WP-5) の区切りで着手できる。実装は WP-5 の統合後。

### 背景 (Mitate 側で確定済み。要約)

- Mitate F9: mitate-application は起動時に Data Service の capability `limits.operation_depth` が必要深さ以上であることを確かめ、満たさなければ起動を拒む。実装・受け入れ済み。
- 2026-09-13 の実環境確認で F9 は阻害された: 本番の MitateDB Data は運用変数で深さ 13 を設定しているが、稼働中の image が古く、認証済み `GET /v1/capabilities` が `limits.operation_depth` を返さない。F9 を含む mitate-application の revision は起動ゲートで拒否され、traffic は旧 revision のまま。**現行の Data / Control のテンプレートは旧式の base URL 設定 (`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`) を持ち、Mitate の互換条件 (Gate-0) を満たさない。**
- **Mitate 側の正本 (読み取り専用。Mitate は Decision・設計・作業指示書・引き継ぎ書だけを持ち、SQL・Cloud Run 手順・運用資産・実装・テストは data-service-api が持つ)**: `../Mitate/decisions/DM-0052-data-service-platform-upgrade-for-operation-depth.json`、`../Mitate/docs/design/data-service-operation-depth-platform-upgrade.md` v1.2、`../Mitate/docs/work-orders/data-service-operation-depth-platform-upgrade.md` v1.2 (WP-1 は 2026-09-14 に「blocked — platform remediation required」)、F9 検証側 `../Mitate/docs/design/f9-data-service-production-validation.md` v2.1 と `../Mitate/decisions/DM-0051-f9-candidate-validation-transport.json`。
- **WP-1 が止まった理由 = Gate-0 の本当の阻害要因**: DSN・credential・token を一切出力せずに次の状態を読める運用経路が無い — (1) isolated / production の組、(2) platform declarations、(3) migration とアプリケーションごとの upgrade 状態、(4) credential registry の参照、(5) rollback の可逆性、(6) DDL のロックと停止時間の上限。**不明の状態は阻害として扱う。**

### 未コミットの起票物 (片付けが要る)

- worktree `.claude/worktrees/mitatedb-operation-depth-platform-plan` (branch `codex/mitatedb-operation-depth-platform-plan`、2026-09-14) に未コミットの変更 2 件がある (監督が 2026-09-16 に `git status` で実在を確認)。
  - `docs/design/ROADMAP_POST_PHASE7_V1.md` の差分 (台帳行を v1.14 として足すもの)
  - 新規 `docs/work-orders/WORK_ORDER_MITATEDB_OPERATION_DEPTH_PLATFORM_UPGRADE_V1.md` (Class D。手順 1 が読み取り専用の経路での状態確認)
- **その起票は台帳番号 R-37 を使っているが、main では R-37 はモジュール分割のリファクタに使われ、台帳は v1.49。番号が衝突しているので、そのままコミットしない。**
- **監督の実測 (2026-09-16、main `9494451`)**: 台帳 §8 の最大番号は **R-44**。空き番号は **最大番号の次の番号の見込み** (台帳にまだ行が無いので本書では番号を名指ししない — 書くと `tools/check_doc_refs.py` が未定義の参照として止める。着手時に取り直すこと)。
- **依頼**: 起票物を読み、空き番号を割り当て、現在の main の台帳 (v1.49 以降) へ当て直す。**worktree の差分は取り込んだ後に自分の方法で片付ける (取り込む前に消さない)。**

### やること (順)

1. **起票物を新しい台帳番号で main へ入れる** (本リポジトリの commit / merge の規約どおり)。
2. **読み取り専用の運用経路の設計を書く。**
   - 材料: `MitateDB-api/src/mitatedb_api/ops.py` の `show-declarations` / `verify-declarations` / `upgrade-status` サブコマンド、`MitateDB-api/docs/cloud-run-cloud-sql.md`、`MitateDB-api/migrations/0007` / `0011` / `0012`、`conformance-tests/test_c05_limit_declaration_agreement.py`。
   - 欠けているもの: 上の 6 状態を **DSN・credential・token を一切出力せずに**読み、**不明の状態を fail-closed で blocked と報告する**経路。
   - **R-37 が MitateDB-api のコードを動かしているので、既存コードは行番号ではなくファイル名と関数名または CLI サブコマンド名で引き、基点コミットを記録する。**
3. **後続の WP は本リポジトリの設計・レビューの手順を経てから**: isolation で同じ候補 digest を使い `operation_depth=13` の公開・13 の受理・14 の拒否を証明する → 本番 Data / Control の更新 → 独立監査。

### 制約 (依頼の指定。いずれも厳守)

- **本番を変えない**: migration、declaration、restart、candidate、traffic、Job、bridge、probe、fixture、promotion をしない。secret の rotate / revoke / delete をしない。Cloud SQL のリソースを消さない。**credential の値を決して出力しない経路が設計とレビューで受け入れられるまでは、読むことさえしない。**
- **DSN・credential・token・credential を含む URL を、出力・ログ・文書・コミットのどこにも置かない** (`CLAUDE.md` の Public Repository Security Gate)。
- **共通の Data Service API の spec、Mitate の契約、mitate-application の F9 ゲートを変えない。**
- `MitateDB-api/docs/f9-execution-assets-v1/` (`7cd1d80`) は**参照用に限り、証拠として使わない** (同ディレクトリの README)。
- **依頼者が言うまで push しない。**
- **変更クラスは D の見込み。最終判定は `RM` §9 の 8 の表で行う。**

### 依頼者への報告事項 (Mitate の監督が Mitate の引き継ぎ書に記録する)

- 新しく割り当てた台帳番号と、起票物を取り込んだコミット。
- 読み取り専用の経路の設計の所在と状態 (レビュー前 / 後)。
- 経路が使えるようになったら、**DM-0052 Gate-0 の各項目** (上の 6 状態 + 旧式の base URL 設定の有無) を **confirmed / blocked / unknown** で。Mitate はこれで F9 Gate-0 を判定し直す。
