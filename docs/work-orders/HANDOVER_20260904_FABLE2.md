# 引き継ぎ — 2026-09-04 (第13次。フェーズ6 契約 1.6.0 — credential の完全 bearer 化 + surface 発見 + 型付き catalog + 衛生 2 件)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/受け入れ監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: **第12次 `HANDOVER_20260904_FABLE.md` の約束事は全て継続**する (§2 到達した状態、§3 クライアント連携、§4 の次の一手と運用規律、§5 教訓)。そのさらに前の引き継ぎ (`HANDOVER_20260903_FABLE2.md`、`HANDOVER_20260903_FABLE.md`、`HANDOVER_20260829_FABLE.md` §3/§4/§5、FABLE3 §4、FABLE4 §4、`HANDOVER_20260830_FABLE.md` §4、`HANDOVER_20260831_FABLE.md` §4、`HANDOVER_20260901_FABLE.md` §3-4/§4) も**全て継続**。現在地のみ本書が上書きする
- 本書は第12次の**直後**のセッション記録である。第12次 §4-2 が残していた課題のうち**フェーズ6 (外部評価の指摘 2 / 3a / 3b / 4 / 5) を完了**し、契約を **1.5.0 → 1.6.0** へ上げて両 peer へ出荷した。第12次 §4-1 の **実機適用は依然として未実施**であり、**クライアント一報も送っていない** (方針不変)

## 1. 現在地 (main)

**契約は `1.5.0` → `1.6.0` へ上がり、両 peer とも `contract_version: 1.6.0` を宣言済みである。** 契約公開 (WP-1) と各 peer の flip (WP-2 / WP-3) は `versioning.version_binding` の規律どおり別コミットに分かれ、flip はいずれも挙動出荷と同一コミットに落ちている。**フェーズ6 は WP-4 (記録整理) をもって閉じている。**

| コミット (merge) | WP | 内容 | root suite (単独実行) |
|---|---|---|---|
| `62e3099` | WP-0(docs) | 設計 v1.4 + 作業指示書 v1.1 | 文書のみ (基準 **1611**) |
| `c1c5c7c` | WP-0 | **衛生 2 件** (flush 間隔の fail-fast / MitateDB の契約同梱 / 同型性テストの対応表化) | **1626 passed / 0 failed / 0 skipped / 0 xfailed** (497.46s、逐次) |
| `99276a8` | WP-1 | **契約 1.6.0 公開** + 従属判断 11 + port v1.10 + 新条件 C-19 + suite 高速化 2 件 | **1675 / 0 / 0 / 2 xfailed** (132.38s) |
| `1bc7b36` | WP-2 | **r2db の 1.6.0 出荷** (locator 形 bearer + `surfaces` + 型付き catalog + flip) | **1757 / 0 / 0 / 2 xfailed** (180.18s) |
| `{WP-3 の merge}` | WP-3 | **MitateDB の 1.6.0 出荷** (同型 + catalog flip + 挙動変更 3 件 + 撤去 3 点) | **1800 / 0 / 0 / 0** (142.82s) |
| `{WP-4 の merge}` | WP-4 | 記録整理 (設計 §10/§11、作業指示書 v1.3、migration 番号の注記、本引き継ぎ) | 文書のみ (**1800** のまま) |

**集計行の出所**: 各 WP のコミットメッセージ末尾の `Root suite alone:` 行 (`git log` で確認できる)。いずれも**監督が完了ゲートで単独実行して得た実測値**であり、ゲートログは `scratchpad/wp0-160-gate.log` / `wp1-160-gate2.log` / `wp2-160-gate3.log` / `wp3-160-gate2.log` に残っている。ディレクトリ別内訳は最終形で **`r2db-api/tests` 790 / `MitateDB-api/tests` 535 / `conformance-tests` 475 = 1800**。conformance は **422 → 473 (WP-1) → 473 (WP-2) → 475 (WP-3)** と動いた。

**完了ゲートのコマンドが変わった**: WP-1 以降は **`./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`** である (逐次と同じ集計行になることを実測してから採用した)。

正本の所在 (第12次から更新された箇所のみ):

- **本フェーズの実施設計** = `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` (**v1.4**)。§3 D-1〜D-5 が確定事項、**§10 が実施記録** (WP-0〜WP-4 の全数。残るのは WP-3 / WP-4 のハッシュ欄のみ)、**§11 が将来課題** (L6-1〜L6-20。各項目に **【状態 2026-09-04 (WP-4)】** を付した)
- **発注と WP 分割** = `docs/work-orders/WORK_ORDER_PHASE6_CONTRACT_160_V1.md` (**v1.3**)。**訂正註 6 件**を置いた (本文の発注内容は書き換えていない)
- **契約の裁定記録** = `spec/CCR_DISPOSITION.md` の **従属判断 11** (項目 1 = D-1 / 項目 2 = D-2 / 項目 3 = D-3 / 項目 4 = D-3 (vii) の `upsert` 同ラベル補筆)
- **conformance の条件** = `conformance-tests/CONDITIONS.md` の **新条件 C-19** (および C-09 行の同居判定の書き換え)。**port は v1.10** (`docs/design/CONFORMANCE_ADAPTER_V1.md` §20)
- **フェーズ4 台帳 / 依頼者判断待ち** = `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.1 / §11.2。**Q4 は未着手のまま**であり、§11.2 Q4 に migration 番号の注記を足した

## 2. 到達した状態

### 2.1 契約 1.6.0 — 「共通仕様 + base URL + API key だけで使える」ことの完成

**従属判断 11 の 4 項目**:

- **項目 1 (D-1、無条件義務)** — `CredentialIssued.secret` と rotate 応答の `secret` は **完全な bearer token** である。クライアントはその文字列をそのまま `Authorization: Bearer <secret>` に提示し、**合成も分解も派生もしない**。内部構造は不透明であり、実装は契約変更なしに構造を変えてよい。**契約に `<credential_id>.<secret>` という構造は 1 文字も書いていない** (実装固有構造を漏らさない制約)
- **項目 2 (D-2、無条件義務)** — `CapabilityDocument.surfaces{data,control}.base_url`。**配備者の表明**であり、両 surface の文書が同じ値を返す。co-hosting は origin の一致として読む
- **項目 3 (D-3、条件付き義務)** — 型語彙に **`json` (any JSON value = 型を宣言せずに作られた field の型)** を足し、`EntityDescriptor.field_types` (全 field を網羅) と `SchemaOperationRequest.field_types` (任意・部分) を足した
- **項目 4 (D-3 (vii)、1.6.0 段落へは置かない同ラベル補筆)** — `structured_operations.upsert` の「mutable class を宣言していない entity への upsert / update を拒否せよ」を **`row_addressability` を提供する実装に限定**する。2 つの義務は 1 つも減っていない

**additive 性の機械確認 (WP-1)**: 1.5.0 との再帰 diff で **削除 0 / 型変更 0 / 狭化 0**、追加 6 (新規キー 5 + `field_type` enum への `json` 追加 1)、変更スカラー 5。**列挙外の差分 0 件**。確定英文は `scratchpad/phase6-contract-prose.md` から逐語複製し、監督・レビュー・監査が**それぞれ独立の正規化器**で 9 箇所すべての一致を確認した。両 peer の packaged copy は `spec/` と sha256 同一。

### 2.2 両 peer が同じ形になった 3 点

1. **credential の wire 形 (D-1)** — 両 peer とも `<credential_id>.<secret_part>` を**1 つの不透明文字列として発行**し、受理側は locator で行を引いてから `compare_digest` する (state 検査より先)。**合成は store / service 層だけで行い**、HTTP 境界・CLI・conformance adapter は返却値を verbatim 使う。**不正形 (ドット無し / 片側空 / NUL) は DB に触れずに `AUTH_INVALID`** で fail closed、未知・不一致・不正形は同一応答 (SI-10)、未知 id でもダミー verifier に `compare_digest` (タイミングオラクル無し)、否認は不帰属 (B-1) のまま耐久記録される。**互換シムは無く、既存 credential は再発行する** (r2db は `POSTGRES_PROVISIONING_RUNBOOK.md` §12a)
2. **surfaces (D-2)** — `R2DB_DATA_BASE_URL` / `R2DB_CONTROL_BASE_URL`、`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL` の 4 変数。**相対 URL / 誤終端 / 末尾スラッシュ / 不在 / 終端の取り違えを起動時に拒否**し、リクエスト host から導出せず、プロセス間の相互検証もしない。`control_plane` が `unavailable` の配備は `surfaces.control` を出さない
3. **型付き catalog (D-3)** — 両 peer の catalog が全 field の型を返す。**MitateDB は `application_catalog` を `unavailable` → `enabled` にし、`GET /v1/catalog` を実装した**。MitateDB 側は宣言型 registry (`_mdb_field_types`) を application データベースに置き、**新規 provisioning は `0003` テンプレート、既存 DB は per-application upgrade script `0006`** が作る。値検証は `cell` 層の choke point に統一した (backend 非依存)

**MitateDB の観測可能な挙動変更 3 件 (α / β / γ)** — 型無し field の既定が `text` → **`json`**、`json` / `object` / `array` の**読み出しが JSON 値へ復元される** (従来は文字列のまま返っていた)、宣言 `boolean` の wire が **0/1 → JSON boolean**。3 件とも 1.6.0 の宣言と同一コミットに入っている。

### 2.3 conformance — port v1.10 と新条件 C-19

- **port v1.10**: 新しい抽象メソッド 3 本 (`create_entity_with_declared_types` / `add_field_with_declared_type` / `isolated_control_surface`) + credential handle の **verbatim 規約** + module-level の `surfaces_cohosted(document)`。**port からメソッドを削除した初めての改訂**でもあり (`control_surface_cohosted_with_data_plane`)、**削除を WP-1 (フォールバック存置) と WP-3 (撤去) の 2 つの WP に跨って行った**
- **C-19 (client self-sufficiency)**: credential verbatim / `surfaces` の 2 文書一致と declare-and-echo / `field_types` の宣言・既定・値 round-trip と**契約 enum から導いた `json` を除く 6 語**の否定側。すべて declare-first であり、**WP-3 の flip で 4 plug 全数が load-bearing になった**
- **`xfail(strict=True)` 2 本**は WP-1 で先置きし、**最後の flip と同一コミットで撤去**した (全体 vacuity guard / adapter が bearer を合成も分解もしないことの静的固定テスト)。**フェーズ6 は xfail を 1 本も残していない**
- **L5-4 は閉じた** — 同居判定が adapter の自己申告から**配備者が宣言した `surfaces` の origin 比較**へ移り、申告メソッドは repo から 0 行になった

### 2.4 suite の高速化と速度規律 (本フェーズで確立)

完了ゲートは **8 分 17 秒 → 2 分 22 秒**になった。(A) C-14 vector 5 を `isolated_control_surface()` の上に作り替えて `sleep(61)` を撤去し (4 plug 合計 248 秒 → 約 6 秒)、(B) conformance を **adapter 単位の `xdist_group`** で並列化した (`-n 5 --dist loadgroup`、1 adapter = 1 worker、逐次と同一の集計行を実測、残骸 DB / role 0 件)。ローカル PostgreSQL の `max_connections` は **100 → 300** に変更済み (開発機の設定)。

**継続する速度規律 5 項目**: (1) 完了ゲートは監督が単独実行し、その集計行だけを正本にする。(2) subagent には suite 全体を回させず、対象ファイル・対象テストの前景直列実行に限る (`timeout` 600000 明示)。(3) レビュー・監査は `--collect-only -q` と静的照合を主とし、変異は自作分のみ最小回数。(4) 時間を食う vector は「構成値に比例しない形」へ作り替える。(5) 並列化は集計行が逐次と一致することを実測してから採る。

### 2.5 常設規律 7 項目 (作業指示書 §0.1) は本フェーズでも全 WP に適用した

第12次 §2.3 のとおりであり、変更はない。本フェーズでの効き方は §5 の教訓に書く。

## 3. クライアント連携状態

**変更なし。一報は送らない (依頼者判断 2026-09-03、1.4.0 で決定済み。1.5.0 / 1.6.0 でも方針不変)。** mitate-30 / mitate-cd は既に終了しており、**第10次 §3 / 第11次 §3 / 第12次 §3 がそのまま有効**である。本書はそれを複製しない。

**1.6.0 を将来クライアントへ伝えることになった場合の材料** (記録としてのみ残す。送る決定はされていない):

1. **`secret` は完全な bearer である** — 発行 / rotate 応答の `secret` をそのまま `Authorization: Bearer` に載せる。**合成も分解もしない**。`credential_id` は別フィールドとして返るが、bearer を組み立てる材料ではない。**MitateDB の既存クライアントは影響を受ける** — 従来 in-band 発行が返していた生の secret は、そのままでは認証を通らなかった (実質、実装知識で合成していた統合者だけが動いていた)
2. **`surfaces` で相手の surface へ辿れる** — data 文書から control surface の base URL が読め、逆も読める。**配備者の表明であり、実装は到達性を保証しない**
3. **catalog が型を返す** — `EntityDescriptor.field_types` は全 field を網羅し、値は 7 語 (`string` / `integer` / `number` / `boolean` / `object` / `array` / **`json`**)。**型を宣言せずに作った field は `json`** である
4. **MitateDB の挙動変更 3 件 (§2.2 の α / β / γ)** — 既存クライアントの読み出し結果が変わりうる唯一の箇所である
5. **`create_entity` が per-field の型を宣言できる** (`field_types`、任意・部分)。**1.5.0 のリクエストはそのまま有効**である

## 4. 次の一手 (優先順)

### 4-1. 配備実機への適用 (最優先。ただし DEPLOY 文書の 1.6.0 版が要る)

**第11次 §4-1 / 第12次 §4-1 の前提はそのまま有効**である (`docs/work-orders/DEPLOY_PHASE4_20260903.md` が正本、着手時にやることは §0.2 の運用者裁定値 4 つを埋めることと §1 の適用前チェック)。**フェーズ5 までと違い、フェーズ6 は DEPLOY 文書の手順そのものに差分を作った** — 1.5.0 は宣言キーが 2 つ増えただけで手順不変だったが、1.6.0 は次の 4 点を伴う:

1. **既存 credential の再発行** — locator 形へ移行するため、**互換シムは無い**。r2db の手順は `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` **§12a**、MitateDB は `MitateDB-api/docs/cloud-run-cloud-sql.md` の対応節。**再発行するまで既存 credential は認証を通らない**
2. **`surfaces` の環境変数 2 本を両プロセスへ配る** — `*_DATA_BASE_URL` / `*_CONTROL_BASE_URL`。**data プロセスと control プロセスの両方に同じ 2 値**を与える (どちらのプロセスも相手のホストへ接続しないため導出できない)。**形が不正なら起動時に落ちる**ので、値を用意しないまま再起動すると上がらない
3. **MitateDB の migration `0006` を既存 application データベースへ適用する** — `MitateDB-api/docs/cloud-run-cloud-sql.md` **§3.4a**。**per-application の upgrade script であり、application DB の数だけ実行する**。未適用の DB は catalog だけでなく read / write も落ちる (`StorageConfigurationError` = SERVICE 系で fail closed する形にはしてある)
4. **MitateDB の挙動変更 α / β / γ の cutover** — `MitateDB-api/docs/cloud-run-cloud-sql.md` **§6.4**。既存の物理 TEXT 列は backfill で **`string`** として登録される (`object` / `array` として使っていた列があれば `add_field` で型付き列を足して移行する — 設計 §11 **L6-16**)

r2db は virtualenv 再インストール + 再起動、MitateDB は 1.6.0 コードからのイメージで再デプロイ、という形自体は変わらない。**reader DSN を配線しない選択がいつでも正当である**という性質 (DEPLOY 文書 §0.1 の 4) も 1.6.0 で成り立つ。

### 4-2. 依頼者判断待ちと台帳

- **Q4 (`visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合)** — **未着手のまま**。正本は `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4、監督推奨は**案 B (DB 側を単一の真実にする)** を独立の設計フェーズとして起票することである。**migration 番号は「r2db `0008` / MitateDB `0007`」に変わった** — フェーズ6 が MitateDB の `0006` を先に取ったためであり、同 §11.2 Q4 と第12次 §4-2 に日付付き注記を置いた (設計 §11 L6-2)。**`surfaces` の 2 プロセス間ドリフト (L6-5a) は Q4 と同族の構造**であり、案 B が成立する際に一緒に載せるのが手当てである
- **フェーズ7 の候補 (設計 §11 L6-20)** — (a) 共通 suite に載っていない条件の共通化 (`C-00` / `C-02` / `C-04` / `C-05` / `C-07` / `C-10` は peer-local evidence only) と外部評価 指摘 1 (conformance の資源管理)、(b) 外部評価 指摘 7 (共通証拠・CI・lock)、(c) 実ソケットを持つ HTTP plug (L6-12)、(d) r2db の `surfaces` 検証ヘルパの重複解消 (L6-17)、(e) `isolated_control_surface()` の pool close 検査 (L6-13)
- **台帳 (設計 §11 に全項目の状態を付した)** — 閉じたのは **L6-2 / L6-3 / L6-8 / L5-4 / L5-6 (と L5-5 の部分閉止)**。**記録のまま**残るのは L6-4 / L6-5 / L6-5a / L6-6 / L6-7 / L6-10 / L6-11〜L6-17、および **L6-18 (作業指示書の誤り 6 件)** / **L6-19 (C-14 の `limit_class` が soft-assert)** / **L6-20 (フェーズ7 候補)**
- **L6-1 (ii) の残り** — `security/CONTROL_MAPPING.md` の **SI-06 / SI-07 の r2db cell** が、認証を「verifier の lookup そのもの」と書いたままである。D-1 後の正は「locator で行を引き、`compare_digest` が権威ある検査」であり、**次に同ファイルを触るときに訂正する**
- **L4-12 (記録のみ、実機未検証) / L4-13 (OPEN、記録のみ) / L4-8 (据え置き)** — いずれも本フェーズでは触れていない
- **1.4.0 alias の除去** (従属判断 9 項目 7 の再検討条件) — **本フェーズでも除去していない**

### 4-3. 運用規律の継続 (第12次 §4-4 を継承。本フェーズが足したのは §2.4 の速度規律 5 項目)

- **完了ゲートの実測は suite を単独実行する** — 他の pytest プロセスが走っていないことを `ps` で確認してから
- **push 前に `git log --format='%an <%ae>'` で r2fish noreply のみを確認する**
- **コミットは push とセット、さらに main へマージまでを 1 単位とする**
- **変異注入の復元は scratchpad 経由**。`git checkout` は使わない。`sleep 3` 後に sha256 を 2 回照合する
- **コミット前に変異文字列そのものを全文 grep する**
- **2026-07-28 から常駐している `pytest tests -q` のプロセス (PID 32812)** — **依頼者への確認は依然として未了**である (各 WP の完了ゲート前の `ps` 確認では他 pytest 0 件を確認できている)

## 5. 教訓の追加 (前書全項継承に追加)

- **Google Drive 同期ツリーでは「復元したコピーが後から巻き戻る」— 本フェーズでも観測した**: 同期が復元より後に走り、ハッシュ照合を通った直後のファイルが古い内容へ戻される現象は、第11次・第12次に続いて本フェーズでも起きた。**常設規律 7 の「`sleep 3` 後に sha256 を 2 回照合」はこの 1 事象のための規律**である。本フェーズではさらに、**受け入れ監査が変異バックアップ 19 ファイルを作業ツリーと `filecmp` で全数照合する**形 (実装者の照合記録を信じない) を採り、復元の完全性を独立に担保した。**復元の証拠は「復元した側の記録」ではなく「第三者の再照合」で持つ。**
- **locator 形は、クライアント由来のバイトを初めて DB の bind パラメータに載せる — その一歩が新しい穴を開けた**: WP-2 の重大バグ (NUL を含む locator が 401 ではなく 503 を返し、**認証否認が耐久監査から消える**) は、まさにこの変更が作った穴である。**WP-2 以前は bind される値が常に 64 hex 桁の verifier だった**ので、この経路自体が存在しなかった。MitateDB (WP-3) でも同型の穴が同じ形で見つかった。**教訓は 2 つ**: (i) **「クライアントの文字列が初めて下層 API の引数になる」変更は、その下層が拒否する値域 (NUL / 長さ / エンコーディング) を上流で決定論的に落とす**こと — リポジトリには既に `structured.py` に同じ判断の前例があり、**既決の判断を横展開できたはずだった**。(ii) **fail-closed でも監査が消えるなら後退である** — 503 は「認可状態が壊れている」という運用者向けシグナルであり、未認証の攻撃者がそれを任意に捏造でき、かつ否認が耐久表に残らないなら SI-14 の後退として扱う。
- **subagent は長い suite で背景待ちに入って止まる — 監督が集計行を握るだけでなく、待ち方も設計する**: 第11次・第12次と同じ現象が本フェーズでも起きた。本フェーズの対処は (i) **完了ゲートは監督が自分で回す**、(ii) subagent には**対象ファイル単位の前景直列実行**しかさせない、(iii) **長い待ちは watchdog ではなくログの完了行を待つ**形にする、の 3 点である。**「実測」と「判定」を分解して発注してあれば、モデルの可用性も待ち時間も工程の停止理由にならない** (第12次 §5 の 529 の教訓と同根)。
- **並行 WP は PostgreSQL の接続数と DB 名前空間で衝突する**: 本フェーズは WP-2 (r2db) と WP-3 (MitateDB) を別 worktree で並行させ、さらに conformance を 5 worker で並列化した。結果として **`max_connections = 100` では足りず 300 へ上げた**。あわせて、**並行作業の痕跡が文書へ漏れた** — WP-3 の `CONDITIONS.md` の C-19 行が「the two r2db-api plugs remain 1.5.0 pending WP-2's own flip (developed in a separate, parallel worktree)」という**worktree 局所の中間状態**を現在形で書いており、受け入れ監査が「現況と矛盾する」と検出した。**並行させるなら、文書に書く「現在」はどのツリーの現在かを常に確かめる。**
- **走査器・静的固定テストは「名前」に寄りかかる — 寄りかかった分だけ空振りする**: 本フェーズの静的固定テストは、当初 **合成側が変数名 `secret` に依存**しており、`token = handle.secret` を挟むだけの合成を緑で通した (レビューの変異 R1)。さらに `_COMPOSITION_ALLOWLIST` の 4 行は**1 件も抑止しておらず、行番号 2 件も陳腐化**していた (「4 plug それぞれが 1 行ずつ寄与する」というコメントが実測されていなかった = 常設規律 3 違反)。**閉じ方は 2 段構え**: 走査を受け手名に依存しない形へ広げ、**allowlist を空にすると 4 件の finding が出る**ことを実測して「allowlist が実効している」ことを示した。**「除外リストがある」ことと「除外が効いている」ことは別であり、後者は空にする変異でしか示せない。** フェーズ5 の教訓 (「除外は可視化である」) の次の段である。
- **発注文書の誤りは、実装ではなく規律で見つかる**: 本フェーズは作業指示書の誤りを **6 件** (設計 §11 L6-18) 検出した — 存在しないテストファイル、同時に満たせない完了条件、「4 plug で赤」の期待、どちらの面かで結果が変わる変異、射程外の却下案の要求、版数参照の取り残し。**すべて「変異先行」「主張は実測の後」「設計と食い違ったら設計が正」の規律が発動して出てきたもの**であり、実装物の欠陥ではない。**発注文書は正本ではなく仮説である** — 実測と食い違ったら、実装を曲げるのではなく発注文書に訂正註を置く。
