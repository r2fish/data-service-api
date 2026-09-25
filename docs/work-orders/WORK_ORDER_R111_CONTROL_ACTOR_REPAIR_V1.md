# 作業指示書 — R-111 MitateDB http conformance adapter の制御 credential 修復経路

## 0. 版数・位置づけ

- **v1.0 (2026-09-26)。** 基点 local main `ffb0943` (契約 1.11.0。契約は変えない)。Change Set Manifest 形式 (`docs/design/ROADMAP_POST_PHASE7_V1.md` (以下 `RM`) §9 の 9)。
- 台帳: `RM` §8 の R-111。**規模 M** (`docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.13 の 73・74)。**変更クラス B** (`tools/change_class.py` 判定: MitateDB-api の conformance adapter と peer の tests。`RM` §9 の 8)。`spec/`・`conformance-tests/`・`security/`・`_ISOMORPHIC_TARGETS` に触れない。
- 設計文書は持たない (規模 M は作業指示書 1 節。`OC` §1.13 の 74)。枠は本書 §1 (監督確定。出所は監督の scratchpad の `$SP/frame-r111.md`)。
- 手本: `docs/work-orders/WORK_ORDER_R110_UNDECLARED_FIELD_REFUSAL_V1.md` の節構成 (§0〜§5)。写さず節番号で指す。
- 役割: 実装担当 (テンプレ 2) 1 回、コードレビュー (テンプレ 5、Class B) 1 回 (`docs/work-orders/ROLE_PROMPT_TEMPLATES.md`)。**監査担当は起動しない** (規模 M かつ Class B。`OC` §1.13 の 74)。commit・完了ゲート・merge は監督。
- 1 WP、1 worktree (`.claude/worktrees/r111`、branch `r111`)、1 commit、main へ 1 merge。

## 1. 監督確定事項

行番号は起草時 (`ffb0943`) の実測。以下 `MH` = `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`、`RH` = `r2db-api/conformance/conformance_adapter_r2db_http.py`。

### 1.1 再現 (事実)

部分集合 `conformance-tests -k "not r2db" -v -rxX -n 5 --dist loadgroup` を 2 回実行し、2 回とも同一 node `conformance-tests/test_c27_concurrent_same_key.py::test_c27_same_digest_executes_once[MitateDB-api-http]` が赤。集計行は `pt: 1 failed, 774 passed in 130.25s` と `pt: 1 failed, 774 passed in 129.90s`。

### 1.2 失敗の呼び出し連鎖 (事実。log の traceback から)

`test_c27_concurrent_same_key.py`:397 → `_assert_single_execution_audit_event` → :300 `_count_execution_audit_events(iso, request_id)` → :264 `control_actor = session_adapter.control_credential()` (この時点の probe は緑、handle H を得る) → :265-266 `_audit_query_control_state` (memo 済み)・`session_adapter.audit_visibility_lag_ms()` → :276 `audit_query(control_actor=H)` → `MH`:2087 `_control_send("POST", "/v1/audit/query", H)` → `MH`:1557 HTTP 401 `AUTH_INVALID`。

### 1.3 原因

- **F1 (事実)**: `MH`:1732-1738 `_control_actor_is_live` は `GET /control/v1/capabilities` の**あらゆる** `ConformanceDenial` で False を返す。`MH`:1757-1760 (`_ensure_control_actor`) はそのとき `_repair_control_actor` (`MH`:1762-1778。`ops reset` = 既存の制御 credential を全部 revoke → 新規発行 → self-rotate) を走らせる。
- **F2 (事実)**: 制御面の `control_requests_per_minute` は server 1 process の単一 sliding window (`MitateDB-api/src/mitatedb_api/control_plane.py`:1319-1330、bearer 抽出前に判定)。adapter の構成値は 200/min (`MH`:1131-1138 のコメント、`MitateDB-api/conformance/conformance_adapter_mitatedb.py`:675)。r2db も 200 (`RH`:1345)。C-05 の `_MAX_EXERCISABLE_LIMIT = 200` (`conformance-tests/test_c14_authority_boundary.py`:141) が「宣言上限は 1 テストで到達できる大きさ」を要求するので、上限を上げる案は採れない。
- **F3 (事実)**: MitateDB では adapter 内部で制御 credential を使う経路も公開 `control_credential()` (`MH`:1780-1781) を通り、**毎回** probe を 1 要求消費する (起草時の実測で内部の呼び出し元は 3 箇所: `MH`:2064 `_audit_query_status`、`MH`:2106 `audit_visibility_lag_ms`、`MH`:3056 tamper vector の in-band enable)。r2db の同名 helper `RH`:1783-1802 は cache を信頼して probe せず、`_privileged_control_send` (`RH`:1861、修復と再送は :1896-1907) が実操作の auth 拒否 (`_REPAIRABLE_AUTH_DENIAL_CODES = {AUTH_INVALID, AUTH_REVOKED, AUTH_REQUIRED, FORBIDDEN}`、`RH`:175) のときだけ修復して 1 回だけ再送する。公開 `control_credential()` (`RH`:2244-2270) だけが probe し、同 set 以外の拒否 (`LIMIT_EXCEEDED` / `AUTH_STATE_UNAVAILABLE`) はそのまま伝播させる (`RH`:2263-2269 のコメント)。
- **F4 (事実)**: `isolated_application_surface` (`MH`:1914-1922) は `copy.copy(self)` で `_control_credential_ref` / `_control_credential_secret` を値で複製する。iso 側の修復は親に戻らず、親の修復 (reset) は iso の cache を殺す。C-15 の `adapter.reset()` (`conformance-tests/test_c15_bootstrap_reset_lifecycle.py`:319、:340、:425、:586-587、`conformance-tests/test_c14_authority_boundary.py`:272) の後、親の cache は古いまま (`reset()` `MH`:1711-1716 は cache を更新しない) なので、以後 iso を使う各テストの最初の `control_credential()` が 401 → ops CLI reset の儀式を 1 回ずつ走らせる。r2db は `RH`:2455-2456 で iso の `_control_send` / `_privileged_control_send` を親の bound method に束ねる。
- **直列の 413 と並列の `AUTH_INVALID` (連鎖は決定的、発火条件は推測)**: 直列実行での 413 (台帳の記録) は窓の枯渇が probe 以外の呼び出しで表面化した形。並列 (`-n 5`) での `AUTH_INVALID` は窓の枯渇が probe (F1) で起き、破壊的 reset が呼び出し側の handle H を revoke した形 — `audit_visibility_lag_ms()` (`MH`:2106) 内の `control_credential()` の probe が 413 → reset → H 失効 → `audit_query(H)` 401。
- **部分集合で再現率が高い理由 (推測)**: 全体ゲートでは 5 worker が 6 plug 分の負荷で競合し MitateDB-http 群の実時間密度が下がる (330 s) が、部分集合 (130 s) では同じ制御要求列が短時間に詰まり 200/min に届く。worker 間の干渉ではない (adapter は worker ごとに別 prefix `mitatedbhttp<hex>` の platform を持つ、`MH`:956)。

### 1.4 問題設定と守るべき条件

1. 直すのは MitateDB http conformance adapter (socket adapter は継承) の制御 credential の扱い。契約・不変条件・`conformance-tests/` の test 本体・server 側 (`MitateDB-api/src/`) は触らない。Class B、規模 M。
2. 依頼者原則: テストの skip / retry / sleep で黙らせない。上限 200 を上げない (F2)。原因を直す。
3. 守るべき port 契約: `control_credential()` は呼び出し時点で有効な handle を返す (`docs/design/CONFORMANCE_ADAPTER_V1.md`:1434-1439 の M-4)。修復 (reset) は「本当に死んだ」ときだけ。
4. 同型性: r2db http adapter の既存の形 (F3・F4) を MitateDB 側に独立実装で揃える (コード共有はしない。P-6 の「同じ形の独立実装」)。

### 1.5 決定と根拠 (3 点、1 WP)

1. **probe の拒否分類**: `_control_actor_is_live` / `control_credential()` は auth 系の拒否 (`AUTH_INVALID` / `AUTH_REVOKED` / `AUTH_REQUIRED` / `FORBIDDEN`) だけを「死んだ cache」と読んで修復し、他の `ConformanceDenial` (`LIMIT_EXCEEDED`、`AUTH_STATE_UNAVAILABLE` 等) はそのまま伝播させる。根拠: F1・F3 (r2db の同名箇所と同じ判断)。
2. **内部経路は probe しない**: 内部 setup primitive が使う `_ensure_control_actor` は cache を信頼し、実操作が auth 系の拒否を返したときだけ修復して 1 回だけ再送する (r2db `_privileged_control_send` の形)。公開 `control_credential()` だけが 1 回の probe を持つ。根拠: F3 (窓の消費を半減、M-4 は公開 method の契約)。
3. **cache は親 1 箇所**: `isolated_application_surface` の copy が親と同じ cache を見るように束ねる (r2db `RH`:2455-2456 の形。実装の細部 = bound method を親に束ねるか、cache を親が持つ holder object にするかは実装担当の裁量)。根拠: F4。

### 1.6 却下した代替案と理由

- (a) test 側 `_count_execution_audit_events` で `AUTH_INVALID` を再取得・再試行: 破壊的 reset の誤発火を隠すだけ。依頼者原則。
- (b) adapter の `control_requests_per_minute` を 200 より上げる: C-05 `_MAX_EXERCISABLE_LIMIT = 200` と衝突し、「制約で回避」に当たる。
- (c) probe の 413 を sleep で待つ: 回避。窓を消費する構造 (F3) が残る。
- (d) server 側の窓を per-credential にする: 契約 1.8.0 の `limit_enforcement` (配備全体) と CONTROL_MAPPING の含意に触れる Class C/D。R-111 の範囲外。

### 1.7 未確定で依頼者判断待ちの選択肢

なし。

### 1.8 記録の置き場

変異を持たない完了条件 (0・6・7・8) の逐語記録は、設計文書が無いので本書 §5 に残す (`OC` §1.5 の 40)。log のパス・log のファイル名は本書に書かない (公開値スキャンの誤検知を避ける。パスは実装担当の報告と scratchpad にだけ置く)。traceback を貼らない (`OC` §1.9 の 63)。

## 2. WP-1 — 制御 credential の拒否分類・内部経路・cache の一本化

### 2.1 目的

`MH` の制御 credential の扱いを §1.5 の 3 点に改め、`test_c27_same_digest_executes_once[MitateDB-api-http]` の赤の原因 (破壊的 reset の誤発火と窓の浪費) を取り除く。

### 2.2 読むべき正本

- 本書 §1
- `MH`: :1231 `_run`、:1537-1563 `_control_send`、:1631-1702 (ops CLI の実行と解析)、:1711-1781 (`reset` 〜 `control_credential`)、:1914-1922 (`isolated_application_surface` の冒頭)、:2059-2066 `_audit_query_status`、:2076-2087 `audit_query`、:2105-2106 `audit_visibility_lag_ms`、:3042-3058 (tamper vector)
- `RH` (形の参照のみ。触らない): :168-175、:1783-1802、:1861-1907、:2244-2270、:2417-2456
- `docs/design/CONFORMANCE_ADAPTER_V1.md`:1434-1439 (M-4)
- `conformance-tests/test_c27_concurrent_same_key.py`:236-305、`conformance-tests/test_c14_authority_boundary.py`:141
- `conformance-tests/test_c19_client_self_sufficiency.py`:781、:1076 付近 (`MH` を静的に走査して bearer の合成箇所を数える。bearer を合成するコードを足さない)
- `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` の `_LazyDialTransport` の docstring (:277-313。iso の制御面呼び出しと event loop の関係)。socket adapter は起草時の実測で本件の method を再定義していない (上書きは `_surfaces_value`・`_operation_catalog_url_value`・`_build_client`・`_reset_surface_state`・`close` 等の hook)
- `MitateDB-api/tests/test_audit_query.py` の `_ISOMORPHIC_TARGETS` (:2383-2384、:2601-2603): `MH` の `_live_pg_backend_count`・`_build_client`・`_surfaces_value`・`_reset_surface_state` が登録済み
- 単体テストの `sys.path` の手本: `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_audit_writer_timeouts.py`:65-66 (この手本は実 adapter を組む。本 WP の単体テストは組まない — 2.4 のタスク 5)

### 2.3 現状と目標 (起草時の実測。着手時に再実測する)

| 箇所 | 現状 | 目標 |
|---|---|---|
| probe の拒否分類 (`MH`:1732-1738) | 全 `ConformanceDenial` を「死んだ」と読み reset | auth 系 4 code だけ修復。他は伝播 (決定 1) |
| 公開 `control_credential()` (`MH`:1780-1781) | probe 1 要求 + 死んだと読めば reset | probe 1 要求 (維持)。分類は決定 1 |
| 内部の呼び出し元 (`MH`:2064、:2106、:3056) | 公開 `control_credential()` 経由 = probe 1 + 実操作 1 | cache を信頼し実操作 1 要求。auth 系拒否で修復 + 1 回だけ再送、他は伝播 (決定 2) |
| `isolated_application_surface` (`MH`:1915) | `copy.copy` で cache を値複製 | 親と copy が同じ cache を読み書きする (決定 3) |
| `reset()` (`MH`:1711-1716) | cache を更新しない | 変えない (死んだ cache は次の実操作・probe の auth 拒否で修復される) |

再現の集計行 (§1.1): `pt: 1 failed, 774 passed in 130.25s` / `pt: 1 failed, 774 passed in 129.90s`。目標: 同じ部分集合で failed 0。

### 2.4 タスク

実装担当が順に行う。

0. **診断の実測 (完了条件 0)**。実装に入る前に行う。
   1. `MH` の `_control_actor_is_live` の `except` 枝に一時的な計測を入れる (拒否の `code` と時刻を 1 行で stderr へ)。併せて `_control_send` に一時的な計数を入れ、直近 60 秒の制御面要求数 (sliding window の実測値) をその拒否行に添える (窓の上限 200 に対する余裕を残すため)。
   2. 2.11 の部分集合 `-k "not r2db"` を 1 回実行する。
   3. 赤になった `test_c27_same_digest_executes_once[MitateDB-api-http]` の captured stderr に「probe が `LIMIT_EXCEEDED` を受けた行」があり、その後に同 node が `AUTH_INVALID` で赤になっていることを確かめる。
   4. 計測を手で戻し、`git diff --stat -- MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` が空であることを確かめる。
   5. §5 の完了条件 0 の欄に、集計行・計測の出力行 (code と時刻のみ)・`FAILED` の要約行を写す。log のパスは書かない (§1.8)。
   6. 再現しない、または連鎖が §1.2・§1.3 と違うときは、実装に進まず監督に上げる (`OC` §1.5 の 37)。
1. **決定 1**: auth 系 4 code (`AUTH_INVALID` / `AUTH_REVOKED` / `AUTH_REQUIRED` / `FORBIDDEN`) の集合を `MH` に独立に置き (`RH`:175 と同じ要素。import しない)、公開 `control_credential()` の probe はこの集合の拒否のときだけ修復に入り、それ以外の `ConformanceDenial` をそのまま伝播させる。
2. **決定 2**: `_ensure_control_actor` は cache を信頼して probe しない (cache が無いときだけ修復で作る)。内部の実操作は、auth 系 4 code の拒否のときだけ修復して 1 回だけ再送し、それ以外の拒否は再送せず伝播させる経路 (`RH`:1896-1907 の形) を通す。着手時に `MH` の内部で `self.control_credential()` を呼ぶ箇所を grep で再列挙し (起草時は :2064、:2106、:3056 の 3 箇所)、すべてこの経路に切り替える。公開 `control_credential()` の外形 (probe 1 回) は変えない。
3. **決定 3**: 親と copy が同じ cache を読み書きするようにする。束ねる範囲は、cache を読む箇所と書く箇所 (`_repair_control_actor` の代入、`MH`:1776-1777) の両方が親の 1 箇所に向くこと (完了条件 5)。method を親に束ねる形では iso の制御面呼び出しが親の `_loop` で走る (`_run`、`MH`:1231) — socket plug を含む部分集合 (タスク 7) で確かめる。登録済みの同型 helper (2.2 の `_ISOMORPHIC_TARGETS` の 4 件) の本体には触れない。
4. **comment / docstring**: `MH`:1741-1756 の `_ensure_control_actor` の docstring の「probe で自己修復」の理由文を、新しい判断 (内部経路は cache を信頼し、修復は auth 系の拒否のときだけ) に合わせて書き換える。新しい comment に経緯語 (WP-n / R-111 / phase N / 日付) を書かない (`MH` は provenance scan の外だが同じ規律で書く)。
5. **単体テスト** (新規 `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_control_actor.py`): PostgreSQL も実 server も使わない。`sys.path` は 2.2 の手本の形。
   - adapter は `__init__` を通さずに作る: `object.__new__(_http_module.MitateDBHttpConformanceAdapter)` に cache の属性 (決定 3 の形で置いたもの) を設定する。`name` はクラス属性 (`MH`:903)。
   - instance に `_control_send` / `_run_reset_ops_cli` / `_run_ops_cli` / `_control_credentials_has_any` / `_parse_issued_stdout` の偽物を置く。偽の `_control_send` は呼び出し (method・path・提示された secret) を記録し、台本どおりに応答するか `_http_module.ConformanceDenial(code=..., adapter=..., native_type=...)` を送出する。偽の ops CLI は呼び出し回数を記録し、新しい credential_id / secret を返す。
   - テスト名は 2.14 の表のとおり (T1〜T5)。
   - T5 は `isolated_application_surface()` 自体を通す (決定 3 の束縛はこの method の中にあるため、別 helper を直接呼ぶだけでは 2.14 の M5 が赤にならない)。必要な属性は `object.__new__` の instance に置き、`HttpService` / `create_app` / `_build_client` 等は `monkeypatch` で差し替える。PostgreSQL・実 server 無しで組めないと分かったら、実装前に監督へ上げる (`OC` §1.5 の 37)。
6. **変異**: 2.14 の M1〜M5 を `$SP/r111-mutations.json` に書き、2.11 の `mutate.py` で回す。
7. **部分集合 3 回と他 suite** (2.11)。
8. **報告**: `pt.py` / `mutate.py` の出力行 (集計行・変異表) をそのまま貼る (`OC` §1.10 の 65)。§5 の欄を埋める。

### 2.5 触ってよいパス

- `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`
- `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_control_actor.py` (新規)
- `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` (本件の method を再定義している箇所が着手時に見つかり、揃える必要があるときだけ。起草時の実測では無い)
- 本書 §5

### 2.6 触らないパス

`spec/`、`security/`、`conformance-tests/` (test 本体・`adapter.py`・`conftest.py`)、`MitateDB-api/src/`、`MitateDB-api/conformance/conformance_adapter_mitatedb.py`、`r2db-api/`、`docs/design/CONFORMANCE_ADAPTER_V1.md` (port は変えない)、`tools/`、`RM`、`OC`、`CLAUDE.md`、`MitateDB-api/tests/` の既存ファイル。これらに変更が要ると分かったら、実装前に監督へ上げる (`OC` §1.5 の 37)。

### 2.7 期待結果表 (commit の時点)

| 対象 | 期待 |
|---|---|
| 新規単体テスト (T1〜T5) | 5 node すべて ok |
| `conformance-tests -k "not r2db"` × 3 回 | 3 回とも failed 0 (`test_c27_same_digest_executes_once[MitateDB-api-http]` を含め全 node ok) |
| `MitateDB-api/tests` | 基点の件数 + 新規 5、failed 0 |
| `conformance-tests -k "not MitateDB"` | 基点と同件数、failed 0 |
| `mutate.py` | M1〜M5 がすべて `as expected` |

### 2.8 完了条件 (assert 水準)

0. **診断の実測**: 実装前の一時計測で「probe が `LIMIT_EXCEEDED` を受けて修復に入った直後に `test_c27_same_digest_executes_once[MitateDB-api-http]` が `AUTH_INVALID` で赤」を観測し、計測を戻したこと (`git diff --stat` 空) を §5 に記録している (監査照合)。
1. probe が `LIMIT_EXCEEDED` を受けたとき、`control_credential()` は `LIMIT_EXCEEDED` の `ConformanceDenial` を伝播し、reset 儀式 (`_run_reset_ops_cli` / `_run_ops_cli`) を 1 回も呼ばない (T1)。
2. probe が `AUTH_INVALID` を受けたとき、reset 儀式がちょうど 1 回走り、`control_credential()` は儀式が発行した新しい credential_ref の handle を返す (T2)。
3. cache が生きているとき、内部経路の 1 操作あたりの制御面 HTTP 要求 (`_control_send` の呼び出し) は 1 回で、probe (生存確認の `GET /control/v1/capabilities`) を含まない。対象は `_audit_query_status()` と `audit_visibility_lag_ms()` (T3)。加えて、`MH` の内部で `self.control_credential()` を呼ぶ箇所が 0 件 (タスク 2 の再列挙と切り替え後の grep を §5 に記録)。
4. 内部経路で実操作が `AUTH_INVALID` を返したら、reset 儀式をちょうど 1 回走らせて新しい secret で 1 回だけ再送する (送信は計 2 回)。`LIMIT_EXCEEDED` を返したら再送も儀式もせず `LIMIT_EXCEEDED` を伝播する (送信は計 1 回) (T4)。
5. `isolated_application_surface()` の copy で修復が起きた後、親の `control_credential()` は同じ credential_ref を返し、2 回目の reset 儀式を走らせない (T5)。
6. 部分集合 `conformance-tests -k "not r2db" -q -rxX -n 5 --dist loadgroup` を 3 回実行し、3 回とも failed 0 (監査照合: 集計行 3 行を §5 に記録)。監督が完了ゲートの前に 1 回追加で回す。
6a. 実装後・3 回の計測の前に、タスク 0 と同じ一時計数 (`_control_send` の直近 60 秒の要求数) を入れて部分集合を 1 回回し、MitateDB-http adapter が観測した 60 秒窓の最大要求数を §5 に記録し、計数を戻す (`git diff --stat` に計数の痕跡が無い)。観察の記録であり合否条件ではない (上限 200 に対する余裕を台帳の閉止注に書く。監査照合)。
7. `MitateDB-api/tests -q` の件数が基点 + 新規 5 で failed 0、`conformance-tests -k "not MitateDB" -q -n 5 --dist loadgroup` の件数が基点と同じで failed 0 (後者は本変更が r2db に触れないことの確認) (監査照合: 集計行を §5 に記録)。
8. 2.14 の表に、変異も監査照合も持たない行が無い (監査照合: 本表)。

### 2.9 非空振り要件

- T1〜T5 は、偽の `_control_send` が実際に呼ばれ、台本の拒否 (`LIMIT_EXCEEDED` / `AUTH_INVALID`) が実際に送出されたことを呼び出し記録で assert する (例外が出なかったこと・出たことだけで済ませない)。
- T2・T4 の「新しい handle」は、偽の ops CLI が発行した値と等号で比べる (旧 secret と異なることだけで済ませない)。T4 は再送に使われた secret が新しい secret であることを呼び出し記録で確かめる。
- T3 は要求数を等号 (`== 1`) で比べる (`_audit_query_status()` 自体が capabilities を読むので、path ではなく回数で probe の有無を区別する)。
- T5 は copy 側で修復が実際に起きたこと (儀式の呼び出し 1 回) を確かめてから、親側の呼び出しで儀式の回数が 1 のままであることを assert する。

### 2.10 同型性テストの対象

なし。`_ISOMORPHIC_TARGETS` を増減しない。登録済みの `MH` の 4 helper (2.2) の本体に触れると Class C になるので触れない (`RM` §9 の 8)。r2db と同名の helper を新設してもよいが、同型性テストへの登録は本 WP の範囲外 (Class D)。

### 2.11 道具の引数と集計行の期待形

リポジトリ root から root の `.venv` で起動する。`SP` は監督が発注時に渡す scratchpad。

```
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r111 --wait 300 -- MitateDB-api/tests/test_conformance_adapter_mitatedb_http_control_actor.py -q
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r111 --wait 300 -- MitateDB-api/tests -q
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r111 --wait 300 -- conformance-tests -k "not r2db" -q -rxX -n 5 --dist loadgroup
./.venv/bin/python tools/dev/pt.py -C .claude/worktrees/r111 --wait 300 -- conformance-tests -k "not MitateDB" -q -n 5 --dist loadgroup
./.venv/bin/python tools/dev/mutate.py "$SP/r111-mutations.json" -C .claude/worktrees/r111
```

- 部分集合 `-k "not r2db"` は 1 回約 130 s。前景で `timeout` 600000 を明示し、完了条件 0 で 1 回、完了条件 6 で 3 回。`-k "not MitateDB"` は 1 回。
- 集計行の期待形 (`<...>` は着手時に基点で実測して埋める):

| コマンド | 期待形 |
|---|---|
| 新規単体テスト | `pt: 5 passed` |
| `MitateDB-api/tests` | `pt: <基点 + 5> passed, 2 subtests passed` (基点の参考値: R-110 の記録 `1475 passed, 2 subtests passed`) |
| `-k "not r2db"` | `pt: <N> passed` (failed 0。起草時の再現 `1 failed, 774 passed` の 775 node がすべて ok になる形) |
| `-k "not MitateDB"` | `pt: <基点と同じ> passed` (基点の参考値: R-110 の記録 `776 passed`) |

- 変異ファイルの entry は **単一の node id、`-n` なし**とする (`mutate.py` は最初の赤で止まる)。conformance 全体・`tools/dev/gate.py`・`tools/dev/finalize.py` は監督だけが回す。

### 2.12 使用テンプレート

実装 = テンプレ 2、コードレビュー = テンプレ 5 (Class B)。受け入れ監査は起動しない (§0)。

### 2.13 禁止事項

- suite 全体 (`conformance-tests` 全体、root suite) を回さない (`OC` §1.6 の 42)。`tools/dev/gate.py` と `tools/dev/finalize.py` を実行しない (`OC` §1.11 の 70)。
- commit・push・merge をしない。下請けの Agent を使わない (`OC` §1.7 の 47)。
- skip / retry / sleep でテストを黙らせない。test 側で再取得・再試行しない (§1.6 の (a)(c))。
- `control_requests_per_minute` の構成値 200 を上げない (§1.6 の (b))。本書 §1 に無い機構 (窓を空にするための制御面 service の作り直し等) を足さない。必要と判断したら実装前に上げる (`OC` §1.5 の 37)。
- `conformance-tests/` と `MitateDB-api/src/` に触れない (2.6)。
- adapter・テストの comment に経緯語 (WP-n / R-111 / phase N / 日付) を書かない。
- bearer を `credential_ref` と secret から合成するコードを足さない (2.2 の `test_c19` の静的走査)。
- 変異による一時変更を残さない (復元は `mutate.py` に任せ、`git checkout --` を使わない)。タスク 0 の一時計測は手で戻し `git diff --stat` で空を確かめる。
- log のパス・log 名・traceback・作業機の絶対パスを本書に書かない (§1.8、`OC` §1.9)。

### 2.14 完了条件番号 → 変異

変異は `MH` の 1 箇所を壊す。`old` / `new` の文字列は実装後のコードから実装担当が書く (`old` は元ファイルで一意)。赤になる node は新規ファイル `MitateDB-api/tests/test_conformance_adapter_mitatedb_http_control_actor.py` の test。

| 完了条件 | 変異 (`file:操作`) | 赤になる test |
|---|---|---|
| 0 | 監査照合: タスク 0 の集計行・計測の出力行・`FAILED` の要約行と、計測を戻した後の `git diff --stat` 空 (§5) | — |
| 1 | M1: `MH` の公開 `control_credential()` の probe の拒否分類を「全拒否 = 死亡」に戻す (auth 系 4 code 以外でも修復に入る) | T1 `test_control_credential_propagates_limit_exceeded_without_reset` |
| 2 | M2: `MH` の公開 `control_credential()` から修復経路を消す (auth 系の拒否でも修復せず、旧い handle を返すか拒否を伝播する) | T2 `test_control_credential_repairs_once_on_auth_invalid` |
| 3 | M3: `MH` の内部経路 (`_ensure_control_actor` またはその呼び出し側) に probe を戻す (cache があるとき生存確認の `GET /control/v1/capabilities` を 1 回送ってから返す) | T3 `test_internal_control_call_sends_no_probe_when_cache_is_live` |
| 4 | M4: `MH` の内部経路の再送条件を全拒否に広げる (auth 系 4 code の判定を外す) | T4 `test_internal_control_call_resends_only_on_auth_denial` (`LIMIT_EXCEEDED` の脚) |
| 4 | M4b: `MH` の内部経路の修復後の再送を消す (儀式は走るが旧い secret のまま伝播するか、再送しない) | T4 (`AUTH_INVALID` の脚。監督追加 2026-09-26: 1 条件に 2 変異、両脚を非空振りにする) |
| 6a | 監査照合: 実装後の 60 秒窓の最大要求数 (§5) | — |
| 5 | M5: `MH` の `isolated_application_surface` の束縛を外す (copy が cache を値で持つ状態に戻す) | T5 `test_isolated_surface_repair_is_seen_by_parent` |
| 6 | 監査照合: 部分集合 3 回の集計行 (§5) | — |
| 7 | 監査照合: `MitateDB-api/tests` と `-k "not MitateDB"` の集計行 (§5) | — |
| 8 | 監査照合: 本表 | — |

## 3. merge (監督)

1. 実装担当の報告 → コードレビュー (テンプレ 5、Class B) → 差し戻しはファイルで (`OC` §1.7 の 49)。
2. 完了ゲートの前に、部分集合 `-k "not r2db" -q -rxX -n 5 --dist loadgroup` を 1 回追加で回す (完了条件 6)。
3. 完了ゲート `./.venv/bin/python tools/dev/gate.py -C .claude/worktrees/r111 --label r111` を 1 回。集計行を本書 §5 に足す。
4. `RM` v1.123: §8 の R-111 行に【追記】(完了条件・変異の結果・`pt.py` の集計行・完了ゲートの集計行) する。版数ログを 5 行に保ち、6 版目の行を `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__VERSION_LOG.md` へ移す (`OC` §1.16 の 78)。`security/CONTROL_MAPPING.md` は触らない (制御は変わらない)。
5. `./.venv/bin/python tools/dev/finalize.py -C .claude/worktrees/r111 --branch r111 --tools-tests -m <message file> --allow <触ったパス>` で commit と merge (1 commit)。`--allow` は 2.5 のうち実際に触ったパスと、`RM`・版数ログの記録ファイル・本書。引き継ぎ書は監督が別途。

## 4. 訂正註

(実施中に本書の誤り・発注後の監督裁定が生じたらここへ追記する。本文は書き換えない。`OC` §1.8 の 57。)

- §1.3 F3 の r2db の記述 (公開 `control_credential()` だけが probe する) は誤り。r2db の `_audit_query_status` (:2570)・`audit_visibility_lag_ms` (:2618)・in-band tamper vector (:3862) は今も公開 probe を通る。MitateDB 側は本 WP でこの 3 系統が r2db より 1 要求少ない形になった (コードレビュー F2、2026-09-26)。

## 5. 実施記録

(監査照合の逐語記録 — 実行したコマンドと集計行、または file:line — を完了条件番号ごとに記す。log のパス・log 名・traceback は書かない (§1.8)。完了ゲートの集計行は監督が記す。)

**完了条件 0** (診断の実測):

一時計測 (`_control_actor_is_live` の `except` 枝と `_control_send` に、拒否の `code` と直近 60 秒の制御面要求数を 1 行で stderr へ出す計測を追加) を入れて部分集合を 1 回実行: `pt: 1 failed, 774 passed in 129.57s (0:02:09)`。captured stderr に `R111_DIAG probe_denial code=LIMIT_EXCEEDED t=1790374097.28... window60=228` の行があり、その直後に `R111_DIAG probe_denial code=AUTH_INVALID t=1790374101.51... window60=221` が続く。同じログ内で `test_c27_same_digest_executes_once[MitateDB-api-http]` が `ConformanceDenial(code='AUTH_INVALID', adapter='MitateDB-api (http+postgres)', native_type='_HttpFailure')` で赤 (HTTP 401 `AUTH_INVALID`)。§1.2・§1.3 の連鎖と一致 (probe が `LIMIT_EXCEEDED` を受けて修復に入った直後に同 node が `AUTH_INVALID` で赤)。計測を手で戻し、`git diff --stat -- MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` は出力なし (空) であることを確認。

**完了条件 3** (内部で `self.control_credential()` を呼ぶ箇所の再列挙と、切り替え後の 0 件):

決定 2 着手時の再列挙: 3 箇所 (`_audit_query_status`、`audit_visibility_lag_ms`、`credential_reactivation_vectors` 内の in-band enable tamper vector `inband_enable_credential_after_revoke_then_reauthenticate_denied_attempt`)。3 箇所すべてを `_privileged_control_send` 経由に切り替え。切り替え後: `grep -n "self\.control_credential()" MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` → 0 件。

**完了条件 6** (部分集合 3 回の集計行):

```
pt: 775 passed in 126.96s (0:02:06)
pt: 775 passed in 135.61s (0:02:15)
pt: 775 passed in 129.90s (0:02:09)
```

**完了条件 6a** (実装後の 60 秒窓の最大要求数、合否条件ではない):

1回目の計測 (実装後、`_control_send` を通った要求すべてを計数): `pt: 775 passed in 130.48s (0:02:10)`。worker (`-n 5`) 別 max: `gw0`=19、`gw1`=4、`gw2`=204、`gw3`=174。**コードレビュー (opus、Class B) F1 の指摘により無効**: この計数は `_control_send` を通った要求の全部であり `/v1/audit/query` を含む。server 側では `/v1/audit/query`・`/control/v1/audit/query` は `control_requests_per_minute` とは別の窓 `audit_requests_per_minute` に課金される (`MitateDB-api/src/mitatedb_api/control_plane.py:1319-1358` の `_check_rate`/`_check_audit_rate`)。204 > 200 なのに赤が 0 件だったこと自体が、計数に制御面の窓へ課金されない要求が含まれる証拠。この数値からは上限 200 に対する余裕は導けない。

2回目の計測 (path に `/audit/query` を含まない `_control_send` の送信だけを計数 = server の `control_requests_per_minute` の窓に課金されるものだけ): 部分集合を 1 回実行、`pt: 775 passed in 129.41s (0:02:09)`。worker 別 max: `gw0`=17、`gw1`=4、`gw2`=176、`gw3`=163。計測を手で戻し、`git diff --stat` に計測の痕跡が無いことを確認 (差分は adapter・新規テスト・作業指示書の 3 ファイルだけ)。

なお、この計数は worker process 単位であり、それが単一の adapter instance の窓と 1:1 かどうかは未検証 (コードレビュー F1 の残り懸念)。176 は 200 未満だが、audit_query 系呼び出しを除いてもなお上限に近く、本 WP はこの数値から「200 への余裕」を主張しない。

**完了条件 7** (`MitateDB-api/tests` と `-k "not MitateDB"` の集計行、基点の件数):

```
pt: 1480 passed, 2 subtests passed in 142.28s (0:02:22)   # MitateDB-api/tests (基点 1475 + 新規 5)
pt: 776 passed in 136.72s (0:02:16)                        # conformance-tests -k "not MitateDB" (基点 776 と同数)
```

**完了条件 8** (2.14 の表の全行と変異表・本節の対応):

2.14 の表の 12 行 (完了条件 0/1/2/3/4/4b/6a/5/6/7/8、変異 M1〜M5+M4b) すべてに、変異表 (下記) または本節の監査照合記録のいずれかが対応している。空行なし。

**変異** (`mutate.py` の変異表):

```
M1       expect=red   got=red       OK  | 1 failed in 0.14s | restore=ok
M2       expect=red   got=red       OK  | 1 failed in 0.10s | restore=ok
M3       expect=red   got=red       OK  | 1 failed in 0.12s | restore=ok
M4       expect=red   got=red       OK  | 1 failed in 0.12s | restore=ok
M4b      expect=red   got=red       OK  | 1 failed in 0.12s | restore=ok
M5       expect=red   got=red       OK  | 1 failed in 0.11s | restore=ok
mutate: 6 mutations, 6 as expected, restores verified 1/1 files (sha256 x2), grep counts unchanged (n/a for 3 edits whose lines all exist in the pristine file)
```

対応: M1→完了条件 1 (T1)、M2→完了条件 2 (T2)、M3→完了条件 3 (T3)、M4→完了条件 4 の `LIMIT_EXCEEDED` 脚 (T4)、M4b→完了条件 4 の `AUTH_INVALID` 脚 (T4)、M5→完了条件 5 (T5)。

**完了ゲート** (監督):
