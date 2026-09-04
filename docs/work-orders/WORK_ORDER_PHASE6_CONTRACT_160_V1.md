# フェーズ6 作業指示書 — 契約 1.6.0 (credential の完全 bearer 化 + surface 発見 + 型付き catalog) + 衛生 2 件

- 版数: **v1.2 (2026-09-04、WP-1 に追補 A/B = suite 高速化 2 件を同梱。WP-0 の実施で確定した 3 点: r2db 側の `parents[3]` フォールバックも除去、同型性テストの対応表は 15 行、WP-0 テストコマンドの `r2db-api/tests/test_main.py` は誤りで実体は `test_credential_persistence.py`)**。v1.1 (2026-09-04、起草報告 8 件に対する監督裁定を反映) — (1) 否定側 vector は **`json` を除く 6 語**に課す (`json` = any JSON value には違反値が存在しない。「監督が発注時に確定する」の逃がしを削除)、(2) 義務の分類語を **unconditional (前提は句)** に統一 (設計 §8 の 1 の書式例は v1.2 の残骸であり従わない)、(3) Dockerfile のパスは実測 `MitateDB-api/docker/Dockerfile` を採る、(4) `[tool.setuptools.package-data]` 節の新設を明記、(5) **同型性テストの機構を「(相対パス, シンボル名) の対応表」駆動へ一般化し、ソース取得方式を両 peer とも `ast.get_source_segment` へ統一する (L5-6 解消)** — WP-0 の確定発注とし、「実測 → 裁定」の形を廃止、(6) 静的固定テストは合成不在 (a) + 分解不在 (b) の両方、(7) **migration の 3 分類を確定**として §7 の 5 に置く、(8) 行番号は起草時の実測値を採る。**あわせて契約英文の確定文は依頼者確定済み (2026-09-04)** である。v1.0 = 起草
- 正本設計: `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` (**v1.3、確定**)。**本書は WP 分割と発注のみを扱う** — 裁定の根拠・却下案・実装の具体形・契約英文の骨子は設計文書が正本であり、本書はそれを重複させない。設計と本書が食い違ったら**設計が正**であり、本書の誤りとして監督へ差し戻すこと
- 前提となる引き継ぎ: `docs/work-orders/HANDOVER_20260904_FABLE.md` (第12次)。**現在地は main `a211584`、root suite 単独実行 1611 passed / 0 failed / 0 skipped / 0 xfailed、うち conformance 422 passed**。ブランチ `phase6-contract-160` は main から切ってある
- 体制: Fable 監督/判断/コミット、Sonnet 実装 (コミットしない)、Opus 起草/独立レビュー/受け入れ監査
- 先行作業指示書: `docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md` (v1.7)。**§0.1 の常設規律 7 項目・完了ゲートの実測規律・禁止事項・コミット規律・「完了条件番号 → 変異」対応表の書式を本書がそのまま引き継ぐ**
- **契約英文の確定文**: **`scratchpad/phase6-contract-prose.md`** — **依頼者確定済み (2026-09-04)** である。WP-1 の実装者は**そのファイルから逐語複製**し、言い換えない (常設規律 4)

---

## 0. 問題設定

外部評価 (2026-09-03、読み取り専用調査) の指摘のうち、監督が 2026-09-04 に枠として確定した 5 件を実施する。テーマは**「共通仕様 + base URL + API key だけで、peer 非依存に利用できる」ことの完成 (クライアント発見性)**である。

| 台帳項目 / 指摘 | 内容 | 閉じ方 | WP |
|---|---|---|---|
| **指摘 2** (Q1) | credential の wire 表現が peer 間で非互換 (r2db = secret 単独 / MitateDB = `<id>.<secret>`)。共通 suite は adapter の合成で検出できない | **契約 1.6.0** の無条件義務 (secret は完全な bearer) + 両 peer とも locator 形へ + adapter の合成撤去 | WP-1 / WP-2 / WP-3 |
| **指摘 3a** (Q2) | control surface の所在をクライアントが発見できない (`CapabilityDocument` に所在キーが無い) | **契約 1.6.0** の `CapabilityDocument.surfaces` + 両 peer の配備者表明 + port v1.10 の同居判定 | WP-1 / WP-2 / WP-3 |
| **指摘 3b** (Q3) | catalog が型を返さず、MitateDB は catalog そのものが `unavailable` | **契約 1.6.0** の型語彙 7 語目 `json` + 既定型 + `field_types` 2 箇所 + MitateDB の catalog flip | WP-1 / WP-2 / WP-3 |
| **指摘 4** | flush 間隔が未検証 (0 / 負 / NaN が無音のホットループになる) | **契約不変**の衛生 — 両 peer の `_optional_float` を fail-fast へ | WP-0 |
| **指摘 5** | MitateDB が契約を同梱していない (`parents[3]` の既知結合 + Dockerfile の手動 COPY) | **契約不変**の衛生 — package-data + `importlib.resources` + byte 同一テスト | WP-0 |

**契約は 1.5.0 → 1.6.0 へ上がる。** 1.5.0 は main へ merge 済み・公開済みであり、据え置きの余地は無い (設計 §2 の 1)。**契約ファイルを変更するコミット (WP-1) は依頼者確認後に実施する** (設計 §2 の 9 / §5)。

**本フェーズで新たに閉じる台帳項目**: **L5-4** (同居判定を adapter の申告で信じている) は WP-3 で閉じる。**L6-1** (出荷済み migration の偽になるコメント) は (i)(iv) を WP-2、(ii) を WP-4 で訂正する。**L6-3 / L6-8 は設計 v1.3 で既に閉じている** (起票の記録として残る)。

---

## 0.1 常設規律 (フェーズ5 §0.1 を逐語継承。全 WP に適用)

1. **空振り禁止**: 新規テストは観測対象が 1 件以上あることを assert する (パラメータ化された全 plug/adapter で)。「このテストは X を固定する」と書くなら、X を壊す変異を全 plug で赤にした実測を報告に添える。
2. **変異先行**: 完了条件 1 項目につき、それだけを壊す変異を 1 つ対応付ける。対応する変異の無い完了条件は残さない。
3. **主張は実測の後**: docstring / CONDITIONS / runbook の断言 (「load-bearing」「必ず赤」等) は変異結果を得た後に、その数値・テスト名を引用して書く。レビュー・監査は「主張 vs 実測」を独立項目として突合する。
4. **確定文言はファイル経由**: 依頼者確定の契約文・裁定文は scratchpad の確定文ファイルから複製し、言い換えない。契約側には確定文を逐語 assert する文字列ピンのテストを置く。
5. **設計外の拡張は実装前に上げる**: 設計に無い検査・機構は実装前に報告し、監督裁定を得てから実装する。
6. **同型性テスト**: 両 peer に同名で置くテストヘルパは、peer 名・パッケージ名・パス・空白を正規化して diff する同型性テスト (両 peer 同名 `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer`) で一致を固定する。peer 間でコードを共有しない慣行は維持する (依頼者裁定 2026-09-03、案 (a))。
7. **実行規律**: テストは前景 Bash で直列、timeout パラメータ 600000 を明示、`ps` で他の pytest が無いことを確認してから。変異の復元は scratchpad backup からのコピー (`git checkout` 禁止)、`sleep 3` 後に sha256 を 2 回照合、変異文字列を全文 grep。

**本フェーズでの適用について**: フェーズ5 は WP-1 のみを規律 2 の対応表から除外していた (規律が WP-1 の実装完了後に導入されたため)。**本フェーズにその除外は無い — WP-0 から WP-4 まで全 WP が対応表を持つ。**

**対応表の書き方 (規律 2 の運用)**: 各 WP の末尾に「完了条件番号 → 変異」の対応表を置く。**テストで固定される条件にはそれだけを壊す変異を 1 つ**対応付ける。**文書・記録・設定・無変更の条件には変異を作らず、「監査が何を何と突き合わせるか」を当該条件の本文に「監査照合」として明記する**。各 WP の最後の完了条件は「**対応表に対応の無い行が無いこと**」というメタ条件である。

---

## 1. 本書が発注する確定事項 (設計 §3 の要約。根拠は設計が正本)

本節は**参照の便のための要約**である。各項の根拠・却下案・英文の骨子は設計 §3 / §4 / §5 を読むこと。

- **D-1 (Q1)**: 契約は「`CredentialIssued.secret` と rotate 応答の `secret` は**完全な bearer token**であり、クライアントは合成・分解・派生してはならない。内部構造は不透明」と明文化する。共通実現形 (契約外) は**両 peer とも locator 付き token** (`<credential_id>.<secret_part>` を 1 つの不透明文字列として発行し、受理側は credential_id で行参照してから digest を照合)。**発行の戻り値は `(credential_id, bearer)` の 2 値**である — `credential_id` は別フィールドであり、bearer から取り出す形にしてはならない (設計 §3 D-1(d)、G1)。**互換シムを置かない。既存 credential は再発行する。**
- **D-2 (Q2)**: `schemas.CapabilityDocument` に**任意キー `surfaces`** (`data` / `control` の 2 つ、それぞれ `base_url`) を追加する。**data 文書と control 文書の双方が同じ `surfaces` を返す。** 値は**配備者の表明**であり (環境変数)、起動時に形だけを検査して不正なら失敗する。同居判定は**両 URL の origin 比較** (scheme + host + port)。`surfaces.control` が無い配備 (`control_plane: unavailable`) の同居判定は `False`。
- **D-3 (Q3)**: 型語彙に **7 語目 `json` (any JSON value)** を足し、**型を宣言せずに作られた field の型は `json`** であると契約が定める。`definitions.EntityDescriptor.field_types` (条件付き義務) と `schemas.SchemaOperationRequest.field_types` (**任意キー。要求してはならない**) を追加する。不正 3 ケース (`fields` に無い名前 / 語彙外の値 / `fields` を伴わない `field_types`) は `VALIDATION_FAILED`。**catalog は schema operations で定義できる事実のみを返す** (null 可否・既定値・必須性を宣言しない)。**(vii)** `structured_operations.upsert` の 1 文に `row_addressability` の限定を**同ラベル補筆**する (1.6.0 段落へは置かない)。
- **D-4 (衛生、契約不変)**: (a) 両 peer の `_optional_float` を「非空なら有限かつ正の float 以外は起動時 fail-fast (変数名を含む `ValueError`)」へ。**`_optional_int` は触らない** (L6-4)。(b) MitateDB の契約同梱 (package-data + `importlib.resources` + byte 同一テスト + `parents[3]` 除去 + Dockerfile の手動 COPY 除去)。
- **D-5 (版束縛)**: 1.5.0 と同じ形。契約公開は単独コミット、各 peer の flip は挙動出荷と同一コミット、`versioning.version_binding` に 1.6.0 の義務を逐条列挙、**全体 vacuity guard と静的固定テストをともに WP-1 で `xfail(strict=True)` 登録し、最後の flip (WP-3) と同一コミットで撤去する**。

---

## 2. 範囲外 (本書では扱わない)

以下は**列挙のみ**である。本書の WP は一切触れない。

1. **Q4** (`visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合) — 独立の設計フェーズとして残る (`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2)。本フェーズは **migration 番号の点でのみ**接する (§8 の 5、L6-2) — WP-4 で Q4 の正本 2 文書へ日付付き注記を置く以上のことをしない。
2. **外部評価の指摘 1 (conformance の資源管理) と指摘 7 (共通証拠・CI・lock)** — フェーズ7。**指摘 6 (実機適用)** — 引き継ぎ §4-1 のまま。
3. **1.4.0 alias の除去** (`endpoints.audit_query` の `POST /v1/audit/query`) — 本フェーズでは除去しない。`surfaces` は alias を surface として扱わないが、alias の存在自体には触れない。
4. **`_optional_int` の degrade-to-default 規律** — L6-4 として記録するのみ。揃えない。
5. **`mutation_classes.rule` 側の語法** (`Where row_addressability is enabled`) — D-3 (vii) は `upsert` 節の 1 文だけを補筆する。rule 側は**変えない** (L6-10)。
6. **L5-5 / L5-6 は本フェーズで閉じる** — **範囲外ではない**。監督裁定 (2026-09-04) により、**WP-0 が同型性テストの機構を対応表駆動へ一般化し (L5-5)、ソース取得方式を両 peer とも `ast.get_source_segment` へ統一する (L5-6)**。§4 WP-0 の変更対象 C が正本である。**WP-4 でこの 2 件を閉止として記録する。**
7. **L4-8 / L4-12 / L4-13 / L5-7 / L5-8** — 本フェーズの射程外。「ついでに」直さない。
8. **クライアント通知** — 依頼者が 1.4.0 で「送らない」と決定済みであり、本フェーズの対象外。

---

## 3. WP 分割 (依存順)

| WP | 担当 | 内容 | 公開面 (契約) への影響 |
|---|---|---|---|
| **WP-0** | Sonnet 実装 → Opus レビュー → Opus 受け入れ監査 | **衛生 (契約不変、両 peer 同時 1 コミット)** — D-4(a) flush 間隔の fail-fast 化 + D-4(b) MitateDB の契約同梱 + 同型性テストの実測 | なし |
| **WP-1** | 同上 | **契約 1.6.0 単一コミット** — spec 変更 (D-1 / D-2 / D-3 / D-3 (vii) / `version_binding` 1.6.0 段落) + 両 peer パッケージ内コピーの byte 同一同期 + 従属判断 11 + 共通 vector + **port v1.10** + **全体 vacuity guard と静的固定テストの `xfail(strict=True)` 登録** + `CONFORMANCE_ADAPTER_V1.md` §20 + 文字列ピン。**peer の版数 flip を含まない。adapter の合成撤去と申告メソッドの削除も含まない** | **あり (契約公開)** |
| **WP-2** | 同上 | **r2db 単一 peer コミット** — locator 形 credential + `surfaces` + `field_types` + **`contract_version` 1.6.0 flip** + L6-1 (i)(iv) の訂正 + runbook の再発行手順 | あり (宣言拡張 + 版数宣言) |
| **WP-3** | 同上 | **MitateDB 単一 peer コミット** — 2 値発行 3 経路 + `surfaces` + 宣言型 registry (migration `0006` + backfill) + cell 層の宣言型検証 + json/boolean round-trip + `application_catalog` flip + **`contract_version` 1.6.0 flip** + **撤去 3 点同時** | あり (宣言拡張 + capability flip + 挙動変更 3 件 + 版数宣言) |
| **WP-4** | Opus 起草 → 監督 → Opus 受け入れ監査 | **記録整理** — 設計 §10、`CONDITIONS.md` (C-19 + 既存行)、`CONTROL_MAPPING.md`、日付付き注記 3 件、runbook / DEPLOY 文書の配備後チェック、従属判断 11 への実施記録、引き継ぎ第13次 | なし |

**依存順の根拠**:

- **WP-0 は独立**である (契約に触れず、WP-1 以降が触るファイルと重ならない)。ただし **WP-1 が MitateDB のパッケージ内コピーへ 1.6.0 を同期する前提**なので、**WP-0 を先に置く**。
- **WP-1 → WP-2 / WP-3** は厳密な依存である。契約 1.6.0 が公開されていない状態で peer が 1.6.0 を宣言するのは `version_binding` 規律違反であり、共通テストの 1.6.0 分岐も存在しない。
- **WP-2 → WP-3** の順序は、全体 vacuity guard と静的固定テストの `xfail` を**最後の flip WP と同一コミットで外す**という要求 (設計 §8 の 3、§9 の申し送り 4) から来る。**順序を入れ替えるなら撤去 3 点も入れ替わる。**
- **WP-4 は最後**である。WP-0〜3 の実測結果 (テスト名・集計行・実測事項の確定内容) を記録するため。

各 WP は **Sonnet 実装 → Opus コードレビュー (変異注入必須) → 差し戻し → Opus 受け入れ監査**の順で回す。

---

## 4. 各 WP の発注

### WP-0 衛生 (契約不変、両 peer 同時 1 コミット)

#### 目的

契約に一切触れずに、**運用上の 2 つの既知結合を切る** — (a) 誤設定した flush 間隔が無音のホットループになる経路を起動時に止め、(b) MitateDB が契約ファイルをリポジトリ相対パスで探す結合を package-data へ移す。**両 peer 同時に、同じ形で**行う (制約 3)。

#### 変更対象

**A. flush 間隔の fail-fast (設計 §3 D-4(a))**

| peer | 定義 | 消費者 (現行) |
|---|---|---|
| r2db | `r2db-api/src/r2db_api/main.py:200-209` `_optional_float` | 同 `:383` の flush スレッド `threading.Event.wait` |
| MitateDB | `MitateDB-api/src/mitatedb_api/main.py:151-160` `_optional_float` | 同 `:336` の同型の `wait` |

- 規則: **環境変数が非空なら、有限かつ正の float 以外は起動時に fail-fast する** — `0` / 負値 / `NaN` / `inf` / 解釈不能文字列のいずれも `ValueError` であり、**メッセージに変数名を含む**。未設定 (不在または空) のときだけ既定値へ落ちる。
- 対象変数: `R2DB_AUDIT_FLUSH_INTERVAL_S` / `MITATEDB_AUDIT_FLUSH_INTERVAL_S`。
- **`_optional_int` は触らない** (設計 §4 の D-4、L6-4)。**MitateDB の alert 側 `audit_dispatch.py:156` の `max(0.0, …)` も触らない** — 射程外である。
- fail-fast の形は新規ではない — `R2DB_CONTROL_PLANE_STATUS` (`r2db-api/src/r2db_api/main.py:165`、許容語彙を `:154` の集合で検査) / `MITATEDB_CONTROL_PLANE_STATUS` (`MitateDB-api/src/mitatedb_api/config.py:93-99`) の既存の起動時検査と同型にする。

**B. MitateDB の契約同梱 (設計 §3 D-4(b))**

- **新設**: `MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` — `spec/data-service-api.v1.json` と**バイト同一**。
- **`MitateDB-api/pyproject.toml`**: package-data の配線を新設する。**現状この pyproject には `[tool.setuptools.*]` の節が 1 つも無い** (r2db は `r2db-api/pyproject.toml:43-48` に `[tool.setuptools.package-data]` を持ち、`r2db_api = ["contract/*.json"]` と書く)。r2db と同型に置くこと。
- **`MitateDB-api/src/mitatedb_api/http.py:47`** の `_CONTRACT_PATH = Path(__file__).resolve().parents[3] / "spec" / …` を除去し、`importlib.resources` 経由の読み込みへ改める (r2db の loader コメントは `r2db-api/src/r2db_api/http.py:45-46`)。
- **byte 同一テスト**を `MitateDB-api/tests/test_http.py` に置く — `r2db-api/tests/test_http.py:286` `test_packaged_contract_copy_is_byte_identical_to_spec_source_of_truth` の**ほぼ逐語の双子**であり、`Path(__file__).parents[2] / "spec"` の深さも一致する (設計 §1.5 の 6)。**r2db 側のテストを緩めない。**
- **`MitateDB-api/docker/Dockerfile`**: `:111` の `COPY spec/data-service-api.v1.json /opt/venv/lib/spec/…` と、`:85` 以降の既知結合の注記を除去する。**build context の記述 (`:20-40` 付近、`spec/` を含めるためにビルド元をリポジトリルートへ引き上げた経緯) を変えるかどうかは、実測してから監督へ上げる** — 設計は COPY と注記の除去までを決めており、build context の縮小は決めていない (常設規律 5)。
- **既存の `MitateDB-api/contracts/` ディレクトリ (`foundation.json` 等) とは別物である** — 新設するのは `src/mitatedb_api/contract/` (単数形、パッケージ内) である。混同しないこと。

**C. 同型性テストの機構の一般化 (監督裁定 2026-09-04。設計 §9 WP-0 / §11 L5-5 / L5-6 に対する確定)**

**現行の同型性テストは、兄弟 peer の `tests/test_audit_query.py` を path 指定でテキスト読みし、その中の 11 個のヘルパ名を突き合わせる形**である (`r2db-api/tests/test_audit_query.py:2235` / `MitateDB-api/tests/test_audit_query.py:1933`)。`_optional_float` は `src/…/main.py` の**製品コード**、byte 同一テストは `tests/test_http.py` にあり、**いずれも現行の走査範囲 (兄弟の `test_audit_query.py` 1 ファイル) の外にある**。**裁定は「走査範囲を広げる」であり、その形まで確定している。実測して裁定を仰ぐ形は採らない。**

- **機構を「(相対パス, シンボル名) の対応表」駆動へ一般化する** — 現行の「1 ファイル + ヘルパ名タプル」を、**peer ルートからの相対パスとシンボル名の対**を列挙した**対応表**に置き換える。対応表の各行が 1 対の突き合わせを定義する。**両 peer 同名の対応表**を持ち、内容は同一である。
- **既存 11 ヘルパを初期行として維持する** — `tests/test_audit_query.py` の 11 シンボルは、そのまま同じ相対パスの 11 行になる。**1 対も落とさない。**
- **本 WP で 2 行を追加する** — `src/<peer package>/main.py::_optional_float` と、`tests/test_http.py` の **byte 同一テスト関数**。
- **ソース取得方式を `ast.get_source_segment` に統一する (L5-6 解消)** — **非対称は「peer 間」ではなく「自 peer 側 vs 兄弟 peer 側」である (起草時の実測)**: 両 peer のテストとも、**自分側は `inspect.getsource`** (`r2db-api/tests/test_audit_query.py:2321` / `MitateDB-api/tests/test_audit_query.py:2011`、**デコレータを含む**)、**兄弟側は `ast.get_source_segment`** (同 `:2326` / `:2016`、**デコレータを含まない**) で取っている。**同じ 1 対の左右で取得方式が違う**ため、将来どちらかにデコレータが付くと**実装差ではなく取得方式差で赤/緑がぶれる**。**自分側も `ast.get_source_segment` へ揃える** (自ファイルもテキストとして読み、AST から取る)。**第12次引き継ぎ §4-2 の (i) が「MitateDB 側は `inspect.getsource`、r2db 側は `ast.get_source_segment`」と書いているのは、片方のテストから見た記述であり、実体は上記のとおりである** — WP-4 でこの点を訂正註として記録する。
- **既存の性質を弱めない** — 正規化は **行頭インデントを保存する** (トークン列が同じでインデントだけが違う意味差を検出するため)、**自己比較は構文的に禁止する** (`"MitateDB-api" in parts` / `"r2db-api" not in parts` の assert)、**対象シンボルの不在・内容不一致はいずれも赤**である。
- **対応表の行が 13 行であることを直接 pin する** — 対応表そのものの内容を固定するテストを置く (フェーズ5 の「走査対象フィールド集合を pin するテスト」と同じ性格の一回きりの人手固定)。**行が黙って減ることを検出する唯一の手段である。**

#### 完了条件 (検証可能な形)

1. **flush 間隔の fail-fast (両 peer)** — 非空かつ「有限・正」でない値 (`0` / 負値 / `NaN` / `inf` / 解釈不能文字列) を与えると**起動時に `ValueError` で失敗し、例外メッセージに当該環境変数名が含まれる**こと。**両 peer について、5 形すべてを個別ケースで観測する**こと (parametrize 可)。
2. **既定値経路の非後退** — 環境変数が不在または空のときは従来どおり既定値が使われること。**この経路のテストが存在する**こと。
3. **`_optional_int` が無変更であること** — **監査照合 (変異を作らない)**: 監査は `git diff -- r2db-api/src/r2db_api/main.py MitateDB-api/src/mitatedb_api/main.py` の変更行を、`_optional_float` の定義行範囲および呼び出し側の行と突き合わせ、**`_optional_int` の定義本文に 1 行の変更も無い**ことを確認する。あわせて `MitateDB-api/src/mitatedb_api/audit_dispatch.py` が **diff に現れない**ことを確認する。
4. **MitateDB のパッケージ内コピーが byte 同一** — `MitateDB-api/tests/test_http.py` の byte 同一テストが緑であり、`resources.files("mitatedb_api.contract")` 経由で読んでいること。**r2db 側の同名テストが緩められていない**こと。
5. **`parents[3]` の消滅** — `grep -rn "parents\[3\]" MitateDB-api/src` が **0 行**であり、契約の読み込みが `importlib.resources` 経由であること。
6. **package-data の配線** — `MitateDB-api/pyproject.toml` に `[tool.setuptools.package-data]` が存在し、`mitatedb_api = ["contract/*.json"]` 相当を宣言していること。
7. **Dockerfile の手動 COPY と注記の除去** — **監査照合 (変異を作らない)**: 監査は `git diff -- MitateDB-api/docker/Dockerfile` を読み、(i) `COPY spec/data-service-api.v1.json …` の行が消えていること、(ii) 既知結合を説明する注記が消えていること、(iii) **build context に関する記述が変更されている場合は、監督裁定の記録が完了報告に添えられている**ことを確認する。
8. **同型性テストの一般化** — 機構が **(相対パス, シンボル名) の対応表**駆動であり、**対応表が 13 行** (既存 11 + `main.py::_optional_float` + `tests/test_http.py` の byte 同一テスト関数) であること。**対応表の内容を直接 pin するテストが存在する**こと。**ソース取得方式が左右とも `ast.get_source_segment` に統一されている**こと — **同型性テスト関数の本体に `inspect.getsource` が 0 件**であること (`MitateDB-api/tests/test_main.py:233` の `inspect.getsource` は別用途であり**触らない**ので、リポジトリ全体の grep で判定しない)。**行頭インデントの保存と自己比較の構文的禁止が保たれている**こと。
9. **契約不変** — **監査照合 (変異を作らない)**: 監査は `git diff -- spec/ r2db-api/src/r2db_api/contract/` が**空**であること、および両 peer の `contract_version` が **1.5.0 のまま**であること (`r2db-api/src/r2db_api/service.py:882` / `r2db-api/src/r2db_api/control_plane.py:714` / `MitateDB-api/src/mitatedb_api/cell.py:1280` / `MitateDB-api/src/mitatedb_api/control_plane.py:1364`) を確認する。**新設する MitateDB のパッケージ内コピーも 1.5.0 の byte 同一コピーである。**
10. **対応表に対応の無い行が無いこと** (メタ条件、常設規律 §0.1 の 2)。
11. **完了ゲート** — root suite を単独実行し、**`failed` 0 / `skipped` 0 / `xfailed` 0**、`passed` が **1611** から増えていること。**conformance は 422 のまま不変**であること。**増分の内訳 (どのテストが何本の収集 id を増やしたか) を完了報告に書く**こと。**監査照合**: 監査は完了報告の増分内訳と、基準値 1611 との差を突き合わせ、`基準値 + 純増 = 集計行` が成立することを確認する。

#### 非 vacuity 要件

- fail-fast のテストは、**実際に環境変数を与えて起動経路 (`_optional_float` を呼ぶ実経路) を通し、`ValueError` を観測する**こと。関数を直接呼ぶだけで済ませる場合は、**その関数が flush 間隔の唯一の消費者へ実際に届いていること**を別途 assert する。
- byte 同一テストは、**packaged copy を `importlib.resources` 経由で実際に読む**こと。ファイルパスを直に組んで読む形にしない (それでは `parents[3]` の除去を固定できない)。

#### 同型性テスト対象

**対応表 13 行** — 既存 11 (`tests/test_audit_query.py` の走査器支援ヘルパ群) + `src/<peer package>/main.py::_optional_float` + `tests/test_http.py` の byte 同一テスト関数。**機構の一般化とソース取得方式の統一 (`ast.get_source_segment`) は変更対象 C のとおり本 WP の確定発注**である。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

**完了条件 → 変異の対応表 (常設規律 §0.1 の 2。対応の無い行を残さない)**

| 完了条件 | 対応する変異 (それだけを壊すもの) |
|---|---|
| 1 flush 間隔の fail-fast | **変異 1** (片 peer の `_optional_float` を旧形 = degrade-to-default へ戻す → 当該 peer の 5 ケースが赤) |
| 2 既定値経路の非後退 | **変異 2** (`if not raw: return default` を落とす → 既定値経路のテストが赤) |
| 3 `_optional_int` 無変更 | **監査照合** (変異を作らない。完了条件 3 に照合対象を明記) |
| 4 byte 同一 | **変異 3** (`MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` を 1 バイト改変 → MitateDB の byte 同一テストが赤。r2db 側は緑のまま = 2 本が独立であることの実測) |
| 5 `parents[3]` の消滅 | **変異 4** + **対照 4′** (下記) |
| 6 package-data の配線 | **変異 5** (`pyproject.toml` の package-data 行を落とし、再インストール後に packaged copy が解決できないこと → byte 同一テストが赤) |
| 7 Dockerfile | **監査照合** (変異を作らない。完了条件 7 に照合対象を明記) |
| 8 同型性テストの一般化 | **変異 6** (対応表から 1 行を落とす → 対応表を pin するテストが赤) + **変異 7** (片側 peer の `_optional_float` の判定を 1 箇所だけ変える → 同型性テストが赤。**新しく足した行が実際に突き合わされている**ことの実測) |
| 9 契約不変 | **監査照合** (変異を作らない。完了条件 9 に照合対象を明記) |
| 10 対応表が全行埋まる | 本表そのもの (メタ条件。変異は作らない) |
| 11 完了ゲート | **監査照合** (変異を作らない。完了条件 11 に照合対象を明記) |

1. **fail-fast の巻き戻し** — 片 peer の `_optional_float` を旧形 (`except ValueError: return default`、正値検査なし) へ戻し、**当該 peer の 5 ケースが赤**になること。他方の peer は緑のままであること (**両 peer 分のテストが独立に存在する**ことの実測)。
2. **既定値経路の欠落** — `if not raw: return default` を除去し、**既定値経路のテストが赤**になること。「非空なら fail-fast」と「空なら既定値」が別々に固定されていることの実測である。
3. **packaged copy の 1 バイト改変** — `MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` を 1 バイト改変し、**MitateDB の byte 同一テストだけが赤**になること (r2db 側は緑)。
4. **packaged copy の退避** — `MitateDB-api/src/mitatedb_api/contract/` の JSON を一時退避し、**`MitateDB-api/tests/test_http.py` が赤**になること (loader が packaged copy を実際に読んでいることの実測)。
   - **対照 4′ (緑であることを示す対照)** — `spec/data-service-api.v1.json` を一時退避し、**`./.venv/bin/python -m pytest -q MitateDB-api/tests/test_http.py` のうち byte 同一テスト以外が緑のまま**であること (byte 同一テストは比較相手が消えるので赤になる — これは正しい)。`parents[3]` 結合が消えたことの実測である。**この対照は `MitateDB-api/tests` に限定して実行する** — `spec/` の退避は `conformance-tests/adapter.py` の `CONTRACT_PATH` を壊すため、root suite では走らせない。**対照であることを報告に明記する。**
5. **package-data 行の脱落** — `MitateDB-api/pyproject.toml` の package-data 宣言を落として再インストールし、packaged copy が解決できずに**赤**になること。
6. **対応表の縮小** — 同型性テストの対応表から **1 行を落とす** (`main.py::_optional_float` の行)。**対応表を pin するテストが赤**になること。これが赤にならないなら「13 行である」ことは固定されておらず、行が黙って減っても誰も気付かない。
7. **同型性の片側崩し** — 片側 peer の `_optional_float` の判定を 1 箇所だけ変え (比較演算子 1 つ)、**同型性テストが赤**になること。正規化 (peer 名・パッケージ名・パス・空白) がこの差まで吸収していないこと、および**新しく足した行が実際に突き合わされている**ことの実測である。

**復元後、変異文字列を全文 grep してゼロを確認する。** 変異 4 / 4′ / 5 はファイルの退避・再インストールを伴うので、**復元後に sha256 二重照合と `pip install -e` の再実行結果も報告に書くこと。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests/test_main.py MitateDB-api/tests/test_main.py
./.venv/bin/python -m pytest -q r2db-api/tests/test_http.py MitateDB-api/tests/test_http.py
./.venv/bin/python -m pytest -q          # 完了ゲート、リポジトリルートで単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **fail-fast の射程超過** — `_optional_int` や alert 側の `max(0.0, …)` へ手が伸びていないか (射程外、L6-4)。
2. **degrade-to-default の残骸** — 「解釈不能文字列だけ fail-fast、`0` は既定値へ」のような**部分的な適用**になっていないか。5 形すべてが fail-fast であること。
3. **エラーメッセージ** — 変数名を含むか。運用者が「どの変数が悪いか」を読めない形になっていないか。
4. **loader の形** — `importlib.resources` 経由になっているか、パスを組み直す別形 (`Path(__file__).parent / "contract"`) へ退化していないか。後者では package-data の配線が load-bearing にならない。
5. **byte 同一テストの双子性** — r2db 側とほぼ逐語であるか。`parents[2]` の深さが一致しているか。**片側だけ弱い assert (「存在する」「JSON として読める」) になっていないか。**
6. **同型性テストの一般化による弱化** — 対応表駆動へ移す際に、**行頭インデントの保存**・**自己比較の構文的禁止**・**不在も内容不一致も赤**という既存の性質が落ちていないか。既存 11 対が**1 対も落ちていない**か。`ast.get_source_segment` への統一が片側だけになっていないか。
7. **契約への波及** — `spec/` と r2db のパッケージ内コピーが 1 バイトも動いていないか。新設する MitateDB のコピーが 1.5.0 の byte 同一コピーであるか。
8. **秘密の混入** — Dockerfile / pyproject / runbook の追記に実ホスト名・実 DSN が無いか。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-1 契約 1.6.0 公開 + port v1.10 + 共通 vector

#### 目的

契約 1.6.0 を公開し、(i) secret が**完全な bearer** であること、(ii) `surfaces` による**所在の発見**、(iii) `field_types` による**型の発見**を契約の義務として置き、(iv) 三者を共通 suite で機械的に固定する。**peer の挙動は一切変えない。**

**この WP のコミットは依頼者確認後に行う** (設計 §2 の 9 / §5)。**契約の英文は `scratchpad/phase6-contract-prose.md` の確定文 (依頼者確定済み、2026-09-04) から逐語複製する** — 言い換え・要約・語順の入れ替えを行わない (常設規律 4)。**文言は確定しているので、実装者は確定待ちを理由に spec の着手を遅らせない** — 監督が確定文ファイルを渡した時点で spec を書いてよい。コミットの前に監督が依頼者へ再度明示する手続きは従前どおり残る。

#### 変更対象

**1. `spec/data-service-api.v1.json`**

- `contract_version` を **`"1.6.0"`** へ (現行 `:6`)。
- **D-1 (項目 1)**: `security.schemes.application_credential` / `security.schemes.control_credential` の description、`schemas.CredentialIssued.secret`、および **rotate 応答の `secret` (application / control の両方)** に確定文 §5 (1) を置く。
- **D-2 (項目 2)**: `schemas.CapabilityDocument.properties` に**任意キー `surfaces`** を追加する (`data` / `control`、それぞれ `base_url`)。**`required` を変えない。** 確定文 §5 (2)。
- **D-3 (項目 3)**: `schemas.SchemaOperationRequest.properties.field_type` の enum に **`"json"`** を追加 (現行 6 語 → 7 語)、`definitions.EntityDescriptor.properties.field_types` を追加、`schemas.SchemaOperationRequest.properties.field_types` を追加。**`fields` の型 (string 配列) を変えない。** 確定文 §5 (3)。
- **D-3 (vii) (項目 4)**: `structured_operations.upsert` の対象 1 文を確定文 §5 (5) の**全文 (2 句)** で置換する。**1.6.0 段落へは置かない。**
- `versioning.version_binding` に **1.6.0 段落**を追加する (確定文 §5 (4))。**あわせて末尾の遡及否認の既存 4 行それぞれに `1.6.0-only` を加える** (§5 の G19 — 5 行目を足すだけでは列挙が閉じない)。
- **書式は既存に揃える** — `Since 1.6.0 (subordinate ruling 11, item N, …)` の体裁。**義務の分類語は確定文 §5 (4) が正である** — **項目 1 と項目 2 は unconditional** であり、control surface に関わる部分は「control surface が提供されている限り」という**前提を句として添える** (契約既存の 1.4.0 (b) と同じ分類)。**条件付きと呼ぶのは capability の status に依存する項目 3 だけ**である。**設計 §8 の 1 に残る `conditional on control_plane being provided` という書式例は v1.2 の残骸であり、これに従わない** (監督裁定 2026-09-04)。

**2. 両 peer のパッケージ内コピー**

- `r2db-api/src/r2db_api/contract/data-service-api.v1.json`
- `MitateDB-api/src/mitatedb_api/contract/data-service-api.v1.json` (**WP-0 で新設**)
- いずれも `spec/data-service-api.v1.json` と**バイト同一**に同期する。両 peer の byte 同一テストがこれを固定する。**両テストを緩めない。**

**3. `spec/CCR_DISPOSITION.md`**

- **従属判断 11** を house style で記録する (従属判断 10 と同じ構成)。
  - **(a) 各項目の内容と根拠** — 項目 1 = D-1、項目 2 = D-2、項目 3 = D-3、**項目 4 = D-3 (vii)** (`upsert` の同ラベル補筆。従属判断 10 項目 2 と同じ形式)。
  - **(b) すべて additive である根拠** — 設計 §8 の 4 が挙げる根拠を項目ごとに書く。**MitateDB の挙動変更 3 件 (α)(β)(γ) が契約の additive 性を損なわない理由も書く。**
  - **(c) 版数の扱い**、**(d) 監督裁定の参照 + 却下側の明記** (設計 §4 の Q1 却下 4 件 / Q2 却下 3 件 / Q3 却下 5 件 / D-4 却下 2 件)。
  - **義務の条件付き性を独立した太字段落で書く** — **項目 1 と項目 2 は無条件義務** (control surface に関わる部分は「control surface が提供されている限り」という前提を句として持つ)、**条件付きなのは項目 3 だけ** (`application_catalog` / `schema_operations` の status に依存)、**項目 4 は 1.6.0 段落へ置かない同ラベル補筆なのでこの分類の外**。`version_binding` 本文の列挙と **1 対 1 に対応させる**。
  - **項目ごとの再検討条件。**

**4. 共通テスト — 新 vector 3 種 (設計 §6.2 の 1〜3)**

いずれも **1.6.0 以上を宣言する peer に対して**課す (declare-first 分岐は既存の `_semver_tuple` を使う)。

- **(1) credential verbatim (D-1)** — issue / rotate が返した `secret` を、**adapter の加工なしに**そのまま bearer として提示して認証が通ること。**surface ごとに書き分ける** — **application credential は data surface** (`GET /v1/capabilities`)、**control credential は control surface** (`GET /control/v1/capabilities`)。**直積では書かない** (交差は既存 C-13 / C-14 が拒否側で固定済み)。**precondition**: `control_plane` が `unavailable` 以外。
- **(2) `surfaces` (D-2)** — **plug ごとの適用範囲を分ける**:
  - **(i) data 文書と control 文書の `surfaces` が一致すること**、**(ii) `control_plane` が `unavailable` 以外なら `surfaces.control` が存在し、`unavailable` なら存在しないこと** — **4 plug 全数**。
  - **(iii) declare-and-echo** (`surfaces.<x>.base_url` + `/capabilities` が同じ `contract_version` と同じ `surfaces` を返すこと) — **HTTP plug 2 件のみ**。in-process plug は実 URL を持たず合成の偽ドメインを申告するため、4 plug 全数に課すと空振りする (常設規律 1)。**この分割と、in-process plug では宣言された URL の実在を検証していないことを `CONDITIONS.md` に限界として開示する** (WP-4)。
  - **(iv) 同居判定が origin 比較で得られること** — **申告メソッドの消滅の確認は WP-3 まで課さない**。
- **(3) `field_types` と round-trip (D-3)** — (i) catalog の全 entity で `fields` ⊆ `field_types` のキー集合、かつ値が契約の **7 語 enum** に収まること; (ii) `create_entity` の `field_types` / `add_field` の `field_type` で宣言した型が catalog にそのまま返ること (**宣言の** round-trip); (iii) **値の round-trip** — 型を宣言せずに作った field が `json` として返り、そこへ書いたオブジェクト・配列・文字列・数値・真偽値の**それぞれが同じ JSON 値として読み戻せる**こと。**`boolean` を宣言した field についても同じ round-trip を課す**; (iv) **否定側** — **宣言型に合わない値の書き込みが `VALIDATION_FAILED` で拒否されること**を、**`json` を除く 6 語** (`string` / `integer` / `number` / `boolean` / `object` / `array`) **それぞれについて 4 plug 全数**で見る。**`json` には課さない** — `json` は any JSON value であり違反値が存在しないためである (監督裁定 2026-09-04。設計 §6.2 の 3 (iv) は「7 語それぞれ」と書くが、これは実行不能であり、6 語が正である)。値の例: `boolean` に `7` / `integer` に `"abc"` / `number` に `"abc"` / `object` に配列 / `array` にオブジェクト / `string` に数値。**precondition**: `application_catalog` が `unavailable` 以外。**`field_types` を送らない `create_entity` が受理されること自体も (iii) が併せて見る** (任意性の実測)。

**vector の配置先ファイルと `CONDITIONS.md` の登録先は監督裁定事項である** — 設計 §6.3 は**新条件 C-19「クライアント自足性」を 1 行切る**案を推奨として挙げ、監督が裁定するとしている (現行の最終行は C-18)。**実装者は裁定を受けてから置く。裁定前に置き先を決めない。**

**5. `conformance-tests/adapter.py` — port v1.10 (設計 §6.1)**

- **(a) credential の verbatim 使用を規約にする** — port の規約文に「**adapter は issue / rotate / bootstrap / reset が返した `secret` を、いかなる加工もせずそのまま bearer として使う**」を置く。`CredentialHandle.secret` (`conformance-tests/adapter.py:64-68`) / `ControlCredentialHandle.secret` の意味を「**完全な bearer token**」と定義し直す。**`_Session.bearer` フィールド自体は残す** (意味は「`Bearer ` の後ろに置く文字列」)。**発行は `(credential_id, bearer)` の 2 値**であり、「**adapter は `credential_ref` に発行側が返した `credential_id` を、bearer に発行側が返した `secret` を、それぞれそのまま持つ — 連結も分割もしない**」と書く。
- **(b) 同居判定を `surfaces` 由来にする** — 判定関数を port v1.10 に置く。**`surfaces` を返す peer では origin 比較を正とし、返さない (1.5.0 宣言の) peer では従来の申告メソッド `control_surface_cohosted_with_data_plane()` (`conformance-tests/adapter.py:1214`) へフォールバックする。** `surfaces.control` が無い配備の判定は `False`。**申告メソッドの削除は WP-3 である** — `conformance-tests/test_c09_audit_evidence.py:868` が版分岐なしに無条件で呼んでおり、WP-1 で消すとこの無条件 vector が 2 つの WP をまたいで判定不能になる。
- **(c) catalog vector 用の fixture** — 共通 suite が「create / add_field で宣言した型」を知った状態で catalog と読み出し値を突合できるようにする。**既存 `Fixture` に宣言型を持たせる形か新メソッド 1 本かは本 WP で確定し、報告に書く** (設計は「共通 suite が自分の宣言型を知った状態で突合できること」までを決めている)。

**6. 4 adapter の port v1.10 対応**

- `r2db-api/conformance/conformance_adapter_r2db.py` / `conformance_adapter_r2db_http.py`
- `MitateDB-api/conformance/conformance_adapter_mitatedb.py` / `conformance_adapter_mitatedb_http.py`
- **追加分のみ。** `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:838` / `:988` / `:943-945` / `:1272-1274` の**合成の撤去は WP-3 である** — MitateDB が 1.5.0 (raw 返却) のままの本 WP で撤去すると HTTP plug の既存テストがその場で全滅する。**申告メソッドの実装も 4 plug に残す** (フォールバック経路として実際に使われる)。

**7. `docs/design/CONFORMANCE_ADAPTER_V1.md`**

- **§20 (v1.10) を新設**する。§19 (v1.9) と同じ構成 — 追加/削除メソッドの意味論 / 既存機構との関係 / **Compatibility impact**。
- **メソッドを削る port 改訂は本 port で初めてである**ことと、**削除が WP-3 に落ちること・4 plug すべてに同時に落ちること** (Python の `ABC` は不要になったメソッドを自動では消さない) を §20 に明記する。**port の版数は本 WP で v1.10 に上げ、WP-3 の削除もその v1.10 の一部として §20 に記す** (2 つの WP にまたがる 1 つの port 改訂であることを明記する)。

**8. 2 本の `xfail(strict=True)` 登録**

- **全体 vacuity guard** `…_every_adapter_declares_1_6_0` — **既存の `test_c09_every_control_surface_adapter_takes_the_provided_branch` と同形** (adapter fixture を取らない**非 parametrize の関数 1 本**が `registered_adapters()` を自前で走査する)。**adapter 名のハードコード列挙にしない。** 収集件数は **1 件**である。reason に「no peer declares 1.6.0 yet; un-xfailed by the last flip WP」旨を書く。
- **静的固定テスト (adapter に合成・分解が無いこと)** — 4 adapter のソースを走査し、**2 つの性質**を固定する。**(a) 合成が無いこと** — `credential_id` (または `credential_ref`) と `secret` を連結する式が存在しない。**(b) 分解が無いこと** — `secret` (または handle の bearer 値) に対する `split` / `partition` / `rsplit` / 添字スライスが存在しない。**(b) を落とすと抜け道が残る** — 合成をやめても、id を bearer から割り出す実装は連結式を持たないので (a) だけでは緑のまま通る。**規則の形は逐語プロトタイプの後に確定する** (常設規律 5) — 実装者は先にプロトタイプを scratchpad へ置き、走査対象・許容形・除外リストの要否を実測して報告する。

**9. 文字列ピンと `upsert` 節の目視突合**

- `conformance-tests/test_contract.py` に、**確定文 §5 (1)〜(5) と遡及否認 4 行**を逐語 assert する文字列ピンを置く (バッククォート・強調・em dash の正規化のみ許容)。
- **再帰 diff は description 文字列の内部から義務が消えたことを検出できない** (設計 §8 の 4)。**D-3 (vii) は 2 義務を運ぶ 1 文を書き換える**ので、**補筆の前後の文を確定文ファイルから逐語で文字列ピンし、`upsert` 節が運ぶ義務の個数が 1.5.0 と同数 (2) であることを目視で突合し、その結果を完了報告に書く。**

#### 完了条件 (検証可能な形)

1. **契約版数と 1.6.0 段落** — `contract_version` が `"1.6.0"` であり、`versioning.version_binding` に 1.6.0 段落が存在し、**遡及否認の既存 4 行それぞれに `1.6.0-only` が加わっている**こと。
2. **項目 4 の置き場所** — D-3 (vii) の補筆が **`structured_operations.upsert` の本文へ**入っており、**1.6.0 段落には入っていない**こと。**前半 (unique key 不在時の upsert 拒否) が逐語で残り、後半だけに限定が付いている**こと。限定句が **`other than unavailable`** であること (`enabled` だけにしていないこと)。**`mutation_classes.declaration_required` を出典として引いていない**こと。**`mutation_classes.rule` 側を変更していない**こと。
3. **確定文の逐語性** — §5 (1)〜(5) が `scratchpad/phase6-contract-prose.md` から**逐語**で複製されていること。**言い換え・要約・語順の入れ替えが 1 箇所も無い**こと。**監査照合**: 監査は確定文ファイルと spec の該当箇所を機械照合し、**正規化 (バッククォート・強調・ASCII 二重ハイフン・em dash) 以外の差が 0 件**であることを確認する。**不一致が出たら、実装を疑う前に照合器の正規化を疑う** (フェーズ5 の教訓)。
4. **additive 性の機械確認** — 1.5.0 → 1.6.0 の再帰比較で **キー削除 0 / 型変更 0 / enum・required・閉鎖宣言の退行 0**、かつ **enum は追加のみ** (`field_type` が 6 語 → 7 語) であること。**変更されたスカラーとその件数を完了報告に列挙する**こと。**監査照合**: 監査は再帰 diff の出力を、追加キー一覧 (`surfaces` / `EntityDescriptor.field_types` / `SchemaOperationRequest.field_types`) と変更スカラー一覧 (`contract_version` / `version_binding` / 各 description) と突き合わせ、**列挙外の差分が 0 件**であることを確認する。
5. **`upsert` 節の義務個数** — 補筆後の `upsert` 節が運ぶ義務が **1.5.0 と同数 (2)** であることを、確定文と現物の突合で確認した記録が完了報告にあること。
6. **両 peer の packaged copy が byte 同一** — 両 peer の byte 同一テストが緑。**どちらのテストも緩めていない**こと。
7. **従属判断 11** — `spec/CCR_DISPOSITION.md` に (a)〜(d) + 項目ごとの再検討条件 + **義務の条件付き性の独立した太字段落**を持って存在すること。条件付き性の段落が `version_binding` の項目分割 (項目 1・2 = 無条件 / 項目 3 = 条件付き / 項目 4 = 分類外) と **1 対 1 で対応**していること。**MitateDB の挙動変更 3 件が additive 性を損なわない根拠が書かれている**こと。
8. **新 vector 3 種の存在と declare-first 分岐** — 設計 §6.2 の 1〜3 が実在し、`_semver_tuple` による 1.6.0 分岐を持つこと。**(2)(iii) の declare-and-echo が HTTP plug 2 件に限定され、(2)(i)(ii) と (3) が 4 plug 全数に課されている**こと。**(3)(iv) の否定側が `json` を除く 6 語それぞれについて存在し、`json` には課されていない**こと (6 語 × 4 plug が収集されること)。**本 WP の時点ではどの adapter も 1.6.0 分岐を通らない**こと (peer は未 flip)。
9. **vector 配置先の裁定** — vector のファイルと `CONDITIONS.md` の登録先について**監督裁定を受けた記録**が完了報告にあり、実装がそれに従っていること。**実装者が独断で決めていない**こと。
10. **port v1.10 (a) verbatim 規約** — port の規約文に verbatim 使用と「`credential_ref` は発行側の `credential_id` をそのまま持ち、bearer から取り出さない」が書かれていること。`CredentialHandle.secret` / `ControlCredentialHandle.secret` の意味が「完全な bearer token」へ改められていること。**`_Session.bearer` フィールドが残っている**こと。
11. **port v1.10 (b) 同居判定** — `surfaces` 由来の判定関数が port に存在し、**`surfaces` を返さない peer では従来の申告メソッドへフォールバック**すること。**申告メソッドが port からも 4 plug からも削られていない**こと。**`test_c09_audit_evidence.py:868` の無条件 vector が 4 plug で従来どおり緑**であること (置換が挙動を変えないことの実測)。
12. **port v1.10 (c) catalog fixture** — 共通 suite が宣言型を知った状態で突合できる形が存在し、**採った形 (既存 `Fixture` の拡張か新メソッドか) が完了報告に書かれている**こと。
13. **4 adapter が port v1.10 を実装** — `ABC` により 4 本すべてが生成できること。**合成の 4 箇所と申告メソッドが残っている**こと (撤去は WP-3)。
14. **`CONFORMANCE_ADAPTER_V1.md` §20** — 新設され、§19 と同じ構成 (意味論 / 既存機構との関係 / Compatibility impact) を持ち、**削除が WP-3 に落ちること・4 plug 同時であること・2 つの WP にまたがる 1 つの port 改訂であること**が明記されていること。
15. **全体 vacuity guard** — `xfail(strict=True)` で登録され、**`registered_adapters()` の機械走査**であること (adapter 名のハードコード列挙でないこと)、**収集件数が 1 件**であること。**既存の 1.4.0 / 1.5.0 の guard 群が弱められずに緑のまま**であること。
16. **静的固定テスト** — 合成不在 (a) と分解不在 (b) の**両方**を見る形で `xfail(strict=True)` 登録されていること。**規則の逐語プロトタイプが scratchpad にあり、走査対象・許容形・除外リストの要否の実測が完了報告に書かれている**こと。
17. **文字列ピン** — 確定文 §5 (1)〜(5) と遡及否認 4 行を逐語 assert するテストが存在すること。
18. **peer の宣言が動いていないこと** — 両 peer の `contract_version` が **1.5.0 のまま**であること (`r2db-api/src/r2db_api/service.py:882` / `control_plane.py:714`、`MitateDB-api/src/mitatedb_api/cell.py:1280` / `control_plane.py:1364`)。**peer の製品コードを 1 バイトも変えていない**こと。**監査照合**: 監査は `git diff -- r2db-api/src MitateDB-api/src` を確認し、**パッケージ内契約コピー 2 本以外に変更行が無い**ことを確認する。
19. **対応表に対応の無い行が無いこと** (メタ条件)。
20. **完了ゲート** — root suite 単独実行で **`failed` 0 / `skipped` 0 / `xfailed` 2** (全体 vacuity guard + 静的固定テスト)、`passed` が WP-0 の値から増えていること。**増分の内訳を完了報告に書く**こと — 共通 vector は 4 adapter でパラメータ化されるため、テスト関数 1 本が収集 4 件になる (declare-and-echo は 2 件)。**監査照合**: 監査は増分内訳と WP-0 / 本 WP の集計行の差を突き合わせ、`新規 − 減 = 純増 = 集計行の差` が成立すること、および `xfailed 2` の**テスト名 2 本**が guard と静的固定テストであることを確認する。

#### 非 vacuity 要件

- **本 WP で実観測を伴うのは port v1.10 (b) のフォールバック経路だけ**である — `test_c09_audit_evidence.py:868` の無条件 vector が新しい判定関数を経由して 4 plug で走り続ける。**この 1 点を「本 WP の唯一の実観測」として完了報告に明記する。**
- 新 vector 3 種は 1.6.0 declare-first であり、**本 WP の時点では全 adapter が分岐を素通りする**。**これを「緑だから通っている」と書かないこと** (常設規律 3)。素通りしている事実そのものを、全体 vacuity guard の `xfail` が代理で表現する。
- 静的固定テストは `xfail` として登録されるが、**「合成が実在するから赤である」ことを変異 4 / 5 で実測する** — 何も検出していないから赤なのではない。

#### 同型性テスト対象

**本 WP は peer-local のテストヘルパを増やさないため、同型性テストの対象は変わらない。** WP-0 の裁定結果 (対象 2 件の扱い) を引き継ぐのみである。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

**完了条件 → 変異の対応表 (常設規律 §0.1 の 2。対応の無い行を残さない)**

| 完了条件 | 対応する変異 (それだけを壊すもの) |
|---|---|
| 1 契約版数と 1.6.0 段落 | **変異 1** (遡及否認 4 行のうち 1 行から `1.6.0-only` を落とす → 文字列ピンが赤) |
| 2 項目 4 の置き場所と形 | **変異 2** (`upsert` 補筆の限定句を `enabled` へ変える → 文字列ピンが赤) |
| 3 確定文の逐語性 | **変異 3** (確定文 1 文の 1 語を spec と両 packaged copy に**同時**適用し byte 同一を保ったまま → 文字列ピンだけが赤) |
| 4 additive 性の機械確認 | **監査照合** (変異を作らない。完了条件 4 に照合対象を明記) |
| 5 `upsert` の義務個数 | **監査照合** (変異を作らない。完了条件 5 に照合対象を明記) |
| 6 packaged copy の byte 同一 | **変異 4** (r2db 側のコピーを 1 バイト改変 → r2db の byte 同一テストが赤) / **変異 4b** (MitateDB 側で同じ → MitateDB のテストが赤。2 本が独立であることの実測) |
| 7 従属判断 11 | **監査照合** (変異を作らない。完了条件 7 に照合対象を明記) |
| 8 新 vector 3 種と declare-first | **変異 5** (in-process adapter 1 本の宣言 `contract_version` を `1.6.0` へ上げる → 新 vector 3 種が当該 plug で 1.6.0 分岐へ入り、peer が未実装なので**赤**。分岐が実在することの実測。**否定側 6 語が 6 件として収集されていること・`json` の行が無いことを同時に確認する**。**必ず復元する**) |
| 9 vector 配置先の裁定 | **監査照合** (変異を作らない。完了条件 9 に照合対象を明記) |
| 10 port v1.10 (a) verbatim 規約 | **変異 6** (規約に反して adapter 1 本が `secret` へ前置を足す → 静的固定テストの合成不在 (a) が当該 adapter を検出。**xfail のままである**ことと、変異 7 の対照で load-bearing を示す) |
| 11 port v1.10 (b) 同居判定 | **変異 8** (フォールバック分岐を除去し `surfaces` 不在時に `True` を返す形へ → `test_c09_audit_evidence.py` の無条件 vector が 4 plug で赤) |
| 12 port v1.10 (c) catalog fixture | **監査照合** (変異を作らない。採った形の報告と port の実体を突合) |
| 13 4 adapter の port 実装 | **変異 9** (1 plug から新メソッドの実装を削る → `ABC` により当該 plug が生成できず収集エラー) |
| 14 `CONFORMANCE_ADAPTER_V1.md` §20 | **監査照合** (変異を作らない。§19 の構成と項目単位で突合) |
| 15 全体 vacuity guard | **変異 10** (4 adapter すべての宣言を `1.6.0` へ上げる → guard が XPASS となり `strict=True` により**赤**。全数要求と strict が効いていることの実測。**必ず復元する**) |
| 16 静的固定テスト | **変異 7** (合成 4 箇所を撤去 → XPASS で赤) + **変異 7′** (合成を撤去したうえで `credential_ref` を bearer の `split(".")` で得る形へ → **XPASS へ移らない** = 分解不在 (b) が load-bearing であることの実測) |
| 17 文字列ピン | **変異 3** (同上) |
| 18 peer の宣言が動いていない | **監査照合** (変異を作らない。完了条件 18 に照合対象を明記) |
| 19 対応表が全行埋まる | 本表そのもの (メタ条件。変異は作らない) |
| 20 完了ゲート | **監査照合** (変異を作らない。完了条件 20 に照合対象を明記) |

**変異 7 / 7′ の実施上の注意**: 合成を撤去すると MitateDB の HTTP plug は認証できなくなり、当該 plug の既存テストは軒並み赤になる。**静的固定テストはソース走査であって suite の緑を要さない**ので、**当該テスト 1 本を単独実行して観測する**。他が赤になることは想定内であり、その旨を報告に書く。**7′ は「XPASS へ移らないこと」を示す変異**である — (b) を実装していない形なら 7′ でも XPASS になり、strict により赤になるはずが緑 (xfail) のままになる。**2 つの対比が (b) の load-bearing の実測である。**

**復元後、変異文字列を全文 grep してゼロを確認する。** 変異 5 / 10 は adapter の宣言版数を触るので、**復元後に 4 plug すべての宣言が 1.5.0 であることを再確認する。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q conformance-tests/test_contract.py
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q r2db-api/tests/test_http.py MitateDB-api/tests/test_http.py
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **項目 4 が 1.6.0 段落へ漏れていないか** — D-3 (vii) は**`upsert` 節の同ラベル補筆**である。1.6.0 段落へ置けば、1.5.0 を宣言し続ける両 peer に対して契約が要求していない読みが立つ。
2. **`upsert` 前半の義務が落ちていないか** — 対象は 2 義務を運ぶ 1 文である。**前半 (unique key 不在時の upsert 拒否) が逐語で残っているか。** 再帰 diff では検出できない欠落であり、文字列ピンと目視突合だけが担う。
3. **限定句の語法** — `other than unavailable` か。`enabled` だけにして `partial` を落としていないか。`declaration_required` を出典として引いていないか。`mutation_classes.rule` 側に手が伸びていないか (射程外、L6-10)。
4. **契約に実装固有の構造が漏れていないか** — `<credential_id>.<secret>` という**内部構造**が契約本文に入っていないか (制約 2)。「locator」「credential_id を前置する」等の実現形が description に現れていないか。
5. **`surfaces` が必須になっていないか** — `CapabilityDocument.required` が変わっていないか。`control_plane: unavailable` の配備が `surfaces.control` を省略できる形になっているか。
6. **`field_types` が要求になっていないか** — `SchemaOperationRequest.required` に入っていないか。**`fields` だけを伴う `create_entity` が 1.6.0 実装でもそのまま有効**と読める形か (semantic change は minor では許されない)。
7. **不正 3 ケースの明記** — (a) `fields` に無い名前 / (b) 語彙外の値 / (c) `fields` を伴わない `field_types` の 3 つが**すべて** `VALIDATION_FAILED` として契約に書かれているか。「黙って無視してよい」と読める余地が残っていないか。
7b. **否定側 vector の語数** — `json` を除く **6 語**に課されているか。`json` に違反値を発明していないか (any JSON value に違反値は存在しない)、逆に 6 語のうち 1 語を落としていないか。
8. **義務の分類語** — 項目 1・2 を conditional と呼んでいないか。確定文 §5 (4) の taxonomy (unconditional + 前提の句) と従属判断 11 の分類段落が**一致**しているか。
9. **静的固定テストの片肺** — (a) 合成不在だけを見て (b) 分解不在を落としていないか。**(b) が無ければ、id を bearer から割り出す実装が緑のまま通る。**
10. **guard の弱化** — `strict=True` が落ちていないか、全数要求が「1 本でも通れば緑」へ緩んでいないか、`registered_adapters()` 走査が名前列挙へ退化していないか。
11. **WP-3 の前倒し** — adapter の合成 4 箇所、port の申告メソッド、4 plug の申告実装が**本 WP で削られていないか**。削れば `test_c09_audit_evidence.py:868` の無条件 vector が判定不能になる。
12. **peer への波及** — peer の製品コード・宣言・版数が 1 バイトでも動いていないか (パッケージ内契約コピー 2 本を除く)。
13. **秘密の混入** — 契約・従属判断・§20 の追記に実 DSN / パスワード / 実在ドメインが無いか。**`surfaces` の例示には `example.invalid` 等の架空ドメインのみを使う。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

#### 追補 (v1.2、2026-09-04 監督裁定、依頼者承認「この2つも進めてください」) — suite 高速化 2 件を WP-1 に同梱する

**背景 (実測)**: root suite 単独 8 分 17 秒のうち conformance が 6 分 13 秒、その 3 分の 2 が `test_c14_resource_bounds_published_and_enforced` (C-14 vector 5、4 plug で各 61〜64 秒。フェーズ5 台帳 L5-7)。監督実験 (2026-09-04、リポジトリ外の使い捨てプラグインで adapter 単位に `xdist_group` を付与し `-n 5 --dist loadgroup`): **conformance 422 passed in 117.17s (0:01:57)**、残骸 DB 0。ログ: scratchpad/xdist-experiment.log。

**A. C-14 vector 5 の作り替え (契約不変・製品不変・conformance のみ)**

- 位置算術を**構成値に比例しない形**へ作り替える — 上限そのものまで登録を積み上げるのではなく、**上限に対する相対位置だけを駆動する** (例: adapter の control plane を小さな `applications` 上限で再構築できる既存機構 `_build_control_stack` 系を port 経由で使う、または既に登録済みの件数から残り headroom を計算して必要最小の登録だけ行う)。**具体形は逐語プロトタイプの後に確定する** (常設規律 5): 実装者は先に 1 plug で試作し、所要秒数と検出力を報告してから 4 plug へ展開する。
- **検出力を落とさない**: LIMIT_EXCEEDED の `limit_class` と位置 (上限ちょうどで拒否、上限−1 で受理) の観測は従来どおり 4 plug 全数。
- 完了条件 A-1: 当該テストの 4 plug 合計 `call` 時間が **60 秒以下** (`--durations` で実測、従来 約 248 秒)。監査照合 = `--durations` 出力。
- 完了条件 A-2: 検出力の保持 — **変異 A** (片 peer の applications 上限検査を 1 つ緩める = 上限ちょうどでも受理する → 当該 plug で赤)。**変異 A′** (`limit_class` を別語にする → 赤)。従来テストで赤だった両変異が作り替え後も赤であること。
- 完了条件 A-3: 作り替えに伴い adapter 構成値 (`applications=115` 等) を**据え置く**か**下げる**かを報告に書く。下げる場合はフェーズ5 §6.4 の据え置き根拠 (他条件テストの登録件数) との整合を示す。フェーズ5 L5-7 が「変異 6/7 は未実測」と記録した点は、作り替えで実用時間になれば本 WP で実測して L5-7 を閉じる。

**B. conformance の adapter 単位並列化 (dev 依存の追加、conformance の conftest のみ)**

- `pytest-xdist` を dev 依存に追加する (root `pyproject.toml` の pytest 設定と、両 peer の dev extras のいずれが正しい置き場かは実測して報告。lock は無い方針のまま)。
- `conformance-tests/conftest.py` に `pytest_collection_modifyitems` で **adapter param id を `xdist_group` に写す**フックを置く (adapter param の無い registry-wide guard は 1 つの固定グループ)。**xdist が無い環境でもフックは無害** (マーカー付与のみ) であること。
- 完了ゲートのコマンドを **`./.venv/bin/python -m pytest -q -n 5 --dist loadgroup`** に改める (§6 を更新)。「単独実行」の規律は**他の pytest プロセスと並行しない**という意味で不変。
- 完了条件 B-1: 上記コマンドで root suite が `failed 0 / skipped 0` かつ xfailed 期待値どおりであること。**従来の逐次コマンドでも同じ集計行**であること (並列化が結果を変えないことの実測)。
- 完了条件 B-2: **各 adapter の全テストが同一 worker で走る**こと — `-v` 出力の worker id (`[gw0]` 等) を adapter 別に集計して 1 adapter = 1 worker であることを示す。監査照合 = その集計。
- 完了条件 B-3: 並列実行後に run-prefix 付きの DB / role の残骸が 0 であること (`pg_database` / `pg_roles` の照合)。
- ローカル PostgreSQL は `max_connections = 300` (2026-09-04 変更済み)。runbook / 引き継ぎに「並列ゲートには 300 以上が要る」旨を WP-4 で記録する。

**対応表 (追補分)**: A-1 監査照合 / A-2 変異 A・A′ / A-3 監査照合 / B-1 監査照合 (2 コマンドの集計行) / B-2 監査照合 / B-3 監査照合。

### WP-2 r2db-api — locator 形 credential + `surfaces` + `field_types` + 1.6.0 flip

#### 目的

r2db に 1.6.0 の 3 つの義務を出荷する — (i) issue / rotate が返す `secret` を**そのまま bearer として受理する** locator 形へ、(ii) `surfaces` を 2 文書に、(iii) catalog に `field_types` を。あわせて `contract_version` を 1.6.0 へ flip する。**flip と挙動出荷は同一コミット**である。

#### 変更対象

**A. locator 形 credential (設計 §3 D-1(c))**

| 対象 | 位置 | 変更 |
|---|---|---|
| in-memory application store | `r2db-api/src/r2db_api/auth.py:213` `authenticate(secret)`、`:219-226` の全 record 走査 | locator 分割 → credential_id で行参照 → `compare_digest` |
| Postgres application store | `r2db-api/src/r2db_api/credential_store.py:139` `_SELECT_BY_VERIFIER` | **使用をやめ**、既存の `:140` `_SELECT_BY_ID` を使う |
| control store の authenticate | 同 `:638` のインライン `SELECT … WHERE verifier = {ph}` | credential_id 参照の**名前付き定数**を新設する (`:656` の `assert_active` と同じ形に揃える) |
| control プロセスの application 認証 | `r2db-api/src/r2db_api/control_plane.py:515-525` `authenticate_application(secret)` | locator 経路へ。**secret 単独のまま残すと D-1 が片肺になる** |
| bearer 抽出 | `r2db-api/src/r2db_api/control_http.py:202` `_extract_bearer` | 完全な bearer をそのまま受け取る形へ |
| 発行点 (application) | `ops.py` / control 面の in-band 発行 | 応答の `secret` を**合成形**に。**`credential_id` は別フィールドのまま残す** |
| 発行点 (control) | bootstrap / reset / rotate | 同上 |

- **不正形 locator の fail-closed** — `.` を含まない / locator 部が空 / secret 部が空 のいずれも、**認証を実行せず `AUTH_INVALID`** で閉じる (MitateDB の `http.py:337-341` / `:354-360` と同型)。
- **実装拘束 3 点 (B-1 裁定の維持、設計 §3 D-1 の実装拘束)** — (1) locator で行を参照した後も **`compare_digest` を先に評価する** (`revoked` / `enabled` / application 無効の検査は digest 一致後にのみ。現行 `auth.py:219-232` の順序を崩さない)、(2) 応答は **`AUTH_INVALID` 一様**であり locator が既知か否かを漏らさない、(3) **クライアントが申告した locator を `actor_id` / `target_id` に記録しない**。
- **DDL migration は不要である。** `verifier` 列は digest 保管として残し、`UNIQUE` 制約も**衝突不能性の構造保証として残す**。**出荷済み migration (`0005_credential_store.sql` / `0006_control_plane_http.sql`) を in-place で編集しない** (L6-1 の裁定)。
- **L6-1 の訂正 2 箇所を本 WP で行う** — **(i)** `credential_store.py` の `PostgresCredentialStore.authenticate` 周辺の docstring (認証が locator 参照になったこと、`UNIQUE` は衝突不能性の構造保証として残ること)、**(iv)** 同 `:265-270` の逐語コメント「this `compare_digest` is deliberate defence-in-depth, **not the authoritative check**」 — **D-1 後はこの `compare_digest` が権威ある検査そのものになる**。実装拘束 1 が依存する当の性質をコメントが否定したまま残してはならない。
- **互換シムを置かない。** 旧形式 (secret 単独) の受理を残さない。

**B. `surfaces` (設計 §3 D-2)**

- capability document 2 箇所 — `r2db-api/src/r2db_api/service.py` の data 文書 (`contract_version` は `:882`)、`r2db-api/src/r2db_api/control_plane.py` の control 文書 (`:714`)。
- 環境変数 **`R2DB_DATA_BASE_URL` / `R2DB_CONTROL_BASE_URL`** を新設し、**data プロセス (`main.py`) と control プロセス (`control_main.py`) の両方に同じ 2 変数を配る** (どちらのプロセスも相手のホストへ接続しないので導出はできない)。
- **起動時に形を検査し、不正なら失敗する** — 絶対 URL であること / `data` は `/v1` で終わること / `control` は `/control/v1` で終わること / **末尾スラッシュを含まないこと**。`R2DB_CONTROL_PLANE_STATUS` (`main.py:165`、語彙検査 `:154`) と同型に置く。
- **`control_plane: unavailable` の配備では control 側変数を要求しない。**
- **検査できるのは形だけであり、両文書の一致は配備者の責任である** — 実装に相互検証を足さない (L6-5a)。

**C. `field_types` (設計 §3 D-3 の r2db 側)**

- **in-memory** (`r2db-api/src/r2db_api/structured.py`):
  - `:1130` `catalog()` に `field_types` を足す。値は `self.schema[name]` そのもの。**内部表現の `None` は `"json"` として返す**。`id` は `"integer"` (`:1406` が既にそう置いている)。
  - `:1405` の `{name: None for name in bound.fields}` を、**リクエストの `field_types` に名前があればその型、無ければ `None`** を置く形へ。
  - `:597` `bind_schema_operation` の `field_type is only supported by add_field.` を、**任意キー `field_types` を create_entity で受ける形**へ改める。**スカラ `field_type` の create_entity での拒否はそのまま残す** (スカラは per-field 対応を持たない)。
  - **不正 3 ケースを `VALIDATION_FAILED` で拒否する** (`fields` に無い名前 / 7 語外の値 / `fields` を伴わない `field_types`)。
  - **明示宣言された `json` は内部表現 `None` へ写す** — 文字列 `"json"` を格納すると `_check_type` (`:779-821`) が `:816-817` の `else: ok = True` へ落ち、**`:820` の NUL 検査が `("string","object","array")` に限定されているため、型無し field なら拒否している NUL 文字が「宣言した `json`」では通る**という逆転が起きる。
- **Postgres** (`r2db-api/src/r2db_api/postgres.py`):
  - `:778` `catalog()` に `field_types` を足す。値は `table_info.columns` (既に「宣言 field 名 → 宣言型」)。**`None` は `"json"` として返す。**
  - `create_entity` の DDL は、`field_types` に名前がある field には `_FIELD_TYPE_SQL` (`:159-166`) を per-field に適用し、無い field は**現行どおり JSONB** のまま。
  - **`_FIELD_TYPE_SQL` に `json` の経路を置く** — `"json": _JSONB_SQL` (`:168`)。無いと per-field DDL 適用時に `KeyError` になる。

**D. `contract_version` 1.6.0 flip**

- `r2db-api/src/r2db_api/service.py:882` と `r2db-api/src/r2db_api/control_plane.py:714` の 2 箇所。
- **版数を固定しているローカルテストの更新も同一コミット**に入れる。

**E. runbook (本 WP の分)**

- `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` と `r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` に、**既存 credential の再発行手順**と **`surfaces` 環境変数 2 本の設定手順**を置く。**grep で実表記を確認してから掃討対象を確定する** (決め打ちの 1 語で走らせない)。
- **`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md` の L6-1 (ii) 訂正は WP-4 である** — 本 WP は再発行手順と環境変数の追記のみ。

#### 完了条件 (検証可能な形)

1. **locator 形の発行 (全発行点)** — application / control の issue / rotate / bootstrap / reset が返す `secret` が**合成形**であり、**`credential_id` が別フィールドとして返り続けている**こと。**raw secret を返す発行点が 1 つも残っていない**こと。
2. **locator 形の受理 (全受理点)** — in-memory / Postgres の application store、control store、`control_plane.py:515-525` の `authenticate_application` のすべてが locator 参照であること。**`_SELECT_BY_VERIFIER` が認証経路から消えている**こと (`grep` で使用箇所 0)。**control 側に credential_id 参照の名前付き定数が存在する**こと。
3. **verbatim 受理の実測** — 発行が返した `secret` を**加工なしに** `Authorization: Bearer` へ載せて認証が通ること。**application credential は data surface、control credential は control surface** で、それぞれ実経路で観測されること。
4. **不正形 locator の fail-closed** — `.` 無し / locator 部空 / secret 部空 の 3 形が**認証を実行せず `AUTH_INVALID`** になること。**3 形すべてが個別ケースで観測される**こと。
5. **応答の一様性 (SI-10)** — 未知 locator / 既知 locator で digest 不一致 / 不正形 locator の**すべてが `AUTH_INVALID`** であり、locator が既知か否かを応答で区別できないこと。
6. **監査の帰属が変わっていないこと (SI-14、B-1 裁定の維持)** — digest 不一致の試行が **`actor_id=None`** で記録されること。**クライアントが申告した locator が `actor_id` / `target_id` に載らない**こと。
7. **判定順序の非後退** — `compare_digest` が `revoked` / `enabled` / application 無効の検査より**先**に評価されること。
8. **DDL 無変更** — **監査照合 (変異を作らない)**: 監査は `git diff -- r2db-api/migrations/` が**空**であること、`verifier` 列と `UNIQUE` 制約が残っていることを確認する。
9. **L6-1 (i)(iv) の訂正** — **監査照合 (変異を作らない)**: 監査は `credential_store.py` の該当 docstring と `:265-270` のコメントを読み、(i) 認証が locator 参照であること、(ii) `UNIQUE` が衝突不能性の構造保証として残ること、(iii) **`compare_digest` が権威ある検査であること**が書かれていることを確認する。**「not the authoritative check」の文言が残っていれば赤**である。
10. **互換シムの不在** — **監査照合 (変異を作らない)**: 監査は `git diff` を読み、旧形式 (secret 単独) の受理経路・二形式分岐・フォールバックが**1 箇所も無い**ことを確認する。
11. **`surfaces` の 2 文書** — data 文書と control 文書の双方が同じ `surfaces` を返し、`surfaces.data.base_url` が `/v1` で、`surfaces.control.base_url` が `/control/v1` で終わること。**実 HTTP 経路でも観測できる**こと。
12. **`surfaces` 環境変数の起動時検査** — 相対 URL / 誤った終端 / 末尾スラッシュ付き / 不在 (control_plane が `unavailable` 以外のとき) の各形が**起動時に失敗**すること。**4 形すべてが個別ケースで観測される**こと。
13. **`field_types` の総覧性** — in-memory / Postgres の双方で、catalog の全 entity について `fields` の**全要素**が `field_types` に現れ、値が **7 語 enum** に収まること。**型を宣言せずに作った field が `json` として返る**こと。
14. **宣言の round-trip** — `create_entity` の `field_types` / `add_field` の `field_type` で宣言した型が catalog にそのまま返ること。**両 backend で同じであること。**
15. **不正 3 ケース** — `fields` に無い名前 / 7 語外の値 / `fields` を伴わない `field_types` の 3 つが**すべて `VALIDATION_FAILED`** であること。**黙って無視されていない**こと。
16. **`json` の内部写像** — 明示宣言された `json` が内部表現 `None` へ写り、**NUL 文字が「宣言した `json`」でも型無し field と同じく拒否される**こと。`_FIELD_TYPE_SQL` に `json` の経路があり、per-field DDL 適用で `KeyError` にならないこと。
17. **1.5.0 リクエストの非破壊** — `fields` だけを伴う `create_entity` が**そのまま有効**であり、その field が `json` 型で作られること。
18. **flip** — 両 plane の `contract_version` が `"1.6.0"` であり、**同一コミット**に上記の挙動が入っていること。宣言が先行することも挙動が先行することもないこと。
19. **共通 suite の 1.6.0 分岐が r2db 2 adapter で初実行される** — 新 vector 3 種の 1.6.0 分岐が r2db の 2 plug で**実際に走る**こと。**全体 vacuity guard と静的固定テストは MitateDB が未 flip なので `xfail` のまま**であること。
20. **runbook** — 既存 credential の再発行手順と `surfaces` 環境変数 2 本が置かれていること。**監査照合**: 監査は掃討に使った grep 語と結果を更新済み文書の一覧と突き合わせ、**ヒットした全ファイルが更新済み一覧に含まれる**ことを確認する。
21. **対応表に対応の無い行が無いこと** (メタ条件)。
22. **完了ゲート** — root suite 単独実行で **`failed` 0 / `skipped` 0 / `xfailed` 2** (guard + 静的固定テスト。**WP-3 で両方 0 になる**)、`passed` が WP-1 の値から増えていること。**増減の内訳を完了報告に書く**こと。**監査照合**: 監査は増減内訳と WP-1 / 本 WP の集計行の差を突き合わせ、`新規 − 減 = 純増 = 集計行の差` が成立すること、および `xfailed 2` のテスト名が WP-1 で登録した 2 本と一致することを確認する。

#### 非 vacuity 要件

- **verbatim 受理 (条件 3) は、adapter の合成を経由しない実経路で観測すること** — r2db の adapter は元から合成していないので、**発行 → そのまま提示 → 認証成功**が 1 本のテスト内で繋がっていることを assert する。
- **新 vector 3 種は本 WP で r2db 2 plug が初めて 1.6.0 分岐へ入る。** 「収集件数は増えないが観測が増える」ため、**分岐へ入ったことを変異で実測する** (変異 12)。
- **`surfaces` の declare-and-echo は HTTP plug でのみ実測される。** in-process plug が合成の偽ドメインを申告することを完了報告に書く。

#### 同型性テスト対象

**WP-0 で確定した対応表 13 行を引き継ぐ。** 本 WP で両 peer 同名になるヘルパを新設した場合は、**対応表に行を足し、行数を pin するテストも同時に更新する**。**r2db 側のみを触る WP であるため、MitateDB 側の実装が揃うのは WP-3 である** — その場合は **WP-2 で r2db 側を先行実装し、当該行について `xfail(strict=True)` の placeholder を登録する** (フェーズ5 WP-2 と同じ運用)。**placeholder を登録した場合は `xfailed` の期待値が 3 になる** — その旨を完了報告に明記し、§5 の期待実測値表との差を監督へ上げること。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

**完了条件 → 変異の対応表 (常設規律 §0.1 の 2。対応の無い行を残さない)**

| 完了条件 | 対応する変異 (それだけを壊すもの) |
|---|---|
| 1 locator 形の発行 | **変異 1** (発行点 1 つを raw secret へ戻す → verbatim 受理テストが赤) |
| 2 locator 形の受理 | **変異 2** (`_SELECT_BY_VERIFIER` を認証経路へ戻す → locator 参照を固定するテストが赤) |
| 3 verbatim 受理の実測 | **変異 3** (control 側 `authenticate_application` だけを secret 単独へ戻す → control surface の verbatim vector が赤。**片肺を捕まえる**) |
| 4 不正形 locator の fail-closed | **変異 4** (`.` 無しのときに全 record 走査へフォールバックする形を足す → 3 形のうち 1 形が赤) |
| 5 応答の一様性 | **変異 5** (未知 locator のとき `AUTH_INVALID` 以外を返す → 一様性テストが赤) |
| 6 監査の帰属 | **変異 6** (digest 不一致時に申告 locator を `actor_id` へ入れる → 帰属テストが赤) |
| 7 判定順序 | **変異 7** (`revoked` 検査を `compare_digest` より前へ移す → 順序テストが赤) |
| 8 DDL 無変更 | **監査照合** (変異を作らない。完了条件 8 に照合対象を明記) |
| 9 L6-1 (i)(iv) の訂正 | **監査照合** (変異を作らない。完了条件 9 に照合対象を明記) |
| 10 互換シムの不在 | **監査照合** (変異を作らない。完了条件 10 に照合対象を明記) |
| 11 `surfaces` の 2 文書 | **変異 8** (control 文書から `surfaces` を落とす → 双方向一致 vector が赤) |
| 12 環境変数の起動時検査 | **変異 9** (末尾スラッシュの検査を落とす → 4 形のうち 1 形が赤) |
| 13 `field_types` の総覧性 | **変異 10** (catalog から 1 field 分の `field_types` エントリを落とす → 総覧性 vector が赤) |
| 14 宣言の round-trip | **変異 11** (`add_field` の宣言型を catalog で `json` へ丸める → round-trip vector が赤) |
| 15 不正 3 ケース | **変異 12** (`fields` に無い名前を黙って無視する形へ → 否定側テストが赤) |
| 16 `json` の内部写像 | **変異 13** (宣言 `json` を文字列 `"json"` のまま格納 → NUL 拒否テストが赤) |
| 17 1.5.0 リクエストの非破壊 | **変異 14** (`field_types` を必須にする → `fields` だけの `create_entity` が赤) |
| 18 flip | **変異 15** (片方の plane だけ `1.5.0` へ戻す → 両 plane の版数を固定するローカルテストが赤) |
| 19 1.6.0 分岐が r2db 2 adapter で初実行 | **変異 16** (r2db adapter 2 本が返す `surfaces` から `control` を落とす → 共通 1.6.0 条件付き vector が r2db 2 plug で赤。**peer の製品コードを触らないため peer-local テストは緑のまま**であり、これが「分岐が実際に走っている」ことの実測) |
| 20 runbook | **監査照合** (変異を作らない。完了条件 20 に照合対象を明記) |
| 21 対応表が全行埋まる | 本表そのもの (メタ条件。変異は作らない) |
| 22 完了ゲート | **監査照合** (変異を作らない。完了条件 22 に照合対象を明記) |

**復元後、変異文字列を全文 grep してゼロを確認する。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q r2db-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **片肺の locator 化** — 発行点・受理点のうち 1 つでも旧形式が残っていないか。とくに `control_plane.py:515-525` の `authenticate_application` と control store の**インライン SQL**は見落としやすい。
2. **帰属規律の破壊 (B-1 裁定)** — locator が token に入ったことで、**申告 id が監査に載る**形になっていないか。digest 不一致が `actor_id=None` のままか。過長 locator で応答コードが `AUTH_INVALID` から別コードへ反転しないか。
3. **判定順序** — `compare_digest` が state 検査より先か。locator 参照後に「行が見つかったから revoked を見る」順序へ滑っていないか。
4. **互換シム** — 二形式受理・フォールバック・「一時的に旧形式も通す」分岐が入っていないか (禁止事項)。
5. **DDL への逸脱** — migration が増えていないか、出荷済み migration が in-place で編集されていないか。
6. **`surfaces` の導出** — 実 URL を「リクエストが来たホスト」から導出していないか。**配備者の表明**であって導出ではない (契約文がそう書く)。
7. **相互検証の発明** — data プロセスが control 文書を取りに行く等、**設計が明示的に配備者責任とした部分に実装を足していないか** (L6-5a、常設規律 5)。
8. **`json` の写像漏れ** — 宣言 `json` が文字列のまま格納されて `_check_type` の無検査分岐へ落ちていないか。**宣言した方が緩くなる逆転**が起きていないか。
9. **`field_types` の必須化** — `SchemaOperationRequest` で必須になっていないか。1.5.0 で有効なリクエストが拒否されていないか。
10. **catalog の丸め** — `object` / `array` が `json` へ丸められていないか (契約文が「never rounding it up to `json`」と書く)。
11. **flip の束縛** — `contract_version` 1.6.0 と、それを真にする挙動が同一コミットか。偽の flip (宣言だけ先行) になっていないか。
12. **MitateDB への波及** — `MitateDB-api/` 配下が 1 バイトも動いていないか (本 WP の射程外)。
13. **秘密の混入** — runbook の再発行手順に実 credential / 実 DSN / 実ホスト名が無いか。**`surfaces` の例は架空ドメインのみ。**

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-3 MitateDB-api — 2 値発行 + `surfaces` + 宣言型 registry + catalog flip + 1.6.0 flip + 撤去 3 点

#### 目的

MitateDB に 1.6.0 の 3 つの義務を出荷し、`application_catalog` を `unavailable` → `enabled` へ flip し、`contract_version` を 1.6.0 へ flip し、**WP-1 で先置きした 2 つの `xfail` と port の申告メソッドを同一コミットで撤去する**。

**本 WP は撤去が 3 点同時に落ちる重いコミットである** — (i) 全体 vacuity guard の `xfail`、(ii) 静的固定テストの `xfail` と 4 adapter の合成撤去、(iii) port の申告メソッドと 4 plug の実装。**どれか 1 つだけ先に落とすと、その時点で赤になるか vacuous になるので、分割しない** (設計 §9 の申し送り 4)。

**WP-2 の裁定・レビュー指摘を発注時点で織り込むこと。** ただし「織り込んだから同じ指摘は出ない」とは限らない。対称実装の価値は指摘数の減少ではなく**両向きの照合**にある。

#### 変更対象

**A. あらゆる発行点の 2 値化 (設計 §3 D-1(d))**

| 経路 | 位置 | 変更 |
|---|---|---|
| in-band issue / rotate (application) | `MitateDB-api/src/mitatedb_api/control_plane.py:1543` / `:1600` / `:1610` | 応答の `secret` を合成形に |
| 帯域外 store API | `credential_store_postgres` / `auth.CredentialStore` の `issue`、`ControlCredentialStore` の対応メソッド | **`(credential_id, bearer)` の 2 値を返す** — `bearer` は `Authorization` にそのまま載る値、`credential_id` は**別フィールド**。合成の場所が呼び出し側から store 側へ移るだけで、返る値の個数は変わらない |
| ops CLI | `MitateDB-api/src/mitatedb_api/ops.py:266-275` `_print_secret_once` | **`credential_id:` 行は残し、`secret:` 行を合成済み bearer の 1 行に置き換える** (2 行のまま) |

- **`credential_id` を消してはならない** — `conformance-tests/adapter.py:64-68` の `CredentialHandle.credential_ref` は必須であり、revoke (`conformance_adapter_mitatedb_http.py:841-842`) と **rotate URL の組み立て** (`:1166`) が使う。**adapter は `credential_ref` に `credential_id` を、bearer に `secret` をそのまま持ち、合成も分解もしない。**
- **`_split_bearer` (`http.py:354`) と store 側の行参照は現状維持**である (MitateDB は既に受理側を満たしている)。
- **混在期間を作らない** — bootstrap / reset / issue / rotate の**すべてを本 WP の同一コミットで**合成形にする。`_repair_control_actor` (`conformance_adapter_mitatedb_http.py:1155-1171`) が bare と合成を同じ handle 型に混ぜ、`_control_send` (`:943-945`) が二重前置 (`id.id.secret`) を作る形を残さない。
- `MitateDB-api/conformance/conformance_adapter_mitatedb.py` (in-process plug) には**合成が 1 件も無い** — store / service を `(credential_id, secret)` の対で直接呼ぶためである。**この plug の 2 値受け取り方を新しい戻り値契約へ追随させる。**

**B. `surfaces` (設計 §3 D-2 の MitateDB 側)**

- capability document 2 箇所 — `MitateDB-api/src/mitatedb_api/cell.py` の data 文書 (`contract_version` は `:1280`、`control_plane` 行は `:1337`)、`MitateDB-api/src/mitatedb_api/control_plane.py` の control 文書 (`:1364`)。
- 環境変数 **`MITATEDB_DATA_BASE_URL` / `MITATEDB_CONTROL_BASE_URL`**。**両プロセス (`main.py` / `control_main.py`) に同じ 2 変数を配る。**
- **起動時に形を検査する** — 絶対 URL / `data` は `/v1` 終端 / `control` は `/control/v1` 終端 / **末尾スラッシュ無し**。`MITATEDB_CONTROL_PLANE_STATUS` (`config.py:93-99`) と同型に置く。
- **`control_plane: unavailable` の配備では control 側変数を要求しない。**

**C. 宣言型 registry (設計 §1.5 の 2a、§3 D-3)**

- **application データベースの `public` に置く。** `create_entity` / `add_field` が契約語彙の値 (7 語) をそのまま書き込む。**型を宣言せずに作られた field には `json` を書き込む。**
- **Postgres**: **per-application 系列**である。**新規 provisioning は `0003_provision_application.sql` の改訂**、**既存 application データベース (Mitate Phase B の検証 DB を含む) は per-application の upgrade script `0006`** で当てる。**platform 単発の `0006` にしてはならない** — 既存 application DB に何も作らず、起動時ではなく最初の catalog / 読み出しリクエストで落ちる。**番号は 2 系統が同一の番号列を共有しており、現存 `0001`〜`0005` の次の空き番号が `0006` である** (裁定 R3、L6-2)。
- **既存列の backfill 規則** (upgrade script が物理型から registry へ写す):

  | 物理型 (MitateDB 内部語彙) | 登録する契約型 |
  |---|---|
  | `text` | **`string`** |
  | `integer` | `integer` |
  | `real` | `number` |
  | `boolean` | `boolean` |
  | `json` | `json` |

  **`object` と `array` は物理的に区別できない**ので既存列は **`json`** として登録する。**型無しで作られた既存 field は `text` 物理型なので `string` と報告される** — それが現物の型である。**`json` を既定とするのは 1.6.0 以後に型無しで作られた field だけ**である。
- **sqlite backend** には provisioning という概念が無いので**遅延生成**になる。**両 backend で宣言型の読み書き API を揃えることが本 WP の要件**である。

**D. catalog の flip と実装 (設計 §3 D-3 の MitateDB 側)**

- `cell.py:1285` の `"application_catalog": {"status": "unavailable"}` を **`"enabled"`** へ flip し、`http.py:718-723` の `get_catalog` を実装する。**宣言と実挙動は同一コミット**である。
- **返す `EntityDescriptor` は `entity` / `fields` / `field_types` の 3 キーのみ**であり、**`mutation_class` / `address_fields` / `address_reuse` / `unique_keys` は省略する** (契約 `mutation_classes.rule` が mutation_class の宣言を `row_addressability` が enabled のときに限っており、MitateDB は `unavailable` である)。
- `http.py:778` の `create_entity cannot honor a request-level field_type` の refuse を、**任意キー `field_types` を受ける形**へ改める (**スカラ `field_type` の refuse 自体は残す**)。**不正 3 ケースは `VALIDATION_FAILED`** である。
- `http.py:810` の `{name: "text" for name in fields_raw}` を、**`field_types` に名前があればその型、無ければ `json`** を置く形へ改める (**挙動変更 (α)**: 既定 `text` → `json`、受理域の拡大)。
- `http.py:484-491` の `_CONTRACT_FIELD_TYPE_TO_MITATEDB` に **7 語目 `"json": "json"`** を足す。

**E. cell 層の宣言型検証 (設計 §3 D-3、G3。L6-9)**

- **`_prepare_values` 系の既存 choke point** (`cell.py:1074` / `:1120-1123` が `encode_value` を呼ぶ地点) で、**registry の宣言型に対する値検証を backend 非依存に行う** — `boolean` は JSON boolean のみ / `integer` は整数のみ (bool を除く) / `number` は数値 / `string` は文字列 / `object` は dict / `array` は list / `json` は任意 JSON 値。**不一致は `VALIDATION_FAILED`。**
- **これは r2db が `structured.py:779-821` の `_check_type` で既に持っている形と同型**である (peer 間で同じ安全成果を同じ形で満たす)。
- **backend のドメイン検査はその下の defence-in-depth として残す。** **2 層の語彙対応 (契約 7 語 ↔ 内部ドメイン `text` / `int32` / `int64` / `float`) を 1 箇所の表に固定し、変異注入で両層の load-bearing を確かめる** (L6-9)。

**F. json / boolean の round-trip (設計 §3 D-3、F2 / F3)**

- **受理側**: **`field_domains` の情報源を宣言型 registry に切り替える** — `information_schema` からの逆引き (`backend_postgres.py:355-380` の `:368-371` / `:380`) は**廃止**する。registry は `string` / `json` / `object` / `array` を**別々のドメイン**として返し、`_check_domain` (`:247-250`) は **`object` → dict のみ / `array` → list のみ / `json` → 任意 JSON 値 / `string` → str のみ**で分岐する。**3 語を 1 ドメインに畳んではならない。**
- **読み出し側**: 現状**逆直列化が存在しない** (`json.loads` は `http.py:48` の 1 件のみ)。**`json` / `object` / `array` を宣言した field の読み出しで、正準 JSON テキストを JSON 値へ復元して返す。`string` を宣言した field は文字列のまま返す** (**挙動変更 (β)**)。
- **宣言 `boolean` の wire を JSON boolean に揃える** (**挙動変更 (γ)**) — **書き込みで受理するのは JSON boolean のみ (`0` / `1` / `7` などの int は `VALIDATION_FAILED` で拒否)、読み出しは `true` / `false` を返す。両 backend で揃える。**
- **`backend_postgres.py:122-129` のコメント訂正 (L6-1 (v)) を同一コミットで行う** — 逐語で「nothing downstream needs to recover **which of the two** a column was originally declared as」と書く箇所が、D-3 後は偽になる。

**G. flip と撤去 3 点 (同一コミット)**

- `MitateDB-api/src/mitatedb_api/cell.py:1280` と `control_plane.py:1364` の `contract_version` を **`"1.6.0"`** へ。**版数を固定しているローカルテストの更新も同一コミット。**
- **(i) 全体 vacuity guard の `@pytest.mark.xfail(strict=True)` デコレータを削除する。**
- **(ii) 静的固定テストの `xfail` を削除し、同時に 4 adapter の合成を撤去する** — `conformance_adapter_mitatedb_http.py:838` / `:988` / `:943-945` / `:1272-1274`、および規約コメント `:447` / `:934-946` / `:986`。**`_Session.bearer` フィールド自体は撤去しない。** `conformance-tests/test_c15_bootstrap_reset_lifecycle.py:347` が rotate 応答の `secret` から `ControlCredentialHandle` を組み直している箇所は、**本 WP 後はそのまま「verbatim に使う」形になる**。
- **(iii) port の申告メソッド `control_surface_cohosted_with_data_plane()` (`conformance-tests/adapter.py:1214`) と 4 plug の実装を削除し、port 側のフォールバック分岐も消す。** **台帳 L5-4 はここで閉じる。**
- **`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` :22 の「実需要が出てから別フェーズで判断」に日付付きの否定注記を置く** (原文は当時の記述として残す)。

**実測事項 (本 WP で確定し、完了報告に書く)**

(i) **Mitate Phase B の実 DB** に宣言型 registry の行を持たない既存 field があるか・あればどう報告し読み出すか、(ii) 両 backend の `json` 受理範囲の一致、(iii) 両 backend の読み出し表現の一致、(iv) `boolean` の round-trip の一致。

#### 完了条件 (検証可能な形)

1. **全発行点の 2 値化** — in-band 3 経路 / 帯域外 store API / ops CLI の**すべて**が `(credential_id, bearer)` を返し、`bearer` が合成済みであること。**raw secret を返す発行点が 1 つも残っていない**こと。**ops CLI が 2 行 (`credential_id:` と合成済み `secret:`) のままである**こと。
2. **verbatim 受理の実測** — 発行が返した `secret` を**加工なしに** bearer として提示して認証が通ること。**application credential は data surface、control credential は control surface** で観測されること。
3. **混在期間の不在** — **監査照合 (変異を作らない)**: 監査は `git diff` を読み、bootstrap / reset / issue / rotate の 4 経路が**同一差分に含まれている**こと、`_repair_control_actor` が bare と合成を混ぜる形になっていないこと、`_control_send` に二重前置が生じ得ないことを確認する。
4. **`surfaces` の 2 文書** — data 文書と control 文書の双方が同じ `surfaces` を返し、終端が `/v1` / `/control/v1` であること。**実 HTTP 経路でも観測できる**こと。
5. **`surfaces` 環境変数の起動時検査** — 相対 URL / 誤った終端 / 末尾スラッシュ付き / 不在 の各形が**起動時に失敗**すること (4 形が個別ケース)。
6. **宣言型 registry (両 backend)** — Postgres / sqlite の双方に宣言型の保管があり、**読み書き API が揃っている**こと。`create_entity` / `add_field` が 7 語をそのまま書き込み、型無しには `json` を書き込むこと。
7. **migration `0006` が per-application 系列であること** — 新規 provisioning が `0003_provision_application.sql` の改訂で registry を作り、**既存 application データベースには upgrade script `0006` が当たる**こと。**platform 単発になっていない**こと。**番号が `0006` である**こと。
8. **backfill 規則** — upgrade script が既存列を §変更対象 C の表どおりに写すこと。**`object` / `array` は物理的に区別できないため既存列は `json`**、**型無し既存列は `string`** として登録されること。**registry に行が無い既存 field が構造的に生じない**こと。
9. **catalog の flip と実装** — `application_catalog` が `enabled` であり、`GET /v1/catalog` が実際に応答すること。**宣言と実挙動が同一コミット**であること。
10. **`EntityDescriptor` の 3 キー** — 返る記述子が `entity` / `fields` / `field_types` の**3 キーのみ**であり、`mutation_class` / `address_fields` / `address_reuse` / `unique_keys` を**省略している**こと。
11. **`field_types` の総覧性と 7 語** — catalog の全 entity について `fields` の全要素が `field_types` に現れ、値が 7 語 enum に収まること。**型無し field が `json` として返る**こと。
12. **不正 3 ケース** — `fields` に無い名前 / 7 語外の値 / `fields` を伴わない `field_types` の 3 つが**すべて `VALIDATION_FAILED`** であること。**スカラ `field_type` の create_entity での refuse が残っている**こと。
13. **cell 層の宣言型検証** — `_prepare_values` 系の choke point で 7 語の判定が**backend 非依存に**行われ、不一致が `VALIDATION_FAILED` であること (**`json` は any JSON value なので不一致が生じない — 判定表には 7 語すべてが載るが、拒否が起きるのは 6 語である**)。**sqlite backed の in-process plug でも効いている**こと (現状は `field_domains` が全列 `None` で検査が一切働かない)。
14. **2 層の語彙対応表** — 契約 7 語と内部ドメインの対応が**1 箇所の表**に固定されていること (L6-9)。**backend のドメイン検査が defence-in-depth として残っている**こと。
15. **`json` の受理と読み出し** — `json` / `object` / `array` を宣言した field で、**書いた JSON 値と読み戻した JSON 値が等しい** (round-trip) こと。**`string` を宣言した field は文字列のまま返る**こと。**両 backend で一致する**こと。
16. **`boolean` の round-trip** — 書いた `true` が `true` で読み戻ること。**`0` / `1` / `7` などの int が `VALIDATION_FAILED` で拒否される**こと。**両 backend で一致する**こと。
17. **L6-1 (v) の訂正** — **監査照合 (変異を作らない)**: 監査は `backend_postgres.py:122-129` を読み、「どちらとして宣言されたかを復元する必要がない」旨の記述が**訂正されている**ことを確認する。`field_domains` の情報源が registry であることが書かれていること。
18. **flip** — 両 plane の `contract_version` が `"1.6.0"` であり、**同一コミット**に上記の挙動が入っていること。
19. **撤去 3 点が同一コミット** — (i) 全体 vacuity guard の `xfail` 削除、(ii) 静的固定テストの `xfail` 削除 + 4 adapter の合成撤去、(iii) port の申告メソッド + 4 plug の実装 + フォールバック分岐の削除。**3 点が同じ差分に入っている**こと。**guard と静的固定テストの本体は変わっていない**こと (flip 自身が無介助で緑にすることを示すため)。**監査照合**: 監査は `git diff` を読み、guard / 静的固定テストの**デコレータ行だけ**が消えていることを確認する。
20. **申告メソッドの消滅** — `grep -rn "control_surface_cohosted_with_data_plane"` が **0 行**であること。`test_c09_audit_evidence.py:868` の無条件 vector が **`surfaces` 由来の判定で 4 plug 全数緑**であること。
21. **合成・分解の不在** — 静的固定テストが**素で緑**であり、`grep` で 4 adapter に合成式が 0 件であること。**`_Session.bearer` フィールドが残っている**こと。
22. **既存 C-11 / C-12 が vacuous でなくなること** — `application_catalog` の flip により、宣言と実挙動の agreement 検査が MitateDB で load-bearing になること。**新 vector を足すのではなく、既存 vector が load-bearing になったことを実測する。**
23. **`MITATEDB_PHASE3` :22 の否定注記** — **監査照合 (変異を作らない)**: 監査は当該箇所を読み、**原文が残り**、**日付付きの否定注記**が添えられていることを確認する (原文の書き換えではない)。
24. **実測事項 4 件の報告** — (i)〜(iv) が完了報告に書かれていること。**設計の想定と食い違ったら実測が正**であり、食い違いを隠さず書くこと。
25. **対応表に対応の無い行が無いこと** (メタ条件)。
26. **完了ゲート** — root suite 単独実行で **`failed` 0 / `skipped` 0 / `xfailed` 0**、`passed` が WP-2 の値から変化していること。**増減の内訳を完了報告に書く**こと — port の申告メソッド削除で**収集件数が減りうる**ため、単純な純増にならない可能性がある。**監査照合**: 監査は増減内訳と WP-2 / 本 WP の集計行の差を突き合わせ、`新規 − 減 = 純増 = 集計行の差` が成立すること、および **`xfailed` が 2 → 0 へ移った 2 本のテスト名**が WP-1 で登録した guard と静的固定テストであることを確認する。**WP-2 で同型性 placeholder を登録した場合は 3 → 0 である** — その場合は 3 本すべてのテスト名を照合する。

#### 非 vacuity 要件

- **本 WP は「4 plug 全数で load-bearing になる」ことが完了条件の核心**である。新 vector 3 種が 4 plug 全数で 1.6.0 分岐へ入ること、宣言型検証が **sqlite backed の in-process plug でも効いていること**を、それぞれ変異で実測する。
- **否定側 (宣言型に合わない値の拒否) を欠いた肯定側だけでは、強制の無い宣言型が緑のまま出荷される** — sqlite backed の in-process plug がまさにその状態である。**否定側は `json` を除く 6 語**であり (`json` には違反値が存在しない)、**その変異を in-process plug で必ず実施する。**
- **撤去 3 点は「消したから緑」ではなく「flip が無介助で緑にした」ことを示す** — guard と静的固定テストの本体を変えていないことを差分で示す。

#### 同型性テスト対象

- **WP-2 で r2db 側を先行実装した同名ヘルパがあれば、本 WP で MitateDB 側を実装し、placeholder の `xfail` を同一コミットで外す。**
- **WP-0 で確定した対応表 13 行**を引き継ぐ (既存 11 + `main.py::_optional_float` + byte 同一テスト関数)。
- **本 WP で新設する peer-local ヘルパのうち、両 peer に同名で置かれるものは対応表に行として加える。** **行を足したら行数を pin するテストも同時に更新し、最終的な対応表の行数と内容を完了報告に書く**こと。

#### 変異注入 (必須。scratchpad へ復元。`git checkout` 不使用)

**完了条件 → 変異の対応表 (常設規律 §0.1 の 2。対応の無い行を残さない)**

| 完了条件 | 対応する変異 (それだけを壊すもの) |
|---|---|
| 1 全発行点の 2 値化 | **変異 1** (帯域外 store API 1 本を raw の対へ戻す → verbatim 受理テストが赤) |
| 2 verbatim 受理の実測 | **変異 2** (ops CLI の `secret:` 行を bare secret へ戻す → bootstrap 経由の verbatim vector が赤) |
| 3 混在期間の不在 | **監査照合** (変異を作らない。完了条件 3 に照合対象を明記) |
| 4 `surfaces` の 2 文書 | **変異 3** (control 文書の `surfaces.data` を別 URL へ → 双方向一致 vector が赤) |
| 5 環境変数の起動時検査 | **変異 4** (末尾スラッシュの検査を落とす → 4 形のうち 1 形が赤) |
| 6 宣言型 registry (両 backend) | **変異 5** (sqlite 側の registry 書き込みを落とす → in-process plug の catalog / round-trip が赤。**Postgres 側は緑のまま** = 両 backend 分が独立に固定されていることの実測) |
| 7 migration `0006` の系列 | **変異 6** (upgrade script を既存 DB に当てない経路を作る → 既存 DB を模した fixture で catalog が赤) |
| 8 backfill 規則 | **変異 7** (backfill で `text` を `json` として登録する → 既存列の型報告テストが赤) |
| 9 catalog の flip と実装 | **変異 8** (`application_catalog` を `unavailable` へ戻す → 既存 C-11 / C-12 の agreement 検査と共通 catalog vector が赤) |
| 10 `EntityDescriptor` の 3 キー | **変異 9** (`mutation_class` を記述子へ足す → 契約適合 (C-11) が赤) |
| 11 `field_types` の総覧性と 7 語 | **変異 10** (1 field 分の `field_types` エントリを落とす → 総覧性 vector が赤) |
| 12 不正 3 ケース | **変異 11** (7 語外の値を黙って通す → 否定側テストが赤) |
| 13 cell 層の宣言型検証 | **変異 12** (choke point の検証を外し backend のドメイン検査だけに戻す → **in-process (sqlite) plug の否定側 vector が赤**。Postgres 側が緑のままなら「backend 依存に戻った」ことの実測) |
| 14 2 層の語彙対応表 | **変異 13** (対応表から 1 語を落とす → 対応表を pin するテストが赤) |
| 15 `json` の受理と読み出し | **変異 14** (読み出しの逆直列化を外す → 値 round-trip vector が赤。**「書けること」だけでは緑になる**ことの実測) |
| 16 `boolean` の round-trip | **変異 15** (宣言 `boolean` の書き込みで `7` を通す → 否定側と round-trip が赤) |
| 17 L6-1 (v) の訂正 | **監査照合** (変異を作らない。完了条件 17 に照合対象を明記) |
| 18 flip | **変異 16** (片方の plane だけ `1.5.0` へ戻す → 両 plane の版数を固定するローカルテストと全体 vacuity guard が赤) |
| 19 撤去 3 点が同一コミット | **監査照合** (変異を作らない。完了条件 19 に照合対象を明記) |
| 20 申告メソッドの消滅 | **変異 17** (`surfaces` 由来の判定を `True` を返す形へ → `test_c09_audit_evidence.py` の無条件 vector が 4 plug で赤。**判定が実際に使われている**ことの実測) |
| 21 合成・分解の不在 | **変異 18** (adapter 1 本に合成を戻す → 静的固定テストが赤) + **変異 18′** (合成ではなく `secret` の `split(".")` を 1 箇所足す → **分解不在 (b) が赤**) |
| 22 C-11 / C-12 の非 vacuity | **変異 8** (同上。flip を戻せば agreement 検査が vacuous に戻ることの実測) |
| 23 `MITATEDB_PHASE3` の否定注記 | **監査照合** (変異を作らない。完了条件 23 に照合対象を明記) |
| 24 実測事項 4 件の報告 | **監査照合** (変異を作らない。報告内容と実 DB / 両 backend の観測を突合) |
| 25 対応表が全行埋まる | 本表そのもの (メタ条件。変異は作らない) |
| 26 完了ゲート | **監査照合** (変異を作らない。完了条件 26 に照合対象を明記) |

**復元後、変異文字列を全文 grep してゼロを確認する。** **変異 6 / 7 は migration / upgrade script を触るので、復元後に実 DB fixture の再構築結果も報告に書くこと。**

#### テストコマンド

```
./.venv/bin/python -m pytest -q MitateDB-api/tests
./.venv/bin/python -m pytest -q conformance-tests
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行
```

#### レビューが必ず探すべき点 (Opus、テンプレ 5)

1. **発行点の取りこぼし** — in-band / 帯域外 / CLI のいずれかが raw を返し続けていないか。**混在は `_control_send` の二重前置 (`id.id.secret`) を実際に生む。**
2. **`credential_id` の消滅** — 発行の戻り値が「合成済み bearer 1 個」になっていないか。**adapter が id を bearer から split せざるを得ない形は、確定文 §5 (1) の `split it into` 禁止に正面から反する。**
3. **registry の 3 面** — catalog / 読み出し / 受理の**すべて**が registry を引いているか。受理面だけ `information_schema` の逆引きが残っていないか。**`string` / `json` / `object` / `array` が別ドメインか** (畳むと「`object` を宣言した field が配列も裸の値も受理する」)。
4. **migration の系列** — `0006` が **per-application** の upgrade script か。platform 単発になっていないか。**既存 application DB に registry が作られるか。**
5. **backfill の逸脱** — 型無し既存列を `json` として登録していないか (**`string` が正**)。`object` / `array` を復元しようとする推測ロジックが入っていないか。
6. **強制の無い宣言型** — sqlite backed の経路で検証が効いているか。**`field_domains` が全列 `None` を返す形に依存したままになっていないか。**
7. **round-trip の片肺** — 「書けること」だけを見て**読み戻しを見ていない**形になっていないか。`boolean` が `0` / `1` のまま返っていないか。
8. **defence-in-depth の消滅** — backend のドメイン検査が「不要になったから」削られていないか (残すのが設計)。
9. **撤去 3 点の分割** — どれか 1 つだけ先に落ちていないか。**guard / 静的固定テストの本体が変えられていないか** (デコレータ行だけが消えるのが正)。
10. **flip の束縛** — `contract_version` 1.6.0 と `application_catalog: enabled` が、それを真にする挙動と同一コミットか。
11. **r2db への波及** — `r2db-api/` 配下が 1 バイトも動いていないか (adapter の port 対応を除く)。
12. **挙動変更 3 件の記録** — (α)(β)(γ) が完了報告とコミットメッセージに書かれているか。**既存クライアントに影響しうる変更を黙って出していないか。**
13. **秘密の混入** — migration / upgrade script / runbook に実 DSN / 実スキーマ名 / 実ホスト名が無いか。

#### 使用テンプレート

実装 = Sonnet (テンプレ 2)。コードレビュー = Opus (テンプレ 5、変異注入必須)。受け入れ監査 = Opus (テンプレ 6)。

---

### WP-4 記録整理

#### 目的

WP-0〜3 の実測を正本へ落とし、台帳と限界開示を現在形にし、**引き継ぎ第13次**を起こす。**本 WP は製品コード・テストを変更しない。**

#### 変更対象

**1. `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md` §10 (実施記録)**

- §10.1 の集計行表 (WP-0〜4 の実装コミット / merge コミット / root suite 単独実行値) と §10.2〜§10.6 を、**各 WP のコミット・集計行・実際に採った形・レビュー指摘の内訳・変異注入の結果・受け入れ境界**で埋める。**`{WP-N 後に確定}` のプレースホルダを 1 つも残さない。**
- **§11 の台帳を現在形にする** — L5-4 の閉止、**L5-5 / L5-6 の閉止 (WP-0 が同型性テストの機構を対応表駆動へ一般化し、ソース取得方式を `ast.get_source_segment` へ統一した)**、L6-1 の (i)(ii)(iv)(v) の処置先、L6-2 の確定 (MitateDB 0006 / Q4 は 0007)、L6-5 / L6-5a / L6-9 の実測後の記述。**新たに見えた項目は L6-11 以降として起票する。**

**2. `conformance-tests/CONDITIONS.md`**

- **新条件 (設計 §6.3 は C-19「クライアント自足性」を推奨する。登録先は監督裁定)** — 「共通仕様と 1 つの base URL と 1 つの credential だけを持つクライアントが、実装知識なしに、両 surface へ到達し、認証し、entity の型を発見できる」。**書く限界 3 点**: (a) declare-and-echo は **HTTP plug 2 件でのみ**実測し in-process plug は合成の偽ドメインを申告する、(b) **`surfaces` の 2 プロセス間ドリフトは実装が検出できない** (検出は配備後チェックと declare-and-echo だけ)、(c) 型付き catalog の round-trip は**共通 suite が書いた値についてのみ**であり既存データの表現は射程外。
- **C-09 行** — L5-4 の開示 (申告を独立に検証する機構が無い) を「port v1.10 で申告を宣言由来へ置換し、WP-3 で申告メソッドを削除した」という**閉止の記録**へ書き換える。**限界 (a) (P4-D18 による vector 4 の射程開示) はそのまま保つ。**
- **C-11 / C-12 行** — MitateDB の `application_catalog` が `unavailable` → `enabled` へ変わり、当該 capability の agreement 検査が **vacuous でなくなった**事実を記録する。
- **C-17 行** — MitateDB が catalog を返すようになるが `row_addressability: unavailable` のまま `mutation_class` を宣言しないこと、および **D-3 (vii) の `upsert` 補筆でその形が契約上一意になった**ことを記録する。
- `./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py` のマーカー/行対応が**双方向で緑**であること。

**3. `security/CONTROL_MAPPING.md`**

- 更新対象は **SI-06 / SI-07 / SI-08 / SI-10 / SI-13 / SI-14 / SI-15** の各行。**両 peer の cell を対で書き換える** (フェーズ5 WP-4 が SI-08 行で採った形と同じ)。
- **SI-06 / SI-07 行の r2db 側は L6-1 (ii) の訂正先でもある** — `verifier` の `UNIQUE` の役割 (索引ではなく衝突不能性の構造保証) を訂正する。
- **SI-08 行**は D-4(a) の fail-fast を記録する。
- **evidence テスト名はすべて `grep` で 1 件以上に解決すること。**

**4. 日付付き注記 3 件**

- **`docs/design/MITATEDB_PHASE3_HTTP_PERSISTENCE_V1.md` :22** — WP-3 が置いた否定注記の**確認**である (本 WP で二重に書かない)。
- **`docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4** (`:1072` 付近) — **migration 番号の予約が本フェーズの出荷でずれた事実**を日付付きで注記する (MitateDB は 0006 をフェーズ6 が取り、Q4 は 0007)。
- **`docs/work-orders/HANDOVER_20260904_FABLE.md` §4-2** (`:120` 付近) — 同上。**原文は残し、注記を添える。**

**5. runbook / 配備文書**

- **`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md`** — **L6-1 (ii)**: `verifier` の `UNIQUE` の役割の訂正。
- **両 peer の runbook / 配備文書の宣言例** — `contract_version` 1.6.0、`surfaces` の 2 キー、`field_types` を含む形へ。**MitateDB は upgrade script `0006` を既存 application データベースへ当てる手順**を置く (L6-8 の残る実測事項はこの運用手順が担保する)。
- **`docs/work-orders/DEPLOY_PHASE4_20260903.md` §4-1** — **配備後チェック**に、(i) `capabilities.contract_version == "1.6.0"`、(ii) **data 文書と control 文書の `surfaces` が一致すること** (2 プロセス間ドリフトの検出は実装ではなくこのチェックが担う、L6-5a)、(iii) `surfaces.<x>.base_url` + `/capabilities` が同じ `surfaces` を返すこと、(iv) MitateDB は `application_catalog` が `enabled` で `field_types` を返すことを加える。
- **grep 語は実表記に合わせること** — 文書によって言語も語彙も違う。**まず grep で実表記を確認**してから掃討対象を確定する。決め打ちの 1 語で走らせない。

**6. `spec/CCR_DISPOSITION.md` 従属判断 11**

- **「実施記録」を追記する** — 各項目がどのコミットで出荷され、どの実測がその additive 主張を支えたか。

**7. 引き継ぎ第13次**

- `docs/work-orders/HANDOVER_20260904_FABLE.md` (第12次) の後継として**第13次**を起こす。既存の体裁に従い、**最終集計行・各 WP のコミット・依頼者の次の判断事項**を明記する。
- **依頼者の次の判断事項として少なくとも挙げるもの**: Q4 (2 プロセス整合)、フェーズ7 (外部評価の指摘 1 / 指摘 7)、実機適用 (§4-1)、1.4.0 alias の除去、1.6.0 のクライアント通知可否 (**送らない方針は 1.4.0 の決定であり、1.6.0 について改めて判断事項として残す**)。
- **本フェーズが増やした運用前提**を書く — `surfaces` は配備者の表明であること、既存 credential の再発行が要ること、MitateDB の挙動変更 3 件。

**8. 本書 §11 (実施記録)**

- 各 WP の完了日・コミット (merge)・root suite の集計行 (単独実行の実測値)・分割の有無を記録する。

#### 完了条件 (検証可能な形)

**本 WP は記録整理であり、製品コード・テストを変更しない。したがって変異注入は行わない** (常設規律 §0.1 の 2 の「テストで固定される条件」に該当する完了条件が無い)。**代わりに全条件へ「監査が何を何と突き合わせるか」を明記する** — 下の各条件の**監査照合**がそれであり、§9 の照合表が対応の全体を示す。

1. **設計 §10 実施記録** — 5 つの WP すべてについて、コミット・集計行・実際に採った形・レビュー指摘の内訳・変異注入の結果・受理境界が記録されていること。**プレースホルダが 0 件**であること。**監査照合**: §10 の表の各行を、(i) `git log --oneline` の当該 merge コミット、(ii) 各 WP の完了報告に転記された root suite 集計行、(iii) 本書 §11 の同じ行と突き合わせ、**3 者が一致する**ことを確認する。「実際に採った形」は各 WP の**発注時の記述**と突き合わせ、食い違いがあれば**実装が正**として記録されていることを確認する。「変異注入の結果」は各 WP の対応表の**変異行の件数**と一致することを確認する。
2. **実測事項の確定内容** — WP-3 の実測 4 件 ((i) 実 DB の既存 field / (ii)(iii) 両 backend の一致 / (iv) `boolean` の round-trip)、WP-1 の静的固定テストの規則の確定形、WP-0 の同型性テストの裁定が §10 に記録されていること。**設計の想定と食い違った点が訂正註として残っている**こと (履歴を消していないこと)。**監査照合**: 記録された内容を各 WP の完了報告の実測値と語単位で突き合わせ、**主張が実測を超えていない**ことを確認する (常設規律 3)。
3. **CONDITIONS.md** — 新条件が監督裁定の登録先に置かれ、限界 3 点 (a)(b)(c) が書かれていること。C-09 / C-11 / C-12 / C-17 行が更新され、**C-09 の限界 (a) が無傷**であること。`test_conditions_register.py` のマーカー/行対応が**双方向で緑**。**監査照合**: 新条件が逐語に引くテスト名を 1 件ずつ `grep -rn conformance-tests` し、**全件が実在テストへ解決する**ことを確認する。限界 (a) は `git diff` で**変更 0 行**であることを確認する。限界の文言は**設計 §6.3 の該当段落**と突き合わせ、主張の強さが設計を超えていないことを確認する。
4. **CONTROL_MAPPING** — SI-06 / SI-07 / SI-08 / SI-10 / SI-13 / SI-14 / SI-15 の各行が**両 peer の cell を対で**書き換えられ、SI-06 / SI-07 の r2db 側が L6-1 (ii) の訂正を含むこと。**監査照合**: 各 cell が挙げる evidence テスト名を 1 件ずつ `grep -rn` し、**全件が 1 件以上に解決する**ことを確認する。各行の記述を**設計 §7 の該当段落**と突き合わせ、「不変」と書かれた invariant を「改善」と書き換えていないことを確認する (SI-14 は**不変**であり、フェーズ6 は帰属能力を変えない)。
5. **日付付き注記 3 件** — `MITATEDB_PHASE3` :22 (WP-3 が置いたものの確認)、`PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4、第12次引き継ぎ §4-2。**原文が残り、注記が日付付きで添えられている**こと。**監査照合**: 3 箇所の `git diff` を読み、**原文の行が削除されていない**こと、注記が「本フェーズの出荷で番号がずれた」事実を述べていることを確認する。`MITATEDB_PHASE3` については **WP-3 の差分に既に含まれ、本 WP で二重に書いていない**ことを確認する。
6. **runbook / 配備文書の全数更新** — `contract_version` / `surfaces` / `field_types` / upgrade script `0006` の手順を持つべき文書が**すべて**更新されていること。**grep で実表記を確認したうえでの掃討**であること。**監査照合**: 掃討に使った grep 語一覧とその実行結果を、更新した文書の一覧と突き合わせ、**ヒットした全ファイルが更新済み一覧に含まれる**ことを確認する。宣言例を**両 peer が実際に返す構造** (WP-2 / WP-3 完了条件で実 HTTP 経路から観測した値) と突き合わせ、キー名・値の形が一致することを確認する。
7. **DEPLOY 文書の配備後チェック** — §4-1 に (i)〜(iv) の 4 項目が加わっていること。**とくに (ii) `surfaces` の 2 文書一致が「実装が検出できない性質を運用が担う」ものとして書かれている**こと (L6-5a)。**監査照合**: 4 項目それぞれを、**両 peer が実際に返す文書**と突き合わせ、チェックが実行可能な形 (どのコマンドで何を見るか) で書かれていることを確認する。
8. **従属判断 11 の実施記録** — 各項目の出荷コミットと additive 主張を支えた実測が追記されていること。**監査照合**: 記録されたコミットを `git log --oneline` と突き合わせ、実測を各 WP の完了報告と突き合わせる。
9. **引き継ぎ第13次** — 最終集計行・各 WP のコミット・依頼者の次の判断事項・本フェーズが増やした運用前提が明記されていること。**監査照合**: 最終集計行を**本書 §11 の最終行**および完了ゲートの実測値と突き合わせる。各 WP のコミットを `git log --oneline` の merge コミットと突き合わせる。判断事項を**設計 §11 の残存項目**および `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 の未結審項目と突き合わせ、**取りこぼしが 0 件**であることを確認する。
10. **正直さの後退がないこと** — 「閉じた」の主張が、実際には片方の peer でしか閉じていない状態を覆い隠していないか。範囲外項目が「対応不要」と読める書き方に化けていないか (**依頼者判断待ちである**)。**監査照合**: 各「閉じた」主張を**両 peer 分の実装コミット**と突き合わせる (L5-4 は WP-3 の申告メソッド削除が揃って初めて閉じる)。範囲外項目の各行を**本書 §2 の列挙**および設計 §11 と突き合わせ、「対応不要」「解決済み」と読める語が使われていないことを確認する。**`surfaces` について「発見できるようになった」という記述が、「宣言が実在を保証しない」(L6-5) を覆い隠していないか**を確認する。
11. **秘密の非混入** — 追記した全箇所に実値の DSN / パスワード / 実在ドメイン / 実データが無いこと。**監査照合**: 本 WP の `git diff` の追加行全体を、`docs/security/public-repository-policy.md` の禁止事項一覧および CLAUDE.md の Public Repository Security Gate と 1 項目ずつ突き合わせる。ホスト名・DSN・鍵らしき文字列を含む追加行を列挙し、**すべてが環境変数名・secret-manager 参照・架空ドメイン・合成 fixture のいずれか**であることを確認する。
12. **対応表 (§9 の照合表) に対応の無い行が無いこと** (メタ条件)。
13. **root suite の最終実測 (単独実行)** の集計行を本書 §11 に記録すること。**監査照合**: 記録した集計行を、**監督が単独実行して得た実測出力そのもの**と突き合わせ、`passed` / `failed` / `skipped` / `xfailed` の 4 数が一致すること、および**出所 (誰がいつ単独実行した値か)** が明記されていることを確認する。起草時の再実行値を転記していないこと。

#### 非 vacuity 要件

**本 WP は文書のみであるため、テストの非 vacuity 要件は無い。** 代わりに **evidence テスト名の実在性** (条件 3 / 4 の監査照合) がその位置を占める — **1 件でも grep に解決しない名前があれば赤**である。

#### 同型性テスト対象

**変更なし** (テストを触らない)。WP-0 / WP-3 で確定した対象一覧を §10 に記録する。

#### テストコマンド

```
./.venv/bin/python -m pytest -q conformance-tests/test_conditions_register.py
./.venv/bin/python -m pytest -q          # 完了ゲート、単独実行 (件数不変であること)
```

#### レビューが必ず探すべき点 (Opus、テンプレ 6 = 受け入れ監査)

1. **記録と実装の乖離** — CONTROL_MAPPING / CONDITIONS / 設計 §10 / 台帳が主張する evidence が、実在し実際に走るテストへ解決するか。**各 WP で採ったテスト名と、本書の完了条件に書いた予定名が食い違っていないか** (食い違うなら**記録側を実装に合わせる**)。
2. **正直さの後退** — 「クライアントが両 surface へ到達できるようになった」という記述が、**宣言が実在を保証しないこと** (L6-5) と **2 プロセス間ドリフトを実装が検出できないこと** (L6-5a) を覆い隠していないか。
3. **SI-14 の書き方** — 「改善」と書いていないか。**D-1 は帰属能力を変えない** (設計 §7、両 peer は既に対称)。フェーズ5 が v1.1 → v1.2 で訂正した誤りを繰り返していないか。
4. **範囲外項目の扱い** — Q4 / フェーズ7 / 実機適用 / alias 除去 / L4-8 / L4-12 / L4-13 / L5-5〜L5-8 が、「対応不要」ではなく**依頼者判断待ち / 将来課題**として保たれているか。
5. **代償の記録** — 既存 credential の再発行が必要になったこと、MitateDB の挙動変更 3 件が既存クライアントに影響しうることが、runbook に**運用者責任として**書かれているか。「対称化した」だけの記述に化けていないか。
6. **台帳の取りこぼし** — WP-0〜3 のレビュー・受け入れ監査で「本書では扱わない」と裁定された項目が、すべて設計 §11 (将来課題) へ落ちているか。

#### 使用テンプレート

起草 = Opus (テンプレ 4 = 文書起草)。受け入れ監査 = Opus (テンプレ 6)。

---

## 5. 期待される実測値

| WP | root suite (passed / failed / skipped / xfailed) | conformance | 期待される変化 |
|---|---|---|---|
| **基準値** | **1611 / 0 / 0 / 0** (2026-09-04、main `a211584`) | **422 passed** | フェーズ5 完了時点 |
| **WP-0** | `{実装者が報告し監督が記録}` / 0 / 0 / **0** | **422 (不変)** | 両 peer の fail-fast ケース (5 形 × 2 peer + 既定値経路) + MitateDB の byte 同一テスト 1 本 + 同型性テストの一般化 (対応表 13 行 + 行数を pin するテスト。**parametrize の形にすると収集件数が 1 → 13 へ増えうる**)。**契約に触れないので conformance は不変**である |
| **WP-1** | `{実装者が報告し監督が記録}` / 0 / 0 / **2** | `{報告}` passed / **2 xfailed** | 共通 vector の新規分。**共通テストは 4 adapter でパラメータ化される**ためテスト関数 1 本が収集 4 件になり、**declare-and-echo だけは HTTP plug 2 件**、**否定側は 6 語 × 4 plug = 24 件**である。加えて全体 vacuity guard 1 本 (**非 parametrize の registry 走査**、収集 1 件) と静的固定テスト (収集件数は実装形による) が **xfailed**。**load-bearing の内訳**: 本 WP で実観測を伴うのは port v1.10 (b) のフォールバック経路のみであり、新 vector 3 種は 1.6.0 declare-first なので全 adapter が分岐を素通りする |
| **WP-2** | `{実装者が報告し監督が記録}` / 0 / 0 / **2** | `{報告}` | r2db の出荷。共通側では新 vector 3 種が **r2db の 2 plug で初めて 1.6.0 分岐へ入る** (収集件数は増えないが観測が増える)。**同型性 placeholder を登録した場合は xfailed 3** — その場合は完了報告に明記し監督裁定を得る |
| **WP-3** | `{実装者が報告し監督が記録}` / 0 / 0 / **0** | `{報告}` | MitateDB の出荷。**xfailed 2 → 0** (guard + 静的固定テスト。placeholder があれば 3 → 0)。**port の申告メソッド削除で収集件数が減りうる**ため単純な純増にならない。**新 vector 3 種が 4 plug 全数で load-bearing になる** |
| **WP-4** | `{実装者が報告し監督が記録}` (件数不変) / 0 / 0 / **0** | `{報告}` (不変) | 文書のみ |

**本数は「テスト関数数」ではなく「収集された test id 数」で数える** — 共通 suite は 4 adapter で、両 peer の一部テストはさらにパラメータ化されている。**上表の `passed` 欄は見積りを置かない** — 実装者が増減内訳を報告し、監督が記録する。**xfailed の期待値だけは上表が正**であり、**xfailed が想定と違う値なら完了と判定しない。**

**完了ゲートの判定**: 各 WP で root suite を単独実行し、`failed` / `skipped` が **0**、`xfailed` が上表と一致し、`passed` (収集件数) の増減内訳が説明されていること。**見積りと実測が食い違ったら、実測が正であり、食い違いの理由を完了報告に書くこと。**

---

## 6. 完了ゲートの実測規律 (全 WP 共通。フェーズ5 §6 を継承)

- 完了ゲートの root suite は**リポジトリルートで単独実行する**。**`ps` で他の pytest プロセスが 0 件であることを確認してから実行する** — PG クラスタの並走衝突で偽の赤が出る (フェーズ3.5 で 2 回発生)。
- **テストは前景で実行する。`timeout` を明示すること (600000 ms)。** root suite は長時間かかる。**サブエージェントはバックグラウンド待ちで止まるので、完了ゲートの実測値は監督が自分で握る** (第12次 §5 の教訓)。
- 実 PostgreSQL は `R2DB_TEST_ADMIN_DSN` / `MITATEDB_TEST_ADMIN_DSN` (既定 `host=/tmp port=5432 dbname=postgres`)。**未接続は fail であり skip しない** — skip が出ていたら環境の問題として解決してから完了と判定する。
- 各 WP の完了報告に **集計行 (passed / failed / skipped / xfailed)** を必ず記録し、**増減の内訳** (どのテストが何本増えたか / 減ったか / 差引) を書く。
- **変異注入は scratchpad へ復元する。`git checkout` は使わない。**
  - **本リポジトリは Google Drive 同期ツリーである。** 変異前に対象ファイルを scratchpad へ backup し、**`sleep 3` の後に `sha256` で二重照合する** (backup と復元後の一致を 2 回確認する) — 同期が復元を巻き戻す事故が第12次でも観測されている。
  - **コミット前に変異文字列そのものを全文 grep する** (差分の一致確認は「消えていないこと」しか保証しない)。
  - **ファイルの退避・再インストール・migration の適用を伴う変異** (WP-0 変異 4 / 4′ / 5、WP-3 変異 6 / 7) は、**復元後の再構築結果も報告に書く。**

---

## 7. 禁止事項 (全 WP 共通)

1. **git commit / push は監督のみが行う**。Sonnet も Opus もコミットしない。
2. **契約ファイルを変更するコミット (WP-1) は依頼者確認後に行う** (設計 §2 の 9)。**契約の英文は `scratchpad/phase6-contract-prose.md` の確定文から逐語複製する** — 言い換え・要約・語順の入れ替えを禁じる。確定前に spec を書いてコミット可能な状態にしない。
3. **WP-1 以外で `spec/` を変えない**。WP-0 は契約不変 (新設する MitateDB のパッケージ内コピーは 1.5.0 の byte 同一コピーである)、WP-2 / WP-3 は peer の宣言と `contract_version` のみ、WP-4 は契約に触れない。両 peer のパッケージ内コピーも同様。
4. **互換シムを作らない。二形式受理を置かない。** 旧形式 (secret 単独) の受理、`field_types` を無視する分岐、`surfaces` を返さない場合の暗黙のフォールバックを製品コードに置かない。**移行は再発行と upgrade script で行う** (設計 §2 の 5)。**port のフォールバック分岐 (WP-1 の同居判定) だけは例外であり、WP-3 で必ず消える。**
5. **migration は 3 分類で扱う (監督裁定 2026-09-04、確定)。**
   - **(a) 一回適用 migration は不変である** — 運用者が既に適用したファイルを書き換えない。r2db の `0005_credential_store.sql` / `0006_control_plane_http.sql`、MitateDB の `0001` / `0002` / `0005` が該当する。**偽になったコメントの訂正先はコード側と runbook である** (L6-1 の (i)(ii)(iv))。
   - **(b) per-application provisioning script はテンプレートであり、改訂してよい** — MitateDB の `0003_provision_application.sql` / `0004_deprovision_application.sql` は provisioning / deprovisioning のたびに 1 application ずつ実行されるテンプレートであって、一回適用の migration ではない。**宣言型 registry を作るための `0003` の改訂は本フェーズの発注事項であり、(a) の禁止の対象ではない。**
   - **(c) 既存 application データベースは upgrade script `0006` で (b) と同じ終状態へ運ぶ** — `0003` の改訂は既存 DB に遡及しないため、per-application の upgrade script `0006` を新設して当てる。**(b) を当てた新規 DB と (c) を当てた既存 DB が同じ終状態になること**が要件である (backfill 規則は §4 WP-3 の変更対象 C)。
   - **この 3 分類の外で migration を触らない。** 必要に見えたら監督へ差し戻す。
6. **契約を言い換えない。** 契約の英文・従属判断の文言・CONDITIONS の限界開示に、確定文の要約・意訳・「趣旨は同じ」書き換えを置かない (常設規律 4)。
7. **adapter へ実装知識を再導入しない。** bearer の合成・分解、peer ごとの credential 形式の分岐、`surfaces` の推測を adapter に書かない。**共通 suite が peer の内部形式を知る形は、指摘 2 が検出できなかった原因そのものである。**
8. **契約に実装固有の構造を漏らさない。** `<credential_id>.<secret>` という内部構造、locator という実現形、registry という保持機構を契約本文に書かない (制約 2)。
9. **偽の flip を行わない** — 宣言を真にする挙動が同一コミットに無いまま `contract_version: 1.6.0` や `application_catalog: enabled` を宣言しない。逆に、1.6.0 の挙動を出荷しながら 1.5.0 を宣言し続けることも禁じる。**過渡期 (WP-1 完了〜各 peer の flip まで) に peer が 1.5.0 を宣言し続けるのは正しい lag であって非適合ではない。**
10. **guard を弱めて緑にしない** — 全体 vacuity guard の `strict=True` を落とす、全数要求を「1 本でも通れば緑」へ緩める、`registered_adapters()` 走査を adapter 名の列挙へ退化させる、静的固定テストの分解不在 (b) を落とす、のいずれも禁じる。**緑にする正しい手段は実装を真にすることだけである。** `xfail` を外すのは **WP-3 のコミットのみ**。
11. **撤去 3 点を分割しない** (WP-3)。guard の `xfail` / 静的固定テストの `xfail` と adapter 合成 / port 申告メソッドと 4 plug 実装 — **どれか 1 つだけ先に落とすと、その時点で赤になるか vacuous になる。**
12. **peer 間でコードを共有しない。** 同名ヘルパは同型性テストで固定する。共有モジュールを作らない (既存の慣行、設計 §2 の 3)。
13. **`git checkout` による変異復元を禁じる。** 復元は scratchpad backup からのコピーであり、`sleep 3` 後に sha256 を 2 回照合する。
14. **テストの並行実行を禁じる。** 完了ゲートは単独実行する。`ps` で他の pytest が 0 件であることを確認してから。
15. **範囲外項目に触れない** (§2) — Q4 / フェーズ7 の指摘 1・7 / 実機適用 / 1.4.0 alias の除去 / `_optional_int` / `mutation_classes.rule` 側の語法 / L4-8 / L4-12 / L4-13 / L5-5〜L5-8。「ついでに」直さない。
16. **制約・制限の追加で問題を回避しない** (依頼者設計原則 3)。新しい上限・拒否経路・機能制限を、難所を回避するために足さない。**`json` を「受理しにくいから型無しのまま」にする、`surfaces` を「検証できないから任意」に緩める等は回避である。**
17. **設計外の拡張を実装前に上げる** (常設規律 5)。静的固定テストの規則、同型性テストの走査範囲、build context の変更、port fixture の形は、いずれも**実測して監督裁定を得てから**実装する。
18. **秘密・実データ・実在ドメインを書かない。** 環境変数名・secret-manager 参照・架空ドメイン (`example.invalid` 等)・合成 fixture のみ。**公開リポジトリである。** とくに `surfaces` の例示と runbook の再発行手順に注意する。
19. **変異ファイル・変異定義を残さない。** 変異は必ず除去し、**scratchpad backup + sha256 二重照合**で復元を確認し、**コミット前に変異文字列を全文 grep する。**

---

## 8. コミット規律

- **WP ごとに 1 コミット** (WP-0 / WP-1 / WP-2 / WP-3 / WP-4 で計 5 コミット)。それ以外の分割は監督の許可を要する。
- **契約公開 (WP-1) は単独コミットである** — spec / 両 peer のパッケージ内コピー / 従属判断 11 / 共通テスト / port v1.10 / §20 / 2 本の `xfail` 登録 / 文字列ピンを 1 コミットに入れ、**peer の版数 flip は入れない**。
- **flip は挙動出荷コミットに束縛する** — `contract_version` 1.6.0 の宣言と、それを真にする挙動は**同一コミット**。**MitateDB の `application_catalog: enabled` も同じ規律**である。版数を固定しているローカルテストの更新、および **WP-3 における撤去 3 点**も同一コミット。
- **契約変更コミット (WP-1) は依頼者確認後**である。監督が確定文言を依頼者へ明示し、確定を得てからコミットする。**契約版に触れるコミットは依頼者確認後に行う。**
- **identity は `r2fish` / noreply**。実名・Gmail を使わない。**コミット前に必ず `git log --format='%an <%ae>'` で確認する。**
- **commit → push → main merge (`--no-ff`) は 1 セット**。コミットしたら直ちに push し、main へマージする。**分離しない。**
- コミットメッセージは日本語可。**WP 番号・変更の要旨・完了ゲートの集計行 (`Root suite alone:` 行) を含める** — 後から `git log` で照合できる形にする。
- 各コミットの前に、独立レビュー (Opus、変異注入込み) と受け入れ監査の往復が完了していること。

---

## 9. WP-4 の照合表 (完了条件 → 監査照合項目)

**本 WP は変異を作らないため、全行が照合項目である** (常設規律 §0.1 の 2)。詳細は §4 WP-4 の各条件の**監査照合**にある。

| 完了条件 | 何を何と突き合わせるか |
|---|---|
| 1 設計 §10 実施記録 | §10 の表 ↔ `git log` の merge コミット ↔ 各 WP 完了報告の集計行 ↔ 本書 §11 / 「実際に採った形」 ↔ 発注時の記述 (食い違いは実装が正) / 「変異注入の結果」 ↔ 各 WP 対応表の変異行の件数 |
| 2 実測事項の確定内容 | §10 の記録 ↔ 各 WP 完了報告の実測値 (語単位) / 訂正註 ↔ 設計の当初想定 (履歴を消していないこと) |
| 3 CONDITIONS.md | 新条件のテスト名 ↔ `grep` 実在性 / 限界 3 点 ↔ 設計 §6.3 / C-09 限界 (a) ↔ `git diff` 0 行 / マーカー対応 ↔ `test_conditions_register.py` 双方向緑 |
| 4 CONTROL_MAPPING | evidence テスト名 ↔ `grep` 実在性 / 各行 ↔ 設計 §7 の該当段落 / SI-14 ↔ 「不変」であること / SI-06・SI-07 の r2db 側 ↔ L6-1 (ii) |
| 5 日付付き注記 3 件 | 3 箇所の `git diff` ↔ 原文の非削除 + 日付付き注記の存在 / `MITATEDB_PHASE3` ↔ WP-3 の差分 (二重記載でないこと) |
| 6 runbook / 配備文書 | grep 語と結果 ↔ 更新済み文書一覧 / 宣言例 ↔ 実 HTTP 経路の観測値 (WP-2 / WP-3 の完了条件) |
| 7 DEPLOY の配備後チェック | (i)〜(iv) の 4 項目 ↔ 両 peer が実際に返す文書 / (ii) ↔ L6-5a (実装が検出できない性質を運用が担うこと) |
| 8 従属判断 11 の実施記録 | 記録されたコミット ↔ `git log --oneline` / 実測 ↔ 各 WP 完了報告 |
| 9 引き継ぎ第13次 | 最終集計行 ↔ 本書 §11 と完了ゲート実測 / コミット ↔ `git log` / 判断事項 ↔ 設計 §11 + PHASE4 §11.2 の残存項目 (取りこぼし 0 件) |
| 10 正直さの後退がないこと | 「閉じた」主張 ↔ 両 peer 分の実装コミット / 範囲外項目 ↔ 本書 §2・設計 §11 / `surfaces` の記述 ↔ L6-5・L6-5a の開示 |
| 11 秘密の非混入 | `git diff` の追加行 ↔ `public-repository-policy.md` 禁止事項一覧・CLAUDE.md のゲート |
| 12 対応表が全行埋まる | 本表そのもの (メタ条件) |
| 13 root suite の最終実測 | 本書 §11 の集計行 ↔ 監督の単独実行出力 (4 数) と出所の明記 |

---

## 10. 使用テンプレートの対応

| WP | 実装 | レビュー | 監査 |
|---|---|---|---|
| WP-0 | Sonnet テンプレ 2 (実装) | Opus テンプレ 5 (コードレビュー、変異注入必須) | Opus テンプレ 6 (受け入れ監査) |
| WP-1 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-2 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-3 | Sonnet テンプレ 2 | Opus テンプレ 5 | Opus テンプレ 6 |
| WP-4 | Opus テンプレ 4 (文書起草) | — | Opus テンプレ 6 |

テンプレートの本文は `~/.claude/.../memory/role-prompt-templates.md` が正本。**各発注時に、当該 WP の「レビューが必ず探すべき点」と「変異注入」の節をテンプレートへ差し込むこと。**

**subagent への発注時の規律** (体制メモの load-shift に従う): 報告は短く上限を切り、**raw 出力は scratchpad のファイルへ**書かせる。長時間の suite は前景実行とし、`timeout` を明示する (600000 ms)。**完了ゲートの実測値は監督が自分で握る。**

---

## 11. 実施記録

(WP-4 で記入する。体裁はフェーズ5 作業指示書 §10 に従う — WP / 完了日 / コミット (merge) / 集計行 (root suite、単独実行) / 分割の有無 / レビュー指摘の内訳 / 変異注入の未実測分があればその明示。)

- **WP-0**: `{未実施}`
- **WP-1**: `{未実施}`
- **WP-2**: `{未実施}`
- **WP-3**: `{未実施}`
- **WP-4**: `{未実施}`

**本書の版数について**: §11 は記録欄であり、本節への追記では版数を上げない。**文言の訂正を要する箇所が見つかったときに版数を上げる。**
