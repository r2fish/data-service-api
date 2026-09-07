# フェーズ7 実施設計: 証拠・再現性・公開準備 (契約 1.6.0 不変)

- 版数: **v1.3 (2026-09-07)** — **フェーズ8 の状態注記のみ**である。§11 の L7-1 / L7-18 / L7-19 / L7-21 / L7-22 / L7-23 に【状態注記 2026-09-07 (フェーズ8)】を、D-6.2 の `operation_depth` 行に訂正註を足した。**決定・裁定・実施記録の本文は 1 文字も変えていない。**
- 旧 **v1.2 (2026-09-05、依頼者裁定 (α)(β)(γ) 確定 + 7-A 前倒し確定)** — **§5 の依頼者裁定は 1 文字も変えていない。** v1.1 からの変更点: **(1)** **§6 を「未確定」から「依頼者裁定 (2026-09-05 確定)」へ改め**、裁定文を逐語で置き、(α)(β)(γ) の各項に確定内容を付した (**両論は経緯として残す**)。**(2)** **(α) 確定**に伴い、**D-3 の Python matrix を「3.11 と 3.12 の両方を required、完了ゲートの正本は 3.11 job の集計行 (3.12 job は同一集計行であることを required で担保)」**へ改め、L7-6 の射程を狭めた。**(3)** **(β) 確定**に伴い、**MitateDB の欠落 4 class への明示エントリ追加を WP-4 同梱**として確定扱いにした (§10)。**(4)** **(γ) 確定 (案 1)** に伴い、**D-1 (iv) の (4)(5)**、**§9 の手順表** (手順 3 = 同名リポジトリの delete + 書換後履歴のみ push + 再作成、手順 4 の取得元 = 再作成後の remote)、**§10 WP-9 の着手条件**、**L7-13 (閉じた)** を確定形へ改めた。**(5)** **7-A (WP-1 / WP-2 / WP-3) の前倒し着手の確定**を §12 と §10 に記した
- 旧 **v1.1 (2026-09-05、設計レビュー 1 回目の指摘 20 件を全件反映。§6 に (γ) 新設。監督が V3 の xfail 件数を 6/8 → 7/9 に訂正 — MitateDB in-process の `request_bytes: unavailable` を静的 parametrize が拾うため。L7-1 に副項目を追加)** — **§5 の依頼者裁定は 1 文字も変えていない。** v1.0 からの変更点: **(1)** D-2 の変異から合成リテラル 2 件を削除し、「許可リスト外の合成 FQDN 1 件と合成 e-mail 1 件を**実装担当が生成して一時ファイルにのみ置く**」へ改めた (書いたままでは WP-1 のスキャナ導入と同時に**本書自身が R1 / R2_fqdn で赤になる**)。**(2)** **D-6.2 を 4 列** (class / 契約上の意味 / 両 peer で同時成立する駆動レシピ / 検査の形) **へ格上げ**し、`query_complexity` / `request_bytes` / `result_items` の 3 class を**片側検査**へ落とした (metric の合成・計測方式が peer 間で異なり、共通の 1 レシピでは N / N+1 の位置が一致しない)。**(3)** V2 の**駆動集合の導出規則を明文化**した — 「(その plug が叩く surface で `enforced`) ∩ (D-6.2 で検査形を持つ class)」とし、差集合 (r2db の `concurrency`) と理由を C-05 行に開示する。**(4)** **公開ゲートに force push (全 branch・tag) と、remote から取り直した新規 clone に対する履歴スキャン**を挿入し (D-1 (iv) / §9)、**GitHub 側に残る unreachable object への対処を §6 (γ) として両論で新設**した (監督案 = 案 1、確定はしない)。**(5)** filter-repo の前に**すべての linked worktree を畳む**手順を §9 の先頭に置いた。**(6)** スキャナの placeholder 除外を「トークン全体を除外」から「**placeholder 部分文字列を除去してから再判定**」へ改めた (前置による実値の隠蔽を塞ぐ)。**(7)** CI の PostgreSQL を `services:` から**専用 step の `docker run`** へ改め (`services:` に `command:` キーは無い)、DSN 既定値が unix socket であるため CI では loopback TCP への上書きが必須である旨を明記した。**(8)** V2 に **`_MAX_EXERCISABLE_LIMIT` 相当の上限 assert と `requests_per_minute` 窓の headroom 前提**を置いた (C-14:476 / :490-511 と同型)。**(9)** `isolated_application_surface()` が返すものを単一 callable から**port 準拠の adapter instance** (小さな profile の新 service に束縛した同型の adapter) へ改めた。**(10)** C-10 の応答走査を port 追加ではなく **conftest 側の generic proxy** に置き、「wire 水準」の語を「**adapter 境界水準**」へ改めた (port 追加項は 2 のまま)。**(11)** V1 (e) が**契約の義務ではなく共通 suite の追加要件**であることを明記し、V1 (c) の対象を **`enforced` と `reference_wall_clock` のみ**へ限定した (`deployment_required` は `limits` 側の制約を置かない)。**(12)** V1 (e) の適用面を **application plane のみ**とし control plane の必須集合を C-14 の 4 class に置き、**V3 を固定 9 の静的 parametrize** へ改め、C-07 の全体 guard と V2 の空振り防止を **per-plug 非空性 assert** (C-17:182-218 と同型) へ改めた。**(13)** `details.limit_class` 必須の根拠を自前の論から**契約 `errors.details_vocabulary` (required、1.2.0 義務)** へ差し替え、C-14 の stale 注釈と L6-19 の訂正を WP-4 に載せた。**(14)** D-6.5「Q4 確定後の追補」の記入を WP-8 から **WP-4 の着手条件**へ移した。**(15)** `httpx2` は**提供元が Starlette / encode 系であることの確認**を完了条件とし、確認できなければ ASGITransport 経路へ切り替えると明記した。**(16)** D-7 の長さ上限を**主表の各セル**に掛けると明記し、目安を 1,500 から **2,500** へ改め (履歴ゼロの C-17 Condition 列が 1,788 文字)、register テストに **ID 重複禁止 assert** を足した。**(17)** `CONDITIONS.md` の更新規約は**表の外の前文に散文で**置くと明記した (parser の単一表前提を壊さないため)。**(18)** companion の見出しを **ID のみ**とし、anchor の解決を register テストで検査すると明記した。**(19)** 「43 ファイル中」の**母数の出所**を明記した。**(20)** §12 に「前倒しした 7-A の worktree も WP-9 の手順 1 の前に畳む」を足した
- 旧 v1.0 (2026-09-05、監督裁定 S-1〜S-6 反映) — 初版起草後・設計レビュー前に、起草者の疑義 3 件と事実確認に対する監督裁定 S-1〜S-6 (D-6 V1 規則の確定形と V2 probe 対象の限定 / 必須エントリ集合の「固定 9 + capability 条件付き 3」化 / D-1 (iii) の凡例訂正 / C-07 の形と port 追加項の限定 / CI matrix と runbook の事実確認 / Status 同一コミット規律) を反映した訂正であり、初版の版数を維持した
- 位置づけ: **監督が確定した枠 (2026-09-05) の実施設計**である。§3 の D-1〜D-7 は監督裁定を受けた確定であり、§5 の依頼者裁定 1〜4 は逐語で記録して**再審議しない**。**§6 の (α)(β)(γ) も 2026-09-05 の依頼者裁定で確定した** — **本設計に未確定事項は無い**。WP 分割は §10 に素案のみを置き、作業指示書 (`docs/work-orders/WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md`) は別途起こす。構成・粒度・文体はフェーズ6 設計文書 (`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md`) を踏襲する
- テーマ: **「第三者が同じ集計行を再現でき、公開しても安全で、現行の担保を短時間で読み取れる」状態にすること**
- 出所: `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 **L6-20 の (a)(b)(g)(h)(i)** を本フェーズの実施対象とし、**(c)(d)(e)** については採否を本設計で決める。**(f) は Q4 フェーズへ移管済みであり本フェーズの範囲外**である (依頼者裁定 2026-09-05)
- **契約は不変である**。本フェーズは `spec/data-service-api.v1.json` を 1 バイトも変えない。`limit_enforcement` の値語彙 (`enforced` / `reference_wall_clock` / `deployment_required` / `unavailable`) と `limits.classes` の 16 語 (契約 :254) は**既存のまま使う**
- 依存: **Q4 フェーズ設計** `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` (main の **v1.2**、merge `1722a8c`。U-1〜U-3 は 2026-09-05 に依頼者裁定で確定 — U-1 = 契約に載せない (peer-local)、U-2 = 台帳表に runtime role の `SELECT` のみ、U-3 = 起動時スナップショット。契約 1.6.0 無変更・conformance の vector / port 無変更。本設計の起草時点は v1.1 だったが、v1.2 は本設計の前提 (wire 不変・limit class は Q4 対象外) を変えない)。本設計の **7-B の各 WP は「着手条件: Q4 の main マージ後」**である (§10)
- 体制・規律: 既存フェーズと同一である。Fable 監督/設計/コミット、Opus 起草/独立レビュー/受け入れ監査、Sonnet 実装 (コミットしない)。常設規律 7 項目 (`docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md` §0.1) を継承する
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。既定の重み付けは「最小変更」ではなく「長期に正しい形」。利用者は AI エージェントである (宣言は確実に読まれる)
- **公開規律**: 本書には実値を一切書かない — 実ホスト名・cloud project 識別子・実 e-mail・実 credential_id・作業機の絶対パス・IAM principal を含まない。合成値は `<UPPER_SNAKE>` 形の placeholder と `*.example.invalid` のみを使う。**実値の対応表はリポジトリ外の運用者記録にあり、本書はその存在だけを書く**

---

## 1. 問題設定

外部評価 第 2 回 (2026-09-05) と第 1 回の残件が示すのは、**契約と実装は揃ったが、「第三者が同じ集計行を再現でき、公開しても安全で、現行の担保を短時間で読み取れる」状態にはない**、ということである。具体的には次の 5 点である。

### 1.1 共通 suite に載っていない 6 条件 — 両 peer の同一性が固定されていない

`conformance-tests/CONDITIONS.md` の **C-00 / C-02 / C-04 / C-05 / C-07 / C-10** は 6 行とも `not yet executable (common suite) -- peer-local evidence only` のままである (同ファイル :8 / :10 / :12 / :13 / :15 / :18)。peer-local テストは両 peer それぞれに存在するが、**共通 suite が両 peer の同一性を固定していない**。

特に **C-05 (SI-08 の有限・発見可能な境界)** は非対称が実体として残っている。

- **r2db**: `r2db-api/src/r2db_api/service.py:936-937` が `ResourceLimits.as_dict()` の全 class を `limits` に出し、`limit_enforcement` を `execution_ms` のみ `reference_wall_clock`、他は `enforced` として機械的に導出する。`ResourceLimits` (`r2db-api/src/r2db_api/limits.py:11-20`) が持つのは **9 class** — `request_bytes` / `batch_items` / `result_items` / `query_complexity` / `execution_ms` / `concurrency` / `requests_per_minute` / `schema_objects` / `operation_depth` である。
- **MitateDB**: `MitateDB-api/src/mitatedb_api/cell.py:1481-1504` が `limits` に **6 class** (`batch_items` / `batch_entities` / `result_items` / `query_complexity` / `request_bytes` / `schema_objects`) を出し、`limit_enforcement` は `request_bytes` のみ `unavailable` (`:1502`)、他 5 つを `enforced` とする。**`execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` の 4 class は宣言そのものが無い** — 「未実装」が「宣言が存在しない」という形で表れており、**クライアントからは「実装していない」と「宣言し忘れた」を区別できない**。
- 逆向きの非対称も 1 点ある: **`batch_entities` は MitateDB だけが宣言する**。MitateDB は `cross_entity_mutation: partial` (`cell.py:1468`)、r2db は同 capability を `unavailable` (`service.py:930`) と宣言しており、**class の適用有無が capability 宣言に従属している**。この従属関係が D-6.1 の必須エントリ集合を「固定 9 + capability 条件付き 3」に分ける根拠である。
- HTTP 面ではさらに 1 点だけ上書きがある: `MitateDB-api/src/mitatedb_api/http.py:577` が `request_bytes` の enforcement だけを `enforced` へ差し替える (R-7: 実際に measure/enforce するのはこの HTTP 合成であり、`cell.py` は backend 非依存の宣言内容の単一の真実であるという既決の分担)。**その帰結として、MitateDB の in-process 面では `request_bytes` が「`limits` に有限値を持ちながら `limit_enforcement` は `unavailable`」という状態で公開されている** (`cell.py:1491` の値と `:1502` の `unavailable`)。これは矛盾ではなく「**値は公開するが、この surface には enforcement 層が無い**」という正直な宣言であり、D-6.1 の V1 規則はこの形を許すように書かれている。

`CONDITIONS.md` C-05 行自身が、この状態を honest-scope 注記として既に開示している — 「no common-suite test cross-checks, adapter-independently, that a peer's declared `limit_enforcement` status per resource class agrees with what a request actually experiences at that peer's own advertised bound」。最も近い既存の共通被覆である **C-14 vector 5** (`conformance-tests/test_c14_authority_boundary.py:436-674`) は **control plane 専用**であり、`control_plane: enabled` の peer にしか届かない。

### 1.2 依存は下限 pin のみ — lock も CI も無い

- 両 peer の `pyproject.toml` は `starlette>=1.0` / `psycopg[binary]>=3.1` / `uvicorn>=0.30` の**下限 pin のみ**であり、`[test]` extras も `pytest` / `httpx>=0.28` / `anyio>=4.0` / `pytest-xdist>=3.6` の下限 pin である。root `pyproject.toml` は `[project]` 節を持たない (4 行、`[tool.pytest.ini_options]` のみ) ので、そこに依存を宣言する構造が無い。
- **lock / constraints ファイルはリポジトリ全体に存在しない**。`.github/` ディレクトリも存在しない。`Makefile` / `tox.ini` / `noxfile.py` も無い。
- `filterwarnings` / `addopts` は root `pyproject.toml` に無い。
- venv の Starlette 1.6.0 は `starlette/testclient.py` が実行時に `httpx2` を試み、`ModuleNotFoundError` で `httpx` へフォールバックしたときに `StarletteDeprecationWarning` を 1 回出す。**`TestClient` を import するモジュールは 12 箇所** (すべて r2db 側のテスト: `r2db-api/tests/test_credential_persistence.py` 4 箇所、`test_audit_query.py` 5 箇所、`test_surfaces_env.py` 3 箇所)。`httpx.ASGITransport` を使う既存 54 箇所は `starlette.testclient` を import しないので警告源ではない。
- 実行環境の要件 (superuser 相当の `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN`、`max_connections=300`、`-n 5 --dist loadgroup`) は**引き継ぎ文書と作業指示書にしか書かれておらず**、`README.md` / `conformance-tests/README.md` / `CLAUDE.md` には無い。

### 1.3 Git 履歴に配備固有の実値が残り、公開規律の明文が足りない

- GitHub リポジトリは **private** である (2026-08-27 作成、2026-09-05 に `gh repo view` で確認)。「公開前提で書く」は**規律であって visibility ではない**。
- 配備記録 `docs/work-orders/DEPLOY_PHASE6_20260904.md` に入っていた配備固有の実値は **2026-09-05 に現行版で placeholder へ置換済み** (`077fe8b`) である。しかし**置換前の版は Git 履歴に残る** — 当該ファイルを触った commit は `4599f54` (新規作成) から `6a8596d` までの **6 個**である (`077fe8b` が 7 個目=置換 commit)。同期間に `docs/work-orders/` 配下で変更された他ファイルは `077fe8b` の commit 本文が列挙する sanitize 対象に含まれておらず、**実値混入は当該 1 ファイルの 6 commit に限定されていると読める** (一次証拠は `077fe8b` の commit message である)。
- `docs/security/public-repository-policy.md` の `Never publish` 節 (:17-23) が挙げるのは**鍵・パスワード・私有 credential・本番 `.env`・dump/実ログ/実データ・CI 埋め込み secret の 6 項目のみ**である。**hostname / cloud project 識別子 / 実 credential_id / IAM principal・e-mail / 内部トポロジ / 作業機の絶対パスは 1 つも書かれていない**。規律の断片は `docs/work-orders/INITIAL_GITHUB_PUBLICATION_WORK_ORDER.md:71` (「本番hostname、private address、internal-only endpoint等の公開不要な運用情報」) にもあり、**正本が 2 つに割れている**。
- **git の pre-commit hook は存在しない**。`.pre-commit-config.yaml` も `.git/hooks/` の実効 hook も無い。リポジトリ内で「pre-commit hook」と呼ばれているものは**フェーズ4 の DB トランザクションのコールバック機構** (`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md`) であり、git とは無関係である。
- `git filter-repo` は作業機に未インストールである。

### 1.4 r2db の配備資産がリポジトリに無い

`r2db-api/deploy/` にあるのは `DEPLOYMENT_RUNBOOK.md` (637 行)、`env/api.env.example` / `env/control.env.example`、`nginx/r2dbsvc-api-8443.conf.example`、`systemd/r2dbsvc-api.service` の 5 点である。

- **`r2dbsvc-control.service` 相当の systemd unit テンプレートが無い**。`env/control.env.example` は存在するのに、対応する unit が無い。runbook §7 (:499-638) の Deployment steps は「第二 unit を作り `ExecStart=` を `uvicorn r2db_api.control_main:app` に向けよ」と**文章で指示するだけ**である。
- nginx 例は `/v1/` のみを proxy する。`/control/v1/` については同ファイル :86-98 の**コメントが「このテンプレートにはまだ含まれていない (Phase 7 deploy-asset work として追跡、2026-09-05)」と明記**しており、実ブロックは無い。
- 実配備で作った operator script (part1 / part1b / part2 相当) は VPS の作業ディレクトリにしか無く、ローカルにも残っていない。**次回配備・復旧・第三者レビューで再現できない。**

### 1.5 現行結論と履歴が同居し、想定読者が現行の担保を抽出できない

- `security/CONTROL_MAPPING.md` は 100 行、SI 行 16 行の合計 **142,732 文字**、**2,000 文字超が 12/16 行**、最長は **SI-14 の 57,135 文字** (表全体の約 40% を 1 行が占める)。`SUPERSEDED` が 2 件。
- `conformance-tests/CONDITIONS.md` は 137 行、C 行 20 行の合計 **83,418 文字**、**2,000 文字超が 10/20 行**、最長は **C-09 の 17,015 文字**。
- 同じセルに旧主張・訂正・閉止記録・WP 進捗が蓄積している。履歴マーカーの語彙は `closed` / `RESOLVED` / `addendum` / `corrected` / `stale` / `WP-N` / `phase N` / `裁定` / `supervisor ruling` / 日付付き括弧 / `【追記】` など **10 種類以上**が自然文中に混在し、**統一記法は無い**。
- 本リポジトリの想定消費者は **AI エージェント**である。「現在有効な結論」を抽出しにくい状態は、宣言が確実に読まれるという前提を直接損なう。

### 1.6 起草時に確認した前提 (読み取り専用。テストは実行していない)

1. **`test_conditions_register.py` の解析制約**: `CONDITIONS.md` の `|` 始まりの行を**すべて単一の表とみなす** (:32)。ヘッダに `ID` 列と `Status` 列が必須 (:37-46)。データ行は `strip("|").split("|")` で列分割する (:54) ので、**セル内に生の `|` を置けず、1 行 1 レコードでなければ壊れる**。`Status` は `.lower().startswith("executable")` で判定する (:87 / :131)。
2. **`test_every_marked_condition_id_maps_to_an_executable_status` (:106-137) は逆向きの検査である** — `@pytest.mark.condition("C-05")` を付けたテストを追加した瞬間に、`CONDITIONS.md` の C-05 行の `Status` が `executable` で始まっていなければ**赤になる**。したがって**テストの追加と Status の更新は同一コミットに載る**。
3. **`CONTROL_MAPPING.md` を機械解析するコードは存在しない**。`--include="*.py"` の全走査で得られるのは 4 件の**コメント内相互参照**のみである (`MitateDB-api/src/mitatedb_api/control_plane.py:1624`、`r2db-api/src/r2db_api/control_plane.py:972`、`r2db-api/src/r2db_api/topology.py:42` / `:65`)。列構造を読むテストは無い。
4. **アンカーの前例**: `CONTROL_MAPPING.md#…` / `CONDITIONS.md#…` 形式のリンクはリポジトリ全体で **0 件**、表セル内の `<a id=…>` も **0 件**である。一方、**ID 単位の Markdown 見出しは確立された記法である** — `security/SECURITY_INVARIANTS_V1.md` が `### SI-00 — …` 形式で SI-00〜SI-15 の全てに H3 見出しを使っており、GitHub の自動アンカー (`#si-00…`) が生成される。
5. **port に idempotency の対応物は無い**。`conformance-tests/adapter.py` / `payloads.py` を全走査しても `idempotency_key` を受け渡す経路は 1 つも無く、`BatchOperation` (:735-753) / `ScopedBatchOperation` (:757-784) にも `attempt_mutation` 系のシグネチャにも当該フィールドが無い。**両 peer とも `idempotency: {"status": "unavailable"}` を宣言し** (`r2db-api/src/r2db_api/service.py:917`、`MitateDB-api/src/mitatedb_api/cell.py:1435`)、**`idempotency_key` を受け取ると `CAPABILITY_UNSUPPORTED` で実行前に拒否する** (r2db は `http.py:331-332` と `structured.py:205-206` の 2 箇所、MitateDB は `http.py:657-658` と `:741-742` の 2 箇所)。
6. **配備先の Python**: r2db の VPS は **3.12.3 のみ**である (`docs/work-orders/DEPLOY_PHASE6_20260904.md:99` / `:1005` / `:1481`。同 :99 は `DEPLOYMENT_RUNBOOK.md` §1 の言う virtualenv が未作成であることも記す)。MitateDB のコンテナ基底は `python:3.11-slim` である (`MitateDB-api/docker/Dockerfile:45` / `:71`)。集計行の記録環境は python3.11 の venv である。両 peer の `requires-python` は `>=3.11` である。
7. **配備記録テンプレート**の凡例は `docs/work-orders/DEPLOY_PHASE6_20260904.md` :3 の blockquote (実値置換の宣言) と §7 (:1412 以降) の blockquote (「記録に書いてよいもの / 書いてはならないもの」) の 2 箇所にある。§7 の現行文は `credential_id` を**書いてよい側**に置いており、D-1 (i) の決定と衝突する — D-1 (iii) はこの行の訂正を含む。

---

## 2. 守るべき条件

1. **C1 契約 1.6.0 は変えない**。本フェーズは契約無変更である。`limit_enforcement` の値語彙と `limits.classes` の 16 語は既存のまま使い、新しい語も新しいキーも足さない。
2. **C2 新しい共通 Security Invariant は不要である**。L6-20 の各項が既に SI への影響を記載している — (a) は SI-08、(g) は SI-10 の部分的無効化 (だから id を変える)、(h) は SI-02、(i) は表示形式のみ。**覆すなら根拠を示す** (§8)。
3. **C3 開発順序**を守る: 共通要件 → 該当 SI → 共通契約への影響判断 → conformance → 実装 → 実装別テスト・統制。
4. **C4 完了ゲート**の集計行は `pytest -q -n 5 --dist loadgroup` の**単独実行**で取る (skipped 0、xfailed は本設計で明示した件数のみ)。**設計段階では suite を回さない。**
5. **C5 常設規律 7 項目**を継承する。特に**規律 2 (完了条件 1 項目 = 変異 1 つ)** と**規律 5 (静的規則は逐語プロトタイプの後に設計へ)** — 後者に従い、D-2 のスキャナはプロトタイプ済みであり、結果を**付録 A** に添付する。
6. **C6 公開規律**: 設計文書・作業指示書に実値を書かない。
7. **C7 両 peer の対称性**: 同名ヘルパは同型性テスト (対応表) に載せる。**peer 間でコードは共有しない** (要請者決定 2026-09-03)。
8. **C8 並行作業**: 別セッションが Q4 を同じディレクトリで進行中である。本フェーズの実装のうち **Q4 と触るファイルが重なる部分 (7-B) は Q4 の main マージ後**に置く。

---

## 3. 決定と根拠

### D-1 (g) 公開計画と公開前ゲート (裁定 1・2 の実施設計)

**(i) `docs/security/public-repository-policy.md` の `Never publish` に下表の 6 分類を追記する。**

| 追記する分類 | 内容 |
|---|---|
| 本番 hostname | 実配備のホスト名・FQDN・private address・internal-only endpoint |
| cloud project 識別子 | project id と project number の実値 |
| 実 credential_id | locator 形 bearer の前半。**認証は破らないが標的を名指しできる** (SI-10、§8) |
| IAM principal・e-mail | service account、運用者アカウントのアドレス |
| 内部トポロジ | proxy 先・内部 port の実配置 |
| 作業機の絶対パス | `/Users/…` / `/home/…` / `C:\Users\…` 形の実パス |

あわせて `docs/work-orders/INITIAL_GITHUB_PUBLICATION_WORK_ORDER.md:71` の運用情報行を **policy への参照に置き換え**、**規律の正本を policy 1 つにする**。

**(ii) placeholder 規約を policy に置く。** 許される伏字の形は `<UPPER_SNAKE>` (山括弧つき) と `REPLACE_ME_*` の 2 つ、ドメインは `*.example.invalid` のみとする。**この規約は D-2 のスキャナの除外規則と 1 対 1 である** — 規約に無い形の伏字は検出される。

**(iii) 配備記録テンプレート** (`DEPLOY_PHASE6_20260904.md` §7 の形) に「**実値は書かず、対応表は運用者記録へ**」の規約と、凡例の形 (同 :3 の blockquote) を置く。**次の DEPLOY 文書はこのテンプレートから始める。** §7 の現行凡例が `credential_id` を「書いてよいもの」に置いている点は (i) と衝突するので**同時に訂正する** (§1.6 の 7)。

**(iv) First-public-push gate に追加する 8 項目** (最終 WP の完了条件と同一である)。

1. **すべての linked worktree を畳む** (`git worktree remove` / `git worktree prune`) — `.claude/worktrees/*` は共有ツリーの `.git/objects` を参照するので、書換後は不整合な参照を持つ。**書換自体は remote から取り直した fresh clone 上で実行する**。
2. `git filter-repo --replace-text` による**全履歴の置換**。置換表は**リポジトリ外の運用者記録にある既存の対応表**を使う (本書はその存在だけを書く)。
3. filter-repo が出す **commit-map で文書内の hash 参照を一括更新**する。対象規模は `docs/` + `security/` + `conformance-tests/CONDITIONS.md` の 43 ファイル中 **29 ファイル・262 件**の 7〜40 桁 hex 様トークンである (**母数の 43 は探索時に走査した `docs/` + `security/` 配下の `.md` と `conformance-tests/CONDITIONS.md` の合計本数である**。誤検出は精査で除く。全数目視は未実施)。
4. **同名リポジトリを delete し、書換後の履歴だけを push して再作成する** (**依頼者裁定 2026-09-05**、§6 (γ) 案 1)。全 branch・全 tag を push する。**運用者作業。** これを行わない限り、履歴の実値が消えるのはローカルだけである。**force push では GitHub 側に旧 commit が unreachable object として残り得る**ので、**remote の object store 自体を新しくする**。
5. **remote から新規 clone を取り直し**、そのクローンに**スキャナの履歴モード** (`git log --all -p` を走査) を掛けて**全規則 0 件**であること。**取得元は (4) で再作成した remote である** (§6 (γ) 案 1)。
6. **全 clone・worktree の作り直し** — 共有ツリー、`.claude/worktrees/*`、VPS 上の clone を含む。
7. **有効 credential 2 件 (r2db control / runtime) の revoke + 再発行**。**rotate は id を保持するため不可である** (裁定 2)。**運用者作業。**
8. **依頼者の実行合図** (着手条件) と **visibility の切替** (依頼者作業)。

**順序**: **(1) → (2) → (3) → (4) → (5) → (6) → (7) → visibility**。(3) は書換後の新 commit として乗る。**(4) が delete + 再作成である以上、(5) の取得元は再作成後の remote である。**(5) を (6) の前に置くのは、**検査対象を「remote が実際に保持している履歴」にする**ためである — ローカルの書換済みツリーを検査しても、公開されるのは remote 側の内容である。

**残留への注意 (対処は確定した)**: force push 後も、GitHub 側には旧 commit が **unreachable object** として残り得る (SHA 直指定で取得できる)。private → public の切替は、その残留を公衆に開くことを意味する。**この点への対処は §6 (γ) で確定した — 案 1 (同名リポジトリを delete し、書換後の履歴だけを push して再作成する) である** (依頼者裁定 2026-09-05)。**remote の object store 自体が新しくなるので、旧 object は存在しない。**

**覚悟すべき帰結として記録する**: 書換後、**リポジトリ外の記録 (運用者の私的記録、引き継ぎ以前のメモリ) が引く旧 hash は無効になる**。commit-map は**リポジトリ外の運用者記録に保存する** (内容は本書に書かない)。

**却下した代替案**:
- **別リポジトリへの新規公開** — 裁定 2 が単一リポジトリの維持を確定している。**なお §6 (γ) の案 1 (同名リポジトリの delete + 再作成) はこれとは別物である** — owner も名前も正本も 1 つのままであり、変わるのは remote の object store だけである。**この読み (裁定 2 の「単一リポジトリを維持する」は識別 (owner / 名前 / 単一の正本) の維持と読む) は依頼者裁定 2026-09-05 で確定した** (§6 (γ))。
- **BFG Repo-Cleaner** — replace-text の機構自体は同等だが、(2) の一括更新手順が **filter-repo の commit-map 形式を前提にしている**。
- **「置換前版が残るのは 6 commit だけだから該当 commit を squash する」** — 履歴の連続性と、他文書からの hash 参照を**より多く壊す**。

**SI への影響**: 新 invariant は不要である。**credential_id の露出は SI-10 の「未知 id と有効 id を応答で区別させない」性質を攻撃者に対して部分的に無効化する** (標的を名指しできる) ので、**公開時に id を変える** (L6-20 (g) のまま)。

**変異 (何を壊すと赤になるか)**: (5) はスキャナの履歴モードそのものであり、D-2 の変異が同じ規則を担保する。(3) は commit-map 適用スクリプトに対し、**未更新の旧 hash を 1 件残した状態で照合が非 0 終了する**ことを実測する。

### D-2 (b)(iv) 実値パターンの機械検査 — 逐語プロトタイプ済み (常設規律 5)

使い捨てスキャナ `proto_realvalue_scan.py` (scratchpad、標準 `re` のみ、655 行) を worktree の**追跡 217 ファイル**に走らせた。**v2 (規則調整後) の結果は真陽性 0 件**である。規則別の件数表は**付録 A** に置く。所要は 1.83 秒 (ツリー 2 走査 + 履歴) である。

**製品版の規則** (プロトタイプから確定するもの):

| 規則 | 対象 | 許可 / 除外 |
|---|---|---|
| **R1** | e-mail | `example.*` / `*.invalid` / `*.test` / `users.noreply.github.com` / `anthropic.com` |
| **R2_url** | スキーム付き URL | 拒否: `*.run.app`、`*.cloudfunctions.net`。許可: `localhost`、`127.0.0.1`、`github.com`、`pypi.org`、`python.org`、`postgresql.org`、`json-schema.org`、`cloud.google.com`、`*.googleapis.com`、公式 docs |
| **R2_fqdn** | 裸 FQDN | **TLD 限定集合** (`com` `net` `org` `jp` `io` `cloud` `info` `biz` と `run.app` `gserviceaccount.com`) に絞る |
| **R3** | GCP project 識別子 | `name-NNNNNN` 形の id と 12 桁 number。**UUID / hex トークンの内部は対象外** |
| **R4** | credential_id 形 | `[a-z]{2,5}_[0-9a-f]{16}`。tests/docs の合成値は**明示の許可リスト** = ファイル内に `synthetic` 注記があるものだけ |
| **R5** | IAM principal / service account | — |
| **R6** | 作業機の絶対パス | `/Users/`、`/home/<非 placeholder>`、`C:\Users\` |
| **R8** | secret 形 | PEM / `AKIA` / `ghp_` / `xox` / `AIza` |
| **R7** | 個人名 | **規則化不能につき対象外と明記する** (人手レビューに委ねる) |

**R2_fqdn の TLD 限定は実測に基づく**。プロトタイプ v2 が残した 112 件の誤検出は、**`self.dev` / `self.app` のような属性連鎖が短 TLD と衝突したもの**であり、短 TLD を外せば消える見込みである。**実装 WP で再プロトタイプし、0 件を確認してから固定する。**

**共通除外 (トークン全体ではなく部分文字列を除去して再判定する)**: トークンから **placeholder 部分文字列** (`<[A-Z0-9_]+>` と `REPLACE_ME[A-Z0-9_]*`) を**除去した残りに対して各規則を再適用し、残りが規則に当たれば flag する** (D-1 (ii) の規約と 1 対 1)。**「placeholder を含むトークンを丸ごと除外する」形は採らない** — その形だと `<HOST>` のような placeholder を実値の隣に前置するだけで、同一トークン内の実値がスキャナから完全に隠れてしまう。意図的な回避だけでなく、DSN 断片を書くときに自然に起きる形である。**この規則変更は付録 A の残存 2 件の判定を変え得る。** 1 件 (R2_url、`DEPLOY_PHASE6_20260904.md:83` の placeholder 2 個からなるホスト形) は、**旧規則 (トークン全体除外) では確実に消えるが、新規則では placeholder を除去した残りが再判定される**ので、消えるかどうかは実測でしか決まらない。もう 1 件 (R3 の UUID 断片) は「hex/UUID 内部の 12 桁は対象外」で消える。**新しい除外規則のもとで 2 件とも消えることは、実装 WP の再プロトタイプで確認する** — 消えなければ、**許可側の規則 (R2_url の許可リスト等) で受けるのであって、placeholder 除外を元の形へ戻すのではない** (L7-4)。

**配置**:
- `tools/public_value_scan.py` (root、新設 `tools/`、**依存無し**)
- `.pre-commit-config.yaml` の **local hook** (外部リポジトリ依存を持たない)
- CI の独立 job (D-3)
- **履歴モード `--history`** (`git log --all -p` を走査。公開ゲート D-1 (iv) の (5) 用)

**pytest suite には入れない。** suite は挙動を測るものであり、スキャナは公開規律である。**CI では両方が必須である。**

**却下した代替案**: 既製の secret scanner (gitleaks / trufflehog 等) の導入 — 本規則は secret ではなく**運用固有識別子**を対象にするので既製の規則集と目的が合わず、外部リポジトリ依存を pre-commit に持ち込む。**依存無しの 1 ファイルで足りる。**

**SI への影響**: 無い。既存の公開規律を機械化するだけである。

**変異**: **許可リスト外の TLD を持つ裸 FQDN 形 1 件と e-mail 形 1 件**を**実装担当が生成し、一時ファイルにのみ置いて赤を実測し、復元する** (`git checkout` は使わない)。履歴モードは、置換前の版を含む一時ブランチを走査させて非 0 終了することで測る。**この 2 件は許可リストの外に置く必要がある** — `*.example.invalid` は R1 / R2 の許可対象なので、それを使うと変異が空振りする。**具体値は設計・作業指示書・コミットのいずれにも書かない。実装担当が WP-1 で生成し、一時ファイルにのみ置く** — 本書に書けば、WP-1 でスキャナと pre-commit hook が入った瞬間に**本書自身が R1 / R2_fqdn で赤になる**。

**【監督注記 2026-09-06、WP-9 事前確認】** 公開ゲートのリハーサル (remote から取り直した scratch clone に対する `git filter-repo --replace-text`、push なし) で、スキャナの規則 3 点を実測に基づき精密化した: **(i) 履歴モードは diff の行頭マーカー (`+` / `-` / 空白) を 1 文字剥がしてから走査する** — 剥がさないと行頭のプラス記号が R1 の local part になり (プラス記号の直後にアットマークと点区切りのデコレータ名が続く形)、履歴側の R1 が 577 件に膨れていた (剥がすと 52 件、すべて `DEPLOY_PHASE6` の置換前版由来)。**(ii) URL / 裸 FQDN の最終ラベルにハイフンを含む host は公開 TLD になり得ないので識別情報としない** (`xn--` は除外; deny suffix の host は最終ラベルにハイフンを持たないので deny は素通りしない) — 履歴に残る分割リテラル (`https://…-platform` + 次行 `.example.invalid/…`) の誤検出 16 件を閉じる。**(iii) R4 の hex 半が `0123456789abcdef` または単一文字の反復である id は明白な合成値として除外** — `# synthetic` 注記が付く前の版が履歴に残る 7 件を閉じる。**リハーサルの結果: 書換前 685 件 (289 commit、DEPLOY_PHASE6 が 662) → 書換後 0 件。** **(iv) R1 の local part は英数字を 1 文字以上含むこと** — 記号だけの local part (diff マーカーや句読点がデコレータのアットマークに接した形) は e-mail ではない。リハーサル 2 (mailmap 込み、294 commit) で本注記の旧版 5 件だけが残ったため追加。**mailmap**: 履歴に 1 commit だけ別の GitHub アカウントの noreply identity があり、`--mailmap` (リポジトリ外) で r2fish noreply へ寄せる — 書換後は author / committer とも 1 identity。 置換表 (14 行) からの `--replace-text` 規則 23 本と commit-map (270 commit) はリポジトリ外の運用者記録に置く。

### D-3 (b)(i)(ii) constraints と CI

**lock 方式 = `constraints.txt` (root 1 本、exact pin)。**

- **生成手順**: 清浄な venv に両 peer の `[test]` extras を入れて `pip freeze` し、**venv 由来の無関係物を手で除く**。
- **利用**: `pip install -c constraints.txt -e ./r2db-api[test] -e ./MitateDB-api[test]`。
- **両 peer の `pyproject.toml` は下限 pin のまま**とする (互換性の主張)。**`constraints.txt` は再現性の記録**であり、役割が違う。
- **更新規約**: 依存を上げるときは、**constraints を更新したコミットに集計行を添える**。

**却下した代替案**: `uv.lock` / `pip-tools` / `poetry` — 追加ツールへの依存を作り、**両 peer が library 形式の下限 pin を保つ方針と二重管理になる**。

**CI = GitHub Actions `.github/workflows/ci.yml`**:

- ubuntu ランナー、**PostgreSQL 16 は `services:` ではなく専用 step の `docker run` で起動する** (`postgres:16`、`-c max_connections=300` をコマンド引数として直接渡す、**合成パスワード**、loopback への port 公開)。**GitHub Actions の `services.<id>` が受けるのは `image` / `credentials` / `env` / `ports` / `volumes` / `options` であり、コンテナのコマンド引数を渡すキーは無い** — `command:` と書いても構文エラーか無視になり、`max_connections` が既定 100 のまま `-n 5` を回して接続枯渇で赤になる。`docker run` step はローカル手順と同型でもある。**代替は service container + 起動後 step の `ALTER SYSTEM SET max_connections=300` + コンテナ再起動**だが、手数が増えるので採らない
- 環境変数 `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (superuser 相当、CI 内 loopback)。**両変数の既定値は unix socket (`host=/tmp`) であり、コンテナで起動した PG には届かない** — **CI では必ず loopback TCP の DSN で上書きする**
- **Python matrix: 3.11 と 3.12** — 3.11 は集計行の記録環境と MitateDB のコンテナ基底 (`python:3.11-slim`)、3.12 は r2db の VPS 実行環境である (§1.6 の 6)。**この 2 つは「実際に走る 2 環境」であることが事実確認で裏付けられている** (裁定 S-5): **r2db の VPS には 3.12 しか無く**、**MitateDB のコンテナ基底は 3.11 である**ので、どちらか一方だけを測ると、もう一方の実配備環境が無検査になる。**両方を required とする** (**依頼者裁定 2026-09-05**、§6 (α))。**完了ゲートの正本は 3.11 job の集計行** (集計行の記録環境) であり、**3.12 job は同一の集計行であることを required で担保する** — 集計行が食い違えば 3.12 job が赤になるので、引く集計行は 1 本のままである
- ゲートコマンド `python -m pytest -q -n 5 --dist loadgroup`、**集計行を job summary に出す**
- **別 job**: スキャナ (D-2)、配備資産 lint (D-5)
- **CI が緑であることを「共通証拠」とし、以後の完了ゲートは CI の集計行を正本の記録に引く** (ローカル単独実行は維持する)。**正本は 3.11 job の集計行である** (依頼者裁定 2026-09-05、§6 (α))

**実 PG の要件** (superuser DSN、`max_connections=300`、`-n 5`) を **`conformance-tests/README.md` に明文化する** — 現状これらは引き継ぎ文書と作業指示書にしか無い (§1.2)。

**pytest 設定の一本化**: root `pyproject.toml` の `[tool.pytest.ini_options]` に `filterwarnings = ["error::DeprecationWarning"]` を置く。**有効化は 7-B の WP-6 である** — 7-A の時点で置くと §1.2 の 12 箇所が赤になる。個別 `ignore` は**台帳項目を付けた場合にのみ**許す。

**SI への影響**: 無い。証拠の取得環境を固定するだけである。

**変異**: 「constraints から 1 行落とす」は install step が変わるだけで**緑のままなので変異にならない**。代わりに **「constraints に無いパッケージを import するテストを一時追加 → CI が赤」**で載ることを示す。PG 要件については **`max_connections` を 100 にして conformance が接続枯渇で赤になること**を実測する (フェーズ6 の実測は 64/100 接続であり、`-n 5` では超える見込みである)。**超えなければ「変異なし」と記録し、要件の根拠をフェーズ6 §10 の実測に置く。**

### D-4 (b)(iii) DeprecationWarning の error 化と httpx2 移行 (7-B)

発生源は Starlette の `testclient.py` が `httpx2` の import に失敗して `httpx` にフォールバックするときの警告であり、**`TestClient` 自体の廃止ではない**。影響は §1.2 の 12 箇所である。

- **第一案: `httpx2` を両 peer の `[test]` extras に足す。** PyPI に実在し `constraints.txt` で pin できることを**実装 WP が確認する** (作業機の venv では未確認である)。**完了条件に「PyPI 上の提供元が Starlette / encode 系の公式配布であることを確認済みであること」を置く** — 公開直前のリポジトリの test extras に**素性を確認していない PyPI 名**を足すのは、名前の取り違えや typosquat の余地がある領域だからである。**確認できなければ第一案は採らず、下記の代替へ切り替える。**
- **代替: 12 箇所を `httpx.ASGITransport` へ書き換える** — 既存 54 箇所と同型であり、`starlette.testclient` への依存そのものが消える。**外部依存を増やさない**。

**どちらを採っても、`error::DeprecationWarning` を有効化したうえで集計行が変わらないこと**を完了条件とする。

**却下した代替案**: `ignore::StarletteDeprecationWarning` の一括 ignore — **警告を消すのではなく原因を消す**。ignore は「error 化した」という主張を空にする。

**SI への影響**: 無い。

**変異**: `filterwarnings` を有効化した状態で、**`DeprecationWarning` を意図的に発する一時テストを足して赤を実測**し、復元する。

**【監督訂正 2026-09-06、WP-6 レビュー 指摘 1】** 本節の前提「httpx2 を入れなければ `error::DeprecationWarning` で 12 箇所が赤になる」は実測で反証された — `starlette.exceptions.StarletteDeprecationWarning` は **`UserWarning` の派生**であり (MRO `StarletteDeprecationWarning → UserWarning → Warning`)、`error::DeprecationWarning` では捕まらない。error 化で実際に赤になるのは上流の `anyio.abc.BlockingPortal` 参照 (L7-19) であり、こちらは httpx2 の有無と無関係である。httpx2 採用の役割は「上流の fallback 警告を warnings summary から消し、Starlette が fallback を落としたときの `RuntimeError` に備え、両 peer の `[test]` extras を対称に保つ」ことに改める。TestClient は維持 (ASGITransport 置換は lifespan 駆動の有無が変わる)。

### D-5 (h) r2db 配備資産の再現性

**追加物**:

1. **`r2db-api/deploy/systemd/r2dbsvc-control.service`** — 既存 `r2dbsvc-api.service` と同型の unit。**unit 名・port・`EnvironmentFile` は placeholder** (`REPLACE_ME_CONTROL_PORT` 等)、`ExecStart` は `uvicorn r2db_api.control_main:app` を指す。既存 unit の hardening 節と `PrivateTmp` の posture B 注意書きは同型で持つ。
2. **nginx 例に `location /control/v1/` ブロックを追加**する — `location /v1/` と**同じ proxy_* 設定**、`REPLACE_ME_CONTROL_PORT`、**`listen 8443 ssl http2;` の nginx 1.24 互換記法** (実配備で `http2 on;` が `nginx -t` に落ちた教訓)。テンプレート :86-98 の「まだ含まれていない」コメントは、追加と同時に置き換える。
3. **`r2db-api/deploy/scripts/` に operator script** を置く — part1 (OS user・ディレクトリ・venv・migration `0005` 適用。**`api_password` 変数が必須である**という教訓を反映)、part1b (control credential reset)、part2 (unit と nginx の有効化)。**runbook §7 と `DEPLOY_PHASE6_20260904.md` §8 の記録から合成値で書く** — **実機からの回収は前提にしない**。運用者が原本と突合するのは任意の検証である。
4. **runbook §7 を上記への参照に更新する** (「第二 unit を作れ」という文章指示をテンプレート参照へ)。
5. **runbook :105 の stale な「Python 3.11 virtualenv」を訂正する** (裁定 S-5) — **実配備の VPS は 3.12 のみである** (§1.6 の 6) ので、この行は現行の配備先と食い違っている。`requires-python` (`>=3.11`) を満たす版という表現に改め、**具体の版を書く箇所は CI の matrix (D-3) と配備記録に一本化する**。

**検証 = CI の deploy-assets lint job**: `systemd-analyze verify` (ubuntu)、`nginx -t` (placeholder を合成値に置換した一時 conf に対して)、`bash -n` + shellcheck (利用可能なら)。

**却下した代替案**: 実機からの回収を前提にする — **実値を持ち込む経路になる** (D-1 の規律に反する)。運用者作業への依存も増える。

**SI への影響**: **SI-02 の分離プロセス構成を再現可能にするだけ**であり、新しい境界は作らない。

**変異**: unit の `ExecStart` を壊す → lint job が赤。nginx ブロックの `proxy_pass` を壊す → `nginx -t` が赤。

### D-6 (a) 6 条件の共通化 — C-05 を先頭に置く (裁定 3)

#### D-6.1 C-05 の形

新規ファイル **`conformance-tests/test_c05_limit_declaration_agreement.py`**、**4 plug 全数**。構造は **C-17 と同じ**「宣言で分岐し、非 enabled 側は skip せず**宣言の正直さを assert する**」形を採る (`conformance-tests/test_c17_declaration_agreement.py` の module docstring がこの構造の根拠を書いている)。

**V1 — 宣言の自己整合 (4 plug 全数。(a)〜(d) は両 plane、(e) は application plane のみ。監督裁定 S-1 の確定形 + 設計レビュー 1 回目 B-7 / B-8)**

- **(a)** `limit_enforcement` のキー集合 ⊆ `limits.classes`、かつ `limits` のキー集合 ⊆ `limits.classes` (契約 `capability_status.rules` の 4 番目が既に前者を 1.2.0 の義務として書いている)
- **(b)** `limits` に値を持つ class は、**すべて `limit_enforcement` にエントリを持つ** (契約 rule「Every discovered finite limit names its enforcement layer」)
- **(c)** **`enforced` / `reference_wall_clock`** のエントリは、`limits` に**有限値 (integer ≥ 1)** を持つ
- **(d)** **`unavailable` / `deployment_required`** のエントリには、**`limits` 側の制約を置かない** — 値があってもなくてもよい
- **(e)** 下記の**必須エントリ集合**の各 class に**明示のエントリがある** (欠落は赤)。**適用面は application plane のみである** (下記 (e) の適用面)

**(c) が `deployment_required` を対象から外している理由** (設計レビュー 1 回目、B-7): 契約 `capability_status.rules` は「発見された有限 limit は enforcement 層を名指す」ことしか要求しておらず、**`deployment_required` の class に有限値を要求する規則は契約に無い**。加えて `deployment_required` は「境界を持つのは reverse proxy / platform 側であり application code は値を知らない」という状態を表す語であるから、**有限値を要求すると、その正直な宣言のほうが赤になる**。契約が要求しないことを共通 suite が要求する範囲は最小に留める、という方針から、`deployment_required` は `unavailable` と同じ扱いにする。**現時点で `deployment_required` を宣言する plug は 0 である**ので、この選択が現況の被覆を減らすことはない。

**(d) は当初案の「`unavailable` の class は `limits` に値を持たない」を撤回したものである** (裁定 S-1)。値あり + `unavailable` は矛盾ではなく「**値は公開するが、この surface では enforcement 層が無い**」という正直な宣言であり、**MitateDB の in-process 面の `request_bytes` がその実例である** — `cell.py:1491` が有限値を出し、`cell.py:1502` が `unavailable` を宣言し、HTTP 面でのみ `http.py:577` が `enforced` へ上書きする (§1.1)。撤回した規則を残すと、この正直な宣言が赤になってしまう。

**必須エントリ集合 = 固定 9 + capability 条件付き 3** (裁定 S-2)

- **固定 9** (request を捌くプロセスに**常に適用される**ので、capability 宣言によらず明示エントリを要求する): `request_bytes` / `batch_items` / `result_items` / `query_complexity` / `execution_ms` / `concurrency` / `requests_per_minute` / `schema_objects` / `operation_depth`
- **capability 条件付き 3** — 当該 capability を `unavailable` と宣言する plug では**エントリの欠落を許す (適用外)**。`unavailable` 以外を宣言するなら**明示エントリ必須**である。

| class | 従属する capability |
|---|---|
| `batch_entities` | `cross_entity_mutation` |
| `idempotency_entries` | `idempotency` |
| `idempotency_retention_ms` | `idempotency` |

**(e) は契約の義務ではなく、共通 suite が課す追加要件である** (設計レビュー 1 回目、B-7)。契約 `capability_status.rules` は 4 条であり、「`limits` / `limit_enforcement` のキーは `limits.classes` から採る」(1.2.0 義務) と「発見された有限 limit は enforcement 層を名指す」までしか要求していない — **「固定 9 class を必ず宣言せよ」という規則は契約に存在しない**。したがって **契約 1.6.0 に準拠しつつ (e) を満たさない第三者実装はあり得る**。それでも (e) を課すのは、C-05 が担う命題が **SI-08 の「All applicable resource classes have finite, discoverable bounds」の証拠**であり、`conformance-tests/` が CLAUDE.md の定める **implementation-independent な behavioral/security requirements** の置き場だからである — 宣言が無い class は「実装していない」と「宣言し忘れた」が区別できず、SI-08 の発見可能性が成立しない。**この位置づけを `CONDITIONS.md` の C-05 行の射程開示にも同文で書く** (§7.3)、また §8 の SI-08 段落にも 1 文置く。**契約側へこの規則を持ち上げるかどうかは本フェーズの対象外である** (契約無変更、制約 C1)。

**(e) の適用面 = application plane のみである** (設計レビュー 1 回目、B-8)。V1 の **(a)〜(d) は両 plane**に掛けるが、**(e) は application plane の capability 文書にのみ**掛ける — 上記の必須エントリ集合は application plane の class で構成されており、control surface の文書に当てると 3 class しか持たない正しい文書が赤になる。**control plane 側の必須集合は新たに定義せず、C-14 vector 5 を基準に 4 class とする** — C-14 が既に位置演算で駆動している **`applications` / `credentials_per_application` / `control_requests_per_minute`** の 3 class と、**`audit_query` を `unavailable` 以外で宣言する plug でのみ必須になる `audit_requests_per_minute`** である (後者は C-14 の駆動対象には入っていないので、C-05 が宣言の存在だけを見る)。

**帰結 (peer ごと)**:

- **r2db** は `ResourceLimits` の 9 class をそのまま宣言し、`cross_entity_mutation` / `idempotency` をいずれも `unavailable` と宣言している (`service.py:930` / `:917`) ので、**無変更で (e) を満たす**。
- **MitateDB** は固定 9 のうち **4 class が欠落している** — `execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` (§1.1)。`MitateDB-api/src/mitatedb_api/cell.py` の `limit_enforcement` ブロック (`:1494-1504`) に**明示エントリを足す**。`cross_entity_mutation` は `partial` なので `batch_entities` は必須であり、既に宣言済みである。`idempotency` は `unavailable` (`cell.py:1435`) なので条件付き 2 class は適用外である。
  - `execution_ms` / `concurrency` / `requests_per_minute` の 3 つは **`unavailable`** とする (次フェーズ候補 L7-1 の対象)。
  - **`operation_depth` は二枝であり、WP-4 の実装担当が事実を確かめて決める** — MitateDB が filter / 操作の入れ子深さを**実際に有限で拒否している**なら `enforced` + `limits` 値を宣言し、**V2 の駆動対象に入れる**; **していなければ `unavailable`** と宣言し、**V3 の xfail と L7-1 の対象に 4 番目の class として加える**。**どちらになるかは実測で決まる**ので、本設計は両方の枝を書く。

いずれも peer-local の宣言変更であり、**契約は変わらない**。既存の `request_bytes: unavailable` (`cell.py:1502`) と**同型の前例がある**。宣言の置き場が `cell.py` の `limit_enforcement` ブロックであることは、R-3 のとおり `cell.py` が capability 内容の単一の真実であり、`http.py:577` は enforcement 層の事実 1 件だけを上書きする既決の分担なので、**未実装を表す宣言は backend 非依存側に置く**のが正しい (この置き場は §6 の論点ではなく、既存の分担から一意に決まる)。

**V2 — 宣言値と拒否位置の一致 (C-14 vector 5 の一般化)**

**駆動集合 = (その plug が実際に叩く surface の capability 文書で `enforced` と宣言されている class) ∩ (D-6.2 で両側または片側の検査形を持つ class)** (裁定 S-1 + 設計レビュー 1 回目 A-3)。**両方の条件を明文で交差させる**のは、片方だけでは規則が決まらないからである — **r2db は `concurrency` を `enforced` と宣言している** (`service.py:936-937` が `execution_ms` 以外を機械的に `enforced` にし、実 enforcement は `service.py:1137` にある) が、**port には「N 個の要求を in-flight で保持したまま N+1 個目を出す」手段が無い** (D-6.2)。宣言だけから駆動集合を導出すると、r2db の 2 plug で `concurrency` が駆動対象に入り、実装担当は固定除外リストを書くか、テストを空振りさせるか、L7-1 の primitive を前倒しするかを迫られる。

**差集合 (`enforced` と宣言されているが検査形を持たない class) は V1 の整合検査のみを掛け、その差集合が空でないことと理由を `CONDITIONS.md` の C-05 行に開示する** — 起草時点では **r2db の 2 plug の `concurrency` 1 件**である。**開示するのは「駆動していない」という事実そのもの**であり、これを黙って落とすと「宣言は `enforced` なのに誰も確かめていない」状態が読み手から見えなくなる。

**検査の形は class ごとに 2 種類ある** (D-6.2 で class ごとに確定する):

- **両側検査**: 宣言値 N を**同じ instance の capability 文書から読み**、**N で成功 / N+1 で `LIMIT_EXCEEDED`** であることを検証する (C-14 vector 5 と同型)。
- **片側検査**: **宣言 N を確実に超える構成が `LIMIT_EXCEEDED` になること**と、**N 未満の安全側の最小要求が成功すること**を検証する。**両 peer で N / N+1 の位置が一致するレシピを書けない class に用いる** — この形については「**位置演算**」という語を使わない (位置を測っていないため)。

**どちらの形でも `details.limit_class == class` を検査する** — **C-14 と違い soft ではなく必須である**。根拠は自前の論ではなく契約である: `errors.details_vocabulary.LIMIT_EXCEEDED.limit_class` は **"string, required"** と定められ、`versioning.version_binding` がこれを **1.2.0 の義務**として列挙している。両 peer とも 1.6.0 を宣言しているので**義務である**。とりわけ片側検査では、**拒否が起きたことだけでは「どの class の bound に当たったのか」が決まらない**ので、`limit_class` の一致が命題を成立させる唯一の手段になる。

**この限定は plug ごとに効く** — MitateDB の in-process plug が見る `request_bytes` は `unavailable` なので **駆動しない** (V1 (d) がその宣言の正直さを受ける)。同じ class を HTTP plug は `enforced` として見るので、**HTTP plug でだけ駆動対象になる**。**駆動集合を宣言から導出するとは、この plug ごとの差を固定リストではなく宣言から出す、ということである。**

**空振り防止 (per-plug 非空性)**: **各 plug について、駆動した class が 1 つ以上あることを、その plug のテスト内で assert する** (設計レビュー 1 回目、B-8)。これが無いと、peer が全 class を `unavailable` へ倒したときに **V2 が静かに緑になる** — 固定 9 は V3 が拾うが、`batch_entities` のような capability 条件付き class は V3 の対象外なので拾えない。前例は **C-17 の per-plug 非空性 assert** (`conformance-tests/test_c17_declaration_agreement.py:182-218`、「this test's sweep would be vacuous」) である。`-n 5 --dist loadgroup` では plug ごとに worker が分かれるので、**session 横断の集約 guard は成立しない** — 非空性はテスト内で測る。

**conformance build の大きさ (C-14 と同型の前提)** (設計レビュー 1 回目、B-4):

- **(a) 上限**: application plane の各駆動 class について、`limits` 値が **C-14 の `_MAX_EXERCISABLE_LIMIT` 相当以下**であることを assert する (`conformance-tests/test_c14_authority_boundary.py:141` / `:476` と同型)。**理論上有限なだけの bound は 1 回の試験で越えられない。**
- **(b) rate 窓の headroom**: r2db の `requests_per_minute` 窓は credential 単位で、`_slot` を通る**すべての** application-plane 操作が 1 件消費する (`service.py:1157-1163`)。したがって他 class の駆動 (N+1 行の投入、N+1 個の schema object 作成など) が rpm 窓を先に食い潰すと、**宣言 N より早く発火して位置がずれ、赤が恒常化する**。**`requests_per_minute` を駆動する前に、他 class の駆動が消費する最悪ケースを検算した headroom 前提を assert する** (`test_c14_authority_boundary.py:490-511` と同型)。**あるいは class ごとに新しい `isolated_application_surface()` を張る** — どちらを採るかは実装 WP が決め、採った側を port の docstring に明記する。

**port v1.11 に `isolated_application_surface()` を追加する** — 使い捨ての data-plane instance (独自の窓・カウンタ、**小さな conformance profile**) を張り、**その instance の `capabilities()` が返す宣言と検証対象を同一にする**。C-14 の `isolated_control_surface()` (`conformance-tests/adapter.py:1211-1226`) と**対になる primitive だが、yield する形は異なる** (設計レビュー 1 回目、B-5) — `isolated_control_surface()` が yield するのは `control_capabilities` 相当の**単一の要求を提示する callable** であり、駆動 class が `control_requests_per_minute` 1 つに閉じているから成立している。application plane では `result_items` に N+1 行の投入、`schema_objects` に N+1 個の entity 作成、`batch_items` に batch mutation、`query_complexity` に query が要り、さらにその instance の `capabilities()` を読む必要があるので、**単一 callable では構成できない**。

**したがって `isolated_application_surface()` が yield するのは、port 準拠の adapter instance** — **小さな conformance profile を宣言する新しい service に束縛した、同型の adapter** である (自己相似)。テストは**通常の port 操作でそれを叩く**ので、駆動レシピごとに port へ場当たりのメソッドを足す必要が無く、隔離の目的 (共有 surface に戻らない) も保たれる。**テスト終了時に close する** (D-6.6 の資源検査がこれを測る)。**必要な操作の一覧は D-6.2 の駆動レシピから逆算して決まる。**

**V3 — fail-loud**

**V3 は固定 9 を静的に parametrize する** (設計レビュー 1 回目、B-8)。各 (plug, class) の組について「**この class は `unavailable` 以外である**」ことを assert し、**現時点で `unavailable` である組にだけ `xfail(strict=True)` を静的に付ける** — 起草時点では **MitateDB の plug 2 つ (`MitateDB-api` / `MitateDB-api-http`) × 3 または 4 class** である。reason には**次フェーズ候補 (L7-1) を名指しする**。

**parametrize の基底を宣言から導出しない**のは、`xfail(strict=True)` が **収集時の静的 mark でなければ XPASS を検出できない**からである。宣言由来にすると、宣言が `unavailable` から上がった瞬間にその組が**収集されなくなり**、strict の赤 (= 撤去の合図) が出ない。静的にすることで、r2db の 2 plug でも 9 組がそのまま実行され (すべて合格)、**「宣言が `unavailable` へ落ちたら赤になる」という逆向きの担保も同時に得られる**。§7.4 の「3 または 4 × MitateDB plug 2」という算術はこの形でのみ成立する。

**件数は「MitateDB HTTP plug で class ごと 3 または 4 本、MitateDB in-process plug で 4 または 5 本 = 合計 7 または 9」**である — `execution_ms` / `concurrency` / `requests_per_minute` の 3 class が両 plug の確定分、`operation_depth` が上記の二枝で `unavailable` に落ちた場合に両 plug で 1 本ずつ加わり、さらに **in-process plug は `request_bytes` を `unavailable` と宣言している** (`MitateDB-api/src/mitatedb_api/cell.py:1502`。HTTP 面だけ `http.py:577` が `enforced` に上書きする) ので、静的 parametrize の下では in-process plug に `request_bytes` の 1 本が加わる (§7.4)。V1 (d) はこの「値あり + `unavailable`」を正直な宣言として受けるが、V3 は宣言だけから「surface に enforcement 層が無い」と「未実装」を区別しないので、r2db が in-process でも構造推定 (`limits.py:36-69`) で `request_bytes` を enforced にしている以上、MitateDB in-process の `request_bytes` も L7-1 の対象 (副項目) として扱う (監督裁定 2026-09-05、起草者の矛盾報告 1 に対する判定)。**class ごとに分けるのは撤去の粒度を実装の粒度に合わせるためである** — L7-1 が 1 class ずつ実装されたときに、その class の xfail だけが XPASS になる。

フェーズ6 の全体 vacuity guard と同じ規律である — **実装が入って宣言が `unavailable` 以外へ上がったコミットで XPASS → strict が赤 → 同一コミットで当該 class の xfail を撤去**する。**`unavailable` の明示宣言を足すだけでは XPASS しない** (`unavailable` である限り vector は落ち続ける) ので、xfail の先置きと宣言追加は同一 WP に置ける (§6 (β))。

#### D-6.2 class の分類表

本表を設計に置き、**テストの vector 一覧で固定する**。**「駆動レシピ」列には、両 peer で同時に成立する具体の駆動手順を書く** — ここが書けるかどうかが「検査の形」を決める (設計レビュー 1 回目、A-2)。

| class | 契約上の意味 (何を bound するか) | 両 peer で同時成立する駆動レシピ | 検査の形 |
|---|---|---|---|
| `batch_items` | 1 要求に含まれる操作の数 | 1 リクエストに N 操作 / N+1 操作。**数え方は両 peer とも操作数そのものである** | **両側** (N 成功 / N+1 拒否) |
| `batch_entities` | 1 要求が跨る entity の数 | 1 リクエストで N entity / N+1 entity (C-16 と重なるので §D-6.4 参照) | **両側** |
| `schema_objects` | application が保持できる schema object の数 | 隔離 instance に N 個作って成功 / N+1 個目で拒否 | **両側** |
| `operation_depth` | 操作構造の入れ子の深さ | N 段のネスト / N+1 段のネスト。**MitateDB が `unavailable` を宣言する枝では駆動されず V3 の対象になる** (D-6.1) 【**訂正註 2026-09-07 (フェーズ8 D-2 裁定 R-A)**: **駆動レシピは「フラット insert (深さ 4) が成功 / 同じ insert に `where` を足して深さ 5 で拒否」から「`update` + `where` (深さ 5) が成功 / `where` の value を dict にして深さ 6 で拒否」へ改まり、隔離 profile の `operation_depth` は 4 plug とも 4 → 5 になった。** 理由: **depth=4 のままでは隔離面で `where` 付き mutation が全て拒否され、MitateDB の唯一の破壊的操作である `delete` を使う C-04 が MitateDB-http で赤になる** (実測)。**MitateDB は両面とも `enforced` になったので、「`unavailable` を宣言する枝」は現存しない** (フェーズ8 §10 L8-3 / L8-12)】 | **両側** (宣言次第) |
| `requests_per_minute` | 単位時間あたりの要求数 | 隔離 instance の空の窓に N 回 / N+1 回目 (C-14 の `control_requests_per_minute` と同型)。**D-6.1 V2 (b) の headroom 前提が要る** | **両側** |
| `idempotency_entries` | 保持する idempotency key の数 | N 個 / N+1 個の key。ただし `idempotency` が `unavailable` 以外であることが前提であり、**現時点で該当 plug は 0 である** (capability 条件付き 3、D-6.1) | **両側** (該当 plug 出現時) |
| `request_bytes` | 1 要求の本文の大きさ | **書けない。** r2db の enforcement は**バイト長ではなく構造推定**である (`r2db-api/src/r2db_api/limits.py:36-69` — str は `len*4`、scalar は 8、container は 2 として積算し、さらに container 要素数が `bound // 8` を超えた時点で拒否する)。MitateDB の HTTP 面は**実バイト計測**である (`http.py:577` が enforcement を `enforced` へ上書きする middleware)。**「N+1 バイトの本文」では r2db の拒否位置が N バイトにならない** | **片側** (明らかな超過の拒否 + 最小要求の成功) |
| `result_items` | 1 回の読み出しが返す行の数 | **書けない。** r2db は `min(len(rows), page_size) > N` を見る (`structured.py:1198`)。MitateDB は**要求 limit** が `> max_result_rows` かどうかだけを見て**返却行数は見ない** (`cell.py:558-559`)。**両 peer の返却規則が異なり、共通の 1 レシピで N+1 の位置を作れない** | **片側** |
| `query_complexity` | 1 query の複雑度 | **書けない。複雑度の単位が契約で未定義であり、metric の合成が peer 別**である — r2db は `len(where)+len(select)+order_by_count` (`structured.py:1183`、`postgres.py:984`)、MitateDB は `len(filters)` のみ (`cell.py:1174`)。**「N+1 個の filter 項」では r2db 側の N が別の値になり、成功側が赤になる** | **片側** |
| `execution_ms` | 1 操作の実行時間 | **構成不能** (wall-clock。決定的に N+1 を作れない) | **駆動しない** (V1 の整合検査のみ) |
| `concurrency` | 同時に in-flight な要求の数 | **構成不能** — **in-flight を保持する primitive が port に無い**。次フェーズ候補が MitateDB の実装と同時に port へ足す (L7-1) | **駆動しない** (V1 の整合検査のみ) |
| `idempotency_retention_ms` | idempotency 記録の保持時間 | **構成不能** (時間。retention を待つ vector は決定的でない) | **駆動しない** (V1 の整合検査のみ) |

**本表は起草時点の見立てである。** レシピは 4 plug 全数で実測したものではないので、**実装 WP が全 plug で実測して確定する**。**両側が成立した class を増やすのは可**であり (実測でレシピが書ければ格上げしてよい)、**両側から片側へ、または片側から「駆動しない」へ落とすには、その理由の開示が要る** (下記)。確定後の分類は §13 に記録する。

**開示する事項** (`CONDITIONS.md` の C-05 行、§7.3):

1. **「駆動しない」3 class とその理由** — `execution_ms` / `concurrency` / `idempotency_retention_ms`。
2. **片側検査に落とした 3 class とその理由** — `request_bytes` / `result_items` / `query_complexity`。**片側検査は「宣言値 N が正しい」ことを測っていない** — 測っているのは「宣言した bound を確実に超える要求が、その class を名指して拒否される」ことだけである。この差を読み手に開示しないと、C-05 の被覆が実際より強く読まれる。
3. **`enforced` と宣言されているが駆動集合に入らない class** (D-6.1 V2 の差集合) — 起草時点では r2db 2 plug の `concurrency`。

**`reference_wall_clock` / `deployment_required` と宣言された class は V1 の整合検査のみ**の対象である (`deployment_required` は「application code の証明ではない」と契約 `capability_status.rules` が明記しており、拒否位置の検査対象にできない)。

**本表は「class として検査形を構成できるか」を示すものであり、実際の駆動集合ではない。** 駆動集合は V2 の交差規則 (その plug が叩く surface で `enforced`、**かつ**本表で検査形を持つ) から決まる (D-6.1)。**検査形を持つ class でも、その plug で `unavailable` と宣言されていれば駆動せず、V1 (d) と V3 が受ける。**

#### D-6.3 C-05 の vector 表 (V1 / V2 / V3、plug ごとの分岐)

| vector | `r2db-api` (in-process) | `r2db-api-http` | `MitateDB-api` (in-process) | `MitateDB-api-http` |
|---|---|---|---|---|
| **V1 (a)〜(e)** 宣言の自己整合 (application plane) | 実行 | 実行 | 実行 | 実行 |
| **V1 (a)〜(d)** 宣言の自己整合 (control plane。**(e) は掛けない**) | `control_plane` が `unavailable` 以外の plug でのみ実行。それ以外は**一様不在**の assert (既存 `absence` ヘルパと同形) | 同左 | 同左 | 同左 |
| **V2** 宣言値と拒否位置の一致 | **(その plug が叩く surface で `enforced`) ∩ (D-6.2 で検査形を持つ)** を**宣言から導出して**駆動。**`concurrency` は `enforced` と宣言されているが検査形が無いので駆動集合から外れ、その事実を C-05 行に開示する** (D-6.1) | 同左 (`concurrency` の差集合も同じ) | 同左 (`request_bytes` は in-process 面では `unavailable` なので**この plug では駆動しない**) | 同左 (`request_bytes` は HTTP 面でのみ `enforced` なので**この plug でだけ駆動対象になる**) |
| **V3** fail-loud (**固定 9 を静的に parametrize**) | 9 組すべて実行 (合格。`unavailable` の固定 9 class が無い) | 同左 | 9 組すべて実行。うち **`xfail(strict=True)` × 4 または 5** (`request_bytes` を含む) | 9 組すべて実行。うち **`xfail(strict=True)` × 3 または 4** |

**V2 の駆動集合は宣言から導出する** — 固定リストを書かない。宣言が変われば駆動集合が変わり、**宣言を偽ると拒否位置が食い違って赤になる**のが本テストの命題である。**同じ class が plug ごとに駆動対象になったりならなかったりするのは正しい挙動である** — `request_bytes` の in-process / HTTP の非対称がその実例であり (§1.1)、V1 (d) がその宣言の正直さを別に受けている。**一方、V3 の parametrize 基底は宣言から導出しない** (静的な固定 9)。理由は D-6.1 V3 のとおり、`xfail(strict=True)` が静的 mark でなければ XPASS を検出できないためである。**この 2 つは意図的に非対称である。**

#### D-6.4 既存 vector との重なり

- **C-14 vector 5** は **control plane の 3 class** (`applications` / `credentials_per_application` / `control_requests_per_minute`) を既に位置演算で固定している。**C-05 は重複させず参照する** — C-05 が担うのは application plane と、両 plane の宣言自己整合である。
- **C-16** は `batch_entities` の**原子性**を固定している。C-05 が見るのは**宣言値と拒否位置の一致**であり命題が違うが、駆動は同じ endpoint に当たるので、**C-16 の既存 vector を参照し、同じ assert を二重に書かない**。
- **C-14 の `limit_class` 注釈は stale であり、WP-4 で訂正する** (設計レビュー 1 回目、B-9)。`conformance-tests/test_c14_authority_boundary.py:639-650` は「`limit_class` は契約保証を持たないので soft check にする」と注釈し、`errors.shape` の `details` が free-form であることを根拠にしている。**しかし契約 `errors.details_vocabulary.LIMIT_EXCEEDED.limit_class` は "string, required" であり、`versioning.version_binding` がこれを 1.2.0 の義務として列挙している。** 同じリポジトリの中で C-14 が「保証が無い」と書き C-05 が「必須である」と主張する状態は、**同一の契約事実について 2 つの conformance ファイルが矛盾した記述を持つ**ことになり、想定読者が AI エージェントである以上、実害のある誤読源である。**WP-4 は注釈の訂正を行う。** assert 自体を hard へ上げるかは C-14 の射程なので**別項として扱う** (本フェーズでは決めない)。**あわせて `PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 の L6-19 を「契約 `details_vocabulary` が既に `limit_class` を必須化しているので、手当て候補 (i) は済んでいる」として閉じる** — L6-19 の起票時の前提 (契約が保証しない) は事実誤認であった。

#### D-6.5 Q4 との揃え方

**C-05 は宣言を「検証対象と同じ instance の wire 文書」から読む。** Q4 は宣言の**出所** (surfaces / coalescing / timeout) を DB 側へ寄せるが **wire は不変**であり、**limit class は Q4 の対象外**なので、**vector 自体は影響を受けない**。

影響を受けるのは **`isolated_application_surface()` の構成経路**である。HTTP plug は composition root を通る。Q4 WP-B 以後の **MitateDB α plug は platform DB の宣言表に seed が要る**一方、**r2db γ plug は明示注入のままである** (Q4 設計 §6.1 / LQ4-11 の非対称)。

**なお Q4 §6.1 / LQ4-11 が述べる非対称は control plane の composition root に関するものである。** data plane の隔離 surface については、**MitateDB の `surfaces` が Q4 D-2 の宣言表由来になる** (`cell.py` の `_surfaces_document_fragment(config)`) ので**別の経路で同じ結論** (seed が要る) に達する。**追補にはこの区別を書く** **【監督訂正 2026-09-06、追補承認時】この 1 文は現物と合わない — `cell.py:1480` が読むのは `config` であり、宣言表の値が `config` に入るのは `main.build_app` (`main.py:321/377`) だけで、両 MitateDB plug は `FoundationConfig(data_base_url=…, control_base_url=…)` を明示注入している。したがって seed 要否の非対称は Q4 §6.1 α/γ と**同じ理由 (control plane の composition root)** であり、data plane の隔離 surface に seed は要らない。追補 (下記) の事実が正であり、本文のこの推測は撤回する。** — 書かないと、実装担当が control 側の記述をそのまま data 側へ写す事故が起きる。

##### Q4 確定後の追補

【追補記入 2026-09-06、Q4 v1.4 (main `55a7a5a`) 確定後。**監督承認済み 2026-09-06** — WP-4 の着手条件を満たす】

**記入は WP-4 の着手条件である** (設計レビュー 1 回目、B-10) — 追補が決めるのは `isolated_application_surface()` の**構成経路**であり、それを実装するのは WP-4 だからである。**Q4 の main マージ後、WP-4 の最初の作業として記入し、監督承認を得てから WP-4 の実装に入る。** WP-8 が持つのは**確定記録**だけである。

**本欄は事実の記録であり、D-6 の決定 (V1 / V2 / V3 の形、駆動集合の導出規則、port v1.11 の 2 項目) を変えない。** 以下はすべて Q4 マージ後の現物 (main `55a7a5a` を取り込んだ作業ツリー) の読み取りであり、**テストは実行していない**。

**(1) 4 plug の構成経路**

| plug | data-plane instance の構成経路 | Q4 後にこの経路が要求するもの | 小さな profile を与える手段 |
|---|---|---|---|
| `r2db-api` (in-process) | service を直接構築 (composition root を通らない) | **無し** | `DataService(..., limits=ResourceLimits(...))` |
| `r2db-api-http` | **data plane は直接構築**、control plane のみ組み立て核 `assemble_control_stack(...)` (明示注入) | **無し** (宣言表の seed も書き手 role 設定も不要) | 同上。HTTP の byte 境界も同じ `ResourceLimits` から出る |
| `MitateDB-api` (in-process) | service を直接構築 | **無し** | `FoundationConfig(...)` の限度フィールド |
| `MitateDB-api-http` | **data plane は直接構築**、control plane のみ composition root `build_control_service(env)` | **control 面を新たに張る場合のみ** platform DB に `0007` 適用 + `surfaces` 行 seed | `FoundationConfig(...)` の限度フィールド + `create_app(request_bytes_limit=...)` を同値にする |

**`r2db-api` (in-process)**。現行は `DataService(self._credentials, control_plane_status="enabled", surfaces=_SURFACES)` (`r2db-api/conformance/conformance_adapter_r2db.py:132`) と `ControlAuthority(self._service)` (`:133`) を直接構築し、`provision_application` は `self._control.register_application(...)` (`:262`) である。cell は `DataService` インスタンスの内部状態であり (`r2db-api/src/r2db_api/structured.py:1095` の `ApplicationCell` は純データクラス)、別インスタンスへ自動的には引き継がれない。**この経路は composition root (`r2db-api/src/r2db_api/main.py:283` の `build_app`) を通らないので、Q4 が入れた廃止 env 拒否・宣言表読み・書き手 role 二重検査のいずれにも触れない。** 小さな profile は `DataService` の第 2 引数 `limits` (`r2db-api/src/r2db_api/service.py:794`、既定は `:828` の `ResourceLimits()`) で与える。`ResourceLimits` は 9 class をフィールドに持ち (`r2db-api/src/r2db_api/limits.py:11-20`)、`__post_init__` (`:22-25`) が正の整数以外を拒む。**env 経路は無い** — r2db に application-plane の限度 env は存在せず、`build_app` の `DataService(...)` 呼び出し (`main.py:457-460`) も `limits=` を渡していない。

**`r2db-api-http`**。**data plane は composition root を通らない** — `DataService(...)` を直接構築し (`r2db-api/conformance/conformance_adapter_r2db_http.py:911-914`)、`create_app(self._service)` (`:917`) で ASGI app を組む。cell は `cell_factory=self._make_cell` (`:912`) が返す実 PG の `PostgresCell` である。**composition root 由来の組み立て核を通るのは control plane だけ**であり、`assemble_control_stack(..., surfaces=_SURFACES)` (`:1062-1088`、`surfaces` は `:1076`、定数は `:737-740`) の明示注入である。Q4 の rework で `assemble_control_stack` は `surfaces` / `audit_visibility_lag_ms` を内部計算しない契約になった (`r2db-api/src/r2db_api/control_main.py:277-284`)。この plug の platform DB には `0008` を当てない (migration 一覧 `:331` 近傍、理由の逐語は `:896-907`)。**したがって隔離 data-plane instance に対して宣言表の行や書き手 role 設定の seed は要求されない** (Q4 §3.11 の 4 / §6.1 γ と同じ結論が data 面にも当てはまる)。
- **`build_app` を使う形を採ると要求が増える** — `main.py:316-317` (廃止 env 4 本の拒否)、`:360-362` (`read_platform_declarations`)、`:366` (F-6)、`:400-403` (`check_writer_role_timeouts`) が必ず走り、かつ `build_app` は `limits` 引数を持たない (`main.py:283` / `:457-460`) ので**小さな profile を与える手段がそもそも無い**。
- 小さな profile は in-process と同じ `limits=` である。**HTTP 面の `request_bytes` も同じ 1 個所から出る** — `create_app` は `RequestByteBoundMiddleware(app, service.limits)` を返す (`r2db-api/src/r2db_api/http.py:475`) ので、宣言と enforcement が同一の `ResourceLimits` を見る。
- application ごとの PG 資産は `_provision_pg_app` (`:365`) が rewrite 済みの `0003_provision_application.sql` (`:331` / `:360`) で作る。Q4 WP-3 でこの `0003` が台帳表 `public._r2db_platform_upgrades` を作り現番号を seed する (`r2db-api/migrations/0003_provision_application.sql:279-290`) ので、隔離 instance が同じ経路で application を作る限り台帳は揃う。**なおこの plug の `_make_cell` は `verify_platform_upgrades_applied()` を呼ばない** — 呼ぶのは composition root の `_cell_factory` (`main.py:434`) だけである。

**`MitateDB-api` (in-process)**。`ControlPlane(pepper, config=FoundationConfig(control_plane_status="enabled", data_base_url=..., control_base_url=...), audit_router=...)` (`MitateDB-api/conformance/conformance_adapter_mitatedb.py:348-363`) と `MitateDataService(self._control)` (`:364`) の直接構築である。cell は `ControlPlane.provision_application` が作り、各 cell は `sqlite3.connect(":memory:")` を 1 本持つ (`MitateDB-api/src/mitatedb_api/backend_sqlite.py:71-72`)。**platform DB も env も読まないので Q4 後の追加要求は無い。** 小さな profile は `FoundationConfig` の限度フィールド — `max_batch_items` / `max_batch_entities` / `max_result_rows` / `max_fields` / `max_filter_terms` / `max_request_bytes` / `max_schema_objects` (`MitateDB-api/src/mitatedb_api/config.py:20-35`) — を構築時に与える。現行 plug は base URL と `control_plane_status` しか渡していないので、いまは全部が既定値である。

**`MitateDB-api-http`**。**data plane は composition root を通らない** — `HttpService(self._gate, _cell_factory, audit_router=self._audit_router)` (`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:700`) と `create_app(self._service, request_bytes_limit=1_048_576)` (`:701`) の直接構築であり、cell も plug 自身が `ApplicationCell(application_id, FoundationConfig(...), backend=PostgresBackend(...), audit_router=...)` (`:891-902`) で組む。**data 面の `surfaces` は `FoundationConfig(data_base_url=..., control_base_url=...)` (`:899`) の明示注入である** — `cell.py:1480` の `_surfaces_document_fragment(config)` が読むのはこの `config` であり、宣言表の値が `config` に入るのは composition root `main.build_app` (`MitateDB-api/src/mitatedb_api/main.py:235` / `:321` / `:377`) の経路だけで、**どの plug もその経路を使っていない**。
- **composition root を通るのは control plane だけである** — `build_control_service(control_env)` (`:767`、`MitateDB-api/src/mitatedb_api/control_composition.py:49`)。**control 面の隔離 instance を張る場合は、fixture の platform DB に (i) `0007_platform_declarations.sql` の適用 (`:276` / `:300`、psql 変数 `api_role` / `controlplane_role` を渡す) と (ii) `surfaces` 行の seed (`:309-322`) が要る** — `build_control_service` が起動時に `read_platform_declarations` (`control_composition.py:123-126`)、`require_control_surface_declared` (`:135`)、`check_writer_role_timeouts` (`:139-142`) を同期で走らせるからである。`0007` は `ALTER ROLE` の 4 文と `audit_writer_roles` / `audit_coalescing_window_ms` の seed を同一トランザクションで持つので、この 1 本で書き手 role 設定も揃う。既存の前例は `isolated_control_surface` が `build_control_service(self._control_env)` を 2 度目に呼ぶ形 (`:1300-1302`) である。
- **data 面だけを新たに張る場合、この seed は要求されない。**
- 小さな profile は `FoundationConfig` の限度フィールド (`config.py:20-35`) である。ただし `request_bytes` は**宣言と enforcement が別引数**である — 宣言は `cell.py:1491` (`config.max_request_bytes`)、enforcement は `create_app(..., request_bytes_limit=...)` (`MitateDB-api/src/mitatedb_api/http.py:954` / `:969`、middleware は `:220-222`) であり、HTTP 面はさらに `limit_enforcement.request_bytes` を `enforced` へ上書きする (`http.py:591`)。product の composition root は `main.py:513` で `request_bytes_limit=config.max_request_bytes` と揃えているので、**隔離 instance でも同じ値にする**。
- application ごとの PG 資産は `0003_provision_application.sql` (`:261`) で作る。`PostgresBackend.__init__` は cell open 時に台帳を検査し、未適用なら F-12 のメッセージを保持して以後の storage 操作をすべて拒む (`MitateDB-api/src/mitatedb_api/backend_postgres.py:419-421` / `:453-478`)。

**(推測)** 隔離 instance が共有 surface と同じ `CredentialStore` / 資格情報を共有するか自前に持つかは、D-6 も本追補も決めていない — 現物からはどちらの形も構成できる。決めるのは WP-4 である。

**(2) `limit_enforcement` / `limits` の出所は Q4 で変わっていない**

- **r2db**: `capabilities()` の `"limits"` / `"limit_enforcement"` は `self.limits.as_dict()` から組む (`r2db-api/src/r2db_api/service.py:936-937`)。`self.limits` は constructor 引数由来である (`:794` / `:828`)。Q4 が `build_app` の `DataService(...)` 呼び出しに入れたのは `surfaces=` と `denial_coalesce_window_s=` であり (`main.py:457-466`)、`limits` は渡していない。
- **MitateDB**: `"limits"` は `config.max_*` から (`MitateDB-api/src/mitatedb_api/cell.py:1481-1493`)、`"limit_enforcement"` は同じブロックの静的な辞書から組む (`:1494-1503`)。`FoundationConfig.from_env` の Q4 改訂は `data_base_url` / `control_base_url` を必須キーワード引数へ移しただけで、7 つの限度 env は据え置きである — 「Every OTHER field below is unaffected -- still read from `environ` exactly as before」(`config.py:100-101`、`names` は `:103-111`)。HTTP 面の `request_bytes: enforced` 上書き (`http.py:591`) も Q4 で触られていない。
- したがって **C-05 の V1 / V2 / V3 が読む宣言の出所は 4 plug とも Q4 前と同一である** (D-6.5 冒頭の「limit class は Q4 の対象外」がそのまま成立している)。

**(3) (e) 資源検査のための計数の手がかり**

- **`r2db-api-http`**: `pg_stat_activity` を login role で数える。同型の既存ヘルパが `r2db-api/tests/test_postgres.py:303-316` (`_live_connections_by_role`) にある。plug 側には admin DSN (`conformance_adapter_r2db_http.py:181` の `_admin_dsn`) と `self._platform` の role/DSN があり、startup sweep が既に `pg_stat_activity` を直接引いている (`:470`)。pool は store 単位 (`pool_size=2`、`:990` / `:1067`)、cell 側は `SharedPoolManager` / `_PoolHandle` (`r2db-api/src/r2db_api/postgres.py:553` / `:672` / `:699`) である。解放の前例は `isolated_control_surface` の `finally` が client を閉じ 4 store を `close()` する形 (`:1793-1816`)。
- **`MitateDB-api-http`**: **cell 1 個につき persistent 接続はちょうど 2 本**である (`MitateDB-api/src/mitatedb_api/backend_postgres.py:404` の docstring と `:419-421`)、解放は `close()` (`:480`)。plug は `cell._backend.close()` を eviction (`:886`) と teardown (`:791`) で呼び、`_MAX_OPEN_CELLS = 6` (`:882`) の上限を持つ。`pg_stat_activity` は plug 自身の sweep が datname 単位で引いている (`:440`)。control 面を張る場合は `build_control_service` が起動検査用に 1 本開いて `finally` で閉じる過渡がある (`control_composition.py:121` / `:155`) 一方、生成される store 群は per-call connection で pool を持たない (`control_composition.py:195-198` の逐語)。
- **`r2db-api` (in-process)**: 数える外部資源が無い。`isolated_control_surface` の逐語が "No real resource to release on exit (in-memory construction only)" (`conformance_adapter_r2db.py:515-516`) と書き、cell は純データクラス (`structured.py:1095`) である。観測できるのは生存 Python オブジェクトの数だけである。
- **`MitateDB-api` (in-process)**: cell 1 個につき `sqlite3.connect(":memory:")` が 1 本 (`backend_sqlite.py:71-72`、`close()` は `:477`)。plug の `close()` は現に no-op である (`conformance_adapter_mitatedb.py:1787-1790`)。**D-6.6 の「in-memory plug は live pool 数」に相当する現物の観測量は、この live な sqlite 接続数である。**

**(4) WP-4 実装担当への構成経路の注意**

- **`r2db-api` (in-process)**: control 側の `isolated_control_surface` は backend / audit / limits を**共有したまま** `ControlPlaneService` を作り直す形 (`conformance_adapter_r2db.py:517-527`) だが、data plane では cell が `DataService` インスタンスの内部状態なので同じ形にはならない — 隔離 instance は自前の `ControlAuthority.register_application` から始める。`limits=` を渡すのは新 `DataService` に対してだけであり、共有 surface の宣言は動かさない。
- **`r2db-api-http`**: **control 側の記述 (composition root・宣言表・書き手 role) を data 側へ写さないこと。** この plug の data plane は `DataService` + `create_app` の直接構築であり、`build_app` を呼ぶと廃止 env 拒否・宣言表読み・書き手 role 二重検査が走るうえ `limits` を注入できない。application を新設するなら既存の `_provision_pg_app` を通す (`0003` が台帳を seed する)。
- **`MitateDB-api` (in-process)**: 新しい `FoundationConfig` で `ControlPlane` + `MitateDataService` を作り直すだけでよい。**Q4 の宣言表・role 設定はこの経路に一切現れない。**
- **`MitateDB-api-http`**: **seed が要るのは control 面を新たに張るときだけである** — `build_control_service` が composition root だからであり (Q4 §6.1 α)、data 面の隔離 instance は `ApplicationCell` + `FoundationConfig` の明示注入で宣言表を読まない。`request_bytes` を小さくするなら `FoundationConfig.max_request_bytes` と `create_app(request_bytes_limit=...)` を**同時に**動かす (片方だけでは宣言と enforcement が食い違う)。

#### D-6.6 (e) L6-13 — 隔離 surface の資源検査

`isolated_control_surface()` / `isolated_application_surface()` について、**呼び出しの前後で資源が戻ることを assert する** — PG plug は `pg_stat_activity` の件数、in-memory plug は live pool 数。**同一 WP で行う** (WP-4)。**【監督注記 2026-09-06】in-memory plug に「pool」は現物に無い — r2db in-process は資源ゼロ、MitateDB in-process は cell ごとの `sqlite3.connect(":memory:")` 1 本 (`backend_sqlite.py:71-72`)。計数対象は「live sqlite 接続数 / 生存オブジェクト数」と読み替える (追補 (3))。close 撤去の変異が効く対象は plug ごとに異なる (r2db HTTP = store の pool、MitateDB HTTP = cell の persistent 接続)。**

**変異**: context manager の close を外す → 件数が戻らず赤。

#### D-6.7 他 5 条件

**port 変更を要さないものを 1 WP (WP-5) にまとめる。**

| 条件 | 共通 suite で固定する命題 |
|---|---|
| **C-04** | unsupported operation が **`CAPABILITY_UNSUPPORTED` で実行前に**返ること + **誤入力の error body に stack trace / SQL 断片 / DSN 形が無いこと** (負の内容検査) |
| **C-10** | **adapter 境界水準**: 応答に credential-bearing 文字列・DSN 形・環境変数の値が無いこと。**走査機構は conftest 側に置く** (下記)。PG 権限の peer-local 証拠は**参照のまま**とし、**射程を `CONDITIONS.md` に開示する** |
| **C-02** | **runtime credential** による schema 操作 / control 操作が拒否されること |
| **C-07** | **(i) 原子性**: 単一 entity の batch に無効 item を 1 つ混ぜ、**全部ロールバック**する (書き込み 0 件を read で確認。**4 plug 全数**)。**(ii) idempotency**: C-17 型の**宣言分岐** (下記) |
| **C-00** | application credential が **control surface / 他 application** で拒否されること。**C-01 / C-14 が既に固定している部分は参照し、欠けている vector だけ足す** |

**C-10 の走査機構は conftest 側に置く** (設計レビュー 1 回目、B-6)。**adapter の公開メソッドを generic proxy で包み、戻り値と error payload を JSON 直列化して走査する fixture** を `conformance-tests/conftest.py` 側に置く。**port は増やさない** — §7.1 の追加項は 2 のままである。**in-process の 2 plug にも効く**のがこの形の利点であり、同時に「**wire**」という語が in-process plug に対して意味を持たない (wire が無い) 問題も解ける。**開示文では「adapter 境界水準」または「plug が返す応答の全内容」と書き、「wire 水準」とは書かない** (§7.3、L7-7)。**射程は「各 worker が観測した応答の範囲」である** — `-n 5 --dist loadgroup` では plug ごとに worker が分かれるので、「suite 全体を 1 プロセスで集約する」形にはならない。この射程も C-10 行に開示する。

**Status は 5 条件とも `executable (common suite)` へ変える。射程の限界は各行に開示する。** §1.6 の 2 のとおり、**Status の更新はテスト追加と同一コミットである**。

**C-07 (ii) idempotency の宣言分岐** (裁定 S-4): 両 peer とも `idempotency: unavailable` を宣言し、`idempotency_key` を `CAPABILITY_UNSUPPORTED` で実行前に拒否する (§1.6 の 5)。したがって C-05 と同じ「**宣言で分岐し、非 enabled 側は skip せず宣言の正直さを assert する**」形 (C-17 型) を採る。

- **`idempotency` が `unavailable` の plug**: 「**`idempotency_key` 付きの要求が実行前に `CAPABILITY_UNSUPPORTED` で拒否され、副作用が 0 件である**」ことを assert する。**skip しない。** 副作用 0 件は (i) と同じ read で確認する。
- **`unavailable` 以外を宣言する plug**: 「**同一 key の再送が同一結果を返す**」ことを assert する。
- **空振り防止は per-plug の非空性 assert で行う** (設計レビュー 1 回目、B-8)。**各 plug について、宣言分岐のどちらか一方の枝が必ず実際に観測されたことを、その plug のテスト内で assert する。** 前例は **C-17 の per-plug 非空性 assert** (`conformance-tests/test_c17_declaration_agreement.py:182-218`) である。**session 横断の集約 guard は採らない** — `-n 5 --dist loadgroup` では plug ごとに worker が分かれるので、「観測対象が 1 plug 以上あること」を全体で数える形は成立しない。**現時点では 4 plug すべてが `unavailable` 枝で観測される** — 肯定側が空であること自体は guard を破らないが、**ある plug でどちらの枝も観測されなければその plug で赤になる**。この形は L7-8 の穴 (肯定側が空である) を**空振りのまま放置しない**ための機構である。

port v1.11 が足すのは「**adapter が `idempotency_key` を実リクエストに載せる経路**」だけであり、declare-first の分岐そのものではない。**肯定側の primitive (key の生成・保管・再送の共通機構) は足さない** — 実装が現れたときに足す (L7-8)。

#### D-6.8 (d) L6-17 — r2db の `surfaces` 検証ヘルパ

`main.py` / `control_main.py` の 2 コピーを **1 モジュールへ寄せ、同型性の対応表に行を足す**。**Q4 WP-B が同じ composition root を触る**ので **7-B に置く** (WP-5)。

#### D-6.9 (c) 実ソケット HTTP plug — 本フェーズには含めない

**理由**: CI (D-3) が**実サーバ起動の場を初めて作る**。その後に conformance 構成 (5・6 番目の plug) の設計として独立に扱うのが順序として正しい。**公開ゲートの条件ではない。** 台帳 **L7-2** に理由付きで残す。

#### D-6.10 SI への影響

**SI-08 (Bounded Resource Consumption) の共通証拠を初めて executable にする。** 新 invariant は不要である (§8)。

#### D-6.11 変異

- **V1 (a)**: いずれかの plug の `limit_enforcement` に `limits.classes` 外のキー (例: 合成名 `not_a_class`) を一時的に足す → 語彙外として赤 (指示書起草者の指摘 4 に対する監督追加、2026-09-05)。
- **V1 (e)**: MitateDB の `limit_enforcement` から固定 9 のうち 1 class を一時的に落とす → 欠落として赤。
- **V1 (b)**: `limits` に値だけがあって `limit_enforcement` にエントリが無い class を一時的に作る → 赤。
- **V1 (c)**: `enforced` のエントリから対応する `limits` の値を落とす (または 0 にする) → 赤。
- **V1 (d) の非変異**: MitateDB in-process の `request_bytes` を「値あり + `unavailable`」のまま走らせる → **緑であること**を確認する。**これは変異ではなく、撤回した規則が復活していないことの確認である** (裁定 S-1)。
- **V2**: 宣言値 N を +1 して実挙動と食い違わせる → **両側検査の class で位置がずれて赤**。`details.limit_class` を別名にする → 赤 (両側・片側の両方で効く)。in-process 面の `request_bytes` を `enforced` と偽る → **駆動集合に入り、片側検査の「明らかな超過が拒否される」が成立せず赤**になる (V2 の交差規則が偽の宣言を捕まえる形である)。
- **V2 の per-plug 非空性**: ある plug の宣言を全 class `unavailable` に倒す → **駆動 class 0 で赤** (静かに緑にならないことの確認)。
- **V2 の headroom 前提**: 隔離 profile の `requests_per_minute` を、他 class の駆動が消費する最悪ケースを下回る値に設定する → **headroom の前提 assert が赤**。
- **V3**: MitateDB の 1 class を `unavailable` から `enforced` へ上げる (= L7-1 の実装が入った状態を模す) → その class の xfail が XPASS → `strict=True` で赤 (**これが撤去の合図である**)。逆に **`unavailable` の明示宣言を足すだけでは XPASS しない**ことも確認する。
- **(e)**: 隔離 surface の close を外す → 資源が戻らず赤。
- **C-04 / C-10**: 応答に DSN 形の文字列を 1 つ混ぜる → 負の内容検査が赤。

### D-7 (i) 現行結論と履歴の分離 (裁定 4)

**元ファイルの各行の形**: 「**現行の担保 (短文) + 証拠 (テスト名・`file:line`) + `[history](CONTROL_MAPPING_HISTORY.md#si-10)` 形のリンク**」。

**列構造は維持する** — `CONDITIONS.md` は `ID` / `Condition` / `Invariants` / `Evidence` / `Status` の 5 列 (`test_conditions_register.py` が `ID` と `Status` を読む)、`CONTROL_MAPPING.md` は 4 列 (解析コードは 0 件だが**列は維持する**)。§1.6 の 1 のとおり、**セル内に生の `|` を置かず、1 行 1 レコードを保つ**。

**companion**: `security/CONTROL_MAPPING_HISTORY.md` / `conformance-tests/CONDITIONS_HISTORY.md`。**見出しは ID のみとし、タイトルを付けない** — `## SI-10` / `## C-19` 型である (GitHub の自動アンカーは `#si-10` / `#c-19`)。**前例の `security/SECURITY_INVARIANTS_V1.md` は `### SI-XX — <タイトル>` 形だが** (§1.6 の 4)、**その形に倣うと slug が `#si-10--…` になり、元ファイルから張ったリンクが解決しない** (設計レビュー 1 回目、C-2)。**倣うのは「ID 単位の Markdown 見出しを使う」という点までであり、タイトルは付けない。** **履歴本文は逐語で移す — 書き換えない** (監査履歴としての価値がある)。

**仕分け基準 (人手。機械化不能)**:

- **現行** = 今日の code / tests の状態、および**開示された射程の限界**
- **履歴** = 置換された主張、訂正の経緯、WP 進捗注記、日付付きの状態注記

**機械化できない理由は実測に基づく**: 日付 / WP マーカーは「**変更があった**」印であって「**もう真ではない**」印ではない。C-19 行の Honest limits (a)〜(e) は**日付マーカーの後ろにあるが現在も有効な制約**であり、日付で機械的に切ると現行の制約を履歴側へ落としてしまう。**レビューは「現行行から落ちた制約が無いか」を独立項目で突合する。**

**更新規約** (両ファイルの冒頭に置く。裁定 4 の文言): 「**訂正は現行行を書き換え、旧文は履歴へ移す**」。**規約は表の外の前文に散文で書く** (設計レビュー 1 回目、C-1) — `test_conditions_register.py:32` は `|` で始まる行を**すべて 1 つの表**とみなし `[0]` を header、`[1]` を divider として扱うので、**規約を表で書くと parser が壊れる** (先頭に置けば header 検出が失敗し、後ろに置けば見出し行が bogus な condition id のデータ行になる)。**`CONDITIONS.md` は `|` 始まりの表を 1 つだけ持つ**、という制約を D-7 の決定として明記する。

**機械固定**: `conformance-tests/test_conditions_register.py` を拡張し、**`conformance-tests/test_control_mapping_register.py` を新設する**。

1. 各 ID 行が companion の該当 anchor へのリンクを持つ
2. **リンク断片と等しい slug の見出しが companion にある** — 「見出しがある」ではなく**アンカーが解決すること**を検査する (slug 化規則をテスト側に持たせる。C-2)
3. **`ID` 列に重複が無い** — 現行 parser は `result[cid] = status` で**同一 ID の重複行を黙って上書きする**ので、1 ID を複数行に割ると Status 検査が最後の行だけを見る形で壊れる (設計レビュー 1 回目、B-12)
4. **主表の各セルの長さ上限** — **行全体ではなくセル単位**に掛ける (`CONDITIONS.md` の 5 列、`CONTROL_MAPPING.md` の 4 列のいずれにも)。**確定値は実装 WP が仕分け後の最長セルから決めて本設計に記録する。目安は 2,500 文字である**

**上限を 2,500 目安とする根拠は実測である** (設計レビュー 1 回目、B-12): `CONDITIONS.md` の **Condition 列だけで C-17 が 1,788 文字**あり (C-18 = 1,138、C-19 = 1,071)、**Condition 列は条件の定義文であって履歴を 1 文字も含まない**。上限を 1,500 に置くと、**仕分けをどれだけ完璧にやっても C-17 は上限を割れない** — 実装担当は条件定義文を削る (= 担保内容の変更であり D-7 の「内容は変えない」に反する) か、1 ID を複数行に割る (= 上記 3 の壊れ方) かに追い込まれる。**目安は下限の目安であり、仕分け後の実測が上回るなら上げる。**

これで**蓄積の再発を機械的に止める**。

**却下した代替案**:
- **同一ファイル内の別セクションへ移す** — 1 ファイルの総量 (142,732 文字 / 83,418 文字) が減らず、読み手の抽出コストの問題が解けない。
- **履歴を捨てる** — 裁定 4 が「履歴は捨てない」を確定している。
- **日付マーカーによる自動仕分け** — 上記の理由で不可能である (C-19 が反例)。

**SI への影響**: **形式のみ**である。担保の**内容は変えない**。

**変異**: 上限を超える**セル**を 1 つ作る → 赤。companion から見出しを 1 つ落とす → **アンカーが解決せず**赤。同一 ID の行を 2 本置く → **ID 重複 assert が赤** (現行 parser の silent overwrite を塞いだことの確認)。

---

## 4. 却下した代替案の一覧

| # | 代替案 | 却下理由 | 出所 |
|---|---|---|---|
| 1 | 別リポジトリへの新規公開 | 裁定 2 が単一リポジトリ維持を確定。**§6 (γ) 案 1 の「同名リポジトリの delete + 再作成」はこれとは別物である** (識別は 1 つのまま、remote の object store だけが変わる。**2026-09-05 に案 1 で確定**) | D-1 |
| 2 | BFG Repo-Cleaner | 機構は同等だが、hash 一括更新が filter-repo の commit-map 形式を前提にしている | D-1 |
| 3 | 実値を含む 6 commit だけを squash | 履歴の連続性と他文書の hash 参照を**より多く**壊す | D-1 |
| 4 | 既製 secret scanner (gitleaks 等) の導入 | 対象は secret ではなく運用固有識別子であり規則集が合わない。pre-commit に外部リポジトリ依存を持ち込む | D-2 |
| 5 | `uv.lock` / `pip-tools` / `poetry` | 追加ツール依存。両 peer が library 形式の下限 pin を保つ方針と二重管理になる | D-3 |
| 6 | `ignore::StarletteDeprecationWarning` の一括 ignore | 警告を消すのではなく**原因を消す**。ignore は「error 化した」という主張を空にする | D-4 |
| 7 | 配備資産を実機から回収する | **実値を持ち込む経路**になり D-1 の規律に反する。運用者作業への依存も増える | D-5 |
| 8 | (c) 実ソケット HTTP plug を本フェーズに含める | CI が実サーバ起動の場を作った後に扱うのが順序として正しい。公開ゲートの条件ではない | D-6.9 |
| 9 | 履歴を同一ファイルの別セクションへ移す | 総量が減らず、抽出コストの問題が解けない | D-7 |
| 10 | 履歴を捨てる | 裁定 4 が「履歴は捨てない」を確定 | D-7 |
| 11 | 日付 / WP マーカーによる自動仕分け | マーカーは「変更があった」印であり「もう真ではない」印ではない (C-19 の Honest limits が反例) | D-7 |

---

## 5. 依頼者裁定

**本節は依頼者裁定を逐語で記録したものであり、再審議しない。**

> 依頼者裁定 (2026-09-05 確定。Fable 推奨を「将来的に有利な方向」の重み付けで採用。設計文書の §裁定 に逐語で記録し、再審議しない):
>
>   裁定 1 (g) 公開を計画する。時期はフェーズ7 の (g)(b) 完了を明示ゲートとし、それまでは private のまま公開可能性を維持する。
>   裁定 2 (g) 単一リポジトリを維持し、git filter-repo --replace-text で全履歴の実値を placeholder へ置換する (置換表は
>         リポジトリ外の運用者記録にある既存の対応表を使う。設計文書にはその存在だけを書き、内容は書かない)。
>         書換で変わる commit hash は設計文書・引き継ぎ・台帳が多数引用しているので、filter-repo の commit-map で
>         文書内の hash 参照を一括更新する手順を作業指示書の WP に含める。全 clone・worktree の作り直し、
>         有効 credential 2 件 (r2db control / runtime) の revoke + 再発行 (rotate は id を保持するため不可) を同じゲートに置く。
>   裁定 3 (a) C-05 はフェーズ7 では「宣言と実挙動の一致」の検証までとし、MitateDB application plane の
>         execution-time / concurrency / request-rate の実装は独立フェーズ候補として最優先で起票する (順序付けであり先送りではない。
>         検証を先に入れることで欠落を fail-loud にする)。
>   裁定 4 (i) 現行結論は元ファイル (CONTROL_MAPPING.md / CONDITIONS.md) に短い行として残し、履歴は文書ごとの companion ファイル
>         1 本 (security/CONTROL_MAPPING_HISTORY.md / conformance-tests/CONDITIONS_HISTORY.md) へ項目別アンカーで移し、各行から
>         アンカーへリンクする。更新規約「訂正は現行行を書き換え、旧文は履歴へ移す」を同時に置く。
>   上記以外に依頼者判断が新たに要る点が出たら、両論併記で提示して確定を待つ (勝手に確定しない)。

**以上について再審議しない。**

---

## 6. 依頼者裁定 ((α)(β)(γ)、2026-09-05 に確定)

**本節の 3 点は依頼者裁定で確定した。裁定文は逐語で置き、両論は経緯として残す。**

**【依頼者裁定 2026-09-05】**

> (α)(β)(γ) は監督案どおり確定。7-A を前倒しで着手してください。

**帰結の一覧**: **(α)** CI の Python matrix は 3.11 と 3.12 の**両方を required** とし、**完了ゲートの正本は 3.11 job の集計行**である (3.12 job は同一集計行であることを required で担保する)。**(β)** MitateDB の欠落 4 class への明示エントリ追加は **7-B WP-4 に置く** (宣言と検証を同一コミットに)。**(γ)** **案 1** — 同名リポジトリを delete し、書換後の履歴だけを push して再作成する。**あわせて 7-A (WP-1 / WP-2 / WP-3) の前倒し着手が確定した** (§12)。

### (α) CI の Python matrix に 3.12 を required とするか、informative に留めるか

**【依頼者裁定 2026-09-05】監督案を採用: CI の Python matrix は 3.11 と 3.12 の両方を required とする。完了ゲートの正本は 3.11 job の集計行 (集計行の記録環境) であり、3.12 job は同一集計行であることを required で担保する。**

**帰結**: `.github/workflows/ci.yml` は 3.11 / 3.12 の 2 job を定義し、**どちらも required** である (D-3)。「以後の完了ゲートは CI の集計行を正本の記録に引く」(D-3) の**正本は 3.11 job の集計行**であり、**3.12 job が担うのは「同一の集計行であること」の担保**である — 食い違えば 3.12 job が赤になる。 **(監督注記 2026-09-05、WP-2 受理時)**: 実装ではこの担保を**別 job `tally-consistency`** が担い、両 job の 4 数 (passed / failed / skipped / xfailed) を比較して食い違えばその job が赤になる。「同一の集計行」とは**この 4 数の同一**を指し、経過秒を含む逐語一致ではない (WP-2 監査の疑義 A・B に対する判定)。**したがって正本の集計行は 1 本のままであり、「2 環境の集計行のどちらを引くか」という曖昧さは生じない** (L7-6 の射程はこれで狭まる)。

**経緯 (両論。裁定前の記述をそのまま残す)**

- **required とする案 (監督案)**: 3.11 は集計行の記録環境と MitateDB のコンテナ基底 (`python:3.11-slim`)、3.12 は r2db の VPS 実行環境 (実測 3.12.3 のみ) である (§1.6 の 6)。**実際に走る 2 環境をどちらも証拠にする**方が、「共通証拠」という本フェーズの目的に合う。両 peer の `requires-python` は `>=3.11` であり、3.12 で赤が出れば**それは実配備で起きる不具合**である。
- **informative に留める案**: 3.12 の赤が上流依存の一時的な非互換に起因する場合、**公開ゲート (D-1 (iv)) が上流の都合で止まる**。required は「集計行 = 1 つ」という現行の完了ゲートの単純さを崩し、2 環境の集計行が食い違ったときの正本を決める必要が生じる。
- **どちらを採っても影響する箇所**: `.github/workflows/ci.yml` の `matrix` と `required` 設定、および「以後の完了ゲートは CI の集計行を正本の記録に引く」(D-3) の**正本の定義**。

### (β) MitateDB の 4 class に明示エントリを足す変更を、7-B WP-4 に置くか、宣言だけ先に 7-A へ出すか

**【依頼者裁定 2026-09-05】監督案を採用: MitateDB の欠落 4 class への明示エントリ追加は 7-B WP-4 に置く (宣言と検証を同一コミットに)。**

**帰結**: 当該の宣言追加は **WP-4 の成果物のまま**であり、**7-A へ先出ししない** (§10)。`MitateDB-api/src/mitatedb_api/cell.py` の `limit_enforcement` ブロックへの追加と、それを測る C-05 の V1 (e) が**同一コミットに載る**。**`operation_depth` の値 (`enforced` か `unavailable` か) を実測で決める工程は WP-4 に残る** (D-6.1 の二枝)。

**対象は MitateDB の固定 9 のうち欠落している 4 class** (`execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth`) **のみである** (裁定 S-2)。**r2db 側は 9 class を宣言済みで、`cross_entity_mutation` / `idempotency` がいずれも `unavailable` なので条件付き 3 class は適用外であり、無変更で V1 (e) を満たす** — したがって本論点は MitateDB 1 peer の話に閉じる。

**経緯 (両論。裁定前の記述をそのまま残す)**

- **WP-4 に置く案 (監督案)**: **宣言と検証を同一コミットに載せる**。宣言の追加は V1 (e) の欠落を埋める変更であり、**V1 を先に入れて宣言を後にすると 7-A の期間ずっと V1 が赤**になる。逆に宣言を先に入れると **V1 が測る前に事実だけが動く**。フェーズ6 の全体 vacuity guard と同じ扱いである。なお **V3 の xfail は宣言追加では XPASS しない** (`unavailable` である限り落ち続ける) ので、xfail の先置きは同一 WP に同居できる (D-6.1)。
- **7-A へ先出しする案**: 宣言の追加は peer-local かつ契約無変更であり、Q4 と触るファイルが重ならない (`cell.py` の宣言ブロックは Q4 の対象外)。**公開ゲートは (g)(b) の完了で開く**ので、宣言だけでも先に正直になっていた方が、公開時点のクライアントに対する誠実さは上がる。
- **どちらを採っても変わらない点**: 宣言の置き場は `MitateDB-api/src/mitatedb_api/cell.py` の `limit_enforcement` ブロック (`:1494-1504`) である (D-6.1)。また **`operation_depth` の値 (`enforced` か `unavailable` か) は実測で決まる**ので、どちらの案でも**実装担当が事実を確かめる工程は WP に残る** (D-6.1)。

### (γ) force push 後も GitHub 側に残る unreachable object への対処

**【依頼者裁定 2026-09-05】監督案を採用: 案 1 — 同名リポジトリを delete し、書換後の履歴だけを push して再作成する。裁定 2 の「単一リポジトリを維持する」は識別 (owner / 名前 / 単一の正本) の維持と読む。**

**帰結**: **D-1 (iv) の (4) は「force push」から「同名リポジトリの delete + 書換後履歴のみ push + 再作成」に変わり、(5) の clone 取得元は再作成後の remote になる**。**§9 の手順表も手順 3・4 が同じ形になる** (手順 3 = delete + 再作成 + push、手順 4 = 再作成後の remote からの新規 clone)。**§10 WP-9 の着手条件から「§6 (γ) の確定」は外れる** — 確定済みだからである。**L7-13 は閉じた** (§11)。**残留対処が未確定であることを理由に公開を止める阻却事由は無くなった。**

**経緯 (両論。裁定前の記述をそのまま残す)**

**論点** (設計レビュー 1 回目、A-4): 履歴を `git filter-repo` で書き換えて force push しても、**GitHub 側には旧 commit が unreachable object として残り得る** — **SHA を直接指定すれば取得できる**状態である (PR ref / fork / cached diff view があれば露出はさらに増える)。**private → public の切替は、その残留オブジェクトを公衆に開くことを意味する。** D-1 (iv) の「履歴の実値を消す」という主張は、この対処を決めない限り **remote 側で担保されない**。**本設計はこれを確定しない** — 依頼者判断が要る点として両論で残す。

- **案 1 (監督案): 同名リポジトリを delete し、書換後の履歴だけを push して再作成する。**
  - **確実であり、自前で完結する** — remote の object store 自体が新しくなるので、旧 object は存在しない。
  - **失うもの**: issue / PR / star / watch / fork 関係などの付帯物。**本リポジトリは単独作業者であり、付帯物はほぼ無い**ので損失は小さい。
  - **裁定 2 との関係**: 裁定 2 の「単一リポジトリを維持する」は**リポジトリの識別 (同一の owner / 名前 / 単一の正本) の維持**であって、**remote の object store の同一性の維持ではない**、という読みを採る。**この読みが妥当かどうかが依頼者判断の対象である。**
- **案 2: GitHub Support に unreachable object の purge を依頼する。**
  - **付帯物を失わない。**
  - **時間が読めず、結果も確実ではない** — 依頼が通るか、いつ完了するかを自分で制御できない。**公開ゲート (D-1 (iv)) の完了が外部の応答待ちになる。**
- **どちらを採っても影響する箇所**: **§9 の手順表** (案 1 なら手順 3 の force push が「delete + 再作成 + push」に置き換わる)、**D-1 (iv) の (4)(5)**、および**手順 4 の履歴スキャンの対象クローンの取得元**。**なお、どちらを採らないという選択肢 (残留を許容して公開する) も形式上はあり得るが、D-1 の目的 (履歴の実値を消す) と両立しないので監督案には採らない。**

---

## 7. conformance への影響

### 7.1 port v1.11

`conformance-tests/adapter.py` を **v1.11** へ上げる。追加は 2 項目であり、**削除は無い**。

1. **`isolated_application_surface()`** (D-6.1 V2) — 使い捨ての data-plane instance を張る context manager。**独自の窓・カウンタを持ち、小さな conformance profile を宣言する**。**yield するのは port 準拠の adapter instance** — その新 service に束縛した**同型の adapter** (自己相似) であり、テストは**通常の port 操作でそれを叩く**。成功時は実応答、拒否時は `ConformanceDenial` という規約は既存 port と同じである。**その instance の `capabilities()` が返す宣言と、検証対象が同一であること**が本 primitive の存在理由である。**`isolated_control_surface()` (`conformance-tests/adapter.py:1211-1226`) が yield する単一 callable とは形が異なる** — control 側は駆動 class が `control_requests_per_minute` 1 つに閉じているから単一 callable で足りるが、application plane は行の投入・entity の作成・batch mutation・query・`capabilities()` の読み出しを要するので、単一 callable では構成できない (設計レビュー 1 回目、B-5)。**必要な操作は D-6.2 の駆動レシピから逆算する。** **テスト終了時に close する** (D-6.6 の資源検査が測る)。**port の面積が「1 メソッドの追加」ではなく「adapter instance を返す」形になる点は、明示の決定である** — 駆動レシピごとに場当たりのメソッドを足すより面積が小さく、隔離の目的も保たれる。
2. **`idempotency_key` を運ぶ optional フィールド** (D-6.7 C-07) — 現行 port には対応物が無い (§1.6 の 5)。**追加するのはこの optional フィールド 1 つだけであり、それ以上は足さない** (裁定 S-4)。**既存メソッドへの任意引数として足すか、`BatchOperation` / `ScopedBatchOperation` に optional フィールドを足すかは作業指示書で確定する**。本設計が決めるのは「**共通 suite が、adapter の加工なしに `idempotency_key` を実リクエストへ載せられること**」までである。
   - **追加の目的は「`unavailable` 枝の拒否を実際に叩くこと」に限られる。** 現時点でこの経路が運ぶ key は**必ず `CAPABILITY_UNSUPPORTED` で実行前に拒否される**ので、port が知る必要があるのは「key を載せられる」ことだけである。
   - **肯定側の primitive は足さない** — 同一 key の保管・再送・結果比較を支える機構は、**`idempotency` を `unavailable` 以外で宣言する実装が現れたときに足す** (L7-8)。今足すと、**動かす対象が無いまま port の面積だけが増える**。

`docs/design/CONFORMANCE_ADAPTER_V1.md` に **§21 (v1.11)** を新設して記録する (§20 = v1.10 と同じ構成: 追加メソッドの意味論 / 既存機構との関係 / 互換性影響)。**文書情報の版数行も更新する。**

### 7.2 新規テストファイル

| ファイル | 条件 | WP |
|---|---|---|
| `conformance-tests/test_c05_limit_declaration_agreement.py` | C-05 | WP-4 |
| `conformance-tests/test_c04_unsupported_and_safe_errors.py` | C-04 | WP-5 |
| `conformance-tests/test_c10_no_bypass_material_on_the_wire.py` | C-10 | WP-5 |
| `conformance-tests/test_c02_runtime_privilege_negative.py` | C-02 | WP-5 |
| `conformance-tests/test_c07_atomicity_and_retry.py` | C-07 | WP-5 |
| `conformance-tests/test_c00_application_escape.py` | C-00 | WP-5 |
| `conformance-tests/test_control_mapping_register.py` | (機械固定。条件 ID を持たない) | WP-7 |

**ファイル名は素案である** — 既存の `test_c<NN>_<主題>.py` 命名に揃えることだけが確定事項であり、主題語は作業指示書で確定する。

### 7.3 `CONDITIONS.md` の Status 変更

**C-00 / C-02 / C-04 / C-05 / C-07 / C-10 の 6 行を `not yet executable (common suite) -- peer-local evidence only` から `executable (four adapters) -- …` へ変える。**

- §1.6 の 2 のとおり、**`@pytest.mark.condition(...)` を付けた瞬間に Status が `executable` で始まっていなければ赤になる**ので、**各行の Status 更新は当該テストの追加と同一コミットである**。
- 各行に**射程の限界を開示する**。**C-05 行に開示する事項は 5 つある** — **(1)** 「駆動しない」3 class とその理由 (D-6.2)、**(2)** **片側検査に落とした 3 class とその理由、および片側検査が「宣言値 N が正しいこと」を測っていないこと** (D-6.2)、**(3)** **`enforced` と宣言されているが検査形が無く駆動集合から外れる class** (起草時点では r2db 2 plug の `concurrency`) とその理由 (D-6.1 V2)、**(4)** **`unavailable` を宣言する class は駆動されず、V1 の整合検査と V3 の fail-loud だけが掛かること** (D-6.1)、**(5)** **V1 (e) の必須エントリ集合は契約の義務ではなく共通 suite が SI-08 の証拠として課す追加要件であり、契約 1.6.0 に準拠しつつ (e) を満たさない実装はあり得ること** (D-6.1)。**C-10 行**は「**adapter 境界水準**であり、射程は各 worker が観測した応答の範囲、PG 権限の証拠は peer-local 参照のまま」。**C-07 行**は「両 peer とも `idempotency: unavailable` であり、共通 suite が測るのは**実行前拒否と副作用 0 件**であって、**再送同一結果の肯定側は現時点で空である**こと」。
- **C-19 行・C-14 行・C-16 行**には、C-05 との重なりの参照を足す (D-6.4)。

### 7.4 xfail の件数と撤去条件

| xfail | 件数 | 撤去条件 |
|---|---|---|
| C-05 V3 (固定 9 のうち `unavailable` を宣言する class ごとに 1 本) | **`MitateDB-api` (in-process) 4 または 5 本 + `MitateDB-api-http` 3 または 4 本 = 7 または 9** (in-process の 1 本は `request_bytes`、D-6.1 V3) | **L7-1 の実装が入ったコミットと同一コミットで、当該 class の分を撤去する。** `strict=True` なので、実装が入って宣言が `unavailable` 以外へ上がれば XPASS → 赤になり、撤去を強制する |

**件数が 7 か 9 かは `operation_depth` の実測で決まる** (D-6.1) — MitateDB が入れ子深さを実際に有限で拒否していれば `enforced` を宣言して V2 の駆動対象になり **7 本** (HTTP 3 + in-process 4、in-process の 1 本は `request_bytes`)、していなければ `unavailable` を宣言して 4 番目の class として **9 本**になる。**確定値は WP-4 が実測して §13 に記録する。**

**本フェーズが増やす xfail はこれだけである。** 完了ゲートの集計行は `xfailed 7` または `xfailed 9` (既存分があればその合算) **【監督注記 2026-09-06】7-B 着手時点 (main `8b0e247`) の既存 xfail は 0 — Q4 WP-3 が WP-0 の strict xfail 4 本を撤去済み。したがって 7-B の完了ゲートの xfailed は本フェーズの 9 本のみである (L7-17 の状態注記も参照)。** を明示する。**skipped は 0 のままである** — 非 enabled 側は skip せず、宣言の正直さを assert する (D-6.1 / D-6.7 の C-07)。

### 7.5 `CONFORMANCE_ADAPTER_V1.md` の改訂

- **§21 (v1.11) の新設** (7.1)
- **文書情報の版数行の更新** (現行は 1.8。§20 追記時の慣行に倣い、port 改訂に合わせて上げる)
- **§9 完了条件**への追記は行わない (本フェーズは port の完了条件の形を変えない)

### 7.6 conformance 構成への影響

- **plug は増えない** (4 plug のまま)。(c) 実ソケット plug は本フェーズの範囲外である (D-6.9)。
- **`conformance-tests/README.md` に実 PG の要件を明文化する** (D-3) — superuser 相当の DSN、`max_connections=300`、`-n 5 --dist loadgroup`。既存 :110-123 の「PostgreSQL が届かないことを silently な被覆欠落にしない」という記述の直後に置く。

---

## 8. Security Invariants との関係

**新しい共通 Security Invariant は足さない** (制約 C2)。本フェーズが導入する要素はいずれも既存の invariant に載る。**Security Invariants は capability の許可リストではなく、守るべき安全成果の集合である** — 本フェーズは新しい安全成果を導入せず、**既存の安全成果を再現可能かつ機械検証可能にする**ものである。

| 決定 | 載る invariant | 根拠 |
|---|---|---|
| **D-1** 公開規律と公開前ゲート | **SI-10** | credential_id の露出は認証を破らないが、「未知 id と有効 id を応答で区別させない」性質を**攻撃者に対して部分的に無効化する** (標的を名指しできる)。だから**公開時に id を変える**。invariant の**内容は変わらない** — 変わるのは、その性質を保つために公開前に何をするかである |
| **D-2** 実値パターンの機械検査 | **SI-10** (同上) | 既存の公開規律を機械化するだけであり、新しい境界も新しい主張も作らない |
| **D-3** constraints と CI | **なし (SI 中立)** | 証拠の取得環境を固定する作業である。**どの invariant の内容も変えない**。CI が測るのは既存の SI に紐づく既存の conformance 条件である |
| **D-4** DeprecationWarning の error 化 | **なし (SI 中立)** | 同上 |
| **D-5** r2db 配備資産 | **SI-02** | **分離プロセス構成 (control plane を別 unit・別 listen address で動かす) を再現可能にするだけ**であり、**新しい境界は作らない**。既存の SI-02 の担保を、文章指示からテンプレートへ移す |
| **D-6** 6 条件の共通化 | **SI-08** (主)、**SI-02 / SI-03** (C-02)、**SI-05 / SI-10 / SI-15** (C-04)、**SI-11** (C-07)、**SI-12** (C-10)、**SI-00 / SI-02 / SI-07** (C-00) | **SI-08 の「有限で発見可能な境界」の共通証拠を初めて executable にする**。他 5 条件も、`CONDITIONS.md` が既に各行に記載している invariant 対応をそのまま使う — **新しい対応も新しい invariant も作らない** |
| **D-7** 現行結論と履歴の分離 | **なし (形式のみ)** | **担保の内容は変えない**。`CONTROL_MAPPING.md` は SI と実装統制の対応表であり、その**表示形式**を変えるだけである。**「現行行から落ちた制約が無いか」の突合をレビューの独立項目に置く**ことで、形式変更が内容変更に化けないようにする |

**SI-08 について 1 点明記する**: SI-08 は「Resource classes to bound **where applicable**」と書き、「Limits may be enforced by application code, reverse proxy, platform controls, database controls, or a combination」という実装自由度を明示している。**したがって MitateDB が `execution_ms` / `concurrency` / `requests_per_minute` (および実測次第で `operation_depth`) を実装していないこと自体は、SI-08 の違反ではない** — 違反になるのは、**その状態を宣言が正直に表していないとき**である。D-6 が閉じるのはこの隙間であり、**実装そのものは L7-1 の次フェーズ候補である** (裁定 3: 順序付けであり先送りではない)。**同じ理由で、「値は公開するが enforcement 層が無い」形の宣言 (`limits` に値 + `limit_enforcement: unavailable`) も SI-08 の違反ではない** — SI-08 が要求するのは境界が有限かつ発見可能であることと、**その enforcement 層が正直に名指しされていること**であり、D-6.1 の V1 (d) はこれを許すために書かれている (裁定 S-1)。

**V1 (e) の位置づけについて 1 点明記する** (設計レビュー 1 回目、B-7): **必須エントリ集合 (固定 9 + capability 条件付き 3) は契約の義務ではなく、共通 suite が SI-08 の証拠として課す追加要件である。** 契約 `capability_status.rules` にこの規則は無く、**契約 1.6.0 に準拠しつつ (e) を満たさない第三者実装はあり得る**。それでも課すのは、**宣言が無い class では「実装していない」と「宣言し忘れた」が区別できず、SI-08 の「有限で発見可能」が成立しない**からであり、`conformance-tests/` は CLAUDE.md の定める implementation-independent な要求の置き場だからである。**これは新しい安全成果の導入ではなく、既存の SI-08 を機械検証可能にするために必要な最小の追加要求である** — したがって新しい invariant は要らない。**この位置づけを C-05 行に開示する** (§7.3) のは、conformance が契約の事実上の拡張であるかのように読まれないためである。**契約側へこの規則を持ち上げるかどうかは本フェーズの対象外である** (制約 C1)。

---

## 9. 公開ゲートの手順骨子

**D-1 (iv) の順序に従う。** 各項目に **[監督]** / **[運用者]** / **[依頼者]** の担当を付す。**着手条件は WP-1・2・3・6 の完了 (= (g)(b) 完了) と依頼者の実行合図である** — **§6 (γ) は 2026-09-05 の依頼者裁定で案 1 に確定した**ので、着手条件としては残らない。

| # | 手順 | 担当 |
|---|---|---|
| 0 | **着手合図の確認** — (g)(b) の完了と、依頼者の明示の実行合図 | **[依頼者]** |
| 0.5 | **すべての linked worktree を畳む** (`git worktree remove` / `git worktree prune`) — `.claude/worktrees/*` は共有ツリーの `.git/objects` を参照するので、書換後は不整合な参照を持つ。**前倒しで作った 7-A の worktree もここで畳む** (§12)。**書換は remote から取り直した fresh clone 上で行う** — filter-repo 自体が fresh clone での実行を前提にしており、既存作業ツリーで `--force` を使うと gc 前の object 残留を生む | **[運用者]** |
| 1 | `git filter-repo --replace-text` による**全履歴の置換**。置換表はリポジトリ外の運用者記録の既存対応表を使う。**filter-repo は作業機に未インストールなので、まず導入する** | **[運用者]** (実行) / **[監督]** (手順書) |
| 2 | **commit-map による文書内 hash 参照の一括更新**。**書換後の新 commit として乗る**。対象規模は 29 ファイル・262 件の hex 様トークン (誤検出は精査で除く) | **[監督]** (適用スクリプトと精査) |
| 3 | **同名リポジトリを delete し、書換後の履歴だけを push して再作成する** (**§6 (γ) 案 1 で確定**、依頼者裁定 2026-09-05)。**全 branch・全 tag を push する**。**force push では GitHub 側に旧 commit が unreachable object として残り得る**ので、remote の object store 自体を新しくする。これを行わない限り、履歴の実値が消えるのはローカルだけである | **[運用者]** |
| 4 | **remote から新規 clone を取り直し**、そのクローンに**スキャナの履歴モードを掛けて全規則 0 件**であること (`--history`)。**取得元は手順 3 で再作成した remote である** (§6 (γ) 案 1)。**ローカルの書換済みツリーではなく、remote が実際に保持している履歴を検査する** | **[監督]** |
| 5 | **全 clone・worktree の作り直し** — 共有ツリー、`.claude/worktrees/*`、VPS 上の clone | **[運用者]** |
| 6 | **有効 credential 2 件 (r2db control / runtime) の revoke + 再発行**。**rotate は id を保持するため不可** | **[運用者]** |
| 6.5 | **R7 (個人名) の人手確認** — スキャナが規則化できない個人名 (L7-3) を、新規 clone の `git log --all -p` に対して人手で確認する (対象語はリポジトリ外の運用者記録にある) | **[運用者]** |
| 7 | **visibility の切替** | **[依頼者]** |

**監督が担うのは**: 手順書、commit-map 適用スクリプト、履歴スキャン、文書 hash 更新の 4 つである。**実行の大半は運用者作業である。**

**記録する帰結**: 手順 1 の後、**リポジトリ外の記録が引く旧 hash は無効になる**。**commit-map はリポジトリ外の運用者記録に保存する** (内容は本書に書かない)。

**手順 6 が手順 5 より後である理由**: 作り直し前の clone が古い credential で動き続けることを避けるためではなく (revoke は即時に効く)、**手順 1〜4 が失敗して巻き戻す場合に、まだ credential を失っていない状態でやり直せるようにするため**である。credential の再発行は**取り消せない**唯一の手順である。

**手順 3 が残留を閉じる (2026-09-05 に確定)**: force push だけでは GitHub 側に旧 commit が **unreachable object** として残り得る (SHA 直指定で取得できる)。**依頼者裁定 2026-09-05 は §6 (γ) の案 1 を採ったので、手順 3 は「同名リポジトリの delete + 書換後履歴のみ push + 再作成」であり、手順 4 のクローン取得元も再作成後の remote である。** **remote の object store 自体が新しくなるので、旧 object は残らない** — **(γ) の未確定を理由に手順 7 (visibility の切替) を止める必要はなくなった** (L7-13)。

---

## 10. WP 分割の素案 (作業指示書で確定する)

**本節は素案であり、着手順・粒度・完了条件は作業指示書が確定する。**

### 7-A (Q4 非依存。共有ツリーと触るファイルが重ならない)

**前倒し着手が確定している** (**依頼者裁定 2026-09-05**、§6 / §12) — **7-A の 3 WP は Q4 の main マージを待たずに着手する**。

| WP | 内容 | 主な成果物 |
|---|---|---|
| **WP-1** | **(g) 公開規律** | `docs/security/public-repository-policy.md` (Never publish の D-1 (i) 表の全行 = 6 分類 + placeholder 規約 + First-public-push gate の 8 項目)、`INITIAL_GITHUB_PUBLICATION_WORK_ORDER.md:71` の参照化、配備記録テンプレート、`tools/public_value_scan.py`、`.pre-commit-config.yaml` |
| **WP-2** | **(b) constraints と CI** | `constraints.txt`、`.github/workflows/ci.yml` (**PG を起動する `docker run` step**、DSN の loopback TCP 上書き、**Python matrix 3.11 / 3.12 をともに required** (§6 (α) 確定。正本は 3.11 job の集計行)、scanner job、deploy-assets lint job)、`conformance-tests/README.md` の実 PG 要件 |
| **WP-3** | **(h) r2db 配備資産** | `r2db-api/deploy/systemd/r2dbsvc-control.service`、nginx 例の `location /control/v1/`、`r2db-api/deploy/scripts/` の operator script 3 本、runbook §7 の更新 |

### 7-B (各 WP に「**着手条件: Q4 の main マージ後**」)

| WP | 内容 | 主な成果物 |
|---|---|---|
| **WP-4** (**着手条件: Q4 の main マージ後、かつ §D-6.5「Q4 確定後の追補」の記入と監督承認の後**) | **(a) C-05 + (e)** | **§D-6.5 追補の記入** (最初の作業)、`test_c05_limit_declaration_agreement.py` (V1 (a)〜(e) / V2 / V3)、**port v1.11 の `isolated_application_surface()`** (port 準拠の adapter instance を返す形)、MitateDB の**欠落 4 class への明示エントリ追加** (3 つは `unavailable`、`operation_depth` は実測で二枝。D-6.1。**§6 (β) 確定により本 WP に置く** — 7-A へ先出ししない)、V3 の `xfail(strict=True)` **7 または 9 件** (in-process の `request_bytes` を含む)、隔離 surface の資源検査、**D-6.2 の駆動レシピ・検査形の全 plug 実測と §13 への記録**、**C-14 の `limit_class` soft-check 注釈の訂正と L6-19 の閉止** (D-6.4) |
| **WP-5** | **(a) 他 5 条件 + (d)** | `test_c04_*` / `test_c10_*` / `test_c02_*` / `test_c07_*` (原子性 + 宣言分岐 + 全体 guard) / `test_c00_*`、**port v1.11 の `idempotency_key` optional フィールド**、r2db の `surfaces` 検証ヘルパの 1 モジュール化と同型性対応表への追加 |
| **WP-6** | **(b)(iii)** | `filterwarnings = ["error::DeprecationWarning"]` の有効化、`httpx2` 追加または `ASGITransport` への 12 箇所の書き換え |
| **WP-7** | **(i) 履歴分離** | `CONTROL_MAPPING_HISTORY.md` / `CONDITIONS_HISTORY.md`、元 2 ファイルの現行行化と更新規約、`test_conditions_register.py` の拡張と `test_control_mapping_register.py` の新設 |
| **WP-8** | **記録** | 本設計 §13 実施記録、`CONDITIONS.md` / `CONTROL_MAPPING.md` の現行行、`PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 L6-20 と L6-19 の状態、**第 14 次引き継ぎ**、**§D-6.5 追補の確定記録** (追補の記入そのものは WP-4 の着手条件である。D-6.5) |

**【状態 2026-09-06】WP 分割の実施状態** (本節は素案であり、確定した発注と実施状態の正本は作業指示書 §1、実測の正本は §13 である):

| WP | 状態 | main の merge |
|---|---|---|
| **WP-1** (g) | **完了 (2026-09-05)** | `448c660` |
| **WP-2** (b)(i)(ii) | **完了 (2026-09-05)** | `50c307f` |
| **WP-3** (h) | **完了 (2026-09-05)** | `dd08594` |
| **WP-4** (a) C-05 + (e) | **完了 (2026-09-06)** | `9ab4245` |
| **WP-5** (a) 他 5 条件 + (d) | **完了 (2026-09-06)**。**(d) は Q4 が先に閉じたため対象消滅** (訂正註 9)、**代わりに conformance の資源管理が入った** | `0650855` |
| **WP-6** (b)(iii) | **完了 (2026-09-06)** | `a090e80` |
| **WP-7** (i) | **完了 (2026-09-06)** | `b2f9224` |
| **WP-8** 記録 | **完了 (2026-09-06)** | 本記録コミット。hash は次回引き継ぎ §1 に記載 |
| **WP-9** 公開ゲート | **着手条件待ち — 依頼者の実行合図のみが残っている** | — |

**したがって 7-A と 7-B は閉じ、フェーズ7 で未着手なのは WP-9 だけである。**

### WP-9 公開ゲート (独立の最終 WP)

**着手条件: WP-1・2・3・6 完了 (= (g)(b) 完了) と依頼者の実行合図。** 内容は **§9 の (0)〜(7)** である。**§6 (γ) は依頼者裁定 2026-09-05 で案 1 に確定した**ので着手条件からは外れ、**手順 3 は「同名リポジトリの delete + 書換後履歴のみ push + 再作成」、手順 4 の clone 取得元は再作成後の remote** である。

---

## 11. 台帳 (本フェーズの起票項目)

- **L7-1 【最優先の次フェーズ候補】MitateDB application plane の資源上限実装 + concurrency probe の port primitive** (依頼者裁定 3、2026-09-05 起票)。**内容**: MitateDB の application plane に `execution_ms` / `concurrency` / `requests_per_minute` の実際の enforcement を実装し、宣言を `unavailable` から `enforced` (または `reference_wall_clock`) へ上げる。**`operation_depth` が WP-4 の実測で `unavailable` と判明した場合は、4 番目の対象 class として本項に加える** (D-6.1 の二枝、裁定 S-2)。**同時に、port へ `concurrency` の駆動に要る in-flight 保持 primitive を足す** — 現行の port には「N 個の要求を同時に in-flight で保持したまま N+1 個目を出す」手段が無く、これが `concurrency` を「駆動しない」に分類している唯一の理由である (D-6.2)。**r2db は `concurrency` を `enforced` と宣言しているので、この primitive が入るまでは「宣言は `enforced` だが共通 suite は駆動していない」状態が続く** — この差集合は C-05 行に開示される (D-6.1 V2)。**本 primitive が入れば r2db 2 plug の差集合も同時に閉じる。** **閉止の合図は C-05 V3 の `xfail(strict=True)` (7 または 9 件。in-process plug の `request_bytes` 1 本を含む — これは r2db 同型の構造推定による in-process の `request_bytes` 上限を MitateDB `cell` 層に置く副項目として本項に含める) が class ごとに XPASS になることである** — 実装コミットが赤にし、同一コミットで当該 class の分を撤去する。**class ごとに分かれているので、本項は 1 class ずつ閉じられる。** **本項は `PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §11 L6-20 の末尾と第 13 次引き継ぎ §4-2 にも起票する** (裁定 3)。**順序付けであり先送りではない** — 検証を先に入れることで欠落を fail-loud にする、というのが裁定 3 の趣旨である。 **【状態注記 2026-09-06 (WP-4 完了)】閉止の合図となる `xfail(strict=True)` は 9 件で置かれた** — 内訳は `MitateDB-api` (in-process) 5 本 (`execution_ms` / `concurrency` / `requests_per_minute` / `operation_depth` / `request_bytes`) と `MitateDB-api-http` 4 本 (`request_bytes` を除く同 4 class) である (§13.2 WP-4)。**`operation_depth` は WP-4 の実測で `unavailable` と判明した**ので (MitateDB 側に深さを計測・拒否する実装コードが 1 つも無いことを直接確認した)、**本項の 4 番目の対象 class として確定した** (D-6.1 の二枝のうち第二の枝、裁定 S-2)。**本項は依然として開いている** — 9 件はいずれも XPASS していない (WP-4 / WP-5 / WP-6 のいずれの完了ゲートでも `9 xfailed` が不変である)。 **【状態注記 2026-09-07 (フェーズ8 完了)】閉じた。** フェーズ8 WP-1 が MitateDB application plane に 4 class の実 enforcement を置き (`execution_ms` = `reference_wall_clock`、`concurrency` = プロセス全体の in-flight カウンタ、`requests_per_minute` = credential 単位の 60 秒窓、`operation_depth` = r2db 同型の汎用再帰深さ)、副項目の in-process `request_bytes` (構造推定) も入れた。**宣言と実装は同一コミットであり、`_V3_KNOWN_UNAVAILABLE` は `frozenset()` — C-05 V3 の `xfail(strict=True)` は 9 → 0 になった** (完了ゲート `2340 passed`、`xfailed` 0)。**`operation_depth` は in-process / HTTP の両面で `enforced` である** — 「in-process 面に要求 dict が無いので `unavailable` が残るかもしれない」という起票時の懸念は成立しなかった (in-process の `values` 自体が要求構造であり、既定 depth 8 の下で 7 段ネストの `session.insert()` が `LIMIT_EXCEEDED` になる)。**port の in-flight 保持 primitive も入った** — `hold_in_flight` (port v1.12) を 4 plug すべてが実装し、**`concurrency` が共通 suite で初めて駆動されるようになったので、r2db 2 plug の差集合も同時に閉じた**。詳細はフェーズ8 設計 §3 D-1 / D-2 と §11.3 WP-1a / WP-1b。
- **L7-2 (c) 実ソケットを持つ HTTP plug は本フェーズに含めない** (D-6.9)。**理由**: CI (D-3) が実サーバ起動の場を初めて作るので、その後に conformance 構成 (5・6 番目の plug) の設計として独立に扱うのが順序として正しい。**公開ゲートの条件ではない。** L6-12 / L6-5 の「宣言 URL の実在が load-bearing になる」性質はこの plug が入って初めて閉じる。 **【状態注記 2026-09-06 (フェーズ7 完了時点)】本項は開いたままである。** **本フェーズは (c) に一切着手していない** — 5・6 番目の plug は 1 つも足しておらず、conformance の plug は 4 のままである。**前提条件だった CI (実サーバ起動の場) は WP-2 で成立した**ので、**着手の障害は無くなった**。**次フェーズ候補として L7-1 に次ぐ位置に置く。**
- **L7-3 R7 (個人名) は機械検査の対象外である** (D-2)。正規表現で表現できないため、**人手レビューに委ねる**。現時点で個人名は現行ツリー・履歴とも 0 件と記録されている (L6-20 (g)) が、**これは機械的に維持される性質ではない**。公開ゲートの手順に人手確認の項目として残す。 **【状態注記 2026-09-06】記録のまま。** スキャナは**出力末尾で「R7 は検査していない」ことを毎回明示する**形で実装され (WP-1)、**§9 の手順 6.5 が人手確認として残っている** — **実行は WP-9 であり未了である**。
- **L7-4 スキャナの誤検出率は R2_fqdn の TLD 集合に依存する**。プロトタイプ v2 は短 TLD と属性連鎖 (`self.dev` 形) の衝突で 112 件の誤検出を出した。**TLD 限定集合は実装 WP で再プロトタイプして 0 件を確認してから固定する** (D-2)。**将来 TLD を足すときは同じ手順を踏む** — 集合を広げると誤検出が戻る。**あわせて、placeholder 除外を「トークン全体の除外」から「部分文字列を除去して再判定」へ改めた新規則で、付録 A に残る誤検出 2 件が同じく消えることを再プロトタイプで確認する** (D-2)。 **【状態注記 2026-09-06】手順は WP-1 で踏み、ツリー全規則 0 件を確認した** (§13.2 WP-1)。**本項が言う「将来 TLD を足すときは同じ手順を踏む」という規律は、規律として残る** — 閉じていない。**さらに 7-B で 1 例が出た**: **隣接行に分割された文字列リテラルで書かれた合成 URL が R2_url で誤検出された** (main CI 緑化の (2))。**是正はテスト側を 1 行に収める形で行い、「スキャナは行単位で走査する」という契約は変えていない** — **行単位という契約が誤検出を生む形が実在することの実測**であり、本項に足しておく。
- **L7-5 `constraints.txt` は作業機の venv の写像であり、CI とローカルの二重の真実になり得る**。生成手順が「清浄 venv + `pip freeze` + 手で整える」である以上、**手で整える工程の判断はコミットに残らない**。CI が constraints を使ってインストールすることで食い違いは検出されるが、**constraints 自体が正しいかは CI では測れない**。依存を上げるときに集計行を添える規約 (D-3) がこの穴を埋める唯一の機構である。 **【状態注記 2026-09-06】記録のまま。** **WP-6 が `constraints.txt` に 3 件 (`httpx2` / `httpcore2` / `truststore`) を足した際も、規約どおり集計行を添えた** (§13.2 WP-6)。**手で整える工程の判断がコミットに残らないという性質そのものは変わっていない。**
- **L7-6 CI の集計行とローカル単独実行の集計行が食い違ったときの正本が未定義である**。D-3 は「以後の完了ゲートは CI の集計行を正本の記録に引く (ローカル単独実行は維持)」とするが、**2 つが食い違った場合の扱い**を決めていない。**§6 (α) は 2026-09-05 に「両方 required、正本は 3.11 job の集計行」で確定した**ので、**引く集計行は 1 本に定まった** — 3.12 job は同一集計行であることの担保に回り、食い違えば当該 job が赤になる。**本項に残るのは「CI の集計行とローカル単独実行の集計行が食い違ったときの扱い」だけである。** **【状態注記 2026-09-06 (7-B WP-4〜WP-6)】食い違いはまだ 1 度も起きていない** — **WP-4 のマージ後の main の 3.11 job は 4 数がローカルの完了ゲートと同一だった** (`2214 passed, 9 xfailed`、§13.1)。**あわせて実測された差は `warnings` の数だけである** (ローカル 5 / CI 10) — **これは共有 `.venv` に `httpx2` が入っていないことによる環境差であり、集計行の 4 数には入らないので一致判定には用いない**。**したがって本項の未定義部分 (食い違ったときの正本) は依然として未定義のまま**であり、閉じていない。
- **L7-7 C-10 の共通化は adapter 境界水準に留まる** (D-6.7)。**「wire 水準」とは書かない** — in-process の 2 plug には wire が無いので、誤読源になる。**PG 権限そのもの (runtime role が platform 表を読めないこと等) は peer-local 証拠の参照のままである** — 共通 suite は adapter 越しにしか peer を見ないので、DB role の権限を直接検査できない。**射程はさらに「各 worker が観測した応答の範囲」に限られる** (`-n 5 --dist loadgroup` では plug ごとに worker が分かれる)。**この 2 つの射程を `CONDITIONS.md` C-10 行に開示する。** **【状態注記 2026-09-06 (WP-5 / WP-7 完了)】開示は入った** — **C-10 行に adapter 境界水準・worker 単位・PG 権限は peer-local という 3 つの射程が書かれている**。**WP-7 の履歴分離を経てもこの 3 点は現行行に残っている** (レビュー §5 と監査 §2-2 が独立に確認)。**射程そのものは残る** — 閉じていない。**あわせて WP-5 が足した受理境界 1 件**: **秘密 literal 集合の走査には非空性の assert が無い** (監査の変異 A、§13.2 WP-5)。
- **L7-8 C-07 の idempotency 側は現時点で肯定側が空である**。両 peer とも `idempotency: unavailable` を宣言する (§1.6 の 5) ので、共通 suite が測れるのは「**拒否が実行前に起き、副作用が 0 件であること**」だけである (D-6.7)。**空振りにはならない** — 宣言分岐の全体 guard が「観測対象 ≥ 1 plug」を要求し、現時点では `unavailable` 枝の観測 4 件がこれを満たす。**どちらかの peer が `idempotency` を `unavailable` 以外で宣言した時点で、再送同一結果の肯定側が初めて load-bearing になる。** port v1.11 が足すのは **`idempotency_key` を運ぶ optional フィールドだけ**であり (裁定 S-4)、**肯定側の primitive (key の保管・再送・結果比較) はそのときに足す** — 動かす対象が無いうちに port の面積を増やさない。 **【状態注記 2026-09-06 (WP-5 完了)】本項の見立ては実測どおりだった。** **C-07 (ii) は 4 plug とも `unavailable` 枝**であり (`retry_same_result` 枝は 0/4)、**全体 guard が空振りを防いでいる**。**宣言分岐リテラルを入れ替える変異は 4 plug すべてで赤である** (§13.2 WP-5 の変異 6 / 7)。**肯定側は依然として空であり、本項は開いたままである。**
- **L7-9 現行セルの長さ上限は仕分け後の実測から決める** (D-7)。**上限は主表の各セルに掛け、設計は目安 2,500 文字だけを置き、確定値は実装 WP が仕分け後の最長セルから決めて本設計に記録する。** 上限が実際の最長セルより低ければ仕分けが未了ということであり、高すぎれば再蓄積を止められない。**目安を 1,500 から 2,500 へ上げたのは実測による** — `CONDITIONS.md` の Condition 列だけで **C-17 が 1,788 文字**あり、この列は条件の定義文であって履歴を含まないので、**1,500 では仕分けをどれだけ完璧にやっても割れない** (設計レビュー 1 回目、B-12)。 **【状態注記 2026-09-06 (WP-7 完了)】本項は閉じた — 確定値は `CONDITIONS.md` = 3,000 / `CONTROL_MAPPING.md` = 15,200 である** (§13.2 WP-7)。**上限は 1 本ではなくファイル別に分けた** — 単一 cap は `CONDITIONS.md` に対して数倍の余裕を生み、本項の「高すぎれば再蓄積を止められない」に該当したためである (レビュー指摘 C-1)。**実測の最長セルは C-09 Status 2,948 字 (余裕 52; C-19 は 2,942) と SI-14 r2db-api 列 15,065 字 (余裕 135)** であり、**設計の目安 2,500 は `CONDITIONS.md` 側でのみ概ね達成され、`CONTROL_MAPPING.md` の SI-14 は監督が超過を受理した** (理由は §13.2 WP-7)。**あわせて残る性質**: **余裕が小さいので正当な追記でも赤になり得る** — その場合は**同一コミットで前文の測定行と上限を更新する** (訂正註 11 の ratchet)。**無記録の緩和は不可である。**
- **L7-10 履歴分離のレビューは「落ちた制約」の突合を独立項目に置く** (D-7)。**機械検査は anchor の有無と長さしか見ない** — 現行行から現行の制約が落ちていないことは、**人手の突合でしか担保できない**。C-19 の Honest limits (a)〜(e) が最も落ちやすい形である。 **【状態注記 2026-09-06 (WP-7 完了)】本項は実施済みであり、かつ実測で正しさが裏づけられた。** **独立コードレビューが「落ちた制約」を独立項目として突合し、8 件を検出した** (C-09 の Honest limit (a)(b)、SI-14 (r2db) の除外根拠と process-local 上限、および低重大度 4 件)。**8 件はすべて現行行へ復帰させ**、付随して虚偽になっていた 2 つの docstring (`test_c09_audit_evidence.py` / `test_c19_client_self_sufficiency.py`) も訂正した。**受け入れ監査は自ら選んだ 12 行を独立に突合し、現行行にも companion にも無い制約 0 件**を確認した。**本項の見立ては機械検査の限界について正確だった** — 実装が用意した網羅検査 (`wp7_full_coverage.py`) は**現行セルと companion の合算**に対して在否を見るので、**「失われていない」ことしか示せず、「現行から落ちた」を原理的に見られない** (レビュー §F、監査 §3)。**したがって完了条件 10 を実際に担保したのは人手の二重突合である。** **本項は「履歴分離を行う将来の作業にも同じ独立項目を置く」という規律として残す** (更新規約が現行行の書き換えを許す以上、同種の欠落は再発し得る)。**あわせて残件 1 件**: **現行行から落ちた台帳 ID のうち未閉止の 2 件は戻していない** — **L7-22** を参照。
- **L7-11 配備資産は合成値から書き起こすので、実機の原本との一致は保証されない** (D-5)。**運用者が原本と突合するのは任意の検証であり、本フェーズの完了条件ではない。** CI の lint job が担保するのは「テンプレートとして構文が妥当であること」までである。 **【状態注記 2026-09-06】記録のまま。実機との突合は行われていない。** **加えて本項と同じ性質の穴が 1 日で顕在化した** — **WP-3 が作った `part1_provision_host_and_db.sh` は、その翌日に main へ入った Q4 の `0008` を知らない状態で出荷された** (Q4 台帳 LQ4-24)。**追随は LQ4-24 追補として 7-A の follow-up で行った** (§13.2)。**「配備資産は文書と別の速度で古くなる」という性質は閉じていない。**
- **L7-12 公開ゲートの手順 6 (credential の revoke + 再発行) は取り消せない**。手順 1〜4 が失敗して巻き戻す場合に備え、**credential 再発行を手順 5 の後に置く** (§9)。**この順序は、失敗時に credential を失わないことだけを目的としている。** **【状態注記 2026-09-06】WP-9 は未着手であり、本項の順序は §9 の手順として置かれたまま実行されていない。** 着手条件 (WP-1・2・3・6 の完了かつ依頼者の実行合図) のうち **WP-6 は 2026-09-06 に完了した**ので、**残るのは依頼者の実行合図だけである。** **【状態注記 2026-09-06 (WP-8)】7-B は WP-7 の完了で閉じたので、フェーズ7 で未着手なのは WP-9 だけである** — **着手条件のうち機械的に満たせるものはすべて満たされており、待っているのは依頼者の実行合図のみである**。**本項の順序 (credential 再発行を手順 5 の後に置く) は §9 の手順表のまま、実行されずに残っている。**
- **L7-13 (閉じた、2026-09-05) force push 後の GitHub 側 unreachable object の残留への対処は、依頼者裁定 (§6 (γ)) で案 1 に確定した** — **同名リポジトリを delete し、書換後の履歴だけを push して再作成する**。**remote の object store 自体が新しくなるので旧 object は残らない**。裁定 2 の「単一リポジトリを維持する」は**識別 (owner / 名前 / 単一の正本) の維持**と読む。**したがって「未確定であること自体が公開の阻却事由である」という本項の起票理由は解消した** — 残るのは実行 (§9 の手順 3・4、D-1 (iv) の (4)(5)) だけである。**本項は WP-9 の実施記録で最終的に閉じる。** **【状態注記 2026-09-06】WP-9 は未着手であり、実行分は未了のままである** — 本項の「閉じた」は**裁定が確定したこと**を指し、**remote の再作成が済んだことではない**。**7-B の実施で新たに増えた linked worktree (`phase7-wp4` / `phase7-wp5` / `phase7-wp6` など) も、§9 の手順 0.5 (worktree 畳み) の対象として WP-9 に乗る** (§12)。 **【状態注記 2026-09-06 (WP-8)】畳む対象の worktree は最終的に 7 本になった** — フェーズ7 側の `phase7` / `phase7-wp2` / `phase7-wp3` / `phase7-wp4` / `phase7-wp5` / `phase7-wp6` / `phase7-wp7` であり、**Q4 セッションが作った worktree もあれば同じく対象である** (`.claude/worktrees/*` はすべて共有ツリーの `.git/objects` を参照する)。**手順 0.5 の実行時に `git worktree list` で実数を確認すること** — 本注記の列挙は 2026-09-06 時点の記録であって、実行時の網羅リストではない。
- **L7-14 (7-A で起票、2026-09-05) スキャナのツリーモードは `git ls-files` の対象しか検査しない — 未追跡ファイルは見ない。** **実測**: WP-2 の変異 4 の先行試行 (実行時生成した違反を**未追跡のまま**置いた) では **scanner job が緑のまま**であり、`git add -N` で intent-to-add した後に初めて赤になった (§13.2 WP-2)。**これは欠陥ではなく契約である** — ツリーモードは「**コミット対象になり得るもの**」を見る、と定義されている。**未追跡ファイルの側は `.pre-commit-config.yaml` の local hook が担う** (hook は staged なファイルに対して走る)。**したがって「ツリーモードが緑である」は「作業ディレクトリに実値が無い」を意味しない** — この射程を公開ゲート (D-1 (iv) の (5)) の読み手が取り違えないよう、**WP-9 の履歴スキャンは fresh clone に対して掛ける** (未追跡ファイルが存在し得ない状態にする) という現行の手順がそのまま手当てになっている。**本項は記録であり、追加の手当ては要さない。**
- **L7-15 (7-A で起票、2026-09-05) 現行 origin 履歴の実値 1061 件という実測値は、WP-9 の書換で消える。** WP-1 の `--history` (`git log --all -p -m`、merge commit を含む) が commits_scanned 218 に対して報告した **総 flagged 1061 件** (規則別: R1_email 447 / R2_fqdn 192 / R2_url 102 / R3_project_id 174 / R3_project_number 34 / R4_credential_id 14 / R5_iam_principal 28 / R5_iam_sa 32 / R6_home_path 38。走査したパッチ行数 336,789) は、**パッチ行単位の件数であり重複を含む** — 付録 A.2 の見積り (単一ファイルの履歴、パッチ行 2,157) とは母数が違うので**直接比較できない**。**この数値は WP-9 の filter-repo と remote 再作成の後には再現できない** — 書換後の履歴に対する `--history` は**全規則 0 件**であることが公開ゲートの条件 (D-1 (iv) の (5)) だからである。**したがって本項は「書換前の規模を記録に残す」ためだけに存在する**。**WP-9 の実施記録で、書換前 1061 → 書換後 0 の対比として引く。**
- **L7-16 (7-A で起票、2026-09-05) deploy-assets lint の検査結果は runner 上のツール版に依存する。** **実測**: 分離形の `http2` ディレクティブを置く変異 L3 が `nginx -t` で赤になるのは、**runner の nginx が 1.24.0 (ubuntu-24.04) だから**である。**nginx 1.25 以降ではこの記法が正当になるので、runner が上がれば L3 は緑に転じ、完了条件 4 (「1.24 互換記法である」) を守っている検査が消える。** 同種の依存は `systemd-analyze` と `shellcheck` にもある — **どの版で何が赤になったかは記録にしか残らない**。**手当ての方向 (本フェーズでは採らない)**: (i) lint job でツール版を出力して記録に残す、(ii) nginx の版を workflow で pin する、(iii) 記法の互換要件そのものを**配備先の nginx 版**に紐づけて runbook 側で管理する。**(iii) が長期に正しい形だが、配備先の版が上がったときに誰が気づくかという問題が残る** — **L7-11 (配備資産と実機の突合は任意の検証である) と同じ性質の穴**であり、実機との突合を制度化しない限り閉じない。**本項は記録として残し、次フェーズ以降で扱う。**
- **L7-17 (7-A で起票、2026-09-05) 集計行が 1800 / 1802 から 1868 passed + 4 xfailed へ動いたのは Q4 フェーズの main 反映であり、本フェーズの変更ではない。** 作業指示書 :1073 が 7-A の基準値として置くのは**フェーズ6 完了時点の 1800 passed / 0 / 0 / 0**、その後 main に乗った値は **1802** である。一方 7-A の CI 基準 run は **1868 passed / 0 failed / 0 skipped / 4 xfailed** である。**差分は Q4 フェーズが main へ入ったこと (Q4 側が先置きした `strict` xfail を含む) によるもの**であり、**7-A の 3 WP は収集対象のテストファイルを 1 本も足していない** — 変更ファイルはすべて root `pyproject.toml:3` の `testpaths` の外であり、`--collect-only` の収集件数 1872 件 (= 1868 + 4) の一致で確認した (§13.1)。**注意すべき帰結は 2 つある**: **(i)** 作業指示書 :1073 の基準値の記述は**7-A の実測とは合わない**が、**発注時の記述は書き換えない** (差を消さないため) — 7-A の実測は本設計 §13.1 が正本である。**(ii) 7-B (WP-4 以降) の基準値は「Q4 マージ後の集計行」であり、それは 1868 passed / 4 xfailed である** — WP-4 が増やす xfail 7 または 9 件は**この 4 件の上に載る**。**本設計 §7.4 と作業指示書 :1062 の「+ 着手時点の既存分」はこの 4 件を指す。** **【状態注記 2026-09-06 (7-B 着手時の実測)】この見立ては実測と合わなかった** — **7-B の着手時点の main (`8b0e247`) の CI 3.11 job は `2165 passed / 0 failed / 0 skipped / 0 xfailed`** であり、**xfailed は 4 ではなく 0 だった**。**Q4 WP-3 (`3d186a9`) が「WP-0 strict xfails removed」として当該 4 件を撤去した**ためである。**したがって「+ 着手時点の既存分」は 0 であり、WP-4 が置いた xfail 9 件はそのまま 9 件としてゲートに現れる** (§13.1 の 7-B の集計行)。**7-A 時点の実測 (1868 passed / 4 xfailed) 自体は当時の事実として正しく、書き換えない** — 本注記は「7-B の基準値」の部分だけを実測で正すものである。
- **L7-18 r2db に「宣言の検証」を終了コードで返す ops コマンドが無い (LQ4-24 追補のレビュー M-1、2026-09-06 起票)**。`ops show-declarations` は診断表示であり、表が無い場合を含め全経路で 0 を返す。配備 script (WP-3 の part2) が起動前に確かめられるのは `upgrade-status` (pending = 非 0) だけで、宣言側 (F-3 / F-3c / F-4 / F-8 相当: `surfaces` 行の有無、control 宣言と `R2DB_CONTROL_PLANE_STATUS` の整合、書き手 role 設定) は**プロセスを起動して fail-fast を見る**しかない。手当て候補: `ops verify-declarations` (両プロセスの起動時検査と同じ判定を provision DSN で実行し、F-n ごとの終了コードを返す) を両 peer に置く。Q4 設計 D-1/D-2 の検査関数 (`platform_declarations.py`) を再利用できるので小さい。挙動追加であり別 WP。 **【状態注記 2026-09-07 (フェーズ8 完了)】閉じた。** フェーズ8 WP-4 が **両 peer に同型の `ops verify-declarations` を置いた** — `platform_declarations.py` の検査関数を順に呼び、**F 番号ごとに固定の終了コード** (F-3 → 3 / F-3c → 4 / F-4 → 5 / F-4b → 6 / F-5 → 7 / F-8 → 8 / F-6 → 9 / F-7・F-10・F-11 → 10 / F-13 → 11 / F-9 → 12、全 pass = 0) を返し、**1 行 1 検査 + 対象外 3 条件 (F-1 / F-2 / F-12) の 1 行**を全経路で出す。**`PlatformDeclarationError` に F 番号の構造化属性 `code` を足した** (メッセージ文言は無変更)。**書き手 role 検査は writer role の DSN で実行しないと常に F-13 / exit 11 になる**ので、この運用要件を `docs/ops/BACKUP_RESTORE_R2DB.md` 手順 4 に明記した。詳細はフェーズ8 設計 §3 D-5 と §11.3 WP-4。
- **L7-19 上流由来の DeprecationWarning 1 件を狭い ignore で受けている (WP-6、2026-09-06 起票)**。`starlette/testclient.py:53` が `anyio.abc.BlockingPortal` (anyio 4.15 で deprecated alias) を無条件に参照し、`import starlette.testclient` だけで DeprecationWarning を出す。我々のコードは 0 件なので、`ignore:.*BlockingPortal.*:DeprecationWarning:starlette.testclient` をモジュール限定で root と両 peer の pytest 設定に置く (D-4 の「個別 ignore は台帳項目付きでのみ」の初例)。**撤去条件**: constraints の Starlette を、この参照を直した版へ上げたとき (constraints 更新の commit で同時に外し、集計行を添える)。あわせて D-3 の「pytest 設定の一本化 = root のみ」は誤りだった — pytest は最寄りの inifile を採るので peer 単体実行に root 設定は効かない。3 つの pyproject に同じ 2 行を置き、同型性 (3 ファイルの `filterwarnings` が同一) を WP-6 のテストで固定する。 **【状態注記 2026-09-06 (WP-6 完了、main `a090e80`)】本項の形はそのまま実装された** — 3 つの `pyproject.toml` に同じ 2 行 (`error::DeprecationWarning` + 上流 1 件の狭い ignore) を置き、**同一性は新設の `conformance-tests/test_pytest_config_symmetry.py` (2 テスト) が pin する**。**撤去条件は未達である** (constraints の Starlette は当該参照を直した版へ上げていない)。**あわせて記録**: 共有 `.venv` に `httpx2` を入れていないため完了ゲートには `StarletteDeprecationWarning` が 5 件残るが、**これは `UserWarning` 派生であり本項の ignore とも `error::DeprecationWarning` とも無関係**である (§13.1)。**L7-20 ローカル開発 PG クラスタの role 設定汚染 (2026-09-06 実測)**: 管理者ロールに `statement_timeout=5000ms` / `idle_in_transaction_session_timeout=5000ms` の `ALTER ROLE … SET` が残っており (Q4 の migration 0008 相当を管理者ロール名で流した痕跡と推定)、r2db の 2 テスト (`assert '0' == '5s'`) が偽赤になった。監督が `ALTER ROLE … RESET` で戻した。Q4 WP-2 の e2e 残骸ロール 2 本も残っている (無害、未削除)。教訓: 共有クラスタで migration を手で流すときは psql 変数の role 名を確認する。 **【状態注記 2026-09-07 (フェーズ8 完了)】据え置き。依然として開いている。** フェーズ8 の R-11 は「撤去条件が満たせる版があれば本フェーズで行う」だったが、**満たせなかった** — `constraints.txt:42` は `starlette==1.6.0` であり、`pip index versions starlette` の最新も **1.6.0** である (2026-09-06 実測)。**上流に `anyio.abc.BlockingPortal` 参照を直した版が存在しないので、「constraints の更新と同一コミットで ignore を外す」という撤去条件そのものが構成できない。こちら側の遅れではない。** フェーズ8 WP-4 は `constraints.txt` と 3 つの `filterwarnings` を 1 バイトも触っていない (受け入れ監査が `git diff` で確認)。**次に Starlette が上がったときに再評価する** (フェーズ8 設計 §10 L8-2)。
- **L7-21 (WP-4 で起票、2026-09-06、監督裁定 1 (4) 反映) MitateDB の `result_items`/`query_complexity` は `enforced` 宣言だが、port v1.11 には要求側の limit/page 件数や filter 述語数を運ぶ経路が無く、V2 は「駆動集合の導出規則」(§8) の外側 -- 実装は peer 名 (`MitateDB-api`/`MitateDB-api-http`) を固定で名指しして駆動対象から外す形になっている (`test_c05_limit_declaration_agreement.py` の駆動 class 表、§13.2 実施記録の疑義 1)。**このため、MitateDB がこの 2 class を偽って `enforced` と宣言しても V2 は永久に緑のままである** -- 除外が「その peer では port 経由でこの検査に到達する要求を構成できない」という port の形に紐づいておらず、宣言の真偽と無関係な peer 名という属性に紐づいているため (監査 `wp4-audit.md` §8 (b) の指摘)。禁止事項 2 (固定除外リストで宣言を偽っても赤にならない形にすることの禁止) に触れる**穴**であり、CONDITIONS.md C-05 行の該当開示 (D-6.2 格下げ理由) にこの L7-21 参照を添える。**手当て**: port v1.12 で `select_eq`/`attempt_filter` に要求側 limit/page 件数と filter 述語数を運ぶ optional フィールドを足し、V2 側の除外判定を「peer 名の固定リスト」から「port がその要求パラメータを運べるかどうかの能力判定」へ置き換える -- そうすれば偽の宣言は「宣言 `enforced` かつ駆動不能な組」として pin されたテストで赤くなる (監査 §8 (b) の代替案)。**次フェーズ候補として L7-1 の束に含める** (L7-1 が MitateDB application plane の資源上限実装と port primitive 追加を一括して扱っているのと同じ性質の「port 能力の拡張待ち」であるため)。**順序付けであり先送りではない** -- 現時点では CONDITIONS.md の開示がこの穴を明文化しており、宣言を検証なしで信頼させてはいない。 **【状態注記 2026-09-06 (WP-5 完了時点)】本項は開いたままである** — **WP-4 のマージ (`9ab4245`) で `CONDITIONS.md` C-05 行の開示と本項への参照は入った**が、**手当て (port v1.12 で要求側 limit/page 件数と filter 述語数を運び、除外判定を peer 名から能力判定へ置き換える) は未着手**である。**WP-5 でも port は 1 method も増やしていない**ので (禁止事項 1)、状態は変わっていない。 **【状態注記 2026-09-06 (WP-7 完了時点)】依然として開いたままである** — **WP-6 / WP-7 は port にも conformance の vector にも触っていない**。**手当ては port v1.12 待ちであり、L7-1 の束に含まれる。** **【状態注記 2026-09-07 (フェーズ8 完了)】閉じた。** フェーズ8 WP-1b が **port v1.12** で `select_eq` / `attempt_filter` に optional の要求側フィールド (**page size = `limit`**、**複数述語 = `extra_predicates`**) を足し、**除外判定を peer 名固定から能力判定へ置き換えた** — **4 plug とも運べるので除外そのものが消えた**。固定は**命題を限定した静的 assert 2 本**である: **(i) `_V2_DRIVERS` の各 driver 本体に `adapter.name` を読んで early `return False` する分岐が無いこと**、**(ii) `test_c05` 内の `adapter.name` 読みが allowlist の 3 行以外 0 件であること** (どちらも AST 走査。allowlist 3 行は実コードとして一致することまで assert する)。**`result_items` は両側化し、レシピを「表に bound+1 行を 1 度だけ入れ、成功側 `limit=bound` / 拒否側 `limit=bound+1`」に改めたことで、port の `limit` が 4 plug すべてで load-bearing になった** (受け入れ監査が、初稿レシピでは r2db 2 plug で `limit` を捨てても全緑になることを変異で実証したための是正である)。**`query_complexity` は metric 定義の算術から片側のままだが、peer 名による除外は消えている。** **なお本項および `CONDITIONS.md` C-05 行が「`request_bytes` / `query_complexity` が peer 名で除外されている」と書いていたのは誤記であり、実際に peer 名で除外されていたのは `result_items` / `query_complexity` である** — 訂正の事実は `CONDITIONS_HISTORY.md#c-05` へ逐語で移した (フェーズ8 設計 §10 L8-7)。
- **L7-22 (WP-7 で起票、2026-09-06) 履歴分離で、未閉止の台帳 ID が現行行から落ちた**。**現行行から消えた台帳 ID は `CONTROL_MAPPING.md` が `L4-1` / `L4-2` / `L4-5` / `L4-6` / `L4-11` / `L4-13` / `L5-1` / `L5-4`、`CONDITIONS.md` が `L4-8` である** (受け入れ監査 §2-3 の独立検出)。**大半は CLOSED 済みであり、閉じた台帳への参照が履歴側へ移るのは仕分けとして正しい**。**問題は未閉止の 2 件である** — **`L4-13`** は `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 で「**OPEN (記録のみ)。判断は次回**」であり、**`L4-8`** は据え置き (CLOSED ではない) である。**事実そのものはどちらも現行行に残っている** — SI-00 の MitateDB 列は「data-plane の env が control 用 credential pepper を名指ししている、別個で未解決の非対称」を保持し、C-09 は裁定 P4-D18 と「未閉止」の状態注記をレビュー是正で復帰させた。**失われているのは追跡性だけである**: 台帳 ID を grep しても該当する現行行に辿り着けない。**一貫性の観点では戻すのが正しい** — A-2 の是正が「識別子ごと戻す」形を採った以上、同じ基準を未閉止の 2 件にも適用すべきである。**重大度は低い (事実は残る)。手当ては現行行に ID を戻す 2 箇所の追記だけであり、次に当該行へ触れる作業で行う。裁定は監督。** **【状態注記 2026-09-07 (フェーズ8 完了)】閉じた。本項の「開いている」という記述は、起票時点で既に実態と食い違っていた (実態訂正)。** フェーズ8 の探索が現物を読んで確認したところ、**未閉止の 2 件はどちらも現行行に台帳 ID を持っていた** — **`security/CONTROL_MAPPING.md:33`** (SI-00 行) に逐語「a separate, still-open asymmetry (**ledger item L4-13, still open**)」、**`conformance-tests/CONDITIONS.md:38`** (C-09 行) に逐語「Supervisor ruling P4-D18 (**L4-8, still open**) DEFERS rebuilding V4」。**したがって追跡性は失われておらず、手当て (現行行への ID の追記 2 箇所) は不要である。** 実装担当と受け入れ監査が別々に読んで一致を確認した (フェーズ8 設計 §10 L8-1 / §11.1)。**ファイルは 1 バイトも変えていない。** 第 14 次引き継ぎ §4-2 の同じ記述も訂正した。
- **L7-23 (WP-7 で起票、2026-09-06) register テストは単独実行では緑にならない**。`conformance-tests/test_conditions_register.py::test_every_executable_condition_has_a_marked_test` は **`@pytest.mark.condition` をライブの pytest collection から集める**ので、**register ファイルだけを収集すると マーカー付きテストが 0 件になり、全 20 条件が「マーカー無し」と判定されて赤になる** (無変異のベースラインで `1 failed, 16 passed`)。**これは原本 (`origin/main` の同ファイル) から引き継いだ既存挙動であり、WP-7 が持ち込んだ回帰ではない**。**当座の扱いは訂正註 11 のとおり「register テストは conformance 全体 run 内で評価する」である**。**手当ての候補**: 当該テストに「**収集されたマーカーが 0 件なら skip する (あるいは自己申告して落ちる)**」ガードを 1 つ足せば、ファイル単独のコマンドがそのまま成立する。**採らなかった理由は WP-7 の発注範囲外だからであり (常設規律 5)、技術的な障害があったからではない。** **実害**: 実装担当・レビュー・監査の 3 者がそれぞれ独立に同じ赤に当たり、全員が全体 run へ逃がした — **「そのファイルだけ回せば緑」という期待は必ず持たれる**ので、ガードを足す価値はある。**裁定は監督。** **【状態注記 2026-09-07 (フェーズ8 完了)】閉じた。** フェーズ8 WP-2 が `_collect_marked_condition_ids` の末尾に **「観測 0 件なら fail-loud」ガード** (`assert ids, "<理由>"`) を置いた。**`skip` にはしていない** (空振り禁止、常設規律 1)。**帰結**: register ファイル単独実行は「収集 0 件」を明示した理由付きの赤になり (`3 failed, 7 passed`)、**同時に、それまで空集合同士で静かに緑になっていた 2 本のテストが赤に転じた** — 誰も見ていなかった側が可視になった。**完了ゲート形式 (`-n 5 --dist loadgroup`) では緑である**ことを実測した (xdist の各 worker が session 全体を収集するため。受け入れ監査が計測プラグインで **conformance 全体 `n=20 items=584` / register 単独 `n=0 items=10`** を独立に観測した)。**ただしガードが閉じるのは「観測 0 件」だけであり、1 件でも収集される部分実行 (register + 1 ファイル) は救えない** — これは設計どおりであり、実装の逸脱ではない (フェーズ8 設計 §3 D-3 / §10 L8-16 (a))。

---

## 12. 7-A 前倒し (2026-09-05 に確定) と判断材料

**7-A の 3 WP は Q4 と触るファイルがほぼ重ならないので、Q4 の main マージを待たずに着手できる。** 判断材料として、両者が触る範囲を並べる。

- **7-A が触るもの**: `docs/security/*`、`docs/work-orders/` (新規 1 本 + 既存 2 本の小変更)、`tools/` (新規)、`.pre-commit-config.yaml` (新規)、`constraints.txt` (新規)、`.github/` (新規)、`conformance-tests/README.md`、`r2db-api/deploy/*`。
- **Q4 が触るもの**: 両 peer の `src` / `migrations` / `ops` / `tests`、conformance adapter 2 本、`CONTROL_MAPPING.md` の 3 行、runbook。
- **重なりは 2 点だけである**: **`r2db-api/deploy/env/*.example`** (Q4 WP-D が廃止 env を消す) と **`CONTROL_MAPPING.md`** (本フェーズでは WP-7 が触るが、WP-7 は 7-B である)。

したがって **7-A の前倒し着手で衝突するのは `r2db-api/deploy/env/*.example` の 1 点のみ**であり、7-A WP-3 がこの 2 ファイルを触らない (unit / nginx / script / runbook §7 のみを触る) 範囲に留めれば、**重なりは 0 になる**。**前倒しの着手は依頼者裁定 2026-09-05 で確定した** (§6) — **7-A (WP-1 / WP-2 / WP-3) は Q4 の main マージを待たずに着手する**。**7-B の着手条件 (Q4 の main マージ後) は変わらない** (§2 の C8 / §10)。

**前倒しで作った worktree も、WP-9 の手順 1 (filter-repo) の前に畳む必要がある** (§9 の手順 0.5) — linked worktree は共有ツリーの `.git/objects` を参照するので、書換後は不整合な参照を持つ。**前倒しの判断材料として、この後始末が WP-9 に乗ることを織り込む。**

---

## 付録 A. スキャナのプロトタイプ結果 (常設規律 5)

**使い捨てスキャナ `proto_realvalue_scan.py`** (scratchpad、標準 `re` のみ、655 行) を worktree の**追跡 217 ファイル**に走らせた結果である。**件数のみを転記する** — マスク済み断片やパスの一覧は転記しない。

### A.1 現行ツリー — v2 (規則調整後) の規則別件数

| 規則 | total | excluded | flagged | 判定 |
|---|---|---|---|---|
| R1_email | 48 | 48 | 0 | — |
| R2_fqdn | 19,089 | 18,977 | **112** | **全件が誤検出** (短 TLD と `self.dev` / `self.app` 形の属性連鎖の衝突。TLD 限定集合で消える) |
| R2_url | 146 | 145 | **1** | **誤検出** (`<UPPER_SNAKE>` 形の placeholder のみからなるホスト形)。**この 1 件は v2 の「placeholder を含むトークンを丸ごと除外する」規則で消えたものであり、製品版が採る「placeholder 部分文字列を除去してから再判定する」規則 (D-2) では判定が変わり得る** — 再プロトタイプで確認する (L7-4) |
| R3_project_number | 2 | 1 | **1** | **誤検出** (UUID/hex トークンの内部。「hex 内部の 12 桁は対象外」で消える) |
| R4_credential_id_a | 1 | 1 (synthetic) | 0 | — |
| R4_credential_id_b | 1 | 1 (synthetic) | 0 | — |
| R5_iam_principal | 5 | 5 | 0 | — |
| R5_iam_sa | 5 | 5 | 0 | — |
| R6_home_path | 1 | 1 | 0 | — |
| R8_b64run | 15 | 15 | 0 | — |
| **合計 (flagged)** | | | **114** | **真陽性 0 件** |

参考: v1 (初回の逐語規則) の flagged 合計は 15,344 件であり、その大半 (15,284 件) は R2_fqdn の未調整規則によるものである。

### A.2 履歴側 — 書換対象規模の見積り

対象は `docs/work-orders/DEPLOY_PHASE6_20260904.md` の履歴 (`git log --all -p` 相当) である。**commit 数 7、走査したパッチ行数 2,157。件数はパッチ行単位であり重複を含む。**

| 規則 | excluded | flagged |
|---|---|---|
| R1_email | 14 | **26** |
| R2_fqdn | 563 | **160** |
| R2_url | 49 | **24** |
| R3_project_id | — | **87** |
| R3_project_number | — | **28** |
| R4_credential_id_a | — | **6** |
| R4_credential_id_b | — | **6** |
| R5_iam_principal | — | **14** |
| R5_iam_sa | — | **16** |
| R6_home_path | — | **18** |

**この表は D-1 (iv) の (1) が置換する規模の見積りであり、置換表そのものではない。** 置換表はリポジトリ外の運用者記録にある。

### A.3 所要時間

| 走査 | 秒 |
|---|---|
| v1 (現行ツリー) | 0.893 |
| v2 (現行ツリー) | 0.888 |
| 履歴 | 0.049 |
| **合計** | **1.830** |

**pre-commit hook として実用に耐える速度である** (現行ツリー 1 走査で 1 秒未満)。

### A.4 R7 (個人名) は対象外である

**正規表現で表現できないため、スキャナは一切の試行を行わない。** 人手レビューに委ねる (台帳 L7-3)。**「検査していない」ことを明記するのが本項の目的である** — 0 件という結果と、検査していないことは違う。

---

## 13. 実施記録

(WP 完了後に確定する。集計行、WP ごとのコミット、受理境界、実測事項をここに置く。)

**本節の完成度 (2026-09-05、7-A 完了時点)**: **7-A (WP-1 / WP-2 / WP-3) は完了した**。各 WP について**成果物・レビュー/監査の件数と主要指摘・変異の実測 (ローカルと CI)・受理境界 (この WP で「実測できなかった」「固定しない」と決めた点)・監督裁定で決めた逸脱**を書いた。**逸脱の正本は作業指示書 `docs/work-orders/WORK_ORDER_PHASE7_EVIDENCE_AND_PUBLICATION_V1.md` §4 の訂正註 1〜6** であり、本節はそれを参照する (重複させない)。**7-B (WP-4〜WP-8) と WP-9 は未着手**であり、本節に該当項は無い。**残るプレースホルダは WP-2 の merge ハッシュ (`50c307f`) と 7-A 記録コミット自身のハッシュ (`本記録コミット。hash は次回引き継ぎ §1 に記載`) だけ**であり、監督がコミット後に埋める欄である — **本文中の事実に未確定は無い**。構成はフェーズ6 設計 §10 を踏襲する。**本節の起草者はテストも CI も実行していない** — レビュー・監査・変異の各ログと監督の CI 実測からの引用である。

**本節の完成度 (2026-09-06、7-B の WP-4 / WP-5 / WP-6 完了時点)**: **7-B のうち WP-4・WP-5・WP-6 は完了し main へマージした**。**WP-7 (i) は進行中**であり、**WP-8 / WP-9 は未着手**である。**7-B の逸脱の正本は作業指示書 §4 の訂正註 7〜10** であり、本節はそれを参照する (重複させない)。**7-B に残るプレースホルダは WP-7 の merge ハッシュ (`{WP-7}`) と 7-B 記録コミット自身のハッシュだけ**であり、監督がコミット後に埋める欄である。**本節の 7-B 分の起草者もテストと CI を一切実行していない** — 実装報告・独立コードレビュー・受け入れ監査の各ログと、監督の完了ゲート実測および CI 実測からの引用である。

**本節の完成度 (2026-09-06、WP-7 完了 + WP-8 記録時点)**: **7-B は WP-7 (i) の完了をもって閉じた**。**残るのは WP-9 公開ゲートだけ**であり、その着手条件は**依頼者の実行合図**である (他の条件はすべて満たされている。§9 / L7-12)。**WP-7 の逸脱の正本は作業指示書 §4 の訂正註 11** であり、本節はそれを参照する (重複させない)。**プレースホルダは WP-8 記録コミット自身のハッシュだけになった** — **`{WP-7}` は実ハッシュで埋め、7-A / 7-B の記録コミットのハッシュも埋めた**。**本節の WP-7 分の起草者もテストと CI を一切実行していない** — 実装報告・独立コードレビュー (`review-wp7.log` / `wp7-review-instructions.md`)・受け入れ監査 (`audit-wp7.md`)・仕分け記録 (`wp7-sorting.md`) の各ログと、監督の完了ゲート実測 (`wp7-gate.log`) からの引用である。**本 WP は製品コード・テストを 1 行も変更していない** (WP-8 禁止事項 1)。

### 13.1 集計行

```
# WP-1 (tree scan): mode=tree files_scanned=228 total_flagged=0 (所要 ~1.0s)
# 7-A の CI 基準 run 33962523499 (branch phase7-wp2 @ 12a0261、全 job 緑) — Python 3.11 job (正本)
1868 passed, 4 xfailed, 10 warnings in 378.88s (0:06:18)
# 同 3.12 job: passed / failed / skipped / xfailed の 4 数が同一 (tally-consistency job = success)
```

**集計行の出所と読み方**:

- **ローカルの完了ゲート (`pytest -q -n 5 --dist loadgroup` の単独実行) は 7-A では回していない。** 7-A の 3 WP は**収集対象のテストファイルを 1 本も足していない** (WP-1 は `tools/` と `docs/`、WP-2 は `.github/` と `constraints.txt` と `conformance-tests/README.md`、WP-3 は `r2db-api/deploy/` — いずれも root `pyproject.toml:3` の `testpaths` の外である)。**収集対象が不変であることは `--collect-only` の収集件数 1872 件 (= 1868 passed + 4 xfailed) の一致で確認した。**
- **したがって 7-A の正本の集計行は CI の 3.11 job の集計行である** (D-3、§6 (α) 確定)。**3.12 job は同一であることの担保に回り**、実装は**別 job `tally-consistency` が両 job の 4 数を突き合わせて赤になる**形を採った (**設計 D-3 / §6 (α) の字面は「食い違えば 3.12 job が赤」であり、実装は別 job である — 監督既決。設計側の訂正註としてここに記す**)。
- **「同一の集計行」の意味は「4 数 (passed / failed / skipped / xfailed) が同一」である。** 基準 run の逐語の集計行は経過秒が異なり (3.11 が `in 378.88s (0:06:18)`)、**経過秒を含む逐語一致は原理的に成立しない**。`conformance-tests/README.md` の "identical tally" もこの意味である。
- **着手時点との差**: 作業指示書 :1073 が 7-A の基準値として置くのはフェーズ6 完了時点の **1800 passed / 0 failed / 0 skipped / 0 xfailed** であり、その後 main に乗った値は **1802** である。CI 基準 run の **1868 passed / 0 / 0 / 4 xfailed** との差は **Q4 フェーズの main 反映によるもので、本フェーズの変更ではない** (台帳 **L7-17**)。**7-A の 3 WP は collection を 1 件も動かしていない。**
- **`10 warnings`** は `StarletteDeprecationWarning` 系の既存分である (§1.2)。**`filterwarnings` の有効化は WP-6 であり、7-A では有効化していない** (WP-2 禁止事項 3)。

**7-B の集計行 (2026-09-06、WP-4 / WP-5 / WP-6)**:

```
# 7-B 着手時点の main (Q4 完了 + main CI 緑化の後) — CI run 33991543611 @ 8b0e247、3.11 job (正本)
2165 passed, 10 warnings in 548.54s (0:09:08)
# WP-4 の完了ゲート (監督、ローカル単独実行 `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`)
2214 passed, 9 xfailed, 5 warnings in 191.23s (0:03:11)
# WP-5 の完了ゲート (同上)
2250 passed, 9 xfailed, 5 warnings in 148.26s (0:02:28)
# WP-6 の完了ゲート (同上)
2252 passed, 9 xfailed, 5 warnings in 149.65s (0:02:29)
# WP-4 マージ後の main — CI run 34004604310 @ 9ab4245、3.11 job (全 job success)
2214 passed, 9 xfailed, 10 warnings in 447.65s (0:07:27)
# WP-5 / WP-6 マージ後の main — CI run 34016273879 @ a090e80、3.11 job (5 job すべて success)
2252 passed, 9 xfailed in 436.49s (0:07:16)
# WP-7 の完了ゲート (監督、ローカル単独実行。7-B の最終値)
2265 passed, 9 xfailed, 5 warnings in 150.20s (0:02:30)
```

- **推移の内訳はすべて新設テストの分だけである**。**2165 → 2214** = WP-4 の新設 `test_c05_limit_declaration_agreement.py` (単体で `49 passed, 9 xfailed`) の **+49 passed** と **xfailed 0 → 9**。**2214 → 2250** = WP-5 の新設 5 ファイル (**新設 9 テスト関数 × 4 plug = +36**、内訳は c00 2 / c02 2 / c04 2 / c07 2 / c10 1 の各関数)。**2250 → 2252** = WP-6 の `conformance-tests/test_pytest_config_symmetry.py` の **2 本**。**`failed` と `skipped` は 3 つのゲートすべてで 0**、**`xfailed` は WP-4 が置いた 9 のまま WP-5 / WP-6 で不変**である。
- **CI との一致**: **WP-4 のマージ後の main の 3.11 job は、4 数 (passed / failed / skipped / xfailed) がローカルの完了ゲートと同一**である (`2214 passed, 9 xfailed`)。**`warnings` の数 (ローカル 5 / CI 10) は集計行の 4 数に入らない環境差**であり、一致の判定には用いない (13.1 の「同一の集計行」= 4 数、7-A から不変)。**WP-5 (`0650855`) と WP-6 (`a090e80`) のマージ後の main の run は、本記録の起草時点では監視中である。** **【監督追記 2026-09-06】WP-5 / WP-6 マージ後の main `a090e80` の CI (run 34016273879) は 5 job すべて緑、3.11 job の集計行は `2252 passed, 9 xfailed` (warnings 0 — constraints で httpx2 が入るため) で監督ゲート (`2252 passed, 9 xfailed, 5 warnings`、共有 venv に httpx2 無し) と 4 数一致。**
- **ローカルの `5 warnings`** は `r2db-api/tests/test_application_audit.py:42` が出す `StarletteDeprecationWarning` 5 件であり、**共有 `.venv` に `httpx2` が入っていない**ことによる (WP-6 は 3 つの `pyproject.toml` の `[test]` extras と `constraints.txt` に pin を置いたが、既存の共有 venv を作り直してはいない)。**これは WP-6 が有効化した `error::DeprecationWarning` の対象外である** — `StarletteDeprecationWarning` は `UserWarning` 派生だからである (D-4 の監督訂正、作業指示書 訂正註 8 の追記)。
- **【WP-8 追記 2026-09-06】WP-7 の完了ゲートで 7-B の推移は閉じた。** **2252 → 2265** の **+13** は、**新設 `conformance-tests/test_control_mapping_register.py` の 7 本**と**既存 `test_conditions_register.py` への追加 6 本**の合計ちょうどである (レビューが独立に算術を突合、監査が register の収集数 **17** = 原本 4 + 増分 13 で再確認した)。**`failed` と `skipped` は 7-B の 4 つのゲートすべてで 0**、**`xfailed` は WP-4 が置いた 9 のまま WP-5 / WP-6 / WP-7 で不変**である。**`5 warnings` の内訳は WP-6 の項に書いたとおり共有 `.venv` に `httpx2` が無いことによる `StarletteDeprecationWarning` 5 件**であり、**4 数には入らない環境差である** (CI 側は constraints で httpx2 が入るため 0)。**したがって 7-B 全体の推移は `2165 → 2214 → 2250 → 2252 → 2265` であり、増分はすべて新設テストの本数と一致する** — 既存テストの挙動は 1 件も動いていない。 **明示しておく受理境界が 1 つある**: **WP-7 のマージ後 (main `b2f9224`) の CI run は本記録の起草時点では記録されていない** — **本節が WP-7 について引く `2265 passed, 9 xfailed, 5 warnings` は監督のローカル完了ゲート (`wp7-gate.log`) だけであり、CI の集計行との突合はまだ取っていない**。**D-3 の「以後の完了ゲートは CI の集計行を正本の記録に引く」に対する例外であり、次に main の CI を確認したときに 4 数の一致を突き合わせること** (L7-6)。 **【監督追記 2026-09-06】WP-7 マージ後の main `b2f9224` の CI (run 34025563291) は 5 job すべて緑、3.11 job の集計行は `2265 passed, 9 xfailed` (warnings 0) で監督ゲートと 4 数一致 — 7-B の CI 突合はこれで閉じた。**
- **7-B の着手時点の基準値は `2165 passed / 0 failed / 0 skipped / 0 xfailed` である。** **台帳 L7-17 が「7-B (WP-4 以降) の基準値は 1868 passed / 4 xfailed であり、WP-4 が増やす xfail はこの 4 件の上に載る」と書いたのは 7-A 時点の見立てであり、実測とは合わない** — **Q4 WP-3 (`3d186a9`、「WP-0 strict xfails removed」) が当該 4 件を撤去した**ので、7-B の着手時点の `xfailed` は **0** だった。**したがって §7.4 と作業指示書 :1062 の「+ 着手時点の既存分」は 0 であり、WP-4 の xfail 9 件は 9 件のままゲートに現れる。** **L7-17 には日付付きの状態注記を置いた (§11)。7-A の実測 (1868 / 4) 自体は当時の事実として正しく、書き換えない。**

### 13.2 WP ごとの記録

- **WP-1** (`tools/public_value_scan.py` + `.pre-commit-config.yaml` 導入): ツリー走査は上記 13.1 の集計行のとおり `total_flagged=0`。対照 A (placeholder 除外 OFF) / B (ellipsis 除外 OFF) の flagged 件数はそれぞれ **7 / 8** (いずれも非ゼロ、除外が load-bearing であることの確認)。`--history` (`git log --all -p -m`、merge commit を含む) は commits_scanned 総 flagged **1061** 件。件数のみを記す (実値は転記しない)。

**7-A の commit / merge**:

| WP | 内容 | 実装コミット | merge コミット |
|---|---|---|---|
| **WP-0(docs)** | 設計 v1.2 + 作業指示書 v1.0/v1.1 | `a8ee013` | `8c982eb` |
| **WP-0(裁定)** | (α)(β)(γ) の確定記録 | — | `56f100e` |
| **WP-3** | (h) r2db 配備資産 | branch `phase7-wp3` | `dd08594` |
| **WP-1** | (g) 公開規律とスキャナ | `27f7d7f` | `448c660` |
| **WP-2** | (b) constraints と CI | branch `phase7-wp2` の `f391e75` + follow-up `4ea9a33` / `12a0261` | `50c307f` |
| **7-A 記録** | 本節・§11・作業指示書 v1.2・第13次引き継ぎ追記 | `788e9ed` | `b3bf310` |

**着手順の実際**: 設計 §12 の前倒し確定により **WP-1 / WP-2 / WP-3 を別 worktree で並列に走らせた**。**merge の順序は WP-3 → WP-1 → WP-2** であり、**発注上の依存順 (WP-1 → WP-2 → WP-3) とは逆である** — この食い違いが作業指示書 §4 **訂正註 1** (lint 本体の置き場所) の直接の原因である。**並列化の帰結であり、実装物の欠陥ではない。**

- **WP-1 (続き — レビュー・監査・受理境界)**: **独立レビューの指摘 11 件 (高 3 / 中 3 / 低 5)**、差し戻し 1 回。レビューは**規則ごとの対照実験**を自作し、各精密化を 1 つずつ無効化したときの flagged 件数 (`example_label` OFF → 18、`malformed_artifact` OFF → 58、`info_attr_chain` OFF → 1、`r6_empty_first_seg` OFF → 6) を指摘の根拠にした。主要な閉じ方は **(1)** `example` 許可を**第 1 ラベルが `example-project` のときだけ**に狭める、**(2)** アーティファクト許可を**その行に placeholder が実在するときだけ**に限る、**(3)** `--history` の exit code を実測し直す (実装担当の初回ログの `exit=0` はログ採取の誤りで、実測は `exit=1`) の 3 点である。**受け入れ監査は完了条件 14 項目**を判定し、**H-A (監査の新規指摘)** として「placeholder 判定が**行**単位なので、同一行に `<UPPER_SNAKE>` が 1 つでもあれば `--` / `..` / 先頭 `.`・`-` を含む実値がアーティファクト扱いで黙って除外される」抜け道を**合成値の探針 3 形で実測**し、あわせて当該箇所のコメントが**設計 D-2 に存在しない文言を根拠として引用していた**ことを指摘した。**是正は設計 D-2 の字面どおり「トークン粒度」へ寄せる方向を採った** — 是正後の再実測で、抜け道 3 形 (二重ハイフンの裸 FQDN / punycode の e-mail / deny-suffix ホスト) がいずれも **FLAG** になり、placeholder がホスト自身に掛かる正当なアーティファクトは**除外のまま**であること、および**ツリー 228 ファイル 0 件**が維持されることを確認した。**`/usr/bin/python3` (3.9.6) でも同一の集計行**が出ることを確認している (pre-commit hook が `python3` = システム Python を entry に持つため)。
- **WP-1 の受理境界**: **(i) R7 (個人名) は検査していない** — 出力末尾が明示するとおり「0 件」ではない (L7-3)。**(ii) ツリーモードは `git ls-files` の対象だけを見る** — 未追跡ファイルは検査されない (**L7-14**、pre-commit hook 側が担う)。**(iii) 完了条件 14 (集計行不変) の突合は 7-A の CI 基準 run で行った** — WP-1 単独のローカルゲートは回していない (13.1)。**(iv) レビュー指摘の逐条突合は行えていない** — 検証ログに指摘本文が残っておらず、監査はコードと文書の実体からの逆算で確認した。

- **WP-2** (`constraints.txt` + `.github/workflows/ci.yml` + `conformance-tests/README.md`。branch `phase7-wp2` の `f391e75` + follow-up `4ea9a33` / `12a0261` → merge `50c307f`):

  **実際に採った形** (発注と食い違った点は**実装が正**として記す):

  - **`constraints.txt`** は root 1 本・**19 行すべて `==` の exact pin** である。清浄 venv の `pip freeze` から **editable install で現れる 2 peer 自身の 2 行だけ**を除いた (`pip` / `setuptools` / `wheel` は当該 venv の freeze に現れなかった)。清浄 venv での `pip install -c constraints.txt -e ./r2db-api[test] -e ./MitateDB-api[test]` は成功し、`pip check` が `No broken requirements found` を返す。**両 peer の `pyproject.toml` の下限 pin は 1 行も触っていない。**
  - **CI** は PostgreSQL 16 を**専用 step の `docker run`** で起動し (`-c max_connections=300` をコマンド引数で直接渡す、合成パスワード、loopback 公開)、**`services:` キーは workflow 全体に不在**である。`R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` を **loopback TCP の DSN で上書き**する (既定値は unix socket なのでコンテナ PG に届かない)。**matrix は 3.11 / 3.12 の 2 job で、job / step とも `continue-on-error` を 1 つも持たない**。ゲートコマンドは `python -m pytest -q -n 5 --dist loadgroup` で**ローカルの完了ゲートと文字列一致**する。集計行は 4 数 + `summary_line` の JSON として job summary に出る。
  - **「3.12 が同一の集計行であること」の担保は別 job `tally-consistency`** が artifact 経由で両 job の 4 数を突き合わせる形で実装した (**監督既決**。設計の字面との差は 13.1 に記した)。
  - **トリガーは `push` (全 branch) + `workflow_dispatch` のみ**であり、**`pull_request` は置かない** (**訂正註 4** — 単独作業者で PR 運用が無く、CI の赤/緑の実測は監督が当該ブランチを push して行うので、二重起動そのものが生じない)。
  - **deploy-assets lint job は「枠」ではなく、`r2db-api/deploy/scripts/lint_deploy_assets.sh --require-tools` の呼び出しと必要な apt install を同梱した形**で着地した (**訂正註 1** — 並列着手により WP-3 が中身を書き込む先の workflow ファイルが存在しなかったため、lint 本体を script 側に置き、workflow は呼ぶだけにした。**WP-2 = job の枠、WP-3 = 検査の中身という境界そのものは保たれている**)。

  **レビューと差し戻し**: 独立レビューの指摘 **7 件 (中 4 / 低 3)**、差し戻し **7 項目すべて是正**。主要なものは **(1) 集計行抽出の非空ガード** (候補ゼロ / `in <N>s` の形状 / `error` 数の非黙殺 — 変異 3 の CI ログで実発火した)、**(2) `psql` クライアントの install** (adapter が実 `psql` を呼ぶ)、**(3) README への `psql` 要件の明記**、**(4) `permissions` / `concurrency` とトリガーの確定**、**(5) lint job の安定した id / name**、**(6) README の接続数記述をフェーズ6 の実測 (100 中 64 接続) に紐づける**、**(7) `[test]` extras の shell 引用**である。レビューは `ci.yml` の heredoc から**抽出器を逐語で切り出して机上実行**し、6 形の入力に対する挙動を指摘の根拠にした。

  **受け入れ監査**: 完了条件 **14 項目中 13 を充足**と判定し、**1 件を証拠不足**とした (完了条件 14 = 着手時点の main の集計行を記録した一次証拠が repo にも監査材料にも無い。13.1 でこれを埋めた)。監査は `gh run view` から集計行を自分で取得し直し、**基準 run と変異 4 本の失敗行を逐語で照合**した。監査自身の追加変異は **3 件 (机上、抽出器を逐語に切り出して実行)** である — **`no tests ran in 0.12s`** → **exit 1** (完全な collection 空振りも赤になる)、**集計行の直後に `replacing crashed worker gw3 …` を置く** → 本物の集計行を選ぶ (末尾行の誤選択が無い)、**`1 passed in 0.50s`** → **exit 0** (下記の受理境界)。

  **変異注入の結果 (すべて監督が CI 上で実測。ローカルでは再現しない性質のもの)**:

  | # | 変異 | run | 結果 |
  |---|---|---|---|
  | **1** | constraints に無いパッケージを import する一時テストを足す | 33961761737 | **赤** (3.11 / 3.12 とも `ModuleNotFoundError`。`tally-consistency` は `needs` により skipped) |
  | **2** | `max_connections` を 100 にする | 33961762443 | **赤** (3.11 / 3.12 とも接続枯渇 — `remaining connection slots are reserved for roles with the SUPERUSER attribute`)。**`max_connections=300` の要件は load-bearing であり、「変異なし」の記録は不要になった** |
  | **3** | DSN の loopback 上書きを外す | 33961763356 | **赤** (既定の unix socket に落ち、`required conformance adapter(s) failed to import or build; the suite fails rather than skips` で exit 4)。**skip ではない** — README の「未接続は fail」と一致する |
  | **4** | WP-1 の変異と同型の合成違反を含めて回す | 33961828701 | **scanner job が赤** (`R1_email:flagged = 1`、exit 1)。**先行試行 (未追跡の生成ファイル) は scanner が緑のまま**であり、**ツリーモード = `git ls-files` という契約どおり**であることを同時に実測した (**L7-14**) |

  変異用の branch (`phase7-wp2-mut1`〜`mut4`) は測定後に削除した。**合成の違反リテラルはコミットに 1 度も入っていない** (変異 4 は実行時生成 + `git add -N`)。

  **受理境界 (この WP で「固定しない」と決めた点)**:

  - **CI は集計行の値そのものを pin していない。** 監査の追加変異 `1 passed in 0.50s` が exit 0 で通るとおり、**収集が壊れて 1 件しか走らなくても、3.11 と 3.12 が同数なら `tally-consistency` も通り workflow は緑になる**。完了条件 14 が人手の監査照合である以上これは条件違反ではないが、**「期待集計行を repo に記録して CI で突き合わせる」恒久策は本フェーズでは採っていない**。
  - **job summary のレンダリング結果そのものは監査で再取得できない** (GitHub REST が返さない)。同一性はステップが `cat` する構造によって担保されている。
  - **`constraints.txt` の「手で整える」工程の判断はコミットに残らない** (L7-5)。除いたのが 2 peer 自身の 2 行だけであることは監査が freeze ログとの完全一致で確認したが、**constraints 自体の正しさは CI では測れない**。
  - **ゲート step の `python` は `setup-python` が解決したものである** (監督既決)。ローカルの `./.venv/bin/python` との**版の一致は matrix が担保し、パスの一致は担保しない**。
  - **job summary 書き出し step の末尾の無条件 `exit 0`** は、summary 書き込み自体の失敗を飲み込む。ゲート step と抽出 step が別に赤くなるので実害は無い。

- **WP-3** (`r2dbsvc-control.service` + nginx `location /control/v1/` + operator script + runbook。branch `phase7-wp3` → merge `dd08594`):

  **実際に採った形** (発注と食い違った点は**実装が正**として記す):

  - **control unit** はコメント・空行を除いた directive diff が既存 `r2dbsvc-api.service` と **3 行** (`Description=` / `EnvironmentFile=` / `ExecStart=`) しか違わない。hardening 節と `PrivateTmp` の posture B 注意書きを同型で持つ。**`EnvironmentFile` は placeholder にせず literal パスのまま**とした (**訂正註 2** — 既存 unit が literal で書いており、新設 unit だけを伏字にすると完了条件 1 の同型性照合と衝突する。**placeholder 化の対象は unit 名と port に限る**)。
  - **nginx** は `location /control/v1/` を追加し、**`/v1/` と proxy_* 6 項目が完全一致**する。`listen 8443 ssl http2;` の **nginx 1.24 互換記法**であり、分離形 `http2 on;` は 0 件である。`:86-98` の「このテンプレートにはまだ含まれていない」コメントは追加と同時に置換した。
  - **operator script は 3 本ではなく 4 本**である (**訂正註 3** — part1 / part1b / part2 に加え、訂正註 1 の帰結として **`lint_deploy_assets.sh`** が同ディレクトリに入った)。`bash -n` は**新設 4 本すべて**に掛かる。part1 は `R2DBSVC_API_PASSWORD` を含む **13 変数の必須検査** (`require_var`) を持ち、**未設定・未解決 placeholder のいずれでも一切の変更前に停止する**。
  - **lint は `systemd-analyze verify` / `nginx -t` / `bash -n` の 3 検査に、`shellcheck` と check 4 (`ExecStart` 非空虚検査) を足した 5 検査**であり、**`--require-tools` モード**を持つ (**訂正註 6** — **監督が事後承認**。設計 D-5 が挙げる 3 検査は撤去せず、その上に足す形である)。
  - **runbook** は §7 の「第二 unit を作れ」という散文指示をテンプレート参照へ置き換え (grep 0 件)、`:105` の stale な「Python 3.11 virtualenv」を `requires-python (>=3.11)` を満たす版という表現へ改め、**具体の版を書く箇所を CI matrix と配備記録に一本化**した。
  - **`r2db-api/deploy/env/*.example` は 1 バイトも触っていない** (`git diff --stat` / `git status --porcelain` のいずれにも現れない。Q4 WP-D との唯一の重なりを 0 にする条件。§12)。

  **レビューと差し戻し**: 独立レビューの指摘 **7 件 (重大 2 / 中 4 / 軽 1)**、差し戻し 1 回。**重大 1** = part1b が **bootstrap の非 0 終了を無条件に「既存 credential あり」と読んで reset 儀式へ落ちていた** → **`error: CONFLICT:` の文字列で分岐**し、非 CONFLICT は stderr を verbatim に出して停止、**CONFLICT 確定後も `R2DBSVC_ALLOW_CONTROL_RESET=1` の opt-in が無ければ停止**する形へ。**重大 2** = `nginx -t` が実在しない証明書パスを見ていた → **使い捨ての自己署名証明書を openssl で生成して sed 置換**し、`trap` で破棄する形へ。**中** の代表は part2 の `verify_401` が **非 401 応答を捕まえていなかった**点 (fake curl が 200 を返しても `part 2 complete` まで到達した) で、`%{http_code}` を読んで `!= "401"` で停止する形へ是正した。レビューは自作の変異 (`reject_placeholder_in_file` の無効化、`require_var` ループの削除) で「検出されない」ことを実測してから指摘している。

  **受け入れ監査**: 完了条件 **13 項目**を判定し、**未充足 0**、**証拠不足 4** (完了条件 5 / 9 の一部 = CI 待ち、10 の正規手段 = WP-1 待ち、13 = 監督ゲート待ち) とした。監査はリポジトリの複製に対してのみ作業し、`r2db-api/deploy` 全 10 ファイルの sha256 を監査前 / 後 1 / 後 2 で照合して**本体無変更**を確認している。**監査自身の追加変異 3 件**:

  | # | 変異 | 結果 |
  |---|---|---|
  | **X1** | part1b の CONFLICT 判定を `*'error: CONFLICT:'*` → `*'error:'*` に緩める | **DB 接続エラーの stderr が CONFLICT と誤判定され、opt-in 済み環境で reset 儀式が起動した** — 判定文字列は load-bearing |
  | **X2** | part2 の `!= "401"` 比較を無効化 | **200 を返すバックエンドが「part 2 complete」として素通り** — 比較は load-bearing (重大指摘の是正が空振りでないことの確認) |
  | **X3** | lint の sed をテンプレートへ適用し、残存 placeholder / 旧証明書パス / 分離形 `http2` / brace 平衡を機械照合 | 残存 **0 件**、brace **4/4**、分離形 **0 件** — `nginx -t` の前提が構文水準で満たされていることの確認 |

  監査はあわせて **3 件の所見** を残した — **F-1 (中)**: runbook が part1b について「既存 credential があれば**自動的に** reset 儀式へ落ちる」と断言しているが、実装は opt-in が無ければ停止する (**破壊的操作の記述なので runbook 側を opt-in 込みへ揃える**)。**F-2 (小)**: part1 の usage コメントが具体の Python 版を書いており、runbook の「版を書く箇所は 2 箇所」という主張の 3 箇所目になっている。**F-3 (小)**: part1b の declaration step が `set +e` で囲まれ rc を検査していない。 **→ 3 件とも監督裁定で受理前に修正し (runbook の part1b 記述を opt-in 込みへ、usage の具体版を削除、declaration step の rc 検査 = 期待 2 以外は停止、fake ops で rc 9 の素通りが再現しないことを実測)、WP-3 のコミット `dd08594` に含めた。**

  **変異注入の結果**:

  | # | 変異 | 実測 |
  |---|---|---|
  | **1 (ローカル)** | `ExecStart` を存在しない module path へ向ける | **本機では `systemd-analyze verify` が動かないため測れない**。**check 4 (`ExecStart` 非空虚検査) が赤**になることで代替した |
  | **2 / 3 (ローカル)** | nginx の `proxy_pass` を壊す / script の構文を壊す | 3 は `bash -n: FAIL` → **RC 1**。2 は本機に nginx が無いため CI 待ち |
  | **`--require-tools` (ローカル)** | ツール不在の環境で強制モードを掛ける | `systemd-analyze verify: FAIL` / `nginx -t: FAIL` → **RC 1** (「緑なのに何も検証していない」穴が塞がっていることの実測) |
  | **L1 (CI)** | control unit の `ExecStart` を存在しない module へ向ける | run 33962527777 — **`ExecStart` 非空虚検査だけが FAIL**。**`systemd-analyze verify` は module パスを見ないので PASS のまま**であり、**check 4 が当該完了条件を担う唯一の検査**であることが実測された |
  | **L2 (CI)** | `location /control/v1/` の `proxy_pass` を綴り違いにする | run 33962529260 — **`nginx -t` が FAIL** (`unknown directive "proxy_pazz"`) |
  | **L3 (CI)** | 分離形の `http2` ディレクティブを置く | run 33962530314 — **`nginx -t` が FAIL** (`unknown directive "http2"`。runner の nginx 1.24.0 / ubuntu-24.04) |

  変異用の branch (`phase7-wp3-mutL1`〜`L3`) と作業 worktree は測定後に削除した。

  **CI 初回 run で見つかった実バグ 5 件と是正** (基準 run 33961202682 の deploy-assets lint job は **failure** だった。**本機で緑だった lint が CI で 5 箇所落ちた**もので、**設計・発注の誤りではなく実装の実バグ**である。是正は follow-up `4ea9a33` / `12a0261`):

  1. **`nginx -t` が `/run/nginx.pid` を書けない** (runner の権限) → **一時 main conf に `pid` と `error_log` を置く**形へ。
  2. **同じく `/var/log/nginx/access.log` を書けない** → 一時 main conf に `access_log` を置く形へ。
  3. **shellcheck が SC1072 / SC1073 を出す** — **`# shellcheck` で始まる散文コメント**を shellcheck が directive として解釈していた → コメントを書き換えた。
  4. **`systemd-analyze verify` が `Command … is not executable: No such file`** — runner に実バイナリが無い → **scratch の unit コピー (`ExecStart` を stub 化、`EnvironmentFile` を空)** に対して verify する形へ。
  5. **shellcheck の SC2317 (到達不能コード)** → disable directive を置いた。

  是正後の run 33962523499 では **`systemd-analyze verify` / `nginx -t` / `bash -n` / `shellcheck` / `ExecStart` 非空虚**の 5 検査がすべて PASS である。

  **受理境界 (この WP で「実測できなかった」「固定しない」と決めた点)**:

  - **`systemd-analyze verify` は unit の構文しか見ず、`ExecStart` が指す module パスの実在を検証しない。** L1 の実測がこれを確定させた — **完了条件 2 (`ExecStart` が `uvicorn r2db_api.control_main:app` を指す) を赤にできる検査は check 4 だけ**であり、**check 4 は設計 D-5 に無い拡張である** (訂正註 6、監督が事後承認)。設計 D-5 の 3 検査だけでは当該条件に対応する変異が成立しない。
  - **lint ツールの版は runner 依存である** (**L7-16**)。分離形 `http2` が赤になるのは **nginx 1.24.0 / ubuntu-24.04** の性質であり、**runner の nginx が上がれば L3 は緑に転じ得る** — その時点で「1.24 互換記法」という完了条件 4 の意味が変わる。
  - **配備資産は合成値から書き起こしたものであり、実機の原本との一致は保証されない** (L7-11)。**運用者が原本と突合するのは任意の検証**であり、本フェーズの完了条件ではない。lint が担保するのは**テンプレートとして構文が妥当であること**までである。
  - **完了条件 10 (新規資産に実値 0 件) の正規手段は WP-1 のスキャナ**だが、WP-3 の監査時点では WP-1 が未着地だったため**監査が手動スキャンで代替**した。**WP-1 / WP-2 着地後の CI 基準 run で `public-value scan (tree mode)` が緑**になっており、正規手段による確認は 13.1 の基準 run が担っている。
  - **成果物 1 の字面 (「`EnvironmentFile` は placeholder」) と実装は食い違う** — 同型性 (完了条件 1) を優先した (訂正註 2)。**発注時の記述は書き換えず、差を残す。**

- **WP-4** ((a) C-05 の共通化 + (e) 隔離 surface の資源検査。port v1.11、`conformance-tests/test_c05_limit_declaration_agreement.py` 新設、`MitateDB-api/src/mitatedb_api/cell.py` の欠落 4 class 追加、`test_c14_authority_boundary.py` の stale 注釈訂正、`CONDITIONS.md` C-05 行更新、`CONFORMANCE_ADAPTER_V1.md` §21 新設。**実装 (Sonnet) に加え、独立コードレビュー (Opus) 1 回・差し戻し 2 回・受け入れ監査 (Opus) 1 回を実施済み** — 本節はそれらの指摘への対応記録を含む)：

  **§D-6.5 追補**: 既に監督承認済み (2026-09-06、本文書 D-6.5 冒頭) — 着手条件は満たされていた状態で着手した。

  **D-6.2 の駆動レシピ・検査形 実測結果表** (起草時点の見立てからの変更点に下線):

  | class | 検査形 (実測後) | r2db-api (両plug) | MitateDB-api (in-process) | MitateDB-api-http |
  |---|---|---|---|---|
  | `batch_items` | 両側 | 駆動 (N=`limits.batch_items`、`attempt_batch_with_addresses`) | 駆動 | 駆動 |
  | `schema_objects` | 両側 | 駆動 (`create_entity` 連打。**実測**: 1 エンティティ (1 field) 消費量は r2db **3** (entity 自身 1 + 自動付与される `id` field 1 + 宣言 field 1)、MitateDB **1** (`schema_count()` はテーブル数のみ)) | 駆動 | 駆動 |
  | `operation_depth` | 両側 (r2db のみ) | 駆動 (`operation_depth=4` の隔離 profile。N=平坦な `insert` 一発 (自然に深さ4)、N+1=同じ `insert` に (意味論上は無効な) `where` を追加 -- `check_depth` が「insert は where を受けない」判定より先に走るため実際に `LIMIT_EXCEEDED`/`operation_depth` が返ることを実測) | **駆動しない** (`unavailable`。実測根拠は下記) | **駆動しない** (同上) |
  | `requests_per_minute` | 両側 (r2db のみ) | 駆動 (**実測**: 両 HTTP plug の `authenticate()` は実 `GET /v1/capabilities` を送るため、隔離窓の 1 unit を先に消費する -- 位置一致の期待値は in-process `bound`、HTTP `bound-1`) | **駆動しない** (`unavailable`) | **駆動しない** (同上) |
  | `batch_entities` | 両側 (MitateDB のみ) | **適用外** (`cross_entity_mutation: unavailable`、V1(e) の capability 条件付き対象外) | 駆動 (`attempt_cross_entity_batch`、N=distinct entity 数) | 駆動 |
  | `request_bytes` | 片側 | 駆動 (両 plug とも `enforced`) | **駆動しない** (`unavailable`、V1(d) の非変異対照そのもの) | 駆動 (`http.py:591` の HTTP 面上書き) |
  | `result_items` | <u>両側 (r2db のみ、差し戻し指示 5(a) で片側から訂正)</u> | 駆動 (`select_eq` の一致行数。**訂正 (レビュー指摘 F5(a))**: `_drive_result_items` は宣言値ちょうどの件数を挿入して一致行数を確認したうえで、+1 件目で拒否を確認する位置一致 (両側) 駆動であり、起草時点で「片側」と分類していたのは実装と食い違っていた -- `batch_items`/`schema_objects` と同型の両側形である) | **駆動しない** (MitateDB での未駆動理由は変わらない。**実測**: `cell.py` の `result_items` 検査は要求された limit/page パラメータの値を見るのみで、実返却行数は見ない。この port に limit/page を渡す引数が無いため、port 経由でこの検査に到達する要求を構成できない) | **駆動しない** (同左理由) |
  | `query_complexity` | 片側、<u>r2db のみに格下げ</u> | 駆動 (`select_eq` の `select` 列長のみで複雑度を積み増せる。`len(where)+len(select)+order_by_count`) | **駆動しない** (**格下げ理由、実測**: `cell.py` の複雑度は `len(filters)` のみで、port の `attempt_filter`/`select_eq` は 1 呼び出しにつき述語 0 または 1 個しか送れないため、`max_filter_terms` を超える要求を port 経由で構成できない) | **駆動しない** (同左理由) |
  | `execution_ms` / `concurrency` / `idempotency_retention_ms` | 駆動しない (起草時点の見立てのまま) | 同左 | 同左 | 同左 |

  **`operation_depth` の枝の判定と根拠**: **`unavailable`** (第二の枝)。根拠 (`file:line`): `MitateDB-api/src/mitatedb_api/*.py` 全体を `depth`/`nest` で走査した結果、`cell.py`/`backend_sqlite.py`/`backend_postgres.py` のいずれにも操作・フィルタのネスト深さを計測または拒否する実装コードが 1 つも無い (ヒットはすべて "defence-in-depth" 等、無関係なコメント文字列)。対照的に r2db は `r2db-api/src/r2db_api/limits.py:77-92` (`ResourceLimits.check_depth`) が実装済み・実際に呼ばれている (`service.py:997`/`:1038`/`:1073`)。したがって `operation_depth` を V3 の xfail と L7-1 の 4 番目の class として扱う。**推測ではなく実装の不在を直接確認した。**

  **`limit_enforcement` に追加した MitateDB の 4 class**: `execution_ms` / `concurrency` / `requests_per_minute` = `unavailable`、`operation_depth` = `unavailable` (上記実測)。宣言追加と V1 (e) を同一コミット相当の作業単位で行った (裁定 (β) 準拠。実際の commit は監督が行う)。

  **xfail 件数**: **9** (`operation_depth` が `unavailable` の枝に落ちたため)。内訳: `MitateDB-api` (in-process) 5 本 (`execution_ms`/`concurrency`/`requests_per_minute`/`operation_depth`/`request_bytes`)、`MitateDB-api-http` 4 本 (`execution_ms`/`concurrency`/`requests_per_minute`/`operation_depth`)。

  **完了ゲート実測 (WP-4 rework 2026-09-06、差し戻し 2 巡目で現物に更新 -- 監査 wp4-audit.md §1 条件 16/21 の指摘どおり、下の値は初回実装時の `51`/`526` ではなく F7 の重複削除 (-4) と F8/F9 の pin 2 本追加 (+2) を反映した現物である)**:
  - `./.venv/bin/python -m pytest -q conformance-tests/test_c05_limit_declaration_agreement.py` → `49 passed, 9 xfailed` (単体で 5 回連続実測、全て緑。監査も独立に再実測し一致)
  - `./.venv/bin/python -m pytest -q conformance-tests/` (全 condition) → `524 passed, 9 xfailed` (`-n 5 --dist loadgroup` でも同一集計行、`~72-78s`。監査も独立に再実測し一致)
  - `./.venv/bin/python -m pytest -q conformance-tests/test_c14_authority_boundary.py` → `20 passed` (無変更)
  - `./.venv/bin/python -m pytest -q conformance-tests/test_c05_limit_declaration_agreement.py conformance-tests/test_c14_authority_boundary.py` → `69 passed, 9 xfailed`
  - `./.venv/bin/python -m pytest -q conformance-tests/test_c05_limit_declaration_agreement.py conformance-tests/test_c14_authority_boundary.py conformance-tests/test_c15_bootstrap_reset_lifecycle.py` → `89 passed, 9 xfailed` (旧記録の `91` は `49`ではなく`51`を基に計算されていた値のままの陳腐化 -- 差分 `-2` は c05 単体の差分 `51→49` と一致)
  - `./.venv/bin/python -m pytest -q MitateDB-api/tests` → `756 passed`
  - `./.venv/bin/python -m pytest -q r2db-api/tests` → `934 passed, 1 warning` (既存の httpx2 非推奨警告、本 WP 無関係)

  **実装中の発見と修正 (第一次実行の実発見、設計・発注の誤りではない)**:

  1. **共有プラットフォームの `applications` レジストリ汚染**: `isolated_application_surface()`（HTTP 2 plug）が provisioning する throwaway application が、C-14 vector 5 が読む同一の共有 PG platform `applications` テーブルへ書かれ、後続の C-14 実行で `n_existing < apps_limit` 前提が破れた (実測: 107 vs 100)。是正: 各 plug の `isolated_application_surface()` の `finally` で自身が provision したアプリケーションを `deprovision_application` で解放するよう変更 (プール接続を先に close してから deprovision -- 順序が逆だと「being accessed by other users」で失敗することも実測)。
  2. **隔離 profile の `request_bytes=200` が通常の setup 要求自体を落とす**: `create_entity` 1 回のバイト見積り (r2db の `len*4`/コンテナ2 の式) だけで約 230 に達し、200 の bound を割り込む前に落ちた。是正: `request_bytes` を 4096 へ引き上げ (`_MAX_EXERCISABLE_LIMIT`=200 の適用対象は count 系 class のみとし、byte 系 class には適用しない旨を明記)。
  3. **`schema_objects` の per-entity 消費単位が peer で異なる**: r2db は「entity 自身 1 + 宣言 field 1 + 自動付与 `id` field 1 = 3」、MitateDB は「テーブル 1 個 = 1」。実測して `_schema_objects_unit_cost()` に反映。
  4. **`requests_per_minute` の headroom**: HTTP 2 plug の `authenticate()` が実 `GET /v1/capabilities` を送るため隔離窓を 1 消費する。in-process は消費しない。実測して期待値を `bound`／`bound-1` に分岐。

  **変異注入の結果 (実装担当が全 plug で実測。scratchpad backup からの復元 + sha256 二重照合 + 変異文字列全文 grep ゼロ確認を徹頭徹尾行った)**:

  | # | 変異 | 対象ファイル | 結果 |
  |---|---|---|---|
  | **1** | `limits` に値だけあり `limit_enforcement` 欠落の class を追加 (r2db `service.py` の `limits` 辞書に `idempotency_entries: 5` を追加) | `r2db-api/src/r2db_api/service.py` | **赤** (`test_c05_v1_application_plane_self_consistency[r2db-api]` — V1 (b)) |
  | **2** | `enforced` class の `limits` 値を 0 にする (`batch_items: 0`) | 同上 | **赤** (同テスト — V1 (c)) |
  | **3** | MitateDB の固定 9 のうち 1 class (`execution_ms`) を `limit_enforcement` から削除 | `MitateDB-api/src/mitatedb_api/cell.py` | **赤 2 件** (`test_c05_v1_application_plane_self_consistency[MitateDB-api]` と `[MitateDB-api-http]` -- 両 plug とも同じ `cell.py` の宣言を読むため同時に赤くなる。**V1 (e)** (`execution_ms` はそもそも `limits` に値を持たないので (b) には触れず、(e) の必須集合チェックが直接捕まえる) |
  | **3 (差し戻し指示 10、r2db 側でも実測)** | 同じ操作を r2db 側で構成 (`固定9のうち1class(batch_items)をlimit_enforcementから削除`、`limits`は元のまま): `r2db-api/src/r2db_api/service.py`の`"limit_enforcement": {name: ... for name in self.limits.as_dict()}`を`if name != "batch_items"`付きへ一時変更 | `r2db-api/src/r2db_api/service.py` | **赤 2 件、ただし V1 (e) ではなく V1 (b)** (`test_c05_v1_application_plane_self_consistency[r2db-api]` と `[r2db-api-http]` -- `limits`/`limit_enforcement`が同じ`self.limits.as_dict()`から作られるため、r2db では固定9のクラスは必ず`limits`に実値を持ち、`limit_enforcement`だけを落とす操作は必然的に「`limits`に値があるのに`limit_enforcement`が無い」V1(b)違反を先に作ってしまう -- V1(e)の必須集合チェックに到達する前に(b)で止まる。**レビュー指摘F10の文言「変異3はr2db側でもV1(e)で2件赤」は red の件数(2件)は正しいが、実際に発火する条件は(b)であって(e)ではない -- MitateDBは対象4classが`limits`に値を一切持たないため(b)を素通りして初めて(e)に到達するのに対し、r2dbは全9classが常に`limits`実値を持つため、同じ形の「削除」変異では(e)に到達する前に必ず(b)で捕まる、という構造の違いを本記録は正確に記載する (F5(a)/(b)の是正と同じ「実測が起草時点の想定と食い違ったら記録を実測で正す」規律)。`test_c05_v1_d_unavailable_class_may_still_publish_a_limits_value[r2db-api]`/`[r2db-api-http]`も同時に赤くなる (差し戻し指示6でこのテストが`_assert_v1_self_consistency`を実際に呼ぶようになったため、副次的に(b)違反を拾う -- 4件赤のうち2件はこちら)。 |
  | **12** | `limit_enforcement` に語彙外キー `not_a_class` を追加 | `r2db-api/src/r2db_api/service.py` | **赤** (同テスト — V1 (a)) |
  | **4** | 宣言値 N を +1 して実挙動と食い違わせる (`limits.batch_items + 1` を報告、実施行は元のまま) | 同上 | **赤** (`test_c05_v2_declaration_and_position_agree[r2db-api]` — `_drive_batch_items` の N 成功呼び出し自体が `LIMIT_EXCEEDED` で失敗) |
  | **5** | `details.limit_class` を別名にする (`"renamed_" + kind`) | `r2db-api/src/r2db_api/limits.py` (`check()`) | **赤** (同テスト — `_assert_limit_exceeded` の `limit_class` 一致検査) |
  | **6** | MitateDB in-process の `request_bytes` を `unavailable`→`enforced` と偽る (実装は無いまま) | `MitateDB-api/src/mitatedb_api/cell.py` | **赤** (`test_c05_v2_declaration_and_position_agree[MitateDB-api]` — `_drive_request_bytes` の「明らかな超過が拒否される」side が `DID NOT RAISE` で失敗。**交差規則が偽の宣言を捕まえた**) |
  | **7** | ある plug の宣言を全 class `unavailable` に倒す (`limit_enforcement` 全体を `{name: "unavailable" ...}` に) | `r2db-api/src/r2db_api/service.py` | **赤** (`test_c05_v2_declaration_and_position_agree[r2db-api]` -- **訂正 (WP-4 rework、指示 7/F7 適用後)**: 本行が起草時点で挙げていた `test_c05_v2_per_plug_nonvacuity_would_be_caught[r2db-api]` は F7 の重複削除で既に存在しない。完了条件 12 (V2 の per-plug 非空性) は同テストが自前で持つ `assert driven_classes, f"{{adapter.name}}: test_c05_v2's own sweep drove zero classes -- would be vacuous"` (`test_c05_limit_declaration_agreement.py:683`) 1 本が担い、この変異はまさにその assert で赤くなる -- 駆動 class 0 で非空虚 guard が発火) |
  | **8** | headroom 前提 (setup 消費分の控除) を外す (`already_consumed = 0` に固定) | `conformance-tests/test_c05_limit_declaration_agreement.py` | **赤** (`test_c05_v2_declaration_and_position_agree[r2db-api-http]` — 位置が 1 ずれて `49 == 50` の assert が失敗) |
  | **9** | MitateDB の `operation_depth` を `unavailable`→`enforced` (L7-1 実装が入った状態を模す) | `MitateDB-api/src/mitatedb_api/cell.py` | **赤** (`test_c05_v3_fixed_nine_are_not_unavailable[MitateDB-api-operation_depth]` — `[XPASS(strict)]` で `strict=True` が失敗に変換) |
  | **10** | 変異 9 を維持したまま該当 xfail の `strict=True` を `strict=False` に緩める | `conformance-tests/test_c05_limit_declaration_agreement.py` | **緑のまま** (`1 xpassed`、失敗にならない — `strict=True` が load-bearing であることの確認) |
  | **11** | 隔離 surface の close を外す (MitateDB in-process、`fresh._control.cells` の `_backend.close()` 呼び出し削除) | `MitateDB-api/conformance/conformance_adapter_mitatedb.py` | **赤** (`test_c05_e_isolated_application_surface_releases_resources[MitateDB-api]` — 閉じたはずの sqlite 接続が `DID NOT RAISE`) |
  | **11 (差し戻し指示 1、r2db-api-http で再実測)** | `isolated_application_surface()` の `finally` から `for cell in iso._provisioned_cells: cell.close()` を削除 | `r2db-api/conformance/conformance_adapter_r2db_http.py` | **赤** (`test_c05_e_isolated_application_surface_releases_resources[r2db-api-http]`)。**訂正 (WP-4 rework 2026-09-06、完了条件 15/F1、監査 wp4-audit.md §2 条件 15 の指摘どおり)**: 本行が起草時点で逐語引用していた `"...before=0, during=7, after=7..."` (`wp4-rework-mut1.log` 系列) は、当時の計数対象がまだ `<prefix>%` (共有 control プールを含む) のままだった実測であり、**無変異の対照ですら「冷たいプロセス」では同じ `after != before` で赤くなる**ため、単独では是正効果の証拠にならなかった (監査が確定的な再現で指摘: 単体選択 5 回が 5 回とも赤)。**有効な証拠は `wp4-rework-mutD-v2.log` の逐語**: `"...before=7, during=9, after=9..."` (`assert 9 == 7`) -- こちらは「温まった」状態 (先行テストが共有プールを開いた後) での実測であり、隔離 instance 自身の 2 本 (`PostgresCell` の `pool_size=2`) が解放されないことを正しく検出している。**是正後 (`_live_pg_backend_count(datname_like)` を当該隔離 instance が provision した application DB 1 個に限定、監督裁定 1 実施後) の新しい実測**: 同じ変異を再注入して確認した逐語 --  `"r2db-api (http+postgres): live PG backend count did not return to baseline after isolated_application_surface() exit (before=0, during=2, after=2); __exit__ itself also raised: RuntimeError('psql failed running 0004_deprovision_application.sql:\n assert_no_credentials_for_deprovision \n---------------------------------------\n \n(1 行)\n\n pg_terminate_backend \n----------------------\n(0 行)\n\n\npsql:...0004_deprovision_application.sql:102: ERROR:  database \"r2dbhttp...\" is being accessed by other users\nDETAIL:  There are 2 other sessions using the database.\n')"` (`assert 2 == 0`)。**是正後は計数が常に `0`/`2`/`2` の形に収束し、単体選択 5 回・モジュール全体のいずれでも無変異なら緑、変異注入なら確定的に赤**であることを確認した (scratchpad `wp4-final-mutation.log`)。**これが指示1の是正効果そのもの**: 修正前は deprovision の RuntimeError がテスト本体を素通りで落とし `after == before` の assertion に到達しなかった (レビュー指摘 F1)。修正後は `__enter__`/`__exit__` を手動駆動しているため、`__exit__` 自身が RuntimeError を送出しても `after` は取得され、資源リーク (`after != before`) の assertion が主たる失敗として発火し、RuntimeError はメッセージに付記されるだけになる。 |
  | **C (裁定 2 回目、MitateDB-api-http)** | 同じ close 除去を MitateDB-api-http 側 (`isolated_application_surface()` の `finally` から `cell._backend.close()` ループを削除) に適用 | `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` | **緑のまま** (`test_c05_e_isolated_application_surface_releases_resources[MitateDB-api-http]` PASSED -- close 除去後も `before`/`after` が一致する)。**受理境界として開示 (テストを歪めて赤にする対応は取っていない)**: 原因は `0004_deprovision_application.sql` が `pg_terminate_backend` を自前で発行し、close の有無に依存せず対象データベースへの接続を強制終了するため。`CONDITIONS.md` C-05 行と `CONFORMANCE_ADAPTER_V1.md` §21.1 にこの旨を記載した。 |
  | **対照 D** | MitateDB in-process の `request_bytes` を「値あり (`cell.py:1491`) + `unavailable` (`:1502`)」のまま無変更で実行 | (非変異) | **緑** (`test_c05_v1_d_unavailable_class_may_still_publish_a_limits_value[MitateDB-api]` が全 plug 込みで pass。撤回した規則は復活していない) |
  | **対照 E** | `unavailable` の明示宣言は基準状態で既に存在する (追加の変異なし) | (非変異) | **緑のまま XPASS しない** (基準の `9 xfailed` がそのまま維持されることで確認 -- xfail の先置きと宣言追加が同居できることの実測) |

  すべて変異後に scratchpad backup から `cp` で復元、`sleep 3`、`shasum -a 256` で復元後ハッシュが backup と一致することを確認、`grep -rn` で変異文字列 (`not_a_class`/`renamed_batch_items`/`mutation_test_v1b`/`MUTATION 8`/`MUTATION 10`/`MUTATION 11`) がリポジトリ全体で 0 件であることを確認した。`git status --short` は変異注入後・復元後のいずれも意図した差分 (WP-4 の実装差分 + 新設ファイル 1 件) とのみ一致する。

  **禁止事項の遵守状況**: 契約 (`spec/`) は無変更 (git diff 0)。V2 の駆動集合は宣言から導出 (固定リストなし)。V3 の parametrize 基底は静的固定 9 (宣言由来にしていない)。skip は使用していない (`skipped` は完了ゲートで一貫して 0)。`xfail` の `strict=True` を落としていない (変異 10 で確認のうえ復元)。C-14 の assert は soft のまま (注釈のみ訂正)。C-16 の assert は参照のみで二重化していない。肯定側 idempotency primitive は追加していない (`idempotency_key` optional field 1 つのみ)。MitateDB の資源上限は実装していない (4 class はすべて `unavailable`)。(β) は宣言追加と検証を本 WP に同梱 (7-A への先出しなし)。

  **疑義 (両論、監督裁定を要する可能性がある点)**:

  1. **`result_items`/`query_complexity` の MitateDB 2 plug 分の格下げ (片側→駆動しない)** は D-6.2 が「起草時点の見立てであり実装 WP が確定する」と明記する範囲内の措置と判断し実施したが、設計文書 D-6.2 の表そのものは書き換えていない (本記録が正本)。CONDITIONS.md の開示にはこの格下げ理由を反映済み。**設計文書 D-6.2 の表自体を書き換えるべきか (対応表としての一致を取るか) は監督判断を要する。**
  2. **`_MAX_EXERCISABLE_LIMIT` (200) を byte 系 class (`request_bytes`) に適用しない扱い**は work order 完了条件 13(a) の字面 (「各駆動 class の limits 値が...以下であること」) から離れる判断であり、根拠 (200 バイトでは通常の setup 要求自体が成立しない、実測) を報告に明記したが、**この解釈が妥当かは監督判断を要する**。
  3. **独立コードレビュー (Opus) 1 回・差し戻し 2 回・受け入れ監査 (Opus) 1 回を実施した。** 使用テンプレート欄が指定する体制 (実装 Sonnet / レビュー Opus / 監査 Opus) の 3 者はいずれも完了しており、本節の各対応記録 (指示 1〜10、裁定 1・2 回目) がその実施の証跡である。
  4. **`isolated_application_surface()` の資源共有範囲 (D-6.5 の「推測」欄)**: 本実装は HTTP 2 plug で `copy.copy(self)` により control-plane 状態・credential store・platform を共有し、data-plane (`_service`/`_app`/`_client`/`_cells` 等) のみ新規にした。D-6.5 が「決めるのは WP-4 である」としていた点への回答であり、この配分が設計意図と一致するかは監督確認を要する。

  **差し戻しラウンド 2 (Opus コードレビュー 1 回目の指摘 F1〜F10、差し戻し指示 1〜10、監督裁定 2 回目) の対応記録** (実装担当 Sonnet、2026-09-06。前任者はレビュー本文を読めずログのみで作業したため、指示 1・2・3・9・13(b) 相当分は現物で対応済みを確認し、4・5(a)(b)(c)・6・7・8・10 と裁定 2 回目を本ラウンドで実施した):

  - **指示 1 (F1、(e) 資源検査の load-bearing 化)**: `test_c05_e_isolated_application_surface_releases_resources` を `__enter__`/`__exit__` を直接駆動する形へ改め (`conformance-tests/test_c05_limit_declaration_agreement.py:695-779`)、close 失敗を deprovision の RuntimeError で覆い隠さないようにした。**実測**: `r2db-api-http` は close 呼び出し相当の分離を保ったまま before/during/after の資源計数で赤くなることを確認 (下記変異表)。**r2db-api (in-process) の「資源ゼロで変異構成不能」の開示は本ラウンドで `CONDITIONS.md` C-05 行と `CONFORMANCE_ADAPTER_V1.md` §21.1 の両方に追加した** (起草時点では設計 D-6.6 本文にのみ監督注記として存在し、`CONDITIONS.md`/§13.2 のどちらにも無かった -- 本ラウンドで解消)。
  - **裁定 2 回目 (変異 C: MitateDB-http の close 撤去で (e) が緑)**: `CONDITIONS.md` C-05 行と `CONFORMANCE_ADAPTER_V1.md` §21.1 に「MitateDB-http では deprovision の `pg_terminate_backend` により close は load-bearing でない (保証は構成上成立)」を追加した。テストを歪めて赤にする対応は取っていない (裁定の指示どおり)。
  - **指示 4 (完了条件 13(b))**: `conformance-tests/adapter.py` の `isolated_application_surface()` docstring に「class ごとに新しい isolated_application_surface() を張る」選択と `requests_per_minute` の headroom 前提を明記 (前任分)。**本ラウンドで `CONFORMANCE_ADAPTER_V1.md` §21.1 にも同内容を追加**し (起草時点では adapter.py にしかなく §21.1 に欠落していた)、テスト側の引用 (`_drive_batch_items` 等コメント "port v1.11 docstring's own documented choice") と記載を整合させた。
  - **指示 5(a)(b)**: `result_items` の分類を「片側」から「両側 (r2db のみ)」へ訂正し、片側 3 class の内訳を `request_bytes`/`query_complexity` の 2 件へ改めた -- `CONDITIONS.md` C-05 行の開示(2)と本節上表の `result_items` 行の両方。`request_bytes` の「(all four, MitateDB in-process excluded」という自己矛盾した文言を「three plugs」へ訂正した。
  - **指示 5(c)**: `_drive_operation_depth` (`test_c05_limit_declaration_agreement.py:293-327`) に他 driver と同型の `assert bound <= _MAX_EXERCISABLE_LIMIT` を追加し、宣言値を `doc["limits"]["operation_depth"]` から読んだうえで「平坦 insert の実測深さ (4) == 宣言値」の前提を `assert bound == 4` で表現した。
  - **指示 6 (F6)**: `test_c05_v1_d_unavailable_class_may_still_publish_a_limits_value` を実効化した -- `_assert_v1_self_consistency` を実際に呼ぶ形にし、`MitateDB-api` について「unavailable + 値」の組が実在することを real assert で確認する形にした (`assert True` の恒真を除去)。
  - **指示 7 (F7)**: `test_c05_v2_per_plug_nonvacuity_would_be_caught` を削除した。完了条件 12 (V2 の per-plug 非空性) は `test_c05_v2_declaration_and_position_agree` 1 本が担う。
  - **指示 8 (F8)**: `_FIXED_NINE` の内容そのものを `test_c05_fixed_nine_is_pinned` で pin する対応は前任分で既に存在した (確認済み)。**本ラウンドで追加**したのは `_ALL_PLUG_NAMES` が `registered_adapters()` のキー集合と一致することを assert する `test_c05_all_plug_names_match_the_registry`。
  - **指示 10**: V3 が「宣言の欠落」(status=None) を捕まえず V1(e) が受けることを `CONDITIONS.md` C-05 行に追加開示した。変異 3 の r2db 側実測は下記変異表に追加した行のとおり -- **実測の結果、レビュー指摘 F10 の文言「V1(e)で2件赤」は red の件数 (2件) は正しいが、実際に発火するのは V1(b) であって V1(e) ではないことが判明した** (r2db は固定9の全classが常に`limits`実値を持つため、`limit_enforcement`だけを落とす操作は必ず`limits`に値があるのに対応する`limit_enforcement`が無いV1(b)違反を先に作る -- MitateDBは対象4classが`limits`に値を一切持たないため、この経路を素通りして初めてV1(e)に到達する、という構造の違いによる)。この訂正 (起草時点の想定と実測の食い違いを実測で正す) は F5(a)/(b) の是正と同じ規律に従う。**なお同じ変異をMitateDB側で改めて実測すると、`MitateDB-api` と `MitateDB-api-http` の両方が赤くなった** (旧記録は `MitateDB-api` 単独としか書いていなかった -- `cell.py` は両 plug が同じ宣言を読むため、こちらも 2 件赤である)。

  **本ラウンドの再実測 (F6 / F8 / F5(c) の変異、および指示 1・10 の再実測)、すべて scratchpad backup からの `cp` 復元 + `sleep 3` + `shasum -a 256` 二重照合 + 変異文字列 grep ゼロ確認を実施**:

  | 対象 | 変異 | 結果 |
  |---|---|---|
  | F6 対照テストの実効化 | `_assert_v1_self_consistency` の (d) 節に withdrawn rule を一時的に再導入 (`if status in ("unavailable","deployment_required") and cls in limits: raise AssertionError(...)`) | **赤 4 件**: `test_c05_v1_control_plane_self_consistency[r2db-api]`、`test_c05_v1_application_plane_self_consistency[MitateDB-api]`、`test_c05_v1_control_plane_self_consistency[MitateDB-api]`、**`test_c05_v1_d_unavailable_class_may_still_publish_a_limits_value[MitateDB-api]`** (これが指示6の狙った的--以前の`assert True`では絶対に赤くならなかった) |
  | F8 の pin | `_FIXED_NINE` から `operation_depth` を削除 | **赤** (`test_c05_fixed_nine_is_pinned`)。副次的に収集数も変化 (49 passed/9 xfailed → 46 passed/7 xfailed) |
  | F5(c) の bound assert | `_drive_operation_depth` に追加した `assert bound == 4` を削除 | **変化なし (49 passed/9 xfailed のまま)** -- この assert は N/N+1 レシピの実行そのものには影響せず、静的な宣言値/レシピ対応の保証としてのみ機能する。**別途、この assert を残したまま `conformance_adapter_r2db.py` の隔離 profile 側 `operation_depth=4` を `5` に変えて実測**: `test_c05_v2_declaration_and_position_agree[r2db-api]` が `assert bound == 4` 自身で赤くなることを確認した (assert は「宣言と実測レシピの対応が壊れたら検出する」役割で load-bearing であり、レシピの通常実行の成否には影響しない、という 2 つの実測の組み合わせで性質を確定させた) |
  | 指示 1 の再実測 (r2db-api-http) | `isolated_application_surface()` の `finally` から `cell.close()` ループを削除 | **赤** (詳細は下記変異表 11 の追加行) |
  | 裁定 2 回目 mutation C (MitateDB-api-http) | 同じ close 除去を MitateDB-http 側に適用 | **緑のまま** (詳細は下記変異表 C の追加行、受理境界として開示) |

  **観測された非決定性 (報告義務、指示外の発見)**: `test_c05_e_isolated_application_surface_releases_resources` を `::test_c05_e_isolated_application_surface_releases_resources` 単体選択 (モジュール全体でなく関数 1 本だけ) で繰り返し実行すると、`r2db-api-http` 側が変異なしでも `after=5`(または類似の非ゼロ値) で赤くなることがある (3 回連続で再現)。**モジュール全体を対象にした実行 (`test_c05_limit_declaration_agreement.py` 単体、conformance 全体直列、conformance 全体 `-n 5 --dist loadgroup` のいずれも) では毎回 `524 passed, 9 xfailed` / `49 passed, 9 xfailed` で安定して緑**であり、単体選択実行時のみに見られる現象である。本ラウンドのコード変更はこのテスト関数の本体に一切触れていない (instructions 4-8/10 の対象外) ため、**前任分から存在した pre-existing のタイミング依存 (フィクスチャ順序またはコネクションクローズの非同期性起因と推測) であり、本ラウンドの回帰ではない**と判断したが、根本原因の特定は未実施。監督確認を要する。

  **【追記、WP-4 rework 最終ラウンド、監督裁定 1 対応】根本原因は特定され、是正済み**: 監査 (`wp4-audit.md` §2) が実測で確定させた原因は「フィクスチャ順序またはコネクションクローズの非同期性」ではなく、`_live_pg_backend_count` の計数対象が `<prefix>%` (共有 platform DB を含む) だったため、共有 control スタックの遅延接続 (先行テストが温めたか否か) を数えてしまっていたことだった (冷たいプロセスでは無変異の対照ですら赤くなることを監査が確定的に再現)。計数対象を当該隔離 instance が provision した application DB 1 個 (`<prefix>_app_<application_id>`) に限定したことで (本節冒頭の是正、監督裁定 1)、単体選択 5 回連続緑・モジュール全体緑の両方を確認し (scratchpad `wp4-final-solo5.log`/`wp4-final-c05-module.log`)、この非決定性は解消した。

- **WP-4 (続き — 監督裁定・独立レビュー・受け入れ監査の経緯。上の各項は実装担当の報告に基づく記録であり、本項はその上に載る体制側の経緯である)**:

  **回数と体制**: **実装 (Sonnet) → 独立コードレビュー (Opus) 1 回 (指摘 F1〜F10) → 差し戻し 2 回 (差し戻し指示 1〜10 と監督裁定 2 回目) → 受け入れ監査 (Opus) 1 回 (完了条件 1〜21 の判定)**。**上の疑義 3 が「レビュー / 監査は未実施」と読める形で残っていたのは起草時点の記述であり、本項が現況として正す** (監査の「主張 vs 実測」表の指摘)。

  **レビュー自身の変異 4 本** (基準 `51 passed, 9 xfailed`。当時はまだ F7 の重複テストが在る状態である):

  | # | 変異 | 実測 |
  |---|---|---|
  | **A** | `_FIXED_NINE` から 1 class を落とす | **`49 passed, 7 xfailed`** — **緑のまま** (pin が無いことの実証。指摘 F8 の根拠) |
  | **B** | r2db 側で固定 9 の 1 class (`operation_depth`) の `limit_enforcement` エントリを落とす | **`2 failed, 49 passed, 9 xfailed`** (`test_c05_v1_application_plane_self_consistency[r2db-api]` と `[r2db-api-http]`) |
  | **C** | MitateDB-http の `isolated_application_surface()` から close を撤去 | **`11 passed, 45 deselected, 4 xfailed`** — **緑のまま** (指摘 F1。監督裁定 2 回目で**受理境界として開示**する形に決着した) |
  | **D** | r2db-http の同じ close を撤去 | **`3 failed, 12 passed, 45 deselected`** (V2 / (e) / 非空性の 3 本)。**ただし当時の計数対象では無変異の対照も赤になる条件下の実測であり、単独では是正効果の証拠にならない** (監査 §2、上の変異表 11 の訂正) |

  **受け入れ監査の判定**: 完了条件 **21 項目**のうち **未充足 1 (条件 15 = (e) の資源検査、下記の実バグ)**、**条件付き 3** (条件 10 = V2 の駆動集合に peer 名固定の除外がある / 条件 13(a) = `_MAX_EXERCISABLE_LIMIT` の byte 系除外 / 条件 16 = §13.2 の記録が現物より古い)、**残りは充足**である。監査は**リポジトリを一切変更せず**、pytest プラグインによる実行時パッチで計測した (M-X / M-Y の 2 変異だけは cp 退避 → 変異 → cp 復元 → `sleep 3` → sha256 の二重照合を行っている)。

  **監査が再実行した集計行 (verbatim)**: `49 passed, 9 xfailed in 4.81s` / `49 passed, 9 xfailed in 4.80s` (2 回)、`69 passed, 9 xfailed in 12.29s`、`20 passed in 8.06s`、`524 passed, 9 xfailed in 72.15s (0:01:12)` (`-n 5 --dist loadgroup`、failed 0 / skipped 0)、両 peer の同型性 pin (67 行) は `75 passed` / `62 passed` で緑。**実装担当の報告値と一致する。**

  **実バグ (共通 suite 側の実バグであり、設計・発注の誤りではない)**: 上の「観測された非決定性」は**非決定性ではなく確定的な順序依存の偽陽性**だった。**単体選択 5 回が 5 回とも赤、モジュール全体 2 回が 2 回とも緑**であり、順序撹乱プラグインは未導入なので真のフレークではない。原因は `_live_pg_backend_count` の計数対象が `<prefix>%` で、**隔離 surface とは無関係な共有 platform / control スタックの遅延接続まで数えていた**ことである (先行テストが温めたか否かで `before` が階段状に動くことを probe で直接再現した)。**是正 (監督裁定 1)** は計数対象を**当該隔離 instance が provision した application DB 1 個に限定**することであり、同時に同型性対応表の `_live_pg_backend_count` の行を更新した (指示 9)。是正後は**単体選択 5 回連続緑・モジュール全体緑**である。

  **監査自身の追加変異 2 本**:

  | # | 変異 | 実測 |
  |---|---|---|
  | **M-X** (発注指定) | MitateDB `cell.py` の `requests_per_minute` を `unavailable` → `enforced` (実装は無いまま) | **`8 failed, 43 passed, 7 xfailed`** — V3 の `[XPASS(strict)]` 2 件、V1 (c) が 2 plug、V1 (d) 対照が 2 plug、V2 が 2 plug。**`xfailed` も 9 → 7 へ落ちる。副次の所見**: V2 側は assert ではなく `KeyError` で落ちるので診断メッセージが出ない (他 driver も同形。`.get()` + assert が望ましい) |
  | **M-Y** (監査独自、F2 の実効性検証) | MitateDB `control_plane.py` の `ControlLimits.as_dict()` から `audit_requests_per_minute` を削除 | **`2 failed, 47 passed, 9 xfailed`** (`test_c05_v1_control_plane_self_consistency` の 2 plug、control 面の V1 (e))。**F2 の是正 (control plane 必須集合の実配線) が load-bearing であることの独立確認** |

  **WP-4 の受理境界 (「実測できなかった」「固定しない」と決めた点)**:

  - **(e) の資源検査が load-bearing なのは 4 plug 中 2 plug である。** **MitateDB-http は変異 C のとおり close を撤去しても緑** — `0004_deprovision_application.sql` が `pg_terminate_backend` を自前で発行し、close の有無に依存せず接続を強制終了するためである (**保証は構成上成立している**。テストを歪めて赤にする対応は取っていない — 監督裁定 2 回目)。**r2db-api (in-process) は隔離 surface が保持する資源がゼロ**で、close 除去の変異そのものが構成できない (D-6.6)。**両方とも `CONDITIONS.md` C-05 行と `CONFORMANCE_ADAPTER_V1.md` §21.1 に開示した。**
  - **V3 は明示された `unavailable` しか捕まえない。** 宣言の**欠落** (`status=None`) は V3 を素通りし、**V1 (e) の必須集合チェックが受ける** (指示 10、CONDITIONS C-05 行に開示)。
  - **`_MAX_EXERCISABLE_LIMIT` (200) を byte 系 class (`request_bytes`) には適用しない** (疑義 2。200 バイトでは通常の setup 要求自体が成立しないという実測が根拠)。
  - **V2 の `result_items` / `query_complexity` の MitateDB 除外は peer 名固定である** — 宣言の真偽ではなく peer 名という属性に紐づくので、**MitateDB が偽って `enforced` と宣言しても V2 は永久に緑である**。**台帳 L7-21 として起票し、CONDITIONS C-05 行の開示に参照を添えた** (port v1.12 の能力判定への置き換えが手当て)。
  - **`test_conditions_register.py` を単独で回すと `test_every_executable_condition_has_a_marked_test` が赤になる** — 部分選択の構造的アーティファクトであり (未収集の条件 ID が落ちる)、**ディレクトリ実行では緑**である。発注文書のテストコマンドの書き方に由来する既存の性質であり、WP-4 の退行ではない。
  - **`adapter.py` の `isolated_application_surface()` docstring が「共有しない」と書く範囲は HTTP 2 plug の実装と食い違う** (`copy.copy(self)` が credential store / control スタック / 共有 platform を共有する)。**監査の指摘であり、本 WP では直していない** — port の正本テキストの是正として残る。
  - **xfail 9 件の内訳は上記のとおり** (MitateDB-api 5 本 + MitateDB-api-http 4 本)。**これが台帳 L7-1 の閉止の合図であり、class ごとに 1 件ずつ閉じられる。**

- **WP-5** ((a) C-00 / C-02 / C-04 / C-07 / C-10 の共通化 + (d)。新設 5 ファイル + `conformance-tests/conftest.py` の走査 proxy と資源管理、`test_c14_authority_boundary.py` の隔離 applications vector、`CONDITIONS.md` 5 行。**実装 (Sonnet) 3 ラウンド + 独立コードレビュー (Opus) + 受け入れ監査 (Opus) 1 回**。branch `phase7-wp5` の `6a3246b` → merge `0650855`):

  **実際に採った形** (発注と食い違った点は**実装が正**として記す):

  - **(d) はコード変更なし** — **Q4 フェーズが先に閉じていた** (訂正註 9)。`validate_surfaces_value` は既に 1 モジュールに統合され、同型性対応表にも行がある。**PHASE6 §11 L6-17 の閉止注記も Q4 側で既記**であり、WP-5 の差分には無い (監査の実測)。**成果物 11〜13 と変異 9 / 10 は対象消滅として N/A。**
  - **代わりに資源管理が入った** (訂正註 9 後半、監督裁定)。**発見の順序が記録として重要である**: (1) 既存テストが provision した application の残骸が共有 platform に積み上がっており、**C-14 の applications vector が「既に上限近く」の状態で空振り気味だった**、(2) conformance の fixture 層に**残骸 teardown (deprovision)** を置いた、(3) すると今度は **`requests_per_minute` の枠が 24 件で枯渇**した、(4) **隔離 surface (`isolated_control_surface(limits_override)`、port v1.11 追補 §21.4) + 既存登録数を差し引く headroom** で駆動する形に改めた。**限度値そのものは上げていない。**
  - **C-10 の走査は `conftest.py` 側の generic proxy (`ScanningAdapterProxy`) で行い、port は 1 method も増やしていない** (禁止事項 1)。`adapter.py` の差分は 0 行ではないが、**その全ては WP-4 の §21.4 追補分であり C-10 由来は 1 行も無い**ことを監査が差分全読で確認した (発注文書の「`adapter.py` 差分 0 行」という照合文言は §21.4 の監督裁定で失効している)。

  **レビューと差し戻し**: 独立レビューの指摘 **8 件 + 1 件 (指摘 10)**、**3 ラウンド**で是正。**最も重い指摘 1 (C-10 の走査パターンがこの build の実際の DSN 形式を捕まえない)** はレビュー自身の変異で実証された — **URL 形の DSN を応答に混ぜると赤** (`1 failed, 3 passed`) だが、**同じ秘密を、両 HTTP plug が実際に組み立てる libpq keyword 形で混ぜると `12 passed` の全緑**だった。**是正は 3 段**である: (i) `\bpassword\s*=\s*\S+` の keyword 形パターンを足す、(ii) **plug が実際に保持している秘密の literal 集合を走査対象へ渡し、1 つでも応答に現れたら赤にする** (port は増やさず、adapter の既存属性から conftest 側で組み立てる)、(iii) **例外側も走査する** (`except Exception` で `str(exc)` と `details` を見てから素通しで再送出する)。**是正後の再実測**: keyword 形の変異・literal の変異とも **`1 failed`** で赤になる。**指摘 2 (C-14 の headroom の余裕が 3 しかない)** は `n_existing_shared + 3` の導出式へ、**指摘 3** は adapter 名分岐を宣言読み取り (`limit_enforcement["operation_depth"] == "enforced"`) へ、**指摘 5** は C-00 の早期 return 2 経路に**宣言の正直さ assert** を足したうえで CONDITIONS に「4 plug すべてで未到達」を開示、**指摘 7** は CONDITIONS の虚偽文の訂正、**指摘 10** は C-01 / C-02 の共通ヘルパ化である。

  **実バグ 2 件 (deprovision 経路。設計・発注の誤りではない)**: **(1)** 残骸 teardown を入れた当初、**プール接続を close する前に deprovision すると「being accessed by other users」で失敗する** — 順序を close → deprovision に改めた (`CONFORMANCE_ADAPTER_V1.md` §21.4 の記述も同順へ訂正)。**(2)** 同じ順序の記述が **port ABC の docstring 側だけ逆のまま残った** — **監査が指摘 8 の残り 1 箇所として検出し、本 WP では未是正のまま受理境界に置いた。**

  **完了ゲート実測**: 全 conformance が `560 passed, 9 xfailed in 71.35s (0:01:11)` (`-n 5 --dist loadgroup`)、新設 5 + C-14 + C-05 + C-06 + C-01 が `188 passed, 9 xfailed`、新設 5 + C-05 + C-14 が `105 passed, 9 xfailed`。**baseline `524 passed, 9 xfailed` からの差は +36 passed のみ**で、`failed` 0 / `skipped` 0 / `xfailed` 9 は不変である。**監督の完了ゲート (root suite 単独実行) は `2250 passed, 9 xfailed, 5 warnings in 148.26s (0:02:28)`。**

  **変異注入の結果** (実装担当。復元は cp + `sleep 3` + sha256 二重照合 + 変異文字列の全文 grep ゼロ確認):

  | # | 変異 | 実測 |
  |---|---|---|
  | **1 / 2** | C-04 の実行前拒否を実行後拒否に変える / error body に stack trace 断片を混ぜる | **赤** (監査の変異 D が `12 failed` = C-04 8/8 + C-10 4/4 で独立に再実証、変異 E が `16 failed` = C-04 8/8 + C-07 8/8) |
  | **3** | 応答に DSN 形の文字列を 1 つ混ぜる | **赤**。**ただし URL 形のみ** — **同じ秘密の keyword 形は当初緑だった** (レビュー指摘 1)。是正後は **keyword 形・literal 形とも `1 failed`** |
  | **4** | C-02 の拒否分岐を 1 つ外す | **成立しない (訂正註 10)**。r2db の developer 検査は `service.py` と `structured.py` の**二重ゲート (defence in depth)** で、**片方だけ外すと `4 passed, 4 deselected` の緑**である (両方向とも実測)。**両ゲートを同時に外して初めて `2 failed`** (`test_c02_runtime_denied_create_entity_but_developer_succeeds_on_the_same_request` の r2db 2 plug)。**片方除去で緑であることを対照として記録する** |
  | **5** | C-07 (i) の batch ロールバックを外す | **r2db-http で赤**。**MitateDB では成立しない** — `transact()` が **two-pass** 構造 (P35 WP-2) で、この vector の invalid item (未知フィールドの insert) は **`begin()` が一度も呼ばれる前に** pass 1 で拒否されるため、rollback 行に到達しない (`4 passed, 4 deselected`)。**実装の欠陥ではなく r2db より強い保証の副作用**であり、**当該行が死んだコードでないことは peer-local 単体テスト 2 本 (SQLite / PostgreSQL) が直接検証している**。**受理境界として開示。** |
  | **6 / 7** | C-07 (ii) の宣言分岐リテラルを入れ替える | **`4 failed`** (4 plug すべての `test_c07_ii_idempotency_declaration_branch`)。**per-plug の非空性は「宣言から独立に導出した期待枝との一致」で担保する形**であり、観測集合の非空性そのものではない (監査 §2 の #8、受理境界) |
  | **8** | C-00 の到達拒否を 1 つ外す | **片方だけでは緑** (`2 passed`)、**両方外すと赤** (`1 failed`)。**C-01 / C-14 の既存 vector を有効にしたままでも新規 vector が独立に赤になる**ことを別 run で確認した (`1 failed, 7 passed`) |
  | **C-14 (k=0)** | headroom の margin を 0 にする | **`4 failed`** (4 plug の `test_c14_resource_bounds_published_and_enforced`) — **headroom の算術が load-bearing であることの実測** |
  | **9 / 10** | 同型性の片側崩し / 対応表の縮小 | **N/A** (訂正註 9 により対象消滅) |

  **受け入れ監査の判定**: 完了条件 **15 項目 + 訂正註 9 の資源管理**を判定し、**証拠不足 1 (条件 5 = C-02 の変異 4 が二重ゲートにより成立しない)**、**N/A 2 (条件 11 / 12 = (d) の対象消滅)**、**残りは充足**とした。監査も**リポジトリを一切変更せず**、実行時パッチのプラグインで計測している (作業ツリーは監査前後で不変)。**監査の追加変異 5 本**: **A** = `_held_secret_literals` を空集合にする → **`36 passed` で誰も赤にならない** (literal 走査には**非空性の機構的保証が無い**)、**B** = 各 plug が**実際に保持している**秘密値を応答に混ぜる → **`4 failed`** (in-process 2 plug は literal 枝、HTTP 2 plug は `password=` 枝)、**C** = 残骸 sweep を無効化 → session 末の非空性 assert が ERROR、**D** / **E** = 上の表のとおり。

  **空振りの実測 (各 vector × 各 plug)**: C-10 の走査は **4 plug とも 23 回/plug** (うち 20 回は literal 集合付き)、**`_held_secret_literals` は 4 plug とも 1 件以上** (件数のみを記す)。C-07 (ii) は **4 plug とも `unavailable` 枝** (`retry_same_result` 枝は 0/4)、C-00 の catalog vector は **4/4 が本体パス** (早期 return 2 経路は 0/4)、C-04 の分岐は **r2db 2 plug が `operation_depth enforced` 側、MitateDB 2 plug が反対側**で**両枝とも通っている**。

  **資源管理の実測**: `-n 5 --dist loadgroup` の 1 run で、worker ごとの created / deprovisioned は **52/52・225/221・161/157・225/221・161/157**、**session 末の残骸は plug あたり 0〜3 件**である。**「残骸 0」ではなく「有界で説明のつく残骸」**であり (c06 のモジュールキャッシュ 2 件と capability probe 分)、**session をまたいだ累積は構造的に起きない** (各 plug の platform DB はプロセスごとに新規作成し close で sweep する)。

  **WP-5 の受理境界**:

  - **C-00 の catalog vector の早期 return 2 経路は 4 plug すべてで到達 0/4 である** — 現在は 4 plug とも `application_catalog: enabled` を宣言するためであり、**その分岐の変異は赤の実証が不能**である。**宣言の正直さ assert を置いたうえで CONDITIONS に開示した** (訂正註 10)。
  - **C-07 (i) の MitateDB 側は two-pass 設計によりこの vector から rollback に到達しない** (上記変異 5)。
  - **C-02 の変異は r2db では二重ゲートを同時に外さない限り成立しない** (訂正註 10)。
  - **C-10 の literal 走査には非空性の assert が無い** (監査の変異 A)。peer が内部属性を改名すれば literal 枝は無音で消える。**両論あり (docstring は「無い plug では空に degrade する」と明示的に設計している) ため、監督裁定を要する点として記録する。**
  - **C-10 の射程は adapter 境界水準・worker 単位である** (L7-7)。**「wire 水準」とは書いていない。**
  - **C-04 の受理コードは `{CAPABILITY_UNSUPPORTED, VALIDATION_FAILED}` の 2 元集合である** (MitateDB-http は wire 段の JSON 形状検査で先に落ちる)。**実行前拒否という命題は保たれるが、完了条件 1 の字句からは緩む** — CONDITIONS C-04 行に実測を開示した。
  - **port ABC の docstring と §21.4 の順序記述の食い違い (指摘 8 の残り 1 箇所) は未是正である。**

- **WP-6** ((b)(iii) `error::DeprecationWarning` の有効化。root と両 peer の 3 つの `pyproject.toml`、`constraints.txt`、`conformance-tests/test_pytest_config_symmetry.py` 新設。branch `phase7-wp6` の `28171bc` → merge `a090e80`):

  **実際に採った形** (訂正註 7・8 が正本):

  - **`httpx2` を採用し `TestClient` は維持した** (ASGITransport への置換は lifespan 駆動の有無が変わるため採らない)。**提供元の確認**: `httpx2` 2.12.0 の配布メタデータ上、**Homepage / Source はいずれも `httpx2` の GitHub リポジトリ**であり、**著者は httpx / Starlette の原作者、maintainer は Pydantic の法人**である (**e-mail 2 件は本記録に転記しない** — 公開規律 R1)。**Starlette 1.6.0 の `testclient.py` 自身が `import httpx2` を第一経路にしている**ことが採用の直接の根拠である。両 peer の `[test]` extras と `constraints.txt` に **`httpx2` 2.12.0 / `httpcore2` 2.12.0 / `truststore` 0.10.4** を pin した。
  - **pytest 設定は 3 ファイルに同じものを置いた。** **設計 D-3 の「pytest 設定の一本化 = root のみ」は誤りだった** — **pytest は最寄りの inifile を採るので、peer 単体実行では root の `filterwarnings` は効かない** (レビューが 4 通りの起動で `rootdir` / `inifile` を実測して確認した)。**`test_pytest_config_symmetry.py` が 3 ファイルの `filterwarnings` が同一であることを pin する** (新設 2 テスト)。
  - **上流由来の `DeprecationWarning` 1 件だけを狭い ignore で受けている** — `starlette/testclient.py` が `anyio.abc.BlockingPortal` (anyio 4.15 で deprecated alias) を無条件に参照するためであり、`ignore:.*BlockingPortal.*:DeprecationWarning:starlette.testclient` を**モジュール限定**で置いた。**我々のコード由来の `DeprecationWarning` は 0 件である。台帳 L7-19 で追跡し、Starlette が直した版へ constraints を上げるときに撤去する。**
  - **`StarletteDeprecationWarning` は `UserWarning` 派生であり、`error::DeprecationWarning` の対象外である** (MRO をレビューが実測)。**したがって「httpx2 が無いと落ちる」は誤りであり、httpx2 の役割は警告の除去と fallback 撤去への備えである** (D-4 の監督訂正、訂正註 8 の追記)。**共有 `.venv` に httpx2 を入れていないため、完了ゲートにはこの警告が 5 件残る** (13.1)。
  - **`TestClient(` の実数は 4 ファイル 21 箇所**である (発注文書の「3 ファイル 12 箇所」は誤り。訂正註 8)。

  **有効化の前後で集計行が変わらないこと (完了条件の中心)**: **r2db-api `934 passed` (前 `2 warnings` → 後 warnings 0)**、**MitateDB-api `756 passed` (前後とも同一)**。**passed の数は前後で一致し、`failed` / `skipped` は 0 のままである。** **監督の完了ゲートは `2252 passed, 9 xfailed, 5 warnings in 149.65s (0:02:29)`** であり、WP-5 の `2250` との差 **+2** は新設の同型性テスト 2 本ちょうどである。

  **レビューと変異**: 独立レビュー (Opus) は**リポジトリを変更せず**、変異は cp 復元 + sha256 二重照合で行った。**変異 4 本**: **宣言済みの 1 本** = MitateDB の `pyproject.toml` から ignore を落とす → **赤**、**未宣言の 3 本** = root から `error::DeprecationWarning` を落とす → **赤**、3 ファイルすべてに**同一の**包括 ignore (`ignore::DeprecationWarning`) を置く → **赤** (同型性は保たれるが「error 化されている」ことを見る側のテストが落ちる)、**我々のテストコードから一時的に `DeprecationWarning` を出す** → **赤**。**基準は `2 passed`。** 実装担当の変異も同型で、`error::DeprecationWarning` の除去は**両 peer とも** `test_zzz_wp6_mutation1_deprecationwarning_is_fatal` が赤、同型性の破壊は `test_pytest_config_symmetry.py` の **2 本とも赤**である。あわせて **`httpx2` を meta_path で遮断した状態でも新しい `filterwarnings` の下で緑である**こと (`1 passed, 1 warning`)、**`error::DeprecationWarning` が `PendingDeprecationWarning` / `FutureWarning` / `UserWarning` を巻き込まない**ことを実測した (禁止事項 3 の充足)。

  **WP-6 の受理境界**:

  - **上流の ignore 1 件は残る** (L7-19)。**撤去は constraints の Starlette 更新と同一コミットで行う。**
  - **共有 `.venv` は作り直していない** — したがって**ローカルの完了ゲートには `StarletteDeprecationWarning` が 5 件残る**。**これは `UserWarning` 派生であり error 化の射程外**であって、条件違反ではない。
  - **同型性テストが固定するのは 3 ファイルの `filterwarnings` の一致だけである** — 3 ファイルが揃って誤った設定になる形 (レビュー変異の 3 本目) は、**error 化そのものを見る側のテスト**が受ける。

- **WP-7** ((i) 現行結論と履歴の分離。`conformance-tests/CONDITIONS_HISTORY.md` と `security/CONTROL_MAPPING_HISTORY.md` を新設、元 2 ファイルを現行行化して更新規約を前文に置き、`conformance-tests/test_conditions_register.py` を拡張して `conformance-tests/test_control_mapping_register.py` を新設。あわせて `test_c09_audit_evidence.py` / `test_c19_client_self_sufficiency.py` の docstring の参照ドリフトを訂正。**差分は 8 ファイル (変更 5 / 新設 3) であり、製品コードは 1 行も含まない**。**実装 (Sonnet) 3 ラウンド + 独立コードレビュー (Opus) 1 回 + 受け入れ監査 (Opus) 1 回**。branch `phase7-wp7` の `2b89976` → merge `b2f9224`):

  **実際に採った形**:

  - **現行行 = 担保 + 証拠 + `[history](…#<id>)` リンク、companion = ID だけの見出し (`## C-19` / `## SI-14`) 配下に原本の逐語**、という裁定 4 の形をそのまま採った。**列構造は維持** (CONDITIONS 5 列 20 行 / CONTROL_MAPPING 4 列 16 行、ID 重複 0、セル内の生 `|` 0、1 ID = 1 行)。**更新規約は表の外の前文に散文で置き**、裁定 4 の逐語文字列「訂正は現行行を書き換え、旧文は履歴へ移す」を両ファイルが持つ。
  - **機械固定は D-7 の 4 項目どおり**である — **(1)** 全行の history リンクが companion の実在 slug へ**解決すること** (見出しの存在ではなく slug の一致を測る)、**(2)** companion の見出し集合が主表の ID 集合と**過不足なく一致**すること、**(3)** 見出し配下が**空でない**こと、**(4) セル長上限**。あわせて **`ID` 列の重複禁止**と **`CONDITIONS.md` が `|` 始まりの表を 1 つだけ持つこと** (既存 parser の前提。原本には無かった保証) を足した。
  - **セル長上限はファイル別に分けた** (レビュー指摘 C-1)。**確定値は `CONDITIONS.md` = 3,000、`CONTROL_MAPPING.md` = 15,200 である** — **実測の最長セルは `CONDITIONS.md` が C-09 の Status セル 2,948 文字 (余裕 52 字; C-19 は 2,942)、`CONTROL_MAPPING.md` が SI-14 の r2db-api control/evidence セル 15,065 文字 (余裕 135 字)** であり、**監査が独立に計測して両ファイル前文・両 register コメントの記載と完全一致することを確認した**。**当初は両ファイル共通の単一 cap (16,600 → 15,700 → 14,300 と推移) を置いていたが、`CONDITIONS.md` の実測最長に対して数倍の余裕が生じ D-7 の「再蓄積を機械的に止める」が事実上無効になる**ため、ファイル別へ分けた。**上限の運用は訂正註 11 の ratchet である** — 正当な追記で赤になったら**同一コミットで前文の測定行と上限を更新する**。
  - **SI-14 の 2,500 字超過は監督が受理した。** D-7 の目安 2,500 に対し、**SI-14 の r2db-api 列は 15,065 字、MitateDB-api 列は 8,639 字**である。**この 1 行が両 peer の durable audit sink の全形状** (2 表 × 13 の `audit.fields` 列、同一トランザクションの fail-closed 書き込み、6 コードの否認耐久性の包含リスト、coalescing + 有界 buffer の機構、`request_id` 相関、`audit_query` の挙動、AST による宣言語彙の等式、`visibility_lag_ms` のプロセス跨ぎ導出) **と、runtime role の GRANT の全記述と、それら全部に掛かる開示された限界**を担う。**2,500 へ詰めるには GRANT の証拠か、監督が「落とせない」と名指しした開示された限界のいずれかを捨てるしかない** — 文の締め方の問題ではない。**したがって上限はこの実測から導いた 15,200 であり、目安 2,500 は `CONDITIONS.md` 側でのみ達成されている** (C-09 / C-14 が 2,500 前後、C-19 が 2,942)。
  - **companion は縮んだ。** 仕分けの最終ラウンドで**中間稿と自己参照リンクを全廃**し (`pre-narrowing` / `2,500-char target` / `WP-7 final` / `rework round` はいずれも 0 件、companion 内の自己参照 `[history](…)` も 0 件)、**監査計測で 180 KB → 126 KB / 285 KB → 178 KB** になった。**現行 2 ファイル自体は原本 101 KB → 51 KB / 157 KB → 88 KB である** (main `b2f9224` での計測)。

  **レビューと 3 ラウンド**: **独立レビューは「落ちた制約」を独立項目として突合し (L7-10 の要求そのもの)、8 件を検出した** — **A-1** C-09 Honest limit (b) の「peer-local AST equality 自身が同時 D→N demotion を見られない」、**A-2** C-09 Honest limit (a) の裁定識別子 P4-D18 と「未閉止 (open future work)」の状態注記、**A-3** SI-14 (r2db) の除外リストの根拠 (「SI-14 自身の minimal event class の外側だから」) と点 (4) の両 plane 非対称性の注記、**A-4** SI-14 (r2db) の coalescing / buffer が process-local であることと配備実効上限が `2 × <windows> × M` / `<buffer capacity> × M` になること、**A-5 の 4 件** (C-05 limit (5) の第三者実装の帰結文、C-19 composition 側 static scan の現行担保、SI-08 (MitateDB) の ceiling 撤廃が配備ミス防止のガードも同時に外すという副作用、C-09 (c) の更新規約「by name」)。**いずれも「現行行から消え companion にしかない」形**であり、**是正は 8 件すべて現行行への復帰**である (逐語である必要はなく、監督裁定の「現行セル = 担保 + 開示された射程の限界 / 受理境界」に収まる短文へ condense してよい、という指示で戻した)。**A-2 は付随して `test_c09_audit_evidence.py:596-599` の docstring を虚偽にしていた** (「同じ文言が C-19 行にあり両者は乖離してはならない」と書きながら、当の文言が現行行から消えていた) ので、**docstring 側も現状に合わせて訂正した**。**E-1 の `test_c19_client_self_sufficiency.py:12` の参照ドリフトも同様である。** 残る指摘は **B-1** (両 register の cap 根拠コメントが古い実測値のままで、その値が cap を超えるという自己矛盾)、**B-2** (確定値がどこにも記録されておらず、コメントの参照先が空)、**C-1** (単一 cap)、**D-1** (companion が WP-7 自身の中間稿を履歴として抱えている) である。

  **受け入れ監査**: **完了条件 13 項目を判定し、充足 10 / 前半充足・後半 WP-8 繰延 1 (条件 7) / 証拠不足 2** とした。**監査は「落ちた制約」を自分で選んだ 12 行 (発注の 6 行以上を上回る) について独立に突合し、現行行にも companion にも無い制約は 0 件** — 対象は C-05 / C-07 / C-09 / C-10 / C-11 / C-19 / SI-00 / SI-02 / SI-08 / SI-10 / SI-12 / SI-14 である。**方式は「原本セルを文単位に分割し、制約語を含む文を抽出してトークン被覆を測り、低被覆のものは全件を人手で読む」**であり、**機械検査の結果をそのまま結論にしていない**。**監査は主張 vs 実測を 7 項目突合し、両ファイル前文・両 register コメント・訂正した 2 つの docstring がすべて現物と一致することを確認した。** **監査もリポジトリを一切変更していない** (`git status` は指示どおりの 8 ファイルのみ、実装担当のコミットは 0 = 規律 2 遵守)。

  **変異注入の結果 (7 種)** — 復元はすべて scratchpad backup からの `cp` + `sleep 3` + sha256 二重照合 + 変異文字列の全文 grep ゼロ確認 (`git checkout --` 不使用):

  | # | 変異 | 実測 |
  |---|---|---|
  | **A** | 主表のセルを cap 超過まで伸ばす | **赤** — `test_control_mapping_md_cells_do_not_exceed_the_length_cap` (実装担当: SI-12 MitateDB 列を 16,511 字に / 監査: C-01 Condition 列を 3,122 字に、`test_conditions_md_…` が赤) |
  | **B** | `ID` 列を書き換えて重複を作る | **赤** — `test_control_mapping_md_has_no_duplicate_ids` (`duplicate SI id row(s): ['SI-14']` / 監査再現は `['SI-08']`) |
  | **C** | 行の `[history](…)` アンカーを実在しない fragment へ壊す | **赤** — `test_every_control_mapping_row_has_a_resolving_history_link` (`[('SI-14', 'si-99')]`) |
  | **D** | companion の見出しを別 ID へ改名する | **赤** — `test_control_mapping_history_has_exactly_the_main_tables_ids` (`missing_from_companion=['si-15'] extra_in_companion=['si-98']`) |
  | **E** | 見出しを残したまま配下の本文を空にする | **赤** — `test_conditions_history_every_heading_section_is_non_empty` (`empty section body: ['c-01']` / 監査再現は `['c-10']`) |
  | **X** (レビュー) | **見出しは残したままタイトルだけを付ける** (`## C-19` → `## C-19 -- Client self-sufficiency`) | **赤 2 件** — `test_every_conditions_row_has_a_resolving_history_link` と `test_conditions_history_has_exactly_the_main_tables_ids` (`extra_in_companion=['c-19----client-self-sufficiency']`)。**anchor 検査が「見出しの存在」ではなく slug の一致を測っていることの実測**であり、発注の非 vacuity 要件そのものである |
  | **Y** (レビュー) | `CONDITIONS.md` の末尾に **2 つ目の `\|` 始まり表**を足す | **赤** — `test_conditions_md_has_a_single_table` (`assert 135 == 25`)。既存 parser の前提が機械固定されたことの実測 |

  **上限がセル単位であることは変異を待たずに立証されている** — **ベースラインの最長「行」長は CONDITIONS 3,983 / CONTROL_MAPPING 25,995 でいずれも自ファイルの cap を超える**ので、**行単位実装ならベースラインが赤になっていたはずである** (監査の指摘)。

  **カバレッジ検査の射程 (本 WP で最も重要な受理境界)**: 仕分けの網羅性は `wp7_full_coverage.py` (bold 区切りの「主張単位」と `test_…` トークンの二層検査) が測り、**最終ツリーで `CONDITIONS missing_units=0 missing_tokens=0; CONTROL_MAPPING missing_units=0 missing_tokens=0`** である (実装担当と監査が別々に実行して一致)。**ただしこの script は「現行セル + companion 全文」の合算に対して在否を見るので、「失われていない」ことは示すが、「現行行から落ちた」(完了条件 10) は原理的に見られない。** **さらに狭い穴が 3 つある** — companion 側は全文を 1 つの塊として扱うので**別 ID の下に紛れ込んだ単位も被覆と数える**、**20 文字未満の単位は飛ばす**、**逆方向 (新しい主張が足された) は見ない**。**したがって完了条件 10 を担保しているのは機械検査ではなく、レビューと監査の人手突合である** — レビューが 8 件を検出し、監査が 12 行を独立に読んで 0 件を確認した、というこの二重の人手工程が load-bearing である (**L7-10 が独立項目を要求した理由がそのまま実測で裏づけられた**)。**逆方向はレビューと監査が別々に確認した** — 現行行に新しく現れて原本に無いテスト名の引用は**両ファイルとも 0 件**、現行行の数値トークンで原本行に無いものも**両ファイルとも 0 件**である (捏造された証拠は入っていない)。

  **実バグ (工程側 1 件。実装物の欠陥ではない)**: **最初の実装担当が下請け Agent の応答待ちに入ったまま停止し、作業を別の担当へ引き継いだ。** 途中成果は scratchpad に残っていたので捨てずに継承できたが、**引き継ぎ地点の状態が「どこまで仕分け済みか」の記録としてしか残っておらず、後続ラウンドが最初に行ったのは全行の再計測だった**。**教訓は「実装担当に下請け Agent を使わせない」であり、第 14 次引き継ぎ §5 に置く。**

  **WP-7 の受理境界**:

  - **companion は「原本の逐語ブロック + WP-7 が書き下ろした注釈行」の二層である。** 非逐語かつ非プレースホルダの行は **`CONDITIONS_HISTORY.md` に 12 行、`CONTROL_MAPPING_HISTORY.md` に 1 行**残る (項目別の索引行。例: C-09 の `**Adoption timeline**: …`、C-07 の `**(ii) idempotency, declare-first …**`)。**監督裁定の「companion = 原本の逐語のみ」からは外れる**が、**D-7 の禁止事項 1 (履歴を捨てない・書き換えない) には抵触しない** — 逐語原文は別ブロックとして全量存在するからである。**両論あり、監査が §9 (2) として両論を記録した。** なお「この行からは履歴が分離されていない」型のプレースホルダ (CONDITIONS 4 / CONTROL_MAPPING 3) は**見出し非空検査が要求する設計上の産物**であり、逸脱ではない。
  - **未閉止の台帳 ID が現行行から落ちている。** 現行行から消えた台帳 ID は `CONTROL_MAPPING` が `L4-1` / `L4-2` / `L4-5` / `L4-6` / `L4-11` / `L4-13` / `L5-1` / `L5-4`、`CONDITIONS` が `L4-8` である。**大半は CLOSED 済みで履歴側にあるのが正しいが、`L4-13` (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 で「OPEN (記録のみ)」) と `L4-8` (据え置き) は未閉止である** — **事実そのものは現行行に残っている**が (SI-00 MitateDB 列は data-plane env が control 用 pepper を名指ししている非対称を保持し、C-09 は P4-D18 を復帰させた)、**ID を落としたぶん追跡性だけが失われている**。**重大度は低い。台帳 L7-22 として起票した。**
  - **register テスト 2 本の単独実行は無変異でも `1 failed, 16 passed` になる** (訂正註 11)。**原本由来の既存挙動**であり (`test_every_executable_condition_has_a_marked_test` がライブの collection からマーカーを集める)、**評価は conformance 全体 run で行う**。**収集 0 件ガードの追加は発注範囲外であり、台帳 L7-23 として起票した。**
  - **cap の余裕は小さい** (58 字 / 135 字)。**再蓄積抑止としては意図どおりだが、正当な追記のたびに「赤 → 同一コミットで上限更新」の往復が生じる** — **これは訂正註 11 の ratchet がそのまま運用である** (無記録の緩和は不可)。
  - **完了条件 7 の後半 (確定値を設計 §13 へ記録する) は本 WP-7 では未充足であり、監督裁定で WP-8 へ繰延した** — **本節がそれを果たしている**。**両 register のコメントはその旨を明記している** (監査が主張 vs 実測で確認)。

- **7-B と並行して行った 2 件 (WP-4 着手の前提を作った作業)**:

  - **main の CI 緑化** (branch `phase7-ci-green` の `811f262` → merge `1c31655`)。**Q4 の main マージ後、main の CI が赤だった** — 原因は **Q4 由来のテスト 2 件**であり、**製品コードでも migration でもない**。**(1)** `r2db-api/tests/test_ops_declarations.py` が **api role へ接続し直すときに当該 role のパスワードを渡していなかった** — ローカルは unix socket の `trust` 認証でパスワード欄が検査されないので隠れていたが、**CI は TCP + `scram-sha-256` なので実際に検査されて落ちる**。同じリポジトリ内の他 4 ファイルは `user=` を切り替えるときに必ず `password=` を渡しており、**この fixture だけが例外だった**。**(2)** `MitateDB-api/tests/test_platform_declarations.py` の合成 URL が**隣接行に分割された文字列リテラル**で書かれており、**行単位で走査するスキャナが placeholder の suffix を同じ行に見つけられず R2_url で誤検出**していた (同じ形はツリー全体でこの 1 箇所のみ)。**是正はどちらもテスト側の小修正** (パスワードを渡す / 合成 URL を 1 行に収める) であり、**スキャナの行単位という契約は変えていない**。**是正後の main は `2165 passed` で全 job success** である。
  - **LQ4-24 追補** (Q4 台帳 LQ4-24 = r2db の配備資産を Q4 の platform-declarations 設計へ追随させる。**Q4 セッションからフェーズ7 側へ引き継がれた項目**であり、7-A の WP-3 の follow-up として branch `phase7-wp3` で実施。`c90f199` → merge `a4d5b3a`、**Q4 設計側の閉止注記** `0a2ae1d` → merge `c25b1ed`)。**発注 5 点** (0001〜0008 の順次適用 / `declare-surfaces` の発行 / 廃止 env 4 変数の排除 / `ops upgrade-applications` の初回手順化 / `upgrade-status`・`show-declarations` による検証) はいずれも充足と監査が判定した。**独立レビューの指摘 7 件と受け入れ監査の追加 5 件を是正して着地した**。実際に採った主な形は **(i)** **`part1c_declare_surfaces.sh` を新設**して宣言発行を独立の手順にし、**control 面は `--no-control` で任意**にした、**(ii)** **part2 は冒頭で「このテンプレートは両 surface を前提とする」ことを明示して data 専用ホストを拒否する** — 監査所見 (1)「control surface 無しの配備が script 対で完遂できない」への回答であり、**optional 側の経路を中途半端に通すのではなく前提を宣言して fail-closed にする**選択である、**(iii)** **F-6 (宣言された control surface と `R2DB_CONTROL_PLANE_STATUS` の整合) を両方向で検査し、値の解釈を systemd 忠実にした** — 監査の A7 (引用符付きの値を誤って拒否) と A8 (`= ` の後の空白で黙って素通り) の両方を塞ぐ、**(iv)** 廃止 env 4 変数を `sudo grep` の rc を明示的に分岐して検査する、**(v)** runbook §7 の手順の並びを本文と同じ「part2 の前に enabled」順へ直す。**変異**: **F-6 検査を無効化すると rc=0 で「already agreed」と誤主張して完走**、**role 名の照合ブロックを除去すると誤った role 名が 0008 へ流れる** — **どちらのゲートも load-bearing である。** **lint は `systemd-analyze verify` / `nginx -t` / `bash -n` / `shellcheck` / `ExecStart` 非空虚の 5 検査**であり、**main の CI (run 33994580740 @ `c25b1ed`) で 5 件すべて PASS、全 job success (`2165 passed`)** である。**受理境界**: 監査の所見 (2)(3)(4) — **F-6 preflight は補助であって唯一の防壁ではない** (実プロセスは起動時に必ず F-6 で落ちる)、**runbook の「no window」という断言は過大**である (part2 は両 unit を `enable --now` した後に 401 を検証するので、正確には「window は 1 スクリプト実行内に閉じている」)、**marker ファイルは part1 系だけが書く一時的な申し送りであり、手打ちの `ops declare-surfaces` では更新されない** — **宣言の検証を終了コードで返す ops コマンドが無いという穴は台帳 L7-18 として起票済み**である。

**7-B の commit / merge (2026-09-06)**:

| WP | 内容 | 実装コミット | merge コミット |
|---|---|---|---|
| **main CI 緑化** | Q4 由来テスト 2 件の小修正 | `811f262` | `1c31655` |
| **WP-4 着手条件** | D-6.5 追補の監督承認 + 訂正註 7 | — | `8b0e247` |
| **記録** | 訂正註 7 / 8 と台帳 L7-18〜L7-20 | — | `653f200` |
| **記録** | D-4 の監督訂正 (`StarletteDeprecationWarning` は `UserWarning`) | — | `ddb303e` |
| **LQ4-24 追補** | r2db 配備資産の Q4 追随 | `c90f199` | `a4d5b3a` (Q4 設計の閉止注記は `c25b1ed`) |
| **記録** | 訂正註 9 | — | `b9e436b` |
| **WP-4** | (a) C-05 + (e) 資源検査、port v1.11 | branch `phase7-wp4` | `9ab4245` |
| **WP-5** | (a) 他 5 条件 + conformance の資源管理 | branch `phase7-wp5` の `6a3246b` | `0650855` |
| **WP-6** | (b)(iii) DeprecationWarning の error 化 | branch `phase7-wp6` の `28171bc` | `a090e80` |
| **WP-7** | (i) 現行結論と履歴の分離 | branch `phase7-wp7` の `2b89976` | `b2f9224` |
| **7-B 記録 (WP-4〜6)** | 本節・§11・作業指示書 v1.3 | `342034c` | `1656ad3` |
| **WP-8 記録 (WP-7 + 引き継ぎ第 14 次)** | 本節・§10・§11・作業指示書 v1.4・フェーズ6 §11 L6-20・第13次 §4-2・第 14 次引き継ぎ | `本記録コミット。hash は次回引き継ぎ §1 に記載` | `本記録コミット。hash は次回引き継ぎ §1 に記載` |

**着手順の実際**: **WP-4 → WP-5 → WP-6 の順に main へマージした。** **WP-6 の実装は branch 上で WP-5 と並行して行っている** — 発注文書の着手条件「WP-5 の完了後」の趣旨は「`error::DeprecationWarning` を main に先に載せて他 WP の完了ゲートを塞がない」ことであり、**branch 上の実装は誰のゲートも塞がないからである** (訂正註 7 の監督裁定)。**完了条件の評価は、マージ時点の main の集計行に対して監督が行った** (13.1)。 **【WP-8 追記 2026-09-06】WP-7 は WP-6 のマージ後に単独で走らせ、`b2f9224` で main へ入った** — **7-B のマージ順は WP-4 → WP-5 → WP-6 → WP-7 である**。**WP-7 は他の 7-B WP と並行させていない** (`CONDITIONS.md` / `CONTROL_MAPPING.md` を全面的に触るため、並行させれば必ず衝突する。§12 が 7-A 前倒しの唯一の重なりとして `CONTROL_MAPPING.md` を挙げていたのと同じ理由である)。
